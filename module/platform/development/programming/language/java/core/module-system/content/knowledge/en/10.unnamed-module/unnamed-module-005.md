# Reflection and unnamed modules

In the Java Platform Module System (JPMS), classes loaded from the **classpath** belong to the unnamed module of the corresponding class loader. Unnamed modules have special opening and readability rules to maintain compatibility with traditional Java applications. These rules directly affect reflection, especially when an application combines named modules with libraries or frameworks that still run on the classpath.

Two access directions must be distinguished:

- Code in a named module using reflection to inspect a class loaded from the classpath.
- A framework loaded from the classpath using reflection to access a class in a named module.

These two cases have different access directions and different granted permissions.

## 1. What is an unnamed module?

When a class is loaded from the classpath, Java places that class into the unnamed module associated with the class loader that defined it. Each class loader has its own unnamed module; therefore, you should not assume that the entire classpath of all class loaders in the JVM always belongs to a single unnamed module.

An unnamed module has no module name to declare in **requires** and has no **module-info.java** file. It is maintained so that unmodularized applications and libraries can continue to operate.

Important characteristics:

- An unnamed module reads all other modules in the module configuration.
- All packages of an unnamed module are exported.
- All packages of an unnamed module are also open for deep reflection.
- Named modules do not automatically read unnamed modules.
- You cannot write a **requires** directive pointing to an unnamed module because it has no name.

Therefore, the classpath can still coexist with the module path. However, when code in a named module needs to directly reference a type on the classpath, the readability relationship must be handled separately.

## 2. Why are unnamed modules open for reflection?

Java applications prior to JPMS often relied on reflection to work with libraries, frameworks, and dynamically loaded classes. If strict encapsulation boundaries like those of named modules were immediately applied to the classpath, many legacy frameworks could stop working.

Consequently, unnamed modules have their packages exported and open. This allows code from other modules to access public APIs and perform deep reflection on classes in the unnamed module, provided the class is loaded and other access conditions are met.

Example of a class on the classpath:

~~~java
package com.example.legacy;

public class LegacyRecord {
    private String secret = "legacy-value";
}
~~~

Code in a named module can look up the class by name and use reflection:

~~~java
Class<?> type = Class.forName("com.example.legacy.LegacyRecord");
Object record = type.getDeclaredConstructor().newInstance();

var field = type.getDeclaredField("secret");
field.setAccessible(true);

System.out.println(field.get(record));
~~~

In this example, the target class belongs to an unnamed module. Packages of an unnamed module are open, so JPMS does not block deep reflection merely because that package lacks an **opens** directive in a module descriptor.

However, reflection still depends on whether the class can be found by the class loader, whether the constructor can instantiate it, and other Java access rules. Being open does not mean every class or member in an unnamed module automatically becomes public.

## 3. Named modules do not automatically read unnamed modules

In the reverse direction, there is an important rule: a named module does not automatically read an unnamed module. If source code in a named module directly references a class on the classpath, the compiler may report that the package is not read or inaccessible.

Example application module:

~~~java
module com.example.app {
}
~~~

Code wanting to use a class on the classpath:

~~~java
package com.example.app;

import com.example.legacy.LegacyRecord;

public class Main {
    public static void main(String[] args) {
        LegacyRecord record = new LegacyRecord();
        System.out.println(record);
    }
}
~~~

The JAR containing **LegacyRecord** may already be on the classpath, yet the named module still does not automatically have a read edge to the unnamed module. A temporary read edge can be added with **--add-reads**:

~~~bash
javac --module-path mods \
      --class-path libs/legacy.jar \
      --add-reads com.example.app=ALL-UNNAMED \
      --module-source-path src \
      -d out \
      -m com.example.app
~~~

At runtime, the corresponding read edge also needs to be configured:

~~~bash
java --module-path out \
     --class-path libs/legacy.jar \
     --add-reads com.example.app=ALL-UNNAMED \
     --module com.example.app/com.example.app.Main
~~~

**ALL-UNNAMED** is a special target name for launcher options. It represents the unnamed modules in the runtime environment. **ALL-UNNAMED** cannot be used as a module name in a **requires** directive of **module-info.java**.

If possible, move the legacy library to the module path so Java recognizes it as an automatic module, then declare the dependency using a stable module name. **--add-reads** is suitable as an intentional bridge during migration.

## 4. A framework on the classpath reflecting into a named module

