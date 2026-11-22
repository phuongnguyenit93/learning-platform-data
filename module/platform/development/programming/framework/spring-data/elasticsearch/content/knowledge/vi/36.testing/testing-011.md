# Kiểm thử bulk lỗi một phần, retry và tính lặp an toàn

Bulk API giúp gửi nhiều thao tác index, create, update hoặc delete trong một request để giảm overhead mạng và tăng throughput. Tuy nhiên, một bulk request không phải transaction nguyên tử. Elasticsearch xử lý từng item độc lập: một số document có thể thành công trong khi item khác thất bại.

Vì vậy, việc nhận được HTTP response thành công hoặc method bulk trả về không đồng nghĩa mọi document đều đã được ghi. Ứng dụng phải đọc kết quả từng item, phân loại lỗi, chỉ retry những thao tác có thể thử lại và bảo đảm retry không tạo dữ liệu trùng hoặc áp dụng một thay đổi nhiều lần.

Trong Spring Data Elasticsearch, bulk operation có thể được thực hiện qua ElasticsearchOperations hoặc Elasticsearch Java API Client. Dù dùng abstraction nào, thiết kế kiểm thử cần xác nhận được ba điều: kết quả từng item được quan sát đúng, retry chỉ áp dụng cho phần thất bại có thể khắc phục, và thao tác lặp lại vẫn giữ đúng trạng thái dữ liệu.

Bài này giải thích semantics của Bulk API, cách kiểm tra partial failure, chiến lược retry có backoff, idempotency theo từng loại operation, cách xử lý timeout không rõ kết quả, dead-letter handling, concurrency, cùng các bài kiểm thử nên có.

## 1. Bulk request không phải transaction

Một bulk request chứa nhiều action liên tiếp. Ví dụ NDJSON:

~~~http
POST /_bulk
{"index":{"_index":"products","_id":"P-1001"}}
{"sku":"SKU-1001","name":"Wireless Mouse","stock":42}
{"index":{"_index":"products","_id":"P-1002"}}
{"sku":"SKU-1002","name":"Keyboard","stock":18}
{"delete":{"_index":"products","_id":"P-1003"}}
~~~

Elasticsearch xử lý từng action trong batch. Kết quả có thể là:

- P-1001 được index thành công.
- P-1002 thất bại vì mapping hoặc dữ liệu không hợp lệ.
- P-1003 được xóa thành công.

Bulk API không rollback P-1001 và P-1003 chỉ vì P-1002 lỗi. Nó cũng không đảm bảo tất cả item cùng commit hoặc cùng thất bại.

Do đó, bulk là cơ chế gom request để tăng hiệu quả truyền tải, không phải transaction nhiều document.

### 1.1. Hai cấp độ lỗi

Cần phân biệt:

**Lỗi ở cấp request**

Toàn bộ request không được xử lý đúng như dự kiến. Ví dụ:

- Request không hợp lệ về NDJSON.
- Body quá lớn hoặc vượt giới hạn.
- Endpoint/index không hợp lệ ở cấp request.
- Authentication/authorization bị từ chối.
- Kết nối thất bại trước khi nhận response.
- Proxy hoặc cluster trả lỗi request-level.

**Lỗi ở cấp item**

Bulk response được trả về nhưng một hoặc nhiều action thất bại. Ví dụ:

- Document không khớp mapping.
- Version conflict.
- Document update không tồn tại.
- Index bị read-only.
- Shard hoặc node từ chối item vì quá tải.

Một request có thể trả HTTP 200 nhưng trường errors trong response là true. Đây là lý do không được chỉ kiểm tra HTTP status.

## 2. Cấu trúc Bulk response

Bulk response có trường errors và danh sách items. Mỗi item tương ứng với một action trong request, theo cùng thứ tự.

Ví dụ:

~~~json
{
  "took": 18,
  "errors": true,
  "items": [
    {
      "index": {
        "_index": "products",
        "_id": "P-1001",
        "status": 201,
        "result": "created"
      }
    },
    {
      "index": {
        "_index": "products",
        "_id": "P-1002",
        "status": 400,
        "error": {
          "type": "mapper_parsing_exception",
          "reason": "failed to parse field [priceInCents]"
        }
      }
    },
    {
      "delete": {
        "_index": "products",
        "_id": "P-1003",
        "status": 200,
        "result": "deleted"
      }
    }
  ]
}
~~~

Trong ví dụ này:

- errors = true vì có ít nhất một item thất bại.
- Item đầu tiên thành công.
- Item thứ hai lỗi mapping với status 400.
- Item thứ ba thành công.

Ứng dụng phải ghép từng item response với operation/source record tương ứng để biết record nghiệp vụ nào cần retry, từ chối hoặc đưa vào vùng cách ly.

### 2.1. Những trường cần đọc

Ở cấp response:

- took: thời gian Elasticsearch xử lý request.
- errors: có ít nhất một item thất bại hay không.
- items: kết quả theo từng action.

Ở cấp item:

- operation type: index, create, update hoặc delete.
- _index và _id: đích và document ID.
- status: HTTP status riêng của item.
- result: created, updated, deleted, noop hoặc kết quả tương ứng.
- error: loại lỗi và thông điệp khi item thất bại.

Không phải mọi item đều có cùng tập field response. Khi thành công, response thường có result và version/sequence metadata; khi lỗi, có error. Hãy kiểm tra cấu trúc đúng với Elasticsearch/client version.

### 2.2. Không suy ra item thành công từ errors = false rồi bỏ qua response

Nếu errors = false, các item trong response đều không báo lỗi theo kết quả bulk đó. Nhưng ứng dụng vẫn nên đọc item result khi cần:

- Lưu version hoặc sequence metadata.
- Phân biệt created và updated.
- Xác nhận delete/noop.
- Ghi metrics theo loại operation.
- Correlate document với nguồn dữ liệu.

