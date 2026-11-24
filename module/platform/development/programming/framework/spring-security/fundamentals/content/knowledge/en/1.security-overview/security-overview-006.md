# First Terms: principal, credentials, Authentication, and authority

When a request arrives at an application, Spring Security needs to answer two sets of questions: **who is making the request** and **what is that entity allowed to do**. Four terms frequently appear together yet carry distinct meanings:

- **Principal** is the identity being referred to.
- **Credentials** are the proof used to verify the claim about that identity.
- **Authentication** is the object representing an authentication request or an authenticated result, along with its state and associated data.
- **Authority** is a granted permission used when the system decides whether to allow an action.

Imagine Mai enters the username `mai` and a password to read an article. The username is a claim; the password is proof that must be verified. If verification succeeds, the system can confirm Mai's identity. Yet even when Mai is authenticated, reading or publishing an article still depends on permissions and access policies. **Authentication** and **authorization** are two separate decisions.

## 1. Concept Map

| Term | Question to Answer | Example | What Cannot Yet Be Concluded |
| --- | --- | --- | --- |
| `principal` | "Which identity?" | `"mai"`, a `UserDetails`, a `Jwt` | That this identity has been verified |
| `credentials` | "What proof?" | Password just entered, bearer token | That the proof is valid |
| `Authentication` | "What is the current authentication object and state?" | `UsernamePasswordAuthenticationToken` | Certainty of having sufficient access permissions |
| `authority` | "What permissions are granted?" | `ROLE_EDITOR`, `article:read` | Automatically having any other permissions |

A username-and-password login flow typically proceeds as follows:

~~~text
Client sends: principal="mai" + credentials=<password>
                           |
                           v
           Unauthenticated Authentication
                           |
                           v
       AuthenticationManager / AuthenticationProvider
                    verifies proof
                  /                 \
           Succeeded               Failed
             |                       |
             v                       v
  Trusted Authentication        AuthenticationException
  (principal, authorities,
   authenticated=true)
             |
             v
     SecurityContext, if used by mechanism
             |
             v
  Authorization policy checks authority
     matching the operation/resource
~~~

This is a model for understanding the terms; it does not mean every system logs in with passwords. With bearer tokens, JWTs, or federated identity mechanisms, how proof is received and verified differs, while the four concepts still need to be distinguished.

## 2. Principal: The Subject's Identity

**Principal** represents the identity that authentication is examining. The subject can be a user, a service account, or an application calling an API. A principal does not have to be the same Java type across all authentication mechanisms.

In Spring Security, `Authentication#getPrincipal()` returns `Object`. Common cases:

1. **Before username/password authentication:** the value may simply be a `String` containing `"mai"`; anyone can send this claim, so it is not yet trustworthy.
2. **After successful authentication:** a provider may return a `UserDetails` containing username, account status, and data needed by the application. This is not mandatory for every provider.
3. **With a resource server validating JWTs:** the principal may be a `Jwt` object after authentication processing, rather than `UserDetails`.
4. **With an anonymous user:** a principal representing anonymous may exist; it does not prove a real account has logged in.

Also distinguish three expressions:

- `authentication`: **the entire object** carrying authentication data.
- `authentication.getPrincipal()`: **the identity inside** that object.
- `authentication.getName()`: **the name representing the identity**, computed according to the specific `Authentication` implementation.

The `Authentication` interface extends `java.security.Principal`, but that does not make `getPrincipal()` always a `String` or `UserDetails`. Therefore do not cast blindly like `(UserDetails) authentication.getPrincipal()` without knowing which authentication mechanism is in use. If you need a stable business ID, define an explicit contract mapping the principal to an application account.

## 3. Credentials: Proof Supporting the Claim

**Credentials** are the data used to verify that a principal has grounds to be trusted. In password login, this is typically the raw password the user just entered. For APIs, it may be a bearer token or protocol-appropriate identity proof.

