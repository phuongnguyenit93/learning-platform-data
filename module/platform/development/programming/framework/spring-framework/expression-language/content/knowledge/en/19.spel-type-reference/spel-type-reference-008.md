# Restricting Referencable Types in Spring Expression Language

Spring Expression Language (SpEL) allows referencing a Java type using the T(...) operator. From the type reference, an expression can access static members, such as constants or static methods:

~~~spel
T(java.lang.Math).PI
T(java.lang.Math).max(10, 20)
~~~

This capability is useful when an expression needs Java APIs, enums, or constants without passing an object as the root. However, in real-world applications, it is not always desirable for expressions to reference every type that the classloader can load.

SpEL resolves type lookup through TypeLocator in EvaluationContext. Thus, an application can configure TypeLocator to permit only a specific set of types. When restricting the expression language, it is important to understand default behavior, how to build an allow-list, and the actual scope of protection provided by restricting type references.

## 1. What is a type reference?

A type reference is the syntax using the T(...) operator to specify a Java type by name:

~~~spel
T(java.lang.String)
T(java.math.BigDecimal)
T(java.time.LocalDate)
~~~

When evaluated, SpEL asks TypeLocator to find the corresponding class and return a Class object. From this Class object, the expression can access permitted static members.

Example:

~~~spel
T(java.lang.Math).PI
T(java.lang.Math).abs(-10)
T(java.lang.Math).max(10, 20)
~~~

The results are the PI constant, 10, and 20, respectively.

A type reference is not a constructor call. If you want to create an instance, SpEL has a separate new syntax. Similarly, T(...) is not a bean reference: it looks up a Java type, whereas the @beanName syntax looks up a bean via BeanResolver.

## 2. Fully qualified type names and default imports

With StandardTypeLocator used by default in StandardEvaluationContext, the java.lang package is pre-imported. Therefore you can write:

~~~spel
T(String)
T(Math)
T(Integer)
~~~

For types outside java.lang, you normally need to use the fully qualified name including the package:

~~~spel
T(java.math.BigDecimal)
T(java.time.LocalDate)
T(java.util.UUID)
~~~

You can register package imports on StandardTypeLocator to use shorter names:

~~~java
StandardTypeLocator typeLocator =
    new StandardTypeLocator();

typeLocator.registerImport("java.math");
typeLocator.registerImport("java.time");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeLocator(typeLocator);
~~~

After registration, expressions can reference:

~~~spel
T(BigDecimal)
T(LocalDate)
~~~

An import is only a way to shorten type names. It does not mean other types have been forbidden. If TypeLocator can still find another fully qualified name via the classloader, an expression can still reference that type.

This is an important point when designing restrictions: adding a few package imports does not create an allow-list.

## 3. TypeLocator is responsible for finding types

EvaluationContext provides TypeLocator for SpEL to resolve type names appearing in T(...). The TypeLocator interface defines the operation of finding a type from the passed name.

In StandardEvaluationContext, the default TypeLocator is usually StandardTypeLocator. It looks up classes through the classloader and supports registered package imports, including the default java.lang.

Processing flow:

~~~text
Expression T(java.math.BigDecimal)
             |
             v
SpEL recognizes type reference
             |
             v
EvaluationContext.getTypeLocator()
             |
             v
TypeLocator.findType(typeName)
             |
       +-----+-----+
       |           |
     Found      Not found
       |           |
       v           v
    Class<?>    Evaluation error
       |
       v
Access static member if requested by expression
~~~

If the type name is wrong, the class is not on the classpath, or the classloader cannot load that type, evaluation may raise an error. If TypeLocator actively rejects the type name, the expression cannot proceed either.

## 4. Default behavior is not an allow-list

StandardTypeLocator helps find types by name and classloader. It is not designed as a mechanism that allows only a safe list of classes.

For example, if an application uses StandardEvaluationContext with the default TypeLocator, expressions can reference various Java types as long as they can be found and subsequent operations are permitted.

Merely adding an import:

~~~java
typeLocator.registerImport("java.math");
~~~

does not restrict expressions to types in java.math. The fully qualified name of another type can still be resolved if the classloader can load it.

Therefore:

- **Import:** helps write short names for a package.
- **ClassLoader:** determines which classes can be loaded in the environment.
- **TypeLocator:** determines how a type name in an expression is resolved.
- **Allow-list:** is a policy actively enforced by the application to permit only selected type names.

If the goal is to restrict referencable types, implement an allow-list policy in TypeLocator or use a context that does not support type references.

## 5. Restricting types with an allow-list TypeLocator

You can create a custom TypeLocator to accept only specific type names. Other names will be rejected before SpEL obtains the Class object.

The following example only allows referencing Math and BigDecimal:

~~~java
import java.math.BigDecimal;
import java.util.Set;

