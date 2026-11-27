# CREATE DATABASE, template databases, and choosing initialization attributes in PostgreSQL

When designing a system using PostgreSQL, tables and schemas are not the first layer of data organization. Before creating tables, we usually have to determine **which database will hold the data, which template that database is initialized from, what encoding and collation it uses, who owns it, which tablespace it defaults to, and what its connection policy is**.

PostgreSQL provides the `CREATE DATABASE` command to perform this task. An important characteristic of PostgreSQL is that a new database is typically **copied from a template database** rather than created completely from scratch. The two default templates `template0` and `template1` govern many behaviors that learners easily overlook.

For example, two databases that both hold UTF-8 data may sort strings differently due to collation choices; a database created from `template1` may inherit objects that were previously installed into the template; and a database with the right name and schema but wrong connection privileges will still prevent the application from accessing it.

This lesson guides you through creating PostgreSQL databases **deliberately, verifiably, and appropriately for the deployment environment**, from fundamental syntax to templates, initialization attributes, hands-on scenarios, common errors, and decisions that are hard to reverse once data has been loaded.

## 1. Distinguishing PostgreSQL cluster, database, schema, and table

To understand `CREATE DATABASE`, you need to know where a database sits in the PostgreSQL architecture.

~~~text
PostgreSQL cluster / instance
|
+-- Cluster-level shared objects
|     +-- Roles
|     +-- Tablespaces
|     +-- Information about databases
|
+-- Database: postgres
|     +-- Schema: public
|
+-- Database: template0
|     +-- Base template objects
|
+-- Database: template1
|     +-- Default base template objects
|
+-- Database: shop_dev
      |
      +-- Schema: public
      |     +-- Table: customer
      |     +-- Table: product
      |
      +-- Schema: sales
            +-- Table: orders
            +-- Table: order_item
~~~

Key points:

- **Cluster**, in traditional PostgreSQL terminology, is a collection of databases managed by a single PostgreSQL system with a data directory, not necessarily a multi-machine cluster.
- **Database** is a workspace with its own metadata, schemas, and objects.
- **Schema** is a namespace *inside a database*, helping group tables, views, functions, and related objects.
- **Table** stores business data rows inside a schema of a database.
- **Role** and **tablespace** are cluster-level objects, not created separately inside each database.

A standard PostgreSQL connection connects to **one specific database**. To operate on tables in another database, you cannot simply write three-part syntax like `other_database.public.table` in standard PostgreSQL SQL; you typically need a separate connection or a mechanism such as a foreign data wrapper/dblink if appropriate.

### 1.1. How does a database differ from a schema?

| Criterion | Database | Schema |
|---|---|---|
| How to create | `CREATE DATABASE` | `CREATE SCHEMA` |
| Scope | A database space within a cluster | Namespace inside a database |
| Connection | Client chooses the database when connecting | Client selects/qualifies the schema within the database |
| Default encoding and locale | Crucial decision when creating the database | Typically uses the database or object collation/settings |
| Management role | Database owner | Schema owner and object privileges |
| Querying across objects | Normally cannot directly JOIN across databases | Can JOIN tables across multiple schemas in the same database |
| Template | New database is copied from a template | Schemas do not use the database template mechanism |
| Logical backup | Can dump an entire database | Can dump/select one or more schemas within a database |

When an application needs transactional tables that are closely related, multiple schemas within **the same database** are usually convenient for joins and transactions. When you need to isolate database-level settings or operational lifecycles, multiple databases may be appropriate. This decision depends on architecture, not just naming.

## 2. What does CREATE DATABASE do?

The `CREATE DATABASE` command creates a new database in the PostgreSQL cluster, with the chosen name and attributes.

Minimal syntax:

~~~sql
CREATE DATABASE shop_dev;
~~~

This command asks the server to create a database named `shop_dev`, using the default template and attributes inherited or selected according to current rules.

Most standard PostgreSQL systems use **`template1` as the default template**. Therefore, objects and related settings already present in `template1` can affect the new database.

Example specifying additional attributes:

~~~sql
CREATE DATABASE shop_dev
WITH
    OWNER = shop_owner
    TEMPLATE = template0
    ENCODING = 'UTF8'
    LC_COLLATE = 'C'
    LC_CTYPE = 'C'
    CONNECTION LIMIT = 50;
~~~

The example assumes:

- The role `shop_owner` **already exists** and the executor has sufficient privileges to set the owner.
- The source PostgreSQL supports the options being used.
- `template0` has a configuration compatible with these encoding/locale choices.
- The database `shop_dev` does not yet exist.
- The command is executed **outside a transaction block**.

The following sections will explain why each choice matters.

### 2.1. There is no standard CREATE DATABASE IF NOT EXISTS command in PostgreSQL

Do not apply habits from other database management systems and write:

~~~sql
-- Invalid syntax in standard PostgreSQL:
-- CREATE DATABASE IF NOT EXISTS shop_dev;
~~~

If the database already exists, `CREATE DATABASE shop_dev` will raise a duplicate name error. We will look at how to check in a script using `psql` in a later section, as well as distinguish a pre-check from mechanisms for avoiding race conditions.

## 3. Privileges required to create a database

The user executing `CREATE DATABASE` must typically:

- Be a **superuser**, or
- Have the **`CREATEDB`** role attribute.

Example checking the current role's attributes:

~~~sql
SELECT
    current_user AS active_role,
    r.rolcreatedb,
    r.rolsuper
FROM pg_catalog.pg_roles AS r
WHERE r.rolname = current_user;
~~~

In a self-managed environment and with an appropriately privileged account, an administrator can create a dedicated role for creating databases:

~~~sql
-- Example for administrators in a test environment.
CREATE ROLE database_creator LOGIN CREATEDB;
~~~

This command does not configure a password or a specific authentication mechanism. In a real system, authentication, TLS, networking, and privilege grants must be configured according to policy. Do not store real passwords in public scripts.

**`CREATEDB` is not synonymous with `SUPERUSER`.** Someone with the privilege to create databases does not automatically have the right to modify all objects and sensitive information across the entire cluster.

### 3.1. Specifying OWNER

If `OWNER` is not specified, the owner of the new database is normally the role executing the command.

You can choose another owner:

~~~sql
CREATE DATABASE shop_test
WITH OWNER = shop_owner;
~~~

The role `shop_owner` must exist. The database creator must have appropriate privileges to assign that role as owner; in managed environments, role membership and privilege policies may be restricted.

The database owner can perform administrative operations within the scope of privileges PostgreSQL grants to an owner. However, **a database owner does not automatically own every table copied from a custom template**, and a database owner is not by default a cluster-wide superuser.

### 3.2. Managed PostgreSQL may restrict operations

On managed PostgreSQL services, the provided administrative account may **not be a true superuser**. Creating databases, choosing tablespaces, locale providers, connection limits, and using custom templates must follow the features and permissions allowed by the provider.

Do not attempt to edit system catalogs or modify server files to bypass restrictions. If you cannot create a database via SQL, check privileges, service policies, and supported provisioning methods.

## 4. Why does CREATE DATABASE require connecting to another database?

A PostgreSQL client must connect to an existing database in order to send SQL commands.

For example, to create `shop_dev`, you can connect to `postgres` — a utility database that usually exists for administrative work:

~~~bash
psql \
  -h 127.0.0.1 \
  -p 5432 \
  -U admin_user \
  -d postgres
~~~

After connecting:

~~~sql
SELECT current_database(), current_user;

CREATE DATABASE shop_dev;
~~~

After creation, the current session remains connected to the `postgres` database. To inspect schemas or create tables in the new database, you must open a connection to `shop_dev`.

In `psql`:

~~~text
\connect shop_dev
~~~

Or open a new session:

~~~bash
psql -h 127.0.0.1 -p 5432 -U admin_user -d shop_dev
~~~

You cannot use `USE shop_dev` in the syntax familiar from some other database engines. PostgreSQL selects the database at **connection establishment time**, and `psql` provides the `\connect` meta-command to reconnect.

## 5. CREATE DATABASE cannot run inside a transaction block

