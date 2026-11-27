# URI Templates, the templated Property, and Parameter Substitution

## Objectives

After this lesson, you will be able to:

- Recognize a URI template in a HAL link.
- Explain the meaning of the **templated** property.
- Distinguish a link with a complete URL from a link that still has variables to fill in.
- Read path and query variables using URI Template syntax.
- Fill in values, encode parameters, and call endpoints properly.
- Apply the link discovery workflow to Spring Data REST paged collections and search resources.

## 1. Why Can a HAL Link Contain a URI Template?

HATEOAS guides clients to discover an API through links returned by the server. In HAL, each link usually has a relation name and an **href** property. The client uses the relation name to find the link matching its purpose, then follows the URL in **href**.

There are two situations:

**A complete link** already contains enough information to call:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/members"
    }
  }
}
~~~

**A URI template** describes a URL that still has variables to be supplied by the client:

~~~json
{
  "_links": {
    "members": {
      "href": "http://localhost:8080/api/members{?page,size}",
      "templated": true
    }
  }
}
~~~

In the second example, the server indicates that the client can choose the page and page size. Concrete values have not yet been attached to the URL. The client must expand the template with appropriate values before sending the HTTP request.

URI templates allow one link to describe many requests sharing the same structure. For example, a single **members** relation can lead to the first page, the next page, or a page with different sorting without requiring the server to emit a separate relation for every parameter combination.

## 2. Meaning of the templated Property

In HAL, **templated** is a boolean property of a link.

| Value | Meaning |
|---|---|
| **true** | **href** is a URI template; it has variables that must be expanded before calling |
| **false** or omitted | **href** is a complete URI that can be used directly |

Example of a templated link:

~~~json
{
  "href": "http://localhost:8080/api/members{?page,size}",
  "templated": true
}
~~~

Example of a regular link:

~~~json
{
  "href": "http://localhost:8080/api/members?page=0&size=20"
}
~~~

**templated** is not a parameter name, does not indicate whether the server has already executed a query, and is not an endpoint enable/disable flag. It simply tells the client how to interpret **href**.

A HAL client should inspect this property instead of guessing from whether the URL contains curly braces. When a link is marked **templated: true**, use a compliant URI template processor to expand it.

## 3. Common URI Template Syntax

URI Templates use curly braces to mark variables. The expressions commonly seen in Spring Data REST are:

| Syntax | Meaning | Illustrative result |
|---|---|---|
| **{id}** | Substitutes a variable in the path | **/members/42** |
| **{?page,size}** | Starts a query string with the supplied variables | **?page=0&size=10** |
| **{&sort}** | Appends a variable to an existing query string | **&sort=name,asc** |

### Path variables

Template:

~~~text
/api/members/{id}
~~~

If the client supplies **id = 42**, the URI expands to:

~~~text
/api/members/42
~~~

Path variables typically identify a specific resource. If a required variable's value is missing, the client does not yet have a valid URL to call.

### Query variables

Template:

~~~text
/api/members{?page,size}
~~~

If the client supplies **page = 0** and **size = 10**, the URI becomes:

~~~text
/api/members?page=0&size=10
~~~

The expression **{?page,size}** automatically inserts the leading question mark for the query string. The client does not need to append **?** manually or build each parameter by hand.

### Appending query parameters

When the URL already has a query string, the template can use the **{&sort}** expression:

~~~text
/api/members?active=true{&sort}
~~~

With **sort = name,asc**, the result is:

~~~text
/api/members?active=true&sort=name,asc
~~~

The **?** and **&** characters are template operators. Do not treat the entire expression inside curly braces as the name of a single query parameter.

## 4. Spring Data REST Generates Templates for Paged Collections

A Spring Data repository that supports paging can expose a collection resource with links for pagination and sorting parameters.

Illustrative HAL response:

~~~json
{
  "_embedded": {
    "members": []
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/members"
    },
    "members": {
      "href": "http://localhost:8080/api/members{?page,size,sort}",
      "templated": true
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

This is an example of structure and behavior; actual relation names, URLs, data, and links depend on the application's configuration and Spring Data REST version.

Common variables:

- **page**: page index; Spring Data pageable defaults to 0-based numbering.
- **size**: maximum number of elements in a page.
- **sort**: sorting property, usually in the form **property,asc** or **property,desc**.

For example, if the client wants the second page, 10 members per page, sorted by name ascending:

~~~text
/api/members?page=1&size=10&sort=name,asc
~~~

**page=1** is the second page under 0-based numbering. The server may cap the maximum page size or reject invalid sort properties; clients must handle the actual response rather than assuming all values are accepted.

## 5. Templates of Search Resources

Spring Data REST can also expose query methods under a search resource. Parameter names in the template are formed from the parameter names declared by the method.

Example repository:

~~~java
public interface MemberRepository extends JpaRepository<Member, Long> {

    List<Member> findByEmailAddress(@Param("email") String email);
}
~~~

HAL may contain a search link similar to:

~~~json
{
  "_links": {
    "findByEmailAddress": {
      "href": "http://localhost:8080/api/members/search/findByEmailAddress{?email}",
      "templated": true
    }
  }
}
~~~

The client supplies a value for the **email** variable. The expanded URI might be:

~~~text
/api/members/search/findByEmailAddress?email=lan%40example.com
~~~

The variable name must match the published query parameter name. In this example, **@Param("email")** defines that name. If the API parameter name changes, the client must use the new name published by the server.

Do not deduce search URLs solely from the Java method name. Find the relation in the HAL response and use the exact **href** and variable names returned by the template.

## 6. Expanding URI Templates in Java

Spring HATEOAS provides **UriTemplate** for expanding URI templates. The client takes the **href** string from the HAL response, passes values keyed by the exact variable names, and receives a complete URI.

~~~java
import java.net.URI;
import java.util.Map;

import org.springframework.hateoas.UriTemplate;

public class MemberLinkClient {

    public URI buildMembersUri(String href) {
        return UriTemplate.of(href).expand(Map.of(
            "page", 1,
            "size", 10,
            "sort", "name,asc"
        ));
    }

    public URI buildSearchUri(String href, String email) {
        return UriTemplate.of(href).expand(Map.of(
            "email", email
        ));
    }
}
~~~

How to call it:

~~~java
URI pageUri = buildMembersUri(
    "http://localhost:8080/api/members{?page,size,sort}"
);

URI searchUri = buildSearchUri(
    "http://localhost:8080/api/members/search/findByEmailAddress{?email}",
    "lan@example.com"
);
~~~

Corresponding output looks like:

~~~text
http://localhost:8080/api/members?page=1&size=10&sort=name,asc
http://localhost:8080/api/members/search/findByEmailAddress?email=lan%40example.com
~~~

This example focuses on the URI expansion step. Parsing HAL JSON and sending HTTP requests are handled by the HTTP client used by the application. Use a Spring HATEOAS version compatible with your project's Spring Boot version.

## 7. Workflow Clients Should Follow

When receiving a HAL response, a client can follow this workflow:

1. Select the relation matching the operation, such as **members** or **findByEmailAddress**.
2. Retrieve the link object and read **href**.
3. Check **templated**.
4. If it is a template, provide variables with the exact names and expand using a URI Template processor.
5. If it is a complete link, use **href** directly.
6. Send the request to the resulting URI and handle the status code and response body.
7. If the next response contains new links, continue discovering from that response.

The key point is that the client navigates via relations and links provided by the server. The client does not need to stitch together base URLs, endpoint names, and query parameters from scattered strings.

## 8. Encoding Values and Handling Parameters

Parameter values may contain special characters such as spaces, plus signs, **@**, **&**, or **/**. When expanding a template, the URI template library applies encoding rules appropriate for the variable's position.

Example email:

~~~text
lan@example.com
~~~

When placed in a query string, the **@** character can be encoded as **%40**:

~~~text
email=lan%40example.com
~~~

Some principles to keep in mind:

- Pass raw values to the template expansion library; avoid manually URL-encoding beforehand and letting the library encode a second time.
- Do not concatenate user-supplied values directly into URLs using string concatenation.
- Do not manually add **?** or **&** if the template already includes the corresponding query operator.
- Supply the exact variable names, proper data types, and valid values expected by the endpoint.
- If an optional variable has no value, let the URI template processor handle it according to template syntax; do not manually replace placeholders with empty strings.
- For path variables, ensure the value represents exactly one path segment; do not let input data accidentally alter the path structure.

Expanded values must still satisfy validation and constraints enforced by the server. A template allowing a variable does not mean every value is valid.

## 9. Common Mistakes

### Sending literal curly braces to the server

A request containing **/members{?page,size}** is not an expanded URI. The client must substitute variables before sending the request.

### Ignoring the templated property

If a client treats every **href** as a complete URL, requests may contain unprocessed placeholders. Check **templated** before using a link.

### Using wrong variable names

The template expects **email**, yet the client supplies **emailAddress**. The variable is not expanded as intended or the URI still contains placeholders. Take variable names directly from **href** and verify them against parameters published by the server.

### Constructing URLs manually instead of using relations

The client hard-codes **/api/members/search/findByEmailAddress** and guesses query parameters. This couples to internal URL structures and breaks easily if the server changes paths. Discover search relations from the HAL response.

### Double encoding

The client encodes the email as **%40** first, and then the template processor encodes the **%** character again. The result can contain **%2540**, causing the server to receive the wrong value. Pass unencoded values to the expansion library.

### Confusing templated with access permissions

**templated: true** does not confirm the client is allowed to call the endpoint. The server still enforces authentication, authorization, validation, and data limits as usual. URI templates are also not a place to embed passwords, access tokens, or secrets.

## 10. Practical Verification with HTTP

Suppose the API root returns the **members** relation with the template:

~~~json
{
  "href": "http://localhost:8080/api/members{?page,size,sort}",
  "templated": true
}
~~~

After expanding with **page=0**, **size=5**, **sort=name,asc**, the client calls:

~~~bash
curl -i -H "Accept: application/hal+json" \
  "http://localhost:8080/api/members?page=0&size=5&sort=name,asc"
~~~

For a templated search relation:

~~~json
{
  "href": "http://localhost:8080/api/members/search/findByEmailAddress{?email}",
  "templated": true
}
~~~

The client calls the parameterized URL:

~~~bash
curl -i -G \
  -H "Accept: application/hal+json" \
  --data-urlencode "email=lan@example.com" \
  "http://localhost:8080/api/members/search/findByEmailAddress"
~~~

The second command demonstrates sending a query parameter encoded by the HTTP tool. When testing a real API, obtain URLs and relations from that server's own HAL responses; the URLs here are examples only.

## 11. Key Takeaways

- **href** contains the address or URI template of a HAL link.
- **templated: true** tells the client to expand the template before calling.
- **{id}** typically represents a path variable; **{?page,size}** starts a query string; **{&sort}** appends a query parameter.
- Use the relation name to locate the link, then extract variable names from the template.
- Use a URI Template processor to fill in values and encode them according to the rules.
- Spring Data REST commonly uses templates for pagination, sorting, and query method parameters.
- Templated links support API discovery; they do not replace validation, authentication, or authorization.
