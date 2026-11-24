# StandardEvaluationContext with full extensibility

## 1. Role of EvaluationContext in SpEL

Spring Expression Language (SpEL) separates parsing an expression from resolving references at runtime. `ExpressionParser` parses a string into an `Expression`; `Expression` executes the expression; and `EvaluationContext` provides the environment for the expression to locate objects, properties, methods, constructors, beans, types, and any needed conversions.

`StandardEvaluationContext` is the full-featured implementation of `EvaluationContext`. It allows:

- Selecting the root object against which unprefixed property and method names are resolved.
- Replacing or supplementing how SpEL reads/writes properties, invokes methods, creates objects, and accesses elements by index.
- Providing mechanisms for finding beans, finding types, converting values, comparing, and performing operations.
- Registering variables and functions for the expression to reference.
- Customizing strategies to match the application's data model or business rules.

Use `StandardEvaluationContext` when expressions are defined by the application or trusted administrators and require the full power of SpEL. If you only need data binding or data filtering with a limited feature set, see `SimpleEvaluationContext`.

## 2. Creating the context and setting the root object

The root object is the default object against which SpEL resolves unprefixed references. You can pass the root object through the constructor or set it later:

```java
Order order = new Order(new BigDecimal("100.00"));

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

// Equivalent:
context.setRootObject(order);

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("subtotal");

BigDecimal subtotal = expression.getValue(context, BigDecimal.class);
```

In the example above, `subtotal` is read from the root object. When accessing a registered variable, use the `#` prefix, such as `#taxRate`. You can change the root object with `setRootObject()`, or pass a separate root object when calling the corresponding overload of `Expression.getValue()`.

If you need to supply additional type metadata for the root object, `setRootObject(Object, TypeDescriptor)` allows passing a `TypeDescriptor` as well.

## 3. Extension points

`StandardEvaluationContext` comes with standard strategies out of the box. You can add custom strategies using `add...` methods, replace lists using `set...`, or inspect the current configuration via `get...` methods.

| Component | Role and typical default | Extension point |
|---|---|---|
| Root object | Default object for unprefixed property/method names. | Constructor, `setRootObject()`, `getRootObject()`. |
| Property accessor | Reads/writes properties and fields; defaults to `ReflectivePropertyAccessor`. | `addPropertyAccessor()`, `setPropertyAccessors()`, `removePropertyAccessor()`. |
| Method resolver | Finds a matching method to invoke; defaults to `ReflectiveMethodResolver`. | `addMethodResolver()`, `setMethodResolvers()`, `removeMethodResolver()`. |
| Constructor resolver | Finds a constructor to handle `new` expressions; defaults to `ReflectiveConstructorResolver`. | `addConstructorResolver()`, `setConstructorResolvers()`, `removeConstructorResolver()`. |
| Bean resolver | Resolves `@beanName` bean references; a standalone context has no preconfigured bean resolver. | `setBeanResolver()`. |
| Type locator | Finds classes for `T(...)` type reference expressions; defaults to `StandardTypeLocator`. | `setTypeLocator()`. |
| Type converter | Converts values, including during assignment and when requesting a result type; defaults to `StandardTypeConverter`. | `setTypeConverter()`. |
| Type comparator | Compares two values; defaults to `StandardTypeComparator`. | `setTypeComparator()`. |
| Operator overloader | Supplements how operations are executed for types outside the standard set; defaults to `StandardOperatorOverloader`. | `setOperatorOverloader()`. |
| Variables and functions | Stores values accessed via `#name`; registers functions invoked via `#function(...)`. | `setVariable()`, `setVariables()`, `lookupVariable()`, `registerFunction()`. |
| Index accessor | Customizes reading/writing structures accessed with `[index]`; the `IndexAccessor` API is available since Spring Framework 6.2. | `addIndexAccessor()`, `setIndexAccessors()`, `removeIndexAccessor()`. |

### 3.1. PropertyAccessor: customizing how properties are read and written

A property accessor determines whether a property can be read or written on a target object. The default accessor is reflection-based and supports standard Java property access patterns.

When you need to read `Map` keys like SpEL properties, you can add `MapAccessor` from the Spring Context module:

```java
Map<String, Object> values = new HashMap<>();
values.put("status", "PAID");

StandardEvaluationContext context =
        new StandardEvaluationContext(values);

context.addPropertyAccessor(new MapAccessor());

String status = parser.parseExpression("status")
        .getValue(context, String.class);
```

For custom data structures, implement `PropertyAccessor`. The main methods are `getSpecificTargetClasses()`, `canRead()`, `read()`, `canWrite()`, and `write()`. `canRead()`/`canWrite()` determine whether the accessor can handle the property on the target object; `read()`/`write()` perform the corresponding operation.

Prefer `addPropertyAccessor()` when you only need to append an accessor. `setPropertyAccessors()` replaces the entire existing list, so if you use it, keep any default accessors that the application still needs.

### 3.2. MethodResolver and ConstructorResolver

`MethodResolver` determines how SpEL finds methods by name and argument list. `ConstructorResolver` determines how constructors are found for object creation expressions, such as `new java.lang.String('hello')`.

