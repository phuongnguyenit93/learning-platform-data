# 17.9 Boundary Between JAAS Configuration and the JCA Security Provider Model

## Learning Objectives

After this lesson, you will be able to pinpoint which component determines **how a subject is authenticated** and which component provides **the implementation of a security algorithm or service** in Java. You will also be able to explain why both mechanisms are called "providers" yet do not share the same registry, recognize the special intersection at `Configuration.getInstance(...)`, and diagnose errors at the right layer.

**Key takeaway:** JAAS configuration selects and coordinates the `LoginModule`s for an application login. The JCA `java.security.Provider` model selects the implementation of a service by service type and algorithm name. A `LoginModule` may *use* JCA services, but registering a JCA provider does not automatically register or replace a `LoginModule`.

## 1. Two Distinct Axes of Extensibility

| Question | JAAS (Java Authentication and Authorization Service) | JCA (Java Cryptography Architecture / Java Security provider) |
|---|---|---|
| Problem addressed | Who is logging in, which authentication mechanism is used, and how are authentication steps combined? | Who provides the implementation for `MessageDigest`, `Signature`, `Cipher`, `KeyStore`, `Mac`, `SecureRandom`…? |
| Common entry-point API | `new LoginContext("AppName")` then `login()` | `MessageDigest.getInstance("SHA-256")`, `Signature.getInstance("SHA256withRSA")`… |
| Where implementations are selected | `javax.security.auth.login.Configuration` maps an application name to a list of `LoginModule` classes along with control flags/options | The list of `java.security.Provider` instances registers `Provider.Service` entries by service type and algorithm |
| Pluggable unit | A class implementing `javax.security.auth.spi.LoginModule` | A provider registering SPI implementations such as `MessageDigestSpi`, `SignatureSpi`, `CipherSpi` |
| Typical outcome | Login state and a `Subject` containing `Principal`s/credentials after successful authentication | An engine object backed by the selected algorithm implementation, such as `MessageDigest` or `Signature` |
| Composition rules | Module order and `required`, `requisite`, `sufficient`, `optional` | Provider priority order, supported services/algorithms, and an explicitly specified provider if given |
| Effect of changing configuration | Changes the authentication method or stack for a login entry | Changes the cryptography/security service implementation called by JCA APIs |

Therefore, "changing where identity is verified" and "changing the library that performs signing/decryption" are two separate operations. They can work together in the same authentication flow, but they do not replace each other.

## 2. How Does JAAS Configuration Control `LoginContext`?

A JAAS configuration typically looks like the following (an illustrative example for an environment that **already has Kerberos**, which will not run on its own if the machine is not configured for Kerberos):

```text
BackendLogin {
    com.sun.security.auth.module.Krb5LoginModule required
        useTicketCache="true";
};
```

- `BackendLogin` is the **JAAS entry name**. Calling `new LoginContext("BackendLogin")` looks up this exact name, not a JCA provider name or an algorithm name.
- `com.sun.security.auth.module.Krb5LoginModule` is the **LoginModule class name**; its mechanism is Kerberos authentication. Another module might check accounts, tokens, certificates, or integrate with an external system.
- `required` is the **control flag** for the overall login process; `useTicketCache` is an option understood by `Krb5LoginModule` *itself*. JAAS does not interpret this option as a JCA service.
- `LoginContext` reads the `Configuration`, instantiates the declared `LoginModule`s, calls `initialize`, and orchestrates the steps. If the requested entry does not exist, it may fall back to the default `other` entry; if both are missing, creating the `LoginContext` fails.

The control flags have clear security semantics:

| Flag | If the module fails | If the module succeeds |
|---|---|---|
| `required` | Continues running subsequent modules, but the overall login still ultimately fails | Continues running subsequent modules; this module's success is mandatory |
| `requisite` | Terminates login processing immediately with failure | Continues running subsequent modules; also mandatory |
| `sufficient` | Usually continues running subsequent modules | May terminate early with success if no prior `required`/`requisite` module failed |
| `optional` | Usually continues running subsequent modules | Usually continues running subsequent modules; only contributes to the overall result |

