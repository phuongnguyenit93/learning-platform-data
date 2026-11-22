# Declaring classes and creating instances in Java

In object-oriented programming (OOP), a **class** describes the data and behavior shared by a group of objects. An **instance** (or object) is a specific object created from that class definition.

For example, the `Workshop` class can represent a workshop with a name, capacity, and number of registered participants. From the same class, the program creates two independent instances: a "Java cơ bản" workshop with two seats and a "Spring Boot" workshop with one seat.

## 1. Declaring a class

Basic syntax:

~~~java
class TenLop {
    // Các trường (fields): lưu trạng thái
    // Constructor: thiết lập trạng thái khi tạo đối tượng
    // Các phương thức (methods): mô tả hành vi
}
~~~

A Java class typically has three components:

| Component | Role | Example in `Workshop` |
| --- | --- | --- |
| Field | Stores data belonging to each object | `name`, `capacity`, `registeredCount` |
| Constructor | Validates and initializes an object | `Workshop(String name, int capacity)` |
| Method | Allows an object to perform behavior | `register()`, `remainingSeats()` |

The `class` keyword defines a new object type. By Java convention, class names use `PascalCase` (`Workshop`, `OrderItem`). The `public` keyword controls accessibility; a source file typically contains one `public` top-level class, and its filename must match that class name (for example, `Main.java` for `public class Main`).

**Declaring a class does not create instances of it.** Instances appear only when the program performs an object-creation operation, typically using `new`.

## 2. Creating instances with `new`

A typical expression:

~~~java
Workshop java = new Workshop("Java cơ bản", 2);
~~~

Read it from left to right:

1. `Workshop` is the **variable's type**.
2. `java` is a **reference variable** used to access the object.
3. `new Workshop(...)` creates an instance of `Workshop` and invokes the matching constructor.
4. `"Java cơ bản"` and `2` are arguments used to initialize the name and capacity.
5. The assignment operator `=` stores **a reference to the object** in the variable `java`.

You can declare a reference and create the object later:

~~~java
Workshop course;                         // Chưa tham chiếu đến đối tượng nào
course = new Workshop("Java cơ bản", 2); // Bắt đầu trỏ đến thể hiện mới
~~~

The local variable `course` must be assigned before use. Unlike local variables, a **reference field** that has not been explicitly initialized defaults to `null`. Calling a method through a `null` reference causes a `NullPointerException`.

## 3. Complete example: workshop registration

Place all the following code in **`Main.java`**. The example uses Java 11 or later because it calls `String.isBlank()`.

~~~java
class Workshop {
    private final String name;
    private final int capacity;
    private int registeredCount;

    // Constructor: cùng tên với lớp, không khai báo kiểu trả về.
    Workshop(String name, int capacity) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên buổi học không hợp lệ");
        }
        if (capacity <= 0) {
            throw new IllegalArgumentException("Sức chứa phải lớn hơn 0");
        }

        this.name = name;
        this.capacity = capacity;
        this.registeredCount = 0;
    }

    // Hành vi thay đổi trạng thái riêng của thể hiện hiện tại.
    boolean register() {
        if (registeredCount >= capacity) {
            return false;
        }
        registeredCount++;
        return true;
    }

    int remainingSeats() {
        return capacity - registeredCount;
    }

    String getName() {
        return name;
    }
}

public class Main {
    public static void main(String[] args) {
        Workshop java = new Workshop("Java cơ bản", 2);
        Workshop spring = new Workshop("Spring Boot", 1);

        System.out.println(java.getName());
        System.out.println(java.register());
        System.out.println(java.register());
        System.out.println(java.register());
        System.out.println(java.remainingSeats());
        System.out.println(spring.remainingSeats());

        Workshop alias = spring; // Thêm tham chiếu, không tạo đối tượng mới
        System.out.println(alias == spring);
        alias.register();
        System.out.println(spring.remainingSeats());

        Workshop separate = new Workshop("Spring Boot", 1);
        System.out.println(separate == spring);
        System.out.println(separate.remainingSeats());
    }
}
~~~

Run these commands from the directory containing `Main.java`:

~~~bash
javac Main.java
java Main
~~~

Output:

~~~text
Java cơ bản
true
true
false
0
1
true
0
false
1
~~~

**Explanation:** The `java` object has two seats, so its first two `register()` calls succeed and the third fails. The `spring` object still has one seat: changing `java` does not affect `spring`. Calling `alias.register()` reduces `spring`'s remaining seats to 0 because both variables refer to the same object. Then `new Workshop("Spring Boot", 1)` creates a *different* instance, even though its arguments match those used to create `spring`.

## 4. What does a constructor do?

A constructor initializes an instance. It **has the same name as its class** and **has no return type**, not even `void`. In the example above, the constructor requires a nonblank name and a positive capacity, then assigns the instance's fields.

