# Ràng buộc mục đích, ngữ cảnh và thời hạn theo giao thức khi tích hợp chữ ký EdDSA

> **Java 15 và các JDK hiện đại:** JEP 339 đưa chữ ký số EdDSA (Ed25519/Ed448) vào Java. `java.security.Signature` xác minh **dãy byte được ký** bằng một public key, nhưng không tự xác minh thông điệp dành cho nghiệp vụ nào, cho ai, tại tenant/tài nguyên nào, có còn hiệu lực hay đã bị phát lại. Những yêu cầu đó phải được **thiết kế và kiểm tra ở tầng giao thức**. Bài này tập trung vào điều kiện chấp nhận chữ ký an toàn, không dựa vào API legacy hay preview.

## 1. Vì sao chữ ký mật mã đúng vẫn có thể bị sử dụng sai?

Ví dụ một hệ thống ký chuỗi `approve=true` để chấp thuận hóa đơn. Một hệ thống khác cũng dùng đúng chuỗi đó để cấp quyền người dùng. Nếu cả hai chỉ chạy Ed25519 `verify()` với cùng khóa được chấp nhận, chữ ký tạo hợp pháp cho **hóa đơn** có thể bị **đặt vào ngữ cảnh cấp quyền**.

Chữ ký vẫn hợp lệ: bytes không bị sửa, khóa không sai. Nhưng quyết định nghiệp vụ là sai vì **mục đích không được ràng buộc**.

Tình huống tương tự:

- Một chứng từ của `tenant-A` được dùng cho tài nguyên `tenant-B`.
- Lệnh `APPROVE` bị hiểu như `TRANSFER`.
- Một request dành cho `billing-service` được gửi sang `admin-service`.
- Một chữ ký cũ được gửi lại sau thời hạn hoặc nhiều lần trong cùng thời hạn.
- `keyId` do client khai được dùng để chọn một khóa có quyền khác.
- Một request có chữ ký đúng nhưng signer không được phép thao tác trên tài nguyên đó.

Do đó, một request chỉ được chấp nhận khi:

~~~text
ACCEPT =
  signatureValid(signedBytes, trustedPublicKey)
  AND keyAndAlgorithmAllowed
  AND protocolAndPurposeMatch
  AND audienceTenantResourceActionMatch
  AND timeWindowValid
  AND replayNotPreviouslyConsumed
  AND businessAuthorizationAllowed
~~~

**Không đánh đồng** `Signature.verify() == true` với “hành động này được phép”.

## 2. Ba lớp cần phân biệt: signed bytes, signed claims và verifier policy

**Lớp 1 — signed bytes:** các byte chính xác được cung cấp cho `Signature.update(...)`. Ed25519 bảo vệ bytes đó, không bảo vệ ngữ cảnh ở ngoài input.

**Lớp 2 — signed claims:** những giá trị ứng dụng đóng gói bên trong signed bytes: version, purpose, issuer, audience, tenant, action, resource, timestamps, nonce và payload.

**Lớp 3 — trusted policy:** kỳ vọng của dịch vụ nhận, lấy từ endpoint, danh tính đã xác thực, registry khóa, quyền thực thi, đồng hồ và kho chống replay. Những giá trị kỳ vọng này **không được lấy bằng cách tin ngay claims do client khai**.

Ví dụ:

~~~java
// Mảnh minh họa SAI: không có kiểm tra mục đích độc lập.
String expectedPurpose = receivedPurpose;
boolean validPurpose = expectedPurpose.equals(receivedPurpose);
~~~

Điều kiện luôn đúng nếu chuỗi không null. Một kiểm tra hữu ích phải so với policy riêng:

~~~java
// Mảnh minh họa đúng về ý tưởng, chưa phải chương trình độc lập.
String endpointPurpose = "INVOICE_APPROVAL";
boolean validPurpose = endpointPurpose.equals(signedPurpose);
~~~

