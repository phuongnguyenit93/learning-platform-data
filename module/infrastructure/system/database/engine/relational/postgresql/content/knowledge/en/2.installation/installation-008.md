# Loading a Reproducible Sample Dataset in PostgreSQL

A PostgreSQL learning environment is most useful when everyone can **reload the exact same dataset, run the exact same queries, and get consistent results**. If each person manually inserts a few rows, uses current timestamps, or relies on uncontrolled random data, it becomes difficult to compare exercises, write automated tests, and diagnose why a SQL query behaves differently across machines.

This lesson guides you through creating and loading a **seed dataset**—a reproducible sample dataset—in PostgreSQL. You will create an isolated practice environment, build tables with foreign-key relationships, save the seed as a UTF-8 SQL file, load it via `psql` inside a single transaction, verify results, re-run it repeatedly without duplicating rows, scale the dataset with `generate_series`, and organize seeds for teams or CI.

**Goals after this lesson:**

- Distinguish seed data, migrations, and backups.
- Create a dedicated database or schema for practice without affecting real data.
- Maintain a SQL seed file containing **fixed IDs, timestamps, and deterministic generation rules**.
- Load with `psql`, catch errors, and roll back the entire load when needed.
- Understand two reproducibility strategies: **full test environment reset** and **idempotent incremental loading**.
- Generate thousands of additional rows using repeatable formulas.
- Verify row counts, foreign keys, order totals, and key data properties.

Examples use standard modern PostgreSQL syntax. Run them on a **disposable learning database or CI environment**; never run the schema-reset portion in production.

## 1. What Does "Reproducible" Mean?

A reproducible sample dataset has these properties:

1. **Same input, same target state:** running the workflow from an empty database produces identical tables and sample values.
2. **No manual clicking:** no need to click through GUI admin tools row by row to add data.
3. **Clear relational ordering:** parent records are created before child records, avoiding foreign-key violations.
4. **Fixed key values:** IDs, monetary amounts, statuses, and timestamps do not change depending on the day the script runs.
5. **Defined re-run behavior:** either reset the test environment or use UPSERT/checks to avoid duplicating records.
6. **Built-in verification:** missing rows or incorrect values are detected automatically.

For example, a JOIN exercise requires exactly four customers, four products, and four orders. If every seed run generated orders with `now()` or quantities with uncontrolled `random()`, report outputs would drift, making the exercise hard to evaluate.

A deterministic seed for sample data typically uses:

~~~text
customer_id: 1, 2, 3, 4
product_id : 101, 102, 103, 104
order_id   : 1001, 1002, 1003, 1004
time       : fixed TIMESTAMPTZ values with +00
price      : NUMERIC, avoid approximate floats for money
~~~

**Reproducible data does not mean query results are automatically ordered.** When checking row order, always use `ORDER BY`.

## 2. How Do Seeds Differ from Migrations, Fixtures, and Backups?

| Concept | Role | Example |
|---|---|---|
| **Schema migration** | Version-controlled structural database changes | `CREATE TABLE`, `ALTER TABLE`, index creation |
| **Seed data** | Deterministic initial dataset | Customer A, Product B, Order C |
| **Test fixture** | Data tailored for a specific test case | A cancelled order to test reporting filters |
| **Backup** | Snapshot of real data for recovery | `pg_dump`, base backup + WAL |
| **Data generator** | Synthesizes bulk data by rule | `generate_series(1, 100000)` |

In this lesson, a single SQL file both creates the practice schema and inserts data for standalone execution. In real projects, **migrations** are usually separated from **seeds**: migrations version structural schema changes, while seeds populate development/test data. Both have different lifecycles.

A seed **never replaces a backup**. If real user data is lost, re-running a seed only recreates sample data—it cannot recover real transactions.

## 3. Preparing PostgreSQL and Connection Tools

You will need:

- A local, containerized, or dedicated learning PostgreSQL server.
- A compatible `psql` client to execute SQL files.
- A role permitted to create databases/schemas and tables in the test environment.
- An editor saving files in **UTF-8**, so accented Vietnamese data is not corrupted.
- Permission to clean the **designated private schema** if choosing the reset approach.

First, verify connectivity using a database the account can access:

~~~bash
psql -h 127.0.0.1 -p 5432 -U lab_user -d postgres
~~~

Inside `psql`:

~~~sql
SELECT
    version() AS postgres_version,
    current_database() AS database_name,
    current_user AS role_name,
    current_setting('server_encoding') AS server_encoding,
    current_setting('TimeZone') AS server_timezone;
~~~

If `psql` reports authentication errors, connection refused, or timeouts, check host, port, role, password, TCP/TLS, and server status. Connection errors are unrelated to the seed file's contents.

### 3.1. Creating the Learning Database Once

If your role is permitted to create databases:

~~~bash
createdb -h 127.0.0.1 -p 5432 -U lab_user -E UTF8 pg_seed_lab
~~~

`createdb` is a client utility requesting the PostgreSQL server to create a database. This is a **one-time setup step**; if `pg_seed_lab` already exists, the command reports an error and does not need to be re-run.

If your environment provides a pre-created database, use it after confirming it is a learning environment and you have rights to create a private schema. Superuser privileges are not strictly required.

Once the database exists:

~~~bash
psql -h 127.0.0.1 -p 5432 -U lab_user -d pg_seed_lab
~~~

### 3.2. Avoid Writing Passwords into Source Code

Do not embed real passwords inside seed files or commit them to Git. Let `psql` prompt interactively, or use a credential store, `.pgpass`/`PGPASSFILE` with proper permissions, or your environment's secret manager. In CI, configure secrets on the runner rather than hardcoding them in the repo.

Never use a production account to test a file containing `DROP SCHEMA`.

## 4. Organizing Files So Everyone Runs the Same Setup

A simple project layout:

~~~text
postgres-lab/
  README.md
  sql/
    seed.sql
    seed-large.sql
    verify.sql
  docs/
    sample-results.md
~~~

Contents and purpose:

- `seed.sql`: recreates the `lab_seed` schema and loads baseline data.
- `seed-large.sql`: optional script generating large rule-based datasets.
- `verify.sql`: holds verification queries.
- `README.md`: documents target PostgreSQL version, load commands, expected values, and safety notes.

**Splitting into multiple files is not mandatory** to follow this lesson: `seed.sql` below is self-contained with all required structure and data. The other files are optional extensions.

If a project already uses a migration framework, integrate seeding into the project's standard workflow to avoid duplicate DDL and environment drift.

## 5. Data Model to Load

We use a small store example:

~~~text
lab_seed.khach_hang (1)
        |
        | 1 - n
        v
lab_seed.don_hang (1) ---- (n) lab_seed.chi_tiet_don_hang
                                            |
                                            | n - 1
                                            v
                                   lab_seed.san_pham