The `this` keyword refers to the current object. In `this.name = name;`, the left side is the object's `name` field; the right side is the `name` parameter passed to the constructor. This form avoids ambiguity when a field and parameter share a name.

If you declare **no constructors at all**, the compiler supplies a default no-argument constructor whose access level matches the class's accessibility. But **once you declare a parameterized constructor**, Java does not automatically generate a no-argument constructor:

~~~java
class Marker {
    String color;
}

Marker a = new Marker(); // Hợp lệ: constructor mặc định

// Với lớp Workshop ở ví dụ chính:
// new Workshop();        // Lỗi biên dịch: thiếu 2 đối số
~~~

The `Marker` snippet is a standalone illustration; do not append it after the complete example outside the `main` method. You can also define multiple constructors with different signatures (*constructor overloading*) when several initialization paths are valid, but each constructor must ensure a valid initial state.

## 5. Distinguishing classes, instances, and references

| Concept | Meaning | Example |
| --- | --- | --- |
| Class | A definition of data and behavior | `class Workshop { ... }` |
| Instance | An object created from a class | The "Java cơ bản" object |
| Reference variable | A variable used to access an object | `java`, `spring`, `alias` |
| `new` | An expression that creates an object and invokes a constructor | `new Workshop("Spring Boot", 1)` |

After the assignments in the example, the reference relationships can be visualized as follows:

~~~mermaid
flowchart LR
    J["java"] --> W1["Workshop #1: Java cơ bản"]
    S["spring"] --> W2["Workshop #2: Spring Boot"]
    A["alias"] --> W2
    D["separate"] --> W3["Workshop #3: Spring Boot"]
~~~

There are three objects but four reference variables. `spring` and `alias` both access object #2; object #3 was created separately.

- `Workshop alias = spring;` **does not copy the object**. It copies the reference value.
- `new Workshop(...)` performs another instance-creation operation.
- `alias == spring` is `true` because the references point to the same object.
- `separate == spring` is `false` because they point to different objects.
- For objects, `==` checks **reference identity**; `equals()` can express content equality if the class overrides it. Here, `Workshop` does not override `equals()`.

Do not think of each reference variable as holding an independent copy of the object. When multiple references point to the same mutable object, changes made through one reference are visible through the others.

## 6. Access control and encapsulation from the declaration stage

The three fields of `Workshop` are declared `private` so calling code cannot directly assign `registeredCount = 999` or change the capacity arbitrarily. To register, the program calls `register()`, which checks for available seats before incrementing the count.

`final` on `name` and `capacity` requires each field to be assigned once during initialization and prevents later reassignment. It does **not** make the entire object immutable, because `registeredCount` can still change.

In this example, `Workshop` is not declared `public`, so it is accessible only within its package. Its methods also have default (package-private) access, which is enough for `Main` because both are in the same file/package. When a project spans multiple packages, use `public` for APIs that must be accessed from another package.

## 7. Common mistakes

| Situation | Cause | Solution |
| --- | --- | --- |
| `new Workshop()` does not compile | The class only has a two-parameter constructor | Supply both arguments or explicitly declare a no-argument constructor if appropriate |
| Declaring `Workshop x;` and then calling `x.register()` | The local variable has not been assigned | Initialize with `new` or assign a valid reference before use |
| Declaring `Workshop x = null;` and then calling a method | `null` does not refer to an object | Check the initialization path and avoid calling methods through `null` |
| Assuming `Workshop b = a;` duplicates the data | Assignment copies only the reference | Create a new object and deliberately copy the data if needed |
| Declaring `public class Workshop` inside `Main.java` | The filename does not match the `public` class name | Move `Workshop` to `Workshop.java`, or keep it non-`public` inside `Main.java` |
| Writing `void Workshop(...)` | This declares a method named `Workshop`, not a constructor | Omit the return type to declare a constructor |

## 8. Check your understanding

1. If you create `Workshop a = new Workshop("A", 3);` and `Workshop b = new Workshop("B", 3);`, does calling `a.register()` change `b.remainingSeats()`? **No**: these are two independent instances.
2. If you then write `Workshop c = a;`, what is `c == a`? **`true`**, because both references point to the same instance.
3. Where should you check that a workshop cannot be created with a capacity of 0? **In the constructor**, so every new object starts in a valid state.
4. Does `new Workshop("A", 3)` create a new class or a new object? **A new object** of the already-defined `Workshop` class.
5. If you only write `class Workshop { ... }` without executing `new Workshop(...)`, has that declaration created any `Workshop` instances? **No**.

**Remember when writing Java:** Declare a `class` to define structure and behavior; use `new` and a constructor to create objects; retain references to call methods. Each new instance has its own state, while reference assignment can allow multiple variables to access the same instance.
