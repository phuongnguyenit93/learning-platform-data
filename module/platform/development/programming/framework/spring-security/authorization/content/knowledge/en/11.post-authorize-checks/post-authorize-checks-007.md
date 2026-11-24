# `@AuthorizeReturnObject` and Version-Aware Protection of Object Members

> **Topic:** Spring Security — Post-method checks and protecting returned objects. This lesson explains what `@AuthorizeReturnObject` does, how it **proxies the return value** to enforce `@PreAuthorize`/`@PostAuthorize` on **getters or methods of the object**, how to handle nested objects, `Optional`, `List`, serialization, AOT/native images, and differences across Spring Security versions. Examples use **Java 17+, Spring Boot 3.5.x, and Spring Security 6.5.x**, following the Servlet/Spring MVC model.

## 1. The problem: allowing name access while denying email and phone number

An endpoint or service can return an object containing multiple members:

~~~text
ProfileView
  ├── name:  "Lan"               (basic info)
  ├── email: "lan@example.test"  (requires profile:email)
  └── contact: ContactView
         ├── city:  "HCM"        (basic info)
         └── phone: "0900000000" (requires profile:phone)
~~~

A user with `profile:read` is allowed to **receive the profile object**, yet does not automatically have permission to read **every getter**. A user having only `profile:email` (without `profile:phone`) may view the email, but must not view the phone number.

One approach is creating separate permission-specific DTOs/endpoints. Spring Security also supports another approach: returning a **security-proxied object** to check whenever the application invokes a sensitive getter.

Distinguish two questions:

1. **May the `ProfileView` object be returned?** A `@PreAuthorize` on the service method can check `profile:read` before creating/returning the profile.
2. **May `ProfileView.getEmail()` be called?** `@PreAuthorize` placed on the getter decides this when the getter is called **through a proxy**.

`@AuthorizeReturnObject` bridges the two layers: it marks a method **returning an object that needs proxy wrapping**, so security annotations on **methods of the returned object** continue to be enforced.

**Core point:** merely placing `@PreAuthorize` on a getter of a manually constructed POJO does not mean that getter is protected by Spring AOP. An appropriate proxy/interception mechanism must be in place.

## 2. How does `@AuthorizeReturnObject` work?

Full annotation:

~~~java
import org.springframework.security.authorization.method.AuthorizeReturnObject;
~~~

A Spring service can be written as:

~~~java
@Service
class ProfileService {

    @AuthorizeReturnObject
    public ProfileView findById(String id) {
        return repository.loadProfile(id);
    }
}
~~~

This is a **fragment**, requiring a real service/repository/model. `@AuthorizeReturnObject` is placed on **the method returning** the object, not necessarily on the object's class. When the service is called through a Spring-managed proxy, the interceptor uses `AuthorizationProxyFactory` to wrap the result object.

Result class:

~~~java
public class ProfileView {
    private final String name;
    private final String email;

