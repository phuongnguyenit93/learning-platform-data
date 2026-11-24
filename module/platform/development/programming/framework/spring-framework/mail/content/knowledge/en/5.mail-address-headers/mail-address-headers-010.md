# Empty, Duplicate, or Invalid Recipient Lists

When sending emails with **Spring Framework Mail**, crafting the subject and body is only half the job. The application must also decide **who receives the message**, whether each person belongs in **To**, **Cc**, or **Bcc**, and whether the address list complies with business rules. An empty recipient list, duplicate addresses, or invalid syntax can cause sending to fail, trigger unintended duplicate emails, or accidentally expose recipients' addresses.

These issues arise especially when addresses are aggregated from multiple sources: registration forms, databases, distribution groups, CRM systems, multiple approvers, or CSV imports. A string that looks like an email in a UI is not guaranteed to be a valid **mailbox**, and a syntactically valid mailbox is not guaranteed to exist or accept mail.

This lesson focuses on identifying, handling, and defining boundaries of responsibility for **empty, duplicate, or invalid recipient lists** in Spring Mail. Examples use **JavaMailSender**, **SimpleMailMessage**, **MimeMessageHelper**, and **Jakarta Mail**.

## 1. Distinguishing Displayed Recipients from Transport Recipients

Email has two layers of recipient information:

- **Header recipients**: the **To**, **Cc**, and **Bcc** fields used by the application when preparing a MIME message.
- **SMTP envelope recipients**: the addresses sent by the SMTP client via **RCPT TO** commands asking the receiving server to deliver the message.

In standard **JavaMailSender** usage, addresses placed in To/Cc/Bcc on the message serve as the source for Jakarta Mail to determine delivery recipients. However, an SMTP transaction can also receive envelope recipients specified separately by the API/transport, and emails can undergo aliasing or forwarding on downstream servers.

~~~text
Application data sources
    |
    | Gather To / Cc / Bcc lists
    v
Check emptiness, syntax, duplicates, and business policy
    |
    v
MimeMessage or SimpleMailMessage
    |
    | Headers: To, Cc, Bcc
    v
JavaMailSender / Jakarta Mail
    |
    | SMTP: RCPT TO for delivery targets
    v
Mail server
    |
    | Accepts, rejects, or defers per address;
    | may route, expand aliases, or forward
    v
Destination mailbox (if delivery succeeds)
~~~

**Key point:** the condition for having recipients to send to is generally **at least one valid destination address in the effective recipient set**, not necessarily an entry in **To**. A **Bcc-only** message can still be sent. Conversely, descriptive text in a To header does not automatically create an SMTP recipient.

### To, Cc, and Bcc Carry Different Semantics

| Group | Typical Meaning | Who Can See It? |
| --- | --- | --- |
| **To** | Primary recipients | Displayed in message headers |
| **Cc** | Public carbon-copy recipients | Displayed in message headers |
| **Bcc** | Blind carbon-copy recipients | Bcc list is not disclosed to other recipients |

At transport, an address in To, Cc, or Bcc can all generate an **RCPT TO** command. Yet in business logic and privacy, the three groups have **different meanings**. Therefore, deduplicating recipients is not as simple as merging all three lists and writing everyone into To.

## 2. Empty Recipient Lists: Multiple Distinct Cases

The word "empty" can describe several input states:

~~~text
to = null
to = []
to = [""]
to = ["   "]
to = ["", "  ", null]
to = []
cc = []
bcc = ["hidden@example.test"]
~~~

The first four cases supply no usable mailbox; the last case **has one Bcc recipient** even though both To and Cc are empty. Validation rules must consider both business intent and all three groups.

### Empty at Data Layer vs. Empty After Filtering

Suppose a system loads subscribers from a database:

~~~text
Original source:
["lan@example.test", " ", null, "minh@example.test"]

After filtering blanks:
["lan@example.test", "minh@example.test"]
~~~

If the rule is to **skip blank entries** and proceed with valid addresses, the list still has recipients. However, if the system handles **financial notices or mandatory approvals**, silently dropping an address can be a serious business defect. In such cases, **reject the entire request with a clear error** instead of silently filtering entries out.

No single policy fits every email type. Decide upfront:

1. **Is an empty list allowed?** A scheduled job might simply skip sending when there are zero subscribers, whereas a "send invoice to customer X" API should fail loudly.
2. **Does a single blank item fail the whole request or get skipped?** This depends on criticality and data origin.
3. **Is To mandatory, or is any recipient across To/Cc/Bcc sufficient?** For Bcc-only messages, many systems do not require To.
4. **If zero recipients remain after filtering, what is the outcome?** "Skipped due to no targets" and "sent successfully" are not the same status.

### Having Recipients Without To

Illustrative example:

~~~text
To:  []
Cc:  []
Bcc: ["audit@example.test"]
~~~

This is a valid send request with a recipient. Depending on the library and infrastructure, the email can be delivered with Bcc as the envelope recipient. Some systems render a label like **undisclosed recipients** when To is absent; that display label is not an SMTP delivery target.

