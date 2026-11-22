# Accessing Constants via Interface Name and Handling Duplicate Constant Names

## 1. Explicitly Specifying the Type That Owns the Constant

Interface fields are public static final, so they can be read directly via the interface name without creating an object or implementing that interface.

~~~java
interface Pagination {
    int DEFAULT_SIZE = 20;
    int MAX_SIZE = 100;
}

public class ConstantAccessDemo {
    public static void main(String[] args) {
        System.out.println(Pagination.DEFAULT_SIZE);
        System.out.println(Pagination.MAX_SIZE);
    }
}
~~~

Output:

~~~text
20
100
~~~

Writing Pagination.DEFAULT_SIZE clearly tells the reader the declaration source. In a class implementing an interface, a simple name can work if there is no conflict, but it forces the reader to search through all interfaces and fields with the same name. Prefer qualifiers to keep the code easy to maintain.

## 2. Two Interfaces with Constants of the Same Name

~~~java
interface HttpSettings {
    int TIMEOUT_SECONDS = 5;
}

interface DatabaseSettings {
    int TIMEOUT_SECONDS = 30;
}

final class ConnectionMonitor implements HttpSettings, DatabaseSettings {
    void showTimeouts() {
        System.out.println(HttpSettings.TIMEOUT_SECONDS);
        System.out.println(DatabaseSettings.TIMEOUT_SECONDS);
    }
}

public class NameCollisionDemo {
    public static void main(String[] args) {
        new ConnectionMonitor().showTimeouts();
    }
}
~~~

Output:

~~~text
5
30
~~~

In ConnectionMonitor, the simple name TIMEOUT_SECONDS does not indicate which field is intended and can cause an ambiguous reference error. Java does not automatically choose the first interface in the implements list, even when the two identically named fields have the same value. Explicitly specifying HttpSettings.TIMEOUT_SECONDS or DatabaseSettings.TIMEOUT_SECONDS resolves the conflict.

## 3. Field Hiding Is Not Overriding

Fields do not participate in polymorphic overriding like instance methods. If a class declares a field with the same name, the class's field hides the inherited name within the applicable scope:

~~~java
interface DefaultLimits {
    int LIMIT = 10;
}

final class LimitedService implements DefaultLimits {
    static final int LIMIT = 25;

    void printLimits() {
        System.out.println(LIMIT);
        System.out.println(LimitedService.LIMIT);
        System.out.println(DefaultLimits.LIMIT);
    }
}
~~~

Both values still exist: LimitedService.LIMIT is 25, while DefaultLimits.LIMIT is 10. Field selection is resolved by the name and declared type, not by the actual object as with instance method calls.

A subinterface can also declare a field with the same name as an inherited field; the child field hides the name, but the parent field can still be accessed via the parent interface name.

## 4. Collisions with Static Imports

Static import allows using static member names without writing the type name. However, it does not eliminate name collisions.

~~~java
import static java.lang.Integer.*;
import static java.lang.Long.*;

public class StaticImportCollisionDemo {
    public static void main(String[] args) {
        // MAX_VALUE alone would be ambiguous between Integer and Long.
        System.out.println(Integer.MAX_VALUE);
        System.out.println(Long.MAX_VALUE);
    }
}
~~~

Output:

~~~text
2147483647
9223372036854775807
~~~

For common names such as MAX_VALUE, LIMIT, STATUS, or TIMEOUT, using OwnerType.CONSTANT avoids having to infer the source from the import list. Collisions can come from interfaces that a class implements, parent interfaces, fields of the class itself, or static imports.

## 5. Practical Rules

- Read constants via the name of the interface that defines them.
- When multiple interfaces have the same field name, write the qualifier explicitly.
- If a class declares a field with the same name, distinguish the class's field from the interface's field; that is hiding.
- Do not implement an interface just to get short constant names. An implements relationship should represent a type/behavior contract.
- A mutable field exposed from an interface can still be modified through a reference; see the lesson on final and immutability.
- Compile-time constant values can be embedded into compiled clients; changing a constant value may require recompiling clients.

### Self-Check

1. Do you need to create an object to read Pagination.DEFAULT_SIZE? **No**.
2. Two unrelated interfaces both declare TIMEOUT_SECONDS; does the simple name automatically choose the first interface? **No**.
3. Does a class field with the same name as an interface field override polymorphically? **No**, that is hiding.
4. Does static import turn two MAX_VALUE constants into one field? **No**, a type qualifier helps select the source.

The key point is to clearly identify which type a field belongs to. Sufficiently explicit names avoid ambiguity and keep design intent stable as a class or interface grows.
