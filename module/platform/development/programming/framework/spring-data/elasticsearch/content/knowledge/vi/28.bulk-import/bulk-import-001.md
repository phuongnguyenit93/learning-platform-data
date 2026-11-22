# Bulk API và sự khác biệt với nhiều yêu cầu đơn lẻ

Elasticsearch Bulk API cho phép gửi nhiều thao tác ghi trong cùng một HTTP request. Thay vì gọi Index API, Update API hoặc Delete API riêng cho từng document, ứng dụng gom các thao tác thành một batch rồi gửi tới endpoint `/_bulk` hoặc `/{index}/_bulk`. Elasticsearch phân phối từng action tới shard chứa document và trả kết quả riêng cho từng action.

Bulk API thường cải thiện throughput vì giảm số lần round trip HTTP, giảm overhead thiết lập request và giúp ứng dụng điều chỉnh kích thước batch. Tuy nhiên, một bulk request **không phải transaction**: một số item có thể thành công trong khi item khác thất bại. HTTP status của toàn request không đủ để kết luận tất cả document đã được ghi thành công. Ứng dụng phải đọc `errors` và từng phần tử trong `items`, phân loại lỗi, rồi retry có chọn lọc.

Trong Spring Data Elasticsearch, có thể dùng các bulk operation của `ElasticsearchOperations` hoặc reactive operations để gửi nhiều `IndexQuery`/`UpdateQuery`. Khi dùng repository `saveAll`, cần hiểu hành vi của phiên bản Spring Data đang chạy và không mặc định rằng mọi implementation đều tạo đúng một Bulk API request. Nếu cần kiểm soát batch size, refresh policy và lỗi từng item, hãy dùng bulk API tường minh.

## 1. Vì sao cần Bulk API?

Giả sử cần index 10.000 sản phẩm. Nếu ứng dụng gửi từng document bằng một request riêng:

```text
Ứng dụng                         Elasticsearch
   |                                  |
   |---- PUT document 1 -------------->|
   |<--- response 1 ------------------|
   |---- PUT document 2 -------------->|
   |<--- response 2 ------------------|
   |---- PUT document 3 -------------->|
   |<--- response 3 ------------------|
   |                ...               |
   |---- PUT document 10000 ---------->|
   |<--- response 10000 --------------|
```

Mỗi thao tác riêng có overhead HTTP, request parsing, coordination và response. Nếu mạng có latency, thời gian chờ round trip có thể chiếm phần đáng kể.

Với Bulk API:

```text
Ứng dụng                         Elasticsearch
   |                                  |
   |---- một bulk request ------------>|
   |     action 1                     |
   |     source 1                     |
   |     action 2                     |
   |     source 2                     |
   |     ...                          |
   |     action N                     |
   |<--- một bulk response ------------|
```

Một request mang nhiều action giúp giảm round trip và tăng hiệu quả sử dụng connection. Elasticsearch vẫn thực hiện từng thao tác trên shard tương ứng; bulk không biến nhiều document thành một thao tác nguyên tử.

### Lợi ích chính

- Giảm số HTTP request và network round trip.
- Tăng throughput khi ingest nhiều document.
- Cho phép điều chỉnh batch size theo byte và latency.
- Có thể kết hợp index, create, update và delete trong cùng batch.
- Dễ tổ chức retry theo từng item thất bại.
- Phù hợp với import, đồng bộ dữ liệu, event consumer và reindex pipeline.

### Chi phí và giới hạn

- Request và response lớn hơn, tiêu thụ bộ nhớ nhiều hơn.
- Một batch có thể chứa item thành công và thất bại đồng thời.
- Batch quá lớn có thể tăng latency, heap pressure và nguy cơ timeout.
- Retry sai cách có thể ghi trùng hoặc ghi đè dữ liệu mới hơn.
- Bulk API không bảo đảm transaction giữa các document.

## 2. So sánh Bulk API với nhiều request đơn lẻ

| Tiêu chí | Nhiều request đơn lẻ | Bulk API |
|---|---|---|
| Số HTTP round trip | Một round trip cho mỗi thao tác | Một round trip cho một batch |
| Throughput khi ingest lớn | Thường thấp hơn do overhead request | Thường cao hơn nếu batch được điều chỉnh phù hợp |
| Kích thước payload | Nhỏ và độc lập | Có thể lớn, gồm nhiều action/source |
| Kết quả | Một response cho mỗi thao tác | Một response có kết quả riêng cho từng item |
| Xử lý lỗi | Lỗi gắn với request tương ứng | Phải kiểm tra từng item; có thể thành công một phần |
| Retry | Retry request thất bại | Retry chọn lọc item phù hợp |
| Thứ tự | Do ứng dụng điều phối từng request | Action có thứ tự trong payload, nhưng xử lý trên nhiều shard không phải transaction toàn cục |
| Điều chỉnh tải | Giới hạn số request đồng thời | Giới hạn batch size và số bulk request đồng thời |
| Phù hợp | Ghi đơn lẻ, read-after-write, thao tác tương tác | Import, batch ingestion, đồng bộ và xử lý lượng lớn |

Bulk không nhất thiết nhanh hơn trong mọi trường hợp. Với một document đơn lẻ, gọi Index API trực tiếp thường đơn giản và không có lợi ích khi tạo một bulk request chỉ chứa một action. Bulk phát huy hiệu quả khi có nhiều thao tác độc lập để gom chung.

## 3. Cấu trúc NDJSON của Bulk API

Bulk API dùng NDJSON (Newline Delimited JSON). Mỗi dòng là một JSON object độc lập. Với action có source document, dòng metadata được theo sau bởi dòng source.

Ví dụ:

```http
POST /_bulk
Content-Type: application/x-ndjson

{ "index": { "_index": "products", "_id": "p-100" } }
{ "name": "Wireless Mouse", "status": "ACTIVE" }
{ "index": { "_index": "products", "_id": "p-101" } }
{ "name": "Mechanical Keyboard", "status": "ACTIVE" }
```

