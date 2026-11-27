# Using curl and HAL Explorer to Inspect the Root Resource

When starting a Spring Data REST application, inspect the **API root resource** first. The root resource is the entry point for clients to discover the resources published by the server. Instead of guessing collection or item URLs, clients read links from the HAL response and follow the appropriate relations.

Two commonly used tools:

- **curl** sends HTTP requests directly and displays status codes, headers, and bodies. It is ideal for protocol inspection, reproducing errors, and automation.
- **HAL Explorer** is a web UI for browsing HAL/HAL-FORMS responses. It parses links from responses, displays advertised operations, and lets you try requests in the browser.

curl shows exact HTTP requests/responses; HAL Explorer makes API discovery visual. Both rely on the links returned by the server.

## 1. The Root Resource in Spring Data REST

Spring Data REST exposes repositories as HTTP resources. A repository managing `Book` can produce the collection resource **`/books`** and item resource **`/books/1`**. The API root sits at the top level and contains links pointing to other resources.

Example HAL root response:

~~~json
{
  "_links": {
    "books": {
      "href": "http://localhost:8080/api/books"
    },
    "profile": {
      "href": "http://localhost:8080/api/profile"
    }
  }
}
~~~

This is an illustrative response; actual relation names and URLs depend on your repositories, base path, and application configuration.

- **`_links`:** the set of links published by the server.
- **`books`:** a relation (`rel`) describing the link's meaning; in this example, it points to the book collection.
- **`href`:** the target URI of the link.
- **`profile`:** a relation that can lead to metadata/profiles describing resources.
- **`self`:** a relation typically pointing to the current resource itself.

The root resource is not a collection. The root points to collections or capabilities; collections hold items, typically inside **`_embedded`**.

Even when a collection is empty, the root still returns the **`books`** link. Thus, you do not need to insert data beforehand to verify whether a repository has been exported as an API.

## 2. Preparing the Application

If you already have a running Spring Data REST application, you can use its current URL. For a Spring Boot 3.x and Java 17+ project, basic dependencies can be declared as follows:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-rest</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Repository example:

~~~java
package com.example.library;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "books",
    collectionResourceRel = "books"
)
public interface BookRepository extends JpaRepository<Book, Long> {
}
~~~

**`Book`** is the domain type and **`Long`** is the ID type. Spring Data REST uses the repository to create the collection resource. The `Book` entity must be defined and mapped according to your persistence provider.

You can set the base path in **`src/main/resources/application.properties`**:

~~~properties
spring.data.rest.base-path=/api
~~~

With that setting, the API root lives under **`/api`**. If no base path is set, the API is typically exposed at the application's root.

Start with the Maven wrapper:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Wait until Spring Boot reports that the application has started and the server is listening, e.g., on port 8080.

## 3. Sending a GET Request to the API Root with curl

With base path **`/api`**, run:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api
~~~

In PowerShell, invoke **`curl.exe`** to avoid the **`curl`** alias that may point to `Invoke-WebRequest`:

~~~powershell
curl.exe -i -H "Accept: application/hal+json" http://localhost:8080/api
~~~

Options:

- **`-i`:** prints both response headers and response body.
- **`-H`:** sends a custom HTTP header.
- **`Accept: application/hal+json`:** requests a HAL JSON representation.
- **`URL`:** the API root URI, including the base path if configured.

A successful response typically has status **`200 OK`**, a HAL JSON `Content-Type` such as **`application/hal+json`**, and a body containing relations in **`_links`**.

Abbreviated example output:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
  "_links": {
    "books": {
      "href": "http://localhost:8080/api/books"
    },
    "profile": {
      "href": "http://localhost:8080/api/profile"
    }
  }
}
~~~

Actual headers may also include `Date`, `Cache-Control`, `Vary`, `Transfer-Encoding`, or security headers. Do not expect the response to match the example verbatim.

### Reading Status, Headers, and Body

Inspect three parts:

1. **Status line:** did the request succeed?
2. **Response headers:** what media type did the server return?
3. **Response body:** is it a HAL document containing the expected relations?

Common statuses:

| Status | What to Check |
|---|---|
| 200 OK | Root resource returned a successful response |
| 301/302/307/308 | Check the `Location` header and redirect target |
| 401 Unauthorized | Request lacks required authentication |
| 403 Forbidden | Request was denied by access policy |
| 404 Not Found | Wrong URL/base path, or root is not mapped at that path |
| 406 Not Acceptable | Media type in `Accept` is not supported |
| 500 Internal Server Error | Check server logs and exceptions |

A 401/403 does not prove a repository is not exported. Likewise, a 404 does not prove a repository lacks CRUD methods. Separate path errors, authentication, authorization, and resource configuration.

### Using Verbose Mode

When you need to inspect request headers, connection details, or redirects:

~~~bash
curl -v -H "Accept: application/hal+json" http://localhost:8080/api
~~~

**`-v`** prints diagnostic details such as the request line, request headers, and connection info. If you only need response headers and body, **`-i`** is usually easier to read. Do not confuse curl debug lines with the JSON body.

## 4. Reading and Following Links in a HAL Response

After a successful GET on the root, inspect **`_links`**. Each relation name represents a navigation target.

Example **`books`** relation:

~~~json
{
  "books": {
    "href": "http://localhost:8080/api/books"
  }
}
~~~

Use the exact URI in **`href`** to send the next request:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/api/books
~~~

A collection response typically includes:

- **`_embedded`:** the list of items embedded in the collection.
- **`_links.self`:** link to the current collection.
- **`_links.profile`:** link to collection metadata.
- **`_links.search`:** link to published query methods.
- **`page`:** page number, page size, and total elements/pages.

Example of an empty collection:

~~~json
{
  "_embedded": {
    "books": []
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/books?page=0&size=20"
    },
    "profile": {
      "href": "http://localhost:8080/api/profile/books"
    },
    "search": {
      "href": "http://localhost:8080/api/books/search"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 0,
    "totalPages": 0,
    "number": 0
  }
}
~~~

This is an illustrative response. When data exists, items appear in **`_embedded.books`**; the exact key name depends on the collection relation.

### Extracting Links with `jq`

If **`jq`** is installed, you can list relations and hrefs:

~~~bash
curl -sS -H "Accept: application/hal+json" http://localhost:8080/api \
  | jq -r '._links | to_entries[] | "\(.key)\t\(.value.href)"'
~~~

Illustrative output:

~~~text
books    http://localhost:8080/api/books
profile  http://localhost:8080/api/profile
~~~

A link can be a URI template and include **`templated: true`**:

~~~json
{
  "self": {
    "href": "http://localhost:8080/api/books{?page,size,sort}",
    "templated": true
  }
}
~~~

Curly braces denote URI template variables. HAL Explorer understands templates and displays a dialog to enter variables. curl does not expand URI templates automatically; when using curl, expand them according to the exact variable names advertised by the server or use a URI Template library. Do not guess parameter names if the response does not provide them.

Once you have confirmed the collection accepts **`page`** and **`size`**, you can pass query parameters with curl:

~~~bash
curl -G \
  -H "Accept: application/hal+json" \
  --data-urlencode "page=0" \
  --data-urlencode "size=10" \
  http://localhost:8080/api/books
~~~

**`-G`** turns **`--data-urlencode`** values into a GET query string. Use the exact variable names advertised in links or API documentation.

## 5. Installing HAL Explorer

HAL Explorer is a web interface for browsing HAL and HAL-FORMS responses. It parses links, navigates collections/items, displays headers/bodies, and helps send requests advertised by the API.

With modern Spring Data REST, add the Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-rest-hal-explorer</artifactId>
</dependency>
~~~

With Gradle:

~~~gradle
runtimeOnly 'org.springframework.data:spring-data-rest-hal-explorer'
~~~

