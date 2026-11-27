# Exploring APIs with HAL Explorer and Reading URI Templates

## Objectives

Spring Data REST uses HAL as its default hypermedia format. Clients start from the API root URI, read the link relations in the **_links** field, and follow **href** to find collections, items, associations, searches, and metadata. For links with **templated: true**, **href** is a URI template containing variables that must be populated before sending a request.

HAL Explorer is a browser-based interface that facilitates this discovery process. This guide walks through installing HAL Explorer, reading HAL documents, filling in URI templates, following metadata, and testing the links published by the API.

The examples use Java, Spring Boot, Spring Data REST, and Spring HATEOAS. Keep dependency versions aligned with your project's Spring Boot or Spring Data BOM to avoid version mismatches.

## 1. Enabling HAL Explorer

Add the **spring-data-rest-hal-explorer** dependency to your application.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-rest-hal-explorer</artifactId>
</dependency>
~~~

Gradle:

~~~groovy
dependencies {
    implementation "org.springframework.data:spring-data-rest-hal-explorer"
}
~~~

When using the Spring Boot or Spring Data BOM, there is no need to specify the version manually for this dependency. HAL Explorer auto-configures the UI to be served when opening the application's root URI. If the API configures a base path, for example:

~~~yaml
spring:
  data:
    rest:
      base-path: /api
~~~

open the application URI corresponding to the base path, such as **http://localhost:8080/api**. If no base path is configured, try **http://localhost:8080/**. When a browser sends an HTML request, HAL Explorer renders the UI; requests with Accept **application/hal+json** still read the API's HAL document.

HAL Explorer can navigate via GET and display POST, PUT, PATCH, and DELETE operations supported by the API. Because the UI can send requests that mutate data, enable it only in development/testing environments or protect it with the same authentication and authorization mechanisms as the API.

## 2. Discovering from the root resource

Start with a GET request to the Spring Data REST root URI:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api
~~~

Example root document:

~~~json
{
  "_links": {
    "people": {
      "href": "http://localhost:8080/api/people"
    },
    "profile": {
      "href": "http://localhost:8080/api/profile"
    }
  }
}
~~~

This is an illustrative example; relation names and URLs depend on repository annotations, base path, and configuration. In HAL:

- **_links** contains the link relations that a client can follow.
- **rel** is the relation name, such as **people**, **self**, **search**, **profile**, **next**, or **prev**.
- **href** is the target URI. Clients should read href from the response instead of manually concatenating the hostname and path.
- **templated: true** indicates that href contains URI template variables.
- **_embedded** typically contains embedded resources in a collection response.
- **page** contains pagination metadata when the endpoint returns paged data.

Resource discovery begins at the root. Follow a collection's link relation to retrieve the list; follow the **self** link to return to the current resource; follow **search** to find exported query methods; follow **profile** to inspect metadata. Do not assume every repository has a search link: this link only appears when the repository exports query methods.

### Distinguishing path and rel

Two values are commonly confused:

- **path** determines the URL segment of the resource.
- **rel** determines the link relation name appearing in the HAL document.

Example:

~~~java
@RepositoryRestResource(path = "people", rel = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "names", rel = "names")
    List<Person> findByName(@Param("name") String name);
}
~~~

The collection has URL **/people** and relation **people** at the root. The query method is discovered under the **names** relation inside the **search** resource. If you only set **path = "people"** without setting **rel**, the relation name may still remain the default pluralized name derived by Spring Data REST from the domain class.

## 3. Interacting with HAL Explorer

After opening the UI:

1. Look at the list of links in the left pane. Each link relation is a path published by the server.
2. Select GET to open a collection or resource. The details pane displays the request URI, HTTP method, response headers, and HAL body.
3. When a link has a URI template, HAL Explorer opens a dialog for the variables. Fill in the required parameters and select Go. Optional variables can be left blank; if left empty, they are omitted from the expanded URI.
4. For non-GET buttons, select the action to open the corresponding dialog. The UI displays the HTTP method and request body fields based on the resource metadata generated by Spring Data REST.
5. Inspect the response after sending: status, Location header if present, body, new links, and next navigation links.

HAL Explorer understands HAL and HAL-FORMS, and also supports Spring profiles generated by Spring Data REST. Fields in the request dialog are populated based on metadata; changing the domain object or representation configuration can change the list of displayed fields.

