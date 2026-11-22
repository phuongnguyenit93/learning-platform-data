# PATH During JDK Installation

## 1. What Is PATH and Why Configure It?

PATH is an environment variable containing a list of directories that the operating system or shell uses to locate executable programs when a user enters a command name. When you type a command such as **java** or **javac**, the terminal needs to determine where the corresponding program file is located. If the directory containing the program is not in PATH, the command may report that it was not found even though the JDK is already installed.

In the JDK, command-line tools are typically located in the **bin** directory:

- **java**: launches Java applications.
- **javac**: compiles Java source code into bytecode.
- **jar**: creates and manipulates JAR files.
- **javadoc**: generates API documentation from source code.
- **jshell**: interactively evaluates Java expressions and code snippets.

For example, if the JDK is installed at **C:\Program Files\Java\jdk-17**, the directory to add to PATH is **C:\Program Files\Java\jdk-17\bin**. The actual path depends on the vendor, version, and installation location; use the JDK directory present on your machine instead of copying the example verbatim.

PATH stores directories, not paths to individual **java.exe** or **javac.exe** files. Therefore, add the JDK's **bin** directory.

## 2. Distinguishing PATH and JAVA_HOME

These two variables are often configured together, but they serve different purposes:

- **JAVA_HOME** points to the root directory of the JDK.
- **PATH** contains the JDK's **bin** directory so Java commands can be invoked from a terminal in any working directory.

Example on Windows:

~~~text
JAVA_HOME = C:\Program Files\Java\jdk-17
PATH      = ...;%JAVA_HOME%\bin;...
~~~

Example on Linux or macOS:

~~~bash
export JAVA_HOME=/path/to/jdk-17
export PATH="$JAVA_HOME/bin:$PATH"
~~~

JAVA_HOME must point to the JDK root directory, without appending **\bin** at the end. Build tools and IDEs typically read JAVA_HOME to determine which JDK to use. The **java** command itself is located through PATH; setting JAVA_HOME does not automatically make Java commands runnable if PATH does not yet contain the **bin** directory.

For Java development, point JAVA_HOME to a full JDK. A runtime-only directory can run programs, but it does not provide the **javac** compiler.

## 3. How Is PATH Searched?

When a shell needs to run an external program, it searches for the program name across the directories in PATH in order. Typically, the directory that appears first takes precedence if multiple programs share the same name.

The separator between directories depends on the operating system:

| Operating System | Separator | Example |
|---|---|---|
| Windows | Semicolon **;** | **C:\Java\jdk-17\bin;C:\Windows\System32** |
| Linux and macOS | Colon **:** | **/opt/jdk-17/bin:/usr/bin:/bin** |

If a machine has multiple JDKs, the order in PATH determines which version is invoked when typing **java** or **javac**. For example, if JDK 17 appears before JDK 21, commands may use JDK 17 even though JDK 21 is also installed.

Check both **java** and **javac**. Both commands should come from the same JDK installation. If the runtime belongs to one version while the compiler belongs to another, compiling and running can produce unpredictable or incompatible results.

## 4. Configuring PATH on Windows 10/11

### Step 1: Locate the JDK Directory

Find the installed JDK directory. Some common locations include:

~~~text
C:\Program Files\Java\jdk-17
C:\Program Files\Eclipse Adoptium\jdk-17.0.x
C:\Program Files\Microsoft\jdk-17.x
~~~

The directory name varies by vendor and update release. Verify in File Explorer that the directory contains a **bin** subdirectory with both **java.exe** and **javac.exe** inside.

### Step 2: Open the Environment Variables Window

1. Open **Settings** → **System** → **About**.
2. Select **Advanced system settings**.
3. In the **System Properties** window, select **Environment Variables**.

You can also search from the Start menu for **Edit the system environment variables**, then select **Environment Variables**.

### Step 3: Create JAVA_HOME

In the **User variables** section (variables for the current account), select **New**:

- Variable name: **JAVA_HOME**
- Variable value: path to the JDK root directory, for example **C:\Program Files\Java\jdk-17**

Do not append **\bin** to the JAVA_HOME value, and do not wrap the path in quotation marks in the value field.

