# Spring AOP and AspectJ Libraries Required for the Chosen Configuration

## 1. Goal: choosing the right dependencies for your Spring configuration style

When setting up **Spring AOP**, the important question is not just "have I added the AOP library yet?" but **which AOP mechanism the application is using**: Spring Boot auto-configuration, Spring Framework configured with `@EnableAspectJAutoProxy`, Spring's manual proxy mechanism, or AspectJ weaving integrated into Spring. Each choice has a different classpath and activation method.

This lesson only covers **selecting and verifying libraries for using AOP in a Spring application**. General AOP concepts and writing AspectJ aspects independently of Spring are outside the scope here.

**For the most common need** — defining an `@Aspect` bean, declaring `@Before`, `@Around`, and applying advice to Spring bean methods via proxies — the core component set is:

- **Spring AOP**, module `org.springframework:spring-aop`: creates and operates proxies, advisors, and interceptors in Spring.
- **AspectJ weaver library**, module `org.aspectj:aspectjweaver`: provides AspectJ types and the ability to parse and match pointcut expressions so Spring understands the `@AspectJ` declaration style.
- **Spring container**, typically `org.springframework:spring-context` for plain Spring Framework, or Spring Boot starters: bean registration, lifecycle, and configuration.

In this configuration, Spring performs **proxy-based AOP**. The library name `aspectjweaver` does not mean the application automatically runs AspectJ compile-time weaving (CTW) or load-time weaving (LTW).

## 2. Distinguishing easily confused artifacts

| Artifact | Group | Role in Spring configuration | When needed |
| --- | --- | --- | --- |
| `org.springframework:spring-aop` | Spring Framework | AOP proxy API and infrastructure, advisor, pointcut, auto-proxy | Fundamental for Spring AOP; usually pulled in transitively by a starter or `spring-context`. |
| `org.springframework:spring-context` | Spring Framework | ApplicationContext, bean management, and Java `@Configuration` | Plain Spring applications; usually already present in Spring Boot applications. |
| `org.aspectj:aspectjweaver` | AspectJ | AspectJ classes and pointcut parser/matcher used for Spring `@AspectJ` | Needed on the classpath when declaring Spring aspects with `@Aspect`/`@Before`/`@Around` and using `@EnableAspectJAutoProxy`. |
| `org.springframework.boot:spring-boot-starter-aop` | Spring Boot 3.x | Starter that pulls in the dependencies needed for Spring AOP using `@AspectJ` | The standard way to add AOP in Boot 3.x applications. |
| `org.springframework.boot:spring-boot-starter-aspectj` | Spring Boot 4.x | Starter for AOP with AspectJ, pulling in `spring-aop` and `aspectjweaver` | The standard way to add AOP in Boot 4.x applications. |
| `org.springframework:spring-aspects` | Spring Framework | Set of Spring-provided aspects for AspectJ weaving use cases such as `@Configurable` or corresponding transaction aspects | Only when the configuration actually uses these aspects; **not needed** for regular custom `@Aspect` proxies. |
| `org.springframework:spring-instrument` | Spring Framework | Spring's instrumentation agent for compatible load-time weaving configurations | Only when choosing an LTW path using Spring's agent/instrumentation. |
| `org.aspectj:aspectjtools` | AspectJ | The `ajc` compiler tool for AspectJ compile-time/post-compile weaving | Only when the build is designed for weaving; not needed for Spring proxy AOP. |

**The two most easily confused points:**

1. **Adding `aspectjweaver` so Spring can read `@Aspect` does not mean enabling weaving.** Spring still invokes methods through a proxy; self-invocation is not automatically advised.
2. **`spring-aspects` is different from `spring-aop`.** Do not add `spring-aspects` just because you need `@Aspect`. Custom Spring aspects with `@Aspect` normally use `spring-aop` and `aspectjweaver` without needing `spring-aspects`.

Depending on the version and dependency graph, some libraries are already present **transitively**. The goal is to confirm that the **runtime classpath contains the exact required modules**, avoiding stray standalone versions that conflict with what the Spring ecosystem manages.

## 3. Choosing dependencies by scenario

