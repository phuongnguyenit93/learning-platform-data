# Executable Shared by Method and Constructor in Java Reflection

In Java Reflection, **Method** represents a method, while **Constructor<T>** represents a constructor. Both inherit from the abstract class **java.lang.reflect.Executable**, introduced in Java 8, because they share a great deal of common information: parameter lists, generic types, annotations, declared exceptions, modifiers, type variables, and varargs/synthetic flags.

Executable is most useful when writing tools that process metadata for both methods and constructors, such as dependency injection, validation, binding, serialization, API documentation, or signature analysis frameworks. Instead of writing two nearly identical loops for Method and Constructor, you can write a single function that accepts Executable and reads those shared properties.

**Core limitation:** Executable is a base class used to **describe and analyze** an executable member. It does not have a common invoke/newInstance method: to actually invoke it, you must distinguish between Method.invoke(...) and Constructor.newInstance(...).

## 1. Type Relationships and Scope of Responsibility

Simple class hierarchy:

~~~text
java.lang.Object
    └── java.lang.reflect.AccessibleObject
          └── java.lang.reflect.Executable
                ├── java.lang.reflect.Method
                └── java.lang.reflect.Constructor<T>
~~~

Executable also implements the **Member**, **AnnotatedElement**, and **GenericDeclaration** interfaces and inherits the reflective access functionality of **AccessibleObject**. On Java 17, it is an abstract sealed class that only permits Method and Constructor to directly inherit from it.

| Concept | Role |
| --- | --- |
| **Method** | Represents a method declared by a class/interface; has a name, return type, receiver, and invoke method |
| **Constructor<T>** | Represents a constructor of class T; calls newInstance to create an instance of the declaring class |
| **Executable** | Provides a shared metadata API for Method and Constructor |
| **Parameter** | Represents a parameter in the runtime signature of an Executable |
| **AccessibleObject** | Provides APIs such as setAccessible/trySetAccessible to request adjusting access checks |

Polymorphism example:

~~~java
import java.lang.reflect.Executable;
import java.lang.reflect.Method;
import java.lang.reflect.Constructor;

Method method = String.class.getMethod("substring", int.class);
Constructor<StringBuilder> constructor = StringBuilder.class.getConstructor();
Executable e1 = method;
Executable e2 = constructor;

System.out.println(e1.getParameterCount()); // 1
System.out.println(e2.getParameterCount()); // 0
~~~

This snippet can be placed inside a method declared with throws ReflectiveOperationException. Both objects can call **getParameterCount()**, because that method resides on Executable. However, only **method** has **invoke(receiver, args...)**, and only **constructor** has **newInstance(args...)**.

Do not try to cast Executable to Method without checking the type first. You can branch using:

~~~java
if (executable instanceof Method m) {
    // You can use Method.getReturnType(), Method.invoke(...)...
} else if (executable instanceof Constructor<?> c) {
    // You can use Constructor.newInstance(...)...
}
~~~

This is a fragment: the executable variable must already exist in context.

## 2. Shared Metadata APIs

The groups below are the core of the Executable class.

| API | Return Type | Purpose |
| --- | --- | --- |
| **getDeclaringClass()** | Class<?> | The class/interface that declares the member |
| **getName()** | String | Method name or constructor name according to Reflection convention |
| **getModifiers()** | int | Modifiers such as public/private/protected; decode using Modifier |
| **getParameterCount()** | int | Total runtime parameters, including certain implicit/synthetic parameters |
| **getParameterTypes()** | Class<?>[] | Parameter types after erasure, in order |
| **getGenericParameterTypes()** | Type[] | Declared generic type information when metadata is present |
| **getParameters()** | Parameter[] | Parameter object for each runtime parameter |
| **getParameterAnnotations()** | Annotation[][] | Annotations on the declaration of each parameter |
| **getAnnotatedParameterTypes()** | AnnotatedType[] | Annotations placed at the parameter type-use site (TYPE_USE) |
| **getExceptionTypes()** | Class<?>[] | Exception types in the throws clause as runtime Class objects |
| **getGenericExceptionTypes()** | Type[] | Exception types in the throws clause with generic information |
| **getAnnotatedExceptionTypes()** | AnnotatedType[] | TYPE_USE annotations on exception types |
| **getTypeParameters()** | TypeVariable<?>[] | Type variables declared by the method/constructor itself |
| **isVarArgs()** | boolean | Whether the last parameter is declared as varargs |
| **isSynthetic()** | boolean | Whether the member is compiler-generated as synthetic |
| **toGenericString()** | String | Signature representation with generics and modifiers |
| **getAnnotatedReturnType()** | AnnotatedType | Return type information with annotations per each subtype's contract |
| **getAnnotatedReceiverType()** | AnnotatedType or null | Receiver type declared where applicable; not every executable has a receiver |

