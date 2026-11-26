# Mã hóa dữ liệu nghiệp vụ nhạy cảm khi yêu cầu bảo vệ đầu cuối

## 1. Bài toán: TLS đã đủ để giữ bí mật message chưa?

Trong **Spring AMQP**, producer thường dùng `RabbitTemplate` publish dữ liệu tới **exchange**, broker định tuyến qua **binding** tới **queue**, và consumer dùng `@RabbitListener` để nhận. Một message có thể nằm trong queue, được dead-letter sang DLQ, bị retry, được lưu trong backup hoặc được một công cụ vận hành đọc để điều tra.

Giả sử message chứa số tài khoản ngân hàng, giấy tờ định danh, thông tin y tế hay chi tiết thanh toán. Dù producer và RabbitMQ kết nối bằng **TLS**, dữ liệu sẽ được giải mã ở điểm kết thúc TLS. Broker, ứng dụng quản trị hoặc một hệ thống trung gian có quyền đọc payload vẫn có thể tiếp cận **plaintext** nếu chỉ dùng TLS.

Khi chính sách yêu cầu **broker và các hệ thống trung gian không đọc được dữ liệu nghiệp vụ nhạy cảm**, cần áp dụng **mã hóa tại tầng ứng dụng trước khi publish**. Chỉ consumer được cấp khóa giải mã mới có thể khôi phục payload.

~~~text
Producer tin cậy                       RabbitMQ                       Consumer tin cậy
------------------                    --------                       ------------------
Business payload
      |
      v
Encrypt AES-GCM
      |
      | envelope(ciphertext, nonce, keyId, metadata)
      +---------- TLS ----------> exchange ---> queue/DLQ
                                                     |
                                          broker thấy ciphertext
                                                     |
                              <---------- TLS -------+
                              |
                              v
                    Verify AEAD tag + Decrypt
                              |
                              v
                    Validate + business transaction
                              |
                              v
                       Consumer ACK
~~~

Mục tiêu bài học:

1. Phân biệt **mã hóa đường truyền (TLS)**, **mã hóa dữ liệu lưu trữ** và **mã hóa message ở tầng ứng dụng**.
2. Xác định ranh giới tin cậy và trường dữ liệu cần bảo mật mà không làm hỏng exchange/queue/binding.
3. Dùng thuật toán **AEAD**, cụ thể **AES-GCM**, với nonce duy nhất, authentication tag và **AAD**.
4. Thiết kế envelope có version, key ID, nonce, ciphertext, mã sự kiện và thông tin định tuyến không nhạy cảm.
5. Tích hợp với `RabbitTemplate` và `@RabbitListener`; bảo vệ retry, DLQ, idempotency và observability.
6. Lập kế hoạch **KMS/HSM**, phân quyền khóa, rotation, phục hồi và kiểm thử thao tác sai lệch ciphertext.

> **Phạm vi:** đây là mã hóa payload **end-to-end giữa producer và consumer được cấp quyền**, không phải bảo mật tuyệt đối cho mọi thành phần. Nếu thiết bị/chạy code của producer hoặc consumer đã bị xâm nhập, plaintext và khóa vẫn có thể bị lộ tại endpoint. Ngoài ra, việc mã hóa không thay thế xác thực nguồn, phân quyền RabbitMQ hay kiểm soát replay.

## 2. Xác định threat model và lớp bảo vệ

Trước khi viết mã, cần xác định chính xác **ai cần được bảo vệ khỏi ai**:

| Mối đe dọa | TLS tới RabbitMQ | Mã hóa payload ở tầng ứng dụng | Kiểm soát bổ sung |
| --- | --- | --- | --- |
| Nghe lén mạng giữa client và broker | Bảo vệ nếu TLS được cấu hình và xác thực đúng. | Ciphertext không tiết lộ plaintext. | mTLS/kiểm tra hostname, TLS cho liên kết nội bộ phù hợp. |
| Broker operator có quyền đọc payload/backup | Không bảo vệ payload sau khi TLS kết thúc. | Bảo vệ nếu operator **không có khóa giải mã**. | KMS/HSM độc lập, RBAC, audit. |
| DLQ hoặc backup bị lộ | Không bảo vệ dữ liệu đã lưu. | Chỉ lưu ciphertext nếu pipeline không giải mã rồi ghi lại. | Mã hóa backup, retention, kiểm soát truy cập. |
| Header chứa email, token, số định danh | TLS bảo vệ trên đường truyền. | **Không** nếu chỉ mã hóa body. | Không cho dữ liệu nhạy cảm vào header/route/log, hoặc bảo vệ riêng. |
| Payload bị sửa hoặc tráo trên đường xử lý | TLS chống sửa trong từng đoạn kết nối. | AEAD tag phát hiện sửa payload/AAD. | Ràng buộc context và xác thực người gửi. |
| Replay nguyên một ciphertext cũ | Không chặn replay hợp lệ. | **AES-GCM không tự ngăn replay**. | `eventId` duy nhất, inbox/idempotency, TTL/deadline. |
| Consumer bị chiếm quyền | Không giải quyết. | Consumer vẫn có khóa và plaintext. | Least privilege, hardening, rotation, hạn chế thời gian giữ plaintext. |
| Sai routing key hoặc broker không xử lý | Không giải quyết. | Không giải quyết. | Publisher confirms/returns, topology, retry/DLQ. |

### 2.1. Ba lớp phải phối hợp, không thay thế nhau

**Transport encryption (TLS/mTLS)** bảo vệ các kết nối như ứng dụng → RabbitMQ, RabbitMQ → ứng dụng và kết nối liên node nếu cấu hình. **At-rest encryption** bảo vệ ổ đĩa/snapshot, nhưng broker vẫn có thể đọc plaintext khi ứng dụng publish payload chưa mã hóa. **Application-level encryption** bảo vệ nội dung message khỏi broker hoặc thành phần trung gian không sở hữu khóa.

Mã hóa tầng ứng dụng **không mã hóa các trường AMQP ngoài body** như exchange, routing key, message headers, timestamp, kích thước message, số lượng message và nhiều thuộc tính vận hành. Chúng có thể tiết lộ **metadata** ngay cả khi ciphertext an toàn.

**Nguyên tắc giảm thiểu dữ liệu** phải đi trước mã hóa: không gửi dữ liệu không cần thiết. Ví dụ nếu consumer chỉ cần `customerId` nội bộ để tự tra cứu thông tin, gửi cả CCCD và số tài khoản dù đã mã hóa thường không phải lựa chọn tốt.

### 2.2. End-to-end theo nghĩa nào?

Trong ví dụ, **producer và consumer tin cậy**, còn RabbitMQ và operator quản lý queue **không được cấp quyền giải mã**. “End-to-end” có nghĩa payload đã mã hóa trước khi vào broker và chỉ được giải mã sau khi tới consumer.

Với **khóa đối xứng dùng chung**, bất kỳ thành phần nào sở hữu khóa đều có thể **tạo** ciphertext hợp lệ, không chỉ giải mã nó. AES-GCM cung cấp tính bí mật và tính toàn vẹn **đối với các bên không có khóa**, nhưng **không tự chứng minh producer cụ thể là ai** khi nhiều producer cùng dùng một khóa. Nếu cần chống giả mạo giữa các producer có khóa khác nhau hoặc không tin cậy lẫn nhau, cân nhắc **khóa riêng theo producer/tenant**, chữ ký số hoặc một mô hình xác thực nguồn có thiết kế phù hợp.

## 3. Tổ chức message envelope và ranh giới mã hóa

Mã hóa toàn bộ payload sau khi tạo object nghiệp vụ thường dễ bảo đảm không bỏ sót trường nhạy cảm hơn việc tự chọn vài trường. Broker vẫn cần exchange, routing key và một số metadata để định tuyến/quản trị.

Một **envelope** có thể gồm:

~~~json
{
  "version": "1",
  "algorithm": "AES-256-GCM",
  "keyId": "customer-a/payload/2026-11",
  "nonceB64": "base64-12-byte-random-nonce",
  "ciphertextB64": "base64-ciphertext-plus-16-byte-auth-tag",
  "eventId": "evt-2026-000129",
  "tenantId": "customer-a",
  "eventType": "payment.authorized"
}
~~~

Các giá trị Base64 ở trên chỉ là **ký hiệu minh họa**, không phải chuỗi hợp lệ để giải mã. Trong triển khai thật, dùng Base64 của 12 byte nonce và các byte ciphertext có GCM tag được thêm vào bởi Java Cipher.

