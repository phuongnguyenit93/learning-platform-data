# @Pattern and @Email: Syntax Validation in Jakarta Bean Validation and Spring Framework

## 1. Goal: Validate String Format, Not Authenticity

In a Spring API, two input fields may look similar yet have fundamentally different rules:

- A promo code must match `ABC-1234`, i.e., three uppercase Latin letters, a hyphen, and four digits. This is an **application-defined syntax rule**, suited for `@Pattern`.
- A registration email must have a valid email address structure per the Bean Validation provider's checker. This is a **standard email syntax rule**, suited for `@Email`.

Both standard annotations reside in `jakarta.validation.constraints`:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Pattern;

class ContactRequest {
    @Email
    String email;

    @Pattern(regexp = "[A-Z]{3}-[0-9]{4}")
    String inviteCode;
}
```

Both validate the **text representation (`CharSequence`)** after Java has received the value. They **do not verify identity**, do not query DNS/databases, do not check whether an email can receive mail, and do not guarantee an invite code exists or belongs to the sender.

The crux of this lesson is distinguishing three questions:

1. **Does the string match the syntax?** → `@Pattern` or `@Email`.
2. **Must the user fill in this field?** → combine `@NotNull`, `@NotBlank`, or `@NotEmpty` according to data type.
3. **Is the value real, permitted, and owned by the user?** → separate business checks, database lookups, and verification flows.

Library note: Spring Framework 6 / Spring Boot 3 uses the **`jakarta.validation.*`** namespace. Older Spring projects may use `javax.validation.*`; avoid mixing annotations from both namespaces with incompatible providers.

## 2. @Pattern: Constraining with a Java Regular Expression

`@Pattern` has one required parameter, `regexp`. The `CharSequence` value must match the regular expression per `java.util.regex.Pattern` conventions. According to the Jakarta Validation specification, **`null` is considered valid** for `@Pattern`; another constraint must be added when the field is required.

Example:

```java
@Pattern(regexp = "[A-Z]{3}-[0-9]{4}")
private String inviteCode;
```

Here:

- `[A-Z]`: one uppercase Latin letter A–Z.
- `{3}`: exactly three times.
- `-`: literal hyphen character.
- `[0-9]`: one ASCII digit from 0 to 9.
- `{4}`: exactly four times.

A `@Pattern` constraint uses **full-string matching** per the validator contract, so `ABC-1234` passes; `xABC-1234`, `ABC-1234x`, `abc-1234`, and `ABC-123` all fail. Do not use `find()` (substring search) logic to infer `@Pattern`'s default behavior.

### 2.1. Syntax Verification Table

| `inviteCode` Value | `@Pattern(regexp="[A-Z]{3}-[0-9]{4}")` | Reason |
| --- | --- | --- |
| `"ABC-1234"` | Pass | Exact character counts and order |
| `"XYZ-0000"` | Pass | `0000` is four syntactically valid digits |
| `"abc-1234"` | Violation | Pattern requires uppercase letters |
| `"AB-1234"` | Violation | Missing one letter |
| `"ABCD-1234"` | Violation | One extra letter |
| `"ABC_1234"` | Violation | Wrong separator character |
| `"ABC-123"` | Violation | Missing one digit |
| `" ABC-1234 "` | Violation | Extra whitespace |
| `""` | Violation | Pattern does not allow an empty string |
| `null` | Pass | `@Pattern` does not enforce presence |

**Key takeaway:** if the invite code is optional, `null` is allowed while an empty string `""` will be rejected by this pattern. If the UI treats an empty input box as unprovided, define a consistent input normalization step; do not accidentally rely on whether the form binder trims or not.

### 2.2. @Pattern Attributes

`@Pattern` provides these primary attributes:

| Attribute | Meaning |
| --- | --- |
| `regexp` | Required regex, following Java regex syntax |
| `flags` | Regex control flags, empty array by default |
| `message` | Message template on violation |
| `groups` | Applicable validation groups |
| `payload` | Extension metadata; does not alter matching condition |

Example accepting both lowercase and uppercase letters:

```java
import jakarta.validation.constraints.Pattern;

