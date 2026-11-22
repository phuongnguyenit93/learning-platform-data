# Designing a mapping tool supporting records and ordinary classes

## 1. Same object data, different creation paths

A mapping tool typically takes property-named data and creates a Java object. Example:

~~~text
{name: " Linh ", age: 20}
    -> student object
~~~

If the target type is a JavaBean class with a no-argument constructor and setters, the tool can instantiate the object first and then assign each property.

If the target type is a record, the appropriate approach is preparing all arguments and invoking the **canonical constructor**. Record components do not have setters to use in the conventional JavaBean model.

Therefore, do not design a single algorithm in the form:

~~~text
Create empty object
    -> find every field
    -> open access
    -> write values into each field
~~~

That algorithm both bypasses the interface of ordinary classes and is incompatible with record component fields. Record component fields are `private final`; Reflection does not allow using accessibility overrides to arbitrarily rewrite final fields of record classes. Field-writing rules are described at [Field.set](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html#set(java.lang.Object,java.lang.Object)).

A better design is **sharing a common property model and validation rules**, while having **an object-creation strategy suited to each target kind**.

## 2. Define the supported contract before writing Reflection

"Ordinary classes" cover many designs: JavaBeans with setters, immutable classes with constructors only, classes using builders, classes with static factories, or classes with public fields. No single guessing algorithm fits every kind.

This lesson builds a bidirectional mapper:

~~~text
Map<String, ?> -> object
object         -> Map<String, Object>
~~~

Concrete contract of the example:

| Target | Discovery approach | Creation approach | Reading approach |
| --- | --- | --- | --- |
| Public record | `getRecordComponents()` | Public canonical constructor | Accessor of each component |
| Public JavaBean | `Introspector` and `PropertyDescriptor` | Public no-argument constructor, then call setters | Getter of each property |

For the JavaBean branch, the example requires all discovered properties to be both readable and writable. It rejects read-only properties, write-only properties, indexed-only properties, or static accessors.

Input values are already Java objects of appropriate types. The example does not automatically convert the string `"20"` to a number, does not recursively map a nested map into a sub-object, and does not verify every element of a generic collection.

That is an intentional contract so the architecture stays clear. When extending it, add corresponding strategies or converters instead of making the Reflection branch silently guess in multiple ways.

## 3. Separating the inspection phase and the data-processing phase

A mapping pass should have clear responsibilities:

1. **Inspect target type:** identify record or JavaBean model.
2. **Build a plan:** store name, type, and access methods for each property; identify the constructor.
3. **Validate input data:** unknown keys, missing keys, `null`, value types.
4. **Instantiate object:** invoke the constructor according to the chosen strategy.
5. **Assign properties if needed:** only in the JavaBean branch.
6. **Report contextual errors:** preserve property name or constructor position along with the cause.

Metadata does not change per data map. Therefore you can build one mapper object for a `Class<T>`, plan once, and reuse it.

In the example, the common property model is:

~~~java
record Property(String name, Class<?> type, Method reader, Method writer) {
}
~~~

This is an excerpt from the program below; `import java.lang.reflect.Method` is needed when used standalone in a file.

- A record has `reader` as the accessor and no `writer`.
- A JavaBean has `reader` as the getter and `writer` as the setter.
- Name and type are shared for data validation.
- The object-creation approach is kept in the mapper's plan, not inferred from whether `writer` exists on each individual property.

## 4. Record branch: prepare arguments then call the constructor

Record component metadata provides name, type, and declaration order. [Class.getRecordComponents](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getRecordComponents()) guarantees component order according to the record header.

For:

~~~java
public record StudentRecord(String name, int age) {
}
~~~

the canonical constructor signature uses the order:

~~~text
(String, int)
~~~

Even if the input map iterates `age` before `name`, the tool must still build the argument array in **record component order**, not map order.

The flow is:

~~~text
component name -> get value by key "name" -> argument 0
component age  -> get value by key "age"  -> argument 1
    -> invoke canonical constructor
~~~

Things to avoid:

- Do not pick the first constructor in `getDeclaredConstructors()`.
- Do not require a record to have a no-argument constructor.
- Do not infer property names from `getX()`; record accessors are normally named `x()`.
- Do not instantiate a record and then try to write component fields directly.
- Do not bypass the canonical or compact constructor, because this may be where data validation and normalization live.

The constructor in the example normalizes the name with `strip()` and rejects negative ages. The mapper must execute that logic when creating the record.

## 5. JavaBean branch: use property descriptors instead of guessing field names

`Introspector` inspects JavaBean properties. Each `PropertyDescriptor` can provide the type, read method, and write method.

Example:

~~~text
getName() / setName(String) -> property name
getAge()  / setAge(int)     -> property age
~~~

The tool does not need to write to private fields `name` or `age`. It uses the getter/setter interface, so validation logic inside setters is still executed.

Call example:

~~~java
Introspector.getBeanInfo(type, Object.class)
~~~

to stop before `Object`, avoiding treating the property inferred from `getClass()` as model data.

The [Introspector](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/beans/Introspector.html) and [PropertyDescriptor](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/beans/PropertyDescriptor.html) documentation describes these entry points.

JavaBean properties in the example are sorted by name for a stable order. That order serves the plan and presentation output; it is not the class's field declaration order.

Because it uses `java.beans`, the program requires the `java.desktop` module, included in the full JDK. If moved into a project using `module-info.java`, the program's module must declare `requires java.desktop;`.

## 6. Complete program

Save into `DualModelMapperDemo.java`:

~~~java
import java.beans.IntrospectionException;
import java.beans.Introspector;
import java.beans.PropertyDescriptor;
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.lang.reflect.RecordComponent;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

public class DualModelMapperDemo {
    public record StudentRecord(String name, int age) {
        public StudentRecord {
            name = Objects.requireNonNull(name, "name").strip();
            if (age < 0) {
                throw new IllegalArgumentException("age must be nonnegative");
            }
        }
    }

    public static class StudentBean {
        private String name;
        private int age;

        public StudentBean() {
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = Objects.requireNonNull(name, "name").strip();
        }

        public int getAge() {
            return age;
        }

        public void setAge(int age) {
            if (age < 0) {
                throw new IllegalArgumentException("age must be nonnegative");
            }
            this.age = age;
        }
    }

    record Property(String name, Class<?> type, Method reader, Method writer) {
    }

    public static final class MappingException extends RuntimeException {
        MappingException(String path, Throwable cause) {
            super(path + ": " + cause.getClass().getSimpleName(), cause);
        }
    }

    static MappingException failure(String path, Exception error) {
        Throwable cause = error instanceof InvocationTargetException wrapped
                ? wrapped.getCause() : error;
        return new MappingException(path, cause);
    }

    public static final class Mapper<T> {
        private static final Map<Class<?>, Class<?>> BOXES = Map.of(
                boolean.class, Boolean.class, byte.class, Byte.class,
                short.class, Short.class, char.class, Character.class,
                int.class, Integer.class, long.class, Long.class,
                float.class, Float.class, double.class, Double.class);

        private final Class<T> type;
        private final Constructor<T> constructor;
        private final List<Property> properties;
        private final Set<String> names;
        private final boolean record;

        public Mapper(Class<T> type) {
            this.type = Objects.requireNonNull(type, "type");
            if (!Modifier.isPublic(type.getModifiers())
                    || Modifier.isAbstract(type.getModifiers())
                    || type.isEnum() || type.isInterface()
                    || type.isArray() || type.isPrimitive()) {
                throw new IllegalArgumentException(
                        "Unsupported target: " + type.getTypeName());
            }

            record = type.isRecord();
            List<Property> discovered = new ArrayList<>();
            try {
                if (record) {
                    RecordComponent[] components = type.getRecordComponents();
                    Class<?>[] parameterTypes = new Class<?>[components.length];
                    for (int i = 0; i < components.length; i++) {
                        RecordComponent component = components[i];
                        parameterTypes[i] = component.getType();
                        discovered.add(new Property(
                                component.getName(), component.getType(),
                                component.getAccessor(), null));
                    }
                    constructor = type.getConstructor(parameterTypes);
                } else {
                    constructor = type.getConstructor();
                    for (PropertyDescriptor descriptor :
                            Introspector.getBeanInfo(type, Object.class)
                                    .getPropertyDescriptors()) {
                        Method reader = descriptor.getReadMethod();
                        Method writer = descriptor.getWriteMethod();
                        if (descriptor.getPropertyType() == null
                                || reader == null || writer == null
                                || Modifier.isStatic(reader.getModifiers())
                                || Modifier.isStatic(writer.getModifiers())) {
                            throw new IllegalArgumentException(
                                    "Unsupported bean property: "
                                    + descriptor.getName());
                        }
                        discovered.add(new Property(
                                descriptor.getName(),
                                descriptor.getPropertyType(), reader, writer));
                    }
                    discovered.sort(Comparator.comparing(Property::name));
                }
            } catch (ReflectiveOperationException | IntrospectionException ex) {
                throw failure(type.getSimpleName() + ".metadata", ex);
            }
            properties = List.copyOf(discovered);
            names = properties.stream()
                    .map(Property::name)
                    .collect(Collectors.toUnmodifiableSet());
        }

        private Object check(Property property, Object value) {
            Class<?> required = property.type();
            if (value == null) {
                if (required.isPrimitive()) {
                    throw new IllegalArgumentException(
                            "Null primitive: " + property.name());
                }
                return null;
            }
            Class<?> boxed = BOXES.getOrDefault(required, required);
            if (!boxed.isInstance(value)) {
                throw new IllegalArgumentException(
                        "Wrong type for " + property.name()
                        + ": expected " + required.getTypeName());
            }
            return value;
        }

        public T fromMap(Map<String, ?> input) {
            Objects.requireNonNull(input, "input");
            Map<String, ?> source = new LinkedHashMap<>(input);
            for (String name : source.keySet()) {
                if (name == null || !names.contains(name)) {
                    throw new IllegalArgumentException(
                            "Unknown property: " + name);
                }
            }

            Object[] values = new Object[properties.size()];
            for (int i = 0; i < properties.size(); i++) {
                Property property = properties.get(i);
                if (!source.containsKey(property.name())) {
                    throw new IllegalArgumentException(
                            "Missing property: " + property.name());
                }
                values[i] = check(property, source.get(property.name()));
            }

            T result;
            try {
                result = record ? constructor.newInstance(values)
                        : constructor.newInstance();
            } catch (ReflectiveOperationException ex) {
                throw failure(type.getSimpleName() + ".<init>", ex);
            }

            if (!record) {
                for (int i = 0; i < properties.size(); i++) {
                    Property property = properties.get(i);
                    try {
                        property.writer().invoke(result, values[i]);
                    } catch (ReflectiveOperationException ex) {
                        throw failure(type.getSimpleName() + "."
                                + property.name(), ex);
                    }
                }
            }
            return result;
        }

        public Map<String, Object> toMap(T value) {
            Objects.requireNonNull(value, "value");
            type.cast(value);
            Map<String, Object> result = new LinkedHashMap<>();
            for (Property property : properties) {
                try {
                    result.put(property.name(),
                            property.reader().invoke(value));
                } catch (ReflectiveOperationException ex) {
                    throw failure(type.getSimpleName() + "."
                            + property.name(), ex);
                }
            }
            return result;
        }
    }

    static void showFailure(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected a failure: " + label);
        } catch (IllegalArgumentException | MappingException expected) {
            System.out.println(label + ": " + expected.getMessage());
            if (expected.getCause() != null) {
                System.out.println(label + " cause: "
                        + expected.getCause().getClass().getSimpleName());
            }
        }
    }

    public static void main(String[] args) {
        Mapper<StudentRecord> records = new Mapper<>(StudentRecord.class);
        Mapper<StudentBean> beans = new Mapper<>(StudentBean.class);

        Map<String, Object> input = new LinkedHashMap<>();
        input.put("age", 20);
        input.put("name", " Linh ");

        StudentRecord student = records.fromMap(input);
        StudentBean bean = beans.fromMap(input);
        System.out.println("record: " + student);
        System.out.println("record map: " + records.toMap(student));
        System.out.println("bean map: " + beans.toMap(bean));
        System.out.println("maps equal: "
                + records.toMap(student).equals(beans.toMap(bean)));

        showFailure("missing", () ->
                records.fromMap(Map.of("name", "Linh")));
        showFailure("unknown", () ->
                records.fromMap(Map.of(
                        "name", "Linh", "age", 20, "extra", true)));
        showFailure("wrong type", () ->
                records.fromMap(Map.of("name", "Linh", "age", "20")));

        Map<String, Object> nullAge = new LinkedHashMap<>(input);
        nullAge.put("age", null);
        showFailure("null primitive", () -> records.fromMap(nullAge));

        showFailure("record validation", () ->
                records.fromMap(Map.of("name", "Linh", "age", -1)));
        showFailure("bean validation", () ->
                beans.fromMap(Map.of("name", "Linh", "age", -1)));
    }
}
~~~

