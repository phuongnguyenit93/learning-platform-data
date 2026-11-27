# R2DBC URL Format and ConnectionFactoryOptions Properties

In Spring Data Relational R2DBC, `ConnectionFactory` is the entry point for obtaining a connection to the database. To create a factory, the application needs to provide information about the driver, host, port, database, credentials, and additional options. The R2DBC SPI represents this information using `ConnectionFactoryOptions`; many drivers also allow declaring it in an R2DBC URL.

The URL and `ConnectionFactoryOptions` describe the same connection configuration in two different forms. A URL is convenient for string-based configuration, while `ConnectionFactoryOptions` is suitable when you need to build configuration in Java, add typed options, or integrate with Spring configuration. Understanding the structure and scope of each option helps avoid using a JDBC URL by mistake, passing incorrect property names, or relying on a single driver's proprietary options.

## 1. What is an R2DBC URL?

An R2DBC URL is a string identifying a connection configuration according to R2DBC conventions. The URL begins with the `r2dbc:` scheme to distinguish it from other URL types, especially JDBC URLs that begin with `jdbc:`.

Example of a PostgreSQL connection URL:

```text
r2dbc:postgresql://appuser:secret@db.example.com:5432/appdb?schema=public
```

The string above specifies the PostgreSQL driver, credentials, host address, port, database, and an additional option. The specific driver parses the URL and converts the components into configuration it understands.

There is no single way to write the address portion that applies identically to every driver. Drivers may support network URLs, embedded forms, or proprietary protocols. Therefore, check the URL format of the exact driver in use rather than assuming every URL contains a host, port, and database in one uniform template.

## 2. Common Components in a URL

For drivers connecting over the network, the common form is:

```text
r2dbc:<driver>://[<user>[:<password>]@]<host>[:<port>]/<database>[?<option>=<value>&...]
```

Some components have the following meanings:

| Component | Meaning | Example |
| --- | --- | --- |
| `r2dbc:` | Scheme identifying this as an R2DBC URL | `r2dbc:` |
| `<driver>` | Name of the driver/provider to use | `postgresql`, `mariadb`, `mysql`, `h2` |
| `<user>` | Username, if the URL contains credentials | `appuser` |
| `<password>` | Password, if declared in the URL | `secret` |
| `<host>` | Hostname or IP address | `db.example.com` |
| `<port>` | Database service port | `5432` |
| `<database>` | Database name or path interpreted by the driver | `appdb` |
| `?<option>=<value>` | Driver-specific additional options | `schema=public` |

The user/password part can be placed in the URL or configured separately via `ConnectionFactoryOptions` or Spring. For real environments, it is usually best to provide credentials via external secrets/configuration to avoid writing passwords into URLs in logs, terminal history, or committed configuration files.

### Driver and protocol

The driver indicates which provider is responsible for creating the `ConnectionFactory`. The protocol part, if supported by the driver, describes how the driver connects or the type of resource to open. For example:

```text
r2dbc:postgresql://localhost:5432/appdb
r2dbc:h2:mem:///testdb
r2dbc:h2:file:///./data/testdb
```

In the PostgreSQL URL, `postgresql` is the driver and the remainder describes the network endpoint. With H2, `h2` is the driver while `mem` or `file` indicates the storage mode. An H2 URL like `mem:///testdb` has no network host; you should not try to interpret it as an ordinary server URL.

The driver name in the URL must correspond to a provider on the classpath. Writing `r2dbc:postgresql:` does not install the PostgreSQL driver automatically; the application still needs the appropriate R2DBC driver dependency.

### Host, port, and database

For network connections, host identifies the server and port identifies the service port. If the port is omitted, the driver may use its own default port. Do not assume default ports when a configuration may run against different database management systems or environments.

The database is usually placed in the path after the `/` character. The exact meaning of the path is determined by the driver. For example, `appdb` in the PostgreSQL URL is the database name. For an embedded database, the path may represent an in-memory database name or a file location.

