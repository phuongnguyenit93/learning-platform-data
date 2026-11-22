# Declaring equals, hashCode, and toString in an Interface Contract

An interface can explicitly declare the three familiar public signatures of Object to clarify API documentation intent. Redeclaring them does not provide an algorithm, nor does it force all implementations to have the same equality semantics or the same string format.

## 1. Declaring Signatures

~~~java
interface EntityContract {
    boolean equals(Object other);
    int hashCode();
    String toString();
}
~~~

The interface methods above are public abstract by default. They do not need a method body. An implementing class can inherit the matching public methods from Object without having to override them solely because the interface repeated the signatures.

~~~java
final class Ticket implements EntityContract {
    // No need to override toString(), equals(), or hashCode()
    // if Object's default behavior fits the class's purpose.
}
~~~

The default behavior is often insufficient for value objects or business entities. By default, Object.equals() compares reference identity; Object.toString() produces a generic string for diagnostics. When data-based comparison or a readable representation is needed, the concrete class must explicitly define the logic. The interface only documents the expectation; it does not generate common logic on its own.

## 2. The equals Contract

A correct equals implementation must guarantee:

| Property | Requirement |
| --- | --- |
| Reflexive | x.equals(x) is true for non-null x |
| Symmetric | x.equals(y) and y.equals(x) yield the same result |
| Transitive | if x equals y and y equals z, then x equals z |
| Consistent | the result remains unchanged when the data used for comparison does not change |
| Null | x.equals(null) is false |

The method should check the type before accessing the other object's data. The signature to override is equals(Object), not equals(Product). If you only declare equals(Product), that is an overload; calls from HashSet or HashMap still use equals(Object).

## 3. The hashCode Contract

Mandatory rule: if a.equals(b) is true, then a.hashCode() and b.hashCode() must be equal. The reverse is not required; hash collisions are valid. When overriding equals based on value, you usually need to override hashCode based on the same data that defines equality.

HashMap and HashSet use the hash code to select the lookup bucket, then rely on equals to identify the matching key or element. If an object is used as a key and a field participating in equality/hashing changes, looking up or removing the element may fail. Prefer immutable fields for key equality. A hash code is not a unique ID and does not need to remain identical across program runs.

## 4. Runnable Example

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

interface EntityContract {
    boolean equals(Object other);
    int hashCode();
    String toString();
}

final class Product implements EntityContract {
    private final String code;
    private final String name;

    Product(String code, String name) {
        this.code = Objects.requireNonNull(code);
        this.name = Objects.requireNonNull(name);
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof Product product
                    && code.equals(product.code));
    }

    @Override
    public int hashCode() {
        return code.hashCode();
    }

    @Override
    public String toString() {
        return "Product{code='" + code + "', name='" + name + "'}";
    }
}

public class ObjectContractDemo {
    public static void main(String[] args) {
        Product first = new Product("P1", "Pen");
        Product sameCode = new Product("P1", "Pencil");
        Product other = new Product("P2", "Pen");

        System.out.println(first == sameCode);
        System.out.println(first.equals(sameCode));
        System.out.println(first.hashCode() == sameCode.hashCode());
        System.out.println(first.equals(other));

        Set<Product> products = new HashSet<>();
        products.add(first);
        products.add(sameCode);
        System.out.println(products.size());
        System.out.println(first);
    }
}
~~~

Output:

~~~text
false
true
true
false
1
Product{code='P1', name='Pen'}
~~~

Product defines two products with the same code as equal, regardless of name. Because hashCode is also based on code, the two equal objects have the same hash code and HashSet keeps only one representative element. Product is final so that no subtype can independently alter the equality policy.

## 5. toString Is a Representation, Not a Data Format

The default Object.toString() typically produces a string consisting of the class name, the @ character, and the hexadecimal form of the hash code; that string is not a business description. Overriding it can produce a readable string, but Java does not require that string to be unique or stable for serialization. Do not use toString() as a data transfer protocol or a long-lived ID unless the API specifically defines that format. Avoid including secrets or sensitive data in log strings.

## 6. Common Mistakes

- Overriding only equals while forgetting hashCode: two equal objects may have different hash codes, causing collections to behave incorrectly.
- Using equal hashCode values to conclude equals: two different objects can have a hash collision.
- Writing equals(Product) thinking it overrides equals(Object): that is an overload.
- Using different fields for equals and hashCode: this can break the equal implies same hash rule.
- Assuming that declaring them in an interface already provides the logic: abstract signatures only declare the methods, without defining semantics.

## 7. When Should You Declare Them Explicitly?

Consider doing so when equality or representation semantics is an important part of the interface documentation. If an interface only describes specific behavior, redeclaring the three signatures usually adds no new calling capability. In both cases, the API documentation must clearly state which data determines equality and what implementations must adhere to.

Do not write default equals(Object), default hashCode(), or default toString() in an interface. Compilation restrictions and design reasons are explained separately in the lesson on default methods and Object.

Self-check:
- If a.equals(b) is true, must their hash codes be equal? Yes.
- Do two equal hash codes prove that equals is true? No.
- Does declaring String toString() in an interface force a class to override it? Not necessarily; the public implementation from Object can satisfy it.
- If an object is already in a HashSet and its equality field changes, what can happen? HashSet may not be able to find the element using the new hash.
