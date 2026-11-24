# Using withParent to Verify SearchStrategy in an ApplicationContext Hierarchy

## Lesson goal

Spring allows an ApplicationContext to have a **parent context**. A child context can use beans provided by the parent context, whereas the parent context does not see beans registered only in the child context. This structure appears in applications with multiple configuration scopes, servlet applications with root/child contexts, or systems that isolate a subset of beans per context.

Spring Boot provides SearchStrategy so bean conditions can decide their search scope across the context hierarchy. Without understanding this scope, an auto-configuration may skip a default bean because it sees a bean in the parent, or create an extra bean in the child even though the parent already has a bean of the same type.

This lesson focuses on verifying the three strategies with ApplicationContextRunner.withParent(...):

- CURRENT: searches only in the current context.
- ANCESTORS: searches in all ancestor contexts, excluding the current context.
- ALL: searches the entire hierarchy, including the current context and all ancestors.

After this lesson, you will be able to explain the differences among the three strategies, predict bean condition outcomes, write isolated parent/child tests, and decide when an explicit strategy is needed instead of the default.

## 1. Why does an ApplicationContext have a parent?

An ApplicationContext manages bean definitions, singleton instances, Environment, event infrastructure, and other container services. One context can be attached to a parent to organize multiple configuration scopes.

Conceptual example:

~~~text
Root ApplicationContext
  - DataSource
  - SharedService
  - Security infrastructure
       |
       +---- Child ApplicationContext A
       |       - Controller A
       |       - ViewResolver A
       |       - Feature A beans
       |
       +---- Child ApplicationContext B
               - Controller B
               - ViewResolver B
               - Feature B beans
~~~

A child context can look up beans in itself and continue looking upward in the parent when needed. The parent context does not look downward into child contexts. Therefore, two contexts can contain beans of the same type while preserving separate scopes.

A common example is a servlet application with a root context containing services/repositories and one or more servlet-specific child contexts containing controllers, handler mappings, or view configuration. A context hierarchy can also be built in tests to simulate a shared module and a specialized module.

**Do not confuse a parent context with Java class inheritance.** This is a runtime relationship between BeanFactory/ApplicationContext instances. Beans in the parent are not copied into the child; the child can look up beans in the parent according to hierarchy rules.

## 2. The three SearchStrategy values differ by search scope

Spring Boot defines the SearchStrategy enum in package org.springframework.boot.autoconfigure.condition.

| Strategy | Search scope | When does the condition see the bean? |
| --- | --- | --- |
| CURRENT | Only the context evaluating the condition | The bean must be registered in the current context |
| ANCESTORS | All parents/ancestors; ignores the current context | The bean must reside in an ancestor context |
| ALL | Entire tree: the current context and all ancestors | The bean can reside in current or any parent |

Visualization when the condition is evaluated in Child:

~~~text
                 ALL
       +-----------------------+
       |                       |
   Parent A                Parent B
       |                       |
       +-----------+-----------+
                   |
                Child
                   |
CURRENT:           |  Child only
ANCESTORS: Parent A + Parent B, excluding Child
ALL:        Parent A + Parent B + Child
~~~

For a context with a single parent, ANCESTORS and ALL can both see beans in the parent. The critical difference appears when the bean resides in the child itself: ANCESTORS ignores it, whereas ALL and CURRENT see it.

### 2.1. CURRENT

CURRENT restricts the check to the current context's BeanFactory. If the child needs a bean created and owned directly inside the child, this strategy prevents the condition from being satisfied merely because the parent has a bean of the same type.

For example, a per-tenant child context needs to create its own TenantFeature. The parent may provide a shared service, yet should not cause the local feature's condition to match automatically. In that case, CURRENT is the right choice.

### 2.2. ANCESTORS

ANCESTORS searches only ancestor contexts, walking from the immediate parent up to higher ancestors. It ignores beans located in the current child.

This strategy is useful when a feature should activate only if a foundational service has already been provided at the parent level. For example, a child context registers an adapter only if the root context provides a SharedInfrastructure bean.

An easy-to-miss consequence: if the child already has the bean while the parent does not, a condition with ANCESTORS still treats that bean as absent.

### 2.3. ALL

ALL searches the entire hierarchy. This is the default choice for Spring Boot bean condition annotations such as ConditionalOnBean and ConditionalOnMissingBean. ConditionalOnSingleCandidate also has a search attribute.

