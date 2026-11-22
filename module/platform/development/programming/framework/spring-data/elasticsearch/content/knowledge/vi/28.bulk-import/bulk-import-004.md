# Phân biệt HTTP thành công và lỗi từng phần tử trong bulk

Bulk API của Elasticsearch nhận nhiều thao tác ghi trong một request để giảm số lần trao đổi giữa ứng dụng và cluster. Một request bulk có thể chứa hàng trăm thao tác index, create, update hoặc delete. Các thao tác này được xử lý độc lập: một số phần tử có thể thành công trong khi những phần tử khác thất bại.

Vì vậy, HTTP status của request không đủ để kết luận toàn bộ batch đã ghi thành công. Elasticsearch có thể trả HTTP 200 cho một bulk request đã được xử lý, đồng thời response body báo `errors: true` vì một hoặc nhiều operation thất bại.

Khi nhập dữ liệu bằng Spring Data Elasticsearch, ứng dụng cần phân biệt:

1. **Request-level outcome:** HTTP request có được server chấp nhận và trả response hay không.
2. **Bulk-level outcome:** response có cờ `errors` cho biết có operation nào thất bại hay không.
3. **Item-level outcome:** từng operation có status, result hoặc error riêng.

Chỉ kiểm tra đủ ba lớp này mới giúp ứng dụng biết chính xác phần dữ liệu nào đã được ghi, phần nào cần sửa và phần nào có thể retry.

## 1. Bulk API xử lý nhiều operation trong một request

Một bulk request có thể chứa nhiều loại thao tác:

| Operation | Mục đích | Nội dung gửi kèm |
| --- | --- | --- |
| `index` | Tạo mới hoặc thay thế document theo ID | Metadata và source document |
| `create` | Chỉ tạo document nếu ID chưa tồn tại | Metadata và source document |
| `update` | Cập nhật một phần document hoặc chạy script | Metadata và update body |
| `delete` | Xóa document theo ID | Chỉ metadata |

Ví dụ request:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{ "index": { "_index": "products", "_id": "P-100" } }
{ "name": "Keyboard", "price": 129.5 }
{ "index": { "_index": "products", "_id": "P-101" } }
{ "name": "Mouse", "price": 49.9 }
{ "delete": { "_index": "products", "_id": "P-102" } }
~~~

Mỗi action metadata nằm trên một dòng riêng. Với `index`, `create` và `update`, dòng tiếp theo chứa source hoặc update body. `delete` chỉ cần một dòng metadata.

Bulk API không phải transaction. Nếu operation đầu tiên và thứ ba thành công nhưng operation thứ hai thất bại, hai operation thành công vẫn có thể được lưu. Elasticsearch không tự rollback các operation đã hoàn tất chỉ vì một operation khác gặp lỗi.

## 2. Ba lớp kết quả không được nhầm lẫn

Một response bulk có thể có HTTP status 200 và body như sau:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "took": 12,
  "errors": true,
  "items": [
    {
      "index": {
        "_index": "products",
        "_id": "P-100",
        "status": 201,
        "result": "created"
      }
    },
    {
      "index": {
        "_index": "products",
        "_id": "P-101",
        "status": 400,
        "error": {
          "type": "mapper_parsing_exception",
          "reason": "failed to parse field [price]"
        }
      }
    },
    {
      "delete": {
        "_index": "products",
        "_id": "P-102",
        "status": 200,
        "result": "deleted"
      }
    }
  ]
}
~~~

Diễn giải:

- HTTP 200: Elasticsearch đã xử lý request bulk và trả về một response hợp lệ.
- `errors: true`: ít nhất một operation trong batch thất bại.
- Item `P-100`: tạo document thành công.
- Item `P-101`: thất bại do không parse được field `price`.
- Item `P-102`: xóa document thành công.

Không được kết luận batch thành công chỉ từ HTTP 200. Cũng không được kết luận tất cả operation thất bại chỉ vì `errors` là true. Cần đọc từng item để xác định kết quả.

### 2.1. Ý nghĩa của từng lớp

| Lớp | Ví dụ | Có thể kết luận điều gì? |
| --- | --- | --- |
| HTTP request | `200 OK` | Server trả response thành công ở cấp HTTP |
| Bulk response | `errors: true` | Có ít nhất một operation có lỗi |
| Item response | `status: 400`, có `error` | Operation cụ thể thất bại |
| Item response | `status: 201`, `result: created` | Operation cụ thể đã tạo document |

HTTP status là kết quả của request gửi đến endpoint. `errors` là tổng hợp kết quả các operation. `items` là dữ liệu chi tiết để ứng dụng xử lý.

### 2.2. HTTP 200 không có nghĩa là tất cả item thành công

Bulk API được thiết kế để trả kết quả từng operation. Một operation có lỗi mapping không làm Elasticsearch phải hủy các operation khác trong cùng request.

