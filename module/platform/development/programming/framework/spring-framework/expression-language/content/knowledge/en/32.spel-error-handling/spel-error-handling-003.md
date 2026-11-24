# AccessException from Accessors or Resolvers

In Spring Expression Language (SpEL), extension points such as **PropertyAccessor**, **MethodResolver**, **ConstructorResolver**, and **BeanResolver** are responsible for accessing properties, finding methods, finding constructors, or resolving beans. Several operations of these interfaces declare that they may throw **AccessException** from the `org.springframework.expression` package.

`AccessException` indicates that an accessor or resolver encountered a problem while performing its access or resolution responsibility. SpEL typically converts this error into an appropriate **SpelEvaluationException** for the operation being evaluated and preserves the original exception as the cause.

Two situations must be distinguished: the extension point does not support the target or member under consideration, and the extension point actually encounters an error while accessing it. For the unsupported case, the accessor/resolver should return `false` or `null` according to the interface contract. Throw `AccessException` only when a real failure occurs. If an exception is used to signal “not applicable”, resolution may stop early and hide another accessor or resolver capable of handling it.

## 1. What Is AccessException?

### 1.1. Location in Spring Expression

`AccessException` resides in the package:

~~~java
org.springframework.expression.AccessException
~~~

This exception is used by the interfaces extending SpEL's access mechanism. It allows an accessor or resolver to report that reading, writing, finding a method, finding a constructor, or retrieving a bean encountered an error.

`AccessException` can carry a message and a root cause:

~~~java
throw new AccessException(
        "Could not read customer profile",
        cause
);
~~~

Preserving the cause helps the caller identify the original error, such as a reflection error, a data access error, or an error from a custom adapter.

### 1.2. AccessException Is Not a Syntax Error

An expression can parse successfully yet still fail during evaluation because an accessor or resolver cannot complete the operation.

Example:

~~~java
customer.email
~~~

The parser can create an `Expression` from the syntax above. During evaluation, SpEL needs to find a `PropertyAccessor` that can read the `email` property. If the matching accessor encounters an access error and throws `AccessException`, evaluation will fail.

Therefore, the phases must be separated:

1. Parse source into an `Expression`.
2. Resolve target object, property, method, constructor, or bean.
3. Execute the access operation.
4. Return the result or raise an evaluation error.

`AccessException` belongs to the resolution or access execution steps, not to parser syntax recognition errors.

### 1.3. Distinguishing from EvaluationException

**EvaluationException** is the broader exception hierarchy used to represent errors during expression evaluation. **SpelEvaluationException** is the concrete implementation of evaluation errors in SpEL.

`AccessException` is declared on extension points and is usually converted by SpEL into a `SpelEvaluationException` when the error leaves the evaluation process.

You can visualize this as:

~~~text
Custom PropertyAccessor / MethodResolver
                 |
                 | throws AccessException
                 v
       SpEL evaluation operation
                 |
                 | wraps with evaluation context
                 v
        SpelEvaluationException
                 |
                 | preserves original cause
                 v
             AccessException
~~~

When handling errors, inspect both the outer exception and the cause. Looking only at the outer message may not be enough to determine which accessor or resolver encountered the problem.

### 1.4. Do Not Confuse with Spring Security AccessDeniedException

`AccessException` in the `org.springframework.expression` package is an exception belonging to SpEL's access mechanism. It differs from authorization exceptions in Spring Security, such as **AccessDeniedException**.

The two exceptions have similar names but belong to different APIs and serve different purposes:

- Expression `AccessException`: a SpEL extension point could not complete the access/resolution operation.
- Security `AccessDeniedException`: an action is denied according to security policy.

Do not use SpEL's `AccessException` as a general authorization mechanism. Business authorization should be checked at the service or security layer.

## 2. Interfaces That Can Throw AccessException

### 2.1. PropertyAccessor

`PropertyAccessor` reads and writes properties on a target object. The methods `canRead`, `read`, `canWrite`, and `write` can declare `AccessException`.

~~~java
public interface PropertyAccessor {

    Class<?>[] getSpecificTargetClasses();

    boolean canRead(
            EvaluationContext context,
            Object target,
            String name
    ) throws AccessException;

    TypedValue read(
            EvaluationContext context,
            Object target,
            String name
    ) throws AccessException;

