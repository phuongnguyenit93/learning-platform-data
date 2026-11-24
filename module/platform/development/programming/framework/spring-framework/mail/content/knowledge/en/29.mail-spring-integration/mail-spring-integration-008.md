# Filtering Emails Before Entering the Flow

When using **Spring Integration Mail** to receive emails, an application does not necessarily want to process every message in the mailbox. A customer support inbox might hold valid tickets, automated replies, newsletters, delivery failure notices, malformed messages, emails already processed in a previous poll, or disallowed attachments. If every email goes straight into a business handler, the system easily creates unwanted tickets, processes duplicate invoices, fills queues, or downloads huge attachments of zero value.

**Filtering emails before entering the flow** means deciding which emails qualify to move from the mailbox into the pipeline, and enforcing that decision at the right boundary. In Spring Integration Mail, there are distinct layers:

1. **Mailbox/server-side:** select the folder and use an IMAP `SearchTerm` to narrow which messages are fetched.
2. **Receiver/intake:** check metadata, size, UID state, idempotency, and eligibility before creating a business job.
3. **Inside IntegrationFlow:** use `filter`, `route`, and `transform` steps to orchestrate messages emitted by the inbound adapter into the flow.
4. **Business validation:** verify partner, tenant, recipient, token, permissions, and untrusted content.

These four layers complement rather than replace one another. Filtering by subject on the IMAP server reduces the messages fetched, yet does not prove the sender is an authorized partner. Filtering with `.filter(...)` after the inbound adapter blocks downstream handlers, yet the email has already been downloaded from the mailbox by the receiver.

~~~mermaid
flowchart TD
    A["Mailbox / folder"] --> B["IMAP SearchTerm"]
    B --> C["Mail receiver"]
    C --> D["Metadata + size limits"]
    D --> E["UID / idempotency gate"]
    E --> F{"Eligible?"}
    F -->|"No"| G["Skip / quarantine / retry"]
    F -->|"Yes"| H["Durable intake record"]
    H --> I["IntegrationFlow"]
    I --> J["Business validation"]
    J --> K["Business job"]
~~~

This lesson covers filtering approaches, Java DSL examples, IMAP/POP3, the `Seen` flag, UIDs, MIME/attachment safety, multi-tenancy, error handling, monitoring, and testing.

## 1. Which Emails Need to Be Filtered?

Suppose a mailbox contains:

~~~text
INBOX
  [Ticket] Customer reports login error
  Re: [Ticket] Customer adds logs
  Auto-Reply: Out of office
  Delivery Status Notification
  Newsletter from vendor
  [Invoice] Invoice from partner
  Email with 100 MiB attachment
  Email already ingested in previous poll
~~~

A ticketing application should forward only qualifying messages into the ticket creation/update flow. An invoicing application may need a separate mailbox, folder, or route.

Without filtering:

- Auto-replies can trigger automated reply loops.
- Spam can create tickets.
- Re-polled messages can create duplicate business records.
- Irrelevant files still get downloaded and parsed.
- Spoofed `From` headers may be mistakenly trusted.
- A shared multi-tenant mailbox can route data to the wrong tenant.
- Deleting emails too early loses unpersisted data.

However, **filtering wrongly is also dangerous**. If you only read `UNSEEN`, staff opening an email before the poller runs can prevent the application from ever receiving it. Thus, filter criteria need verification, auditing, and recovery mechanisms.

## 2. Message Source and Inbound Channel Adapter

In Spring Integration Mail:

| Component | Responsibility |
| --- | --- |
| `ImapMailReceiver` | Searches and receives emails via IMAP |
| `Pop3MailReceiver` | Receives emails via POP3 |
| `MailReceivingMessageSource` | Supplies emails via the message source interface |
| Poller | Calls the source on a schedule |
| Inbound channel adapter | Emits data from the source onto a Spring Integration channel |
| Message channel | Transfers messages to endpoints |
| `.filter(...)` | Allows or drops messages at a point inside the flow |
| Service activator | Executes a handler |
| Error handling | Routes errors from the flow/endpoint |

Two positions to distinguish:

~~~text
Mailbox
  -> folder selection
  -> IMAP server search
  -> mail receiver
  -> message source
  -> inbound adapter
  --- BOUNDARY INTO FLOW ---
  -> integration filter
  -> transformer/router
  -> business handler
~~~

**Filtering at the receiver** shrinks the candidate set from the server. **Filtering in the flow** orchestrates payloads after receipt. If the product goal is saving bandwidth and avoiding fetching oversized emails, writing `.filter(...)` in the DSL alone is not enough.

## 3. Filtering Layers Ordered by Cost

| Layer | Condition | Benefit | What It Does Not Guarantee |
| --- | --- | --- | --- |
| Mailbox/folder | `INBOX/Invoices` | Narrows message set | Emails were not misfiled |
| IMAP search | Flags, subject, date | Server filters candidates | Sender is trustworthy |
| Lightweight metadata | From, To, MIME headers | Quickly drops irrelevant mail | Headers are authenticated |
| Size policy | Byte/part limits | Reduces resource exhaustion risk | File is safe |
| UID gate | Already ingested or not | Prevents duplicate ingestion | Exactly-once business side effects |
| MIME/content validation | Attachments, body schema | Identifies valid data | Sender has permission |
| Business authorization | Tenant, ticket, invoice | Protects side effects | Mail transport always succeeds |

