# Overlapping Scan Conflicts and Module-Based Scan Boundaries in Spring Core Container

## 1. The Problem: Expanding Component Scan in a Multi-Module Project

Suppose a system has three Gradle modules: `catalog` manages the product catalog, `audit` records events, and `app` wires those two capabilities together. Both `catalog` and `audit` define a class with the short name `ReportService` and annotate it with `@Service`:

```text
catalog -> demo.catalog.service.ReportService
audit   -> demo.audit.service.ReportService
app     -> ApplicationContext configuration
```

Each Java class has a different fully qualified name, so **there is no conflict for the Java compiler**. However, if the component scanner discovers both classes inside the same Spring `BeanDefinitionRegistry`, the default naming strategy may assign both the bean name `reportService`. The container then cannot register two incompatible bean definitions under the same name and will throw an error.

Another scenario: the application scans `demo.catalog` and simultaneously scans `demo.catalog.service`. A component inside `demo.catalog.service` appears in both regions. Does **overlapping scanning** always create two instances or throw an error? **Not necessarily.** The Spring scanner checks already-registered bean definitions; if the second candidate comes from the same source or is compatible, the scanner normally **skips duplicate registration** and does not create a second bean.

Therefore, distinguish clearly between:

- **Overlapping scanning:** the same class is discovered across multiple passes or intersecting package roots.
- **Name conflict:** incompatible bean definitions sharing the same bean name.
- **Type collision:** multiple beans having types compatible with a single dependency, causing ambiguity during autowiring.
- **Registration via multiple mechanisms:** the same or different classes appearing via `@ComponentScan`, `@Bean`, `@Import`, auto-configuration, or programmatic bean registration; the outcome depends on source and override policy.

The goal of this lesson is to understand the rules, choose accurate scan boundaries by Java package and Gradle module, analyze real-world errors, and build a Java 17+ Spring Framework example demonstrating **no error**, **conflict**, and **resolution**.

## 2. Scanning Model: Classpath, Packages, and Bean Registry

`@ComponentScan` from `org.springframework.context.annotation` instructs Spring to discover component candidates in one or more base packages. By default, the scanner picks up `@Component` and stereotypes such as `@Service`, `@Repository`, `@Controller`, `@Configuration`, or custom stereotypes meta-annotated with `@Component`.

When `@ComponentScan(basePackages = "demo.catalog")` is processed:

```text
Runtime classpath containing .class files of dependent modules
                     |
                     v
Spring scans demo.catalog and its subpackages
                     |
                     v
Applies stereotypes + exclude/include filters/conditions
                     |
                     v
BeanNameGenerator generates a name for each bean definition
                     |
                     v
BeanDefinitionRegistry checks name / compatibility
                     |
                     v
  Register new definition, skip compatible duplicate,
  or fail if colliding with an incompatible definition
                     |
                     v
ApplicationContext instantiates beans per scope/lifecycle
```

**Three distinct namespaces:**

1. **Java package**: for example `demo.catalog.service`. It defines the Java namespace and the class search range of the component scanner.
2. **Build module**: for example Gradle project `:catalog`. It determines which classes are compiled and placed on another module's runtime classpath.
3. **Spring bean name**: for example `reportService`. This is the key used to register/look up beans in a specific `BeanFactory`/registry.

Spring **does not automatically treat a Gradle module name as a scan scope**. Two Gradle modules can share the same Java package prefix; one Gradle module can contain multiple packages; one package can span multiple JARs. The component scanner operates on packages + classpath, rather than accepting a command like "scan only Gradle module A" via `@ComponentScan`.

### 2.1. A Class on the Classpath Is Not Guaranteed to Be a Bean

For a class to be registered via scanning, all of the following are required simultaneously:

- The artifact containing the `.class` file is present on the runtime classpath (or matching module path).
- The class's package lies inside a scanned base package.
- The class is a valid candidate (concrete, independent, matching stereotype/filters).
- It is not excluded by `@Profile`, `@Conditional`, or exclude filters.
- Its bean name/metadata can be registered without causing an incompatible conflict.

Having `implementation project(':audit')` in Gradle only makes `audit` classes available to `app`; it **does not automatically open component scanning** into `demo.audit`.

### 2.2. Per-`ApplicationContext` Registry

Bean names are unique within **a single registry**, not across the entire JVM. Two independent `ApplicationContext`s can both have a bean named `reportService` without conflict. Conflicts occur when two incompatible definitions enter **one** registry under the same name.

In parent-child context relationships, bean lookup from parent/child and shadowing behavior depend on bean names/locations. Do not assume two beans with the same name in **two different contexts** are equivalent to a registration conflict in one registry.

## 3. When Overlapping Scans Cause No Error: Compatible Candidates

Spring's `ClassPathBeanDefinitionScanner` has a `checkCandidate(beanName, definition)` step. Its meaning:

- No existing bean definition with the same name: the candidate can be registered.
- Existing compatible definition: the scanner **skips the duplicate candidate**.
- Existing incompatible definition: the scanner may throw an error, typically involving `ConflictingBeanDefinitionException`.

With two intersecting roots:

```java
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackages = {
        "demo.catalog",
        "demo.catalog.service"
})
class OverlappingConfig {
}
```

If `demo.catalog.service.ReportService` is a concrete bean class with a stereotype and no conflicting registration, the `demo.catalog` root already covers this class; subsequently scanning the `demo.catalog.service` root encounters the same component. By default, Spring recognizes the compatible duplicate and does not create two independent beans just because two roots intersect.

This is an **illustrative configuration snippet**, run in full in section 7's example.

**Do not overgeneralize:** compatibility does not mean every kind of duplicate is safe. If two sources register different bean definitions under the same name, check/override policies also depend on definition type, registry configuration, and registration order. With two different classes discovered by the scanner, a name conflict is an entirely different issue from scanning *the same class* twice.

### 3.1. Scanning One Class Twice Does Not Mean Two Singletons

A default singleton component is registered into the registry **once** under the same bean name during a compatible overlapping scan. Lookups return the same singleton; no "second singleton" is created by overlapping scans.

If you genuinely need two bean instances of the same class with different configurations, declare two intentional bean definitions (for example, two `@Bean` methods with different names and parameters) and manage scope/lifecycle; do not use overlapping scans to try to create two instances.

### 3.2. Do Not Rely on Scan Order to Resolve Conflicts

Filesystem/classpath scanning order should never be a business contract. Truly conflicting bean definitions must be fixed via naming, scan boundaries, or explicit registration. Never design logic assuming "whichever class is scanned first wins", because changing JARs, builds, or package layouts can alter behavior.

## 4. When Identical Names on Two Different Classes Cause a Conflict

By default, `AnnotationBeanNameGenerator` typically uses the **short class name** per JavaBeans rules, e.g. `ReportService` -> `reportService`.

Suppose:

```java
// catalog/src/main/java/demo/catalog/service/ReportService.java
package demo.catalog.service;

import org.springframework.stereotype.Service;

@Service
public class ReportService {
}
```

and:

```java
// audit/src/main/java/demo/audit/service/ReportService.java
package demo.audit.service;

import org.springframework.stereotype.Service;

@Service
public class ReportService {
}
```

Both files are valid because their Java packages differ. However, scanning both:

```java
@Configuration
@ComponentScan(basePackages = {"demo.catalog", "demo.audit"})
class ConflictConfig {
}
```

can cause both to be registered under the bean name `reportService`. Because the bean classes differ, the scanner encounters two incompatible definitions and throws `ConflictingBeanDefinitionException` (sometimes wrapped in a higher-level exception).

The error message usually includes the name `reportService`, the fully qualified names of both classes, and wording like "conflicts with existing ... bean definition." When diagnosing, read **both class names** and the **bean name** in the exception rather than only searching for the word "duplicate."

### 4.1. Solutions Ranked by Level of Necessity

**Option A — Scan only the module actually needed.** If `app` only uses catalog, restrict the scanner to `demo.catalog`. Do not pull audit components into the registry merely because the audit library is also on the classpath.

**Option B — Assign distinct explicit names on components.** If both services are needed:

```java
@Service("catalogReportService")
public class ReportService {
}
```

in catalog and:

```java
@Service("auditReportService")
public class ReportService {
}
```

in audit. Both snippets are **illustrative variants** belonging to the two separate files/packages above. Explicit names distinguish them and stay stable across class renames, though string references depending on the old name must be updated.

**Option C — Fully-qualified bean names.** Spring provides `FullyQualifiedAnnotationBeanNameGenerator` to generate fallback bean names from package-qualified class names:

```java
@Configuration
@ComponentScan(
    basePackages = {"demo.catalog", "demo.audit"},
    nameGenerator = FullyQualifiedAnnotationBeanNameGenerator.class
)
class QualifiedConfig {
}
```

Then the two beans can be named `demo.catalog.service.ReportService` and `demo.audit.service.ReportService`. This generator still preserves explicit stereotype names; if both classes declare `@Service("reportService")`, **it will not automatically eliminate the explicit name conflict**.

**Option D — Explicit registration.** If you do not want to scan all of audit, the audit module can expose a `@Configuration` providing beans via `@Bean(name = "...")`, or use `@Import` to register the needed classes/configurations. This establishes a clearer module boundary contract, especially for libraries with many internal components.

### 4.2. Changing the Generator Does Not Resolve Type Ambiguity

Two beans with different names that both implement interface `ReportPort` can both register successfully. If a constructor injects **a single** `ReportPort` without a selection policy, Spring can still throw `NoUniqueBeanDefinitionException`.