~~~text
Bulk request
   |
   +-- index P-100  ---> 201 created
   |
   +-- index P-101  ---> 400 mapper_parsing_exception
   |
   +-- update P-102 ---> 200 updated
   |
   +-- delete P-103 ---> 200 deleted

HTTP response: 200 OK
Bulk errors:   true
Successful:    3 operations
Failed:        1 operation
~~~

Ứng dụng phải ghi nhận ba operation thành công và đưa riêng operation thất bại vào luồng xử lý lỗi.

## 3. Phân biệt request-level error và item-level error

### 3.1. Request-level error

Request-level error xảy ra ở cấp HTTP hoặc transport. Elasticsearch không trả về một response bulk bình thường mà ứng dụng có thể duyệt đầy đủ danh sách item.

| Tình huống | Ví dụ kết quả |
| --- | --- |
| Sai cú pháp NDJSON hoặc request body không hợp lệ | HTTP 400 |
| Không xác thực được | HTTP 401 |
| Không có quyền truy cập index hoặc thao tác | HTTP 403 |
| Index không tồn tại và không được phép tự tạo | Có thể là HTTP 404 |
| Request vượt giới hạn kích thước | HTTP 413 |
| Cluster hoặc node tạm thời không thể xử lý | Có thể là HTTP 429 hoặc 5xx |
| Timeout hoặc mất kết nối | Client có thể nhận lỗi transport thay vì BulkResponse |

Đây là lỗi cần xử lý ở cấp request. Ví dụ HTTP 401 cần sửa thông tin xác thực; HTTP 413 cần giảm kích thước batch; HTTP 400 do NDJSON sai cần sửa cách tạo request.

### 3.2. Item-level error

Item-level error xảy ra khi bulk request đã được xử lý và Elasticsearch có thể trả status riêng cho một operation.

Ví dụ:

- `mapper_parsing_exception`: giá trị source không phù hợp mapping.
- `document_parsing_exception`: nội dung document không thể được parse.
- `version_conflict_engine_exception`: operation xung đột version.
- `document_missing_exception`: update yêu cầu document đang tồn tại nhưng ID không tìm thấy.
- `es_rejected_execution_exception`: node từ chối operation do quá tải hoặc queue đầy.

Một item lỗi thường có cấu trúc:

~~~json
{
  "index": {
    "_index": "products",
    "_id": "P-101",
    "status": 400,
    "error": {
      "type": "mapper_parsing_exception",
      "reason": "failed to parse field [price] of type [double]"
    }
  }
}
~~~

Các item khác trong cùng response vẫn có thể thành công.

### 3.3. Timeout khác với item failure đã được xác nhận

Nếu client gửi request rồi timeout trước khi nhận response, ứng dụng có thể không biết Elasticsearch đã xử lý được bao nhiêu operation. Một số operation có thể đã thành công trước khi kết nối bị ngắt.

Không nên xem mọi timeout là bằng chứng rằng không có dữ liệu nào được ghi. Đây là trạng thái **kết quả chưa xác định**. Cần thiết kế ID ổn định, thao tác idempotent và cơ chế đối soát để xử lý an toàn.

## 4. Cấu trúc bulk response

Response bulk thường có các trường:

| Trường | Ý nghĩa |
| --- | --- |
| `took` | Thời gian Elasticsearch xử lý bulk request, tính bằng millisecond |
| `errors` | `true` nếu có ít nhất một operation thất bại |
| `items` | Danh sách kết quả từng operation, theo thứ tự request |
| `ingest_took` | Thời gian ingest pipeline nếu response có trường này |

Mỗi phần tử trong `items` có một key là operation type (`index`, `create`, `update` hoặc `delete`) và value là kết quả của operation đó.

Một item thành công có thể trông như sau:

~~~json
{
  "index": {
    "_index": "products",
    "_id": "P-100",
    "_version": 3,
    "result": "updated",
    "_shards": {
      "total": 2,
      "successful": 2,
      "failed": 0
    },
    "status": 200
  }
}
~~~

Một item thất bại có thể trông như sau:

~~~json
{
  "update": {
    "_index": "products",
    "_id": "P-101",
    "status": 409,
    "error": {
      "type": "version_conflict_engine_exception",
      "reason": "[P-101]: version conflict"
    }
  }
}
~~~

### 4.1. Kiểm tra status, result và error

Khi phân tích một item, nên xem:

- `status`: mã status HTTP tương ứng với operation.
- `result`: kết quả ở cấp Elasticsearch như `created`, `updated`, `deleted`, `noop` hoặc `not_found`.
- `error`: thông tin lỗi nếu operation thất bại.
- `_index`, `_id`: xác định document được thao tác.
- `_version`, `_seq_no`, `_primary_term`: metadata phục vụ concurrency nếu response có.

