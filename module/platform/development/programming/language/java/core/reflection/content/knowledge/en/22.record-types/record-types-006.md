# How annotations on records are propagated by `@Target`

When an annotation is written before a record component, you should not assume it sits only on a `RecordComponent` object, nor that it is copied to every related member. **The annotation's target and how the member is declared determine where metadata appears.**

This matters for tools using Reflection: a tool reading annotations on data fields may see something different from a tool reading on accessors or constructor parameters. Two different results are not necessarily a bug; first identify the exact element being queried.

This article uses Java 17 or later and distinguishes declaration annotations from annotations on data type uses.

## 1. One record component relates to multiple declarations

Consider the header:

```java
record Message(String text) {
}
```

`text` is a record component. It relates to:

- The metadata of the component itself: `RecordComponent`.
- The data field `text` provided for the record.
- The accessor `text()`.
- The parameter `text` of the canonical constructor.

These are distinct metadata locations. Annotations written in the header can be propagated by the compiler to appropriate locations. This mechanism is commonly called **annotation propagation**.

It is not `getAnnotation()` automatically searching other locations at runtime. When you query a `Field`, Reflection reads that field's annotations; it does not additionally query `RecordComponent` to merge results.

## 2. `@Target` and `@Retention` answer two different questions

[`@Target`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Target.html) describes the contexts where an annotation is allowed to apply. The compiler checks those constraints.

[`@Retention`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Retention.html) describes retention lifetime. To read the annotations in the experiment with Reflection at runtime, they are declared with `RetentionPolicy.RUNTIME`. If `@Retention` is omitted, the default is `CLASS`, not `RUNTIME`.

Therefore, when an annotation is not found, check both the **metadata location** and the **retention policy**, rather than only looking at whether source code has an `@` sign.

For members provided implicitly for a record, common targets have the following meanings:

| Target in `@Target` | Relevant location to inspect |
| --- | --- |
| `RECORD_COMPONENT` | Metadata of the record component itself |
| `FIELD` | Component field declaration |
| `METHOD` | Implicitly provided accessor declaration |
| `PARAMETER` | Parameter inferred for an implicit or compact canonical constructor |
| `TYPE_USE` | Type use location, such as component type, field type, return type, and inferred parameter type |

