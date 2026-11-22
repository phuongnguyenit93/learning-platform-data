# `getGenericSuperclass` and `getGenericInterfaces` in Java Reflection

When Java Reflection analyzes a class, there are two distinct questions: **which class does this class directly extend?** and **which interfaces does it directly declare implementing/extending?**. If those relationships carry type arguments, such as **extends Repository<Order>** or **implements Handler<List<String>>**, APIs that return only `Class` discard the generic parameter information. The two methods **Class.getGenericSuperclass()** and **Class.getGenericInterfaces()** read those generic declarations from the class file.

This lesson focuses on how to use both APIs, distinguishing `Class` from `Type`/`ParameterizedType`, the "direct" boundary in the inheritance tree, how to handle type variables across multiple levels, and special cases such as interfaces, raw types, anonymous subclasses, and array classes. Examples use Java 17+ and require no external libraries.

## 1. Distinguishing Ordinary APIs from Generic APIs

A class may declare:

~~~java
class Base<T> {}

interface Named<T> {}

class User extends Base<String> implements Named<Integer> {}
~~~

From **User.class**, the related APIs return:

| API | Return type | Meaning |
| --- | --- | --- |
| **getSuperclass()** | Class<?> or null | Direct superclass `Class`, after erasure; e.g. Base.class |
| **getGenericSuperclass()** | Type or null | Direct superclass declaration, which can be Base<String> |
| **getInterfaces()** | Class<?>[] | Direct interfaces, runtime type; e.g. Named.class |
| **getGenericInterfaces()** | Type[] | Direct interfaces, which can include Named<Integer> |
| **getTypeParameters()** | TypeVariable<?>[] | Type variables declared by the class/interface itself, such as T in Base<T> |
| **getAnnotatedSuperclass()** | AnnotatedType or null | Type use of the superclass with TYPE_USE annotations if present |
| **getAnnotatedInterfaces()** | AnnotatedType[] | Type use of direct interfaces with TYPE_USE annotations if present |

**Important:** getGenericSuperclass/getGenericInterfaces do not return "a list of all ancestors." They reflect **direct edges** in the declaration of the class/interface being inspected. To find all indirect interfaces or substitute type variables across multiple classes, you must traverse further yourself.

For **extends Base<String>**, getSuperclass() provides the **Class of Base**, whereas getGenericSuperclass() typically provides a **ParameterizedType** consisting of raw type Base and actual type argument String.

## 2. Structure of `Type` and `ParameterizedType`

Objects returned from generic APIs have the general type **java.lang.reflect.Type**. `Type` is a common interface; not every `Type` is a `Class`.

| `Type` form | Example | How to recognize / query |
| --- | --- | --- |
| **Class<?>** | Object, String, raw Base, an unparameterized interface | Check **instanceof Class<?>** |
| **ParameterizedType** | Base<String>, Handler<List<Integer>> | **getRawType()**, **getActualTypeArguments()**, **getOwnerType()** |
| **TypeVariable<?>** | T, E, X in generic declarations | **getName()**, **getBounds()**, **getGenericDeclaration()** |
| **WildcardType** | ? extends Number, ? super String | **getUpperBounds()**, **getLowerBounds()** |
| **GenericArrayType** | T[] when component is a type variable | **getGenericComponentType()** |

A safe reflex is always to **branch on the `Type` kind** before casting:

~~~java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;

Type type = User.class.getGenericSuperclass();
if (type instanceof ParameterizedType parameterized) {
    Type raw = parameterized.getRawType();
    Type[] arguments = parameterized.getActualTypeArguments();
    System.out.println(raw);            // class Base, name depends on package/nesting
    System.out.println(arguments[0]);   // class java.lang.String
}
~~~

This is an illustrative snippet requiring classes Base/User in the same compilation unit as section 1; the two comment lines are not standardized stdout of a standalone program.

### Three Components of `ParameterizedType`

- **getRawType()**: the underlying class/interface, e.g. Base in Base<String>. The return type is declared as Type; when working with standard JVM Reflection, the raw type is mainly Class<?>.
- **getActualTypeArguments()**: the type arguments at the declared inheritance edge, e.g. String or a complex Type like List<T>. When multiple type arguments are declared, the order matches the declaration.
- **getOwnerType()**: the enclosing type when the parameterized type is a member type, e.g. Outer<String>.Inner<Integer>; for top-level types, it is usually null.

**Do not cast directly**:

~~~java
// Unsafe if the superclass is Object, a raw type, or there is no superclass:
ParameterizedType p = (ParameterizedType) clazz.getGenericSuperclass();
~~~

