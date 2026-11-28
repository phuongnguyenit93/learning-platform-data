# Không lưu key trong log – Ngăn rò rỉ vật liệu khóa qua nhật ký và hệ thống quan sát

**Không lưu key trong log** là nguyên tắc **không ghi vật liệu khóa mật mã bí mật** — như **DEK, KEK, private key, HMAC key, seed, password pepper, recovery secret** — vào application log, audit log, trace, metrics, bản ghi lỗi, CI/CD output hoặc bất kỳ kênh quan sát nào không được thiết kế để bảo vệ chính vật liệu khóa đó. Thay vì in dữ liệu bí mật, hệ thống cần ghi **sự kiện đã được phân loại, định danh khóa phù hợp, hành động, kết quả, mã lỗi và request/correlation ID**.

Trong chương **Key storage** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, quy tắc này gắn trực tiếp với toàn bộ vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy khóa**, đồng thời kết nối mật mã đối xứng, bất đối xứng, chữ ký số, **KMS/HSM**, envelope encryption, kiểm soát truy cập và kiểm toán.

> **Điểm mấu chốt:** Một khóa được bảo vệ tốt trong KMS/HSM vẫn có thể bị lộ nếu **bản sao plaintext DEK**, private key nhập khẩu, secret dùng cho MAC hoặc token có quyền ký bị ghi vào log. **Log là nơi lưu dữ liệu có vòng đời, bản sao, quyền truy cập và nhà cung cấp riêng**; không được xem log như một vùng nhớ tạm “chỉ để debug”.

## 1. Vì sao ghi key vào log nguy hiểm?

Giả sử Billing Service dùng **AES-256-GCM** với một DEK được KMS cấp. Để điều tra lỗi giải mã, developer thêm dòng:

~~~java
// SAI: có nguy cơ lộ data-encryption key.
logger.info("Generated DEK: " + java.util.Base64.getEncoder()
        .encodeToString(plaintextDek));
~~~

Log có thể được chuyển từ container sang log agent, tập trung tại một hệ thống quan sát, đưa vào dashboard, export sang dịch vụ thứ ba, đính kèm ticket hỗ trợ hoặc tồn tại trong backup trong thời gian dài. **Một lỗi debug trong vài phút có thể tạo nhiều bản sao của khóa**.

Hậu quả không dừng ở bí mật của một request:

- Nếu đó là **DEK**, ai lấy được khóa và ciphertext tương ứng có thể thử giải mã dữ liệu.
- Nếu đó là **KEK/wrapping key**, nguy cơ có thể lan sang nhiều DEK được bọc dưới KEK đó.
- Nếu đó là **private signing key**, người có khóa có thể tạo chữ ký mật mã hợp lệ, buộc hệ thống phải đánh giá lại trust và các chữ ký trong khoảng ảnh hưởng.
- Nếu đó là **HMAC key/PSK**, bên ngoài có thể tạo MAC hoặc giả mạo một bên biết cùng secret.
- Nếu đó là **seed hoặc recovery material**, một giá trị có thể tái tạo nhiều khóa khác nhau.
- Nếu đó là **workload credential/token KMS**, kẻ tấn công có thể gọi API Sign/Decrypt/Unwrap trong phạm vi quyền và thời gian còn hiệu lực, dù không lấy được raw key.

### 1.1. Ranh giới bảo mật bị phá vỡ như thế nào?

~~~mermaid
flowchart TD
    APP["Ứng dụng với DEK rõ tạm thời"] --> KMS["KMS/HSM bảo vệ KEK"]
    APP --> GOOD["Chỉ dùng DEK để mã hóa/giải mã"]
    APP --> BAD["LỖI: log DEK hoặc KMS response"]
    BAD --> AGENT["Log agent / stdout / collector"]
    AGENT --> STORE["Log storage, APM, SIEM"]
    STORE --> BACKUP["Archive, export, backup"]
    STORE --> USERS["Người xem dashboard / support"]
    BACKUP --> ATTACKER["Nguy cơ sao chép/chiếm đoạt"]
    USERS --> ATTACKER
~~~

**KMS IAM bảo vệ lệnh sử dụng key tại KMS; IAM đó không nhất thiết áp dụng cho các bản sao đã xuất hiện trong log storage.** Nếu developer in raw DEK, một người chỉ có quyền đọc log có thể nhận được bí mật mà họ vốn **không được phép lấy từ KMS**.

### 1.2. Đặc biệt nguy hiểm khi log được sao lưu lâu hơn khóa

Một phiên DEK có thể chỉ tồn tại trong RAM vài mili giây; log chứa DEK có thể lưu **90 ngày hoặc nhiều năm** theo chính sách vận hành. Việc **rotate hoặc disable KEK** sau đó không tự xóa được DEK đã bị lộ trong log.

**Độ dài khóa không giảm thiểu rủi ro này.** Một AES-256 key bị lộ vẫn là secret đã bị lộ, không phải một khóa an toàn hơn chỉ vì có 256 bit.

## 2. Phân loại giá trị: cái gì tuyệt đối không log, cái gì cần cân nhắc?

Không phải mọi thông tin liên quan đến khóa đều là **key material**, nhưng cũng không phải mọi metadata đều nên công khai.

| Giá trị | Có nên đưa vào log? | Lý do và hướng thay thế |
| --- | --- | --- |
| **Raw DEK/AES secret** | **Không.** | Có thể trực tiếp giải mã dữ liệu; ghi key ID/version và operation thay thế. |
| **Raw KEK/master/wrapping key** | **Không.** | Có thể mở nhiều DEK; không export chỉ để debug. |
| **Private key RSA/ECDSA/Ed25519, PKCS#8 PEM/DER** | **Không.** | Có thể giả mạo chữ ký hoặc giải mã theo key usage. |
| **HMAC/KMAC key, PSK, password pepper** | **Không.** | Bên nhận có thể giả mạo/xác thực trái phép hoặc thử tấn công vào dữ liệu liên quan. |
| **Seed, entropy state, recovery shares** | **Không.** | Có thể tạo lại key material; recovery shares thuộc quy trình đặc quyền riêng. |
| **KMS token, cloud credential, secret manager value** | **Không.** | Không phải key mật mã trong mọi trường hợp, nhưng có thể cấp quyền truy cập KMS/secret. |
| **Plaintext dữ liệu, password, bearer JWT/session token** | **Không theo mặc định.** | Dữ liệu/credential nhạy cảm, đôi khi cho phép thực thi hành động như người dùng. |
| **Wrapped DEK/ciphertext** | **Tránh log toàn bộ.** | Không phải DEK rõ, nhưng có thể nhạy cảm, rất lớn và gắn với dữ liệu cá nhân. |
| **Nonce/IV, tag, salt** | **Không phải secret; vẫn hạn chế.** | Thường được lưu đúng chỗ cùng ciphertext/verifier; log toàn bộ không cần thiết. |
| **Public key/chứng chỉ** | **Có thể, theo nhu cầu và policy.** | Public key không bí mật; kiểm tra provenance/identity và không log certificate chain vô tội vạ. |
| **Public-key fingerprint** | **Thường có thể dùng trong audit được bảo vệ.** | Ví dụ SHA-256 trên SPKI DER; không tự chứng minh owner hoặc trust. |
| **Key ID, alias, material version** | **Có điều kiện.** | Là metadata, có thể tiết lộ tenant, kiến trúc hoặc tên tài sản quan trọng; dùng reference đã phân loại. |
| **Operation, outcome, reason code, request ID** | **Nên có.** | Hữu ích cho bảo mật/vận hành nếu schema đã được cho phép và không chứa dữ liệu tự do. |
| **Encryption context/AAD** | **Không log nguyên khối.** | Có thể chứa tenant, object ID và PII; một số KMS cũng ghi context vào audit. |