This is one of the most important practical rules.

**Invalid** example:

~~~sql
BEGIN;

CREATE DATABASE shop_dev;

COMMIT;
~~~

PostgreSQL will refuse to execute `CREATE DATABASE` inside a normal transaction block.

This affects:

- Migration frameworks that wrap every SQL file in a transaction by default.
- Scripts run with `psql --single-transaction`.
- PL/pgSQL `DO` blocks or functions trying to invoke `CREATE DATABASE` as dynamic SQL.
- Automation tools attempting to combine multiple provisioning steps into a single transaction.

### 5.1. Proper way to run with psql

From the terminal, connect to the administrative database and run the command standalone:

~~~bash
psql \
  -X \
  -v ON_ERROR_STOP=1 \
  -h 127.0.0.1 \
  -p 5432 \
  -U admin_user \
  -d postgres \
  -c "CREATE DATABASE shop_dev"
~~~

`-X` avoids reading personal `psql` startup configuration files, and `ON_ERROR_STOP=1` ensures orchestration scripts clearly receive errors.

**Do not use `--single-transaction` for the `CREATE DATABASE` command**. Once the database has been created, many DDLs inside the database such as `CREATE SCHEMA` and `CREATE TABLE` can be organized inside appropriate transactions.

### 5.2. Separating provisioning and migration

A deployment workflow might look like:

~~~text
[1] Provision role / database (outside transaction)
                    |
                    v
[2] Connect to new database
                    |
                    v
[3] Run schema migrations (in transaction where appropriate)
                    |
                    v
[4] Load seed / reference data
                    |
                    v
[5] Grant privileges and verify
~~~

These tasks should not be lumped into a single "run SQL once" step if they have different transactional and privilege requirements.

## 6. What is a template database?

A distinctive characteristic of PostgreSQL is that creating a new database is typically done by **copying an existing database**.

Illustration:

~~~text
PostgreSQL cluster
      |
      +-- template1
      |      |
      |      +---- CREATE DATABASE shop_dev;
      |                     |
      |                     v
      |                 shop_dev
      |
      +-- template0
             |
             +---- CREATE DATABASE audit_lab
                             TEMPLATE template0;
                           |
                           v
                        audit_lab
~~~

A template contains the objects and data inside the source database. PostgreSQL copies the appropriate structure to create the target database, rather than interpreting an empty SQL file in the manner of `pg_dump`/`pg_restore` each time.

There are three concepts:

- **`template1`:** the default template for many database creation commands.
- **`template0`:** a base template kept relatively untouched to support creating databases with different attributes, especially encoding and locale.
- **Custom template:** a database prepared by an administrator, which can be used as a copy source if conditions and privileges are met.

### 6.1. A template is not just a schema blueprint

A template database can contain tables, views, functions, extensions, seed data, and metadata for those objects. Creating a new database from a template can copy **many objects inside the database**, not just schema declarations.

If you only need to initialize a few tables for an application, using versioned migrations and seeds is usually easier to manage than modifying the cluster's default template.

## 7. template1: the default template

In a PostgreSQL cluster initialized through the standard process, `template1` is the default database used when creating a new database if no other `TEMPLATE` is specified.

For example:

~~~sql
CREATE DATABASE shop_dev;
~~~

is essentially equivalent to:

~~~sql
CREATE DATABASE shop_dev
WITH TEMPLATE template1;
~~~

Unless configured otherwise, the target database receives the appropriate objects, structures, and attributes from `template1`.

### 7.1. What happens if template1 is modified?

Suppose an administrator connects to `template1` and creates a table:

~~~sql
-- Illustrative example; do not run on a real template1 just to test.
-- CREATE TABLE public.platform_note (
--     note_id INTEGER PRIMARY KEY,
--     note_text TEXT NOT NULL
-- );
~~~

Any database subsequently created from `template1` may have the `platform_note` table from the start.

This can be useful in environments designed with a specific template, but it also introduces risks:

- All new databases receive unnecessary objects.
- Privileges and ownership of template objects may be inappropriate.
- Extensions or configurations added to the template make upgrades/backups more complex.
- Different environments have different `template1` contents, making database creation results inconsistent.
- Newcomers unaware that the template was modified find it hard to explain why a table appears on its own.

**Practical recommendation:** do not modify `template1` in shared environments just for exercise convenience or to add a few sample tables. If you need a custom template, create a separate database and manage it through a controlled process.

## 8. template0: the minimally modified base template

`template0` is intended to remain in a clean baseline state, suitable when you want to create a database with **an encoding or locale different from `template1`**, provided that combination of attributes is supported by PostgreSQL and the operating system.

Example:

~~~sql
CREATE DATABASE customer_search_lab
WITH
    TEMPLATE = template0
    ENCODING = 'UTF8'
    LC_COLLATE = 'C'
    LC_CTYPE = 'C';
~~~

The reason for choosing `template0` is not that it is "faster" or "better" for every application. The key point is being able to choose initialization settings that are incompatible with copying a template that already holds data/metadata tied to an older locale.

### 8.1. Why does PostgreSQL restrict changing encoding/locale when cloning?

If a template already has indexes or data organized according to character comparison rules, copying those structures and then declaring that the target database uses a different locale could lead to inconsistent results.

Therefore, PostgreSQL normally binds the choices of `ENCODING`, `LC_COLLATE`, and `LC_CTYPE` to the source template. `template0` is the path designed to allow selecting different values when supported.

**Do not attempt to edit catalog data to bypass template compatibility checks.**

### 8.2. Should you connect to and modify template0?

No. `template0` is maintained as a baseline point. In many clusters, it is configured to **disallow normal connections**, specifically to prevent unintended changes.

Do not turn `template0` into a practice database or a place to casually install extensions. To experiment, **create a new database from `template0`**.

## 9. Comparing template0, template1, and custom templates

| Attribute | template0 | template1 | Custom template |
|---|---|---|---|
| Role | Baseline template | Default template | Purpose-specific template |
| Used by default in CREATE DATABASE | No | Usually yes | Only when explicitly specified |
| Should be modified directly | No | Only with planned administration | Can be managed via controlled workflow |
| Choosing different encoding/locale | Primary choice when changes are needed | Usually constrained by template attributes | Depends on template compatibility |
| Can contain custom data/extensions | Should not | Possible, but requires caution | Can be proactively prepared |
| Objects copied | Base objects | Objects currently in template1 | Objects prepared in the template |
| Administrative risk | Corrupts clean baseline | Affects all subsequently created databases | Wrong owner, stale data, open sessions |

You do not need to create application databases from a custom template just to have a few configuration tables. In projects using Flyway/Liquibase or SQL migrations, creating an empty database and running migrations is generally easier to track over time.

## 10. The OWNER attribute: specifying the database owner

Example:

~~~sql
CREATE DATABASE shop_orders
WITH
    OWNER = shop_owner
    TEMPLATE = template0;
~~~

The **database owner** is a role with a certain administrative standing for that database. However:

- An owner is not automatically a superuser.
- Database owner and privileges on individual schemas/tables are distinct concepts.
- Objects copied from a custom template may still retain ownership from the template state.
- Applications should not use a broadly privileged owner account to handle routine queries.

A role design might include:

~~~text
database_admin  : provisioning and administration
shop_owner      : owns the database / team-managed schemas
shop_migrator   : executes controlled migrations
shop_app        : read/write privileges needed by the application
shop_readonly   : read-only access to granted tables
~~~

Specific roles and privilege inheritance must be designed according to PostgreSQL's `GRANT`/`REVOKE` rules, not merely based on naming.

### 10.1. Database owner does not equal schema owner

After connecting to the new database, you can inspect:

~~~sql
SELECT
    current_database(),
    current_user;

SELECT
    nspname,
    pg_catalog.pg_get_userbyid(nspowner) AS schema_owner
FROM pg_catalog.pg_namespace
WHERE nspname = 'public';
~~~

The owner of `public` and privileges on this schema may depend on the PostgreSQL version and how the database was initialized. **Do not assume every PostgreSQL instance has the same default grants on the `public` schema**; check the actual state and design privileges explicitly.

