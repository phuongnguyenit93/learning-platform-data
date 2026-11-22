# Access flags in Java class files

Access flags are bits in the class file structure used to describe properties of a class, field, or method. The JVM and tools such as javac and javap use these bits to understand access permissions, static/final modifiers, interface characteristics, synchronized methods, bridge methods, and several compiler-generated properties.

In a class file, access flags are stored as a 16-bit (u2) bitmask value. Multiple flags can be combined using bitwise OR. The meaning of a bit depends on where it appears: `access_flags` of a class, `field_info`, or `method_info`. Therefore, you cannot interpret a hex value while ignoring the structure that contains it.

For example, the bit 0x0020 means ACC_SUPER in class access_flags, but ACC_SYNCHRONIZED in method access_flags. Similarly, 0x0040 is ACC_VOLATILE for a field, but ACC_BRIDGE for a method.

## 1. Where are access flags located in a class file?

According to the JVM class file format, there are three important locations that contain an `access_flags` field:

- **ClassFile.access_flags:** describes a class or interface.
- **field_info.access_flags:** describes a field.
- **method_info.access_flags:** describes a method or constructor.

Each location has its own set of valid flags. Some bits have the same numeric value but different meanings across structures.

For example, a class file may contain:

~~~text
ClassFile
  access_flags
  this_class
  super_class
  interfaces
  fields
    field_info
      access_flags
      name_index
      descriptor_index
  methods
    method_info
      access_flags
      name_index
      descriptor_index
~~~

Flags are not text strings stored directly in the file. The class file stores a bitmask; javap reads the bitmask and displays the corresponding names for easier human inspection.

A single value can have multiple bits enabled at the same time. For example:

~~~text
0x0011 = 0x0001 | 0x0010
       = ACC_PUBLIC | ACC_FINAL
~~~

Therefore, when reading javap output, look at both the hex value and the list of flag names.

## 2. Class and interface flags

Common class flags in modern Java class files:

| Flag | Hex value | Meaning |
|---|---:|---|
| ACC_PUBLIC | 0x0001 | Class can be accessed from outside its package according to Java rules |
| ACC_FINAL | 0x0010 | Class cannot be subclassed |
| ACC_SUPER | 0x0020 | Enables special handling when invoking superclass methods with invokespecial |
| ACC_INTERFACE | 0x0200 | This declaration is an interface |
| ACC_ABSTRACT | 0x0400 | Class/interface is abstract |
| ACC_SYNTHETIC | 0x1000 | Declaration is compiler-generated or does not appear directly in source |
| ACC_ANNOTATION | 0x2000 | Interface is an annotation interface |
| ACC_ENUM | 0x4000 | Declaration is an enum |
| ACC_MODULE | 0x8000 | Class file is a module descriptor module-info.class |

### ACC_PUBLIC

Example:

~~~java
public class PublicService {
}
~~~

The class can be accessed from code in another package, provided the relevant module and access rules allow it.

If a top-level class is not declared public, it has package access: code outside the package cannot directly access that class by its normal type name.

### ACC_FINAL

Example:

~~~java
public final class ImmutableToken {
}
~~~

A final class cannot be extended with `extends`. This is a class-level flag, distinct from ACC_FINAL on a field (cannot be reassigned after initialization) or a method (cannot be overridden under Java rules).

A class that is both abstract and final is an invalid combination because an abstract class needs to be subclassable to implement its abstract parts, whereas final forbids subclassing.

### ACC_SUPER

ACC_SUPER relates to how the JVM handles invokespecial when a method invokes an implementation in a superclass. This is a class-file-level flag, not a modifier that developers normally write directly in Java source.

Modern class files produced by javac typically have ACC_SUPER set. For class file versions 51.0 and above, this flag is required by the JVM Specification. When reading javap output, seeing ACC_SUPER is normal and does not mean the class declared a `super` modifier in source.

### ACC_INTERFACE and ACC_ABSTRACT

An interface is marked with ACC_INTERFACE. Interfaces also have ACC_ABSTRACT.

~~~java
public interface Repository {
    Object findById(long id);
}
~~~

An abstract class is marked with ACC_ABSTRACT:

~~~java
public abstract class BaseRepository {
    public abstract Object findById(long id);
}
~~~

Not every abstract class is an interface. ACC_INTERFACE helps the JVM distinguish between the two kinds of declarations.

### ACC_ANNOTATION

