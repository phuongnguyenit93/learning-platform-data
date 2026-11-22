# Explicitly declared accessors and actual record metadata

## 1. A record accessor is a real method

For `record Label(String text)`, the `text` component has an accessor method of the same name: `text()`. If the author does not declare it, the compiler provides an implementation that returns the component field's value.

The author can also declare an accessor explicitly inside the record body. In that case, that method is the component's accessor; there is no additional implicit accessor with the same signature for Reflection to choose between.

This creates three layers of information to distinguish:

- **RecordComponent:** name, type, annotations, and information about the component in the record header.
- **Accessor method:** the actual access method, along with its metadata and implementation body.
- **Component field:** where the corresponding value is stored, with `private final` characteristics.

`RecordComponent.getAccessor()` connects the component to the exact `Method` object describing its accessor. This API does not guarantee that the accessor performs only a simple field read if the author wrote its body manually.

## 2. Rules for explicit accessors

An explicit accessor of a component must:

- Have the same name as the component.
- Be a `public` instance method.
- Have no parameters.
- Have the same return type as the component's declared type.
- Declare no method-specific type parameters.
- Have no `throws` clause.

Example of a valid declaration in the language:

~~~java
record Measurement(int value) {
    public int value() {
        return value;
    }
}
~~~

This is a record declaration, not a program with `main`.

Do not rename the accessor to `getValue()` following JavaBean conventions and assume it replaces `value()`. A method with a different name is just another method on the record. Similarly, an overload like `value(int scale)` is not the accessor of component `value`.

A handwritten accessor does not have to override a method from a superclass or interface. Still, Java has a special rule for records: **you are allowed to put `@Override` on an explicit accessor of a component**, even when there is no corresponding method in a supertype. This annotation helps the compiler catch when a component is renamed or removed and the old method is no longer an accessor. The rule is stated in [JLS §9.6.4.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.4.4).

## 3. Example: metadata identifies the accessor, invocation runs the actual body

The example below intentionally puts string normalization inside the accessor to observe the difference between the stored value and the returned value. The `Label` design in the example fails the record copy rule; a later section shows how to fix it.

Save as `ExplicitAccessorBehaviorDemo.java`:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;
import java.util.Locale;
import java.util.Objects;

public class ExplicitAccessorBehaviorDemo {
    public record Label(String text) {
        public String text() {
            return text.strip().toUpperCase(Locale.ROOT);
        }
    }

    public record NormalizedLabel(String text) {
        public NormalizedLabel {
            text = Objects.requireNonNull(text, "text")
                    .strip().toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<Label> type = Label.class;
        RecordComponent component = type.getRecordComponents()[0];
        Method accessor = component.getAccessor();
        Label original = new Label("  lan  ");

        System.out.println("component=" + component.getName());
        System.out.println("accessor=" + accessor.getName());
        System.out.println("parameters=" + accessor.getParameterCount());
        System.out.println("return=" + accessor.getReturnType().getSimpleName());
        System.out.println("sameMethod="
                + accessor.equals(type.getDeclaredMethod("text")));
        System.out.println("synthetic=" + accessor.isSynthetic());
        System.out.println("viaAccessor=[" + accessor.invoke(original) + "]");

        Field field = type.getDeclaredField(component.getName());
        field.setAccessible(true);
        System.out.println("viaField=[" + field.get(original) + "]");

        Label copy = new Label(original.text());
        System.out.println("copyEquals=" + original.equals(copy));

        NormalizedLabel normalized = new NormalizedLabel("  lan  ");
        NormalizedLabel normalizedCopy =
                new NormalizedLabel(normalized.text());
        System.out.println("normalized=[" + normalized.text() + "]");
        System.out.println("normalizedCopyEquals="
                + normalized.equals(normalizedCopy));
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 ExplicitAccessorBehaviorDemo.java
java ExplicitAccessorBehaviorDemo
~~~

Output:

~~~text
component=text
accessor=text
parameters=0
return=String
sameMethod=true
synthetic=false
viaAccessor=[LAN]
viaField=[  lan  ]
copyEquals=false
normalized=[LAN]
normalizedCopyEquals=true
~~~

The square brackets make whitespace in the field value easy to see. The explicit accessor returns `LAN`, while the field still holds the string `"  lan  "` passed to the constructor.

`getAccessor()` returns metadata for the actual `text()` method. Comparing with `Method.equals` against the method found by `getDeclaredMethod("text")` evaluates to true. Do not use `==` to require two metadata lookups to return the same `Method` object reference.

The call `accessor.invoke(original)` runs the body written by the author. Reflection does not skip the normalization logic to read the field directly.

Enabling field access in the example is solely to observe the stored value inside the same outer class; there is no field write operation. A tool using a record's public interface should not by default replace accessor calls with private field reads.

## 4. Consequences for the record contract

The default implementations of `equals`, `hashCode`, and `toString` rely on component fields rather than calling an explicit accessor to obtain a transformed value.

A record should uphold the copy rule: if you create a new record using the values returned by the old record's accessors, the two records should be equal according to `equals`.

In `Label` of the example:

1. The original object stores `"  lan  "`.
2. The accessor returns `"LAN"`.
3. The copy created from the accessor stores `"LAN"`.
4. Default `equals` compares the two different field values, so it returns `false`.

That code compiles, yet the design breaks the copy rule. The compiler cannot verify all behaviors of an author-written accessor.

`NormalizedLabel` moves the normalization step into the compact constructor. The stored value is `LAN` from the start; the implicit accessor returns that exact value. A copy goes through the same normalization rule and remains equal to the original object.

If you merely need a different display string, a clean option is keeping the accessor returning component data and adding a separately named method for the display representation. Whichever approach is chosen, the author must consider consistency with the constructor and the record's characteristic methods.

Metadata such as name and return type is not enough to prove an accessor "only reads a field." A method can compute, throw unchecked exceptions, or perform other work while having the exact same signature.

## 5. Component annotations and accessor annotations are two separate locations

Annotations in the record header can be propagated to implicitly declared members if `@Target` permits. For an **explicitly declared accessor**, annotations on the component are not automatically propagated to that method.

Therefore, adding an explicit accessor can change the observable method metadata, even though the component name and component type remain the same.

Save as `ExplicitAccessorAnnotationsDemo.java`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;

public class ExplicitAccessorAnnotationsDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.RECORD_COMPONENT, ElementType.METHOD})
    public @interface HeaderTag {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface AccessorTag {
        String value();
    }

