# Domain-Level SPF, DKIM, and DMARC

An email sent successfully through `JavaMailSender` is not guaranteed to be evaluated as valid by the receiving system. The SMTP relay may have accepted the message, but the destination server still needs to verify whether the sending IP is authorized by the domain, whether the content signature is valid, and whether the domain displayed in the `From` address matches the authenticated identities.

In **Spring Framework Mail**, `JavaMailSender` primarily builds and sends MIME messages. Meanwhile, **SPF, DKIM, and DMARC** are email authentication mechanisms **at the domain and sending-infrastructure level**: DNS records, envelope sender addresses, DKIM signing systems, SMTP provider configuration, and domain policies. They are closely tied to deliverability, yet they are not three properties you can simply toggle on in `application.yml` and be done.

This lesson explains how the three mechanisms work together, distinguishes the `From` address in the content from `MAIL FROM` in the SMTP session, explains **DMARC alignment** requirements, covers configuring a sending domain via Spring Mail and an SMTP provider, checking DNS/headers, deploying safely with multiple mail-sending systems, and real-world failure scenarios.

## 1. Three Protection Mechanisms Answering Three Different Questions

| Mechanism | Primary Question | Verification Data | Primarily Responsible Component |
|---|---|---|---|
| **SPF** — Sender Policy Framework | Is the IP of the sending SMTP server authorized by the envelope sender's domain? | Sending IP, `RFC5321.MailFrom` or `HELO/EHLO` domain, SPF TXT record | Domain DNS and SMTP infrastructure |
| **DKIM** — DomainKeys Identified Mail | Do the signed parts of the message carry a valid cryptographic signature attested by the signing domain? | `DKIM-Signature`, DNS public key under selector | Outbound MTA/email provider or DKIM signer |
| **DMARC** — Domain-based Message Authentication, Reporting & Conformance | Is the domain displayed in `From` authenticated via **aligned** SPF or DKIM, and how does the domain want receivers to handle failures? | `RFC5322.From`, SPF/DKIM results, `_dmarc` TXT record | DNS policy and receiving mail servers |

Summary:

- **SPF** lets a domain publish which systems are authorized to send using a given SMTP envelope identity.
- **DKIM** enables verifying a signature bound to a signing domain and a portion of the content/headers.
- **DMARC** ties SPF/DKIM results to the **domain the recipient sees in From**.

An email does not need **both SPF and DKIM to pass** to pass DMARC. The foundational requirement is that **at least one of the two mechanisms passes and has proper alignment with From**. However, properly deploying both SPF and DKIM generally improves authentication resilience during forwarding or across different sending routes.

### 1.1. Verification Flow Model

```text
Spring application
  |
  | MIME message:
  | From: notices@example.com
  | Subject: ...
  |
  v
Outbound SMTP relay/provider
  |                                DNS
  | MAIL FROM: bounce@bounces.example.com
  | IP: 192.0.2.25                  |
  | DKIM signs with d=example.com   |
  +---------------------------+----+
                              |
                              v
Receiving SMTP server
   |
   +--> SPF: Is IP authorized by bounces.example.com?
   |
   +--> DKIM: Does signature d=example.com validate?
   |
   +--> DMARC: Does either PASS + align with From example.com?
   |
   +--> Apply policy, spam filtering, and local rules
   |
   v
Delivery / spam / quarantine / reject
```

The IPs and domains in the example are illustrative data, not parameters of an actual provider.

## 2. Distinguishing Four Easily Confused Identities

A message can contain multiple addresses and domains. Confusing them makes SPF/DMARC configuration very error-prone.

| Component | Example | Meaning |
|---|---|---|
| **Header From** (`RFC5322.From`) | `notices@example.com` | Sender address displayed to the recipient; DMARC extracts the domain from here. |
| **Envelope sender** (`RFC5321.MailFrom`) | `bounce@bounces.example.com` | Address used in the SMTP `MAIL FROM` session and as the return path for many delivery failure notifications; SPF typically checks this domain. |
| **DKIM signing domain** (`d=`) | `example.com` | Domain taking responsibility for signing the message under DKIM. |
| **SMTP server hostname** | `smtp.provider.example` | Endpoint the application connects to for sending; not necessarily the domain in Header From. |

Example:

```text
From: Example Store <notices@example.com>
Reply-To: support@example.com

SMTP envelope:
MAIL FROM:<bounce@bounces.example.com>

DKIM-Signature: ... d=example.com; s=mail2026; ...
```

Explanation:
- Users see `notices@example.com`.
- SMTP uses `bounce@bounces.example.com` to handle certain types of delivery failures.
- The DKIM signer attests that the signature belongs to `example.com`.
- The provider may be another system such as `smtp.provider.example`.

**SPF does not directly check `From: notices@example.com`.** DMARC is what evaluates whether the SPF result is aligned with the `example.com` domain of From.

### 2.1. Is Return-Path the Same as From?

No. `Return-Path` is usually added by the destination MTA to a received message to record the envelope sender, for example:

```text
Return-Path: <bounce@bounces.example.com>
```

Do not manually set a `Return-Path` header and assume you have changed the SMTP envelope. To change the envelope sender, configure an appropriate SMTP mechanism, such as `mail.smtp.from` on Jakarta Mail's SMTP transport, or configure a custom bounce domain at the provider. The provider may rewrite the envelope sender itself for bounce/tracking management.

### 2.2. Does Reply-To Affect SPF or DMARC?

`Reply-To: support@example.com` controls the reply address as used by mail clients. It is **not an identifier used by SPF for verification** and does not determine the From domain checked by DMARC.

```java
helper.setFrom("notices@example.com");
helper.setReplyTo("support@example.com");
```

These two lines do not configure the envelope sender or DKIM signing domain on their own.

### 2.3. HELO/EHLO When the Envelope Sender Is Empty

In some system messages, especially delivery status notifications, SMTP uses `MAIL FROM:<>`. SPF can use an identifier based on `HELO/EHLO` in those cases according to SPF rules. Therefore, do not assume every SPF result originates from the Header From address or a specific mailbox.

## 3. SPF: Publishing Authorized Sending Infrastructure

SPF is typically published using a **DNS TXT record** on the domain used in the SMTP envelope.

For example, the domain `bounces.example.com` only accepts certain approved IPs and providers:

```dns
bounces.example.com. IN TXT "v=spf1 ip4:192.0.2.25 include:_spf.provider.example -all"
```

Meaning:
- `v=spf1`: SPF record.
- `ip4:192.0.2.25`: illustrative allowed IP address.
- `include:_spf.provider.example`: references the IP authorization mechanism per the illustrative provider's SPF policy.
- `-all`: remaining sources are not authorized according to the record.