This snippet intentionally illustrates an antipattern. getGenericSuperclass() can return **Class<?>** or **null**; the cast above will cause ClassCastException or lead to NullPointerException later.

### Type.getTypeName()

Every Type has **getTypeName()** to obtain a string representation of the type, convenient for logs and documentation. However, this string is not a standard interface for parsing back every generic structure; when writing tools, handling **Type objects by kind** remains more accurate. Full names can include packages, `$` signs of nested classes, and complex generic expressions.

## 3. `getGenericSuperclass()`: Only the Direct Superclass

Distinguish the following declarations:

~~~java
class Parent<T> {}
class Concrete extends Parent<String> {}
class Plain {}
class RawChild extends Parent {} // Inherits raw type, String information is not declared
~~~

| `Class` object | getGenericSuperclass() | Explanation |
| --- | --- | --- |
| Concrete.class | ParameterizedType describing Parent<String> | Superclass declaration has an actual type argument |
| Parent.class | Class describing Object | Parent writes no `extends` and defaults to superclass Object |
| Plain.class | Class describing Object | Default superclass |
| RawChild.class | Class describing Parent | Raw `extends` supplies no actual type argument |
| Object.class | null | Object has no superclass |
| List.class (interface) | null | An interface has no class superclass |
| int.class, void.class | null | Primitives and void have no superclass |
| String[].class | Class describing Object | An array class has superclass Object |

Each call reads only **one level of class superclass**. For example:

~~~text
Leaf extends Middle<Integer>
Middle<X> extends Parent<List<X>>
Parent<T> extends Object
~~~

When calling **Leaf.class.getGenericSuperclass()**, the result is **Middle<Integer>**, not Parent<List<Integer>>. When calling **Middle.class.getGenericSuperclass()**, the result is **Parent<List<X>>**. To get Parent<List<Integer>> in Leaf's context, you must combine both edges and substitute **X → Integer** in Middle's signature.

This is the most important limitation of custom hierarchy-analysis libraries: they can read each edge's Type accurately, yet still infer incorrectly if they skip type-variable mapping.

### A Non-Generic Class Can Still Have a Generic Superclass

Concrete may have no type variables of its own:

~~~java
Concrete.class.getTypeParameters().length == 0
~~~

yet still have **Parent<String>** in getGenericSuperclass(). Conversely, Parent.class.getTypeParameters() has T, while Parent.class.getGenericSuperclass() is just Object. The two APIs answer two different questions: **which type variables does this class declare** and **what generic type does this class use on its extends edge**.

## 4. `getGenericInterfaces()`: Direct Interfaces List

With:

~~~java
interface Keyed<T> {}
interface Logged {}
class Service implements Keyed<String>, Logged {}
~~~

**Service.class.getGenericInterfaces()** returns a Type array with two elements in declaration order:

1. ParameterizedType representing Keyed<String>.
2. Class<?> representing Logged because that interface is not parameterized at that site.

If a class does not directly declare `implements`, the result is usually an **empty array**, even when it **inherits** an interface from its superclass.

~~~java
class ParentService implements Keyed<String> {}
class ChildService extends ParentService {}
~~~

**ChildService.class.getGenericInterfaces()** returns an empty array; **ParentService.class.getGenericInterfaces()** contains Keyed<String>. That **does not mean** ChildService is not a Keyed: **Keyed.class.isAssignableFrom(ChildService.class)** can still return true due to the inheritance relationship.

For an **interface** extending other interfaces, getGenericInterfaces() returns the **direct superinterfaces**, in declared order:

~~~java
interface Tag<T> {}
interface Compound<T> extends Tag<java.util.List<T>> {}
~~~

**Compound.class.getGenericInterfaces()** contains a Type representing **Tag<List<T>>**, where T is a TypeVariable declared by Compound. **Compound.class.getGenericSuperclass()** returns **null**, because Compound is an interface and has no class superclass.

### Ordering and Array Types

Java SE 17 specifies the order of interfaces from getInterfaces/getGenericInterfaces follows their order in the **implements** or **extends** clause. Thus when direct interfaces are declared as A, B, the corresponding array is A, B.

For an **array class**, getGenericInterfaces() returns the two runtime array interfaces: **Cloneable**, **java.io.Serializable**, in that order. For primitives/void or classes/interfaces that declare no direct interfaces, the array is empty. An array has superclass Object via getGenericSuperclass() and contains no generic element argument under the parameterized class mechanism.

