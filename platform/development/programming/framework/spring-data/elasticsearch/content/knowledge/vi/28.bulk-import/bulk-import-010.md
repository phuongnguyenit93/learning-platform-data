# Nạp dữ liệu lớn, chia lô và kiểm soát bộ nhớ

Khi nạp vài chục document vào Elasticsearch, gọi `save()` cho từng entity có thể vẫn đáp ứng được yêu cầu. Nhưng khi phải nhập hàng trăm nghìn hoặc hàng triệu bản ghi, cách gửi từng request riêng lẻ tạo ra nhiều chi phí mạng, serialization và xử lý request. Ứng dụng thường cần dùng Bulk API để gửi nhiều thao tác index/update/delete trong một request.

Bulk API cải thiện throughput, nhưng không có nghĩa nên gom toàn bộ dữ liệu vào một danh sách rồi gửi một lần. Một batch quá lớn có thể làm heap tăng đột biến, tạo request payload lớn, tăng thời gian xử lý và khiến retry trở nên tốn kém. Một batch quá nhỏ lại tạo nhiều request và giảm hiệu quả.

Một quy trình nhập liệu lớn cần kiểm soát đồng thời:

- **Nguồn dữ liệu:** đọc tuần tự hoặc theo cursor, không tải toàn bộ dataset vào heap.
- **Kích thước batch:** giới hạn số document và kích thước payload của mỗi bulk request.
- **Concurrency:** giới hạn số request đang chạy đồng thời để tạo backpressure.
- **Lỗi từng item:** phân biệt item thành công, lỗi có thể retry và lỗi dữ liệu cần xử lý riêng.
- **Refresh và replica:** chọn chính sách phù hợp để tăng throughput trong lúc import.
- **Checkpoint:** ghi nhận tiến độ sau khi batch đã được xử lý thành công.
- **Bộ nhớ:** giải phóng object, buffer và response sau mỗi batch.

Trong Spring Data Elasticsearch, `ElasticsearchOperations` cung cấp các phương thức bulk như `bulkIndex`, `bulkUpdate` và `bulkDelete`. Khi kết hợp chúng với nguồn dữ liệu streaming, batch có giới hạn và cơ chế retry có chọn lọc, ứng dụng có thể nhập dữ liệu lớn ổn định hơn.

## 1. Vì sao cần Bulk API?

Giả sử ứng dụng cần index 500.000 sản phẩm. Nếu gọi `save()` riêng cho từng sản phẩm, ứng dụng có thể phải gửi 500.000 request đến Elasticsearch.

```text
save(product-1)  -> HTTP request 1
save(product-2)  -> HTTP request 2
save(product-3)  -> HTTP request 3
...
save(product-N)  -> HTTP request N
```

Mỗi request có overhead như:

- Thiết lập và xử lý HTTP request/response.
- Serialize document và metadata.
- Điều phối request giữa client, node nhận request và shard.
- Xử lý refresh/replica theo cấu hình cluster.
- Quản lý callback, future hoặc connection ở phía ứng dụng.

Bulk API cho phép gửi nhiều thao tác trong cùng một request:

```text
Batch 1: document 1 ... document 500  -> HTTP request 1
Batch 2: document 501 ... document 1000 -> HTTP request 2
Batch 3: document 1001 ... document 1500 -> HTTP request 3
...
```

Thay vì 500.000 request, ứng dụng có thể gửi khoảng 1.000 request nếu mỗi batch có 500 document. Con số thực tế cần được benchmark; batch size tối ưu phụ thuộc kích thước document, số shard, mapping, analyzer, replica và tài nguyên cluster.

Bulk API không biến toàn bộ batch thành một transaction. Mỗi item được xử lý độc lập và một số item có thể thành công trong khi item khác thất bại. Vì vậy, ứng dụng phải kiểm tra kết quả từng item.

## 2. Bulk API hoạt động như thế nào?

Elasticsearch Bulk API dùng định dạng NDJSON (Newline Delimited JSON). Mỗi thao tác gồm một dòng metadata/action và có thể có thêm một dòng source hoặc payload.

Ví dụ index hai document:

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "index": { "_id": "P-100" } }
{ "name": "Mechanical Keyboard", "price": 2500000 }
{ "index": { "_id": "P-101" } }
{ "name": "Wireless Mouse", "price": 450000 }
```

Các action phổ biến:

| Action | Dòng tiếp theo | Ý nghĩa |
|---|---|---|
| `index` | Source document | Tạo hoặc thay thế document theo ID. |
| `create` | Source document | Chỉ tạo mới; lỗi nếu ID đã tồn tại. |
| `update` | Update payload | Cập nhật một phần hoặc chạy script/upsert. |
| `delete` | Không có | Xóa document theo ID. |

Ví dụ update và delete:

```http
POST /products/_bulk
Content-Type: application/x-ndjson

{ "update": { "_id": "P-100" } }
{ "doc": { "price": 2600000 } }
{ "delete": { "_id": "P-101" } }
```

Bulk request kết thúc bằng newline. Nếu tự tạo NDJSON, thiếu newline cuối có thể làm request không hợp lệ. Khi dùng Spring Data, thư viện tạo payload thay cho ứng dụng.

### 2.1. Bulk response không phải một kết quả all-or-nothing

Response bulk có thể có `errors: true` dù HTTP request tổng thể đã được Elasticsearch xử lý. Mỗi phần tử trong `items` có status và kết quả riêng:

```json
{
  "took": 42,
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

Trong ví dụ, `P-100` đã được index thành công, còn `P-101` lỗi mapping. Không được coi toàn bộ batch thất bại và gửi lại tất cả item một cách mù quáng.

## 3. Dùng `ElasticsearchOperations.bulkIndex`

Spring Data Elasticsearch cung cấp `ElasticsearchOperations` để thực hiện bulk mà không cần tự tạo NDJSON. Với các API Spring Data Elasticsearch 5.x, có thể tạo `IndexQuery` cho mỗi entity rồi gửi danh sách bằng `bulkIndex`.

Ví dụ entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Double)
    private double price;

    // constructors, getters, setters
}
```

Tạo `IndexQuery` và bulk index:

```java
import java.util.List;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;

public class ProductBulkIndexer {