    public ProfileView(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public String getName() {
        return name;
    }

    @PreAuthorize("hasAuthority('profile:email')")
    public String getEmail() {
        return email;
    }
}
~~~

This is an **illustrative class**; to use it, import `PreAuthorize` and return an instance of it from a method annotated with `@AuthorizeReturnObject`. Methods are public and non-`final`, and the class is non-`final` so subclass proxying can work.

When the caller receives the result of `service.findById(...)`:

- Calling `view.getName()`: no guard on the getter, so it executes (having passed prior barriers).
- Calling `view.getEmail()`: the proxy sees `@PreAuthorize("hasAuthority('profile:email')")` and requires that authority.
- User missing `profile:email`: denied at **the getter call**, typically throwing `AccessDeniedException` / `AuthorizationDeniedException`.
- User with the authority: the getter returns the email value.

**The object's fields are not mutated:** the `email` data still lives inside the target; the proxy checks **calls to members**. Do not treat this as encryption, database field-level filtering, or automatic hiding of all reflective paths to the data.

## 3. Distinguishing three easily confused mechanisms

| Mechanism | Where applied | Timing of check | Decision scope |
| --- | --- | --- | --- |
| `@PreAuthorize` | Service method or any proxied getter/method | **Before** target method runs | Allows/denies **a single call** |
| `@PostAuthorize` | Method returning a result | **After** target runs | Allows/denies **returning the whole result** based on SpEL, e.g., `returnObject.owner` |
| `@AuthorizeReturnObject` | Method/class returning an object | After source method returns object, when wrapping result | **Creates a proxy**, so methods/getters on the result object are guarded when called |

Examples of two design styles:

### 3.1. Blocking the whole object with `@PostAuthorize`

~~~java
@PostAuthorize("returnObject.owner == authentication.name")
public ProfileView readProfile(String id) {
    return repository.loadProfile(id);
}
~~~

If the owner is invalid, the caller **never receives the object**. This is a post-check of the entire return value. It does not separate `getEmail` and `getPhone` permissions.

### 3.2. Allowing the object, guarding individual members

~~~java
@PreAuthorize("hasAuthority('profile:read')")
@AuthorizeReturnObject
public ProfileView readProfile(String id) {
    return repository.loadProfile(id);
}
~~~

With `ProfileView.getEmail()` annotated `@PreAuthorize("hasAuthority('profile:email')")`, the user can still read name, while the email call is denied if permission is missing. Thus:

- `@PreAuthorize` on the service guards **the entry point**.
- `@AuthorizeReturnObject` produces **the proxy**.
- `@PreAuthorize` on the getter guards **each member**.
- If the getter used `@PostAuthorize` instead, the getter could **already have run** before being denied. That is why choosing pre vs. post on getters must be deliberate.

**Do not treat `@AuthorizeReturnObject` as an ALLOW/DENY expression**; this annotation does not take a SpEL string like `@PreAuthorize("...")`.

## 4. Call flow across two proxy layers

~~~text
HTTP GET /api/profiles/P-1/email
    |
    v
SecurityFilterChain: requires authentication
    |
    v
Controller calls Spring-managed ProfileService
    |
    v
Service proxy:
    @PreAuthorize(profile:read) ----DENY----> 403
    |
    v ALLOW
Target service creates ProfileView
    |
    v
@AuthorizeReturnObject:
    AuthorizationProxyFactory wraps ProfileView
    |
    v
Controller receives proxied ProfileView
    |
    v
Controller calls view.getEmail()
    |
    v
ProfileView proxy:
    @PreAuthorize(profile:email) ---DENY---> 403
    |
    v ALLOW
Target ProfileView.getEmail() -> "lan@example.test"
    |
    v
Controller returns String to client
~~~

Most important point: **member protection on the returned object runs when the caller uses the object**, not necessarily when the service method creates the object. If nobody ever calls `getEmail()`, the authority check for that getter may not have executed yet.

Having `ProfileService.find...` return an object created via `new` is not an issue as long as **the service itself** is Spring-proxied and `@AuthorizeReturnObject` wraps the result. However, if you call `new ProfileService().find...` or self-invoke via `this.find...` bypassing the service proxy, the wrapping step can be skipped.

Furthermore, the caller must use **the proxied instance returned**, not a raw object reference stored elsewhere, and then assume getters are always guarded.

## 5. Version compatibility: don't use newer APIs prematurely

This detail is mandatory because `@AuthorizeReturnObject` **does not exist in every Spring Security generation**.

| Version range | Key facts |
| --- | --- |
| Spring Security **6.2 and earlier** | Cannot assume `@AuthorizeReturnObject` is available; choose service/DTO/`@PostAuthorize` protection or a verified upgrade |
| Spring Security **6.3** | Javadoc notes `@AuthorizeReturnObject` **Since: 6.3**; supports wrapping return objects with method security advice |
| Spring Security **6.4** | AOT hint APIs like `AuthorizeReturnObjectHintsRegistrar` have Javadoc `Since: 6.4`; watch native images when types are erased |
| Spring Security **6.5** | Official docs describe object proxying, `Optional`/collection/map values, nested `@AuthorizeReturnObject`, `TargetVisitor`, `AuthorizationProxyFactory`, AOT; improved Spring MVC integration is also noted in 6.5 release notes |
| Spring Security **7.x and later** | API names may persist, yet config/AOT/serialization may evolve; verify reference docs and Javadoc for the **exact running version**, never treating 6.5 samples as permanent guarantees |

**Important note:** Spring Boot manages Spring Security versions via dependency management. “The app uses Java 17” **does not** mean Spring Security 6.5 is present. Verify actual dependencies with Maven/Gradle instead of guessing from imports or blog posts.

Verification examples:

~~~bash
# In a Maven project, inspect the actually resolved artifact:
./mvnw dependency:tree -Dincludes=org.springframework.security

# With Gradle:
./gradlew dependencyInsight --dependency spring-security-config \
    --configuration runtimeClasspath
~~~

On Windows use `mvnw.cmd`/`gradlew.bat`. Build tool flags/configurations must fit the project. If using Boot 3.x with Spring Security older than 6.3, importing `AuthorizeReturnObject` **will not compile**—that is a dependency/version issue, not a runtime permission problem.

## 6. Conditions for proxies to be created properly

### 6.1. The source bean must pass through Spring AOP

`@EnableMethodSecurity` must be enabled; the method returning the object belongs to a Spring-managed bean and the call must traverse the proxy. Self-invocation (`this.findById(...)`) inside the same service can bypass the `@AuthorizeReturnObject` interceptor.

### 6.2. The returned object must be suitable for proxying

A plain POJO class with public **non-final** getters/methods is an easy-to-control choice. Some types have restrictions:

- A Java `record` is `final`; do not assume a class-based proxy can be created for a record like a regular POJO.
- `String`, `Integer`, `Double`, and many value types are unsuitable for subclass proxying.
- `private` or `final` methods, or objects already wrapped by another proxy strategy, may not receive advice as expected.
- Kotlin classes are final by default without `open`/compiler plugins; test against your actual Kotlin configuration.
- Objects from Hibernate/JPA or third-party proxies can interact subtly with Spring Security proxies; do not rely solely on annotations on entities.

**Learning rule:** use non-final Java classes, public getters, and never expose security-critical values in public fields. Test proxies at runtime.

### 6.3. Do not apply class-level annotations indiscriminately

By API, `@AuthorizeReturnObject` can be placed at class level, meaning it applies to every method in that class. However, when the class has methods returning `String`, `int`, `Integer`, or numeric/value types, Spring Security may attempt to **proxy return types that should not be proxied**.

~~~java
// Warning: class-level causes all methods to be covered.
@AuthorizeReturnObject
@Service
class MixedService {
    public ProfileView find() { return new ProfileView(); }
    public String health() { return "ok"; }
}
~~~

This is an **anti-pattern**. In a concrete app, `new ProfileView()` needs an appropriate constructor; the point is purely to show class-level scope. Do not copy this class as runnable code.

A clearer approach is **placing `@AuthorizeReturnObject` on each specific method returning an object that needs wrapping**. If there is a reason to use class-level, Spring Security 6.5 suggests `TargetVisitor` to skip value types:

~~~java
// Spring configuration fragment, requires import:
// org.springframework.security.authorization.method
//     .AuthorizationAdvisorProxyFactory.TargetVisitor

@Bean
static TargetVisitor skipSimpleValues() {
    return TargetVisitor.defaultsSkipValueTypes();
}
~~~

This is a customization for specific scenarios and is unnecessary in the complete example below because we **do not** use a class-level annotation.

## 7. Protecting nested members with additional `@AuthorizeReturnObject`

A `ProfileView` may contain a `ContactView`. Proxying `ProfileView` **does not mean every inner object is proxied to infinite depth**. To also protect getters of `ContactView`, annotate the method returning `ContactView`:

~~~java
public class ProfileView {
    private final ContactView contact;

    public ProfileView(ContactView contact) {
        this.contact = contact;
    }

    @AuthorizeReturnObject
    public ContactView getContact() {
        return contact;
    }
}

public class ContactView {
    private final String city;
    private final String phone;

    public ContactView(String city, String phone) {
        this.city = city;
        this.phone = phone;
    }

