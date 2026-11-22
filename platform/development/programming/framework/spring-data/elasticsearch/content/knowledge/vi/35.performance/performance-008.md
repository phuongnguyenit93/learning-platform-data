# Tối ưu bulk size, mức đồng thời và refresh interval

Khi ghi lượng lớn document vào Elasticsearch, hiệu năng phụ thuộc nhiều vào cách gom request, số request chạy đồng thời và thời điểm document được làm mới để search nhìn thấy. Gửi từng document một thường tạo quá nhiều HTTP round trip; gom quá nhiều document vào một bulk request lại làm tăng bộ nhớ, độ trễ và áp lực lên shard. Tăng concurrency quá mức có thể khiến write thread pool bị đầy và trả về lỗi `429 TOO_MANY_REQUESTS`. Refresh quá thường xuyên cũng làm tăng chi phí tạo segment và merge.

Ba nút điều chỉnh cần được xem cùng nhau:

- **Bulk size:** lượng dữ liệu trong một bulk request, thường đo bằng byte và số document.
- **Concurrency:** số bulk request đang được xử lý cùng lúc.
- **Refresh interval:** khoảng thời gian Elasticsearch tạo refresh để document mới có thể được search.

Không có một bộ giá trị tối ưu cho mọi cluster. Cách làm hiệu quả là bắt đầu với batch nhỏ, tăng dần một biến tại một thời điểm, đo throughput và latency, rồi dừng khi hiệu năng không còn cải thiện hoặc tài nguyên bắt đầu bão hòa.

## 1. Bulk API giải quyết vấn đề gì?

Nếu ứng dụng gửi 10.000 document bằng 10.000 request index riêng lẻ, mỗi document cần một lần gửi request, xử lý HTTP và phối hợp với Elasticsearch. Overhead này có thể lớn hơn chi phí ghi thực tế.

Bulk API cho phép gửi nhiều thao tác trong một request. Elasticsearch phân phối từng thao tác tới shard đích và xử lý chúng trong cùng một lần trao đổi HTTP.

Ví dụ request Bulk API:

~~~http
POST /products/_bulk
Content-Type: application/x-ndjson

{"index":{"_id":"P-100"}}
{"name":"Keyboard","category":"ACCESSORIES","price":49.99}
{"index":{"_id":"P-101"}}
{"name":"Mouse","category":"ACCESSORIES","price":19.99}
{"delete":{"_id":"P-102"}}
~~~

Bulk body dùng NDJSON (newline-delimited JSON):

- Dòng thứ nhất là action metadata, ví dụ `index`, `create`, `update` hoặc `delete`.
- Với `index`, `create` và `update`, dòng kế tiếp thường chứa document hoặc nội dung update.
- Với `delete`, action metadata là đủ, không có dòng source tiếp theo.
- Mỗi dòng phải kết thúc bằng newline; request thường kết thúc bằng newline cuối cùng.

Bulk API giảm số HTTP round trip nhưng không biến toàn bộ request thành một transaction. Một item có thể thành công trong khi item khác thất bại.

### 1.1. Các action thường dùng

| Action | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| `index` | Tạo document hoặc thay thế document cùng ID. | Đồng bộ toàn bộ source của document. |
| `create` | Chỉ tạo nếu ID chưa tồn tại. | Cần bảo đảm không ghi đè document hiện hữu. |
| `update` | Partial update hoặc chạy script trên document hiện có. | Chỉ thay đổi một phần source. |
| `delete` | Xóa document theo ID. | Xóa theo danh sách ID đã xác định. |

Nếu cần cập nhật toàn bộ document, `index` thường đơn giản hơn. Nếu chỉ thay một số field, `update` tránh phải gửi lại toàn bộ source nhưng có chi phí xử lý update riêng. Hãy đo theo workload thực tế.

## 2. Bulk size: đo bằng byte và số document

Bulk size là lượng dữ liệu được gửi trong một request. Có hai cách đo bổ sung cho nhau:

- Số document/action trong batch.
- Kích thước body đã serialize, tính bằng byte.

Chỉ giới hạn số document có thể gây batch quá lớn nếu document có source nặng. Ngược lại, chỉ giới hạn byte có thể tạo batch có rất ít document nếu mỗi document lớn.

Ví dụ 500 document nhỏ có thể chỉ tạo body 1 MB, nhưng 500 document chứa nested arrays hoặc nội dung dài có thể vượt hàng chục MB.

### 2.1. Điểm bắt đầu để benchmark

Có thể bắt đầu với bulk body khoảng 5 MB, sau đó tăng dần theo dữ liệu thực tế. Đây là điểm khởi đầu để thử nghiệm, không phải giá trị bắt buộc.

Một quy trình thử đơn giản:

1. Bắt đầu với 1 MB hoặc 5 MB.
2. Chạy một số batch đủ lớn để đo throughput ổn định.
3. Tăng body size lên khoảng gấp đôi.
4. So sánh documents/second, MB/second, latency và lỗi.
5. Dừng khi throughput gần như không tăng hoặc p95 latency, heap, GC hay rejected request tăng rõ rệt.

Không gửi request vượt giới hạn HTTP body của cluster. Mặc định `http.max_content_length` thường là 100 MB; giữ bulk request thấp hơn giới hạn này và chừa khoảng an toàn cho metadata, serialization và biến động kích thước document.

### 2.2. Số document không thay thế giới hạn byte

Giả sử mỗi document sau serialization có kích thước trung bình 10 KB:

| Số document | Kích thước source xấp xỉ |
| ---: | ---: |
| 100 | 1 MB |
| 500 | 5 MB |
| 1.000 | 10 MB |
| 5.000 | 50 MB |

