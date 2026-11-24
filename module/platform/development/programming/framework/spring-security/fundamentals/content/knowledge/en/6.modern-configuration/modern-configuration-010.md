# Identifying Legacy APIs in Examples and Looking Up Syntax for Your Active Spring Security Version

A Spring Security tutorial on the Internet may run perfectly in its author's environment yet fail to compile in your project. Examples using `WebSecurityConfigurerAdapter`, `antMatchers`, `authorizeRequests`, or chaining DSL calls with `.and()` were valid in earlier Spring Security generations, but were deprecated or removed across upgrade milestones. The error does not necessarily mean you wrote invalid Java: **an example that was right for version A may no longer be a valid API in version B**.

This lesson helps you **spot legacy example signals, determine the version actually being built, look up the right documentation/Javadoc, and migrate to the appropriate syntax without accidentally altering your security policy**. The focus is Spring Security for **Spring MVC / Servlet** and configuration with `SecurityFilterChain`. The complete runnable example uses **Spring Boot 3 + Spring Security 6 + Java 17+**, while explaining what to verify when moving to **Spring Boot 4 + Spring Security 7**.

> Learning principle: Never pick an API merely because a snippet appeared in a recently published post. **Anchor on the version actually resolved by your build, open documentation for that exact version line, and verify with compilation and behavioral tests.**

## 1. Why Do Security Examples Break After Upgrades?

A Java project has multiple version layers:

- **JDK**: determines language features, class library, bytecode, and runtime.
- **Spring Framework**: provides the IoC container, Web MVC, proxies, servlet integration, and annotations.
- **Spring Boot**: provides starters, auto-configuration, plugins, and dependency management.
- **Spring Security**: provides authentication, authorization, filter chains, password utilities, and test support.
- **Jakarta Servlet API** or reactive stack: determines import namespaces and web processing flow.
- **Other dependencies**: OAuth2, JWT, databases, testing, Spring Cloud, custom DSLs.

Example:

```text
Legacy learning material:
Spring Boot 2.x + Spring Security 5.x + javax.servlet.*
    -> WebSecurityConfigurerAdapter / antMatchers / legacy DSL configuration

Spring Boot 3 learning material:
Spring Boot 3.x + Spring Security 6.x + jakarta.servlet.*
    -> SecurityFilterChain bean / requestMatchers / Lambda DSL

Spring Boot 4 learning material:
Spring Boot 4.x + Spring Security 7.x
    -> SecurityFilterChain + mandatory Lambda DSL
    -> continue checking Boot 4 and Security 7 specific changes
```

These are **version lines that commonly travel together**, not a rule for inferring every minor/patch release. Let your project's BOM/dependency management resolve compatible versions. Never force a newer Spring Security JAR into an older Boot project just to use a method seen in newer docs.

### 1.1. Milestone Changes to Remember

| Milestone | Key change | Impact when copying examples |
| --- | --- | --- |
| Spring Security **5.4** | Support configuring web security with a `SecurityFilterChain` bean | Component-based style can replace the adapter |
| Spring Security **5.7** | `WebSecurityConfigurerAdapter` deprecated | Tutorials using `extends WebSecurityConfigurerAdapter` become an update signal |
| Spring Security **6.0** | Removed `WebSecurityConfigurerAdapter` and many legacy matcher APIs; moved to Jakarta baseline in Spring Framework 6 | `extends WebSecurityConfigurerAdapter`, legacy `antMatchers`, `javax.servlet` imports usually fail to compile |
| Spring Security **6.x** | `SecurityFilterChain` + `authorizeHttpRequests` + `requestMatchers` is the modern Servlet config pattern | Permission equivalence can be preserved with careful testing during migration |
| Spring Security **6.2+** | `HttpSecurity.apply(...)` for custom DSLs deprecated; `with(...)` recommended | Custom DSL authors should check migration APIs |
| Spring Security **6.5 -> 7.0** | Migration guides prepare for mandatory Lambda DSL | Configs like `.authorizeHttpRequests().and()` must be rewritten |
| Spring Security **7.0** | Removed legacy `.and()` DSL style and `authorizeRequests` per What's New docs; legacy Access Decision APIs split into legacy module | Do not copy `authorizeRequests` or legacy DSL chaining tutorials verbatim on 7.x builds |

These milestones explain **why looking up the exact version matters**, rather than serving as an exhaustive list of every change. When upgrading, read release notes/migration guides for **each version step**, because beyond syntax, default behaviors, matcher semantics, dependency modules, or filter ordering can change.

## 2. Determining the Version Actually Being Built

This is step one before changing any import or API.

### 2.1. Gradle Projects

Inspect `plugins`, `dependencies`, and platform/BOM config in `build.gradle` or `build.gradle.kts`; then ask Gradle which version was **ultimately resolved**.

```bash
# Project using Gradle Wrapper (macOS/Linux)
./gradlew --version

# Find actual spring-security-config version in the runtime graph
./gradlew dependencyInsight \
  --dependency spring-security-config \
  --configuration runtimeClasspath

# Find versions of core, web, crypto and what pulled them in
./gradlew dependencyInsight \
  --dependency spring-security-core \
  --configuration runtimeClasspath

# Full runtime classpath
./gradlew dependencies --configuration runtimeClasspath

# Test classpath, where spring-security-test may differ if misconfigured
./gradlew dependencies --configuration testRuntimeClasspath
```

In Windows PowerShell, write the command on **one line** and use `.\gradlew.bat`, for example:

