# Optimistic Locking at the Data Store and HTTP Conditionals at the REST API

## 1. Objectives

When multiple clients concurrently read and update a resource, one client may accidentally overwrite newer changes made by another client. Spring Data provides **optimistic locking** to detect conflicts when saving entities. Spring Data REST connects this mechanism to HTTP conditional requests through ETag and the If-Match and If-None-Match headers.

These two layers cooperate as follows:

- **At the persistence layer:** the version field is checked on update or delete. If the data in the database has changed since the entity was read, the operation can fail.
- **At the HTTP layer:** the server returns an ETag for a versioned resource. The client sends back the ETag via If-Match when modifying the resource, so the server proceeds only if the resource is still at the version the client read.
- **For caching:** the client sends If-None-Match when re-GETting the same resource. If the ETag has not changed, the server can return 304 Not Modified without resending the representation.

The goal is to prevent lost updates and reduce data transfer when clients re-read unchanged resources.

## 2. What Is Optimistic Locking?

Optimistic locking assumes that update conflicts do not occur frequently. Instead of locking the record for the entire time a user is editing, the system stores a version marker and checks that marker on write.

Example of two clients reading Customer with version 5:

1. Client A reads version 5.
2. Client B also reads version 5.
3. Client A updates successfully; the version increments to 6.
4. Client B submits an update based on version 5 data.
5. The persistence layer detects that the version in the database is now 6, so it rejects B's write.

Without version checking, the new data written by A could be overwritten by B with an older copy. This is a lost update error.

Optimistic locking is suitable when conflicts are relatively rare and the duration users hold data for editing can be long. It avoids holding a database lock for that entire duration.

## 3. Declaring the Version Field

With Spring Data JPA, use the jakarta.persistence.Version annotation on an entity property:

    import jakarta.persistence.Entity;
    import jakarta.persistence.GeneratedValue;
    import jakarta.persistence.Id;
    import jakarta.persistence.Version;

    @Entity
    public class Customer {

        @Id
        @GeneratedValue
        private Long id;

        private String name;
        private String email;

        @Version
        private Long version;

        // getters and setters
    }

The JPA provider manages the version field. When the entity is saved successfully, the version is incremented according to the provider's mechanism. Do not manually increment the version in controllers or services; doing so can break concurrency checking.

With non-JPA Spring Data modules, you can use the org.springframework.data.annotation.Version annotation corresponding to the store module. Spring Data REST relies on the store's persistent entity metadata to recognize the version property.

Simply adding a field named version without annotating it appropriately is not enough to enable optimistic locking. The annotation must match the persistence technology in use.

## 4. How Does the Persistence Layer Check the Version?

With JPA, when updating an entity with a version, the provider generates an UPDATE statement conditioned on both the ID and the current version. Illustrative SQL:

    UPDATE customer
       SET name = ?,
           email = ?,
           version = 6
     WHERE id = 42
       AND version = 5;

If exactly one row is updated, the operation can succeed. If no rows match, the record may have been updated or deleted by another transaction. The JPA provider throws OptimisticLockException; Spring can translate this error into OptimisticLockingFailureException at the data access layer.

The SQL statement above only illustrates the principle. The actual statement, flush timing, and exception timing depend on the provider, transaction, and database.

With Spring Data JDBC/Relational, Spring Data also supports optimistic locking using a version property on the aggregate root. When the version no longer matches, the save operation can throw OptimisticLockingFailureException. Statement details depend on the store module.

In JPA, a conflict may only be detected at flush or commit. Therefore, do not assume the exception always occurs on the exact line calling save. Transaction boundaries and rollback rules determine the final state.

## 5. ETag in Spring Data REST

An ETag (Entity Tag) is an HTTP validator representing the state of a resource. Spring Data REST uses the version property recognized by store metadata to generate the ETag for the resource.

