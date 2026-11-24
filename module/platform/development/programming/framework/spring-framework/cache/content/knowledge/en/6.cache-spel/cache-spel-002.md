# Accessing `#p0`, `#a0`, and Parameter Names in Spring Cache SpEL

> **Topic:** Spring Framework – Cache Abstraction · **Group:** SpEL Expressions  
> **Focus:** How to reference method arguments from expression attributes such as `key`, `condition`, and `unless` on caching annotations; prerequisites for using **parameter names** reliably.

## 1. Why Access Arguments in SpEL?

A method may accept multiple parameters, yet only some parameters actually determine the result to be cached. Spring allows writing **Spring Expression Language (SpEL)** directly inside cache annotations to extract argument values as the cache key, decide whether to cache, or veto an entry.

For example:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public String findBook(String isbn) {
    return queryBook(isbn);
}
~~~

This snippet illustrates only a single method; `queryBook` must be defined in an actual application. When Spring intercepts the call `findBook("9780134685991")`, `#p0` evaluates to `"9780134685991"`. That string becomes the **entry key** in the `books` cache. When a later call produces the same key and a value already exists, Spring can return the cached result without invoking the method body again.

Be careful to distinguish:

- `cacheNames = "books"`: the **cache region** name resolved from `CacheManager`.
- `key = "#p0"`: the **SpEL expression** selecting the key inside the cache region.
- `findBook(String isbn)`: the actual arguments of the call serve as the data source for SpEL evaluation.
- `@Cacheable` requires active caching infrastructure, such as `@EnableCaching`, and the call must go through the corresponding interceptor/proxy.

## 2. Three Ways to Reference the Same Argument

Suppose a method is called as follows:

~~~java
public String findBook(String isbn, boolean includeArchived) {
    return "...";
}

// Call: findBook("BK-17", true)
~~~

Spring Cache places the arguments into a dedicated **evaluation context** for caching:

| Expression | What It Points To | Value in Example | Requirement |
| --- | --- | --- | --- |
| `#p0` | **First** argument (index 0) | `"BK-17"` | Positional, does not need parameter names retained |
| `#a0` | **First** argument (alias of `#p0`) | `"BK-17"` | Positional, does not need parameter names retained |
| `#isbn` | Argument named `isbn` in Java | `"BK-17"` | Spring must be able to discover the parameter name |
| `#p1` | **Second** argument (index 1) | `true` | Positional |
| `#a1` | **Second** argument (alias of `#p1`) | `true` | Positional |
| `#includeArchived` | Parameter named `includeArchived` | `true` | Requires parameter name metadata |
| `#root.args[0]` | First element of the arguments array | `"BK-17"` | Does not need parameter names |
| `#root.args[1]` | Second element | `true` | Does not need parameter names |

**Important rule:** indexing starts at **0**. The letter `p` stands for *parameter*, and `a` stands for *argument*; in Spring Cache SpEL, `#pN` and `#aN` are **two alias conventions for the exact same argument at position N**, not two different data sources.

For the same call, the three expressions `#p0`, `#a0`, and `#isbn` can all produce the same value. However, `#isbn` only works reliably when the runtime has sufficient parameter name information.

### Syntax: Why Is `#` Required?

In SpEL, the `#` character denotes a variable in the evaluation context. Therefore:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")   // Valid: variable p0
@Cacheable(cacheNames = "books", key = "#a0")   // Valid: alias a0
@Cacheable(cacheNames = "books", key = "#isbn") // Valid if name isbn is discovered
~~~

The annotations above are **alternative choices** for illustration, not three annotations placed simultaneously on the same method.

Do not write `key = "p0"` if you intend to use the first argument: omitting `#` causes SpEL to interpret it differently, leading to an error or an unintended key. The expression `key = "'fixed'"` returns the constant string `fixed`; the inner single quotes are SpEL's literal syntax.

## 3. How Spring Provides `#p0`, `#a0`, and Actual Names

When a caching operation executes, Spring creates an evaluation context for SpEL. The context holds metadata about the method and arguments, where:

1. The list of actual arguments is kept by **call position**.
2. Spring registers index-based aliases such as `p0`, `a0`, `p1`, `a1`, ...
3. If the method's parameter names can be determined, Spring also enables access by name such as `isbn`, `includeArchived`.
4. Key or condition evaluation reads these variables at the appropriate stage of the cache operation.

Because positional aliases do not depend on Java names, `#p0`/`#a0` are generally safer when you do not control how dependencies were compiled. Conversely, meaningful names like `#isbn` or `#customerId` make expressions easier to read and review if builds consistently retain metadata.

Other access forms are also valid:

~~~java
// The snippets below are separate annotation examples.
@Cacheable(cacheNames = "books", key = "#root.args[0]")
@Cacheable(cacheNames = "books", key = "#p0.toUpperCase()")
@Cacheable(cacheNames = "books", key = "#isbn.toUpperCase()")
~~~

The two expressions using `toUpperCase()` require the argument to be a non-`null` string. When data may be null, you must add a condition or choose an appropriate key; calling a method directly on null can cause SpEL evaluation to fail.

### What Is `#root`?

Spring Cache also provides a root object, including:

- `#root.args[0]`: argument by position, without needing Java names.
- `#root.methodName`: name of the method being invoked.
- `#root.method`: the `java.lang.reflect.Method` object.
- `#root.target`: the target object.
- `#root.targetClass`: the class of the target object.
- `#root.caches`: the caches involved in the operation.

**Do not confuse** `#root.args[0]` (the invocation's argument array) with `#root.caches[0]` (the resolved cache region). Both belong to the root object but serve different purposes.

## 4. Why Does Parameter Name `#isbn` Sometimes Fail?

In Java, seeing `findBook(String isbn)` in source code **does not guarantee** that the name `isbn` is available via reflection at runtime. The JVM always knows the *count, order, and types* of parameters in the method descriptor, but source names must be retained during compilation.

In Java, the standard way is to use the flag:

~~~bash
javac -parameters BookService.java
~~~

The command above illustrates the compiler flag; `BookService.java` still needs all corresponding dependencies/imports if it contains Spring annotations. You cannot retrieve names with this command if compiling a standalone Spring file without a classpath.

**Gradle (Groovy DSL):**

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

**Maven:**

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

The configuration snippets above show only the part enabling name retention; in a real project, ensure they reside in the proper `build.gradle` or `pom.xml` and rebuild the classes.

### Checking Whether Parameter Names Are Retained

Java reflection can verify this:

~~~java
Method method = BookService.class.getMethod("findBook", String.class);
Parameter parameter = method.getParameters()[0];

System.out.println(parameter.isNamePresent());
System.out.println(parameter.getName());
~~~

This illustrative snippet requires importing `java.lang.reflect.Method` and `java.lang.reflect.Parameter`, along with a `BookService` class having a public `findBook(String)` method. When compiled with `-parameters`, the expected output is:

~~~text
true
isbn
~~~

Without metadata retention, Java reflection typically exposes synthetic names like `arg0` and `isNamePresent()` returns `false`. **`arg0` is not the standard `#a0` alias**: do not turn a reflection-generated name into an assumption about SpEL variables.

In modern Spring Framework versions (especially Spring 6.1+), proactively compile Java with `-parameters` if you want to rely on parameter names. Do not rely on compiler debug symbols as a substitute guarantee. For Kotlin, proxies, or generated classes, parameter name discovery mechanisms may differ; verify at runtime rather than assuming.

## 5. Complete Java 17+ Example: Three Access Styles

The following example uses **Spring Framework 6.2.14** and Gradle, creating a `ConcurrentMapCacheManager` with the `books` region and calling three cached methods. One method uses `#p0`, one uses `#a0`, and one uses the name `#code`. Different key prefixes let you observe the three examples without one method's entry masking another method's result.

Create two files at the exact paths:

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

// Required for the example accessing named variable #code.
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

application {
    mainClass = 'demo.ArgumentKeyDemo'
}
~~~

**`src/main/java/demo/ArgumentKeyDemo.java`**

~~~java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ArgumentKeyDemo {

    @Configuration
    @EnableCaching
    public static class Config {

        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("books");
        }

        @Bean
        public BookService bookService() {
            return new BookService();
        }
    }

    public static class BookService {
        private int positionCalls;
        private int aliasCalls;
        private int namedCalls;

        @Cacheable(cacheNames = "books", key = "'p:' + #p0")
        public String byPosition(String code) {
            return "position-load-" + (++positionCalls);
        }

        @Cacheable(cacheNames = "books", key = "'a:' + #a0")
        public String byAlias(String code) {
            return "alias-load-" + (++aliasCalls);
        }

        @Cacheable(cacheNames = "books", key = "'name:' + #code")
        public String byName(String code) {
            return "name-load-" + (++namedCalls);
        }
    }

    public static void main(String[] args) throws Exception {
        boolean namesPresent = BookService.class
                .getMethod("byName", String.class)
                .getParameters()[0]
                .isNamePresent();
        System.out.println("parameter names: " + namesPresent);

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            // Retrieve the bean from Spring so calls go through the caching proxy.
            BookService service = context.getBean(BookService.class);

            System.out.println(service.byPosition("J17"));
            System.out.println(service.byPosition("J17"));

            System.out.println(service.byAlias("J17"));
            System.out.println(service.byAlias("J17"));

            System.out.println(service.byName("J17"));
            System.out.println(service.byName("J17"));
        }
    }
}
~~~