Không chỉ dựa vào `status` hoặc `result` riêng lẻ. Ví dụ `noop` trong update thường có nghĩa script không làm thay đổi document; đây có thể là một kết quả hợp lệ chứ không phải lỗi.

Với delete document không tồn tại, response có thể có `result: not_found` và status tương ứng. Ứng dụng cần quyết định đây có phải lỗi theo hợp đồng nghiệp vụ hay không. Nếu mục tiêu là xóa idempotent, document đã không tồn tại có thể được coi là trạng thái mong muốn.

### 4.2. errors là cờ tổng hợp, không phải danh sách lỗi

`errors: true` chỉ cho biết có ít nhất một operation thất bại. Nó không cho biết item nào thất bại, có bao nhiêu item thất bại hoặc lỗi nào có thể retry. Các thông tin đó nằm trong `items`.

## 5. Bulk không có tính atomic

Bulk API gom nhiều thao tác vào một request, nhưng không biến chúng thành một transaction nguyên tử.

Ví dụ một batch có 1.000 operation:

- 980 operation thành công.
- 15 operation lỗi mapping.
- 5 operation bị từ chối do quá tải.

Elasticsearch không rollback 980 operation thành công. Ứng dụng cần giữ kết quả của chúng và xử lý 20 operation còn lại.

Điều này có ba hệ quả:

1. Không retry toàn bộ batch chỉ vì `errors: true`.
2. Không xóa hoặc rollback các document thành công nếu nghiệp vụ không yêu cầu một compensating action riêng.
3. Cần lưu được quan hệ giữa từng operation gửi đi và item response tương ứng.

Nếu nghiệp vụ đòi hỏi tất cả thay đổi phải commit hoặc rollback cùng nhau, bulk không phải cơ chế transaction phù hợp. Hãy xử lý transaction ở hệ thống nguồn rồi xây dựng read model Elasticsearch theo event hoặc projection.

## 6. NDJSON: định dạng request ảnh hưởng kết quả

Bulk API sử dụng NDJSON (newline-delimited JSON), không phải một JSON array thông thường.

Đúng:

~~~text
{ "index": { "_index": "products", "_id": "P-100" } }
{ "name": "Keyboard", "price": 129.5 }
{ "delete": { "_index": "products", "_id": "P-101" } }
~~~

Sai:

~~~json
[
  {
    "index": {
      "_index": "products",
      "_id": "P-100"
    }
  },
  {
    "name": "Keyboard"
  }
]
~~~

Các quy tắc quan trọng:

- Mỗi action metadata là một dòng JSON.
- Source/update body nằm trên dòng tiếp theo khi operation cần body.
- Không thêm dấu phẩy giữa các dòng.
- Không pretty-print một JSON object thành nhiều dòng.
- Kết thúc request bằng newline cuối cùng.
- Dùng content type `application/x-ndjson`.

Một request sai định dạng có thể thất bại ở cấp request trước khi có response item như mong đợi.

### 6.1. Số dòng theo operation

| Operation | Số dòng |
| --- | ---: |
| `index` | 2 |
| `create` | 2 |
| `update` | 2 |
| `delete` | 1 |

Ví dụ update:

~~~text
{ "update": { "_index": "products", "_id": "P-100" } }
{ "doc": { "price": 119.5 } }
~~~

Ví dụ update với upsert:

~~~text
{ "update": { "_index": "products", "_id": "P-200" } }
{ "doc": { "name": "New Product" }, "doc_as_upsert": true }
~~~

Nếu gửi thiếu dòng source cho operation cần body, hoặc đặt nhầm body vào dòng action tiếp theo, parser có thể không hiểu request.

## 7. Đọc từng item theo đúng thứ tự request

Bulk response trả `items` theo thứ tự các operation đã gửi. Ứng dụng có thể đối chiếu theo vị trí trong danh sách request.

Không nên chỉ dùng document ID làm khóa đối chiếu nếu cùng một bulk request có nhiều operation trên cùng ID. Ví dụ một request có thể index document rồi update chính document đó. Cần lưu cả vị trí, operation type, index và ID.

~~~java
public record SubmittedOperation(
    int position,
    String operation,
    String index,
    String id
) {}
~~~

Khi gửi bulk, giữ danh sách SubmittedOperation cùng thứ tự với request. Khi nhận response, ghép `items.get(i)` với operation ở vị trí `i`.

## 8. Đọc BulkResponse bằng Elasticsearch Java API Client

Khi cần kiểm tra chính xác `errors`, status và error của từng item, Elasticsearch Java API Client cung cấp `BulkResponse`.

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.BulkRequest;
import co.elastic.clients.elasticsearch.core.BulkResponse;
import co.elastic.clients.elasticsearch.core.bulk.BulkResponseItem;

BulkRequest.Builder request = new BulkRequest.Builder();

