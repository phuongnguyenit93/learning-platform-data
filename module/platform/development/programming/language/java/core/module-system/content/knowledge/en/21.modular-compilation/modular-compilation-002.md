# javac --module-path and --add-modules

## 1. Why Does javac Need a Module Path?

When compiling a Java application that uses the Java Platform Module System (JPMS), the **javac** compiler must locate the modules that the source code depends on. The **--module-path** option specifies where those modules are located.

The module path can contain:

- A modular JAR containing a **module-info.class** file.
- A compiled module directory in exploded module form.
- An automatic module, meaning a JAR without a module descriptor that is recognized as an automatic module when placed on the module path.

For example, a **lib** directory contains the JAR **com.example.codec.jar**. The application module declares:

~~~java
module com.example.app {
    requires com.example.codec;
}
~~~

You can compile the application module with:

~~~bash
javac --module-path lib \
      --module-source-path src \
      -d out \
      -m com.example.app
~~~

In this command:

- **--module-path lib** (short form **-p lib**) helps javac find dependency modules in the lib directory.
- **--module-source-path src** specifies the directory structure containing the modules' source code.
- **-d out** specifies where to write compiled class files and module descriptors.
- **-m com.example.app** selects the module to compile.

If dependency modules reside elsewhere, include those locations in the module path. The compiler must be able to resolve the modules declared in **requires** of the module being compiled.

## 2. Distinguishing Module Path and Classpath

The **classpath** contains classes and JARs loaded into the unnamed module. The **module path** contains modules that can be recognized and resolved by module name by the JPMS.

| Option | Purpose | Organization |
|---|---|---|
| **--class-path** or **-cp** | Find classes and JARs on the classpath | Classes belong to the unnamed module |
| **--module-path** or **-p** | Find named modules and automatic modules | Module descriptors, module names, and module graph |
| **--module-source-path** | Find source code of multiple modules | Source directories organized by module name |

Example of compiling a regular classpath program:

~~~bash
javac -cp "lib/*" -d out src/com/example/Main.java
~~~

Example of compiling a named module whose dependencies are on the module path:

~~~bash
javac -p lib -d out --module-source-path src -m com.example.app
~~~

Do not place a library on the classpath just to avoid module declarations. If the application already uses named modules and the library can be used as a module, place the library on the module path and declare the appropriate **requires**.

A library JAR can be a modular JAR or an automatic module. You can inspect how the JDK recognizes the module using:

~~~bash
jar --describe-module --file lib/com.example.codec.jar
~~~

If the JAR has a module descriptor, the module name is taken from the descriptor. If there is no descriptor, the automatic module name is derived from metadata or the JAR filename, unless the manifest declares **Automatic-Module-Name**. You should use the stable module name published by the library instead of guessing from the filename.

## 3. Multi-Module Source Code Structure

When compiling multiple modules from a source tree, each module usually resides in its own directory with the same name as the module:

~~~text
project/
  src/
    com.example.model/
      module-info.java
      com/example/model/Customer.java
    com.example.app/
      module-info.java
      com/example/app/Main.java
  lib/
    com.example.codec.jar
  out/
~~~

Model module:

~~~java
module com.example.model {
    exports com.example.model;
}
~~~

Class in the model module:

~~~java
package com.example.model;

public record Customer(String name) {}
~~~

Application module:

~~~java
module com.example.app {
    requires com.example.model;
    requires com.example.codec;
}
~~~

Entry-point class:

~~~java
package com.example.app;

import com.example.model.Customer;

public class Main {
    public static void main(String[] args) {
        Customer customer = new Customer("Lan");
        System.out.println(customer.name());
    }
}
~~~

If **com.example.codec** is an external library packaged as a JAR, the **lib** directory must contain that JAR and its module descriptor must declare the needed package with **exports**.

You can compile the source modules simultaneously with:

~~~bash
javac \
  --module-path lib \
  --module-source-path src \
  -d out \
  -m com.example.model,com.example.app
~~~

This command selects two source modules to compile. javac reads the module descriptors, checks the **requires** relationships, locates dependency modules on the module source path and module path, and writes the output to **out**.

If source modules depend on one another in a valid relationship, include them in the same compilation pass or compile them in dependency order. An invalid module dependency cycle cannot be resolved simply by adding module names to the command line.

After compilation, the output directory has a structure similar to:

~~~text
out/
  com.example.model/
    module-info.class
    com/example/model/Customer.class
  com.example.app/
    module-info.class
    com/example/app/Main.class
~~~

These are exploded modules. You can use the **out** directory directly as a module path when running the application:

~~~bash
java --module-path out:lib \
     -m com.example.app/com.example.app.Main
~~~

On Windows, the separator between module path entries is a semicolon:

~~~powershell
java --module-path "out;lib" -m com.example.app/com.example.app.Main
~~~

## 4. Using --module-path in Common Scenarios

### Compiling a Module That Depends on an External JAR

