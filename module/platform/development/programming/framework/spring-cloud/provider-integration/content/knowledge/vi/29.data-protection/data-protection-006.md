# Kiểm tra chữ ký webhook, token sự kiện và chống phát lại

Webhook và event callback giúp Spring Boot nhận thông báo từ payment gateway, CRM, object storage, message broker hoặc dịch vụ cloud. Một request có thể yêu cầu ứng dụng cập nhật đơn hàng, phát hành hóa đơn, cấp quyền tải file hoặc kích hoạt workflow. Nếu endpoint chỉ nhận JSON rồi xử lý ngay, kẻ tấn công có thể giả mạo request, sửa payload hoặc gửi lại một thông báo hợp lệ nhiều lần.

Một webhook an toàn phải trả lời ba câu hỏi độc lập:

1. **Nguồn gửi có đáng tin không?** Xác minh chữ ký, MAC hoặc token xác thực do sender cung cấp.
2. **Thông điệp có nguyên vẹn không?** Chữ ký phải gắn với đúng byte của payload và các metadata quan trọng.
3. **Thông điệp đã được xử lý chưa?** Dùng timestamp, event ID, nonce và idempotency để chống replay hoặc xử lý trùng.

Chỉ kiểm tra chữ ký chưa đủ để chống phát lại. Chỉ kiểm tra timestamp cũng chưa đủ vì attacker có thể gửi lại request trong cửa sổ thời gian hợp lệ. Ứng dụng cần kết hợp xác thực mật mã với một kho lưu trạng thái sự kiện bền vững.

Bài thuộc chương **Bảo vệ dữ liệu** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud, bao gồm danh tính/quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Trọng tâm bài là kiểm tra chữ ký webhook, xác minh token sự kiện, chống replay, xử lý retry/duplicate và thiết kế endpoint nhận sự kiện an toàn.

## 1. Mục tiêu học tập và tình huống xuyên suốt

Sau bài học, bạn có thể:

1. Phân biệt webhook authentication, payload integrity, freshness và idempotency.
2. Giải thích HMAC, chữ ký bất đối xứng, JWT và TLS bảo vệ những phần nào.
3. Xác minh chữ ký trên raw request body trước khi parse JSON.
4. Dùng timestamp, event ID và nonce để phát hiện request cũ hoặc lặp.
5. Thiết kế inbox/idempotency store có unique constraint và xử lý request đồng thời.
6. Xoay webhook secret mà không làm gián đoạn sender đang dùng key cũ.
7. Tích hợp xác thực webhook với AWS SNS/EventBridge, Azure Event Grid và Google Cloud Pub/Sub.
8. Xử lý at-least-once delivery, retry, duplicate, out-of-order và dead-letter queue.
9. Kiểm thử giả mạo, sửa payload, replay, key rotation và side effect lặp.
10. Ghi audit đủ điều tra nhưng không làm lộ secret, signature hoặc dữ liệu nhạy cảm.

Tình huống xuyên suốt: **order-service** nhận thông báo thanh toán từ một payment provider. Khi nhận sự kiện thanh toán thành công, service đánh dấu đơn hàng đã thanh toán và phát lệnh tạo hóa đơn. Một request giả mạo hoặc một sự kiện bị gửi lại có thể làm đơn hàng sai trạng thái hoặc tạo hóa đơn nhiều lần.

~~~mermaid
flowchart TD
    A["Webhook / event request"] --> B["Giới hạn kích thước + HTTPS"]
    B --> C["Xác minh nguồn: HMAC / RSA / JWT"]
    C --> D["Kiểm tra timestamp và key version"]
    D --> E["Kiểm tra event ID / nonce"]
    E --> F["Ghi inbox với unique constraint"]
    F --> G["Xử lý nghiệp vụ idempotent"]
    G --> H["Ghi outbox trong cùng transaction"]
    H --> I["ACK 2xx sau khi lưu bền vững"]
    C -->|Không hợp lệ| X["Reject + security audit"]
    F -->|Duplicate| Y["Không lặp side effect; ACK theo contract"]
~~~

**Xác thực request và chống xử lý lặp là hai lớp riêng.** Chữ ký xác minh request được tạo bởi bên có secret/private key; idempotency bảo đảm cùng một sự kiện không làm nghiệp vụ chạy hai lần.

## 2. Các rủi ro của webhook và event endpoint

### 2.1. Giả mạo nguồn gửi

Nếu endpoint chỉ tin vào URL bí mật hoặc một header do client tự đặt, bất kỳ ai biết endpoint đều có thể gửi payload giả.

Ví dụ attacker gửi:

~~~http
POST /webhooks/payment HTTP/1.1
Content-Type: application/json

{"event":"payment.succeeded","orderId":"ORD-1001","amount":990000}
~~~

Nếu service cập nhật đơn hàng chỉ dựa trên JSON, request giả có thể kích hoạt nghiệp vụ. IP allowlist hoặc URL khó đoán không thay thế chữ ký/token xác thực.

### 2.2. Sửa payload trên đường truyền hoặc tại intermediary

TLS bảo vệ kết nối tới endpoint, nhưng payload có thể bị sửa trước khi ký, sau khi giải mã tại proxy hoặc bởi một thành phần có quyền trong hệ thống. Chữ ký/MAC gắn với payload giúp phát hiện nội dung không còn khớp với nội dung sender đã ký.

Nếu chỉ ký một vài field nhưng không ký amount, currency, event ID hoặc resource ID quan trọng, attacker có thể thay đổi field chưa được bảo vệ. Cần xác định rõ canonical message và metadata nào được ký.

### 2.3. Replay attack

Replay xảy ra khi một request hợp lệ được ghi lại và gửi lại:

- Một webhook thanh toán thành công bị gửi lại để tạo hóa đơn nhiều lần.
- Một callback đổi email được phát lại sau khi người dùng đã đổi mật khẩu.
- Một event cấp quyền được gửi lại sau khi quyền đã bị thu hồi.
- Một message cũ được gửi lại để ghi đè trạng thái mới.

Chữ ký hợp lệ vẫn hợp lệ nếu payload và metadata đã ký không đổi. Vì vậy, **signature verification không tự ngăn replay**.

### 2.4. Duplicate delivery do retry bình thường

Không phải mọi duplicate đều là tấn công. Hệ thống event thường giao ít nhất một lần. Sender có thể không nhận được ACK dù receiver đã xử lý xong, nên sender gửi lại. Network timeout, process restart hoặc ACK thất bại cũng tạo duplicate.

