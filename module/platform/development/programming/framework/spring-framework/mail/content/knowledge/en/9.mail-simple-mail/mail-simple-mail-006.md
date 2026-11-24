# Distinguishing `setTo` from `addTo` in Spring Framework Mail

When sending email from a Spring application, a message may need one recipient, a fixed set of recipients, or a list that is built up gradually by the business logic. The two method names `setTo` and `addTo` can easily make programmers think they always appear on the same class and differ very little. In reality, there are **two things to distinguish**:

1. **`SimpleMailMessage` has `setTo(...)` but no `addTo(...)`.** This is Spring's object for simple text messages; to send to multiple people, pass all the addresses into `setTo(...)`.
2. **`MimeMessageHelper` has both `setTo(...)` and `addTo(...)`.** `setTo(...)` **sets/replaces** the list of `To` recipients, while `addTo(...)` **adds** one `To` recipient to the existing list.

If you call `setTo(...)` after calls to `addTo(...)`, the `To` addresses added earlier may be replaced. Conversely, if you use `addTo(...)` multiple times, the `To` list accumulates. Understanding this difference helps avoid sending to too few people, sending duplicates, or putting too many addresses into one email by mistake.

This lesson places the two APIs in the context of **Simple mail** in Spring Framework Mail, covering both how to send plain text with `SimpleMailMessage` and how to create a text-only MIME message with `JavaMailSender`.

## 1. First: what kind of recipient is `To`?

An email usually has three groups of recipients:

| Group | Typical header | Meaning for the recipient |
| --- | --- | --- |
| **To** | `To:` | Primary recipients, usually displayed in the recipient list |
| **Cc** | `Cc:` | People sent a copy, usually also displayed |
| **Bcc** | `Bcc:` | Blind carbon copy recipients; Bcc addresses are usually not disclosed in the copy sent to others |

Example:

```text
From: notifications@example.org
To: alice@example.net, bob@example.net
Cc: manager@example.org
Subject: Maintenance notice
```

Here, Alice and Bob are both in the **To** group. `setTo` and `addTo` do not automatically move recipients to Cc or Bcc. Those groups have their own APIs such as `setCc`, `addCc`, `setBcc`, and `addBcc` when using `MimeMessageHelper`.

**Note about SMTP:** the `To` header is part of the email content, while SMTP uses the `RCPT TO` envelope addresses to deliver the message. Spring/Jakarta Mail usually builds the list of sending recipients from the message's To/Cc/Bcc groups. You should not concatenate a `To: ...` header string yourself to replace the recipient API.

## 2. Two different classes: `SimpleMailMessage` and `MimeMessageHelper`

Spring Framework Mail has several ways to create a message. For this lesson, you need to identify the right kind of object before choosing a method.

### 2.1. `SimpleMailMessage` — a simple text message

`SimpleMailMessage` belongs to the package:

```java
import org.springframework.mail.SimpleMailMessage;
```

This class holds the common fields: `from`, `replyTo`, `to`, `cc`, `bcc`, `sentDate`, `subject`, and `text`. `To` is represented as a list of string addresses.

Common ways to call it:

```java
SimpleMailMessage mail = new SimpleMailMessage();

mail.setTo("alice@example.net");
mail.setTo("alice@example.net", "bob@example.net");

String[] currentTo = mail.getTo();
```

**There is no `mail.addTo(...)` method on `SimpleMailMessage`.** If you write:

```java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setTo("alice@example.net");
mail.addTo("bob@example.net");  // Does not compile: SimpleMailMessage has no addTo
```

the compiler will report that no suitable method was found. This error comes from **using the wrong API**, not from Spring not having SMTP configured.

### 2.2. `MimeMessageHelper` — a tool for building `MimeMessage`

`MimeMessageHelper` belongs to the package:

```java
import org.springframework.mail.javamail.MimeMessageHelper;
```

The helper operates on a `jakarta.mail.internet.MimeMessage`, supporting plain text, HTML, multipart, attachments, and many utility methods for addresses:

```java
helper.setTo("alice@example.net");
helper.addTo("bob@example.net");
```

Here, both calls are valid:

- `setTo("alice@example.net")`: sets the `To` recipient list to Alice.
- `addTo("bob@example.net")`: adds Bob to the existing `To` list.

