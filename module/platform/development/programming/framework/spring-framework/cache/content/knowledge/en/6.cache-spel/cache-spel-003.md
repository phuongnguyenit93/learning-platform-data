# Parameter Name Information and the `-parameters` Compiler Option in Spring Cache SpEL

## 1. The Problem: Why Does `#isbn` Work on One Machine Yet Fail on Another?

When declaring caching with the Spring Framework, we often select the cache key using **Spring Expression Language (SpEL)**:

~~~java
@Cacheable(cacheNames = "books", key = "#isbn")
public Book findByIsbn(String isbn) {
    return repository.findByIsbn(isbn).orElseThrow();
}
~~~

This is **illustrative code for integration in a Spring application**; `Book` and `repository` are domain components, not a standalone runnable program. The `#isbn` expression requires Spring to know that the method's first argument is named `isbn`. If the bytecode does not retain parameter names in a form readable by Java reflection, Spring may fail to bind the name `isbn` in the SpEL context. The expression then fails to produce the expected cache key, and the cached call may fail.

This issue is distinct from whether a Java method actually receives arguments. The JVM always knows the **values and positions** of arguments to invoke a method. However, source names such as `isbn` or `edition` are not required to be stored in `.class` file metadata. **`javac -parameters`** instructs the compiler to preserve that information so reflection and Spring can use it.

Lesson goals: understand the parameter-name mechanism, verify the effect of `-parameters`, use `#name`/`#p0`/`#a0`/`#root.args[0]` properly in Spring Cache SpEL, configure builds, and troubleshoot discrepancies between deployment and development environments.

## 2. How Parameter Names Travel from Java Source to SpEL

Consider the signature:

~~~java
public Book find(String isbn, int edition) {
    // Load book by ISBN and edition...
}
~~~

Two kinds of information must be distinguished:

1. **Argument position, type, and value:** the first argument is `String`, the second argument is `int`; the JVM still passes both values correctly even without `-parameters`.
2. **Programmer-declared names:** `isbn` and `edition`. To access them via Java reflection, the compiler must store parameter-name metadata (the `MethodParameters` attribute in bytecode).

Spring uses a parameter-name discovery mechanism (such as `StandardReflectionParameterNameDiscoverer` for Java) when building the SpEL evaluation context. Conceptual flow:

~~~text
Java source: find(String isbn, int edition)
              |
              | javac -parameters
              v
.class: MethodParameters = isbn, edition
              |
              | Java reflection / Spring parameter-name discovery
              v
Spring Cache SpEL context:
    #isbn    = first argument
    #edition = second argument
    #p0      = first argument (by index)
    #p1      = second argument (by index)
              |
              v
@Cacheable(key = "...") → cache key
~~~

If compilation does not retain names, values can still be referenced by **position** in Spring Cache SpEL. This is the most important practical point when building lessons or reusable libraries.

### Ways to Refer to Arguments in Cache SpEL

| SpEL Syntax | Accesses | Requires `-parameters`? | When to Use |
|---|---|---|---|
| `#isbn` | Argument with Java name `isbn` | **Normally yes** with Java code and modern Spring | Expressive, readable, suitable for codebases configured to retain parameter names |
| `#edition` | Argument with Java name `edition` | **Normally yes** | Conditions/keys based on the second argument by name |
| `#p0`, `#p1` | Arguments at index 0, 1 | No | Want to avoid relying on names in bytecode |
| `#a0`, `#a1` | Aliases for index 0, 1 | No | Equivalent to `#p0` and `#p1` |
| `#root.args[0]`, `#root.args[1]` | Arguments array on root object | No | Want explicit access via the root context |

**Indexing starts at 0.** For `find(String isbn, int edition)`: `#p0`, `#a0`, and `#root.args[0]` all point to the `isbn` value; `#p1` points to `edition`. `#p0` is a SpEL variable name provided by Spring; do not confuse it with the string `arg0` that Java reflection may display when metadata is missing. `#arg0` is not a fallback syntax guaranteed by Spring Cache like `#p0`.

