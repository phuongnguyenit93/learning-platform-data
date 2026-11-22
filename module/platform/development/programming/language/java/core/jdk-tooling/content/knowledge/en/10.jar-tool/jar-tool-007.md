# The Main-Class Attribute in JAR

A JAR (Java Archive) file can package a Java application's class files, resources, and metadata. To run an application from a JAR using the `java -jar` command, the JVM needs to know which class contains the program's entry point. This information is declared using the **`Main-Class`** attribute in the JAR's manifest.

`Main-Class` tells the Java launcher which class to launch. The value of this attribute is the main class's fully qualified binary name, such as `app.Main`, rather than a `.class` file path.

## 1. What Is a JAR Manifest?

The manifest is a metadata file named:

```text
META-INF/MANIFEST.MF
```

The manifest resides inside the JAR and contains name–value attribute pairs. It can describe the launch class, dependency classpath, version information, vendor details, and other metadata.

A minimal manifest typically looks like this:

```text
Manifest-Version: 1.0
Main-Class: app.Main

```

Meaning:

- `Manifest-Version: 1.0` specifies the manifest format version.
- `Main-Class: app.Main` specifies the class containing the main method that the Java launcher should invoke.
- The trailing blank line terminates the main attributes section of the manifest.

When using `jar` to create a JAR, the tool can generate a default manifest automatically. If `--main-class` is specified, the tool writes the appropriate `Main-Class` attribute into the manifest.

**Note:** `Main-Class` must be placed in the main attributes section at the top of the manifest, before the blank line that separates named sections. Placing it in a named section does not declare a default entry point for the entire JAR.

## 2. Which Class Should Main-Class Point To?

For a standard Java application on the classpath, the class declared in `Main-Class` must have a valid main method for the Java launcher to invoke.

Common form:

```java
public static void main(String[] args)
```

Example:

```java
package app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from executable JAR");
    }
}
```

Because the class is in the `app` package, the manifest value must be:

```text
Main-Class: app.Main
```

Important notes:

- Use the fully qualified class name, including the package if the class belongs to one.
- Do not append the `.class` extension.
- Do not replace package-separating dots with slashes.
- Class names are case-sensitive.
- The main class's class file must be present in the JAR or in a location discoverable by the class loader.
- The main method must have a signature supported by the Java launcher; for example, Java 17 uses `public static void main(String[] args)`.

For example, the correct value is `app.Main`, not `app/Main.class`.

## 3. Creating an Executable JAR with the --main-class Option

Suppose the project has the following structure:

```text
project/
  src/
    app/
      Main.java
```

Create the file **`src/app/Main.java`**:

```java
package app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from executable JAR");
    }
}
```

### Step 1: Compile the source code

Run from the `project` root directory:

```bash
javac -d out src/app/Main.java
```

After compiling, the class file is located at:

```text
out/
  app/
    Main.class
```

The `out` directory is the root of the package structure. When packaging, the `app/Main.class` path must be preserved inside the JAR.

### Step 2: Create the JAR and declare Main-Class

Run:

```bash
jar --create --file app.jar --main-class app.Main -C out .
```

Explanation:

- `--create`: creates a new JAR.
- `--file app.jar`: specifies the output JAR file name.
- `--main-class app.Main`: writes the launch class into the manifest.
- `-C out .`: changes into the `out` directory and adds its contents to the JAR.

After running, the project structure is:

```text
project/
  app.jar
  out/
    app/
      Main.class
  src/
    app/
      Main.java
```

Inside the JAR, the class file is at `app/Main.class`, and the manifest is at `META-INF/MANIFEST.MF`.

### Step 3: Run the JAR

Run:

```bash
java -jar app.jar
```

Output:

```text
Hello from executable JAR
```

A JAR is called an executable JAR because the Java launcher can locate the launch class through the manifest and run the application with `java -jar`.

This term means the JAR can be run by the Java launcher; the JAR file itself is not necessarily a standalone native executable for the operating system.

## 4. Creating a Manifest Manually

In addition to `--main-class`, you can create a manifest file manually and pass it to `jar`.

Create **`MANIFEST.MF`** in the project root directory:

```text
Manifest-Version: 1.0
Main-Class: app.Main

```

After compiling the class into `out`, create the JAR:

```bash
jar --create --file app.jar --manifest MANIFEST.MF -C out .
```