**You do not need HTML or file attachments to be allowed to use `MimeMessageHelper`.** A MIME message can still contain only plain text. When you want to add recipients step by step, the helper is the convenient choice.

### 2.3. API comparison table

| Capability | `SimpleMailMessage` | `MimeMessageHelper` |
| --- | --- | --- |
| Assign one `To` address | `setTo(String)` | `setTo(String)` |
| Assign multiple `To` addresses at once | `setTo(String...)` | `setTo(String...)` |
| Add `To` addresses one by one with `addTo` | **Not supported** | **Supported** |
| Read the `To` list | `getTo()` | Can be read through the `MimeMessage` managed by the helper |
| Create plain text | `setText(String)` | `setText(String, false)` |
| Create HTML | Not the purpose of the class | `setText(String, true)` |
| File attachments and multipart | Not directly supported | `addAttachment(...)`, the multipart constructors |
| Send via `JavaMailSender` | `mailSender.send(simpleMail)` | `mailSender.send(mimeMessage)` |

The difference lies in the **object type**, not in the type of SMTP port or login identity.

## 3. `setTo` means "set the list"

With both `SimpleMailMessage` and `MimeMessageHelper`, `setTo` sets the set of `To` addresses to the values passed in. Each time you call `setTo` again on the same message, the previous `To` list is **replaced** by the new list.

Example on `SimpleMailMessage`:

```java
SimpleMailMessage mail = new SimpleMailMessage();

mail.setTo("alice@example.net");
mail.setTo("bob@example.net");

mail.setFrom("notifications@example.org");
mail.setSubject("Notification");
mail.setText("Plain text content.");
```

After two `setTo` calls, the final `To` list contains only:

```text
bob@example.net
```

**Alice is no longer a `To` recipient of this message.** This differs from the interpretation that "each `setTo` adds one person".

### 3.1. To have multiple recipients, pass multiple addresses in one call

```java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setTo(
        "alice@example.net",
        "bob@example.net",
        "carol@example.net"
);
```

Logical result:

```text
To:
  alice@example.net
  bob@example.net
  carol@example.net
```

`setTo(String...)` takes a **varargs**. Therefore, all of the following express a `To` list:

```java
mail.setTo("alice@example.net");

mail.setTo("alice@example.net", "bob@example.net");

String[] recipients = {
        "alice@example.net",
        "bob@example.net"
};
mail.setTo(recipients);
```

In Java, `String...` lets you pass multiple `String` arguments or a `String[]` array. There is no need to assemble one string of many emails separated by commas just to use the array overload.

### 3.2. `setTo` does not replace `Cc` or `Bcc`

Example:

```java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setTo("alice@example.net");
mail.setCc("manager@example.org");
mail.setBcc("audit@example.org");

mail.setTo("bob@example.net");
```

The final lists:

```text
To:  bob@example.net
Cc:  manager@example.org
Bcc: audit@example.org
```

`setTo` only updates the **To group** and does not delete Cc/Bcc. Similarly, `setCc` sets the Cc list and `setBcc` sets the Bcc list.

## 4. `addTo` means "add to the existing list"

`MimeMessageHelper.addTo(...)` adds one `To` address to the addresses already on the `MimeMessage`. This is an **accumulating** operation, useful when each business step identifies one more recipient.

Example:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

helper.setFrom("notifications@example.org");
helper.setTo("alice@example.net");
helper.addTo("bob@example.net");
helper.addTo("carol@example.net");
helper.setSubject("Notification");
helper.setText("Plain text content.", false);

mailSender.send(message);
```

The `To` list at send time contains Alice, Bob, and Carol.

### 4.1. Do you need to call `setTo` before `addTo`?

Not required if the message has no `To` yet:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

helper.addTo("alice@example.net");
helper.addTo("bob@example.net");
```

The logical result is still two `To` recipients. However, when you have a clear input list, calling `setTo(recipients)` once is usually easier to understand.

### 4.2. `addTo` after `setTo`

```java
helper.setTo(
        "alice@example.net",
        "bob@example.net"
);
helper.addTo("carol@example.net");
```

Result:

```text
To: alice@example.net, bob@example.net, carol@example.net
```

### 4.3. `setTo` after `addTo`

```java
helper.addTo("alice@example.net");
helper.addTo("bob@example.net");
helper.setTo("carol@example.net");
```

Result:

```text
To: carol@example.net
```

The two addresses added earlier are **no longer in the To group** because the new `setTo` call resets the list.

**The call order directly affects the final send list.** This is the most important difference when the two methods are used together.

## 5. State table: what happens when you call them multiple times?

Suppose you use a new `MimeMessageHelper` object with no recipients yet:

| Order | Method called | `To` list after the operation |
| --- | --- | --- |
| 1 | `setTo("alice@example.net")` | Alice |
| 2 | `addTo("bob@example.net")` | Alice, Bob |
| 3 | `addTo("carol@example.net")` | Alice, Bob, Carol |
| 4 | `setTo("david@example.net")` | David |
| 5 | `addTo("erin@example.net")` | David, Erin |

You can picture it as:

```text
To = []
 |
 | setTo(Alice)
 v
To = [Alice]
 |
 | addTo(Bob)
 v
To = [Alice, Bob]
 |
 | addTo(Carol)
 v
To = [Alice, Bob, Carol]
 |
 | setTo(David)
 v
To = [David]
 |
 | addTo(Erin)
 v
To = [David, Erin]
```

At the moment `send(...)` is called, the library uses the message state **after the content and recipient operations have completed**. Therefore, a `setTo` that accidentally occurs at the end of the preparation process can wipe out the addresses previously added with `addTo`.

## 6. The underlying API: Jakarta Mail sets and adds recipients

`MimeMessageHelper` is a Spring utility class built on Jakarta Mail's `MimeMessage`. At the Jakarta Mail layer there is also an equivalent distinction between **set** and **add** for recipients:

```java
import jakarta.mail.Message;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

MimeMessage message = mailSender.createMimeMessage();

message.setRecipients(
        Message.RecipientType.TO,
        InternetAddress.parse("alice@example.net,bob@example.net")
);

message.addRecipient(
        Message.RecipientType.TO,
        new InternetAddress("carol@example.net")
);
```

General idea:

- `setRecipients(RecipientType.TO, ...)` sets the list for one recipient group.
- `addRecipient(RecipientType.TO, ...)` adds one address to that group.
- `addRecipients(RecipientType.TO, ...)` adds a group of addresses.
- `Message.RecipientType.TO` differs from `Message.RecipientType.CC` and `Message.RecipientType.BCC`.

In ordinary Spring application code, `MimeMessageHelper.setTo` and `addTo` make the operations more readable and support overloads using strings/display names, while also using the library's address handling mechanism.

**There is no need to work directly with `MimeMessage.setRecipients` just to add an ordinary recipient** if the helper already meets the requirement. Mixing both the helper and low-level Jakarta Mail code in the same sending path can make the final state hard to trace.

## 7. Complete example: sending Simple mail with `SimpleMailMessage`

A common case is sending a plain text notification to a fixed list, or a list that has been computed before the email is created.

### 7.1. Configure sending over SMTP in Spring Boot

With Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

Example `application.yml` using SMTP submission on port 587:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    from: ${MAIL_FROM_ADDRESS}
```

This is an example for a server that supports SMTP AUTH and STARTTLS on port 587. The port, TLS, and authentication method must follow the real provider. Do not put real passwords in the source code; the environment variable values are supplied by the deployment system.

### 7.2. A service with a single `setTo`

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class SimpleNotificationService {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public SimpleNotificationService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress
    ) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendAnnouncement(List<String> recipients) {
        if (recipients == null || recipients.isEmpty()) {
            throw new IllegalArgumentException("Recipients are required");
        }

        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom(fromAddress);
        mail.setTo(recipients.toArray(new String[0]));
        mail.setSubject("System notification");
        mail.setText("The system will undergo maintenance at the end of the week.");

        mailSender.send(mail);
    }
}
```

The key point is:

```java
mail.setTo(recipients.toArray(new String[0]));
```

The application gathers the recipient list first, converts it to `String[]`, and calls `setTo` **once**. There is no need for `addTo`. In a real system, `recipients` should be addresses that have been checked against business rules; merely checking that the list is non-empty is not enough to ensure that every address is valid or allowed to be sent to.

### 7.3. If the list is built up from multiple sources

Suppose you need to send to the requester and the people in charge:

```java
import java.util.ArrayList;
import java.util.List;

List<String> recipients = new ArrayList<>();
recipients.add("requester@example.net");
recipients.add("owner@example.net");

if (notifyBackupOwner) {
    recipients.add("backup@example.net");
}

SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("notifications@example.org");
mail.setTo(recipients.toArray(new String[0]));
mail.setSubject("Request updated");
mail.setText("There is a new change for you to follow.");

mailSender.send(mail);
```

In this illustrative snippet, the variable `notifyBackupOwner` has already been determined by the business logic. The key is to **accumulate the list in a collection**, and then call `setTo` once at the end.

### 7.4. Should you "add" recipients by reading `getTo` and then calling `setTo` again?

This technique can be done:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

SimpleMailMessage mail = new SimpleMailMessage();
mail.setTo("alice@example.net");

List<String> current = new ArrayList<>();
if (mail.getTo() != null) {
    current.addAll(Arrays.asList(mail.getTo()));
}
current.add("bob@example.net");

mail.setTo(current.toArray(new String[0]));
```

But this is an operation that **rebuilds the whole list yourself**, not an official `addTo` method of `SimpleMailMessage`. If multiple layers of code read/modify the message in an order that is hard to control, this approach is easily overwritten. In a normal design, you should keep one collection of the recipient list at the business layer and call `setTo` once the final decision has been made.

## 8. Complete example: plain text with `MimeMessageHelper.addTo`

When the business flow needs to add recipients step by step or wants to take advantage of MIME capabilities, you can use `MimeMessageHelper` even if the body is only text:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class MimeNotificationService {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public MimeNotificationService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress
    ) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendUpdate(
            String requester,
            String owner,
            String backupOwner
    ) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                "UTF-8"
        );

        helper.setFrom(fromAddress);
        helper.setTo(requester);
        helper.addTo(owner);

        if (backupOwner != null && !backupOwner.isBlank()) {
            helper.addTo(backupOwner);
        }

        helper.setSubject("Request update");
        helper.setText(
                "There is a new update for the request handling team.",
                false
        );

        mailSender.send(message);
    }
}
```

Here:

- `helper.setTo(requester)` determines the initial primary recipient.
- `helper.addTo(owner)` adds the person in charge.
- `helper.addTo(backupOwner)` is only performed when there is a backup owner.
- `setText(..., false)` creates plain text content.
- `JavaMailSender.send(message)` sends the message with the final To list.

For a real application, you need a policy for handling duplicate or invalid `requester`/`owner`/`backupOwner`. `addTo` only helps to **add an address**; it does not mean it filters duplicates on its own or checks whether the recipient has the right to view the email content.

### 8.1. Using `addTo` to add a display name

`MimeMessageHelper` has overloads that support an address and a **personal name**:

```java
helper.setTo("alice@example.net");
helper.addTo("bob@example.net", "Support Team");
```

In this case, the display name can be encoded in the right charset by the library and appears in the mail client in a form roughly like:

```text
To: alice@example.net, Support Team <bob@example.net>
```

This is the **presentation of the recipient's identity** and does not change the routing address `bob@example.net`. The overloads that take `jakarta.mail.internet.InternetAddress` can also be used when you need to control the address object at a lower level.

## 9. When to choose `setTo` or `addTo`?

| Situation | Recommended API | Why |
| --- | --- | --- |
| Send a SimpleMailMessage to one person | `mail.setTo(address)` | A simple API, enough for the need |
| Send a SimpleMailMessage to several known people | `mail.setTo(addresses)` | There is no `addTo`; set the entire list |
| Add recipients from multiple sources before creating the email | Gather a `List<String>` then `setTo(list.toArray(...))` | One place decides the final list |
| Create a MIME message with a known To list | `helper.setTo(addresses)` | Clearly sets the initial recipient set |
| Create a MIME message, then need to add one person | `helper.addTo(address)` | Does not overwrite those already there |
| Need to completely replace the To list of a MIME message | `helper.setTo(newAddresses)` | Deliberately replaces the old data |
| Need to add Cc/Bcc, not To | `addCc`/`addBcc` or `setCc`/`setBcc` | Keeps the recipient group's meaning correct |
| Need to send separately to each person | Create a **separate message** for each person | Each message has its own recipient, content, and access rights |

**An easy-to-remember design rule:** when you know the **final list**, use `setTo`; when you need to **append** to the `To` list already on a `MimeMessageHelper`, use `addTo`.

