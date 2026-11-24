# Keeping Recipient Rules Out of the Controller

An email-sending endpoint typically receives requests from a browser or another application. The request may contain an order ID, notification type, and sometimes the destination email address. The controller receives the request, turns the input into a command, and calls an application service. However, **deciding who may receive an email, which address is used, and when sending is allowed** are application/business rules that should not live in the controller.

If the controller itself looks up recipients, checks order ownership, verifies email status, checks notification consent, and decides whether to send, that logic becomes tied to HTTP. When the same feature is invoked from a scheduler, message consumer, or internal service, those rules can be bypassed or duplicated.

In **Spring Framework Mail**, `JavaMailSender` sends messages through mail infrastructure. `MimeMessageHelper` builds MIME recipients and content. Neither component decides whether a recipient address is valid under business rules or whether the caller is authorized to send to it. Keep recipient rules inside an application/domain service or a dedicated policy, and let the controller handle intake and forwarding.

This lesson covers the boundary between controllers and the application layer, resolving recipients from authoritative data, handling user-supplied addresses, verification, consent, suppression, tenants, recipient lists, testing, and integration with Spring Mail.

## 1. Email recipients are a business decision

An email can go to many kinds of recipients: a customer's verified account email; a registered billing contact; a support ticket assignee; an external address entered to share a document; a tenant's member list; or a marketing subscriber address.

These cases do not share the same rules. An order confirmation email must usually go to a valid contact tied to the customer/order. A document-sharing email may permit entering an external address, provided the caller is authorized to share the document and the target address is allowed. Marketing emails must enforce product consent and unsubscribe policies.

Thus, a "recipient" is not merely a `String`. It is tied to questions:

- Who is requesting the send?
- Which account or customer does the email belong to?
- Is the caller authorized to send this information to that recipient?
- Has the address been verified per application workflow?
- Is this notification type allowed to be sent to this address?
- Is the recipient suppressed, unsubscribed, or suspended?
- Does the address belong to the right tenant and resource?
- Are there limits on send count or recipient count?

These questions are application rules. The controller may accept input and perform basic structural checks, but it should not enforce the entire policy.

## 2. What should the controller do?

The controller is an adapter at the HTTP boundary. Its responsibilities typically include:

1. Reading path variables, query parameters, request body, and authentication info.
2. Checking protocol-level input structure, such as required fields and basic format.
3. Obtaining the caller's identity from the authenticated security context.
4. Constructing a command representing the use case.
5. Calling the application service/handler.
6. Translating results or application errors into appropriate HTTP responses.

The controller should not execute rules such as picking an invoice email from multiple contacts, checking consent/suppression itself, choosing fallback recipients, enforcing quotas itself, or building `MimeMessage` and calling SMTP.

Example of a lean controller:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderMailController {

    private final SendOrderConfirmationHandler handler;

    public OrderMailController(
            SendOrderConfirmationHandler handler) {
        this.handler = handler;
    }

    @PostMapping("/{orderId}/confirmation-email")
    public ResponseEntity<Void> sendConfirmation(
            @PathVariable UUID orderId,
            @AuthenticationPrincipal AppPrincipal principal) {

        handler.handle(new SendOrderConfirmationCommand(
                orderId,
                principal.userId()
        ));

        return ResponseEntity.accepted().build();
    }
}
~~~

The controller passes only `orderId` and the authenticated caller identity into the command. It does not accept an arbitrary email address and decide itself whether an order confirmation can be sent there.

`AppPrincipal` is an application-defined principal type in this example. Never take `userId` from the request body when that identity must come from the authenticated session.

## 3. Why should recipient policy not live in the controller?

### 3.1. Logic becomes coupled to HTTP

An email-sending feature can be invoked from multiple sources:

~~~mermaid
flowchart LR
    A["HTTP controller"] --> E["Application service"]
    B["Scheduled job"] --> E
    C["Message consumer"] --> E
    D["Internal workflow"] --> E
~~~

If recipient rules live only in the controller, a scheduler or consumer can invoke the mail service directly and bypass those checks.

### 3.2. Rules get duplicated and become inconsistent

Controller A might check verified email status while Controller B forgets. One flow checks the suppression list while another skips it. When a rule changes, the team has to hunt down and edit multiple places. Placing policy at an application/domain boundary ensures every entry point enforces the same rules.

### 3.3. Harder to unit test business rules

If logic lives in the controller, unit tests must construct HTTP requests, principals, and many dependencies just to verify "is this recipient allowed to receive this notification?" When policy lives in a dedicated service, it can be tested with clear input objects without a web server.