## 11. ENCODING: the database character encoding

**Encoding** defines how PostgreSQL encodes text characters in the database. In most modern applications with multilingual data, **UTF-8** is the common choice.

Example:

~~~sql
CREATE DATABASE shop_utf8
WITH
    TEMPLATE = template0
    ENCODING = 'UTF8';
~~~

You can check the currently connected database:

~~~sql
SHOW server_encoding;
SHOW client_encoding;
~~~

Two parameters to distinguish:

- `server_encoding`: the database encoding on the server side.
- `client_encoding`: how the client sends and receives text data; PostgreSQL can convert between client and server encodings when supported.

Example:

~~~sql
SELECT
    current_database() AS database_name,
    current_setting('server_encoding') AS database_encoding,
    current_setting('client_encoding') AS connection_encoding;
~~~

### 11.1. Why not pick an arbitrary encoding?

The encoding must be compatible with the locale and features being used. If a database is initialized with an encoding that does not support the characters an application needs to store, data insertion may fail or lose the ability to represent characters.

For example, Vietnamese data:

~~~text
Đà Nẵng
Nguyễn Ánh
Trường Sa
Cà phê
~~~

`UTF8` is suitable for representing these strings. However, getting the system to **sort** them properly according to language rules also requires choosing a collation; encoding and collation are two different concepts.

### 11.2. Can encoding be changed after the database is created?

Encoding cannot be treated as a parameter you can casually `ALTER DATABASE` once data exists. The standard safe migration path is to **create a target database with the desired encoding and then migrate the data using a supported method**, such as dump/restore or logical migration.

Do not alter the encoding value in the system catalog to "convert to UTF-8". Doing so does not convert the bytes of already stored data.

## 12. Locale: cultural and linguistic rules

Locale relates to linguistic and regional conventions, including:

- In what order strings are sorted.
- By which collation strings are compared.
- Character classification and certain character-processing behaviors.
- Compatibility with the operating system environment or ICU library.

In PostgreSQL, two traditional parameters commonly encountered are:

- **`LC_COLLATE`:** rules for sorting and comparing strings.
- **`LC_CTYPE`:** character classification and related behaviors.

Example with the `C` locale:

~~~sql
CREATE DATABASE shop_c
WITH
    TEMPLATE = template0
    ENCODING = 'UTF8'
    LC_COLLATE = 'C'
    LC_CTYPE = 'C';
~~~

`C` has simple byte-order comparison characteristics, often suitable for comparing technical identifiers, but is not considered natural linguistic sorting for Vietnamese or any specific human language.

### 12.1. Encoding does not determine sort order

Two databases that both have `ENCODING = 'UTF8'` can still return different orders when running:

~~~sql
SELECT ten
FROM danh_muc
ORDER BY ten;
~~~

because their collations may differ. Do not infer from "already using UTF-8" that the application will automatically sort people's names according to Vietnamese rules.

### 12.2. Are locales identical across all OSes?

No. With the `libc` provider, supported locale names and exact rules depend on the operating system and locale libraries. A locale name that exists on one machine may not be installed on another.

When writing database creation scripts with a specific locale choice, document the target environment and verify that the locale is actually supported. If deployment uses containers or managed services, do not assume you can install arbitrary locales on the underlying OS.

## 13. LOCALE_PROVIDER: libc and ICU

In PostgreSQL versions that support choosing the corresponding provider, a database can use different collation mechanisms. Two common providers are:

- **`libc`:** relies on the operating system library's locale rules.
- **`icu`:** uses International Components for Unicode (ICU) to handle collation according to Unicode rules and the selected locale.

Depending on the PostgreSQL version, additional providers or options may exist. **Always check the syntax of the server version in use**, rather than taking a single script and assuming it runs on every old/new PostgreSQL release.

### 13.1. Creating a database using libc

Example for a PostgreSQL version supporting `LOCALE_PROVIDER`:

~~~sql
CREATE DATABASE app_libc
WITH
    TEMPLATE = template0
    ENCODING = 'UTF8'
    LOCALE_PROVIDER = libc
    LC_COLLATE = 'C'
    LC_CTYPE = 'C';
~~~

With the `libc` provider, locale names and rules depend on the OS/libc. `C` is a simple and common choice, though not a natural linguistic ordering for every application.

### 13.2. Creating a database using ICU

Example on a PostgreSQL version built and configured with ICU support:

~~~sql
CREATE DATABASE app_icu
WITH
    TEMPLATE = template0
    ENCODING = 'UTF8'
    LOCALE_PROVIDER = icu
    ICU_LOCALE = 'vi-VN';
~~~

`ICU_LOCALE` is the locale tag used for the ICU provider. The locale name and level of support must match the current ICU/PostgreSQL version. Some versions include additional options to tune ICU or related attributes; do not assume all options exist on every server.

**The two SQL statements above are examples for two separate databases.** If a database named `app_libc` or `app_icu` already exists, `CREATE DATABASE` will report an error.

### 13.3. Does ICU automatically make every Vietnamese comparison "correct"?

There is no single "correct" definition for every kind of data.

For example:

- Person names may need linguistic ordering.
- Order codes need stable identifier comparison, which may differ from name search rules.
- A unique code may need case or diacritic sensitivity according to business rules.
- Fuzzy search and exact matching often have different requirements.

Test with real data before choosing a collation and designing `UNIQUE` constraints or related indexes.

### 13.4. Don't look only at the locale and forget the library version

Collation rules in ICU or libc can change when the library or OS is upgraded. This can affect string-sorted indexes and `ORDER BY`/`UNIQUE` behavior.

PostgreSQL has a metadata mechanism to track certain **collation versions**. If the library version changes, operational procedures may need to inspect and **REINDEX affected indexes** before updating the collation version metadata according to the corresponding guidelines.

A command like:

~~~sql
-- Only use when an appropriate process for handling collation changes is in place.
-- ALTER DATABASE app_icu REFRESH COLLATION VERSION;
~~~

mainly updates the recorded version metadata; **it does not automatically rebuild all necessary indexes**. Do not treat this as "collation fixed" without reviewing the impact on data and indexes.

## 14. Why must collation choices be decided early?

Suppose a user table has an identifier:

~~~sql
CREATE TABLE app_user (
    user_id BIGINT PRIMARY KEY,
    login_name TEXT NOT NULL UNIQUE
);
~~~

Comparison behavior for `login_name` and `UNIQUE` checks can depend on the collation of the column, expression, or index. If comparison rules change after the system already holds data, strings previously considered distinct might become equivalent, or sort order might change.

With diacritical data:

~~~text
Ánh
Anh
Đặng
dang
Đà Nẵng
da nang
~~~

you need to determine:

1. Which strings should be treated as duplicates during account registration?
2. Which language rules should govern name ordering?
3. Should searches be case-sensitive?
4. Under which collation were indexes created?
5. Do results need to be consistent across environments?

**Database-level locale is a foundational choice**, though PostgreSQL also allows specifying collations at the column or expression level as needed. Using one default collation does not prevent an application from designing different rules for special columns.

## 15. TABLESPACE: default storage location of the database

PostgreSQL supports **tablespaces** to map database object storage to managed physical locations.

By default, many databases are created in the `pg_default` tablespace. If a suitable tablespace already exists and the creator has privileges, you can select it:

~~~sql
CREATE DATABASE analytics_db
WITH
    TEMPLATE = template0
    TABLESPACE = fast_storage;
~~~

Here `fast_storage` is the name of a **pre-created** tablespace; it is not a directory automatically created inside the `CREATE DATABASE` command.

Verification:

~~~sql
SELECT
    d.datname,
    ts.spcname AS default_tablespace
FROM pg_catalog.pg_database AS d
JOIN pg_catalog.pg_tablespace AS ts
    ON ts.oid = d.dattablespace
WHERE d.datname = 'analytics_db';
~~~

### 15.1. A tablespace is a cluster-level object

