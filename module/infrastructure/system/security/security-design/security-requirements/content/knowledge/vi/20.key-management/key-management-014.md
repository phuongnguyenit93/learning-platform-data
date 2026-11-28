# Audit sử dụng key

## 1. Audit phải trả lời được câu hỏi nào?

Audit sử dụng key là việc tạo, bảo vệ và khai thác bằng chứng về những thao tác dùng khóa mật mã và những thay đổi làm ảnh hưởng quyền sử dụng khóa.

Một audit trail hữu ích cần giúp trả lời:

- Workload hoặc chủ thể nào đã yêu cầu thao tác?
- Khóa hay phiên bản nào được yêu cầu và thực tế được sử dụng?
- Thao tác là encrypt, decrypt, sign, verify, wrap, unwrap hay MAC?
- Quyết định phân quyền là gì?
- Key service đã thực hiện thành công, từ chối, thất bại hay chưa xác định kết quả?
- Thao tác gắn với request hoặc mục đích nghiệp vụ nào?
- Có dấu hiệu dùng sai phạm vi, dùng key cũ hoặc vượt ngân sách không?
- Có khoảng trống nào trong bằng chứng cần được công bố?

Mục tiêu không phải ghi mọi byte của request. Mục tiêu là đủ bằng chứng để kiểm tra chính sách, phát hiện bất thường và điều tra, đồng thời không biến log thành một kho bí mật mới.

### 1.1. Vì sao đây là yêu cầu bảo mật?

Một key có thể được bảo vệ tốt khỏi export nhưng vẫn bị một workload có quyền decrypt lạm dụng.

Nếu không có bằng chứng sử dụng:

- Không biết dữ liệu nào có thể đã bị truy cập.
- Không xác định được identity đang dùng key ngoài mục đích.
- Không đánh giá được ảnh hưởng của một grant quá rộng.
- Không kiểm chứng rotation hoặc revocation đã có hiệu lực.
- Không phát hiện một đường gọi bỏ qua lớp kiểm soát ứng dụng.

Vì vậy, quản lý quyền và audit phải phối hợp. Audit không thay thế việc chặn thao tác trái phép, nhưng giúp chứng minh kiểm soát đã vận hành và xác định sự cố khi giả định tin cậy bị phá vỡ.

### 1.2. Audit khác debug log

| Loại dữ liệu | Mục đích | Đặc tính cần ưu tiên |
|---|---|---|
| Debug log | Chẩn đoán lỗi phát triển | Chi tiết phù hợp môi trường, tránh lộ bí mật |
| Metric | Quan sát xu hướng | Tổng hợp, độ trễ và cardinality có kiểm soát |
| Trace | Liên kết luồng xử lý | Correlation giữa các thành phần |
| Audit event | Bằng chứng hành động và quyết định | Danh tính, kết quả, toàn vẹn, phạm vi và retention rõ |

Một dòng “decrypt called” không có actor, key reference và kết quả không đủ làm audit event.

Ngược lại, một audit event không nên chứa raw key hoặc plaintext chỉ để hỗ trợ debug.

## 2. Xác định phạm vi operation và nguồn bằng chứng

### 2.1. Sử dụng khóa và quản trị khóa

Cần phân biệt hai nhóm:

| Nhóm | Ví dụ |
|---|---|
| Data-plane operation | Encrypt, decrypt, sign, verify, generate/verify MAC, wrap/unwrap |
| Control-plane operation | Tạo/import key, đổi policy, cấp grant, đổi alias, disable, revoke, rotate, hủy |

Một thay đổi grant có thể là nguyên nhân khiến hàng nghìn lần decrypt sau đó được phép. Vì vậy, điều tra sử dụng key cần liên kết cả hai nhóm.

Không chỉ ghi thao tác thành công. Những lần bị từ chối hoặc lỗi có thể cho thấy thử dùng sai phạm vi, cấu hình sai hoặc một sự cố đang bắt đầu.

### 2.2. Nguồn ứng dụng và nguồn key service

Một luồng có thể gồm:

```text
Request nghiệp vụ
    → ứng dụng kiểm tra quyền
    → gọi KMS/HSM hoặc primitive local
    → sử dụng kết quả
    → trả response
```

Có ít nhất ba góc nhìn:

- Ứng dụng biết mục đích và đối tượng nghiệp vụ.
- Key service biết API operation và identity gọi nó.
- Hạ tầng audit biết thời điểm nhận, lưu và phân phối event.

Không nguồn nào tự có toàn bộ ngữ cảnh.