Run in the directory containing `build.gradle`, with JDK 17+ and a compatible Gradle version:

~~~bash
gradle run --quiet
~~~

**Expected application stdout** (excluding external environment/build logs):

~~~text
parameter names: true
position-load-1
position-load-1
alias-load-1
alias-load-1
name-load-1
name-load-1
~~~

**Analysis:**

1. `parameter names: true` confirms the `-parameters` option was applied.
2. On the first `byPosition("J17")` call, the key is `"p:J17"`; the second call with the same key returns a cache hit and `positionCalls` does not increment.
3. For `byAlias("J17")`, `#a0` points to the first argument just like `#p0`; the key is `"a:J17"` and the second call also hits.
4. For `byName("J17")`, Spring knows the name `code` and computes the key `"name:J17"`; the repeated call also hits.
5. All three methods share the `books` region, but the prefixes `p:`, `a:`, `name:` intentionally create **three different keys** for demonstration. This does **not** mean `#p0` and `#a0` produce different results; both point to argument index 0.

`@EnableCaching` enables the caching interceptor. In default proxy mode, calling a cacheable method from another method on the same object (`this.byName(...)`) can bypass the proxy and thus bypass the cache. The example calls from `main` via the Spring bean to observe the intended behavior.

## 6. Choosing Positional vs. Named Access

| Criterion | `#p0`, `#a0` | `#isbn`, `#userId` |
| --- | --- | --- |
| Readability | Requires checking the method signature to know what `0` is | Business-meaningful names, easy to review |
| Compiler metadata | Does not require source names in bytecode | Requires Spring to find the actual name |
| Renaming a parameter | Usually does not change meaning | Must update the expression if the name changes |
| Reordering parameters | Can silently switch to a different argument | Less dependent on order if names stay stable |
| Using with unowned compiled libraries | Generally more predictable | Must verify metadata at runtime |
| Recommendation | Useful for small methods, few parameters, or missing metadata | Useful for application code you control with `-parameters` always enabled |

Example:

~~~java
// Illustrative signatures/annotations only, not a standalone program.
@Cacheable(cacheNames = "customers", key = "#p0")
public Customer load(long customerId, boolean includeDetails) { /* ... */ }

@Cacheable(cacheNames = "customers", key = "#customerId")
public Customer load(long customerId, boolean includeDetails) { /* ... */ }
~~~

Both expressions select `customerId` if name metadata exists. However, **you must revisit the key design** if `includeDetails` changes the returned data: using only `customerId` could then put the wrong variant into the cache. Parameters that affect the result must be reflected in the key or separated into different cache regions.

Example of a method where two parameters both affect the result:

~~~java
@Cacheable(cacheNames = "prices")
public String price(String sku, String currency) {
    return queryPrice(sku, currency);
}
~~~

If `key` is omitted, the default `SimpleKeyGenerator` combines the arguments into an appropriate key (in the two-parameter scenario). With `key = "#p0"`, currency is ignored, easily causing a USD price to be returned for an EUR call with the same SKU. Only select a single argument when you are certain it uniquely identifies the result.

## 7. Common Application Expressions

| Purpose | SpEL Example in Annotation | Meaning / Condition |
| --- | --- | --- |
| Get first argument | `key = "#p0"` or `key = "#a0"` | Key is the first argument |
| Get second argument | `key = "#p1"` or `key = "#a1"` | Key is the second argument |
| Get by name | `key = "#customerId"` | Requires `customerId` name discovery |
| Get property | `key = "#p0.id"` or `key = "#customer.id"` | First argument is a non-null object with property `id` |
| Root args | `key = "#root.args[0]"` | Alternative way to get argument by position |
| Conditional caching | `condition = "#p1 == true"` | Only cache when the second argument is true |
| Exclude null values after execution | `unless = "#result == null"` | Do not write null results to the cache |
| Distinguish methods in one cache region | `key = "#root.methodName + ':' + #p0"` | Useful when two methods share a region but need distinct keys |

The examples above are **standalone** expression strings that must be placed in valid annotations on methods with matching argument counts and types. Do not reference `#p1` if the method only has one argument. With `#p0.id`, the property must actually be accessible from SpEL (e.g., via a JavaBean getter), and the ID value must be stable.

Differences in evaluation timing:

- `@Cacheable(key = "...")` and `condition = "..."` normally use information available **before** method execution.
- `unless = "..."` is evaluated **after** a result is obtained; when applicable, `#result` references the business result.
- `#result` is **not** an input variable for writing `@Cacheable(key = "#result")`; during a normal cacheable lookup, the method has not been called yet and no result exists.
- With `@CachePut`, the `key` expression can use `#result` according to the operation's specific timing; this is specific to that caching operation and does not change how `#p0`/`#a0` work.

## 8. Common Errors and How to Fix Them

### Error 1: `#isbn` is not recognized even though the Java method has an `isbn` parameter

**Symptom:** Named expression evaluates to null or fails cache key generation, while `#p0` still works.

**Common causes:** Class was compiled without `-parameters`; method is discovered through a proxy/interface or generated code with unexpected metadata.

**Fix:** Add `-parameters` to the Java compile task, clean/rebuild the artifact containing the method, and verify `Parameter.isNamePresent()`. When you do not control how classes are compiled, use `#p0` or `#a0` and verify the exact index. Do not try to fix it by assuming an `#arg0` variable.

### Error 2: Confusing 0-based indexing

With `findBook(String isbn, boolean includeArchived)`, `#p0` is `isbn`; `#p1` is `includeArchived`. `#p2` is not the second parameter but the third position, which does not exist. Check the signature in actual order to avoid errors or wrong keys.

### Error 3: Key omits a parameter that affects the result

~~~java
// Wrong if currency changes the returned price:
@Cacheable(cacheNames = "prices", key = "#sku")
public String price(String sku, String currency) {
    return queryPrice(sku, currency);
}
~~~

This expression omits `currency`, so two calls with the same SKU but different currencies can share an entry. Include enough information in the key, or let the default `SimpleKeyGenerator` combine all arguments when appropriate. **Using the right name is not enough; you must choose the right data that identifies the result.**

### Error 4: Argument or property is `null`

`#p0.id` cannot access `id` if the first argument is null. `#p0?.id` uses safe navigation and may return null, but many cache managers do not allow **null keys**. Do not treat safe navigation as a complete solution for null keys; use `condition` to skip caching in that scenario, or design a non-colliding alternative key value.

Example of a method that may receive null:

~~~java
@Cacheable(cacheNames = "books",
           condition = "#p0 != null",
           key = "#p0")
public String findBook(String isbn) {
    return queryBook(isbn);
}
~~~