Ngay cả sau khi chữ ký đã xác minh thành công, các claims vẫn cần được **đối chiếu** với policy. Một chữ ký có thể xác thực rằng signer **thực sự yêu cầu** chuyển tiền, nhưng không tự chứng minh signer **có quyền** chuyển số tiền đó.

## 3. Ràng buộc purpose, type và protocol version

Giao thức nên phân biệt những khái niệm sau:

| Trường | Vai trò | Ví dụ |
| --- | --- | --- |
| `protocolVersion` | Định danh format/semantics cụ thể | `billing.invoice.v1` |
| `purpose` | Lý do dùng chữ ký | `INVOICE_APPROVAL` |
| `messageType` | Loại message, schema | `InvoiceCommand` |
| `action` | Hành động cụ thể | `APPROVE` |
| `domain` | Nhãn ngữ cảnh ổn định của signature | `com.example.billing/approve/v1` |

Không nhất thiết mọi dự án tách thành năm field; cần đủ để **hai chức năng khác nhau không tình cờ xem cùng signature là cùng loại yêu cầu**.

### Domain separation ở tầng ứng dụng

Thay vì chỉ ký payload `approve=true`, đưa nhãn domain và mục đích vào **dữ liệu thực được ký**:

~~~text
encode(
    domain = "com.example.billing/approve/v1",
    purpose = "INVOICE_APPROVAL",
    action = "APPROVE",
    payload = ...
)
      |
      v
Signature.update(encodedBytes)
~~~

Một request dành cho password reset phải dùng domain/purpose khác và có **validation rules riêng**. Điều này tạo cách ly về ngữ cảnh ngay cả khi ứng dụng cùng dùng thuật toán Ed25519.

**Lưu ý:** domain string ở tầng ứng dụng chỉ là một phần của **message được ký**, không phải tính năng cryptographic context của biến thể `Ed25519ctx` trong RFC 8032. Không tự thay đổi toán học của thuật toán; sử dụng `Signature.getInstance("Ed25519")` chuẩn.

### Trường bên ngoài chữ ký không được bảo vệ

Nếu chỉ ký `body` rồi đặt `purpose` ở một HTTP header không được ký, attacker có thể sửa purpose mà giữ nguyên signature. Đây không phải lỗi Ed25519; đó là lỗi **phạm vi bytes được ký**.

## 4. Ràng buộc issuer, audience, tenant, resource, action và keyId

Một signed envelope có thể chứa:

~~~text
issuer   = partner-A
audience = billing-service
tenant   = tenant-A
resource = invoice-42
action   = APPROVE
keyId    = partner-A-key-1
~~~

**Ý nghĩa và phép kiểm tra:**

- **Issuer:** người/tổ chức được tuyên bố là bên ký. Public key phải được ràng buộc với issuer bằng nguồn tin cậy.
- **Audience:** hệ thống nhận dự kiến. Không chấp nhận bản tin cho dịch vụ khác.
- **Tenant:** phạm vi dữ liệu và cô lập khách hàng. Phải khớp tenant đã xác thực từ ngữ cảnh server.
- **Resource:** đối tượng cụ thể mà hành động tác động. Phải khớp route, database và quyền của signer.
- **Action:** phải nằm trong tập hành động được phép của key và identity.
- **Key ID:** nhãn tra cứu khóa trong **trusted registry**, không phải bằng chứng quyền.

Ví dụ endpoint:

~~~text
POST /tenants/tenant-B/invoices/invoice-42/approve
~~~

Nếu signed claim cho `tenant-A`, request phải bị từ chối khi thực hiện trong ngữ cảnh `tenant-B`. Một chữ ký hợp lệ với khóa của tenant-A **không** biến nó thành hành động của tenant-B.

### Chọn public key từ registry tin cậy

Một cấu hình khái niệm:

~~~text
trustedKeyRegistry[(issuer, keyId)] =>
  publicKey
  allowedAlgorithm = Ed25519
  allowedPurposes  = {INVOICE_APPROVAL}
  allowedAudiences = {billing-service}
  allowedTenants   = {tenant-A}
  keyState         = active
~~~