request.operations(op -> op
    .index(index -> index
        .index("products")
        .id("P-100")
        .document(product100)
    )
);

request.operations(op -> op
    .index(index -> index
        .index("products")
        .id("P-101")
        .document(product101)
    )
);

BulkResponse response = elasticsearchClient.bulk(request.build());
~~~

Đọc kết quả:

~~~java
if (response.errors()) {
    System.out.println("At least one bulk item failed");
}

for (BulkResponseItem item : response.items()) {
    if (item.error() == null) {
        System.out.printf(
            "SUCCESS index=%s id=%s status=%d result=%s%n",
            item.index(),
            item.id(),
            item.status(),
            item.result()
        );
    } else {
        System.out.printf(
            "FAILED index=%s id=%s status=%d type=%s reason=%s%n",
            item.index(),
            item.id(),
            item.status(),
            item.error().type(),
            item.error().reason()
        );
    }
}
~~~

Điểm quan trọng:

- `response.errors()` là cờ tổng hợp.
- `response.items()` chứa từng operation result.
- `item.status()` là status của item.
- `item.error()` có thông tin lỗi khi item thất bại.
- `item.id()` và `item.index()` giúp xác định document.
- `item.result()` cho biết kết quả như created, updated hoặc deleted nếu có.

Nếu request gặp HTTP 4xx/5xx hoặc lỗi transport, client có thể ném exception thay vì trả một `BulkResponse` bình thường. Cần xử lý exception riêng với việc phân loại item trong response.

### 8.1. Kiểm tra item count

Nếu request có N operation, response bình thường phải có N item result. Nếu số lượng không khớp, không được tự suy luận operation nào đã thành công. Hãy xem đây là tình huống bất thường cần log request metadata, response và kiểm tra phiên bản client/endpoint.

## 9. Dùng BulkOperations trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp abstraction `BulkOperations` để gom các thao tác ghi:

~~~java
import org.springframework.data.elasticsearch.core.BulkOperations;
import org.springframework.data.elasticsearch.core.BulkMode;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

BulkOperations bulk = operations.bulkOps(
    BulkMode.BULK,
    ProductDocument.class
);

bulk.insert(products);
bulk.execute();
~~~

Bulk abstraction phù hợp khi ứng dụng muốn làm việc qua mapping và các API Spring Data. Tuy nhiên, mức chi tiết mà abstraction trả về cho lỗi từng operation phụ thuộc API và phiên bản Spring Data Elasticsearch.

Nếu luồng nghiệp vụ cần quyết định retry theo từng `BulkResponseItem`, cần sử dụng API bulk có expose chi tiết item response, chẳng hạn Elasticsearch Java API Client, hoặc dùng API Spring Data cụ thể có trả failed document details trong phiên bản dự án.

Không nên giả định một lời gọi `execute()` không ném exception đồng nghĩa mọi document đã được ghi đúng. Cũng không nên giả định mọi phiên bản `BulkOperations` trả trực tiếp danh sách item result.

### 9.1. API bulk index của ElasticsearchOperations

Một số API `ElasticsearchOperations` cung cấp phương thức bulk index/update nhận danh sách query và trả về thông tin document được index. Các API này có thể ném `BulkFailureException` hoặc exception tương ứng khi có failed documents, tùy phiên bản.

Khi sử dụng:

- Kiểm tra Javadoc của đúng Spring Data Elasticsearch version.
- Xem exception có chứa map/list các document thất bại hay không.
- Không bỏ qua failed document details.
- Nếu cần status/error nguyên bản của từng operation, cân nhắc đọc response từ Java API Client.

### 9.2. Chọn abstraction phù hợp

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Ghi nhiều entity theo mapping Spring Data | `BulkOperations` hoặc API bulk của `ElasticsearchOperations` |
| Muốn thao tác ở mức entity | Spring Data abstraction |
| Cần `BulkResponse.errors()` và từng item status/error | Elasticsearch Java API Client |
| Cần retry đúng các item lỗi | Lưu request metadata và đọc item response chi tiết |
| Cần kiểm soát đầy đủ operation metadata | Java API Client hoặc Bulk REST API |

## 10. Phân loại lỗi từng item

Không phải lỗi nào cũng nên retry. Hãy phân loại theo nguyên nhân và khả năng tự phục hồi.

