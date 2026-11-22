# HTTP 429, rejection, timeout và lỗi từng phần tử bulk

Khi ứng dụng Spring Data Elasticsearch ghi dữ liệu với tốc độ cao, Elasticsearch có thể không xử lý kịp lượng request đang đến. Ứng dụng có thể gặp HTTP 429, lỗi `es_rejected_execution_exception`, timeout hoặc một bulk response chỉ thành công một phần. Đây là các tình huống khác nhau và cần cách xử lý khác nhau.

Điểm quan trọng là **một bulk request không phải một transaction all-or-nothing**. Một response có thể xác nhận hàng trăm item thành công nhưng một số item khác thất bại. Nếu ứng dụng chỉ kiểm tra HTTP status hoặc chỉ nhìn cờ `errors`, nó có thể bỏ sót dữ liệu chưa được ghi hoặc gửi lại những item đã thành công.

Một chiến lược vận hành đáng tin cậy cần:

- Phân biệt lỗi từ chối toàn request với lỗi riêng từng item.
- Nhận diện áp lực tài nguyên và giảm tốc độ gửi.
- Phân biệt timeout có kết quả chưa rõ với lỗi được xác nhận thất bại.
- Retry có giới hạn, backoff và jitter.
- Chỉ retry item cần retry khi response đã cho biết kết quả từng item.
- Thiết kế ID/version và thao tác idempotent để retry an toàn.
- Đưa lỗi dữ liệu không thể tự phục hồi vào dead-letter queue.
- Theo dõi queue, rejection, latency, indexing pressure và tỷ lệ lỗi.

## 1. Bulk request có thể thất bại ở những cấp nào?

Một bulk request gồm nhiều thao tác index/create/update/delete. Khi gửi request, có thể xảy ra lỗi ở ba cấp:

1. **Request-level failure:** Elasticsearch hoặc tầng mạng từ chối/toàn request thất bại. Ứng dụng có thể không nhận được danh sách kết quả từng item.
2. **Item-level failure:** bulk response được trả về nhưng một hoặc nhiều thao tác riêng lẻ thất bại. Các item còn lại vẫn có thể thành công.
3. **Client/application failure:** client timeout, connection reset, ứng dụng bị cancel hoặc process dừng trước khi ghi nhận response. Trạng thái ở server có thể chưa rõ.

```text
Application
    |
    | Bulk request: A, B, C, D
    v
Elasticsearch
    |
    +-- Request rejected (HTTP 429)
    |       -> Không có kết quả item đầy đủ cho ứng dụng
    |
    +-- Bulk response received
    |       +-- A: success
    |       +-- B: success
    |       +-- C: item failure (429 / 400 / 409 ...)
    |       +-- D: success
    |
    +-- Response lost / client timeout
            -> Server có thể đã xử lý một phần hoặc toàn bộ
```

Không dùng chung một nhánh retry cho cả ba trường hợp. Request-level 429 thường yêu cầu gửi lại batch sau khi giảm tải; item-level 429 chỉ cần retry các item bị từ chối; timeout có thể cần đối soát hoặc retry idempotent vì ứng dụng không biết server đã thực hiện đến đâu.

## 2. HTTP 429 và `es_rejected_execution_exception`

HTTP 429 biểu thị server đang từ chối request vì không thể tiếp nhận thêm công việc tại thời điểm đó. Trong Elasticsearch, một nguyên nhân phổ biến là thread pool xử lý write/bulk đã đầy queue hoặc không còn capacity.

Một response có thể chứa lỗi tương tự:

```json
{
  "error": {
    "type": "es_rejected_execution_exception",
    "reason": "rejected execution ..."
  },
  "status": 429
}
```

`es_rejected_execution_exception` là tín hiệu quá tải hoặc thiếu capacity ở một thành phần xử lý. Nó không có nghĩa document sai mapping. Gửi lại ngay lập tức với cùng tốc độ thường làm tình hình tệ hơn.

### 2.1. Vì sao Elasticsearch từ chối write?

Các nguyên nhân thường gặp:

- Producer gửi bulk nhanh hơn tốc độ shard có thể index.
- Quá nhiều bulk request chạy đồng thời.
- Batch quá lớn, làm tăng thời gian xử lý và bộ nhớ cần thiết.
- Shard/node đang chịu tải cao do merge, disk I/O, CPU hoặc GC.
- Mapping/analyzer/ingest pipeline làm mỗi document tốn nhiều chi phí xử lý.
- Số shard hoặc routing khiến tải dồn vào một số shard/node.
- Search, aggregation hoặc workload khác cạnh tranh tài nguyên với indexing.
- Replica phải xử lý cùng lượng write và đang chậm.

Một cluster có thể vẫn ở trạng thái `green` nhưng write thread pool vẫn bị rejection. Cluster health không phải chỉ số duy nhất để kết luận cluster còn đủ capacity.

### 2.2. Thread pool write/bulk

Elasticsearch dùng thread pool để điều phối các loại công việc. Tên pool và cách triển khai có thể thay đổi theo phiên bản. Ở các phiên bản hiện đại, các thao tác write thường được xử lý qua thread pool `write`; một số phiên bản cũ hoặc tài liệu cũ có thể nhắc đến pool `bulk`.

Có thể xem thông tin thread pool:

```http
GET /_nodes/stats/thread_pool
```

Hoặc dùng CAT API để quan sát nhanh:

```http
GET /_cat/thread_pool?v
```

Các trường đáng chú ý:

| Trường | Ý nghĩa |
|---|---|
| `active` | Số thread đang xử lý công việc. |
| `queue` | Số công việc đang chờ trong queue. |
| `rejected` | Số công việc đã bị từ chối. |
| `completed` | Số công việc đã hoàn tất. |

Nếu `queue` thường xuyên gần giới hạn và `rejected` tăng liên tục, producer đang vượt khả năng xử lý hoặc cluster đang có bottleneck. Không cố tăng queue/thread pool một cách tùy tiện; queue lớn hơn có thể làm latency và memory pressure tăng mà không cải thiện throughput.

## 3. Phân biệt request-level 429 và item-level 429

Đây là phân biệt quan trọng nhất khi xử lý bulk.

### 3.1. Request-level 429

Elasticsearch từ chối toàn request trước khi trả kết quả bulk từng item. Ứng dụng nhận HTTP 429 hoặc exception tương ứng thay vì một response chứa đầy đủ trạng thái từng thao tác.

Trong trường hợp này, không có item-level response để biết từng document đã thành công hay chưa. Khi lỗi được xác nhận là request bị từ chối, có thể retry toàn batch sau backoff. Nếu response bị mất hoặc lỗi đến từ proxy/network, trạng thái không còn chắc chắn; khi đó phải dựa vào idempotency và đối soát.

### 3.2. Item-level 429 trong bulk response

Bulk API có thể trả HTTP response thành công ở cấp request nhưng có `errors: true`. Mỗi item có status riêng:

```json
{
  "took": 35,
  "errors": true,
  "items": [
    {
      "index": {
        "_index": "products",
        "_id": "P-100",
        "status": 201
      }
    },
    {
      "index": {
        "_index": "products",
        "_id": "P-101",
        "status": 429,
        "error": {
          "type": "es_rejected_execution_exception",
          "reason": "rejected execution ..."
        }
      }
    },
    {
      "index": {
        "_index": "products",
        "_id": "P-102",
        "status": 400,
        "error": {
          "type": "mapper_parsing_exception",
          "reason": "failed to parse field [price]"
        }
      }
    },
    {
      "index": {
        "_index": "products",
        "_id": "P-103",
        "status": 201
      }
    }
  ]
}
```

Trong ví dụ:

- `P-100` thành công.
- `P-101` bị từ chối tạm thời do quá tải.
- `P-102` có dữ liệu không tương thích mapping.
- `P-103` thành công.

Ứng dụng nên xác nhận hai item thành công, đưa `P-101` vào retry có giới hạn và đưa `P-102` vào luồng xử lý lỗi dữ liệu. Gửi lại cả bốn item sẽ tốn tài nguyên và có thể gây side effect không mong muốn.

### 3.3. Không suy luận chỉ từ HTTP status

HTTP status phản ánh kết quả request ở cấp giao thức. Với Bulk API, phải đọc cả body và từng phần tử `items`. Một HTTP 200 không đảm bảo mọi item thành công; `errors: true` là tín hiệu cần kiểm tra item detail.

Ngược lại, nếu nhận HTTP 429 mà không có bulk response, không được giả định ứng dụng đã có danh sách item thất bại. Đây là một tình huống request-level.

## 4. Các nhóm lỗi và cách phân loại

| Nhóm lỗi | Ví dụ | Có nên retry? | Hướng xử lý |
|---|---|---|---|
| Quá tải tạm thời | HTTP 429, `es_rejected_execution_exception` | Có, có giới hạn | Backoff, jitter, giảm concurrency và retry. |
| Timeout/connection | Read timeout, connection reset, gateway timeout | Có điều kiện | Trạng thái có thể chưa rõ; chỉ retry an toàn khi operation idempotent hoặc có đối soát. |
| Server tạm thời | HTTP 502/503/504 | Có điều kiện | Backoff và retry có giới hạn; kiểm tra khả năng request đã được xử lý. |
| Dữ liệu không hợp lệ | HTTP 400, `mapper_parsing_exception` | Không retry nguyên trạng | Sửa dữ liệu hoặc dead-letter. |
| Request quá lớn | HTTP 413 hoặc lỗi payload/request limit | Không retry nguyên batch | Chia nhỏ batch, xử lý document ngoại cỡ. |
| Xung đột version | HTTP 409, `version_conflict_engine_exception` | Không retry mù quáng | Đọc version/trạng thái và xử lý theo nghiệp vụ. |
| Xác thực/phân quyền | HTTP 401/403 | Không retry liên tục | Sửa credential/role; dừng job. |
| Index/cấu hình | Index không tồn tại, alias sai, pipeline thiếu | Không retry liên tục | Sửa cấu hình và kiểm tra lại. |
| Circuit breaker/resource | `circuit_breaking_exception` | Có điều kiện | Giảm tải, giảm batch/concurrency và retry sau khi resource ổn định. |

Classifier nên dựa vào status/error type ổn định, không dựa vào việc tìm một từ khóa tùy ý trong exception message. Message có thể thay đổi theo phiên bản và có thể chứa dữ liệu nhạy cảm.

## 5. Timeout không đồng nghĩa request thất bại

Timeout là một trong những tình huống khó xử lý nhất vì client có thể không biết Elasticsearch đã thực hiện thao tác hay chưa.

Ví dụ:

1. Ứng dụng gửi bulk request.
2. Elasticsearch nhận và ghi một số hoặc tất cả item.
3. Response bị chậm hoặc bị mất trên đường về.
4. Client hết thời gian chờ và ném timeout exception.

Ở phía ứng dụng, request thất bại vì không nhận được response. Nhưng ở phía Elasticsearch, một phần hoặc toàn bộ thao tác có thể đã thành công.

