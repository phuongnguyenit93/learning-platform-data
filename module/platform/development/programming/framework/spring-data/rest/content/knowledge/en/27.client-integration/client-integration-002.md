# Executing a Spring Data REST Operation Flow with curl or Postman

## Objectives

This hands-on guide walks a REST client through discovering a Spring Data REST API and performing a common sequence of operations on an exported repository: reading the root resource, reading a collection, creating an item, reading an item, partially or fully updating it, searching, paging, sorting, and deleting. The examples use the people collection and Person entity from the Spring Getting Started Guide; substitute relation names, JSON fields, and URIs with the actual values returned by your API.

After this lesson, you will be able to:

- Discover endpoints through HAL links rather than guessing paths.
- Send the proper HTTP method, Content-Type, Accept, and JSON body.
- Use Location or _links.self to continue a request sequence.
- Distinguish PUT full-resource replacement from PATCH partial updates.
- Use curl in the terminal or build a Postman collection with variables and response checks.
- Recognize common HTTP errors during client integration.

## 1. Preparation

Assume the application is running at http://localhost:8080 and the repository is exported under the relation people, corresponding to the collection URI /people. If the application configures a base path such as /api, set the base URL to http://localhost:8080/api. Do not assume every repository has the /people path: Spring Data REST derives collection paths from the domain type name and allows overriding the path with @RepositoryRestResource.

Spring Data REST uses HAL as its default hypermedia format. Responses typically contain:

- _links: links to collections, items, search, profile, and related resources.
- _embedded: embedded resources, such as the people list in a collection response.
- page: pagination metadata when the endpoint returns a Page.

Commonly used headers:

| Header | Purpose |
|---|---|
| Accept: application/hal+json | Requests the response in HAL JSON format |
| Content-Type: application/json | Declares the request body is JSON |
| Content-Type: text/uri-list | Sends URIs when linking an association |
| Authorization | Sends credentials if the API enables Spring Security |

In Windows PowerShell, invoke curl.exe explicitly because curl may be an alias for Invoke-WebRequest. The commands below use PowerShell syntax and the $baseUrl variable. On Linux/macOS, replace curl.exe with curl and use shell-appropriate quoting.

~~~powershell
$baseUrl = "http://localhost:8080"
~~~

If the application has a base path, update that variable before running the commands.

## 2. Discovering the API from the root resource

Start with a GET request to the root URI:

~~~powershell
curl.exe -i -H "Accept: application/hal+json" "$baseUrl/"
~~~

A sample response may contain the people relation:

~~~json
{
  "_links": {
    "people": {
      "href": "http://localhost:8080/people{?page,size,sort*}",
      "templated": true
    },
    "profile": {
      "href": "http://localhost:8080/profile"
    }
  }
}
~~~

Read the href of the people relation to learn the collection URI. In this example, the URI is /people. If the relation or path differs, use the exact href returned by the server. For long-term client integration, follow HAL links instead of hardcoding paths or inferring collection names.

## 3. Operation sequence with curl

### 3.1. Reading the collection

~~~powershell
curl.exe -i -H "Accept: application/hal+json" "$baseUrl/people"
~~~

A collection response typically includes _embedded.people, self, profile, and search links, and a page object. If the collection is empty, the people array may be empty or absent, while navigation links can still appear.

### 3.2. Creating an item with POST

Sample body based on Person from the Spring guide:

~~~powershell
$createBody = '{"firstName":"Frodo","lastName":"Baggins"}'
curl.exe -i -X POST "$baseUrl/people" -H "Content-Type: application/json" -H "Accept: application/hal+json" --data-raw $createBody
~~~

Expected result:

- HTTP 201 Created.
- The response includes a Location header containing the URI of the newly created item.
- If the server returns a representation, the body typically contains _links.self.href and the Person data.

For example, Location might be http://localhost:8080/people/1. The actual ID is assigned by the datastore; always take Location or _links.self.href from the response. Store that URI in a variable for subsequent steps:

~~~powershell
$itemUrl = "http://localhost:8080/people/1"
~~~

Replace the example value with the actual Location.

