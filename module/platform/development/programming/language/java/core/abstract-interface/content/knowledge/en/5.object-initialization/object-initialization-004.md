# Maintaining Valid State in an Abstract Class (Java)

An object is in a **valid state** when its values satisfy the design rules. **Invariants** are the conditions that must hold true after constructor initialization succeeds and after every public operation completes normally.

For example, a reservation may require a non-empty reference code, a non-negative number of remaining seats, and, for each reservation request, a positive count that does not exceed the remaining capacity. If the state becomes invalid, subsequent methods may continue computing based on unreliable data.

An abstract class has constructors, fields, and regular methods; it simply does not allow direct instantiation with new. When a concrete subclass is created, the superclass's portion of the state still resides in the object. Therefore, **an abstract class should itself protect the shared invariants it owns**.

| Concept | Question to Answer |
| --- | --- |
| Precondition | What values is the caller allowed to pass? |
| Invariant | What state must always be true? |
| Postcondition | After a successful operation, what must the result be? |
| Encapsulation | Who may read or modify the state, and through which API? |

## 1. Checking in the Constructor and at Every Update Point

The constructor is an appropriate place to validate required data and initialize the fields managed by the class. If a parameter violates the contract, throw a clear exception instead of creating an object that is already invalid from the start.

However, **the constructor only protects the starting point**. Every method that modifies state must also maintain the invariants. If checks are performed only at creation time, yet assigning a negative seat count is allowed later, the object can still become invalid.

- Use IllegalArgumentException for values that do not satisfy business conditions.
- Use Objects.requireNonNull when a required reference must be non-null and a NullPointerException is appropriate.
- A protected constructor is usually appropriate for an abstract superclass that is initialized only through subclasses.
- Avoid publishing this through a callback or registry before the object finishes initializing.

## 2. Runnable Example: Reservation with Invariants

Save to **ReservationDemo.java**:

~~~java
abstract class Reservation {
    private final String reference;
    private int available;

    protected Reservation(String reference, int available) {
        if (reference == null || reference.isBlank()) {
            throw new IllegalArgumentException(
                    "reference must not be blank");
        }
        if (available < 0) {
            throw new IllegalArgumentException(
                    "available must be non-negative");
        }
        this.reference = reference;
        this.available = available;
    }

    public final String reference() {
        return reference;
    }

    public final int available() {
        return available;
    }

    public final void reserve(int count) {
        if (count <= 0) {
            throw new IllegalArgumentException(
                    "count must be positive");
        }
        if (count > available) {
            throw new IllegalStateException("not enough seats");
        }
        available -= count;
    }

    protected abstract String type();

    public final String description() {
        return type() + " " + reference + ": "
                + available + " seats";
    }
}

final class ConferenceReservation extends Reservation {
    ConferenceReservation(String reference, int available) {
        super(reference, available);
    }

    @Override
    protected String type() {
        return "Conference";
    }
}

public class ReservationDemo {
    public static void main(String[] args) {
        Reservation reservation =
                new ConferenceReservation("EV-24", 5);

        System.out.println(reservation.description());
        reservation.reserve(2);
        System.out.println(reservation.description());

        try {
            reservation.reserve(4);
        } catch (IllegalStateException error) {
            System.out.println("Rejected: " + error.getMessage());
        }
        System.out.println("Remaining: " + reservation.available());

        try {
            new ConferenceReservation(" ", 3);
        } catch (IllegalArgumentException error) {
            System.out.println("Invalid: " + error.getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac ReservationDemo.java
java ReservationDemo
~~~

Stdout:

~~~text
Conference EV-24: 5 seats
Conference EV-24: 3 seats
Rejected: not enough seats
Remaining: 3
Invalid: reference must not be blank
~~~

The Reservation constructor validates the reference code and seat count before storing them. reserve checks count and capacity **before subtracting**, so a failed request does not leave a negative seat count. The reference variable has type Reservation, while the actual object is a ConferenceReservation; an abstract class can still serve as a reference type.

## 3. Encapsulation to Protect State

If available were protected, a subclass could assign available = -99 and break the invariant without going through reserve. Keep mutable fields private and provide behavior with business meaning instead of arbitrary setters.

- **Clear data ownership:** do not directly return a reference to an internal mutable structure if the caller can modify it.
- **Check before modifying:** validate the input and current state, and only then update.
- **Restrict extension points:** use final for methods that protect invariants when subclasses must not change that rule.
- **Do not confuse final with thread safety:** final prevents overriding or reassignment according to Java rules, but it does not automatically make multi-step operations atomic.

For a mutable reference field, a defensive copy may be needed. The example below illustrates a list of tags:

~~~java
import java.util.List;

abstract class TaggedResource {
    private final List<String> tags;

    protected TaggedResource(List<String> tags) {
        this.tags = List.copyOf(tags);
    }

    public final List<String> tags() {
        return tags;
    }
}
~~~

List.copyOf rejects a null list or null elements and provides a list that cannot be modified through the List API. Because String is immutable, this is an appropriate protection for the tags. For mutable elements, this is still a shallow copy; consider whether each element must be copied or whether an immutable type should be used.

## 4. Coordinating Invariants Between Superclass and Subclass

The invariant of the entire object is the combination of rules for both superclass and subclass state. The superclass constructor validates the data owned by the superclass; the subclass constructor validates its own data after calling super(...). The subclass must preserve the contract observable from the superclass and must not open update paths that conflict with the shared rules.

For example, if a subclass requires the seat count to always be greater than 0, checking that condition only in the subclass constructor is not enough: a subsequent call to reserve can bring the seat count to 0. Every API that modifies related state must protect the same invariant. This is the difference between **valid upon creation** and **valid throughout the lifecycle**.

Care is also needed when a superclass calls an overridable method in its constructor: the subclass method may run before subclass fields are initialized. Keep constructors focused on the parameters and state that they themselves control; the article on the risks of calling overridden methods in a constructor analyzes this case in more detail.

## 5. Limitations with Multiple Threads

The Reservation example protects invariants in a sequential call flow. If two threads call reserve simultaneously, checking available and subtracting do not automatically become a single atomic operation. To support multiple threads, appropriate synchronization such as locks or another concurrency design is needed, along with proper testing. A final method does not automatically imply thread safety.

## 6. Testing and Common Mistakes

| Test Case | Expected Result |
| --- | --- |
| Null, empty, or whitespace-only reference code | Rejected |
| Negative available | Rejected |
| available equal to 0 with a valid reference code | Accepted per the example contract |
| reserve(0) or reserve(-1) | Rejected, preserving the previous state |
| Reserving more than the remaining seats | Rejected, preserving the previous state |
| Reserving a valid count | Decreased by the exact amount, non-negative |
| Subclass accesses available directly | Compile error because the field is private |
| Multiple threads reserving concurrently | Claim safety only when the synchronization mechanism has been verified |

Common mistakes include validating only setters while forgetting the constructor; validating only the constructor while forgetting update methods; using assert for business data; leaving mutable fields protected; or modifying multiple fields before finishing checks, leaving the object in a partial state when an exception occurs.

**Takeaway:** an abstract class is an appropriate place to establish the shared invariants of a family of classes. The constructor verifies the starting point; encapsulation, checked update APIs, and controlled extension points keep the state valid thereafter.