~~~

Four tables:

| Table | Role | Primary Key |
|---|---|---|
| `khach_hang` | Stores customers | `khach_hang_id` |
| `san_pham` | Stores products and current prices | `san_pham_id` |
| `don_hang` | Stores customer orders and statuses | `don_hang_id` |
| `chi_tiet_don_hang` | Stores product, quantity, and price at order time | Composite key `(don_hang_id, san_pham_id)` |

Relationships:

- `don_hang.khach_hang_id` references `khach_hang`.
- `chi_tiet_don_hang.don_hang_id` references `don_hang`.
- `chi_tiet_don_hang.san_pham_id` references `san_pham`.

We deliberately store `don_gia` on the line-item row so exercises can compute line totals using the **price at order time** rather than always reading the current price from the product table.

## 6. Complete seed.sql File: Resetting a Private Schema and Loading Data

Below is the **complete content** for `sql/seed.sql`. It uses a schema named `lab_seed` separate from `public`.

**Warning:** `DROP SCHEMA IF EXISTS lab_seed CASCADE` deletes schema `lab_seed`, every object inside it, and any dependent objects per `CASCADE` rules. Run this only when `lab_seed` belongs to a **disposable learning database** with no valuable data or external dependencies. Never run it on production or uncontrolled shared databases.

~~~sql
-- sql/seed.sql
-- Use only on a disposable learning database.
-- Invoke with psql --single-transaction and ON_ERROR_STOP=1.

SET client_encoding TO 'UTF8';
SET TIME ZONE 'UTC';

DROP SCHEMA IF EXISTS lab_seed CASCADE;
CREATE SCHEMA lab_seed;

CREATE TABLE lab_seed.khach_hang (
    khach_hang_id INTEGER PRIMARY KEY,
    ho_ten TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    tao_luc TIMESTAMPTZ NOT NULL,
    CONSTRAINT chk_khach_hang_ho_ten
        CHECK (length(btrim(ho_ten)) > 0)
);

CREATE TABLE lab_seed.san_pham (
    san_pham_id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    ten_san_pham TEXT NOT NULL,
    gia NUMERIC(12, 2) NOT NULL,
    dang_ban BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT chk_san_pham_gia
        CHECK (gia >= 0)
);

CREATE TABLE lab_seed.don_hang (
    don_hang_id INTEGER PRIMARY KEY,
    khach_hang_id INTEGER NOT NULL
        REFERENCES lab_seed.khach_hang(khach_hang_id),
    dat_luc TIMESTAMPTZ NOT NULL,
    trang_thai TEXT NOT NULL,
    CONSTRAINT chk_don_hang_trang_thai
        CHECK (trang_thai IN ('moi', 'da_thanh_toan', 'da_huy'))
);

CREATE TABLE lab_seed.chi_tiet_don_hang (
    don_hang_id INTEGER NOT NULL
        REFERENCES lab_seed.don_hang(don_hang_id),
    san_pham_id INTEGER NOT NULL
        REFERENCES lab_seed.san_pham(san_pham_id),
    so_luong INTEGER NOT NULL,
    don_gia NUMERIC(12, 2) NOT NULL,
    PRIMARY KEY (don_hang_id, san_pham_id),
    CONSTRAINT chk_chi_tiet_so_luong
        CHECK (so_luong > 0),
    CONSTRAINT chk_chi_tiet_don_gia
        CHECK (don_gia >= 0)
);

-- Parent table: customers.
INSERT INTO lab_seed.khach_hang
    (khach_hang_id, ho_ten, email, tao_luc)
VALUES
    (1, 'Nguyễn An', 'an@example.test',
        TIMESTAMPTZ '2026-01-01 08:00:00+00'),
    (2, 'Trần Bình', 'binh@example.test',
        TIMESTAMPTZ '2026-01-02 08:00:00+00'),
    (3, 'Lê Chi', 'chi@example.test',
        TIMESTAMPTZ '2026-01-03 08:00:00+00'),
    (4, 'Phạm Dũng', 'dung@example.test',
        TIMESTAMPTZ '2026-01-04 08:00:00+00');

-- Parent table: products.
INSERT INTO lab_seed.san_pham
    (san_pham_id, sku, ten_san_pham, gia, dang_ban)
VALUES
    (101, 'BOOK-SQL', 'PostgreSQL Book', 150000.00, TRUE),
    (102, 'KEYBOARD', 'Keyboard', 450000.00, TRUE),
    (103, 'MOUSE', 'Mouse', 180000.00, TRUE),
    (104, 'HEADSET', 'Headset', 650000.00, FALSE);

-- Child table: orders referencing customers.
INSERT INTO lab_seed.don_hang
    (don_hang_id, khach_hang_id, dat_luc, trang_thai)
VALUES
    (1001, 1, TIMESTAMPTZ '2026-01-10 08:00:00+00',
        'da_thanh_toan'),
    (1002, 2, TIMESTAMPTZ '2026-01-11 09:00:00+00',
        'moi'),
    (1003, 1, TIMESTAMPTZ '2026-01-12 10:00:00+00',
        'da_huy'),
    (1004, 3, TIMESTAMPTZ '2026-01-13 11:00:00+00',
        'da_thanh_toan');

-- Child table: order items referencing orders and products.
INSERT INTO lab_seed.chi_tiet_don_hang
    (don_hang_id, san_pham_id, so_luong, don_gia)
VALUES
    (1001, 101, 2, 150000.00),
    (1001, 103, 1, 180000.00),
    (1002, 102, 1, 450000.00),
    (1003, 104, 1, 650000.00),
    (1004, 101, 1, 150000.00),
    (1004, 102, 1, 450000.00);

-- In-load verification: if counts fail, raise an error
-- so psql stops and the transaction rolls back.
DO $seed_verify$
BEGIN
    IF (SELECT count(*) FROM lab_seed.khach_hang) <> 4 THEN
        RAISE EXCEPTION 'Seed khach_hang: expected 4 rows';
    END IF;

    IF (SELECT count(*) FROM lab_seed.san_pham) <> 4 THEN
        RAISE EXCEPTION 'Seed san_pham: expected 4 rows';
    END IF;

    IF (SELECT count(*) FROM lab_seed.don_hang) <> 4 THEN
        RAISE EXCEPTION 'Seed don_hang: expected 4 rows';
    END IF;

    IF (SELECT count(*) FROM lab_seed.chi_tiet_don_hang) <> 6 THEN
        RAISE EXCEPTION 'Seed chi_tiet_don_hang: expected 6 rows';
    END IF;
END;
$seed_verify$;
~~~

