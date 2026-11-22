# Chính sách lưu giữ, xóa và phân loại dữ liệu

Trong chương **Quản trị và tuân thủ**, chính sách lưu giữ, xóa và phân loại dữ liệu xác định dữ liệu nào được phép thu thập, ai được truy cập, cần giữ trong bao lâu và phải xử lý ra sao khi hết mục đích sử dụng. Với ứng dụng serverless, dữ liệu không chỉ nằm trong database chính. Một request có thể tạo bản sao trong queue, DLQ, event archive, log, trace, cache, object storage, backup và hệ thống phân tích. Vì vậy, xóa một row không đồng nghĩa đã hoàn tất yêu cầu xóa trên toàn bộ hệ thống.

Bài học thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng theo mô hình serverless, đặc biệt là Java function kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Người học xử lý trigger, trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí để xác định khi nào nên dùng FaaS. Quản trị dữ liệu cần được thiết kế cùng event flow, IAM, storage, observability, backup và quy trình vận hành của function.

## 1. Mục tiêu của chính sách dữ liệu

Một chính sách dữ liệu tốt cần trả lời các câu hỏi:

- Dữ liệu nào được thu thập và vì mục đích gì?
- Dữ liệu thuộc loại công khai, nội bộ, bí mật hay nhạy cảm?
- Ai là owner chịu trách nhiệm cho dữ liệu?
- Hệ thống nào lưu bản chính và hệ thống nào giữ bản sao?
- Thời hạn lưu bắt đầu từ sự kiện nào?
- Khi hết hạn, dữ liệu được archive, anonymize hay xóa?
- Có yêu cầu pháp lý, hợp đồng hoặc legal hold ngăn việc xóa không?
- Làm sao chứng minh dữ liệu đã được xử lý theo chính sách?
- Nếu dữ liệu được sao chép qua event, log và backup thì quy trình xóa lan truyền thế nào?

Chính sách không nên chỉ là một con số TTL. Thời hạn lưu cần gắn với mục đích nghiệp vụ, nghĩa vụ pháp lý và loại dữ liệu. Mỗi loại dữ liệu có thể có mốc bắt đầu tính thời hạn khác nhau, ví dụ từ lúc tạo, lần hoạt động cuối, kết thúc hợp đồng hoặc hoàn tất giao dịch.

## 2. Phân loại dữ liệu

Phân loại dữ liệu giúp quyết định cách lưu, mã hóa, truy cập, log, chia sẻ và xóa. Một mô hình đơn giản có thể gồm bốn mức:

| Mức | Ví dụ | Biện pháp thường áp dụng |
|---|---|---|
| Public | Nội dung website đã công bố, tài liệu marketing | Kiểm soát tính toàn vẹn, quản lý phiên bản |
| Internal | Metadata vận hành, tài liệu nội bộ thông thường | IAM nội bộ, kiểm soát chia sẻ và retention |
| Confidential | Dữ liệu khách hàng, hợp đồng, thông tin kinh doanh | Least privilege, mã hóa, audit access |
| Restricted / Sensitive | PII nhạy cảm, dữ liệu thanh toán, credential, bí mật xác thực | Truy cập rất hạn chế, mã hóa mạnh, masking, giám sát và retention chặt |

Tên mức phân loại có thể khác giữa các tổ chức. Điều quan trọng là mỗi mức phải có quy tắc thực thi cụ thể, không chỉ là nhãn.

### 2.1. Phân loại theo trường dữ liệu

Một record có thể chứa nhiều trường với mức nhạy cảm khác nhau. Ví dụ order có order ID, trạng thái, số tiền, địa chỉ giao hàng và số điện thoại. Không nên gán nhãn chung rồi cho phép toàn bộ payload xuất hiện trong log.

Có thể phân loại theo field:

- Public identifier: có thể dùng trong log nếu không liên kết trực tiếp tới cá nhân.
- Internal business metadata: chỉ hiển thị cho nhân viên có nhu cầu.
- Personal data: giới hạn mục đích sử dụng và thời gian lưu.
- Sensitive personal data: yêu cầu bảo vệ cao hơn và chỉ xử lý khi có căn cứ phù hợp.
- Authentication secret: không ghi log, không đưa vào event payload nếu consumer không cần.

Khi một object chứa nhiều loại dữ liệu, mặc định áp dụng mức bảo vệ cao nhất cho toàn object hoặc tách field sang các storage/record có policy riêng.

### 2.2. Phân loại phải gắn với mục đích

Không phải cứ có thể thu thập dữ liệu là nên thu thập. Trước khi thêm field vào request, event hoặc log, hãy xác định:

- Mục đích xử lý.
- Cơ sở cho phép xử lý theo chính sách và quy định áp dụng.
- Hệ thống hoặc consumer cần field đó.
- Thời gian cần giữ.
- Có thể dùng dữ liệu tổng hợp, pseudonym hoặc reference thay cho dữ liệu gốc không?

Data minimization giảm rủi ro và chi phí. Nếu consumer chỉ cần customer ID để gọi một API được phân quyền, không gửi toàn bộ hồ sơ khách hàng qua event bus.

## 3. Data inventory và data ownership

Không thể quản lý retention nếu không biết dữ liệu đang tồn tại ở đâu. Cần duy trì inventory có thể truy vết:

| Thuộc tính | Nội dung cần ghi |
|---|---|
| Data domain | Customer, order, payment, telemetry |
| Data owner | Nhóm hoặc vai trò chịu trách nhiệm |
| Source of truth | Hệ thống giữ bản chính |
| Classification | Mức nhạy cảm |
| Purpose | Mục đích xử lý |
| Storage locations | Database, bucket, queue, log, archive |
| Consumers | Function, service, analytics job |
| Retention rule | Mốc bắt đầu và thời hạn |
| Deletion method | Hard delete, anonymize, crypto erase, expiry |
| Legal hold | Điều kiện tạm dừng xóa |
| Evidence | Audit record hoặc báo cáo xác minh |

Data owner quyết định mục đích và chính sách nghiệp vụ; platform/security team cung cấp cơ chế thực thi; application team đảm bảo code tuân thủ. Không nên giao trách nhiệm retention cho một scheduled Lambda mà không có owner và policy được phê duyệt.

### 3.1. Theo dấu dữ liệu trong serverless

Một HTTP request có thể tạo ra nhiều bản sao:

~~~mermaid
flowchart TD
    R["HTTP request"] --> F["Java Lambda"]
    F --> DB["Primary database"]
    F --> Q["Queue / Event bus"]
    F --> L["Logs and traces"]
    DB --> A["Analytics / warehouse"]
    Q --> C["Downstream consumers"]
    Q --> D["DLQ / archive"]
    DB --> B["Snapshots / backups"]
    C --> S["Search / cache / object store"]
~~~

Data inventory cần bao gồm cả bản sao phát sinh từ integration và vận hành. Một event có thể được chuyển tới nhiều consumer; mỗi consumer có thể tạo thêm projection hoặc index riêng. Xóa ở source mà không thông báo cho các consumer có thể để lại dữ liệu cũ.

## 4. Thiết kế retention schedule

Retention schedule định nghĩa dữ liệu nào được giữ bao lâu, tính từ thời điểm nào và hành động khi hết hạn.

Ví dụ cấu trúc chính sách:

| Loại dữ liệu | Mốc bắt đầu | Hành động khi hết hạn |
|---|---|---|
| Session tạm | Thời điểm tạo hoặc hoạt động cuối | Xóa |
| Request staging | Khi workflow kết thúc | Xóa hoặc giữ ngắn để retry |
| Business transaction | Khi giao dịch đóng | Archive theo nghĩa vụ áp dụng |
| Customer profile | Khi mục đích xử lý kết thúc hoặc có yêu cầu hợp lệ | Xóa hoặc anonymize theo policy |
| Application logs | Thời điểm log được tạo | Hết hạn theo log retention |
| DLQ | Khi message vào DLQ | Điều tra, redrive hoặc xóa có audit |
| Event archive | Thời điểm event được archive | Hết hạn theo retention của archive |
| Backup | Thời điểm snapshot | Xóa theo backup lifecycle |
| Security audit records | Thời điểm phát sinh | Giữ theo policy audit và nghĩa vụ áp dụng |

Bảng trên chỉ minh họa cách mô hình hóa. Không có một thời hạn chung phù hợp với mọi loại dữ liệu hoặc mọi quốc gia. Legal, privacy, security và business owner cần xác nhận thời hạn dựa trên quy định hiện hành, hợp đồng và mục đích sử dụng.

### 4.1. Xác định retention clock

Cần chỉ rõ đồng hồ retention bắt đầu khi nào:

- created_at: thời điểm record được tạo.
- last_activity_at: lần hoạt động cuối.
- transaction_closed_at: giao dịch kết thúc.
- contract_ended_at: hợp đồng hết hiệu lực.
- request_completed_at: yêu cầu hoặc workflow hoàn tất.
- archived_at: dữ liệu chuyển sang archive.

Không dùng một timestamp chung cho mọi loại record. Ví dụ, thời gian lưu hồ sơ thanh toán có thể tính từ khi giao dịch hoàn tất; thời gian lưu session có thể tính từ lần hoạt động cuối.

### 4.2. Retention theo nhiều tầng

Dữ liệu có thể đi qua hot, warm và cold storage:

- Hot: dữ liệu đang phục vụ ứng dụng, cần truy cập nhanh.
- Warm: dữ liệu ít truy cập nhưng vẫn cần tra cứu.
- Cold/archive: dữ liệu chỉ giữ vì audit hoặc nghĩa vụ lưu trữ.
- Expired: dữ liệu hết mục đích và đủ điều kiện xóa.

Chuyển sang archive không phải xóa. Archive vẫn phải có classification, encryption, IAM, retention và deletion policy. Dữ liệu lưu lâu hơn có thể vẫn có rủi ro nếu quyền truy cập không được kiểm soát.

## 5. Legal hold và ngoại lệ retention

Legal hold là yêu cầu tạm dừng xóa dữ liệu có liên quan tới tranh chấp, điều tra hoặc nghĩa vụ lưu giữ. Nó cần có phạm vi, owner, thời điểm bắt đầu, lý do và điều kiện kết thúc.

Quy trình nên:

1. Xác định chính xác data subject, record, tenant hoặc khoảng thời gian liên quan.
2. Đặt hold trên các bản sao thuộc phạm vi.
3. Ghi người phê duyệt và thời điểm.
4. Ngăn job retention xóa dữ liệu đang bị hold.
5. Tiếp tục bảo vệ dữ liệu bằng encryption và access control.
6. Gỡ hold khi có xác nhận hợp lệ.
7. Đưa dữ liệu trở lại retention workflow.

Không đặt một legal hold toàn hệ thống nếu phạm vi chỉ liên quan một tập record nhỏ. Hold quá rộng làm tăng chi phí và giữ dữ liệu lâu hơn cần thiết.

Retention job phải kiểm tra hold ở thời điểm thực thi, không chỉ lúc tạo danh sách xóa. Hold có thể được thêm sau khi job đã lập kế hoạch nhưng trước khi delete chạy.

## 6. Các kiểu xử lý khi dữ liệu hết hạn

Có nhiều cách kết thúc vòng đời dữ liệu:

| Cách xử lý | Ý nghĩa | Khi phù hợp |
|---|---|---|
| Hard delete | Xóa bản ghi hoặc object khỏi storage đang hoạt động | Khi dữ liệu không còn cần giữ |
| Soft delete | Đánh dấu deleted và ẩn khỏi luồng nghiệp vụ | Khi cần workflow phục hồi ngắn hoặc audit |
| Anonymization | Biến đổi để không còn nhận diện cá nhân theo tiêu chuẩn áp dụng | Khi vẫn cần thống kê |
| Pseudonymization | Thay định danh trực tiếp bằng mã khác, còn khả năng liên kết qua khóa riêng | Khi cần giảm exposure nhưng vẫn cần liên kết có kiểm soát |
| Archive | Chuyển sang storage lưu trữ | Khi còn nghĩa vụ hoặc nhu cầu tra cứu |
| Cryptographic erasure | Hủy khóa giải mã phù hợp để dữ liệu mã hóa không còn đọc được | Khi kiến trúc khóa hỗ trợ và đáp ứng yêu cầu |

Soft delete không phải là xóa hoàn toàn. Nếu record chỉ có cờ deleted=true nhưng vẫn xuất hiện trong API, search index, export hoặc backup, dữ liệu vẫn còn. Pseudonymization cũng không đồng nghĩa anonymization nếu vẫn có thể tái nhận diện bằng bảng ánh xạ hoặc dữ liệu khác.

### 6.1. Hard delete và cascade

Xóa một customer có thể liên quan tới order, address, preference, support ticket, search index và analytics. Không nên cascade xóa mọi record nếu một số hồ sơ cần giữ theo nghĩa vụ khác.

Cần định nghĩa theo từng domain:

- Xóa hoàn toàn.
- Giữ transaction nhưng xóa hoặc tách thông tin nhận diện.
- Giữ dữ liệu tổng hợp đã được anonymize.
- Giữ một reference tối thiểu để bảo toàn tính toàn vẹn.
- Giữ bản sao đang bị legal hold.

Quy tắc phải được phê duyệt và có thể giải thích. Không tự suy ra rằng yêu cầu xóa customer luôn đồng nghĩa xóa toàn bộ transaction history.

## 7. Quy trình xóa dữ liệu xuyên hệ thống

Một deletion workflow có thể chia thành các bước:

1. Nhận yêu cầu hoặc xác định record đã hết retention.
2. Xác thực người yêu cầu và phạm vi dữ liệu.
3. Kiểm tra legal hold và nghĩa vụ giữ lại.
4. Tìm source of truth và tất cả bản sao.
5. Ngăn phát sinh thêm dữ liệu mới trong phạm vi cần xóa.
6. Xóa, anonymize hoặc hạn chế truy cập bản chính theo policy.
7. Phát deletion event qua transactional outbox.
8. Các consumer xóa bản sao, cache, search index và projection.
9. Xử lý queue, DLQ, archive và third-party processor.
10. Xử lý backup theo lifecycle hoặc cơ chế crypto erase đã phê duyệt.
11. Đối soát kết quả và ghi audit evidence.

Không nên chạy một script xóa database rồi coi quy trình hoàn tất. Cần biết consumer nào đã nhận deletion event và hệ thống nào còn bản sao.

~~~mermaid
flowchart TD
    REQ["Deletion request / retention expiry"] --> AUTH["Verify scope and authority"]
    AUTH --> HOLD{"Legal hold?"}
    HOLD -->|"Yes"| PAUSE["Pause deletion and record hold"]
    HOLD -->|"No"| MAP["Discover copies and processors"]
    MAP --> SOURCE["Delete / anonymize source data"]
    SOURCE --> OUTBOX["Commit deletion event via outbox"]
    OUTBOX --> FAN["Notify downstream consumers"]
    FAN --> VERIFY["Verify replicas, indexes and caches"]
    VERIFY --> BACKUP["Apply backup expiry / key policy"]
    BACKUP --> AUDIT["Record evidence and close request"]
~~~

## 8. Deletion event và idempotent delete handler

Deletion event nên chứa định danh cần thiết để consumer tìm dữ liệu, không nên phát toàn bộ PII cần xóa.

Ví dụ:

~~~json
{
  "eventId": "evt-delete-901",
  "eventType": "CustomerDataDeletionRequested",
  "schemaVersion": 1,
  "requestId": "del-2026-0042",
  "subjectRef": "subject-token-7f21",
  "scope": [
    "profile",
    "preferences",
    "search-index"
  ],
  "policyVersion": "customer-retention-v3",
  "requestedAt": "2026-11-17T10:00:00Z"
}
~~~