Verifier chỉ dùng key từ nguồn tin cậy. Không chấp nhận tùy ý public key hoặc URL `jku`/`x5u` do request cung cấp để làm nguồn xác thực danh tính. Kiểm tra algorithm allowlist, key usage, rotation/revocation và quyền trong phạm vi nghiệp vụ.

Dù `keyId` đã được ký, hệ thống vẫn cần kiểm tra **nó có gắn với đúng public key, issuer và quyền hay không**. Client tự khai `keyId=admin` không cấp quyền admin.

## 5. Ràng buộc thời hạn: issuedAt, notBefore, expiresAt

Ba trường có ý nghĩa khác nhau:

- `issuedAt`: signer khai thời điểm phát hành.
- `notBefore`: thời điểm sớm nhất được nhận.
- `expiresAt`: thời điểm bắt đầu **hết hiệu lực**.

Thống nhất biểu diễn Unix epoch **seconds**, UTC. Một chính sách điển hình:

~~~text
issuedAt <= now
notBefore <= now
now < expiresAt
issuedAt < expiresAt
notBefore < expiresAt
expiresAt - issuedAt <= maxTTL
~~~

Với `expiresAt=1700000160`, thời điểm `now=1700000160` đã **hết hạn**, nếu quy tắc là nửa mở `[notBefore, expiresAt)`.

### Phải dùng đồng hồ của verifier

~~~java
// Mảnh mã trong một phương thức.
long now = java.time.Instant.now().getEpochSecond();
~~~

Không dùng timestamp do client truyền làm `now` để kiểm tra chính client đó. Timestamp trong signed message không tự có nguồn thời gian đáng tin: chữ ký chỉ xác nhận signer đã **ký giá trị** đó.

### TTL tối đa và clock skew

Dù `expiresAt` đã được ký, signer có thể ký thời hạn quá xa với policy. Verifier nên giới hạn `maxTTL` cho từng purpose. Nếu hệ phân tán cần dung sai đồng hồ, chỉ cho phép **skew hữu hạn và có chủ đích**; một số hành động nhạy cảm cần từ chối ngay tại expiry, không gia hạn grace.

### Cảnh giác sai đơn vị và overflow

`System.currentTimeMillis()` trả **mili giây**, `Instant.now().getEpochSecond()` trả **giây**. Không so trực tiếp hai đại lượng. Với timestamps nhận từ dữ liệu không tin cậy, validate range trước khi tính hiệu hoặc cộng skew để tránh `long` overflow.

## 6. Nonce, replay và idempotency

Một signature đúng có thể được gửi lại **nguyên văn**; phép verify vẫn đúng vì message bytes và public key không đổi.

Để chống replay:

1. Đưa `nonce` hoặc `requestId` **vào dữ liệu được ký**.
2. Định nghĩa uniqueness scope, ví dụ signer + tenant + purpose + nonce.
3. Chỉ **đánh dấu nonce đã dùng sau khi** chữ ký/ngữ cảnh/time policy được xác thực.
4. Dùng kho trạng thái có **atomic uniqueness**, tránh hai request đồng thời cùng vượt qua bước kiểm tra.
5. Giữ trạng thái đủ lâu theo thời hạn có thể replay; xử lý restart, multi-node, clock skew.
6. Liên kết việc consume nonce với business side effect theo transaction/idempotency thích hợp.

**Vì sao một nonce được ký chưa đủ?** Kẻ tấn công có thể phát lại nguyên nonce + payload + chữ ký. Chỉ khi server **ghi nhớ đã xử lý**, request mới bị từ chối hoặc được trả kết quả cũ theo idempotency policy.

**Vì sao không đánh dấu nonce trước verify?** Một request giả có nonce đoán được có thể đầu độc replay cache và chặn request hợp lệ.

Một `HashSet` cục bộ chỉ phù hợp demo đơn luồng/đơn tiến trình; production cần database unique constraint, transactional insert hoặc atomic shared store phù hợp.

## 7. Signed envelope: ký đúng trường và serialize không nhập nhằng

Ví dụ các claims:

~~~json
{
  "protocol": "billing.invoice.v1",
  "purpose": "INVOICE_APPROVAL",
  "issuer": "partner-A",
  "audience": "billing-service",
  "tenant": "tenant-A",
  "resource": "invoice-42",
  "action": "APPROVE",
  "keyId": "partner-A-key-1",
  "issuedAt": 1700000100,
  "notBefore": 1700000100,
  "expiresAt": 1700000160,
  "nonce": "request-123",
  "body": {
    "amount": 100,
    "currency": "VND",
    "recipient": "account-7"
  }
}
~~~

Đây là **cấu trúc minh họa**, chưa phải canonical JSON. Ed25519 ký **bytes**, không ký ý nghĩa trừu tượng của JSON: thứ tự keys, whitespace, escaping, Unicode NFC/NFD, newline hay biểu diễn số khác nhau có thể tạo chữ ký khác.

Hai phương án hợp lý:

- Ký **raw bytes** đã tạo đúng một lần, gửi nguyên signedBytes và verify trước khi parse.
- Ký **canonical bytes** theo một tiêu chuẩn/định dạng được hai bên thỏa thuận chi tiết, có test vectors.

Không tự giả định sort keys + `toString()` là canonical JSON chuẩn.

### Vì sao phải có framing?

Nếu chỉ ghép field A và field B:

~~~text
("ab","c")  -> "abc"
("a","bc")  -> "abc"
~~~

Hai cặp giá trị cho cùng bytes. Một format binary đơn giản có thể ghi `length-prefix` của UTF-8 bytes trước mỗi string, rồi timestamp dưới dạng số nguyên 64-bit. `String.length()` đếm UTF-16 units, **không** phải kích thước UTF-8. Trong Java, `DataOutputStream.writeInt`/`writeLong` dùng big-endian.

Khi đưa giao thức vào production, phải có version, max field length, nullable rules, canonicalization, parsing an toàn và xử lý unknown fields.

## 8. Ví dụ Java 17+ hoàn chỉnh: purpose, audience, tenant, thời hạn và replay

