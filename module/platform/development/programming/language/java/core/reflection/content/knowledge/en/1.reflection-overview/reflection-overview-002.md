# Distinguishing Compile-Time and Runtime Type Information in Java

## 1. Objectives

After this lesson, you will be able to:
- Distinguish the **static/compile-time type** of an expression from the **actual runtime class** of the object the expression references.
- Predict where Java checks types at compile time and where the JVM must check them at runtime.
- Explain why **overloading** depends on compile-time types while **overriding** depends on the runtime object.
- Choose correctly among **Class literals**, **getClass()**, **instanceof**, and Reflection APIs when observing types.
- Understand Reflection's limitations due to **type erasure**, and exceptions such as generic declaration metadata or array component types.

Context: Java is a statically type-checked language. The compiler and the JVM play different roles, yet both contribute to enforcing type safety. Reflection lets a program query classes, methods, fields, or generic types recorded in metadata at runtime; Reflection does not turn every piece of information the compiler once knew into data retrievable from an object.

## 2. Two Questions About "Type"

Consider the declaration:

~~~java
Animal pet = new Dog();
~~~

This snippet assumes **Dog extends Animal**.

- **Compile-time type of the expression pet:** **Animal**, because that is the declared type of the variable. The compiler uses it to check which methods can be called, which assignments are valid, and which overload is selected.
- **Actual runtime class of the object:** **Dog**, because the object was created with **new Dog()**. For a non-null reference, **pet.getClass()** returns the Class object representing Dog.
- **A reference can change objects:** if later **pet = new Cat()** and Cat also extends Animal, the declared type of pet remains Animal, but the actual class that pet points to at that time is Cat.
- **No object when null:** the variable **Animal pet = null** still has the static type Animal, but **pet.getClass()** will cause a NullPointerException.

| Aspect | Compile Time | Runtime |
| --- | --- | --- |
| Primary question | As what type is this expression **allowed** to be used? | What is the **actual** value/object? |
| Where handled | **javac** (or another Java compiler) | The JVM and runtime libraries |
| Example | **pet** has type Animal | The object in pet is of class Dog |
| Typical decisions | Checking assignments, member access, overload selection | Dispatching overridden instance methods, cast checks, instanceof |
| Observation tools | Variable declarations, method signatures, expression types | **getClass()**, **instanceof**, Reflection |

**Note on terminology:** For primitives like **int**, a static type still exists, but there is no corresponding Java object on which to call **getClass()** directly. It is also important to distinguish "the compile-time type of an expression" from "the runtime class of an object": they are not always measurements of the same kind.

## 3. Runnable Example: Static Type, Overriding, and Overloading

Create the file **TypeStagesDemo.java**:

~~~java
public class TypeStagesDemo {
    static class Animal {
        String voice() {
            return "animal";
        }
    }

    static class Dog extends Animal {
        @Override
        String voice() {
            return "woof";
        }

        void fetch() {
            System.out.println("fetch");
        }
    }

    static String describe(Animal value) {
        return "overload Animal";
    }

    static String describe(Dog value) {
        return "overload Dog";
    }