By contrast:

~~~text
To:  []
Cc:  []
Bcc: []
~~~

Without a separate envelope recipient list, the application **has no delivery target**. Catch this condition **before calling `JavaMailSender.send(...)`** rather than relying on whatever exception a particular library version or SMTP transport happens to throw.

### Ordering Checks Produces Clearer Errors

A processing pipeline can look like:

~~~text
Receive send request
      |
      v
Has list data? ---- No ---> Missing recipient error
      |
     Yes
      v
Normalize input per policy
      |
      v
Blank or invalid syntax items? ---- Yes ---> Reject or record per-item errors
      |
      No
      v
Check To / Cc / Bcc duplicates
      |
      v
At least one recipient left? ---- No ---> Skip with reason or return error
      |
     Yes
      v
Build message and send
~~~

If input contains **recipients with invalid addresses**, report **invalid address** rather than treating it as an **empty list**. Accurate errors help callers fix the real problem.

## 3. Duplicate Addresses: String Duplicates, Mailbox Duplicates, and Delivery Target Duplicates

Duplication exists at multiple levels:

| Duplicate Type | Example | Note |
| --- | --- | --- |
| Exact duplicate | **lan@example.test** appears twice | Detectable via string comparison |
| Duplicate after trimming surrounding whitespace | **" lan@example.test "** and **"lan@example.test"** | Normalizable at the ingestion boundary |
| Different domain casing | **Lan@Example.Test** and **Lan@example.test** | Domain part is case-insensitive |
| Different local-part casing | **Lan@example.test** and **lan@example.test** | Do not assume they are always the same mailbox across every system |
| Different spelling, same alias | **team@example.test** and **member@example.test** | Applications usually cannot know true alias targets |
| Dot variations or plus-addressing | **name+promo@...**, **name@...** | Never apply one provider's rules to every domain |
| Cross-group duplicate | **lan@example.test** in both To and Bcc | Creates visibility conflicts; needs explicit policy |

A list containing two identical strings definitely holds a **data-level duplicate**. Whether two differently spelled addresses resolve to the same final mailbox belongs to the mail/alias system, which your application cannot always know.

### Do Not Lowercase Entire Addresses Arbitrarily

In a standard email address:

~~~text
local-part@domain
~~~

The **domain** is case-insensitive. Under traditional SMTP rules, the **local-part** can carry case-sensitive meaning decided by the destination mail server, even though many popular providers treat it case-insensitively. Therefore, for a technically safe deduplication key, **preserve the local-part and lowercase only the domain**.

Do not strip dots, plus signs, or suffixes like **`+news`** in the local-part automatically. Certain services apply such alias rules, yet they are not universal across all email systems. Over-aggressive merging can drop a valid distinct recipient.

For products with internal account verification, your application may define **its own documented canonicalization policy**. Apply that policy consistently at both account registration and mail sending rather than guessing from address strings.

### Duplicates Within the Same Group

Example:

~~~text
To:
  - lan@example.test
  - minh@example.test
  - lan@example.test
~~~

If two entries represent the same mailbox under your chosen policy, only one recipient entry is normally needed for a single **message**. Listing it twice can produce duplicate recipient commands, server-side collapsing, or transport-dependent behavior. Do not rely on SMTP always handling this the way your application expects.

Two common approaches:

- **Reject duplicate input** with a clear error naming the repeated item—ideal for APIs expecting exact data.
- **Deduplicate cleanly** and log how many duplicates were removed—suitable for batch/import flows where repetition has no business meaning.

When deduplicating, **preserve first-seen order** so data stays predictable and traceable. Avoid reordering the whole list simply because a Set was used internally.

### Duplicates Across To, Cc, and Bcc Are More Dangerous

Consider:

~~~text
To:  ["lan@example.test"]
Cc:  []
Bcc: ["lan@example.test"]
~~~

The same address appears in both a public group and a hidden group. Merging into a flat Set **loses group intent**: keeping the To entry exposes the recipient publicly, whereas keeping only Bcc alters the request's semantics.

In serious systems, define **cross-group conflict rules**. For example:

1. **Reject when the same mailbox appears in multiple groups**, requiring the caller to classify it cleanly. This is predictable and protective of Bcc.
2. Or **apply a pre-agreed precedence order**, such as an organizational rule where To takes precedence over Cc and Bcc. Understand the visibility consequences and record the decision.
3. For strict privacy requirements, **build a separate message per recipient** instead of combining multiple targets in one MIME message.

Never "fix duplicates" by moving every recipient into **To**, as that can leak recipients intended to remain Bcc.

### One Address Can Appear Across Separate Send Jobs

Deduplicating **within a single message's list** does not prevent sending multiple emails to the same person across separate jobs. For example, a user may belong to two subscription lists, or two business events may emit two similar mail jobs. During retries, a worker may also resend an email when the previous send outcome was unknown.

