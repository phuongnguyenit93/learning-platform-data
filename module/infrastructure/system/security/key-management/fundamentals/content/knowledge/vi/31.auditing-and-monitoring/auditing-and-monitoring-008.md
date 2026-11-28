# Failed key access

**Failed key access** là sự kiện một người dùng, ứng dụng hoặc workload không thể truy cập hoặc sử dụng khóa theo yêu cầu. Nguyên nhân có thể là danh tính không được xác thực, policy từ chối quyền, khóa bị vô hiệu hóa, credential hết hạn, provider gặp lỗi hoặc dịch vụ KMS/HSM không sẵn sàng.

Một lần truy cập khóa thất bại không tự động chứng minh có tấn công. Lỗi có thể xuất phát từ cấu hình sai, rotation chưa đồng bộ, ứng dụng dùng alias cũ hoặc sự cố hạ tầng. Tuy nhiên, chuỗi lần truy cập thất bại, đặc biệt khi nhắm tới nhiều khóa hoặc thao tác nhạy cảm, có thể cho thấy hành vi dò quyền, credential bị lộ hoặc một workload đang bị xâm phạm.

Trong quản lý khóa mật mã, failed key access cần được ghi nhận, phân loại, đối chiếu với hoạt động bình thường và điều tra theo ngữ cảnh. Mục tiêu là phát hiện sớm hành vi bất thường, giảm false positive, khôi phục dịch vụ an toàn và giữ được bằng chứng kiểm toán mà không làm lộ vật liệu khóa.

## 1. Failed key access là gì?

Một lần truy cập khóa có thể gồm nhiều bước: xác thực principal, kiểm tra policy, tìm key theo định danh, kiểm tra trạng thái và thực hiện thao tác mật mã. Thất bại ở bất kỳ bước nào đều có thể tạo ra một sự kiện cần quan sát.

Ví dụ:

- Một service gọi KMS để giải mã nhưng identity của workload không có quyền Decrypt.
- Một kỹ sư dùng credential đã hết hạn để truy cập HSM.
- Ứng dụng yêu cầu alias không tồn tại sau khi key được đổi tên hoặc chuyển phiên bản.
- Khóa đã bị disable, pending deletion hoặc bị thu hồi theo policy.
- Provider không thể kết nối HSM do lỗi mạng hoặc thiết bị đang bảo trì.
- KMS từ chối request do vượt quota hoặc throttling.

Cần phân biệt **key access failure** với **cryptographic operation failure**. Access failure thường xảy ra trước hoặc trong quá trình kiểm tra quyền truy cập khóa. Operation failure có thể xảy ra sau khi quyền đã được chấp nhận, ví dụ ciphertext bị hỏng, tag AEAD không hợp lệ, tham số không đúng hoặc dữ liệu đầu vào không phù hợp. Hai loại lỗi có ý nghĩa bảo mật và hướng điều tra khác nhau.

## 2. Các lớp nguyên nhân thường gặp

| Nhóm nguyên nhân | Ví dụ | Dấu hiệu cần kiểm tra |
|---|---|---|
| Authentication | Token hết hạn, workload identity không hợp lệ, chứng thư client không được chấp nhận | Principal, issuer, audience, thời điểm hết hạn, trạng thái xác thực |
| Authorization | IAM/key policy từ chối Decrypt, Sign hoặc GenerateDataKey | Principal, operation, resource, policy decision và điều kiện context |
| Key state | Khóa bị disable, pending deletion, revoked hoặc chưa active | Trạng thái khóa, thời điểm thay đổi và người thực hiện |
| Key identifier | Alias sai, key ID không tồn tại, dùng nhầm region/tenant | Key ID, alias, version, account/tenant và cấu hình môi trường |
| Credential lifecycle | Secret lease hết hạn, grant bị thu hồi, credential chưa được rotation đồng bộ | Lease ID đã che, TTL, phiên bản credential và lịch rotation |
| Provider/HSM | Provider chưa đăng ký, token HSM bị khóa, partition không sẵn sàng | Provider, thiết bị, partition, session và mã lỗi |
| Infrastructure | Mạng gián đoạn, timeout, quota, throttling hoặc dịch vụ KMS không sẵn sàng | Request ID, latency, retry, service health và giới hạn tài nguyên |
| Cryptographic input | Sai thuật toán, key usage không tương thích, tham số hoặc ciphertext sai | Algorithm, key usage, parameter profile và loại operation |