class CouponRequest {
    @Pattern(
        regexp = "[A-Z]{3}-[0-9]{4}",
        flags = Pattern.Flag.CASE_INSENSITIVE,
        message = "Code must match ABC-1234"
    )
    String code;
}
```

`Pattern.Flag` here is the **enum nested inside `jakarta.validation.constraints.Pattern`**, not `java.util.regex.Pattern`. Other flags you may encounter: `MULTILINE`, `DOTALL`, `COMMENTS`, `UNICODE_CASE`. Only add flags intentionally; in particular, `CASE_INSENSITIVE` and `UNICODE_CASE` can broaden the accepted character set. For identifiers requiring strict ASCII, use explicit character classes and test Unicode inputs.

### 2.3. Regex in Java Source Requires Two Levels of Escaping

If you want a pattern like `ABC-1234` but use `\d` for a digit in Java regex, in a **Java string literal** you must write:

```java
@Pattern(regexp = "[A-Z]{3}-\\d{4}")
String code;
```

In a Java string literal, two backslashes `\\` produce one `\` passed into the regex; then the regex engine interprets `\d` per its syntax. Typing `"[A-Z]{3}-\d{4}"` in Java source causes a compiler error: `illegal escape character`.

You can avoid confusion by writing `[0-9]`. For a literal dot in an email domain, Java source needs `"\\."` so the regex treats it as a literal `.` rather than the `.` wildcard.

With a regex already requiring full-input matching, adding `^` and `$` is unnecessary. If you intentionally use anchors in other regexes, understand the differences between `^`/`$`, multiline mode, and `\A`/`\z`; do not expect anchors alone to protect code that calls `find()`.

### 2.4. Practical Regexes Should Be Narrow and Bounded

Example of a handle allowing only 3–12 characters consisting of lowercase letters, digits, and underscores, starting with a lowercase letter:

```java
@Pattern(regexp = "[a-z][a-z0-9_]{2,11}")
String handle;
```

The regex above bounds both **character set and length**. For a field needing only length bounds without a special character set, use `@Size`; for a required string with non-whitespace text, use `@NotBlank`. Do not write huge regexes to replace a full complex data parser.

Regexes can burn CPU with nested quantifiers on long inputs (catastrophic backtracking). For example, patterns with overlapping repetition groups on non-matching strings can cause processing time to spike sharply. Limit request sizes, design linear-time regexes when possible, test long/adversarial inputs, and consider dedicated parsers for complex formats.

## 3. @Email: Checking Email Addresses per the Provider

`@Email` is standardized in Jakarta Bean Validation:

```java
import jakarta.validation.constraints.Email;

class SignupRequest {
    @Email
    String contactEmail;
}
```

Per the standard contract:

- The validated value is a **`CharSequence`**, such as `String`.
- `null` is **valid**. To make input required, combine with another constraint.
- The address must be a well-formed email address as considered by the provider.
- **The exact definition of a valid email is left to the Bean Validation provider.** Therefore, do not treat `@Email` as a complete, universally identical implementation of every email RFC edge case.
- `regexp` defaults to `".*"`, meaning no extra regex restriction beyond the provider's email criteria.

This explains why unusual addresses such as local parts with special symbols, internationalized addresses, uncommon domains, or quoted syntax may be accepted/rejected differently across providers/versions.

**`@Email` only checks syntax; it does not verify an active mailbox.** A structurally valid string like `unknown@example.com` still may not represent an account able to receive mail; moreover, `example.com` is a documentation example domain. Do not use `@Email` results as proof that the sender owns the address.

### 3.1. @Email Does Not Replace @NotBlank

To make email a **required field with content**, write:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

class AccountRequest {
    @NotBlank(message = "Please enter an email")
    @Email(message = "Invalid email address format")
    String email;
}
```

