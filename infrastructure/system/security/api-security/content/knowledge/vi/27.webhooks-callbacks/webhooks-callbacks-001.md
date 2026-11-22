# Xác thực webhook bằng HMAC hoặc chữ ký

Webhook là cách một hệ thống gửi thông báo sự kiện tới endpoint của hệ thống khác. Ví dụ, payment provider gửi `payment.succeeded`, dịch vụ giao hàng gửi `shipment.updated`, hoặc một hệ thống SaaS gọi callback khi tác vụ hoàn tất. Vì endpoint webhook thường nhận request qua mạng và từ một hệ thống bên ngoài, receiver phải xác minh nguồn gửi và tính toàn vẹn của nội dung trước khi thực hiện nghiệp vụ.

Hai cách phổ biến để xác thực webhook là **HMAC với shared secret** và **chữ ký số bất đối xứng**. Với HMAC, sender và receiver cùng giữ một secret và tính mã xác thực trên dữ liệu được quy định. Với chữ ký bất đối xứng, sender ký bằng private key còn receiver xác minh bằng public key. Cả hai cách đều giúp phát hiện payload bị sửa và request không có chữ ký hợp lệ; chúng không tự mã hóa payload, không tự ngăn replay và không thay thế authorization theo tenant/object.

Trong API Security, webhook cần được xử lý như một API endpoint có trust boundary riêng. Server phải xác minh chữ ký trên đúng dữ liệu đã nhận, kiểm tra timestamp/delivery ID, ánh xạ key tới đúng integration, xác thực event type và tenant, rồi mới lưu hoặc thực hiện side effect. Không được coi một JSON payload có trường `source: "trusted-provider"` là bằng chứng nguồn gửi.

## 1. Webhook inbound và outbound

Webhook có hai chiều với trách nhiệm bảo mật khác nhau:

| Luồng | Ai gửi? | Ai xác minh chữ ký? | Mục tiêu chính |
|---|---|---|---|
| Inbound webhook | Provider/đối tác gọi API của hệ thống | Hệ thống nhận | Chứng minh request đến từ sender được cấu hình và payload không bị sửa |
| Outbound webhook | Hệ thống gửi event tới URL subscriber | Hệ thống nhận ở phía đối tác | Cho phép receiver xác minh event do hệ thống phát hành |

Ví dụ inbound: Payment Provider gửi event thanh toán. Payment API cần xác minh chữ ký provider trước khi đánh dấu invoice là đã thanh toán.

Ví dụ outbound: Order Service gửi `order.shipped` tới URL webhook do tenant đăng ký. Order Service cần ký payload bằng secret riêng của subscription để receiver xác minh nguồn và nội dung.

Hai luồng có thể dùng cùng nguyên tắc mật mã nhưng key lifecycle, retry, URL validation và quyền sở hữu endpoint khác nhau. Tài liệu provider đã chọn luôn là nguồn chuẩn cho thuật toán, header, canonical payload và cách xoay key; không tự thay giao thức của provider bằng một biến thể riêng.

## 2. HMAC và chữ ký bất đối xứng khác nhau thế nào?

### HMAC với shared secret

HMAC (Hash-based Message Authentication Code) kết hợp một secret với hàm hash mật mã, thường là SHA-256. Sender và receiver cùng có secret nên có thể tính và xác minh cùng một MAC.

Ưu điểm:

- Dễ triển khai và có hiệu năng tốt.
- Phù hợp với webhook giữa hai hệ thống đã thiết lập quan hệ tin cậy và có thể trao đổi secret an toàn.
- Receiver không cần lưu private/public key pair.

Giới hạn:

- Cả sender và receiver đều có khả năng tạo chữ ký hợp lệ vì cùng giữ secret.
- Nếu secret bị lộ ở một phía, attacker có thể giả mạo webhook.
- Khó mở rộng khi nhiều receiver cần xác minh nhưng không nên được quyền ký event.

HMAC chứng minh người gửi có khả năng sử dụng secret, không cung cấp non-repudiation (không thể phủ nhận) như mô hình chữ ký bất đối xứng trong các điều kiện phù hợp.

### Chữ ký số bất đối xứng

Sender ký bằng private key. Receiver chỉ cần public key tương ứng để xác minh. Các thuật toán thường gặp tùy giao thức gồm Ed25519, ECDSA hoặc RSA-PSS.

Ưu điểm:

- Receiver không giữ private key và không thể tạo chữ ký thay sender.
- Một public key có thể được phân phối tới nhiều receiver.
- Phù hợp khi có nhiều consumer cần xác minh event do một publisher phát hành.

Giới hạn:

- Quản lý key pair, key ID, rotation và trust store phức tạp hơn.
- Phải xác minh public key đến từ nguồn tin cậy, không lấy key tùy ý từ URL do request cung cấp.
- Việc verify chữ ký vẫn không ngăn replay nếu không có timestamp/nonce/deduplication.

| Tiêu chí | HMAC | Chữ ký bất đối xứng |
|---|---|---|
| Key dùng để ký | Shared secret | Private key |
| Key dùng để xác minh | Cùng shared secret | Public key |
| Receiver có thể tạo chữ ký hợp lệ? | Có | Không, nếu chỉ giữ public key |
| Phân phối key | Phải giữ secret ở cả hai phía | Phân phối public key, bảo vệ private key ở sender |
| Phù hợp | Tích hợp hai bên, số lượng receiver hạn chế | Publisher có nhiều receiver hoặc cần tách quyền ký và quyền xác minh |
| Rủi ro chính | Secret bị lộ ở bất kỳ bên nào | Private key compromise hoặc public key trust bị giả mạo |

Chọn thuật toán theo giao thức provider, năng lực key management và mô hình tin cậy. Không tự chọn thuật toán yếu hơn chỉ vì thư viện có sẵn; cũng không tự thay đổi thuật toán của đối tác.

## 3. Chữ ký bảo vệ gì và không bảo vệ gì?

Chữ ký hợp lệ có thể chứng minh rằng dữ liệu được ký không bị thay đổi sau khi ký và người tạo chữ ký có quyền sử dụng key tương ứng. Tuy nhiên, chữ ký không cung cấp tất cả thuộc tính bảo mật:

- **Không mã hóa:** người quan sát vẫn có thể đọc payload nếu dữ liệu không được bảo vệ bằng TLS hoặc cơ chế mã hóa riêng.
- **Không tự chống replay:** một request hợp lệ bị ghi lại có thể được gửi lại.
- **Không tự bảo đảm đúng tenant:** key hợp lệ phải được ánh xạ tới integration/tenant cụ thể và payload phải khớp phạm vi đó.
- **Không chứng minh event đúng về nghiệp vụ:** provider có thể ký một event hợp lệ nhưng trạng thái local đã thay đổi hoặc event không còn được phép áp dụng.
- **Không tự bảo vệ khỏi duplicate delivery:** sender có thể retry cùng event nhiều lần.
- **Không thay thế authentication của transport hoặc authorization của API:** TLS, workload identity, function/object policy và audit vẫn cần thiết theo kiến trúc.

Vì vậy, quy trình đúng không dừng ở `verifySignature() == true`. Sau xác minh mật mã, receiver còn phải kiểm tra timestamp, delivery ID, integration state, event type, tenant, object reference và business state.

## 4. Ký đúng raw request body

Một trong những lỗi phổ biến nhất là receiver parse JSON rồi serialize lại trước khi tính HMAC. Cùng một JSON object có thể được biểu diễn bằng nhiều chuỗi bytes khác nhau:

```json
{"event":"invoice.paid","amount":1200}
```

```json
{
  "amount": 1200,
  "event": "invoice.paid"
}
```

Hai payload có thể mang cùng dữ liệu logic nhưng bytes khác nhau do thứ tự field và whitespace. Nếu sender ký raw bytes mà receiver ký JSON đã serialize lại, digest sẽ không khớp.

Nguyên tắc:

- Sender ký chính xác bytes sẽ gửi qua HTTP.
- Receiver lấy raw body bytes trước khi deserialize.
- Hai bên thống nhất encoding, thứ tự thành phần, separator và signature version.
- Không trim, đổi newline, đổi charset hoặc canonicalize theo cách riêng trước khi verify.
- Gateway, proxy và middleware không được biến đổi body trước verifier, trừ khi giao thức định nghĩa canonicalization rõ ràng.
- Giới hạn body size trước khi đọc toàn bộ payload vào memory.

Nếu provider quy định ký một canonical string gồm timestamp, method, path hoặc một số header, receiver phải tạo đúng chuỗi theo tài liệu của provider. Không giả định mọi webhook chỉ ký body.

## 5. Ví dụ định dạng HMAC minh họa

Một giao thức tự thiết kế có thể quy định các header:

```http
X-Webhook-Key-Id: whk_2026_02
X-Webhook-Timestamp: 1794992400
X-Webhook-Id: delivery-8f31
X-Webhook-Signature: v1=4f9a...hex-digest...
Content-Type: application/json
```

Ví dụ này sử dụng chuỗi ký:

```text
v1:{timestamp}:{delivery_id}:{raw_body_bytes}
```

và MAC:

\[
MAC = HMAC\text{-}SHA256(secret, signed\_payload)
\]

Sender minh họa bằng Python:

```python
import hashlib
import hmac
import time

timestamp = str(int(time.time()))
delivery_id = "delivery-8f31"
raw_body = b'{"event":"invoice.paid","invoiceId":"inv-123"}'

signed_payload = (
    b"v1:" + timestamp.encode("ascii") + b":"
    + delivery_id.encode("ascii") + b":" + raw_body
)
digest = hmac.new(secret, signed_payload, hashlib.sha256).hexdigest()
signature_header = "v1=" + digest
```

Đây chỉ là giao thức minh họa để giải thích nguyên tắc. Sender và receiver phải thống nhất chính xác version, header name, encoding, thuật toán, cách biểu diễn digest và thành phần được ký. Khi tích hợp provider, dùng đúng thuật toán/header/canonical payload của provider.

`Key-Id` là selector để tìm key đã đăng ký; nó không phải bằng chứng xác thực. `Timestamp` giúp giới hạn tuổi request. `Delivery-Id` giúp nhận diện cùng một event qua nhiều lần retry. Trong ví dụ này, cả timestamp và delivery ID đều nằm trong chuỗi được ký. Nếu delivery ID chỉ là header không được ký, attacker có thể đổi ID để né deduplication dù body vẫn hợp lệ. Giao thức thật phải ký delivery ID hoặc dùng event ID nằm trong payload đã ký. Nếu cùng một key được dùng cho nhiều endpoint hoặc method, cân nhắc đưa method, path/endpoint ID và audience vào canonical payload để chữ ký không bị tái sử dụng ở route khác; chỉ làm theo format đã thống nhất với sender.

## 6. Xác minh HMAC bằng Java

Ví dụ dưới đây sử dụng Java 17, HMAC-SHA256 và digest biểu diễn bằng hexadecimal. Secret phải được lấy từ secret manager theo integration/key ID đã được server ánh xạ; không lấy secret từ payload hoặc URL.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

final class WebhookHmacVerifier {
    private static final long TOLERANCE_SECONDS = 300;
    private static final int SHA256_BYTES = 32;

    void verify(
            byte[] rawBody,
            String timestampHeader,
            String deliveryId,
            String signatureHeader,
            byte[] secret,
            Instant now) {

        if (rawBody == null || rawBody.length > 1_000_000) {
            throw new InvalidWebhookException();
        }

        long timestamp;
        try {
            if (timestampHeader == null
                    || !timestampHeader.matches("[0-9]{1,12}")) {
                throw new NumberFormatException();
            }
            timestamp = Long.parseLong(timestampHeader);
        } catch (NumberFormatException ex) {
            throw new InvalidWebhookException();
        }

        long nowSeconds = now.getEpochSecond();
        if (timestamp < nowSeconds - TOLERANCE_SECONDS
                || timestamp > nowSeconds + TOLERANCE_SECONDS) {
            throw new InvalidWebhookException();
        }

        if (signatureHeader == null
                || !signatureHeader.startsWith("v1=")) {
            throw new InvalidWebhookException();
        }

        if (deliveryId == null
                || !deliveryId.matches("[A-Za-z0-9._-]{1,200}")) {
            throw new InvalidWebhookException();
        }

        byte[] supplied;
        try {
            supplied = HexFormat.of().parseHex(
                    signatureHeader.substring(3));
        } catch (IllegalArgumentException ex) {
            throw new InvalidWebhookException();
        }

        if (supplied.length != SHA256_BYTES) {
            throw new InvalidWebhookException();
        }

        byte[] prefix = ("v1:" + timestampHeader + ":" + deliveryId + ":")
                .getBytes(StandardCharsets.US_ASCII);
        byte[] signedPayload = new byte[prefix.length + rawBody.length];
        System.arraycopy(prefix, 0, signedPayload, 0, prefix.length);
        System.arraycopy(rawBody, 0, signedPayload, prefix.length,
                rawBody.length);

        byte[] expected = calculateHmac(secret, signedPayload);
        if (!MessageDigest.isEqual(expected, supplied)) {
            throw new InvalidWebhookException();
        }
    }

