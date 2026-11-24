# List-Unsubscribe for Subscription Emails

## 1. Why Do Subscription Emails Need List-Unsubscribe?

In a **Spring Framework Mail** application, a system often sends both transactional emails (order confirmations, OTPs, security alerts) and **subscription** emails: newsletters, marketing, product updates, or lists recipients actively opted in to follow. For subscription emails, recipients must have a simple way to **stop receiving the specific type of email they no longer want**.

`List-Unsubscribe` is a standard email header. It gives mail clients URIs for handling unsubscribe requests, allowing clients to display an unsubscribe option directly in the message UI. In particular, **RFC 8058** defines how to signal **one-click unsubscribe** with two headers so a mail receiver can perform an HTTPS POST request on the user's behalf.

~~~text
Recipient subscribed to newsletter
             |
             v
Spring app builds subscription email
             |
             +-- HTML / text content
             +-- List-Unsubscribe header
             +-- List-Unsubscribe-Post header
             |
             v
SMTP / email provider (DKIM signing)
             |
             v
Inbox: client may display "Unsubscribe"
             |
             v
One-click HTTPS POST to sender's endpoint
             |
             v
Persist suppression / stop sending to that list
~~~

Benefits:

- Recipients do not have to hunt for an unsubscribe link at the bottom of a long email.
- Mail clients receive the signals needed to support one-click unsubscribe, depending on client policy.
- Reduces the chance recipients click "Report spam" when they really just want to leave the list.
- The system can keep consent/suppression state consistent and stop sending for the right list.
- Helps meet mailbox provider requirements for marketing/subscription emails, protecting **deliverability**.

**List-Unsubscribe is not a way to guarantee emails land in the Inbox.** It is one part of healthy email sending practices alongside consent, SPF/DKIM/DMARC, domain/IP reputation, spam complaint rates, bounce handling, and recipient list management.

## 2. Distinguishing Subscription Emails from Transactional Emails

Not every email sent from `JavaMailSender` should be treated as an unsubscribable newsletter.

| Email Type | Example | Unsubscribe Behavior |
|---|---|---|
| Newsletter / marketing | Weekly newsletter, promo codes, marketing content | Requires clear unsubscribe mechanism, typically supporting one-click |
| Optional product updates | New feature updates the user opted into | Can be turned off per list/topic |
| Optional digest | Daily/weekly notification summary | Can stop digest without affecting other emails |
| OTP / password reset | Verification codes, password reset links | Typically transactional; should not expose unsubscribe that breaks security flows |
| Purchase receipt | Purchase receipts, transaction records | Typically transactional; separate sending policy |
| Security alert | Unfamiliar login, authentication method change | Must not be blocked by marketing suppression |

Google distinguishes **subscription messages** and **non-subscription/transactional messages** by sending purpose, not merely template name or From address. A "notification" can still be a subscription if sent to a list of users who opted in to optional content.

Therefore, **classify emails before composing**:

~~~java
public enum MailCategory {
    SUBSCRIPTION,
    TRANSACTIONAL
}

public record NotificationPolicy(
        MailCategory category,
        String listId,
        boolean supportsOneClick) {
}
~~~

This is an application-defined model. For newsletters, `listId` must identify the exact list the recipient subscribed to; for transactional emails, typically do not enroll them in marketing suppression and do not arbitrarily attach fake List-Unsubscribe headers.

## 3. Three Standards and Documents to Know

| Source | Role |
|---|---|
| **RFC 2369** | Defines the `List-*` header group, including `List-Unsubscribe` with angle-bracketed URIs |
| **RFC 8058** | How to signal one-click unsubscribe: `List-Unsubscribe-Post`, HTTPS POST, and DKIM |
| **Provider email sender guidelines** | Additional rules on one-click, authentication, processing timelines, and unsubscribe UI visibility |

Official references:

- [RFC 2369 — The Use of URLs as Meta-Syntax for Core Mail List Commands](https://www.rfc-editor.org/rfc/rfc2369.html)
- [RFC 8058 — Signaling One-Click Functionality for List Email Headers](https://www.rfc-editor.org/rfc/rfc8058.html)
- [Google — Email sender guidelines](https://support.google.com/mail/answer/81126?hl=en)
- [Google — Email subscription guidelines](https://support.google.com/mail/answer/15263077?hl=en)

Provider requirements can change over time, email type, and sender scale. During production deployment, re-check current guidelines from target mailbox providers.

## 4. List-Unsubscribe Syntax per RFC 2369

The `List-Unsubscribe` header contains one or more URIs, each enclosed in `<` and `>`. Multiple options are comma-separated:

~~~mime
List-Unsubscribe: <mailto:unsubscribe@example.com?subject=unsubscribe>
~~~

Or:

~~~mime
List-Unsubscribe: <https://mail.example.com/u/opaque-token>
~~~

Or multiple options:

~~~mime
List-Unsubscribe: <https://mail.example.com/u/opaque-token>, <mailto:unsubscribe@example.com?subject=unsubscribe>
~~~

Per RFC 2369, URIs are ordered by preference from left to right; clients can use whichever method they support. Prefer an **HTTPS URL** for one-click and optionally provide `mailto:` as a fallback if your system actually processes unsubscribe request emails.

**Do not simply write `List-Unsubscribe: unsubscribe@example.com`:** URIs in the header must have valid syntax, including scheme and angle brackets. Each message should have only one `List-Unsubscribe` header; do not emit duplicate copies from multiple application/gateway layers.

### Limitations of mailto

The `mailto:` option requires a system that processes email-based requests. Some clients may open a new compose window to send the request; that is not equivalent to RFC 8058 one-click HTTPS POST. Therefore, **`mailto` alone does not satisfy one-click requirements** of providers requiring RFC 8058.

## 5. One-Click per RFC 8058: Two Headers Working Together

To signal one-click, the message must have **both**:

~~~mime
List-Unsubscribe: <https://mail.example.com/u/f4TzYf4u6K8...>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
~~~

`List-Unsubscribe` contains an HTTPS URI capable of identifying the **exact subscriber and mailing list**. `List-Unsubscribe-Post` has the **exact** value `List-Unsubscribe=One-Click`; it is not JSON or another URL.

When the recipient chooses unsubscribe in the mail client UI and the client performs one-click, the receiving side can issue:

~~~http
POST /u/f4TzYf4u6K8... HTTP/1.1
Host: mail.example.com
Content-Type: application/x-www-form-urlencoded
Content-Length: 26

List-Unsubscribe=One-Click
~~~

RFC 8058 permits `application/x-www-form-urlencoded` or `multipart/form-data`; the example above uses form-urlencoded. The server must understand the request properly and process the unsubscribe **without requiring login, cookies, CAPTCHA, or a second confirmation step**.

Core requirements of RFC 8058:

1. The `List-Unsubscribe` header must contain an **HTTPS** URI.
2. The `List-Unsubscribe-Post` header must have the exact key/value pair `List-Unsubscribe=One-Click`.
3. The URL must be self-contained (typically an opaque token) to identify list + recipient, without relying on browser sessions.
4. The email must carry a **valid DKIM signature covering both headers**.
5. The one-click endpoint handles **POST**, not a GET that automatically mutates subscription state.
6. Do not return HTTP redirects for the one-click POST action.
7. Do not require additional interactive input from the recipient.

**Merely adding the two headers to the message is not enough.** If the endpoint fails to handle POST, the link redirects, or DKIM does not sign properly, clients may hide the one-click button or unsubscribe will fail.

## 6. One-Click POST Must Not Work Like an Unsubscribe GET

Some legacy systems implement endpoints like:

~~~text
GET https://mail.example.com/unsubscribe?email=user@example.com
    -> immediately removes user from the list
~~~

This approach easily triggers **unintended unsubscribes**. Email security systems often automatically fetch URLs inside messages to scan links, check for phishing, or generate previews. A GET invoked by a bot does not mean the recipient actually wanted to unsubscribe.

RFC 8058 solves this by separating behaviors:

| Method | Behavior to Implement |
|---|---|
| `GET /u/{token}` | Display an info page or preference center; **never mutate state automatically** |
| `POST /u/{token}` with `List-Unsubscribe=One-Click` | Unsubscribe the exact subscription per one-click request |
| `POST` from a form on the management page | Handle via custom workflow with explicit action checks |

Example:

~~~text
Mail security scanner
       |
       v
GET /u/token123
       |
       v
Confirmation / preferences page
       |
       +-- DOES NOT change subscription

Mail client (recipient clicked unsubscribe)
       |
       v
POST /u/token123
Content-Type: application/x-www-form-urlencoded

List-Unsubscribe=One-Click
       |
       v
Record UNSUBSCRIBED status
~~~

The server must accept one-click **without cookies, HTTP Authorization, sessions, or browser-generated CSRF tokens**. Yet never skip validating the token in the URL: the URL is a narrowly scoped **bearer capability**, used solely to perform the unsubscribe action for that specific list/recipient. An unpredictable token bound and verified on the server is the primary safeguard.

### Can the Same URL Be Used for Both GET and POST?

Yes. That is a common pattern: GET leads to an unsubscribe/preference page, while POST with the one-click marker performs the action. The key is that **GET has no side effects** and one-click POST requires no further round-trip/confirmation.

### One-Click Is a Completed Action, Not Opening a Page

If POST merely returns a `"Click Confirm to unsubscribe"` page without updating suppression, that is not the RFC 8058 one-click experience. Conversely, returning `204 No Content` after a successful update is a clean choice so the client knows the request succeeded without rendering HTML.

## 7. DKIM Must Sign Both List-Unsubscribe Headers

RFC 8058 requires the email to have **at least one valid DKIM signature** whose signed header list (the `h=` parameter of `DKIM-Signature`) includes both:

- `List-Unsubscribe`
- `List-Unsubscribe-Post`

Illustrative raw header example:

~~~mime
From: newsletter@example.com
To: subscriber@example.net
Subject: November newsletter
List-Id: Product Updates <updates.example.com>
List-Unsubscribe: <https://mail.example.com/u/opaque123>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
DKIM-Signature: v=1; a=rsa-sha256; d=example.com; s=mail;
 h=from:to:subject:list-id:list-unsubscribe:list-unsubscribe-post;
 bh=...; b=...
~~~

**This is only a structural example**: the values `bh=...` and `b=...` are not valid signatures. In production, DKIM is generated and verified by the sending system/provider or a dedicated signing library with appropriate keys.

### Order of Creation and Signing Matters

~~~text
Spring builds MimeMessage
       |
       +-- From/To/Subject
       +-- List-Id
       +-- List-Unsubscribe
       +-- List-Unsubscribe-Post
       +-- HTML/text body
       |
       v
DKIM signer (mail gateway / provider)
       |
       v
SMTP relay / mailbox provider
~~~

If the two headers are added **after DKIM signing**, the earlier signature does not cover them or can be invalidated. Thus ensure they are set before signing. If sending via an SMTP provider that signs DKIM upon receipt, verify the provider actually signs both headers and does not strip or rewrite them.

Spring Mail and `MimeMessageHelper` **do not automatically grant DKIM for a domain** merely by calling `setHeader`. Signing authority and DNS selectors/records are usually configured at the email provider or mail gateway.

### Inspecting the Raw Message on the Receiving Side

When a mail client does not show the one-click option, verify:

1. There is exactly one `List-Unsubscribe` and one `List-Unsubscribe-Post` header.
2. The List-Unsubscribe header contains a working HTTPS URI.
3. The List-Unsubscribe-Post header has the exact required value.
4. There is a valid DKIM signature and `h=` covers both headers.
5. No provider/gateway stripped the headers during relay.
6. Sender reputation and the client's display policy conditions are met.

**Having DKIM pass does not guarantee the headers were signed.** Inspect `h=` on the valid signature: if DKIM passes yet only signs From/Subject without the two unsubscribe headers, RFC 8058 is not satisfied.

## 8. Unsubscribe the Right List, Do Not Block All Emails

An application can have multiple lists:

~~~text
Subscriber: user@example.net
    |
    +-- WEEKLY_NEWSLETTER      subscribed
    +-- PRODUCT_UPDATES        subscribed
    +-- PROMOTIONAL_OFFERS     subscribed
    +-- TRANSACTIONAL_RECEIPTS (transactional stream, not part of marketing lists)
~~~

When the recipient uses one-click from the weekly newsletter, the right outcome is typically:

~~~text
WEEKLY_NEWSLETTER  -> unsubscribed
PRODUCT_UPDATES    -> unchanged
PROMOTIONAL_OFFERS -> unchanged
TRANSACTIONAL_RECEIPTS -> not blocked
~~~

RFC 8058 requires the URI to carry enough information to identify recipient and list; there is no follow-up step asking "which list do you want to leave?" Therefore, **do not reuse one generic unsubscribe URL across all lists if the endpoint cannot distinguish the list**.

### Using List-Id When There Are Multiple Mailing Lists

The `List-Id` header helps identify a list with a stable identifier:

~~~mime
List-Id: Weekly Newsletter <weekly.example.com>
List-Unsubscribe: <https://mail.example.com/u/opaque-weekly-token>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
~~~

`List-Id` does not replace the token in the URL. It assists clients/filtering; the endpoint must still identify the exact subscriber and list from trusted server-side data.

Do not put personal data or secret tokens into List-Id. The ID should represent a **mailing list**, not a recipient.

### Preference Center and Global Unsubscribe Are Different

A preference center page can offer:

- Turn off the weekly newsletter alone.
- Turn off product update notices.
- Turn off all marketing/optional emails.
- Choose sending frequency.

However, **one-click from an email must handle leaving the list associated with that email on its own**, without forcing the recipient to pick again on a preferences page. If the organization offers a global unsubscribe option, present it as a separate intentional choice and explain its impact to the recipient.

## 9. Still Include an Unsubscribe Link in the Email Body

The List-Unsubscribe header serves email clients, yet not every client displays an unsubscribe button in its UI. Therefore, subscription emails should still contain a **clear unsubscribe link in the body**, along with list details and how to change preferences.

HTML example:

~~~html
<html lang="en">
  <body>
    <h1>Weekly Newsletter</h1>
    <p>Latest content for subscribers.</p>

    <hr>
    <p>
      You received this email because you subscribed to the Weekly Newsletter.
      <a href="https://mail.example.com/preferences/opaque-token">
        Manage email preferences
      </a>
      or
      <a href="https://mail.example.com/u/opaque-token">
        Unsubscribe from this newsletter
      </a>.
    </p>
  </body>
</html>
~~~

Plain-text example:

~~~text
You received this email because you subscribed to the Weekly Newsletter.
Unsubscribe or manage your preferences:
https://mail.example.com/u/opaque-token
~~~

When GET only opens a page requiring the user to click confirm, the body link still works; meanwhile, the **one-click header uses HTTPS POST** to the corresponding endpoint without requiring extra clicks. You may use two distinct URLs if you want to separate the preference center path from the POST endpoint, provided semantics and security are respected.

**A link in the body alone cannot replace the one-click header** for flows where providers require RFC 8058. Conversely, having only the header without an easy-to-find body unsubscribe option creates a poor experience on unsupported clients.

## 10. Gmail and Requirements for Subscription Senders

Under Google's current guidelines, senders of **more than 5,000 emails/day to personal Gmail accounts** fall into the bulk sender category, and marketing/subscribed emails must support one-click unsubscribe. Google describes implementing both `List-Unsubscribe` and `List-Unsubscribe-Post`, alongside email authentication and spam rate requirements.

Google also instructs:

- Process and honor unsubscribe requests **within 48 hours**.
- Confirm users genuinely opted in to receive content (appropriate consent).
- Separate sending addresses for subscription vs. non-subscription emails where sensible.
- Identify mailing lists using an understandable `List-Id` or a dedicated From address per subscription list.
- Stop sending a subscription message type once a recipient has unsubscribed from that list.

Treat 48 hours as an **outer bound**, not a target for your system: the sensible flow updates suppression immediately when POST succeeds and enforces policy at dispatch time. If the system already has queued jobs, prevent them from sending after unsubscribe.

Where the unsubscribe option appears in Gmail or another provider's UI **is not solely up to the sender**. Mailbox providers may evaluate authentication, reputation, sending history, email type, and their own policies before displaying the option.

For other mailbox providers, check their respective policies rather than assuming every provider uses the exact same bulk-sender threshold or UI.

## 11. Designing Subscription and Suppression in the Database

A reliable system should not treat unsubscribe as "received POST" and merely write a log line. There must be a **state checkable before every send**, durably stored in a database or dedicated data store.

PostgreSQL example:

~~~sql
CREATE TABLE mailing_subscription (
    id UUID PRIMARY KEY,
    subscriber_id UUID NOT NULL,
    list_key VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('SUBSCRIBED', 'UNSUBSCRIBED')),
    subscribed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    unsubscribed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (subscriber_id, list_key)
);

CREATE TABLE unsubscribe_token (
    token_hash BYTEA PRIMARY KEY,
    subscription_id UUID NOT NULL
        REFERENCES mailing_subscription(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMPTZ
);

CREATE INDEX unsubscribe_token_subscription_idx
    ON unsubscribe_token(subscription_id);
~~~

Here:

- `subscriber_id` is the recipient's internal identifier.
- `list_key` identifies the mailing list, such as `WEEKLY_NEWSLETTER`.
- `status` is the consent status for **that exact list**.
- `token_hash` verifies unsubscribe authority without storing the raw token sent in the URL.
- `unsubscribed_at` helps audit when processing occurred.

This schema is illustrative only. In practice you may need consent source, locale, tenant ID, consent version, double opt-in confirmation, suppression reason, and retention. For tenant-scoped lists, unique constraints must include tenant to avoid mixing subscribers across organizations.

### One Unsubscribe Table May Not Be Enough

An application may maintain:

1. Subscription preferences: which content types the user wants.
2. Global suppression: emails with hard bounces, complaints, or requests to block all promotions.
3. Legal/consent evidence: source and timestamp of user consent.
4. Delivery state: whether an email was scheduled, submitted, failed, or skipped.

These do not necessarily overlap. For instance, leaving a weekly newsletter does not mean blocking invoice emails; yet an address marked invalid may need blocking across multiple email types to protect sender reputation.

### Idempotency When Receiving Unsubscribe

One-click POST can arrive multiple times due to repeated user clicks, system retries, or multiple clients acting on the same message. The unsubscribe command must be **idempotent**:

~~~sql
UPDATE mailing_subscription
SET status = 'UNSUBSCRIBED',
    unsubscribed_at = COALESCE(
        unsubscribed_at, CURRENT_TIMESTAMP),
    updated_at = CURRENT_TIMESTAMP
WHERE id = :subscription_id
  AND status = 'SUBSCRIBED';
~~~

If the row is already UNSUBSCRIBED, the operation needs no further change. The server can still return a success response so the user is not stuck on a duplicate request.

If using a distributed cache, ensure durable suppression updates occur **before** the response completes; cache invalidation and read replicas used by workers must be designed so stale data does not cause continued sends.

## 12. One-Click Tokens: Must Identify the Exact Person and List, Unpredictable

The URL in `List-Unsubscribe` should not simply be:

~~~text
https://mail.example.com/u?email=user@example.net&list=NEWS
~~~

Reasons:

- An email address in the URL can show up in request logs, proxy logs, or analytics tools.
- Anyone could alter the email/list to unsubscribe someone else if the endpoint lacks authentication.
- A GET scanner or automated tool could accidentally trigger the action if misdesigned.

A better approach is generating an **unpredictable random opaque token with high entropy**. The server stores the mapping from token to `subscription_id`; outsiders cannot infer email/list from the token:

~~~text
https://mail.example.com/u/ScuNwUewX1kKM8aQ...
                             |
                             v
                         token hash
                             |
                             v
                    subscription_id
                             |
                   +---------+---------+
                   | subscriber_id     |
                   | list_key          |
                   | status            |
                   +-------------------+
~~~

Java example generating a token from 32 random bytes:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class UnsubscribeTokenGenerator {
    private final SecureRandom random = new SecureRandom();

    public String newToken() {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }
}
~~~

32 bytes yield about 256 bits of entropy before encoding, suitable against token guessing when using a cryptographic random source. Never use `java.util.Random` or a sequential subscriber ID as a public token.

### Store Only the Token Hash When Possible

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

public static byte[] hashToken(String token) {
    try {
        return MessageDigest.getInstance("SHA-256").digest(
                token.getBytes(StandardCharsets.US_ASCII));
    } catch (java.security.NoSuchAlgorithmException ex) {
        throw new IllegalStateException(
                "SHA-256 is required by the Java runtime", ex);
    }
}
~~~

With strong random tokens, SHA-256 keeps raw bearer tokens out of the database. The server receives the raw token, hashes it, and looks it up by `token_hash`. **Never log tokens, including tokens in URL paths.** Access log/reverse proxy configs should avoid recording raw unsubscribe paths whenever possible.

### What Scope Should a Token Bind To?

Tokens should bind to:

- One verified subscriber or target address.
- One specific mailing list.
- Tenant/campaign policy in multi-tenant systems.
- One consent/subscription cycle if the system allows re-subscribing after unsubscribing.

Tokens must not carry permission to change email addresses, update profiles, access accounts, or cancel other lists. Their sole effect is **stopping sends for the list named in the email**.

### Token Expiration and Re-Subscription

Do not set a TTL so short that delayed emails or messages reopened weeks later can no longer unsubscribe. An unsubscribe link in an older email should still behave safely and predictably:

- If the subscription is already canceled, return idempotent success.
- If the user re-subscribed with **a fresh consent event**, decide whether to revoke old-cycle tokens so an old link cannot cancel the new subscription.
- If a token was revoked, offer an option to adjust subscriptions through another safe workflow if appropriate.

Never automatically re-subscribe users merely because they opened a GET page. Re-opting in must require an explicit consent action.

## 13. Setting Both Headers from Spring Framework Mail

`MimeMessageHelper` helps build common bodies and headers, while list headers such as `List-Unsubscribe` and `List-Unsubscribe-Post` can be set directly on `MimeMessage` using Jakarta Mail APIs.

Example composer using a fixed sender:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class NewsletterMailComposer {
    private final JavaMailSender mailSender;
    private final UnsubscribeLinkService linkService;

    public NewsletterMailComposer(
            JavaMailSender mailSender,
            UnsubscribeLinkService linkService) {
        this.mailSender = mailSender;
        this.linkService = linkService;
    }

    public MimeMessage compose(
            NewsletterRecipient recipient,
            String plainBody,
            String htmlBody) throws MessagingException {

        // recipient is data already checked for consent/list.
        String unsubscribeUrl =
                linkService.httpsOneClickUrl(recipient.subscriptionId());

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, StandardCharsets.UTF_8.name());

        helper.setFrom("newsletter@example.com");
        helper.setTo(recipient.email());
        helper.setSubject("Product newsletter");
        helper.setText(plainBody, htmlBody);

        // Set exactly one value for each header.
        message.setHeader(
                "List-Id",
                "Product Newsletter <newsletter.example.com>");
        message.setHeader(
                "List-Unsubscribe",
                "<" + unsubscribeUrl + ">");
        message.setHeader(
                "List-Unsubscribe-Post",
                "List-Unsubscribe=One-Click");

        // Not sent yet; gateway/provider signs DKIM after headers exist.
        return message;
    }
}
~~~

`NewsletterRecipient` and `UnsubscribeLinkService` are application-built abstractions; `httpsOneClickUrl` must build URLs from a **trusted configured base URL**, a valid token, and HTTPS, never accepting an arbitrary URL passed by a request.

After composing:

~~~java
MimeMessage message =
        newsletterMailComposer.compose(recipient, plain, html);
mailSender.send(message);
~~~

**Only compose messages for recipients still permitted to receive them.** For batch campaigns, do not build one MimeMessage and swap `To` and the unsubscribe URL repeatedly; each recipient should get their own message and token.

### Why setHeader Instead of addHeader?

`setHeader(name, value)` replaces any existing header of the same name; `addHeader(name, value)` can add duplicate headers. Per list-header rules, each mail message should have only **one** `List-Unsubscribe`. If multiple layers in a pipeline add the header, it can cause unpredictable behavior and mismatch DKIM signatures.

Do not append header lines into the HTML body:

~~~java
// Does not create a MIME List-Unsubscribe header.
helper.setText(
        "List-Unsubscribe: <https://mail.example.com/u/token>", false);
~~~

Headers must reside in MIME headers, not inside text/plain or HTML bodies.

### Adding mailto to the Header

If the system processes emails sent to `unsubscribe@example.com`, you can offer the fallback:

~~~java
message.setHeader(
        "List-Unsubscribe",
        "<" + unsubscribeUrl + ">, "
            + "<mailto:unsubscribe@example.com?subject=unsubscribe>");
~~~

If the backend has no listener handling `mailto:`, **do not publish a fake URI** just to "complete the syntax." The HTTPS one-click flow must still work independently.

## 14. Implementing the One-Click Endpoint with Spring MVC

The server endpoint receives `POST` requests triggered by mail clients after recipients choose unsubscribe. It must return a result **without login or extra confirmation** and handle the right token/list.

Example:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/u")
public class OneClickUnsubscribeController {
    private final UnsubscribeService unsubscribeService;

    public OneClickUnsubscribeController(
            UnsubscribeService unsubscribeService) {
        this.unsubscribeService = unsubscribeService;
    }

    @PostMapping(
            path = "/{token}",
            consumes = {
                MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                MediaType.MULTIPART_FORM_DATA_VALUE
            })
    public ResponseEntity<Void> oneClick(
            @PathVariable String token,
            @RequestParam("List-Unsubscribe") String marker) {

        if (!"One-Click".equals(marker)) {
            return ResponseEntity.badRequest().build();
        }

        // Unsubscribe only the list authenticated by the token.
        unsubscribeService.unsubscribeByToken(token);

        // Do not redirect to another URL and do not require confirmation.
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/{token}")
    public ResponseEntity<String> viewPreferences(
            @PathVariable String token) {
        // Simple stub: GET only describes the action.
        // Real apps may render a preferences page.
        return ResponseEntity.ok(
                "Unsubscribe page. GET does not change state.");
    }
}
~~~

This is an illustrative skeleton; `UnsubscribeService` is application-built. In real systems, `GET` may show a page with a form-based confirm button or link into a preference center, yet must never alter consent merely upon being fetched.

### Requests Without Session/Cookies Must Be Accepted

Per RFC 8058, one-click requests do not include cookies or HTTP authorization. Therefore:

- The `POST /u/{token}` route must be publicly callable, relying solely on the narrowly scoped token.
- Do not require login, CAPTCHA, or a browser-session CSRF form token.
- When using Spring Security with default CSRF protection, apply a **targeted CSRF exemption** strictly for the one-click endpoint; never disable CSRF application-wide.
- Do not place the endpoint behind a reverse proxy enforcing SSO login.
- Do not rely on HTTP-to-HTTPS redirects from the published URL. The URL in the header must be valid HTTPS from the start.

A Spring Security 6 configuration illustrating how to exempt CSRF only for **one-click POST**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Bean
SecurityFilterChain mailSecurityFilterChain(
        HttpSecurity http) throws Exception {

    RequestMatcher oneClickPost = request ->
            "POST".equals(request.getMethod())
            && request.getServletPath()
                    .matches("^/u/[A-Za-z0-9_-]{43}$");

    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers(oneClickPost).permitAll()
                    .requestMatchers(
                            org.springframework.http.HttpMethod.GET,
                            "/u/**").permitAll()
                    .anyRequest().authenticated())
            .csrf(csrf ->
                    csrf.ignoringRequestMatchers(oneClickPost))
            .build();
}
~~~

The regex above assumes tokens are generated from 32 unpadded Base64URL bytes, **43 characters** long. If your token format differs, adjust the matcher. This is an **example configuration**, not a complete security config for every system; if the application already defines multiple `SecurityFilterChain` beans, integrate the rule into the right chain without accidentally replacing remaining endpoints. Spring Security APIs can vary across versions; match your project version.

**A targeted CSRF exemption is acceptable because the endpoint uses unpredictable tokens, narrow scope, and idempotent actions**. Never open APIs that change email addresses, passwords, or profiles merely because their routes also contain tokens.

## 15. UnsubscribeService: Validating Tokens and Persisting Suppression Durably

The controller only receives the request. Logic resolving subscriber/list and updating state lives inside a service transaction.

~~~java
import java.util.Optional;
import java.util.regex.Pattern;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UnsubscribeService {
    private static final Pattern TOKEN_FORMAT =
            Pattern.compile("[A-Za-z0-9_-]{43}");

    private final UnsubscribeTokenRepository tokens;
    private final MailingSubscriptionRepository subscriptions;

    public UnsubscribeService(
            UnsubscribeTokenRepository tokens,
            MailingSubscriptionRepository subscriptions) {
        this.tokens = tokens;
        this.subscriptions = subscriptions;
    }

    @Transactional
    public void unsubscribeByToken(String token) {
        if (token == null
                || !TOKEN_FORMAT.matcher(token).matches()) {
            return;
        }

        byte[] digest = hashToken(token);
        Optional<UnsubscribeTokenRecord> record =
                tokens.findActiveByHash(digest);

        if (record.isEmpty()) {
            return;
        }

        subscriptions.markUnsubscribed(
                record.get().subscriptionId());
    }

    private static byte[] hashToken(String token) {
        try {
            return java.security.MessageDigest
                    .getInstance("SHA-256")
                    .digest(token.getBytes(
                            java.nio.charset.StandardCharsets.US_ASCII));
        } catch (java.security.NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                    "SHA-256 unavailable", ex);
        }
    }
}
~~~

`UnsubscribeTokenRepository`, `MailingSubscriptionRepository`, and `UnsubscribeTokenRecord` are illustrative abstractions. `findActiveByHash` must look up the token by hash and check validity/tenant/list status if required by the schema. `markUnsubscribed` executes an idempotent `UPDATE` in the same transaction.

In the example, invalid/nonexistent tokens still return `204` through the controller. This avoids creating an oracle that leaks accounts/lists via status codes; systems can design another appropriate response, yet must not report an unperformed action as a successful removal in operational reports. Internal logs/metrics should distinguish invalid tokens from already-unsubscribed states without exposing email addresses.

### Do Not Identify Subscribers via HTTP Request Headers

Never use IP address, `User-Agent`, cookies, self-declared `From` addresses in the request, or an out-of-body email parameter as proof of subscriber identity. With one-click, **all unsubscribe context must reside in the URI/token generated at send time**. The mail receiver's IP may be a proxy/shared infrastructure and does not represent the recipient.

### Idempotency and Concurrent Transactions

Two concurrent POSTs for the same token must converge to the same state:

~~~text
POST A ---+
          +--> UPDATE subscription SET UNSUBSCRIBED
POST B ---+
          |
          v
Final state: UNSUBSCRIBED
~~~

Unique constraints, transactions, and conditional updates are the primary tools; there is no need to enqueue a duplicate unsubscribe job per POST. If suppression must sync to a third party, use an outbox/event to sync **after updating the durable source state**, while ensuring subsequent sends still respect the source state.

## 16. Blocking Sends After Unsubscribe, Including Already-Scheduled Emails

Suppose the application creates 50,000 newsletter jobs at 08:00; a user unsubscribes at 08:10; a worker is still sending scheduled jobs at 08:30. If recipients are filtered only when creating the campaign, sends can continue despite changed subscription state.

~~~text
08:00  Create 50,000 mail outbox jobs
08:10  Subscriber X performs one-click unsubscribe
08:30  Worker processes X's older job
        |
        +-- Wrong: send using 08:00 recipient snapshot
        |
        +-- Right: check suppression right before submit
                 -> SKIP for the list X left
~~~

Recommended flow:

~~~mermaid
flowchart TD
    A[Campaign / mail outbox job] --> B[Claim job]
    B --> C[Load subscriber + list + suppression]
    C --> D{Still permitted to receive?}
    D -- No --> E[Mark SKIPPED_UNSUBSCRIBED]
    D -- Yes --> F[Render message + List-Unsubscribe]
    F --> G[Rate limit / JavaMailSender.send]
    G --> H[Mark SMTP submission outcome]
~~~

**Checking at dispatch time** is vital because consent can change between scheduling and sending. If the system has multiple replicas and caches, design a suppression-sync strategy so workers do not rely too long on stale cache entries.

### An Irreducible Race Window Still Exists

A worker can verify the subscription is still active, and then the recipient unsubscribes right while the SMTP call is in flight:

~~~text
Worker: checks SUBSCRIBED
             |
             +---- Recipient POSTs unsubscribe
             |
Worker: SMTP call already started
~~~

No header-based mechanism can recall an email already accepted by an SMTP server. Shrink the race window by checking close to submit time, processing suppression fast, and avoiding stale batch snapshots. Avoid locking a subscription row across the entire SMTP network call just for "atomic send," since SMTP does not participate in database transactions.

### Do Not Use Marketing Suppression to Block Security Emails

If a subscriber leaves a promotional list, OTPs or transactional notices must still follow their own rules. Distinguish:

~~~text
mailCategory=SUBSCRIPTION, list=WEEKLY_NEWSLETTER
  -> check status of that exact list

mailCategory=TRANSACTIONAL, kind=PASSWORD_RESET
  -> check authorization and transactional need, do not use newsletter status
~~~

This does not mean transactional emails are sent unconditionally: abuse controls, recipient verification, security policies, and related obligations still apply. Simply do not conflate "unsubscribe newsletter" with "disable all emails."

## 17. Consent and List Quality

A system with compliant List-Unsubscribe headers can still suffer deliverability issues if it mails people who never consented to receive subscription emails.

Healthy list workflow:

1. User chooses to subscribe to a specific mailing list.
2. Record timestamp, source, and consent text version per policy.
3. For signups requiring confirmation, send a verification email and activate only once confirmed (**double opt-in**).
4. Send only content matching the consented subscription type.
5. Every email includes list details and a clear unsubscribe mechanism.
6. Upon receiving one-click POST, update state quickly and stop subsequent sends.
7. When a user re-subscribes, store **fresh consent**; never revive consent simply because they opened an old email.
8. Handle bounces/complaints/suppression under separate policies.

### One Subscriber Can Have Multiple Consent Channels

Example:

| Channel | Preference | Email Unsubscribe Effect |
|---|---|---|
| Email newsletter | SUBSCRIBED | Switches to UNSUBSCRIBED |
| Email promotions | SUBSCRIBED | Unchanged if it is a different list |
| Push notification | ENABLED | Unchanged |
| SMS marketing | ENABLED | Unchanged |
| Transactional email | Per business activity | Not blocked by newsletter one-click |

If the product wants an "unsubscribe all marketing" command, state its scope explicitly and provide a separate action. One-click from a single list must not silently change unrelated communication channels.

## 18. Testing MIME Headers Without Sending Real SMTP

Before sending, verify that Spring-created messages contain both headers properly. A round-trip test with Jakarta Mail:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.MimeMessageHelper;

class ListUnsubscribeHeaderTest {
    @Test
    void hasOneClickHeadersAfterMimeRoundTrip() throws Exception {
        Session session = Session.getInstance(new Properties());
        MimeMessage message = new MimeMessage(session);
        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, StandardCharsets.UTF_8.name());

        helper.setFrom("newsletter@example.com");
        helper.setTo("subscriber@example.net");
        helper.setSubject("Weekly newsletter");
        helper.setText("Newsletter content", false);

        message.setHeader(
                "List-Unsubscribe",
                "<https://mail.example.com/u/opaque123>");
        message.setHeader(
                "List-Unsubscribe-Post",
                "List-Unsubscribe=One-Click");

        message.saveChanges();
        ByteArrayOutputStream stream = new ByteArrayOutputStream();
        message.writeTo(stream);

        MimeMessage parsed = new MimeMessage(
                session,
                new ByteArrayInputStream(stream.toByteArray()));

        assertThat(parsed.getHeader("List-Unsubscribe"))
                .containsExactly(
                        "<https://mail.example.com/u/opaque123>");
        assertThat(parsed.getHeader("List-Unsubscribe-Post"))
                .containsExactly("List-Unsubscribe=One-Click");
    }
}
~~~

The test uses a dummy URL to check **MIME serialization**, not real tokens or deployed HTTP endpoints. Calling `MimeMessage.saveChanges()/writeTo` confirms headers survive raw message generation.

**This test does not verify DKIM.** Signatures are typically added at the gateway/provider after Spring sends. To verify RFC 8058 end-to-end, capture the raw message **after DKIM signing** and confirm a valid signature whose `h=` covers both headers.

### Do Not Assert Hardcoded Production Tokens

In unit tests you can use a dummy constant token. In real code, URLs are generated per recipient/list with random tokens. Assert URL structure, selected list, and token mapping via test repositories/services; never snapshot-test real secrets.

## 19. Testing the One-Click Endpoint with Spring MockMvc

Spring MockMvc can test POST/GET behavior without sending real emails.

~~~java
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class OneClickControllerTest {
    @Test
    void postUnsubscribesButGetDoesNot() throws Exception {
        UnsubscribeService service = mock(UnsubscribeService.class);
        MockMvc mvc = MockMvcBuilders.standaloneSetup(
                new OneClickUnsubscribeController(service))
                .build();

        String token = "a".repeat(43);

        mvc.perform(get("/u/" + token))
                .andExpect(status().isOk());
        verifyNoInteractions(service);

        mvc.perform(post("/u/" + token)
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("List-Unsubscribe", "One-Click"))
                .andExpect(status().isNoContent());

        verify(service).unsubscribeByToken(token);
    }
}
~~~

This test relies on the controller and service abstractions shown above; it verifies controller invocation flow, not repositories or the Spring Security filter chain.

Other tests to include:

- `POST` with missing/wrong marker returns `400` and does not change subscription.
- `POST` multipart/form-data with valid marker is processed.
- Unknown/invalid tokens cannot alter another subscriber.
- Two identical POSTs maintain UNSUBSCRIBED state without duplicate side effects.
- GET and HEAD, if supported, **never update subscriptions**.
- POST from clients lacking cookies/Auth/CSRF tokens still succeeds when the token is valid.
- HTTPS endpoint does not redirect before processing POST.
- DB write failure does not report success and silently keep sending.
- Worker dispatch skips unsubscribed subscribers.
- List A's token cannot unsubscribe list B.

**Standalone MockMvc tests do not run the full Spring Security chain.** Add integration tests with real security config to catch cases where one-click POST gets `403 CSRF` or `302 redirect to login`.

## 20. Diagnosis: Why Does the Unsubscribe Button Not Appear?

Even when the sending system includes both headers, recipients do not always see an "Unsubscribe" button next to the sender name. Mail clients decide display based on policies and sender trustworthiness.

| Symptom | Possible Cause | Diagnostic Check |
|---|---|---|
| No unsubscribe button | Missing either header, DKIM, or client-side conditions | Inspect received raw source, authentication, and sender reputation |
| Has List-Unsubscribe but no one-click | Missing `List-Unsubscribe-Post` or `mailto` only | Supply HTTPS URI and exact RFC 8058 marker |
| Header has HTTPS yet client ignores one-click | DKIM does not sign both headers | Check `h=` and DKIM verification results |
| Clicking unsubscribe returns 403 | Spring Security CSRF or login required | Scope CSRF exemption to route; permit public tokenized POST |
| Clicking unsubscribe returns 404 | Wrong URL or token not saved | Check base URL, route, and token mapping |
| Clicking unsubscribe returns 405 | Endpoint only implements GET | Implement actual POST handler |
| Clicking unsubscribe redirects 301/302/307 | Trailing slash, HTTP→HTTPS, SSO, or reverse proxy | Publish final HTTPS URL; do not redirect one-click POST |
| POST returns 415 | Server does not accept form-urlencoded/multipart | Check `consumes`/content type |
| POST returns 400 | Cannot parse `List-Unsubscribe=One-Click` | Check marker and form parameter binding |
| HTTP 204 yet newsletters still arrive | POST only logged; suppression ignored at dispatch | Check DB, cache, outbox, and send logic |
| Canceling one list blocks other emails | Global suppression accidentally applied across all categories | Separate list-level consent from transactional policy |
| Token from old email cancels new subscription | Token scope not bound to subscription cycle | Revoke/lifecycle tokens upon re-subscribing |
| Footer link works yet one-click does not | GET flow works, POST flow fails | Test endpoint with POST requests, not only opening in browser |

### End-to-End Diagnostic Workflow

~~~mermaid
flowchart TD
    A[Unsubscribe missing or not working] --> B[Inspect received raw email]
    B --> C{Both headers present?}
    C -- No --> D[Fix composer/provider header handling]
    C -- Yes --> E{HTTPS URL and marker valid?}
    E -- No --> F[Fix URL/RFC 8058 syntax]
    E -- Yes --> G{DKIM valid and signs both?}
    G -- No --> H[Fix signing order or DKIM config]
    G -- Yes --> I[Test form-urlencoded POST without cookies]
    I --> J{POST processed?}
    J -- No --> K[Check Security, route, proxy, Content-Type]
    J -- Yes --> L{Subscription updated and worker skipped?}
    L -- No --> M[Fix suppression/dispatch/cache]
    L -- Yes --> N[Check client display policies and reputation]
~~~

### Headers Can Be Rewritten by Providers

An email can pass through multiple layers:

~~~text
Spring MimeMessage
    |
    v
SMTP submission provider
    |
    v
DKIM signer / outbound gateway
    |
    v
Mail transfer / security gateway
    |
    v
Recipient mailbox provider
~~~

Do not inspect only the message before `JavaMailSender.send` and assume the Inbox sees the same headers. A gateway can add, normalize, strip, or rewrite List-Unsubscribe, altering DKIM and client behavior. When investigating, compare **raw MIME before sending** against **raw MIME actually seen by the recipient**.

## 21. Securing the Unsubscribe Endpoint and Personal Data

### Tokens Are Narrowly Scoped Capabilities

Anyone possessing a valid URL can request unsubscribing from that list. This is intentional in one-click because mail receivers do not send login cookies or HTTP authorization. Therefore, design tokens as bearer capabilities:

- Generate with a CSPRNG with sufficient entropy.
- Never use emails or sequential IDs as guessable tokens.
- Scope to one subscriber/list and the right tenant.
- Grant no permission to read/edit account details.
- Store hashes or suitable cryptographic verification data.
- Revoke/rebind tokens when required by consent lifecycle.
- Never emit tokens into logs, analytics, or unnecessary exception traces.

### Do Not Leak Tokens When GET Opens a Page

If the footer link opens a GET page, browsers can leak the URL via `Referer` if the page loads third-party resources. Thus:

- Serve over HTTPS with a valid certificate.
- Set `Referrer-Policy: no-referrer` on the subscription management page.
- Avoid third-party scripts/pixels/assets on pages carrying sensitive tokens.
- Never pass tokens into analytics URLs or external navigation.
- Never reflect tokens into HTML/JavaScript in a way that creates XSS.
- Configure access logs to omit/redact URLs containing tokens.

### Rate Limiting Requests to Reduce Abuse

A public one-click endpoint can be scanned or flooded with POSTs. Apply:

- Reverse-proxy rate limits by source and behavior, tuned to allow legitimate mail receivers.
- Length and character-set limits on tokens.
- Sensible max request counts and body sizes.
- HTTP/DB timeouts so resources are not held indefinitely.
- Monitoring for invalid-token rates and DB errors.

**Never put CAPTCHAs or interactive confirmations on one-click POST.** They contradict RFC 8058's purpose. Rate limiting must also avoid falsely blocking legitimate mail clients/receivers sending multiple requests from shared IPs or IP ranges.

### Do Not Use Unsubscribe as an Email Existence Oracle

An endpoint returning:

~~~json
{ "email": "customer@example.net", "subscribed": true }
~~~

for an unauthenticated URL can leak user data. One-click only needs to process the request, not return email addresses or profile details. For nonexistent tokens, responses must not reveal lists or user status.

### HTTPS and Redirects

The header URL must be real HTTPS, not HTTP redirecting afterward. RFC 8058 requires senders **not to return redirects for one-click POST**. In particular, reverse proxies can unintentionally redirect due to:

- Missing or added trailing slashes.
- Old-to-new domain migration.
- Enforcing login/SSO redirects.
- HTTP-to-HTTPS upgrades.
- WAF challenges or bot-protection interstitials.

Publish the exact final origin/path and configure proxies so POST executes directly without redirects.

## 22. Metrics, Auditing, and Unsubscribe Processing SLAs

Unsubscribe handling is a **continuous operational business flow**. You cannot test the endpoint once and forget it. When the service breaks, recipients keep getting emails, spam complaints rise, and sender reputation drops.

Suggested metrics:

| Metric | Meaning |
|---|---|
| `unsubscribe_post_total` | Valid POST requests hitting the endpoint |
| `unsubscribe_success_total` | Requests processed successfully |
| `unsubscribe_invalid_token_total` | Tokens that failed verification |
| `unsubscribe_failure_total` | Service/DB errors |
| `unsubscribe_processing_duration` | POST processing latency |
| `unsubscribe_to_suppression_lag` | Lag from request to active suppression state |
| `subscription_mail_skipped_total` | Jobs skipped due to unsubscribed status |
| `subscription_mail_sent_after_optout_total` | Suspected sends after opt-out |
| `subscription_backlog_age` | Age of pending subscription mail jobs |

Metric labels should be low-cardinality dimensions such as list type, result code, environment, or provider. Never use emails, tokens, or subscriber IDs as metric labels.

### Minimum Audit Event

~~~text
event=subscription_unsubscribed
subscriptionId=8f2b...
listKey=WEEKLY_NEWSLETTER
source=RFC8058_ONE_CLICK
processedAt=2026-11-12T10:00:00Z
result=ALREADY_UNSUBSCRIBED_OR_UPDATED
~~~

Values are examples. An audit event should include source, timestamp, list, and outcome while avoiding raw unsubscribe tokens. When legal/policy consent proof must be kept, use a separate access-controlled data store.

### The 48-Hour Window and Practical Targets

Google requires/guides processing subscription unsubscribes within 48 hours per its sender/subscription guideline pages. Technically, a one-click POST can update the DB **immediately**, so a sensible operational target is seconds or minutes rather than waiting near 48 hours.

If syncing suppression to an external email service provider, monitor sync lag and retries; meanwhile, the internal sending system must still block jobs seeing opt-out rather than waiting for a nightly batch to stop sends.

### Useful Alerts

- Rising HTTP 5xx rate on the unsubscribe endpoint.
- Endpoint receives only GETs and zero successful POSTs while subscription mails continue sending.
- DKIM verification of one-click headers fails after a gateway change.
- Suppression DB updates yet workers keep sending to canceled lists.
- Sudden spike in invalid tokens after a URL-generation deploy.
- Accidental sends after unsubscribe exceed policy thresholds.

## 23. Common Anti-Patterns

### 23.1. Adding Only a Body Link and Assuming One-Click Exists

~~~html
<a href="https://example.com/preferences">Unsubscribe</a>
~~~

An HTML link is necessary for user experience, yet **does not replace** `List-Unsubscribe` and `List-Unsubscribe-Post` headers when providers require RFC 8058 one-click.

### 23.2. Using Only mailto in List-Unsubscribe

~~~mime
List-Unsubscribe: <mailto:unsubscribe@example.com>
~~~

This RFC 2369-style header can be helpful, yet lacks an HTTPS endpoint for mail receivers to POST. It does not satisfy RFC 8058 one-click.

### 23.3. Using GET to Unsubscribe Immediately

~~~java
@GetMapping("/unsubscribe")
public void unsubscribe(@RequestParam String email) {
    repository.unsubscribe(email);
}
~~~

Mail scanners/prefetchers can trigger unintended unsubscribes. GET should only display a page or non-mutating view; one-click mutates via POST with the marker.

### 23.4. Sharing One Token Across All Recipients

If every newsletter uses `https://mail.example.com/u/newsletter`, the endpoint cannot know who is unsubscribing without asking for more info. Generate per-subscription tokens mapped to the exact list/recipient.

### 23.5. Putting Raw Email Addresses Directly in URLs Without Protection

~~~text
https://mail.example.com/u?email=user@example.net&list=NEWS
~~~

The URL is easily tampered with and leaks PII via logs/proxies. Use high-entropy opaque tokens or tamper-resistant signing; never let the request dictate subscriber identity on its own.

### 23.6. One-Click POST Returning a Page Asking for Another Confirmation

One-click must complete without extra clicks. A preference center can exist separately, yet must not be a mandatory hurdle for RFC 8058 POST.

### 23.7. Supporting Only JSON POST

An endpoint accepting only:

~~~http
Content-Type: application/json

{"unsubscribe": true}
~~~

is incompatible with standard one-click requests using form encoding. Support `List-Unsubscribe=One-Click` with `application/x-www-form-urlencoded` and/or `multipart/form-data` as specified by RFC 8058.

### 23.8. Adding Headers After DKIM Signing

Then the signature does not cover the new headers or breaks; RFC 8058 requires a valid signature covering both headers. Add headers **before the provider signs**, and inspect raw MIME on the receiving side.

### 23.9. Checking Only DKIM Pass While Ignoring h=

A passing DKIM signature does not guarantee `List-Unsubscribe` and `List-Unsubscribe-Post` were signed. Read `h=` on the valid signature to confirm both.

### 23.10. Blocking All Emails When Unsubscribing from One Mailing List

A recipient leaving a newsletter does not mean rejecting invoices, OTPs, or other lists. Apply list-scoped consent and separate transactional policies.

### 23.11. Filtering Subscribers Only at Campaign Creation

Users who unsubscribe after enqueueing yet before sending will keep receiving messages. Check suppression **close to dispatch time** and apply policy to queued jobs.

### 23.12. Logging POST Without Persisting State

HTTP 204 without database updates causes continued sends. The endpoint must persist suppression durably with transactions, error handling, and metrics.

### 23.13. Requiring Cookies, SSO, or CSRF Tokens for One-Click

Mail clients do not hold the recipient's browser session. The URL/token is the narrowly scoped authentication credential; expose the right POST endpoint publicly with tightly scoped CSRF exemption rather than disabling CSRF globally.

### 23.14. Using HTTP and Redirecting to HTTPS

RFC 8058 requires HTTPS URIs and no POST redirects. Publish the final HTTPS URL and configure proxies to accept it directly.

### 23.15. Auto-Re-Subscribing After Non-Consent Actions

Opening a management page, logging in, making a new purchase, or receiving a transactional email does not equal opting back into marketing. Require an explicit opt-in and store fresh consent.

### 23.16. Letting a Multi-Tenant Service Mis-Scope Tokens

Tenant A's token must never alter Tenant B's subscription. Token mapping must resolve to a subscription record with explicit tenant/list/subscriber; repository queries must never rely solely on a request-supplied ID.

## 24. Implementation Roadmap in Spring Framework Mail

If a system already sends newsletters without one-click, roll out in this order:

1. **Classify emails:** separate marketing/subscription from transactional.
2. **Define lists:** establish `list_key` and `List-Id` for each subscription list.
3. **Audit consent:** who actually opted in, consent source, and where double opt-in is needed.
4. **Build suppression store:** durably track SUBSCRIBED/UNSUBSCRIBED per subscriber/list.
5. **Generate tokens:** CSPRNG, opaque, narrow scope, store mapping/hash, and define lifecycle.
6. **Build HTTPS endpoint:** GET does not mutate state; POST checks one-click marker and runs idempotently.
7. **Configure security:** HTTPS, no session/Auth requirement for POST, targeted CSRF exemption on route, log redaction.
8. **Add headers when composing:** List-Unsubscribe, List-Unsubscribe-Post, and List-Id before DKIM signing.
9. **Keep body links:** clear unsubscribe footer and preference center in both HTML and text.
10. **Verify DKIM/provider:** raw MIME at receiver, `h=` signing both headers.
11. **Verify dispatch:** suppression applies to already-enqueued jobs and across replicas.
12. **Run negative tests:** GET, invalid token, wrong marker, duplicate POST, multiple lists, expired consent.
13. **Monitor SLAs:** POST success, suppression lag, skipped jobs, and sends after opt-out.
14. **Roll out carefully:** pilot one list first, then expand to remaining lists.

### Acceptance Test Suite

| Scenario | Expected Result |
|---|---|
| Recipient not subscribed to list | Subscription email is not sent |
| Composed marketing email | Has one syntactically valid header pair |
| Received email | Valid DKIM signature covers both headers |
| Recipient clicks unsubscribe in client | POSTs exact token/marker, no login or redirect |
| Bot only GETs URL | Subscription does not change |
| Duplicate POST twice | Remains a single UNSUBSCRIBED state |
| Token for list A | Unsubscribes A only, not B |
| Transactional email after newsletter opt-out | Still follows separate transactional policy |
| Campaign job enqueued before unsubscribe | Skipped at dispatch if not yet submitted |
| Same recipient validly re-subscribes | Fresh consent and clear token lifecycle |
| Proxy/WAF enabled | Does not block POST or force unintended redirects |
| User opens email in client without button support | Footer link still works |

## 25. Frequently Asked Questions

**What is List-Unsubscribe?** A MIME header telling mail clients how to perform an unsubscribe action from a mailing list, defined in RFC 2369.

**What is List-Unsubscribe-Post for?** It signals RFC 8058 one-click when set to `List-Unsubscribe=One-Click` alongside an HTTPS URI in List-Unsubscribe.

**Are both headers required for marketing emails?** For senders/mail types subject to one-click requirements from mailbox providers like Gmail, yes. Beyond specific mandates, full RFC 8058 implementation is good practice for subscription mail.

**Is a mailto link alone enough?** Not for RFC 8058 one-click. An HTTPS URI accepting POST is required.

**Should users be asked to log in when unsubscribing?** One-click POST must not require login or extra interaction. Tokens in URLs must be narrowly scoped and unpredictable.

**Can the same URL be used for the GET footer and POST one-click?** Yes, provided GET does not change state and POST with the valid marker executes unsubscribe. Never redirect POST.

**Why shouldn't a GET unsubscribe directly?** Mail security scanners can fetch URLs automatically, unintentionally unsubscribing recipients.

**Can I return `302` after POST to redirect to a thank-you page?** You should not. RFC 8058 requires returning no HTTPS redirects for one-click POST actions. Return `204` or `200` directly after processing.

**Is a DKIM pass enough?** Not yet. A valid DKIM signature must cover both unsubscribe headers in `h=`.

**Does Spring Mail have a dedicated API for List-Unsubscribe?** Use Jakarta Mail's `MimeMessage.setHeader(...)` alongside `MimeMessageHelper`. Do not put the two header lines inside the body.

**Should tokens embed email addresses?** Do not place plaintext emails in URLs. Unpredictable opaque tokens reduce spoofing and data-leak risks; still protect tokens since they grant unsubscribe capability.

**Can one token cancel multiple lists?** One-click should cancel the exact list associated with the email. If offering global unsubscribe, design a separate action with explicit scope.

**Does unsubscribing from a newsletter block OTPs/receipts?** It should not. Transactional and subscription emails must have separate policies.

**Must requests be processed immediately?** Update suppression immediately when a valid POST succeeds; Google guides processing unsubscribes within 48 hours. Waiting near 48 hours is poor UX and increases risk of extra sends.

**What if a send already succeeded right as the recipient clicked unsubscribe?** An already-accepted SMTP submission cannot be recalled. Checking status close to send time minimizes the race for unsubmitted emails.

**List-Unsubscribe is present, so why isn't Gmail showing the button?** Clients also evaluate authentication, reputation, and UI policies. Inspect received raw MIME, DKIM `h=`, URL/endpoint, and provider criteria.

**Is List-Id also needed?** List-Id helps identify mailing lists and is often helpful for subscription messages, yet does not replace the two RFC 8058 headers.

**Should the newsletter break if a mail client sends POST twice?** Unsubscribe commands must be idempotent. Repeated POSTs must preserve UNSUBSCRIBED state rather than returning errors that trigger endless retries.

## 26. Summary

**List-Unsubscribe for subscription emails** combines **standard MIME headers**, a **one-click HTTPS endpoint**, **durable consent/suppression**, and **dispatch-time sending policy**.

For Spring Framework Mail, the core model:

~~~text
Subscriber opts in to receive list
            |
            v
Persist consent per subscriber + list
            |
            v
Generate opaque unsubscribe token
            |
            v
Spring MimeMessage:
  List-Unsubscribe: <https://.../u/token>
  List-Unsubscribe-Post: List-Unsubscribe=One-Click
  List-Id: ...
            |
            v
DKIM signer signs both unsubscribe headers
            |
            v
SMTP / mailbox provider
            |
            v
Mail client POSTs when recipient chooses unsubscribe
            |
            v
Spring endpoint validates token
            |
            v
Update UNSUBSCRIBED for the right list
            |
            v
Dispatcher stops sending subscription mail
~~~

Remember four principles:

1. **Headers must follow RFC 8058:** HTTPS List-Unsubscribe + List-Unsubscribe-Post, with DKIM signing both.
2. **POST completes in one click:** no login/cookies/confirmation/redirects; GET never self-unsubscribes.
3. **Scope unsubscribes accurately:** subscriber + mailing list, without wrongly blocking transactional emails.
4. **Suppression must actually prevent sends:** persist durably and check at dispatch, including already-scheduled jobs.

When these layers work together seamlessly, unsubscribes become a reliable pillar of subscription email delivery—respecting recipient choice and sustaining long-term deliverability.