To prevent duplicate emails from the same business event, use a business key or **idempotency key** on the mail job, separate from recipient-list deduplication. Even application-level idempotency cannot guarantee **exactly-once email delivery** if the provider accepted a message and the response was lost.

## 4. "Invalid" Has at Least Four Meanings

An address can pass one validation layer and fail the next:

| Validation Layer | Question | Example Problem |
| --- | --- | --- |
| **Data shape** | Is it a non-null, non-whitespace single string? | **null**, **""**, **"   "** |
| **Email syntax** | Does the string match an accepted mailbox syntax? | **user@**, **@example.test**, misplaced brackets or characters |
| **Application policy** | Is this address permitted to receive this kind of mail? | User unsubscribed from marketing, domain blocked by internal policy |
| **Actual deliverability** | Can the mail server and mailbox accept mail at send time? | Non-existent mailbox, domain accepts no mail, quota or policy rejection |

Syntax checking in Java only tells you the string **looks valid according to parser rules**. It does not guarantee valid DNS, mailbox existence, user ownership, or inbox delivery.

### Typical Inputs to Consider

| Input Data | Assessment |
| --- | --- |
| **lan@example.test** | Valid common mailbox form |
| **" lan@example.test "** | Surrounding whitespace; can be stripped at the ingestion boundary |
| **""** or **null** | Missing address |
| **lan@** | Missing domain part |
| **@example.test** | Missing local-part |
| **lan@@example.test** | Syntax incompatible with standard mailboxes |
| **Lan Nguyen <lan@example.test>** | Valid mailbox with display name per email syntax; parsers may accept it, though APIs expecting bare addresses may reject it |
| **lan+course@example.test** | A **`+`** in the local-part does not make an address invalid |
| **a.b@example.test** | Dots inside a local-part are normally valid |
| **"a b"@example.test** | Quoted local-part syntax; naive validators may reject it even though standards support it |
| **lan@example.test, minh@example.test** | Valid *list* in one string when invoking a list parser; invalid as a single mailbox if the API requires one address per item |

The **`.test`** domains in these examples are purely illustrative, not live mail domains. Nor is this list the full RFC grammar; many standards-compliant addresses use uncommon forms.

### Avoid Overly Simple Regexes for Judging Every Address

A regex such as:

~~~regex
^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+$
~~~

misses many valid addresses (such as local-parts containing **`+`**) while failing to catch invalid cases (such as misplaced dots or invalid domain labels). Checking "one `@` and one dot" is insufficient for syntax validation.

In the Spring Mail/Jakarta Mail ecosystem, use **`InternetAddress`** to parse and validate syntax. Then apply your product's **input policy**, such as requiring each list item to be a bare mailbox and rejecting groups or comma-separated lists within a single element.

### InternetAddress Does Not Verify Mailbox Existence

Syntax validation example:

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

public final class MailboxParser {
    private MailboxParser() {
    }

    public static InternetAddress parseOne(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("Recipient address is missing");
        }

        String value = input.strip();
        if (value.indexOf('\r') >= 0 || value.indexOf('\n') >= 0) {
            throw new IllegalArgumentException("Address contains newline");
        }

        try {
            InternetAddress mailbox = new InternetAddress(value, true);
            mailbox.validate();
            if (mailbox.isGroup() || !value.equals(mailbox.getAddress())) {
                throw new IllegalArgumentException(
                        "Each item must be a bare mailbox"
                );
            }
            return mailbox;
        } catch (AddressException ex) {
            throw new IllegalArgumentException(
                    "Invalid recipient address syntax", ex
            );
        }
    }
}
~~~

This snippet demonstrates **one specific policy**: accept one bare mailbox per item, trim outer whitespace, reject newlines, and disallow groups or user-provided display names. It is not a universal RFC address parser for every product; your application's rules may be broader or stricter.

Calling **`validate()`** does not verify MX records, mailbox existence, or SMTP acceptance. An address passing this step can still be rejected later. Never build an "email existence checker" solely around `InternetAddress.validate()`.

### Internationalized Addresses and SMTPUTF8

Addresses containing Unicode in the local-part or domain must be handled according to actual support in the parser, application, SMTP server, and extensions like **SMTPUTF8**. Internationalized domains may require IDNA conversion during validation and transport.

Do not blindly convert all Unicode addresses to ASCII or apply an ASCII-only regex and declare every internationalized address invalid. Conversely, accepting a Unicode string at your API layer **does not guarantee the SMTP path can deliver to it**. Product policy must align with infrastructure capabilities.

## 5. Recipient Data Is Untrusted Input

Email addresses can arrive from forms, file imports, tokens, or external systems. At the application boundary, prevent input from altering header structure or leaking data.

### Watch Out for Header Injection

A string containing a newline:

~~~text
lan@example.test
Bcc: attacker@example.test
~~~

must never be treated as a normal mailbox. When applications manually concatenate raw email headers, **CR/LF** in input can create unintended headers. APIs like **MimeMessageHelper** and **InternetAddress** help manage MIME structure, yet the application must still enforce clean input boundaries, reject invalid control characters, and **never concatenate raw headers from unvalidated data**.