**Nguyên tắc phân loại:** phân biệt **bí mật mật mã**, **bí mật xác thực**, **metadata mật mã** và **dữ liệu nghiệp vụ**. Không nên chỉ dùng regex `key` để quyết định: `keyId` thường là định danh; `privateKey` là secret; `apiKey` có thể là credential cần giữ bí mật.

### 2.1. Hash khóa rồi log có an toàn không?

Không nên mặc định **SHA-256(secretKey)** là phương pháp logging an toàn:

- Nếu bí mật entropy thấp, hash có thể trở thành dữ liệu để **dò ngoại tuyến**.
- Hash ổn định có thể liên kết hoạt động giữa nhiều tenant hoặc hệ thống ngoài chủ đích.
- Nếu hàm băm được dùng sai ngữ cảnh hoặc việc tính hash đòi hỏi **export raw key**, hành động đó tự tạo đường lộ.
- Một fingerprint public key và hash của một **symmetric secret** là hai trường hợp khác nhau.

Thay vào đó, log **opaque key reference hoặc inventory ID được cấp sẵn** và giới hạn quyền xem. Với khóa non-exportable, **không export key chỉ để tạo fingerprint**. Khi cần tra cứu dấu vết public key, dùng fingerprint của **biểu diễn public key đã quy định**.

### 2.2. Vì sao wrapped DEK cũng không nên log tùy tiện?

Wrapped DEK là **ciphertext bảo vệ một khóa**, thường có thể được lưu cùng bản mã. Nó **không tự là plaintext DEK**. Tuy nhiên:

- Log wrapped DEK làm tăng số bản sao vật liệu mã hóa và có thể tiết lộ metadata.
- Nếu KEK/KMS credential bị compromise sau đó, các bản sao mới có thể trở thành dữ liệu đầu vào để mở DEK.
- Một số provider blob chứa key reference, context hoặc thông tin liên kết nhạy cảm.
- Một log lớn chứa wrapped DEK có thể gây tăng chi phí và khó đáp ứng retention/xóa dữ liệu.

**Hãy log một ID của encrypted object hoặc backup manifest**, không log nguyên wrapped key. Chỉ khi có một quy trình chẩn đoán đặc biệt đã phê duyệt mới cân nhắc thu thập blob vào **kho chứng cứ an toàn** với quyền/retention riêng, không phải log thông thường.

## 3. Những đường rò rỉ trực tiếp và gián tiếp

Developer thường kiểm tra `logger.info(secret)` nhưng bỏ sót nhiều đường khác.

### 3.1. Application logs

~~~java
// SAI: println, format, debug đều có thể đi vào log collector.
System.out.println("AES key = " + secretKey);
logger.fine("KMS result = " + response);
logger.warning("decrypt failed, dek=" + java.util.Arrays.toString(dek));
~~~

Các biến có tên không rõ ràng như `payload`, `credentials`, `material`, `context` cũng có thể chứa secret. **Đừng kỳ vọng tên biến nói cho log framework biết dữ liệu cần che**.

### 3.2. ToString, JSON serialization và log request/response

~~~text
KHÔNG AN TOÀN:
  log.debug("request={}", entireRequest)
  log.debug("response={}", kmsResponse)
  log.error("failed: " + exception)
  trace.setAttribute("kms.response", serialize(response))

AN TOÀN HƠN:
  log eventType + keyRef từ registry + operation + result + reasonCode
  liên kết requestId để điều tra ở hệ thống được phân quyền
~~~

Một record/DTO KMS có thể chứa `plaintextDek` lẫn `wrappedDek`. Nếu log object hoặc JSON serialize toàn bộ response, framework có thể xuất nhiều trường hơn developer dự kiến.

**Không dựa vào `toString()` hiện tại của một thư viện** để bảo đảm an toàn: phiên bản SDK mới có thể thêm fields, thay formatter hoặc hiển thị dữ liệu khác. Quy tắc tốt hơn là **không đưa DTO chứa secret vào logging API ngay từ đầu**.

### 3.3. Exceptions và stack traces

Một lỗi có thể làm lộ thông tin qua:

- `exception.getMessage()` do provider hoặc ứng dụng tạo.
- `Throwable.toString()`, `printStackTrace()` và logger kèm đối tượng exception.
- HTTP client exception chứa request body, header hoặc URL.
- Wrapper exception được xây từ giá trị key hoặc `Base64(secret)`.
- Error page trả trực tiếp stack trace cho client.

**Không phải mọi stack trace đều chứa secret**; tuy nhiên không thể bảo đảm các thông báo tự do từ SDK/HTTP layer luôn được lọc. Với thao tác chứa key material, nên **ánh xạ lỗi vào reason code được phép** rồi lưu correlation ID để điều tra qua kênh bảo mật chuyên biệt.

### 3.4. Distributed tracing và APM

Một số công cụ quan sát tự thu thập:

- HTTP request/response body, headers, query strings.
- Exception events và stack traces.
- Method arguments hoặc return values do instrumentation thu thập.
- Span attributes/baggage của giao thức tracing.
- Thông tin database query, job queue payload hoặc workflow variables.

**Không đặt secret vào span attribute, baggage, metric labels hoặc request tags**. Trace và metrics thường có chính sách truy cập/retention khác application log. Nếu APM tự động bắt body cho endpoint quản lý khóa, cần **cấu hình loại trừ tại nguồn**, không chỉ xóa ở dashboard.

### 3.5. CI/CD, debug và môi trường vận hành

Khóa có thể lộ qua:

- Pipeline bật `set -x`, echo biến môi trường hoặc in output secret manager.
- Build artifact có chứa `.env`, keystore, private PEM hoặc file config.
- IaC state/plan output chứa raw secret khi sử dụng sai công cụ.
- Container logs khi startup dump toàn bộ config.
- HTTP wire logging của SDK KMS/secret manager.
- Crash dump, heap dump, debugger snapshot hoặc profiler **không phải log truyền thống nhưng có thể chứa key trong bộ nhớ**.
- Báo cáo test lỗi in ra expected/actual chứa plaintext key.

**Bật debug có thời hạn không phải cơ chế bảo vệ secret.** Một request debug duy nhất có thể được sao chép đến nhiều hệ thống và tồn tại sau khi tắt debug.

## 4. Tư duy đúng: log sự kiện, không log đối tượng bí mật

Với KMS/HSM, nhiều câu hỏi vận hành chỉ cần biết:

- Workload nào đã gọi API?
- Key reference nào được sử dụng?
- Phép toán là `GenerateDataKey`, `DecryptDataKey`, `Sign`, `Rotate` hay `Disable`?
- Kết quả **thành công, bị từ chối hay lỗi hạ tầng**?
- Policy/version và thời điểm nào?
- Incident/request/correlation ID nào để truy tiếp nguồn dữ liệu an toàn?
- Có dấu hiệu bất thường về tần suất, principal, môi trường hoặc loại dữ liệu không?

**Không câu hỏi nào bắt buộc phải in DEK rõ hoặc private signing key vào log.**

### 4.1. Tạo allowlist trường audit

Một **allowlist** là danh sách trường được phép ghi, thay vì thu nhận mọi trường rồi cố tìm secret để xóa.

| Trường đề xuất | Ví dụ | Yêu cầu |
| --- | --- | --- |
| `eventType` | `KEY_OPERATION` | Enum/canonical value do server định nghĩa. |
| `operation` | `DECRYPT_DATA_KEY` | Không lấy raw operation string từ input chưa kiểm tra. |
| `outcome` | `DENIED` | Giá trị chuẩn hóa: SUCCESS/DENIED/FAILED. |
| `reasonCode` | `POLICY_DENIED` | Không chứa exception message tự do. |
| `actorRef` | `billing-prod-workload` | Từ danh tính đã xác thực, được lọc theo quyền truy cập. |
| `keyRef` | `billing-kek` | Reference được phê duyệt; có thể pseudonymize tùy phân loại. |
| `requestId` | UUID do server cấp | Không chứa token, user input hoặc PII. |
| `policyVersion` | `billing-key-policy-v3` | Giúp truy xuất quyết định khi sự cố. |
| `timestamp` | ISO-8601 UTC | Dùng đồng hồ có kiểm soát và chuẩn thời gian. |