Đây chỉ là ước tính. Bulk body còn có action metadata và newline, còn kích thước document có thể lệch đáng kể so với trung bình.

Với document có kích thước không đồng đều, hãy theo dõi byte thực tế của NDJSON body. Nếu batch được tạo trong ứng dụng, có thể serialize trước hoặc dùng bộ đếm byte để flush khi chạm ngưỡng.

### 2.3. Vì sao bulk quá nhỏ kém hiệu quả?

Bulk quá nhỏ làm tăng:

- Số HTTP request cần gửi.
- Overhead TLS/HTTP và serialization.
- Số lần coordinator nhận và phân phối request.
- Chi phí quản lý request trên client.
- Tỷ lệ overhead so với lượng dữ liệu hữu ích.

Nếu mỗi request chỉ có 1–5 document nhỏ, ứng dụng có thể đang bỏ lỡ lợi ích của Bulk API.

### 2.4. Vì sao bulk quá lớn cũng không tốt?

Bulk quá lớn có thể:

- Tăng bộ nhớ giữ body ở client và node nhận request.
- Tăng thời gian xử lý một request và độ trễ của batch.
- Tạo áp lực heap và network buffer.
- Khi request lỗi, lượng item cần kiểm tra hoặc retry lớn hơn.
- Tăng nguy cơ vượt `http.max_content_length`.
- Làm một shard nóng nếu phần lớn document trong bulk route về cùng shard.

Bulk request lớn không bảo đảm throughput cao hơn. Nếu các shard hoặc disk đã bão hòa, tăng body chỉ làm tăng thời gian chờ và lượng dữ liệu nằm trong flight.

## 3. Chọn batch theo byte, count và thời gian

Một batcher tốt thường có ít nhất hai ngưỡng:

- **Max operations:** số action tối đa.
- **Max bytes:** số byte tối đa của bulk body.

Có thể thêm ngưỡng thời gian để dữ liệu ít vẫn được flush, tránh chờ mãi để đủ batch.

Ví dụ chính sách:

~~~text
flush khi:
  operations >= 500
  HOẶC body_bytes >= 5 MB
  HOẶC thời gian chờ batch >= 200 ms
~~~

Các con số chỉ là giá trị khởi đầu để benchmark. Hệ thống cần điều chỉnh theo document size, throughput, latency mục tiêu và cluster capacity.

### 3.1. Không để batch chờ vô hạn

Nếu chỉ flush khi đủ 1.000 document, tenant có lượng ghi thấp có thể phải chờ lâu mới thấy dữ liệu được gửi đi. Thêm timer hoặc flush interval ở phía producer để batch nhỏ cũng được gửi sau một khoảng thời gian.

Ngưỡng thời gian của batcher ứng dụng khác với `index.refresh_interval` của Elasticsearch:

- Batch timeout quyết định khi nào client gửi bulk.
- Refresh interval quyết định khi nào document đã được index trở nên search-visible.

Hai khoảng thời gian này cộng dồn vào độ trễ nhìn thấy dữ liệu.

### 3.2. Chia batch theo giới hạn thực tế

Ví dụ Java chia danh sách thành các chunk theo số lượng:

~~~java
static <T> List<List<T>> chunks(List<T> items, int batchSize) {
    List<List<T>> result = new ArrayList<>();

    for (int start = 0; start < items.size(); start += batchSize) {
        int end = Math.min(start + batchSize, items.size());
        result.add(items.subList(start, end));
    }

    return result;
}
~~~

Đây là cách đơn giản khi kích thước document tương đối đồng đều. Với document lớn/nhỏ khác nhau, nên tạo batch dựa trên byte đã serialize thay vì chỉ dùng số phần tử.

Không tạo tất cả bản sao của các batch nếu danh sách đầu vào đã lớn. Có thể xử lý theo iterator hoặc stream để giữ bộ nhớ ở mức ổn định.

## 4. Bulk trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp bulk operations trên `ElasticsearchOperations` và `ElasticsearchTemplate`. Có thể chuyển entity thành `IndexQuery`, sau đó gửi một danh sách trong cùng bulk request.

Ví dụ entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Double)
    private Double price;

    // getters và setters
}
~~~

Tạo các `IndexQuery`:

~~~java
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;

List<IndexQuery> queries = products.stream()
        .map(product -> new IndexQueryBuilder()
                .withId(product.getId())
                .withObject(product)
                .build())
        .toList();
~~~

Gửi bulk:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

List<IndexedObjectInformation> results =
        operations.bulkIndex(
                queries,
                IndexCoordinates.of("products")
        );
~~~

`bulkIndex` gửi nhiều index actions trong một request bulk. Kiểu kết quả cung cấp thông tin về các document được index theo API phiên bản đang dùng.

### 4.1. Bulk update

Nếu cần partial update, tạo `UpdateQuery` cho từng document:

~~~java
UpdateQuery update = UpdateQuery.builder("P-100")
        .withDocument(Document.create().append("price", 45.99))
        .build();
~~~

Sau đó gửi một danh sách:

~~~java
operations.bulkUpdate(
        updateQueries,
        IndexCoordinates.of("products")
);
~~~

`bulkUpdate` thích hợp khi nhiều document chỉ thay một số field. Cần kiểm tra semantics của partial update, script và version conflict theo từng item.

### 4.2. Bulk delete

Có thể gom ID cần xóa:

~~~java
operations.bulkDelete(
        ids,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Đảm bảo danh sách ID đã được xác thực và nằm trong phạm vi tenant/index được phép. Bulk delete không tự thêm điều kiện nghiệp vụ nếu ứng dụng chỉ truyền ID.

### 4.3. BulkOptions và refresh policy

Các overload bulk của Spring Data cho phép truyền `BulkOptions` trong những phiên bản hỗ trợ. Có thể cấu hình refresh policy, timeout và một số tùy chọn bulk khác qua builder.

Ví dụ dạng cấu hình:

~~~java
BulkOptions bulkOptions = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.NONE)
        .build();

operations.bulkIndex(
        queries,
        bulkOptions,
        IndexCoordinates.of("products")
);
~~~

Tên package và builder method của `BulkOptions` cần khớp với version Spring Data Elasticsearch trong dự án. Nếu không cần tùy chọn riêng, overload mặc định thường đủ; tránh đặt refresh policy thành IMMEDIATE cho mọi batch chỉ để dữ liệu xuất hiện ngay trong search.

### 4.4. Chọn Operations hay Java API Client?

Ưu tiên `ElasticsearchOperations.bulkIndex`, `bulkUpdate` hoặc `bulkDelete` khi cần mapping entity Spring Data và các abstraction sẵn có.

Dùng Elasticsearch Java API Client trực tiếp khi cần Bulk API option hoặc response metadata mà abstraction Spring Data đang dùng chưa expose. Hãy tái sử dụng client bean do Spring quản lý; không tạo client mới cho mỗi batch.

## 5. Concurrency: số bulk request chạy đồng thời

Bulk size quyết định kích thước một request. Concurrency quyết định số request đang được xử lý song song.

Ví dụ:

~~~text
Producer
   |
   +--> Bulk 1 ----+
   +--> Bulk 2 ----+----> Elasticsearch
   +--> Bulk 3 ----+
   +--> Bulk 4 ----+
~~~

Tăng concurrency có thể giúp tận dụng network, CPU và các shard khi một request chưa sử dụng hết năng lực cluster. Nhưng quá nhiều request đồng thời làm tăng lượng dữ liệu đang chờ, áp lực heap, disk và write thread pool.

### 5.1. Bắt đầu với concurrency thấp

Một cách benchmark thận trọng:

- Bắt đầu với 1 bulk request đang chạy.
- Tăng lên 2, 4, rồi 8 nếu throughput vẫn tăng và latency ổn định.
- Theo dõi write rejections, bulk latency, CPU, heap, disk I/O và network.
- Dừng tăng khi throughput không cải thiện hoặc lỗi/latency tăng.

Đây không phải công thức cố định. Cluster nhỏ có thể bão hòa ở concurrency thấp; cluster lớn có thể xử lý nhiều request hơn. Kích thước document, số shard và cách routing đều ảnh hưởng.

### 5.2. Tránh unbounded concurrency

Không dùng `parallelStream()` hoặc tạo một Future cho mỗi batch của hàng triệu document mà không giới hạn. Cách đó có thể giữ quá nhiều request và payload trong bộ nhớ.

Cần giới hạn:

- Số batch đang chạy.
- Tổng byte đang in-flight.
- Số item trong queue producer.
- Thời gian chờ khi queue đầy.
- Số lần retry đồng thời.

Bounded concurrency tạo backpressure: khi Elasticsearch chậm, producer giảm tốc độ hoặc chờ thay vì tiếp tục tích lũy payload.

### 5.3. Concurrency phải phù hợp với shard distribution

Một bulk request có thể chứa document thuộc nhiều shard. Elasticsearch phân phối các action tới shard đích. Nếu tất cả document dùng cùng routing key, nhiều request có thể dồn vào một shard và tạo hot spot.

Hãy quan sát:

- Số primary shard.
- Phân bố document theo shard.
- Routing key có bị lệch không.
- Write queue và rejected count.
- Disk utilization và merge pressure.
- Có node nào nhận phần lớn bulk traffic không.

Tăng số request đồng thời không giải quyết được shard hot spot do routing skew. Khi đó cần xem lại routing strategy, index layout hoặc phân bố workload.

## 6. Xử lý lỗi 429 và backpressure

Khi Elasticsearch không thể nhận thêm công việc, bulk item hoặc request có thể bị từ chối với HTTP `429 TOO_MANY_REQUESTS` hoặc lỗi tương ứng trong response.

Đây là tín hiệu cần giảm tốc độ ghi hoặc retry sau khi hệ thống có thời gian phục hồi.

### 6.1. Bulk response có thể thành công một phần

Một Bulk API response có cấu trúc như:

~~~json
{
  "took": 42,
  "errors": true,
  "items": [
    {
      "index": {
        "_id": "P-100",
        "status": 201,
        "result": "created"
      }
    },
    {
      "index": {
        "_id": "P-101",
        "status": 429,
        "error": {
          "type": "es_rejected_execution_exception",
          "reason": "rejected execution"
        }
      }
    }
  ]
}
~~~

HTTP request tổng thể có thể được trả về nhưng một số item vẫn lỗi. Ứng dụng phải đọc `errors` và từng entry trong `items`.

Không giả định HTTP 200 nghĩa là tất cả document đã được ghi thành công.

### 6.2. Retry chỉ item thất bại

Một quy trình phù hợp:

1. Gửi bulk.
2. Duyệt từng item response.
3. Ghi nhận item thành công.
4. Chỉ đưa item lỗi có thể retry vào retry queue.
5. Với 429, chờ backoff rồi gửi lại.
6. Với lỗi mapping hoặc validation, chuyển sang dead-letter/error handling thay vì retry vô hạn.