Never "repair" an address by stripping odd characters until the parser accepts it, because doing so can turn invalid input into **someone else's mailbox**. On syntax errors, report the problem clearly so the data creator can fix it.

### Valid Syntax Does Not Mean Authorized to Receive

Consider a platform with two mail streams:

- **Transactional mail**: verification codes, invoices, critical account updates.
- **Marketing mail**: newsletters, promotional offers.

The same mailbox may be eligible for one stream and ineligible for the other due to preferences, consent rules, or unsubscribe state. **Parsers cannot replace purpose and authorization checks**.

Systems should also enforce per-request recipient caps, rate limits, and caller authorization. If a user can submit arbitrary lists without limits, bulk sending can exhaust resources and damage your sending domain's reputation.

## 6. Building a Shared Validation Policy for To, Cc, and Bcc

To keep every mail feature from validating addresses inconsistently, centralize rules at the boundary before building **`MimeMessage`**. For example, adopt a policy like:

1. **`null`** at list level equals an empty list; **`null`** or blank string at item level is an error.
2. Each item must be **a bare mailbox**. Disallow comma-separated addresses inside a single list item.
3. Use **`InternetAddress`** for syntax parsing; cap total recipients per operational limits.
4. Detect duplicates across **To, Cc, and Bcc combined**. Reject duplicates so the caller assigns the right group; never silently convert Bcc into To.
5. If all three groups contain zero mailboxes, fail with **no recipients**.
6. Preserve the order and spelling of accepted addresses when populating the message.

The following Java 21 example uses **`MailboxParser.parseOne(...)`** defined earlier:

~~~java
import jakarta.mail.internet.InternetAddress;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public final class RecipientPolicy {

    private static final int MAX_RECIPIENTS = 100; // Example business limit

    private RecipientPolicy() {
    }

    public record RecipientSet(
            List<InternetAddress> to,
            List<InternetAddress> cc,
            List<InternetAddress> bcc
    ) {
        public int total() {
            return to.size() + cc.size() + bcc.size();
        }
    }

    public static RecipientSet check(
            List<String> to,
            List<String> cc,
            List<String> bcc
    ) {
        Set<String> seen = new HashSet<>();

        List<InternetAddress> checkedTo = checkGroup(to, "To", seen);
        List<InternetAddress> checkedCc = checkGroup(cc, "Cc", seen);
        List<InternetAddress> checkedBcc = checkGroup(bcc, "Bcc", seen);

        RecipientSet result = new RecipientSet(
                List.copyOf(checkedTo),
                List.copyOf(checkedCc),
                List.copyOf(checkedBcc)
        );

        if (result.total() == 0) {
            throw new IllegalArgumentException(
                    "No recipients in To/Cc/Bcc"
            );
        }

        return result;
    }

    private static List<InternetAddress> checkGroup(
            List<String> input,
            String group,
            Set<String> seen
    ) {
        List<InternetAddress> checked = new ArrayList<>();
        if (input == null) {
            return checked;
        }

        for (int index = 0; index < input.size(); index++) {
            InternetAddress address = MailboxParser.parseOne(
                    input.get(index)
            );
            String key = duplicateKey(address.getAddress());

            if (!seen.add(key)) {
                throw new IllegalArgumentException(
                        "Duplicate recipient at " + group
                        + "[" + index + "]"
                );
            }

            checked.add(address);
            if (seen.size() > MAX_RECIPIENTS) {
                throw new IllegalArgumentException(
                        "Exceeded maximum allowed recipients"
                );
            }
        }
        return checked;
    }

    private static String duplicateKey(String mailbox) {
        int at = mailbox.lastIndexOf('@');
        if (at <= 0 || at == mailbox.length() - 1) {
            throw new IllegalArgumentException(
                    "Address must contain local-part and domain"
            );
        }
        // Preserve local-part. Lowercase only the domain.
        return mailbox.substring(0, at)
                + "@"
                + mailbox.substring(at + 1).toLowerCase(Locale.ROOT);
    }
}
~~~

This is **one chosen input policy implementation**, not a claim that every standards-compliant address must be handled identically. Domain normalization here targets common addresses; systems supporting internationalized addresses may apply IDNA rules consistently. Splitting on the last **`@`** works safely after the parser and bare-mailbox policy have run.

### Why Use a Single `seen` Set?

Using three separate sets for To, Cc, and Bcc catches duplicates only **within each group** while missing an address present in both To and Bcc. Using **one `seen` set across all three groups** detects conflicts before constructing the message.

The **`HashSet`** only stores keys for duplicate checks; separate **`ArrayList`** instances per group preserve input order. Because this example **rejects duplicates**, no deduplication discards group classification. If you choose to deduplicate instead of rejecting, define the precedence explicitly—especially around Bcc.

If your system needs to pinpoint **both locations** of a duplicate address, map each key to its first-seen location; on collision, return an error referencing both field paths. Avoid logging full user email addresses in public error responses when they contain personal data.