| Problem | Symptom | Fix |
| --- | --- | --- |
| Duplicate bean name | Two incompatible definitions share a key; conflict during registration | Distinct explicit names, FQ generator, narrow scan |
| Multiple candidates by type | Two distinct bean names, yet caller requests one shared interface/type | `@Qualifier`, `@Primary`, or collection injection design |
| Missing bean | Not scanned/imported, missing runtime dependency, or excluded by condition | Fix packages/classpath/configuration |
| Same class scanned compatibly twice | Scanner sees the same definition across intersecting regions | Usually skips duplicate registration; still simplify scan if possible |

## 5. Scan Boundaries in Multi-Module Projects

A multi-module project might be organized by responsibility:

```text
workspace/
├── app/           -> demo.app
├── catalog/       -> demo.catalog
├── audit/         -> demo.audit
└── contracts/     -> demo.contracts (interfaces/DTOs)
```

In the build, `app` may depend on `catalog` and `audit`; `catalog` and `audit` may both depend on `contracts`. However, **component scanning does not infer module boundaries from the dependency graph**.

When configuring:

```java
@ComponentScan(basePackages = "demo")
```

Spring inspects all component candidates in `demo` and its subpackages **present on the runtime classpath**. This can pull unwanted adapters, internal services, demo/test-support configurations, or optional integrations into the container and trigger conflicts.

Instead of scanning too broadly, clearly define the "application composition root":

- Which modules actually provide beans to the current application?
- What are each module's **public API** packages or **configuration entry points**?
- Which modules need internal components isolated, exposing beans only via `@Bean`/`@Import`?
- Do any tests or profiles intend to build a context with only a subset of modules?
- When a new dependency appears on the classpath, should all components inside it automatically join runtime?

A library module can expose a **public configuration class** for the application to `@Import` instead of requiring a scan of all internal packages. That design makes integration targeted and limits unexpected naming conflicts.

### 5.1. `basePackageClasses` Helps Restrict by Package Root

`@ComponentScan(basePackageClasses = CatalogMarker.class)` uses the package containing `CatalogMarker` as the scan root. If the marker sits in `demo.catalog`, Spring scans `demo.catalog` and its subpackages.

```java
@Configuration
@ComponentScan(basePackageClasses = {
        CatalogMarker.class,
        AuditMarker.class
})
class ModuleComposition {
}
```

This is an illustrative snippet requiring markers in the corresponding root packages. Marker classes do not need stereotypes. This approach is **more type-safe than package strings during refactoring**, yet it still selects a **Java package root** rather than strictly bounding by Gradle module/JAR. If two modules share package `demo.catalog`, the scanner can read classes from both if both are on the classpath.

If you only want to expose **a few beans** from a module whose package contains many internal components, `basePackageClasses` is not enough; use explicit configuration, appropriate filters, or split packages architecturally.

### 5.2. Overlapping Scans into Subpackages

`@ComponentScan(basePackages = {"demo.catalog", "demo.catalog.service"})` is redundant if `demo.catalog` is already scanned. The subpackage is already covered. Removing the second root is recommended for readability, even though compatible duplicate scanning usually causes no error.

A root of `demo.catalog.service` **does not cover** sibling `demo.catalog.persistence`. If a service depends on a repository in the sibling package, a narrow configuration can cause `UnsatisfiedDependencyException`. Do not fix it by hastily widening to `demo`: pick the proper common root `demo.catalog` or explicitly import/register the required beans.

### 5.3. Spring Boot and Module Boundaries

In Spring Boot, `@SpringBootApplication` includes component scanning; by default the root is usually the package containing the application class. Placing the class at the application root scans the application's subpackages, whereas placing the root too high (e.g., `demo`) can scan library modules sharing that prefix.

You can configure:

```java
@SpringBootApplication(
    scanBasePackageClasses = {
        CatalogMarker.class,
        AuditMarker.class
    }
)
public class MainApplication {
}
```

This is an illustrative Boot snippet requiring appropriate dependencies/imports. In Boot, `scanBasePackages`/`scanBasePackageClasses` control **component scanning**, and do not replace **JPA entity scanning** or **Spring Data repository scanning** (`@EntityScan`, `@EnableJpaRepositories` in appropriate contexts). A Spring Data repository interface does not get a proxy created by the component scanner merely for sitting in a scanned package; Spring Data has its own mechanism.

**Customization note:** if manually adding `@ComponentScan` onto a Boot class, check the default filters Boot supplies via the composed annotation and active configurations. Do not treat replacing scan annotations as a completely harmless change.

### 5.4. Conditions for a Module's Beans to Appear

| Condition | Impact |
| --- | --- |
| Dependency on the module is on the runtime classpath | Classes are available for the scanner to find |
| Module's packages lie within scan roots | Components have a chance to become candidates |
| Proper stereotypes/filters match | Candidates proceed to evaluation |
| `@Profile`/`@Conditional` match | Beans are registered in the matching environment |
| Bean names do not conflict | Registry can complete registration |
| Bean dependencies are satisfied | Instances can be created normally |

