# Queue và retry không bypass verification

Webhook thường được gửi qua HTTP đến một endpoint công khai, sau đó hệ thống đưa sự kiện vào queue để xử lý bất đồng bộ. Queue giúp giảm thời gian phản hồi, hấp thụ tải và retry khi dependency tạm thời lỗi. Tuy nhiên, việc chuyển một webhook từ HTTP sang queue không làm dữ liệu trở nên đáng tin cậy. Nếu chữ ký chỉ được kiểm tra ở một đường xử lý, nếu worker tin một field verified do message tự khai báo, hoặc nếu retry/DLQ có thể gọi thẳng domain handler, attacker có thể đi vòng qua bước xác minh ban đầu.

Nguyên tắc cốt lõi là **mọi đường đi đến side effect nghiệp vụ đều phải có bằng chứng xác minh hợp lệ gắn với đúng payload và đúng nguồn gửi**. Việc xác minh có thể diễn ra trước khi enqueue hoặc trong worker, tùy kiến trúc. Nhưng queue, retry, dead-letter queue và thao tác redrive không được tạo ra một đường xử lý ít kiểm soát hơn.

Trong bảo mật API, webhook là một trust boundary: request đến từ hệ thống bên ngoài, có thể được gửi lặp, đến sai thứ tự, đến trễ hoặc bị giả mạo. Queue là một trust boundary tiếp theo: message được lưu, chuyển tiếp, retry và có thể được vận hành viên phát lại. Cần thiết kế cả hai ranh giới cùng với trạng thái workflow và idempotency.

## 1. Hiểu luồng webhook và các điểm xác minh

Một luồng điển hình:

~~~mermaid
flowchart TD
    P[Provider sends webhook] --> I[Public webhook ingress]
    I --> L[Limit size and validate headers]
    L --> V[Verify signature and timestamp]
    V -->|Valid| E[Create trusted event envelope]
    V -->|Invalid| R[Reject and audit]
    E --> Q[Durable queue]
    Q --> W[Worker authenticates message source]
    W --> S[Validate envelope and schema]
    S --> D[Deduplicate and check event state]
    D --> H[Apply business transition]
    H --> A[Audit and acknowledge]
    Q --> X[Retry policy]
    X --> Q
    X --> DLQ[Dead-letter queue]
~~~

Luồng trên thể hiện một lựa chọn: ingress xác minh chữ ký trước khi enqueue. Một kiến trúc khác có thể enqueue raw webhook trước, rồi worker xác minh trước mọi xử lý nghiệp vụ. Cả hai có thể an toàn nếu ranh giới tin cậy được xác định rõ và không có side effect nào xảy ra trước verification.

### 1.1. Các bước có trách nhiệm khác nhau

| Thành phần | Trách nhiệm chính | Không được giả định |
|---|---|---|
| Webhook ingress | Giới hạn request, xác minh nguồn/chữ ký, xác định provider và endpoint | Request đến đúng URL thì chắc chắn đến từ provider |
| Queue producer | Tạo message envelope có nguồn gốc và metadata rõ ràng | Có thể enqueue mọi payload chưa xác minh vào luồng trusted |
| Message broker | Bảo vệ lưu trữ, quyền publish/consume, delivery và retry | Message trong queue luôn nguyên vẹn hoặc đúng nghiệp vụ |
| Worker | Xác minh nguồn message, envelope, payload, event state và quyền thực thi | Message có field verified là đã được xác minh |
| Retry handler | Thử lại lỗi tạm thời theo policy và idempotency | Lần xử lý trước đã xác minh nên lần sau không cần kiểm tra trạng thái |
| DLQ/redrive | Cách ly message lỗi và phát lại có kiểm soát | Vận hành viên có thể sửa payload rồi replay tùy ý |

### 1.2. Phân biệt xác minh chữ ký và xác thực message nội bộ

Chữ ký webhook xác minh rằng payload được tạo bởi bên nắm giữ secret/private key của provider theo cơ chế đã thỏa thuận. Sau khi ingress xác minh, hệ thống có thể tạo một message nội bộ đã được attest. Nhưng worker vẫn cần xác thực message đến từ producer đáng tin, kiểm tra tính toàn vẹn và xác nhận envelope thuộc đúng provider, endpoint, tenant và loại event.

Hai bước bảo vệ hai trust boundary khác nhau:

- **Provider → ingress:** xác minh chữ ký, timestamp, key và nội dung gốc.
- **Ingress → broker → worker:** xác minh workload identity, quyền broker, tính toàn vẹn và provenance của message nội bộ.

Không dùng kết quả xác minh ở ranh giới thứ nhất để bỏ qua ranh giới thứ hai.

## 2. Chọn thời điểm verification: trước queue hay trong worker

Có hai mô hình thường dùng. Việc chọn phụ thuộc vào thời gian xác minh, tải, khả năng lưu raw body và yêu cầu phản hồi của provider.

### 2.1. Verify tại ingress rồi enqueue trusted event

Trong mô hình này, endpoint nhận webhook đọc raw body, kiểm tra chữ ký và timestamp, xác định provider/account, rồi mới tạo message nội bộ.

Ưu điểm:

- Payload sai chữ ký bị loại trước khi chiếm queue và worker capacity.
- Broker chỉ nhận event đã vượt qua kiểm tra nguồn ở ingress.
- Provider nhận response HTTP nhanh sau khi message được ghi bền vững.
- Worker có thể tập trung vào schema, deduplication và xử lý nghiệp vụ.

Điều kiện:

- Ingress phải xác minh chữ ký trên đúng raw bytes theo contract của provider.
- Queue producer phải là service identity được tin cậy và chỉ có quyền publish vào đúng topic.
- Envelope cần gắn với hash payload, provider/account, event ID và verification metadata.
- Worker phải xác thực producer/message và kiểm tra envelope trước side effect.
- Không cho phép client hoặc một service khác tự gửi message vào trusted topic.

Không nên lưu một boolean verified đơn lẻ rồi tin tuyệt đối. Bằng chứng phải gắn với payload bất biến, provider, key context, thời điểm và phiên bản policy đã dùng để xác minh.

### 2.2. Enqueue raw event rồi verify trong worker

Một số hệ thống muốn trả lời webhook nhanh hoặc cần xử lý xác minh tốn thời gian trong worker. Khi đó ingress có thể enqueue raw request vào một queue dành riêng cho dữ liệu chưa tin cậy.

Điều kiện bắt buộc:

- Queue này phải được phân loại là untrusted input.
- Worker phải xác minh chữ ký và timestamp trước khi gọi domain handler.
- Không có consumer, retry hook hoặc side channel nào gọi business logic trực tiếp từ raw queue.
- Raw body và signature headers phải được giữ nguyên theo yêu cầu của provider.
- Message cần giới hạn kích thước và thời hạn lưu.
- Queue và worker phải được bảo vệ khỏi message giả mạo hoặc sửa đổi.
- Chỉ sau khi verification thành công mới chuyển thành trusted event hoặc cập nhật trạng thái đã xác minh.

Mô hình này giảm tải xử lý đồng bộ cho ingress nhưng cần cẩn thận với timestamp freshness. Timestamp webhook được kiểm tra theo thời điểm nhận ban đầu, không nên bị đánh giá như một request mới khi worker retry nhiều phút sau. Worker cần dùng received-at được ghi nhận đáng tin cậy và policy về cửa sổ xác minh ban đầu.

### 2.3. Không trộn hai mô hình tùy tiện

Không enqueue raw payload vào topic trusted rồi trông chờ worker nhớ kiểm tra một field. Cũng không enqueue event đã xác minh nhưng sau đó cho phép một endpoint nội bộ nhận message không có provenance. Tách rõ topic/schema/trạng thái:

- Raw/unverified event.
- Verified internal event.
- Retry event có provenance.
- Dead-letter event chờ điều tra.

Quyền publish và consume cần khác nhau theo từng loại. Chuyển từ unverified sang verified phải là một bước có kiểm soát, có thể audit và không thể bị caller bên ngoài tự thực hiện.

## 3. Xác minh chữ ký trên đúng payload

Nhiều provider ký trên raw HTTP body, có thể kèm timestamp, event ID hoặc một chuỗi canonical theo tài liệu của họ. Nếu ứng dụng parse JSON rồi serialize lại trước khi verify, khoảng trắng, thứ tự field, escape sequence hoặc encoding có thể thay đổi và làm sai chữ ký.

Nguyên tắc:

- Đọc raw bytes đúng một lần theo giới hạn kích thước.
- Lấy signature header và timestamp theo đúng tên/format provider quy định.
- Dùng thuật toán, canonicalization và encoding đúng tài liệu.
- Không parse rồi serialize lại trước khi xác minh nếu provider ký raw body.
- So sánh MAC/signature bằng hàm constant-time phù hợp.
- Chỉ parse JSON sau khi verification thành công, nếu kiến trúc xác minh ở ingress.
- Không tự chấp nhận thuật toán yếu hoặc thuật toán do request tự chọn.

Ví dụ generic HMAC-SHA256:

~~~java
byte[] expected = hmacSha256(secret, signedPayload);
byte[] supplied = decodeSignature(signatureHeader);

if (!MessageDigest.isEqual(expected, supplied)) {
    throw new InvalidWebhookSignatureException();
}
~~~

Đây là minh họa nguyên tắc, không phải contract chung cho mọi provider. Một số provider ký timestamp nối với body, một số dùng RSA/ECDSA hoặc định dạng signature khác. Hãy triển khai đúng SDK/spec chính thức, xác minh độ dài và encoding, và không tự ghép signedPayload khác với quy tắc của provider.

### 3.1. Xác minh timestamp và chống replay

Chữ ký hợp lệ có thể bị phát lại nếu attacker lấy được một request cũ. Nếu provider hỗ trợ timestamp:

- Kiểm tra timestamp nằm trong cửa sổ chấp nhận quanh thời điểm nhận.
- Dùng đồng hồ hệ thống đồng bộ và theo dõi clock drift.
- Ghi nhận event ID hoặc delivery ID để deduplicate.
- Có thể dùng nonce nếu protocol hỗ trợ.
- Từ chối signature thiếu timestamp khi contract yêu cầu.
- Không cho phép client tự đặt received-at hoặc thời điểm xác minh.

