# Why Did Java Add Default Methods?

Before Java 8, an interface primarily described the methods that implementing classes had to provide. When a library wanted to add an operation to a public interface already implemented by many projects, adding a new abstract method usually forced concrete classes to be modified and recompiled. For a popular API, the number of implementers can be far greater than what the library author can control.

## 1. The API Evolution Problem

Suppose the first version of the library has the contract:

```java
interface ReportExporter {
    String export(String content);
}
```

Classes such as `CsvExporter` only know how to implement `export`. If the next version adds `String exportNormalized(String content);` as an abstract method, older classes will lack an implementation when recompiled.

Java 8 added **default methods** so an interface can provide a ready-to-use default behavior:

```java
interface ReportExporter {
    String export(String content);

    default String exportNormalized(String content) {
        return export(content.trim());
    }
}

final class CsvExporter implements ReportExporter {
    @Override
    public String export(String content) {
        return "CSV:" + content;
    }
}
```

`CsvExporter` does not need to write `exportNormalized` itself. The default method normalizes the content and then calls the abstract method `export`; that call is dispatched to the actual object's implementation. The class can still override it if its normalization rule differs.

## 2. Benefits for Java's Standard API

This feature was especially useful when Java 8 added lambdas, method references, and the Stream API. Widely implemented interfaces could receive new operations without forcing every provider to duplicate the same logic.

| Interface | Example default methods | Purpose |
| --- | --- | --- |
| `Iterable` | `forEach(Consumer)` | Iterate using a lambda or method reference. |
| `Collection` | `stream()`, `parallelStream()`, `removeIf(Predicate)` | Build pipelines and perform conditional operations. |
| `List` | `replaceAll(UnaryOperator)`, `sort(Comparator)` | Transform or sort elements. |
| `Map` | `getOrDefault`, `forEach`, `computeIfAbsent` | Convenience operations on mappings. |

A specialized implementation can still override them to suit its own data structure, performance, or guarantees. Default methods do not guarantee that the general-purpose algorithm is optimal for every class.

## 3. Three Types of Compatibility to Distinguish

- **Source compatibility:** When an older class is recompiled, a default method usually lets it continue satisfying the interface without needing to add a new method.
- **Binary compatibility:** Already-compiled programs can continue to link in many cases because the JVM can select the default implementation when called.
- **Behavioral compatibility:** The new behavior must still make sense for every valid implementation. A default method based on wrong assumptions about data or state can cause business-logic errors even though the program still compiles.

This is compatibility support, not an absolute guarantee. A new default method can conflict with a method that already exists in another class or interface. When multiple default methods compete, inheritance rules must be considered, and an override may be needed to resolve the conflict.

## 4. When Should You Add a Default Method?

Consider adding one when the new behavior can be built from operations already in the contract and that default makes sense for every implementation. If each class must do something different, an abstract method may express the requirement more clearly. If the algorithm requires instance state, constructors, or an atomic transaction, consider a base class or a component object.

Before releasing the API, check representative implementers, potentially conflicting signatures, preconditions, exceptions, side effects, and concurrency characteristics. The goal is to add a safe shared behavior, not just to make the source code shorter.

## Self-Check

1. Why can adding an abstract method to a popular interface cause older implementing classes to fail to recompile?
2. How do default methods reduce that burden?
3. Why can a new default method still cause compatibility errors?
4. When is an abstract method or a service more suitable than a default method?

**Remember:** Default methods help interfaces evolve alongside new APIs while many existing classes can still use shared behavior. Compatibility still depends on inheritance rules and the correctness of the contract.