Một thông báo lỗi đơn lẻ có thể chưa đủ để xác định nguyên nhân. Ví dụ, **UnrecoverableKeyException** khi đọc entry trong KeyStore có thể liên quan tới mật khẩu bảo vệ entry hoặc khả năng khôi phục entry; nó không nhất thiết có nghĩa là policy IAM đã từ chối quyền. Ngược lại, lỗi **AccessDenied** từ KMS thường là quyết định ủy quyền ở dịch vụ đích.

## 3. Phân biệt lỗi bảo mật và lỗi vận hành

Việc phân loại đúng giúp chọn phản ứng phù hợp:

- **Authentication denied:** principal không chứng minh được danh tính hợp lệ. Kiểm tra token, chứng thư, workload identity và nguồn cấp credential.
- **Authorization denied:** principal đã được nhận diện nhưng không có quyền thực hiện operation trên key hoặc trong context hiện tại.
- **Key unavailable:** key không tồn tại, chưa active, đã disable hoặc không khả dụng ở vùng/partition được yêu cầu.
- **Provider/device failure:** ứng dụng không giao tiếp được với provider, HSM hoặc thiết bị bảo vệ khóa.
- **Transient service failure:** timeout, throttling, quota hoặc lỗi dịch vụ tạm thời.
- **Cryptographic input failure:** key đã được truy cập nhưng thao tác thất bại do dữ liệu hoặc tham số không hợp lệ.

Không nên biến mọi lỗi thành một nhãn chung **KEY_ACCESS_FAILED**. Một phân loại đủ chi tiết giúp nhóm bảo mật nhận diện hành vi bị từ chối, còn nhóm vận hành tìm được lỗi cấu hình hoặc hạ tầng. Đồng thời, thông tin trả về cho caller có thể được chuẩn hóa để tránh tiết lộ sự tồn tại của key hoặc policy nội bộ.

## 4. Nguồn telemetry và audit event

Không nên chỉ dựa vào log của ứng dụng. Một hệ thống quản lý khóa thường có nhiều nguồn sự kiện:

- **Application log:** ứng dụng yêu cầu key nào, operation nào và request thất bại ở lớp nào.
- **KMS audit log:** dịch vụ quản lý khóa ghi nhận principal, API operation, resource, decision và request ID.
- **HSM audit log:** thiết bị hoặc partition ghi nhận phiên, user, lệnh mật mã, đăng nhập thất bại và thay đổi cấu hình.
- **Identity provider:** đăng nhập thất bại, token issuance, MFA, federation và thay đổi danh tính.
- **Secret manager:** truy cập secret, lease issue/renew/revoke, credential rotation và lỗi backend.
- **Infrastructure telemetry:** network timeout, service health, throttling, quota, process restart và lỗi provider.

Audit log do KMS/HSM phát ra thường là bằng chứng quan trọng cho việc dịch vụ đích đã nhận và xử lý request như thế nào. Application log bổ sung ngữ cảnh nghiệp vụ, nhưng có thể thiếu sự kiện nếu tiến trình bị dừng đột ngột hoặc lỗi xảy ra trước khi log được ghi.

Nên đối chiếu nhiều nguồn bằng request ID, correlation ID, principal và timestamp. Không giả định mọi hệ thống đều dùng chung một request ID; có thể cần tạo correlation ID ở application rồi ghi kèm ID do KMS/HSM trả về.

## 5. Thiết kế một audit event cho lần truy cập khóa thất bại

Một event có cấu trúc nên trả lời được: ai đã yêu cầu, yêu cầu thao tác gì, trên khóa nào, ở đâu, lúc nào và vì sao bị từ chối.

