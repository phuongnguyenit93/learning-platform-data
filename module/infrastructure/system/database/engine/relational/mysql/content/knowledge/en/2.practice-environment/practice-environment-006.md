# Setting Up a Practice Account with Least Privilege

A safe MySQL practice environment needs a dedicated database and a dedicated account for the learner or application. This account should only be allowed to perform the tasks required within the scope of the exercises. If you use the `root` account for every operation, a single mistaken statement could affect other databases or the entire server configuration.

In this lesson, we create the `mysql_lab` database and a `mysql_lab_user` account for practicing SQL. The account can read and write data, create and alter tables, and create indexes inside the practice database. The account cannot administer users, grant privileges, arbitrarily create databases, or drop databases and tables. Examples use MySQL 8.x syntax; replace passwords and connection addresses according to your actual environment.

## 1. Understanding the Principle of Least Privilege

Least privilege means each account receives only the set of privileges needed to complete its work. When determining privileges, answer three questions: what operations does the account need to perform, on which objects, and from which hosts is it allowed to connect?

MySQL allows granting privileges at multiple scopes:

| Scope | Example | Effect |
|---|---|---|
| Server-wide | `ON *.*` | Applies to corresponding databases and objects across the entire server |
| Single database | `ON mysql_lab.*` | Applies to tables and objects belonging to the `mysql_lab` database |
| Single table | `ON mysql_lab.customers` | Applies only to the `customers` table in `mysql_lab` |
| Specific columns | `ON mysql_lab.customers (email)` | Applies only to the specified columns, for privileges supporting column scope |

For a learning environment, dedicate a separate database for practice exercises and grant privileges on that database. Avoid granting global privileges with `ON *.*` unless the exercise requires administering the entire server.

Different account types typically serve different purposes:

- **Administrative or environment-setup accounts** create databases, create users, and grant privileges. Only designated administrators should use these accounts.
- **Practice accounts** work with tables and data inside the assigned database. This is the account used in MySQL Workbench, the command line, or the exercise's Java program.
- **Routine application accounts** typically need only DML privileges such as `SELECT`, `INSERT`, `UPDATE`, and `DELETE`. Table structure changes should be performed by a separate deployment/migration account.
- **Read-only accounts** typically need only `SELECT` on authorized tables.

Do not share an administrative account with applications. Separating accounts by purpose limits damage if a password is exposed and makes auditing operations easier.

## 2. Preparing the Practice Database

Log in to MySQL using an administrative account with privileges to create databases, create users, and grant privileges. In a learning environment on a personal machine, you can use a local administrative account. Do not put administrative passwords in source code or share them within a group.

Verify the server you are connected to:

```sql
SELECT VERSION();
SELECT CURRENT_USER();
```

Create a dedicated database for the practice exercises:

```sql
CREATE DATABASE mysql_lab
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;
```

`utf8mb4` supports full Unicode, suitable for Vietnamese text and many other character sets. The `mysql_lab` database is the lesson's practice workspace; do not use system databases such as `mysql`, `sys`, `performance_schema`, or `information_schema` for exercises.

If the database already exists, check its owner and data before using it. Never drop or recreate an existing database without knowing what purpose it serves.

## 3. Creating a Dedicated Practice Account

In MySQL, an account is identified by both the username and the host portion. Therefore, `'mysql_lab_user'@'localhost'` and `'mysql_lab_user'@'10.0.0.25'` are two distinct account identities, even though they share the same username.

For applications or tools running directly on the MySQL machine, create an account for local connections:

```sql
CREATE USER 'mysql_lab_user'@'localhost'
    IDENTIFIED BY 'replace-with-a-unique-strong-password';
```

Replace the placeholder password string with a strong password dedicated to the practice environment. This statement lets MySQL use the server's default authentication mechanism. Never use example passwords in real environments and never write real passwords into Git.

If an application runs on another machine, create the account with the exact host address or hostname of the source machine as seen by MySQL, for example:

```sql
CREATE USER 'mysql_lab_user'@'10.0.0.25'
    IDENTIFIED BY 'replace-with-a-unique-strong-password';
```

`10.0.0.25` is only an illustrative address. Replace it with the actual client address and grant privileges to that exact account identity. Do not default to host `%`, as it permits connections from many source addresses; if you must use it in an isolated lab, restrict access using the network and firewall.

## 4. Granting the Exact Privileges Needed for Practice

The practice account needs to work with tables and data in `mysql_lab`. Grant the following privileges at the database scope:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE,
      CREATE, ALTER, INDEX
