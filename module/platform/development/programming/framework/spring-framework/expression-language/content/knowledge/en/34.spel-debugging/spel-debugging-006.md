# Analyzing errors caused by resolvers or converters in SpEL

When Spring Expression Language (SpEL) evaluates an expression, multiple components of EvaluationContext collaborate to look up properties, methods, constructors, beans, and convert data types. If one component cannot handle the request, the expression can parse successfully yet fail at runtime.

To diagnose accurately, you need to determine **which step is failing** and **which component is responsible**. A property-not-found error usually relates to PropertyAccessor; a method invocation error may relate to MethodResolver or argument types; a type conversion error relates to TypeConverter. Looking only at the expression line or the outermost error message is often not enough to pinpoint the cause.

## 1. Distinguishing parse errors and evaluation errors

SpEL has two main phases:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression("#order.total");

    Object value = expression.getValue(context);

`parseExpression(...)` parses the syntax and creates an Expression. Syntax errors usually appear as `SpelParseException`. Only when calling `getValue(...)` does SpEL resolve properties, variables, beans, methods, and converters in EvaluationContext. Errors at this point are typically represented by `SpelEvaluationException` or a related evaluation exception, which may preserve the underlying root cause.

For example:

    Expression expression =
            parser.parseExpression("#order.customer.address.city");

The expression can parse successfully even if variable `order` is not registered, or `customer` is null. These issues only appear when evaluating against an actual context.

When debugging, explicitly record whether the error occurred during parse or evaluation. Do not change resolvers or converters if the expression has not even passed the parse step.

## 2. Identifying the responsible component

EvaluationContext provides different mechanisms for each kind of access:

| Component | Job | Common error symptoms |
|---|---|---|
| PropertyAccessor | Read or write properties | Property not found, property not readable/writable |
| MethodResolver | Find a matching method | Method not found or overload cannot be resolved |
| ConstructorResolver | Find a constructor | No matching constructor found |
| BeanResolver | Resolve `@beanName` | Bean not found or resolver rejects the name |
| TypeLocator | Resolve class in `T(...)` or `new` | Class not found |
| TypeConverter | Convert a value to target type | No converter or value cannot be converted |

Not every error is caused by a resolver. A property may exist while the target is null; a method may exist while arguments are incompatible; a converter may support the type pair yet the specific data value is malformed.

Start from the operation the expression is performing, then inspect the right component of the context.

## 3. Analyzing PropertyAccessor errors

PropertyAccessor is responsible for reading and writing properties on a target object. When SpEL accesses:

    #order.customer.name

it sequentially reads `customer` on order and then reads `name` on customer. Each step may need an accessor matching the target type at that step.

Common causes:

- The target object is not of a type supported by the accessor.
- Wrong property name or getter does not follow the JavaBean convention recognized by the accessor.
- An intermediate property returns null.
- The accessor does not support reading or writing the property.
- Multiple accessors support a target and search order causes another accessor to be used first.
- A custom accessor throws AccessException in `read` or `write`.

You can inspect accessors directly:

    EvaluationContext context =
            new StandardEvaluationContext(order);

    for (PropertyAccessor accessor :
            context.getPropertyAccessors()) {
        boolean supported =
                accessor.canRead(context, order, "customer");

        System.out.println(
                accessor.getClass().getName() + ": " + supported
        );
    }

The code snippet illustrates checking readability on a specific target and property. If you need to debug a nested path, repeat the check with the actual intermediate object and the property name at the next level.

For assignment, check `canWrite(...)` and confirm that the setter or accessor write mechanism actually works. `canWrite` returning true only indicates technical capability; application policy must still decide whether updates are permitted.

## 4. Analyzing MethodResolver errors

MethodResolver finds a method matching the target object, method name, and argument types. For example:

    #pricingService.calculate(#amount, #customer.level)

If the expression reports method not found, check:

1. Has the target bean or variable been resolved?
2. Is the target null?
3. Does the method name match exact casing?
4. Does the argument count match?
5. What is the runtime type of each argument?
6. Is there an overload accepting those types?
7. Does TypeConverter support any required conversions?
8. Is the method accessible under the current resolver?

A method may exist in Java yet still not be selected if its signature is incompatible with runtime arguments. With overloads, a string might match a method accepting String but not a method accepting Integer if no appropriate converter exists.