subjectRef nên là reference opaque, không chứa email hoặc số định danh trực tiếp. Consumer cần kiểm tra quyền và scope từ workflow đã xác thực, không tin một event bất kỳ có thể yêu cầu xóa dữ liệu tùy ý.

Delete handler phải idempotent: chạy nhiều lần vẫn đưa dữ liệu về cùng trạng thái cuối. Ví dụ, xóa một cache key đã không còn tồn tại có thể được xem là thành công; nhưng cần phân biệt “không tồn tại” với “không đủ quyền truy cập”.

~~~java
public final class CustomerDeletionHandler {
    private final DeletionRepository deletions;
    private final SearchIndex searchIndex;
    private final CacheStore cache;

    public CustomerDeletionHandler(
            DeletionRepository deletions,
            SearchIndex searchIndex,
            CacheStore cache) {
        this.deletions = deletions;
        this.searchIndex = searchIndex;
        this.cache = cache;
    }

    public void handle(CustomerDeletionRequested event) {
        deletions.deleteProfileIfPresent(event.subjectRef());
        searchIndex.deleteBySubject(event.subjectRef());
        cache.evictSubject(event.subjectRef());
        deletions.markConsumerComplete(
                "customer-projection",
                event.eventId());
    }
}
~~~

Đây là ví dụ đơn giản. Trong production, mỗi bước cần trạng thái và retry riêng. Không đánh dấu consumer hoàn tất nếu một bước bắt buộc thất bại. Nếu nhiều hệ thống phải thay đổi cùng nhau, dùng workflow orchestration hoặc deletion task ledger để theo dõi tiến độ.

## 9. Tombstone ngăn dữ liệu cũ quay trở lại

Trong hệ thống event-driven, một event cũ có thể được retry hoặc replay sau khi dữ liệu đã bị xóa. Nếu consumer chỉ xóa row hiện tại, event OrderUpdated hoặc CustomerProfileChanged đến muộn có thể tạo lại dữ liệu.

Tombstone là dấu ghi nhận rằng một entity đã bị xóa hoặc bị chặn tái tạo. Tombstone có thể chứa:

- Opaque subject/entity ID.
- Thời điểm xóa.
- Policy version.
- Deletion request ID.
- Trạng thái hoàn tất.
- Phạm vi hệ thống đã xử lý.

Khi event cũ đến, consumer kiểm tra tombstone trước khi tạo hoặc cập nhật projection. Nếu entity đã bị xóa, event cũ bị bỏ qua hoặc chuyển sang luồng điều tra theo policy.

Tombstone cần được giữ đủ lâu để bao phủ retention của queue, archive, replay và backup restore. Nếu xóa tombstone quá sớm, dữ liệu cũ có thể được tái tạo.

## 10. Xóa trong queue, DLQ và event archive

Message queue và event archive có vòng đời riêng:

- Message trong queue có thể tồn tại tới retention limit của dịch vụ.
- DLQ có thể giữ bản sao của message lỗi.
- Event archive có thể cho phép replay event cũ.
- Stream có thể giữ record theo retention window.
- Consumer retry có thể tiếp tục giữ event trong thời gian dài.

Khi có yêu cầu xóa dữ liệu, cần đánh giá liệu payload chứa PII có thể được xóa trực tiếp, expire theo retention, hoặc phải được mã hóa bằng khóa riêng để có thể hủy khả năng giải mã.

Một số dịch vụ không cho phép xóa chọn lọc một event đã được append vào archive hoặc stream theo event ID. Khi đó cần phương án đã được phê duyệt: hạn chế truy cập, loại event khỏi replay, crypto erase nếu phù hợp hoặc chờ retention hết hạn. Không tuyên bố đã xóa hoàn toàn nếu bản sao vẫn còn.

### 10.1. Tránh replay dữ liệu đã xóa

Replay controller và consumer cần kiểm tra deletion ledger/tombstone. Nếu event nằm trong archive nhưng subject đã bị xóa, consumer không được tạo lại profile hoặc projection.

Nếu archive có thể chứa dữ liệu nhạy cảm, quyền replay cần được giới hạn. Replay không chỉ là quyền đọc; nó có thể tái tạo dữ liệu và side effect trên production.

## 11. Log và trace cũng là dữ liệu

Log, trace và metric có thể chứa dữ liệu cá nhân hoặc bí mật:

- Request body và response body.
- Email, phone, address hoặc access token.
- URL có query parameter nhạy cảm.
- Exception message chứa SQL hoặc payload.
- Trace attribute chứa customer ID.
- Custom metric dimension có giá trị định danh.

Quy tắc logging:

- Chỉ log field cần cho vận hành.
- Mask hoặc redact PII và secret trước khi ghi.
- Không log Authorization header, password, token hoặc raw payment data.
- Dùng correlation ID opaque để truy vết.
- Đặt retention riêng cho từng log group.
- Hạn chế quyền đọc log và audit truy cập.
- Không dùng PII làm metric dimension có cardinality cao.

Log retention không thay thế data retention của hồ sơ nghiệp vụ. Ngược lại, dữ liệu trong log vẫn cần được phân loại và có thời hạn lưu riêng.