`_spf.provider.example` is only a placeholder name for documentation; in real deployments, obtain the exact host/record published by your SMTP provider. Do not copy illustrative domains verbatim into real DNS.

### 3.1. Common Mechanisms

| Mechanism | Example | Role |
|---|---|---|
| `ip4` | `ip4:192.0.2.25` | Authorizes an IPv4 address or network. |
| `ip6` | `ip6:2001:db8::/32` | Authorizes an IPv6 address or network. |
| `include` | `include:_spf.provider.example` | Incorporates a provider's SPF policy per include rules. |
| `a` | `a:mail.example.com` | Matches IP against DNS A/AAAA records of the hostname. |
| `mx` | `mx:example.com` | Matches against the MX hosts and their addresses. |
| `exists` | `exists:check.example.com` | DNS existence-based mechanism, often used in complex setups. |
| `redirect` | `redirect=_spf.example.com` | Redirects policy evaluation under SPF conditions. |
| `all` | `-all`, `~all` | Specifies the default result for sources not previously matched. |

`include` does not mean mechanically copying the provider's TXT record into the same string; it has its own evaluation rules and can trigger DNS lookups. Only include providers that actually send with your envelope domain.

### 3.2. SPF Qualifiers

| Symbol | Result When Mechanism Matches | Common Meaning |
|---|---|---|
| `+` | Pass | Authorized; if no qualifier is written, the default is `+`. |
| `-` | Fail | Not authorized per policy. |
| `~` | Softfail | Domain believes the source is unauthorized but makes a softer assertion. |
| `?` | Neutral | Neither affirms authorization nor denial. |

Example:

```dns
example.com. IN TXT "v=spf1 include:_spf.provider.example ~all"
```

`~all` is not the same as `-all`. In deployment, the SPF policy should reflect the actual list of sending sources and the domain owner's confidence level. **SPF fail does not mean the receiver must reject the email**: the result also feeds into further checks, DMARC, receiver policies, and reputation.

### 3.3. Where Should the SPF Record Be Placed?

**Place SPF at the domain evaluated by SPF**, typically the domain of `RFC5321.MailFrom`.

Example:
- Header From: `billing@example.com`.
- MAIL FROM: `bounce@bounces.example.com`.

The SPF lookup will look for a record at `bounces.example.com` (per the evaluated identifier) and **does not automatically fall back to SPF on `example.com`**.

Adding SPF only at the apex `example.com` while forgetting the bounce subdomain can cause SPF checks on `bounces.example.com` to fail or have no policy. If the provider manages a custom return-path separately, follow their instructions on CNAME/TXT/MX for the bounce domain.

### 3.4. Only One SPF TXT Policy per Owner Name

Multiple TXT records can exist for different purposes (verification, DKIM, etc.), but **there should not be two separate records both starting with `v=spf1` at the same DNS owner name**.

Incorrect:

```dns
example.com. IN TXT "v=spf1 include:_spf.provider-a.example -all"
example.com. IN TXT "v=spf1 include:_spf.provider-b.example -all"
```

This can cause an SPF `permerror` due to multiple SPF records. If both providers send using the same envelope domain that evaluates that record, merge the policies appropriately:

```dns
example.com. IN TXT "v=spf1 include:_spf.provider-a.example include:_spf.provider-b.example -all"
```

However, do not merge blindly: check each provider's **actual envelope domain**, the DNS lookup count, and allowed IP sources. In some cases each provider uses its own bounce subdomain so they do not need to be in the same SPF record.

### 3.5. DNS Lookup Limit in SPF

SPF limits the number of mechanisms/modifiers requiring DNS lookups during evaluation, typically **a maximum of 10** for items such as `include`, `a`, `mx`, `ptr`, `exists`, and `redirect` under SPF rules. Includes can be nested and consume lookups at deeper levels.

Example of a multi-provider record:

```dns
example.com. IN TXT "v=spf1 include:_spf.a.example include:_spf.b.example include:_spf.c.example -all"
```

Although only three `include` directives are visible, each provider may in turn include multiple domains. Exceeding the limit can result in `permerror` and negate the benefits of SPF.

Notes:
- `ip4`/`ip6` do not generate DNS lookups like `include`.
- Count lookups across the evaluation process, not just keywords in a single record.
- Avoid using `ptr` unless truly necessary and understand its limitations.
- Remove sending sources that are no longer used.
- Do not "flatten" SPF into a static list of IPs if you cannot manage provider IP changes; that approach can quickly become stale.

### 3.6. SPF Does Not Verify Email Content

SPF checks authorization of the IP/SMTP identity. It **does not sign the subject, HTML body, attachments, or From header**. Therefore, DKIM and DMARC are needed for authentication at additional layers.

## 4. DKIM: Signing Messages with a Domain Identity

DKIM uses digital signatures. A system on the sending side holds a **private key** to sign selected headers and the message body according to the configured algorithm/canonicalization. The receiving system reads the **public key** published in the signing domain's DNS to verify.

An illustrative header:

```text
DKIM-Signature: v=1; a=rsa-sha256; c=relaxed/relaxed;
 d=example.com; s=mail2026;
 h=from:to:subject:date:mime-version;
 bh=BODY_HASH_PLACEHOLDER;
 b=SIGNATURE_PLACEHOLDER
```

Important fields:

| Parameter | Meaning |
|---|---|
| `v=1` | DKIM signature version. |
| `a=rsa-sha256` | Illustrative signature algorithm. |
| `d=example.com` | **Signing domain** — domain responsible for the signature. |
| `s=mail2026` | **Selector** — name used to locate the DNS public key. |
| `h=...` | List of signed header fields; `From` must be signed per DKIM. |
| `bh=...` | Hash of the body after canonicalization. |
| `b=...` | Cryptographic signature. |
| `c=relaxed/relaxed` | How headers/body are normalized before signing and verification. |

`bh` and `b` in the example are placeholders, not valid signatures. DKIM does not encrypt content so others cannot read it; it provides proof that the signed data has not been modified beyond what canonicalization permits and that the signature corresponds to domain `d=`.

### 4.1. DKIM Public Key Resides at the DNS Selector

Given:
- `d=example.com`;
- `s=mail2026`;

the receiver queries:

```text
mail2026._domainkey.example.com
```

Illustrative TXT record:

```dns
mail2026._domainkey.example.com. IN TXT "v=DKIM1; k=rsa; p=BASE64_PUBLIC_KEY_PLACEHOLDER"
```

`p=` is the public key formatted per DKIM record syntax; it is **not a private key**, with no PEM headers or arbitrary whitespace. The string above is a placeholder and not for real verification.

DNS providers may split a long TXT value into multiple quoted strings due to per-string length limits; resolvers concatenate strings of the same TXT record per DNS rules. Avoid accidentally creating multiple conflicting TXT policies at the same selector.