You do not create a new tablespace inside the `analytics_db` database via `CREATE DATABASE`. Tablespace administration is a separate task, typically requiring high privileges, appropriate paths, and filesystem management. On managed PostgreSQL, privileges to create tablespaces or select filesystems may be restricted.

### 15.2. Database tablespace does not mean every object always resides there

An individual object can be created with its own tablespace when supported. Session configuration or subsequent DDL operations can also affect storage location. Thus, `TABLESPACE` at database creation determines the **initial default**, not a guarantee that all tables and indexes remain in one place forever.

### 15.3. Can tablespace be changed after creation?

PostgreSQL provides `ALTER DATABASE ... SET TABLESPACE` with operational conditions and restrictions, unlike attempting to change encoding/collation in place.

Moving a database can involve heavy I/O and require proper privileges and connection states. Do not run it just to experiment on production; plan capacity, backups, and downtime.

## 16. ALLOW_CONNECTIONS: whether connections to the database are allowed

The `ALLOW_CONNECTIONS` attribute determines whether the database accepts **new connections**.

Example:

~~~sql
CREATE DATABASE maintenance_template
WITH
    TEMPLATE = template0
    ALLOW_CONNECTIONS = false;
~~~

This database is still created, but it does not accept normal connections. Depending on the goal, this can be used to protect a template or isolate a database, but do not set `false` for an application database and then be surprised when connections fail.

### 16.1. Changing after creation

You can use syntax such as:

~~~sql
ALTER DATABASE maintenance_template
WITH ALLOW_CONNECTIONS = true;
~~~

Modification privileges and system state must be appropriate. Establishing a connection still depends on host/network, `pg_hba.conf` or network management mechanisms, roles, and the `CONNECT` privilege.

**ALLOW_CONNECTIONS = true does not mean anyone can log in.** It is only one of several conditions allowing a connection to be established.

## 17. CONNECTION LIMIT: limiting the number of connections

Example:

~~~sql
CREATE DATABASE batch_lab
WITH
    TEMPLATE = template0
    CONNECTION LIMIT = 20;
~~~

The `CONNECTION LIMIT` attribute sets a connection limit at the database level.

Points to understand:

- The default value typically uses `-1` to indicate **no separate database-level limit**.
- A positive value sets a limit enforced according to PostgreSQL's mechanism.
- This is not a replacement for `max_connections` at the server level.
- Certain connection types or roles with special privileges have exception rules; the limit is not an absolute barrier in every scenario.
- A database-level limit does not automatically allocate connection pools per application.

You can check:

~~~sql
SELECT
    datname,
    datconnlimit
FROM pg_catalog.pg_database
WHERE datname = 'batch_lab';
~~~

### 17.1. Why shouldn't the limit be set too low?

An application may have multiple pods/processes, each holding its own connection pool. If there are 10 application instances, each holding up to 10 connections, total demand can reach 100 connections even before admin tools, batch jobs, or metrics.

Setting `CONNECTION LIMIT = 20` without accounting for total clients can cause connection failures under load.

Conversely, allowing too many connections can also pressure server memory and resources. Sometimes it is advisable to use an appropriate connection pooler/proxy, optimize the application, and choose server limits intentionally.

## 18. IS_TEMPLATE: marking a database as a template source

You can create a custom database for reuse:

~~~sql
CREATE DATABASE training_template
WITH
    TEMPLATE = template0
    IS_TEMPLATE = true;
~~~

A database marked as a template can be copied by eligible roles according to PostgreSQL rules. **This is not an option to enable for every business database.**

If `IS_TEMPLATE` is false, the right to copy a database is not extended to every role with `CREATEDB`; the owner or superuser has specific rules governing this.

### 18.1. Why must custom templates be tightly managed?

A template containing existing data or objects can:

- Distribute demo data or faulty structures to many new databases.
- Carry inappropriate privileges and ownership.
- Introduce extension version discrepancies.
- Have unwanted dependencies.
- Be silently modified, making new databases non-reproducible.

Do not create a template containing real data or secrets and allow any role to clone it. Templates must also comply with data and access policies.

## 19. STRATEGY: how PostgreSQL copies a template

In PostgreSQL versions that support the `STRATEGY` option for `CREATE DATABASE`, two commonly mentioned strategies are:

- **`WAL_LOG`:** writes WAL records for copying data blocks according to the corresponding mechanism.
- **`FILE_COPY`:** copies files using a strategy that requires its own checkpoints to ensure recoverability.

Example on a supported version:

~~~sql
CREATE DATABASE reporting_test
WITH
    TEMPLATE = template0
    STRATEGY = WAL_LOG;
~~~

Or:

~~~sql
CREATE DATABASE reporting_copy
WITH
    TEMPLATE = template0
    STRATEGY = FILE_COPY;
~~~

Notes:

- `WAL_LOG` is often the default in versions providing this option, and can be suitable for databases/templates that are not overly large.
- `FILE_COPY` may reduce the amount of WAL written for large copies under certain conditions, but requires additional checkpoints and creates its own I/O and operational latency impact.
- Actual effectiveness depends on template size, storage speed, checkpoint configuration, and workload.
- Not all older PostgreSQL versions share the same syntax/options.

**Do not pick FILE_COPY simply because you heard "file copying is faster"**. Measure execution time, WAL volume, and cluster impact in a comparable environment if database creation is a frequent and large-scale operation.

## 20. Summary table of CREATE DATABASE attributes

| Attribute | Purpose | When to decide? |
|---|---|---|
| `OWNER` | Database owner | When provisioning roles and security model |
| `TEMPLATE` | Source database to copy | Before initializing structure/data |
| `ENCODING` | Database character encoding | **Before creation**, hard to change directly afterward |
| `LC_COLLATE` | Base sorting/comparison rules | **Before creation**, changing later requires migration/redesign |
| `LC_CTYPE` | Base character classification | **Before creation**, not an arbitrary custom GUC |
| `LOCALE_PROVIDER` | Locale/collation mechanism | Need to choose the right provider from the start |
| `ICU_LOCALE` | Locale when using ICU | Before creation; requires build support |
| `TABLESPACE` | Default tablespace | When choosing storage location; changing later has cost/limits |
| `ALLOW_CONNECTIONS` | Accept new connections | Can be adjusted during operations |
| `CONNECTION LIMIT` | Database connection limit | Can be adjusted based on demand |
| `IS_TEMPLATE` | Allow using database as template per rules | Enable only when intentionally creating a template |
| `STRATEGY` | Template copy strategy | Mainly matters for large or high-frequency clones |

Other options may appear depending on the version, such as collation metadata management or advanced ICU rules. **Do not put version-specific parameters into shared scripts without verifying the target server documentation.**

## 21. Lab 1: creating a UTF-8 database with locale C

Suppose you have a suitable PostgreSQL instance, the current role has `CREATEDB`, and you want to create a lab database to learn SQL. From the `postgres` database:

~~~sql
CREATE DATABASE shop_lab
WITH
    TEMPLATE = template0
    ENCODING = 'UTF8'
    LC_COLLATE = 'C'
    LC_CTYPE = 'C'
    CONNECTION LIMIT = 30;
~~~

**This is a new database creation operation**, not deleting an existing database. If `shop_lab` already exists, the command reports an error; do not automatically drop the database to rerun if it holds data you need to keep.

After creating it, switch connections in `psql`:

~~~text
\connect shop_lab
~~~

Verify:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS role_name,
    current_setting('server_encoding') AS encoding,
    current_setting('lc_collate') AS lc_collate,
    current_setting('lc_ctype') AS lc_ctype;
~~~

Next, try creating a table:

~~~sql
CREATE TABLE public.demo_product (
    product_id INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL UNIQUE,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0)
);

INSERT INTO public.demo_product
    (product_id, product_name, price)
VALUES
    (1, 'PostgreSQL Book', 185000.00),
    (2, 'Keyboard', 420000.00),
    (3, 'Mouse', 175000.00);

SELECT product_id, product_name, price
FROM public.demo_product
ORDER BY product_id;
~~~

This data belongs to **the `shop_lab` database**, not in `postgres` just because the initial session was connected to the `postgres` database.