| Trường | Ý nghĩa |
|---|---|
| event_time | Thời điểm phát sinh theo UTC |
| actor_id | User hoặc workload identity đã được xác thực, nếu xác định được |
| actor_type | Human, service account, workload hoặc system |
| key_id | Định danh khóa hoặc alias theo chính sách log |
| operation | Encrypt, Decrypt, Sign, Verify, GenerateDataKey, Rotate hoặc Export |
| result | Success, Denied, Failed hoặc Throttled |
| failure_category | Authentication, Authorization, KeyState, Provider, Network, Throttling hoặc Input |
| reason_code | Mã lỗi đã chuẩn hóa từ provider hoặc adapter |
| source | Application, KMS, HSM, identity provider hoặc secret manager |
| environment | Development, staging, production hoặc tenant |
| request_id | ID từ dịch vụ đích nếu có |
| correlation_id | ID nối các sự kiện giữa các thành phần |
| policy_context | Policy version, role hoặc điều kiện liên quan, đã loại bỏ dữ liệu nhạy cảm |
| source_context | Workload, host, network zone hoặc thiết bị theo chính sách |

Không ghi secret value, private key, password, access token, plaintext, dữ liệu giải mã hoặc ciphertext nhạy cảm vào event. Không ghi toàn bộ request body nếu nó có thể chứa vật liệu khóa hoặc dữ liệu khách hàng.

Key ID và alias thường không phải vật liệu bí mật, nhưng vẫn có thể tiết lộ cấu trúc hệ thống. Hãy giới hạn quyền đọc log và cân nhắc mã hóa hoặc pseudonymize định danh trong các dashboard có phạm vi rộng. Event cần giữ đủ chi tiết ở kho kiểm toán được bảo vệ để điều tra khi cần.

## 6. Những mẫu bất thường cần phát hiện

Một lần từ chối có thể là lỗi người dùng. Mẫu hành vi lặp lại hoặc lan rộng thường có giá trị phát hiện cao hơn.

| Mẫu | Có thể chỉ ra | Hướng điều tra |
|---|---|---|
| Nhiều lần AccessDenied từ một principal trong thời gian ngắn | Dò quyền hoặc policy cấu hình sai | Kiểm tra identity, key scope, deployment gần nhất và nguồn request |
| Một principal lần lượt thử nhiều key ID | Dò tìm tài nguyên hoặc alias | Kiểm tra danh sách key được yêu cầu và quyền của principal |
| Một key nhận request từ workload chưa từng sử dụng | Credential bị dùng sai nơi hoặc thay đổi kiến trúc | Xác minh deployment, workload identity và network origin |
| Lỗi tập trung sau một lần rotation | Consumer còn dùng credential, alias hoặc key version cũ | Đối chiếu thời điểm rotation và rollout |
| Nhiều principal bị từ chối trên cùng một key | Policy bị thay đổi hoặc key state thay đổi | Kiểm tra change log, key policy và trạng thái key |
| Failed sign/decrypt ngoài giờ hoặc ngoài maintenance window | Hoạt động đặc quyền bất thường | Kiểm tra ticket, JIT grant, approval và danh tính |
| Authentication failure tăng đồng thời ở nhiều dịch vụ | Credential hoặc identity provider có sự cố | Kiểm tra issuer, token, federation và hệ thống cấp credential |
| Lỗi provider/HSM tăng trên nhiều ứng dụng | Sự cố thiết bị hoặc hạ tầng | Kiểm tra partition, session, network và service health |
| Một principal bị từ chối rồi nhanh chóng thành công với quyền cao hơn | Có thể là privilege escalation hoặc policy thay đổi | Nối các sự kiện grant, policy change và operation thành công |

Không nên đặt cảnh báo chỉ dựa trên số lượng thô. Một batch job hợp lệ có thể tạo nhiều lần truy cập, còn một lần Decrypt bất thường vào key trọng yếu có thể cần điều tra ngay. Cần tính đến độ nhạy của key, operation, principal và bối cảnh thay đổi.