### 4.2. Who Actually Signs DKIM?

In a common Spring Mail architecture:

```text
Spring Boot / JavaMailSender
         |
         | raw MIME via SMTP
         v
Authorized outbound SMTP provider / MTA
         |
         | DKIM signing with domain key
         v
Receiving MX
         |
         | look up selector._domainkey.domain
         v
DKIM validation
```

`MimeMessageHelper` helps build text/HTML, attachments, CIDs, and headers, but it **does not configure DNS and does not sign DKIM by default just because JavaMailSender is used**.

Typically DKIM signing is set up at the SMTP provider or outbound MTA:
1. Verify that you own the domain.
2. The provider supplies selector/DNS records or key generation instructions.
3. Publish the public key/record in the right DNS zone.
4. The provider stores or manages the private key via its mechanism.
5. Enable signing messages with the right signing domain.
6. Verify an actually received email has `dkim=pass` and the expected `header.d`.

If the organization operates its own mail server, signing can be performed by a DKIM signer on the outbound MTA. Do not store the DKIM private key in source code or attach it to emails.

### 4.3. DKIM Selectors Enable Key Rotation

A domain can use multiple selectors:

```text
mail2026._domainkey.example.com
mail2027._domainkey.example.com
marketing1._domainkey.example.com
transactional1._domainkey.example.com
```

Each selector maps to a public key. This allows:
- separating keys across systems;
- deploying a new key before switching the signer;
- planned rollbacks;
- keeping the old public key available for an appropriate period so already-signed messages can still be verified;
- revoking a compromised key via process.

**Do not delete the old selector too early** if already-sent messages may still be re-verified by receivers or systems processing slowly. Retention period and revocation timing should follow the organization's security policy.

### 4.4. DKIM Does Not Mean Content Is Guaranteed Accurate or Safe

`dkim=pass` does not mean a message is not spam, contains no malware, or is not impersonating a brand if the signing domain is not the domain displayed in From. A spammer can validly sign DKIM using its own domain.

That is why DMARC needs to check **alignment between the signing domain and the From domain**.

### 4.5. What Causes DKIM to Fail?

Several causes:
- Wrong DNS public key or selector not yet published.
- Sender signed with a key that does not match the public key.
- Provider signed with the wrong `d=` domain.
- A downstream system modified the body or signed headers after the signature was created.
- Mail gateway added a footer, rewrote links, or altered MIME.
- DNS propagation delay or disabled record.
- Algorithm/key not supported by the receiver under its policy.

`relaxed` canonicalization tolerates certain whitespace/formatting changes, but **does not permit arbitrary content modification**. If an MTA modifies the body after signing, the signature can fail.

Place the DKIM signer **after controlled content transformation steps** when possible, or ensure downstream systems do not corrupt the signature.

## 5. DMARC: Authentication Tied to the Domain Recipients See

DMARC centers on the domain in the `RFC5322.From` header. It uses SPF and DKIM results, though it is not simply "SPF pass or DKIM pass" in all cases: the passing result must also be **aligned** with the From domain.

DMARC provides:
- a mechanism to determine whether an email passes for the From domain;
- the desired policy on failure;
- a mechanism to receive aggregate reports and, if supported by receivers, certain failure reports.

### 5.1. Publishing a DMARC TXT Record

For Header From domain `example.com`, start with:

```dns
_dmarc.example.com. IN TXT "v=DMARC1; p=none; rua=mailto:dmarc-reports@example.com; adkim=r; aspf=r"
```

Meaning:

| Tag | Role |
|---|---|
| `v=DMARC1` | DMARC record version. |
| `p=none` | Publishes a monitoring policy; does not ask receivers to quarantine/reject solely for DMARC failure. |
| `rua=mailto:...` | Address to receive aggregate reports if receivers send them. |
| `adkim=r` | DKIM relaxed alignment. |
| `aspf=r` | SPF relaxed alignment. |

`adkim=r` and `aspf=r` are typically defaults when omitted; writing them explicitly helps operators read the configuration. A DMARC policy is evaluated by **receiving systems**, not a command guaranteeing every receiver behaves identically.

### 5.2. Three Policy Levels

| Tag | Domain Owner's Intent for DMARC-Failing Email | Usage |
|---|---|---|
| `p=none` | Monitor and report; request no enforcement action under DMARC policy | Phase for observing sending sources. |
| `p=quarantine` | Request receivers treat cautiously, typically placing into spam/quarantine | Escalation step after controlling sending sources. |
| `p=reject` | Request receivers reject emails failing DMARC | Stronger protection against From-domain spoofing. |

`p=none` **does not guarantee emails land in the Inbox**; receivers still apply spam filters, malware scanners, and local policies. `p=reject` is likewise not an order executed identically by every receiver; the final decision depends on the receiving system, exceptions, and local policy.

### 5.3. DMARC Does Not Sign Emails on Its Own

Adding:

```dns
_dmarc.example.com. IN TXT "v=DMARC1; p=reject"
```

does not make SPF or DKIM pass on its own. It only publishes policy and requires authentication/alignment. If sending systems do not yet have aligned SPF/DKIM, jumping straight to `p=reject` can cause **the company's own legitimate emails** to be rejected.

Therefore, the rollout process must start by **inventorying all sending sources**, not just changing a TXT record.

## 6. DMARC Alignment: The Decisive Factor

Suppose the recipient sees:

```text
From: Example Store <notices@example.com>
```

The From domain is `example.com`. DMARC checks:

- **SPF alignment:** is the domain used for SPF, normally the `MAIL FROM` domain, aligned with `example.com`? And did SPF itself `pass`?
- **DKIM alignment:** is there at least one verified `pass` DKIM signature with `d=` aligned with `example.com`?

Only one branch needs to succeed:

```text
DMARC PASS
  =
    [SPF PASS AND SPF domain aligned with Header From]
  OR
    [DKIM PASS AND DKIM d= aligned with Header From]
```

If neither branch succeeds, DMARC fails.

### 6.1. Relaxed Alignment

In relaxed alignment (`aspf=r`, `adkim=r`), two domains can be considered aligned if they share the same **Organizational Domain** according to the applicable DMARC rules.

Common example:
- From domain: `example.com`.
- MAIL FROM domain: `bounces.example.com`.
- DKIM d=: `mail.example.com`.

With Organizational Domain `example.com`, both subdomains can align under relaxed mode.

Do not determine the Organizational Domain by simply taking the "last two labels" of a DNS name. Public suffixes such as `co.uk` break that approach. DMARC verification systems must rely on appropriate public suffix rules/data for deployment.

### 6.2. Strict Alignment

In strict alignment (`aspf=s` or `adkim=s`), the compared domain names must match exactly according to the corresponding rules.