Examples of safe operations in a local environment:

- Open the **people** relation with GET to view the collection.
- Open **search**, then choose a published query relation to test searching.
- Use a templated link to test page/size/sort.
- Use POST with a valid JSON body to create sample data.
- Open the item's **self** link to inspect the newly created resource.

Do not enter real data or try POST/PUT/PATCH/DELETE in production just to explore the UI.

## 4. Reading URI templates

A paginated collection typically returns **self** and **next** links as templates. Example:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people{&sort,page,size}",
      "templated": true
    },
    "next": {
      "href": "http://localhost:8080/api/people?page=1&size=5{&sort}",
      "templated": true
    }
  },
  "page": {
    "size": 5,
    "totalElements": 50,
    "totalPages": 10,
    "number": 0
  }
}
~~~

In this example:

- **templated: true** indicates that href is not yet the final URI.
- **{&sort,page,size}** represents query variables that can be appended to the URI.
- **next** preserves the page and size of the next page; clients can follow this link instead of calculating page numbers themselves.
- **page.number** is the 0-based page index; **page.size** is the number of items per page.

For repositories supporting paging, the default parameters are typically **page**, **size**, and **sort**. Example:

~~~bash
curl -i -H "Accept: application/hal+json" "http://localhost:8080/api/people?page=1&size=5&sort=name,asc"
~~~

Enclose the entire URL in quotes when using a shell if the query string contains **&**, so the shell does not interpret it as a command chaining operator. Paging parameter names can be customized in Spring Data REST configuration; read the variables published by the server rather than assuming fixed names.

### Expanding templates with Spring HATEOAS

Spring HATEOAS provides **Link** to inspect and expand URI templates. Example:

~~~java
import java.util.Map;

import org.springframework.hateoas.Link;

Link template = Link.of("/people{?page,size,sort}");

assertThat(template.isTemplated()).isTrue();
assertThat(template.getVariableNames())
    .contains("page", "size", "sort");

String expanded = template.expand(
    Map.of("page", 1, "size", 5)
).getHref();

assertThat(expanded).isEqualTo("/people?page=1&size=5");
~~~

Key operations:

- **isTemplated()** indicates whether the link is a URI template.
- **getVariableNames()** returns the names of variables declared by the template.
- **expand(Map)** creates a link with variables replaced by the supplied values.
- **getHref()** returns the URI after expansion.

The example above uses **{?page,size,sort}** because the template begins the query string portion. When a URI already has query parameters and needs additional variables appended, the template can use the **{&sort}** operator as seen in Spring Data REST's **next** link.

Do not strip the template part or manually concatenate query strings when the server already provides a link. Using link relations and the expansion mechanism avoids requiring the client to know the URL structure in advance.

## 5. Reading metadata via profile

Spring Data REST publishes a **profile** link at the root or within a resource representation. Follow that link to locate metadata instead of constructing paths by assumption. ALPS documents describe repository semantics: resource properties and the REST operations that can be performed.

Discovery steps:

1. GET the root and look up the **profile** relation in **_links**.
2. Follow the profile link to retrieve the profile resources.
3. Follow the target collection's profile to view descriptors of the domain type and exported operations.
4. Send Accept **application/alps+json** to read ALPS; if JSON Schema is needed, try Accept **application/schema+json** at the published profile resource.

ALPS can describe operations such as get, create, update, patch, and delete along with representation fields. HAL Explorer uses this metadata to help build request bodies. Metadata does not replace authorization: an operation shown in a profile can still be denied by security policy when executed.

## 6. Testing links and templates