| Trường | Mã hóa? | Chức năng | Quy tắc |
| --- | --- | --- | --- |
| `version`, `algorithm` | Ngoài ciphertext | Chọn phiên bản envelope và thuật toán được phép. | Xác thực bằng AAD; không cho phép thuật toán tùy ý do message đề xuất. |
| `keyId` | Ngoài ciphertext | Tìm phiên bản khóa có quyền giải mã. | Không phải secret nhưng không được để user tùy ý chọn khóa tenant khác. |
| `nonceB64` | Ngoài ciphertext | Tham số khởi tạo AES-GCM. | 12 byte, không lặp với cùng key; không cần giấu nonce. |
| `ciphertextB64` | Ciphertext | Payload nghiệp vụ đã mã hóa và GCM tag. | Không log hoặc in plaintext khi decrypt thất bại. |
| `eventId` | Ngoài ciphertext | Dedupe, trace và đối soát. | Tham gia AAD; unique theo business operation. |
| `tenantId`, `eventType` | Ngoài ciphertext | Định tuyến/phân quyền/quan sát giới hạn. | Tham gia AAD; nếu cũng nhạy cảm, chuyển vào ciphertext và dùng alias khác. |

**Chọn metadata theo yêu cầu thực tế.** Nếu tenant ID, tên event hoặc key ID có thể tiết lộ thông tin nhạy cảm, không giữ chúng ở ngoài dưới dạng dễ đọc. Có thể dùng opaque identifier, một routing group không nhạy cảm và mapping được quản lý riêng.

### 3.1. AAD ràng buộc metadata

**AAD (Additional Authenticated Data)** là dữ liệu **không mã hóa nhưng được xác thực** cùng ciphertext bởi AES-GCM. Khi encrypt và decrypt, hai phía phải tạo **chính xác cùng byte AAD**. Nếu một trường đã được dùng làm AAD bị sửa, GCM tag sẽ không hợp lệ.

Ví dụ AAD chứa:

~~~text
version
algorithm
keyId
tenantId
eventId
eventType
~~~

Trong một hệ thống có broker/route cố định, có thể ràng buộc thêm **logical destination** hoặc **schema version** nếu đảm bảo giá trị không bị thay đổi hợp lệ khi message được đưa vào DLQ/retry. **Không buộc AAD vào một header có thể bị broker sửa khi dead-letter**, nếu consumer sau đó vẫn cần giải mã message ấy. AAD phải được định nghĩa ở mức hợp đồng ứng dụng và bất biến trong suốt vòng đời ciphertext.

**Không dùng phép nối chuỗi mơ hồ** như `tenantId + ":" + eventId` nếu trường có thể chứa `:`; nhiều bộ giá trị khác nhau có thể tạo cùng chuỗi. Dùng encoding chuẩn hóa rõ ràng: JSON canonical có quy tắc chặt, CBOR canonical, protobuf deterministic hoặc chuỗi các trường có **prefix độ dài**.

### 3.2. Content type và phiên bản

Ví dụ sử dụng JSON envelope với `contentType = application/vnd.example.secure-event+json`. **Content type không làm payload an toàn hơn**; nó giúp consumer nhận đúng loại message. Chỉ chấp nhận danh sách version/algorithm đã định nghĩa trước, không suy đoán hoặc fallback tự động sang plaintext nếu decrypt thất bại.

Khi thay đổi schema payload, cần duy trì **schemaVersion bên trong ciphertext** hoặc trong metadata được xác thực để hỗ trợ consumer cũ. Không đánh đồng `envelope version` với version của dữ liệu nghiệp vụ.

## 4. Chọn thuật toán đúng: AES-GCM thay vì tự tạo mã hóa

**Authenticated Encryption with Associated Data (AEAD)** cung cấp hai tính chất:

1. **Confidentiality:** không khôi phục plaintext từ ciphertext khi không có khóa.
2. **Integrity/authenticity theo khóa:** phát hiện ciphertext hoặc AAD bị sửa, với giới hạn threat model của khóa đối xứng.

**AES/GCM/NoPadding** được Java Cryptography Architecture (JCA) hỗ trợ rộng rãi. Ví dụ phù hợp cho bài học:

| Tham số | Giá trị minh họa | Lý do |
| --- | --- | --- |
| Thuật toán | `AES/GCM/NoPadding` | AEAD tích hợp mã hóa và xác thực. |
| Độ dài khóa | **256 bit** (32 byte) | Phù hợp ứng dụng đòi hỏi bảo vệ mạnh; quản lý bằng KMS/HSM. |
| Nonce/IV | **96 bit** (12 byte) | Độ dài khuyến nghị phổ biến cho GCM. |
| Authentication tag | **128 bit** (16 byte) | Được Java thêm vào kết quả `doFinal` khi encrypt. |
| AAD | Byte canonical của metadata không nhạy cảm | Ràng buộc context vào ciphertext. |

**Không bao giờ tái sử dụng cặp (AES key, nonce)** để mã hóa hai payload khác nhau. Với AES-GCM, việc lặp nonce cùng key có thể phá vỡ tính bí mật và tính toàn vẹn. Ví dụ dùng `SecureRandom` tạo nonce mới cho **từng lần encrypt**; vì nonce ngẫu nhiên vẫn có xác suất va chạm, production phải giới hạn số lần dùng một khóa và luân chuyển theo khuyến nghị của NIST/OWASP. Đừng coi random 96-bit là giấy phép dùng một key vô hạn cho mọi instance.

**Những điều không làm:**

- Không dùng `AES/ECB`, thuật toán tự chế, XOR hoặc “chỉ Base64 encode”.
- Không dùng AES-CBC không kèm cơ chế xác thực toàn vẹn riêng.
- Không cố định IV bằng số 0, ngày, `orderId` hoặc counter không đảm bảo duy nhất xuyên nhiều replica/restart.
- Không biến password con người thành AES key bằng `getBytes()`; nếu cần password-based encryption, dùng KDF phù hợp, nhưng trong messaging service-to-service nên dùng khóa sinh ngẫu nhiên và KMS.
- Không tiếp tục xử lý nghiệp vụ khi GCM tag không xác thực được.

### 4.1. Khác biệt giữa “encrypt lần nữa” và “redeliver”

Nếu broker **redeliver cùng message ciphertext** do ACK thất bại, cùng nonce và ciphertext xuất hiện lần nữa. Đây là **truyền lại cùng một kết quả encrypt**, không phải thực hiện lại phép mã hóa. Nguy cơ lớn là **gọi encrypt nhiều lần bằng cùng key/nonce tự tái sử dụng**, hoặc sử dụng một nonce cố định cho các payload khác nhau.

Nếu phải tạo ciphertext mới khi retry, luôn sinh **nonce mới** (hoặc dùng DEK mới theo chính sách). Dù nonce mới, **business event ID phải giữ nguyên** để consumer kiểm tra idempotency; **nonce không phải event ID**.

## 5. Lưu trữ, phân phối và xoay vòng khóa

Mã hóa đúng thuật toán nhưng khóa bị lộ trong Git, image container hoặc log vẫn không đạt mục tiêu bảo vệ.

### 5.1. Hợp đồng quản lý khóa

Một dịch vụ quản lý khóa cho producer/consumer nên đảm bảo:

1. Khóa AES được **sinh ngẫu nhiên bằng CSPRNG** hoặc bởi KMS/HSM.
2. Producer được phép dùng khóa cho **encrypt** đúng tenant và loại sự kiện.
3. Consumer được phép dùng khóa cho **decrypt** đúng phạm vi; quyền decrypt không được cấp cho broker/operator không cần thiết.
4. `keyId` chỉ là **định danh version/alias**, không phải bản thân khóa.
5. Khóa có lifecycle: active → decrypt-only → retired → revoked/destroyed khi hết retention và hợp đồng lưu trữ.
6. Khi nghi bị lộ khóa, kích hoạt rotation/incident response phù hợp, không chỉ đổi `keyId` trong envelope.

**Không hard-code base64 key trong source**, không commit secret vào repository và không ghi khóa ra log. Với môi trường chuyên nghiệp, KMS, Vault hoặc HSM cung cấp kiểm soát quyền, audit và rotation tốt hơn config file thông thường.

### 5.2. Static data key và envelope encryption

Có hai chiến lược thường gặp:

| Chiến lược | Cách hoạt động | Đánh đổi |
| --- | --- | --- |
| **Key dài hạn theo tenant/version** | Producer encrypt nhiều message với một AES key có version. | Đơn giản nhưng phải quản lý nonce uniqueness/usage limit cực chặt, phạm vi lộ khóa lớn hơn. |
| **Envelope encryption, DEK riêng theo message hoặc nhóm nhỏ** | Sinh data encryption key (DEK), encrypt payload bằng DEK, dùng key encryption key (KEK) tại KMS để wrap DEK. | Chi phí KMS/metadata và lifecycle phức tạp hơn, tách biệt tốt hơn, giới hạn tác động lộ DEK. |

Với envelope encryption, message có thêm trường `wrappedDekB64` hoặc `encryptedDataKey`, `kekKeyId` và thuật toán wrap theo hợp đồng. **KEK không nằm trong message**; chỉ bản mã của DEK được gửi kèm ciphertext. Consumer có quyền `unwrap/decrypt` trên KMS mới lấy được DEK.

~~~text
Producer                                KMS / HSM
   |                                        |
   +--> request data key hoặc generate DEK  |
   |<--------- plaintext DEK + wrapped DEK -+
   |
   +--> AES-GCM(payload, DEK, nonce, AAD)
   |
   +--> publish {keyId, wrappedDEK, nonce, ciphertext, metadata}
                             |
                           RabbitMQ
                             |
                          Consumer
                             |
                      KMS unwrap DEK
                             |
                    AES-GCM verify + decrypt
~~~

Nếu dùng **DEK mới thật sự cho mỗi message**, giới hạn tái sử dụng nonce theo DEK dễ quản lý hơn; nhưng vẫn phải dùng nonce hợp lệ và kiểm tra tag. **Key rotation của KEK** có thể cho phép **rewrap** DEK mà không đổi plaintext/ciphertext; **thay DEK** thì phải giải mã và mã hóa lại dữ liệu. Hệ thống cần bảo đảm có thể giải mã dữ liệu trong DLQ, backup và retry cũ trong thời gian lưu trữ hợp lệ.

### 5.3. Không xoay vòng khóa một cách phá vỡ consumer

Quy trình rollout ví dụ:

1. Triển khai consumer có khả năng decrypt **K1 và K2**; K2 mới được cấp quyền đúng tenant.
2. Chuyển producer sang encrypt bằng **K2**, ghi `keyId=K2` vào envelope.
3. Giữ K1 ở chế độ decrypt-only trong thời gian queue, retry/DLQ, backup và event cũ còn hợp lệ.
4. Đo số message còn dùng K1; chỉ retire/revoke K1 sau khi đã xử lý dữ liệu cũ hoặc có kế hoạch re-encrypt/rewrap.
5. Audit mọi thao tác cấp, rotate, dùng và revoke khóa; chuẩn bị quy trình khôi phục nếu KMS tạm không sẵn sàng.

Đừng cắt quyền decrypt khóa cũ khi DLQ chưa được xử lý hoặc queue còn chứa ciphertext cũ. **Mất khả năng decrypt là sự cố nghiệp vụ** ngay cả khi RabbitMQ và kết nối TLS hoàn toàn khỏe.

## 6. Ví dụ Java: mã hóa AES-GCM có AAD

Ví dụ dùng **Java 17+**, JCA và khóa AES được cấp qua một abstraction. Các class Java dưới đây minh họa **hợp đồng có thể ghép vào ứng dụng**, không chứa khóa cứng hoặc triển khai KMS giả. Để chạy đầy đủ, cần viết bean `TenantKeyResolver` sử dụng secret/KMS phù hợp.

### 6.1. DTO envelope

~~~java
// ProtectedEnvelope.java
public record ProtectedEnvelope(
        String version,
        String algorithm,
        String keyId,
        String nonceB64,
        String ciphertextB64,
        String eventId,
        String tenantId,
        String eventType) {
}
~~~

`ciphertextB64` chứa byte ciphertext **kèm 16 byte GCM authentication tag**, đúng dạng `Cipher.doFinal()` của JCA. Không tách tag và bỏ quên khi lưu message.

### 6.2. Key resolver: hạn chế quyền theo tenant

~~~java
// TenantKeyResolver.java
import javax.crypto.SecretKey;

public interface TenantKeyResolver {

    record EncryptionKey(String keyId, SecretKey key) {
    }

    // Khóa đang active để encrypt các event MỚI cho tenant.
    EncryptionKey activeForEncryption(String tenantId);

    // Chỉ trả khóa mà consumer ĐƯỢC PHÉP giải mã cho tenant này.
    SecretKey forDecryption(String tenantId, String keyId);
}
~~~

**Không triển khai `forDecryption` bằng map toàn bộ khóa của mọi khách hàng rồi lấy theo keyId bất kỳ.** Phải xác thực producer/consumer identity, phạm vi tenant được phép và mục đích encrypt/decrypt; một tenant không được tạo envelope trỏ đến khóa của tenant khác.

### 6.3. Crypto service JCA

~~~java
// AesGcmEnvelopeCrypto.java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Objects;

import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AesGcmEnvelopeCrypto {
    private static final String VERSION = "1";
    private static final String ALG = "AES-256-GCM";
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final SecureRandom RANDOM = new SecureRandom();

    private final TenantKeyResolver keys;

    public AesGcmEnvelopeCrypto(TenantKeyResolver keys) {
        this.keys = Objects.requireNonNull(keys);
    }

    public ProtectedEnvelope encrypt(byte[] plaintext,
                                     String tenantId,
                                     String eventId,
                                     String eventType)
            throws GeneralSecurityException {

        requireText(tenantId);
        requireText(eventId);
        requireText(eventType);

        TenantKeyResolver.EncryptionKey selected =
                keys.activeForEncryption(tenantId);
        requireText(selected.keyId());

        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce); // nonce MỚI cho TỪNG phép encrypt

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, selected.key(),
                new GCMParameterSpec(TAG_BITS, nonce));

        cipher.updateAAD(aad(VERSION, ALG, selected.keyId(),
                tenantId, eventId, eventType));
        byte[] ciphertextWithTag = cipher.doFinal(plaintext);

        return new ProtectedEnvelope(
                VERSION, ALG, selected.keyId(),
                Base64.getEncoder().encodeToString(nonce),
                Base64.getEncoder().encodeToString(ciphertextWithTag),
                eventId, tenantId, eventType);
    }

    public byte[] decrypt(ProtectedEnvelope envelope,
                          String expectedTenant)
            throws GeneralSecurityException {

        Objects.requireNonNull(envelope);
        // expectedTenant lấy từ ngữ cảnh tin cậy của consumer,
        // KHÔNG mặc định tin tenantId trong payload do caller gửi.
        if (!Objects.equals(expectedTenant, envelope.tenantId())) {
            throw new GeneralSecurityException("Tenant mismatch");
        }
        if (!VERSION.equals(envelope.version())
                || !ALG.equals(envelope.algorithm())) {
            throw new GeneralSecurityException("Unsupported envelope");
        }
        requireText(envelope.keyId());
        requireText(envelope.eventId());
        requireText(envelope.eventType());

        // Production: chặn độ dài field / Base64 TRƯỚC decode.
        byte[] nonce = Base64.getDecoder().decode(envelope.nonceB64());
        byte[] ciphertext = Base64.getDecoder()
                .decode(envelope.ciphertextB64());

        if (nonce.length != NONCE_BYTES
                || ciphertext.length < TAG_BITS / 8) {
            throw new GeneralSecurityException("Invalid encrypted payload");
        }

        // Resolver phải kiểm tra cả tenantId và keyId.
        SecretKey key = keys.forDecryption(expectedTenant, envelope.keyId());

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad(
                envelope.version(), envelope.algorithm(), envelope.keyId(),
                envelope.tenantId(), envelope.eventId(), envelope.eventType()));

        // Nếu ciphertext hoặc AAD bị sửa, JCA ném AEADBadTagException.
        return cipher.doFinal(ciphertext);
    }

    private static void requireText(String s) {
        if (s == null || s.isBlank()) {
            throw new IllegalArgumentException("Missing envelope field");
        }
    }

    private static byte[] aad(String... fields) {
        // Encoding canonical bằng prefix độ dài (4 byte + UTF-8).
        // KHÔNG phụ thuộc thứ tự property JSON hoặc dấu phân cách tự chọn.
        try {
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            DataOutputStream out = new DataOutputStream(buffer);
            for (String field : fields) {
                byte[] bytes = field.getBytes(StandardCharsets.UTF_8);
                out.writeInt(bytes.length);
                out.write(bytes);
            }
            out.flush();
            return buffer.toByteArray();
        } catch (IOException impossibleForMemoryBuffer) {
            throw new IllegalStateException("AAD encoding failure",
                    impossibleForMemoryBuffer);
        }
    }
}
~~~

