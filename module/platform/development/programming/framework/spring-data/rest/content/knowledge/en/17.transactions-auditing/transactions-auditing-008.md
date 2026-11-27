# Distinguishing Data Auditing, HTTP Logs, and Business Journals

In a Spring Data REST application, data auditing, HTTP logs, and business journals can all record activity, yet they answer different questions. Data auditing shows who created or modified a record and when; HTTP logs show which request passed through the system and how the server responded; business journals record domain-meaningful actions, such as an order being confirmed or a limit being changed for a specific reason.

These three types of records complement one another. Using the right type at the right layer helps with incident investigation, traceability requirements, and explaining business history without turning a technical log line into sole proof of a business decision.

## 1. Three types of records answer three different questions

| Type | Primary question | Example |
|---|---|---|
| Data auditing | Who created or updated the record? When was it created/updated? | createdBy=alice, createdDate=2026-11-11T08:00Z, lastModifiedBy=bob. |
| HTTP/access logging | Which endpoint did the client call, when, how long did it take, and what status was returned? | POST /api/orders returned 201, duration 84 ms, requestId=abc123. |
| Business journal | What business action occurred, who performed it, which object was affected, and why? | Order 42 confirmed by alice, from DRAFT to CONFIRMED, reason: customer payment received. |

For example, when a user confirms an order:

- Data auditing can update lastModifiedBy and lastModifiedDate on the PurchaseOrder entity.
- HTTP logs record the POST /api/orders/42/confirm request, status 200, and processing duration.
- The business journal records an OrderConfirmed event with orderId=42, actor=alice, before/after state, and confirmation reason.

With data auditing alone, you know the record changed, but not precisely which business operation occurred. With HTTP logs alone, you know an endpoint was called, but not whether any change actually committed. With a business journal alone, you know the business event, yet lack request details, latency, or HTTP-layer errors.

## 2. Data auditing with Spring Data JPA Auditing

Spring Data JPA Auditing automatically populates standard metadata on entities:

- @CreatedBy: who created the record.
- @CreatedDate: when the record was created.
- @LastModifiedBy: who last updated the record.
- @LastModifiedDate: when the record was last updated.

These fields are typically stored with the entity and reflect its current audit state. They do not automatically create a complete history of every modification; lastModifiedBy and lastModifiedDate are overwritten on the next change.

Entity example:

~~~java
import java.time.Instant;

import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    private String status;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedDate;

    // getters and setters
}
~~~

To enable auditing, configure @EnableJpaAuditing and provide an AuditorAware bean so Spring knows the current user:

~~~java
@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorProvider")
public class JpaAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> {
            Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return Optional.empty();
            }

            return Optional.of(authentication.getName());
        };
    }
}
~~~

The example above retrieves the principal name from Spring Security. In real applications, use a stable user identifier such as user ID instead of a mutable display name. For background tasks, return a dedicated system identifier or explicitly allow the auditor field to remain empty; do not misattribute background work to an end user.

Auditing must be applied consistently across entities: enable configuration, attach AuditingEntityListener or equivalent setup, declare metadata fields, and ensure AuditorAware returns the right actor. If no authenticated user exists, decide explicitly how to represent the actor rather than assuming Authentication is always present.

## 3. Auditing shows who modified last, not the full history

Suppose an order is updated three times:

| Change | Actor | Status |
|---|---|---|
| Created | alice | DRAFT |
| Updated address | bob | DRAFT |
| Confirmed | carol | CONFIRMED |

After the last change, @CreatedBy and @CreatedDate still indicate who originally created the record. @LastModifiedBy and @LastModifiedDate only show the most recent modifier and timestamp.

They do not retain that bob changed the address, that carol confirmed the order, or the before/after values of individual fields. When that history is required, you need a business journal, a versioned audit table, or an appropriate history-tracking mechanism.

You can extend auditing with dedicated domain fields, but do not turn existing metadata fields into a concatenated history string. History needs its own structure for querying, reconciliation, and integrity protection.

## 4. HTTP logs record requests and responses

HTTP/access logs focus on client-server communication. Useful fields typically include:

- Request start or completion timestamp.
- HTTP method and route/path.
- Status code.
- Processing duration.
- Client address if permitted by policy.
- Request ID or trace ID to correlate logs across gateways, applications, and downstream services.
- Authenticated user ID or principal when needed for investigation and allowed by data policy.

Example access log line:

~~~text
2026-11-11T08:15:32Z requestId=abc123 method=POST
path=/api/orders/42/confirm status=200 durationMs=84
principal=user-17
~~~

This log shows that the request was handled and returned 200. It does not prove that an OrderConfirmed event was durably persisted in the database, nor does it describe before/after business state.

In Spring Boot, you can enable embedded Tomcat access logs via server properties:

~~~properties
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.directory=logs
server.tomcat.accesslog.pattern=%t %a "%r" %s %D
~~~

Exact configuration depends on the embedded server. If the application runs behind a reverse proxy or API gateway, proxy access logs are also valuable at the network boundary; propagate request/trace IDs across layers for correlation.