| Item status / error | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| 400 `mapper_parsing_exception` | Giá trị source không khớp mapping | Sửa dữ liệu hoặc mapping; không retry nguyên trạng |
| 400 `document_parsing_exception` | Document không hợp lệ | Sửa serializer/source |
| 400 `illegal_argument_exception` | Tham số hoặc cấu hình operation sai | Sửa request |
| 404 `document_missing_exception` | Update document không tồn tại, không có upsert | Kiểm tra ID và chính sách create/upsert |
| 409 `version_conflict_engine_exception` | Xung đột version hoặc optimistic concurrency | Đọc lại, hợp nhất hoặc retry có điều kiện |
| 409 khi `create` | ID đã tồn tại | Xử lý duplicate theo nghiệp vụ |
| 429 `es_rejected_execution_exception` | Node hoặc write queue quá tải | Backoff, giảm concurrency/batch |
| 5xx tạm thời | Lỗi node, shard hoặc dịch vụ | Retry có giới hạn sau khi phân loại |

Error type và status thực tế có thể thay đổi theo operation, cấu hình cluster và phiên bản. Hãy dùng `error.type`, `error.reason`, status và operation type thay vì chỉ dựa vào một mã số.

### 10.1. Lỗi mapping không nên retry nguyên trạng

Ví dụ field `price` được mapping là double nhưng source gửi chuỗi không chuyển đổi được:

~~~json
{
  "price": "unknown"
}
~~~

Retry cùng document sẽ tiếp tục thất bại. Cần sửa dữ liệu thành giá trị hợp lệ, bỏ field nếu nghiệp vụ cho phép hoặc thay đổi mapping sau khi đánh giá tác động.

### 10.2. Lỗi quá tải có thể retry

`429` thường biểu thị Elasticsearch từ chối operation do quá tải. Đây là trường hợp phù hợp với retry có backoff, nhưng retry dồn dập sẽ làm tình trạng quá tải nặng hơn.

Nên:

- Chờ theo exponential backoff.
- Thêm jitter để nhiều worker không retry cùng thời điểm.
- Giới hạn số lần retry.
- Giảm batch size hoặc số request đồng thời.
- Theo dõi rejected count và write queue.

### 10.3. Version conflict cần xử lý theo nghiệp vụ

`409 version_conflict_engine_exception` không phải lúc nào cũng là lỗi tạm thời có thể gửi lại nguyên operation.

Nếu hai writer cùng cập nhật một document, cần xác định writer nào có dữ liệu mới hơn, có thể đọc lại và tính lại update hay cần optimistic concurrency.

`retry_on_conflict` là cơ chế retry xung đột cho update operation; nó không giải quyết lỗi mapping, request timeout hay quá tải 429.

## 11. Retry chỉ các item thất bại

Giả sử bulk request có 100 operation và response cho thấy 96 thành công, 4 thất bại. Không nên gửi lại cả 100 operation nếu mục tiêu chỉ là xử lý bốn item lỗi.

~~~text
Gửi batch 100 operation
          |
          v
Nhận response 100 items
          |
          +----> 96 success: ghi nhận hoàn tất
          |
          +----> 4 failed: phân loại lỗi
                         |
             +-----------+-----------+
             |                       |
             v                       v
        Retryable                 Permanent
             |                       |
             v                       v
     Retry có backoff          DLQ / sửa dữ liệu
~~~

### 11.1. Giữ lại operation gốc

Để retry, ứng dụng cần lưu lại operation type, index, document ID, routing, source hoặc update body, version constraints, số lần retry, batch ID và error type/reason.

Chỉ giữ ID là chưa đủ nếu operation cần source hoặc script để chạy lại.

### 11.2. Exponential backoff và jitter

| Lần retry | Delay cơ sở |
| --- | ---: |
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.600 ms |
| 5 | 3.200 ms |

Thực tế nên thêm random jitter và giới hạn delay tối đa. Giá trị trên chỉ là ví dụ; cần điều chỉnh theo latency, tải cluster và SLA.

### 11.3. Retry có giới hạn

Không retry vô hạn. Sau số lần cho phép, đưa item vào dead-letter queue, ghi nguyên nhân và payload tham chiếu, phát cảnh báo theo ngưỡng và cho phép sửa dữ liệu/replay có kiểm soát.

## 12. Idempotency và timeout không xác định kết quả

Retry an toàn phụ thuộc vào việc operation có idempotent hay không.

### 12.1. Dùng ID ổn định

~~~text
{ "index": { "_index": "products", "_id": "P-100" } }
{ "name": "Keyboard", "price": 129.5 }
~~~

Nếu request bị timeout nhưng Elasticsearch đã ghi document, gửi lại cùng operation index với cùng ID và cùng source thường sẽ thay thế document bằng cùng nội dung thay vì tạo thêm document mới.

Ngược lại, nếu mỗi lần retry tạo ID ngẫu nhiên, cùng một dữ liệu có thể được ghi thành nhiều document trùng lặp.

### 12.2. Create và duplicate

`create` chỉ tạo nếu ID chưa tồn tại. Nếu lần đầu đã thành công nhưng client timeout trước khi nhận response, lần retry có thể trả 409 vì ID đã tồn tại.

Không thể kết luận dữ liệu chưa được ghi chỉ từ lỗi 409 của lần retry. Có thể cần đọc document theo ID và đối chiếu nội dung/version.