**Key point:** "the module is in the build" and "the module's beans exist in the container" are two separate things.

## 6. Other Duplicate Sources Beyond Two Scan Passes

### 6.1. `@Component` and `@Bean` Registering the Same Responsibility

```java
@Component
class MessageSender {
}

@Configuration
class SenderConfig {
    @Bean
    MessageSender messageSender() {
        return new MessageSender();
    }
}
```

This is an **illustrative snippet**. If the component is scanned and the `@Bean` method is also processed, you can encounter overlapping registration: duplicate names, one definition ignored/overridden depending on configuration, or multiple beans of the same type if names differ. The exact outcome depends on names and registry policy; **do not assume each path always yields a separate bean**.

For an application component, one registration path is usually enough. For third-party classes whose source you cannot edit, `@Bean` is the clear choice.

### 6.2. `@Import` and `@ComponentScan` Both Discovering a Configuration

A `@Configuration` class that is both component-scanned and `@Import`ed can enter two registration paths. Spring's configuration class processor has mechanisms for handling configuration metadata/candidates, yet incompatible names/sources still need review. Avoid relying on importing/scanning the same class multiple times to increase instance counts or "ensure" processing.

### 6.3. Bean Overriding and "Hiding" Errors

`BeanDefinitionRegistry` has a bean definition overriding policy depending on implementation/configuration. **Enabling overriding is not a default fix** for conflicts:

- For collisions between two incompatible scanned definitions, the scanner may throw `ConflictingBeanDefinitionException` rather than letting the second definition override.
- For other registration sources, overriding can silently swap out an expected bean.
- Modern Spring Boot disables overriding by default unless explicitly enabled; do not flip a global override setting just to dodge an unexplained error.

The right direction is clarifying **who owns the bean name**, which packages are scanned, and where beans are created. If intentionally replacing a bean via profiles/conditions, choose official extension points or policies rather than relying on registration order.

### 6.4. Component Scanning Does Not Automatically Create Spring Data Repositories

An interface `JpaRepository<Order, Long>` is normally registered by Spring Data as a repository proxy via its own scanning mechanism. When tracking bean name conflicts, distinguish names generated by the component scanner, repository scanner, and factory methods. Changing `@ComponentScan` does not necessarily affect other registry extensions.

## 7. Complete Java 17+ and Spring 6 Example: Three Gradle Modules

This example demonstrates three cases:

1. Overlapping scan of the catalog package: one component still produces a single compatible bean definition.
2. Scanning both catalog and audit with default names: two `ReportService` classes in different packages cause a `reportService` name conflict.
3. Scanning both using `FullyQualifiedAnnotationBeanNameGenerator`: both register cleanly under distinct names.

The project uses Spring Framework `6.2.18` and a Gradle multi-project setup, requiring no Spring Boot, web server, or database.

### 7.1. Project Structure

```text
component-scan-modules/
├── settings.gradle
├── build.gradle
├── catalog/
│   ├── build.gradle
│   └── src/main/java/demo/catalog/service/ReportService.java
├── audit/
│   ├── build.gradle
│   └── src/main/java/demo/audit/service/ReportService.java
└── app/
    ├── build.gradle
    └── src/main/java/demo/app/ScanConflictDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'component-scan-modules'
include 'catalog', 'audit', 'app'
```

Root `build.gradle`:

```groovy
subprojects {
    apply plugin: 'java'

    repositories {
        mavenCentral()
    }

    tasks.withType(JavaCompile).configureEach {
        options.release = 17
    }
}
```

Each subproject gets the Java plugin, Maven Central, and Java 17 compilation target. Run Gradle with a compatible JDK; for this example, use JDK 17 or higher.

File `catalog/build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}
```

File `audit/build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}
```

File `app/build.gradle`:

```groovy
plugins {
    id 'application'
}

dependencies {
    implementation project(':catalog')
    implementation project(':audit')
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'demo.app.ScanConflictDemo'
}
```

From `app`, both modules are placed on the runtime classpath by Gradle dependencies. Yet each context still controls which packages are component-scanned.

### 7.2. Catalog Component

File `catalog/src/main/java/demo/catalog/service/ReportService.java`:

```java
package demo.catalog.service;

import org.springframework.stereotype.Service;

@Service
public class ReportService {
    public String report() {
        return "catalog";
    }
}
```

Default bean name in a regular scan pass is `reportService`.

### 7.3. Audit Component

File `audit/src/main/java/demo/audit/service/ReportService.java`:

```java
package demo.audit.service;

import org.springframework.stereotype.Service;

@Service
public class ReportService {
    public String report() {
        return "audit";
    }
}
```

Even though the short class name matches catalog, the fully qualified Java name `demo.audit.service.ReportService` is a different type. The default bean name is still `reportService` if the class is discovered by the scanner.

### 7.4. Main Class with Three Contexts

File `app/src/main/java/demo/app/ScanConflictDemo.java`:

```java
package demo.app;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.FullyQualifiedAnnotationBeanNameGenerator;

public class ScanConflictDemo {

    @Configuration(proxyBeanMethods = false)
    @ComponentScan(basePackages = {
            "demo.catalog",
            "demo.catalog.service"
    })
    static class OverlapConfig {
    }

    @Configuration(proxyBeanMethods = false)
    @ComponentScan(basePackages = {
            "demo.catalog",
            "demo.audit"
    })
    static class CollisionConfig {
    }

    @Configuration(proxyBeanMethods = false)
    @ComponentScan(
            basePackages = {"demo.catalog", "demo.audit"},
            nameGenerator = FullyQualifiedAnnotationBeanNameGenerator.class
    )
    static class QualifiedConfig {
    }

    private static boolean hasNameConflict(Throwable error) {
        for (Throwable current = error;
                current != null;
                current = current.getCause()) {
            if ("ConflictingBeanDefinitionException"
                    .equals(current.getClass().getSimpleName())) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(OverlapConfig.class)) {
            String[] catalogNames = context.getBeanNamesForType(
                    demo.catalog.service.ReportService.class);
            System.out.println("overlap.beanCount = " + catalogNames.length);
            System.out.println("overlap.defaultName = " +
                    context.containsBean("reportService"));
        }

        boolean conflictFound = false;
        try (var context =
                     new AnnotationConfigApplicationContext(CollisionConfig.class)) {
            // Does not enter this branch when two bean definitions conflict.
        } catch (RuntimeException exception) {
            if (!hasNameConflict(exception)) {
                throw exception;
            }
            conflictFound = true;
        }
        System.out.println("default.conflict = " + conflictFound);

        try (var context =
                     new AnnotationConfigApplicationContext(QualifiedConfig.class)) {
            System.out.println("qualified.catalog = " +
                    context.containsBean("demo.catalog.service.ReportService"));
            System.out.println("qualified.audit = " +
                    context.containsBean("demo.audit.service.ReportService"));
            System.out.println("qualified.shortName = " +
                    context.containsBean("reportService"));

            String catalog = context.getBean(
                    demo.catalog.service.ReportService.class).report();
            String audit = context.getBean(
                    demo.audit.service.ReportService.class).report();
            System.out.println("qualified.reports = " + catalog + "," + audit);
        }
    }
}
```

The nested configuration classes are `static`, independent of any `ScanConflictDemo` instance, and passed directly into `AnnotationConfigApplicationContext`. The three contexts **do not share a registry**.

Method `hasNameConflict` walks the exception chain by exception class name solely to produce deterministic output without dumping the entire stack trace; if another error occurs, the program rethrows it to avoid masking unrelated configuration errors.

### 7.5. Run Command

From the root directory `component-scan-modules`:

```bash
gradle :app:run --quiet
```

With Gradle Wrapper: `./gradlew :app:run --quiet` (Linux/macOS) or `.\gradlew.bat :app:run --quiet` (Windows PowerShell).

Lines **printed by the program itself**:

```text
overlap.beanCount = 1
overlap.defaultName = true
default.conflict = true
qualified.catalog = true
qualified.audit = true
qualified.shortName = false
qualified.reports = catalog,audit
```

**Note on logs:** Spring may emit warnings/errors to stderr when a context encounters a collision; the block above only shows `System.out.println` lines and does not claim the entire process output consists solely of these lines.

### 7.6. Explaining Each Result

- `overlap.beanCount = 1`: root `demo.catalog` already covers `demo.catalog.service`. Rescanning the subpackage finds the exact original class, so the scanner does not register an incompatible duplicate definition.
- `overlap.defaultName = true`: the catalog class is registered under the default name `reportService`.
- `default.conflict = true`: in `CollisionConfig`, catalog and audit both generate the name `reportService` despite being different classes; the scanner detects the collision.
- `qualified.catalog = true` and `qualified.audit = true`: the fully-qualified generator assigns two separate names.
- `qualified.shortName = false`: neither component declared an explicit name; this strategy does not register a default `reportService` alias.
- `qualified.reports = catalog,audit`: both beans can be retrieved by their respective **fully qualified classes** and each module's method invoked without casting.

**Limitation:** this example only demonstrates component scanning and naming. When both beans implement the same interface, injecting that single interface remains ambiguous even with distinct names; that is an autowiring problem requiring `@Qualifier`/`@Primary` separately.

## 8. Separating Boundaries via Configuration Entry Points

If `audit` is a library, the application might want to **use just one adapter** without scanning every internal class under `demo.audit`.

One option is for the audit module to expose a configuration class:

```java
package demo.audit.config;

import demo.audit.service.ReportService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AuditModuleConfig {

    @Bean("auditReportService")
    ReportService auditReportService() {
        return new ReportService();
    }
}
```

