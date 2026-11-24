# Code Execution Risks When Allowing Arbitrary Types in SpEL

Spring Expression Language (SpEL) supports referencing Java types via the T(...) operator. This feature is useful when an expression needs constants, static fields, or static methods of a class. For example, an expression can use Math.PI or call Math.max(...).

However, when an expression is taken from a user, tenant, or external source while EvaluationContext allows broad type resolution and method invocation, the expression can access powerful JVM APIs. When combined with permissions to call methods, constructors, or bean references, a configuration expression can become a vector for executing unintended actions.

This lesson explains the role of TypeLocator, the privileges opened up by type references, why syntax checking alone is insufficient to protect the application, and how to design contexts using allowlists and least privilege.

## 1. Objectives and prerequisites

After this lesson, you can:

- Understand the T(...) syntax and how SpEL resolves class names.
- Distinguish TypeLocator from MethodResolver and ConstructorResolver.
- Identify the risks when expressions are permitted to reference arbitrary classes.
- Explain why static methods and constructors can produce side effects.
- Restrict type references using an allowlist TypeLocator.
- Combine type restrictions with restrictions on methods, constructors, beans, and property access.
- Choose SimpleEvaluationContext or a dedicated context for untrusted expressions.
- Design data passing patterns and test rejection policies.

You should know basic SpEL syntax, StandardEvaluationContext, MethodResolver, and how to pass data via variables in EvaluationContext.

## 2. What is a type reference in SpEL?

The T(...) operator lets an expression reference a Java type by name. Example:

~~~text
T(java.lang.Math).PI
~~~

The expression reads the PI constant from the Math class.

Static methods can be called:

~~~text
T(java.lang.Math).max(10, 20)
~~~

The result is 20.

For classes in the java.lang package, the default TypeLocator usually allows short names thanks to the default import. Example:

~~~text
T(Math).max(10, 20)
~~~

In documentation and production configurations, using fully qualified names such as java.lang.Math helps readers identify the exact class more accurately.

A type reference does not create an instance. It supplies the Class object so the rest of the expression can access appropriate static members. Calling methods still requires method resolution; creating instances with the new syntax is a separate capability involving ConstructorResolver.

## 3. What is TypeLocator responsible for?

TypeLocator is the component in EvaluationContext used to resolve a type name into a Java Class. When SpEL encounters T(...), it asks TypeLocator to find the corresponding type.

With StandardEvaluationContext, the default TypeLocator is typically StandardTypeLocator. This resolver uses a class loader to find types and supports configured imports, including the default java.lang import.

You can set a different TypeLocator:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeLocator(customTypeLocator);
~~~

The key point is that TypeLocator decides which type names an expression can reference. If the resolver permits any class the class loader can find, an expression can reach a very broad range of APIs.

TypeLocator does not execute methods itself. It only resolves type names. Risk arises when the expression proceeds to use that Class to read static fields, call static methods, or combine with other capabilities of EvaluationContext.

## 4. Why can allowing arbitrary types be dangerous?

A Java class can provide capabilities far beyond pure computation. Some APIs can:

- Read system information or environment configuration.
- Access files and directories.
- Spawn processes or interact with other processes.
- Open network connections or call external services.
- Modify system properties or global state.
- Create objects that have access to other resources.

API groups such as Runtime, ProcessBuilder, Files, or System illustrate why referencing arbitrary classes must be controlled. Resolving a class name by itself does not mean an action has occurred; however, if the expression is permitted to call suitable methods, it can trigger behavior far beyond the original computational intent.

Safe example in this lesson:

~~~text
T(java.lang.Math).max(#minimum, #requested)
~~~

The expression only computes the larger of two variables.

Conversely, a user-supplied expression should not be allowed to choose arbitrary classes and call arbitrary methods. If the context allows access to powerful system APIs, the expression can perform actions with the privileges of the application process.

The consequences depend on the JVM process's privileges. If the application runs with permission to read configuration files, access the internal network, or connect to databases, an expression can exploit those exact privileges held by that process.

## 5. Type references are only part of the permission surface

To assess risk, examine the other capabilities of EvaluationContext:

| Component | Capability |
|---|---|
| TypeLocator | Resolves class names for T(...) |
| MethodResolver | Finds and calls methods on objects or referenced types |
| ConstructorResolver | Resolves constructors for the new syntax |
| BeanResolver | Retrieves beans using the @beanName syntax |
| PropertyAccessor | Reads or writes properties and fields |
| Function/variable | Exposes methods or objects via variables and functions |
| Parser configuration | Controls features such as auto-grow and expression limits |

Restricting TypeLocator alone is not enough if the root object already holds a service with sensitive methods. Similarly, blocking methods on a referenced class does not stop calling a dangerous method via a bean reference if BeanResolver still exposes that bean.

A sound security policy must explicitly identify which capabilities expressions need, and grant only those capabilities.

## 6. Do not use full-privilege StandardEvaluationContext for untrusted expressions

StandardEvaluationContext is designed to be flexible and typically provides reflection resolvers/accessors useful for application-controlled expressions. It fits many internal integration points, but one should not assume this context is a sandbox for arbitrary input.

If you receive a SpEL string from a request or tenant and evaluate it with StandardEvaluationContext using default resolvers, the expression can hold far more power than a simple filter condition needs.

Example risky use case:

1. A user enters an expression string.
2. The backend parses that string.
3. The backend evaluates it using a context containing internal services or objects.
4. The expression can reference types, call methods, or read data beyond expectations.
5. Actions execute with the application's privileges.

Do not address the issue merely by blocking a few class name or method name strings. Blocklists easily miss aliases, overloads, other classes with similar capabilities, or indirect access paths.

Start from an allowlist: explicitly specify the permitted type names, properties, methods, and data.

## 7. Use an allowlist TypeLocator

If a use case genuinely needs type references, create a TypeLocator that returns only permitted classes.

The example below illustrates a very small allowlist permitting only Math:

~~~java
public final class AllowlistTypeLocator implements TypeLocator {

    private final Map<String, Class<?>> allowedTypes = Map.of(
        "Math", Math.class,
        "java.lang.Math", Math.class
    );

    @Override
    public Class<?> findType(String typeName) {
        Class<?> type = allowedTypes.get(typeName);

        if (type == null) {
            throw new EvaluationException(
                "Type is not allowed: " + typeName
            );
        }

        return type;
    }
}
~~~

Registering on the context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeLocator(new AllowlistTypeLocator());
~~~

Then the expression can use:

~~~text
T(Math).max(#left, #right)
~~~

Type names not in the allowlist are rejected.

This is an illustrative example of a type resolution policy. In a real application, consider:

- Using only fully qualified names to avoid unintended aliases.
- Not allowing package wildcards or overly broad prefixes.
- Not automatically allowing every subclass or implementation in a package.
- Keeping the class list short with clear ownership.
- Testing permitted names, disallowed names, and aliases.
- Avoiding returning detailed classpath or internal structure information to the client on rejection.

If the use case does not need T(...), the simpler approach is not to provide a TypeLocator capable of resolving arbitrary classes.

## 8. A type allowlist does not restrict methods yet

If TypeLocator allows java.lang.Math, an expression can reference that class. However, if MethodResolver remains broad, the expression can call many public methods of Math, not just the one method the application intended to allow.

Therefore, there are two policy layers:

1. **Type allowlist:** which classes may be referenced?
2. **Method allowlist:** which methods on those classes may be invoked?

You can use a MethodFilter with ReflectiveMethodResolver or a custom MethodResolver to restrict signatures. For example, the application might want to allow only Math.max with two suitable numeric arguments. In that case, the filter needs to check the method name and parameter types, rather than keeping every method on Math.

If replacing the MethodResolver list, do not leave a general reflective resolver behind the allowlist resolver, because the trailing resolver could still resolve calls that were rejected.

Remember that methods can be called via the root object or beans without needing T(...). Consequently, the method allowlist must apply to all invocation paths an expression can use.

## 9. Constructors and the new syntax are a separate privilege

SpEL can instantiate objects using the new syntax when ConstructorResolver and TypeLocator allow it:

~~~text
new java.math.BigDecimal('12.50')
~~~

This is a capability separate from T(...). Blocking type references should not be taken as proof that constructors are blocked if the context still has a permissive ConstructorResolver.

If an expression only needs to compute over existing data, there is usually no need to allow arbitrary object creation. You should:

- Not grant constructor resolution if the use case does not need it.
- Only allow constructors of small value types if genuinely required.
- Avoid allowing classes whose constructors initialize resources or perform actions.
- Check limits on argument sizes and types.

TypeLocator, ConstructorResolver, and MethodResolver must be configured consistently. Allowlisting types without restricting constructors or methods can still leave unintended behaviors open.

## 10. Bean references and property access also need restrictions

Expressions can access beans with @beanName if BeanResolver is configured. A bean may hold references to services, repositories, or system resources. Thus, an expression without T(...) can still perform actions through exposed beans.

PropertyAccessor also matters. The root object or beans may contain sensitive properties; allowing inappropriate property reads or writes can leak data or alter state.

Design principles:

- Do not expose ApplicationContext or BeanFactory to untrusted expressions.
- Do not register BeanResolver if the use case does not need bean references.
- Use a small DTO as the root object, containing only the needed data.
- Prefer read-only property access for read-only expressions.
- Do not pass repositories, administrative services, large entity graphs, or objects containing secrets.
- If a few operations are needed, expose a small facade with pure methods and an explicit allowlist.

## 11. SimpleEvaluationContext for restricted use cases

SimpleEvaluationContext is designed for cases needing only a subset of SpEL features. It does not provide powerful capabilities such as type references, constructor invocations, and bean references like StandardEvaluationContext.

Example read-only context:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Or a context allowing read/write data binding:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadWriteDataBinding().build();
~~~

Method invocation is not broadly enabled by default; if a use case needs methods, configure a clearly controlled resolver. Choose read-only if only evaluating conditions or retrieving values.

SimpleEvaluationContext is a better fit for many restricted data-binding use cases, though you still need to review the supplied objects and accessors. No EvaluationContext should be treated as an absolute sandbox if the application passes in highly privileged objects.

## 12. Pass data via variables instead of string-concatenating expressions

If users want to choose a value, pass the data via variables and keep the expression fixed.

Example:

~~~java
Expression expression =
    parser.parseExpression("#amount >= #minimum");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("amount", amount);
context.setVariable("minimum", minimum);
~~~

This separates data from syntax. Users cannot alter the expression structure simply by putting special characters into the amount value.

If users need to configure conditions, define a constrained grammar such as field/operator/value, and have the backend translate the validated structure into internal logic. A small condition language is usually much easier to constrain than letting users enter general-purpose SpEL.

Do not concatenate input strings directly into T(...), method names, property paths, or other syntactic parts.

## 13. Process for building a safe context

A practical process:

1. Determine whether the expression genuinely needs type references. If not, do not expose this capability.
2. Identify input data and create a DTO containing only the necessary properties.
3. Choose SimpleEvaluationContext if the use case only needs data binding and a restricted feature set.
4. If StandardEvaluationContext must be used, replace the default TypeLocator with an allowlist.
5. Restrict MethodResolver by target type and method signature.
6. Do not grant ConstructorResolver, BeanResolver, or write access if not needed.
7. Keep the root object and variables free of services or sensitive resources.
8. Limit expression length, expression count, and evaluation cost at the application layer.
9. Evaluate with strongly typed data and handle exceptions at the application boundary.
10. Log enough for diagnostics without logging secrets or full sensitive payloads.

Application-layer length limits and timeouts are supplementary measures. They do not replace capability allowlists and do not turn an overly privileged expression into a safe one.

## 14. Testing type reference policies

Create tests for the following cases:

| Case | Expected outcome |
|---|---|
| Referencing allowlisted T(Math) | Resolves successfully |
| Referencing a non-allowlisted class | Rejected by TypeLocator |
| Using an unregistered alias | Rejected |
| Calling an allowlisted method | Succeeds with valid argument types |
| Calling another method on an allowed class | Rejected if method allowlist forbids it |
| Calling an overload with a different signature | Rejected |
| Using new syntax when constructors are restricted | Cannot instantiate |
| Referencing a bean when BeanResolver is not provided | Bean cannot be resolved |
| Reading or writing a property outside the allowlist | Accessor rejects |
| Passing input with syntax characters into a variable | Value is still treated as data |
| Using a read-only context | Cannot write properties through that context |

In addition to unit tests, test the exact context the application uses at runtime. A manually constructed test context may differ from the context configured by a Spring integration point.

## 15. Common errors and diagnostics

| Symptom | Common cause | Resolution |
|---|---|---|
| T(...) fails to resolve | TypeLocator cannot find class name or class is not allowlisted | Check fully qualified name and list of permitted types |
| Class resolves but method cannot be called | MethodResolver does not permit it or signature does not match | Check method allowlist and argument types |
| Unwanted method can still be called | General reflective resolver remains in the list | Replace the entire resolver list or filter existing resolvers |
| Expression using new still works | ConstructorResolver still has permission | Restrict or remove constructor resolution |
| Expression can still call services | BeanResolver or root object still exposes services | Narrow bean access and root DTO |
| TypeLocator allowlisted yet data still leaks | PropertyAccessor or other methods provide access paths | Review all capabilities, not just type references |
| Parse succeeds but evaluation fails | Type resolution, method resolution, or runtime conversion error | Distinguish parse errors from evaluation errors |
| Class name other than alias is still accepted | TypeLocator supports broad imports or aliases | Accept only specified canonical names |

## 16. Practice exercises

1. Parse T(java.lang.Math).PI and T(java.lang.Math).max(10, 20) in an internal context.
2. Create a TypeLocator allowing only Math and verify that another class name is rejected.
3. Try the short name Math and the fully qualified name java.lang.Math; decide which aliases are allowed.
4. Add a MethodFilter allowing only one specific Math method signature.
5. Try another method on the same class and confirm the method filter rejects it.
6. Create a read-only SimpleEvaluationContext and observe that type reference features are unsupported.
7. Test an expression with a variable containing special syntax characters to verify data is not interpreted as syntax.
8. Write tests confirming BeanResolver and ConstructorResolver are not granted when the use case does not need them.

## 17. Checklist before permitting type references

- [ ] Does the expression truly need T(...)?
- [ ] Is the expression source completely trusted?
- [ ] Does TypeLocator have an exact class name allowlist?
- [ ] Are there any aliases or package imports unnecessarily broadening scope?
- [ ] Does MethodResolver restrict methods and overloads?
- [ ] Is ConstructorResolver removed or restricted?
- [ ] Is BeanResolver genuinely necessary?
- [ ] Do the root object and PropertyAccessor expose sensitive data?
- [ ] Can SimpleEvaluationContext be used for a restricted use case?
- [ ] Is runtime data passed via variables instead of string concatenation?
- [ ] Have both allowed and rejected types/methods been tested?
- [ ] Are expression cost and size limits enforced at the application layer?

## 18. Conclusion

The T(...) operator lets SpEL reference Java classes and access static members. TypeLocator decides which classes can be resolved; MethodResolver and ConstructorResolver decide what subsequent behaviors can be invoked or instantiated. If arbitrary types are permitted in untrusted expressions, the application can inadvertently expose APIs with privileges to read files, access the network, spawn processes, or alter system state. Prefer disallowing type references when unneeded, use an allowlist TypeLocator if mandatory, restrict method/constructor/bean/property access simultaneously, and pass data via variables in a narrow context.