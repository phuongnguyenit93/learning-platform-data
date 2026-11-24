# 17.6 required, requisite, sufficient, optional, and Combining Multiple LoginModules

## Learning Objectives

After this lesson, you will be able to:

1. Explain how **JAAS (Java Authentication and Authorization Service)** uses `LoginContext`, `Configuration`, `LoginModule`, `Subject`, `Principal`, and `CallbackHandler` to combine multiple authentication sources in Java 17.
2. Distinguish the four **LoginModule control flags**: `required`, `requisite`, `sufficient`, and `optional`—especially continuation rules, early termination, and **entire-stack** outcomes.
3. Correctly predict tricky cases: a `required` module fails yet a subsequent `sufficient` succeeds; a `sufficient` succeeds before a `required`; multiple `optional` modules; a `requisite` fails mid-stack.
4. Understand the two phases of JAAS: `login()` to evaluate each module, followed by `commit()` or `abort()`; use `logout()` to remove module-added identities/credentials.
5. Create and run **two standalone Java 17 programs**: simulating the control-flag matrix and proving that an **MFA configuration with an `optional` OTP** can unintentionally allow login when OTP is wrong.
6. Distinguish **OR (alternative mechanisms)** from **AND (multiple mandatory factors)**; design configurations, callbacks, shared state, error handling, and tests to prevent security bypasses.

## 1. How Does JAAS Support "Stacked Authentication"?

JAAS is a pluggable authentication model capable of combining multiple authentication components. The application does not need to know whether it is checking a password, Kerberos, a smart card, or another mechanism; it calls `LoginContext`. Concrete authentication components implement `javax.security.auth.spi.LoginModule`.

A diagram:

```text
Application
    |
    | new LoginContext("AppName", handler)
    | context.login()
    v
JAAS LoginContext
    |
    +--> Configuration: AppName
    |       |
    |       +-- PasswordModule  required
    |       +-- OtpModule       required
    |       +-- AuditModule     optional
    |
    +--> LoginModule.login() in order
    |
    +--> Evaluate control flags
    |
    +--> If login phase succeeds: commit()
    |      and update Subject/Principal
    |
    +--> If login phase fails: abort()
           and clear temporary state
    |
    v
Application receives Subject on success
```

Core concepts:

| Component | Role |
| --- | --- |
| `LoginContext` | Entry point where the application calls `login()`, `getSubject()`, `logout()`; orchestrates multiple modules |
| `Configuration` | Module list, **order**, flags, and options mapped by application name |
| `AppConfigurationEntry` | Describes one module class, one flag, and an options map |
| `LoginModule` | Verifies one form of authentication; manages state/Principal lifecycle |
| `CallbackHandler` | Mechanism for modules to gather input such as username/password or verification codes |
| `sharedState` | Per-login-attempt map shared across modules; avoid storing unnecessary secrets |
| `Subject` | Authenticated entity and its sets of `Principal`s/credentials |
| `Principal` | Subject identity/attribute at the identity level; **does not prove access permissions by itself** |

Application code can be very simple:

```java
LoginContext context = new LoginContext("MyApplication", callbackHandler);
context.login(); // Returns on success; throws LoginException on failure
Subject subject = context.getSubject();
// Use subject per application policy, then:
context.logout();
```

This is an **embedded snippet**, not a standalone Java file: it requires imports, a `callbackHandler` definition, and a JAAS configuration for the name `MyApplication`. `LoginContext` decides which modules are called based on the configuration, rather than the caller invoking each `LoginModule.login()` manually.

**Module ordering is part of your security policy.** With the exact same list, moving `sufficient` or `requisite` can change the outcome and how many authentication mechanisms are actually required.

## 2. Configuration Structure and the Four Control Flags

A login configuration file typically has the structure:

```text
ApplicationName {
    module.class.Name required  optionA="value";
    module.class.Name requisite optionB="value";
    module.class.Name sufficient optionC="value";
    module.class.Name optional  optionD="value";
};
```

This is **structural syntax for illustration**, not a runnable configuration because the class names here only indicate placeholders and are not implemented classes. Each module entry ends with `;`, and the application stanza ends with `};`. The application name is passed to `LoginContext`.

The Java 17 `Configuration` documentation specifies:

| Flag | Must succeed for the overall stack to pass? | If `login()` succeeds | If `login()` fails |
| --- | --- | --- | --- |
| **`required`** | **Yes** | Proceed to subsequent modules | **Still proceeds**, but the overall stack will fail |
| **`requisite`** | **Yes** | Proceed to subsequent modules | **Stops the login phase immediately**, returns failure |
| **`sufficient`** | Not mandatory | **May finish early with success** if **no prior `required`/`requisite` failed** | Proceed to subsequent modules |
| **`optional`** | Not mandatory | Proceed to subsequent modules | Proceed to subsequent modules |

**Overall rule:** all `required` and `requisite` modules **evaluated before any valid early termination** must succeed. If the configuration has **no `required`/`requisite` modules**, at least **one** `sufficient` or `optional` module must succeed. A succeeding `SUFFICIENT` module can prevent subsequent modules from executing; therefore you cannot interpret "every `required` module always runs" in isolation from configuration order.

### 2.1 `required` — Mandatory, Yet Does Not Halt Immediately on Failure

Example:

```text
PasswordCheck  required  -> FAIL
DeviceCheck    optional  -> PASS
AuditCheck     optional  -> PASS

Final result: FAIL
```

`LoginContext` still invokes the modules after `PasswordCheck`. Advantage: it avoids revealing too blatantly which step failed merely by **stopping immediately**, and lets downstream components execute as designed. However, this **does not guarantee constant-time responses** since modules can take different amounts of time.

**Never** treat a succeeding `optional` module as "rescuing" a failed `required` module.

### 2.2 `requisite` — Mandatory and Short-Circuits on Failure

Example:

```text
AccountExists  requisite -> FAIL
PasswordCheck  required  -> NO login()
OtpCheck       required  -> NO login()

Final result: FAIL
```

