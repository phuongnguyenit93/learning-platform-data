# Resource Deletion Mutations

In GraphQL, a resource deletion mutation is a command requesting the server to remove or mark a resource as inactive—for example, deleting a book, canceling a draft order, or removing a shipping address. With Spring for GraphQL, fields in the `Mutation` root type are mapped to Java methods using `@MutationMapping`; the method typically delegates the operation to a service to verify permissions, enforce data constraints, and perform the change within a transaction.

Designing a deletion mutation requires clearly answering three questions: which resource is being deleted, what conditions permit deletion, and what information the client receives once the operation finishes. Deleting a single row of data is often straightforward in code, yet it can affect relationships, history, audit trails, and other business processes.

## 1. Declaring a Deletion Mutation in SDL

Suppose a library application allows deleting a book by ID. A minimal schema:

```graphql
type Mutation {
    deleteBook(id: ID!): Boolean!
}
```

The `deleteBook` field takes a required ID and returns a non-null Boolean. Such a contract may suffice if the client only needs to know whether the operation succeeded or failed. However, a Boolean does not tell the client which ID was deleted, why the resource could not be deleted, or which list to update.

In real-world APIs, a payload is usually more helpful:

```graphql
type Mutation {
    deleteBook(id: ID!): DeleteBookPayload!
}

type DeleteBookPayload {
    deleted: Boolean!
    deletedId: ID
    userErrors: [UserError!]!
}

type UserError {
    code: String!
    message: String!
}
```

This payload is always returned when the command is handled according to expected business outcomes. When deletion succeeds, `deleted` is `true`, `deletedId` holds the deleted ID, and `userErrors` is empty. When the resource does not exist or fails deletion conditions, `deleted` is `false`, `deletedId` is null, and `userErrors` describes the issue safely for the client to handle.

`DeleteBookPayload!` promises that the mutation always returns a payload. Therefore, do not return null from the resolver for predictable failures; construct a payload with an explicit status. Unexpected failures like an unavailable database or programming bugs can still go through the GraphQL error channel.

## 2. Client Sending the Mutation Operation

The client invokes the mutation using a named operation and selects the needed fields from the payload:

```graphql
mutation DeleteBook($id: ID!) {
    deleteBook(id: $id) {
        deleted
        deletedId
        userErrors {
            code
            message
        }
    }
}
```

Variables:

```json
{
  "id": "book-42"
}
```

Response on successful deletion:

```json
{
  "data": {
    "deleteBook": {
      "deleted": true,
      "deletedId": "book-42",
      "userErrors": []
    }
  }
}
```

Response when the book is not found:

```json
{
  "data": {
    "deleteBook": {
      "deleted": false,
      "deletedId": null,
      "userErrors": [
        {
          "code": "BOOK_NOT_FOUND",
          "message": "Book to delete not found."
        }
      ]
    }
  }
}
```

The client can rely on `deleted` to update the UI, use `deletedId` to remove the item from caches or lists, and display errors from `userErrors`. Never let clients infer success solely from an HTTP success status; GraphQL can return an HTTP success response while the body still contains `errors` or a failed business outcome.

## 3. Mapping the Mutation with @MutationMapping

Spring for GraphQL maps a controller method to a matching field on the `Mutation` root type using `@MutationMapping`.

```java
package com.example.graphql.book;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public DeleteBookPayload deleteBook(@Argument("id") String id) {
        return bookService.deleteBook(id);
    }
}
```

The `deleteBook` method maps to the `Mutation.deleteBook` field. `@Argument("id")` extracts the ID sent by the client. Using `String` for IDs makes clear that a GraphQL `ID` is passed across the API as an identifier value; the service can convert it to an internal key type if the system uses UUIDs or numeric IDs.

If the method name differs from the field name, specify the name explicitly:

```java
@MutationMapping(name = "deleteBook")
public DeleteBookPayload remove(@Argument("id") String id) {
    return bookService.deleteBook(id);
}
```