Timestamp giúp giới hạn tuổi request nhưng không thay thế idempotency. Một webhook hợp lệ có thể được provider gửi lại nhiều lần trong cửa sổ hợp lệ; event ID và trạng thái xử lý vẫn cần ngăn side effect lặp.

### 3.2. Key rotation

Provider có thể xoay secret hoặc signing key. Hệ thống cần:

- Lưu nhiều key đang hợp lệ trong overlap window theo contract.
- Dùng key ID hoặc cấu hình endpoint để chọn tập key được phép.
- Không cho request tự chỉ định URL hoặc secret source tùy ý.
- Theo dõi key version đã xác minh và thời điểm hiệu lực.
- Loại bỏ key cũ sau thời gian chuyển tiếp.
- Có quy trình khẩn cấp khi secret bị lộ.

Nếu key ID đến từ header, chỉ dùng nó để chọn trong một tập key đã cấu hình cho provider/endpoint đó. Không dùng giá trị này để truy cập một secret path tùy ý.

## 4. Tạo trusted event envelope có provenance

Khi verification thành công, ingress nên tạo một envelope nội bộ chứa đủ thông tin để worker xác định nguồn gốc và kiểm tra tính toàn vẹn.

Các trường thường cần:

| Trường | Mục đích |
|---|---|
| provider | Xác định nhà cung cấp |
| provider_account | Phân biệt merchant/account hoặc webhook endpoint |
| event_id | ID ổn định do provider cấp, dùng deduplication |
| event_type | Loại sự kiện theo allowlist |
| payload | Nội dung đã xác minh hoặc raw bytes cần thiết |
| payload_hash | Hash của đúng payload đã được xác minh |
| signature_key_id | Key version đã dùng |
| signature_timestamp | Timestamp được provider ký, nếu có |
| verified_at | Thời điểm ingress xác minh |
| received_at | Thời điểm ingress nhận request |
| verification_policy_version | Phiên bản quy tắc xác minh |
| correlation_id | Liên kết log/trace và operation |
| tenant_mapping | Tenant nội bộ đã được xác định từ mapping tin cậy |

Envelope không nên chứa secret dùng để xác minh. Không đưa Authorization header đầy đủ hoặc signature secret vào queue. Có thể lưu signature gốc nếu cần bằng chứng điều tra, nhưng cần đánh giá retention và quyền truy cập; nhiều trường hợp chỉ cần key ID, timestamp, payload hash và kết quả verification đã được attest.

### 4.1. Bảo vệ verified attestation

Worker không nên tin một field verified=true chỉ vì nó có trong JSON. Cần bảo vệ nguồn và tính toàn vẹn của envelope bằng một hoặc nhiều cách:

- Broker ACL chỉ cho ingress service identity publish vào verified topic.
- TLS/mTLS hoặc workload identity cho producer/consumer.
- Schema/topic riêng cho verified event.
- Message signing hoặc MAC nội bộ nếu message đi qua nhiều miền tin cậy.
- Immutable storage hoặc append-only record cho bằng chứng verification khi cần.
- Hash payload được kiểm tra lại trước khi xử lý.

Nếu một service khác có quyền publish vào verified topic, nó có thể giả event đã xác minh. Quyền broker phải theo least privilege và được kiểm tra định kỳ.

### 4.2. Payload bất biến

Verification chỉ có ý nghĩa đối với đúng bytes đã được ký. Nếu payload được transform, enrich hoặc sửa trước khi worker xử lý, phải phân biệt:

- Raw payload đã ký.
- Parsed DTO được tạo từ raw payload.
- Internal domain event sau mapping.

Giữ hash của raw payload để đối chiếu. Mọi enrichment nội bộ cần ghi rõ nguồn và không được ghi đè các field gốc có ý nghĩa xác minh như event ID, account reference hoặc amount. Nếu cần thay đổi payload, tạo một bản ghi mới có quan hệ với event gốc và audit.

## 5. Worker phải xác minh trước side effect

Worker là một consumer có quyền thực hiện thay đổi nghiệp vụ. Không nên xem nó là một tiến trình nội bộ tự động an toàn. Worker cần xác thực message source, kiểm tra schema, provenance, tenant mapping và trạng thái operation trước khi xử lý.

Một trình tự tham khảo:

1. Xác thực workload identity hoặc broker principal của message.
2. Kiểm tra topic, schema version và message size.
3. Xác minh producer có quyền phát loại event này.
4. Kiểm tra provider/account/event type thuộc cấu hình được phép.
5. Kiểm tra payload hash khớp với attestation.
6. Nếu kiến trúc xác minh tại worker, kiểm tra signature và timestamp trước khi parse/dispatch.
7. Parse vào DTO biên giới và validate field, enum, size và business invariant.
8. Resolve tenant/object từ mapping tin cậy.
9. Kiểm tra event deduplication, trạng thái workflow và quyền service identity.
10. Thực hiện side effect theo transaction/idempotency.
11. Ghi audit và acknowledge message sau khi commit.

Không để worker có quyền rộng hơn mức cần thiết. Worker chỉ nên có thể cập nhật domain object và phát event phục vụ nhiệm vụ của nó; không dùng credential quản trị toàn hệ thống cho mọi consumer.

