# Parameterizing Meta-Annotations in Spring Security: Choosing a Version-Safe Solution

## 1. Problem and desired outcome

When many services enforce the same rule, repeating `@PreAuthorize("hasRole('ADMIN')")` or `@PreAuthorize("hasAuthority('report:read')")` across dozens of methods makes policies harder to read and evolve. **Meta-annotations** allow placing a Spring Security annotation onto a project-defined annotation, then applying that domain annotation to services.

The next step is **parameterizing meta-annotations**: instead of defining separate `@CanReadReports`, `@CanEditReports`, and `@IsAdmin` annotations, we want to declare `@RequiresRole("ADMIN")` or `@RequiresAuthority("report:read")` and substitute those values into the SpEL expression. Support for **placeholder replacement in expression annotations** varies significantly across Spring Security generations. Therefore, the first question is: **which version are we running, and is template processing enabled?**

After this lesson, you will know how to:
- Build a fixed meta-annotation that works without templating.
- Build parameterized meta-annotations using `{value}`, `{role}`, and `{roles}` arrays on supported versions.
- Enable `AnnotationTemplateExpressionDefaults` in Spring Security 6.4–6.5, and understand the default change in Spring Security 7.
- Distinguish **annotation attributes** from **method parameters** (`#owner`), avoid SpEL quoting mistakes, and accurately test allow/deny behavior.
- Choose a safe fallback for older versions and plan upgrades cleanly.

**Scope:** Spring Security Method Security (primarily `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`) in Spring applications using Java 17+. This is not Java syntax for "mutating annotations at runtime"; every value written on an annotation must still satisfy Java's compile-time rules.

## 2. Fixed meta-annotations vs. templated meta-annotations

### 2.1. Fixed meta-annotations: the baseline approach

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasRole('ADMIN')")
public @interface IsAdmin {
}
```

This is the contents of a separate `IsAdmin.java` file; to use it, place it in an application package and enable Method Security. A service can then write:

```java
@IsAdmin
public String getSystemReport() {
    return "system-report";
}
```

**In fixed form, with no placeholders:** Spring Security discovers `@PreAuthorize` on the custom annotation and evaluates `hasRole('ADMIN')`. This is straightforward and works even on versions without expression templating. It provides domain-friendly naming, though it cannot pass varying roles through a single annotation.

### 2.2. Parameterized meta-annotations: with placeholders

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasRole('{value}')")
public @interface RequiresRole {
    String value();
}
```

Usage example:

```java
@RequiresRole("ADMIN")
public String getSystemReport() {
    return "system-report";
}
```

When **annotation template resolution is enabled or active by default in the version**, `value = "ADMIN"` replaces the `{value}` placeholder. The resulting expression is equivalent to:

```text
hasRole('ADMIN')
```

Key point: Java itself does not interpret `{value}`. That is **Spring Security's template convention**. Without template support/configuration, the string may remain `hasRole('{value}')` literally or fail depending on expression/setup—meaning the policy will not behave as intended.

### 2.3. Two distinct layers of parameters

Consider the pattern:

```java
@PreAuthorize(
    "hasRole('{role}') or #owner == authentication.name"
)
public @interface OwnerOrRole {
    String role();
}
```

Usage:

```java
@OwnerOrRole(role = "SUPPORT")
public String read(@P("owner") String owner) {
    return "report:" + owner;
}
```

These are **illustrative snippets**, needing `@P`, `@PreAuthorize`, and `@Target`/`@Retention` imports to form valid Java files. When preparing annotation metadata, the template resolves `{role}` to `SUPPORT`. At actual method invocation time, SpEL compares the invocation variable `#owner` against `authentication.name`.

| Syntax | Where does the data come from? | When is it resolved? |
|---|---|---|
| `{role}` | `role()` attribute of `@OwnerOrRole` | When the framework creates/reads security metadata and resolves templates |
| `{value}` | `value()` attribute of custom annotation | During template resolution |
| `#owner` | `owner` parameter of the invoked method | When evaluating SpEL for **each invocation** |
| `authentication.name` | `Authentication` in the security context | When evaluating authorization for the call |
| `@policy.canRead(#id)` | Spring bean named `policy` and variable `#id` | When evaluating SpEL |

Never push user data onto an annotation as a dynamically generated runtime expression. For request-varying data, use `#methodArg`, `authentication`, and policy beans instead of trying to modify `{value}`.

## 3. Capability matrix across Spring Security versions

