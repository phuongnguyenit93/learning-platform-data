# Spring MVC: @RequestParam — Required Parameters, Default Values, Multiple Values, and Maps

## 1. Learning objectives

After this lesson, you will be able to:

- Receive controller input data using `@RequestParam` and distinguish between required and optional parameters.
- Configure `defaultValue`, understand when default values are used, and see how Spring performs type conversion.
- Receive multiple values with the same name via arrays or `List<T>`.
- Collect all request parameters using `Map<String, String>` or `MultiValueMap<String, String>`, choosing the right structure when a key may appear multiple times.
- Diagnose common errors (missing parameters, invalid type conversion, empty values) and test real endpoints.

Scope: Spring MVC (Servlet stack), Java 17+; examples run on Spring Boot 3.5.0 and Spring Framework 6.2.x. The core behaviors below are also documented in the Spring MVC reference.

## 2. What data does @RequestParam receive?

`@RequestParam` binds a **request parameter** to a controller method parameter:

~~~java
@GetMapping("/hello")
public String hello(@RequestParam("name") String name) {
    return "Hello " + name;
}
~~~

With the request `GET /hello?name=Lan`, the `name` variable receives `"Lan"`.

In **Spring MVC**, the Servlet concept of a request parameter includes both query string parameters (e.g., `?page=2`) and form data parsed by the Servlet container (typically `application/x-www-form-urlencoded`). For JSON in the request body, use `@RequestBody` with an appropriate DTO type; for a URL segment like `/products/42`, use `@PathVariable`. Spring WebFlux has different rules: `@RequestParam` only reads query parameters; do not apply this MVC rule mechanically to WebFlux.

**Mechanism summary:** Spring looks up the request parameter by name → determines whether it is missing → applies the default value if configured → converts the string to the target Java type → invokes the controller method. Errors during argument resolution can return HTTP 400 before the method body runs.

## 3. Attributes of @RequestParam

| Attribute | Meaning | Example |
| --- | --- | --- |
| `name` / `value` | Request parameter name; both attributes are aliases for each other | `@RequestParam("q")`, `@RequestParam(name = "q")` |
| `required` | Defaults to `true`: parameter must be present; `false`: allows absence | `@RequestParam(name = "q", required = false)` |
| `defaultValue` | Fallback value when the parameter is **absent or has an empty value**; automatically makes `required` false | `@RequestParam(name = "page", defaultValue = "0")` |

You should specify `name` explicitly in examples and public APIs. If the name is omitted, inferring it from the Java parameter depends on parameter name metadata being available at compile time; explicit names also make APIs easier to read.

### 3.1. Required parameters

~~~java
@GetMapping("/search")
public String search(@RequestParam(name = "q") String q) {
    return "Searching: " + q;
}
~~~

- `GET /search?q=java` → `q = "java"`.
- `GET /search` → missing `q`, Spring MVC defaults to returning HTTP **400 Bad Request**, typically with `MissingServletRequestParameterException`.
- `GET /search?q=` → `q` is present but is an empty string. With `String` and no content validation constraints, `required = true` **does not mean** "cannot be blank".

If business rules require meaningful text, add input validation (e.g., Bean Validation with `@NotBlank` and appropriate validation configuration) or custom checking logic. Do not use `required` as a substitute for validation.

### 3.2. Optional parameters: required = false and Optional

~~~java
@GetMapping("/filter")
public String filter(
        @RequestParam(name = "category", required = false) String category,
        @RequestParam(name = "minPrice") Optional<Integer> minPrice) {
    String selected = category == null ? "all" : category;
    String lowerBound = minPrice.map(String::valueOf).orElse("none");
    return selected + " / " + lowerBound;
}
~~~

When `category` is missing, the reference argument typically receives `null`; when `minPrice` is missing, `Optional<Integer>` is `Optional.empty()`. Using `Optional` can express "present or absent" semantics more clearly. Avoid relying on `null` with primitive types like `int`: choose `Integer`, `Optional<Integer>`, or provide a default value.

### 3.3. Default values

~~~java
@GetMapping("/page")
public String page(
        @RequestParam(name = "page", defaultValue = "0") int page,
        @RequestParam(name = "size", defaultValue = "20") int size) {
    return "page=" + page + ", size=" + size;
}
~~~

| URL | `page` | `size` | Reason |
| --- | ---: | ---: | --- |
| `/page` | 0 | 20 | Both are absent |
| `/page?page=3` | 3 | 20 | Only `size` uses default |
| `/page?page=&size=5` | 0 | 5 | Empty string triggers `defaultValue` |
| `/page?page=abc` | — | — | Cannot convert `abc` to `int`; typically HTTP 400 |

`defaultValue` is a string in the annotation; Spring converts it to the declared type (`"20"` → `int 20`). Declaring both `required = true` and `defaultValue` is misleading because **having a default makes it optional**. A default value does not act as a fallback for invalid values: `?page=abc` does not "fall back to 0".