This is an **illustrative design variant**, not part of the runnable project in section 7. Keeping `@Service` on `ReportService` while simultaneously scanning `demo.audit` can create extra definitions or overlapping registrations depending on names/configuration; when moving completely to explicit configuration, **avoid scanning that implementation** or remove the stereotype from the class to prevent double registration.

The application can then use:

```java
@Configuration
@Import(AuditModuleConfig.class)
@ComponentScan(basePackages = "demo.catalog")
class AppComposition {
}
```

This snippet requires imports for `@Configuration`, `@Import`, `@ComponentScan`, and `AuditModuleConfig`. The `@Bean("auditReportService")` method defines precisely one audit bean per the module contract. Benefits:

- The application explicitly chooses which modules/configurations join the context.
- No need to scan all internal packages of the library.
- Bean names/roles exposed via configuration are controlled.
- Avoids accidentally pulling experimental components or optional adapters into the application merely because they sit on the classpath.

However, `@Import`ing a configuration class still allows that configuration to register multiple bean definitions and further imports. Treat it as a **module integration API**, and review configuration contents just like other dependencies.

### 8.1. Considering Auto-Configuration

In Spring Boot, a library can provide auto-configuration registering beans with `@ConditionalOnClass`, `@ConditionalOnMissingBean`, or matching conditions. This is a separate extension point, removing the need for the scanner to scan all library packages. When building a Spring Boot starter, follow Boot auto-configuration conventions instead of forcing users to widen scan roots.

Do not confuse `@ComponentScan` with auto-configuration: a library JAR present on the classpath does not guarantee its beans are registered by component scan, and a bean created by auto-configuration does not require its implementation class to carry `@Component`.

## 9. Duplicate Bean Names and Explicit Names: Notes When Fixing

Using `FullyQualifiedAnnotationBeanNameGenerator` is a good solution for **default names** of two classes in different packages. However, if they declare:

```java
@Service("sharedReport")
class CatalogReportService {
}

@Service("sharedReport")
class AuditReportService {
}
```

The two snippets above are different classes with **the same explicit name**. The fully-qualified generator still respects `"sharedReport"`, so a conflict can still happen. Assign distinct role-based explicit names, or adjust scan boundaries.

A system already using `@Qualifier("reportService")`, `@Resource(name="reportService")`, `getBean("reportService")`, or `Map<String, ReportPort>` will also be impacted when switching to fully-qualified names. Bean names are part of the contract whenever external code/config references them by string.

**Do not proactively change the generator system-wide** just to fix an isolated conflict if the application relies heavily on existing bean names. In that case, a narrower fix such as giving explicit names to the two conflicting components or tightening scan scope may be easier to control.

## 10. Common Errors and Investigation Methods

| Symptom | Likely Cause | How to Check/Fix |
| --- | --- | --- |
| `ConflictingBeanDefinitionException` for `reportService` | Two different classes share a short name across two scanned packages | Compare FQCNs of both classes; use explicit names, FQ generator, or narrow scan |
| Scanning the same package twice with no error | Scanner skips compatible definition from the same class | Expected behavior; do not assume two instances exist |
| Adding `implementation project(':audit')` triggers startup conflict | Audit classes are now on runtime classpath and scan root is wide enough | Narrow roots or use explicit registration instead of scanning every module |
| `NoUniqueBeanDefinitionException` after fixing duplicate names | Two differently named beans implement the same single-injected interface | Select via `@Qualifier`/`@Primary` or inject a collection |
| `NoSuchBeanDefinitionException` after narrowing scan | Required bean resides in a package outside roots | Add the right root or import the module configuration |
| Bean present despite package not being scanned | Created via `@Bean`, `@Import`, Spring Data, auto-config, or another registration | Locate the bean definition source; do not inspect only `@ComponentScan` |
| Class has both `@Component` and `@Bean` | Overlapping registration paths or multiple beans of the same type | Choose one clear strategy; inspect registry |
| Bean overriding enabled yet scanner still reports conflict | Two incompatible scanned definitions may be rejected before normal overriding | Fix naming/scan boundaries; do not rely on overriding |
| Conflict appears only in tests | Test context scans too broadly, imports extra configs, or uses different profiles | Compare test configuration, package roots, and active profiles |
| One module shares a package root with another module | Package-based scanning can pull classes from both JARs | Split packages by module responsibility or use explicit config |
| Library component not scanned | Missing runtime dependency or package not under roots | Check Gradle `runtimeClasspath` and annotations/filters |
| Bean registered yet creation fails | Missing constructor dependency, circular dependency, scope, or factory error | Read exception chain; distinguish registration from instantiation |
| Explicit name conflict despite using FQ generator | Built-in generator preserves explicit names | Fix `@Service("...")`/custom stereotype aliases |
| Spring Data repository missing despite broad component scan | Repository interfaces use Spring Data's separate mechanism | Check `@EnableJpaRepositories`/repository bootstrap |
| Scanning `demo` produces too many beans | Root too high, pulling in unintended modules | Pick specific package roots with markers or import module configs |