| Scenario | Principal/Claim | Credentials/Proof |
| --- | --- | --- |
| Login form | `mai` | Password submitted by Mai |
| HTTP Basic | Username extracted from credentials | Accompanying password |
| Bearer token | Identity to be extracted from a valid token | Bearer token sent by client |
| Service account | Service identity | Secret or proof required by the active mechanism |

The `Authentication#getCredentials()` method returns `Object` and may return `null`. A `null` value **does not by itself prove login failed**: after successful authentication, `ProviderManager` by default typically attempts to erase sensitive credentials from the resulting object if the object supports `CredentialsContainer`. The application then still has principal and authorities to work with without keeping the raw password.

Practices to follow:

- Do not log passwords, bearer tokens, or other secrets into logs, error messages, API responses, or `toString()` calls used for logging.
- Do not retain raw credentials inside `SecurityContext` for reuse. After verification, keep only data genuinely needed for processing.
- Do not manually compare raw passwords as strings in controllers. Use properly configured providers and `PasswordEncoder`.
- Do not confuse a **client-supplied bearer token** with Spring Security's **`Authentication`** object. Both are sometimes casually called "tokens", but they serve different roles.

## 4. Authentication: Authentication Request and Result

`org.springframework.security.core.Authentication` is the central interface in Spring Security. The same interface can represent either an **unauthenticated request** or an **authenticated result**. For example, `UsernamePasswordAuthenticationToken` holds a username and password before verification, and then another instance of the same type can represent a trusted result afterward.

| Component | Method | Meaning |
| --- | --- | --- |
| Identity | `getPrincipal()` | Object representing the subject |
| Proof | `getCredentials()` | Identity-proving data, possibly already erased |
| Granted permissions | `getAuthorities()` | Collection of `GrantedAuthority` used as input for authorization |
| Status | `isAuthenticated()` | Trust state according to the `Authentication` implementation |
| Subject name | `getName()` | Name exposed by the object for identification |
| Other details | `getDetails()` | Additional data populated by the authentication mechanism, not a default place to store permissions |

Compare before and after concretely:

~~~text
Before verification:
  principal       = "mai"                (unverified)
  credentials     = password just received
  isAuthenticated = false
  authorities     = []

After provider verifies successfully (illustrative):
  principal       = "mai" or Mai's UserDetails
  credentials     = null                 (common due to erasing sensitive data)
  isAuthenticated = true
  authorities     = ["ROLE_EDITOR", "article:read"]
~~~

An `AuthenticationManager` such as `ProviderManager` chooses an appropriate provider to authenticate. When credentials are invalid, `authenticate(...)` usually **throws `AuthenticationException`**; do not mistakenly picture every failed login as returning a normal result with a `false` flag.

**Trust boundary:** request-handling code must only build unauthenticated input data. Only trusted authentication components should mark a result as authenticated based on verified proof. Creating an `Authentication` with `isAuthenticated=true` from arbitrary client-sent data can bypass the entire protection mechanism.

### Where Does SecurityContext Hold Authentication for Use?

In a standard **servlet** application, after successful authentication, Spring Security filters can place the result into `SecurityContext`; `SecurityContextHolder` lets processing code access the current context. The snippet below is only code inside an application already integrated with Spring Security, not a standalone program:

~~~java
Authentication current =
        SecurityContextHolder.getContext().getAuthentication();

if (current != null) {
    String displayName = current.getName();
    // displayName used for appropriate display/audit;
    // access permissions are decided by Spring Security.
}
~~~

Both types are imported from `org.springframework.security.core.Authentication` and `org.springframework.security.core.context.SecurityContextHolder`. `getAuthentication()` can be `null`, or carry an anonymous token depending on configuration. In reactive applications, the security context uses a Reactor-bound mechanism instead of assuming a servlet `ThreadLocal`.

