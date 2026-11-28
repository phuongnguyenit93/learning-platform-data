# Thiết kế audit cho key usage

Bài toán đặt ra: một nền tảng SaaS lưu trữ tài liệu cho nhiều khách hàng cần chứng minh được **ai hoặc workload nào đã sử dụng khóa nào, để thực hiện thao tác gì, vào thời điểm nào và kết quả ra sao**. Khi phát hiện một tài khoản dịch vụ bất thường, đội bảo mật phải truy vết được các lần giải mã, ký, tạo data key và thay đổi quyền có liên quan, đồng thời xác định tenant và dữ liệu có thể bị ảnh hưởng.

Audit cho key usage không chỉ là ghi một dòng log khi gọi KMS. Hệ thống cần kết hợp audit event do ứng dụng phát ra, audit log độc lập từ KMS/HSM, quyết định policy, thay đổi quản trị và metadata nghiệp vụ. Các nguồn này phải liên kết được với nhau bằng request ID và correlation ID, được bảo vệ khỏi sửa đổi, và không chứa key material, plaintext hoặc credential.

Case study sử dụng envelope encryption: dữ liệu tài liệu được mã hóa bằng DEK với AES-GCM; DEK được wrap bằng KEK trong KMS. Ứng dụng không export KEK. Bài toán tập trung vào thiết kế audit xuyên suốt thao tác sử dụng khóa và quy trình điều tra.

## 1. Bối cảnh hệ thống và yêu cầu

Nền tảng có các thành phần:

- API Gateway xác thực request từ người dùng.
- Document Service xử lý đọc/ghi tài liệu cho nhiều tenant.
- Key Access Adapter gọi KMS để tạo hoặc unwrap DEK.
- KMS quản lý KEK, policy, version và audit log riêng.
- Audit Publisher phát sự kiện ứng dụng tới durable event stream.
- Central Audit Store lưu bằng chứng dài hạn.
- SIEM/Monitoring phân tích hành vi và tạo cảnh báo.
- Security Operations điều tra sự kiện đáng ngờ.

Mỗi tenant có một logical key hoặc key hierarchy riêng theo chính sách phân vùng dữ liệu. Một số tenant có thể dùng KEK riêng; các tenant khác có thể dùng key theo nhóm nếu mô hình rủi ro và yêu cầu cách ly cho phép. Mọi bản ghi mã hóa phải lưu key version ID hoặc metadata đủ để xác định chính xác version cần dùng.

Yêu cầu nghiệp vụ và bảo mật:

1. Truy vết được thao tác mã hóa, giải mã, ký và quản trị khóa.
2. Phân biệt người dùng cuối với workload thực sự gọi KMS.
3. Liên kết thao tác ứng dụng với request KMS/HSM tương ứng.
4. Ghi nhận cả thành công, bị từ chối, thất bại và throttling.
5. Phát hiện một principal truy cập bất thường nhiều key hoặc nhiều tenant.
6. Bảo vệ audit evidence kể cả khi Document Service bị xâm phạm.
7. Không ghi plaintext, DEK, KEK, token hoặc ciphertext nhạy cảm vào log.
8. Có thể xác định phạm vi ảnh hưởng khi credential hoặc key bị compromise.
9. Đáp ứng retention và kiểm soát truy cập của tổ chức.
10. Không để lỗi pipeline audit âm thầm làm mất bằng chứng.

## 2. Phạm vi audit và các loại sự kiện

Cần phân biệt ba nhóm sự kiện vì chúng được phát ra ở các ranh giới khác nhau.

| Nhóm | Ví dụ | Nguồn chính |
|---|---|---|
| Key usage | Encrypt, Decrypt, Sign, Verify, GenerateDataKey, Unwrap/Wrap | Ứng dụng và KMS/HSM |
| Key administration | Create, Import, Rotate, Disable, ScheduleDeletion, Destroy, PolicyChange, Grant | KMS/HSM và control plane |
| Access governance | Authentication, AuthorizationDecision, JITGrant, Approval, Revoke | Identity Provider, policy engine, access broker |

Audit của KMS có thể ghi nhận API Decrypt đã được gọi trên KEK để unwrap DEK. Nhưng sau khi DEK được trả về, ứng dụng có thể thực hiện AES-GCM trực tiếp trong process. KMS không nhìn thấy thao tác giải mã dữ liệu đó. Vì vậy, cần có application-level event cho thao tác sử dụng DEK, còn KMS audit là bằng chứng độc lập cho thao tác unwrap.