If a `requisite` module fails, JAAS halts the **`login()` evaluation phase** immediately. Nevertheless, `abort()` cleanup still runs per the lifecycle; "stopping early" does not mean skipping post-failure cleanup.

Placing `requisite` earlier can **save cost** by skipping downstream steps once a mandatory condition has already failed. On the flip side, timing or external system calls can leak why login failed if messages and timing are not carefully designed.

### 2.3 `sufficient` — Enough to Finish Early If No Prior Mandatory Failure Occurred

Compare two cases carefully:

```text
Case A:
PasswordCheck  required   -> PASS
TrustedTicket  sufficient -> PASS
ExtraCheck     optional   -> NO login()

Result: PASS (no prior mandatory failure)
```

```text
Case B:
PasswordCheck  required   -> FAIL
TrustedTicket  sufficient -> PASS
ExtraCheck     optional   -> still calls login()

Result: FAIL (a required failure occurred)
```

The condition "no prior mandatory failure" is **frequently omitted** in quick JAAS summaries. `SUFFICIENT` does not erase an earlier `REQUIRED`/`REQUISITE` failure.

Conversely, placing `sufficient` **too early** can open a policy hole:

```text
CachedTicket   sufficient -> PASS
PasswordCheck  required   -> NO login()

Result: PASS
```

If business rules state that password **must always be checked**, the ordering above is wrong. You cannot claim "`PasswordCheck` is marked `required`, so password is definitely mandatory" when an earlier `sufficient` is allowed to short-circuit.

### 2.4 `optional` — Neither "Forbidden" Nor "Mandatory"

An `optional` module can succeed or fail while JAAS continues:

```text
PasswordCheck  required -> PASS
OtpCheck       optional -> FAIL

Result: PASS
```

If the team intended OTP to be **mandatory**, this is a severe MFA misconfiguration. `optional` is appropriate for benign supplemental modules by design (e.g., optional environment identity enrichment), never for a critical security factor the user **must** pass.

When there are only `optional` modules:

```text
A optional -> FAIL
B optional -> PASS
=> PASS

A optional -> FAIL
B optional -> FAIL
=> FAIL
```

At least one module must succeed when no mandatory modules exist. That is an aggregation rule, **not "`optional` means always allow login."**

## 3. Visualizing the Aggregation Algorithm

To predict outcomes, you can use this conceptual model (not JDK internal source code):

```text
mandatoryFailure = false
anySuccess = false

for each LoginModule in Configuration order:
    result = module.login()

    if REQUIRED:
        success -> anySuccess = true
        failure -> mandatoryFailure = true
        always continue

    if REQUISITE:
        success -> anySuccess = true, continue
        failure -> stop login phase, overall FAIL

    if SUFFICIENT:
        success:
            anySuccess = true
            if !mandatoryFailure: finish login phase early PASS
            if mandatoryFailure: continue, overall result still FAIL
        failure -> continue

    if OPTIONAL:
        success -> anySuccess = true
        failure -> continue

after login phase:
    if mandatoryFailure: overall FAIL
    if not mandatoryFailure and enough success: overall PASS
    if no module authenticated successfully: overall FAIL

overall PASS -> commit phase
overall FAIL -> abort phase
```

This model intentionally simplifies cases where `LoginModule.login()` returns `false` (module asks to **be ignored**, see Section 8), exception precedence, and commit/abort mechanics; do not use it to re-implement a JAAS engine replacing `LoginContext`.

A quick checklist when reviewing configs:

1. Read modules **top to bottom**.
2. Flag any failed `required`/`requisite` module.
3. If a `requisite` fails: stop the login phase immediately.
4. If a `sufficient` succeeds: check whether a mandatory failure occurred **before it**; if not, modules **after it are no longer login conditions**.
5. At the end of the stack: all evaluated mandatory modules must pass; an all-`optional`/`sufficient` stack needs at least one pass.

## 4. Lab 1 — Java 17 Verifying the Eight-Case Matrix

The program below creates **an in-memory `Configuration`** without touching the machine's global JAAS config or files. It uses `ProbeModule` to simulate `login()` results from each entry's options: `pass`, `fail`, or `ignore`. The goal is to observe **which modules execute** and **the overall stack result**.

The data is mocked and **authenticates no real users**. Never use a "`behavior=pass`" trick as a production `LoginModule`. The program still implements the full `LoginModule` interface and uses a real `LoginContext` to verify behavior.

Create the file **`JaasFlagsMatrixDemo.java`**:

```java
import java.security.Principal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import javax.security.auth.Subject;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.login.AppConfigurationEntry;
import javax.security.auth.login.Configuration;
import javax.security.auth.login.LoginContext;
import javax.security.auth.login.LoginException;
import javax.security.auth.spi.LoginModule;

public class JaasFlagsMatrixDemo {
    static final List<String> CALLED = new ArrayList<>();

    static final class DemoPrincipal implements Principal {
        private final String name;
        DemoPrincipal(String name) { this.name = name; }
        public String getName() { return name; }
    }

    public static class ProbeModule implements LoginModule {
        private Subject subject;
        private String name;
        private String behavior;
        private boolean passed;
        private DemoPrincipal principal;

        public ProbeModule() {}

        public void initialize(Subject subject, CallbackHandler handler,
                Map<String, ?> sharedState, Map<String, ?> options) {
            this.subject = subject;
            name = (String) options.get("name");
            behavior = (String) options.get("behavior");
            passed = false;
        }

        public boolean login() throws LoginException {
            CALLED.add(name);
            if ("fail".equals(behavior)) {
                throw new LoginException(name + " rejected");
            }
            if ("ignore".equals(behavior)) return false;
            passed = true;
            return true;
        }

        public boolean commit() {
            if (!passed) return false;
            principal = new DemoPrincipal(name);
            subject.getPrincipals().add(principal);
            return true;
        }

        public boolean abort() {
            logout();
            passed = false;
            return true;
        }

        public boolean logout() {
            if (principal != null) subject.getPrincipals().remove(principal);
            principal = null;
            passed = false;
            return true;
        }
    }

    static AppConfigurationEntry entry(String name,
            AppConfigurationEntry.LoginModuleControlFlag flag, String behavior) {
        return new AppConfigurationEntry(ProbeModule.class.getName(), flag,
                Map.of("name", name, "behavior", behavior));
    }

    static void trial(String label, AppConfigurationEntry... stack)
            throws Exception {
        CALLED.clear();
        Configuration config = new Configuration() {
            public AppConfigurationEntry[] getAppConfigurationEntry(String name) {
                return "lab".equals(name) ? stack.clone() : null;
            }
        };
        LoginContext context = new LoginContext(
                "lab", new Subject(), (CallbackHandler) null, config);
        String result = "PASS";
        try {
            context.login();
        } catch (LoginException e) {
            result = "FAIL";
        }
        System.out.println(label + " -> " + result +
                "; login calls=" + String.join(",", CALLED));
        if ("PASS".equals(result)) context.logout();
    }

    public static void main(String[] args) throws Exception {
        var required = AppConfigurationEntry.LoginModuleControlFlag.REQUIRED;
        var requisite = AppConfigurationEntry.LoginModuleControlFlag.REQUISITE;
        var sufficient = AppConfigurationEntry.LoginModuleControlFlag.SUFFICIENT;
        var optional = AppConfigurationEntry.LoginModuleControlFlag.OPTIONAL;

        trial("required-fail-then-sufficient-pass",
              entry("A", required, "fail"),
              entry("B", sufficient, "pass"),
              entry("C", optional, "pass"));
        trial("required-pass-sufficient-pass",
              entry("A", required, "pass"),
              entry("B", sufficient, "pass"),
              entry("C", optional, "fail"));
        trial("requisite-fail-stops",
              entry("A", optional, "pass"),
              entry("B", requisite, "fail"),
              entry("C", optional, "pass"));
        trial("only-optional-one-pass",
              entry("A", optional, "fail"),
              entry("B", optional, "pass"));
        trial("only-optional-all-fail",
              entry("A", optional, "fail"),
              entry("B", optional, "ignore"));
        trial("required-pass-optional-fail",
              entry("A", required, "pass"),
              entry("B", optional, "fail"));
        trial("sufficient-before-required",
              entry("A", sufficient, "pass"),
              entry("B", required, "fail"));
        trial("sufficient-fail-required-pass",
              entry("A", sufficient, "fail"),
              entry("B", required, "pass"));
    }
}
```

Compile and run:

```bash
javac --release 17 JaasFlagsMatrixDemo.java
java JaasFlagsMatrixDemo
```

**Verified stdout on a JDK with Java 17-compatible APIs:**

```text
required-fail-then-sufficient-pass -> FAIL; login calls=A,B,C
required-pass-sufficient-pass -> PASS; login calls=A,B
requisite-fail-stops -> FAIL; login calls=A,B
only-optional-one-pass -> PASS; login calls=A,B
only-optional-all-fail -> FAIL; login calls=A,B
required-pass-optional-fail -> PASS; login calls=A,B
sufficient-before-required -> PASS; login calls=A
sufficient-fail-required-pass -> PASS; login calls=A,B
```

### 4.1 Analyzing Each Output Line

| Scenario | Module order read | Result and reason |
| --- | --- | --- |
| `required-fail-then-sufficient-pass` | A required fail, B sufficient pass, C optional pass | **FAIL**: mandatory failure in A exists; B cannot short-circuit to erase A's failure |
| `required-pass-sufficient-pass` | A required pass, B sufficient pass, C optional fail | **PASS**: B qualifies to terminate early; C is not called in the login phase |
| `requisite-fail-stops` | A optional pass, B requisite fail, C optional pass | **FAIL**: B stops the login phase immediately; C is not called |
| `only-optional-one-pass` | A optional fail, B optional pass | **PASS**: no mandatory modules and at least one optional passes |
| `only-optional-all-fail` | A optional fail, B optional returns false | **FAIL**: no module authenticated successfully |
| `required-pass-optional-fail` | A required pass, B optional fail | **PASS**: B is not mandatory |
| `sufficient-before-required` | A sufficient pass, B required would fail if called | **PASS**: B **is not called** because A terminates early; this is a misconfiguration hazard |
| `sufficient-fail-required-pass` | A sufficient fail, B required pass | **PASS**: A is not mandatory, B passes |

**Note:** the table and stdout track **`login()` invocations**. When a `sufficient` module finishes the login phase early, JAAS's second-phase lifecycle still must be resolved. Do not infer from `login calls` alone exactly how every provider invokes `commit()`/`abort()`; a `LoginModule` must behave safely even if it never reached a successful login state.

### 4.2 Explaining the Code

1. `AppConfigurationEntry` carries the class name, control flag, and options. Within one stack, the same `ProbeModule` class is reused with different names/behaviors—distinct instances are still created.
2. `Configuration#getAppConfigurationEntry("lab")` returns **entries in exact order**. The demo supplies the configuration directly through `LoginContext(..., config)` without changing JVM-wide security configuration.
3. `ProbeModule.login()` demonstrates **`true`** on success, **`LoginException`** on failure, and **`false`** when the module chooses to be ignored. Real systems must perform genuine credential/identity checks.
4. `commit()` adds a `Principal` to `Subject` only when `passed=true`. If the module did not authenticate successfully, it returns `false` to avoid adding fake identities.
5. `abort()` and `logout()` remove only the `Principal` added by this module, without deleting other modules' `Principal`s; this lifecycle must be implemented accurately to prevent state leaks.
6. `CALLED` is a static list used solely to **observe a single sequential lab process**, unsuitable as a global request trace in a multi-threaded service.

## 5. Two Phases `login/commit/abort`: Crucial Security Details