Put cheap checks first and expensive checks later without sacrificing safety. When a filter lacks sufficient evidence, prefer **quarantine/review** instead of irreversibly deleting the email.

## 4. Differences Between IMAP and POP3

| Capability | IMAP/IMAPS | POP3/POP3S |
| --- | --- | --- |
| Folders | Multiple folders | Simpler mailbox model |
| Server-side SEARCH | Yes | No equivalent to IMAP SEARCH |
| `\Seen` flag | Yes | Does not share the same semantics |
| Message UID | Folder-scoped UID + `UIDVALIDITY` | UIDL per POP3 server semantics |
| Move folder/mark flags | Supported | Limited |
| Exclude mail before fetching body | Can search by metadata | Generally more limited |

If the use case needs unread messages in a specific folder without downloading everything, IMAP usually fits. With POP3, the application may have to fetch lists, inspect metadata, and filter client-side within server capabilities.

Do not assume every provider supports the same IMAP extensions, user flags, or Unicode search behavior. Likewise, never use a POP3 message index as a durable identifier.

## 5. IMAP SearchTerm

Jakarta Mail provides `SearchTerm` types in `jakarta.mail.search`:

- `FlagTerm`: filters flags that are set/unset.
- `SubjectTerm`: searches for a string in the subject.
- `FromStringTerm`: searches for a string in From.
- `RecipientStringTerm`: searches recipients.
- `ReceivedDateTerm` or `SentDateTerm`: searches by timestamp.
- `AndTerm`, `OrTerm`, `NotTerm`: combines conditions.

Logical example:

~~~text
UNSEEN
AND subject contains "[Invoice]"
AND receivedDate >= lowerBound
~~~

When the receiver uses a `SearchTerm` with IMAP, the server can reduce how many messages must be fetched. Remember:

- `SearchTerm` only finds **candidates**.
- Subject and From can be forged.
- Servers may implement search according to their own rules.
- Received date is not a reliable sole cursor.
- Conditions requiring PDF parsing or virus scanning cannot be performed purely by IMAP SEARCH.

## 6. Filtering by Unread Flag

Example term matching messages without the `SEEN` flag:

~~~java
import jakarta.mail.Flags;
import jakarta.mail.search.FlagTerm;
import jakarta.mail.search.SearchTerm;

SearchTerm unseen =
        new FlagTerm(
                new Flags(Flags.Flag.SEEN),
                false
        );
~~~

Combined with subject:

~~~java
import jakarta.mail.search.AndTerm;
import jakarta.mail.search.SubjectTerm;

SearchTerm term =
        new AndTerm(
                unseen,
                new SubjectTerm("[Invoice]")
        );
~~~

This expresses the criteria using the Jakarta Mail API. However, **UNSEEN does not equal unprocessed by business logic**:

- A human may open the email before the poller runs.
- The receiver may not mark it read automatically.
- The email was persisted, yet acknowledgment failed.
- Another application sharing the mailbox changed flags.

To prevent losing emails, you need durable ingestion state and a reconciliation policy, not just flag reliance.

## 7. SearchTermStrategy in ImapMailReceiver

Spring Integration Mail allows customizing the search term strategy for the IMAP receiver. Example configuration:

~~~java
import jakarta.mail.Flags;
import jakarta.mail.Folder;
import jakarta.mail.search.AndTerm;
import jakarta.mail.search.FlagTerm;
import jakarta.mail.search.SearchTerm;
import jakarta.mail.search.SubjectTerm;

import org.springframework.integration.mail.ImapMailReceiver;
import org.springframework.integration.mail.SearchTermStrategy;

public ImapMailReceiver createReceiver(
        String mailUrl) {

    ImapMailReceiver receiver =
            new ImapMailReceiver(mailUrl);

    receiver.setSearchTermStrategy(
            new SearchTermStrategy() {

                @Override
                public SearchTerm generateSearchTerm(
                        Flags supportedFlags,
                        Folder folder) {

                    SearchTerm unseen =
                            new FlagTerm(
                                    new Flags(
                                            Flags.Flag.SEEN
                                    ),
                                    false
                            );

                    return new AndTerm(
                            unseen,
                            new SubjectTerm("[Invoice]")
                    );
                }
            }
    );

    receiver.setShouldDeleteMessages(false);
    receiver.setShouldMarkMessagesAsRead(false);

    return receiver;
}
~~~

This illustrates **pre-flow candidate selection**. APIs and overloads must match your Spring Integration version. When customizing a search strategy, understand the receiver's default search semantics so you do not accidentally drop safeguards against re-fetching old mail.

`supportedFlags` and `folder` can tailor criteria to server/folder capabilities. Never assume user-defined flags are supported by every server.

## 8. Subject Filtering: Helpful Yet Easy to Miss Mail