Ngược lại, không nên tự tạo một application event giả định KMS đã thành công trước khi nhận response từ KMS. Event phải phản ánh đúng ranh giới thực thi: request được gửi, provider trả kết quả, và ứng dụng hoàn tất hoặc từ chối nghiệp vụ.

## 3. Kiến trúc audit đề xuất

Luồng đọc tài liệu minh họa:

~~~mermaid
flowchart LR
    U[User / Client] --> API[API Gateway]
    API --> DOC[Document Service]
    DOC --> KMSA[Key Access Adapter]
    KMSA --> KMS[KMS / HSM]
    DOC --> APPLOG[Application Audit Event]
    KMS --> KMSLOG[Provider Audit Log]
    APPLOG --> STREAM[Durable Audit Stream]
    KMSLOG --> COLLECT[Independent Log Collector]
    STREAM --> STORE[Central Immutable Audit Store]
    COLLECT --> STORE
    STORE --> SIEM[SIEM / Detection]
    SIEM --> SOC[Security Operations]
~~~

Các ranh giới quan trọng:

- API Gateway xác thực người dùng và tạo request context.
- Document Service xác định tenant, tài nguyên nghiệp vụ và operation.
- Key Access Adapter xác thực workload identity với KMS.
- KMS/HSM tự ghi audit ở phía dịch vụ, độc lập với application logger.
- Application Audit Event ghi ngữ cảnh nghiệp vụ và thao tác DEK mà KMS không quan sát được.
- Central Audit Store nhận log từ hai pipeline độc lập.
- SIEM nối sự kiện để phát hiện bất thường.

Audit log KMS nên được chuyển tới tài khoản, project hoặc hệ thống lưu trữ có quyền quản trị tách biệt với Document Service. Nếu ứng dụng bị chiếm quyền, attacker không được có quyền xóa hoặc sửa bằng chứng phía KMS.

## 4. Xác định chủ thể thực hiện thao tác

Một request đọc tài liệu có thể liên quan đến nhiều danh tính:

- **Initiating actor:** người dùng hoặc hệ thống khởi tạo nghiệp vụ.
- **Authenticated principal:** danh tính đã được API Gateway xác thực.
- **Workload principal:** service account hoặc workload identity gọi KMS.
- **Approver:** người phê duyệt JIT hoặc thao tác đặc quyền nếu có.
- **Effective principal:** danh tính mà policy engine dùng để quyết định quyền cuối cùng.

Không gộp tất cả vào một trường user ID. Ví dụ, người dùng A yêu cầu tải tài liệu, Document Service dùng workload identity document-reader để unwrap DEK. Audit cần ghi cả actor A và workload principal document-reader, đồng thời liên kết hai danh tính bằng correlation ID.

Không tin một actor ID do client tự gửi. Actor phải đến từ token đã xác minh hoặc identity context đáng tin cậy. Tenant ID và resource ID phải được lấy từ authorization context đã kiểm tra, không lấy từ header tùy ý rồi coi là sự thật.

## 5. Thiết kế schema cho Key Usage Event

Một event có cấu trúc giúp truy vấn, đối chiếu và cảnh báo nhất quán. Ví dụ schema:

| Trường | Ý nghĩa | Lưu ý |
|---|---|---|
| event_id | Định danh duy nhất của event | UUID hoặc ID do hệ thống cấp |
| schema_version | Phiên bản schema event | Hỗ trợ parser và detection tương thích |
| event_time | Thời điểm phát sinh UTC | Dùng clock đồng bộ |
| event_type | KEY_USAGE hoặc KEY_ADMINISTRATION | Phân biệt nhóm sự kiện |
| outcome | SUCCESS, DENIED, FAILED, THROTTLED | Kết quả thực tế |
| operation | ENCRYPT, DECRYPT, SIGN, UNWRAP, ROTATE... | Enum chuẩn hóa |
| actor_id | Người/hệ thống khởi tạo | Từ identity đã xác thực |
| actor_type | HUMAN, SERVICE, WORKLOAD | Tránh mơ hồ |
| workload_id | Workload thực sự gọi KMS | Ví dụ service account |
| tenant_ref | Tenant đã được authorization | Có thể pseudonymize |
| resource_ref | Tài liệu hoặc resource nghiệp vụ | Dùng ID nội bộ, không dùng nội dung |
| key_ref | Logical key hoặc key ID | Bảo vệ quyền đọc trường này |
| key_version | Phiên bản khóa đã sử dụng | Không dùng alias thay cho version |
| operation_scope | Mục đích và phạm vi | Ví dụ document-read |
| policy_decision | ALLOW hoặc DENY | Kèm policy version nếu phù hợp |
| request_id | ID từ KMS/HSM hoặc dịch vụ đích | Chỉ có sau khi nhận response |
| correlation_id | Nối API, ứng dụng, KMS và SIEM | Tạo ở ranh giới request |
| source_service | Thành phần phát event | Document Service, KMS collector... |
| environment | DEV, STAGING, PROD | Dùng nhãn chuẩn hóa |
| failure_category | AUTH, POLICY, KEY_STATE, PROVIDER... | Chỉ có khi thất bại |
| approval_ref | JIT/ticket/approval liên quan | Không ghi nội dung ticket nhạy cảm |

Schema có thể mở rộng theo nền tảng, nhưng phải duy trì tên trường và semantics ổn định. Thay đổi schema nên có version để parser và detection rule không hiểu sai event cũ.

Không đưa vào event:

- Raw key material, private key, DEK hoặc KEK.
- Password, access token, refresh token, session cookie hoặc credential.
- Plaintext tài liệu, nội dung request hoặc dữ liệu khách hàng.
- Ciphertext đầy đủ nếu không cần cho điều tra.
- Secret nằm trong exception message hoặc stack trace.
- Dữ liệu cá nhân không cần thiết cho mục tiêu audit.

Key ID và tenant reference vẫn có thể nhạy cảm vì tiết lộ cấu trúc hệ thống. Giới hạn quyền truy cập, mã hóa log và cân nhắc pseudonymization ở dashboard diện rộng.

## 6. Phân biệt event ở ứng dụng và event từ KMS/HSM

Một thao tác đọc tài liệu với envelope encryption có thể tạo chuỗi event:

| Bước | Event | Nguồn | Nội dung cần chứng minh |
|---|---|---|---|
| 1 | DOCUMENT_READ_REQUESTED | API/Application | Actor yêu cầu đọc tài liệu |
| 2 | KEY_ACCESS_DECISION | Policy Engine | Workload được phép dùng key trong context |
| 3 | KMS_DECRYPT_REQUEST | KMS audit | Workload gọi KMS để unwrap encrypted DEK |
| 4 | KMS_DECRYPT_RESULT | KMS audit | KMS chấp nhận hoặc từ chối operation |
| 5 | DATA_DECRYPT | Document Service | DEK được dùng để giải mã payload trong ứng dụng |
| 6 | DOCUMENT_READ_COMPLETED | Application | Nghiệp vụ đọc hoàn tất hoặc bị từ chối |

Không phải hệ thống nào cũng tạo đủ event như bảng trên. Một số provider ghi một event duy nhất có request và outcome; một số tách API call và result. Adapter cần ánh xạ theo log schema thực tế, giữ nguyên request ID và không tự bịa event provider không phát ra.

Nếu ứng dụng chỉ log DOCUMENT_READ_COMPLETED, đội điều tra không biết thao tác key nào đã diễn ra. Nếu chỉ dựa vào KMS log, họ có thể biết workload unwrap DEK nhưng không biết tài liệu hoặc tenant nghiệp vụ nào được đọc. Cần hai góc nhìn để dựng được chuỗi đầy đủ.

## 7. Correlation ID và liên kết bằng chứng

Mỗi request nghiệp vụ cần một correlation ID do hệ thống tin cậy tạo ra. ID này được truyền qua các service nội bộ và gắn vào application audit event. Khi gọi KMS, adapter ghi correlation ID vào trường encryption context hoặc request context nếu dịch vụ hỗ trợ; đồng thời lưu KMS request ID trả về.

Các nguyên tắc:

- Correlation ID không phải credential và không cấp quyền.
- Không dùng một ID cố định cho nhiều request độc lập.
- Giữ nguyên ID qua retry của cùng một logical operation hoặc tạo attempt ID riêng.
- Lưu cả request ID của provider và correlation ID của ứng dụng.
- Không đưa dữ liệu nhạy cảm vào correlation ID.
- Nếu KMS không hỗ trợ metadata tùy chỉnh, lưu mapping request ID ↔ correlation ID ở audit event phía ứng dụng.

