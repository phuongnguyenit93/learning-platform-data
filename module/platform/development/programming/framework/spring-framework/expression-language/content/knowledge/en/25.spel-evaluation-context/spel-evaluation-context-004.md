# Registering PropertyAccessor, MethodResolver, and ConstructorResolver

**EvaluationContext** determines what data SpEL can see and manipulate when evaluating an expression. With **StandardEvaluationContext**, an application can extend how properties are accessed, how methods are found, and how constructors are found through three extension points: **PropertyAccessor**, **MethodResolver**, and **ConstructorResolver**.

These components separate three responsibilities:

- **PropertyAccessor** reads or writes a property on a target object.
- **MethodResolver** finds how to invoke a method on a target object given a name and arguments.
- **ConstructorResolver** finds how to create an instance of a requested type given the provided arguments.

Registering custom resolvers enables expressions to work with custom data models, restricts permitted operations, or integrates with application-specific object access mechanisms.

## What do the three extension points do?

| Component | Question it answers | Interface implemented |
|---|---|---|
| PropertyAccessor | Can a property with this name be read or written on the target object? | **PropertyAccessor** |
| MethodResolver | Can a method with this name be invoked with the current argument types? | **MethodResolver** |
| ConstructorResolver | Is there a suitable constructor to create this type with the current argument types? | **ConstructorResolver** |

Resolvers generally do not execute the operation directly when queried. They find a suitable execution strategy and return an executor. SpEL then invokes the executor when the expression is evaluated.

In StandardEvaluationContext, the default reflective implementations are typically:

- **ReflectivePropertyAccessor** to access JavaBean properties and eligible properties via reflection.
- **ReflectiveMethodResolver** to locate methods invocable via reflection.
- **ReflectiveConstructorResolver** to locate constructors invocable via reflection.

An application can add its own resolvers, replace the default list, or build an explicitly ordered list.

## Registering on StandardEvaluationContext

The straightforward way is to create a StandardEvaluationContext and add each component:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.addPropertyAccessor(new CustomPropertyAccessor());
context.addMethodResolver(new CustomMethodResolver());
context.addConstructorResolver(new CustomConstructorResolver());
~~~

The methods **addPropertyAccessor(...)**, **addMethodResolver(...)**, and **addConstructorResolver(...)** append implementations to the context's respective lists.

If you want to replace the entire list, you can use:

~~~java
context.setPropertyAccessors(propertyAccessors);
context.setMethodResolvers(methodResolvers);
context.setConstructorResolvers(constructorResolvers);
~~~

The `set...` methods replace the existing resolver/accessor list. When replacing the list, the application must supply all necessary implementations itself. If you omit the default reflective resolver, properties, methods, or constructors that it previously handled may no longer be accessible.

List order matters: SpEL tries the configured accessors or resolvers in order to find a matching component. When you need to prioritize a custom accessor while keeping reflective behavior as a fallback, configure the list in the desired order and place ReflectivePropertyAccessor, ReflectiveMethodResolver, or ReflectiveConstructorResolver in the fallback position.

## PropertyAccessor: customizing how properties are read and written

**PropertyAccessor** enables SpEL to access a property on a target object. This interface provides the following main operations:

~~~java
Class<?>[] getSpecificTargetClasses();

boolean canRead(
        EvaluationContext context,
        Object target,
        String name) throws AccessException;

TypedValue read(
        EvaluationContext context,
        Object target,
        String name) throws AccessException;

boolean canWrite(
        EvaluationContext context,
        Object target,
        String name) throws AccessException;

void write(
        EvaluationContext context,
        Object target,
        String name,
        Object newValue) throws AccessException;
~~~

Meaning:

- **getSpecificTargetClasses()** indicates which target types the accessor applies to. Return null if the accessor is not restricted by target type.
- **canRead(...)** indicates whether the accessor can read the property.
- **read(...)** returns the property value as a TypedValue.
- **canWrite(...)** indicates whether the accessor can write the property.
- **write(...)** performs the property update.

For example, an accessor that only allows reading a selected set of keys from a Map:

~~~java
public class AllowlistedMapPropertyAccessor
        implements PropertyAccessor {

    private static final Set<String> ALLOWED =
            Set.of("theme", "locale");

    @Override
    public Class<?>[] getSpecificTargetClasses() {
        return new Class<?>[] { Map.class };
    }

    @Override
    public boolean canRead(
            EvaluationContext context,
            Object target,
            String name) {
        return target instanceof Map<?, ?> map
                && ALLOWED.contains(name)
                && map.containsKey(name);
    }

    @Override
    public TypedValue read(
            EvaluationContext context,
            Object target,
            String name) throws AccessException {
        if (!canRead(context, target, name)) {
            throw new AccessException("Property is not available: " + name);
        }

        Map<?, ?> map = (Map<?, ?>) target;
        return new TypedValue(map.get(name));
    }

    @Override
    public boolean canWrite(
            EvaluationContext context,
            Object target,
            String name) {
        return false;
    }

    @Override
    public void write(
            EvaluationContext context,
            Object target,
            String name,
            Object newValue) throws AccessException {
        throw new AccessException("This accessor is read-only");
    }
}
~~~

Registering the accessor:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setPropertyAccessors(
        List.of(new AllowlistedMapPropertyAccessor()));

Map<String, Object> settings = Map.of(
        "theme", "dark",
        "locale", "vi",
        "internalToken", "not-exposed");

ExpressionParser parser = new SpelExpressionParser();

String theme = parser.parseExpression("theme")
        .getValue(context, settings, String.class);
~~~

The accessor can only read keys that are in the allowlist. The **internalToken** property is not exposed by this accessor.

In the example, **setPropertyAccessors(...)** replaces the default accessor list. This is a deliberate choice so expressions only use the allowlisted accessor. If you want to preserve reflective access for other objects, include both the custom accessor and the reflective accessor in the list in the appropriate order. Do not add an allowlist accessor and still keep a broad fallback if the goal is to prevent access to properties outside the list.

For business objects, a custom accessor can map SpEL property names to internal data fields, read data from a non-JavaBean structure, or reject unexposed properties.

## MethodResolver: customizing how methods are located

**MethodResolver** is responsible for finding how to invoke a method on a target object. It receives the EvaluationContext, target object, method name, and a list of TypeDescriptor describing the argument types:

~~~java
MethodExecutor resolve(
        EvaluationContext context,
        Object targetObject,
        String name,
        List<TypeDescriptor> argumentTypes) throws AccessException;
~~~

If a matching method is found, the resolver returns a **MethodExecutor**. The executor performs the invocation and returns a TypedValue:

~~~java
TypedValue execute(
        EvaluationContext context,
        Object target,
        Object... arguments) throws AccessException;
~~~

For example, an application wants to allow invoking only the **normalize** method on a TextTools object:

~~~java
public class AllowlistedMethodResolver
        implements MethodResolver {

    private static final Set<String> ALLOWED =
            Set.of("normalize");

    private final MethodResolver reflective =
            new ReflectiveMethodResolver();

    @Override
    public MethodExecutor resolve(
            EvaluationContext context,
            Object targetObject,
            String name,
            List<TypeDescriptor> argumentTypes)
            throws AccessException {

        if (!ALLOWED.contains(name)) {
            return null;
        }

        return reflective.resolve(
                context,
                targetObject,
                name,
                argumentTypes);
    }
}
~~~

Registering the resolver as a list containing only the allowlisted resolver:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setMethodResolvers(
        List.of(new AllowlistedMethodResolver()));
~~~

The custom resolver delegates method lookup to ReflectiveMethodResolver only when the method name is in the allowlist. Because the context list has no separate reflective resolver behind it, methods outside the allowlist cannot be invoked via a default resolver instead.

In a real application, the allowlist should inspect both the target type and the method signature, not just the method name. Different classes may have methods with the same name but different safety levels. You can inspect targetObject.getClass(), the argument count, and the TypeDescriptor of each argument before delegating.

If a method is not supported by any resolver, SpEL cannot perform the invocation and will throw an evaluation error. If a method is found but throws an exception itself, the error occurs during executor execution.

## ConstructorResolver: customizing how constructors are located