Many people read only the flag table and ignore the lifecycle. According to the `LoginModule` Developer's Guide:

**Phase 1 — attempt authentication:**
- `initialize(Subject, CallbackHandler, sharedState, options)` before module operations.
- `login()` checks credentials or state for that mechanism and records **private temporary state** (e.g., `succeeded`).
- The module should **not** prematurely publish long-lived identity/credentials to `Subject` as soon as `login()` succeeds: **other mandatory modules might still fail**.
- `login()` returns `true` if the module authenticated successfully; `false` if the module chooses to be "ignored"; or throws `LoginException` if authentication failed.

**Phase 2 — finalize or abort:**
- If overall evaluation succeeds, `LoginContext` invokes `commit()` on the modules per lifecycle: succeeding modules add allowed `Principal`s/credentials to `Subject`.
- If overall evaluation fails, `abort()` is invoked to discard temporary login state, wipe short-lived passwords/tokens, and prevent state leaks.
- If `commit()` fails in one module, the engine handles failure/abort; the module itself must perform complete cleanup.
- After a successful session, `LoginContext.logout()` invokes `logout()` to remove only identities/credentials **added by that module**, leaving other modules' entries untouched.

```text
Module A.login() PASS ---+
                         |
Module B.login() FAIL ---+--> Overall FAIL
                         |
                         v
                 abort() / cleanup
                 (DO NOT publish an authenticated Subject)
```

```text
Module A.login() PASS ---+
                         |
Module B.login() PASS ---+--> Overall PASS
                         |
                         v
                       commit()
                         |
                         v
                   Subject Principals
                         |
                         v
                       logout()
                         |
                         v
                Clean up added identity/credentials
```

**Never call `module.commit()` manually to "rescue" a failing stack.** The two-phase protocol protects identity consistency across multiple modules and enables rollback.

### 5.1 Do Not Confuse Returning `false` from `LoginModule.login()` with Throwing an Exception

By the `LoginModule` interface:

- `return true`: module authenticated successfully.
- `return false`: module asks to be **ignored**, not a way to report that a credential check failed.
- `throw new LoginException(...)`: module reports **authentication failed**.

Because flags evaluate module results, **never** replace throwing `LoginException` with `return false` in a module enforcing mandatory policy. Declaring itself ignored has different semantics from an explicit failure and can produce unexpected aggregation outcomes.

Follow the contract of real modules/providers and write unit/integration tests for all three return behaviors. Never write `catch (Exception ignored) { return true; }` or swallow network/credential errors and let JAAS pass.

### 5.2 Which Identities Should `Subject` Hold After Login?

`Subject` holds `Principal`, public credential, and private credential sets. Each module may contribute identities (account ID, realm, verified roles, etc.) in `commit()` if that module genuinely succeeded.

Two issues:

- **Conflicting identity**: if a password module authenticates user A while a token module authenticates user B and both pass, the system must not treat them as the same entity. Enforce identity/tenant/session binding across modules.
- **Privilege pollution**: if an unrequired module adds roles/permissions loosely, `Subject` may carry Principals stronger than the evidence warrants. Separate **identity authentication** from policy-based **operation authorization**.

A `Principal` is just an identity object. Simply having `Principal("admin")` inside `Subject` is not an access grant if the application does not verify its source and authorization rules.

## 6. AND versus OR: Choosing Flags to Express Policy

### 6.1 AND Policy — Must Pass Multiple Conditions

For example, an application requiring **both password and OTP**:

```text
PasswordModule required
OtpModule      required
```

Overall login passes only if **both** pass. If either fails, the login is rejected, though `required` lets the subsequent module still run. If you want to stop immediately when password fails to avoid wasted OTP requests (trading off timing uniformity), you can use:

```text
PasswordModule requisite
OtpModule      required
```

Both remain mandatory when evaluated in order. However, **placing a `sufficient` before mandatory steps** can accidentally turn "AND" into OR.

### 6.2 OR Policy — One Trusted Mechanism May Suffice

For instance, an application might authenticate via **either of two alternative mechanisms**, if policy permits:

```text
KerberosTicketModule sufficient
FallbackPasswordModule required
```

If the ticket is valid, the stack can finish early without checking the password; if the ticket is invalid, the password module becomes the mandatory fallback. Use this only when **both mechanisms have been independently vetted by your organization as providing equivalent security**, never allowing a weak factor to bypass a strong factor.

Never treat "`sufficient` == MFA passed" or "`required` is skipped because another mechanism exists" as a general rule. Any bypass path must be explicitly documented in your threat model and tested.

### 6.3 Where Should an "Audit" Module Live?

If auditing/logging is a **mandatory action**, do not rely on an `AuditModule optional` placed after a `SufficientModule`: the audit module might never have `login()` called when `sufficient` short-circuits. Centralized auditing at the orchestration layer around `LoginContext.login()` or a dedicated event pipeline is usually better, and must be tested for early-termination and failure paths.

Because `LoginModule` is designed for authentication, stuffing arbitrary side effects like auditing, provisioning, or billing into login callbacks can cause control flags to alter their behavior unexpectedly.

## 7. Lab 2 — Demonstrating MFA Bypass When OTP Becomes OPTIONAL

The lab below uses two `LoginModule`s:

1. `PasswordModule` simulates verifying a fixed username/password for a **lab user**.
2. `OtpModule` simulates checking a fixed OTP in memory **solely to illustrate control flags**, without implementing real TOTP/HOTP or replay defenses.

Both modules share one `Subject`, `CallbackHandler`, and `sharedState`. `PasswordModule` writes the **non-secret username** into shared state after verification; `OtpModule` reads this username and checks the OTP. Never put passwords, OTPs, or MFA keys into shared state carelessly.

The program tests three configurations:

- Password required, OTP required, valid code → **PASS** with two Principals.
- Password required, OTP required, wrong code → **FAIL**.
- Password required, OTP **optional**, wrong code → **PASS** with **one** Principal: proving that `optional` does not enforce MFA.