Ứng dụng phải xử lý duplicate an toàn thay vì giả định mỗi event chỉ đến một lần.

### 2.5. Out-of-order delivery

Hai event liên quan có thể đến không theo thứ tự phát sinh:

- Order được tạo rồi cập nhật trạng thái, nhưng event cập nhật tới trước.
- Inventory nhận event reserve sau event release.
- Subscription nhận trạng thái active cũ sau khi đã nhận trạng thái cancelled mới.

Không dùng thời gian nhận request làm thứ tự nghiệp vụ. Nếu thứ tự quan trọng, dùng sequence/version của aggregate hoặc đọc trạng thái hiện tại từ nguồn có thẩm quyền.

## 3. HMAC, chữ ký số và JWT

### 3.1. HMAC là gì?

HMAC (Hash-based Message Authentication Code) dùng một secret chung và hàm hash mật mã, thường là SHA-256, để tạo mã xác thực:

\[
\operatorname{HMAC}_{SHA256}(K, M)
\]

Trong đó:

- K là shared secret chỉ sender và receiver được biết.
- M là message bytes được ký.
- Kết quả là MAC, thường được biểu diễn bằng hex hoặc Base64.

Sender tính MAC rồi gửi kèm request. Receiver tính lại với cùng secret và so sánh. Nếu payload hoặc metadata đã ký thay đổi, kết quả không khớp.

**HMAC không mã hóa payload.** Người nhận vẫn đọc được JSON. HMAC cung cấp authentication và integrity, còn TLS bảo vệ dữ liệu trên đường truyền.

### 3.2. Chữ ký bất đối xứng

Với chữ ký RSA hoặc ECDSA:

- Sender giữ private key để ký.
- Receiver dùng public key tương ứng để xác minh.
- Receiver không cần giữ private signing key.
- Một public key có thể được phân phối cho nhiều consumer.

Cơ chế này phù hợp khi provider ký sự kiện bằng private key và receiver cần xác minh bằng public key. Ví dụ Amazon SNS ký notification bằng RSA. Chữ ký bất đối xứng không tự mã hóa message và cũng không tự ngăn replay.

### 3.3. JWT là gì?

JWT là định dạng token có header, claims và signature/MAC. Với webhook push, token thường xác thực service gửi request:

- Issuer (iss): bên phát hành token.
- Subject (sub): principal được đại diện.
- Audience (aud): endpoint/resource server được phép nhận token.
- Expiration (exp): thời điểm hết hạn.
- Issued-at (iat): thời điểm phát hành.
- Signature: xác minh token không bị sửa và được issuer ký.

Không coi việc decode JWT thành công là xác thực. Receiver phải kiểm tra chữ ký, issuer, audience, thời hạn và các claim bắt buộc theo provider. Không chấp nhận thuật toán hoặc key do token tự khai báo nếu không nằm trong cấu hình tin cậy.

### 3.4. So sánh

| Cơ chế | Bí mật nằm ở đâu? | Xác minh điều gì? | Replay được ngăn thế nào? |
| --- | --- | --- | --- |
| HMAC-SHA256 | Shared secret ở sender và receiver | Payload/metadata do hai bên ký | Timestamp + event ID/nonce store |
| RSA/ECDSA signature | Private key ở sender; public key ở receiver | Payload được private key ký | Timestamp + event ID/nonce store |
| JWT bearer token | Signing key ở issuer; verifier có public key/secret phù hợp | Identity, audience, claims và token integrity | Token expiry, jti/revocation nếu có; event ID vẫn cần cho duplicate |
| TLS/mTLS | Certificate/private key và session keys | Kênh kết nối, có thể xác thực client | Không tự chống replay ở tầng nghiệp vụ |
| API key | Shared secret/token tĩnh | Quyền truy cập theo key nếu server kiểm tra | Cần rotation, TTL, nonce/idempotency riêng |

### 3.5. Không dùng một cơ chế thay cho tất cả

- TLS là bắt buộc cho webhook qua Internet.
- HMAC/RSA xác minh message hoặc provider.
- JWT xác thực service identity và audience khi provider hỗ trợ.
- Timestamp kiểm tra freshness.
- Event ID/nonce và inbox chống duplicate/replay.
- Authorization kiểm tra event có được phép thay đổi đúng resource/tenant hay không.

Một request có chữ ký hợp lệ vẫn có thể không được phép cập nhật đơn hàng thuộc tenant khác.

## 4. Ký và xác minh payload đúng cách

### 4.1. Ký raw body bytes

JSON có nhiều cách biểu diễn tương đương:

~~~json
{"amount":1000,"currency":"USD"}
~~~

~~~json
{
  "currency": "USD",
  "amount": 1000
}
~~~

Hai payload có thể parse thành cùng object nhưng byte khác nhau. Nếu sender ký byte JSON ban đầu mà receiver parse rồi serialize lại trước khi tính HMAC, chữ ký có thể sai. Nếu receiver ký một canonical representation tự thiết kế, sender và receiver có thể hiểu khác nhau về whitespace, Unicode, number format hoặc escaping.

Quy tắc an toàn:

1. Đọc raw request body dưới dạng byte[].
2. Xác minh chữ ký trên đúng bytes và metadata theo spec của sender.
3. Chỉ parse JSON sau khi xác minh thành công.
4. Không dùng lại request body đã normalize hoặc serialize lại để xác minh.
5. Không bỏ qua field chỉ vì ứng dụng không sử dụng; sender có thể đã ký toàn bộ payload.

Một số provider định nghĩa canonical string riêng thay vì ký raw body. Phải tuân thủ chính xác tài liệu của provider, không tự thay đổi thứ tự field hoặc encoding.

### 4.2. Ký cả timestamp và event ID

Một format ví dụ cho webhook HMAC tự thiết kế:

~~~text
X-Webhook-Key-Id: key-2026-02
X-Webhook-Timestamp: 1795512000
X-Webhook-Event-Id: evt_8f2a9c
X-Webhook-Signature: v1=<hex-mac>
~~~

Canonical message:

~~~text
v1
key-2026-02
1795512000
evt_8f2a9c
<raw-body-bytes>
~~~

Sender và receiver phải thống nhất encoding, separator, newline và cách xử lý byte. Timestamp, key ID và event ID đều nằm trong phần được xác thực; attacker không thể thay chúng mà vẫn giữ MAC hợp lệ.