Bản ghi nên **giữ nhất quán schema**, tránh phát sinh tên field tùy ý. Có thể dùng nguồn audit của provider cho hoạt động KMS và audit ứng dụng cho quyền trên dữ liệu, sau đó liên kết bằng **correlation ID an toàn**.

### 4.2. Ví dụ sự kiện được phép

~~~json
{
  "eventType": "KEY_OPERATION",
  "service": "billing-service",
  "environment": "production",
  "operation": "DECRYPT_DATA_KEY",
  "keyRef": "billing-kek",
  "outcome": "DENIED",
  "reasonCode": "POLICY_DENIED",
  "policyVersion": "billing-key-policy-v3",
  "requestId": "4d37bc85-9c28-40ea-9b11-5562b5be0e7a"
}
~~~

**Mẫu trên là dữ liệu giả, không phải log KMS thật.** Nó đủ để xem **dịch vụ nào bị từ chối và do chính sách nào**, đồng thời không chứa key material, encrypted key blobs, request body hay plaintext.

### 4.3. Một event nên có những gì để phân biệt tenant?

Trong hệ thống multi-tenant, không nên mặc định ghi tenant ID thật, email hoặc account number vào log. Có thể dùng **opaque tenant reference** hoặc mã phân vùng đã được tổ chức phê duyệt, lưu bản đồ giải mã định danh thật ở hệ có quyền riêng.

Nếu một trường key alias có tên chứa **tên khách hàng**, việc log alias cũng có thể làm lộ PII. Lúc đó dùng **inventory ID** hoặc resource handle đã được phân loại, không ghi trực tiếp nhãn người dùng đặt.

## 5. Java 17: ghi audit an toàn cho thao tác KMS

Ví dụ dưới đây dùng **Java 17** và thư viện chuẩn `java.util.logging`. Nó tập trung vào thiết kế **event có kiểu (typed event) và allowlist field**, tránh truyền KMS response, `byte[]` secret hay exception message vào logger.

- `Action`, `Outcome`, `Reason`, `KeyPurpose` là enum chỉ có giá trị đã biết.
- `requestId` do server cấp dưới dạng UUID.
- `keyRef` trong log là **logical key purpose**, không phải raw key hay endpoint.
- Adapter `KmsClient` là giao diện giả định: khi triển khai phải dùng SDK và workload identity được cấp quyền.
- Hàm minh họa **không log KMS data key response**; nó chỉ ghi kết quả hoạt động và xóa mảng DEK tạm sau sử dụng.

Đây là **đoạn mã có thể biên dịch**, không phải sản phẩm giám sát/audit production: chưa có hệ phân quyền, backend audit chống sửa, persistence, retry hoặc adapter KMS thật.

~~~java
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Arrays;
import java.util.Objects;
import java.util.UUID;
import java.util.logging.Level;
import java.util.logging.Logger;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class SafeKmsLoggingExample {
    private static final Logger AUDIT =
            Logger.getLogger("security.key.audit");

    private static final SecureRandom RNG = new SecureRandom();

    enum Action { GENERATE_DATA_KEY, ENCRYPT_RECORD, DECRYPT_RECORD, SIGN }
    enum Outcome { SUCCESS, DENIED, FAILED }
    enum Reason { OK, POLICY_DENIED, KMS_UNAVAILABLE,
                  INVALID_RESPONSE, CRYPTO_OPERATION_FAILED }
    enum KeyPurpose { BILLING_DATA_ENCRYPTION, PAYMENT_EVENT_SIGNING }

    // Các trường đều là giá trị điều khiển hoặc reference đã phê duyệt.
    // Không thêm raw key, plaintext, wrapped key hay exception vào đây.
    record AuditEvent(
            Instant at, UUID requestId,
            Action action, Outcome outcome,
            Reason reason, KeyPurpose keyPurpose) {}

    // Provider API được tích hợp ở nơi khác; không cung cấp key bytes
    // cho logger. IAM/workload identity phải được enforce ở KMS.
    interface KmsClient {
        DataKey generateDataKey() throws Exception;
    }

    // CHỨA SECRET: tuyệt đối không log/toString/serialize object này.
    record DataKey(byte[] plaintextDek, byte[] wrappedDek) {}

    // Adapter chỉ ném loại này khi provider thật sự từ chối quyền.
    static final class KmsAccessDeniedException extends Exception {}
    static final class InvalidKmsResponseException extends Exception {}

    record EncryptedPayload(
            byte[] nonce, byte[] ciphertextWithTag, byte[] wrappedDek) {}

    static void log(AuditEvent event) {
        Objects.requireNonNull(event);
        // Allowlist theo kiểu dữ liệu. Không truyền một DTO chứa secret.
        // Các field enum/UUID/Instant không lấy từ request body tùy ý.
        String line = "event=KEY_OPERATION"
                + " timestamp=" + event.at()
                + " requestId=" + event.requestId()
                + " action=" + event.action()
                + " outcome=" + event.outcome()
                + " reason=" + event.reason()
                + " keyPurpose=" + event.keyPurpose();
        AUDIT.log(Level.INFO, line);
    }

    static void audit(UUID requestId, Action action,
                      Outcome outcome, Reason reason) {
        log(new AuditEvent(
                Instant.now(), requestId, action, outcome,
                reason, KeyPurpose.BILLING_DATA_ENCRYPTION));
    }

    static EncryptedPayload encryptWithKms(
            KmsClient kms, byte[] plaintext, UUID requestId)
            throws Exception {
        Objects.requireNonNull(kms);
        Objects.requireNonNull(plaintext);
        Objects.requireNonNull(requestId);

        DataKey reply = null;
        byte[] dek = null;
        try {
            reply = kms.generateDataKey();
            dek = reply == null ? null : reply.plaintextDek();
            if (dek == null || dek.length != 32
                    || reply.wrappedDek() == null
                    || reply.wrappedDek().length == 0) {
                throw new InvalidKmsResponseException();
            }
            // Không log reply, dek, plaintext hoặc wrapped DEK.
            audit(requestId, Action.GENERATE_DATA_KEY,
                    Outcome.SUCCESS, Reason.OK);

            byte[] nonce = new byte[12];
            RNG.nextBytes(nonce);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(dek, "AES"),
                    new GCMParameterSpec(128, nonce));
            byte[] ciphertextWithTag = cipher.doFinal(plaintext);
            audit(requestId, Action.ENCRYPT_RECORD,
                    Outcome.SUCCESS, Reason.OK);
            return new EncryptedPayload(
                    nonce, ciphertextWithTag, reply.wrappedDek().clone());
        } catch (InvalidKmsResponseException e) {
            audit(requestId, Action.GENERATE_DATA_KEY,
                    Outcome.FAILED, Reason.INVALID_RESPONSE);
            throw new IllegalStateException(
                    "Invalid KMS response; requestId=" + requestId);
        } catch (KmsAccessDeniedException e) {
            // Không log e.getMessage() hoặc toàn bộ exception từ SDK.
            audit(requestId, Action.ENCRYPT_RECORD,
                    Outcome.DENIED, Reason.POLICY_DENIED);
            throw new SecurityException(
                    "Key operation denied; requestId=" + requestId);
        } catch (Exception e) {
            // Các lỗi hạ tầng/mật mã được báo bằng mã chuẩn, không
            // đưa raw exception hoặc KMS response vào logger.
            audit(requestId, Action.ENCRYPT_RECORD,
                    Outcome.FAILED, Reason.CRYPTO_OPERATION_FAILED);
            throw new IllegalStateException(
                    "Encryption failed; requestId=" + requestId);
        } finally {
            if (dek != null) Arrays.fill(dek, (byte) 0);
        }
    }

    public static void main(String[] args) {
        UUID requestId = UUID.randomUUID();
        // Demo log sự kiện có kiểu, không có key bytes.
        audit(requestId, Action.GENERATE_DATA_KEY,
                Outcome.DENIED, Reason.POLICY_DENIED);

        // Không gọi encryptWithKms vì chưa có SDK/adapter KMS thật.
        // Trong production: authorization theo tenant/object phải
        // xảy ra trước khi ứng dụng gọi GenerateDataKey.
    }

    private SafeKmsLoggingExample() {}
}
~~~