### 3.4. Controllers easily accumulate excessive data access

A controller that queries order, customer, contact, tenant, consent, and suppression repositories while sending email holds too many responsibilities. An application service coordinates those components around a clearer use case.

## 4. Distinguishing validation, authorization, and recipient policy

These concepts are often lumped together yet answer different questions.

| Mechanism | Question | Example |
| --- | --- | --- |
| Structural validation | Does the data have the right shape? | `orderId` is present; email address has valid syntax. |
| Authorization | Is the caller allowed to act on this resource? | Can the current user view this order? |
| Recipient policy | Which address is allowed to receive this notification type? | Only send to the customer's verified contact email. |
| Business rule | Is the use case allowed in the current state? | Only send confirmation after the order is created. |
| Delivery policy | When to send, how many times, and how to retry? | Do not exceed notification limits within a time window. |

`@Email` or a syntax validator does not prove an address exists, that the caller owns it, or that sending data there is permitted. Likewise, authorization to view an order does not automatically mean the user can send that order's invoice to any address.

These checks can be invoked inside the same application service, while keeping their purposes distinct so "syntactically valid address" is never confused with "authorized recipient".

## 5. Resolving recipients from authoritative data sources

For order confirmation emails, clients usually do not need to supply a recipient address. The command can contain only the order identifier and caller:

~~~java
public record SendOrderConfirmationCommand(
        UUID orderId,
        UUID requestedBy) {
}
~~~

The application service loads the data and resolves the recipient:

~~~java
@Service
public class SendOrderConfirmationHandler {

    private final OrderRepository orders;
    private final CustomerRepository customers;
    private final OrderRecipientPolicy recipientPolicy;
    private final MailGateway mailGateway;

    public SendOrderConfirmationHandler(
            OrderRepository orders,
            CustomerRepository customers,
            OrderRecipientPolicy recipientPolicy,
            MailGateway mailGateway) {
        this.orders = orders;
        this.customers = customers;
        this.recipientPolicy = recipientPolicy;
        this.mailGateway = mailGateway;
    }

    public void handle(SendOrderConfirmationCommand command) {
        Order order = orders.findById(command.orderId())
                .orElseThrow(() ->
                        new OrderNotFoundException(command.orderId()));

        Customer customer = customers.findById(order.customerId())
                .orElseThrow(() ->
                        new CustomerNotFoundException(order.customerId()));

        MailRecipient recipient =
                recipientPolicy.requireOrderConfirmationRecipient(
                        command.requestedBy(),
                        order,
                        customer
                );

        // Build content from the validated order/customer.
        // Then send through the gateway.
    }
}
~~~

This example shows where the policy is invoked. The repositories, domain objects, and exceptions are hypothetical application components.

The key point is that the address comes from an authoritative contact record and is then checked against policy. A client cannot tamper with `recipient` in the request to redirect order details elsewhere.

### Do not rely solely on orderId

If an endpoint accepts `orderId`, the application still has to verify that the caller has access to that order. An unguessable UUID is not an authorization mechanism. The typical sequence is:

1. Load the resource within the appropriate tenant scope.
2. Check caller permissions on the resource.
3. Resolve the allowed recipient per the use case.
4. Check email status/recipient policy.
5. Render and send.

Never check only that the order exists and then email an address taken from the request.
## 6. What is a recipient policy?

A recipient policy expresses the rules for selecting and authorizing recipients per notification type. You can define an interface:

~~~java
public interface OrderRecipientPolicy {

    MailRecipient requireOrderConfirmationRecipient(
            UUID requestedBy,
            Order order,
            Customer customer);
}
~~~

An internal recipient data type:

~~~java
public record MailRecipient(
        String address,
        UUID contactId) {
}
~~~

The policy can verify that the customer is active, a contact email exists and is verified, the contact belongs to the right customer/tenant, the address is not suppressed, and the caller is permitted to request sending to that contact.

Example:

~~~java
@Component
public class DefaultOrderRecipientPolicy
        implements OrderRecipientPolicy {

    private final ContactRepository contacts;
    private final SuppressionRepository suppressions;
    private final OrderAccessPolicy orderAccess;

    public DefaultOrderRecipientPolicy(
            ContactRepository contacts,
            SuppressionRepository suppressions,
            OrderAccessPolicy orderAccess) {
        this.contacts = contacts;
        this.suppressions = suppressions;
        this.orderAccess = orderAccess;
    }

    @Override
    public MailRecipient requireOrderConfirmationRecipient(
            UUID requestedBy,
            Order order,
            Customer customer) {

        orderAccess.requireCanReceiveOrderNotice(
                requestedBy,
                order
        );

        Contact contact = contacts
                .findPreferredVerifiedEmail(customer.id())
                .orElseThrow(() ->
                        new NoEligibleRecipientException(customer.id()));

        if (suppressions.isSuppressed(
                contact.email(),
                MailPurpose.ORDER_CONFIRMATION)) {
            throw new RecipientSuppressedException();
        }

        return new MailRecipient(
                contact.email(),
                contact.id()
        );
    }
}
~~~

This is a structural example. The repository method `findPreferredVerifiedEmail` has a contract to return only verified contacts belonging to that customer. If the repository does not guarantee that, the policy must explicitly verify those invariants before returning the recipient.

### Policies can return a result instead of throwing exceptions

If the application needs to explain why an email was not sent, use a result type:

~~~java
public sealed interface RecipientDecision {
    record Allowed(MailRecipient recipient)
            implements RecipientDecision {}

    record Rejected(RecipientRejection reason)
            implements RecipientDecision {}
}
~~~

Example reason codes:

~~~java
public enum RecipientRejection {
    NO_VERIFIED_ADDRESS,
    SUPPRESSED,
    NOT_AUTHORIZED,
    WRONG_TENANT,
    CONSENT_REQUIRED
}
~~~

Choosing exceptions or result objects depends on project conventions. What matters is never silently skipping checks or falling back to an unapproved address.

## 7. User-entered email addresses: when are they allowed?

Not every use case pulls recipients from profiles. An invoice-sharing or document-copy feature may allow users to enter an external address.

Example request DTO:

~~~java
public record ShareInvoiceRequest(
        @NotBlank
        @Email
        String recipient) {
}
~~~

The controller can use `@Valid` to check shape:

~~~java
@PostMapping("/{invoiceId}/share")
public ResponseEntity<Void> shareInvoice(
        @PathVariable UUID invoiceId,
        @Valid @RequestBody ShareInvoiceRequest request,
        @AuthenticationPrincipal AppPrincipal principal) {

    shareInvoiceHandler.handle(
            new ShareInvoiceCommand(
                    invoiceId,
                    principal.userId(),
                    request.recipient()
            )
    );

    return ResponseEntity.accepted().build();
}
~~~

The controller does not decide whether that address is allowed to receive the invoice. The handler/policy must check:

- Is the caller allowed to share this invoice?
- Does the invoice belong to the right tenant/customer?
- Does the feature allow sending outside the organization?
- Is the address on a blocklist or suppression list?
- Is the caller permitted to share this data category with external recipients?
- Are share counts and recipient counts within limits?

### An entered address does not prove ownership

Users can type someone else's email address. If the application sends sensitive information to that address without proper policy checks, data leaks can happen.

For use cases needing recipient verification, send a confirmation prompt or expiring link before exposing data. For invoices, contracts, or personal data, the product must explicitly define sharing rules and requester permissions.

### Do not use one shared rule for every email type

Account verification, invoices, security alerts, newsletters, and document-sharing emails can each have different recipient policies. An address unsubscribed from marketing should not necessarily block a required transactional email; conversely, a verified email status does not automatically imply marketing consent.

Define policies by **email purpose/type**, not merely by the address string.

## 8. Address verification and updating account emails

An account may change its email address. If the application sends critical notices immediately after a user enters a new address, determine whether that address has been verified.

A contact model might store:

~~~java
public record EmailContact(
        UUID id,
        String address,
        boolean verified,
        Instant verifiedAt,
        boolean primary) {
}
~~~

This is an example DTO/domain model; actual state may live in a dedicated entity.

An email-change flow typically includes these steps:

1. The user requests an address change.
2. The application saves the new address in a pending state.
3. Sends a verification link to the new address.
4. The user proves access to that address.
5. The application marks the contact verified and applies primary-contact rules.
6. Subsequent notifications use the address selected by recipient policy.

Never mark an address verified just because the request contains a valid-looking address or the user is signed in. `@Email` checks only syntax; verification requires a flow proving mailbox access.

### Old address vs. new address

When changing an email, the application may need to notify the old address, the new address, or both per security policy. That decision belongs to the email-change use case, not the controller. In particular, never let requests choose an arbitrary address to receive a verification link without tying it to a pending change state.

## 9. Distinguishing transactional emails and marketing emails

Different email categories have different recipient rules.

