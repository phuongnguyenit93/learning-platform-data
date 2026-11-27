# Distinguishing 200, 201, 204, and Unsupported Method Errors in Spring Data REST

## Objectives

After this lesson, you will be able to:
- Read status codes to tell whether a request read data, updated, or created a resource.
- Distinguish a successful response with a representation from a successful response without a body.
- Recognize HTTP 405 when calling a method not supported by the endpoint or repository.
- Inspect the right URL, HTTP method, headers, and Spring Data REST configuration when encountering errors.

## 1. Starting from the resource type

Spring Data REST publishes repositories as HTTP resources. For a repository managing Person, for example:

- Collection resource: **/people**, representing the collection of Persons.
- Item resource: **/people/42**, representing a specific Person.
- Search resource: **/people/search**, providing exported query methods.
- Association resource: **/people/42/address**, representing an item's relationship.

Supported methods depend on the resource type and the methods the repository actually exports. Therefore, you cannot assume every URL accepts every HTTP method.

| Resource | Commonly supported HTTP methods | Purpose |
|---|---|---|
| Collection /people | GET, POST | Read list; create a new item |
| Item /people/{id} | GET, PUT, PATCH, DELETE | Read, replace, partially update, or delete an item |
| Search /people/search | GET | Discover and invoke query methods |
| Association | GET, PUT, POST, DELETE depending on relationship type | Read or modify links |

This is the common default configuration. Missing repository methods, methods hidden with @RestResource(exported = false), or restrictions via exposure configuration can make a method unsupported.

## 2. Meaning of the three success status codes

### 200 OK — request succeeded and has a representation

200 OK indicates that the server processed the request successfully and returned a representation in the response body.

Common scenarios:
- GET reading a collection or item succeeds.
- PUT updating an existing item and the server returns the item's representation.
- PATCH partially updating an item and the server returns the representation.
- DELETE may return 200 OK with the deleted representation if configuration and headers request a response body.

Example when reading an item:

    GET /people/42
    Accept: application/hal+json

Sample response:

    HTTP/1.1 200 OK
    Content-Type: application/hal+json

    {
      "firstName": "An",
      "lastName": "Nguyen",
      "_links": {
        "self": { "href": "http://localhost:8080/people/42" }
      }
    }

Do not interpret 200 as "newly created". For update requests, it normally means the operation succeeded and the server returned the representation.

### 201 Created — a new resource was created

201 Created confirms the server created a new resource. In Spring Data REST, common cases are:
- POST to a collection resource, such as POST /people.
- PUT creating a new resource at an item URI, if PUT-for-creation is enabled.

The response usually includes a Location header pointing to the URI of the new resource. This is key information for the client to save the path of the newly created item.

Example:

    POST /people
    Content-Type: application/json
    Accept: application/hal+json

    {
      "firstName": "An",
      "lastName": "Nguyen"
    }

Sample response:

    HTTP/1.1 201 Created
    Location: http://localhost:8080/people/42
    Content-Type: application/hal+json

    {
      "firstName": "An",
      "lastName": "Nguyen",
      "_links": {
        "self": { "href": "http://localhost:8080/people/42" }
      }
    }

The body may be returned or left empty depending on Accept and RepositoryRestConfiguration.setReturnBodyOnCreate(...). Even when the body is empty, the client can still use the URI in Location to access the newly created resource.

Do not assume every PUT returns 201: PUT updating an existing item usually returns 200 or 204; PUT returns 201 only when it actually creates a new resource and creation via PUT is allowed.

### 204 No Content — request succeeded without a body

204 No Content is still a success outcome. It means the server performed the operation without sending a representation in the response body.

In Spring Data REST, 204 commonly appears with:
- PUT updating an item when the server does not return a body.
- PATCH partially updating an item when the server does not return a body.
- DELETE deleting an item when the server does not return a body.

With default configuration, the presence of the Accept header can determine whether the server returns a body. With Accept, the server may return a representation and status 200 OK for update/delete operations; without it, a successful response is typically 204 No Content. Settings such as setReturnBodyOnUpdate(...) and setReturnBodyOnDelete(...) can alter this behavior.

Example:

    PUT /people/42
    Content-Type: application/json

    {
      "firstName": "An",
      "lastName": "Tran"
    }