### 3.3. Reading the newly created item

~~~powershell
curl.exe -i -H "Accept: application/hal+json" "$itemUrl"
~~~

Verify status 200 OK, the firstName and lastName data, and the self link. Use the item's URI for the remaining operations.

### 3.4. Partially updating with PATCH

PATCH applies only the fields included in the body. For example, change firstName while preserving lastName:

~~~powershell
$patchBody = '{"firstName":"Bilbo Jr."}'
curl.exe -i -X PATCH "$itemUrl" -H "Content-Type: application/json" -H "Accept: application/hal+json" --data-raw $patchBody
~~~

Then GET the item again to confirm firstName changed and lastName is still Baggins. Spring Data REST supports application/json for PATCH; the media types application/hal+json, application/patch+json, and application/merge-patch+json are also supported.

### 3.5. Replacing the entire resource with PUT

PUT replaces the state of the resource with the submitted representation. Send all fields that should be kept:

~~~powershell
$putBody = '{"firstName":"Bilbo","lastName":"Baggins"}'
curl.exe -i -X PUT "$itemUrl" -H "Content-Type: application/json" -H "Accept: application/hal+json" --data-raw $putBody
~~~

Omitting a field from a PUT body can set that field to null under replacement semantics. Use PATCH when you only want to change a subset of fields. GET the item again to confirm the updated data.

### 3.6. Discovering and calling the search resource

Read the search link from the collection response or call the search URI returned by HAL:

~~~powershell
curl.exe -i -H "Accept: application/hal+json" "$baseUrl/people/search"
~~~

If the repository defines finder findByLastName with @Param("name"), the search response may expose a URI template such as /people/search/findByLastName{?name}. Call the finder with query parameters:

~~~powershell
curl.exe -i -H "Accept: application/hal+json" "$baseUrl/people/search/findByLastName?name=Baggins"
~~~

Finder name, path, and parameters depend on the repository interface and @RestResource annotations. If the link does not appear, check that the repository declares the finder and that the method is exported.

### 3.7. Paging and sorting

The collection supports the page, size, and sort query parameters if the repository supports paging/sorting:

~~~powershell
curl.exe -i -H "Accept: application/hal+json" "$baseUrl/people?page=0&size=5&sort=lastName,asc"
~~~

- page is 0-based.
- size is the maximum number of items per page.
- sort uses the format field-name,asc or field-name,desc.

Paginated responses contain page metadata and next, prev links when applicable. Follow the href of next/prev to navigate pages. In the shell, quote the full URI if the URL contains &.

### 3.8. Deleting an item

~~~powershell
curl.exe -i -X DELETE "$itemUrl"
~~~

With the default configuration that does not return a body on DELETE, a successful response is typically 204 No Content. Depending on configuration and Accept header, the server may return 200 OK with a representation. Call GET on the item URI again to confirm the resource was deleted; the expected result is usually 404 Not Found.

### 3.9. Linking associations (if the domain has relationships)

An item response may contain links to associations, such as _links.customer.href. Use the exact href from the response to get the association URI. For a to-one association, send the URI of the target resource using PUT and Content-Type text/uri-list:

~~~powershell
$customerUri = "http://localhost:8080/customers/42"
curl.exe -i -X PUT "$baseUrl/orders/1/customer" -H "Content-Type: text/uri-list" --data-raw $customerUri
~~~

For a collection association, POST adds an item to the association; DELETE removes the link. The path /orders/1/customer is only an example; replace it with the actual association URI. For a to-one association, sending multiple URIs may result in 400 Bad Request.

## 4. Running the same sequence in Postman

Create a Collection, e.g. Spring Data REST - Client Flow, and set Collection Variables:

| Variable | Initial value |
|---|---|
| baseUrl | http://localhost:8080 |
| peopleUrl | leave blank |
| itemUrl | leave blank |

If the API has a base path, include it in baseUrl. Each request should set Accept: application/hal+json. Requests with a JSON body need Content-Type: application/json.

### Request 1 — Discover root

- Method: GET
- URL: {{baseUrl}}/
- Header: Accept = application/hal+json

