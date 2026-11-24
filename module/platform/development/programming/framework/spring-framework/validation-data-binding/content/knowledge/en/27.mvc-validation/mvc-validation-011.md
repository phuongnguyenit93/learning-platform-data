# Local Validators, Global Validators, and Multiple Validators in Spring MVC

## 1. The problem: one form with multiple kinds of validation rules

In Spring MVC, receiving HTTP data and verifying that the data is valid are two related yet distinct steps. For example, a signup form has these conditions:

- `username` must not be blank per Jakarta Bean Validation `@NotBlank`.
- `age` must be at least 18 per `@Min(18)`.
- The name `admin` is reserved per an application rule.
- Emails from the domain `blocked.test` are not accepted per a custom system policy.

The first two can be placed directly on the DTO using Jakarta constraints. The latter two can be implemented using one or more Spring `org.springframework.validation.Validator`s.

**Core question:** How can Spring MVC use both the application-wide default validator and multiple custom validators for a single form/controller without accidentally losing `@NotBlank` and `@Min` checks?

The answer lies in three concepts:

1. **Global validator** configured for the Spring MVC infrastructure, typically `LocalValidatorFactoryBean` when a Jakarta Bean Validation provider is present.
2. **Local validators** added to the `WebDataBinder` of a controller or a model attribute via `@InitBinder`.
3. **Multiple validators** can participate together in a single validation pass when the binder uses `addValidators(...)` instead of replacing the entire list.

This lesson covers the **Spring MVC Servlet stack** (Spring Framework 6.x, Spring Boot 3.x). Spring WebFlux has similar APIs yet different request-processing infrastructure. Do not equate this mechanism with method validation on Spring AOP services or all of Jakarta Bean Validation.

## 2. The two Validator interfaces and their roles

### 2.1. Spring Validator

Spring provides the interface:

```java
package org.springframework.validation;

public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
```

This is an **illustrative API signature**, not a file you write yourself. In your application, import the built-in interface from Spring.

- `supports(Class<?>)`: declares which object types the validator can handle. For a `SignupForm` DTO, it can return `SignupForm.class.isAssignableFrom(clazz)`.
- `validate(Object, Errors)`: evaluates data and **records errors** using `errors.rejectValue(...)` for fields or `errors.reject(...)` for object-level errors.

Unlike `jakarta.validation.ConstraintValidator<A,T>`, a Spring `Validator` **does not return a valid/invalid boolean**. It adds `ObjectError`/`FieldError` instances into the active `Errors` object.

Example username validator:

```java
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class UsernameRuleValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return SignupForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;
        if ("admin".equalsIgnoreCase(form.getUsername())) {
            errors.rejectValue(
                "username", "reservedUsername",
                "This name is reserved");
        }
    }
}
```

This is an **illustrative snippet** requiring the corresponding `SignupForm`. The complete program in section 6 includes all files, imports, and configuration.

### 2.2. Jakarta Bean Validation and LocalValidatorFactoryBean

Jakarta Bean Validation uses annotations such as `@NotNull`, `@NotBlank`, `@Min`, `@Email`, and `@Size`; a common provider is Hibernate Validator. This engine is wired into Spring MVC via `org.springframework.validation.beanvalidation.LocalValidatorFactoryBean`, which bridges **Spring `Validator`/`SmartValidator`** and **Jakarta `Validator`**.

When a Bean Validation library is present, Spring MVC normally auto-registers `LocalValidatorFactoryBean` as the global validator to process `@Valid` and `@Validated` on controller method arguments.

Therefore, in a Spring Boot app that already has `spring-boot-starter-validation`, **you do not need to replace the global validator just to add a custom rule for one form**. Using `@InitBinder(...).addValidators(...)` is usually simpler and has fewer side effects.

### 2.3. Spring SmartValidator

`org.springframework.validation.SmartValidator` extends Spring's `Validator`, adding an overload that supports *validation hints* (such as validation groups):

```java
// Illustrative signature in Spring API:
void validate(Object target, Errors errors, Object... validationHints);
```

`LocalValidatorFactoryBean` supports this mechanism. When a controller uses `@Validated(SomeGroup.class)`, the groups can be passed as hints to `SmartValidator`. A simple custom `Validator` implementing only `validate(Object, Errors)` does not automatically read and filter validation groups like a Bean Validation provider; if group filtering is needed, design for it explicitly or use the appropriate API.