ON mysql_lab.*
TO 'mysql_lab_user'@'localhost';
```

Meaning of each privilege:

| Privilege | Permitted Operation |
|---|---|
| `SELECT` | Read data |
| `INSERT` | Insert records |
| `UPDATE` | Update records |
| `DELETE` | Delete records |
| `CREATE` | Create tables in the granted database |
| `ALTER` | Modify table structure |
| `INDEX` | Create and drop indexes |

These privileges are sufficient for many table design, querying, and basic data manipulation exercises. They apply only within `mysql_lab`, without granting similar privileges across the entire server.

We intentionally omit `DROP`, `CREATE USER`, `GRANT OPTION`, `FILE`, `PROCESS`, or global administrative privileges. `DROP` allows deleting objects within the database scope, so grant it only when an exercise genuinely requires it and the target is a disposable test database. If you need to practice dropping tables, have an administrator prepare a dedicated schema for destructive exercises and restrict `DROP` to that schema.

If an application only needs to operate on an existing table, you can restrict privileges further at the table level. For example, an account that only manipulates data in the `customers` table:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON mysql_lab.customers
TO 'mysql_lab_user'@'localhost';
```

In this case, do not grant DDL privileges if the application does not need to create or alter table structures. Remember to match the account host in the `GRANT` statement to the account created in the previous step.

## 5. Verifying Granted Privileges

After creating the user and granting privileges, use the administrative account to inspect the grants:

```sql
SHOW GRANTS FOR 'mysql_lab_user'@'localhost';
```

The output usually contains a `USAGE ON *.*` line and a privilege line on `mysql_lab.*`. `USAGE` indicates that the account exists but grants no access privileges by itself. Check the scope of the `GRANT` line to ensure there are no unintended privileges on `*.*`.

Log in using the practice account:

```bash
mysql --host=localhost --port=3306 --user=mysql_lab_user --password mysql_lab
```

The `--password` option makes the client prompt for the password in the terminal. Never write the password directly after `--password` because command-line arguments can be saved in shell history or exposed in the process list.

After logging in, verify the account identity and current database:

```sql
SELECT USER(), CURRENT_USER(), DATABASE();
SHOW GRANTS;
```

`USER()` shows the username and host sent by the client; `CURRENT_USER()` shows the account MySQL actually used for authentication and privilege checking. These two values help detect cases where a connection matched a different account host than intended.

## 6. Testing Permitted and Denied Operations

While logged in as `mysql_lab_user`, create a test table:

```sql
CREATE TABLE permission_check (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(254) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE INDEX idx_permission_check_email
    ON permission_check (email);
```

These two statements verify `CREATE` and `INDEX` privileges. Next, test data manipulation inside a transaction so the test data can be rolled back:

```sql
START TRANSACTION;

INSERT INTO permission_check (email)
VALUES ('learner@example.com');

SELECT id, email, created_at
FROM permission_check;

UPDATE permission_check
SET email = 'updated@example.com'
WHERE email = 'learner@example.com';

DELETE FROM permission_check
WHERE email = 'updated@example.com';

ROLLBACK;
```

The read, insert, update, and delete statements should succeed. `ROLLBACK` undoes changes inside the transaction so the table does not retain test records. If you need to test the `ALTER` privilege, you can add a test column:

```sql
ALTER TABLE permission_check
ADD COLUMN note VARCHAR(100) NULL;
```

Next, test the following statements. With the privilege set granted in step 4, MySQL must reject these statements because the account lacks the corresponding privileges:

```sql
CREATE DATABASE another_database;
CREATE USER 'another_user'@'localhost' IDENTIFIED BY 'temporary-password';
DROP TABLE mysql_lab.permission_check;
DROP DATABASE mysql_lab;
```

Exact error messages may vary by version and context, but the expected outcome is that the practice account cannot create databases, create users, or drop tables/databases. There is no need to test `GRANT` on a real environment; this account also lacks `GRANT OPTION` to grant privileges to others.

When finished, an administrator can log back in and drop the test table to keep the database clean:

```sql
DROP TABLE IF EXISTS mysql_lab.permission_check;
```

This cleanup statement is run by the administrative account. The practice account does not need `DROP` just so an administrator can clean up test artifacts.

## 7. Connecting with the Account from a Java Application

A Java application connects to MySQL Server via the MySQL Connector/J JDBC driver. Connection settings must use the exact username, host, and database that were granted privileges. Example local JDBC URL:

```java
String url = "jdbc:mysql://localhost:3306/mysql_lab";
String username = "mysql_lab_user";
String password = System.getenv("MYSQL_LAB_PASSWORD");

if (password == null || password.isEmpty()) {
    throw new IllegalStateException("MYSQL_LAB_PASSWORD is not configured");
}

try (Connection connection =
         DriverManager.getConnection(url, username, password)) {
    System.out.println("Connected to MySQL: " + connection.getCatalog());
}
```

This snippet assumes the project declares MySQL Connector/J and JDBC types such as `Connection` and `DriverManager` are imported. The `MYSQL_LAB_PASSWORD` environment variable holds the password configured by whoever runs the application. Never hard-code real passwords in Java, committed configuration files, or logs.