### Where Should Recipient Count Limits Live?

Limits should be enforced **server-side** before calling SMTP, even if the UI already caps entries. Specific limits are business/infrastructure decisions and vary across:

- Single-recipient transactional emails.
- Alert emails to a small admin group.
- Batch emails dispatched via queues and workers.
- Personalized emails per subscriber.

The **`100`** limit in code is illustrative, not a default limit of Spring Mail or SMTP. Providers may enforce their own limits per account, message, day, or plan tier.

## 7. Sending Validated Data with MimeMessage

Once validated, pass the lists into **`MimeMessage`**:

~~~java
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import java.util.List;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {

    private final JavaMailSender mailSender;

    public NotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotification(
            List<String> to,
            List<String> cc,
            List<String> bcc
    ) throws MessagingException {

        RecipientPolicy.RecipientSet recipients =
                RecipientPolicy.check(to, cc, bcc);

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, "UTF-8");

        helper.setFrom("notifications@example.test");
        helper.setSubject("New notification");
        helper.setText("You have a new notification.", false);

        if (!recipients.to().isEmpty()) {
            message.setRecipients(
                    Message.RecipientType.TO,
                    recipients.to().toArray(InternetAddress[]::new)
            );
        }
        if (!recipients.cc().isEmpty()) {
            message.setRecipients(
                    Message.RecipientType.CC,
                    recipients.cc().toArray(InternetAddress[]::new)
            );
        }
        if (!recipients.bcc().isEmpty()) {
            message.setRecipients(
                    Message.RecipientType.BCC,
                    recipients.bcc().toArray(InternetAddress[]::new)
            );
        }

        mailSender.send(message);
    }
}
~~~

This code separates **input validation** from **sending**:

- **`RecipientPolicy.check(...)`** enforces emptiness, syntax, and duplicate rules before creating the email.
- **`message.setRecipients(...)`** assigns each group to its corresponding MIME recipient field.
- When **To** is empty yet **Bcc** has addresses, the code still builds a valid message targeting Bcc recipients.
- **`send(...)`** is never invoked when all three groups are empty.
- **`MailException`** during send and **`MessagingException`** during construction occur at different layers; callers should handle them appropriately.

Production applications also need SMTP configuration, authorized From addresses, error handling, and monitoring. The **`example.test`** addresses are sample data.

### Using SimpleMailMessage for Plain Text

**`SimpleMailMessage`** also provides **`setTo(...)`**, **`setCc(...)`**, and **`setBcc(...)`**. For simple plain-text emails, run your validation policy first and convert approved **`InternetAddress`** objects back to strings:

~~~java
import org.springframework.mail.SimpleMailMessage;

RecipientPolicy.RecipientSet recipients =
        RecipientPolicy.check(to, cc, bcc);

SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("notifications@example.test");
mail.setSubject("Notification");
mail.setText("Notification content.");

mail.setTo(
        recipients.to().stream()
                .map(InternetAddress::getAddress)
                .toArray(String[]::new)
);
mail.setCc(
        recipients.cc().stream()
                .map(InternetAddress::getAddress)
                .toArray(String[]::new)
);
mail.setBcc(
        recipients.bcc().stream()
                .map(InternetAddress::getAddress)
                .toArray(String[]::new)
);

mailSender.send(mail);
~~~

Here, **`SimpleMailMessage`** fits plain text. When complex MIME is needed (HTML, images, attachments, explicit charsets, and multipart), **`MimeMessageHelper`** is the better tool. Regardless of which API you use, **stopping invalid recipient lists before sending** remains the application's responsibility.

### Why Not Simply Call `helper.setTo(rawList)` and Let the Library Validate?

The mail library handles syntax and message construction, yet knows nothing about business rules such as:

- Requiring at least one recipient across To/Cc/Bcc.
- Capping each email at N recipients.
- Blocking the same mailbox from appearing in both To and Bcc.
- Sending only to verified, non-unsubscribed, or authorized users.
- Sending **one personalized message** per person instead of a shared broadcast.

Catching errors early lets the API return structured codes like **`RECIPIENT_LIST_EMPTY`**, **`INVALID_RECIPIENT`**, or **`DUPLICATE_RECIPIENT`** instead of parsing low-level SMTP or transport exceptions.

## 8. Using Bean Validation Within Its Proper Scope

In Spring MVC APIs, Bean Validation can check basic data shapes:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import java.util.List;

public record SendMailRequest(
        List<@NotBlank @Email String> to,
        List<@NotBlank @Email String> cc,
        List<@NotBlank @Email String> bcc
) {
}
~~~

When the controller enables validation, element-level **`@NotBlank`** and **`@Email`** constraints catch blank items or items failing the validator's check. However:

- **`@Email`** does not verify mailbox existence.
- **`@Email`** does not deduplicate within a list.
- **`@Email`** does not detect conflicts across To, Cc, and Bcc.
- When all lists are empty, no element violates **element-level** constraints.
- Bean Validation's **`@Email`** is an application validator, not a full replacement for RFC parsing or SMTP transport capabilities.

