# Unsubscribes and Do-Not-Contact Requests

In an email-sending system, a message can have accurate content, a DKIM signature, and SMTP server acceptance yet still harm deliverability if the recipient **no longer wants to receive it**. Continuing to send unwanted emails raises the risk of users clicking **Report spam**, email providers throttling traffic, or sending addresses losing reputation. Therefore, **unsubscribe** support and handling **opt-out / do-not-contact** requests are an essential part of *deliverability*, not a decorative link at the bottom of an email.

In Spring Framework Mail, **JavaMailSender** and **MimeMessageHelper** are responsible for composing and sending messages. They **do not automatically manage** unsubscribed user states, blocklists, email topic choices, or do-not-contact requests. Those rules must be implemented at the business, data, and dispatch layers; the email composer may send only after the system decides the message is valid for the recipient and email type.

This lesson covers: classifying emails and opt-out scopes; generating **List-Unsubscribe** and **one-click unsubscribe**; designing endpoints, tokens, and databases; checking sending permission at every dispatch; handling retries, race conditions, and webhooks; plus Java/Spring examples, testing, and operations. Relevant technical standards are explained as general principles; legal requirements and specific provider rules must be verified by jurisdiction, service type, and deployment timing.

## 1. Distinguishing Unsubscribe, Opt-Out, Suppression, and Delivery Failure

Several concepts are often used interchangeably:

| Concept | Meaning | Example |
| --- | --- | --- |
| **Unsubscribe** | Recipient requests stopping one or more subscribed email streams | Leave weekly newsletter |
| **Opt-out / do-not-contact** | Recipient withdraws consent for a communication type or all communications within a defined scope | Stop receiving promotional emails |
| **Preference center** | Where recipients pick topics, cadence, or channels | Receive product updates only, no offers |
| **Suppression list** | List enforced at dispatch time to block sending to a recipient or specific scope | Block all marketing email to address A |
| **Complaint** | Recipient marks a message as spam with their mailbox provider | Feedback loop reports complaint |
| **Hard bounce** | Persistent delivery failure, e.g., nonexistent mailbox | SMTP reports recipient address invalid |
| **Soft bounce** | Temporary or inconclusive delivery failure | Mailbox full, receiving server temporarily rejects |

A user unsubscribing reflects **recipient intent**; a hard bounce is a **technical signal about delivery capability**. Both can lead to suppression, yet their **reason**, blocking scope, duration, and recoverability differ.

For example, a user leaving a newsletter does not mean their account no longer exists or cannot receive password-change confirmations. Conversely, a continuously hard-bouncing address should not be retried forever merely because the preference center still says "subscribed."

### Consent and Preferences Are More Than One Boolean

A single **subscribed = true/false** flag in a users table is usually insufficient:

- One address can belong to multiple tenants.
- A user can subscribe to multiple newsletter types.
- The same address can serve multiple distinct accounts.
- A user can opt out of marketing emails while still needing security alerts.
- A global do-not-contact takes precedence over individual newsletter subscriptions.
- Consent grants and withdrawals require history and timestamps.

Instead of one flag, explicitly model **recipient + channel + purpose/category + scope**.

## 2. Classify Emails Before Deciding Whether Unsubscribe Applies

A Spring Mail system typically runs several email streams:

| Group | Example | Preference Design |
| --- | --- | --- |
| **Marketing/promotional** | Promotions, newsletters, product marketing | Clear unsubscribe mechanism; must honor opt-outs |
| **Product updates / non-essential** | New feature news, community events | Policy-dependent; usually allows opting out or picking topics |
| **Transactional / service** | Order confirmations, receipts, request status updates | Handled per transactional purpose; limit promotional content |
| **Security/critical** | Login verification, password-change alerts | Controlled for security purpose; never used to bypass marketing opt-outs |
| **Operational notices** | System maintenance, major account changes | Needs concrete classification per context and product obligations |

**Do not label something transactional by default to skip unsubscribe.** If an order confirmation email includes a large promotional campaign, classification by actual purpose may differ from the class or template name. Separate marketing content from essential messages and check applicable rules.

Likewise, do not unconditionally block all system emails just because a user turned off newsletters. Dropping a password recovery email harms account usability. Email-category policies should be defined alongside product, privacy, and legal teams where applicable.

### Designing Meaningful Notification Purposes

~~~java
public enum MailPurpose {
    MARKETING_NEWSLETTER,
    MARKETING_PROMOTION,
    PRODUCT_ANNOUNCEMENT,
    ORDER_RECEIPT,
    SECURITY_ALERT
}
~~~

An application policy function can distinguish:

~~~java
public enum ConsentRequirement {
    MARKETING_OPT_IN,
    NON_ESSENTIAL_PREFERENCE,
    SERVICE_POLICY,
    SECURITY_POLICY
}
~~~

Neither enum above is a built-in Spring Mail API; they are application-defined business concepts. What matters is that **purpose is assigned by a trusted workflow**, never allowing callers to arbitrarily pick SECURITY_ALERT to bypass suppression.

### One Email Should Have One Primary Purpose

Mixing promotional copy into payment receipts makes it hard to know whether marketing unsubscribes must apply to the whole email. A better approach is usually:

1. Send the transactional receipt with essential content.
2. Send promotions via a separate stream only to eligible recipients.
3. Record distinct statuses/identifiers per notification.

This makes auditing and opt-out enforcement far cleaner.

## 3. Scope of a "Do-Not-Contact" Request

An unsubscribe request must specify **what to stop, for whom, and in which scope**.

Example:

~~~text
Recipient:        customer-392
Channel:          EMAIL
Tenant:           shop-7
List/Purpose:     NEWSLETTER_WEEKLY
Effective state:  UNSUBSCRIBED
Updated at:       2026-11-12T09:15:00Z
Source:           ONE_CLICK_UNSUBSCRIBE
~~~

A recipient may opt out of **a specific list**, **all marketing emails from a brand**, or **all non-essential communications**, depending on presented choices and agreements. Never silently turn "no newsletters" into canceling security alerts; nor interpret "stop all promotions" as blocking only one campaign.

### Rule Precedence Order

One way to express policy:

~~~text
Global do-not-contact / mandatory suppression
                  |
                  v
   Block by tenant or sender brand
                  |
                  v
          Block by purpose/list
                  |
                  v
       Recipient-specific preference
                  |
                  v
        Workflow sending conditions
                  |
                  v
              ALLOW / DENY
~~~

Logic examples:

- If the recipient is under global marketing suppression, send no marketing email at all, even if an individual list still has subscribed=true.
- If the recipient left only the newsletter, they can still receive other product notices **when that notice's policy and consent allow**.
- If the provider reports a complaint/hard bounce, apply dedicated deliverability suppression and never try to bypass it with another sender.
- If a user just unsubscribed, the new suppression state must take precedence over older queued marketing jobs.

A policy engine should return a result along with a **reason code** rather than just a boolean:

~~~text
DENIED_GLOBAL_OPT_OUT
DENIED_LIST_UNSUBSCRIBE
DENIED_NO_VALID_CONSENT
DENIED_HARD_BOUNCE
DENIED_COMPLAINT
ALLOWED
~~~

This reason aids observability and operations without logging excessive personal information.

## 4. Why Does Deliverability Depend on Honoring Unsubscribes?

Users who cannot find a way to unsubscribe may:

- Report the message as spam.
- Block the sender or domain.
- Mass-delete messages without engaging.
- File complaints with providers, support, or regulators.

These signals influence how receiving systems evaluate your traffic. Delivery capability is not decided solely by DNS settings or calling **mailSender.send(...)** without throwing; **how much recipients want the mail** matters long-term.

A good unsubscribe flow typically has these traits:

1. **Easy to find:** recipients clearly see how to stop messages.
2. **Low friction:** do not force login just to stop marketing emails when one-click fits.
3. **Accurately scoped:** explains which list/topic is being canceled.
4. **Idempotent:** clicking multiple times causes no divergent effects or confusing errors.
5. **Enforced:** the updated state blocks already-pending sending jobs too.
6. **Observable:** logs/audits state changes and request sources.
7. **Non-bypassable:** bulk flows, retries, requeues, and provider APIs all honor the same suppression policy.

## 5. Unsubscribing via Links in the Email Body

A marketing email can include:

~~~text
You received this message because you subscribed to the product newsletter.
Unsubscribe: https://mail.example.test/preferences/u/<opaque-token>
~~~

Matching HTML part:

~~~html
<p>
  You received this message because you subscribed to the product newsletter.
  <a href="https://mail.example.test/preferences/u/opaque-example">
    Unsubscribe
  </a>
</p>
~~~

In production, the URL contains a real server-generated token, not a string guessable from an email address. Clicking the link can take the user to a confirmation page or preference center depending on workflow.

### Do Not Force Users to Re-Enter Passwords to Stop Marketing

When trying to stop a newsletter, a flow requiring account creation, login, OTP entry, and multiple pages frustrates users and drives them to click "Report spam" instead of unsubscribing. Cancellation must be easy while still protecting tokens and request scope.

### GET Must Not Mutate State

Many email clients and security scanners automatically open/scan links in emails. If **GET /unsubscribe/token** alone sets UNSUBSCRIBED, a link scanner can accidentally unsubscribe users.

A safer implementation:

- **GET** renders a confirmation/info page without changing state.
- **POST** executes the cancellation for a valid token.
- For standard one-click, mailbox providers issue a dedicated **POST** specification.

Distinguish an in-body link for human interaction from the **one-click unsubscribe header** discussed next.

## 6. MIME Headers Supporting Unsubscribe

Alongside the HTML/plain-text footer, list-style emails can add **List-Unsubscribe** to give email clients header-level unsubscribe metadata.

Example:

~~~text
List-Unsubscribe: <https://mail.example.test/u/abC123opaque>, <mailto:leave-newsletter@example.test>
~~~

This header describes mechanisms the sender supports. Many email clients can use it to offer an **Unsubscribe** action in their UI without making recipients hunt for a footer link.

### List-Unsubscribe Is Not a Sending Blocker by Itself

Simply adding the header to a message **does not automatically block the user on the next send**. The system must implement the endpoint/email processor, update preferences or suppression in the database, and check state before subsequent sends.

If the URL in the header returns an error, the endpoint does not exist, or it only sends recipients to a login page without handling the request, the unsubscribe experience will fail.

### Methods Represented in the Header

| Method | Meaning | Notes |
| --- | --- | --- |
| **HTTPS URL** | Unsubscribe endpoint or page on sender's system | URL must use a trusted domain and valid token/scope |
| **mailto:** | Email address receiving unsubscribe requests | Must have a mailbox processor mapping requests to recipient/list |
| **One-click POST** | Direct POST execution per RFC 8058 | Requires List-Unsubscribe-Post and compliant endpoint |

If offering **mailto**, you must actually process emails sent to that address. Listing a mailto address with no worker watching it does not fulfill unsubscribe requirements.

### Never Concatenate Headers from Unchecked Input

URLs and mailboxes appearing in headers should come from application configuration and server-generated tokens. Do not write:

~~~java
message.setHeader(
        "List-Unsubscribe",
        request.unsubscribeUrl()
);
~~~

because a request could trick the sender into advertising an untrusted endpoint or wrong scope. Header names are constants, URLs are built from trusted base URLs and scoped tokens, and every header value must be checked against control characters.

## 7. One-Click Unsubscribe per RFC 8058

**RFC 8058** defines using two headers:

~~~text
List-Unsubscribe: <https://mail.example.test/one-click/opaque-token>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
~~~

Meaning:

- **List-Unsubscribe** supplies the HTTPS URI handling the request.
- **List-Unsubscribe-Post** declares the sender supports one-click POST.
- When a recipient triggers unsubscribe in a supporting email client, the client/provider can send an **HTTP POST** to the HTTPS URI.
- The request body under the one-click mechanism includes the form field **List-Unsubscribe=One-Click**.
- The endpoint receiving POST must execute unsubscribe per token/scope without requiring further interaction.

Illustrative request example:

~~~http
POST /one-click/opaque-token HTTP/1.1
Host: mail.example.test
Content-Type: application/x-www-form-urlencoded

List-Unsubscribe=One-Click
~~~

This is an abbreviated HTTP layout. The token name is a placeholder; production must use an unpredictable value generated for the specific notification scope or recipient.

### Why Use POST Instead of GET?

Security systems routinely fetch URLs inside emails to analyze links. If GET triggered unsubscribes, link scanners would cause unintended opt-outs. RFC 8058 uses POST to distinguish an explicit action from ordinary link fetches.

Hence:

~~~text
GET /one-click/token
    -> Does not change preference/suppression

POST /one-click/token
Body: List-Unsubscribe=One-Click
    -> Marks unsubscribed for the exact scope
~~~

### One-Click Must Truly Be One Action

Do not turn one-click POST into a chain:

~~~text
POST -> login -> CAPTCHA -> choose reason -> click Confirm
~~~

An endpoint serving one-click should resolve recipient/list from the token and **update state immediately** on a valid request; you can offer a preference center as an optional footer link, yet never require it to complete one-click.

### Unsubscribing Must Never Grant Re-Opt-In

An unsubscribe token must only have authority to **reduce** non-essential sends by design, never authority to re-subscribe. If a user wants to re-subscribe, require an explicit workflow with evidence per consent policy. Never build a toggle endpoint, as repeated POSTs or bots could turn a canceled subscription back on.

### DKIM and Unsubscribe Headers

RFC 8058 requires one-click headers to be protected by a suitable **DKIM signature**. If the sender adds List-Unsubscribe yet the SMTP/ESP provider strips it or signs the message without covering those headers, mailbox providers may refuse to display or trust the one-click action.

In practice, DKIM signing is typically performed by the **mail provider or outbound-boundary system**, not by MimeMessageHelper. Inspect raw messages on the receiving side to confirm List-Unsubscribe and List-Unsubscribe-Post are preserved and properly signed. Do not treat calling setHeader before JavaMailSender.send(...) as proof of valid DKIM.

### Deliverability and Provider-Specific Requirements

Some providers enforce mandates on bulk/marketing traffic, including domain authentication, easy unsubscribe mechanisms, and compliant one-click. Requirements, thresholds, and processing deadlines can change. Consult your current provider's sender-requirements documentation rather than treating a fixed number in an article as a universal global rule.

## 8. Adding List-Unsubscribe with Spring Mail

With **JavaMailSender** and **MimeMessageHelper**, the application can set headers via the **MimeMessage** API:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class NewsletterComposer {

    private final JavaMailSender mailSender;

    public NewsletterComposer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public MimeMessage compose(
            String recipient,
            String subject,
            String htmlBody,
            String oneClickUrl
    ) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("newsletter@example.test");
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(htmlBody, true);

        message.setHeader(
                "List-Unsubscribe",
                "<" + oneClickUrl + ">"
        );
        message.setHeader(
                "List-Unsubscribe-Post",
                "List-Unsubscribe=One-Click"
        );

        return message;
    }
}
~~~

This example illustrates only the **header-addition mechanics**, assuming recipient, subject, HTML, and URL were generated/validated by application policy. Never pass oneClickUrl from an arbitrary request; build it from a trusted HTTPS host and server-generated token. In production code, use a dedicated service/policy to verify **the recipient is permitted to receive the newsletter** before composing and before submitting.

### URLs in List-Unsubscribe Must Be Safely Constructed

One way to build them:

~~~java
import java.net.URI;

public final class UnsubscribeUrls {

    private static final String PUBLIC_BASE =
            "https://mail.example.test";

    private UnsubscribeUrls() {
    }

    public static URI oneClick(String token) {
        if (!token.matches("[A-Za-z0-9_-]{32,128}")) {
            throw new IllegalArgumentException(
                    "Malformed token"
            );
        }

        return URI.create(
                PUBLIC_BASE + "/one-click/" + token
        );
    }
}
~~~

**PUBLIC_BASE** must come from trusted server configuration, not from unvalidated HTTP Host or X-Forwarded-Host headers. Base64url tokens contain no CR/LF and fit cleanly into a URL path segment after strict validation. In real applications, ensure generated token format and validation regex stay consistent.

### Body Content Still Needs an Easy-to-Find Unsubscribe Option

One-click headers serve email clients/providers; not every email client displays an unsubscribe button. Marketing emails should still include a clear unsubscribe link in both HTML and plain-text footers, bound to the exact recipient/list.

### When There Are Multiple Marketing Lists

