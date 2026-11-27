# GraphQL observation convention

In Spring for GraphQL, an observation convention determines the observation name, the name displayed in traces, and the key-values attached to the observation. A convention does not measure time or create observations itself; instrumentation creates observations while GraphQL processes requests, while the convention describes how metadata is recorded.

Spring for GraphQL provides default conventions for three levels: GraphQL requests, data fetchers, and DataLoaders. When default metadata is not enough for your dashboards or tracing, you can extend a convention to add information such as API version, resolver group, or the business domain of a batch loader.

Observations are only published when the application has a configured `ObservationRegistry`. A convention specifies metadata for an observation; it does not replace the registry or instrumentation.

For Spring Boot applications, the recommended integration is registering conventions as beans. When configuring the GraphQL runtime manually, you can pass conventions directly into `GraphQlObservationInstrumentation`. This article covers both approaches as well as principles for keeping metadata stable and safe for metrics.

## 1. What Does an Observation Convention Solve?

An observation records an ongoing activity. A convention provides information describing that activity:

- Observation name used to identify the meter or span.
- Contextual name used as a human-readable span name.
- Low-cardinality key-values used as metric tags and also included in traces.
- High-cardinality key-values reserved for traces and excluded from metrics.

For example, the default request observation is named `graphql.request`. The convention attaches the operation type and outcome so dashboards can analyze rates of successful or failing queries, mutations, and subscriptions.

When an application serves multiple API versions, you can add a `graphql.api.version` key. When analyzing resolvers, you can group fields into `catalog`, `account`, or `other`. These labels help dashboards filter data without creating a separate time series per request or per user.

## 2. Three Conventions in Spring for GraphQL

Spring for GraphQL has three convention interfaces corresponding to the three observation types:

| Convention | Observation | Context | Scope |
| --- | --- | --- | --- |
| `ExecutionRequestObservationConvention` | `graphql.request` | `ExecutionRequestObservationContext` | Entire GraphQL request |
| `DataFetcherObservationConvention` | `graphql.datafetcher` | `DataFetcherObservationContext` | A field data-fetching operation |
| `DataLoaderObservationConvention` | `graphql.dataloader` | `DataLoaderObservationContext` | A batch load invocation |

Each interface extends Micrometer's `ObservationConvention<T>`. A convention can provide the observation name, contextual name, and both groups of key-values.

Spring provides the corresponding default implementations:

- `DefaultExecutionRequestObservationConvention`.
- `DefaultDataFetcherObservationConvention`.
- `DefaultDataLoaderObservationConvention`.

Extend the default implementation if you only want to add a few keys. This preserves standard metadata and reduces the risk of accidentally dropping keys relied upon by dashboards or monitoring tools.

## 3. Default Metadata of Each Observation

Before customizing, you need to know which keys the default conventions emit.

**`graphql.request`**

| Cardinality | Key | Meaning |
| --- | --- | --- |
| Low | `graphql.operation.type` | `query`, `mutation`, `subscription`, or `operation` if the document cannot be parsed |
| Low | `graphql.outcome` | `SUCCESS`, `REQUEST_ERROR`, or `INTERNAL_ERROR` |
| High | `graphql.execution.id` | ID of the GraphQL execution |
| High | `graphql.operation.name` | Operation name sent by the client |

**`graphql.datafetcher`**

| Cardinality | Key | Meaning |
| --- | --- | --- |
| Low | `graphql.error.type` | Class name of the data fetching error |
| Low | `graphql.field.name` | Name of the field being resolved |
| Low | `graphql.outcome` | `SUCCESS` or `ERROR` |
| High | `graphql.field.path` | Full path to the field in the response |

Data fetcher observations are only created for data fetching operations considered non-trivial. Simple property reads from a Java object usually do not create a separate observation.

**`graphql.dataloader`**

| Cardinality | Key | Meaning |
| --- | --- | --- |
| Low | `graphql.error.type` | Class name of the batch loading error |
| Low | `graphql.loader.name` | DataLoader name |
| Low | `graphql.outcome` | `SUCCESS` or `ERROR` |
| High | `graphql.loader.size` | Number of keys in the batch |

DataLoader observations track `@BatchMapping` calls and manually registered DataLoaders supported by instrumentation. The DataLoader convention was added in Spring for GraphQL 1.4.0.

## 4. What Data Does the Context Provide to a Convention?

A convention does not need to parse GraphQL documents or measure time itself. Instrumentation passes an appropriate context into the convention.