If your workflow allows **Bcc-only**, do not place **`@NotEmpty`** on **`to`** and accidentally reject valid requests. The rule "at least one address in To/Cc/Bcc" needs a **cross-field** constraint, such as a custom validator or service policy.

For multi-recipient APIs, modeling recipients as **arrays of individual mailboxes** makes errors easy to report by index:

~~~json
{
  "to": [
    "lan@example.test",
    "minh@example.test"
  ],
  "cc": [],
  "bcc": [
    "audit@example.test"
  ]
}
~~~

This also makes clear that a comma inside a single element does not implicitly create two recipients. If a product intentionally offers a CSV multi-address input box, parse it explicitly with a proper parser accounting for quotes and display names rather than calling **`split(",")`** naively.

## 9. Syntactically Valid Addresses Can Still Be Rejected by SMTP

Even after input validation, sending can fail at the SMTP server. Example:

~~~text
C: MAIL FROM:<notifications@example.test>
S: 250 Sender OK
C: RCPT TO:<lan@example.test>
S: 250 Recipient OK
C: RCPT TO:<unknown@recipient.test>
S: 550 5.1.1 User unknown
~~~

This is an illustrative session, not a universal transcript for every SMTP server. It shows that a server can accept one recipient while rejecting another.

Other scenarios:

| Observation | Careful Interpretation |
| --- | --- |
| Parser accepts the address | Syntax fits the parser's validation scope |
| SMTP returns **`5xx`** for RCPT TO | Recipient error reported as permanent in that response; enhanced status code gives detail |
| SMTP returns **`4xx`** for RCPT TO | Temporary failure/deferral; bounded retry may be considered per policy |
| SMTP accepts RCPT TO | Address accepted at that protocol step only |
| SMTP accepts entire DATA payload | Server accepted message at that hop; inbox delivery not yet guaranteed |
| Provider reports a bounce later | Update recipient/job status from provider data or DSN |

Code **`550`** does not always mean "mailbox does not exist"; it can reflect other policy rejections. Interpret it alongside enhanced status codes and reliable response details, and avoid exposing raw provider error strings directly to end users.

### Can Partial Delivery Succeed?

With multiple recipients on one message, outcomes can **vary per address**. How an SMTP transport behaves when some addresses are rejected depends on configuration and server behavior; some environments deliver to accepted recipients and report errors, while others abort the whole message.

Jakarta Mail exposes details via **`SendFailedException`** and categorizes **`invalid`**, **`valid sent`**, and **`valid unsent`** recipients when the transport provides them. Spring wraps mail-layer failures into **`MailException`** subclasses such as **`MailSendException`**, carrying underlying causes.

Applications should never infer that **one exception means nobody received the email**, or that **no exception means every destination mailbox received it**. When mailing multiple recipients, track status at sufficient granularity based on actual provider evidence.

### Be Careful When Retrying Recipient Lists

Suppose you send to Lan and Minh. SMTP accepts Lan, then the application encounters a connection error before learning Minh's result. Retrying the entire list immediately may send Lan a duplicate email.

Conversely, marking the entire batch succeeded just because one recipient was accepted may leave Minh without the message.

For workflows requiring tight control:

- Persist a **mail job ID**, message type, and selected recipient list.
- Distinguish states such as **`PENDING`**, **`SUBMITTED`**, **`TEMPORARY_FAILURE`**, **`PERMANENT_FAILURE`**, or provider-specific statuses.
- Mark **`DELIVERED`** only when backed by delivery evidence—not merely because **`send(...)`** returned.
- Design bounded retries with backoff and account for duplicate risk.
- When each recipient needs distinct content or tracking, create a separate message/job per person.

This is an application reliability and delivery-semantics decision, not an automatic feature of **`setTo(...)`**.

## 10. Database-Backed Lists and Batch Sending

Suppose a notification campaign loads these records:

~~~text
Subscriber 101 -> lan@example.test
Subscriber 102 -> minh@example.test
Subscriber 103 -> lan@example.test
Subscriber 104 -> (blank email)
Subscriber 105 -> invalid@@example.test
~~~

If sending targets **each subscriber account**, records 101 and 103 are two distinct **accounts** sharing one mailbox. Deduplicating by email address can break "one notification per account" semantics, especially when content holds account-specific codes or verification links. Conversely, if the goal is "one public newsletter per subscribed mailbox," deduplicating by address makes sense.

Therefore, define the **delivery unit**:

- **Per mailbox**: one email sent per unique address under a defined canonicalization rule.
- **Per account**: one email per user account, even if contact emails overlap.
- **Per business event**: one email per event, potentially sending multiple emails to the same mailbox at different times.
- **Distribution group**: one email to a group address; the group may expand into multiple mailboxes outside the application's direct visibility.

Your choice of deduplication key should reflect the business unit—not a knee-jerk "see two identical emails, delete one."

### Two Policies for Handling Invalid Records in a Batch

