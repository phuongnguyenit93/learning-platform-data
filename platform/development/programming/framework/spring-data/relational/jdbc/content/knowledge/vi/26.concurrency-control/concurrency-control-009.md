# Idempotency và ràng buộc duy nhất cho yêu cầu ghi lặp

Trong **Spring Data Relational JDBC**, một yêu cầu ghi có thể được gửi nhiều lần dù người dùng chỉ thực hiện một hành động. Ví dụ, client gửi yêu cầu tạo đơn hàng nhưng mạng bị ngắt trước khi nhận response. Client không biết server đã commit hay chưa nên gửi lại request. Nếu mỗi lần nhận request đều tạo ra một đơn mới, một hành động của người dùng sẽ tạo ra nhiều hiệu ứng nghiệp vụ.

**Idempotency** là cách thiết kế để một thao tác được gửi lặp lại với cùng định danh yêu cầu chỉ tạo ra một hiệu ứng nghiệp vụ. **Ràng buộc duy nhất (unique constraint)** trong database là lớp bảo vệ quan trọng để xử lý cả các request đồng thời. Kiểm tra bằng Java trước khi insert không đủ an toàn vì hai transaction có thể cùng thấy “chưa tồn tại” rồi cùng ghi.

Trong Spring Data JDBC, có thể lưu idempotency key cùng kết quả xử lý trong database, đặt thao tác đó và thay đổi aggregate trong một transaction, rồi dùng unique constraint để database phân xử khi có request trùng. Bài học giải thích cách thiết kế key, request fingerprint, transaction, retry, replay kết quả, xung đột và phối hợp với outbox cho side effect bên ngoài database.

## 1. Vì sao request ghi có thể bị gửi lặp?

Một request có thể được gửi lại vì:

- Client timeout trong khi server vẫn đang xử lý.
- Server đã commit nhưng response bị mất trên đường truyền.
- Gateway hoặc load balancer retry request.
- Người dùng bấm nút nhiều lần.
- Message broker giao lại message sau khi consumer chưa xác nhận.
- Worker khởi động lại sau khi không biết lần xử lý trước đã hoàn thành chưa.

Ví dụ:

~~~text
Client                  Server                  Database
  |                        |                        |
  | POST /orders           |                        |
  |----------------------->| INSERT order           |
  |                        |----------------------->|
  |                        | COMMIT                 |
  |                        |<-----------------------|
  |       response mất     |                        |
  |        X               |                        |
  | timeout                |                        |
  |                        |                        |
  | retry POST /orders     |                        |
  |----------------------->| INSERT order lần nữa   |
~~~

Server không thể kết luận request retry là một hành động mới chỉ vì nó nhận thêm một HTTP request. Client cần gửi lại một định danh ổn định cho cùng một thao tác, ví dụ header `Idempotency-Key`.

## 2. Idempotency nghĩa là gì?

Một thao tác idempotent có tính chất: thực hiện một lần hay nhiều lần với cùng đầu vào và cùng định danh thao tác đều dẫn đến cùng hiệu ứng nghiệp vụ cuối cùng.

Ví dụ:

- Tạo đơn hàng với cùng idempotency key chỉ tạo một đơn.
- Gửi lại yêu cầu thanh toán với cùng key không tạo thêm một lần ghi nhận thanh toán.
- Consumer nhận lại cùng event ID không xử lý hiệu ứng nghiệp vụ lần thứ hai.
- Cập nhật một thuộc tính thành giá trị cụ thể, như đặt trạng thái thành `CANCELLED`, có thể idempotent nếu các quy tắc chuyển trạng thái được thiết kế phù hợp.

Idempotency không có nghĩa mọi request giống nội dung đều phải được gộp. Hai yêu cầu tạo hai đơn hàng khác nhau có thể có body giống hệt nhưng là hai hành động hợp lệ. Vì vậy, cần định danh thao tác bằng key do client tạo hoặc một business identifier có semantics rõ.