If there is no `required` or `requisite` module, at least one `sufficient` or `optional` module must succeed. Setting the wrong flag or order can create a weaker authentication flow than intended. A succeeding `sufficient` module does **not** clear the failure of a previously executed `required` module.

Typical processing flow:

```text
Application
  -> LoginContext("BackendLogin")
  -> Configuration.getAppConfigurationEntry("BackendLogin")
  -> LoginModules in order and by control flag
  -> login() on each module (validating input data)
  -> if the overall login succeeds: commit() the modules
     if it fails: abort() and clean up state
  -> Subject with Principal/credentials after successful commit
  -> logout() when the session ends
```

`CallbackHandler` allows a module to request input data via `NameCallback`, `PasswordCallback`, and similar callbacks instead of depending on a concrete input UI. `Subject` is the container for identities and credentials after authentication; a `Principal` can be a username or another identity. **Having a `Subject` does not mean every API will automatically enforce permission checks:** the application/system must still enforce appropriate authorization rules.

Important boundary note: even though `LoginModule` is an SPI in the `javax.security.auth.spi` package, it is **not** a `java.security.Provider`. Adding a `LoginModule` to a JAAS file does not place that module into `Security.getProviders()`.

## 3. How Does JCA Select a `Provider`?

JCA separates the API used by an application from the implementations of security services. In the example below, the application requests the **`MessageDigest` service type + `SHA-256` algorithm**, not a user login:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
System.out.println(digest.getAlgorithm());
System.out.println(digest.getProvider().getName());
```

This is a **snippet placed inside a method**; `java.security.MessageDigest` must be imported. The provider name on the second output line depends on the JDK and runtime configuration, so you should not assume it is always a fixed name.

Selection mechanism:

1. `Security.getProviders()` returns the registered `Provider`s and their priority order.
2. Each provider declares `Provider.Service` entries—for example, a `MessageDigest` service supporting `SHA-256` or a `Signature` service supporting `SHA256withRSA`.
3. `getInstance("algorithm")` without specifying a provider finds a matching implementation according to the runtime's priority mechanism; the JDK may apply algorithm-specific preferences via `jdk.security.provider.preferred`.
4. `getInstance("algorithm", "ProviderName")` requests a specific provider; a missing provider or unsupported service results in the corresponding exception.
5. The engine API delegates to the SPI of the selected implementation, such as `MessageDigestSpi`. A provider may be implemented in Java, via native libraries, or with security hardware.

Providers can be configured in the JDK security file via `security.provider.N` or managed at runtime via `Security.addProvider(...)` / `Security.insertProviderAt(...)`. This modifies the **JVM-wide JCA service registry**, not the `LoginModule` chain of a JAAS entry. Do not alter the global provider order arbitrarily: every component using JCA in the JVM can be affected.

JCA/security providers do not only cover cryptographic primitives. The provider mechanism also supports certain other security services, including JAAS `Configuration` (see Section 4). That is the root cause of the naming confusion.

## 4. Subtle Intersection: A `Configuration` Provider Is Not a `LoginModule` Provider

The word "provider" has at least three distinct contexts that must be separated:

| Term | Actual component | Selected by what? |
|---|---|---|
| Authentication provider in JAAS documentation | A `LoginModule` class implementing an authentication technology | `Configuration` entry, class name, order, and flag |
| Login configuration provider | A `javax.security.auth.login.Configuration` implementation supplying the list of `LoginModule`s | `Configuration.getConfiguration()`/`setConfiguration(...)` or a `getInstance(...)` factory |
| JCA security provider | A `java.security.Provider` registering services/algorithms via SPI | The security providers list and the service's `getInstance(...)` factory |

Two ways of obtaining a `Configuration` are especially easy to confuse:

**Path 1 — the default/installed JAAS configuration for the JVM.** `Configuration.getConfiguration()` retrieves the `Configuration` object installed via `Configuration.setConfiguration(...)`, or instantiates the default implementation. The security property `login.configuration.provider` can specify the **class name** of the `Configuration` implementation. With the file-based implementation, this object reads entries from the JAAS file. Changing this property is not equivalent to `Security.addProvider(...)`.

**Path 2 — a factory using the JCA provider model itself.** `Configuration.getInstance("JavaLoginConfig", null)` looks up the **`Configuration`/`ConfigurationSpi`** service in the registered security providers list and returns a `Configuration` object supported by that provider. This genuinely is an integration point with JCA. If the requested service/type is unavailable, the factory may throw `NoSuchAlgorithmException`. Do not assume every vendor or JDK will select the same provider.

```java
import javax.security.auth.login.Configuration;

