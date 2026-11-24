# AspectJ as a Deliberate Choice When the Proxy Model Falls Short

## 1. Objective and Real-World Problem

Spring Security Method Security and `@Transactional` transaction management normally operate via **Spring AOP proxies**. This model fits most services: another bean invokes a method through a Spring-provided reference, the proxy executes authorization/transaction advice, and only then forwards the call to the real target object.

Limits appear when one method calls another method **on the same object**, such as `this.restricted()`, when interception is needed on a class not called through a Spring proxy, or when the proxy model cannot satisfy a proven constraint. **AspectJ weaving** is a deliberate alternative: instead of placing advice solely on a proxy, AspectJ can weave advice directly into the target class's bytecode so interception occurs even on internal call paths that standard proxies skip.

This is not the default choice for every application. Weaving carries build, startup, class-loader, operational, and testing costs. This lesson belongs to the **Proxies and Transactions** group of Spring Security Authorization, helping you evaluate *when* AspectJ is warranted, *what components are required*, *how to verify the outcome*, and *how to keep security policies sound after switching*.

By the end of this lesson, you will be able to:

1. Distinguish **Spring AOP proxies**, **AspectJ bytecode weaving**, and AspectJ pointcut syntax inside Spring AOP.
2. Explain why self-invocation bypasses proxies and why switching from JDK proxies to CGLIB does not solve it on its own.
3. Deliberately configure `@EnableMethodSecurity(mode = AdviceMode.ASPECTJ)` and `@EnableTransactionManagement(mode = AdviceMode.ASPECTJ)` alongside the required dependencies, weaving, and tests.
4. Compare **compile-time weaving (CTW)** with **load-time weaving (LTW)** and their operational requirements.
5. Make evidence-based decisions grounded in tests and real requirements, covering permission checks, transaction propagation, annotations, startup, and security patches.

**Scope:** Java 17+, Spring Framework 6.x, Spring Security 6.x, Spring Boot 3.x. Examples focus on synchronous service-layer method security and transactions; they do not replace request authentication or repository-level data protection.

## 2. Nature of Proxy Limitations

### 2.1. External Calls vs. Self-invocation

Suppose a service exposes public methods:

```java
public class PaymentService {

    public void checkout() {
        this.charge(); // Internal call on the same target.
    }

    @PreAuthorize("hasRole('PAYMENT_ADMIN')")
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void charge() {
        // Sensitive action.
    }
}
```

When another bean calls `paymentService.charge()` through the Spring proxy, method security checks the role and transaction advice creates a transaction per the declared propagation. Inside `checkout()`, however, `this.charge()` is a direct call on the target: **it does not re-enter the proxy** for `charge`. Hence, annotations on `charge` may not execute on that call path.

```text
Call from another bean (proxy mode)
Controller/Coordinator -> PaymentService proxy
                         -> security / transaction advice
                         -> target.charge()

Self-invocation (proxy mode)
Controller/Coordinator -> PaymentService proxy -> target.checkout()
                                                 -> this.charge()
                                                    (skips advice for charge)
```

If `checkout()` has its own advisors, the initial call into `checkout()` through the proxy can still be protected. What is bypassed is **interception specific to the internally called method**, not every protection mechanism in the application.

### 2.2. Impact per Annotation

| Annotation | When calling `this.inner()` in proxy mode | Risk if relying on the annotation |
| --- | --- | --- |
| `@PreAuthorize` | Interceptor on `inner` is not triggered | Unauthorized caller still enters method body |
| `@PostAuthorize` | Return value of `inner` is not checked | Sensitive result may be returned |
| `@PreFilter` | Input elements of `inner` are not filtered | Batch processes disallowed elements |
| `@PostFilter` | Returned elements of `inner` are not filtered | Data leaked via returned collection |
| `@Transactional` | Transaction advice of `inner` does not run | Wrong transaction opening, rollback, or propagation |

**Common transaction confusion:** if the outer method already runs inside a transaction, calling `this.inner()` may still observe `TransactionSynchronizationManager.isActualTransactionActive() == true`. That **does not prove** `@Transactional(propagation = REQUIRES_NEW)` on `inner` took effect: the inner operations may simply be running inside the outer method's transaction without creating a new one.

### 2.3. CGLIB Proxies Do Not Fix Self-invocation

