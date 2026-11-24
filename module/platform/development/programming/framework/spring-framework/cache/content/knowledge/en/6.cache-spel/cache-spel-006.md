# Handling Null Objects in Spring Cache SpEL Expressions

> **Context:** Spring Framework — **SpEL Expressions** topic. This lesson focuses on handling `null` values when accessing properties, invoking methods, and evaluating conditions in SpEL, especially in `key`, `condition`, and `unless` on Spring Cache annotations.

## 1. Objectives

After this lesson, you will be able to:

- Identify when accessing a `null` object causes a SpEL evaluation failure.
- Use the safe navigation operator `?.`, the Elvis operator `?:`, the ternary operator, and short-circuit logical conditions.
- Handle multi-level property chains, null inputs, null results, and empty strings.
- Write expressions for `@Cacheable` with `key`, `condition`, and `unless` at the right evaluation timing and avoid null cache keys.
- Run a standalone Java 17 example using `spring-expression`; distinguish syntax experiments from actual cache annotation integration tests.

## 2. Why Do Null Objects Break SpEL Expressions?

Spring Expression Language (SpEL) is used to read properties, call methods, compare values, and construct keys or conditions from objects. Consider a structure:

```text
request
  └── customer
        └── address
              └── city
```

In practice, `request`, `customer`, or `address` can all be null. The following expression assumes by default that every object exists:

```spel
#request.customer.address.city
```

If an intermediate object is null, continuing to access a property normally causes SpEL to throw `SpelEvaluationException`. This differs from **an expression legitimately returning null**: an evaluation failure can cause the cache operation to fail, whereas a null-safe expression returns null and lets subsequent steps decide.

Typical sources of null include omitted method arguments, uninitialized properties, records not found in the database, `Optional.empty()` values, or absent collections. For caching, clearly distinguish three concerns: **safe expression evaluation**, **a valid storage key**, and **whether the value is allowed to be cached**.

## 3. The Safe Navigation Operator `?.`

Place `?.` before reading a property or calling a method on a potentially null object:

```spel
#request?.customer
#request?.customer?.address
#request?.customer?.address?.city
#request?.customer?.getName()
```

For an operation using `?.`, if the left-hand operand is null, the result of that operation is null instead of dereferencing a null object. If the left-hand side is non-null, SpEL performs the access normally.

**Protect every link in the chain that can be null.** Compare:

```spel
#request?.customer.address.city
#request?.customer?.address?.city
```

The first line **can still fail**: after `#request?.customer` returns null, the `.address.city` portion of the chained expression is still evaluated. The second line uses safe navigation at each subsequent step, so it is safe if `request`, `customer`, or `address` is null.

| Case | Expression | Result |
| --- | --- | --- |
| `request == null` | `#request?.customer` | `null` |
| `customer == null` | `#request?.customer?.address?.city` | `null` |
| `address == null` | `#request?.customer?.address?.city` | `null` |
| All objects present | `#request?.customer?.address?.city` | City value |
| Getter throws an exception itself | `#request?.customer` | Can still throw the exception from the getter |

Safe navigation does **not** hide wrong property names, type mismatches, exceptions thrown inside a getter, subsequent accesses missing `?.`, or domain errors inside a method.

## 4. The Elvis Operator `?:` — Choosing a Fallback Value

Elvis in SpEL lets you write `a ?: b`. If `a` is null **or an empty string**, SpEL selects `b`:

```spel
#request?.customer?.name ?: 'Guest'
#request?.customer?.address?.city ?: 'Unknown'
```

Examples:

| Name Value | `#name ?: 'Guest'` |
| --- | --- |
| `null` | `Guest` |
| `""` | `Guest` |
| `"Lan"` | `Lan` |

Caution: SpEL's Elvis operator treats an empty string as a missing value. If an empty string must be preserved for business reasons, use an explicit ternary condition:

```spel
#name == null ? 'Guest' : #name
```

**A fallback suitable for display** is not necessarily suitable for a cache key. For example, `#p0?.id ?: 'MISSING'` lumps every input missing an ID into a single `MISSING` key, risking key collisions and returning wrong data across users or tenants. For cache keys, you should normally **skip caching when the identifier is missing** or validate input, rather than using a shared sentinel.

## 5. The Ternary Operator and Short-Circuit Logical Evaluation

SpEL supports `condition ? trueValue : falseValue`:

```spel
#request == null ? 'empty' : #request.customerId
```

Use the ternary operator when two distinct business branches are needed. You must still guard nested values if the chosen branch can encounter null.

The operators `and`/`&&` and `or`/`||` support short-circuit evaluation. With AND, if the left side is false the right side is not evaluated; with OR, if the left side is true the right side is not evaluated:

```spel
#request != null && #request.customer != null
#request == null || #request.customer == null
#request != null and #request.customer != null
```

For cache conditions, the following two forms can be equivalent when accessors behave normally:

```spel
#p0 != null && #p0.customer != null && #p0.customer.id != null
#p0?.customer?.id != null
```

Both check for an identifier to decide whether to cache. Using `?.` is concise; explicit conditions are convenient when combining multiple business checks.

## 6. SpEL in Spring Cache: Each Attribute Has Its Own Evaluation Timing

SpEL evaluated directly via `SpelExpressionParser` and SpEL inside cache annotations share the same syntax, but the **cache evaluation context** provides specific variables:

| Variable | Meaning |
| --- | --- |
| `#p0` or `#a0` | First method parameter |
| `#p1` or `#a1` | Second parameter |
| `#root.args[0]` | First parameter via the root object |
| `#root.methodName` | Method name |
| `#root.target` | Target object of the call |
| `#result` | Return value after method execution, **only in permitted expressions** |

Parameter-name variables like `#request` require parameter name information in bytecode; `#p0` and `#a0` make examples less dependent on compiler flags.

Timing table:

| Annotation/Attribute | Timing | Has `#result`? |
| --- | --- | --- |
| `@Cacheable.condition` | Before deciding whether to access the cache | No |
| `@Cacheable.key` | When computing the key to look up and store in cache | No |
| `@Cacheable.unless` | After obtaining the result of an actual invocation | Yes |
| `@CachePut.key` | When writing the result to the cache | Available |
| `@CacheEvict` post-invocation | After the method completes | Available |
| `@CacheEvict(beforeInvocation = true)` | Before calling the method | No |

Crucial point: **`@Cacheable(key = "#result?.id")` is wrong on timing**, because the framework needs the key *before* knowing the result. Adding `?.` cannot fix `#result` not yet existing in context. Conversely, `unless = "#result == null"` is valid for vetoing storage of a null result **after running the method**.

For wrapper return types supported by Spring Cache such as `Optional<Customer>`, `#result` in post-invocation cache context refers to the **unwrapped domain value**, or null if the Optional is empty. Do not assume you can write `#result.isPresent()` in `unless` as if it were an Optional object.

## 7. Spring Cache Example: Skipping Caching on Missing Input, Avoiding Caching Null Results

Suppose a Spring service receives a `LookupRequest` containing an ID and looks up a `Customer` via a repository. This is an **illustrative snippet inside a Spring bean that already has `LookupRequest`, `Customer`, and `repository`**; it is not a standalone Java program:

```java
@Cacheable(
    cacheNames = "customers",
    condition = "#p0 != null && #p0.id != null",
    key = "#p0.id",
    unless = "#result == null"
)
public Customer findCustomer(LookupRequest request) {
    if (request == null || request.getId() == null) {
        return null;
    }
    return repository.findById(request.getId()).orElse(null);
}
```

Processing flow:

1. If `request` is null, `condition` is false so Spring **does not use the cache**. The method still executes and must handle null itself in Java.
2. If `request` is non-null but ID is null, `condition` is still false; avoids generating a key without an ID.
3. If both `request` and ID are valid, Spring computes `key` and checks the cache. A cache hit can return the result without running the method body.
4. A cache miss calls the repository. If the repository finds nothing, the null result makes `unless` evaluate to true and **does not store that cache entry**.
5. A subsequent call with that nonexistent ID will continue to miss until new data arrives or conditions change.

Here `key = "#p0.id"` is safe whenever caching is enabled because `condition` already checked for non-null. You could write `key = "#p0?.id"` for null-safe syntax, but **a null expression value still cannot produce a valid explicit cache key** in cases where Spring validates keys; it is best not to trigger key generation when the ID is missing.

If you only want to cache results whose status is non-null, you can write:

```java
@Cacheable(
    cacheNames = "customers",
    key = "#p0",
    condition = "#p0 != null",
    unless = "#result?.status == null"
)
public Customer findCustomerById(String id) {
    return repository.findById(id).orElse(null);
}
```

`?.` protects against a null result. The `unless` expression is a **veto condition**: if the result is null or its status is null, it evaluates to true and skips caching. Verify that `status` is actually a readable property, and that the ID key properly distinguishes the data.

### Distinguishing Null Key, Null Result, and Null Parameter

These are three independent cases:

- **Null parameter**: the caller passes a null argument to the method. This does not automatically mean the default key generator returns null; `SimpleKeyGenerator` has its own rules for 0, 1, and multiple parameters.
- **Null key from an explicit expression**: `key = "#p0?.id"` can return null when ID is absent; Spring Cache may report an error like `Null key returned for cache operation`, even though the SpEL navigation itself did not throw.
- **Null result**: the method executes and returns null. Whether the cache stores it depends on the adapter/provider and policy; `unless = "#result == null"` proactively excludes that result from being cached.