**ExecutionRequestObservationContext**

The request context provides:

- `getExecutionInput()`: the GraphQL input of the request.
- `getExecutionContext()`: the execution context once available.
- `getExecutionResult()`: the execution result once available.

You can use the context to read information placed in the GraphQL execution input or execution result. Do not extract full variables or raw documents and put them into metrics.

**DataFetcherObservationContext**

The data fetcher context provides:

- `getEnvironment()`: `DataFetchingEnvironment` of the running field.
- `getValue()`: the value returned by the data fetcher, if available.

From `DataFetchingEnvironment`, a convention can read the field definition, field path, GraphQL context, and related execution info. Choose only useful metadata with a bounded domain of values.

**DataLoaderObservationContext**

The DataLoader context provides:

- `getDataLoader()`: the DataLoader executing the batch.
- `getEnvironment()`: the batch loader environment.
- `getKeys()`: keys requested in the batch.
- `getResult()`: list of resolved results.

Do not put keys or results directly into metric tags. Those values are typically IDs, account numbers, or business data and can cause very high cardinality.

## 5. Customizing Conventions in Spring Boot

In a Spring Boot application, register a bean of the corresponding convention type. Spring GraphQL auto-configuration uses convention beans when creating observation instrumentation.

Example configuring a request convention:

~~~java
package com.example.graphql.observability;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;
import org.springframework.graphql.observation.ExecutionRequestObservationConvention;

@Configuration
public class GraphQlObservationConfiguration {

    @Bean
    ExecutionRequestObservationConvention executionRequestConvention() {
        return new ApiVersionRequestConvention();
    }
}

class ApiVersionRequestConvention
        extends DefaultExecutionRequestObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ExecutionRequestObservationContext context) {

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("graphql.api.version", "v1"));
    }
}
~~~

The default convention still produces `graphql.operation.type` and `graphql.outcome`. The custom convention simply adds `graphql.api.version=v1`.

This key fits low cardinality because the value is controlled by the application and only changes when the API version changes. If an application serves only a single API version in a deployment, this value may not add much insight; only add tags when they support an actual operational query.

## 6. Classifying Operations with a Convention

You can add an operation group label so dashboards can distinguish important flows. Do not use raw client-supplied operation names as low-cardinality keys because clients can invent unlimited names.

A safe approach is maintaining an allow-list of known operation names and mapping them to a few fixed groups:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;

class OperationGroupRequestConvention
        extends DefaultExecutionRequestObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ExecutionRequestObservationContext context) {

        String operationName = context.getExecutionInput().getOperationName();
        String group = operationGroup(operationName);

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("graphql.operation.group", group));
    }

    private String operationGroup(String operationName) {
        if (operationName == null) {
            return "unnamed";
        }

        return switch (operationName) {
            case "FindBook", "SearchBooks" -> "catalog-read";
            case "CreateBook", "UpdateBook" -> "catalog-write";
            case "SignIn", "RefreshSession" -> "identity";
            default -> "other";
        };
    }
}
~~~

The convention reads the operation name from `ExecutionInput`, maps it to an allow-listed group, and appends the new key. Always keep an `other` branch so unknown operation names cannot inflate cardinality. If the document has no operation name, the label becomes `unnamed`.

This is an alternative to `ApiVersionRequestConvention` from the previous section. Pick the request convention suited to your needs; do not register two beans of the same convention type in the same application context.

A simpler option is adding only a fixed API version or service name. Do not add tags merely because conventions allow doing so.

## 7. Customizing DataFetcherObservationConvention

A data fetcher convention is useful when you want to group resolvers by business domain. For example, an API has catalog and people groups. The field name is mapped to a fixed label:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.graphql.observation.DataFetcherObservationContext;
import org.springframework.graphql.observation.DataFetcherObservationConvention;
import org.springframework.graphql.observation.DefaultDataFetcherObservationConvention;

class FieldDomainDataFetcherConvention
        extends DefaultDataFetcherObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            DataFetcherObservationContext context) {

        String fieldName =
            context.getEnvironment().getFieldDefinition().getName();

        String fieldDomain = switch (fieldName) {
            case "book", "books", "searchBooks" -> "catalog";
            case "author", "authors" -> "people";
            default -> "other";
        };

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("graphql.field.domain", fieldDomain));
    }
}
~~~

Register this class via a bean of type `DataFetcherObservationConvention` in your Spring Boot configuration.