**Điểm đúng của ví dụ:**

1. Không lưu `Cipher` trong singleton bean: mỗi lần encrypt/decrypt tạo một instance mới, tránh chia sẻ trạng thái giữa thread.
2. Mỗi phép encrypt gọi `SecureRandom.nextBytes` để tạo nonce 12 byte mới.
3. Gọi `updateAAD` **trước** `doFinal` ở cả hai phía với encoding cùng thứ tự.
4. Version, algorithm, key ID, event ID, tenant ID và event type đều được xác thực bằng AEAD tag.
5. Decrypt chỉ lấy khóa theo `expectedTenant` từ ngữ cảnh đáng tin cậy, không chỉ dựa vào `keyId` trong message.
6. Khi tag không hợp lệ, `doFinal` ném `AEADBadTagException`; không được trả payload một phần hoặc cố decrypt bằng thuật toán khác.

**Phạm vi minh họa:** code chưa giới hạn số byte envelope, độ dài từng field và số lần dùng một key; những giới hạn đó là bắt buộc trước khi đưa ra production để giảm rủi ro DoS và vi phạm giới hạn nonce GCM. `Base64.getDecoder().decode` có thể ném `IllegalArgumentException`; tầng listener cần coi envelope sai encoding là message lỗi định dạng.

**Khóa 256 bit:** contract `TenantKeyResolver` phải trả đúng `SecretKey` AES với độ dài phù hợp. Khi dùng provider/HSM, không mặc định `key.getEncoded()` luôn cho phép xuất key material; không ghi hay kiểm tra key bằng cách log raw bytes. Mọi giới hạn dùng khóa cần do hệ thống quản lý khóa giám sát.

## 7. Spring AMQP: định tuyến ciphertext tới RabbitMQ

Ở tầng RabbitMQ, **exchange, routing key, queue và binding không thay đổi** chỉ vì body được mã hóa. Broker vẫn cần metadata định tuyến ở ngoài ciphertext, nhưng không cần hiểu nội dung payment.

~~~java
// ProtectedMessagingTopology.java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ProtectedMessagingTopology {
    public static final String EXCHANGE = "secure.events.x";
    public static final String QUEUE = "secure.payment.q";
    public static final String KEY = "secure.payment";

    @Bean
    Declarables protectedTopology() {
        DirectExchange exchange =
                new DirectExchange(EXCHANGE, true, false);
        Queue queue = QueueBuilder.durable(QUEUE)
                .deadLetterExchange("secure.dead.x")
                .deadLetterRoutingKey("secure.payment.failed")
                .build();
        Binding main = BindingBuilder.bind(queue)
                .to(exchange).with(KEY);

        DirectExchange dead =
                new DirectExchange("secure.dead.x", true, false);
        Queue deadQueue = QueueBuilder.durable("secure.payment.dead.q")
                .build();
        Binding deadBinding = BindingBuilder.bind(deadQueue)
                .to(dead).with("secure.payment.failed");

        return new Declarables(exchange, queue, main,
                dead, deadQueue, deadBinding);
    }
}
~~~

Queue chính chứa **ciphertext envelope**. Nếu consumer reject mà không requeue, broker có thể dead-letter **cùng ciphertext** sang `secure.payment.dead.q`. **Không tự giải mã rồi đẩy plaintext vào DLQ**. Với hệ thống thật, policy, quyền RabbitAdmin và cơ chế cấu hình DLX phải được kiểm soát; thay đổi queue arguments khi queue đã tồn tại có thể đòi hỏi migration.

### 7.1. Producer: mã hóa trước RabbitTemplate.send()

Ví dụ dưới sử dụng **Spring Boot 3.x / Spring AMQP AMQP 0-9-1**, Java 17 và Jackson 2 (`com.fasterxml.jackson.databind.ObjectMapper`). Với Spring Boot 4 có Jackson 3 hoặc thay đổi starter, cần điều chỉnh dependency/API serializer theo phiên bản. Phần mã hóa JCA không phụ thuộc Jackson.

~~~java
// PaymentAuthorized.java
import java.math.BigDecimal;

public record PaymentAuthorized(
        String paymentId,
        String bankAccountNumber,
        BigDecimal amount,
        String currency) {
}
~~~

~~~java
// ProtectedPaymentPublisher.java
import java.security.GeneralSecurityException;
import java.util.Objects;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProtectedPaymentPublisher {
    private final RabbitTemplate rabbitTemplate;
    private final AesGcmEnvelopeCrypto crypto;
    private final ObjectMapper mapper;

    public ProtectedPaymentPublisher(RabbitTemplate rabbitTemplate,
                                     AesGcmEnvelopeCrypto crypto,
                                     ObjectMapper mapper) {
        this.rabbitTemplate = rabbitTemplate;
        this.crypto = crypto;
        this.mapper = mapper;
    }

    public void publish(String eventId,
                        String tenantId,
                        PaymentAuthorized payment)
            throws GeneralSecurityException, JsonProcessingException {

        Objects.requireNonNull(payment);
        byte[] sensitiveJson = mapper.writeValueAsBytes(payment);

        ProtectedEnvelope envelope = crypto.encrypt(
                sensitiveJson, tenantId, eventId, "payment.authorized");

        // Tại đây chỉ serialize envelope, không phải plaintext nghiệp vụ.
        byte[] messageBody = mapper.writeValueAsBytes(envelope);

        MessageProperties properties = new MessageProperties();
        properties.setContentType(
                "application/vnd.example.secure-event+json");
        properties.setMessageId(eventId);
        properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);

        rabbitTemplate.send(
                ProtectedMessagingTopology.EXCHANGE,
                ProtectedMessagingTopology.KEY,
                new Message(messageBody, properties));
    }
}
~~~

Producer dùng `RabbitTemplate.send` để chuyển **message đã mã hóa** đến RabbitMQ; không gửi `sensitiveJson` trực tiếp. `MessageProperties.messageId` được đặt bằng `eventId` để hỗ trợ correlation/dedupe, nhưng **consumer phải đối chiếu ID ngoài với envelope đã xác thực** trước khi sử dụng.

**Rủi ro bộ nhớ:** biến `sensitiveJson` chứa plaintext trong RAM. Nếu có thể, xóa byte array sau khi mã hóa bằng `Arrays.fill` trong `finally`, đồng thời tránh lưu plaintext vào cache/log. Tuy nhiên, serialization/JVM có thể tạo bản sao tạm không xóa được ngay; đừng quảng cáo việc zero hóa một mảng byte là bảo đảm bí mật tuyệt đối trong Java.

### 7.2. Consumer: đọc envelope, kiểm tra và giải mã

Để tránh converter tự động coi envelope là DTO nghiệp vụ đã giải mã, ví dụ listener nhận **raw `org.springframework.amqp.core.Message`**:

~~~java
// ProtectedPaymentListener.java
import java.io.IOException;
import java.security.GeneralSecurityException;
import java.util.Arrays;
import java.util.Objects;

import javax.crypto.AEADBadTagException;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class ProtectedPaymentListener {
    private static final String EXPECTED_TENANT = "finance-tenant-a";
    private static final int MAX_BODY_BYTES = 1_048_576;

    private final AesGcmEnvelopeCrypto crypto;
    private final ObjectMapper mapper;
    private final PaymentApplicationService paymentService;

    public ProtectedPaymentListener(AesGcmEnvelopeCrypto crypto,
                                     ObjectMapper mapper,
                                     PaymentApplicationService paymentService) {
        this.crypto = crypto;
        this.mapper = mapper;
        this.paymentService = paymentService;
    }

    @RabbitListener(queues = ProtectedMessagingTopology.QUEUE)
    public void receive(Message message)
            throws GeneralSecurityException, IOException {

        if (message.getBody().length > MAX_BODY_BYTES) {
            throw new AmqpRejectAndDontRequeueException(
                    "Protected envelope exceeds size limit");
        }
        if (!"application/vnd.example.secure-event+json".equals(
                message.getMessageProperties().getContentType())) {
            throw new AmqpRejectAndDontRequeueException(
                    "Unsupported protected content type");
        }

        ProtectedEnvelope envelope;
        try {
            envelope = mapper.readValue(
                    message.getBody(), ProtectedEnvelope.class);
        } catch (JsonProcessingException ex) {
            throw new AmqpRejectAndDontRequeueException(
                    "Invalid protected envelope", ex);
        }

        if (!Objects.equals(envelope.eventId(),
                message.getMessageProperties().getMessageId())) {
            throw new AmqpRejectAndDontRequeueException(
                    "AMQP message ID does not match authenticated event ID");
        }

        byte[] plaintext;
        try {
            plaintext = crypto.decrypt(envelope, EXPECTED_TENANT);
        } catch (AEADBadTagException | IllegalArgumentException ex) {
            // Lỗi tampering/định dạng: không thử đi thử lại vô hạn.
            throw new AmqpRejectAndDontRequeueException(
                    "Invalid encrypted payload", ex);
        }

        try {
            PaymentAuthorized payment =
                    mapper.readValue(plaintext, PaymentAuthorized.class);
            // Ghi inbox(eventId) và tác dụng phụ nghiệp vụ cùng DB tx.
            paymentService.applyOnce(
                    envelope.eventId(), EXPECTED_TENANT, payment);
        } finally {
            Arrays.fill(plaintext, (byte) 0);
        }
    }
}
~~~

