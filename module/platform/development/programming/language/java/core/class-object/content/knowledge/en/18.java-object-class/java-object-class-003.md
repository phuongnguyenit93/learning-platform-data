# Distinguishing Between a Class, an Ordinary Object, and a `Class` Object in Java

Java has three related but **not identical** concepts:

1. **Class** is the type definition in source code, such as `class Student { ... }`. A class describes constructors, instance fields, methods, and the rules for its instances.
2. **Ordinary object (instance)** is a runtime entity, such as an object created by `new Student("Mai")`. It has identity and can have instance state.
3. **`java.lang.Class<?>` object** is a **metadata object about a runtime type**. `Student.class` returns a Class object representing the Student type; it is **not** a Student instance.

~~~java
class Student {
    String name;
}

// Inside a method:
Student student = new Student();      // Student instance.
Class<Student> type = Student.class;   // Class object describing Student.
Class<?> runtime = student.getClass(); // Class object of the actual runtime class.
~~~

`Student.class` does not invoke a constructor, does not create a Student instance, and is not the bytecode file on disk. A Class object lets the JVM/framework/caller ask **what this type is named, what it inherits from, and which members it declares**, whereas a Student instance is an object with a concrete `name` field.

This article belongs to **Java Core — Class & Object / The Object Class**, using **Java 17+**. Standalone programs list the filename, `javac`/`java` commands, and stdout. Isolated code snippets are illustrative and do not necessarily run standalone.

## 1. Learning Objectives

You will be able to:

- Distinguish between a class declaration, an instance, and a metadata Class object.
- Distinguish between the `class` keyword, the `Class` API class, and the `.class` class literal.
- Understand the role of `java.lang.Object` and the `Class extends Object` relationship.
- Read `getClass()` based on the actual runtime object rather than the declared reference type.
- Know why multiple instances of the same runtime class share a single Class object within the same defining-loader scope.
- Distinguish between `Object.class`, `Class.class`, `String.class`, and a String instance.
- Correctly use `Class<T>`, `Class<?>`, `isInstance`, `isAssignableFrom`, and `cast`.
- Know Class tokens for primitives, `void`, arrays, interfaces, records, and enums.
- Understand when `Class.forName` triggers initialization while `.class` does not.
- Separate Field/Method/Constructor metadata from instance state values.
- Know Reflection APIs and limitations regarding access, type erasure, and class-loader identity.
- Accurately predict Java code and avoid confusion when using reflection.

## 2. The Three-Level Model

Suppose:

~~~java
class Person {
    String name;
}

Person mai = new Person();
Person an = new Person();

Class<Person> type = Person.class;
~~~

Model:

~~~text
TYPE DECLARATION (source)
     class Person { String name; }
                  |
                  v
RUNTIME METADATA FOR TYPE PERSON
     one Class object: Person.class
                  ^
                  |
          getClass() from instances
                  |
     +------------+-------------+
     |                          |
 Person object #1           Person object #2
 (mai, own name)            (an, own name)
~~~

Two Person instances can exist while sharing the same runtime Class object. Conversely, **a Class object does not contain a default list of all Person instances**. Java has no `Person.class.getAllInstances()` API.

### What Is Shared?

- Class metadata: the runtime type description is shared.
- Instance fields: each ordinary instance has its own state according to the constructor/class design.
- Static fields: data tied to the runtime class, not a copy for each ordinary object.
- Class object identity: tied to the runtime type itself, taking the defining class loader into account.

Class metadata is different from a “storage container holding all instance field values”.

## 3. How `class`, `Class`, and `.class` Differ

| Expression or declaration | Meaning |
| --- | --- |
| `class Book {}` | Java keyword declaring a class |
| `java.lang.Class` | API class representing runtime types |
| `Class<Book>` | Reference type to a Class object describing Book |
| `Book.class` | Class literal expression |
| `new Book()` | Creates an ordinary Book object |
| `book.getClass()` | Gets the actual runtime Class object of book |
| `Class.forName("pkg.Book")` | Finds/loads a runtime class by binary name |
| `Object.class` | Class object describing the Object type |

Java is case-sensitive. `Class` is a library class name, not a keyword. `Book.class` is not a method named class invoked on Book.

### A `.class` File Differs from a Class Literal

- `Book.java`: source file.
- `Book.class` on the filesystem: bytecode file.
- `Book.class` **in a Java expression**: Class object value.

Although written the same way, a class literal does not open a bytecode file every time it is evaluated. A runtime class can be defined by a custom loader from bytes that do not reside in a traditional file.

## 4. `Object` Is the Root Superclass, and `Class` Is Also an Object

`java.lang.Object` is the root superclass of ordinary classes. `java.lang.Class` is a real class that inherits from Object.

Therefore:

~~~java
Object value = String.class;
System.out.println(value.getClass() == Class.class);
~~~

prints `true`.

However:

~~~java
Object value = "Java";
System.out.println(value.getClass() == String.class);
~~~

is also true, because here `value` is a **String instance**.