## 10. Be careful about call order across code layers

Mistakes are easy when a message is built through multiple services or helper functions.

Example:

```java
void fillCommonRecipients(MimeMessageHelper helper)
        throws MessagingException {
    helper.setTo("primary@example.net");
    helper.addTo("observer@example.net");
}

void fillSpecificRecipient(MimeMessageHelper helper)
        throws MessagingException {
    helper.setTo("case-owner@example.net");
}
```

If the program calls:

```java
fillCommonRecipients(helper);
fillSpecificRecipient(helper);
```

`case-owner@example.net` will replace the To group set in the first step. The intention of "adding the case owner" was not carried out.

If `fillSpecificRecipient` only needs to add a recipient, it must use:

```java
void addSpecificRecipient(MimeMessageHelper helper)
        throws MessagingException {
    helper.addTo("case-owner@example.net");
}
```

Another clearer design is to **gather all recipients first**, normalize them according to business policy, and call `setTo` exactly once in the email-building layer.

### Why is it error-prone when many layers modify the recipient?

Because the order of operations becomes part of the semantics:

```text
commonRecipients()   -> setTo(Alice), addTo(Bob)
caseRecipients()     -> setTo(Carol)
auditRecipients()    -> addTo(David)

Final list: Carol, David
```

If a developer only reads the content of `commonRecipients()` and assumes Alice and Bob are still present, the email will be sent to too few people. You should clearly specify which layer **owns the final To list** and avoid having multiple decorators call `setTo` on their own.

## 11. Does `addTo` prevent duplicate addresses on its own?

You should not assume so. `addTo` is an operation that **adds a recipient**, not an API that manages a unique set according to email rules. If you add the same address multiple times:

```java
helper.setTo("alice@example.net");
helper.addTo("alice@example.net");
```

the message may carry duplicate To entries. How the server or transport handles a duplicate list may vary by implementation; do not rely on it to prevent repeated sends.

If the business requires each address to appear only once in the same list, you can **deduplicate before creating the message**:

```java
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.Set;

Set<String> recipients = new LinkedHashSet<>(
        Arrays.asList(
                "alice@example.net",
                "bob@example.net",
                "alice@example.net"
        )
);

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");
helper.setTo(recipients.toArray(new String[0]));
```

`LinkedHashSet` preserves insertion order and removes strings that are equal under the `String.equals` rule. It is **not** a complete email address normalizer: strings that differ in upper/lower case, display name, or address syntax may need additional rules.

If the application puts the same address in To, Cc, and Bcc, deduplicating within To alone does not handle the overlap among the three groups. You should clearly define a recipient priority policy when consolidating the groups.

### Sending one message to many people differs from sending many separate messages

```text
One message:
  To: Alice, Bob, Carol
  Subject: Common update

Three independent messages:
  Message 1 -> To: Alice
  Message 2 -> To: Bob
  Message 3 -> To: Carol
```

The two approaches differ:

- One message with multiple `To` addresses usually exposes the `To` list to the people who receive the message.
- Separate messages allow customizing names, links, or send status per person.
- Retry/recording of delivery errors per recipient may differ between the two models.

Do not use `addTo` with hundreds of recipients if the business needs **each email to be private and personalized**. In that case, you should create a separate message for each person or use a separate bulk sending mechanism with an appropriate policy.

## 12. Use `Cc` and `Bcc` for their proper purpose

When you want someone to be "kept informed" rather than become a primary recipient, use Cc:

```java
helper.setTo("customer@example.net");
helper.addCc("account-manager@example.org");
```

When you need to send a blind copy, use Bcc:

```java
helper.setTo("customer@example.net");
helper.addBcc("audit@example.org");
```

With `SimpleMailMessage`, the equivalent is **setting the list**:

```java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setTo("customer@example.net");
mail.setCc("account-manager@example.org");
mail.setBcc("audit@example.org");
```

In mail sent to a customer, `audit@example.org` should not appear in the `To`/`Cc` headers distributed to other recipients; this is the purpose of Bcc. However, the Bcc feature alone is not a complete data protection mechanism and does not replace recipient control at the business layer.

**Do not call `addTo` just because you want to "add a silent follower"**: adding to To may make their address visible. Choose To/Cc/Bcc according to the proper information and privacy purpose.

## 13. Check addresses and receiving rights before sending