Example response:

    GET /customers/42
    Accept: application/hal+json

    HTTP/1.1 200 OK
    Content-Type: application/hal+json
    ETag: "5"

    {
      "name": "An Nguyen",
      "email": "an@example.com",
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers/42"
        }
      }
    }

The value 5 is only an illustrative example when the current version is 5. Use the exact ETag header returned by the server. Clients should treat the ETag as an opaque token and not compute or modify its contents.

When the resource changes and the version increments, the ETag returned for the new representation also changes. Clients can use this token to detect stale data.

The ETag of one item resource should not be used in place of another resource's ETag. Associate the ETag with the exact URI/resource from which the client retrieved it.

## 6. If-Match Protects PUT, PATCH, and DELETE

When a client wants to modify a resource, it sends the received ETag in the If-Match header:

    PATCH /customers/42
    Content-Type: application/merge-patch+json
    Accept: application/hal+json
    If-Match: "5"

    {
      "name": "An Nguyen Updated"
    }

The server performs the operation only if the resource's current ETag matches the If-Match value. If the resource is still at version 5, the request can be accepted and the response will carry a new ETag, for example:

    HTTP/1.1 200 OK
    ETag: "6"

If another client updated the resource earlier and the current version is 6, a request sending If-Match with the version 5 token is no longer valid. Spring Data REST returns:

    HTTP/1.1 412 Precondition Failed

This is how stale updates are detected at the HTTP boundary. The client knows the data it is editing is stale and needs to reload the resource, compare changes, and decide how to merge.

Spring Data REST also supports conditional PUT and DELETE following the same principle. Use the ETag from the most recent GET of the exact resource being modified.

Do not send the ETag of another Customer, another URL, or another query. If the API requires conditional writes, the client needs to track tokens per resource.

## 7. Scenario: Two Clients Updating Concurrently

Suppose A and B both read Customer 42:

    Client A                         Server                         Client B
       |                               |                               |
       |--- GET /customers/42 -------> |                               |
       |<-- 200, ETag: "5" ------------|                               |
       |                               | <------ GET /customers/42 ---|
       |                               | ------ 200, ETag: "5" ------->|
       |                               |                               |
       |--- PATCH, If-Match: "5" ----> |                               |
       |<-- 200, ETag: "6" ------------|                               |
       |                               |                               |
       |                               | <--- PATCH, If-Match: "5" ----|
       |                               | ------ 412 Precondition Failed|
       |                               |                               |

Client A updates first, so the version changes from 5 to 6. Client B still holds ETag 5; the server rejects B's change to avoid overwriting newer data.

After a 412, client B should:

1. Re-GET the resource to receive the new representation and ETag.
2. Compare the current data with the changes entered by the user.
3. Merge manually or according to business rules if possible.
4. Send a new request with the new If-Match once approved by the user or business logic.

Do not automatically resend the same payload with the new ETag without checking. Doing so can overwrite client A's changes and defeat the purpose of optimistic locking.

## 8. If-None-Match Helps GET Save Bandwidth

If-None-Match is used for conditional GET. The client stores the ETag received from the previous GET and sends it back when checking whether the resource has changed:

    GET /customers/42
    Accept: application/hal+json
    If-None-Match: "6"

If the current ETag still matches, the server can return:

    HTTP/1.1 304 Not Modified

A 304 response does not need to resend the resource body. The client keeps the cached representation and knows that the stored copy is still valid according to the validator.

If the resource has changed, the server returns the new representation with a success status and a new ETag:

    HTTP/1.1 200 OK
    ETag: "7"

    {
      "name": "An Nguyen Updated",
      "email": "an@example.com"
    }

Use the ETag for the exact resource and exact URI. When a request has query parameters or a different representation variant, do not arbitrarily reuse a validator taken from a different request.

## 9. Distinguishing If-Match and If-None-Match