    public static void main(String[] args) {
        Animal pet = new Dog();

        System.out.println("Runtime class: " + pet.getClass().getSimpleName());
        System.out.println("Override: " + pet.voice());
        System.out.println("Overload: " + describe(pet));
        System.out.println("instanceof Dog: " + (pet instanceof Dog));
        System.out.println("Animal.class matches: " + Animal.class.equals(pet.getClass()));
        System.out.println("Dog.class matches: " + Dog.class.equals(pet.getClass()));

        if (pet instanceof Dog dog) {
            dog.fetch();
            System.out.println("Overload after narrowing: " + describe(dog));
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac TypeStagesDemo.java
java TypeStagesDemo
~~~

Output:

~~~text
Runtime class: Dog
Override: woof
Overload: overload Animal
instanceof Dog: true
Animal.class matches: false
Dog.class matches: true
fetch
Overload after narrowing: overload Dog
~~~

Point-by-point explanation:

1. **pet.getClass().getSimpleName()** reads the actual class, so it is Dog.
2. **pet.voice()** compiles because Animal declares voice(). At runtime, the JVM executes Dog's overridden version.
3. **describe(pet)** selects the overload taking Animal because the static type of pet is Animal, even though the actual object is Dog. Overload selection is primarily a compile-time decision; it is **not** reselected automatically by the argument's runtime class.
4. **pet instanceof Dog** checks the object's actual class; the pattern variable **dog** has type Dog inside the matching branch.
5. After the **instanceof** check, **describe(dog)** selects the overload taking Dog because the static type of the new variable is Dog.
6. **pet.fetch()** will **not compile**: Animal does not declare fetch(). To call it, you need a safely narrowed reference or an appropriate cast.

Do not confuse the ability to call a method with the selection of an implementation: the compiler decides whether a call is valid according to the static type; for an overridable instance method call, the runtime decides which implementation receives the call.

## 4. Which Checks Happen at Which Stage?

### 4.1. Assignments and Member Access

~~~java
Animal a = new Dog();     // Valid: Dog is a subtype of Animal
// Dog d = a;             // Compile error: Animal is not guaranteed to be a Dog
Dog d = (Dog) a;          // Valid at runtime because a points to a Dog
~~~

The compiler allows the downcast **(Dog) a** because, in terms of type relationships, the cast could potentially succeed; the JVM checks the object at runtime. If a points to an Animal object that is not a Dog, the cast throws **ClassCastException**. Casting a reference does not change the object's runtime class.

### 4.2. instanceof and Pattern Matching

~~~java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length()); // 4
}
~~~

**instanceof** checks the actual value at runtime. If the value is null, the result of the type check is false. The pattern variable text is only in scope in branches where the compiler proves the condition matches.

### 4.3. Overloading, Overriding, Fields, and Static Methods

- **Overloading**: determines the method signature from the compile-time types of the arguments and overload resolution rules. For example, **describe(pet)** selects the version taking Animal.
- **Overriding**: for overridable instance methods, the JVM selects the implementation based on the actual class of the receiver. For example, **pet.voice()** runs Dog.voice().
- **Field hiding**: accessing a field through an expression generally depends on the expression's static type; fields do not have polymorphism like instance methods.
- **Static method hiding**: calls via a type/reference are resolved according to static rules; static methods are not overridden. Avoid calling static methods via an instance because it easily causes confusion.

A useful rule to remember: **static types constrain what is allowed to be called; polymorphism determines which overridden version runs**.

## 5. What Types Does Reflection See?

### 5.1. Class Literals and getClass()

There are two ways to obtain a **Class** metadata object with different meanings:

~~~java
Class<?> declared = Animal.class; // Class Animal known from source code
Animal pet = new Dog();
Class<?> actual = pet.getClass(); // Runtime class Dog of the object
~~~

- **Animal.class** is a class literal for Animal, independent of a variable's current value.
- **pet.getClass()** is a method on Object that retrieves the object's actual class and requires pet to be non-null.
- **Class<?>** represents the metadata of a type that has a Class token; use the wildcard when the code does not know the exact type parameter.
- **Class.forName("com.example.Dog")** can find a class by fully qualified name at runtime through the class loading mechanism; the single-parameter version also initializes the class if it has not yet been initialized. It can throw ClassNotFoundException.
- A Class token is identified by **the class name together with its defining class loader**. The same binary name defined by two different class loaders can be two distinct runtime types.

**Do not infer that getClass() can return "the declared type of the variable."** An object does not carry separate information stating that it was stored in an Animal, Object, or generic variable.

### 5.2. Checking Type Relationships with Class

~~~java
Class<?> parent = Animal.class;
Class<?> child = Dog.class;

System.out.println(parent.isAssignableFrom(child)); // true
System.out.println(child.isAssignableFrom(parent)); // false

Animal pet = new Dog();
System.out.println(child.isInstance(pet));           // true
~~~

Meaning of **X.isAssignableFrom(Y)**: a value of type Y can be assigned to a variable of type X according to the appropriate reference type conversion rules. Because Dog extends Animal, **Animal.class.isAssignableFrom(Dog.class)** returns true, while the reverse returns false. For a specific object, **Dog.class.isInstance(pet)** is analogous to checking **pet instanceof Dog** at runtime, and returns false when pet is null.

Additional APIs:
- **targetClass.cast(object)**: checks and casts the object against the Class token; may throw ClassCastException.
- **someClass.asSubclass(Base.class)**: validates a subclass relationship on a Class token; may throw ClassCastException.
- **getSuperclass()**, **getInterfaces()**: inspects direct inheritance/interface relationships in metadata.
- **getDeclaredMethods()**, **getDeclaredFields()**: inspects members declared directly in the class; unlike **getMethods()**, which considers inherited public methods according to API rules.

### 5.3. Example of Inspecting a Declared Member

Create the file **ReflectionInspectDemo.java**:

~~~java
import java.lang.reflect.Method;

public class ReflectionInspectDemo {
    static class Base {
        public void start() {}
    }

    static class Worker extends Base {
        private void process() {}
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Worker.class;
        Method local = type.getDeclaredMethod("process");
        Method inherited = type.getMethod("start");