**All-or-nothing policy:** if any mandatory recipient is blank, violates duplicate rules, or is invalid, reject the entire batch before sending. This suits transactions requiring an exact recipient set, such as mandatory notices to all approvers.

**Per-recipient policy:** classify inputs first, enqueue valid recipients for sending, and isolate invalid records into a separate report showing succeeded count, skipped count, and reasons. This suits large subscription lists, though mandatory recipients in critical workflows must never be silently dropped.

Example batch result summary:

~~~text
Batch validation:
    received_count = 5
    accepted_count = 2
    duplicate_count = 1
    empty_count = 1
    malformed_count = 1

Batch sending:
    submitted_count = ...
    failed_count = ...
    pending_retry_count = ...
~~~

**Validation** metrics and **sending** metrics measure two different stages. **`accepted_count = 2`** means two recipients passed input policy—not that two emails reached their inboxes.

### Per-Recipient Sending Protects Status Tracking and Privacy

For emails containing personalized names, codes, or URLs, build **one message/job per recipient or event**. For example, Lan's password-reset email must never be combined with Minh's in a single message with multiple To/Cc/Bcc entries.

Sending individually:

- Simplifies per-recipient status tracking.
- Enforces per-recipient content authorization.
- Prevents leaking recipient lists across users.
- Allows retrying one recipient without repeating the entire batch.

The trade-off is higher job and submission volume; manage sending limits, rates, and queues accordingly. Never let volume convenience justify merging personalized content into one shared message.

## 11. Designing Clear API Responses

A mail-sending API should distinguish **input validation errors** from **transport errors**. Example:

| Scenario | Suggested API Outcome | Internal Status to Record |
| --- | --- | --- |
| To/Cc/Bcc all empty when business requires recipients | Return client validation error, typically **400 Bad Request** | **REJECTED_INPUT** |
| Invalid address syntax | Return element-position error with code **INVALID_RECIPIENT** | **REJECTED_INPUT** |
| Duplicate recipient across To and Bcc under strict policy | Return **DUPLICATE_RECIPIENT** or **CONFLICTING_RECIPIENT_GROUP** | **REJECTED_INPUT** |
| Valid request persisted for background processing | May return **202 Accepted** per API contract | **PENDING** |
| SMTP submission succeeded | Return or record application-level submission success | **SUBMITTED** |
| Temporary SMTP/provider failure | Record retryable error and next retry schedule | **RETRY_PENDING** |
| Provider reports permanent delivery failure | Record per-recipient failure status | **BOUNCED/FAILED** |

HTTP codes are design suggestions, not mandatory Spring Mail mappings. For synchronous APIs, responses depend on your contract and when the business action is considered complete. Once a job is durably persisted, **202 Accepted** indicates the request was accepted for processing—not that the recipient has read the email.

### Example Input Error Without Leaking Excess Data

~~~json
{
  "code": "INVALID_RECIPIENT",
  "field": "to[2]",
  "message": "Recipient address format is invalid."
}
~~~

Or for a cross-group conflict:

~~~json
{
  "code": "CONFLICTING_RECIPIENT_GROUP",
  "fields": ["to[0]", "bcc[1]"],
  "message": "A recipient appears in multiple groups."
}
~~~

In privacy-sensitive systems, returning **element positions** lets clients highlight the exact offending input without echoing full address lists or verbose provider messages.

### Do Not Distort Primary Business Outcomes When Email Is Secondary

Consider a "create order and send notification email" request. If the order commits successfully while SMTP fails, returning an "order creation failed" API error encourages users to place duplicate orders. Decouple **order creation outcome** from **email job status**, especially when mail sends asynchronously.

This also clarifies empty-recipient handling:

- If sending the email is a **mandatory business precondition**, reject the request before committing.
- If the email is an **optional notification**, complete the primary transaction and record "no recipients configured" on the notification status.

Make this an explicit product decision rather than letting an SMTP exception dictate whether the core operation succeeded.

## 12. Observing Errors While Protecting Recipient Data

To spot error trends, emit metrics per category:

| Metric or Event | Meaning |
| --- | --- |
| **recipient.validation.empty** | Count of requests missing recipients |
| **recipient.validation.invalid** | Count of items failing syntax or policy rules |
| **recipient.validation.duplicate** | Count of duplicate conflicts detected |
| **mail.submitted** | Count of messages successfully submitted to sending infrastructure |
| **mail.submit_failed** | Count of submission failures |
| **mail.bounced** | Count of undeliverable events reported by provider |
| **mail.retry_pending** | Count of jobs awaiting retry |

These are example metric names; adapt them to your observability stack. In logs, include **mailJobId**, email type, normalized error code, To/Cc/Bcc group, and item index. Store specific email addresses only when genuinely necessary and compliant with personal-data policies.

Guidelines:

- Never dump entire email bodies and full recipient lists into every log line.
- Avoid using raw email addresses as metric labels, which causes **high cardinality** and data exposure.
- Restrict displaying, logging, or surfacing Bcc lists in error messages to unauthorized users.
- Use **job ID**, **recipient ID**, or dedicated correlation keys to match provider events.
- Separate syntax failures from bounces: one is caught **before sending**, while the other occurs **after the system accepts the message**.