### 12.3. Update script không idempotent

~~~json
{
  "script": {
    "source": "ctx._source.viewCount += params.amount",
    "params": {
      "amount": 1
    }
  }
}
~~~

Nếu request đã được thực thi nhưng response bị mất, retry script này có thể tăng thêm lần nữa. Đây là operation không idempotent.

Để tránh cập nhật trùng, có thể dùng event ID đã xử lý, lưu sequence/version từ nguồn, thiết kế update gán giá trị tuyệt đối, dùng optimistic concurrency hoặc project lại từ event log theo cách idempotent.

### 12.4. Không retry toàn bộ request sau timeout một cách mù quáng

Timeout có thể xảy ra trước khi server nhận request, trong khi server đang xử lý hoặc sau khi đã hoàn tất nhưng response chưa về tới client.

Nếu không biết trạng thái, hãy:

1. Dùng ID ổn định và operation idempotent.
2. Đối soát các document theo ID nếu cần xác nhận.
3. Chỉ gửi lại operation chưa được xác nhận.
4. Không lặp update script có side effect nếu chưa có cơ chế deduplicate.

## 13. Kiểm soát batch size và concurrency

Bulk request quá nhỏ làm tăng overhead HTTP. Bulk request quá lớn có thể tăng memory, latency, kích thước response và thời gian xử lý.

Không có một batch size tối ưu cho mọi cluster. Nên benchmark theo kích thước source, số operation, payload bytes, mapping, ingest pipeline, số shard/replica, tốc độ ghi và tỷ lệ lỗi 429.

### 13.1. Giới hạn theo số item và byte

Nên chia batch theo cả số operation lẫn tổng kích thước payload. Một batch 1.000 document nhỏ có thể nhẹ hơn 100 document có source rất lớn.

Nếu request vượt giới hạn body size, server/proxy có thể trả HTTP 413. Hãy chia nhỏ batch thay vì retry cùng payload.

### 13.2. Điều chỉnh concurrency

Nếu tăng số worker làm 429 tăng mạnh, giảm số bulk request đồng thời. Nhiều request lớn cùng lúc có thể khiến write thread pool và queue quá tải.

Một cơ chế producer-consumer có backpressure giúp tốc độ đọc dữ liệu nguồn không vượt quá khả năng ghi của Elasticsearch.

### 13.3. Theo dõi latency

`took` trong response là thời gian Elasticsearch xử lý request. Nó không nhất thiết bao gồm toàn bộ thời gian từ lúc ứng dụng tạo batch đến lúc nhận response.

Nên đo riêng thời gian chuẩn bị batch, client latency, `took`, số operation/giây, số item thành công/thất bại và tỷ lệ retry.

## 14. Bulk và refresh không thay đổi semantics lỗi

Bulk API có thể dùng refresh policy hoặc tham số refresh để điều khiển khi thay đổi trở nên tìm kiếm được.

Ví dụ `refresh=wait_for` chờ refresh tiếp theo để các thay đổi đã ghi có thể được search thấy. Nó không biến bulk thành transaction và không có nghĩa mọi item thành công.

Ngay cả khi request dùng `refresh=wait_for`, ứng dụng vẫn phải kiểm tra HTTP request result, `errors` và từng item status/error.

Tương tự, `wait_for_active_shards` liên quan đến mức shard cần active trước khi thực hiện operation; nó không thay thế kiểm tra kết quả từng item.

## 15. Ghi log và quan sát bulk ingestion

Một pipeline bulk cần log đủ thông tin để trả lời batch nào được gửi, có bao nhiêu operation, bao nhiêu thành công/thất bại, item nào lỗi, lỗi thuộc nhóm nào, có bao nhiêu lần retry và bao nhiêu item đã vào dead-letter queue.

Ví dụ log tổng hợp:

~~~text
bulkId=bulk-20260312-00042
index=products
submitted=1000
succeeded=982
failed=18
retryable=12
permanent=6
esTookMs=245
clientLatencyMs=318
~~~

Ví dụ log item:

~~~text
bulkId=bulk-20260312-00042
position=147
operation=index
index=products
id=P-10147
status=400
errorType=mapper_parsing_exception
retryable=false
~~~

Không log toàn bộ source document nếu có dữ liệu nhạy cảm hoặc payload lớn. Ghi ID, batch ID, error type và một phần thông tin đã được lọc là đủ trong nhiều trường hợp.

### 15.1. Metric nên có

