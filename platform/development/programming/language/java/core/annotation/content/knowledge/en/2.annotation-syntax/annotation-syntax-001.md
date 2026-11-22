# Annotation Names, Imports, and Fully Qualified Type Names in Java

When using an annotation, the part following the **@** sign is the name of an **annotation type**. Java must find that exact type at compile time, just as when source code references a class or interface. You can write the short name when the type is already in scope, or write the fully qualified name including the package to identify the exact type to use.

This lesson focuses on naming, package declarations, imports, and referencing annotation types. Reading metadata via reflection is used only to verify that the different forms actually point to the same type.

## 1. An Annotation Name Is a Java Type Name

A custom annotation is declared using **@interface**:

~~~java
package com.example.annotations;

public @interface Role {
    String value();
}
~~~

In this example:

- **Role** is the *simple name* of the annotation type; Java is case-sensitive.
- **com.example.annotations** is the package declaring the type.
- **com.example.annotations.Role** is the *fully qualified name* of the type.
- **Role.java** is the required source file name corresponding to this public type declaration.
- **value()** is an *annotation element*. It is not the name of the annotation; this element accepts a String value when used.

Once declared, you can apply the annotation to a permitted location:

~~~java
@Role("admin")
class AdminService {}
~~~

The **@** sign is the syntax for using an annotation; **Role** is still a regular Java type with respect to name resolution. You do not create an annotation with the **new Role()** expression. The example above is valid only when the source code can find the Role type, the declaration of Role allows applying it to a class, and the value element is given a valid value.

**@Role("admin")** is shorthand for **@Role(value = "admin")** because the element has the special name **value**. These two forms do not change how Java locates the Role type.

## 2. Short Names and Fully Qualified Names

Suppose the Role type is in the package **com.example.annotations**, while the class using it is in **com.example.app**.

| Reference form | Syntax | When to use |
| --- | --- | --- |
| Short name (*simple name*) | **@Role("admin")** | When Role is already visible in the current scope, such as through an import |
| *Fully qualified name* | **@com.example.annotations.Role("admin")** | When you want to specify the exact package without importing the Role type |

Both forms above can reference **the same annotation type**; they do not create two different annotations. For example:

~~~java
package com.example.app;

import com.example.annotations.Role;

@Role("admin")
class FirstService {}

@com.example.annotations.Role("guest")
class SecondService {}
~~~

Here, the import statement allows using the short name Role. Using the fully qualified name on SecondService is still valid even with the import present; it simply spells out both the package and the type name.

**A fully qualified name does not contain an @ sign inside it.** The @ sign is written once, directly before the name: **@com.example.annotations.Role**, not **com.example.annotations.@Role**.

## 3. How to Import Annotations

An annotation type is imported with a **standard import**, because it is also a type:

~~~java
package com.example.app;

import com.example.annotations.Role;

@Role("admin")
class AdminService {}
~~~

The order of the main sections in a Java file is: the **package** declaration (if any), the **import** statements, and then the class/interface/annotation/enum declaration. Do not write **import @Role;**; the @ symbol appears only when applying an annotation or in the **@interface** declaration keyword.

Common cases include:

- **Same package:** If the using class and the annotation type are in the same package, you can use the short name directly without a separate import.
- **Different packages:** Use **import com.example.annotations.Role;** or write **@com.example.annotations.Role** at the usage site.
- **Wildcard import:** **import com.example.annotations.*;** also allows finding matching types in that package, but it tends to obscure actual dependencies and does not avoid all name conflicts. In learning examples, direct imports are easier to read.
- **java.lang:** Annotation types in the **java.lang** package are visible through Java's implicit import mechanism, such as **@Override**, **@Deprecated**, and **@SuppressWarnings**.
- **Subpackages:** Importing a parent package does not automatically import its subpackages. For example, **java.lang.annotation** is not implicitly imported just because **java.lang** is implicitly imported.

### Built-in Java Annotations

~~~java
class Parent {
    public String label() {
        return "parent";
    }
}

class Child extends Parent {
    @Override
    public String label() {
        return "child";
    }

    @Deprecated
    public void oldMethod() {
    }
}
~~~

**@Override** and **@Deprecated** use their short names without an import statement because they belong to **java.lang**. In contrast, when using **@Retention** and **@Target**, you normally need to import them from **java.lang.annotation**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Role {
    String value();
}
~~~

The names **Retention** and **Target** are annotation types; **RetentionPolicy** and **ElementType** are enum types; **RUNTIME** and **TYPE** are enum constants referenced through their enum names. These are distinct elements even though they often appear in the same declaration.

If you do not want to import those types, you can write their fully qualified names:

~~~java
@java.lang.annotation.Retention(
        java.lang.annotation.RetentionPolicy.RUNTIME)
@java.lang.annotation.Target(
        java.lang.annotation.ElementType.TYPE)
public @interface Role {
    String value();
}
~~~

This is an example of **equivalent ways to write the same Java types**, not two different retention/target policies. If you use a static import, you can import the enum constant individually, such as **import static java.lang.annotation.RetentionPolicy.RUNTIME;**, and then write **@Retention(RUNTIME)**. That static import is for the RUNTIME constant; the Retention type itself still needs to be resolved through an appropriate name or import.

## 4. Complete Java 17+ Example: Imports and Fully Qualified Names Working Together

Create the file structure:

~~~text
src/
└── com/
    └── example/
        ├── annotations/
        │   └── Role.java
        └── app/
            └── Main.java
~~~

**File src/com/example/annotations/Role.java**

~~~java
package com.example.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Role {
    String value();
}
~~~