**ConstructorResolver** locates constructors for expressions using the **new TypeName(arguments)** syntax. The interface receives the EvaluationContext, type name, and list of argument types:

~~~java
ConstructorExecutor resolve(
        EvaluationContext context,
        String typeName,
        List<TypeDescriptor> argumentTypes) throws AccessException;
~~~

If a matching constructor is found, the resolver returns a **ConstructorExecutor**. The executor creates the object and returns a TypedValue:

~~~java
TypedValue execute(
        EvaluationContext context,
        Object... arguments) throws AccessException;
~~~

For example, allowing instantiation only of a SafeValue type:

~~~java
public class AllowlistedConstructorResolver
        implements ConstructorResolver {

    private static final Set<String> ALLOWED_TYPES =
            Set.of("com.example.SafeValue");

    private final ConstructorResolver reflective =
            new ReflectiveConstructorResolver();

    @Override
    public ConstructorExecutor resolve(
            EvaluationContext context,
            String typeName,
            List<TypeDescriptor> argumentTypes)
            throws AccessException {

        if (!ALLOWED_TYPES.contains(typeName)) {
            return null;
        }

        return reflective.resolve(
                context,
                typeName,
                argumentTypes);
    }
}
~~~

Registering the resolver:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setConstructorResolvers(
        List.of(new AllowlistedConstructorResolver()));
~~~

With this configuration, the resolver delegates to ReflectiveConstructorResolver only when the type name is in the allowlist. If the application needs to support multiple types, register each allowed type and inspect the argument count, types, and side effects of the constructor.

TypeLocator remains responsible for resolving the type name to a Class. ConstructorResolver decides whether there is an allowed and suitable constructor to invoke. These two components collaborate but do not replace each other.

## Resolver order and fallback behavior

A context can contain multiple PropertyAccessors, MethodResolvers, or ConstructorResolvers. SpEL queries the registered components in sequence to find a suitable handler.

For example, if you want a custom accessor to handle Map first, while still using reflective access for JavaBeans:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setPropertyAccessors(List.of(
        new AllowlistedMapPropertyAccessor(),
        new ReflectivePropertyAccessor()));
~~~

The list is configured in the desired priority order. The custom accessor is queried first; the reflective accessor serves as a fallback for targets/properties that the custom accessor does not handle.

Similarly, you can combine a custom resolver with a reflective resolver if you want a fallback for other methods or constructors. However, this changes the permission policy: a custom resolver returning null can allow the next resolver to handle the call. Therefore, if the goal is an allowlist, ensure there is no broader resolver remaining that can handle rejected operations.

Distinguish between two goals:

- **Extending capabilities:** add accessors/resolvers to support new data types while keeping default behavior.
- **Restricting capabilities:** replace the default list with a controlled list and do not leave unintended broad fallbacks.

## Using add... or set...?

The add and replace APIs serve two different purposes:

| API | Effect |
|---|---|
| **addPropertyAccessor(...)** | Adds an accessor to the current list |
| **setPropertyAccessors(...)** | Replaces the entire property accessor list |
| **addMethodResolver(...)** | Adds a method resolver to the current list |
| **setMethodResolvers(...)** | Replaces the entire method resolver list |
| **addConstructorResolver(...)** | Adds a constructor resolver to the current list |
| **setConstructorResolvers(...)** | Replaces the entire constructor resolver list |

If you only need to support an additional data type and still want default behavior, the `add...` methods are usually convenient. If you need exact control over order or access restrictions, build an explicit list using `set...`.

Do not use `set...` and forget to re-add necessary default resolvers. Conversely, do not use `add...` for a security allowlist if the default resolver can still handle operations rejected by the custom resolver.

## Combining the three components in one context

An application may need all three kinds of customization. For example, a context that allows:

- Reading properties from a specialized data structure.
- Calling a selected set of methods.
- Creating a selected set of object types.

Each list can be configured separately:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setPropertyAccessors(
        List.of(new AllowlistedMapPropertyAccessor()));

context.setMethodResolvers(
        List.of(new AllowlistedMethodResolver()));

context.setConstructorResolvers(
        List.of(new AllowlistedConstructorResolver()));
