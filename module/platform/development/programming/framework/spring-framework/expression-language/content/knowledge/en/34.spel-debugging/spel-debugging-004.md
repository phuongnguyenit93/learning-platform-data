# Isolating long property paths with smaller expressions

## 1. Why break down a property path?

A SpEL expression can access multiple consecutive properties:

    customer.profile.address.city

If this expression behaves incorrectly, looking only at the final error message may not be enough to know which object or property caused the issue.

A path can fail for several different reasons:

- An intermediate object is null.
- The property does not exist or cannot be read.
- The getter throws an exception.
- PropertyAccessor does not support the current object type.
- The returned value has a different type than the next step expects.
- An index or Map key is invalid.
- A method in the path cannot be found or cannot execute.
- Lazy-loaded data is not ready or accessing it triggers unexpected extra operations.

An effective debugging technique is to split the path into small steps, evaluate each step, and observe the intermediate values and data types.

Instead of only running:

    customer.profile.address.city

check sequentially:

    customer
    customer.profile
    customer.profile.address
    customer.profile.address.city

The first step returns the Customer object, the next returns Profile, then Address, and finally city. The first point that fails or returns null usually isolates the cause.

## 2. Distinguishing parsing errors from evaluation errors

Before breaking down the path, determine which phase the expression fails in.

**Parsing** occurs when the parser analyzes the source:

    Expression expression =
        parser.parseExpression("customer.profile.address.city");

If the syntax is invalid, parseExpression may throw ParseException. In that case, there is no valid Expression yet to call getValue on.

**Evaluation** occurs when the expression accesses data:

    Object city = expression.getValue(context);

If the source is valid but customer or profile is null, or a property cannot be read, the error appears during evaluation and is typically reported by EvaluationException or one of its subtypes.

For example:

    customer.profile.address.city

can parse successfully yet fail at runtime because customer.profile returns null.

Do not change syntax when the real cause is runtime data. Check parse and evaluation as two separate steps.

## 3. Building a prefix list from the path

For a simple property path, write incremental prefixes in access order:

    customer
    customer.profile
    customer.profile.address
    customer.profile.address.city

Evaluate each prefix with the same root object and EvaluationContext:

    ExpressionParser parser =
        new SpelExpressionParser();

    String[] prefixes = {
        "customer",
        "customer.profile",
        "customer.profile.address",
        "customer.profile.address.city"
    };

    for (String source : prefixes) {
        try {
            Expression expression =
                parser.parseExpression(source);

            Object value =
                expression.getValue(context, rootObject);

            String typeName = value == null
                ? "<null>"
                : value.getClass().getName();

            log.debug(
                "SpEL prefix [{}] returned type [{}]",
                source,
                typeName
            );
        }
        catch (ParseException ex) {
            log.warn(
                "Cannot parse SpEL prefix [{}]: {}",
                source,
                ex.getSimpleMessage()
            );
            break;
        }
        catch (EvaluationException ex) {
            log.warn(
                "Cannot evaluate SpEL prefix [{}]: {}",
                source,
                ex.getSimpleMessage()
            );
            break;
        }
    }

When a prefix fails, stop there and inspect the object accessed at the corresponding step.

In the example, each prefix is evaluated from the same root object. Thus, getters at earlier steps may be invoked multiple times. This approach suits diagnostics when property access is read-stable, inexpensive, and has no side effects.

If a getter can mutate state, trigger I/O, or trigger lazy loading, prefer the incremental evaluation approach in the next section to avoid repeated calls.

## 4. Incremental evaluation on intermediate objects

For a path consisting only of simple properties, you can evaluate each property on the result of the previous step.

For example:

    Object current = rootObject;

    String[] properties = {
        "customer",
        "profile",
        "address",
        "city"
    };

    for (String property : properties) {
        if (current == null) {
            log.warn(
                "Stop before property [{}]: previous value is null",
                property
            );
            break;
        }

        try {
            Expression step =
                parser.parseExpression(property);

            current = step.getValue(context, current);

            String typeName = current == null
                ? "<null>"
                : current.getClass().getName();

            log.debug(
                "Property [{}] returned type [{}]",
                property,
                typeName
            );
        }
        catch (ParseException | EvaluationException ex) {
            log.warn(
                "Property step [{}] failed: {}",
                property,
                ex.getMessage()
            );
            break;
        }
    }

This keeps the same EvaluationContext while passing the intermediate object as the root object for the next step.