Database and schema are two different concepts. A database identifies the database to which the connection opens; a schema is typically a namespace inside a database. With PostgreSQL, `appdb` and `public` in the example above are the database and schema, respectively. Do not substitute the schema for the database name just because both appear in connection configuration.

### Query parameters

The part after `?` contains options as name/value pairs, usually separated by `&`:

```text
r2dbc:postgresql://db.example.com:5432/appdb?schema=public&sslMode=require
```

In the example, `schema` and `sslMode` are options supported by the PostgreSQL driver in their respective versions. They are not option names you can assume work across every driver. Another driver may use different names, different value types, or not support a similar feature.

Do not treat query parameters as a universal set of properties. The R2DBC SPI provides common options; the driver/provider decides how to interpret proprietary options. When configuring TLS, timeouts, application name, default schema, or specialized features, consult the documentation for the exact driver and version in use.

## 3. URL Examples by Connection Type

### PostgreSQL over the network

```text
r2dbc:postgresql://localhost:5432/appdb
```

Credentials and driver-specific options can be added:

```text
r2dbc:postgresql://appuser:secret@localhost:5432/appdb?schema=public
```

If credentials are separated out into Spring configuration, the URL can contain only the endpoint and database:

```text
r2dbc:postgresql://localhost:5432/appdb
```

### In-memory H2

```text
r2dbc:h2:mem:///testdb
```

This is a common example for development or testing environments. The lifecycle of data in an in-memory database depends on how the driver and H2 configuration manage the database; do not assume by default that data persists across every connection or after the application terminates.

### File-based H2

```text
r2dbc:h2:file:///./data/testdb
```

The file path is interpreted by the H2 driver. Check the working directory, read/write permissions, and the URL rules for the driver version. A relative path may point to different locations when the application is run from an IDE, Gradle, or a deployment environment.

### Connecting through R2DBC Pool

If the application uses R2DBC Pool, the pool library may provide a `ConnectionFactory` wrapper around the underlying driver. Some configurations use a URL form with the `pool` prefix, for example:

```text
r2dbc:pool:postgresql://localhost:5432/appdb
```

This is a form supported by the pool provider, not a prefix that every driver understands. You need the pool dependency and proper configuration for the pool provider to create a factory wrapping the PostgreSQL factory. Pool size and timeout options also depend on the pool library and should not be confused with common database driver options.

## 4. URL Encoding and Special Characters

R2DBC URLs follow URI component-splitting rules. Certain characters have structural meaning: `@` separates user information from the host, `:` separates username/password or host/port, `/` separates paths, `?` begins the query string, `&` separates query parameters, and `#` starts a fragment.

If a user, password, database name, or option value contains characters with structural meaning, that value must be percent-encoded according to URI rules and the driver's rules. For example, a password containing `@` should not be inserted verbatim into the user information section because the parser may misinterpret it as the boundary before the host.

Illustrative examples of encoding forms:

| Character in data | Percent-encoded form |
| --- | --- |
| space | `%20` |
| `@` | `%40` |
| `:` | `%3A` |
| `/` | `%2F` |
| `?` | `%3F` |
| `&` | `%26` |
| `#` | `%23` |

Do not concatenate unencoded passwords into a URL manually. If using a URI-building library, pass each component through the corresponding API so the library encodes each position properly. Also check how the driver decodes components, as the driver's parser may have its own rules.

For IPv6 addresses, the host part in the authority usually needs to be enclosed in square brackets, such as `[2001:db8::10]`, so that `:` characters inside the address are not mistaken for the port separator.

## 5. What is `ConnectionFactoryOptions`?

`io.r2dbc.spi.ConnectionFactoryOptions` is an immutable configuration object in the R2DBC SPI. It holds option-and-value pairs that a provider uses to create a `ConnectionFactory`.

Each option is represented by an `Option<T>`, where `T` indicates the value's data type. For example, port is an integer, SSL is a boolean, and host and database are typically strings. This typed representation helps applications avoid handling all configuration as a URL string.

Key related classes:

| Type | Role |
| --- | --- |
| `ConnectionFactoryOptions` | Holds the complete set of options to create a factory |
| `ConnectionFactoryOptions.Builder` | Builds the option set via `option(...)` calls |
| `Option<T>` | Identifies an option and its corresponding value type |
| `ConnectionFactories` | Locates a matching provider and creates a `ConnectionFactory` |
| `ConnectionFactoryProvider` | SPI implemented by a driver/provider to support options and create a factory |

`ConnectionFactoryOptions` does not open sockets or execute SQL itself. It only describes configuration. `ConnectionFactories.get(...)` uses that set of options to find a matching `ConnectionFactoryProvider`, and then the provider creates the actual factory.

## 6. Common Shared Options

The R2DBC SPI defines common options so drivers can share a unified way of representing configuration. Typical core options include:

| Option constant | Common value type | Meaning |
| --- | --- | --- |
| `DRIVER` | `String` | Driver/provider name, such as `postgresql` or `h2` |
| `PROTOCOL` | `String` | Protocol or connection mode interpreted by the driver, if applicable |
| `HOST` | `String` | Database server host |
| `PORT` | `Integer` | Connection port |
| `USER` | `String` | Username |
| `PASSWORD` | `CharSequence` | Password or character-sequence credentials |
| `DATABASE` | `String` | Database or database resource per the driver |
| `SSL` | `Boolean` | Enable/disable SSL/TLS support at the common option level |

These are common options for understanding connection configuration; the exact set of options depends on the R2DBC SPI and provider versions. Not every common option is supported by every driver in the same way. For example, `SSL=true` only expresses a general intent to enable SSL; certificate verification mode, trust store, client certificates, or detailed TLS policies may require driver-specific options.

In addition to common options, drivers may define proprietary options for default schema, application name, timeouts, SSL modes, sockets, or specialized features. Consult the driver documentation for their names, data types, valid values, and defaults.

## 7. Building `ConnectionFactoryOptions` in Java

You can create options with `ConnectionFactoryOptions.builder()` and call `option(key, value)` for each property. PostgreSQL example:

```java
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactoryOptions;
import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.Option;

import static io.r2dbc.spi.ConnectionFactoryOptions.*;

ConnectionFactoryOptions options = ConnectionFactoryOptions.builder()
        .option(DRIVER, "postgresql")
        .option(HOST, "localhost")
        .option(PORT, 5432)
        .option(DATABASE, "appdb")
        .option(USER, "appuser")
        .option(PASSWORD, "secret")
        .build();

ConnectionFactory connectionFactory = ConnectionFactories.get(options);
```

`DRIVER` helps `ConnectionFactories` determine which provider to use. The remaining options supply the endpoint and login credentials. The driver must be on the classpath and must support the options passed.

In this example the password is for illustration only. Real applications should read secrets from the deployment environment or a secret manager. Do not write real credentials into source code, logs, or repositories.

### Adding driver-specific options

When a driver has proprietary options, you can use the `Option` constants provided by the driver or create an option with `Option.valueOf(...)` if the API requires it:

```java
ConnectionFactoryOptions options = ConnectionFactoryOptions.builder()
        .option(DRIVER, "postgresql")
        .option(HOST, "localhost")
        .option(PORT, 5432)
        .option(DATABASE, "appdb")
        .option(USER, "appuser")
        .option(PASSWORD, "secret")
        .option(Option.valueOf("schema"), "public")
        .build();
```

In the example, `schema` is a proprietary option depending on the PostgreSQL driver's capabilities and version in use. `Option.valueOf("schema")` only creates an option key; it does not make the driver automatically support that feature. If the option name is wrong or the provider does not recognize the option, factory creation may be rejected or the option may have no effect depending on provider behavior.

Prefer option constants published by the driver when available, because those constants clearly express the name and data type the driver expects. If using `Option.valueOf`, verify the exact name and value type in the driver documentation.

### Creating a factory from a URL

When you already have a valid URL and the corresponding driver on the classpath, the `ConnectionFactories` API can accept a URL to create a factory:

```java
ConnectionFactory connectionFactory = ConnectionFactories.get(
        "r2dbc:postgresql://localhost:5432/appdb"
);
```

