# Checking registered variable, bean, and function names

When debugging a Spring Expression Language (SpEL) expression, a common error is that the expression references a **variable**, **Spring bean**, or **function** that has not been registered in the EvaluationContext used for evaluation. The syntax of these three reference types differs, the mechanisms for providing data also differ, and they may exist in different contexts.

An expression may parse successfully yet fail when calling getValue because the name is undeclared, the casing is wrong, the bean resolver is unconfigured, or the function has an incompatible signature. An effective debugging approach is to identify the reference type, inspect the exact EvaluationContext at evaluation time, and then verify the name and data type actually provided by the context.

## Distinguishing variable, bean, and function

Three common reference forms:

| Type | Syntax in SpEL | How to register or provide |
|---|---|---|
| Variable | **#minimumPrice** | setVariable(name, value) |
| Bean | **@pricingService** | BeanResolver, typically BeanFactoryResolver |
| Function | **#normalize(value)** | registerFunction(name, Method) |

The leading character helps identify what SpEL is looking up:

- **#name** requests a variable in EvaluationContext.
- **@name** requests a bean through BeanResolver.
- **#name(...)** invokes a function registered under that name.
- **name** without # is usually a property of the current root object, not a variable.
- **#root** and **#this** are special variables managed by SpEL.

Do not swap these syntaxes back and forth just to try fixing an error. First, determine whether the name in the expression represents data, a bean, or a function.

## Checking variables

Applications register variables on EvaluationContext. With StandardEvaluationContext, you can use **setVariable(...)**:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("minimumPrice", new BigDecimal("50.00"));
context.setVariable("enabled", true);
context.setVariable("region", "VN");
~~~

In the expression, the variable name must include #:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression(
                "#enabled and #region == 'VN' and #minimumPrice >= 50");

Boolean accepted =
        expression.getValue(context, Boolean.class);
~~~

If you write **minimumPrice** instead of **#minimumPrice**, SpEL looks for a property on the current root object. If the root object lacks that property, the expression can throw an error even though the variable minimumPrice was registered properly.

You can read a variable from Java using **lookupVariable(...)**:

~~~java
Object minimumPrice =
        context.lookupVariable("minimumPrice");
~~~

The name passed to lookupVariable does not include #. This is how you inspect the value registered in the exact context the application intends to use for evaluation.

### Checking the right EvaluationContext

Variables belong to EvaluationContext, not to ExpressionParser, and are not permanently attached to Expression. If an application parses an expression and then evaluates it with a different context, variables set in the original context will not automatically appear in the new context.

~~~java
Expression expression =
        parser.parseExpression("#minimumPrice >= 50");

StandardEvaluationContext configuredContext =
        new StandardEvaluationContext();
configuredContext.setVariable(
        "minimumPrice",
        new BigDecimal("75.00"));

StandardEvaluationContext emptyContext =
        new StandardEvaluationContext();

// Evaluate with configuredContext: the variable is registered.
Boolean first =
        expression.getValue(configuredContext, Boolean.class);

// Evaluate with emptyContext: the variable minimumPrice is not here.
~~~

When debugging, inspect the context object passed into the exact getValue call. A common mistake is initializing variables in one bean or helper, while elsewhere creating a new context and evaluating the expression with that new context.

If an expression is cached or reused, that does not mean variables are cached with the expression. Each evaluation still uses the root object and EvaluationContext passed to that call.

### Checking variable names

Variable names must be consistent between where they are registered and where they are referenced:

~~~java
context.setVariable("customerId", "CUS-1024");
~~~

Correct expression:

~~~text
#customerId
~~~

Names like **#customerID**, **#CustomerId**, or **#customer_id** are different names. Do not assume variable names are automatically normalized for casing or underscores.

You should declare variable names as constants in Java if the same name is used in multiple places:

~~~java
public final class SpelVariableNames {
    public static final String CUSTOMER_ID = "customerId";

    private SpelVariableNames() {
    }
}
~~~

~~~java
context.setVariable(
        SpelVariableNames.CUSTOMER_ID,
        customerId);
~~~

This reduces typos when building contexts and when maintaining expressions stored in configuration.

### Null variables vs. unregistered variables

A variable can be registered with a null value:

~~~java
context.setVariable("middleName", null);
~~~