    boolean canWrite(
            EvaluationContext context,
            Object target,
            String name
    ) throws AccessException;

    void write(
            EvaluationContext context,
            Object target,
            String name,
            Object newValue
    ) throws AccessException;
}
~~~

The methods have distinct meanings:

- **canRead** indicates whether the accessor can read the requested property.
- **read** performs the read and returns a `TypedValue`.
- **canWrite** indicates whether the accessor can write the property.
- **write** performs the value update.

If the target is not of a type supported by the accessor or the property is outside the accessor's scope, return `false` in `canRead`/`canWrite`. If the accessor has already determined it can handle the request but the actual operation fails, throw `AccessException`.

### 2.2. MethodResolver

`MethodResolver` finds a method matching the target, method name, and argument types:

~~~java
public interface MethodResolver {

    MethodExecutor resolve(
            EvaluationContext context,
            Object targetObject,
            String name,
            List<TypeDescriptor> argumentTypes
    ) throws AccessException;
}
~~~

If the resolver does not handle the target or cannot find a matching method, it should return `null`. If the resolver encounters an actual failure while searching for or inspecting the method, it can throw `AccessException`.

`MethodResolver` returns a `MethodExecutor` once an execution strategy is found. `MethodExecutor` can also throw `AccessException` when the invocation cannot complete:

~~~java
public interface MethodExecutor {

    TypedValue execute(
            EvaluationContext context,
            Object target,
            Object... arguments
    ) throws AccessException;
}
~~~

Consequently, errors can occur in both the method lookup phase and the method execution phase.

### 2.3. ConstructorResolver and ConstructorExecutor

`ConstructorResolver` finds a matching constructor for `new` expressions:

~~~java
public interface ConstructorResolver {

    ConstructorExecutor resolve(
            EvaluationContext context,
            String typeName,
            List<TypeDescriptor> argumentTypes
    ) throws AccessException;
}
~~~

The resolver returns a `ConstructorExecutor` when it finds a way to instantiate the type. If it does not support the type or there is no matching constructor, the resolver should return `null` to indicate no candidate.

If an access or reflection error occurs during resolution/execution, `AccessException` may be thrown. `ConstructorExecutor` is responsible for performing the instantiation and can also report access errors.

### 2.4. BeanResolver

`BeanResolver` resolves beans by name:

~~~java
public interface BeanResolver {

    Object resolve(
            EvaluationContext context,
            String beanName
    ) throws AccessException;
}
~~~

If the context supports bean references, the expression:

~~~java
@pricingService
~~~

asks `BeanResolver` to find the `pricingService` bean.

If the bean does not exist or the resolver cannot retrieve the bean, the operation may fail. With custom resolvers, distinguish a bean name disallowed by policy from an actual error from `BeanFactory` or the lookup mechanism.

### 2.5. Other Components Do Not Share the Same Contract

Not every error in SpEL is represented by `AccessException`. For example, `TypeConverter` can raise conversion errors; `TypeLocator` can report errors when failing to resolve a type; the parser can report syntax errors.

When investigating, identify which extension point is running rather than catching a generic exception and assuming every problem is an `AccessException`.

## 3. When Should You Return false or null?

### 3.1. PropertyAccessor Does Not Support the Target

Suppose an accessor only reads properties from `CustomerView`. When the target is `Order`, the accessor does not support that object:

~~~java
@Override
public boolean canRead(
        EvaluationContext context,
        Object target,
        String name) {

    return target instanceof CustomerView
            && "email".equals(name);
}
~~~

If the target is `Order` or the property is not `email`, returning `false` signals that this accessor is not applicable. SpEL can continue trying other accessors.

Do not throw `AccessException` simply because the target is not `CustomerView`. That is a normal case when multiple accessors participate in resolution.

### 3.2. MethodResolver Does Not Find the Method

A resolver only handles the `calculateRisk` method on `CustomerView`. If the expression asks for `formatName`, the resolver should return `null`:

~~~java
if (!(targetObject instanceof CustomerView)
        || !"calculateRisk".equals(name)) {
    return null;
}
~~~

A `null` value means this resolver does not provide a `MethodExecutor` for that call. SpEL can continue trying other resolvers.

If the resolver throws `AccessException` for every method other than `calculateRisk`, it can prevent subsequent resolvers from handling methods they support.