## 4. Multiple values for the same parameter

A URL can repeat the same key:

~~~text
GET /api/tags?tag=java&tag=spring&tag=web
~~~

Receive them as an array or a list:

~~~java
@GetMapping("/tags")
public List<String> tags(@RequestParam(name = "tag") List<String> tags) {
    return tags;
}

@GetMapping("/tag-array")
public String[] tagArray(@RequestParam(name = "tag") String[] tags) {
    return tags;
}
~~~

With the URL above, the result represents three elements `["java", "spring", "web"]`. If you declare `List<Integer>`, Spring also has to convert each value to a number; an element like `tag=abc` can cause binding to fail. With a required `List<String>`, omitting the `tag` parameter completely can cause HTTP 400; to allow absence:

~~~java
@GetMapping("/tags-optional")
public List<String> tagsOptional(
        @RequestParam(name = "tag", required = false) List<String> tags) {
    return tags == null ? List.of() : tags;
}
~~~

When a client sends a comma-separated string (`?tag=java,spring`), Spring may split it during type conversion depending on the data type and configuration. To keep the API unambiguous, establish a **clear convention** for sending lists; the examples here use repeated keys. Do not assume all clients or converters handle comma syntax identically.

## 5. Map and MultiValueMap

### 5.1. Collecting all parameters with Map<String, String>

~~~java
@GetMapping("/params")
public Map<String, String> params(@RequestParam Map<String, String> params) {
    return params;
}
~~~

The request `/params?name=Lan&sort=asc` creates a map with `name → "Lan"`, `sort → "asc"`. The key rule: **omit the name** in `@RequestParam` and use `Map<String, String>` as the argument type, and Spring collects request parameters by name into the map. Each key in the map can only hold **one** string; when a key appears multiple times, this structure cannot preserve all repeated values.

### 5.2. Collecting all repeated values with MultiValueMap<String, String>

~~~java
import org.springframework.util.MultiValueMap;

@GetMapping("/params-all")
public MultiValueMap<String, String> paramsAll(
        @RequestParam MultiValueMap<String, String> params) {
    return params;
}
~~~

With `/params-all?tag=java&tag=spring&sort=asc`, the data is equivalent to:

~~~json
{
  "tag": ["java", "spring"],
  "sort": ["asc"]
}
~~~

`MultiValueMap<K, V>` maps one key → `List<V>`. Use `getFirst("tag")` if you only want the first value, or `get("tag")` when you want the entire list. Be sure to import the exact `org.springframework.util.MultiValueMap`.

| Controller parameter type | When to choose | If sending `?tag=a&tag=b` |
| --- | --- | --- |
| `@RequestParam("tag") String tag` | API needs a single value | Not suitable for preserving all values |
| `@RequestParam("tag") List<String> tags` | Only need all values for the specific `tag` key | `["a", "b"]` |
| `@RequestParam Map<String, String> params` | Want all parameter names, one value/key | Does not preserve both `a` and `b` |
| `@RequestParam MultiValueMap<String, String> params` | Want all names and all values/key | `tag → ["a", "b"]` |

**Be careful with the annotation name:** `@RequestParam("filters") Map<...>` does not mean "collect all parameters into a map". When you specify the name `filters`, Spring looks for a single parameter with that name and attempts to convert **the value of that specific parameter** into a `Map` (requiring a suitable converter). To collect all keys, use `@RequestParam Map<String, String>` **without specifying a name**.

## 6. Runnable example with Java 17 and Spring Boot

Maven project structure:

~~~text
request-param-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── RequestParamDemoApplication.java
~~~

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>request-param-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Create `src/main/java/demo/RequestParamDemoApplication.java`:

~~~java
package demo;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RequestParamDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequestParamDemoApplication.class, args);
    }
}

@RestController
@RequestMapping("/api")
class ParamController {
    @GetMapping("/required")
    public Map<String, String> required(@RequestParam("q") String q) {
        return Map.of("q", q);
    }

    @GetMapping("/defaults")
    public Map<String, Integer> defaults(
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "size", defaultValue = "20") int size) {
        return Map.of("page", page, "size", size);
    }

    @GetMapping("/optional")
    public Map<String, Object> optional(
            @RequestParam(name = "keyword", required = false) String keyword,
            @RequestParam(name = "limit") Optional<Integer> limit) {
        return Map.of(
                "keyword", keyword == null ? "(none)" : keyword,
                "limit", limit.orElse(10));
    }

    @GetMapping("/tags")
    public Map<String, List<String>> tags(
            @RequestParam(name = "tag", required = false) List<String> tags) {
        return Map.of("tags", tags == null ? List.of() : tags);
    }

    @GetMapping("/map")
    public Map<String, String> map(@RequestParam Map<String, String> all) {
        return all;
    }

    @GetMapping("/multi")
    public MultiValueMap<String, String> multi(
            @RequestParam MultiValueMap<String, String> all) {
        return all;
    }
}
~~~

