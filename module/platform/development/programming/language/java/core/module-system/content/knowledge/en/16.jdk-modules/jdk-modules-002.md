# Standard JDK Modules: java.logging, java.sql, and Commonly Used Modules

## 1. What Are Java's Standard Modules?

Since Java 9, the Java Platform Module System (JPMS) organizes many Java platform APIs into **named modules**. Each module declares the packages it provides, the modules it needs to read, and the packages that are exported or opened. Platform modules reside in the **runtime image** of the JDK/JRE in use.

When learning Java Core, it is useful to distinguish three groups:

- **Standard Java SE modules**, usually named **java.***: for example **java.base**, **java.logging**, **java.sql**, **java.xml**, **java.desktop**, **java.net.http**. They contain APIs belonging to the Java SE platform corresponding to the Java version in use.
- **JDK-specific modules**, usually named **jdk.***: for example **jdk.jfr**, **jdk.management**, **jdk.compiler**, **jdk.httpserver**. They provide tools and APIs of the JDK distribution and should not all be assumed to be Java SE APIs.
- **Application or third-party library modules**: for example **com.example.app** and a JDBC driver distributed by a database vendor.

An application module is described by **module-info.java**. In code belonging to a **named module**, to use public APIs exported by another module, you generally must declare the corresponding **requires**. **java.base** is a special exception: every module reads java.base without declaring it.

Example:

~~~java
module com.example.app {
    requires java.logging;
    requires java.sql;
    requires java.xml;
    requires java.net.http;
}
~~~

The declarations above form **module-level** dependencies. They do not load every class of those modules into memory immediately. When the program references a specific class, class loading still occurs on demand.

## 2. Quick Reference Table of Common Java SE Modules

| Module | Typical APIs/packages | Primary purpose | Practical notes |
|---|---|---|---|
| **java.base** | java.lang, java.util, java.io, java.nio, java.time, java.util.concurrent | Language foundation, collections, I/O, time, concurrency | Implicitly required by every module |
| **java.logging** | java.util.logging | Logging via JUL | Uses Logger, Level, Handler, Formatter |
| **java.sql** | java.sql, javax.sql | JDBC API, relational database access | API only; requires an appropriate JDBC driver to connect |
| **java.sql.rowset** | javax.sql.rowset | RowSet types, convenient JDBC support | Used when RowSet APIs are needed |
| **java.xml** | javax.xml.parsers, org.w3c.dom, org.xml.sax, javax.xml.transform | Parse, create, and process XML | DOM, SAX, Transformer, and related XML APIs |
| **java.xml.crypto** | javax.xml.crypto | XML Digital Signature | Not synonymous with all cryptographic APIs in Java |
| **java.net.http** | java.net.http | Modern HTTP Client | Stable API since Java 11 |
| **java.desktop** | java.awt, javax.swing, javax.imageio, java.beans | AWT/Swing GUI, images, desktop APIs | Not every server application needs this |
| **java.management** | java.lang.management, javax.management | JVM monitoring, JMX, MXBeans | Useful for administration and observability |
| **java.naming** | javax.naming | JNDI and lookup/naming services | Needed when integrating systems that use JNDI |
| **java.prefs** | java.util.prefs | Storing preferences/settings via Preferences | Different from framework configuration systems |
| **java.scripting** | javax.script | ScriptEngine API | Having the API does not mean the runtime ships a JavaScript engine |
| **java.compiler** | javax.tools, javax.lang.model | Compiler API and language model | Not synonymous with the javac implementation module |
| **java.instrument** | java.lang.instrument | Java agents and instrumentation | Commonly used with -javaagent |
| **java.rmi** | java.rmi | Remote Method Invocation | Suitable when using RMI |
| **java.security.jgss** | org.ietf.jgss, javax.security.auth.kerberos | GSS-API, Kerberos | Related authentication protocols and mechanisms |
| **java.transaction.xa** | javax.transaction.xa | XA interfaces for distributed transactions | XA API only; does not provide a full transaction manager |
| **java.se** | Not a module containing all packages directly | Aggregate module for the Java SE API set | Uses requires transitive relationships to group SE modules |