Với batch hoặc fan-out, mỗi operation key có thể có operation ID riêng nhưng cùng parent correlation ID. Nhờ vậy, có thể điều tra một request nghiệp vụ tạo ra nhiều KMS call mà không trộn các thao tác của request khác.

## 8. Quy trình phát event trong ứng dụng Java

Application event phải được tạo ở ranh giới nơi ứng dụng biết actor, tenant, resource, logical key và kết quả operation. Ví dụ sau minh họa event khi adapter unwrap DEK từ KMS. KMS vẫn có audit log độc lập; application event bổ sung ngữ cảnh và correlation.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;

public final class KeyUsageAudit {
    public enum Operation {
        UNWRAP_DATA_KEY,
        DATA_ENCRYPT,
        DATA_DECRYPT
    }

    public enum Outcome {
        SUCCESS,
        DENIED,
        FAILED
    }

    public record KeyUsageEvent(
            String eventId,
            int schemaVersion,
            String eventType,
            Instant eventTime,
            String actorId,
            String workloadId,
            String tenantRef,
            String resourceRef,
            String keyRef,
            String keyVersion,
            Operation operation,
            Outcome outcome,
            String policyDecision,
            String correlationId,
            String providerRequestId,
            String failureCategory) {
    }

    public record UnwrappedDataKey(byte[] keyBytes, String providerRequestId) {
    }

    public interface KmsPort {
        UnwrappedDataKey unwrap(
                String keyRef,
                String keyVersion,
                byte[] encryptedDataKey) throws KmsFailureException;
    }

    public interface AuditPublisher {
        // publish phải trả về sau khi event đã được durable-accepted.
        void publish(KeyUsageEvent event) throws AuditUnavailableException;
    }

    public static final class KmsFailureException extends Exception {
        private final String failureCategory;
        private final String providerRequestId;

        public KmsFailureException(
                String message,
                String failureCategory,
                String providerRequestId) {
            super(message);
            this.failureCategory = failureCategory;
            this.providerRequestId = providerRequestId;
        }

        public String failureCategory() {
            return failureCategory;
        }

        public String providerRequestId() {
            return providerRequestId;
        }
    }

    public static final class AuditUnavailableException extends Exception {
        public AuditUnavailableException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    private final KmsPort kms;
    private final AuditPublisher audit;
    private final Clock clock;

    public KeyUsageAudit(KmsPort kms, AuditPublisher audit, Clock clock) {
        this.kms = kms;
        this.audit = audit;
        this.clock = clock;
    }