| Version line | **Fixed** meta-annotations | Template parameterization | Recommended configuration |
|---|---|---|---|
| Spring Security before 6.3 | Method Security meta-annotations supported | Do not assume new template APIs exist | Use fixed annotations or SpEL calling policy beans |
| Spring Security 6.3 | Supported | Early `PrePostTemplateDefaults` API (introduced in 6.3); differs from newer API | If not upgrading, consult docs for your **exact patch version** and its specific setup; avoid copying 6.4 APIs |
| Spring Security **6.4–6.5** | Supported | `AnnotationTemplateExpressionDefaults` (introduced in 6.4); **must be enabled explicitly** per 6.x guide | Register a `static AnnotationTemplateExpressionDefaults` bean |
| Spring Security **7.x** | Supported | `AnnotationTemplateExpressionDefaults` enabled by default per migration guide to 7 | No bean needed solely to enable templating; can still register bean to customize behavior |

**Deployment rule:** verify the actual Spring Security version on your classpath (usually managed by Spring Boot), never infer it from Java version alone. The surest check is inspecting the dependency tree and running integration tests on the exact deployed version.

In Spring Security 6.4, `org.springframework.security.authorization.method.PrePostTemplateDefaults` was deprecated in favor of the unified `org.springframework.security.core.annotation.AnnotationTemplateExpressionDefaults`. Do not adopt the deprecated API as a default for new code, as it obscures the upgrade path. **Different versions may implement annotation scanning differently**: conclusions about "whether a bean is needed" must be verified against dependencies and tests rather than guessed from annotation names.

### 3.1. Enabling templates in Spring Security 6.4–6.5

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.annotation.AnnotationTemplateExpressionDefaults;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
    @Bean
    static AnnotationTemplateExpressionDefaults templateExpressionDefaults() {
        return new AnnotationTemplateExpressionDefaults();
    }
}
```

The `@Bean` method is declared **`static`** per official examples so the framework detects the configuration early while building Method Security infrastructure. `@EnableMethodSecurity` remains mandatory to activate method-level interceptors in Spring Boot 3.x apps; adding `spring-boot-starter-security` alone is not enough.

`AnnotationTemplateExpressionDefaults` was added in Spring Security 6.4. If your IDE reports `Cannot resolve symbol AnnotationTemplateExpressionDefaults`, you are typically on an older Spring Security version or an overridden dependency version. Do not "fix" it by importing the wrong package; check dependencies and version-line support.

### 3.2. With Spring Security 7

In the 6.5 → 7 migration guide, Spring Security states `AnnotationTemplateExpressionDefaults` is provided by default. In Spring Security 7 applications, meta-annotation templates can work immediately once Method Security is enabled. Keep tests for every annotation after upgrading and verify any custom template settings still take effect.

**Do not apply the Spring Boot 3.5 build example below to Spring Security 7 by overriding individual versions.** Spring Security 7 belongs to a newer Spring Framework/Spring Boot generation; to test 7.x, pick a compatible Spring Boot 4.x release, read the migration guide, and re-verify dependencies. The complete example in Section 5 intentionally pins Spring Boot 3.5 / Spring Security 6.5 with an explicit template-enabling bean to avoid relying on cross-version default shifts.

### 3.3. Handling unknown placeholders

`AnnotationTemplateExpressionDefaults` supports:

```java
AnnotationTemplateExpressionDefaults defaults =
    new AnnotationTemplateExpressionDefaults();
defaults.setIgnoreUnknown(false);
```

This is a **standalone config snippet**, not a complete Java class. `ignoreUnknown` defaults to `true`; setting `false` makes unrecognized placeholders throw an error during template resolution, useful for catching typos like `{rol}` instead of `{role}`. Strict checking may conflict with expressions using curly braces for other reasons, so test across all project annotations before enabling globally. Never treat "ignoring unknown placeholders" as proof an expression still enforces the right policy; test actual authorization states.

## 4. Placeholder substitution syntax and quoting rules

### 4.1. Single String: quotes live inside the expression

```java
@PreAuthorize("hasAuthority('{value}')")
public @interface RequiresAuthority {
    String value();
}
```

`@RequiresAuthority("report:read")` resolves to:

```text
hasAuthority('report:read')
```

`hasAuthority` matches the **exact** `GrantedAuthority`. `hasRole('ADMIN')` defaults to `ROLE_ADMIN`; never confuse the two when the role prefix is customized.

### 4.2. String array: quotes live inside the annotation values

Official pattern for role arrays:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasAnyRole({roles})")
public @interface HasAnyRole {
    String[] roles();
}
```

