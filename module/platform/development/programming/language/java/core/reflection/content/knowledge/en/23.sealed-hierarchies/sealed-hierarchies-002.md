# Permitted Direct Subclasses or Subinterfaces in a Sealed Hierarchy

## 1. "Direct" Is a Relationship, Not All Subtypes

A sealed type controls which classes or interfaces are allowed to sit **immediately beneath it** in the inheritance relationship. Deeper types are governed by the constraints of their respective intermediate branch.

For example, if `MobileWallet` implements `Wallet` and `Wallet` extends `PaymentMethod`, then `MobileWallet` is a kind of `PaymentMethod`, but it is not a direct subtype of `PaymentMethod`.

This distinction is critical when reading:

~~~java
Class<?>[] children = parent.getPermittedSubclasses();
~~~

This is an illustrative snippet inside a method with a `Class<?> parent` variable. The result, when `parent` is sealed, describes the **directly permitted** subtypes obtainable in the runtime environment. It does not automatically flatten the entire hierarchy into one list.

A tool that displays models, checks architecture, or selects processing branches must preserve this exact relationship. If it treats every indirect subtype as a direct entry, the tool changes the meaning of the model.

## 2. permits and extends/implements Handle Two Different Parts

`permits` specifies who is allowed to be a direct subtype. `extends` or `implements` declares the actual type relationship from the subtype's side.

| Sealed parent type | Valid direct subtype | How the subtype declares the relationship |
| --- | --- | --- |
| A class | A class | `extends Parent` |
| An interface | A class | `implements Parent` |
| An interface | An interface | `extends Parent` |

An interface cannot extend a class, so the permitted list of a sealed class never becomes a list of interfaces implementing it.

Merely listing a name in `permits` does not automatically make that class extend or implement the parent type. Conversely, a type that is not permitted cannot add itself as a direct relationship to a sealed type simply by writing `extends` or `implements`.

A direct subtype must also specify its own further extensibility:

- `final` class: stops inheritance at that class.
- `sealed` class or interface: continues controlling its own direct subtypes.
- `non-sealed` class or interface: reopens extensibility on that branch.
- Certain declaration forms have appropriate implicit properties, such as records being `final`.

Interfaces do not use `final`. If an interface is a direct subinterface of a sealed interface, it continues as `sealed` or `non-sealed`.

## 3. Runnable Example: A List Containing Both Classes and Interfaces

Save as `DirectPermittedTypesDemo.java`:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.stream.Collectors;

public class DirectPermittedTypesDemo {
    sealed interface PaymentMethod
            permits Card, Wallet, ExternalPayment {
    }

    record Card(String network) implements PaymentMethod {
    }

    sealed interface Wallet extends PaymentMethod
            permits MobileWallet, BrowserWallet {
    }

    record MobileWallet(String account) implements Wallet {
    }

    record BrowserWallet(String account) implements Wallet {
    }

    static non-sealed class ExternalPayment implements PaymentMethod {
    }

    static final class VendorPayment extends ExternalPayment {
    }

    private static boolean hasDirectRelation(
            Class<?> parent, Class<?> candidate) {
        if (parent.isInterface()) {
            return Arrays.asList(candidate.getInterfaces()).contains(parent);
        }
        return candidate.getSuperclass() == parent;
    }