## 3. Spring MVC's global validator

### 3.1. Default behavior

When Spring MVC finds a Jakarta Validation provider, it registers a built-in validator to support DTO validation. Example:

```java
public class SignupForm {

    @NotBlank
    private String username;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    // Default constructor, getters, and setters...
}
```

A controller using it:

```java
@PostMapping("/signup")
public ResponseEntity<?> signup(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body("Invalid form");
    }
    return ResponseEntity.ok().build();
}
```

When `@Valid` triggers validation, the global MVC validator can create `FieldError`s from `@NotBlank`, `@Email`, `@NotNull`, or `@Min`. That is **validation on a bound object**, not necessarily executable method validation on scalar controller parameters.

### 3.2. Customizing via WebMvcConfigurer#getValidator()

In applications that need to pick a shared MVC validator explicitly, Spring provides a hook:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.Validator;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcValidationConfig implements WebMvcConfigurer {

    private final Validator myMvcValidator;

    public MvcValidationConfig(Validator myMvcValidator) {
        this.myMvcValidator = myMvcValidator;
    }

    @Override
    public Validator getValidator() {
        return myMvcValidator;
    }
}
```

**This is an illustrative configuration; do not combine it with the runnable example in section 6.** `myMvcValidator` must be a properly constructed bean that causes no circular configuration dependencies. When you return a custom validator from `getValidator()`, it replaces the default choice for the **MVC infrastructure**. If that validator does not integrate Jakarta Bean Validation, do not expect `@NotBlank` or `@Min` annotations to keep running merely because they remain on the DTO.

You can use `LocalValidatorFactoryBean` or an appropriate composite strategy as the global validator if you need both Bean Validation and extra logic. However, **to add logic for one specific DTO**, the safer approach is keeping the default MVC configuration and adding a local validator.

**"Global" here means global within MVC argument validation scope**; it does not automatically mean every Java call, service, scheduled task, or message consumer uses the exact same configuration. Method validation via Spring AOP and built-in MVC method validation also have their own integration points to verify.

## 4. Local validators: @InitBinder and WebDataBinder

A controller can define an `@InitBinder` method to customize the binder before binding/validation.

```java
@RestController
public class SignupController {

    private final UsernameRuleValidator usernameValidator;

    public SignupController(UsernameRuleValidator usernameValidator) {
        this.usernameValidator = usernameValidator;
    }

    @InitBinder("signup")
    void initBinder(WebDataBinder binder) {
        binder.addValidators(usernameValidator);
    }

    @PostMapping("/signup")
    public String create(
            @Valid @ModelAttribute("signup") SignupForm form,
            BindingResult errors) {
        return errors.hasErrors() ? "INVALID" : "ACCEPT";
    }
}
```

This is an **illustrative integration snippet**; corresponding imports, DTO, and validator bean declaration are required.

Meaning of each part:

- `@InitBinder("signup")` applies only to the binder belonging to the model attribute named `signup`. It does not implicitly apply to every bean in the application.
- `WebDataBinder` is the binder handling a specific object in the request; this configuration happens before validation.
- `addValidators(usernameValidator)` **appends** the validator to the existing list rather than replacing the global validator.
- `@Valid` on the bound object tells Spring MVC to validate the form.
- `BindingResult` must stand **immediately after** the bound parameter; the controller decides whether to return errors or proceed with business logic.

If `@InitBinder` is defined inside a `@Controller` itself, its effect is local to that controller by default. If declared inside a `@ControllerAdvice`, it can apply across multiple controllers depending on the advice selector; adding the attribute name in `@InitBinder("signup")` scopes it to that binder.

**Merely declaring `@InitBinder` does not make validation run immediately.** It is a binder configuration point. Validation is normally triggered by `@Valid`/`@Validated`, or when the application invokes the binder/validator explicitly.

## 5. addValidators(), setValidator(), and replaceValidators(): not the same

This difference decides whether an application **keeps or loses the default validator**.

| DataBinder/WebDataBinder API | Behavior |
| --- | --- |
| `setValidator(validator)` | **Clears the current validator list**, then sets a single new validator; passing `null` can clear everything |
| `addValidators(v1, v2)` | **Appends** to the current list, keeping existing validators |
| `replaceValidators(v1, v2)` | Clears the old list and **replaces it with the supplied list** |
| `getValidator()` | Returns the first (primary) validator, if any |
| `getValidators()` | Returns the list of registered validators |
| `getValidatorsToApply()` | List actually applied after exclusion filtering (API since Spring 6.1) |

Inside `@InitBinder`:

```java
// Recommended if you want to keep default Bean Validation and add extra rules.
binder.addValidators(usernameValidator, emailValidator);
```

Compared to:

```java
// Caution: replaces the existing list.
binder.setValidator(usernameValidator);
```

If the binder previously held `LocalValidatorFactoryBean`, calling `setValidator(usernameValidator)` removes it from **that binder's validator list**. With only `UsernameRuleValidator` left, Jakarta constraints on the DTO may no longer run during this binder validation pass. Do not assume every `@NotBlank` annotation keeps running automatically just because the Hibernate Validator dependency is present.

Meanwhile:

```java
// Replace everything with the specified list.
binder.replaceValidators(usernameValidator, emailValidator);
```

can be deliberately useful in special cases, yet is normally not the right choice when you only want to **add** rules.

When adding validators, `DataBinder` checks `supports(target.getClass())` when a target is present. If a validator does not support the class being bound, configuration can fail with `IllegalStateException`. Never use a broad `@InitBinder` to attach a `SignupForm`-specific validator onto binders for every DTO.

### How does one validation pass run multiple validators?

With a list containing:

```text
[ MVC global LocalValidatorFactoryBean,
  UsernameRuleValidator,
  EmailDomainRuleValidator ]