    private byte[] calculateHmac(byte[] secret, byte[] payload) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            return mac.doFinal(payload);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("HMAC unavailable", ex);
        }
    }
}
```

Đây là ví dụ nền tảng, cần điều chỉnh theo giao thức thật:

- `TOLERANCE_SECONDS` phải theo policy/provider và có giới hạn cấu hình.
- `rawBody` cần được giới hạn ở gateway/server trước khi đọc vào memory.
- `Key-Id` phải được xác minh và ánh xạ tới secret của đúng integration.
- Timestamp và raw body phải được ký theo đúng canonical format của sender.
- Secret cần có entropy đủ mạnh và được lưu trong secret manager.
- Sau verify phải thực hiện delivery deduplication bền vững trước side effect.
- Lỗi xác minh nên trả response chung; không tiết lộ key tồn tại hay chi tiết nội bộ.

Ví dụ dùng `MessageDigest.isEqual` để so sánh byte array, tránh so sánh chuỗi thông thường có thể dừng tại vị trí khác nhau. Không log secret, raw signature hoặc payload nhạy cảm.

## 7. Xác minh chữ ký bất đối xứng

Với chữ ký số, sender tạo chữ ký bằng private key trên canonical payload. Receiver lấy public key đã tin cậy, xác minh chữ ký rồi mới xử lý event.

Ví dụ Ed25519 trong Java:

```java
import java.security.PublicKey;
import java.security.Signature;