| Metric | Ý nghĩa |
| --- | --- |
| `bulk_requests_total` | Số bulk request đã gửi |
| `bulk_request_failures_total` | Request-level failures |
| `bulk_items_submitted_total` | Tổng item đã gửi |
| `bulk_items_succeeded_total` | Tổng item thành công |
| `bulk_items_failed_total` | Tổng item thất bại |
| `bulk_items_retried_total` | Tổng item đã retry |
| `bulk_items_dead_letter_total` | Tổng item không thể xử lý tự động |
| `bulk_duration_seconds` | Thời gian xử lý bulk |
| `bulk_item_failure_rate` | Tỷ lệ item thất bại |

Theo dõi riêng HTTP request error và item failure rate. Nếu chỉ đếm HTTP 2xx, dashboard có thể hiển thị ingestion khỏe mạnh dù hàng nghìn document bị lỗi mapping.

## 16. Ví dụ xử lý lỗi từng item

~~~java
import java.util.ArrayList;
import java.util.List;

import co.elastic.clients.elasticsearch.core.BulkResponse;
import co.elastic.clients.elasticsearch.core.bulk.BulkResponseItem;

public record FailedOperation(
    int position,
    String index,
    String id,
    int status,
    String errorType,
    String reason
) {}

public record BulkOutcome(
    int succeeded,
    List<FailedOperation> failed
) {}

public BulkOutcome inspect(BulkResponse response) {
    List<FailedOperation> failed = new ArrayList<>();
    int succeeded = 0;

    for (int i = 0; i < response.items().size(); i++) {
        BulkResponseItem item = response.items().get(i);

        if (item.error() == null) {
            succeeded++;
            continue;
        }

        failed.add(new FailedOperation(
            i,
            item.index(),
            item.id(),
            item.status(),
            item.error().type(),
            item.error().reason()
        ));
    }

    return new BulkOutcome(succeeded, failed);
}
~~~

Đây là bước phân tích response. Để retry, ứng dụng phải ghép position với danh sách operation gốc đã gửi, lấy lại source/update body và chỉ tạo request mới từ các item được phân loại retryable.

### 16.1. Phân loại retryable

~~~java
boolean isRetryable(FailedOperation failure) {
    if (failure.status() == 429) {
        return true;
    }

    if (failure.status() >= 500 && failure.status() <= 599) {
        return true;
    }

    return false;
}
~~~

Quy tắc trên chỉ là điểm bắt đầu. Hệ thống thực tế cần kiểm tra error type, operation semantics và chính sách riêng cho 409, 404 hoặc lỗi tạm thời cụ thể. Không nên coi mọi 5xx đều chắc chắn an toàn để retry nếu operation không idempotent và kết quả trước đó chưa rõ.

### 16.2. Gửi lại subset lỗi

~~~java
List<PendingOperation> retryOperations = new ArrayList<>();

for (FailedOperation failure : outcome.failed()) {
    if (isRetryable(failure)) {
        PendingOperation original =
            submittedOperations.get(failure.position());
        retryOperations.add(original);
    } else {
        deadLetterQueue.publish(
            submittedOperations.get(failure.position()),
            failure
        );
    }
}

// Chờ backoff rồi tạo bulk request mới chỉ từ retryOperations.
~~~

`PendingOperation` là kiểu dữ liệu ứng dụng giữ operation metadata và source gốc. Không lấy item response để tự dựng lại source vì response không chứa đầy đủ payload ban đầu.

## 17. Các trường hợp cần xử lý riêng

### 17.1. Mapping thay đổi giữa các batch

Nếu một field đổi kiểu mapping trong khi pipeline vẫn đang gửi dữ liệu, một phần document có thể thành công còn phần khác thất bại. Dừng hoặc điều tiết producer, xử lý migration mapping và chỉ retry item sau khi mapping đã tương thích.

### 17.2. Index alias và rollover

Nếu bulk ghi qua alias, cần bảo đảm alias có write index đúng. Nếu alias trỏ sai hoặc không có write index, request có thể thất bại ở cấp request hoặc item tùy lỗi và cấu hình.

Có thể dùng `require_alias` khi muốn Elasticsearch từ chối ghi nếu tên đích không phải alias. Điều này giúp tránh vô tình tạo index mới do gõ nhầm tên.

### 17.3. Ingest pipeline

Ingest pipeline có thể biến đổi hoặc từ chối document. Lỗi từ processor có thể xuất hiện trong item error dù request bulk tổng thể đã được xử lý.

Khi lỗi lặp lại, kiểm tra pipeline ID, processor gây lỗi, trường đầu vào bị thiếu/sai kiểu và pipeline version đang được gắn với request/index.

### 17.4. Update với upsert

Update không có document đích có thể trả lỗi missing. Nếu nghiệp vụ cho phép tạo mới, cấu hình `doc_as_upsert` hoặc `upsert` trong update body:

~~~json
{ "update": { "_index": "products", "_id": "P-200" } }
{ "doc": { "name": "New Product" }, "doc_as_upsert": true }
~~~

Không bật upsert một cách tự động nếu document không tồn tại là dấu hiệu dữ liệu sai hoặc quan hệ tham chiếu bị hỏng.