### 10.1. Systematic Debugging Procedure

**Step 1 — Identify the exception type.** `ConflictingBeanDefinitionException` relates to bean definition names during scanning; `NoUniqueBeanDefinitionException` relates to multiple candidates during dependency resolution; `NoSuchBeanDefinitionException` usually means no matching bean exists.

**Step 2 — Read both sides of the conflict.** If the message lists two classes with fully qualified names, identify which module/JAR each comes from and why both were scanned.

**Step 3 — Identify active package roots.** Check `@ComponentScan` on actually registered configurations, `@SpringBootApplication` placement, and relevant imports/auto-configs. Never assume only a single scanner is active.

**Step 4 — Inspect the runtime classpath.** In Gradle, from the `app` module you can run:

```bash
gradle :app:dependencies --configuration runtimeClasspath
```

If an unexpected module appears, inspect dependency declarations. Dependency graph tools report **JAR/module presence**, not directly which beans were scanned.

**Step 5 — Inspect bean definitions in a runnable context.** For example, in code with an `AnnotationConfigApplicationContext context`:

```java
String[] names = context.getBeanNamesForType(
        demo.catalog.service.ReportService.class);
java.util.Arrays.sort(names);
System.out.println(java.util.Arrays.toString(names));
```

This is an illustrative snippet requiring the class on the runtime classpath. If the context already failed to refresh due to a conflict, you must **fix or narrow the configuration first** before inspecting the final registry. You cannot call `getBean...` on a context that failed to initialize.

**Step 6 — Audit bean name contracts.** After changing generators, check `@Qualifier`, `@Resource`, bean name strings, and map keys; retest real functionality. A successfully built bean registry does not guarantee every consumer has been updated.

## 11. Controlled Scanning Architecture for Multi-Module Projects

### 11.1. Clearer Boundaries Than a Global Root Package

A helpful convention:

```text
com.example.app               -> composition root / main app
com.example.catalog           -> catalog public config + internal packages
com.example.audit             -> audit public config + internal packages
com.example.integration.*     -> optional integrations by profile/condition
```

Instead of `@ComponentScan("com.example")`, the application scans only packages under its direct responsibility, and uses `@Import`/module configurations or Boot auto-configuration for libraries. This prevents adding one Gradle dependency from immediately dumping all library components into the registry.

### 11.2. One Module, Multiple Packages

If a Gradle module `:catalog` contains both `com.example.catalog` and `com.example.sharedcatalog`, a `CatalogMarker` in the first package only covers one branch. Use multiple root markers or reorganize packages if that reflects the true architecture. Do not expect Spring to infer the entire build module from a marker class.

### 11.3. One Package Spanning Multiple JARs

If two Gradle modules both declare classes under `com.example.catalog`, a scanner scanning that package sees available classes from both JARs when both are on the runtime classpath. If the architecture requires isolation, change packaging/classpath or choose explicit bean configuration; a string package root alone cannot constrain the scanner strictly to one JAR.

### 11.4. Filters and Conditions

`@ComponentScan` has `excludeFilters`, `includeFilters`, and `useDefaultFilters`, operating **inside the selected package scope**. For example:

```java
@Configuration
@ComponentScan(
    basePackages = "com.example",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = LegacyReportService.class
    )
)
class AppConfig {
}
```

This is an illustrative snippet requiring imports and the corresponding `LegacyReportService` class. An exclude filter can remove a class from **this scan pass**, yet does not forbid another `@Bean` from registering that class. When the number of exclusions grows large, it may be a sign that the chosen base package is too broad.

`@Profile` and `@Conditional` can also exclude components by environment/configuration. To ensure both test and production behave correctly, test scan scopes under important active profiles and conditions.

### 11.5. Naming Conventions

Name beans by **role** when name-based references are genuinely needed. If two modules both have `ReportService`, names `catalogReportService` and `auditReportService` express intent much better than two short names `reportService`. The FQ generator prevents large-scale collisions yet couples bean names to packages; refactoring packages can change bean names. When a bean name is an external contract, prefer intentional explicit names and tests.

## 12. Exercises with Answers

### Exercise 1 — Overlapping Scan

A config scans `demo.catalog` and `demo.catalog.service`; class `demo.catalog.service.ReportService` has `@Service`. Will it definitely produce two singletons?

**Answer:** No. This is the same class appearing across two intersecting roots; the scanner checks candidate compatibility and normally keeps only one bean definition.

### Exercise 2 — Duplicate Class Name Across Two Modules

Two modules contain `demo.catalog.service.ReportService` and `demo.audit.service.ReportService`, each with `@Service`. A config scans both packages using the default generator. What is the primary cause of the conflict?

**Answer:** Two different types both generate the **bean name** `reportService`. The Java class names differ, yet the registry cannot register two incompatible definitions under the same name.

### Exercise 3 — Does the Fully-Qualified Generator Always Solve Collisions?

