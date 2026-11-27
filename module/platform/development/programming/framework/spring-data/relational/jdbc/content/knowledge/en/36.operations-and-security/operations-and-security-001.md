# Enabling SQL Logs, Bind Logs, and Protecting Sensitive Data

When operating a **Spring Data Relational JDBC** application, SQL logs help identify causes of slow queries, incorrect column names, mapping errors, or unexpected numbers of generated statements. Two types of information must be distinguished:

- **SQL log:** records the SQL statement being executed, usually keeping placeholders such as question marks or named parameters.
- **Bind log:** records the actual values bound to each placeholder, which may include emails, phone numbers, tokens, addresses, payment data, or other personal information.

In Spring JDBC, you can enable SQL logging at the DEBUG level and bind value logging at the TRACE level of `StatementCreatorUtils`. If the application uses MyBatis, you can enable loggers by mapper namespace or statement. These configurations are useful during debugging, but bind logs carry a high risk of data exposure. **Enable them only for the required scope and duration, and keep sensitive value logging disabled in production.**

This lesson explains how to enable SQL logs and bind logs for Spring Data JDBC, configure MyBatis, choose narrow-scoped loggers, use dedicated profiles, read logs properly, and protect sensitive data in logs.

## 1. How Do SQL Logs and Bind Logs Differ?

Suppose a repository runs the query:

~~~sql
SELECT id, email, status
FROM customer
WHERE email = ?
  AND status = ?;
~~~

The SQL log might show:

~~~text
Executing prepared SQL statement
[SELECT id, email, status FROM customer WHERE email = ? AND status = ?]
~~~

It helps identify which statement ran, which tables/columns were accessed, and what the condition structure looks like.

The bind log might show:

~~~text
Setting SQL statement parameter value:
column index 1, parameter value [alice@example.com],
value class [java.lang.String], SQL type 12

Setting SQL statement parameter value:
column index 2, parameter value [ACTIVE],
value class [java.lang.String], SQL type 12
~~~

Bind logs help confirm that the application passes the right values and data types. However, they also reveal the actual input data.

| Log type | Commonly seen information | Risk |
| --- | --- | --- |
| SQL log | SQL text, table/column names, placeholders | Exposes schema structure and query logic |
| Bind log | Actual values, Java type, JDBC type, parameter position | May expose PII, secrets, tokens, and business data |
| Result log | Row counts or result data depending on framework/logger | May expose database contents |
| Timing log | Execution time, row count, errors | Usually less sensitive, but still requires control |

SQL logs and bind logs should be enabled independently. In many situations, the SQL text along with execution time is enough to investigate without logging bind values.

## 2. Enabling SQL Logs for Spring Data JDBC

Spring Data JDBC uses Spring JDBC at the execution layer. `JdbcTemplate` logs SQL statements at the DEBUG level under the template class's logger category.

In `application-local.yml`:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core.JdbcTemplate: DEBUG
~~~

Or in `application.properties`:

~~~properties
logging.level.org.springframework.jdbc.core.JdbcTemplate=DEBUG
~~~

Once enabled, logs usually show the query or update being executed and the SQL text with placeholders. `NamedParameterJdbcTemplate` uses the underlying Spring JDBC infrastructure; depending on the version and execution path, SQL is logged via the `JdbcTemplate` logger or related classes in the `org.springframework.jdbc.core` package.

### 2.1. Enabling a Broader Package Logger

If you need more information about JDBC core:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core: DEBUG
~~~

A broader package configuration can generate more logs. Start with a specific logger and expand only when needed.

Do not set the root logger to DEBUG just to view SQL. Doing so can generate massive amounts of logs from web, security, framework, and other libraries.

## 3. Enabling Bind Logs for Spring JDBC

Spring Framework provides the logger:

~~~text
org.springframework.jdbc.core.StatementCreatorUtils
~~~

This class prepares values for `PreparedStatement`. When TRACE is enabled, it can log:

- The parameter position in the statement.
- The parameter value.
- The Java class of the value.
- The SQL type used for binding.

Configuration:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core.JdbcTemplate: DEBUG
    org.springframework.jdbc.core.StatementCreatorUtils: TRACE
~~~

Or:

~~~properties
logging.level.org.springframework.jdbc.core.JdbcTemplate=DEBUG
logging.level.org.springframework.jdbc.core.StatementCreatorUtils=TRACE
~~~

Example log:

~~~text
DEBUG JdbcTemplate - Executing prepared SQL statement
  [SELECT id FROM customer WHERE email = ?]

TRACE StatementCreatorUtils - Setting SQL statement parameter value:
  column index 1, parameter value [alice@example.com],
  value class [java.lang.String], SQL type 12
~~~

This is why bind logs must be treated as sensitive data: values are written directly into log messages. If parameters contain passwords, access tokens, refresh tokens, account numbers, emails, or personal information, logs can become a copy of that data.

### 3.1. Bind Logs Are Not Always SQL with Replaced Placeholders

Spring JDBC typically writes the SQL and bind values in two separate log messages. You need to match them by execution order and parameter position.

For example:

~~~sql
UPDATE customer
SET status = ?, updated_at = ?
WHERE id = ?;
~~~

Bind log:

~~~text
index 1 -> ACTIVE
index 2 -> 2026-11-13T10:15:00
index 3 -> 42
~~~

When investigating, match the parameter order accurately. Do not infer values from the field order in a Java object if the query has expressions or conditionally bound parameters.

### 3.2. Nulls and JDBC Types

For null values, bind logs can record the parameter value as null along with the corresponding SQL type. If the database reports a data type error, examine both the SQL type and the Java type. Looking at the null string alone is not enough to know which SQL type the driver used to bind NULL.

## 4. Enabling SQL and Parameter Logs for MyBatis

If a Spring Data JDBC application uses MyBatis integration or standalone MyBatis mappers, logs are categorized by mapper namespace or statement ID.

Example namespace:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <select id="findById" resultMap="purchaseOrderMap">
        SELECT id, order_number, status
        FROM purchase_order
        WHERE id = #{id}
    </select>
</mapper>
~~~

You can enable the logger for the mapper:

~~~yaml
logging:
  level:
    com.example.orders.PurchaseOrderMapper: DEBUG
~~~

Or enable it for a specific statement:

~~~yaml
logging:
  level:
    com.example.orders.PurchaseOrderMapper.findById: TRACE
~~~

MyBatis supports logging by package, mapper namespace, or full statement name. Typically DEBUG displays the prepared SQL statement and parameter list; TRACE may display additional result details.

Example MyBatis log:

~~~text
==> Preparing: SELECT id, order_number, status
              FROM purchase_order WHERE id = ?
==> Parameters: 42(Long)
<== Total: 1
~~~

The parameter list can contain actual values. Therefore, enabling a mapper logger at DEBUG should also be treated as an action that can expose data, depending on the MyBatis version and logging configuration.

### 4.1. Choosing the Logging Implementation

MyBatis has an internal log factory and can automatically choose an implementation based on libraries on the classpath. In a Spring Boot application using SLF4J/Logback, you can explicitly configure MyBatis to use SLF4J if auto-detection picks a different implementation.

In `mybatis-config.xml`:

~~~xml
<configuration>
    <settings>
        <setting name="logImpl" value="SLF4J"/>
    </settings>
</configuration>
~~~

If using `SqlSessionFactoryBean`, load the corresponding MyBatis configuration file. With the MyBatis Spring Boot starter, you can configure the `mybatis.configuration.log-impl` property according to the starter version in use.

There is no need to force `logImpl` if auto-detection already picks the right logging framework and logs work as expected.

### 4.2. Choosing the Logger Namespace

Instead of enabling all of `org.apache.ibatis`, you can enable specific mappers:

~~~yaml
logging:
  level:
    com.example.orders.PurchaseOrderMapper: DEBUG
    com.example.catalog.ProductMapper: INFO
~~~

This limits logs to the module under investigation. Once resolved, return the logger to an appropriate level to avoid continuing to log parameter values.

## 5. Configuring Logs by Profile

Bind logging should not be enabled in the default configuration shared across all environments. Place it in a local or time-bound debug profile.

Example `application.yml`:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.jdbc.core.JdbcTemplate: INFO
    org.springframework.jdbc.core.StatementCreatorUtils: OFF
~~~

Example `application-local.yml`:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core.JdbcTemplate: DEBUG
    org.springframework.jdbc.core.StatementCreatorUtils: TRACE
~~~

Run locally using an environment variable:

~~~text
SPRING_PROFILES_ACTIVE=local
~~~

When the local profile is not active, the bind logger remains off. Depending on the environment configuration, profiles can be selected via environment variables, command line, or deployment configuration.

### 5.1. Using a Temporary Debug Profile

If you need to investigate in a staging environment:

1. Create a dedicated debug configuration.
2. Enable loggers only for the relevant mapper/repository.
3. Limit the duration it is enabled.
4. Use sanitized test data.
5. Confirm logs are stored in a location with restricted access.
6. Disable the configuration after collecting sufficient evidence.

Never allow a debug profile to become the default production configuration.

### 5.2. Do Not Commit Sensitive Data with Configuration

Configuration files should only contain logger categories and levels. Do not put passwords, API keys, tokens, connection strings with credentials, or real data into source control, log messages, or debug scripts.

## 6. Protecting Sensitive Data in Logs

Bind logging can write raw parameter values. Fields that must be treated as sensitive include:

- Passwords, PINs, secrets, and API keys.
- Access tokens, refresh tokens, session IDs, and cookies.
- Card numbers, account details, or payment data.
- Emails, phone numbers, addresses, and personal identifiers.
- Message contents, private notes, or health data.
- Payloads containing customer information or internal data.

Even when a value is not a secret, it may still be personal data or business data requiring restricted access.

### 6.1. Do Not Enable TRACE Bind Logging in Production

Safety principles:

- Keep `StatementCreatorUtils` at OFF or a level that does not log parameter values in production.
- Only enable SQL DEBUG when there is a clear operational need and the SQL contents have been evaluated.
- Do not enable TRACE for an entire mapper package unnecessarily.
- Do not use root DEBUG/TRACE to investigate a single query.
- Turn off debug loggers once the investigation is complete.

When investigating production issues, prefer logging sanitized metadata: operation name, query identifier, elapsed time, row count, SQLState, vendor error code, and trace ID.

### 6.2. Masking and Allowlisting

If your organization needs to log partial parameters for investigation, use a logging mechanism capable of masking or allowlisting:

- Log only approved fields.
- Mask values such as email, phone, and account number.
- Never log passwords/tokens even if partially masked.
- For identifiers needed for correlation, consider a salted hash or pseudonymous ID compliant with policy.
- Do not log entire DTOs or request JSON using `toString()`.

Masking must happen before logs are written to the appender. Redacting data after logs have already been sent to a centralized system does not eliminate the original copy.

### 6.3. Do Not Manually Log PreparedStatements with Values

Do not manually write:

~~~java
log.debug("Executing query with customer data: {}", customer);
~~~

or:

~~~java
log.debug("SQL={}, parameters={}", sql, parameters);
~~~

if `customer` or `parameters` may contain sensitive data. Log a query identifier and selected metadata instead.

### 6.4. Be Cautious with P6Spy and datasource-proxy

Tools like P6Spy or datasource-proxy can log SQL and parameters at the DataSource layer, which is useful when you want to observe multiple JDBC execution paths. However, they can also log sensitive values or generate very large log volumes.

Before enabling them:

- Check the formatter and masking capabilities.
- Identify which logger/appender receives the output.
- Restrict packages, queries, or environments.
- Evaluate overhead and performance impact.
- Do not assume the tool masks data safely by default.

Do not use placeholder-substitution features to generate copy-pasteable SQL in production without masking policies and access controls in place.

## 7. Logging SQL Errors Without Exposing Parameters

When a query fails, logs should help operators identify the error without recording the entire input data.

Commonly useful information:

- Operation name or statement ID.
- Repository/mapper name.
- Trace ID or correlation ID.
- Execution duration.
- Expected row count or affected row count, if available.
- Spring exception type.
- SQLState and vendor error code.
- Constraint/index name if provided by the exception and logging it does not expose data.

Example:

~~~java
try {
    repository.save(order);
} catch (DataAccessException ex) {
    log.error(
            "Failed to persist order; operation=createOrder, traceId={}",
            traceId,
            ex
    );
    throw ex;
}
~~~

Do not append `order.toString()` or the request body to exception logs if the object may contain customer data. The exception stack trace is usually enough to identify the error class; parameter values should be inspected in a safe environment using sanitized data.

## 8. Reading Logs to Investigate Issues

### 8.1. Query Not Running as Expected

Check:

1. Does the SQL text match the intended statement?
2. Are table/column aliases correct?
3. Is any WHERE condition missing?
4. Does the number of placeholders match the number of parameters?
5. Does the JDBC type match the column type?
6. Is there any unexpected conversion or null binding?

With Spring JDBC, pair DEBUG SQL logs with bind logs for a short period in local/test environments to pinpoint wrong parameters.

### 8.2. Slow Queries

SQL logs help identify the statement, but do not explain the cause of slowness by themselves. You also need to inspect:

- Execution time.
- Number of rows returned or updated.
- Indexes and execution plan.
- Lock waits, blocking sessions, and the connection pool.
- Result set size.
- Number of queries generated within a use case.

There is no need to enable bind logs if the issue only involves execution plans and indexes. You can use the query ID and sanitized test data for analysis.

### 8.3. More Queries Than Expected

If reading an aggregate once produces many SQL statements, check relation mappings, child collections, and how the service accesses the repository. SQL logs can reveal an N+1 pattern or repeated aggregate loading. Do not use real bind values if you only need to count the number of queries.

## 9. Log Configuration in YAML and Properties

A consolidated local configuration:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.jdbc.core.JdbcTemplate: DEBUG
    org.springframework.jdbc.core.StatementCreatorUtils: TRACE
    com.example.orders.PurchaseOrderMapper: DEBUG
    com.example.catalog.ProductMapper: INFO
~~~

Properties equivalent:

~~~properties
logging.level.root=INFO
logging.level.org.springframework.jdbc.core.JdbcTemplate=DEBUG
logging.level.org.springframework.jdbc.core.StatementCreatorUtils=TRACE
logging.level.com.example.orders.PurchaseOrderMapper=DEBUG
logging.level.com.example.catalog.ProductMapper=INFO
~~~

This is an example for local/debug environments. Before using it, verify the actual mapper namespaces and logging implementation. In production, turn off TRACE bind values and enable only narrow-scoped SQL loggers when needed.

### 9.1. Logging Levels

| Level | Common usage |
| --- | --- |
| ERROR | Errors requiring attention |
| WARN | Abnormal situations where the application continues running |
| INFO | Important operational events |
| DEBUG | SQL text, technical flows, or debugging details |
| TRACE | Parameter values and very deep execution details |

The exact meaning of each logger depends on the library. Do not assume TRACE only logs metadata; `StatementCreatorUtils` can log actual bind values.

## 10. Protecting Logs at the Operational Layer

Even when the application masks parameters, logs must still be protected like a data store:

- Restrict log read permissions by role.
- Use TLS when shipping logs to a centralized system.
- Encrypt logs at rest if required by policy.
- Configure retention and delete logs on schedule.
- Do not paste sensitive logs into tickets, chats, or uncontrolled reports.
- Review observability vendor access permissions.
- Monitor logger configuration changes in production.
- Ensure logs do not contain user-supplied data that could cause log injection or forge log lines.