Vì vậy, timeout phải được coi là **outcome chưa xác định** trừ khi biết chắc request chưa được gửi/nhận.

### 5.1. Các loại timeout cần phân biệt

| Loại timeout | Ý nghĩa | Điều cần chú ý |
|---|---|---|
| Connection timeout | Không thiết lập được kết nối trong thời gian cho phép. | Request có thể chưa được gửi, nhưng cần xem transport và giai đoạn lỗi. |
| Read/response timeout | Client đã gửi request nhưng không nhận response kịp. | Server có thể đã xử lý một phần hoặc toàn bộ. |
| Request timeout ở proxy/gateway | Tầng trung gian ngừng chờ upstream. | Elasticsearch có thể vẫn tiếp tục xử lý sau khi proxy trả lỗi. |
| Application deadline/cancellation | Request bị hủy do deadline hoặc client disconnect. | Hủy phía ứng dụng không tự rollback thao tác đã đến Elasticsearch. |
| Elasticsearch operation timeout | Một thao tác nội bộ không hoàn tất trong thời hạn cấu hình. | Cần đọc loại API và response/error cụ thể; không đồng nhất với socket timeout. |

Không dùng một cấu hình timeout duy nhất để mô tả tất cả các tầng. HTTP client, reverse proxy, application deadline và API parameter có thể có semantics khác nhau.

### 5.2. Retry sau timeout cần idempotency

Nếu thao tác là index toàn bộ document với ID ổn định và cùng source state, gửi lại thường đưa document về cùng trạng thái cuối. Nhưng nếu thao tác là tăng counter hoặc script cộng dồn, gửi lại có thể áp dụng side effect hai lần.

Trước khi retry timeout:

- Xác định operation có idempotent không.
- Dùng ID ổn định hoặc event ID để nhận diện thao tác.
- Nếu có version, bảo đảm phiên bản cũ không ghi đè phiên bản mới.
- Với update không idempotent, kiểm tra trạng thái hoặc thiết kế idempotency key.
- Nếu cần, đối soát document theo ID/version trước khi gửi lại.

## 6. Xử lý lỗi từng item trong Bulk API

Một bulk response có `errors: true` không phải lý do để retry toàn bộ request. Hãy duyệt `items`, xác định item thành công và phân loại item lỗi.

Một luồng xử lý:

```text
Bulk response
    |
    v
errors == false ? ------ yes -----> Mark all items successful
    |
    no
    v
Inspect each item
    |
    +-- 2xx -----------------------> Acknowledge success
    |
    +-- 429 / transient ----------> Bounded retry queue
    |
    +-- mapping / validation -----> Dead-letter / data correction
    |
    +-- 409 conflict -------------> Business/version conflict handling
    |
    +-- auth/config --------------> Stop and alert
    |
    v
Persist outcomes and checkpoint
```

### 6.1. Lưu tương quan giữa request item và response item

Ứng dụng cần biết response item tương ứng với command/source record nào. Có thể dùng:

- Document ID ổn định.
- Operation type (index/create/update/delete).
- Source version/event ID.
- Batch sequence và item sequence.
- Routing value nếu document dùng custom routing.

Không chỉ giữ một danh sách ID nếu cùng ID có thể xuất hiện nhiều operation trong một batch. Lưu metadata đủ để xây dựng lại chính thao tác cần retry.

Bulk response giữ thứ tự item tương ứng với thứ tự operation trong request, nhưng adapter vẫn nên giữ command metadata và đối chiếu ID/operation rõ ràng để tránh nhầm khi có duplicate ID hoặc nhiều loại action.

### 6.2. Xác nhận item thành công ngay khi đã biết kết quả

Khi response xác nhận một item thành công, ghi nhận success/checkpoint theo cơ chế bền vững của job. Không đưa item đó trở lại retry queue chỉ vì item khác trong cùng bulk thất bại.

Nếu process chết sau khi Elasticsearch ghi thành công nhưng trước khi ứng dụng lưu checkpoint, item có thể được gửi lại. Đây là lý do deterministic ID, versioning và idempotent write rất quan trọng.

### 6.3. Chỉ retry tập item thất bại

Ví dụ batch ban đầu gồm 1.000 item:

- 985 item thành công.
- 10 item bị 429.
- 5 item lỗi mapping.

Xử lý phù hợp:

1. Ghi nhận 985 item thành công.
2. Retry 10 item 429 sau backoff.
3. Ghi 5 item lỗi mapping vào dead-letter, kèm error code và source reference đã được bảo vệ.
4. Chỉ đánh dấu batch hoàn tất khi mọi item đã được xác nhận thành công hoặc đã được ghi bền vững vào luồng xử lý lỗi theo chính sách.

## 7. Đọc Bulk response bằng Elasticsearch Java API Client

Khi cần kiểm soát item-level result, Elasticsearch Java API Client cung cấp `BulkResponse` với cờ `errors()` và danh sách item response.

Ví dụ khái quát:

```java
import co.elastic.clients.elasticsearch.core.BulkResponse;
import co.elastic.clients.elasticsearch.core.bulk.BulkResponseItem;

BulkResponse response = client.bulk(request);

if (response.errors()) {
    for (BulkResponseItem item : response.items()) {
        if (item.error() == null) {
            // Acknowledge this item as successful.
            continue;
        }

        int status = item.status();
        String documentId = item.id();
        String errorType = item.error().type();

        if (status == 429) {
            // Persist this item for bounded retry.
        } else if (status == 400) {
            // Send to validation/dead-letter handling.
        } else if (status == 409) {
            // Resolve version/create conflict according to business rules.
        } else {
            // Classify other statuses explicitly.
        }
    }
}
```

