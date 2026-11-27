# PropertySource and Profile Inheritance in a Hierarchy

This lesson belongs to the **Context Hierarchy** chapter of the **SPRING_CLOUD_CORE** module. In a Spring application with multiple `ApplicationContext` instances linked in a parent–child relationship, whether one context can look up configuration or beans from another context depends on how the hierarchy and each context's `Environment` are configured.

Two concepts must be separated:

- **ApplicationContext hierarchy:** governs bean scope and bean lookup relationships between parent and child.
- **Environment hierarchy:** governs how `PropertySource` instances and profiles are brought into a context's environment to resolve configuration.

A child context can typically inherit property sources and active/default profiles from its parent via the merge mechanism. Local PropertySources in the child take precedence over sources from the parent. However, if two sources have the same name, the child's source is kept and the parent's same-named source is omitted from the child; Spring does not merge individual keys across those two sources. Profiles are also merged as a set of profile names, rather than inheriting all beans or configuration documents as-is.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain parent–child ApplicationContexts and distinguish them from relationships between Environments.
2. Describe how `ConfigurableEnvironment.merge(parent)` brings property sources, active profiles, and default profiles from parent into child.
3. Determine the winning property value when both child and parent declare the same key.
4. Detect collisions when two different PropertySources use the same name.
5. Explain how active/default profiles are merged and deduplicated, and how `setActiveProfiles` differs from `addActiveProfile`.
6. Distinguish profiles of parent, child, and sibling contexts; know when they share an Environment.
7. Understand how the Spring Cloud bootstrap context and Spring Cloud Config introduce remote PropertySources into a hierarchy.
8. Distinguish legacy bootstrap from modern Spring Boot Config Data imports.
9. Design tests to verify property resolution, profile selection, and merge limitations.

## 2. What Is an ApplicationContext Hierarchy?

An application can create multiple Spring containers instead of just a single context. One context can be attached as the **parent** of another context:

~~~mermaid
flowchart TD
    P["Parent ApplicationContext"] --> C1["Child context: order"]
    P --> C2["Child context: inventory"]
    C1 --> G1["Order-specific beans"]
    C2 --> G2["Inventory-specific beans"]
    P --> PB["Shared beans in parent"]
~~~

Some fundamental characteristics:

- A child can look up beans defined in itself as well as accessible beans from the parent.
- The parent does not look downward for beans that exist only in the child.
- A child can define a bean with the same name to shadow a same-named bean in the parent during lookups from the child.
- Siblings do not automatically see each other's private beans; they can share beans placed in the parent.
- Each context has its own lifecycle: refresh, close, and managing its own beans.

For example, the parent contains shared beans such as an HTTP client or infrastructure components. The `order-service` and `inventory-service` children can define their own business beans while looking up infrastructure beans from the parent.

**Bean visibility does not imply property inheritance.** A child seeing parent beans does not automatically tell you configuration precedence order. To understand configuration, inspect that context's Environment.

## 3. Environment and PropertySource in a Context

### 3.1. Environment Is Where Properties Are Resolved

`Environment` is the abstraction for reading properties and profiles. An Environment contains an ordered collection of `PropertySource` objects searched in sequence. When multiple sources contain the same key, the first source found supplies the value.

Example:

~~~java
String region = environment.getProperty("app.region");
~~~

The returned value depends not only on whether the key exists, but also on:

- Which source contains that key.
- What position that source occupies in the list.
- Whether the source was replaced or removed.
- Whether the Environment of the queried context is a separate Environment or a shared Environment.

### 3.2. Named PropertySources

Each PropertySource has a name identifying it in the source collection. Example:

~~~java
new MapPropertySource(
    "parent-defaults",
    Map.of("app.region", "ap-southeast")
);
~~~

The source name is not a property key name. Two sources with different names can both contain `app.region`; in that case, their order in the list determines the winning value.

The source name also matters when merging parent and child. If a child source has the same name as a parent source, Spring keeps the child source and drops the parent source with the matching name. This is replacement by source name, not a key-by-key merge of two maps.

### 3.3. Separate Environment vs. Shared Environment

Two models must be distinguished:

| Model | Characteristics | Consequence |
| --- | --- | --- |
| **Separate Environment per context** | Parent and child have separate Environments; child can merge parent's Environment. | Allows adding local configuration and separate profiles for the child. |
| **Shared Environment** | Multiple contexts reference the same Environment object. | PropertySource/profile changes on that object can affect all contexts sharing it; lower isolation. |

`SpringApplicationBuilder` can be configured to share an Environment across a hierarchy, but that is not the default. Do not assume two siblings always have the same active profiles or PropertySources just because they share a parent.

If each child needs different configuration, keep separate Environments and merge intentionally. If you need the same configuration set to change synchronously, you can choose a shared Environment or a configuration broadcast mechanism, while understanding the impact on all participating contexts.

## 4. How ConfigurableEnvironment.merge(parent) Works

Spring Framework provides `ConfigurableEnvironment.merge(ConfigurableEnvironment parent)`. During merge:

1. The parent's active profiles are added to the child's set of active profiles.
2. The parent's default profiles are added to the child's set of default profiles.
3. The parent's PropertySources are appended to the child's PropertySource list.
4. Duplicate profile names are deduplicated.
5. If a source with the same name appears in both parent and child, the child's source is kept and the parent's source is dropped.
6. The parent Environment is not modified.
7. With separate Environments, changes made to the parent after the merge are not automatically synced to the child; you must update/re-merge at an appropriate lifecycle point or use a shared Environment if that is intended.

Because the parent's property sources are appended to the child's list, local sources already in the child are generally searched first and take higher precedence than inherited sources.

### 4.1. Example: Parent and Child with Differently Named Sources

Parent:

~~~java
ConfigurableEnvironment parent = new StandardEnvironment();

parent.getPropertySources().addFirst(
    new MapPropertySource("parent-config", Map.of(
        "app.region", "ap-southeast",
        "app.timeout", "2s",
        "app.parent-only", "parent-value"
    ))
);

parent.setActiveProfiles("common", "production");
~~~

Child:

~~~java
ConfigurableEnvironment child = new StandardEnvironment();

child.getPropertySources().addFirst(
    new MapPropertySource("child-config", Map.of(
        "app.region", "eu-west",
        "app.child-only", "child-value"
    ))
);

child.setActiveProfiles("worker");
child.merge(parent);
~~~

Lookup results in the child:

| Key | Value | Winning source |
| --- | --- | --- |
| `app.region` | `eu-west` | `child-config` |
| `app.timeout` | `2s` | Inherited `parent-config` |
| `app.parent-only` | `parent-value` | Inherited `parent-config` |
| `app.child-only` | `child-value` | `child-config` |

Active profiles in the child include `worker`, `common`, and `production`. The parent's profiles were added to the child's set; the child's profile was preserved.

### 4.2. Same-Named Sources: Child Replaces Parent Source

Suppose the parent has:

~~~java
parent.getPropertySources().addFirst(
    new MapPropertySource("shared-config", Map.of(
        "app.color", "blue",
        "app.parent-only", "visible-in-parent"
    ))
);
~~~

The child has:

~~~java
child.getPropertySources().addFirst(
    new MapPropertySource("shared-config", Map.of(
        "app.color", "green",
        "app.child-only", "visible-in-child"
    ))
);
~~~

After `child.merge(parent)`, the child's `shared-config` source is kept. The parent's `shared-config` source is omitted from the child's list due to the name collision.

Result:

- `app.color` in the child is `green`.
- `app.child-only` in the child is `visible-in-child`.
- `app.parent-only` is not resolved from the parent source that was excluded from the child.
- The parent retains its original source, and when queried directly on the parent, `app.color` is still `blue`.

This is a very easy pitfall. If you want to inherit parent keys while allowing the child to override a subset, use different PropertySource names such as `parent-config` and `child-config`, or explicitly build a merged source before adding it to the Environment.

### 4.3. Merge Order and Precedence

You can visualize the source list after merging as:

~~~text
Child's Environment
  1. child-config          (higher precedence)
  2. child-local-defaults
  3. parent-config         (appended from parent)
  4. parent-defaults
  5. other default sources depending on Environment
~~~

This is an illustrative diagram, not a fixed list for every Spring Boot application. The actual order depends on which sources are created and how they are added.

Do not infer precedence solely from source names. When conflicts occur, inspect the actual order in `environment.getPropertySources()` and the values returned by `getProperty()`.