An annotation interface is a special kind of interface:

~~~java
public @interface Audited {
}
~~~

In a class file, an annotation interface has ACC_ANNOTATION and ACC_INTERFACE. An annotation type is represented as an interface with the corresponding annotation metadata structures.

### ACC_ENUM

An enum class and its enum constant fields have the ACC_ENUM flag at their respective locations in the class file.

~~~java
public enum Status {
    NEW,
    ACTIVE,
    CLOSED
}
~~~

This flag helps the JVM and tools recognize enum declarations. Enums also have their own rules for constructors, instances, and constant-specific class bodies.

### ACC_MODULE

A module descriptor is compiled into module-info.class and has ACC_MODULE. This is not a flag for marking a regular Java class.

~~~java
module com.example.orders {
    requires java.logging;
    exports com.example.orders.api;
}
~~~

A module descriptor contains a Module attribute structure and related metadata. Do not set ACC_MODULE on a regular class.

## 3. Field flags

Field `access_flags` describe visibility, storage behavior, and certain field characteristics.

| Flag | Hex value | Meaning |
|---|---:|---|
| ACC_PUBLIC | 0x0001 | Public field |
| ACC_PRIVATE | 0x0002 | Private field |
| ACC_PROTECTED | 0x0004 | Protected field |
| ACC_STATIC | 0x0008 | Field belongs to the class rather than each object |
| ACC_FINAL | 0x0010 | Field can only be assigned according to final rules |
| ACC_VOLATILE | 0x0040 | Field accesses have volatile visibility and ordering semantics across threads |
| ACC_TRANSIENT | 0x0080 | Field is excluded from default Java Object Serialization |
| ACC_SYNTHETIC | 0x1000 | Field is compiler-generated or has no direct declaration in source |
| ACC_ENUM | 0x4000 | Field represents an enum constant |

Example:

~~~java
public class FieldFlags {
    public static final int MAX_RETRIES = 3;
    private volatile boolean running;
    protected transient String cachedToken;
}
~~~

Common combinations:

- MAX_RETRIES: ACC_PUBLIC, ACC_STATIC, ACC_FINAL.
- running: ACC_PRIVATE, ACC_VOLATILE.
- cachedToken: ACC_PROTECTED, ACC_TRANSIENT.

ACC_VOLATILE and ACC_FINAL cannot be combined on the same field according to class file rules. A field also cannot simultaneously be public, private, and protected; only one visibility level is used.

### ACC_STATIC

A static field belongs to the class, not to each instance. A static final field can be used for a compile-time constant if it meets the conditions of the Java Language Specification, though not every static final field is inlined as a constant in the bytecode at use sites.

### ACC_FINAL

A final field may only be assigned in locations permitted by Java, such as its direct declaration or an appropriate constructor/initializer. The final flag does not mean the referenced object is immutable; it only prevents reassigning the field variable.

~~~java
private final List<String> names = new ArrayList<>();
~~~

You cannot assign a different List to `names` after initialization, but you can still add elements to the List unless other rules prevent it.

### ACC_VOLATILE

A volatile field is used to establish visibility and ordering rules across threads. When one thread writes to a volatile field and another thread reads the same field, a happens-before relationship applies according to the Java Memory Model.

~~~java
private volatile boolean stopped;
~~~

`volatile` does not make compound operations like `count++` atomic. For concurrent increment/decrement counters, use `synchronized`, `Lock`, or appropriate atomic classes.

### ACC_TRANSIENT

A transient field is skipped during default Java Object Serialization.

~~~java
private transient String sessionToken;
~~~

This flag does not automatically encrypt or erase the value from memory. It only affects the default serialization mechanism; custom serialization such as `writeObject` may apply different rules.

### Interface fields

Fields declared in an interface are `public static final` according to the Java Language Specification, whether or not the source explicitly writes those modifiers.

~~~java
interface Limits {
    int DEFAULT_TIMEOUT = 30;
}
~~~

In the class file, this field has the flags corresponding to public, static, and final.

## 4. Method and constructor flags

Method `access_flags` have their own set of flags:

| Flag | Hex value | Meaning |
|---|---:|---|
| ACC_PUBLIC | 0x0001 | Public method |
| ACC_PRIVATE | 0x0002 | Private method |
| ACC_PROTECTED | 0x0004 | Protected method |
| ACC_STATIC | 0x0008 | Static method |
| ACC_FINAL | 0x0010 | Method cannot be overridden |
| ACC_SYNCHRONIZED | 0x0020 | JVM performs monitor enter/exit according to synchronized semantics |
| ACC_BRIDGE | 0x0040 | Compiler-generated bridge method |
| ACC_VARARGS | 0x0080 | Method uses variable-arity parameter syntax |
| ACC_NATIVE | 0x0100 | Method is implemented in native code |
| ACC_ABSTRACT | 0x0400 | Method has no normal bytecode implementation |
| ACC_STRICT | 0x0800 | Legacy class file strict floating-point flag; ignored since version 61.0 |
| ACC_SYNTHETIC | 0x1000 | Method is compiler-generated or does not appear directly in source |

### Method visibility

Example:

~~~java
public void start() {
}

private void resetState() {
}

protected void validate() {
}
~~~

If a method does not have public, private, or protected, it has package access. In the class file, no corresponding visibility flag is set for the package-private case.

Visibility determines which code can invoke the method under Java and JVM rules. `protected` does not mean `public`: outside the package, access also depends on subclass relationships and how the receiver is referenced.

### ACC_STATIC

A static method belongs to the class:

~~~java
public static int add(int left, int right) {
    return left + right;
}
~~~

A static method has no `this` and is not overridden via dynamic dispatch like an instance method. A static method with the same name in a subclass is method hiding when conditions are met, not normal overriding.

### ACC_FINAL

A final method cannot be overridden by a subclass:

~~~java
public final void closeSafely() {
    // cleanup
}
~~~

ACC_FINAL on a method differs from ACC_FINAL on a class or field; it shares the same flag name, but its scope of application is different.

### ACC_SYNCHRONIZED

A synchronized method has its monitor acquisition and release managed by the JVM:

~~~java
public synchronized void increment() {
    count++;
}
~~~

For an instance method, the monitor is the `this` object. For a static synchronized method, the monitor is the corresponding `Class` object. The JVM ensures the monitor is released whether the method completes normally or exits via an exception.

ACC_SYNCHRONIZED is not a class flag. The bit value 0x0020 on a class is ACC_SUPER, whereas on a method it is ACC_SYNCHRONIZED.

### ACC_ABSTRACT

An abstract method has no normal implementation body in the class file:

~~~java
public abstract class Handler {
    public abstract void handle();
}
~~~

An abstract method cannot simultaneously have certain modifiers such as private, static, final, synchronized, or native because those combinations conflict with the semantics of an abstract method.

### ACC_NATIVE

A native method is implemented outside Java bytecode, typically through JNI or a related native mechanism:

~~~java
public native int readNativeValue();
~~~

ACC_NATIVE tells the JVM that the method has no normal `Code` attribute containing Java bytecode. Linking to the native implementation is a separate runtime concern.

## 5. Bridge methods, varargs, and synthetic flags

This is the group of flags that often causes javap readers to see methods not written directly in source.

### ACC_BRIDGE

Java generics are implemented using type erasure. In some cases, the compiler needs to generate a bridge method to preserve proper polymorphism after generic types are erased.

Example:

~~~java
interface Converter<T> {
    T convert(T value);
}

final class StringConverter implements Converter<String> {
    @Override
    public String convert(String value) {
        return value.trim();
    }
}
~~~

After type erasure, the method in `Converter` has a descriptor corresponding to `Object convert(Object)`. `StringConverter` implements `String convert(String)`, so javac generates an additional bridge method `Object convert(Object)` to preserve the dispatch contract.

When running `javap -v -p StringConverter`, you may see a method similar to:

~~~text
public java.lang.Object convert(java.lang.Object);
  flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
~~~

The bridge method takes an Object, casts it to String, calls `convert(String)`, and returns the result as an Object. This is a compiler-generated detail; you do not write bridge methods yourself in Java source.

### ACC_VARARGS

A method declares a variable-arity parameter using an ellipsis:

~~~java
public void log(String... messages) {
}
~~~

In bytecode, a varargs parameter is represented as an array, but the method carries ACC_VARARGS so tools can recognize the varargs declaration in source.

Example signature:

~~~text
log(java.lang.String...);
  flags: (0x0081) ACC_PUBLIC, ACC_VARARGS
~~~

ACC_VARARGS does not create a separate invocation mechanism in the JVM. At the bytecode level, the parameter is still an array.

### ACC_SYNTHETIC

