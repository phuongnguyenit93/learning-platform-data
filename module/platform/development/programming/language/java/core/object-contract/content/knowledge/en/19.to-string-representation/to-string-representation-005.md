# Never Include Passwords, Tokens, or Sensitive Data in `toString()` Representations

## 1. Why Is `toString()` an Easy Point of Information Leakage?

`Object.toString()` returns a string representation of an object. Classes often override `toString()` to help developers read logs, error messages, or debugging output more quickly. However, **the representation string can leave the controlled scope**: it can be written to logs, forwarded to observability services, stored in error reports, displayed on support screens, or shared during incident handling.

For example, a login object might have `accountId`, `password`, and `accessToken` fields. A `toString()` that lists every field will accidentally disclose credentials when someone prints the object to trace an execution flow. Passwords and tokens can grant access to an account or system once leaked; even access-restricted logs may be copied, retained for a long time, or accessed by more components than the original secret-handling scope.

**Default principle:** `toString()` serves **diagnosis**, not dumping the entire state. Only include attributes **determined to be safe for logging**. Never put passwords, secrets, private keys, or access token values into the representation string.

How to define a good representation:

- Readers can recognize the **object type** and **sufficient context for diagnosis**.
- The string does not contain credentials or personal data beyond the permitted purpose.
- If sensitive fields are added to the class later, the representation does not automatically expose the new fields.
- The representation has a stable, concise, understandable format and does not contain uncontrolled input data that could break log structure.

## 2. Types of Data That Should Not Be Printed in `toString()`

Depending on the application and data classification, the following categories typically need to be excluded from the representation:

| Data Category | Examples | Risk When Exposed in the Representation |
| --- | --- | --- |
| Passwords, PINs, OTPs, and recovery codes | `password`, `pin`, `oneTimeCode` | Can be used to authenticate or take over access |
| Authentication and session tokens | Access token, refresh token, session cookie, bearer token | Can be reused to access sessions or APIs |
| Technical keys and secrets | API key, client secret, private key, connection strings containing passwords | Grants access to services, signing/decryption, or unauthorized connections |
| Sensitive headers/queries | `Authorization`, `Cookie`, URLs with tokens in query strings | Secret values can leak through HTTP logs or exceptions |
| Personal information | Email, phone number, address, identity documents, financial or health data | Can violate privacy or exceed permitted data usage |
| Request/response bodies | JSON containing account details, profiles, payment information | Can accidentally pull in a whole set of sensitive fields |

Not every `id`, email, or reference number is permitted for output. An identifier can be personal information or a secret in a specific context. If you need to correlate events, prefer a **correlation ID specifically designed for system observability**, carrying no access capability and approved for logging.

Do not assume only raw passwords are secrets. Password hashes, verification codes, expired tokens, test keys, "partial" values, or identifying documents can still be sensitive. Policy decisions must be based on intended use and risk level, not solely on field names.

## 3. `toString()` Can Be Called Indirectly

A developer may never write `object.toString()` yet still cause the representation to be used:

~~~java
System.out.println(object);              // Calls the object's string representation.
String message = "Request: " + object;    // String concatenation uses the representation.
String text = String.format("%s", object);
String display = String.valueOf(object);
~~~

These are **illustrative snippets**, assuming the `object` variable is already declared. With some parameterized logging APIs, such as calls like `logger.info("request={}", request)` in popular libraries, the formatter may convert arguments to strings when logging. Deferring formatting or checking log levels can affect evaluation timing, but **it does not make `request.toString()` safe** when the message is actually written.

Other paths can also invoke the representation indirectly: building an exception string, recording values in assertion messages, rendering an object on an admin page, or capturing snapshots for incident investigation.

**What to avoid is putting the entire secret-bearing object into messages**, especially when you do not control how it is converted to a string. Instead of logging `request`, log permitted fields such as action type, processing outcome, and a classified correlation ID.

## 4. The `record` Trap: Auto-Generated `toString()` Includes Every Component