`@NotBlank` rejects `null`, `""`, and whitespace-only strings, while `@Email` handles email syntax checking. For an optional email, `@Email` alone allows `null`; application policy should specify how empty strings are interpreted.

Some providers, including common Hibernate Validator configurations, accept `""` for `@Email`; the specification only guarantees that `null` is allowed and leaves detailed syntax criteria to the provider. Therefore, do not rely on `@Email` alone to require an email, and write actual tests for `""` against your running provider.

### 3.2. @Email Can Add an Extra Regex

`@Email` also has `regexp` and `flags`. This pattern applies an **additional** regex condition alongside the provider's email syntax check.

Example of an internal application allowing only addresses in a specific domain:

```java
@Email(
    regexp = "[^@]+@example\\.com",
    message = "Must use an example.com email"
)
String workEmail;
```

Explanation:

- `@Email` still evaluates whether the address has valid email syntax per the provider.
- `regexp` additionally restricts the string to a local part before `@` and domain `example.com`.
- Regex is case-sensitive unless flags are specified. If policy treats domains case-insensitively, normalize or configure flags accordingly.
- `example.com` here is an illustrative domain; real apps need official organizational domain rules.
- **Domain regex alone does not prove a user belongs to the organization** and may fail to handle aliases, subdomains, internationalized domains, or internal addresses per real policy. Domain verification and address ownership should be enforced through dedicated application workflows.

Do not write a massive RFC email regex just to be "as strict as possible". `@Email` plus a few narrow business rules is usually easier to understand and test. If policy is complex (domain allowlists, aliases, tenants, OTP verification), move it out of regex annotations or write a custom constraint with clear semantics.

### 3.3. What @Email Does Not Guarantee

| Requirement | Supported by `@Email`? | How to Handle When Needed |
| --- | --- | --- |
| Matches provider's email structure | Yes | `@Email` |
| Cannot be left blank | Not guaranteed on its own | `@NotBlank` |
| Length per application policy | Does not enforce all limits on its own | `@Size` / appropriate length checks |
| Domain has active DNS/MX | No | Check network only if truly needed, handle DNS with MX/SMTP fallbacks |
| Mailbox exists | No | Cannot be reliably inferred from syntax/DNS alone |
| User owns the address | No | Send verification link/code |
| Address not yet registered | No | Database unique constraint and race-condition handling |
| Not in a blocked domain | No | Separate domain/allowlist/blocklist rules |
| Not a disposable address | No | Risk-assessment service/policy, which may be imperfect |
| No risk of abuse | No | Rate limiting, anomaly detection, and mailing policies |

Running synchronous DNS/SMTP checks inside a `ConstraintValidator` on every request often causes latency, side effects, and network coupling; weigh this carefully. Most signup flows validate syntax first, create an **unverified** state, send a verification email, and only transition to **verified** after the user proves delivery access.

## 4. Comparison Table: @Pattern vs. @Email

| Criterion | `@Pattern` | `@Email` |
| --- | --- | --- |
| Purpose | Matches an application-declared regex | Matches email syntax per provider |
| Input | `CharSequence` | `CharSequence` |
| `null` value | Valid | Valid |
| Required attribute | `regexp` | None; `regexp` defaults to `".*"` |
| `flags` | Flags for the main regex | Flags for the additional regex |
| Provider-dependent rules | Java regex engine; provider invokes check | Well-formed email definition decided by provider |
| Typical data | Identifiers, postal codes per policy, usernames | Email addresses |
| Replaces `@NotBlank` | No | No |
| Verifies data exists | No | No |
| Verifies ownership | No | No |

You can use `@Pattern` directly to constrain a specialized email format, yet **an arbitrary regex should not be treated as a full replacement for `@Email`**. Conversely, do not use `@Email` to validate customer codes or arbitrary formats merely because it has a `regexp` attribute.

## 5. DTO Design: Combining Multiple Constraints Semantically

### 5.1. Required Fields and Optional Fields

