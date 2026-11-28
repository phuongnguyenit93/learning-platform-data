# Key accessed event

Trong một hệ thống quản lý khóa, việc biết khóa nào đang được sử dụng, ai yêu cầu sử dụng và thao tác đó có thành công hay không là điều kiện quan trọng để phát hiện lạm dụng và điều tra sự cố. **Key accessed event** là sự kiện audit ghi nhận một danh tính hoặc workload đã truy cập hay yêu cầu thực hiện thao tác với một khóa cụ thể.

Sự kiện có thể được tạo khi ứng dụng yêu cầu KMS/HSM mã hóa, giải mã, ký số, xác minh, wrap, unwrap hoặc khi một quy trình quản trị đọc metadata, thay đổi policy hay export key material. Phạm vi chính xác phụ thuộc dịch vụ và provider; vì vậy tổ chức cần định nghĩa taxonomy thống nhất để các hệ thống có thể phân tích và so sánh.

Key accessed event giúp trả lời các câu hỏi: ai đã dùng khóa, khóa nào được dùng, thao tác gì đã diễn ra, vào lúc nào, từ workload hoặc môi trường nào, quyết định cho phép hay từ chối ra sao và kết quả thế nào. Event phải đủ thông tin để kiểm toán nhưng không được chứa key material, password, plaintext hoặc dữ liệu nhạy cảm không cần thiết.

## 1. Key accessed event là gì?

Key accessed event là một bản ghi có cấu trúc về một lần truy cập khóa hoặc yêu cầu sử dụng khóa. Tùy kiến trúc, event có thể được phát ra từ KMS, HSM, provider mật mã, dịch vụ quản lý khóa hoặc lớp ứng dụng điều phối thao tác.

Một event thường biểu diễn một hành động cụ thể:

- `Encrypt` hoặc `Decrypt` bằng một key ID.
- `Sign` hoặc `Verify` bằng khóa tương ứng.
- `WrapKey` hoặc `UnwrapKey` trong envelope encryption.
- `GetKey`, `GetSecret` hoặc thao tác lấy key handle/metadata.
- `ExportKey` hoặc `ImportKey`.
- `DescribeKey`, thay đổi policy, disable, enable, rotate hoặc schedule deletion.
- Một yêu cầu bị từ chối do principal không có quyền, khóa không hoạt động hoặc policy không thỏa điều kiện.

Không phải mọi hệ thống đều gọi tất cả những hành động này là “key access”. Một số KMS ghi riêng event cho thao tác mật mã, thao tác quản trị và thao tác export. Điều quan trọng là tổ chức phải hiểu event source thực sự ghi nhận điều gì và tránh diễn giải một event `Decrypt` thành bằng chứng rằng key material đã được đọc ra.

## 2. Vì sao cần ghi nhận sự kiện truy cập khóa?

Key accessed event hỗ trợ nhiều mục tiêu bảo mật và vận hành:

1. **Accountability:** xác định principal hoặc workload chịu trách nhiệm cho thao tác với khóa.
2. **Threat detection:** phát hiện tần suất giải mã tăng đột biến, truy cập từ workload lạ hoặc thao tác ngoài giờ.
3. **Incident response:** dựng lại chuỗi hành động trước, trong và sau thời điểm nghi ngờ lộ khóa.
4. **Compliance:** chứng minh tổ chức có kiểm soát quyền sử dụng khóa và lưu bằng chứng audit.
5. **Capacity and reliability:** nhận biết lỗi provider, KMS throttling, HSM unavailable hoặc workload gọi API quá mức.
6. **Lifecycle governance:** xác định khóa còn được dùng ở đâu trước khi disable, rotate hoặc destroy.

Ví dụ, trước khi thu hồi một KEK, đội vận hành có thể truy vấn event theo key ID để xác định workload nào còn gọi `Decrypt` hoặc `UnwrapKey`. Nếu vẫn có hoạt động hợp lệ, họ cần phối hợp chuyển workload và dữ liệu trước khi vô hiệu hóa khóa.

## 3. Phân biệt truy cập metadata, sử dụng khóa và export key material

Một event cần phân biệt rõ loại truy cập vì mức độ rủi ro khác nhau.