A message may belong to newsletter A, promotion B, or announcement C. The one-click URL must cancel the exact **subscription list** the message represents. If a sender uses one global URL for all mail types, confirm that is a deliberate product commitment; otherwise it unsubscribes too broadly.

It is not safe to put only the recipient's email in the URL without tenant/list/scope info and token verification.

## 9. Unsubscribe Tokens Must Be Unpredictable and Clearly Scoped

One-click must run without recipient login, so the URL acts as a **bearer capability**: whoever holds a valid token can execute the action bounded by that token. Thus tokens must:

- Be generated by a cryptographically secure random number generator.
- Have enough entropy to resist guessing or brute force.
- Bind to recipient, tenant, list/purpose, and the unsubscribe action.
- Contain no email addresses, sequential user IDs, or readable personal info.
- Permit **unsubscribe only**, never privilege escalation or re-subscription.
- Have storage, revocation, and lifetime policies matching support needs for older emails.

### Generating Random Tokens in Java

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class UnsubscribeTokens {

    private static final SecureRandom RANDOM = new SecureRandom();

    private UnsubscribeTokens() {
    }

    public static String generate() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }
}
~~~

32 random bytes yield a base64url token around 43 characters long. Never use **sequential UUIDs**, timestamps, email addresses, or order numbers alone as unsubscribe tokens. You do not need to embed all metadata in the URL; metadata can live server-side keyed by token hash.

### Store Hashes Instead of Raw Tokens

When generating a token, the application can store the **SHA-256 hash** of the token in the database and place only the raw token in the email. On receiving POST:

1. Validate token format.
2. Hash the received token with the same algorithm.
3. Look up the record by hash.
4. Resolve recipient/list/tenant bound to the record.
5. Update suppression idempotently.

High-entropy random tokens make SHA-256 suitable as a lookup key while reducing exposure of raw bearer tokens from the database. For low-entropy secrets like human-chosen passwords, use a brute-force-resistant hashing scheme; do not infer SHA-256 suffices for all secret types.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class UnsubscribeTokenHashes {

    private UnsubscribeTokenHashes() {
    }

    public static String sha256(String token) {
        try {
            byte[] digest = MessageDigest
                    .getInstance("SHA-256")
                    .digest(
                            token.getBytes(StandardCharsets.US_ASCII)
                    );
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                    "SHA-256 is not supported",
                    ex
            );
        }
    }
}
~~~

In production, hash only strings that passed base64url/ASCII validation. **Never log raw tokens**, never attach tokens to metric labels, and restrict access to proxy access logs.

### Token Lifetime: Balancing Security and Ability to Unsubscribe

An unsubscribe link in an older email may still be opened months later. If tokens expire too early with no fallback, recipients lose the ability to stop emails. Conversely, keeping tokens indefinitely extends exposure windows if URLs leak.

Choose TTL per product policy, provider requirements, and account recovery needs. You can use long-lived tokens scoped strictly to **unsubscribe-only**, refresh links in newer emails, or offer an accessible preference center. Do not use short-lived tokens that render one-click useless shortly after sending.

## 10. Opt-Out Requests Must Be Idempotent

Recipients may click unsubscribe multiple times; mailbox providers may retry POST on timeout; or concurrent requests may hit the same endpoint simultaneously.

Expected behavior:

~~~text
POST attempt 1 -> state UNSUBSCRIBED
POST attempt 2 -> still UNSUBSCRIBED
POST attempt 3 -> still UNSUBSCRIBED
~~~

A repeated POST must **not** flip state back to SUBSCRIBED. This is why toggle-style endpoints must not be used.

### Distinguishing Idempotency from Omitting Audits

State updates must be idempotent, yet the system can still record calls/replays for monitoring or security within sensible bounds. Not every POST needs to emit a brand-new business event or send a new opt-out confirmation email; doing so could keep sending unwanted emails to someone who just unsubscribed.

### Emit No Marketing Emails After Confirming Cancellation

Once the endpoint returns success, sending policies across all workers/campaigns must observe the new state. An API that only logs "request received" while campaigns keep sending for hours without updating suppression is a risky design. If asynchronous processing exists, define effective cutoffs clearly and ensure dispatch jobs honor this state.

## 11. Designing Subscription, Token, and Suppression Data

A system can separate data into three groups:

1. **Subscription/preference:** whether the recipient opted into a specific list or content type.
2. **Suppression:** blocking decisions due to global opt-out, complaints, bounces, or other policies.
3. **Unsubscribe token/audit:** tokens mapped to recipient/list and history of processed requests.

Simple illustrative PostgreSQL schema:

~~~sql
CREATE TABLE mail_subscription (
    tenant_id VARCHAR(80) NOT NULL,
    recipient_id VARCHAR(120) NOT NULL,
    list_id VARCHAR(120) NOT NULL,
    subscribed BOOLEAN NOT NULL,
    source VARCHAR(80) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, recipient_id, list_id)
);

CREATE TABLE mail_suppression (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    recipient_id VARCHAR(120) NOT NULL,
    scope VARCHAR(80) NOT NULL,
    reason VARCHAR(80) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_mail_suppression
        UNIQUE (tenant_id, recipient_id, scope, reason)
);

CREATE TABLE mail_unsubscribe_token (
    id UUID PRIMARY KEY,
    token_hash CHAR(64) NOT NULL UNIQUE,
    tenant_id VARCHAR(80) NOT NULL,
    recipient_id VARCHAR(120) NOT NULL,
    list_id VARCHAR(120) NOT NULL,
    purpose VARCHAR(80) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    unsubscribed_at TIMESTAMPTZ
);
~~~

This schema is **illustrative**, not an entity/JPA schema generated by Spring Mail. Scope names, reasons, recipient identities, and policies must match the product model. If consent is tracked by email address instead of account ID, model the relationship between verified emails and users/tenants explicitly.

### Why Not Use a Single unsubscribed_emails Table?

For a simple app, one blocklist of emails may suffice initially. Yet with multiple tenants, lists, and mail types, you must distinguish:

- User A left newsletter X in tenant T.
- User A wants no marketing at all from brand B.
- Address Z hard-bounced and should not be emailed even if the account changes subscriptions.
- A recipient may change contact addresses and need to verify the new address.
- Two accounts may share a mailbox and need mailbox-level do-not-contact rules.

Storing only **email -> unsubscribed=true** risks blocking too broadly or too narrowly.

### Permission and Suppression States Must Combine

A **mail_subscription.subscribed=true** must never override **mail_suppression.active=true** within the applicable scope. Evaluation rules should enforce explicit precedence rather than whichever table was written most recently.

Example:

~~~text
SUBSCRIPTION = TRUE
SUPPRESSION  = GLOBAL_MARKETING_OPT_OUT
RESULT       = DENY
~~~

A valid re-subscription request should not automatically erase complaint suppression or bounce suppression without an appropriate workflow.

### Auditing Without Storing Raw Tokens

Minimal audit entry:

~~~text
event_id       = ...
recipient_id   = ...
tenant_id      = ...
list_id        = NEWSLETTER_WEEKLY
action         = UNSUBSCRIBE
source         = RFC8058_ONE_CLICK
occurred_at    = ...
token_record   = ...
~~~

Never write raw tokens to logs. You can retain the token hash and record ID sufficiently to investigate repeated requests. For privacy compliance, define retention periods and deletion rules for personal data per policy.

## 12. Updating Subscriptions in One Transaction

Upon receiving a valid token, the service must update status to **UNSUBSCRIBED** within a database transaction:

~~~sql
INSERT INTO mail_subscription (
    tenant_id, recipient_id, list_id, subscribed,
    source, updated_at
)
VALUES (
    :tenant_id, :recipient_id, :list_id,
    FALSE, 'RFC8058_ONE_CLICK', CURRENT_TIMESTAMP
)
ON CONFLICT (tenant_id, recipient_id, list_id)
DO UPDATE SET
    subscribed = FALSE,
    source = 'RFC8058_ONE_CLICK',
    updated_at = CURRENT_TIMESTAMP;
~~~

This statement is a PostgreSQL example. It is idempotent regarding **effective state**: repeated calls keep subscribed=false. If the system needs to preserve the first cancellation timestamp, adjust updated_at/audit logic rather than overwriting on every replay.

### A Spring Service Handling the Request