Các quy tắc quan trọng:

- Mỗi dòng JSON phải là một object hợp lệ.
- Metadata action đứng trên dòng riêng.
- `index`, `create` và `update` có thêm dòng nội dung theo định dạng của action.
- `delete` chỉ cần dòng metadata, không có dòng source theo sau.
- Các dòng được phân tách bằng newline `\n`.
- Payload phải kết thúc bằng newline cuối cùng.
- Content type nên là `application/x-ndjson`.

Không gửi một JSON array như `[ {...}, {...} ]` tới Bulk API. Đó không phải định dạng NDJSON mà endpoint yêu cầu.

## 4. Các action trong Bulk API

Bulk API hỗ trợ bốn action chính:

| Action | Mục đích | Dòng tiếp theo |
|---|---|---|
| `index` | Tạo document hoặc thay thế document cùng ID | Source document |
| `create` | Chỉ tạo mới nếu ID chưa tồn tại | Source document |
| `update` | Cập nhật một phần hoặc chạy update script | Update body |
| `delete` | Xóa document theo ID | Không có |

### `index`: tạo hoặc thay thế

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "index": { "_id": "p-100" } }
{ "name": "Wireless Mouse", "price": 29.99 }
```

Nếu document ID chưa tồn tại, Elasticsearch tạo document. Nếu ID đã tồn tại, nội dung `_source` được thay thế bằng source mới. Vì vậy, khi dùng `index`, hãy gửi đầy đủ document mà ứng dụng muốn lưu.

### `create`: chỉ tạo nếu chưa tồn tại

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "create": { "_id": "p-101" } }
{ "name": "Keyboard", "price": 79.00 }
```

Nếu ID đã tồn tại, item tương ứng thất bại với conflict. `create` hữu ích khi cần phát hiện ID trùng thay vì âm thầm thay thế document.

### `update`: cập nhật một phần

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "update": { "_id": "p-100" } }
{ "doc": { "price": 27.99 } }
```

Update body có thể chứa `doc`, `doc_as_upsert`, `upsert`, script và các tùy chọn được hỗ trợ. Chọn semantics rõ ràng để tránh vô tình tạo document mới hoặc ghi đè field.

### `delete`: xóa document

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "delete": { "_id": "p-101" } }
```

Không thêm dòng source sau action `delete`; nếu thêm, parser sẽ hiểu sai ranh giới action tiếp theo.

## 5. Chỉ định index và document ID

Có thể chỉ định index trong URL:

```http
POST /products/_bulk
```

Khi đó action có thể bỏ `_index`:

```json
{ "index": { "_id": "p-100" } }
{ "name": "Mouse" }
```

Hoặc gửi tới `/_bulk` và chỉ định index trong từng action:

```json
{ "index": { "_index": "products", "_id": "p-100" } }
{ "name": "Mouse" }
{ "index": { "_index": "categories", "_id": "c-100" } }
{ "name": "Accessories" }
```

Cách thứ hai cho phép nhiều index trong một bulk request. Cần kiểm tra quyền truy cập trên tất cả index mà request có thể chạm tới.

### Dùng ID ổn định

Đối với đồng bộ từ database, thường dùng primary key nguồn làm `_id` để một lần replay cập nhật cùng document thay vì tạo bản sao mới.

```text
database product.id = p-100
              |
              v
Elasticsearch _id = p-100
```

ID ổn định giúp upsert và retry dễ idempotent hơn. Nếu mỗi lần retry tạo ID ngẫu nhiên, cùng một bản ghi nguồn có thể xuất hiện thành nhiều document.

## 6. Bulk response: kiểm tra từng item

Một bulk request thường trả response tổng thể với trường `errors` và danh sách `items`:

```json
{
  "took": 12,
  "errors": true,
  "items": [
    {
      "index": {
        "_index": "products",
        "_id": "p-100",
        "status": 201,
        "result": "created"
      }
    },
    {
      "index": {
        "_index": "products",
        "_id": "p-101",
        "status": 400,
        "error": {
          "type": "mapper_parsing_exception",
          "reason": "failed to parse field [price]"
        }
      }
    }
  ]
}
```

Trong ví dụ, request bulk đã hoàn tất nhưng `p-100` thành công còn `p-101` thất bại. HTTP status của request có thể vẫn là 200. Ứng dụng phải kiểm tra:

- `errors`: có ít nhất một item thất bại hay không.
- `items`: kết quả tương ứng với từng action đã gửi.
- `status`: HTTP status của từng item.
- `error.type` và `error.reason`: nguyên nhân thất bại.
- `_id`, `_index` và action: xác định item cần xử lý.

Response items được trả theo thứ tự action trong request, giúp ứng dụng đối chiếu với input batch. Tuy nhiên, đừng coi bulk là transaction có thứ tự toàn cục giữa nhiều shard hoặc nhiều document.

### Không chỉ kiểm tra HTTP status

Đoạn code chỉ kiểm tra HTTP 200 là chưa đủ:

```java
if (response.statusCode() == 200) {
    markWholeBatchSuccessful();
}
```

Phải duyệt kết quả từng item và chỉ đánh dấu batch hoàn tất khi tất cả item đã được xử lý theo chính sách nghiệp vụ.

## 7. Bulk API không phải transaction

Bulk API giảm overhead request nhưng không tạo transaction bao trùm toàn bộ action. Nếu một item lỗi mapping, các item khác vẫn có thể thành công. Elasticsearch không tự rollback những item đã thành công khi một item khác thất bại.

Ví dụ:

```text
Bulk request gồm A, B, C, D
       |
       +--> A: thành công
       +--> B: lỗi mapping
       +--> C: thành công
       +--> D: lỗi version conflict

Kết quả: A và C vẫn được ghi.
        B và D cần xử lý riêng.
```