In the Post-response tab, save the href of the people relation:

~~~javascript
const body = pm.response.json();

pm.test("Root returns people relation", function () {
    pm.response.to.have.status(200);
    pm.expect(body._links.people.href).to.be.a("string");
});

pm.collectionVariables.set("peopleUrl", body._links.people.href);
~~~

If the relation is renamed via @RepositoryRestResource, replace people with the exact key in _links.

### Request 2 — Read collection

- Method: GET
- URL: {{peopleUrl}}
- Header: Accept = application/hal+json

Check status 200 and the _embedded, _links, and page structure. If you need an existing item from the collection, you can store _links.self.href of the first element:

~~~javascript
const body = pm.response.json();
const items = body._embedded?.people ?? [];

if (items.length > 0) {
    pm.collectionVariables.set("itemUrl", items[0]._links.self.href);
}
~~~

### Request 3 — Create item

- Method: POST
- URL: {{peopleUrl}}
- Headers: Content-Type = application/json; Accept = application/hal+json
- Body: select raw, JSON

~~~json
{
  "firstName": "Frodo",
  "lastName": "Baggins"
}
~~~

Post-response script:

~~~javascript
pm.test("POST creates item successfully", function () {
    pm.response.to.have.status(201);
});

const location = pm.response.headers.get("Location");
pm.expect(location).to.be.ok;
pm.collectionVariables.set("itemUrl", location);
~~~

The script saves Location to itemUrl so subsequent requests operate on the same resource. If the server does not return Location due to custom configuration, read href from _links.self in the response body.

### Request 4 — Read item

- Method: GET
- URL: {{itemUrl}}
- Header: Accept = application/hal+json

Check status 200 and the item data. If the POST request has not run yet or did not save itemUrl, the variable will be empty and the request cannot be routed properly.

### Request 5 — PATCH item

- Method: PATCH
- URL: {{itemUrl}}
- Headers: Content-Type = application/json; Accept = application/hal+json
- Body:

~~~json
{
  "firstName": "Bilbo Jr."
}
~~~

Post-response script:

~~~javascript
pm.test("PATCH succeeds", function () {
    pm.expect(pm.response.code).to.be.oneOf([200, 204]);
});
~~~

Call GET on the item after PATCH to confirm the target field changed and other fields remain intact.

### Request 6 — PUT item

- Method: PUT
- URL: {{itemUrl}}
- Headers: Content-Type = application/json; Accept = application/hal+json
- Body: send all fields that should be kept.

~~~json
{
  "firstName": "Bilbo",
  "lastName": "Baggins"
}
~~~

Read the item again to confirm the new representation. Do not send a single-field body if the intent is to preserve the remaining fields.

### Request 7 — DELETE item

- Method: DELETE
- URL: {{itemUrl}}

Post-response script:

~~~javascript
pm.test("DELETE succeeds", function () {
    pm.expect(pm.response.code).to.be.oneOf([200, 204]);
});
~~~

Then send GET {{itemUrl}}. The expected result is 404 Not Found. You can keep itemUrl in collection variables for the post-delete check; if you want to run the collection again from the start, rerun the POST request to create a new item.

### Running in order

In the Collection Runner, order requests as: root, collection, POST, GET item, PATCH, GET item, PUT, GET item, DELETE, GET after delete. Collection variables updated by Post-response scripts are used by subsequent requests. If running requests manually, you must still run root before POST to populate peopleUrl, and POST before item requests to populate itemUrl.

If the API requires authentication, configure Authorization in the collection or environment Authorization tab. Avoid writing real tokens into examples, shared collection files, or test scripts.

## 5. Checking results and status codes

| Operation | Typical result | What to verify |
|---|---|---|
| GET root | 200 OK | Contains _links to collections |
| GET collection | 200 OK | Contains _embedded, _links, and page if paginated |
| POST collection | 201 Created | Contains Location of the new item |
| GET item | 200 OK | Valid item URI and expected body |
| PATCH item | 200 OK or 204 No Content | Only the submitted fields are updated |
| PUT item | 200 OK or 204 No Content | Entire representation is replaced |
| DELETE item | 200 OK or 204 No Content | Item is deleted |
| GET item after DELETE | 404 Not Found | Resource no longer exists |