## 5. Complete Runnable Example on Java 17+

The program below shows the difference between generic superclass, generic interfaces, erased superclass, type arguments, raw inheritance, and indirectly inherited interfaces. The **display(Type)** helper intentionally prints short names so stdout is stable, avoiding dependence on full nested class names.

Save verbatim to **HierarchyReflectionDemo.java**:

~~~java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class HierarchyReflectionDemo {
    interface Named<T> {}
    interface Audited {}
    interface Chain<T> extends Named<List<T>> {}

    static class Base<T> {}
    static class Direct extends Base<String> implements Named<Integer>, Audited {}
    static class Middle<X> extends Base<List<X>> implements Named<X> {}
    static class Leaf extends Middle<Integer> {}
    static class Raw extends Base {} // Raw superclass: argument information absent
    static class Plain {}

    private static String display(Type t) {
        if (t == null) return "null";
        if (t instanceof ParameterizedType p) {
            String args = Arrays.stream(p.getActualTypeArguments())
                    .map(HierarchyReflectionDemo::display)
                    .collect(Collectors.joining(", "));
            return display(p.getRawType()) + "<" + args + ">";
        }
        if (t instanceof Class<?> c) return c.getSimpleName();
        if (t instanceof TypeVariable<?> v) return v.getName();
        return t.getTypeName();
    }

    private static String interfacesOf(Class<?> type) {
        return Arrays.stream(type.getGenericInterfaces())
                .map(HierarchyReflectionDemo::display)
                .collect(Collectors.joining(", ", "[", "]"));
    }

    public static void main(String[] args) {
        System.out.println("Direct superclass=" + display(Direct.class.getGenericSuperclass()));
        System.out.println("Direct interfaces=" + interfacesOf(Direct.class));
        System.out.println("Direct raw superclass=" + Direct.class.getSuperclass().getSimpleName());

        Type supertype = Direct.class.getGenericSuperclass();
        if (supertype instanceof ParameterizedType p) {
            System.out.println("Direct super raw=" + display(p.getRawType()));
            System.out.println("Direct super arg=" + display(p.getActualTypeArguments()[0]));
        }

        System.out.println("Leaf superclass=" + display(Leaf.class.getGenericSuperclass()));
        System.out.println("Leaf interfaces=" + interfacesOf(Leaf.class));
        System.out.println("Middle superclass=" + display(Middle.class.getGenericSuperclass()));
        System.out.println("Middle interfaces=" + interfacesOf(Middle.class));
        System.out.println("Chain superclass=" + display(Chain.class.getGenericSuperclass()));
        System.out.println("Chain interfaces=" + interfacesOf(Chain.class));
        System.out.println("Raw superclass=" + display(Raw.class.getGenericSuperclass()));
        System.out.println("Plain superclass=" + display(Plain.class.getGenericSuperclass()));
        System.out.println("Object superclass=" + display(Object.class.getGenericSuperclass()));
        System.out.println("List superclass=" + display(List.class.getGenericSuperclass()));
        System.out.println("String[] superclass=" + display(String[].class.getGenericSuperclass()));
    }
}
~~~

From the directory containing the file, compile and run:

~~~bash
javac --release 17 -encoding UTF-8 HierarchyReflectionDemo.java
java HierarchyReflectionDemo
~~~

Stdout verified on JDK 21 with Java 17-compatible source:

~~~text
Direct superclass=Base<String>
Direct interfaces=[Named<Integer>, Audited]
Direct raw superclass=Base
Direct super raw=Base
Direct super arg=String
Leaf superclass=Middle<Integer>
Leaf interfaces=[]
Middle superclass=Base<List<X>>
Middle interfaces=[Named<X>]
Chain superclass=null
Chain interfaces=[Named<List<T>>]
Raw superclass=Base
Plain superclass=Object
Object superclass=null
List superclass=null
String[] superclass=Object
~~~

### How to Read the Output

- **Direct superclass=Base<String>**: The `Type` contains the String argument just as on the extends edge.
- **Direct raw superclass=Base**: Class.getSuperclass() does not retain String.
- **Direct interfaces=[Named<Integer>, Audited]**: one parameterized interface and one unparameterized interface, in implements order.
- **Leaf interfaces=[]**: Leaf does not directly declare implements, even though it inherits the Named contract through Middle.
- **Middle superclass=Base<List<X>>**: The Type still has X because we are reading the edge declared by Middle, without yet substituting Leaf's Integer for X.
- **Chain superclass=null**: an interface has no class superclass. However, **Chain interfaces=[Named<List<T>>]** expresses the extends relationship with the interface.
- **Raw superclass=Base**: raw type inheritance; there is no String or type argument to retrieve from that edge.
- **Plain superclass=Object** while **Object superclass=null**.
- **String[] superclass=Object**: a runtime array is a class whose superclass is Object; it also directly implements Cloneable and Serializable.