| Category | Examples | Recipient rules to evaluate |
| --- | --- | --- |
| Transactional | Order confirmation, invoice, password reset | Recipient tied to account/transaction; authorization and data accuracy |
| Security alert | New sign-in, email change | Verified address or security contact channel per policy |
| Operational notice | Service maintenance, tenant incident | Members/contacts belonging to the right tenant and role |
| Marketing | Newsletters, promotions | Consent, unsubscribe, suppression, and applicable rules |
| User-initiated share | Sending documents to user-entered addresses | Resource sharing permissions, external recipient controls, and auditing |

Do not apply the same "subscribed to newsletter" condition to every email without classifying purpose. Nor should you use the "transactional" label to skip all checks. The application still requires the right recipient, right purpose, access authorization, and applicable legal/policy requirements.

### Consent and unsubscribe

For marketing emails, recipient policy usually checks subscription status, consent timestamp, content scope, consent source, and unsubscribe/suppression status. Checks should run at the application boundary right before creating the send job or right before the worker sends, depending on architecture and freshness requirements.

If a recipient has unsubscribed, never send marketing again just because a different controller failed to check that status. Use a centralized policy so all entry points enforce the same rule.

## 10. Suppression lists and blocked addresses

A suppression list may contain addresses that:

- Requested to unsubscribe.
- Hard-bounced or are no longer deliverable.
- Triggered complaints/spam reports.
- Were locked for security or administrative reasons.
- Are disallowed from receiving a specific notification type.

Suppression may apply system-wide or per purpose/provider. Thus, the policy must recognize **notification type** and suppression scope.

Example:

~~~java
public enum MailPurpose {
    ORDER_CONFIRMATION,
    PASSWORD_RESET,
    SECURITY_ALERT,
    MARKETING
}
~~~

~~~java
public interface RecipientSuppressionPolicy {
    void requireNotSuppressed(
            EmailAddress recipient,
            MailPurpose purpose);
}
~~~

A marketing suppression does not necessarily carry the same effect as a security alert. Decisions must follow product policy and applicable rules; avoid a single global `blocked` boolean across all mail types when legitimate exceptions exist.

### Checking suppression at the right time

If sending immediately, check recipient policy right before sending. If creating an async job, suppression status can change between job creation and worker execution. For mail types needing up-to-date status, the worker should recheck policy before handing the message to the gateway.

Define behavior when policy rejects: mark the job suppressed, store an appropriate reason code, and do not retry it like an SMTP error. A policy-blocked address is not a connection error solvable by retries.

## 11. Tenants and organizational boundaries

In multi-tenant applications, the same email address may appear in multiple tenants or a user may hold different roles per tenant. Never look up a contact solely by email and send Tenant A's data to someone associated with Tenant B.

The command can carry the tenant context resolved from security/session:

~~~java
public record SendTenantNoticeCommand(
        UUID tenantId,
        UUID requestedBy,
        String noticeCode) {
}
~~~

The application service must verify that the caller belongs to that tenant and is authorized to send the notice. The recipient resolver queries contacts only within that tenant:

~~~java
Optional<TenantContact> findEligibleRecipient(
        UUID tenantId,
        NoticePurpose purpose);
~~~

Never trust a `tenantId` from the request body when the real tenant must come from authenticated context or verified membership. If the request supplies a tenant ID, the application layer must still validate it against the principal's scope.

### Do not let recipients become a cross-tenant bypass

A user in Tenant A must not send an email containing Tenant A data to an address pulled from Tenant B's records just because that address exists. Verify which tenant owns the resource, whether the caller has permission on the resource, whether the chosen contact belongs to the same tenant or cross-tenant sharing is allowed, and whether external recipient policies apply.

These checks belong in the use case/policy, never relying on controller routes or UI alone for enforcement.

## 12. Cc, Bcc, and recipient lists

A request may want to send to multiple recipients. In that case, the recipient policy must evaluate the entire list, not just individual addresses.

Decisions to make:

- Maximum recipient count.
- Are To/Cc/Bcc allowed or only To?
- Should duplicate addresses be removed?
- Are recipients allowed to see one another's addresses?
- Is everyone authorized to receive the same content?
- Should separate messages be sent per person for personalization?
- If one address is invalid, does the whole batch fail or only that address?

### Do not expose recipient lists

When sending the same email to multiple people who do not know one another, putting everyone in To or Cc reveals their email addresses to each other. Bcc may fit certain cases, while still obeying privacy policies and sending purpose.