StandardEvaluationContext uses reflective method resolution by default. If the application replaces the default resolver with a custom MethodResolver, inspect the actual resolver list and the return logic of each resolver. A custom resolver can return an executor when finding a method, return null to let the next resolver try, or throw AccessException upon encountering an access error per the API contract.

## 5. Analyzing ConstructorResolver and TypeLocator errors

For object creation expressions:

    new com.example.Customer('Lan', 25)

SpEL needs to locate the class first, and then choose a constructor.

- **TypeLocator** finds the class by name.
- **ConstructorResolver** finds a constructor matching argument count and types.
- **TypeConverter** may assist in converting arguments to types required by the constructor.

If the error says type not found, check package name, classpath, classloader, and TypeLocator. If the type was found but no matching constructor exists, check constructor visibility, argument count, overloads, and convertibility.

StandardTypeLocator recognizes the `java.lang` package by default. For other classes, use the fully qualified name or register an appropriate import prefix:

    StandardTypeLocator locator =
            new StandardTypeLocator();

    locator.registerImport("com.example.domain");

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setTypeLocator(locator);

If the application uses a custom TypeLocator or ConstructorResolver, inspect the configuration of the exact EvaluationContext doing the evaluation. Do not confuse an unresolvable class error with an uncallable constructor error.

## 6. Analyzing BeanResolver errors

The `@beanName` syntax requires a BeanResolver:

    @pricingService.defaultCurrency

A manually created StandardEvaluationContext does not automatically know about ApplicationContext. If the expression reports a bean cannot be resolved, check:

- Was `setBeanResolver(...)` called on the context?
- Does the bean name match a bean name or alias in BeanFactory?
- Does the resolver have a bean name allowlist?
- Does the bean belong to an active scope?
- Did bean initialization fail due to a dependency or configuration?
- Is the expression running in the right ApplicationContext or a different test context?

Common configuration example:

    context.setBeanResolver(
            new BeanFactoryResolver(beanFactory)
    );

If using a custom BeanResolver, inspect the input bean name and lookup result. A resolver may intentionally reject beans outside an allowlist; that is policy behavior, not necessarily a configuration bug.

Do not fix the error by exposing the entire ApplicationContext or BeanFactory to every expression. Only provide the beans or facades that the use case needs.

## 7. Analyzing TypeConverter errors

TypeConverter is used when SpEL needs to convert a value to a target type, such as when assigning a property, passing arguments to a method/constructor, or retrieving a result with a requested type.

Two main operations:

    TypeConverter converter = context.getTypeConverter();

    boolean canConvert = converter.canConvert(
            TypeDescriptor.valueOf(String.class),
            TypeDescriptor.valueOf(Integer.class)
    );

    Object converted = converter.convertValue(
            "42",
            TypeDescriptor.valueOf(String.class),
            TypeDescriptor.valueOf(Integer.class)
    );

`canConvert` indicates whether the converter supports the described type pair. It does not guarantee every specific value is valid. For example, the string `"42"` can convert to Integer, while `"forty-two"` can fail even for the same String-to-Integer pair.

When conversion fails, check:

- The actual source type, not just the type you think the variable holds.
- The target type of the property, method parameter, or constructor parameter.
- Converters registered in ConversionService.
- The specific value, format, numeric range, and null.
- TypeDescriptor metadata if conversion depends on collection generics or annotations.

Exceptions can appear at multiple layers, such as Spring conversion errors or exceptions wrapped by SpEL inside an evaluation error. Inspect the cause chain to find the failing converter or source value.

## 8. Distinguishing method selection errors from argument conversion errors

These two error types are easily confused. Method resolution decides which method can receive the call; conversion helps convert arguments to the corresponding parameter types.

Java example:

    public String format(Integer value) {
        return "number=" + value;
    }

    public String format(String value) {
        return "text=" + value;
    }

Expression:

    #formatter.format(#input)

If `input` is String, the overload taking String can be chosen directly. If only the method taking Integer exists, SpEL needs an appropriate converter to convert String to Integer. If the value cannot be converted, the error can occur while preparing the method call.

To isolate the cause:

1. Print the runtime type of each argument.
2. Check the method signatures available on the target.
3. Check the converter for the source/target type pair.
4. Try converting the value separately using TypeConverter.
5. Try invoking the method with type-normalized arguments in Java.

If the method works when passing an Integer directly but fails with a String, the issue may lie in conversion or overload resolution, not in the method not existing.

## 9. Registration and ordering of custom resolvers

StandardEvaluationContext allows adding or replacing resolvers and accessors. When there are multiple implementations, order in the list can affect which component is tried first.

Example adding a PropertyAccessor:

    context.addPropertyAccessor(
            new CustomerPropertyAccessor()
    );

Example replacing the MethodResolver list must be done intentionally:

    context.setMethodResolvers(
            List.of(customMethodResolver)
    );

When using `setMethodResolvers`, the supplied list becomes the context's resolver list. If you need to keep the reflective fallback, include that resolver in the list in the order the application expects. Similarly, when replacing property accessors, do not accidentally drop the default accessor that other expressions rely on.

To debug, record the class of each accessor/resolver and the order they are registered in the context. Check both custom implementations and default resolvers. Do not add multiple permissive resolvers just to silence errors; that can mask the root cause and open unintended access scope.

## 10. Creating a small test to reproduce the error

When an error occurs in a large flow, narrow it down to a test containing only the expression, target, context, and necessary dependencies.

Example testing conversion independently:

    @Test
    void convertsStringToInteger() {
        StandardEvaluationContext context =
                new StandardEvaluationContext();

        Integer value = new SpelExpressionParser()
                .parseExpression("'42'")
                .getValue(context, Integer.class);

        assertEquals(42, value);
    }

Example testing a property:

    @Test
    void readsNestedProperty() {
        StandardEvaluationContext context =
                new StandardEvaluationContext(order);

        String city = new SpelExpressionParser()
                .parseExpression("customer.address.city")
                .getValue(context, String.class);

        assertEquals("Da Nang", city);
    }

After the small test reproduces the error, re-add components one by one: custom accessor, method resolver, bean resolver, or converter. This identifies which component changes the behavior.

If the error only appears in an annotation, test through the exact framework infrastructure and Spring-managed beans. A manually created context in a unit test may not match the context provided by an annotation handler.

## 11. Logging enough for diagnostics without exposing data

Useful information when logging errors includes:

- Controlled expression or expression identifier.
- Phase: parse or evaluate.
- Annotation type or use case being processed.
- Target object type and related property/method name.
- Source and target types when conversion fails.
- Types of resolver/accessor/converter in use.
- Original exception and cause chain.

Avoid logging entire objects, secret values, tokens, personal information, or expressions containing sensitive data. If expressions are user-configured, consider logging the expression ID and config version instead of the full string.

Do not catch an exception and silently return null or a default value. Doing so can turn a configuration or conversion error into a wrong business result. Classify the error, preserve the root cause, and handle according to a fail-closed policy appropriate to the use case.

## 12. Quick diagnostic checklist

When an expression fails, proceed in order:

1. Did parsing succeed? If not, check syntax and error position.
2. Which EvaluationContext is being used? Verify root, variables, and resolvers.
3. Is the target at the failing step null or the wrong type?
4. Does PropertyAccessor support reading/writing the target and property?
5. Can MethodResolver find the method by name, argument count, and argument types?
6. Can BeanResolver resolve the bean name?
7. Can TypeLocator find the class?
8. Can ConstructorResolver find a matching constructor?
9. Does TypeConverter support the type pair and the specific value?
10. Is a custom resolver/accessor/converter throwing an exception or shadowing another implementation's error?

Once the cause is identified, fix the configuration or data at the exact component. Avoid adding broad fallbacks, exposing extra beans, or enabling write access just so the expression stops throwing errors.

## 13. Takeaways

Resolvers and converters handle different parts of SpEL evaluation. PropertyAccessor reads/writes properties; MethodResolver and ConstructorResolver find matching executables; BeanResolver finds beans; TypeLocator finds classes; TypeConverter converts values. Distinguish parse errors from evaluation errors, check targets and runtime types, inspect the cause chain, and verify the actual resolver list on EvaluationContext. `canConvert` only checks capability per type pair, not whether a specific value is valid. Keep errors clear, write a small reproduction test, and fix only the failing component; do not widen permissions or swallow exceptions to hide the issue.