If you need to configure this for all accounts on the machine, you can set the variable under **System variables**; this operation may require administrator privileges. For personal machines, User variables are usually sufficient.

### Step 4: Add the JDK to PATH

In the same Environment Variables area:

1. Select the **Path** variable and click **Edit**.
2. Click **New** and add **%JAVA_HOME%\bin**.
3. Move this entry above older Java entries if you want this JDK to be selected as the default.
4. Click **OK** to close and save all windows.

Only add a new entry to the Path list. Do not delete the entire existing Path value, because Windows and other applications rely on the previously configured directories. Paths containing spaces still work in the Path list; do not add quotation marks around the new entry.

### Temporary Configuration in PowerShell

If you only want to test in the current PowerShell window, you can set the variables for that process:

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-17'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version
javac -version
~~~

Replace the example path with your actual JDK directory. This change takes effect in the current PowerShell window and child processes launched from it. Closing the window ends this temporary configuration.

### Temporary Configuration in Command Prompt

~~~bat
set "JAVA_HOME=C:\Program Files\Java\jdk-17"
set "PATH=%JAVA_HOME%\bin;%PATH%"
java -version
javac -version
~~~

The **set** commands above only modify the environment of the current Command Prompt window. For permanent configuration, use the Environment Variables window. Avoid manually rebuilding the entire PATH using **setx PATH ...** unless you clearly understand how the command handles existing values and variable references; an incorrect command can wipe out essential PATH entries.

After saving changes through the Windows UI, open a new terminal window. Terminals that were already open usually retain a copy of the old environment.

## 5. Configuring PATH on Linux

First, identify the actual JDK directory. If **javac** is already runnable, the following command reveals the real path of the compiler on many Linux distributions:

~~~bash
readlink -f "$(command -v javac)"
~~~

An example output might be:

~~~text
/usr/lib/jvm/jdk-17/bin/javac
~~~

In this example, the JDK root directory is **/usr/lib/jvm/jdk-17** — the parent directory of **bin**. The path on your machine may differ if the JDK was installed via a package manager or placed in a custom location.

Open the configuration file for your shell. For interactive Bash, this is usually **~/.bashrc**; for interactive Zsh, it is usually **~/.zshrc**. Some login environments read **~/.profile**; choose the file that matches how your terminal launches the shell to avoid duplicate declarations.

Add the following two lines, replacing the sample path with the JDK directory on your machine:

~~~bash
export JAVA_HOME="/usr/lib/jvm/jdk-17"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Save the file, then reload the configuration. For example, with Bash:

~~~bash
source ~/.bashrc
~~~

Or with Zsh:

~~~bash
source ~/.zshrc
~~~

You can also close and open a new terminal to pick up the updated environment. Placing **$JAVA_HOME/bin** at the beginning of PATH ensures the chosen JDK takes precedence over other Java commands on the system.

## 6. Configuring PATH on macOS

macOS provides the **/usr/libexec/java_home** utility to locate installed JDKs. List the recognized JDK installations:

~~~bash
/usr/libexec/java_home -V
~~~

To select JDK 17, you can use:

~~~bash
export JAVA_HOME=$(/usr/libexec/java_home -v 17)
export PATH="$JAVA_HOME/bin:$PATH"
~~~

The commands above set JAVA_HOME to the JDK 17 installed on the machine and prepend its **bin** directory to PATH. If you are using a different version, replace **17** with the desired installed version.

For persistent configuration, modern macOS typically uses Zsh as the default shell. Add the two configuration lines to **~/.zshrc**:

~~~bash
export JAVA_HOME=$(/usr/libexec/java_home -v 17)
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Then reload it:

~~~bash
source ~/.zshrc
~~~

If you are using Bash, place the configuration in the startup file your shell actually reads, usually **~/.bash_profile** or **~/.bashrc**. You can use **/usr/libexec/java_home -V** to inspect the JDK versions recognized by macOS.

## 7. Verifying the Configuration

After configuring, open a new terminal and check JAVA_HOME, the resolved program locations, and the actual versions.

### Windows PowerShell