Ví dụ, [AWS KMS tích hợp với CloudTrail](https://docs.aws.amazon.com/kms/latest/developerguide/logging-using-cloudtrail.html) để ghi nhận các API dùng và quản trị key. Cấu hình trail vẫn có thể loại trừ KMS events; một số trường nhạy cảm được bỏ khỏi log và phạm vi ghi nhận lỗi có điều kiện theo loại lời gọi.

Hệ quả là không nên suy ra “đã có KMS” đồng nghĩa mọi audit cần thiết đã tự được lưu đúng nơi và đủ retention.

### 2.3. Operation ở provider không phải operation nghiệp vụ

Một request nghiệp vụ có thể tạo:

- Không có KMS call vì dùng cache.
- Một call unwrap rồi nhiều operation local.
- Nhiều call do nhiều field hoặc chunk.
- Nhiều attempt do retry.
- Một call bị từ chối trước khi có thao tác mật mã.
- Một call thành công nhưng nghiệp vụ sau đó thất bại.

Không dùng công thức “mỗi lượt đọc tài liệu tương ứng một Decrypt log” nếu kiến trúc không bảo đảm điều đó.

Muốn audit từng lượt sử dụng dữ liệu ở ứng dụng, cần event tại lớp ứng dụng phù hợp, không chỉ đếm log KMS.

### 2.4. Phân loại event theo hợp đồng nền tảng

Các dịch vụ có mô hình audit khác nhau. [Cloud KMS audit logging](https://docs.cloud.google.com/kms/docs/audit-logging) phân loại API theo permission type và nhóm audit, đồng thời có những operation dài tạo event bắt đầu và kết thúc.

Khi triển khai, phải đối chiếu đúng API, loại log, cấu hình thu thập và cấu trúc event. Không ánh xạ mọi mục từ nhà cung cấp vào một trường “key used” rồi làm mất trạng thái quan trọng.

## 3. Mô hình event: ai, làm gì, bằng khóa nào và kết quả ra sao?

### 3.1. Trường dữ liệu cốt lõi

Một schema ứng dụng có thể gồm:

| Nhóm | Trường minh họa |
|---|---|
| Định danh event | eventId, schemaVersion, eventType |
| Thời gian | occurredAt, receivedAt |
| Liên kết | operationId, requestId, providerRequestId |
| Chủ thể | workloadIdentity, actorReference, delegatedSubject nếu đã xác minh |
| Tài nguyên | keyReference, keyVersion nếu xác định được, environment |
| Thao tác | operation, purpose |
| Quyết định | policyDecision, policyVersion, reasonCode |
| Kết quả | outcome, errorCategory |
| Phạm vi dữ liệu | tenant/object reference đã được phân loại |
| Nguồn | producer, region hoặc zone cần thiết |

Không phải mọi event đều có mọi trường. Schema cần quy định field bắt buộc, field không áp dụng và mức tin cậy của từng trường.

### 3.2. Ví dụ event tổng hợp

```json
{
  "schemaVersion": 1,
  "eventId": "event-example-014",
  "operationId": "operation-example-014",
  "eventType": "KEY_OPERATION_RESULT",
  "occurredAt": "2026-01-01T10:00:00Z",
  "producer": "document-service",
  "workloadIdentity": "workload-document-production",
  "keyReference": "managed-key-reference",
  "keyVersion": "immutable-version-reference",
  "operation": "DECRYPT",
  "purpose": "DOCUMENT_READ",
  "scopeReference": "opaque-scope-reference",
  "policyDecision": "ALLOW",
  "policyVersion": "policy-version-18",
  "outcome": "SUCCEEDED",
  "providerRequestId": "provider-request-reference"
}
```

Đây là ví dụ schema, không phải log thực tế của một nhà cung cấp.

Tên và giá trị reference không cần chứa tên người, email, số hồ sơ hoặc nội dung tài liệu.

### 3.3. Danh tính phải có nguồn đáng tin

Nếu actorReference lấy nguyên từ JSON request, audit chỉ ghi lại một lời khai, không chứng minh ai đã thao tác.

Cần phân biệt:

- Workload thực sự xác thực với key service.
- Người dùng đã xác thực gọi ứng dụng.
- Chủ thể được ủy quyền.
- Một account hoặc integration được ánh xạ theo policy.
- Metadata do caller tự cung cấp chưa được xác minh.

Một role dùng chung ở KMS có thể không cho biết trực tiếp người dùng cuối. Correlation với ứng dụng cần giữ được nguồn và ranh giới tin cậy của dữ liệu.

### 3.4. Requested key và actual key

Alias hoặc logical key có thể được resolve sang một version. Nếu nền tảng cung cấp actual version, audit nên giữ đủ thông tin để xác định phiên bản thực tế.

Nếu nền tảng không công bố material version trong loại operation đó, phải ghi đúng giới hạn. Không tự ghi “latest” vào trường actualVersion rồi coi đó là sự thật lịch sử.

Có thể giữ:

```text
requestedReference
resolvedReference
providerReportedReference
```

theo schema phù hợp, thay vì trộn ba ý nghĩa vào một chuỗi.

## 4. Phân biệt attempt, decision và kết quả thực thi

### 4.1. Một event thành công cần nói rõ thành công ở đâu

Những mốc khác nhau:

```text
Yêu cầu được nhận
    → quyền được cho phép
    → key operation được gửi
    → provider trả kết quả
    → nghiệp vụ commit
    → response được gửi
```

policyDecision=ALLOW không có nghĩa key operation đã thành công.

Một operation sign thành công cũng không có nghĩa chữ ký đã được phát hành cho client. Ngược lại, response bị mất không có nghĩa provider chưa tạo chữ ký.

### 4.2. Những kết quả cần phân biệt

| Kết quả | Ý nghĩa |
|---|---|
| DENIED | Một điểm kiểm soát đã từ chối |
| SUCCEEDED | Nguồn có thẩm quyền cho mốc đó xác nhận thành công |
| FAILED | Có kết quả thất bại xác định cho mốc đó |
| UNKNOWN | Chưa xác định được kết quả thực tế |
| STARTED hoặc PENDING | Chưa có kết luận cuối |

Không ghi timeout của client thành “provider không thực hiện”. Request có thể đã được xử lý trước khi kết nối bị gián đoạn.

Nếu không có kết quả chắc chắn, UNKNOWN là thông tin quan trọng để đối chiếu và phục hồi.

### 4.3. Correlation không đồng nghĩa exactly once

Một operationId có thể liên kết nhiều attempt. Mỗi event hoặc attempt cần định danh phù hợp để deduplicate và tái dựng lịch sử.

Hệ thống audit thường cần chịu được event lặp hoặc đến muộn. Điều cần bảo đảm là không mất ý nghĩa, không đếm trùng như một thao tác khác và không tự tuyên bố exactly-once nếu kiến trúc không cung cấp điều đó.

### 4.4. Không dùng log ứng dụng như xác nhận của provider

Một workload bị xâm nhập có thể phát event “không dùng key” hoặc “đã bị từ chối” trong khi vẫn gọi key service.

Bằng chứng từ một nguồn độc lập như provider giúp đối chiếu, trong phạm vi tin cậy của nguồn đó.

Điều tra cần giữ nhãn nguồn. Một event do ứng dụng tạo không nên được trình bày như một bản ghi đã được provider xác nhận chỉ vì nó chứa providerRequestId do producer ghi.

## 5. Những dữ liệu không được ghi

### 5.1. Không đưa bí mật vào audit

Theo mặc định, không ghi:

- Raw symmetric key.
- Private key.
- Plaintext data key.
- Credential hoặc access token.
- Plaintext nghiệp vụ.
- Passphrase hoặc password.
- Buffer bộ nhớ có thể chứa material.
- Toàn bộ request/response mật mã.
- Nội dung exception chưa được phân loại có thể chứa các dữ liệu trên.

Ciphertext và authentication tag cũng cần được phân loại. Không mặc định chúng có thể lưu rộng rãi chỉ vì không phải plaintext.

### 5.2. Metadata có thể là dữ liệu nhạy cảm

Một key reference, tenantId, objectId hoặc purpose có thể tiết lộ quan hệ nghiệp vụ.

Cần quyết định:

- Reference nào được ghi trực tiếp.
- Ai được tra ngược opaque reference.
- Những trường nào cần masking hoặc giảm chi tiết.
- Có thể tổng hợp gì ở metric.
- Những trường nào bị cấm ở nguồn.

Hash một định danh ít entropy không tự làm nó ẩn danh. Bên biết tập giá trị có thể thử đối chiếu. Không dùng việc “đã hash” làm căn cứ duy nhất để hạ mức bảo vệ.

### 5.3. Encryption context không mặc định là bí mật

Một số dịch vụ cho phép truyền context vào operation. Context đó có thể xuất hiện trong log bên provider.

Ví dụ, [AWS KMS encryption context](https://docs.aws.amazon.com/kms/latest/developerguide/encrypt_context.html) không được mã hóa và được ghi trong CloudTrail; tài liệu yêu cầu không đặt thông tin nhạy cảm trong đó.

Vì vậy, muốn audit dễ đối chiếu không có nghĩa được đưa email, số hồ sơ hoặc toàn bộ path nhạy cảm vào context.

Nếu thông tin đã được gửi tới log provider, việc che nó ở collector phía sau không xóa bản ghi gốc. Tối thiểu hóa phải bắt đầu tại nơi tạo context.

### 5.4. Structured logging và giới hạn trường

Dữ liệu không tin cậy có thể chứa ký tự điều khiển hoặc chuỗi rất dài. Audit serializer cần:

- Encoding có cấu trúc.
- Giới hạn độ dài từng field.
- Schema/version xác định.
- Danh sách reason code hữu hạn.
- Xử lý field không hợp lệ theo policy.
- Không nối raw input vào một dòng log tùy tiện.

Không cho phép caller chọn eventType, outcome hoặc workloadIdentity để giả một sự kiện đáng tin.

## 6. Ví dụ Java: event không chứa material

Ví dụ Java 17 trở lên sau mô tả một loại event có giới hạn. Nó không cài đặt log storage hoặc chứng minh nguồn dữ liệu đáng tin.

```java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record KeyUseAuditEvent(
        UUID eventId,
        UUID operationId,
        Instant occurredAt,
        String workloadReference,
        String keyReference,
        Operation operation,
        Outcome outcome,
        Reason reason
) {
    public enum Operation {
        ENCRYPT,
        DECRYPT,
        SIGN,
        VERIFY,
        GENERATE_MAC,
        VERIFY_MAC,
        WRAP,
        UNWRAP
    }

    public enum Outcome {
        STARTED,
        DENIED,
        SUCCEEDED,
        FAILED,
        UNKNOWN
    }

    public enum Reason {
        NONE,
        ACCESS_DENIED,
        KEY_NOT_ACTIVE,
        INVALID_AUTHENTICATION_TAG,
        PROVIDER_UNAVAILABLE,
        RESULT_NOT_CONFIRMED
    }

    public KeyUseAuditEvent {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(operationId);
        Objects.requireNonNull(occurredAt);
        Objects.requireNonNull(operation);
        Objects.requireNonNull(outcome);
        Objects.requireNonNull(reason);

        workloadReference = requireReference(
                workloadReference,
                "workloadReference"
        );
        keyReference = requireReference(
                keyReference,
                "keyReference"
        );
    }

    private static String requireReference(
            String value,
            String fieldName
    ) {
        Objects.requireNonNull(value, fieldName);

        if (value.isBlank()
                || value.length() > 256
                || value.chars().anyMatch(Character::isISOControl)) {
            throw new IllegalArgumentException(
                    "Invalid audit reference"
            );
        }

        return value;
    }
}
```

### 6.1. Những điểm của ví dụ

- Không có field SecretKey, private key, plaintext hoặc raw request.
- Operation, outcome và reason là giá trị hữu hạn.
- Reference có giới hạn và không chứa ký tự điều khiển.
- Event có định danh riêng và operationId để liên kết.
- Thời gian là dữ liệu có cấu trúc, không phải một chuỗi tự do.

Schema thật có thể cần thêm stage, actor, version hoặc provider request ID. Quy tắc tổ hợp giữa stage/outcome/reason cũng cần được kiểm tra ở lớp producer hoặc validator tương ứng.

### 6.2. Event hợp lệ về schema chưa phải bằng chứng hợp lệ

Constructor không xác minh:

- Workload đã được xác thực.
- Key reference nằm trong phạm vi.
- Provider đã thực hiện operation.
- Đồng hồ producer đúng.
- Event được lưu bền vững.
- Không có event bị bỏ trước khi tạo object.

Những bảo đảm đó thuộc pipeline và nguồn có thẩm quyền.

Không dùng record này để cho người dùng submit một outcome SUCCEEDED rồi nhập trực tiếp vào audit trail như sự kiện của hệ thống.

### 6.3. Logger không nên tự gọi mật mã đệ quy

Nếu logger cần dùng key service cho mọi event trong khi đang audit chính key service đó, có thể tạo vòng lặp hoặc phụ thuộc khó phục hồi.

Thiết kế cần tách thao tác bảo vệ log, cơ chế credential và policy xử lý lỗi phù hợp. Không thêm encryption hoặc MAC vào logger một cách máy móc mà chưa xét dependency và khóa dùng để bảo vệ audit.

## 7. Độ đầy đủ: ghi đủ không đồng nghĩa ghi được mọi thứ

### 7.1. Lập coverage matrix

Ví dụ:

| Tình huống | Nguồn audit cần có |
|---|---|
| Ứng dụng từ chối trước KMS | Application authorization event |
| KMS từ chối operation | Provider event và correlation nếu có |
| KMS thực hiện thành công | Provider result và application result theo phạm vi |
| Primitive chạy bằng key local | Event tại ranh giới local được quản lý |
| DEK cache dùng lại | Event ứng dụng hoặc metric theo hợp đồng, không kỳ vọng KMS call mới |
| Đổi key policy/grant | Control-plane audit |
| Đổi cấu hình audit | Audit cấu hình và cảnh báo từ nguồn phù hợp |

Không nên có một ô “do bên khác ghi” mà không xác định ai, loại event và nơi lưu.

### 7.2. Sampling cần được quyết định rõ

Nếu yêu cầu là audit đầy đủ một operation nhạy cảm, sampling 1% không đáp ứng dù dashboard vẫn có dữ liệu.

Có thể dùng sampling cho trace hoặc metric không yêu cầu bằng chứng từng operation. Nhưng audit event và dữ liệu tổng hợp cần được phân biệt.

Nếu một loại operation chỉ được ghi ở mức tổng hợp theo quyết định rủi ro, phải công bố giới hạn điều tra. Không trình bày nó như full per-operation audit.

### 7.3. Coverage của provider có điều kiện

Cần xác minh:

- Loại log được bật.
- Account/project, vùng và key trong phạm vi.
- Event selector và exclusion.
- Sink hoặc routing.
- Quyền ghi vào nơi lưu.
- Retention.
- Những lỗi có thể không xuất hiện ở nguồn dự kiến.
- Trạng thái migration schema của provider.

Một cấu hình log ở môi trường thử không chứng minh production có cùng coverage.

### 7.4. Reconciliation

Có thể đối chiếu:

- OperationId giữa ứng dụng và provider request ID.
- Số attempt, kết quả và retry theo mốc.
- Những event STARTED chưa có kết quả.
- Workload/key có ở provider nhưng không có ngữ cảnh ứng dụng.
- Event ứng dụng khai thành công nhưng không có bằng chứng mong đợi.
- Thời gian không có dữ liệu vượt ngưỡng dự kiến.

Không đòi count bằng nhau khi kiến trúc có cache hoặc nhiều call cho một request. Reconciliation phải dựa trên mapping đã mô tả, không chỉ một phép trừ tổng số.

## 8. Độ tin cậy và lỗi pipeline

### 8.1. Các bước có thể mất dữ liệu

```text
Producer
    → buffer
    → transport
    → collector
    → storage
    → index
    → truy vấn/cảnh báo
```

Một event có thể đã lưu nhưng chưa được index, hoặc đã gửi nhưng chưa được xác nhận lưu. Cần xác định “audit đã thành công” ở mốc nào.

Log chỉ nằm trong RAM của process có thể mất khi crash. Log chỉ có ở console của container cũng cần cơ chế thu thập và lưu với bảo đảm phù hợp.

### 8.2. Policy khi không ghi được audit

Có thể cần phân loại operation:

| Loại | Ví dụ quyết định cần đánh giá |
|---|---|
| Thao tác quản trị rủi ro cao | Không tiếp tục khi chưa có bằng chứng tối thiểu bền vững theo policy |
| Operation dữ liệu nhạy cảm | Buffer hữu hạn hoặc fail closed theo yêu cầu |
| Luồng có provider audit độc lập | Xác định bằng chứng tối thiểu và thời gian đối chiếu |
| Metric không phải audit bắt buộc | Có thể giảm chi tiết theo ngân sách |

Đây là những lựa chọn kiến trúc, không phải mặc định chung. Mỗi lựa chọn cần nói về mất dữ liệu tối đa, khả dụng và cách cảnh báo.

Không fallback sang ghi raw request để tránh lỗi serializer.

### 8.3. Không hứa transaction nguyên tử khi không có

Một luồng có thể:

```text
Ghi intent bền vững
    → gọi sign ở provider
    → ghi kết quả
    → trả chữ ký
```

Nếu provider đã ký nhưng ghi kết quả thất bại, thao tác mật mã có thể đã xảy ra dù response ứng dụng không thành công.

Cần giữ intent/operation ID, đánh dấu kết quả chưa xác định và đối chiếu theo cơ chế. Không ghi FAILED với ý nghĩa “không có chữ ký nào được tạo” nếu không có bằng chứng đó.

Cũng không retry một cách mù quáng rồi ghi lại như chỉ có một attempt.

### 8.4. Buffer phải hữu hạn và được bảo vệ

Một local spool có thể giúp chịu gián đoạn, nhưng cần:

- Giới hạn dung lượng.
- Giới hạn thời gian giữ.
- Quyền truy cập.
- Bảo vệ dữ liệu theo phân loại.
- Quy tắc flush, ACK và retry.
- Deduplication.
- Hành vi khi đầy.
- Cách xử lý khi host mất hoặc bị xâm nhập.

Một buffer không giới hạn có thể biến sự cố audit thành cạn đĩa. Một spool chứa metadata nhạy cảm cũng cần lifecycle riêng.

### 8.5. At-least-once và event đến muộn

Pipeline có thể giao lại event. Consumer cần xử lý event ID trùng mà không xóa nhầm những attempt thực sự khác.

Không dùng cùng một ID cho mọi retry nếu cần phân biệt attempt. Có thể có:

```text
businessOperationId
attemptId
auditEventId
providerRequestId
```

theo mức chi tiết cần thiết.

Các event muộn phải giữ occurredAt ban đầu và receivedAt do collector ghi. Không thay thời điểm xảy ra bằng thời điểm ingest rồi làm sai cửa sổ điều tra.

## 9. Bảo vệ tính toàn vẹn và quyền audit

### 9.1. Tách người dùng key và người quản trị log

Một workload có quyền decrypt không nên tự có quyền sửa hoặc xóa audit của nó.

Tương tự, quyền đổi key policy và quyền tắt audit cần được kiểm soát theo mô hình phân tách phù hợp.

Có thể tách:

- Producer chỉ append.
- Collector xác thực nguồn.
- Storage owner quản lý retention.
- Auditor có quyền đọc.
- Người thay cấu hình có quy trình riêng.
- Cơ chế giám sát thay đổi audit không phụ thuộc hoàn toàn vào chính producer.

Không phải mọi đội phải dùng cùng một sơ đồ tổ chức. Nhưng một actor không nên có đường đơn giản vừa lạm dụng key vừa xóa toàn bộ bằng chứng ngoài kiểm soát.

### 9.2. Append-only và retention

Một kho append-only hoặc retention-locked có thể hạn chế sửa/xóa trong thời gian giữ.

Yêu cầu cần xác định:

- Phạm vi object/event.
- Ai có thể thay retention.
- Cơ chế khóa và khả năng vượt quyền theo nền tảng.
- Backup hoặc replica.
- Thời gian giữ và cleanup.
- Quy trình truy cập phục vụ điều tra.

Không dùng từ “immutable” nếu quyền quản trị thông thường vẫn có thể thay dữ liệu theo cách không được ghi nhận.

### 9.3. Hash chain hoặc chữ ký có giới hạn

Hash chain, MAC hoặc chữ ký có thể hỗ trợ phát hiện thay đổi khi cấu trúc, khóa và anchor được quản lý đúng.

Nhưng chúng không tự chứng minh:

- Mọi operation đã tạo event.
- Producer không bỏ sót sự kiện trước khi ký.
- Timestamp nguồn đúng.
- Không có đường dùng key ngoài pipeline.
- Một kho bị xóa toàn bộ sẽ được phát hiện nếu không có anchor độc lập.

Tính toàn vẹn của bằng chứng đã ghi khác với độ đầy đủ của những hành động cần ghi.

### 9.4. Ví dụ xác minh log provider

[CloudTrail log file integrity validation](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-log-file-validation-intro.html) sử dụng digest và chữ ký để hỗ trợ phát hiện thay đổi/xóa sau khi log được chuyển tới nơi lưu.

Tài liệu cũng phân biệt việc bật cơ chế tạo digest với việc thực sự chạy validation. Vì vậy, yêu cầu cần có thao tác kiểm chứng và xử lý lỗi, không chỉ một checkbox cấu hình.

Bảo đảm đó có phạm vi; nó không thay coverage matrix của ứng dụng hoặc chứng minh operation local đã được provider quan sát.

### 9.5. Bảo mật truy cập log

Người đọc audit có thể suy ra:

- Đối tượng nào được truy cập.
- Lịch sử làm việc của một chủ thể.
- Cấu trúc tenant.
- Thời điểm xảy ra sự cố.
- Mối quan hệ giữa key và dữ liệu.

Cần phân quyền, ghi nhận truy cập, giới hạn export và quản lý bản sao điều tra. Audit trail không mặc định là dữ liệu công khai cho mọi thành viên kỹ thuật.

## 10. Phân tích và cảnh báo có mục đích

### 10.1. Những câu hỏi phát hiện thực tế

Có thể xây dựng phát hiện cho:

- Decrypt tăng bất thường theo workload/key.
- Identity mới dùng key nhạy cảm.
- Operation ngoài purpose hoặc môi trường dự kiến.
- Dùng version cũ sau hạn tạo mới.
- Dùng key đã revoke sau cửa sổ hiệu lực.
- Sign hoặc generate-MAC ngoài luồng nghiệp vụ đã biết.
- Thay grant/policy rồi có lượng sử dụng khác thường.
- Audit source hoặc sink đột ngột ngừng gửi.
- Tác vụ hủy/disable ngoài lịch hoặc quy trình.

Mỗi rule cần có phạm vi, owner và hành động phản hồi, không chỉ tạo một biểu đồ.

### 10.2. Bất thường chưa phải kết luận xâm nhập

Spike có thể do migration, retry, khôi phục dữ liệu hoặc một lỗi ứng dụng.

Cảnh báo nên kèm:

- Key và workload liên quan.
- Khoảng thời gian.
- Baseline hoặc điều kiện so sánh.
- OperationId/provider reference có thể tra.
- Thay đổi policy gần đó.
- Mức thiếu hoặc chậm của bằng chứng.
- Runbook xử lý.

Không tự kết luận mọi decrypt failure là giả mạo dữ liệu. Có thể là sai AAD, key version, profile hoặc dữ liệu bị hỏng.

### 10.3. Độ trễ event và độ trễ phát hiện

Có thể phân biệt:

```text
T_occurrence: operation xảy ra
T_receive: collector nhận event
T_index: có thể truy vấn
T_alert: rule phát cảnh báo
```

Một mục tiêu “cảnh báo trong 2 phút” phải nói tính từ mốc nào và áp dụng cho nguồn nào. Con số chỉ là ví dụ, không phải mặc định cho audit key.

Không báo đạt chỉ vì rule chạy nhanh sau ingest, trong khi event mất nhiều giờ để đến collector.

### 10.4. Audit những thay đổi làm mất audit

Cần theo dõi thay đổi:

- Event selector hoặc exclusion.
- Loại data-access log.
- Sink/routing.
- Retention.
- Quyền xóa hoặc đọc log.
- Cấu hình signing/validation.
- Quota và buffer.
- Sampling ở lớp không được phép sampling.

Một sự kiện “audit disabled” cần được gửi hoặc lưu qua một đường có thể còn quan sát được theo thiết kế. Nếu chỉ ghi vào chính nguồn vừa bị tắt, hệ thống có thể mất tín hiệu cần nhất.

## 11. Chuyển quyết định thành yêu cầu bảo mật

### 11.1. Phát biểu mơ hồ

> Hệ thống phải log mọi lần sử dụng key.

Câu này chưa nói “sử dụng” ở tầng nào, cache được xử lý ra sao, event nào bắt buộc và log được bảo vệ thế nào.

### 11.2. Yêu cầu về coverage

> Các operation mật mã được xác định trong phạm vi production phải có nguồn audit tương ứng. Những quyết định bị từ chối trước provider có application event; provider call được đối chiếu bằng reference khi có. Operation local và cache use không được mặc định suy ra từ KMS log.

### 11.3. Yêu cầu về schema

> Event phải có định danh, nguồn, thời gian, chủ thể đã xác minh, key reference, operation, mốc xử lý và kết quả theo schema có version. Trạng thái UNKNOWN phải được giữ khi không xác định được kết quả; không chuyển timeout thành bằng chứng thao tác không xảy ra.

### 11.4. Yêu cầu về dữ liệu nhạy cảm

> Audit không chứa raw key, private key, plaintext data key, credential hoặc plaintext nghiệp vụ. Context và reference theo allowlist đã phân loại. Tối thiểu hóa dữ liệu được thực hiện tại producer trước khi gửi tới log provider hoặc collector.

### 11.5. Yêu cầu về độ bền và lỗi

> Mỗi nhóm operation có policy khi pipeline không khả dụng, giới hạn buffer và điểm xác nhận lưu. Tác vụ không được tự bỏ audit bắt buộc hoặc ghi dữ liệu nhạy cảm để tiếp tục. Khoảng trống và kết quả chưa xác định phải được phát hiện, đối chiếu và công bố trong thời hạn đã định nghĩa.

### 11.6. Yêu cầu về toàn vẹn và quyền

> Producer không có quyền sửa/xóa bằng chứng đã lưu ngoài phạm vi append. Retention và quyền quản trị audit được kiểm soát riêng. Cơ chế validation được thực thi và kiểm tra định kỳ; một cấu hình bật không tự là bằng chứng log đã được xác minh.

### 11.7. Mẫu truy vết

```text
ID: KEY-AUDIT-01
Tài sản:
    bằng chứng sử dụng key và quan hệ key/dữ liệu
Phạm vi:
    data-plane + thay đổi quyền liên quan
Nguồn:
    ứng dụng, provider, pipeline
Schema:
    actor + key reference + operation + stage + outcome
Dữ liệu cấm:
    material, credential và plaintext nhạy cảm
Độ đầy đủ:
    coverage matrix và reconciliation
Độ bền:
    điểm ACK, buffer và failure policy
Toàn vẹn:
    quyền append, retention và validation
Bằng chứng:
    sự kiện thử tổng hợp qua toàn pipeline
```

## 12. Ma trận rủi ro và bằng chứng chấp nhận

| Rủi ro | Kiểm soát | Bằng chứng |
|---|---|---|
| Lạm dụng key không có ngữ cảnh | Schema và correlation | Xác định được workload, operation và mục đích |
| Ứng dụng từ chối nhưng không có KMS call | Application decision event | Có bản ghi deny phù hợp |
| Cache làm thiếu KMS event | Coverage riêng cho local use | Không báo KMS count là toàn bộ data access |
| Log chứa bí mật | Allowlist tại nguồn | Dữ liệu tổng hợp nhạy cảm không xuất hiện trong pipeline |
| Producer giả actor | Danh tính nguồn được xác minh | Metadata tự khai không ghi như sự thật |
| Timeout bị coi là không thực hiện | Outcome UNKNOWN và đối chiếu | Không mất trạng thái cần điều tra |
| Event lặp bị đếm như operation khác | Event/attempt ID rõ | Reconciliation giữ đúng ý nghĩa |
| Pipeline đầy hoặc ngừng | Buffer hữu hạn và failure policy | Không âm thầm bỏ audit bắt buộc |
| Actor xóa dấu vết | Phân quyền và lưu toàn vẹn | Thay đổi trái phép bị chặn hoặc phát hiện |
| Bật digest nhưng không kiểm tra | Quy trình validation | Có kết quả kiểm tra thực tế |
| Audit bị tắt ngoài policy | Theo dõi cấu hình | Thay đổi được phát hiện và xử lý |
| Key revoked vẫn được dùng | Rule gắn policy time/version | Cảnh báo trong thời hạn được công bố |

## 13. Thiết kế kiểm chứng

Những tình huống dưới đây là cơ sở cho việc kiểm thử khi triển khai, không phải kết quả kiểm thử đã chạy cho một hệ thống cụ thể.

### 13.1. Event tổng hợp qua toàn tuyến

Dùng key và dữ liệu thử không nhạy cảm để thực hiện operation trong phạm vi được phép.

Theo dõi:

```text
Request thử
    → decision
    → provider/local operation
    → result
    → collector
    → storage
    → index
    → truy vấn đối chiếu
```

Kiểm tra các field quan trọng khớp ở từng mốc. Không chỉ xác nhận một dòng xuất hiện trên console.

### 13.2. Thành công, deny, lỗi và unknown

Cần bao phủ:

- Operation hợp lệ.
- Workload thiếu quyền.
- Key không active hoặc bị revoke.
- Xác thực tag/MAC thất bại nếu operation liên quan.
- Provider không khả dụng.
- Request timeout sau khi đã gửi.
- Nghiệp vụ lỗi sau khi primitive thành công.
- Retry và event đến muộn.

Expected outcome phải theo nguồn và mốc tương ứng. Không bắt mọi hệ thống ghi cùng một event nếu provider không cung cấp, nhưng coverage gap cần được giải thích và có kiểm soát phù hợp.

### 13.3. Kiểm tra không lộ dữ liệu

Đưa marker tổng hợp vào những trường không được phép ghi, rồi kiểm tra các nơi trong phạm vi:

- Log ứng dụng.
- Error handler.
- Trace.
- Provider context.
- Local spool.
- Collector dead-letter queue.
- Index.
- Bản export phục vụ điều tra.

Không dùng secret production để chứng minh cơ chế redaction. Cần quan sát cả đường lỗi, không chỉ đường thành công.

### 13.4. Lỗi pipeline và crash

Bao phủ:

- Mất kết nối producer–collector.
- Collector trả lỗi.
- Spool đầy.
- Process crash sau key operation nhưng trước result event.
- ACK bị mất và event được gửi lại.
- Storage có event nhưng index chưa có.
- Schema mới chưa được consumer hỗ trợ.
- Event không hợp lệ đi vào dead-letter path.

Điều kiện đạt là hành vi đúng failure policy, không làm mất thông tin một cách âm thầm hoặc tạo kho raw data ngoài kiểm soát.

### 13.5. Toàn vẹn và quyền

Trong môi trường thử, xác minh:

- Producer không sửa/xóa event đã lưu.
- Người chỉ có quyền dùng key không tự thay retention.
- Người đọc audit không mặc định có quyền decrypt dữ liệu.
- Thay đổi file/object log được cơ chế validation phát hiện theo khả năng.
- Event bị thiếu được phát hiện qua cơ chế đối chiếu phù hợp.
- Thao tác thay cấu hình audit có bằng chứng.

Không đồng nhất bài thử integrity với chứng minh coverage hoàn chỉnh. Cần kiểm tra cả hai.

### 13.6. Cache và operation local

Dùng cùng một luồng ứng dụng ở hai trạng thái:

1. Cache miss, có provider call.
2. Cache hit hoặc local use, không có provider call mới.

Kiểm tra coverage matrix có giải thích được cả hai. Nếu yêu cầu audit từng lượt sử dụng dữ liệu, phải có event tương ứng ở lớp được quản lý.

Nếu chỉ có metric tổng hợp cho local use, kết luận phải nêu đúng giới hạn; không xuất một báo cáo per-operation giả từ một counter.

### 13.7. Cảnh báo và điều tra

Tạo tình huống tổng hợp phù hợp để kiểm tra:

- Dùng key ngoài workload dự kiến.
- Operation trên version đã ngừng tạo mới.
- Nguồn audit ngừng gửi.
- Độ trễ ingest vượt ngưỡng.
- Thay cấu hình exclusion.
- Một operation STARTED không có kết luận.
- Một provider call không có correlation mong đợi.

Cần kiểm tra người nhận cảnh báo, nội dung đủ để xử lý và runbook có owner. Một rule chỉ tồn tại trong cấu hình chưa chứng minh đường phản hồi hoạt động.

## 14. Retention, phục hồi và quản lý thay đổi

### 14.1. Retention theo mục đích

Thời gian giữ cần phù hợp:

- Thời gian phát hiện và điều tra sự cố.
- Vòng đời dữ liệu/key.
- Cam kết vận hành và yêu cầu tổ chức áp dụng.
- Mức nhạy cảm của log.
- Chi phí lưu và khả năng truy vấn.
- Chính sách xóa sau khi hết mục đích.

Không giữ vô hạn mọi trường dữ liệu chỉ vì chúng thuộc audit. Ngược lại, không để index xóa sau vài ngày trong khi yêu cầu bằng chứng cần lâu hơn mà không có archive dùng được.

### 14.2. Phục hồi audit trail

Backup cần giữ đủ:

- Event gốc theo schema.
- Metadata nguồn.
- Cơ chế đối chiếu và dedup.
- Digest/chữ ký/anchor nếu dùng.
- Quyền và key cần để đọc log được mã hóa.
- Công cụ hoặc quy tắc diễn giải version cũ.

Một file archive không đọc lại được hoặc không còn bằng chứng integrity không đáp ứng mọi mục tiêu điều tra.

### 14.3. Version schema

Khi provider hoặc ứng dụng đổi format, cần bảo vệ:

- Trường cũ không bị đọc sai ý nghĩa.
- Trường mới không bị bỏ âm thầm nếu là bắt buộc.
- Cảnh báo vẫn chọn đúng operation/outcome.
- Retention và index không làm mất schema version.
- Query lịch sử hiểu được thay đổi.

Không thay một mapping rồi áp dụng ngược cho toàn bộ dữ liệu mà không kiểm chứng nguồn và thời gian.

### 14.4. Những thay đổi cần đánh giá lại

- Bật cache DEK.
- Chuyển operation từ KMS sang local.
- Thay provider.
- Đổi workload identity hoặc grant.
- Thêm tenant/context.
- Thêm vùng hoặc account.
- Đổi sink, collector hoặc retention.
- Thay schema, sampling hoặc event selector.
- Bật một loại operation mật mã mới.
- Đổi cơ chế bảo vệ log.

Những thay đổi đó có thể làm coverage sai dù API nghiệp vụ vẫn chạy bình thường.

## 15. Những sai lầm thường gặp

### 15.1. Có KMS thì mặc định có full audit

Cần kiểm tra loại event, cấu hình, routing, retention và local use. Provider chỉ quan sát trong phạm vi của nó.

### 15.2. Ghi plaintext để biết dữ liệu nào bị đọc

Có thể dùng reference đã phân loại và correlation phù hợp. Ghi dữ liệu thật vào log làm tạo thêm nơi lộ mà không nhất thiết tăng chất lượng bằng chứng.

### 15.3. Timeout được ghi là không có operation

Một kết quả chưa xác định phải được giữ đúng. Cần đối chiếu, không suy ra trạng thái provider từ lỗi client.

### 15.4. Chỉ ghi success

Deny, lỗi, thay policy và thay audit configuration đều có thể cần cho điều tra. Coverage phải theo rủi ro đã xác định.

### 15.5. Dùng sampling rồi báo đủ mọi operation

Dữ liệu mẫu không thay bằng chứng từng thao tác. Nếu chỉ có tổng hợp, phải nêu rõ giới hạn.

### 15.6. Log có chữ ký là đã hoàn toàn đầy đủ

Chữ ký hỗ trợ toàn vẹn của những gì đã ghi, không tự chứng minh không có event bị bỏ trước khi ghi.

### 15.7. Một role vừa dùng key vừa xóa mọi log

Đây là đường xóa dấu vết cần được giảm bằng phân quyền, lưu độc lập và quan sát thay đổi phù hợp.

### 15.8. Bật validation nhưng không chạy kiểm tra

Cấu hình tạo digest hoặc retention không tự thay kết quả kiểm chứng. Phải có quy trình quan sát và xử lý sai lệch.

## 16. Điểm cần ghi nhớ

Audit sử dụng key là bằng chứng có cấu trúc về chủ thể, khóa, operation, quyết định và kết quả. Nó cần kết hợp ngữ cảnh ứng dụng với nguồn key service theo phạm vi thực tế.

Yêu cầu đầy đủ phải nói rõ coverage, dữ liệu cấm ghi, điểm lưu bền vững, xử lý UNKNOWN, quyền truy cập, retention và validation. Cache hoặc operation local là những nơi dễ tạo khoảng trống nếu chỉ dựa vào KMS logs.

Bằng chứng chấp nhận cần đi qua toàn pipeline và bao phủ cả thành công, từ chối, lỗi, retry, mất kết nối và thay cấu hình. Một audit trail tốt giúp điều tra được mà không trở thành một kho key hoặc plaintext mới.
