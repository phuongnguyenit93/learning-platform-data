# Case Sensitivity, Filesystems, and lower_case_table_names

An application may run fine on a Windows developer machine yet fail when deployed to Linux simply because of a table name's letter case. For example, the code queries `SELECT * FROM Customer` while the table was created as `customer`. On a MySQL server that compares table names case-insensitively, the statement still runs; on a server that compares case-sensitively, the statement can report that the table was not found.

The cause relates to how the operating system and filesystem handle filenames, combined with MySQL's `lower_case_table_names` configuration. In the **DATABASE_MYSQL** module, understanding these rules helps design portable schema/table names and avoid errors when switching environments, restoring backups, or configuring replication.

## 1. Distinguishing Object Names from String Data

First, separate two commonly confused concepts:

- **Identifier names** are names of databases, tables, columns, indexes, views, or other SQL objects. Case-sensitivity rules for database and table names depend on MySQL configuration and the filesystem environment.
- **String data values** are contents stored in `VARCHAR` or `TEXT` columns or literals in SQL statements. Comparing `'Alice'` with `'alice'` is governed primarily by the expression/column's collation, not by `lower_case_table_names`.

For example, the following two issues belong to different mechanisms:

```sql
-- Table name Customer/customer: governed by MySQL identifier rules.
SELECT * FROM Customer;

-- String value comparison: governed by the expression's collation.
SELECT 'Alice' = 'alice';
```

On MySQL 8.0, the common default collation `utf8mb4_0900_ai_ci` is case-insensitive when comparing strings. If business requirements call for case-sensitive comparison, choose an appropriate collation, such as one ending with `_cs` for case-sensitive comparisons. Do not change `lower_case_table_names` to control how column contents are compared.

## 2. How Do Filesystems Handle Case Sensitivity?

Filenames can be handled in two primary ways:

| Characteristic | Behavior | Example |
|---|---|---|
| Case-sensitive | `Customer` and `customer` are two distinct names | Linux filesystems such as ext4 typically distinguish these two names |
| Case-insensitive | `Customer` and `customer` are treated as the same name on lookup | NTFS on Windows is typically case-insensitive by default; APFS on macOS is typically created in case-insensitive mode |
| Case-preserving | Preserves the original uppercase/lowercase spelling for display | A filesystem can store the display name `Customer` while still looking up `customer` as the same name |

Case-preserving and case-sensitive are not the same property. Windows typically preserves letter case when displaying filenames while still performing case-insensitive lookups. macOS can also use case-sensitive or case-insensitive APFS volumes depending on how the volume was created. Therefore, do not infer behavior from the OS name alone; know the actual filesystem and configuration of the datadir.

MySQL stores databases and tables in a manner tied to the filesystem. Although MySQL 8.0 has its own data dictionary for managing metadata, database/table name comparison must still remain compatible with the filesystem and is controlled by `lower_case_table_names`. A configuration incompatible with the filesystem's characteristics can cause object names to be handled unexpectedly or be rejected by the server.

## 3. Default Rules by Operating System

In typical MySQL installations, the defaults are usually:

| Common environment | Typical default | Consequence |
|---|---:|---|
| Windows | `1` | Database/table names are stored in lowercase and compared case-insensitively |
| Linux/Unix | `0` | Names are preserved as declared and compared case-sensitively |
| macOS | `2` | Names are preserved as declared but compared case-insensitively; suited for default case-insensitive filesystems |

These are common defaults, not a substitute for checking the configuration on a specific server. Distributions, installation methods, filesystems, volumes, and initialization settings can make the actual value differ from OS-based assumptions.

For example, a development team on Windows might create a table `Customer`. A Windows environment with `lower_case_table_names=1` accepts references to `customer`. When deploying the same database to Linux with `lower_case_table_names=0`, the name `customer` may not match the `Customer` table and the query fails.

## 4. The Three Values of `lower_case_table_names`

`lower_case_table_names` is the MySQL configuration variable controlling how letter case is handled for database and table names. Three values are commonly documented:

| Value | How names are stored | How names are compared | Typically suited environment |
|---:|---|---|---|
| `0` | Preserved exactly as created | Case-sensitive | Case-sensitive filesystems, common on Linux/Unix |
| `1` | Converted to lowercase when stored | Case-insensitive | Case-insensitive filesystems, common on Windows |
| `2` | Preserved as created | Converted to lowercase on comparison | Case-insensitive filesystems, common on macOS |

You can picture this with an example creating database `SalesDB` and table `Customer`:

- With `0`, MySQL keeps the names as declared; references to `SalesDB.Customer` must match the exact case.
- With `1`, names are stored as `salesdb.customer`; references `SalesDB.Customer`, `salesdb.customer`, or `SALEsDB.CUSTOMER` are compared case-insensitively.
- With `2`, names are preserved with their declared case, while lookups are case-insensitive.