```

when the binder runs validation:

1. The global validator evaluates Jakarta constraints on `SignupForm`.
2. The username validator checks the reserved-name rule for `username`.
3. The email domain validator checks the custom rule for `email`.
4. Errors from all three are recorded into the same `BindingResult` for the form.

That is the **logical model**; do not design business logic around the exact order of returned errors. Validators can report multiple errors on the same field, and test assertions should use normalized sorting when order is not a contract.

By default, one validator recording an error **does not automatically stop all other validators**. If you want to skip expensive business checks when binding errors exist, design the validator or check step explicitly and test that rule rather than expecting the list to short-circuit on its own.

## 6. Complete Java 17 + Spring Boot 3.5.6 example: three validators running together

The example below builds an HTTP endpoint receiving a form. It uses:

- **Global:** Jakarta constraints on the DTO, executed via the default MVC validator.
- **Local 1:** Spring Validator forbidding username `admin`.
- **Local 2:** Spring Validator forbidding emails in domain `blocked.test`.
- **Composition:** `@InitBinder("signup")` calling `addValidators(v1, v2)`, without touching the global validator.

No database or template engine is required. The goal is clearly observing errors from multiple sources accumulating in the same `BindingResult`.

### 6.1. Project structure

```text
mvc-multi-validator/
├── pom.xml
└── src/main/java/demo/mvc/
    ├── MultiValidatorApplication.java
    ├── SignupForm.java
    ├── UsernameRuleValidator.java
    ├── EmailDomainRuleValidator.java
    └── SignupController.java
```

### 6.2. pom.xml

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
  <groupId>demo</groupId>
  <artifactId>mvc-multi-validator</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-validation</artifactId>
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

`spring-boot-starter-web` sets up Spring MVC and the embedded server. `spring-boot-starter-validation` adds the Jakarta Validation provider so annotations on the DTO are processed. The project uses Java 17 and Maven 3.x.

### 6.3. MultiValidatorApplication.java

```java
package demo.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiValidatorApplication {

    public static void main(String[] args) {
        SpringApplication.run(MultiValidatorApplication.class, args);
    }
}
```

### 6.4. SignupForm.java

```java
package demo.mvc;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SignupForm {

    @NotBlank
    private String username;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    public SignupForm() {
    }

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
```

All constraints belong to the `Default` group: `username` and `email` must be non-blank, `email` must have valid syntax, and `age` must be non-null and 18 or older.

### 6.5. UsernameRuleValidator.java

```java
package demo.mvc;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public class UsernameRuleValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return SignupForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;
        if ("admin".equalsIgnoreCase(form.getUsername())) {
            errors.rejectValue(
                "username", "reservedUsername",
                "Username is reserved");
        }
    }
}
```

This validator does not query a database or mutate the object. Using `"admin".equalsIgnoreCase(...)` is safe when `username` is `null`.

### 6.6. EmailDomainRuleValidator.java

```java
package demo.mvc;