Module names and presence must be evaluated against the actual **Java version and runtime image**. An image created with **jlink** may contain only selected modules. Do not assume every runtime includes every module based solely on the module list of a full JDK.

## 3. java.logging: Built-in Logging API

The **java.logging** module provides **java.util.logging** (JUL). This is the logging API bundled with the Java platform, requiring no external dependencies for basic logging.

Declaration:

~~~java
module com.example.app {
    requires java.logging;
}
~~~

Example:

~~~java
package com.example.app;

import java.util.logging.Level;
import java.util.logging.Logger;

public class LoggingExample {
    private static final Logger LOG =
            Logger.getLogger(LoggingExample.class.getName());

    public static void main(String[] args) {
        LOG.info("Application starting");
        LOG.log(Level.WARNING, "Invalid value: {0}", -1);

        try {
            Integer.parseInt("abc");
        } catch (NumberFormatException ex) {
            LOG.log(Level.SEVERE, "Failed to parse number", ex);
        }
    }
}
~~~

Key components:

- **Logger**: the logger name and source where log records are emitted.
- **Level**: severity levels such as SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST.
- **Handler**: destination receiving log records, such as ConsoleHandler or FileHandler.
- **Formatter**: rules for formatting messages.
- **LogManager**: manages JUL system configuration.
- **Filter**: allows filtering LogRecord entries by condition.

You can pass a JUL configuration file path via a system property:

~~~sh
java -Djava.util.logging.config.file=logging.properties --module-path mods -m com.example.app/com.example.app.LoggingExample
~~~

Example **logging.properties** content:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
~~~

**Note:** JUL is one built-in logging option. SLF4J is a third-party logging facade, while Logback and Log4j 2 are separate solutions with their own dependencies. You cannot replace **requires java.logging** with a framework's module name if the application still imports **java.util.logging**.

In large applications, multiple logging backends may coexist. When analyzing logs, identify clearly whether code uses JUL directly or through a bridge/adaptor.

## 4. java.sql: JDBC API, Not a Database Driver

The **java.sql** module contains Java Database Connectivity (JDBC): interfaces and classes that help Java work with relational databases. Commonly used APIs:

- **Connection**: a connection session with the database.
- **DriverManager**: manages and selects a JDBC driver matching the URL.
- **DataSource** (in **javax.sql**): the preferred way to obtain connections in applications using connection pools.
- **PreparedStatement**: sends parameterized SQL; suitable for passing input values.
- **ResultSet**: iterates over query results.
- **SQLException**: JDBC error details.
- **DatabaseMetaData** and **ResultSetMetaData**: metadata about the database and result set.

Declaration:

~~~java
module com.example.app {
    requires java.sql;
}
~~~

JDBC example with a URL, username, and password supplied from application configuration:

~~~java
package com.example.app;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class JdbcExample {
    public static void printCustomerName(
            String url, String username, String password, long customerId)
            throws SQLException {

        String sql = "SELECT name FROM customers WHERE id = ?";

        try (Connection conn = DriverManager.getConnection(
                    url, username, password);
             PreparedStatement ps = conn.prepareStatement(sql)) {

            ps.setLong(1, customerId);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    System.out.println(rs.getString("name"));
                }
            }
        }
    }
}
~~~

In this example, **try-with-resources** closes ResultSet, PreparedStatement, and Connection upon exiting scope. The **?** placeholder in PreparedStatement represents a parameter value; this approach is safer than concatenating user data into SQL strings.

**Conditions for a successful connection:** besides java.sql, the runtime needs the **JDBC driver for the corresponding database** (PostgreSQL, MySQL, MariaDB, SQL Server, etc.) on the class path or module path depending on deployment. Drivers can be discovered through the service provider mechanism. Class loader and module configurations can affect driver discovery. **java.sql does not bundle all database drivers.**

When an error like **No suitable driver** occurs, inspect the JDBC URL, driver dependency, packaging, and how the runtime discovers providers. This error does not by itself prove that **java.sql** is missing.

### How Do java.sql and java.sql.rowset Differ?

**java.sql** is the core JDBC API. **java.sql.rowset** adds RowSet APIs such as **JdbcRowSet**, **CachedRowSet**, and RowSet providers. If using **javax.sql.rowset.RowSetProvider** in a named module, you must declare a dependency on **java.sql.rowset**.