| Chosen configuration | Dependencies to declare | How to activate |
| --- | --- | --- |
| **Spring Boot 3.x + custom `@Aspect`** | `spring-boot-starter-aop` | Boot auto-configuration; register `@Aspect` as a `@Component` or `@Bean`. |
| **Spring Boot 4.x + custom `@Aspect`** | `spring-boot-starter-aspectj` | Boot auto-configuration; register the aspect bean. |
| **Plain Spring Framework + `@Aspect`** | `spring-context`, `spring-aop`, `aspectjweaver` (direct or transitive via dependency management) | `@EnableAspectJAutoProxy` in Spring configuration; register the aspect bean. |
| **Plain Spring Framework + Spring AOP API like `ProxyFactory`/`MethodInterceptor`** | `spring-aop` along with the Spring modules the application actually uses | Manual proxy/advisor configuration; `aspectjweaver` may not be needed if not using the AspectJ parser or annotations. |
| **Spring + AspectJ weaving for special requirements** | Spring AOP/integration and `aspectjweaver`; possibly `spring-aspects`, `spring-instrument`, or the corresponding compiler tools | Requires dedicated weaving configuration and agent/compiler; adding dependencies alone is not enough. |

**Selection rule:** if you only need advice on **Spring bean methods called through a proxy**, choose among the first three rows depending on your platform. Only consider weaving when there is a confirmed technical requirement that goes beyond the proxy model, such as intercepting self-invocation or objects outside the Spring container.

## 4. Spring Boot 3.x: using `spring-boot-starter-aop`

An application using a **Spring Boot 3.x** parent/BOM usually only needs to add **a single starter**, because the starter manages the dependency chain needed for Spring AOP to work. There is no need to specify separate versions for `spring-aop` and `aspectjweaver` if they are already managed by Boot.

### Maven

In `pom.xml` with a Boot 3.x parent or dependency management:

```xml
<dependencies>
    <!-- Other application starters -->

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-aop</artifactId>
    </dependency>
</dependencies>
```

### Gradle Groovy DSL

In `build.gradle` with the appropriate Spring Boot plugin/BOM applied:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

### Gradle Kotlin DSL

In `build.gradle.kts` with the Spring Boot plugin/BOM applied:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-aop")
}
```

**Accompanying condition:** the aspect must be registered as a Spring bean; typically `@Aspect` **combined with** `@Component` in a package covered by component scan, or declared via `@Bean`. Merely putting `@Aspect` on a class without registering it as a bean is not enough for Spring to apply it.

With Boot auto-configuration and the appropriate AspectJ library on the classpath, the aspect auto-proxy infrastructure is enabled automatically. In this standard case, there is no need to repeat `@EnableAspectJAutoProxy`. Boot uses class-based proxies by default; this can be changed via `spring.aop.proxy-target-class=false` when the JDK interface proxy strategy is needed and the target object supports it.

## 5. Spring Boot 4.x: using `spring-boot-starter-aspectj`

**The starter name changes across Spring Boot generations.** In Boot 4.x, the starter listed in the official documentation is `spring-boot-starter-aspectj`, which contains the components for Spring AOP and AspectJ. When upgrading a project from Boot 3 to Boot 4, you must review dependency names rather than copying configuration meant only for Boot 3 verbatim.

### Maven

In an application with a **Boot 4.x** parent/BOM:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aspectj</artifactId>
</dependency>
```

### Gradle Groovy DSL

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aspectj'
}
```

### Gradle Kotlin DSL

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-aspectj")
}
```

A starter named `aspectj` **does not automatically turn Spring Boot's `@Aspect` into AspectJ weaving**. The application only uses proxy infrastructure unless AspectJ weaving is additionally configured. Self-invocation capabilities and limitations as well as non-bean objects remain those of Spring proxy AOP.

**Do not guess a starter from the word "AspectJ".** Check the Boot version line in `pom.xml`, Gradle plugins, or the BOM first, then pick the artifact matching the generation in use.

## 6. Plain Spring Framework: explicitly declaring Spring AOP and AspectJ