    private final ElasticsearchOperations operations;

    public ProductBulkIndexer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void indexBatch(List<ProductDocument> products) {
        List<IndexQuery> queries = products.stream()
                .map(product -> new IndexQueryBuilder()
                        .withId(product.getId())
                        .withObject(product)
                        .build())
                .toList();

        operations.bulkIndex(queries, ProductDocument.class);
    }
}
```

`IndexQueryBuilder` cho phép gắn ID và object cần index. `bulkIndex` gửi danh sách thao tác trong một bulk request. Nếu ID đã tồn tại, action index sẽ thay thế document hiện tại theo semantics của Elasticsearch index operation.

Nếu muốn từ chối ID đã tồn tại, cần chọn create semantics phù hợp với API/version đang dùng. Đừng giả định `bulkIndex` mặc định tương đương `create`.

### 3.1. Chọn đúng thao tác bulk

Spring Data Elasticsearch có các phương thức bulk theo mục đích:

| Phương thức | Mục đích |
|---|---|
| `bulkIndex(...)` | Index hoặc thay thế nhiều document. |
| `bulkUpdate(...)` | Gửi nhiều `UpdateQuery` để cập nhật document. |
| `bulkDelete(...)` | Xóa nhiều document theo ID/query tương ứng API. |

Nên chọn thao tác theo semantics nghiệp vụ. Nếu cần thay toàn bộ document, dùng index. Nếu chỉ cập nhật một số field và giữ lại các field khác, dùng update với partial document. Nếu cần tạo mới và lỗi khi trùng ID, dùng create operation qua API phù hợp.

## 4. Chia dữ liệu thành batch có giới hạn

Không nên tạo một `List` chứa toàn bộ dataset rồi gọi bulk một lần:

```java
// Không phù hợp với dữ liệu rất lớn.
List<ProductDocument> allProducts = loadAllProducts();
indexer.indexBatch(allProducts);
```

Nếu mỗi document chiếm trung bình 5 KB, 500.000 document có thể tương đương khoảng 2,5 GB dữ liệu source trước khi tính overhead object Java, String, collection, mapping metadata và payload serialization. Bộ nhớ thực tế có thể lớn hơn đáng kể.

Thay vào đó, đọc tuần tự và chỉ giữ một batch trong heap:

```java
int batchSize = 500;
List<IndexQuery> batch = new ArrayList<>(batchSize);

for (ProductDocument product : source) {
    batch.add(new IndexQueryBuilder()
            .withId(product.getId())
            .withObject(product)
            .build());

    if (batch.size() >= batchSize) {
        operations.bulkIndex(batch, ProductDocument.class);
        batch.clear();
    }
}

if (!batch.isEmpty()) {
    operations.bulkIndex(batch, ProductDocument.class);
    batch.clear();
}
```

Batch được gửi ngay khi đủ kích thước. Sau khi request hoàn tất, `clear()` bỏ tham chiếu đến các `IndexQuery` trong danh sách để garbage collector có thể thu hồi object nếu không còn tham chiếu nào khác.

### 4.1. Đừng chỉ dựa vào số lượng document

Batch 500 document có thể nhỏ nếu mỗi document chỉ có vài field, nhưng rất lớn nếu mỗi document chứa nội dung HTML, mảng nested dài hoặc trường text lớn.

Nên giới hạn cả:

- **Document count:** số document tối đa trong batch.
- **Estimated bytes:** tổng kích thước payload ước lượng.
- **Processing time:** thời gian xử lý một batch.

Ví dụ ban đầu có thể đặt giới hạn 500 document hoặc 5–10 MB payload, tùy workload; đây chỉ là điểm xuất phát để benchmark, không phải ngưỡng chung cho mọi cluster. Nếu document rất lớn, giảm số lượng item trong batch.

Elasticsearch khuyến nghị benchmark để tìm kích thước bulk tối ưu. Tăng batch đến khi throughput không còn cải thiện đáng kể hoặc bắt đầu thấy memory pressure, latency tăng và lỗi 429 thì dừng ở mức ổn định trước đó.

### 4.2. Dùng byte threshold

Nếu ứng dụng có thể ước lượng kích thước source trước khi serialize, có thể flush khi vượt giới hạn byte:

```java
int maxDocuments = 500;
long maxEstimatedBytes = 8L * 1024 * 1024;

List<IndexQuery> batch = new ArrayList<>(maxDocuments);
long estimatedBytes = 0;

for (ProductDocument product : source) {
    IndexQuery query = new IndexQueryBuilder()
            .withId(product.getId())
            .withObject(product)
            .build();

    long documentBytes = estimatePayloadBytes(product);
    boolean batchFull = batch.size() >= maxDocuments;
    boolean bytesFull = !batch.isEmpty()
            && estimatedBytes + documentBytes > maxEstimatedBytes;

    if (batchFull || bytesFull) {
        operations.bulkIndex(batch, ProductDocument.class);
        batch.clear();
        estimatedBytes = 0;
    }

    batch.add(query);
    estimatedBytes += documentBytes;
}