Compile and run on the standard classpath with JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 DualModelMapperDemo.java
java DualModelMapperDemo
~~~

Exact output:

~~~text
record: StudentRecord[name=Linh, age=20]
record map: {name=Linh, age=20}
bean map: {age=20, name=Linh}
maps equal: true
missing: Missing property: age
unknown: Unknown property: extra
wrong type: Wrong type for age: expected int
null primitive: Null primitive: age
record validation: StudentRecord.<init>: IllegalArgumentException
record validation cause: IllegalArgumentException
bean validation: StudentBean.age: IllegalArgumentException
bean validation cause: IllegalArgumentException
~~~

In the example, all model types and methods called by the mapper are public and accessible in the runtime environment. The mapper does not force deep access with `setAccessible(true)`.

## 7. Reading the design through the execution results

### 7.1. Both models share the same input data

The map is supplied in the order `age`, then `name`. The record is still created properly because constructor arguments are prepared in component metadata order, not map order.

Both the record's compact constructor and the JavaBean's `setName` setter strip leading and trailing whitespace. The resulting name is `Linh`, without the two original spaces.

This proves the mapper goes through the initialization or assignment behavior defined by the model. It does not bypass that logic by writing directly into fields.

### 7.2. Output maps can differ in order and still be equal

Output:

~~~text
record map: {name=Linh, age=20}
bean map: {age=20, name=Linh}
maps equal: true
~~~

The record branch preserves the component order `name, age`. The JavaBean branch sorts properties by name `age, name`.

The two maps have the same key/value pairs, so `Map.equals` returns `true`. Do not equate presentation order with equivalence of map data.

If an output protocol requires a common order for both models, design a separate output rule. Do not change the canonical constructor argument order for presentation purposes.

### 7.3. Missing keys and null must be distinguished

The mapper uses:

~~~java
source.containsKey(property.name())
~~~

before reading the value.

Therefore, the following two cases are not conflated:

~~~text
No key age
Key age is present, but value is null
~~~

The example chooses a strict policy:

- Every property in the plan must have a key.
- `null` is rejected if the target type is primitive.
- `null` can pass the mapper's type check if the target type is a reference type.
- The constructor or setter can still reject `null` according to the model's rules.

Do not automatically use `0` for a missing primitive key, nor automatically ignore a missing key on a JavaBean just because a new object has a default value.

### 7.4. Data types are checked before creating the object

`BOXES` maps primitive types to their corresponding wrappers, such as `int.class -> Integer.class`. An `Integer` value is accepted for an `int` property, while the string `"20"` is rejected.

The policy in the example requires the exact matching wrapper for a primitive; it does not let a `Byte` pass into `int` even though some Reflection operations can support primitive widening conversions.