Two objects at two levels:

~~~text
"Java"          --> ordinary String object
String.class    --> Class object describing String
Class.class     --> Class object describing java.lang.Class itself
~~~

Notably: `Class.class.getClass() == Class.class` is true. There is no infinite chain of “Class of Class of Class”.

## 5. Runnable Example: Ordinary Objects and a Class Object

Create **`ThreeLevelsDemo.java`**:

~~~java
public class ThreeLevelsDemo {
    static final class Student {
        private final String name;

        Student(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        Student mai = new Student("Mai");
        Student an = new Student("An");

        Class<Student> type = Student.class;
        Class<?> fromMai = mai.getClass();
        Class<?> fromAn = an.getClass();

        System.out.println("mai=" + mai.name());
        System.out.println("an=" + an.name());
        System.out.println("same instance=" + (mai == an));
        System.out.println("same Class=" + (fromMai == fromAn));
        System.out.println("literal matches=" + (type == fromMai));
        System.out.println("type=" + type.getSimpleName());
        System.out.println("Class itself=" +
                (type.getClass() == Class.class));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ThreeLevelsDemo.java
java ThreeLevelsDemo
~~~

Stdout:

~~~text
mai=Mai
an=An
same instance=false
same Class=true
literal matches=true
type=Student
Class itself=true
~~~

Calling `new Student(...)` twice creates two objects; having the same runtime type Student causes both `getClass()` calls to return the same Class token. `Student.class` also yields that exact token. However, `type.getClass()` gets the runtime class of the **metadata object**, which is `java.lang.Class`.

## 6. `Object.class` and `Class.class` Ask About Two Different Types

`Object.class` represents the **runtime type Object**; it does not “contain every object”.

`Class.class` represents the **runtime type Class**. It is itself also a Class instance.

Create **`ObjectAndClassDemo.java`**:

~~~java
public class ObjectAndClassDemo {
    public static void main(String[] args) {
        Object ordinary = "Java";
        Object metadata = String.class;

        System.out.println("ordinary type=" +
                ordinary.getClass().getSimpleName());
        System.out.println("metadata type=" +
                metadata.getClass().getSimpleName());
        System.out.println("String type=" +
                String.class.getSimpleName());
        System.out.println("Class type=" +
                Class.class.getSimpleName());

        System.out.println("Class parent is Object=" +
                (Class.class.getSuperclass() == Object.class));
        System.out.println("Object parent null=" +
                (Object.class.getSuperclass() == null));
        System.out.println("Class self=" +
                (Class.class.getClass() == Class.class));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ObjectAndClassDemo.java
java ObjectAndClassDemo
~~~

Stdout:

~~~text
ordinary type=String
metadata type=Class
String type=String
Class type=Class
Class parent is Object=true
Object parent null=true
Class self=true
~~~

A Class token is also an Object because Class extends Object; you cannot say a token is a String instance just because the token describes String.

## 7. `getClass()` Returns Metadata of the *Actual Object*, Not the Variable's Type

Given `Animal animal = new Dog();` (assuming `Dog extends Animal`), `animal.getClass()` returns `Dog.class`: it does not return `Animal.class` just because the variable has type Animal. `getClass()` is final, so subclasses cannot override it to fake different metadata.

Two different checks:

- `object.getClass() == Animal.class` — true when the runtime class is **exactly** Animal; a null receiver causes an NPE.
- `object instanceof Animal` — accepts subclasses and returns false for null.

This is the foundation for reading the `Class` object. The dedicated article on `getClass()` focuses on static-vs-runtime type; this article shifts focus to **the `Class` metadata object having a different identity from ordinary instances** and how to leverage it.

## 8. Complete Program: Two Instances but One Class Token

Save the file **`ClassTokenAndInstancesDemo.java`**:

~~~java
public class ClassTokenAndInstancesDemo {
    static final class Student {
        private final String name;

        Student(String name) {
            this.name = name;
        }
    }

    public static void main(String[] args) {
        Student first = new Student("Lan");
        Student second = new Student("Mai");
        Class<?> type = first.getClass();

        System.out.println("same instances=" + (first == second));
        System.out.println("same metadata=" + (type == second.getClass()));
        System.out.println("literal matches=" + (type == Student.class));
        System.out.println("first is Student=" + type.isInstance(first));
        System.out.println("token is Student=" + type.isInstance(type));
        System.out.println("token class=" + type.getClass().getSimpleName());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClassTokenAndInstancesDemo.java
java ClassTokenAndInstancesDemo
~~~

**Stdout:**

~~~text
same instances=false
same metadata=true
literal matches=true
first is Student=true
token is Student=false
token class=Class
~~~

Calling `new Student(...)` twice creates **two ordinary objects** with different identities; both return the same `Class` token for Student within the same runtime definition. `type` itself is an object of class `java.lang.Class`, **not a Student instance**. `Class.isInstance(obj)` asks whether an object belongs to the type described by the token, not whether the token holds Student's fields.

## 9. A Class Token Is Not an Instance of the Described Type

If:

~~~java
Class<String> type = String.class;
Object ordinary = "hello";
~~~

then `type` is a Class instance, **not a String instance**.

Create **`ClassTokenNotValueDemo.java`**:

~~~java
public class ClassTokenNotValueDemo {
    public static void main(String[] args) {
        Class<String> type = String.class;
        Object ordinary = "hello";

        System.out.println("token is Class=" +
                (type instanceof Class));
        System.out.println("token is Object=" +
                (type instanceof Object));
        System.out.println("ordinary is String=" +
                type.isInstance(ordinary));
        System.out.println("token is String=" +
                type.isInstance(type));
        System.out.println("token is Class=" +
                Class.class.isInstance(type));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClassTokenNotValueDemo.java
java ClassTokenNotValueDemo
~~~

Stdout:

~~~text
token is Class=true
token is Object=true
ordinary is String=true
token is String=false
token is Class=true
~~~

`String.class.isInstance(type)` is false because the type token itself is not a String. `Class.class.isInstance(type)` is true because the token is a Class object.

## 10. Three Ways to Obtain a Class Object

| Syntax | When to use | Ordinary instance needed? |
| --- | --- | --- |
| `SomeType.class` | Type is known at compile time | Not needed |
| `object.getClass()` | Actual runtime class is needed | Needs non-null object |
| `Class.forName(name)` | Runtime type name comes from configuration/plugin | No direct instance needed |

If all of them target the same runtime class identity, they can return **the same Class object**. However, their initialization semantics differ:

- A class literal **does not by itself require** initialization of the described class.
- `getClass()` is invoked on an already existing object.
- `Class.forName(String)` can cause class initialization.
- The overload `Class.forName(name, false, loader)` does not require initializing the class.

Do not substitute one approach for another when class initialization side effects matter.

## 11. Generic `Class<T>` and Wildcard `Class<?>`

`java.lang.Class` is a generic class. Example:

~~~java
Class<String> textType = String.class;
Class<Integer> numberType = Integer.class;
Class<?> unknownType = new java.util.ArrayList<>().getClass();
~~~

`Class<String>` states that the token represents the String type. `Class<?>` states a token of a type not specifically known at compile time.

### API Using a Class Token

~~~java
static <T> T convert(Class<T> target, Object input) {
    return target.cast(input);
}
~~~

When the caller passes `String.class`, the compiler knows the return type T is String. You should not use raw `Class` if `Class<?>` or `Class<T>` expresses the intent more clearly.

### Limitations

Class<T> does not represent all parameterized generic types: there is no `List<String>.class` literal. When frameworks need generic type declarations, they can use `java.lang.reflect.Type` and related APIs, whereas an ordinary object's `getClass()` does not by itself expose all type arguments due to erasure.

## 12. `Class.isInstance`, `Class.cast`, and `isAssignableFrom`

**`SomeType.class.isInstance(object)`** checks whether an object can be regarded as an instance of SomeType.

**`SomeType.class.cast(object)`** performs a runtime checked cast, which can throw `ClassCastException`. `cast(null)` returns null; `isInstance(null)` is false.

**`A.class.isAssignableFrom(B.class)`** asks: can a value of type B be assigned to a variable of type A? A is the **target**, and B is the source.

If Dog extends Animal:

~~~java
Animal.class.isAssignableFrom(Dog.class) // true.
Dog.class.isAssignableFrom(Animal.class) // false.
Object.class.isAssignableFrom(Dog.class) // true.
~~~

### Runnable Example

Create **`ClassChecksDemo.java`**:

~~~java
public class ClassChecksDemo {
    static class Animal {}
    static final class Dog extends Animal {}

    static <T> T checked(Class<T> expected, Object value) {
        if (!expected.isInstance(value)) {
            throw new IllegalArgumentException(
                    "expected " + expected.getSimpleName());
        }
        return expected.cast(value);
    }

    public static void main(String[] args) {
        Animal animal = new Dog();

        System.out.println("Animal <- Dog=" +
                Animal.class.isAssignableFrom(Dog.class));
        System.out.println("Dog <- Animal=" +
                Dog.class.isAssignableFrom(Animal.class));
        System.out.println("Dog instance=" +
                Dog.class.isInstance(animal));

        Dog dog = checked(Dog.class, animal);
        System.out.println("cast type=" +
                dog.getClass().getSimpleName());

        try {
            checked(String.class, animal);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClassChecksDemo.java
java ClassChecksDemo
~~~

Stdout:

~~~text
Animal <- Dog=true
Dog <- Animal=false
Dog instance=true
cast type=Dog
rejected=expected String
~~~

`isAssignableFrom` compares two runtime type tokens; `isInstance` asks about an object; `cast` produces an appropriately typed reference, **without creating a new object**.

## 13. Primitive Types Have Class Tokens and Are Not Object Instances

Java has eight primitive types: `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, and `double`. Primitive values are not ordinary objects, yet all have Class tokens:

~~~java
Class<?> a = int.class;
Class<?> b = boolean.class;
Class<?> c = void.class;
~~~

`void.class` is also a special Class token. `Class.isPrimitive()` returns true for primitives and void according to the API.

### Wrapper Classes Do Not Have the Same Type as Primitives

~~~java
int.class == Integer.class // false.
boolean.class == Boolean.class // false.
~~~

Autoboxing allows an `int` value to be converted to an Integer object in certain contexts, but does not make the two Class objects identical.

~~~java
int number = 7;
// number.getClass(); // Error: a primitive does not have instance methods.
Object boxed = number;
System.out.println(boxed.getClass() == Integer.class); // true.
~~~

## 14. Arrays Also Have Class Metadata

~~~java
int[] numbers = {1, 2};
String[][] matrix = new String[2][3];
~~~

Arrays are objects and have runtime Class tokens:

~~~java
numbers.getClass() == int[].class
matrix.getClass() == String[][].class
~~~

Methods:

- `int[].class.isArray()` → true.
- `int[].class.getComponentType() == int.class` → true.
- `String[][].class.getComponentType() == String[].class` → true.
- `int[].class.getSuperclass() == Object.class` → true.

Array classes implement Cloneable and Serializable according to Java semantics. There is no need for the user to declare a class named `int[]` in Java syntax.

## 15. An Interface Also Has a Class Token

~~~java
interface Action {
    void run();
}
~~~

`Action.class.isInterface()` is true. However, you cannot call `new Action()` directly. An implementing class or a lambda (when Action is a functional interface) creates an object for which `Action.class.isInstance(instance)` can be true.

**`Action.class` itself is not an Action instance**; it is a Class instance representing the Action type.

For interface Class tokens, `getSuperclass()` returns null. The fact that objects implementing interfaces are Objects does not give an interface a direct superclass of Object according to the `getSuperclass` API.

## 16. Runnable Example: Primitive, Array, Interface

Create **`SpecialTypesDemo.java`**:

~~~java
public class SpecialTypesDemo {
    interface Action {
        void run();
    }

    public static void main(String[] args) {
        Object boxed = 7;
        int[] values = {1, 2};
        Action action = () -> {};

        System.out.println("int primitive=" + int.class.isPrimitive());
        System.out.println("void primitive=" + void.class.isPrimitive());
        System.out.println("int != Integer=" + (int.class != Integer.class));
        System.out.println("boxed Integer=" +
                (boxed.getClass() == Integer.class));
        System.out.println("int[] array=" + int[].class.isArray());
        System.out.println("array token=" +
                (values.getClass() == int[].class));
        System.out.println("component int=" +
                (int[].class.getComponentType() == int.class));
        System.out.println("matrix component=" +
                (String[][].class.getComponentType() == String[].class));
        System.out.println("Action interface=" +
                Action.class.isInterface());
        System.out.println("Action instance=" +
                Action.class.isInstance(action));
    }
}
~~~

~~~bash
javac -encoding UTF-8 SpecialTypesDemo.java
java SpecialTypesDemo
~~~

Stdout:

~~~text
int primitive=true
void primitive=true
int != Integer=true
boxed Integer=true
int[] array=true
array token=true
component int=true
matrix component=true
Action interface=true
Action instance=true
~~~

Do not hardcode the runtime class name of a lambda object: that can be a generated name that varies by implementation, whereas interface-compatibility checking is the semantics to learn.

## 17. `getSuperclass()` and `getInterfaces()`

`Class.getSuperclass()` returns the direct superclass (or null per the API for Object, interfaces, and primitives/void). `getInterfaces()` returns Class tokens for the interfaces directly declared by the class/interface according to its contract.

Example:

~~~java
interface Named {
    String name();
}

class Animal {}

class Dog extends Animal implements Named {
    public String name() {
        return "Dog";
    }
}
~~~

`Dog.class.getSuperclass() == Animal.class` is true. `Animal.class.getSuperclass() == Object.class` is true. `Object.class.getSuperclass() == null` is true.

### Runnable Example

Create **`HierarchyMetadataDemo.java`**:

~~~java
public class HierarchyMetadataDemo {
    interface Named {
        String name();
    }

    static class Animal {}

    static final class Dog extends Animal implements Named {
        @Override
        public String name() {
            return "Dog";
        }
    }

    public static void main(String[] args) {
        System.out.println("Dog parent=" +
                Dog.class.getSuperclass().getSimpleName());
        System.out.println("Animal parent=" +
                Animal.class.getSuperclass().getSimpleName());
        System.out.println("Object parent=" +
                Object.class.getSuperclass());
        System.out.println("Named parent=" +
                Named.class.getSuperclass());
        System.out.println("Dog direct interfaces=" +
                Dog.class.getInterfaces().length);
    }
}
~~~

~~~bash
javac -encoding UTF-8 HierarchyMetadataDemo.java
java HierarchyMetadataDemo
~~~

Stdout:

~~~text
Dog parent=Animal
Animal parent=Object
Object parent=null
Named parent=null
Dog direct interfaces=1
~~~

Do not treat `getSuperclass()` as “all ancestors” or `getInterfaces()` as “all indirect interfaces” in a flat list.

## 18. Class Metadata Is Information About Declarations

`Class<?>` holds/exposes **type descriptions**, for example:

- Name, package, superclass/interfaces.
- Modifiers and annotations (depending on retention).
- Declared fields, types of fields.
- Declared methods, parameter/return types.
- Constructors, record components, sealed status.

However, a Class object **does not directly contain the individual values of each instance field**. For example, Person #1 has name Mai and Person #2 has name An; Person.class is still a single token describing the `name` field, not a single name.

### Distinguishing a Reflection Field from a Field Value

~~~java
java.lang.reflect.Field f =
        Person.class.getDeclaredField("name");
~~~

`f` is a metadata descriptor for the name declaration. To read `f.get(person)`, you need a compatible ordinary instance target, appropriate access permissions, and error handling. Private fields do not automatically become readable just because their metadata was found.

## 19. Commonly Used Reflection APIs

| API | What information does it return? |
| --- | --- |
| `getDeclaredFields()` | Directly declared fields, including non-public ones |
| `getFields()` | Applicable public fields, including inherited public ones |
| `getDeclaredMethods()` | Directly declared methods, including non-public ones |
| `getMethods()` | Applicable public methods, including inherited methods |
| `getDeclaredConstructors()` | Directly declared constructors |
| `getConstructor(...)` | Looks up a public constructor by parameter types |
| `getDeclaredConstructor(...)` | Looks up a declared constructor |
| `getModifiers()` | Modifier flags read via the Modifier API |
| `getName()` | Binary/runtime name |
| `getSimpleName()` | Simple name, which can be empty |
| `getCanonicalName()` | Canonical name, which can be null |
| `getTypeName()` | Display type name, useful for arrays |
| `isInterface()/isArray()/isPrimitive()` | Checks the type kind |
| `isEnum()/isRecord()/isSealed()` | Runtime type properties (Java 17) |

**Note:** The `getDeclared...` APIs differ from `get...` mainly in direct scope, inherited members, and visibility. Do not infer that merely calling `getDeclaredField` grants permission to break private state.

## 20. Runnable Example: Class Metadata vs. Field Value

Create **`ReflectionMetadataDemo.java`**:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class ReflectionMetadataDemo {
    public static final class User {
        private final String name;

        public User(String name) {
            this.name = name;
        }

        public String name() {
            return name;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Class<User> type = User.class;

        Field field = type.getDeclaredField("name");
        Method method = type.getMethod("name");

        System.out.println("class=" + type.getSimpleName());
        System.out.println("field=" + field.getName());
        System.out.println("field type=" +
                field.getType().getSimpleName());
        System.out.println("field private=" +
                Modifier.isPrivate(field.getModifiers()));
        System.out.println("method return=" +
                method.getReturnType().getSimpleName());
        System.out.println("constructor count=" +
                type.getDeclaredConstructors().length);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReflectionMetadataDemo.java
java ReflectionMetadataDemo
~~~

Stdout:

~~~text
class=User
field=name
field type=String
field private=true
method return=String
constructor count=1
~~~

The program **creates no ordinary User instance at all**; it only inspects declarations through the Class object. This is proof that Class metadata is not synonymous with an object's state.

## 21. Runnable Example: One Field Declaration, Two Instance Values

Create **`ReflectionValuesDemo.java`**:

~~~java
import java.lang.reflect.Field;

public class ReflectionValuesDemo {
    public static final class Meter {
        public int count = 5;
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Meter first = new Meter();
        Meter second = new Meter();
        second.count = 9;

        Field descriptor = Meter.class.getField("count");

        System.out.println("field=" + descriptor.getName());
        System.out.println("first=" + descriptor.getInt(first));
        System.out.println("second=" + descriptor.getInt(second));
        System.out.println("same Class=" +
                (first.getClass() == second.getClass()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReflectionValuesDemo.java
java ReflectionValuesDemo
~~~

Stdout:

~~~text
field=count
first=5
second=9
same Class=true
~~~

The same `count` descriptor applies, yet the values reside on each Meter object. A public field is used here so reflection is easy to demonstrate; production classes typically encapsulate state in private fields and meaningful methods.

## 22. A Class Token Is Not a Constructor, but It Is Used to Look Up Constructors

`Person.class` does not create a Person instance. Normal instance creation:

~~~java
Person person = new Person("Mai");
~~~

If reflection is needed:

~~~java
Person person = Person.class
        .getConstructor(String.class)
        .newInstance("Mai");
~~~

This requires a matching public constructor(String) and requires handling reflection exceptions. `Class.newInstance()` is deprecated; prefer the Constructor API or a typed constructor/factory.

### Runnable Example

Create **`ReflectiveConstructorDemo.java`**:

~~~java
public class ReflectiveConstructorDemo {
    public static final class Person {
        private final String name;

        public Person(String name) {
            this.name = name;
        }

        public String name() {
            return name;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Class<Person> token = Person.class;

        Person first = new Person("Mai");
        Person second = token.getConstructor(String.class)
                .newInstance("An");

        System.out.println("first=" + first.name());
        System.out.println("second=" + second.name());
        System.out.println("same instance=" + (first == second));
        System.out.println("same type=" +
                (first.getClass() == second.getClass()));
        System.out.println("token matches=" +
                (token == second.getClass()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReflectiveConstructorDemo.java
java ReflectiveConstructorDemo
~~~

Stdout:

~~~text
first=Mai
second=An
same instance=false
same type=true
token matches=true
~~~

Creating an object via reflection or directly through a constructor both yield ordinary Person instances; the Class token still only represents the runtime Person type.

## 23. Class Loading and Class Initialization Differ from Obtaining a Class Token

The concepts:

1. **Loading/definition:** The JVM defines a representation for the runtime type from bytecode.
2. **Linking:** Verification, preparation, and resolution according to VM rules.
3. **Initialization:** Java executes static field initializers and static initializer blocks according to the rules.
4. **Ordinary instance creation:** Constructor and instance initialization when creating an object.

`SomeType.class` obtains the Class token **without by itself forcing initialization of SomeType**.

`Class.forName(String)` normally requires initializing the class per the API semantics. The overload `Class.forName(name, false, loader)` allows not initializing immediately.

### Runnable Example

Create **`ClassInitializationDemo.java`**:

~~~java
public class ClassInitializationDemo {
    static final class Plugin {
        static int version = 17;

        static {
            System.out.println("Plugin initialized");
        }
    }

    public static void main(String[] args)
            throws ClassNotFoundException {
        System.out.println("begin");

        Class<?> literal = Plugin.class;
        System.out.println("literal=" + literal.getSimpleName());

        Class<?> loaded = Class.forName(
                Plugin.class.getName(),
                false,
                Plugin.class.getClassLoader());
        System.out.println("loaded same=" + (literal == loaded));

        Class<?> initialized = Class.forName(Plugin.class.getName());
        System.out.println("initialized same=" +
                (literal == initialized));
        System.out.println("version=" + Plugin.version);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClassInitializationDemo.java
java ClassInitializationDemo
~~~

Stdout:

~~~text
begin
literal=Plugin
loaded same=true
Plugin initialized
initialized same=true
version=17
~~~

The static block runs only when Plugin is initialized. A class literal and `forName(..., false, ...)` do not by themselves require initialization. `forName(String)` is the trigger in the demo.

Do not confuse “class loaded” with “class initialized” or “ordinary object created”.

## 24. The Class Loader Is Part of Runtime Type Identity

A runtime class is identified by **its binary name and defining class loader**. Two Class objects can have the same `getName()` string yet **different runtime identities** if defined by different class loaders.

Consequences:

- Do not use a name string alone as proof that two runtime classes are the same.
- In a simple application, `Person.class == new Person().getClass()` is the right model.
- With plugins/containers/test class loaders, a ClassCastException can occur even when class names look identical, because the runtime types differ.
- `Class.getClassLoader()` can return null for bootstrap-loaded classes; that is the API semantics and does not mean the Class object does not exist.

`Class.forName` requires a valid binary name. A nested class typically has `$` in its binary name, and array type names have an encoded form different from `"java.lang.String[]"`.

## 25. Type Erasure: Two Generic Objects Can Share the Same Class Token

~~~java
java.util.List<String> strings = new java.util.ArrayList<>();
java.util.List<Integer> integers = new java.util.ArrayList<>();
~~~

`strings.getClass() == integers.getClass()` is true; both have the ArrayList runtime class.

### Runnable Example

Create **`GenericClassDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericClassDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T value() {
            return value;
        }
    }

    public static void main(String[] args) {
        List<String> strings = new ArrayList<>();
        List<Integer> integers = new ArrayList<>();

        Box<String> word = new Box<>("Java");
        Box<Integer> number = new Box<>(17);

        System.out.println("same List Class=" +
                (strings.getClass() == integers.getClass()));
        System.out.println("same Box Class=" +
                (word.getClass() == number.getClass()));
        System.out.println("word=" + word.value());
        System.out.println("number=" + number.value());
    }
}
~~~

~~~bash
javac -encoding UTF-8 GenericClassDemo.java
java GenericClassDemo
~~~

Stdout:

~~~text
same List Class=true
same Box Class=true
word=Java
number=17
~~~

Generics are still useful for compile-time type checking. However, `getClass()` does not create a new Class object for each use with type arguments.

## 26. Records, Enums, and Sealed Types Have Class Metadata

Java 17 supports:

~~~java
record Point(int x, int y) {}
enum Color { RED, BLUE }
sealed interface Result permits Success, Failure {}
record Success() implements Result {}
record Failure() implements Result {}
~~~

`Point.class.isRecord()` is true; `Color.class.isEnum()` is true; `Result.class.isInterface()` and `Result.class.isSealed()` are both true.

### Runnable Example

Create **`ModernMetadataDemo.java`**:

~~~java
public class ModernMetadataDemo {
    record Point(int x, int y) {}
    enum Color { RED, BLUE }

    sealed interface Result permits Success, Failure {}
    record Success() implements Result {}
    record Failure() implements Result {}

    public static void main(String[] args) {
        System.out.println("record=" + Point.class.isRecord());
        System.out.println("enum=" + Color.class.isEnum());
        System.out.println("interface=" +
                Result.class.isInterface());
        System.out.println("sealed=" +
                Result.class.isSealed());

        Object point = new Point(1, 2);
        System.out.println("point runtime=" +
                (point.getClass() == Point.class));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ModernMetadataDemo.java
java ModernMetadataDemo
~~~

Stdout:

~~~text
record=true
enum=true
interface=true
sealed=true
point runtime=true
~~~

A metadata token states that Point is a record, but it does not individually store the component values 1, 2 of the point object.

## 27. A Class Object Can Be Used as a Map Key or Lock, but Use Caution

A Class object is an Object, having identity and a monitor. You can store:

~~~java
java.util.Map<Class<?>, String> labels =
        new java.util.HashMap<>();

labels.put(String.class, "text");
labels.put(Integer.class, "integer");
~~~

Or a block `synchronized (SomeClass.class) { ... }` locks the monitor of the Class object.

However, using public Class objects as locks can cause contention/deadlocks with unrelated code, especially `Object.class` or `String.class`. Prefer a **private lock object** or an appropriate concurrency abstraction.

Do not infer that every instance method becomes thread-safe merely because a class has a Class token or a static method is synchronized.

## 28. Reflection Introspection Differs from Reflection Invocation

Operations that **read metadata**:

~~~java
Class<?> type = Person.class;
type.getDeclaredMethods();
type.getDeclaredFields();
~~~

do not directly create a Person instance.

Operations that **can execute or mutate state**:

- `Constructor.newInstance(...)`: creates an object, runs the constructor.
- `Method.invoke(target, args...)`: invokes a method, which can have side effects.
- `Field.set(target, value)`: can modify state when permitted.
- `Class.forName(String)`: can initialize the class and run static initializers.

You should not assume every reflection operation is “only inspecting metadata with no side effects”. Using reflection on private members is also governed by accessibility and the Java module system.

## 29. Common Mistakes

| Misconception | Fact |
| --- | --- |
| “`Foo.class` creates a Foo instance.” | Returns a Class object. |
| “`Foo.class` is the Foo.class file itself.” | It is a Java class literal expression. |
| “A Class object contains all Foo instances.” | Describes the runtime type, not an instance registry. |
| “`Class<Foo>` is a Foo object.” | Foo's Class token has runtime class Class. |
| “`String.class` is a String object.” | It is a Class object describing String. |
| “`Class.class.getClass()` creates an infinite chain.” | Equals Class.class. |
| “`getClass()` returns the declared variable type.” | Returns the actual runtime class. |
| “`getClass()` on null returns null.” | Throws NPE. |
| “`Object.class` represents all objects.” | Describes the Object type. |
| “Primitive int also has instance methods.” | A primitive is not an Object instance. |
| “`int.class` equals `Integer.class`.” | Two different Class tokens. |
| “An array has no Class token.” | It does, and `isArray()` is true. |
| “An interface has no metadata.” | `SomeInterface.class` has a Class object. |
| “`isAssignableFrom` can be read in either direction.” | The target class token is on the left side of the call. |
| “A Class token automatically creates an object when read.” | No. |
| “`getDeclaredField` directly gives the field value.” | Returns Field metadata; getting the value needs a target/access. |
| “Reflection grants permission to read every private field.” | Restricted by access/module rules. |
| “`Foo.class` definitely runs the static block.” | Does not by itself force initializing Foo. |
| “`Class.forName(String)` has no side effects.” | Can initialize the class. |
| “Same `getName()` means same runtime type.” | Defining class loaders may differ. |
| “Generics create a separate Class object for `List<String>`.” | Type erasure; the runtime List implementation type is still shared. |

## 30. Exercise 1 — Two Instances and One Class Token

~~~java
class Book {}
Book a = new Book();
Book b = new Book();
Class<Book> type = Book.class;
~~~

**Answer:** There are two Book objects; within the same normal loader context, there is one Class object for the Book runtime type. `a == b` is false; `a.getClass() == b.getClass()` is true; `type == a.getClass()` is true.

## 31. Exercise 2 — Runtime Type via Object

~~~java
Object a = "hello";
Object b = String.class;
~~~

**Answer:** `a.getClass() == String.class` is true, `b.getClass() == Class.class` is true. `b` is a Class object describing String, not a String instance.

## 32. Exercise 3 — Exact vs. Subtype

~~~java
class Animal {}
class Dog extends Animal {}
Animal dog = new Dog();
~~~

**Answer:** `dog.getClass() == Animal.class` is false; `dog.getClass() == Dog.class` is true; `dog instanceof Animal` is true; `dog instanceof Dog` is true.

## 33. Exercise 4 — Primitive, Wrapper, and Array

Predict:

~~~java
int.class == Integer.class;
int[].class.isArray();
int[].class.getComponentType() == int.class;
Integer.class.isPrimitive();
void.class.isPrimitive();
~~~

**Answer:** In order, `false`, `true`, `true`, `false`, `true`.

## 34. Exercise 5 — Assignability

Given `Dog extends Animal`:

~~~java
Animal.class.isAssignableFrom(Dog.class);
Dog.class.isAssignableFrom(Animal.class);
Object.class.isAssignableFrom(Dog.class);
Dog.class.isInstance(new Animal());
~~~

**Answer:** `true`, `false`, `true`, `false`. `isAssignableFrom` takes two Class tokens; `isInstance` takes an object value.

## 35. Exercise 6 — Metadata Is Not an Instance Value

~~~java
class Account {
    public int balance;
}
~~~

Two Accounts have balances of 10 and 20, respectively. `Field f = Account.class.getField("balance")` represents **one field declaration**, whereas `f.getInt(account1)`/`f.getInt(account2)` read two different values.

**Explanation:** Ordinary instance state belongs to each object, whereas Class and Field objects provide runtime metadata about declarations.

## 36. Exercise 7 — Class Initialization

A class:

~~~java
class Config {
    static {
        System.out.println("Config initialized");
    }
}
~~~

The program first uses `Config.class`, then calls `Class.forName("Config")` within the same normal loader context.

**Answer:** A class literal does not by itself force initialization. `Class.forName(String)` requires initialization if the class has not yet been initialized, causing the block to print once. If Config has already been initialized by another operation, it does not print again. In a real package, use the full binary name.

## 37. Exercise 8 — Generic Type Erasure

~~~java
java.util.List<String> a = new java.util.ArrayList<>();
java.util.List<Integer> b = new java.util.ArrayList<>();
System.out.println(a.getClass() == b.getClass());
~~~

**Answer:** `true`. Same runtime ArrayList class, even though the compile-time generic types differ. The compiler still protects `List<String>` from having an Integer added via the type-safe API.

## 38. Exercise 9 — Can a Class Token Be Cast to a String Instance?

~~~java
Class<String> token = String.class;
// String value = (String) (Object) token;
~~~

If uncommented, the cast through Object can compile, yet throws `ClassCastException` because token is a Class object, not a String instance. A cast **does not create or transform an ordinary object**.

## 39. Exercise 10 — Class of Class

~~~java
Class<?> token = Class.class;
System.out.println(token.getClass() == Class.class);
System.out.println(token.getSuperclass() == Object.class);
~~~

**Answer:**

~~~text
true
true
~~~

`Class` inherits from Object, and `Class.class` itself is also a Class object.

## 40. End-of-Article Checklist

- [ ] I can distinguish between a class declaration, an ordinary instance, and a Class object.
- [ ] I know `class`, `Class`, and `.class` are three different notations.
- [ ] I do not confuse a bytecode file with a class literal.
- [ ] I know Class extends Object.
- [ ] I understand `Class.class.getClass() == Class.class`.
- [ ] I know multiple instances of the same runtime type share the Class token within a loader scope.
- [ ] I do not think a Class object holds a list of all instances.
- [ ] I know `Object.class` only describes the Object type.
- [ ] I know `getClass()` returns the actual runtime type.
- [ ] I know `getClass()` on null throws an NPE.
- [ ] I distinguish exact runtime type from subtype compatibility.
- [ ] I know `Class<T>` and `Class<?>`.
- [ ] I know primitive, void, array, and interface types have Class objects.
- [ ] I do not equate a primitive token with a wrapper token.
- [ ] I use `Class.isInstance`, `isAssignableFrom`, and `cast` properly.
- [ ] I distinguish Class metadata from instance field values.
- [ ] I understand how `getDeclared...` and public `get...` APIs differ.
- [ ] I know reflective construction differs from obtaining a Class token.
- [ ] I avoid the deprecated Class.newInstance API.
- [ ] I understand `.class` does not by itself run the static initializer.
- [ ] I know `Class.forName(String)` has initialization semantics.
- [ ] I understand class loader identity and type erasure.
- [ ] I know Class.isRecord/isEnum/isSealed in Java 17.
- [ ] I know reflection access has limitations and can have side effects.
- [ ] I can explain the stdout of the standalone examples above.

**Conclusion:** A **Class** is a type description in Java, an **ordinary object** is an instance with identity and state, and a **`java.lang.Class<?>` object** is a runtime metadata object representing a type. `.class` obtains the token of the type named in source, `getClass()` returns the actual runtime type of a non-null object, and `Class.forName` supports dynamic lookup with its own class-initialization semantics. Do not confuse metadata with object data, and do not confuse “same type name” with the same runtime identity when multiple class loaders are present.