Nếu nghiệp vụ yêu cầu tất cả thay đổi phải cùng thành công hoặc cùng rollback, Bulk API không đáp ứng semantics transaction đó. Hãy dùng transaction ở nguồn dữ liệu chuẩn hoặc thiết kế saga/compensation phù hợp; không mô phỏng transaction bằng cách gửi bulk rồi xóa ngược những item đã thành công nếu chưa xử lý được mọi failure mode.

## 8. Vì sao Bulk API thường nhanh hơn?

Bulk API giảm một số chi phí lặp lại:

1. Ít lần mở/gửi HTTP request hơn.
2. Ít network round trip hơn.
3. Giảm overhead parse/dispatch ở tầng request.
4. Có thể phân phối nhiều action tới các shard trong cùng batch.
5. Ứng dụng có thể điều chỉnh batch size để tận dụng throughput của cluster.

Tuy nhiên, Elasticsearch vẫn phải parse từng action, phân phối tới shard, index document, cập nhật translog và xử lý refresh/merge theo cấu hình. Bulk không làm chi phí xử lý mỗi document biến mất.

### Bulk quá nhỏ

Nếu batch chỉ có một vài document, overhead tạo và gửi batch có thể không đáng kể hơn request riêng. Throughput có thể bị giới hạn bởi số round trip và scheduling.

### Bulk quá lớn

Batch lớn có thể:

- Tăng memory ở ứng dụng để dựng payload và giữ response.
- Tăng thời gian xử lý một request.
- Tăng nguy cơ timeout hoặc request bị từ chối.
- Làm một lần retry phải xử lý nhiều item hơn.
- Tạo áp lực lớn lên coordinating node và data nodes.

Mục tiêu là tìm batch size đủ lớn để giảm overhead nhưng vẫn nằm trong ngân sách bộ nhớ và latency.

## 9. Chọn batch size theo byte, không chỉ theo số document

Một batch 1.000 document nhỏ có thể nhẹ hơn 100 document có source rất lớn. Vì vậy, không nên chỉ cấu hình `batchSize = 1000` mà bỏ qua kích thước payload.

Các yếu tố cần xem xét:

- Kích thước trung bình và percentile cao của source JSON.
- Số lượng field và nested objects.
- Kích thước metadata/action line.
- Số shard nhận dữ liệu.
- Network throughput.
- Heap của ứng dụng và Elasticsearch.
- Latency mục tiêu cho một bulk request.
- Tỷ lệ retry và failure.

Một số hướng dẫn thực tế thường bắt đầu với batch payload ở mức vài MB rồi tăng dần bằng benchmark. Không có một kích thước tối ưu cố định cho mọi cluster. Nên đo số byte NDJSON thực tế thay vì ước lượng chỉ từ số document.

### Ví dụ gom batch theo số item

```java
Flux.fromIterable(products)
    .buffer(500)
    .concatMap(this::sendBulkBatch);
```

Đoạn này giới hạn mỗi batch ở 500 phần tử và gửi tuần tự. Nếu source có kích thước biến động lớn, cần bổ sung logic flush theo byte hoặc dùng một bulk processor hỗ trợ threshold theo kích thước request.

### Batch theo cả số lượng và thời gian

Với stream event liên tục, có thể flush khi đủ số item hoặc hết thời gian chờ:

```java
Flux<List<ProductDocument>> batches = source
    .bufferTimeout(500, Duration.ofSeconds(2));
```

Điều này tránh giữ batch quá lâu khi lưu lượng thấp. Nếu payload có thể rất lớn, thêm giới hạn byte hoặc chia nhỏ batch trước khi gửi.

## 10. Điều chỉnh số bulk request đồng thời

Bulk size và bulk concurrency là hai tham số khác nhau:

- Batch size quyết định số/khối lượng action trong một request.
- Concurrency quyết định có bao nhiêu bulk request đang được xử lý đồng thời.

Ví dụ:

```java
return Flux.fromIterable(batches)
    .flatMap(this::sendBulkBatch, 2);
```

Tối đa hai bulk batch được xử lý đồng thời trong pipeline này. Tăng concurrency có thể cải thiện throughput khi cluster còn dư tài nguyên, nhưng cũng có thể làm tăng indexing pressure, queue, heap và số request bị từ chối.

### Tính tổng tải theo số instance

Nếu mỗi instance cho phép 4 bulk request đồng thời và có 6 instance chạy cùng lúc, luồng đó có thể tạo khoảng 24 bulk request in-flight. Cần tính cả scheduler, consumer khác, retries và các service khác cùng dùng cluster.

Không chọn concurrency chỉ theo số CPU của ứng dụng. Cần đo khả năng ingest của Elasticsearch, connection pool, shard distribution và độ trễ.

## 11. Theo dõi và xử lý HTTP 429

Khi Elasticsearch quá tải hoặc không thể nhận thêm indexing work, request/item có thể bị từ chối với lỗi `429 Too Many Requests` hoặc lỗi rejection tương ứng.

Ứng dụng nên:

- Giảm bulk concurrency khi tỷ lệ 429 tăng.
- Retry các item có lỗi tạm thời với exponential backoff và jitter.
- Giới hạn số lần retry.
- Tránh retry ngay lập tức với tốc độ cũ.
- Theo dõi indexing pressure, thread pool rejection, CPU, heap và merge.
- Tạm dừng hoặc giảm tốc consumer nếu nguồn dữ liệu hỗ trợ backpressure.

Retry storm có thể làm tình hình xấu hơn. Khi cluster đang quá tải, gửi lại ngay một batch lớn thường chỉ tăng thêm tải.

### Backoff minh họa

```text
Lần retry 1: chờ 200 ms + jitter
Lần retry 2: chờ 400 ms + jitter
Lần retry 3: chờ 800 ms + jitter
Sau giới hạn: đưa vào retry queue/DLQ hoặc đánh dấu job lỗi
```

