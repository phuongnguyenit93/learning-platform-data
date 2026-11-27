# What Is `spring.graphql.schema.locations`?

`spring.graphql.schema.locations` is a Spring Boot configuration property used to specify the directories containing GraphQL Schema definition files written in SDL (Schema Definition Language). When the application starts, Spring Boot uses these locations to search for and load schema files, then creates the GraphQL Schema source for Spring for GraphQL to use.

This property is especially helpful when a schema is split across multiple files—for example, separating `Query`, `Mutation`, data types, and extensions by feature. Rather than merging schemas manually, you organize files in resource directories and configure where Spring Boot should look for them.

## 1. Role in a Spring for GraphQL Application

A GraphQL API needs a schema to describe the data types and operations clients are allowed to call. For example, SDL might declare a query field as follows:

```graphql
type Query {
    greeting: String!
}
```

The schema describes the API contract. It states that `Query` has a `greeting` field, that the field returns a string, and that the result must not be `null`. The schema does not execute business logic itself. Field handling is wired to resolvers in the Spring application, such as a method annotated with `@QueryMapping`.

In a standard Spring Boot configuration, this process can be visualized as follows:

1. Spring Boot reads `spring.graphql.schema.locations` and properties related to file extensions.
2. The resource loader searches for matching SDL files in the configured locations.
3. Spring for GraphQL builds the GraphQL Schema from the contents of the discovered files.
4. Application controllers and mapping methods provide the execution logic for the declared fields.

Thus, `spring.graphql.schema.locations` determines **where schemas are located**. It does not determine the URL of the GraphQL endpoint, nor does it declare Java resolvers.

## 2. Default Location

With Spring Boot's default configuration, the schema location is:

```yaml
spring:
  graphql:
    schema:
      locations: classpath:graphql/**/
```

Schema files are typically placed in the project's resources directory:

```text
src/
└── main/
    └── resources/
        └── graphql/
            ├── schema.graphqls
            ├── common/
            │   └── scalar.graphqls
            └── product/
                └── product.graphqls
```

After building, contents under `src/main/resources` are placed on the application's classpath. The `classpath:` prefix tells Spring to search for resources on the classpath. The `graphql/**/` segment allows searching inside the `graphql` directory and its subdirectories.

Under Spring Boot's default configuration, recognized schema extensions are `.graphqls` and `.gqls`. Hence, names like `schema.graphqls` and `product.gqls` work out of the box. If a project uses a different extension, configure `spring.graphql.schema.file-extensions` accordingly.

Normally, you do not need to redeclare `spring.graphql.schema.locations` if all schemas already reside in `src/main/resources/graphql/` or its subdirectories and the project uses default auto-configuration.

## 3. Configuring a Single Schema Location

When you want to place schemas in another directory, declare that location in `application.yml`:

```yaml
spring:
  graphql:
    schema:
      locations: classpath:api-schema/**/
```

Example corresponding resource structure:

```text
src/main/resources/
└── api-schema/
    ├── root.graphqls
    └── customer/
        └── customer.graphqls
```

If you only set `classpath:api-schema/`, scanning is limited by the declared directory pattern. Use `**/` when you want to include subdirectories across multiple levels. Ensure the configured value points to a resource directory that actually exists on the classpath after building.

You can use `application.properties` instead of YAML:

```properties
spring.graphql.schema.locations=classpath:api-schema/**/
```

Both formats serve the same purpose; pick the configuration format that matches your project's conventions.

## 4. Configuring Multiple Locations

When schemas are divided into multiple groups or provided from multiple resource directories, you can declare a list of locations:

```yaml
spring:
  graphql:
    schema:
      locations:
        - classpath:graphql/shared/**/
        - classpath:graphql/catalog/**/
        - classpath:graphql/order/**/
```

Each entry is a location to search for schema files. The example above groups shared schemas, catalog schemas, and order schemas into separate directories. In `application.properties`, a list can be represented as comma-separated values:

```properties
spring.graphql.schema.locations=classpath:graphql/shared/**/,classpath:graphql/catalog/**/,classpath:graphql/order/**/
```

When overriding the default property with a custom list, list all locations the application needs to load. Do not assume that the default `classpath:graphql/**/` location is automatically retained once a new list is configured.

Spring also supports referencing resources on the filesystem. For example, a deployment environment might provide schemas in a directory external to the application:

```yaml
spring:
  graphql:
    schema:
      locations: file:/opt/my-service/graphql/**/
```

A `file:` path must point to an existing location, and the application process must have read permissions. For environment-dependent settings, place the value in a profile-specific configuration file or an environment variable for that deployment environment. Absolute paths are generally easier to control than relative paths because the process working directory can change.

## 5. Combining Multiple SDL Files into One Schema

An application can split its schema into multiple files for easier management. For example:

`src/main/resources/graphql/root.graphqls`:

```graphql
type Query {
    greeting: String!
    product(id: ID!): Product
}
```

`src/main/resources/graphql/product/product.graphqls`:

```graphql
type Product {
    id: ID!
    name: String!
    price: Float!
}
```

Both files reside within the configured resource area so Spring Boot can load them to build the schema. Types declared in one file can be referenced from another file, as long as the combined schema is valid as a whole.

If you need to add fields to a type that was already declared, use GraphQL SDL type extension syntax. For instance, if `Query` is already declared in `root.graphqls`, another file can write:

```graphql
extend type Query {
    featuredProducts: [Product!]!
}
```

Do not redeclare `type Query` as two independent type definitions. Extending with `extend type` keeps split schema files clean and avoids definition conflicts.

Once the schema is loaded, a resolver in Spring can handle the declared field:

```java
@Controller
class GreetingController {

    @QueryMapping
    String greeting() {
        return "Hello from Spring GraphQL";
    }
}
```

The method name `greeting` maps to the `Query.greeting` field. This example highlights two separate responsibilities: `spring.graphql.schema.locations` helps locate the SDL, whereas `@QueryMapping` connects the query field to the Java code executing the logic.

## 6. Distinguishing from Other GraphQL Properties

Several properties have similar names but solve different problems:

| Property | Purpose |
|---|---|
| `spring.graphql.schema.locations` | Specifies where to search for GraphQL SDL files. |
| `spring.graphql.schema.file-extensions` | Specifies the file extensions of schema files to scan; defaults are typically `.graphqls` and `.gqls`. |
| `spring.graphql.path` | Specifies the HTTP path at which the GraphQL endpoint is served. |
| `spring.graphql.graphiql.enabled` | Enables or disables the GraphiQL UI when the application has supporting configuration. |

For example, changing `spring.graphql.path` does not alter where Spring Boot searches for schemas. Similarly, setting `spring.graphql.schema.locations` does not create a new endpoint or enable GraphiQL.

## 7. Troubleshooting When Schemas Fail to Load

If the application fails to start or a GraphQL type does not appear in the schema, check the following points in order:

1. **Correct resource location:** verify that the files sit under `src/main/resources` or a resource directory actually included on the classpath. With `file:`, verify the path on the host running the application.
2. **Correct directory pattern:** check the `classpath:` or `file:` prefix and trailing `/`. Use `**/` if files reside in nested subdirectories.
3. **Correct file extension:** verify that the file uses an extension included in `spring.graphql.schema.file-extensions`. If using a custom extension, declare it in configuration.
4. **Correct profile:** check whether `application.yml`, `application-{profile}.yml`, or environment variables override the schema location.
5. **Valid schema:** check for SDL syntax errors, undeclared types, fields referencing wrong types, and duplicate definitions. Multiple loaded files must still form a single valid GraphQL schema.
6. **Schema source configuration:** if the application declares its own `GraphQlSource` or builds the schema manually, check whether that custom configuration replaces the auto-configuration that uses this property.

A simple verification check is to create a small query field in an SDL file inside the configured location, write a matching resolver with `@QueryMapping`, start the application, and send a query to the GraphQL endpoint. If the field is recognized and the resolver is invoked, the schema has been loaded and mapped properly for that test case.

For schemas stored outside the classpath, manage file read permissions and deployment lifecycle carefully. The schema is the server's API contract; control schema changes alongside your application review and release workflow to prevent an environment from running definitions incompatible with existing resolvers.

## 8. When Should You Configure This Property?

Keep the default configuration when your project follows the convention of placing schemas in `src/main/resources/graphql/`. Declare `spring.graphql.schema.locations` when you need to move schemas to another directory, split schemas across multiple directories, or load schemas from a location outside the classpath.

When organizing multiple files, choose a domain-aligned directory structure that is easy to understand, ensure all needed locations are listed, and keep SDL definitions valid when combined. This organization helps Spring Boot locate schemas consistently across development, testing, and deployment environments.