Since Java 16, a `record` has synthesized `equals()`, `hashCode()`, and `toString()` methods if you do not declare them yourself. The generated `toString()` displays the record name along with its **components** and corresponding values. Thus using a record for data containing secrets still carries a leakage risk, even if you never write a single line of `toString()` manually.

### Runnable Example: Detecting the Risk Without Printing Secret Values

Create the file `UnsafeRecordToStringDemo.java`:

~~~java
public class UnsafeRecordToStringDemo {
    record LoginData(String accountId, String password, String accessToken) {}

    public static void main(String[] args) {
        // Use synthetic strings only to test behavior; never put real secrets in code.
        LoginData login = new LoginData(
                "account-demo",
                "example-password",
                "example-token"
        );

        String rendered = login.toString();

        // Print only check results; DO NOT print rendered or the secrets.
        System.out.println("contains account: "
                + rendered.contains(login.accountId()));
        System.out.println("contains password: "
                + rendered.contains(login.password()));
        System.out.println("contains token: "
                + rendered.contains(login.accessToken()));
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 UnsafeRecordToStringDemo.java
java UnsafeRecordToStringDemo
~~~

Stdout:

~~~text
contains account: true
contains password: true
contains token: true
~~~

The example intentionally leaves the record with its default `toString()` **in order to detect the issue**, while not printing the password/token values. The `true` results show that if any code calls `System.out.println(login)` or concatenates `"login=" + login`, the representation string will carry those values into the output.

Besides `record`, IDEs or code generators can create `toString()` based on all fields or components. When adding fields, re-running a generator, or enabling auto-generation, you must verify the policy for excluding sensitive fields.

## 5. A Safer Strategy: Explicitly Choose Permitted Fields for Output

The safe way to write `toString()` for an object with secrets is an **allowlist**: list only the attributes permitted to appear, instead of concatenating all fields and trying to filter out forbidden ones.

For example, a processing session contains a request ID and two secrets. If the request ID has been designed as a non-sensitive diagnostic code, we can print that code and a fixed label without touching the secret values.

Create the file `SafeSessionToStringDemo.java`:

~~~java
public class SafeSessionToStringDemo {
    record SessionData(String requestId, String password, String accessToken) {
        @Override
        public String toString() {
            return "SessionData[requestId=" + requestId
                    + ", credentials=<redacted>]";
        }
    }

    public static void main(String[] args) {
        SessionData session = new SessionData(
                "req-42",
                "example-password",
                "example-token"
        );

        String representation = session.toString();
        System.out.println(representation);
        System.out.println("contains password: "
                + representation.contains(session.password()));
        System.out.println("contains token: "
                + representation.contains(session.accessToken()));
        System.out.println("same object identity: "
                + (session == session));
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeSessionToStringDemo.java
java SafeSessionToStringDemo
~~~

Stdout:

~~~text
SessionData[requestId=req-42, credentials=<redacted>]
contains password: false
contains token: false
same object identity: true
~~~

This is a complete example with synthetic data, using a **fixed** `<redacted>` label to indicate that secrets were excluded from the representation. Do not build the label by concatenating or slicing an actual part of the token for display.

Benefits of an allowlist:

1. Readers know exactly which fields are exposed.
2. Sensitive fields `password` and `accessToken` are never accessed in the `toString()` body.
3. When a new secret is added to the record, the custom `toString()` **does not automatically output that secret**.
4. The output is short, meaningful, and convenient for logs, provided `requestId` has genuinely been classified as safe.

In a real environment, verify that the `requestId` value also does not contain secrets or user-supplied strings. If unsure, exclude that field too or use a system-generated correlation ID.

**Note:** Overriding `toString()` only changes the string representation. It does not remove the password/token from the object, does not block accessor methods, does not protect JSON/XML serialization, and does not solve secret-storage rules on its own. Default records still generate `equals/hashCode` based on components unless those methods are implemented manually; they serve a different purpose from logging policies.

## 6. Why Asterisk Masking Is Not Enough if Secrets Still Flow Through Logs

Some common "masking" approaches can still leak data:

~~~java
// The following snippets are design anti-patterns; do not use them to log secrets.
String partiallyVisible = token.substring(0, 6) + "***";
String suffix = "***" + token.substring(token.length() - 4);
String encoded = java.util.Base64.getEncoder()
        .encodeToString(token.getBytes(java.nio.charset.StandardCharsets.UTF_8));
~~~

These snippets are **illustrative fragments**, assuming `token` is a non-null string long enough for both slices. In real programs, `substring` calls can also throw errors on overly short tokens; what is notable is:

- Token prefixes/suffixes can still be sensitive or help correlate a specific token with user activity.
- Base64 is **representation encoding**, not cryptographic encryption or data erasure; it is reversible.
- Directly hashing a secret and writing the hash to logs still creates a fixed correlation value that can reveal relationships across events or aid guessing without a proper threat model.
- Global string-pattern replacement after a secret has already been concatenated into a log easily misses paths, new formats, or sensitive values nested deep inside objects.

In `toString()`, it is best **not to reference secret values at all**. If there is a very specific requirement to display status (such as `configured`/`absent`), do so only after it is assessed as safe, because even the presence of credentials can sometimes be sensitive information.

There is no need to print a prefix, suffix, token length, or authentication state if the goal is only to identify which request was processed. Use an independent diagnostic identifier instead.

## 7. Leakage Through Nested Objects, Collections, and `Map.toString()`

Omitting a direct secret field is not enough if the outer class's `toString()` **calls `toString()` on a child object** that holds a secret.

Example:

~~~java
record Credential(String token) {}
record Request(String requestId, Credential credential) {}
~~~

If both keep the default `toString()`, `Request`'s representation contains `Credential`'s representation, and `Credential` contains the token value. Similarly, writing `return "Request{headers=" + headers + "}";` can invoke `Map.toString()` and print entries like `Authorization` or `Cookie`. `List.toString()` can also trigger each element's `toString()`.

### Runnable Example: Demonstrating Indirect Leakage

Create the file `NestedToStringDemo.java`:

~~~java
public class NestedToStringDemo {
    record Credential(String token) {}
    record UnsafeRequest(String requestId, Credential credential) {}

    record SafeRequest(String requestId, Credential credential) {
        @Override
        public String toString() {
            return "SafeRequest[requestId=" + requestId + "]";
        }
    }

    public static void main(String[] args) {
        Credential credential = new Credential("example-token");
        UnsafeRequest unsafe = new UnsafeRequest("req-9", credential);
        SafeRequest safe = new SafeRequest("req-9", credential);

        // Print only check booleans; do not output the unsafe string.
        System.out.println("nested leak: "
                + unsafe.toString().contains(credential.token()));
        System.out.println("safe excludes nested token: "
                + !safe.toString().contains(credential.token()));
        System.out.println("safe representation: " + safe);
    }
}
~~~

~~~bash
javac -encoding UTF-8 NestedToStringDemo.java
java NestedToStringDemo
~~~

Stdout:

~~~text
nested leak: true
safe excludes nested token: true
safe representation: SafeRequest[requestId=req-9]
~~~

When designing nested objects, check every place where the outer class's representation **includes an entire object, collection, header map, URL, or payload** in the string. A safe `toString()` should not rely on every child object knowing how to hide its own secrets.

If you need to describe a collection, you can output just the element count or a permitted statistic, such as `itemsCount=3`, rather than concatenating `items`. If you need to describe an HTTP request, use selected metadata such as method, normalized route, or correlation ID; avoid outputting raw headers, query strings, and bodies without classification.

## 8. Regular Class Example: Outputting Only Controlled Metadata

Records are not the only case. A POJO class should also manually override `toString()` if it contains sensitive data and may appear in logs.

Create the file `SafeAccountToStringDemo.java`:

~~~java
public class SafeAccountToStringDemo {
    static final class Account {
        private final String correlationId;
        private final String passwordHash;
        private final String recoveryCode;

        Account(String correlationId, String passwordHash, String recoveryCode) {
            this.correlationId = correlationId;
            this.passwordHash = passwordHash;
            this.recoveryCode = recoveryCode;
        }

        @Override
        public String toString() {
            return "Account{correlationId='" + correlationId + "'}";
        }

        boolean representationContainsSecret() {
            String text = toString();
            return text.contains(passwordHash) || text.contains(recoveryCode);
        }
    }

    public static void main(String[] args) {
        Account account = new Account(
                "trace-100",
                "example-hash-value",
                "example-recovery-code"
        );

        System.out.println(account);
        System.out.println("contains secret: "
                + account.representationContainsSecret());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeAccountToStringDemo.java
java SafeAccountToStringDemo
~~~

Stdout:

~~~text
Account{correlationId='trace-100'}
contains secret: false
~~~

Note that `passwordHash` can still be sensitive data and must not be considered safe just because it is hashed. In this example, the output string contains **only** the permitted synthetic correlation ID. Secret field names may appear in source code for illustration, yet are **absent from the `toString()` result**.

You should also avoid using user-supplied names/IDs indiscriminately. If input data can carry newlines or control characters, normalize/escape it or replace it with a system-generated diagnostic ID; see the next section.

## 9. Preventing Untrusted Data from Breaking Log Structure

Even a field without secrets can be **untrusted** data. If `toString()` directly concatenates strings containing newlines, control characters, or very long text, logs can be polluted, spoofed with forged lines, or incur increased storage costs.

One way to reduce risk when you genuinely need to print a permitted input value is to bound its length and escape special characters. Do this **only after** confirming the field is allowed to be logged; escaping does not make a secret safe.

Illustrative snippet (not a standalone program):

~~~java
static String safeShortText(String value) {
    if (value == null) return "null";
    String cleaned = value.replace("\\", "\\\\")
            .replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace("\t", "\\t");
    int max = 80;
    return cleaned.length() <= max
            ? cleaned
            : cleaned.substring(0, max) + "...";
}
~~~

The function above illustrates displaying a short string with CR/LF/tab characters escaped. It **does not handle every control character, Unicode sequence, or byte-limit policy**, so rules matching the actual log format are needed when building a production library. Whenever possible, **not printing raw input values** remains easier to guarantee.

## 10. When Using Logging, Exceptions, and Code Generators

### Logging

- Avoid `logger.info("login={}", login)` or `logger.debug("request=" + request)` if `login`/`request` may contain secrets.
- Log business events and metadata with clear purpose, such as operation name, status, and an approved correlation ID.
- Check log configuration and retention/access policies, but **do not rely on logs being admin-only to justify writing secrets**.
- Use structured logging and field allowlists where appropriate. Also configure serializers/mappers safely: protecting `toString()` does not automatically protect every way an object is serialized.

### Exceptions and Debugging

Patterns like `throw new IllegalArgumentException("Bad request: " + request)` can pull `request.toString()` into the exception message. The exception may then be logged or sent over an API. Use descriptive error messages, error codes, or non-sensitive correlation IDs instead of the entire object.

Debuggers, heap dumps, and tracing can observe values differently from `toString()`. A safe `toString()` is **one layer of defense for string output scope**, not a promise that secrets do not exist or cannot be read elsewhere.

### IDEs, Records, and Code Generators

- Records auto-generate `toString()` from their components if not overridden. Audit records/DTOs containing credentials before logging.
- IDEs have features to generate `toString()` from fields. Do not accept "select all" by default.
- Code-generation libraries may have options to exclude or include only permitted fields; verify the actual configuration and generated code. An annotation that ignores a field during JSON serialization **does not automatically change `toString()`**, and vice versa.
- For model types that may gain new fields, prefer an allowlist so the representation does not automatically change with internal structure.

If an object needs to be displayed in a UI or sent over the network, use a **dedicated DTO/response model** designed to exclude secrets. Do not use `toString()` as a data-exchange protocol or API format.

## 11. Self-Testing `toString()` with a Simple Test

Do not rely on eyeballing the output once. When changing a class or adding components, check that the representation still contains none of the secret markers placed in a test object.

Create the file `ToStringSafetyCheck.java`:

~~~java
public class ToStringSafetyCheck {
    record SafeCredential(
            String operationId,
            String password,
            String accessToken
    ) {
        @Override
        public String toString() {
            return "SafeCredential[operationId=" + operationId + "]";
        }
    }

    private static void assertNotContained(String text, String secret) {
        if (text.contains(secret)) {
            throw new AssertionError("Sensitive value appears in representation");
        }
    }

    public static void main(String[] args) {
        SafeCredential value = new SafeCredential(
                "op-123",
                "synthetic-password-123",
                "synthetic-access-token-456"
        );

        String output = value.toString();
        assertNotContained(output, value.password());
        assertNotContained(output, value.accessToken());

        if (!output.contains("op-123")) {
            throw new AssertionError("Missing permitted diagnostic field");
        }

        System.out.println("toString safety check: PASS");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ToStringSafetyCheck.java
java ToStringSafetyCheck
~~~

Stdout:

~~~text
toString safety check: PASS
~~~

All values above are **synthetic data**; never put real tokens into test code or failure messages. This is a minimal check and cannot prove that all unknown secret types or all serialization paths are safe. To strengthen it, add tests when adding fields, changing nested component types, or changing the `toString()` generation mechanism.

When a test fails, never embed the secret itself into the assertion message or test log. The goal is to detect leaks, not create another secret-exposure channel.

## 12. Common Misconceptions

| Misconception | What Is True |
| --- | --- |
| `toString()` is only used in debuggers so it can print every field. | It can also appear in logs, exceptions, monitoring tools, and string concatenation. |
| A record without a hand-written `toString()` is safe. | A default record generates a representation containing all components, which may include passwords/tokens. |
| Encoding a token in Base64 or printing only a few characters is safe. | Not guaranteed; it can still leak information and correlate tokens. |
| Only the outer class's `toString()` needs fixing. | If the outer class concatenates whole child objects/Maps/Lists, child representations can contain secrets. |
| Password hashes are always permitted in logs. | Hashes can also be sensitive data; they should be excluded from representations. |
| Using `logger.debug` means secrets are never written. | Once that log level is enabled or messages are collected, data can still appear. |
| Having `@JsonIgnore` automatically excludes the field from `toString()`. | JSON serialization policy and `toString()` are two separate mechanisms. |
| If `toString()` does not leak secrets, the whole object is safe to serialize. | JSON/XML, debuggers, or heap dumps have separate paths to read data. |
| Replacing secrets after string concatenation is enough. | It easily misses new fields, different formats, and nested objects; an allowlist is stronger. |
| Every identifier is public data. | IDs can carry sensitive meaning; classify them before putting them in logs. |

## 13. Checklist for Designing Safe Representations

Before finalizing `toString()` for a Java class:

1. **Classify all data**: identify passwords, tokens, keys, cookies, personal information, and sensitive data in both direct fields and nested objects.
2. **Define the diagnostic goal**: what actually needs to be known to handle an incident? Usually only the object type, status, and a safely designed correlation ID.
3. **Use an allowlist**: concatenate only approved fields, rather than printing everything and trying to scrub afterward.
4. **Never use tokens as correlation codes**: do not log raw tokens, prefixes/suffixes, Base64, or arbitrary token hashes.
5. **Check nested objects**: do not concatenate whole header maps, request DTOs, collections, or payloads containing unclassified data.
6. **Review records and code generators**: auto-generated `toString()` may expose fields added later.
7. **Control printable input data**: escape newlines/control characters, limit size, or log only system-generated IDs.
8. **Keep exceptions and logging consistent**: use permitted values, even when messages are meant only for debugging.
9. **Test with synthetic data bearing recognizable markers**: verify the string contains none of the test secrets; do not print those values in test output.
10. **Evaluate other channels separately**: JSON serialization, tracing, events, heap dumps, and support screens must have their own protection policies.

**Key takeaway:** `toString()` is an object's **observation** surface and can be invoked indirectly many times. A good debugging representation must be **minimal, intentional, and free of credentials**. For classes holding passwords, tokens, or sensitive data, prefer an allowlist and never let secrets enter the `toString()` string, whether through direct fields, auto-generated records, or nested objects.