Đoạn code minh họa cách đọc response; kiểu request, package và accessor có thể khác theo version Java API Client. Trong code production, cần giữ mapping giữa từng response item và command gốc, đồng thời xử lý cả trường hợp request ném exception trước khi có `BulkResponse`.

Không log `item.error().reason()` nguyên bản nếu reason có thể chứa dữ liệu người dùng. Ghi error type/status và correlation reference đã được làm sạch; chỉ lưu diagnostic detail ở nơi có kiểm soát khi thực sự cần.

## 8. Bulk qua Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp các API bulk qua `ElasticsearchOperations`, ví dụ `bulkIndex`, `bulkUpdate` và `bulkDelete`. Các API này giúp ứng dụng không phải tự serialize NDJSON.

Ví dụ index batch:

```java
List<IndexQuery> queries = products.stream()
        .map(product -> new IndexQueryBuilder()
                .withId(product.getId())
                .withObject(product)
                .build())
        .toList();

operations.bulkIndex(queries, Product.class);
```

Khi dùng Spring Data, hãy đọc đúng contract trả về và exception của phiên bản đang pin. Một số wrapper có thể ném exception khi có item failure thay vì trả một response object tương tự low-level client. Nếu cần phân tích status/error type từng item, hãy dùng API/exception detail mà version đó cung cấp hoặc đặt một adapter rõ ràng quanh Elasticsearch Java API Client.

Không bắt mọi exception rồi retry cả batch mà không phân biệt request-level và item-level. Đặt logic phân loại ở một lớp adapter/service bulk để repository/service nghiệp vụ không phải biết chi tiết transport.

### 8.1. Tạo adapter cho bulk operation

Một abstraction có thể trả kết quả đã chuẩn hóa:

```java
public record BulkItemOutcome(
        String documentId,
        int status,
        String errorCode,
        boolean success
) {}

public record BulkWriteResult(
        int submitted,
        List<BulkItemOutcome> items
) {
    public List<BulkItemOutcome> failures() {
        return items.stream().filter(item -> !item.success()).toList();
    }
}
```

Adapter chuyển response/exception phụ thuộc client version thành `BulkWriteResult` của ứng dụng. Lớp retry có thể làm việc với status/error code ổn định mà không phụ thuộc message thô của Elasticsearch.

Trong adapter, không đưa raw document hoặc query vào `BulkItemOutcome`. Chỉ giữ metadata cần thiết để retry hoặc dead-letter; payload cần lưu riêng và có kiểm soát.

## 9. Exponential backoff và jitter

Khi Elasticsearch trả 429, retry ngay lập tức có thể làm queue đầy thêm. Dùng exponential backoff để tăng thời gian chờ giữa các lần thử.

Ví dụ minh họa:

```text
Attempt 1: wait khoảng 200 ms
Attempt 2: wait khoảng 400 ms
Attempt 3: wait khoảng 800 ms
Attempt 4: wait khoảng 1.6 s
Attempt 5: wait khoảng 3.2 s
```

Jitter thêm độ ngẫu nhiên vào thời gian chờ để nhiều worker không đồng loạt retry tại cùng một thời điểm. Một lựa chọn là full jitter:

\[
delay = random(0, min(maxDelay, baseDelay \times 2^{attempt}))
\]

Các giá trị trong ví dụ chỉ là điểm xuất phát. Hãy điều chỉnh theo latency, SLA, tải cluster và thời gian job cho phép.

### 9.1. Giới hạn retry

Một retry policy cần có:

- Số lần retry tối đa.
- Backoff ban đầu và thời gian chờ tối đa.
- Tổng deadline cho một item/job.
- Danh sách status/error type được retry.
- Điều kiện idempotency.
- Retry queue có giới hạn.
- Cách xử lý khi hết số lần retry.

Không retry vô hạn. Khi hết giới hạn, ghi item vào dead-letter hoặc đánh dấu job cần can thiệp, tùy mức độ quan trọng dữ liệu.

### 9.2. Ví dụ Retry với Reactor

Với reactive workflow, có thể dùng `retryWhen`:

```java
return sendBulk(batch)
        .retryWhen(Retry.backoff(4, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(5))
                .jitter(0.5)
                .filter(this::isRetryableRequestFailure));
```

Đây là ví dụ retry request-level. Nó chỉ phù hợp khi `sendBulk` phát error cho request-level failure và thao tác có semantics an toàn khi gửi lại. Với item-level failures trong một response bình thường, cần phân loại `items` rồi tạo publisher retry riêng cho những item lỗi; không dùng `retryWhen` trên toàn publisher để gửi lại toàn bộ batch.

## 10. Backpressure và giảm tải khi có rejection

Retry không đủ nếu producer vẫn gửi nhanh hơn Elasticsearch có thể xử lý. Cần điều chỉnh tốc độ nguồn.

Các biện pháp:

- Giảm số bulk request đang chạy đồng thời.
- Giảm batch size nếu payload lớn hoặc mỗi item nặng.
- Giới hạn số batch trong queue.
- Tạm dừng/giảm tốc producer khi queue đầy.
- Giảm concurrency tự động khi tỷ lệ 429 tăng.
- Tăng dần concurrency khi cluster ổn định trở lại.
- Chia tải theo tenant/routing nếu một shard bị nóng.

### 10.1. Bounded queue

Một queue hữu hạn tạo backpressure:

```java
BlockingQueue<List<IndexQuery>> queue = new ArrayBlockingQueue<>(4);
```

Khi có bốn batch đang chờ, producer phải chờ consumer xử lý thay vì tiếp tục tạo thêm batch. Queue không giới hạn có thể làm heap tăng không kiểm soát khi Elasticsearch chậm.

### 10.2. Giới hạn concurrency

Với Reactor:

```java
Flux<Void> writes = batches
        .flatMap(batch -> sendBatch(batch), 2);
```

Tham số concurrency giới hạn số batch đang được xử lý đồng thời. Nếu tăng lên quá cao, ứng dụng có thể tạo nhiều request và buffer hơn khả năng cluster.

Không có một con số concurrency đúng cho mọi cluster. Đo throughput, latency, 429, heap và queue depth rồi tăng/giảm từng bước.

### 10.3. Adaptive concurrency đơn giản

Một bộ điều khiển có thể giảm concurrency khi tỷ lệ rejection vượt ngưỡng và tăng lại chậm khi cluster ổn định:

```text
429 rate rises
      |
      v
Decrease in-flight bulk limit
      |
      v
Wait for cooldown window
      |
      v
Measure latency / queue / rejection
      |
      +---- still overloaded ----> decrease again
      |
      +---- stable --------------> increase slowly
```

Không tăng concurrency ngay sau một batch thành công đơn lẻ. Dùng cửa sổ đo đủ dài và giới hạn min/max để tránh dao động liên tục.

## 11. Chọn batch size phù hợp

Batch quá lớn có thể tạo payload khổng lồ, tốn heap, tăng thời gian xử lý và làm một lần retry trở nên đắt đỏ. Batch quá nhỏ tạo quá nhiều request và overhead mạng.

Chọn batch theo cả:

- Số document.
- Kích thước payload ước lượng/thực tế.
- Số shard nhận dữ liệu.
- Kích thước document và chi phí ingest pipeline.
- Latency và rejection rate.
- Memory của client và server.

Ví dụ một batch 500 document nhỏ có thể ổn, nhưng 500 document chứa JSON lớn hoặc nested arrays có thể quá nặng. Hãy đo byte size thay vì chỉ đếm document.

Khi gặp HTTP 413 hoặc lỗi request quá lớn, giảm batch/byte threshold và thử lại theo từng phần. Không retry nguyên request với cùng payload size.

### 11.1. Chia nhỏ tập item thất bại

Nếu một nhóm item vẫn bị rejection dù đã giảm concurrency, có thể chia nhóm retry thành batch nhỏ hơn. Việc này hữu ích khi một số document rất lớn hoặc gây áp lực riêng lên shard.

Không chia nhỏ vô hạn. Đặt minimum batch size và ngưỡng document ngoại cỡ để xử lý riêng.

## 12. Idempotency và an toàn khi retry

Retry chỉ đáng tin cậy nếu gửi lại cùng thao tác không làm dữ liệu sai hoặc tạo duplicate ngoài ý muốn.

### 12.1. Dùng document ID ổn định

Ví dụ dùng business ID làm Elasticsearch `_id`:

```java
IndexQuery query = new IndexQueryBuilder()
        .withId(product.getId())
        .withObject(product)
        .build();
```

Nếu cùng source record luôn tạo cùng `_id`, index lại cùng trạng thái thường ghi đè cùng document thay vì tạo thêm document mới.

Không sinh UUID mới mỗi lần retry nếu một event phải luôn cập nhật cùng một document. Nếu ID thay đổi, retry có thể tạo duplicate.

### 12.2. `index` và `create` có semantics khác nhau

- `index`: tạo mới hoặc thay thế document theo ID.
- `create`: chỉ tạo mới; nếu ID đã tồn tại thì trả conflict.

Với at-least-once delivery, một `create` có thể thành công ở lần đầu nhưng response bị mất. Retry sẽ gặp 409 vì document đã tồn tại. Ứng dụng cần xác minh document có phải cùng event/source version hay không trước khi coi conflict là thành công.

### 12.3. Update cộng dồn không tự idempotent

Ví dụ script tăng số lượng:

```json
{
  "script": {
    "source": "ctx._source.view_count += params.delta",
    "params": { "delta": 1 }
  }
}
```

Nếu request đã thành công nhưng client timeout rồi gửi lại, `view_count` có thể tăng hai lần.

Các lựa chọn:

- Dùng event ID đã xử lý để bỏ qua duplicate.
- Ghi trạng thái tuyệt đối thay vì cộng dồn nếu domain cho phép.
- Dùng version/source sequence để loại event cũ.
- Lưu idempotency record bền vững ở tầng ứng dụng.

### 12.4. Optimistic concurrency control

Elasticsearch hỗ trợ `_seq_no` và `_primary_term` để ngăn ghi đè document đã thay đổi kể từ lần đọc. Khi update có điều kiện version, conflict 409 cần được xử lý theo nghiệp vụ, không retry payload cũ vô hạn.

Nếu migration/replay dựa trên version nguồn, hãy đảm bảo version phản ánh thứ tự thay đổi có thẩm quyền. Không dùng timestamp không ổn định làm version nếu có thể có event đến sai thứ tự.

## 13. Xử lý lỗi mapping và validation

Lỗi mapping thường là lỗi dữ liệu, không phải quá tải:

```json
{
  "type": "mapper_parsing_exception",
  "reason": "failed to parse field [price]"
}
```

Ví dụ field `price` được mapping numeric nhưng source gửi chuỗi không chuyển đổi được. Retry cùng payload không làm lỗi biến mất.