`PaymentApplicationService` là lớp nghiệp vụ do ứng dụng triển khai, không phải API Spring AMQP có sẵn. `EXPECTED_TENANT` chỉ minh họa một **queue/consumer dành riêng cho tenant A**. Với nhiều tenant, cần lấy tenant mong đợi từ **định tuyến/identity tin cậy và policy của consumer**; không gọi `decrypt(envelope, envelope.tenantId())` rồi cho rằng đã xác thực tenant.

**Phân loại lỗi là một phần của bảo mật và độ tin cậy:**

- **GCM tag sai, envelope không hợp lệ, version không hỗ trợ:** dữ liệu bị sửa hoặc không hợp đồng; không thực thi nghiệp vụ. Có thể reject không requeue tới DLQ an toàn để điều tra.
- **KMS bị outage, timeout lấy khóa:** lỗi hạ tầng **có thể hồi phục**, dùng retry/backoff có giới hạn; không coi là payload giả mạo.
- **Key ID không tồn tại hoặc tenant không có quyền:** tùy chính sách có thể chuyển sang quarantine/DLQ và cảnh báo bảo mật; không tự thử mọi khóa hay cho phép fallback.
- **Business validation thất bại sau decrypt:** xử lý theo hợp đồng nghiệp vụ; không tiết lộ plaintext khi log hoặc retry.
- **DB commit thành công nhưng ACK chưa được broker ghi nhận:** message có thể redeliver; `applyOnce` phải chống trùng bằng eventId.

Đoạn listener trên minh họa nhánh `AEADBadTagException` cụ thể. Production nên thêm exception riêng cho **unknown key**, **forbidden tenant** và **KMS temporarily unavailable**, cùng retry interceptor/recoverer phù hợp. Một `GeneralSecurityException` không được phân loại sẽ đi theo quy tắc lỗi của listener container; đừng mặc định nó luôn tới DLQ hoặc luôn retry hữu hạn.

**Chú ý:** `AmqpRejectAndDontRequeueException` chỉ khiến container từ chối không requeue theo ngữ nghĩa Spring AMQP 0-9-1 trong cấu hình phù hợp. Muốn vào DLQ cần có DLX/queue binding đúng; nếu không, broker có thể loại bỏ delivery. Đồng thời, việc ACK/reject chịu ảnh hưởng bởi transaction, retry advice và error handler thực tế.

### 7.3. Đăng ký bean và giới hạn serializer

Với một bean `TenantKeyResolver` đã được triển khai bằng KMS/HSM hoặc secret manager:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ProtectedCryptoConfig {

    @Bean
    AesGcmEnvelopeCrypto envelopeCrypto(TenantKeyResolver keys) {
        return new AesGcmEnvelopeCrypto(keys);
    }
}
~~~

Không viết `@Bean` lấy khóa AES từ một chuỗi hard-code trong bài học. Nếu cần test thuần JUnit, tạo key bằng `KeyGenerator` và giữ trong bộ nhớ **chỉ trong phạm vi test**. Đối với production, key provider là **boundary bảo mật**, phải có kiểm soát danh tính, quota, audit và vòng đời riêng.

Khi dùng JSON cho envelope và payload, đặt giới hạn độ sâu, chiều dài chuỗi, kích thước body và danh sách kiểu được deserialize. Không bật deserialization đa hình không an toàn chỉ để nhận nhiều object động. **Jackson xử lý JSON không đồng nghĩa kiểm chứng tính hợp lệ nghiệp vụ**: sau decrypt vẫn phải kiểm tra cấu trúc, số tiền, đơn vị tiền tệ, định danh và trạng thái hiện tại.

Trong code ở mục 7.2, lỗi JSON **sau khi decrypt** cũng nên được phân loại như một message có payload nghiệp vụ không hợp lệ, thay vì mặc định retry vô hạn. Ví dụ khi sử dụng một `PaymentAuthorized` schema cố định:

~~~java
PaymentAuthorized payment;
try {
    payment = mapper.readValue(plaintext, PaymentAuthorized.class);
} catch (JsonProcessingException ex) {
    throw new AmqpRejectAndDontRequeueException(
            "Decrypted business payload violates schema", ex);
}
paymentService.applyOnce(envelope.eventId(), EXPECTED_TENANT, payment);
~~~

Đoạn này **thay thế** hai câu lệnh đọc JSON + gọi service bên trong `try` của listener mục 7.2; vẫn giữ `finally` để xóa buffer plaintext. Không chạy cả hai phiên bản nối tiếp.

## 8. Retry, dead-letter và idempotency khi payload đã mã hóa

**Mã hóa không làm RabbitMQ trở thành exactly-once.** Một delivery có thể được gửi lại sau khi consumer ghi DB thành công nhưng trước ACK; poison message có thể lặp vô hạn; broker có thể dead-letter khi reject hoặc TTL hết hạn.

### 8.1. Vì sao replay cần lớp bảo vệ riêng?

Giả sử kẻ tấn công hoặc một tiến trình có quyền publish **gửi lại nguyên một envelope hợp lệ**. AES-GCM tag vẫn đúng, vì ciphertext, nonce và AAD không bị sửa. Nếu consumer chỉ kiểm tra tag rồi trừ tiền, cùng một payment có thể bị thực thi nhiều lần.

Giải pháp là **inbox với khóa duy nhất trên business event ID** hoặc business operation ID:

~~~sql
-- PostgreSQL, ví dụ schema nghiệp vụ đích.
CREATE TABLE processed_secure_events (
    tenant_id       TEXT NOT NULL,
    event_id        TEXT NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, event_id)
);
~~~

Trong cùng database transaction với tác động nghiệp vụ, thực hiện insert có điều kiện:

~~~sql
INSERT INTO processed_secure_events(tenant_id, event_id)
VALUES (:tenant_id, :event_id)
ON CONFLICT DO NOTHING;
~~~

Chỉ thực hiện thao tác nghiệp vụ nếu **đã insert thành công một dòng mới**. Nếu transaction rollback, cả dấu vết inbox và thay đổi nghiệp vụ phải rollback. Nếu ACK bị mất sau DB commit, lần redelivery tiếp theo gặp khóa unique và không lặp lại tác dụng phụ.

**Lưu ý:** eventId dùng để dedupe phải được **xác thực bằng AAD/tag**, được ràng buộc đúng tenant và có chính sách ID phù hợp. Không dùng nonce, delivery tag hoặc RabbitMQ correlation ID làm business operation ID mặc định.

### 8.2. DLQ có thể vẫn lộ thông tin

Khi reject message vì không decrypt được, một bản sao ciphertext thường được broker dead-letter sang DLQ. DLQ vẫn có thể chứa:

- `keyId`, `tenantId`, `eventType`, `eventId` không mã hóa.
- Message headers, routing key, exchange và thời điểm nhận.
- Độ dài ciphertext, tần suất event và các thông tin thống kê có thể suy luận.

**Không đưa plaintext vào DLQ hoặc logs khi điều tra lỗi.** Nếu cần cung cấp sample cho đội vận hành, sử dụng envelope nguyên trạng với dữ liệu metadata tối thiểu; quy trình giải mã điều tra nên có quyền riêng, audit đầy đủ và cách xuất kết quả có bảo vệ.

### 8.3. Bảng điều phối lỗi