If you use Spring Boot dependency management or the Spring Data BOM, you generally do not need to specify a separate version. Keep Spring Boot and Spring Data versions compatible.

The dependency auto-configures HAL Explorer to be served when opening the application's root URI in a browser. If the application uses a base path such as **`/api`**, open that configured API root; the integration can redirect to the Explorer UI.

HAL Explorer assists with manual exploration. It does not replace API contracts, automated tests, or server-side access-control checks.

## 6. Exploring the Root Resource with HAL Explorer

After adding the dependency and starting the application:

1. Open your browser to the application address, such as **`http://localhost:8080/`**. If the API uses a base path, enter the corresponding API root, such as **`http://localhost:8080/api`**.
2. HAL Explorer displays the current URI and the list of links provided by the HAL response.
3. Select the **`books`** relation to navigate to the collection.
4. Inspect the response headers and response body in the inspector pane.
5. From the collection, select an item link or the **`search`** relation if advertised.
6. When encountering a URI template, enter parameters in the dialog displayed by Explorer.

The UI typically has two areas:

- **Explorer:** the current URI, links, available methods/actions, and request details.
- **Inspector:** response headers and response body of the most recent request.

Explorer reads links from the HAL response and presents them as actionable controls. The GET button navigates to the resource. Other buttons can open create, update, or delete actions if advertised and allowed by the API.

### Observing a Request

When selecting the **`books`** link, verify:

- Does the navigated URI match the **`href`** from the root response?
- Is the HTTP method GET or another method?
- Did the response status succeed?
- Is the `Content-Type` HAL JSON?
- Does the collection contain **`_embedded`** and **`_links`**?
- Do **`self`**, **`profile`**, and **`search`** links appear as expected?

When selecting an item, check the **`self`** link and association links if the domain model has relationships. Explorer shows the paths advertised by the server; it does not guarantee every business operation is valid.

### Trying a URI Template

If a link has **`templated: true`**, Explorer can open a dialog to enter `page`, `size`, `sort`, or other variables. Enter values and observe the final URL sent.

If you leave variables blank, Explorer may omit the template variables. This is helpful when viewing the collection with defaults, but inspect the URL/response to see which defaults the server applied.

### Trying Write Operations

Explorer may provide forms for POST, PUT, PATCH, or DELETE. For non-GET operations, it can display the method, fields inferred from metadata, and a JSON body editor.

Only test write operations in development environments or against test data:

- POST to a collection can create a new record.
- PUT to an item can replace data.
- PATCH to an item can partially update fields.
- DELETE can remove an item.

Before sending, double-check the URI, method, headers, and body. POST or DELETE can alter real data if pointed at the wrong environment.

## 7. Comparing curl and HAL Explorer

| Criterion | curl | HAL Explorer |
|---|---|---|
| Send GET to root | Yes | Yes |
| Show status and headers | Yes, via `-i` or `-v` | Yes, in the inspector |
| Read HAL JSON | Yes, directly or via `jq` | Yes, automatically parses links |
| Follow links | Copy `href` or script it | Click relations in the UI |
| URI templates | Expand manually or via library | Built-in dialog for variables |
| POST/PUT/PATCH/DELETE | Via HTTP options and body | UI forms when advertised by the API |
| CI automation | Very suitable | Not its primary purpose |
| Visual exploration | Less visual | Ideal for manual exploration |

Choose curl when you need reproducible requests, exact header inspection, scripting, or pipeline checks. Choose HAL Explorer when you want to inspect links, step through resources, and quickly explore an unfamiliar API.

## 8. End-to-End Verification Workflow

Suppose the application runs at **`http://localhost:8080`** and Spring Data REST has base path **`/api`**.

**Step 1 — check the root:**

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api
~~~

Expected: successful response, HAL JSON `Content-Type`, and a body with **`_links`**.

**Step 2 — confirm the collection link:**

Read the **`books`** relation and take the exact URI in **`href`**. Do not construct paths manually when links are already provided.

**Step 3 — call the collection:**

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api/books
~~~