### 2.1. Idempotency khác với HTTP method

HTTP định nghĩa PUT và DELETE có semantics idempotent theo giao thức, còn POST thường không được xem là idempotent mặc định. Tuy nhiên, ứng dụng vẫn cần thiết kế hành vi cụ thể:

- PUT đặt resource về trạng thái đã chỉ định thường có thể lặp lại.
- DELETE cùng resource có thể trả kết quả khác nhau ở lần sau nhưng hiệu ứng cuối cùng vẫn là resource không còn.
- POST tạo đơn hoặc ghi nhận thanh toán thường cần idempotency key nếu client có thể retry.

Chỉ dùng một HTTP method không tự tạo ra cơ chế deduplication trong database.

### 2.2. Idempotency không phải exactly-once toàn hệ thống

Mạng, message broker và service có thể giao request/message nhiều lần. Idempotency giúp xử lý delivery lặp mà vẫn giữ hiệu ứng nghiệp vụ một lần trong phạm vi được bảo vệ. Không nên hứa hẹn exactly-once end-to-end chỉ dựa vào một unique key ở một database.

Mô hình thực tế thường là delivery at-least-once kết hợp với xử lý idempotent và lưu dấu kết quả đã xử lý.

## 3. Idempotency key

Idempotency key là định danh duy nhất cho một lần thực hiện nghiệp vụ. Client tạo key trước khi gửi request và giữ nguyên key khi retry cùng thao tác.

Ví dụ header:

~~~http
POST /api/orders
Idempotency-Key: 8c2e6e6a-8f7d-4e7c-a8ef-8f5f14d2f9f1
Content-Type: application/json
~~~

Nếu client timeout và gửi lại đúng yêu cầu, nó gửi lại cùng key. Khi người dùng bắt đầu một thao tác tạo đơn mới, client tạo key mới.

### 3.1. Phạm vi key

Không nên mặc định key là duy nhất trên toàn hệ thống. Có thể đặt unique scope theo:

- Tenant hoặc account.
- Tên operation/endpoint.
- Idempotency key.

Ví dụ:

~~~sql
UNIQUE (tenant_id, operation, idempotency_key)
~~~

Như vậy, hai tenant có thể dùng cùng chuỗi key mà không xung đột, và cùng một key ở hai loại thao tác khác nhau có thể được phân biệt nếu hợp đồng cho phép.

Key cần có giới hạn độ dài, định dạng được chấp nhận và thời gian lưu giữ phù hợp. Không dùng thông tin nhạy cảm như access token hoặc mật khẩu làm key.

### 3.2. Ai tạo key?

Với HTTP API, client thường tạo UUID ngẫu nhiên hoặc một token đủ entropy. Server xác thực key, kiểm tra độ dài và ghép nó với tenant/operation để xác định phạm vi.

Với message consumer, message ID hoặc event ID ổn định có thể đóng vai trò idempotency key. Producer phải giữ nguyên event ID khi giao lại cùng message.

## 4. Ràng buộc duy nhất là trọng tài dưới concurrency

Một cách sai thường gặp:

~~~java
if (!receiptRepository.existsByKey(key)) {
    receiptRepository.save(new Receipt(key));
    orderRepository.save(order);
}
~~~

Hai request có thể chạy đồng thời:

~~~text
Transaction A                  Transaction B
-------------                  -------------
SELECT key -> absent
                               SELECT key -> absent
INSERT receipt
                               INSERT receipt
INSERT order
                               INSERT order
COMMIT
                               COMMIT
~~~

Nếu không có unique constraint, cả hai transaction có thể tạo receipt và order trùng nhau. Đây là race condition kiểu check-then-act: kết quả kiểm tra đã cũ ngay khi một transaction khác thay đổi database.

Tạo unique constraint:

~~~sql
CREATE TABLE idempotency_record (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    operation VARCHAR(80) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    request_hash CHAR(64) NOT NULL,
    state VARCHAR(20) NOT NULL,
    resource_id BIGINT,
    response_status INTEGER,
    response_body TEXT,
    created_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    CONSTRAINT uk_idempotency_scope
        UNIQUE (tenant_id, operation, idempotency_key)
);
~~~

Database sẽ chỉ cho phép một hàng trong cùng scope. Nếu hai transaction đồng thời insert cùng key, unique index sẽ phân xử: một insert thành công; insert còn lại phải chờ hoặc nhận xung đột theo hành vi của database. Vì thế, unique constraint mới là lớp bảo vệ cuối cùng; exists chỉ có thể là tối ưu phụ, không phải cơ chế đảm bảo duy nhất.

## 5. Idempotency key và business unique key là hai thứ khác nhau

Hai loại unique constraint giải quyết hai quy tắc khác nhau:

| Loại | Ví dụ | Bảo vệ điều gì? |
| --- | --- | --- |
| Idempotency key | (tenant_id, operation, idempotency_key) | Cùng một lần gửi yêu cầu không tạo hiệu ứng lặp |
| Business unique key | order_number, provider_payment_id, external_reference | Không tạo hai bản ghi đại diện cho cùng một thực thể/sự kiện nghiệp vụ |

Ví dụ, hai request có idempotency key khác nhau vẫn có thể cùng chứa external_reference của một đơn hàng từ hệ thống đối tác. Business unique constraint ngăn tạo hai đơn cho cùng reference đó.

Ngược lại, hai request cùng idempotency key nhưng body khác nhau cần được phát hiện bằng request fingerprint. Unique key chỉ cho biết key đã được dùng; nó không chứng minh request mới có cùng ý nghĩa với request ban đầu.

Trong hệ thống quan trọng, thường cần cả idempotency key lẫn business unique constraint.

## 6. Request fingerprint: phát hiện key bị tái sử dụng sai

Khi lưu idempotency record, lưu thêm hash của nội dung nghiệp vụ đã chuẩn hóa:

~~~text
request_hash = SHA-256(canonical request representation)
~~~

Fingerprint giúp phân biệt:

- Cùng key, cùng nội dung: retry hợp lệ, replay kết quả cũ.
- Cùng key, nội dung khác: client dùng lại key cho một hành động khác; trả conflict.

Ví dụ:

~~~text
Lần đầu:
  key = K-123
  body = {customerId: 7, items: [{sku: "A", qty: 2}]}
  hash = H1

Retry:
  key = K-123
  body = {customerId: 7, items: [{sku: "A", qty: 2}]}
  hash = H1  -> replay

Tái sử dụng sai:
  key = K-123
  body = {customerId: 7, items: [{sku: "A", qty: 5}]}
  hash = H2  -> conflict
~~~

Không nên hash JSON thô nếu thứ tự key, format số, whitespace hoặc cách biểu diễn tương đương có thể thay đổi giữa các lần gửi. Hãy canonicalize request theo schema API, chẳng hạn sắp xếp key, chuẩn hóa giá trị và chỉ đưa các field có ý nghĩa nghiệp vụ vào hash.

Không đưa dữ liệu ngẫu nhiên do server tự sinh vào fingerprint trước khi xử lý. Cần xác định rõ những field nào làm thay đổi ý nghĩa command.

## 7. Lưu receipt cùng thao tác nghiệp vụ trong một transaction

Với một command chỉ ghi database và hoàn thành nhanh, cách đơn giản là lưu idempotency record, thay đổi aggregate và lưu kết quả trong **cùng một transaction**:

~~~text
BEGIN
  INSERT idempotency_record (scope, key, hash, state)
  INSERT purchase_order
  INSERT order_line ...
  UPDATE idempotency_record
      SET state = COMPLETED,
          resource_id = ...,
          response_body = ...
COMMIT
~~~

Nếu bất kỳ bước nào thất bại, toàn bộ transaction rollback. Không có receipt hoàn tất mà thiếu đơn hàng, cũng không có đơn hàng được commit nhưng không có receipt nếu cả hai dùng cùng transaction.