With ALL, a bean in the parent can make ConditionalOnBean match in the child. Likewise, a bean in the parent can cause ConditionalOnMissingBean not to match and prevent the child from creating a duplicate default bean.

### 2.4. The default value is ALL

In Spring Boot 3.3, the search attribute of ConditionalOnBean and ConditionalOnMissingBean defaults to SearchStrategy.ALL. ConditionalOnSingleCandidate also defaults to searching the entire hierarchy.

As a result, the following code:

~~~java
@Bean
@ConditionalOnMissingBean(SharedClient.class)
SharedClient sharedClient() {
    return new DefaultSharedClient();
}
~~~

can back off when the parent context already provides SharedClient, even though the child context has no such bean in local scope.

If this is not the desired behavior, set search explicitly:

~~~java
@Bean
@ConditionalOnMissingBean(
        value = SharedClient.class,
        search = SearchStrategy.CURRENT)
SharedClient childSharedClient() {
    return new ChildSharedClient();
}
~~~

Choosing CURRENT or ALL is part of the architectural contract, not merely a syntactic detail.

## 3. SearchStrategy affects the condition, not the context structure

SearchStrategy determines the scope a bean condition uses for checking. It does not alter the parent-child relationship and does not alter normal bean lookup rules.

Distinguish three things:

1. **Condition search:** does the annotation see beans in the parent, the child, or both?
2. **Bean lookup/injection:** when a bean needs a dependency, Spring resolves candidates according to BeanFactory hierarchy, type, qualifier, and primary rules.
3. **Bean ownership:** a bean remains owned by the context that registered it; the child does not turn a parent bean into its own local bean.

For example, if the parent has SharedClient and the child does not, the child can still inject SharedClient from the parent. If you use ConditionalOnBean with CURRENT, the condition may not match even though normal lookup from the child can find the bean in the parent. This is not a contradiction: the condition and dependency lookup are using two different scope rules.

Conversely, if the child has a bean of the same type and uses CURRENT, the condition matches based on the local bean. That does not mean the parent can see the child's bean.

**SearchStrategy is not an implementation-selection tool.** It does not replace @Qualifier or @Primary. If a condition matches and a bean method needs to inject a type with multiple candidates, autowiring rules must still be able to resolve a candidate, such as via qualifier or primary.

## 4. Annotations that have a search attribute

In Spring Boot 3.3, common bean conditions have a search attribute:

| Annotation | Condition meaning | Hierarchy scenario |
| --- | --- | --- |
| ConditionalOnBean | Matches if a bean meeting the requirements is found | Child feature depends on a bean in the parent |
| ConditionalOnMissingBean | Matches if no bean meeting the requirements is found | Decides whether to create a default in the child |
| ConditionalOnSingleCandidate | Matches if a single autowire candidate can be determined | Checks a shared dependency across contexts |

ConditionalOnBean example:

~~~java
@Bean
@ConditionalOnBean(
        value = SharedInfrastructure.class,
        search = SearchStrategy.ANCESTORS)
ChildAdapter childAdapter() {
    return new ChildAdapter();
}
~~~

ChildAdapter is registered only when a SharedInfrastructure bean exists in a parent/ancestor. A bean of the same type existing only in the child does not satisfy this condition.

ConditionalOnMissingBean example:

~~~java
@Bean
@ConditionalOnMissingBean(
        value = ChildFeature.class,
        search = SearchStrategy.CURRENT)
ChildFeature childFeature() {
    return new DefaultChildFeature();
}
~~~

A ChildFeature bean in the parent does not prevent the child from creating a local implementation. This is a reasonable choice if each child needs its own feature instance.

ConditionalOnSingleCandidate example:

~~~java
@AutoConfiguration
@ConditionalOnSingleCandidate(
        value = SharedClient.class,
        search = SearchStrategy.ALL)
class ChildClientAutoConfiguration {
}
~~~

This condition checks whether a single candidate can be determined for type SharedClient within the selected scope. If multiple candidates match, a primary candidate can make choosing one bean unambiguous. SearchStrategy only changes which hierarchy scope is inspected; single-candidate resolution rules still apply.

## 5. Using ApplicationContextRunner.withParent to build a hierarchy in tests

ApplicationContextRunner creates a new non-web context on each run call. The withParent(ApplicationContext) method configures the parent of the context about to be created.