Some methods such as **getParameterCount()**, **getParameters()**, and **getGenericParameterTypes()** have shared implementations in Executable; others are abstract and implemented by Method and Constructor. From the API consumer's perspective, they can still be called through a variable of type Executable.

### A Signature Is Not an Execution Call

Executable provides **getParameterCount()**, but does not itself provide **invoke()**. To execute:

- **Method.invoke(Object receiver, Object... args)** invokes the selected method; for a static method, receiver may be null.
- **Constructor.newInstance(Object... initargs)** creates an object of the declaring class.
- Both can produce an **InvocationTargetException** if the method or constructor body throws an exception.
- **IllegalAccessException** relates to invocation permissions; **IllegalArgumentException** usually relates to mismatched receiver or arguments. Details of access checks belong to Method/Constructor and the module environment.

When writing a metadata scanner, it is best to keep the variable typed as **Executable** during the shared analysis phase, and only branch to subtypes when invocation or subtype-specific APIs are needed.

## 3. Parameter: Object Representing Each Parameter

The **getParameters()** API returns a **Parameter[]** array, where each element has:

- **getName()**: parameter name read from the class file if available, or a synthesized name such as arg0, arg1.
- **isNamePresent()**: whether the class file contains the parameter name in appropriate metadata.
- **getType()**: Class<?> after type erasure.
- **getParameterizedType()**: Type representing the generic declaration.
- **getAnnotations()**, **getAnnotation(...)**: annotations attached directly to the parameter declaration.
- **getAnnotatedType()**: AnnotatedType for annotations at the type-use position.
- **isVarArgs()**: whether the parameter represents a variable-length argument list.
- **isImplicit()** and **isSynthetic()**: parameter that is implicit in source or generated by the compiler.
- **getDeclaringExecutable()**: returns back to the Method/Constructor declaring the parameter.

**Parameter names are not always preserved in the .class file.** With javac, compile with **-parameters** when tools rely on names like name, amount, or requestId. Without that option, names may become arg0, arg1; do not treat these names as stable source names.

~~~bash
javac --release 17 -parameters -encoding UTF-8 ExecutableDemo.java
java ExecutableDemo
~~~

Although **-g** adds some debug information, it does not replace the purpose of **-parameters** so that Reflection parameter-name APIs can work according to their contract. Parameter names of certain special constructs such as records may be stored by the compiler under their own rules; do not infer from that that every method has names.

### Erasure: Class<?> vs. Type

Suppose a method has the signature:

~~~java
public <E extends Number> void submit(List<E> values, E limit) {}
~~~

Typical information:

| Parameter | getParameterTypes() | getGenericParameterTypes() |
| --- | --- | --- |
| values | List.class | ParameterizedType representing List<E> |
| limit | Number.class | TypeVariable E |

The method lookup must use the erased parameter types:

~~~java
clazz.getDeclaredMethod("submit", java.util.List.class, Number.class);
~~~

clazz is a variable of type Class<?> in the example. You cannot pass a ParameterizedType representing List<E> into **getDeclaredMethod**, because that method accepts **Class<?>...**.

**getTypeParameters()** of the submit method has one TypeVariable named E; this is different from **getGenericParameterTypes()** returning E at the parameter position. For a Constructor of a generic class, getTypeParameters() only describes type variables declared **specifically on the constructor**, and does not automatically include all type variables of the class.

## 4. Complete Java 17+ Example: Analyzing Method and Constructor via Executable

The following program demonstrates an **inspect(Executable)** function that handles both a constructor and a method simultaneously, printing parameter names/types, generics, throws, varargs, and annotations, and then invoking each member via its specific API.