Spring AOP uses JDK dynamic proxies (typically for interfaces) or class-based proxies (CGLIB). Both are **proxies**. Setting `proxyTargetClass = true` may change the proxy form, yet does not turn `this.inner()` into a call that **leaves the target and re-enters the proxy**.

Similarly, `@EnableAspectJAutoProxy` enables Spring's interpretation of `@Aspect` as **Spring AOP proxies**. It is **not equivalent** to the AspectJ compiler/weaver and does not make self-invocation advised.

## 3. How Does AspectJ Weaving Differ from Spring AOP?

**Weaving** embeds advice directly into class bytecode at compile time or when the JVM loads classes. With properly woven classes and configured aspects, advice can apply directly at method-execution join points, including self-invocation.

```text
Proxy mode:
Caller -> proxy(advice) -> target
                     target.outer() -> this.inner()
                                      bypasses proxy

AspectJ weaving:
Caller -> woven class
          outer() -> inner()
                     advice is woven into inner()'s execution
```

| Criterion | Spring AOP proxy | AspectJ weaving |
| --- | --- | --- |
| Mechanism | Places advice on a Spring bean proxy | Weaves advice into the bytecode of target classes |
| Self-invocation | Does not intercept advice on internal calls | Can intercept when class/join point/aspect are properly woven |
| Interception points | Primarily method execution through proxy | AspectJ supports broader join points depending on aspect |
| Non-Spring-bean objects | Not automatically proxied | Can be woven, though security/tx aspects still need proper initialization and dependencies |
| Setup | Relatively simple via Spring config | Requires CTW/LTW, aspect libraries, build/JVM/class-loader setup, and testing |
| Operational risks | Self-calls, `final`/`private`, wrong reference | Wrong weave scope, missing agent, preloaded classes, toolchain/packaging differences |

**Two meanings of "AspectJ" must be separated:**

- Spring AOP can use **AspectJ pointcut** expression syntax (e.g., `execution(* com.example..*Service.*(..))`) while still running via **proxies**. That syntax does not prove weaving occurred.
- Spring Security/Transactions in **`AdviceMode.ASPECTJ`** require genuine AspectJ weaving—meaning target classes have actually been transformed with the relevant advice. Config annotations alone are not enough.

## 4. When Should You Consider AspectJ?

The first step is confirming **the requirement cannot be met cleanly with standard proxy design**. Simpler options usually suffice: extract the sensitive method into a separate bean, inject that bean into the coordinator, and call via the Spring reference; use `TransactionTemplate` for explicit transaction boundaries; place permission checks in policies/services or scoped queries.

AspectJ is justified when **hard requirements** and **test evidence** show:

1. An internal flow within the same class must receive advice **at method execution**, and refactoring bean boundaries cannot preserve system contracts.
2. An external framework instantiates or invokes objects in ways that bypass Spring proxies, and the team has evaluated initialization lifecycles, aspect config, class loaders, and access controls.
3. Advice is needed at join points proxies do not support, with well-defined scope and tests for those exact join points.
4. The project already maintains reliable CTW/LTW pipelines, CI/CD, and runtime weaving verification so extra operational cost is controlled.

**Insufficient reasons:** "wanting it faster," "needing to fix one stray self-call," "liking `@Aspect`," or "wanting all private methods protected automatically." Weaving does not make permissions right, transactions atomic, logging sufficient, or data safe by itself. It changes **how advice is applied**, not the authorization policy.

## 5. Four Pieces That Must Work Together

### 5.1. Selecting AspectJ Mode for the Right Subsystems

In Spring configuration:

```java
import org.springframework.context.annotation.AdviceMode;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableMethodSecurity(mode = AdviceMode.ASPECTJ)
@EnableTransactionManagement(mode = AdviceMode.ASPECTJ)
public class AuthorizationAndTxConfig {
}
```

`@EnableMethodSecurity(mode=ASPECTJ)` instructs Spring Security to expose method-security advice in AspectJ-weaving form. `@EnableTransactionManagement(mode=ASPECTJ)` activates AspectJ transaction management. **The two settings are independent:** switching security to `ASPECTJ` does not switch transactions, and vice versa.

If only transactions need AspectJ, do not accidentally switch method security; choose each subsystem's mode per verified goals and scope.

