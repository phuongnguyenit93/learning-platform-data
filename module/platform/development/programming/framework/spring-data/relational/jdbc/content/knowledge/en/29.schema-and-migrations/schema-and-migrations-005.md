# Generating Liquibase Change Sets with LiquibaseChangeSetWriter in Spring Data JDBC

## 1. Role of LiquibaseChangeSetWriter

Spring Data JDBC provides `LiquibaseChangeSetWriter` to generate Liquibase change sets from aggregate mapping metadata. The class resides in the package:

~~~java
org.springframework.data.jdbc.core.mapping.schema.LiquibaseChangeSetWriter
~~~

The writer reads `MappingContext` to identify mapped entities and their corresponding table/column structures. It supports two modes:

1. **Initial schema creation:** generates change sets describing an initial schema for an empty database.
2. **Differential schema change creation:** compares the desired schema from entity mappings against the existing schema of a Liquibase `Database` and generates change sets describing the difference.

The writer produces a changelog for the development team to review and manage with Liquibase. It does not apply migrations to the database itself. Generating the file and executing migrations are two separate steps.

`LiquibaseChangeSetWriter` was introduced in Spring Data Relational 3.2. When using older versions, check the corresponding API because the class or methods may not exist yet.

API documentation: https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/mapping/schema/LiquibaseChangeSetWriter.html

## 2. How the Writer Derives Schema from the Domain Model

Spring Data JDBC uses `RelationalMappingContext` to store metadata about aggregates and relational mappings. This metadata includes information such as:

- Aggregate root types and mapped entities.
- Table names from `@Table` or default naming rules.
- Column names from properties and `@Column`.
- Identifiers from `@Id`.
- Java types of properties to derive SQL types.
- Other relational mapping metadata supported by the schema writer.

The writer does not scan the entire Java codebase to discover every class automatically. It uses entities already registered in `MappingContext`. The mapping context is often populated lazily; when generating a schema, ensure the desired aggregate roots have been registered in the context.

Example entity:

~~~java
import java.time.LocalDate;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("customer_code")
    private String code;

    private String displayName;

    private LocalDate birthday;

    private boolean active;
}
~~~

The writer can derive a `customers` table with columns such as `id`, `customer_code`, `display_name`, `birthday`, and `active`. Exact SQL types depend on `SqlTypeMapping` and the target database/dialect.

### 2.1. Registering Aggregate Roots

If the context does not yet know about the aggregate roots, register the set of entities for schema generation:

~~~java
import java.util.Set;

import org.springframework.data.relational.core.mapping.RelationalMappingContext;

mappingContext.setInitialEntitySet(Set.of(
        Customer.class,
        PurchaseOrder.class,
        Product.class
));
~~~

Include in this set the actual aggregate roots belonging to the managed schema. If you register only `Customer.class`, the writer cannot automatically discover other independent aggregates unknown to the context.

If the application already configures the mapping context with an initial entity set, ensure that set covers all aggregates that belong in the changelog. Do not include DTO classes, projections, or service-layer-only objects in the schema if they are not relational entities.

## 3. Required Dependencies

`LiquibaseChangeSetWriter` integrates with Liquibase, so the project needs the `liquibase-core` dependency.

Gradle, if using the writer only in tests to generate changelogs:

~~~groovy
dependencies {
    testImplementation("org.liquibase:liquibase-core")
}
~~~

If the application also executes Liquibase migrations on startup, the dependency must be available at runtime, typically using `implementation` or a configuration matching your project conventions:

~~~groovy
dependencies {
    implementation("org.liquibase:liquibase-core")
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.liquibase</groupId>
    <artifactId>liquibase-core</artifactId>
</dependency>
~~~

When using Spring Boot dependency management, let the BOM manage compatible versions rather than picking an arbitrary Liquibase version manually. Ensure the Spring Data JDBC and Liquibase versions in your project are compatible.

## 4. Generating Change Sets for an Initial Schema

Initial mode fits starting a project or creating a schema for an empty database. The constructor takes a `MappingContext`, and you then call `writeChangeSet(Resource)`.

Example usage in a test:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.FileSystemResource;
import org.springframework.data.relational.core.mapping.RelationalMappingContext;
import org.springframework.data.jdbc.core.mapping.schema.LiquibaseChangeSetWriter;

@SpringBootTest(properties = "spring.liquibase.enabled=false")
class SchemaGenerationTest {

    @Autowired
    RelationalMappingContext mappingContext;

    @Test
    void generateInitialSchema() throws IOException {
        mappingContext.setInitialEntitySet(Set.of(
                Customer.class,
                PurchaseOrder.class
        ));

        LiquibaseChangeSetWriter writer =
                new LiquibaseChangeSetWriter(mappingContext);

        Path output = Path.of(
                "build/generated/liquibase/initial-schema.yaml"
        );

        Files.createDirectories(output.getParent());

        // Use a separate generated file; the writer may append to an existing file.
        Files.deleteIfExists(output);
        Files.createFile(output);

        writer.writeChangeSet(
                new FileSystemResource(output.toFile())
        );
    }
}
~~~

In the example, `spring.liquibase.enabled=false` simply prevents Spring Boot from automatically running Liquibase inside the context used to generate the changelog. This is an appropriate setup for a generator test before a runtime changelog exists. When the application actually needs to run migrations, configure Liquibase with the reviewed changelog and re-enable migration execution in the corresponding environments.

### 4.1. Why Run Schema Generation in Tests?

Schema generation is a development and review activity. Placing generator code in tests helps:

- Reuse the application's mapping configuration and custom conversions.
- Avoid unintended migration generation during application startup.
- Write files into a build directory or dedicated generated folder.
- Re-run easily whenever the domain model changes.
- Keep file generation separate from migration execution.

Spring documentation recommends placing schema generation logic in tests to prevent it from running unintentionally in production.

Reference: https://spring.io/blog/2023/08/29/spring-data-jdbc-how-to-maintain-your-database-schema/

## 5. Reading the Generated YAML Output

The output is a Liquibase changelog. Condensed example:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "..."
      author: Spring Data Relational
      changes:
        - createTable:
            tableName: customers
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: customer_code
                  type: VARCHAR(255)
              - column:
                  name: display_name
                  type: VARCHAR(255)
              - column:
                  name: birthday
                  type: DATE
              - column:
                  name: active
                  type: TINYINT
~~~

This example illustrates the structure; exact SQL types, nullability, quoting, and specific attributes depend on mappings, SQL type mapping, and the database.

Things to check in the output:

- Do table and column names match the desired naming strategy?
- Are SQL types appropriate for the target database?
- Are identifiers declared with the proper primary key?
- Which columns are nullable and which are required?
- Should ID columns auto-increment or use a different ID generation mechanism?
- Are schema names, quoting, and data types suitable for the deployment environment?

Do not treat generated YAML as an already-approved final schema. Review it before moving it into your official changelog.

## 6. Generating Differential Change Sets Against an Existing Database

When a project already has a schema and the domain model changes, you can generate a differential change set. This mode requires a Liquibase `Database` representing the current database.

Processing flow:

1. Initialize the mapping context with the desired aggregate roots.
2. Create a `LiquibaseChangeSetWriter`.
3. Open a JDBC connection to the database to compare against.
4. Create a Liquibase `Database` matching that JDBC connection.
5. Call `writeChangeSet(resource, database)`.
6. Review the generated changelog before using it.

Example using Liquibase `DatabaseFactory`:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;

import javax.sql.DataSource;

import liquibase.database.Database;
import liquibase.database.DatabaseFactory;
import liquibase.database.jvm.JdbcConnection;

import org.springframework.core.io.FileSystemResource;
import org.springframework.data.jdbc.core.mapping.schema.LiquibaseChangeSetWriter;

public void generateDiff(
        RelationalMappingContext mappingContext,
        DataSource dataSource
) throws Exception {

    LiquibaseChangeSetWriter writer =
            new LiquibaseChangeSetWriter(mappingContext);

    Path output = Path.of(
            "build/generated/liquibase/schema-diff.yaml"
    );

    Files.createDirectories(output.getParent());
    Files.deleteIfExists(output);
    Files.createFile(output);

    Connection connection = dataSource.getConnection();

    Database database = DatabaseFactory.getInstance()
            .findCorrectDatabaseImplementation(
                    new JdbcConnection(connection)
            );

    try (database) {
        writer.writeChangeSet(
                new FileSystemResource(output.toFile()),
                database
        );
    }
}
~~~

`DatabaseFactory` accepts the JDBC connection and selects the Liquibase implementation matching the actual database. If using a database wrapper or special setup, construct the `Database` in a way matching the running DBMS.

In the example, the Liquibase `Database` owns the attached connection and closes it once the writer finishes. If constructing `Database` fails before entering the try-with-resources block, close the JDBC connection in the corresponding error handler to avoid connection leaks.

Do not use an assumed database implementation such as `HsqlDatabase` when the actual `DataSource` connects to PostgreSQL, MySQL, or another DBMS. Schema comparison must read the exact database the application intends to diff against.

### 6.1. What Does the Writer Compare?

Differential mode compares the current schema from the Liquibase `Database` with the desired schema from mapped entities. It can generate changes to:

- Create tables that do not exist in the current schema.
- Add columns that do not exist yet.
- Drop tables no longer in the desired schema if allowed by the drop-table filter.
- Drop columns no longer in the desired schema if allowed by the drop-column filter.

Table and column names in differential mode are compared case-insensitively using the comparator described in the API. However, maintain a consistent naming convention; do not rely on case-insensitive comparison to mask naming discrepancies across environments.

## 7. Controlling Deletions with Drop Filters

An important safety feature: by default, the writer does not drop tables or columns. The default drop filters exclude all tables/columns from deletion.

You can configure them:

~~~java
writer.setDropTableFilter(tableName ->
        tableName.equalsIgnoreCase("obsolete_import_staging")
);

writer.setDropColumnFilter((tableName, columnName) ->
        tableName.equalsIgnoreCase("legacy_customers")
                && columnName.equalsIgnoreCase("unused_code")
);
~~~

A predicate returning `true` permits dropping the passed table or column; `false` retains it.

Never enable a filter such as "drop all unmapped tables/columns" without fully understanding the real schema. A table might be used by reports, stored procedures, integration systems, or another service even if it does not appear in the current entity mappings.

### 7.1. Schema Filter vs. Drop Filters

`setSchemaFilter` determines which entities are included in the desired schema:

~~~java
writer.setSchemaFilter(entity ->
        entity.getType() != LegacyReadModel.class
);
~~~

Returning `true` includes the entity; `false` excludes it from the generated schema.

In differential mode, an existing table excluded by the schema filter may be treated as no longer part of the desired schema. However, that table will only be dropped if the drop-table filter permits it. Both filter types serve different roles:

| Filter | Question it answers |
|---|---|
| Schema filter | Which entities are considered part of the desired schema? |
| Drop-table filter | Which existing tables are permitted to be dropped? |
| Drop-column filter | Which existing columns are permitted to be dropped? |

If you only want to skip an entity when generating an initial schema, the schema filter may suffice. When generating diffs, separately assess the impact of an excluded entity on existing tables.

## 8. Customizing SQL Types with SqlTypeMapping

The writer uses a `SqlTypeMapping` strategy to convert Java property types into database data types. The default is `DefaultSqlTypeMapping`.

If custom types are required, provide a custom strategy and compose it with the default mapping:

~~~java
import org.springframework.data.jdbc.core.mapping.schema.DefaultSqlTypeMapping;
import org.springframework.data.jdbc.core.mapping.schema.SqlTypeMapping;

writer.setSqlTypeMapping(((SqlTypeMapping) property -> {
    if (property.getType() == String.class
            && property.getName().equals("displayName")) {
        return "VARCHAR(500)";
    }

    return null;
}).and(new DefaultSqlTypeMapping()));
~~~

The example sets the `displayName` property's column to `VARCHAR(500)`. For other properties, the strategy returns `null` so `DefaultSqlTypeMapping` handles them.

Base rules on meaningful metadata, such as domain annotations or specific properties, rather than changing every `String` property globally. If many custom types are needed, define a dedicated annotation and read it from `RelationalPersistentProperty`.

### 8.1. Using Annotations to Describe Data Types

Example annotation:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
public @interface VarcharLength {
    int value();
}
~~~

Annotating a property:

~~~java
@VarcharLength(500)
private String displayName;
~~~

The strategy can read the annotation:

~~~java
writer.setSqlTypeMapping(((SqlTypeMapping) property -> {
    VarcharLength length =
            property.findAnnotation(VarcharLength.class);

    if (property.getType() == String.class && length != null) {
        return "VARCHAR(" + length.value() + ")";
    }

    return null;
}).and(new DefaultSqlTypeMapping()));
~~~

SQL types must be valid on the target database. If the application supports multiple databases, the strategy should account for dialects or use environment-specific mappings.

## 9. Customizing Serializer and Parser

Liquibase supports multiple changelog formats. `LiquibaseChangeSetWriter` uses a YAML serializer/parser by default and allows substituting other implementations:

~~~java
writer.setChangeLogSerializer(customSerializer);
writer.setChangeLogParser(customParser);
~~~

Only replace the serializer/parser when the project requires a custom changelog format or parsing behavior. If using default YAML, no additional configuration is needed.

Ensure the parser and serializer are compatible with the existing changelog format. An incompatible changelog structure can cause reading, appending, or migration execution to fail.

## 10. Output Resource and Append Behavior

The `writeChangeSet` methods take a Spring `Resource`. The API requires the resource to resolve to a valid file via `Resource.getFile()`. Therefore, `FileSystemResource` is the natural choice when generating local files.

Example:

~~~java
Resource output = new FileSystemResource(
        new File("build/generated/liquibase/initial-schema.yaml")
);

writer.writeChangeSet(output);
~~~

The Javadoc notes that the writer outputs the changelog to the resource and can append to an existing change set file. Therefore:

- Create a fresh generated file per run when you want clean output.
- Create parent directories before writing.
- Never point the generator at a manually maintained production changelog.
- Do not run repeatedly against the same file without accounting for append behavior.
- Do not use a resource inside a JAR or a classpath resource that cannot resolve to a physical file.

In real projects, output files to `build/generated` or a temporary directory. After reviewing, place the approved changelog into the version-controlled migration location.

## 11. What the Schema Writer Cannot Automatically Infer

Entity mappings describe the current desired schema state. They do not record full prior schema history or the business intent behind each change.

Thus, looking solely at two versions of an entity cannot automatically determine every necessary migration.

Important limitations:

- Cannot infer column rename intent; an old column disappearing and a new column appearing does not prove a rename.
- Cannot automatically generate data migrations, such as transforming values or copying data from old columns to new columns.
- Cannot know how to safely convert data when a column type changes.
- Schema generation documentation notes that relational references are currently not supported and may be ignored; check your running version and add required relationships via manual Liquibase change sets.
- Elements such as indexes, business constraints, triggers, views, or stored procedures must be verified in the output and added manually if the writer does not describe them as required.

Example column rename:

~~~text
Old version: customer_name
New version: display_name
~~~

When generating a diff purely from two schemas, the writer may interpret this as dropping the old column and adding a new one. If data in `customer_name` must be preserved, the migration must use intentional change sets such as renaming the column or adding the column, copying data, and dropping the old column in an appropriate release.

Similarly, when changing `VARCHAR(100)` to `VARCHAR(500)`, verify that the database supports the direct alteration and existing data obeys any new rules. Do not assume the schema writer replaces migration design.

## 12. From Generated Change Sets to Managed Migrations

A typical workflow:

~~~mermaid
flowchart TD
    A["Domain model and mappings"] --> B["RelationalMappingContext"]
    B --> C["LiquibaseChangeSetWriter"]
    C --> D["Generated YAML"]
    D --> E["Review schema and expected SQL"]
    E --> F["Edit / add manual migrations"]
    F --> G["Commit changelog to version control"]
    G --> H["Register changelog in Liquibase"]
    H --> I["Liquibase executes migrations in deployment environment"]
~~~

Practical steps:

1. Generate the initial schema or differential change set in a development environment.
2. Read the entire YAML file and inspect tables/columns/types/constraints.
3. Add indexes, foreign keys, renames, data migrations, or custom SQL as needed.
4. Place the changelog into the project's configured Liquibase directory, usually `src/main/resources/db/changelog`.
5. Include that file from the master changelog if the project uses a master changelog.
6. Commit the reviewed changelog to version control.
7. Configure Spring Boot/Liquibase to point to the master changelog.
8. Run migrations against a test database before deploying to other environments.

Liquibase tracks executed change set history in its tracking tables. Never arbitrarily edit a change set that has already run in a shared environment; create a new change set to describe the next change.

## 13. Configuring Liquibase in Spring Boot

When the Liquibase dependency is present, Spring Boot can automatically launch Liquibase when the application context is created. The default changelog is normally located in a standard path or configured explicitly with a property:

~~~properties
spring.liquibase.change-log=classpath:/db/changelog/db.changelog-master.yaml
~~~

The master changelog can include generated and reviewed files:

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/001-initial-schema.yaml
      relativeToChangelogFile: false
  - include:
      file: db/changelog/002-add-customer-status.yaml
      relativeToChangelogFile: false
~~~

Include paths must match the actual resource layout in the project. If the master file lives in a different directory, be explicit about how relative paths resolve.

In generator tests, you can disable Liquibase auto-run with:

~~~properties
spring.liquibase.enabled=false
~~~

Once the changelog is reviewed and integrated, enable Liquibase in environments that should run migrations. Do not treat disabling Liquibase in a generator test as a permanent deployment configuration.

## 14. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| No tables in output | Mapping context does not know aggregate roots | Register entities with `setInitialEntitySet` |
| Missing some aggregates | Initial entity set is incomplete | Add all aggregate roots to be managed |
| Liquibase class not found | Missing `liquibase-core` or incompatible dependency version | Add dependency and check dependency management |
| Spring Boot reports changelog not found during generator test | Liquibase auto-configuration tries to run migrations | Disable `spring.liquibase.enabled` in generator test |
| Writer cannot write file | Resource does not resolve to physical file or parent dir missing | Use `FileSystemResource` and create directory |
| File contains duplicate repeated change sets | Writer appended to an existing file | Use a fresh generated file or clear output before running |
| Diff proposes dropping tables/columns | Entity excluded from desired schema and drop filter permits drop | Check schema/drop filters and review diff |
| Table not dropped even after removing entity | Default drop-table filter forbids dropping | Enable filter selectively only for approved tables |
| Column not dropped | Default drop-column filter retains columns | Configure explicit predicate if drop is genuinely intended |
| SQL types do not match expectations | `DefaultSqlTypeMapping` does not match database conventions | Provide a custom `SqlTypeMapping` |
| Rename generated as drop/add | Writer lacks rename history and intent | Write rename/data migration manually |
| Foreign keys/references missing | Schema generation does not infer or support references as needed | Add Liquibase changesets manually and check version |
| Diff reads wrong database | `Database` object does not match actual `DataSource` | Use `DatabaseFactory` with the real JDBC connection |
| Changelog generated but database unchanged | Writer only writes files; it does not execute migrations | Configure Liquibase to apply changelog after review |

## 15. Implementation Workflow

1. Check Spring Data JDBC version; `LiquibaseChangeSetWriter` is available since Spring Data Relational 3.2.
2. Add `liquibase-core` with a compatible version.
3. Obtain the `RelationalMappingContext` configured for your application.
4. Register all aggregate roots via `setInitialEntitySet` if the context does not already hold the right entity set.
5. Instantiate `LiquibaseChangeSetWriter` from the mapping context.
6. Choose initial mode for empty schemas or differential mode with a Liquibase `Database` for existing schemas.
7. Use a `FileSystemResource` pointing to a separate generated file.
8. Configure schema filter, drop filters, and SQL type mapping only when genuinely needed.
9. Generate the changelog, review it, and supplement migrations that mapping metadata cannot infer.
10. Commit the approved changelog to version control and let Liquibase execute migrations across deployment environments.

## 16. Practice Exercises

### Exercise 1 — Initial Schema

Create two aggregate roots `Customer` and `PurchaseOrder`. Register them in `RelationalMappingContext` and use `LiquibaseChangeSetWriter` to generate YAML. Verify table names, column names, and SQL types.

### Exercise 2 — Mapping Metadata

Change table names with `@Table` and rename columns with `@Column`. Regenerate the initial schema and observe the impact of mapping metadata.

### Exercise 3 — Differential Schema

Generate an initial schema, apply it to a test database, then add a property to an entity. Run differential mode and inspect the generated add-column change set.

### Exercise 4 — Drop Filters

Remove an entity from the desired schema set. Observe the diff with the default drop-table filter and with the filter enabled for a selected table. Never run drop migrations on a shared database.

### Exercise 5 — Custom SQL Type

Create an annotation specifying `VARCHAR` length. Write a `SqlTypeMapping` that reads the annotation and composes with `DefaultSqlTypeMapping`. Verify the output across multiple properties.

### Exercise 6 — Rename and Data Migration

Rename a property that already holds data. Inspect the generated diff, then write a Liquibase change set that preserves data via rename or add/copy/drop following an appropriate strategy.

### Exercise 7 — Schema Filter

Exclude an entity from the schema using `setSchemaFilter`. Compare results in initial and differential modes, and explain the role of the drop-table filter.

### Exercise 8 — Liquibase Integration

Include the reviewed changelog in the master changelog. Run Liquibase against a test database and confirm both the schema and change set history were recorded.

## 17. Key Takeaways

- `LiquibaseChangeSetWriter` generates Liquibase changelogs from Spring Data JDBC relational mapping metadata.
- The class belongs to `org.springframework.data.jdbc.core.mapping.schema` and has been available since Spring Data Relational 3.2.
- Initial mode generates an initial schema; differential mode compares mapped entities against an existing Liquibase `Database`.
- `RelationalMappingContext` must know all aggregate roots before generating a schema.
- `writeChangeSet` writes changelog files; it does not apply migrations to the database.
- Default SQL type mapping can be customized via `SqlTypeMapping`; serializers/parsers are also customizable.
- Schema filters determine which entities belong to the desired schema; drop-table and drop-column filters determine what is permitted to be dropped.
- Dropping tables/columns is disabled by default. Enable selectively and review every destructive change.
- The writer cannot automatically infer renames or data migrations; references also need verification and manual additions depending on version support.
- Output to separate generated files, review changelogs, commit to version control, and let Liquibase manage migration execution.
- Generator tests should disable Liquibase auto-run before the changelog is ready; re-enable migration execution in deployment environments.