### 5.1. Không dùng queue như bằng chứng authorization

Message đến từ queue nội bộ không chứng minh user hoặc tenant được phép thực hiện mọi action. Với webhook provider, authorization thường là authorization của provider đối với account/event đã đăng ký, sau đó hệ thống map event vào tenant và workflow nội bộ.

Worker cần xác minh:

- Provider account thuộc tenant nào theo mapping do hệ thống quản lý.
- Object reference có khớp operation đã tạo hay không.
- Event type có được phép thay đổi trạng thái hiện tại không.
- Service identity có quyền thực hiện transition đó không.
- Tenant/object có còn hợp lệ hoặc bị khóa theo policy hiện tại không.

Không dùng tenant ID trong payload webhook làm căn cứ duy nhất để chọn tenant database. Hãy đối chiếu provider account/reference với mapping nội bộ đã được xác minh.

## 6. Retry không được bỏ qua verification hoặc business checks

Retry là việc thử lại một lần xử lý thất bại. Nó không phải một đường tắt để gọi handler trực tiếp mà bỏ qua validation, provenance hoặc idempotency.

Một lần retry cần giữ nguyên:

- Event ID và provider/account identity.
- Payload hash hoặc raw payload bất biến.
- Verification attestation hoặc dữ liệu đủ để xác minh lại.
- Tenant mapping và correlation ID.
- Idempotency key của operation.
- Phiên bản schema/policy có ý nghĩa đối với event.

Trước khi thực hiện side effect ở mỗi lần retry, worker vẫn cần kiểm tra event đã xử lý chưa, operation còn hợp lệ không, trạng thái hiện tại có cho phép transition không và dependency có đang ở trạng thái phù hợp không.

### 6.1. Phân loại lỗi trước khi retry

| Loại lỗi | Hành vi |
|---|---|
| Signature invalid hoặc timestamp ngoài cửa sổ tại ingress | Từ chối; không retry như lỗi tạm thời |
| Message provenance hoặc payload hash sai | Cách ly, cảnh báo và không dispatch |
| Schema/enum không hỗ trợ | DLQ hoặc quarantine để điều tra; không retry vô hạn |
| Business invariant không đạt | Từ chối hoặc manual review theo nghiệp vụ |
| Database/network timeout tạm thời | Retry có giới hạn và backoff |
| Dependency 429/5xx | Tôn trọng Retry-After, retry budget và deadline |
| Credential worker hết hạn | Dừng consumer, cảnh báo và khôi phục credential |
| Event đã xử lý | Acknowledge như duplicate đã nhận diện, không lặp side effect |
| Trạng thái không xác định sau timeout | Tra cứu operation/idempotency trước khi chạy lại |

Không retry lỗi xác minh như thể provider chỉ đang chậm. Việc gửi lại cùng payload sai chữ ký không làm nó trở nên hợp lệ.

### 6.2. Backoff, jitter và retry budget

Dùng exponential backoff có jitter để tránh nhiều worker retry cùng lúc. Đặt số lần retry tối đa, tổng thời gian tối đa và giới hạn số message đang retry. Tôn trọng Retry-After khi provider/dependency trả về. Tránh retry ở nhiều tầng cùng lúc vì một request có thể bị nhân số lần gọi theo tích của retry ở gateway, service, queue và HTTP client.

Một policy cần xác định:

- Lỗi nào được retry.
- Số lần retry và khoảng thời gian giữa các lần.
- Tổng deadline của event.
- Retry budget theo provider, tenant hoặc loại event.
- Điều kiện đưa vào DLQ.
- Cách vận hành viên redrive sau khi khắc phục.

### 6.3. Không làm mới timestamp của webhook khi retry

Không sửa timestamp ký trong payload hoặc tạo timestamp mới rồi coi đó là một webhook mới. Timestamp là một phần của bằng chứng ban đầu. Khi retry, giữ nguyên dữ liệu ký và verification metadata; thời điểm retry chỉ là metadata nội bộ.

Nếu worker xác minh chữ ký lại, cần phân biệt hai câu hỏi:

- Chữ ký có khớp với payload và key context tại thời điểm nhận ban đầu không?
- Request ban đầu có nằm trong cửa sổ freshness khi ingress nhận nó không?

Không áp dụng cửa sổ timestamp tính từ hiện tại cho một event đã được nhận hợp lệ nhưng nằm trong queue lâu. Ngược lại, cũng không được cho phép một raw webhook cũ chưa từng được xác minh đi vào worker như một event mới hợp lệ.

## 7. Idempotency và deduplication

Provider có thể gửi cùng một event nhiều lần do timeout, không nhận được HTTP response hoặc retry theo lịch của họ. Queue cũng có thể deliver lại message khi worker crash trước khi acknowledge. Vì vậy, deduplication phải được thực hiện ở tầng lưu trữ hoặc transaction có tính nguyên tử, không chỉ dựa vào bộ nhớ của worker.

Một khóa deduplication thường dựa trên:

- Provider.
- Provider account hoặc webhook endpoint.
- Event ID của provider.

Ví dụ unique key trong inbox table:

~~~sql
CREATE TABLE webhook_inbox (
    provider          VARCHAR(80)  NOT NULL,
    provider_account  VARCHAR(120) NOT NULL,
    event_id          VARCHAR(200) NOT NULL,
    payload_hash      CHAR(64)     NOT NULL,
    received_at       TIMESTAMP    NOT NULL,
    status            VARCHAR(24)  NOT NULL,
    processed_at      TIMESTAMP    NULL,
    PRIMARY KEY (provider, provider_account, event_id)
);
~~~

Đây là schema minh họa. Cần chọn độ dài, kiểu timestamp và cách lưu hash theo database thực tế. Nếu cùng event ID xuất hiện lại với payload hash khác, không coi đó là duplicate bình thường; cách ly và cảnh báo vì có thể là lỗi provider, collision hoặc hành vi giả mạo.

### 7.1. Commit side effect và inbox state nhất quán

Không đánh dấu event processed trước khi side effect được commit. Nếu worker ghi processed rồi crash trước khi cập nhật payment, lần retry có thể bị bỏ qua và giao dịch bị kẹt. Nếu cập nhật payment xong rồi crash trước khi ghi processed, retry có thể lặp side effect.

Giải pháp thường dùng là transaction database bao gồm:

1. Insert/claim inbox event với unique key.
2. Kiểm tra trạng thái operation.
3. Áp dụng domain transition.
4. Ghi outbox event nếu cần phát message tiếp.
5. Đánh dấu inbox event processed.
6. Commit tất cả thay đổi nội bộ cùng nhau.

Với side effect ở provider bên ngoài, database transaction không thể bao trùm request HTTP. Dùng idempotency key phía provider, operation state machine và reconciliation để xử lý kết quả không xác định.

### 7.2. Event ID không thay thế business idempotency

Hai event ID khác nhau có thể mô tả cùng một operation hoặc cùng một trạng thái. Ngược lại, cùng một event có thể được gửi lại. Ngoài dedup theo event ID, domain handler cần kiểm tra operation ID, payment reference và transition hiện tại để tránh xử lý trùng về mặt nghiệp vụ.

## 8. Ordering và event đến sai thứ tự

Queue có thể đảm bảo thứ tự trong một partition hoặc message group, nhưng không phải mọi broker và cấu hình đều bảo đảm ordering toàn cục. Provider cũng có thể gửi event mới trước event cũ.

Ví dụ:

- payment.succeeded đến trước payment.processing.
- subscription.cancelled đến trước subscription.updated cũ.
- account.disabled đến sau một event đã được tạo trước đó nhưng gửi trễ.

Không dùng thời điểm nhận queue làm thứ tự nghiệp vụ duy nhất. Nên:

- Dùng provider sequence/version nếu có.
- Kiểm tra transition hợp lệ trong state machine.
- So sánh event creation time hoặc version theo contract, có xử lý clock skew.
- Lưu event đến muộn để audit thay vì lùi trạng thái hiện tại.
- Với event cần trạng thái mới nhất, truy vấn provider qua API đã xác thực trước khi quyết định.
- Không để event cũ ghi đè trạng thái mới hơn.

### 8.1. State machine cho event

Ví dụ payment có thể chuyển theo các trạng thái CREATED, PENDING, AUTHORIZED, CAPTURED, FAILED và REFUNDED. Event chỉ được phép tạo transition hợp lệ. Một event FAILED đến sau CAPTURED không nên tự động chuyển payment về FAILED nếu contract không cho phép. Trường hợp mâu thuẫn cần được đưa vào reconciliation hoặc manual review.

## 9. Dead-letter queue và redrive an toàn

DLQ cách ly message không thể xử lý sau số lần retry hoặc do lỗi vĩnh viễn. DLQ là nơi chứa dữ liệu bên ngoài, có thể có PII, transaction reference, signature metadata hoặc payload độc hại. Không nên cấp quyền đọc rộng hoặc cho phép sửa rồi replay tùy ý.

Kiểm soát DLQ:

- Topic/queue riêng với ACL tối thiểu.
- Encryption in transit và at rest.
- Retention có giới hạn và chính sách xóa.
- Redaction trong dashboard/log.
- Quyền xem payload thô chỉ dành cho nhóm được phê duyệt.
- Ghi audit mọi lần inspect, export, retry hoặc redrive.
- Cảnh báo khi DLQ tăng đột biến hoặc có loại event mới.
- Không tự động redrive toàn bộ DLQ khi dependency vừa phục hồi.

### 9.1. Redrive không phải enqueue lại payload tùy ý

Trước khi redrive:

1. Xác định nguyên nhân ban đầu và khắc phục dependency/policy.
2. Xác minh message provenance và payload hash.
3. Giữ nguyên provider, account, event ID và verification attestation.
4. Kiểm tra event chưa được xử lý qua đường khác.
5. Kiểm tra operation và state machine còn cho phép transition.
6. Xác định redrive có cần re-verify chữ ký theo policy hay không.
7. Thực hiện với batch size/rate limit nhỏ.
8. Ghi actor, lý do, ticket, số lượng và kết quả.