Example:

```text
Header From domain: example.com

MAIL FROM domain: bounces.example.com
  -> SPF strict alignment: NO match.

DKIM d=example.com
  -> DKIM strict alignment: MATCH.

DKIM d=marketing.example.com
  -> DKIM strict alignment: NO match.
```

Even if SPF returns `pass` for `bounces.example.com`, it still **does not help DMARC pass via the strict SPF branch** when the From domain is `example.com`. If DKIM `d=example.com` passes, DMARC can still pass via DKIM.

### 6.3. Illustrative Decision Table

Assume Header From is always `notices@example.com` and DMARC uses relaxed alignment:

| SPF | MAIL FROM domain | DKIM | DKIM d= | DMARC |
|---|---|---|---|---|
| Pass | `bounces.example.com` | Fail | — | **Pass** via aligned SPF. |
| Fail | `bounces.example.com` | Pass | `example.com` | **Pass** via aligned DKIM. |
| Pass | `provider.other.example` | Pass | `provider.other.example` | **Fail** because neither domain is aligned. |
| Pass | `provider.other.example` | Pass | `example.com` | **Pass** via aligned DKIM. |
| Pass | `bounces.example.com` | Pass | `provider.other.example` | **Pass** via aligned SPF. |
| Fail | `bounces.example.com` | Fail | — | **Fail**. |
| Neutral | `bounces.example.com` | Pass | `example.com` | **Pass** via aligned DKIM. |

This table illustrates alignment logic; all pass/fail values are assumed to be actual verification results computed by the receiver.

### 6.4. Example: SPF Pass but DMARC Fail

```text
From: notices@example.com
MAIL FROM: bounce@provider-other.example
Authentication-Results:
  spf=pass smtp.mailfrom=provider-other.example;
  dkim=pass header.d=provider-other.example;
  dmarc=fail header.from=example.com
```

Both SPF and DKIM **pass** for the provider's domain, but neither domain aligns with `example.com`. This is a classic case when using an SMTP service without custom customer domain authentication configured.

Possible solutions:
- Configure a custom MAIL FROM/bounce domain under `example.com` for SPF alignment; or
- Configure DKIM signing domain `d=example.com`; or
- Do both per provider instructions.

Merely adding an SPF record at `example.com` while the provider still sends the envelope with `provider-other.example` **does not make SPF aligned**.

## 7. Domain/Subdomain Policies in DMARC

### 7.1. Organizations with Multiple Subdomains

Example:
- `example.com` for corporate email.
- `billing.example.com` for invoices.
- `news.example.com` for marketing.
- `alerts.example.com` for alerts.

Functional isolation can be designed via subdomains with separate senders and DKIM selectors. A DMARC policy can be published on each subdomain or applied via the Organizational Domain's policy mechanism where appropriate.

### 7.2. The sp Tag for Subdomains

Example:

```dns
_dmarc.example.com. IN TXT "v=DMARC1; p=reject; sp=quarantine; rua=mailto:dmarc-reports@example.com"
```

`p=reject` is the policy at the domain per applicable discovery rules, while `sp=quarantine` publishes the policy for subdomains per DMARC rules. A subdomain with its own DMARC record can have its own specific policy.

Do not assume an apex record always applies identically to deeply nested domains in every situation; DMARC discovery/policy has clear rules depending on the Organizational Domain. In deployment, test against each From domain in use.

### 7.3. Choosing Domains for Each Sending System

One separation pattern:

| System | Header From | MAIL FROM | DKIM d= |
|---|---|---|---|
| Transactional | `billing@example.com` | `bounce@bounces.example.com` | `example.com` |
| Marketing | `news@news.example.com` | `bounce@bounces.news.example.com` | `news.example.com` |
| Alerts | `alerts@alerts.example.com` | `bounce@bounces.alerts.example.com` | `alerts.example.com` |

These examples are designed so SPF/DKIM can align under the corresponding relaxed policy. If the organization requires strict alignment, adjust the exact domains and re-verify.

Splitting subdomains helps manage policies, logs, reputation, and access permissions, but **does not automatically produce SPF, DKIM, or DMARC passes**; each sending stream still must be configured properly.

## 8. SPF and DKIM in Spring Framework Mail: Where Does Responsibility Lie?

A Spring Mail application can determine:
- Header From/Reply-To;
- MIME text/HTML and attachments;
- SMTP host/port/authentication;
- SMTP envelope sender within what Jakarta Mail/the provider allows;
- custom headers/correlation IDs.

However, **the application does not publish DNS TXT records itself**, does not issue DKIM certificates, and does not make receivers trust the domain on its own.

A typical architecture:

```text
Spring Boot
  |
  | JavaMailSender builds message
  | From: notices@example.com
  v
SMTP provider / outbound MTA
  |
  +--> Applies envelope sender
  |     bounce@bounces.example.com
  |
  +--> Signs DKIM with
  |     d=example.com; s=mail2026
  |
  v
Receiving MTA
  |
  +--> SPF: DNS TXT at bounces.example.com
  +--> DKIM: DNS TXT at mail2026._domainkey.example.com
  +--> DMARC: DNS TXT at _dmarc.example.com
  |
  v
Authentication results + local filtering
```

To send using your own domain, you usually need to complete **domain verification/authentication in the SMTP provider's admin console** before putting the application into production.

## 9. Spring Boot Configuration Example Combined with Domain Authentication

Suppose the company owns `example.com`, has verified the domain with the SMTP provider, and configured the provider to sign DKIM with `d=example.com`.

```yaml
spring:
  mail:
    host: smtp.provider.example
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          ssl:
            checkserveridentity: true
          from: bounce@bounces.example.com
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
```

Notes:
- `smtp.provider.example` is an illustrative endpoint; use the real host supplied by the provider.
- `from: bounce@bounces.example.com` lies under `spring.mail.properties.mail.smtp.from`: that is Jakarta Mail transport's SMTP envelope sender property in this simple configuration.
- The provider may **override or disallow** custom envelope senders. Verify the actual message and the provider's custom return-path/bounce domain settings.
- TLS/hostname verification protects the hop from the application to the SMTP server, which is **different** from SPF/DKIM/DMARC.
- Passwords come from a secret store/environment variables; never commit real credentials.
- If multiple senders/tenants use different envelope domains, a single global property may not fit; design sender profiles or a provider-supported per-message mechanism.