The value `2` does not mean every filesystem can use this mode. It is designed for case-insensitive filesystems; on a case-sensitive filesystem, do not pick `2` as a way to get the best of both worlds.

### Checking the running value

Connect to the right MySQL Server and run:

```sql
SELECT VERSION();
SELECT @@GLOBAL.lower_case_table_names;
SHOW VARIABLES LIKE 'lower_case_table_names';
SHOW VARIABLES LIKE 'datadir';
```

`@@GLOBAL.lower_case_table_names` shows the active configuration value. `datadir` helps identify the data directory MySQL uses; if you need to verify filesystem properties, inspect the volume containing that directory on the server.

Do not rely on the MySQL client's configuration or the developer machine's OS to deduce the value on the server. An application may connect to a remote server running an entirely different OS and filesystem.

## 5. Scope of Case Sensitivity Rules

`lower_case_table_names` mainly controls how MySQL handles database and table names. Not every identifier in SQL follows the same rule:

| Name type | Rule to remember |
|---|---|
| Database/schema name | Affected by `lower_case_table_names` and filesystem configuration |
| Table name | Affected by `lower_case_table_names` and filesystem configuration |
| Table alias | Can be case-sensitive on Unix; behavior depends on the MySQL platform |
| Column name | Case-insensitive in MySQL |
| Index name | Case-insensitive in MySQL |
| Stored routine and event names | Case-insensitive in MySQL |
| String values in columns | Follows the collation or comparison operator used |

For example, with column names, the following spellings are treated as the same column:

```sql
SELECT CustomerID, customerid, CUSTOMERID
FROM customers;
```

However, do not apply this conclusion to table names on a server with `lower_case_table_names=0`. Additionally, table aliases have their own rules; if you want SQL portable across operating systems, use one consistent casing style for aliases and reference them consistently.

## 6. Testing the Difference in a Dedicated Schema

Perform this only in a test environment and within a schema dedicated to this lesson. Do not create objects differing only by case in databases holding real data.

Create a sample schema and table:

```sql
CREATE DATABASE CaseLab;
USE CaseLab;

CREATE TABLE Customer (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL
);

INSERT INTO Customer (id, full_name)
VALUES (1, 'Nguyen An');

SHOW TABLES;
```

Try querying with the exact created casing:

```sql
SELECT * FROM Customer;
```

Then try referencing it with different casing:

```sql
SELECT * FROM customer;
```

The result depends on `@@GLOBAL.lower_case_table_names`:

- With `0`, on a case-sensitive filesystem, the second query typically reports that the table was not found.
- With `1` or `2`, table names are looked up case-insensitively, so the second query can succeed.

To see how names are displayed, compare `SHOW TABLES` and the name in `SHOW CREATE TABLE`:

```sql
SHOW CREATE TABLE CaseLab.Customer;
```

With value `1`, MySQL stores database/table names in lowercase. With `0` and `2`, names are kept in their declared case. Record both the configuration value and the observed test result; do not record conclusions based only on your own development machine.

## 7. Why Should You Avoid Names Differing Only by Case?

On a server using `lower_case_table_names=0` and a case-sensitive filesystem, objects such as `Customer` and `customer` can coexist. But when moving to a server using `1` or `2`, those two names are treated as the same name. This can create conflicts during restores or migrations.

Common issues include:

- A migration script creates `Customer`, while ORM code accesses `customer`.
- A Windows development machine accepts a query with mismatched casing, while Linux production rejects it.
- A dump containing two tables differing only by case cannot be restored as-is into a case-insensitive environment.
- Deployment, backup, or file-sync tools handle object names differently across platforms.
- A source and replica with different configurations can process table names inconsistently, leading to errors or data not being applied as intended.

A safe convention for multi-environment projects is to name databases and tables in lowercase using `snake_case`, such as `sales_order`, `customer_profile`, `order_item`. Never create two tables differing only by letter case. Use the same convention across DDL, migrations, Java code, ORM mappings, reports, and operations scripts.

## 8. `lower_case_table_names` in MySQL 8.0

A critical operational point: in MySQL 8.0, `lower_case_table_names` must be decided when initializing the data directory. Once the server has been initialized, this value cannot be changed like a regular runtime configuration variable.

This means:

- You cannot safely switch a running server from `0` to `1` just via `SET GLOBAL` or by editing the config file and restarting.
- If you need to change modes, you must plan to create a new instance with the desired configuration, then migrate data via a controlled process.
- The value must be compatible with the filesystem characteristics where `datadir` resides. MySQL may refuse to start if the configuration is not supported on that filesystem.
- All existing database/table names must be reviewed for conflicts before transferring data.

To inspect the startup configuration file, an administrator can check the configuration used by the MySQL server. Example in a config file:

```ini
[mysqld]
lower_case_table_names=1
```

This is only a configuration example for a new instance on a case-insensitive filesystem. Do not add or change this line on an already-initialized `datadir` and expect MySQL to convert metadata automatically. Verify the instructions for your exact version and installation procedure before creating an instance.