Không chỉnh payload để làm cho event vượt validation rồi redrive dưới danh nghĩa event gốc. Nếu cần sửa dữ liệu nghiệp vụ, tạo correction operation có actor, approval và audit riêng.

### 9.2. Phân biệt retry tự động và replay thủ công

Retry tự động xử lý lỗi tạm thời theo policy đã định. Replay thủ công là một thao tác vận hành có thể gây side effect tài chính hoặc thay đổi dữ liệu. Replay cần permission riêng, step-up/approval khi phù hợp và phải hiển thị event ID, tenant, action, payload hash cùng trạng thái hiện tại trước khi thực hiện.

## 10. Queue security và quyền producer/consumer

Broker là thành phần bảo mật quan trọng. Nếu một workload không đáng tin có thể publish vào topic webhook verified, mọi kiểm soát ở ingress có thể bị vô hiệu hóa.

Áp dụng:

- Authentication workload-to-broker bằng identity phù hợp.
- ACL theo topic và action: publish, consume, inspect, purge, redrive.
- Producer chỉ publish vào topic được giao.
- Consumer chỉ consume nhóm topic cần thiết.
- DLQ và retry topic có quyền riêng.
- Không dùng credential broker chung cho toàn bộ service.
- TLS/mTLS và encryption at rest theo khả năng broker.
- Rotation credential và thu hồi khi workload bị xâm nhập.
- Giới hạn message size, retention, partition và consumer concurrency.
- Theo dõi thay đổi ACL và quyền quản trị broker.

Nếu broker hỗ trợ message-level encryption hoặc signing, cân nhắc khi message đi qua nhiều miền quản trị hoặc cần bảo vệ provenance độc lập với broker ACL. Không tự xây crypto envelope nếu chưa có thiết kế và quản lý key phù hợp.

### 10.1. Tách topic theo trust level

Một cách tổ chức:

| Topic | Nội dung | Producer được phép | Consumer được phép |
|---|---|---|---|
| webhook.raw | Raw request chưa xác minh | Webhook ingress | Verification workers |
| webhook.verified | Event đã xác minh và có provenance | Verification service | Domain workers |
| webhook.retry | Event chờ retry theo policy | Worker/retry scheduler | Consumer được chỉ định |
| webhook.dlq | Event lỗi cần điều tra | Broker/dead-letter handler | Operator/service được phê duyệt |

Tên topic chỉ là ví dụ. Điều quan trọng là trust level được thể hiện trong schema, ACL, monitoring và quy trình vận hành, không chỉ bằng convention trong tên.

## 11. Tenant isolation và provider mapping

Webhook endpoint có thể dùng chung cho nhiều merchant hoặc tenant. Một payload có thể chứa account ID, customer ID hoặc object reference từ provider. Không lấy tenant ID trong body làm căn cứ duy nhất để truy cập dữ liệu nội bộ.

Quy trình mapping:

1. Xác định endpoint/credential/key set đã nhận webhook.
2. Xác minh signature theo provider account tương ứng.
3. Đọc provider account/reference từ payload đã xác minh.
4. Tra cứu mapping nội bộ được quản lý bởi admin workflow.
5. Kiểm tra mapping đang active và thuộc đúng provider.
6. Xác minh object reference nằm trong tenant được map.
7. Gắn tenant context tin cậy vào internal envelope.

Nếu không xác định được tenant hoặc mapping mâu thuẫn, cách ly event để điều tra. Không thử lần lượt mọi tenant cho đến khi tìm thấy object khớp.

## 12. Giới hạn tài nguyên và chống message poisoning

Kẻ tấn công có thể gửi nhiều webhook không hợp lệ, payload rất lớn hoặc cấu trúc gây tốn CPU parser. Nếu ingress enqueue mọi request, queue có thể bị lấp đầy trước khi worker xác minh.

Giới hạn tại ingress:

- Request body bytes và header size.
- Số header và độ dài signature header.
- Request timeout và connection limits.
- Rate limit theo provider endpoint/IP đã xác minh ở proxy.
- Content-Type và encoding được hỗ trợ.
- Giới hạn giải nén và parser depth.

Nếu xác minh chữ ký trước queue, payload sai chữ ký không nên chiếm worker queue. Nếu phải enqueue raw input, dùng raw queue có quota, retention ngắn và worker capacity riêng; không để raw traffic làm cạn queue nghiệp vụ.

### 12.1. Queue backpressure

Theo dõi queue depth, oldest message age, consumer lag, retry rate và DLQ count. Đặt giới hạn concurrency để worker không mở quá nhiều connection đến database/provider. Khi queue đầy, ingress cần trả response theo contract để provider retry có kiểm soát; không trả 2xx nếu event chưa được lưu bền vững.

### 12.2. Poison message

Poison message là message luôn gây lỗi khi xử lý, ví dụ schema không hợp lệ, parser crash hoặc state transition không thể thực hiện. Không để message này retry vô hạn và chiếm worker. Đặt max delivery count, quarantine và alert. Không bỏ qua validation để message qua được; cần sửa nguyên nhân hoặc tạo correction event có audit.

## 13. Ví dụ trình tự xử lý với Java

Ví dụ dưới đây minh họa ranh giới trách nhiệm, không phải SDK đầy đủ cho một provider cụ thể.