### 5.1. Đọc đúng ví dụ

1. **Không log dữ liệu nhạy cảm theo thiết kế:** logger chỉ nhận một `AuditEvent` có các trường enum/UUID/thời gian.
2. **Không in `DataKey` hoặc DTO KMS:** đây là điểm quan trọng vì `DataKey` chứa raw DEK.
3. **Không log `Exception` thô:** thay bằng mã kết quả; lỗi trả lên tầng ngoài cũng được chuẩn hóa với request ID.
4. **Không đưa raw key vào audit**, kể cả khi thao tác thành công.
5. **Mảng `dek` được điền số 0 trong `finally`:** điều này giảm thời gian lưu trên mảng đó, **không chứng minh mọi bản sao trong JVM/provider đã bị xóa**.
6. **DEK vẫn có mặt trong RAM ứng dụng** vì ví dụ minh họa envelope encryption. Nếu chính sách yêu cầu key không rời HSM, kiến trúc phải dùng phép mật mã tại HSM/KMS theo khả năng provider.
7. **KMS policy và quyền nghiệp vụ nằm ngoài logger:** log an toàn không tự ngăn người có quyền gọi Decrypt/Sign sai mục đích.

**Giới hạn cố ý:** Ví dụ tối giản **không có AAD/encryption context hoặc versioning đầy đủ**; trước khi dùng thật phải bổ sung theo format mã hóa, kiểm tra authorization, key reference/provider version, transaction lưu wrapped DEK và ciphertext, KMS audit correlation và negative tests. Không dùng đoạn mã này như một hệ thống mã hóa hoàn chỉnh.

### 5.2. Cải tiến xử lý exception để tránh phân loại sai

Trong ví dụ, adapter phải chỉ ném `KmsAccessDeniedException` khi nhà cung cấp **thực sự từ chối quyền**, còn phản hồi data key sai định dạng dùng `InvalidKmsResponseException`. **Hệ thống thật phải phân biệt lỗi IAM denied, dữ liệu sai định dạng, KMS timeout, key disabled và GCM tag sai qua các loại lỗi đáng tin do SDK/adapter định nghĩa**; không coi mọi `SecurityException` là AccessDenied.

Đồng thời, **không nên mất dấu lỗi khi điều tra**: có thể lưu chẩn đoán có kiểm soát ở một kênh bảo mật chuyên dụng sau khi phân loại và lọc, hoặc tra cứu provider audit bằng correlation ID. Không tự ghi `e.toString()` vào log công khai.

### 5.3. Vì sao enum/allowlist tốt hơn generic redaction?

Nếu logger nhận `Map<String,Object>` tùy ý và cố thay mọi trường tên chứa `secret` bằng `***`, có thể vẫn lộ qua `dataKey`, `material`, `response`, `payload` hoặc tên trường mới của SDK.

**Allowlist theo kiểu dữ liệu ở điểm tạo event** giúp người review biết rõ những gì **có thể** xuất hiện trong log. Redaction ở collector là **lớp phòng vệ bổ sung**, không phải đường bảo vệ duy nhất.

## 6. Redaction, masking và kiểm soát ở nhiều lớp

Dù ưu tiên **không tạo log chứa secret**, vẫn cần phòng vệ bổ sung vì dependency/SDK/agent có thể xuất dữ liệu ngoài ý muốn.

### 6.1. Kiểm soát tại nguồn

- Tạo các helper `auditKeyOperation(...)` có **schema cố định**.
- Không serialize **KMS request/response** hoặc `SecretKey`, `PrivateKey`, `KeyPair`, `byte[]` secret.
- Tắt **HTTP body/wire-level logging** cho API có secret, kể cả ở mức DEBUG/TRACE.
- Không đưa KMS decryption context nguyên khối hoặc plaintext vào event.
- Bỏ raw secret khỏi `toString()`, `equals()` debug output, exception messages và test failure output.
- Dùng **classification annotation/taint tracking** nếu nền tảng có hỗ trợ, nhưng không dựa vào annotation là đủ.
- Hạn chế dump môi trường/config khi service khởi động hoặc khi xảy ra lỗi.

### 6.2. Kiểm soát trong pipeline log

- Redact fields nhạy cảm trước khi **xuất qua mạng** nếu có thể.
- Dùng log forwarder/collector có chính sách **lọc body, header, query, environment**.
- Mã hóa đường truyền đến collector, mã hóa lưu trữ và tách quyền xem.
- Áp giới hạn export, download, chia sẻ dashboard và quyền API log storage.
- Thiết lập retention theo độ nhạy cảm; backup, archive và bản sao ở dịch vụ thứ ba cũng thuộc phạm vi.
- Có cơ chế kiểm tra sample log đã được phép và cảnh báo khi xuất hiện dấu hiệu key leak.

**Một regex redaction không thể đảm bảo lọc mọi kiểu secret**: khóa có thể có nhiều encoding, bị cắt dòng, chia chunks, nén hoặc trộn vào stack trace. Phát hiện ở pipeline chỉ là **defense in depth**.

### 6.3. Masking không đồng nghĩa an toàn tuyệt đối

Các kiểu log sau vẫn nên tránh:

~~~text
key=abcd****************
keyPrefix=abcd1234
keySuffix=...f00d
sha256(secret)=...
base64(secret)=...
hex(secret)=...
~~~

Một prefix/suffix của secret cũng có thể giảm không gian tìm kiếm, làm lộ cấu trúc hoặc liên kết đối tượng. **Không có lý do vận hành thông thường để in một phần raw KEK/DEK/private key**. Nếu cần phân biệt khóa, dùng **opaque key ID** do registry cấp và phân quyền truy cập metadata đó.

## 7. KMS/HSM và các API dễ làm lộ dữ liệu trong log

### 7.1. GenerateDataKey hoặc giải bọc DEK

Một số API KMS có thể trả về đồng thời:

- **Plaintext data key** cho ứng dụng sử dụng tạm thời.
- **Encrypted/wrapped data key** để lưu theo bản mã.
- Metadata như key ID, thuật toán hoặc context.

**Không log toàn bộ response** chỉ vì muốn kiểm tra xem API có hoạt động. Ghi `operation=GenerateDataKey`, logical key purpose, result, request ID và thời gian là đủ cho phần lớn trường hợp.

Nếu cần kiểm tra độ dài DEK, log **kết quả validation** (`KEY_LENGTH_VALID`/ `INVALID_KEY_LENGTH`) thay vì bytes khóa.

### 7.2. ImportKeyMaterial, BYOK và secure backup

Với **BYOK** hoặc key import, request/response có thể liên quan:

- Wrapped key material.
- Wrapping public key và import parameters.
- Import token hoặc credential.
- HSM recovery data, backup blob hoặc attestation.

Không mặc định tất cả các đối tượng trên đều cùng mức bí mật; **nhưng không log raw blob hoặc token khi chưa được phân loại và phê duyệt**. Đặc biệt không xuất private/KEK từ HSM chỉ để khắc phục lỗi import.