Usage:

```java
@HasAnyRole(roles = {"'ANALYST'", "'ADMIN'"})
public String readSharedReport() {
    return "shared";
}
```

After resolution:

```text
hasAnyRole('ANALYST', 'ADMIN')
```

This is a frequent mistake: **the annotation array uses strings already wrapped in single quotes** to form valid SpEL string arguments. Writing `@HasAnyRole(roles = {"ANALYST", "ADMIN"})` with template `hasAnyRole({roles})` can expand to `hasAnyRole(ANALYST, ADMIN)`, which is no longer the intended string literals. Do not change the template to `hasAnyRole('{roles}')` either, because the entire array gets wrapped in a single pair of quotes, which is also semantically wrong.

For one or two fixed roles reused frequently, consider a dedicated meta-annotation such as `@CanReadSharedReport` if quoted `String[]` syntax hurts readability.

### 4.3. Multiple annotation attributes, multiple method variables

```java
@PreAuthorize(
    "hasAuthority('{authority}') and #tenantId == authentication.name"
)
public @interface HasTenantAuthority {
    String authority();
}
```

Usage:

```java
@HasTenantAuthority(authority = "tenant:read")
public String readTenant(@P("tenantId") String tenantId) {
    return "tenant:" + tenantId;
}
```

These are **illustrative snippets to place into an appropriate annotation/service**; they do not replace membership checks in a real multi-tenant system. The example only makes sense if `authentication.name` literally equals `tenantId`, a rare pattern you should not assume in multi-tenant applications. In real systems, pass `#tenantId` and `authentication` to a policy bean to verify membership or push tenant predicates into data queries.

`@P("tenantId")` (or compiling with `-parameters`) ensures `#tenantId` is recognized by Spring Security. `{authority}` is not an invocation variable: it is an attribute defined by the annotation at the declaration site.

### 4.4. Situations requiring extra care

- **The substituted string must be valid SpEL.** Placeholder resolution performs character substitution; it does not automatically make any role string valid SpEL in every context.
- **Annotation attribute values are trusted policy code**, written by developers. Never concatenate request/user data into SpEL expressions for evaluation; that risks authorization bypasses or injection.
- **Quotes, slashes, and special characters** can alter parsing. If roles/authorities contain complex characters, use a policy bean or test properly quoted literals instead of ad-hoc expression splicing.
- **Cannot pass a runtime variable as an annotation value:** `@RequiresRole(userChosenRole)` will not compile if `userChosenRole` is a runtime-computed variable.
- **Cannot stack two `@PreAuthorize` annotations on the same method** to declare two separate policies: Spring Security does not support repeating that annotation. Combine conditions with `and`/`or`, define a single-policy domain annotation, or delegate to a bean.
- **Target/Retention** must match: `@Target(METHOD/TYPE)` to allow placement on methods/classes; `@Retention(RUNTIME)` so the framework detects the annotation at runtime.

## 5. Runnable integration example: Spring Boot 3.5.6 + Java 17

This section builds an app requiring no HTTP server or database; Method Security runs on a service bean, and JUnit tests use `@WithMockUser` to populate `Authentication`. **We use Spring Boot 3.5.6 (released 2025-09-18) and the Boot-managed Spring Security 6.5.x**, without overriding Spring Security versions.

File tree:

```text
meta-annotation-demo/
  pom.xml
  src/main/java/com/example/metasec/MetaAnnotationApplication.java
  src/main/java/com/example/metasec/security/MethodSecurityConfig.java
  src/main/java/com/example/metasec/security/RequiresRole.java
  src/main/java/com/example/metasec/security/HasAnyRole.java
  src/main/java/com/example/metasec/security/OwnerOrRole.java
  src/main/java/com/example/metasec/ReportService.java
  src/test/java/com/example/metasec/ReportServiceTest.java
```

### 5.1. Maven configuration: pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>meta-annotation-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.2. Application and configuration enabling templates

**`src/main/java/com/example/metasec/MetaAnnotationApplication.java`**

```java
package com.example.metasec;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MetaAnnotationApplication {
    public static void main(String[] args) {
        SpringApplication.run(MetaAnnotationApplication.class, args);
    }
}
```

**`src/main/java/com/example/metasec/security/MethodSecurityConfig.java`**