If using Spring Boot, you can configure the URL and username in the configuration file while reading the password from an environment variable:

```properties
spring.datasource.url=jdbc:mysql://localhost:3306/mysql_lab
spring.datasource.username=mysql_lab_user
spring.datasource.password=${MYSQL_LAB_PASSWORD}
```

The routine application account should only hold the DML privileges required by business logic. If the application needs to alter schemas during deployment, use a dedicated migration account in the deployment step and do not let the application grant privileges or create users during normal runtime.

## 8. Notes When Connecting from Docker or Another Machine

The host value in a MySQL account represents the connection source as seen by the server, not simply the hostname in the JDBC URL. For example, if the application runs in a Docker container while MySQL runs in another container or on another machine, `localhost` inside the application container usually points to the application container itself. It does not automatically point to MySQL.

In multi-machine or Docker environments, determine the source address seen by MySQL, then create the account with the matching host. Also verify:

- MySQL Server is listening on the network interface matching your deployment architecture.
- The firewall or network rules allow only the required application hosts to reach the MySQL port.
- The account `user` and `host` in `CREATE USER`/`GRANT` match the actual connection.
- Remote connections are protected with TLS when required by the environment and deployment policy.
- Never expose the MySQL port to the public Internet merely for practice convenience.

If a remote connection is refused, check both the account host and network configuration. Simply changing the host to `%` does not address the real root cause and can overly widen the attack surface.

## 9. Modifying and Revoking Privileges When Needed

Account privileges should be reviewed when roles change. For example, if an account no longer needs to modify data, an administrator can revoke write privileges:

```sql
REVOKE INSERT, UPDATE, DELETE
ON mysql_lab.*
FROM 'mysql_lab_user'@'localhost';
```

To change a password, use `ALTER USER` from an account with user-administration privileges:

```sql
ALTER USER 'mysql_lab_user'@'localhost'
    IDENTIFIED BY 'replace-with-a-new-unique-password';
```

When an account is no longer used, an administrator can drop the account:

```sql
DROP USER 'mysql_lab_user'@'localhost';
```

`CREATE USER`, `GRANT`, `REVOKE`, and `ALTER USER` update the privilege system through MySQL's administrative mechanism. You do not need to run `FLUSH PRIVILEGES` after these statements. `FLUSH PRIVILEGES` is mainly relevant when directly editing system grant tables, which should not be done in normal workflows.

## 10. Troubleshooting Common Errors

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `Access denied for user` on login | Wrong password, wrong account host, or incompatible authentication method | Check the `user`/`host` pair, password, `CURRENT_USER()`, and driver configuration |
| Can log in, but cannot select the database | Account has not been granted privileges on the database or wrong database name | Run `SHOW GRANTS FOR ...` using an admin account and verify the schema name |
| Can read, but cannot insert or update data | Missing `INSERT` or `UPDATE`, or privileges were granted only on another table | Check the `ON database.table` scope and listed privileges |
| Cannot create tables | Missing `CREATE` privilege on the database or connected to the wrong schema | Check `DATABASE()`, `SHOW GRANTS`, and privileges of the matched account host |
| Administrative statements are denied | The practice account lacks user/database admin privileges or `GRANT OPTION` | This is the intended outcome under least privilege; use an admin account for admin tasks |
| Java cannot connect, but CLI can | JDBC URL, driver, environment variable, or connection settings differ from CLI | Compare host, port, database, username, and the underlying error from Connector/J |

When diagnosing, distinguish connection errors from privilege errors. If a connection session has not been established yet, check network, host, password, and authentication. If connected but an SQL statement is rejected, inspect the privileges of the actual account via `CURRENT_USER()` and `SHOW GRANTS`.

## 11. Self-Practice Exercises

1. Log in with an administrative account and create the `mysql_lab` database.
2. Create the `mysql_lab_user` account with a local host, then grant the exact seven privileges from the example.
3. Log in with the practice account, run `SELECT USER(), CURRENT_USER(), DATABASE()`, and record the output.
4. Create a table, create an index, insert, and query data in `mysql_lab`.
5. Try creating a new database and dropping a table; explain why both operations are denied.
6. Use `SHOW GRANTS` to confirm the account has no global privileges and no `GRANT OPTION`.
7. Try revoking the `DELETE` privilege, verify that delete operations are denied, and then grant it back if subsequent lessons need it.
8. Configure a Java program to read data via JDBC with the password supplied from an environment variable.

You have completed this lesson when you can create an independent practice account, explain every granted privilege, demonstrate that out-of-scope operations are denied, and connect successfully from Java or the MySQL client. Keep administrative accounts for administrative work and use narrow-scope accounts for daily operations.