### 21.1. Why not create tables before switching connections?

The command:

~~~sql
CREATE TABLE public.demo_product (...);
~~~

is processed inside the connection's current database. If you are still connected to `postgres`, the table will be created in `postgres.public` rather than automatically going into `shop_lab`.

In orchestration scripts, always know clearly **which database `-d` is pointing to**.

## 22. Lab 2: inspecting metadata in pg_database

`pg_database` is a cluster-wide system catalog storing information about databases.

You can inspect it:

~~~sql
SELECT
    oid,
    datname,
    pg_catalog.pg_encoding_to_char(encoding) AS encoding_name,
    datcollate,
    datctype,
    datistemplate,
    datallowconn,
    datconnlimit,
    pg_catalog.pg_get_userbyid(datdba) AS database_owner
FROM pg_catalog.pg_database
WHERE datname IN ('postgres', 'template0', 'template1', 'shop_lab')
ORDER BY datname;
~~~

Notable columns:

| Column | Meaning |
|---|---|
| `oid` | Internal OID of the database |
| `datname` | Database name |
| `datdba` | OID of the owning role |
| `encoding` | Encoding code |
| `datcollate` | Traditional locale/collation value |
| `datctype` | LC_CTYPE value |
| `datistemplate` | Whether the database is marked as a template |
| `datallowconn` | Whether new connections are accepted |
| `datconnlimit` | Database-level connection limit |
| `dattablespace` | OID of the default tablespace |

Some additional locale/provider or collation-version fields may differ across PostgreSQL versions; the query above uses a common baseline set of fields.

### 22.1. Checking the default tablespace

~~~sql
SELECT
    d.datname,
    t.spcname AS tablespace_name
FROM pg_catalog.pg_database AS d
JOIN pg_catalog.pg_tablespace AS t
    ON t.oid = d.dattablespace
WHERE d.datname = 'shop_lab';
~~~

This is an example of joining system catalogs by OID, rather than matching hardcoded tablespace names.

### 22.2. Checking database size

~~~sql
SELECT
    datname,
    pg_catalog.pg_size_pretty(
        pg_catalog.pg_database_size(oid)
    ) AS database_size
FROM pg_catalog.pg_database
WHERE datname = 'shop_lab';
~~~

Size values can vary across environments due to PostgreSQL version, metadata, objects, VACUUM, and storage factors. A new database does not necessarily have a size of 0 bytes.

## 23. Lab 3: creating a custom template

Suppose a training team wants to create multiple databases sharing the same lookup tables.

### 23.1. Create the template database

Connect to `postgres`, then create:

~~~sql
CREATE DATABASE training_seed
WITH
    TEMPLATE = template0
    ENCODING = 'UTF8'
    LC_COLLATE = 'C'
    LC_CTYPE = 'C';
~~~

### 23.2. Prepare objects inside the template

Switch the connection to `training_seed`:

~~~text
\connect training_seed
~~~

Create schema and data:

~~~sql
CREATE SCHEMA training;

CREATE TABLE training.status_code (
    status_code TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

INSERT INTO training.status_code
    (status_code, description)
VALUES
    ('NEW', 'Newly created'),
    ('DONE', 'Completed'),
    ('CANCELLED', 'Cancelled');
~~~

Verify:

~~~sql
SELECT status_code, description
FROM training.status_code
ORDER BY status_code;
~~~

### 23.3. Disconnect from the template and clone

Return to the administrative database:

~~~text
\connect postgres
~~~

Ensure **no other sessions are connected to `training_seed`** while cloning. Then:

~~~sql
CREATE DATABASE training_student_01
WITH TEMPLATE = training_seed;
~~~

Verify the new database:

~~~text
\connect training_student_01
~~~

~~~sql
SELECT status_code, description
FROM training.status_code
ORDER BY status_code;
~~~

The result will contain the three status codes from the source template.

### 23.4. Is IS_TEMPLATE = true required?

If the executor is the owner or has permission to clone that database, marking `training_seed` as a public template may not be necessary. The `IS_TEMPLATE = true` attribute affects which roles are allowed to use it as a template source according to PostgreSQL rules.

Enable it only when the design intentionally wants to share cloning capability with eligible `CREATEDB` roles. In shared environments, do not broaden clone permissions on databases containing data solely for convenience.

### 23.5. Cloning is not like versioned migrations

If you modify a table in `training_seed` after `training_student_01` has been created, the student database **does not automatically receive that change**. Each database is an independent copy at the moment of creation.

~~~text
training_seed -- cloned at t1 --> training_student_01
      |
      +-- changed at t2
                                   training_student_01
                                   does not change along
~~~

This is the difference between **template cloning** and **migrations applied to multiple existing databases**.

## 24. What if the template has active connections?

`CREATE DATABASE ... TEMPLATE = source_db` can be rejected when the source database has other connected sessions. PostgreSQL needs to ensure a suitable state for copying.

Example checking sessions on the template:

~~~sql
SELECT
    datname,
    COUNT(*) AS connection_count
FROM pg_catalog.pg_stat_activity
WHERE datname = 'training_seed'
GROUP BY datname;
~~~

A safe verification workflow:

1. Confirm the template is not a database with active users working in it.
2. Notify or coordinate stopping application sessions.
3. Ensure the clone command is executed from **a different database**.
4. Clone only once the source is stable.

Do not automatically call `pg_terminate_backend` on production just to make a clone command succeed. Terminating sessions can disrupt transactions and other tasks.

### 24.1. Why shouldn't a production database be used as a template?

It can introduce multiple risks:

- Production always has many connections, making cloning unfeasible or disruptive.
- Real data may be copied to less secure environments.
- Large databases require heavy I/O and storage space to clone.
- Objects containing secrets or sensitive data may be copied.
- Ownership, extensions, and configurations in the clone may be inappropriate.

To spin up staging, prioritize a backup/restore or data masking pipeline designed for that purpose, rather than arbitrarily cloning a production database directly.

## 25. Creating a database with createdb

PostgreSQL provides the `createdb` command-line utility, which is essentially a client sending a database creation request to the server.

Example:

~~~bash
createdb \
  -h 127.0.0.1 \
  -p 5432 \
  -U admin_user \
  -O shop_owner \
  -T template0 \
  -E UTF8 \
  -l C \
  shop_cli
~~~

Explanation:

- `-h` and `-p` specify host/port.
- `-U` specifies the connecting role.
- `-O` specifies the owner, if permitted.
- `-T` specifies the template.
- `-E` specifies the encoding.
- `-l` specifies the locale as supported by the utility.
- `shop_cli` is the name of the new database.

The syntax and set of options for `createdb` depend on the client version, so check:

~~~bash
createdb --help
~~~

When needing to select an ICU provider or newer parameters, consult `CREATE DATABASE` and the capabilities of the specific client/version. Do not assume an overly old `createdb` supports every option of a newer server.

### 25.1. Benefits of createdb in scripts

`createdb` can be well suited for shell provisioning or automation. However, it does not replace server privileges, does not automatically create the owner role, and does not automatically handle already-existing databases for idempotency unless the script is designed to do so.

In CI, check the **exit code** to prevent migration steps from running on a database that failed to be created.

## 26. Conditional database creation in psql scripts

PostgreSQL does not provide standard `CREATE DATABASE IF NOT EXISTS` syntax. In `psql`, there is the `\gexec` meta-command to execute SQL generated by a query.

Example on **an administrative database**, intended only for controlled provisioning workflows:

~~~sql
SELECT format(
    'CREATE DATABASE %I WITH TEMPLATE template0 ENCODING %L',
    'ci_lab_01',
    'UTF8'
)
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_database
    WHERE datname = 'ci_lab_01'
)
\gexec
~~~

Explanation:

- `WHERE NOT EXISTS` checks whether the database already exists.
- `format('%I', ...)` quotes identifiers such as the database name appropriately.
- `format('%L', ...)` quotes literals such as the encoding string.
- `\gexec` is a **psql meta-command** that executes the SQL statement produced by the preceding query.
- Execution of `CREATE DATABASE` happens outside a normal transaction block; do not use `psql --single-transaction`.