```java
package com.example.metasec.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.annotation.AnnotationTemplateExpressionDefaults;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
    @Bean
    static AnnotationTemplateExpressionDefaults templateExpressionDefaults() {
        return new AnnotationTemplateExpressionDefaults();
    }
}
```

The template bean here is the essential step on the 6.4–6.5 line. The configuration class is automatically scanned by Spring Boot because it resides under root package `com.example.metasec`. Placing it outside the component-scan base package may prevent the configuration from loading.

### 5.3. Three custom meta-annotations

**`src/main/java/com/example/metasec/security/RequiresRole.java`**

```java
package com.example.metasec.security;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasRole('{value}')")
public @interface RequiresRole {
    String value();
}
```

**`src/main/java/com/example/metasec/security/HasAnyRole.java`**

```java
package com.example.metasec.security;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasAnyRole({roles})")
public @interface HasAnyRole {
    String[] roles();
}
```

**`src/main/java/com/example/metasec/security/OwnerOrRole.java`**

```java
package com.example.metasec.security;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.security.access.prepost.PreAuthorize;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize(
    "isAuthenticated() and (#owner == authentication.name or hasRole('{role}'))"
)
public @interface OwnerOrRole {
    String role();
}
```

These annotations illustrate three forms: a `String value`, a `String[]`, and combining a template attribute with a runtime method variable. Under the default `ROLE_` prefix, `@RequiresRole("ADMIN")` requires authority `ROLE_ADMIN`.

### 5.4. Service using the annotations

**`src/main/java/com/example/metasec/ReportService.java`**

```java
package com.example.metasec;

import com.example.metasec.security.HasAnyRole;
import com.example.metasec.security.OwnerOrRole;
import com.example.metasec.security.RequiresRole;
import org.springframework.security.access.method.P;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @RequiresRole("ADMIN")
    public String adminReport() {
        return "admin-report";
    }

    @HasAnyRole(roles = {"'ANALYST'", "'ADMIN'"})
    public String sharedReport() {
        return "shared-report";
    }

    @OwnerOrRole(role = "SUPPORT")
    public String readOwnerReport(@P("owner") String owner) {
        return "report:" + owner;
    }
}
```

For `readOwnerReport("alice")`: user `alice` can read via matching owner, and user `bob` granted `ROLE_SUPPORT` can read via the support branch. User `bob` holding only `ROLE_VIEWER` is blocked. This is an **illustrative policy**: in a multi-tenant system, add tenant checks or a policy bean rather than assuming support staff have access across every tenant.

### 5.5. Eight integration tests

**`src/test/java/com/example/metasec/ReportServiceTest.java`**

```java
package com.example.metasec;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class ReportServiceTest {
    @Autowired
    ReportService reports;

    @Test
    @WithMockUser(username = "root", roles = "ADMIN")
    void adminCanReadAdminReport() {
        assertEquals("admin-report", reports.adminReport());
    }

    @Test
    @WithMockUser(username = "viewer", roles = "VIEWER")
    void viewerCannotReadAdminReport() {
        assertThrows(
            AccessDeniedException.class,
            () -> reports.adminReport()
        );
    }

    @Test
    @WithMockUser(username = "analyst", roles = "ANALYST")
    void analystCanReadSharedReport() {
        assertEquals("shared-report", reports.sharedReport());
    }

    @Test
    @WithMockUser(username = "root", roles = "ADMIN")
    void adminCanReadSharedReport() {
        assertEquals("shared-report", reports.sharedReport());
    }

    @Test
    @WithMockUser(username = "viewer", roles = "VIEWER")
    void viewerCannotReadSharedReport() {
        assertThrows(
            AccessDeniedException.class,
            () -> reports.sharedReport()
        );
    }

    @Test
    @WithMockUser(username = "alice", roles = "VIEWER")
    void ownerCanReadOwnReport() {
        assertEquals("report:alice", reports.readOwnerReport("alice"));
    }

    @Test
    @WithMockUser(username = "bob", roles = "SUPPORT")
    void supportCanReadAnotherOwnersReport() {
        assertEquals("report:alice", reports.readOwnerReport("alice"));
    }

    @Test
    @WithMockUser(username = "bob", roles = "VIEWER")
    void otherViewerCannotReadOwnersReport() {
        assertThrows(
            AccessDeniedException.class,
            () -> reports.readOwnerReport("alice")
        );
    }
}
```