A synthetic member is an element generated by the compiler or not represented as a normal declaration in source. Examples may include bridge methods, helper fields for inner classes in certain compilers/versions, or synthetic accessor methods.

Not every compiler generates the same set of synthetic members for the same source. Details depend on source structure, compiler version, and optimization strategies.

When writing bytecode analysis tools, do not assume every member was written directly by a developer. Check ACC_SYNTHETIC and ACC_BRIDGE to decide how to display or process them.

## 6. Bitmasks and reading hex values

Access flags are bitmasks. Each flag corresponds to a bit; multiple flags are combined using bitwise OR.

Example of a public final class:

~~~text
ACC_PUBLIC = 0x0001
ACC_FINAL  = 0x0010
ACC_SUPER  = 0x0020

Total      = 0x0031
~~~

A private static final field:

~~~text
ACC_PRIVATE = 0x0002
ACC_STATIC  = 0x0008
ACC_FINAL   = 0x0010

Total       = 0x001A
~~~

A public synchronized varargs method:

~~~text
ACC_PUBLIC       = 0x0001
ACC_SYNCHRONIZED = 0x0020
ACC_VARARGS      = 0x0080

Total            = 0x00A1
~~~

When checking bits in class file parsing code, use bitwise AND:

~~~java
boolean isPublic = (accessFlags & 0x0001) != 0;
boolean isFinal = (accessFlags & 0x0010) != 0;
~~~

Do not compare the entire value with equality if the goal is only to check a single flag. For example, a public final class has the value 0x0031; comparing `accessFlags == 0x0001` will be false even though the class has ACC_PUBLIC.

To clear a bit in a bitmask variable, you can use bitwise AND with the bitwise complement, but only do so when manipulating data that the program is permitted to modify. Class file reader tools usually only need to check and display flags.

## 7. The same bit can have different meanings by structure

This is an important rule when reading the class file format:

| Value | In class access_flags | In field access_flags | In method access_flags |
|---:|---|---|---|
| 0x0001 | ACC_PUBLIC | ACC_PUBLIC | ACC_PUBLIC |
| 0x0002 | Not used for top-level classes | ACC_PRIVATE | ACC_PRIVATE |
| 0x0004 | Not used for top-level classes | ACC_PROTECTED | ACC_PROTECTED |
| 0x0008 | Not used for top-level classes | ACC_STATIC | ACC_STATIC |
| 0x0010 | ACC_FINAL | ACC_FINAL | ACC_FINAL |
| 0x0020 | ACC_SUPER | Not used | ACC_SYNCHRONIZED |
| 0x0040 | Not used | ACC_VOLATILE | ACC_BRIDGE |
| 0x0080 | Not used | ACC_TRANSIENT | ACC_VARARGS |
| 0x0100 | Not used | Not used | ACC_NATIVE |
| 0x0200 | ACC_INTERFACE | Not used | Not used |
| 0x0400 | ACC_ABSTRACT | Not used | ACC_ABSTRACT |
| 0x0800 | Not used | Not used | ACC_STRICT |
| 0x1000 | ACC_SYNTHETIC | ACC_SYNTHETIC | ACC_SYNTHETIC |
| 0x2000 | ACC_ANNOTATION | Not used | Not used |
| 0x4000 | ACC_ENUM | ACC_ENUM | Not used |
| 0x8000 | ACC_MODULE | Not used | Not used |

This table helps avoid a common bug where a parser uses a single shared list of flag names for all member types. A class file tool must know whether it is reading `ClassFile`, `field_info`, or `method_info` before decoding bits.

Some flag combinations are also forbidden by the JVM Specification. For example, a field cannot be both final and volatile; an abstract method cannot also be synchronized; a class cannot be both final and abstract. If a parser encounters an invalid combination, it should report an invalid class file rather than assigning an arbitrary meaning.

## 8. Nested class access flags and the InnerClasses attribute

A nested class can be declared private, protected, or static:

~~~java
public class Outer {
    private static class Hidden {
    }

    protected class Extension {
    }
}
~~~

However, the private/protected/static modifiers of a nested class are recorded in the `InnerClasses` attribute of the relevant class files. They are not all stored in `ClassFile.access_flags` of `Hidden.class` or `Extension.class`.

Therefore, when running `javap -v`, you may see a class flags section and an `InnerClasses` entry with separate flags for the nested class. Do not confuse these two metadata locations.