The controller simply accepts input and calls the service. Avoid placing all authorization, data relationship, and transaction logic inside the controller, because the same business logic may be invoked from REST endpoints, background jobs, or other internal workflows.

## 4. Placing Deletion Rules in Services and Transactions

Simple example with Spring Data JPA:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<BookEntity, String> {
}
```

Payload DTO:

```java
import java.util.List;

public record UserError(String code, String message) {}

public record DeleteBookPayload(
    boolean deleted,
    String deletedId,
    List<UserError> userErrors
) {}
```

Service:

```java
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {

    private final BookRepository bookRepository;
    private final BookAuthorizationService authorizationService;

    public BookService(
            BookRepository bookRepository,
            BookAuthorizationService authorizationService) {
        this.bookRepository = bookRepository;
        this.authorizationService = authorizationService;
    }

    @Transactional
    public DeleteBookPayload deleteBook(String id) {
        BookEntity book = bookRepository.findById(id).orElse(null);

        if (book == null) {
            return new DeleteBookPayload(
                false,
                null,
                List.of(new UserError(
                    "BOOK_NOT_FOUND",
                    "Book to delete not found."
                ))
            );
        }

        authorizationService.checkCanDelete(book);
        bookRepository.delete(book);

        return new DeleteBookPayload(true, id, List.of());
    }
}
```

`@Transactional` sets the transaction boundary across loading the resource, checking conditions, and deleting data. If deleting violates a database constraint or fails during commit, the transaction rolls back and the error propagates to GraphQL execution. In production code, adapt the ID type, entity, and repository to your application's data model.

Do not blindly call `deleteById(id)` if business rules require checking permissions or deletion preconditions on the entity. Loading the resource first lets the service inspect ownership, status, relationships, and record appropriate audit entries before mutating data.

## 5. Checking Permissions Before Deletion

Knowing a resource's ID does not mean the user has permission to delete that resource. The server must obtain the caller's identity from the authenticated security context and verify permissions against the loaded object itself.

Authorization service example:

```java
@Service
public class BookAuthorizationService {