## 18. Những lỗi thường gặp

**Chỉ kiểm tra HTTP 200.** Bulk response vẫn có thể chứa item failures. Hãy kiểm tra `errors` và duyệt `items`.

**Chỉ kiểm tra `errors: true`.** Cờ này không cho biết item nào thành công hay thất bại. Phải đọc từng item.

**Retry cả batch khi chỉ vài item lỗi.** Các item thành công có thể bị ghi lại hoặc gây side effect. Tạo batch retry từ đúng subset lỗi.

**Coi bulk là transaction.** Elasticsearch không rollback các item thành công khi item khác thất bại.

**Coi timeout là không có dữ liệu nào được ghi.** Server có thể đã thực hiện một phần hoặc toàn bộ request. Dùng ID ổn định và đối soát.

**Retry mapping error.** Dữ liệu sai mapping sẽ tiếp tục thất bại. Sửa source hoặc mapping trước khi retry.

**Retry 429 ngay lập tức.** Retry dồn dập làm tăng tải. Dùng exponential backoff, jitter và giảm concurrency.

**Retry 409 mà không đọc lại dữ liệu.** Version conflict cần quy tắc hợp nhất hoặc kiểm soát version.

**Dùng create với ID ngẫu nhiên khi retry.** Có thể tạo duplicate document. Dùng ID ổn định theo nghiệp vụ.

**Retry update script tăng/giảm không idempotent.** Timeout sau khi script đã chạy có thể làm side effect xảy ra lần hai. Dùng event ID, version hoặc phép gán xác định.

**Đối chiếu response bằng document ID duy nhất.** Một request có thể có nhiều operation trên cùng ID. Dùng vị trí và operation type cùng index/ID.

**Tạo NDJSON không có newline cuối.** Bulk parser yêu cầu định dạng newline-delimited và newline kết thúc request.

**Pretty-print từng source JSON thành nhiều dòng.** Body của một operation phải là một JSON object trên một dòng NDJSON.

**Cho rằng BulkOperations luôn trả item response.** Abstraction Spring Data thay đổi theo phiên bản và không phải API nào cũng expose toàn bộ response. Kiểm tra Javadoc hoặc dùng Java API Client khi cần chi tiết.

**Chỉ log HTTP request failure.** Dashboard sẽ bỏ sót item failures. Ghi metric ở cả request-level và item-level.

## 19. Quy trình xử lý một bulk batch

Một pipeline ingestion có thể thực hiện theo trình tự:

1. Chuẩn bị source document và ID ổn định.
2. Chia dữ liệu theo batch size và giới hạn payload bytes.
3. Lưu danh sách operation metadata theo đúng thứ tự gửi.
4. Gửi bulk request với NDJSON hợp lệ hoặc Java API Client.
5. Nếu có request-level exception, phân loại HTTP/transport error và xác định kết quả có chắc chắn hay không.
6. Nếu nhận BulkResponse, kiểm tra `errors` và số lượng `items`.
7. Ghép từng item với operation gốc theo vị trí.
8. Ghi nhận item thành công.
9. Phân loại item lỗi theo status, error type và operation semantics.
10. Retry subset có thể phục hồi bằng exponential backoff và jitter.
11. Đưa lỗi dữ liệu hoặc lỗi không thể retry vào dead-letter queue.
12. Đối soát các request timeout hoặc kết quả chưa xác định.
13. Theo dõi latency, throughput, error rate, retry count và queue pressure.
14. Chỉ đánh dấu batch hoàn tất khi mọi operation đã có trạng thái cuối cùng theo chính sách ứng dụng.

## 20. Tài liệu tham khảo

- [Elasticsearch - Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk): NDJSON format, operation types, response errors và item results.
- [Elasticsearch - Bulk API concepts](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html): cách xử lý nhiều operation và kết quả từng item.
- [Elasticsearch Java API Client - Bulk operations](https://www.elastic.co/docs/reference/elasticsearch/clients/java/usage/indexing-bulk): xây dựng bulk request và đọc BulkResponse bằng Java client.
- [Spring Data Elasticsearch - Bulk operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): sử dụng ElasticsearchOperations và BulkOperations.
- [Elasticsearch - Optimistic concurrency control](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/optimistic-concurrency-control): sequence number, primary term và version conflict.
- [Elasticsearch - Index API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-index): semantics của index và document ID.

Các class và builder method của Spring Data Elasticsearch và Elasticsearch Java API Client có thể khác theo phiên bản. Khi triển khai, hãy kiểm tra Javadoc của dependency trong dự án. Quy tắc cốt lõi vẫn là: HTTP response cho biết request-level outcome; `errors` báo có item failure; từng phần tử trong `items` mới cho biết operation nào thành công hoặc thất bại.