~~~java
module com.example.app {
    requires java.sql;
    requires java.sql.rowset;
}
~~~

## 5. java.xml: Processing XML with Java SE APIs

The **java.xml** module supports parsing, transforming, and working with XML. Common approaches:

- **DOM**: loads the XML tree into Document, Element, and Node objects.
- **SAX**: reads XML via events, suitable for large documents.
- **StAX**: processes XML using a streaming pull model.
- **Transformer**: transforms or outputs XML.

Example parsing XML from a safe, self-provided string:

~~~java
package com.example.app;

import java.io.StringReader;
import javax.xml.parsers.DocumentBuilderFactory;
import org.xml.sax.InputSource;

public class XmlExample {
    public static void main(String[] args) throws Exception {
        String xml = "<book><title>Java Modules</title></book>";

        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newInstance();
        var builder = factory.newDocumentBuilder();
        var document = builder.parse(
                new InputSource(new StringReader(xml)));

        System.out.println(
                document.getDocumentElement()
                        .getElementsByTagName("title")
                        .item(0)
                        .getTextContent());
    }
}
~~~

For external XML, configure the XML parser appropriately to restrict external entity processing (XXE) and unwanted resource usage. The example above uses a fixed XML string solely to illustrate the API.

Declaration in **module-info.java**:

~~~java
module com.example.app {
    requires java.xml;
}
~~~

Do not confuse **java.xml** (XML parser/transform APIs) with **java.xml.crypto** (XML Digital Signature API).

## 6. java.net.http: HTTP Client in Modern JDKs

Since Java 11, the **java.net.http** module provides **HttpClient**, **HttpRequest**, and **HttpResponse** for sending synchronous or asynchronous HTTP/HTTPS requests.

~~~java
module com.example.app {
    requires java.net.http;
}
~~~

Example demonstrating how to construct a request (without actually sending it):

~~~java
package com.example.app;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;

public class HttpExample {
    public static void main(String[] args) {
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/api/items"))
                .GET()
                .build();

        System.out.println(request.method());
        System.out.println(client.version());
    }
}
~~~

If actually sending a synchronous request:

~~~java
// Performs an actual network connection when run:
var response = client.send(
        request, java.net.http.HttpResponse.BodyHandlers.ofString());
System.out.println(response.statusCode());
~~~

The second snippet is an additional illustration in the same context using the **client** and **request** variables above; it can throw **IOException** or **InterruptedException**, and should be placed in a method that handles both exception types.

Do not confuse the **java.net.http** module with **java.net**: the **java.net** package belongs to **java.base** and contains foundational APIs such as URI, URL, and Socket. To import **java.net.http.HttpClient**, a named module still needs **requires java.net.http**.

## 7. java.desktop, java.management, and Other Supporting Modules

### java.desktop

The **java.desktop** module contains AWT, Swing, Java 2D, Image I/O, and related desktop APIs:

~~~java
module com.example.viewer {
    requires java.desktop;
}
~~~

Examples include importing **javax.swing.JFrame**, **java.awt.Graphics2D**, or **javax.imageio.ImageIO**. Headless/server environments may not support creating windows; **having the module present** does not mean the environment has a graphical interface.

### java.management

The **java.management** module provides JVM monitoring and JMX APIs:

~~~java
module com.example.monitor {
    requires java.management;
}
~~~

Example:

~~~java
import java.lang.management.ManagementFactory;

long used = ManagementFactory.getMemoryMXBean()
        .getHeapMemoryUsage()
        .getUsed();

System.out.println("Heap used (bytes): " + used);
~~~

The value is the heap usage reported at the time of measurement. For remote JMX, also check the JVM process configuration and security settings.

### java.naming

The **java.naming** module contains JNDI, used when code depends on **javax.naming** APIs to look up resources or services.

### java.compiler and Related JDK Modules

**java.compiler** provides standard APIs such as **javax.tools.JavaCompiler** and **javax.lang.model**. A full JDK also includes the separate **jdk.compiler** module providing the javac compiler implementation. **Having the compiler API** is not synonymous with **having the javac tool or a compiler provider** in every runtime image.