**Scope of name usage:** this refers to arguments of the **method being intercepted by Spring Cache**, not local variables inside the method body. A local variable such as `String normalized = ...` does not automatically become `#normalized` inside the `@Cacheable` expression.

## 3. Standalone Java 17 Experiment: With and Without `-parameters`

To isolate the Java mechanism from Spring, create the following **`ParameterNamesDemo.java`** file. Only JDK 17+ is required, with no Maven/Gradle or dependencies:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterNamesDemo {
    public String load(String isbn, int edition) {
        return isbn + ":" + edition;
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Method method = ParameterNamesDemo.class
                .getDeclaredMethod("load", String.class, int.class);
        Parameter[] parameters = method.getParameters();

        for (int i = 0; i < parameters.length; i++) {
            System.out.printf("p%d: name=%s, present=%s%n",
                    i, parameters[i].getName(), parameters[i].isNamePresent());
        }
    }
}
~~~

### Run 1: Compiling without parameter-name retention

~~~bash
javac --release 17 ParameterNamesDemo.java
java ParameterNamesDemo
~~~

Stdout (with standard `javac`, without `-parameters` enabled elsewhere):

~~~text
p0: name=arg0, present=false
p1: name=arg1, present=false
~~~

`Parameter.getName()` returns synthetic names `arg0` and `arg1`; `Parameter.isNamePresent()` is `false`. These are not the two names declared in the source code.

### Run 2: Enabling debug info only

~~~bash
javac --release 17 -g ParameterNamesDemo.java
java ParameterNamesDemo
~~~

Stdout is still:

~~~text
p0: name=arg0, present=false
p1: name=arg1, present=false
~~~

`-g` generates debugging information, which may include local variable tables, but **does not replace `-parameters`** for supplying names to Java reflection.

### Run 3: Enabling parameter-name metadata

~~~bash
javac --release 17 -parameters ParameterNamesDemo.java
java ParameterNamesDemo
~~~

Stdout:

~~~text
p0: name=isbn, present=true
p1: name=edition, present=true
~~~

This time, source names are preserved for `Method.getParameters()` to read. The third command recompiles the same `.class` file; make sure you do not run an older `.class` file lingering earlier on the classpath. You can inspect the bytecode with:

~~~bash
javap -v ParameterNamesDemo
~~~

In the `load` method section of the `-parameters` build, look for the **`MethodParameters`** attribute with names `isbn`, `edition`. If you see a `LocalVariableTable` section generated by `-g`, understand that it is **different metadata**. All three cases above were verified against a Java 17 target; the difference lies in metadata, not in the return value of `load`.

## 4. Why Does Spring Framework 6.1+ Require Special Attention?

In older Spring versions, the framework used to support discovering Java parameter names from `LocalVariableTable` debug information when standard metadata was absent. **Spring Framework 6.1 removed `LocalVariableTableParameterNameDiscoverer`** and no longer falls back to reading the local variable table to infer names as before. Therefore, “it previously worked with `-g`” is not proof that it still works on Spring 6.1+.

For **name-based** cache expressions such as `key = "#isbn"`, the reliable approach for Java code is to enable **`-parameters`** when building the corresponding source. Do not assume that enabling debug mode, generating source maps, using `--release 17`, or running JDK 17+ is sufficient.

This does not mean every `@Cacheable` expression requires `-parameters`. If you use the **default key generator**, `#p0`, `#a0`, or `#root.args[0]`, Spring already has the argument values by position without needing names from reflection.

## 5. Applying This to Cache Annotations

### 5.1. `@Cacheable` and Name-Based Keys

~~~java
@Cacheable(cacheNames = "books", key = "#isbn")
public Book findByIsbn(String isbn) {
    return repository.findByIsbn(isbn).orElseThrow();
}
~~~