Đây là **giao thức minh họa do ứng dụng thiết kế**, không phải header chuẩn chung của AWS, Azure, Google hoặc Stripe. Khi tích hợp provider, dùng header và signing format chính thức của họ.

### 4.3. Chọn thuật toán và độ dài secret

- Ưu tiên HMAC-SHA256 trở lên cho shared-secret webhook mới.
- Dùng secret ngẫu nhiên entropy cao, tối thiểu 32 byte cho HMAC-SHA256 theo policy nội bộ.
- Không dùng password do con người chọn làm webhook secret.
- Không dùng MD5 hoặc SHA-1 thuần để xác thực message.
- Không tự ghép secret với SHA256 bằng cách nối chuỗi; dùng HMAC API.
- Với chữ ký số, dùng thuật toán/key type theo provider và thư viện được duy trì.
- Không tự viết thuật toán RSA/ECDSA hoặc parser chữ ký.

### 4.4. So sánh chữ ký an toàn

Khi so sánh MAC, không dùng phép so sánh chuỗi thông thường nếu nó dừng ở byte đầu tiên khác nhau. Dùng hàm constant-time phù hợp, ví dụ Java MessageDigest.isEqual cho byte arrays có độ dài hợp lệ.

Trước khi so sánh:

- Kiểm tra version/prefix của signature.
- Kiểm tra encoding hex/Base64.
- Từ chối chữ ký sai độ dài.
- Không log giá trị signature hoặc secret.
- Trả lỗi chung cho caller; chi tiết chỉ nằm trong security metric/audit đã được kiểm soát.

Constant-time compare giảm timing leakage khi so sánh MAC; nó không thay thế rate limit, TLS hoặc xử lý lỗi an toàn.

## 5. Timestamp, nonce và event ID chống replay

### 5.1. Timestamp window

Receiver kiểm tra timestamp nằm trong cửa sổ chấp nhận, ví dụ ±5 phút:

\[
|t_{request} - t_{server}| \leq \Delta
\]

Giá trị 5 phút chỉ là ví dụ. Chọn tolerance theo clock skew, retry policy và độ trễ mạng của provider. Timestamp phải được đưa vào phần ký; nếu không, attacker có thể thay timestamp cũ thành timestamp mới.

Dùng UTC và đồng hồ đồng bộ NTP. Từ chối timestamp ở tương lai quá xa hoặc quá cũ. Không lấy timestamp từ body chưa được xác minh để quyết định freshness.

### 5.2. Timestamp không đủ để chống replay

Một attacker chụp được request hợp lệ lúc 10:00 có thể gửi lại lúc 10:01 nếu tolerance là 5 phút. Chữ ký vẫn đúng và timestamp vẫn nằm trong cửa sổ.

Timestamp chỉ giảm thời gian request bị đánh cắp có thể dùng lại. Cần event ID hoặc nonce được lưu và kiểm tra duy nhất.

### 5.3. Event ID và nonce

- **Event ID:** định danh ổn định cho một sự kiện nghiệp vụ; sender giữ nguyên ID qua các lần retry.
- **Nonce:** giá trị ngẫu nhiên duy nhất cho một lần phát hành message/request.
- **Idempotency key:** khóa để receiver nhận diện một thao tác logic đã được tiếp nhận/xử lý.

Với event delivery có retry, ưu tiên event ID ổn định của provider. Nonce mới cho mỗi lần retry sẽ không giúp deduplicate cùng một event. Nếu giao thức do mình thiết kế, có thể dùng nonce cố định trong message gốc và giữ nguyên qua retry.

### 5.4. Lưu dấu đã nhận trong database

Không chỉ lưu event ID trong memory hoặc local cache; nhiều instance Spring Boot có thể nhận cùng event đồng thời. Dùng unique constraint trong database:

~~~sql
CREATE TABLE webhook_inbox (
    provider VARCHAR(80) NOT NULL,
    endpoint_id VARCHAR(120) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    payload_sha256 BYTEA NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ,
    status VARCHAR(24) NOT NULL,
    PRIMARY KEY (provider, endpoint_id, event_id)
);
~~~

Unique key nên được scope theo provider/endpoint/tenant theo hợp đồng định danh. Không giả định event ID của mọi provider là duy nhất toàn hệ thống.

### 5.5. Cùng event ID nhưng payload khác

Nếu event ID đã tồn tại:

- Payload hash giống nhau: duplicate delivery; không chạy side effect lần nữa.
- Payload hash khác nhau: có thể là sender bug, event ID collision hoặc dấu hiệu giả mạo; không ghi đè event cũ, đưa vào security review/quarantine.

Không trả thông tin nội bộ cho attacker. Ghi security event với provider, endpoint, event ID, hash và thời điểm; không log raw payload nhạy cảm.

### 5.6. Retention của inbox

Giữ event ID đủ lâu để bao phủ:

- Cửa sổ timestamp chấp nhận.
- Khoảng retry tối đa của provider.
- Khoảng thời gian replay có thể xảy ra theo threat model.
- Thời gian vận hành cần điều tra và replay có kiểm soát.

Nếu xóa inbox quá sớm, một event cũ có thể được xử lý lại. Có thể lưu tombstone/idempotency record lâu hơn payload chi tiết. Không cần giữ raw body vô thời hạn để chống duplicate.

## 6. Mẫu HMAC verification trong Java và Spring Boot

### 6.1. Model đã xác minh

~~~java
package com.example.webhook;

import java.time.Instant;

public record VerifiedWebhook(
        String keyId,
        String eventId,
        Instant timestamp,
        byte[] rawBody) {
}
~~~

Trong production, record cần defensive copy cho byte array hoặc dùng immutable value object. Không để caller thay đổi raw body sau khi xác minh.

### 6.2. HMAC utility

~~~java
package com.example.webhook;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.security.GeneralSecurityException;
import java.nio.charset.StandardCharsets;

public final class WebhookMac {
    private WebhookMac() {
    }

    public static byte[] hmacSha256(byte[] secret, byte[] message)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(message);
    }

    public static byte[] canonicalMessage(
            String version,
            String keyId,
            String timestamp,
            String eventId,
            byte[] rawBody) throws IOException {

        ByteArrayOutputStream output = new ByteArrayOutputStream();
        output.write((version + "\n" + keyId + "\n" + timestamp
                + "\n" + eventId + "\n").getBytes(StandardCharsets.UTF_8));
        output.write(rawBody);
        return output.toByteArray();
    }
}
~~~