**Important trap:** `AnonymousAuthenticationToken` can have `isAuthenticated() == true` internally. Therefore, a hand-written check `current != null && current.isAuthenticated()` is not a reliable test for "a real user has logged in". Use the `authenticated()` rule or authentication-type evaluation components provided by Spring Security. Even when authenticated, resource access must still go through authorization.

## 5. Authority: Granted Permissions for Authorization

**Authority** describes a permission or permission label recognized by the system for a subject. Spring Security represents it via the `GrantedAuthority` interface, commonly using `SimpleGrantedAuthority` holding a string, such as:

- `ROLE_EDITOR`: editor role.
- `article:read`: permission to read articles.
- `article:publish`: permission to publish articles.
- `SCOPE_messages.read`: an example of a scope mapped into an authority in some OAuth2 configurations.

`Authentication#getAuthorities()` returns a collection of `GrantedAuthority`. This collection can be empty even when someone is authenticated. Which authorities exist depends on the issuing source and configured authority mapping; **never trust arbitrary permission strings sent by the client**.

### A Role Is Not a Different Kind of Identity

In common configurations, a **role is a naming convention for an authority** with the `ROLE_` prefix. For example, role `EDITOR` usually corresponds to authority string `ROLE_EDITOR`. Compare the two check styles:

| Condition | String Needed in `GrantedAuthority` Under Default Config |
| --- | --- |
| `hasAuthority("article:read")` | `article:read` |
| `hasAuthority("ROLE_EDITOR")` | `ROLE_EDITOR` |
| `hasRole("EDITOR")` | `ROLE_EDITOR` |
| `hasAuthority("EDITOR")` | `EDITOR` |

`hasRole` prepends `ROLE_` by default; `hasAuthority` matches the exact string passed in. This prefix can be configured differently. Having `ROLE_EDITOR` does not automatically include `ROLE_ADMIN`; having `article:read` does not automatically include `article:publish`. If there is a role hierarchy or relationship between permissions, the application must configure it explicitly.

**Authentication answers who has been identified and in what state; authorization uses authorities and other conditions to determine whether an operation is permitted.** An authenticated principal is not automatically permitted to access every resource.

## 6. Runnable Java 17+ Example to Observe the Four Terms

The example uses real Spring Security classes, observes an unauthenticated request, and **simulates** an authenticated result. The code creating the result is strictly for studying the data structures: it **does not verify a password** and is not how production login is implemented.