These target names belong to [`ElementType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/ElementType.html). `CONSTRUCTOR` refers to **the constructor declaration**, whereas `PARAMETER` refers to **a constructor parameter**; they must not be treated as the same target.

An annotation with only the `CONSTRUCTOR` target cannot be written on a component with the expectation that it will transfer to the constructor. In the example below, `Mark` includes the `CONSTRUCTOR` target, yet using `@Mark` in the header still does not automatically mark the constructor as a whole.

## 3. Complete Java 17+ experiment

The program uses three annotations:

- `Mark`: applies to multiple declaration kinds so each place receiving metadata can be observed.
- `FieldOnly`: applies only to data fields.
- `TypeMark`: applies only to data type uses.

The records differ in whether they let the compiler provide the accessor or constructor, declare them manually, or restate annotations at explicit locations.

Save the entire code into **`RecordAnnotationTargetsDemo.java`**:

```java
import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class RecordAnnotationTargetsDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target({
            ElementType.RECORD_COMPONENT,
            ElementType.FIELD,
            ElementType.METHOD,
            ElementType.PARAMETER,
            ElementType.CONSTRUCTOR
    })
    public @interface Mark {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    public @interface FieldOnly {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface TypeMark {
    }

    public record Generated(@Mark @FieldOnly @TypeMark String text) {
    }

    public record Compact(@Mark @TypeMark String text) {
        public Compact {
            text = Objects.requireNonNull(text, "text");
        }
    }

    public record OwnAccessor(@Mark @TypeMark String text) {
        public String text() {
            return text;
        }
    }

    public record OwnConstructor(@Mark @TypeMark String text) {
        public OwnConstructor(String text) {
            this.text = text;
        }
    }

    public record Restated(@Mark @TypeMark String text) {
        @Mark
        public Restated(@Mark @TypeMark String text) {
            this.text = text;
        }

        @Mark
        public @TypeMark String text() {
            return text;
        }
    }

    public record NestedType(List<@TypeMark String> values) {
    }

    private static String names(Annotation[] annotations) {
        return Arrays.stream(annotations)
                .map(annotation -> annotation.annotationType().getSimpleName())
                .sorted()
                .toList()
                .toString();
    }

    private static void show(Class<?> type) throws NoSuchMethodException,
            NoSuchFieldException {
        RecordComponent component = type.getRecordComponents()[0];
        Field field = type.getDeclaredField(component.getName());
        Method accessor = component.getAccessor();
        Constructor<?> constructor = type.getDeclaredConstructor(component.getType());
        Parameter parameter = constructor.getParameters()[0];

        System.out.println(type.getSimpleName());
        System.out.println("  declarations: component="
                + names(component.getDeclaredAnnotations())
                + "; field=" + names(field.getDeclaredAnnotations())
                + "; accessor=" + names(accessor.getDeclaredAnnotations())
                + "; parameter=" + names(parameter.getDeclaredAnnotations())
                + "; constructor=" + names(constructor.getDeclaredAnnotations()));
        System.out.println("  types: component="
                + names(component.getAnnotatedType().getAnnotations())
                + "; field=" + names(field.getAnnotatedType().getAnnotations())
                + "; return=" + names(accessor.getAnnotatedReturnType().getAnnotations())
                + "; parameter=" + names(parameter.getAnnotatedType().getAnnotations()));
    }

    private static String firstTypeArgument(AnnotatedType type) {
        AnnotatedParameterizedType parameterized = (AnnotatedParameterizedType) type;
        return names(parameterized.getAnnotatedActualTypeArguments()[0].getAnnotations());
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        show(Generated.class);
        show(Compact.class);
        show(OwnAccessor.class);
        show(OwnConstructor.class);
        show(Restated.class);
        show(NestedType.class);

        RecordComponent component = NestedType.class.getRecordComponents()[0];
        Field field = NestedType.class.getDeclaredField("values");
        Method accessor = component.getAccessor();
        Constructor<?> constructor = NestedType.class.getDeclaredConstructor(List.class);
        System.out.println("Nested component argument = "
                + firstTypeArgument(component.getAnnotatedType()));
        System.out.println("Nested field argument = "
                + firstTypeArgument(field.getAnnotatedType()));
        System.out.println("Nested return argument = "
                + firstTypeArgument(accessor.getAnnotatedReturnType()));
        System.out.println("Nested parameter argument = "
                + firstTypeArgument(constructor.getParameters()[0].getAnnotatedType()));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 --release 17 -Xlint:all -Werror RecordAnnotationTargetsDemo.java
java RecordAnnotationTargetsDemo
```

Output:

```text
Generated
  declarations: component=[Mark]; field=[FieldOnly, Mark]; accessor=[Mark]; parameter=[Mark]; constructor=[]
  types: component=[TypeMark]; field=[TypeMark]; return=[TypeMark]; parameter=[TypeMark]
Compact
  declarations: component=[Mark]; field=[Mark]; accessor=[Mark]; parameter=[Mark]; constructor=[]
  types: component=[TypeMark]; field=[TypeMark]; return=[TypeMark]; parameter=[TypeMark]
OwnAccessor
  declarations: component=[Mark]; field=[Mark]; accessor=[]; parameter=[Mark]; constructor=[]
  types: component=[TypeMark]; field=[TypeMark]; return=[]; parameter=[TypeMark]
OwnConstructor
  declarations: component=[Mark]; field=[Mark]; accessor=[Mark]; parameter=[]; constructor=[]
  types: component=[TypeMark]; field=[TypeMark]; return=[TypeMark]; parameter=[]
Restated
  declarations: component=[Mark]; field=[Mark]; accessor=[Mark]; parameter=[Mark]; constructor=[Mark]
  types: component=[TypeMark]; field=[TypeMark]; return=[TypeMark]; parameter=[TypeMark]
NestedType
  declarations: component=[]; field=[]; accessor=[]; parameter=[]; constructor=[]
  types: component=[]; field=[]; return=[]; parameter=[]
Nested component argument = [TypeMark]
Nested field argument = [TypeMark]
Nested return argument = [TypeMark]
Nested parameter argument = [TypeMark]
```

The `names()` method sorts annotation names so the output is easy to compare. Do not use element order inside the annotation array as a precedence rule.

`show()` is a verification helper for known records in the experiment; each record here has a single component. It is not designed as a general scanner for arbitrary classes.

## 4. Reading results when members are implicitly provided

### `Generated`: one source location, multiple metadata targets

The header has `@Mark @FieldOnly @TypeMark String text`, yet the result is not three declared annotations on `RecordComponent`.

| Queried location | Visible declared annotations |
| --- | --- |
| `RecordComponent` | `Mark` |
| Field `text` | `FieldOnly`, `Mark` |
| Accessor `text()` | `Mark` |
| Canonical constructor parameter | `Mark` |
| Constructor declaration itself | None |

`FieldOnly` is valid in the header thanks to the field target, and it appears on the corresponding field. However, `RecordComponent.getDeclaredAnnotations()` does not see `FieldOnly`, because that annotation type does not have the `RECORD_COMPONENT` target.

`TypeMark` does not appear in the declared annotation arrays in the table above. It appears on the `AnnotatedType` objects of the component type, field, accessor return type, and parameter.

`Mark` has the `CONSTRUCTOR` target, yet the `constructor=[]` line remains empty. This shows that "allowed on constructors" does not mean "every annotation usage in the header automatically marks the constructor."

### `Compact`: parameters are still inferred from the header

`Compact` writes the body of the compact canonical constructor itself without writing the parameter list. Parameters are still inferred from the header, so the `text` parameter has `Mark` and the parameter type has `TypeMark`.

Having an explicit constructor body is not enough to conclude that parameter metadata was lost; you must distinguish a **compact constructor** from a **full constructor with a manually declared parameter list**.

## 5. When declaring an accessor or constructor manually

### Explicit accessor

`OwnAccessor` writes `public String text()` itself. In the output, declared annotations on the accessor are `[]`, and annotations on the return type are also `[]`.

Header annotations still exist on the component and field; the implicit canonical constructor still has the appropriate parameter metadata. Only the manually declared accessor does not automatically receive annotations from the header.

If your tool reads metadata on accessors, replacing an implicit accessor with an explicit accessor can change the result, even though the method's name and return type stay the same.

### Full canonical constructor

`OwnConstructor` writes the parameter list `String text` itself. The output shows that parameter has no `Mark`, and its type has no `TypeMark` unless restated in the parameter declaration.

Conversely, the accessor is still implicitly provided, so it receives metadata from the header according to the appropriate targets.

### Restating metadata when needed

`Restated` intentionally writes annotations on the explicit parameter and accessor. Therefore those locations see `Mark` or `TypeMark` again.

The `@Mark` annotation written separately right on `Restated`'s constructor declaration also produces `constructor=[Mark]`. This is an annotation directly on the constructor, not a result of using `@Mark` in the header.

Summary of `Mark`'s behavior across the records in the experiment:

| Record | Component | Field | Accessor | Canonical parameter | Constructor |
| --- | --- | --- | --- | --- | --- |
| `Generated` | Yes | Yes | Yes | Yes | No |
| `Compact` | Yes | Yes | Yes | Yes | No |
| `OwnAccessor` | Yes | Yes | No | Yes | No |
| `OwnConstructor` | Yes | Yes | Yes | No | No |
| `Restated` | Yes | Yes | Yes due to direct annotation | Yes due to direct annotation | Yes due to direct annotation |

The rules for propagation to fields, accessors, and parameters are described in [the JLS on record members](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.3) together with the canonical constructor section. This mechanism is not annotation inheritance via `@Inherited`.

## 6. `TYPE_USE` must be read at the exact position in the type structure

Declaration annotations and type annotations are two different metadata channels:

| What to observe | API |
| --- | --- |
| Component declaration annotations | `component.getDeclaredAnnotations()` |
| Outermost type annotations | `component.getAnnotatedType().getAnnotations()` |
| Generic argument annotations | `((AnnotatedParameterizedType) component.getAnnotatedType()).getAnnotatedActualTypeArguments()` |

The `NestedType(List<@TypeMark String> values)` case in the experiment shows `TypeMark` sits on `String` inside `List`; the annotation array at the `List` root remains empty. The `firstTypeArgument` method in the program inspects that position directly for component, field, accessor return, and parameter type.

Casting to `AnnotatedParameterizedType` is only valid when the type shape is already known as in the experiment. For a general-purpose tool, check the interface with `instanceof` and add support for array types, wildcards, or type variables as needed. Having `TYPE_USE` in `@Target` only specifies the contexts where marking is allowed; it does not make the annotation execute data validation on its own.

## 7. Application in metadata processing tools

Before reading annotations, decide which metadata source is meaningful for the tool:

- Processing record structure: you can select `RecordComponent` metadata.
- Processing data fields: read `Field` and the field type.
- Processing accessor calls: read `Method` and the return type.
- Processing record creation arguments: read canonical constructor `Parameter` and the parameter type.

Do not fall back by default to reading another location just because the current location has no annotation. That can accidentally merge contracts the author intentionally separated, such as an explicitly declared accessor or parameter.

If a tool truly wants to aggregate multiple locations, specify precedence, conflict detection, and how to avoid processing the same meaning repeatedly. An annotation appearing on multiple declarations from a single source position does not tell the tool how many times to enforce a rule.

Annotation propagation does not perform data validation on its own either. For instance, a name like `TypeMark` or an annotation named `NonNull` is only metadata unless a compiler, processor, or runtime code is designed to act on it. The `Objects.requireNonNull` check in `Compact`'s constructor is explicitly written behavior.

## 8. Common pitfalls and self-check

| Wrong inference | How to verify |
| --- | --- |
| An annotation written in the header must be on `RecordComponent` | Check the `RECORD_COMPONENT` target |
| Having `RUNTIME` means it can be found at every location | Check both the applicable targets and the element being read |
| Having `METHOD` means it propagates even into an explicit accessor | Distinguish implicit accessors from manually declared ones |
| Every manually written constructor loses parameter metadata | Distinguish compact constructors from full form |
| `PARAMETER` and `CONSTRUCTOR` point to the same location | Read `Parameter` separately from `Constructor` |
| `TYPE_USE` is read using declaration annotations | Traverse the appropriate `AnnotatedType` |
| If the outermost type level has no annotation, inner generic types have none either | Traverse the type structure to the exact position |
| Once metadata is propagated, data is validated automatically | Identify the processor or code enforcing the rule |

Try changing one small factor of the experiment at a time and predict the output before running:

1. Remove `RECORD_COMPONENT` from `Mark`'s targets while keeping the others: which locations can still read it?
2. Remove `@Mark` on the explicit accessor of `Restated`: does the header annotation automatically fill back in?
3. Change `OwnConstructor`'s full constructor to compact form: how does parameter metadata change?
4. Move `@TypeMark` from `List<@TypeMark String>` to `@TypeMark List<String>`: does the position in the type tree to read change?
5. Replace `RUNTIME` with `CLASS`: why does the Reflection output change even though the annotation syntax remains in source code?

Three questions to keep clear are: **where is the annotation allowed to apply, is that member implicitly provided or manually declared, and is Reflection reading the declaration or reading the type use**.