    public String getCity() {
        return city;
    }

    @PreAuthorize("hasAuthority('profile:phone')")
    public String getPhone() {
        return phone;
    }
}
~~~

Both classes are **fragments** shown to illustrate the mechanism and require the corresponding Spring Security annotation imports. Once `ProfileView` is a proxy, calling `view.getContact()` triggers the `@AuthorizeReturnObject` interceptor to wrap `ContactView` as well. A caller subsequently invoking `contact.getPhone()` must hold `profile:phone`.

**Clearly distinguish the paths:**

- `view.getName()`: info without a permission annotation on the getter.
- `view.getEmail()`: requires `profile:email` if the getter is annotated.
- `view.getContact().getCity()`: obtaining `ContactView` may not require `profile:phone`, and `getCity()` has no guard.
- `view.getContact().getPhone()`: requires `profile:phone`.

If `@AuthorizeReturnObject` is omitted from `getContact()`, you may receive a **raw ContactView**, and `@PreAuthorize` on `getPhone()` of the raw POJO will not be applied as expected. **Negative** tests for nested getters are mandatory.

## 8. `Optional`, `List`, `Map`, and other objects

Spring Security 6.5 documents that `AuthorizationProxyFactory` can proxy:

- Single objects such as `ProfileView`.
- `Optional<ProfileView>`: the inner value can be proxy-wrapped.
- `List<ProfileView>`/`Collection`: element objects are proxied.
- Arrays, streams, iterators: traversal mechanisms supported per docs.
- `Map<K, ProfileView>`: **map values** are proxied when the factory processes maps.

Example:

~~~java
@Service
class ProfileService {

    @AuthorizeReturnObject
    public Optional<ProfileView> findOptional(String id) {
        return repository.findOptional(id);
    }

    @AuthorizeReturnObject
    public List<ProfileView> findAll() {
        return repository.findAll();
    }
}
~~~

This is a **fragment**; it needs a repository/model. With `Optional.empty()`, there is no inner object to call getters on. With `List`, obtaining the list does not necessarily call `getEmail()` on every element; getter authorization happens when an element is accessed through the proxy.

**Do not confuse “collection proxying” with “data filtering”.** If a list has ten profiles, `@PreAuthorize` on `getEmail` only checks when the caller reads each profile's email; it does not pre-remove profiles belonging to other tenants. To filter lists by owner/tenant, prefer database queries with permission predicates or `@PostFilter` where appropriate.

### Avoid assuming Map keys are also protected

For `Map<String, ProfileView>`, documentation highlights that the factory proxies map **values**, not an automatic key-protection policy. If map keys contain sensitive info, proxying values alone is insufficient. Constrain/design returned data at the service layer.

### When using generics and AOT

On a regular JVM, a `List<ProfileView>` is traversed/proxied by runtime types. However, Spring AOT/native images need to know in advance which classes require proxies. Due to **type erasure**, AOT processing may not infer every element type solely from the method return type. Section 15 explains how to register explicit hints.

## 9. Plain Java 17: simulating getter protection before using Spring

This model uses **delegation** to demonstrate “returning a view while blocking sensitive getters”. It **does not implement Spring AOP** and does not prove `@AuthorizeReturnObject` runs in the real framework.

Create **`MemberAccessDemo.java`**:

~~~java
import java.util.Set;
import java.util.function.Supplier;

public class MemberAccessDemo {

    record RawProfile(String name, String email, String phone) {}

    static final class SecuredProfile {
        private final RawProfile profile;
        private final Set<String> authorities;

        SecuredProfile(RawProfile profile, Set<String> authorities) {
            this.profile = profile;
            this.authorities = authorities;
        }

        private void require(String authority) {
            if (!authorities.contains(authority)) {
                throw new SecurityException("Missing " + authority);
            }
        }

        String getName() {
            require("profile:read");
            return profile.name();
        }

        String getEmail() {
            require("profile:email");
            return profile.email();
        }

        String getPhone() {
            require("profile:phone");
            return profile.phone();
        }
    }

    static String attempt(Supplier<String> operation) {
        try {
            return operation.get();
        } catch (SecurityException exception) {
            return "DENY";
        }
    }

    public static void main(String[] args) {
        RawProfile raw = new RawProfile(
            "Lan", "lan@example.test", "0900000000"
        );

        SecuredProfile reader = new SecuredProfile(
            raw, Set.of("profile:read")
        );
        SecuredProfile emailer = new SecuredProfile(
            raw, Set.of("profile:read", "profile:email")
        );
        SecuredProfile phoneUser = new SecuredProfile(
            raw, Set.of("profile:read", "profile:phone")
        );
        SecuredProfile outsider = new SecuredProfile(
            raw, Set.of()
        );

        System.out.println("reader.name=" + attempt(reader::getName));
        System.out.println("reader.email=" + attempt(reader::getEmail));
        System.out.println("reader.phone=" + attempt(reader::getPhone));
        System.out.println("emailer.email=" + attempt(emailer::getEmail));
        System.out.println("phoneUser.phone=" + attempt(phoneUser::getPhone));
        System.out.println("outsider.name=" + attempt(outsider::getName));
    }
}
~~~

Run:

~~~bash
javac MemberAccessDemo.java
java MemberAccessDemo
~~~

**Exact stdout:**

~~~text
reader.name=Lan
reader.email=DENY
reader.phone=DENY
emailer.email=lan@example.test
phoneUser.phone=0900000000
outsider.name=DENY
~~~

Here `RawProfile` is a **final record** because it is pure data for a plain Java program; `SecuredProfile` works via **manual delegation**, not a Spring proxy. In the Spring application below, `ProfileView`/`ContactView` are **non-final public classes** to work with method-authorization proxies.

## 10. Spring Boot 3.5 / Spring Security 6.5: runnable application

### 10.1. Authorization scenario

The application provides a profile `P-1`:

| Field | Value | Required permission |
| --- | --- | --- |
| `name` | `Lan` | `profile:read` on service, no separate guard on getter |
| `email` | `lan@example.test` | `profile:read` + `profile:email` |
| `contact.city` | `HCM` | `profile:read` |
| `contact.phone` | `0900000000` | `profile:read` + `profile:phone` |

Accounts:

| User | Authorities |
| --- | --- |
| `reader` | `profile:read` |
| `emailer` | `profile:read`, `profile:email` |
| `phoneuser` | `profile:read`, `profile:phone` |
| `superreader` | `profile:read`, `profile:email`, `profile:phone` |
| `outsider` | `ROLE_USER` |

The goal is not to invent an implied “highest role sees everything”. Every permission is an explicitly granted literal authority. All HTTP endpoints use GET to focus on method security rather than mixing with write-method CSRF.

### 10.2. Dependencies

Create a Maven Spring Boot **3.5.x** project, Java 17+, with:

- `spring-boot-starter-web`.
- `spring-boot-starter-security`.
- `spring-boot-starter-test` in test scope.
- `spring-security-test` in test scope.

Using Spring Initializr and the Boot BOM/parent keeps versions consistent. **Verify** that the `spring-security-config` dependency is actually **6.5.x** before using the APIs in this lesson.

### 10.3. Complete single-file application

Create **`src/main/java/com/example/returned/ReturnObjectApplication.java`**:

~~~java
package com.example.returned;

import java.util.List;
import java.util.Optional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authorization.method.AuthorizeReturnObject;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class ReturnObjectApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReturnObjectApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/api/profiles/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader123"))
            .authorities("profile:read")
            .build();