Usage pattern:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(ParentConfiguration.class)
        .run(parent -> {
            new ApplicationContextRunner()
                    .withParent(parent)
                    .withConfiguration(
                            AutoConfigurations.of(ChildAutoConfiguration.class))
                    .run(child -> {
                        // Assert results in the child context.
                    });
        });
~~~

The sequence is:

1. The outer runner creates and refreshes the parent context.
2. The callback receives the active parent context.
3. The inner runner uses that parent to create the child context.
4. The child is refreshed and conditions are evaluated within the hierarchy.
5. The child callback performs assertions.
6. The child runner closes the child after its callback finishes; then the outer runner closes the parent.

AssertableApplicationContext provided by the runner is also an ApplicationContext, so it can be passed directly into withParent.

**Use AutoConfigurations.of(...) for the auto-configuration under test.** This preserves the role of auto-configuration and its processing order relative to user configuration. Bean conditions see only bean definitions processed up to evaluation time; Spring Boot recommends placing ConditionalOnBean/ConditionalOnMissingBean on auto-configurations and declaring ordering when depending on a bean provided by another auto-configuration.

## 6. Complete JUnit 5 example: testing all three strategies

The example below uses a Marker interface as the target bean type. The parent context registers ParentMarker; the child context registers features based on condition outcomes.

**File:** src/test/java/example/hierarchy/SearchStrategyHierarchyTest.java

~~~java
package example.hierarchy;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.SearchStrategy;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class SearchStrategyHierarchyTest {

    @Test
    void allAndAncestorsSeeParentButCurrentDoesNot() {
        new ApplicationContextRunner()
                .withUserConfiguration(ParentConfiguration.class)
                .run(parent -> new ApplicationContextRunner()
                        .withParent(parent)
                        .withConfiguration(
                                AutoConfigurations.of(ParentLookupAutoConfiguration.class))
                        .run(child -> {
                            assertThat(child).hasSingleBean(AllFeature.class);
                            assertThat(child).hasSingleBean(AncestorFeature.class);
                            assertThat(child).hasSingleBean(DefaultAllFeature.class);
                            assertThat(child).doesNotHaveBean(CurrentFeature.class);
                        }));
    }

    @Test
    void ancestorsDoesNotSeeBeanDefinedOnlyInCurrentContext() {
        new ApplicationContextRunner()
                .withUserConfiguration(LocalMarkerConfiguration.class)
                .withConfiguration(
                        AutoConfigurations.of(LocalLookupAutoConfiguration.class))
                .run(child -> {
                    assertThat(child).hasSingleBean(LocalMarker.class);
                    assertThat(child).hasSingleBean(AllLocalFeature.class);
                    assertThat(child).hasSingleBean(CurrentLocalFeature.class);
                    assertThat(child).doesNotHaveBean(AncestorLocalFeature.class);
                });
    }

    @Test
    void missingBeanWithDefaultAllBacksOffForParentBean() {
        new ApplicationContextRunner()
                .withUserConfiguration(ParentConfiguration.class)
                .run(parent -> new ApplicationContextRunner()
                        .withParent(parent)
                        .withConfiguration(
                                AutoConfigurations.of(MissingAllAutoConfiguration.class))
                        .run(child -> {
                            assertThat(child).doesNotHaveBean(ChildMarker.class);
                            assertThat(child.getBean(Marker.class))
                                    .isSameAs(parent.getBean(ParentMarker.class));
                        }));
    }

    @Test
    void missingBeanWithCurrentCanCreateChildBeanDespiteParentBean() {
        new ApplicationContextRunner()
                .withUserConfiguration(ParentConfiguration.class)
                .run(parent -> new ApplicationContextRunner()
                        .withParent(parent)
                        .withConfiguration(
                                AutoConfigurations.of(MissingCurrentAutoConfiguration.class))
                        .run(child -> {
                            assertThat(child).hasSingleBean(ChildMarker.class);
                            assertThat(child.getBean(Marker.class))
                                    .isInstanceOf(ChildMarker.class);
                            assertThat(parent.getBean(Marker.class))
                                    .isInstanceOf(ParentMarker.class);
                        }));
    }

    interface Marker {
    }

    static class ParentMarker implements Marker {
    }

    static class LocalMarker implements Marker {
    }

    static class ChildMarker implements Marker {
    }

    static class AllFeature {
    }

    static class AncestorFeature {
    }

    static class CurrentFeature {
    }

    static class DefaultAllFeature {
    }

    static class AllLocalFeature {
    }

    static class AncestorLocalFeature {
    }

    static class CurrentLocalFeature {
    }

    @Configuration(proxyBeanMethods = false)
    static class ParentConfiguration {

        @Bean
        ParentMarker parentMarker() {
            return new ParentMarker();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class LocalMarkerConfiguration {

        @Bean
        LocalMarker localMarker() {
            return new LocalMarker();
        }
    }

    @AutoConfiguration
    static class ParentLookupAutoConfiguration {

        @Bean
        @ConditionalOnBean(
                value = Marker.class,
                search = SearchStrategy.ALL)
        AllFeature allFeature() {
            return new AllFeature();
        }

        @Bean
        @ConditionalOnBean(
                value = Marker.class,
                search = SearchStrategy.ANCESTORS)
        AncestorFeature ancestorFeature() {
            return new AncestorFeature();
        }

        @Bean
        @ConditionalOnBean(
                value = Marker.class,
                search = SearchStrategy.CURRENT)
        CurrentFeature currentFeature() {
            return new CurrentFeature();
        }

        @Bean
        @ConditionalOnBean(Marker.class)
        DefaultAllFeature defaultAllFeature() {
            return new DefaultAllFeature();
        }
    }

    @AutoConfiguration
    static class LocalLookupAutoConfiguration {

        @Bean
        @ConditionalOnBean(
                value = Marker.class,
                search = SearchStrategy.ALL)
        AllLocalFeature allLocalFeature() {
            return new AllLocalFeature();
        }

        @Bean
        @ConditionalOnBean(
                value = Marker.class,
                search = SearchStrategy.ANCESTORS)
        AncestorLocalFeature ancestorLocalFeature() {
            return new AncestorLocalFeature();
        }

        @Bean
        @ConditionalOnBean(
                value = Marker.class,
                search = SearchStrategy.CURRENT)
        CurrentLocalFeature currentLocalFeature() {
            return new CurrentLocalFeature();
        }
    }

    @AutoConfiguration
    static class MissingAllAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(Marker.class)
        ChildMarker childMarker() {
            return new ChildMarker();
        }
    }

    @AutoConfiguration
    static class MissingCurrentAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(
                value = Marker.class,
                search = SearchStrategy.CURRENT)
        ChildMarker childMarker() {
            return new ChildMarker();
        }
    }
}
~~~