Example application-defined repository design:

~~~java
public record UnsubscribeIdentity(
        String tenantId,
        String recipientId,
        String listId
) {
}

public interface UnsubscribeTokenRepository {

    UnsubscribeIdentity findActiveIdentityByTokenHash(
            String tokenHash
    );

    void markUsed(String tokenHash);
}

public interface MailSubscriptionRepository {

    void markUnsubscribed(
            String tenantId,
            String recipientId,
            String listId,
            String source
    );
}
~~~

In the example, **findActiveIdentityByTokenHash(...)** returns null if the token does not exist, was revoked, or expired. Optional/exception conventions are a project decision. To avoid races between token revocation and cancellation, implementations should use proper transactions/locking or conditional updates.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UnsubscribeService {

    private final UnsubscribeTokenRepository tokenRepository;
    private final MailSubscriptionRepository subscriptionRepository;

    public UnsubscribeService(
            UnsubscribeTokenRepository tokenRepository,
            MailSubscriptionRepository subscriptionRepository
    ) {
        this.tokenRepository = tokenRepository;
        this.subscriptionRepository = subscriptionRepository;
    }

    @Transactional
    public void unsubscribe(String opaqueToken) {
        if (opaqueToken == null
                || !opaqueToken.matches("[A-Za-z0-9_-]{32,128}")) {
            throw new InvalidUnsubscribeTokenException();
        }

        String tokenHash =
                UnsubscribeTokenHashes.sha256(opaqueToken);
        UnsubscribeIdentity identity =
                tokenRepository.findActiveIdentityByTokenHash(tokenHash);

        if (identity == null) {
            throw new InvalidUnsubscribeTokenException();
        }

        subscriptionRepository.markUnsubscribed(
                identity.tenantId(),
                identity.recipientId(),
                identity.listId(),
                "RFC8058_ONE_CLICK"
        );
        tokenRepository.markUsed(tokenHash);
    }
}
~~~

Exception example:

~~~java
public class InvalidUnsubscribeTokenException
        extends RuntimeException {
}
~~~

**UnsubscribeService** does not send a marketing confirmation email afterward. If a confirmation email is required for legal/business reasons, evaluate sending it separately; never exploit unsubscribe confirmations to send more promotional material.

### Do Not Invalidate Tokens After First Use in a Way That Breaks Idempotency

If **markUsed(...)** revokes the token immediately after the first POST, a second POST could return an error even though the unsubscribe succeeded. That is poor behavior for provider retries.

A better design **records the first-use timestamp while still accepting the same token within policy bounds**, returning success when the recipient is already UNSUBSCRIBED. A token can still be revoked for security incidents, yet successful cancellation need not turn every valid replay into an error.

In implementation, repositories should distinguish nonexistent tokens, security-revoked tokens, already-used tokens, and already-unsubscribed states.

## 13. One-Click POST Endpoint in Spring MVC

A controller accepting RFC 8058 requests properly:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/one-click")
public class OneClickUnsubscribeController {

    private final UnsubscribeService unsubscribeService;

    public OneClickUnsubscribeController(
            UnsubscribeService unsubscribeService
    ) {
        this.unsubscribeService = unsubscribeService;
    }

    @PostMapping(
            path = "/{token}",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<Void> oneClick(
            @PathVariable String token,
            @RequestParam("List-Unsubscribe") String requestAction
    ) {
        if (!"One-Click".equals(requestAction)) {
            return ResponseEntity.badRequest().build();
        }

        unsubscribeService.unsubscribe(token);
        return ResponseEntity.noContent().build();
    }
}
~~~

The controller uses **List-Unsubscribe** from the form body and the token from the URL to execute the action. The example omits an exception handler; in production, map **InvalidUnsubscribeTokenException** to an appropriate HTTP response without leaking identities/emails or DB details in errors.

### GET Endpoint Must Not Mutate Data

If you want to support users visiting the URL in a browser, you can provide:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@GetMapping("/one-click/{token}")
public ResponseEntity<String> landing(@PathVariable String token) {
    return ResponseEntity.ok(
            "To manage the emails you receive, please use the preferences page."
    );
}
~~~

This example only illustrates the rule that **GET does not call unsubscribe()**. In real apps, do not echo raw tokens into HTML, avoid loading third-party assets that leak URLs via Referer, and avoid broad access logging of tokenized request paths. A separate preference page can let users view and adjust choices after authenticating per product requirements.

### Do Not Require Login/Cookies for One-Click

Mailbox providers normally send one-click POSTs from their own systems without the recipient's login session. Thus the endpoint must act based on the **narrowly scoped token**, without login/cookies or CAPTCHA.

If the app enables Spring Security CSRF protection for session-based forms, configure a **narrow exemption strictly for the stateless one-click endpoint** where appropriate, compensating with strong random tokens, HTTPS, rate limits, and unsubscribe-only state changes. Never disable CSRF across the entire application just to make this endpoint work.

### HTTP Responses and Privacy

Upon cancellation or valid duplicate POSTs, return HTTP **204 No Content**. For invalid/revoked tokens, return 400/404/410 per policy; never return payloads containing email addresses, user names, or subscription lists.

Do not let callers probe whether an address is subscribed via account details in responses. Rate-limit brute force by IP and other signals, without setting limits so tight that mailbox providers using shared infrastructure get blocked en masse.

## 14. Footer Unsubscribe vs. One-Click Unsubscribe: Two Different Journeys

A system usually needs both:

| Criterion | Footer Link / Preference Page | RFC 8058 One-Click |
| --- | --- | --- |
| Actor | Recipient clicks link in body | Email client/provider triggers POST |
| Method | GET displays page, POST after user action | Direct POST in specified format |
| Can show topic choices | Yes | Must not require choosing before completing |
| Login needed | May require appropriate auth for complex changes | No login required to unsubscribe |
| Token | Scoped and protected like capability | Scoped, unpredictable, supports retry/idempotence |
| Purpose | Self-service control and explanation | Fast one-action unsubscribe from email client |

One URL should not both process automated one-click and use GET to mutate state. Separate paths can be used:

~~~text
GET  /preferences/unsubscribe/{token}   -> render preferences
POST /preferences/unsubscribe/{token}   -> handle user submission

POST /one-click/{token}                 -> handle RFC 8058
GET  /one-click/{token}                 -> read-only, no state change
~~~

Tokens in both flows may map to the same subscription, yet their scopes, lifetimes, and usage semantics must be clearly designed.

## 15. Mailbox Scanning and Token Exposure Risks

Unsubscribe URLs can appear in:

- Raw email source and mailbox providers.
- Proxy access logs or application logs.
- Security link-analysis systems.
- User browsers.
- Redirects, analytics, or third-party assets if pages are carelessly built.

Safeguards to apply:

1. Use HTTPS exclusively on trusted domains.
2. Never put email addresses, names, or sensitive IDs in query/path.
3. Never write raw tokens to logs; mask paths/tokens in reverse proxies and error reporting.
4. Load zero third-party scripts, pixels, or external assets on unsubscribe landing pages.
5. Set **Referrer-Policy: no-referrer** when rendering pages tied to tokens.
6. Never redirect tokens to external domains.
7. Grant tokens unsubscribe-only capability within one scope, never reading personal data or re-subscribing.
8. Monitor anomalous requests without hindering legitimate providers.

### URL Tokens Are Not Login Credentials

If a token leaks, someone else could cancel one subscription; that remains a risk, so it must be **bounded strictly to cancellation**. Never share this token with password resets, logins, account queries, or email-change APIs. Isolating tokens by purpose limits blast radius if a link leaks.

## 16. Check Suppression Before Every Dispatch

**The final decision point is not campaign creation time**, it is right when the system is about to hand the message to the provider. Recipient lists may be prepared hours earlier, while a user unsubscribes minutes before the job runs.

A weak design:

~~~text
08:00 Build campaign recipients by querying subscribed users
08:05 User A unsubscribes
09:00 Worker sends to the 08:00 recipient snapshot
      -> A still receives another marketing email
~~~

A better design:

~~~text
Create campaign jobs
        |
        v
Queue / outbox
        |
        v
Worker claims job
        |
        v
Re-check latest suppression/preferences
        |
        +-- DENY -> SUPPRESSED, do not send
        |
        '-- ALLOW -> compose and submit
~~~

### An Application-Layer Policy Interface

~~~java
public record MailDeliveryContext(
        String tenantId,
        String recipientId,
        String recipientEmail,
        MailPurpose purpose,
        String listId
) {
}

public enum DeliveryDecisionType {
    ALLOW,
    DENY
}

public record DeliveryDecision(
        DeliveryDecisionType type,
        String reasonCode
) {
    public boolean allowed() {
        return type == DeliveryDecisionType.ALLOW;
    }
}

public interface MailDeliveryPolicy {