Both `setTo` and `addTo` take addresses to create the message. They are **not** APIs that confirm the mailbox actually exists or that the person has the right to receive business information.

Situations that need management:

- **Syntactically wrong addresses:** `alice@@example.net` may cause an error when parsing/preparing the message.
- **Empty or `null` addresses:** need to be handled from the input layer and the policy requiring a recipient.
- **Accounts that opted out of notifications:** need to be removed from the recipient set if the business requires.
- **Recipients without permission to view the data:** must be checked before being placed in To/Cc/Bcc.
- **Too-large lists:** the SMTP provider may limit the number of `RCPT TO`, the message size, or the sending rate.
- **Duplicate addresses:** need to be handled according to application policy before creating the message.
- **User-supplied addresses:** avoid putting untrusted data into raw headers; use Spring/Jakarta Mail's address API.

With `MimeMessageHelper`, an address parsing error may show up as a `MessagingException` or a specific Jakarta Mail exception depending on how it is called. With `SimpleMailMessage`, some problems are only detected when the sender converts the message into the sending format. An exception may occur **before SMTP accepts the message**, but the absence of an exception also does not prove the recipient has opened the email.

### Do you need to concatenate addresses separated by commas yourself?

No, when you already have a list of addresses as `String[]` or `List<String>`. For example:

```java
String[] addresses = {
        "alice@example.net",
        "bob@example.net"
};

helper.setTo(addresses);
```

This is a clear way to express **two separate addresses**. For addresses with display names or complex syntax, concatenating strings yourself and then splitting by comma yourself is error-prone. Use the right overload or an appropriate `InternetAddress`.

## 14. Common misunderstandings

| Symptom / thought | Problem | How to handle |
| --- | --- | --- |
| "`SimpleMailMessage` has `addTo`" | This class only has `setTo` for the To group | Gather the list and call `setTo` |
| "Calling `setTo` twice gives two recipients" | The later call overwrites the To list | Call once with multiple addresses or use `addTo` on the helper |
| "`addTo` and `setTo` are interchangeable" | One adds, one replaces | Choose according to the recipient state you want |
| "`addTo` automatically removes duplicates" | It is not a unique-list management function | Filter/normalize according to business rules |
| "`addTo` also adds Cc" | `addTo` only handles `To` | Use `addCc` or `setCc` |
| "To get Bcc, use `addTo` and hide it in HTML" | To may be visible to other recipients | Use the appropriate Bcc API |
| "Only HTML uses `MimeMessageHelper`" | The helper can also send plain text | `helper.setText(text, false)` |
| "To reach many people, sending one message is equivalent to sending separately" | The To list is shared, hard to personalize | Create separate messages when privacy is needed |
| "`setTo` has confirmed the receiving address exists" | The API only places the recipient into the message | Handle bounce/delivery in the email system |
| "SMTP success means everyone has read the message" | Submission status differs from delivery/read | Track status independently if the business needs it |

### 14.1. Wrong because `setTo` is called in a loop

```java
for (String recipient : recipients) {
    helper.setTo(recipient); // Wrong if you want to send the same message to everyone
}
```

After the loop, `To` usually contains only the **last element**, because each iteration of `setTo` replaces the list.

Fix it in one of two ways:

```java
// Approach 1: Assign the whole list at once.
helper.setTo(recipients.toArray(new String[0]));
```

```java
// Approach 2: Add each address on the MimeMessageHelper.
for (String recipient : recipients) {
    helper.addTo(recipient);
}
```

If `recipients` may be empty or contain invalid values, you need to handle that before the loop. For `SimpleMailMessage`, **there is only the first approach**, i.e. gather the list and call `setTo`.

### 14.2. Wrong because `To` is reset after adding

```java
helper.setTo("alice@example.net");
helper.addTo("bob@example.net");

// A piece of shared code that runs at the end:
helper.setTo("system@example.org");
```

The final result no longer has Alice and Bob in the To group. If `system@example.org` only needs to receive a copy, add it to Cc/Bcc according to the proper purpose, or use `addTo` if you really need to add a To recipient. Better, determine all recipients before building the message.

### 14.3. Wrong because sending multiple separate messages while still accumulating into the same message

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message);