For personalized emails or sensitive data, generate a separate message per recipient. Never place recipients from different tenants or unrelated groups into the same message.

### Controlling count and duplicates

Example request DTO:

~~~java
public record BulkNoticeRequest(
        @NotEmpty
        @Size(max = 50)
        List<@NotBlank @Email String> recipients,
        @NotBlank
        String noticeCode) {
}
~~~

50 is only an illustrative limit. Applications must set limits based on provider quotas, message size, product policy, and abuse prevention.

Deduplication also requires a clear address normalization policy. Email domains are case-insensitive per DNS, while local-parts can technically be case-sensitive; do not arbitrarily lowercase full addresses assuming every provider treats them identically. You may trim whitespace and apply product-approved canonicalization rules while preserving address semantics.

## 13. Email addresses: syntax, normalization, and authorization

An address roughly follows the form:

~~~text
local-part@domain
~~~

Checking email syntax cannot prove that the domain is active, the mailbox exists, the recipient controls the mailbox, the recipient wants this email type, or the caller is allowed to send data there.

Bean Validation's `@Email` is useful for basic input shape checking, not mailbox verification. Some RFC-valid addresses may be rejected by providers or internal systems; conversely, overly strict regexes can reject valid addresses.

Example DTO:

~~~java
public record ExternalShareRequest(
        @NotBlank
        @Email
        @Size(max = 254)
        String recipient) {
}
~~~

The 254 limit is a common application value, yet should be checked against address/provider rules your system supports. Do not treat a length number as proof of ultimate validity.

### Careful normalization

Appropriate steps may include:

- Trimming accidental leading/trailing whitespace if the API contract permits.
- Rejecting control characters or newlines.
- Using an appropriate email address parser when display-name syntax is supported.
- Normalizing domains under IDN rules if supported by the system.
- Preserving local-part per chosen policy; do not arbitrarily strip dots or plus tags because providers have different semantics.

Do not write a massive regex to solve every address form. Define the set of formats your system supports and use an appropriate parser/validator.

### Do not build raw headers from input

Set recipients via APIs like `helper.setTo(...)` or overloads taking `InternetAddress`, rather than concatenating `To:` header strings manually. Reject unwanted CR/LF characters and let the MIME library encode headers. This is part of mail-boundary defense, alongside business recipient policies.

## 14. Recipient policy is not the same as Reply-To/From

An email has several addresses with different roles:

| Field | Role |
| --- | --- |
| To | Primary recipients |
| Cc | Visible copy recipients |
| Bcc | Hidden copy recipients |
| `From` | Displayed sender address |
| `Reply-To` | Suggested address for replies |
| SMTP account | Credentials authenticating to the SMTP relay |

Recipient policy focuses on **who receives the message**. `From`, `Reply-To`, and SMTP account are separate concerns. For example, setting `Reply-To` to a support address does not send the email to support; the primary recipients remain in To.

+## 15. Sending email after policy permits

Once the application service has resolved a valid recipient, the mail-sending layer can accept an internal object:

~~~java
public record OutboundMail(
        MailRecipient recipient,
        String subject,
        String plainText,
        String html) {
}
~~~

Gateway using Spring Mail:

~~~java
@Component
public class SpringMailGateway {

    private final JavaMailSender mailSender;

    public SpringMailGateway(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(OutboundMail mail) {
        try {
            MimeMessage message = mailSender.createMimeMessage();

            MimeMessageHelper helper =
                    new MimeMessageHelper(message, true, "UTF-8");

            helper.setFrom("notice@example.org");
            helper.setTo(mail.recipient().address());
            helper.setSubject(mail.subject());
            helper.setText(mail.plainText(), mail.html());

            mailSender.send(message);
        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Could not prepare email", ex
            );
        } catch (MailException ex) {
            throw new MailDeliveryException(
                    "Could not send email via SMTP", ex
            );
        }
    }
}
~~~

`MailPreparationException` and `MailDeliveryException` are custom application exceptions in this example. The gateway does not decide who may receive; it accepts a recipient already resolved by the application layer.

If the gateway is called from multiple use cases, you can design it to accept an `ApprovedRecipient` type constructible only through policy or the application boundary. This expresses intent in code, though not an absolute security mechanism: Java visibility and module boundaries still need proper design.

### Do not turn the gateway into an arbitrary public sending endpoint

An internal gateway may have a generic `send(OutboundMail)` method. Never expose this method directly over HTTP without policy checks. If any caller can construct `OutboundMail` with arbitrary recipients and arbitrary HTML, use-case rules can be bypassed.