import org.springframework.expression.EvaluationException;
import org.springframework.expression.TypeLocator;
import org.springframework.expression.spel.support.StandardTypeLocator;

public class AllowListTypeLocator implements TypeLocator {

    private final TypeLocator delegate =
        new StandardTypeLocator();

    private final Set<String> allowedTypes = Set.of(
        "java.lang.Math",
        "java.math.BigDecimal"
    );

    @Override
    public Class<?> findType(String typeName)
            throws EvaluationException {

        if (!allowedTypes.contains(typeName)) {
            throw new EvaluationException(
                "Type is not allowed: " + typeName
            );
        }

        return delegate.findType(typeName);
    }
}
~~~

Registering the TypeLocator:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeLocator(new AllowListTypeLocator());

ExpressionParser parser = new SpelExpressionParser();

Integer result = parser.parseExpression(
    "T(java.lang.Math).max(10, 20)"
).getValue(context, Integer.class);
~~~

The result is 20.

If an expression requests a type not in the allow-list, such as:

~~~spel
T(java.lang.System)
~~~

the custom TypeLocator rejects the type name and throws an EvaluationException. SpEL cannot continue evaluating that type reference.

The example above uses exact fully qualified names so the policy is easy to verify. If you want to support aliases or short names, explicitly define the permitted names and normalize them before checking; do not accidentally broaden the policy by accepting any name the delegate can find.

## 6. Why check before calling the delegate?

An allow-list TypeLocator typically wraps another TypeLocator. The delegate is responsible for finding the class after the policy has accepted the name.

The correct order is:

1. Receive the type name from the expression.
2. Check whether the name is in the allowed list.
3. If not, reject immediately.
4. If yes, call the delegate to find the Class.
5. Return the Class to SpEL.

If you call the delegate first and check afterward, the application has already allowed the class loading and type resolution mechanism to run before the policy is applied. Checking first keeps the policy clear and easier to control.

In addition, the allow-list should be managed centrally. When adding a new type, review what static methods, fields, or capabilities that type provides for expressions to access.

## 7. Use SimpleEvaluationContext when type references are not needed

If the application only needs a subset of SpEL features for data binding, consider SimpleEvaluationContext.

SimpleEvaluationContext is designed with a narrower syntax scope than StandardEvaluationContext. It does not support features such as:

- Java type references via T(...).
- Constructor invocations via new.
- Bean references via @beanName.

Example creating a context for data binding:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding()
        .build();
~~~

This context is suitable when expressions only need to read properties according to configured data binding mechanisms. If the application needs type references, constructors, or bean references, choose a context with the corresponding capabilities and restrict those capabilities under an explicit policy.

SimpleEvaluationContext is an option for reducing the feature surface, but you still need to configure property accessors and other capabilities appropriately for the application's data.

## 8. Restricting type references does not mean a complete sandbox

This is the most important limitation to understand when evaluating untrusted expressions.

An allow-list TypeLocator only controls which types are resolved via the T(...) syntax. It does not automatically control every object an expression can access.

For example, if the root object is a service with many public methods, an expression can still call those methods if MethodResolver and the context allow it. Similarly, a registered variable or bean can provide an access path to other objects.

Therefore, restricting T(...) alone is not enough to create a safe evaluation environment. You must simultaneously consider:

- **Root object:** provide only the objects and data the expression actually needs.
- **Variables:** do not register objects with broad access permissions unless necessary.
- **PropertyAccessor:** restrict which properties an expression is allowed to read or write.
- **MethodResolver:** restrict callable methods and methods with side effects.
- **BeanResolver:** do not register if expressions do not need bean references; if needed, expose only an appropriate scope of beans.
- **ConstructorResolver:** control or omit object creation capabilities if not needed.
- **TypeLocator:** apply an allow-list for type references.
- **Input values:** validate data before evaluation.

An expression may avoid using T(...) yet still invoke dangerous methods on a passed-in object. Conversely, allowing a type does not mean every operation on that type is automatically fully controlled by TypeLocator.

TypeLocator is one control layer in the evaluation architecture, not the sole security boundary.

## 9. Also control which static members are used

When a type is allowed, SpEL can access static members permitted by the access mechanism, for example:

~~~spel
T(java.lang.Math).PI
T(java.lang.Math).abs(-10)
~~~

Therefore, when adding a type to an allow-list, review not only the class name but also the static API the class provides.

If the application only needs a single constant or specific calculation, consider providing that value as a variable or a wrapper object with a small interface, rather than opening the entire type to expressions.

For example, instead of letting an expression access a broad API itself, the application can register a variable containing a precomputed value:

~~~java
context.setVariable("pi", Math.PI);
~~~

The expression only needs to reference:

~~~spel
#pi
~~~

