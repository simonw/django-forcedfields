"""
Tests of the timestamp field.

"""

import inspect
import unittest.mock as mock

import django.core.exceptions
import django.core.management
import django.db
import django.test

from . import models as test_models
from . import utils as test_utils
import django_forcedfields


class TestTimestampField(django.test.TestCase):
    """
    Since django.test.TestCase automatically applies the INSTALLED_APPS models
    and migrations, any syntax violations in the SQL generated by the models or
    their fields will trigger database-level errors before the test suites are
    even run. Therefore, the test cases in this class are able to verify correct
    database field data type and parameters but cannot check for valid SQL
    beforehand.

    """

    multi_db = True

    @classmethod
    def setUpTestData(cls):
        """
        TODO: Get test DB entity names from Django's TestCase class directly?

        """
        cls._db_aliases = test_utils.get_db_aliases()

    def _test_db_type_mysql(self):
        """
        Test output of the custom field db_type method with the MySQL backend.

        """
        connection = django.db.connections[test_utils.ALIAS_MYSQL]
        for config in test_utils.TS_FIELD_TEST_CONFIGS:
            current_kwargs_string = ', '.join(config.kwargs_dict.keys())

            with self.subTest(arguments=current_kwargs_string):
                test_field = django_forcedfields.TimestampField(
                    **config.kwargs_dict)
                self.assertEqual(
                    test_field.db_type(connection),
                    config.db_type_mysql)

    def _test_db_type_postgresql(self):
        """
        Test output of custom field db_type method with the PostgreSQL backend.

        """
        connection = django.db.connections[test_utils.ALIAS_POSTGRESQL]
        for config in test_utils.TS_FIELD_TEST_CONFIGS:
            current_kwargs_string = ', '.join(config.kwargs_dict.keys())

            with self.subTest(arguments=current_kwargs_string):
                test_field = django_forcedfields.TimestampField(
                    **config.kwargs_dict)
                self.assertEqual(
                    test_field.db_type(connection),
                    config.db_type_postgresql)

    def test_db_type(self):
        """
        Test simple output of the field's overridden "db_type" method.

        Only test thoroughly the overridden field behavior. Cursory checks will
        be performed to ensure fallback to Django default if necessary but
        those values will not be extensively checked.

        """
        backend_subtests = {
            test_utils.ALIAS_MYSQL: self._test_db_type_mysql,
            test_utils.ALIAS_POSTGRESQL: self._test_db_type_postgresql}

        for alias, subtest_callable in backend_subtests.items():
            db_backend = django.db.connections[alias].settings_dict['ENGINE']
            with self.subTest(backend=db_backend):
                subtest_callable()

    def test_field_argument_check(self):
        """
        Ensure keyword argument rules are enforced.

        For some reason, model and field check() methods are not called during
        test database setup or when dynamically creating and migrating model
        classes. I don't know where and when the checks are run or when the
        checks framework raises the returned errors.

        I'm just going to manually call the check() method here.

        I concatenate a test iteration count to the dynamic class name to
        prevent Django from issuing a warning "RuntimeWarning: Model
        'tests.testmodel' was already registered."

        Note:
            Validation covers actual model attribute values, not the field class
            instance arguments. Checks cover the field class arguments and
            field class state.

        See:
            https://docs.djangoproject.com/en/dev/topics/checks/

        """
        check_tests = {
            'fields.E160' : {
                'auto_now': True,
                'auto_now_add': True},
            'django_forcedfields.E160' : {
                'auto_now': True,
                'auto_now_update': True}}

        check_test_count = 0
        for check_error_id, kwargs in check_tests.items():
            test_model_members = {
                'ts_field_1': django_forcedfields.TimestampField(**kwargs),
                '__module__':  __name__}
            TestModel = type(
                'TestModel' + str(check_test_count),
                (django.db.models.Model,),
                test_model_members)
            model_instance = TestModel(ts_field_1='2000-01-01 00:00:01')
            check_results = model_instance.check()

            with self.subTest(field_args=', '.join(kwargs.keys())):
                self.assertEqual(len(check_results), 1)
                self.assertEqual(check_results[0].id, check_error_id)

            check_test_count = check_test_count + 1

    def test_field_deconstruction(self):
        """
        Test the custom field's deconstruct() method.

        See:
            https://docs.djangoproject.com/en/dev/howto/custom-model-fields/#field-deconstruction

        """
        test_field = django_forcedfields.TimestampField(
            auto_now_add=True,
            auto_now_update=True,
            null=True)
        name, path, args, kwargs = test_field.deconstruct()
        reconstructed_test_field = django_forcedfields.TimestampField(
            *args,
            **kwargs)

        self.assertEqual(test_field.auto_now, reconstructed_test_field.auto_now)
        self.assertEqual(
            test_field.auto_now_update,
            reconstructed_test_field.auto_now_update)
        self.assertEqual(test_field.null, reconstructed_test_field.null)

    def test_mysql_table_structure(self):
        """
        Test correct DB table structures with MySQL backend.

        Because all db_type method return values were tested in another test
        case, this method will only run a cursory set of checks on the actual
        database table structure. This module is supposed to test the custom
        field, not the underlying database.

        information_schema.COLUMNS.COLUMN_DEFAULT is a longtext field.

        See:
            https://mariadb.com/kb/en/mariadb/create-table/
            https://mariadb.com/kb/en/mariadb/sql-statements-that-cause-an-implicit-commit/

        """
        test_model_class_name = test_utils.get_ts_model_class_name(
            **test_utils.TS_FIELD_TEST_CONFIGS[0].kwargs_dict)
        test_model_class = getattr(test_models, test_model_class_name)
        connection = django.db.connections[test_utils.ALIAS_MYSQL]

        sql_string = """
            SELECT
                LOWER(`DATA_TYPE`) AS `DATA_TYPE`,
                LOWER(`IS_NULLABLE`) AS `IS_NULLABLE`,
                LOWER(CAST(`COLUMN_DEFAULT` AS CHAR(32))) AS `COLUMN_DEFAULT`,
                LOWER(`EXTRA`) AS `EXTRA`
            FROM
                `information_schema`.`COLUMNS`
            WHERE
                `TABLE_SCHEMA` = %s
                AND `TABLE_NAME` = %s
                AND `COLUMN_NAME` = %s
        """
        sql_params = [
            connection.settings_dict['NAME'],
            test_model_class._meta.db_table,
            test_model_class._meta.fields[1].get_attname_column()[1]]

        with connection.cursor() as cursor:
            cursor.execute(sql_string, sql_params)
            record = cursor.fetchone()

        self.assertEqual(record[0], 'timestamp')
        self.assertEqual(record[1], 'no')
        self.assertEqual(record[2], 'current_timestamp')
        self.assertEqual(record[3], 'on update current_timestamp')

    def test_postgresql_table_structure(self):
        """
        Test correct DB table structures with PostgreSQL backend.

        Because all db_type method return values were tested in another test
        case, this method will only run a cursory set of checks on the actual
        database table structure. This module is supposed to test the custom
        field, not the underlying database.

        information_schema.COLUMNS.COLUMN_DEFAULT is a longtext field.

        See:
            https://mariadb.com/kb/en/mariadb/create-table/
            https://mariadb.com/kb/en/mariadb/sql-statements-that-cause-an-implicit-commit/

        """
        test_model_class_name = test_utils.get_ts_model_class_name(
            **test_utils.TS_FIELD_TEST_CONFIGS[0].kwargs_dict)
        test_model_class = getattr(test_models, test_model_class_name)
        connection = django.db.connections[test_utils.ALIAS_POSTGRESQL]

        sql_string = """
            SELECT
                LOWER(data_type) AS data_type,
                LOWER(is_nullable) AS is_nullable,
                LOWER(column_default) AS column_default
            FROM
                information_schema.columns
            WHERE
                table_catalog = %s
                AND table_name = %s
                AND column_name = %s
        """
        sql_params = [
            connection.settings_dict['NAME'],
            test_model_class._meta.db_table,
            test_model_class._meta.fields[1].get_attname_column()[1]]

        with connection.cursor() as cursor:
            cursor.execute(sql_string, sql_params)
            record = cursor.fetchone()

        self.assertEqual(record[0], 'timestamp without time zone')
        self.assertEqual(record[1], 'no')
        self.assertEqual(record[2], 'now()')

    def test_field_save(self):
        """
        Test that the output values are correct in final SQL statements.

        For MySQL, this should bypass most of the django.db.DateTimeField value
        overrides.

        TODO:
            REMOVE THE TEST CONFIGS LIST SLICE

        """
        for config in test_utils.TS_FIELD_TEST_CONFIGS[:1]:
            test_model_class_name = test_utils.get_ts_model_class_name(
                **config.kwargs_dict)
            test_model_class = getattr(test_models, test_model_class_name)
            with self.subTest(test_model=test_model_class_name):
                self._test_field_save_values(
                    test_model_class,
                    config.save_values_dict)

    def _test_field_save_values(self, test_model_class, save_values_dict):
        """
        Test instantiating a test model class with multiple field values.

        Args:
            test_model_class (tests.models.*) Test Django model class.
            save_values_dict (dict): The timestamp field test config attribute
                containing model field attribute values and expected database
                fetch values after saving.

        """
        for key, value in save_values_dict.items():
            with self.subTest(attr_value=key):
                self._test_attr_value_for_all_backends(
                    test_model_class,
                    key,
                    value)

    def _test_attr_value_for_all_backends(
        self, test_model_class, attr_value, expected_value):
        """
        Run the test model saved value test for all available DB backends.

        Args:
            test_model_class (class): The class of the current model to use
                in the tests.
            attr_value: The value to save in the new model instance's attribute.
            expected_value: The value that is expected to be retrieved from the
                database after a successful save() call.

        TODO:
            Mock datetime.datetime.today() to ensure that parent DateTimeField
            functionality is not the source of datetime values in the database.

        """
        for alias in test_utils.get_db_aliases():
            if attr_value is django.db.models.NOT_PROVIDED:
                test_model = test_model_class()
            else:
                test_kwargs = {
                    test_utils.TS_FIELD_TEST_ATTRNAME: attr_value}
                test_model = test_model_class(**test_kwargs)

            backend = django.db.connections[alias].settings_dict['ENGINE']
            with self.subTest(backend=backend):
                if issubclass(expected_value.__class__, Exception):
                    self.assertRaises(
                        expected_value,
                        test_model.save,
                        using=alias)
                else:
                    test_model.save(using=alias)
                    retrieved_test_model = test_model.__class__.objects.get(
                        id=test_model.id)
                    retrieved_value = getattr(
                        retrieved_test_model,
                        test_utils.TS_FIELD_TEST_ATTRNAME)
                    if inspect.isclass(expected_value):
                        retrieved_value = retrieved_value.__class__

                    self.assertEqual(retrieved_value, expected_value)

    def test_field_update(self):
        """
        Test that an UPDATE statement correctly produces auto date.

        """
        raise NotImplementedError('Complete this test you lazy bastard.')

    def test_invalid_attribute_value(self):
        """
        Test that model attribute value is still validated.

        Just testing to make sure that any custom field modificatiosn haven't
        disrupted the parent DateTimeField's functionality.

        """
        test_model_class_name = test_utils.get_ts_model_class_name(
            **test_utils.TS_FIELD_TEST_CONFIGS[0].kwargs_dict)
        test_model_class = getattr(test_models, test_model_class_name)
        connection = django.db.connections[test_utils.ALIAS_MYSQL]

        test_model_kwargs = {
            test_utils.TS_FIELD_TEST_ATTRNAME: 'invalid'}
        test_model = test_model_class(**test_model_kwargs)

        self.assertRaises(
            django.core.exceptions.ValidationError,
            test_model.save,
            using=test_utils.ALIAS_MYSQL)