The file omits `BEGIN` and `COMMIT` because the next section wraps the entire run with `psql --single-transaction`. If running inside a GUI tool instead of `psql`, control the transaction boundary explicitly.

### 6.1. Why Create Tables in That Order?

Table `don_hang` has a foreign key to `khach_hang`, so the customer table must exist first. `chi_tiet_don_hang` references both `don_hang` and `san_pham`, so it is created after those tables.

Data insertion order follows the same dependency graph:

~~~text
khach_hang ---+
              +--> don_hang ---+
san_pham -----+                +--> chi_tiet_don_hang
~~~

In practice, complex schemas may require different loading strategies, yet **never disable foreign-key checks to hide seed errors**. If seed data violates constraints, fix the seed data or loading sequence first.

### 6.2. Why Use INTEGER and Fixed IDs?

Sample data does not need auto-generated IDs on every run. Assigning explicit IDs ensures JOIN and foreign-key exercises always yield identical results.

For example, order `1001` always belongs to customer `1` with two line items. If IDs came from an advancing sequence, re-running normal `INSERT`s would generate different IDs or break foreign-key references.

PostgreSQL still supports `GENERATED ... AS IDENTITY` and sequences in real applications. This simple seed deliberately uses fixed IDs to avoid resynchronizing sequences at the introductory stage.

### 6.3. Why Use NUMERIC for Money?

`NUMERIC(12,2)` stores exact decimal numbers at the declared precision, making it far more suitable than `REAL` or `DOUBLE PRECISION` for simple monetary calculations in exercises. Line-item prices have two decimal places and stay fixed.

### 6.4. Why Do Timestamps Include +00?

`TIMESTAMPTZ '2026-01-10 08:00:00+00'` pins a specific instant in time. Writing `now()` in a seed produces different values across runs on different days. Using timestamp literals without offsets in timezone-sensitive contexts makes interpretation depend on session settings.

`TIMESTAMPTZ` stores an instant that can be formatted in any session timezone. `SET TIME ZONE 'UTC'` at the top of the file keeps printed output easy to compare; the stored instants already carry explicit `+00` offsets in the data.

## 7. Loading the File with psql in a Single Transaction

From the project directory containing `sql/seed.sql`:

~~~bash
psql \
  -X \
  -v ON_ERROR_STOP=1 \
  --single-transaction \
  -h 127.0.0.1 \
  -p 5432 \
  -U lab_user \
  -d pg_seed_lab \
  -f sql/seed.sql
~~~

Key flags:

| Flag | Meaning |
|---|---|
| `-X` | Ignores the user's `psqlrc` startup file, reducing differences across machines |
| `-v ON_ERROR_STOP=1` | Stops script execution immediately on the first statement error |
| `--single-transaction` or `-1` | Wraps all commands in the run inside a single transaction |
| `-h`, `-p` | Specifies server host and port |
| `-U` | Specifies PostgreSQL role |
| `-d` | Specifies target database |
| `-f` | Reads SQL commands from file |

Because `seed.sql` contains only transaction-safe commands, `psql` executes the schema reset, table creation, and row inserts as one atomic unit. If any statement or assertion causes `psql` to stop with an error, the transaction never commits and all changes from that run roll back.

**Especially important:** `DROP SCHEMA` here runs inside the PostgreSQL transaction, so if the script fails before commit, the previous run's schema is not replaced by a half-loaded state. That is convenient for test environments—but it does not make dropping a schema in the wrong environment safe. Always double-check the target database.

### 7.1. Do Not Mix BEGIN/COMMIT Inside the File with --single-transaction

If you want to use `psql -1`, let `psql` manage the transaction boundary. Do not insert extra `BEGIN` and `COMMIT` statements arbitrarily inside the seed file assuming `-1` will still span everything. In GUI tools, you can issue `BEGIN` and `COMMIT` yourself, provided you understand the tool's autocommit behavior.

### 7.2. Running It a Second Time

Run the **exact same command** a second time. On the dedicated learning database, schema `lab_seed` is replaced by the same four tables and fixed rows. Counts and amounts do not double.

This is the **reset-and-seed** pattern:

~~~text
Run 1: empty schema -> 4 customers, 4 products, 4 orders, 6 items
Run 2: drop schema lab_seed -> recreate -> exact same state
Run 3: drop schema lab_seed -> recreate -> exact same state
~~~

Conversely, any manual edits made inside `lab_seed` are wiped on the next run. **Use this only on environments explicitly approved for resets.**

## 8. Verifying Data After Loading

### 8.1. Checking Row Counts

~~~sql
SELECT 'khach_hang' AS bang, count(*) AS so_dong
FROM lab_seed.khach_hang
UNION ALL
SELECT 'san_pham', count(*)
FROM lab_seed.san_pham
UNION ALL
SELECT 'don_hang', count(*)
FROM lab_seed.don_hang
UNION ALL
SELECT 'chi_tiet_don_hang', count(*)
FROM lab_seed.chi_tiet_don_hang
ORDER BY bang;
~~~

Expected:

| bang | so_dong |
|---|---:|
| chi_tiet_don_hang | 6 |
| don_hang | 4 |
| khach_hang | 4 |
| san_pham | 4 |

### 8.2. Checking JOINs and Order Totals

~~~sql
SELECT
    d.don_hang_id,
    k.ho_ten,
    d.trang_thai,
    SUM(ct.so_luong * ct.don_gia) AS tong_tien
FROM lab_seed.don_hang AS d
JOIN lab_seed.khach_hang AS k
    ON k.khach_hang_id = d.khach_hang_id
JOIN lab_seed.chi_tiet_don_hang AS ct
    ON ct.don_hang_id = d.don_hang_id
GROUP BY
    d.don_hang_id,
    k.ho_ten,
    d.trang_thai
ORDER BY d.don_hang_id;
~~~

Expected output:

| don_hang_id | ho_ten | trang_thai | tong_tien |
|---:|---|---|---:|
| 1001 | Nguyễn An | da_thanh_toan | 480000.00 |
| 1002 | Trần Bình | moi | 450000.00 |
| 1003 | Nguyễn An | da_huy | 650000.00 |
| 1004 | Lê Chi | da_thanh_toan | 600000.00 |

Order `1003` is a cancelled order that still contains line items for practicing status filters. When computing real revenue in exercises, explicitly define whether cancelled and unpaid orders are excluded.

### 8.3. Checking Foreign-Key Integrity

Because the tables define `REFERENCES` constraints, PostgreSQL enforces foreign keys on inserts and updates. You can still write an observation query to understand verification:

~~~sql
SELECT ct.don_hang_id, ct.san_pham_id
FROM lab_seed.chi_tiet_don_hang AS ct
LEFT JOIN lab_seed.don_hang AS d
    ON d.don_hang_id = ct.don_hang_id