If the application uses Spring Framework directly without Spring Boot auto-configuration, you need the **proper classpath** and to **enable auto-proxying via Spring configuration**.

The `build.gradle` example below is a **fixed sample version set** for learners to try Spring 6.1 on JDK 17, not a claim that it is the latest release:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework:spring-framework-bom:6.1.14')

    implementation 'org.springframework:spring-context'
    implementation 'org.springframework:spring-aop'
    implementation 'org.aspectj:aspectjweaver:1.9.22.1'
}

application {
    mainClass = 'com.example.aopdemo.DemoApp'
}
```

Here:

- `spring-context` provides `AnnotationConfigApplicationContext`, `@Configuration`, and bean management.
- `spring-aop` is listed directly for learning purposes, even though in some dependency graphs it already arrives via `spring-context`; Gradle can merge duplicate module dependencies.
- `aspectjweaver` enables processing `@Aspect` and pointcut expressions. It has an explicit sample version because **the Spring Framework BOM is not by default a version manager for every external non-Spring library**.
- `@EnableAspectJAutoProxy` is the required configuration for a plain Spring example using `@AspectJ`, unlike Spring Boot which is auto-configured.

For Maven in plain Spring, the same principle applies: manage Spring versions via a BOM or project parent, declare the required Spring dependencies, and declare `org.aspectj:aspectjweaver` with a compatible version. Do not arbitrarily mix Spring Framework 6 and 7 or versions managed by competing BOMs.

### Configuration to enable proxying in plain Spring

```java
package com.example.aopdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfig {
    @Bean
    public TransferService transferService() {
        return new TransferService();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

In this example, `proxyTargetClass = true` uses class-based proxying for `TransferService`, which does not implement an interface; if the parameter is omitted and the bean has an interface, the proxy strategy may differ. `@Bean` ensures the aspect bean is registered without requiring `@ComponentScan`.

Depending on the application, the XML equivalent for enabling `@AspectJ`-style support is `<aop:aspectj-autoproxy />` in the `aop` namespace; it also activates **Spring proxy auto-configuration**, not AspectJ weaving.

## 7. Runnable example: verifying that dependencies actually work

To make both the dependency declarations and output easy to follow, the small example uses **Spring Boot 3.5.7, Java 17+**, and the parent can be replaced with any Boot 3.x version managed by your project. This is a standalone Maven project requiring no web server.

### Project structure

```text
spring-aop-dependencies/
├── pom.xml
└── src/main/java/com/example/aopdemo/
    ├── DemoApplication.java
    ├── TransferService.java
    └── TraceAspect.java
```

### `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-aop-dependencies</artifactId>
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
            <artifactId>spring-boot-starter-aop</artifactId>
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

### `src/main/java/com/example/aopdemo/DemoApplication.java`

```java
package com.example.aopdemo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(TransferService service) {
        return args -> service.transfer("TR-101");
    }
}
```

### `src/main/java/com/example/aopdemo/TransferService.java`

```java
package com.example.aopdemo;

import org.springframework.stereotype.Service;

@Service
public class TransferService {
    public void transfer(String transactionId) {
        System.out.println("[SERVICE] transfer " + transactionId);
    }
}
```

### `src/main/java/com/example/aopdemo/TraceAspect.java`

```java
package com.example.aopdemo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TraceAspect {
    @Before("execution(public * com.example.aopdemo.TransferService.transfer(..))")
    public void trace(JoinPoint joinPoint) {
        System.out.println("[AOP] before " + joinPoint.getSignature().getName());
    }
}
```

Run inside the `spring-aop-dependencies` directory with JDK 17+ and Maven installed:

```bash
mvn spring-boot:run
```

Stdout will contain the following lines in order (in addition to the banner and startup logs generated by Spring Boot):

```text
[AOP] before transfer
[SERVICE] transfer TR-101
```

**Why does this result prove the configuration is correct?**

1. `spring-boot-starter-aop` provides the classpath for Spring AOP and `@AspectJ` support.
2. Spring Boot activates the corresponding proxy configuration; both `TransferService` and `TraceAspect` are Spring beans discovered by component scan.
3. `@Before` matches the call from `CommandLineRunner` to `TransferService.transfer()` through the Spring bean, so the `[AOP]` line runs before the `[SERVICE]` line.
4. The program does not need Spring MVC, an HTTP controller, an AspectJ compiler, or a weaving agent to demonstrate this mechanism.

Control experiment: when **temporarily removing `@Aspect` or removing the aspect bean from component scan**, the `[SERVICE]` business code still runs, but the `[AOP]` line disappears. If `service.transfer(...)` is replaced with `new TransferService().transfer(...)`, the call to an object created outside the container does not go through the proxy and therefore does not trigger the advice either. Only use this experiment to verify, then restore the project to its original configuration.

## 8. When do you need `spring-aspects`, `spring-instrument`, or weaving tools?

This is an advanced branch, **different from standard Spring AOP setup**. Adding `spring-aspects` or an agent should not be the default action.

### 8.1. `spring-aspects` is for Spring's built-in aspects that use weaving

`org.springframework:spring-aspects` contains a few built-in aspects provided by Spring, such as support for `@Configurable` on objects instantiated outside the Spring container and certain AspectJ-based transaction models. Those cases require **actual weaving configuration** and the appropriate Spring mechanism.

Do not use `spring-aspects` to "fix" a custom `@Aspect` that is not running. First check bean registration, proxies, pointcuts, and the call path. Adding the `spring-aspects` jar on its own will not automatically turn a custom aspect into weaving.

### 8.2. `spring-instrument` is for the appropriate Spring load-time weaving path

When intentionally choosing **load-time weaving**, `org.springframework:spring-instrument` may be needed if using the instrumentation agent provided by Spring. Some configurations instead use the AspectJ weaving agent directly with `aspectjweaver`. Choosing an agent belongs to runtime architecture, not the default Spring AOP setup step.

If choosing LTW, you must also consider `META-INF/aop.xml`, classloaders, how the agent is attached to the JVM, and testing procedures. **Having `aspectjweaver` on the classpath is not enough to claim that LTW is active.**

### 8.3. When only using Spring proxies, `aspectjtools` is not needed

`org.aspectj:aspectjtools` contains the `ajc` compiler; it is a tool for AspectJ build/weaving. A project that only uses Spring AOP annotations and proxies does not need `aspectjtools` in its runtime dependencies.

In a Spring application, only consider the weaving toolset when there is a real requirement such as pointcuts that cannot be expressed with Spring proxy AOP, objects that must be intercepted outside the container, or specialized `@Configurable`/transaction weaving mechanisms.

## 9. Inspecting the dependency graph and classpath instead of guessing

### Maven

At the project root:

```bash
mvn dependency:tree
```

With **Boot 3.x**, expect the dependency tree to contain `spring-boot-starter-aop`, `spring-aop`, and `aspectjweaver` via direct or transitive dependencies.

With **Boot 4.x**, look for `spring-boot-starter-aspectj`, `spring-aop`, and `aspectjweaver`.

Inspect the resolved versions further when multiple Spring-group dependencies appear:

```bash
mvn dependency:tree -Dverbose
```

Exact output depends on the Maven dependency plugin version; `mvn dependency:tree` is usually sufficient to determine whether an artifact is on the classpath tree.

### Gradle

With Gradle Groovy or Kotlin DSL:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-aop --configuration runtimeClasspath
./gradlew dependencyInsight --dependency aspectjweaver --configuration runtimeClasspath
```

On Windows PowerShell, replace `./gradlew` with `.\gradlew.bat`. `dependencyInsight` shows which module was selected along which dependency path and under which version management mechanism.

**Reading the output properly:** seeing an artifact in `compileClasspath` does not prove it is present at application runtime; you need to check **`runtimeClasspath`**, especially when the project has custom configurations, excludes, or executable packaging.

## 10. Common errors when choosing Spring AOP libraries

| Symptom | What to check | How to resolve |
| --- | --- | --- |
| Package `org.aspectj.lang.annotation` not found at compile time | Is `aspectjweaver`/a dependency containing AspectJ APIs missing from compile classpath? | Add the right starter for your Boot version or declare the AspectJ dependency for plain Spring; reload dependencies. |
| Startup fails on classes related to `org.aspectj.weaver` or the pointcut parser | Is `aspectjweaver` actually on the runtime classpath? | Check tree/insight, exclusions, and dependency scope; align with the version managed by the project. |
| `@Aspect` exists but advice does not run | Is the aspect a **Spring bean**? Is auto-proxying enabled in plain Spring? Does the pointcut match? Does the call go through the proxy? | Check sequentially: bean registration → enablement → pointcut → proxy boundary. |
| Upgraded Boot 3 to Boot 4 while keeping the old starter declaration | Do the artifact and version belong to the current Boot generation? | Use the starter and official documentation for the exact Boot generation. |
| Added `spring-aspects` but custom advice still does not work | Are you confusing the specialized weaving aspect library with Spring proxies? | Go back to `spring-aop` + `aspectjweaver` and check enablement/registration. |
| Added `aspectjweaver` yet self-invocation is still not advised | Are you actually using Spring proxies or real AspectJ weaving? | Understand Spring proxy limitations, and prefer extracting the call into another bean when appropriate. |
| `NoSuchMethodError`, `ClassNotFoundException` after upgrading | Was a Spring/AspectJ dependency forced to an incompatible version? | Cross-check the BOM and dependency graph and remove unnecessary overrides; do not guess the cause from the exception name alone. |
| Advice runs twice or unexpected proxies appear | Are multiple advisor, aspect, or proxy creator configurations involved? | Review `@Aspect` beans, transaction/AOP configurations, pointcuts, and proxy creation order. |

**Distinguishing library errors from activation errors:** if `@Aspect` code compiles, you cannot immediately conclude that dependencies alone are sufficient for advice to run. Executing advice also requires the aspect bean to exist in the context, the Spring proxy to be created, the pointcut to match, and a call to pass through the proxy.

## 11. Decision workflow for an existing Spring project

1. **Identify the runtime environment:** Spring Boot 3.x, Boot 4.x, or plain Spring Framework. Check the parent/BOM/plugins the project actually uses.
2. **Identify the AOP model:** typical Spring proxy `@Aspect`, hand-built Spring AOP API, or intentionally chosen AspectJ weaving.
3. **Choose minimal dependencies:** Boot 3.x → `spring-boot-starter-aop`; Boot 4.x → `spring-boot-starter-aspectj`; plain Spring + `@Aspect` → container, `spring-aop`, `aspectjweaver`.
4. **Let dependency management control versions:** keep Spring modules on the same version line published by the project/BOM. Avoid mixing Spring Framework 6/7 versions or overriding AspectJ arbitrarily.
5. **Activate the proper infrastructure:** Boot auto-configuration; plain Spring uses `@EnableAspectJAutoProxy` or the XML equivalent.
6. **Register the aspect as a Spring bean:** use `@Aspect` combined with `@Component`/component scan, or `@Bean`.
7. **Verify the runtime classpath and a real call:** run a short example whose stdout can be verified; if advice does not run, check bean → pointcut → proxy in turn instead of adding libraries blindly.
8. **Expand to weaving only when needed:** document the agent/compiler mechanism, additional libraries, and dedicated tests for the weaving path.

### Official sources for version cross-referencing

- Spring Framework — @AspectJ support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework — Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — Using AspectJ with Spring Applications: https://docs.spring.io/spring-framework/reference/core/aop/using-aspectj.html
- Spring Boot — Aspect-Oriented Programming: https://docs.spring.io/spring-boot/reference/features/aop.html
- Spring Boot 3.x — Build Systems/starters: https://docs.spring.io/spring-boot/3.4/reference/using/build-systems.html
- Spring Boot 4.x — Build Systems/starters: https://docs.spring.io/spring-boot/4.0/reference/using/build-systems.html

For **Spring AOP applied to ordinary beans**, a proper setup is confirmed by three signs: the classpath contains the required libraries, Spring registers and proxies the matching beans, and a call through the proxy actually runs the advice as expected. Libraries are only the first condition; Spring configuration and the call path determine the final behavior.