A very common situation is when the main application is already modularized, but a framework is still loaded from the classpath. In that case, the framework belongs to an unnamed module and can read named modules. However, if the framework needs to access private fields, constructors, or methods in a named module, the package owning the class must be opened to the framework.

Example application module:

~~~java
module com.example.app {
    exports com.example.app.api;
}
~~~

Suppose an entity resides in the package:

~~~java
package com.example.app.model;

public class Customer {
    private String email;
}
~~~

An ORM framework on the classpath wants to access the **email** field using reflection. The package **com.example.app.model** has not been opened, so deep reflection may be blocked.

You can open the package at runtime to all unnamed modules with:

~~~bash
java --add-opens com.example.app/com.example.app.model=ALL-UNNAMED \
     --module com.example.app/com.example.app.Main
~~~

This option means:

- **com.example.app** is the module owning the package.
- **com.example.app.model** is the package to open.
- **ALL-UNNAMED** refers to the unnamed modules, where the classpath framework is loaded.

One point to remember: the fact that an unnamed module can read a named module does not mean the named module has opened all its packages to the framework. Module readability and deep reflection permissions are two separate issues.

## 5. opens in module-info.java and ALL-UNNAMED

In **module-info.java**, you can open a package to a specific named module:

~~~java
module com.example.app {
    exports com.example.app.api;
    opens com.example.app.model to com.example.orm;
}
~~~

This approach works when the ORM framework is also a named module named **com.example.orm**.

If the framework is on the classpath, it belongs to an unnamed module and has no name to include in the target module list of an **opens ... to ...** directive. Therefore, you cannot write **ALL-UNNAMED** in a module descriptor. Instead, you can use the launcher option:

~~~bash
--add-opens com.example.app/com.example.app.model=ALL-UNNAMED
~~~

Or open the package without restricting the target module:

~~~java
module com.example.app {
    opens com.example.app.model;
}
~~~

The **opens package;** directive opens that package to all modules at runtime. If the goal is only to grant access to a framework on the classpath, **--add-opens ...=ALL-UNNAMED** expresses a narrower scope than opening the package to every module.

You should not convert an entire module into an **open module** just to support a classpath framework. That opens every package in the module for deep reflection, which is broader than typically needed.

## 6. Distinguishing --add-reads and --add-opens

These two options often appear together when integrating modular code with legacy libraries, but they grant different permissions.

| Option | What permission does it grant? | Typical case |
|---|---|---|
| **--add-reads** | Adds a read edge between two modules | A named module needs to read types in an unnamed module |
| **--add-opens** | Opens a package of the source module for deep reflection from the target module | A framework on the classpath needs to access private members in a named module |

Example adding both in a single command:

~~~bash
java --module-path mods \
     --class-path libs/legacy.jar \
     --add-reads com.example.app=ALL-UNNAMED \
     --add-opens com.example.app/com.example.app.model=ALL-UNNAMED \
     --module com.example.app/com.example.app.Main
~~~

Here, **--add-reads** allows the application module to read the unnamed module. **--add-opens** allows the unnamed module to perform deep reflection into the application module's model package.

Do not use one option in place of the other. Opening a package does not create a read edge for code needing to reference types; adding a read edge does not automatically allow deep reflection into private members of a closed package.

## 7. Reflection into the classpath vs. reflection into a named module

The two access directions can be compared as follows:

| Reflection direction | Target module | Main rule |
|---|---|---|
| Named module reflecting into a classpath class | Unnamed module | Packages of the unnamed module are already open |
| Classpath framework reflecting into a named-module class | Named module | Target package must be open to the unnamed module if deep reflection is needed |
| Named module directly calling a classpath type | Unnamed module | Named module needs a read edge, e.g. --add-reads |
| Classpath framework calling a public API of a named module | Named module | API package needs appropriate export; unnamed module reads named modules |

This table helps avoid the misconception that because an unnamed module is open, every package in a named module is also automatically open. The openness of an unnamed module only applies to packages belonging to that unnamed module.

## 8. Complete example: framework on the classpath accessing an entity

Suppose the application module has the structure:

~~~text
src/
└── com.example.app/
    ├── module-info.java
    └── com/example/app/
        ├── Main.java
        └── model/Customer.java

libs/
└── legacy-orm.jar
~~~

Module descriptor:

~~~java
module com.example.app {
    exports com.example.app.api;
}
~~~

Entity:

~~~java
package com.example.app.model;