Một audit event nên ghi **import request ID, target key ref, actor, policy/approval và result**; dữ liệu gói nhập khóa phải ở kênh chuyển an toàn theo quy trình nhà cung cấp.

### 7.3. Sign và Verify

Một KMS/HSM có thể cho phép **Sign** mà không bao giờ xuất private key. Tuy nhiên:

- Không log **private key bytes** hoặc signing seed.
- Hạn chế log **message được ký** nếu nó chứa PII, token hoặc dữ liệu giao dịch nhạy cảm.
- Có thể log **artifact digest/reference, release ID, signer key ID, workflow ID và status** theo policy; digest của dữ liệu ít entropy/nhạy cảm cũng cần đánh giá.
- Không log toàn bộ JWT access token: token có thể là **bearer credential**.
- Tại verifier, lưu bằng chứng **đã xác minh chữ ký và kiểm tra issuer/audience/permission** thay vì toàn bộ payload riêng tư.

**HSM non-exportable key không loại trừ rủi ro lạm dụng quyền Sign.** Nếu log KMS chỉ có `Sign=SUCCESS` mà không gắn với workflow và actor được phép, khó điều tra một chữ ký không hợp lệ về mặt nghiệp vụ.

### 7.4. Encryption context và log tự động của provider

Một số dịch vụ KMS đưa **encryption context** vào audit hoặc metadata quan sát. Vì vậy không đặt **password, raw DEK, API token, nội dung hóa đơn, thông tin thẻ hoặc dữ liệu cá nhân không cần thiết** vào context.

AAD hoặc encryption context thường phục vụ **ràng buộc ngữ cảnh**, không phải kênh bí mật. Chỉ đặt những tham số cần thiết và đủ an toàn nếu bị quan sát theo chính sách logging của provider.

## 8. Vai trò của application authorization và tenant isolation

Một hệ thống không log key vẫn có thể **dùng key sai**. Cần kết hợp:

~~~mermaid
flowchart TD
    REQUEST["Request từ user / workload"] --> AUTHN["Xác thực danh tính"]
    AUTHN --> AUTHZ["Authorization tenant/object và purpose"]
    AUTHZ --> POLICY["Chọn key reference được phê duyệt"]
    POLICY --> KMS["KMS/HSM kiểm tra IAM và trạng thái key"]
    KMS --> CRYPTO["AEAD Decrypt / Sign đúng giao thức"]
    AUTHZ --> EVENT["Audit allowlist: actorRef, keyRef, operation, outcome"]
    KMS --> EVENT
    CRYPTO --> RESULT["Trả kết quả đã được cấp quyền"]
    EVENT --> LOGSTORE["Audit store được bảo vệ"]
~~~

### 8.1. Vì sao chỉ log key ID chưa đủ để điều tra?

Giả sử KMS cho Billing Service quyền Decrypt trên một KEK dùng chung. Log ghi `Decrypt=SUCCESS, keyId=billing-kek`, nhưng không biết **caller của API có thực sự được đọc invoice của tenant A không**.

Do đó cần **audit ứng dụng tại điểm authorization** và liên kết với **audit KMS**. Nhưng việc ghi thêm tenant/object phải tuân thủ **phân loại dữ liệu**; không vì muốn điều tra mà in nguyên bản ghi hóa đơn.

### 8.2. Không lấy metadata audit từ user input chưa xác thực

Nếu caller truyền `keyId`, `tenant`, `reasonCode` hoặc `actor` tùy ý, log có thể bị:

- **Log injection:** chèn newline hoặc control characters để giả sự kiện.
- **Misattribution:** giả một principal khác.
- **High-cardinality abuse:** tạo hàng triệu labels/tags trong metrics.
- **Metadata leakage:** nhúng secret/PII vào trường mà hệ thống cho phép log.

Nên lấy **actor từ session/workload identity được xác thực**, key reference từ registry/config đáng tin và event type từ enum. Trường văn bản cần kiểm tra định dạng/độ dài và chuẩn hóa trước khi log.

## 9. Không log key trong toàn bộ vòng đời khóa

| Giai đoạn | Bẫy logging thường gặp | Cách ghi nhận an toàn |
| --- | --- | --- |
| **Generate** | In bytes khóa, seed, entropy source state, response của KMS. | Key ref, thuật toán, purpose, actor, result, creation event ID. |
| **Register/Provision** | Ghi request bao gồm private key import hoặc credential. | Registration ID, key type, ownerRef, provenance verification result. |
| **Store** | Dump file keystore, secret manager value, backup key blob. | Storage reference đã phân quyền, custody status, policy ID. |
| **Use** | Log DEK rõ, plaintext, signed payload, raw MAC secret. | Operation, key ref, outcome, request ID, policy decision. |
| **Rotate** | In cả key cũ/mới để so sánh bytes. | Old/new **key IDs/versions**, predecessor link, approval, result. |
| **Retire/Revoke** | Ghi token/private material khi điều tra sự cố. | Affected key refs, trust decision, reason code, thời điểm. |
| **Backup/DR** | Log HSM backup blob, escrow share, recovery credential. | Backup reference, restore test status, approvers, key version coverage. |
| **Destroy** | Xuất key lần cuối để “chứng minh đã xóa”. | Destruction event, evidence reference, dependencies checked. |

**Không có giai đoạn nào đòi hỏi log raw secret để chứng minh thành công.** Việc xác minh khóa được tạo/hủy đúng cần bằng chứng từ nguồn có thẩm quyền, phép thử có kiểm soát, attestation nếu có hỗ trợ hoặc audit của provider — không phải bản sao key bytes.

### 9.1. Key ID, version và predecessor

Một inventory tốt nên lưu:

~~~text
keyFamily = billing-kek
version = v4
predecessor = v3
state = ACTIVE
purpose = WRAP/UNWRAP
ownerRef = billing-security
dependencyIndexRef = billing-dek-catalog
~~~

Tất cả là **metadata minh họa**, không phải vật liệu khóa. Audit có thể ghi version/predecessor theo quyền xem được phê duyệt, giúp tìm ciphertext còn phụ thuộc v3 mà **không in raw KEK**.

## 10. Khả năng điều tra khi không có raw key trong log

Một câu hỏi thực tế: “Nếu không log key thì debug lỗi KMS bằng cách nào?”

Cách tiếp cận là **tách các phép kiểm tra có thể quan sát được** khỏi dữ liệu bí mật.

| Câu hỏi debug | Không cần log | Có thể ghi/kiểm tra |
| --- | --- | --- |
| KMS có trả đúng loại DEK? | Plaintext DEK. | Thuật toán, key size validation result, request ID. |
| Workload có đủ quyền? | Access token hoặc credentials. | Principal ref, key ref, action, IAM decision/error code. |
| Lỗi do sai context? | Raw context chứa PII/secret. | Context schema version, mismatch reason code, object reference đã lọc. |
| Lỗi AES-GCM do tag sai? | DEK, plaintext, toàn ciphertext. | Authentication failed, record ID, format version, request ID. |
| Khóa bị disabled? | Raw key hoặc backup material. | Key ID, lifecycle state từ KMS, timestamp được xác minh. |
| Rotation chưa đồng bộ? | Cả key bytes cũ/mới. | Old/new key versions, consumer readiness, alias history. |
| Signing key dùng sai? | Private key hoặc toàn bộ message nhạy cảm. | Signer key ref, workflow, signed artifact reference/digest được phép. |
| Restore không chạy? | HSM recovery shares hoặc KEK rõ. | Backup ID, restore phase, key-version coverage, error code. |

### 10.1. Correlation ID không phải secret

Một **request ID ngẫu nhiên và không mang dữ liệu người dùng** có thể liên kết:

~~~text
Billing app audit:
  requestId=R, operation=DECRYPT_INVOICE, tenantRef=T, outcome=DENIED

