# Member Types Declared Inside an Interface

## 1. What Is a Member Type?

An interface can contain data type declarations directly inside its body. Those types are called **member types**. Java allows nested classes, nested interfaces, enums, records (Java 16+), and annotation interfaces:

```java
interface Transport {
    interface Driver {
        void drive();
    }

    class Route {
        private final String name;

        Route(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    enum Mode {
        ROAD, RAIL
    }

    record Ticket(String code) {}

    @interface Audited {}
}
```

The full names of the types in the example are `Transport.Driver`, `Transport.Route`, `Transport.Mode`, `Transport.Ticket`, and `Transport.Audited`, respectively. They are types, not fields or methods of `Transport`.

## 2. Implicit Modifiers: public static

Every member type declared directly in an interface is implicitly `public static`, even when those two keywords are not written.

- `static` means the member type does not need an instance of the enclosing interface. An instance of `Transport` cannot be created because it is an interface, and no such instance is needed to create `Transport.Route` either.
- `public` is the modifier of the member type, but it does not override the accessibility of the enclosing type. If the enclosing top-level interface is package-private, code outside the package still cannot access it solely because the member type is public.
- Do not place `private` or `protected` on a member type declared directly inside an interface.

Usage:

```java
Transport.Route route = new Transport.Route("North");
Transport.Mode mode = Transport.Mode.RAIL;
Transport.Ticket ticket = new Transport.Ticket("T-1");
```

`Transport.Route` is a static nested class and has its own constructor. It does not need the `outer.new Route(...)` syntax.

## 3. Runnable Example on Java 17+

```java
interface Library {
    interface Identified {
        String id();
    }

    class Holder {
        private final String text;

        Holder(String text) {
            this.text = text;
        }

        String text() {
            return text;
        }
    }

    enum Status {
        DRAFT, PUBLISHED
    }

    record Book(String id, String title) implements Identified {}
}

public class Main {
    public static void main(String[] args) {
        Library.Holder holder = new Library.Holder("Notes");
        Library.Book book = new Library.Book("B01", "Java");
        Library.Identified identified = book;
        System.out.println(holder.text());
        System.out.println(identified.id() + " - " + book.title());
        System.out.println(Library.Status.PUBLISHED);
    }
}
```

Output:

```text
Notes
B01 - Java
PUBLISHED
```

`Library.Book` is a record, so it automatically provides the `id()` and `title()` accessors. It implements `Library.Identified` explicitly; being declared inside `Library` does not automatically create an `implements` relationship with the enclosing interface.

## 4. Distinguishing Member Types from Fields and Methods

```java
interface Sensor {
    int MAX_RETRIES = 3;  // Field: public static final
    int read();           // Method: public abstract

    default boolean ready() {
        return read() >= 0;
    }

    static String category() {
        return "sensor";
    }

    record Reading(int value) {} // Member type: public static
}
```

`MAX_RETRIES` is a constant field; `read`, `ready`, and `category` are methods; `Reading` is a type. Do not infer that a regular member class is final or immutable just because it is inside an interface. For example, a record is final according to the rules for records, whereas a normal nested class can have mutable state and mutating methods.

## 5. Declaration Location Does Not Create a Type Relationship

A nested class does not automatically implement the enclosing interface:

```java
interface Task {
    void execute();

    class Config {}
    class Worker implements Task {
        @Override
        public void execute() {
            System.out.println("working");
        }
    }
}
```

`Task.Config` is not a `Task`. `Task.Worker`, however, is a `Task` because it explicitly declares `implements Task` and provides `execute()`. Similarly, a nested interface inherits from the enclosing interface only when it declares `extends`.

## 6. When Should You Nest a Type?

A member type is appropriate when the type is closely tied in meaning to the enclosing API, such as `Parser.Result`, `Connection.State`, or `EventBus.Listener`. The `Outer.Member` notation helps readers recognize a group of related concepts.

If a type is used independently by multiple APIs or has a significant separate responsibility, consider a top-level type to improve reusability. Always check the access rules, `extends`, and `implements` separately; nesting only organizes names and scope, and does not automatically create an inheritance relationship.