        UserDetails emailer = User.withUsername("emailer")
            .password(encoder.encode("emailer123"))
            .authorities("profile:read", "profile:email")
            .build();

        UserDetails phoneuser = User.withUsername("phoneuser")
            .password(encoder.encode("phone123"))
            .authorities("profile:read", "profile:phone")
            .build();

        UserDetails superreader = User.withUsername("superreader")
            .password(encoder.encode("super123"))
            .authorities(
                "profile:read", "profile:email", "profile:phone"
            )
            .build();

        UserDetails outsider = User.withUsername("outsider")
            .password(encoder.encode("outsider123"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(
            reader, emailer, phoneuser, superreader, outsider
        );
    }

    // Proxied object: NOT final and getters NOT final.
    public static class ProfileView {
        private final String id;
        private final String name;
        private final String email;
        private final ContactView contact;

        public ProfileView(String id, String name,
                           String email, ContactView contact) {
            this.id = id;
            this.name = name;
            this.email = email;
            this.contact = contact;
        }

        public String getId() {
            return id;
        }

        public String getName() {
            return name;
        }

        @PreAuthorize("hasAuthority('profile:email')")
        public String getEmail() {
            return email;
        }

        // Delegate to proxy for nested object.
        @AuthorizeReturnObject
        public ContactView getContact() {
            return contact;
        }
    }

    public static class ContactView {
        private final String city;
        private final String phone;

        public ContactView(String city, String phone) {
            this.city = city;
            this.phone = phone;
        }

        public String getCity() {
            return city;
        }

        @PreAuthorize("hasAuthority('profile:phone')")
        public String getPhone() {
            return phone;
        }
    }

    @Service
    public static class ProfileService {

        private ProfileView sample() {
            return new ProfileView(
                "P-1",
                "Lan",
                "lan@example.test",
                new ContactView("HCM", "0900000000")
            );
        }

        @PreAuthorize("hasAuthority('profile:read')")
        @AuthorizeReturnObject
        public ProfileView find(String id) {
            if (!"P-1".equals(id)) {
                throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Profile not found"
                );
            }
            return sample();
        }

        @PreAuthorize("hasAuthority('profile:read')")
        @AuthorizeReturnObject
        public Optional<ProfileView> findOptional(String id) {
            return "P-1".equals(id)
                ? Optional.of(sample())
                : Optional.empty();
        }

        @PreAuthorize("hasAuthority('profile:read')")
        @AuthorizeReturnObject
        public List<ProfileView> findAll() {
            return List.of(sample());
        }
    }

    @RestController
    static class Api {
        private final ProfileService service;

        Api(ProfileService service) {
            this.service = service;
        }

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/api/profiles/{id}/name")
        String name(@PathVariable("id") String id) {
            return service.find(id).getName();
        }

        @GetMapping("/api/profiles/{id}/email")
        String email(@PathVariable("id") String id) {
            return service.find(id).getEmail();
        }

        @GetMapping("/api/profiles/{id}/contact/city")
        String city(@PathVariable("id") String id) {
            return service.find(id).getContact().getCity();
        }

        @GetMapping("/api/profiles/{id}/contact/phone")
        String phone(@PathVariable("id") String id) {
            return service.find(id).getContact().getPhone();
        }

        // Optional with element: inner value must be proxied.
        @GetMapping("/api/profiles/optional/{id}/email")
        String optionalEmail(@PathVariable("id") String id) {
            return service.findOptional(id)
                .map(ProfileView::getEmail)
                .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Profile not found"
                ));
        }

        // List elements: getters of each element must be protected.
        @GetMapping("/api/profiles/all/emails")
        List<String> allEmails() {
            return service.findAll().stream()
                .map(ProfileView::getEmail)
                .toList();
        }

        @GetMapping("/api/unknown")
        String unknown() {
            return "must not be reached";
        }
    }
}
~~~

### 10.4. Why does the example have controllers return String instead of returning raw `ProfileView`?

An object whose `getEmail()` has `@PreAuthorize` is checked when a framework **calls the getter**. If the controller returns the whole `ProfileView` for Jackson to serialize automatically, Jackson may call **all getters**, including sensitive ones. When a getter is denied, the entire request may receive **403** instead of automatically producing JSON “without the email field”.

Hence the demo application picks individual endpoints and **explicitly calls the getters**:

- `/name`: calls normal getter.
- `/email`: calls getter guarded by `profile:email`.
- `/contact/city`: nested object is proxied; city is viewable.
- `/contact/phone`: nested getter guarded by `profile:phone`.