In the `meta-annotation-demo` directory, run:

```bash
mvn test
```

**Expected result (not an actually executed log):** `Tests run: 8, Failures: 0, Errors: 0, Skipped: 0`. Log lines and test order may vary by Maven/Surefire version. The illustrated authorization outcomes are:

| Invocation | User / authority | Expected |
|---|---|---|
| `adminReport()` | `ROLE_ADMIN` | Returns `admin-report` |
| `adminReport()` | `ROLE_VIEWER` | `AccessDeniedException` |
| `sharedReport()` | `ROLE_ANALYST` or `ROLE_ADMIN` | Returns `shared-report` |
| `sharedReport()` | `ROLE_VIEWER` | `AccessDeniedException` |
| `readOwnerReport("alice")` | `alice` / `ROLE_VIEWER` | Returns `report:alice` |
| `readOwnerReport("alice")` | `bob` / `ROLE_SUPPORT` | Returns `report:alice` |
| `readOwnerReport("alice")` | `bob` / `ROLE_VIEWER` | `AccessDeniedException` |

Tests use the `ReportService` bean from `@SpringBootTest` so real interceptors apply. Instantiating `new ReportService()` manually or calling `this.adminReport()` internally can bypass the Spring AOP proxy and lose authorization enforcement. Running requires Java 17+ and Maven/IDE access to resolve dependencies.

## 6. If your project does not support templates yet: equivalent alternatives

You do not necessarily need to upgrade just to parameterize two annotation words. Two safe options exist.

### 6.1. Define fixed domain-named annotations

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@PreAuthorize("hasAuthority('report:read')")
public @interface CanReadReport {
}
```

```java
@CanReadReport
public Report readReport(long id) {
    return repository.findById(id).orElseThrow();
}
```

These are **integration patterns**, requiring annotation imports, `Report`, repository, and service. When you only have a few stable policies, domain names like `@CanReadReport` are often clearer than `@RequiresAuthority("report:read")`.

### 6.2. Move dynamic variables into a Java policy bean

```java
@PreAuthorize("@reportPolicy.canRead(authentication, #reportId)")
public Report readReport(@P("reportId") long reportId) {
    return repository.findById(reportId).orElseThrow();
}
```

This is an integration pattern: `reportPolicy` must be a Spring bean with a method taking `Authentication` and the ID; `Report`, repository, and imports must exist in the app. The bean checks permissions/tenant/ACL and decides based on runtime data. Benefits: isolates business logic, easy to unit test, and independent of `{value}` substitution engines.

For applications handling multi-tenancy or record-level permissions, a policy bean or permission-filtered data query matters far more than shaving characters off an annotation.

## 7. Upgrade compatibility from 6.3/6.4/6.5 to 7

A practical migration path:

1. **Confirm the exact version** via `mvn dependency:tree` or Gradle's dependency report; identify the Spring Security version managed by the BOM/Boot. Never rely solely on seeing `@EnableMethodSecurity` in source.
2. **Document the security contract**: which annotations sit where, which values are substituted, what the role prefix is, and allow/deny cases.
3. **On 6.4–6.5**, register `static @Bean AnnotationTemplateExpressionDefaults` and run tests. If on 6.3 using `PrePostTemplateDefaults`, prepare to migrate to the new API when upgrading Spring Security.
4. **On 7.x**, templating is default per the migration guide; remove the bean only if no custom settings must be preserved, while keeping all authorization tests.
5. **If using custom advisors**, check wiring template defaults directly via `setTemplateDefaults(new AnnotationTemplateExpressionDefaults())` and review migration notes; a global bean does not magically apply to every hand-rolled configuration.
6. **Test negative paths**: user missing role, similar-looking role name (`ADMINISTRATOR` is not `ADMIN`), typoed placeholder, unquoted array items, `this` self-invocation, unresolved parameter name.
7. **Verify production behavior** with real data, especially JWT/OIDC role mapping, authority mapping, tenant membership, and all entry points calling the service.

A more defensive configuration (optional on 6.4+):

```java
@Bean
static AnnotationTemplateExpressionDefaults templateExpressionDefaults() {
    AnnotationTemplateExpressionDefaults defaults =
        new AnnotationTemplateExpressionDefaults();
    defaults.setIgnoreUnknown(false);
    return defaults;
}
```

This **replaces** the identically named bean in the earlier example; do not declare a second bean. On a typoed placeholder, strict mode fails fast instead of letting an unrecognized template slip through. Test against every expression in the app first, since curly braces used for non-templating purposes could also be affected.

### 7.1. Command to inspect dependencies

```bash
mvn dependency:tree -Dincludes=org.springframework.security
```

This command is not guaranteed to output a single line; it lists all Security modules and actual resolved versions in the dependency tree. With Gradle, use `./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath` (on Windows use `gradlew.bat`). Run against the exact project and deployed dependency configuration.

## 8. Typical errors and diagnostics

| Symptom | Likely cause to check | Fix |
|---|---|---|
| `@RequiresRole("ADMIN")` does not enforce access | Missing `@EnableMethodSecurity`, self-invocation, non-Spring bean | Verify AOP interceptor, call via Spring bean, add deny test |
| SpEL still contains literal `{value}` | Unsupported version or templating not enabled on 6.4–6.5 | Check version, register defaults bean |
| `Cannot resolve symbol AnnotationTemplateExpressionDefaults` | Spring Security older than 6.4 or version conflict | Inspect BOM/dependency tree; do not import wrong package |
| `hasAnyRole` errors or denies unexpectedly | `String[]` lacks single-quoted literal elements | Use `{"'ANALYST'", "'ADMIN'"}` with `hasAnyRole({roles})` |
| `hasRole('ADMIN')` denies despite having `ADMIN` | Actual authority is `ADMIN` rather than default `ROLE_ADMIN` | Use `hasAuthority('ADMIN')` or standardize role mapping |
| `#owner` fails to resolve | Missing parameter name metadata; mismatched name | Use `@P("owner")` or compile with `-parameters` |
| Bean/advisor startup error | Unknown placeholder, invalid expression, conflicting annotations | Enable `setIgnoreUnknown(false)` where suitable; test startup |
| Annotation on interface not applied as expected | Proxy/interface/inheritance config or annotation ambiguity | Run integration test matching proxy mode; check annotation placement |
| Multiple meta-annotations cause ambiguity | Multiple `@PreAuthorize` candidates on the same method | Merge into one policy; avoid duplicate annotations |
| Data leaks through another path | Authorization placed on only one service/endpoint while another bypasses | Enforce policies at the proper service/data boundary; test all paths |

