# Accessing a Static Field and the Declared Type of a Field Using Reflection

Java Reflection allows a program to look up information about a class at runtime, find a field by name, read the field value, and check the declared type in the source code. For a `static field`, you read the value through a `Field` object and pass `null` to `Field.get`, because the field does not belong to a specific instance.

## 1. Three Concepts to Distinguish

- **Where the field is declared:** `Field.getDeclaringClass()` returns the class or interface that directly declares that field.
- **The declared type of the field:** `Field.getType()` returns a `Class<?>` describing the declared field type, for example `Number`, `String`, or `int`. For a generic field, `Field.getGenericType()` provides additional generic type information when that information is present in the signature.
- **The actual type of the current value:** if the value is not `null`, call `value.getClass()` to see the runtime class of the object currently referenced by the field. This type may be a subclass of the declared type.

For example, if you declare `static Number LIMIT = Integer.valueOf(42);`, then the declared type of `LIMIT` is `Number`, whereas the runtime class of the current value is `Integer`. These two questions are different, and Reflection provides separate APIs to answer them.

## 2. Finding and Reading a Static Field

Commonly used APIs:

| API | Meaning |
| --- | --- |
| `SomeClass.class` | Obtains the `Class` object representing the type without creating an instance. |
| `getDeclaredField("NAME")` | Gets the field named `NAME` directly declared in that class; it may be `public`, `protected`, package-private, or `private`. |
| `getField("NAME")` | Finds a `public` field, including inherited `public` fields. |
| `field.getType()` | Gets the declared type of the field as a `Class<?>`. |
| `field.getGenericType()` | Gets the declared type, which may include generic parameters, as a `Type`. |
| `Modifier.isStatic(field.getModifiers())` | Checks whether the field has the `static` modifier. |
| `field.get(null)` | Reads the value of a static field. The object argument is ignored for `static` fields, so passing `null` is the clear way to write it. |
| `field.getDeclaringClass()` | Gets the type that directly declares the field. |

`getDeclaredField` only searches within the type it is called on; it does not automatically search for fields declared in a superclass. If no field with that name exists, the method throws `NoSuchFieldException`. Field names are case-sensitive.

## 3. Complete Example Running with Java 17+

Save the code below to the file `StaticFieldReflectionDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

public class StaticFieldReflectionDemo {
    public static class Settings {
        public static Number LIMIT = Integer.valueOf(42);
        public static String LABEL = "production";
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        inspect(Settings.class, "LIMIT");
        inspect(Settings.class, "LABEL");
    }

    private static void inspect(Class<?> owner, String fieldName)
            throws ReflectiveOperationException {
        Field field = owner.getDeclaredField(fieldName);
        Object value = field.get(null);

        System.out.println("field: " + field.getName());
        System.out.println("declaring class: "
                + field.getDeclaringClass().getTypeName());
        System.out.println("declared type: " + field.getType().getTypeName());
        System.out.println("static: " + Modifier.isStatic(field.getModifiers()));
        System.out.println("value: " + value);
        System.out.println("runtime type: "
                + (value == null ? "null" : value.getClass().getTypeName()));
        System.out.println();
    }
}
```

Compile and run in the directory containing the file:

```shell
javac StaticFieldReflectionDemo.java
java StaticFieldReflectionDemo
```

Exact stdout:

```text
field: LIMIT
declaring class: StaticFieldReflectionDemo$Settings
declared type: java.lang.Number
static: true
value: 42
runtime type: java.lang.Integer

field: LABEL
declaring class: StaticFieldReflectionDemo$Settings
declared type: java.lang.String
static: true
value: production
runtime type: java.lang.String
```

In the output for `LIMIT`, `getType()` returns `Number.class`, because that is the declared field type. The current value is an `Integer`, so `getClass()` on the value returns `Integer.class`. Do not call `getClass()` when the value is `null`; the example checks for null first to avoid a `NullPointerException`.

## 4. How Does Reading a Static Field Differ from Reading an Instance Field?

```java
Field staticField = Settings.class.getDeclaredField("LIMIT");
Object limit = staticField.get(null);

Field instanceField = SomeClass.class.getDeclaredField("name");
Object name = instanceField.get(someObject);
```

For a static field, no instance of the declaring class is needed; the `null` argument expresses that. For an instance field, a compatible object must be passed as the target from which to get the value. If `null` is passed for an instance field, the read will fail with a `NullPointerException`. In both cases, `getType()` still tells you the declared type, independent of the current value.

Reading a static field using Reflection can trigger class initialization if the class has not been initialized yet. Therefore, if initialization has side effects, you need to account for that when using Reflection.

## 5. Inherited Fields, Actual Declaring Type, and Impact on Initialization