### 6.1. Reading each test result

**Test 1 — parent has Marker**

ParentConfiguration registers ParentMarker. Child uses three strategies:
- ALL sees ParentMarker so it creates AllFeature.
- ANCESTORS sees ParentMarker so it creates AncestorFeature.
- CURRENT searches only in child, where no Marker exists yet, so it does not create CurrentFeature.
- DefaultAllFeature also appears because the default search of ConditionalOnBean is ALL.

**Test 2 — only child has Marker**

LocalMarkerConfiguration registers Marker in the current context:
- ALL sees LocalMarker.
- CURRENT sees LocalMarker.
- ANCESTORS ignores the current context so it does not create AncestorLocalFeature.

**Test 3 — default ConditionalOnMissingBean**

Parent has Marker, child has no local Marker. ConditionalOnMissingBean defaults to ALL, so the parent bean causes the condition not to match and child does not create ChildMarker.

**Test 4 — ConditionalOnMissingBean with CURRENT**

Parent still has Marker, but the condition searches only in child. Child has no local Marker yet, so default ChildMarker is created. Parent still retains its own ParentMarker.

These four tests confirm that SearchStrategy affects bean registration decisions in the context being refreshed. They require no database connection, HTTP server, or external service.

## 7. Dependencies and run commands

Requires Java 17+ and Spring Boot 3.3.x. In a Gradle project with versions managed by the Spring Boot plugin or BOM:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Run the test in the module containing the test class:

~~~bash
# Linux/macOS
./gradlew test --tests "example.hierarchy.SearchStrategyHierarchyTest"

# Windows
gradlew.bat test --tests "example.hierarchy.SearchStrategyHierarchyTest"
~~~

**Expected result:** four tests PASS. The tests use AssertJ to verify bean registration; there is no System.out.println so there is no fixed stdout output. Gradle will display test results according to the project's logging configuration.