**Security notice:** the fixed password `lab-pass` and OTP `123456` are for lab use only. `Arrays.equals` on demo password arrays does not replace password KDFs like PBKDF2/Argon2id in production. This lesson covers **JAAS orchestration**, not building production password or OTP systems.

### 7.1 Java 17 Code `JaasTwoFactorPolicyDemo.java`

```java
import java.security.Principal;
import java.util.Arrays;
import java.util.Map;
import java.util.Set;
import javax.security.auth.Subject;
import javax.security.auth.callback.*;
import javax.security.auth.login.*;
import javax.security.auth.spi.LoginModule;

public class JaasTwoFactorPolicyDemo {
    public record UserPrincipal(String name) implements Principal {
        public String getName() { return name; }
    }
    public record FactorPrincipal(String name) implements Principal {
        public String getName() { return name; }
    }

    public static class PasswordModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private Map<String, Object> shared;
        private boolean success;
        private Principal added;

        @SuppressWarnings("unchecked")
        public void initialize(Subject subject, CallbackHandler handler,
                Map<String, ?> sharedState, Map<String, ?> options) {
            this.subject = subject;
            this.handler = handler;
            this.shared = (Map<String, Object>) sharedState;
        }

        public boolean login() throws LoginException {
            NameCallback name = new NameCallback("Username");
            PasswordCallback password = new PasswordCallback("Password", false);
            char[] typed = null;
            try {
                handler.handle(new Callback[] {name, password});
                typed = password.getPassword();
                char[] demoExpected = "lab-pass".toCharArray();
                boolean match = "student".equals(name.getName()) &&
                        typed != null && Arrays.equals(typed, demoExpected);
                Arrays.fill(demoExpected, '\0');
                if (!match) throw new LoginException("Password factor rejected");
                shared.put("user", name.getName()); // Do not put secrets into shared state
                success = true;
                return true;
            } catch (Exception ex) {
                if (ex instanceof LoginException le) throw le;
                throw new LoginException("Callback failed");
            } finally {
                if (typed != null) Arrays.fill(typed, '\0');
                password.clearPassword();
            }
        }

        public boolean commit() {
            if (!success) return false;
            added = new UserPrincipal((String) shared.get("user"));
            subject.getPrincipals().add(added);
            return true;
        }

        public boolean abort() { return logout(); }

        public boolean logout() {
            if (added != null) subject.getPrincipals().remove(added);
            added = null;
            success = false;
            if (shared != null) shared.remove("user");
            return true;
        }
    }

    public static class OtpModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private Map<String, ?> shared;
        private boolean success;
        private Principal added;

        public void initialize(Subject subject, CallbackHandler handler,
                Map<String, ?> sharedState, Map<String, ?> options) {
            this.subject = subject;
            this.handler = handler;
            this.shared = sharedState;
        }

        public boolean login() throws LoginException {
            if (!"student".equals(shared.get("user"))) {
                throw new LoginException("Password factor must succeed first");
            }
            TextInputCallback input = new TextInputCallback("Demo OTP");
            try { handler.handle(new Callback[]{input}); }
            catch (Exception ex) { throw new LoginException("OTP callback failed"); }
            if (!"123456".equals(input.getText())) {
                throw new LoginException("OTP factor rejected");
            }
            success = true;
            return true;
        }

        public boolean commit() {
            if (!success) return false;
            added = new FactorPrincipal("otp");
            subject.getPrincipals().add(added);
            return true;
        }

        public boolean abort() { return logout(); }

        public boolean logout() {
            if (added != null) subject.getPrincipals().remove(added);
            added = null;
            success = false;
            return true;
        }
    }

    static final class Inputs implements CallbackHandler {
        private final String user, password, otp;

        Inputs(String user, String password, String otp) {
            this.user = user; this.password = password; this.otp = otp;
        }

        public void handle(Callback[] callbacks) throws UnsupportedCallbackException {
            for (Callback cb : callbacks) {
                if (cb instanceof NameCallback nc) nc.setName(user);
                else if (cb instanceof PasswordCallback pc)
                    pc.setPassword(password.toCharArray());
                else if (cb instanceof TextInputCallback tc) tc.setText(otp);
                else throw new UnsupportedCallbackException(cb);
            }
        }
    }

    private static void test(String label, String otp,
            AppConfigurationEntry.LoginModuleControlFlag otpFlag)
            throws Exception {
        Configuration config = new Configuration() {
            public AppConfigurationEntry[] getAppConfigurationEntry(String name) {
                if (!"twoFactor".equals(name)) return null;
                return new AppConfigurationEntry[]{
                    new AppConfigurationEntry(PasswordModule.class.getName(),
                        AppConfigurationEntry.LoginModuleControlFlag.REQUIRED, Map.of()),
                    new AppConfigurationEntry(OtpModule.class.getName(),
                        otpFlag, Map.of())
                };
            }
        };

        LoginContext context = new LoginContext(
            "twoFactor", new Subject(),
            new Inputs("student", "lab-pass", otp), config);
        try {
            context.login();
            System.out.println(label + ": PASS, principals=" +
                    context.getSubject().getPrincipals().size());
            context.logout();
            System.out.println(label + ": after logout=" +
                    context.getSubject().getPrincipals().size());
        } catch (LoginException e) {
            System.out.println(label + ": FAIL");
        }
    }

    public static void main(String[] args) throws Exception {
        test("both-required-correct-otp", "123456",
                AppConfigurationEntry.LoginModuleControlFlag.REQUIRED);
        test("both-required-wrong-otp", "000000",
                AppConfigurationEntry.LoginModuleControlFlag.REQUIRED);
        test("otp-optional-wrong-otp", "000000",
                AppConfigurationEntry.LoginModuleControlFlag.OPTIONAL);
    }
}
```

Compile and run:

```bash
javac --release 17 JaasTwoFactorPolicyDemo.java
java JaasTwoFactorPolicyDemo
```