### 5.2. Functional Dependencies

In a Spring Boot Gradle project with proper dependency version management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-aspects'
    implementation 'org.springframework:spring-aspects'
    runtimeOnly 'org.aspectj:aspectjweaver'
}
```

- `spring-security-aspects` contains aspects supporting Spring Security method authorization.
- `spring-aspects` contains Spring Framework aspects, including `AnnotationTransactionAspect` for `@Transactional`.
- `aspectjweaver` provides class-load-time weaving; running LTW on a standard JVM also requires **activating the weaver**, e.g. `-javaagent`.

The dependency snippet above is **part of an existing build**, not a standalone `build.gradle`. `spring-security-aspects` must match other Spring Security modules, `spring-aspects` must match Spring Framework, and AspectJ must be compatible with your JDK and packaging.

### 5.3. Actual Weaving Must Occur

Two primary routes:

| Route | When weaving happens | Typical setup | What to observe |
| --- | --- | --- | --- |
| **Compile-time weaving (CTW)** | During class build | AspectJ compiler `ajc`, aspect libraries, build/plugin config | Weave logs, output classes genuinely transformed |
| **Load-time weaving (LTW)** | JVM loads classes | `aspectjweaver` Java agent or class-loader-compatible Spring LTW; aspect config | Agent is active and target classes are woven in time |

Conceptual LTW command when launching a Java application:

```bash
java -javaagent:/opt/aspectj/aspectjweaver.jar -jar application.jar
```

The agent path must point to an actual JAR file, not a dependency coordinate. Across containers/CI/tests, the JVM in **every runtime environment** must receive the proper configuration; class loaders and Spring Boot executable JARs must be tested in the exact deployment format. Never assume adding a JAR to the runtime classpath performs weaving.

AspectJ uses `META-INF/aop.xml` to declare and scope weaving. Aspect libraries may bundle their own `aop.xml`; if you add an application file, coordinate carefully to avoid duplicate aspect declarations or mis-scoped class filters. Example configuration **limiting scope and logging weaves** for application package `demo`:

```xml
<!DOCTYPE aspectj PUBLIC "-//AspectJ//DTD//EN"
    "https://www.eclipse.org/aspectj/dtd/aspectj.dtd">
<aspectj>
    <weaver options="-showWeaveInfo">
        <include within="demo..*"/>
    </weaver>
</aspectj>
```

Place it in `src/main/resources/META-INF/aop.xml` or `src/test/resources/META-INF/aop.xml` depending on scope. This is **not** a complete aspect listing; required aspects must be registered/available through compatible `spring-security-aspects` and `spring-aspects` libraries. Inspect real logs: the mere presence of `aop.xml` does not prove classes were woven.

### 5.4. Tests Specifically Covering Internal Calls

Meaningful acceptance criteria are not "the app boots," but rather:

- A `USER` lacking the role is denied on **both direct calls** to the protected method and **self-invocation**.
- `ADMIN` is permitted along both paths.
- When a method is annotated with `@Transactional` and woven, transactions are active where expected.
- When `REQUIRES_NEW` is needed, a test proves a **separate** transaction, not merely an active boolean.
- Turning off the agent or removing weaving makes the **self-invocation** test fail predictably. That proves the test is sensitive enough to catch broken weaving config.

## 6. Java 17+ Example: Verifying Self-invocation with AspectJ LTW

This example is a **weaving-dependent integration test suite**. It provides the full code, dependencies, and agent setup to try in a dedicated project. Requires JDK 17+, compatible Gradle, repository access, and compatible `aspectjweaver`. Results below are **expected outcomes when weaving succeeds**, not logs from an actual run.

### 6.1. Layout

```text
aspectj-method-security/
├── settings.gradle
├── build.gradle
└── src/test/
    ├── java/demo/AspectJWeavingTest.java
    └── resources/META-INF/aop.xml
```

`settings.gradle`:

```groovy
rootProject.name = 'aspectj-method-security'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