| Nhóm hành động | Ví dụ | Ý nghĩa audit |
|---|---|---|
| Đọc metadata | `DescribeKey`, đọc trạng thái hoặc alias | Principal biết thông tin mô tả khóa; không nhất thiết sử dụng key material |
| Crypto operation | `Encrypt`, `Decrypt`, `Sign`, `Verify`, `Mac`, `DeriveKey` | Principal yêu cầu hệ thống thực hiện phép toán bằng khóa |
| Key wrapping | `WrapKey`, `UnwrapKey` | Khóa khác được bảo vệ hoặc mở bằng wrapping key; cần ghi rõ key ID của các khóa liên quan |
| Lấy key handle | Lấy đối tượng tham chiếu đến khóa trong provider/HSM | Có quyền sử dụng theo policy; không đồng nghĩa key bytes đã được xuất |
| Export | `ExportPlaintext`, `ExportWrapped` | Key material được đưa ra khỏi ranh giới quản lý theo định dạng cụ thể |
| Quản trị | `CreateKey`, `DisableKey`, `RotateKey`, `SetPolicy`, `ScheduleDeletion` | Thay đổi trạng thái hoặc cách khóa được quản lý |

Không nên gộp tất cả thành một event tên `KEY_ACCESS` mà không có trường `action` hoặc `operation`. Nếu hệ thống chuẩn hóa thành một taxonomy chung, cần giữ trường chi tiết để phân biệt đọc metadata, crypto operation và export.

## 4. Nguồn phát sinh event

Event nên được ghi tại thành phần có khả năng quan sát chính xác thao tác và kết quả.

| Nguồn | Thông tin thường quan sát được | Giới hạn cần lưu ý |
|---|---|---|
| KMS audit log | Principal, key ID, API action, policy result, thời gian, request ID | Tên trường và độ chi tiết phụ thuộc nhà cung cấp; có thể không có ngữ cảnh nghiệp vụ của ứng dụng |
| HSM audit log | Session, object/handle, operation, login, lỗi thiết bị | Có thể dùng mã object nội bộ và cần ánh xạ sang key inventory |
| Java security provider | Dịch vụ/thuật toán, provider, một số lỗi và thao tác được wrapper quan sát | Không phải provider nào cũng phát audit event đầy đủ; log ứng dụng không thay thế audit ở HSM |
| Ứng dụng | User/workload, request ID, tenant, mục đích nghiệp vụ và kết quả | Có thể bị bỏ qua nếu ứng dụng bị xâm nhập; không phải nguồn duy nhất đáng tin cậy |
| IAM/policy engine | Quyết định allow/deny, principal, policy và điều kiện | Có thể không biết crypto operation có thực sự hoàn tất hay không |

Với khóa nằm trong KMS/HSM, audit tại ranh giới dịch vụ hoặc thiết bị thường là nguồn bằng chứng quan trọng nhất cho thao tác thực tế. Ứng dụng có thể bổ sung context nghiệp vụ như `orderId` hoặc `tenantId`, nhưng không nên tự tuyên bố thao tác thành công nếu KMS/HSM trả lỗi.

## 5. Trường dữ liệu cần có trong Key accessed event

Một event có cấu trúc nên có các nhóm trường sau:

| Nhóm | Trường gợi ý | Mục đích |
|---|---|---|
| Định danh event | `eventId`, `eventType`, `schemaVersion` | Nhận diện duy nhất và hỗ trợ thay đổi schema |
| Thời gian | `eventTime`, `ingestTime` | Phân biệt lúc thao tác xảy ra với lúc hệ thống nhận log |
| Principal | `principalId`, `principalType`, `credentialId` | Xác định người dùng, service account hoặc workload |
| Tài nguyên | `keyId`, `keyVersion`, `keyType`, `keyOwner` | Xác định khóa bị truy cập |
| Thao tác | `action`, `operation`, `accessMode` | Phân biệt metadata, crypto operation, export và quản trị |
| Quyết định | `authorizationDecision`, `policyId`, `denialReason` | Ghi nhận allow/deny và căn cứ chính sách |
| Kết quả | `outcome`, `errorCode`, `durationMs` | Biết thao tác hoàn tất, thất bại hay bị từ chối |
| Ngữ cảnh | `sourceService`, `environment`, `region`, `networkContext` | Hỗ trợ phát hiện truy cập bất thường |
| Tương quan | `requestId`, `traceId`, `sessionId`, `correlationId` | Liên kết event với request và các log liên quan |
| Quản trị | `changeTicket`, `approvalId`, `reason` | Truy vết thao tác đặc quyền hoặc thay đổi đã duyệt |