### 7.1. Entity receipt

Ví dụ entity Spring Data JDBC:

~~~java
@Table("idempotency_record")
public class IdempotencyRecord {

    @Id
    private Long id;

    private String tenantId;
    private String operation;
    private String idempotencyKey;
    private String requestHash;
    private String state;
    private Long resourceId;
    private Integer responseStatus;
    private String responseBody;
    private LocalDateTime createdAt;
    private LocalDateTime completedAt;
}
~~~

Repository:

~~~java
public interface IdempotencyRecordRepository
        extends CrudRepository<IdempotencyRecord, Long> {

    Optional<IdempotencyRecord>
    findByTenantIdAndOperationAndIdempotencyKey(
            String tenantId,
            String operation,
            String idempotencyKey
    );
}
~~~

Tên property Java cần được ánh xạ sang cột snake_case theo naming strategy hoặc khai báo `@Column` nếu schema dùng tên khác. Unique constraint vẫn được khai báo ở database; không thể chỉ dựa vào tên method repository để bảo đảm uniqueness.

### 7.2. Ghi receipt trước, rồi mới ghi aggregate

Trong transaction:

1. Insert receipt với key và request hash.
2. Tạo và lưu aggregate root.
3. Ghi child rows qua aggregate repository.
4. Lưu resource ID và response snapshot vào receipt.
5. Commit.

Thứ tự này bảo đảm unique constraint được kiểm tra trước khi tạo hiệu ứng nghiệp vụ. Nếu insert receipt bị duplicate, transaction hiện tại không được tiếp tục tạo đơn.

### 7.3. Lưu kết quả để replay

Chỉ lưu key là chưa đủ nếu API cần trả lại response giống lần đầu. Có thể lưu:

- HTTP status.
- Resource ID.
- Response body đã serialize.
- Các header cần thiết, nếu contract yêu cầu.
- Thời điểm hoàn thành.

Nếu chỉ lưu resource ID rồi đọc trạng thái hiện tại của resource ở lần retry, response có thể khác response ban đầu vì resource đã thay đổi. Hãy quyết định API cần replay response snapshot hay chỉ cần trả lại định danh resource.

Không lưu thông tin bí mật hoặc dữ liệu không cần thiết vào receipt. Nếu lưu response body, áp dụng chính sách bảo vệ và thời gian lưu giữ tương ứng.

## 8. Xử lý request trùng và replay kết quả

Khi insert receipt thất bại do unique key:

1. Transaction ghi lần retry phải rollback hoặc kết thúc đúng cách.
2. Đọc receipt đã commit bằng một transaction/read operation mới.
3. So sánh request hash.
4. Nếu hash giống và receipt hoàn tất, trả lại kết quả đã lưu.
5. Nếu hash khác, trả lỗi conflict vì key đã được dùng cho nội dung khác.

Pseudo-flow:

~~~text
Receive request(key, command)
        |
        v
Compute canonical request hash
        |
        v
Try transaction:
  insert receipt with unique key
  write aggregate
  store completed response
  commit
        |
        +-- success --> return new response
        |
        +-- duplicate key
                |
                v
          transaction has ended/rolled back
                |
                v
          load existing receipt
                |
          +-----+------+
          |            |
       same hash    different hash
          |            |
       replay       conflict
       response
~~~

### 8.1. Không bắt duplicate rồi tiếp tục trong transaction đã lỗi

Một unique violation có thể khiến transaction bị đánh dấu rollback-only hoặc database chuyển transaction sang trạng thái lỗi. Ví dụ PostgreSQL yêu cầu rollback transaction sau một lỗi SQL thông thường trước khi tiếp tục câu lệnh khác.

Vì vậy, không nên bắt duplicate exception bên trong cùng transaction rồi lập tức query receipt và tiếp tục như thể transaction vẫn khỏe. Hãy để transaction thất bại và kết thúc; sau đó đọc receipt trong transaction khác.