        System.out.println(type.getSimpleName());
        System.out.println(local.getDeclaringClass().getSimpleName());
        System.out.println(inherited.getDeclaringClass().getSimpleName());
        System.out.println(type.getSuperclass().getSimpleName());
    }
}
~~~

~~~bash
javac ReflectionInspectDemo.java
java ReflectionInspectDemo
~~~

Deterministic output:

~~~text
Worker
Worker
Base
Base
~~~

Here **getDeclaredMethod("process")** finds the private method declared in Worker. **getMethod("start")** finds the public method inherited from Base. *Finding metadata* does not mean having permission to *access or invoke* that member; reflecting into private members is still subject to access control and module restrictions of the Java Platform Module System. Do not assume **setAccessible(true)** will succeed.

## 6. Generics: Which Information Is Erased and Which Remains?

Java generally compiles generics using **type erasure**. A parameterized type such as **List\<String>** helps the compiler enforce type safety when writing code, but an ArrayList object at runtime does not carry a String element tag of its own.

Valid compilable example:

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();

System.out.println(names.getClass().equals(numbers.getClass())); // true
System.out.println(names.getClass().getName()); // java.util.ArrayList
~~~

**List\<String>** and **List\<Integer>** differ at the compile-time type-checking layer, but the two **new ArrayList<>()** objects share the same runtime class **java.util.ArrayList**.

Limitations to remember:
- **List\<String>.class** is invalid; class literals work with **List.class** (raw type) or another appropriate Class token.
- For a variable `Object value`, `value instanceof List<String>` is invalid because the check requires an unsafe (unchecked) conversion. Since Java 16, for a variable `List<String> value`, `value instanceof List<String>` and `value instanceof ArrayList<String>` can be valid because the static type already provides enough information to check without an unchecked conversion. `value instanceof List<?>` remains the appropriate check when you only need to know whether an object is a list; it does not check the type of each element at runtime.
- **getClass()** of an ArrayList cannot infer on its own that an external variable was declared as List\<String>.
- There is no guarantee that a list at runtime always contains elements of the type written in source code: raw types, unchecked conversions, or Reflection can cause heap pollution; the compiler usually emits warnings in such cases.

**However, "type erasure" does not mean every trace of generics disappears.** Metadata of *declarations* such as fields, methods, superclasses, or interfaces can retain a generic signature in the class file and be read through **java.lang.reflect.Type** (for example, ParameterizedType, TypeVariable, WildcardType). That is different from each instance having a separate Class object for each type argument.

### Example: getType() vs. getGenericType()

Create the file **GenericMetadataDemo.java**:

~~~java
import java.lang.reflect.Field;
import java.util.List;

public class GenericMetadataDemo {
    private List<String> labels;