## 5. Inheritance of Active Profiles and Default Profiles

### 5.1. Profiles Are Merged as a Set of Names

Profiles control which beans or configuration documents are activated. When a child Environment merges a parent, active profiles and default profiles from the parent are appended to the child's corresponding sets; duplicate names are removed.

Example:

| Context | Active profiles before merge |
| --- | --- |
| Parent | `common`, `production` |
| Child | `worker`, `production` |
| Child after merge | `worker`, `production`, `common` |

`production` appears only once. The `common` profile is inherited from the parent, while `worker` is the child's local profile.

A profile is not a PropertySource. It is Environment state used when evaluating `@Profile` and selecting profile-specific configuration documents.

### 5.2. `setActiveProfiles` vs. `addActiveProfile`

The two APIs behave differently:

- `setActiveProfiles("worker")` replaces the current set of active profiles with the supplied set.
- `addActiveProfile("worker")` adds a profile to the current set while preserving existing profiles.

If a child has already merged the parent and then calls `setActiveProfiles("worker")`, the merged parent profiles can be removed from the child's active set. If the goal is to add a local profile while keeping inherited profiles, use `addActiveProfile` or configure profiles in a way that does not replace the current set.

Example:

~~~java
child.merge(parent);

// Add a profile while preserving merged profiles
child.addActiveProfile("worker");
~~~

Do not call `setActiveProfiles` after a merge unless you intentionally want to replace the entire profile set.

### 5.3. Default Profiles Are Not Regular Active Profiles

Default profiles are used when no matching active profiles are set. During merge, default profiles from the parent are added to the child's default profiles and deduplicated.

If the child has an active profile, default profiles are not treated as an additional active profile. Check them separately:

~~~java
environment.getActiveProfiles();
environment.getDefaultProfiles();
~~~

This avoids confusion when a bean with `@Profile("default")` is not registered even though the parent has a default profile, because the child has another active profile.

## 6. How Profiles Affect Beans and Configuration Documents

### 6.1. `@Profile` Is Evaluated in the Context Containing the Bean

Example:

~~~java
@Configuration
@Profile("production")
class ProductionConfiguration {
    @Bean
    PaymentPolicy paymentPolicy() {
        return new ProductionPaymentPolicy();
    }
}
~~~

This bean is registered when the configuration is processed in a context with the `production` active profile.

If the parent context has already refreshed with the `production` profile, beans in the parent are created according to the parent's profiles. Later adding the `worker` profile to the child does not cause the parent to rescan configurations or recreate beans for the child's profiles.

Conversely, the child can see beans already created by the parent if those beans are exposed in the hierarchy. If the child needs a different implementation, define a separate bean in the child and design the override/lookup behavior explicitly.

### 6.2. Profile-Specific Configuration Files

Spring Boot can load files such as:

~~~text
application.yml
application-common.yml
application-production.yml
application-worker.yml
~~~

Active profiles in the Environment influence which profile-specific configuration documents are selected. However, which files are actually loaded also depends on Config Data locations, how each context is launched, and the property sources owned by that context.

In a hierarchy with separate Environments:

- The parent can load configuration documents matching the parent's profiles.
- The child can load configuration documents matching the child's profiles.
- After merging, the child can also look up PropertySources inherited from the parent.
- The child seeing parent properties does not mean the child automatically reloads all parent files, or that the parent loads files for the child's profiles.

Distinguish **inheriting existing PropertySources** from **each SpringApplication's Config Data loading flow**.

### 6.3. `spring.profiles.include` and Profile Groups

Spring Boot provides additional profile mechanisms:

- `spring.profiles.include` adds profiles to the active profile set.
- `spring.profiles.group` allows activating a group of profiles by a logical name.
- `spring.profiles.active` specifies the active profile set per property precedence or API.

These properties are processed during Spring Boot's configuration flow and do not replace the rules of `ConfigurableEnvironment.merge(parent)`. In particular, `spring.profiles.active`, `spring.profiles.include`, and `spring.profiles.group` may only be declared in non-profile-specific configuration documents per Spring Boot rules.

Do not confuse a profile being included/grouped in one context with parent beans being re-activated. Each context still runs its own bean registration process.

## 7. Building a Hierarchy with SpringApplicationBuilder

`SpringApplicationBuilder` provides an API to create parent, child, and sibling contexts.