## 7. Baseline và ngưỡng cảnh báo

Baseline mô tả hành vi truy cập khóa bình thường của từng workload hoặc nhóm người dùng. Có thể xây dựng từ:

- Key và operation mà principal thường sử dụng.
- Tần suất và thời gian truy cập theo lịch chạy.
- Môi trường, tenant, region và network zone.
- Tỷ lệ thành công/thất bại trong khoảng thời gian.
- Số lượng key khác nhau mà một principal truy cập.
- Mối liên hệ giữa request và deployment, incident hoặc maintenance window.

Ví dụ, một service thanh toán thường gọi Decrypt trên một key trong production với tần suất ổn định. Nếu cùng identity đột nhiên thử nhiều key thuộc môi trường khác, đó là thay đổi đáng chú ý. Một kỹ sư chỉ truy cập key khi có ticket và JIT grant; request ngoài cửa sổ được phê duyệt cần được đánh giá.

Ngưỡng cần được điều chỉnh theo quy mô và mức rủi ro. Có thể dùng cửa sổ thời gian, tỷ lệ lỗi, số principal hoặc số key khác nhau, nhưng phải tránh ngưỡng quá nhạy gây alert fatigue. Với key trọng yếu, một sự kiện bị từ chối ở operation nguy hiểm có thể tạo cảnh báo ngay cả khi chưa đạt ngưỡng lặp lại.

## 8. Thiết kế cảnh báo theo mức độ rủi ro

| Mức | Ví dụ | Phản ứng đề xuất |
|---|---|---|
| Informational | Một lần lỗi alias trong môi trường thử nghiệm | Ghi nhận, không cần paging |
| Low | Một workload bị từ chối do token hết hạn, có rollout tương ứng | Tạo sự kiện vận hành, theo dõi xu hướng |
| Medium | Một principal lặp lại lỗi authorization trên key production | Cảnh báo nhóm sở hữu dịch vụ và kiểm tra policy |
| High | Principal lạ thử nhiều key hoặc thao tác nhạy cảm ngoài giờ | Điều tra bảo mật, xem xét revoke credential hoặc grant |
| Critical | Nhiều dấu hiệu dò key trọng yếu, thay đổi policy trái phép hoặc failed access đi kèm hoạt động đặc quyền đáng ngờ | Kích hoạt incident response, cô lập principal và bảo vệ key theo playbook |

Một cảnh báo tốt cần chứa principal, key ID đã được bảo vệ theo policy, operation, failure category, số lần, khoảng thời gian, nguồn request, correlation ID và đường dẫn tới audit evidence. Không đưa secret vào nội dung cảnh báo.

Nên nhóm các sự kiện tương tự để giảm trùng lặp, nhưng không gộp mất thông tin về key hoặc principal khác nhau. Suppression phải có thời hạn và có audit; không tắt cảnh báo vĩnh viễn chỉ vì một workload thường xuyên phát sinh lỗi.

## 9. Quy trình điều tra một lần truy cập khóa thất bại

Khi nhận cảnh báo, người điều tra có thể đi theo trình tự:

1. **Xác nhận sự kiện:** kiểm tra timestamp, nguồn log, request ID và kết quả từ KMS/HSM.
2. **Xác định principal:** user hoặc workload nào đã gửi request; identity có hợp lệ và đang hoạt động không?
3. **Xác định mục tiêu:** key ID, operation, môi trường và tenant có đúng với công việc không?
4. **Kiểm tra policy:** quyền có bị từ chối do key policy, IAM, grant, condition, boundary hoặc JIT expiration không?
5. **Kiểm tra trạng thái khóa:** key có active, enabled và được phép dùng cho operation đó không?
6. **Kiểm tra thay đổi gần đây:** rotation, policy update, deploy, certificate renewal, secret lease expiry hoặc thay đổi provider.
7. **Đối chiếu hành vi:** principal có truy cập key này trước đây không; có thử nhiều key hoặc operation khác không?
8. **Đánh giá mức độ:** lỗi cấu hình, lỗi vận hành hay dấu hiệu credential compromise.
9. **Hành động:** sửa cấu hình nếu hợp lệ; nếu nghi ngờ bị xâm phạm, revoke credential/grant, cô lập workload và bảo vệ key theo playbook.
10. **Lưu kết quả:** ghi nguyên nhân gốc, bằng chứng, phạm vi ảnh hưởng và hành động khắc phục.