```powershell
.\gradlew.bat dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
.\gradlew.bat dependencies --configuration testRuntimeClasspath
```

`dependencyInsight` is more informative than glancing at `implementation` lines because libraries can be pulled in **transitively**, and versions may be chosen by a BOM, constraints, or resolution strategies. When output shows multiple variants/configurations, read the exact configuration used for compiling/running. `compileClasspath` can also be worth checking when the IDE reports a missing method; `runtimeClasspath` confirms what actually runs.

### 2.2. Maven Projects

```bash
mvn -version

# Inspect Spring Security artifacts and resolved versions
mvn dependency:tree -Dincludes=org.springframework.security

# When checking versions managed via parent/BOM
mvn help:effective-pom
```

If using Maven Wrapper:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.security
```

In PowerShell, mind shell syntax and you can use `.\mvnw.cmd`. Never infer versions from a snippet lacking `parent` or `dependencyManagement`; the BOM may determine the true version numbers.

### 2.3. Checking the JDK and Web Stack

```bash
java -version
javac -version
```

Then confirm:

- Does the project use `spring-boot-starter-web` (Servlet/MVC) or `spring-boot-starter-webflux` (Reactive)?
- Is it using `HttpSecurity` and `SecurityFilterChain`, or `ServerHttpSecurity` and `SecurityWebFilterChain`?
- Are Servlet imports `jakarta.servlet.*` or `javax.servlet.*`?
- Are `spring-security-core`, `web`, `config`, `crypto`, and `test` aligned on consistent versions?

**Do not paste Servlet `HttpSecurity` configuration directly into WebFlux.** Reactive has different security chains, matchers, and testing APIs.

### 2.4. If You Only Have a JAR Without Build Sources

For a packaged artifact, you can inspect `META-INF/MANIFEST.MF` or build metadata inside that JAR, though available details depend on packaging and are not always complete. Returning to the build file/BOM/lockfile or dependency resolver output is best. Looking solely at abbreviated JAR filenames can also mislead when an app uses a fat JAR with embedded dependencies.

## 3. Spotting Legacy APIs from Just a Few Lines of Code

The table below helps **spot and question**, not blindly replace everything via find-and-replace.

| Pattern seen in an article | Why is it suspect? | Modern direction | What to check before replacing |
| --- | --- | --- | --- |
| `extends WebSecurityConfigurerAdapter` | Deprecated 5.7, removed 6 | `SecurityFilterChain` bean; separate beans for user store/provider | Are there legacy `configure(HttpSecurity)`, `configure(AuthenticationManagerBuilder)`, or `configure(WebSecurity)` methods? |
| `@Override protected void configure(HttpSecurity http)` in adapter | Ties policy to legacy superclass | `@Bean SecurityFilterChain filterChain(HttpSecurity http)` | Are session/filter/entry point configs needing migration? |
| `authorizeRequests()` | Legacy authorization pipeline; removed 7 | `authorizeHttpRequests(auth -> ...)` | Semantics of `FilterSecurityInterceptor`/`AuthorizationFilter` and custom authorization |
| `antMatchers(...)` / `mvcMatchers(...)` in rules | Legacy overloads absent in 6 | `requestMatchers(...)` | Path matching, Servlet path, HTTP method, and edge cases |
| `http.antMatcher("/api/**")` | Legacy chain scoping style | `http.securityMatcher("/api/**")` | Chain order, fallback, and unmatched URLs |
| `http.authorizeHttpRequests().anyRequest()...and()` | Legacy builder chaining; removed in 7 | Lambda DSL `authorizeHttpRequests(auth -> ...)` | Ensure each configurer sits inside the right lambda without changing rule logic |
| `http.csrf().disable()` | Uses legacy chained configurer | `csrf(csrf -> csrf.disable())` if justified | Is disabling CSRF truly needed? What is the credential/cookie model? |
| `http.httpBasic()` / `http.formLogin()` without Customizer | Legacy no-arg DSL syntax, invalid in 7 | `httpBasic(Customizer.withDefaults())` / `formLogin(Customizer.withDefaults())` | Which clients receive a Basic challenge vs. form redirect? |
| `http.apply(customDsl)` | `apply` deprecated since 6.2 | `http.with(customDsl, dsl -> ...)` | Which version does the custom DSL target? |
| `@EnableGlobalMethodSecurity(prePostEnabled = true)` | Legacy method security enablement, usually moved to `@EnableMethodSecurity` | `@EnableMethodSecurity` and `@PreAuthorize` | Is method security actually active? Proxy/self-invocation? |
| `javax.servlet.http.HttpServletRequest` | Fits legacy Servlet baseline; Boot 3/Framework 6 uses Jakarta | `jakarta.servlet.http.HttpServletRequest` | Must migrate dependencies/namespaces together; changing imports alone is insufficient |
| `web.ignoring().antMatchers("/static/**")` | Legacy matcher API, also skips security filters | Consider `requestMatchers("/static/**").permitAll()` | Should static resources retain security headers/filters? |
| `User.withDefaultPasswordEncoder()` | Convenient for demos, unsuitable for production | `PasswordEncoder` with BCrypt/Delegating | Password hashes, migration, and user store |
| `AccessDecisionManager` / `AccessDecisionVoter` | Legacy authorization architecture, split to `spring-security-access` in 7 | `AuthorizationManager` | Must migrate policies, not just swap imports |
| `@EnableWebSecurity` with unfamiliar configs | Not automatically an error; may be needed per project | Check Boot auto-config and existing chains | Avoid creating conflicting chains or unintentionally disabling default configuration |

**Not every line that looks "old" has been removed in every version.** For example, `authorizeRequests` may still exist in some 6.x releases while removed in 7. The goal is identifying **what to verify against your exact version**, not labeling code broken solely because syntax differs from the newest example.

### 3.1. Distinguish the Types of Changes

- **Deprecated:** compiler/IDE warns, yet the API may still run in the current version; usually has a planned replacement.
- **Removed:** the symbol/method/class no longer exists in the active version; compile or linkage failure.
- **Changed behavior:** code still compiles, yet matchers, filters, default policies, or mappings changed.
- **Configuration mistake:** the API exists, yet matchers/chains are misordered or `permitAll()` accidentally exposes endpoints.
- **Wrong stack:** copying Servlet APIs into WebFlux or vice versa.
- **Wrong dependency:** the code uses a method valid in docs while the classpath holds another version.

Classify before fixing. A `Cannot resolve symbol` error differs from an API that compiles cleanly yet leaves requests unprotected.

## 4. Migrating from WebSecurityConfigurerAdapter to SecurityFilterChain

### 4.1. Legacy Pattern to Recognize, Not Copy for Spring Security 6+

In Spring Security 5.x documentation you may see:

```java
// OLD: illustrative snippet from the WebSecurityConfigurerAdapter style.
@Configuration
class OldSecurityConfig extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/public/**").permitAll()
                .antMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            .and()
            .httpBasic();
    }
}
```

Telltale signs: adapter class, overridden `configure`, `antMatchers`, and `.and()`. This pattern **depends on an older generation Spring Security API**, not Java 17/Spring Boot 3 code that runs verbatim.

### 4.2. Component-Based Pattern Suited to Spring Security 6

```java
@Configuration
class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

What changed:

1. No longer extends `WebSecurityConfigurerAdapter`. Configuration is wrapped in a `SecurityFilterChain` bean.
2. `authorizeHttpRequests` replaces the old example's `authorizeRequests`.
3. `requestMatchers` replaces `antMatchers` in the authorization DSL, though you must re-verify URL/HTTP method matching behavior.
4. `.httpBasic(Customizer.withDefaults())` uses consistent Lambda DSL syntax.
5. `.build()` produces the chain for Servlet filters.
6. `anyRequest().authenticated()` only requires login; if this is a sensitive app, decide whether undeclared routes should use `denyAll()` instead.
7. `hasRole("ADMIN")` checks authority `ROLE_ADMIN` by default. User/role sources must be configured separately.

**Do not stop at compilation.** Test anonymous callers, USER, ADMIN, public/admin URIs, and all remaining paths. If the app has multiple filter chains, verify which chain actually receives each request.

### 4.3. From configure(AuthenticationManagerBuilder) to Beans

If an old example overrides:

```java
@Override
protected void configure(AuthenticationManagerBuilder auth)
        throws Exception {
    auth.inMemoryAuthentication()
        .withUser("reader")
        .password("{noop}password")
        .roles("USER");
}
```

Instead of porting mechanically, a modern Spring Boot example can register:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}

@Bean
UserDetailsService userDetailsService(PasswordEncoder encoder) {
    var reader = User.withUsername("reader")
        .password(encoder.encode("demo-password"))
        .roles("USER")
        .build();

    return new InMemoryUserDetailsManager(reader);
}
```

This is a **code snippet inside a Spring application**, requiring proper imports and dependencies. `{noop}` from the old snippet should only be used in tightly constrained test settings; production must use properly designed password hashing. For JDBC, LDAP, OAuth2, or custom providers, configuration differs; **not everything turns into `InMemoryUserDetailsManager`**.

### 4.4. When an AuthenticationManager Bean Is Needed

Some legacy code called `authenticationManagerBean()` on the adapter. In Spring Security 6 apps, you can obtain the configured `AuthenticationManager` via `AuthenticationConfiguration` when needed:

```java
@Bean
AuthenticationManager authenticationManager(
        AuthenticationConfiguration configuration
) throws Exception {
    return configuration.getAuthenticationManager();
}
```

Register this bean only when your architecture truly needs to inject the manager into another component; built-in filters operate through Spring Security's configuration without you exposing an authentication manager bean yourself. With multiple providers or chains, verify which manager is actually used.

## 5. Migrating Legacy Rules: antMatchers, mvcMatchers, and authorizeRequests

### 5.1. Legacy Pattern

```java
// OLD: matches certain Spring Security 5 tutorials.
http.authorizeRequests()
    .antMatchers(HttpMethod.GET, "/public/**").permitAll()
    .antMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated();
```

Equivalent pattern in Spring Security 6:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
```

**What must not be overlooked:** `requestMatchers` has multiple overloads and chooses `RequestMatcher` implementations based on classpath/context. Spring MVC path matching, servletPath, context paths, and path patterns can differ in edge cases from legacy Ant style. When policies govern sensitive paths, **write integration tests for exact paths** rather than treating this as a 100% equivalent string swap.

Example edge cases to test when migrating:

- `/admin` vs. `/admin/`;
- `/admin/users` vs. `/admin-other`;
- non-root servlet paths;
- paths with encoded characters or semicolons when routing permits them;
- GET vs. POST methods;
- fallbacks across multiple security chains.

Keep tests meaningful for your real routing config; the goal is catching accidentally exposed endpoints, not hunting for one magic string syntax that guarantees all apps.

### 5.2. securityMatcher Selects the Chain, requestMatchers Selects the Rule

Another easily confused snippet:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().denyAll()
    );
    return http.build();
}
```

- `securityMatcher("/api/**")` limits **the entire first chain**.
- `requestMatchers("/api/admin/**")` selects a rule **inside the already-matched chain**.
- `@Order(1)` sets the highest-priority chain first.
- The second chain declares no `securityMatcher`, acting as the fallback.
- `anyRequest().denyAll()` on fallback does not alter the API chain's matcher; it applies only to requests accepted by the fallback chain.

If you migrate `http.antMatcher("/api/**")` to `http.securityMatcher("/api/**")` and forget a fallback, requests outside `/api/**` can **bypass every Spring Security filter chain**. That is a critical configuration bug even though source code compiles cleanly.

### 5.3. web.ignoring Differs from permitAll

Some older posts write:

```java
// OLD / use only when you genuinely want to skip Spring Security filters:
@Override
public void configure(WebSecurity web) {
    web.ignoring().antMatchers("/static/**");
}
```

In many applications, what you actually want is allowing public assets to be read while retaining protective filters/headers:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/static/**").permitAll()
    .anyRequest().authenticated()
);
```

`permitAll` **differs** from excluding requests from Spring Security. There are cases needing `WebSecurityCustomizer` to ignore requests, yet you must understand the boundary; never use `ignoring` as a shortcut to fix 401/403 errors without evaluating lost protections.

## 6. Migrating from Legacy DSL to Lambda DSL

### 6.1. Recognizing the .and() Chaining Style

In older tutorials:

```java
// OLD: non-lambda DSL pattern.
http.authorizeHttpRequests()
        .anyRequest().authenticated()
        .and()
    .formLogin()
        .loginPage("/login")
        .permitAll()
        .and()
    .httpBasic();
```

Pattern better suited for Spring Security 6 and mandatory in Spring Security 7:

```java
http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    )
    .formLogin(form -> form
        .loginPage("/login")
        .permitAll()
    )
    .httpBasic(Customizer.withDefaults());
```

In the Lambda DSL, each configuration section lives inside a lambda receiving its own configurer object. `HttpSecurity` is returned after each lambda; **`.and()` is unnecessary**.

### 6.2. Why Does the Lambda DSL Improve Readability?

Example with CSRF:

```java
http.csrf(csrf -> csrf
    .csrfTokenRepository(tokenRepository)
);
```

It reads directly as "the CSRF configurer receives a repository setting." With the old DSL, you had to track which builder `.and()` returned before chaining the next step. Several no-arg APIs were deprecated before removal in the next major release.

**Never change security posture just because syntax changed.** Rewriting `csrf().disable()` to `csrf(csrf -> csrf.disable())` still leaves **CSRF protection disabled**; the code may look modern syntactically without being secure. First confirm whether CSRF fits the threat model, especially for apps using session cookies.

### 6.3. Common DSL Translations

| Old style you may encounter | More readable lambda style | Keep in mind |
| --- | --- | --- |
| `http.httpBasic()` | `http.httpBasic(Customizer.withDefaults())` | Enables Basic with defaults |
| `http.formLogin()` | `http.formLogin(Customizer.withDefaults())` | Enables form login with defaults |
| `http.csrf().disable()` | `http.csrf(csrf -> csrf.disable())` | Disable only if designed and verified |
| `http.headers().frameOptions().disable()` | `http.headers(headers -> headers.frameOptions(frame -> frame.disable()))` | Mind clickjacking; change only when needed |
| `http.sessionManagement().sessionCreationPolicy(...)` | `http.sessionManagement(s -> s.sessionCreationPolicy(...))` | Changing syntax does not alter session policy |
| `http.apply(myDsl)` | `http.with(myDsl, dsl -> ...)` from matching version | Used for custom DSLs; check exact version Javadoc |
| `authorizeRequests()` | `authorizeHttpRequests(auth -> ...)` | Verify permissions on every URL |
| `antMatchers(...)` | `requestMatchers(...)` | Verify matcher semantics |

No expression in the table can simply be dropped into arbitrary code without imports or beans. Check the exact lambda type of **the method on your active version's class** and consult complete official examples.

## 7. Method Security: From @EnableGlobalMethodSecurity to @EnableMethodSecurity

Older tutorials often show:

```java
// OLD:
@EnableGlobalMethodSecurity(prePostEnabled = true)
class LegacyMethodSecurityConfig {
}
```

In Spring Security 6, the standard form is:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

`@EnableMethodSecurity` enables method security interceptors the modern way; pre/post annotations like `@PreAuthorize` are supported by default. There is no need to copy old parameters mechanically.

Example:

```java
@Service
class ReportService {
    @PreAuthorize("hasAuthority('report:read')")
    public String read() {
        return "report";
    }
}
```

To test whether this method is protected, call it through a Spring-managed bean/proxy. **Self-invocation** (`this.read()` inside the same object) can bypass the proxy so the annotation is not enforced as expected.

### 7.1. Method Parameters in SpEL Expressions

An example using `@PreAuthorize("@authz.check(#orderId, authentication)")` may depend on Spring discovering Java parameter names. In Spring Framework 6.1+, when checking permissions based on parameter names, compile with `-parameters` as appropriate or reference parameters in a way supported by your version.

Gradle Java example:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
```

Do not evaluate changes solely by looking at annotations in the IDE: test actual calls and denied cases. Crucially, method security does not automatically know whether the user owns an order ID or belongs to the resource's tenant unless the policy checks it.

## 8. Recognizing Java EE / Jakarta EE Namespaces

Spring Boot 3 ships with Spring Framework 6, moving Servlet APIs and many Jakarta EE APIs to the `jakarta.*` namespace:

```java
// OLD: Java EE servlet namespace
import javax.servlet.http.HttpServletRequest;

// Spring Boot 3 / Spring Framework 6:
import jakarta.servlet.http.HttpServletRequest;
```

Similarly for Bean Validation:

```java
// OLD:
import javax.validation.Valid;

// With Spring Boot 3:
import jakarta.validation.Valid;
```

Not every `javax.*` package changes to `jakarta.*`. For instance, `javax.crypto` and `javax.net.ssl` are Java SE packages and **do not change** when Spring Boot upgrades. Never run a global search-and-replace from `javax` to `jakarta` across the entire codebase.

Changing imports while keeping old servlet/validation dependencies can fail to compile or trigger runtime errors. Upgrade the whole stack per the migration guide, especially the servlet container, security filters, validation starter, and third-party libraries.

## 9. What Else to Check When a Project Uses Spring Security 7?

Spring Security 7 introduces larger configuration API changes:

1. **Mandatory Lambda DSL:** `.and()` chaining is no longer valid.
2. **Legacy `authorizeRequests` removed:** use `authorizeHttpRequests` and matching policies.
3. **Several legacy AccessDecision APIs** moved to the `spring-security-access` module, while `AuthorizationManager` is the recommended direction.
4. **Custom DSLs:** if still using `HttpSecurity.apply`, check `with` and DSL initialization patterns.
5. **Method security:** review migration changes for annotation templates, parameter names, and application-specific components.
6. **Integrations such as Jackson** may change between Spring Boot/Spring Security lines; never copy old serializer configuration classes/modules unconditionally.
7. **Build tools/plugins/test packages:** upgrade alongside Spring Boot 4 docs; never assume a Spring Boot 3 test compiles verbatim in Boot 4.

Pick documentation with explicit versioned URLs, for example:

- Spring Security 6.5: `https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html`
- Spring Security 7.0: `https://docs.spring.io/spring-security/reference/7.0/servlet/configuration/java.html`
- Preparing from 6.5 to 7: `https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html`
- Migration 7: `https://docs.spring.io/spring-security/reference/7.0/migration/`

**Never guess "the latest version" from an author's memory.** At the time you work, check your dependency resolver, the stable docs list, and patch versions approved by your organization/project. This lesson intentionally uses version-pinned URLs so references remain stable.

## 10. How to Look Up Javadoc and Documentation: A Repeatable Workflow

When an example fails to compile, follow this sequence:

```text
1. Capture exact error and symbol
       |
       v
2. Verify Gradle/Maven resolved Spring Security version
       |
       v
3. Identify Servlet vs. WebFlux and Boot/JDK versions
       |
       v
4. Open docs for the exact major.minor (do not just search snippets)
       |
       v
5. Open the API / package in Javadoc for that same version
       |
       v
6. Read migration guides between the example's version and your project
       |
       v
7. Translate policies + imports + beans semantically
       |
       v
8. Compile and test both allowed + denied requests
       |
       v
9. Inspect runtime security chain and confirm no endpoints leaked open
```

### 10.1. Effective Search Queries

Suppose you are using Spring Security 6.5:

```text
site:docs.spring.io/spring-security/reference/6.5/
    "SecurityFilterChain" "authorizeHttpRequests"

site:docs.spring.io/spring-security/reference/6.5/
    "requestMatchers" "securityMatcher"

site:docs.spring.io/spring-security/reference/6.5/migration-7/
    "Lambda DSL"
```

These search queries can be typed on **a single line** in a search engine; line breaks here are for readability. For Security 7, swap `/6.5/` to `/7.0/` or your confirmed version. Rely on official reference pages and Javadocs rather than truncated snippets missing imports, config, chain matchers, test setup, and security context.

### 10.2. Javadoc Answers Three Questions

When the IDE reports `Cannot resolve method`, look up the versioned Javadoc for the **receiver type**:

- Which overloads of `authorizeHttpRequests`, `csrf`, and `httpBasic` does `HttpSecurity` have?
- Which `requestMatchers` does the corresponding `AuthorizeHttpRequestsConfigurer` / registry expose?
- Do `AuthenticationManager`, `UserDetailsService`, and `AuthorizationManager` have those exact method signatures?

Then check `@since`/`@Deprecated`, related classes, and official samples. A method missing from package A does not always mean a missing Java import; you may be reading an example meant for **another version or another builder type**.

### 10.3. When a Method Exists in Docs Yet the IDE Still Cannot See It

Check:

1. Does `compileClasspath` match the exact version whose docs you are reading?
2. Is the IDE importing the right Gradle/Maven module?
3. Are multiple versions of `spring-security-config`/`core` on the classpath due to BOM overrides?
4. Did you import the right class? `HttpSecurity` differs from `ServerHttpSecurity`.
5. Were `javax.servlet` packages migrated to `jakarta.servlet` per the Boot 3 baseline?
6. Does the method live on `HttpSecurity` itself or on the configurer inside the lambda?
7. Does the build error originate from Java source or from annotation processors/generated code?

After fixing dependencies, refresh/reimport Gradle/Maven in the IDE and run a command-line build. **Never "fix" compilation errors by disabling security** or deleting matchers.

## 11. Complete Spring Boot 3 / Spring Security 6 Example

This example illustrates modern configuration with three behaviors:

- GET `/public`: allows anonymous callers.
- GET `/me`: requires HTTP Basic login.
- GET `/admin`: requires authority `ROLE_ADMIN`.

It uses a **`SecurityFilterChain` bean**, **Lambda DSL**, and **`UserDetailsService`** instead of the legacy adapter, with tests proving no endpoint is accidentally exposed during API migration.

### 11.1. Project Dependencies

In `build.gradle` of a Spring Boot 3 project using Java 17+ with the Spring Boot Gradle plugin, repository, and dependency management already configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is a **dependencies block**, not a complete build file. Never manually add versions to individual Spring Security JARs when the Boot BOM manages them.

### 11.2. Main Class

Create `src/main/java/example/versionguide/VersionGuideApplication.java`:

```java
package example.versionguide;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class VersionGuideApplication {
    public static void main(String[] args) {
        SpringApplication.run(VersionGuideApplication.class, args);
    }
}
```

### 11.3. SecurityConfig Using Lambda DSL

Create `src/main/java/example/versionguide/SecurityConfig.java`:

```java
package example.versionguide;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-alice-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin-pass"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/me")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Mapping the changes:

- `SecurityFilterChain` replaces the legacy adapter.
- `authorizeHttpRequests` and `requestMatchers` replace `authorizeRequests`/`antMatchers`.
- `Customizer.withDefaults()` enables HTTP Basic in lambda form.
- `anyRequest().denyAll()` denies undeclared endpoints.
- `BCryptPasswordEncoder` avoids storing plaintext passwords in the user store.
- `@Configuration` registers separate beans instead of overriding `configure` methods.

This configuration intentionally opens only specific GET endpoints; if you add a new controller, you must update the rules. This is a learning example, not a production configuration: hardcoded credentials are for local use only, and HTTP Basic must run over HTTPS for real data.

### 11.4. Controller

Create `src/main/java/example/versionguide/DemoController.java`:

```java
package example.versionguide;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Principal principal) {
        return principal.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin";
    }
}
```

`Principal` is supplied by Spring MVC from the authenticated request context. The controller neither handles passwords nor trusts a client-sent `X-User-Id` header.

### 11.5. Running and Observing

In the root of the Spring Boot project with Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows:

```powershell
.\gradlew.bat bootRun
```

Once the application listens at `http://localhost:8080`:

```bash
# 200: public endpoint
curl -i http://localhost:8080/public

# 401: unauthenticated
curl -i http://localhost:8080/me

# 200: Alice with valid credentials
curl -i -u alice:demo-alice-pass http://localhost:8080/me

# 403: Alice lacks ROLE_ADMIN
curl -i -u alice:demo-alice-pass http://localhost:8080/admin

# 200: Admin has ROLE_ADMIN
curl -i -u admin:demo-admin-pass http://localhost:8080/admin

# 401: wrong password
curl -i -u alice:wrong-pass http://localhost:8080/me
```

The HTTP codes here **are expectations from the sample configuration**. Body/header details, realm, and response header order can vary. `curl -u` with inline passwords is for local demo only; real secrets need HTTPS and safe handling to avoid leaking in shell history/process lists.

## 12. Testing to Prevent Syntax Changes from Changing Behavior

Before migrating, record expected outcomes from the existing API. After moving to `SecurityFilterChain`, run the same request suite against the new configuration.

Add `spring-security-test` to the test classpath as in Section 11.1. Create `src/test/java/example/versionguide/SecurityVersionMigrationTest.java`:

```java
package example.versionguide;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityVersionMigrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicGetIsAllowed() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousMeIsChallenged() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicUserCanReadOwnName() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("alice", "demo-alice-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void userCannotAccessAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("alice", "demo-alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "demo-admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void invalidCredentialsAreRejected() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("alice", "wrong-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownRouteIsNotPublic() throws Exception {
        mvc.perform(get("/unregistered"))
            .andExpect(status().isForbidden());
    }
}
```

Run:

```bash
./gradlew test --tests example.versionguide.SecurityVersionMigrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.versionguide.SecurityVersionMigrationTest
```

**Expected:** the first six cases pass with the described statuses. For `/unregistered`, `denyAll` denies even anonymous callers so modern Spring Security typically returns 403, though exact status may be affected by entry points, exception handling, and version; if it differs, verify that the endpoint **is neither public nor returning data** and adjust the assertion to match your real policy. These are **suggested tests**, not results already executed in this document.

**For real projects undergoing upgrades**, add strict tests for:

- GET/POST and per-HTTP-method permissions;
- Admin, regular user, anonymous, and specific authorities;
- Chain ordering and URLs outside `securityMatcher`;
- Resource IDs belonging to another owner/tenant;
- Missing/invalid/valid CSRF tokens when using cookies/sessions;
- OAuth2 login/logout endpoints and token parsing if used;
- Forward/error dispatcher requests when custom configurations exist;
- Guaranteeing no side effects occur when policy denies a request.

Never "fix" failing tests by deleting `@PreAuthorize`, changing `denyAll` to `permitAll`, or disabling CSRF without understanding the root cause. **A successful migration preserves security requirements, not merely turns the compiler green.**

## 13. Standalone Java 17: A Tool to Scan for Legacy API Signals

You do not always need an IDE open to spot legacy API signals. The small tool below **compiles with plain Java 17**, reads a text/Java file, and prints lines containing keywords along with lookup hints. It is intentionally a **text scanner**, not a Java parser or official proof that an API was removed in your version.

Create `LegacyApiScanner.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class LegacyApiScanner {
    record Rule(String needle, String advice) {}

    static final List<Rule> RULES = List.of(
        new Rule("WebSecurityConfigurerAdapter",
            "use SecurityFilterChain bean (removed in 6)"),
        new Rule("authorizeRequests(",
            "check authorizeHttpRequests (removed in 7)"),
        new Rule("antMatchers(",
            "check requestMatchers (removed in 6)"),
        new Rule(".and()",
            "use Lambda DSL for 7"),
        new Rule("javax.servlet",
            "check jakarta.servlet for Boot 3+"),
        new Rule("EnableGlobalMethodSecurity",
            "check EnableMethodSecurity")
    );

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.out.println("Usage: java LegacyApiScanner <file>");
            return;
        }

        List<String> lines = Files.readAllLines(Path.of(args[0]));
        int matches = 0;

        for (int i = 0; i < lines.size(); i++) {
            String line = lines.get(i);
            for (Rule rule : RULES) {
                if (line.contains(rule.needle())) {
                    matches++;
                    System.out.println(
                        "line " + (i + 1) + ": " + rule.needle()
                            + " -> " + rule.advice()
                    );
                }
            }
        }

        System.out.println("Signals found: " + matches);
    }
}
```

Create a test file **`legacy-snippet.txt`** with contents:

```text
import javax.servlet.http.HttpServletRequest;
class Config extends WebSecurityConfigurerAdapter {
  void configure() {
    http.authorizeRequests().antMatchers("/admin").authenticated();
    http.httpBasic().and();
  }
}
```

Compile and run:

```bash
javac LegacyApiScanner.java
java LegacyApiScanner legacy-snippet.txt
```

**Exact stdout of the example:**

```text
line 1: javax.servlet -> check jakarta.servlet for Boot 3+
line 2: WebSecurityConfigurerAdapter -> use SecurityFilterChain bean (removed in 6)
line 4: authorizeRequests( -> check authorizeHttpRequests (removed in 7)
line 4: antMatchers( -> check requestMatchers (removed in 6)
line 5: .and() -> use Lambda DSL for 7
Signals found: 5
```

**Scanner limitations:** it reads text lines, so it may flag keywords inside comments, string literals, or examples illustrating "old code." It knows nothing about Gradle/Maven versions, parses no syntax, and verifies no endpoint safety. Use it to **list places worth reading carefully**, then check versioned APIs, build, test, and review policies. Never auto-replace all keywords across a repository.

If run against a nonexistent file, `Files.readAllLines` throws IOException; the program intentionally does not hide this error. On large projects, `rg` or IDE Find in Files can locate signals faster.

## 14. Concrete Debugging Scenarios

### 14.1. "Cannot resolve symbol WebSecurityConfigurerAdapter"

- Confirm the resolved `spring-security-config` version.
- On Spring Security 6+, the usual reason is that the adapter was removed.
- Migrate to a `SecurityFilterChain` bean and move earlier user/provider configs alongside it.
- Never add a Spring Security 5.x JAR into Boot 3 just to regain that class: it breaks compatibility and security.

### 14.2. "Cannot resolve method antMatchers"

- Check whether you are inside `authorizeRequests`/`authorizeHttpRequests` or `WebSecurityCustomizer`.
- In Security 6+, use the appropriate `requestMatchers`.
- Pick the right overload when matching HTTP methods; verify paths/servletPath and fallback.
- Write tests for anonymous callers and users with/without roles on every sensitive pattern.

### 14.3. "Cannot resolve method and()" After Upgrading to Security 7

- Open the DSL migration guide.
- Replace chained no-arg configs with lambdas and `Customizer.withDefaults()`.
- Check custom DSLs using `.apply(...)`; look into `.with(...)`.
- Never convert `csrf().disable()` blindly: whether to keep CSRF is a security decision.

### 14.4. IDE Reports Import javax.servlet Does Not Exist

- Verify whether Boot 3/Framework 6 uses `jakarta.servlet`.
- Confirm the appropriate web/Servlet dependencies are present.
- Do not change Java SE packages such as `javax.crypto`.
- Check whether any third-party library still drags in legacy javax causing conflicts.

### 14.5. Compiles Cleanly Yet Admin URL Becomes Public

- Check each chain's `securityMatcher`, `@Order`, and fallback.
- Inspect `requestMatchers` ordering: an overly broad `permitAll` rule may match before the admin rule.
- Check whether `web.ignoring` bypassed filters for that URL.
- Test with unauthenticated callers, non-admin users, and variant request paths.
- A "green build" does not prove policy equivalence.

### 14.6. @PreAuthorize Does Not Block Despite Updated Annotation

- Is `@EnableMethodSecurity` present in the right application context?
- Is the class/method Spring-managed and invoked through a proxy? Could self-invocation be happening?
- If the method uses parameter names in SpEL, was it compiled with `-parameters`?
- Is the method public / matching the invocation boundary of the active AOP mode?
- Test real calls through the bean and verify permissions rather than merely checking that the annotation exists.

### 14.7. Conflict Between Search Results and IDE

Suppose a blog post uses `http.antMatcher`, while your project's versioned Javadoc has only `securityMatcher`. **Prioritize the actual API of your resolved version**, followed by the reference/migration guide for that same version. If the website has a version selector at the top, select the right branch. For multi-layered dependencies, inspect the BOM before concluding docs are wrong.

## 15. Controlled API Upgrade Workflow

A sound migration splits into sequential technical steps:

1. **Snapshot the current state**: Boot, Security, JDK versions, Servlet/WebFlux, chain list, and policies.
2. **Inventory legacy signals**: adapter, `authorizeRequests`, matchers, no-arg DSLs, `.and()`, `apply`, method security annotations, `javax` imports.
3. **Open the exact migration step**: for 5.x -> 6.x read the guide to 6; for 6.5 -> 7.x read the guide to 7—never skip breaking-change notes.
4. **Lock in expected behavior**: capture tests for 200/401/403, redirects, CSRF, sessions, and object permissions before editing.
5. **Update dependencies cohesively**: use the Boot BOM/constraints instead of overriding individual modules arbitrarily.
6. **Migrate code by responsibility**: security chains, authentication providers/stores, request authorization, method security, protections, and exception handlers.
7. **Compile**: resolve import/method/annotation errors, test classpaths, and match Java/toolchain settings.
8. **Run security regression tests**: especially paths that were denied prior to migration.
9. **Verify runtime**: right chain selected, fallback present, no bypasses from changed matcher semantics.
10. **Document why changes were made**: old/new versions, preserved policies, intentional changes, and verifying tests.

Never optimize this into a project-wide find-and-replace script. When changing `antMatchers` to `requestMatchers` or altering chain selection, a single character can change the entire attack surface. Review security rules like critical business logic changes.

## 16. Checklist Before Trusting an Example on the Internet

When reading a Spring Security snippet from a blog, Stack Overflow, video, or sample repo, ask:

- Did the author state exact **Spring Boot, Spring Security, Java, and Servlet/WebFlux versions**?
- Does your real project share the same major/minor and BOM?
- Are legacy `WebSecurityConfigurerAdapter`, `antMatchers`, `authorizeRequests`, or `.and()` present?
- Does the example import `javax.servlet` while you are on Boot 3?
- Are all required main/config/controller/dependency pieces shown, or is it just a fragment?
- How are unlisted routes handled? Is there a fallback chain?
- Where does the `ROLE_ADMIN` matched by `hasRole("ADMIN")` come from?
- Does the example disable CSRF or use `web.ignoring` without explaining the risks?
- Does the login/token mechanism match your clients and credential management?
- Does the example include tests for anonymous, wrong password, missing permission, and CSRF?
- If custom providers/OAuth2 are used, are issuer, audience, signing keys, and scopes verified properly?
- Do official migration docs/Javadoc for your exact version confirm the methods used?

"The blog code compiles" is a good sign, yet **does not prove the config protects every access path properly**. Always test denial cases and side effects.

## 17. Self-Check

**Question 1.** An article uses `extends WebSecurityConfigurerAdapter`. A Spring Boot 3/Security 6 project reports class not found. What error is this, and how do you fix it?

**Question 2.** `antMatchers("/admin/**")` from an older article is rewritten to `requestMatchers("/admin/**")`. Why must you still test path matching?

**Question 3.** How does `HttpSecurity.securityMatcher` differ from `authorizeHttpRequests().requestMatchers`?

**Question 4.** Why can `authorizeRequests()` compile in a 6.x project yet fail in a 7.x project?

**Question 5.** A snippet uses `http.csrf().disable()`. Does changing it to `http.csrf(csrf -> csrf.disable())` make the app safer by itself?

**Question 6.** Why should you never add a Spring Security 5.x JAR into Boot 3 just to keep using the adapter?

**Question 7.** Why does a passing `@WithMockUser` test not prove HTTP Basic/login providers actually work?

**Question 8.** Is changing every `javax.*` package in an app to `jakarta.*` correct?

**Question 9.** If the build and happy-path tests pass, yet an anonymous request to `/admin` returns 200, is the migration complete?

**Question 10.** An old article uses `@EnableGlobalMethodSecurity`. When switching to `@EnableMethodSecurity`, what must you verify?

**Suggested answers:**

1. The adapter API was removed in Security 6; use a `SecurityFilterChain` bean and migrate related user/provider beans.
2. Matcher semantics can differ, especially for Servlet/MVC paths, methods, and sensitive patterns; test to confirm no endpoints were opened.
3. `securityMatcher` selects the whole chain; `requestMatchers` sets rules inside the selected chain.
4. `authorizeRequests` is a legacy API removed in 7; check Javadoc/actual version.
5. No. That only changes syntax while keeping CSRF disabled; evaluate the threat model.
6. It easily causes Framework/Jakarta/dependency conflicts, runtime failures, and defeats safe upgrades.
7. Mock users simulate a security context without exercising password providers or token verifiers.
8. No. Only relevant Jakarta EE packages migrate; `javax.crypto` and `javax.net.ssl` remain Java SE.
9. No. That is a critical authorization flaw requiring fixes and regression tests.
10. Verify method interception via Spring proxies, exact authorities, SpEL parameter resolution, and denial cases.

## 18. Official Versioned Documentation

- [Spring Security – Reference 6.5 / Java Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security – Reference 7.0 / Java Configuration](https://docs.spring.io/spring-security/reference/7.0/servlet/configuration/java.html)
- [Spring Security – Migrating to 6.0](https://docs.spring.io/spring-security/reference/6.5/migration/index.html)
- [Spring Security – Preparing for 7 / Configuration Migrations](https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html)
- [Spring Security – Migrating to 7.0](https://docs.spring.io/spring-security/reference/7.0/migration/)
- [Spring Security – What's New in 7.0](https://docs.spring.io/spring-security/reference/7.0/whats-new.html)
- [Spring Security – Authorization / Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring – Security without WebSecurityConfigurerAdapter](https://spring.io/blog/2022/02/21/spring-security-without-the-websecurityconfigureradapter)
- [Spring Boot – Managed Dependency Versions](https://docs.spring.io/spring-boot/appendix/dependency-versions/index.html)