Save the entire code to a file named **ExecutableDemo.java**:

~~~java
import java.io.IOException;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.Executable;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.List;

public class ExecutableDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @interface Label { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface Marked {}

    public static class Service {
        private final List<String> names;

        public Service(@Label("ctor") @Marked List<String> names) throws IOException {
            this.names = names;
        }

        public <E extends Number> @Marked List<E> process(
                @Label("key") String key, @Marked List<E> values, int... limits)
                throws IOException {
            return values;
        }

        public int size() { return names.size(); }
    }

    private static void inspect(Executable executable) {
        System.out.println("kind=" + (executable instanceof Method ? "method" : "constructor"));
        System.out.println("owner=" + executable.getDeclaringClass().getSimpleName());
        System.out.println("count=" + executable.getParameterCount());
        System.out.println("varargs=" + executable.isVarArgs());
        Parameter[] parameters = executable.getParameters();
        for (int i = 0; i < parameters.length; i++) {
            Parameter parameter = parameters[i];
            System.out.println("p" + i + "=" + parameter.getName()
                    + ":" + parameter.getType().getSimpleName()
                    + ",namePresent=" + parameter.isNamePresent()
                    + ",generic=" + parameter.getParameterizedType().getTypeName());
        }
        System.out.println("throws=" + executable.getExceptionTypes()[0].getSimpleName());
        System.out.println("typeVariables=" + executable.getTypeParameters().length);
    }

    public static void main(String[] args) throws Exception {
        Constructor<Service> constructor = Service.class.getConstructor(List.class);
        Method method = Service.class.getMethod("process", String.class, List.class, int[].class);

        inspect(constructor);
        inspect(method);

        System.out.println("constructor label="
                + constructor.getParameters()[0].getAnnotation(Label.class).value());
        System.out.println("method p1 type annotation="
                + method.getAnnotatedParameterTypes()[1].isAnnotationPresent(Marked.class));
        System.out.println("method return type annotation="
                + method.getAnnotatedReturnType().isAnnotationPresent(Marked.class));
        System.out.println("method type variable=" + method.getTypeParameters()[0].getName());
        System.out.println("return=" + method.getReturnType().getSimpleName());

        Service service = constructor.newInstance(List.of("A", "B"));
        Object result = method.invoke(service, "ok", List.of(3, 4), new int[] {1, 2});
        System.out.println("invoke=" + result);
        System.out.println("service size=" + service.size());
    }
}
~~~

Compile/run (JDK 17 or higher):

~~~bash
javac --release 17 -parameters -encoding UTF-8 ExecutableDemo.java
java ExecutableDemo
~~~

Stdout verified on JDK 21 after compiling with **--release 17 -parameters**:

~~~text
kind=constructor
owner=Service
count=1
varargs=false
p0=names:List,namePresent=true,generic=java.util.List<java.lang.String>
throws=IOException
typeVariables=0
kind=method
owner=Service
count=3
varargs=true
p0=key:String,namePresent=true,generic=java.lang.String
p1=values:List,namePresent=true,generic=java.util.List<E>
p2=limits:int[],namePresent=true,generic=int[]
throws=IOException
typeVariables=1
constructor label=ctor
method p1 type annotation=true
method return type annotation=true
method type variable=E
return=List
invoke=[3, 4]
service size=2
~~~

### Result Analysis

1. **The same inspect function** accepts both Constructor<Service> and Method through **Executable**. The program only needs to distinguish method/constructor to print kind; all remaining APIs in inspect are on the shared base.
2. The constructor declares one List<String> parameter, so **count=1**; the erased type is List while generic preserves **java.util.List<java.lang.String>**. There is no type variable declared on it, so **typeVariables=0**.
3. The process method has three parameters: String, List<E>, and int...; erasure turns List<E> into List. Varargs **int...** has runtime parameter type **int[]**, so **varargs=true** while getParameterTypes() of the last parameter is an array.
4. Type variable E extends Number is declared on the method itself, so **typeVariables=1** and its name is **E**.
5. **@Label** is a PARAMETER-targeted annotation, read via Parameter.getAnnotation(Label.class). **@Marked** is a TYPE_USE annotation, read via the AnnotatedType of the parameter or return type. The two annotation groups come from different metadata sources.
6. getExceptionTypes() sees **IOException** because both the constructor and method declare throws IOException. It describes the declared signature; it does not assert that every call will throw IOException.
7. Instantiation uses **Constructor.newInstance**; method invocation uses **Method.invoke**. The return value from Method.invoke is Object and is printed as a List containing 3, 4.