LEFT JOIN lab_seed.san_pham AS p
    ON p.san_pham_id = ct.san_pham_id
WHERE d.don_hang_id IS NULL
   OR p.san_pham_id IS NULL;
~~~

Expected result: **0 rows**. If an application ever bypasses constraints during bulk import or performs special recovery, explicit checks like this help audit integrity.

### 8.4. Checking Queries with ORDER BY

~~~sql
SELECT khach_hang_id, ho_ten
FROM lab_seed.khach_hang
ORDER BY khach_hang_id;
~~~

Do not grade or verify exercises by comparing the natural order of `SELECT *` without `ORDER BY`. PostgreSQL does not guarantee row ordering unless sorting is requested.

## 9. Two Reproducibility Strategies: Reset vs. Idempotent

### 9.1. Reset-and-Seed

Idea: drop the test scope, recreate the schema, and load a deterministic set.

**Pros:**

- Guarantees the post-run state matches the baseline, even if a learner previously altered rows.
- Easy to validate row counts and query outputs.
- No need to worry about stale modified records.
- Ideal for temporary test databases and disposable learning environments.

**Cons:**

- Wipes existing data inside the reset scope.
- Can drop dependent objects if `CASCADE` is used.
- Unsuitable for environments holding real data or shared schemas.

### 9.2. Idempotent Seed

Idea: repeated runs never create duplicate records; typically uses a business key or primary key with `ON CONFLICT`.

Example inserting a customer only if absent:

~~~sql
INSERT INTO lab_seed.khach_hang
    (khach_hang_id, ho_ten, email, tao_luc)
VALUES
    (5, 'Võ Hà', 'ha@example.test',
        TIMESTAMPTZ '2026-01-05 08:00:00+00')
ON CONFLICT (khach_hang_id) DO NOTHING;
~~~

Running again will not insert a second row with ID 5 **if ID 5 already exists**. However, if ID 5 previously held a different email or name, `DO NOTHING` leaves the old values untouched. Thus `ON CONFLICT DO NOTHING` **prevents duplicates** without guaranteeing the final row state matches the seed.

If you want final values synced with the file, use an UPSERT:

~~~sql
INSERT INTO lab_seed.khach_hang
    (khach_hang_id, ho_ten, email, tao_luc)
VALUES
    (5, 'Võ Hà', 'ha@example.test',
        TIMESTAMPTZ '2026-01-05 08:00:00+00')
ON CONFLICT (khach_hang_id)
DO UPDATE SET
    ho_ten = EXCLUDED.ho_ten,
    email = EXCLUDED.email,
    tao_luc = EXCLUDED.tao_luc;
~~~

`EXCLUDED` represents the row values proposed by the `INSERT`. This resets ID 5 to the declared values, though you must watch **other unique keys**: if that email already belongs to ID 6, the operation still fails. That is proper behavior; never silently ignore conflicting data.

### 9.3. Which Strategy Should You Use?

| Environment | Appropriate Choice |
|---|---|
| Disposable personal learning database | Reset-and-seed |
| CI spinning up a temporary DB per test suite | Reset-and-seed or per-test fixtures |
| Standard reference/lookup data in staging | Controlled idempotent seed/migration |
| Database shared across multiple teams | Do not auto-reset; define strict scope and privileges |
| Production with live user data | Never run reset scripts; deploy reference data via change-controlled migrations |

Idempotency is a property of **operation logic against a specific state**; merely including `ON CONFLICT` does not automatically make an entire script safe for production.

## 10. Generating Large Deterministic Datasets with generate_series

PostgreSQL provides `generate_series` to generate numeric or timestamp sequences inside queries. This is a handy way to produce thousands or millions of practice rows **without relying on random values**.

Example inspecting a sequence:

~~~sql
SELECT g
FROM generate_series(1, 5) AS g;
~~~

Returns 1, 2, 3, 4, 5.

### 10.1. Adding 1,000 Synthetic Customers

After running the base `seed.sql`, you can run the snippet below as a separate exercise:

~~~sql
INSERT INTO lab_seed.khach_hang
    (khach_hang_id, ho_ten, email, tao_luc)
SELECT
    g,
    'Customer ' || g::text,
    'kh' || lpad(g::text, 5, '0') || '@example.test',
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + ((g - 10001) * INTERVAL '1 minute')
FROM generate_series(10001, 11000) AS g
ON CONFLICT (khach_hang_id)
DO UPDATE SET
    ho_ten = EXCLUDED.ho_ten,
    email = EXCLUDED.email,
    tao_luc = EXCLUDED.tao_luc;
~~~

Formula guarantees:

- IDs always span 10001 through 11000.
- Emails follow a deterministic pattern from each ID.
- Timestamps start from a fixed baseline.
- Each ID receives the exact same name, email, and timestamp across runs.
- Re-running this extension updates existing rows instead of accumulating duplicates.

After this step, `khach_hang` has **1,004 rows** if initially seeded with four customers from `seed.sql`.

### 10.2. Adding 5,000 Formula-Driven Orders

~~~sql
INSERT INTO lab_seed.don_hang
    (don_hang_id, khach_hang_id, dat_luc, trang_thai)
SELECT
    g,
    10001 + ((g - 20001) % 1000),
    TIMESTAMPTZ '2026-02-01 00:00:00+00'
        + ((g - 20001) * INTERVAL '1 minute'),
    CASE (g % 3)
        WHEN 0 THEN 'moi'
        WHEN 1 THEN 'da_thanh_toan'
        ELSE 'da_huy'
    END
FROM generate_series(20001, 25000) AS g
ON CONFLICT (don_hang_id)
DO UPDATE SET
    khach_hang_id = EXCLUDED.khach_hang_id,
    dat_luc = EXCLUDED.dat_luc,
    trang_thai = EXCLUDED.trang_thai;
~~~

For `g` from 20001 to 25000:

- `10001 + ((g - 20001) % 1000)` targets only customer IDs created in the synthetic range.
- Each order receives a deterministic timestamp and status without `random()`.
- All orders reference valid customers provided Step 10.1 succeeded.

### 10.3. Adding One Line Item Per Order

~~~sql
INSERT INTO lab_seed.chi_tiet_don_hang
    (don_hang_id, san_pham_id, so_luong, don_gia)
SELECT
    g,
    101 + (g % 4),
    1 + (g % 3),
    p.gia
FROM generate_series(20001, 25000) AS g
JOIN lab_seed.san_pham AS p
    ON p.san_pham_id = 101 + (g % 4)
ON CONFLICT (don_hang_id, san_pham_id)
DO UPDATE SET
    so_luong = EXCLUDED.so_luong,
    don_gia = EXCLUDED.don_gia;
~~~