Similarly, `condition = "#p0 != null"` **does not make the business method itself null-safe**. When `condition` is false, the Java code still runs; if `request.getId()` is called on a null `request` without checking, Java can still throw an exception.

## 8. Standalone Runnable Java 17 Example: Experimenting with SpEL Syntax

To separate syntax errors from null data, let's test the `spring-expression` library directly without starting Spring Boot or Redis.

### 8.1. Project Structure

```text
spel-null-demo/
├── pom.xml
└── src/main/java/demo/SpelNullDemo.java
```

### 8.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spel-null-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-expression</artifactId>
            <version>6.2.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.SpelNullDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-expression:6.2.1` is a concrete version to make the example reproducible on JDK 17. In an existing Spring Boot application, manage Spring module versions consistently via the project's Boot parent or BOM rather than pinning each module to a different version.

### 8.3. `src/main/java/demo/SpelNullDemo.java`

```java
package demo;

import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class SpelNullDemo {

    public static final class Address {
        private final String city;

        public Address(String city) {
            this.city = city;
        }

        public String getCity() {
            return city;
        }
    }

    public static final class User {
        private final String name;
        private final Address address;

        public User(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        public String getName() {
            return name;
        }

        public Address getAddress() {
            return address;
        }
    }

    private static Object evaluate(
            ExpressionParser parser,
            StandardEvaluationContext context,
            String expression) {
        return parser.parseExpression(expression).getValue(context);
    }

    public static void main(String[] args) {
        ExpressionParser parser = new SpelExpressionParser();
        StandardEvaluationContext context = new StandardEvaluationContext();

        context.setVariable("user", null);
        System.out.println("nullName="
                + evaluate(parser, context, "#user?.name"));
        System.out.println("fallback="
                + evaluate(parser, context, "#user?.name ?: 'guest'"));
        System.out.println("guard="
                + evaluate(parser, context,
                        "#user != null and #user.name != null"));

        context.setVariable("user", new User("", null));
        System.out.println("emptyName="
                + evaluate(parser, context, "#user?.name ?: 'guest'"));
        System.out.println("missingCity="
                + evaluate(parser, context,
                        "#user?.address?.city ?: 'unknown'"));

        context.setVariable("user", new User("Lan", new Address("Ha Noi")));
        System.out.println("city="
                + evaluate(parser, context, "#user?.address?.city"));
    }
}
```

### 8.4. Compiling and Running

Requires JDK 17+, Maven 3.9+, and network access to download dependencies on the first run. Inside the `spel-null-demo` directory:

```bash
java -version
mvn -q compile exec:java
```

Lines printed by **the program itself** (excluding Maven/plugin output):

```text
nullName=null
fallback=guest
guard=false
emptyName=guest
missingCity=unknown
city=Ha Noi
```

Explanation:

- `nullName=null`: safe navigation returns Java null; String concatenation prints `null`.
- `fallback=guest`: Elvis replaces a null value with the fallback string.
- `guard=false`: AND stops at the first false condition without accessing `#user.name`.
- `emptyName=guest`: in SpEL, Elvis also treats an empty string as needing the fallback.
- `missingCity=unknown`: `user` exists but `address` is null; the second `?.` protects it.
- `city=Ha Noi`: when all nodes exist, the expression returns the actual property.

**Experiment limitation:** this program tests the **raw SpEL parser**. It does not create a `CacheManager`, verify Spring proxies, or measure cache hits/misses. When placing expressions into cache annotations, you must also check evaluation timing and provider behavior.

## 9. Null-Safe Indexing, Collection Selection, and Projection

Beyond reading properties, SpEL supports other null-safe forms (null-safe indexing syntax was introduced in Spring Framework 6.2):

| Purpose | Syntax | When Source Object Is Null |
| --- | --- | --- |
| Property access | `#user?.name` | Returns null |
| Method invocation | `#user?.getName()` | Returns null |
| Element access by index | `#items?.[0]` | Returns null |
| Filter collection | `#items?.?[active]` | Returns null |
| Select first matching element | `#items?.^[active]` | Returns null |
| Select last matching element | `#items?.$[active]` | Returns null |
| Project elements | `#items?.![name]` | Returns null |

**Two limitations to remember:** null-safe indexing does not protect accessing index 0 of a **non-null yet empty** list; and inner expressions inside selection/projection can still fail if individual elements have null values on other properties.

An example chaining multiple operations:

```spel
#items?.^[active]?.name ?: 'none'
```

If `items` is null, no matching element exists, or `name` is null/empty string, the result falls back to `none`. Elements that are actually selected must have valid `active` and `name` properties.

For `Optional`: direct null-safe support on an `Optional` object varies by version; Spring Framework **7.0** adds null-safe access and unwrapping on `Optional` in SpEL. Do not assume that modern syntax works identically on older Spring versions. This is separate from the `#result` unwrapping rule inside Spring Cache annotations.

## 10. Common Mistakes and Fixes

### Mistake 1: Using one safe navigation operator and then regular dots

- **Wrong:** `#p0?.customer.address.city`.
- **Right for nullable nodes:** `#p0?.customer?.address?.city`.

`?.` only protects **the operation at that exact position**; it does not automatically make the rest of the chain null-safe.

### Mistake 2: Using Elvis to build a shared key for multiple objects

- **Dangerous:** `key = "#p0?.id ?: 'unknown'"`.
- **Safer when missing ID means do not cache:** `condition = "#p0?.id != null"`, paired with a proper key for valid inputs.

Key design must reflect tenant, locale, role, and any arguments that change the result if business logic depends on them.

### Mistake 3: Using `#result` inside `@Cacheable`'s `key`

`#result` does not exist before the call; use method arguments, or choose an appropriate post-invocation cache update mechanism. Safe navigation cannot fix the wrong context.

### Mistake 4: Inverting the meaning of `unless`

To **avoid storing null results**, use:

```java
@Cacheable(cacheNames = "customers", key = "#p0",
           unless = "#result == null")
```

`unless` returning true means **do not store**; `unless = "#result != null"` blocks storing valid non-null results, which is usually the opposite of the goal.

### Mistake 5: Thinking `condition` stops the method from running

When `condition` is false, Spring Cache skips caching, but the Java code inside the method still executes. The method body must still validate or handle null itself. Only a `@Cacheable` hit skips the method body via interception.

### Mistake 6: Using null-safe logic to mask real exceptions

A getter throwing `IllegalStateException` is not turned into null by `?.`. Wrong property names or missing getters must be fixed according to Java structure and stack traces, not by sprinkling more `?.`.

### Mistake 7: Testing SpEL without testing actual caching

Testing the standalone parser only verifies syntax and expression output. A real integration test needs `@EnableCaching`, a provider, retrieving the bean through the Spring proxy, and asserting that with the same key the underlying method does not run a second time.

## 11. Controlled Testing Approach

You should prepare the following cases for the same expression:

| Case | Input/Result | Expected Behavior |
| --- | --- | --- |
| 1 | Root object null | Safe navigation returns null; condition can evaluate to false |
| 2 | Intermediate property null | Fully null-safe expression does not throw |
| 3 | Empty string | Elvis applies fallback |
| 4 | All valid values | Reads expected property, produces expected key |
| 5 | Method returns null | Appropriate `unless` skips storing |
| 6 | Different IDs | Do not accidentally share a cache key |
| 7 | Same ID, second call | Cache hit skips underlying execution |
| 8 | Cache evicted/TTL expired | Misses and re-runs the method body |

In practice, also inspect the `CacheManager` actually selected by Spring and the cached entry stored under the key. Avoid putting a shared sentinel into keys when authorization or tenant-scoped data is involved.

## 12. Self-Check Exercises

**Question 1.** When `person == null`, what is the result of `#person?.address?.city ?: 'N/A'`?  
**Answer:** `N/A`.

**Question 2.** If `person != null` but `person.address == null`, is `#person?.address.city` safe?  
**Answer:** No; use `#person?.address?.city`.

**Question 3.** Why does `key = "#p0?.id"` not guarantee caching works when ID is null?  
**Answer:** The expression can return null, yet explicit null cache keys are not accepted by Spring; avoid caching via `condition` or fix the input data.

**Question 4.** A method returns `Optional.empty()` and you do not want to cache the “not found” result. What `unless` should you write?  
**Answer:** `unless = "#result == null"` in Spring's cache evaluation context where `Optional` is supported.

**Question 5.** When `#p0 == null`, does `condition = "#p0 != null"` guarantee the Java method will not execute?  
**Answer:** No; it only skips caching. The method can still run and must handle null itself.

## Official Documentation

- [Spring Framework — Safe Navigation Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework — The Elvis Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-elvis.html)
- [Spring Framework — SpEL Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)

**Key takeaway:** `?.` prevents null dereferencing at that exact link; `?:` supplies an intentional fallback; `condition` can prevent applying caching to incomplete inputs; `unless` decides whether a computed result should be stored. Safeguard both the correctness of the **cache key** and the availability timing of SpEL variables, not merely avoiding exceptions.