For top-level classes, Java only allows public or package access. `private`, `protected`, and `static` are not valid modifiers for a top-level class.

## 9. Metadata that is not an access flag

Not every characteristic of a class is represented by `access_flags`.

- **Record:** described by the `Record` attribute; there is no `ACC_RECORD` in the standard class access flags set.
- **Sealed class:** permitted subclasses information is recorded in the `PermittedSubclasses` attribute.
- **Generic signature:** uses the `Signature` attribute.
- **Runtime annotations:** recorded in the corresponding annotation attributes.
- **Source file name:** typically stored in the `SourceFile` attribute.
- **Inner/nested class metadata:** has the `InnerClasses` attribute.
- **Module descriptor:** uses `ACC_MODULE` together with the `Module` attribute and related module structures.

Record example:

~~~java
public record UserId(long value) {
}
~~~

When inspecting a record's class file, you will see flags such as public, final, and super, along with the `Record` attribute. Do not look for a flag named `ACC_RECORD` in the class `access_flags` table.

Sealed class example:

~~~java
public sealed class Shape permits Circle, Rectangle {
}
~~~

The classes permitted to extend it are described by the `PermittedSubclasses` attribute, not a separate access flag.

## 10. Inspecting access flags with javap

The JDK provides `javap` for reading class file structures.

Compile:

~~~bash
javac --release 17 -d out AccessFlagsDemo.java
~~~

View declarations and members, including private ones:

~~~bash
javap -p -classpath out AccessFlagsDemo
~~~

View detailed class file information and access flags:

~~~bash
javap -v -p -classpath out AccessFlagsDemo
~~~

Options:

- **-p** or **-private**: displays all classes and members, including private ones.
- **-v** or **-verbose**: displays the constant pool, flags, attributes, and detailed bytecode information.
- **-c**: displays method bytecode.
- **-classpath**: specifies where to find class files.

For example, the header of the output might look like:

~~~text
public final class AccessFlagsDemo
  flags: (0x0031) ACC_PUBLIC, ACC_FINAL, ACC_SUPER
~~~

A field:

~~~text
private static final int LIMIT;
  flags: (0x001A) ACC_PRIVATE, ACC_STATIC, ACC_FINAL
~~~

A synchronized varargs method:

~~~text
public synchronized java.lang.String join(java.lang.String...);
  flags: (0x00A1) ACC_PUBLIC, ACC_SYNCHRONIZED, ACC_VARARGS
~~~

Method names, descriptors, and offsets in the output depend on the source and compiler. The values above correspond to the example in the hands-on section.

To inspect a bridge method:

~~~bash
javap -v -p -classpath out StringConverter
~~~

Look for the method with ACC_BRIDGE and ACC_SYNTHETIC. You can use `javap -c` to read the bridge method's bytecode and see the cast operation before calling the String-typed method.

## 11. Complete hands-on example with Java 17+

The example below creates a public final class, a private static final field, a synchronized varargs method, and a bridge method generated from a generic interface.

Create `AccessFlagsDemo.java`:

~~~java
interface Mapper<T> {
    T map(T value);
}

final class StringMapper implements Mapper<String> {
    @Override
    public String map(String value) {
        return value.trim();
    }
}

public final class AccessFlagsDemo {
    private static final int LIMIT = 3;

    public synchronized String join(String... values) {
        return String.join(",", values);
    }

    private static int clamp(int value) {
        return Math.min(value, LIMIT);
    }

    public static void main(String[] args) {
        StringMapper mapper = new StringMapper();
        AccessFlagsDemo demo = new AccessFlagsDemo();

        System.out.println(mapper.map("  java  "));
        System.out.println(demo.join("one", "two"));
        System.out.println(clamp(5));
    }
}
~~~

Compile:

~~~bash
javac --release 17 -d out AccessFlagsDemo.java
~~~

Run:

~~~bash
java -cp out AccessFlagsDemo
~~~

Output:

~~~text
java
one,two
3
~~~

View flags of the class and its members:

~~~bash
javap -v -p -classpath out AccessFlagsDemo
~~~

Notable flags in `AccessFlagsDemo`:

- Class: ACC_PUBLIC, ACC_FINAL, ACC_SUPER.
- LIMIT: ACC_PRIVATE, ACC_STATIC, ACC_FINAL.
- join: ACC_PUBLIC, ACC_SYNCHRONIZED, ACC_VARARGS.
- clamp: ACC_PRIVATE, ACC_STATIC.
- main: ACC_PUBLIC, ACC_STATIC.