### 9.1. JavaMailSender Setting From and Reply-To

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderConfirmationMailer {

    private final JavaMailSender mailSender;

    public OrderConfirmationMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(
            String recipient,
            String orderId,
            String orderUrl) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        // Header From: the centerpiece domain of DMARC.
        helper.setFrom("notices@example.com");
        helper.setReplyTo("support@example.com");
        helper.setTo(recipient);
        helper.setSubject("Order confirmation " + orderId);

        String plain = """
            Order %s has been confirmed.
            View details: %s
            """.formatted(orderId, orderUrl);

        String html = """
            <html><body>
              <p>Your order has been confirmed.</p>
              <p><a href="%s">View order details</a></p>
            </body></html>
            """.formatted(orderUrl);

        // For untrusted data, context-appropriate HTML escaping is required,
        // and the URL must be validated against application policy.
        helper.setText(plain, html);

        mailSender.send(message);
    }
}
```

This example focuses on the From/domain relationship. In production, use a template engine with proper HTML escaping; do not concatenate arbitrary user data into URL attributes.

In the example:
- Spring Mail sets Header From to `notices@example.com`.
- Jakarta Mail/SMTP provider uses the envelope sender per actual configuration and policy.
- The provider/MTA signs DKIM if configured for the domain.
- The receiver verifies SPF/DKIM/DMARC against the DNS records of the relevant domains.

**There are no `helper.enableSpf()`, `helper.enableDkim()`, or `helper.enableDmarc()` methods in `MimeMessageHelper`.** These mechanisms are not turned on merely by a Spring helper method.

### 9.2. The Return-Path Header Is Not an SPF Switch

Conceptually wrong:

```java
message.setHeader("Return-Path", "<bounce@bounces.example.com>");
```

Manually writing this header does not guarantee the SMTP session uses the right `MAIL FROM`. The Return-Path address is typically generated by the receiving system from the envelope sender. For SPF to check the right domain, control the envelope sender at the **SMTP transport/provider** and publish SPF on the domain actually used.

### 9.3. SMTP AUTH Does Not Mean SPF/DKIM/DMARC Pass

Username/password only proves the application's account is accepted by the SMTP provider. It **does not authenticate authority to use the Header From domain** on the receiving side.

An SMTP account may log in successfully yet:
- the provider rejects unverified From addresses;
- the provider signs DKIM using its own domain;
- MAIL FROM belongs to the provider's domain;
- SPF passes but DMARC fails due to lack of alignment.

Domain authentication must be verified separately.

## 10. Example Set of DNS Records for a Sending Domain

Suppose:
- Header From is `notices@example.com`.
- The SMTP provider uses bounce domain `bounces.example.com`.
- Provider DKIM signing uses `d=example.com` and selector `mail2026`.
- The company begins DMARC monitoring.

Illustrative record set:

```dns
; SPF at the exact MAIL FROM domain:
bounces.example.com. IN TXT "v=spf1 include:_spf.provider.example -all"

; DKIM public key:
mail2026._domainkey.example.com. IN TXT "v=DKIM1; k=rsa; p=PUBLIC_KEY_BASE64_PLACEHOLDER"

; DMARC policy for Header From domain:
_dmarc.example.com. IN TXT "v=DMARC1; p=none; rua=mailto:dmarc-reports@example.com; adkim=r; aspf=r"
```

Placeholders **must not be used directly** in production DNS. A provider may require a CNAME for DKIM instead of a self-published TXT public key. In that case, follow the exact record provided by the provider and verify resolution to a valid public key.

### 10.1. DNS Propagation and TTL

When changing records:
- account for TTL and recursive resolver caches;
- sending a test immediately after saving DNS may not reflect the new configuration;
- different resolvers may see changes at different times;
- changing policy from `p=none` to `p=reject` requires waiting long enough and inspecting data.

Do not change multiple SPF/DKIM/DMARC records at once and then conclude failure from a single test send. Record the record version, timestamp, and sending source.

### 10.2. DKIM Can Use CNAME

Some providers require:

```dns
mail2026._domainkey.example.com. IN CNAME mail2026.example-com._domainkey.provider.example.
```

This is a hypothetical pattern illustrating syntax, not a real host. The provider manages the public key in its own DNS zone; when the receiver queries it, DNS can resolve to the TXT DKIM key.

Do not invent a CNAME target yourself. Only use records provided by the provider and do not create conflicting TXT and CNAME records at the same owner name.

## 11. Phased DMARC Rollout Process

Setting `p=reject` before knowing who is sending mail on behalf of the domain can break legitimate flows such as:
- confirmation emails from Spring Boot applications;
- CRM/marketing automation;
- customer support teams;
- invoicing systems;
- helpdesk/ticketing;
- survey tools;
- HR systems;
- third-party notification services.

A sensible roadmap:

### Phase 1 — Inventory Sending Sources

List:
- all SMTP providers and outbound MTAs;
- From domains/subdomains;
- envelope MAIL FROM/return-path domains;
- DKIM d=/selectors;
- provider IPs or SPF includes;
- DMARC report recipient addresses;
- the owner responsible for each source.

Clearly separate transactional, marketing, and internal emails if they use different providers/policies.

### Phase 2 — Configure SPF and DKIM

For each source:
1. Verify the domain at the provider.
2. Set up SPF for the actual envelope domain.
3. Set up an aligned DKIM signing domain.
4. Confirm the public key/selector in DNS.
5. Send a test email.
6. Read `Authentication-Results` from a trusted receiving system.
7. Cross-check SPF/DKIM identities against Header From.

Prioritize **at least one reliable aligned authentication path**, ideally having both SPF and DKIM aligned where the architecture permits.

### Phase 3 — Enable DMARC p=none and Collect Reports

```dns
_dmarc.example.com. IN TXT "v=DMARC1; p=none; rua=mailto:dmarc-reports@example.com"
```

Observe:
- email volume by IP/provider;
- SPF pass/fail rates;
- DKIM pass/fail rates;
- DMARC pass/fail rates;
- legitimate sending sources not yet configured;
- spoofing sources and misconfigured records.

DMARC aggregate reports can arrive with delay and not every receiver sends them. Do not rely on a single email sample to conclude the entire domain is ready.

### Phase 4 — Remediate Failing Legitimate Sources

Examples:
- CRM signs DKIM with vendor domain: enable custom DKIM domain if supported.
- Transactional sender uses an external bounce domain: set up custom return-path or aligned DKIM.
- An outbound node is missing its SPF IP: update approved sources.
- DKIM key does not resolve: fix selector record.
- Mailing list modifies body: evaluate handling per list/From policy and forwarding characteristics.

Do not stay on `p=none` forever just because unresolved errors exist. Yet also do not raise enforcement while many legitimate sources remain unauthenticated.

### Phase 5 — Gradually Move to Quarantine and Reject

Once legitimate sources have alignment:
- consider `p=quarantine` for appropriate domains/groups;
- monitor false positives, bounces, and inbox placement;
- handle justified exceptions;
- upgrade to `p=reject` when ready;
- if needed, use `sp` to control subdomain policy per DMARC rules.

You can roll out per domain/subdomain or in stages, depending on risk and operational capacity. Tags like `pct` have been used to roll out policy by percentage in DMARC deployments, though support levels and semantics may vary by standard/receiver; do not rely on it as a guaranteed rollout tool without verifying actual systems.

## 12. DMARC Reporting: rua, ruf, and Privacy

### 12.1. Aggregate Reports with rua

Example:

```dns
_dmarc.example.com. IN TXT "v=DMARC1; p=none; rua=mailto:dmarc-reports@example.com"
```

`rua` specifies where to send aggregate reports, which typically contain statistics by:
- source IP;
- message count;
- SPF result;
- DKIM result;
- DMARC disposition;
- Header From / policy domain;
- related identities and reporting organization.

Reports are usually in XML format and may be compressed. A mailbox receiving high-volume reports should integrate a parser/dashboard and proper retention, rather than opening files manually one by one.

### 12.2. Failure Reports with ruf

Some DMARC configurations specify `ruf=mailto:...` to request failure/forensic reports, but **do not assume receivers will send this report type**. Many receivers restrict or omit them due to privacy concerns. Failure reports may contain sensitive metadata or excerpts of content.

If used, verify security policies, access permissions, retention, and actual report delivery capability.

### 12.3. Report Addresses on External Domains

If `rua` sends reports to a domain **with a different organizational domain** than the domain publishing DMARC, there is an external reporting destination authorization mechanism per DMARC rules. Do not just change `rua` to an external address and assume reports will arrive.

Conceptual example:

```text
DMARC policy domain: example.com
Aggregate report address: dmarc@reports.external.example
```

The external report-receiving domain may need to publish a corresponding authorization verification record following the DMARC external-reporting pattern provided by the report analytics service. Follow that service's DNS instructions exactly; without authorization, receivers may withhold reports.

### 12.4. Reports Are Not Complete Audit Logs

DMARC reports do not cover every email and do not replace SMTP/outbox logs. They help illuminate authentication posture at the domain level; to trace a specific message you still need message keys, provider message IDs, SMTP logs, and delivery events.

## 13. How to Verify DNS Records

The commands below are **examples for learners to practice in authorized environments**, not results of already-executed DNS checks.

### 13.1. On Linux/macOS with dig

```bash
# SPF of the envelope domain:
dig TXT bounces.example.com