configurations {
    aspectjAgent
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-aspects'
    implementation 'org.springframework:spring-aspects'
    runtimeOnly 'com.h2database:h2'

    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'

    aspectjAgent 'org.aspectj:aspectjweaver:1.9.22.1'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    doFirst {
        jvmArgs "-javaagent:${project.configurations.aspectjAgent.singleFile.absolutePath}"
    }
}
```

**Intent:** use the BOM to align Spring dependency versions; Gradle launches the test JVM with the AspectJ agent. `spring-boot-starter-jdbc` with H2 creates a transaction manager to test real transactions without an external database. This is a test-only project needing no web server or `main()`.

Place `src/test/resources/META-INF/aop.xml`:

```xml
<!DOCTYPE aspectj PUBLIC "-//AspectJ//DTD//EN"
    "https://www.eclipse.org/aspectj/dtd/aspectj.dtd">
<aspectj>
    <weaver options="-showWeaveInfo">
        <include within="demo..*"/>
    </weaver>
</aspectj>
```

This file limits scope to the test package and enables logging of woven join points. Aspect definitions come from the listed aspect JARs; when moving to a real application, check the final classpath, all discovered `META-INF/aop.xml` files, and AspectJ warnings.

### 6.2. Complete Test Class

Create `src/test/java/demo/AspectJWeavingTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.AdviceMode;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
    classes = AspectJWeavingTest.Config.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
public class AspectJWeavingTest {

    @Autowired
    GuardedService service;

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity(mode = AdviceMode.ASPECTJ)
    @EnableTransactionManagement(mode = AdviceMode.ASPECTJ)
    public static class Config {
        @Bean
        public GuardedService guardedService() {
            return new GuardedService();
        }
    }

    public static class GuardedService {

        public String internalEntry() {
            return this.restrictedAction(); // intentional self-invocation
        }