- **@Retention(RetentionPolicy.RUNTIME)** retains the annotation at runtime, allowing the program to read it via reflection.
- **@Target(ElementType.TYPE)** allows the annotation to be used on type declarations such as a class.
- The public Role type is placed in the matching Role.java file and the declared package.

**File src/com/example/app/Main.java**

~~~java
package com.example.app;

import com.example.annotations.Role;

@Role("admin")
class ImportedService {
}

@com.example.annotations.Role("guest")
class QualifiedService {
}

public class Main {
    public static void main(String[] args) {
        printRole(ImportedService.class);
        printRole(QualifiedService.class);
    }

    private static void printRole(Class<?> type) {
        Role annotation = type.getAnnotation(Role.class);
        System.out.println(type.getSimpleName() + ": " + annotation.value());
    }
}
~~~

Compile both files from the directory containing **src**:

~~~bash
javac -encoding UTF-8 -d out src/com/example/annotations/Role.java src/com/example/app/Main.java
java -cp out com.example.app.Main
~~~

Expected output on stdout:

~~~text
ImportedService: admin
QualifiedService: guest
~~~

How it works:

1. At compile time, the compiler resolves **@Role** from the import statement and **@com.example.annotations.Role** from the fully qualified name. Both point to the **com.example.annotations.Role** type.
2. The **javac -d out** command writes the class files following the package directory structure; **java -cp out com.example.app.Main** uses the fully qualified name of the class containing the main method to run it.
3. **Role.class** is the Class object representing the Role annotation type. **getAnnotation(Role.class)** asks reflection to look up an annotation of this type on each class.
4. The **annotation.value()** method reads the declared value. Being readable at runtime is because Role itself has **RUNTIME** retention; whether the short name or fully qualified name was used does not determine retention.

Because both classes have Role applied, the annotation variable in the example is non-null. For a class without Role, **getAnnotation(Role.class)** can return null, and real-world programs must check before calling **value()**.

The example also shows that applying a custom annotation does not automatically produce any business behavior. A compiler, annotation processor, framework, or application code must interpret that metadata. In the program above, the reflection code is what consumes the metadata.

## 5. Name Resolution and Conflicts

Writing a short name is safe only when it identifies the right type in the compilation context:

- If the source code does not import Role, does not have Role in the same scope, and does not use the fully qualified name either, the **@Role** reference cannot resolve the type; compilation fails.
- If libraries contain annotation types with the same short name, such as **com.example.auth.Role** and **com.example.ui.Role**, you can use the fully qualified name inline to specify which type to apply. Do not declare two **single-type imports** with the same short name in the same compilation unit and expect Java to choose automatically.
- If you already know the exact type needed, the form **@com.example.auth.Role** has meaning independent of another short-name import. Java still needs to find that type on the appropriate source path, module path, or classpath.
- Package and type names are case-sensitive. **@Role** differs from **@role**, and **com.example.annotations.Role** differs from **com.example.annotation.Role**.
- Writing the fully qualified name does not solve a missing dependency or an incorrect package declaration. The compiler still must have access to the annotation type.

Here, **@Role** is the usage syntax, whereas **Role.class** and **Role annotation** are ways to reference the same type in an expression or variable declaration. Do not write **@Role.class** to apply an annotation.

## 6. Common Errors and Fixes

| Error | Cause | Fix |
| --- | --- | --- |
| Writing **@Role** in another package without importing it | The name Role is not resolved | Add **import com.example.annotations.Role;** or use **@com.example.annotations.Role** |
| Writing **import @Role;** | Imports accept only type or package names according to Java syntax | Write **import com.example.annotations.Role;** |
| Writing **@java.lang.annotation.* ** | Wildcards are valid only in import declarations, not as a type name at the usage site | Use a specific type name, for example **@java.lang.annotation.Retention(...)** |
| Assuming **import java.lang.*;** includes Retention | Imports do not cascade into subpackages | Import from **java.lang.annotation** or use the fully qualified name |
| Placing **public @interface Role** in a differently named file | The file name does not match the top-level public type | Place it in **Role.java** |
| Writing **@Role** when the **value()** element is required | No value was supplied for an annotation element without a default | Use **@Role("admin")** or **@Role(value = "admin")** |
| Applying Role to a location violating **@Target** | The annotation is not permitted on that target location | Check the **@Target** declaration and apply it to an allowed location |
| Failing to read the annotation via reflection | Retention is not RUNTIME or the wrong element is being read | Check **@Retention(RUNTIME)**, the right type, and the right reflected object |

Note on the table: **@Target** and **@Retention** are metadata about an annotation's applicability rules and retention lifetime; imports and fully qualified names only help **reference the right type**. These two aspects must be checked separately.

## 7. Knowledge Self-Check

**Scenario A.** There is a declaration **public @interface Trace {}** in the **org.example.meta** package. A class in the **org.example.service** package wants to use Trace. The two valid ways are:

~~~java
import org.example.meta.Trace;

@Trace
class OrderService {}
~~~

Or without an import, using the fully qualified name:

~~~java
@org.example.meta.Trace
class OrderService {}
~~~

**Scenario B.** Why does **@Override** normally not need an import, while **@Target** does? Because Override belongs to the **java.lang** package, which is implicitly imported; Target belongs to **java.lang.annotation**, which is a separate package.

**Scenario C.** Does changing **@Role("admin")** to **@com.example.annotations.Role("admin")** change the data read by reflection? No, provided both names resolve to the same Role type and all other declarations remain unchanged.

When reading any annotation, determine in order: **what is the type name after @ → which package does the type belong to → is the type visible to the source code via the same package/import/fully qualified name → does @Target allow the usage location → is the metadata retained until the stage where it is needed**. This check sequence helps separate naming/import errors from annotation application or processing errors.