Không cấp thêm quyền rộng chỉ để làm cho lỗi biến mất. Nếu lỗi do thiếu quyền, xác định operation tối thiểu cần thiết, principal đúng và resource cụ thể trước khi cập nhật policy.

## 10. Xử lý lỗi trong ứng dụng Java

Ứng dụng Java nên ghi lại kết quả truy cập ở ranh giới adapter hoặc service gọi KeyStore/KMS. Event cần chứa metadata an toàn, còn exception phải được phân loại bằng mã lỗi ổn định thay vì ghi toàn bộ nội dung có thể chứa dữ liệu nhạy cảm.

Ví dụ dưới đây minh họa một service bao quanh thao tác KMS. **KeyAccessException** là exception của adapter ứng dụng; phần tích hợp thật cần ánh xạ lỗi từ SDK/provider cụ thể sang các nhóm lỗi chuẩn hóa.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Arrays;

public final class AuditedKeyService {
    public enum Operation {
        SIGN,
        DECRYPT
    }

    public enum FailureCategory {
        AUTHENTICATION,
        AUTHORIZATION,
        KEY_STATE,
        PROVIDER,
        THROTTLED,
        NETWORK,
        UNKNOWN
    }

    public record KeyAccessEvent(
            Instant eventTime,
            String actorId,
            String keyId,
            Operation operation,
            String result,
            FailureCategory failureCategory,
            String reasonCode,
            String correlationId) {
    }

    public interface AuditSink {
        void publish(KeyAccessEvent event);
    }

    public interface KeyBackend {
        byte[] decrypt(String keyId, byte[] ciphertext)
                throws KeyAccessException;
    }

    public static final class KeyAccessException extends Exception {
        private final FailureCategory category;
        private final String reasonCode;

        public KeyAccessException(
                FailureCategory category,
                String reasonCode) {
            super(reasonCode);
            this.category = category;
            this.reasonCode = reasonCode;
        }

        public FailureCategory category() {
            return category;
        }

        public String reasonCode() {
            return reasonCode;
        }
    }

    private final KeyBackend backend;
    private final AuditSink audit;
    private final Clock clock;

    public AuditedKeyService(
            KeyBackend backend,
            AuditSink audit,
            Clock clock) {
        this.backend = backend;
        this.audit = audit;
        this.clock = clock;
    }

    public byte[] decrypt(
            String actorId,
            String keyId,
            String correlationId,
            byte[] ciphertext) throws KeyAccessException {

        try {
            byte[] plaintext = backend.decrypt(keyId, ciphertext);

            try {
                audit.publish(new KeyAccessEvent(
                    clock.instant(),
                    actorId,
                    keyId,
                    Operation.DECRYPT,
                    "SUCCESS",
                    null,
                    null,
                    correlationId
                ));
            } catch (RuntimeException auditFailure) {
                Arrays.fill(plaintext, (byte) 0);
                throw new IllegalStateException(
                    "Không thể ghi audit cho thao tác giải mã thành công",
                    auditFailure
                );
            }

            return plaintext;
        } catch (KeyAccessException ex) {
            try {
                audit.publish(new KeyAccessEvent(
                    clock.instant(),
                    actorId,
                    keyId,
                    Operation.DECRYPT,
                    "FAILED",
                    ex.category(),
                    ex.reasonCode(),
                    correlationId
                ));
            } catch (RuntimeException auditFailure) {
                ex.addSuppressed(auditFailure);
            }

            throw ex;
        }
    }
}
~~~