The advantage is that each property in the chain is read once. When a step returns null, the loop stops before attempting to access the next property.

This method works for simple property paths. If the path includes indexers, method invocations, selection, projection, or operators, split it into valid SpEL fragments instead of treating every segment as a single property name.

## 5. When the path starts with a variable

If the expression uses a variable, the first step needs to retrieve the variable from the context.

Example original expression:

    #order.customer.profile.address.city

You can check by prefix:

    #order
    #order.customer
    #order.customer.profile
    #order.customer.profile.address
    #order.customer.profile.address.city

Or retrieve the object from the variable and evaluate incrementally:

    Object current =
        parser.parseExpression("#order")
            .getValue(context);

    String[] properties = {
        "customer",
        "profile",
        "address",
        "city"
    };

    for (String property : properties) {
        if (current == null) {
            break;
        }

        current = parser
            .parseExpression(property)
            .getValue(context, current);

        log.debug(
            "Step [{}] type [{}]",
            property,
            current == null
                ? "<null>"
                : current.getClass().getName()
        );
    }

What matters is that the #order variable must be registered in the exact EvaluationContext used for the original expression.

If you swap the context for a new context lacking the needed variables, custom accessors, or converters, the debug result may differ from the original error.

## 6. Keep EvaluationContext and root object intact

When splitting an expression into smaller parts, keep the runtime factors identical to the original evaluation:

- Same root object or exact intermediate object.
- Same variables and functions.
- Same PropertyAccessor and MethodResolver.
- Same TypeConverter and TypeLocator if the expression needs them.
- Same BeanResolver if the expression references beans.
- Same parser configuration related to null-safe navigation or auto-grow.

For example, the original expression runs on a StandardEvaluationContext with a custom PropertyAccessor. If you debug with a new context having only default accessors, a property might be readable in the original run yet fail during the debug step.

Do not change the root object, context, and expression simultaneously and conclude you found the cause. Changing one factor at a time makes comparisons meaningful.

## 7. Checking null at each layer

With the path:

    customer.profile.address.city

determine which value is null:

    customer
    customer.profile
    customer.profile.address

If customer is null, the error happens immediately when accessing profile.

If customer exists but profile is null, the address step is where it fails.

If address is null, the city step is where it fails.

You can use null-safe navigation:

    customer?.profile?.address?.city

This style allows the expression to return null when a guarded receiver is null.

However, a final null result does not tell you which layer was null. When diagnosing, inspect each prefix or each intermediate object.

The null-safe operator protects the operation immediately following it. If a subsequent step still uses normal navigation on a null receiver, the expression can still fail.

## 8. Checking the data type after each step

A prefix can evaluate successfully yet return a different type than the expression author assumed.

For example:

    customer.profile
    customer.profile.address

Maybe profile returns a Map instead of class Profile, or address returns a proxy instead of the expected Address class.

Check the runtime type:

    Object value =
        parser.parseExpression("customer.profile")
            .getValue(context, rootObject);

    if (value != null) {
        log.debug(
            "Runtime type: {}",
            value.getClass().getName()
        );
    }

Runtime types help detect:

- A property returning a different implementation than expected.
- A collection containing different element types.
- A Map being used instead of a JavaBean.
- A proxy or wrapper being returned.
- A getter returning null or a substitute object.

When calling getValue without specifying a desired result type, you can observe the actual object before asking TypeConverter to convert it to the target type. This avoids confusing a property access error with a type conversion error.

Do not log the entire object or call toString() on an object of unknown origin. Only log type names and non-sensitive metadata.

## 9. JavaBean properties and Map keys

A long path can traverse both JavaBeans and Maps. The access syntax must match the actual structure.

JavaBean property:

    customer.address.city

Map key:

    #payload['customer']
    #payload['customer']['address']
    #payload['customer']['address']['city']

If a key contains a dot:

    #payload['user.profile']

then the dot is inside the key string, not a property path separator.

When suspecting a step is wrong, check whether the target is a Map and whether the key exists. Do not assume every dot denotes a JavaBean property.

With Maps, an indexer clearly expresses key-based access. With Lists or arrays, an indexer accesses by position.

## 10. Isolating indexers in a path

Example:

    order.items[2].product.category.name

Can be split into prefixes:

    order
    order.items
    order.items[2]
    order.items[2].product
    order.items[2].product.category
    order.items[2].product.category.name

Inspect the collection separately before accessing the index:

    #items.size()
    #items.isEmpty()