if (!batch.isEmpty()) {
    operations.bulkIndex(batch, ProductDocument.class);
}
```

`estimatePayloadBytes` là hàm ứng dụng tự triển khai dựa trên kích thước JSON/UTF-8 ước lượng. Kích thước object trong heap không giống kích thước JSON gửi qua mạng. Nếu cần giới hạn chính xác payload, phải đo sau serialization hoặc dùng bulk client có khả năng quản lý byte threshold.

Nếu một document riêng lẻ đã lớn hơn ngưỡng, vẫn cần quyết định xử lý nó riêng, từ chối hoặc ghi qua một luồng chuyên biệt. Không để batch rỗng lặp vô hạn vì document lớn không thể vừa giới hạn.

## 5. Đọc nguồn dữ liệu theo kiểu streaming

Chia batch ở phía Elasticsearch chưa đủ nếu ứng dụng đã tải toàn bộ dữ liệu nguồn vào heap. Nguồn cũng phải được đọc theo từng phần.

Các cách thường dùng:

- JDBC cursor/stream với fetch size phù hợp.
- Spring Data repository trả `Stream<T>` và được đóng đúng cách.
- Phân trang theo keyset hoặc ID tăng dần.
- Đọc file CSV/JSON từng dòng hoặc từng record.
- Consumer nhận message theo batch từ queue.
- API nguồn có cursor hoặc continuation token.

Ví dụ dùng stream từ repository:

```java
try (Stream<SourceProduct> products = sourceRepository.streamAllProducts()) {
    // Consume incrementally and close the stream when finished.
}
```

Với JDBC, stream thường cần transaction và cấu hình fetch size phụ thuộc driver. Nếu driver mặc định tải toàn bộ result set vào client, việc trả về Java `Stream` không tự bảo đảm dữ liệu được đọc từng record.

### 5.1. Kết hợp source stream và bulk batch

Ví dụ một import service đọc source stream và flush từng batch:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;

public class ProductImportService {

    private static final int BATCH_SIZE = 500;

    private final SourceProductRepository sourceRepository;
    private final ElasticsearchOperations operations;

    public ProductImportService(
            SourceProductRepository sourceRepository,
            ElasticsearchOperations operations) {
        this.sourceRepository = sourceRepository;
        this.operations = operations;
    }

    public void importAll() {
        List<IndexQuery> batch = new ArrayList<>(BATCH_SIZE);

        try (Stream<SourceProduct> source = sourceRepository.streamAllProducts()) {
            source.forEach(sourceProduct -> {
                ProductDocument document = map(sourceProduct);

                batch.add(new IndexQueryBuilder()
                        .withId(document.getId())
                        .withObject(document)
                        .build());

                if (batch.size() >= BATCH_SIZE) {
                    operations.bulkIndex(batch, ProductDocument.class);
                    batch.clear();
                }
            });
        }

        if (!batch.isEmpty()) {
            operations.bulkIndex(batch, ProductDocument.class);
            batch.clear();
        }
    }

    private ProductDocument map(SourceProduct source) {
        // Map source fields to the Elasticsearch document.
        throw new UnsupportedOperationException("Example only");
    }
}
```

Ví dụ minh họa luồng dữ liệu, không phải một implementation hoàn chỉnh cho mọi repository. Trong code production, cần bảo đảm source stream được đọc bằng cursor/fetch size thực sự và tránh giữ entity nguồn sau khi đã map.

`Stream.forEach` là thao tác tuần tự trong ví dụ. Không thêm `.parallel()` một cách tùy tiện vì nó có thể tạo nhiều object cùng lúc, cạnh tranh trên batch list và làm mất kiểm soát concurrency/memory. Nếu cần parallel mapping, hãy dùng bounded queue và consumer có giới hạn.

### 5.2. Keyset pagination khi nguồn không hỗ trợ stream

Nếu nguồn hỗ trợ truy vấn theo ID tăng dần, có thể đọc từng trang bằng keyset:

```sql
SELECT id, name, price
FROM source_products
WHERE id > :lastSeenId
ORDER BY id
LIMIT :pageSize;
```

Sau khi batch được index thành công, cập nhật `lastSeenId` bằng ID cuối cùng của batch. Cách này tránh offset pagination sâu ở database và cho phép tiếp tục từ checkpoint.

Nếu ID không phản ánh thứ tự cập nhật, hoặc bản ghi cũ có thể thay đổi trong lúc import, cần watermark theo version/updated timestamp hoặc CDC. Không coi `id > lastSeenId` là cách bảo đảm đồng bộ mọi thay đổi.

## 6. Kiểm soát bộ nhớ ở phía ứng dụng

Một import job có thể dùng nhiều bộ nhớ ở nhiều tầng:

```text
Source database / file / queue
           |
           v
  Source objects in heap
           |
           v
   Mapping / transformation
           |
           v
      Batch buffer
           |
           v
 JSON serialization buffer
           |
           v
 HTTP request / response
           |
           v
 Bulk response metadata
```

Nếu mỗi tầng đều giữ bản sao dữ liệu, peak heap có thể cao hơn nhiều so với kích thước source. Các nguyên tắc sau giúp giới hạn memory:

- Đọc nguồn từng trang hoặc từng record.
- Chỉ giữ một hoặc một số ít batch đang xử lý.
- Dùng batch list có capacity hữu hạn.
- Sau khi flush, clear buffer và không giữ reference đến entity cũ.
- Không tích lũy toàn bộ bulk response trong một collection lớn.
- Không chuyển stream thành `List` cho dataset lớn.
- Giới hạn số request async đang chạy đồng thời.
- Giới hạn queue giữa producer và consumer.
- Không giữ toàn bộ exception/source payload trong log hoặc dead-letter list ở heap.
- Theo dõi heap, allocation rate, GC pause và direct buffer.

### 6.1. Tránh `findAll()` cho import lớn

Ví dụ không phù hợp:

```java
List<SourceProduct> products = sourceRepository.findAll();
List<ProductDocument> documents = products.stream()
        .map(this::map)
        .toList();

operations.save(documents);
```

Đoạn code giữ ít nhất hai danh sách lớn cùng lúc: entity nguồn và document đích. Nếu serialization tạo thêm buffer, peak memory còn tăng hơn.

Thay bằng streaming và batch:

```java
try (Stream<SourceProduct> products = sourceRepository.streamAllProducts()) {
    Iterator<SourceProduct> iterator = products.iterator();
    List<IndexQuery> batch = new ArrayList<>(500);

    while (iterator.hasNext()) {
        SourceProduct source = iterator.next();
        ProductDocument document = map(source);

        batch.add(new IndexQueryBuilder()
                .withId(document.getId())
                .withObject(document)
                .build());

        if (batch.size() == 500) {
            operations.bulkIndex(batch, ProductDocument.class);
            batch.clear();
        }
    }

    if (!batch.isEmpty()) {
        operations.bulkIndex(batch, ProductDocument.class);
    }
}
```

### 6.2. Đừng giữ payload chỉ để retry toàn batch

Nếu batch thất bại, giữ lại toàn bộ object graph trong một danh sách retry vô hạn có thể làm heap tăng không giới hạn. Thay vào đó:

- Chỉ giữ các item lỗi có thể retry trong một buffer giới hạn.
- Giới hạn số lần retry và thời gian retry.
- Ghi lỗi không retry được vào dead-letter store/file/queue bền vững.
- Nếu batch quá lớn, chia nhỏ tập lỗi trước khi gửi lại.
- Không lưu source JSON khổng lồ trong log; ghi ID, status, error type và reference đến payload nếu cần.

### 6.3. Heap không phải nơi duy nhất tiêu thụ bộ nhớ

HTTP client có thể dùng direct buffer ngoài heap; TLS, compression, serialization và response body cũng tiêu thụ bộ nhớ. Vì vậy, chỉ xem `-Xmx` không đủ để đánh giá toàn bộ memory footprint.

Theo dõi thêm:

- Heap used/committed và old-generation occupancy.
- Allocation rate và GC pause.
- Direct/mapped buffer pool.
- Số connection đang mở và request đang chờ.
- Kích thước queue/batch.
- Container memory limit và RSS.

## 7. Concurrency và backpressure

Tăng số bulk request chạy đồng thời có thể tăng throughput đến một mức nhất định. Sau đó, cluster có thể bị quá tải, request latency tăng, thread pool write/bulk queue đầy và Elasticsearch trả về lỗi 429.

Không nên tạo một future cho mọi batch của toàn bộ dataset:

```java
// Không phù hợp: số lượng task/future tăng theo tổng số batch.
List<CompletableFuture<?>> futures = allBatches.stream()
        .map(this::sendAsync)
        .toList();
```

Với dữ liệu lớn, danh sách future có thể tăng không giới hạn. Thay vào đó, giới hạn số batch đang chạy và chỉ đọc/submit batch mới khi có capacity.

### 7.1. Mô hình producer-consumer có bounded queue

```text
Source reader
     |
     v
Bounded queue (ví dụ tối đa 4 batch)
     |
     +--------+--------+
     |        |        |
     v        v        v
 Worker 1  Worker 2  Worker 3
     |        |        |
     +--------+--------+
              |
              v
       Elasticsearch
```

Khi queue đầy, producer phải chờ hoặc giảm tốc độ đọc. Đây là backpressure: tốc độ đọc nguồn được điều chỉnh theo khả năng xử lý của Elasticsearch.

Ví dụ dùng `BlockingQueue`:

```java
BlockingQueue<List<IndexQuery>> queue = new ArrayBlockingQueue<>(4);
```

Producer chỉ có thể đưa tối đa bốn batch chưa xử lý vào queue. Nếu consumer chậm, `put()` sẽ chờ thay vì tiếp tục tạo thêm batch.

Trong ứng dụng thực tế, cần xử lý cả tín hiệu kết thúc, exception từ worker, cancellation và đóng queue. Không dùng queue không giới hạn như `LinkedBlockingQueue` mặc định cho một import không có giới hạn đầu vào.

### 7.2. Chọn concurrency từ số đo

Bắt đầu với một worker và batch size vừa phải. Đo throughput, latency và tài nguyên. Sau đó tăng concurrency từng bước, ví dụ 1 → 2 → 4, quan sát điểm mà throughput không còn cải thiện hoặc 429/latency tăng mạnh.

Không có công thức chung kiểu “mỗi shard một worker” cho mọi workload. Một bulk request có thể fan-out đến nhiều shard; document routing, kích thước payload và loại analyzer đều ảnh hưởng. Chọn concurrency dựa trên benchmark và khả năng cluster.

## 8. Xử lý lỗi bulk theo từng item

Bulk API có thể thành công một phần. Ứng dụng cần phân loại lỗi thay vì retry toàn bộ request.

Một số nhóm lỗi:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Dữ liệu không hợp lệ | Mapping parse error, sai kiểu field, document quá lớn. | Không retry nguyên trạng; sửa dữ liệu hoặc đưa vào dead-letter. |
| Xung đột nghiệp vụ | `version_conflict_engine_exception`, ID đã tồn tại với create. | Xử lý theo chính sách version/upsert hoặc bỏ qua nếu đã được xử lý. |
| Quá tải tạm thời | HTTP 429, rejection. | Retry item lỗi với backoff và giới hạn concurrency. |
| Lỗi tạm thời hạ tầng | Timeout, connection reset, 502/503/504. | Xác định trạng thái item; retry có kiểm soát, bảo đảm thao tác idempotent. |
| Lỗi cấu hình/quyền | Index không tồn tại, unauthorized/forbidden. | Dừng job và sửa cấu hình/quyền; không retry liên tục. |

### 8.1. Chỉ retry item lỗi

Giả sử bulk gồm 500 item, trong đó 490 thành công, 5 bị 429 và 5 lỗi mapping. Chiến lược hợp lý:

- Ghi nhận 490 item thành công.
- Đưa 5 item 429 vào retry queue có giới hạn.
- Ghi 5 item lỗi mapping vào dead-letter để điều tra.
- Không gửi lại 490 item thành công chỉ vì response có `errors: true`.

Nếu API Spring Data đang dùng ném exception chứa danh sách failed documents/errors, hãy lấy danh sách đó để phân loại. Với Elasticsearch Java API Client mức thấp, kiểm tra `BulkResponse.errors()` và từng `BulkResponseItem` trong response. Kiểu exception và cấu trúc response cụ thể phụ thuộc phiên bản client.

### 8.2. Exponential backoff và jitter

Khi Elasticsearch trả 429 do quá tải, retry ngay lập tức có thể làm tải tăng thêm. Dùng exponential backoff:

```text
attempt 1: wait ~200 ms
attempt 2: wait ~400 ms
attempt 3: wait ~800 ms
attempt 4: wait ~1600 ms
...
```

Thêm jitter ngẫu nhiên để nhiều worker không retry cùng thời điểm. Cần đặt:

- Số lần retry tối đa.
- Thời gian chờ tối đa.
- Tổng thời gian job có thể dành cho retry.
- Danh sách status/error type được retry.
- Cơ chế giảm concurrency khi 429 tăng.

Các con số trên chỉ minh họa. Giá trị thực tế cần dựa trên latency và chính sách vận hành.

### 8.3. Không retry lỗi mapping vô hạn

Một lỗi parse field do gửi chuỗi vào field numeric sẽ không tự hết khi gửi lại sau một giây. Retry lỗi không thể phục hồi làm tiêu tốn băng thông, heap và năng lực cluster. Chuyển lỗi dữ liệu sang dead-letter với ID, source version, error type và lý do.

