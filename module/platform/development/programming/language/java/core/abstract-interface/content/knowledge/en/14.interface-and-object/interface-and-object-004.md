# Implementing Consistent equals and hashCode Across Subtypes in Java

When a class has subtypes, equality must have a unified definition across the entire hierarchy. A common mistake is when the superclass accepts a subclass object because the shared fields match, while the subclass compares additional own fields and rejects the superclass object. In that case, equals loses symmetry; if hashCode also relies on different sets of fields, the hash contract can be broken.

## 1. The Contract to Preserve

| Property | Verification question |
| --- | --- |
| Reflexivity | Is x.equals(x) true? |
| Symmetry | Do x.equals(y) and y.equals(x) produce the same result? |
| Transitivity | If x equals y and y equals z, does x equal z? |
| Consistency | When relevant data does not change, is the result stable? |
| Null | Is x.equals(null) false? |
| Hash | If x.equals(y) is true, are the two hash codes equal? |

Two unequal objects can still share the same hash code. The only requirement is that equal implies same hash. The compiler cannot prove these properties merely from the code compiling.

Each hierarchy needs to decide in advance: can objects of different concrete classes be equal, are subtypes allowed to add fields to equality, and who is allowed to change the policy when adding subtypes. Do not start by mechanically choosing instanceof or getClass(); start with the meaning of identity/value in the business domain.

## 2. Classic Mistake: Superclass Uses instanceof, Subclass Adds Conditions

~~~java
class Point {
    final int x;
    final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Point point
                && x == point.x && y == point.y;
    }

    @Override
    public int hashCode() {
        return 31 * x + y;
    }
}

final class ColorPoint extends Point {
    final String color;

    ColorPoint(int x, int y, String color) {
        super(x, y);
        this.color = color;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof ColorPoint point
                && super.equals(point)
                && color.equals(point.color);
    }

    @Override
    public int hashCode() {
        return 31 * super.hashCode() + color.hashCode();
    }
}

public class BrokenEqualityDemo {
    public static void main(String[] args) {
        Point plain = new Point(1, 2);
        Point colored = new ColorPoint(1, 2, "blue");
        System.out.println(plain.equals(colored));
        System.out.println(colored.equals(plain));
    }
}
~~~

Output:

~~~text
true
false
~~~

Point accepts ColorPoint because the coordinates match; ColorPoint rejects Point because it lacks color. The two directions produce different results. Point can also treat two objects as equal while ColorPoint generates a hash code based on color, leading to a violation of the equal implies same hash rule. Having @Override on both methods does not guarantee a correct contract.

## 3. Choosing the Equality Boundary for the Entire Hierarchy

**Model A: equal only for the same runtime class.** Suitable when each subtype carries different data or meaning. Use getClass() to reject other subtypes, then compare common fields and subtype-specific fields. If you want to lock the policy for the entire tree, the superclass can define final equals/hashCode and call protected hooks for subtypes to compare details.

**Model B: equality by shared identity across subtypes.** Suitable when subtypes are different views of the same entity and have a global, immutable ID. The superclass can use instanceof with the shared ID, while declaring final equals/hashCode so that subtypes do not add their own conditions. Choose this model only if two subtypes with the same ID truly must represent the same business identity.

## 4. Examples for the Two Models

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class EqualitySubtypesDemo {
    static abstract class Notice {
        private final String code;

        Notice(String code) {
            this.code = Objects.requireNonNull(code);
        }

        protected abstract boolean sameDetails(Notice other);
        protected abstract int detailsHash();

        @Override
        public final boolean equals(Object obj) {
            if (this == obj) return true;
            if (obj == null || getClass() != obj.getClass()) return false;
            Notice other = (Notice) obj;
            return code.equals(other.code) && sameDetails(other);
        }

        @Override
        public final int hashCode() {
            return Objects.hash(getClass(), code, detailsHash());
        }
    }

    static final class EmailNotice extends Notice {
        private final String email;

        EmailNotice(String code, String email) {
            super(code);
            this.email = Objects.requireNonNull(email);
        }

        @Override
        protected boolean sameDetails(Notice other) {
            return email.equals(((EmailNotice) other).email);
        }

        @Override
        protected int detailsHash() {
            return email.hashCode();
        }
    }

    static final class SmsNotice extends Notice {
        private final String phone;

        SmsNotice(String code, String phone) {
            super(code);
            this.phone = Objects.requireNonNull(phone);
        }

        @Override
        protected boolean sameDetails(Notice other) {
            return phone.equals(((SmsNotice) other).phone);
        }

        @Override
        protected int detailsHash() {
            return phone.hashCode();
        }
    }

    static abstract class GlobalEntity {
        private final String id;

        GlobalEntity(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override
        public final boolean equals(Object obj) {
            return this == obj
                    || (obj instanceof GlobalEntity other && id.equals(other.id));
        }

        @Override
        public final int hashCode() {
            return id.hashCode();
        }
    }

    static final class UserEntity extends GlobalEntity {
        UserEntity(String id) { super(id); }
    }

    static final class AdminEntity extends GlobalEntity {
        AdminEntity(String id) { super(id); }
    }

    public static void main(String[] args) {
        Notice a = new EmailNotice("N1", "a@example.org");
        Notice b = new EmailNotice("N1", "a@example.org");
        Notice c = new EmailNotice("N1", "b@example.org");
        Notice d = new SmsNotice("N1", "12345");

        Set<Notice> notices = new HashSet<>();
        notices.add(a);
        notices.add(b);
        notices.add(c);
        notices.add(d);

        HashMap<Notice, String> messages = new HashMap<>();
        messages.put(a, "sent");

        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());
        System.out.println(a.equals(c));
        System.out.println(a.equals(d));
        System.out.println(notices.size());
        System.out.println(messages.get(b));

        GlobalEntity user = new UserEntity("G1");
        GlobalEntity admin = new AdminEntity("G1");
        System.out.println(user.equals(admin));
        System.out.println(user.hashCode() == admin.hashCode());
    }
}
~~~