The response may be:

    HTTP/1.1 204 No Content

There is no JSON body to read. Clients should not call response.json() unconditionally after a 204 response, because parsing an empty body can raise a client-side error even though the server operation succeeded.

## 3. Comparing 200, 201, and 204 by operation

| Request | Outcome | Typical status | What to check |
|---|---|---|---|
| GET collection or item | Read succeeded | 200 | Response body contains representation |
| POST collection | Created new item | 201 | Get new URI from Location header |
| PUT existing item | Replaced item state | 200 or 204 | Whether body is returned; check Accept and configuration |
| PUT item to create new | Created item at specified URI | 201 if PUT-for-creation is enabled | Check configuration allowing creation via PUT |
| PATCH item | Partially updated item | 200 or 204 | Check return-body policy |
| DELETE item | Deleted item | 200 or 204 | Check return-body policy |

Key point: the status code of PUT, PATCH, and DELETE depends on more than the HTTP method. It also depends on whether the operation created vs. updated/deleted, whether the server returns a representation, the Accept header, and Spring Data REST configuration.

## 4. 405 Method Not Allowed — URL has a resource, but the method is unsupported

405 Method Not Allowed occurs when a request uses an HTTP method that the resource does not permit.

Examples:
- Sending PUT /people: collection resources support only GET and POST by default.
- Sending DELETE /people/search: search resources are read-only resources.
- Sending PATCH /people/42 when PATCH has been disabled via exposure configuration.
- Sending POST, PUT, or PATCH when the repository does not export the save(...) method.
- Sending DELETE when the repository does not export the corresponding delete method.

Sample response:

    HTTP/1.1 405 Method Not Allowed
    Allow: GET, HEAD, POST

If the response includes an Allow header, use the list in that header to see which methods the endpoint accepts. Do not change URLs blindly or repeatedly try random methods without identifying the resource being called.

### Distinguishing 405 from 404

| Status | Meaning | How to investigate |
|---|---|---|
| 404 Not Found | Path or corresponding resource not found; item may not exist | Check base path, collection name, ID, and whether the repository is exported |
| 405 Method Not Allowed | Path is recognized, but the HTTP method is not supported | Check resource type, exported methods, and Allow header |

A completely hidden repository or resource can cause the path not to be registered and return 404. Therefore, confirm whether the URL actually points to an exported resource before concluding it is a method error.

### How to investigate the cause of 405

1. Identify the resource type: collection, item, search, or association.
2. Compare the method being sent against the default method list for that resource type.
3. Check whether the repository has the corresponding method. For example, save(...) is typically used for POST on collections and PUT/PATCH on items; delete(...) methods are used for DELETE.
4. Check whether the method or repository is hidden with @RestResource(exported = false) or @RepositoryRestResource(exported = false).
5. Check whether rules in RepositoryRestConfiguration.getExposureConfiguration() disable the method by resource type or domain type.
6. If the method was intentionally disabled, use a supported method or change the configuration according to business requirements. Do not re-enable a method just to silence a 405 if that operation should not be allowed.

For example, Spring Data REST lets you disable PATCH on item resources via exposure configuration:

    config.getExposureConfiguration()
        .withItemExposure((metadata, methods) ->
            methods.disable(HttpMethod.PATCH));

You can also separately disable creating items with PUT for a domain type using disablePutForCreation(). Disabling a method is an API exposure decision; clients must follow the published contract.

## 5. Do not confuse 405 with header or data errors

Other common errors when writing resources:

| Status | Common cause | Resolution |
|---|---|---|
| 400 Bad Request | Malformed JSON, invalid data, or invalid association URI | Check body, data types, required fields, and sent URIs |
| 406 Not Acceptable | Accept value asks for a representation the server cannot provide | Use a media type supported by the endpoint, usually application/hal+json or application/json |
| 415 Unsupported Media Type | Request body Content-Type is not supported by the endpoint | Send the right Content-Type; PATCH can use application/patch+json or application/merge-patch+json |
| 404 Not Found | URL or item does not exist, or resource is not exported | Check links, ID, and repository exposure |
| 405 Method Not Allowed | HTTP method is not supported on the resource | Check method, repository methods, and exposure configuration |

