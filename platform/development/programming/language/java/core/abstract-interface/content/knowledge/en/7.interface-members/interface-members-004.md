# Distinguishing final from Object Immutability in Java

## 1. Two Different Questions

**final** on a variable or field restricts reassigning the variable. **Immutability** describes whether an object's observable state changes after creation. One property does not automatically imply the other.

~~~java
final int count = 3;
// count = 4;                 // Error: cannot reassign count

final StringBuilder text = new StringBuilder("Java");
text.append(" 17");           // Valid: modifies the referenced object
// text = new StringBuilder(); // Error: cannot change the reference
~~~

For primitives, final fixes the value after initialization. For reference types, final fixes the reference; the target object's API may still allow modifying its state.

String and Integer are immutable types. StringBuilder, arrays, and ArrayList have mutable state. A final class only prevents inheritance, and a record only fixes component field reassignment according to the record's structure; neither automatically makes child objects deeply immutable.

## 2. Why Does This Matter for Interface Fields?

Fields declared in an interface are public static final. If a field points to a mutable object, external code can still modify that object through the public reference.

~~~java
interface SharedSettings {
    int TIMEOUT_SECONDS = 5;
    int[] PORTS = {8080, 8081};
}
~~~

You cannot assign SharedSettings.PORTS to a new array, but the assignment SharedSettings.PORTS[0] = 9090 is valid. Every place reading the field sees the change on the same array. Avoid exposing mutable arrays or collections if you want stable configuration data.

## 3. Immutability Requires Controlling Escaping References

~~~java
import java.util.List;

final class UnsafeProfile {
    private final List<String> roles;

    UnsafeProfile(List<String> roles) {
        this.roles = roles;
    }

    List<String> roles() {
        return roles;
    }
}
~~~

This class is not immutable: the caller can retain the input list and modify it after creating the profile; at the same time, the getter directly returns the internal list, allowing modification from the outside. These two issues are commonly called aliasing on input and representation exposure on output.

If you want stable state, control both the data coming in and the data being returned.

## 4. Defensive Copying with List.copyOf

Save the following code to **ProfileDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

final class Profile {
    private final String username;
    private final List<String> roles;

    Profile(String username, List<String> roles) {
        this.username = username;
        this.roles = List.copyOf(roles);
    }

    String username() {
        return username;
    }

    List<String> roles() {
        return roles;
    }
}

public class ProfileDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("READER"));
        Profile profile = new Profile("mai", input);
        input.add("ADMIN");

        System.out.println(profile.username());
        System.out.println(profile.roles());
        System.out.println(input);
    }
}
~~~

Run with JDK 17+:

~~~bash
javac --release 17 ProfileDemo.java
java ProfileDemo
~~~

Output:

~~~text
mai
[READER]
[READER, ADMIN]
~~~

List.copyOf creates an unmodifiable list and decouples the list structure from the mutable source. Because the elements in the example are immutable Strings, there is no need to copy each element individually. List.copyOf rejects null for the list or its elements, and does not automatically deep-copy mutable elements.

## 5. Unmodifiable Views and Snapshots Differ

**Collections.unmodifiableList(source)** blocks modifications through the view, but the view still reflects changes from source. **List.copyOf(source)** creates an unmodifiable structure that no longer reflects additions or removals on the mutable source.

| Creation method | Modifiable through the result? | Sees structural changes from source? |
| --- | --- | --- |
| Collections.unmodifiableList(source) | No | Yes |
| List.copyOf(source) | No | No |

Neither approach makes mutable elements immutable. If an element is a StringBuilder and another reference to it exists, the element's content can still change.

## 6. Records and Deep Immutability

A record does not automatically copy passed-in collections. If a record receives a mutable List and keeps the original reference, the caller can still cause its observable content to change. You can perform defensive copying in a compact constructor:

~~~java
import java.util.List;

record Report(List<String> tags) {
    Report {
        tags = List.copyOf(tags);
    }
}
~~~

For immutable elements like String, this approach protects the structure and observable data in the example. For mutable elements, you must explicitly define how to copy them or convert them into immutable data types.

## 7. final Does Not Make Shared Data Thread-Safe

A public static final ArrayList can still be read and modified concurrently by multiple threads. final does not turn modification operations on a mutable object into thread-safe operations. Choose an appropriate data structure and synchronization mechanism; best of all, avoid sharing mutable state when unnecessary.

### Design Checklist

- Use final to prevent reassigning a variable or reference.
- Use immutable types when a value should not change after creation.
- Defensively copy input data and do not directly return internal mutable references.
- Distinguish an unmodifiable view from an independent snapshot.
- Do not infer deep immutability solely from final class, record, or List.copyOf.
- Avoid exposing mutable state from an interface because every place with access can affect the same data.

Immutability is the result of an object's design and the references that can reach it; the final keyword is only one part of that design.