You can implement custom resolvers and register them:

```java
context.addMethodResolver(new DomainMethodResolver());
context.addConstructorResolver(new DomainConstructorResolver());
```

Each resolver can decline to handle a call so the next resolver can try. If you replace the list with `setMethodResolvers()` or `setConstructorResolvers()`, the previous list is replaced.

With the reflective method resolver, `registerMethodFilter(Class, MethodFilter)` allows filtering which methods are considered for a target type. This is an additional way to control methods exposed through that type; it does not replace designing safe root objects and accessors.

### 3.3. BeanResolver: referencing Spring beans

Expressions using `@beanName` syntax require a `BeanResolver`. When creating a context outside Spring's preconfigured expression evaluation mechanisms, you can connect the context to a `BeanFactory`:

```java
context.setBeanResolver(new BeanFactoryResolver(beanFactory));

Expression expression =
        parser.parseExpression("@pricingService.currentRate");

BigDecimal rate = expression.getValue(context, BigDecimal.class);
```

`BeanFactoryResolver` is in the `org.springframework.context.expression` package. Only configure a resolver when expressions genuinely need bean access; beans can significantly expand the operations an expression can perform.

### 3.4. TypeLocator: resolving types in T(...)

The type locator finds classes specified in expressions such as `T(java.time.Instant)`. The default is `StandardTypeLocator`. In applications with custom class loaders, plugins, or modular runtime environments, configure an appropriate class loader:

```java
context.setTypeLocator(
        new StandardTypeLocator(applicationClassLoader));
```

If a class cannot be found even though it exists in the application, check which class loader the type locator is using before changing the expression.

### 3.5. TypeConverter: converting data types

SpEL uses `TypeConverter` to convert values during evaluation, such as when assigning a value to a specifically typed property or calling `getValue()` with a desired result type. `StandardTypeConverter` integrates with Spring's `ConversionService`, including default converters and application-registered converters.

You can pass a custom `ConversionService` into the context:

```java
context.setTypeConverter(
        new StandardTypeConverter(conversionService));
```

Spring's conversion mechanism understands generic metadata. For example, when assigning an element into `List<Boolean>`, SpEL can convert the string `"false"` into `Boolean.FALSE` rather than leaving it as a string.

### 3.6. TypeComparator and OperatorOverloader

`TypeComparator` controls how two values are compared. Use `setTypeComparator()` when domain types require custom comparison rules.

`OperatorOverloader` allows adding operations between data types that SpEL does not support out of the box. For example, an application can define how to add two monetary objects or perform operations on a domain numeric type. Implement the `OperatorOverloader` interface and register it with `setOperatorOverloader()`.

Only replace these two strategies when default comparison or operator semantics do not fit the application's data model.

### 3.7. Variables and functions

Variables are referenced using `#name` syntax. Functions are registered from a Java method and called using `#functionName(arguments)` syntax. A method used as a SpEL function must be `static`.

```java
context.setVariable("taxRate", new BigDecimal("0.08"));

Method withTax = PricingFunctions.class.getMethod(
        "withTax", BigDecimal.class, BigDecimal.class);

context.registerFunction("withTax", withTax);

Expression expression =
        parser.parseExpression("#withTax(subtotal, #taxRate)");
```

Functions can group shared calculation logic into a clearly named API. Only register functions that expressions need to invoke, because every registered function becomes part of the capabilities an expression can access.

### 3.8. IndexAccessor (Spring Framework 6.2 and later)

Starting in Spring Framework 6.2, `IndexAccessor` provides a dedicated extension point for indexed access operations. It fits structures that are not standard arrays, collections, or maps, such as JSON trees or domain data structures.

An implementation defines `canRead()`, `read()`, `canWrite()`, and `write()`, and is then added via:

```java
context.addIndexAccessor(new JsonIndexAccessor());
```

Do not use this API if the project runs Spring Framework earlier than 6.2. SpEL's indexing syntax stays the same; the accessor determines how the index maps to the target structure.

## 4. Complete example: root object, variable, and function

The following example calculates the total amount after tax. The root object provides `subtotal`, the variable provides the tax rate, and the function encapsulates the calculation:

```java
public class Order {
    private final BigDecimal subtotal;

    public Order(BigDecimal subtotal) {
        this.subtotal = subtotal;
    }

    public BigDecimal getSubtotal() {
        return subtotal;
    }
}

public final class PricingFunctions {
    private PricingFunctions() {
    }

    public static BigDecimal withTax(
            BigDecimal subtotal, BigDecimal taxRate) {
        return subtotal.multiply(BigDecimal.ONE.add(taxRate));
    }
}

// Configuration and evaluation:
ExpressionParser parser = new SpelExpressionParser();

Order order = new Order(new BigDecimal("100.00"));
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable("taxRate", new BigDecimal("0.08"));
context.registerFunction(
        "withTax",
        PricingFunctions.class.getMethod(
                "withTax", BigDecimal.class, BigDecimal.class));

Expression totalExpression =
        parser.parseExpression("#withTax(subtotal, #taxRate)");

BigDecimal total =
        totalExpression.getValue(context, BigDecimal.class);

// total = 108.0000
```