public class Customer {
    private String email = "customer@example.com";
}
~~~

Framework on the classpath using reflection to read the field:

~~~java
package com.example.orm;

import java.lang.reflect.Field;

public class EntityInspector {
    public static Object readField(Object entity, String fieldName)
            throws ReflectiveOperationException {
        Field field = entity.getClass().getDeclaredField(fieldName);
        field.setAccessible(true);
        return field.get(entity);
    }
}
~~~

Because the framework belongs to an unnamed module, the model package in the named module must be opened to it. You can configure:

~~~bash
java --module-path mods \
     --class-path libs/legacy-orm.jar \
     --add-opens com.example.app/com.example.app.model=ALL-UNNAMED \
     --module com.example.app/com.example.app.Main
~~~

If **--add-opens** is omitted, deep reflection on the private field may fail with **InaccessibleObjectException**. When the proper option is added, permission is granted to the unnamed module to which the framework belongs, scoped to the model package.

If the framework is migrated to a named module, **ALL-UNNAMED** can be replaced with the specific module name and the directive moved into **module-info.java**:

~~~java
module com.example.app {
    opens com.example.app.model to com.example.orm;
}
~~~

This is a clearer way to express integration permissions when both sides have module descriptors.

## 9. Notes when using frameworks and tests on the classpath

Frameworks such as ORMs, JSON mappers, dependency injection containers, or test frameworks can use reflection in various ways. Not every reflection operation requires opens. Accessing exported public APIs usually does not require deep reflection.

When configuring the runtime environment:

- Determine whether the framework belongs to a named module or an unnamed module.
- Identify which application packages the framework actually needs deep access to.
- Use qualified opens to the target named module if the framework is already modularized.
- Use **--add-opens package=ALL-UNNAMED** when the framework is on the classpath.
- Place options on the actual JVM process running the application or tests; compiler configurations do not automatically apply to the test/runtime process.
- After upgrading a framework or moving it to the module path, review old package-opening options and remove any that are no longer needed.

For Gradle or Maven, JVM options must be passed to the corresponding forked test JVM or application run task. Setting options only in a terminal running a different process does not alter the JVM running the tests.

## 10. Common errors

**InaccessibleObjectException when a framework accesses a private field**

Check which named module the class's package belongs to. If the framework belongs to an unnamed module, open the exact package to **ALL-UNNAMED** using **--add-opens**.

**Used --add-reads yet reflection still fails**

Add-reads only adds a readability relationship. If the framework needs deep reflection into a named module's package, opens or --add-opens is needed separately.

**Used --add-opens yet named module code still cannot import a class on the classpath**

Add-opens only grants reflection permission. A named module needs a read edge to the unnamed module if source code directly references classpath types, for example via **--add-reads**.

**Opening a package in module-info.java to ALL-UNNAMED does not compile**

**ALL-UNNAMED** is a special symbol for launcher options, not a valid module name in the opens directive of a module descriptor. Use **--add-opens** at runtime or open the package to a specific named module.

**Framework is still blocked even though the module has opens**

Verify that the package and target module are accurate. The framework might be loaded from the classpath in another unnamed module, or the error may come from a different package that the framework also needs to process.

**Opened the entire module yet still cannot import a package**

An open module only opens packages for deep reflection; it does not export all packages for normal access. Appropriate exports must be added if another module needs to use public APIs.

## 11. Takeaways

- Each class loader has its own unnamed module for classes it defines in the unnamed module.
- An unnamed module reads all modules, and all of its packages are exported and open.
- A named module does not automatically read unnamed modules; code directly referencing the classpath may need **--add-reads**.
- A framework on the classpath can read named modules, but deep reflection into a named module's package requires the package to be opened to the unnamed module.
- **--add-opens module/package=ALL-UNNAMED** opens a specific package to unnamed modules.
- **ALL-UNNAMED** cannot be written as a target module in an opens directive of **module-info.java**.
- **--add-reads** and **--add-opens** address two different kinds of permissions.
- Open only the necessary model packages for frameworks, keep other packages encapsulated, and avoid making the entire module open unless clearly required.

When integrating a classpath framework into a modular application, identify the reflection direction first. If modular code reflects into the classpath, the target package is already open under unnamed module rules. If a classpath framework reflects into a named module, the module owning the class must open the specific package to **ALL-UNNAMED**. This distinction helps configure JPMS with the right scope and maintain intentional module boundaries.