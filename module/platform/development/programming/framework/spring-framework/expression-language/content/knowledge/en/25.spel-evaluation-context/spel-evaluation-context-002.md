# `SimpleEvaluationContext` and a Safer SpEL Evaluation Surface

## Objectives

`SimpleEvaluationContext` is an implementation of `EvaluationContext` designed for data binding scenarios and expression evaluation with a restricted feature set. It allows an application to expose only the capabilities needed for a rule or expression, instead of providing full reflection capabilities by default like `StandardEvaluationContext`.

`SimpleEvaluationContext` is suitable when an expression needs to read or update properties of an object, or needs to invoke a set of allowed instance methods. It excludes powerful features such as type references, constructor invocations, and bean references. This provides a narrower evaluation surface, though it is not a complete sandbox: allowed getters or methods can still execute code, access data, or have side effects.

## 1. Why is SimpleEvaluationContext needed?

`StandardEvaluationContext` provides fuller SpEL evaluation capabilities, including reflective property/method access, type references, constructor resolution, bean resolution when configured, and other extension mechanisms. This flexibility is useful for internal expressions controlled by the application, but can be overly broad when evaluating rules or expressions from external configuration.

`SimpleEvaluationContext` is designed for scenarios that only require a subset of syntax and access permissions. The application must explicitly choose how properties are accessed and whether to enable method invocation.

| Criterion | `SimpleEvaluationContext` | `StandardEvaluationContext` |
| --- | --- | --- |
| Purpose | Data binding and expressions with a restricted permission set. | SpEL evaluation with more full-featured capabilities. |
| Property access | Choose data-binding accessors or custom accessors. | Has reflective property access by default and can be further configured. |
| Property writing | Can be enabled via read-write builder and write-supporting accessor. | Writable if the accessor supports it. |
| Method invocation | Disabled by default; instance methods can be explicitly enabled. | Has reflective method resolution by default. |
| Type reference `T(...)` | Not supported. | Supported via `TypeLocator`. |
| Constructor `new ...` | Not supported. | Supported via `ConstructorResolver`. |
| Bean reference `@bean` | Not supported. | Can be supported when `BeanResolver` is configured. |

Choose the context according to the exact capabilities the expression needs. If a rule only compares and reads properties, there is no need to enable method invocation or switch to the full context.

## 2. Creating a read-only context

The simplest way is to use the `forReadOnlyDataBinding()` builder. This context configures property access in read-only mode and does not enable method invocation:

```java
ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

CustomerView customer = new CustomerView("Lan", true, 28);
Expression expression = parser.parseExpression(
        "active == true and age >= 18");

Boolean eligible = expression.getValue(
        context, customer, Boolean.class);
```

In this example, SpEL reads the `active` and `age` properties from the root object `customer`, then computes the Boolean result. The expression does not need to call arbitrary methods, create new objects, or reference classes.

Read-only mode means the expression cannot use this data-binding accessor to write properties. It does not guarantee that every getter is purely read-only: a Java getter can still contain code, lazy-load data, or access resources. Therefore, provide view/DTO objects with simple getters and avoid exposing domain objects with complex behavior.

## 3. Creating a context that can write properties

If the use case genuinely needs to update properties via SpEL, use `forReadWriteDataBinding()`:

```java
ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context = SimpleEvaluationContext
        .forReadWriteDataBinding()
        .build();

CustomerView customer = new CustomerView("Lan", true, 28);
Expression displayName = parser.parseExpression("displayName");
displayName.setValue(context, customer, "Linh");
```

The read-write builder allows the data-binding property accessor to perform write operations on properties that have an appropriate setter or write path. Properties that do not support writing still cannot be updated simply because the context is in read-write mode.

Only enable read-write when the expression needs to modify objects. If a rule only checks conditions, using read-only helps reduce the chance of an expression accidentally mutating data.

## 4. Enabling instance method invocation when truly needed

Method invocation is disabled by default in `SimpleEvaluationContext`. If an expression needs to call instance methods, you can enable it explicitly using `withInstanceMethods()` on the builder:

```java
EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .withInstanceMethods()
        .build();
```