Nếu gửi lại toàn bộ bulk, những item đã thành công có thể bị thực thi lại. Với `index` dùng ID cố định, thao tác thay thế source có thể idempotent trong một số use case; với `create`, generated ID hoặc update script tăng giá trị, gửi lại có thể tạo duplicate hoặc thay đổi dữ liệu thêm lần nữa.

### 6.3. Exponential backoff và jitter

Không retry ngay lập tức theo vòng lặp tight loop. Có thể dùng backoff tăng dần:

~~~text
attempt 1: chờ 200 ms
attempt 2: chờ 400 ms
attempt 3: chờ 800 ms
attempt 4: chờ 1.6 s
...
~~~

Thêm jitter ngẫu nhiên để nhiều producer không đồng loạt retry cùng thời điểm. Đặt số lần retry tối đa và giới hạn tổng thời gian retry.

Các giá trị trên chỉ minh họa. Chính sách cần dựa trên latency mục tiêu và khả năng phục hồi của cluster.

### 6.4. Phân loại lỗi trước khi retry

| Loại lỗi | Cách xử lý |
| --- | --- |
| 429 / rejected execution | Backoff, giảm concurrency hoặc giảm batch pressure, rồi retry item lỗi. |
| 502/503/504 hoặc lỗi mạng tạm thời | Retry có giới hạn nếu biết request chưa tạo hiệu ứng không thể lặp. |
| Mapping exception | Sửa schema/document; không retry nguyên trạng. |
| Parsing/validation error | Đưa vào error queue hoặc dead-letter để xử lý. |
| 401/403 | Sửa credential/privilege; retry không giải quyết. |
| Version conflict | Đọc lại và áp dụng quy tắc concurrency; không retry mù. |
| Document missing trong update | Kiểm tra logic upsert hoặc thứ tự sự kiện. |

### 6.5. Idempotency và thứ tự ghi

Retry an toàn phụ thuộc loại action:

- `index` với ID xác định và cùng source thường có thể lặp lại mà không tạo document mới.
- `create` với ID cố định sẽ conflict nếu lần trước đã thành công nhưng response bị mất.
- `update` script kiểu `stock += 1` không idempotent; gửi lại có thể tăng hai lần.
- `delete` theo ID thường có thể lặp về trạng thái cuối, nhưng response có thể khác.
- Các update phụ thuộc trạng thái cần OCC hoặc sequence/event ID để chống xử lý lặp.

Nếu cùng một document được cập nhật bởi nhiều producer, hãy định nghĩa thứ tự nghiệp vụ và dùng optimistic concurrency hoặc cơ chế idempotency phù hợp. Bulk API không tự tạo transaction giữa nhiều request.

## 7. Bulk size và concurrency tác động lẫn nhau

Không tối ưu từng biến riêng lẻ mà bỏ qua tổng lượng dữ liệu đang in-flight.

Ví dụ:

| Bulk body | Concurrent requests | Dữ liệu tối đa đang in-flight gần đúng |
| ---: | ---: | ---: |
| 2 MB | 2 | 4 MB |
| 5 MB | 4 | 20 MB |
| 10 MB | 8 | 80 MB |
| 20 MB | 16 | 320 MB |

Đây là phép nhân đơn giản để ước tính payload đang bay, chưa tính object Java, buffer, response và overhead của HTTP/client. Heap thực tế có thể cần lớn hơn nhiều lần body size.

Một batch 20 MB có thể ổn khi chỉ chạy một request, nhưng trở nên nặng khi 16 request cùng hoạt động. Vì vậy, giới hạn đồng thời cần được điều chỉnh cùng bulk size.

### 7.1. Một ví dụ điều chỉnh

Giả sử cấu hình ban đầu:

- Bulk body khoảng 5 MB.
- Tối đa 4 request đồng thời.
- Refresh interval 1 giây.
- Retry 429 có backoff.

Nếu throughput tăng khi chuyển concurrency từ 2 lên 4 nhưng không tăng khi lên 8, giữ mức 4. Nếu tăng bulk size từ 5 MB lên 10 MB làm latency tăng mạnh mà throughput chỉ cải thiện rất ít, quay về 5 MB.

Đừng chọn cấu hình chỉ theo thời gian chạy của một batch. Đo trong khoảng đủ dài để bao gồm refresh, merge và workload search đồng thời.

## 8. Refresh interval và near-real-time search

Elasticsearch là hệ thống near-real-time. Một document được index thành công chưa chắc xuất hiện ngay trong search.

Refresh tạo một searcher mới để các thay đổi đã index trở nên visible cho search. Đây là cơ chế khác với việc ghi document vào translog và khác với flush.

Setting `index.refresh_interval` quyết định khoảng thời gian refresh tự động của index.

Ví dụ:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "5s"
  }
}
~~~

Nếu refresh interval là 5 giây, thay đổi mới thường được search nhìn thấy sau lần refresh kế tiếp, ngoài thời gian xử lý request và scheduling.

Với index tự quản lý, refresh interval mặc định thường là 1 giây. Một số môi trường được quản lý hoặc serverless có thể dùng giá trị khác; hãy kiểm tra setting thực tế thay vì dựa vào mặc định giả định.

### 8.1. Refresh có chi phí gì?

Refresh tạo searcher/segment mới để search có thể nhìn thấy dữ liệu. Refresh quá thường xuyên có thể:

- Tạo nhiều segment nhỏ.
- Tăng chi phí merge.
- Tăng CPU và I/O.
- Làm giảm throughput indexing.
- Tăng áp lực tài nguyên khi vừa ingest vừa search.