**Compiled and verified output:**

```text
both-required-correct-otp: PASS, principals=2
both-required-correct-otp: after logout=0
both-required-wrong-otp: FAIL
otp-optional-wrong-otp: PASS, principals=1
otp-optional-wrong-otp: after logout=0
```

### 7.2 Why Does Changing One Flag Break MFA Policy?

In the OTP `REQUIRED` case, when the OTP is wrong, `OtpModule.login()` throws `LoginException`. Even though the password module passed, the entire `LoginContext.login()` must fail. `PasswordModule.abort()` runs to wipe temporary state—the `Subject` is never treated as two-factor authenticated.

When OTP is `OPTIONAL`, an OTP failure is non-mandatory. Because `REQUIRED` password passed, the overall stack **can PASS**. The `Subject` then has `UserPrincipal` yet **lacks `FactorPrincipal("otp")`** (stdout shows one Principal). If the application grants MFA-level privileges merely because `LoginContext.login()` succeeded, it has created an OTP bypass.

**Remediation:** if MFA is genuinely mandatory, express it with `REQUIRED`/`REQUISITE` or equivalent non-bypassable orchestration policy, and enforce a rule that grants "MFA-complete" access only with sufficient evidence. Do not paper over the bug with "OTP is optional, and login code guesses afterward whether the user entered a code" without clear authorization policy.

### 7.3 Key Takeaways from the Code

- `LoginContext(..., config)` accepts an isolated `Configuration`, avoiding a global file and avoiding altering other applications' JAAS setups.
- `CallbackHandler` passes username/password/OTP to modules via their corresponding `Callback` types; never log credentials.
- `sharedState` is written by `PasswordModule` **after verification**, then read by `OtpModule`. The demo enforces Password-before-OTP order; reversing it leaves `OtpModule` without a user.
- `commit()` adds meaningful `Principal`s to `Subject` only after the overall stack passes.
- `logout()` removes only Principals added by the module. Stdout `after logout=0` verifies cleanup in the lab.
- Real implementations must use standard password hashing, TOTP/HOTP/WebAuthn with replay/rate-limit checks, a real user source of truth, and session-bound MFA; never use fixed codes or immutable `String`s holding secrets as in the demo.
- When multiple modules verify multiple factors, **bind all evidence to the same principal/session**; never allow account A's password combined with account B's OTP to count as MFA for one user.

## 8. File-Based JAAS Configuration vs. Programmatic Configuration

### 8.1 File Configuration

You can supply a configuration file to the JDK via the property:

```bash
java -Djava.security.auth.login.config=jaas.conf MyApplication
```

This is a **configuration command template**, which does not run standalone without a `jaas.conf` file and `MyApplication` class. Security configuration loading can vary by framework/container.

Example `jaas.conf` **referencing the actual classes implemented in the second demo** (classes must be on the classpath):

```text
twoFactor {
    JaasTwoFactorPolicyDemo$PasswordModule required;
    JaasTwoFactorPolicyDemo$OtpModule      required;
};
```

With this configuration, the application would call `new LoginContext("twoFactor", handler)` with a `CallbackHandler` supplying username/password/OTP; the demo source above uses a programmatic `Configuration`, so it **does not read this file** when running `JaasTwoFactorPolicyDemo.main`. To use the config file, the caller must not pass a custom `Configuration` to the constructor.

**Watch out:** the module name is the **binary class name** (`Outer$Nested`), not the source-code `Outer.Nested`; that is why the config above uses `$`. In real systems, use classes with clear package namespaces, such as `com.company.auth.PasswordLoginModule` and `com.company.auth.OtpLoginModule`, rather than the demo's default package.

Never put credentials, passwords, or private keys in `ModuleOptions` inside the config file. Options are suitable for non-secret parameters such as realms, controlled debug modes, or protected endpoint identifiers.

### 8.2 Programmatic `Configuration`

Both demos above use:

```java
Configuration config = new Configuration() {
    public AppConfigurationEntry[] getAppConfigurationEntry(String name) {
        return "lab".equals(name) ? stack.clone() : null;
    }
};
LoginContext ctx = new LoginContext(
        "lab", new Subject(), handler, config);
```

This is an API-explaining snippet requiring `stack` and `handler` variables. This approach is useful for testing **many flag combinations** in one process, giving each test an isolated configuration without mutating global `Configuration.setConfiguration(...)`.

Also, when using an installed configuration via `Configuration.getConfiguration()`, an unknown application name may fall back to the `other` entry if defined; if no matching entry exists, `LoginContext` throws `LoginException`. Do not make `other` overly permissive, because a typo in `appName` could route requests to a **weaker stack than intended**.

### 8.3 Ordering and Reloading Configurations

`Configuration` controls entry order strictly according to the list. Different applications/realms can have different policies. Any change to a flag or module position deserves code review just like a security policy change:

- Never place a weak `sufficient` mechanism ahead of a business-mandatory `required` factor.
- Never downgrade `required` to `optional` just to reduce login failures during upstream outages if that factor is a security requirement.
- When implementing fallbacks, distinguish **approved alternative fallbacks** from **bypassing mandatory conditions**.
- If configs come from files/DB/config services, protect write permissions, versioning/approval, and reload behavior; never let users pick a weaker configuration via a request parameter.

## 9. `CallbackHandler`, Options, and `sharedState`: Safe Coordination

### 9.1 `CallbackHandler` and Sensitive Data

`CallbackHandler` is the boundary between the application/UI and modules. Common JAAS callbacks:

| Callback | Purpose | Note |
| --- | --- | --- |
| `NameCallback` | Username | Do not trust the name value until verified |
| `PasswordCallback` | Password `char[]` array | Use `getPassword()` and `clearPassword()`; avoid unnecessary `String` copies |
| `TextInputCallback` | Auxiliary text such as demo OTP | Illustrative only; real secrets need dedicated memory/log protection policies |
| `ConfirmationCallback` | User confirmation prompt | Not equivalent to cryptographic authentication proof |
| `UnsupportedCallbackException` | Handler does not support callback | Fail authentication per policy; never pass silently |