A null value differs from an unregistered name, but when using **lookupVariable(...)**, both situations can return null. This API does not provide a public containsVariable operation to reliably distinguish the two cases.

If business logic needs to distinguish an absent variable from a declared variable whose value is null, maintain a list of allowed variable names or separate metadata at the application layer. Another option is to use a wrapper type representing presence/absence instead of overloading null with multiple meanings.

When a variable can be null, the expression needs to handle null before accessing properties or invoking methods on that value.

## Checking bean references

Bean references in SpEL use the **@** prefix:

~~~text
@pricingService
~~~

This syntax requires EvaluationContext to have a **BeanResolver** to look up beans by name. Simply creating a StandardEvaluationContext does not automatically make all Spring beans accessible via @.

For a Spring application, you can configure **BeanFactoryResolver**:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setBeanResolver(
        new BeanFactoryResolver(applicationContext));
~~~

Once configured, the expression can reference beans:

~~~java
Expression expression =
        parser.parseExpression("@pricingService");
~~~

Or invoke methods on a bean if method invocation is supported:

~~~java
Expression expression =
        parser.parseExpression(
                "@pricingService.calculate(#order)");
~~~

When a bean reference fails, check both conditions: whether the bean exists in BeanFactory and whether EvaluationContext has an appropriate BeanResolver.

### Checking bean names

The name in the expression must match the bean name or alias registered in the container. For example:

~~~java
@Component("pricingService")
public class PricingService {
    // ...
}
~~~

Referencing expression:

~~~text
@pricingService
~~~

If the bean was registered under the name **priceService**, the expression @pricingService will not find that bean unless pricingService is a valid alias.

You can check the name on the application side using BeanFactory or ApplicationContext:

~~~java
boolean exists =
        applicationContext.containsBean("pricingService");
~~~

If the bean does not exist, check component scan, profiles, conditional configuration, bean names declared in @Bean, and aliases. Also check the right ApplicationContext if the application has a parent context or multiple child contexts.

Do not call getBean just to probe a name if fetching the bean might initialize a lazy singleton or trigger initialization logic with side effects. containsBean is more suitable for a basic existence check; verifying the actual bean should be done in an appropriate test environment.

### Checking the context's BeanResolver

An application may have the bean in ApplicationContext yet still fail to access it with @ syntax if the SpEL evaluation context lacks a BeanResolver.

When creating StandardEvaluationContext manually, configure it explicitly:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

context.setBeanResolver(
        new BeanFactoryResolver(applicationContext));
~~~

If an expression is evaluated by a Spring integration, that integration may create its own EvaluationContext and supply a BeanResolver or another access mechanism. Do not assume the context created by an annotation is identical to a context the application creates manually.

When debugging, find the exact place where the context is created for that expression and inspect the resolver attached there. Adding BeanResolver to a context that is not used in getValue will not fix the error.

### Bean name vs. variable name

Both syntaxes can contain the same word yet look up in two different places:

~~~java
context.setVariable("pricingService", service);
~~~

- **#pricingService** reads the variable registered in the context.
- **@pricingService** looks up a bean via BeanResolver.

Registering a variable does not create a bean. Registering a bean in Spring also does not automatically create a variable of the same name. If the expression uses the wrong prefix, SpEL will look for the wrong kind of object.

## Checking registered functions

Functions in SpEL are referenced with # followed by an argument list:

~~~text
#normalize('  Spring  ')
~~~

Unlike plain variables, functions have call parentheses and are registered with a Java Method. StandardEvaluationContext provides **registerFunction(name, method)**.

For example, defining a static function:

~~~java
public final class TextFunctions {

    private TextFunctions() {
    }

    public static String normalize(String value) {
        return value == null ? null : value.trim().toLowerCase();
    }
}
~~~

Registering the method:

~~~java
Method normalizeMethod =
        TextFunctions.class.getMethod(
                "normalize",
                String.class);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.registerFunction(
        "normalize",
        normalizeMethod);
~~~

Then calling it in an expression:

~~~java
Expression expression =
        parser.parseExpression("#normalize('  Spring  ')");

String result =
        expression.getValue(context, String.class);
~~~

The result is **spring**. The name passed to registerFunction does not have #; the # sign is only used in the expression.

### Checking the method used for registration

When a function cannot be called, verify:

- The Method was retrieved from the right class.
- The method name in registerFunction matches the name in the expression.
- The method signature accepts the right number and types of arguments.
- The method suits the function invocation mechanism, typically public static.
- The method is not confused among overloads when retrieving Method via reflection.
- The context passed to getValue is the exact context on which the function was registered.

Retrieve Method via getMethod with explicit parameter types:

~~~java
Method method =
        TextFunctions.class.getMethod(
                "normalize",
                String.class);
~~~

This explicitly identifies the overload to register. If a class has multiple methods with the same name but different parameters, do not look up a method by name alone and pick the first element from the reflection list.

### Distinguishing functions and object methods

A function is invoked by its registered name:

~~~text
#normalize(#input)
~~~

An object method is invoked on a target:

~~~text
#customer.getName()
~~~

A function is not a Spring bean and is not referenced with @. Nor does it appear automatically just because a Java class has a static method. The application must register the Method into EvaluationContext before the expression calls the function.

If you want to call a method of a Spring service, use a bean reference and method invocation when the context permits, or call the service from Java and pass the result into the context. There is no need to register the same service method as a function if a bean reference already covers the use case.

### Functions and variables share the # prefix

Variables and functions both use #, so distinguish the reference form:

- **#threshold** reads a variable value.
- **#normalize(value)** invokes a function.
- **#root** and **#this** are special SpEL variables.

Avoid registering the same name as both a variable and a function. Duplicate names make expressions confusing and can conflict in the context's variable/function storage mechanism. Use separate naming conventions, such as nouns for variables and verbs for functions.

## Checking in the right EvaluationContext type

Not all EvaluationContexts support the same capabilities:

| Capability | StandardEvaluationContext | SimpleEvaluationContext |
|---|---|---|
| Root object and property access | Yes, configurable | Yes, within builder/accessor scope |
| Variables | Yes | Yes in supported configurations |
| Bean references | Yes if BeanResolver attached | Does not support bean references |
| Type references T(...) | Yes with TypeLocator | Not supported |
| Constructor invocation | Yes with ConstructorResolver | Not supported |
| Method invocation | Yes per configured resolver | Not enabled by default; can be restricted via appropriate builder |
| Function registration | Supported via StandardEvaluationContext | Does not provide full capabilities like StandardEvaluationContext |

If an expression uses @bean or functions while the actual context is a restricted context, check the capabilities of that context type before looking for a naming mistake. You may need to move that processing to Java or use StandardEvaluationContext with explicitly restricted resolvers.

## Distinguishing parse errors from evaluation errors

Variable, bean, or function names are typically looked up when the expression is evaluated. Therefore, a string can parse successfully yet fail at getValue.

Two phases to distinguish:

- **ParseException:** the string does not conform to SpEL syntax, such as missing parentheses or malformed call structure.
- **EvaluationException:** the expression is syntactically valid, but the name does not exist in the context, the resolver is unconfigured, or the call cannot be executed with the current data.

Example:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("#normalize(#name)");
} catch (ParseException ex) {
    throw new IllegalArgumentException(
            "Invalid SpEL syntax", ex);
}