Illustrative example:

~~~java
new SpringApplicationBuilder(SharedParentConfiguration.class)
    .child(OrderConfiguration.class)
    .run(args);
~~~

The parent can hold shared beans. The child holds order business beans. When the builder creates the hierarchy, the contexts' Environments are handled according to the hierarchy mechanism; configuring a shared Environment must be done explicitly, rather than assuming all contexts always use the same Environment object.

It can be extended to siblings:

~~~java
new SpringApplicationBuilder(SharedParentConfiguration.class)
    .child(OrderConfiguration.class)
    .sibling(InventoryConfiguration.class)
    .run(args);
~~~

Exact API details should be checked against your Spring Boot version. In a real application, inspect each created context, its active profiles, PropertySources, and bean visibility rather than just looking at the builder chain.

### 7.1. When Should You Use Parent–Child?

A hierarchy is useful when contexts need:

- To share certain infrastructure beans in the parent.
- Separate business beans or local configuration.
- Separate lifecycles for each group of components.
- The ability to select distinct profiles or PropertySources for a child.
- Configuration separation by logical application within a single JVM.

Do not create a hierarchy just to "share configuration" if a single Environment or a simple configuration object suffices. A hierarchy increases complexity around lifecycle, bean visibility, profiles, and precedence.

## 8. Spring Cloud Bootstrap Context and PropertySource Hierarchy

### 8.1. Legacy Bootstrap Context

In Spring Cloud's traditional bootstrap mode, a bootstrap context is created as the parent of the main application context. The bootstrap context is typically used to load external configuration and perform setup before the main context finishes starting.

In this mechanism:

- The bootstrap context and main context have a parent–child relationship.
- An Environment can be shared through the bootstrap mechanism.
- Remote property sources (for example, from Spring Cloud Config Server) can be added with high precedence.
- `bootstrap.yml` is a convention for bootstrap-phase configuration; it is not synonymous with the remote property source named `bootstrap`.
- Values in `bootstrap.yml` can serve as default configuration for the bootstrap context and have lower precedence than regular application configuration.
- Each context in a hierarchy can have its own bootstrap property sources; avoid inadvertently pushing a parent's local configuration down to all descendants.

Legacy bootstrap mode must be enabled per version guidelines, such as with `spring-cloud-starter-bootstrap` or `spring.cloud.bootstrap.enabled=true` supplied early enough via system properties/environment. Do not assume a bootstrap context automatically appears in every Spring Cloud application.

### 8.2. Remote PropertySource and Overrides

With Spring Cloud Config in bootstrap mode, remote properties are typically placed at high precedence and by default do not allow local configuration to override them. If you want local properties to override remote properties, the remote property source must permit it via `spring.cloud.config.allowOverride=true` configured from the remote server side.

Options such as:

- `spring.cloud.config.overrideNone=true`: allows local property sources to override remote ones under the corresponding policy.
- `spring.cloud.config.overrideSystemProperties=false`: restricts which local sources are allowed to override remote properties.

These are rules of Spring Cloud Config's remote property source in bootstrap mode, not general rules for every PropertySource or every Spring context hierarchy. Check the release train you are using.

### 8.3. Modern Config Data Import

With Spring Boot 2.4 and later, the modern default way to connect Spring Cloud Config Client is Config Data import:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://config-server:8888"
~~~

This approach does not require `bootstrap.yml` for Config Data imports. Remote config is loaded during Spring Boot's Config Data phase.

Distinction:

| Integration approach | Mechanism | Bootstrap file |
| --- | --- | --- |
| Config Data import | `spring.config.import=configserver:...` | Does not require `bootstrap.yml` |
| Legacy bootstrap | Bootstrap parent context loads remote properties before main context | Uses `bootstrap.yml` or corresponding bootstrap config |

Do not mix examples from the two mechanisms without identifying which mode is running. If the system uses legacy bootstrap, check how bootstrap is enabled and where property sources sit. If using Config Data import, check the import configuration and Config Data ordering in the application's Environment.

## 9. Configuration Example for Parent and Child

Suppose an application has a parent with shared configuration and an order child with its own configuration.

Parent source:

~~~yaml
app:
  region: ap-southeast
  timeout: 2s
  logging-mode: compact
~~~

Child source:

~~~yaml
app:
  region: eu-west
  service-name: order-service
~~~

After the child merges the parent Environment (with differently named sources), the child can resolve:

| Property | Value in child | Reason |
| --- | --- | --- |
| `app.region` | `eu-west` | Child source has the same key and is searched first. |
| `app.timeout` | `2s` | Child does not declare it; value from parent remains available. |
| `app.logging-mode` | `compact` | Child inherits the parent's property source. |
| `app.service-name` | `order-service` | Property exists only in the child. |

If the two sources share the same name, the result differs: the parent source with the matching name is excluded from the child's list, so keys present only in that parent source are no longer inherited by the child through that source.

### 9.1. Two Contexts Do Not Necessarily Get the Same Result

The parent still resolves `app.region=ap-southeast` because the parent Environment is not modified when the child merges. The child resolves `app.region=eu-west` because the child's local source precedes the parent source.

This is why you must inspect the Environment of the exact context in question. Calling `environment.getProperty("app.region")` from a bean in the parent and from a bean in the child can return two different results.

## 10. Testing PropertySource and Profile Inheritance

A good test should verify values, the source list, and profiles. Do not assert only one final property and conclude the entire hierarchy is right.

### 10.1. Testing Basic Merging

JUnit-style example:

~~~java
@Test
void childMergesParentPropertiesAndProfiles() {
    ConfigurableEnvironment parent = new StandardEnvironment();
    parent.getPropertySources().addFirst(
        new MapPropertySource("parent", Map.of(
            "app.region", "ap-southeast",
            "app.timeout", "2s"
        ))
    );
    parent.setActiveProfiles("common", "production");

    ConfigurableEnvironment child = new StandardEnvironment();
    child.getPropertySources().addFirst(
        new MapPropertySource("child", Map.of(
            "app.region", "eu-west"
        ))
    );
    child.setActiveProfiles("worker");

    child.merge(parent);

    assertEquals("eu-west", child.getProperty("app.region"));
    assertEquals("2s", child.getProperty("app.timeout"));
    assertTrue(Arrays.asList(child.getActiveProfiles())
        .containsAll(List.of("worker", "common", "production")));
}
~~~

The example requires JUnit 5, Spring Core, and the corresponding Java imports. The goal is to verify the Environment merge API without needing to boot a full Spring Boot application.

### 10.2. Testing Same-Named PropertySources

Create a source named `shared` in both parent and child, each containing a distinct key. After merging, verify:

- The key from the child source is present.
- The key from the same-named parent source does not appear in the child.
- The parent can still query its original key.

This test helps catch a subtle misconfiguration: two components sharing a generic PropertySource name while expecting keys from both sources to accumulate.

### 10.3. Testing Profiles and `@Profile`

Create a parent bean with `@Profile("production")` and a child bean with `@Profile("worker")`. Initialize each context with the appropriate active profiles, merge the Environment before refreshing the child, and then verify that beans are registered in the right contexts.

Verify:

- When the parent has the `production` profile, the production bean is created in the parent.
- When the child receives the `worker` profile and inherited profiles, the matching bean is created in the child.
- Changing the child's profiles after the parent has already refreshed does not cause the parent to recreate beans.
- If the Environment is shared, profile changes must be evaluated across all contexts using that Environment.

### 10.4. Verification Matrix

| ID | Scenario | Expected verification |
| --- | --- | --- |
| H1 | Parent has key, child does not. | Child reads the inherited value. |
| H2 | Parent and child have the same key, differently named sources. | Child value wins. |
| H3 | Parent and child have same-named sources. | Child source is kept; parent's same-named source is omitted from child. |
| H4 | Parent and child share a profile name. | Duplicate profile appears only once after merge. |
| H5 | Parent and child have different profiles. | Child keeps its own profiles and receives the parent's profiles. |
| H6 | Call `setActiveProfiles` after merge. | Current profile set is replaced by the passed list. |
| H7 | Call `addActiveProfile` after merge. | New profile is added while existing profiles remain. |
| H8 | Parent updates Environment after merge. | A separate child Environment does not automatically sync parent changes. |
| H9 | Parent already refreshed, child changes active profile. | Parent beans are not re-registered for the child's profile. |
| H10 | One Environment shared across multiple contexts. | Changes to the shared Environment can affect all referencing contexts. |