### 11.1. Java logging an toàn

Ví dụ log metadata thay vì toàn bộ request:

~~~java
public void handle(CreateOrderRequest request) {
    logger.info(
            "CreateOrder received: correlationId={}, itemCount={}",
            request.correlationId(),
            request.items().size());

    orderService.create(request);
}
~~~

Không ghi trực tiếp request object vì nó có thể chứa địa chỉ, thông tin khách hàng hoặc token. Nếu cần điều tra payload, lưu ở nơi kiểm soát quyền và retention riêng, có mã hóa và audit.

Với logging framework, có thể xây dựng redaction filter hoặc structured logging encoder để lọc field nhạy cảm tập trung. Tuy nhiên, filter không thay thế trách nhiệm không đưa secret vào message ngay từ đầu.

## 12. CloudWatch Logs và retention rõ ràng

Nếu không đặt retention, log group có thể lưu lâu hơn dự kiến theo mặc định dịch vụ. Với CloudWatch Logs, khai báo retention trong IaC để mọi môi trường có cấu hình nhất quán.

Ví dụ CloudFormation:

~~~yaml
Resources:
  OrdersFunctionLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: /aws/lambda/orders-function
      RetentionInDays: 90
~~~

90 ngày chỉ là giá trị minh họa, không phải khuyến nghị chung. Chọn theo nhu cầu vận hành, security investigation và nghĩa vụ lưu trữ đã được phê duyệt. Cần bảo đảm quyền tạo log group và retention được cấu hình đúng trong cả trường hợp function tạo log group tự động.

Nếu log được export sang S3, SIEM hoặc data lake, retention của bản export cần được quản lý riêng. Xóa log group không tự xóa bản export hoặc bản sao trong hệ thống quan sát khác.

## 13. DynamoDB TTL và giới hạn của tự động hết hạn

DynamoDB TTL có thể xóa item khi thuộc tính TTL chứa Unix epoch time đã qua. Ví dụ item có trường expiresAtEpochSeconds.

~~~json
{
  "PK": "SESSION#session-123",
  "expiresAtEpochSeconds": 1794916800,
  "status": "EXPIRED"
}
~~~

TTL giúp dọn dữ liệu tạm mà không cần scheduled scan/delete cho từng item. Tuy nhiên:

- TTL deletion là bất đồng bộ, không xảy ra chính xác tại thời điểm timestamp.
- Item quá hạn có thể vẫn đọc được trước khi service xóa.
- TTL không thay thế authorization hoặc kiểm tra expiry trong ứng dụng.
- TTL không tự xóa bản sao ở search index, cache, queue hoặc backup.
- TTL không phải cơ chế đáp ứng deadline xóa nghiêm ngặt nếu yêu cầu đòi hỏi xác nhận tức thời.

Nếu session hết hạn lúc 12:00, ứng dụng phải từ chối session dựa trên expiresAt dù item chưa bị TTL xóa. TTL chỉ là cleanup.

## 14. S3 Lifecycle, versioning và object deletion

S3 Lifecycle có thể chuyển object sang storage class khác hoặc hết hạn theo rule. Nhưng cần xem xét:

- Bucket có bật versioning không?
- Delete marker có được tạo thay vì xóa version cũ không?
- Noncurrent versions có retention rule riêng không?
- Có Object Lock hoặc legal hold không?
- Replication destination có giữ bản sao không?
- Object đã được export hoặc copy sang bucket khác chưa?
- Multipart upload dang dở có cần cleanup không?

Trong bucket versioned, xóa object hiện tại có thể chỉ tạo delete marker; các object version trước vẫn tồn tại. Muốn xóa thực sự cần xử lý các version theo policy và kiểm tra Object Lock/legal hold.

Lifecycle action là cơ chế quản lý vòng đời, không nên coi là thao tác xóa đồng bộ chính xác tới từng giây. Nếu cần chứng minh hoàn tất deletion, cần quy trình kiểm tra và audit phù hợp.

## 15. Backup, snapshot và phục hồi sau restore

Backup tạo ra một bản sao dữ liệu độc lập. Một record bị xóa khỏi database đang hoạt động có thể vẫn tồn tại trong snapshot hoặc backup trước đó.

Chính sách phải xác định:

- Backup được giữ trong bao lâu.
- Ai có quyền restore.
- Backup có mã hóa và key riêng không.
- Khi restore, làm sao áp dụng các yêu cầu xóa đã nhận sau thời điểm snapshot.
- Backup nào có thể bị legal hold.
- Khi nào backup hết hạn hoặc bị tiêu hủy.

Một cách phổ biến là duy trì deletion ledger/tombstone bền vững. Sau khi restore backup cũ, chạy lại ledger để áp dụng các yêu cầu xóa đã hoàn tất sau thời điểm backup. Nếu không, dữ liệu đã xóa có thể xuất hiện trở lại.

Không hứa xóa ngay khỏi mọi backup nếu kiến trúc chỉ xóa theo chu kỳ backup expiry. Cần mô tả chính xác thời hạn và ngoại lệ trong chính sách.

## 16. Cryptographic erasure và quản lý khóa

Cryptographic erasure là cách làm dữ liệu không thể giải mã bằng cách hủy khóa mã hóa cần thiết. Cách này chỉ có ý nghĩa khi:

- Dữ liệu đã được mã hóa bằng khóa phù hợp.
- Khóa hoặc data encryption key không còn bản sao có thể sử dụng.
- Backup không chứa bản plaintext hoặc bản sao khóa ngoài kiểm soát.
- Key hierarchy được thiết kế để hủy đúng phạm vi dữ liệu cần xóa.
- Việc hủy khóa không làm mất dữ liệu khác cần giữ.

Nếu nhiều khách hàng dùng chung một KMS key, hủy key có thể làm mất khả năng giải mã dữ liệu của tất cả khách hàng. Để xóa theo subject, cần kiến trúc key granularity phù hợp, ví dụ data key theo tenant hoặc đối tượng và quản lý wrapping key an toàn.

Hủy KMS key có thể có thời gian chờ và trạng thái scheduled deletion; không nên mô tả là thao tác tức thời. Crypto erase cũng không thay thế việc xóa metadata, index và các bản plaintext.

## 17. Event sourcing và dữ liệu append-only

Trong event-sourced system, trạng thái hiện tại được tái dựng từ event log. Xóa một event có thể phá vỡ khả năng replay và audit. Cần xác định cách xử lý theo yêu cầu:

- Xóa hoặc mã hóa phần dữ liệu nhận diện khỏi event payload nếu kiến trúc cho phép.
- Tách PII khỏi event bất biến, chỉ lưu reference.
- Dùng encryption key riêng cho subject để hỗ trợ crypto erase.
- Tạo redaction event hoặc tombstone để projection không hiển thị dữ liệu.
- Rebuild projection sau khi áp dụng deletion policy.
- Giữ lại record tối thiểu nếu có nghĩa vụ pháp lý, có access control và retention riêng.

Redaction event không tự xóa PII khỏi event cũ. Nếu payload gốc vẫn có thể đọc, dữ liệu vẫn tồn tại. Thiết kế event contract từ đầu để tránh nhúng dữ liệu cá nhân không cần thiết vào event dài hạn.

## 18. Retention và deletion trong workflow serverless

Workflow có thể chạy qua nhiều function và kéo dài hơn một invocation. Mỗi bước có thể tạo execution history, payload, retry record hoặc output.

Cần xem xét:

- Step Functions execution history và input/output có chứa PII không.
- SQS message và DLQ có giữ payload bao lâu.
- EventBridge archive có lưu event nhạy cảm không.
- Kinesis/Kafka retention có đủ cho retry/replay không.
- Lambda /tmp có lưu file nhạy cảm qua warm invocation không.
- Extension, layer hoặc container image có vô tình chứa test data/secret không.
- X-Ray trace và log có chứa request field không.
- Snapshot database và object storage có lifecycle riêng không.

Lambda execution environment có thể được tái sử dụng. File trong /tmp có thể còn tồn tại giữa các invocation trên cùng environment. Không lưu dữ liệu nhạy cảm ở đó nếu không cần; nếu buộc phải dùng, đặt tên file theo request, giới hạn quyền, xóa sau xử lý theo best effort và không dựa vào việc environment sẽ bị hủy ngay.

Không giữ dữ liệu cá nhân trong static cache của Java nếu không có mục đích rõ và giới hạn TTL/size. Execution environment có thể xử lý request tiếp theo; cache phải tránh rò rỉ dữ liệu giữa tenant hoặc user.

## 19. Data retention trong cache và search index

Cache thường bị bỏ sót trong deletion workflow. Khi xóa dữ liệu gốc, cache có thể vẫn trả kết quả cũ cho đến khi TTL hết.

Nên:

- Dùng cache key có scope tenant/subject.
- Phát invalidation event khi record bị xóa hoặc thay đổi.
- Dùng TTL phù hợp nhưng không dựa vào TTL để đáp ứng yêu cầu xóa khẩn.
- Có cơ chế xóa theo subject hoặc namespace.
- Tránh cache raw PII nếu chỉ cần cache reference.
- Xác minh search index và materialized view đã cập nhật.

Search index có thể lưu bản sao document, tokenized field và metadata. Xóa document trong database không tự xóa index. Deletion consumer cần biết index nào chứa entity và xác nhận thao tác thành công.

## 20. Third-party processor và data sharing

Dữ liệu có thể được gửi tới email provider, analytics, payment processor, CRM hoặc hệ thống support. Data inventory cần ghi rõ:

- Processor nhận loại dữ liệu nào.
- Mục đích chia sẻ.
- Cơ chế truyền và mã hóa.
- Retention của processor.
- Cách gửi yêu cầu xóa/correction.
- Thời gian phản hồi và bằng chứng hoàn tất.
- Subprocessor hoặc bản sao do processor quản lý.

Deletion workflow nội bộ không tự xóa dữ liệu tại bên thứ ba. Cần API hoặc quy trình hỗ trợ từ processor, theo dõi request ID và trạng thái. Nếu processor không hỗ trợ xóa chọn lọc, phải ghi nhận giới hạn và xử lý theo hợp đồng/quy định được áp dụng.

## 21. Tự động hóa retention bằng policy as code

Retention policy nên được biểu diễn thành cấu hình có version và owner, thay vì hardcode nhiều con số rải rác trong Lambda.

Ví dụ cấu hình khái niệm:

~~~yaml
dataPolicies:
  - category: temporary-session
    classification: internal
    retention:
      anchor: lastActivityAt
      duration: P30D
    action: delete

  - category: application-log
    classification: confidential
    retention:
      anchor: createdAt
      duration: P90D
    action: expire

  - category: customer-profile
    classification: restricted
    retention:
      anchor: purposeEndedAt
      duration: APPROVED_DURATION
    action: review-and-delete
~~~

Các duration P30D và P90D chỉ minh họa định dạng ISO-8601, không phải thời hạn pháp lý được khuyến nghị. APPROVED_DURATION là placeholder cần được thay bằng thời hạn do data owner và bộ phận phụ trách phê duyệt. Legal hold được kiểm tra riêng tại thời điểm thực thi retention/deletion, không nên biểu diễn bằng một cờ cho biết loại dữ liệu có hỗ trợ hold hay không.

Policy engine hoặc retention service có thể đọc cấu hình và tạo deletion task. Cần version policy để biết record được đánh giá theo quy tắc nào. Thay đổi retention phải có review và audit vì có thể làm dữ liệu bị xóa sớm hoặc giữ quá lâu.

### 21.1. Scheduled cleanup an toàn

Một scheduled Lambda có thể tìm record đã hết hạn:

~~~sql
SELECT record_id, tenant_id
FROM temporary_session
WHERE expires_at <= CURRENT_TIMESTAMP
  AND deletion_status = 'ACTIVE'
ORDER BY expires_at
LIMIT :batch_size;
~~~

Sau đó, mỗi record cần được xử lý với điều kiện chống race:

- Kiểm tra legal hold ở thời điểm xóa.
- Claim record hoặc dùng conditional update.
- Xóa/anonymize trong transaction phù hợp.
- Ghi deletion audit.
- Phát event cho downstream qua outbox.
- Retry phần thất bại mà không xóa nhầm record mới được gia hạn.

Không chạy một lệnh DELETE lớn trên toàn bảng nếu nó tạo lock, tải hoặc replication lag. Dùng batch nhỏ, rate limit và quan sát database.

## 22. Java model cho retention policy

Có thể mô hình hóa retention rule trong code nhưng thời hạn nên được cấu hình từ policy đã phê duyệt:

~~~java
import java.time.Duration;
import java.time.Instant;

public record RetentionRule(
        String category,
        Duration duration,
        Anchor anchor,
        ExpiryAction action) {

    public Instant expiresAt(Instant anchorTime) {
        return anchorTime.plus(duration);
    }

    public enum Anchor {
        CREATED_AT,
        LAST_ACTIVITY_AT,
        PURPOSE_ENDED_AT
    }

    public enum ExpiryAction {
        DELETE,
        ANONYMIZE,
        ARCHIVE,
        REVIEW
    }
}
~~~

Ví dụ này biểu diễn rule đơn giản. Production cần hỗ trợ legal hold, policy version, timezone semantics, ngoại lệ theo jurisdiction và audit. Không dùng duration từ request của user để quyết định retention; chỉ policy được quản trị mới được phép xác định thời hạn.

### 22.1. Không xóa chỉ dựa trên timestamp từ client

Client có thể gửi timestamp sai hoặc bị chỉnh sửa. Retention anchor phải do hệ thống tin cậy ghi nhận, ví dụ database commit time hoặc thời điểm workflow hoàn tất đã được xác thực. Nếu dùng lastActivityAt, cập nhật timestamp cần kiểm soát để user không thể kéo dài retention trái policy.

## 23. Audit evidence và xác minh deletion

Một deletion request nên có record theo dõi:

- Request ID.
- Subject reference hoặc record scope.
- Policy version.
- Người/hệ thống khởi tạo.
- Thời điểm xác thực và phê duyệt.
- Legal hold result.
- Các hệ thống đã nhận deletion event.
- Trạng thái từng consumer.
- Kết quả backup/archive handling.
- Thời điểm hoàn tất hoặc lý do chưa hoàn tất.

Không lưu lại chính dữ liệu nhạy cảm đã xóa trong audit log. Audit nên giữ metadata đủ chứng minh quy trình đã chạy, không tái tạo dữ liệu cần xóa.

Deletion workflow có thể có trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> VERIFIED
    VERIFIED --> ON_HOLD
    VERIFIED --> IN_PROGRESS
    ON_HOLD --> VERIFIED
    IN_PROGRESS --> PARTIAL
    PARTIAL --> IN_PROGRESS
    IN_PROGRESS --> COMPLETED
    COMPLETED --> [*]
~~~

COMPLETED chỉ được đặt khi mọi hệ thống bắt buộc trong scope đã xác nhận hoặc đã đạt trạng thái xử lý được policy chấp nhận, ví dụ bản sao trong backup sẽ hết hạn theo lịch đã công bố. Không đánh dấu hoàn tất chỉ vì deletion event đã được publish.

## 24. Kiểm thử retention và deletion

Các tình huống cần kiểm thử:

- Record hết hạn được xử lý đúng policy.
- Record chưa hết hạn không bị xóa.
- Legal hold ngăn deletion job.
- Hold được thêm sau khi job tạo candidate nhưng trước khi xóa.
- Duplicate deletion event không gây lỗi hoặc side effect phụ.
- Consumer lỗi giữa chừng có thể retry.
- Search index, cache và projection được xóa.
- Event cũ không tái tạo entity đã bị tombstone.
- Restore backup áp dụng deletion ledger.
- S3 versioning và delete marker được xử lý đúng.
- DynamoDB TTL không bị nhầm là xóa tức thời.
- Log và trace không chứa PII ngoài policy.
- /tmp hoặc cache Java không làm lộ dữ liệu giữa invocation.
- Processor bên thứ ba nhận và xác nhận yêu cầu xóa.

Integration test nên kiểm tra trạng thái thật ở database, queue, object storage và index trong môi trường riêng. Mock chỉ kiểm tra lời gọi method, không chứng minh dữ liệu đã biến mất khỏi mọi bản sao.

## 25. Những lỗi thường gặp

**Chỉ xóa database chính:** Bản sao còn trong queue, log, cache, search index hoặc backup. Dùng inventory và deletion workflow xuyên hệ thống.

**Coi soft delete là xóa hoàn toàn:** Record vẫn còn và có thể xuất hiện trong export hoặc API. Định nghĩa rõ trạng thái và thời hạn hard delete.

**Dùng TTL như deadline xóa:** Cleanup thường bất đồng bộ. Ứng dụng phải kiểm tra expiry và có quy trình xác minh riêng.

**Không xử lý S3 object version:** Delete marker không xóa các version cũ. Kiểm tra versioning, lifecycle và Object Lock.

**Không xử lý log và trace:** PII vẫn còn trong observability platform. Redact trước khi ghi và đặt retention riêng.

**Quên DLQ và event archive:** Payload cũ có thể được replay. Kiểm soát quyền replay, retention và tombstone.

**Xóa tombstone quá sớm:** Event cũ có thể tái tạo dữ liệu. Giữ tombstone đủ lâu theo toàn bộ replay horizon.

**Restore backup làm dữ liệu quay lại:** Backup cũ chứa record đã xóa. Áp dụng deletion ledger sau restore.

**Legal hold không được kiểm tra ở thời điểm xóa:** Job có thể xóa record vừa được hold. Kiểm tra lại trong transaction hoặc trước thao tác cuối.

**Gửi PII trong deletion event:** Thêm bản sao nhạy cảm vào broker. Dùng opaque reference và scope tối thiểu.

**Giữ dữ liệu trong Lambda /tmp hoặc static cache:** Environment tái sử dụng có thể giữ dữ liệu qua invocation. Giới hạn, cô lập và cleanup dữ liệu tạm.

**Không có owner và policy version:** Không biết ai phê duyệt thời hạn và quy tắc nào được áp dụng. Quản lý owner, version và audit.

## 26. Checklist production

- [ ] Có data inventory bao gồm database, queue, DLQ, archive, logs, traces, cache, backup và third-party processors.
- [ ] Mỗi data category có owner, purpose và classification.
- [ ] Mỗi loại dữ liệu có retention anchor và duration đã phê duyệt.
- [ ] Legal hold có scope, owner, audit và kiểm tra trước khi xóa.
- [ ] Hard delete, soft delete, anonymization và pseudonymization được phân biệt rõ.
- [ ] Deletion workflow có xác thực yêu cầu và idempotency.
- [ ] Deletion event không chứa PII không cần thiết.
- [ ] Outbox bảo đảm deletion request được phát sau commit.
- [ ] Consumer downstream xóa cache, index và projection.
- [ ] Tombstone ngăn event cũ tái tạo dữ liệu.
- [ ] Queue, DLQ, stream và archive có retention/replay policy.
- [ ] CloudWatch Logs có retention rõ ràng.
- [ ] DynamoDB TTL không được dùng thay kiểm tra expiry.
- [ ] S3 versioning, lifecycle và Object Lock được kiểm tra.
- [ ] Backup restore có bước áp dụng deletion ledger.
- [ ] Crypto erase chỉ dùng khi key architecture đáp ứng phạm vi xóa.
- [ ] Lambda /tmp, static cache và log không giữ PII ngoài policy.
- [ ] Third-party processor có quy trình xóa và bằng chứng.
- [ ] Audit evidence không lưu lại dữ liệu nhạy cảm đã xóa.
- [ ] Có metric cho deletion backlog, partial failure và oldest pending request.
- [ ] Có integration test cho hold, retry, replay, backup restore và downstream copies.

## Kết luận

Chính sách lưu giữ, xóa và phân loại dữ liệu phải bao phủ toàn bộ vòng đời và mọi bản sao của dữ liệu. Phân loại xác định mức bảo vệ; retention schedule xác định thời gian và mốc tính; legal hold kiểm soát ngoại lệ; deletion workflow bảo đảm yêu cầu được lan truyền tới database, queue, archive, log, cache, backup và processor bên ngoài.

Trong serverless, cần đặc biệt chú ý event payload, DLQ, replay, CloudWatch Logs, DynamoDB TTL, S3 versioning, Lambda /tmp và execution environment được tái sử dụng. TTL và lifecycle là cơ chế hỗ trợ dọn dẹp, không thay thế policy hay xác minh. Java function nên dùng deletion event idempotent, transactional outbox, tombstone và audit ledger để xóa có kiểm soát mà không làm dữ liệu cũ xuất hiện trở lại.