# DKIM of selector mail2026:
dig TXT mail2026._domainkey.example.com

# DMARC of the From domain:
dig TXT _dmarc.example.com
```

You can use `+short` for concise output:

```bash
dig +short TXT bounces.example.com
dig +short TXT mail2026._domainkey.example.com
dig +short TXT _dmarc.example.com
```

Do not conclude a mechanism passes merely because a DNS record exists. SPF also depends on the actual sending IP; DKIM also depends on the actual MIME signature; DMARC also depends on From and alignment.

### 13.2. On Windows with nslookup/PowerShell

```powershell
nslookup -type=TXT bounces.example.com
nslookup -type=TXT mail2026._domainkey.example.com
nslookup -type=TXT _dmarc.example.com
```

Or PowerShell:

```powershell
Resolve-DnsName bounces.example.com -Type TXT
Resolve-DnsName mail2026._domainkey.example.com -Type TXT
Resolve-DnsName _dmarc.example.com -Type TXT
```

### 13.3. Checking by Exact DNS Owner Name

Questions to ask:
1. Which domain does Header From use?
2. Which domain does the provider's actual Envelope MAIL FROM use?
3. Which `d=` and `s=` does the DKIM signature carry?
4. Is SPF located at the right envelope domain?
5. Does the DKIM TXT/CNAME at `selector._domainkey.d-domain` resolve properly?
6. Is the DMARC TXT at the right `_dmarc.from-domain` or applicable domain per discovery?
7. Are there duplicate SPF/DMARC records, excessive DNS lookups, or truncated public keys?

Checking TXT at `example.com` is not enough if emails use `bounces.example.com` or `news.example.com`.

## 14. Verifying Results in Actually Received Emails

After sending a test message to an authorized test mailbox/recipient, inspect the **raw message source** and the `Authentication-Results` section added by a trusted receiving system.

Illustrative example:

```text
From: Example Store <notices@example.com>
Return-Path: <bounce@bounces.example.com>
DKIM-Signature: v=1; a=rsa-sha256; d=example.com; s=mail2026; ...

Authentication-Results: mx.recipient.example;
    spf=pass smtp.mailfrom=bounces.example.com;
    dkim=pass header.d=example.com header.s=mail2026;
    dmarc=pass header.from=example.com
```

Interpretation:
- SPF passed with envelope domain `bounces.example.com`.
- DKIM passed with signing domain `example.com`.
- From domain is `example.com`.
- There is aligned authentication, so DMARC passes.

**Security note:** A sender may try to inject a forged `Authentication-Results` header into MIME. When reading, know which header was generated by trusted receiving infrastructure, and do not blindly trust every line named `Authentication-Results`.

### 14.1. Authentication-Results Can Show Alignment Failure

```text
Authentication-Results: mx.recipient.example;
    spf=pass smtp.mailfrom=provider-other.example;
    dkim=pass header.d=provider-other.example;
    dmarc=fail header.from=example.com