Since `san_pham` holds IDs 101–104, `101 + (g % 4)` always picks one of the four seeded products. Line-item prices come from `san_pham`. In this example, product prices from the base seed stay fixed.

After all three scaling steps, expected state:

| Table | Initial | Added | Total |
|---|---:|---:|---:|
| `khach_hang` | 4 | 1,000 | 1,004 |
| `san_pham` | 4 | 0 | 4 |
| `don_hang` | 4 | 5,000 | 5,004 |
| `chi_tiet_don_hang` | 6 | 5,000 | 5,006 |

**Limitation:** data generated by these formulas works well for practicing `JOIN`, `GROUP BY`, indexes, and basic pagination, but **does not represent production data distributions**. Real workloads often involve skewed purchasing patterns, varying item counts per order, seasonality, hot keys, and column correlations.

### 10.4. Putting Scaling Statements in a Separate File

Save the three snippets in `sql/seed-large.sql` and run it after `seed.sql`. Never run the scaling script before the base seed, as foreign keys will fail.

Example:

~~~bash
psql -X -v ON_ERROR_STOP=1 --single-transaction \
  -h 127.0.0.1 -p 5432 -U lab_user -d pg_seed_lab \
  -f sql/seed-large.sql
~~~

To return to a clean baseline of the large dataset, always run the **base seed first, then the large seed**. Re-running `seed.sql` resets the schema and clears the scaled rows by design.

## 11. Why Avoid Uncontrolled random()?

The query:

~~~sql
SELECT
    g,
    random() AS diem
FROM generate_series(1, 10) AS g;
~~~

yields different values across runs. While occasionally useful for simulating randomness, it complicates assertions based on exact expected values.

PostgreSQL provides `setseed` to initialize `random()`'s pseudo-random sequence per session, e.g.:

~~~sql
SELECT setseed(0.42);

SELECT random();
~~~

However, if call counts or execution order change—due to query plan changes, parallelism, PostgreSQL versions, or generation logic—row-level outputs can shift. Setting a PRNG seed **does not automatically guarantee identical datasets across every environment**.

For highly deterministic seeds, prefer formulas computed directly from the ID:

~~~sql
SELECT
    g AS id,
    1 + ((g * 17) % 5) AS so_luong,
    10000 + ((g * 97) % 90000) AS gia_mau
FROM generate_series(1, 10) AS g
ORDER BY g;
~~~

Each ID always yields the exact same values. When realistic distributions are needed, prepare a versioned fixture file or a generator with a pinned algorithm, config, and version.

## 12. Creating Sample Data with CSV and \copy

Seeds are not always most convenient as long `INSERT` lists. For standalone lookup tables or data curated by business teams, CSV files can be easier to read and diff.

Example `sql/products.csv` (UTF-8):

~~~csv
san_pham_id,sku,ten_san_pham,gia,dang_ban
101,BOOK-SQL,PostgreSQL Book,150000.00,true
102,KEYBOARD,Keyboard,450000.00,true
103,MOUSE,Mouse,180000.00,true
104,HEADSET,Headset,650000.00,false
~~~

Two file-import mechanisms are frequently confused:

### 12.1. SQL COPY Reads Files on the Server

~~~sql
COPY lab_seed.san_pham
    (san_pham_id, sku, ten_san_pham, gia, dang_ban)
FROM '/srv/data/products.csv'
WITH (FORMAT csv, HEADER true);
~~~

The path lives on the **PostgreSQL server host**; the server process must be able to read it, and permissions to execute `COPY FROM file` are restricted. On managed PostgreSQL services, you usually cannot place files on the server's filesystem.

### 12.2. \copy Reads Files on the psql Client

Inside `psql`:

~~~text
\copy lab_seed.san_pham (san_pham_id, sku, ten_san_pham, gia, dang_ban) FROM 'sql/products.csv' WITH (FORMAT csv, HEADER true)
~~~

`\copy` is a `psql` meta-command that reads the file on the **client machine running `psql`** and streams it over the connection. This is typically the right choice when the CSV resides on a laptop or CI runner while PostgreSQL runs in Docker or remotely.

**Note:** `san_pham` from the base seed already contains IDs 101–104. Running `\copy` directly into that table without clearing existing rows raises a primary-key conflict. To use CSV as the seed source instead of product `INSERT`s, omit the corresponding `INSERT` in an alternate seed script, or load into a staging table and merge with a controlled UPSERT.

### 12.3. \copy Is Not Pure SQL

`\copy` works in `psql`, but cannot be sent verbatim as a regular SQL statement from JDBC or SQL-only query editors. From applications, use your PostgreSQL driver's COPY API or parameterized `INSERT` statements.

### 12.4. CSV and Locales

When using CSV:

- Standardize on UTF-8 encoding.
- Define delimiters and quoting clearly.
- Document representations for NULLs, booleans, numbers, and timestamps.
- Do not let Excel silently reformat IDs, decimal separators, or dates.
- Commit CSV files to version control if they contain no sensitive data.

If CSV values contain commas inside names or text, follow proper CSV quoting. Never split lines naively on commas expecting clean results.

## 13. Seeding in Docker: Ephemeral Databases and Volume Lifecycles

Docker lets teams run the exact same PostgreSQL major version locally. Example `compose.yaml` for a lab:

~~~yaml
services:
  db:
    image: postgres:16
    env_file:
      - .env
    ports:
      - "127.0.0.1:55432:5432"
    volumes:
      - pg_seed_data:/var/lib/postgresql/data

volumes:
  pg_seed_data:
~~~

Local `.env` file configuring the container:

~~~text
POSTGRES_USER=lab_user
POSTGRES_DB=pg_seed_lab
POSTGRES_PASSWORD=<local-password-do-not-commit>
~~~

The password value here is a placeholder, not a valid configured secret. Never commit files containing secrets to Git; use `.gitignore` and proper secret distribution.

Start:

~~~bash
docker compose up -d
~~~

Connect from the host where `psql` is installed:

~~~bash
psql -X -h 127.0.0.1 -p 55432 \
  -U lab_user -d pg_seed_lab
~~~

Load the seed:

~~~bash
psql -X -v ON_ERROR_STOP=1 --single-transaction \
  -h 127.0.0.1 -p 55432 \
  -U lab_user -d pg_seed_lab \
  -f sql/seed.sql
~~~

Example port setup:

- Inside the container, PostgreSQL listens on port 5432 per image defaults.
- On the host, `127.0.0.1:55432` maps to container port 5432.
- Bind only to loopback for lab purposes; never expose PostgreSQL to public networks.

### 13.1. Why Does Changing init.sql Not Reload Automatically on Container Restart?

In standard PostgreSQL Docker images, scripts in `/docker-entrypoint-initdb.d` run only when the **data directory is uninitialized**. Once the volume holds a PostgreSQL cluster, restarting the container does not re-execute init scripts.