Nếu workload chủ yếu là bulk ingestion và không cần search ngay, tăng refresh interval có thể cải thiện hiệu năng ghi.

### 8.2. Refresh interval dài hơn

Ví dụ chuyển từ 1 giây lên 30 giây:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "30s"
  }
}
~~~

Thay đổi này giảm tần suất refresh tự động. Đổi lại, document mới có thể phải chờ lâu hơn trước khi xuất hiện trong search.

Có thể dùng khoảng 5–30 giây làm vùng thử nghiệm cho workload ingest, nhưng cần đo theo SLA search visibility và cluster. Không có một giá trị chuẩn áp dụng cho mọi index.

### 8.3. Tạm tắt refresh trong initial bulk load

Khi nạp dữ liệu lớn vào index mới và không cần search trong thời gian nạp, có thể tạm tắt refresh tự động:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "-1"
  }
}
~~~

Sau khi hoàn tất bulk load:

1. Gửi các bulk request còn lại và xử lý hết lỗi.
2. Khôi phục refresh interval mong muốn.
3. Gọi refresh một lần nếu cần dữ liệu visible ngay.
4. Xác minh search và count.
5. Mở workload đọc hoặc chuyển alias khi index đã sẵn sàng.

Khôi phục setting:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "refresh_interval": "1s"
  }
}
~~~

Không quên khôi phục refresh interval sau initial load. Nếu để `-1`, document mới có thể không tự xuất hiện trong search cho tới khi có refresh thủ công hoặc thay đổi cấu hình.

Tắt refresh phù hợp với bulk load có cửa sổ bảo trì hoặc index chưa phục vụ truy vấn. Không dùng cho index đang cần near-real-time search.

## 9. Refresh policy trong request

Bulk API có query parameter `refresh` với các lựa chọn chính:

| Giá trị | Hành vi | Tác động |
| --- | --- | --- |
| `false` | Không yêu cầu refresh riêng cho request. | Throughput tốt hơn; search visibility chờ refresh tự động. |
| `wait_for` | Chờ refresh kế tiếp làm các thay đổi visible. | Có thể tăng latency request nhưng không ép refresh ngay lập tức. |
| `true` | Yêu cầu refresh ngay sau thao tác. | Tăng chi phí; không nên dùng cho mọi bulk batch trong pipeline lớn. |

Ví dụ:

~~~http
POST /products/_bulk?refresh=wait_for
Content-Type: application/x-ndjson

{"index":{"_id":"P-100"}}
{"name":"Keyboard","price":49.99}
~~~

`refresh=wait_for` hữu ích khi một thao tác cần bảo đảm document có thể được search ngay sau khi request hoàn tất, ví dụ luồng người dùng vừa tạo bản ghi rồi chuyển sang trang search.

Không gắn `refresh=true` vào mọi bulk request. Nếu mỗi batch đều ép refresh, Elasticsearch có thể tạo rất nhiều segment nhỏ và throughput giảm rõ rệt.

Một chiến lược thực tế:

- Bulk ingestion thông thường: không yêu cầu refresh riêng.
- Luồng cần read-after-write: dùng `wait_for` ở request thích hợp.
- Initial load: tăng hoặc tắt refresh interval rồi refresh một lần khi hoàn tất.
- Không dùng `true` làm mặc định cho batch pipeline.

### 9.1. Refresh khác với flush

| Thao tác | Mục đích |
| --- | --- |
| Refresh | Làm thay đổi đã index trở nên visible cho search. |
| Flush | Thực hiện Lucene commit và xử lý translog theo cơ chế Elasticsearch. |
| Force merge | Hợp nhất segment; là tác vụ quản trị tốn tài nguyên. |

Không gọi `_flush` sau mỗi bulk chỉ để search thấy dữ liệu. Search visibility được điều khiển bởi refresh. Cũng không chạy force merge liên tục trong lúc ingest vì có thể cạnh tranh CPU và I/O với indexing.

## 10. Phối hợp bulk và refresh trong Spring Data

Spring Data có thể gửi bulk với `BulkOptions` và cấu hình refresh policy cho request. Tuy nhiên, refresh interval là index setting; refresh policy là hành vi của một request cụ thể.

Phân biệt:

- `index.refresh_interval`: cấu hình tự động refresh cho index.
- `BulkOptions` refresh policy: lựa chọn refresh áp dụng cho bulk request.
- `IndexOperations.refresh()`: yêu cầu refresh index ở thời điểm được gọi.

Ví dụ dùng request không ép refresh:

~~~java
BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.NONE)
        .build();

operations.bulkIndex(
        queries,
        options,
        IndexCoordinates.of("products")
);
~~~

Khi cần search visibility sau một bulk request:

~~~java
BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
        .build();

operations.bulkIndex(
        queries,
        options,
        IndexCoordinates.of("products")
);
~~~

Tên enum, package và builder method có thể thay đổi theo phiên bản Spring Data Elasticsearch. Hãy kiểm tra API dependency của dự án. Điểm quan trọng là không dùng `IMMEDIATE`/`true` cho mọi batch nếu throughput là mục tiêu chính.

Có thể refresh rõ ràng sau một đợt bulk:

~~~java
IndexOperations indexOperations =
        operations.indexOps(IndexCoordinates.of("products"));

indexOperations.refresh();
~~~

`refresh()` đồng bộ trong API imperative. Với ứng dụng reactive, dùng `ReactiveIndexOperations.refresh()` và ghép publisher vào pipeline thay vì block.

## 11. Bulk pipeline trong ứng dụng imperative