Example request DTO:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public class SignupForm {
    @NotBlank
    @Email
    @Size(max = 254)
    private String email;

    // Optional invite code: null is valid; if provided, must match format.
    @Pattern(regexp = "[A-Z]{3}-[0-9]{4}")
    private String inviteCode;

    @NotBlank
    @Pattern(regexp = "[a-z][a-z0-9_]{2,11}")
    private String handle;

    // Appropriate getters/setters or constructor binding.
}
```

`@Size(max=254)` in the example is a common **application length rule**, not a universal proof that every RFC-compliant email address is handled correctly. With Unicode, character counts, UTF-16 code units, and UTF-8 byte counts are not always equal; clearly define which length metric the system uses and test boundary values.

Field meanings:

- `email`: non-empty/non-blank, valid syntax per provider, within application length limit.
- `inviteCode`: may be null; if present, must match the invite code pattern. `""` does not match the pattern.
- `handle`: required to have content and match the exact character set/length defined.

A case like "optional invite code, but treat whitespace-only as unprovided" requires **defining an explicit normalization step** before validation, e.g., trimming and converting empty strings to null in the binder/mapper. Do not assume JSON deserializers, form binders, and method validation all do this automatically.

### 5.2. How Do @NotNull, @NotEmpty, @NotBlank, and @Size Differ?

| Constraint | `null` | `""` | `"   "` | Purpose |
| --- | --- | --- | --- | --- |
| `@NotNull` | Violation | Pass | Pass | Disallow `null` |
| `@NotEmpty` | Violation | Violation | Pass | Disallow empty |
| `@NotBlank` | Violation | Violation | Violation | Disallow whitespace-only |
| `@Size(min=1)` | Pass | Violation | Pass | Minimum length; does not forbid null on its own |
| `@Pattern(regexp="[A-Z]+")` | Pass | Violation | Violation | Syntax via regex |
| `@Email` | Pass | Depends on provider details | Usually rejected; provider-dependent | Email syntax |

Do not apply `@NotBlank` to `Integer` or collections; it is for `CharSequence`. For collections, use `@NotEmpty` or `@Size(min=1)`. Multiple constraints failing together can produce multiple violations for **the same field**, so UIs should not count total violations and assume that equals the number of invalid fields.

### 5.3. Choose the Right Data Type

Both `@Pattern` and `@Email` are designed for `CharSequence`. Do not place them directly on `Long phone`, `UUID id`, `LocalDate`, or arbitrary domain object types expecting the validator to convert them to `String`. Applying constraints to unsupported types can raise `UnexpectedTypeException` or configuration exceptions at validation time.

For phone numbers, identifiers with leading zeros, or strings with `+` signs, use `String` if exact formatting must be preserved. After syntax checking, apply country/format-specific parsing if business rules need it; do not mistake `@Pattern(regexp="[0-9]{10}")` for an international phone number rule.

## 6. Standalone Java 17+: Observing @Pattern, @Email, and Violation Results

The example below uses **Jakarta Validation 3.x** and provider **Hibernate Validator 8.x**, without booting Spring MVC, to observe core constraint behavior. Run commands use Maven to build the classpath, followed by `javac` and `java` like a standard Java program.

### 6.1. Create pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>pattern-email-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.1.Final</version>
        </dependency>
    </dependencies>
</project>
```

`hibernate-validator` brings in the Jakarta Validation API and transitive dependencies. In typical applications, Hibernate Validator can use Jakarta Expression Language to interpolate certain message templates. In this small CLI program, we intentionally use Hibernate Validator's `ParameterMessageInterpolator` to avoid an EL dependency. This is a provider component, not a portable Jakarta Validation API; for message templates needing EL expressions, configure EL appropriately.

### 6.2. Create PatternEmailDemo.java

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import org.hibernate.validator.HibernateValidator;
import org.hibernate.validator.messageinterpolation.ParameterMessageInterpolator;

import java.util.List;
import java.util.Set;