Ví dụ chỉ ghi nhận metadata của thao tác. Nó không ghi ciphertext, plaintext, khóa hoặc credential. **actorId** và **correlationId** phải đến từ authentication/context đã được tin cậy, không lấy trực tiếp từ trường do client tự khai.

**AuditSink** trong hệ thống thật cần chuyển event tới nơi lưu trữ có kiểm soát truy cập, chống sửa đổi và có cơ chế chịu lỗi. Cần định nghĩa rõ hành vi khi audit không ghi được: với thao tác nhạy cảm, có thể phải từ chối tiếp tục nếu không bảo đảm được bằng chứng; với một số hệ thống khác, có thể dùng durable queue/outbox và cảnh báo ngay. Không nên âm thầm bỏ qua lỗi audit.

Adapter KMS/HSM cần ánh xạ exception cụ thể của SDK/provider thành **FailureCategory** và **reasonCode** ổn định. Không phân loại chỉ bằng cách so khớp chuỗi thông báo exception vì thông điệp có thể thay đổi theo phiên bản hoặc chứa dữ liệu không nên log.

## 11. Retry và xử lý lỗi có kiểm soát

Không phải mọi failed key access đều nên retry:

- **Authorization denied:** không retry liên tục. Kiểm tra policy, principal và scope; retry không làm quyền tự xuất hiện.
- **Authentication failed:** làm mới credential qua quy trình xác thực hợp lệ; không lặp vô hạn với cùng token hoặc password.
- **Key disabled hoặc revoked:** dừng operation và xác minh change/incident. Không tự động chọn key khác nếu điều đó làm thay đổi ngữ nghĩa bảo mật.
- **Throttling hoặc transient network error:** có thể retry với exponential backoff, jitter và giới hạn số lần.
- **Provider/HSM unavailable:** dùng health check, circuit breaker và quy trình failover đã được phê duyệt.
- **Invalid cryptographic input:** kiểm tra thuật toán, tham số và dữ liệu; retry cùng đầu vào thường không có ích.

Đặc biệt, không fallback sang key khác hoặc credential tĩnh có quyền rộng chỉ để request thành công. Hành vi fallback phải được định nghĩa trong kiến trúc, giới hạn quyền và ghi audit như một quyết định riêng.

## 12. Lưu trữ và bảo vệ audit log

Audit log về key access có giá trị điều tra cao nên cần được bảo vệ như một tài sản an ninh:

- Gửi log tới kho tập trung có quyền truy cập tách biệt với workload tạo log.
- Dùng lưu trữ append-only hoặc cơ chế chống sửa đổi khi yêu cầu kiểm toán đòi hỏi.
- Đồng bộ thời gian giữa ứng dụng, identity provider, KMS và HSM.
- Giới hạn quyền đọc, xuất và xóa log; ghi audit cả thao tác truy cập log.
- Mã hóa log khi truyền và khi lưu.
- Đặt retention theo yêu cầu pháp lý, hợp đồng và chính sách nội bộ.
- Giám sát khoảng trống log, độ trễ ingest, lỗi forwarder và thay đổi cấu hình logging.
- Không để người quản trị key có thể âm thầm xóa bằng chứng về thao tác của chính họ.

Nếu log chỉ tồn tại trên máy chủ ứng dụng, kẻ tấn công kiểm soát máy chủ có thể sửa hoặc xóa bằng chứng. Vì vậy, nên chuyển log sớm tới hệ thống độc lập và kiểm tra tính toàn vẹn của pipeline.

## 13. Liên hệ với vòng đời và rotation của khóa

Failed key access thường tăng trong những giai đoạn thay đổi vòng đời khóa:

- Sau rotation, consumer có thể vẫn dùng alias hoặc key version cũ.
- Khi key bị disable, các request mới có thể bị từ chối.
- Khi certificate hoặc workload credential hết hạn, KMS/HSM có thể từ chối principal.
- Khi grant JIT hết TTL, thao tác tiếp theo không còn được phép.
- Khi key chuyển trạng thái pending deletion, policy có thể chặn một số thao tác.