Never rely on container restarts to re-seed data. In this lesson, **explicitly loading with `psql -f sql/seed.sql`** ensures behavior never depends on init-only hooks.

### 13.2. Warning About Volumes

Commands that delete volumes such as `docker compose down -v` wipe all PostgreSQL data stored in the project volume. Run them only when certain the volume contains disposable lab data. You do not need to delete the volume to re-test the seed: `seed.sql` already resets schema `lab_seed`.

### 13.3. Pinning the Image Version

`postgres:16` pins the major branch in this example, though patch releases can change over time. When tests require an **exact identical** environment across runs, pin a specific version or controlled image digest and standardize extensions, collation/locale, configs, and client versions across your workflow.

## 14. Seeding in CI and Automated Tests

In CI, the goal is starting every test run from an **isolated database with deterministic data**.

A general pipeline:

~~~text
[1] Start PostgreSQL test container/service
       |
       v
[2] Create dedicated test database or schema
       |
       v
[3] Run schema migrations (if applicable)
       |
       v
[4] Load versioned seeds/fixtures
       |
       v
[5] Verify required baseline data
       |
       v
[6] Run integration tests
       |
       v
[7] Collect logs and clean up test environment
~~~

In a self-contained learning repo, basic DDL and seed data can live together in `seed.sql`. In projects with proper schema migrations, keep migrations and seeds separate so two structural definitions never compete.

### 14.1. Using Environment Variables for Connections

`psql` reads connection defaults from environment variables such as `PGHOST`, `PGPORT`, `PGUSER`, and `PGDATABASE`:

~~~bash
psql -X -v ON_ERROR_STOP=1 \
  --single-transaction -f sql/seed.sql
~~~

This assumes the runner injects appropriate connection variables and secrets; the command itself contains no credentials. CI steps must fail immediately if `psql` exits non-zero. Never swallow errors and run tests against a half-seeded database.

### 14.2. Separating Shared Baseline Data from Per-Test Fixtures

Avoid cramming every edge case into the base seed. You can organize:

~~~text
sql/
  seed.sql              # Shared standard baseline dataset
  fixtures/
    empty-order.sql     # An order with no line items
    cancelled-order.sql # Data for cancelled-order tests
    many-records.sql    # High-volume dataset
~~~

Each test suite should declare which fixtures it loads, in what order, and how cleanup works. If a test mutates data, start from a fresh database/schema on the next run.

## 15. Synchronizing Sequences When Using IDENTITY or SERIAL

The basic example uses manually supplied `INTEGER` IDs. In real applications, tables often use:

~~~sql
CREATE TABLE lab_seed.nhat_ky_seed (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    noi_dung TEXT NOT NULL
);
~~~

You can insert explicit IDs:

~~~sql
INSERT INTO lab_seed.nhat_ky_seed (id, noi_dung)
VALUES (10, 'Seed row with fixed ID');
~~~

However, inserting an explicit ID into a `BY DEFAULT` identity column **does not automatically advance the underlying sequence to 11**. Later inserts omitting the ID draw from the sequence's lower counter and eventually collide once the sequence reaches an already-taken ID.

You can synchronize the sequence after loading fixed IDs:

~~~sql
SELECT setval(
    pg_get_serial_sequence('lab_seed.nhat_ky_seed', 'id'),
    (SELECT max(id) FROM lab_seed.nhat_ky_seed),
    true
);
~~~

This assumes the table **has at least one row** and owns the corresponding sequence. Passing `true` means the next `nextval` call returns the value after the set maximum. For empty tables or custom increments, handle edge cases accordingly.

Example:

~~~sql
INSERT INTO lab_seed.nhat_ky_seed (noi_dung)
VALUES ('Auto-generated ID row');

SELECT id, noi_dung
FROM lab_seed.nhat_ky_seed
ORDER BY id;
~~~

With a default increment of 1 and row ID 10 seeded earlier, the new row receives ID 11.

### 15.1. How Do SERIAL and IDENTITY Differ in Seeds?

- `SERIAL` is convenience syntax creating a sequence, default expression, and ownership linkage.
- `GENERATED ... AS IDENTITY` is PostgreSQL's modern SQL-standard identity syntax.
- `GENERATED ALWAYS AS IDENTITY` requires `OVERRIDING SYSTEM VALUE` if intentionally inserting explicit IDs.
- `GENERATED BY DEFAULT AS IDENTITY` permits normal explicit ID inserts.

If a seed supplies explicit IDs, know which sequence/identity is backing the column and resynchronize it afterward when needed. Never assume sequences roll back like table data inside transactions; gaps from issued sequence values are normal behavior.

## 16. Transactions, Rollbacks, and Atomic Loads

Loading a seed involves multiple statements. If the final step fails while earlier steps already committed, the database is left half-updated.

Example **without a wrapping transaction**:

~~~text
DROP schema       -> succeeds, committed
CREATE tables     -> succeeds, committed
INSERT customers  -> succeeds, committed
INSERT orders     -> foreign-key error
Result: partially loaded database
~~~

Approach with `psql --single-transaction -v ON_ERROR_STOP=1` for transactional SQL seeds:

~~~text
BEGIN
  DROP SCHEMA lab_seed
  CREATE SCHEMA lab_seed
  CREATE TABLE...
  INSERT...
  DO verification...
COMMIT only if every command succeeds

On any error -> entire transaction rolls back
~~~

In PostgreSQL, most DDL commands such as `CREATE TABLE` and `DROP TABLE` are transactional. However, not all administrative commands can run inside a transaction block—`CREATE DATABASE` is a notable exception, which is why database creation runs **separately** prior to the seed script.

### 16.1. Practicing a Controlled Foreign-Key Error

On the loaded lab schema, open a test session:

~~~sql
BEGIN;

INSERT INTO lab_seed.don_hang
    (don_hang_id, khach_hang_id, dat_luc, trang_thai)
VALUES
    (9999, 999999,
        TIMESTAMPTZ '2026-03-01 10:00:00+00',
        'moi');

-- The INSERT fails because customer 999999 does not exist.
-- The transaction is now in an aborted state.

ROLLBACK;
~~~

The foreign-key error shows PostgreSQL protecting referential integrity. After a statement fails inside a transaction, subsequent statements are rejected until you roll back (or restore a savepoint). Never try to `COMMIT` a failed transaction expecting earlier steps to remain valid.

This failure exercise **must not live inside `seed.sql`**; the main seed file should complete cleanly.

## 17. Verifying Data with Assertions Instead of Eyeballing Tables

Beyond row-count checks in `DO` blocks, you can assert other invariants.

### 17.1. Checking the Total Amount for Order 1001