Khi errors = true, phải duyệt từng item để phân loại. Không retry cả batch một cách mặc định.

## 3. Giữ metadata để ghép request với response

Bulk response trả items theo thứ tự action. Vì vậy ứng dụng cần giữ một danh sách metadata cùng thứ tự với operations đã gửi.

Ví dụ metadata:

~~~java
public record BulkOperationMetadata(
    int position,
    String businessKey,
    String indexName,
    String documentId,
    String operationType,
    int attempt
) {
}
~~~

Khi tạo bulk request, tạo metadata tương ứng cho từng operation. Khi nhận response, ghép item ở vị trí i với metadata ở vị trí i.

Điều này giúp:

- Xác định record nguồn gây lỗi.
- Chỉ xây dựng lại các operation cần retry.
- Ghi dead-letter record kèm business key.
- Tránh retry nhầm item thành công.
- Theo dõi số lần thử theo từng document.

Không chỉ lưu một list document mà không có correlation key. Khi một batch chứa hàng nghìn item, log một thông báo lỗi chung không đủ để xử lý chính xác.

### 3.1. Đừng giả định thứ tự sau khi tự lọc hoặc sắp xếp

Khi xây dựng retry batch, danh sách operations mới có thể ngắn hơn và thứ tự khác batch ban đầu. Tạo metadata mới cho retry batch theo đúng thứ tự operations mới.

Nếu code xử lý response song song hoặc gom nhiều batch, dùng correlation ID/batch ID riêng để tránh ghép response của batch này với source record của batch khác.

## 4. Kiểm tra Bulk response bằng Elasticsearch Java API Client

Với Elasticsearch Java API Client, response thường có thể được kiểm tra qua BulkResponse và BulkResponseItem.

Ví dụ:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.BulkRequest;
import co.elastic.clients.elasticsearch.core.BulkResponse;
import co.elastic.clients.elasticsearch.core.bulk.BulkResponseItem;

BulkResponse response = client.bulk(request);

if (response.errors()) {
    for (int i = 0; i < response.items().size(); i++) {
        BulkResponseItem item = response.items().get(i);

        if (item.error() != null) {
            BulkOperationMetadata metadata = metadataForBatch.get(i);

            log.warn(
                "Bulk item failed: batchId={}, position={}, key={}, index={}, id={}, status={}, type={}, reason={}",
                batchId,
                metadata.position(),
                metadata.businessKey(),
                item.index(),
                item.id(),
                item.status(),
                item.error().type(),
                item.error().reason()
            );
        }
    }
}
~~~

Đây là cách kiểm tra theo API Java client hiện đại. Package, kiểu response và tên accessor có thể thay đổi theo client version. Hãy xác nhận với dependency của dự án.

Điểm quan trọng của ví dụ:

- Kiểm tra errors.
- Duyệt từng item.
- Dùng vị trí để tìm metadata của operation tương ứng.
- Chỉ log business key và thông tin kỹ thuật cần thiết.
- Không log toàn bộ source nếu document có dữ liệu nhạy cảm.

### 4.1. Xây dựng danh sách item thất bại

Có thể phân loại response thành ba nhóm:

~~~java
List<BulkOperationMetadata> succeeded = new ArrayList<>();
List<BulkOperationMetadata> retryable = new ArrayList<>();
List<FailedBulkRecord> permanentFailures = new ArrayList<>();

for (int i = 0; i < response.items().size(); i++) {
    BulkResponseItem item = response.items().get(i);
    BulkOperationMetadata metadata = metadataForBatch.get(i);

    if (item.error() == null) {
        succeeded.add(metadata);
        continue;
    }

    if (isRetryable(item.status(), item.error().type())) {
        retryable.add(metadata);
    } else {
        permanentFailures.add(
            new FailedBulkRecord(
                metadata,
                item.status(),
                item.error().type(),
                item.error().reason()
            )
        );
    }
}
~~~

Các kiểu FailedBulkRecord và isRetryable là logic ứng dụng cần định nghĩa. Không phụ thuộc vào tên class ví dụ; mục tiêu là tách rõ item thành công, lỗi có thể retry và lỗi không thể retry.

## 5. Phân loại lỗi trước khi retry

Retry chỉ có ích khi lỗi có khả năng biến mất sau một khoảng thời gian hoặc sau một hành động khắc phục. Retry lỗi vĩnh viễn chỉ làm tăng tải và kéo dài thời gian xử lý.

Một bảng phân loại tham khảo:

| Lỗi/status | Phân loại thường gặp | Hành động |
|---|---|---|
| 400 mapper/parsing error | Permanent | Sửa dữ liệu hoặc schema; không retry tự động |
| 401 unauthorized | Configuration/credential | Sửa authentication; dừng hoặc cảnh báo |
| 403 forbidden | Authorization | Sửa quyền; không retry liên tục |
| 404 index/document missing | Tùy operation | Kiểm tra đích và semantics upsert/delete |
| 409 version conflict | Concurrency conflict | Đọc lại và giải quyết theo nghiệp vụ |
| 413 payload too large | Batch/request size | Chia nhỏ batch, không gửi lại nguyên kích thước |
| 429 too many requests | Transient/backpressure | Backoff, giảm concurrency |
| 502/503/504 | Thường transient | Backoff có giới hạn và theo dõi cluster |
| Timeout/network reset | Kết quả có thể không rõ | Reconcile hoặc retry an toàn theo idempotency |
| 5xx khác | Tùy nguyên nhân | Xem error type và server logs |

Phân loại trên là điểm khởi đầu. Cần dựa vào error type, status, context của operation và chính sách cluster.

### 5.1. Lỗi mapping không nên retry

Ví dụ priceInCents được mapping long nhưng producer gửi chuỗi "unknown". Gửi lại cùng payload sau một giây không làm giá trị trở thành số hợp lệ.

Cách xử lý phù hợp:

- Ghi nhận business key và validation error.
- Đưa record vào dead-letter/quarantine nếu cần sửa sau.
- Trả lỗi về upstream hoặc đánh dấu batch có record bị từ chối.
- Chỉ replay sau khi dữ liệu hoặc mapping được sửa.

### 5.2. 429 là tín hiệu cần giảm tải

429 thường cho biết cluster đang từ chối một số thao tác vì quá tải hoặc giới hạn tài nguyên. Retry ngay lập tức với cùng concurrency có thể làm tình hình tệ hơn.

Cần:

- Exponential backoff.
- Jitter để nhiều worker không retry cùng lúc.
- Giảm số request đồng thời hoặc batch size.
- Giới hạn số item đang chờ.
- Theo dõi thread pool queue, rejection và ingest/indexing pressure theo phiên bản.

Retry không thay thế load control.

### 5.3. 409 cần chính sách nghiệp vụ

409 có thể là version conflict hoặc create trùng ID. Hai trường hợp không giống nhau:

- Version conflict: một writer khác đã thay đổi document. Có thể đọc lại, tính lại thay đổi và retry có kiểm soát.
- Create conflict: document ID đã tồn tại. Có thể đây là duplicate hợp lệ, duplicate không mong muốn hoặc một lần thử trước đã thành công nhưng response bị mất.

Không tự động retry 409 mà chưa xác định ý nghĩa operation.

## 6. Retry chỉ các item thất bại

Giả sử batch có 100 operations:

- 94 item thành công.
- 4 item lỗi 429.
- 2 item lỗi mapping 400.

Chiến lược phù hợp:

1. Xác nhận 94 item thành công.
2. Ghi 2 item mapping error vào failure/quarantine.
3. Chỉ retry 4 item 429.
4. Tạo bulk request mới gồm đúng 4 operation.
5. Tăng attempt counter cho các item được retry.

Không gửi lại cả 100 operations. Làm vậy vừa tốn tải vừa có thể lặp các thao tác không idempotent đã thành công.

### 6.1. Retry subset cần giữ nguyên payload có chủ đích

Khi retry, lưu đủ thông tin để tái tạo operation:

- Operation type.
- Index/alias đích.
- Document ID.
- Routing nếu có.
- Source hoặc partial document.
- Script và params nếu dùng update script.
- Version/concurrency condition nếu có.
- Pipeline ID nếu request cần pipeline.
- Business key và correlation ID.

Không chỉ lưu error message rồi kỳ vọng có thể xây dựng lại request. Nếu source đã thay đổi trong hệ thống upstream, retry có thể ghi một payload khác với operation ban đầu.

### 6.2. Pseudocode xử lý một batch

~~~text
pending = original operations
attempt = 0

while pending is not empty and attempt < maxAttempts:
    response = sendBulk(pending)

    nextRetry = []

    for each item result in response order:
        correlate result with pending operation

        if success:
            record success

        else if retryable:
            add operation to nextRetry

        else:
            write permanent failure to quarantine

    pending = nextRetry

    if pending is not empty:
        wait exponentialBackoffWithJitter(attempt)

    attempt = attempt + 1

if pending is not empty:
    move remaining operations to retry-exhausted queue
~~~

Trong thực tế, retry có thể chạy bất đồng bộ qua queue thay vì giữ một thread chờ. Dù chọn cách nào, cần giới hạn tổng thời gian và số lần thử.

## 7. Exponential backoff và jitter

Một retry policy phổ biến tăng khoảng chờ theo số lần thử:

\[
delay_n = \min(maxDelay,\ baseDelay \times 2^n)
\]

Ví dụ baseDelay 200 ms, maxDelay 5 s:

| Attempt | Delay cơ sở |
|---:|---:|
| 0 | 200 ms |
| 1 | 400 ms |
| 2 | 800 ms |
| 3 | 1.6 s |
| 4 | 3.2 s |
| 5 trở đi | 5 s |

Không nên để mọi worker retry đúng cùng thời điểm. Jitter thêm một độ ngẫu nhiên vào delay để phân tán request:

\[
actualDelay = random(0,\ delay_n)
\]

Một số hệ thống dùng full jitter, equal jitter hoặc decorrelated jitter. Chọn một policy nhất quán và đặt giới hạn tối đa.

### 7.1. Retry budget

Cần có các giới hạn:

- Max attempts theo item.
- Max elapsed time.
- Max queue size.
- Max concurrent retry batches.
- Max batch size.
- Circuit breaker hoặc pause khi cluster liên tục từ chối.
- Dead-letter khi hết retry budget.

Nếu một item có thể retry 100 lần, một lỗi mapping có thể làm queue phình lớn và giữ tài nguyên vô hạn. Retry budget giúp failure có điểm kết thúc rõ ràng.

### 7.2. Respect Retry-After khi có

Một số proxy hoặc tầng dịch vụ có thể trả Retry-After. Nếu client có thông tin này, cân nhắc tôn trọng giá trị đó thay vì luôn dùng delay nội bộ ngắn hơn.

Không phải mọi Elasticsearch item error đều có Retry-After. Đừng giả định header luôn có mặt trong Bulk API response.

## 8. Ví dụ retry classifier và backoff trong Java

Classifier đơn giản:

~~~java
public boolean isRetryable(int status, String errorType) {
    if (status == 429) {
        return true;
    }

    if (status == 502 || status == 503 || status == 504) {
        return true;
    }

    if (status >= 500 && status <= 599) {
        return true;
    }

    // Mapping, validation, authentication and authorization
    // errors should normally be handled without blind retry.
    return false;
}
~~~

Classifier production cần xem thêm error type và operation semantics. Ví dụ 404 của update có thể cần upsert hoặc xử lý not found; 409 cần concurrency policy riêng.

