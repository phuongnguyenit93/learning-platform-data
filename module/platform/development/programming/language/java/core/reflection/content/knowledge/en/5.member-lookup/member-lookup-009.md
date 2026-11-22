# Member Lookup by Erased Types After Type Erasure in Java Reflection

When finding methods, constructors, or fields of a generic class using Java Reflection, you must distinguish **runtime types for lookup** from **generic declarations in source code**. Java uses *type erasure*: a type variable such as T is typically replaced by Object or its first bound, while List<String> carries only the raw type List in the signature used to find the method. Declared generic information can still reside in the class file's Signature attribute for the getGeneric... APIs to read back.

This lesson explains how to choose the right Class<?> during lookup, how to inspect Type to analyze generics, how generics behave across inheritance, and why the compiler generates bridge methods.

## 1. Type Erasure Rules Related to Lookup

| Declared Parameter Type | Class<?> Used to Look Up After Erasure | Reason |
| --- | --- | --- |
| T (unbounded) | Object.class | Erasure of an unbounded type variable |
| T extends Number | Number.class | Erasure to the bound |
| T extends Number & Comparable<T> | Number.class | Selects the first bound |
| List<String> | List.class | Erases the String type argument |
| List<? extends Number> | List.class | Wildcard does not change the raw type |
| T[] with unbounded T | Object[].class | Erases the element type to Object |
| String... | String[].class | Varargs is an array parameter |

Consider the declaration:

~~~java
class Holder<T extends Number> {
    void set(T value) {}
    void setAll(java.util.List<String> values) {}
}
~~~

Here are the two correct lookups:

~~~java
Holder.class.getDeclaredMethod("set", Number.class);
Holder.class.getDeclaredMethod("setAll", java.util.List.class);
~~~

Do not look up set using Integer.class even though in the application you may pass Integer for T; the declared type has already been erased to Number. Also do not pass a ParameterizedType representing List<String> into getDeclaredMethod because this API accepts an array of Class<?> describing **parameter types after erasure**.

Two overloads differing only in generic type arguments lead to the same erasure and will conflict at compile time. The following snippet **intentionally fails to compile**:

~~~java
void process(java.util.List<String> items) {}
void process(java.util.List<Integer> items) {} // name clash: same erasure
~~~

Objects new ArrayList<String>() and new ArrayList<Integer>() both have runtime class java.util.ArrayList; calling getClass() cannot recover the String/Integer type argument from a regular instance.

## 2. Member Lookup APIs and Search Scope

**Method**

- getDeclaredMethod(name, Class<?>...) finds a method declared **directly in the class** at any access level, including private; does not find inherited methods.
- getMethod(name, Class<?>...) finds a **`public`** method, including inherited public methods.
- getDeclaredMethods() / getMethods() return lists to find overloads, filter bridges, or inspect generic information.
- getDeclaredMethod/getMethod matches the name and the parameter types list after erasure; **does not require the return type**. For bridge methods with the same name and parameters, use isBridge()/isSynthetic() when iterating the list.
- For void update(int id, List<String> values), int.class and List.class are required in exact order. int.class differs from Integer.class; String[].class differs from String.class in varargs.

~~~java
clazz.getDeclaredMethod("update", int.class, java.util.List.class);
~~~

**Constructor**

- getDeclaredConstructor(Class<?>...) finds a constructor declared in the class at any access level.
- getConstructor(Class<?>...) finds only public constructors.
- If a constructor takes T extends Number, look it up with Number.class, even if the value passed when creating an instance is Integer.

**Field**

- getDeclaredField(name) finds a field declared directly, including private; getField(name) finds a public field and can see inherited fields.
- Fields are looked up by **name**, with no type parameters in the lookup call. Afterward, Field.getType() returns the erased type, while Field.getGenericType() returns the declared generic information when metadata is present.
- Field T value of class Holder<T extends Number> will have getType() as Number.class, and getGenericType() typically as a TypeVariable named T.

Looking up a member does not mean being able to access/invoke it successfully. Private access and module encapsulation still apply; type erasure does not allow bypassing access control.

## 3. Compilable and Runnable Java 17+ Example

Create the file **ErasureLookupDemo.java** with all the code below:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.Arrays;
import java.util.List;

public class ErasureLookupDemo {
    static class Store<T extends Number> {
        private T lastValue;
        public Store() {}
        public Store(T initial) { lastValue = initial; }
        public void put(T value) {}
        public void putList(List<String> values) {}
        public T first() { return null; }
        public void labels(String... values) {}
    }

    static class Base<T> {
        public T get() { return null; }
    }

    static class InheritsText extends Base<String> {}

    static class TextStore extends Base<String> {
        @Override
        public String get() { return "hello"; }
    }