Expected: HAL collection containing **`_links`**; if items exist, they appear inside **`_embedded`**.

**Step 4 — open the profile:**

Use the **`profile`** link returned from the collection or root response. Do not assume profile URLs are identical across all applications.

**Step 5 — open HAL Explorer:**

Open the root URI in a browser. Select **`books`**, inspect the request and response in Explorer/Inspector, and follow links provided by the server.

**Step 6 — test pagination:**

If the collection link is a URI template, use Explorer to enter parameters. With curl, expand the advertised variables properly and send GET.

**Step 7 — record the results:**

Note the status, `Content-Type`, relations, `href`s, collection data, and pagination info. If results differ from expectations, compare the curl request against the request sent by Explorer to spot differences in URI, headers, or authentication state.

## 9. Common Errors and Troubleshooting

### curl returns 404

- Verify host and port.
- Verify the application has started.
- Check **`spring.data.rest.base-path`**.
- Call the correct API root, avoiding confusion with admin UI URLs or specific collections.
- Use the **`href`** link from the previous response.

### curl returns 406

Check the **`Accept`** header. For HAL JSON, try:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api
~~~

If the endpoint only supports a different media type, check the endpoint's contract instead of repeatedly changing the URL.

### curl returns 401 or 403

Check Spring Security configuration, credentials, and access permissions. HAL Explorer running in the browser is also affected by sessions, cookies, tokens, and security policies.

### Body lacks `_links`

Check:

- Are you calling the actual Spring Data REST API root?
- Is `Content-Type` HAL JSON?
- Was the request routed to another controller or static resource?
- Is the repository exported?
- Is the `Accept` header correct?

### HAL Explorer does not appear

- Confirm the **`spring-data-rest-hal-explorer`** dependency is on the runtime classpath.
- Verify the dependency version is compatible with Spring Data REST.
- Restart the application after adding the dependency.
- Open the exact application/API root URI and follow any redirects.
- Inspect server logs and the root URI response if the UI fails to load.

### Explorer shows links, but requests fail

Check URI, method, headers, body, authentication, and status code. Published links are navigation hints; the server can still reject requests due to validation, authorization, or business state.

### URI template links do not work

Check **`templated: true`**, variable names, and URI expansion. Explorer provides a variable input dialog; with curl, expand the template using valid syntax. Never send literal curly braces as though they were a complete URL.

## 10. API Root Verification Checklist

- [ ] Spring Boot application started on the expected port.
- [ ] Spring Data REST base path confirmed.
- [ ] GET on root returns the expected status.
- [ ] `Content-Type` is HAL JSON as requested.
- [ ] Body contains **`_links`**.
- [ ] Read actual relations and **`href`**s.
- [ ] Followed collection link and verified response.
- [ ] Checked **`profile`** link if metadata is needed.
- [ ] HAL Explorer dependency added and accessible.
- [ ] Explorer displays links, request methods, headers, and bodies.
- [ ] URI templates are handled properly.
- [ ] Write operations tested only on non-production environments/test data.
- [ ] Distinguished URL, media type, authentication, and authorization errors.

## 11. Conclusion

The API root is the starting point for exploring a Spring Data REST API. Use curl to inspect HTTP statuses, headers, media types, and HAL bodies precisely. Read **`_links`**, extract URIs from **`href`**, and follow relations to reach collections, items, or profiles.

HAL Explorer provides a visual interface for the same discovery flow: it parses links, understands URI templates, displays responses, and lets you test methods advertised by the API. Combining both tools lets you verify APIs both reproducibly from the command line and visually during development.

## References

- [Spring Data REST Reference — Resource Discoverability](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST Reference — The HAL Explorer](https://docs.spring.io/spring-data/rest/reference/tools.html)
- [Spring Data REST — Getting Started](https://spring.io/guides/gs/accessing-data-rest)
- [HAL Explorer Reference Documentation](https://toedter.github.io/hal-explorer/release/reference-doc/)