Example:

~~~java
SearchTerm invoiceTerm =
        new SubjectTerm("[Invoice]");
~~~

Subjects you might encounter:

~~~text
[Invoice] INV-981
Re: [Invoice] INV-981
Fwd: [Invoice] INV-981
November invoice
Invoice INV-981
~~~

Rules matching only a narrow prefix can miss valid emails when a partner changes formats, users forward messages, or replies alter prefixes.

When a partner has an automated sending contract, prefer a **structured, verified identifier**, recipient alias, or file schema rather than relying purely on subject text. For uncertain cases, route to review rather than deleting.

### Subject Does Not Grant Authority

Any sender can write `[Ticket-123]`. Never automatically modify ticket 123 without verifying tokens/identity and tenant access permissions.

## 9. Filtering by From

Example:

~~~java
import jakarta.mail.search.FromStringTerm;

SearchTerm fromPartner =
        new FromStringTerm(
                "invoices@partner.example"
        );
~~~

This is a candidate heuristic. **The From header is not authentication proof.** Senders can spoof it. If business logic requires trusting the source, use an authoritative mechanism: provider authentication metadata, partner signatures/tokens, or a trusted protocol/boundary paired with authorization.

Never use a check like:

~~~java
fromAddress.endsWith("partner.example")
~~~

to assert a valid domain. Lookalike domains easily bypass suffix matching. Parse the address, canonicalize the domain, and check against authorized identities. Even with a valid domain, the sender may still lack permission to issue business commands.

## 10. Recipients and Alias Routing

An inbox can receive emails addressed to:

~~~text
support+ticket-123@platform.example
invoice+tenant-a@platform.example
reply@platform.example
~~~

Recipient aliases can assist classification. However, the `To` header is not necessarily the SMTP envelope recipient:

- A Bcc email may not list the alias in `To`.
- Forwarding can alter recipients.
- One email may have multiple `To`/`Cc` addresses.
- Senders can populate headers inconsistent with the envelope.
- Providers may rewrite metadata.

To separate tenants before the flow, prefer **trusted delivery metadata** or platform-issued tokens/aliases. Never extract a tenant ID string from subject/`To` alone and grant permission to update that tenant's data.

## 11. Choosing a Folder Before Searching

IMAP supports mailbox folders:

~~~text
INBOX
INBOX/Support
INBOX/Invoices
INBOX/Notifications
INBOX/Processed
~~~

A receiver scanning only `INBOX/Invoices` reduces traffic compared to scanning everything. However, users can move folders, providers can alter spam filters, or administrators can change rules.

Define a clear policy:

1. Who is authorized to change folder routing?
2. How are messages outside the polled folder handled?
3. Is there reconciliation when a mailbox filter misfiles mail?
4. If a folder is deleted/renamed, does it alert or fail closed?
5. Should messages be archived after durable ingestion?

Folders are a **data-partitioning** technique, not proof of business validation.

## 12. Filtering by Received Date

Example:

~~~java
import java.util.Date;

import jakarta.mail.search.ComparisonTerm;
import jakarta.mail.search.ReceivedDateTerm;

Date lowerBound = /* policy-defined date */;

SearchTerm since =
        new ReceivedDateTerm(
                ComparisonTerm.GE,
                lowerBound
        );
~~~

A search window avoids scanning huge histories, yet never simply store `lastSeenTimestamp` and search for everything "greater than" it:

- Servers may evaluate date search at day granularity.
- Timezones and clocks differ.
- Multiple emails can share the same timestamp.
- Messages can be copied/moved into a folder late.
- Downtime and `UIDVALIDITY` changes happen.

You can scan with a controlled overlap window as needed and rely on UID idempotency to drop duplicates. When using a UID watermark, tie it to `UIDVALIDITY` and resync when the namespace changes.

## 13. Combining Multiple Conditions

Example of unread messages from either of two partner addresses:

~~~java
import jakarta.mail.Flags;
import jakarta.mail.search.AndTerm;
import jakarta.mail.search.FlagTerm;
import jakarta.mail.search.FromStringTerm;
import jakarta.mail.search.OrTerm;
import jakarta.mail.search.SearchTerm;

SearchTerm unseen =
        new FlagTerm(
                new Flags(Flags.Flag.SEEN),
                false
        );

SearchTerm partners =
        new OrTerm(
                new FromStringTerm(
                        "invoices@partner-a.example"
                ),
                new FromStringTerm(
                        "billing@partner-b.example"
                )
        );

SearchTerm candidate =
        new AndTerm(
                unseen,
                partners
        );
~~~

Do not turn an overly complex `SearchTerm` tree into your entire business policy. Keep server-side search predictable. Test Unicode, folder flags, and actual provider behavior in integration tests.

## 14. Attachment and Content Filtering: Limits of Server Search

A rule like:

> Only accept emails with a valid PDF file, a contract signature, and a non-duplicate invoice.

cannot be fully enforced using `SubjectTerm` or `FromStringTerm`.

The pipeline needs:

~~~text
Server candidate search
  -> Fetch metadata
  -> Check size and content bounds
  -> Parse MIME
  -> Save attachment to authorized storage
  -> Malware scan/file validation
  -> Authenticate partner/tenant
  -> Check invoice idempotency
  -> Business processing
~~~

IMAP search narrows candidates, yet cannot inspect PDF contents, business signatures, or tenant ownership. If a provider exposes a proprietary attachment-filtering API, that is provider-specific, not a default feature of Spring Integration Mail.

## 15. Filters Inside IntegrationFlow vs. Server-Side Filters

A flow with `.filter(...)`:

~~~java
@Bean
IntegrationFlow inboundFlow(
        MailReceivingMessageSource source,
        InboundCandidatePolicy policy,
        MailIntakeService intake) {

    return IntegrationFlow
            .from(
                    source,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(
                                    Duration.ofSeconds(30)
                            ).maxMessagesPerPoll(10)
                    )
            )
            .filter(
                    message -> policy.allow(message)
            )
            .handle(intake, "accept")
            .get();
}
~~~

`InboundCandidatePolicy` and `MailIntakeService` are illustrative application APIs. Overloads, filter signatures, and message payload types must match your DSL version.

**This filter step runs after the inbound adapter.** The message has already been brought into the pipeline by the receiver. It helps gate business handlers or route messages, yet does not reduce bytes previously downloaded over IMAP.

If you need to know why an email was dropped, use a discard path/audit or a decision router rather than simply returning `false` and losing visibility.

## 16. maxMessagesPerPoll Is Not a Size Limit

~~~java
Pollers.fixedDelay(
        Duration.ofSeconds(30)
).maxMessagesPerPoll(10)
~~~

`maxMessagesPerPoll` normally caps how many receive calls/messages the poller pulls from the source per polling cycle. It does **not** guarantee:

- Each poll downloads at most 10 MiB.
- MIME attachments are size-limited.
- The receiver does not fetch many metadata/candidates in a single query.
- The whole cluster runs at most 10 jobs.
- Emails are never repeated across polls.

A single 200 MiB message can threaten heap memory even with `maxMessagesPerPoll=1`. Enforce separate size policies, file/part limits, streaming, and bounded concurrency.

## 17. Unseen, Ingested, and Processed Are Three Separate States

| State | Where Stored | Meaning |
| --- | --- | --- |
| `\Seen` | IMAP mailbox | Marked as read |
| `\Deleted` | IMAP mailbox | Marked for deletion |
| `INGESTED` | Intake DB | Email durably persisted |
| `FILTERED_OUT` | Intake DB/audit | Dropped by a rule |
| `PROCESSING` | Business DB | Currently processing |
| `PROCESSED` | Business DB | Business work completed |
| `RETRY` | Job store | Needs reprocessing |
| `QUARANTINED` | Storage/DB | Needs isolation or review |

A dangerous bug:

~~~text
Receiver fetches email
  -> marks Seen or deletes
  -> database insert fails
  -> next poll searches only unseen
  -> email is skipped
~~~

Avoid acknowledgments that exclude messages from search before **required data has been persisted**. If acknowledgment fails after persistence, re-polling and deduplicating is normally the desired recovery path.

## 18. Configuring Marking and Deletion in the Receiver

Common options:

~~~java
receiver.setShouldMarkMessagesAsRead(false);
receiver.setShouldDeleteMessages(false);
~~~

These are sound business choices: they prevent fetched emails from being treated as processed or deleted prematurely. However, if unread messages are not marked read and searches keep looking for `Unseen`, the receiver may emit the same email across multiple polls.

Do not fix duplicates by enabling deletion before saving to the database. Build durable ingestion state with an explicit acknowledgment policy:

~~~text
Discover candidate
  -> Extract identity + permitted content
  -> Persist unique inbox record + job
  -> Commit
  -> Mark/move/ack per policy
~~~

IMAP and the database do not automatically share a single ACID transaction.

## 19. Idempotency: UID, UIDVALIDITY, and Mailbox Namespace

An IMAP message should not be identified by its message sequence number because folder ordering shifts on expunge.

A **UID** is meaningful only inside a folder with a specific **UIDVALIDITY**. A solid inbound key is:

~~~text
mailboxAccountId
  + folderId
  + uidValidity
  + uid
~~~

~~~java
public record ImapMailKey(
        String mailboxAccountId,
        String folderId,
        long uidValidity,
        long uid) {
}
~~~

The `Message-ID` header helps with tracing yet can be missing, duplicated, or forged. It does not replace the mailbox UID key. If the server changes `UIDVALIDITY`, the new namespace must be resynchronized rather than blindly reusing the old "last UID".

### Two Layers of Idempotency

1. **Ingestion:** the same UID in the same namespace creates at most one inbound record.
2. **Business:** one business request triggers side effects according to contract, even if workers retry or two different emails describe the same request.

No single filter operation guarantees end-to-end exactly-once processing.

## 20. Database Unique Constraints Matter

Illustrative schema:

~~~sql
CREATE TABLE inbound_mail (
    id BIGINT PRIMARY KEY,
    mailbox_account_id VARCHAR(128) NOT NULL,
    folder_id VARCHAR(256) NOT NULL,
    uid_validity BIGINT NOT NULL,
    uid BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL,
    first_seen_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_mail_uid UNIQUE (
        mailbox_account_id,
        folder_id,
        uid_validity,
        uid
    )
);
~~~

This is a simplified schema, not representative of every database/dialect. Tests should verify the real unique constraint.

Do not rely solely on:

~~~java
if (!repository.existsByKey(key)) {
    repository.insert(key);
}
~~~

because two threads can both observe "does not exist yet". Database unique constraints and duplicate-key conflict handling form the real race barrier.

## 21. When Should a Message Enter the Business Flow?

A common architecture:

~~~mermaid
flowchart TD
    A["IMAP candidate"] --> B["Resolve UID + metadata"]
    B --> C["Size/security preflight"]
    C --> D["Persist intake unique key"]
    D --> E["Persist raw content/attachment reference"]
    E --> F["Commit"]
    F --> G["Ack/move mailbox"]
    F --> H["Durable processing queue"]
    H --> I["Business validation"]
    I --> J["Idempotent handler"]
~~~

The intake layer should be fast and resource-bounded, while heavy work such as OCR, third-party API calls, or ticket creation can run later from a durable queue.

Never hold a `MimeMessage` tied to an IMAP folder/session inside a job lasting hours. Once the folder closes, lazy content/attachments may become unreadable. Persist the required content before detaching from the receiver.

## 22. Filter Decisions Are Not Just a Boolean

A predicate returning `true`/`false` suits simple flows, yet real systems usually need to know **why** an email was excluded.

~~~java
public enum InboundDecisionType {
    ACCEPT,
    SKIP_ALREADY_INGESTED,
    REJECT_PERMANENT,
    RETRY_LATER,
    QUARANTINE
}
~~~

~~~java
public record InboundDecision(
        InboundDecisionType type,
        String reasonCode) {
}
~~~

Examples:

| Decision | Example | Action |
| --- | --- | --- |
| `ACCEPT` | Properly formatted invoice | Persist and enqueue |
| `SKIP_ALREADY_INGESTED` | UID already exists | Create no new job, retry ack if needed |
| `REJECT_PERMANENT` | Format outside contract | Audit/retain per policy |
| `RETRY_LATER` | Temporary DB or validation outage | Preserve ability to re-read |
| `QUARANTINE` | Corrupted MIME, suspicious file | Isolate, review, and restrict access |

Never equate every `filter=false` case with deleting the email. A DB outage is completely different from an unwanted newsletter.

## 23. Filtering Automated Emails and Avoiding Loops

An application that sends confirmation emails can receive auto-generated responses:

~~~text
Application -> sends acknowledgment
Remote system -> auto-reply
Application -> receives auto-reply and sends another acknowledgment
...
~~~

Signals you can inspect:

- `Auto-Submitted` header.
- Delivery Status Notification / bounce content types.
- Provider-specific headers.
- System-verified return-path/bounce identities.
- Recipient and purpose rules.

Do not rely solely on searching for `Out of office` in subjects, since wording and languages vary widely. Automated emails should never trigger another auto-reply unless governed by an explicit policy. Rate limits and deduplication remain necessary to prevent loops when metadata is forged.

## 24. Mailboxes Shared Across Multiple Tenants

Example:

~~~text
tenant-a+ticket-981@inbound.platform.example
tenant-b+invoice-172@inbound.platform.example
~~~

A mailbox receiving emails for multiple tenants must use **trusted mapping**:

- Reliable envelope recipients or delivery metadata.
- Platform-issued aliases/tokens.
- Verified domain/tenant ownership.
- Business objects scoped to the right tenant.
- Attachment storage keys with matching permissions.

`To`, `From`, and subject headers can all be set by senders or altered during forwarding. Never use them as the sole evidence for updating a tenant's data.

If using a dedicated mailbox per tenant, still manage poller counts, secrets/credentials, connection quotas, idempotency namespaces, and account revocation.

## 25. Multiple Instances Polling the Same Mailbox

~~~text
Pod A -> IMAP search -> UID 123
Pod B -> IMAP search -> UID 123
Pod A -> insert inbox record
Pod B -> insert inbox record
~~~

IMAP does not automatically distribute messages across consumers like a consumer group. The `Seen` flag is not a distributed lock.

Options:

- Allow only one active poller per mailbox.
- Distributed lease/leader election.
- Partition mailboxes across workers.
- Unique constraints blocking duplicate ingestion.
- Business idempotency for side effects.
- Reconciliation after crashes and lease expiration.

A lease needs an owner, TTL, and fencing against stale workers writing after ownership moved. An in-memory boolean cannot coordinate multiple JVMs.

## 26. Error Handling During Filtering and Acknowledgment