**Business note:** post-checks such as `@PostAuthorize` can deny **after** the method already produced a result; never use them to guard mutations that already ran. Most operations with side effects should check permissions beforehand via `@PreAuthorize` or business-layer checks.

## 9. Adoption checklist

- [ ] Exact Spring Security and compatible Spring Boot versions are confirmed.
- [ ] **Fixed meta-annotations** are distinguished from `{placeholder}` meta-annotations.
- [ ] On 6.4–6.5, a `static AnnotationTemplateExpressionDefaults` bean is present; on 7.x, default changes are verified.
- [ ] `@EnableMethodSecurity` is enabled and security annotations are detected by Spring AOP.
- [ ] Annotations have appropriate `@Target`, `@Retention(RUNTIME)`, and attributes.
- [ ] Expanded SpEL strings are syntactically valid; verify `String[]` quoting carefully.
- [ ] `{annotationAttribute}` and `#methodArgument` are never confused.
- [ ] Role and authority mappings are tested with real allow/deny cases.
- [ ] No proxy-bypassing `this` self-invocations or ambiguous duplicate policies exist.
- [ ] Codebase targeting Java 17+ is tested with `mvn test` on the deployed dependency tree.
- [ ] For complex policies, prefer policy beans or permission-filtered queries over long, hard-to-audit expressions.

## 10. Official Documentation

- [Spring Security 6.5 — Method Security: Using Meta Annotations & Templating](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Migration to 7: Authorization Changes](https://docs.spring.io/spring-security/reference/6.5/migration-7/authorization.html)
- [Spring Security — AnnotationTemplateExpressionDefaults API (Since 6.4)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/annotation/AnnotationTemplateExpressionDefaults.html)
- [Spring Security 6.5 — PrePostTemplateDefaults (deprecated)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/PrePostTemplateDefaults.html)
- [Spring Boot 3.5.6 release](https://spring.io/blog/2025/09/18/spring-boot-3-5-6-available-now/)

**Key takeaway:** a fixed meta-annotation gives consistent policy naming; a templated meta-annotation passes role/authority values via annotation configuration. Correctness of parameterized solutions depends on **exact version, template setup, and resulting SpEL expression**, making allow and deny tests at the method boundary indispensable.