If the index is 2, the List must have at least three elements. A null-safe indexer only protects against a null receiver; it does not turn an out-of-bounds index into null.

If the path uses a Map key, verify the key exists and has the right type:

    #payload.containsKey('customer')
    #payload['customer']

When an indexer fails, determine whether the receiver is null, the collection is empty, the index is out of range, or the key does not exist. These are distinct causes requiring different handling.

## 11. Isolating method invocations

A property path can contain method calls:

    order.customer.getProfile().getAddress().getCity()

If an error appears at a method, split by each call:

    order.customer
    order.customer.getProfile()
    order.customer.getProfile().getAddress()
    order.customer.getProfile().getAddress().getCity()

Check:

- Does the method exist on the runtime type?
- Do the number and types of parameters match?
- Does the method return null?
- Does the method throw an exception?
- Does the method have side effects or perform I/O?
- Which MethodResolver is handling the call?

If the method throws an exception, inspect the cause of EvaluationException instead of looking only at the position of the method call node.

Avoid re-invoking methods with side effects during debugging. For expensive or impure methods, store the result once in Java and inspect the returned object.

## 12. Do not split expressions by splitting on dots

Do not use:

    String[] parts = source.split("\\.");

Dots are not always property separators.

For example:

    #settings['user.profile']
    T(java.lang.Math).max(1, 5)
    #customer.calculateTax(10.5)
    #message == 'profile.city'

In these expressions, dots can appear inside Map keys, package/class names, method paths, or string literals. Decimal numbers and nested structures also make manual string splitting error-prone.

SpEL is a language with a grammar. The safe approach is to identify meaningful steps according to the expression structure, or use the parser on each valid fragment.

Do not rely on counting dots to infer the AST or property path.

## 13. Templates, selections, and projections must be split structurally

An expression may contain selection or projection:

    orders.?[customer.profile.active == true].![customer.name]

Do not split this string into segments by dots. Identify separately:

- Source collection orders.
- Predicate inside the selection.
- Property path evaluated on each element.
- Projection expression applied to the selected elements.

You can debug the source collection first:

    orders

Then test the predicate on a representative element:

    customer.profile.active == true

Finally test the projection on an element:

    customer.name

If the expression is inside a template block, preserve information about delimiters and parsed fragments. An error inside an inner expression may report a position relative to the fragment rather than the whole template.

## 14. Using exception position to choose which prefix to check

If evaluation throws SpelEvaluationException, you can retrieve the message code, position, and expression source:

    try {
        expression.getValue(context);
    }
    catch (SpelEvaluationException ex) {
        log.warn(
            "Code={}, position={}, source={}",
            ex.getMessageCode(),
            ex.getPosition(),
            ex.getExpressionString()
        );
    }

Position is an offset in the expression source, not directly a property name or line number. It can help locate the region to inspect, though it does not always highlight the entire failing token.

Use position as a clue to choose which prefix to inspect, then confirm by evaluating small steps.

If source or position is unavailable, use the original expression retained by the application and check step by step according to the known structure.

## 15. Avoiding repeated evaluation of getters with side effects

When testing prefixes from the start each time, getters in earlier parts may be called multiple times.

For example:

    customer
    customer.profile
    customer.profile.address
    customer.profile.address.city

The final evaluation may invoke getCustomer(), getProfile(), and getAddress() again after earlier prefixes already called them.

This can cause problems if a getter:

- Triggers lazy loading.
- Calls a database or external service.
- Reads data from a file or network.
- Mutates cache or state.
- Throws an exception based on runtime conditions.

For simple property paths, incremental evaluation on intermediate objects avoids repeating earlier getters.

For methods with side effects, do not call them repeatedly just to debug. Use fixtures, mocks, spies, or capture the result once at an appropriate Java layer.

## 16. Checking lazy loading and proxies

In applications using ORM, property access can pass through proxies or lazy relationships.

For example:

    order.customer.profile.address.city

Reading customer or profile may trigger a database query. If the persistence context is already closed, evaluation can fail even though the path and property names are correct.

When debugging, check:

- Is the runtime class a proxy?
- Which relationships are lazy?
- Is there an active session/entity manager at evaluation time?
- Are additional queries issued for each property?
- Does the path cause N+1 queries when evaluated over a collection?

If the expression only needs a few facts, fetch them in a service or repository and pass an appropriate DTO into EvaluationContext. Do not use a long path to inadvertently load an entire object graph.