Two headers to distinguish:
- Content-Type: format of the data the client sends up. Example: application/json.
- Accept: format of the representation the client wants back. Example: application/hal+json.

A request with a valid JSON body can still fail if Content-Type is wrong. Likewise, a request can succeed yet return 204 if the client did not request a representation or the server is configured not to return a body.

## 6. Practicing with curl

Assume the application runs at http://localhost:8080 and the repository exports the /people collection.

### Creating a resource with POST

    curl -i -X POST http://localhost:8080/people -H "Content-Type: application/json" -H "Accept: application/hal+json" -d '{"firstName":"An","lastName":"Nguyen"}'

Read status 201 Created and the Location header. Use the URI in Location to read or update the new item.

### Updating a resource with PUT

    curl -i -X PUT http://localhost:8080/people/42 -H "Content-Type: application/json" -H "Accept: application/hal+json" -d '{"firstName":"An","lastName":"Tran"}'

If the item already exists and the server returns a representation, the result is usually 200 OK. If you omit the Accept header and the server is not configured to return a body on update, a successful result is usually 204 No Content.

### Partially updating with PATCH

    curl -i -X PATCH http://localhost:8080/people/42 -H "Content-Type: application/merge-patch+json" -H "Accept: application/hal+json" -d '{"lastName":"Tran"}'

PATCH changes only the sent fields according to the patch format supported by the endpoint. Check the response body and status 200 or 204 per the return-body policy.

### Deleting a resource with DELETE

    curl -i -X DELETE http://localhost:8080/people/42 -H "Accept: application/hal+json"

Depending on configuration, the server may return 200 OK with a body or 204 No Content without a body.

### Reproducing an unsupported method error

    curl -i -X PUT http://localhost:8080/people

Collection resources do not support PUT by default, so the request may receive 405 Method Not Allowed. Inspect the Allow header and switch to the endpoint/method matching your goal. To create a new item, normally send POST to the collection resource.

## 7. Checklist when reading responses

When inspecting a write operation, ask in order:

- Am I calling a collection URI or an item URI?
- Is this method supported by the resource?
- Does the repository have the corresponding method and is it exported?
- Are the request body and Content-Type valid JSON and the right media type?
- Does Accept request a representation supported by the endpoint?
- Is the status 200, 201, or 204? If 201, where does Location point?
- If 204, has the client handled the empty response properly?
- If 405, what do the Allow header and exposure configuration indicate?

Do not judge an operation solely by whether there is a JSON body. 204 is success; conversely, 200 does not mean a new resource was created.

## 8. Self-check exercises

**Scenario 1:** Client POSTs JSON to /people, receives 201 Created and Location: /people/43. What happened?

Answer: The server created a new resource. The client should store or follow the link in Location to access item /people/43.

**Scenario 2:** Client sends PUT to /people/42, receives 204 No Content. Did the update fail?

Answer: No. This can be a successful update where the server did not return a body. The client should not attempt to parse JSON from this response.

**Scenario 3:** Client sends DELETE to /people and receives 405. Why?

Answer: /people is a collection resource; the DELETE method applies by default to item resources such as /people/42, not to the collection.

**Scenario 4:** Client sends PATCH to an item URI and receives 405, even though the repository has save(...). What should be checked?

Answer: Check @RestResource(exported = false), exposure configuration, and item/domain-type rules. Having save(...) does not guarantee PATCH is exported if configuration disabled the method.

**Scenario 5:** Client receives 415 Unsupported Media Type when sending PATCH. Should it immediately switch PATCH to PUT?

Answer: Not yet. Check Content-Type. Spring Data REST supports patch media types such as application/patch+json and application/merge-patch+json; use the exact format accepted by the endpoint.

## Conclusion

- 200 OK: operation succeeded and usually includes a representation in the response body.
- 201 Created: a new resource was created; inspect the Location header.
- 204 No Content: operation succeeded with an empty response body.
- 405 Method Not Allowed: the resource does not support the sent HTTP method; check resource type, repository methods, and exposure configuration.

With Spring Data REST, identify the right resource first, then choose the HTTP method and interpret status codes. In particular, PUT/PATCH/DELETE can return 200 or 204 depending on the return-body policy; 204 is not an error.

## References

- Spring Data REST — Repository resources: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST — Customizing supported HTTP methods: https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html