If application-level logging is needed, use a OncePerRequestFilter or interceptor to attach correlation IDs, principal, and standardized metadata. Measure duration properly and log status after the response is handled. Avoid logging full request/response bodies by default.

## 5. Protecting sensitive data in HTTP logs

HTTP logs often contain client-supplied data and can inadvertently capture secrets. Avoid logging directly:

- Authorization headers, access tokens, refresh tokens, or session cookies.
- Passwords, API keys, or one-time verification codes.
- Card numbers, payment details, or unnecessary personal data.
- Query parameters that may contain sensitive information.
- Entire request bodies purely for debugging convenience.

Prefer route templates over full URLs containing IDs or sensitive query parameters when unnecessary. For example, log /api/orders/{id}/confirm instead of the concrete path with an ID when policy calls for minimizing identifying data.

Establish retention policies, log read access controls, storage encryption, and expiration cleanup procedures. Logs must be sufficient for investigation without becoming a secondary secret store.

## 6. Business journals record domain-meaningful events

A business journal is a history of business actions or events that have occurred. A record typically includes:

- Unique eventId.
- eventType, such as OrderConfirmed or RefundIssued.
- aggregateType and aggregateId to identify the business object.
- actorId or systemActor.
- occurredAt: when the business event took place.
- Relevant payload such as before/after state, amount, reason, or request source.
- correlationId/requestId to link with HTTP logs.
- version or sequence if ordering events for the same aggregate is needed.

Example event:

~~~json
{
  "eventId": "evt-8f31",
  "eventType": "OrderConfirmed",
  "aggregateType": "PurchaseOrder",
  "aggregateId": "42",
  "actorId": "user-17",
  "occurredAt": "2026-11-11T08:15:32Z",
  "data": {
    "previousStatus": "DRAFT",
    "newStatus": "CONFIRMED",
    "reason": "Payment received"
  },
  "correlationId": "abc123"
}
~~~

This record captures a concrete business action. It can be used to look up history, explain why state changed, support customer service, or generate compliance reports.

Business journals should favor event names stating what happened, such as OrderConfirmed, AddressChanged, or RefundApproved. Avoid overly generic descriptions like EntityUpdated because they do not explain business intent.

## 7. Writing the business journal in the same transaction as data changes

If an order change commits while its journal entry fails to save, history will miss the event. Conversely, if the journal is written while the order change rolls back, the journal will describe an action that never actually occurred.

For critical business operations, write both the entity and the business journal within the same database transaction:

~~~java
@Service
public class OrderService {

    private final PurchaseOrderRepository orders;
    private final BusinessJournalRepository journal;

    public OrderService(
            PurchaseOrderRepository orders,
            BusinessJournalRepository journal) {
        this.orders = orders;
        this.journal = journal;
    }

    @Transactional
    public void confirm(Long orderId, String actorId, String reason) {
        PurchaseOrder order = orders.findById(orderId)
            .orElseThrow(() -> new EntityNotFoundException("Order not found"));

        String previousStatus = order.getStatus();

        if (!"DRAFT".equals(previousStatus)) {
            throw new IllegalStateException("Order cannot be confirmed");
        }

        order.setStatus("CONFIRMED");

        journal.save(BusinessJournalEntry.orderConfirmed(
            order.getId(),
            actorId,
            previousStatus,
            "CONFIRMED",
            reason,
            Instant.now()
        ));
    }
}
~~~

In the example, the status update and the journal entry participate in the same transaction. If the transaction rolls back, both database changes roll back. The journal repository save is shown via a factory method to keep the event's domain structure clear.

If messages must be sent to external systems after commit, do not invoke remote services directly mid-transaction expecting both systems to stay synchronized. Transactional outbox is one option: write an outbox record in the same transaction as the business change, then have a publisher read the outbox and deliver messages with retries. This reduces the risk of the database committing while the message is lost due to network failure.

## 8. What role do Spring Data REST repository events play?

Spring Data REST provides events such as BeforeCreateEvent, AfterCreateEvent, BeforeSaveEvent, AfterSaveEvent, BeforeDeleteEvent, and AfterDeleteEvent. You can handle them with @RepositoryEventHandler to run logic around entity persistence lifecycle triggered through REST repositories.

Example:

~~~java
@Component
@RepositoryEventHandler(PurchaseOrder.class)
public class PurchaseOrderEventHandler {

    @HandleBeforeSave
    public void beforeSave(PurchaseOrder order) {
        if ("CANCELLED".equals(order.getStatus())
                && order.getItems().isEmpty()) {
            throw new IllegalStateException(
                "Cannot cancel an order with no items"
            );
        }
    }

    @HandleAfterSave
    public void afterSave(PurchaseOrder order) {
        // Hook for handling after a repository save event occurs.
    }
}
~~~

Repository events are useful for validation or technical persistence-related hooks. However, BeforeSaveEvent/AfterSaveEvent do not by themselves tell you whether the business intent was “confirm order”, “change address”, or “apply discount”. When a meaningful business journal is needed, emit explicit events in the service or use case where the actor, reason, and business decision are known.