| Failure Point | Risk | Mitigation |
| --- | --- | --- |
| IMAP search timeout | Candidates missed | Backoff/retry poll |
| Authentication failure | Cannot read inbox | Refresh credentials/alert |
| MIME parse failure | Poison message | Quarantine/reason code |
| Oversized attachment | Heap/disk pressure | Bounded rejection |
| DB insert failure | Fails to persist | Do not mark/delete |
| Ack failure after commit | Email re-fetched | Deduplicate and retry ack |
| User flags changed | Search skips mail | Reconciliation |
| `UIDVALIDITY` changed | Cursor invalidated | Resync namespace |
| Rule change | False negatives | Audit and rollback |
| Temporary business validation outage | Processing incomplete | Retry business job |
| Tenant mismatch | Cross-tenant risk | Reject and security audit |

Spring Integration has error channels and error handlers, yet an error pushed to a channel **does not automatically roll back IMAP flags or database transactions**. Identify which side effects already happened and which steps are safe to retry.

## 27. Performance and Backpressure

If an inbox receives 500 emails/minute while business processors handle 100/minute, polling faster will not raise business throughput.

Required controls:

- Appropriate poll interval.
- Limit candidates/batch size.
- Control IMAP connection counts.
- Bounded intake/worker concurrency.
- Size limits and attachment streaming.
- Durable queue instead of holding MIME objects in RAM.
- Per-mailbox/provider rate limits.
- Throttling when storage/database nears capacity.
- Monitoring age of unprocessed emails.

A single 100 MiB email can cause trouble even with `maxMessagesPerPoll=1`. Distinguish task counts from byte/data budgets.

## 28. Monitoring and Filter Explainability

| Metric | Purpose |
| --- | --- |
| `mail_inbound_poll_total` | Poll count |
| `mail_inbound_search_candidates_total` | Candidates returned by server |
| `mail_inbound_fetched_total` | Messages fetched |
| `mail_inbound_accepted_total` | Messages accepted into intake |
| `mail_inbound_filtered_total` | Dropped counts by reason |
| `mail_inbound_duplicate_total` | UIDs already present |
| `mail_inbound_quarantined_total` | Quarantined counts |
| `mail_inbound_ack_failure_total` | Ack/move failures |
| `mail_inbound_search_duration_seconds` | Search latency |
| `mail_inbound_backlog_age_seconds` | Processing wait time |
| `mail_inbound_resync_total` | Rescan counts |
| `mail_inbound_lease_conflict_total` | Poller contention |

Use internal mailbox IDs, protocols, rule IDs, and reason codes as labels. Never put email addresses, subjects, raw Message-IDs, or attachment names into metric labels to avoid leaking PII and creating high cardinality.

Alert when:

- Filtered ratio spikes abruptly.
- Candidate count drops abnormally after a deploy.
- Time since last successful poll exceeds SLA.
- Duplicates or quarantines spike.
- `UIDVALIDITY` changes without resync.
- DB errors occur while mailbox flags still mutate.
- Valid emails get stuck outside the polled folder.
- Backlog grows and processing latency breaches SLA.

## 29. Changing Filters Safely

An overly strict `SearchTerm` can cause valid emails to vanish from application visibility. Rollout procedure:

1. Define the rule's goal: reduce spam, cut traffic, or enforce validation?
2. Separate metadata heuristics from authorization.
3. Record rule ID/version in ingestion audits.
4. Test against both valid and invalid fixtures.
5. Where possible, run **shadow evaluation**: log new decisions without actually dropping mail.
6. Monitor candidate/accepted/filtered ratios.
7. Roll out gradually by mailbox or tenant.
8. Maintain a rollback path.
9. Do not immediately delete rejected emails before building confidence.
10. Support policy-driven replay/reconciliation.

A scoped log:

~~~text
mailboxId: mailbox-17
uidNamespace: 381
uid: 1062
ruleVersion: 8
decision: QUARANTINE
reasonCode: UNEXPECTED_ATTACHMENT_TYPE
~~~

Never log raw bodies, tokens, or attachments. Storing the rule version explains why an email was filtered out at that point in time.

## 30. Testing Search Strategies

You can unit test a `SearchTerm` against a small `MimeMessage`:

~~~java
@Test
void matchesExpectedInvoiceSubject()
        throws Exception {

    MimeMessage message =
            new MimeMessage(
                    Session.getInstance(
                            new Properties()
                    )
            );

    message.setSubject(
            "[Invoice] INV-981",
            "UTF-8"
    );

    SearchTerm term =
            new SubjectTerm("[Invoice]");

    assertTrue(term.match(message));
}
~~~

Common imports:

~~~java
import java.util.Properties;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import jakarta.mail.search.SearchTerm;
import jakarta.mail.search.SubjectTerm;
~~~

Local testing of `SearchTerm.match` does not guarantee a real IMAP server evaluates Unicode/flags/dates identically. Add integration tests against an appropriate server when relying on server-side behavior.

## 31. Testing Filter Policies

Metadata DTO example:

~~~java
public record InboundMailMetadata(
        String mailboxAccountId,
        String folderId,
        String senderAddress,
        String subject,
        long declaredSizeBytes,
        String messageIdHeader) {
}
~~~

A decision test:

~~~java
@Test
void quarantinesOversizedCandidate() {

    InboundMailMetadata candidate =
            new InboundMailMetadata(
                    "account-a",
                    "INBOX",
                    "sender@example.test",
                    "[Invoice] INV-981",
                    50L * 1024 * 1024,
                    "test@example.test"
            );

    InboundDecision decision =
            policy.evaluate(candidate);

    assertEquals(
            InboundDecisionType.QUARANTINE,
            decision.type()
    );
}
~~~

`policy` is an application component constructed by the test. `declaredSizeBytes` is preliminary metadata; enforce limits on actual bytes read so false headers cannot bypass checks.

Additional test cases: `ACCEPT`, duplicate UID, unknown partner, malformed MIME, temporary DB failure, and tenant mismatch.

## 32. Integration Testing with an IMAP Test Server

An integration test can use GreenMail or a test IMAP server:

~~~text
IMAP test server
  -> seed valid and invalid emails
  -> ImapMailReceiver + SearchTermStrategy
  -> polling inbound adapter
  -> intake service + repository
  -> assertions by UID/correlation
~~~

Steps:

1. Initialize an isolated test mailbox.
2. Seed an email with a matching subject.
3. Seed a non-matching email.
4. Trigger a controlled poll.
5. Verify the matching candidate is ingested.
6. Poll a second time to verify duplicate handling.
7. Simulate a DB failure and verify no ack loses the email.
8. Check the `Seen` flag and `UIDVALIDITY`.
9. Clean up test server/fixtures.

Never use a production inbox in automated tests, as tests can flip read flags, delete real mail, or leak credentials.

For async polling, avoid fixed `Thread.sleep` calls. Wait conditionally with Awaitility when that test dependency is present:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() -> {
            assertTrue(
                    inboundRepository.existsByCorrelationId(
                            correlationId
                    )
            );
        });
~~~

These are illustrative test helpers/repository methods; message IDs must be scoped to the current test.

## 33. Scenario Matrix

| Scenario | Expected Result |
| --- | --- |
| Empty inbox | No business job created |
| Matching subject | Candidate enters intake per policy |
| Non-matching subject | Not processed; clear reason/retention |
| Spoofed `From` header | Grants no business permissions |
| Already `Seen` email | Handled per search/reconciliation policy |
| Re-polling same UID | No duplicate side effects |
| `UIDVALIDITY` changed | Namespace resync |
| Two replicas poll same UID | Protected by unique constraint/lease |
| DB failure before commit | Not marked/deleted, no lost mail |
| Ack failure after commit | Re-poll deduplicates |
| Malformed MIME | Quarantined without blocking entire inbox |
| Oversized attachment | No OOM |
| Auto-reply | No mail loop created |
| Wrong tenant alias | Does not update another tenant |
| POP3 lacks IMAP SEARCH | Client-side filtering per capability |
| Filter rule change | Audited, rolled out, and rollbackable |
| Parallel tests | Never share one inbox for assertions |

**Verification note:** filtering after the adapter blocks downstream processing while still fetching the message. To verify server-side filtering, observe search/receiver behavior in a real IMAP environment.

## 34. Common Mistakes

### 34.1. Calling IntegrationFlow.filter Server-Side Filtering

Wrong: it runs inside the flow, after the inbound adapter. To reduce candidates before fetching, use folder selection and receiver search.

### 34.2. Using Unseen Alone for Deduplication

`Seen` can be changed by other clients and is not a business acknowledgment. Use UID/idempotency.

### 34.3. Deleting Emails Whenever filter=false

Can delete valid emails. Require decision types, reason codes, and retention policies.

### 34.4. Marking Seen Before DB Commit

A DB failure can cause the email to be skipped in the next poll.

### 34.5. Using Message-ID as the Sole Unique Key

The header can be missing, duplicated, or forged. Use the mailbox UID namespace.

### 34.6. Using IMAP Message Sequence Numbers as Cursors

Sequence numbers shift on expunge. Use UID paired with `UIDVALIDITY`.

### 34.7. Treating From or Subject as Authorization

Senders can forge metadata. Business policies must verify identity separately.

### 34.8. Filtering PDFs by Filename and Content-Type

Both are untrusted metadata. Inspect content and scan files.

### 34.9. Treating maxMessagesPerPoll as a Memory Cap

One huge email can still exhaust heap. Bound bytes and part counts.

### 34.10. Date-Based Searching Without Overlap

Late-arriving or same-timestamp emails can be skipped. Combine rescanning with idempotency.

### 34.11. Multiple Pods Polling Without Unique Constraints

Causes double ingestion or duplicate job creation.

### 34.12. Ignoring Default Search Semantics When Customizing SearchTermStrategy

Can accidentally fetch stale mail or drop needed emails.

### 34.13. Keeping Live MimeMessage Objects in Long-Lived Queues

IMAP folders/sessions can close. Persist required data beforehand.

### 34.14. Filtering All Auto-Replies by Subject Alone

Languages and providers vary. Use multiple signals and loop protection.

### 34.15. Not Monitoring Filtered Mail Counts