The expression combines three reference sources: `subtotal` comes from the root object, `#taxRate` comes from a variable, and `#withTax(...)` invokes the registered function. The function can be replaced with a method resolver or bean resolver if the logic needs to depend on an application service.

## 5. Distinguishing StandardEvaluationContext and SimpleEvaluationContext

| Criterion | StandardEvaluationContext | SimpleEvaluationContext |
|---|---|---|
| Goal | Full-featured SpEL evaluation. | Data binding and expressions requiring restricted features. |
| Root object | Can be configured directly. | Can be configured via builder. |
| Reflection | Standard strategies use reflection to access properties, methods, and constructors. | Explicitly selects property/method support levels and accessors. |
| Type reference, constructor, bean reference | Usable when the corresponding strategy is configured. | Does not support these features. |
| Customization level | Configures individual EvaluationContext strategies. | Builder focused on capabilities to enable. |

Choose `StandardEvaluationContext` when trusted expressions require full SpEL access or when multiple strategies need customization. Choose `SimpleEvaluationContext` when the problem is primarily reading/writing data and the needed capabilities can be clearly restricted. `SimpleEvaluationContext` only narrows the feature set; it is not an absolute security boundary on its own.

## 6. Security and Expression lifecycle

`StandardEvaluationContext` allows expressions to invoke methods, instantiate objects, read/write properties, and reference beans. Therefore, **do not use StandardEvaluationContext to evaluate expressions coming from untrusted users or external systems**. An expression can access whatever objects are exposed by the root object, accessors, resolvers, variables, or functions.

Even when using `SimpleEvaluationContext`, accessible objects must be controlled. A zero-argument method returning a value can be treated like a property getter; a method's naming convention does not guarantee it has no side effects. For example, `Queue.poll()` mutates the queue and `File.delete()` deletes a file. Create dedicated DTOs, prefer immutability, expose only truly needed data and operations, and audit nested objects that expressions can reach.

SpEL can cache resolved accessors, method executors, or constructor executors inside an `Expression`'s AST. This speeds up subsequent evaluations, but has security implications:

- You can parse an `Expression` once and evaluate it repeatedly with root objects or contexts that share an equivalent configuration.
- Avoid changing the accessor/resolver lists between evaluations without a clear reason.
- If the same expression string is executed under different permissions, parse it into separate `Expression` instances for each permission configuration.
- Do not evaluate an `Expression` first with a broad-privilege context and then reuse that same instance in a more restricted context. The AST may reuse strategies cached from the earlier run.

Distinguish context configuration from parser configuration. `StandardEvaluationContext` controls reference resolution during evaluation; `SpelParserConfiguration` controls parser behaviors such as auto-growing collections, expression limits, and compiler mode.

## 7. Common errors and how to handle them

| Symptom | Common cause | What to check |
|---|---|---|
| Property not found | Wrong root object, misspelled property name, or missing matching accessor. | Check the root object, getters/fields, and property accessor list. |
| Cannot call method | No matching method resolver or parameter signature mismatch. | Check the method name, argument types, and registered resolvers. |
| Cannot create object with `new` | No matching constructor or constructor resolver was replaced. | Check constructors and the constructor resolver list. |
| `@beanName` is not resolved | `BeanResolver` is not configured. | Register `BeanFactoryResolver` if bean access is needed from a standalone context. |
| `T(MyType)` cannot find class | Type locator uses a class loader that cannot see the class. | Configure `StandardTypeLocator` with the application's class loader. |
| Value assigned with wrong type | Current converter does not support the desired conversion. | Register a converter in `ConversionService` and configure `StandardTypeConverter`. |
| Default accessor stops working | Used `setPropertyAccessors()` and replaced the entire list. | Append with `addPropertyAccessor()` or include the default accessor back in the list. |
| Results differ across contexts | Expression cached a strategy from an earlier evaluation. | Use separate Expression instances when contexts have different configurations or permissions. |

When debugging, you can inspect `getRootObject()`, `getPropertyAccessors()`, `getMethodResolvers()`, `getConstructorResolvers()`, `getBeanResolver()`, `getTypeLocator()`, `getTypeConverter()`, `getTypeComparator()`, `getOperatorOverloader()`, and `lookupVariable()`. Syntax parsing errors usually occur in `parseExpression()`; reference resolution or execution errors usually occur in `getValue()` or `setValue()`.

## 8. Key takeaways

- `EvaluationContext` is the reference resolution environment; `StandardEvaluationContext` is the full-featured and deeply configurable implementation.
- The root object serves unprefixed references; variables/functions are referenced via `#name`.
- Properties, methods, constructors, beans, types, conversion, comparison, and operators each have corresponding strategies.
- Use `add...` to append; use `set...` when intentionally replacing an entire strategy list.
- `IndexAccessor` is available since Spring Framework 6.2.
- Only evaluate trusted expressions with `StandardEvaluationContext`; also restrict the objects expressions can reach.
- Reuse Expression instances with equivalent permission configurations; create separate Expression instances for different permission domains.

## References

- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
- [MapAccessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/expression/MapAccessor.html)
- [IndexAccessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/IndexAccessor.html)