Create a Gradle project with `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
}

application {
    mainClass = 'AuthTermsDemo'
}
~~~

Create `src/main/java/AuthTermsDemo.java`:

~~~java
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public class AuthTermsDemo {
    public static void main(String[] args) {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "mai", "demo-secret");

        System.out.println("request.authenticated=" + request.isAuthenticated());
        System.out.println("request.principal=" + request.getPrincipal());
        System.out.println("request.hasCredentials=" + (request.getCredentials() != null));
        System.out.println("request.authorities=" + request.getAuthorities().size());

        // Illustrates a result that a trusted provider could produce.
        // This program does NOT verify any password.
        Authentication result =
                UsernamePasswordAuthenticationToken.authenticated(
                        "mai",
                        null,
                        List.of(
                                new SimpleGrantedAuthority("ROLE_EDITOR"),
                                new SimpleGrantedAuthority("article:read")));

        String labels = result.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.joining(", "));

        boolean mayRead = result.getAuthorities().stream()
                .anyMatch(a -> "article:read".equals(a.getAuthority()));

        System.out.println("result.authenticated=" + result.isAuthenticated());
        System.out.println("result.name=" + result.getName());
        System.out.println("result.hasCredentials=" + (result.getCredentials() != null));
        System.out.println("result.authorities=" + labels);
        System.out.println("result.mayRead=" + mayRead);
    }
}
~~~

With JDK 17 or higher and Gradle installed, run from the project directory:

~~~bash
gradle run --quiet
~~~

Program output:

~~~text
request.authenticated=false
request.principal=mai
request.hasCredentials=true
request.authorities=0
result.authenticated=true
result.name=mai
result.hasCredentials=false
result.authorities=ROLE_EDITOR, article:read
result.mayRead=true
~~~

Interpreting the output: `request` holds the user-claimed principal and unverified credentials; thus `authenticated=false`. In the illustrative `result`, the flag is `true`, credentials are `null`, and authorities contain `ROLE_EDITOR` and `article:read`. The `mayRead` check only matches an authority string to illustrate reading `GrantedAuthority`; in a real application, let Spring Security's authorization mechanism enforce access policies. The example intentionally prints only the **presence** of credentials, not the secret.

This standalone sample pins `spring-security-core:6.5.11` so readers can reproduce it. In a Spring Boot project using the security starter, follow the version managed by Spring Boot and avoid overriding dependency versions arbitrarily.

## 7. Four Terms Coming Together in One Access Decision

Suppose user Mai authenticated successfully and has authorities `ROLE_EDITOR` and `article:read`:

| Task | Rule | Result Under Assumed Data |
| --- | --- | --- |
| Read article | `hasAuthority("article:read")` | Allowed |
| Publish article | `hasAuthority("article:publish")` | Denied due to missing permission |
| Open editorial section | `hasRole("EDITOR")` | Allowed under default prefix |
| System administration | `hasRole("ADMIN")` | Denied due to missing `ROLE_ADMIN` |

A corresponding servlet configuration fragment could look like this. This is a **configuration snippet that must live inside a valid `SecurityFilterChain`**, not a standalone Java file:

~~~java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/articles/**").hasAuthority("article:read")
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
);
~~~

Beyond authorities, a resource may require the accessor to be the owner, belong to the right tenant, or meet business constraints. Therefore a generic authority does not automatically replace every check against a specific object.

## 8. Common Misconceptions

1. **"Having a principal means logged in."** Not true: it may just be a self-claimed username before authentication.
2. **"Having credentials means authenticated."** Not true: the proof must be verified by a provider.
3. **"`getCredentials() == null` means not logged in."** False: secrets are commonly erased after authentication.
4. **"`Authentication` and principal are the same thing."** False: `Authentication` is the broader object containing the principal along with status, credentials, and authorities.
5. **"`isAuthenticated()==true` allows going anywhere in the system."** False: authorization is required; with an anonymous token you must also inspect the authentication type.
6. **"`hasRole("EDITOR")` checks the string `EDITOR`."** By default it checks `ROLE_EDITOR`; `hasAuthority` matches the exact string passed in.
7. **"A role always includes all weaker roles."** Not by default; hierarchy must be configured.
8. **"You can accept a permission list directly from the user's JSON."** Unsafe: only permissions established from trusted sources may be used to grant access.
9. **"Having `article:read` guarantees reading every article."** Not sufficient: ownership or data-scope conditions may still apply.

## 9. Self-Check Your Understanding

**Scenario A.** Mai enters `mai` and an incorrect password. The principal is still the claimed name; credentials were sent, yet authentication fails to produce a trusted result. Access must not be granted merely because two input fields were supplied.

**Scenario B.** After authentication, `getCredentials()` is `null` and `getAuthorities()` contains `article:read`. There is no contradiction: secrets can be erased while retaining the identity and needed permissions.

**Scenario C.** An `Authentication` has `ROLE_READER`, while a resource requires `hasAuthority("article:publish")`. Even though the user is authenticated, this policy still denies access because the required authority is missing.

**Scenario D.** Under the default role prefix, `hasRole("ADMIN")` and `hasAuthority("ROLE_ADMIN")` both look for the label `ROLE_ADMIN`; `hasAuthority("ADMIN")` looks for a different label.

When reading Spring Security code, ask yourself in order: **which principal is being referenced, which credentials are verified, which component produces a trusted `Authentication`, and which rule matches authorities against the protected action?** Answering all four questions helps separate authentication errors from authorization errors.

### Reference Documentation

- [Spring Security — `Authentication` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/Authentication.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — Anonymous Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html)