~~~powershell
$env:JAVA_HOME
Get-Command java -All
Get-Command javac -All
where.exe java
where.exe javac
java -version
javac -version
~~~

**where.exe** lists the files that can be found via PATH. The first line is typically the entry that takes precedence when invoking an external command with that name. **Get-Command -All** also helps identify aliases or other commands that may affect command resolution in PowerShell.

### Windows Command Prompt

~~~bat
echo %JAVA_HOME%
where java
where javac
java -version
javac -version
~~~

### Linux and macOS

~~~bash
printf '%s\n' "$JAVA_HOME"
command -v java
command -v javac
type -a java javac
java -version
javac -version
~~~

A proper configuration typically meets the following conditions:

- JAVA_HOME points to the root directory of the chosen JDK.
- The resolved paths for **java** and **javac** belong to the same JDK.
- **java -version** and **javac -version** display the expected version.
- No older JDK or other Java path precedes the chosen JDK in PATH.

Note: **java -version** reports the running runtime; **javac -version** confirms that the JDK compiler can be invoked. Checking only one of the two commands is not enough to catch all cases where PATH mixes multiple versions.

## 8. Testing Compilation and Execution of a Java Program

Create a file named **Hello.java** with the following content:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
~~~

Open a terminal in the directory containing the file and run:

~~~bash
javac Hello.java
java Hello
~~~

Expected output:

~~~text
Hello, Java!
~~~

This example tests two parts of the JDK through PATH: the **javac** command must locate the compiler to produce **Hello.class**, and then the **java** command must locate the runtime to execute the **Hello** class. If both commands succeed and produce the output above, the basic configuration is working.

PATH only helps locate executable programs. It does not automatically locate source files in arbitrary directories. When running the example, the terminal still needs to be in the directory containing **Hello.java**, or you must provide the appropriate path to the file.

## 9. Common Errors and Troubleshooting

### “java is not recognized” or “command not found” Error

Common causes:

- The JDK's **bin** directory has not been added to PATH.
- The path was mistyped or points to a nonexistent directory.
- PATH was updated, but you are still using a terminal opened beforehand.
- JAVA_HOME was set, but JAVA_HOME/bin was not added to PATH.

How to fix: verify that the JDK directory contains **java**, check the PATH entry, save changes, and open a new terminal. On Windows, you can use **where.exe java**; on Linux/macOS, you can use **command -v java**.

### The java Command Works, but javac Is Not Found

PATH may be pointing to a runtime-only installation or a Java directory that does not include the compiler. Verify that a full JDK is installed and that the PATH entry points to that JDK's **bin** directory. Then verify again with **javac -version**.

### Unexpected Java Version

The machine may have multiple JDKs or an older Java path preceding the new path. Use **where.exe java** and **where.exe javac** on Windows, or **type -a java javac** on Linux/macOS to see all discovered locations. Move the **bin** directory of the desired JDK higher in priority, remove old entries only when you are sure they are no longer needed, then open a new terminal and verify again.

### JAVA_HOME Points to the Wrong Location

JAVA_HOME must point to the JDK root directory. For example, the value should end at **jdk-17**, not **jdk-17\bin**. PATH then references **%JAVA_HOME%\bin** on Windows or **$JAVA_HOME/bin** on Linux/macOS.

### Using the Wrong Separator

On Windows, directories in PATH are separated by semicolons. On Linux and macOS, they are separated by colons. Using the wrong separator can cause the entire string to be interpreted as a single invalid path entry.

### Accidentally Overwriting PATH

Do not replace the entire PATH with only the JDK directory. PATH also contains system directories and other tools. When configuring it, only append or prepend the JDK entry to the existing list and preserve the required entries.

## 10. Completion Checklist

- [ ] A full JDK is installed, not just a runtime.
- [ ] JAVA_HOME points to the root directory of the JDK.
- [ ] PATH contains the JDK's **bin** directory.
- [ ] The correct separator for the operating system is used.
- [ ] A new terminal was opened after modifying environment variables.
- [ ] **java -version** and **javac -version** display the expected version.
- [ ] A Java program was compiled and run successfully.