    public static void main(String[] args) throws Exception {
        Constructor<?> constructor = Store.class.getDeclaredConstructor(Number.class);
        System.out.println("ctor/erased = " + constructor.getParameterTypes()[0].getTypeName());

        Field field = Store.class.getDeclaredField("lastValue");
        System.out.println("field/erased = " + field.getType().getTypeName());
        System.out.println("field/generic = " + field.getGenericType().getTypeName());

        Method put = Store.class.getDeclaredMethod("put", Number.class);
        System.out.println("put/erased = " + put.getParameterTypes()[0].getTypeName());
        System.out.println("put/generic = " + put.getGenericParameterTypes()[0].getTypeName());

        Method putList = Store.class.getDeclaredMethod("putList", List.class);
        System.out.println("putList/erased = " + putList.getParameterTypes()[0].getTypeName());
        Type declaredType = putList.getGenericParameterTypes()[0];
        if (declaredType instanceof ParameterizedType parameterized) {
            System.out.println("putList/typeArg = "
                    + parameterized.getActualTypeArguments()[0].getTypeName());
        }

        Method first = Store.class.getDeclaredMethod("first");
        System.out.println("first/erased = " + first.getReturnType().getTypeName());
        System.out.println("first/generic = " + first.getGenericReturnType().getTypeName());

        Method labels = Store.class.getDeclaredMethod("labels", String[].class);
        System.out.println("labels/isVarArgs = " + labels.isVarArgs());

        try {
            Store.class.getDeclaredMethod("put", Integer.class);
        } catch (NoSuchMethodException ex) {
            System.out.println("put(Integer) = not found");
        }

        Method inherited = InheritsText.class.getMethod("get");
        System.out.println("InheritsText.get/erased = " + inherited.getReturnType().getSimpleName());
        System.out.println("InheritsText.get/generic = " + inherited.getGenericReturnType().getTypeName());

        Method[] declared = TextStore.class.getDeclaredMethods();
        Arrays.sort(declared, (left, right) -> Boolean.compare(left.isBridge(), right.isBridge()));
        for (Method method : declared) {
            if (method.getName().equals("get")) {
                System.out.println("TextStore.get = " + method.getReturnType().getSimpleName()
                        + ", bridge=" + method.isBridge());
            }
        }

        Type parent = TextStore.class.getGenericSuperclass();
        if (parent instanceof ParameterizedType parameterized) {
            System.out.println("TextStore<Base> arg = "
                    + parameterized.getActualTypeArguments()[0].getTypeName());
        }
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac -encoding UTF-8 ErasureLookupDemo.java
java ErasureLookupDemo
~~~

Stdout output verified with JDK 21 and using Java 17-compatible features:

~~~text
ctor/erased = java.lang.Number
field/erased = java.lang.Number
field/generic = T
put/erased = java.lang.Number
put/generic = T
putList/erased = java.util.List
putList/typeArg = java.lang.String
first/erased = java.lang.Number
first/generic = T
labels/isVarArgs = true
put(Integer) = not found
InheritsText.get/erased = Object
InheritsText.get/generic = T
TextStore.get = String, bridge=false
TextStore.get = Object, bridge=true
TextStore<Base> arg = java.lang.String
~~~

Output explanation:

1. **Erased types**: Store<T extends Number> declares a constructor and method taking T, yet getDeclaredConstructor/getDeclaredMethod must receive Number.class. The field and return type T also have raw Class Number.
2. **Preserved generic declarations**: getGenericType/getGenericParameterTypes/getGenericReturnType return TypeVariable T; putList has ParameterizedType with actual type argument String even though lookup only used List.class.
3. **Inherited method**: InheritsText extends Base<String> without overriding get(); the Method inherited from Base still has erased return type Object and generic return T. To know String is Base's type argument on the subclass, you must analyze getGenericSuperclass().
4. **Bridge method**: TextStore overrides get() returning String. The compiler adds a bridge get() returning Object (isBridge() == true) so calls through Base continue dispatching properly after erasure. The order of getDeclaredMethods() is not guaranteed; the example actively sorts before printing for stable stdout.

## 4. Class<?> for Lookup; Type for Reading Generic Signatures

| Task | API | Result Form |
| --- | --- | --- |
| Find method or constructor | getMethod/getDeclaredMethod/getConstructor/getDeclaredConstructor | Pass erased Class<?>... |
| Read runtime parameter types | Method.getParameterTypes(), Constructor.getParameterTypes() | Class<?>[] |
| Read runtime return/field type | Method.getReturnType(), Field.getType() | Class<?> |
| Read method generics | Method.getGenericParameterTypes(), Method.getGenericReturnType() | Type[], Type |
| Read constructor generics | Constructor.getGenericParameterTypes() | Type[] |
| Read field generics | Field.getGenericType() | Type |
| Read generic superclass/interfaces | Class.getGenericSuperclass(), Class.getGenericInterfaces() | Type, Type[] |

Type is a general interface; not every Type is a Class. Common cases:

- **Class<?>**: non-parameterized type at the inspected position.
- **ParameterizedType**: List<String>, Map<String, Integer>; use getRawType() and getActualTypeArguments().
- **TypeVariable<?>**: T; use getName() and getBounds().
- **WildcardType**: the ? in List<? extends Number>; use getUpperBounds()/getLowerBounds().
- **GenericArrayType**: an array type still containing a generic type variable, e.g., T[].

Do not cast Type directly to ParameterizedType without an instanceof check. Generic metadata describes the **declared signature**. It is not a runtime mechanism verifying that all actual elements in a List are indeed String, especially when raw types or unchecked conversions exist.

Using the Store class from the example above, the following snippet illustrates separating the raw type and type argument (this is an **excerpt depending on Store**, not a standalone runnable file):

~~~java
Method m = Store.class.getDeclaredMethod("putList", List.class);
Type t = m.getGenericParameterTypes()[0];
if (t instanceof ParameterizedType p) {
    System.out.println(p.getRawType());               // interface java.util.List
    System.out.println(p.getActualTypeArguments()[0]); // class java.lang.String
}
~~~

To deduce the binding T = String from a subclass extends Base<String>, you must traverse generic superclass/interfaces, extract actual type arguments, and map them to type variables in the declaring class. Calling getMethod() on an inherited method does not automatically replace every TypeVariable in that method with the subclass's concrete type.

## 5. Workflow for Handling a Lookup Request

1. **Determine the declaration site and visibility.** Choose getDeclaredMethod/getDeclaredConstructor/getDeclaredField when you need directly declared members (including non-public); choose getMethod/getConstructor/getField when requiring corresponding public ones.
2. **Convert each parameter type to its erasure.** Drop type arguments of parameterized types; replace T with Object or the erasure of its first bound; keep arrays in array class form; for primitives use exact int.class/long.class...
3. **Look up name + parameters in exact order.** For example, foo(T, List<String>, int[]) with T extends Number requires Number.class, List.class, int[].class. Fields are looked up by name only.
4. **Read generic metadata when the problem needs it.** Use getGeneric... and instanceof to distinguish ParameterizedType, TypeVariable, WildcardType, GenericArrayType; when inheritance is involved, add type variable mapping across superclasses/interfaces.
5. **If listing methods after generic overriding**, check isBridge()/isSynthetic(); depending on needs, bridge methods can be excluded when generating source-oriented API docs, while retained when analyzing JVM dispatch.

## 6. Common Errors and How to Identify Them

- **NoSuchMethodException**: passing Integer.class for T extends Number; passing Integer.class instead of int.class; passing String.class instead of String[].class for varargs; or confusing getDeclaredMethod with getMethod when the member is actually inherited.
- **Confusing type arguments with runtime parameter types**: getDeclaredMethod uses List.class whether source writes List<String> or List<Integer>. There is no List<String>.class.
- **Confusing generic superclass with the signature of an inherited method**: extends Base<String> does not suddenly give Base.get() an erased return type of String.
- **Not checking bridge methods**: getDeclaredMethods() may contain compiler-generated methods; do not rely on Method array order when finding a specific version.
- **Misusing getGeneric... to validate runtime values**: generic type info mostly describes declarations. Casts/invoke calls can still fail and remain constrained by access permissions or module boundaries.
- **Treating return type as a lookup parameter**: getMethod/getDeclaredMethod does not accept return types; if you need to analyze the return type, read Method.getReturnType()/getGenericReturnType() after obtaining Method.

## 7. Self-Check Exercise

For a method declared as **<T extends CharSequence> void consume(T[] data, List<? super String> output)**, it is looked up with:

~~~java
clazz.getDeclaredMethod("consume", CharSequence[].class, java.util.List.class);
~~~

T[] is erased to CharSequence[] due to T's bound; List<? super String> is erased to List. When reading getGenericParameterTypes()[0], you typically receive a GenericArrayType containing TypeVariable T; the second parameter is a ParameterizedType containing a WildcardType with lower bound String. Looking up with String[].class is wrong even though an actual call might pass a String[] array.

**Takeaway:** use erased Class<?> objects to **find** members; use Type to **analyze** declared generic information. With generic inheritance and overriding, additionally inspect generic superclasses and bridge methods.

### References

- Java Language Specification 17, §4.6 — Type Erasure: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6
- JDK 17 Class API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- JDK 17 Method API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
- JDK 17 ParameterizedType API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html