## 9. Idempotency khi retry

Retry an toàn phụ thuộc loại thao tác:

- Index document bằng ID ổn định với toàn bộ source thường có thể retry theo kiểu ghi đè cùng trạng thái.
- Create document có thể trả conflict nếu lần gửi trước đã thành công nhưng response bị mất.
- Partial update cộng dồn (ví dụ tăng counter) có thể không idempotent; retry có thể áp dụng hai lần.
- Script update cần được thiết kế để nhận diện version/event ID hoặc có semantics idempotent.
- Delete cùng ID thường có thể retry theo chính sách chấp nhận document đã không còn tồn tại.

Ví dụ dùng deterministic ID:

```java
IndexQuery query = new IndexQueryBuilder()
        .withId(sourceProduct.getBusinessId())
        .withObject(document)
        .build();
```

Nếu cùng một source record luôn tạo cùng `_id`, gửi lại cùng index operation sẽ không tạo document trùng. Nếu ID được sinh ngẫu nhiên mỗi lần retry, cùng một bản ghi có thể xuất hiện thành nhiều document.

Với event stream, có thể lưu event ID hoặc source version để tránh áp dụng lại một event cũ. Nếu dữ liệu có thể đến sai thứ tự, cần kiểm tra version/timestamp trước khi ghi để phiên bản cũ không ghi đè phiên bản mới.

## 10. Checkpoint và khả năng tiếp tục import

Import lớn có thể chạy nhiều phút hoặc nhiều giờ. Nếu process dừng ở batch 700, ứng dụng cần biết batch nào đã được ghi thành công để tiếp tục.

Checkpoint thường chứa:

- Import job ID và source dataset/version.
- Last source key hoặc cursor đã xử lý.
- Số batch đã gửi/thành công/thất bại.
- Thời điểm bắt đầu/cập nhật.
- Index/alias đích và mapping version.
- Trạng thái hoàn tất hoặc cần xử lý lại.

Quy tắc quan trọng: chỉ cập nhật checkpoint sau khi batch đã được Elasticsearch xác nhận thành công theo chính sách của job. Nếu batch có một số item thất bại, checkpoint không nên bỏ qua các item đó trừ khi chúng đã được ghi vào durable retry/dead-letter store.

```text
Read source batch
       |
       v
Bulk index batch
       |
       v
Inspect every item
       |
       +---- retryable errors? ----> persist retry work
       |
       +---- permanent errors? ---> persist dead-letter
       |
       v
All items accounted for
       |
       v
Commit source checkpoint
```

Nếu ứng dụng ghi checkpoint trước khi bulk hoàn tất, process có thể chết sau checkpoint và bỏ qua các document chưa được index. Nếu ghi checkpoint sau khi bulk thành công nhưng process chết trước khi checkpoint được lưu, batch có thể được gửi lại; deterministic ID/idempotent sink giúp retry an toàn.

## 11. Refresh policy trong lúc bulk import

Elasticsearch là near real-time. Document được index thành công chưa chắc lập tức xuất hiện trong search; chúng trở nên searchable sau refresh.

Trong một đợt bulk lớn, refresh quá thường xuyên có thể làm giảm throughput vì tạo nhiều segment nhỏ và tăng công việc merge. Nếu ứng dụng không cần đọc ngay các document vừa import, hãy tránh refresh sau từng batch.

Các lựa chọn refresh thường gặp:

| Chính sách | Ý nghĩa |
|---|---|
| `NONE` / không yêu cầu refresh | Ghi nhanh; document sẽ searchable theo chu kỳ refresh tự nhiên hoặc refresh thủ công. |
| `IMMEDIATE` / `true` | Yêu cầu refresh ngay sau request; có thể giảm throughput nếu dùng cho từng batch. |
| `WAIT_UNTIL` / `wait_for` | Chờ lần refresh tiếp theo làm document searchable. |

Tên enum và cách cấu hình trong Spring Data phụ thuộc phiên bản. Với import lớn, thường gửi bulk với refresh policy không yêu cầu refresh từng request, sau đó refresh một lần khi cần công bố dữ liệu.

Ví dụ REST:

```http
POST /products/_bulk?refresh=false
Content-Type: application/x-ndjson

{ "index": { "_id": "P-100" } }
{ "name": "Mechanical Keyboard", "price": 2500000 }
```

Sau khi import hoàn tất:

```http
POST /products/_refresh
```

Không refresh sau từng batch nếu không có yêu cầu đọc ngay. Nếu import chạy liên tục và người dùng cần nhìn thấy dữ liệu mới trong một SLA cụ thể, hãy thiết kế refresh interval và visibility policy phù hợp thay vì refresh cưỡng bức mọi request.

## 12. Replica và active shard khi nhập dữ liệu

Replica giúp tăng khả năng chịu lỗi và phục vụ search, nhưng trong lúc import lớn, mỗi lần index document cũng cần cập nhật replica shard. Điều này có thể ảnh hưởng throughput.

Một số hệ thống thực hiện quy trình nhập liệu theo đợt trên index mới:

1. Tạo index mới với mapping/settings đúng.
2. Trong thời gian bulk import, cân nhắc cấu hình replica phù hợp với yêu cầu availability.
3. Nạp dữ liệu và xử lý lỗi.
4. Chờ shard hoạt động theo chính sách yêu cầu.
5. Khôi phục replica settings cần thiết.
6. Refresh và kiểm tra dữ liệu.
7. Chuyển alias sang index mới.

Không tự động đặt replicas về 0 trên production nếu chưa đánh giá rủi ro availability. Nếu node gặp sự cố trong lúc replica bằng 0, index có thể mất khả năng phục vụ hoặc dữ liệu chưa được bảo vệ theo mức mong muốn.

`wait_for_active_shards` kiểm soát số shard copy cần active trước khi thao tác được thực hiện. Đây là lựa chọn về availability/acknowledgement, không thay thế retry item và không bảo đảm mọi item trong bulk thành công.

## 13. Sử dụng `BulkOptions`