KMS provider audit:
  requestId=R hoặc providerRequestId=P, keyRef=K, action=Decrypt, outcome=DENIED

Incident timeline:
  R -> P -> policyVersion -> deployment/change request
~~~

**Correlation ID chỉ hữu ích khi được tạo và truyền theo quy ước**; một số provider tự cấp request ID riêng nên cần lưu **mapping an toàn** thay vì giả định KMS sẽ sử dụng request ID từ ứng dụng.

### 10.2. Test và log chuyên dụng

Khi điều tra lỗi mã hóa, có thể tạo **test vector bằng khóa thử nghiệm riêng, không có giá trị production**, và log giá trị thử nghiệm ở môi trường test cô lập theo chính sách. **Không copy khóa production vào bài test** để tái hiện lỗi.

Nếu cần chứng minh tag sai, dùng negative tests thay đổi ciphertext/AAD của dữ liệu giả và xác minh API từ chối. Không biến production log thành một kho dữ liệu có thể dùng để tái hiện toàn bộ bí mật.

## 11. Kiểm soát quyền và vòng đời của chính log

Log không chỉ cần **lọc trường nhạy cảm**; bản thân hệ thống log phải được bảo vệ.

### 11.1. Least privilege và phân tách nhiệm vụ

| Vai trò | Quyền thường phù hợp | Không nên mặc định có |
| --- | --- | --- |
| **Developer** | Xem log đã lọc theo ứng dụng/môi trường được phép. | Bulk export toàn bộ audit KMS production hoặc xem secret. |
| **SRE/on-call** | Phân tích lỗi và metrics, truy cập sự kiện theo incident. | Sửa/xóa audit lịch sử hoặc lấy key material. |
| **Security incident responder** | Tra cứu audit, đối chiếu KMS và ứng dụng theo sự cố. | Dùng quyền Decrypt/Sign ngoài quy trình. |
| **KMS administrator** | Quản lý key policy/operation theo phạm vi. | Tự xóa log chứng minh hành động của chính họ. |
| **Auditor** | Xem bằng chứng đã lọc và lịch sử đầy đủ được bảo vệ. | Truy cập plaintext data hoặc recovery shares. |
| **Support/third party** | Thông tin vận hành tối thiểu theo hợp đồng. | Raw key, credential, PII hay toàn bộ key inventory. |

**Để điều tra việc một KMS admin lạm dụng quyền, audit phải nằm ngoài khả năng tự ý sửa/xóa của người đó** theo kiến trúc được hỗ trợ. Có thể dùng write-once/immutable retention hoặc export tới môi trường quản trị độc lập, đi cùng cơ chế bảo vệ dữ liệu và kiểm soát thời gian lưu.

### 11.2. Retention, export và backup

- Xác định thời gian lưu của application log, audit KMS, tracing, SIEM và bản sao export/backup.
- Hạn chế ai được tạo **snapshot, export hoặc chia sẻ dashboard**.
- Khi một log bị phân loại có secret, phải xem **mọi bản sao** theo đường thu thập và retention.
- Không chỉ đổi permission của logger trong ứng dụng: log cũ có thể đã được nhân bản.
- Kế hoạch xóa/ẩn bản ghi phải cân bằng **bằng chứng điều tra, legal hold, tuân thủ và giảm thiểu bí mật bị lộ** dưới quy trình được phép.

**Không nên “giải quyết rò rỉ” bằng cách xóa toàn bộ audit** khi chưa bảo toàn chứng cứ cần thiết và được security/incident commander phê duyệt. Cách xử lý đúng phải vừa hạn chế truy cập bí mật vừa giữ bằng chứng có giá trị pháp lý/vận hành theo quy định.

### 11.3. Metadata vẫn cần bảo mật

Dù không lưu raw key, một hệ thống log có thể chứa **key names, IAM principals, trust relationships, đường dẫn backup, tenant references và lịch quay khóa**. Tập hợp metadata đó có thể cung cấp bản đồ tấn công. Cần áp dụng **RBAC/ABAC, giới hạn truy vấn, audit truy cập log, mã hóa at rest/in transit và chính sách export**.

## 12. Nếu phát hiện đã log key: quy trình ứng phó

Khi key material có thể đã đi vào log, **không chỉ sửa code rồi đóng ticket**. Xử lý như một sự kiện lộ bí mật cần đánh giá.

~~~mermaid
flowchart TD
    DETECT["Phát hiện log có secret"] --> STOP["Ngăn tạo thêm bản sao và hạn chế truy cập"]
    STOP --> CLASSIFY["Phân loại DEK/KEK/private key/token, tính xác thực"]
    CLASSIFY --> SCOPE["Xác định key IDs, phiên bản, log pipelines, retention"]
    SCOPE --> CONTAIN["Cô lập credentials/key usage theo quyết định sự cố"]
    CONTAIN --> ROTATE["Rotation/revoke và đánh giá dữ liệu/chữ ký bị ảnh hưởng"]
    ROTATE --> CLEAN["Xử lý log copies, backups và bằng chứng theo chính sách"]
    CLEAN --> VERIFY["Đối soát KMS audit, inventory, consumer, negative tests"]
    VERIFY --> REVIEW["Hậu kiểm, sửa logging/SDK/collector"]
~~~

### 12.1. Bước 1 – Chặn đường lộ và bảo vệ chứng cứ

1. Tắt hoặc sửa logging gây rò rỉ; **không tiếp tục in secret để xác nhận**.
2. Hạn chế ngay quyền truy cập log chứa secret và đường xuất dữ liệu.
3. Xác định phạm vi thời gian, ứng dụng, môi trường và các pipeline/collector/bản sao.
4. Lưu bằng chứng đã được lọc hoặc bảo vệ theo quy trình ứng phó; không paste raw key vào issue, chat hoặc email.
5. Phân biệt **thông tin thật đã bị lộ** với một key ID/public key hoặc test vector vô hại để đánh giá đúng mức rủi ro.

### 12.2. Bước 2 – Phân tích loại khóa và hậu quả

| Dữ liệu trong log | Rủi ro và hướng xử lý chính |
| --- | --- |
| **DEK rõ** | Xác định ciphertext/dataset liên quan, đánh giá ai truy cập log; thay DEK và re-encrypt khi cần. |
| **KEK rõ** | Xác định các DEK được wrap và phạm vi ảnh hưởng; đánh giá rotate KEK, rewrap, khả năng DEK đã lộ và re-encrypt. |
| **Private signing key** | Ngừng Sign bằng key cũ, tạo khóa mới, cập nhật verifier trust, điều tra chữ ký trong khoảng ảnh hưởng. |
| **HMAC/PSK secret** | Rotate và cập nhật các bên dùng chung, thu hẹp cửa sổ tin cũ, đánh giá khả năng giả mạo. |
| **Seed hoặc recovery secret** | Đánh giá mọi key có thể được tái tạo từ secret đó; xử lý cùng recovery/backup policy. |
| **KMS token/credential** | Thu hồi token/identity, kiểm tra KMS audit và quyền Sign/Decrypt/Unwrap đã bị lạm dụng hay chưa. |
| **Wrapped DEK/ciphertext** | Phân loại dữ liệu và đường decrypt; đánh giá mức độ rò metadata/PII và tính nhạy cảm của blob. |
| **Key ID/public key không bí mật** | Không tự coi là compromise của key material; đánh giá metadata leakage/trust integrity theo policy. |

**Quan trọng:** **Rewrap cùng DEK dưới KEK mới không bảo vệ được ciphertext cũ nếu DEK đã bị lộ**. Nếu private signing key bị lộ, việc xóa log hoặc xóa private key không tự xóa các chữ ký giả có thể đã được phát hành.

### 12.3. Bước 3 – Xử lý lịch sử log và backup