## 16. Bringing recipient policy into asynchronous flows

With async mail sending, the application service can create a job and a worker sends later:

~~~mermaid
flowchart TD
    A["Controller / Event / Scheduler"] --> B["Application command handler"]
    B --> C["Authorization + recipient policy"]
    C --> D["Save mail job / outbox"]
    D --> E["Mail worker"]
    E --> F["Recheck current policy if needed"]
    F --> G["Render message"]
    G --> H["JavaMailSender"]
    H --> I["Update status"]
~~~

There are two points where policy can be evaluated:

- **At job creation:** confirm the use case is valid and the initial recipient is permitted.
- **Right before sending:** check conditions that may change, such as suppression, unsubscribe, or contact status.

Whether to recheck depends on business requirements. For order confirmation emails, a recipient snapshot at event creation time may be necessary for historical accuracy. For marketing, the latest unsubscribe status must normally be respected when the worker sends.

### Store a recipient snapshot or re-resolve?

| Approach | Meaning | Considerations |
| --- | --- | --- |
| Store recipient snapshot | Job sends to the address resolved at creation time | Address may change or get suppressed before worker runs |
| Resolve recipient at send time | Worker reads current contact from the system | Recipient may differ from who was expected at job creation |
| Snapshot + policy recheck | Store recipient/purpose and check mutable conditions before send | Clearly define which conditions are allowed to cancel a job |

No single choice fits every use case. For security or transactional notices, the decision can affect auditing and access control. Record recipient identity, purpose, resolution timestamp, and policy outcome at an appropriate metadata level.

## 17. Abuse prevention and send limits

An endpoint accepting external recipients can be abused for spam or harassment if unbounded. Recipient policy and delivery policy can work together to enforce:

- Max emails per user/tenant in a time window.
- Max recipients per command.
- Send frequency to the same address.
- Allowed notification types per endpoint.
- Permissions on shared resources.
- Account, tenant, and API key status.
- Abnormal or repetitive sending behavior.

Example interface:

~~~java
public interface MailRateLimitPolicy {
    void requireWithinLimit(
            UUID actorId,
            UUID tenantId,
            MailPurpose purpose);
}
~~~

This policy should be invoked in the application layer or a dedicated component rather than relying solely on API gateway rate limits. HTTP rate limits protect endpoints, whereas scheduled jobs or event consumers also need appropriate caps.

### Do not leak too much through recipient errors

For sensitive use cases such as password reset, error messages can let attackers probe which emails are registered. Public responses may need neutral wording while internal logs store appropriate reason codes with data protection.

For example, an external response might say "If a matching account exists, instructions will be sent" instead of directly revealing whether an account exists. Specific rules depend on the application's threat model.

## 18. Auditing and logging recipient policies

When sending is blocked by policy, that is a business outcome distinct from an SMTP error. You can store metadata:

~~~text
mail_request_id: req-7f2...
purpose: ORDER_CONFIRMATION
tenant_id: tenant-42
recipient_contact_id: contact-19
decision: REJECTED
reason: SUPPRESSED
requested_at: 2026-11-12T09:00:00Z
~~~

This is an illustrative record. Avoid logging full email addresses, message bodies, tokens, or SMTP credentials unless necessary and properly protected. You can use contact IDs, keyed hashes, or partially masked values per logging policy.

Audits should answer which use case requested the send, who or what component initiated it, where the recipient was resolved from, which policy applied, the allow/reject decision and reason code, whether the message reached the gateway, and how the SMTP provider responded.

Distinguish **policy rejected**, **message prepared**, **SMTP accepted**, and **delivery confirmed**. SMTP acceptance does not prove an email reached the inbox.

## 19. Testing recipient policy outside the controller

When policy resides in its own service, it can be tested directly against cases:

| Case | Expected outcome |
| --- | --- |
| Primary contact verified, not suppressed | Allowed |
| No verified address exists | Rejected |
| Contact belongs to another tenant | Rejected |
| Caller lacks permission on order | Rejected |
| Address suppressed for that purpose | Rejected |
| Marketing consent missing | Rejected per marketing policy |
| User enters external address when use case disallows | Rejected |
| Valid recipient exceeds rate limit | Rejected or delayed per delivery policy |

Example skeleton test:

~~~java
@Test
void rejectsOrderRecipientWhenContactIsNotVerified() {
    // Arrange:
    // - valid order and customer
    // - unverified contact
    // - actor authorized on the order

    assertThrows(
            NoEligibleRecipientException.class,
            () -> policy.requireOrderConfirmationRecipient(
                    actorId,
                    order,
                    customer
            )
    );
}
~~~