Nên gắn các sự kiện audit với change record và key lifecycle event. Ví dụ, một loạt lỗi Decrypt ngay sau rotation có thể là dấu hiệu ứng dụng chưa cập nhật key ID hoặc envelope metadata. Cùng mẫu đó, nếu xuất hiện từ workload lạ và nhắm tới nhiều key, có thể là dấu hiệu dò quyền.

Khi xoay vòng, hãy theo dõi tỷ lệ thành công/thất bại theo key version và consumer. Khi thu hồi hoặc disable key, xác định trước workload nào dự kiến bị ảnh hưởng và tạo cảnh báo riêng để phân biệt hành động quản trị hợp lệ với thay đổi ngoài kế hoạch.

## 14. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hệ quả | Cách phòng tránh |
|---|---|---|
| Coi mọi failure là tấn công | False positive, alert fatigue và bỏ sót sự cố thật | Phân loại nguyên nhân và đối chiếu ngữ cảnh |
| Gộp mọi lỗi vào một mã chung | Khó điều tra và retry sai cách | Chuẩn hóa failure category và reason code |
| Chỉ ghi log ở ứng dụng | Mất sự kiện nếu process crash hoặc request chưa tới app logger | Thu thập audit từ KMS/HSM và identity provider |
| Log secret hoặc plaintext để debug | Audit log trở thành nguồn rò rỉ | Chỉ ghi metadata và mã lỗi đã chuẩn hóa |
| Retry authorization denied vô hạn | Tăng tải, che khuất dấu hiệu dò quyền | Không retry lỗi policy; cảnh báo theo mẫu |
| Tự fallback sang key khác | Có thể giải mã hoặc ký bằng sai key | Dừng an toàn và yêu cầu quyết định theo policy |
| Không đồng bộ thời gian | Timeline điều tra sai lệch | Đồng bộ UTC và giám sát clock drift |
| Không nối event giữa các hệ thống | Không dựng được chuỗi nguyên nhân | Dùng correlation ID và request ID |
| Không giám sát log pipeline | Sự kiện bảo mật có thể bị mất mà không ai biết | Alert khi ingest delay hoặc log gap tăng |
| Không cập nhật baseline sau rotation | Cảnh báo sai hoặc bỏ sót consumer dùng key cũ | Liên kết monitoring với change và lifecycle event |

## 15. Nguyên tắc triển khai an toàn

- Thu thập failed access từ ứng dụng, identity provider, KMS, HSM và secret manager.
- Phân biệt authentication, authorization, key state, provider, infrastructure và cryptographic input failure.
- Ghi event có cấu trúc với principal, key ID, operation, timestamp, reason code và correlation ID.
- Không ghi key material, secret, token, plaintext hoặc dữ liệu nhạy cảm vào log.
- Dùng baseline theo principal, key, operation, môi trường và lịch công việc.
- Cảnh báo theo rủi ro và mẫu hành vi, không chỉ theo số lượng lỗi.
- Không retry authorization denied hoặc key revoked; chỉ retry lỗi tạm thời theo backoff và giới hạn.
- Không fallback sang key hoặc credential khác ngoài policy đã phê duyệt.
- Bảo vệ audit log bằng kho tập trung, quyền đọc hạn chế, đồng bộ thời gian và cơ chế chống sửa đổi.
- Liên kết failed access với rotation, JIT grant, policy change và trạng thái key để giảm false positive.
- Duy trì playbook điều tra, thu hồi credential, cô lập workload và khôi phục dịch vụ.
- Kiểm thử cả trường hợp bị từ chối hợp lệ, dò quyền, provider outage và log pipeline bị gián đoạn.

Failed key access là tín hiệu cần được hiểu trong ngữ cảnh của danh tính, key, operation và trạng thái hệ thống. Khi phân loại lỗi chính xác, thu thập audit từ đúng nguồn, phát hiện mẫu bất thường và phản ứng theo mức rủi ro, tổ chức có thể phân biệt lỗi vận hành với hành vi đáng ngờ, bảo vệ khóa tốt hơn và giữ được bằng chứng cần thiết cho kiểm toán.