## 9. Migrating Data Between Windows, macOS, and Linux

When migrating environments, check more than just MySQL version and charset. Check `lower_case_table_names` on both source and target.

Migration preparation process:

1. Record `SELECT VERSION()` and `SELECT @@GLOBAL.lower_case_table_names` on both the source server and target server.
2. List database/table names from metadata and look for pairs differing only by letter case.
3. Check whether DDL scripts, migrations, and application entity mappings use a consistent spelling.
4. If the target is case-insensitive, resolve name conflicts before importing; rename systematically and update all references.
5. Restore into a test environment, then run schema checks and integration tests from the actual target platform.
6. Cut over to production only after backups, rollback plans, and downtime windows or sync mechanisms are agreed upon.

Example metadata query to scan table names in a schema:

```sql
SELECT TABLE_SCHEMA, TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'CaseLab'
ORDER BY TABLE_NAME;
```

This query lists table names exactly as metadata provides them. To find names that might conflict when moving to case-insensitive mode, you can export the list and normalize to lowercase in a migration checker tool. Keep the original names to identify which objects need renaming; do not rename automatically without checking foreign keys, views, triggers, routines, and referencing code.

Never rename directories or files inside `datadir` using File Explorer, `mv`, or sync tools. MySQL manages metadata and storage files; manipulating the data directory directly can corrupt the instance or cause the data dictionary to no longer match the files on disk. Use DDL or supported dump/restore and migration procedures.

## 10. Replication and Multi-Server Environments

With replication, source and replica should use the same case-sensitivity rules for database/table names. If the source allows two tables `Customer` and `customer` while the replica treats them as the same name, replicated DDL or DML operations can collide.

When designing a MySQL topology, you should:

- Standardize database and table names before enabling replication.
- Check `@@GLOBAL.lower_case_table_names` on all involved nodes.
- Never create object names differing only by case on the source if a replica or target platform cannot represent those two names separately.
- Test DDL and restore procedures on a test replica before applying major changes.
- Keep rules consistent across development, testing, staging, and production environments.

Keeping the same configuration value does not solve every replication issue on its own, but it is an important condition for interpreting object names consistently. If an existing topology has mismatched configurations, evaluate and plan a dedicated migration rather than changing the variable on an active node.

## 11. Naming Conventions for Java Applications

Java applications commonly access databases through JDBC, JPA, or ORMs like Hibernate. Table name mappings may be declared explicitly or generated by a naming strategy. If code and DDL do not match in casing, errors may appear only when running on an environment with case-sensitive rules.

Example entity:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_profile")
public class CustomerProfile {
    @Id
    private Long id;

    private String fullName;
}
```

Corresponding DDL:

```sql
CREATE TABLE customer_profile (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL
);
```

In this example, the table name in both `@Table` and the DDL uses `customer_profile`. Apply this consistently across other entities, native queries, stored procedures, and migration scripts. If using an automatic naming strategy, verify the final SQL names emitted by the ORM via SQL logs or integration tests.

## 12. Checklist When Troubleshooting Case-Mismatch Errors

When encountering `Table doesn't exist` or `Unknown database` in only one environment, check in order:

1. Confirm the application is connecting to the right server and database using `SELECT @@hostname, DATABASE(), VERSION();`.
2. Read `SELECT @@GLOBAL.lower_case_table_names;` on that exact server.
3. Use `SHOW TABLES` or `INFORMATION_SCHEMA.TABLES` to inspect the actual object names.
4. Compare letter casing across DDL, migrations, ORM mappings, and executed SQL.
5. Determine the filesystem/`datadir` and whether the server environment is case-sensitive or case-insensitive.
6. Check whether two names differ only by case in the schema or in a dump.
7. If migration/replication is involved, compare configurations on both source and target before fixing.

Do not fix the issue by changing `lower_case_table_names` on an initialized instance or renaming files directly inside `datadir`. Standardize naming conventions, prepare a migration, and verify in a test environment.

## 13. Hands-On Exercises

1. Run `SELECT VERSION(), @@GLOBAL.lower_case_table_names;` on local MySQL and record the output.
2. Create schema `CaseLab` and table `Customer` in an isolated test environment.
3. Try querying the table using both matching and differing letter case; explain the results based on the `lower_case_table_names` value.
4. Inspect object names using `SHOW TABLES` and `INFORMATION_SCHEMA.TABLES`.
5. Compare table name casing in DDL with `@Table` or ORM mappings in a Java application.
6. Simulate a migration containing tables `Customer` and `customer`; identify why conflicts can occur when restoring into a case-insensitive environment.
7. Propose a database/table naming convention that works consistently across Windows, macOS, and Linux.

You have mastered this lesson when you can explain how the filesystem affects database/table names, distinguish the three `lower_case_table_names` values, inspect a server's configuration, and anticipate risks when migrating data. Using lowercase `snake_case` naming conventions and keeping configurations consistent across nodes prevents most case-related portability errors.