Giá trị thực tế phải được benchmark và có thể cần cap thời gian tối đa. Chỉ retry lỗi được xác định là tạm thời; lỗi mapping hoặc validation cần sửa dữ liệu/config trước.

## 12. Phân loại lỗi trước khi retry

Không phải lỗi nào cũng có thể khắc phục bằng cách gửi lại cùng item.

| Lỗi | Ví dụ | Hành động |
|---|---|---|
| Mapping/parse error | `mapper_parsing_exception` | Không retry nguyên payload; sửa source hoặc mapping |
| Validation error | Field sai kiểu hoặc document không hợp lệ | Đưa vào error handling/DLQ, sửa dữ liệu |
| Version conflict | `version_conflict_engine_exception` | Đọc lại trạng thái/token và tính lại nghiệp vụ |
| 429/rejection | Cluster quá tải | Backoff, giảm concurrency, retry có giới hạn |
| Timeout/network error | Không rõ server đã xử lý hay chưa | Retry idempotent theo ID ổn định và theo dõi trạng thái |
| Authorization error | 401/403 | Sửa credential/quyền; không retry liên tục |
| Index missing | Index/alias chưa tồn tại | Sửa lifecycle/configuration hoặc tạo index theo quy trình |

Đặc biệt, timeout không chứng minh thao tác chưa được thực hiện. Server có thể đã ghi document nhưng response bị mất. Retry cần an toàn với trường hợp request trước thực tế đã thành công.

## 13. Idempotency khi gửi lại bulk item

Idempotency nghĩa là gửi lại cùng một thao tác không làm sai trạng thái cuối cùng.

### Index với ID ổn định

```json
{ "index": { "_index": "products", "_id": "p-100" } }
{ "name": "Wireless Mouse", "price": 29.99 }
```

Gửi lại cùng action/source với cùng ID sẽ ghi cùng document thay vì tạo document mới có ID ngẫu nhiên. Tuy nhiên, nếu source trong retry cũ hơn source hiện tại, nó vẫn có thể ghi đè dữ liệu mới. ID ổn định không tự giải quyết ordering.

### Create không idempotent theo cùng semantics

`create` chỉ thành công khi ID chưa tồn tại. Retry sau khi lần đầu đã thành công có thể trả conflict. Ứng dụng cần coi conflict đó là kết quả cần đối chiếu, không tự động kết luận dữ liệu sai.

### Update script có thể không idempotent

Ví dụ script tăng counter:

```json
{ "update": { "_id": "p-100" } }
{ "script": { "source": "ctx._source.views += params.n", "params": { "n": 1 } } }
```

Nếu retry sau khi update đã thành công nhưng response bị mất, counter có thể tăng hai lần. Với update dạng cộng/trừ, cần idempotency key, event ID đã xử lý, version condition hoặc thiết kế thao tác sao cho retry không nhân đôi tác động.

## 14. Version conflict và optimistic concurrency trong bulk

Bulk action hỗ trợ metadata condition như `if_seq_no` và `if_primary_term` cho các thao tác phù hợp. Ví dụ:

```http
POST /_bulk
Content-Type: application/x-ndjson

{ "update": { "_index": "products", "_id": "p-100", "if_seq_no": 42, "if_primary_term": 3 } }
{ "doc": { "price": 27.99 } }
```

Nếu document đã thay đổi từ lần đọc metadata, item có thể trả 409. Khi đó, không retry cùng token cũ. Ứng dụng cần đọc lại document, lấy token mới, kiểm tra nghiệp vụ và tính lại thay đổi.

Trong một batch, mỗi document có token riêng. Không dùng chung một cặp sequence number/primary term cho mọi item.

### Bulk conflict không làm hỏng item khác

Một item 409 không rollback các item khác. Response phải được phân loại theo từng action và retry chỉ những item có thể giải quyết an toàn.

## 15. Thứ tự action và phụ thuộc giữa các document

Bulk request có thể chứa action tới nhiều shard. Nó không cung cấp transaction toàn cục hoặc bảo đảm tính nhất quán giữa nhiều document.

Nếu hai thao tác phụ thuộc nhau, ví dụ cập nhật product rồi cập nhật aggregate document, không nên coi việc đặt chúng cạnh nhau trong một bulk là cơ chế transaction. Nếu một action thất bại, action còn lại có thể đã thành công.

Với nhiều action cho cùng một document, hãy xác định semantics và thứ tự cần thiết. Nếu correctness phụ thuộc thứ tự, cân nhắc serialize theo document ID, dùng version/conditional update hoặc tách thành các bước có kiểm soát. Không để nhiều worker gửi các bulk batch cạnh tranh trên cùng ID mà không có quy tắc ordering.

## 16. Bulk và refresh policy

Bulk API hỗ trợ tham số `refresh` tương tự các API ghi khác:

| Giá trị | Ý nghĩa |
|---|---|
| `false` | Không yêu cầu refresh riêng do request; chờ periodic refresh |
| `true` | Yêu cầu refresh ngay các shard bị ảnh hưởng sau request |
| `wait_for` | Chờ lần refresh tiếp theo làm thay đổi searchable |

Ví dụ:

```http
POST /products/_bulk?refresh=wait_for
Content-Type: application/x-ndjson

{ "index": { "_id": "p-100" } }
{ "name": "Mouse" }
{ "index": { "_id": "p-101" } }
{ "name": "Keyboard" }
```

Nếu ingestion có throughput cao và không cần search thấy từng batch ngay, thường để `refresh=false` hoặc không truyền tham số. Với một workflow cần search thấy toàn bộ batch sau khi ghi, có thể dùng `wait_for` hoặc refresh một lần ở ranh giới batch.

Không dùng `refresh=true` cho mọi bulk batch nhỏ trong một luồng tốc độ cao nếu không có yêu cầu read-after-write rõ ràng; refresh liên tục có thể làm tăng segment và merge overhead.

## 17. Tối ưu bulk load lớn bằng refresh interval