// Snippet placed inside a method; a provider supporting JavaLoginConfig must be present in the JVM.
Configuration config = Configuration.getInstance("JavaLoginConfig", null);
System.out.println(config.getProvider().getName());
```

Once you have the `config` object, authentication still relies on the `AppConfigurationEntry` objects returned by `config`. Those entries determine the **`LoginModule` classes**. `Configuration.getInstance(...)` does not turn the `LoginModule` list into a `Provider.Service` list.

Developers can also pass a `Configuration` directly to the `LoginContext(String, Subject, CallbackHandler, Configuration)` constructor to explicitly choose the configuration for that login attempt, rather than relying solely on the global JAAS configuration.

A `LoginModule` may use JCA engines internally: for example, verifying a digital signature with `Signature`, accessing keys through `KeyStore`, or running encryption operations via `Cipher`. At that point, **JAAS selects the module**, while **JCA selects the cryptography/security service implementation that the module calls**:

```text
LoginContext -> Configuration -> LoginModule -> verify credential -> Subject
                                       |
                                       +-> Signature/KeyStore/Cipher.getInstance(...)
                                                -> JCA Provider -> SPI implementation
```

What they share is the ability to swap implementations; the boundary is **selecting an authentication workflow** versus **selecting the implementation of a security service**.

## 5. Distinguishing Very Similar Configuration Names

| Name/API | Kind | What does it control? |
|---|---|---|
| `-Djava.security.auth.login.config=demo-jaas.conf` | JVM **system property** | Location of the JAAS entry file for the default file-based configuration implementation |
| `login.config.url.1`, `login.config.url.2`… | **Security properties** in `conf/security/java.security` | JAAS configuration URLs for the file-reading implementation |
| `login.configuration.provider` | **Security property** | Class name of the `Configuration` implementation used for the default JAAS configuration |
| `Configuration.setConfiguration(config)` | Java API | Replaces the globally installed JAAS `Configuration` object |
| `Configuration.getInstance(type, params)` | Provider-backed Java API | Finds a `ConfigurationSpi` implementation for the type through the JCA provider registry |
| `security.provider.1`, `security.provider.2`… | **Security properties** | JCA provider registration and priority order |
| `Security.addProvider(provider)` / `insertProviderAt(...)` | Java API | Adds a JCA provider at runtime |

System properties starting with `-D` are not the same as security properties retrieved via `Security.getProperty(...)`. The `java.security` file is the JDK's security configuration file; `demo-jaas.conf` contains **`LoginModule` entries**. The two files serve different purposes.

When asking "I already installed the provider, so why didn't JAAS change?", check whether you just installed a **`java.security.Provider`**, changed **`Configuration`**, or edited **`LoginModule` entries**. The three actions are not interchangeable.

## 6. Java 17+ Example: One JAAS Login and One Independent JCA Provider Selection

This example runs on a standard JDK with JAAS/JCA and does not require Kerberos. To stay focused on the **module selection mechanism**, `DemoLoginModule` intentionally accepts every login and attaches a mock principal. **It does not verify real credentials and must never be used to protect an application.**

Create three files in the same directory.

**File `demo-jaas.conf`** — JAAS selects the class and control flag:

```text
Demo {
    DemoLoginModule required;
};
```

**File `DemoLoginModule.java`** — implements the JAAS SPI:

```java
import java.security.Principal;
import java.util.Map;
import javax.security.auth.Subject;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.spi.LoginModule;