In the directory containing `pom.xml`, run:

~~~bash
mvn spring-boot:run
~~~

By default, the application listens on `http://localhost:8080`. You can test:

~~~bash
curl -i 'http://localhost:8080/api/required?q=java'
curl -i 'http://localhost:8080/api/required'
curl -i 'http://localhost:8080/api/defaults?page=&size=5'
curl -i 'http://localhost:8080/api/defaults?page=oops'
curl -i 'http://localhost:8080/api/optional'
curl -i 'http://localhost:8080/api/tags?tag=java&tag=spring'
curl -i 'http://localhost:8080/api/map?name=Lan&sort=asc'
curl -i 'http://localhost:8080/api/multi?tag=java&tag=spring&sort=asc'
~~~

If running in Windows PowerShell and `curl` is an alias, use `curl.exe`.

Comparing key results (JSON object key order is not guaranteed):

| Command/path | Key result |
| --- | --- |
| `/api/required?q=java` | HTTP 200, `{"q":"java"}` |
| `/api/required` | HTTP 400 due to missing `q` |
| `/api/defaults?page=&size=5` | HTTP 200, `page=0`, `size=5` |
| `/api/defaults?page=oops` | HTTP 400 because `oops` cannot be converted to `int` |
| `/api/optional` | HTTP 200, `keyword="(none)"`, `limit=10` |
| `/api/tags?tag=java&tag=spring` | HTTP 200, `{"tags":["java","spring"]}` |
| `/api/map?name=Lan&sort=asc` | HTTP 200, map contains `name="Lan"`, `sort="asc"` |
| `/api/multi?tag=java&tag=spring&sort=asc` | HTTP 200, `tag=["java","spring"]`, `sort=["asc"]` |

Default error response payloads (body, message, trace) may vary depending on Spring Boot configuration; check the HTTP status and returned data instead of relying on verbatim error messages.

## 7. Common pitfalls and how to handle them

1. **Assuming `required = true` means text must be present:** For `String`, `?q=` is still an empty string. Validate content at the validation layer.
2. **Assuming `defaultValue` fixes any invalid input:** `?page=abc` is typically a number conversion error, not turned into the default value.
3. **Using `int` with `required = false` and no default:** Primitive types cannot hold `null`; use `Integer`, `Optional<Integer>`, or `defaultValue`.
4. **Using `Map<String, String>` to receive all values for duplicate keys:** You need `MultiValueMap<String, String>` or `List<String>`.
5. **Writing `@RequestParam("x") Map<String, String>` to collect everything:** The name `x` tells Spring to process a single named parameter, not all parameters.
6. **Confusing request parameters with JSON body or path variables:** Choose `@RequestBody`, `@PathVariable`, or `@RequestParam` according to the data source.
7. **Trusting Map data directly in queries or filters:** All keys/values from clients are untrusted. For strict APIs, use defined parameters/DTOs, validate values, bound page/size limits, and whitelist sort/filter names before use.
8. **Not standardizing how clients send lists:** Specify repeated keys, valid URL encoding, and exact key names; use `curl --get --data-urlencode` when values contain spaces or special characters.

## 8. Self-practice exercises

**Exercise 1 — Required:** Write `GET /orders?id=12` accepting `long id`. What happens when `id` is omitted or `id=xyz` is sent? Explain the two different causes leading to HTTP 400.

**Exercise 2 — Default:** Write `GET /products?page=1&size=10` with defaults `page=0`, `size=20`. Predict `/products?page=&size=7` and propose valid bounds for `size`.

**Exercise 3 — Multi-value:** Receive `?color=red&color=blue` as `List<String>`. Update the endpoint so it does not error when `color` is missing; return an empty list.

**Exercise 4 — Map:** Given `?tag=a&tag=b&sort=asc`, state the difference between `Map<String,String>` and `MultiValueMap<String,String>`. Show how to retrieve only the first element of `tag` from `MultiValueMap`.

*Verification hints:* Exercise 1 distinguishes missing parameter vs failed `String → long` conversion; Exercise 2 `page=0`, `size=7`; Exercise 3 uses `required=false` and replaces `null` with `List.of()`; Exercise 4 uses `params.get("tag")` and `params.getFirst("tag")`.

## 9. References

- [Spring Framework — MVC `@RequestParam`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html): how request parameters, `Optional`, arrays/lists, `Map`, and `MultiValueMap` are bound.
- [Spring Framework — `RequestParam` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/RequestParam.html): exact semantics of `name`, `required`, and `defaultValue`.
- [Spring Boot 3.5.0 release](https://spring.io/blog/2025/05/22/spring-boot-3-5-0-available-now/): version used in the example project.