boolean verifyEd25519(
        PublicKey trustedPublicKey,
        byte[] signedPayload,
        byte[] signatureBytes) {
    try {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(trustedPublicKey);
        verifier.update(signedPayload);
        return verifier.verify(signatureBytes);
    } catch (GeneralSecurityException ex) {
        throw new InvalidWebhookException();
    }
}
```

Public key trong ví dụ phải đến từ trust store hoặc key registry được cấu hình an toàn. Không lấy URL public key tùy ý từ request body/header rồi tự động tải về để xác minh; attacker có thể thay key bằng key do họ kiểm soát.

Nếu provider công bố JWKS hoặc endpoint key rotation, hãy dùng hostname/issuer đã cấu hình, kiểm tra TLS và cache key theo hướng dẫn chính thức. `kid` chỉ giúp chọn key trong tập key đã tin cậy. Không chấp nhận thuật toán do request tự chọn; verifier phải có allowlist thuật toán và key type tương ứng.

Với RSA/ECDSA, cần khớp đúng padding/curve/hash và encoding chữ ký mà provider quy định. Ví dụ RSA-PSS và RSA PKCS#1 v1.5 là các scheme khác nhau; không tự đổi giữa chúng. Với ECDSA, chú ý định dạng chữ ký DER hay raw `r || s` theo contract.

## 8. Chống replay bằng timestamp và delivery ID

Một attacker có thể ghi lại webhook hợp lệ rồi gửi lại. Chữ ký vẫn đúng vì payload và signature không thay đổi. Hai lớp thường dùng để giảm rủi ro:

1. **Timestamp tolerance:** chỉ chấp nhận chữ ký được tạo trong một cửa sổ thời gian hữu hạn.
2. **Delivery ID/nonce deduplication:** không xử lý lại cùng một delivery đã được tiếp nhận.

Ví dụ tolerance 5 phút:

\[
|now - timestamp| \leq 300\ seconds
\]

Con số 5 phút chỉ là minh họa. Chọn cửa sổ dựa trên clock drift, độ trễ mạng, provider retry schedule và thời hạn chữ ký. Đồng hồ sender/receiver cần đồng bộ.

Timestamp phải nằm trong nội dung được ký. Nếu timestamp chỉ là header không được ký, attacker có thể thay nó để kéo dài thời gian replay. Timestamp cũng không đủ một mình: request cũ vẫn có thể được gửi lại trong cửa sổ còn hiệu lực.

Delivery ID cần ổn định qua các lần retry của cùng một event. Nếu sender tạo ID mới cho mỗi lần retry, receiver sẽ không nhận ra đó là cùng event. Nếu provider có cả `event_id` và `delivery_id`, cần hiểu rõ ID nào ổn định qua retry và dùng đúng trường cho deduplication.

## 9. Lưu delivery ID một cách nguyên tử

Có thể lưu webhook inbox với unique key theo integration và delivery ID:

```sql
CREATE TABLE webhook_inbox (
    integration_id UUID NOT NULL,
    delivery_id VARCHAR(200) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    received_at TIMESTAMP NOT NULL,
    processed_at TIMESTAMP NULL,
    processing_status VARCHAR(30) NOT NULL,
    PRIMARY KEY (integration_id, delivery_id)
);
```

Sau khi chữ ký hợp lệ:

1. Tính hash payload để phát hiện trường hợp cùng ID nhưng body khác.
2. Insert inbox record bằng transaction và unique constraint.
3. Ghi event/outbox command cùng transaction nếu cần xử lý bất đồng bộ.
4. Commit rồi mới trả acknowledgement thành công.
5. Nếu ID đã tồn tại và hash giống nhau, coi là duplicate delivery; không chạy side effect lần nữa.
6. Nếu ID đã tồn tại nhưng hash khác, không ghi đè; cách ly và phát cảnh báo.

Không dùng mô hình `SELECT` kiểm tra trước rồi `INSERT` sau mà không có unique constraint. Hai request đồng thời có thể cùng thấy ID chưa tồn tại và cùng thực hiện nghiệp vụ. Unique constraint là lớp bảo vệ nguyên tử cuối cùng.

Giữ deduplication record lâu hơn thời gian sender có thể retry và thời gian timestamp còn được chấp nhận. Cache có thể tăng tốc nhưng không nên là nguồn duy nhất nếu cache có thể mất dữ liệu hoặc evict record trước hạn.

## 10. Replay protection, duplicate delivery và idempotency

Ba khái niệm liên quan nhưng không đồng nghĩa:

- **Replay protection:** ngăn request cũ bị chấp nhận lại trong cửa sổ thời gian.
- **Duplicate delivery handling:** nhận biết sender giao lại cùng event do retry hoặc không nhận được acknowledgement.
- **Idempotency:** bảo đảm xử lý lặp không tạo thêm side effect hoặc kết quả khác ngoài dự kiến.

Webhook thường có semantics at-least-once. Sender có thể retry nếu receiver timeout sau khi đã lưu event. Worker cũng có thể crash sau khi gọi payment provider nhưng trước khi đánh dấu event đã xử lý. Vì vậy cần idempotency ở cả inbox và nghiệp vụ/downstream.

Ví dụ với `payment.succeeded`, không chỉ đánh dấu delivery ID đã xử lý. Hãy có unique constraint theo provider transaction ID hoặc idempotency key nghiệp vụ để không cộng tiền hoặc ghi sổ hai lần.

Không tuyên bố exactly-once chỉ vì có chữ ký và delivery ID. Mạng, queue và worker có thể giao lặp; mục tiêu thực tế là xử lý at-least-once với side effect idempotent.

## 11. Ánh xạ key tới đúng integration và tenant

Mỗi secret/public key phải thuộc một integration hoặc sender đã đăng ký. Receiver cần có mapping server-side:

```text
key_id -> provider/integration -> tenant_id -> allowed_event_types
```

Không chọn tenant hoặc secret dựa trên `tenantId` trong JSON body. Payload có thể chứa tenant reference để đối chiếu, nhưng nguồn quyết định phải là integration đã xác minh.

Sau khi verify:

- Kiểm tra integration còn active và chưa bị revoke/offboard.
- Kiểm tra event type nằm trong allowlist của integration.
- Kiểm tra event schema/version được hỗ trợ.
- Kiểm tra object reference thuộc đúng tenant.
- Kiểm tra action/event phù hợp trạng thái nghiệp vụ.
- Kiểm tra provider account, merchant, subscription hoặc customer reference khớp integration.

Một key dùng cho `invoice.paid` không tự động được phép phát `tenant.deleted` hoặc `user.role_changed`. Có thể tách key theo endpoint hoặc event group để giới hạn phạm vi khi một secret bị lộ.

## 12. Xoay vòng và thu hồi key

Webhook key có thể bị lộ qua cấu hình, log, ticket hỗ trợ hoặc máy chủ đối tác. Cần có quy trình rotate/revoke:

1. Tạo key mới bằng cryptographically secure random generator hoặc tạo key pair trong HSM/KMS.
2. Lưu key mới trong secret manager/key registry và gắn `key_id` mới.
3. Cấu hình sender ký bằng key mới; receiver có thể chấp nhận key cũ và mới trong khoảng overlap ngắn đã phê duyệt.
4. Xác minh delivery test bằng key mới.
5. Thu hồi key cũ sau khi migration hoàn tất hoặc ngay lập tức nếu key bị compromise.
6. Xác minh request dùng key cũ bị từ chối.
7. Ghi audit actor, integration, key ID, thời điểm và kết quả.

Với HMAC, raw secret không được lưu trong source code, file cấu hình công khai hoặc database plaintext. Chỉ lưu secret reference/hash phù hợp và truy cập giá trị qua secret manager. Với chữ ký bất đối xứng, private key chỉ ở sender; receiver quản lý public key và trust metadata.

Không thử mọi key trong hệ thống khi `key_id` không tồn tại. Key lookup phải giới hạn trong integration/endpoint đã xác định và không tạo oracle tiết lộ key nào đang active.

## 13. Inbound webhook trong Spring: xác minh trước khi xử lý

Controller cần nhận raw body bytes để verifier dùng đúng nội dung:

```java
@RestController
@RequestMapping("/webhooks")
@RequiredArgsConstructor
class ProviderWebhookController {
    private final WebhookKeyResolver keyResolver;
    private final WebhookHmacVerifier verifier;
    private final WebhookInboxService inboxService;