Logs can be copied to many places: local files, container stdout, collectors, SIEM, APM, and backups. Deleting one copy does not guarantee that other copies are deleted as well.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Enabling DEBUG on the root logger to view SQL | Too many logs, hard to find queries | Enable a specific JDBC or mapper logger |
| Enabling only JdbcTemplate DEBUG and expecting bind values | SQL logs usually keep placeholders | Enable StatementCreatorUtils TRACE only when truly needed |
| Leaving TRACE bind logs on long-term | Exposes PII, tokens, or payment data | Turn off in production, enable temporarily in a safe environment |
| Assuming SQL logs and bind logs are the same | Missing parameter info or misjudging risk | Separate the two log types |
| Enabling MyBatis logging with no output | Incorrect log implementation or namespace | Check logImpl and mapper logger |
| Enabling TRACE on all of org.apache.ibatis | Logs too many statements/results | Choose a specific namespace or statement |
| Logging entire DTOs/requests | May expose sensitive data | Log allowlisted metadata |
| Using P6Spy without configuring masking | Logs SQL with real values | Check formatter, filters, and retention |
| Including SQL parameters in exception messages | Sensitive data appears in error logs | Log operation ID, SQLState, and trace ID |
| Enabling debug logs in shared application.yml | Production accidentally receives debug settings | Place them in a separate local/debug profile |
| Relying solely on SQL logs to diagnose slow queries | Misses execution plans or lock waits | Use database monitoring and execution plans |

## 12. Safe Workflow for Enabling Debug Logs

When investigating a JDBC issue:

1. **Identify the query/mapper:** find the relevant repository method, logger category, or namespace.
2. **Enable scoped SQL DEBUG:** prefer `JdbcTemplate` or a specific mapper.
3. **Check whether data is sensitive:** determine if the query binds PII, secrets, or payment data.
4. **Enable bind TRACE only when necessary:** use local/staging with dummy or sanitized data.
5. **Collect minimal logs:** query text, types, SQLState, timing, and trace ID.
6. **Analyze the results:** check placeholders, JDBC types, nulls, indexes, and execution plans.
7. **Turn off debug loggers:** restore appropriate log levels after investigating.
8. **Handle generated logs:** store in a controlled location, follow retention policies, and delete unnecessary copies.
9. **Document the root cause:** use the query ID/operation name and sanitized descriptions without attaching real parameters.

## Takeaways

In Spring Data JDBC, `JdbcTemplate` SQL is typically logged at DEBUG via the `org.springframework.jdbc.core.JdbcTemplate` logger. `PreparedStatement` bind values can be logged at TRACE via `org.springframework.jdbc.core.StatementCreatorUtils`. With MyBatis, you can enable loggers by mapper namespace or statement; DEBUG generally shows the SQL and parameter list, while TRACE can add result details.

SQL logs and bind logs are two distinct types of information. SQL text with placeholders helps locate the statement; bind logs show actual values but may contain PII, tokens, passwords, or payment data. Enable logging via local/debug profiles, scope loggers narrowly, enable bind TRACE only in safe environments, and disable it after investigating. In production, favor operation IDs, trace IDs, durations, row counts, SQLState, and sanitized error details. Protect logs with masking/allowlisting, access controls, encryption, and proper retention; never treat logs as a storage location for business data.

## References

- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Framework — JDBC core classes](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework — StatementCreatorUtils source](https://github.com/spring-projects/spring-framework/blob/main/spring-jdbc/src/main/java/org/springframework/jdbc/core/StatementCreatorUtils.java)
- [MyBatis — Logging](https://mybatis.org/mybatis-3/logging.html)
- [MyBatis — Configuration settings](https://mybatis.org/mybatis-3/configuration.html)