When the method is called via cache interception, Spring evaluates `#isbn` to the `String` argument and uses it as the key to look up the value in the `books` cache. This pattern is readable, but you must ensure the runtime method has the appropriate parameter-name metadata.

Three **independent** alternative ways to write the same first-parameter lookup:

~~~java
// Each annotation below is ONE option; do not place them together.
@Cacheable(cacheNames = "books", key = "#p0")
// or:
@Cacheable(cacheNames = "books", key = "#a0")
// or:
@Cacheable(cacheNames = "books", key = "#root.args[0]")
~~~

They do not require Java name metadata. On the other hand, if you later change **argument order**, index `0` may point to a different value; you must update and retest the expression.

### 5.2. Multiple Parameters: Are Names Enough, and Is the Key Correct?

Suppose a service loads books by tenant and ISBN:

~~~java
@Cacheable(cacheNames = "tenantBooks",
           key = "#tenantId + ':' + #isbn")
public Book find(String tenantId, String isbn) {
    return repository.findForTenant(tenantId, isbn).orElseThrow();
}
~~~

Both `#tenantId` and `#isbn` require parameter names to be supplied accurately. Moreover, string concatenation expressions need an **unambiguous encoding rule**: if input values can contain `:`, two different argument pairs can produce the same key. When the cache key should include **all arguments**, it can be simpler to omit the `key` attribute entirely:

~~~java
@Cacheable(cacheNames = "tenantBooks")
public Book find(String tenantId, String isbn) {
    return repository.findForTenant(tenantId, isbn).orElseThrow();
}
~~~

By default, Spring uses a `SimpleKey` containing both arguments when a method has multiple arguments. For a method with **one** argument, the default key is that argument value itself (when compatible with the key generator contract); for **zero** arguments, the key is `SimpleKey.EMPTY`. This choice does not depend on parameter-name metadata, though you must still verify `equals()` and `hashCode()` if arguments are custom objects.

**Do not use `key = "#p0"` merely to work around missing parameter names** when the second parameter still affects the result. Otherwise, requests across different tenants, versions, languages, or filters could collide on the same key and receive wrong data.

### 5.3. `condition` and `unless` Have Different Evaluation Timings

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#isbn",
    condition = "#isbn != null && !#isbn.isBlank()",
    unless = "#result == null"
)
public Book findByIsbn(String isbn) {
    return repository.findByIsbn(isbn).orElse(null);
}
~~~

- `key` specifies an expression to compute the cache key; `condition` determines **before calling the method** whether caching applies at all.
- `unless` is evaluated **after the method actually executes**, using `#result` to veto placing the result into the cache.
- `#result` is **not available in `@Cacheable`'s `key`** or pre-invocation `condition`. It is supported in `unless`, `@CachePut` key expressions, and post-invocation `@CacheEvict` (with `beforeInvocation = false`).
- If the method returns `Optional<T>`, `#result` in cache expressions refers to the unwrapped domain value according to Spring Cache rules; it may be `null`. Use null-safe operators when accessing properties.

The example above still requires `-parameters` because `#isbn` appears in `key` and `condition`. If metadata is uncertain, switch consistently to `#p0` at **every place** referencing the argument:

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()",
    unless = "#result == null"
)
~~~

The annotation snippets in this section are **Spring integration examples** and do not compile standalone: they require `@EnableCaching`, a cache manager/provider, a service bean, and corresponding classes/repositories.

### 5.4. `@CacheEvict` and `@CachePut` Can Also Hit Name Issues

~~~java
@CacheEvict(cacheNames = "books", key = "#isbn")
public void remove(String isbn) {
    repository.deleteByIsbn(isbn);
}
~~~

After deleting data successfully, Spring needs to determine the key to evict. If the name `isbn` is not retained, the expression may fail to produce a valid key. You can switch to `key = "#p0"` if the method only has that argument; what matters is that **the eviction key must match the cache key of the read method**.

