from django.apps import AppConfig
import os

class TelemetryConfig(AppConfig):
    name = 'telemetry'

    def ready(self):
        # Only run database migration/fix and start MQTT listener in the main process
        if os.environ.get('RUN_MAIN') == 'true':
            self.fix_database_schema()
            from .mqtt import start_mqtt_listener
            start_mqtt_listener()

    def fix_database_schema(self):
        from django.db import connection
        print("🔧 Checking and repairing telemetry database schema...")
        with connection.cursor() as cursor:
            # 1. Dynamically find and drop all foreign key constraints on telemetry_telemetryreading
            try:
                cursor.execute("""
                    SELECT tc.constraint_name 
                    FROM information_schema.table_constraints AS tc 
                    WHERE tc.table_name = 'telemetry_telemetryreading' 
                      AND tc.constraint_type = 'FOREIGN KEY';
                """)
                constraints = cursor.fetchall()
                for r in constraints:
                    constraint_name = r[0]
                    print(f"Dropping constraint {constraint_name}...")
                    cursor.execute(f"ALTER TABLE telemetry_telemetryreading DROP CONSTRAINT {constraint_name};")
                print("✅ Successfully dropped all foreign key constraints on telemetry_telemetryreading!")
            except Exception as e:
                print(f"Error dropping constraints: {e}")

            # 2. Clean up device_id non-numeric values
            try:
                cursor.execute("UPDATE telemetry_telemetryreading SET device_id = NULL WHERE device_id !~ '^[0-9]+$';")
            except Exception as e:
                pass
            
            # 3. Alter column device_id to integer
            try:
                cursor.execute("ALTER TABLE telemetry_telemetryreading ALTER COLUMN device_id TYPE integer USING device_id::integer;")
                print("✅ Successfully converted device_id column to integer type!")
            except Exception as e:
                print(f"ℹ️ device_id column alter failed: {e}")

            # 4. Drop NOT NULL on power column
            try:
                cursor.execute("ALTER TABLE telemetry_telemetryreading ALTER COLUMN power DROP NOT NULL;")
                print("✅ Successfully dropped NOT NULL constraint on power column!")
            except Exception as e:
                print(f"ℹ️ power column check skip: {e}")

            # 6. Drop NOT NULL on power_watts column
            try:
                cursor.execute("ALTER TABLE telemetry_telemetryreading ALTER COLUMN power_watts DROP NOT NULL;")
                print("✅ Successfully dropped NOT NULL constraint on power_watts column!")
            except Exception as e:
                print(f"ℹ️ power_watts column check skip: {e}")

            # 7. Dynamically add c1, c2, c3, c4 columns if they don't exist
            for col in ['c1', 'c2', 'c3', 'c4']:
                try:
                    cursor.execute(f"ALTER TABLE telemetry_telemetryreading ADD COLUMN {col} double precision DEFAULT 0.0;")
                    print(f"✅ Successfully added column {col} to telemetry_telemetryreading!")
                except Exception as e:
                    pass

            # 8. Dynamically add appliance_id column if it doesn't exist
            try:
                cursor.execute("ALTER TABLE telemetry_telemetryreading ADD COLUMN appliance_id integer;")
                print("✅ Successfully added column appliance_id to telemetry_telemetryreading!")
            except Exception as e:
                pass