The default convention continues to provide field name, outcome, and error type. The new `graphql.field.domain` key has exactly three values: `catalog`, `people`, and `other`.

Do not put the full field path into a low-cardinality key. A field nested inside a list can produce paths containing indices or structures that vary per request; that metadata belongs in high-cardinality traces.

Also do not put field arguments such as `bookId`, email, or filter values into the convention. They may contain sensitive data and are unsuitable as metric tags.

## 8. Customizing DataLoaderObservationConvention

Since Spring for GraphQL 1.4.0, you can customize the convention for DataLoader observations. The following example adds a shared domain label for loaders belonging to the catalog service:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.graphql.observation.DataLoaderObservationContext;
import org.springframework.graphql.observation.DataLoaderObservationConvention;
import org.springframework.graphql.observation.DefaultDataLoaderObservationConvention;

class CatalogDataLoaderConvention
        extends DefaultDataLoaderObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            DataLoaderObservationContext context) {

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("graphql.loader.domain", "catalog"));
    }
}
~~~

Register this class via a bean of type `DataLoaderObservationConvention` in your Spring Boot configuration.

The default convention still records the loader name, outcome, and error type. The new `graphql.loader.domain` key groups batch loaders belonging to the catalog domain.

This example assumes the convention bean only applies to a set of loaders within the same domain. If the application spans multiple business domains, map loaders to a small set of labels such as `catalog`, `identity`, or `other`. Do not put key lists, entity IDs, or result contents into low-cardinality keys.

`DataLoaderObservationContext` allows reading the key list and result, but that does not mean those values belong in metrics. Batch size information is already provided by the default convention via the high-cardinality key `graphql.loader.size`.

## 9. Registering All Three Conventions in One Configuration

An application can provide all three beans in the same configuration:

~~~java
@Configuration
public class AllGraphQlObservationConventionsConfiguration {

    @Bean
    ExecutionRequestObservationConvention executionRequestConvention() {
        return new ApiVersionRequestConvention();
    }

    @Bean
    DataFetcherObservationConvention dataFetcherConvention() {
        return new FieldDomainDataFetcherConvention();
    }

    @Bean
    DataLoaderObservationConvention dataLoaderConvention() {
        return new CatalogDataLoaderConvention();
    }
}
~~~

`ApiVersionRequestConvention`, `FieldDomainDataFetcherConvention`, and `CatalogDataLoaderConvention` are the classes defined in the previous sections. Separating classes makes it easier to unit test each convention independently and avoids overly long configuration classes.

This combined configuration replaces the request-only configuration from section 5. When using it, remove the separate request convention bean from the earlier configuration so the application context has only one bean per convention type.

Each convention type has its own responsibility and context. Do not register multiple beans of the same type simultaneously unless intentionally replacing the default convention; bean selection can become ambiguous or prevent auto-configuration from initializing as expected.

If you only need to customize request observations, register only the request convention. Data fetchers and DataLoaders can continue using their default conventions.

## 10. Customizing Contextual Name and Observation Name

Beyond key-values, conventions also control:

- `getName()`: the observation name used as the meter name.
- `getContextualName(context)`: human-readable name for spans in traces.

Normally, keep the default names `graphql.request`, `graphql.datafetcher`, and `graphql.dataloader`. Dashboards, alerts, and Prometheus queries typically depend on these names. Renaming them can cause the monitoring system to treat the renamed observation as a brand-new meter.

If you want more readable span names, you can override the contextual name in a convention:

~~~java
@Override
public String getContextualName(
        ExecutionRequestObservationContext context) {
    return "graphql request";
}
~~~

Contextual names should be short, stable, and free of user IDs, entity IDs, or full GraphQL documents. You can keep the default implementation if current trace names are already clear enough.

## 11. Manually Configuring GraphQlObservationInstrumentation

For applications not using Spring Boot auto-configuration, you can instantiate `GraphQlObservationInstrumentation` and pass conventions into the constructor:

~~~java
import io.micrometer.observation.ObservationRegistry;

import org.springframework.graphql.observation.GraphQlObservationInstrumentation;

GraphQlObservationInstrumentation instrumentation =
    new GraphQlObservationInstrumentation(
        observationRegistry,
        requestConvention,
        dataFetcherConvention,
        dataLoaderConvention
    );
~~~

Then register this instrumentation with the GraphQL Java builder used by `GraphQlSource`. Example integration point:

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.graphql.execution.GraphQlSource;

GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
    .schemaResources(new ClassPathResource("graphql/schema.graphqls"))
    .configureGraphQl(builder ->
        builder.instrumentation(instrumentation)
    )
    .build();
~~~

This is manual configuration for applications managing the GraphQL runtime themselves. You must provide `ObservationRegistry` and the required beans/dependencies according to how the application is wired.

Do not add instrumentation manually if Spring Boot already configures GraphQL observation instrumentation. If both auto-configuration and manual configuration register instrumentation, observations may be recorded twice or the pipeline may become difficult to reason about.

## 12. Constructor Notes by Spring for GraphQL Version

The constructor API of `GraphQlObservationInstrumentation` changed when DataLoader observations were added:

| API version | Constructor | Status |
| --- | --- | --- |
| Prior to 1.4.0 | `GraphQlObservationInstrumentation(ObservationRegistry)` | Uses default conventions |
| Since 1.1.0 | 3-arg constructor: registry, request convention, data fetcher convention | Deprecated since 1.4.0, slated for removal |
| Since 1.4.0 | 4-arg constructor adding data loader convention | Use when passing conventions manually for all three types |

`DataLoaderObservationConvention` and `DataLoaderObservationContext` were introduced in Spring for GraphQL 1.4.0. If your project is on an older branch, the DataLoader convention API may not exist yet.

With Spring Boot applications, let Spring Boot manage the Spring for GraphQL version through dependency management/BOM and register conventions as beans. This avoids calling the instrumentation constructor directly in most applications.

## 13. When to Extend the Default Convention vs. Implement the Interface

Extending the default class is suitable when:

- You want to add one or a few key-values.
- You want to retain Spring's standard keys and outcome computation.
- You only need to adjust part of the metadata.
- You want to minimize code you have to maintain when the framework evolves.

Implementing the interface directly is suitable when:

- You need full control over observation names and key-values.
- You want to define a completely different metadata convention.
- You have a clear reason to alter contextual names or outcome classification.

When implementing directly, you must fulfill the entire Micrometer convention contract: observation name, contextual name, low-cardinality key-values, and high-cardinality key-values. You must also ensure the convention applies only to the right context type.

Do not re-implement an entire convention just to add one tag. Extending the default class is usually easier to read, less error-prone, and more compatible.

## 14. Distinguishing Conventions from ObservationFilter

`ObservationConvention` determines the initial metadata for a specific observation type. `ObservationFilter` is a post-processing step on the registry that can modify names or key-values after the convention has run.

| Criterion | ObservationConvention | ObservationFilter |
| --- | --- | --- |
| Scope | A specific observation type with a specific context | Observations passing through the registry |
| Role | Defines standard names and metadata | Modifies or enriches metadata afterward |
| Suitable when | Customizing GraphQL request/data fetcher/DataLoader | Normalizing application-wide shared metadata |
| Risk | Can drop default keys if implemented incompletely | Can unintentionally affect HTTP, database, or messaging observations |

If you only want to add `graphql.api.version` to GraphQL requests, use a request convention. Avoid using a global filter to inspect multiple context types and inject GraphQL-specific logic into a hook shared across the entire application.

## 15. Cardinality and Data Protection

When adding a new key, decide explicitly whether it is low or high cardinality.

**Use low cardinality for:**

- API versions from a small set.
- Allow-listed operation groups.
- Business domains such as catalog, identity, or billing.
- Normalized resolver categories.
- Controlled DataLoader groups.

**Do not use low cardinality for:**

- User IDs, tenant IDs, or account IDs.
- Emails, usernames, or session IDs.
- Book IDs, order IDs, or author IDs.
- GraphQL arguments and variables.
- Raw client-supplied operation names.
- Raw field paths or GraphQL documents.

High-cardinality keys are only suitable for traces, not metrics. Yet high cardinality does not mean data is automatically safe: traces can still be retained for a long time, queried, or widely shared. Put only truly necessary metadata into traces and follow your system's data policies.

Avoid using different key names for the same meaning across services when they can be standardized. Consistent naming conventions keep dashboards, alerts, and trace queries maintainable.

## 16. Testing Custom Conventions

You can unit test conventions directly without starting an HTTP server. Example checking that a request convention preserves default keys and adds the API version:

~~~java
package com.example.graphql.observability;

import static org.assertj.core.api.Assertions.assertThat;