### 3.3. BeanResolver and Disallowed Names

For a resolver with an allowlist, a bean name not on the list is not a lookup system error. It is a policy decision.

The resolver can reject it with an appropriate exception so the expression cannot proceed. However, recognize this as a permission denial, not a case where a resolver simply does not support a target type.

Do not let access permission errors silently turn into “bean not found” if the application needs to record denied attempts.

### 3.4. When Is AccessException Appropriate?

Throw `AccessException` when the accessor or resolver has been selected to handle the operation but cannot fulfill its responsibility due to an actual issue, such as:

- The data backend used by the accessor is unreachable.
- Reflection encounters an access permission error.
- An adapter needs metadata, but the metadata is corrupted or unreadable.
- `BeanFactory` or the bean lookup system encounters an error during resolution.
- `MethodExecutor` cannot execute the operation per contract.
- `ConstructorExecutor` cannot invoke the constructor due to an access error.

Do not use exceptions in place of the `false`/`null` values defined by the interface for non-matching cases.

## 4. How SpEL Handles AccessException

### 4.1. In Property Resolution

When an expression accesses a property, SpEL checks the `PropertyAccessor` instances that can handle the target. An accessor can return `false` if it cannot read that property.

If an accessor throws `AccessException` while checking or reading the property, SpEL may convert the error into a `SpelEvaluationException` tied to the position and property name being evaluated.

This helps callers know which property operation caused the expression to fail. The original exception remains important for finding the cause inside the accessor.

### 4.2. In Method Resolution

When an expression calls a method, SpEL queries `MethodResolver` instances in order to find a suitable `MethodExecutor`.

A resolver returns `null` when it does not handle the call. If a resolver throws `AccessException`, SpEL treats it as a problem during resolution and typically converts it into a `SpelEvaluationException` for the method being invoked.

Therefore, a custom resolver should not throw `AccessException` just to say “I do not handle this method”. Return `null` so other resolvers have a chance to handle it.

### 4.3. In Constructor Resolution

Constructor expressions also need a resolver to find the constructor and an executor to run it. If the resolver has no candidate, return `null`. If accessing the constructor encounters an error, `AccessException` may be converted into an evaluation error.

Example:

~~~java
new com.example.domain.Customer('C-100')
~~~

If a custom constructor resolver encounters a reflection error while inspecting the `Customer` constructor, preserve the cause in `AccessException` so investigation does not lose information.

### 4.4. In Bean Resolution

When an expression references a bean, `BeanResolver` performs the lookup. `AccessException` from the resolver is usually converted into a `SpelEvaluationException` describing the bean resolution problem.

Example:

~~~java
@pricingService.calculate(order)
~~~

If the resolver cannot retrieve `pricingService` due to a genuine error from `BeanFactory`, preserve the cause. If the bean name is not allowed by the allowlist, clearly log the policy error type in internal logs without exposing unnecessary details to end users.

### 4.5. Errors in Executors Differ from Not Finding a Candidate

You must distinguish:

- Resolver finds no candidate and returns `null`: SpEL continues checking other resolvers; if no resolver matches, the expression reports that the method/constructor could not be found.
- Resolver throws `AccessException`: the resolution process encountered an error.
- Executor throws `AccessException`: a candidate was selected, but the execution operation failed.

These three cases have different meanings and should be handled separately when writing custom extension points.

## 5. Custom PropertyAccessor Example

### 5.1. Data Model

Suppose the application has a view type storing dynamic attributes:

~~~java
public class CustomerView {

    private final Map<String, Object> attributes;

    public CustomerView(Map<String, Object> attributes) {
        this.attributes = new HashMap<>(attributes);
    }

    public boolean hasAttribute(String name) {
        return attributes.containsKey(name);
    }

    public Object getAttribute(String name) {
        return attributes.get(name);
    }

    public void setAttribute(String name, Object value) {
        attributes.put(name, value);
    }
}
~~~

We want SpEL to read the attributes as properties:

~~~java
email
region
customerTier
~~~

### 5.2. Implementing the Accessor

~~~java
public class CustomerViewAccessor implements PropertyAccessor {

    @Override
    public Class<?>[] getSpecificTargetClasses() {
        return new Class<?>[] { CustomerView.class };
    }