for (String recipient : recipients) {
    helper.addTo(recipient);
    mailSender.send(message);
}
```

This flow does not create "an independent message for each person". The `To` list grows incrementally on the **same message**, so later sends have more recipients than earlier ones.

If the requirement is **one email per person**, create a new message in each iteration:

```java
for (String recipient : recipients) {
    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

    helper.setFrom("notifications@example.org");
    helper.setTo(recipient);
    helper.setSubject("Personal notification");
    helper.setText("Content just for you.", false);

    mailSender.send(message);
}
```

A real sending design also needs rate limiting, error handling, and storing business status. This example only clarifies the lifetime scope of the message object.

## 15. A maintainable design model

Instead of letting multiple components modify recipients one after another on a shared message, you can split it into two stages:

```text
Business event
       |
       v
Compute the To/Cc/Bcc lists
  - check receiving rights
  - deduplicate per policy
  - distinguish To, Cc, Bcc
       |
       v
Create the message
  - SimpleMailMessage.setTo(allTo)
        or
  - MimeMessageHelper.setTo(allTo)
       |
       v
Create the content, Subject, From
       |
       v
JavaMailSender.send(...)
       |
       v
SMTP submission / mail server
```

If a process truly needs to add recipients **while building the MIME message**, `addTo` expresses the intent to append clearly. When the whole list has already been determined, a single `setTo` makes it easier for a code reader to verify the result.

### Suggested method naming convention

A service that uses the functions:

```java
List<String> determinePrimaryRecipients(...);
List<String> determineCopyRecipients(...);
List<String> determineBlindCopyRecipients(...);
```

can determine the lists at the business layer; the mail-building class only receives the results and calls:

```java
helper.setTo(primary.toArray(new String[0]));
helper.setCc(copy.toArray(new String[0]));
helper.setBcc(blindCopy.toArray(new String[0]));
```

The variables `primary`, `copy`, and `blindCopy` in the example represent lists that have been prepared. This organization avoids the confusion when a helper method thinks it is adding recipients but actually calls `setTo` and wipes out the old list.

## 16. Self-check questions

**Question 1.** With `SimpleMailMessage`, how do you send to Alice and Bob?

> Call `mail.setTo("alice@example.net", "bob@example.net")` or pass a `String[]` of two addresses. `SimpleMailMessage` has no `addTo`.

**Question 2.** On `MimeMessageHelper`, who does the following snippet send to?

```java
helper.setTo("alice@example.net");
helper.addTo("bob@example.net");
```

> Two people in To: Alice and Bob.

**Question 3.** And the following snippet?

```java
helper.addTo("alice@example.net");
helper.setTo("bob@example.net");
```

> Only Bob remains in To; `setTo` replaced the old list.

**Question 4.** If you only want to add a recipient who receives a visible copy, which method must you use?

> With `MimeMessageHelper`, use `addCc(...)`; with `SimpleMailMessage`, use `setCc(...)` to set the Cc list.

**Question 5.** Can you use `MimeMessageHelper.addTo` when the message is only text, with no HTML and no attachment?

> Yes. `MimeMessageHelper` supports plain text through `setText(text, false)`. Choosing the helper depends on the need to manipulate the message, and does not require HTML.

**Question 6.** Why is calling `addTo` multiple times not a way to guarantee "one email per person"?

> Because `addTo` adds to the **same MIME message**. To send an independent message to each person, you need to create a new message for each person or use a bulk sending mechanism with an equivalent handling contract.

## 17. Key takeaways

| What to remember | `setTo` | `addTo` |
| --- | --- | --- |
| Meaning | Sets/replaces the `To` list | Adds an address to the `To` list |
| In `SimpleMailMessage`? | **Yes** | **No** |
| In `MimeMessageHelper`? | **Yes** | **Yes** |
| Called multiple times | The later call replaces the earlier list | The calls add recipients |
| Does it change Cc/Bcc? | No, only the To group | No, only the To group |
| When to use? | You know the final recipient list | You need to add each person to a MIME message |

With ordinary **Simple mail**, the most direct approach is to prepare a `String[]`/`List<String>` and call `SimpleMailMessage.setTo(...)` once. When using `MimeMessageHelper`, remember: **`setTo` = reset; `addTo` = append**. Choosing the right method, the right class, and the right To/Cc/Bcc group helps the email reach the right people, avoids overwriting the list, and reduces the risk of unintentionally exposing recipients.