## 17. Creating a controlled diagnostic helper

A small helper can record prefixes, result types, and errors without logging sensitive data:

    static void tracePrefix(
            ExpressionParser parser,
            EvaluationContext context,
            Object rootObject,
            String source) {

        try {
            Expression expression =
                parser.parseExpression(source);

            Object value =
                expression.getValue(context, rootObject);

            String type = value == null
                ? "<null>"
                : value.getClass().getName();

            log.debug(
                "Expression prefix [{}] -> [{}]",
                source,
                type
            );
        }
        catch (ParseException ex) {
            log.warn(
                "Parse failed at prefix [{}]: {}",
                source,
                ex.getSimpleMessage()
            );
        }
        catch (EvaluationException ex) {
            log.warn(
                "Evaluation failed at prefix [{}]: {}",
                source,
                ex.getSimpleMessage()
            );
        }
    }

You can invoke the helper for manually identified prefixes.

Do not put the entire root object, variable map, or result object into logs. Expression sources can also contain sensitive literals if generated from configuration; redact before logging.

In production, only enable detailed tracing when needed and restrict log access.

## 18. Writing tests for each step of a property path

After finding the failing step, create a small test with the corresponding object graph.

For example:

    @Test
    void readsNestedCity() {
        Address address = new Address("Da Nang");
        Profile profile = new Profile(address);
        Customer customer = new Customer(profile);

        StandardEvaluationContext context =
            new StandardEvaluationContext(customer);

        Expression expression =
            new SpelExpressionParser()
                .parseExpression("profile.address.city");

        assertThat(
            expression.getValue(context, String.class)
        ).isEqualTo("Da Nang");
    }

You should also add tests for cases such as:

- Null root object.
- Null intermediate property.
- Non-existent or unreadable getter.
- Unexpected return type.
- Missing Map key.
- Empty List or out-of-bounds index.
- Custom PropertyAccessor.
- Getter throwing an exception.
- Lazy proxy or unloaded data if the application uses ORM.

Tests should use small, clear objects and deterministic data. This makes it easy to reproduce errors without starting the entire application when unnecessary.

## 19. If paths are dynamically generated from configuration or users

If the application receives property names from users or an external system, do not concatenate that name directly into the expression source.

Example to avoid:

    String source = "customer." + suppliedProperty;

    Expression expression =
        parser.parseExpression(source);

Instead, use an allow-list:

    Map<String, Expression> allowedPaths = Map.of(
        "name", parser.parseExpression("customer.name"),
        "city", parser.parseExpression("customer.address.city")
    );

    Expression expression =
        allowedPaths.get(suppliedProperty);

Only paths defined by the application are evaluated.

If many dynamic fields are needed, use a schema or strongly typed rule structure rather than allowing arbitrary strings. Property paths can reach deep into the object graph, so object scope and accessors must be controlled.

## 20. Key points to remember

- Split long property paths into incremental prefixes to find the first failing step.
- Distinguish ParseException at parseExpression from EvaluationException at getValue.
- Keep the same EvaluationContext, root object, and resolvers/accessors when comparing.
- Incremental evaluation on intermediate objects suits simple property paths and avoids re-calling earlier getters.
- Check null and runtime type after each step.
- Use indexers properly for Lists, arrays, and Maps; check indexes/keys separately.
- Method invocations must be checked as a separate step, including cause and side effects.
- Do not split on dots to parse expressions; dots can appear in keys, class names, methods, or strings.
- Selection, projection, and templates must be split according to expression structure.
- Position in an exception is an offset and only a clue, not a complete source range.
- Be careful with getters that trigger lazy loading, I/O, or state mutation.
- Do not log entire objects or sensitive data when tracing.
- If paths are externally supplied, use an allow-list or schema-backed rule model.
- Write small tests for each layer of the object graph and null/type/index cases.

When a long property path fails, narrow the scope step by step: confirm the root, check each intermediate object, identify runtime types, and only then examine the relevant accessor or method. This approach helps distinguish data errors, object structure errors, and SpEL configuration errors without guessing from the final message.

## References

- Spring Framework Reference — Properties, Arrays, Lists, Maps, and Indexers: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/properties-arrays.html
- Spring Framework Reference — Safe Navigation Operator: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html
- Spring Framework Reference — Evaluation and Exceptions: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework Javadoc — Expression: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/Expression.html
- Spring Framework Javadoc — PropertyAccessor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/PropertyAccessor.html