public class PatternEmailDemo {

    public static final class Signup {
        @NotBlank
        @Email
        private final String email;

        // Optional invite code; null does not violate Pattern.
        @Pattern(regexp = "[A-Z]{3}-[0-9]{4}")
        private final String inviteCode;

        @Pattern(regexp = "[a-z][a-z0-9_]{2,11}")
        private final String handle;

        public Signup(String email, String inviteCode, String handle) {
            this.email = email;
            this.inviteCode = inviteCode;
            this.handle = handle;
        }
    }

    private static void show(
            String label, Set<? extends ConstraintViolation<?>> violations) {
        List<String> failures = violations.stream()
                .map(v -> v.getPropertyPath() + ":"
                        + v.getConstraintDescriptor()
                           .getAnnotation()
                           .annotationType()
                           .getSimpleName())
                .sorted()
                .toList();
        System.out.println(label + " -> " + failures);
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory = Validation
                .byProvider(HibernateValidator.class)
                .configure()
                .messageInterpolator(new ParameterMessageInterpolator())
                .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            Signup valid = new Signup(
                    "alice@example.com", "ABC-1234", "alice_1");
            Signup optional = new Signup(
                    "alice@example.com", null, null);
            Signup missing = new Signup(
                    null, null, null);
            Signup invalid = new Signup(
                    "wrong-address", "ab-12", "A");

            show("valid", validator.validate(valid));
            show("optional", validator.validate(optional));
            show("missing", validator.validate(missing));
            show("invalid", validator.validate(invalid));

            show("property inviteCode",
                    validator.validateProperty(invalid, "inviteCode"));
            show("candidate good",
                    validator.validateValue(
                            Signup.class, "inviteCode", "XYZ-0034"));
            show("candidate bad",
                    validator.validateValue(
                            Signup.class, "inviteCode", "XYZ-34"));
        }
    }
}
```

The input strings are deliberately simple, avoiding unusual emails that different providers might parse differently. The `show` helper prints sorted **property path + annotation name**, avoiding reliance on `Set<ConstraintViolation<?>>` ordering or locale-specific message translations.

### 6.3. Compile, Run, and Compare

Bash (Linux/macOS):

```bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
CP="$(cat classpath.txt)"
javac -encoding UTF-8 -cp "$CP" PatternEmailDemo.java
java -cp ".:$CP" PatternEmailDemo
```

PowerShell (Windows):

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
$cp = (Get-Content classpath.txt -Raw).Trim()
javac -encoding UTF-8 -cp $cp PatternEmailDemo.java
java -cp ".;$cp" PatternEmailDemo
```

**Expected stdout** (ignoring extra provider/Maven logs if printed by the environment):

```text
valid -> []
optional -> []
missing -> [email:NotBlank]
invalid -> [email:Email, handle:Pattern, inviteCode:Pattern]
property inviteCode -> [inviteCode:Pattern]
candidate good -> []
candidate bad -> [inviteCode:Pattern]
```

Analysis:

- `valid`: email has basic valid structure; invite code and handle both match their regexes.
- `optional`: `inviteCode` and `handle` are allowed to be `null` because `@Pattern` imposes no requiredness.
- `missing`: null email violates `@NotBlank`; `@Email` allows null. The other two fields remain valid.
- `invalid`: email lacks email structure, and invite code and handle fail regex matching; sorting paths keeps stdout deterministic.
- `validateProperty(invalid, "inviteCode")` checks only constraints on the property's current value.
- `validateValue(Signup.class, "inviteCode", "XYZ-0034")` checks a candidate without constructing a new bean; `XYZ-34` lacks four digits.
- `Validator` itself does not trim, lowercase, fix emails, or mutate objects; if normalization is needed, perform it explicitly before validation.

**Scope of example results:** these results follow the chosen constraints and Hibernate Validator 8.x provider, and do not promise identical email parsing/message formatting details across every provider. In CI, run against your project's actual JDK and dependency versions.