import java.util.Locale;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public class EmailDomainRuleValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return SignupForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;
        String email = form.getEmail();

        if (email != null && email.toLowerCase(Locale.ROOT)
                .endsWith("@blocked.test")) {
            errors.rejectValue(
                "email", "blockedDomain",
                "Addresses from this domain are not accepted");
        }
    }
}
```

The rule uses `endsWith("@blocked.test")` to check the exact suffix. This is an **illustrative policy**, not a general email parser; email syntax is still checked by Bean Validation's `@Email`. In real systems, domain rules should be designed/tested with IDN, normalization, and your application's specific email contract.

### 6.7. SignupController.java

```java
package demo.mvc;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.stream.Collectors;

@RestController
public class SignupController {

    private final UsernameRuleValidator usernameRule;
    private final EmailDomainRuleValidator emailDomainRule;

    public SignupController(
            UsernameRuleValidator usernameRule,
            EmailDomainRuleValidator emailDomainRule) {
        this.usernameRule = usernameRule;
        this.emailDomainRule = emailDomainRule;
    }

    @InitBinder("signup")
    void configureSignupBinder(WebDataBinder binder) {
        // Keep global Bean Validation, add two local rules.
        binder.addValidators(usernameRule, emailDomainRule);
    }

    @PostMapping(
        path = "/signup",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<String> signup(
            @Valid @ModelAttribute("signup") SignupForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            String details = errors.getFieldErrors().stream()
                .map(error -> error.getField() + ":" + simpleCode(error))
                .sorted()
                .collect(Collectors.joining(","));

            return ResponseEntity.badRequest()
                .body("INVALID|" + details);
        }

        return ResponseEntity.ok("ACCEPT|" + form.getUsername());
    }

    private static String simpleCode(FieldError error) {
        String[] codes = error.getCodes();
        return (codes == null || codes.length == 0)
            ? "unknown"
            : codes[codes.length - 1];
    }
}
```

Things to examine closely:

1. Both Spring `Validator` classes have `@Component` and are constructor-injected rather than re-instantiated per request.
2. `@InitBinder("signup")` targets the binder for model attribute `signup`; it **adds** both validators to the existing list.
3. `@Valid` causes MVC to validate the bound `SignupForm`. Global Bean Validation handles Jakarta annotations, while the two local validators add business-rule errors.
4. `BindingResult errors` immediately follows `SignupForm form`, letting the controller read multiple errors for the same form.
5. Errors are formatted as `field:code` and `sorted()`, avoiding reliance on the framework's `FieldError` creation order.
6. `ResponseEntity.badRequest()` is chosen **by the controller itself**, not because `BindingResult` automatically generates HTTP 400.

**Important:** Do not additionally declare a custom `WebMvcConfigurer#getValidator()` in this sample app. The goal is proving that adding local validators **preserves the default global mechanism**.

### 6.8. Running the application

From the directory containing `pom.xml`:

```bash
mvn -q spring-boot:run
```

With default configuration and an available port, the web server listens at `http://localhost:8080`. Send the following requests from another bash, zsh, or WSL terminal.

**Case A — all conditions valid:**

```bash
curl -s -X POST 'http://localhost:8080/signup' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=alice' \
  --data-urlencode 'email=alice@example.org' \
  --data-urlencode 'age=22'
```

HTTP 200 OK, body:

```text
ACCEPT|alice
```

**Case B — global Jakarta errors and local username validator:**

```bash
curl -s -X POST 'http://localhost:8080/signup' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=admin' \
  --data-urlencode 'email=broken' \
  --data-urlencode 'age=17'
```

HTTP 400 Bad Request, body:

```text
INVALID|age:Min,email:Email,username:reservedUsername
```

Three errors demonstrating composition:

- `age:Min` comes from global `@Min(18)`.
- `email:Email` comes from global `@Email`.
- `username:reservedUsername` comes from local `UsernameRuleValidator`.

**Case C — local email validator error:**

```bash
curl -s -X POST 'http://localhost:8080/signup' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=alice' \
  --data-urlencode 'email=alice@blocked.test' \
  --data-urlencode 'age=22'
```

HTTP 400 Bad Request, body:

```text
INVALID|email:blockedDomain
```

The address has valid email syntax, yet violates the `EmailDomainRuleValidator` policy.

**Case D — all three validators detect errors in one request:**