    DeliveryDecision evaluate(MailDeliveryContext context);
}
~~~

These types are **application-designed APIs**, not built into Spring Mail. Implementations must combine authoritative sources: preferences, suppression, consent, hard bounces/complaints, and purpose rules.

### Workers Must Check Before Calling JavaMailSender

~~~java
import org.springframework.stereotype.Service;

@Service
public class MarketingMailDispatcher {

    private final MailDeliveryPolicy deliveryPolicy;
    private final MarketingMailComposer composer;
    private final MailJobStore jobStore;

    public MarketingMailDispatcher(
            MailDeliveryPolicy deliveryPolicy,
            MarketingMailComposer composer,
            MailJobStore jobStore
    ) {
        this.deliveryPolicy = deliveryPolicy;
        this.composer = composer;
        this.jobStore = jobStore;
    }

    public void dispatch(ClaimedMailJob job) {
        MailDeliveryContext context = job.deliveryContext();
        DeliveryDecision decision =
                deliveryPolicy.evaluate(context);

        if (!decision.allowed()) {
            jobStore.markSuppressed(
                    job.id(),
                    job.leaseToken(),
                    decision.reasonCode()
            );
            return;
        }

        composer.submit(job);
        jobStore.markSubmitted(job.id(), job.leaseToken());
    }
}
~~~

**MarketingMailComposer**, **MailJobStore**, and **ClaimedMailJob** are illustrative system components. They must handle transport errors, tokens/leases, and job states per their contracts. This example highlights where to check suppression: **close to the moment of external side effects**, not only when the event was created.

### What If Suppression Storage Is Unreadable?

For marketing emails, consider **failing closed**: if unsure whether the recipient is still eligible, do not submit the email; move the job to waiting or transient error state. Never interpret a database timeout as "no suppression found" and send anyway.

The same rule must apply to bulk sending methods, manual send endpoints, scheduled tasks, and retry workers; there must be no side door bypassing policy.

## 17. Race Condition When Unsubscribe and Send Happen Nearly Simultaneously

Even when workers check suppression before every send, a window remains:

~~~text
Worker A                              Unsubscribe request
    |                                        |
    v                                        |
Check suppression -> ALLOW                   |
    |                                        v
    |                                  Commit UNSUBSCRIBED
    v                                        |
JavaMailSender.send(...)                     |
    |                                        |
    v                                        v
Provider accepted                        HTTP 204
~~~

Sending may already have started right before or around when the opt-out took effect. Databases and SMTP do not share an atomic transaction, so a pre-send query cannot guarantee absolutely that **zero emails ever arrive after an unsubscribe POST**.

### Risk-Reduction Measures

- Check suppression **as close as possible to submission**.
- Limit the number of marketing jobs `IN_FLIGHT` at once.
- Cancel or mark `SUPPRESSED` unsubmitted jobs after opt-out.
- Sync suppression to the ESP/provider if they maintain a separate blocklist.
- Never retry suppressed jobs, even if a prior attempt timed out.
- Avoid pre-submitting thousands of emails into provider queues before checking preferences.
- Define effective timestamps clearly and handle messages already accepted by the provider.

### Do Not Hold Database Locks Across SMTP Calls

Trying to avoid races by opening a database transaction, locking the recipient row, and waiting for SMTP replies creates serious issues: holding locks/connections long, increasing contention, and risking timeouts.

Business-level synchronization or dispatch barriers can be designed when requirements are ultra-strict, while weighing non-rollbackable external side effects. Standard practice is **blocking unsent jobs, rechecking right before submit, and acknowledging limits on in-flight messages**.

### Distinguishing PENDING, IN_FLIGHT, and ACCEPTED Jobs

| Job State at Unsubscribe | Handling |
| --- | --- |
| **PENDING/SCHEDULED** | Block or mark SUPPRESSED before sending |
| **CLAIMED but not submitted** | Worker rechecks and refuses to send |
| **IN_FLIGHT over transport** | May not be cancelable; track and prevent retries |
| **ACCEPTED by provider** | Generally cannot be recalled over SMTP |
| **RETRYABLE_FAILED/UNKNOWN** | Check suppression before every retry; if opted out, do not resend marketing |

For **UNKNOWN** after a timeout, alongside duplicate risk there is the new opt-out condition. A marketing job that is technically retryable must still never bypass current suppression.

## 18. Preventing Older Jobs from Retrying After User Unsubscribes

In queue/outbox systems, an email may go through multiple processing attempts:

~~~text
Campaign event
    |
    v
Outbox PENDING
    |
    v
Worker attempt 1 -> SMTP temporary error
    |
    v
RETRY_SCHEDULED
    |
    +------------------- User unsubscribes
    |                             |
    |                             v
    |                        Suppression active
    v
Worker attempt 2
    |
    v
Check suppression -> DENY
    |
    v
SUPPRESSED, do not resend
~~~

**Retry policies must never bypass consent/suppression policies automatically.** All of these mechanisms must re-invoke the delivery policy:

- **Spring Retry** or worker retry loops.
- Post-incident job schedulers.
- Dead-letter redrives.
- Manual admin requeues.
- Retries in the email provider integration layer.
- Campaign resends to recipients "not confirmed delivered."

### Separating "Retry" and "Resubscribe"

Retry means trying to finish an older notification; it is **not fresh consent for new mail**. If the recipient unsubscribed, old marketing notifications must stop.

Resubscribe means the recipient performed a new action to opt back in per policy. Never flip subscribed=true just because:

- The user logged back in.
- They changed passwords or updated profile info.
- They opened an old email.
- They clicked a tracking link.
- Support staff re-triggered a campaign.

Change consent only through a flow with proper authorization, purpose, and evidence.

## 19. Syncing Suppression with the Email Provider

When using an **Email Service Provider (ESP)**, state may live in two places:

1. **Application:** preference/suppression tables and notification jobs.
2. **Provider:** suppression lists, unsubscribe events, complaints, hard bounces, and recipient segments.

The two places can drift out of sync. If the application updates only its database while the provider runs a campaign off a previously uploaded list, the provider may keep sending queued jobs. Conversely, if the provider records an unsubscribe yet the application never receives the event, sends via another path may ignore the opt-out.

### Sync Strategy

~~~text
                    Unsubscribe event
                           |
             +-------------+-------------+
             |                           |
             v                           v
    Application suppression      Provider suppression
             |                           |
             +-------------+-------------+
                           |
                           v
                   Reconciliation
~~~

Principles:

- Define the **source of truth** for each suppression type.
- Ingest unsubscribe/complaint/bounce webhooks when supported by the provider.
- Record events idempotently so replays do not cause unwanted mutations.
- Push opt-outs to the provider when APIs support it.
- Periodically reconcile counts and divergent records.
- Avoid blocking only at the provider while letting the application keep generating and submitting rejected jobs.

### Webhooks Must Be Authenticated

An HTTP request claiming "user unsubscribed" must never update state unless the source is verified. When handling webhooks:

- Verify signatures or authentication mechanisms specified by the provider.
- Check timestamp/replay windows if supported by the provider.
- Use unique provider event IDs or deduplication keys.
- Map events to authorized tenants/lists/recipients.
- Never overwrite a stronger suppression with a weaker state.

There is no universal webhook signing scheme across providers; follow the documentation of the integrated provider.

### Provider-Side Suppression Does Not Replace Application Policy

A provider may refuse to send to an address on its suppression list, yet the business application should still mark the notification **SUPPRESSED** instead of reporting send success. Provider rejections may arrive asynchronously or fail to apply across another SMTP connection, so centralized application policy must still enforce rules.

## 20. Complaints and Bounces Are Also "Do-Not-Send" Signals

Unsubscribe is not the only signal that should stop marketing sends. Provider feedback matters too:

| Signal | Common Meaning | Suggested Action |
| --- | --- | --- |
| **Explicit unsubscribe** | Recipient does not want selected mail type | Block exact scope immediately |
| **Spam complaint** | Recipient reported unwanted mail | Apply suppression per provider/product policy |
| **Hard bounce** | Mailbox/domain persistently rejects | Stop retrying address; recheck if address changes |
| **Soft bounce** | Temporary error | Bounded retries; monitor frequency |
| **Repeated transient failures** | Possible low-quality address/host | Pause or review per policy |
| **Manual do-not-contact** | Request from support/legal/recipient | Apply scoped suppression and audit |

Do not treat a single soft bounce as a voluntary unsubscribe: it does not mean the recipient withdrew consent. Conversely, do not ignore a spam complaint merely because `user.subscription` is still true.

### Do Not Try to "Work Around Suppression"

If a provider blocks sends due to complaints or hard bounces, never swap sender domains, switch mail services, or guess alias addresses just to keep a campaign going. That violates suppression intent and harms deliverability.

### Distinguishing Technical Errors from Business Requests

In the data model, store distinct **reasons**:

~~~text
UNSUBSCRIBE
GLOBAL_OPT_OUT
COMPLAINT
HARD_BOUNCE
INVALID_RECIPIENT
MANUAL_SUPPRESSION
~~~

Recovery policies differ: replacing a bounced address, re-subscribing to a newsletter, and lifting complaint suppression must not share a single `subscribe=true` endpoint.

## 21. Preference Centers and Intentional Re-Subscription

One-click has one primary goal: **stop an email stream within the token's scope**. A preference center is broader: it lets recipients tune topics or frequency.

Example choice UI:

~~~text
Manage emails from Shop 7

[ ] Weekly newsletter
[ ] Promotional offers
[x] Product updates

[ Unsubscribe from all marketing emails ]

Save preferences
~~~

In the example, checked or unchecked boxes only work when accurately mapped to purposes and lists. The system must explain which transactional/security emails will still be sent per policy, avoiding confusion that "Unsubscribe from all marketing emails" stops payment receipts.

### Do Not Turn the Preference Center into an Arbitrary Mail Tool

Updating preferences requires authentication or appropriately scoped tokens; users must never alter someone else's preferences by swapping a recipient ID in the URL. When allowing multi-purpose edits, scope tokens/authorization accordingly.

### Re-Subscribing Requires Explicit Action

A user requesting to subscribe again may require:

- A form clearly showing the email types being subscribed to.
- An affirmative opt-in action with policy-compliant evidence.
- Mailbox ownership verification when needed.
- Double opt-in if required by workflow/provider/law or chosen by product policy.
- A record of consent source, timestamp, policy version, or accepted text.

Never infer **opening an email**, logging into an account, or not clicking unsubscribe as fresh consent.

### Do Not Wipe All Suppressions on Re-Subscription

Example:

~~~text
Marketing preference: SUBSCRIBED
Provider hard bounce: ACTIVE
Delivery decision:    DENY
~~~

Re-subscribing does not prove a mailbox exists again. Policies must define how bounce/complaint suppression is cleared based on provider capabilities and verification requirements. Never run a blanket UPDATE clearing all suppressions just because a user checked a box again.

## 22. Email Changes and Imported Lists

A user may change their email from **old@example.test** to **new@example.test**. Decide clearly:

- Do subscriptions attach to the **account** or the **verified email address**?
- Should a recipient who opted out of a list retain that choice upon changing addresses?
- If the old address is reassigned to someone else, do old suppressions and consents still apply?
- When importing marketing lists from CSV/CRM, may that import overwrite existing opt-outs?

A simpler and generally safer rule is **never automatically overwrite opt-outs with imported data**. When ingesting a new consent source, inspect scope, who consented, timestamp, and proof. If unclear, do not send marketing merely because a CRM holds an email address.

### Do Not Lose Suppression When Accounts Are Deleted and Recreated

If a user deletes an account and recreates one with the same address, opt-out flags stored in the old users table can be lost. For do-not-contact requests, you may need to retain a minimal, legally compliant suppression record to avoid accidental re-imports and resends.

Balance this with erasure rights and data minimization: do not keep full personal profiles solely to block emails. You can use securely designed recipient references or digests per legal and retention policies, evaluating re-identification risks and compliance.

### Do Not Over-Normalize Mailboxes Yourself

For instance, do not strip dots or plus-tags from every email under one blanket rule. Alias handling depends on mailbox providers and is not universal across domains. If suppressing by email address, follow a consistent canonicalization policy grounded in authoritative rules while avoiding falsely merging distinct mailboxes.

## 23. Testing One-Click and Suppression

A test suite must verify **protocol behavior**, **state transitions**, **scoped authorization**, and **pre-send gating**, not only that the controller returns 204.

### Testing One-Click POST with a Valid Body

Example using Spring MockMvc with a standalone controller and mocked service:

~~~java
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class OneClickUnsubscribeControllerTest {

    @Test
    void postOneClickDelegatesToService() throws Exception {
        UnsubscribeService service = mock(UnsubscribeService.class);
        MockMvc mvc = MockMvcBuilders.standaloneSetup(
                new OneClickUnsubscribeController(service)
        ).build();

        String token = "A".repeat(43);

        mvc.perform(post("/one-click/{token}", token)
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED
                        )
                        .param("List-Unsubscribe", "One-Click"))
                .andExpect(status().isNoContent());

        verify(service).unsubscribe(token);
    }