Một cấu trúc dễ hiểu là facade không có transaction bao ngoài gọi một bean thực thi command có `@Transactional`, rồi bắt duplicate exception sau khi proxy đã rollback transaction:

~~~java
@Service
public class CreateOrderAttempt {

    @Transactional
    public CreateOrderResult execute(
            String tenantId,
            String key,
            String requestHash,
            CreateOrderCommand command
    ) {
        // Insert receipt, save aggregate, mark receipt complete.
        // Unique violation phải thoát khỏi method này.
        return ...;
    }
}
~~~

Facade:

~~~java
@Service
public class IdempotentOrderService {

    private final CreateOrderAttempt attempt;
    private final IdempotencyReplayService replay;

    public IdempotentOrderService(
            CreateOrderAttempt attempt,
            IdempotencyReplayService replay
    ) {
        this.attempt = attempt;
        this.replay = replay;
    }

    public CreateOrderResult create(
            String tenantId,
            String key,
            CreateOrderCommand command
    ) {
        String hash = requestHasher.hash(command);
        try {
            return attempt.execute(tenantId, key, hash, command);
        } catch (DuplicateKeyException ex) {
            return replay.resolve(tenantId, "CREATE_ORDER", key, hash);
        }
    }
}
~~~

Đây là khung minh họa; cần inject `requestHasher`, khai báo exception/domain result và xử lý đúng constraint. `DuplicateKeyException` là một loại `DataIntegrityViolationException` trong Spring. Tùy cách ghi và exception translation của driver/framework, vi phạm unique có thể được biểu diễn bằng exception cụ thể khác. Chỉ xem đó là duplicate idempotency khi xác định được đúng unique constraint hoặc khi bước replay tìm thấy receipt tương ứng; không biến mọi lỗi integrity thành retry thành công.

### 8.2. Nếu không tìm thấy receipt sau duplicate exception?

Có thể duplicate exception đến từ một business unique constraint khác, chẳng hạn SKU hoặc external reference. Nếu không tìm thấy receipt theo scope/key, hãy ném lại lỗi hoặc xử lý business conflict tương ứng. Không được mặc định mọi duplicate key đều là idempotency replay.

### 8.3. Request trùng trong khi request đầu đang chạy

Với unique insert trong transaction, request thứ hai có thể phải chờ transaction đầu giải quyết xung đột trên unique index:

- Nếu transaction đầu commit, request thứ hai nhận unique conflict rồi đọc receipt hoàn tất để replay.
- Nếu transaction đầu rollback, request thứ hai có thể insert thành công và thực hiện command.

Chi tiết chờ, timeout và khả năng nhìn thấy receipt phụ thuộc database và isolation level. Đặt timeout phù hợp và kiểm thử trên database mục tiêu.

## 9. Dùng INSERT ... ON CONFLICT hoặc cơ chế tương đương

Một số database hỗ trợ cú pháp insert không làm transaction thất bại khi key đã tồn tại. PostgreSQL:

~~~sql
INSERT INTO idempotency_record (
    tenant_id, operation, idempotency_key,
    request_hash, state, created_at
)
VALUES (
    :tenantId, :operation, :key,
    :requestHash, 'PROCESSING', :createdAt
)
ON CONFLICT (tenant_id, operation, idempotency_key)
DO NOTHING;
~~~

Sau đó kiểm tra số hàng bị ảnh hưởng:

- `1`: request đã giành được key và có thể thực hiện command.
- `0`: key đã tồn tại; đọc receipt hiện tại và so sánh hash.

Đây là cú pháp PostgreSQL, không portable nguyên dạng sang mọi database. SQL Server, MySQL, Oracle và các hệ quản trị khác có cách biểu diễn upsert/ignore conflict khác nhau. Với nhiều database, có thể tách implementation theo dialect hoặc dùng chiến lược insert + exception translation.