File **`SignedProtocolDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.HashSet;
import java.util.Set;

public final class SignedProtocolDemo {
    private static final String PROTOCOL = "billing.invoice.v1";
    private static final long MAX_TTL = 300L;

    private static final class Message {
        final String purpose, issuer, audience, tenant;
        final String resource, action, keyId, nonce, body;
        final long issuedAt, notBefore, expiresAt;

        Message(String purpose, String issuer, String audience,
                String tenant, String resource, String action,
                String keyId, String nonce, String body,
                long issuedAt, long notBefore, long expiresAt) {
            this.purpose = purpose;
            this.issuer = issuer;
            this.audience = audience;
            this.tenant = tenant;
            this.resource = resource;
            this.action = action;
            this.keyId = keyId;
            this.nonce = nonce;
            this.body = body;
            this.issuedAt = issuedAt;
            this.notBefore = notBefore;
            this.expiresAt = expiresAt;
        }

        Message withBody(String changedBody) {
            return new Message(purpose, issuer, audience, tenant,
                    resource, action, keyId, nonce, changedBody,
                    issuedAt, notBefore, expiresAt);
        }
    }

    private static void writeString(DataOutputStream out, String value)
            throws IOException {
        byte[] data = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(data.length);
        out.write(data);
    }

    private static byte[] encode(Message m) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            writeString(out, PROTOCOL);
            writeString(out, m.purpose);
            writeString(out, m.issuer);
            writeString(out, m.audience);
            writeString(out, m.tenant);
            writeString(out, m.resource);
            writeString(out, m.action);
            writeString(out, m.keyId);
            out.writeLong(m.issuedAt);
            out.writeLong(m.notBefore);
            out.writeLong(m.expiresAt);
            writeString(out, m.nonce);
            writeString(out, m.body);
        }
        return bytes.toByteArray();
    }

    private static byte[] sign(PrivateKey key, Message m)
            throws GeneralSecurityException, IOException {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(key);
        signer.update(encode(m));
        return signer.sign();
    }

    private static boolean accept(
            Message m, byte[] signature, PublicKey trustedKey,
            String expectedPurpose, String expectedAudience,
            String expectedTenant, String expectedResource,
            long now, Set<String> usedNonces)
            throws GeneralSecurityException, IOException {

        // Policy kỳ vọng độc lập với dữ liệu request.
        if (!expectedPurpose.equals(m.purpose)
                || !expectedAudience.equals(m.audience)
                || !expectedTenant.equals(m.tenant)
                || !expectedResource.equals(m.resource)
                || !"APPROVE".equals(m.action)
                || !"partner-A".equals(m.issuer)
                || !"partner-A-key-1".equals(m.keyId)) {
            return false;
        }

        // Thời gian demo là epoch seconds có range nhỏ.
        if (m.issuedAt < 0
                || m.notBefore < m.issuedAt
                || m.expiresAt <= m.notBefore
                || m.expiresAt <= m.issuedAt
                || m.issuedAt > now
                || now < m.notBefore
                || now >= m.expiresAt
                || m.expiresAt - m.issuedAt > MAX_TTL
                || m.nonce.isEmpty()) {
            return false;
        }

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(trustedKey);
        verifier.update(encode(m));
        if (!verifier.verify(signature)) {
            return false;
        }

        // DEMO: một tiến trình, một luồng.
        // Production cần replay store atomic/durable.
        return usedNonces.add(m.nonce);
    }

    public static void main(String[] args) throws Exception {
        KeyPair pair = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();
        long now = 1_700_000_100L;

        Message message = new Message(
                "INVOICE_APPROVAL", "partner-A",
                "billing-service", "tenant-A",
                "invoice-42", "APPROVE",
                "partner-A-key-1", "request-123",
                "amount=100;currency=VND;recipient=account-7",
                now - 5, now - 5, now + 60);

        byte[] signed = sign(pair.getPrivate(), message);
        Set<String> consumed = new HashSet<>();

        System.out.println("first accepted: " + accept(
                message, signed, pair.getPublic(),
                "INVOICE_APPROVAL", "billing-service",
                "tenant-A", "invoice-42", now, consumed));
        System.out.println("replay rejected: " + !accept(
                message, signed, pair.getPublic(),
                "INVOICE_APPROVAL", "billing-service",
                "tenant-A", "invoice-42", now, consumed));

        System.out.println("purpose rejected: " + !accept(
                message, signed, pair.getPublic(),
                "PASSWORD_RESET", "billing-service",
                "tenant-A", "invoice-42", now, new HashSet<>()));
        System.out.println("audience rejected: " + !accept(
                message, signed, pair.getPublic(),
                "INVOICE_APPROVAL", "other-service",
                "tenant-A", "invoice-42", now, new HashSet<>()));
        System.out.println("tenant rejected: " + !accept(
                message, signed, pair.getPublic(),
                "INVOICE_APPROVAL", "billing-service",
                "tenant-B", "invoice-42", now, new HashSet<>()));
        System.out.println("resource rejected: " + !accept(
                message, signed, pair.getPublic(),
                "INVOICE_APPROVAL", "billing-service",
                "tenant-A", "invoice-99", now, new HashSet<>()));

        System.out.println("payload rejected: " + !accept(
                message.withBody(
                        "amount=900;currency=VND;recipient=account-7"),
                signed, pair.getPublic(),
                "INVOICE_APPROVAL", "billing-service",
                "tenant-A", "invoice-42", now, new HashSet<>()));

        System.out.println("expired rejected: " + !accept(
                message, signed, pair.getPublic(),
                "INVOICE_APPROVAL", "billing-service",
                "tenant-A", "invoice-42", now + 61, new HashSet<>()));
        System.out.println("not-before rejected: " + !accept(
                message, signed, pair.getPublic(),
                "INVOICE_APPROVAL", "billing-service",
                "tenant-A", "invoice-42", now - 10, new HashSet<>()));

        KeyPair stranger = KeyPairGenerator
                .getInstance("Ed25519").generateKeyPair();
        System.out.println("wrong key rejected: " + !accept(
                message, signed, stranger.getPublic(),
                "INVOICE_APPROVAL", "billing-service",
                "tenant-A", "invoice-42", now, new HashSet<>()));
    }
}
~~~

Biên dịch và chạy trên JDK 17+ có Ed25519 provider:

~~~bash
javac SignedProtocolDemo.java
java SignedProtocolDemo
~~~

**Stdout kỳ vọng:** (hai key pairs sinh độc lập bằng randomness an toàn, xác suất trùng nhau không đáng kể)

~~~text
first accepted: true
replay rejected: true
purpose rejected: true
audience rejected: true
tenant rejected: true
resource rejected: true
payload rejected: true
expired rejected: true
not-before rejected: true
wrong key rejected: true
~~~

Giải thích:

1. **Lần đầu:** signed bytes và khóa đúng, ngữ cảnh phù hợp, `now` nằm trong cửa sổ, nonce chưa dùng nên accept.
2. **Lần hai:** signature vẫn đúng nhưng `consumed.add("request-123")` trả `false`; có tác dụng minh họa replay check.
3. **Sai purpose/audience/tenant/resource:** chữ ký có thể hợp lệ về toán học, nhưng expected policy khác message, nên từ chối.
4. **Body bị thay từ 100 thành 900:** bytes không còn như bản đã ký nên signature verification thất bại.
5. **Hết hạn:** `now+61` lớn hơn `expiresAt=now+60`; request bị từ chối.
6. **Chưa hiệu lực:** `now-10 < notBefore` nên bị từ chối.
7. **Sai khóa:** public key khác không xác minh được signature của private key ban đầu.

### Phạm vi và giới hạn demo

- `KeyPair` mới được tạo để chạy test. Public key dùng trong verifier **giả định được tin cậy**; production phải lấy từ registry xác thực gắn signer/keyId/permissions.
- `HashSet` chỉ là ví dụ tuần tự đơn tiến trình. Production cần atomic durable state và xử lý idempotency cùng side effect.
- `now` cố định giúp stdout lặp lại. Production lấy giờ từ `Instant`/`Clock` tin cậy và áp policy/skew.
- Format binary của `encode` có thứ tự và length-prefix, nhưng chưa có parser, input bounds, max bytes, null checks, chuẩn Unicode, version negotiation và test vectors hoàn chỉnh.
- `issuer`/`action`/`keyId` trong `accept` được cố định để minh họa independent policy, không phải chiến lược quản lý khóa mở rộng.
- Nếu application có các writes/transactions kéo dài, recheck trạng thái quyền, thời hạn, tài nguyên tại điểm commit.

Cùng API Ed25519 đã có từ Java 15 và không cần `--enable-preview`. Trên JDK còn hỗ trợ target 15, có thể kiểm tra:

~~~bash
javac --release 15 SignedProtocolDemo.java
~~~

## 9. Trình tự nhận/verify một request đúng

~~~text
1. Nhận envelope, giới hạn kích thước và kiểm tra cấu trúc.
2. Xác định endpoint, expected purpose/audience/tenant/resource.
3. Tra trusted public key từ issuer/keyId allowlist.
4. Kiểm tra thuật toán/key usage/key state.
5. Verify đúng signedBytes bằng Signature Ed25519.
6. So signed claims với context/policy độc lập phía server.
7. Check issuedAt/notBefore/expiresAt/maxTTL với đồng hồ verifier.
8. Check authorization và trạng thái nghiệp vụ.
9. Consume nonce atomically cùng thao tác nghiệp vụ.
10. Commit/return đúng một lần (hoặc đáp ứng idempotency policy).
~~~

Một số kiểm tra **sơ bộ** như độ dài, schema hoặc audience khác rõ ràng có thể chạy trước crypto verify để giảm chi phí, nhưng không được tạo side effect hay tin nội dung chưa xác thực. Bước **accept cuối cùng** luôn phải thỏa tất cả điều kiện.

Không đánh dấu nonce đã dùng nếu chữ ký chưa được xác thực, bởi request giả có thể đầu độc kho replay.

## 10. Kết nối các tiêu chuẩn còn áp dụng

### JWT/JWS: cross-token confusion

**RFC 8725 — JSON Web Token Best Current Practices** cảnh báo token cho loại nghiệp vụ này bị chấp nhận ở loại khác. Giải pháp gồm:

- Verify đúng algorithm cho phép, gắn algorithm với key policy.
- Kiểm tra issuer `iss` và audience `aud` theo endpoint.
- Sử dụng explicit token type như `typ` hoặc profile riêng khi cần.
- Thiết kế **mutually exclusive validation rules** giữa các token types.
- Không tin tùy ý `kid`, `jku`, `x5u` từ request để lấy khóa hoặc truy cập URL (nguy cơ key confusion/SSRF).
- Kiểm tra timestamps, quyền hạn và trạng thái thu hồi theo chính sách.

JWT/JWS là format tiêu chuẩn riêng. Không coi binary encoder trong demo là JWT/JWS.

### HTTP Message Signatures

**RFC 9421 — HTTP Message Signatures** quy định signature base cho những thành phần HTTP được chọn cùng metadata như `created`, `expires`, `nonce`. Verifier phải chắc chắn **các thành phần quan trọng đều nằm trong phạm vi được ký**, key/algorithm được phép, time window phù hợp và replay được kiểm soát theo threat model.

Khi triển khai HTTP signatures, dùng đúng canonicalization/serialization của RFC 9421 và thư viện đã được kiểm thử, không tự tạo một biến thể giống tên chuẩn.

## 11. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ gọi `Signature.verify()` rồi cho phép | Chữ ký đúng nhưng sai nghiệp vụ | Kiểm tra context/time/authorization |
| Không ký `purpose` | Dùng chéo chức năng | Signed purpose + expected purpose độc lập |
| Không ký `audience` | Mang request sang service khác | Bind audience và so với endpoint |
| Không ký `tenant/resource/action` | Tác động nhầm đối tượng | Signed fields và quyền thực |
| Đưa `expiresAt` ngoài chữ ký | Kéo dài hạn dùng | Bảo vệ timestamps trong signed bytes |
| Dùng `issuedAt` của client làm thời gian hiện tại | Client tự quyết định còn hạn | Verifier clock |
| Không giới hạn TTL | Request hợp lệ quá lâu | MaxTTL theo purpose |
| So epoch milli với epoch seconds | Sai điều kiện thời gian | Định dạng/unities nhất quán |
| Không chặn clock skew/overflow | Mở rộng cửa sổ bất hợp lý | Bound input + skew hữu hạn |
| Chỉ ký nonce, không lưu state | Replay không bị chặn | Atomic nonce store |
| Mark nonce trước verify | Replay store bị đầu độc | Chỉ consume sau kiểm tra hợp lệ |
| `HashSet` trên mỗi replica | Replay vẫn chạy ở máy khác | Shared durable store/idempotency |
| Dùng public key do attacker gửi | Tự ký giả được verify | Trusted key registry |
| Tin `keyId` như permission | Selector bị lạm dụng | Key policy và authorization |
| Không có schema/framing | Ghép fields mơ hồ | Length prefix/canonical encoding |
| Bên nhận serialize JSON khác bên ký | Verify fail dù “nội dung giống” | Chính xác signed bytes |
| Tin tùy ý thuật toán do token khai | Algorithm confusion/downgrade | Explicit allowlist |
| Không phân loại JWT token types | Cross-token confusion | Type/validation rules riêng |
| Thực hiện side effect trước verify | Request giả gây hậu quả | Fail closed và commit sau checks |

## 12. Checklist kiểm thử và bài tập

Các test quan trọng: happy path; sửa payload; sai purpose/audience/tenant/resource/action; sai signer/khóa; key revoked; `now < notBefore`; `now == expiresAt`; TTL quá dài; timestamp đơn vị/range sai; replay một lần và replay đồng thời; unknown protocol version; malformed input; signed field bị bỏ sót; serialize UTF-8/Unicode/newline khác; mỗi lỗi verify/key/parser đều fail closed.

**Bài 1.** Chữ ký Ed25519 hợp lệ trên `approve=true` có tự chứng minh đây là lệnh phê duyệt hóa đơn không?

**Đáp án:** Không. Cần ký purpose/protocol/action và so với policy endpoint.

**Bài 2.** `expiresAt` nằm trong HTTP header không được ký. Attacker có thể kéo dài thời hạn mà signature vẫn đúng không?

**Đáp án:** Có. Chữ ký chỉ bảo vệ bytes nằm trong signature base; phải đưa expiry vào phần được ký.

**Bài 3.** Token có `audience=billing-service` nhưng được gửi sang `inventory-service`. Verify signature đúng có đủ accept?

**Đáp án:** Không. Audience không khớp; endpoint inventory-service phải từ chối.

**Bài 4.** Chữ ký đúng, nonce đã xử lý trước đó. Có được thực hiện nghiệp vụ lần nữa không?

**Đáp án:** Không. Replay/idempotency check phải ngăn side effect lặp.

**Bài 5.** Vì sao không lấy `receivedPurpose` làm `expectedPurpose`?

**Đáp án:** Đó là kiểm tra một field với chính nó, không xác nhận expected context. Expected value phải đến từ policy tin cậy.

**Bài 6.** Hai tuples `("ab","c")` và `("a","bc")` có thể được ký thành cùng bytes nếu chỉ nối chuỗi không?

**Đáp án:** Có. Dùng canonical framing, ví dụ length-prefix UTF-8 cho từng field.

**Bài 7.** Vì sao keyId trong request không đủ để quyết định signer có quyền?

**Đáp án:** KeyId chỉ gợi ý tra key. Key và issuer phải được kiểm chứng trong trusted registry và quyền ký phải được kiểm tra độc lập.

**Bài 8.** Có thể dùng `HashSet` ở mỗi replica để chống replay toàn hệ thống không?

**Đáp án:** Không. Cần shared atomic/durable uniqueness và xử lý concurrency.

**Bài 9.** Timestamp đã được ký thì có thể bỏ kiểm tra TTL tối đa không?

**Đáp án:** Không. Signer có thể ký thời hạn quá dài; verifier cần policy maxTTL và đồng hồ độc lập.

**Bài 10.** Một JWT dùng cho access token có nên được nhận như password reset token nếu signature hợp lệ?

**Đáp án:** Không. Dùng token type, audience, issuer và validation rules riêng theo RFC 8725.

## 13. Tài liệu tiêu chuẩn và API

- **JEP 339 — EdDSA trong Java 15:** https://openjdk.org/jeps/339
- **RFC 8032 — EdDSA (Ed25519/Ed448):** https://www.rfc-editor.org/rfc/rfc8032
- **Oracle Java SE 17 — `Signature`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html
- **Oracle Java SE 17 — `Clock`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html
- **RFC 8725 — JWT Best Current Practices:** https://www.rfc-editor.org/rfc/rfc8725.html
- **RFC 9421 — HTTP Message Signatures:** https://www.rfc-editor.org/rfc/rfc9421.html
- **RFC 7515 — JSON Web Signature (JWS):** https://www.rfc-editor.org/rfc/rfc7515

**Kết luận:** `Signature.verify()` chỉ kiểm tra chữ ký trên bytes theo public key. Một giao thức an toàn phải đưa **protocol version, purpose, issuer/keyId, audience, tenant, resource/action, issuedAt/notBefore/expiresAt, nonce và payload** vào signed bytes, rồi verifier so chúng với **policy và trạng thái tin cậy**. Cuối cùng phải kiểm tra thời hạn, quyền ký và replay một cách atomic trước khi tạo side effect. Đây là điểm phân biệt giữa **“chữ ký hợp lệ”** và **“request được phép thực hiện”**.