This produces a clear 200/403 matrix. **Do not mistake `@AuthorizeReturnObject` for default JSON masking**. If you need to return a JSON object with the email field hidden, use **permission-based DTO projections** or `@HandleAuthorizationDenied` with a properly designed/tested masking policy.

### 10.5. Why aren't `ProfileView` and `ContactView` records?

A Java `record` is `final`, whereas class-based proxying needs the ability to intercept methods. Because this lesson specifically tests with AOP proxies, it uses public, non-final classes with public, non-final getters. Using immutable records or Kotlin data classes in a real system requires a different proxy design or mapping to DTOs before exposing; do not treat a record as a “framework bug” if it cannot be proxied this way.

## 11. Result matrix to verify

### 11.1. HTTP endpoints

| User | GET name | GET email | GET city | GET phone |
| --- | :---: | :---: | :---: | :---: |
| Anonymous | 401 | 401 | 401 | 401 |
| Reader — only `profile:read` | **200** | 403 | **200** | 403 |
| Emailer — read + email | **200** | **200** | **200** | 403 |
| Phoneuser — read + phone | **200** | 403 | **200** | **200** |
| Superreader — all three | **200** | **200** | **200** | **200** |
| Outsider — only `ROLE_USER` | 403 | 403 | 403 | 403 |

All requests use `P-1` in the path and are sent with HTTP Basic as in the sample app. For accounts with `profile:read`, `GET /api/profiles/X/name` must return 404 since `X` does not exist. For outsider lacking `profile:read`, it can return 403 before lookup. Define your 403/404 policy clearly when you want to avoid disclosing object existence.

### 11.2. Optional and List

| Endpoint | Reader | Emailer | Phoneuser | Superreader |
| --- | :---: | :---: | :---: | :---: |
| `GET /api/profiles/optional/P-1/email` | 403 | 200 | 403 | 200 |
| `GET /api/profiles/optional/X/email` | 404 | 404 | 404 | 404 |
| `GET /api/profiles/all/emails` | 403 | 200 | 403 | 200 |

`Optional.empty()` has no member to check. `List<ProfileView>` contains already-proxied elements: calling `getEmail` on each element must pass through the guard. This is **not** `@PostFilter` and does not automatically filter an element out of the list if email is denied.

### 11.3. Bodies of ALLOW endpoints

| Request | Expected body |
| --- | --- |
| Public ping | `pong` |
| Reader GET name | `Lan` |
| Reader GET city | `HCM` |
| Emailer GET email | `lan@example.test` |
| Phoneuser GET phone | `0900000000` |
| Superreader GET all/emails | JSON list `["lan@example.test"]` |

**403 means a guard disallowed executing the call**, not that the object does not exist. With form login or custom exception handling, status and body may differ from the demo.

## 12. Manual testing with curl

From the Maven project root:

~~~bash
# Linux / macOS:
./mvnw spring-boot:run

# Windows:
mvnw.cmd spring-boot:run
~~~

When the app is listening on `http://localhost:8080`:

~~~bash
# Public and anonymous:
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/profiles/P-1/name

# Reader can view name/city, cannot view email/phone:
curl -i -u reader:reader123 http://localhost:8080/api/profiles/P-1/name
curl -i -u reader:reader123 http://localhost:8080/api/profiles/P-1/contact/city
curl -i -u reader:reader123 http://localhost:8080/api/profiles/P-1/email
curl -i -u reader:reader123 http://localhost:8080/api/profiles/P-1/contact/phone

# Emailer can view email but not phone:
curl -i -u emailer:emailer123 http://localhost:8080/api/profiles/P-1/email
curl -i -u emailer:emailer123 http://localhost:8080/api/profiles/P-1/contact/phone

# Phoneuser can view phone but not email:
curl -i -u phoneuser:phone123 http://localhost:8080/api/profiles/P-1/contact/phone
curl -i -u phoneuser:phone123 http://localhost:8080/api/profiles/P-1/email

# Optional, list, not-found:
curl -i -u emailer:emailer123 http://localhost:8080/api/profiles/optional/P-1/email
curl -i -u reader:reader123 http://localhost:8080/api/profiles/all/emails
curl -i -u reader:reader123 http://localhost:8080/api/profiles/X/name

# HTTP default deny:
curl -i -u superreader:super123 http://localhost:8080/api/unknown
~~~

In production, never use sample passwords. HTTP Basic requires HTTPS; authorities from the demo `UserDetailsService` are purely for learning, while real systems must use a proper identity provider and authorization policy.

## 13. Testing with Spring Security Test and MockMvc

### 13.1. Test dependencies

In `pom.xml`, ensure you have (without adding duplicates):

~~~xml
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
~~~

This is an XML fragment inside `<dependencies>` of the POM. Spring Boot dependency management keeps versions consistent.

### 13.2. Complete test class

Create **`src/test/java/com/example/returned/ReturnObjectApplicationTests.java`**:

~~~java
package com.example.returned;