The display() method is an illustrative utility. In real applications, Type.getTypeName() can return full names such as **java.util.List<java.lang.String>** or nested class names containing `$`, so do not copy shortened output to compare runtime name strings.

## 6. Multi-Level Traversal and `TypeVariable` Substitution

The two APIs discussed in this lesson provide **direct edges**. To trace the type of an interface or superclass in the context of a final subclass, you must traverse **the entire inheritance graph** while carrying generic type mappings along.

Revisit the chain:

~~~java
class Base<T> {}
class Middle<X> extends Base<List<X>> {}
class Leaf extends Middle<Integer> {}
~~~

Starting from Leaf:

1. Read **Leaf.class.getGenericSuperclass()** → Middle<Integer>.
2. In this ParameterizedType, the raw type is Middle.class and the actual argument is Integer.class. Create the mapping **X → Integer** based on Middle.class.getTypeParameters().
3. Read **Middle.class.getGenericSuperclass()** → Base<List<X>>.
4. Substitute TypeVariable X with Integer using the mapping from step 2, yielding **Base<List<Integer>>** in Leaf's context.
5. If continuing to Base.class, maintain the additional mapping **T → List<Integer>** if you need to understand the types of fields/methods declared by Base.

This is a **type-variable substitution** process, not an automatic result of a single getGenericSuperclass() call. Similarly, moving from a class to an indirect interface requires traversing both superclasses **and** getGenericInterfaces() of each class/interface.

### Conceptual Pseudocode for Generic Hierarchy Resolution

~~~text
resolve(targetClass, soughtRawType):
  queue = [(targetClass, emptyMapping)]
  while queue not empty:
    (currentType, mapping) = take(queue)
    raw = rawClassOf(currentType)
    localMapping = bind typeParameters(raw) to actualTypeArguments(currentType)
                   after replacing variables via mapping
    if raw == soughtRawType:
       return localMapping or resolved parameterized view
    enqueue raw.getGenericSuperclass() if non-null
    enqueue each raw.getGenericInterfaces()
    propagate mappings through every edge
  return not found
~~~

This is **conceptual pseudocode**, not standalone runnable Java. A complete implementation must handle multiple forms of Type, cycles from interface graphs, owner types of nested classes, bounded type variables, wildcards, generic arrays, raw types, and multiple paths reaching the same interface. You should track a set of visited nodes/mappings and define clear behavior when type argument information is lost due to raw inheritance.

To check **whether a class implements an interface regardless of generic arguments**, you can use **Interface.class.isAssignableFrom(SomeClass.class)**. However, that method only returns a boolean based on raw class relationships; it **does not** return List<Integer> or substitute TypeVariables.

### When Can Concrete Types Not Be Inferred?

With:

~~~java
class Container<T> {}
Container<String> first = new Container<>();
Container<Integer> second = new Container<>();
~~~

Both objects have **getClass() == Container.class**. Type arguments of ordinarily instantiated objects do not exist as two distinct runtime Classes. **Container.class.getGenericSuperclass()** only returns Object; it cannot recover String/Integer from first/second by itself.

A common way to preserve the type in metadata is creating an **anonymous subclass**:

~~~java
Container<String> captured = new Container<String>() {};
Type capturedParent = captured.getClass().getGenericSuperclass();
// capturedParent can be a ParameterizedType representing Container<String>
~~~

This is a fragment using Container from the example; you must import java.lang.reflect.Type. This anonymous subclass has a directly declared superclass **Container<String>**, so String can be read from the **anonymous class's Signature**. It **does not** prove that every ordinary Container<String> object stores String. When creating an anonymous subclass in an unconstrained generic context, metadata may contain a TypeVariable rather than necessarily a concrete Class.

## 7. Raw Types, Wildcards, Nested Types, and Annotations

### Raw Inheritance

If **class Raw extends Base** instead of extends Base<String>, getGenericSuperclass() is usually **Class** Base, not ParameterizedType. You cannot extract an actual type argument that never existed in the declaration. Do not assign Object yourself and claim it was the actual type argument in Signature; **erasure to Object** is a runtime type rule, different from having a **declared generic argument**.

