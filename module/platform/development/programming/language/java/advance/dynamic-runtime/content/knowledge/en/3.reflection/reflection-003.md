# 3.3. Finding Methods by Name and Parameter Types; Limits of Overload Resolution at Runtime

## Objectives

After this lesson, you will be able to:

- Distinguish between **compile-time overload resolution**, **exact method lookup via Reflection**, and **runtime override dispatch**.
- Correctly use **Class.getMethod**, **Class.getDeclaredMethod**, and **Method.invoke** with the method name and parameter type list.
- Explain why calling **arg.getClass()** and then looking up a method often fails with supertypes, primitives, null, varargs, or generics.
- Know when you need to define your own overload selection algorithm, how to handle ambiguous cases, and access control limitations.
- Recognize that lookup errors differ from method invocation errors; avoid confusing Reflection invocation with "the compiler automatically choosing the best overload".

## 1. Three Different Decisions

Java allows multiple methods with **the same name but different parameter type lists** (overloading). For example:

~~~java
public String format(Object value)  { return "Object"; }
public String format(Number value)  { return "Number"; }
public String format(Integer value) { return "Integer"; }
public String format(int value)     { return "int"; }
~~~

The four methods above are four **overloads**; Java must determine which method is being referred to.

| Mechanism | What decides | Primary timing | Example |
| --- | --- | --- | --- |
| **Compiler overload resolution** | Most appropriate signature based on **compile-time expression types**, applicable overloads, and Java rules | Compile-time | **service.format(value)** |
| **Reflection lookup** | Name and **exact specified Class<?> parameter list**; does not infer the best overload from argument values | Runtime, when calling the lookup API | **type.getMethod("format", Number.class)** |
| **Dynamic dispatch of overrides** | After the signature to call is known, selects the overridden implementation according to the **actual runtime class of the receiver** for virtual instance methods | Runtime, when invoking | A subclass object overriding **format(Object)** |

The word "dynamic" can easily cause confusion: Reflection allows **selecting a signature based on runtime information** if the program itself supplies the name and parameter types, but **it does not mean** **getMethod** is re-running the full overload resolution rules of the Java compiler.

Two questions must be distinguished:

1. **Which signature is selected?** For example, **format(Number)** or **format(Integer)**.
2. **Which implementation executes that signature?** For example, **Base.format(Number)** or **Derived.format(Number)** if the subclass overrides it.

Reflection returning a **Method** object means the signature to be found has already been fixed. Calling **Method.invoke** invokes that method; it does not scan all overloads with the same name to choose again.

## 2. Finding by Exact Name and Parameter Types

### 2.1. Class.getMethod and Class.getDeclaredMethod

Two common APIs:

~~~java
// Find a public method declared by the class or inherited.
Method publicMethod =
        SomeType.class.getMethod("execute", String.class, int.class);

// Find a method declared DIRECTLY in SomeType, regardless of visibility.
Method declaredMethod =
        SomeType.class.getDeclaredMethod("execute", String.class, int.class);
~~~

The snippet above is an **API illustration**, assuming **SomeType** has the corresponding method; it is not a standalone program.

| API | Search scope | Sees private methods declared in the class? | Finds inherited public methods? |
| --- | --- | --- | --- |
| **getMethod(name, parameterTypes...)** | Public methods of the class and inherited public members | No | Yes |
| **getDeclaredMethod(name, parameterTypes...)** | Methods declared in the class itself, including private/protected/package-private | Yes | No |
| **getMethods()** | Array of public methods visible from the class, including inherited ones | No | Yes |
| **getDeclaredMethods()** | Array of methods declared in the class itself | Yes | No |

**getDeclaredMethod** finding a private method **is not synonymous** with having permission to invoke it. Access permissions are checked when Reflection uses the method; package, module, and accessibility rules still apply.

The order of elements in **getMethods() / getDeclaredMethods()** is not guaranteed. Do not pick "the first method with the same name" and assume it is the most suitable overload.

### 2.2. Lookup Method Parameters Are Class Objects, Not Values

Important lookup signatures:

~~~java
Class<?>.getMethod(String name, Class<?>... parameterTypes)
Class<?>.getDeclaredMethod(String name, Class<?>... parameterTypes)
~~~

**parameterTypes** are the **formal parameter types**, in exact order, after type erasure if generics are involved. The Java compiler can usually produce the class descriptors using **String.class**, **Number.class**, **int.class**, **String[].class**, etc.

Examples:

| Declared method | Correct lookup | Error-prone lookup |
| --- | --- | --- |
| **send(String value)** | **getMethod("send", String.class)** | **getMethod("send", Object.class)** |
| **send(Number value)** | **getMethod("send", Number.class)** | **getMethod("send", Integer.class)** |
| **send(int value)** | **getMethod("send", int.class)** | **getMethod("send", Integer.class)** |
| **send(String... values)** | **getMethod("send", String[].class)** | **getMethod("send", String.class)** |
| **send(int[] values)** | **getMethod("send", int[].class)** | **getMethod("send", Integer[].class)** |
| **send(List<String> values)** | **getMethod("send", List.class)** | **getMethod("send", ArrayList.class)** |

In the table, each row is assumed to be considered independently and the **List** type comes from **java.util.List**.

Java Reflection requires **exact parameter type matching**, without using subtype–supertype relationships, autoboxing, primitive widening, or varargs rules to **find** the method. Therefore, **getMethod("send", Integer.class)** does not return **send(Number)**, even though an Integer object can be passed to **send(Number)** once the corresponding Method object is obtained.

An empty parameter list is expressed as **getMethod("run")** (providing no parameter types). When there are multiple overloads, you must pass the exact number and order of types.

### 2.3. Name + Parameters; Not Selected by Return Type

In Java source, you cannot declare two overloads that differ only by return type. The two lines below cannot coexist as two normal method declarations:

~~~java
// Two declarations with the same signature will cause a compile error:
String read(int id);
Integer read(int id);
~~~

This code snippet **intentionally does not compile**, used to illustrate the "method is already defined" error, not a runnable program.

Overloads are distinguished by name and parameter type list; **getMethod** does not accept a return type for selection. However, JVM bytecode and compiler-generated **bridge methods** can create situations where Reflection sees Methods with the same name and parameters but different return types. When scanning all of **getDeclaredMethods**, pay attention to **Method.isBridge()**, **isSynthetic()**, and **getReturnType()**; do not assume the array is always the set of overloads written directly by the programmer.

## 3. Complete Example: Exact Signature Lookup vs. Overload Resolution