    public byte[] unwrap(
            String actorId,
            String workloadId,
            String tenantRef,
            String resourceRef,
            String keyRef,
            String keyVersion,
            String correlationId,
            byte[] encryptedDataKey) throws Exception {

        try {
            UnwrappedDataKey result = kms.unwrap(
                keyRef,
                keyVersion,
                encryptedDataKey
            );

            try {
                audit.publish(new KeyUsageEvent(
                    UUID.randomUUID().toString(),
                    1,
                    "KEY_USAGE",
                    clock.instant(),
                    actorId,
                    workloadId,
                    tenantRef,
                    resourceRef,
                    keyRef,
                    keyVersion,
                    Operation.UNWRAP_DATA_KEY,
                    Outcome.SUCCESS,
                    "ALLOW",
                    correlationId,
                    result.providerRequestId(),
                    null
                ));
            } catch (AuditUnavailableException auditFailure) {
                java.util.Arrays.fill(result.keyBytes(), (byte) 0);
                throw auditFailure;
            }

            return result.keyBytes();
        } catch (KmsFailureException failure) {
            try {
                audit.publish(new KeyUsageEvent(
                    UUID.randomUUID().toString(),
                    1,
                    "KEY_USAGE",
                    clock.instant(),
                    actorId,
                    workloadId,
                    tenantRef,
                    resourceRef,
                    keyRef,
                    keyVersion,
                    Operation.UNWRAP_DATA_KEY,
                    "AUTHORIZATION".equals(failure.failureCategory())
                        ? Outcome.DENIED : Outcome.FAILED,
                    "AUTHORIZATION".equals(failure.failureCategory())
                        ? "DENY" : "NOT_EVALUATED",
                    correlationId,
                    failure.providerRequestId(),
                    failure.failureCategory()
                ));
            } catch (AuditUnavailableException auditFailure) {
                failure.addSuppressed(auditFailure);
            }

            throw failure;
        }
    }
}
~~~

Đây là adapter minh họa. Trong triển khai thật:

- KMS SDK phải ánh xạ exception sang failure category ổn định, không parse message tùy tiện.
- actorId và workloadId phải đến từ security context đáng tin cậy.
- keyRef và keyVersion phải được lấy từ metadata đã xác thực.
- AuditPublisher phải có durable acknowledgment; trả về trước khi event được lưu bền vững sẽ không đáp ứng cam kết đó.
- Khi audit success không được ghi bền vững, ví dụ hủy buffer DEK là một lựa chọn fail-closed; ứng dụng cần xử lý exception và không tiếp tục trả plaintext.
- Với thao tác không nhạy cảm, policy có thể cho phép queue bền vững và cảnh báo thay vì chặn request; quyết định phải được tài liệu hóa.
- Không ghi encryptedDataKey, keyBytes hoặc plaintext vào event.
- Consumer phải xóa buffer DEK best-effort sau khi hoàn tất thao tác dữ liệu; không giữ DEK trong cache lâu hơn yêu cầu.

Khi giải mã payload bằng DEK trong ứng dụng, phát thêm event DATA_DECRYPT ở application boundary. Event đó dùng cùng correlation ID và key version metadata, nhưng không ghi DEK hoặc ciphertext.

## 9. Bảo đảm audit không bị mất

Một pipeline audit có thể thất bại do mạng, broker, quota, storage hoặc credential. Cần xác định rõ semantics khi publish:

| Cách xử lý | Ưu điểm | Rủi ro/điều kiện |
|---|---|---|
| Synchronous durable publish | Chỉ tiếp tục sau khi event được lưu bền vững | Tăng latency và có thể giảm availability |
| Transactional outbox | Ghi event cùng transaction nghiệp vụ rồi relay bất đồng bộ | Cần xử lý duplicate, relay delay và outbox access |
| Durable local queue | Tách request path khỏi broker | Cần bảo vệ queue, disk, capacity và replay |
| Best-effort logger | Đơn giản, ít ảnh hưởng request | Có thể mất bằng chứng; không phù hợp với operation rủi ro cao |

Với thao tác giải mã dữ liệu nhạy cảm, có thể yêu cầu fail-closed nếu không thể bảo đảm event được durable-accepted. Với các event telemetry ít rủi ro, có thể dùng queue bền vững và cảnh báo khi backlog tăng. Không nên có một chính sách duy nhất cho mọi event; hãy phân loại theo operation và yêu cầu audit.

Transactional outbox giúp tránh trường hợp nghiệp vụ commit thành công nhưng event chưa được ghi. Event relay có thể gửi lặp, do đó Central Audit Store cần idempotency theo event_id. Duplicate phải được nhận diện mà không làm mất bằng chứng về retry.

Cần giám sát audit pipeline như một dịch vụ production: queue depth, oldest event age, publish failure, delivery lag, dead-letter count, storage rejection và khoảng trống sequence nếu hệ thống dùng sequence.

## 10. Bảo vệ tính toàn vẹn và tính sẵn có của audit evidence

Audit store nên nằm ngoài quyền quản trị thường ngày của ứng dụng tạo event. Các biện pháp:

- Gửi KMS/HSM audit trực tiếp tới collector độc lập.
- Dùng storage append-only hoặc immutable retention khi phù hợp.
- Tách role ghi, đọc, quản trị retention và xóa log.
- Ghi audit cả việc đọc, export, thay đổi policy và xóa audit store.
- Mã hóa log khi truyền và khi lưu.
- Bảo vệ signing key dùng ký manifest/log batch bằng quy trình độc lập.
- Đồng bộ thời gian bằng nguồn tin cậy và theo dõi clock drift.
- Có backup và kiểm thử restore audit evidence.
- Giám sát thay đổi cấu hình logging, collector và retention.

Hash chain hoặc chữ ký số trên batch có thể giúp phát hiện thay đổi sau khi tạo, nhưng không tự ngăn attacker bỏ qua bước ghi log hoặc tắt pipeline trước khi ký. Cần kết hợp nguồn log độc lập, quyền quản trị tách biệt, sequence/heartbeat và kiểm soát hạ tầng.

Không để cùng một workload có quyền dùng key để giải mã dữ liệu đồng thời có quyền xóa audit log chứng minh việc sử dụng key đó.

## 11. Bảo vệ quyền riêng tư và giảm dữ liệu nhạy cảm

Audit phải đủ chi tiết để điều tra nhưng không trở thành nơi tập trung dữ liệu nhạy cảm. Áp dụng data minimization:

- Dùng resource reference thay vì ghi tên tài liệu hoặc nội dung.
- Pseudonymize tenant/user trên dashboard rộng; chỉ giải mã mapping khi điều tra được ủy quyền.
- Không ghi request body, plaintext, DEK, KEK, token hoặc secret.
- Chuẩn hóa failure code thay vì ghi exception message có thể chứa credential.
- Phân loại audit field và áp dụng retention theo loại.
- Giới hạn truy vấn/export theo vai trò và ghi audit mọi lần truy cập evidence.
- Xóa hoặc ẩn danh trường không còn cần theo retention policy.

Key ID không phải lúc nào cũng là secret, nhưng có thể tiết lộ topology hoặc tenant relationship. Quyền truy cập audit store nên chặt chẽ như một hệ thống bảo mật nội bộ.

## 12. Detection rule và cảnh báo

Từ schema event, có thể tạo detection rule dựa trên principal, key, operation, tenant, thời gian và outcome.

| Mẫu phát hiện | Điều kiện minh họa | Phản ứng |
|---|---|---|
| Decrypt burst | Một workload có số lần DECRYPT vượt baseline trong cửa sổ ngắn | Tạm hạn chế principal, xác minh job và tenant |
| Cross-tenant access | Một workload truy cập key thuộc tenant ngoài assignment | Cảnh báo mức cao, kiểm tra authorization boundary |
| Key enumeration | Một principal thử nhiều key_ref với outcome DENIED | Điều tra dò tìm tài nguyên |
| Unusual workload | Key được dùng từ workload hoặc environment chưa từng thấy | Xác minh deployment và credential |
| Admin change before usage | Policy/grant thay đổi rồi xuất hiện nhiều key usage bất thường | Nối admin event với usage event |
| Audit pipeline gap | Không nhận heartbeat hoặc sequence liên tục bị đứt | Xử lý như sự cố logging, không giả định không có hoạt động |
| Decrypt outside JIT window | Event sử dụng key xuất hiện sau khi grant hết hạn | Kiểm tra cache/session semantics và policy enforcement |
| Rotation anomaly | Writer vẫn dùng key version cũ sau thời điểm promote | Điều tra consumer, cache và cấu hình |

Không dùng một ngưỡng cố định cho mọi tenant. Baseline cần phân biệt batch job, giờ cao điểm, workload đặc biệt và độ nhạy của key. Một lần truy cập key thuộc tenant khác có thể nghiêm trọng hơn hàng trăm request bị từ chối do token hết hạn.

Alert phải chứa event ID, correlation ID, principal, key reference đã bảo vệ, operation, outcome, thời gian, detection rule và đường dẫn tới evidence. Không đưa plaintext hoặc token vào notification.

## 13. Case điều tra: workload bị chiếm quyền

Giả sử lúc 02:14 UTC, SIEM phát hiện workload document-reader thực hiện số lượng lớn thao tác unwrap DEK trên nhiều tenant. Các event application cho thấy nhiều DATA_DECRYPT có correlation ID khác nhau; KMS audit xác nhận các request Decrypt đến từ cùng workload principal.

Quy trình điều tra:

1. Xác minh KMS request ID và correlation ID để loại trừ duplicate event.
2. Xác nhận workload identity, deployment version, host/cluster và network source.
3. So sánh tenant_ref và key_ref với assignment của service.
4. Kiểm tra các policy/grant change gần thời điểm đầu tiên.
5. Đối chiếu JIT approval, maintenance window và batch job đã đăng ký.
6. Xác định resource_ref đã được truy cập và thời điểm operation thành công.
7. Nếu không có lý do hợp lệ, revoke workload credential/grant và cô lập workload.
8. Đánh giá plaintext có thể đã được trả về caller hoặc ghi vào downstream storage.
9. Xoay credential và key nếu phạm vi compromise yêu cầu; không tự động rotate mọi KEK nếu chưa đánh giá tác động.
10. Lưu evidence, timeline, quyết định và phạm vi ảnh hưởng trong incident record.

Nếu KMS log chỉ ra unwrap thành công nhưng application event thiếu, có thể ứng dụng bị dừng sau khi nhận DEK hoặc pipeline application audit bị gián đoạn. Đây là tín hiệu cần điều tra, không phải bằng chứng rằng không có dữ liệu được giải mã. Phải kiểm tra event gap, process crash, queue và telemetry của workload.

## 14. Retention, truy cập và vận hành audit store

Retention cần dựa trên phân loại dữ liệu, yêu cầu điều tra, hợp đồng và quy định áp dụng. Không nên giữ mọi trường audit vô thời hạn hoặc xóa quá sớm khiến không thể điều tra incident.

Thiết kế vận hành cần xác định:

- Retention riêng cho key usage, admin event, authentication và debug telemetry.
- Quyền truy cập theo vai trò: SOC analyst, auditor, platform operator và data owner.
- Quy trình legal hold khi có incident hoặc yêu cầu điều tra.
- Mã hóa, backup, restore và kiểm tra tính toàn vẹn.
- Quy trình export evidence có người thực hiện, lý do và chain of custody.
- Rà soát định kỳ quyền đọc và quyền quản trị retention.
- Giám sát storage capacity, ingest lag và thay đổi cấu hình collector.

Một analyst có quyền đọc event không mặc nhiên được quyền export toàn bộ log hoặc truy cập mapping định danh tenant. Tách quyền đọc, truy vấn, export và quản trị retention giúp giảm nguy cơ lạm dụng audit data.

## 15. Kế hoạch kiểm thử thiết kế audit

Kiểm thử cần chứng minh cả tính đầy đủ, tính chính xác và khả năng chống mất bằng chứng.

| Nhóm test | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Event completeness | Encrypt/Decrypt/Sign/Unwrap thành công | Có event đúng operation và outcome |
| Denied access | Principal thiếu quyền | Có event DENIED và provider audit tương ứng nếu request tới KMS |
| Identity binding | Người dùng A gọi qua workload B | Event thể hiện cả actor A và workload B |
| Correlation | Một request tạo nhiều KMS call | Nối được event ứng dụng và provider |
| Tenant isolation | Workload thử key tenant khác | Policy từ chối và detection được kích hoạt |
| Secret leakage | Kiểm tra event/log/report | Không có key bytes, plaintext, token hoặc payload nhạy cảm |
| Audit outage | Broker hoặc store không sẵn sàng | Hành vi fail-closed/queue theo policy, không âm thầm bỏ event |
| Duplicate delivery | Relay gửi cùng event nhiều lần | Idempotency không tạo bản ghi sai |
| Tamper attempt | Principal ứng dụng cố sửa/xóa audit | Bị từ chối và tạo cảnh báo |
| Clock drift | Đồng hồ một node lệch | Phát hiện drift, timeline có thể hiệu chỉnh |
| Retention | Event hết hạn theo policy | Xử lý đúng, legal hold được tôn trọng |
| Restore | Khôi phục audit store | Evidence và index có thể truy vấn lại |

Ngoài test tự động, cần diễn tập điều tra một incident giả lập từ application event tới KMS audit, policy decision và resource reference. Nếu analyst không thể nối các nguồn trong thời gian mục tiêu, schema hoặc pipeline cần được cải thiện.

## 16. Các quyết định thiết kế và đánh đổi

| Quyết định | Lựa chọn đề xuất | Đánh đổi |
|---|---|---|
| Nguồn bằng chứng | Kết hợp application audit và KMS/HSM audit | Hai pipeline cần đồng bộ schema và correlation |
| Ghi event | Durable stream hoặc transactional outbox | Tăng thành phần vận hành và latency |
| Khi audit lỗi | Fail-closed với thao tác nhạy cảm; durable queue cho trường hợp được policy cho phép | Availability phụ thuộc phân loại rủi ro |
| Định danh tenant | Reference/pseudonymized ID | Cần mapping có kiểm soát khi điều tra |
| Integrity | Immutable storage, tách quyền, signed batch khi cần | Tăng chi phí và quy trình quản trị |
| Chi tiết event | Metadata đủ để truy vết, không ghi payload | Điều tra có thể cần truy vấn hệ thống nghiệp vụ khác |
| Correlation | ID ứng dụng + provider request ID | Cần mapping khi provider không hỗ trợ custom context |

Không có một cấu hình audit tối ưu cho mọi hệ thống. Quyết định phải dựa trên mức độ nhạy cảm của dữ liệu, criticality của key, yêu cầu pháp lý, độ sẵn sàng của KMS/HSM và khả năng vận hành pipeline.

## 17. Checklist triển khai

Trước khi đưa audit key usage vào production, xác nhận:

- [ ] Đã lập danh mục key, version, owner, tenant và workload sử dụng.
- [ ] Đã phân biệt event key usage, key administration và access governance.
- [ ] Có application audit cho thao tác DEK mà KMS không quan sát được.
- [ ] Có KMS/HSM audit độc lập và được chuyển tới collector riêng.
- [ ] Schema có actor, workload, key/version, operation, outcome, request ID và correlation ID.
- [ ] Actor và tenant lấy từ context đã xác thực/ủy quyền.
- [ ] Event không chứa key material, plaintext, token hoặc payload nhạy cảm.
- [ ] Có durable delivery, idempotency và xử lý audit outage theo risk policy.
- [ ] Audit store tách quyền ghi, đọc, export, retention và xóa.
- [ ] Có detection cho burst, cross-tenant, enumeration, admin change và pipeline gap.
- [ ] Có retention, legal hold, backup, restore và chain of custody.
- [ ] Đã kiểm thử denied access, tamper, duplicate, clock drift và incident investigation.
- [ ] Có playbook revoke credential/grant, cô lập workload và đánh giá key/data impact.

## 18. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hệ quả | Cách phòng tránh |
|---|---|---|
| Chỉ dựa vào application log | App bị xâm phạm có thể sửa hoặc làm mất bằng chứng | Thu thập KMS/HSM audit độc lập |
| Chỉ dựa vào KMS log | Không biết tenant/resource nghiệp vụ hoặc thao tác DEK trong app | Bổ sung application-level event |
| Gộp actor và workload | Không xác định được ai khởi tạo và service nào dùng key | Ghi riêng initiating actor và workload principal |
| Không lưu key version | Khó xác định chính xác version đã được dùng | Ghi key version ID bất biến |
| Không có correlation ID | Không nối được các bước của một request | Tạo và truyền correlation xuyên service |
| Log plaintext hoặc token | Audit store trở thành nguồn rò rỉ | Chỉ ghi metadata tối thiểu |
| Best-effort logging cho mọi thao tác | Có thể mất bằng chứng của thao tác nhạy cảm | Phân loại rủi ro và yêu cầu durable acknowledgment |
| Không giám sát pipeline | Log gap bị hiểu nhầm là không có hoạt động | Heartbeat, sequence và ingest-lag alert |
| Dùng một ngưỡng cảnh báo cho mọi key | False positive hoặc bỏ sót hành vi nghiêm trọng | Baseline theo principal, key, operation và tenant |
| Cùng role dùng key và xóa audit | Attacker có thể che dấu việc sử dụng khóa | Tách quyền và lưu trữ độc lập |

## 19. Nguyên tắc kết luận thiết kế

Thiết kế audit cho key usage cần trả lời được ba câu hỏi: **ai đã yêu cầu**, **workload nào thực sự dùng khóa**, và **thao tác đã có kết quả gì**. Muốn trả lời đầy đủ, phải nối application audit với log độc lập của KMS/HSM, identity provider và policy engine.

Schema event cần ổn định, có key version, operation, outcome, actor, workload, tenant/resource reference và correlation. Pipeline phải có durable delivery, idempotency, integrity protection, retention và cảnh báo khi mất log. Các trường nhạy cảm như key material, DEK, KEK, token và plaintext không được ghi vào audit.

Khi thiết kế được kiểm thử qua success, denial, audit outage, tampering và incident exercise, tổ chức có thể dùng audit evidence để điều tra việc sử dụng khóa, phát hiện lạm dụng quyền và đánh giá phạm vi compromise. Audit không tự ngăn được khóa bị lạm dụng; nó cung cấp khả năng quan sát và bằng chứng để policy, monitoring và incident response hành động đúng lúc.