## 11. Common Errors and How to Diagnose Them

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| Child cannot read property from parent. | Child did not merge Environment, or parent source was dropped due to name collision. | Check hierarchy and PropertySource names. |
| Child still gets parent value despite local declaration. | Child source sits after parent source, or child is not using the expected Environment. | Inspect source order in the child Environment. |
| Some parent keys disappear after merge. | Parent and child sources have the same name, causing the entire parent source to be dropped. | Use distinct source names or build a merged source intentionally. |
| Parent profile does not appear in child. | Child called `setActiveProfiles` after merge, or merge has not occurred. | Check merge timing and how profiles are configured. |
| Parent profile is in child, but parent beans did not change. | Parent beans were already registered in parent per parent's own profiles. | Check which context owns the bean and refresh timing. |
| Siblings have different profiles. | Each sibling has a separate Environment; this may be expected behavior. | Check whether Environments are separate or shared. |
| Parent changes a property, but child does not change. | Child Environment merged earlier and does not automatically track all parent changes. | Update child explicitly, re-merge at an appropriate lifecycle point, or share an Environment if truly needed. |
| Remote config overrides local. | Remote PropertySource has high precedence or override policy forbids local overrides. | Check bootstrap/config data mode and Config Server override flags. |
| Application has no bootstrap context as in older docs. | Using Config Data import or legacy bootstrap is not enabled. | Check `spring.config.import` and the actual bootstrap mechanism. |

## 12. Principles for Designing a Maintainable Hierarchy

1. **Keep PropertySource names meaningful and unique per scope.** Avoid multiple modules creating generically named sources like `custom` or `config` if they must coexist.
2. **Place shared configuration in the parent.** Put only service-specific configuration in children.
3. **Do not rely on implicit ordering.** Inspect the source list and document precedence when multiple places declare the same key.
4. **Configure profiles before refreshing the context.** `@Profile` beans are selected during bean registration; changing profiles afterward does not automatically recreate all beans.
5. **Decide explicitly between separate vs. shared Environment.** A shared Environment simplifies synchronization at the cost of isolation; separate Environments allow differing configurations but require deliberate merging/propagation.
6. **Do not use a hierarchy just to avoid passing configuration.** Consider Config Data, Config Server, or configuration objects if a hierarchy complicates lifecycle.
7. **Distinguish legacy bootstrap from Config Data import.** Documentation and configuration examples must match the active mode and release train.
8. **Test source collisions and profile inheritance.** These bugs may not surface in a single context, yet cause wrong configuration when a hierarchy is deployed.

## 13. Completion Checklist

- [ ] Can explain parent–child ApplicationContexts and bean visibility.
- [ ] Can distinguish ApplicationContext hierarchy from Environment hierarchy.
- [ ] Can describe how property sources and active/default profiles are merged.
- [ ] Knows that child sources take precedence over sources inherited from parent when source names differ.
- [ ] Knows that a same-named child source replaces the parent's same-named source rather than merging key-by-key.
- [ ] Can distinguish `setActiveProfiles` and `addActiveProfile`.
- [ ] Can explain why profile inheritance does not cause parent beans to be re-registered.
- [ ] Can distinguish profile-specific config loading from PropertySource inheritance.
- [ ] Knows when `SpringApplicationBuilder` uses separate Environments vs. a shared Environment.
- [ ] Can distinguish the legacy bootstrap context from Config Data import.
- [ ] Understands Spring Cloud Config's remote PropertySource override policy.
- [ ] Has tests for key precedence, source-name collisions, profile merging, and context lifecycle.
- [ ] Has conventions for naming PropertySources and organizing shared vs. local configuration.

**Official documentation to cross-reference for your project version:**

- [Spring Framework – ConfigurableEnvironment](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html): PropertySource manipulation, active/default profiles, and `merge(parent)`.
- [Spring Cloud Commons – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): bootstrap context, hierarchy, Environment changes, and remote PropertySources.
- [Spring Cloud Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data import, legacy bootstrap, and fetching remote configuration.
- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): active/default profiles, includes, profile groups, and profile-specific documents.

APIs, bootstrap mechanisms, and precedence may differ across Spring Boot/Spring Cloud versions. When applying to a project, verify against your exact release train and test each context's Environment before drawing conclusions.