Save the file **OverloadLookupDemo.java**:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class OverloadLookupDemo {
    public static class Formatter {
        public String format(Object value) {
            return "Object";
        }

        public String format(Number value) {
            return "Number";
        }

        public String format(Integer value) {
            return "Integer";
        }

        public String format(int value) {
            return "int(" + value + ")";
        }

        public String format(String... values) {
            return "String...:" + String.join(",", values);
        }

        public String onlyNumber(Number value) {
            return "onlyNumber";
        }

        private String hidden(String value) {
            return "hidden:" + value;
        }
    }

    public static void main(String[] args) throws Exception {
        Formatter formatter = new Formatter();

        // Static type is Object, even though the actual object is Integer.
        Object payload = Integer.valueOf(7);
        System.out.println("normal=" + formatter.format(payload));
        System.out.println("runtimeClass="
                + payload.getClass().getSimpleName());

        // Reflection selects the EXACT signature specified.
        Method integerMethod =
                Formatter.class.getMethod("format", Integer.class);
        Method numberMethod =
                Formatter.class.getMethod("format", Number.class);
        Method intMethod =
                Formatter.class.getMethod("format", int.class);

        System.out.println("exactReference="
                + integerMethod.invoke(formatter, payload));
        System.out.println("explicitSuper="
                + numberMethod.invoke(formatter, payload));
        System.out.println("primitive="
                + intMethod.invoke(formatter, Integer.valueOf(7)));
        System.out.println("widening="
                + intMethod.invoke(formatter, Short.valueOf((short) 8)));

        // Java String... parameter is stored as String[].
        Method arrayMethod =
                Formatter.class.getMethod("format", String[].class);
        System.out.println("varargs="
                + arrayMethod.invoke(
                        formatter, (Object) new String[]{"a", "b"}));

        try {
            Formatter.class.getMethod("format", Long.class);
        } catch (NoSuchMethodException e) {
            System.out.println("Long=not-found");
        }

        // getClass() is not an overload resolution algorithm by supertype.
        try {
            Formatter.class.getMethod("onlyNumber", payload.getClass());
        } catch (NoSuchMethodException e) {
            System.out.println("runtimeOnlyNumber=not-found");
        }

        try {
            Formatter.class.getMethod("hidden", String.class);
        } catch (NoSuchMethodException e) {
            System.out.println("public-hidden=not-found");
        }

        Method declared =
                Formatter.class.getDeclaredMethod("hidden", String.class);
        System.out.println("declared-private="
                + Modifier.isPrivate(declared.getModifiers()));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 OverloadLookupDemo.java
java OverloadLookupDemo
~~~

Exact stdout:

~~~text
normal=Object
runtimeClass=Integer
exactReference=Integer
explicitSuper=Number
primitive=int(7)
widening=int(8)
varargs=String...:a,b
Long=not-found
runtimeOnlyNumber=not-found
public-hidden=not-found
declared-private=true
~~~

### Part-by-Part Explanation

**normal=Object:** The expression **payload** has **declared type Object**. The Java compiler chooses the overload **format(Object)**, even though at runtime **payload.getClass()** is **Integer**. A receiver can use dynamic dispatch to select an override of **format(Object)**, but it does not change the signature to **format(Integer)** just because the runtime argument is Integer.

**exactReference=Integer:** The program explicitly requests **getMethod("format", Integer.class)**, so the Method already represents the Integer overload. When passing payload whose actual value is Integer, the call is valid.

**explicitSuper=Number:** There is no "auto-selecting Number" behavior here. The program **specified** the **Number.class** overload, and then passed the Integer object into the Number parameter via subtype relationship.

**primitive=int(7) and widening=int(8):** Lookup requires **int.class** exactly. Once the right Method is found, **Method.invoke** can accept the corresponding wrapper (Integer) or a wrapper of a smaller compatible primitive (Short) and then **unbox and primitive-widen** it for the int parameter. Argument conversion at the invoke step **differs from** the exact match rule at the lookup step. If you change the lookup to **getMethod("format", short.class)**, the API does not automatically find **format(int)**.

**varargs=String...:a,b:** The declaration **String...** becomes a **String[]** parameter. **Method.invoke** itself also has a varargs form **Object...**, so casting **(Object) new String[]{"a", "b"}** passes **the entire String[] array as a single argument** to the target method. Reflection does not automatically pack multiple separate String arguments into a String[] the way the compiler handles normal varargs calls.

**Long=not-found:** There is no overload with an exact **Long** parameter. **format(Number)** and **format(Object)** can accept a Long value when called with the right signature, but they are not the result of looking up **Long.class**.

**runtimeOnlyNumber=not-found:** **onlyNumber** only has the signature **(Number)**; **payload.getClass()** returns **Integer.class**, so the lookup fails even though **onlyNumber(Number)** itself can accept an Integer.

**public-hidden=not-found / declared-private=true:** **getMethod** only searches public methods. **getDeclaredMethod** allows finding a private method declared in Formatter, but retrieving metadata does not automatically grant invocation permission.

## 4. Overload Resolution and Override Dispatch Are Two Independent Layers

The following example has two overloads **call(Object)** and **call(String)**. The subclass **only overrides call(Object)**.

Save the file **OverrideDispatchDemo.java**:

~~~java
import java.lang.reflect.Method;

public class OverrideDispatchDemo {
    public static class Parent {
        public String call(Object value) {
            return "Parent/Object";
        }

        public String call(String value) {
            return "Parent/String";
        }
    }

    public static class Child extends Parent {
        @Override
        public String call(Object value) {
            return "Child/Object";
        }
    }

    public static void main(String[] args) throws Exception {
        Parent receiver = new Child();
        Object value = "hello";

        // The Object signature is selected by the static type of value.
        System.out.println("java=" + receiver.call(value));

        // Reflection fixes the Object signature; the override runs on Child.
        Method objectOverload =
                Parent.class.getMethod("call", Object.class);
        System.out.println("reflectObject="
                + objectOverload.invoke(receiver, value));

        // Reflection fixes the String signature; Child does not override it.
        Method stringOverload =
                Parent.class.getMethod("call", String.class);
        System.out.println("reflectString="
                + stringOverload.invoke(receiver, value));
    }
}
~~~

~~~bash
javac -encoding UTF-8 OverrideDispatchDemo.java
java OverrideDispatchDemo
~~~

Stdout:

~~~text
java=Child/Object
reflectObject=Child/Object
reflectString=Parent/String
~~~

**Why?** For a normal Java call, the compiler selected the **call(Object)** signature because the variable value has static type Object; at runtime when called on Child, the JVM uses the **Child.call(Object)** override. Reflection can also invoke that override when the Method represents Parent's **call(Object)**. However, **getMethod("call", String.class)** explicitly specifies the String signature, and Child does not override this signature, so the inherited implementation **Parent.call(String)** is executed. The actual string **"hello"** does not cause overloads to switch back and forth.

**Rule of thumb:** **Overloading** is choosing between *different signatures*; **overriding** is choosing *different implementations of the same signature* (for virtual calls).

## 5. Why arg.getClass() Is Not a General Overload Resolver

A commonly seen pattern:

~~~java
// Illustrating an UNSAFE idea for general overload lookup:
Class<?>[] types = new Class<?>[args.length];
for (int i = 0; i < args.length; i++) {
    types[i] = args[i].getClass();
}
Method method = target.getClass().getMethod(methodName, types);
~~~

This is an **illustrative fragment** assuming variables **args**, **target**, and **methodName** exist, not a standalone program. It can only work when every element is non-null **and** the runtime classes happen to match the target method's parameters **exactly**.

Important counterexamples:

| Data and available method | Type returned by arg.getClass() | Why lookup can fail? |
| --- | --- | --- |
| Argument **Integer(7)**, method **run(Number)** | Integer.class | Exact lookup does not search supertype Number |
| Argument **Integer(7)**, method **run(int)** | Integer.class | int.class differs from Integer.class |
| Argument **Short(7)**, method **run(int)** | Short.class | Can unbox+widen at invoke time, but lookup does not widen |
| Argument **null**, method **run(String)** | None | **null.getClass()** throws NullPointerException; null does not indicate a formal type |
| Two methods **run(String)** and **run(Integer)**, argument null | None | Using null does not uniquely identify an overload; Java call **run(null)** is also ambiguous at compile-time if the two overloads are unrelated |
| Method **run(String... xs)**, called with individual strings | String.class | Runtime signature takes String[] |
| Method **run(List<String> xs)**, passing ArrayList | ArrayList.class | Runtime parameter after erasure is List.class |
| Methods **run(Serializable)** and **run(Cloneable)**, argument ArrayList | ArrayList.class | Multiple supertypes/interfaces may match; requires a disambiguation policy |

For a parameter type **List<String>**, Reflection looks up the formal type **List.class**, not **List<String>.class**, because Java has no class literal for parameterized generics. You cannot declare two overloads **run(List<String>)** and **run(List<Integer>)** in the same class differing only by type arguments, because both signatures have the same erasure.

Even if you iterate through all methods yourself, **Class.isAssignableFrom(...)** only solves part of the reference type relationship; by itself it does not fully handle primitives, autoboxing, widening, varargs, null, specificity, or the precedence of overload resolution phases.

## 6. If You Want to Select Overloads by Runtime Values, You Must Define a Policy

There is no standard Reflection API that is completely equivalent to "automatically call the best overloaded method as javac would choose if it saw my runtime data". The application must choose an **invocation contract**. Three common approaches:

### Approach A: Contract That Explicitly Specifies Signatures

Used when configuration, RPC, message handlers, or plugins already have a schema explicitly defining what type each argument has. For example, the command **createInvoice** only accepts **(String, int)**; the program obtains the Method using those two Class objects. Each behavior is configured by **name + type list**, rather than guessing from runtime values.

Advantages: predictable, easy to validate, easy to audit, and avoids ambiguity. Suitable if the data source comes from JSON or a schema-based configuration.

### Approach B: Register Allowed Methods

Only expose approved business behaviors, mapping command names to pre-looked-up Methods. For example, **action=showNumeric** maps uniquely to **format(Number)**. Overload selection is **a rule managed by the application**, not dependent on **getMethods()** ordering.

The following fragment pattern applies to the **Formatter** class in the first example:

~~~java
// Fragment in a context where variable Formatter formatter exists.
java.util.Map<String, Method> commands = java.util.Map.of(
        "number", Formatter.class.getMethod("format", Number.class),
        "integer", Formatter.class.getMethod("format", Integer.class)
);
Method chosen = commands.get("number");
Object result = chosen.invoke(formatter, Integer.valueOf(7));
// result is the string "Number".
~~~

The snippet above is **not standalone**; it requires the Formatter class, a formatter object, and checked exception handling as in the previous program. A real application must check for keys not in the allowlist before invoking.

### Approach C: Write Your Own Overload Resolver (When Truly Needed)

If an API receives runtime arguments and must select a method among multiple overloads, you need to clearly specify:

1. **Candidate set:** name, parameter count, public/declared, static/instance, visibility, and receiver; consider filtering bridge/synthetic methods.
2. **Applicability:** whether the parameter types can accept the arguments, including null for reference types, inheritance relationships, primitive conversions, boxing/unboxing, and varargs.
3. **Precedence:** select the more specific method according to defined rules; if Java call-like behavior is needed, you must model the overload resolution phases in the JLS rather than simple scoring.
4. **Ambiguity:** if there are no candidates or multiple equally specific candidates, **report an error clearly**, do not pick the first method.
5. **Execution:** check access permissions, normalize varargs argument packing, and catch errors from Method.invoke.

Approach C easily becomes complex because Java has edge cases such as unrelated interfaces, generic methods, boxing combined with widening, varargs, lambdas, null, and most-specific rules. **Completely reproducing javac from runtime objects does not even have enough information**, because the compiler uses **the static types of expressions** and target typing that raw objects do not retain. If business requirements allow, prefer Approach A or B.

## 7. Frequently Overlooked Limitations

### 7.1. Primitives Differ from Wrappers, and Lookup Differs from Invocation Conversion

**int.class != Integer.class**. **getMethod("process", int.class)** only matches formal type int, while **getMethod("process", Integer.class)** only matches formal type Integer.

After a Method has been selected, **Method.invoke** can unbox a wrapper into a primitive and perform valid **primitive widening**. For example, **Short** can be passed to a method with formal type int via unboxing and widening. There is no arbitrary conversion: you cannot take a **String** and automatically parse it to int, nor can you narrow int to short if it exceeds the invocation contract. For reference parameters, the argument must be reference assignment-compatible; **Method.invoke** does not convert a reference argument type into another type just because there is an overload with the same name.

### 7.2. Null Has No "Runtime Class" to Infer

With **print(String)** and **print(Integer)**, null is value-compatible with both; the program must choose the signature using additional information (schema, declaration, cast, or policy). **getMethod("print", String.class)** is an explicit choice; **null.getClass()** is an error. For a primitive formal parameter, null cannot be unboxed to invoke the method.

When invoking via Reflection, null must be packaged in the right argument form for **invoke**, for example **method.invoke(receiver, new Object[]{null})** to pass **one null argument**. Avoid confusing it with **(Object[]) null**, which means the argument array for invoke itself was not provided.

### 7.3. Varargs Are Arrays at Runtime

**void log(String... lines)** has formal type **String[]**. Reflection lookup uses **String[].class**. **Method.invoke(Object receiver, Object... args)** is itself varargs, so:

~~~java
// Illustrative fragment, assuming logMethod takes exactly one String[]:
logMethod.invoke(receiver, (Object) new String[]{"a", "b"});
// Or:
logMethod.invoke(receiver, new Object[]{new String[]{"a", "b"}});
~~~

Do not expect **logMethod.invoke(receiver, "a", "b")** to automatically pack two Strings into one String[]. At the Method.invoke level, those are **two** separate arguments, whereas the target method has only **one** formal parameter of type String[].

### 7.4. Generics Are Type-Erased; Bridge Methods May Appear

A method declared as **void consume(List<String> items)** has a runtime formal parameter of **java.util.List.class**. Generic information can be inspected via **Method.getGenericParameterTypes()**, but **getMethod** still looks up by the Class<?> of the post-erasure type.

When inheriting generics or overriding with a covariant return type, the compiler may generate a **bridge method** to preserve dispatch compatibility. Therefore, when listing methods via Reflection, you may encounter synthetic/bridge methods. Check **isBridge()**, **isSynthetic()**, **getDeclaringClass()**, **getParameterTypes()**, and **getReturnType()** if you are writing a resolver or API analyzer. Do not treat all such Methods as independent business overload choices.

### 7.5. Public, Declared, and Access Permissions Are Different Layers

- **getMethod** finds public methods, including inherited ones.
- **getDeclaredMethod** finds methods on the class itself, including private ones; it does not automatically search private methods of superclasses.
- **Method.invoke** still must check access permissions when needed.
- **setAccessible(true)** or **trySetAccessible()** may be restricted by the Java Platform Module System and strong encapsulation; you cannot assume you can always open private members of another module.
- For static methods, the receiver object of invoke is ignored (null can be used). For instance methods, the receiver must be compatible with the declaring class.

Reflection can find a Method and still lack permission to invoke it; lookup errors and access errors are two different kinds of failures.

### 7.6. Reflection Has Overhead and Errors Are Discovered at Runtime

Lookup by name can fail when deployed with a different version, a signature change, or missing module permissions. Errors only surface at runtime, whereas static Java calls are checked much more by the compiler. If calling the same method repeatedly, you can cache the **Method** after verifying the right class loader/version and signature; do not scan methods on every request if unnecessary. Only optimize when actual cost is measured.

## 8. Handling Errors at the Right Stage

| Stage | Common error | Appropriate action |
| --- | --- | --- |
| Lookup with **getMethod / getDeclaredMethod** | **NoSuchMethodException** | Check name, count, order, and Class<?> of formal parameters; public vs declared; class loader |
| Invocation with **invoke** | **IllegalArgumentException** | Check receiver, argument count/types, and valid conversions |
| Invocation with **invoke** | **IllegalAccessException** | Check visibility, module open permissions, and access context |
| The invoked method itself throws an error | **InvocationTargetException** | Read **getCause()** or **getTargetException()** to handle the actual exception from the method |
| Involved object/type is invalid | **NullPointerException**, **LinkageError**, or other runtime errors depending on context | Determine whether null is in the receiver/argument or there is a class loading/linking issue; do not lump all errors into "method does not exist" |

For example, when a business method throws **IllegalStateException**, **Method.invoke** typically reports an **InvocationTargetException** wrapping that error; do not catch it and log "NoSuchMethodException" or drop the cause. **getMethod** succeeding also does not guarantee **invoke** will succeed on all arguments.

For systems that receive method names from JSON, HTTP, or plugins, use a **signature allowlist**, validate argument counts and types after parsing, reject disallowed names, and limit the Reflection surface. Do not let untrusted input freely invoke any public method on an object.

## 9. Self-Check Questions

**1.** A variable is declared **Number n = Integer.valueOf(9)**. A class has two overloads **f(Number)** and **f(Integer)**. Which overload does a normal Java call **f(n)** choose?

**Answer:** **f(Number)** because the static type of the expression n is Number. The actual Integer object does not cause the compiler to re-select the overload at runtime.

**2.** Only **f(Number)** exists. Does **getMethod("f", Integer.class)** find it?

**Answer:** No. Lookup requires the exact **Number.class**; **Integer.class** is not automatically "widened" to a supertype.

**3.** If you already have the Method for **f(int)**, can you invoke it with **Integer.valueOf(9)**?

**Answer:** Yes, when other invocation conditions are valid. Reflection can unbox Integer to int at the **invoke** step. However, the lookup **getMethod("f", Integer.class)** still will not find **f(int)**.

**4.** Is **f(String... values)** looked up with **String.class** or **String[].class**?

**Answer:** **String[].class**, because varargs is an array at the method's formal parameter level.

**5.** **getDeclaredMethod("secret", String.class)** found a private method. Does this guarantee **invoke** will succeed from any module?

**Answer:** No. Lookup and access check are two separate steps; module/visibility rules may prevent access.

**6.** **Parent.call(Object)** is overridden by **Child**. Using the Method for **Parent.call(Object)** and a Child receiver, does it always run Parent?

**Answer:** No. For virtual instance methods, **Method.invoke** performs dynamic method dispatch, so Child's override can be called.

**7.** Why is scanning **getMethods()**, filtering by the same name, and taking the first element wrong?

**Answer:** There is no guaranteed order, and multiple overloads can have the same name; there are also scope, inheritance, and bridge/synthetic method issues. Overload selection requires an explicit signature/policy.

## Key Takeaways

- **getMethod / getDeclaredMethod** looks up by **name + Class<?> of formal parameters in exact order**. This is **exact signature lookup**.
- **Method.invoke** executes the **selected Method**; it performs some valid argument conversions but **does not re-resolve overloads**.
- The Java compiler's **overload resolution** is based on **static types**, whereas **override dispatch** of instance methods can be based on the actual class of the receiver.
- **arg.getClass()** is not an overload resolver: it misses null, supertypes/interfaces, primitives, varargs, generic erasure, and ambiguous cases.
- When you must select a method from runtime data, prefer **an explicit signature contract or an allowed Method registry**; if you must write your own resolver, define applicability/specificity/ambiguity error policies in a verifiable way.

## References

- Java SE 17, **java.lang.Class** (getMethod, getDeclaredMethod, getMethods, getDeclaredMethods): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17, **java.lang.reflect.Method** (invoke, isVarArgs, isBridge, getParameterTypes): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
- Java Language Specification, **15.12 Method Invocation Expressions**, especially **15.12.2 Compile-Time Step 2: Determine Method Signature**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.2
- Java Language Specification, **8.4 Method Declarations**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4