```bash
curl -s -X POST 'http://localhost:8080/signup' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=admin' \
  --data-urlencode 'email=alice@blocked.test' \
  --data-urlencode 'age=17'
```

HTTP 400 Bad Request, body:

```text
INVALID|age:Min,email:blockedDomain,username:reservedUsername
```

This is the centerpiece scenario of the lesson: **global constraints + two local validators all contributing `FieldError`s into one `BindingResult`**.

Note: Output blocks show the **HTTP response body returned by the application**, not the full stdout of Spring Boot or Maven. `curl -s` prints the body without appending a newline. Logs/headers may differ by environment. Error codes are taken from the last (most general) entry of `FieldError#getCodes()`, because more specific code names depend on `MessageCodesResolver`.

### 6.9. When intentionally replacing addValidators with setValidator

If you change `configureSignupBinder` to:

```java
@InitBinder("signup")
void configureSignupBinder(WebDataBinder binder) {
    binder.setValidator(usernameRule);
}
```

then the validator list previously configured on the binder is replaced with **only `usernameRule`**. `EmailDomainRuleValidator` is no longer added, and the previous global MVC validator is also removed from this list. In the current sample, that can cause `@Min` or `@Email` on the DTO to **stop producing errors during this binder validation pass** even though the annotations remain present.

This is a **replacement snippet to analyze API behavior**; do not run it simultaneously with the main source in section 6. To avoid introducing input-validation gaps, prefer `addValidators` when keeping default rules.

## 7. Local scope and global scope via ControllerAdvice

### 7.1. @InitBinder inside a single controller

In `SignupController`, `@InitBinder("signup")` applies only within that controller and to the binder whose object name is `signup`. Renaming the attribute to `"registration"` without updating `@InitBinder` changes whether the local rules get attached.

`@InitBinder` does not turn a validator into a system-wide interceptor. It only adjusts matching `WebDataBinder` instances during controller request handling.

### 7.2. @InitBinder inside @ControllerAdvice

To share the same policy across multiple controllers, you can place the binder method in a `@ControllerAdvice`:

```java
// Separate illustration; do NOT add simultaneously to the section 6 program.
@ControllerAdvice(assignableTypes = {
    SignupController.class,
    PartnerSignupController.class
})
public class SignupBinderAdvice {

    private final UsernameRuleValidator usernameRule;

    public SignupBinderAdvice(UsernameRuleValidator usernameRule) {
        this.usernameRule = usernameRule;
    }

    @InitBinder("signup")
    void configure(WebDataBinder binder) {
        binder.addValidators(usernameRule);
    }
}
```

This is an **integration snippet** assuming `PartnerSignupController` and existing imports/beans. With `@ControllerAdvice`, Spring can apply the `@InitBinder` method to controllers matching the selector; `@InitBinder("signup")` scopes it by model attribute name. If you **keep the local method and also add the advice above**, the same validator may be added twice and produce duplicate errors. When moving a policy from a controller to advice, maintain a single clear registration point.

### 7.3. Global in MVC differs from global across the application

Setting a global validator via `WebMvcConfigurer#getValidator()` affects MVC infrastructure. Direct Java service calls, scheduled methods, repositories, or event listeners do **not automatically** go through request binders. When validation is needed at a service boundary, consider explicit Bean Validation, Spring `@Validated` + appropriate method validation, or a dedicated invariant layer.

Request DTO validators also do not replace enforcing uniqueness in the database, transactions, or server-side authorization.

## 8. Principles when multiple validators run together

### 8.1. supports() must be accurate

A validator meant for `SignupForm` must not return `true` for every class. For example:

```java
@Override
public boolean supports(Class<?> type) {
    return SignupForm.class.isAssignableFrom(type);
}
```

This permits `SignupForm` and its subclasses. Use `type == SignupForm.class` if you strictly want that exact class without subtypes. When the binder checks whether a validator fits the target, an inaccurate `supports()` can fail configuration or cause a `ClassCastException` inside `validate()`.

### 8.2. Do not rely on error order

Validators can add multiple `FieldError`s for the same property. For example, an empty email can violate `@NotBlank`; an email with invalid syntax and a blocked domain can trigger both the Jakarta rule and the custom rule depending on policy.

When API clients require deterministic ordering, sort by field and code, or design an explicit error structure. Never write business logic assuming `getFieldErrors().get(0)` is the most severe error if ordering is unspecified.

### 8.3. Validation hints and @Validated