### 13.1. Ingress xác minh trước khi enqueue

~~~java
public ResponseEntity<Void> receive(
        byte[] rawBody,
        HttpHeaders headers) {

    if (rawBody.length > MAX_WEBHOOK_BYTES) {
        return ResponseEntity.status(413).build();
    }

    ProviderConfig config = providerRegistry.resolveConfiguredEndpoint(
        headers, requestPath());

    VerificationResult verification =
        verifier.verify(config, rawBody, headers);

    if (!verification.valid()) {
        audit.invalidWebhook(config.provider(), verification.reason());
        return ResponseEntity.status(401).build();
    }

    VerifiedWebhookEnvelope envelope =
        envelopeFactory.create(config, rawBody, verification);

    queuePublisher.publishVerified(envelope);
    return ResponseEntity.accepted().build();
}
~~~

Endpoint và provider config cần được resolve từ route/config đã quản lý, không để header tùy ý chọn secret hoặc provider URL. Response 202 chỉ được trả sau khi broker xác nhận message đã được ghi bền vững theo durability requirement. Mã minh họa cần bổ sung exception mapping, timeout, audit và contract status cụ thể.

### 13.2. Worker kiểm tra provenance và idempotency

~~~java
public void handle(VerifiedWebhookEnvelope envelope) {
    messageAuthenticator.verifyProducer(envelope);
    envelopeValidator.validate(envelope);
    payloadHashVerifier.verify(envelope);

    WebhookEvent event = parser.parse(envelope.rawPayload());
    businessValidator.validate(envelope, event);

    transactionTemplate.executeWithoutResult(tx -> {
        if (inboxRepository.exists(
                envelope.provider(),
                envelope.providerAccount(),
                envelope.eventId())) {
            return;
        }

        tenantResolver.verifyMapping(envelope, event);
        domainHandler.apply(envelope, event);
        inboxRepository.markProcessed(envelope);
        outboxRepository.appendEvents(envelope, event);
    });
}
~~~

Đây là pseudocode để minh họa thứ tự. Việc claim event phải có unique constraint và xử lý race condition nguyên tử; kiểm tra exists rồi insert riêng rẽ có thể cho phép hai worker cùng chạy. Trong triển khai thật, dùng insert-if-absent/unique constraint hoặc lock phù hợp. Không acknowledge message trước khi transaction commit thành công.

### 13.3. Retry không gọi handler bỏ qua guard

Retry scheduler nên phát lại envelope gốc có provenance và delivery metadata mới, hoặc yêu cầu worker xử lý lại cùng event ID. Không tạo một route nội bộ gọi trực tiếp domain handler mà bỏ qua message authentication, envelope validation, deduplication và state check.

## 14. Giám sát và audit

Các metric cần theo dõi:

- Webhook received, signature valid/invalid và timestamp rejected.
- Event accepted, verified, queued và processing latency.
- Queue depth, oldest message age và consumer lag.
- Retry count theo provider/event type/reason.
- Duplicate event và payload hash mismatch.
- DLQ count, redrive count và redrive success/failure.
- Schema validation/business invariant failure.
- Provider account/tenant mapping failure.
- Broker authentication/ACL denial.
- Idempotency conflict và operation pending quá lâu.

Audit event nên ghi provider, provider account reference, event ID, payload hash, verification result/reason, key ID, policy version, received-at, verified-at, worker identity, tenant mapping, operation ID và kết quả xử lý. Không ghi secret, token, raw signature secret hoặc payload nhạy cảm đầy đủ.

Log cần có correlation ID để nối ingress, broker, worker, retry và domain event. Khi redrive, giữ event ID gốc và tạo redrive operation ID riêng. Điều này giúp phân biệt một lần provider gửi lại với một lần operator chủ động phát lại.

## 15. Kiểm thử queue, retry và verification

Test cần chứng minh mọi đường xử lý đều giữ được verification và không tạo side effect trùng.

| Nhóm test | Tình huống | Kết quả mong đợi |
|---|---|---|
| Signature | Sai signature, thiếu header hoặc key không hợp lệ | Không có domain side effect |
| Raw bytes | JSON được parse/serialize lại trước khi verify | Verification không chấp nhận bytes khác |
| Timestamp | Timestamp quá cũ/tương lai ngoài ngưỡng | Bị từ chối theo policy |
| Replay | Gửi lại event ID đã xử lý | Không lặp side effect |
| Queue source | Principal lạ publish vào verified topic | Broker từ chối |
| Envelope integrity | Sửa payload nhưng giữ attestation/hash cũ | Worker từ chối và quarantine |
| Worker path | Gọi worker handler với event chưa verified | Không dispatch domain handler |
| Retry | Retry message sau timeout | Giữ nguyên event ID/hash/provenance |
| Timestamp on retry | Event hợp lệ nằm queue lâu | Không bị coi là webhook mới; freshness gắn với ingress time |
| Idempotency race | Hai worker xử lý cùng event đồng thời | Chỉ một transaction áp dụng side effect |
| Ordering | Event cũ đến sau event mới | State machine không bị lùi trạng thái |
| DLQ/redrive | Redrive event đã xử lý hoặc payload bị sửa | Không tạo side effect; audit rõ |
| Tenant mapping | Provider account map sang tenant khác | Không ghi vào tenant không đúng |
| Resource limits | Body lớn, header lớn, queue flood | Bị giới hạn và có backpressure |
| Poison message | Schema luôn lỗi | Đưa DLQ sau ngưỡng, không retry vô hạn |
| Broker outage | Queue không ghi bền vững | Ingress không trả success giả |
| Logging | Payload có PII/token | Log đã redact, không lộ secret |