Với đợt nạp dữ liệu lớn vào index mới, có thể tạm tăng `index.refresh_interval` hoặc đặt `-1` để tắt periodic refresh trong lúc bulk load, nếu workload cho phép.

Quy trình tổng quát:

1. Đọc và lưu refresh interval hiện tại.
2. Tạm tắt hoặc tăng interval.
3. Gửi bulk batches với concurrency có giới hạn.
4. Kiểm tra tất cả item response và xử lý lỗi.
5. Khôi phục refresh interval cũ.
6. Gọi Refresh API một lần nếu cần dữ liệu searchable ngay.
7. Xác nhận search visibility.

Ví dụ tắt periodic refresh:

```http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "-1"
  }
}
```

Sau khi nhập xong, khôi phục giá trị cũ và refresh:

```http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "1s"
  }
}
```

```http
POST /products/_refresh
```

Trong production, phải khôi phục đúng giá trị đã đọc ở bước đầu, không giả định luôn là `1s`. Job cần cleanup/finally để khôi phục setting kể cả khi một batch lỗi hoặc worker bị dừng.

Không dùng `refresh=wait_for` trong lúc periodic refresh đã tắt nếu không có một bước refresh khác; request có thể chờ cho tới khi có refresh.

## 18. Routing trong Bulk API

Nếu index dùng custom routing, mỗi action phải gửi routing phù hợp để document được ghi vào đúng shard:

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "index": { "_id": "p-100", "routing": "tenant-42" } }
{ "tenantId": "tenant-42", "name": "Mouse" }
```

Khi update/delete hoặc retry action, dùng cùng routing cần thiết. Nếu routing sai hoặc thiếu, thao tác có thể không tìm thấy document hoặc ghi tới shard khác theo default routing.

Với multi-tenant index, routing có thể giúp phân phối dữ liệu theo tenant, nhưng một tenant quá lớn có thể tạo hot shard. Hãy thiết kế routing theo kích thước tenant và workload; không dùng một routing key duy nhất cho mọi document nếu điều đó gây mất cân bằng.

## 19. Pipeline và metadata action

Bulk action có thể chỉ định ingest pipeline:

```http
POST /products/_bulk?pipeline=normalize-product
Content-Type: application/x-ndjson

{ "index": { "_id": "p-100" } }
{ "name": "  Wireless Mouse  " }
```

Pipeline có thể chuẩn hóa, enrich hoặc biến đổi source trước khi index. Khi dùng pipeline, cần tính chi phí xử lý của pipeline vào batch size và concurrency. Pipeline phức tạp có thể trở thành bottleneck ngay cả khi network overhead đã giảm.

Một số metadata như routing, version condition, pipeline hoặc retry-on-conflict có thể được chỉ định theo action hoặc request tùy API. Kiểm tra đúng semantics và phiên bản Elasticsearch trước khi dựa vào một tham số cụ thể.

## 20. Bulk và alias

Ứng dụng thường gửi bulk vào alias ghi thay vì index vật lý:

```http
POST /products-write/_bulk
Content-Type: application/x-ndjson

{ "index": { "_id": "p-100" } }
{ "name": "Mouse" }
```

Alias giúp đổi write index trong quá trình rollover hoặc rebuild mà không cần sửa code. Nếu alias trỏ tới nhiều index, phải cấu hình write index rõ ràng hoặc bảo đảm action được định tuyến theo ý định.

Khi rebuild index mới, cần quản lý đồng bộ event/backfill và alias switch riêng. Bulk API chỉ thực hiện các action được gửi; nó không bảo đảm alias switch, backfill và event replay thành một transaction.

## 21. Spring Data Elasticsearch: khi nào dùng bulk operations?

Spring Data Elasticsearch cung cấp `ElasticsearchOperations` để thao tác index/update/delete ở mức template. Khi cần gửi nhiều action, có thể dùng các phương thức bulk thay vì gọi `save` nhiều lần.

Các trường hợp phù hợp:

- Import dữ liệu từ CSV/JSON hoặc database.
- Consumer nhận event theo batch.
- Đồng bộ search projection.
- Reindex dữ liệu qua application mapper.
- Xóa hoặc cập nhật nhiều document theo một tập ID đã biết.

Với một document đơn lẻ trong request tương tác, `save()`/repository method thường dễ đọc và đủ dùng. Với hàng trăm hoặc hàng nghìn document, hãy cân nhắc bulk API và benchmark.

## 22. Dùng `IndexQuery` và `bulkIndex`

Ví dụ tạo danh sách `IndexQuery`:

```java
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;

List<IndexQuery> queries = products.stream()
    .map(product -> new IndexQueryBuilder()
        .withId(product.getId())
        .withObject(product)
        .build())
    .toList();
```

Gửi bulk:

```java
List<IndexedObjectInformation> indexed =
    operations.bulkIndex(
        queries,
        IndexCoordinates.of("products")
    );
```

Các kiểu trả về và overload `bulkIndex` thay đổi theo phiên bản Spring Data Elasticsearch. Một số phiên bản cho phép truyền `BulkOptions` để cấu hình các tùy chọn bulk. Hãy dùng đúng API của dependency dự án.

### Không tạo một list vô hạn

Ví dụ trên dùng `stream().toList()` để minh họa một batch đã có sẵn trong bộ nhớ. Với nguồn lớn, không tải toàn bộ dataset thành `List`. Hãy đọc từng page/chunk từ nguồn, tạo `IndexQuery` cho batch giới hạn rồi gửi bulk và giải phóng batch trước khi lấy batch kế tiếp.

## 23. Dùng `BulkOptions`

Một số phiên bản Spring Data Elasticsearch hỗ trợ `BulkOptions` để truyền cấu hình bổ sung cho bulk operation, ví dụ refresh policy, timeout, pipeline hoặc các tùy chọn được client/version hỗ trợ.

Ví dụ minh họa refresh policy:

```java
import org.springframework.data.elasticsearch.core.RefreshPolicy;
import org.springframework.data.elasticsearch.core.query.BulkOptions;