In this approach, the URL is parsed into configuration so a matching provider can create the factory. If the application needs to add options or prefers Java-based configuration, you can build `ConnectionFactoryOptions` directly and pass it to `ConnectionFactories.get(options)`.

Both approaches lead to a `ConnectionFactory`. Choosing which one to use depends on where configuration is stored, secret management requirements, the number of options, and how much type control is needed.

## 8. Relationship Between URL and ConnectionFactoryOptions

A URL can be viewed as a string representation of configuration; `ConnectionFactoryOptions` is the typed configuration model used by the provider. High-level flow:

```mermaid
flowchart TD
    A["R2DBC URL"] --> C["Parse into ConnectionFactoryOptions"]
    B["Java Builder / Spring configuration"] --> C
    C --> D["ConnectionFactories.get(options)"]
    D --> E["Find matching ConnectionFactoryProvider"]
    E --> F["Driver or pool provider"]
    F --> G["ConnectionFactory"]
```

For example, the same PostgreSQL configuration can be represented as a URL:

```text
r2dbc:postgresql://localhost:5432/appdb
```

Or in Java:

```java
ConnectionFactoryOptions options = ConnectionFactoryOptions.builder()
        .option(DRIVER, "postgresql")
        .option(HOST, "localhost")
        .option(PORT, 5432)
        .option(DATABASE, "appdb")
        .build();
```

When using a URL, the provider's parser converts the parts into the corresponding options. When using the builder, the application sets each option directly. For proprietary options, the name and URL encoding are defined by the driver; the Java form must provide the exact `Option` and value type supported by the driver.

Do not assume every query parameter in a URL has a corresponding `ConnectionFactoryOptions` constant in the SPI. Some options are driver extensions. Nor should you assume an option with the same name in two drivers has the same type, default, or semantics.

## 9. Configuration in Spring Boot

In a Spring Boot application, you usually do not need to call `ConnectionFactories.get(...)` manually. Spring Boot can create a `ConnectionFactory` bean from R2DBC configuration and supply it to `DatabaseClient`, `R2dbcEntityTemplate`, and repositories.

Example YAML configuration with PostgreSQL:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/appdb
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    properties:
      schema: public
```

`url` identifies the driver and endpoint. `username` and `password` are declared separately to avoid putting secrets into the URL. Additional properties under `properties` are forwarded according to Spring Boot's and the provider's configuration mechanism; the names and types must match the driver in use. Check the Spring Boot documentation for your project's version to confirm which properties are supported.

When configured with environment variables, the application can use the same artifact across multiple environments:

```yaml
spring:
  r2dbc:
    url: ${R2DBC_URL}
    username: ${R2DBC_USERNAME}
    password: ${R2DBC_PASSWORD}