~~~sql
DO $check_total$
DECLARE
    v_total NUMERIC(14, 2);
BEGIN
    SELECT SUM(so_luong * don_gia)
    INTO v_total
    FROM lab_seed.chi_tiet_don_hang
    WHERE don_hang_id = 1001;

    IF v_total IS DISTINCT FROM 480000.00 THEN
        RAISE EXCEPTION
            'Unexpected total for order 1001: %', v_total;
    END IF;
END;
$check_total$;
~~~

`IS DISTINCT FROM` handles `NULL` safely, avoiding pitfalls where `<> NULL` evaluates to unknown rather than true.

### 17.2. Checking for Duplicate Emails

~~~sql
SELECT email, count(*) AS so_lan
FROM lab_seed.khach_hang
GROUP BY email
HAVING count(*) > 1;
~~~

Because the table defines `UNIQUE (email)`, this query should return zero rows; the constraint catches duplicates early at write time.

### 17.3. Checking Row Counts on the Large Seed

~~~sql
SELECT count(*) AS so_khach
FROM lab_seed.khach_hang;

SELECT count(*) AS so_don
FROM lab_seed.don_hang;

SELECT count(*) AS so_dong_chi_tiet
FROM lab_seed.chi_tiet_don_hang;
~~~

Expect `1004`, `5004`, and `5006` **after running all three parts of the large seed** on top of the base seed. If only the base seed ran, expect `4`, `4`, and `6`. Never apply the same assertion suite to two different dataset profiles without documenting which profile is active.

### 17.4. Checking a Data Hash When Comparing Environments

You can compute a deterministic fingerprint over an ordered result set:

~~~sql
SELECT md5(
    string_agg(
        khach_hang_id::text || ':' || email,
        '|'
        ORDER BY khach_hang_id
    )
) AS fingerprint
FROM lab_seed.khach_hang;
~~~

This checksum covers the selected representation; it does not prove the entire database is identical. For strict reconciliation, specify exact columns, NULL handling, timezone, numeric formatting, and ordering. MD5 here serves purely for **simple diff detection** in exercises, not security or tamper protection.

## 18. Keeping Sample Datasets Stable Across PostgreSQL Versions

A SQL seed fixes data values, yet runtime environment differences still affect results and performance.

Parameters to record:

- PostgreSQL server and `psql` client versions.
- Database and file encoding.
- Timezone, locale, and collation.
- Installed extensions.
- Schema migration version.
- Role names and privilege scopes.
- Data types, rounding rules, and arithmetic behavior.
- Seed script version.
- Environment variables affecting execution.

For instance, sorting accented strings can vary across collations/locales. Therefore, when exercises compare ordered results, **do not rely on default `TEXT` sort order across every system** unless the collation is explicitly specified and tested. For basic seeds, sorting by ID is clearer.

### 18.1. Timestamps and Output Formatting

Two sessions with different timezones format the same `TIMESTAMPTZ` instant in different local times. For deterministic text verification, normalize explicitly:

~~~sql
SELECT
    don_hang_id,
    dat_luc AT TIME ZONE 'UTC' AS dat_luc_utc
FROM lab_seed.don_hang
ORDER BY don_hang_id;
~~~

`AT TIME ZONE 'UTC'` converts `TIMESTAMPTZ` into a timezone-less wall-clock timestamp in UTC for display. When transferring data between systems, always verify the exact data types and instants represented.

## 19. Seeds and Sensitive Data

Never take a production database dump containing real names, emails, phone numbers, or transactions and commit it straight to Git as a seed.

For practice examples, use:

- Reserved documentation email domains such as `example.test`.
- Synthetic names and records unrelated to real people.
- Illustrative payment amounts.
- Zero real passwords, tokens, API keys, account numbers, or PII.

If a team needs production-like data, enforce a **verified anonymization/masking pipeline**, restrict access, and set retention limits. Simply masking names may not protect privacy if IDs, addresses, timestamps, and linked fields still enable re-identification.

## 20. Common Mistakes When Loading Seeds

### Mistake 1: Running a Reset Script on the Wrong Database

`DROP SCHEMA ... CASCADE` can wipe dependent objects.

**Resolution:** use a dedicated lab database/schema, check `current_database()` and endpoint before running, and never run reset scripts on real data.

### Mistake 2: Running a Seed Twice and Getting Duplicates

An `INSERT`-only script against a preserved table raises `duplicate key` errors or inserts duplicate rows if constraints are missing.

**Resolution:** pick reset-and-seed or key-based UPSERT rather than manual cleanup.

### Mistake 3: Using now() Causes Shifting Results

Time-filtered reports produce different results the next day.

**Resolution:** use fixed timestamps with explicit offsets when exercises require stable outputs.

### Mistake 4: Using Uncontrolled random()

Values and distributions change across every load.

**Resolution:** use ID-based formulas or versioned fixture files when deterministic outputs are needed.

### Mistake 5: Inserting Child Tables Before Parent Tables

Foreign-key constraints reject inserts because referenced parent rows do not exist yet.

**Resolution:** load in dependency order; never disable constraints carelessly.

### Mistake 6: Forgetting ON_ERROR_STOP

Scripts keep executing past failed statements, leaving hard-to-diagnose partial states.

**Resolution:** always pass `-v ON_ERROR_STOP=1` and inspect exit codes in terminals/CI.

### Mistake 7: Skipping Transactions

Part of the seed commits even though a later command fails.

**Resolution:** use `--single-transaction` for compatible transactional scripts and exclude non-transactional admin commands.

### Mistake 8: Forgetting to Reset Sequences After Explicit IDs

Later inserts omitting IDs collide with existing primary keys.

**Resolution:** resynchronize `SERIAL`/`IDENTITY BY DEFAULT` sequences after seeding explicit IDs if auto-generated IDs will follow.

### Mistake 9: Wrong CSV File Encoding

Accented Vietnamese names turn into garbled characters.

**Resolution:** save files as UTF-8 and check `client_encoding`, `server_encoding`, and editor/export settings.

### Mistake 10: Confusing COPY and \copy

The file sits on your laptop while SQL `COPY FROM '/home/...csv'` tells the server to read from the server's own disk.

**Resolution:** use `\copy` in `psql` for client-side files, or stage files on the server via proper procedures.

### Mistake 11: Docker Restart Does Not Re-Run Init Scripts

The volume already holds an initialized cluster, so one-time init scripts are skipped.

**Resolution:** execute seeds explicitly with `psql -f` as a deliberate step.

### Mistake 12: Relying on SELECT * Without ORDER BY

Identical data returns in different row orders.

**Resolution:** always include `ORDER BY` when deterministic row order matters.

### Mistake 13: Drawing Production Performance Conclusions from Synthetic Data