Can silently drop valid emails after a rule change.

### 34.16. Using the To Header to Isolate Tenants Without Verification

Forwarding/Bcc/spoofing can cause cross-tenant routing. Use trusted mappings.

### 34.17. Treating DB Errors as Permanent Rejections

DB outages require retries, never deleting mail.

### 34.18. Using a Production Inbox for Integration Tests

Can flip flags or delete real mail. Use an isolated test server/mailbox.

## 35. Practice Questions

**Q1.** To reduce how many messages the IMAP server fetches, where should rules be placed?

Folder selection and `SearchTermStrategy` on the receiver, within server capabilities.

**Q2.** Does `IntegrationFlow.filter` prevent emails from being fetched over IMAP?

No. It only blocks the downstream path at that point in the flow.

**Q3.** Is an `Unseen` email guaranteed to be unprocessed by business logic?

No. That is a mailbox flag, not intake DB state.

**Q4.** Does a Subject containing `[Invoice]` prove a valid invoice?

No. You must verify partner, content, tenant, and business authorization.

**Q5.** Should `FromStringTerm` be used as strong identity verification?

No. `From` headers can be spoofed.

**Q6.** The DB saved the email, yet IMAP mark `Seen` failed; what happens on the next poll?

Use the UID unique key to deduplicate, and optionally retry the ack.

**Q7.** Does UID 100 across two different `UIDVALIDITY` values guarantee the same email?

No. A UID is meaningful only within its current namespace.

**Q8.** Do two workers polling the same mailbox automatically get partitioned by IMAP?

Not by default. You need leases and/or unique constraints.

**Q9.** Can oversized attachments be blocked completely using `SubjectTerm`?

No. You need size limits and bounded parsing/streaming.

**Q10.** Should an email rejected due to a temporary DB error be deleted?

No. Retry without losing data.

**Q11.** Does POP3 support IMAP SEARCH identically?

No. Design filtering around POP3 capabilities.

**Q12.** Does the `To` header always identify the email's true tenant?

No, especially with Bcc/forwarding. Use trusted mappings.

**Q13.** A new rule cuts accepted mail by 90%. What should you do?

Inspect candidate/filtered metrics, reason codes, server behavior, false negatives, and rollback/reconciliation.

**Q14.** Why avoid pushing live `MimeMessage` objects onto a queue for hours?

Because folders/sessions can close and lazy content becomes inaccessible.

**Q15.** Are `filter=false` and quarantine the same thing?

No. Quarantine is an explicit decision with a reason code, access controls, and retention; `false` alone under-specifies the action.

## 36. Mental Model

~~~mermaid
flowchart TD
    A["Mailbox / folder"] --> B["IMAP SearchTerm"]
    B --> C["Receiver / fetch"]
    C --> D["UID + metadata + bounds"]
    D --> E{"Already ingested?"}
    E -->|"Yes"| F["Dedup / ack policy"]
    E -->|"No"| G["Candidate policy"]
    G --> H{"Decision"}
    H -->|"ACCEPT"| I["Durable intake"]
    H -->|"RETRY"| J["Keep opportunity to re-read"]
    H -->|"QUARANTINE"| K["Store reason + isolate"]
    H -->|"REJECT"| L["Audit + retention"]
    I --> M["Spring Integration flow"]
    M --> N["Business authorization"]
    N --> O["Idempotent processing"]
~~~

Remember these principles:

1. **Pre-adapter filtering differs from in-flow filtering**; `.filter(...)` after the adapter does not eliminate server fetch cost.
2. **Server-side search only selects candidates**; it never proves an email is safe or business-valid.
3. **IMAP and POP3 have different filtering capabilities**; POP3 lacks full IMAP SEARCH.
4. **Seen is not processed**; durable ingestion state is required.
5. **Never mark/delete before persisting** if doing so risks skipping messages.
6. **Deduplicate IMAP by mailbox + folder + UIDVALIDITY + UID**, not `Message-ID` alone.
7. **From/To/Subject are untrusted metadata**; never authorize actions via a search term.
8. **MIME/attachments need size caps, parsing bounds, and scanning**, not just subject matching.
9. **Decisions need reason codes and retryability**, not a bare boolean for every outcome.
10. **Multiple replicas need leases/idempotency**; never treat IMAP flags as distributed locks.
11. **Date-based searches need rescanning/overlap** to avoid missing emails.
12. **Never hold live MimeMessage objects in long-lived queues**; persist required data upfront.
13. **Monitoring accepted/filtered/quarantine/duplicates** catches overly aggressive rules.
14. **Rule changes need versioning, staged rollout, and rollback** to avoid losing valid mail.
15. **Test search, policy, database idempotency, and IMAP integration at each boundary**.

In Spring Integration Mail, effective email filtering is more than adding `subject.contains(...)`. Place each rule in the right layer: **IMAP search and folders to narrow candidates, intake to enforce resource bounds and idempotency, the flow to orchestrate data, and the business layer to verify permissions and side effects**. When these boundaries are clear, the system drops irrelevant messages without losing critical emails and can explain why every message was accepted or excluded.