This is a method-level illustration (`queryBook` must be defined). When the condition is false, Spring does not apply caching for that call; business code must still handle null per the method's own contract.

### Error 5: Self-invocation within the same class

A method on a bean calling `this.findBook(...)` normally bypasses Spring's cache proxy in default proxy mode. You might mistakenly think `#p0` is wrong because the cache does not hit. Check the caching infrastructure/proxy before changing the expression.

### Error 6: Confusing caching SpEL with other SpEL environments

`#p0` and `#a0` are variables provided by the **cache operation context**. Do not assume they exist everywhere SpEL is used, such as `@Value`, security expressions, or a manually instantiated SpEL parser. Which variables exist depends on the evaluation context prepared by the framework.

### Error 7: Key mutates after storage

If the key is a mutable object whose `equals()`/`hashCode()` changes with state, the entry can become unretrievable or misidentified. Consider extracting an immutable ID field: `key = "#p0.id"` (when non-null and valid) instead of using the whole object as the key. Avoid calling methods with side effects inside SpEL keys.

## 9. How to Verify an Expression in a Real Application

When you get unexpected cache misses or key errors, check in order:

1. **Method signature:** what are the first and second arguments, what are their types, and can they be null?
2. **Expression:** is `#` present before the variable name; do `#p0`/`#a0` or `#p1` have the correct index?
3. **Name metadata:** if the expression uses `#isbn`, was the class compiled with `-parameters`? What does reflection `isNamePresent()` return?
4. **Cache identity:** what region is `cacheNames`; do multiple methods share a region and accidentally generate the same key?
5. **Proxy and conditions:** is `@EnableCaching` active, does the call go through a Spring bean/proxy, and are `condition`/`unless` blocking caching?
6. **Key data coverage:** are all parameters affecting the result included in the key? Is the key value stable and accepted by the provider?

To isolate the difference between name-based and positional access, you can temporarily change `key = "#isbn"` to `key = "#p0"` in a case where the first argument is clearly the ISBN. If only the named variable fails, prioritize checking metadata/parameter name discovery. If both fail, investigate Spring proxies, the cache manager, and key types more broadly.

## 10. Self-Check Exercises

**Exercise 1.** Given:

~~~java
public String search(String keyword, int page, boolean exact) {
    return "...";
}
~~~

For the call `search("spring", 2, true)`, what is `#p0`? What is `#a1`? What is `#root.args[2]`?

**Answer:** `"spring"`, `2`, `true`.

**Exercise 2.** Do `#p0` and `#a0` require the `-parameters` flag? Do the two variables refer to different arguments?

**Answer:** No flag is needed for positional access; both reference the argument at index 0.

**Exercise 3.** To use `key = "#keyword"` for Exercise 1, what condition is required?

**Answer:** Spring must be able to discover the parameter name `keyword`, e.g., the Java class was compiled with `-parameters`. You must also be sure that keyword alone determines the result; if page or exact changes the result, the key must reflect that information.

**Exercise 4.** Why is `#result` not used as the `key` of `@Cacheable` in the usual way?

**Answer:** Cache lookup occurs before executing the method body on a potential hit, so no result exists yet; `#result` is suitable in post-execution contexts such as `unless` as specified by Spring.

## 11. Takeaways and Official Sources

- `#p0` = `#a0` = **first argument**; `#p1` = `#a1` = **second argument**. Indexing starts at 0.
- `#paramName` such as `#isbn`/`#customerId` is readable but requires parameter name metadata. In modern Java, **`-parameters`** is the standard choice.
- `#root.args[0]` is an alternative way to get an argument by index.
- Expressions placed in `key`, `condition`, and `unless` belong to the **Spring caching evaluation context**; `#result` is only available at appropriate stages.
- Key selection must fully reflect the parameters that affect the result; valid SpEL syntax does not automatically mean a correct cache design.

**Spring Documentation:**

- [Declarative Annotation-based Caching — Parameters and Evaluation Context](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Cache — @Cacheable API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/annotation/Cacheable.html)
- [Spring Framework — SpEL Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Java Compiler — `-parameters` specification](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