Inspect class `StringMapper`:

~~~bash
javap -v -p -classpath out StringMapper
~~~

In addition to `map(String)`, the compiler generates a bridge method `map(Object)` with ACC_BRIDGE and ACC_SYNTHETIC. The bridge ensures that calls through `Mapper<String>` still reach the right implementation after type erasure.

This example illustrates that source code does not show every member in the class file. To understand exactly what the compiler generated, inspect the bytecode with `javap`.

## 12. Access flags, reflection, and runtime access permissions

Java Reflection exposes modifiers as integers through methods such as:

~~~java
Class<?> type = AccessFlagsDemo.class;
int classModifiers = type.getModifiers();

int methodModifiers =
        type.getDeclaredMethod("main", String[].class).getModifiers();
~~~

You can decode them using `java.lang.reflect.Modifier`:

~~~java
System.out.println(
        java.lang.reflect.Modifier.toString(classModifiers));
~~~

For fields, methods, and classes, Reflection displays modifiers according to their respective context. Some internal class file flags such as ACC_SUPER, ACC_BRIDGE, or ACC_SYNTHETIC are not represented as normal source modifiers in `Modifier.toString`. To inspect bridge/synthetic metadata, use APIs such as `Method.isBridge()`, `Method.isSynthetic()`, `Field.isSynthetic()`, and `Class.isSynthetic()`.

Example:

~~~java
for (var method : StringMapper.class.getDeclaredMethods()) {
    System.out.println(
            method.getName()
                    + ", bridge=" + method.isBridge()
                    + ", synthetic=" + method.isSynthetic());
}
~~~

The output lists both the `map` method and the compiler-generated bridge method. The order in which methods are listed is not guaranteed.

Access flags are one part of class file metadata, while actual access permissions are governed by Java language access rules, JVM access checks, packages, modules, class loaders, and reflection mechanisms. Do not treat the presence of a public/private bit in a file as the entire security model of an application.

## 13. Common mistakes when reading access flags

**Using the same bit table for classes, fields, and methods**

Bit 0x0020 can be ACC_SUPER or ACC_SYNCHRONIZED depending on the structure. Always decode according to the correct `access_flags` type.

**Confusing ACC_FINAL on a class with a field or method**

A final class cannot be subclassed; a final field cannot be reassigned outside permitted locations; a final method cannot be overridden. Same flag, different applicable rules.

**Assuming package-private is a separate flag**

Package-private is represented by having none of public, private, or protected set. There is no ACC_PACKAGE_PRIVATE.

**Assuming every method in javap was written by a developer**

Bridge and synthetic methods can be generated by the compiler. Check ACC_BRIDGE and ACC_SYNTHETIC when analyzing bytecode.

**Confusing ACC_VARARGS with an array type**

Varargs is represented by an array in the descriptor; ACC_VARARGS marks the variable-arity declaration semantics in source.

**Mistaking record or sealed for an access flag**

Records and sealed classes use separate attributes to store metadata. There is no ACC_RECORD or ACC_SEALED in the standard class `access_flags` table.

**Reading nested class flags in the wrong place**

Modifiers of a nested class are described in the `InnerClasses` attribute. `ClassFile.access_flags` of a nested class does not contain all modifiers of the nested declaration.

**Treating ACC_SUPER as a source modifier**

ACC_SUPER is a flag serving `invokespecial` semantics and commonly appears in modern class files. Java source has no `super` modifier to add to a class declaration.

## 14. Principles when analyzing class files

1. Identify whether you are reading `access_flags` of `ClassFile`, `field_info`, or `method_info`.
2. Read the hex value and decode each bit according to the appropriate table.
3. Check whether flag combinations are valid under the JVM Specification.
4. Use `javap -v -p` to cross-check metadata and members.
5. Distinguish flags written in source from compiler-generated flags.
6. Check `InnerClasses` or other attributes when you need to understand nested classes, records, sealed classes, and modules.
7. Do not treat access flags as the complete security or runtime access-check mechanism.
8. When writing a parser, preserve unknown bits if you want forward compatibility, and do not interpret flags undefined for the current structure.

Access flags are a small but important metadata layer in the class file format. Understanding the bitmask and its per-structure meaning lets you read `javap` output, analyze compiler-generated members, and build bytecode processing tools more accurately.