- Tra cứu ingestion path từ application tới agent, SIEM/APM, archive, dashboard và export.
- Xác định người/role và bên thứ ba có khả năng tiếp cận log.
- Hạn chế quyền, xử lý bản sao theo retention và phê duyệt pháp lý/bảo mật.
- Không tuyên bố secret đã bị xóa hoàn toàn nếu vẫn còn bản sao không kiểm soát.
- Cập nhật key inventory, incident timeline và audit về key status/rotation.
- Kiểm tra rằng **key đã bị lộ không còn được dùng cho thao tác mới trái policy**.

**Rotate key thường quan trọng hơn nỗ lực chỉ xóa dấu vết trong Git/log.** Các bản sao đã được tải xuống có thể không thể thu hồi. Cần đưa giả định này vào phạm vi sự cố và kế hoạch chuyển khóa.

### 12.4. Bước 4 – Ngăn lặp lại

- Bổ sung **unit/contract tests** bảo đảm logger không nhận secret DTO.
- Tắt các chế độ HTTP wire/body logging nguy hiểm của KMS SDK.
- Thêm allowlist events và redaction thứ cấp.
- Kiểm tra các môi trường có cờ DEBUG/TRACE hoặc dump config.
- Đào tạo review code: **không log object chứa key material**, kể cả khi `toString()` hiện trông vô hại.
- Theo dõi sự kiện log key leak từ scanner hoặc DLP được phê duyệt mà không làm thêm bản sao bí mật.

## 13. Kiểm thử: chứng minh key material không xuất hiện trong log

Một test đúng hướng không cần lấy khóa production. Nó có thể dùng **sentinel secret giả** hoặc dữ liệu test được tạo có kiểm soát để xác định liệu đường logging có tạo bản sao ngoài ý muốn hay không.

### 13.1. Các lớp test

| Bài kiểm tra | Kết quả kỳ vọng |
| --- | --- |
| Log thành công `GenerateDataKey` | Có action/outcome/request ID, **không có raw DEK**. |
| KMS trả error chứa payload nhạy cảm | Lỗi được map thành reason code, không lộ exception text. |
| GCM tag sai | Log `INVALID_TAG` hoặc reason code tương ứng, không log plaintext/ciphertext toàn bộ. |
| JSON serialize `KmsResponse` trong log helper | Bị chặn hoặc không có đường gọi vào logger an toàn. |
| DEBUG/TRACE HTTP client | Không bật body/header logging cho KMS/secret manager. |
| Request có tenant chứa newline/control chars | Không tạo log injection, trường bị loại/chuẩn hóa. |
| Một user không có quyền tenant B yêu cầu Decrypt | Application authorization từ chối trước KMS; audit đủ thông tin đã lọc. |
| Rotate DEK/KEK | Ghi old/new **key refs/versions**, không in bytes hai khóa. |
| HSM backup/restore | Log status và evidenceRef, không in backup blob/recovery shares. |
| Crash/exception production | Không đưa secret vào error page, APM hoặc log collector. |
| CI/CD chạy test lỗi | Không echo `.env`, keystore password, private key hoặc access tokens. |
| Export log cho support | Chỉ có các fields đã được phép, quyền và retention phù hợp. |

### 13.2. Tư duy kiểm thử phù hợp

Có thể kiểm tra rằng event audit chỉ nhận kiểu **enum/UUID/opaque ref**, đồng thời dùng test dữ liệu giả để xác nhận không phát hiện sentinel trong log capture.

Nhưng **“không tìm thấy secret” không chứng minh tất cả đường rò đều không tồn tại**: secret có thể bị chuyển encoding, split, nén hoặc xuất qua APM/crash dump thay vì log. Cần kết hợp **review cấu trúc code, kiểm tra cấu hình logging agent/SDK, data-flow analysis, threat model và thử tích hợp**.

**Không bao giờ đưa production key vào bài test chỉ để xác minh redaction**.

## 14. Tình huống thực tế: Billing, Payment và Ledger

Một nền tảng gồm:

- **Billing Service** dùng AES-GCM với DEK tạm do KMS cấp, KEK trong KMS/HSM.
- **Payment Service** dùng private key Ed25519 được bảo vệ để ký sự kiện.
- **Ledger Service** dùng public key từ registry/JWKS/PKI đáng tin để Verify và kiểm tra replay.

### 14.1. Sự cố ở Billing Service

Developer thêm:

~~~text
DEBUG kms.generateDataKey response={
  plaintextDek: "<secret-bytes>",
  wrappedDek: "<encrypted-key-blob>",
  keyRef: "billing-kek",
  context: {tenant: "...", invoiceId: "..."}
}
~~~

Đây là **mẫu minh họa lỗi**, không có secret thật. KMS có thể chỉ cấp `GenerateDataKey` cho Billing workload, nhưng DEK đã được ghi vào log có thể được đọc bởi một nhóm người có quyền log rộng hơn.

**Cách xử lý:** tắt log response, giới hạn quyền đọc log, đánh giá phạm vi DEK/ciphertext và backup, thay key material cần thiết, re-encrypt nếu DEK thực sự bị lộ và dữ liệu còn cần giữ bí mật, sau đó kiểm thử logging helper mới.

**Không kết luận rằng rotate KEK là đủ**, vì DEK rõ đã xuất hiện trong log.

### 14.2. Sự cố ở Payment Service

Một exception debug chứa `privateKey.getEncoded()` rồi được chuyển thành Base64 và đưa vào stack trace. Nếu private key có thể xuất dạng rõ, **người đọc log có thể lấy vật liệu ký**. Nếu private key non-exportable, lỗi khác có thể xảy ra nhưng **quyền Sign qua KMS vẫn phải được giám sát**.

**Cách xử lý:** cô lập và thu hồi quyền/key theo quyết định sự cố, phát hành S2, cập nhật Ledger trust, điều tra chữ ký lịch sử, thay logging code để không hề nhận `PrivateKey` hoặc raw `KmsSignResponse` khi không cần.

### 14.3. Sự cố ở Ledger Service

Ledger ghi toàn bộ JWT/event body khi Verify thất bại. Dù public key không bí mật, **token hoặc payload có thể mang bearer credential, thông tin tài chính và dữ liệu cá nhân**.

**Cách xử lý:** ghi `signatureVerification=FAILED`, issuerRef, eventRef, key ID được phân loại và reason code; không in full token/message. Ngoài Verify, Ledger vẫn cần kiểm tra **issuer, audience, authorization và replay/idempotency**.

### 14.4. Liên kết với key inventory và lifecycle

Khi phát hiện log chứa secret, **key inventory** cần trả lời:

1. Key ID/phiên bản nào tương ứng với vật liệu đã bị lộ?
2. Key được dùng cho **ENCRYPT/DECRYPT, WRAP/UNWRAP, SIGN/VERIFY hay MAC**?
3. Những ciphertext, wrapped DEK, signed events hoặc backups nào phụ thuộc?
4. Owner, service và tenant nào chịu trách nhiệm?
5. Key đang **ACTIVE, RETIRED, DISABLED, REVOKED hay PENDING_DELETION**?
6. Có thể triển khai successor và cập nhật consumer trust an toàn không?
7. Những bản sao ở log/archive có được thu hồi hoặc kiểm soát theo mức độ sự cố không?

Đây là lý do một bài học về **logging** gắn trực tiếp với **key storage, rotation, revocation, destruction và audit**: log có thể làm sai phạm vi lưu trữ khóa mà KMS/HSM đã được thiết kế để bảo vệ.