Success codes for PUT, PATCH, and DELETE depend on returnBodyOnUpdate/returnBodyOnDelete configuration and the Accept header. Do not treat a 204 response as an error just because the body is empty. For POST, use Location to locate the new resource if no body is returned.

## 6. Common errors and troubleshooting

| Symptom | Common cause | How to check and fix |
|---|---|---|
| GET root or collection returns 404 | Wrong host, port, base path, or relation path | Call the correct root URI, read _links, and use the href returned by the server |
| POST returns 405 Method Not Allowed | Repository does not export save or collection does not support POST | Check that the repository extends CrudRepository/JpaRepository and save is not hidden by @RestResource(exported = false) |
| PUT/PATCH returns 405 | Repository save method is not exported or endpoint is not an item resource | Call the item URI from _links.self; check method export configuration |
| DELETE returns 405 | Delete method is not exported | Check the repository interface and supported methods configuration |
| 400 Bad Request | Malformed JSON, wrong field name, or invalid body | Check raw body, data types, and validation response |
| 415 Unsupported Media Type | Content-Type does not match body or association | Use application/json for JSON body; use text/uri-list for association URI |
| POST succeeds without a body | Server does not enable return body or request lacks Accept | Read Location response header and GET that URI; add Accept if a representation is needed |
| PUT wipes out other fields | PUT body does not include all fields | Send the full representation or use PATCH for partial updates |
| Postman reports URL has empty variable | Root/POST request has not run or script did not find relation/Location | Check Post-response script, relation name, and response headers/body |
| Query fails in curl | URL containing & is unquoted or wrong parameter name | Quote the full URI and compare against the URI template in the search link |
| 401 Unauthorized or 403 Forbidden | Missing credentials or user lacks permission | Check login mechanism, token, roles, and Spring Security configuration |

Debugging rules of thumb:

- Inspect status line, response headers, and body together using curl.exe -i.
- Use Content-Type to describe the body being sent; use Accept to describe the response expected.
- Follow _links.self.href and Location instead of guessing IDs.
- Collection names in _embedded can differ from Java class names because relations are configurable.
- If a link has templated: true, populate query parameters per the URI template before calling it.
- Inspect the actual request body in the Postman Console when encountering serialization or environment variable issues.
- Never send a JSON object to an association endpoint expecting text/uri-list.

## 7. Lab completion checklist

- [ ] Application is running and base URL points to the right service.
- [ ] GET root returns HAL with required relations.
- [ ] Client retrieves collection URI from _links.
- [ ] GET collection returns representation and pagination metadata.
- [ ] POST creates an item and client stores Location or _links.self.href.
- [ ] GET item retrieves the newly created data.
- [ ] PATCH updates only the submitted fields.
- [ ] PUT replaces the entire representation matching the body.
- [ ] Search and paging/sorting use the proper URI template or query parameters.
- [ ] DELETE removes the item and a subsequent GET confirms 404.
- [ ] If associations exist, client sends URIs with text/uri-list.
- [ ] Postman collection variables are set and the request sequence runs in order.

## Official references

1. [Spring Getting Started — Accessing JPA Data with REST](https://spring.io/guides/gs/accessing-data-rest/): complete curl examples for GET root, GET collection, POST, GET item, search, PUT, PATCH, and DELETE.
2. [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): discoverability via HAL, collection/item resources, HTTP methods, status codes, and media types.
3. [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html): page, size, sort, and next/prev links.
4. [Spring Data REST — Tools / HAL Explorer](https://docs.spring.io/spring-data/rest/reference/tools.html): inspecting HAL responses, navigating URI templates, and executing GET/POST/PUT/PATCH/DELETE via the UI.
5. [Spring Data REST — Using cURL to talk to Spring Data REST](https://docs.spring.io/spring-data/rest/reference/introduction/example-api-usage-with-curl.html): guide index for interacting with Spring Data REST via curl.