**Important limitation:** this is a check-then-execute pattern, **not an atomic create-if-not-exists operation**. If two processes check and create the database concurrently, one process can still encounter a duplicate name error. Automation must handle errors like `duplicate_database` when running concurrently, or coordinate concurrency at the orchestration layer.

Do not pass `\gexec` into JDBC as ordinary SQL: the server does not understand `psql` meta-commands.

## 27. CONNECT and TEMPORARY privileges after CREATE DATABASE

A newly created database does not mean every role has permission to operate on tables, though you must pay special attention to **default privileges at the database level**.

In PostgreSQL, `CONNECT` and `TEMPORARY`/`TEMP` privileges on a database are normally granted to `PUBLIC` by default, unless another policy is in place. `PUBLIC` is a privilege group encompassing all roles, not an individual user.

This **does not guarantee anyone can connect**, because authentication, host/network, and other conditions still apply. However, if you want a model where **only designated roles can connect**, you must explicitly manage grants/revokes.

Example in an environment where role `shop_app` already exists:

~~~sql
REVOKE CONNECT ON DATABASE shop_lab FROM PUBLIC;

GRANT CONNECT ON DATABASE shop_lab TO shop_app;
~~~

You can check privileges:

~~~sql
SELECT
    pg_catalog.has_database_privilege(
        'shop_app',
        'shop_lab',
        'CONNECT'
    ) AS app_can_connect;
~~~

### 27.1. CONNECT does not equal table read privilege

Even when role `shop_app` has `CONNECT`, it still needs:

- `USAGE` on the schema to access objects inside it.
- `SELECT`, `INSERT`, `UPDATE`, `DELETE` on the appropriate tables.
- Sequence or function privileges when used by the application.
- Other privileges according to the data model.

Example inside database `shop_lab`:

~~~sql
-- Only when the schema and role already exist.
GRANT USAGE ON SCHEMA public TO shop_app;
GRANT SELECT ON TABLE public.demo_product TO shop_app;
~~~

Do not grant `ALL PRIVILEGES` on all objects to an application just to quickly test a connection.

### 27.2. REVOKE is not a session termination tool

Revoking `CONNECT` affects the ability to establish new connections under privilege rules; it should not be treated as a reliable way to immediately terminate all existing sessions. To disconnect applications during maintenance, a separate coordination process is required.

## 28. Customizing database-level defaults after creation

In addition to initialization attributes, PostgreSQL can store certain **per-database default session configurations** using `ALTER DATABASE ... SET`.

Example:

~~~sql
ALTER DATABASE shop_lab
SET statement_timeout = '15s';

ALTER DATABASE shop_lab
SET idle_in_transaction_session_timeout = '60s';
~~~

These settings are applied according to configuration rules when a session connects, and may be overridden by role configurations or session-level `SET`.

Do not confuse these settings with **the database's base encoding/collation**:

- `statement_timeout` is a parameter managing query execution behavior.
- `idle_in_transaction_session_timeout` limits the time spent idle in a transaction.
- `ENCODING`, `LC_COLLATE`, and `LC_CTYPE` are foundational choices tied to how the database was initialized, and cannot be treated as GUCs that can be freely changed.

### 28.1. Does ALTER DATABASE SET affect already-open sessions?

Normally, a change to database-level defaults should be evaluated for **new connections**, rather than assuming it immediately modifies every running session. When verification is needed, open a new connection and run:

~~~sql
SHOW statement_timeout;
SHOW idle_in_transaction_session_timeout;
~~~

For applications using connection pools, default changes may not take effect until connections are recreated or session configurations are intentionally adjusted.

## 29. Attributes that can be changed vs. hard to change after creation

| Attribute | Adjustable after creation? | Operational notes |
|---|---|---|
| Database name | Has `ALTER DATABASE ... RENAME TO` path | Must handle sessions, endpoints/connection strings, and privileges |
| Owner | Has `ALTER DATABASE ... OWNER TO` subject to privileges | Does not automatically change owner of all objects inside |
| Connection limit | Adjustable via `ALTER DATABASE` | Must evaluate load and connection pools |
| Allow connections | Adjustable via `ALTER DATABASE` | Easy to lock yourself out if chosen wrongly |
| Is template | Modifiable under supported privileges | Can expand cloning privileges |
| Tablespace | Has relocation mechanism with restrictions | I/O intensive and requires connection control |
| Session defaults | Has `ALTER DATABASE ... SET/RESET` | Normally affects new sessions |
| Encoding | Cannot be changed in place like a normal variable | Usually requires creating a new database and migrating data |
| Base Locale/Collation | Cannot be treated as a freely changeable variable | Requires migration strategy and appropriate indexing |
| Source template used | No "live link" to change | Created database is an independent copy |
| Initial copy strategy | Applies only at CREATE time | Meaningless to change for an existing database |

**Lock in the hard-to-change factors — encoding, locale provider, and collation — before loading large volumes of business data.**

## 30. What if you need to change locale/encoding after data exists?

A common approach is to **create a new target database with the desired attributes, then logically migrate the data** using appropriate tools and procedures.

Example workflow outline:

~~~text
Source database: shop_old
      |
      | Restorable backup + establish data cutoff point
      v
Supported logical dump / migration
      |
      v
CREATE DATABASE shop_new
  TEMPLATE template0
  ENCODING UTF8
  new locale/provider
      |
      v
Restore schema + data
      |
      v
Rebuild indexes / verify UNIQUE / foreign keys
      |
      v
Compare data and test application
      |
      v
Coordinate writes + cutover per runbook
~~~

A conceptual example:

~~~bash
pg_dump \
  -h old-db.example \
  -U backup_user \
  -d shop_old \
  -F c \
  -f shop_old.dump
~~~

Create the target database via an administrative connection:

~~~sql
CREATE DATABASE shop_new
WITH
    TEMPLATE = template0
    ENCODING = 'UTF8'
    LC_COLLATE = 'C'
    LC_CTYPE = 'C';
~~~

Load using an appropriate tool:

~~~bash
pg_restore \
  -h new-db.example \
  -U restore_user \
  -d shop_new \
  shop_old.dump
~~~

**This is not yet a complete production runbook.** You must handle roles/global objects, extensions, ownership, grants, connections, syncing transactions occurring between dump and cutover, collation changes, UNIQUE checks, indexes, and rollback capability.

When collation rules change, values previously considered unique may be evaluated differently. Do not assume restoring all indexes/constraints will succeed without checking the data under the target collation.

## 31. Differences between database templates and backups

They share a similarity in that both can help produce an environment with schemas/data, but their purposes differ:

| Criterion | Database template | Backup/restore |
|---|---|---|
| Goal | Initialize a new database from an existing blueprint | Recover data at a protected point in time |
| Source | A database within the cluster | Dump files, base backups, WAL, system backups |
| Context | Typically within the same PostgreSQL cluster | Can transfer across machines/clusters via supported methods |
| Real data | Should not be placed casually in shared templates | May contain real data; requires security |
| Lifecycle | Used for rapid provisioning of multiple databases | Used for disaster recovery/PITR, migration |
| Privileges | Depends on template clone privileges | Depends on backup/restore privileges |
| When source changes | Already-cloned databases do not auto-update | Backups represent specific points in time |

**Templates do not replace backups.** If production order data is lost, copying `template1` cannot recover recorded business data.

Conversely, production backups should not be used as an open learning template for everyone due to data exposure risks and large sizes.

## 32. Costs and resources when creating databases from templates

`CREATE DATABASE` is not a "free" operation in all cases. When a template contains large amounts of data, creating a copy can consume:

- Disk I/O.
- CPU and file-management resources.
- WAL or checkpoints depending on strategy.
- Storage capacity for the new database.
- Time holding an appropriate state for cloning.
- Storage throughput and time needed for concurrent operations.

A template holding hundreds of GiB of data should not be multiplied into numerous test databases without accounting for disk space and bandwidth.

For simple training environments, a blueprint with few tables/seeds or an empty-database + migration workflow can be lighter than cloning a large database.

