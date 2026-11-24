# Controlling the List of Exposed Functions

## 1. What is a Function in SpEL?

Spring Expression Language (SpEL) allows applications to extend the language with developer-defined functions. A function is a named operation registered in an EvaluationContext that can be called from an expression.

Call syntax:

    #functionName(argument1, argument2, ...)

Example:

    #normalizeCode('  vn-hcm  ')

The expression above calls the function named normalizeCode and passes in a string.

A function does not appear automatically simply because a Java class has a public static method. The application must actively register the corresponding method or MethodHandle in the EvaluationContext before the expression is evaluated.

This creates an allow-list mechanism: the context only needs to register the functions that a given type of expression is permitted to use.

## 2. Distinguishing Functions from Method Invocation

Both functions and method invocations can invoke Java logic, but how the target is resolved differs.

| Syntax | How it works |
| --- | --- |
| #normalizeCode('vn') | Looks up the function named normalizeCode registered in EvaluationContext |
| #text.trim() | Retrieves the text variable and calls the trim() method on that object |
| text.trim() | Calls a method on the text property of the root object |
| @pricingService.calculate(#amount) | Looks up the pricingService bean via BeanResolver and calls the method |

Functions are called by name after the # symbol. Method invocation requires an object as a target, which can be the root object, a variable, or a bean reference.

Registering one function does not mean all other methods in the class containing that function are automatically registered. Only the method or MethodHandle bound to the function name can be called using function syntax.

However, if the context also exposes an object with many methods, the expression can access those methods via the separate method invocation path. Therefore, controlling the function registry is one part of limiting expression capabilities, not the entire security boundary.

## 3. Registering Functions with Method

The common approach is to obtain a java.lang.reflect.Method and register that method in the EvaluationContext.

Utility class example:

    public final class RuleFunctions {

        private RuleFunctions() {
        }

        public static String normalizeCode(String value) {
            if (value == null) {
                return null;
            }
            return value.trim().toUpperCase(Locale.ROOT);
        }

        public static boolean isWithinRange(
                BigDecimal value,
                BigDecimal minimum,
                BigDecimal maximum) {
            return value != null
                && value.compareTo(minimum) >= 0
                && value.compareTo(maximum) <= 0;
        }
    }

Obtaining the Method and registering it in the context:

    Method normalizeMethod =
        RuleFunctions.class.getMethod(
            "normalizeCode",
            String.class
        );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.registerFunction(
        "normalizeCode",
        normalizeMethod
    );

Calling the function in an expression:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
        parser.parseExpression(
            "#normalizeCode('  vn-hcm  ')"
        );

    String result =
        expression.getValue(context, String.class);

Result:

    VN-HCM

The method in the example is static. This is the standard implementation for functions because functions are called by name without needing an instance target in the expression.

## 4. Registering Functions via setVariable

According to the SpEL API, functions can also be registered as a variable holding a Method or MethodHandle using EvaluationContext's setVariable method.

Example:

    Method normalizeMethod =
        RuleFunctions.class.getMethod(
            "normalizeCode",
            String.class
        );

    EvaluationContext context =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

    context.setVariable(
        "normalizeCode",
        normalizeMethod
    );

Then invoke using function syntax:

    String result = parser
        .parseExpression("#normalizeCode('  spring  ')")
        .getValue(context, String.class);

    // result = "SPRING"

This approach is useful when you need to register a function in an EvaluationContext implementation that supports variable lookup, including SimpleEvaluationContext.

Do not confuse the two approaches:

- StandardEvaluationContext.registerFunction(name, method) is a convenience API specific to StandardEvaluationContext.
- EvaluationContext.setVariable(name, method) registers a Method as a function through the shared variable/function namespace.

Both allow expressions to invoke the function using #functionName(...).

## 5. Registering Multiple Functions via an Allow-List

If rules only need a predefined set of operations, register each function explicitly.

Example:

    Method normalizeMethod =
        RuleFunctions.class.getMethod(
            "normalizeCode",
            String.class
        );

    Method rangeMethod =
        RuleFunctions.class.getMethod(
            "isWithinRange",
            BigDecimal.class,
            BigDecimal.class,
            BigDecimal.class
        );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.registerFunction(
        "normalizeCode",
        normalizeMethod
    );

    context.registerFunction(
        "isWithinRange",
        rangeMethod
    );

The expression can only call functions under the registered names:

    #normalizeCode(#region) == 'VN'
        and #isWithinRange(#amount, #minimum, #maximum)

This is an easy-to-review allow-list. Rule maintainers can inspect the list and know exactly which operations an expression is granted.

Do not register every method of a utility class or automatically expose all public static methods via reflection. A small change in the utility class could unintentionally expand the API that expressions are allowed to call.

Treat the function list as part of the contract between the application and the rules.

## 6. Function Names and Variables Share a Namespace

In EvaluationContext, functions and variables share one namespace. Therefore, a function name should not collide with a variable name.

Example to avoid:

    context.setVariable("normalize", "VN");

    context.registerFunction(
        "normalize",
        normalizeMethod
    );

The same name normalize is being used for two purposes. Overwriting or lookup can prevent the expression from invoking the function as expected.

Use clear names and a convention:

    normalizeCode
    isWithinRange
    calculateDiscount
    hasPermission

And avoid using the same name for variables:

    context.setVariable("regionCode", "VN");
    context.registerFunction("normalizeCode", normalizeMethod);

A simple rule is to use verbs or verb phrases for functions, and nouns for variables. This makes expressions easier to read and reduces name collisions.

## 7. Functions Support Varargs

SpEL supports varargs for functions, similar to regular method invocation.

Utility method example:

    public static String joinLabels(String... labels) {
        return String.join(", ", labels);
    }

Obtaining the Method:

    Method joinMethod =
        RuleFunctions.class.getMethod(
            "joinLabels",
            String[].class
        );

Registering:

    context.registerFunction(
        "joinLabels",
        joinMethod
    );

Calling in an expression:

    #joinLabels('Java', 'Spring', 'SpEL')

Result:

    Java, Spring, SpEL

Varargs is useful when the number of arguments varies. However, clearly define the accepted argument count and types to avoid hard-to-control expressions or oversized inputs.

If a function only needs two or three fixed parameters, an explicit method signature is usually easier to understand than varargs.

## 8. Registering Functions with MethodHandle

Since Spring Framework 6.1, StandardEvaluationContext provides a registerFunction overload accepting java.lang.invoke.MethodHandle.

Conceptual example:

    MethodHandle handle = ...;

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.registerFunction(
        "formatMessage",
        handle
    );

MethodHandle can be suitable when the application already has a handle to a target and pre-bound parameters. Spring also supports registering a MethodHandle via setVariable in EvaluationContext.

A MethodHandle with a bound target or some pre-bound arguments can simplify expressions and potentially reduce method invocation overhead in some cases.

However, do not switch to MethodHandle solely assuming it is always faster than Method. Measure on realistic workloads and choose the registration approach that is easiest to control.

When using MethodHandle, check the exact return type, parameter types, bound receiver, and number of arguments that expressions are allowed to pass.

## 9. Designing Small, Clear Functions with Minimal Side Effects

An exposed function becomes a capability that expressions can use. Therefore, the chosen method needs a clear scope of responsibility.

Prefer functions that:

- Have a name that accurately describes their behavior.
- Have a clear parameter count and parameter types.
- Return a predictable value.
- Have validation for input data.
- Do not mutate shared state unnecessarily.
- Do not perform I/O or call external systems during rule evaluation.
- Do not return service objects or objects with broad access permissions.

Suitable examples:

    #normalizeCode(#region)
    #isWithinRange(#amount, #minimum, #maximum)

These functions perform transformations or checks on provided data.

Be cautious with functions such as:

    #executeCommand(#input)
    #readFile(#path)
    #callExternalService(#url)
    #deleteAccount(#accountId)

These operations can cause side effects, access resources, or expand the expression's privileges. If business logic requires those operations, perform them in a service with permission controls and only place the verified result into the context.

## 10. Separating Registries by Usage Purpose

Do not have a single global function list containing every application operation and share it across all rules.

Create registries by purpose:

| Expression type | Functions that may be needed |
| --- | --- |
| Checking order conditions | normalizeCode, isWithinRange |
| Computing display price | roundMoney, calculateTax |
| Customer classification rules | isEligible, hasLoyaltyTier |
| Validating input data | isValidPostalCode, normalizePhone |

Each rule type should receive only the functions necessary for that task.

Example creating a context for order rules:

    StandardEvaluationContext createOrderRuleContext(
            OrderFacts facts) throws NoSuchMethodException {

        StandardEvaluationContext context =
            new StandardEvaluationContext(facts);

        context.registerFunction(
            "normalizeCode",
            RuleFunctions.class.getMethod(
                "normalizeCode",
                String.class
            )
        );

        context.registerFunction(
            "isWithinRange",
            RuleFunctions.class.getMethod(
                "isWithinRange",
                BigDecimal.class,
                BigDecimal.class,
                BigDecimal.class
            )
        );

        return context;
    }

This context does not need functions related to files, payments, account administration, or services outside the scope of order rules.

If the application has multiple rule groups, keep separate registries and review registry changes just as you would review a public API.

## 11. Functions and SimpleEvaluationContext

SimpleEvaluationContext provides a subset of SpEL features to support data binding or property-based expressions that require restricted permissions.

Functions can be registered using setVariable with a Method or MethodHandle:

    EvaluationContext context =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

    context.setVariable(
        "normalizeCode",
        normalizeMethod
    );

    String result = parser
        .parseExpression("#normalizeCode('vn')")
        .getValue(context, String.class);

This example shows that calling a function does not require using StandardEvaluationContext.registerFunction.

SimpleEvaluationContext does not support all SpEL features such as type references, constructor invocation, and bean references. It requires explicitly choosing the level of property and method support suited to the use case.

However, do not treat SimpleEvaluationContext as a guarantee of complete safety. A registered function is still an operation that expressions can invoke. Evaluate the method itself and every object accessible from the context.

## 12. The Function List Is Not the Only Security Boundary

Explicitly registering a few functions helps control named functions. But expressions can also access other capabilities through:

- Root object.
- Variables containing objects with methods.
- PropertyAccessor.
- MethodResolver.
- BeanResolver.
- ConstructorResolver.
- TypeLocator.
- Registered functions or MethodHandles.

For example, even if only the normalizeCode function is registered, if the root object is a service with administrative or I/O methods and method invocation is still allowed, an expression could attempt to call those methods through another path.

Therefore, design the entire EvaluationContext according to least privilege:

1. The root object contains only the necessary data.
2. Variables include only necessary facts or objects.
3. The function registry includes only approved methods.
4. Do not register a BeanResolver if expressions do not need beans.
5. Do not grant constructor or type access if not needed.
6. PropertyAccessor and MethodResolver should be restricted to the intended target.

Spring documentation warns against using StandardEvaluationContext to evaluate expressions from untrusted sources. SimpleEvaluationContext restricts part of the language on a best-effort basis, but still does not guarantee safety if exposed objects, resolvers, variables, or functions contain dangerous operations.

If end users can enter SpEL themselves, consider a structured rule language or a restricted DSL instead of allowing general-purpose expressions.

## 13. Controlling Function Arguments and Results

A safe function still needs to handle inputs properly.

Example:

    public static BigDecimal calculateDiscount(
            BigDecimal amount,
            BigDecimal rate) {

        if (amount == null || rate == null) {
            throw new IllegalArgumentException(
                "Amount and rate are required"
            );
        }

        if (rate.compareTo(BigDecimal.ZERO) < 0
                || rate.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException(
                "Rate must be between 0 and 1"
            );
        }

        return amount.multiply(rate);
    }

Do not assume that expressions will always pass valid values. Rules may contain null, out-of-bounds values, or incompatible data types.

Items to control:

- Nullability of each parameter.
- Element count limits if accepting collections or varargs.
- Data types and conversion rules.
- Valid value ranges.
- Return value type.
- Behavior when the function fails.

Avoid having a function accept an overly broad object just to read a single field. Passing the needed value directly or a narrow DTO is easier to control.

## 14. Managing Contexts and Function Lifecycles

Functions are registered in an EvaluationContext. A context can hold variables that change per evaluation.

A manageable way to organize this is:

- Keep the parser and parsed expression if the rule source does not change.
- Create a context per request or per evaluation when the context contains dynamic data.
- Register the same approved allow-list of functions.
- Do not modify the registry arbitrarily while expressions are in use.
- Do not share mutable variables across requests without concurrency control.

Example:

    Expression rule =
        parser.parseExpression(
            "#isWithinRange(#amount, #minimum, #maximum)"
        );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.registerFunction(
        "isWithinRange",
        rangeMethod
    );

    context.setVariable("amount", amount);
    context.setVariable("minimum", minimum);
    context.setVariable("maximum", maximum);

    Boolean allowed =
        rule.getValue(context, Boolean.class);

The Expression is parsed once. The context supplies data and functions for the current evaluation.

If a function depends on mutable state or services, clearly define the target lifecycle and synchronization approach instead of placing a shared mutable object into every context.

## 15. Common Errors When Exposing Functions

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Function not found | Not registered or wrong call name | Check registry and name after # |
| Incompatible method | Wrong signature or argument types | Check parameter types and conversion |
| Function name overwritten | Name collision with variable | Use separate naming namespaces and avoid overlap |
| Cannot invoke MethodHandle | Handle has unbound/mismatched receiver or parameter types | Check MethodType, target, and argument count |
| Function works in one context but not another | Other context did not register the same function | Check where EvaluationContext is created |
| Expression can invoke unexpected operations | Root object or resolver exposes extra privileges | Narrow context and method access |
| SimpleEvaluationContext cannot perform desired operation | Needed feature is not in the enabled subset | Check the builder and choose the right feature set |
| Function causes unintended side effects | Method performs I/O or mutates state | Move operation to a permission-controlled service |

When debugging, check in this order:

1. Does the expression use the right #functionName(...) call syntax?
2. Does the evaluating context have that name registered?
3. Does the function name collide with a variable?
4. Does the Method or MethodHandle have the exact signature?
5. Are argument types compatible?
6. Did the function throw an exception at runtime?

Successful parsing does not mean the function is registered. Function lookup and invocation occur when the expression is evaluated.

## 16. Checklist When Designing a Function Registry

Before exposing functions to SpEL, determine:

1. Which operations does the expression actually need?
2. Can that operation be implemented as a small, pure function without side effects?
3. Does the method have a clear public signature and specific parameter types?
4. Is varargs needed, or is a fixed number of parameters sufficient?
5. Does the function name collide with any existing variable?
6. Does the function return an overly broad or sensitive object?
7. Can the function access files, network, database, or mutate state?
8. Can the registry be separated by rule type?
9. Do the root object and other resolvers expose additional methods beyond the function list?
10. Does the expression come from an untrusted source?
11. Is the context created and managed according to the proper request lifecycle?
12. Can SimpleEvaluationContext or a more restricted DSL be used?

If a function is not needed for the rules, do not register it merely for convenience.

## 17. Key Takeaways

- Functions are registered by the application and called using the #functionName(...) syntax.
- A Method can be registered via EvaluationContext.setVariable().
- StandardEvaluationContext provides registerFunction() for Method and MethodHandle.
- MethodHandle registration via StandardEvaluationContext has been available since Spring Framework 6.1.
- Function invocation supports varargs.
- Functions and variables share a namespace; names must avoid collisions.
- Registering a function does not automatically expose every method in its containing class.
- Method invocation on the root object or a variable is a separate mechanism and also needs control.
- Create an explicit allow-list per rule type; do not automatically expose an entire utility class.
- Prefer small, clear functions with minimal side effects and input validation.
- SimpleEvaluationContext can use functions via setVariable, yet exposed capabilities still need control.
- Do not use StandardEvaluationContext to evaluate expressions from untrusted sources; SimpleEvaluationContext is not a guarantee of absolute safety either.
- The function registry is only part of access control; the root object, variables, accessors, and resolvers also need to be restricted.

Treat every registered function as a permission granted to expressions. Only expose operations actually needed by rules, keep signatures simple, and restrict the entire EvaluationContext according to the principle of least privilege.

## References

- Spring Framework Reference — Functions: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/functions.html
- Spring Framework Reference — Evaluation: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework Javadoc — StandardEvaluationContext: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html
- Spring Framework Javadoc — SimpleEvaluationContext: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html