With `@CachePut`, the method always runs and the result is placed in the cache; `#result` is available in the appropriate post-invocation context, while `#p0` still references the argument by position. Having parameter names in SpEL does **not** make annotations work by themselves: Spring caching must be enabled and calls must go through the proper interception mechanism (in proxy mode, calling `this.method()` on the same bean typically bypasses the proxy).

## 6. Enabling `-parameters` in the Build Process

### 6.1. Calling `javac` Directly

~~~bash
javac --release 17 -parameters MyService.java
~~~

`--release 17` selects the Java 17 compatible API and class file version; **`-parameters`** is an independent option to retain names. The exact flag is `-parameters` (plural). When recompiling, ensure the application runs the newly compiled classes/JAR and is not shadowed by an older class earlier on the classpath.

### 6.2. Gradle with `build.gradle` (Groovy DSL)

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}
~~~

This configuration applies to `JavaCompile` tasks in the project where it is placed, typically covering both production and test sources in that project. If using multiple subprojects/modules, apply the configuration to **all modules containing cached methods**; do not assume one module's settings automatically propagate to all others.

### 6.3. Gradle with `build.gradle.kts` (Kotlin DSL)

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

The effect on `javac` is the same as the Groovy DSL. After editing the build script, **recompile the bytecode** and verify the actual packaged/deployed artifact rather than merely restarting the app with old class files.

### 6.4. Maven Compiler Plugin

In `pom.xml`, configure the Java compiler plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <parameters>true</parameters>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

The corresponding property is `maven.compiler.parameters`; in a project using a compatible Maven Compiler Plugin you can declare:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <maven.compiler.parameters>true</maven.compiler.parameters>
</properties>
~~~

Do not add a second `build` section if the POM already has one; merge the configuration into the existing POM. Also do not assume every plugin/framework version enables this flag for you; **inspecting the output bytecode** is the most direct confirmation.

## 7. Diagnosing Why a `#name` Expression Fails

A checklist you can apply to SpEL cache issues:

1. **Identify the active expression:** check `key`, `condition`, `unless` in `@Cacheable`, `@CachePut`, `@CacheEvict`. For example, `key="#isbn"` must match the method's exact argument name.
2. **Inspect compiler metadata on the running class:** use reflection `Parameter.isNamePresent()` and `getName()` as shown; or `javap -v` to check `MethodParameters`. An `arg0/false` result indicates missing name metadata.
3. **Check build commands and deployed artifacts:** confirm the flag applies to the right module/source set, clean recompile happened where needed, and the updated JAR/container is actually deployed. A dependency JAR compiled without the flag is not fixed merely by enabling the flag on the consuming project.
4. **Test the name-independent variant:** temporarily replace `#isbn` with `#p0` (only when they have the same key semantics). If that works, the issue is likely parameter-name discovery.
5. **Verify key and annotation correctness:** generating a key does not prove the cache is correct. With multiple arguments, cover every parameter that affects the result, including tenant/authorization where appropriate.
6. **Verify cache interception:** if no hits occur, confirm `@EnableCaching`, the appropriate `CacheManager`, and that invocations go through the Spring proxy. That is separate from missing parameter names.

A symptom you may see when an expression returns a `null` key is an error like **“Null key returned for cache operation”**; if an expression accesses a property/method on an unresolved object, a different SpEL evaluation error may occur. Do not rely on exact exception wording across versions. Inspecting the expression configuration and checking metadata reveals the root cause.

### Fix Decision Table

| Situation | Appropriate Action | Remaining Risk |
|---|---|---|
| Want to write `#isbn` for readability | Enable `-parameters` and recompile the method's class | Renaming the parameter while forgetting to update the expression |
| Cannot control how a third-party JAR is compiled | Consider `#p0`/`#a0`/`#root.args[0]` in code you control | Reordering parameters can produce wrong keys |
| All arguments together identify the result | Consider the default key generator | Requires proper `equals/hashCode`; non-domain parameters can fragment the cache |
| Already have `-g` but names are not found | Use `-parameters`; check `MethodParameters` | Debug info does not replace Java reflection metadata |
| Key is valid but no cache hits occur | Check proxy, `@EnableCaching`, cache manager, and actual calls | Issue may be unrelated to parameter names |
| Multi-module deployment, fails only in runtime env | Inspect the actual loaded class/JAR and module compile task | Stale artifacts or mismatched compilation settings |