    @Override
    public boolean canRead(
            EvaluationContext context,
            Object target,
            String name) {

        return target instanceof CustomerView view
                && view.hasAttribute(name);
    }

    @Override
    public TypedValue read(
            EvaluationContext context,
            Object target,
            String name) throws AccessException {

        if (!(target instanceof CustomerView view)) {
            throw new AccessException(
                    "Unsupported target for CustomerViewAccessor"
            );
        }

        if (!view.hasAttribute(name)) {
            throw new AccessException(
                    "Customer attribute is no longer available: " + name
            );
        }

        return new TypedValue(view.getAttribute(name));
    }

    @Override
    public boolean canWrite(
            EvaluationContext context,
            Object target,
            String name) {

        return target instanceof CustomerView;
    }

    @Override
    public void write(
            EvaluationContext context,
            Object target,
            String name,
            Object newValue) throws AccessException {

        if (!(target instanceof CustomerView view)) {
            throw new AccessException(
                    "Unsupported target for CustomerViewAccessor"
            );
        }

        view.setAttribute(name, newValue);
    }
}
~~~

In this example:

- `canRead` returns `false` when the target is not a `CustomerView` or the attribute does not exist.
- `read` throws `AccessException` if the target state changes after `canRead` returned `true`.
- `canWrite` only allows writing on `CustomerView`.
- `write` throws `AccessException` if the target is of the wrong type.

In a real system, clearly define the policy for writable attributes. Do not allow writing any arbitrary key if expressions can come from users.

### 5.3. Registering the Accessor

~~~java
CustomerView view = new CustomerView(
        Map.of(
                "email", "user@example.com",
                "region", "APAC"
        )
);

StandardEvaluationContext context =
        new StandardEvaluationContext(view);

context.addPropertyAccessor(new CustomerViewAccessor());

ExpressionParser parser = new SpelExpressionParser();

String email = parser
        .parseExpression("email")
        .getValue(context, String.class);
~~~

If the accessor is registered on the context, SpEL can use it to read properties that the accessor supports.

If you want to write:

~~~java
parser.parseExpression("region")
        .setValue(context, "EU");
~~~

The operation should only be allowed when the application genuinely needs to update attributes and write permissions have been verified.

### 5.4. Backend Errors Inside an Accessor

If an accessor reads data from a backend instead of an in-memory `Map`, wrap the error meaningfully:

~~~java
try {
    Object value = profileStore.read(customerId, name);
    return new TypedValue(value);
} catch (ProfileStoreException ex) {
    throw new AccessException(
            "Could not read customer profile attribute",
            ex
    );
}
~~~

Do not return `null` to hide a failing backend. `null` can be a valid data value; it should not represent an access error.

## 6. Custom MethodResolver Example

### 6.1. Resolver Handling Only One Method

Suppose `CustomerView` has a pure method `canArchive()`:

~~~java
public class CustomerView {

    public boolean canArchive() {
        // Read-only, deterministic rule
        return true;
    }
}
~~~

A resolver can handle only the `canArchive` call with no arguments:

~~~java
public class CustomerMethodResolver implements MethodResolver {

    @Override
    public MethodExecutor resolve(
            EvaluationContext context,
            Object targetObject,
            String name,
            List<TypeDescriptor> argumentTypes)
            throws AccessException {

        if (!(targetObject instanceof CustomerView)) {
            return null;
        }

        if (!"canArchive".equals(name)
                || !argumentTypes.isEmpty()) {
            return null;
        }

        return (ctx, target, arguments) -> {
            if (!(target instanceof CustomerView view)) {
                throw new AccessException(
                        "Unexpected target for canArchive"
                );
            }

            return new TypedValue(view.canArchive());
        };
    }
}
~~~

The resolver returns `null` if the target or signature is outside its supported scope. It returns a `MethodExecutor` only after identifying a matching call.

### 6.2. Registering the Resolver

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(customerView);

context.addMethodResolver(new CustomerMethodResolver());

Boolean canArchive = parser
        .parseExpression("canArchive()")
        .getValue(context, Boolean.class);
~~~

When the method is called, the executor performs the behavior and returns a `TypedValue`.

### 6.3. Error Handling in a Resolver

If a resolver must read metadata or look up configuration to identify a method, distinguish:

- No method supported by the resolver: return `null`.
- Metadata does not exist because the target is of the wrong type: usually return `null`.
- Required metadata is corrupted or the data source is unreachable: throw `AccessException` with cause.
- Method was selected, but execution logic fails: the executor reports an appropriate error.

Do not throw `AccessException` for every method with a different name. Doing so can block the default resolver or other resolvers.

## 7. How to Preserve Cause and Create Helpful Messages

### 7.1. Using the Constructor with Cause

When catching an exception from a library or backend, always preserve the cause:

~~~java
try {
    return repository.readProperty(targetId, propertyName);
} catch (RepositoryException ex) {
    throw new AccessException(
            "Failed to read expression property",
            ex
    );
}
~~~

Do not just concatenate `ex.getMessage()` into a string and drop the cause. Preserving the cause allows logs and debuggers to trace the original exception type and stack trace.

### 7.2. Messages Should Include Context

A good message should help identify the failed operation:

- Which property was being read or written.
- Which method was being resolved.
- Which type was being instantiated.
- Which bean name was being looked up.
- Which data category the target belongs to, if that information is safe to log.

Do not put sensitive data, tokens, full request payloads, or personal information into exception messages.

### 7.3. Do Not Let Exceptions Hide the Error Category

If all errors are wrapped in a generic `AccessException` without a cause or context, operators will struggle to distinguish configuration errors, data errors, and backend errors.

Use specific messages at the extension point layer and preserve the root cause. At the API layer, translate the error into an appropriate message without exposing internal structure.

## 8. Handling SpelEvaluationException at the Application Layer

### 8.1. Catching Exceptions at the Evaluation Boundary

You can catch `EvaluationException` around the evaluation call:

~~~java
try {
    Object result = expression.getValue(context);
    return result;
} catch (SpelEvaluationException ex) {
    // Log by error code and cause
    throw new IllegalStateException(
            "Could not evaluate configured expression",
            ex
    );
}
~~~

If the API needs to return validation or configuration errors, map them to application-layer exceptions. Do not expose reflection or backend details directly to clients.

### 8.2. Inspecting the Cause Chain

To determine whether an error originated from an `AccessException`:

~~~java
Throwable cause = ex;

while (cause != null) {
    if (cause instanceof AccessException) {
        // SpEL extension point reported an access error
        break;
    }

    cause = cause.getCause();
}
~~~

The cause chain may contain intermediate exceptions. Do not assume `AccessException` is always the direct cause if other integration layers also wrapped the error.

### 8.3. Categorizing by Phase

Record at least these categories:

| Error Group | Meaning | Investigation Direction |
|---|---|---|
| Parse failure | Source has invalid syntax | Check the expression source |
| Property access failure | Accessor could not read/write property | Check target, property, and accessor |
| Method resolution failure | No executor found or resolver failed | Check name, arguments, and resolver |
| Constructor resolution failure | Constructor not found or could not be invoked | Check type, signature, and constructor resolver |
| Bean resolution failure | BeanResolver could not retrieve bean | Check bean name, allowlist, and BeanFactory |
| Conversion failure | Argument or result could not be converted | Check TypeConverter/ConversionService |
| Business exception | Code inside getter/method/constructor failed | Investigate business logic and cause |

Do not convert every error into `false`, `null`, or an empty collection. Doing so can make an invalid rule appear valid and hide infrastructure failures.

## 9. Common Implementation Mistakes

| Implementation | Consequence | Fix |
|---|---|---|
| canRead throws AccessException when target is unsupported | Subsequent accessors may not be tried | Return false |
| canWrite throws AccessException when property does not belong to accessor | Blocks other writable accessors | Return false |
| MethodResolver throws exception when method name does not match | Other resolvers get no chance to handle it | Return null |
| ConstructorResolver throws exception when no candidate exists | Constructor resolution aborts early | Return null |
| read/write returns null or ignores backend error | Hides errors and produces ambiguous results | Throw AccessException with cause |
| Losing cause when wrapping exceptions | Difficult to find root cause | Use the AccessException constructor with cause |
| Catching all SpelEvaluationException and returning false | Failing expression is treated as condition not met | Categorize errors and report at the right layer |
| Using AccessException instead of authorization | Mixes extension point errors with security policy | Check permissions at the service/security layer |
| Returning internal exception messages to clients | May expose bean names, class names, or sensitive data | Map to safe messages |
| Using an accessor that supports all target classes | May conflict with other accessors | Declare accurate specific target classes |