Never put passwords/tokens into logs, traces, exception messages, or long-lived `sharedState`. Passwords must be verified via a dedicated secure method; `PasswordCallback` is only an input-passing mechanism, not a substitute for password hashing/KDF or rate limiting.

### 9.2 `sharedState` Across Multiple Modules

`initialize` receives:

```java
public void initialize(
    Subject subject,
    CallbackHandler handler,
    Map<String, ?> sharedState,
    Map<String, ?> options)
```

This is a **snippet-level** method signature inside a class implementing `LoginModule`. `sharedState` allows modules in one `LoginContext` invocation to share state, while `options` holds per-entry configuration.

Key considerations:

- Store only values genuinely needing sharing; avoid passwords/OTPs/raw credentials.
- Define **who is authorized to write** a key and how readers validate its provenance.
- Never use `sharedState` to skip verification: downstream modules must verify strong outcomes/identities, not blindly trust an arbitrary `"authenticated"` flag key.
- Clean up in `abort`/`logout` so stale data does not linger across retries or reuse.
- Module order determines what data is already present in shared state when another module runs.
- When combining Kerberos/SSO modules with passwords, verify identity consistency; mismatched principals from two sources must not be merged automatically.

### 9.3 Exceptions and Error Messages

A `requisite` module can stop early, whereas `required` continues to subsequent modules even after failure. This can produce observable differences in timing or side effects:

```text
A requisite -> FAIL:  B, C do not call login
A required  -> FAIL:  B, C can still call login
```

Choosing flags **does not replace** account-enumeration defenses, rate limiting, auditing, and generic error messages. If an app returns "wrong OTP" differently from "wrong password," attackers learn account state. Keep external errors uniform, classify causes in controlled internal audit logs, and ensure no failure branch ever issues a session.

## 10. When to Use `REQUIRED`, `REQUISITE`, `SUFFICIENT`, `OPTIONAL`?

| Requirement | How to choose flags | Warning |
| --- | --- | --- |
| Must require both password and OTP | Both `required`, or `requisite`/`required` in a sensible order | Never make OTP `optional` or bypassable by an earlier `sufficient` |
| Either SSO or Password **vetted as equivalent** suffices | `sufficient` for the preferred method, appropriate fallback | Verify strength/issuer/tenant; never assume every SSO is strong enough |
| Mandatory pre-check needed before expensive work | `requisite` upfront | Evaluate timing/side-effect differences and `abort` behavior |
| Non-decisive enrichment step | `optional` | Never let it arbitrarily add sensitive privileges |
| Mandatory check while still running remaining modules to reduce failure-point leakage | `required` | Still enforce timeouts and cost bounds |
| Mandatory audit/telemetry even on early login success | Handle outside the stack or via a dedicated guaranteed audit mechanism | An `optional` after `sufficient` may skip `login()` |
| Multiple identity sources in one session | Stack with explicit identity-binding rules | One passing Principal does not mean different modules verified the same person |

No flag by itself solves authorization, phishing-resistant MFA, or credential storage. These flags only govern **control flow and aggregation across multiple `LoginModule`s**.

## 11. Test Matrix Before Shipping a Configuration to Production

Do not test only "right password" and "wrong password." At a minimum include:

1. **One `required` fails, other `optional`/`sufficient` pass:** entire stack must fail.
2. **`requisite` fails mid-stack:** downstream modules are not invoked in the login phase; temp state is cleaned.
3. **`sufficient` passes before a mandatory module:** verify downstream mandatory modules **are skipped** and confirm whether that matches desired policy.
4. **`sufficient` passes after a mandatory pass:** skips unneeded remaining steps and still passes.
5. **`sufficient` fails then `required` passes:** valid fallback if business rules permit.
6. **Only `optional`, at least one passes:** passes.
7. **Only `optional`, all fail/ignore:** fails.
8. **`required` passes, `optional` fails:** passes—for critical security modules, this may be a policy flaw.
9. **Two factors both `required`, wrong OTP:** fails and grants no MFA principal.
10. **OTP misconfigured as `optional`:** tests must catch this if MFA is mandatory.
11. **`login` succeeded, later module's `commit` fails:** `abort`/cleanup removes added state/Principals properly.
12. **Login failed at the final module:** no leaked tokens, password buffers, sessions, or Principals across retries.
13. **`logout` after success:** removes only credentials/Principals added by the right module; preserves other modules' data.
14. **`CallbackHandler` missing a callback:** fails per policy, never silently returns true or accepts null data.
15. **Two modules verify different identities:** reject or explicitly reconcile per policy; never blindly merge privileges.
16. **Wrong config name / `other` fallback:** never accidentally route to a weak realm.
17. **Config ordering changes/rollouts:** snapshot tests ensure strong policies are not weakened by reordering.
18. **Concurrency:** never share mutable `LoginContext`/`LoginModule`/static `sharedState` across independent sessions.
19. **Timeout/upstream unavailable:** never automatically downgrade a mandatory module to `optional`.
20. **Audit/logging:** all success/failure/short-circuit paths emit investigable events without leaking secrets.

**The security of a stack is the security of every path that can succeed**, not simply a config that "has `required` on a few lines." An early-succeeding `sufficient` can create a login path that skips mandatory checks at the end.

## 12. Common Misconceptions