## 8. Misconceptions and Design Pitfalls to Avoid

- **“Names in Java source are always in `.class`.”** False. Source code and reflection metadata have different contracts; verify that names are retained.
- **“`-g` is equivalent to `-parameters`.”** False. Spring 6.1+ no longer falls back to discovering names from `LocalVariableTable`.
- **“`-parameters` solves every Spring Cache issue.”** False. It only supplies names for one category of scenarios; cache managers, self-invocation, transactions, TTL, eviction, and key correctness remain independent concerns.
- **“Without `-parameters`, `@Cacheable` cannot be used.”** False. Default keys and positional syntax still work.
- **“`#p0` is safe across every refactor.”** False. Reordering parameters changes the meaning of an index; omitting tenant/version arguments risks cross-data leakage.
- **“`#result` is always available.”** False. In `@Cacheable`, it is used for `unless` after a result exists, not in `key` or pre-invocation `condition`.
- **“Setting the flag in the main runner project is enough.”** False in many multi-module systems. What matters is that **the class containing the intercepted method** was compiled with the appropriate metadata.
- **“Seeing `arg0` in reflection means `#arg0` works.”** Do not infer that. Use the officially supported Spring Cache aliases: `#p0`, `#a0`, or `#root.args[0]`.
- **“Renaming `isbn` to `code` has no side effects.”** With `#isbn` named expressions, refactoring source requires updating the expression and testing behavior; the compiler does not update SpEL strings inside annotations.

## 9. Self-Check

**Question 1.** The method `Book find(String isbn, int edition)` is compiled without `-parameters`. Which expressions can still access the second argument: `#edition`, `#p1`, `#a1`, `#root.args[1]`?

**Question 2.** Does `javac --release 17 -g Demo.java` enable Java reflection to retrieve the name `isbn`? If not, which flag should be added?

**Question 3.** `@Cacheable(key="#p0")` is applied to `find(String isbn, String tenantId)`. If data differs per tenant, what risk does this cache key pose?

**Question 4.** Why is `@Cacheable(key="#result.id")` not a valid key selection given the annotation's execution timing?

**Question 5.** After adding `-parameters` to Gradle, the application still does not see parameter names; what should you check before concluding Spring has a bug?

**Answers and Explanations:**

1. `#p1`, `#a1`, `#root.args[1]` access the second position; `#edition` depends on name discovery.
2. No. `-g` is for debugging; add `-parameters` and recompile the class.
3. Two tenants with the same ISBN will share the key, risking returning another tenant's data; use a key with full context or the appropriate default generator.
4. `@Cacheable`'s cache key must be known during cache lookup **before** deciding whether to run the method; `#result` only exists after the method executes in supported contexts.
5. Check the compile task of the module containing the method, the actual deployed class/JAR, `MethodParameters` in bytecode, cache proxy/configuration, and the expression being invoked.

## 10. References

- Spring Framework — Declarative Annotation-based Caching and SpEL Evaluation Context table: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework 6.1 Release Notes — Parameter Name Retention, removal of `LocalVariableTableParameterNameDiscoverer`: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.1-Release-Notes
- Oracle JDK — `javac`: definitions of `-parameters`, `-g`, and `--release`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- Gradle Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Maven Compiler Plugin — `parameters`: https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html

**Key takeaway:** In Spring Cache SpEL, `#isbn` requires Java parameter names to be recognized properly; compiling classes containing cached methods with `javac -parameters` is the reliable practice for Spring Framework 6.1+. `#p0`, `#a0`, and `#root.args[0]` use **argument positions**, independent of name metadata. Whichever approach you choose, the cache key must cover all inputs that determine the result.