Không phải event nào cũng có mọi trường. Ví dụ một thao tác `Verify` có thể dùng khóa công khai; event không cần có `keyOwner` nếu inventory không cung cấp. Trường bắt buộc nên được định nghĩa trong schema nội bộ, còn trường tùy chọn cần ghi rõ khi không có dữ liệu.

Thời gian nên ở định dạng UTC có độ chính xác phù hợp. `eventTime` phải phản ánh thời điểm thao tác tại nguồn; `ingestTime` phản ánh thời điểm pipeline nhận event. Chênh lệch giữa hai thời điểm giúp phát hiện log bị trễ hoặc pipeline có vấn đề.

## 6. Ví dụ event có cấu trúc

Ví dụ dưới đây là JSON minh họa một lần KMS cho phép workload giải mã dữ liệu bằng một key version:

```json
{
  "eventId": "evt-01JKEYACCESS9M4Q",
  "schemaVersion": "1.0",
  "eventType": "KEY_ACCESS",
  "eventTime": "2026-11-28T04:25:12.481Z",
  "ingestTime": "2026-11-28T04:25:12.620Z",
  "principal": {
    "id": "workload:billing-api",
    "type": "SERVICE_ACCOUNT"
  },
  "resource": {
    "keyId": "kms/prod/billing-dek-kek",
    "keyVersion": "v7",
    "keyType": "SYMMETRIC"
  },
  "action": "Decrypt",
  "accessMode": "CRYPTO_OPERATION",
  "authorization": {
    "decision": "ALLOW",
    "policyId": "billing-api-decrypt-v3"
  },
  "result": {
    "outcome": "SUCCESS",
    "durationMs": 18
  },
  "context": {
    "environment": "production",
    "region": "ap-southeast-1",
    "requestId": "req-8f12a9",
    "traceId": "trace-43b7d1"
  }
}
```

Ví dụ này không chứa key bytes, password, plaintext hay ciphertext. Nếu event cần chỉ ra dữ liệu nào được giải mã, chỉ nên dùng một định danh nghiệp vụ hoặc phân loại dữ liệu đã được phê duyệt; tránh đưa nội dung nhạy cảm vào log.

Với một yêu cầu bị từ chối, event cần ghi `decision=DENY`, kết quả `DENIED` và mã lý do đủ để điều tra, chẳng hạn `ACCESS_DENIED`, `KEY_DISABLED`, `INVALID_KEY_STATE` hoặc `POLICY_CONDITION_FAILED`. Không ghi thông tin xác thực được gửi kèm yêu cầu.

## 7. Ghi event mà không làm lộ key material

Audit phải ghi nhận việc sử dụng khóa nhưng không trở thành một kênh rò rỉ khóa. Không đưa các dữ liệu sau vào event:

- Key bytes, private key encoding hoặc giá trị `SecretKey.getEncoded()`.
- Password, PIN, API token, client secret hoặc access token.
- Plaintext trước mã hóa hoặc sau giải mã.
- Wrapped key nếu tổ chức xem gói đó là dữ liệu có thể khôi phục nhạy cảm và không có nhu cầu audit rõ ràng.
- Nonce, ciphertext hoặc AAD nếu chúng chứa dữ liệu nhạy cảm hay không cần thiết cho mục tiêu audit.
- Nội dung request/response đầy đủ hoặc stack trace có thể chứa bí mật.

Thông thường, key ID, key version, action, principal, decision, result và request ID đã đủ để kiểm toán. Nếu cần kiểm tra dữ liệu, dùng một mã tham chiếu đã được kiểm soát thay vì ghi dữ liệu đó trực tiếp.

Log nên dùng allowlist trường được phép ghi thay vì serialize toàn bộ request object. Cách này giảm nguy cơ một trường mới được thêm vào request sẽ vô tình xuất hiện trong audit.