## 7. Combining @Pattern and @Email with Spring MVC

In Spring MVC, `@Pattern` and `@Email` are typically attached to DTOs/forms and executed when controllers use `@Valid` or `@Validated`. Annotating a field **does not automatically run checks on every Java setter call**; validation must be triggered.

Example DTO usable with a standard JSON deserializer:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public class CreateAccountRequest {
    @NotBlank
    @Email
    private String email;

    @Pattern(regexp = "[A-Z]{3}-[0-9]{4}")
    private String inviteCode;

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public String getInviteCode() { return inviteCode; }
    public void setInviteCode(String inviteCode) {
        this.inviteCode = inviteCode;
    }
}
```

Illustrative controller (inside a `@RestController`; requires corresponding Spring/Jakarta imports):

```java
@PostMapping("/accounts")
public ResponseEntity<?> create(
        @Valid @RequestBody CreateAccountRequest request,
        BindingResult errors) {

    if (errors.hasErrors()) {
        var fields = errors.getFieldErrors().stream()
                .map(e -> e.getField() + ":" + e.getCode())
                .toList();
        return ResponseEntity.badRequest().body(fields);
    }

    // Service proceeds to check business rules and send verification email.
    return ResponseEntity.ok().build();
}
```

Flow breakdown:

1. JSON body is read and converted into `CreateAccountRequest` by an `HttpMessageConverter` (usually Jackson) first.
2. Bean Validation checks the matching fields when a provider and validator are configured.
3. With a controller signature placing `BindingResult` immediately after the DTO parameter in supported Spring cases, code can inspect `FieldError`s and return an error response.
4. Once syntactically valid, the service still must verify business rules, persist data, check database uniqueness, and verify the email address.

Spring MVC has two validation paths to distinguish: validation on `@ModelAttribute`/`@RequestBody`/`@RequestPart` and method validation on parameters/return values. Depending on method signature, Spring may raise `MethodArgumentNotValidException` or `HandlerMethodValidationException`; do not claim all violations always flow through a single exception type.

### 7.1. Forms and JSON Can Differ at the Binding Step

With forms, initial input may be a `String`; converters/binders can trim, parse, or convert blank strings to null if configured. With JSON, Jackson and deserialization settings determine the resulting Java value. When a normalization step modifies data before validation, the exact same string typed by a user can yield different outcomes between form and JSON.

For example:

- `inviteCode=null` → `@Pattern` passes.
- `inviteCode=""` → the code pattern above violates.
- `inviteCode=" ABC-1234 "` → violates if kept as-is; may pass after `strip()` normalization if business rules permit trimming.
- `email=null` → `@Email` passes, `@NotBlank` violates if present.
- `email=""` → `@NotBlank` violates; `@Email` depends on the provider for empty strings.

Decide explicitly which strings are accepted, normalize per policy, and test both input paths. Be cautious about automatically lowercasing the **entire** email: the domain part is case-insensitive in DNS, whereas local-part equivalence and Unicode rules are subtle; do not assume "all emails are equal after lowercasing" solely on `@Email`.

### 7.2. Validation Groups per Operation

Every annotation has a `groups` attribute. For instance, an invite code format check might only apply on account creation while another update operation does not validate that field:

```java
interface OnCreate {}

class AccountCommand {
    @NotBlank(groups = OnCreate.class)
    @Email(groups = OnCreate.class)
    String email;

    @Pattern(
        regexp = "[A-Z]{3}-[0-9]{4}",
        groups = OnCreate.class
    )
    String inviteCode;
}
```

Call `validator.validate(command, OnCreate.class)` to enforce constraints in this group. If a controller uses Spring's `@Validated(OnCreate.class)`, Spring selects the matching group in supported validation contexts.

**Note:** once a custom group is requested, constraints belonging only to `Default` do not run automatically unless group inheritance/sequences/conversions are declared appropriately. For PATCH-style updates, distinguish missing fields, null fields, and fields with new strings; `@Pattern` alone cannot express "clear this value".

### 7.3. Manual Validation and Displaying Errors

You can inject `jakarta.validation.Validator` into a service:

```java
@Service
public class ContactValidationService {
    private final jakarta.validation.Validator validator;