Suppose the source tree only contains **com.example.app**, while the library **com.example.codec** is already packaged in **lib**:

~~~bash
javac \
  --module-path lib \
  --module-source-path src \
  -d out \
  -m com.example.app
~~~

In the application's **module-info.java**:

~~~java
module com.example.app {
    requires com.example.codec;
}
~~~

javac finds the **com.example.codec** module on the module path, checks exported packages, and allows the source code to use the public types exposed by that module.

### Compiling a Single Source Module Without a Multi-Module Source Tree

If you only have one module and want to specify source files directly, you can pass the **module-info.java** file along with the Java files:

~~~bash
javac --module-path lib \
      -d out \
      src/module-info.java \
      src/com/example/app/Main.java
~~~

This approach fits a simple source tree. For multi-module projects, **--module-source-path** and **-m** make module selection clearer and more scalable.

### Using Module Path Together with Classpath

In a project migrating gradually to JPMS, some libraries may still remain on the classpath while named modules are already compiled on the module path. In that case, you can use **--class-path** and **--module-path** together:

~~~bash
javac \
  --module-path mods \
  --class-path "legacy-libs/*" \
  --module-source-path src \
  -d out \
  -m com.example.app
~~~

You must verify accurately which libraries are named modules and which are used on the classpath. Do not place the same library in both locations, as it can cause duplicate classes or resolution conflicts.

## 5. What Does --add-modules Mean?

The **--add-modules** option instructs javac to add one or more modules to the set of root modules to resolve:

~~~bash
javac --module-path lib \
      --add-modules com.example.codec \
      -d out \
      -cp src \
      src/com/example/Main.java
~~~

This option is useful when compiling code belonging to the unnamed module that needs to see a named module on the module path, or when extra modules need to be brought into the module graph for resolution during compilation.

You can specify multiple modules separated by commas:

~~~bash
javac --module-path lib \
      --add-modules com.example.codec,com.example.json \
      -d out \
      -cp src \
      src/com/example/Main.java
~~~

In addition to specific module names, special values can be used:

- **ALL-MODULE-PATH**: adds all observable modules on the module path to the set of modules to resolve.
- **ALL-SYSTEM**: adds all system modules to the set of modules to resolve.

Example:

~~~bash
javac --module-path lib \
      --add-modules ALL-MODULE-PATH \
      -d out \
      -cp src \
      src/com/example/Main.java
~~~

Using **ALL-MODULE-PATH** can be convenient when exploring or integrating many modules, but it widens the resolution scope. For stable builds, prefer listing specific modules so the result is easier to control.

## 6. --add-modules Does Not Replace requires

This is an important point to remember when compiling a named module.

Suppose the application module has the following code:

~~~java
package com.example.app;

import com.example.codec.Encoder;

public class Main {
    public static void main(String[] args) {
        Encoder encoder = new Encoder();
        System.out.println(encoder.encode("hello"));
    }
}
~~~

If this code belongs to the named module **com.example.app**, the module descriptor must still declare:

~~~java
module com.example.app {
    requires com.example.codec;
}
~~~

Passing **--add-modules com.example.codec** on the command line does not automatically edit **module-info.java**, does not establish a readability relationship in place of **requires**, and does not automatically export packages from the dependency module.

The two parts have different roles:

- **requires** is the dependency contract recorded in the module descriptor and distributed with the module.
- **--add-modules** adjusts the set of root modules included in the resolution process of the javac command.

Therefore, when a named module's source code directly imports types from another module, declare **requires**. Only use **--add-modules** when you need to expand the set of resolved modules beyond the default root modules.

For code in the unnamed module on the classpath, the rule is different: the unnamed module can read all resolved named modules. In that case, **--module-path** provides the modules and **--add-modules** can bring them into the graph so classpath code can use their exported public APIs.

## 7. Distinguishing -m and --add-modules

The two options have similar names, but different responsibilities:

| Option | Meaning |
|---|---|
| **-m** or **--module** | Specifies the source modules to compile |
| **--add-modules** | Adds modules to the set of root modules to resolve |

Example:

~~~bash
javac --module-path lib \
      --module-source-path src \
      -d out \
      -m com.example.app
~~~

The command above selects **com.example.app** for compilation.

Meanwhile:

~~~bash
javac --module-path lib \
      --add-modules com.example.tools \
      --module-source-path src \
      -d out \
      -m com.example.app
~~~

The second command still compiles **com.example.app**, while also requesting that **com.example.tools** be resolved. If code in the named module needs to read and use the tools API, the descriptor must still have an appropriate declaration, typically **requires com.example.tools**.

Do not confuse `javac`'s **-m** with `java`'s **-m** across contexts. With javac, **-m** selects the modules to compile; with java, **-m** selects the module to launch.

## 8. When Is --add-modules Needed?

Some situations may require adding modules to the resolution set:

1. **A classpath application uses an API from a named module:** specify the module on the module path and add it with **--add-modules** so the compiler recognizes the module.
2. **Dynamically selected dependencies:** the module name comes from configuration or a plugin mechanism, so it does not appear in static `requires` relationships.
3. **Inspecting the module graph:** use **ALL-MODULE-PATH** to inspect the modules present on the module path.
4. **Build requires additional system modules:** specify particular JDK modules when instructing the build tool to resolve those modules.

If a named module directly uses another module's API, declaring **requires** remains the right way to describe the dependency. If a module needs to be read dynamically without being declared in the descriptor, tools supporting JPMS also provide the **--add-reads** option; this is a separate mechanism and should be used carefully because it alters readability relationships outside the descriptor.

**--add-modules** also does not replace **--add-exports** or **--add-opens**. Those options address package access or reflection permissions, whereas **--add-modules** only adds modules to the resolution set.

## 9. Verifying Modules and Compilation Output

After compiling, you can inspect the modules in the output:

~~~bash
java --module-path out:lib --list-modules
~~~

Inspect the descriptor of a compiled module:

~~~bash
java --module-path out --describe-module com.example.app
~~~

If a dependency module is a JAR, you can view its descriptor:

~~~bash
jar --describe-module --file lib/com.example.codec.jar
~~~

These commands help confirm the module names recognized by the JDK. If a module name differs from what is written in **requires**, check the descriptor or automatic module name of the JAR.

When building for a specific Java version, you can use **--release**:

~~~bash
javac --release 17 \
      --module-path lib \
      --module-source-path src \
      -d out \
      -m com.example.app
~~~

**--release** controls the language version, bytecode version, and platform APIs that the source code is allowed to use. Choose a release matching the target runtime rather than relying solely on the JDK version installed on the build machine.

## 10. Common Errors and How to Handle Them

**module not found**

A module declared in **requires** or **--add-modules** cannot be found. Check the module path, module name, JAR filename, and module descriptor. If using an exploded module directory, ensure the directory containing **module-info.class** is at the proper level.

**package is not visible**

The dependency module was found, but the required package has not been exported by that module. Check **exports** in the providing module's descriptor. Adding **--add-modules** cannot replace an `exports` declaration.

**module does not read ...**

The current module does not yet have a readability relationship to the module containing the API. For a named module, check **requires** in the module descriptor. Special situations may require **--add-reads**, though it should only be used when you clearly understand the intended module relationships.

**package does not exist**

The JAR may be placed incorrectly on the classpath or module path, the package may not be exported, or the dependency may be missing from the build. Check how the library is classified and its actual module name using **jar --describe-module**.

**Module name does not match**

The name in **requires** must match the module name recognized by the JDK. For an automatic module, check **Automatic-Module-Name** or the name derived from the JAR filename. Do not rename the file blindly without confirming the module name.

**Compiles successfully but runtime reports missing module**

The classpath and module path at runtime must provide the corresponding components accurately. Modules must be resolved in the runtime graph; if dependencies are selected dynamically, add the modules to the launch configuration or appropriate runtime image.

## 11. Recommended Modular Build Workflow

When building a JPMS application, you can follow this sequence:

1. Organize the source tree by module name and place **module-info.java** inside each module.
2. Identify which library JARs are modular JARs, automatic modules, or classpath libraries.
3. Place dependency modules on **--module-path**.
4. Declare direct dependencies using **requires** in the module descriptor.
5. Use **--module-source-path** and **-m** to select the source modules to compile.
6. Only use **--add-modules** when you need to add modules to the resolution set; do not use it to mask a missing `requires` declaration.
7. Write output to a dedicated directory using **-d**.
8. Verify module names and descriptors after compilation.
9. Run the application with the corresponding module path and test its functionality.
10. Record the JDK version, target release, module path, and build commands for reproducibility in CI.

Example combined compilation command:

~~~bash
javac \
  --release 17 \
  --module-path lib \
  --module-source-path src \
  -d out \
  -m com.example.model,com.example.app
~~~

If the project has additional modules that must be resolved beyond the root modules, add **--add-modules** with specific names and recheck the module graph.

## 12. Key Takeaways

- **--module-path** or **-p** tells javac where to find named modules and automatic modules.
- **--module-source-path** organizes the source code of multiple modules.
- **-m** or **--module** selects the modules to compile.
- **--add-modules** adds modules to the set of root modules to resolve.
- **requires** in **module-info.java** is the actual declaration of a named module's direct dependencies.
- **exports**, **opens**, **--add-reads**, and **--add-exports** address different access aspects; they are not equivalent to adding a module to the module graph.
- Use **--release** when building for a target Java version and verify JAR module names before concluding that the module path is configured correctly.

When you clearly understand the roles of module path, `requires`, and `--add-modules`, compiling modular applications becomes predictable and reproducible. The descriptor describes the module's true dependencies; command-line options control the compilation and resolution scope for each build.