try {
    String result =
            expression.getValue(context, String.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException(
            "Cannot resolve or invoke the expression reference", ex);
}
~~~

If the error is in a function, check the registered name and Method. If the error is in a bean, check BeanResolver and the bean name. If the error is in a variable, check setVariable and the context passed in. Do not alter the syntax when the real cause is a missing registration.

## Systematic debugging workflow

When an expression reports a missing variable, bean, or function, check in order:

1. **Identify the reference syntax.** # is variable/function; @ is bean; a name without # is typically a property of the root object.
2. **Identify the actual context.** Find where EvaluationContext is created and which object is passed into getValue.
3. **Check registration.** For variables, use lookupVariable; for beans, check BeanFactory and BeanResolver; for functions, check the Method passed to registerFunction.
4. **Match exact names.** Check casing, aliases, prefixes, and typos.
5. **Check data types.** Verify the number and types of function/method arguments, root object type, and property types.
6. **Check resolvers.** Confirm the context has the appropriate PropertyAccessor, MethodResolver, or BeanResolver.
7. **Separate parse and evaluation.** Record errors at the appropriate phase.
8. **Create a minimal reproduction.** Use a small context, one expression, and a fixed dataset to reproduce.

An example checking a variable:

~~~java
Object value =
        context.lookupVariable("minimumPrice");

if (value == null) {
    // Check additional application metadata if null can be a valid value.
}
~~~

An example checking a bean:

~~~java
if (!applicationContext.containsBean("pricingService")) {
    throw new IllegalStateException(
            "Required bean is not registered");
}
~~~

An example checking a function:

~~~java
Method method =
        TextFunctions.class.getMethod(
                "normalize",
                String.class);

context.registerFunction("normalize", method);
~~~

These checks must run on the exact context or configuration creating the context used for evaluation. Testing a different test context does not prove the production context is configured the same way.

## Testing registration with JUnit

You should have a small test proving variables, beans, and functions are supplied properly:

~~~java
@Test
void evaluatesVariableAndFunction() throws Exception {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("name", "Spring");

    Method normalize =
            TextFunctions.class.getMethod(
                    "normalize",
                    String.class);

    context.registerFunction("normalize", normalize);

    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("#normalize(#name)");

    String result =
            expression.getValue(context, String.class);

    assertEquals("spring", result);
}
~~~

For bean references, the test needs to configure BeanResolver or use a Spring-created context in an integration test:

~~~java
context.setBeanResolver(
        new BeanFactoryResolver(applicationContext));
~~~

Then evaluate the expression using @beanName and assert the right bean was invoked. You can use a fake bean or spy to verify invocation count and arguments.

In addition to success tests, test wrong names, missing registrations, wrong argument types, and contexts that do not support the capability. Tests should assert that errors are reported at the right phase and no unexpected bean or function is called.

## Checking contexts of annotations and Spring integrations

When SpEL is used in an annotation or a Spring module, the framework may create its own EvaluationContext and supply certain variables, bean resolvers, or root objects automatically. These values do not necessarily match a context created manually with new StandardEvaluationContext().

For example, Spring Cache may provide method and parameter information for key expressions. Spring Security may provide a root object and variables according to the security context. Do not assume a variable name from one integration exists in another integration.

If the error only happens inside an annotation:

- Identify which integration is evaluating the expression.
- Look up the root object and variables provided by that integration.
- Check whether parameter names are discovered properly.
- Confirm whether beans/functions are exposed by the integration or need separate configuration.
- Write an integration test running through the annotation or interceptor itself instead of only testing the parser in isolation.

A manually constructed StandardEvaluationContext does not fully simulate the context created by a specific Spring module.

## Logging and diagnostics without exposing sensitive data

When debugging, record:

- Rule code or name.
- Failing reference type: variable, bean, function, or root property.
- Reference name normalized per logging policy.
- Type of EvaluationContext in use.
- Error phase: parse or evaluation.
- Root object type and required argument types, if non-sensitive.

Avoid logging full variable values, objects, or function arguments if they may contain tokens, personal data, or sensitive business data. For errors from user-entered expressions, do not return stack traces or internal class names to end users.

## Short checklist

- Use # for variables/functions, @ for beans, and direct property names for the root object.
- Register variables on the exact EvaluationContext using setVariable.
- Use lookupVariable to check variables; remember null does not distinguish unregistered from registered-as-null.
- Configure BeanResolver, such as BeanFactoryResolver, before using @beanName in a manually created context.
- Check the bean name or alias in the right ApplicationContext.
- Register functions with the matching Method via registerFunction.
- Check function signature, argument count, and argument types.
- Avoid duplicating names between variables and functions.
- Check the capabilities of the actual SimpleEvaluationContext or StandardEvaluationContext.
- Distinguish ParseException from EvaluationException.
- Check the context passed to getValue, not just a context configured elsewhere.
- Test both successful registration and missing/wrong-name cases.

## Conclusion

To debug variable, bean, and function names in SpEL, first distinguish the syntax properly: **#variable**, **@beanName**, and **#function(arguments)**. Variables are set with setVariable on EvaluationContext; beans require a BeanResolver to look up in the Spring container; functions require a Method registered with registerFunction.

An expression that parses successfully can still fail during evaluation if the context does not contain the needed name or does not support that reference type. Inspect the exact context passed into getValue, verify names and argument types, separate parse errors from evaluation errors, and write tests against the application's actual context configuration. Checking by each reference type helps find the root cause quickly without unnecessarily widening access permissions.