## 8. Ví dụ Java: phát audit event cho thao tác dùng khóa

Ứng dụng có thể bổ sung context nghiệp vụ cho audit sau khi gọi KMS/provider. Ví dụ dưới đây minh họa một record event và một interface phát event. Trong thực tế, audit source có thẩm quyền của KMS/HSM vẫn cần được bật để ghi nhận thao tác ở ranh giới quản lý khóa.

```java
import java.time.Instant;

public record KeyAccessEvent(
        String eventId,
        Instant eventTime,
        String principalId,
        String keyId,
        String keyVersion,
        String action,
        String authorizationDecision,
        String outcome,
        String requestId,
        long durationMs,
        String errorCode) {}

public interface KeyAuditSink {
    void publish(KeyAccessEvent event);
}
```

Một wrapper có thể phát event cho kết quả thao tác:

```java
import java.time.Instant;
import java.util.UUID;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;

public final class AuditedDecryptor {
    private final KeyAuditSink auditSink;

    public AuditedDecryptor(KeyAuditSink auditSink) {
        this.auditSink = auditSink;
    }

    public byte[] decrypt(
            SecretKey key,
            String keyId,
            String keyVersion,
            String principalId,
            String requestId,
            byte[] nonce,
            byte[] ciphertext) throws Exception {

        String eventId = UUID.randomUUID().toString();
        long startedAt = System.nanoTime();
        byte[] plaintext;
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key,
                    new javax.crypto.spec.GCMParameterSpec(128, nonce));
            plaintext = cipher.doFinal(ciphertext);
        } catch (Exception e) {
            try {
                auditSink.publish(new KeyAccessEvent(
                        eventId, Instant.now(), principalId, keyId, keyVersion,
                        "Decrypt", "ALLOW", "FAILURE", requestId,
                        (System.nanoTime() - startedAt) / 1_000_000,
                        e.getClass().getSimpleName()));
            } catch (RuntimeException auditFailure) {
                e.addSuppressed(auditFailure);
            }
            throw e;
        }

        auditSink.publish(new KeyAccessEvent(
                eventId, Instant.now(), principalId, keyId, keyVersion,
                "Decrypt", "ALLOW", "SUCCESS", requestId,
                (System.nanoTime() - startedAt) / 1_000_000, null));
        return plaintext;
    }
}
```

Đây là ví dụ đơn giản để minh họa cấu trúc event, không phải audit system hoàn chỉnh. `authorizationDecision=ALLOW` trong ví dụ chỉ thể hiện ứng dụng đã cho phép gọi wrapper; nếu KMS/HSM thực hiện policy evaluation riêng, cần lấy decision từ nguồn audit có thẩm quyền. Với thao tác bị từ chối trước khi gọi provider, ứng dụng hoặc policy engine phải ghi event deny tương ứng. Phần phát event thành công nằm ngoài `try/catch` của thao tác giải mã để lỗi ghi audit không bị hiểu nhầm thành lỗi giải mã. Production nên dùng sink bền vững/outbox và xác định rõ hành vi khi sink lỗi để tránh mất event hoặc khiến client retry thao tác đã hoàn tất.

Trong production, cần bảo đảm audit event không bị mất khi sink tạm thời không khả dụng. Có thể dùng queue bền vững hoặc outbox, retry có giới hạn và cảnh báo khi backlog tăng. Quyết định có chặn thao tác mật mã khi audit sink lỗi hay không phải dựa trên yêu cầu bảo mật và tính sẵn sàng; với thao tác đặc quyền hoặc export, chính sách có thể yêu cầu fail-closed.

## 9. Bảo vệ tính toàn vẹn và tính sẵn sàng của audit log

Nếu attacker có thể sửa hoặc xóa event, audit không còn là bằng chứng đáng tin cậy. Vì vậy, hệ thống cần bảo vệ cả log tại nguồn và pipeline chuyển tiếp.

Các biện pháp thường dùng:

- Gửi log tới kho tập trung với quyền ghi riêng cho agent và quyền đọc riêng cho auditor.
- Dùng storage có retention lock hoặc cơ chế chống sửa/xóa theo chính sách.
- Ký hoặc tạo hash chain cho batch log khi cần phát hiện thay đổi; bảo vệ khóa ký audit độc lập với khóa ứng dụng.
- Đồng bộ thời gian bằng nguồn tin cậy; giám sát clock drift và event đến trễ.
- Mã hóa log khi truyền và khi lưu; quản lý khóa mã hóa log tách khỏi khóa được audit.
- Giám sát pipeline, queue, collector, dropped event, retry và dung lượng lưu trữ.
- Phân tách người quản trị KMS/HSM khỏi người có quyền sửa hoặc xóa audit log.
- Kiểm thử khả năng truy xuất log trong sự cố và bảo đảm retention đáp ứng chính sách.

Không dùng chính key đang được audit để ký hoặc mã hóa audit log của nó nếu điều đó tạo ra vòng phụ thuộc hoặc cho phép người quản lý key sửa bằng chứng. Khóa bảo vệ audit cần có ownership, quyền và quy trình phục hồi riêng.

## 10. Monitoring và phát hiện truy cập bất thường

Audit event là dữ liệu đầu vào cho monitoring. Một event đơn lẻ có thể hợp lệ, nhưng chuỗi event hoặc thay đổi hành vi có thể cho thấy nguy cơ.

Một số quy tắc phát hiện:

| Tín hiệu | Dấu hiệu cần điều tra |
|---|---|
| Tần suất `Decrypt` tăng đột biến | Workload có thể đang đọc dữ liệu hàng loạt hoặc credential bị lạm dụng |
| Principal mới dùng key nhạy cảm | Có thể có quyền IAM bị cấp sai hoặc workload lạ |
| Truy cập ngoài môi trường/region dự kiến | Có thể là cấu hình sai hoặc hoạt động trái phép |
| Nhiều request bị deny | Có thể là dò quyền, credential cũ hoặc thay đổi policy không đồng bộ |
| `ExportKey` hoặc `GetKeyMaterial` bất thường | Nguy cơ key material rời khỏi ranh giới bảo vệ |
| `DisableKey`, `ScheduleDeletion` không có change ticket | Nguy cơ phá hoại hoặc thao tác quản trị sai |
| Một key version đột nhiên không còn được dùng | Có thể rotation đã hoàn tất hoặc workload bị lỗi; cần đối chiếu kế hoạch |
| Audit event bị trễ hoặc mất | Có thể pipeline bị gián đoạn hoặc log bị can thiệp |

Monitoring nên kết hợp baseline theo workload, loại khóa, môi trường, giờ hoạt động và lượng dữ liệu. Không nên đặt một ngưỡng cố định cho mọi khóa vì một dịch vụ mã hóa lưu lượng cao có hành vi khác một khóa ký quản trị ít dùng.

## 11. Metrics và dashboard cho key access

Ngoài từng event, cần theo dõi số liệu tổng hợp để nhận biết xu hướng và lỗi vận hành.

Các metrics hữu ích gồm:

- Số thao tác theo `keyId`, `action`, `principal` và `outcome`.
- Tỷ lệ allow/deny theo workload và policy.
- Tỷ lệ lỗi KMS/HSM, timeout, throttling và latency p50/p95/p99.
- Số lần export, unwrap, decrypt và sign theo thời gian.
- Số lượng key version active, disabled, retired và sắp hết hạn.
- Thời gian từ event xảy ra đến khi event vào SIEM.
- Số event bị drop, retry hoặc nằm trong queue quá thời hạn.
- Số principal mới truy cập key và số lần thay đổi policy.

Không nên dùng key material, token hoặc dữ liệu nhạy cảm làm metric label. `keyId` có thể có cardinality cao; dashboard nên cân nhắc nhóm theo owner, service, environment hoặc key classification, còn truy vấn chi tiết dùng log/event store.

## 12. Tương quan event và điều tra sự cố

Một thao tác nghiệp vụ có thể tạo nhiều event: ứng dụng nhận request, policy engine đánh giá quyền, KMS thực hiện decrypt, database trả dữ liệu và ứng dụng trả response. Để điều tra, cần liên kết các event bằng `requestId`, `traceId`, `sessionId` hoặc correlation ID đã được chuẩn hóa.

Khi điều tra một key ID, nên dựng timeline gồm:

1. Thời điểm tạo khóa và các lần thay đổi metadata/policy.
2. Principal đã truy cập và loại thao tác được gọi.
3. Các lần allow, deny, failure và timeout.
4. Thay đổi quyền IAM, role, workload identity và provider configuration.
5. Các lần export, wrap, unwrap, backup, import và rotation.
6. Sự kiện thu hồi, disable, schedule deletion hoặc destroy.
7. Request nghiệp vụ và dữ liệu phụ thuộc trong khoảng thời gian liên quan.

Nếu nghi ngờ key compromise, cần xác định không chỉ ai đã gọi API mà còn có khả năng key material đã được export hoặc truy cập qua một đường khác hay không. Event `Decrypt` thành công chứng minh thao tác giải mã được thực hiện, nhưng không tự chứng minh plaintext đã được người dùng hợp lệ nhận hoặc không bị lưu ở nơi khác.

## 13. Retention và quyền truy cập audit

Audit log có thể chứa thông tin định danh, cấu trúc hệ thống và hoạt động nhạy cảm. Cần giới hạn quyền truy cập và thời gian lưu giữ theo mục tiêu điều tra, yêu cầu pháp lý và chính sách tổ chức.

Một chính sách retention nên xác định:

- Nhóm event nào cần lưu lâu hơn, chẳng hạn export, key policy change, destroy và thao tác với root key.
- Thời gian lưu hot để truy vấn nhanh và thời gian lưu archive.
- Cách bảo vệ archive, mã hóa, integrity và khả năng khôi phục.
- Ai được truy vấn, export hoặc xóa log; việc xóa phải được kiểm soát và ghi audit riêng.
- Cách xử lý dữ liệu cá nhân hoặc thông tin nghiệp vụ không cần thiết trong event.
- Cách bảo toàn bằng chứng khi có incident hoặc yêu cầu legal hold.

Không lưu vô hạn mọi trường chỉ vì có thể. Thu thập tối thiểu và retention có mục tiêu giúp giảm rủi ro riêng tư, chi phí và phạm vi dữ liệu bị lộ nếu hệ thống log bị xâm nhập.

## 14. Checklist triển khai Key accessed event

- Định nghĩa taxonomy event cho metadata access, crypto operation, export và key administration.
- Bật audit tại KMS/HSM/provider ở nơi có thể quan sát thao tác thực tế.
- Ghi principal, key ID/version, action, decision, outcome, timestamp và request/correlation ID.
- Ghi cả allow, deny, failure và thao tác quản trị nhạy cảm.
- Phân biệt `eventTime` và `ingestTime`; đồng bộ thời gian.
- Không ghi key material, password, token, plaintext hoặc dữ liệu nhạy cảm không cần thiết.
- Bổ sung context nghiệp vụ từ ứng dụng mà không thay thế audit ở KMS/HSM.
- Bảo vệ log khỏi sửa/xóa; tách quyền quản trị log và quyền quản lý khóa.
- Giám sát event bị drop, pipeline trễ, queue backlog và dung lượng lưu trữ.
- Tạo cảnh báo cho export bất thường, decrypt tăng đột biến, principal lạ và thay đổi policy.
- Xác định retention, quyền truy vấn, archive và legal hold.
- Diễn tập truy vấn timeline theo key ID và điều tra một sự kiện truy cập trái phép.

Key accessed event là nền tảng để biến hoạt động sử dụng khóa thành bằng chứng có thể kiểm toán và dữ liệu có thể giám sát. Event tốt phải xác định đúng principal, khóa, thao tác, quyết định và kết quả; được phát từ nguồn đáng tin cậy; bảo vệ tính toàn vẹn và sẵn sàng; đồng thời tránh ghi key material hoặc plaintext. Khi kết hợp audit ở KMS/HSM với context ứng dụng và monitoring theo baseline, tổ chức có thể phát hiện truy cập bất thường, điều tra sự cố và quản trị vòng đời khóa dựa trên bằng chứng.

## Tài liệu tham khảo

- [NIST SP 800-57 Part 1 Rev. 5: Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final)
- [NIST SP 800-92: Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final)
- [NIST SP 800-53 Rev. 5: Security and Privacy Controls for Information Systems and Organizations](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [Java SE API: `java.security.Provider`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Provider.html)