Quy trình xử lý:

1. Ghi nhận item ID/reference và error type.
2. Xác định field/type lỗi bằng diagnostic đã được làm sạch.
3. Đưa item vào dead-letter hoặc trạng thái cần sửa dữ liệu.
4. Sửa source/mapping/transform.
5. Reprocess item bằng thao tác có idempotency.

Không retry lỗi 400 vô hạn. Cũng không bỏ qua mọi lỗi 400 một cách mù quáng: có thể là query/request sai hoặc lỗi cấu hình cần dừng job.

## 14. Dead-letter queue cho item không thể xử lý

Dead-letter queue (DLQ) lưu item thất bại không thể retry tự động hoặc đã hết retry budget.

Một record DLQ nên chứa:

- Job/batch ID.
- Document ID hoặc source reference đã được pseudonymize theo chính sách.
- Operation type.
- Error code/type và status.
- Số lần retry.
- Thời điểm lỗi gần nhất.
- Source version/event ID.
- Reference đến payload được bảo vệ nếu cần reprocess.

Không nhất thiết lưu nguyên document trong DLQ. Nếu payload có PII/secret, cần mã hóa, phân quyền, audit và retention ngắn. Không ghi payload gốc vào application log để thay thế DLQ.

### 14.1. Phân biệt retry queue và DLQ

| Retry queue | Dead-letter queue |
|---|---|
| Chứa lỗi tạm thời có khả năng phục hồi. | Chứa lỗi dữ liệu/logic hoặc item đã hết retry budget. |
| Có lịch backoff và giới hạn attempt. | Chờ điều tra, sửa dữ liệu hoặc reprocess có kiểm soát. |
| Được xử lý tự động theo policy. | Không tự động lặp vô hạn. |
| Ví dụ 429, một số timeout. | Ví dụ mapping parse error, invalid field, conflict cần nghiệp vụ. |

## 15. Timeout và request cancellation trong ứng dụng

Timeout có thể được cấu hình ở nhiều tầng:

- HTTP client connect timeout.
- HTTP client response/read timeout.
- Connection pool acquire timeout.
- Application request deadline.
- Reverse proxy/gateway timeout.
- Elasticsearch API timeout/operation wait.

Hãy đặt các timeout theo một deadline tổng thể hợp lý. Nếu proxy timeout ngắn hơn client timeout, ứng dụng có thể chỉ nhận lỗi từ proxy. Nếu application deadline kết thúc nhưng client vẫn tiếp tục request nền, thao tác có thể hoàn tất sau khi caller đã bỏ cuộc.

### 15.1. Không retry chồng tầng vô hạn

Nếu HTTP client tự retry ba lần, service retry năm lần và queue consumer retry mười lần, một thao tác có thể được gửi lại nhiều lần hơn dự kiến.

Thiết kế một retry budget tổng thể:

- Chọn tầng sở hữu retry chính.
- Giới hạn retry ở client/service/consumer.
- Ghi attempt count và correlation ID.
- Không retry đồng thời ở nhiều tầng nếu không tính tổng số lần.
- Dùng idempotency để bảo vệ các lần gửi lại.

### 15.2. Phân biệt timeout với server-side `timeout` parameter

Một API parameter tên `timeout` có thể điều khiển việc chờ điều kiện nội bộ, ví dụ shard availability, chứ không nhất thiết giới hạn thời gian HTTP client chờ response. Hãy đọc đúng API đang gọi và cấu hình transport tương ứng.

Không giải quyết socket timeout bằng cách chỉ tăng Elasticsearch `timeout` parameter nếu vấn đề nằm ở network/client/proxy.

## 16. Theo dõi cluster khi gặp 429/rejection

Khi tỷ lệ 429 tăng, cần kiểm tra nhiều tín hiệu cùng lúc.

### 16.1. Thread pool stats

```http
GET /_nodes/stats/thread_pool
```

Xem `active`, `queue`, `rejected` và `completed` của pool liên quan đến write. So sánh counter `rejected` theo thời gian, không chỉ xem một snapshot đơn lẻ.

### 16.2. Indexing pressure

```http
GET /_nodes/stats/indexing_pressure
```

Indexing pressure cung cấp tín hiệu về memory pressure từ hoạt động indexing ở node. Tên field và chi tiết response có thể thay đổi theo Elasticsearch version.

### 16.3. Cluster và node health

```http
GET /_cluster/health
```

```http
GET /_cat/nodes?v
```

```http
GET /_cat/indices/products?v
```

Kiểm tra node có bị mất, shard relocation, unassigned shard, disk pressure hoặc tải mất cân bằng không.

### 16.4. Các chỉ số ứng dụng cần ghi

| Metric | Mục đích |
|---|---|
| `bulk_requests_total` | Tổng số request bulk. |
| `bulk_request_duration` | Latency request bulk. |
| `bulk_items_submitted_total` | Số item đã gửi. |
| `bulk_items_succeeded_total` | Số item thành công. |
| `bulk_items_failed_total` | Số item lỗi. |
| `bulk_rejected_total` | Số request/item bị 429 hoặc rejection. |
| `bulk_retry_total` | Số lần retry. |
| `bulk_dead_letter_total` | Số item vào DLQ. |
| `bulk_payload_bytes` | Kích thước payload. |
| `bulk_in_flight` | Số request đang chạy. |
| `bulk_queue_depth` | Số batch đang chờ. |
| `bulk_timeout_total` | Số timeout theo loại. |
| `bulk_retry_exhausted_total` | Số item hết retry budget. |