This is test code designed for Spring Boot 3.3/JUnit 5; it has not been executed in a specific project environment. If running in an existing module, use that module's Spring Boot BOM version and make sure the test package matches the source path.

## 8. When to choose each strategy?

### Choose ALL when the bean may be provided at any layer

Use ALL when the feature only needs to know whether a bean exists somewhere in the application/context hierarchy. This is the common default behavior for auto-configuration bean conditions.

Examples:
- A parent context already provides a shared client.
- The child context does not need to create another default for the same role.
- An infrastructure bean is registered in the root context yet used in the child.

### Choose CURRENT when the feature belongs exclusively to the child

Use CURRENT when the bean must be registered directly inside the context under evaluation. This keeps each child context independent.

Examples:
- Each servlet child context needs its own handler.
- Each tenant context needs its own adapter.
- The parent has a service of the same type, yet the child still needs a local implementation.

Before choosing CURRENT, check whether creating another bean of the same type in the child introduces injection ambiguity. If the child needs a local bean, define clear names/qualifiers and specify which dependency should use the local implementation.

### Choose ANCESTORS when only the parent may provide the dependency

Use ANCESTORS when the child should enable a feature only if infrastructure is supplied from the parent. If the child creates that bean itself, the condition does not match; this can be intentional to enforce a clear ownership boundary.

Examples:
- A child adapter activates only when the root context has SharedInfrastructure.
- A feature depends on a shared registry and should not be triggered by a local registry mistakenly declared in the child.

Do not choose ANCESTORS merely because its name sounds closer to parent. Determine whether a bean in the current context should be allowed to satisfy the condition.

## 9. Notes when applying in real auto-configuration

### 9.1. Bean conditions depend on processing order

ConditionalOnBean and ConditionalOnMissingBean can evaluate only bean definitions processed up to the moment the condition runs. Therefore, Boot recommends using them on auto-configurations; auto-configurations are designed to apply after user configuration.

If a condition depends on a bean created by another auto-configuration, declare appropriate ordering:

~~~java
@AutoConfiguration(after = SharedInfrastructureAutoConfiguration.class)
class ChildFeatureAutoConfiguration {
}
~~~

Ordering only ensures the dependent configuration's bean definitions are processed after the configuration providing the dependency. It does not instantiate beans and does not replace constructor injection.

### 9.2. A parent bean can still be injected even when CURRENT does not see it

An easy-to-misunderstand situation:

- Parent contains SharedService.
- Child uses ConditionalOnBean(search = CURRENT) and the condition does not match.
- Another bean in the child can still inject SharedService from the parent via normal lookup.

That is valid. CURRENT restricts only the condition search; it does not disable the child's ability to look up beans from the parent.

### 9.3. Parent and child can contain the same bean type

If the child creates a bean of the same type as the parent, the child normally uses its local bean when looking up by type within the child itself; the parent still keeps its own bean. Use qualifiers if you need explicit disambiguation, especially when multiple candidates exist or dependencies cross layers.

SearchStrategy does not resolve ambiguity. If an ALL condition sees one bean in the parent and one bean in the child, it only confirms presence within the scope; injecting a single dependency still follows candidate, @Primary, and @Qualifier rules.

### 9.4. Do not use conditions as a lifecycle control mechanism

SearchStrategy is not a tool for opening/closing contexts, sharing instances, or managing scopes. It only adjusts where bean conditions search. If you need singleton beans per tenant, request, or servlet, design the appropriate context/scope.

### 9.5. Non-web vs. web context tests

ApplicationContextRunner creates non-web contexts. If the real hierarchy consists of a root WebApplicationContext and servlet child contexts, use WebApplicationContextRunner or construct an appropriate web context. The semantics of SearchStrategy remain unchanged, while the context factory and web bean types match the actual application.

## 10. Common mistakes when testing SearchStrategy