Uniform ID ranges and simple formulas lack real-world hot keys and data skew.

**Resolution:** use synthetic data to learn SQL syntax; production benchmarks require representative data and workloads.

### Mistake 14: Loading into the Wrong Schema Due to search_path

Unqualified SQL statements may write into `public` or another schema depending on `search_path`.

**Resolution:** use schema-qualified names like `lab_seed.khach_hang` in seeds, or explicitly set `search_path` and verify your environment.

### Mistake 15: Checking Only That the Seed Ran Without Verifying Results

The command exits cleanly while rows are missing or totals are off.

**Resolution:** add assertions for row counts, foreign keys, and business metrics such as order totals.

## 21. End-to-End Walkthrough

To practice on your own machine:

**Step 1 — Have PostgreSQL server and psql ready:** verify connection, role, and version.

**Step 2 — Create database `pg_seed_lab`:** run `createdb` once if needed and permitted.

**Step 3 — Save `sql/seed.sql` as UTF-8:** use the complete script from Section 6.

**Step 4 — Run `psql -X -v ON_ERROR_STOP=1 --single-transaction -f sql/seed.sql`:** target the right host, port, user, and database.

**Step 5 — Verify all four tables:** expect 4 customers, 4 products, 4 orders, and 6 line items.

**Step 6 — Run the JOIN calculating order totals:** order 1001 must total 480000.00; order 1004 must total 600000.00.

**Step 7 — Re-run `seed.sql`:** results and row counts remain unchanged.

**Step 8 — For large data, create `sql/seed-large.sql`:** combine the three `generate_series` queries from Section 10, load sequentially, and verify row totals.

**Step 9 — Practice a failure case in a separate transaction:** trigger a foreign-key violation and `ROLLBACK` as shown in Section 16.

**Step 10 — Commit seeds and docs to version control:** ensure zero secrets or real personal data are included.

When working in a team, everyone should use the same file version, the same baseline/extended seed profile, and the same verification rules. This establishes a reliable input baseline for upcoming lessons on `JOIN`, `GROUP BY`, indexes, transactions, and `EXPLAIN`.

## 22. Self-Practice Exercises

### Exercise 1 — Verifying Fixed Results

After running the base seed, write SQL to count customers, products, orders, and line items. What should the counts be?

**Hint:** 4, 4, 4, and 6 respectively.

### Exercise 2 — Computing Order Total

Write SQL calculating the total amount for order 1001 from `so_luong * don_gia` without looking up current prices in the product table.

**Hint:** two items (2 × 150000 and 1 × 180000), totaling 480000.00.

### Exercise 3 — Re-Runnable Customer Insert

Create customer ID 5 with email `ha@example.test` so running the script twice leaves only one row whose final values match the seed.

**Hint:** `INSERT ... ON CONFLICT (khach_hang_id) DO UPDATE SET ...`.

### Exercise 4 — Foreign Keys

Try creating an order with `khach_hang_id = 999999`. Why is it rejected?

**Hint:** no customer exists with that ID; the `REFERENCES` constraint blocks orphaned child records.

### Exercise 5 — Testing Errors Inside a Transaction

Start a transaction, insert one valid row, and then insert one row violating a foreign key. Can you continue writing normally without rolling back?

**Hint:** after an error, the transaction enters an aborted state; you must roll back or use a savepoint properly.

### Exercise 6 — Bulk Generation

Write a `generate_series` query creating 2,000 products with IDs 50001–52000, unique SKUs, and deterministic prices derived from ID.

**Hint:** use `'SKU-' || g::text`, `1000 + ((g * 7) % 90000)`, and `ON CONFLICT` if re-runnability is desired.

### Exercise 7 — Deterministic Timestamps

Why is `TIMESTAMPTZ '2026-01-10 08:00:00+00'` better than `now()` for fixtures?

**Hint:** fixed instants do not depend on the run date; time-based tests remain predictable.

### Exercise 8 — CSV in Docker

You have `products.csv` on the host machine while PostgreSQL runs in a container. Should you use `COPY FROM '/home/...'` or `\copy` from host `psql`?

**Hint:** `\copy` reads the file on the client, avoiding placing files inside the server's filesystem.

### Exercise 9 — Idempotency and Modified Data

Row ID 5 already exists with an email differing from the seed. Can `ON CONFLICT DO NOTHING` fix the email?

**Hint:** no; use an UPSERT `DO UPDATE` if the final state must match the seed.

### Exercise 10 — Sequences

A `GENERATED BY DEFAULT AS IDENTITY` table was seeded with explicit ID 100. Why might a later insert collide with an existing ID if the sequence is not resynchronized?

**Hint:** explicit ID inserts do not automatically advance the sequence to the inserted value.

### Exercise 11 — CI

Propose three criteria ensuring CI halts immediately when seed loading fails instead of running tests on partially loaded data.

**Hint:** `ON_ERROR_STOP=1`, wrapping transaction, and checking exit codes/assertions.

### Exercise 12 — Reproducibility

A team runs the exact same seed file under different locales, timezones, and image versions. Even with identical logical data, where might display or sort outputs differ?

**Hint:** timezone formatting of timestamps, collation sorting of `TEXT`, unordered queries lacking `ORDER BY`, and version-specific behavior differences.

## 23. Key Takeaways

- **Seed data** is an initial dataset for learning and testing; it never replaces migrations or backups.
- To be **reproducible**, combine deterministic data, explicit load commands, bounded scope, and automated verification.
- Keep `seed.sql` under **version control**, saved as UTF-8, with zero sensitive data.
- `psql -X -v ON_ERROR_STOP=1 --single-transaction -f ...` is the right loading pattern when the script contains only transaction-safe statements.
- Reset-and-seed guarantees identical post-run state every time, but **use it only on disposable learning schemas/databases**.
- `ON CONFLICT DO NOTHING` prevents duplicate-key errors without guaranteeing final values match the seed; `DO UPDATE` synchronizes values per policy.
- `generate_series` with ID-based formulas generates repeatable large datasets; uncontrolled `random()` makes outputs unpredictable.
- Load **parent tables before child tables** and let PostgreSQL enforce foreign keys.
- `COPY` reads files on the server; `\copy` in `psql` reads files on the client.
- When seeding explicit IDs into `IDENTITY`/`SERIAL` columns, remember to synchronize sequences.
- Always **verify row counts, relationships, totals, and explicit sort order**, rather than assuming tool completion equals valid data.
- Identical data does not guarantee identical default query order or production benchmarks; control timezone, collation, versions, and workloads.

A good PostgreSQL sample dataset does not need to be complex, but it must be **designed so anyone can re-run it from scratch, verify its outputs, and know the exact scope the script modifies**. That forms the foundation for learning SQL, writing integration tests, and maintaining consistent development environments.