This test does not build an HTTP request or call SMTP. It tests recipient selection rules at the right layer.

### Testing the controller separately

Controller tests focus on verifying that valid requests map to the right command, actor ID comes from the authenticated principal, malformed requests return proper HTTP errors, and application exceptions map to responses via exception handlers.

Do not repeat the entire policy test matrix in every controller test. You can mock the application handler to verify the controller invokes the right command.

### Integration testing

Integration tests can use a test database repository, fake mail gateway, or SMTP test server to verify the whole flow. Separating policy, controller, renderer, and SMTP tests pinpoints failures at the right boundary.

## 20. Example endpoint for external addresses with policy still in application layer

Sometimes a product lets users enter an address to send a document copy. The controller simply receives the request and dispatches a command:

~~~java
public record ShareDocumentRequest(
        @NotBlank
        @Email
        @Size(max = 254)
        String recipient) {
}
~~~

~~~java
public record ShareDocumentCommand(
        UUID documentId,
        UUID requestedBy,
        String recipient) {
}
~~~

Controller:

~~~java
@PostMapping("/{documentId}/share")
public ResponseEntity<Void> share(
        @PathVariable UUID documentId,
        @Valid @RequestBody ShareDocumentRequest request,
        @AuthenticationPrincipal AppPrincipal principal) {

    shareDocumentHandler.handle(
            new ShareDocumentCommand(
                    documentId,
                    principal.userId(),
                    request.recipient()
            )
    );

    return ResponseEntity.accepted().build();
}
~~~

Handler:

~~~java
@Service
public class ShareDocumentHandler {

    private final DocumentRepository documents;
    private final DocumentSharePolicy sharePolicy;
    private final MailGateway mailGateway;

    public ShareDocumentHandler(
            DocumentRepository documents,
            DocumentSharePolicy sharePolicy,
            MailGateway mailGateway) {
        this.documents = documents;
        this.sharePolicy = sharePolicy;
        this.mailGateway = mailGateway;
    }

    public void handle(ShareDocumentCommand command) {
        Document document = documents.findById(command.documentId())
                .orElseThrow(() ->
                        new DocumentNotFoundException(command.documentId()));

        sharePolicy.requireCanShare(
                command.requestedBy(),
                document,
                command.recipient()
        );

        // Create share link with appropriate permissions and expiration.
        // Render email and send through the gateway.
    }
}
~~~

`DocumentSharePolicy` can check sharing permissions, document type, tenant, external recipients, suppression, and rate limits. The controller does not need to know any of those rule details.

+## 21. Common mistakes

### 21.1. Controller taking email directly from the request

**Problem:** clients can swap the address to receive data that does not belong to them.

**Fix:** for account/transaction notices, resolve recipients from authoritative data inside the application service.

### 21.2. Checking only @Email and sending

**Problem:** valid syntax does not prove the address exists, is verified, or is authorized to receive.

**Fix:** separate structural validation from authorization and recipient policy.

### 21.3. Placing policy in a single controller

**Problem:** schedulers or consumers can invoke the service and bypass policy.

**Fix:** place rules in an application/domain service shared by all entry points.

### 21.4. Using one recipient rule for every email type

**Problem:** transactional, security, marketing, and sharing emails have different conditions.

**Fix:** pass an explicit purpose and apply the appropriate policy.

### 21.5. Trusting client-supplied recipients in sensitive use cases

**Problem:** callers can redirect invoices, reset links, or personal data to external addresses.

**Fix:** resolve from verified contacts or require a dedicated sharing/authorization workflow.

### 21.6. Missing tenant checks

**Problem:** contacts or resources may belong to another tenant.

**Fix:** scope repository queries and policies to the authenticated tenant; never trust client-declared tenant IDs.

### 21.7. Skipping suppression checks when workers send old jobs

**Problem:** recipients may unsubscribe or become suppressed after the job was created.

**Fix:** define when policy must be rechecked, especially for marketing.

### 21.8. Using Bcc to send unauthorized data

**Problem:** Bcc hides addresses from other recipients, but does not grant sending or data-sharing permission.

**Fix:** check every To/Cc/Bcc address under the same authorization and purpose rules.

### 21.9. Logging full email addresses and content

**Problem:** logs become a store of personal data, tokens, and private content.

**Fix:** log IDs, reason codes, and minimal metadata; protect logs per policy.

### 21.10. Retrying policy failures like SMTP errors

