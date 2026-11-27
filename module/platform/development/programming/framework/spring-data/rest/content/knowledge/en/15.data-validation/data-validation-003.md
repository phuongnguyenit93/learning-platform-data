# Implementing Spring Validator with supports and validate

Spring Framework provides the \`org.springframework.validation.Validator\` interface to group data validation rules into a reusable component. A validator implements two methods: \`supports(Class<?> clazz)\` indicates the object type the validator handles, while \`validate(Object target, Errors errors)\` validates the actual data and records errors into the \`Errors\` object.

In Spring Data REST, validators can be registered on repository events such as \`beforeCreate\` and \`beforeSave\`. As a result, data sent through repository endpoints is validated before the save or resource creation operation proceeds. The same validator can also be used in Spring MVC or services if invoked appropriately in the corresponding processing flow.

## 1. What Problem Does Spring Validator Solve?

Suppose an application manages products. A product must have a name, a non-negative price, and a non-negative stock quantity. If these conditions are scattered across controllers, each endpoint may perform different checks. When more endpoints for creation, updating, or data import are added, rules easily become duplicated and inconsistent.

Spring Validator separates validation rules from controllers and repositories:

- \`supports\` determines which object types the validator applies to.
- \`validate\` checks the values of a specific object.
- \`Errors\` collects field-level or global errors.
- Spring MVC or Spring Data REST invokes the validator at the appropriate point in the request/repository lifecycle.

A validator does not save data itself and does not throw HTTP errors on its own. It records errors into \`Errors\`; the integrating layer above decides how to handle and return errors to the client.

## 2. The Validator Interface Has Two Core Methods

The Spring Validator interface resides in the \`org.springframework.validation\` package:

~~~java
public interface Validator {

    boolean supports(Class<?> clazz);

    void validate(Object target, Errors errors);
}
~~~

Meaning of each method:

| Method | Responsibility | Question to Answer |
|---|---|---|
| \`supports(Class<?> clazz)\` | Checks whether the class type is supported by the validator. | Does this validator handle this kind of object? |
| \`validate(Object target, Errors errors)\` | Checks the data and adds errors to Errors. | Does the current object violate any rules? |

\`supports\` receives only type information, not a specific instance. Therefore, do not check name, price, or entity state values inside this method.

\`validate\` receives the object to check and an \`Errors\` instance to record results. This method can add multiple errors in a single run so the client receives all issues to fix at once.

Spring typically calls \`supports\` before calling \`validate\`. When invoking a validator manually, you should also check \`supports(target.getClass())\` to avoid passing the wrong type.

## 3. Implementing a Validator for Product

Suppose the Product entity has name, price, and stock properties:

~~~java
public class Product {

    private String name;
    private BigDecimal price;
    private Integer stock;

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public Integer getStock() {
        return stock;
    }
}
~~~

Create the validator:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

import java.math.BigDecimal;

@Component
public class ProductValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return Product.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Product product = (Product) target;

        if (!StringUtils.hasText(product.getName())) {
            errors.rejectValue(
                "name",
                "product.name.required",
                "Product name must not be blank"
            );
        }

        BigDecimal price = product.getPrice();
        if (price == null) {
            errors.rejectValue(
                "price",
                "product.price.required",
                "Product price is required"
            );
        } else if (price.compareTo(BigDecimal.ZERO) < 0) {
            errors.rejectValue(
                "price",
                "product.price.negative",
                "Product price must not be negative"
            );
        }

        Integer stock = product.getStock();
        if (stock == null || stock < 0) {
            errors.rejectValue(
                "stock",
                "product.stock.invalid",
                "Stock quantity must be a non-negative number"
            );
        }
    }
}
~~~

The validator above checks three fields and can record multiple errors simultaneously. If name is empty, price is negative, and stock is invalid, all three errors are added to \`Errors\`; the client does not need to fix one error at a time across multiple requests.

\`Product.class.isAssignableFrom(clazz)\` accepts Product and subclasses of Product. If the validator must support only one exact class, you can use \`Product.class.equals(clazz)\`. Choose the check based on the inheritance model and proxy types used by your application.

## 4. Understanding supports(Class<?> clazz) Properly

\`supports\` is the step that selects a validator by object type. A validator for Product should not return true for every class, because Spring may invoke it with an incompatible object.

Example:

~~~java
@Override
public boolean supports(Class<?> clazz) {
    return Product.class.isAssignableFrom(clazz);
}
~~~

Some implementation options:

- \`Product.class.equals(clazz)\`: supports only Product exactly.
- \`Product.class.isAssignableFrom(clazz)\`: supports Product and subclasses.
- \`clazz != null && Product.class.isAssignableFrom(clazz)\`: adds a null check if the validator is called from custom code that might pass a null class.

Do not use \`target instanceof Product\` inside \`supports\`, because the method parameter is \`Class<?>\`, not an object instance. Also avoid checking field contents here; content checking belongs to \`validate\`.

If a validator supports multiple object types, you can check multiple classes:

~~~java
@Override
public boolean supports(Class<?> clazz) {
    return Product.class.isAssignableFrom(clazz)
        || ProductVariant.class.isAssignableFrom(clazz);
}
~~~

However, when two types have significantly different rules, splitting them into separate validators usually makes the code easier to understand and register.

## 5. Recording Errors with Errors and rejectValue

\`Errors\` is the API for validators to report errors. Two commonly used methods are:

~~~java
errors.rejectValue(
    "name",
    "product.name.required",
    "Product name must not be blank"
);

errors.reject(
    "product.invalid",
    "Product information is invalid"
);
~~~

\`rejectValue\` attaches an error to a field. Its parameters typically include:

1. The field name in the object, such as \`name\` or \`price\`.
2. An error code for looking up a message.
3. A default message if no matching message is found.

\`reject\` creates a global error not tied to a specific field. Use it for rules spanning multiple properties or the overall state of the object.

Other useful methods:

- \`errors.hasErrors()\`: checks if any errors exist.
- \`errors.hasFieldErrors("price")\`: checks for errors on a specific field.
- \`errors.getFieldErrors()\`: retrieves the list of field errors.
- \`errors.getGlobalErrors()\`: retrieves global errors.
- \`errors.getAllErrors()\`: retrieves all errors.

Do not use arbitrary field names. The field path must match the property understood by the binder or API representation; using the wrong name may leave the client unsure which field to fix.

## 6. Using Error Codes and MessageSource

Instead of hardcoding messages in every validator, you can use error codes so Spring looks up text in a MessageSource.

Example \`messages.properties\` file:

~~~properties
product.name.required=Product name is required.
product.price.required=Product price is required.
product.price.negative=Product price must not be negative.
product.stock.invalid=Stock must be zero or greater.
product.period.invalid=The availability end date must not precede the start date.
~~~

A Vietnamese version can be placed in \`messages_vi.properties\`:

~~~properties
product.name.required=Tên sản phẩm là bắt buộc.
product.price.required=Giá sản phẩm là bắt buộc.
product.price.negative=Giá sản phẩm không được âm.
product.stock.invalid=Số lượng tồn kho phải từ 0 trở lên.
product.period.invalid=Ngày kết thúc không được trước ngày bắt đầu.
~~~

The validator can pass an error code and a default message:

~~~java
errors.rejectValue(
    "price",
    "product.price.negative",
    "Product price must not be negative"
);
~~~

When resolving messages, Spring uses the error code and current locale to pick the appropriate message. The default message serves as a fallback if no matching message exists.

Error codes should be stable and domain-meaningful. Do not embed sensitive data or raw client-supplied values directly in error messages unless necessary.

## 7. Validating Multi-Field Rules

Some rules cannot be checked on each field in isolation. For example, the end date must be on or after the start date.

~~~java
public class Promotion {

    private LocalDate startsOn;
    private LocalDate endsOn;

    public LocalDate getStartsOn() {
        return startsOn;
    }

    public LocalDate getEndsOn() {
        return endsOn;
    }
}
~~~

Validator:

~~~java
@Component
public class PromotionValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return Promotion.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Promotion promotion = (Promotion) target;

        LocalDate start = promotion.getStartsOn();
        LocalDate end = promotion.getEndsOn();

        if (start != null && end != null && end.isBefore(start)) {
            errors.rejectValue(
                "endsOn",
                "product.period.invalid",
                "The end date must not precede the start date"
            );
        }
    }
}
~~~

The error is attached to \`endsOn\` so the UI knows which field needs correction. If the rule does not belong to a specific field, you can use \`errors.reject(...)\` to create a global error.

You can check conditions spanning multiple fields in the same validator, but keep each rule clear and readable. For complex business rules that need to query multiple data sources or modify state, consider placing that processing in the domain/service and keeping the validator focused on input validation within an appropriate scope.

## 8. Registering Validators for Spring Data REST Repository Events

Spring Data REST has a repository event mechanism to invoke validators before or after repository operations. For validating data before create and update, two commonly used events are:

- \`beforeCreate\`: before creating a new resource.
- \`beforeSave\`: before saving changes to an existing resource.

Registering a validator via \`RepositoryRestConfigurer\`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.event.ValidatingRepositoryEventListener;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;

@Configuration
public class RepositoryValidationConfiguration
        implements RepositoryRestConfigurer {

    private final ProductValidator productValidator;

    public RepositoryValidationConfiguration(
            ProductValidator productValidator) {
        this.productValidator = productValidator;
    }

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener validatingListener) {

        validatingListener.addValidator("beforeCreate", productValidator);
        validatingListener.addValidator("beforeSave", productValidator);
    }
}
~~~

Spring manages \`ProductValidator\` as a bean and injects it into the configuration. When Spring Data REST emits the corresponding event, the listener invokes the registered validators. \`supports\` ensures the validator only handles Product; if an event is emitted for another domain type, the validator skips that type.

If you only register \`beforeCreate\`, newly created data is checked, but updates may not run the same rules. If you only register \`beforeSave\`, creations may not be checked as intended. Choose events matching the API operations your repository exposes.

Other event names may include \`beforeLinkSave\`, \`afterCreate\`, \`afterSave\`, and \`beforeDelete\`. Data validators are usually attached to pre-save events; post-save events are better suited for post-operation handling rather than preventing invalid data from being written.

## 9. Distinguishing Repository Event Validation from Spring MVC Binding

Spring Validator can also be used in Spring MVC controllers through \`WebDataBinder\`. Example:

~~~java
@Controller
public class ProductController {

    private final ProductValidator productValidator;

    public ProductController(ProductValidator productValidator) {
        this.productValidator = productValidator;
    }

    @InitBinder("product")
    void initProductBinder(WebDataBinder binder) {
        binder.addValidators(productValidator);
    }

    @PostMapping("/products")
    public String create(
            @ModelAttribute("product") Product product,
            BindingResult result) {

        if (result.hasErrors()) {
            return "products/form";
        }

        // Call service to process valid data.
        return "redirect:/products";
    }
}
~~~

In the example, \`@InitBinder("product")\` registers the validator for the model attribute named product. When Spring MVC performs binding and validation according to the handler configuration, errors are recorded in \`BindingResult\`.

The two integration mechanisms differ:

| Mechanism | Where Registered | When Invoked |
|---|---|---|
| Spring MVC | \`@InitBinder\` and \`WebDataBinder\` | During controller binding/validation. |
| Spring Data REST | \`ValidatingRepositoryEventListener\` via \`RepositoryRestConfigurer\` | When a repository event is emitted, e.g., before create or save. |

If the application has both custom controllers and auto-exposed repository endpoints, you can share the same validator across both places. Do not assume registration in \`@InitBinder\` automatically applies to Spring Data REST or vice versa.

## 10. Combining Spring Validator with Bean Validation

Spring Validator (\`org.springframework.validation.Validator\`) differs from the Bean Validation API (\`jakarta.validation.Validator\`). Both APIs share similar goals, but their contracts and integration mechanisms differ.

Bean Validation typically uses annotations on fields or classes:

~~~java
public class ProductRequest {

    @NotBlank
    private String name;

    @NotNull
    @DecimalMin("0.00")
    private BigDecimal price;
}
~~~

Spring Validator is suitable when you need to write rules in Java, use services or conditional logic, or integrate directly with \`Errors\`.

Both can be used together:

- Bean Validation handles simple declarative constraints such as requiredness, length, value ranges, and format.
- Spring Validator handles business rules or conditions depending on multiple properties.
- Both should return consistent errors so clients can understand and correct data.

Spring provides adapters integrating Bean Validation with Spring's validation system, such as \`LocalValidatorFactoryBean\`. When combining multiple validators, avoid registering the same rule twice and causing duplicate messages.

## 11. How Are Validation Errors Returned to the Client?

When a validator is invoked by Spring Data REST and adds errors to \`Errors\`, the repository event flow can halt the operation and Spring Data REST handles the validation failure as an HTTP error response, typically 400 Bad Request. The exact response body structure depends on the version, exception handlers, and application configuration.

Clients should rely on HTTP status codes and the error contract published by the API. Do not assume all applications return the same JSON shape or the same field names for errors.

In Spring MVC, a controller can inspect \`BindingResult\`:

~~~java
if (result.hasErrors()) {
    return ResponseEntity.badRequest().body(
        result.getFieldErrors().stream()
            .map(error -> Map.of(
                "field", error.getField(),
                "code", error.getCode(),
                "message", error.getDefaultMessage()
            ))
            .toList()
    );
}
~~~

This example builds a simple error response for a custom controller. If your application has a standard error format, use a unified error DTO or \`@ControllerAdvice\` instead of having each controller build a different structure.

Do not return stack traces, SQL, internal details, or sensitive data in validation messages. Messages should state the field and condition to fix, without exposing implementation details.

## 12. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Validator is not called | Not registered on the right repository event or binder. | Check the registration point and corresponding event. |
| \`supports\` always returns false | Incorrect class comparison or wrong domain type assumed. | Check the passed class and use \`isAssignableFrom\` when subclasses need support. |
| ClassCastException inside \`validate\` | Validator invoked directly with an incompatible type. | Check \`supports\` before invoking and register the validator within the right scope. |
| Create is validated but update is not | Only \`beforeCreate\` was registered. | Also register \`beforeSave\` if updates require the rules. |
| Errors not attached to the expected field | Wrong field path passed to \`rejectValue\`. | Use the property name matching the object being validated. |
| Client does not display an appropriate message | Error code has no message or locale is not configured. | Add message properties and a default message. |
| A rule runs twice | Same logic registered through multiple mechanisms. | Designate a single owner for the rule or coordinate them clearly. |
| Data from services is not validated | Spring Data REST repository events are not a universal validation mechanism for all call paths. | Invoke validator/service validation on non-REST write paths when needed. |

## 13. Workflow for Using a Validator

When implementing a validator for a domain type:

1. Identify the input rules to check and the relevant fields.
2. Create a class implementing \`org.springframework.validation.Validator\`.
3. Write \`supports\` to accept only matching classes.
4. Write \`validate\` to check data and record errors into \`Errors\`.
5. Use \`rejectValue\` for field errors and \`reject\` for global errors.
6. Register error codes and messages in MessageSource if multilingual support is needed.
7. Register the validator with \`beforeCreate\` and \`beforeSave\` for repository events that need protection.
8. Register separately with \`WebDataBinder\` if custom Spring MVC controllers also need the validator.
9. Handle validation errors according to the API's HTTP contract.
10. Ensure write paths outside Spring Data REST also have appropriate validation in the service/domain layer.

Spring Validator separates type selection and data checking into two clear responsibilities: \`supports\` decides whether the validator applies to a class; \`validate\` checks the instance and records errors into \`Errors\`. Registering validators on the right repository events lets Spring Data REST validate data before create/save, while \`WebDataBinder\` serves custom Spring MVC controllers. Combined with Bean Validation and service/domain validation, input rules are enforced consistently across multiple write paths.