Một service ghi bulk thường có ba phần:

1. Chuyển entity thành `IndexQuery`.
2. Chia danh sách thành batch.
3. Gửi batch với concurrency giới hạn và xử lý kết quả.

Ví dụ tuần tự, phù hợp làm baseline:

~~~java
@Service
public class ProductBulkWriter {

    private static final IndexCoordinates INDEX =
            IndexCoordinates.of("products");

    private final ElasticsearchOperations operations;

    public ProductBulkWriter(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void write(List<Product> products, int batchSize) {
        for (List<Product> batch : chunks(products, batchSize)) {
            List<IndexQuery> queries = batch.stream()
                    .map(product -> new IndexQueryBuilder()
                            .withId(product.getId())
                            .withObject(product)
                            .build())
                    .toList();

            operations.bulkIndex(queries, INDEX);
        }
    }
}
~~~

Đây là baseline có một bulk request tại một thời điểm. Bắt đầu bằng cách này giúp đo throughput và xác định bulk size trước khi thêm concurrency.

### 11.1. Tăng concurrency có giới hạn

Nếu benchmark cho thấy cluster còn năng lực, có thể chạy nhiều batch qua bounded executor hoặc một worker pool có giới hạn.

Nguyên tắc:

- Không submit toàn bộ hàng triệu batch vào queue không giới hạn.
- Giới hạn số worker.
- Giới hạn tổng byte đang chờ và đang in-flight.
- Chờ kết quả batch để phát hiện lỗi.
- Dừng producer khi queue đạt ngưỡng.
- Giữ một cơ chế shutdown chờ các batch đang chạy hoàn tất.

Không dùng `parallelStream()` như một cơ chế điều tiết tải. Nó không cung cấp giới hạn theo byte, retry policy theo item hoặc backpressure phù hợp với bulk workload.

### 11.2. Ghi cùng document ID từ nhiều batch

Nếu hai batch cùng ghi một `_id`, thứ tự hoàn tất có thể khác thứ tự producer tạo batch. Điều này có thể khiến dữ liệu cũ ghi sau dữ liệu mới.

Các cách xử lý:

- Partition queue theo document ID để cùng ID luôn vào cùng worker.
- Dùng version hoặc OCC nếu cập nhật dựa trên snapshot.
- Đảm bảo event có sequence/version nghiệp vụ và bỏ qua event cũ.
- Dùng thao tác idempotent có điều kiện rõ ràng.

Tăng concurrency mà không định nghĩa thứ tự ghi có thể làm dữ liệu cuối cùng sai dù tất cả request đều trả thành công.

## 12. Reactive bulk pipeline và backpressure

Trong ứng dụng WebFlux, cần giữ publisher xuyên suốt. Không gọi imperative `ElasticsearchOperations.bulkIndex` trực tiếp trên event-loop thread.

ReactiveElasticsearchOperations cung cấp các API bulk theo publisher ở những phiên bản hỗ trợ. Có thể gom input bằng Reactor `bufferTimeout` để tạo batch theo count và thời gian:

~~~java
Flux<IndexQuery> queries = products
        .map(product -> new IndexQueryBuilder()
                .withId(product.getId())
                .withObject(product)
                .build());

return queries
        .bufferTimeout(500, Duration.ofMillis(200))
        .flatMap(batch ->
                reactiveOperations.bulkIndex(
                        Flux.fromIterable(batch),
                        IndexCoordinates.of("products")
                ),
                4
        )
        .then();
~~~

Ví dụ minh họa ý tưởng batching và giới hạn tối đa 4 bulk operation đồng thời. Kiểu trả về chính xác của `bulkIndex`, overload nhận `Publisher` và generic result cần khớp với version Spring Data Elasticsearch đang dùng.

`flatMap(..., 4)` giới hạn số inner publisher hoạt động đồng thời. Nếu muốn giữ thứ tự xử lý batch, dùng `concatMap`; nếu cần song song nhưng phát kết quả theo thứ tự nguồn, cân nhắc `flatMapSequential`.

### 12.1. Backpressure và buffer

`bufferTimeout(500, Duration.ofMillis(200))` flush khi đủ 500 item hoặc hết 200 ms. Nó chỉ giới hạn count, không giới hạn byte. Nếu document size chênh lệch lớn, cần custom batching theo byte hoặc giới hạn payload trước khi buffer.

Không dùng `onBackpressureBuffer()` với queue vô hạn cho ingestion. Nếu Elasticsearch chậm hơn producer, buffer sẽ tăng dần và có thể làm cạn heap. Hãy giới hạn buffer, giảm tốc độ producer hoặc ghi tạm vào durable queue.

### 12.2. Giới hạn concurrency reactive

Ví dụ `flatMap(..., 4)` không có nghĩa cluster chỉ nhận tối đa 4 request từ toàn hệ thống. Nó chỉ giới hạn subscription trong pipeline đó. Nếu có nhiều application instance hoặc nhiều pipeline, tổng concurrency cluster nhận được là tổng của tất cả caller.

Cần tính tổng số producer/instance và đặt rate limit hoặc concurrency budget ở tầng hệ thống.

## 13. Mapping và dữ liệu cũng ảnh hưởng bulk throughput

Bulk size và concurrency không phải yếu tố duy nhất.

Một số yếu tố mapping ảnh hưởng hiệu năng ghi:

- Analyzer text có chi phí tokenization.
- `doc_values` và inverted index cần được xây dựng khi ghi field có index.
- Field cardinality cao có thể làm tăng chi phí cấu trúc index.
- Nested objects có thể tạo nhiều Lucene documents cho một source document.
- Dynamic mapping quá linh hoạt có thể làm mapping phình lớn.
- Ingest pipeline/script processor thêm CPU vào mỗi document.
- Nhiều field không cần search/sort/aggregation vẫn có thể tạo index overhead.

Hãy khai báo mapping phù hợp với use case. Nếu một field chỉ cần lưu và không cần search, cân nhắc `index: false` hoặc kiểu field phù hợp. Không tắt indexing hàng loạt nếu nghiệp vụ vẫn cần filter/sort trên field đó.

### 13.1. Replicas trong initial load

Replica shard cũng cần được cập nhật khi index document. Với initial load vào index mới, một số hệ thống tạm giảm `number_of_replicas` xuống 0 rồi khôi phục sau khi load xong để giảm lượng ghi.

Đây là lựa chọn vận hành có rủi ro:

- Trong thời gian replica bằng 0, index không có bản sao dự phòng cho primary.
- Node failure có thể làm mất khả năng phục vụ hoặc dữ liệu đã ghi tùy trạng thái và cấu hình.
- Sau khi khôi phục replica, cluster cần thời gian copy shard và có thể chịu thêm I/O.

Chỉ dùng trong cửa sổ nạp dữ liệu được kiểm soát, khi có nguồn dữ liệu có thể nạp lại và chấp nhận rủi ro availability. Không thay đổi replica count trên index production đang phục vụ mà không có kế hoạch.

## 14. Refresh, replica và search workload

Nếu index vừa ghi vừa search, refresh interval dài hơn có thể cải thiện throughput nhưng làm dữ liệu chậm visible. Nếu search latency và freshness quan trọng, cần đo hai mục tiêu cùng lúc:

- Write throughput: document/second và MB/second.
- Search visibility delay: thời gian từ khi bulk thành công tới khi document xuất hiện trong search.

Khi tăng refresh interval, có thể thấy write throughput tăng nhưng freshness giảm. Đây là trade-off nghiệp vụ, không chỉ là tuning kỹ thuật.

Nếu workload search nặng cùng lúc ingestion:

- Theo dõi search latency và indexing latency riêng.
- Không chạy refresh quá thường xuyên.
- Cân nhắc tách index hoặc workload theo thời gian.
- Giữ page size và aggregation size hợp lý.
- Không ép refresh chỉ để kiểm thử một request nếu không phản ánh workload thật.

## 15. Đo hiệu năng và chọn cấu hình

Cần đo cùng một tập dữ liệu, mapping và cluster state để so sánh các cấu hình.

Các chỉ số nên thu thập:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Documents/second | Throughput theo số document. |
| MB/second | Throughput theo byte thực tế. |
| Bulk latency p50/p95/p99 | Thời gian xử lý một batch. |
| 429/rejected count | Cluster đang bị quá tải hoặc write queue đầy. |
| Client queue depth | Producer đang tích lũy bao nhiêu batch. |
| In-flight bytes | Lượng payload đang gửi/chờ response. |
| CPU/heap/GC | Áp lực xử lý và bộ nhớ. |
| Disk I/O và merge time | Chi phí ghi segment và merge. |
| Refresh time/count | Chi phí refresh và tần suất refresh. |
| Search latency/freshness | Ảnh hưởng của ingestion tới người đọc. |

### 15.1. Benchmark từng biến

Một ma trận thử nghiệm:

| Lần thử | Bulk body mục tiêu | Concurrency | Refresh interval |
| --- | ---: | ---: | --- |
| A | 1 MB | 1 | 1s |
| B | 5 MB | 1 | 1s |
| C | 5 MB | 2 | 1s |
| D | 5 MB | 4 | 1s |
| E | 10 MB | 4 | 1s |
| F | 10 MB | 4 | 5s |
| G | 10 MB | 4 | 30s |

Đây là ví dụ ma trận, không phải cấu hình khuyến nghị cố định. Mỗi lần thử nên thay đổi một biến chính để hiểu tác động.

Không benchmark chỉ trên một vài trăm document nhỏ. Dùng dữ liệu có kích thước và mapping gần production, số shard tương tự và có workload search đồng thời nếu production cũng có.

### 15.2. Tiêu chí dừng tăng tải

Nên dừng tăng bulk size hoặc concurrency khi:

- Throughput không tăng đáng kể.
- p95/p99 latency vượt SLA.
- 429/rejected request bắt đầu tăng.
- Heap hoặc GC pressure tăng liên tục.
- Disk I/O hoặc merge backlog trở thành bottleneck.
- Search latency/freshness không còn đáp ứng yêu cầu.
- Producer queue tăng mãi và không thể drain.

Tối ưu không có nghĩa là đẩy cluster tới 100% resource utilization. Cần chừa capacity cho burst, recovery, merge và workload đọc.

## 16. Các API và công cụ quan sát

Có thể dùng các API Elasticsearch để xem tình trạng cluster và indexing:

- Nodes stats: CPU, heap, thread pool, filesystem, indexing/search stats.
- Cluster stats: tổng quan node, index, shard và resource.
- Index stats: indexing, refresh, merge, segments và store.
- Thread pool stats: active, queue và rejected của write thread pool.
- CAT indices/shards: kích thước và phân bố shard để điều tra nhanh.

Ví dụ kiểm tra thread pool:

~~~http
GET /_nodes/stats/thread_pool
~~~

Ví dụ kiểm tra index stats:

~~~http
GET /products/_stats/indexing,refresh,merge,segments,store
~~~

Ví dụ kiểm tra shard:

~~~http
GET /_cat/shards/products?v
~~~

Tên thread pool và các field stats có thể khác theo phiên bản. Tập trung xem rejected count, queue growth, refresh/merge activity và shard imbalance.

Ở phía ứng dụng, ghi metric cho mỗi bulk:

- Số action.
- Request bytes.
- Thời gian gửi và thời gian nhận.
- Số item thành công/thất bại theo loại.
- Số retry và backoff delay.
- Concurrency hiện tại.
- Queue depth.
- Tenant hoặc workload class nếu cần phân tích.

Không log toàn bộ source document trong mỗi bulk error. Ghi ID, index, status và error type phù hợp với chính sách bảo vệ dữ liệu.

## 17. Những anti-pattern cần tránh

| Anti-pattern | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Gửi từng document một | Quá nhiều HTTP overhead. | Gom thành bulk request. |
| Bulk chỉ giới hạn theo số document | Batch có thể quá lớn khi source nặng. | Giới hạn cả count và bytes. |
| Bulk request quá lớn | Heap, latency và retry cost tăng. | Tăng dần theo benchmark và giữ dưới body limit. |
| Gửi quá nhiều request đồng thời | 429, queue và heap pressure. | Bounded concurrency và backpressure. |
| Retry ngay lập tức khi 429 | Làm cluster quá tải nặng hơn. | Exponential backoff, jitter và giảm tốc độ. |
| Retry toàn bộ bulk | Lặp lại item đã thành công. | Chỉ retry item thất bại có thể retry. |
| Không kiểm tra bulk item response | Bỏ sót lỗi dù request tổng thể được trả về. | Kiểm tra `errors` và từng item. |
| Dùng `refresh=true` mọi batch | Nhiều segment nhỏ, indexing chậm. | Để refresh tự động hoặc dùng `wait_for` khi cần. |
| Tắt refresh và quên bật lại | Document không tự visible theo chu kỳ. | Lưu giá trị cũ và khôi phục sau initial load. |
| Tăng concurrency mà không xem routing | Một shard có thể trở thành hot spot. | Kiểm tra shard distribution và routing skew. |
| `parallelStream()` không giới hạn | Khó kiểm soát in-flight payload và retry. | Worker pool hoặc Reactor concurrency có giới hạn. |
| Buffer reactive vô hạn | Producer nhanh hơn consumer làm cạn heap. | Buffer bounded và backpressure. |
| Bulk update cùng ID không có thứ tự | Ghi cũ có thể hoàn tất sau ghi mới. | Partition theo ID hoặc dùng OCC/version. |
| Giảm replicas trên production tùy tiện | Mất khả năng dự phòng trong thời gian load. | Chỉ thực hiện trong cửa sổ có kiểm soát. |
| Force merge trong lúc ingest | Cạnh tranh CPU và disk I/O. | Để merge tự nhiên; chỉ force merge theo quy trình riêng. |

## 18. Quy trình tuning cho một ứng dụng Spring Data

Một quy trình thực tế có thể đi theo thứ tự:

1. Xác định mục tiêu: throughput, freshness hay cả hai; ghi lại SLA.
2. Đo kích thước document trung bình và p95 sau serialization.
3. Tạo batch theo count, byte và timeout.
4. Bắt đầu bulk body khoảng 1–5 MB và một request đồng thời.
5. Kiểm tra partial failure và triển khai retry item-level cho lỗi tạm thời.
6. Tăng bulk size tới khi throughput không còn cải thiện.
7. Giữ bulk size phù hợp rồi tăng concurrency từng bước.
8. Theo dõi 429, write queue, heap, CPU, disk và merge.
9. Điều chỉnh refresh interval theo yêu cầu search visibility.
10. Với initial load, cân nhắc refresh interval dài hoặc `-1` rồi khôi phục sau khi nạp xong.
11. Kiểm tra mapping, routing và shard distribution nếu throughput không tăng.
12. Kiểm thử khi có search workload đồng thời.
13. Chạy benchmark đủ lâu để quan sát merge và refresh ổn định.
14. Lưu cấu hình theo workload/index và theo dõi khi dữ liệu tăng.

Không sao chép cấu hình bulk/concurrency từ môi trường khác mà không đo. Cùng một batch size có thể hoạt động tốt trên cluster nhiều node nhưng gây quá tải trên cluster nhỏ hoặc shard không cân bằng.

## 19. Tài liệu tham khảo

- [Elasticsearch — Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html)
- [Elasticsearch — Tune for indexing speed](https://www.elastic.co/guide/en/elasticsearch/reference/current/tune-for-indexing-speed.html)
- [Elasticsearch — Refresh API](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-refresh.html)
- [Elasticsearch — Index settings: refresh interval](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-modules.html)
- [Elasticsearch — Thread pool settings](https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-threadpool.html)
- [Elasticsearch — Nodes stats API](https://www.elastic.co/guide/en/elasticsearch/reference/current/cluster-nodes-stats.html)
- [Spring Data Elasticsearch — Bulk operations and templates](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — Reactive operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/reactive-template.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)

Bulk size quyết định lượng dữ liệu trong một request; concurrency quyết định số request đang chạy cùng lúc; refresh interval quyết định độ trễ search visibility. Hãy đo bulk theo byte lẫn số document, giới hạn tổng payload in-flight, retry từng item có thể phục hồi với backoff và kiểm tra partial failures. Với workload ghi lớn, tăng refresh interval hoặc tạm tắt refresh có thể cải thiện throughput, nhưng phải khôi phục setting và chấp nhận độ trễ nhìn thấy dữ liệu tương ứng.

