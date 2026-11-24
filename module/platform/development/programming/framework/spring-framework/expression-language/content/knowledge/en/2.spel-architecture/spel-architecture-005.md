# PropertyAccessor, MethodResolver, and ConstructorResolver in SpEL

In Spring Expression Language (SpEL), the three strategy interfaces **PropertyAccessor**, **MethodResolver**, and **ConstructorResolver** determine how an expression reads/writes properties, invokes methods, and instantiates objects. They are supplied via **EvaluationContext**, so the same expression can operate under different access rules depending on the configured context.

## 1. Position in the expression evaluation process

SpEL parses the expression string into an abstract syntax tree (AST), then evaluates the tree nodes within an EvaluationContext. When encountering an operation, the corresponding node asks the strategies in the context how to perform it:

| SpEL syntax | Task | Strategy |
|---|---|---|
| `customer.address.city` | Read properties across each object | PropertyAccessor |
| `customer.rename('An')` | Locate and invoke a method | MethodResolver |
| `new com.example.Customer('An')` | Locate a matching constructor and create an object | ConstructorResolver |

These three interfaces separate **choosing how to access** from **executing the operation**. MethodResolver returns a MethodExecutor; ConstructorResolver returns a ConstructorExecutor. PropertyAccessor directly provides the check, read, and write operations.

Other components still have their own roles. For example, TypeLocator locates the class named in an expression; TypeConverter converts value types; index operators such as `items[0]` are handled by SpEL's index node. Do not treat these three strategies as the handlers for every syntax construct in the language.

## 2. EvaluationContext determines which strategies are used

EvaluationContext holds the root object and the services needed when evaluating an expression, including lists of PropertyAccessors, MethodResolvers, and ConstructorResolvers. Strategies are tried in list order. The first matching strategy handles the operation; if no strategy satisfies it, SpEL reports an evaluation error.

Two common contexts:

- **StandardEvaluationContext** provides reflection-based access capabilities. By default, it includes ReflectivePropertyAccessor, ReflectiveMethodResolver, and ReflectiveConstructorResolver, along with services such as TypeConverter and TypeLocator.
- **SimpleEvaluationContext** is meant for cases requiring restricted features. This context does not support type references, constructor invocation, bean references, or assignment. Instance method invocation must be explicitly enabled through the builder via `withInstanceMethods()`; property access is also selected through the builder or application-supplied accessors.

When replacing a strategy list, retain the default strategy if reflection fallback is still needed. An overly broad custom accessor or resolver placed first may intercept operations intended for another strategy.

## 3. PropertyAccessor: reading and writing properties

PropertyAccessor describes how SpEL accesses a named property on a target object. The interface resides in the `org.springframework.expression` package and has these main methods:

| Method | Meaning |
|---|---|
| `getSpecificTargetClasses()` | Declares the target classes the accessor specializes in; returns `null` if not restricted by class |
| `canRead(context, target, name)` | Indicates whether the property can be read |
| `read(context, target, name)` | Reads the value and returns a TypedValue |
| `canWrite(context, target, name)` | Indicates whether the property can be written |
| `write(context, target, name, newValue)` | Writes the new value |

SpEL uses `canRead` to find an accessor that can read the property, then calls `read` on the selected accessor. For assignment, SpEL follows a similar process with `canWrite` and `write`. These methods may throw AccessException when the operation cannot be performed.

**TypedValue** carries the read value together with type information (TypeDescriptor). When static types or type metadata matter for data conversion, a custom accessor should return a TypedValue with an appropriate TypeDescriptor rather than relying solely on the runtime type.

### Default accessors and when customization is needed

- **ReflectivePropertyAccessor** accesses properties via JavaBean getters/setters and matching fields through reflection. This is the common default accessor in StandardEvaluationContext.
- **DataBindingPropertyAccessor** serves data binding with a more restricted access scope than the general reflective accessor.
- A custom PropertyAccessor is useful when data has a specialized structure, such as virtual properties, Map-shaped configurations, or proxy objects where JavaBean getters/setters do not describe properties properly.

### Example: accessor for Map

The following example treats property names as keys in a Map. Imports are omitted to focus on the interface contract.

    public final class MapPropertyAccessor implements PropertyAccessor {

        @Override
        public Class<?>[] getSpecificTargetClasses() {
            return new Class<?>[] { Map.class };
        }

        @Override
        public boolean canRead(
                EvaluationContext context, Object target, String name) {
            return target instanceof Map
                    && ((Map<?, ?>) target).containsKey(name);
        }

        @Override
        public TypedValue read(
                EvaluationContext context, Object target, String name)
                throws AccessException {
            Map<?, ?> map = (Map<?, ?>) target;
            if (!map.containsKey(name)) {
                throw new AccessException("No map entry named " + name);
            }
            return new TypedValue(map.get(name));
        }

        @Override
        public boolean canWrite(
                EvaluationContext context, Object target, String name) {
            return target instanceof Map;
        }

        @Override
        @SuppressWarnings("unchecked")
        public void write(
                EvaluationContext context, Object target,
                String name, Object newValue) throws AccessException {
            if (!(target instanceof Map)) {
                throw new AccessException("Target is not a Map");
            }
            ((Map<Object, Object>) target).put(name, newValue);
        }
    }

If this accessor is registered for a root Map, the expression `customer.name` can be interpreted as reading key `customer` from the outer Map, then reading key `name` from the nested Map. This is a convention defined by the accessor; it differs from the index syntax `customer['name']`.

A good accessor should restrict target classes with `getSpecificTargetClasses()` whenever possible. `canRead` and `canWrite` should only check accessibility without mutating data or calling services with side effects. If `canRead` returns true yet `read` cannot complete, throw an AccessException with enough information for diagnosis.