Ngay cả khi dùng `ON CONFLICT DO NOTHING`, vẫn phải xử lý transaction và visibility theo isolation level. Không giả định mọi database đều có cùng semantics về concurrent insert và read-after-conflict.

## 10. Trạng thái PROCESSING và command kéo dài

Với command ngắn chỉ ghi database, receipt có thể được tạo và hoàn tất trong cùng transaction; trạng thái trung gian không bao giờ được commit ra ngoài. Nếu transaction rollback, receipt cũng biến mất.

Với công việc kéo dài hoặc bất đồng bộ, ứng dụng có thể cần commit receipt ở trạng thái `PROCESSING` trước khi xử lý:

~~~text
NEW -> PROCESSING -> COMPLETED
                  -> FAILED/RETRYABLE
~~~

Khi đó cần thêm cơ chế vận hành:

- Lease/lock owner để xác định worker đang xử lý.
- Thời hạn lease để thu hồi công việc bị bỏ dở.
- Số lần thử và thời điểm retry.
- Trạng thái lỗi có thể phục hồi hay lỗi vĩnh viễn.
- Quy tắc cho request trùng khi đang PROCESSING (trả 202, chờ hoặc báo đang xử lý).
- Worker recovery sau khi process chết.

Không chỉ lưu `PROCESSING` rồi giả định nó sẽ tự chuyển sang `COMPLETED`. Process có thể chết giữa chừng; cần cơ chế phát hiện và tiếp tục.

### 10.1. Không để receipt PROCESSING vô thời hạn

Nếu receipt được commit trước khi xử lý business command, worker có thể chết sau khi claim. Dùng `lease_until`, `attempt_count` và `updated_at` để xác định khi nào có thể reclaim. Reclaim phải có điều kiện atomic hoặc lock phù hợp để hai worker không cùng nhận một job.

Đây là mô hình phức tạp hơn idempotency trong một transaction ngắn. Chỉ dùng khi thời gian xử lý hoặc kiến trúc bất đồng bộ thực sự yêu cầu.

## 11. Idempotency với side effect bên ngoài database

Transaction JDBC chỉ bảo vệ các thay đổi tham gia cùng database transaction. Nó không thể rollback email đã gửi, HTTP request tới payment provider hoặc message đã được publish ra broker.

Ví dụ không an toàn:

~~~text
BEGIN
  save order
  call payment provider
  insert idempotency receipt
COMMIT
~~~

Nếu payment provider đã thu tiền nhưng database rollback, hệ thống có thể có thanh toán thật mà không có order/receipt tương ứng. Nếu database commit nhưng lời gọi bên ngoài thất bại, kết quả cũng không đồng bộ.

### 11.1. Transactional outbox

Một cách phổ biến:

~~~text
BEGIN
  save order aggregate
  save idempotency receipt
  insert outbox event
COMMIT

Outbox publisher:
  read unpublished event
  send to broker/provider
  mark published
~~~

Order, receipt và outbox event được commit cùng transaction. Publisher có thể gửi lại event nếu không chắc lần gửi trước đã thành công; consumer cần deduplicate bằng event ID hoặc xử lý idempotent.

Outbox bảo đảm event được ghi cùng business change trong database. Nó không tự biến việc gửi ra broker thành exactly-once; publisher và consumer vẫn cần xử lý delivery lặp.

### 11.2. Dùng idempotency key của nhà cung cấp

Nếu gọi payment provider, dùng key ổn định theo payment operation nếu nhà cung cấp hỗ trợ. Khi retry lời gọi, gửi lại cùng provider idempotency key để provider không tạo hai giao dịch.

Key ở ứng dụng và key ở provider có thể khác scope. Lưu mapping giữa chúng để có thể đối chiếu, retry và điều tra.

## 12. Idempotency và optimistic locking giải quyết hai vấn đề khác nhau

Hai cơ chế thường bị nhầm:

| Cơ chế | Câu hỏi được trả lời |
| --- | --- |
| Idempotency key + unique constraint | Đây có phải cùng một command đã được xử lý trước đó không? |
| Optimistic locking (`@Version`) | Aggregate có còn ở phiên bản mà command dựa trên không? |
| Business unique constraint | Hai bản ghi này có vi phạm quy tắc duy nhất của miền không? |

Ví dụ:

- Client retry cùng request tạo đơn: idempotency key ngăn tạo đơn thứ hai.
- Hai người dùng cùng sửa một đơn từ version 5: optimistic locking phát hiện một bản cập nhật dùng version cũ.
- Hai request khác key cùng tạo đơn với external reference đã tồn tại: business unique constraint ngăn trùng reference.

Một hệ thống có thể cần cả ba cơ chế.

## 13. Thời gian lưu idempotency record

Không phải record nào cũng cần giữ mãi, nhưng xóa quá sớm có thể khiến retry cũ tạo hiệu ứng lần nữa.

Chính sách retention cần xét:

- Client có thể retry trong bao lâu?
- Gateway/message broker có thời hạn giao lại bao lâu?
- Có quy định nghiệp vụ hoặc kiểm toán cần giữ receipt không?
- Kết quả có thể được tái dựng từ resource ID không?
- Có thể xóa response body nhạy cảm nhưng giữ key/hash/resource ID không?

Nếu xóa record sau 24 giờ nhưng client có thể retry sau 48 giờ, cùng key có thể bị xử lý lại. Hãy chọn retention dài hơn cửa sổ retry tối đa và cân nhắc lưu business unique reference lâu dài như một lớp bảo vệ bổ sung.

Có thể partition hoặc dọn record theo thời gian, nhưng việc dọn không được xóa nhầm receipt đang PROCESSING hoặc record còn trong cửa sổ retry.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ dùng `exists` rồi mới insert | Race condition khi request đồng thời | Đặt unique constraint và xử lý duplicate |
| Mỗi lần retry tạo key mới | Server xem đó là command mới | Client giữ nguyên key cho cùng thao tác |
| Không lưu request hash | Cùng key có thể được dùng với body khác | Lưu fingerprint và trả conflict khi khác |
| Key không có tenant/operation scope | Các caller/endpoint có thể va chạm ngoài ý muốn | Unique composite theo scope |
| Chỉ lưu key, không lưu kết quả | Không thể replay response nhất quán | Lưu response snapshot hoặc resource reference theo contract |
| Bắt duplicate bên trong transaction đã lỗi | Transaction có thể rollback-only/aborted | Để transaction kết thúc rồi đọc receipt trong transaction mới |
| Coi mọi DataIntegrityViolation là duplicate idempotency | Che lỗi foreign key, CHECK hoặc business unique | Xác định đúng constraint và xác minh receipt |
| Ghi receipt và aggregate ở hai transaction riêng | Có thể có receipt không có resource hoặc ngược lại | Ghi cùng transaction khi cùng database |
| Gọi external API trong transaction và kỳ vọng rollback | Side effect ngoài DB không rollback | Dùng outbox và idempotency của provider |
| Để PROCESSING không có lease/recovery | Request bị kẹt vô thời hạn | Có lease, timeout, retry và worker recovery |
| Xóa receipt quá sớm | Retry cũ có thể tạo hiệu ứng lần nữa | Retention phù hợp cửa sổ retry |
| Nhầm idempotency với optimistic locking | Không xử lý đúng retry hoặc lost update | Dùng đúng cơ chế cho từng vấn đề |

## 15. Quy trình thiết kế idempotent write

Khi triển khai endpoint hoặc consumer có thể nhận delivery lặp:

1. **Xác định command:** hành động nghiệp vụ nào cần có hiệu ứng tối đa một lần trong phạm vi nào?
2. **Chọn key ổn định:** client tạo key hoặc dùng event ID; giữ nguyên khi retry.
3. **Xác định scope:** tenant, operation và key.
4. **Canonicalize request:** tạo fingerprint từ các field có ý nghĩa nghiệp vụ.
5. **Đặt unique constraint:** dùng database làm trọng tài cho các request đồng thời.
6. **Chọn transaction strategy:** command ngắn thì ghi receipt, aggregate và response cùng transaction; command dài thì thiết kế state machine/lease.
7. **Lưu kết quả replay:** response snapshot hoặc resource ID theo API contract.
8. **Xử lý duplicate sau rollback:** đọc receipt đã commit, so sánh hash, replay hoặc trả conflict.
9. **Bảo vệ invariant miền:** thêm business unique constraint và optimistic locking khi cần.
10. **Xử lý side effect:** ghi outbox trong transaction và deduplicate ở consumer/provider.
11. **Đặt retention:** giữ record đủ lâu cho cửa sổ retry và yêu cầu audit.
12. **Kiểm thử concurrency:** gửi đồng thời nhiều request cùng key và xác nhận chỉ có một hiệu ứng nghiệp vụ.

## 16. Kiểm thử idempotency và ràng buộc duy nhất

Các test quan trọng:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Gửi một key một lần | Tạo resource và receipt hoàn tất |
| Gửi lại cùng key, cùng body | Không tạo resource mới; trả lại kết quả cũ |
| Gửi cùng key, body khác | Trả conflict; không tạo hiệu ứng mới |
| Hai request cùng key chạy đồng thời | Chỉ một transaction tạo hiệu ứng |
| Request đầu rollback trước commit | Request retry có thể thực hiện command |
| Hai key khác nhau nhưng cùng business reference | Business unique constraint ngăn bản ghi trùng |
| Ghi aggregate thành công nhưng ghi receipt thất bại | Cùng transaction rollback cả hai |
| Gửi event outbox lặp | Consumer deduplicate theo event ID |
| Receipt hết retention rồi request cũ quay lại | Hành vi đúng với chính sách retention đã công bố |

### 16.1. Test đồng thời cần database thật

Mock repository không thể chứng minh unique index thực sự xử lý hai insert đồng thời. Hãy chạy integration test với database production hoặc Testcontainers:

1. Tạo một idempotency key và command cố định.
2. Khởi chạy nhiều thread/request cùng lúc với key đó.
3. Đồng bộ điểm bắt đầu để tăng khả năng tranh chấp.
4. Chờ tất cả kết quả.
5. Kiểm tra chỉ có một receipt trong scope.
6. Kiểm tra chỉ có một order/resource.
7. Kiểm tra các request còn lại replay cùng kết quả hoặc nhận trạng thái đang xử lý theo contract.

Không chỉ assert một request trả thành công; phải kiểm tra trạng thái database sau concurrency.

### 16.2. Test rollback khi lỗi giữa chừng

Buộc một bước sau khi insert receipt hoặc lưu aggregate thất bại, rồi xác nhận transaction không để lại receipt/resource một phần. Test phải đọc lại sau khi transaction của command kết thúc, tránh đọc trong transaction test đang che kết quả commit/rollback thực tế.

## Ghi nhớ

Idempotency bảo vệ một command khỏi tạo hiệu ứng lặp khi client, gateway hoặc message broker gửi lại cùng yêu cầu. Idempotency key nhận diện lần thao tác; request hash phát hiện key bị tái sử dụng với nội dung khác; unique constraint là trọng tài ở database khi nhiều request chạy đồng thời.

Với command ghi database ngắn, lưu receipt, thay đổi aggregate và kết quả replay trong cùng transaction. Khi gặp duplicate key, để transaction thử ghi kết thúc rồi đọc receipt đã commit trong transaction mới; so sánh fingerprint để replay hoặc trả conflict. Business unique constraint và `@Version` bảo vệ những quy tắc khác. Với side effect ngoài database, ghi outbox cùng transaction và tiếp tục xử lý delivery lặp ở publisher/consumer. Cách này tạo hành vi ghi đáng tin cậy trước retry và concurrency mà không dựa vào một bước kiểm tra tồn tại dễ gặp race condition.