BulkOptions options = BulkOptions.builder()
    .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
    .build();
```

Sau đó truyền `options` vào overload bulk operation tương ứng của `ElasticsearchOperations`.

Tên builder, method và các option khả dụng phụ thuộc version Spring Data Elasticsearch. Không copy nguyên ví dụ sang dự án mà chưa đối chiếu Javadoc dependency. Nếu một tùy chọn không được abstraction hỗ trợ ở version hiện tại, có thể dùng Elasticsearch Java API Client được cấu hình trong Spring context.

## 24. `saveAll()` có luôn dùng Bulk API không?

`CrudRepository`/Elasticsearch repository cung cấp `saveAll()` để lưu nhiều entity. Đây là API thuận tiện ở tầng repository:

```java
productRepository.saveAll(products);
```

Tuy nhiên, không nên suy ra rằng mọi version, repository implementation hoặc đường cấu hình đều tạo một Bulk API request duy nhất với batch size tối ưu. Cách triển khai nội bộ có thể thay đổi theo version và implementation.

Nếu throughput và kích thước request là yêu cầu quan trọng:

- Xem Javadoc/source của đúng version Spring Data Elasticsearch.
- Đo số request thực tế qua client metrics hoặc instrumentation.
- Dùng `ElasticsearchOperations.bulkIndex(...)` khi cần kiểm soát rõ bulk behavior.
- Chia dữ liệu thành batch có giới hạn trước khi gọi.
- Kiểm tra kết quả từng item và lỗi.

`saveAll()` vẫn phù hợp với use case đơn giản, batch nhỏ và code không cần kiểm soát sâu về bulk options.

## 25. Bulk với reactive operations

Reactive Spring Data Elasticsearch cung cấp các API bulk tương ứng trả về `Mono` hoặc `Flux` tùy operation/version. Cách dùng reactive không làm thay đổi bản chất Bulk API: một bulk request vẫn có nhiều item và response vẫn có thể thành công một phần.

Ví dụ minh họa luồng batch:

```java
Flux.fromIterable(source)
    .buffer(500)
    .concatMap(batch -> reactiveOperations.bulkIndex(
        toIndexQueries(batch),
        IndexCoordinates.of("products")
    ))
    .then();
```

Tên method, kiểu return và overload chính xác phụ thuộc version. Đoạn code minh họa cách tổ chức pipeline: gom batch có giới hạn, gửi bulk, chờ batch hoàn tất rồi xử lý batch kế tiếp.

Nếu muốn gửi nhiều bulk batch song song, dùng `flatMap` với concurrency tường minh:

```java
Flux.fromIterable(source)
    .buffer(500)
    .flatMap(batch -> sendBulk(batch), 2)
    .then();
```

Không dùng `flatMap` không giới hạn trên một nguồn lớn. Mỗi batch đang in-flight có thể giữ payload và response trong heap, đồng thời tạo áp lực lên Elasticsearch.

### Backpressure và batch

`buffer(500)` giới hạn số item trong mỗi batch, còn concurrency của `flatMap` giới hạn số batch được xử lý đồng thời trong pipeline. Nếu nguồn là pagination từ Elasticsearch hoặc database, cần kiểm soát cả số page được lấy trước. Không gọi `collectList()` trên toàn bộ nguồn chỉ để gửi một bulk khổng lồ.

## 26. Bulk với `UpdateQuery`

Khi chỉ cập nhật một số field, tạo `UpdateQuery` cho từng document:

```java
Document partial = Document.create();
partial.put("status", "ACTIVE");

UpdateQuery update = UpdateQuery.builder("p-100")
    .withDocument(partial)
    .build();
```

Sau đó gom nhiều update query và gửi qua bulk update API của `ElasticsearchOperations` tương ứng version.

Bulk update có thể chứa partial document, upsert hoặc script. Hãy chọn rõ:

- `doc`: cập nhật một phần `_source`.
- `doc_as_upsert`: dùng partial doc để tạo document nếu chưa tồn tại khi được bật.
- `upsert`: source dùng khi document chưa tồn tại.
- `script`: thực hiện logic update phía Elasticsearch.

Script update cần idempotency và kiểm soát params. Nếu retry một phép cộng/trừ, có thể áp dụng tác động nhiều lần nếu lần trước đã thành công nhưng response bị mất.

## 27. Bulk delete

Nếu cần xóa nhiều document đã biết ID, có thể tạo delete action cho từng ID rồi gửi trong bulk:

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "delete": { "_id": "p-100" } }
{ "delete": { "_id": "p-101" } }
{ "delete": { "_id": "p-102" } }
```

Bulk delete phù hợp khi ứng dụng đã có danh sách ID. Nếu mục tiêu là xóa theo query, `_delete_by_query` có semantics và cơ chế riêng; không cần tải toàn bộ ID về application chỉ để xóa hàng loạt.

Delete item không tìm thấy có thể trả kết quả `not_found` tùy tình huống/API. Hãy quyết định liệu đây là kết quả idempotent có thể chấp nhận hay lỗi cần báo cáo.

## 28. Bulk response và mapping lỗi về input

Ứng dụng cần giữ mối liên hệ giữa mỗi action và bản ghi nguồn để xử lý item failure. Có thể dùng một wrapper:

```java
public record PendingIndex(
    String sourceId,
    long sourceVersion,
    IndexQuery query) {
}
```

Khi tạo batch, giữ danh sách theo cùng thứ tự với các action gửi đi. Khi đọc response, ánh xạ item về `sourceId`, source version và event ID tương ứng.

Nếu chỉ giữ `List<IndexQuery>` mà không giữ metadata nguồn, việc tìm bản ghi cần retry hoặc đưa vào dead-letter queue sẽ khó hơn.

### Báo cáo batch result