Output:

~~~text
true
true
false
false
3
sent
true
true
~~~

Notice uses Model A: only objects of the same type and with the same data are equal. GlobalEntity uses Model B: UserEntity and AdminEntity with the same ID are considered the same identity. Both choices can be correct if they fit the business domain; do not mix them within a single hierarchy. In Model A, the cast in sameDetails is safe because equals has already confirmed the exact same runtime class before calling the hook.

## 5. instanceof, getClass, and canEqual Answer Different Questions

- other instanceof Parent accepts Parent and subtypes.
- getClass() == other.getClass() requires two objects to have the exact same runtime class.
- final equals/hashCode in the base class prevents subtypes from independently changing the equality policy.
- canEqual is a pattern for both sides to confirm they can be compared with each other; having canEqual alone does not automatically prove transitivity or a correct hashCode.

Checking the concrete class is often suitable when subtypes carry their own equality fields. However, it may not be suitable for ORM proxies or entities whose runtime class is generated by a framework. IDs assigned after persistence also make equality harder because the hash value can change during the object's lifecycle. For entities, follow the semantics and lifecycle of the specific framework.

Records are final and automatically define equals/hashCode based on components, making them suitable for many value objects. If a component is an array, the generated equality does not automatically become deep equality because arrays are usually compared by reference. A sealed hierarchy restricts allowed subtypes, but it does not automatically choose an equality policy for you.

## 6. Error-Prone Data Types and States

- **Mutable fields:** if a field used for equals/hashCode changes after the object has been placed into a HashSet or used as a HashMap key, lookups may fail. Prefer immutable keys.
- **Arrays:** Objects.equals(arrayA, arrayB) does not compare array elements; use Arrays.equals or Arrays.deepEquals depending on the structure, and the corresponding hash counterpart.
- **BigDecimal:** equals distinguishes scale; 2.0 and 2.00 may not be equal even though compareTo returns 0. Clearly choose the semantics before designing hash.
- **Floating-point numbers:** NaN and +0.0/-0.0 require comparison rules compatible with hashing; use consistent handling such as Double.compare and Double.hashCode where appropriate.
- **Subclasses with new fields:** if base equality considers all subtypes with the same ID equal, a subclass must not add its own fields to equality while still keeping that shared rule.

An interface can be used as the reference type when calling equals; the implementation is still dispatched by the runtime class. Merely implementing the same interface or returning the same id() does not mean two implementations must be equal. equals(Customer) also does not replace equals(Object); use @Override to detect signature errors.

## 7. Testing the Entire Hierarchy

Use a matrix consisting of: the same object, objects with the same data and same subtype, different data and same subtype, different subtypes with the same key, different subtypes with different keys, and null. For each appropriate pair and triple, verify reflexivity, symmetry, transitivity, consistency, and the equal implies same hash rule. Then verify that HashSet does not add equal duplicates and HashMap.get finds the value when using a different key that is equal to the original key.

Do not test only parent.equals(child); always test child.equals(parent) as well. With multiple inheritance levels, test every relevant pair of subtypes. If using assert in Java, remember that assertions are disabled by default unless run with -ea; a test framework can help execute checks more reliably.

Before writing code, answer: does the object have identity or value semantics; may different subtypes be equal; which fields participate in equality; who is allowed to change the policy; and does the framework have proxies or late-assigned IDs. A clear policy is more important than choosing instanceof or getClass() alone.