    public void checkCanDelete(BookEntity book) {
        // Retrieve the current principal from the security context.
        // Check roles or resource ownership.
        // Throw AccessDeniedException if not permitted.
    }
}
```

This illustrates where to place the check; the exact implementation depends on how the application configures Spring Security and its permission model. Never accept `ownerId` from the client and trust it to authorize deletion. Clients can edit variables and invoke the GraphQL endpoint directly.

For sensitive data, consider how to handle `NOT_FOUND` versus `FORBIDDEN`. If revealing that an ID exists while the user lacks access could leak information, the API may return the same not-found result for both cases. This policy must stay consistent with the system's security model.

Do not rely on directives, aliases, or hiding a delete button in the UI as an authorization mechanism. Permissions must be enforced server-side at the resolver/service or appropriate data access boundary.

## 6. Hard Delete vs. Soft Delete

Deleting a resource can carry two distinct meanings.

| Approach | Behavior | Best suited when |
| --- | --- | --- |
| Hard delete | Removes the record from the database or primary data store | The resource can be permanently discarded with no recovery needed |
| Soft delete | Marks the resource as deleted, e.g., `deletedAt` or `status = DELETED` | Audit trails, recovery, history retention, or retention policies are required |

Hard delete does not automatically delete all related data safely. Foreign keys may block the operation, cascades may wipe unintended records, and audit or historical rows may need to remain. Evaluate constraints and lifecycles of related resources before enabling cascades.

Soft delete must be applied consistently across read queries. If you only set `deletedAt` while regular queries still return deleted resources, clients may continue seeing invalid records. Define default filtering, access permissions for deleted records, restoration capabilities, and how unique constraints behave.

Soft delete service example:

```java
@Transactional
public DeleteBookPayload softDeleteBook(String id) {
    BookEntity book = bookRepository.findById(id).orElse(null);
    if (book == null || book.isDeleted()) {
        return new DeleteBookPayload(
            false,
            null,
            List.of(new UserError("BOOK_NOT_FOUND", "Book to delete not found."))
        );
    }

    authorizationService.checkCanDelete(book);
    book.markDeleted();
    return new DeleteBookPayload(true, id, List.of());
}
```

This snippet assumes the entity has `isDeleted()` and `markDeleted()` methods to update state. With soft delete, the repository does not call `delete`; the change is saved through the transaction on the managed entity.

## 7. Handling Non-Existent Resources and Business Errors

The API must clearly define what happens when a client tries to delete a non-existent ID. Two common contracts exist:

**Return a business outcome payload:** return `deleted: false` with `userErrors` as in the earlier example. This works well when resource-not-found is an expected outcome the UI should handle gracefully.

**Return a GraphQL error:** throw a business exception and use `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver` to translate it into a GraphQL error with a stable code. This fits when the API treats not-found as a command execution failure.

Avoid returning both a failure payload and a GraphQL error for the same expected failure without a clear reason. Pick one consistent error contract so clients do not have to handle two error channels for a single scenario.

Unexpected system errors like database timeouts, lost connections, or programming bugs should normally go through GraphQL `errors`. Responses may include partial `data` depending on field position and nullability. Client-facing error messages must never expose SQL, stack traces, file paths, or infrastructure details.

When using payloads, define stable error codes such as `BOOK_NOT_FOUND`, `BOOK_CANNOT_BE_DELETED`, or `BOOK_HAS_ACTIVE_LOANS`. Clients can branch on `code`, while user-facing messages can vary by language.

## 8. Checking Relationship Constraints and Business Preconditions

A resource may still be referenced by other data. For example:

- A book is part of an unreturned loan.
- A category is actively used by products.
- A user owns unfinished orders.
- A file is referenced by an active processing workflow.

Before deleting, the service must check these business preconditions. Do not rely solely on whether the database permits deletion; foreign keys are the last line of defense, not a substitute for clear business error messages.

Example:

```java
if (loanRepository.existsActiveLoanForBook(id)) {
    return new DeleteBookPayload(
        false,
        null,
        List.of(new UserError(
            "BOOK_HAS_ACTIVE_LOANS",
            "Cannot delete a book with active unfinished loans."
        ))
    );
}
```

Relationship checks must run within a consistency boundary matching the deletion operation. If concurrent updates can occur, checking first and deleting afterward may not suffice. Consider transaction isolation, locking, or database constraints depending on the invariant's criticality.

## 9. Retries, Idempotency, and Repeated Deletions

Clients may resend a mutation on timeout or connection loss, even when the server already completed the deletion before the response reached the client. Therefore, define what happens when the same command arrives multiple times.

For simple deletions, choose one of two contracts:

- The first deletion succeeds; subsequent attempts return `BOOK_NOT_FOUND`.
- If the resource no longer exists, treat the desired state as achieved and return success under an idempotent API policy.

Both approaches can be valid depending on business rules. What matters is that clients know how repeated outcomes behave. For deletions triggering refunds, notifications, or side-effect events, introduce an idempotency key or event deduplication so retries do not repeat side effects.

GraphQL does not automatically make mutations idempotent. Operation names, aliases, or serial mutation execution do not stop clients from resending requests.

## 10. Serial Mutations Do Not Make an Entire Operation One Transaction

Top-level mutation fields within a single GraphQL operation execute serially in the order they appear. For example:

```graphql
mutation {
    removeDraft: deleteBook(id: "book-1") {
        deleted
    }
    removeOldCopy: deleteBook(id: "book-2") {
        deleted
    }
}
```

The second field executes after the first field. However, GraphQL does not automatically wrap the entire operation in a database transaction. If the first field deletes successfully and the second fails, the first change is not rolled back automatically.

If business rules require multiple steps to be atomic, design a single mutation command—such as `deleteCollection`—and execute the steps within one transaction/service workflow. Transaction boundaries belong to the business and persistence layers, not to the `mutation` keyword.

## 11. Returning a Payload Snapshot After Deletion

Another option is returning the deleted object itself:

```graphql
type Mutation {
    deleteBook(id: ID!): Book
}
```

This can be convenient for clients, but note: after deletion, the GraphQL runtime still resolves any fields the client selected on the returned object. If those fields issue further database queries or depend on deleted relationships, the response may fail or trigger unnecessary queries.

For delete commands, a snapshot payload is usually clearer:

```graphql
type DeleteBookPayload {
    deleted: Boolean!
    deletedId: ID
    deletedTitle: String
    userErrors: [UserError!]!
}
```

The service can capture the ID and title before deleting and return those values. The client receives enough information to update its UI without resolving a deleted entity.

Include only truly necessary data in the payload. Never return the entire entity if it could expose sensitive data or fields that are no longer meaningful after deletion.

## 12. Testing Deletion Mutations with GraphQlTester

`GraphQlTester` lets you execute mutations and verify payloads. Example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest(BookMutationController.class)
class BookMutationControllerTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void deletesBookAndReturnsPayload() {
        graphQlTester.document("""
                mutation DeleteBook($id: ID!) {
                    deleteBook(id: $id) {
                        deleted
                        deletedId
                        userErrors {
                            code
                        }
                    }
                }
                """)
            .variable("id", "book-42")
            .execute()
            .path("deleteBook.deleted")
            .entity(Boolean.class)
            .isEqualTo(true);
    }
}
```