import graphql.ExecutionInput;
import io.micrometer.common.KeyValue;

import org.junit.jupiter.api.Test;
import org.springframework.graphql.observation.ExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;

class ApiVersionRequestConventionTests {

    private final ExecutionRequestObservationConvention convention =
        new ApiVersionRequestConvention();

    @Test
    void keepsDefaultKeysAndAddsApiVersion() {
        ExecutionInput input = ExecutionInput.newExecutionInput(
            "{ books { id } }"
        ).build();

        ExecutionRequestObservationContext context =
            new ExecutionRequestObservationContext(input);

        assertThat(convention.getLowCardinalityKeyValues(context))
            .contains(KeyValue.of("graphql.api.version", "v1"));
    }
}
~~~

This test focuses on the convention contract. You can add tests to verify:

- Default low-cardinality keys remain present.
- New keys only take values within the specified set.
- High-cardinality keys are not accidentally moved to low cardinality.
- Unknown fields are mapped to `other`.
- DataLoader conventions do not put keys or results into metrics.
- Observation names stay unchanged if dashboards rely on default names.

Beyond unit tests, write integration tests with the GraphQL runtime and `SimpleMeterRegistry` or an appropriate test registry. Integration tests verify that the convention is actually picked up by Spring Boot auto-configuration and that meters appear after sending GraphQL operations.

## 17. Common Mistakes When Customizing Conventions

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Custom convention is not used | Bean implements wrong interface or GraphQL instrumentation is configured elsewhere | Check bean type and auto-configuration |
| Default keys disappear after customization | Override returns brand-new KeyValues without calling super | Combine with `super.getLowCardinalityKeyValues(context)` |
| DataLoader convention fails to compile | Spring for GraphQL older than 1.4.0 | Upgrade to a compatible version or customize only available conventions |
| Using 3-arg constructor on newer versions | Constructor deprecated since 1.4.0 | Use the 4-arg constructor when configuring instrumentation manually |
| Metrics generate too many time series | IDs, field paths, or operation names put in low cardinality | Map to a finite label set or move to high cardinality if truly needed |
| GraphQL metrics recorded twice | Both auto-configuration and manual instrumentation active | Keep only one instrumentation configuration |
| Dashboard loses old meters | Observation name was changed | Keep the default name or plan a dashboard migration |
| Traces expose user data | Variables or keys added to contextual name | Record only normalized and permitted metadata |
| DataFetcher observations missing for some fields | Field only reads a simple property | Expected instrumentation behavior |
| Convention reads context too early | Execution result data is not yet available at that stage | Use data available at the right lifecycle phase and check nullability |

## 18. Implementation Checklist

- Have you decided whether you need to customize the request, data fetcher, or DataLoader convention?
- Have you reviewed the default keys before adding metadata?
- Did you extend the default convention when only adding keys?
- Does Spring Boot pick up the convention via a bean of the right interface?
- Does a manually configured application pass the right conventions into instrumentation?
- Are observation names kept stable so dashboards are not disrupted?
- Do low-cardinality keys take only finite, controlled values?
- Are IDs, arguments, variables, and personal data excluded from metric tags?
- Does the DataLoader convention only use APIs available in Spring for GraphQL 1.4.0 or later?
- Is the instrumentation constructor version-compatible and free of deprecated APIs?
- Do unit tests verify both default keys and custom keys?
- Do integration tests verify Spring actually records meters/traces using the convention?
- Is there no duplicate instrumentation between auto-configuration and manual setup?

A GraphQL observation convention defines how Spring for GraphQL describes requests, data fetchers, and DataLoaders in metrics and traces. Start from the default conventions, add only useful metadata, and keep low-cardinality keys within a finite set of values. With Spring Boot, register conventions as beans; with a manually configured GraphQL runtime, pass them into the four-argument constructor of `GraphQlObservationInstrumentation` on Spring for GraphQL 1.4.0 or later. Testing default keys, new keys, and confirming auto-configuration actually applies the convention keeps metadata consistent without bloating dashboard cardinality.

## References

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [ExecutionRequestObservationConvention API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/ExecutionRequestObservationConvention.html)
- [DataFetcherObservationConvention API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/DataFetcherObservationConvention.html)
- [DataLoaderObservationConvention API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/DataLoaderObservationConvention.html)
- [GraphQlObservationInstrumentation API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html)
- [Micrometer Observation — Concepts](https://docs.micrometer.io/micrometer/reference/observation.html)