Hàm tính delay có jitter:

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public Duration retryDelay(
        int attempt,
        Duration baseDelay,
        Duration maxDelay) {

    long multiplier = 1L << Math.min(attempt, 20);

    long baseMillis = baseDelay.toMillis();
    long maxMillis = maxDelay.toMillis();

    long exponential = Math.min(
        maxMillis,
        baseMillis * multiplier
    );

    long jittered = ThreadLocalRandom.current()
        .nextLong(exponential + 1);

    return Duration.ofMillis(jittered);
}
~~~

Đây là helper minh họa cho full jitter. Trong code production:

- Chặn attempt âm.
- Tránh overflow khi nhân delay.
- Đảm bảo maxDelay dương.
- Dùng scheduler không block nếu đang ở reactive pipeline.
- Đưa policy vào cấu hình để điều chỉnh theo tải.

Nếu dùng Reactor, có thể dùng delayElement hoặc retryWhen với Retry.backoff và jitter, nhưng phải chú ý retry ở cấp request khác với retry subset item. Một retryWhen đặt quanh toàn bộ bulk publisher có thể gửi lại cả batch, không tự lọc item đã thành công.

## 9. Tính idempotent là gì?

Một operation idempotent khi thực hiện nhiều lần với cùng input và cùng điều kiện cho ra cùng trạng thái cuối như thực hiện một lần.

Theo ký hiệu:

\[
f(f(state)) = f(state)
\]

Idempotency đặc biệt quan trọng khi:

- Client timeout và không biết server đã xử lý request hay chưa.
- Connection reset sau khi Elasticsearch đã index nhưng trước khi response tới client.
- Worker bị restart sau khi ghi thành công nhưng trước khi đánh dấu job complete.
- Message broker redeliver event.
- Retry được chạy bởi nhiều worker.

Retry an toàn không chỉ phụ thuộc status code. Nó phụ thuộc semantics của operation và cách định danh document.

## 10. Idempotency theo loại Bulk operation

| Operation | Tính lặp an toàn | Lưu ý |
|---|---|---|
| index với ID cố định và cùng full source | Thường idempotent về trạng thái source | Mỗi lần ghi lại cùng document state |
| index với ID tự sinh | Không idempotent | Retry có thể tạo document mới |
| create với ID cố định | Không thành công lặp lại theo protocol | Lần đầu có thể đã thành công; lần sau trả 409 |
| update doc gán giá trị cố định | Thường idempotent cho các field đó | Ví dụ set status = SHIPPED |
| update script tăng counter | Không idempotent | Retry có thể cộng hai lần |
| update script append array | Không idempotent nếu không kiểm tra duplicate | Retry có thể thêm phần tử lặp |
| delete cùng ID | Desired state thường idempotent | Lần sau có thể trả not found |
| upsert gán source cố định | Thường idempotent về trạng thái source | Cần xét script và concurrency |
| scripted upsert cộng dồn | Không idempotent nếu không có guard | Retry có thể chạy script nhiều lần |

### 10.1. Index với ID xác định

Ví dụ:

~~~http
PUT /orders/_doc/ORDER-2026-0001
{
  "orderId": "ORDER-2026-0001",
  "status": "PAID",
  "totalInCents": 259900
}
~~~

Nếu gửi lại cùng ID và cùng source, trạng thái cuối vẫn là document đó với cùng dữ liệu. Đây là một cách retry tương đối an toàn.

Nhưng cần lưu ý: Index API thay thế source hiện tại. Nếu một writer khác cập nhật document giữa hai lần retry, gửi lại snapshot cũ có thể ghi đè thay đổi mới. Idempotent với cùng input không có nghĩa an toàn trước concurrent writers.

### 10.2. ID tự sinh

Ví dụ ứng dụng để Elasticsearch tự sinh ID:

~~~http
POST /orders/_doc
{
  "orderId": "ORDER-2026-0001",
  "status": "PAID"
}
~~~

Nếu response bị mất và ứng dụng gửi lại, Elasticsearch có thể tạo document thứ hai với ID khác. Vì vậy, retry an toàn cho event nghiệp vụ thường cần document ID xác định từ business key hoặc event ID.

### 10.3. Create và HTTP 409

Create-only đảm bảo ID chỉ được tạo một lần:

~~~http
PUT /orders/_create/ORDER-2026-0001
{
  "orderId": "ORDER-2026-0001",
  "status": "PAID"
}
~~~

Nếu request đầu đã thành công nhưng response bị mất, lần retry có thể nhận 409 vì ID đã tồn tại. Không nên kết luận ngay đó là thất bại nghiệp vụ.

Ứng dụng có thể:

1. Đọc document theo ID.
2. So sánh event/business key và payload/version.
3. Nếu document thể hiện đúng operation ban đầu, coi như đã hoàn tất.
4. Nếu dữ liệu khác, xử lý conflict theo nghiệp vụ.

Create chống duplicate ID, nhưng caller vẫn cần reconcile kết quả mơ hồ.

### 10.4. Update gán giá trị và update cộng dồn

Update gán giá trị cố định:

~~~http
POST /orders/_update/ORDER-2026-0001
{
  "doc": {
    "status": "SHIPPED"
  }
}
~~~

Gửi lại cùng payload thường giữ trạng thái status là SHIPPED.

Ngược lại, script tăng counter:

~~~http
POST /metrics/_update/worker-1
{
  "script": {
    "source": "ctx._source.count += params.amount",
    "params": {
      "amount": 1
    }
  }
}
~~~

Nếu retry sau timeout, count có thể tăng hai lần. Script append array cũng có rủi ro tương tự.

## 11. Thiết kế idempotency key và document ID

Một cách phổ biến là tạo document ID xác định từ business key hoặc event ID.

Ví dụ:

- Order document: orderId.
- Payment event: payment provider transaction ID.
- Inventory movement: movementId.
- Outbox event: eventId.
- Import row: sourceSystem + sourceRecordId.