import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReturnObjectApplicationTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    ReturnObjectApplication.ProfileService service;

    @ParameterizedTest
    @CsvSource({
        // username,password,path,expected HTTP status
        "anonymous,none,/public/ping,200",
        "anonymous,none,/api/profiles/P-1/name,401",
        "reader,reader123,/api/profiles/P-1/name,200",
        "reader,reader123,/api/profiles/P-1/email,403",
        "reader,reader123,/api/profiles/P-1/contact/city,200",
        "reader,reader123,/api/profiles/P-1/contact/phone,403",
        "reader,reader123,/api/profiles/X/name,404",
        "reader,reader123,/api/profiles/optional/P-1/email,403",
        "reader,reader123,/api/profiles/optional/X/email,404",
        "reader,reader123,/api/profiles/all/emails,403",

        "emailer,emailer123,/api/profiles/P-1/name,200",
        "emailer,emailer123,/api/profiles/P-1/email,200",
        "emailer,emailer123,/api/profiles/P-1/contact/phone,403",
        "emailer,emailer123,/api/profiles/optional/P-1/email,200",
        "emailer,emailer123,/api/profiles/all/emails,200",

        "phoneuser,phone123,/api/profiles/P-1/email,403",
        "phoneuser,phone123,/api/profiles/P-1/contact/phone,200",
        "phoneuser,phone123,/api/profiles/all/emails,403",

        "superreader,super123,/api/profiles/P-1/email,200",
        "superreader,super123,/api/profiles/P-1/contact/phone,200",
        "superreader,super123,/api/profiles/all/emails,200",
        "superreader,super123,/api/unknown,403",

        "outsider,outsider123,/api/profiles/P-1/name,403",
        "outsider,outsider123,/api/profiles/P-1/email,403"
    })
    void httpAuthorizationMatrix(
            String username, String password,
            String path, int expectedStatus
    ) throws Exception {
        MockHttpServletRequestBuilder request = get(path);
        if (!"anonymous".equals(username)) {
            request.with(httpBasic(username, password));
        }
        mvc.perform(request).andExpect(status().is(expectedStatus));
    }

    @Test
    void returnedNameIsAllowedButEmailIsDenied() throws Exception {
        mvc.perform(get("/api/profiles/P-1/name")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isOk())
            .andExpect(content().string("Lan"));

        mvc.perform(get("/api/profiles/P-1/email")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void emailAndPhoneAreIndependent() throws Exception {
        mvc.perform(get("/api/profiles/P-1/email")
                .with(httpBasic("emailer", "emailer123")))
            .andExpect(status().isOk())
            .andExpect(content().string("lan@example.test"));

        mvc.perform(get("/api/profiles/P-1/contact/phone")
                .with(httpBasic("emailer", "emailer123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/profiles/P-1/contact/phone")
                .with(httpBasic("phoneuser", "phone123")))
            .andExpect(status().isOk())
            .andExpect(content().string("0900000000"));
    }

    @Test
    void listContainsSecuredElements() throws Exception {
        mvc.perform(get("/api/profiles/all/emails")
                .with(httpBasic("superreader", "super123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0]").value("lan@example.test"));

        mvc.perform(get("/api/profiles/all/emails")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "profile:read")
    void directServiceProxyProtectsMembers() {
        ReturnObjectApplication.ProfileView view = service.find("P-1");
        assertEquals("Lan", view.getName());
        assertThrows(AccessDeniedException.class, view::getEmail);

        ReturnObjectApplication.ContactView contact = view.getContact();
        assertEquals("HCM", contact.getCity());
        assertThrows(AccessDeniedException.class, contact::getPhone);
    }

    @Test
    @WithMockUser(authorities = {"profile:read", "profile:email"})
    void optionalAndListProxyTheirElements() {
        Optional<ReturnObjectApplication.ProfileView> optional =
            service.findOptional("P-1");

        assertTrue(optional.isPresent());
        assertEquals("lan@example.test", optional.orElseThrow().getEmail());

        List<ReturnObjectApplication.ProfileView> views =
            service.findAll();
        assertEquals(1, views.size());
        assertEquals("lan@example.test", views.get(0).getEmail());
        assertThrows(
            AccessDeniedException.class,
            () -> views.get(0).getContact().getPhone()
        );
        assertFalse(service.findOptional("X").isPresent());
    }

    @Test
    @WithMockUser(authorities = "profile:email")
    void cannotReceiveViewWithoutBaseReadPermission() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.find("P-1")
        );
    }

    @Test
    void badPasswordIsAuthenticationFailure() throws Exception {
        mvc.perform(get("/api/profiles/P-1/name")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

### 13.3. Meaning of the test cases

- **HTTP matrix:** tests not only that superreader gets 200, but also that reader gets 403 on email/phone and outsider is blocked right at the service.
- **Direct Spring bean test:** verifies **the actual proxy object** from `service.find(...)`. The returned object allows reading name while denying `getEmail`.
- **Nested test:** `getContact()` must return a proxied ContactView; if `@AuthorizeReturnObject` is removed from the nested getter, the unauthorized `contact.getPhone()` test risks failing.
- **Optional/List test:** proves elements are protected, not just single objects. `Optional.empty` does not trigger getter calls.
- **Base permission test:** if a user has only `profile:email` without `profile:read`, the service `@PreAuthorize` denies before creating/returning ProfileView.
- **Authentication test:** wrong password yields 401 with HTTP Basic; do not confuse with getter 403.

**Do not use `new ProfileService()` to write security tests**, because manually instantiated objects do not pass through the Spring AOP proxy. `@WithMockUser` in tests is provided by `spring-security-test` and mocks Authentication to test rules directly; `httpBasic` goes through the demo `UserDetailsService`.

### 13.4. Running tests

~~~bash
# Linux/macOS:
./mvnw test

# Windows:
mvnw.cmd test
~~~

The statuses/outputs above are **designed expectations**, not a claim that the test suite was executed here. When upgrading Spring Security or changing proxy settings, run against your application's exact artifact/dependency versions to verify results.

## 14. Jackson/REST serialization: the most commonly misunderstood issue

An API might want to return:

~~~json
{
  "name": "Lan",
  "email": null,
  "contact": {
    "city": "HCM",
    "phone": null
  }
}
~~~

Yet **`@AuthorizeReturnObject` does not automatically guarantee producing that JSON**. Jackson calls getters on the proxy; a getter lacking permission throws `AccessDeniedException` by default. Depending on where it fails, the whole response may be denied or affected by exception mappers/serialization buffering. Never promise “unauthorized fields will automatically disappear”.

There are three implementation approaches:

1. **Choose a permission-specific DTO from the service/controller:** include only allowed fields in the DTO, avoiding forbidden getters altogether. Useful when the API has a strict contract and needs consistent pagination and field masking.
2. **Use `@HandleAuthorizationDenied` with a fallback/masking policy:** in Spring Security 6.5, you can provide a `MethodAuthorizationDeniedHandler` to return null or a masked string when permission is missing. The handler must be implemented and registered properly; it is not automatic merely from using `@AuthorizeReturnObject`.
3. **Return 403 for the whole request:** appropriate when missing permission on any required field means the entire response must not be emitted.

### `@HandleAuthorizationDenied` is not “granting access”

Model example:

~~~java
// Fragment: annotation for a getter. Class MaskingHandler must
// implement an appropriate MethodAuthorizationDeniedHandler and be a Spring bean.
@PreAuthorize("hasAuthority('profile:email')")
@HandleAuthorizationDenied(handlerClass = MaskingHandler.class)
public String getEmail() {
    return email;
}
~~~

This is a **fragment**; `MaskingHandler` is not a built-in Spring class. The handler can return `null` or a masked value per the `MethodAuthorizationDeniedHandler` contract. A buggy handler can **leak denied data**, especially if it is allowed to inspect the original value. Never copy a fragment without a trustworthy handler; test with authorized and unauthorized users and inspect the actual JSON.

If you want to omit the field key altogether when null, Spring Boot offers Jackson non-null inclusion options; also verify actual serialization and the API contract.

### Field security does not stop at Jackson

Even when a getter proxy denies, sensitive data may still exist in the **raw target**, caches, logs, events, or direct field access by a serializer bypassing getters. Do not rely solely on getter interception to protect every access path to a raw JPA entity. DTO minimization, scoped queries, and server-side policies remain essential.

## 15. AOT/native image: why versions and generic types matter?

Spring AOT/native images usually need proxy/reflection hints registered at build time. Spring Security 6.5 can scan Spring beans and methods annotated with `@AuthorizeReturnObject`, then recurse into return types and nested `@AuthorizeReturnObject` annotations to register proxy classes and expression-related hints.

However, when a method has return type `List<ProfileView>` or a generic interface, Spring cannot always infer the full **runtime element type** before native compilation. In those cases, explicit hints must be provided.

### 15.1. Registering additional types for AOT

**Spring Security 6.5 configuration fragment** example:

~~~java
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Role;
import org.springframework.security.aot.hint.AuthorizeReturnObjectHintsRegistrar;
import org.springframework.security.aot.hint.SecurityHintsRegistrar;
import org.springframework.security.authorization.method.AuthorizationProxyFactory;

@Bean
@Role(BeanDefinition.ROLE_INFRASTRUCTURE)
static SecurityHintsRegistrar registerReturnObjectTypes(
        AuthorizationProxyFactory proxyFactory) {
    return new AuthorizeReturnObjectHintsRegistrar(
        proxyFactory, ProfileView.class, ContactView.class
    );
}
~~~

**Note:** This is a fragment placed inside a `@Configuration`/`@SpringBootApplication` class; `ProfileView` and `ContactView` must be real classes in the project. If they are nested classes as in section 10 while the fragment sits in another class, use `ReturnObjectApplication.ProfileView.class` and `ReturnObjectApplication.ContactView.class`.

The `AuthorizeReturnObjectHintsRegistrar` API is in package **`org.springframework.security.aot.hint`**; its Javadoc notes `Since: 6.4`. API docs remind you to **list every type needing proxying** missed by default scanning; do not assume a custom registrar traverses arbitrary runtime graphs.

### 15.2. Are AOT hints needed when just running on a regular JVM?

Normally you **do not** need to add this registration just to run the sample Spring Boot JVM application. Only add it when configuring AOT/native images, when types are erased, or when missing native proxies/hints appear in build/tests. **Do not blindly add hints** as a substitute for runtime testing.

### 15.3. What to test with native images

- Objects are genuinely proxied on both JVM and native.
- Nested getter `getContact()` retains its guard.
- Optional/List elements are proxied properly.
- Custom SpEL beans / property getters have sufficient reflection hints.
- JSON serializer works with proxied classes.
- When permission is missing, the response denies or masks per contract.

A passing JVM test suite **does not prove native image success**; native builds require dedicated testing.

## 16. Programmatic proxying: `AuthorizationProxyFactory`

In addition to `@AuthorizeReturnObject`, Spring Security 6.5 provides `AuthorizationProxyFactory` to wrap objects **programmatically** when application flows make annotating a returning method inconvenient.

**Test fragment** example:

~~~java
@Autowired
AuthorizationProxyFactory proxyFactory;

@Test
@WithMockUser(authorities = "profile:read")
void directFactoryProxyChecksEmail() {
    ProfileView raw = new ProfileView(
        "P-1", "Lan", "lan@example.test",
        new ContactView("HCM", "0900000000")
    );

    ProfileView secured = proxyFactory.proxy(raw);
    assertThrows(AccessDeniedException.class, secured::getEmail);
}
~~~

Requires JUnit 5, `@WithMockUser`, and `ProfileView/ContactView` imports. This is a **fragment inside a Spring test class** with a bean factory and `@EnableMethodSecurity`, not a standalone test.

You can create a factory via `AuthorizationAdvisorProxyFactory.withDefaults()` when needed, or configure a `TargetVisitor` per use case. However, manually constructing a factory may differ from the factory Spring uses (advisors/role hierarchy/customizations); for production apps, verify a consistent configuration source.

**Security context note:** if a proxied object escapes the original request/thread and is invoked from a background worker, the `SecurityContext` at call time may differ or be absent. Do not assume the proxy “freezes authorities at creation time”; understand when the method interceptor reads identity and guard tasks/async flows accordingly.

## 17. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `@AuthorizeReturnObject` on Spring Security 6.2 | API does not exist as shown | Check dependencies; use 6.3+ or another pattern |
| Putting `@PreAuthorize` on POJO getter without proxying object | Getter is never intercepted | Use `@AuthorizeReturnObject` on source method/proxy factory |
| Putting `@AuthorizeReturnObject` without member guards | No concrete policy to enforce | Add `@PreAuthorize`/`@PostAuthorize` on sensitive methods |
| Service method self-invocation | Return object may not be wrapped | Call through Spring-managed proxy |
| Putting annotation indiscriminately at class level | Attempts to proxy String/int/value types | Annotate only needed methods or use `TargetVisitor` |
| Returning Java record/final class expecting CGLIB | Cannot subclass-proxy like a POJO | Use suitable proxy type or non-final view |
| Forgetting `@AuthorizeReturnObject` on nested getter | Raw nested object, guarded getter bypassed | Annotate nested getter and test 403 |
| Thinking `List<ProfileView>` auto-filters elements | List retains elements, only getters are guarded | Filter via query/`@PostFilter` as appropriate |
| Thinking Map keys are protected because values are proxied | Key/metadata can still leak | Restrict data at the service layer |
| Returning raw proxy to Jackson expecting auto-masking | Denied getter causes 403/serialization error | Choose DTO, handler, or explicit 403 |
| Using `@HandleAuthorizationDenied` without review | Handler can leak sensitive values | Test masking/return types and negative cases |
| Only testing authorized users | Fails to catch bypassed proxies | Test missing email/phone permissions yield DENY |
| Ignoring AOT/nested generic types | Missing native proxies/hints | Register `AuthorizeReturnObjectHintsRegistrar` per version |
| Using wrong JDK proxy/class proxy structure | Annotations not applied as expected | Verify proxy type, final/private, interfaces, tests |
| Expecting getter protection to replace ACL/tenant | IDOR/BOLA still exists | Check ownership, tenant, field scope early |
| Calling proxy on another thread without context | Permissions depend on wrong context | Design `SecurityContext` propagation |
| Looking only at HTTP 403 without identifying the block point | Misdiagnosing HTTP vs. service vs. getter | Correlate request and direct proxy tests |

## 18. Self-check questions

**Q1.** What does `@AuthorizeReturnObject` do differently from `@PostAuthorize`?  
**Answer:** It requests wrapping the result object in a proxy with authorization advice, rather than deciding allow/deny for the whole result based on `returnObject`.

**Q2.** Can you put `@PreAuthorize` on a POJO's `getEmail()` and expect manually `new`-created POJOs to always be blocked?  
**Answer:** No. The getter must be called through an appropriate proxy/interceptor.

**Q3.** Since which version has Spring Security included `@AuthorizeReturnObject`?  
**Answer:** **6.3**, per `Since: 6.3` in the official Javadoc.

**Q4.** Does `@AuthorizeReturnObject` on a service method automatically grant `profile:email`?  
**Answer:** No. Permissions must be checked on the getter with `@PreAuthorize`/an appropriate policy.

**Q5.** Why add `@AuthorizeReturnObject` to `getContact()`?  
**Answer:** So the nested `ContactView` object is also proxied and `getPhone()` receives authorization advice.

**Q6.** If the `reader` user gets 200 on name yet 403 on email, what does that prove?  
**Answer:** `profile:read` passed, while the email getter was gated by `profile:email`; the whole object was not necessarily denied.

**Q7.** With `Optional<ProfileView>`, when the Optional is empty, is `getEmail()` called?  
**Answer:** No. There is no element to invoke. When present, the factory can wrap the element in a proxy.

**Q8.** If returning `List<ProfileView>`, does `@AuthorizeReturnObject` automatically remove profiles not belonging to the user?  
**Answer:** No. It proxies the elements; list-filtering policy is a separate concern.

**Q9.** Why avoid class-level `@AuthorizeReturnObject` on a service returning many Strings/Integers?  
**Answer:** Spring may try to proxy unsuitable value types; annotate only required methods or use `TargetVisitor`.

**Q10.** Does `@AuthorizeReturnObject` automatically produce JSON with `email=null` when permission is missing?  
**Answer:** No. Jackson calls the getter and may hit an exception; masking requires a policy/handler or an explicit DTO.

**Q11.** When running a native image, why might `List<ProfileView>` need extra hints?  
**Answer:** Generic erasure means the AOT scanner cannot always determine element types needing proxies before build time.

**Q12.** What is the AOT registrar named and since which version did it appear?  
**Answer:** `AuthorizeReturnObjectHintsRegistrar` in `org.springframework.security.aot.hint`, Javadoc `Since: 6.4`.

**Q13.** If the application's raw entity is logged before a proxied getter denies, does the proxy erase the log?  
**Answer:** No. Data/log/cache flows must be protected at the domain and observability layers.

**Q14.** How do you prove `getContact().getPhone()` is genuinely protected?  
**Answer:** Test on a Spring-managed `ProfileService` with `@AuthorizeReturnObject`; a user lacking `profile:phone` calling the nested getter must throw `AccessDeniedException`.

**Q15.** If you add `@PreAuthorize` to a service method yet callers go through `this.method()`, is the result always safe?  
**Answer:** No. Self-invocation in standard proxy mode can bypass both the pre-check and return-object proxying.

**Q16.** Should proxy member authorization be used instead of tenant/owner checks for sensitive documents?  
**Answer:** No. Member proxying is only one barrier; you must constrain queries, returned data, and check per-resource permissions.

**Summary:** **`@AuthorizeReturnObject` wraps returned objects in authorization proxies**, allowing annotations like `@PreAuthorize` on **getters/methods of that object itself** to be checked when the caller uses the object. Available since Spring Security **6.3**, this API works with objects, nested members, Optionals, and collections. On 6.5 pay attention to class/value types, serializers, and AOT/native hints; always write **positive/negative tests** proving both base permissions and individual sensitive fields.

## Official documentation

- Spring Security 6.5 — Method Security, **Authorizing Arbitrary Objects**, Proxying Collections, AOT, and denied results: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — `AuthorizeReturnObject` API (`Since: 6.3`): https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authorization/method/AuthorizeReturnObject.html
- Spring Security 6.5 — `AuthorizeReturnObjectMethodInterceptor`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/AuthorizeReturnObjectMethodInterceptor.html
- Spring Security 6.5 — `AuthorizationProxyFactory` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/AuthorizationProxyFactory.html
- Spring Security 6.5 — `AuthorizeReturnObjectHintsRegistrar` (`Since: 6.4`): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/aot/hint/AuthorizeReturnObjectHintsRegistrar.html
- Spring Security 6.5 — `MethodAuthorizationDeniedHandler` and `@HandleAuthorizationDenied`: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 RC1 release notes — improved Spring MVC integration with `@AuthorizeReturnObject`: https://spring.io/blog/2025/04/21/spring-security-6-5-0-RC1-is-out/