## 33. Inspecting and managing databases with psql

Some useful meta-commands:

~~~text
\l              -- List databases
\l+             -- More detailed database information
\conninfo       -- Current connection information
\connect shop_lab
\dn             -- List schemas in the current database
\dt             -- List tables according to object search rules
\q              -- Quit
~~~

Strings starting with `\` are **psql meta-commands**, not SQL to be sent directly from JDBC.

With pure SQL:

~~~sql
SELECT
    current_database(),
    current_user,
    current_setting('server_encoding'),
    current_setting('lc_collate'),
    current_setting('lc_ctype');
~~~

You can view the list of databases from any database in the same cluster if you have catalog read privileges:

~~~sql
SELECT datname
FROM pg_catalog.pg_database
ORDER BY datname;
~~~

However, to view table data in the `shop_lab` database, you need to connect to that exact database.

## 34. Common errors with CREATE DATABASE

### Error 1 — Permission denied to create database

Common cause: the role lacks `CREATEDB` or sufficient privileges under the system's management mechanism.

**How to handle:** check `rolcreatedb`, `rolsuper`, and provider policies. Ask an administrator to grant appropriate privileges; do not attempt to alter system catalogs.

### Error 2 — CREATE DATABASE cannot run inside a transaction block

The command is inside `BEGIN ... COMMIT`, `psql --single-transaction`, or a transaction created by a migration framework.

**How to handle:** run `CREATE DATABASE` separately outside any transaction. Run schema migrations after opening a connection to the target database.

### Error 3 — Database already exists

The database was already created by a previous run or another process.

**How to handle:** inspect `pg_database`, accurately verify the environment and provisioning idempotency; do not `DROP DATABASE` just to clear the error.

### Error 4 — Cannot find the new database in the current session

`CREATE DATABASE` creates the database but does not automatically switch the connection.

**How to handle:** use `\connect` in `psql` or open a new connection with the appropriate `-d`.

### Error 5 — Encoding or locale incompatible with template

Commonly happens when trying to create a database with an encoding/locale different from `template1`.

**How to handle:** check server compatibility and use `TEMPLATE template0` when appropriate. Do not ignore the error or edit catalogs directly.

### Error 6 — Locale does not exist in the environment

A locale is installed on a laptop but missing on the PostgreSQL server's OS.

**How to handle:** confirm the locale is genuinely supported by the server. If using a managed service, choose from the capabilities offered by the provider.

### Error 7 — ICU is not supported

The target PostgreSQL version or build may lack the required ICU/provider support.

**How to handle:** check the version, build, and provider documentation; do not use ICU configurations when the platform does not support them.

### Error 8 — Multiple sessions connected to the source template

PostgreSQL needs to clone from a source in an appropriate state; active sessions using the source can block it.

**How to handle:** pick an appropriate window, cleanly close connections in a controlled manner, and run the clone from another database. Do not forcefully terminate all sessions on production.

### Error 9 — Accidentally picking a customized template1

New databases have extensions or tables "appearing on their own".

**How to handle:** inspect the source template and metadata; use `template0` alongside migrations if you want a stable baseline state.

### Error 10 — Treating OWNER as cluster-wide read access

A database owner does not automatically have all privileges across objects or the cluster.

**How to handle:** explicitly design roles, schema owners, and object grants.

### Error 11 — ALLOW_CONNECTIONS = false on an application database

The application is denied connections even though host and role are correct.

**How to handle:** check `datallowconn`; update the attribute with appropriate privileges, from an administrative database if necessary.

### Error 12 — CONNECTION LIMIT too low

Connection pools or multiple application instances exceed the limit.

**How to handle:** calculate total demand, review `max_connections`, proxies/pools, and administrative connections; set the limit deliberately.

### Error 13 — Forgetting to check PUBLIC CONNECT

The database may be allowing unintended roles to attempt opening connections by default.

**How to handle:** manage `GRANT`/`REVOKE` alongside network/auth policies; check `has_database_privilege`.

### Error 14 — Assuming UTF8 guarantees proper Vietnamese search

Encoding and collation are two separate decisions.

**How to handle:** design collations tailored to specific search, sorting, and unique key requirements.

### Error 15 — Changing collation provider and ignoring indexes

If the collation library changes, affected indexes may need to be rebuilt.

**How to handle:** track collation versions, assess impact, and run REINDEX following procedures; do not merely refresh metadata.

### Error 16 — Cloning a production database as a test environment

This can cause heavy load, data leaks, and session conflicts.

**How to handle:** use a designed backup/restore or data masking pipeline, or templates free of sensitive information.

### Error 17 — Naming a database with uppercase letters and forgetting quotes

Unquoted identifiers are folded to lowercase by PostgreSQL parser rules. Quoted uppercase names can complicate operations.

**How to handle:** prefer lowercase `snake_case` names without spaces that do not require quoting.

### Error 18 — Using DROP DATABASE to "rerun cleanly"

`DROP DATABASE` deletes the database and all data inside it, which is dangerous if aimed at production or a shared environment by mistake.

**How to handle:** only use approved reset procedures on temporary databases, verify endpoint/role/name, and back up when needed; avoid unconditional automated drop commands.

## 35. Choosing attributes for different scenarios

### 35.1. A small database for practicing SQL

Requirements: isolated, easy to create, disposable, supports Vietnamese text.

A suitable choice might be:

~~~sql
CREATE DATABASE learning_pg
WITH
    TEMPLATE = template0
    ENCODING = 'UTF8'
    LC_COLLATE = 'C'
    LC_CTYPE = 'C';
~~~

Suitable for a lab needing simple byte ordering; if exercises require Vietnamese name sorting, select an appropriate locale/collation and test it.

### 35.2. Application database with dedicated accounts

Requirements: separate provisioning/migration privileges from application runtime privileges.

Plan to:

1. Create owner/migrator/app roles via administrative mechanisms.
2. Select an appropriate template and encoding/locale.
3. Create the database with an intentional `OWNER`.
4. Manage `CONNECT`/`TEMP` and schema/object grants.
5. Run migrations with the appropriate role.
6. Run the application with least privilege.
7. Set up backups, monitoring, and connection pooling.

Do not use the owner or superuser as the default account for every application request.

### 35.3. Database for language-specific search

Requirements: sort names according to specific linguistic rules.

You should:

- Identify supported locale providers.
- Test datasets with diacritics, mixed case, and pairs of strings prone to collision.
- Inspect the impact on `ORDER BY`, `UNIQUE`, and indexes.
- Pin environment versions and establish a procedure for handling collation versions during system upgrades.
- Consider per-column collations when different data types have different rules.

### 35.4. Database sharing a common structure for many students

If you frequently create databases with the same lookup tables, you can create a small custom template free of sensitive info and persistent connections.

If the schema changes continuously, versioned migration scripts/seeds may be easier to manage than a manually edited template.

### 35.5. Large analytical database

Besides encoding and locale, evaluate:

- Storage capacity and tablespaces.
- Template copy speed, WAL, and checkpoints.
- Connection limits.
- Backup/restore capabilities.
- Privileges and target environment.
- Storage costs when creating multiple copies.

Do not choose `STRATEGY` or `TABLESPACE` without understanding their operational impact.

## 36. Recommended complete provisioning workflow

A reliable PostgreSQL database creation workflow should follow these steps:

**Step 1 — Verify the cluster and administrative database.** Check host, port, server version, environment, and role before acting.

**Step 2 — Verify privileges.** Does the role have `CREATEDB`, owner assignment rights, and appropriate tablespace privileges?

**Step 3 — Choose the database name.** Use a stable, environment-clear name; avoid colliding with production and avoid names requiring quotes.

**Step 4 — Choose the template.** `template0` if needing a clean baseline/different locale attributes; `template1` if defaults are acceptable; custom template only with a clear requirement.

**Step 5 — Lock in encoding and locale.** Especially critical for Unicode, string comparisons, and multilingual data.

**Step 6 — Choose owner, tablespace, and connection policy.** Do not wait until the application goes live to discover wrong privileges or insufficient resources.

**Step 7 — Run CREATE DATABASE separately outside a transaction.** Use `psql -c` or `createdb`, and check the exit code.

**Step 8 — Verify metadata in pg_database.** Read encoding, locale, owner, tablespace, connection limit, and flags.

**Step 9 — Connect to the new database.** Run `SELECT current_database()` before running migrations.

**Step 10 — Configure SQL privileges.** Manage CONNECT and schema/table/sequence grants per the design.

**Step 11 — Run schema migrations and appropriate seeds.** Keep versioned change history instead of silently modifying templates.

**Step 12 — Test connections, data, collation, and transactions.** Include application drivers, Vietnamese text, indexes, and critical queries.

**Step 13 — Enable and test recoverability.** A new database also needs backups/PITR and monitoring aligned with system objectives.

**Step 14 — Document initialization decisions.** Record template, encoding, locale provider, PostgreSQL version, owner, grants, and scripts so subsequent deployments are reproducible.

## 37. Self-practice exercises

### Exercise 1 — Database and schema

Distinguish the `shop_dev` database from the `sales` schema inside `shop_dev`. When should you use multiple schemas in one database instead of creating multiple databases?

**Hint:** tables needing JOINs and transactions within the same database generally belong in multiple schemas; databases separate at the connection and initialization attribute level.

### Exercise 2 — Default template

Which template does the command:

~~~sql
CREATE DATABASE test_a;
~~~

usually use? Why can a table already created in the default template appear in the new database?

**Hint:** usually `template1`. PostgreSQL copies the template's contents.

### Exercise 3 — Encoding and template0

You need a UTF-8 database with `LC_COLLATE = 'C'`, different from the locale of `template1`. Which template should you choose and why?

**Hint:** `template0` is designed for creating databases with different initialization attributes when supported.

### Exercise 4 — How to run CREATE DATABASE

Why is the following snippet invalid?

~~~sql
BEGIN;
CREATE DATABASE test_a;
COMMIT;
~~~

**Hint:** `CREATE DATABASE` cannot run inside a normal transaction block.

### Exercise 5 — Database created but table not found

You are connected to `postgres`, run `CREATE DATABASE shop_b;`, and then create table `public.customer`. Which database does the table belong to?

**Hint:** the session remains connected to `postgres` unless switched via `\connect` or a new client connection.

### Exercise 6 — CREATEDB privilege and OWNER

Is a role with the `CREATEDB` attribute automatically a superuser? Should an application account use the owner role to handle all requests?

**Hint:** no. Provisioning, migration, and runtime roles should be separated following least privilege.

### Exercise 7 — UTF8 and Vietnamese sort order

Can two databases both using UTF-8 return different `ORDER BY ten` sort orders?

**Hint:** yes, if their locales/collations differ; encoding does not determine the entire sort order.

### Exercise 8 — ICU and libc

Describe one operational difference between the `icu` and `libc` providers. When upgrading the OS/ICU, what issue should be checked?

**Hint:** locale rules depend on provider and version; indexes on strings may need REINDEX if collation changes.

### Exercise 9 — CONNECTION LIMIT

An application has eight instances, each holding a pool of 10 connections. What issue can setting a database limit of 30 cause?

**Hint:** peak demand can exceed the limit; batch jobs and admin connections must also be accounted for.

### Exercise 10 — CONNECT privilege

A role has `CONNECT` privilege on a database, yet `SELECT` is denied. Is this a PostgreSQL bug?

**Hint:** no. Database, schema, and table privileges are separate layers.

### Exercise 11 — Custom template

Create `training_seed` with one table and three rows, then clone `training_student_01`. Afterward, modify data in `training_seed` — does the student database's data automatically change?

**Hint:** no. A cloned database is an independent copy.

### Exercise 12 — Multiple sessions on template

Why can cloning a source database that has persistent active connections fail? What should be done beforehand?

**Hint:** PostgreSQL requires an appropriate state to copy; use a stable source without other sessions.

### Exercise 13 — pg_database

Write SQL to list the name, encoding, owner, `datallowconn`, and `datconnlimit` of databases.

**Hint:** `pg_database`, `pg_encoding_to_char(encoding)`, and `pg_get_userbyid(datdba)`.

### Exercise 14 — Using createdb

Write a terminal command to create database `test_cli` from `template0` with UTF-8 and locale C.

**Hint:** use the `-T template0`, `-E UTF8`, `-l C` options of `createdb` on a supported version.

### Exercise 15 — IF NOT EXISTS

Why is using `SELECT NOT EXISTS ... \gexec` insufficient to guarantee that two CI jobs creating the same database will never collide?

**Hint:** there is a race between checking and creating; concurrency coordination or duplicate-name error handling is needed.

### Exercise 16 — STRATEGY

Distinguish the idea of `WAL_LOG` and `FILE_COPY` when creating a database from a large template.

**Hint:** the two strategies have different WAL, checkpoint, and I/O costs; use on a supported version and measure in practice.

### Exercise 17 — Changing locale after data exists

Why should you not edit the catalog to switch a database from an old collation to another collation?

**Hint:** indexes and data comparison rules may become inconsistent; migration/restore and data verification are required.

### Exercise 18 — Backup and template

A team says "we already have template1 so we don't need to back up the production database". How do you explain why this is wrong?

**Hint:** templates do not hold production transaction history; backups and PITR exist to recover real data at points in time.

### Exercise 19 — TABLESPACE

When running `CREATE DATABASE analytics WITH TABLESPACE fast_storage`, are all tables created later permanently forced onto fast_storage?

**Hint:** no. That is the default; objects can have their own tablespaces or be affected by appropriate configuration/DDL changes.

### Exercise 20 — Design scenario

An application serving Vietnamese customers requires UTF-8 data, name searching and sorting according to appropriate rules, least-privilege runtime access, and CI frequently creating new databases. Propose steps for selecting initialization attributes and testing before production.

**Hint:** lock in provider/collation after testing diacritical data, choose a stable template, separate owner/migrator/app roles, automate non-transactional provisioning, verify pg_database, and test backup/restore.

## 38. Key takeaways

- **`CREATE DATABASE`** creates a new database in the PostgreSQL cluster and **does not automatically switch the session** to that database.
- A database differs from a schema: each database is a separate connection and metadata space, while a schema is a namespace inside a database.
- The creator usually needs **`CREATEDB` or superuser**; specifying `OWNER` also depends on privileges over the owner role.
- **`CREATE DATABASE` does not run inside a transaction block**; separate database provisioning from in-database migrations.
- New databases are normally **copied from `template1`**; `template0` is the baseline template used when different encoding/locale choices are needed within supported bounds.
- **Do not modify template0** and do not modify template1 casually; custom templates require managing privileges, data, and lifecycles.
- **`ENCODING` and `LC_COLLATE`/`LC_CTYPE` are different**: encoding determines character representation, while collation affects sorting and comparison.
- **`LOCALE_PROVIDER`** and `ICU_LOCALE` must be chosen according to PostgreSQL version, environment, and business rules; later collation changes can affect indexes.
- **`TABLESPACE`** sets default storage, **`CONNECTION LIMIT`** caps database-level connections, **`ALLOW_CONNECTIONS`** toggles new connection acceptance, and **`IS_TEMPLATE`** governs using the database as a template.
- **`STRATEGY`** selects how a template is copied on supported versions, not a default trick to speed up every workload.
- **`pg_database`** provides metadata to inspect owner, encoding, locale, flags, and tablespace.
- **`CONNECT` is not equivalent to table privileges**; separate grants must be designed for schemas and objects.
- Attributes that are **hard to change after creation** — especially encoding and base locale/collation — should be determined through testing before loading real data.
- **Templates are not backups**; production applications still require backup, recovery, and data reconciliation processes.

Creating a good PostgreSQL database means choosing **a durable data foundation for the application**, not merely allocating a name. By understanding template databases and initialization attributes, you can proactively ensure environments are provisioned consistently, data is represented accurately, privileges are granted properly, and hard-to-reverse decisions do not become incidents as the system grows.