    public ContactValidationService(
            jakarta.validation.Validator validator) {
        this.validator = validator;
    }

    public boolean validCandidateCode(String code) {
        return validator.validateValue(
                CreateAccountRequest.class, "inviteCode", code
        ).isEmpty();
    }
}
```

This is an **integration snippet**, not a standalone Java program; import `@Service` and the project's DTO class. `validateValue` checks a candidate against field constraints, without validating the whole bean/cross-field rules or sending emails.

For UIs, use property paths, error codes, and locale-appropriate messages; avoid logging raw user inputs, especially tokens or personal data. `BindingResult.getFieldErrors()` classifies field-bound errors; also handle `getGlobalErrors()` if object-level constraints exist. Messages can vary by locale, so do not use translated strings as system logic keys.

## 8. Scope of Syntax Validation vs. Business Validation

### 8.1. A Regex-Valid Invite Code Can Still Be Invalid

The string `ABC-1234` can pass `@Pattern` and still be unusable if:

- The code does not exist in the database.
- The code is expired or out of uses.
- The code does not belong to the current account/user group.
- The code was already redeemed or deactivated.
- The code belongs to another tenant and leaking details affects authorization.

The proper approach: validate syntax on the DTO, then have the service check existence/status/ownership using appropriate transactions and concurrency control. Never treat `@Pattern` as business validation.

### 8.2. A Syntactically Valid Email Still Needs Verification

A sound registration flow:

1. Bind JSON/form into the DTO.
2. Validate email presence and syntax.
3. Normalize per explicit policy and verify contractual length limits.
4. Create the account in an unverified-email state.
5. Send a short-lived verification token/link with attempt limits and abuse protection.
6. Mark verified only after confirming delivery access.
7. Handle email changes, token expiration, resends, and database uniqueness conflicts.

You do not need live SMTP probing every time a user enters an email; many mail servers reject probing and results easily cause false positives/negatives. Review privacy policies when logging emails and verification actions.

### 8.3. Unicode Handling and Consistency

ASCII regexes like `[A-Z]` and `[0-9]` have narrow, explicit intent. If the product supports accented names, internationalized domains, or Unicode codes, define Unicode normalization, case folding, and equivalence rules before picking a regex; enforce the same rules on backend and UI, avoiding reliance on HTML `pattern` alone.

Browser HTML `input type="email"` and `pattern` give early feedback yet **do not protect the server**: clients can bypass JavaScript, send direct HTTP requests, or use other HTTP clients. Backend constraints still must be enforced. When values pass through URLs, JSON, or form encoding, validate the decoded Java representation rather than running regexes directly on raw bytes at the wrong layer.

## 9. Common Mistakes and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `@Email` allows `null` | Spec treats null as valid | Combine `@NotBlank` if required |
| `@Pattern` allows `null` yet rejects `""` | Regex only runs on non-null values | Define optional semantics and normalization step |
| `@Email` reports "valid" for a nonexistent address | Only checks well-formed syntax | Use email verification |
| Email valid in one environment, rejected in another | Providers have slightly different email semantics | Pin/test provider version and input policy |
| Java reports `illegal escape character` | Forgot to escape backslash in Java literal | Write `"\\d"` or use `[0-9]` |
| Invite code regex accepts unintended strings | Overly broad regex, `.*`, wrong flags | Specify exact character classes and quantifiers |
| Regex slow on long inputs | Heavy backtracking or unbounded length | Limit request size, simplify regex, benchmark worst cases |
| `@Pattern` on an integer type throws exception | Constraint only supports `CharSequence` | Use `String` for syntax-checked data or custom constraint |
| Form valid yet service rejects | Format matches, but code missing/expired | Separate syntax and business validation |
| API ignores annotations | Validator/provider not enabled or wrong namespace | Configure Jakarta provider and `@Valid`/`@Validated` |
| Spring returns 400 before running Bean Validation | Malformed JSON body or deserialization failure | Separate parse errors from constraint errors |
| `@Email(regexp=...)` blocks valid domains | Domain regex policy too narrow / misses aliases | Align domain policy, write representative tests |
| Uppercase `@Pattern` rejects lowercase | Unclear flags and normalization rules | Define canonical case, add flag or normalize beforehand |
| UI regex passes yet backend regex fails | Different regex engines, Unicode/flags/normalization | Treat server as source of truth, test samples in Java |
| Email logged alongside form errors | Logging full DTO/`getInvalidValue()` | Log error code/path, mask sensitive data |
| "100% RFC-compliant" email regex hard to maintain | Email format has many valid cases/provider differences | Use `@Email` + narrow policy and real verification |

## 10. Recommended Test Suite

To verify both syntax and input contracts, test in layers:

**A. Unit tests specifically for @Pattern**

- Valid cases, wrong length, wrong characters, wrong case, leading/trailing whitespace.
- `null`, `""`, and very long values.
- `CASE_INSENSITIVE`/Unicode flags if enabled.
- Adversarial inputs that could cause high CPU in regexes, especially for client-controlled input.

**B. Unit tests specifically for @Email**

- Common emails like `alice@example.com`.
- Missing `@`, missing local/domain part, disallowed whitespace.
- `null` and `""` under your exact provider.
- International addresses, subdomains, `+` tags, or quoted parts if the system intends to support them.
- When upgrading provider/version, run regression tests to detect syntax scope changes.

**C. Spring MVC integration tests**

- `@Valid`/`@Validated` is actually triggered.
- Wrong-type body/unparseable JSON differs from email/regex violations.
- `BindingResult`, exception handlers, and response status/messages satisfy the API contract.
- Form and JSON normalization policies are consistent.
- Never return raw emails, tokens/passwords, or stack traces in bodies/logs.
- After syntax validation, the service still checks state, uniqueness, and verification in the proper flow.

One direct way to test Jakarta Validator is calling `validator.validateValue(Request.class,"inviteCode", candidate)` across boundary inputs, asserting violation count or annotation type rather than locale-translated messages. However, during submission flows, run `validate(request)`/`@Valid` on the entire DTO so no other constraints are missed.

## 11. Selection Rules and Key Takeaways

- **Want strings matching a custom structure** (codes, handles, versions, serial numbers): start with `@Pattern(regexp=...)` with clearly bounded scope.
- **Want addresses with email syntax**: use `@Email`; remember exact email validity details depend on the provider and null is allowed.
- **Want a required field with content**: add `@NotBlank`; `@Email`/`@Pattern` do not enforce requiredness on their own.
- **Want to limit length**: use `@Size` and define which length representation applies when Unicode is involved.
- **Want to verify a code exists, an email is owned, or a code is unexpired**: perform separate business, persistence, and verification checks.
- **Want reliable behavior in Spring**: configure a Bean Validation provider, use `@Valid`/`@Validated` in the right context, and separate binding/deserialization errors from constraint errors.
- **Want to avoid environment drift**: test boundary inputs and pin provider versions; bound regexes to avoid heavy backtracking.

Choose `@Pattern` when you **own the syntax rule**; choose `@Email` when you need **provider-implemented email address rules**. In both cases, syntax validation is an input-checking layer, not proof that data is valid for business rules or that the user is authorized to use it.

### Reference Documentation

- Jakarta Validation 3.1 API — `@Pattern`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/Pattern.html
- Jakarta Validation 3.1 API — `@Email`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraints/Email.html
- Jakarta Bean Validation specification, built-in constraints: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Java 17 regex `Pattern`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html
- Hibernate Validator 8 Reference Guide: https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/
- Spring Framework — Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC — Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring MVC — `@RequestBody`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