Additionally, AfterSaveEvent is an event after the repository save call; do not assume it means the transaction has committed. For tasks that must run after commit, use appropriate transaction synchronization, @TransactionalEventListener(AFTER_COMMIT), or an outbox depending on reliability requirements.

Operations performed outside the Spring Data REST flow—such as internal services, batch jobs, or message consumers—may not pass through the same repository event handlers. Therefore, do not use repository events as the sole mechanism for recording the system's complete business history.

## 9. Comparing storage location and retention

| Criterion | Data auditing | HTTP log | Business journal |
|---|---|---|---|
| Typical location | Metadata columns on the entity. | Files, log platforms, gateways, or observability systems. | Journal table, event store, or outbox/archive. |
| Unit of record | Created/updated entity. | One request/response or access event. | One business event. |
| Semantic level | Who created/modified and latest timestamp. | Technical communication and HTTP outcome. | Action, actor, target object, and reason. |
| Multi-step history | Does not automatically store all versions. | Captures multiple requests, not necessarily commits. | Can store each event over time. |
| Typical query | Who last modified this record? | Which requests returned 500? Which endpoints are slow? | Why did the order transition to CONFIRMED? |
| Protection requirements | Control metadata updates. | Protect logs and limit sensitive data. | Restrict edit/delete, enforce access control and retention. |

You do not need a single store for all three. Data auditing usually lives with the entity for easy reading of current state; HTTP logs usually go to centralized logging; business journals typically live in dedicated persistence supporting queries by entity, actor, and event type.

## 10. Designing correlation IDs to link the three sources

When investigating an operation, you need to connect requests, entity changes, and business events. A correlation ID or trace ID serves as the linking key:

1. The gateway or application generates/receives a request ID when a request begins.
2. HTTP logs record the request ID along with method, route, status, and duration.
3. The service passes the request ID into the business journal entry.
4. When messages or background tasks are involved, attach the correlation ID in message headers or metadata.
5. Data auditing stores the actor and timestamp on the entity; when needed, query the entity by ID and cross-check with the journal.

For instance, searching requestId=abc123 in HTTP logs shows which request arrived. Using the same correlationId, search the business journal to see whether OrderConfirmed was recorded. Then inspect PurchaseOrder 42 to verify its current state and lastModified metadata.

Do not use the request ID as the unique identifier of a business event: a single request may emit multiple events, and a single event may pass through multiple internal steps or messages. Keep a separate eventId and use correlationId strictly to link the processing flow.

## 11. Ensuring integrity and traceability

If the business journal supports auditing or dispute resolution, define clearly who may read, who may write, and whether modification/deletion is allowed. Common measures include:

- Allow only dedicated services to create journal entries.
- Do not expose journal update/delete APIs to regular users.
- Store actor ID and timestamps from trustworthy server-side sources.
- Maintain a unique event ID and reference key to the aggregate.
- Record the reason or source of change when required by business rules.
- Use transactions/outbox so the journal does not drift out of sync with primary data.
- Configure appropriate retention, backups, and read access controls.
- If tamper-resistance requirements are stringent, consider append-only mechanisms, database-level permissions, hash chains, or immutable storage per policy.

Never allow clients to supply an arbitrary actorId and trust it as the performer. Actors must come from authenticated principals or controlled system identities. Before/after values should likewise be read from the entity inside the service rather than trusting client-declared content.

## 12. Verification flow for the three mechanisms

For an order-confirmation endpoint, you can verify each record type:

1. Create an order via POST; verify @CreatedBy and @CreatedDate are populated.
2. Update the order via PUT/PATCH; verify @LastModifiedBy and @LastModifiedDate change.
3. Call the order-confirmation endpoint; verify HTTP logs record method, route, status, duration, and request ID.
4. Verify the business journal contains an OrderConfirmed event with actor, order ID, before/after state, and reason.
5. Use the correlation ID to locate the request in HTTP logs and the event in the journal.
6. Trigger a validation or business error; verify the failed request is logged without creating a successful business event.
7. Simulate a rollback; verify neither the entity change nor the journal entry in the same transaction is committed.
8. Check log/journal read permissions and confirm tokens, passwords, or sensitive data do not appear in logs.

## 13. Choosing a mechanism by need

- Need to know who created and who last modified a record: use Spring Data JPA Auditing.
- Need to know which requests hit an endpoint, status, and processing time: use HTTP/access logs.
- Need to explain business actions, reasons, and change history: write a business journal.
- Need to trace across multiple services: add correlation/trace IDs.
- Need to ensure business events emit after commit: use AFTER_COMMIT or a transactional outbox.
- Need history of every field change: design an audit history/version table or event journal; the four auditing fields alone are not enough.

Data auditing, HTTP logs, and business journals all support traceability, yet at three distinct levels. Use auditing to store entity metadata, HTTP logs to observe requests/responses, and a business journal to capture domain-meaningful events. Connecting them via actor ID, entity ID, and correlation ID provides complete answers to who did what, which request triggered it, and how business state evolved.