Spring Data Elasticsearch cung cấp `BulkOptions` để cấu hình một số tùy chọn cho bulk request, ví dụ refresh policy, timeout và số shard copy cần active. Cách tạo options và overload `bulkIndex` phụ thuộc phiên bản Spring Data Elasticsearch.

Ví dụ khái quát:

```java
import org.springframework.data.elasticsearch.core.BulkOptions;
import org.springframework.data.elasticsearch.core.RefreshPolicy;

BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.NONE)
        .build();

operations.bulkIndex(indexQueries, options, ProductDocument.class);
```

Ở đây `RefreshPolicy.NONE` thể hiện không yêu cầu refresh sau bulk request. Khi kết thúc import, service có thể gọi refresh qua `IndexOperations` nếu cần công bố dữ liệu ngay.

Hãy đối chiếu package, builder method và overload với đúng phiên bản dependency đang dùng. Không phải mọi version đều có cùng API hoặc tên enum.

## 14. Import theo chiến lược reindex/alias

Với import lớn cần hạn chế ảnh hưởng người dùng, có thể tạo index mới rồi chuyển alias sau khi hoàn tất:

```text
Alias products-read
       |
       v
Index products-v1 (đang phục vụ)

Tạo products-v2
       |
       v
Bulk import vào products-v2
       |
       v
Validate count / sample / errors
       |
       v
Atomic alias switch
       |
       v
Alias products-read -> products-v2
```

Ví dụ tạo index mới:

```http
PUT /products-v2
{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1
  },
  "mappings": {
    "properties": {
      "name": { "type": "text" },
      "price": { "type": "double" },
      "category": { "type": "keyword" }
    }
  }
}
```

Sau khi import và xác minh, chuyển alias trong một `_aliases` request:

```http
POST /_aliases
{
  "actions": [
    { "remove": { "index": "products-v1", "alias": "products-read" } },
    { "add": { "index": "products-v2", "alias": "products-read" } }
  ]
}
```

Alias switch trong một request giúp đổi đích alias nguyên tử ở cấp cluster state. Nếu nguồn vẫn tiếp tục nhận ghi trong khi import, cần cơ chế dual-write hoặc delta/CDC để không mất cập nhật giữa snapshot và thời điểm switch.

## 15. Theo dõi tiến độ và throughput

Một import job nên ghi nhận metric ở cấp batch thay vì chỉ log “đã bắt đầu” và “đã hoàn tất”.

Các chỉ số hữu ích:

| Metric | Ý nghĩa |
|---|---|
| `documents_read_total` | Số document đã đọc từ nguồn. |
| `documents_indexed_total` | Số item được xác nhận thành công. |
| `documents_failed_total` | Số item thất bại. |
| `bulk_requests_total` | Số bulk request đã gửi. |
| `bulk_batch_documents` | Số item trong từng batch. |
| `bulk_payload_bytes` | Kích thước payload ước lượng/thực tế. |
| `bulk_request_duration` | Thời gian xử lý một bulk request. |
| `bulk_retry_total` | Số item/request đã retry. |
| `queue_depth` | Số batch đang chờ xử lý. |
| `heap_used` / `gc_pause` | Tình trạng bộ nhớ và GC. |
| `http_429_total` | Số lỗi rejection/quá tải. |

Có thể tính throughput:

\[
Throughput = \frac{\text{documents indexed successfully}}{\text{elapsed seconds}}
\]

Theo dõi p50/p95/p99 latency của bulk request. Nếu batch size tăng mà throughput không tăng, trong khi latency và memory tăng, cần quay về kích thước nhỏ hơn.

Log theo batch nên chứa job ID, batch sequence, count, duration, success/failure count và checkpoint. Tránh log toàn bộ source document hoặc payload vì có thể gây lộ dữ liệu và làm log storage tăng mạnh.

## 16. Tối ưu mapping và dữ liệu trước khi import

Bulk throughput còn phụ thuộc cách document được index:

- Chỉ khai báo field cần thiết; tránh mapping explosion từ dynamic field không kiểm soát.
- Chọn đúng kiểu `keyword`, `text`, numeric, date, geo hoặc nested.
- Không tạo quá nhiều nested object nếu không cần.
- Chuẩn hóa dữ liệu trước khi gửi để tránh mapping parse error.
- Dùng deterministic ID để hỗ trợ retry và upsert.
- Tránh gửi field null/rỗng không cần thiết nếu source lớn.
- Cân nhắc ingest pipeline nếu cần xử lý tập trung; đo chi phí pipeline.
- Tránh chạy aggregation/search nặng trên cùng index trong giai đoạn import cao điểm nếu có thể.

Không nên tắt mapping hoặc analyzer chỉ để tăng tốc rồi quên khôi phục. Nếu cần index mới phục vụ import, hãy thiết kế mapping chính xác từ đầu và xác minh query sau import.

## 17. Bulk update và bulk delete

Không phải mọi import đều tạo document mới. Một số job cần cập nhật hoặc xóa nhiều document.

### 17.1. Bulk update

Ví dụ cập nhật giá sản phẩm:

```java
import org.springframework.data.elasticsearch.core.query.UpdateQuery;
import org.springframework.data.elasticsearch.core.query.UpdateQueryBuilder;

List<UpdateQuery> updates = new ArrayList<>();

for (PriceChange change : changes) {
    UpdateQuery update = UpdateQuery.builder(change.productId())
            .withDocument(Document.create().append("price", change.newPrice()))
            .build();
    updates.add(update);
}

operations.bulkUpdate(updates, ProductDocument.class);
```

Đoạn code minh họa partial update; API builder của `UpdateQuery` và `Document` cần đối chiếu phiên bản Spring Data đang dùng. Partial update giữ các field khác không có trong payload. Nếu cần upsert khi document chưa tồn tại, phải cấu hình upsert semantics rõ ràng.

### 17.2. Bulk delete

Nếu có danh sách ID cần xóa, có thể dùng bulk delete:

```java
List<String> ids = expiredProducts.stream()
        .map(ExpiredProduct::id)
        .toList();

operations.bulkDelete(ids, ProductDocument.class);
```

Với danh sách lớn, cũng cần chia ID thành batch. Không tạo một list chứa hàng triệu ID nếu có thể stream từ nguồn.