| Loại lỗi | Ví dụ | Hành động |
| --- | --- | --- |
| **Tampering/format** | Base64 sai, nonce sai kích thước, AEAD tag không hợp lệ. | Không decrypt fallback; quarantine/DLQ, ghi mã lỗi, alert khi tăng. |
| **Không được phép** | Tenant A yêu cầu key của tenant B. | Từ chối, audit bảo mật, không thử các key khác. |
| **Key chưa được đồng bộ** | Producer đã dùng K2 nhưng consumer chưa được cấp K2. | Xem rollout/khóa; tạm giữ/retry giới hạn nếu là deployment lag; không xóa message vội. |
| **KMS outage/throttling** | Timeout hoặc rate limit truy vấn khóa. | Retry có backoff/jitter, giới hạn song song, circuit breaker; giữ message bền vững. |
| **Business schema không hợp lệ** | Dữ liệu sau decrypt thiếu trường bắt buộc. | Reject không requeue hoặc phiên bản/schema migration đã kiểm chứng. |
| **DB transient error** | Deadlock/DB unavailable. | Retry giới hạn; inbox và thao tác DB phải idempotent. |
| **Duplicate hợp lệ** | RabbitMQ redelivery sau khi DB commit. | Inbox xác định đã xử lý, ACK mà không gây tác dụng phụ mới. |

Đặc biệt, **không coi mọi lỗi decrypt là “mã khóa sai, thử cả key cũ”**. Cơ chế brute-force lựa chọn khóa gây rủi ro cross-tenant, làm lộ thông tin về danh sách khóa và tăng tải KMS. Key lookup phải dựa trên **keyId đã kiểm soát và phạm vi tenant**, với các phiên bản được phép.

### 8.4. Khi nào nên re-encrypt trong retry?

| Tình huống | Cách xử lý an toàn |
| --- | --- |
| Broker redeliver cùng delivery vì chưa ACK | Giữ nguyên envelope/ciphertext; decrypt lại rồi kiểm tra inbox. |
| Producer retry vì kết quả publish chưa rõ | Có thể gửi lại **cùng ciphertext** nếu có bản sao lưu bền vững và chính sách cho phép; hoặc encrypt mới bằng **nonce mới**, nhưng giữ eventId. |
| Key cũ sắp retire, còn message đang nằm trong DLQ | Có kế hoạch decrypt/rewrap hoặc re-encrypt an toàn qua quy trình có audit, không tự sửa ciphertext tùy tiện. |
| Metadata AAD cần đổi sau routing/dlq | Không sửa field đã được xác thực trực tiếp. Phát một **envelope mới** bằng encrypt được cấp quyền với metadata mới. |

Đừng lưu plaintext lâu trong outbox chỉ để retry. Nếu outbox lưu ciphertext, phải quản lý **DEK/KEK, thời gian lưu, khả năng decrypt sau rotation và bảo vệ dữ liệu outbox**. Nếu ứng dụng lưu plaintext ở outbox do yêu cầu phục hồi nghiệp vụ, outbox phải được bảo vệ bằng các kiểm soát at-rest và quyền truy cập tương ứng; khi đó broker-blind encryption chưa đồng nghĩa toàn bộ pipeline không có plaintext lưu trữ.

## 9. Header, routing và metadata: bảo mật không chỉ là body

Một thiết kế phổ biến:

~~~text
Exchange: secure.events.x             (public routing alias)
Routing key: secure.payment           (không chứa account/email)
Header: message schema/encryption    (tối thiểu)
Body: ProtectedEnvelope              (payload nhạy cảm là ciphertext)
~~~

**Không đặt trong exchange, queue name, routing key hoặc headers** những dữ liệu như số tài khoản, tên khách hàng, token truy cập, nội dung y tế, địa chỉ chi tiết. Những trường đó có thể hiện trong Management UI, trace, broker logs, policy, DLQ và công cụ theo dõi.

Nếu broker cần định tuyến theo một thuộc tính nhạy cảm, có hai hướng thiết kế:

1. **Tách routing khỏi bí mật:** dùng nhóm không nhạy cảm, mã định tuyến opaque hoặc queue riêng do service tin cậy quản lý.
2. **Đưa quyết định vào consumer tin cậy:** broker gửi message tới service có quyền decrypt, sau đó service quyết định xử lý nội bộ dựa trên dữ liệu nghiệp vụ. Đánh đổi là broker không còn lọc chi tiết và chi phí xử lý có thể tăng.

**Không giả định băm/hash dữ liệu nhạy cảm luôn đủ để ẩn danh.** Các trường có tập giá trị nhỏ như mã tỉnh, loại bệnh, trạng thái tài chính có thể bị suy ra từ hash hoặc tần suất; cần threat modeling về metadata và chọn giải pháp phù hợp.

### 9.1. AAD khi dùng exchange, queue và DLQ

Nếu hợp đồng cần ràng buộc destination, hãy dùng một **destination ID logic bất biến** như `payment-processing-v1` trong AAD. Không dùng tên `receivedExchange` hay `receivedRoutingKey` lấy từ message sau dead-letter nếu chúng có thể đổi khi broker chuyển queue. Người dùng có thể cần giải mã message trong DLQ mà không có đầy đủ thông tin routing ban đầu.

Đồng thời, nếu một producer được quyền publish cùng ciphertext đến nhiều queue, cần xác định người nhận nào được cấp khóa. **Mã hóa không ngăn một consumer có khóa truy cập message được route nhầm tới nó**; phân quyền KMS và RabbitMQ vẫn cần thiết.

### 9.2. Nén trước khi mã hóa?

Nén plaintext **trước** encrypt có thể giảm kích thước khi payload lớn, nhưng có nguy cơ **rò rỉ qua kích thước** khi nội dung bí mật được nén cùng dữ liệu có thể điều khiển bởi kẻ tấn công. Cần đánh giá theo threat model (đặc biệt với nội dung secret và attacker-controlled input trong cùng khối). Không tự bật `gzip + AES` cho dữ liệu rất nhạy cảm chỉ vì tiết kiệm băng thông. Sau encrypt, ciphertext gần như không nén được hữu ích.

Nếu vẫn sử dụng compression, ghi version/algorithm nén trong envelope được xác thực, giới hạn tỷ lệ giải nén/kích thước để chống decompression bomb, và không fallback sang giải nén bất kỳ từ dữ liệu không tin cậy.

## 10. TLS, xác thực và phân quyền vẫn bắt buộc

Ngay cả khi ciphertext được mã hóa từ đầu tới cuối, broker vẫn cần kiểm soát:

- **TLS với certificate validation** cho producer và consumer, tránh nghe lén credentials và metadata. Với hệ thống cần đảm bảo danh tính client mạnh, cân nhắc **mTLS**.
- **Tài khoản RabbitMQ riêng** theo vai trò; không dùng default `guest` trong production. Hạn chế quyền configure/write/read theo exchange/queue/vhost.
- **Không trao quyền đọc queue** cho ứng dụng không cần thiết; E2E encryption là lớp bảo vệ bổ sung, không thay thế ACL.
- **KMS IAM** riêng với RabbitMQ permissions. Một tài khoản có thể publish nhưng không được decrypt; chỉ consumer tin cậy có decrypt permission.
- **Phân tách môi trường** dev/staging/prod và tenant; không dùng chung key production trong test.
- **Không xuất khóa** qua health endpoint, diagnostic dump, config endpoint, actuator, exception hoặc thread dump nếu tránh được.

Ví dụ Spring Boot 3.x kết nối RabbitMQ TLS bằng cấu hình **minh họa**:

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal
    port: 5671
    username: secure-publisher
    password: ${RABBITMQ_PASSWORD}
    ssl:
      enabled: true
      validate-server-certificate: true
      verify-hostname: true
~~~

Sự hỗ trợ/đặt tên của TLS properties tùy **dòng Spring Boot**; đối chiếu reference config metadata của phiên bản thực tế và cấu hình truststore/keystore hoặc SSL bundle theo môi trường. Không triển khai TLS chỉ bằng `ssl.enabled=true` mà bỏ qua kiểm chứng certificate chain và hostname.

**Lưu ý về quyền broker:** quyền publish, consume và khai báo topology là khác nhau. Nếu service chỉ publish tới exchange, không cấp quyền xóa queue hoặc đọc mọi queue trong vhost. Nếu service chỉ consume, không cấp quyền publish rộng trừ khi có yêu cầu reply/forward rõ ràng.

## 11. Quan sát mà không làm lộ plaintext

Trên đường gửi/nhận bảo mật, nên có **metrics** về tính sẵn sàng, không chứa bí mật:

| Metric/tín hiệu | Ý nghĩa | Cardinality |
| --- | --- | --- |
| `secure_message_encrypt_total{result}` | Số lần encrypt thành công/thất bại. | `result` thuộc tập hữu hạn. |
| `secure_message_decrypt_total{result}` | Decrypt thành công, bad_tag, forbidden, unknown_key. | Không gắn eventId vào metric. |
| `secure_message_key_lookup_latency` | Thời gian truy vấn key/KMS. | Nhãn key family hoặc tenant group có giới hạn. |
| `secure_message_kms_error_total{kind}` | KMS unavailable, throttling, permission denied. | Tập kind nhỏ, ổn định. |
| `secure_message_dlq_depth` | Message bảo mật bị reject/chờ điều tra. | Theo queue/broker được kiểm soát. |
| `secure_message_business_completion_latency` | Độ trễ từ event nguồn tới hoàn tất nghiệp vụ. | Theo loại sự kiện/nhóm khách hàng ít cardinality. |

Một log thất bại hợp lý:

~~~json
{
  "severity": "WARN",
  "event": "secure_message.decrypt_rejected",
  "reason": "AEAD_TAG_INVALID",
  "broker": "orders",
  "queue": "secure.payment.q",
  "eventId": "evt-2026-000129",
  "envelopeVersion": "1",
  "keyAlias": "finance-payload",
  "traceId": "trace-example"
}
~~~

**Không log `bankAccountNumber`, `plaintext`, `ciphertext` nguyên vẹn, khóa thô hoặc `wrappedDEK`** trong luồng ứng dụng mặc định. Tùy chính sách, `eventId` và `keyId` cũng có thể là metadata cần bảo vệ; giới hạn log, masking hoặc sử dụng opaque IDs.

Nếu logging framework tự log `Message.toString()`, exception hoặc payload cho debug, phải kiểm tra **logging interceptor, message converter và lỗi serializing**. Một điểm lộ plaintext trong debug log có thể vô hiệu hóa nỗ lực mã hóa đầu cuối.

Đối với tracing, propagation headers thường không được mã hóa cùng body; **không đưa số tài khoản, tên bệnh nhân hay secret vào baggage/span attributes**. Trace ID dùng để tương quan, không phải bí mật.

### 11.1. Cảnh báo an toàn

Nên cảnh báo khi:

- `AEAD_TAG_INVALID` tăng bất thường (có thể do lỗi triển khai hoặc tampering).
- `UNKNOWN_KEY` tăng sau deployment/rotation.
- `KMS_UNAVAILABLE` dẫn tới consumer backlog và deadline bị vượt.
- Nhiều message dùng khóa sắp retire nhưng vẫn nằm trong DLQ.
- Phát hiện ciphertext/plaintext ngoài ý muốn trong queue, logs, backups hoặc tracing.
- Producer tạo số lần encrypt gần giới hạn dùng khóa/nonce được quy định.

Các cảnh báo phải phân biệt **lỗi bảo mật**, **lỗi cấu hình khóa** và **lỗi hạ tầng**. Đừng tự động retry liên tục một ciphertext có bad tag; cũng đừng xóa ngay message không decrypt được khi có thể là lỗi phân phối khóa tạm thời.

## 12. Kiểm thử: không chỉ kiểm tra round-trip

Một phép thử mã hóa–giải mã thành công **không đủ chứng minh thiết kế an toàn**. Phải kiểm tra chống sửa, replay, phân quyền, failure mode và mối quan hệ với RabbitMQ.

### 12.1. Unit test crypto với khóa chỉ dùng trong test

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

import javax.crypto.AEADBadTagException;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class AesGcmEnvelopeCryptoTest {

    @Test
    void roundTripAndRejectTamperedAad() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey demoKey = generator.generateKey();

        TenantKeyResolver keys = new TenantKeyResolver() {
            @Override
            public EncryptionKey activeForEncryption(String tenantId) {
                if (!"tenant-A".equals(tenantId)) {
                    throw new SecurityException("Tenant not allowed");
                }
                return new EncryptionKey("key-test-1", demoKey);
            }

            @Override
            public SecretKey forDecryption(String tenantId, String keyId) {
                if (!"tenant-A".equals(tenantId)
                        || !"key-test-1".equals(keyId)) {
                    throw new SecurityException("Key not allowed");
                }
                return demoKey;
            }
        };

        AesGcmEnvelopeCrypto crypto = new AesGcmEnvelopeCrypto(keys);
        byte[] plaintext = "SENSITIVE-TEST-DATA"
                .getBytes(StandardCharsets.UTF_8);

        ProtectedEnvelope envelope = crypto.encrypt(
                plaintext, "tenant-A", "evt-001", "payment.authorized");

        assertArrayEquals(plaintext,
                crypto.decrypt(envelope, "tenant-A"));

        // Chỉ đổi metadata eventType. AAD không còn đúng -> bad tag.
        ProtectedEnvelope tampered = new ProtectedEnvelope(
                envelope.version(), envelope.algorithm(), envelope.keyId(),
                envelope.nonceB64(), envelope.ciphertextB64(),
                envelope.eventId(), envelope.tenantId(), "payment.refunded");

        assertThrows(AEADBadTagException.class,
                () -> crypto.decrypt(tampered, "tenant-A"));
        assertThrows(java.security.GeneralSecurityException.class,
                () -> crypto.decrypt(envelope, "tenant-B"));

        // Test key chỉ nằm trong bộ nhớ của bài kiểm thử.
        Arrays.fill(plaintext, (byte) 0);
    }
}
~~~

Test xác minh payload thay đổi trong AAD sẽ làm GCM tag sai. Cần thêm test **thay một byte ciphertext**, **sai nonce**, **đổi keyId**, **Base64 hỏng**, **message quá lớn** và **khóa không được cấp quyền**. Test ở trên **không kiểm chứng** KeyResolver/KMS thực tế, giới hạn số lần encrypt một key hoặc chính sách replay; chúng có bộ test riêng.

### 12.2. Ma trận kiểm thử tích hợp

| Kịch bản | Điều kiểm tra | Kết quả kỳ vọng |
| --- | --- | --- |
| Publish message mã hóa hợp lệ | Exchange–binding–queue, envelope, listener. | Consumer decrypt thành công và ghi nghiệp vụ đúng một lần. |
| Người xem queue bằng Management UI | Chỉ thấy ciphertext và metadata cho phép. | Không nhìn thấy số tài khoản hoặc JSON nghiệp vụ plaintext. |
| Thay một byte ciphertext trong bản test | AEAD verification. | Reject không chạy business service; ghi nhận lỗi bảo mật. |
| Sửa `tenantId`/`eventId`/`eventType` | AAD integrity và expected tenant. | Decrypt thất bại; không cho thay đổi key/tenant để vượt quyền. |
| Chèn cùng message hợp lệ hai lần | Replay và inbox. | Chỉ một tác dụng phụ nghiệp vụ. |
| Producer retry vì mất confirm | EventId cố định và idempotency. | Không tạo payment/task trùng. |
| Consumer mất DB trước commit | Transaction và ACK/retry. | Message có thể redeliver, không mất tác vụ vĩnh viễn. |
| Chặn KMS tạm thời | Retry/backoff/quarantine. | Không giả định ciphertext giả mạo; không hot-loop vô hạn. |
| Rotate từ K1 sang K2 | Encrypt mới bằng K2, decrypt cũ bằng K1. | Message cũ trong queue/DLQ vẫn đọc được tới khi hết retention. |
| Tắt quyền decrypt tenant A đối với key B | Authorization tại key resolver. | Deny/audit, không thử key khác. |
| Chuyển message vào DLQ | Body và metadata trong DLQ. | Không có plaintext nhạy cảm xuất hiện. |
| In log ở DEBUG và khi exception | Logger/converter/interceptor. | Không lộ plaintext, key hoặc secret trong log/trace. |
| Broker thiếu RAM/đĩa và phục hồi | Backpressure, outbox, confirm/return. | Không tự xóa message; retry an toàn sau khi phục hồi. |

Khi thử trên RabbitMQ thật, sử dụng môi trường test riêng hoặc Testcontainers, **không dùng dữ liệu cá nhân thật**. Có thể dùng dữ liệu giả, tokenized values và test keys do fixture tạo. Không lưu dump queue chứa khóa thực vào artifact kiểm thử.

## 13. Bài thực hành vận dụng

**Bối cảnh:** Service Thanh toán nhận một kết quả thanh toán từ hệ thống nội bộ và cần publish `payment.authorized` cho service Kế toán. Message có số tài khoản ngân hàng và giá trị tiền; RabbitMQ cùng đội vận hành không được đọc payload. Kế toán phải tạo một bản ghi duy nhất cho mỗi event, kể cả khi message bị giao lại.

**Yêu cầu:**