When code uses `Child.FIELD`, the name `Child` before the dot does not prove that the field is **declared** in `Child`. Java resolves the field name at compile time based on inheritance and member hiding. If the field is actually declared by `Parent`, a read operation on a `static` field that is not a compile-time constant triggers initialization of **`Parent`**, and does not automatically trigger `Child` solely because of how the expression is written.

The `Field` object helps verify the owner at runtime: `getDeclaringClass()` identifies where it is declared; `getType()` identifies the declared data type. These two results answer two different questions. Save this example to `StaticFieldOwnerDemo.java`:

~~~java
import java.lang.reflect.Field;

public class StaticFieldOwnerDemo {
    public static class Parent {
        public static int SHARED = initialize();

        private static int initialize() {
            System.out.println("init Parent");
            return 10;
        }
    }

    public static class Child extends Parent {
        static {
            System.out.println("init Child");
        }

        public static int OWN = 20;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Field inherited = Child.class.getField("SHARED");
        System.out.println("declaring type: "
                + inherited.getDeclaringClass().getSimpleName());
        System.out.println("reflective read: " + inherited.get(null));
        System.out.println("Child.SHARED: " + Child.SHARED);
        System.out.println("Child.OWN: " + Child.OWN);
    }
}
~~~

~~~bash
javac StaticFieldOwnerDemo.java
java StaticFieldOwnerDemo
~~~

~~~text
declaring type: Parent
init Parent
reflective read: 10
Child.SHARED: 10
init Child
Child.OWN: 20
~~~

Looking up with `Child.class.getField("SHARED")` finds the inherited public field without yet reading the field's value. `getDeclaringClass()` returns `Parent`; then `get(null)` triggers initialization of `Parent` to read `SHARED`. The expression `Child.SHARED` also points to the field declared by `Parent`, so it does not initialize `Child`. Only when reading `Child.OWN`, a field declared by `Child` itself, does the program print `init Child`.

**Field hiding** is a different case: if `Child` declares its own field with the same name as `Parent.SHARED`, each declaration has a separate field. `Child.class.getDeclaredField("SHARED")` returns `Child`'s field, whereas `Parent.class.getDeclaredField("SHARED")` returns `Parent`'s field. The reference type used for access determines which declaration is resolved; with Reflection, check `getDeclaringClass()` to avoid drawing the wrong conclusion. This rule also applies when a field is declared by an interface and referenced through a subinterface name.

## 6. Private Fields and Access Restrictions

`getDeclaredField` can find a `private` field, but finding it does not mean you are permitted to read it. For a private field in code controlled by the application, you can request to open access using `field.setAccessible(true)` before reading:

```java
Field field = Settings.class.getDeclaredField("SECRET");
field.setAccessible(true);
Object secret = field.get(null); // only when access is permitted
```

In modern Java, `setAccessible(true)` can fail, for example with an `InaccessibleObjectException`, if module boundaries do not allow opening access. You should not rely on breaking encapsulation when a public API already meets your needs. Only read private fields when there is a clear reason and you control the runtime environment.

For a `static final` field, reading and modifying are two different matters. You should not use Reflection to try to modify constants; permission to modify final fields is restricted and is not a reliable way to update configuration.

## 7. Error Handling and Practical Notes

- `NoSuchFieldException`: the field name does not exist in the class queried with `getDeclaredField`, or the field resides in another class such as a superclass.
- `IllegalAccessException`: the program does not have permission to access the field under the current access rules.
- `InaccessibleObjectException`: the request to open access was denied by the module system when using `setAccessible(true)`.
- `IllegalArgumentException`: the object passed for an instance field is incompatible with the declaring type of the field. For a static field, the instance argument is not used.
- `getType()` returns the declared type, while `getGenericType()` is useful when generic information such as `List<String>` is needed. Due to type erasure, `getType()` of a `List<String>` field is only `List.class`.
- If the value is a primitive type such as `int`, Reflection returns the value through boxing when using `Field.get`; for example, an `int` value is represented as an `Integer` in `Object`.
- When you only need to read a value in normal application code, accessing `Settings.LIMIT` directly is usually clearer and safer. Reflection is suitable when class/field names need to be discovered at runtime, such as in frameworks, inspection tools, or data mappers.

## 8. Checklist

- [ ] Use the right `Class<?>` for the class containing the field.
- [ ] Choose `getDeclaredField` for a directly declared field or `getField` for a public field, including inherited ones.
- [ ] Use `Modifier.isStatic(...)` if you need to verify that the field is static.
- [ ] Call `field.get(null)` to read a static field.
- [ ] Use `field.getType()` for the declared type and `value.getClass()` for the runtime class when the value is not `null`.
- [ ] Handle Reflection exceptions and access permissions according to the module environment.

The most important rule: the declared type belongs to the field definition; the runtime type belongs to the object being referenced. When reading a static field with Reflection, get the field from the right class, read it with `get(null)`, and then choose the type API that fits the question you need to answer.