For reference types, the check uses `Class.isInstance(...)`. A value that is a subclass or compatible interface implementation can be accepted.

This is a check against erased type tokens. It does not prove that every element of a `List<String>` is actually a `String`. To handle generics, you must retain and analyze `Type` as well, then define a checking or conversion policy at each level.

## 8. Preserving error causes and where they occurred

Input errors such as missing keys, unknown keys, and wrong types are caught before the constructor call step.

For errors originating inside the model's behavior, Reflection typically wraps the exception in `InvocationTargetException`. The `failure(...)` method unwraps the root cause and keeps it as the `cause` of `MappingException`.

Thus, the two negative-age validation errors are localized differently:

~~~text
StudentRecord.<init>: IllegalArgumentException
StudentBean.age: IllegalArgumentException
~~~

In the record, the error comes from the constructor. In the JavaBean, the error comes from the setter of property `age`.

This information is more useful than merely reporting "mapping failed." When extending to nested data, the error path should include additional context, such as `student.address.city` or `students[2].age`.

You should also separate categories:

| Error category | Example |
| --- | --- |
| Target model outside contract | Enum, abstract class, JavaBean with a read-only property |
| Unable to build plan | Missing matching constructor or introspection error |
| Unsuitable input data | Missing key, unknown key, wrong type, `null` for primitive |
| Model behavior rejects data | Compact constructor or setter throws an exception |
| Unsatisfied access condition | Constructor or method cannot be invoked from the current environment |

Do not swallow the root cause and return a seemingly valid default object. That makes it hard for tool users to tell whether data was skipped or an object was only partially initialized.

## 9. Pre-checking does not mean the operation is transactional

The example validates key names and types of all data before creating the object. As a result, a mistyped string on the last property does not cause the mapper to call setters for earlier properties first.

However, domain validation still happens inside constructors or setters:

- A constructor can perform side effects before throwing an exception.
- One setter can succeed while a subsequent setter fails.
- Getters used when exporting a map can also contain logic or throw exceptions.

The mapper does not roll back those side effects. With a JavaBean, when a setter fails, the method does not return the object being constructed, yet this does not create a transactional guarantee for all code executed by the model class.