```

Example value of `R2DBC_URL` in a development environment:

```text
r2dbc:postgresql://localhost:5432/appdb
```

In test or production environments, simply provide the corresponding endpoint and secrets via deployment configuration. Do not commit real passwords into `application.yml`.

If the application configures multiple `ConnectionFactory` instances manually or uses a custom pool, explicitly declare which factory is used for `DatabaseClient` and the transaction manager. Having the right URL configuration but wiring the wrong factory can still cause repositories to connect to a different database than expected.

## 10. Distinguishing Common Options from Driver-Specific Options

A common mistake is treating every connection property as part of the R2DBC standard. In practice, three groups should be distinguished:

| Group | Examples | Where meaning is defined |
| --- | --- | --- |
| Common SPI options | `DRIVER`, `HOST`, `PORT`, `USER`, `PASSWORD`, `DATABASE`, `SSL` | R2DBC SPI and provider |
| Driver-specific options | `schema`, `sslMode`, application name, or specific timeouts | Driver documentation and driver version |
| Pool options | pool size, connection borrow wait time, idle time | R2DBC Pool or active pool provider documentation |

For example, `PORT` describes the connection port and is a common option. A property like `sslMode=require` may be understood by the PostgreSQL driver, while another driver may use a different option. Similarly, `maxSize` is a pool configuration concept; you should not pass it to the database driver and expect the driver to manage a pool on its own.

When reading documentation or examples on the Internet, identify which group an option belongs to and which driver/version the example was written for. Copying a query string verbatim from one driver to another can create an invalid configuration or cause certain features to be silently ignored.

## 11. Common Configuration Errors

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Provider not found | Missing driver dependency or wrong `DRIVER` name | Check runtime dependencies and the driver name in URL/options |
| URL cannot be parsed | Wrong scheme or syntax unsupported by the driver | Check the `r2dbc:` prefix and URL examples for the exact driver |
| Cannot connect to host | Wrong hostname, port, DNS, firewall, or database not listening | Check the endpoint from the application's runtime environment |
| Authentication failed | Wrong username/password or unencoded special characters | Check secrets and how user information is passed |
| Cannot open database | Wrong database name or path in embedded mode | Check the path meaning in the driver's URL format |
| Option rejected | Wrong option name or option belonging to another driver | Cross-check option name and data type in driver documentation |
| SSL does not behave as expected | Confusing common `SSL` option with driver-specific TLS mode | Check certificate, trust, and SSL mode requirements of the driver |
| Connected to wrong database | Wrong URL or miswired `ConnectionFactory` bean | Check effective configuration and injected bean |
| Pool has no effect | Missing pool provider or pool configuration not enabled | Check pool dependency and application pool configuration mechanism |

When investigating, verify in order that the driver is loaded, the URL/options are parsed properly, the endpoint is reachable, credentials are valid, and proprietary options are accepted by the provider. If you need to log configuration for diagnostics, mask passwords, tokens, and sensitive information before logging.

## 12. Guidelines for Choosing a Configuration Approach

**Use an R2DBC URL** when configuration is concise, consists mainly of driver and endpoint, and the URL is managed safely in environment configuration. URLs are easy to pass via environment variables or deployment configuration.

**Use the `ConnectionFactoryOptions` builder** when you need to create a factory in Java, configure dynamically, add typed options, or integrate with provider-selection logic. This approach also makes each component clear instead of concatenating a URL string.

**Use Spring Boot configuration** when the application runs in the Spring Boot ecosystem and only needs one or a few configured factories. Letting Spring manage the bean ensures `DatabaseClient`, templates, and repositories share a consistent configuration.

Whichever approach you choose, keep credentials out of source code, use the right driver, distinguish SPI options from driver-specific options, and verify documentation against the actual dependency version. An R2DBC configuration only takes effect when the corresponding provider understands and applies the options passed to it.

## 13. Key Takeaways

- R2DBC URLs begin with `r2dbc:`; do not use a JDBC URL (`jdbc:`) for an R2DBC driver.
- The driver name determines the provider; some drivers also have specific protocols or connection modes such as `mem` and `file`.
- For network URLs, host, port, and database usually reside in the authority/path; the query string holds additional driver-specific options.
- Database and schema serve different roles. Not every query parameter is a common R2DBC SPI option.
- `ConnectionFactoryOptions` is an immutable, typed configuration built using `ConnectionFactoryOptions.builder()` and `option(...)` calls.
- `ConnectionFactories.get(...)` selects a matching provider to create a `ConnectionFactory`; the driver must be on the runtime classpath.
- Use common options such as `DRIVER`, `HOST`, `PORT`, `USER`, `PASSWORD`, `DATABASE`, and `SSL` with the proper types; proprietary options must follow driver documentation.
- Special characters in a URL must be percent-encoded in the appropriate position. Do not put real secrets in URLs that are logged or committed.
- Connection pool options belong to the pool provider configuration and are not equivalent to database driver options.
- In Spring Boot, you can declare URL, username, password, and additional properties via `spring.r2dbc.*` configuration; verify against the exact Boot and driver versions.

When diagnosing an R2DBC connection, break the URL into its individual components, map them to `ConnectionFactoryOptions`, and identify which provider is responsible for interpreting each option. This approach helps separate URL syntax errors, missing driver errors, endpoint errors, and unsupported proprietary option errors.