## 15. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Log `plaintextDek` để debug AES | Key có thể giải mã dữ liệu xuất hiện ở nơi nhiều người xem được. | Log key ref/operation/outcome, không raw DEK. |
| Log toàn bộ `GenerateDataKeyResponse` | Có thể chứa raw DEK lẫn metadata khác. | Typed allowlist events, không serialize SDK response. |
| Log private signing key hoặc PKCS#8 PEM | Kẻ đọc log có thể tạo chữ ký giả. | KMS/HSM custody và audit Sign theo key ID. |
| Log HMAC key/PSK hoặc hash của secret | Lộ secret hoặc tạo dữ liệu để liên kết/dò. | Key version/opaque ID, không in bytes/fingerprint secret. |
| Dùng Base64/hex rồi coi không còn là secret | Encoding đảo ngược được. | Không log cả bản gốc lẫn bản mã hóa. |
| Dùng regex redact duy nhất tại collector | Bỏ sót format mới, encoding hoặc SDK output. | Ngăn tại source, allowlist, rồi defense in depth. |
| Log exception kèm request body và header | Secret/token có thể xuất hiện trong stack trace. | Trusted reason codes, correlation ID, kênh chẩn đoán hạn chế. |
| Bật SDK HTTP wire logging trong production | Lộ key import, credentials, data key responses. | Tắt body/header logging cho đường có secret. |
| Đặt key material trong tracing span/metrics label | Secret lan vào APM/metrics có retention và quyền khác. | Chỉ ghi metadata đã phân loại, không arbitrary attributes. |
| Tin rằng wrapped DEK luôn vô hại | Tăng bản sao ciphertext khóa, có thể lộ metadata. | Chỉ lưu wrapped DEK ở kho dữ liệu được thiết kế. |
| Log nguyên encryption context có PII | Rò tenant/object/customer data. | Context schema tối thiểu, không secret/PII nhạy cảm. |
| Ghi raw KMS key ID vào dashboard công khai | Rò kiến trúc tài nguyên hoặc tenant naming. | Opaque reference và quyền xem metadata. |
| Người quản trị KMS có thể xóa audit của mình | Khó phát hiện lạm dụng. | Tách quyền và bảo vệ integrity/retention audit. |
| Chỉ xóa log cục bộ sau khi lộ DEK | Bản sao có thể tồn tại ở SIEM/APM/archive. | Incident response theo toàn pipeline và rotate key. |
| Chỉ rotate KEK khi raw DEK đã lộ | Ciphertext cũ vẫn có nguy cơ bị đọc. | Thay DEK, đánh giá re-encrypt theo phạm vi. |
| Destroy key trước khi kiểm tra backup/dependencies | Mất khả năng phục hồi dữ liệu. | Key inventory, retention, restore drill và approval. |
| Log test key production trong CI | Secret xuất hiện trong job logs/artifacts. | Test keys riêng và chính sách không echo. |
| Không log gì để “an toàn tuyệt đối” | Thiếu bằng chứng audit khi có sự cố. | Structured security events không chứa secret. |
| Tin zeroization của một byte array là đủ | JVM/SDK có thể giữ bản sao khác. | Giảm secret exposure, không log, giảm lifetime và đánh giá runtime. |

## 16. Checklist triển khai và câu hỏi tự kiểm tra

### 16.1. Checklist dành cho developer, SRE và security

1. Log helper có **schema allowlist** chỉ chứa các trường vận hành được phê duyệt không?
2. Mọi API **GenerateDataKey, Decrypt, Unwrap, Sign, ImportKeyMaterial** có tránh in full request/response không?
3. Có đường `toString()`, JSON serialization, exception/log format nào chứa raw secret không?
4. HTTP wire logs, DEBUG/TRACE và APM body/header capture đã được cấu hình phù hợp chưa?
5. Có chắc **DEK, KEK, private key, seed, MAC key, PSK, token và recovery material** không thể được đưa vào log theo đường thông thường?
6. Key ID, version, tenantRef, actorRef và encryption context có được phân loại và giới hạn quyền xem không?
7. Có dùng **workload identity** và IAM để hạn chế thao tác KMS mà không in credential không?
8. Ứng dụng có kiểm tra quyền **tenant/object trước khi gọi KMS** không?
9. Cơ chế mã hóa có dùng **AEAD nonce/tag/AAD đúng**, và failure log chỉ có reason code an toàn không?
10. Có phân biệt **wrapped DEK** với **plaintext DEK**, không log blob lớn nếu không cần?
11. Có correlation ID nối **application authorization audit** với **KMS provider audit** không?
12. Log collector, SIEM, APM, dashboards và export có quyền, mã hóa, retention, audit truy cập phù hợp không?
13. Quy trình sự cố có thể xác định những bản sao secret đã xuất hiện ở log/backup nào không?
14. Khi một DEK bị lộ, có kế hoạch **thay DEK/re-encrypt** chứ không chỉ rotate KEK không?
15. Khi signing private key bị lộ, có kế hoạch **revoke/trust update, điều tra chữ ký và rotate** không?
16. Trước destruction/crypto-shredding, inventory đã tính đến **key copies trong logs, archives và recovery paths** chưa?
17. Có negative tests bảo đảm log không chứa test sentinel secret, ngay cả khi KMS lỗi không?
18. Có owner quản trị logging policy, kiểm tra cấu hình agent/SDK và điều tra alert secret leak không?

### 16.2. Câu hỏi tự kiểm tra

1. Vì sao một DEK chỉ nằm trong RAM ứng dụng vài mili giây có thể trở thành rủi ro dài hạn nếu bị ghi log?
2. **Key ID** và **raw KEK/DEK** khác nhau về độ nhạy cảm như thế nào?
3. Một public key fingerprint có thể log theo điều kiện nào? Vì sao không nên băm raw symmetric key chỉ để log?
4. **Base64(secret)** có bảo vệ secret khỏi người đọc log không?
5. Tại sao không nên log toàn bộ `GenerateDataKeyResponse` hoặc `ImportKeyMaterialRequest`?
6. Nếu không log private key, một developer còn có thể debug lỗi `Sign` bằng những metadata nào?
7. Vì sao `logger.error("failed", exception)` có thể nguy hiểm trong đường xử lý KMS?
8. Logging allowlist khác regex redaction ở collector như thế nào?
9. Tại sao encryption context/AAD có thể **không bí mật** nhưng vẫn không nên ghi nguyên khối vào log?
10. Một KMS key non-exportable có bảo vệ plaintext DEK đã được ứng dụng in ra log không?
11. Sau khi raw DEK xuất hiện trong log, chỉ rotate KEK có khiến ciphertext cũ an toàn trở lại không?
12. Vì sao việc xóa log ở một container không đủ xử lý khi SIEM/APM đã thu nhận secret?
13. Hệ thống còn cần audit gì nếu tuyệt đối không ghi key material?
14. Sự kiện Verify chữ ký hợp lệ có tự chứng minh người ký được phép thao tác và event không bị replay không?
15. Key inventory cần ghi những metadata nào để đánh giá phạm vi ảnh hưởng khi key lộ qua log?
16. Vì sao phải giữ audit khỏi khả năng sửa/xóa của người có quyền quản trị KMS?
17. Các bài test có thể dùng secret test như thế nào mà không chép khóa production vào môi trường CI?
18. Vì sao retention của log có thể làm thất bại tuyên bố **crypto-shredding** nếu log còn chứa raw key?

**Ghi nhớ:** **Không lưu key trong log** không chỉ là xóa vài câu lệnh `println` mà là **thiết kế toàn bộ pipeline quan sát để không tiếp nhận bí mật mật mã**. Hệ thống vẫn phải có **audit rõ ràng về ai dùng khóa nào, thao tác gì, kết quả ra sao và theo chính sách nào**, nhưng không cần raw DEK, KEK, private key, seed, token hoặc recovery material. Kết hợp **allowlist events, kiểm soát KMS/HSM và quyền IAM, phân quyền dữ liệu, phân loại metadata, kiểm soát log/tracing/CI, rotation, incident response và key inventory** giúp bảo vệ khóa xuyên suốt vòng đời mà vẫn có đủ bằng chứng để điều tra sự cố.