        @PreAuthorize("hasRole('ADMIN')")
        @Transactional
        public String restrictedAction() {
            boolean active =
                TransactionSynchronizationManager.isActualTransactionActive();
            return active ? "AUTHORIZED_TX_ACTIVE" : "NO_TRANSACTION";
        }
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void directCallRejectsUser() {
        assertThatThrownBy(service::restrictedAction)
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void selfInvocationAlsoRejectsUserWhenWoven() {
        assertThatThrownBy(service::internalEntry)
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void directAuthorizedCallHasTransaction() {
        assertThat(service.restrictedAction())
            .isEqualTo("AUTHORIZED_TX_ACTIVE");
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void internalAuthorizedCallHasTransactionWhenWoven() {
        assertThat(service.internalEntry())
            .isEqualTo("AUTHORIZED_TX_ACTIVE");
    }
}
```

The test intentionally places **the same annotations on `restrictedAction()`** and calls it via **two paths**. If you look only at the direct call, Spring proxy mode would pass too; `selfInvocationAlsoRejectsUserWhenWoven` and `internalAuthorizedCallHasTransactionWhenWoven` are the cases that specifically verify weaving's effect.

### 6.3. Running and Interpreting Results

From the project directory:

```bash
gradle test --tests demo.AspectJWeavingTest --info
```

If using a Gradle Wrapper, run `./gradlew test --tests demo.AspectJWeavingTest --info` on Linux/macOS or `gradlew.bat test --tests demo.AspectJWeavingTest --info` on Windows.

When AspectJ LTW, security aspects, and transaction aspects are all applied properly, expected results are **4 passing tests** and Gradle finishing with `BUILD SUCCESSFUL`. These tests **do not by themselves prove** `REQUIRES_NEW` independence; they only prove advice on the internally called method checks permissions and opens a transaction when no outer transaction exists.

| Test | Role | Call path | Expected |
| --- | --- | --- | --- |
| `directCallRejectsUser` | USER | Direct to `restrictedAction` | `AccessDeniedException` |
| `selfInvocationAlsoRejectsUserWhenWoven` | USER | `internalEntry() -> this.restrictedAction()` | `AccessDeniedException` |
| `directAuthorizedCallHasTransaction` | ADMIN | Direct | `AUTHORIZED_TX_ACTIVE` |
| `internalAuthorizedCallHasTransactionWhenWoven` | ADMIN | Self-invocation | `AUTHORIZED_TX_ACTIVE` |

**Checking logs and evidence:** If classes are not woven or advisors are missing, USER's self-call test may **fail to throw an exception**, and ADMIN's self-call test may return `NO_TRANSACTION`. Never weaken the expected result to make tests pass: inspect whether the agent actually attached to the test JVM, check woven-class logs, `aop.xml`, aspect dependencies, annotations on the implementation class, and the transaction manager.

To contrast with default proxy mode, run the same contract in a **separate test config/project** without weaving using default `@EnableMethodSecurity` and `@EnableTransactionManagement`. Avoid mixing both modes on the same method inside one test context, as that makes root causes ambiguous.

## 7. CTW vs. LTW: Choosing a Deployment Path

### CTW (Compile-Time Weaving)

The AspectJ compiler `ajc` can weave classes during the build. Once services are woven in the output artifact, no runtime agent is needed to weave those classes again. However, you must integrate the AspectJ compiler/plugin into Gradle or Maven, pass the right aspect libraries on the aspectpath, and ensure the deployed artifact is genuinely **the woven build**.

Your pipeline needs steps proving woven classes are packaged, checking build cache / incremental compilation, JDK compatibility, and rollback to an unwoven artifact if needed. Never run plain `javac` and assume CTW happened.

### LTW (Load-Time Weaving)

The AspectJ agent transforms classes as the JVM loads them. The advantage is keeping the standard Java compiler, yet operations must control `-javaagent`, library paths, class loaders, early class loading, and `META-INF/aop.xml`. Tests run without the agent might pass via Spring proxies or fail obscurely unless dedicated self-invocation tests exist.

Spring Framework also supports `@EnableLoadTimeWeaving` and environment-specific `LoadTimeWeaver` implementations. Those still require suitable class-loader/transformer setup; **never** treat `@EnableLoadTimeWeaving` alone as proof every class was woven.

**Operational practice:** capture weave logs in test and staging environments; restrict package scope; measure startup time; verify that executable JARs, Gradle Tests, containers, and production all use the same strategy. Do not overlook background jobs or multi-class-loader setups.

## 8. Configuration Pitfalls and Limitations to Verify

### 8.1. Having Config or Dependencies Without Actual Weaving

`@EnableMethodSecurity(mode=ASPECTJ)` does not transform bytecode on its own. Missing the agent/CTW or missing aspect libraries can leave expected call paths unprotected by method security. Always have a test where an unauthorized principal **must throw `AccessDeniedException` on a self-call**.

### 8.2. Interface vs. Class Annotations

AspectJ follows standard Java rules: **annotations on interfaces are not automatically inherited by implementing methods**. For AspectJ transaction aspects, place `@Transactional` on the concrete class or concrete method. For AspectJ method security as well, verify annotations are recognized on the woven class/method. Never switch from proxies to weaving while continuing to rely on interface-only annotations without integration tests.

### 8.3. `private`/`final` Methods and Weave Scope

AspectJ can advise join points that Spring proxies do not intercept, yet exact behavior depends on the specific aspect, pointcut, version, and actual bytecode. Never treat a `private` method annotated with `@PreAuthorize` as guaranteed safe merely because `mode=ASPECTJ` is set.

**Important version evidence:** Spring published **CVE-2025-41232** affecting `spring-security-aspects` and method-security annotations on **`private` methods** in Spring Security **6.4.0 through 6.4.5**; version 6.4.6 fixed that branch. Inventory versions and test private/entry call paths directly before adopting, especially across branch upgrades. Reference: https://spring.io/security/cve-2025-41232/

### 8.4. An Active Transaction Does Not Prove `REQUIRES_NEW` Worked

To prove `REQUIRES_NEW` under weaving, use real transaction tests with H2/PostgreSQL: outer transaction writes A, inner `REQUIRES_NEW` writes B and commits, outer rolls back; verify B persists while A rolled back. Configure a real transaction manager, connection, and call boundaries. Checking only `isActualTransactionActive()` misses cases where inner accidentally joined outer.

### 8.5. Advice Ordering and Side Effects

When both security and transactions apply to a method, **ordering** affects whether a transaction opens before checking permissions. Spring Security docs describe method interceptor ordering; with weaving, observe your real runtime configuration. Denying unauthorized users must occur **before sensitive business actions**; inspect side effects and audit logs rather than assuming advice order.

### 8.6. Performance, Debugging, and Compatibility

Do not assume AspectJ is always faster than proxies. Weaving can reduce certain proxy overhead while increasing build time, startup time, and stack-trace complexity. Benchmark with application workloads and control compatibility across AspectJ, JDK, Spring, Java agents, and package layouts. Evaluate impacts on AOT/native images, testing tools, and other instrumentation agents; support varies by version/runtime and is not guaranteed automatically.

## 9. Deliberate Decision Workflow

You can follow this decision sequence:

1. **Pinpoint the exact bug:** which method, annotation, caller, principal, request/transaction, and test are failing?
2. **Try standard proxy design first:** split beans, inject collaborators; for programmatic transactions, consider `TransactionTemplate`. Run the same test suite across the new boundary.
3. **If still insufficient:** document why interception must happen inside non-proxied / same-class paths; evaluate CTW/LTW costs and library versions.
4. **Prototype in isolation:** apply `ASPECTJ` mode to only the needed subsystem, add matching aspect modules, verify agent/compiler, weave logs, and positive/negative tests.
5. **Test thoroughly:** direct calls, self-calls, USER/ADMIN, active transactions, `REQUIRES_NEW` rollback, private/interface annotations, side effects, and unexpected call paths.
6. **Approve deployment only with proof:** CI, staging, and production all load woven classes; version/CVE checks, startup metrics, and rollback plans are in place.

| Situation | First option to try | When AspectJ is worth considering |
| --- | --- | --- |
| A service calls `this.securedMethod()` | Move method to separate bean, call via Spring | Boundary cannot change due to special contract |
| Need `REQUIRES_NEW` from internal logic | Extract transactional service or `TransactionTemplate` | Must weave execution join point with dedicated transaction tests |
| Want to intercept `final`/`private` methods | Review contract, design public service boundary | Current aspect supports join point, version is patched, and direct tests pass |
| Object instantiated outside Spring | Move guarded operation into Spring-managed policy/service | Entry points cannot go through proxies and aspect initialization is solved |
| Only want AspectJ pointcut syntax | Spring AOP `@Aspect`/pointcut expressions | No weaving needed when public proxy interception suffices |
| Need performance optimization | Profile and optimize call paths/queries | Benchmarks prove real gains outweigh operational cost |

## 10. Acceptance Checklist Before Using AspectJ in Production

- [ ] Document the exact **technical reason** why Spring proxies / bean boundaries cannot solve the problem.
- [ ] Each subsystem using weaving has the right mode and dependencies: `spring-security-aspects` for method security; `spring-aspects` for transactions.
- [ ] Build or JVM genuinely weaves target classes; weave logs/evidence and self-invocation tests exist.
- [ ] `@PreAuthorize` blocks USER on **both direct calls and internal calls**, while ADMIN runs only authorized actions.
- [ ] `@Transactional` opens transactions in the right places; `REQUIRES_NEW` is proven with commit/rollback and independent transactions.
- [ ] Annotations sit on appropriate implementation classes/methods; never rely blindly on interface annotations.
- [ ] Security patches are verified, especially advisories for AspectJ private methods, along with JDK/AspectJ/Spring compatibility.
- [ ] Tests run using the exact production packaging/launch setup, verifying class loaders, agents, and startup.
- [ ] Changes to weaving can be rolled back without dropping authorization checks on critical call paths.

## 11. Takeaways

- **Spring AOP proxies** intercept calls passing through the proxy; `this.method()` normally skips advice on the internally called method.
- **AspectJ weaving** transforms class bytecode, enabling self-invocation interception when *the right aspect, right class, and right weaving setup* are in place.
- **`AdviceMode.ASPECTJ` is not enough by itself**: you also need aspect libraries, CTW/LTW, and verification tests.
- **Security and transactions are two independent subsystems**. Switch modes and verify each subsystem according to requirements.
- Splitting beans or using programmatic transactions is usually far less complex. Choose weaving only when technical constraints are proven and operations can observe and control it.

## Official References

- Spring Security 6.5 — Method Security, Integrate with AspectJ Byte-weaving: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Framework 6.2 — Using `@Transactional`, especially `mode = aspectj` and self-invocation: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- Spring Framework — Using AspectJ with Spring Applications, LTW, `META-INF/aop.xml`: https://docs.spring.io/spring-framework/reference/core/aop/using-aspectj.html
- Spring Framework — AOP Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Security Advisory — CVE-2025-41232: https://spring.io/security/cve-2025-41232/