    public static void main(String[] args) throws Exception {
        Field field = GenericMetadataDemo.class.getDeclaredField("labels");

        System.out.println(field.getType().getTypeName());
        System.out.println(field.getGenericType().getTypeName());
    }
}
~~~

~~~bash
javac GenericMetadataDemo.java
java GenericMetadataDemo
~~~

Output:

~~~text
java.util.List
java.util.List<java.lang.String>
~~~

**getType()** returns the Class for the erased type of the field. **getGenericType()** reads the declared type from the generic signature when metadata is available. If a declaration uses a type variable **T**, Reflection may return a **TypeVariable**; finding the concrete type argument across a generic hierarchy often requires further analyzing the Type structure, and in some cases it is impossible to recover the type a caller originally used.

## 7. Arrays and Primitives: Two Easily Confused Exceptions

### 7.1. Runtime Component Type of Arrays

Arrays are objects that have a runtime component type. Because reference arrays in Java are **covariant**, the following assignment is valid at compile time while writes are checked at runtime:

Create the file **ArrayRuntimeTypeDemo.java**:

~~~java
public class ArrayRuntimeTypeDemo {
    public static void main(String[] args) {
        Object[] items = new String[1];

        System.out.println(items.getClass().getComponentType().getName());

        try {
            items[0] = 42;
        } catch (ArrayStoreException ex) {
            System.out.println("ArrayStoreException");
        }
    }
}
~~~

~~~bash
javac ArrayRuntimeTypeDemo.java
java ArrayRuntimeTypeDemo
~~~

Output:

~~~text
java.lang.String
ArrayStoreException
~~~

The variable items has the static type **Object[]**, but the actual object is **String[]**. The JVM does not allow storing an Integer into a String array, so it throws **ArrayStoreException**. This differs from erased generic lists: the JVM genuinely knows the runtime component type of an array.

### 7.2. Primitives and Wrappers

~~~java
Class<?> primitive = int.class;
Class<?> wrapper = Integer.class;

System.out.println(primitive.isPrimitive()); // true
System.out.println(wrapper.isPrimitive());   // false
System.out.println(primitive.equals(Integer.TYPE)); // true
~~~

**int.class** represents metadata for the primitive int, but an **int** value is not an object and has no **getClass()** method. When assigning an int to Object, Java performs boxing into an Integer; if you later call getClass() on the boxed object, you get **Integer.class**, not **int.class**. Do not mix up primitives and wrappers when looking up constructors or methods by Reflection signature.

## 8. Distinguishing What Can Be Checked vs. What Can Be Queried

| Practical Question | What to Use? | What to Watch Out For |
| --- | --- | --- |
| Which members is a variable allowed to call? | Declared type and compiler rules | The object may belong to a subclass with richer members |
| Which class does a non-null object currently belong to? | **obj.getClass()** | Does not return the variable's declared type |
| Is a value compatible with a subtype? | **instanceof**, **Class.isInstance()** | null does not match |
| Does class A accept values of type B? | **A.isAssignableFrom(B)** | Easy to reverse the order |
| Obtain a Class token when the type is known in source? | **SomeType.class** | Does not reflect the current object |
| Find a generic field signature? | **Field.getGenericType()** | Metadata belongs to the declaration; does not prove instance elements |
| Find the runtime component type of an array? | **array.getClass().getComponentType()** | Primitive arrays and reference arrays differ |
| Look up a method at runtime? | **getMethod/getDeclaredMethod** | Differ on inherited/public; access is still controlled |

### Guidance When Writing APIs Using Reflection

If the logic already knows the types and behaviors to call in advance, prefer normal interfaces, generics, and polymorphism: the compiler will check them for you. Reflection is better suited for inspecting schemas/metadata or frameworks that need to discover classes, fields, and methods at runtime. When using Reflection:

1. Identify whether you are handling a **Class**, a **Type**, a declared **Field/Method**, or a specific **instance**.
2. Distinguish questions about an **assignable relationship** from questions about **whether the actual class is strictly equal to class X**. **Animal.class.equals(pet.getClass())** may be false while **pet instanceof Animal** is still true.
3. Pay attention to **class loaders**, **null**, **erasure**, **access control**, and checked exceptions when looking up by name.
4. Do not rely on the result order of **getDeclaredMethods()**/**getDeclaredFields()**: the API does not guarantee a fixed order.
5. Check exact parameter signatures when using **getMethod(name, parameterTypes...)**; generic arguments in source code are usually erased.

## 9. Common Misconceptions

**"If an Animal variable points to a Dog, the compiler allows calling every Dog method."** False. The compiler checks against the variable's static type; use polymorphism through methods declared in Animal, or narrow with a check if you truly need Dog members.

**"Both overriding and overloading are selected by runtime class."** False. Overloading selects the signature at compile time; overriding dispatches by the receiver at runtime.

**"Casting an object to Animal turns the object into an Animal."** False. A cast changes how the expression is typed; a Dog object still has runtime class Dog if the cast is valid.

**"Reflection always recovers List\<String> from an ArrayList instance."** False. The generic signature of a declaration can sometimes be read, but that is not a type argument tag present on every object.

**"If Class.getName() matches, two Class tokens are guaranteed to be the same type."** False in situations with multiple defining class loaders.

**"getDeclaredMethods() returns all public methods including inherited ones."** False; you must understand the difference between declared vs. public/inherited.

## 10. Self-Check

Given the declaration **Animal a = new Dog()** where Dog extends Animal, Dog overrides voice(), and Dog adds fetch():

1. What is the static type of a? What is the runtime class?
2. Why does **a.voice()** run Dog's version while **a.fetch()** does not compile?
3. Given two overloads **f(Animal)** and **f(Dog)**, which version does **f(a)** call?
4. What does **Animal.class.isAssignableFrom(Dog.class)** return? What does **Dog.class.isAssignableFrom(Animal.class)** return?
5. If **List\<String>** and **List\<Integer>** are both created with ArrayList, does getClass() distinguish the type arguments?
6. Why is the assignment **Object[] values = new String[1]** valid while writing an Integer into values can throw an error?

Answers: (1) Animal and Dog. (2) The compiler sees voice on Animal and the JVM dispatches the override; fetch is not part of the API of static type Animal. (3) f(Animal). (4) true then false. (5) No, because of erasure and the same ArrayList class. (6) Arrays are covariant, but the JVM checks the runtime component type, resulting in ArrayStoreException.

## 11. Summary

In Java, **compile-time type information** is used to prove code validity and determine many static choices; **runtime type information** describes the actual value/object and supports polymorphic dispatch, dynamic type checks, and Reflection. **Class<?>** provides metadata about a runtime class or a directly named type, while **Type** additionally represents certain generic declarations. Understanding this boundary helps you predict compile errors, ClassCastException, ArrayStoreException, and the limits of Reflection-based libraries.