Run:

```bash
java -jar app.jar
```

Output:

```text
Hello from executable JAR
```

Using a manual manifest is useful when you need to declare additional attributes such as `Class-Path`, version information, or custom metadata.

When using a custom manifest, make sure that:

- The file is named `MANIFEST.MF` (the source file does not strictly have to use this name, but it is a recognizable convention).
- Lines follow the `Attribute-Name: value` format.
- There is a blank line terminating the main section.
- No arbitrary leading spaces are inserted before attribute names.
- If a line is too long, follow the manifest line-wrapping rule: the continuation line starts with a single space; the length limit is measured in bytes, not just characters.
- For manifests containing Unicode content, save them in UTF-8 and follow the JAR manifest specification.

Do not place `Main-Class` after the first blank line if you want it to serve as the default entry point.

## 5. Verifying That Main-Class Is Written to the JAR

After creating the JAR, you should verify both the archive contents and the manifest.

### Listing the JAR contents

Run:

```bash
jar --list --file app.jar
```

The output should include entries similar to:

```text
META-INF/
META-INF/MANIFEST.MF
app/
app/Main.class
```

The order and some displayed entries may vary by tool version, but both the manifest and the main class's class file must be present.

### Extracting the manifest to inspect it

You can extract just the manifest:

```bash
jar --extract --file app.jar META-INF/MANIFEST.MF
```

Then read the extracted file:

**Windows PowerShell:**

```powershell
Get-Content META-INF/MANIFEST.MF
```

**macOS/Linux:**

```bash
cat META-INF/MANIFEST.MF
```

The contents should look like:

```text
Manifest-Version: 1.0
Created-By: ...
Main-Class: app.Main
```

Additional attributes such as `Created-By` depend on the JDK. What you need to verify is that `Main-Class` has the correct class name and is located in the main attributes section.

## 6. Passing Arguments to the Program When Running a JAR

Application arguments are placed after the JAR file name:

```bash
java -jar app.jar production 8080
```

The Java launcher invokes the main method of the class declared in the manifest. Inside the method:

- `args[0]` receives `production`.
- `args[1]` receives `8080`.
- `args.length` equals 2.

Example:

```java
package app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Argument count: " + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "]=" + args[i]);
        }
    }
}
```

Output when running `java -jar app.jar production 8080`:

```text
Argument count: 2
args[0]=production
args[1]=8080
```

You should distinguish between JVM arguments and application arguments:

```bash
java -Xmx512m -Dapp.mode=production -jar app.jar arg1 arg2
```

- `-Xmx512m` and `-Dapp.mode=production` are JVM options, placed before `-jar`.
- `arg1` and `arg2` are passed into `main(String[] args)`.

## 7. Main-Class and Class-Path in the Manifest

An application may depend on external JARs. The manifest supports the `Class-Path` attribute to declare dependency locations for the Java launcher.

Example structure:

```text
project/
  app.jar
  lib/
    helper.jar
    logging.jar
```

Manifest contents:

```text
Manifest-Version: 1.0
Main-Class: app.Main
Class-Path: lib/helper.jar lib/logging.jar

```

Entries in `Class-Path` are URLs separated by spaces. Relative paths are resolved relative to the location of the JAR containing the manifest.

Create the JAR with the manifest:

```bash
jar --create --file app.jar --manifest MANIFEST.MF -C out .
```

If the dependencies are located at `lib/helper.jar` and `lib/logging.jar` relative to `app.jar`, preserve that directory structure when deploying.

Run:

```bash
java -jar app.jar
```

The Java launcher uses `Main-Class` as the entry point and reads `Class-Path` to locate dependencies.

Notes:

- `Class-Path` does not package dependent JARs inside `app.jar`; it only references external locations.
- The paths must exist at runtime and resolve properly relative to the JAR's location.
- Each entry is a URL; if a path contains special characters or spaces, it must be properly URL-encoded.
- Do not use operating-system classpath separators (`;` or `:`) in this manifest value; URLs are separated by spaces.
- Wildcards such as `lib/*` are not a standard way to declare dependencies in the manifest `Class-Path`; list the specific JARs.
- Do not put secrets or credentials in the manifest.

## 8. Differences Between java -jar and java -cp

These two common launch methods follow different rules:

| Run command | Launch class | How dependencies are resolved |
| --- | --- | --- |
| `java -cp "out:lib/*" app.Main` (macOS/Linux) | Class name specified on the command line | Classpath passed via `-cp` |
| `java -cp "out;lib/*" app.Main` (Windows) | Class name specified on the command line | Classpath passed via `-cp` |
| `java -jar app.jar` | `Main-Class` attribute in the manifest | The main JAR and `Class-Path` entries in the manifest |

When using `java -jar`, other classpath settings on the command line or the `CLASSPATH` environment variable are not used to determine the application classpath in the usual way. If the application requires external JARs, declare the dependencies in the manifest or launch by class name with `-cp`.

For example, the following command is not a valid way to add a library in `-jar` mode:

```bash
java -cp lib/helper.jar -jar app.jar
```

Instead, put the dependency in the manifest `Class-Path`, or use classpath launch mode:

```bash
java -cp "app.jar:lib/helper.jar" app.Main
```

The last command uses a colon on macOS/Linux. On Windows, replace the separator with a semicolon.

## 9. Updating Main-Class of an Existing JAR

If you already have a JAR and want to change its launch class, you can update the manifest with the `jar` tool:

```bash
jar --update --file app.jar --main-class app.Main
```

After updating, inspect the manifest and run it again:

```bash
jar --list --file app.jar
java -jar app.jar
```

Only update a JAR when you have permission to modify that artifact and clearly understand the new main class. If the JAR is generated automatically in a build pipeline, you should fix the build configuration so the next package produces the correct manifest rather than patching the artifact manually after each build.

## 10. Common Errors with Main-Class

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `no main manifest attribute` | The manifest lacks a `Main-Class` attribute in the main section | Recreate the JAR with `--main-class` or a manifest containing `Main-Class` |
| `Could not find or load main class` | `Main-Class` has the wrong name or package, or the class is missing from the JAR/classpath | Check the class name and JAR contents with `jar --list` |
| `Main method not found` or similar error | The declared class does not have a valid main method for the launcher | Check `public static void main(String[] args)` |
| Works with `-cp` but fails with `-jar` | The manifest is missing dependencies or has an incorrect `Class-Path` | Check the manifest and the locations of dependent JARs |
| Edited the manifest but behavior is unchanged | The JAR being run is not the modified artifact or the manifest was not updated properly | Verify the JAR path, list its contents, and re-read the manifest |
| Dependency with spaces in its name is not found | The URL in `Class-Path` is not properly encoded | Use a valid URL or place the dependency in a simpler path |
| Main class is found, but loading another class fails | Missing transitive dependency or incompatible library version | Check all runtime dependencies |

## 11. Best Practices for Packaging Executable JARs

- Use the fully qualified class name with exact casing in `Main-Class`.
- Ensure the entry point's class file is included in the JAR.
- Prefer `jar --main-class` when you only need to declare the main class.
- Use a manual manifest when you need to add `Class-Path` or custom metadata.
- Verify the manifest and file list before releasing.
- Test using the exact `java -jar` command in the target deployment environment.
- Keep external dependencies in their expected locations if the manifest references relative paths.
- Use Maven or Gradle to configure the manifest in automated builds for reproducible artifacts.
- Distinguish between a regular executable JAR and a fat/uber JAR. A regular JAR does not automatically contain all dependencies unless they are packaged into it.
- Do not edit the manifest directly after signing a JAR; modifying the archive contents can invalidate the signature. Rebuild and re-sign the artifact according to your release process.

## 12. Key Takeaways

- The manifest is located at `META-INF/MANIFEST.MF` inside the JAR.
- `Main-Class` specifies the class that `java -jar` launches.
- Its value must be the fully qualified class name, such as `app.Main`, not `app/Main.class`.
- Use `jar --create --file app.jar --main-class app.Main -C out .` to create an executable JAR.
- Use `--manifest MANIFEST.MF` when you want to declare attributes manually.
- `Class-Path` in the manifest references external JAR dependencies using appropriate relative or absolute URLs.
- `java -jar` uses the manifest as the source for the entry point and application classpath; the `-cp` option does not add to the classpath in this mode.
- Always verify the manifest and test running the JAR with the Java launcher before releasing.

By understanding the `Main-Class` attribute, you can package Java applications into JARs with a clear entry point, pass program arguments, manage external dependencies, and diagnose common deployment errors.