Một cấu trúc kết quả ứng dụng có thể chứa:

```java
public record BulkBatchResult(
    int submitted,
    int succeeded,
    int retryableFailures,
    int permanentFailures,
    List<BulkItemFailure> failures) {
}
```

Kết quả này là model ứng dụng, không phải response type cố định của Spring Data. Nó giúp job runner quyết định tiếp tục, retry, cảnh báo hoặc đánh dấu batch partial.

## 29. Retry chọn lọc và dead-letter queue

Một pipeline bulk bền vững thường tách item thành ba nhóm:

```text
Bulk response
     |
     +--> Success --------------------> mark completed
     |
     +--> Retryable failure ----------> retry queue with backoff
     |
     +--> Permanent failure ----------> DLQ / error report
```

Retry queue nên giữ đủ metadata để tái tạo action: document ID, index/alias, routing, source payload hoặc event reference, source version, số lần thử và lỗi gần nhất.

Dead-letter queue (DLQ) lưu item không thể xử lý tự động, ví dụ mapping error hoặc dữ liệu sai định dạng. DLQ cần có quy trình sửa và replay; không nên chỉ ghi log rồi bỏ qua nếu dữ liệu bắt buộc phải được đồng bộ.

### Không retry toàn bộ batch nếu chỉ một item lỗi

Nếu 999/1.000 item thành công và một item lỗi mapping, gửi lại cả batch có thể lặp các thao tác không cần thiết và tăng tải. Tạo batch retry chỉ gồm item retryable. Với thao tác idempotent, retry toàn batch có thể an toàn về trạng thái nhưng vẫn lãng phí tài nguyên và che khuất lỗi.

## 30. Bulk và ingest pipeline

Ingest pipeline có thể xử lý dữ liệu trước khi index, ví dụ normalize field, enrich, parse timestamp hoặc loại bỏ field. Có thể chỉ định pipeline cho bulk request hoặc action theo API hỗ trợ.

Lưu ý:

- Pipeline chạy trên ingest node hoặc node xử lý ingest theo cấu hình cluster.
- Pipeline nặng có thể trở thành bottleneck.
- Processor có thể lỗi cho một item; kiểm tra item response.
- Thay đổi pipeline có thể làm cùng source tạo ra projection khác nhau theo thời gian.
- Nếu cần replay deterministic, version hóa pipeline và giữ logic biến đổi rõ ràng.

Đo thời gian ingest pipeline cùng indexing throughput. Bulk batch lớn không bù được pipeline CPU-bound hoặc enrichment call chậm.

## 31. Bulk và mapping

Mapping error là nguyên nhân thường gặp khiến một phần bulk item thất bại. Ví dụ field `price` được mapping là `double` nhưng source gửi chuỗi không thể parse:

```json
{ "index": { "_id": "p-100" } }
{ "name": "Mouse", "price": "not-a-number" }
```

Bulk response có thể trả item lỗi `mapper_parsing_exception`. Các item khác vẫn có thể thành công.

Trước khi ingest lớn:

- Tạo index và mapping rõ ràng trước khi gửi dữ liệu.
- Chuẩn hóa kiểu dữ liệu ở application mapper.
- Kiểm tra field date, numeric, keyword và nested.
- Tránh dynamic mapping tạo field ngoài dự kiến.
- Test một batch đại diện trước khi chạy import lớn.

Không retry mapping error mà không thay đổi payload hoặc mapping; kết quả sẽ tiếp tục thất bại.

## 32. Bulk và alias/data stream

Bulk request có thể ghi qua index, alias hoặc data stream theo điều kiện của Elasticsearch. Khi ghi qua alias, cần xác định write index. Với data stream, action thường phải tuân thủ semantics append-only của data stream; thao tác update/delete theo ID có các giới hạn và yêu cầu phù hợp.

Trong một job import:

- Xác định đích là index vật lý, write alias hay data stream.
- Không trộn nhiều đích nếu chưa có quyền và routing rõ ràng.
- Kiểm tra rollover có thể xảy ra trong lúc job chạy.
- Dùng ID và action phù hợp với semantics đích.
- Theo dõi kết quả item để biết action thực tế ghi vào index nào.

## 33. Theo dõi hiệu năng bulk

Để chọn batch size và concurrency, cần theo dõi cả ứng dụng và Elasticsearch.

### Metrics ở ứng dụng

- Số document/byte trong mỗi batch.
- Bulk request latency p50/p95/p99.
- Documents indexed per second.
- Số bulk request in-flight.
- Số item success/failure theo loại lỗi.
- Retry count và backoff duration.
- Queue depth và consumer lag.
- Heap usage khi dựng payload/response.
- Timeout và connection pool pending acquire.

### Metrics ở Elasticsearch

- Indexing rate và indexing latency.
- Indexing pressure.
- CPU, heap và GC.
- Thread pool write/bulk rejections theo version.
- Merge time và segment count.
- Disk I/O và network.
- Refresh count/time.
- Shard distribution và hot shard.

Có thể kiểm tra index stats:

```http
GET /products/_stats/indexing,refresh,merge
```

Và node stats phù hợp để quan sát indexing pressure/thread pools theo version đang chạy.

## 34. Benchmark batch size và concurrency

Một cách benchmark có kiểm soát:

1. Chọn tập dữ liệu đại diện và mapping giống production.
2. Cố định số shard, replica, pipeline và refresh interval.
3. Bắt đầu với batch nhỏ, concurrency thấp.
4. Tăng batch size từng bước, ghi throughput và p95 latency.
5. Giữ batch size tốt, tăng concurrency từng bước.
6. Dừng tăng khi throughput không cải thiện hoặc CPU/heap/rejection tăng mạnh.
7. Chạy lại với document lớn và phân bố routing thực tế.
8. Kiểm tra item failure và dữ liệu cuối cùng sau benchmark.

Ví dụ ma trận thử nghiệm:

| Batch size | Concurrent bulk requests | Mục tiêu quan sát |
|---:|---:|---|
| 100 docs | 1 | Baseline |
| 500 docs | 1 | Tác động tăng batch |
| 500 docs | 2 | Tác động tăng concurrency |
| 1.000 docs | 2 | Tác động batch lớn hơn |
| 1.000 docs | 4 | Tác động tổng tải |

Các số trên chỉ là ví dụ benchmark, không phải cấu hình mặc định. Chọn theo byte payload và năng lực cluster.

## 35. Khi nào nên dùng request đơn lẻ?

Bulk không phải lựa chọn tốt nhất cho mọi write:

- Người dùng tạo một document và cần response ngay.
- Một thao tác cần read-after-write rõ ràng.
- Luồng ghi có ít dữ liệu và tần suất thấp.
- Cần xử lý lỗi của một document độc lập và trả kết quả trực tiếp.
- Thao tác có logic phụ thuộc ngay vào response của thao tác trước.

Trong các trường hợp này, Index/Update/Delete API riêng có thể đơn giản và dễ quan sát hơn. Không gom một thao tác đơn lẻ vào batch chỉ vì hệ thống có hỗ trợ Bulk API.

## 36. Lỗi thường gặp khi dùng Bulk API

### Gửi JSON array thay vì NDJSON

Bulk API yêu cầu từng action/source trên các dòng riêng biệt và newline cuối cùng. JSON array không phải định dạng bulk.

### Thiếu newline cuối payload

NDJSON phải kết thúc bằng newline. Payload bị cắt ở cuối có thể làm request parse thất bại.

### Dùng sai content type

Nên gửi `Content-Type: application/x-ndjson`.

### Chỉ kiểm tra HTTP 200

Một số item có thể thất bại trong khi bulk request trả response tổng thể thành công. Kiểm tra `errors` và từng `items`.

### Nghĩ bulk là transaction

Một item lỗi không rollback item khác. Xử lý partial success như một phần bình thường của thiết kế.

### Batch quá lớn

Tăng memory, latency, timeout và retry cost. Đo theo byte và chia batch.

### Concurrency không giới hạn

Nhiều bulk request cùng lúc có thể làm Elasticsearch bị quá tải. Giới hạn concurrency theo tổng tải của tất cả instance.

### Retry toàn batch không chọn lọc

Tăng tải và có thể lặp side effect. Phân loại item rồi retry nhóm retryable.

### Retry script update không idempotent

Counter hoặc phép cộng có thể bị áp dụng hai lần. Dùng idempotency key/version hoặc thiết kế update an toàn.

### Bỏ qua 429

Không có backoff sẽ tạo retry storm. Giảm concurrency và retry có giới hạn.

### Quên routing

Update/delete có thể không tìm thấy document hoặc tới shard sai nếu routing không nhất quán.

### Cho rằng `saveAll()` chắc chắn là bulk tối ưu

Kiểm tra implementation/version hoặc dùng bulk operation tường minh khi cần kiểm soát.

## 37. Quy trình xây dựng bulk ingestion bền vững

Một pipeline nhập dữ liệu có thể đi theo các bước:

1. Xác định nguồn chuẩn, document ID và semantics của index/create/update/delete.
2. Tạo mapping và ingest pipeline trước khi nạp dữ liệu.
3. Đọc dữ liệu nguồn theo page/chunk có giới hạn.
4. Chuyển từng bản ghi thành bulk action và giữ metadata nguồn để đối chiếu.
5. Chia batch theo số item và byte payload.
6. Gửi với số bulk request đồng thời có giới hạn.
7. Kiểm tra `errors` và từng item response.
8. Đánh dấu item thành công; phân loại retryable/permanent failures.
9. Retry chọn lọc với backoff, jitter và idempotency.
10. Đưa lỗi không thể xử lý vào DLQ/error report.
11. Theo dõi throughput, latency, 429, heap và Elasticsearch indexing pressure.
12. Áp dụng refresh policy phù hợp với SLA search visibility.
13. Đối soát số lượng/version để xác nhận dữ liệu đã đồng bộ.
14. Lưu checkpoint để job có thể tiếp tục sau sự cố.

## 38. Kết luận

Bulk API gom nhiều thao tác index/create/update/delete vào một HTTP request NDJSON, giúp giảm round trip và thường tăng throughput khi nhập dữ liệu lớn. So với nhiều request đơn lẻ, Bulk API giảm overhead nhưng tạo request/response lớn hơn và yêu cầu ứng dụng quản lý batch size, concurrency, memory và partial failures.

Bulk không phải transaction: một số item có thể thành công trong khi item khác thất bại. Luôn kiểm tra `errors` và từng item trong `items`, phân loại lỗi rồi retry có chọn lọc. Dùng ID ổn định, version condition và idempotency để tránh duplicate hoặc ghi đè dữ liệu mới; áp dụng backoff khi gặp 429; giới hạn batch theo byte và số lượng; chọn refresh/routing/pipeline phù hợp. Trong Spring Data Elasticsearch, dùng `ElasticsearchOperations` bulk methods hoặc reactive bulk operations khi cần kiểm soát rõ hành vi, đồng thời kiểm tra API theo version. `saveAll()` tiện lợi nhưng không nên được mặc định là một bulk request tối ưu nếu chưa xác nhận implementation.

## Tài liệu tham khảo

- [Elasticsearch – Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
- [Elasticsearch – Tune for indexing speed](https://www.elastic.co/docs/deploy-manage/production-guidance/optimize-performance/indexing-speed)
- [Elasticsearch – Index API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-index)
- [Elasticsearch – Update API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update)
- [Elasticsearch – Delete API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete)
- [Elasticsearch – Refresh API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-refresh)
- [Elasticsearch – Optimistic concurrency control](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/optimistic-concurrency-control)
- [Spring Data Elasticsearch – ElasticsearchOperations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – Bulk operations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ElasticsearchOperations.html)
