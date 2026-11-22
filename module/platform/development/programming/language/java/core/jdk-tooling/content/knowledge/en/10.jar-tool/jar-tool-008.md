# Class-Path in the JAR Manifest

## 1. What Are the Manifest and the Class-Path Attribute?

Every JAR file is an archive based on the ZIP format. In addition to class files and resources, a JAR can contain a manifest file at the path **META-INF/MANIFEST.MF**. The manifest stores metadata as attribute name-value pairs.

Two important attributes when creating a standalone executable JAR are:

- **Main-Class**: the name of the class containing the application entry point, typically the class with the main method.
- **Class-Path**: a list of URLs pointing to additional JARs or directories that need to be added to the class path when the JAR is used to run the application.

Manifest example:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/common.jar lib/logging.jar

~~~

When running:

~~~bash
java -jar app.jar
~~~

The Java launcher reads Main-Class to locate the main class and uses Class-Path in the manifest to find external libraries. As a result, users can launch the application with a short command without having to type the entire classpath on the command line.

**Class-Path in the manifest does not embed dependencies into the main JAR.** It only references the locations of other files or directories. When distributing the application, you must include the dependencies following the exact directory structure declared.

## 2. Basic Structure of META-INF/MANIFEST.MF

A manifest is a text file structured into sections. The first section is the main section, which contains attributes that apply to the entire JAR. Subsequent sections can describe metadata for individual entries in the archive.

A simple manifest:

~~~text
Manifest-Version: 1.0
Main-Class: demo.app.Main
Class-Path: lib/helper.jar lib/logging.jar

~~~

Important rules:

1. Each attribute has the form **Name: Value**.
2. The main section starts at the beginning of the file and ends with a blank line.
3. **Manifest-Version** should appear first in the main section.
4. **Main-Class** and **Class-Path** must be placed in the main section to apply to the entire JAR.
5. The class name in Main-Class is the fully qualified binary name, including the package, without the .class extension and without file path slashes.
6. The manifest must end its section with a blank line. The jar tool automatically generates a standard manifest when using the --manifest option.

Correct example:

~~~text
Manifest-Version: 1.0
Main-Class: com.acme.billing.Main
Class-Path: lib/common.jar lib/database.jar

~~~

Incorrect Main-Class name example:

~~~text
Main-Class: com/acme/billing/Main.class
~~~

The correct value is **com.acme.billing.Main**. The JVM uses the class name to load the class, not the class file path.

## 3. How to Write the Class-Path Attribute

Class-Path contains a list of URLs separated by one or more spaces. Each URL can be a relative path resolved from the location of the JAR containing the manifest, or an absolute URL.

Example:

~~~text
Class-Path: lib/common.jar lib/logging.jar config/

~~~

Meaning of the entries above:

- **lib/common.jar**: a JAR located in the lib directory next to the application JAR.
- **lib/logging.jar**: another dependency JAR in the same lib directory.
- **config/**: a directory of additional resources or classes; directory URLs end with a forward slash.

Do not use colons or semicolons to separate items in the manifest attribute. The separator for Class-Path is a space. This differs from the launcher -cp option, which uses the operating system's path separator: a semicolon on Windows and a colon on Linux/macOS.

Comparison example:

~~~text
# In the manifest: URLs are separated by spaces
Class-Path: lib/a.jar lib/b.jar

# On the Windows command line:
java -cp "app.jar;lib/a.jar;lib/b.jar" com.example.Main

# On the Linux/macOS command line:
java -cp "app.jar:lib/a.jar:lib/b.jar" com.example.Main
~~~

### Where Are Relative Paths Resolved From?

This is the most important rule of the manifest Class-Path: relative URLs are resolved against the URL/location of the JAR containing the manifest, not against the terminal's current working directory.

Suppose the structure is:

~~~text
deployment/
  app.jar
  lib/
    helper.jar
    logging.jar
~~~

Inside app.jar:

~~~text
Class-Path: lib/helper.jar lib/logging.jar

~~~

When running app.jar from the deployment directory, dependencies are looked up in deployment/lib. If the user changes to another directory and runs the JAR using its full path, the relative URLs are still resolved from the location of app.jar.

Paths must point to the exact packaged files or directories. On case-sensitive operating systems, directory and file names in the manifest must also match exact casing.

### Paths with Spaces

Class-Path uses spaces as URL separators, so spaces in file names must be URL-encoded, typically as **%20**.

Example:

~~~text
Class-Path: lib/My%20Library.jar
~~~

Do not wrap paths containing spaces in single or double quotes as in shell commands; the manifest does not apply shell quoting rules.

## 4. Relationship Between Main-Class, Class-Path, and java -jar

An executable JAR typically declares both Main-Class and Class-Path:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/common.jar lib/database.jar

~~~

Run with:

~~~bash
java -jar app.jar
~~~

The launcher performs these main steps:

1. Opens the specified JAR.
2. Reads the manifest.
3. Finds the class declared in Main-Class.
4. Builds the application class path from the main JAR and the URLs in Class-Path.
5. Loads the main class and invokes the main method.

Arguments placed after the JAR name are passed to main(String[] args):

~~~bash
java -jar app.jar --port 8080 production
~~~

In this example, --port and production are application arguments. They are not VM options or launcher options.

### How Do Manifest Class-Path and -cp Differ?

| Criterion | Manifest Class-Path | Launcher -cp / --class-path |
|---|---|---|
| Where declared | META-INF/MANIFEST.MF | Command line or script |
| Separator | Spaces between URLs | OS-specific path separator |
| Relative paths | Resolved from the JAR containing the manifest | Resolved from the current working directory |
| Purpose | Bind dependencies to the JAR configuration | Specify a classpath for a single run |
| When using -jar | Used by the launcher | External classpath provided by -cp is ignored in -jar mode |

If you need to specify the classpath directly, you can run the main class instead of using -jar:

~~~bash
java -cp "app.jar:lib/helper.jar" com.example.Main
~~~

On Windows, replace the colon with a semicolon. In -jar mode, place dependencies in the manifest's Class-Path and ensure those paths exist.

## 5. Practice: Creating a Two-JAR Application

Let's create a small application consisting of:

- **app.jar**: contains the main class demo.app.Main.
- **helper.jar**: contains the class demo.support.MessageProvider.
- The manifest of app.jar declares Main-Class and Class-Path.

Project structure:

~~~text
project/
  src/
    demo/
      app/
        Main.java
      support/
        MessageProvider.java
  build/
    classes/
    lib/
      helper.jar
    app.jar
  manifest.mf
~~~

### Step 1: Create the Library Class

File src/demo/support/MessageProvider.java:

~~~java
package demo.support;

public class MessageProvider {
    public String message() {
        return "Loaded from helper.jar";
    }
}
~~~

### Step 2: Create the Main Class

File src/demo/app/Main.java:

~~~java
package demo.app;

import demo.support.MessageProvider;

public class Main {
    public static void main(String[] args) {
        System.out.println(new MessageProvider().message());
        System.out.println("args=" + String.join(",", args));
    }
}
~~~

### Step 3: Compile the Classes

Create the build/classes and build/lib directories, then run:

~~~bash
javac --release 17 -d build/classes \
    src/demo/support/MessageProvider.java \
    src/demo/app/Main.java
~~~

After this command, the class files are located in:

~~~text
build/classes/demo/support/MessageProvider.class
build/classes/demo/app/Main.class
~~~

### Step 4: Package helper.jar

Run from the project directory:

~~~bash
jar --create --file build/lib/helper.jar \
    -C build/classes demo/support
~~~

The -C option changes the packaging root directory to build/classes and adds only the demo/support package. Therefore, inside helper.jar, the class path remains demo/support/MessageProvider.class.

### Step 5: Create the Manifest for app.jar

File manifest.mf:

~~~text
Manifest-Version: 1.0
Main-Class: demo.app.Main
Class-Path: lib/helper.jar

~~~

Class-Path is written relative to build/app.jar. The main JAR is in build, while helper.jar is in build/lib, so the URL lib/helper.jar points to the dependency correctly.

### Step 6: Package app.jar

~~~bash
jar --create --file build/app.jar \
    --manifest manifest.mf \
    -C build/classes demo/app
~~~

The main JAR contains only the demo/app package. The dependency remains external in build/lib/helper.jar and is referenced by the manifest.

### Step 7: Run the Application

~~~bash
java -jar build/app.jar one two
~~~

Expected output:

~~~text
Loaded from helper.jar
args=one,two
~~~

If you delete or rename build/lib/helper.jar, the application may start but will fail with an error when the JVM needs to load MessageProvider. This proves that Class-Path only references the dependency; it does not copy the library into app.jar.

## 6. Inspecting the Manifest and Dependencies

When the application cannot find a class, verify both the JAR contents and the dependency paths.

### View JAR Contents

~~~bash
jar --list --file build/app.jar
jar --list --file build/lib/helper.jar
~~~

In app.jar, verify it contains:

~~~text
META-INF/MANIFEST.MF
demo/app/Main.class
~~~

In helper.jar, verify it contains:

~~~text
META-INF/MANIFEST.MF
demo/support/MessageProvider.class
~~~

A default manifest can be generated automatically by jar. If using a custom manifest, inspect META-INF/MANIFEST.MF inside app.jar to confirm that Main-Class and Class-Path are correct.

You can extract just the manifest:

~~~bash
jar --extract --file build/app.jar META-INF/MANIFEST.MF
~~~

Then open META-INF/MANIFEST.MF and verify:

~~~text
Manifest-Version: 1.0
Main-Class: demo.app.Main
Class-Path: lib/helper.jar
~~~

### Verify Paths When Running from Another Directory

Suppose app.jar and lib/helper.jar are in deployment as in the previous example. You can switch to another working directory and run the JAR by its absolute path:

~~~bash
cd /tmp
java -jar /opt/myapp/deployment/app.jar
~~~

If the manifest declares the relative Class-Path correctly, the JVM still locates the dependency relative to deployment/app.jar. This is a good check to avoid confusion between manifest paths and the current working directory.

### Inspect Classpath and Class Sources

You can enable class-loading logs to see where the JVM loads classes from:

~~~bash
java -Xlog:class+load=info -jar build/app.jar
~~~

This log is useful when there are multiple copies of the same class or when the application loads the wrong dependency version. The log output can be long; filter by the class name you want to inspect.

## 7. Multiple Dependencies and Search Order

Class-Path can list multiple JARs:

~~~text
Class-Path: lib/core.jar lib/json.jar lib/logging.jar

~~~

URLs are processed in the order listed in the attribute. When multiple locations contain the same class name, the class path order can determine which class is loaded first. This is a common cause of using the wrong library version.

A few notes:

- Avoid putting two different versions of the same library on the class path.
- Keep JAR names and locations stable in the release package.
- Check the transitive dependencies required by each library.
- A referenced JAR may declare its own Class-Path in its manifest; therefore, also check dependency manifests when diagnosing issues.
- Do not rely on the accidental order of file copying or packaging to resolve class conflicts.

The manifest Class-Path is not a full dependency management tool. It does not manage versions, scopes, checksums, dependency conflicts, or module-based library loading. For projects with many libraries, use Maven or Gradle to resolve dependencies and produce a clearly structured distribution package.

## 8. Class-Path in the Manifest and the Module Path

The manifest Class-Path belongs to the traditional class path mechanism, typically used with non-modular JARs and applications running on the class path class loader.

The Java Platform Module System has its own mechanisms:

- **--class-path / -cp**: searches for classes in directories and JARs on the class path.
- **--module-path / -p**: searches for modules with descriptors or automatic modules.
- **module-info.java**: declares requires, exports, opens, and module relationships.

The Class-Path attribute does not replace requires declarations in module-info.java. If an application is designed around named modules, manage dependencies using the module path and module descriptors instead of trying to use manifest Class-Path as a module system.

A modular JAR can be packaged with module-info.class. When run on the module path, the JVM resolves module relationships according to JPMS rules. Do not confuse a JAR having a manifest with a JAR automatically becoming a fully declared module.

## 9. Creating a Manifest with the jar Tool and Build Tools

### Using jar

The jar tool can accept an existing manifest:

~~~bash
jar --create --file app.jar --manifest manifest.mf -C classes .
~~~

Or set Main-Class via an option:

~~~bash
jar --create --file app.jar --main-class com.example.Main -C classes .
~~~

When Class-Path is needed, create a manifest containing that attribute and pass it with --manifest. If you use both a custom manifest and the --main-class option, check the final manifest to make sure there is only one correct Main-Class.

### Maven

With Maven, you can configure the Maven JAR Plugin to write Main-Class and Class-Path into the manifest. Basic configuration example:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <configuration>
        <archive>
            <manifest>
                <mainClass>demo.app.Main</mainClass>
                <addClasspath>true</addClasspath>
                <classpathPrefix>lib/</classpathPrefix>
            </manifest>
        </archive>
    </configuration>
</plugin>
~~~

The addClasspath setting instructs the plugin to write dependency classpath entries into the manifest. The distribution structure must still place the dependency JARs in the matching lib/ directory relative to the application JAR. Writing the manifest alone does not automatically copy dependencies into that directory; configure an additional copy step or an appropriate assembly/distribution step.

### Gradle

Gradle allows customizing the manifest when building a JAR:

~~~groovy
tasks.jar {
    manifest {
        attributes(
            'Main-Class': 'demo.app.Main',
            'Class-Path': configurations.runtimeClasspath.files
                .collect { file -> "lib/" + file.name }
                .join(' ')
        )
    }
}
~~~

This is an illustrative example of building the list from runtimeClasspath. If you use this configuration, ensure the dependency files are actually copied into the lib directory next to the JAR during distribution. Additional handling is needed for duplicate file names or dependencies with different versioned names.

For real-world applications, the Gradle Application Plugin, Maven Assembly Plugin, or an equivalent packaging tool usually helps produce a complete distribution directory containing the application JAR, dependencies, and launch scripts.

## 10. Limitations and Common Errors

### ClassNotFoundException or NoClassDefFoundError

Common causes:

- The dependency JAR is not at the location declared in Class-Path.
- Case mismatch in file or directory names.
- The manifest uses paths relative to the working directory instead of the JAR location.
- The dependency was not copied into the release package.
- Another transitive dependency is missing further down the dependency chain.

How to troubleshoot: inspect META-INF/MANIFEST.MF inside the JAR, check the actual files on disk, run jar --list, and enable class-loading logs.

### Main Method Not Found

Verify that Main-Class has the exact fully qualified binary class name. That class needs an appropriate entry point, for example:

~~~java
public static void main(String[] args)
~~~

Do not include .class, do not use directory paths, and do not misspell the package name.

### Paths with Spaces

Encode spaces in URLs as %20. Do not add shell quotes to manifest values. Whenever possible, use simple directory names without spaces to reduce deployment errors.

### JAR Works on the Development Machine but Fails on Another Machine

The development machine may accidentally have dependencies on the classpath, in the IDE, or in environment variables. The deployment machine only has the packaged files. Test running java -jar from a different working directory and in a clean environment to verify package self-containment.

### Using -cp with -jar Still Fails to Load Dependencies

In java -jar mode, an external classpath provided by -cp or CLASSPATH is not used to replace the application's classpath. Put dependencies in the manifest's Class-Path or run the main class using java -cp ... com.example.Main.

### Manifest Too Long or Malformed

According to the JAR specification, a manifest line must not exceed **72 bytes** before the newline. Long lines must be wrapped, and the continuation line must start with a single space to continue the previous value. Length is measured in bytes, not simply the number of Unicode characters. Let the jar tool or build tool generate the manifest rather than manually concatenating long lines.

Continuation line example:

~~~text
Class-Path: lib/core.jar lib/json.jar lib/logging.jar
 lib/metrics.jar lib/database.jar

~~~

The leading space on the second line is a continuation marker, not a new separator.

## 11. Security and Operations

The manifest Class-Path directly affects which libraries the application loads. Therefore:

- Distribute dependencies only from trusted sources.
- Do not allow untrusted users to replace JARs in the lib directory.
- Verify dependency versions and checksums in the release pipeline.
- Avoid absolute paths tied to a specific machine.
- Keep the deployment directory structure stable.
- Do not let untrusted JARs appear before trusted libraries on the class path.
- Record the list of dependencies and versions in release artifacts or metadata.

Class-Path only declares where to find libraries; it does not verify the security, origin, or compatibility of those JARs.

## 12. Checklist Before Releasing an Executable JAR

- [ ] The manifest has the correct Manifest-Version and Main-Class.
- [ ] Main-Class is the fully qualified class name without .class.
- [ ] Class-Path is in the main section of the manifest.
- [ ] Class-Path entries are separated by spaces.
- [ ] Relative URLs are resolved from the location of the JAR containing the manifest.
- [ ] Dependency JARs and directories exist in the distribution package.
- [ ] Paths containing spaces are properly encoded.
- [ ] There are no duplicate dependency versions or shadowed classes.
- [ ] Tested running with java -jar from a different working directory.
- [ ] Checked output and class-loading logs when errors occur.
- [ ] Use Maven/Gradle to manage dependencies if the application has many libraries.
- [ ] Distinguish the traditional class path from the JPMS module path.