For example, when needing to call a string method:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("displayName.toUpperCase()");

String label = expression.getValue(context, customer, String.class);
```

Only enable this feature if the rule genuinely needs method invocation. A method called on an object in an expression is still Java code; a method can read a database, mutate state, or perform expensive tasks. Therefore, only expose objects with appropriate public methods and clear contracts.

`withInstanceMethods()` does not turn `SimpleEvaluationContext` into `StandardEvaluationContext`: excluded features such as type references, constructor invocations, and bean references remain unsupported.

## 5. Using a custom property accessor

Besides the two built-in data binding modes, you can create a context from one or more `PropertyAccessor` instances chosen by the application:

```java
EvaluationContext context = SimpleEvaluationContext
        .forPropertyAccessors(myReadOnlyAccessor)
        .build();
```

This is useful when expressions should only see an allowlisted set of properties or when data has a custom structure unsuitable for JavaBean data binding.

The accessor determines:

- Which objects and property types can be accessed.
- Which properties can be read.
- Which properties can be written, if the accessor supports writing.
- How property names in expressions map to actual data.

If using a custom accessor, clearly restrict the supported target types and exposed property names. Do not implement an accessor that "reads every field or invokes every getter" if the goal is to limit the access surface.

## 6. Root object, variables, and expression evaluation

`SimpleEvaluationContext` is still an `EvaluationContext`, so it can use a root object and variables according to the context's API:

```java
ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

Expression expression = parser.parseExpression(
        "status == #expectedStatus and total <= #limit");

// The root object is passed for the evaluation.
// Variables expectedStatus and limit must be provided according to the context API being used.
```

In an application, create the context and register the required input values before evaluating. Use meaningful variable names and pass data as strongly typed objects. Avoid concatenating input into the expression source.

Example with a root object:

```java
OrderView order = orderService.loadView(orderId);
EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

Boolean withinLimit = parser.parseExpression("total <= #limit")
        .getValue(context, order, Boolean.class);
```

Here `total` is read from the root `order`, while `#limit` is a variable that needs to be provided in the context. If an application needs variables, use the variable registration mechanism supported by the context in the Spring version being used, or place that value into a strongly typed root view.

## 7. Unsupported SpEL features

`SimpleEvaluationContext` excludes features that can significantly expand an expression's access permissions:

| Feature | Example with full SpEL | In `SimpleEvaluationContext` |
| --- | --- | --- |
| Type reference | `T(java.lang.Math).max(1, 2)` | Not supported. |
| Constructor invocation | `new java.math.BigDecimal('10.5')` | Not supported. |
| Bean reference | `@pricingService.calculate(total)` | Not supported. |
| Method invocation | `name.toUpperCase()` | Disabled by default; instance methods can be opted in. |
| Property access | `customer.name` | Must choose appropriate data-binding or property accessor. |

This means an expression requiring `T(...)`, `new`, or `@bean` cannot run simply by enabling instance methods. If the use case genuinely needs those capabilities, re-evaluate the design and use an appropriate context with a strict access permission allowlist.

## 8. Read-only does not mean side-effect free

This is an important limitation when choosing `SimpleEvaluationContext`.

Read-only primarily controls the ability to write properties through the accessor. It cannot guarantee that invoked getters or methods are purely read-only. For example:

- A getter can trigger ORM lazy loading and execute database queries.
- A getter can read configuration files or call another service.
- An enabled instance method can update a counter, modify a cache, or send a message.
- A custom property accessor can perform any logic that its implementation allows.

Therefore, to keep expressions predictable, you should:

- Pass DTOs or view objects containing prepared data.
- Keep getters simple, free of side effects, and without resource access.
- Only enable method invocation when needed and restrict which methods can be called.
- Do not expose repositories, HTTP clients, filesystem services, or administrative objects in the root/context.
- Perform write operations or external system access in the service layer, at an explicitly controlled step.

`SimpleEvaluationContext` reduces the available feature surface; actual safety still depends on the objects, accessors, converters, and methods that the application exposes.

## 9. Choosing SimpleEvaluationContext vs StandardEvaluationContext

You can use the following questions to choose a context:

| Need | Suitable choice |
| --- | --- |
| Read-only property access to evaluate a rule | `forReadOnlyDataBinding()` |
| Update allowed properties via data binding | `forReadWriteDataBinding()` |
| Expose only specific properties | `forPropertyAccessors(...)` with an allowlist accessor |
| Need to call allowed instance methods | `SimpleEvaluationContext` builder combined with `withInstanceMethods()` |
| Need `T(...)`, `new`, or `@bean` | `StandardEvaluationContext` with resolvers/locators restricted as required |
| Internal expressions needing full SpEL features | `StandardEvaluationContext` |

Do not switch to the full context just to fix a syntax error if the missing feature is not actually necessary. Identify the exact permissions the expression needs and expose the corresponding minimum permissions.

## 10. Context configuration examples by purpose

**Read-only rule:**

```java
EvaluationContext readOnly = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

Boolean valid = parser.parseExpression(
        "active == true and balance >= 0")
        .getValue(readOnly, accountView, Boolean.class);
```

**Updating properties via data binding:**

```java
EvaluationContext readWrite = SimpleEvaluationContext
        .forReadWriteDataBinding()
        .build();

parser.parseExpression("displayName")
        .setValue(readWrite, profileView, "Lan Nguyen");
```

**Allowing necessary instance methods:**

```java
EvaluationContext withMethods = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .withInstanceMethods()
        .build();

String normalized = parser.parseExpression("code.trim()")
        .getValue(withMethods, requestView, String.class);
```

These examples illustrate three different options. In a real application, reuse the parser/expression appropriately and create the context with the right root object for each evaluation.

## 11. Common errors and troubleshooting

| Symptom | Cause to check | How to resolve |
| --- | --- | --- |
| `T(...)` does not work | `SimpleEvaluationContext` does not support type references. | Use Java APIs to compute the value beforehand, or switch to the full context with a restricted type locator if truly needed. |
| `new SomeType(...)` does not work | Constructor invocation is not part of this context's feature set. | Create the object in Java and pass it via an appropriate root/variable. |
| `@bean` is not resolved | Bean references are not supported. | Call the service in Java before/after evaluation or use the full context with a controlled BeanResolver. |
| Calling `name.toUpperCase()` fails | Method invocation is disabled by default. | Only when needed, enable `withInstanceMethods()` and restrict the exposed objects. |
| `setValue` cannot write property | Using a read-only builder or the property lacks a suitable write accessor/setter. | Use the read-write builder and check whether the property is writable. |
| Property cannot be read | Current property accessor does not support that object/property type. | Choose an appropriate data-binding builder or register a custom allowlisted accessor. |
| Read-only expression still triggers queries | Getter or accessor performs lazy loading/resource access. | Use pre-loaded DTOs and purely read-only getters. |
| Expression causes unintended actions | Instance method or custom accessor has side effects. | Disable method invocation if unnecessary; narrow methods/accessors and move actions to the service layer. |

## Key takeaways

- `SimpleEvaluationContext` provides a more restricted SpEL feature set for data binding and rule evaluation.
- Use `forReadOnlyDataBinding()` when only reading properties is required.
- Use `forReadWriteDataBinding()` when the expression needs to update allowed properties.
- Method invocation is disabled by default; `withInstanceMethods()` explicitly enables it when truly needed.
- `forPropertyAccessors(...)` allows the application to control property access using selected accessors.
- Type references `T(...)`, constructors `new`, and bean references `@bean` are not supported.
- Read-only prevents writing through a read-only accessor, but does not guarantee that getters have no side effects.
- Do not expose repositories, HTTP clients, filesystem services, or domain objects with broad behavior to external expressions.
- Use DTOs/view objects, simple getters, and property/method allowlists to reduce the access surface.
- Choose `StandardEvaluationContext` only when the use case requires fuller features and the application can restrict permissions appropriately.

## References

- [Spring Framework Reference — EvaluationContext and SimpleEvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework API — SimpleEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [Spring Framework API — DataBindingPropertyAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/DataBindingPropertyAccessor.html)
- [Spring Framework API — StandardEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)