### 15.1. Test end-to-end

Một test end-to-end nên:

1. Tạo payload fixture đúng contract của provider.
2. Ký payload bằng test key.
3. Gửi qua public ingress.
4. Xác minh event được enqueue với envelope đúng.
5. Chạy worker và kiểm tra domain transition.
6. Gửi lại cùng event và xác nhận không có side effect thứ hai.
7. Làm worker lỗi tạm thời rồi retry.
8. Sửa payload/hash để thử bypass và xác nhận bị từ chối.
9. Đưa message vào DLQ và redrive theo quyền được cấp.
10. Kiểm tra audit từ ingress đến kết quả cuối.

Test cần dùng key và dữ liệu giả; không dùng secret hoặc webhook production thật.

## 16. Những sai lầm thường gặp

- **Chỉ verify ở ingress rồi tin mọi message nội bộ:** producer hoặc broker khác có thể giả message verified.
- **Chỉ verify ở một worker path:** retry, redrive hoặc consumer phụ có thể gọi handler trực tiếp.
- **Tin field verified=true:** không ràng buộc với producer identity và payload hash.
- **Parse rồi serialize trước khi verify:** chữ ký không còn được kiểm tra trên đúng bytes.
- **Làm mới timestamp khi retry:** biến một event cũ thành request có vẻ mới.
- **Retry lỗi chữ ký:** lãng phí tài nguyên và làm tăng tải mà không sửa được lỗi.
- **Không có deduplication bền vững:** worker crash có thể tạo side effect trùng.
- **Đánh dấu processed trước commit:** event bị mất khi worker crash giữa các bước.
- **Exists rồi insert không nguyên tử:** hai worker có thể cùng xử lý một event.
- **Cho phép sửa payload trong DLQ:** phá vỡ bằng chứng chữ ký và provenance.
- **Queue ACL quá rộng:** service không đáng tin publish vào trusted topic.
- **Tin tenant ID trong webhook:** có thể ghi dữ liệu vào tenant khác.
- **Không kiểm soát ordering:** event cũ ghi đè trạng thái mới.
- **Retry vô hạn:** poison message chiếm queue và worker.
- **Trả 2xx trước khi enqueue bền vững:** provider không retry dù event đã mất.
- **Log raw payload/signature:** lộ PII, token hoặc dữ liệu giao dịch.

## 17. Checklist trước khi phát hành

- [ ] Chọn rõ verification tại ingress hay worker; mọi đường đến side effect đều phải qua verification.
- [ ] Raw/unverified và verified event được tách topic/schema/ACL.
- [ ] Signature được xác minh trên đúng raw bytes theo contract provider.
- [ ] Timestamp freshness và replay protection được kiểm tra ở thời điểm nhận ban đầu.
- [ ] Key rotation có overlap window, key ID allowlist và quy trình revoke.
- [ ] Trusted envelope gắn provider/account/event ID, payload hash, received-at, verified-at và policy version.
- [ ] Worker xác thực producer, broker principal và message provenance.
- [ ] Field verified không được tin nếu thiếu bằng chứng nguồn và tính toàn vẹn.
- [ ] Worker validate schema, event type, tenant mapping, object reference và state transition.
- [ ] Retry giữ nguyên payload, event ID, hash và verification provenance.
- [ ] Retry chỉ áp dụng cho lỗi tạm thời, có backoff, jitter, budget và deadline.
- [ ] Idempotency/deduplication dùng unique constraint hoặc cơ chế nguyên tử.
- [ ] Side effect, inbox state và outbox event được commit nhất quán.
- [ ] Ordering/version và event đến muộn được xử lý bằng state machine.
- [ ] DLQ có ACL, encryption, retention, audit và redrive có phê duyệt.
- [ ] Broker producer/consumer/admin permissions theo least privilege.
- [ ] Tenant được resolve từ provider mapping tin cậy, không chỉ từ payload.
- [ ] Có giới hạn request size, header, parser, queue depth và worker concurrency.
- [ ] Ingress chỉ trả success sau khi event được lưu bền vững theo contract.
- [ ] Có metric cho signature failure, retry, duplicate, DLQ, lag và mapping failure.
- [ ] Có test signature, replay, tampering, race, retry, ordering, DLQ và broker ACL.

Queue và retry giúp webhook chịu lỗi tốt hơn, nhưng không làm giảm yêu cầu xác minh. Khi hệ thống bảo toàn provenance từ raw request đến trusted event, kiểm tra message ở worker, giữ idempotency qua mọi lần delivery và quản lý DLQ/redrive như thao tác nhạy cảm, đường xử lý bất đồng bộ sẽ không trở thành lối tắt vượt qua verification.