If a model must guarantee valid state from the start, creating via a constructor or factory with complete data is usually clearer than assigning multiple setters sequentially. That applies to ordinary immutable classes too, not just records.

Do not alter a model's data rules for the mapper's convenience. Choose a creation approach that matches the model's contract.

## 10. Extension points should be separate policies

### 10.1. Type conversion and nested data

You can add a converter taking the source value, target type, and current path.

Examples of tasks requiring dedicated decisions:

- String to number: whitespace, sign, value range, and overflow.
- String to enum: declared name or business code, policy when unmatched.
- Map to sub-object: recurse according to the target type.
- List of elements: analyze `ParameterizedType`, convert each element, and keep the index in errors.
- `Optional`, date-time, or custom value types: specific source representation.

Do not merely add a few casting branches inside the constructor call site. When data is more complex, conversion must finish and be validated before passing arguments to the creation strategy.

### 10.2. Ordinary immutable classes and factories

An ordinary class with a multi-parameter constructor should not be treated as an "unrecognized record." It needs a separate creation strategy with rules for identifying the constructor and mapping parameter names.

Explicit configuration, annotations, or a registered factory can be used. For ordinary constructors, do not assume Reflection parameter names are always data domain names unless the program has appropriate metadata or configuration.

Builders and static factories should also be separate strategies. Do not try a series of constructors by array position and pick the first call that does not throw an error.

### 10.3. Annotations and mapped names

A real-world tool can support input names different from Java property names or data validation rules via annotations.

In that case, clearly specify where annotations are read:

- Record component.
- Backing field.
- Accessor.
- Canonical constructor parameter.
- Type use position.

These are distinct metadata locations. Do not merge every annotation found and assume they always carry the same meaning or value. Precedence and conflict-handling policies belong in the mapper's contract.

### 10.4. Nested objects and cycles

When mapping recursively, data can contain shared references or cycles. Decide whether to preserve object identity or only copy values.

Records require all arguments before calling the canonical constructor, so you cannot assume every cycle can be handled by creating an empty object and patching fields afterward. If a cyclic structure is unsupported, the tool should detect it and report clearly along the data path.

## 11. Metadata planning, reuse, and performance limits

`Mapper<T>` in the program inspects the type once when created. Each `fromMap` or `toMap` call reuses the stored property list and constructor.

That is a sound optimization: there is no need to re-introspect the same type for every data row.

If adding a shared cache, keys must reflect the exact `Class<?>` object, not only the class name. Two classes with the same name from different class loaders can be different runtime types. Cache lifetime also needs to match class loader lifetime if the application loads or unloads plugins.

Do not conclude that a Reflection mapper is fast or slow from a single sample program run. Cost can lie in metadata inspection, data conversion, domain validation, or the accessor methods themselves. Measure on real workloads before replacing calls with another mechanism.

The output map in the example is a top-level copy of the key/value structure. Inner referenced objects can still be the exact same objects returned by getters/accessors. The tool does not automatically deep-copy or take an atomic snapshot of the entire data graph.

## 12. Self-check

1. Why not use the same "create empty then write fields" algorithm for JavaBeans and records?
2. Why does the input map in the example supply `age` before `name` while the record is still created properly?
3. Should the canonical constructor be chosen as the first constructor in the Reflection array?
4. Why use `containsKey` instead of checking only `get(...) == null`?
5. Does the program automatically convert the string `"20"` into `int`?
6. When age is negative, at which locations are the errors for the record and the JavaBean reported?
7. Why do the output maps of the record and JavaBean have different orders yet still equal each other?
8. Does checking all data types before creation guarantee rolling back side effects of setters?
9. To support an immutable class with a three-parameter constructor, should it be forced through the JavaBean branch or given a suitable creation strategy?
10. Does `List.class.isInstance(value)` returning `true` prove every element is a `String`?

Answers:

1. A record must be created via an appropriate constructor and has final component fields; the JavaBean in the contract is assigned via setters.
2. Values are fetched by name and arranged into an array in record component order, not map order.
3. No. You must look up the exact signature from the ordered list of component types.
4. To distinguish a missing key from a present key with a `null` value.
5. No. The example requires matching types and does not perform string-to-number conversion.
6. `StudentRecord.<init>` and `StudentBean.age`; the business cause is preserved as `cause`.
7. The record uses component order, the JavaBean uses name order; `Map.equals` compares key/value pairs.
8. No. It is not a transaction rolling back code already executed by the model.
9. Add a creation strategy with clear constructor or factory mapping.
10. No. The check only confirms the object is a list by erased type; checking generic elements is a separate task.