Đây là giao thức minh họa. Sender phải tạo chính xác cùng canonical bytes. Với body lớn, tránh tạo nhiều bản sao không cần thiết; giới hạn kích thước request trước khi đọc toàn bộ vào memory hoặc dùng streaming MAC nếu protocol hỗ trợ.

### 6.3. Verifier có timestamp và constant-time compare

~~~java
package com.example.webhook;

import java.io.IOException;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Map;

import org.springframework.stereotype.Component;

@Component
public class WebhookVerifier {
    private final Map<String, byte[]> activeSecrets;
    private final Clock clock;
    private final Duration tolerance;

    public WebhookVerifier(
            WebhookSecretProvider secretProvider,
            Clock clock) {
        this.activeSecrets = secretProvider.currentAndPreviousSecrets();
        this.clock = clock;
        this.tolerance = Duration.ofMinutes(5);
    }

    public VerifiedWebhook verify(
            String keyId,
            String timestampHeader,
            String eventId,
            String signatureHeader,
            byte[] rawBody) {

        if (rawBody == null || rawBody.length == 0
                || rawBody.length > 1_048_576) {
            throw new InvalidWebhookException();
        }

        if (eventId == null || !eventId.matches("[A-Za-z0-9_-]{1,200}")) {
            throw new InvalidWebhookException();
        }

        Instant timestamp;
        try {
            timestamp = Instant.ofEpochSecond(
                    Long.parseLong(timestampHeader));
        } catch (RuntimeException ex) {
            throw new InvalidWebhookException();
        }

        if (Duration.between(timestamp, clock.instant()).abs()
                .compareTo(tolerance) > 0) {
            throw new StaleWebhookException();
        }

        if (signatureHeader == null
                || !signatureHeader.startsWith("v1=")) {
            throw new InvalidWebhookException();
        }

        byte[] supplied;
        try {
            supplied = HexFormat.of().parseHex(
                    signatureHeader.substring(3));
        } catch (IllegalArgumentException ex) {
            throw new InvalidWebhookException();
        }

        if (supplied.length != 32) {
            throw new InvalidWebhookException();
        }

        byte[] secret = activeSecrets.get(keyId);
        if (secret == null) {
            throw new InvalidWebhookException();
        }

        byte[] message;
        byte[] expected;
        try {
            message = WebhookMac.canonicalMessage(
                    "v1", keyId, timestampHeader, eventId, rawBody);
            expected = WebhookMac.hmacSha256(secret, message);
        } catch (GeneralSecurityException | IOException ex) {
            throw new WebhookVerificationUnavailableException();
        }

        if (!MessageDigest.isEqual(expected, supplied)) {
            throw new InvalidWebhookException();
        }

        return new VerifiedWebhook(keyId, eventId, timestamp, rawBody);
    }
}
~~~

Ví dụ cần các import còn lại như GeneralSecurityException, IOException, Map và ByteArrayOutputStream. Trong ứng dụng thật, secret provider đọc key từ secret manager/KMS-backed configuration và trả về key material theo key ID. Không tạo Map secret bất biến trong source code hoặc commit secret vào Git.

Verifier kiểm tra timestamp trước HMAC để từ chối request cũ sớm. Nếu cần tránh tạo khác biệt quan sát được giữa lỗi timestamp và chữ ký, chuẩn hóa response code/body và rate limit. Không trả thông tin cho caller biết key ID nào đang hoạt động.

### 6.4. Nhận raw body trong controller

~~~java
@RestController
@RequestMapping("/webhooks/payment")
public class PaymentWebhookController {
    private final WebhookVerifier verifier;
    private final ObjectMapper objectMapper;
    private final PaymentEventService eventService;