Nếu cần xóa theo điều kiện query trên nhiều document, cân nhắc Delete By Query API. API này có semantics, throttling, slicing và conflict handling riêng; không đồng nghĩa với một bulk delete theo danh sách ID.

## 18. Phân biệt Bulk API với Reindex API

Hai API đều xử lý nhiều document nhưng có mục đích khác nhau:

| Bulk API | Reindex API |
|---|---|
| Client gửi các action index/create/update/delete. | Elasticsearch đọc document từ source index và ghi sang destination index. |
| Phù hợp khi nguồn dữ liệu ở database, file, queue hoặc ứng dụng. | Phù hợp khi sao chép/chuyển đổi dữ liệu giữa index Elasticsearch. |
| Ứng dụng chịu trách nhiệm đọc nguồn, batch và retry. | Elasticsearch quản lý quá trình scan/reindex theo request. |
| Có thể gửi nhiều loại action trong cùng request. | Có thể dùng script và query để lọc/chuyển đổi trong quá trình reindex. |

Nếu dữ liệu nguồn nằm ngoài Elasticsearch, Bulk API thường là lựa chọn phù hợp. Nếu mục tiêu là chuyển dữ liệu từ index cũ sang index mới, Reindex API có thể đơn giản hơn; vẫn cần kiểm soát slicing, throttling, conflicts và dung lượng đích.

## 19. Quy trình import lớn hoàn chỉnh

Một quy trình an toàn có thể triển khai theo các bước:

1. **Chuẩn bị index:** tạo index/alias và mapping đúng trước khi nạp.
2. **Xác định source snapshot:** ghi lại mốc dữ liệu hoặc version của nguồn.
3. **Mở source cursor:** dùng stream/fetch size/keyset pagination để đọc tuần tự.
4. **Map document:** chuyển dữ liệu nguồn thành entity Elasticsearch với ID ổn định.
5. **Tạo batch có giới hạn:** giới hạn count và estimated bytes.
6. **Gửi bulk:** dùng `bulkIndex`, `bulkUpdate` hoặc `bulkDelete`.
7. **Phân loại response:** kiểm tra từng item, tách success/retry/dead-letter.
8. **Retry có backoff:** chỉ retry item có lỗi tạm thời và có semantics idempotent.
9. **Checkpoint:** lưu tiến độ sau khi mọi item của batch đã được xử lý hoặc lưu bền vững vào retry/dead-letter.
10. **Điều chỉnh tải:** theo dõi 429, latency, heap, queue depth và giảm concurrency khi cần.
11. **Hoàn tất visibility:** refresh khi cần và kiểm tra dữ liệu trên index.
12. **Công bố:** chuyển alias hoặc đánh dấu job hoàn tất sau khi xác minh.
13. **Đối soát:** so sánh số lượng nguồn/đích, lỗi, sample document và các metric nghiệp vụ.

## 20. Ví dụ skeleton import có checkpoint

Ví dụ dưới đây thể hiện cách tổ chức batch và checkpoint. Các interface source/checkpoint/dead-letter là abstraction của ứng dụng, cần triển khai theo database hoặc queue thực tế.

```java
public class ImportJob {

    private static final int BATCH_SIZE = 500;

    private final SourceProductRepository source;
    private final ElasticsearchOperations operations;
    private final ImportCheckpointStore checkpoints;
    private final DeadLetterStore deadLetters;

    public void run(String jobId) {
        String lastId = checkpoints.loadLastId(jobId);
        List<IndexQuery> batch = new ArrayList<>(BATCH_SIZE);
        String lastIdInBatch = lastId;

        try (Stream<SourceProduct> rows = source.streamAfter(lastId)) {
            Iterator<SourceProduct> iterator = rows.iterator();

            while (iterator.hasNext()) {
                SourceProduct row = iterator.next();
                ProductDocument document = map(row);

                batch.add(new IndexQueryBuilder()
                        .withId(document.getId())
                        .withObject(document)
                        .build());
                lastIdInBatch = row.id();

                if (batch.size() >= BATCH_SIZE) {
                    sendAndAccount(batch, jobId);
                    checkpoints.saveLastId(jobId, lastIdInBatch);
                    batch.clear();
                }
            }
        }

        if (!batch.isEmpty()) {
            sendAndAccount(batch, jobId);
            checkpoints.saveLastId(jobId, lastIdInBatch);
            batch.clear();
        }
    }

    private void sendAndAccount(List<IndexQuery> batch, String jobId) {
        // Send the batch, inspect item-level outcomes, persist retryable
        // and permanent failures, and return only when every item is accounted for.
    }
}
```

Điểm quan trọng là `sendAndAccount` phải bảo đảm mỗi item được phân loại trước khi checkpoint được commit. Nếu chỉ gửi bulk rồi bỏ qua response, checkpoint có thể tiến qua các document bị lỗi và import sẽ không bao giờ thử lại chúng.

Skeleton dùng `lastId` làm keyset checkpoint. Nếu source có thể cập nhật các ID cũ trong lúc job chạy, cần thêm source version, watermark hoặc change log để bảo đảm không bỏ sót thay đổi.

## 21. Kiểm thử và vận hành import

Nên kiểm thử trên Elasticsearch thật hoặc Testcontainers với version tương thích. Mock `ElasticsearchOperations` phù hợp để kiểm tra service tạo batch, nhưng không xác nhận được Bulk API, mapping, partial failures hoặc throughput.

Các tình huống nên có:

- Import ít hơn một batch.
- Import đúng bằng batch size.
- Import nhiều batch và batch cuối không đủ kích thước.
- Một document có mapping error giữa batch hợp lệ.
- Bulk response có 429 và retry thành công.
- Bulk request timeout sau khi Elasticsearch có thể đã xử lý một phần.
- Process dừng sau khi bulk thành công nhưng trước checkpoint.
- Process dừng sau khi checkpoint được ghi.
- Source stream ném exception và được đóng đúng cách.
- Queue đầy và producer bị backpressure.
- Index không tồn tại hoặc user thiếu quyền.
- Refresh sau import và search thấy dữ liệu.

Khi benchmark:

1. Dùng dữ liệu có kích thước và phân bố field gần production.
2. Cố định số shard, replica, mapping và analyzer.
3. Thử nhiều batch size và concurrency.
4. Đo docs/second, p95 bulk latency, 429, heap và GC.
5. Lặp lại đủ lần để giảm ảnh hưởng cache và tải nền.
6. Chọn cấu hình ổn định, không chỉ cấu hình có throughput đỉnh trong một lần chạy.

## 22. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Heap tăng liên tục khi import | Dùng `findAll()`, tích lũy toàn bộ batch/future/response hoặc retry list không giới hạn. | Stream nguồn, bounded batch/queue, clear reference và giới hạn retry. |
| Bulk request quá chậm | Batch quá lớn, document nặng, shard/node quá tải hoặc concurrency không phù hợp. | Đo payload/latency, giảm batch/concurrency và tối ưu mapping. |
| Quá nhiều request nhỏ | Batch size quá thấp hoặc flush theo từng document. | Tăng batch dần và benchmark. |
| Bulk response có lỗi nhưng job báo thành công | Chỉ kiểm tra HTTP status, không đọc item-level errors. | Kiểm tra `errors` và từng item trong response. |
| Retry làm nhân đôi dữ liệu | ID mới được sinh mỗi lần hoặc update không idempotent. | Dùng deterministic ID, source version và idempotent operation. |
| Một lỗi mapping làm retry cả batch mãi | Không phân loại lỗi vĩnh viễn và lỗi tạm thời. | Dead-letter lỗi dữ liệu; chỉ retry lỗi phục hồi được. |
| Elasticsearch trả 429 liên tục | Producer nhanh hơn cluster, concurrency/queue quá cao. | Backpressure, giảm worker, exponential backoff và jitter. |
| Dữ liệu index xong nhưng search chưa thấy | Refresh chưa xảy ra. | Chờ refresh tự nhiên hoặc refresh một lần sau import nếu cần. |
| Checkpoint bỏ qua document lỗi | Lưu checkpoint trước khi phân loại đầy đủ item. | Chỉ commit sau khi mọi item được xử lý hoặc lưu retry/dead-letter bền vững. |
| Import chậm dù tắt refresh | Mapping/analyzer/replica/aggregation hoặc I/O là bottleneck khác. | Đo toàn pipeline và cluster; không chỉ tập trung refresh. |
| Batch size theo count gây OOM | Document có kích thước rất khác nhau. | Giới hạn thêm payload bytes và xử lý document ngoại cỡ riêng. |
| Parallel stream làm memory tăng | Tạo nhiều object và request cùng lúc, không có backpressure. | Dùng bounded queue và số consumer hữu hạn. |

## 23. Nguyên tắc thiết kế

- Dùng Bulk API thay cho một request riêng cho mỗi document khi nhập dữ liệu lớn.
- Chia batch theo cả số document và kích thước payload ước lượng.
- Đọc nguồn bằng stream/cursor/keyset pagination; tránh `findAll()` cho dataset lớn.
- Chỉ giữ số batch đang xử lý có giới hạn; dùng bounded queue khi chạy song song.
- Không tạo future/task cho toàn bộ dataset cùng lúc.
- Kiểm tra lỗi từng item trong bulk response; HTTP thành công không có nghĩa mọi item thành công.
- Retry có chọn lọc, backoff, jitter và giới hạn; không retry mapping error vô hạn.
- Dùng deterministic ID/version để retry an toàn và tránh duplicate.
- Ghi checkpoint sau khi batch đã được xử lý hoặc lỗi đã được lưu bền vững.
- Tránh refresh từng batch nếu không cần visibility ngay; refresh một lần khi hoàn tất nếu phù hợp.
- Đo batch size/concurrency trên workload thật; không có một giá trị tối ưu cho mọi cluster.
- Theo dõi heap, GC, direct buffer, queue depth, 429 và p95/p99 latency.
- Dùng alias switch khi import vào index mới và cần công bố dữ liệu sau khi xác minh.

## 24. Những điểm cần nhớ

- Bulk API gửi nhiều index/create/update/delete action trong một request NDJSON.
- Bulk không phải transaction all-or-nothing; từng item có status riêng.
- Spring Data Elasticsearch cung cấp `bulkIndex`, `bulkUpdate` và `bulkDelete` qua `ElasticsearchOperations`.
- `IndexQueryBuilder` tạo index operation từ ID và entity object.
- Không tải toàn bộ nguồn vào heap; đọc theo stream/cursor/keyset và flush batch có giới hạn.
- Batch size cần xét cả số document lẫn byte; document lớn có thể làm batch cùng count tiêu thụ memory rất khác nhau.
- `clear()` batch sau khi xử lý giúp bỏ reference, nhưng không thay thế việc giới hạn nguồn, response và concurrency.
- Bounded queue tạo backpressure khi Elasticsearch xử lý chậm.
- Kiểm tra `errors` và từng item; chỉ retry lỗi tạm thời, không gửi lại mù quáng toàn batch.
- Deterministic ID và thao tác idempotent giúp retry an toàn.
- Checkpoint phải được commit sau khi mọi item đã được xử lý hoặc lỗi được lưu bền vững.
- Tránh refresh sau mỗi batch; chọn visibility policy theo yêu cầu đọc dữ liệu.
- Bulk import cần được theo dõi qua throughput, latency, 429, heap, GC và queue depth.

Nạp dữ liệu lớn hiệu quả là bài toán điều phối cả nguồn, batch, mạng, Elasticsearch và bộ nhớ ứng dụng. Hãy đọc dữ liệu theo luồng, giữ batch và concurrency ở giới hạn đo được, xử lý kết quả từng item và chỉ tiến checkpoint khi dữ liệu đã được ghi nhận an toàn. Cách tổ chức này giúp import đạt throughput tốt mà vẫn kiểm soát được bộ nhớ, lỗi và khả năng chạy lại.

## Tài liệu tham khảo

- [Elasticsearch — Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html)
- [Elasticsearch — Tune for indexing speed](https://www.elastic.co/guide/en/elasticsearch/reference/current/tune-for-indexing-speed.html)
- [Spring Data Elasticsearch — ElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/ElasticsearchOperations.html)
- [Spring Data Elasticsearch — BulkOptions API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/BulkOptions.html)