| Header | Commonly used for | Condition | Typical outcome |
|---|---|---|---|
| If-Match | PUT, PATCH, DELETE | Modify only if the current ETag matches | Operation executes or 412 |
| If-None-Match | GET | Send representation only if ETag does not match | 200 with new body or 304 |
| If-Modified-Since | GET | Check if the resource changed after a known time | 200 with new body or 304 |

If-Match addresses update conflicts. If-None-Match primarily avoids re-downloading unchanged content. The two headers have different goals even though both use ETag.

Spring Data REST also supports Last-Modified and If-Modified-Since in appropriate conditional requests. For resources with a version property, ETag is usually the right validator for optimistic locking because it ties directly to the version marker.

## 10. Testing Examples with curl

First GET the resource and save the ETag:

    curl -i \
      -H 'Accept: application/hal+json' \
      http://localhost:8080/customers/42

Read the ETag header in the response. Suppose the server returns an ETag corresponding to version 5.

Try updating with the current version:

    curl -i -X PATCH \
      -H 'Accept: application/hal+json' \
      -H 'Content-Type: application/merge-patch+json' \
      -H 'If-Match: "5"' \
      -d '{"name":"An Nguyen Updated"}' \
      http://localhost:8080/customers/42

After a successful update, the response returns a new ETag. Try resending a request with the old ETag to simulate a stale client; the expected result under conditional behavior is 412 Precondition Failed.

Try a conditional GET with the latest ETag:

    curl -i \
      -H 'Accept: application/hal+json' \
      -H 'If-None-Match: "6"' \
      http://localhost:8080/customers/42

If the resource has not changed since ETag 6, the server can return 304 Not Modified.

The version and ETag values in the commands are examples only. Copy the actual header from the previous response. The PATCH Content-Type format must also match the endpoint configuration and media types supported by the application.

## 11. Testing Optimistic Locking at the Repository Layer

This can be tested with two transactions or two entity instances representing two clients:

1. Read the same entity in two persistence contexts.
2. Update and commit the first instance.
3. Try saving the second instance based on the old version.
4. Verify the second save fails with an optimistic locking exception.
5. Verify the final data retains the change committed first.

Conceptual test example:

    Customer first = repository.findById(id).orElseThrow();
    Customer second = repository.findById(id).orElseThrow();

    first.setName('Updated by A');
    repository.saveAndFlush(first);

    second.setName('Updated by B');

    assertThatThrownBy(() -> {
        repository.saveAndFlush(second);
    }).isInstanceOf(OptimisticLockingFailureException.class);

The test above is valid only when the two entities are read in independent persistence contexts or properly detached/refreshed. If the same persistence context returns the same object instance, the test will not simulate two independent clients.

With JPA, you can use two transactions and two EntityManagers to explicitly control version state. Flush to force the provider to execute the UPDATE and detect the conflict before the assertion completes.

## 12. ETag Integration Tests via Spring Data REST

Integration tests should verify both HTTP headers and data state.

Example test flow with MockMvc:

    MvcResult firstGet = mockMvc.perform(
            get('/customers/{id}', id)
                .accept('application/hal+json'))
        .andExpect(status().isOk())
        .andReturn();

    String etag = firstGet.getResponse()
        .getHeader(HttpHeaders.ETAG);

    assertThat(etag).isNotBlank();

Use the ETag just received to update:

    mockMvc.perform(patch('/customers/{id}', id)
            .header(HttpHeaders.IF_MATCH, etag)
            .contentType('application/merge-patch+json')
            .accept('application/hal+json')
            .content('{"name":"Updated"}'))
        .andExpect(status().is2xxSuccessful());

Obtain the new ETag after the update, then resend a request using the old ETag:

    mockMvc.perform(patch('/customers/{id}', id)
            .header(HttpHeaders.IF_MATCH, etag)
            .contentType('application/merge-patch+json')
            .content('{"name":"Stale update"}'))
        .andExpect(status().isPreconditionFailed());