### java.scripting

**java.scripting** defines **javax.script.ScriptEngineManager** and script engine interfaces. The presence of the API does not guarantee a specific engine is installed. For example, some modern JDKs no longer bundle Nashorn the way older JDK releases did.

### java.prefs, java.rmi, java.instrument

**java.prefs** provides **Preferences**; **java.rmi** supports Remote Method Invocation; **java.instrument** provides the **Instrumentation** API for agents. Only declare requires for APIs your module directly uses; avoid adding numerous modules to the descriptor without need.

## 8. Modular Application Example Using Multiple Standard Modules

We create an application named **demo.jdkmodules** to demonstrate how a named module uses logging, JDBC metadata, the HTTP Client, and the XML parser. The program does not perform network or database connections.

Structure:

~~~text
src/
  demo.jdkmodules/
    module-info.java
    demo/jdkmodules/Main.java
~~~

**src/demo.jdkmodules/module-info.java**:

~~~java
module demo.jdkmodules {
    requires java.logging;
    requires java.sql;
    requires java.net.http;
    requires java.xml;
}
~~~

**src/demo.jdkmodules/demo/jdkmodules/Main.java**:

~~~java
package demo.jdkmodules;

import java.net.http.HttpClient;
import java.sql.DriverManager;
import java.util.logging.Logger;
import javax.xml.parsers.DocumentBuilderFactory;

public class Main {
    private static final Logger LOG =
            Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        LOG.info("Checking standard module APIs");

        System.out.println("Preferred HTTP version: " +
                HttpClient.newHttpClient().version());

        System.out.println("JDBC driver available: " +
                DriverManager.getDrivers().hasMoreElements());

        System.out.println("XML parser factory: " +
                DocumentBuilderFactory.newInstance()
                        .getClass().getName());

        System.out.println("java.sql in boot layer: " +
                ModuleLayer.boot().findModule("java.sql").isPresent());
    }
}
~~~

Compile from the directory containing **src** using JDK 11 or later:

~~~sh
javac --module-source-path src -d mods -m demo.jdkmodules
~~~

Run the application:

~~~sh
java --module-path mods -m demo.jdkmodules/demo.jdkmodules.Main
~~~

The output consists of logging messages and four lines from System.out. The value of **JDBC driver available** depends on drivers available in the environment; the preferred HTTP version and XML parser name may also vary by JDK and provider configuration. **java.sql in boot layer** is expected to be **true** because module demo.jdkmodules declares requires java.sql.

Typical compilation error when forgetting to declare **requires**:

~~~text
package java.sql is not visible
(package java.sql is declared in module java.sql,
 but module demo.jdkmodules does not read it)
~~~

The exact message may vary slightly by JDK. To fix it, add **requires java.sql;** to **module-info.java**, ensure the environment provides the appropriate module, and recompile. Importing a Java package in source code cannot replace a module-level dependency declaration.

## 9. Commands for Inspecting JDK Modules

### Listing Modules in the Current Runtime

~~~sh
java --list-modules
~~~

The output contains module names and versions, for example:

~~~text
java.base@<version>
java.logging@<version>
java.sql@<version>
java.xml@<version>
~~~

**<version>** above is merely an illustrative placeholder; actual output depends on the Java release. The list from **--list-modules** reflects the observable modules in the runtime used to execute the command, and does not prove every module listed is resolved into the boot layer of any given application.

### Viewing a Module's Descriptor

~~~sh
java --describe-module java.logging
java --describe-module java.sql
java --describe-module java.net.http
~~~

This command displays details such as **exports**, **requires**, **uses**, and **provides** depending on the module. It is how you check which module provides a package and which dependency relationships it declares on an actual JDK.

### Observing an Application's Module Resolution

~~~sh
java --show-module-resolution --module-path mods -m demo.jdkmodules/demo.jdkmodules.Main
~~~

**--show-module-resolution** is useful for seeing root modules and resolved dependencies. Distinguish this from **--list-modules**: the list of observable modules is not the same as the graph of the running program.

### Finding Library Module Dependencies with jdeps

After compiling a JAR, you can analyze static dependencies using the **jdeps** tool:

~~~sh
jdeps --print-module-deps path/to/library.jar
~~~

The output suggests the set of JDK modules detected from static dependencies. This analysis has limitations with reflection, dynamic class loading, ServiceLoader, and environment configuration. Do not treat jdeps output as an exhaustive list of every module that may be needed at runtime.

## 10. Relationships Between requires, exports, opens, and Runtime Images

Four commonly confused concepts:

**requires X**: the current module requires reading module X. For example, **requires java.sql;** lets a named module read java.sql and use appropriately exported public APIs.

**exports p**: the module declares package p usable by other modules under standard Java access. If a package is not exported, having a module dependency is not enough to import its classes from another module.

**opens p**: allows deep reflective access under JPMS rules, useful for certain frameworks. **opens** does not mean the package is also exported for normal compile-time access.

**jlink runtime image**: an application can be packaged with a selected set of modules. If the program needs **java.sql** and the image does not contain that module, it will not be able to resolve dependencies as on a full JDK. Check the actual runtime with **java --list-modules** and review how the image was built.

A module can **requires transitive** another module. This propagates readability of the dependent module to modules that read the current module under JPMS rules. When designing **module-info.java**, declare direct and transitive dependencies according to the APIs actually exposed, rather than adding **requires transitive** to every dependency.

**java.se** is an aggregator module: it declares transitive dependencies to represent the relevant Java SE module set. For typical applications, declaring specific dependencies like **requires java.sql;** or **requires java.logging;** usually makes the dependency graph express actual needs more clearly.

## 11. Common Misconceptions and How to Handle Them

| Misconception | Reality | How to handle it |
|---|---|---|
| "All Java APIs belong to java.base" | java.base is the minimal foundation; many APIs live in separate modules | Look up the package and verify which module contains the API |
| "Importing java.sql is enough" | Named modules also need readability via requires or appropriate transitive relationships | Declare requires java.sql |
| "Having java.sql lets you connect to any DB" | A matching JDBC driver and configuration are required | Check driver, URL, and module/class path |
| "Having java.scripting means a JavaScript engine is available" | The scripting API and engine providers are separate components | Check the available ScriptEngineFactory implementations |
| "Having java.desktop lets a server render a GUI" | Headless environments may restrict GUI APIs | Verify graphical environment and actual needs |
| "A module in --list-modules is already resolved" | Observable modules differ from resolved modules | Inspect the boot layer or --show-module-resolution |
| "All jdk.* modules are Java SE APIs" | jdk.* modules are typically tied to JDK tools and implementations | Distinguish Java SE modules from JDK-specific modules |
| "java.net.http has existed since Java 9" | The stabilized HttpClient API named java.net.http is from Java 11 | Choose a JDK matching your source/module requirements |
| "jlink always packages the full JDK" | A runtime image may contain only a selected set of modules | Inspect the modules included in the image |
| "requires loads every class into RAM" | Module resolution is not eager-loading of all classes | Distinguish descriptor, graph, and class loading |

## 12. Choosing Modules by Functionality

If your application needs **simple logging**, start with **java.logging**. If it needs **JDBC**, use **java.sql** and add the appropriate driver; if using RowSet, consider **java.sql.rowset**. If it needs **XML DOM/SAX/transform**, use **java.xml**. If it needs the standard **HTTP Client** from Java 11, use **java.net.http**. If it needs **JMX/JVM monitoring**, use **java.management**; if building an **AWT/Swing GUI**, use **java.desktop**.

In a named module, declare **requires** for the modules containing the APIs you use, verify with **java --describe-module**, and compile with the target JDK. When running on a minimal runtime image, confirm those modules are actually present. For third-party libraries and JDBC drivers, also check descriptors, Automatic-Module-Name, or how the library is packaged on the module/class path.

**Key takeaway:** Standard modules provide Java API groups organized by capability. **java.logging** handles logging; **java.sql** provides JDBC; modules such as **java.xml**, **java.net.http**, **java.management**, and **java.desktop** extend specific capabilities. Understanding module boundaries properly helps you write accurate **module-info.java** files, reduce unnecessary dependencies, and diagnose resolution or class loading errors more effectively.