With:

```java
@PostMapping("/signup")
public String submit(
        @Validated(AdvancedChecks.class)
        @ModelAttribute("signup") SignupForm form,
        BindingResult errors) {
    // ...
    return errors.hasErrors() ? "INVALID" : "OK";
}
```

this is an **illustrative snippet** requiring the `AdvancedChecks` interface and imports. `LocalValidatorFactoryBean` supports Jakarta Bean Validation groups via `SmartValidator`; constraints in the `Default` group do not run automatically just because the form is checked under another group, unless that group is included in the validation contract.

The two custom classes in section 6 implement only Spring's `Validator`, not `SmartValidator`. They do not automatically interpret `AdvancedChecks` and continue running their logic when called by the binder. If custom rules need to depend on groups, use `SmartValidator`/Jakarta groups deliberately and write tests for specific hints.

### 8.4. Field errors and object errors

`errors.rejectValue("email", "blockedDomain")` creates an error tied to a field, whereas `errors.reject("duplicateAccount")` creates an object-level error. After binding, the controller can inspect:

```java
errors.getFieldErrors();  // Property-level errors
errors.getGlobalErrors(); // Object-level errors
errors.getAllErrors();    // Both kinds
```

Do not print only `getFieldErrors()` in an application whose custom validators emit global errors, as doing so drops part of the error information. The HTTP example in section 6 uses only `rejectValue`, so printing field errors suffices for the exercise.

## 9. Distinguishing argument validation from method validation in MVC

Starting in Spring Framework 6.1, MVC also has **built-in method validation** when handlers have constraints directly on method parameters or return values.

### Command-object validation

Example:

```java
@PostMapping("/signup")
public String submit(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult errors) {
    // ...
    return "done";
}
```

When nothing triggers whole-method validation, constraints on the object are evaluated through the argument binder. Registered global and local validators in the binder can both record errors; the controller receives the adjacent `BindingResult`.

### Direct method constraint

Example:

```java
@GetMapping("/reports")
public String report(@RequestParam("page") @Min(1) int page) {
    return "page=" + page;
}
```

`@Min(1)` is **on the method parameter itself**, not a field inside a DTO. In Spring MVC 6.1+, errors typically go through `HandlerMethodValidationException`. Do not assume `@InitBinder("signup")` or local Spring `Validator`s for `SignupForm` will handle this constraint.

When both a `@Valid` DTO and another direct method constraint are present, method validation can encompass cascaded validation of the DTO and take a different exception path. Therefore, test signatures that combine both instead of assuming all errors always land in the same `BindingResult`.

**Note:** For Spring MVC 6.1+ controllers, documentation recommends removing class-level `@Validated` when wanting built-in method validation; class-level annotation can activate Spring AOP method validation, which differs in proxies and exception types.

## 10. Binding conversion errors, HTTP statuses, and controller handling

Validators do not replace data binding. On a DTO with `Integer age`, if a request sends `age=abc`, conversion from `String` to `Integer` can fail before `@Min` ever evaluates. The binder records `typeMismatch` in `BindingResult` when the form binding path permits.

Other error paths:

| Issue | Origin | Handling |
| --- | --- | --- |
| `age=abc` with `@ModelAttribute` | `WebDataBinder` type conversion | `FieldError` `typeMismatch` can be observed |
| `age=17` with `@Min(18)` | Jakarta Bean Validation | `FieldError` with code `Min` |
| Username `admin` | Local `UsernameRuleValidator` | `FieldError` with code `reservedUsername` |
| Blocked email domain | Local `EmailDomainRuleValidator` | `FieldError` with code `blockedDomain` |
| Unparseable JSON body | HTTP message converter | May throw `HttpMessageNotReadableException` before validation |
| Direct `@RequestParam @Min` fails | Built-in MVC method validation | `HandlerMethodValidationException` |
| AOP `@Validated` service method fails | MethodValidationPostProcessor/provider | Exception type depends on AOP config |

**Having `BindingResult` does not mean the framework automatically chooses HTTP 400.** When a result immediately follows `@ModelAttribute`, the handler can run and choose the view/status itself. In the example, the controller uses `ResponseEntity.badRequest()`, whereas a server-rendered form app can re-render the view with field errors.

If no matching `BindingResult` is declared in the argument validation flow, Spring normally throws `MethodArgumentNotValidException` for the exception handler infrastructure to process. When standardizing JSON errors across endpoints, use `@ControllerAdvice`/`ResponseEntityExceptionHandler` for the exact exception types.