Không dùng một giá trị không ổn định như random UUID mới cho mỗi lần retry. Nếu cần UUID, tạo một lần ở nguồn phát event và lưu lại cùng event.

### 11.1. Kết hợp nhiều trường

Nếu business key gồm nhiều thành phần, có thể tạo ID từ canonical representation:

~~~text
tenantId + ":" + sourceSystem + ":" + sourceRecordId
~~~

Cần tránh collision do delimiter xuất hiện trong thành phần. Có thể encode từng phần hoặc hash canonical bytes thành ID.

ID xác định giúp retry tìm đúng document, nhưng không thay thế kiểm tra tenant authorization hoặc uniqueness ở hệ thống nguồn.

### 11.2. Event ID và payload hash

Có thể lưu thêm:

- eventId.
- sourceSystem.
- sourceVersion.
- payloadHash.
- processedAt.

Khi gặp duplicate event ID, ứng dụng có thể xác định:

- Cùng event và cùng payload: duplicate delivery có thể coi là đã xử lý.
- Cùng event ID nhưng payload khác: vi phạm contract hoặc event bị tái sử dụng sai.
- Source version cũ hơn: có thể bỏ qua theo quy tắc version.
- Source version mới hơn: cập nhật theo chính sách.

Không chỉ so sánh timestamp nếu nguồn có version tăng đơn điệu và đáng tin cậy.

## 12. Idempotency cho update script

Nếu cần phép cộng dồn, có thể dùng một operation ID đã xử lý để ngăn áp dụng lặp.

Ví dụ về ý tưởng:

~~~json
{
  "script": {
    "source": "if (ctx._source.processedEvents == null) { ctx._source.processedEvents = []; } if (!ctx._source.processedEvents.contains(params.eventId)) { ctx._source.count += params.amount; ctx._source.processedEvents.add(params.eventId); } else { ctx.op = 'none'; }",
    "params": {
      "eventId": "evt-10001",
      "amount": 1
    }
  }
}
~~~

Script kiểm tra eventId trước khi áp dụng phép cộng. Nếu event đã được xử lý, operation trở thành noop.

Đây là ví dụ minh họa, không phải thiết kế lưu deduplication vô hạn. Mảng processedEvents có thể tăng không giới hạn và làm document lớn. Hệ thống thực tế có thể cần một index deduplication riêng, bounded retention, external idempotency store hoặc event processing architecture phù hợp.

Nếu thao tác phải có exactly-once effect xuyên nhiều hệ thống, Elasticsearch script đơn lẻ không cung cấp distributed transaction. Hãy dùng idempotency key, outbox/inbox pattern hoặc cơ chế điều phối phù hợp.

## 13. Timeout và kết quả không rõ ràng

Timeout là trường hợp khó vì client không biết operation đã được thực hiện hay chưa.

Ví dụ:

1. Client gửi bulk request.
2. Elasticsearch nhận và ghi một số hoặc tất cả item.
3. Response bị mất trên mạng hoặc client timeout.
4. Client chỉ thấy exception.

Không thể kết luận tất cả item thất bại. Có thể một phần hoặc toàn bộ đã thành công.

Đây là ambiguous outcome.

Cách xử lý phụ thuộc operation:

- Với index ID cố định và full source xác định: có thể gửi lại và kiểm tra trạng thái cuối.
- Với update gán giá trị: thường có thể retry nếu không có writer khác làm thay đổi field.
- Với script cộng dồn: cần idempotency guard hoặc đọc/reconcile trước khi retry.
- Với create: đọc document theo ID và đối chiếu event ID.
- Với delete: xác nhận trạng thái đã vắng mặt theo semantics nghiệp vụ.

Nếu có thể, ghi lại batch ID và operation ID trước khi gửi để sau timeout có thể đối chiếu.

### 13.1. Không retry exception một cách mù quáng

Một retry quanh toàn bộ client.bulk(request) có thể gửi lại mọi operation. Điều này chỉ an toàn nếu tất cả operations trong request đều idempotent và không có side effect khác.

Nếu batch chứa cả index, create, update script và delete, cần phân loại semantics từng item trước khi chọn retry strategy. Một policy duy nhất cho mọi operation là quá thô.

## 14. Version conflict và optimistic concurrency

Khi nhiều writer cùng cập nhật một document, Elasticsearch có thể trả 409 version conflict nếu request dùng optimistic concurrency control.

Có thể dùng sequence number và primary term:

~~~http
POST /products/_update/P-1001?if_seq_no=12&if_primary_term=3
{
  "doc": {
    "stock": 35
  }
}
~~~

Nếu document đã thay đổi kể từ khi đọc, request bị từ chối thay vì ghi đè bản mới.

Ứng dụng cần:

1. Đọc document/version mới.
2. Xác định thay đổi còn hợp lệ không.
3. Tính lại command nếu cần.
4. Retry với concurrency token mới hoặc trả conflict cho caller.

Không tự động bỏ concurrency condition để retry, vì điều đó có thể biến lost update thành overwrite âm thầm.

### 14.1. retry_on_conflict không thay thế idempotency

Update API có tùy chọn retry_on_conflict cho một số update operation. Elasticsearch có thể đọc lại source mới và chạy lại update script khi gặp conflict.

Điều này xử lý một loại xung đột trong lúc update, nhưng không làm cho script trở nên idempotent trước việc client gửi trùng request. Một script tăng counter vẫn có thể tăng hai lần nếu toàn bộ request được gửi lại sau timeout.

## 15. Bulk qua Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp ElasticsearchOperations với các bulk operation như bulkIndex, bulkUpdate hoặc bulkDelete tùy version.

Ví dụ dạng thường gặp:

~~~java
List<IndexQuery> indexQueries = products.stream()
    .map(product -> new IndexQueryBuilder()
        .withId(product.getId())
        .withObject(product)
        .build())
    .toList();