This approach clarifies what data is supplied and avoids having to permit type references just to obtain a fixed value.

## 10. ClassLoader and type resolution capability

StandardTypeLocator finds classes through a classloader. In applications with multiple modules, plugins, or containers, the classloader can affect which types are found.

A type might exist in a module or dependency yet not be visible from the classloader used by TypeLocator. In that case, the expression can still fail even though the type name is correct.

StandardTypeLocator allows configuring an appropriate classloader:

~~~java
StandardTypeLocator typeLocator =
    new StandardTypeLocator(
        Thread.currentThread().getContextClassLoader()
    );
~~~

Then you can register imports or use fully qualified names as usual.

If using a custom TypeLocator wrapping StandardTypeLocator, configure the delegate with the classloader the application expects. The allow-list policy and class-loading capability are two separate conditions: an allowed name must still be a loadable type.

## 11. Distinguishing type reference errors from post-lookup operation errors

There are two error stages to separate:

**Type resolution errors:**

- The type name is wrong or incomplete.
- The type is not on the classpath or not visible via the classloader.
- TypeLocator does not allow the type name.
- The context does not support type references.

In this case, SpEL has not received a suitable Class to continue.

**Errors after finding the type:**

- The requested static member does not exist.
- The static method has an incompatible argument count or argument types.
- The member is not accessible.
- The method is invoked, but the method body itself throws an exception.

In the second group, TypeLocator may have succeeded. Check the member, overloads, access permissions, and underlying exception instead of modifying the allow-list by guesswork.

## 12. Complete example: allowing only selected type references

Suppose an application wants to let expressions use Math and BigDecimal, while forbidding references to other types.

Create the context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeLocator(new AllowListTypeLocator());

ExpressionParser parser = new SpelExpressionParser();

Expression allowedExpression =
    parser.parseExpression(
        "T(java.lang.Math).max(12, 30)"
    );

Integer result =
    allowedExpression.getValue(context, Integer.class);
~~~

Result:

~~~text
30
~~~

Another expression:

~~~spel
T(java.time.LocalDate).now()
~~~

is rejected because java.time.LocalDate is not in the allow-list, even though that class may be on the classpath.

Policy outcomes:

| Type reference | Policy | Behavior |
|---|---|---|
| T(java.lang.Math) | Allowed | Delegate finds type and SpEL proceeds |
| T(java.math.BigDecimal) | Allowed | Delegate finds type and SpEL proceeds |
| T(java.time.LocalDate) | Rejected | TypeLocator throws EvaluationException |
| T(java.lang.System) | Rejected | TypeLocator throws EvaluationException |

The allow-list decides which types can be referenced. The delegate still checks class loadability, and subsequent member access steps must still be valid.

## 13. Common misconceptions

**Misconception 1: Importing only one package forbids other packages.**  
Imports only help use short names. They are not an allow-list and do not prevent fully qualified names of other types from being resolved.

**Misconception 2: StandardTypeLocator only allows java.lang by default.**  
java.lang is imported by default, but StandardTypeLocator can still find other types by fully qualified name if the classloader can access them.

**Misconception 3: T(...) is a bean reference.**  
T(...) references a Java type via TypeLocator; @beanName looks up a bean via BeanResolver.

**Misconception 4: T(...) creates a new instance.**  
T(...) returns a Class type reference. Creating an instance uses the separate new syntax.

**Misconception 5: An allow-list TypeLocator is a complete sandbox.**  
It only controls type references. The root object, variables, property accessors, method resolvers, and bean resolvers can still provide other access paths.

**Misconception 6: If a type is allow-listed, every method on that type is guaranteed to be callable.**  
TypeLocator only finds the type. Method resolution, access permissions, and member execution are separate steps.

## 14. Key takeaways

- Type references use the T(...) syntax to look up a Java type.
- TypeLocator in EvaluationContext is responsible for resolving type names.
- StandardEvaluationContext typically uses StandardTypeLocator, with java.lang imported by default.
- Type names outside java.lang can use fully qualified names or registered package imports.
- Imports are not an allow-list; restricting types requires enforcing an explicit policy in TypeLocator.
- A custom TypeLocator can validate the type name before delegating to find the Class.
- SimpleEvaluationContext excludes type references, constructor invocations, and bean references from its supported feature set.
- An allow-list TypeLocator does not control every object, property, or method an expression can access.
- Combine restrictions across root object, variables, accessors, resolvers, and bean exposure when evaluating untrusted expressions.
- Type lookup errors differ from static member access errors or exceptions inside invoked methods.

When designing type references for SpEL, decide which types are genuinely required, enforce an allow-list in TypeLocator, verify the classloader, and review all other access paths in EvaluationContext. That keeps expressions capable enough for what they need while maintaining a clear type reference boundary.