    private static String childNames(Class<?> sealedType) {
        return Arrays.stream(sealedType.getPermittedSubclasses())
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        Class<?> root = PaymentMethod.class;
        Class<?>[] children = root.getPermittedSubclasses();
        Arrays.sort(children, Comparator.comparing(Class::getName));

        System.out.println("PaymentMethod.children="
                + childNames(root));

        for (Class<?> child : children) {
            System.out.println(child.getSimpleName()
                    + ": kind=" + (child.isInterface() ? "interface" : "class")
                    + ", direct=" + hasDirectRelation(root, child));
        }

        System.out.println("Wallet.children=" + childNames(Wallet.class));
        System.out.println("MobileWallet.directToRoot="
                + hasDirectRelation(root, MobileWallet.class));
        System.out.println("MobileWallet.assignableToRoot="
                + root.isAssignableFrom(MobileWallet.class));
        System.out.println("VendorPayment.directToRoot="
                + hasDirectRelation(root, VendorPayment.class));
        System.out.println("VendorPayment.assignableToRoot="
                + root.isAssignableFrom(VendorPayment.class));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 DirectPermittedTypesDemo.java
java DirectPermittedTypesDemo
~~~

Output:

~~~text
PaymentMethod.children=Card,ExternalPayment,Wallet
Card: kind=class, direct=true
ExternalPayment: kind=class, direct=true
Wallet: kind=interface, direct=true
Wallet.children=BrowserWallet,MobileWallet
MobileWallet.directToRoot=false
MobileWallet.assignableToRoot=true
VendorPayment.directToRoot=false
VendorPayment.assignableToRoot=true
~~~

Three key points:

1. `getPermittedSubclasses()` on an interface can return a subinterface such as `Wallet`, even though the API name contains the word "Subclasses".
2. `MobileWallet` belongs to the `Wallet` branch, and `VendorPayment` belongs to the `ExternalPayment` branch. Neither appears in the root's direct list.
3. `isAssignableFrom` accepts indirect relationships, so both of those types are still assignable to `PaymentMethod`.

The `childNames` helper in the example is only called with types already known to be sealed. If used on an arbitrary `Class`, you must handle the case where `getPermittedSubclasses()` returns `null`.

Sorting is performed so the output is stable. Do not treat the array order returned by Reflection as a required ordering of the list in source code.

## 4. Verifying a Direct Edge via Reflection

The relationship can be observed from the subtype's side:

- When the parent is a class, `candidate.getSuperclass() == parent` checks the direct superclass.
- When the parent is an interface, `candidate.getInterfaces()` returns the direct interfaces that `candidate` implements or extends.
- `parent.isAssignableFrom(candidate)` answers the broader type relationship, including indirect ones.

For example, `VendorPayment` extends `ExternalPayment`. It receives its relationship to `PaymentMethod` through its superclass, and does not have `PaymentMethod` in its own direct interface list.

A class can directly implement multiple interfaces. If several of those interfaces are sealed, the direct relationship must be valid for each corresponding interface. Therefore, an interface hierarchy can be a graph, not always a tree with a single parent.

The `hasDirectRelation` helper above illustrates how to read edges. It is not a way to grant new permissions or bypass sealed rules. For valid results returned from `getPermittedSubclasses()`, the API already uses the direct-subtype concept; a tool can read the reverse edge to explain and validate its own data.

If you need to traverse deeper, keep each parent–child edge separate and continue querying on sealed branches. Do not dump all descendants into the root's direct children list just to simplify a UI.

## 5. The List Can Be Inferred Without Writing permits

A sealed declaration may omit the `permits` clause if the compiler can infer the direct subtypes according to the rules within the same compilation unit. For an ordinary sealed class, classes with suitable canonical names, declared in the same compilation unit, and directly using `extends` on that class are used to infer the list.

Reflection can still read the permitted list recorded in the compiled output. It does not require the application to re-parse the source text to look for the `permits` keyword.

Save as `InferredDirectChildrenDemo.java`:

~~~java
import java.util.Arrays;
import java.util.stream.Collectors;

public class InferredDirectChildrenDemo {
    static abstract sealed class Document {
    }

    static final class Invoice extends Document {
    }

    static abstract sealed class Report extends Document
            permits SummaryReport {
    }

    static final class SummaryReport extends Report {
    }

    private static String childNames(Class<?> type) {
        return Arrays.stream(type.getPermittedSubclasses())
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        System.out.println("Document.children="
                + childNames(Document.class));
        System.out.println("Report.children="
                + childNames(Report.class));
        System.out.println("Document.memberClasses="
                + Document.class.getDeclaredClasses().length);
        System.out.println("SummaryReport.directToDocument="
                + (SummaryReport.class.getSuperclass() == Document.class));
        System.out.println("Document.assignableFromSummaryReport="
                + Document.class.isAssignableFrom(SummaryReport.class));
        System.out.println("Invoice.superclass="
                + Invoice.class.getSuperclass().getSimpleName());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 InferredDirectChildrenDemo.java
java InferredDirectChildrenDemo
~~~

Output:

~~~text
Document.children=Invoice,Report
Report.children=SummaryReport
Document.memberClasses=0
SummaryReport.directToDocument=false
Document.assignableFromSummaryReport=true
Invoice.superclass=Document
~~~

`Document` does not write `permits`, yet both `Invoice` and `Report` directly extend it in the same file. `Document`'s list does not include `SummaryReport`, because that class's direct parent is `Report`.

All classes are nested inside the outer class `InferredDirectChildrenDemo` so the example fits cleanly in a single file. They are members of the outer class; they are not member classes declared inside `Document`.

Therefore, `Document.class.getDeclaredClasses()` returns an empty array in the example. **Member classes** and **inherited subclasses** are two different kinds of relationships. `getDeclaredClasses()` is not a replacement API for the permitted list.

## 6. Declaration Boundaries of Direct Types

Placing the types in the example is not only for reading convenience. Java enforces constraints on where permitted direct subtypes are declared:

- For a sealed type in a named module, the permitted direct subtypes must belong to the same module.
- For a sealed type in an unnamed module, they must belong to the same package.

In a named module, being in the same module does not necessarily mean being in the same package; the relevant access and type-reference rules must still be satisfied.

The goal is to keep the direct extension boundary within the model's scope of management. An external class cannot become a new direct branch simply by appearing on the classpath.

For a `non-sealed` branch, deeper types do not have to be added by name to the root's `permits` list. In the first example, `VendorPayment` extends `ExternalPayment`; it does not need to be, and should not be, treated as a direct element of `PaymentMethod`.

If you want to change who is a direct subtype, that requires changing the type declaration and the corresponding compiled output. Mutating a `Class<?>[]` array received from Reflection does not update the JVM's inheritance permissions.

## 7. What a Permitted Result Does and Does Not Include

An element in the list indicates a permitted direct type relationship; it does not answer all other questions:

| Question | Can it be inferred solely from being in the list? |
| --- | --- |
| Is this a direct branch of the sealed type under inspection? | Yes, for valid elements returned by the API |
| Is this guaranteed to be a class? | No; when the parent is an interface, it may be an interface |
| Is this guaranteed to be a concrete instantiable type? | No; it may be abstract or an interface |
| Does it have a public no-arg constructor? | No |
| Are any instances of that type currently alive? | No |
| Is that type registered as a bean/plugin in the application? | No |
| Are all deeper subtypes in this array? | No |

The API attempts to obtain `Class` objects for permitted types using the parent type's defining class loader. Entries whose `Class` cannot be obtained may be omitted per the API contract. Therefore, when an auditing report covering every name in binary metadata is needed, you must also inspect the class files and loading environment, not just the returned array.

For an unsealed type, the method returns `null`. For a sealed type, it returns a non-null array that may be empty per the contract. Preserve this distinction if the tool needs to know whether a type is open or sealed without obtained elements.

Retrieving the list is not an object creation step. A tool inspecting type relationships can work with names, type kinds, and direct edges without calling constructors on the types in the array.

## 8. How to Present and Verify the Model Properly

When building a tool that uses the permitted list, a clear workflow is:

1. Confirm the parent type and its sealed status.
2. Retrieve the direct elements.
3. Classify each element as a class or an interface.
4. Keep the direct relationship and the `Class` object as the type's identity in the JVM.
5. If needed, expand sealed nodes separately, clearly marking `non-sealed` branches or points with incomplete information.
6. Sort the presentation according to explicit rules.

Simple names are fine for short examples, but are not unique keys for all types in an application. Different packages or class loaders can produce types with the same display name. Do not mistakenly merge two nodes just because `getSimpleName()` matches.

If verifying the model in a test, compare the expected set of direct types, or the required relationships. Do not hardcode the array order returned by the API. If the application must ensure classes are completely packaged, verify that the environment provides them instead of assuming a missing entry proves the source code never permitted it.

Also do not instantiate each class just to "verify it is permitted". Being in the hierarchy and creating a valid object are steps with different contracts.

## 9. Self-Check

1. `MobileWallet` is a kind of `PaymentMethod`; why is it not in `PaymentMethod`'s direct list?
2. Does the word "Subclasses" in the API name exclude subinterfaces?
3. Can a class listed in `permits` omit `extends`/`implements` and still receive the relationship automatically from that list?
4. Can `getDeclaredClasses()` be used to find all permitted subtypes?
5. Is the absence of a `permits` clause in source code enough to conclude that Reflection cannot return a list?
6. Must a subclass of a `non-sealed` branch be added to the root's direct permitted list?

Answers:

1. It directly implements `Wallet`; its relationship to `PaymentMethod` goes through that branch.
2. No. A sealed interface can permit both directly implementing classes and directly extending interfaces.
3. No. The permitted list and the relationship declaration must match each other.
4. No. That API is for member types declared inside a type.
5. No. The compiler can infer the list according to the corresponding rules.
6. No. It sits deeper in the branch; it does not become a direct edge of the root.

## References

- [Java 17 — Class.getPermittedSubclasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()).
- [Java 17 — Class.getInterfaces](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getInterfaces()).
- [JLS 17 — Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6).
- [JLS 17 — Permitted Direct Subclasses and Subinterfaces of a Sealed Interface](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4).