    @PostMapping(
            path = "/provider",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Void> receive(
            @RequestHeader("X-Webhook-Key-Id") String keyId,
            @RequestHeader("X-Webhook-Timestamp") String timestamp,
            @RequestHeader("X-Webhook-Id") String deliveryId,
            @RequestHeader("X-Webhook-Signature") String signature,
            @RequestBody byte[] rawBody) {

        WebhookKey key = keyResolver.requireActiveKey(keyId);
        verifier.verify(rawBody, timestamp, deliveryId, signature,
                key.secretBytes(), Instant.now());

        inboxService.acceptOnce(
                key.integrationId(), deliveryId, rawBody);
        return ResponseEntity.accepted().build();
    }
}
```

Đây là ví dụ khung; cần bổ sung import, exception mapping và cấu hình thực tế. `WebhookKeyResolver` phải giới hạn key ID theo endpoint/integration. `acceptOnce` cần insert inbox record với unique constraint và lưu event/outbox bền vững trong transaction. Không chỉ `SELECT` trước rồi `INSERT` sau.

Đặt giới hạn body size ở gateway và server trước khi đọc toàn bộ `byte[]`; nếu không, payload rất lớn có thể làm cạn memory ngay cả khi chữ ký sai. Cũng cần rate limit, timeout và concurrency limit cho endpoint.

Sau khi event được lưu thành công, worker có thể parse JSON, validate schema, kiểm tra tenant/object và thực hiện nghiệp vụ. Nếu xử lý đồng bộ, mọi bước cần transaction/idempotency rõ ràng và không được tạo side effect trước signature verification.

## 14. Xử lý response và acknowledgement

Webhook receiver thường cần trả response nhanh để sender không retry quá sớm. Inbox pattern giúp xác nhận sau khi event đã được lưu bền vững:

| Trường hợp | Hành vi gợi ý |
|---|---|
| Chữ ký hợp lệ, delivery ID mới, inbox commit thành công | Trả `2xx` |
| Chữ ký hợp lệ, delivery ID đã có và payload hash giống | Không xử lý lại; trả `2xx` theo duplicate policy |
| Cùng delivery ID nhưng payload hash khác | Không ghi đè; cách ly/cảnh báo và từ chối theo contract |
| Chữ ký sai hoặc timestamp ngoài tolerance | Từ chối; không tạo inbox record hoặc side effect |
| Database/inbox tạm thời không khả dụng | Trả lỗi retryable như `5xx`; không báo thành công khi chưa lưu bền vững |
| Event type không hỗ trợ | Ghi nhận theo policy; không chạy nghiệp vụ và tránh retry vô hạn |

Không trả `2xx` trước khi event được lưu bền vững nếu hệ thống dựa vào sender retry để bảo đảm delivery. Ngược lại, không giữ HTTP request mở trong thời gian thực hiện báo cáo hoặc workflow dài. Trả acknowledgement sau commit rồi xử lý bất đồng bộ thường dễ kiểm soát hơn.

## 15. Outbound webhook: ký event trước khi gửi

Khi hệ thống gửi webhook cho subscriber, event nên được tạo cùng transaction nghiệp vụ qua outbox pattern:

```text
Business transaction:
  update order status = SHIPPED
  insert outbox event order.shipped
  commit

Webhook dispatcher:
  load pending event
  resolve active subscription and key version
  serialize canonical raw payload
  sign payload
  send over HTTPS
  record attempt and result
```

Sender cần:

- Tạo event ID ổn định qua các lần retry.
- Ký chính xác bytes sẽ gửi.
- Gửi timestamp và signature version theo contract.
- Dùng secret riêng theo subscription/tenant hoặc key pair được quản lý.
- Xác minh TLS certificate và hostname của receiver.
- Không gửi token nội bộ, cookie hoặc credential của service trong webhook header.
- Chỉ gửi trường cần thiết, không đưa dữ liệu nhạy cảm dư thừa vào payload.
- Ghi attempt, status và latency mà không log secret hoặc raw payload nhạy cảm.

Timestamp/signature có thể được tạo lại cho mỗi attempt nếu giao thức yêu cầu timestamp mới; event ID vẫn phải giữ nguyên để receiver deduplicate. Cách retry phải khớp chính xác giao thức của hai bên.

## 16. Bảo vệ URL callback khỏi SSRF

Outbound webhook thường gửi tới URL do tenant hoặc đối tác cấu hình. Nếu server kết nối tới URL tùy ý, attacker có thể lợi dụng dispatcher để truy cập localhost, private network, cloud metadata hoặc management endpoint.

Các kiểm soát cần có:

- Chỉ cho phép scheme cần thiết, thường là HTTPS; giới hạn port theo policy.
- Xác minh quyền sở hữu/đăng ký endpoint theo quy trình của sản phẩm.
- Resolve DNS và chặn loopback, private, link-local, multicast và dải metadata/hạ tầng không được phép.
- Chống DNS rebinding bằng egress proxy hoặc ràng buộc IP đã kiểm tra với kết nối thực tế.
- Tắt redirect mặc định; nếu cần redirect, revalidate scheme, host, IP và port ở từng hop.
- Không chuyển signature secret hoặc header nhạy cảm sang origin khác.
- Bật TLS hostname verification; không bỏ qua lỗi chứng thư.
- Đặt connect/read timeout, response body limit và concurrency/egress budget.
- Dùng network egress policy để dispatcher không thể truy cập control plane, database hoặc mạng quản trị.

Không dùng `Origin` hoặc CORS để bảo vệ outbound callback. Đây là server-to-server traffic; CORS không ngăn dispatcher truy cập địa chỉ nội bộ.

## 17. Retry, backoff và giới hạn tài nguyên

Webhook delivery thường cần retry khi receiver tạm thời không sẵn sàng. Retry không giới hạn có thể tạo request storm và chi phí egress.

- Retry timeout, lỗi mạng tạm thời, `408`, `429` và một số `5xx` theo hợp đồng.
- Không retry vô hạn lỗi `4xx` cố định như endpoint không tồn tại hoặc payload không được hỗ trợ.
- Dùng exponential backoff kèm jitter.
- Giới hạn số attempt và tổng thời gian retry.
- Tôn trọng `Retry-After` trong giới hạn policy.
- Giới hạn delivery concurrency theo subscription và tenant.
- Đặt queue depth, event age, payload size và egress budget.
- Dùng circuit breaker hoặc pause subscription khi endpoint lỗi kéo dài.
- Đưa event hết retry vào trạng thái failed/dead-letter để replay thủ công có kiểm soát.

Mỗi retry giữ event ID ổn định. Không tạo event ID mới cho từng attempt vì receiver sẽ không thể nhận diện cùng một event. Retry chỉ là cơ chế delivery; receiver vẫn phải deduplicate và xử lý idempotently.

## 18. Validate event sau khi chữ ký hợp lệ

Chữ ký hợp lệ không có nghĩa mọi field trong payload đều đúng hoặc event được phép thực hiện. Sau verify, receiver cần:

- Validate `Content-Type`, schema version, event type, field length và JSON depth.
- Kiểm tra event type nằm trong allowlist của integration.
- Kiểm tra tenant/object reference khớp integration đã xác minh.
- Kiểm tra trạng thái hiện tại và thứ tự event nếu nghiệp vụ yêu cầu.
- Không tin `ownerId`, `tenantId`, `amount` hoặc status do sender gửi nếu nguồn authoritative ở hệ thống khác; cần đối soát.
- Xác minh provider account/merchant/customer reference khớp integration.
- Giới hạn array size, nested object và tổng payload để tránh resource abuse.

Ví dụ, event `payment.succeeded` không nên tự động ghi nhận thanh toán chỉ vì payload có `status: "succeeded"`. Hệ thống cần xác minh transaction ID, merchant/account, số tiền, currency và trạng thái provider theo hợp đồng. Chữ ký xác minh nguồn gửi và integrity; nghiệp vụ vẫn cần validation.

## 19. Logging, monitoring và incident response

Webhook security cần telemetry cho cả inbound verification và outbound delivery. Có thể ghi:

- Integration ID, tenant reference, endpoint ID và key ID (không ghi secret).
- Delivery/event ID, event type, schema version và correlation ID.
- Signature verification result, timestamp skew và duplicate/replay result.
- Inbox/outbox state, attempt count, response class và latency.
- Queue age, dead-letter count, endpoint pause và retry exhaustion.
- Destination reference và SSRF policy decision ở mức an toàn.

Không log raw secret, private key, access token, full signature nếu không cần, raw payload chứa dữ liệu cá nhân hoặc response body không giới hạn. Nếu cần lưu payload để xử lý bất đồng bộ, mã hóa dữ liệu, giới hạn quyền đọc và retention.

Alert khi:

- Signature failure tăng đột biến.
- Timestamp drift bất thường.
- Delivery ID trùng với payload hash khác.
- Key đã revoke vẫn được sử dụng.
- Một integration gửi event type ngoài allowlist.
- Queue/dead-letter tăng nhanh hoặc retry kéo dài.
- Outbound destination resolve tới IP bị cấm hoặc liên tục redirect.
- Tenant bị offboard nhưng webhook vẫn được nhận/gửi.

Nếu secret/private key bị compromise, thu hồi hoặc xoay key, tạm dừng integration khi cần, đánh giá event trong khoảng thời gian bị ảnh hưởng và phát hành credential mới qua kênh an toàn. Xóa một log chứa secret không làm credential mất hiệu lực; phải revoke key trước.

## 20. Kiểm thử webhook authentication

Kiểm thử cần bao gồm chữ ký hợp lệ, sai chữ ký, replay, concurrency, key lifecycle và outbound URL:

| Tình huống | Kết quả cần xác minh |
|---|---|
| Raw body và chữ ký hợp lệ | Event được lưu bền vững một lần |
| Sửa một byte trong body | Verify thất bại; không có side effect |
| Sửa timestamp nhưng giữ signature cũ | Verify thất bại hoặc timestamp bị từ chối |
| Timestamp quá cũ/quá xa tương lai | Request bị từ chối |
| Gửi lại cùng delivery ID và payload | Không chạy nghiệp vụ lần hai |
| Cùng delivery ID nhưng payload khác | Không ghi đè; cách ly và cảnh báo |
| Hai request cùng ID đến đồng thời | Unique constraint chỉ tạo một inbox record |
| Signature sai encoding/độ dài | Từ chối an toàn; không lỗi 500 hoặc log secret |
| Key ID không tồn tại/đã revoke | Từ chối; không fallback thử mọi key |
| Key rotation overlap | Key mới được chấp nhận; key cũ bị từ chối sau hạn |
| Payload có tenant khác integration | Từ chối và audit |
| Event type ngoài allowlist | Không thực hiện nghiệp vụ |
| Database inbox không khả dụng | Không trả success trước commit |
| Outbound URL là localhost/private/link-local | Bị chặn trước khi kết nối |
| DNS trả public rồi đổi sang private | Kết nối bị chặn theo destination thực tế |
| Redirect sang IP/host bị cấm | Không follow hoặc bị chặn sau revalidation |
| Receiver trả `429`/`5xx` | Retry theo backoff, giới hạn attempt và giữ event ID |
| Tenant bị offboard | Key/grant/subscription bị revoke và event bị chặn theo lifecycle policy |

Integration test nên đi qua HTTP stack thực tế để xác minh raw body không bị middleware thay đổi, header được parse đúng, body size được giới hạn và deduplication có tính nguyên tử. Với outbound SSRF, dùng DNS/HTTP test server giả lập các loại địa chỉ và redirect; không thử bằng cách gọi metadata endpoint production.

## 21. Checklist triển khai

- [ ] Chọn HMAC hoặc chữ ký bất đối xứng theo trust model và giao thức provider.
- [ ] Sender/receiver thống nhất thuật toán, signature version, canonical input và encoding.
- [ ] Ký và verify đúng raw body bytes hoặc canonical payload theo contract.
- [ ] Giới hạn body size, timeout, rate và concurrency trước khi xử lý payload lớn.
- [ ] Chọn key bằng key ID đã đăng ký; không lấy key/secret từ request hoặc URL tùy ý.
- [ ] So sánh HMAC an toàn; verify chữ ký số bằng public key đã tin cậy và thuật toán allowlist.
- [ ] Timestamp nằm trong dữ liệu được ký và có tolerance hữu hạn.
- [ ] Delivery ID ổn định qua retry và được deduplicate bằng unique constraint bền vững.
- [ ] Side effect nghiệp vụ có idempotency; không tuyên bố exactly-once chỉ dựa vào webhook signature.
- [ ] Key riêng theo integration/tenant, lưu trong secret manager và có rotation/revocation.
- [ ] Kiểm tra integration state, tenant, event type, schema và business state sau verify.
- [ ] Outbound callback có SSRF protection, TLS verification, redirect policy và egress controls.
- [ ] Retry có backoff, jitter, attempt limit, deadline và dead-letter handling.
- [ ] Log không chứa secret/private key/token/raw payload nhạy cảm; có metric và alert.
- [ ] Có test body tampering, stale timestamp, replay, duplicate, concurrency, rotation và SSRF.

## Kết luận

Xác thực webhook cần chứng minh nguồn gửi và tính toàn vẹn của dữ liệu trước khi receiver thực hiện nghiệp vụ. HMAC phù hợp khi hai bên chia sẻ secret; chữ ký bất đối xứng phù hợp khi sender giữ private key và nhiều receiver chỉ cần public key để verify. Dù chọn cách nào, receiver phải ký/verify đúng raw body hoặc canonical payload theo contract, giới hạn timestamp, deduplicate delivery ID và xử lý side effect idempotently. Key cần được quản lý theo integration với rotation/revocation rõ ràng. Sau verify vẫn phải kiểm tra tenant, event type, schema và business state; outbound webhook cần thêm SSRF protection và retry budget. Khi các lớp này được triển khai và kiểm thử cùng nhau, webhook trở thành một kênh tích hợp có thể xác minh và kiểm soát thay vì một endpoint tin mọi payload đến.