List<IndexedObjectInformation> indexed =
    operations.bulkIndex(
        indexQueries,
        IndexCoordinates.of("products")
    );
~~~

API signature, response type và cách biểu diễn item failures thay đổi theo Spring Data Elasticsearch version. Một số đường gọi có thể ném exception chứa chi tiết failed documents thay vì trả về một kết quả đơn giản cho mọi item.

Vì vậy:

- Đọc Javadoc đúng dependency.
- Xác định API trả item results hay ném bulk failure exception.
- Bảo đảm ứng dụng giữ metadata của từng IndexQuery.
- Không bắt exception chung rồi đánh dấu toàn bộ batch thất bại mà không xác minh item nào đã thành công.
- Viết integration test cho đúng bulk method mà production sử dụng.

Nếu cần kiểm soát chi tiết request/response item-level, có thể dùng Elasticsearch Java API Client trực tiếp và quản lý transport qua cấu hình Spring phù hợp.

### 15.1. Bulk update và partial failure

Bulk update có thể chứa các operation với doc, script hoặc upsert. Item-level failure vẫn có thể xảy ra do:

- Document không tồn tại.
- Mapping error.
- Version conflict.
- Script error.
- Authorization hoặc index state.
- Quá tải.

Retry một update script có thể có semantics khác retry index operation. Lưu nguyên operation definition, script params và concurrency conditions nếu cần replay.

### 15.2. saveAll không đồng nghĩa transaction

Repository saveAll có thể dùng bulk hoặc nhiều thao tác theo implementation/version. Không giả định saveAll có atomicity. Kiểm tra API path và failure semantics cụ thể.

Nếu ứng dụng cần một nghiệp vụ chỉ thành công khi nhiều thay đổi cùng hoàn tất, cần thiết kế workflow/compensation hoặc transaction ở hệ thống phù hợp. Bulk API không cung cấp transaction nhiều document.

## 16. Kiến trúc retry queue và dead-letter

Với hệ thống ingest lớn, không nên giữ mọi retry trong memory của một request handler. Có thể dùng queue hoặc persistent job store.

Luồng gợi ý:

~~~text
Source events
     |
     v
Batch builder
     |
     v
Bulk writer
     |
     +------ successful items ------> Mark completed
     |
     +------ transient failures ----> Retry queue
     |
     +------ permanent failures ---> Dead-letter / quarantine
                                      |
                                      v
                                Repair and replay
~~~

Retry queue cần lưu:

- Event ID và business key.
- Operation type.
- Index và document ID.
- Payload hoặc reference tới payload bất biến.
- Số lần thử.
- Lần thử gần nhất.
- Lỗi cuối.
- Thời điểm thử tiếp theo.
- Correlation/batch ID.

Dead-letter record cần đủ thông tin để điều tra và replay sau khi sửa nguyên nhân. Tránh lưu password, token hoặc dữ liệu nhạy cảm không cần thiết.

### 16.1. Không để retry queue tăng vô hạn

Thiết lập:

- Max attempts.
- Retention.
- Queue capacity.
- Alert khi backlog tăng.
- Dead-letter threshold.
- Quy trình replay.
- Giới hạn concurrency của retry worker.

Nếu Elasticsearch ngừng hoạt động lâu, queue phải có backpressure để bảo vệ memory và upstream. Không tiếp tục nhận vô hạn chỉ vì có thể ghi vào một list trong process.

## 17. Bảo đảm thứ tự theo document key

Một số nghiệp vụ yêu cầu event cho cùng một document được xử lý đúng thứ tự.

Ví dụ:

1. Order được tạo.
2. Order chuyển sang PAID.
3. Order chuyển sang SHIPPED.

Nếu event SHIPPED được retry và ghi trước event PAID cũ, trạng thái có thể bị lùi về PAID.

Các chiến lược:

- Partition queue theo document ID/business key.
- Xử lý tuần tự trong từng partition.
- Dùng source version/sequence để từ chối event cũ.
- Dùng optimistic concurrency.
- Chỉ cho phép một writer sở hữu key trong một thời điểm theo kiến trúc phù hợp.

Idempotency không tự bảo đảm ordering. Một event có thể idempotent nhưng vẫn ghi đè trạng thái mới hơn nếu được phát lại sai thứ tự.

## 18. Bulk size, concurrency và retry storm

Khi cluster quá tải, retry nhiều request đồng thời có thể tạo retry storm.

Cần theo dõi:

- Batch size theo số item và byte.
- Số bulk request đồng thời.
- Latency của bulk request.
- Item failure rate theo status/error type.
- 429/rejection.
- Retry queue depth.
- Retry attempts và exhausted count.
- Ingest/indexing thread pool và indexing pressure theo version.
- Heap, CPU, disk I/O và merge pressure.

### 18.1. Chọn batch size

Không có một batch size cố định cho mọi cluster. Batch lớn giảm số request nhưng có thể:

- Tăng memory phía client.
- Tăng latency khi phải chờ cả batch.
- Tạo request quá lớn.
- Làm retry subset phức tạp nếu metadata không được giữ.
- Tạo áp lực lớn khi server từ chối request.

Đo trên document size thực tế. Tăng dần batch size tới khi throughput không còn cải thiện hoặc latency/rejection tăng.

### 18.2. Điều chỉnh concurrency khi có 429

Nếu 429 tăng:

1. Giảm số bulk request đang chạy đồng thời.
2. Giảm hoặc giữ ổn định batch size tùy nguyên nhân.
3. Backoff có jitter.
4. Theo dõi queue/rejection.
5. Tăng tải trở lại từ từ khi cluster phục hồi.

Không tăng retry concurrency để bù cho throughput giảm. Điều đó thường làm cluster bị quá tải lâu hơn.

## 19. Kiểm thử partial failure có chủ đích

Một test tốt cần chứng minh một batch có cả thành công và thất bại, sau đó ứng dụng xử lý đúng từng nhóm.