### Wildcards and Nested Generic Arguments

A class can declare a superclass or interface with nested type expressions:

~~~java
interface Source<T> {}
class WildcardSource implements Source<List<? extends Number>> {}
~~~

When querying the direct interface:

~~~java
Type t = WildcardSource.class.getGenericInterfaces()[0];
if (t instanceof ParameterizedType p) {
    Type nested = p.getActualTypeArguments()[0]; // List<? extends Number>
}
~~~

This is a code fragment example: classes Source/WildcardSource must be declared as above. `nested` is typically a ParameterizedType for List, and the type argument inside List is a **WildcardType** with upper bound Number. Never cast `nested` unconditionally to Class, because `nested` could also be a TypeVariable, a WildcardType elsewhere, or a complex generic form.

### Nested/Inner Classes and Owner Types

When a type resides inside a generic outer class, the structure can be Outer<String>.Inner<Integer>. If a subclass extends that type, **ParameterizedType.getOwnerType()** can hold Outer<String>, while the inner's getActualTypeArguments() largely describes Inner's own type parameters. Do not ignore the owner type when you need full generic information.

### Annotations on `extends`/`implements` Positions

If **@Target(ElementType.TYPE_USE)** and **@Retention(RetentionPolicy.RUNTIME)** are present, annotations on the types used in extends/implements declarations can be inspected via:

- **getAnnotatedSuperclass()**: AnnotatedType of the direct superclass.
- **getAnnotatedInterfaces()**: AnnotatedType[] of each direct interface.
- **AnnotatedParameterizedType.getAnnotatedActualTypeArguments()** when drilling down into annotations on the type arguments of a parameterized type.

The difference between **getGenericSuperclass()** and **getAnnotatedSuperclass()** is that the second API retains the TYPE_USE annotation layer. Not every annotation in source is readable at runtime; check `@Retention` and where the annotation is placed.

## 8. Exceptions and Metadata Reliability

When parsing the generic Signature in a `.class` file, Reflection may encounter missing or invalid data (e.g., a class file transformed improperly by a bytecode tool, or a dependency used in a type argument no longer present at runtime). The Java 17 documentation for **getGenericSuperclass** and **getGenericInterfaces** lists:

- **GenericSignatureFormatError**: the generic signature in the class file does not conform to the format specified by the JVM specification.
- **TypeNotPresentException**: a type referenced in the generic superclass/superinterface does not exist or cannot be resolved while reading metadata.
- **MalformedParameterizedTypeException**: a parameterized type in metadata cannot be validly instantiated.

These cases differ from **ClassNotFoundException**, which occurs when code directly loads a class by name. You do not need to catch all three in every simple application, but a scanner handling bytecode from untrusted sources should report the error clearly, distinguishing corrupted metadata from a class that simply declares no interfaces/superclass.

For normally compiled Java classes, generic information resides in the class file's **Signature attribute**. Most runtime execution relies on type erasure; Signature supplies supplementary information for Reflection. If Signature is stripped by a build tool or obfuscator, the class can still load, yet generic metadata may no longer be complete.

### Is `setAccessible(true)` Needed to Read Hierarchy?

**No.** getGenericSuperclass() and getGenericInterfaces() on Class read class/type metadata, not private method invocations or private field reads. JPMS package `opens` rules mainly matter for **deep reflective member access**, not as a prerequisite merely to read generic hierarchy declarations.

## 9. Practical Workflow for Type-Analysis Libraries

Suppose a framework wants to find the type argument of Handler<T> that a user class implements across multiple classes:

1. **Start from the provided runtime class**, but confirm that class actually contains sufficient generic signature data to analyze; an ordinary instance may have lost its argument due to erasure.
2. **Traverse the direct superclass** via getGenericSuperclass() and **direct interfaces** via getGenericInterfaces() at each node.
3. **Check the `Type` kind** before processing: Class, ParameterizedType, TypeVariable, WildcardType, GenericArrayType.
4. **Bind type variables to actual type arguments** when passing through a ParameterizedType and carry the mapping across levels. Do not stop at raw types or rely solely on variable names like T/E/X.
5. **Identify the target raw class** using ParameterizedType.getRawType() or a Class `Type`, instead of comparing getTypeName() strings.
6. **If encountering raw inheritance**, surface explicitly that generic argument data is insufficient; avoid fabricating a concrete type.
7. **Check direct vs. inherited in the right context**: getGenericInterfaces() returns direct interfaces, whereas assignability can hold due to an ancestor level.
8. **Have a strategy for nested owners, wildcards, and arrays** if the framework needs to support full Java type expressions.
9. **Write tests for multiple levels** such as Leaf → Middle<Integer> → Base<List<X>>, an interface extending another interface, raw types, anonymous subclasses, primitives/arrays, and Java module boundaries.