Không dùng document ID, customer ID, email hoặc query string làm metric label vì cardinality cao và có thể làm lộ dữ liệu. Dùng label có tập giá trị hữu hạn như operation, status class, error category và index group.

## 17. Logging an toàn khi chẩn đoán lỗi

Khi lỗi bulk, log đủ metadata để tìm nguyên nhân:

```java
log.warn(
        "Elasticsearch bulk partially failed index={} batchId={} total={} succeeded={} failed={} retryable={} permanent={} durationMs={}",
        indexAlias,
        batchId,
        total,
        succeeded,
        failed,
        retryable,
        permanent,
        duration.toMillis()
);
```

Tránh log:

- Toàn bộ entity/document source.
- Full query DSL nếu chứa literal người dùng.
- Authorization header/token.
- Exception message nguyên bản chưa được phân loại.
- Payload dead-letter có PII.

Với item lỗi, ghi error code/type, status và reference đã được pseudonymize nếu cần liên kết log. Chi tiết nhạy cảm nên nằm trong kho lỗi có kiểm soát, không nằm trong log phổ thông.

## 18. Kiến trúc xử lý bulk bền vững

Một pipeline có thể được tổ chức như sau:

```text
Source database / queue
          |
          v
      Batch builder
   (count + byte limit)
          |
          v
   Bounded in-flight queue
          |
          v
   Bulk request adapter
          |
          v
     Bulk response
          |
     +----+-------------------+
     |                        |
     v                        v
Item successes           Item failures
     |                        |
     v                        +-- retryable -> retry queue
Checkpoint                   |
                              +-- permanent -> DLQ
                              |
                              +-- conflict -> business handler
```

Adapter chịu trách nhiệm giao tiếp với Elasticsearch và chuẩn hóa kết quả. Retry worker chỉ xử lý item đã phân loại. Checkpoint chỉ tiến khi mọi item của batch đã được xử lý hoặc lỗi đã được lưu bền vững vào nơi phù hợp.

### 18.1. Checkpoint đúng thời điểm

Không commit checkpoint trước khi biết item nào thành công và item nào đã được lưu vào retry/DLQ. Nếu checkpoint tiến qua item lỗi mà không lưu durable failure, item có thể bị bỏ qua vĩnh viễn.

Nếu process chết sau khi Elasticsearch ghi thành công nhưng trước khi checkpoint commit, item có thể được gửi lại. Idempotent operation và deterministic ID giúp trường hợp này an toàn hơn.

### 18.2. Giới hạn retry queue

Retry queue phải có capacity hữu hạn và persistence phù hợp. Nếu queue đầy, producer cần backpressure hoặc job phải dừng có kiểm soát. Không chuyển tất cả lỗi vào một `List` trong heap rồi tiếp tục đọc nguồn.

## 19. Ví dụ phân loại item và xây retry plan

Một classifier có thể chuyển status/error type thành category:

```java
enum FailureCategory {
    RETRYABLE,
    PERMANENT_DATA_ERROR,
    CONFLICT,
    CONFIGURATION_ERROR,
    UNKNOWN
}

FailureCategory classify(int status, String errorType) {
    if (status == 429
            || status == 502
            || status == 503
            || status == 504) {
        return FailureCategory.RETRYABLE;
    }

    if (status == 400
            || "mapper_parsing_exception".equals(errorType)) {
        return FailureCategory.PERMANENT_DATA_ERROR;
    }

    if (status == 409) {
        return FailureCategory.CONFLICT;
    }

    if (status == 401 || status == 403 || status == 404) {
        return FailureCategory.CONFIGURATION_ERROR;
    }

    return FailureCategory.UNKNOWN;
}
```

Classifier này chỉ là điểm khởi đầu. Cần xem context cụ thể: HTTP 404 có thể là index missing (cấu hình) hoặc document not found (nghiệp vụ); 409 có thể là create conflict hoặc optimistic concurrency conflict; 429 có thể là rejection hoặc circuit breaker. Không phân loại chỉ theo status nếu error type cung cấp ngữ cảnh cần thiết.

Kết quả classifier nên được đưa vào policy:

```text
RETRYABLE             -> retry with backoff, within budget
PERMANENT_DATA_ERROR  -> dead-letter and alert/report
CONFLICT              -> read/compare version, then business resolution
CONFIGURATION_ERROR  -> stop affected job and alert
UNKNOWN               -> quarantine, preserve diagnostics safely
```

## 20. Khi nào nên dừng job thay vì retry?

Không phải mọi lỗi đều nên xử lý ở cấp item. Dừng job nếu:

- Credential hết hạn hoặc user mất quyền.
- Index/alias đích không tồn tại hoặc trỏ sai.
- Mapping/template/pipeline chưa được cài đặt.
- Tỷ lệ lỗi permanent vượt ngưỡng.
- Retry queue/DLQ không thể ghi bền vững.
- Checkpoint store lỗi, khiến tiến độ không còn đáng tin cậy.
- Cluster đang quá tải kéo dài và retry budget đã hết.
- Dữ liệu nguồn không nhất quán hoặc version ordering không thể xác định.

Tiếp tục ghi trong các tình huống này có thể tạo một index thiếu dữ liệu hoặc không thể đối soát.