## 11. Testing multiple validators

A test suite should cover both **binder registration** and **error behavior**:

| Scenario | Expectation |
| --- | --- |
| Valid form | HTTP 200, no FieldErrors |
| `age=17` | `Min` error from global Bean Validation |
| `username=admin` | `reservedUsername` error from local validator |
| Email in `blocked.test` | `blockedDomain` error from local validator |
| All three rules fail | One `BindingResult` holds errors from multiple sources |
| `age=abc` | Binding/type conversion error present; business logic not dispatched |
| Another controller without matching `@InitBinder` | Not affected by the current controller's local policies |
| Another DTO receives an unsupported validator | No broad registration causing `supports` errors |
| Replacing `addValidators` with `setValidator` | Detects loss of constraints handled by the global validator in that binder pass |
| Global error via `reject` | Tests check `getGlobalErrors()` alongside `getFieldErrors()` |
| Using `@Validated(SomeGroup.class)` | Bean Validation and custom validators have expected group behavior |
| Direct method constraint on handler | Distinguishes the `HandlerMethodValidationException` path |

To test real Spring MVC behavior, prefer HTTP integration tests or `MockMvc` over merely calling:

```java
new SignupController(...).signup(form, errors);
```

Direct Java calls **do not initialize `WebDataBinder`, do not run `@InitBinder`, and do not invoke the global validator**. Unit tests for individual validators are still helpful for verifying each rule in isolation, yet cannot replace testing how Spring MVC wires them together.

## 12. Designing safe and maintainable validators

1. **Avoid per-request mutable state inside singleton validators.** Injected validator beans can handle many concurrent requests; use immutable state or local variables inside `validate()`.
2. **Do not mutate data during validation.** Normalization/conversion belongs to binding, formatters, services, or an explicit preprocessing layer. Validators should inspect and record errors rather than modifying `SignupForm`.
3. **Keep errors tied to stable codes.** With `rejectValue("username","reservedUsername",...)`, Spring generates specific-to-general message codes. Use `MessageSource` for localization instead of only hardcoding Vietnamese messages in code.
4. **Restrict binding with DTOs and allowed fields.** Never bind every field of a JPA entity straight to client requests. When property binding is used, consider `WebDataBinder#setAllowedFields(...)` to prevent mass assignment.
5. **Never use validators as authorization.** Even if a form is valid, the caller must still be authorized to create/modify the resource. Denylists and critical uniqueness rules must be enforced at the appropriate layer, including database constraints.
6. **Do not run expensive queries casually inside validators.** If existence checks are necessary, watch out for transactions, race conditions, and timeouts. For uniqueness, a pre-insert read check never replaces a database unique constraint.
7. **Avoid useless duplicate errors on a field.** When coordinating multiple rules, define business ordering or skip expensive checks when foundational data is already invalid; never silently clear another validator's errors.
8. **Do not replace the global validator unintentionally.** `setValidator`/`getValidator()` can drop Bean Validation annotations across one or more MVC paths. Prefer adding local validators when the requirement is scoped to one form.

## 13. Key takeaways and references

**Global validators** form the baseline for checking common Spring MVC constraints, usually supplied by `LocalValidatorFactoryBean`. **Local validators** apply controller- or model-attribute-specific rules via `@InitBinder`. **Multiple validators** can all record errors into `BindingResult` when registered with `binder.addValidators(...)`.

The most important distinction is **adding** versus **replacing**: `addValidators` keeps the existing list; `setValidator` and `replaceValidators` replace it. When combining Spring Validators with Jakarta Bean Validation, preserve the global validator if you still need `@NotBlank`, `@Min`, and `@Email`, and test through real requests to verify local rules run as well.

Official references:

- Spring Framework 6.2 — *Validation* (MVC global/local validators): https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html
- Spring Framework 6.2 — `@InitBinder`, controller and advice scope: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework 6.2 — *Validation* on controllers, direct method constraints: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — `DataBinder` Javadoc (`addValidators`, `setValidator`): https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2 — `WebDataBinder` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/web/bind/WebDataBinder.html
- Spring Framework 6.2 — `LocalValidatorFactoryBean` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html
- Spring Framework 6.2 — `Validator` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/Validator.html
- Jakarta Bean Validation 3.0 specification: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html