```

The problem is not that SPF/DKIM failed. The problem is that **no passing result is aligned with From**. Check custom DKIM signing domain or custom MAIL FROM settings at the provider.

### 14.2. Headers Must Be Checked After Passing Through the Provider

Do not inspect only `MimeMessage` inside the application before `send`:
- The DKIM signer typically resides at the provider and signs **after** Spring builds the MIME.
- The envelope sender may be rewritten by the provider.
- The receiving MTA is where SPF/DKIM/DMARC are evaluated using the IP and DNS at receipt time.

Inspecting raw mail in a receiving mailbox gives a view much closer to real deliverability than unit tests verifying only that `mailSender.send(...)` was called.

## 15. Sending from Multiple Providers Using One Domain

Suppose a company has:
- Spring Boot sending transactional emails via Provider A.
- A marketing platform sending campaigns via Provider B.
- A helpdesk sending notifications via Provider C.

Implementation approaches:

### 15.1. SPF Matched to Each Provider's MAIL FROM

If each provider uses a different custom bounce domain:

```text
Provider A -> bounce.tx.example.com
Provider B -> bounce.news.example.com
Provider C -> bounce.support.example.com
```

Each bounce domain needs SPF/provider routing configured via supported mechanisms. You do not necessarily merge all IPs into SPF at the `example.com` apex, because receivers may not evaluate the apex when envelopes use the subdomains above.

### 15.2. Per-Provider DKIM Selectors

```text
tx1._domainkey.example.com       -> Provider A
news1._domainkey.example.com     -> Provider B
support1._domainkey.example.com  -> Provider C
```

Each provider has its own selector and key material, while signing domain `d=example.com` can be shared if the providers support it and the company has verified domain ownership.

A provider may require signing with a subdomain or specific CNAME structure. Confirm alignment for the actual From domain.

### 15.3. Separating From Subdomains to Reduce Operational Conflicts

You can use:
- `billing@example.com` for transactional;
- `news@news.example.com` for marketing;
- `help@support.example.com` for support.

Each stream can have its own DMARC policy, DKIM selector, bounce domain, suppression/feedback handling, and monitoring. This design helps isolate errors and reputation by function, though it does not automatically make emails "delivered."

### 15.4. Do Not Leave Old Providers in SPF Forever

When retiring a provider:
- confirm no sending flows still depend on it;
- check outbox/queues have no pending items;
- remove unnecessary includes/IPs from SPF on the appropriate domain;
- revoke signing keys/selectors per plan;
- audit domain verification permissions in the provider account.

Leaving old records indefinitely increases abuse surface and complicates SPF lookups.

## 16. Forwarding, Mailing Lists, and Limitations of SPF/DKIM

### 16.1. Forwarding Causes SPF to Fail

Suppose mail is sent:

```text
Provider A -> mailbox1@example.net -> forwarding service -> mailbox2@example.org
```

Upon arrival at mailbox2, the connecting IP may be the forwarding service's IP rather than an IP authorized by the original envelope domain. If the forwarder keeps the old envelope sender, SPF at the destination can fail.

A forwarder may use **SRS — Sender Rewriting Scheme** to rewrite the envelope sender for the forwarding path. However, the SPF result after rewriting may align with the forwarder's domain instead of the original Header From; in that case, **aligned DKIM from the original sender** is crucial for DMARC.

### 16.2. DKIM Can Help Mail Survive Forwarding

If forwarding does not modify the parts signed by DKIM, the original signature can still pass. Thus, deploying aligned DKIM is often helpful when SPF is affected by forwarding.

However, DKIM can fail if a forwarder/list manager:
- appends a footer to the body;
- alters the subject;
- rewrites link tracking;
- converts MIME structure;
- modifies signed headers.

### 16.3. Mailing Lists Can Make DMARC Harder to Pass

Mailing lists sometimes keep the author's Header From while altering content and sending from the list's IP. Outcomes can be:
- SPF passes for the list domain but is not aligned with the author's From domain;
- the author's DKIM fails because the list modified the body;
- DMARC fails if no aligned mechanism still passes.

Some lists rewrite From or adjust the sending flow. Handling requires weighing recipient experience, mailing list conventions, and security; turning off `p=reject` for the entire domain just because one list flow is poorly designed is not recommended.

### 16.4. What Is ARC?

**ARC — Authenticated Received Chain** can help intermediary systems communicate authentication history when email is forwarded/modified. However, ARC **does not simply turn `dmarc=fail` into `dmarc=pass`**. Receivers may use ARC as a signal in their own policies; trusting an ARC chain depends on the receiver's evaluation.

Do not treat ARC as a reason to skip SPF, DKIM, or DMARC alignment on the originating sending system.

## 17. Deliverability Is More Than SPF, DKIM, and DMARC

These three mechanisms authenticate domains/identities, yet **they do not guarantee Inbox placement**.

Other influencing factors:
- IP/domain reputation;
- traffic frequency and consistency;
- complaint, bounce, and spam trap rates;
- engagement history and how much recipients expect the content;
- opt-in/unsubscribe lists;
- recipient list quality;
- message content and linked URLs;
- PTR/rDNS and SMTP `HELO/EHLO` consistency per provider requirements;
- TLS, rate limits, and receiving MTA policies;
- mailbox state or suppression policies.

An email with all three results `pass` can still be sorted into spam due to content, reputation, or unwanted recipients.

### 17.1. Separating Authentication Failure from Delivery Failure

| Status | Meaning |
|---|---|
| `spf=fail` | SPF authorization failed for the evaluated identifier. |
| `dkim=fail` | Checked DKIM signature did not pass. |
| `dmarc=fail` | No SPF/DKIM pass aligned with From. |
| SMTP `250 accepted` | SMTP relay accepted submission; does not mean it landed in the Inbox. |
| Provider `delivered` | Typically means destination mail server accepted it; not proof the user opened it. |
| `bounced` | Provider/MTA reported undeliverable. |
| `spam` / `quarantine` | Receiver/client classified the message per its own policy. |

Do not try to "fix deliverability" merely by changing DMARC `p=reject` to `p=none` if the real issue is reputation or missing unsubscribe.

### 17.2. Operational Data to Monitor

Observe:
- SPF/DKIM/DMARC pass rates by From domain and provider;
- mismatches between Header From, envelope sender, and DKIM d=;
- report volume from unfamiliar IPs;
- SPF permerror/temperror;
- DKIM failures due to selector, DNS, or body modification;
- bounces, complaints, and suppressions;
- SMTP submission failures and rate limiting;
- email volume sent from each domain/subdomain.

Use message keys/attempt IDs to look up a specific email, and DMARC aggregate reporting to analyze **authentication posture at the domain level**.

## 18. Common Errors and How to Resolve Them

| Symptom | Common Cause | Resolution |
|---|---|---|
| SPF pass but DMARC fail | Envelope MAIL FROM belongs to a domain outside From; DKIM not aligned | Configure custom MAIL FROM or aligned DKIM. |
| DKIM pass but DMARC fail | Signer's `d=` is another provider's domain | Enable custom/aligned DKIM domain. |
| SPF `permerror` | Two SPF records or too many DNS lookups | Merge into one record at the right owner name; reduce lookups. |
| SPF record at apex but SPF still fails | MAIL FROM uses a bounce subdomain | Publish/authorize SPF on the domain actually evaluated. |
| SPF passes in dev, fails in production | Different IPs/relays | Inventory sender IPs and provider config per environment. |
| DKIM `selector not found` | DNS selector does not exist yet or wrong d=/s= | Check `s._domainkey.d` and TTL. |
| DKIM fails after adding footer | Message modified after DKIM signing | Sign after transformation or stop modifying signed parts. |
| DKIM fails after rotation | Old selector deleted too early or key mismatch | Keep overlap; verify key versions. |
| DMARC fails only on forwarded mail | SPF did not survive forwarding, DKIM no longer passes | Improve DKIM; examine SRS/ARC/list behavior. |
| p=reject causes legitimate mail to be rejected | Senders still lack aligned SPF/DKIM | Return to source inventory, remediate, and roll out carefully. |
| Not receiving DMARC aggregate reports | Receivers do not send, wrong rua, missing external authorization | Check rua, mailbox, policy, and external domain requirements. |
| SPF/DKIM/DMARC all pass yet goes to spam | Reputation, content, complaints, or receiver policy | Investigate deliverability beyond authentication. |
| Spring SMTP AUTH succeeds but DKIM fails | SMTP login does not control DKIM signing | Check provider domain verification and signer. |
| Return-Path header set manually but SPF unchanged | Header does not control SMTP envelope | Configure MAIL FROM/bounce domain at transport/provider. |
| Only unit-testing MimeMessage so DKIM is unseen | Provider signs after receiving MIME | Send test via real route to a test mailbox and inspect raw headers. |

## 19. Domain-Level Deployment Checklist

### 19.1. Before Configuration

- [ ] Confirm domains/subdomains are under the organization's control.
- [ ] List all sending systems and owners.
- [ ] Identify Header From for each stream.
- [ ] Identify actual MAIL FROM/return-path domains.
- [ ] Identify DKIM signing d=/selectors for each provider.
- [ ] Check how the provider supports custom domain authentication and bounce domains.
- [ ] Protect SMTP credentials, DKIM private keys, and DNS write permissions.

### 19.2. When Publishing DNS

- [ ] SPF at the right owner name, one valid SPF policy per name.
- [ ] Within the SPF DNS lookup limit.
- [ ] DKIM TXT/CNAME matching the provider's exact selector/domain.
- [ ] DMARC TXT at the right policy domain.
- [ ] Verify `p`, `sp`, `rua`, and alignment mode.
- [ ] If using an external report address, complete required authorization.
- [ ] Monitor TTL and keep a change log.
- [ ] Never expose DKIM private keys.

### 19.3. Before Upgrading to p=reject

- [ ] Send tests from every legitimate sending source.
- [ ] Cross-check SPF `smtp.mailfrom` and DKIM `header.d` against Header From.
- [ ] Confirm DMARC passes on trusted receivers.
- [ ] Review aggregate reports sufficiently to spot missed sending sources.
- [ ] Test critical forwarding/list flows.
- [ ] Have an owner, runbook, rollback plan, and bounce monitoring.
- [ ] Do not rely on a single test email.

## 20. Practice Exercises

### Exercise 1 — Distinguishing Identities

Given:

```text
From: billing@example.com
Reply-To: help@example.com
MAIL FROM:<bounce@bounces.example.com>
DKIM-Signature: ... d=example.com; s=tx1 ...
```

Identify the domain SPF checks, the domain DKIM uses, and the domain at the center of DMARC. Explain why Reply-To does not participate in alignment.

### Exercise 2 — SPF at the Bounce Subdomain

An SMTP provider sends using `bounce@bounces.example.com`, but the admin only created SPF on `example.com`. Identify the owner name that needs checking and how to verify it using `dig` or `Resolve-DnsName`.

### Exercise 3 — Two SPF TXT Records

A domain has two `v=spf1` records, one for marketing and one for transactional. Explain the `permerror` risk, propose an appropriate merged policy or separated MAIL FROM subdomains, and check the lookup budget.

### Exercise 4 — DMARC Relaxed Versus Strict

The From domain is `example.com`. SPF passes for `bounce.example.com` and DKIM passes with `d=mail.example.com`. Determine DMARC when `aspf=r/adkim=r`, and then when both switch to `s`.

### Exercise 5 — SPF Pass, DKIM Pass, Yet DMARC Fail

An email has `From: alerts@example.com`, while both SPF and DKIM pass using domain `vendor.other.example`. Explain why DMARC fails and design a custom DKIM signing domain.

### Exercise 6 — Spring Boot Sender

Write an SMTP STARTTLS 587 configuration with hostname verification and envelope sender `bounce@bounces.example.com`; use `helper.setFrom("notices@example.com")`. Identify what Spring controls and what must be configured in DNS/provider.

### Exercise 7 — DKIM Key Rotation

Provider A currently signs with selector `old1`. Design the steps to publish selector `new1`, switch signing, maintain overlap, and then retire the old key; note the risk of deleting the old TXT too early.

### Exercise 8 — Forwarding

A message passes SPF on first receipt, then gets forwarded so SPF fails at the final mailbox. If aligned DKIM d= still passes, can DMARC pass? Explain what happens when forwarding modifies the body.

### Exercise 9 — Analyzing Authentication-Results

Given the results:

```text
spf=pass smtp.mailfrom=outbound.provider.example
dkim=pass header.d=example.com
dmarc=pass header.from=example.com
```

Identify which mechanism enables DMARC to pass, even though SPF is not aligned.

### Exercise 10 — DMARC Rollout

An organization has three sending systems: Spring Boot, CRM, and helpdesk. Plan `p=none`, source inventory, alignment fixes, report monitoring, and transitioning to `quarantine` and `reject` without breaking legitimate email.

### Exercise 11 — DKIM and MIME Modification

A gateway appends a footer after the provider has signed DKIM. Explain why `bh=`/the signature may no longer pass and recommend where signing should occur.

### Exercise 12 — All Three Mechanisms Pass Yet Email Goes to Spam

Identify at least five deliverability factors other than authentication and propose metrics to monitor to find the root cause.

## 21. Summary

**Domain-level SPF, DKIM, and DMARC** are not three flags that can be switched on entirely inside Spring Mail. They are a coordination across **DNS owner names, SMTP envelopes, outbound signing infrastructure, Header From, and receiver policies**.

Remember:

1. **SPF** authenticates the sending IP for the domain evaluated from the SMTP envelope (`MAIL FROM`; sometimes HELO), not directly Header From.
2. **DKIM** verifies a signature with `d=` and the public key under `s._domainkey.d`. Spring `MimeMessageHelper` does not sign DKIM itself; the signer is usually at the SMTP provider/MTA.
3. **DMARC** ties results to Header From: **aligned SPF pass or aligned DKIM pass** yields a DMARC pass.
4. **Passing SPF/DKIM without alignment can still fail DMARC**. Therefore, inspect `smtp.mailfrom`, `header.d`, and `header.from`.
5. Deploy DNS in the right places: SPF on the envelope domain, DKIM selector on the signing domain, DMARC policy on the From domain.
6. Start DMARC with **source inventory and `p=none`**, using reports to fix issues before advancing to `quarantine` and `reject`.
7. Verify with DNS tools and **Authentication-Results from trusted receivers**, not only `JavaMailSender.send(...)` outcomes.
8. SPF/DKIM/DMARC form the authentication foundation, yet **do not guarantee Inbox placement**; reputation, bounces, complaints, content, and recipient policies still govern deliverability.

When domain identities are properly configured and continuously monitored, a Spring Mail system can send messages with a more trustworthy identity, reduce the risk of Header From domain spoofing, and help operations teams diagnose authentication failures systematically.