Có thể dùng Elasticsearch Testcontainers hoặc test cluster cô lập.

Kịch bản:

1. Tạo index với mapping priceInCents là long.
2. Tạo batch gồm document hợp lệ và document có priceInCents không parse được.
3. Gửi bulk.
4. Xác nhận response.errors là true.
5. Xác nhận item hợp lệ đã được index.
6. Xác nhận item lỗi có status/error tương ứng.
7. Xác nhận application không retry item mapping error.
8. Sửa payload hoặc đưa vào quarantine.
9. Đọc lại document để xác nhận trạng thái cuối.

Không chỉ assert rằng bulk method ném exception. Cần kiểm tra item nào đã thành công và item nào thất bại.

### 19.1. Test response correlation

Dùng nhiều document với business key khác nhau và cố tình làm một item lỗi ở giữa batch. Xác nhận failure được gắn đúng business key và document ID.

Test này phát hiện lỗi phổ biến: code duyệt danh sách lỗi rồi dùng index sai để lấy source record.

### 19.2. Test retry subset

Giả lập response:

- Item A thành công.
- Item B trả 429.
- Item C lỗi 400.

Xác nhận lần gửi tiếp theo chỉ chứa B. A không được gửi lại; C được chuyển vào permanent failure path.

Dùng mock client hoặc fake bulk gateway để kiểm tra classifier và retry orchestration mà không cần tạo lỗi cluster thật trong mọi unit test.

### 19.3. Test retry exhaustion

Giả lập item liên tục trả 503 hoặc 429. Xác nhận:

- Số lần thử không vượt giới hạn.
- Delay policy được áp dụng.
- Item cuối cùng được ghi vào retry-exhausted/dead-letter.
- Queue không giữ item vô hạn.
- Metrics và alert được phát ra theo contract.

## 20. Kiểm thử idempotency

Cần kiểm thử trạng thái cuối sau khi gửi cùng operation nhiều lần.

### 20.1. Index với ID cố định

1. Gửi index operation lần đầu.
2. Gửi lại cùng ID và cùng source.
3. Đọc document.
4. Xác nhận chỉ có một document với source đúng.

### 20.2. ID tự sinh

1. Gửi create/index không có ID.
2. Gửi lại cùng payload.
3. Đếm document.
4. Xác nhận có thể tạo duplicate.

Test này giúp chứng minh vì sao event processing cần ID ổn định.

### 20.3. Script tăng counter

1. Gửi script increment một lần.
2. Gửi lại cùng request.
3. Đọc counter.
4. Xác nhận giá trị tăng hai lần nếu không có dedup guard.
5. Bổ sung idempotency guard và xác nhận gửi lặp chỉ áp dụng một lần.

### 20.4. Create conflict sau timeout

Mô phỏng trường hợp operation đã được tạo nhưng client không nhận response. Gửi lại create cùng ID và nhận 409. Sau đó đọc document, so sánh eventId/payloadHash và xác nhận kết quả có thể reconcile là đã hoàn tất.

### 20.5. Concurrent retry

Chạy hai worker cùng xử lý một event ID. Xác nhận chỉ một worker tạo effect hoặc cơ chế dedup/concurrency bảo vệ trạng thái cuối. Một idempotency check chỉ ở memory của từng worker không đủ khi có nhiều instance.

## 21. Unit test classifier và backoff

Classifier nên là thành phần thuần để test:

~~~java
@Test
void shouldRetryTooManyRequests() {
    assertThat(retryPolicy.isRetryable(429, "rejected_execution_exception"))
        .isTrue();
}

@Test
void shouldNotRetryMappingErrors() {
    assertThat(retryPolicy.isRetryable(400, "mapper_parsing_exception"))
        .isFalse();
}
~~~

Backoff nên test các giới hạn:

- Delay không âm.
- Delay không vượt maxDelay.
- Attempt lớn không gây overflow.
- Jitter nằm trong range dự kiến.
- Max attempts dừng đúng thời điểm.

Nếu dùng random jitter, inject random source hoặc clock để test có thể xác định. Tránh viết test dựa vào sleep thực tế; dùng virtual time hoặc kiểm tra giá trị delay được tính ra.

## 22. Reactive bulk và retry

Nếu ứng dụng dùng reactive API, bulk publisher cần xử lý item-level response trong reactive chain. Không gọi block để chờ kết quả.

Một luồng khái quát:

~~~java
return bulkGateway.send(operations)
    .flatMap(response -> classifyItems(response, metadata))
    .flatMapMany(classification -> processClassification(classification));
~~~

Nếu dùng Reactor retryWhen quanh toàn bộ bulk request, cần nhớ rằng retryWhen thường resubscribe publisher và có thể gửi lại toàn bộ request. Nó không tự biết item nào đã thành công trong partial response.

Với reactive bulk, nên:

- Phân loại item trong response.
- Tạo publisher riêng cho retry subset.
- Dùng delayElement hoặc retryWhen có backoff/jitter cho subset phù hợp.
- Giới hạn concurrency.
- Giữ metadata và idempotency key qua mọi lần retry.
- Không subscribe thủ công trong service.
- Không giữ một list retry vô hạn trong memory.

Reactive không thay đổi semantics của Bulk API: mỗi item vẫn có kết quả riêng và batch không phải transaction.

## 23. Quan sát và logging

Một hệ thống bulk đáng tin cậy cần metrics theo batch và item.

Metrics gợi ý:

- bulk_requests_total.
- bulk_items_total.
- bulk_items_succeeded_total.
- bulk_items_failed_total.
- bulk_item_failures{status,error_type}.
- bulk_retry_items_total.
- bulk_retry_exhausted_total.
- bulk_dead_letter_total.
- bulk_request_duration.
- bulk_batch_bytes.
- bulk_retry_queue_depth.

Log nên có:

- Batch ID.
- Operation type.
- Index.
- Document ID hoặc business key đã được phép ghi log.
- Attempt.
- Status.
- Error type.
- Correlation ID.
- Retry decision.

Không log toàn bộ document source mặc định. Dữ liệu có thể chứa thông tin cá nhân, token hoặc bí mật nghiệp vụ. Nếu cần lưu payload lỗi để replay, dùng kho lưu có phân quyền, retention và encryption phù hợp.

Alert khi:

- Item failure rate tăng đột ngột.
- 429 liên tục.
- Retry queue tăng nhanh.
- Dead-letter tăng.
- Retry exhausted vượt ngưỡng.
- Bulk latency tăng hoặc throughput giảm.
- Mapping errors xuất hiện sau deployment.

## 24. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Bulk trả HTTP 200 nhưng một số record thiếu | Không kiểm tra errors/items | Duyệt từng item response |
| Retry làm duplicate document | Dùng ID tự sinh hoặc không có idempotency key | Dùng ID xác định và reconcile |
| Batch retry làm tăng counter hai lần | Script increment không idempotent | Dedup event ID hoặc dùng operation idempotent |
| Item lỗi gắn sai source record | Không giữ thứ tự/correlation metadata | Ghép theo position và batch ID |
| Retry mapping error liên tục | Không phân biệt permanent/transient | Phân loại theo status và error type |
| Cluster tiếp tục trả 429 | Retry ngay, concurrency quá cao | Backoff, jitter và giảm tải |
| Timeout nhưng document đã được ghi | Response bị mất sau khi server xử lý | Reconcile theo ID/event ID |
| Create retry trả 409 | Lần trước có thể đã thành công | Đọc và đối chiếu document |
| Update trả 404 | Document chưa tồn tại hoặc index sai | Chọn not found/upsert theo nghiệp vụ |
| Version conflict lặp lại | Concurrent writers | Đọc lại và giải quyết theo concurrency policy |
| Retry queue tăng vô hạn | Không có max attempts/backpressure | Retry budget và dead-letter |
| Event mới bị event cũ ghi đè | Retry không giữ ordering/version | Partition theo key hoặc source version |
| Bulk method ném exception và mất chi tiết | Không đọc exception/failed item detail | Dùng API/response đúng version và test |
| saveAll được coi là atomic | Hiểu nhầm bulk semantics | Xử lý từng item |
| Reactive retry gửi lại cả batch | retryWhen bọc toàn request | Lọc retry subset trước khi resubscribe |

## 25. Quy trình xử lý một bulk batch

Một pipeline xử lý có thể áp dụng:

1. Tạo batch với giới hạn số item và byte.
2. Gán batch ID và giữ metadata cho từng operation.
3. Gửi request qua client đã cấu hình.
4. Nếu nhận response, ghép từng item theo thứ tự.
5. Đánh dấu item thành công.
6. Phân loại lỗi permanent, transient và conflict.
7. Gửi permanent failure vào quarantine/dead-letter.
8. Tạo retry batch chỉ từ transient failures.
9. Áp dụng backoff, jitter và retry budget.
10. Nếu timeout không có response, đánh dấu outcome ambiguous và reconcile theo operation ID.
11. Khi hết retry budget, ghi retry-exhausted record.
12. Phát metrics và cập nhật trạng thái batch.

Không đánh dấu toàn bộ batch completed chỉ vì một phần item thành công. Trạng thái batch nên phản ánh số item thành công, lỗi vĩnh viễn, đang retry và chưa rõ kết quả.

## 26. Bảng tra cứu nhanh

| Nhu cầu | Cách làm |
|---|---|
| Phát hiện bulk có lỗi item | Kiểm tra response.errors |
| Xác định item lỗi | Duyệt response.items và error/status |
| Ghép response với source | Giữ metadata cùng thứ tự operations |
| Retry lỗi 429/5xx tạm thời | Backoff, jitter và retry subset |
| Không retry lỗi mapping | Quarantine hoặc sửa payload |
| Xử lý version conflict | Đọc lại và áp dụng concurrency policy |
| Retry index an toàn hơn | ID ổn định và source xác định |
| Tránh duplicate do autogenerated ID | Dùng document ID từ business/event key |
| Reconcile create 409 | Đọc document và so sánh event ID/payload |
| Bảo vệ script increment | Idempotency guard hoặc dedup store |
| Xử lý timeout mơ hồ | Reconcile theo operation ID trước khi retry |
| Giới hạn retry | Max attempts, elapsed time và queue capacity |
| Xử lý lỗi không khắc phục | Dead-letter/quarantine |
| Giữ ordering | Partition theo document key hoặc source version |
| Kiểm tra Spring Data bulk | Test đúng bulk API và exception semantics của version |
| Kiểm tra reactive bulk | Phân loại response trong Publisher, không block |
| Theo dõi vận hành | Metrics theo batch và item |

Kiểm thử bulk cần chứng minh rằng ứng dụng đọc kết quả từng item, nhận diện partial failure và chỉ retry những thao tác có thể khắc phục. Bulk API không phải transaction, vì vậy item thành công vẫn có thể đã được ghi khi item khác thất bại. Retry phải có backoff, jitter, retry budget và phân loại lỗi; mapping/authentication errors cần được xử lý như lỗi lâu dài, còn 429/5xx thường cần giảm tải và thử lại có giới hạn. Tính lặp an toàn phụ thuộc operation: index với ID cố định và payload xác định thường dễ retry, trong khi create, ID tự sinh và script cộng dồn cần deduplication hoặc reconciliation. Với timeout không rõ kết quả, hãy đối chiếu document/event ID trước khi gửi lại. Giữ metadata theo từng item, kiểm thử cả partial response lẫn ambiguous outcome, và theo dõi retry/dead-letter để bulk ingestion có thể phục hồi mà không tạo duplicate hoặc áp dụng thay đổi nhiều lần.