1. **Not using withParent.** Two independent runners do not form a hierarchy; conditions in a child cannot see beans in another context unless that context is set as its parent.
2. **Using CURRENT while expecting a parent bean to satisfy the condition.** CURRENT searches only the context evaluating the condition.
3. **Using ANCESTORS while expecting a child bean to satisfy the condition.** ANCESTORS excludes the current context from the search scope.
4. **Assuming ALL searches only the parent.** ALL includes both the current context and all ancestors.
5. **Forgetting the ALL default.** ConditionalOnBean/ConditionalOnMissingBean can be affected by parent beans even when the code does not declare search.
6. **Confusing condition search with dependency lookup.** A child can inject a parent bean even if a condition using CURRENT did not match.
7. **Assuming the parent sees the child.** Lookup flows from child up to parent; the parent never searches down into children.
8. **Using ConditionalOnMissingBean on regular configuration processed too early.** Conditions see only already-processed bean definitions; use them in auto-configuration and declare ordering when depending on other configurations.
9. **Checking beans from the wrong scope in assertions.** Assertions may look up beans in the parent by default; when you need to check a local bean, use scoped assertions or inspect the source context's BeanFactory.
10. **Creating two beans of the same type without distinguishing them.** The condition may match while autowiring remains ambiguous; use qualifiers/primary and test the dependency separately.
11. **Closing the parent before running the child.** The child needs the parent active for the duration of the test; nest runners as shown so lifecycles are managed properly.
12. **Using ApplicationContextRunner for servlet hierarchy tests without checking context type.** For web applications, choose the appropriate runner or context factory.

## 11. Checklist when designing or reviewing conditions

Before adding the search attribute, answer:

- Which context does the target bean belong to: current, parent, or any layer?
- If the parent has the bean, should the child still create its own default?
- If the child has the bean while the parent does not, should the condition match?
- Are there multiple parents/ancestors, and should beans in distant ancestors count?
- Is the annotation being used ConditionalOnBean, ConditionalOnMissingBean, or ConditionalOnSingleCandidate?
- Does it depend on a bean created by another auto-configuration? If so, is ordering explicit?
- Does the bean method have an ambiguous dependency type requiring qualifier/primary?
- Has the test created a real parent using withParent?
- Has the test verified both local beans and beans inherited from the parent?

A small decision table is usually enough for review:

| Where is the bean? | CURRENT | ANCESTORS | ALL |
| --- | --- | --- | --- |
| Only in child | Seen | Not seen | Seen |
| Only in parent | Not seen | Seen | Seen |
| In both child and parent | Sees child | Sees parent | Sees entire hierarchy |
| Nowhere | Not seen | Not seen | Not seen |

The table describes search scope. For ConditionalOnMissingBean, invert the logical outcome: the condition matches when no matching bean is found within the selected scope.

## 12. Self-check questions

**Question 1.** The parent context has Marker, and the child context does not. Does ConditionalOnBean(Marker.class, search = CURRENT) match?

**Answer:** No. CURRENT inspects only bean definitions in the child.

**Question 2.** The child context has Marker, and the parent does not. Does ConditionalOnBean(Marker.class, search = ANCESTORS) match?

**Answer:** No. ANCESTORS searches only ancestor contexts, not the current child.

**Question 3.** The parent has Marker, and the child does not. Does the default ConditionalOnMissingBean(Marker.class) create a default bean in the child?

**Answer:** No. The default search is ALL, so the parent bean counts and the missing condition does not match.

**Question 4.** If each child context should be able to create its own default even when the parent already has a bean of the same type, which strategy should be used?

**Answer:** CURRENT for ConditionalOnMissingBean, if the application policy is to inspect only local beans in the child.

**Question 5.** A bean condition using CURRENT does not match because the bean lives only in the parent. Can another bean in the child still inject that parent bean?

**Answer:** Yes. SearchStrategy changes only condition scope; normal lookup/injection from the child can still find beans in the parent.

## 13. Takeaways

withParent creates a real ApplicationContext hierarchy for verifying bean conditions. CURRENT searches the current context; ANCESTORS searches parent contexts without inspecting current; ALL searches the entire tree. ConditionalOnBean and ConditionalOnMissingBean default to ALL, so a bean in the root/parent can affect auto-configuration running in a child.

Choose the strategy based on where the bean is owned and which scope the feature needs to observe. Use ApplicationContextRunner.withParent to test cases where the bean is only in the parent, only in the child, and found across the entire hierarchy. Finally, remember that condition search does not replace bean lookup, qualifiers, primary, or auto-configuration processing order.

### Official Spring Boot documentation

- Spring Boot 3.3 — SearchStrategy Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SearchStrategy.html
- Spring Boot 3.3 — ConditionalOnBean Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html
- Spring Boot 3.3 — ConditionalOnMissingBean Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot 3.3 — ApplicationContextRunner Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.3 — AbstractApplicationContextRunner Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/AbstractApplicationContextRunner.html