**Problem:** suppressed or unauthorized addresses cannot be fixed by retrying.

**Fix:** classify rejected/suppressed outcomes separately from transient delivery failures.

### 21.11. Controller calling JavaMailSender directly

**Problem:** HTTP layer becomes coupled to MIME, SMTP, and sending rules; other entry points easily bypass policy.

**Fix:** controller calls use case, application service enforces policy, and only the gateway calls Spring Mail.

### 21.12. Automatically falling back to a secondary email

**Problem:** a secondary address may be unverified, belong to someone else, or be disallowed for that data type.

**Fix:** fallback must be an explicit business rule with verification and auditing; never blindly pick the next available address.

## 22. Reasoning exercises

**Question 1.** An order confirmation endpoint takes `orderId` and `recipient` from the client. Should it send to `recipient` without checking?

No. The application service must verify permission on the order and select/allow the recipient per policy. For typical use cases, the authoritative contact address is resolved from the customer/order.

**Question 2.** Does `@Email` returning valid prove the recipient verified the address?

No. It only checks validator-level syntax; verification requires a workflow proving mailbox access.

**Question 3.** Why should recipient policy not live only in the controller?

Because schedulers, consumers, and internal workflows can invoke the use case without going through a controller. Policy in the application/domain layer applies across all entry points.

**Question 4.** A user unsubscribed from marketing. Should all transactional emails be blocked?

No. Policies must distinguish purpose and follow applicable product/legal rules. Unsubscribing from marketing does not automatically block transactional or security notices.

**Question 5.** A user in Tenant A enters a Tenant B contact's email to receive a Tenant A invoice. Is valid email syntax enough?

No. You must check resource-sharing permissions, tenant boundaries, and recipient policy.

**Question 6.** A marketing job was created yesterday, the recipient unsubscribed today, and the worker runs tomorrow. What should happen?

If policy requires respecting the latest status, the worker must check suppression/consent right before sending and mark the job suppressed instead of retrying SMTP.

**Question 7.** Does Bcc make sending to an arbitrary address valid?

No. Bcc only hides recipient headers from other recipients; it does not replace authorization or recipient policy.

**Question 8.** A controller test confirmed the endpoint returns HTTP 202. Does that prove the policy is right?

Not yet. Policies need dedicated unit/integration tests in the application layer. Controller tests primarily check request/response mapping.

**Question 9.** Should full email addresses be lowercased for deduplication?

Do not automatically assume local-parts are always case-insensitive. Use an intentional canonicalization rule that respects your system/provider semantics.

**Question 10.** Can the gateway accept a generic `OutboundMail`?

Yes, at an internal layer after the application layer has decided the recipient and content. Never expose the gateway as a public endpoint allowing callers to bypass policy.

## 23. Mental model to remember

The mail-sending flow should keep recipient policy at the application/domain boundary:

~~~mermaid
flowchart TD
    A["Controller / Scheduler / Event"] --> B["Command"]
    B --> C["Application service"]
    C --> D["Authorization + business checks"]
    D --> E["Recipient resolver / policy"]
    E --> F{"Recipient permitted?"}
    F -->|"No"| G["Reject / Suppressed / Audit"]
    F -->|"Yes"| H["Render email content"]
    H --> I["Mail gateway"]
    I --> J["MimeMessageHelper"]
    J --> K["JavaMailSender"]
    K --> L["SMTP relay"]
~~~

Core principles:

1. **Controllers receive requests and build commands**, never making business recipient decisions themselves.
2. **Resolve recipients from authoritative sources** when emails tie to accounts, orders, or documents.
3. **Separate validation, authorization, and recipient policy**: valid email syntax does not prove permission to receive.
4. **Classify by purpose**: transactional, security, marketing, and sharing can follow different rules.
5. **Check verification, consent, suppression, and tenant** at the appropriate application/domain layer.
6. **User-entered addresses must still pass policy**; request DTOs and `@Email` are only structural checks.
7. **Control To, Cc, and Bcc** as real recipients; Bcc grants no sending permission.
8. **Define when to recheck policy** for async jobs and retries.
9. **Distinguish policy rejections from SMTP errors**, storing reason codes and appropriate audit metadata.
10. **Keep JavaMailSender inside the gateway**; application services decide whom to send to, and the gateway handles sending.

With this design, controllers stay thin and easy to change, while recipient rules are enforced consistently whether requests arrive via HTTP, schedulers, or event consumers. `MimeMessageHelper` and `JavaMailSender` only handle building and sending messages after the application has determined valid recipients for the use case.