| Misconception | Accurate explanation |
| --- | --- |
| "When `required` fails, Java stops immediately." | No; it continues running later modules, though the overall stack ultimately fails. |
| "`requisite` is completely identical to `required`." | Both are mandatory, but a `requisite` failure **halts the login phase immediately**. |
| "A passing `sufficient` always wins, even if an earlier `required` failed." | No; a prior mandatory failure still causes overall failure. |
| "A `required` at the end of the file will always run." | Not necessarily: an earlier succeeding `sufficient` can short-circuit. |
| "`optional` has no effect." | Optional success can produce an overall pass when no mandatory modules exist; it can also add Principals on commit. |
| "All `optional` failing still passes." | No; without mandatory modules, at least one `optional`/`sufficient` must succeed. |
| "An `optional` OTP enforces MFA because the UI shows an OTP box." | False; a passing `required` password suffices to pass the whole stack if OTP is `optional` and fails. |
| "Returning `false` from `LoginModule.login` is the same as throwing `LoginException`." | No; `false` means ignored per contract, whereas an exception reports failure. |
| "Write roles into `Subject` as soon as a module passes." | Wait for `commit` after overall pass to avoid publishing identities from a failing stack. |
| "A `Subject` containing an admin `Principal` has admin permissions." | No; permissions depend on policy, trusted Principal provenance, and authorization. |
| "`sufficient` short-circuits, so `abort`/`commit` are unneeded." | The login phase stops early, yet second-phase state lifecycle still must be handled cleanly. |
| "When `requisite` fails, cleanup does not run." | False: the `abort` phase is still responsible for cleaning up state. |
| "Modules share `sharedState`, so any key in it can be trusted." | No; verify provenance, scope, and identity binding. |
| "A global static trace list works in a multi-user server." | No; the demo runs sequentially, whereas production needs per-request/login-context tracing. |
| "Setting `required` on multiple modules makes MFA phishing-resistant." | No; phishing resistance depends on factor type, replay defenses, session binding, and policy. |
| "Changing config is not changing code, so no security review is needed." | False; reordering or changing a single flag can rewrite the entire login policy. |

## 13. Self-Check Questions

**1.** How do `required` and `requisite` differ when they fail?  
**Answer:** Both cause overall failure; `required` **continues** to subsequent modules, while `requisite` **halts the login phase immediately**.

**2.** An earlier `required` failed, and a later `sufficient` succeeds. Does login succeed?  
**Answer:** No. The prior mandatory failure was not cleared, so overall login still fails.

**3.** A succeeding `sufficient` sits before a `required`. Does the downstream `required` module run?  
**Answer:** Not during the login phase if the `sufficient` validly short-circuits. Thus placement can create a bypass.

**4.** There are two `optional` modules; one fails and one passes. What is the overall result when no mandatory modules exist?  
**Answer:** Pass, because at least one module authenticated successfully.

**5.** Both `optional` modules fail/ignore, with no `required`/`requisite`; does it succeed?  
**Answer:** No; there was no successful authentication.

**6.** If `required` password passes and `optional` OTP fails, can the application log in successfully?  
**Answer:** Yes; that is why `optional` must never be used for a mandatory MFA factor.

**7.** What is `commit()` used for?  
**Answer:** Finalizing the identities/credentials of succeeding modules once the **overall** login phase meets policy conditions.

**8.** When is `abort()` called?  
**Answer:** When overall authentication fails or state must be rolled back; it clears temporary state and reverts changes per contract.

**9.** How do `CallbackHandler` and `sharedState` differ?  
**Answer:** A handler is the interface for requesting/providing input, whereas `sharedState` is a map exchanging state **between modules inside the same `LoginContext`**.

**10.** What should `LoginContext.logout()` do to `Subject`?  
**Answer:** Modules clean up Principals/credentials added **by that module itself**, without deleting other modules' resources.

**11.** If one module authenticates user A and another authenticates user B and both pass, should their privileges be combined?  
**Answer:** No. Bind to the exact same identity/session and enforce authorization policy.

**12.** Why must changing a JAAS flag from `required` to `optional` undergo security review?  
**Answer:** Because it changes the login success condition and can turn a mandatory factor into an optional one.

## Summary

```text
required  = mandatory; on failure still runs login() on later modules
requisite = mandatory; on failure halts login() immediately
sufficient= not mandatory; pass may short-circuit early if
            no prior required/requisite failure occurred
optional  = not mandatory; always continues to later modules

If no required/requisite exists:
    at least one sufficient/optional must succeed

JAAS authentication lifecycle:
    login() modules in config order
                |
       aggregate flags/result
        /                \
     success             failure
       |                    |
     commit()             abort()
       |
     Subject/Principal
       |
     logout()

Security depends on:
    flags + ORDER + identity binding + cleanup + policy.
```

**Conclusion:** the four control flags are not merely labels indicating a module's "importance"; they govern **the control flow of the entire login process**. `REQUIRED` and `REQUISITE` enforce mandatory conditions, `SUFFICIENT` expresses a mechanism **enough to terminate early**, and `OPTIONAL` cannot enforce a mandatory MFA factor. To get it right, **test both success/failure branches and module ordering**, rather than reading a single config line in isolation.

## Official References

- [Java SE 17 — Configuration API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/Configuration.html): exact definition of the four flags, aggregation rules, and module ordering.
- [Java SE 17 — AppConfigurationEntry.LoginModuleControlFlag](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/AppConfigurationEntry.LoginModuleControlFlag.html): constants `REQUIRED`, `REQUISITE`, `SUFFICIENT`, `OPTIONAL`.
- [Java SE 17 — LoginContext API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/login/LoginContext.html): stacked authentication, `login`, `getSubject`, `logout`, configuration, and `CallbackHandler`.
- [Java SE 17 — LoginModule API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/spi/LoginModule.html): `initialize`, `login`, `commit`, `abort`, `logout`.
- [Oracle — JAAS LoginModule Developer's Guide (Java 17)](https://docs.oracle.com/en/java/javase/17/security/java-authentication-and-authorization-service-jaas-loginmodule-developers-guide1.html): two phases, return values, cleanup, and `Subject`.
- [Java SE 17 — Subject API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/Subject.html): Principals/credentials and subject lifecycle.
- [Java SE 17 — NameCallback / PasswordCallback](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/security/auth/callback/package-summary.html): callback framework and login input handling.