## 4. MethodResolver: selecting the method to call

MethodResolver is responsible for finding a method matching the method name, target object, and argument types. Main contract:

    MethodExecutor resolve(
        EvaluationContext context,
        Object targetObject,
        String name,
        List<TypeDescriptor> argumentTypes
    ) throws AccessException;

The resolver returns a MethodExecutor if a way to invoke the call is found, or `null` if it cannot handle that call. MethodExecutor executes the selected method:

    TypedValue execute(
        EvaluationContext context,
        Object target,
        Object... arguments
    ) throws AccessException;

**ReflectiveMethodResolver** is the default resolver in StandardEvaluationContext. It locates matching methods via reflection, considering argument types and type conversion capabilities. Resolution is especially important when a class has multiple overloads, varargs parameters, or when arguments need to be converted before invocation.

For example, the expression:

    customer.rename('An')

asks the resolver to find a `rename` method on the customer object taking a single string argument. The resolver selects a MethodExecutor; the executor then invokes the method and returns the result as a TypedValue. If an expression calls a static method via a type reference, the target of the call is the corresponding Class object; finding the class remains the responsibility of TypeLocator.

You should write a custom MethodResolver when you want to expose a dedicated set of operations, delegate calls to another service, or allow only an allowlist of methods. A custom resolver must explicitly specify accepted method names, targets, and argument types; avoid allowing arbitrary invocation of every public method on a sensitive object.

## 5. ConstructorResolver: selecting a constructor to instantiate an object

ConstructorResolver handles object creation expressions using the `new` keyword. Main contract:

    ConstructorExecutor resolve(
        EvaluationContext context,
        String typeName,
        List<TypeDescriptor> argumentTypes
    ) throws AccessException;

The resolver returns a matching ConstructorExecutor or `null` if it cannot handle that constructor. The executor performs the object creation and returns a TypedValue:

    TypedValue execute(
        EvaluationContext context,
        Object... arguments
    ) throws AccessException;

**ReflectiveConstructorResolver** is the default resolver in StandardEvaluationContext. It locates a matching constructor via reflection and coordinates with the type conversion mechanism when needed. TypeLocator is responsible for finding the class from the class name in the expression; ConstructorResolver is responsible for selecting the constructor of the located class. These two steps are separate responsibilities.

Example:

    new com.example.Customer('An')

SpEL locates the Customer class, then finds a constructor accepting matching arguments and creates an instance. If no matching constructor exists, or the class is not found, the expression fails with the corresponding evaluation error.

ConstructorResolver is useful when the application needs a custom instantiation rule, such as allowing only a predefined set of types or delegating instantiation to a factory. A static factory call such as `T(com.example.CustomerFactory).create('An')` is a method call and goes through method resolution, not constructor resolution.

## 6. Registering and ordering strategies

Strategies can be configured on StandardEvaluationContext. The following example places MapPropertyAccessor before the reflective accessor so Maps are handled by the custom convention while preserving JavaBean access for other targets:

    StandardEvaluationContext context =
            new StandardEvaluationContext(root);

    context.setPropertyAccessors(Arrays.asList(
            new MapPropertyAccessor(),
            new ReflectivePropertyAccessor()
    ));

    ExpressionParser parser = new SpelExpressionParser();
    Object result = parser.parseExpression("customer.name")
            .getValue(context);

The lists of method resolvers and constructor resolvers are configured similarly using `setMethodResolvers(...)` and `setConstructorResolvers(...)`. When replacing a list, put the custom resolver in the desired priority position and re-add ReflectiveMethodResolver or ReflectiveConstructorResolver if you want to keep the default fallback. Do not mechanically add a second reflection resolver if the default resolver already meets your needs.

If only property access is needed in a data binding flow, you can use SimpleEvaluationContext with an appropriate accessor. When enabling instance methods with `withInstanceMethods()`, clearly determine which methods can be invoked through the objects supplied to the context.

## 7. Choosing strategies and restricting access permissions

| Need | Implementation approach |
|---|---|
| Reading/writing standard JavaBeans | Use the default ReflectivePropertyAccessor |
| Restricting accessible properties | Use DataBindingPropertyAccessor or a custom PropertyAccessor |
| Accessing Map-like data or virtual properties | Write a custom PropertyAccessor restricted by target class |
| Calling standard methods and handling overloads | Use ReflectiveMethodResolver |
| Allowing only a specific group of methods | Write an allowlist-based custom MethodResolver |
| Instantiating via constructor | Use ReflectiveConstructorResolver if the context allows it |
| Allowing instantiation of only specific types | Write a custom ConstructorResolver or restrict the context |

If expressions are entered by users, treat EvaluationContext as the access boundary. StandardEvaluationContext with reflective accessors/resolvers can open up extensive capabilities for reading properties, invoking methods, and instantiating objects. Prefer SimpleEvaluationContext when a restricted feature set suffices; only register accessors or resolvers that are genuinely required. Do not enable method invocation or constructor invocation purely for convenience if expressions do not need those capabilities.

When building custom strategies, follow three principles:

1. **Limit scope:** accept only the target classes, properties, methods, or constructors that the application intends to support.
2. **Separate checks from execution:** accessibility checks and resolution steps must not mutate system state.
3. **Keep type information and errors clear:** return an appropriate TypedValue, use AccessException for strategy-layer errors, and provide messages specific enough to identify the failed operation.

## 8. Summary

PropertyAccessor determines how properties are read/written; MethodResolver selects how methods are invoked; ConstructorResolver selects how instances are created. All three are supplied via EvaluationContext and can be replaced or extended to fit the application's data model. When configuring them, strategy order, type conversion capabilities, and access permission scope directly determine both the behavior and the safety of SpEL expressions.