1. Xác định source/consumer tin cậy, ai được truy cập RabbitMQ và KMS, dữ liệu nào cần được mã hóa và metadata nào có thể lộ.
2. Khai báo `secure.events.x`, `secure.payment.q` và binding; cấu hình DLQ để tránh mất dấu các message không xử lý được.
3. Triển khai `TenantKeyResolver` dùng KMS/secret test phù hợp, không hard-code khóa vào Git; hỗ trợ K1 và K2.
4. Gửi `PaymentAuthorized` bằng `ProtectedPaymentPublisher`. Kiểm tra trong queue body chỉ có envelope/ciphertext, không có số tài khoản plaintext.
5. Dùng `ProtectedPaymentListener` để kiểm tra AAD và decrypt; trước khi ghi DB, xác thực tenant/schema và áp dụng idempotency theo `(tenantId,eventId)`.
6. Cố ý thay ciphertext, nonce, eventId, eventType, keyId hoặc tenantId. Đối chiếu lỗi và hành vi reject/quarantine tương ứng, không để side effect được thực thi.
7. Tắt khả năng truy cập KMS của consumer trong thời gian ngắn; bảo đảm lỗi tạm thời được retry có giới hạn và sau khi KMS trở lại có thể xử lý tiếp.
8. Rotate K1 → K2: producer dùng K2, consumer vẫn hỗ trợ decrypt K1 trong thời gian DLQ/retention.
9. Gửi lại chính xác cùng envelope đã xử lý; chứng minh inbox chỉ cho phép một tác dụng phụ.
10. Kiểm tra debug log, trace, metrics, backup queue/DLQ và dashboard không xuất hiện plaintext hay khóa.

### Câu hỏi tự kiểm tra

**Câu 1.** Producer kết nối RabbitMQ qua TLS 1.3; RabbitMQ lưu message dạng JSON chứa số tài khoản. Đã đạt mục tiêu broker không đọc payload chưa?

**Đáp án:** Chưa. TLS bảo vệ lưu lượng giữa các endpoint, nhưng broker kết thúc TLS rồi thấy plaintext. Cần mã hóa payload **trước** `RabbitTemplate.send`, chỉ consumer tin cậy có khóa decrypt.

**Câu 2.** Nonce của AES-GCM có phải secret không? Có thể dùng lại nonce sau khi service restart không?

**Đáp án:** Nonce không cần bí mật, nhưng **không được lặp cặp (key, nonce) giữa các lần encrypt**. Dùng nonce ngẫu nhiên 96 bit với giới hạn số lần encrypt/rotation hoặc chiến lược sinh nonce duy nhất được thiết kế chặt; không reset counter thiếu phối hợp xuyên replica/restart.

**Câu 3.** Message mã hóa và AEAD tag đều đúng. Vì sao vẫn cần idempotency?

**Đáp án:** AES-GCM **không chặn replay**. Một ciphertext hợp lệ có thể được gửi hoặc redeliver nhiều lần; consumer phải dùng business event ID đã xác thực để chống tác dụng phụ trùng lặp.

**Câu 4.** Producer đặt email khách hàng trong routing key rồi mã hóa body. Có bảo vệ được email trước broker không?

**Đáp án:** Không. Exchange, routing key và headers thường vẫn hiển thị với broker/công cụ vận hành. Dùng alias/nhóm định tuyến không nhạy cảm hoặc chuyển quyết định dựa trên email về consumer tin cậy.

**Câu 5.** Sau key rotation, message cũ trong DLQ không giải mã được. Có thể xóa K1 vì producer đã chuyển sang K2?

**Đáp án:** Không nên. Khóa cũ cần ở chế độ decrypt-only trong thời hạn xử lý dữ liệu cũ, hoặc phải re-encrypt/rewrap có kiểm soát trước khi retire. Việc cắt quyền decrypt quá sớm làm mất khả năng phục hồi nghiệp vụ.

**Câu 6.** KMS đang outage, listener không lấy được khóa. Có nên coi mọi exception là bad tag và reject không requeue?

**Đáp án:** Không. Cần phân biệt **sai tính toàn vẹn hoặc không có quyền** với **sự cố KMS tạm thời**, rồi áp dụng retry/backoff, DLQ/quarantine và cảnh báo tương ứng.

**Câu 7.** Có thể dùng cùng AES key cho nhiều producer không?

**Đáp án:** Có thể về mặt kỹ thuật nếu quản lý nonce và quyền rất chặt, nhưng tất cả bên sở hữu khóa có thể tạo ciphertext hợp lệ, nên không xác thực được producer cụ thể. Với yêu cầu phân tách quyền hoặc truy nguyên nguồn, nên có khóa riêng theo domain/producer hoặc chữ ký nguồn phù hợp.

## 14. Checklist trước khi đưa lên production

- [ ] Có **threat model** chỉ rõ broker/operator có được đọc plaintext hay không, dữ liệu được bảo vệ từ đâu đến đâu.
- [ ] Không đưa PII/secret vào routing key, headers, logs, tracing hoặc metric tags.
- [ ] Dùng **AES-GCM hoặc AEAD chuẩn**, khóa sinh ngẫu nhiên, authentication tag đủ mạnh và AAD canonical.
- [ ] Nonce được sinh mới với mỗi phép encrypt, có **usage limits và rotation** theo key.
- [ ] Dùng **KMS/HSM hoặc hệ quản lý secret phù hợp**, kiểm soát quyền decrypt theo tenant/service và audit.
- [ ] Version envelope, thuật toán, key ID và metadata được **xác thực bằng AAD**.
- [ ] Chặn input quá lớn, thuật toán không hỗ trợ, Base64 lỗi và schema không hợp lệ; không fallback sang plaintext.
- [ ] Lỗi tampering, thiếu quyền, thiếu key và KMS outage được **phân loại riêng**.
- [ ] RabbitMQ dùng TLS, xác thực server, user/vhost permissions tối thiểu và phân vùng môi trường.
- [ ] Producer có cơ chế **publisher confirm/return** và lưu công việc cần phát vào outbox nếu không thể mất.
- [ ] Consumer **idempotent**, có retry giới hạn và DLQ/quarantine không làm lộ plaintext.
- [ ] Key cũ vẫn decrypt được dữ liệu cũ cho đến khi hết queue/DLQ/backup/retention hợp lệ.
- [ ] Có bài test sửa ciphertext/AAD, replay, broker crash, KMS outage và key rotation.
- [ ] Alert và runbook đủ để ứng phó tampering, key compromise và lỗi vận hành.

## 15. Tổng kết

Khi Spring AMQP vận chuyển dữ liệu nghiệp vụ nhạy cảm, **TLS bảo vệ kết nối nhưng không làm RabbitMQ “mù” với body**. Nếu yêu cầu bảo vệ đầu cuối khỏi broker hoặc các hệ thống trung gian, producer cần **mã hóa payload trước khi publish** và consumer chỉ giải mã sau khi nhận bằng khóa được cấp quyền. Cách tiếp cận phù hợp là **AEAD (AES-GCM)** với nonce không lặp, AAD xác thực metadata, envelope có version/key ID và **KMS/HSM** quản lý vòng đời khóa.

Song song, vẫn cần exchange–queue–binding và bảo mật RabbitMQ, **publisher confirms/returns, ACK, retry, DLQ, idempotency, outbox và quan sát** để đạt độ tin cậy. **Mã hóa giải quyết bí mật và toàn vẹn dữ liệu; nó không tự giải quyết routing, replay, exactly-once, authentication hay trạng thái nghiệp vụ cuối cùng.**

### Tài liệu tham khảo chính thức

- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html) — threat model, AEAD, lựa chọn thuật toán, quản lý khóa, envelope encryption.
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html) — nonce uniqueness, vòng đời và usage limits, rotation/rewrap.
- [Oracle Java Cryptography Architecture (JCA) Reference Guide](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html) — `AES/GCM/NoPadding`, `GCMParameterSpec`, `updateAAD`.
- [Oracle Cipher API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/javax/crypto/Cipher.html) — AEAD tag và yêu cầu nonce/IV duy nhất.
- [RabbitMQ TLS Support](https://www.rabbitmq.com/docs/ssl) — TLS, xác minh chứng chỉ, mTLS và bảo mật kết nối.
- [RabbitMQ Access Control](https://www.rabbitmq.com/docs/access-control) — user, vhost, configure/write/read permissions.
- [Spring AMQP RabbitTemplate](https://docs.spring.io/spring-amqp/reference/amqp/template.html) — `send`, message, confirms/returns và publishing.
- [Spring AMQP Asynchronous Consumer](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html) — `@RabbitListener`, listener container, ACK/error handling.