    @Test
    void rejectsWrongAction() throws Exception {
        UnsubscribeService service = mock(UnsubscribeService.class);
        MockMvc mvc = MockMvcBuilders.standaloneSetup(
                new OneClickUnsubscribeController(service)
        ).build();

        mvc.perform(post("/one-click/{token}", "A".repeat(43))
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED
                        )
                        .param("List-Unsubscribe", "Other-Action"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }
}
~~~

This test verifies only the controller contract with a mocked service. It **does not prove** Spring Security allows sessionless POSTs in a real environment or that DB updates committed. Add integration tests for the security filter chain, token repository, and suppression store.

### Testing That GET Does Not Alter Preferences

A test should send GET to the one-click URL and verify:

~~~text
Given: recipient is still subscribed
When: GET /one-click/token
Then: UNSUBSCRIBED is not recorded
And: no suppression event is created
~~~

This simulates link scanners. Do not check only status 200; verify storage state remains unchanged.

### Testing Repeated POSTs

~~~text
Given: valid token for newsletter A
When: POST attempt 1, then POST again with the same token
Then: newsletter A remains UNSUBSCRIBED
And: nothing flips subscribed back to true
And: two cancellation confirmation emails are not created
~~~

If the repository stores the first cancellation timestamp, verify the second POST does not erase the first audit record.

### Testing Exact Token Scope

~~~text
Given: token for recipient R / tenant T / list A
When: POST one-click
Then: list A for R in T is canceled
And: list B is unchanged
And: recipient S is unchanged
And: tenant U is unchanged
~~~

This test is essential in multi-tenant systems or with multiple marketing lists. Never let a token read/modify all preferences of a recipient.

### Testing Jobs Created Before Unsubscribe

~~~text
T1: create PENDING newsletter job for R
T2: R unsubscribes
T3: dispatcher claims job
Expected: dispatcher marks SUPPRESSED, JavaMailSender is not called
~~~

This is the end-to-end test of the **do-not-send** rule. Updating subscribed=false in the database is insufficient if the mail dispatcher uses stale recipient snapshots.

### Testing Retries After Unsubscribe

~~~text
T1: marketing send attempt hits a temporary error
T2: user unsubscribes
T3: retry worker runs
Expected: does not retry SMTP; job moves to SUPPRESSED
~~~

For retries, do not test only max attempts/backoff. Test preference changes occurring while jobs wait.

### Testing Concurrent Requests

Run two POSTs for the same token near-simultaneously. The result must be a consistent UNSUBSCRIBED state. If the system writes a single audit event for the first cancellation, use constraints/upserts to avoid unintended duplicate records.

### Testing Real DKIM/Headers

A composer-level test can verify:

~~~java
MimeMessage message = composer.compose(
        recipient,
        subject,
        html,
        oneClickUrl
);

assertNotNull(message.getHeader("List-Unsubscribe"));
assertNotNull(message.getHeader("List-Unsubscribe-Post"));
~~~

Yet to confirm **DKIM signatures** and how email clients display the unsubscribe button, inspect real received messages or provider test environments. Header unit tests do not prove the provider signed headers properly per RFC 8058.

### Testing Token Leakage in Logs

When calling the endpoint with a malformed token that throws an exception, verify application logs and reverse proxy access logs do not accidentally print the full URL path. The goal is keeping raw tokens out of broadly accessible log systems, not just avoiding logging in Java methods.

## 24. Metrics, Alerts, and Measuring Effectiveness

Useful metrics for unsubscribe operations:

| Illustrative Metric | Meaning |
| --- | --- |
| **mail_unsubscribe_requests_total{source,result}** | Requests from one-click/footer/provider webhooks and outcomes |
| **mail_unsubscribe_processing_duration_seconds** | Time to update preference/suppression |
| **mail_suppressed_jobs_total{reason}** | Notifications blocked before sending |
| **mail_eligible_recipients_total{purpose}** | Eligible recipients by purpose |
| **mail_complaints_total{provider}** | Spam complaints |
| **mail_hard_bounces_total{provider}** | Hard bounces |
| **mail_delivery_policy_failures_total** | Errors while evaluating delivery eligibility |
| **mail_provider_suppression_sync_failures_total** | Failures syncing suppression to providers |

These are **application-defined metrics**, not Spring Mail defaults. Never place recipient emails, raw tokens, or notification IDs into metric labels due to high cardinality and privacy risks.

### Alerts Worth Considering

- Unusual rise in HTTP 5xx on the one-click endpoint.
- Subscriptions updated yet the mail dispatcher keeps sending marketing for canceled scopes.
- Provider unsubscribe/complaint webhooks failing authentication or going silent.
- Large drift between application suppression and provider suppression.
- Rising spam reports on marketing emails.
- Post-opt-out marketing retry rate above acceptable thresholds.

The goal is not lowering unsubscribe counts by hiding the unsubscribe button. High unsubscribes may signal mismatched content, frequency, or targeting. Empowering recipient choice is almost always better than hiding or delaying opt-outs.

## 25. Handling Unsubscribe Requests via mailto or Customer Support

Not every recipient uses an email client supporting one-click or wants to click a link. Requests saying **"Please stop sending promotional emails"** can arrive via:

- A reply email to support.
- A `List-Unsubscribe` header containing **mailto:**.
- A customer support ticket.
- A privacy or do-not-contact web form.
- A provider feedback loop.

If the system advertises mailto in the header, it must have a matching processor:

~~~text
mailto:leave-newsletter@example.test
               |
               v
         Mailbox receiver
               |
               v
    Parse and correlate request
               |
               v
      Identify recipient/list
               |
               v
      Apply suppression
               |
               v
      Record audit outcome
~~~

### Do Not Blindly Trust From on Emails Sent to the Unsubscribe Mailbox

The From header in an incoming email can be spoofed or forwarded. An email arriving at the unsubscribe address does not automatically prove the writer controls the mailbox named in the header. Use an appropriate correlation and scoping mechanism:

- The **mailto:** address or subject can embed a server-generated opaque code.
- The system can use identifiers linked to the notification.
- Support requests may verify the requester per policy.
- Unverifiable cases may go to manual review or risk-reduction workflows.

Do not build a mailto handler where anyone can send another user's name and arbitrarily alter all preferences. Conversely, do not impose excessive verification friction that prevents recipients from exercising opt-out rights.

### Do Not Use Auto-Replies to Pressure Users to Re-Subscribe

Once an unsubscribe is processed, never send another newsletter disguised as "Confirm you still want our emails" to circumvent cancellation. Any operational confirmation must comply with policy, contain zero promotional content, and avoid infinite auto-reply loops.

## 26. Legal and Sending-Policy Considerations

Unsubscribe rights and do-not-contact requests may be governed by:

- Anti-spam and e-commerce laws in relevant jurisdictions.
- Privacy regulations and lawful bases for data processing.
- Contracts with email providers.
- Internal policies on marketing, transactional notices, and data retention.
- Choices presented to recipients at signup time.

No single processing deadline or email classification fits every market. For instance, rules for promotional emails vs. security verification emails may differ; a message mixing promotions and transactions may be judged by its actual content.

### Questions to Clarify in Product Requirements

1. Which email types require prior opt-in before sending?
2. Can recipients unsubscribe per list, per brand, or across all marketing?
3. What turnaround deadline applies to opt-out requests by market/provider?
4. Is one-click mandatory for the traffic volume in use?
5. Must consent and withdrawal evidence be retained, and for how long?
6. When users change emails or delete accounts, what minimal suppression is retained?
7. Who can perform manual overrides and under what workflow?
8. Which service/security notices remain permitted or mandatory?

These items must be checked against current policies; this is a technical lesson and **not a substitute for legal advice**.

### Honoring Choice Must Happen in Systems, Not Only on Paper

Writing "you can unsubscribe anytime" in emails while the unsubscribe endpoint fails, job queues skip rechecking suppression, or providers keep running campaigns renders the policy meaningless in practice.

A "do-not-contact" request must govern the **allow-send decision** inside the mail dispatcher, not merely a preference form.

## 27. Common Mistakes

### Mistake 1 — Unsubscribe Link Exists Without Persisting State

Footer opens a "Thank you" page without changing the subscription.

**Fix:** apply idempotent suppression and verify the database committed.

### Mistake 2 — GET Link Triggers Unsubscribe Directly

Link scanners fetching URLs trigger unwanted unsubscribes.

**Fix:** GET only renders; POST mutates. One-click uses standard POST per RFC 8058.

### Mistake 3 — One-Click Requires Login or CAPTCHA

Mailbox providers have no user login session to complete prompts automatically.

**Fix:** narrowly scoped tokens, HTTPS, and direct POST requiring no extra confirmation steps.

### Mistake 4 — Adding List-Unsubscribe Without a Handler

Email clients show the unsubscribe button, yet requests return 404/500.

**Fix:** implement the endpoint/mailbox processor, monitor errors, and test from real receiving environments.

### Mistake 5 — Checking Subscribed Only at Enqueue Time

Jobs queued for hours still send after the user unsubscribes.

**Fix:** recheck suppression at dispatch and before retries.

### Mistake 6 — Canceling One List Yet Resending via Another Campaign in the Same Scope

The system misdefined scopes or failed to enforce global opt-outs.

**Fix:** define clear precedence and share one MailDeliveryPolicy across every sending path.

### Mistake 7 — Second POST Re-Subscribes After Cancellation

The endpoint used boolean toggle logic.

**Fix:** the action is strictly unsubscribe, executed idempotently.

### Mistake 8 — Token Is an Email or Predictable User ID

Others can guess another recipient's unsubscribe URL.

**Fix:** high-entropy random opaque tokens, tightly scoped and unsubscribe-only.

### Mistake 9 — Re-Subscribing Clears Complaints and Hard Bounces Too

One global UPDATE erased all suppressions.

**Fix:** manage reasons and recovery rules independently per suppression type.

### Mistake 10 — Treating Hard Bounces as Voluntary Unsubscribes

Technical failure and recipient intent get conflated.

**Fix:** store explicit reasons; policy can block both while auditing/recovery remain distinct.

### Mistake 11 — Provider Knows About Opt-Out While the App Does Not

The app keeps generating/sending through another transport, ignoring provider state.

**Fix:** authenticate webhooks, sync, and reconcile suppressions.

### Mistake 12 — Tokenized URLs Logged in Access Logs

Raw tokens sit in proxies/error trackers and risk unintended use.

**Fix:** unsubscribe-only tokens, redact logs, and avoid external assets on landing pages.

### Mistake 13 — Sending Marketing as Security Notifications

The app flags marketing as transactional/security to bypass unsubscribes.

**Fix:** classify by genuine purpose and separate promotional copy from essential notices.

### Mistake 14 — Hard-Coding Turnaround Policies from One Provider

One deadline may conflict with another regulation or updated guideline.

**Fix:** verify legal/provider requirements for current markets and store policies in config/operational specs.

### Mistake 15 — Relying Only on SMTP Success

JavaMailSender.send(...) throws no errors, yet recipients still complain or unsubscribe.

**Fix:** monitor provider events, delivery outcomes, complaints, and preferences; never equate SMTP accept with ongoing consent.

## 28. Practice Scenarios

### Scenario A — User Cancels Newsletter, Then Places an Order

User opted out of newsletters yet completes a new purchase.

**Question:** may an order receipt be sent?

**Answer:** apply policy by purpose. Opting out of a newsletter alone usually does not mean stopping transactional messages; receipts should follow service policies and applicable rules without sneaking promotions inside to evade opt-outs.

### Scenario B — One-Click URL Receives GET from a Link Scanner

Server observes a GET to the one-click URL before the user opens the email.

**Question:** should subscription state change?

**Answer:** no. GET causes no side effects; standard one-click processes POST with the List-Unsubscribe field.

### Scenario C — Provider Sends POST Twice

The first call succeeded yet the HTTP response was lost; the provider retries.

**Question:** may the second call flip state back to SUBSCRIBED?

**Answer:** no. The unsubscribe handler must be idempotent and retain the canceled state.

### Scenario D — Recipient Has Three Newsletters

The token in newsletter A's email is used to unsubscribe.

**Question:** does it automatically cancel B and C?

**Answer:** only if that option's scope was explicitly defined as all marketing. If the token represents list A, cancel only A; never guess scope from email addresses.

### Scenario E — Unsubscribe Token Exposes Email in URL

The URL carries full email and list ID query parameters.

**Question:** what is the risk?

**Answer:** data leakage in logs/traces, easy to guess or tamper with. Use opaque tokens linked server-side to recipient/list.

### Scenario F — Job Enqueued While User Was Still Subscribed

By send time, the recipient has unsubscribed.

**Question:** send or skip?

**Answer:** do not send marketing; the dispatcher must recheck suppression and mark SUPPRESSED rather than relying on stale eligibility snapshots.

### Scenario G — Mail Is IN_FLIGHT When User Opts Out

The worker started the SMTP transaction right before the unsubscribe committed.

**Question:** can delivery be guaranteed not to arrive?

**Answer:** a submission already accepted by the provider cannot be reliably recalled. Minimize the race window, block unsubmitted jobs, and never retry after opt-out.

### Scenario H — Provider Reports a Spam Complaint

The preference database still shows subscribed=true.

**Question:** should newsletters continue?

**Answer:** do not rely solely on preferences. Complaint suppression may mandate stopping sends per policy/provider; sync the signal back to the application.

### Scenario I — Marketing Operator Re-Imports an Old CSV

The CSV shows the user opted in, yet they unsubscribed last week.

**Question:** may the CSV re-enable the subscription?

**Answer:** not automatically. Verify valid new consent evidence; recent opt-outs must not be silently overwritten by stale snapshots.

### Scenario J — Sender Address Changed to Another Brand

A campaign swaps From to keep mailing opted-out addresses.

**Question:** is this acceptable?

**Answer:** no, if used to circumvent the suppression scope the recipient requested. Policies must track actual brand/tenant/purpose rather than just the From string.

### Scenario K — User Wants to Re-Subscribe After Canceling

**Question:** can the old one-click token be reused to subscribe?

**Answer:** no. Tokens grant unsubscribe only. Re-subscribing requires a separate authorized action with appropriate evidence.

### Scenario L — Email Client Does Not Show the Unsubscribe Button

The raw message contains List-Unsubscribe.

**Question:** is the message definitely broken?

**Answer:** not necessarily. Check client/provider support, DKIM signature, List-Unsubscribe-Post, mail type, and sender requirements. Header presence alone does not guarantee clients render the button.

### Scenario M — One Provider Has Suppression, Another Does Not

The system fails over SMTP after an outage.

**Question:** how do we avoid mailing unsubscribed users again?

**Answer:** enforce application-side suppression as the common gate and sync across providers; never depend solely on one vendor's blocklist.

### Scenario N — Recipient Asks "Stop Emailing Me" via Support

**Question:** is marking only newsletter A unsubscribed enough?

**Answer:** verify request scope and policy; if the intent is stopping all marketing, apply the right scope rather than a single list. Audit the source and reason.

### Scenario O — Suppression Database Unreadable During Dispatch

**Question:** should it default to ALLOW so the campaign is not delayed?

**Answer:** for marketing, prefer failing closed and pausing/deferring dispatch when eligibility is unknown. Sending without opt-out controls can cause much worse harm than delayed delivery.

## 29. End-to-End Implementation Workflow

~~~text
DEFINE POLICIES
    |
    +-- Mail types: marketing / product / service / security
    +-- Scope: tenant / brand / list / purpose
    +-- Consent, do-not-contact, and suppression precedence
    |
    v
DESIGN DATA
    |
    +-- Subscription/preference records
    +-- Suppression records + reasons
    +-- Token hash -> recipient/list/scope
    +-- Audit trail
    |
    v
COMPOSE EMAILS
    |
    +-- Verify recipient eligibility
    +-- Render unsubscribe footer
    +-- Add List-Unsubscribe
    +-- Add List-Unsubscribe-Post
    +-- Outbound provider signs DKIM properly
    |
    v
HANDLE OPT-OUTS
    |
    +-- HTTPS one-click POST
    +-- GET causes no state change
    +-- Validate opaque token/scope
    +-- Commit UNSUBSCRIBED idempotently
    |
    v
ENFORCE SUPPRESSION
    |
    +-- Dispatcher rechecks right before send
    +-- Retries/dead-letter redrives also check
    +-- Block PENDING jobs no longer eligible
    |
    v
SYNC AND OPERATE
    |
    +-- Provider webhooks + suppression sync
    +-- Complaint/bounce handling
    +-- Metrics, alerts, reconciliation
    |
    v
TEST
    |
    +-- RFC 8058 POST/form body
    +-- GET link scanner
    +-- Idempotent replay
    +-- Cross-tenant/list isolation
    +-- Queued and retried jobs after opt-out
    +-- DKIM/headers in real received messages
~~~

### Practical Implementation Checklist

- **Policy:** are marketing, transactional, and security notifications clearly defined?
- **Scope:** do tokens and subscription states bind to the right tenant, list, and recipient?
- **Consent:** is there an authoritative data source/permission allowing marketing sends?
- **Headers:** are List-Unsubscribe and List-Unsubscribe-Post syntactically valid, HTTPS URLs, and properly DKIM-signed?
- **Endpoint:** does form POST process directly, GET leave state untouched, and no login/CAPTCHA block it?
- **Token:** are tokens unpredictable, hash-looked-up, free of PII, and scoped strictly to unsubscribe?
- **Database:** is unsubscribe idempotent with clean transaction boundaries?
- **Dispatcher:** do all marketing send paths recheck latest suppression before submission?
- **Retries:** are pending/retry jobs blocked after opt-out?
- **Providers:** are unsubscribes, complaints, and bounces synced/reconciled?
- **Privacy:** are tokenized URL logging and audit access restricted?
- **Tests:** have you simulated provider POSTs, link-scanner GETs, replays, races, and queued emails?
- **Operations:** are alerts configured if the endpoint fails or suppression is bypassed?

## 30. Summary of Core Principles

~~~text
The unsubscribe link is only the UI;
suppression at send time is the enforcement mechanism.

GET unsubscribe URL -> no state change
RFC 8058 one-click POST -> cancel exact scope, idempotently

One unpredictable token -> one limited cancellation capability
Never use tokens to query data or re-subscribe

Never trust recipient snapshots from enqueue time
Every marketing attempt must check current suppression

Newsletter opt-out != auto-blocking all security emails
Subscribed=true != allowed to send when global suppression is active

Provider suppression != complete replacement for application policy
SMTP accepted != recipient wants to keep receiving mail
~~~

**Unsubscribes and do-not-contact requests** form a business lifecycle spanning consent/preferences, MIME composition, HTTP POST ingestion, database updates, job blocking, and email provider synchronization. With Spring Framework Mail, **JavaMailSender** can attach **List-Unsubscribe** and **List-Unsubscribe-Post** headers, yet **does not enforce suppression itself**. Implement protocol-compliant one-click endpoints, narrowly scoped tokens, idempotent updates, and eligibility checks right before every send—even for pre-enqueued or retrying jobs. When recipients can stop emails effortlessly and that choice is enforced across every sending path, the system respects their preferences while building a far more sustainable deliverability foundation.