public class DemoLoginModule implements LoginModule {
    private Subject subject;
    private Principal principal;
    private boolean passed;

    @Override
    public void initialize(Subject subject, CallbackHandler handler,
                           Map<String, ?> sharedState, Map<String, ?> options) {
        this.subject = subject;
    }

    @Override
    public boolean login() {
        passed = true; // Illustrates the mechanism only; does not authenticate a real user.
        return true;
    }

    @Override
    public boolean commit() {
        if (!passed) return false;
        principal = () -> "demo-user";
        subject.getPrincipals().add(principal);
        return true;
    }

    @Override
    public boolean abort() {
        return logout();
    }

    @Override
    public boolean logout() {
        if (principal != null) subject.getPrincipals().remove(principal);
        principal = null;
        passed = false;
        return true;
    }
}
```

**File `BoundaryDemo.java`** — application calling both systems:

```java
import java.security.MessageDigest;
import javax.security.auth.login.LoginContext;

public class BoundaryDemo {
    public static void main(String[] args) throws Exception {
        LoginContext context = new LoginContext("Demo");
        context.login();
        System.out.println("JAAS principal: " +
                context.getSubject().getPrincipals().iterator().next().getName());

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        System.out.println("JCA algorithm: " + digest.getAlgorithm());
        System.out.println("JCA provider assigned: " + (digest.getProvider() != null));

        context.logout();
        System.out.println("JAAS principals after logout: " +
                context.getSubject().getPrincipals().size());
    }
}
```

Compile and run in the directory containing the three files:

```bash
javac BoundaryDemo.java DemoLoginModule.java
java -Djava.security.auth.login.config=demo-jaas.conf BoundaryDemo
```

**Expected output** (verified by compiling and running on OpenJDK; the provider check prints a boolean so it does not depend on vendor name):

```text
JAAS principal: demo-user
JCA algorithm: SHA-256
JCA provider assigned: true
JAAS principals after logout: 0
```

Trace the exact **two implementation-selection paths**:

1. `LoginContext("Demo")` looks up the `Demo` entry in the JAAS configuration file. The entry specifies `DemoLoginModule` with the `required` flag. `login()` followed by `commit()` adds the principal to the `Subject`; `logout()` removes the principal.
2. `MessageDigest.getInstance("SHA-256")` queries the JCA registry to find a provider for the SHA-256 algorithm; it does not inspect the name `Demo`, the class name `DemoLoginModule`, or the `required` control flag.
3. Replacing `DemoLoginModule` in `demo-jaas.conf` changes the JAAS flow. Replacing the provider that supplies `SHA-256` affects `MessageDigest` instantiation. Each operation is independent unless the authentication module itself calls JCA internally.

This example only verifies wiring and call flow. In a real system, `login()` must validate authentication evidence through a trusted service, handle secrets properly, and only then `commit()` identity data; an application-added `Principal` must never be treated as proof of authentication.

## 7. Localizing Errors by Layer Instead of Misconfiguring

| Symptom | Check first | Do not jump to the conclusion |
|---|---|---|
| `LoginException` reporting a missing `LoginModule` for an entry | Name in `LoginContext("...")`, loaded JAAS file, `other` entry, class name/syntax | "No cryptographic provider is installed" |
| `LoginException` / `FailedLoginException` inside a module | Credentials, callbacks, options, module order, and flags | "Wrong SHA-256 algorithm" |
| `ClassNotFoundException` or `LoginModule` instantiation error | Classpath/module path, class name, visibility/constructor, dependencies | "Must call `Security.addProvider`" |
| `NoSuchAlgorithmException` from `MessageDigest.getInstance`/`Signature.getInstance` | Algorithm/service name and which provider supports it | "Missing `LoginModule` entry" |
| `NoSuchProviderException` when specifying a JCA provider | Actual name/registration of the JCA provider present | "Wrong JAAS control flag" |
| `NoSuchAlgorithmException` from `Configuration.getInstance` | Which provider supports the `Configuration` service and a type such as `JavaLoginConfig` | "Every `LoginModule` runs through JCA" |
| Login succeeds, yet resource access still fails | Application authorization, principal → permission mapping, session handling | "`Subject` automatically protects every API" |

Quick diagnostic rule: locate **the first API that throws the error**. Errors in `LoginContext`/`LoginModule` usually belong to the JAAS path; errors from engine `getInstance` belong to JCA service selection; authorization errors belong to an independent permission-decision layer. If a `LoginModule` calls JCA internally, the stack trace may pass through **both**; identify the exact failing step.

## 8. When Both Systems Appear Together in Real-World Applications

**Case A — changing the login method:** switching from an account-checking module to Kerberos/LDAP is done by changing the `LoginModule` configuration and preparing the corresponding infrastructure. Adding a SHA-256 provider does not switch the login method.

**Case B — keys stored in an HSM/PKCS#11:** register a JCA/PKCS#11 provider so `KeyStore`/`Signature` use hardware. A `LoginModule` can use it when authenticating via signatures/certificates, but the rules for "who may log in" and how identities map to a `Principal` are still managed by the authentication flow.

**Case C — an already-authenticated application needs to sign a document:** JAAS establishes the user's `Subject`; business APIs check signing permissions, and then `Signature` obtains an implementation from a JCA provider. "Authentication succeeded," "authorized to sign," and "valid signing algorithm" are three separate checks.

**Case D — changing the JVM-wide JCA provider:** the change can affect TLS, signatures, keystores, and other engines using that provider. State a concrete reason when pinning a provider name; let JCA choose automatically when there is no special compatibility, hardware, or compliance requirement.

## 9. Safety Principles and Takeaways

- **Do not confuse authentication with authorization.** `Subject`/`Principal` describes identity after JAAS; the application must enforce permissions on resources, and having a `Subject` object does not automatically protect every API.
- **Do not treat provider presence as proof of authentication.** `Security.getProviders()` only tells you which JCA services are available; being able to create a `MessageDigest` says nothing about a user's identity.
- **Do not put secrets into demo examples or logs.** `CallbackHandler` should pass user input to the `LoginModule`; the module must verify against a trusted system and clear credentials when no longer needed. Never use plain `SHA-256` to store passwords; password systems need a proper KDF, salt, and configured work factor.
- **Read JAAS order and control flags as a security policy.** `required`, `requisite`, `sufficient`, and `optional` alter success conditions; review both success and failure cases for every module.
- **Distinguish where configuration lives.** The JAAS file holds `LoginModule` entries; security properties configure `Configuration` or the provider registry; application code calls the API that determines which step is executed.

Self-check questions:

1. Does calling `Security.addProvider(new MyProvider())` automatically add `MyLoginModule` to `LoginContext("App")`? **No**; you must configure the JAAS entry or supply a corresponding `Configuration`.
2. Does changing `required` to `sufficient` affect `MessageDigest.getInstance("SHA-256")`? **Not directly**; it changes the policy for combining authentication modules.
3. Why is `Configuration.getInstance("JavaLoginConfig", null)` a notable exception? Because in this API, **the JAAS configuration object** is selected via the **JCA provider/`ConfigurationSpi` mechanism**; the contents of that configuration still determine the `LoginModule`s.
4. If a `LoginModule` uses `Signature.getInstance(...)` and the algorithm is missing, where do you fix it? Check the **JCA service/algorithm/provider** requested by the module, while keeping JAAS responsible for deciding which module is invoked.

## Official Documentation

- Oracle, *JAAS Reference Guide* (Java 21): https://docs.oracle.com/en/java/javase/21/security/java-authentication-authorization-service-jaas-reference-guide.html
- Oracle, *JAAS LoginModule Developer's Guide* (Java 21): https://docs.oracle.com/en/java/javase/21/security/java-authentication-and-authorization-service-jaas-loginmodule-developers-guide1.html
- Java SE 21 API, `Configuration`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/login/Configuration.html
- Java SE 21 API, `LoginContext`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/login/LoginContext.html
- Oracle, *JCA Reference Guide* (Java 21): https://docs.oracle.com/en/java/javase/21/security/java-cryptography-architecture-jca-reference-guide.html