## 13. Practice Scenarios

### Scenario A — Bcc Only

~~~text
To  = []
Cc  = []
Bcc = ["audit@example.test"]
~~~

**Question:** is this an empty list?

**Answer:** no, because there is an actual recipient in Bcc. The application can send it if the message type and policy permit. Never copy Bcc into To just to make To non-empty.

### Scenario B — Nobody Left After Stripping Blank Items

~~~text
To  = [" ", ""]
Cc  = []
Bcc = []
~~~

**Question:** should you call `send(...)` with an empty array?

**Answer:** no. If policy rejects blank items, fail input validation immediately. If policy allows skipping blanks, zero recipients remain, so **skip with a recorded reason** or return a missing-recipient error per business contract. Never record the email as sent.

### Scenario C — Duplicate with Different Domain Casing

~~~text
To = ["lan@Example.Test", "lan@example.test"]
~~~

**Question:** can these be treated as duplicates?

**Answer:** under a policy that lowercases domains while preserving local-parts, both share the same key. You can reject or deduplicate per your documented rule.

### Scenario D — Different Casing in the Local-Part

~~~text
To = ["Lan@example.test", "lan@example.test"]
~~~

**Question:** should you unconditionally collapse them into one address?

**Answer:** not unconditionally. Under traditional protocols, case sensitivity of the local-part is decided by the receiving system. If your product defines its own account-identity rule, apply it; do not generalize across arbitrary external domains.

### Scenario E — Duplicate Between To and Bcc

~~~text
To  = ["lan@example.test"]
Bcc = ["lan@example.test"]
~~~

**Question:** why not simply merge into one entry?

**Answer:** To and Bcc carry different visibility semantics. Picking one arbitrarily can violate the sender's intent. The policy shown in this lesson **rejects the conflict** and asks the caller to reclassify.

### Scenario F — Parser Accepts, Yet SMTP Rejects

~~~text
To = ["unknown@recipient.test"]
~~~

**Question:** does `InternetAddress.validate()` succeeding mean the email will be delivered?

**Answer:** no. That is a syntax check, not proof the mailbox exists. The SMTP server or provider can reject at RCPT TO or accept first and bounce later.

### Scenario G — User Enters Two Addresses in One Field

~~~text
"lan@example.test, minh@example.test"
~~~

**Question:** is this one address or two?

**Answer:** it depends on the API contract. If each list item must be a bare mailbox, this is **invalid input**. If a UI provides a multi-address input box, parse it with a proper parser into two separate entries before running policy checks. Never assume every comma is a safe delimiter in all address syntaxes.

### Scenario H — Two Similar Emails from Two Separate Events

~~~text
Job 1001 -> lan@example.test -> EVENT_ORDER_CREATED
Job 1002 -> lan@example.test -> EVENT_ORDER_SHIPPED
~~~

**Question:** should the second job be dropped because the recipient appeared in the earlier job?

**Answer:** no. These are two distinct business events; per-message recipient deduplication must not suppress notifications for different events. To prevent **the same event from spawning duplicate jobs**, use an event-scoped idempotency key.

### Scenario I — Batch Succeeds for Some Recipients

~~~text
To = ["lan@example.test", "minh@example.test"]
SMTP provider confirms acceptance for Lan;
Minh's status is unknown due to connection drop.
~~~

**Question:** can you mark the whole batch failed and immediately retry everyone?

**Answer:** doing so risks sending Lan a duplicate email. Reconcile known outcomes, provider state, and retry rules; for critical workflows, manage separate jobs or per-recipient status tracking.

## 14. Practical Design Principles

A reliable email-sending flow in Spring Framework Mail can be structured as:

~~~text
1. Receive input
   -> To, Cc, Bcc alongside business context

2. Define policy
   -> require To, or at least one recipient overall?
   -> skip blank items or return an error?
   -> how to handle within-group and cross-group duplicates?

3. Validate before sending
   -> null, blank, control characters
   -> parse one mailbox per item
   -> cap recipient count
   -> check business rules and authorization

4. Normalize and deduplicate within proper scope
   -> never silently turn Bcc into To
   -> never guess provider alias rules
   -> never lose business event context

5. Build message
   -> JavaMailSender / MimeMessageHelper / SimpleMailMessage
   -> preserve To, Cc, Bcc semantics

6. Send and track
   -> SMTP submit can fail per recipient
   -> never equate submitted with delivered
   -> retry and manage state based on evidence
~~~

**Empty lists**, **duplicate lists**, and **invalid addresses** are three distinct failure modes: emptiness leaves no delivery target, duplicates create ambiguity around send counts or visibility, and invalidity can surface at syntax, policy, or SMTP delivery time. Separating these cases cleanly enables Spring Mail applications to reject bad inputs early, protect Bcc privacy, and report accurate delivery statuses.