Verify GET with If-None-Match:

    mockMvc.perform(get('/customers/{id}', id)
            .header(HttpHeaders.IF_NONE_MATCH, newEtag)
            .accept('application/hal+json'))
        .andExpect(status().isNotModified());

This is an illustrative skeleton. You need to create the entity before the test, use the correct PATCH media type, and verify that the endpoint and actual Spring Data REST version support those operations. Do not hard-code ETag 5 or 6; always extract the token from the response.

## 13. Common Limitations and Pitfalls

**Forgetting the version annotation**

A property named version without the proper annotation may not enable optimistic locking or ETag. Use JPA @Version for JPA and Spring Data @Version for the corresponding store module.

**Manually incrementing the version**

Do not modify the version in controllers or clients. The persistence framework manages incrementing the version after a successful operation.

**Omitting If-Match on updates**

A client sending a payload based on stale data can overwrite newer changes if conditional writes are not used. For versioned resources, retain and send the ETag from the most recent read.

**Using the wrong ETag**

An ETag is a validator for a specific representation/resource. Do not use another resource's token or construct a token manually from the version field.

**Treating 412 as a server error**

412 Precondition Failed is typically a conditional conflict that the client must handle: reload fresh data, merge changes, and resend when appropriate.

**Confusing 304 with a regular empty response**

304 Not Modified is the result of a conditional GET. The client should use the cached representation; do not parse the response as a new JSON body.

**Assuming AfterSave is always already committed**

ETag and version reflect resource state through persistence metadata. However, transaction boundaries still determine when data is committed. Do not infer a commit solely because a post-save callback ran.

**Not testing across transactions**

An optimistic locking exception may occur at flush or commit. Integration tests must run across appropriate transaction boundaries and verify rollback/persistence state.

## 14. Practice Exercises

Given a Customer resource with id, name, email, and version:

1. Add a version property with JPA @Version.
2. Start the application and GET a Customer resource.
3. Check whether the response contains an ETag header.
4. Store the ETag along with the self URI in client state.
5. Send a PATCH with If-Match set to the ETag just received.
6. Verify the update succeeds and the response returns a new ETag.
7. Send a second request with the old ETag; verify the server returns 412.
8. Re-GET the resource, compare the new data with the changes held by the client, and perform a business-level merge.
9. GET with If-None-Match set to the latest ETag; verify 304 if the resource has not changed.
10. Write a repository test simulating two persistence contexts concurrently editing the same entity.
11. Write MockMvc integration tests for success, stale update, and conditional GET.
12. Try deleting the resource using If-Match and verify an old version cannot delete a modified resource.

Self-check questions:

- How does optimistic locking detect lost updates?
- How does JPA @Version differ from Spring Data @Version in usage scope?
- How does Spring Data REST use the version property to generate an ETag?
- When should a client send If-Match?
- Why does a stale ETag result in 412?
- How does If-None-Match help reduce data transfer?
- Why should you not manually increment version or fabricate ETags?
- Why must tests simulate two independent persistence contexts or two independent clients?

## 15. Key Takeaways

- Optimistic locking detects write conflicts using a version marker.
- JPA uses jakarta.persistence.Version; other Spring Data stores can use org.springframework.data.annotation.Version.
- The persistence layer checks the version on update and increments the version on successful save.
- Spring Data REST uses the recognized version property to generate the ETag for a resource.
- PUT, PATCH, and DELETE can be made conditional using If-Match.
- A mismatched ETag results in HTTP 412 Precondition Failed.
- GET with If-None-Match can return 304 Not Modified when the resource has not changed.
- Use the exact ETag of the exact resource; do not fabricate or edit tokens.
- After 412, reload fresh data and merge changes before retrying.
- Test repository-layer exceptions, HTTP headers, and persistence state.

## References

- Spring Data REST Reference — Conditional Operations with Headers: https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html
- Spring Data Commons — Version: https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/annotation/Version.html
- Jakarta Persistence — Optimistic Locking and Version: https://jakarta.ee/specifications/persistence/
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html