    public record Implicit(
            @HeaderTag("from-header") String text) {
    }

    public record Explicit(
            @HeaderTag("from-header") String text) {

        @AccessorTag("from-method")
        public String text() {
            return text;
        }
    }

    private static void report(Class<?> recordType) {
        RecordComponent component = recordType.getRecordComponents()[0];
        Method accessor = component.getAccessor();

        System.out.println(recordType.getSimpleName()
                + ": componentHeader="
                + component.isAnnotationPresent(HeaderTag.class)
                + ", accessorHeader="
                + accessor.isAnnotationPresent(HeaderTag.class)
                + ", accessorOwn="
                + accessor.isAnnotationPresent(AccessorTag.class));
    }

    public static void main(String[] args) {
        report(Implicit.class);
        report(Explicit.class);
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 ExplicitAccessorAnnotationsDemo.java
java ExplicitAccessorAnnotationsDemo
~~~

Output:

~~~text
Implicit: componentHeader=true, accessorHeader=true, accessorOwn=false
Explicit: componentHeader=true, accessorHeader=false, accessorOwn=true
~~~

Explanation:

- `HeaderTag` is allowed on both components and methods, and is retained at runtime.
- Both components have `HeaderTag`.
- `Implicit`'s implicit accessor receives the annotation propagated from the component.
- `Explicit`'s explicit accessor does not automatically receive `HeaderTag`; it has `AccessorTag` written directly on the method.

If a framework reads annotations from the accessor, an author adding an explicit method can cause the framework to stop seeing the old annotation on the method. That does not mean the annotation disappeared from the component.

If the contract requires the explicit accessor to also carry the same annotation, the author can declare the annotation on the method when `@Target` allows. A tool can also read multiple locations according to a defined policy, but it should not assume every location always holds the same data.

## 6. Choosing the right API for the needed metadata kind

| Information to retrieve | Suitable API |
| --- | --- |
| Component name in the record header | `RecordComponent.getName()` |
| Component type at the Class level | `RecordComponent.getType()` |
| Generic type of the component | `RecordComponent.getGenericType()` |
| Declaration annotations on the component at runtime | `RecordComponent.getAnnotations()` or `getAnnotation(...)` |
| Annotated type metadata of the component | `RecordComponent.getAnnotatedType()` |
| Actual accessor method | `RecordComponent.getAccessor()` |
| Annotations of the actual accessor method | `Method.getAnnotations()` or `getAnnotation(...)` |
| Annotated return type metadata of the accessor | `Method.getAnnotatedReturnType()` |
| Value provided by the accessor for an instance | `Method.invoke(instance)` |

Declaration annotations and type-use annotations (`TYPE_USE`) are also two aspects that must be read with their respective APIs. When an accessor is explicitly written, inspect the metadata of the actual method and return type; do not assume it was copied from the component.

For generics, `getType()`/`getReturnType()` give `Class`-level information, while `getGenericType()`/`getGenericReturnType()` retain the appropriate generic description. Do not use an erased type name string as proof that all metadata at both locations is identical.

You should preserve annotation source information when aggregating: did the annotation come from the component or from the method? If both locations have the same annotation type with different values, the tool must have a clear precedence rule or conflict reporting.

No single merging rule fits every library. A record-structure processor may treat the component as primary; a public-method processor may treat the method as primary. Both must enforce their policy based on the data read.

## 7. getAccessor is not a tool for distinguishing author from compiler

An implicit accessor is also a real method on the class after compilation. An explicit accessor is also returned through the same `getAccessor()` API.

There is no `isExplicitAccessor()` flag on `RecordComponent`. Nor should you use `Method.isSynthetic()` as a definitive check for "implicit vs. author-written": implicit members specified by Java are not necessarily synthetic.

In the first example, the explicit accessor has `synthetic=false`. A compiler-provided accessor can also yield that result. This flag value does not prove an explicit origin of the body.

If a tool needs to know for certain whether an accessor was written in a source file, it needs additional source data or an appropriate analysis tool. Do not infer that from whether the method shares the component's name, whether it has annotations, or whether it appears to return only a field.

The purpose of `getAccessor()` is to find the component's exact accessor method, not to reconstruct the authoring history of the method.

## 8. Application in a record-reading tool

A record reader can proceed in sequence:

1. Check `Class.isRecord()`.
2. Retrieve `getRecordComponents()` to preserve component structure and order.
3. For each component, get `getAccessor()` and read the needed method metadata.
4. Keep component, method, and annotated-type metadata separate.
5. Invoke the accessor only when the value is actually needed and the input object is valid.

Do not find an accessor by taking the first element in `getDeclaredMethods()` with the same name. Overloaded methods or bridge methods can cause such a simple selection to pick the wrong target; metadata array order must not be used as a selection rule either.

When invoking an explicit accessor:

- It can return a transformed value, as observed in the example.
- It can throw unchecked exceptions even without a `throws` clause in its declaration.
- Exceptions from the body are wrapped by `Method.invoke` in `InvocationTargetException`.
- The invocation is still subject to Reflection access rules.

If an accessor fails, automatically falling back to reading the private field can alter the reader's semantics and bypass the record's public logic. Handle errors according to the tool's contract instead of silently treating the two ways of obtaining values as equivalent.

A metadata viewer that only needs names, types, and annotations can stop at the descriptor-reading steps. It does not need to execute the accessor to know which accessor belongs to which component.

## 9. Common pitfalls

| Wrong assumption | Consequence |
| --- | --- |
| A record accessor is always compiler-generated code to read a field | Overlooks author-written implementation |
| `getAccessor()` returns a default method separate from the explicit method | Misunderstands the actual method being used |
| Having the same name/type means field and accessor always return the same value | May read wrong data semantics |
| Annotations on a component are always present on the accessor | Fails for explicit accessors or annotations without an applicable target |
| Not seeing an annotation on the method means the component has no annotation | Misses metadata at the other location |
| Non-synthetic methods are definitely author-written | Misclassifies implicit accessors |
| Default `equals` calls a customized accessor | Overlooks the field values used for comparison |
| Customizing an accessor without considering constructor/copy | May break the record's copy rule |

## 10. Self-check

1. When a record declares an accessor itself, which method does `RecordComponent.getAccessor()` return?
2. Why might a reader calling the accessor receive a different value than a field reader?
3. Is `@Target(METHOD)` enough to guarantee an annotation on a component propagates to an explicit accessor?
4. If an annotation remains on the component but is absent on the accessor, do the two Reflection results contradict each other?
5. Can `isSynthetic()` be used to determine with certainty that an accessor was written by the author?
6. Why does moving normalization into the constructor help `NormalizedLabel` preserve the copy rule in the example?

Answers:

1. The actual explicitly declared accessor method.
2. The accessor has its own executable body; reading the field gets the stored value.
3. No. An explicit accessor does not automatically receive annotations propagated from the component; the target is only a condition for allowed locations.
4. No. They describe two different annotated elements.
5. No; additional data is needed to determine the origin of the body.
6. The stored value is already normalized; the accessor returns that value and copying via the constructor preserves the same value.

## References

- [JLS 17 — Record members, explicit accessors, and annotations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3).
- [Java 17 — RecordComponent.getAccessor and component metadata](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html#getAccessor()).
- [Java 17 — Record and the copy rule](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html).