Suppose both classes carry `@Service("reportService")`. Is replacing `AnnotationBeanNameGenerator` with `FullyQualifiedAnnotationBeanNameGenerator` sufficient?

**Answer:** No. The built-in FQ generator preserves explicit names. You must change the explicit names or restrict registration.

### Exercise 4 — Distinct Names Yet Injection Still Fails

Two beans `catalogReportService` and `auditReportService` both implement `ReportPort`. Constructor `Reporter(ReportPort port)` throws `NoUniqueBeanDefinitionException`. Is the scanner still creating duplicate names?

**Answer:** No. This is **type ambiguity**, not a duplicate name. Fix via `@Qualifier`/`@Primary` or inject a collection when business logic truly needs both.

### Exercise 5 — Gradle Dependency and Scan Root

`:app` has `implementation project(':audit')` yet only scans `demo.catalog`. Will the `demo.audit.service.ReportService` bean appear automatically?

**Answer:** Not via that scan pass. Gradle adds the classes to the classpath; becoming a bean requires appropriate scanning/registration and other conditions.

### Exercise 6 — Marker Placed Too Deep in a Package

`@ComponentScan(basePackageClasses = CatalogServiceMarker.class)` with the marker in `demo.catalog.service`. Will repository beans in `demo.catalog.persistence` be scanned?

**Answer:** No, because the persistence package is a sibling. Place the marker at `demo.catalog` or import the appropriate repository configuration.

### Exercise 7 — Global Package Scanning

An app previously had only `catalog`; after adding the `audit` dependency, startup hits a conflict. Should you immediately enable bean overriding system-wide?

**Answer:** No. Check whether the component scan root already includes the audit package, identify the two conflicting bean definitions, and then narrow scanning, adjust naming, or register explicitly. Enabling overrides can hide bugs and does not guarantee the scanner accepts incompatible definitions.

### Exercise 8 — Choosing Module Configuration

A module contains 40 internal components yet the app only needs one adapter. Scan the entire module package or import a public configuration with one `@Bean`?

**Answer:** Importing a public configuration usually expresses boundaries more clearly when a module is designed as an integration library. Ensure the class is not simultaneously scanned via another path to avoid duplicate registration.

### Exercise 9 — Two Contexts

Context A scans catalog and Context B scans audit; each context has a bean named `reportService`. Is `ConflictingBeanDefinitionException` guaranteed to occur?

**Answer:** No. Two independent registries can use the same name; registration conflicts occur when incompatible definitions compete for one name within the same registry.

## 13. Checklist Before Fixing an Overlapping Scan Error

1. Read the exception chain to distinguish **duplicate bean name**, **missing bean**, and **ambiguous type**.
2. Identify the **fully qualified package/class name** of each involved bean.
3. Identify the **runtime module/classpath** containing those beans and the Gradle dependencies.
4. List all **actively running component scan roots**, including Boot's default scan and imported configs.
5. Check whether it is **the same class scanned twice** or **two different classes sharing a bean name**.
6. Inspect other registration paths: `@Bean`, `@Import`, library auto-configuration, Spring Data.
7. Pick an intentional fix: narrow roots, explicit names, FQ generator, module configuration, or filters.
8. After renaming, check `@Qualifier`, `@Resource`, map keys, and `getBean(String)`.
9. Test the context under key profiles/test/prod setups; confirm expected beans exist and no conflicts remain.
10. Avoid relying on scan order or enabling global bean overriding to mask the issue.

## 14. Key Takeaways

- **Overlapping scans of the same component** are typically recognized by the scanner as the same/compatible bean definition, skipping duplicate registration rather than creating duplicate singletons.
- **True conflicts** usually stem from **two incompatible bean definitions sharing a name**, especially two classes in different packages with the same simple class name under default naming.
- **Gradle modules** govern classpath, **Java packages** govern component scan scope, and **bean names** govern registry identity. These are three separate boundaries.
- **Component scan roots are not JAR-level module boundaries.** Adding a dependency can cause the scanner to discover extra components if existing package roots already cover them.
- **Distinct names do not automatically resolve type ambiguity.** After successful registration, single-bean dependencies may still need `@Qualifier` or `@Primary`.
- Resolve issues with clear scan scope, explicit naming, `FullyQualifiedAnnotationBeanNameGenerator`, or module-specific configuration entry points. Never use bean overriding as a default fix.

### Official Documentation

- [Spring Framework — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html).
- [Spring Framework 6.2 — `ClassPathBeanDefinitionScanner` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/ClassPathBeanDefinitionScanner.html).
- [Spring Framework 6.2 — `@ComponentScan` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/ComponentScan.html).
- [Spring Framework 6.2 — `FullyQualifiedAnnotationBeanNameGenerator` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/FullyQualifiedAnnotationBeanNameGenerator.html).
- [Spring Framework — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html).
- [Spring Boot — Structuring Your Code](https://docs.spring.io/spring-boot/reference/using/structuring-your-code.html).