    public PaymentWebhookController(
            WebhookVerifier verifier,
            ObjectMapper objectMapper,
            PaymentEventService eventService) {
        this.verifier = verifier;
        this.objectMapper = objectMapper;
        this.eventService = eventService;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Void> receive(
            @RequestHeader("X-Webhook-Key-Id") String keyId,
            @RequestHeader("X-Webhook-Timestamp") String timestamp,
            @RequestHeader("X-Webhook-Event-Id") String eventId,
            @RequestHeader("X-Webhook-Signature") String signature,
            @RequestBody byte[] rawBody) throws IOException {

        VerifiedWebhook verified = verifier.verify(
                keyId, timestamp, eventId, signature, rawBody);

        PaymentEvent event = objectMapper.readValue(
                verified.rawBody(), PaymentEvent.class);

        eventService.accept(verified, event);
        return ResponseEntity.accepted().build();
    }
}
~~~

Controller chỉ parse JSON sau khi verifier thành công. Cấu hình giới hạn body ở reverse proxy/container; annotation hoặc kiểm tra trong controller không thay thế giới hạn ở tầng network. Nếu dùng filter để đọc body, phải bảo đảm body có thể được đọc lại hoặc dùng wrapper phù hợp.

### 6.5. Lưu ý về secret provider

- Lấy secret từ AWS Secrets Manager/Parameter Store, Azure Key Vault hoặc Google Secret Manager theo identity của workload.
- Dùng key ID không bí mật để chọn secret version.
- Không dùng cùng một secret cho nhiều tenant hoặc nhiều webhook provider nếu có thể tách.
- Có thể giữ current và previous secret trong khoảng overlap để xoay khóa.
- Giới hạn quyền đọc secret cho service cần xác minh.
- Không log secret, MAC, full authorization header hoặc raw body.
- Cache secret trong memory có TTL và refresh policy; không gọi secret manager cho từng request nếu latency/availability không cho phép.
- Khi key bị compromise, revoke/rotate và theo dõi request dùng key cũ.

## 7. Chống duplicate và xử lý nghiệp vụ idempotent

### 7.1. Inbox pattern

Một cách triển khai phổ biến:

1. Xác minh chữ ký và timestamp.
2. Parse event.
3. Tính hash payload.
4. Insert event ID vào inbox với unique constraint.
5. Nếu duplicate cùng payload, không chạy nghiệp vụ lại.
6. Nếu event mới, cập nhật domain state.
7. Ghi outbox event nếu cần phát message tiếp.
8. Commit transaction.
9. ACK sender sau khi event đã được lưu bền vững.

Ví dụ pseudo-code:

~~~java
@Transactional
public AcceptResult accept(
        VerifiedWebhook verified,
        PaymentEvent event) {

    byte[] payloadHash = sha256(verified.rawBody());

    boolean inserted = inboxRepository.insertIfAbsent(
            "payment-provider",
            "payment-endpoint",
            verified.eventId(),
            payloadHash);

    if (!inserted) {
        InboxRecord existing = inboxRepository.findRequired(
                "payment-provider",
                "payment-endpoint",
                verified.eventId());

        if (!MessageDigest.isEqual(
                existing.payloadHash(), payloadHash)) {
            throw new EventIdCollisionException();
        }

        return AcceptResult.DUPLICATE;
    }

    orderService.markPaidIdempotently(
            event.orderId(), event.paymentId(), event.amount());

    outboxRepository.save(
            OutboxEvent.invoiceRequested(event.orderId(), event.paymentId()));

    inboxRepository.markProcessed(
            "payment-provider", "payment-endpoint", verified.eventId());

    return AcceptResult.ACCEPTED;
}
~~~

Phương thức insertIfAbsent phải được thực hiện bằng INSERT có unique constraint và xử lý conflict tại database. Kiểm tra tồn tại bằng SELECT rồi INSERT là không an toàn khi hai instance nhận cùng lúc.

### 7.2. Transaction và side effect bên ngoài

Nếu update database và gửi message ra broker trong cùng method nhưng không có distributed transaction, có thể xảy ra:

- DB commit nhưng publish thất bại.
- Publish thành công nhưng DB rollback.
- Retry tạo side effect trùng.

Dùng **Transactional Outbox**: ghi trạng thái nghiệp vụ và outbox record trong cùng database transaction; worker riêng publish outbox và đánh dấu đã gửi. Consumer tiếp tục idempotent vì publish vẫn có thể lặp.

Nếu gọi payment provider, email hoặc dịch vụ bên ngoài, dùng idempotency key ở API đích nếu được hỗ trợ. Không giả định transaction của database bao phủ HTTP call.

### 7.3. ACK khi nào?

Chỉ trả 2xx sau khi:

- Chữ ký/token đã xác minh.
- Event được ghi bền vững vào inbox hoặc đã xử lý transactionally.
- Hệ thống có thể phục hồi tiếp tục xử lý sau restart.

Nếu trả 2xx trước khi persist, process có thể chết và sender nghĩ event đã nhận thành công trong khi event mất. Với xử lý lâu, persist inbox rồi trả 202/204 theo contract; worker xử lý bất đồng bộ.

Nếu database tạm thời không khả dụng, trả lỗi retriable theo contract để sender retry. Đừng ACK rồi bỏ event.

### 7.4. Idempotency ở domain layer

Inbox ngăn một event ID lặp, nhưng cùng một hành động có thể được gửi với event ID khác nhau. Domain operation cũng nên idempotent:

- Unique constraint cho payment ID/transaction reference.
- Chuyển trạng thái theo state machine hợp lệ.
- Không tạo invoice nếu invoice đã tồn tại cho payment.
- Không cộng tiền nhiều lần; lưu ledger transaction với unique business key.
- Không chỉ dựa vào event ID để bảo vệ logic tài chính.

### 7.5. Giữ idempotency record đủ lâu

Retention inbox cần bao phủ retry window của sender và yêu cầu audit. Nếu provider có thể retry nhiều giờ/ngày, không xóa record sau vài phút. Có thể partition theo ngày hoặc chuyển payload cũ sang archive nhưng giữ event ID/hash tombstone.

## 8. Xử lý retry và thứ tự sự kiện

### 8.1. Mã HTTP và retry

Mỗi provider có quy tắc riêng. Thông thường:

- 2xx: xác nhận đã nhận.
- 4xx: có thể bị coi là lỗi cấu hình hoặc không retry, tùy provider.
- 5xx/timeout: thường được retry với backoff.
- Response phải nhanh; xử lý nặng nên chuyển sang background worker sau khi persist.

Không giả định 401/403 luôn được retry. Một số dịch vụ coi đó là lỗi cấu hình và ngừng delivery hoặc dead-letter.

### 8.2. Out-of-order

Dùng version/sequence của resource:

~~~text
orderId=ORD-1001, version=12, status=PAID
orderId=ORD-1001, version=13, status=REFUNDED
~~~

Nếu version 13 đến trước version 12, service có thể lưu trạng thái version 13 và bỏ qua event cũ version 12. Nếu có gap, fetch current state từ API nguồn hoặc buffer event chờ phiên bản thiếu tùy nghiệp vụ.

Timestamp event không luôn là thứ tự tuyệt đối: clock sender có thể lệch, event có thể được tạo bởi nhiều service hoặc replay. Ưu tiên monotonic version/sequence do domain owner phát hành.

### 8.3. Dead-letter queue

DLQ giữ event không xử lý được sau retry limit hoặc TTL. Cần:

- Phân loại lỗi transient và permanent.
- Alert khi DLQ tăng.
- Giữ original event ID và metadata để điều tra.
- Có quy trình replay có kiểm soát.
- Replay vẫn đi qua signature/authentication hoặc một đường replay nội bộ được audit.
- Không bypass idempotency khi replay.
- Không đưa secret hoặc payload restricted vào ticket/log.

## 9. AWS: SNS signatures và EventBridge delivery

### 9.1. Amazon SNS HTTP/S notifications

Amazon SNS ký notification và gửi signature cùng SigningCertURL:

- SignatureVersion 1 dùng SHA-1 with RSA.
- SignatureVersion 2 dùng SHA-256 with RSA và được khuyến nghị.
- Chữ ký bao phủ các trường message theo loại notification, gồm Message, MessageId, Subject nếu có, Type, Timestamp và TopicArn.
- Receiver cần xác minh certificate chain và chữ ký trước khi xử lý.
- Chỉ chấp nhận TopicArn dự kiến; không nhận mọi topic chỉ vì chữ ký hợp lệ.

Nên dùng AWS SDK hỗ trợ xác minh SNS thay vì tự dựng canonical string. Nếu tự xử lý SigningCertURL, chỉ tải certificate qua HTTPS từ domain SNS AWS được cho phép theo region; xác minh chain/issuer và không fetch URL tùy ý từ payload vì có thể tạo SSRF.

Notification confirmation/unsubscribe cũng cần được xác minh theo loại message. Không tự động truy cập UnsubscribeURL chỉ vì nó xuất hiện trong payload.

### 9.2. EventBridge

EventBridge gửi event tới target theo retry policy và có thể giao ít nhất một lần. Khi target là API destination, cấu hình Connection để quản lý API key, Basic hoặc OAuth authorization theo khả năng dịch vụ. HTTPS và authentication ở endpoint vẫn cần được cấu hình.

- EventBridge không biến mọi HTTP target thành webhook HMAC.
- Authentication của API destination là lớp xác thực request tới endpoint.
- Event ID và idempotency vẫn cần để xử lý duplicate.
- Cấu hình retry policy và DLQ cho target.
- Không giả định event luôn đến đúng thứ tự.

Service event delivery vào EventBridge có thể là best effort hoặc durable tùy dịch vụ nguồn; durable có nghĩa cố gắng giao ít nhất một lần. Phân biệt delivery vào EventBridge với delivery từ EventBridge tới target.

### 9.3. Hướng xử lý trong Spring Boot

Với SNS, endpoint xác minh signature bằng thư viện AWS SNS/SDK phù hợp, kiểm tra TopicArn và message type trước khi parse message nghiệp vụ. Với EventBridge API destination, xác minh API key/OAuth token theo Connection đã cấu hình, sau đó kiểm tra event envelope, source, detail-type và event ID.

Không dùng một HMAC verifier tự thiết kế cho SNS nếu provider đã có định dạng RSA signature riêng.

## 10. Azure Event Grid

### 10.1. Endpoint validation handshake

Khi đăng ký webhook endpoint, Event Grid yêu cầu xác minh endpoint ownership. Với Event Grid event schema, endpoint nhận validation event và trả lại validation response đúng contract. Đây là handshake xác nhận endpoint có chủ sở hữu dự kiến; nó không phải chữ ký xác minh từng event payload.

Phải xử lý validation event riêng và không gửi validation event vào nghiệp vụ đơn hàng. Validation URL có thời hạn; hoàn thành handshake trong thời gian provider quy định.

### 10.2. Xác thực delivery bằng Microsoft Entra ID

Event Grid có thể bảo vệ delivery tới webhook bằng Microsoft Entra ID:

- Cấu hình ứng dụng/identity đích và audience/resource.
- Cấp role phù hợp cho service principal mà Event Grid sử dụng.
- Endpoint xác minh bearer token, issuer, audience, thời hạn và quyền.
- Không chỉ kiểm tra token tồn tại trong Authorization header.

Cơ chế này xác thực service gửi request. Nếu ứng dụng cần xác minh thêm tính toàn vẹn payload theo một hợp đồng riêng, phải dùng signature/MAC riêng; đừng coi endpoint validation handshake là payload signature.

### 10.3. Delivery, duplicate và ordering

Event Grid giao event theo at-least-once và không bảo đảm thứ tự. Endpoint có thể nhận duplicate, kể cả khi trước đó đã trả thành công trong một số tình huống. Dùng event ID của Event Grid làm idempotency key, kết hợp subscription/provider scope.

Cấu hình retry, TTL và dead-letter destination. Theo tài liệu hiện hành, một số lỗi webhook như 400, 401, 403 hoặc 413 có thể không được retry; xác định status code phù hợp để tránh bỏ event do lỗi cấu hình. Không trả 2xx cho event chưa được persist.

## 11. Google Cloud Pub/Sub push subscriptions

### 11.1. JWT authentication

Nếu push subscription bật authentication, Pub/Sub ký một OIDC JWT và gửi trong Authorization header. Receiver phải xác minh:

- Chữ ký JWT bằng public key tin cậy của issuer.
- Issuer theo cấu hình Pub/Sub/OIDC.
- Audience khớp chính xác audience đã cấu hình cho push endpoint.
- exp và các claim thời gian.
- Email/service account claim đúng service account được cấu hình và email_verified là true khi contract yêu cầu.

Không chỉ decode token hoặc kiểm tra email claim mà bỏ qua chữ ký. Không dùng audience mặc định rộng nếu endpoint có audience cụ thể.

### 11.2. Message ID và duplicate

Pub/Sub push envelope có message ID và subscription metadata. Dùng message ID cùng subscription/provider scope làm idempotency key. Pub/Sub có thể redeliver nếu endpoint trả negative acknowledgment hoặc acknowledgment deadline hết hạn.

Exactly-once delivery của Pub/Sub chỉ hỗ trợ pull subscriptions, không áp dụng cho push subscriptions. Ngay cả khi dùng pull exactly-once, publisher có thể tạo hai message khác ID cho cùng một ý định nghiệp vụ; domain idempotency vẫn cần thiết.

### 11.3. ACK và xử lý

Với push, trả HTTP status thành công theo contract của Pub/Sub để ACK. Trả status không thành công hoặc không phản hồi có thể làm message được gửi lại. Persist event trước khi ACK; xử lý bất đồng bộ qua inbox/worker khi tác vụ dài.

Không nhầm JWT xác thực push request với chữ ký trên từng message payload. JWT xác minh Pub/Sub service identity; event ID/idempotency kiểm soát xử lý lặp.

## 12. So sánh ba cloud provider

| Tiêu chí | AWS SNS / EventBridge | Azure Event Grid | Google Cloud Pub/Sub push |
| --- | --- | --- | --- |
| Cơ chế xác thực tiêu biểu | SNS RSA signature; EventBridge API destination Connection | Endpoint validation handshake; Microsoft Entra ID delivery auth | OIDC JWT trong Authorization header |
| Xác minh payload | SNS signature trên các field theo message type; EventBridge envelope + endpoint auth | Entra xác thực service; handshake không phải payload signature | JWT xác thực publisher service; message body là envelope Pub/Sub |
| Chống duplicate | MessageId/event ID + inbox | Event ID + inbox | Message ID + subscription + inbox |
| Delivery semantics | Durable service event có at-least-once; target có retry | At-least-once | Push redelivery khi NACK/ack deadline |
| Ordering | Không nên giả định thứ tự | Không bảo đảm thứ tự | Không mặc định bảo đảm thứ tự |
| Exactly-once | Không mặc định ở HTTP target | Không | Chỉ pull subscription có hỗ trợ; không phải push |
| Recovery | Retry policy + DLQ | Retry policy + dead-letter | Retry/redelivery + dead-letter topic |
| Trách nhiệm ứng dụng | Verify provider auth, validate source, idempotency | Validate endpoint setup, token, event ID, idempotency | Verify JWT claims, event ID, idempotency |

Provider có thể thay đổi tính năng theo API, region và cấu hình. Kiểm tra tài liệu đúng dịch vụ và endpoint type đang dùng; không suy rộng một tính năng từ SNS sang EventBridge hoặc từ Pub/Sub pull sang push.

## 13. Xoay vòng secret và quản lý khóa xác minh

### 13.1. Rotation không được làm gián đoạn retry

Khi đổi webhook secret:

1. Tạo secret mới và key ID mới.
2. Cấu hình receiver chấp nhận key mới và key cũ trong overlap window.
3. Cập nhật sender dùng key mới.
4. Theo dõi request theo key ID.
5. Chờ hết retry window và thời gian chuyển đổi.
6. Thu hồi key cũ.
7. Kiểm thử request ký bằng key cũ bị từ chối sau khi hết overlap.

Nếu provider hỗ trợ hai signing secret đồng thời, dùng cơ chế rotation của provider. Không lưu raw secret trong database cùng event payload.

### 13.2. Key ID không phải secret

Key ID giúp receiver chọn đúng secret/public key. Nó có thể xuất hiện trong header hoặc metadata. Không dùng key ID làm bằng chứng xác thực; chữ ký phải hợp lệ với key tương ứng.

### 13.3. Quản lý public key và certificate

Với chữ ký RSA/ECDSA:

- Pin issuer/host và trust chain theo provider.
- Cache certificate/public key theo hướng dẫn provider, có TTL và refresh.
- Hỗ trợ key rotation bằng key ID hoặc certificate metadata.
- Không fetch URL certificate tùy ý từ request.
- Kiểm tra algorithm và key type được phép.
- Khi key bị thu hồi, xử lý request cũ theo policy và audit.

### 13.4. Bảo vệ secret và observability

Không ghi:

- HMAC secret hoặc private key.
- Authorization header, JWT đầy đủ hoặc refresh token.
- Signature đầy đủ.
- Raw webhook body nếu chứa PII/secret.
- Certificate URL không được lọc nếu có nguy cơ chứa dữ liệu không tin cậy.

Có thể ghi event ID, provider, key ID, timestamp, verification outcome, body hash, latency và correlation ID. Giới hạn quyền đọc audit log và retention theo classification.

## 14. Các lỗi triển khai phổ biến

| Lỗi | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| Parse JSON rồi serialize lại để tính HMAC | Byte representation thay đổi | Xác minh raw body theo spec |
| Chỉ kiểm tra IP sender | IP có thể thay đổi, shared egress hoặc bị giả trong header | Chữ ký/JWT + network restriction như lớp bổ sung |
| Chỉ kiểm tra timestamp | Replay vẫn xảy ra trong tolerance window | Event ID/nonce store có unique constraint |
| Chỉ dùng event ID trong memory | Nhiều instance/restart làm mất trạng thái | Inbox bền vững trong database |
| Dùng SELECT rồi INSERT | Race condition khi duplicate đến đồng thời | Unique constraint và insert-if-absent |
| Dùng String.equals cho MAC | Có thể tạo timing leakage | Constant-time byte comparison |
| Không ký timestamp/event ID | Metadata có thể bị thay đổi | Ký canonical metadata cùng body |
| ACK trước khi persist | Event có thể mất khi process chết | Persist inbox rồi ACK |
| Side effect ngoài transaction | Retry có thể tạo hành động lặp | Outbox và idempotency ở domain/API đích |
| Xóa inbox quá sớm | Replay cũ được xử lý lại | Retention bao phủ retry và replay window |
| Giả định event có thứ tự | Trạng thái cũ ghi đè trạng thái mới | Aggregate version/sequence |
| Tin JWT chỉ vì decode thành công | Không xác minh chữ ký/issuer/audience | Dùng JWT verifier chuẩn và validate claims |
| Fetch certificate URL tùy ý | SSRF và trust certificate không đúng | Allowlist host, HTTPS, chain/issuer validation |
| Log raw body/signature | Làm lộ dữ liệu và credential | Redact, hash và structured audit |

## 15. Kiểm thử webhook và event endpoint

### 15.1. Kiểm thử chữ ký

- Payload hợp lệ và signature đúng được chấp nhận.
- Sửa một byte body làm verification thất bại.
- Sửa timestamp/event ID/key ID làm signature thất bại.
- Signature sai version hoặc sai encoding bị từ chối.
- Signature thiếu byte hoặc thừa byte bị từ chối.
- Body có Unicode, whitespace, newline và escaped character được xác minh trên đúng raw bytes.
- Key ID không tồn tại bị từ chối.
- Key cũ chỉ được chấp nhận trong rotation overlap window.

### 15.2. Kiểm thử freshness và replay

- Timestamp quá cũ bị từ chối.
- Timestamp tương lai vượt tolerance bị từ chối.
- Request hợp lệ gửi lần đầu được xử lý.
- Cùng event ID và cùng payload gửi lại không tạo side effect.
- Cùng event ID nhưng payload khác được đưa vào security handling.
- Hai request cùng event ID tới đồng thời chỉ một request claim được inbox.
- Nonce đã dùng bị từ chối theo protocol.
- Inbox record còn tồn tại trong toàn bộ retry window.

### 15.3. Kiểm thử nghiệp vụ

- Payment event không tạo invoice hai lần.
- Event version cũ không ghi đè trạng thái mới.
- DB transaction rollback không để event ở trạng thái processed giả.
- Outbox worker retry không publish side effect không idempotent.
- DLQ replay vẫn qua kiểm soát và audit.
- Tenant/resource trong event được authorization trước khi thay đổi dữ liệu.

### 15.4. Kiểm thử provider integration

- SNS signature version 2, certificate chain và TopicArn đúng.
- SNS certificate URL không thuộc AWS domain bị từ chối.
- Event Grid validation event được trả đúng response và không chạy nghiệp vụ.
- Event Grid Entra JWT sai audience/issuer/expiry bị từ chối.
- Pub/Sub push JWT sai audience hoặc service account bị từ chối.
- Pub/Sub push duplicate cùng message ID không xử lý lại.
- EventBridge retry/DLQ được thử trong môi trường test.
- HTTP ACK/NACK đúng contract của provider.

### 15.5. Kiểm thử bảo mật vận hành

- Request body vượt giới hạn bị từ chối trước khi tiêu tốn quá nhiều memory.
- Rate limit hoạt động khi signature invalid liên tục.
- Log không chứa raw secret, JWT, signature hoặc PII.
- Error response không tiết lộ key ID/secret validity chi tiết.
- Certificate fetching không thể bị điều khiển thành SSRF.
- Endpoint chỉ nhận HTTPS và có policy network phù hợp.
- Replay sau khi restart service vẫn bị chặn bởi inbox database.

## 16. Bài tập thực hành tổng hợp

order-service nhận webhook thanh toán từ provider. Khi thanh toán thành công, service cập nhật order, ghi payment ledger và phát sự kiện tạo invoice. Provider gửi webhook theo at-least-once và có thể retry trong nhiều giờ.

**Nhiệm vụ:**

1. Thiết kế HMAC-SHA256 protocol với key ID, timestamp, event ID và raw body.
2. Viết sender test helper để tạo signature đúng canonical bytes.
3. Viết verifier Spring Boot dùng MessageDigest.isEqual và timestamp tolerance.
4. Lưu webhook secret trong secret manager và hỗ trợ current/previous key rotation.
5. Tạo webhook inbox với unique key theo provider, endpoint và event ID.
6. Xử lý duplicate cùng payload như ACK an toàn; xử lý cùng ID khác payload như security incident.
7. Cập nhật order và payment ledger idempotently trong transaction.
8. Dùng transactional outbox để phát invoice request.
9. Xử lý event out-of-order bằng aggregate version hoặc sequence.
10. Mô phỏng request bị sửa, request cũ, replay, race condition, process restart và DLQ replay.
11. So sánh cách xác thực của SNS, Event Grid và Pub/Sub push.
12. Viết runbook khi signing secret hoặc provider signing key bị compromise.

**Câu hỏi tự đánh giá:**

- HMAC xác minh điều gì và không cung cấp điều gì?
- Vì sao phải xác minh raw request body trước khi parse JSON?
- Vì sao timestamp không đủ để chống replay?
- Event ID khác nonce và idempotency key ở đâu?
- Vì sao inbox cần unique constraint ở database?
- Vì sao trả 2xx trước khi persist event có thể làm mất dữ liệu?
- Transactional outbox giải quyết vấn đề gì?
- Vì sao duplicate delivery không nhất thiết là tấn công?
- AWS SNS SignatureVersion 2 dùng thuật toán gì?
- Event Grid endpoint validation handshake có phải payload signature không?
- Pub/Sub push JWT cần kiểm tra claim nào?
- Pub/Sub exactly-once delivery có áp dụng cho push subscription không?
- Vì sao không giả định event đến đúng thứ tự?
- Khi xoay secret, vì sao cần overlap window?

**Đáp án định hướng:** HMAC xác minh authenticity/integrity nhưng không mã hóa; raw bytes phải giữ nguyên để khớp chữ ký sender; timestamp chỉ giới hạn freshness, event ID/nonce store mới chặn replay đã nhận; event ID định danh event, nonce định danh request/message, idempotency key định danh thao tác; unique constraint xử lý race giữa nhiều instance; ACK trước persist có thể làm event mất; outbox đồng bộ commit DB với ý định publish; duplicate thường đến từ at-least-once retry; SNS v2 dùng SHA256withRSA; Event Grid handshake xác minh endpoint ownership; Pub/Sub push cần kiểm chữ ký JWT, issuer, audience, expiry và service account; exactly-once chỉ hỗ trợ pull; version/sequence giải quyết out-of-order; overlap cho sender chuyển key mà không làm retry hợp lệ thất bại.

## 17. Tài liệu tham khảo chính thức

- [Amazon SNS – Verifying message signatures](https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html): SignatureVersion 1/2, certificate validation, TopicArn và best practices.
- [Amazon SNS – Verifying message signature details](https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message-verify-message-signature.html): canonical fields, SigningCertURL và trusted AWS domain.
- [Amazon SNS – HTTP/S notification JSON format](https://docs.aws.amazon.com/sns/latest/dg/http-notification-json.html): SignatureVersion, Signature, SigningCertURL và MessageId.
- [Amazon EventBridge – Event delivery levels](https://docs.aws.amazon.com/eventbridge/latest/ref/event-delivery-level.html): best-effort và durable at-least-once delivery.
- [Amazon EventBridge – Retry policy](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-rule-retry-policy.html): retry attempts, exponential backoff và dead-letter queue.
- [Microsoft Learn – Event Grid endpoint validation](https://learn.microsoft.com/en-us/azure/event-grid/end-point-validation-event-grid-events-schema): validation handshake cho webhook endpoint.
- [Microsoft Learn – Secure Event Grid webhook delivery with Microsoft Entra ID](https://learn.microsoft.com/en-us/azure/event-grid/secure-webhook-delivery): xác thực service-to-service bằng Entra ID.
- [Microsoft Learn – Event Grid delivery and retry](https://learn.microsoft.com/en-us/azure/event-grid/delivery-and-retry): at-least-once, ordering, retry và dead-letter.
- [Google Cloud – Authenticate Pub/Sub push subscriptions](https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions): OIDC JWT, Authorization header, audience và service account claims.
- [Google Cloud – Pub/Sub push subscriptions](https://docs.cloud.google.com/pubsub/docs/push): ACK/NACK, push delivery và redelivery.
- [Google Cloud – Exactly-once delivery](https://docs.cloud.google.com/pubsub/docs/exactly-once-delivery): giới hạn exactly-once ở pull subscription và duplicate semantics.
- [RFC 2104 – HMAC](https://www.rfc-editor.org/rfc/rfc2104): định nghĩa HMAC và cách kết hợp hash với shared secret.
- [RFC 7519 – JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và claims.
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): nguyên tắc bảo vệ endpoint, authentication, validation và transport security.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu cần loại khỏi log, sanitization, quyền đọc và retention của audit log.

**Ghi nhớ:** chữ ký trả lời “ai tạo request và payload có bị sửa không”; timestamp trả lời “request còn mới không”; event ID/inbox trả lời “sự kiện này đã được tiếp nhận chưa”; domain idempotency trả lời “nghiệp vụ đã thực hiện chưa”. Muốn endpoint webhook an toàn, Spring Boot phải kết hợp cả bốn lớp và tuân thủ retry/authentication contract của từng provider.