## 21. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| HTTP 429 tăng liên tục | Producer/concurrency vượt capacity Elasticsearch. | Giảm in-flight request, backoff và kiểm tra write queue. |
| Bulk trả HTTP 200 nhưng `errors=true` | Một số item thất bại. | Kiểm tra từng `items[]`; chỉ retry item cần retry. |
| Retry toàn batch gây tải tăng | Item thành công cũng bị gửi lại. | Phân loại response và retry tập item lỗi. |
| Timeout rồi document bị duplicate | Retry thao tác không idempotent hoặc ID được sinh mới. | Dùng deterministic ID/event ID và versioning. |
| Timeout nhưng không biết trạng thái | Response bị mất sau khi server có thể đã ghi. | Coi là outcome chưa xác định; đối soát hoặc retry idempotent. |
| Mapping error bị retry mãi | Không phân biệt lỗi permanent và transient. | Dead-letter và sửa dữ liệu/mapping. |
| 429 vẫn tăng dù đã tăng thread pool | Bottleneck nằm ở CPU, disk, shard, merge hoặc indexing pressure. | Đo cluster; giảm producer và xử lý bottleneck thực. |
| Batch lớn gây timeout/413 | Payload quá lớn hoặc xử lý quá lâu. | Giảm batch theo byte/count và xử lý document lớn riêng. |
| Retry đồng loạt làm cluster quá tải | Không có jitter, nhiều worker retry cùng lúc. | Exponential backoff + jitter và adaptive concurrency. |
| Queue trong ứng dụng tăng vô hạn | Producer không bị backpressure. | Bounded queue và giới hạn số batch in-flight. |
| Checkpoint bỏ qua item lỗi | Commit checkpoint trước khi persist retry/DLQ. | Chỉ commit khi mọi item đã được account for bền vững. |
| `create` retry gặp 409 | Lần trước có thể đã thành công nhưng response mất. | Kiểm tra event/version/document rồi quyết định conflict có phải duplicate expected. |
| Log chứa document source khi lỗi | Dump toàn request/exception. | Log status/error type/count và reference đã làm sạch. |

## 22. Checklist xử lý sự cố 429/rejection/timeout

Khi incident xảy ra, có thể đi theo thứ tự:

1. **Xác định cấp lỗi:** request-level, item-level hay client timeout/connection.
2. **Đọc response:** kiểm tra HTTP status, `errors`, item status và error type.
3. **Giảm tải ngay:** hạ concurrency/in-flight limit; tạm giảm hoặc pause producer nếu cần.
4. **Kiểm tra cluster:** write thread pool queue/rejected, indexing pressure, node health, disk, CPU và GC.
5. **Phân loại item:** transient, permanent data error, conflict, configuration hoặc unknown.
6. **Retry có giới hạn:** chỉ retry request/item phù hợp, backoff và jitter.
7. **Bảo đảm idempotency:** deterministic ID, event ID, version hoặc reconciliation.
8. **Persist failure:** lưu retry/DLQ và checkpoint bền vững.
9. **Theo dõi phục hồi:** rejection rate, latency, retry queue depth và DLQ count.
10. **Đối soát sau incident:** so sánh source/destination và xác minh item hết retry budget.

## 23. Những điểm cần nhớ

- HTTP 429 và `es_rejected_execution_exception` thường báo hiệu Elasticsearch đang thiếu capacity hoặc từ chối công việc.
- Request-level 429 khác item-level 429 trong bulk response.
- Bulk response có thể HTTP 200 nhưng `errors=true`; phải kiểm tra từng item.
- Item thành công không được đưa lại vào retry chỉ vì item khác thất bại.
- Timeout có thể xảy ra sau khi server đã xử lý request; coi trạng thái là chưa xác định nếu không có bằng chứng ngược lại.
- Retry cần exponential backoff, jitter, giới hạn attempt và tổng deadline.
- Retry 429 phải đi cùng giảm concurrency/backpressure; retry nhanh không giải quyết overload.
- Mapping/validation error thường là permanent và cần dead-letter hoặc sửa dữ liệu.
- 409 conflict cần xử lý theo version/operation semantics, không retry mù quáng.
- Dùng ID ổn định, event ID và versioning để retry an toàn.
- Bounded queue, batch size theo byte và concurrency limit giúp bảo vệ heap/client/cluster.
- Theo dõi write thread pool, indexing pressure, latency, 429, retry và DLQ.
- Không log raw document, query hoặc exception reason nếu có thể chứa dữ liệu nhạy cảm.
- Checkpoint chỉ tiến khi mọi item đã được xử lý hoặc lỗi đã được lưu bền vững.

HTTP 429, rejection, timeout và lỗi từng phần tử bulk là những tín hiệu khác nhau của một pipeline ghi dữ liệu. Hãy xác định request đã bị từ chối, một vài item thất bại hay kết quả chưa rõ vì timeout; sau đó giảm tải, phân loại lỗi và retry đúng phạm vi với idempotency. Khi kết hợp backpressure, retry có giới hạn, dead-letter và checkpoint bền vững, ứng dụng có thể phục hồi khỏi quá tải mà không âm thầm bỏ sót hoặc nhân đôi dữ liệu.

## Tài liệu tham khảo

- [Elasticsearch — Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html)
- [Elasticsearch — Tune for indexing speed](https://www.elastic.co/guide/en/elasticsearch/reference/current/tune-for-indexing-speed.html)
- [Elasticsearch — Thread pool settings](https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-threadpool.html)
- [Elasticsearch — Nodes stats API](https://www.elastic.co/guide/en/elasticsearch/reference/current/cluster-nodes-stats.html)
- [Elasticsearch — Indexing pressure](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-modules-indexing-pressure.html)
- [Spring Data Elasticsearch — ElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/ElasticsearchOperations.html)
- [Project Reactor — Retry](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html)