### Trying Without -parameters

Recompile in a separate directory or delete old class files and run:

~~~bash
javac --release 17 -encoding UTF-8 ExecutableDemo.java
java ExecutableDemo
~~~

When parameter metadata is not retained by -parameters, the names in the output typically change to **arg0**, **arg1**, **arg2**, and **isNamePresent()** becomes false, for example:

~~~text
p0=arg0:List,namePresent=false,generic=java.util.List<java.lang.String>
~~~

Generic information such as List<String> and type variable E **does not depend on -parameters the way variable names do**: it comes from the generic signature information in the class file. Clearly distinguish these metadata types when diagnosing issues.

## 5. Declaration Annotations and Type-Use Annotations

An annotation attached **directly to a parameter declaration** differs from an annotation attached to the **type** used at the parameter site.

Short code example (not a standalone program):

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface Input {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Checked {}

void save(@Input @Checked List<String> values) {}
~~~

In real code, you need to import java.lang.annotation.* and java.util.List.

- **getParameterAnnotations()** returns a two-dimensional array: each position corresponds to the set of declaration annotations of one parameter.
- **getParameters()[i].getAnnotations()** also yields the declaration annotations on that Parameter.
- **getAnnotatedParameterTypes()[i].getAnnotations()** yields the TYPE_USE annotations at the corresponding parameter type site.
- **getAnnotatedReturnType()** is used for type-use annotations on the return type; for Method, it can be read alongside **getReturnType()** or **getGenericReturnType()** depending on the goal.
- **getAnnotatedExceptionTypes()** describes type-use annotations of exceptions in throws.
- **getAnnotatedReceiverType()** describes the receiver type where valid (for example, an explicitly declared receiver parameter); it may return null if there is no applicable receiver.

Do not force all annotations into the same category. A validation framework that wants to inspect annotations on parameters should read both **declaration** and **type-use** annotations according to their @Target meta-annotation.

**Note:** annotation arrays are not guaranteed to reflect all source information if the annotation lacks RetentionPolicy.RUNTIME. SOURCE/CLASS annotations may not be visible through runtime reflection APIs the way RUNTIME annotations are.

## 6. Implicit, Synthetic Parameters and Differences Between Arrays

An executable does not only contain parameters explicitly visible in source code. The compiler may insert **implicit** or **synthetic** parameters. Two common cases:

- The constructor of a **non-static inner class** usually has an additional parameter referencing the enclosing instance in the first position.
- Constructors related to certain compiler constructs such as enum may have extra parameters added outside the list written by the programmer.

Example:

~~~java
class Outer {
    class Inner {
        Inner(int number) {}
    }
}
~~~

For a non-static inner type, the constructor in bytecode needs to receive an instance of Outer. When looking up the constructor via Reflection, in the typical javac case you must use:

~~~java
Outer outer = new Outer();
Constructor<Outer.Inner> c =
        Outer.Inner.class.getDeclaredConstructor(Outer.class, int.class);
Outer.Inner instance = c.newInstance(outer, 10);
~~~

This is a fragment that requires importing java.lang.reflect.Constructor and placing it in a method that handles checked exceptions. For a **static nested class**, there is no extra outer instance under this mechanism.

**Important when processing metadata:**

- **getParameterCount()** includes implicit/synthetic parameters present at runtime.
- **getParameterTypes()** provides the actual types used in the descriptor, needed for lookup.
- **getParameters()** provides Parameter objects and the **isImplicit()/isSynthetic()** flags when metadata allows interpreting them.
- **getGenericParameterTypes()** may return a list with a different count in certain situations involving implicit/synthetic parameters and generic signatures; the API documentation itself warns about this.
- Annotation arrays may also reflect extra parameters under specific rules; do not mechanically pair arrays from two different APIs by index without checking their relationship and lengths.

When building a parameter-mapping library, test on real classes and on the target compiler/JDK. If you need to inspect the descriptor in bytecode, you can use **javap -v** on the .class file to view MethodParameters, Signature, and RuntimeVisibleParameterAnnotations/RuntimeVisibleTypeAnnotations.

## 7. isVarArgs() and Passing Actual Arguments

Given the method:

~~~java
void log(String label, int... numbers) {}
~~~

The compiler turns the last parameter type into an int[] array. A Method looked up via:

~~~java
Method method = clazz.getDeclaredMethod("log", String.class, int[].class);
~~~

is valid if clazz describes the class declaring log.

**isVarArgs()** only indicates that the method was **declared with variable-arity syntax**. It does not mean Reflection always performs overload resolution or automatically packs numbers into an array like Java source call syntax:

~~~java
method.invoke(receiver, "sum", new int[] {1, 2, 3});
~~~

Here receiver is an appropriate instance; the third parameter is passed as an array argument. If a method only takes a single parameter of type String[] and you need to pass the array as **one element** of Method.invoke's Object... varargs, cast explicitly to Object:

~~~java
method.invoke(receiver, (Object) new String[] {"a", "b"});
~~~

The latter line is only valid when the method takes **one String[]**, unlike the log(String,int...) method above. The (Object) cast is especially useful to prevent Java from expanding a String[] reference array into varargs elements of **Method.invoke itself**.

Similarly, **Constructor.newInstance(Object... args)** also takes an argument array matching the runtime signature, rather than running overload selection like javac. Do not use isVarArgs() to assume that every reflective call will automatically convert arbitrary numbers of elements into an array.

## 8. Access Rights via AccessibleObject and JPMS

Method and Constructor inherit the ability to request bypassing certain Java language access checks from AccessibleObject:

~~~java
if (executable.trySetAccessible()) {
    // The caller can request disabling access checks within permitted limits.
}
~~~

This is a fragment assuming an Executable variable already exists.

On the Java Platform Module System (JPMS), a private member of a class belonging to another named module may reside in a package **not opened to the module performing Reflection**. Calling **setAccessible(true)** may throw **InaccessibleObjectException**, while **trySetAccessible()** may return false. A package that is **exports**-ed for public API does not automatically permit deep reflection into private methods/constructors; appropriate **opens** is usually required.

If the goal is only reading metadata, many APIs such as getDeclaredMethods/getDeclaredConstructors/getParameters still work even when you lack permission to invoke non-public members afterward. Therefore:

1. Analyze metadata with Executable first.
2. Only request deep reflective access when you actually need invoke/newInstance.
3. Verify the exact module/package and caller if blocked.
4. Do not use setAccessible to bypass permissions on internal members when a public API already meets the requirement.

Even when **setAccessible(true) succeeds**, it does not alter the Method/Constructor signature, generic return types, parameter count, or annotations. It is a change to access-check enforcement during Reflection, not a modification of the class file.

## 9. Using Executable to Write a Safe Generic Scanner

A scanner used for both Method and Constructor can accept an Executable and print shared fields:

~~~java
static void describe(Executable e) {
    System.out.println("member: " + e.getName());
    for (Parameter p : e.getParameters()) {
        System.out.println(p.getType().getTypeName()
                + " " + p.getName()
                + " (namePresent=" + p.isNamePresent() + ")");
    }
}
~~~

This is a method fragment requiring imports for java.lang.reflect.Executable and java.lang.reflect.Parameter. It can be called with a Method or Constructor. When scanning an entire class, you can retrieve:

~~~java
for (Method m : type.getDeclaredMethods()) {
    describe(m);
}
for (Constructor<?> c : type.getDeclaredConstructors()) {
    describe(c);
}
~~~

The type variable is a resolved Class<?>; the two getDeclared... calls do not traverse superclasses the way getMethods() does, and constructors **are not inherited**.

When upgrading the scanner for a real-world framework:

- Check **Modifier** together with **getDeclaringClass()**; do not rely on the order of getDeclaredMethods()/getDeclaredConstructors().
- Check **Method.isBridge()** (only Method has this) and **Executable.isSynthetic()** to reduce compiler-generated members when generating source API documentation.
- Use **isNamePresent()** before using a parameter name as a property name/JSON key/argument binding.
- Distinguish **getParameterTypes()** when needing runtime descriptors from **getGenericParameterTypes()** when analyzing T, List<T>, or wildcards.
- Distinguish **declaration annotations** from **type-use annotations**.
- When implicit/synthetic parameters exist, check lengths and metadata before pairing multiple arrays by index.
- Use subtype-specific APIs to handle **Method return types** or **Constructor instantiation**.

A framework should not assume parameter names, annotations, and generic types form the entire validation contract: much of this data may be absent due to build settings, retention, obfuscation, or the compiler. Provide fallbacks and clear error messages.

## 10. Common Mistakes and Self-Check Questions

### Common Mistakes

1. **Trying to call executable.invoke(...)**: Executable does not declare a common invoke/newInstance. Distinguish Method and Constructor with instanceof, then use the proper API.
2. **Assuming generic Type is always Class<?>**: for List<String>, Type may be ParameterizedType; for T it may be TypeVariable. Do not cast blindly.
3. **Treating getParameters()[i].getName() as a guaranteed source name**: missing -parameters often yields arg0/arg1, with isNamePresent() returning false.
4. **Confusing isVarArgs with automatic argument packing**: reflective invocation requires arguments matching the descriptor; the last parameter is an array.
5. **Confusing parameter annotations and type-use annotations**: getParameterAnnotations() and getAnnotatedParameterTypes() serve different purposes.
6. **Assuming runtime parameter count always equals the source parameter count**: implicit/synthetic parameters can change parameter count and the generic metadata layout.
7. **Believing getExceptionTypes() lists every exception that can occur on call**: it only reflects the throws declaration; runtime exceptions/errors can still occur.
8. **Calling setAccessible(true) to modify metadata**: the API only alters the ability to bypass certain access checks; JPMS still protects packages that are not appropriately opened.
9. **Ignoring bridge/synthetic methods** when iterating over an entire class; compiler-generated methods can make scanner output differ from source.
10. **Relying on the array order of getDeclaredMethods() or getDeclaredConstructors()**: no stable source order is guaranteed.

### Self-Check

**Question 1.** An Executable variable e points to a Constructor<?>. Can you call e.getParameters()? Can you call e.newInstance() directly?

**Answer:** getParameters() works because it belongs to the Executable API; newInstance() is not a shared API, so you need to cast/check for Constructor<?>.

**Question 2.** A method takes List<String> and int... . What types are used in getDeclaredMethod?

**Answer:** List.class and int[].class, in order. With varargs, the last parameter has an array runtime type.

**Question 3.** A Parameter has name arg1 and isNamePresent() returns false. Should arg1 be used as a fixed API data name?

**Answer:** No. This is usually a synthesized name due to missing metadata. Use -parameters or explicit name-mapping configuration.

**Question 4.** When reading a parameter that has both a @Label declaration annotation and a @Marked TYPE_USE annotation, which APIs should be used?

**Answer:** Parameter.getAnnotation(Label.class) for the declaration annotation and getAnnotatedType()/getAnnotatedParameterTypes() for the type-use annotation.

**Question 5.** A method has a generic type parameter E extends Number; what does getParameterTypes() return for a parameter of type E, and what does getGenericParameterTypes() return?

**Answer:** Usually Number.class and TypeVariable E; type erasure is used for lookup, while generic metadata serves declaration analysis.

**Question 6.** What extra parameter might the constructor of a non-static inner class have?

**Answer:** The enclosing instance parameter of the outer class, typically at the beginning of the runtime descriptor. Use the right Class<?> when looking it up and check Parameter flags if metadata is present.

**Remember:** **Executable is the shared metadata API for Method and Constructor**. Use it to analyze parameters, generics, annotations, exceptions, varargs, and modifiers; when execution is needed, use **Method.invoke** or **Constructor.newInstance**. When relying on parameter names, build with **-parameters** and verify **isNamePresent()**.

### References

- Java SE 17 — Executable: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html
- Java SE 17 — Parameter: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html
- Java SE 17 — Method: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
- Java SE 17 — Constructor<T>: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html
- Java SE 17 — AccessibleObject: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- Oracle Java Tutorials — Obtaining Names of Method Parameters: https://docs.oracle.com/javase/tutorial/reflect/member/methodparameterreflection.html