For tasks that only need to know "is this an interface?", **Class.isAssignableFrom** is enough. Build a full generic type resolver only when you specifically need **parameterized arguments** of an abstraction like Repository<Customer> or Handler<List<Order>>.

## 10. Common Mistakes

- **Casting every getGenericSuperclass() to ParameterizedType:** the superclass can be Class or null.
- **Reading getGenericInterfaces() and concluding the class does not implement an interface:** the class may inherit the interface from a superclass; traverse further or use isAssignableFrom to check the raw relationship.
- **Assuming an interface's superclass is Object:** getGenericSuperclass() on an interface returns null, even though Java interfaces are reference types related to Object under other language rules.
- **Assuming Leaf's result is already Base<List<Integer>>:** Leaf.getGenericSuperclass() is only Middle<Integer>; you must substitute X through the Middle level.
- **Using getInterfaces() and expecting generic arguments:** the result is Class<?>[], which does not contain the declared edge's Type arguments.
- **Confusing generic declarations with runtime objects:** a directly constructed Container<String> does not store String as a separate Class.
- **Treating getTypeName() as a stable format to parse:** using Type and its subtypes is better.
- **Forgetting raw inheritance:** raw Base carries no String argument, and erased Object should not be treated as declared actual argument metadata.
- **Skipping nested owners / type-use annotations:** frameworks needing complete metadata should also inspect getOwnerType/getAnnotatedInterfaces/getAnnotatedSuperclass where appropriate.
- **Confusing Class.getTypeParameters with getGenericSuperclass:** the first reads type variables declared by the class itself; the second reads the superclass type on the extends edge.

## 11. Self-Check

**Question 1.** class Child extends Base<String> and implements no interfaces. What do getGenericSuperclass() and getGenericInterfaces() return?

**Answer:** A ParameterizedType describing Base<String>; an empty Type[] array.

**Question 2.** interface Fancy<T> extends Named<List<T>>. What does Fancy.class.getGenericSuperclass() return?

**Answer:** null because Fancy is an interface. Fancy.class.getGenericInterfaces() returns a ParameterizedType describing Named<List<T>>.

**Question 3.** class Leaf extends Middle<Integer>, and Middle<X> extends Base<List<X>>. Can you get Base<List<Integer>> solely from Leaf.class.getGenericSuperclass()?

**Answer:** No. It returns Middle<Integer>; you must continue reading Middle.getGenericSuperclass(), then substitute Integer for X.

**Question 4.** class Raw extends Base. Calling getGenericSuperclass() gives Base.class; can you recover a String type argument?

**Answer:** No. Raw declares raw inheritance and contains no String actual type argument on its extends edge.

**Question 5.** A class inherits an implementation of interface I via its superclass, yet getGenericInterfaces() on that class returns an empty array. Is this a Reflection bug?

**Answer:** No. The API returns **direct** interfaces; indirectly inherited interfaces require traversing ancestors. I.class.isAssignableFrom(ThatClass.class) may still be true.

**Question 6.** What is getGenericSuperclass() of String[].class? And of Object.class and List.class?

**Answer:** String[] has superclass Object; Object and interface List return null.

**Question 7.** Why can `new Box<String>() {}` reveal String whereas ordinary `new Box<String>()` cannot?

**Answer:** The `{}` creates an anonymous subclass whose declaration is `extends Box<String>` in the **anonymous class's** generic Signature. An ordinary Box instance carries only the erased runtime Class Box.

**Takeaway:** **getGenericSuperclass()** reads **one direct superclass** as a Type; **getGenericInterfaces()** reads **direct interfaces** as Type[]. To preserve generic information across multiple levels, you must analyze **ParameterizedType**, **TypeVariable**, and perform **type argument substitution along each inheritance edge**.

### References

- Java SE 17 — Class.getGenericSuperclass/getGenericInterfaces, getAnnotatedSuperclass/getAnnotatedInterfaces: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 — Type: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html
- Java SE 17 — ParameterizedType: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html
- Java SE 17 — TypeVariable: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html
- Java SE 17 — WildcardType: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/WildcardType.html
- Java SE 17 — GenericArrayType: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/GenericArrayType.html
- Java Language Specification 17 — Types, parameterized types and erasure: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html