This example assumes the test context provides a mock or test `BookService` bean returning a success payload for ID `book-42`. Add tests for non-existent resources, insufficient permissions, resources blocked by active relationships, database errors, and retries.

In integration tests, verify that data is actually deleted or soft-deleted in the database, that transactions roll back on failure, and that read queries no longer return deleted resources according to policy. Isolated controller tests only verify mapping and responses; they do not prove persistence changed correctly.

## 13. Common Mistakes When Designing Deletion Mutations

| Issue | Consequence | Resolution |
| --- | --- | --- |
| Calling `deleteById` without permission checks | May delete another user's resource | Load the resource and enforce authorization first |
| Returning Boolean for multi-state business logic | Clients cannot tell why deletion failed | Use a payload with stable error codes |
| Returning null for a non-null payload | GraphQL raises a non-null execution error | Always return a valid payload for expected outcomes |
| Ignoring foreign keys and relationships | Deletion fails or orphans/destroys related data | Define cascade rules and invariants |
| Hard-deleting when audit/restore is needed | Cannot recover or trace history fully | Consider soft delete and audit logging |
| Assuming serial mutations form a transaction | Partial changes may commit before a later step fails | Place transactions in the business service |
| Not defining retry behavior | Clients cannot handle repeated outcomes safely | Specify idempotency and deduplicate side effects |
| Returning the deleted entity with nested fields | Child resolvers may query data that no longer exists | Return a minimal snapshot payload |
| Testing only the response | Unknown whether database state changed properly | Add integration tests for persistence and rollback |

## 14. Pre-Release Checklist for Deletion Mutations

- Does the field name clearly describe the resource and delete action?
- Is the ID non-null and validated for format at the right layer?
- Does the schema specify payload structure, nullability, and the error contract?
- Does the service verify resource existence and permissions on that resource?
- Have business conditions, relationships, and foreign keys been accounted for?
- Has hard delete versus soft delete been decided?
- Does the transaction cover all changes requiring consistency?
- Is behavior clear when a request is retried or deleted twice?
- Does the payload contain only safe, necessary information post-deletion?
- Are there tests for success, not found, forbidden, conflict, and rollback?

Resource deletion mutations in Spring for GraphQL start from a field on the `Mutation` root type mapped with `@MutationMapping`. Resolvers should forward commands to services to verify permissions, business preconditions, and perform deletions inside transactions. A payload with clear status and error codes makes UI updates straightforward, while choosing between hard and soft delete, handling retries, and protecting data relationships keep operations safe in production.