~~~

Each extension point controls one kind of operation. A read-only property accessor does not automatically prevent method invocation; an allowlisted method resolver does not automatically restrict constructors; and a constructor resolver does not decide which properties are read. To restrict the entire expression, you must consider all three along with TypeLocator, BeanResolver, the root object, and supplied variables.

## SimpleEvaluationContext and extension point limitations

**SimpleEvaluationContext** is designed for a subset of SpEL capabilities, typically used in data binding when all privileges of StandardEvaluationContext are not needed. Its builder allows configuring PropertyAccessors and certain method access capabilities within its supported scope.

SimpleEvaluationContext does not provide full mechanisms such as type references, constructor invocations, and bean references. Therefore, it cannot be treated as a StandardEvaluationContext where any arbitrary resolver can be registered.

If a use case needs to customize all three—PropertyAccessor, MethodResolver, and ConstructorResolver—StandardEvaluationContext is the more flexible choice. If you only need to read properties with a restricted set of accessors, SimpleEvaluationContext may fit and helps reduce the operation surface.

## Error handling and diagnostics

Errors related to resolvers can appear at several stages:

- **ParseException:** the SpEL string has invalid syntax; the parser cannot create an Expression.
- **No matching accessor/resolver found:** the expression is valid, but the context has no component supporting the required operation.
- **AccessException:** an accessor or resolver encounters a problem while checking or performing the operation.
- **EvaluationException:** SpEL cannot complete evaluation; causes may include a non-existent property, incompatible method/constructor, failed conversion, or an executor throwing an error.

Record the operation type, property/method/type name, and necessary context for diagnostics. Avoid logging entire objects or arguments if they contain sensitive data.

When a custom resolver rejects an operation, return a not-found result matching the interface contract or throw an AccessException when an actual access error occurs. Do not catch all exceptions and return null, as that can hide programming bugs inside the resolver and cause SpEL to fall through to another resolver unexpectedly.

## Security and limiting the operation surface

Resolvers determine which parts of the application an expression can access. If expressions come from user-editable configuration or an untrusted source, using StandardEvaluationContext with default reflective resolvers can open up more capabilities than the use case requires.

Some principles:

- Expose only necessary properties; use an allowlist PropertyAccessor when needed.
- Restrict methods by target type, name, and argument signature.
- Only allow instantiating object types whose constructors are appropriate and have no unintended side effects.
- Do not expose services, repositories, or objects with resource access permissions if the expression does not need them.
- When restriction is required, replace the default list with a controlled list rather than merely adding an allowlist resolver while keeping a broad fallback.
- Combine resolvers with a small root object, clear variables, and an appropriate TypeLocator.

A custom resolver does not create a complete sandbox by itself. Other components of EvaluationContext can still provide additional access. Safety policy must be designed across the entire context.

## When should you write a custom resolver?

Consider a custom resolver/accessor when:

- Data does not follow JavaBean conventions but needs to be accessed using property syntax.
- You want to map SpEL properties onto a custom data model.
- Only a defined set of methods or constructors is allowed to be invoked.
- A specialized object/factory mechanism needs to be integrated.
- You want to control priority order across multiple access mechanisms.
- Expressions are externally configured and the operation surface must be restricted.

If you only need to read ordinary properties or invoke standard JavaBean methods, the default reflective resolvers are usually sufficient. Do not create custom extension points without a clear requirement regarding behavior or access permissions.

## Conclusion

**PropertyAccessor**, **MethodResolver**, and **ConstructorResolver** are the three extension points for controlling how SpEL reads/writes properties, invokes methods, and creates objects. StandardEvaluationContext lets you add to or replace each type's list via the **add...** and **set...** APIs. Resolvers locate an appropriate executor; the executor performs the operation when the expression is evaluated.

Resolver order determines fallback behavior and can directly affect access permissions. If you want to extend capabilities, keep the necessary default resolvers; if you want to restrict capabilities, replace the list with controlled implementations and do not let a broad fallback inadvertently reopen rejected operations. Combining the three extension points with the root object, TypeLocator, and other EvaluationContext components gives expressions the exact capabilities the application needs.