You should test both HAL responses and template expansion. Example using Spring Boot test and MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class HalDiscoveryTest {

    private static final MediaType HAL_JSON =
        MediaType.parseMediaType("application/hal+json");

    @Autowired
    private MockMvc mvc;

    @Test
    void rootPublishesCollectionRelation() throws Exception {
        mvc.perform(get("/api").accept(HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(HAL_JSON))
            .andExpect(jsonPath("$._links.people.href").exists());
    }

    @Test
    void collectionPublishesTemplatedPagingLink() throws Exception {
        mvc.perform(get("/api/people")
                .param("size", "5")
                .accept(HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.templated").value(true))
            .andExpect(jsonPath("$.page.size").value(5));
    }
}
~~~

If the application does not set **spring.data.rest.base-path: /api**, replace **/api** with the actual root URI. The repository must support paging for the response to include page metadata. To test **next**, prepare enough data to have at least two pages; the server does not emit a next link on the last page.

Testing template expansion separately:

~~~java
@Test
void expandsPagingTemplate() {
    Link template = Link.of("/people{?page,size}");

    assertThat(template.isTemplated()).isTrue();
    assertThat(template.getVariableNames()).contains("page", "size");

    assertThat(template.expand(Map.of("page", 1, "size", 5)).getHref())
        .isEqualTo("/people?page=1&size=5");
}
~~~

If the repository has finder methods, test the **search** relation and the query method's relation:

~~~java
mvc.perform(get("/api/people/search")
        .accept(HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.names.href").exists());
~~~

The search test assumes the repository declares the query method with **@RestResource(rel = "names")** as in the path/rel example. If using default naming, replace the JSON path with the actual relation returned by the server.

## 7. Troubleshooting common issues

| Symptom | Cause to check | Resolution |
|---|---|---|
| HAL Explorer UI does not appear | Missing dependency or wrong root/base path URI opened | Add **spring-data-rest-hal-explorer**, open the application URI matching **spring.data.rest.base-path** |
| Root returns 404 or has no collection link | Repository is not exported, wrong base path, or repository sets **exported = false** | Check repository scanning, path configuration, and **@RepositoryRestResource** |
| Link key is **persons** instead of **people** | Only **path** was changed, not **rel** | Set both **path = "people"** and **rel = "people"** if you want the relation named people |
| No **search** relation | Repository does not export query methods | Declare finder methods and verify they are not hidden by **@RestResource(exported = false)** |
| **next** is not present | Dataset is not large enough for a next page | Create enough records and test with a small **size** |
| **self** link does not have **templated: true** | Resource does not provide a URI template or does not support paging | Verify the repository supports paging and check the correct collection response |
| HAL Explorer prompts for template variables | Link has **templated: true** and requires parameters | Fill in variable names matching the template, e.g. **page**, **size**, **sort** |
| Query does not filter/sort as expected | Wrong variable name, sort value is not a valid property, or page is 0-based | Read the template, use valid domain property names, and check **page/size/sort** |
| POST/PUT/PATCH returns 405 | HTTP method or repository method is not exported | Check CRUD methods, **@RestResource(exported = false)**, and the target resource type |
| Request returns 401/403 | Security requires login or corresponding permissions | Use a valid session/credential and check the authorization policy |
| Dialog does not show expected fields | Metadata/representation does not expose those fields | Follow the **profile** link, check projections, serialization, and hidden fields |

## 8. Practice checklist

- [ ] HAL Explorer dependency is added and its version is managed by the BOM.
- [ ] Opened the correct root URI or REST base path in the browser.
- [ ] Root response has HAL content type and publishes collection relations.
- [ ] Distinguished relation name (**rel**) from URL path (**path**).
- [ ] Followed collection, item, search, and profile links returned by the server.
- [ ] Identified **templated: true** and listed the template variable names.
- [ ] Tested expanding the paging template with **page**, **size**, and **sort**.
- [ ] Verified page metadata and the conditions for **next/prev** to appear.
- [ ] Read ALPS or JSON Schema metadata via the profile link.
- [ ] MockMvc verifies root relations and collection paging templates.
- [ ] Separate test confirms the URI template expands to the expected URI.
- [ ] HAL Explorer is enabled only in appropriate environments and protected when needed.

## 9. Official documentation

- [Spring Data REST — Tools / HAL Explorer](https://docs.spring.io/spring-data/rest/reference/tools.html): dependency, UI, HTTP operations, URI templates, and metadata.
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): root discovery, collection/item/search resources, media types, and HTTP methods.
- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html): self/next/prev links, URI templates, and page metadata.
- [Spring Data REST — Metadata](https://docs.spring.io/spring-data/rest/reference/metadata.html): profiles and ALPS for repositories.
- [Spring Data REST — Configuring the REST URL Path](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html): using path and rel, finder resources, and hiding resources.
- [Spring HATEOAS — Link API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html): isTemplated, getVariableNames, and expand.
- [Spring HATEOAS — UriTemplate API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/UriTemplate.html): creating, listing variables, and expanding URI templates.