## 10. Testing Accessors and Resolvers

### 10.1. Testing Unsupported Cases

For a custom accessor, verify that an unsuitable target returns `false`:

~~~java
assertFalse(
        accessor.canRead(context, new OrderView(), "email")
);
~~~

For a resolver, verify that an out-of-scope method returns `null`:

~~~java
assertNull(
        resolver.resolve(
                context,
                new OrderView(),
                "unknownMethod",
                List.of()
        )
);
~~~

These tests are important because they ensure the extension point allows other resolvers/accessors to continue processing.

### 10.2. Testing AccessException from Real Operations

Create a scenario where the accessor has determined it can read the property, but the backend fails. Verify:

- `AccessException` is thrown.
- The root cause is preserved.
- SpEL converts the error into `SpelEvaluationException` during evaluation.
- The application does not misinterpret the error as a missing property or a `null` result.

Example of verifying the outer exception type:

~~~java
assertThrows(
        SpelEvaluationException.class,
        () -> parser.parseExpression("email")
                .getValue(context)
);
~~~

Then inspect the cause chain to confirm `AccessException` or the original exception is preserved according to the implementation's design.

### 10.3. Testing read and write

A `PropertyAccessor` may support reading without supporting writing. Test separately:

- `canRead` is `true` and `read` returns the expected `TypedValue`.
- `canRead` is `false` when the property does not belong to the accessor.
- `canWrite` is `false` when the target or property is unsupported.
- `write` updates the value accurately when allowed.
- `read`/`write` throws `AccessException` when the actual operation fails.
- No custom accessor blocks other accessors solely because the target is unsuitable.

### 10.4. Testing Method and Constructor Executors

For a custom resolver, test both the `resolve` and `execute` steps:

- Unsupported target: `null`.
- Mismatched name or arity: `null`.
- Valid candidate: returns an executor.
- Executor succeeds: returns the expected `TypedValue`.
- Executor fails: `AccessException` preserves the cause.
- Default resolvers can still handle methods outside the custom resolver's scope.

## 11. Workflow for Investigating AccessException in an Application

When encountering `AccessException` or a `SpelEvaluationException` whose cause is `AccessException`, follow this sequence:

1. **Identify the operation.** Is the expression reading a property, writing a property, calling a method, instantiating an object, or referencing a bean?
2. **Find the extension point.** Identify which `PropertyAccessor`, `MethodResolver`, `ConstructorResolver`, or `BeanResolver` is being used.
3. **Check the target.** Confirm the target class and argument types match what the extension point expects.
4. **Distinguish unsupported from real errors.** Unsupported cases must return `false`/`null`; only actual failures should throw `AccessException`.
5. **Read the cause chain.** Locate the underlying reflection, backend, or internal logic exception causing the failure.
6. **Check registration order.** Is a custom accessor/resolver blocking other extension points?
7. **Check permissions.** If the error is a business access denial, verify authorization at the service layer.
8. **Fix at the extension point.** Preserve the interface contract and provide contextual messages.
9. **Test both branches.** Unsupported cases must allow other resolvers to handle them; real errors must propagate clearly.

This workflow avoids the common workaround of catching exceptions and returning `false` or `null`, which can lose the cause and mask configuration errors.

## 12. Summary

`AccessException` is an exception in the `org.springframework.expression` package used by extension points to report errors during access or resolution. SpEL typically converts it into a `SpelEvaluationException` associated with the operation being evaluated and preserves the cause for investigation.

- `PropertyAccessor` uses `AccessException` in read/write operations and access capability checks.
- `MethodResolver` and `ConstructorResolver` use it when candidate lookup encounters an error; executors can also report errors at execution time.
- `BeanResolver` uses it when bean lookup cannot complete.
- Unsupported targets/members should return `false` or `null` per contract; only actual errors should throw `AccessException`.
- Preserve causes, classify errors by phase, and do not turn every error into `false`/`null`.
- SpEL's `AccessException` differs from Spring Security's `AccessDeniedException`.
- Authorization, validation, and resource limits remain the responsibility of the application layer.

When writing custom accessors or resolvers, keep “not applicable” and “applicable but operation failed” clearly separated. This lets SpEL continue searching for the right extension point when needed, while retaining accurate details when an access operation genuinely fails.