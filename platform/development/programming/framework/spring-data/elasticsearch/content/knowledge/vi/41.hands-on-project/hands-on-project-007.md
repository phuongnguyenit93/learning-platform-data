# Nhập dữ liệu theo lô và xử lý lỗi từng tài liệu

Khi cần đưa hàng nghìn hoặc hàng triệu document vào Elasticsearch, gửi từng request riêng lẻ thường tốn nhiều thời gian và tạo overhead mạng không cần thiết. Bulk API cho phép gửi nhiều thao tác index, create, update hoặc delete trong một request. Spring Data Elasticsearch cung cấp ElasticsearchOperations.bulkIndex(...) và bulkUpdate(...) để gom thao tác theo lô; với luồng reactive, ReactiveElasticsearchOperations hỗ trợ save Flux theo batch.

Bulk giúp tăng throughput, nhưng một bulk request không phải transaction. HTTP response có thể thành công trong khi một số item bên trong thất bại. Ví dụ 998 document được index thành công nhưng 2 document bị lỗi mapping. Ứng dụng phải biết chính xác document nào thành công, document nào cần retry, document nào cần đưa vào Dead Letter Queue (DLQ), và khi nào được xác nhận message nguồn.

Bài học này trình bày cách thiết kế batch size, tạo IndexQuery, gọi bulkIndex, đọc BulkFailureException, xử lý BulkResponse ở cấp từng item, phân loại lỗi transient và permanent, retry có backoff, tránh duplicate, kiểm soát memory/backpressure, xử lý partial success với message broker, dùng BulkIngester cho ingestion liên tục, theo dõi metrics và kiểm thử lỗi từng document.

## 1. Vì sao nhập dữ liệu theo lô?

Giả sử một ứng dụng cần đồng bộ 100.000 sản phẩm vào index products. Nếu gửi từng document:

~~~text
Application
   |
   +-- PUT document 1
   +-- PUT document 2
   +-- PUT document 3
   +-- ...
   +-- PUT document 100000
~~~

Mỗi request có chi phí:

- Thiết lập và sử dụng kết nối HTTP.
- Serialize request và parse response.
- Network round trip.
- Xử lý request, authorization và routing ở server.
- Theo dõi timeout/retry cho từng request.

Bulk gom nhiều thao tác vào một request:

~~~text
Application
    |
    | Bulk request: documents 1..500
    v
Elasticsearch
    |
    | Bulk response: 500 item results
    v
Application
~~~

Số request giảm đáng kể, throughput thường tốt hơn và ứng dụng có thể kiểm soát batch size. Tuy nhiên, bulk không loại bỏ chi phí xử lý từng document. Elasticsearch vẫn xử lý từng item và trả trạng thái riêng cho từng thao tác.

### 1.1. Bulk không phải transaction

Một bulk request có thể có kết quả:

| Document | Kết quả |
|---|---|
| product-001 | Indexed |
| product-002 | Indexed |
| product-003 | Mapping error |
| product-004 | Indexed |
| product-005 | Rejected, status 429 |

Elasticsearch không rollback product-001, product-002 và product-004 chỉ vì product-003 hoặc product-005 thất bại.

Do đó:

- Không coi HTTP 200 là mọi item đều thành công.
- Không retry toàn bộ batch một cách mù quáng.
- Không ack toàn bộ message nguồn nếu vẫn còn item chưa được xử lý hoặc lưu DLQ theo chính sách.
- Không giả định có thể rollback các item đã ghi thành công.

## 2. Bulk API hoạt động như thế nào?

Elasticsearch Bulk API nhận dữ liệu theo định dạng NDJSON (newline-delimited JSON). Mỗi thao tác có một dòng metadata và, tùy loại thao tác, có thêm một dòng source hoặc update body.

Ví dụ hai thao tác index:

~~~http
POST products/_bulk
Content-Type: application/x-ndjson

{"index":{"_id":"p-100"}}
{"sku":"KB-100","name":"Keyboard","price":1299000}
{"index":{"_id":"p-101"}}
{"sku":"MS-101","name":"Mouse","price":299000}
~~~

Các action phổ biến:

| Action | Dòng tiếp theo | Ý nghĩa |
|---|---|---|
| index | Document source | Tạo mới hoặc thay thế document cùng ID |
| create | Document source | Chỉ tạo mới; lỗi nếu ID đã tồn tại |
| update | Partial document/script/upsert | Cập nhật document hiện có hoặc upsert nếu được cấu hình |
| delete | Không có dòng source | Xóa document theo ID |

Bulk API sử dụng NDJSON để parse và xử lý từng action hiệu quả. Dòng cuối của request phải kết thúc bằng newline khi gọi REST endpoint trực tiếp.

### 2.1. index và create khác nhau

Action index có semantics tạo mới hoặc thay thế document:

~~~json
{"index":{"_id":"p-100"}}
{"name":"Keyboard","price":1299000}
~~~

Nếu document p-100 đã tồn tại, source mới thay thế source cũ.

Action create chỉ tạo mới:

~~~json
{"create":{"_id":"p-100"}}
{"name":"Keyboard","price":1299000}
~~~

Nếu p-100 đã tồn tại, item thất bại với version conflict. Điều này hữu ích khi muốn phát hiện duplicate thay vì ghi đè.

Chọn action theo semantics nghiệp vụ:

- Snapshot/projection cần retry idempotent thường dùng index với ID ổn định.
- Event chỉ được phép tạo một lần có thể dùng create và xử lý conflict như duplicate.
- Partial update dùng update và phải đánh giá tính idempotent của script.
- Delete cần ID và routing đúng.

Data stream chỉ hỗ trợ action create. Nếu cần update hoặc delete document, phải target backing index phù hợp theo quy tắc của Elasticsearch.

## 3. Phân biệt lỗi request và lỗi item

Có hai tầng lỗi khác nhau:

### 3.1. Lỗi toàn request

Request không hoàn tất hoặc Elasticsearch không trả response hợp lệ:

- Network timeout hoặc connection reset.
- DNS/connection failure.
- Authentication/authorization ở cấp request.
- Index không tồn tại hoặc request không hợp lệ.
- Cluster không sẵn sàng.
- Proxy/load balancer trả 502/503/504.

Trong trường hợp này, ứng dụng có thể không biết item nào đã được xử lý trước khi kết nối bị ngắt. Đây là kết quả không chắc chắn (ambiguous outcome).

### 3.2. Lỗi từng item

Elasticsearch nhận bulk request và trả response, nhưng một số action thất bại:

- Mapping/parsing error.
- Document đã tồn tại với action create.
- Version conflict.
- Rejected execution do tải cao.
- Field hoặc giá trị không hợp lệ.

Bulk response vẫn có thể là HTTP 200. Field errors ở cấp response cho biết có item thất bại; từng phần tử trong items chứa status và error riêng.

Ví dụ:

~~~json
{
  "took": 18,
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
    },
    {
      "index": {
        "_index": "products",
        "_id": "p-102",
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

Trong ví dụ:

- p-100 thành công.
- p-101 có dữ liệu không tương thích mapping.
- p-102 bị từ chối tạm thời do tải.

Không thể xử lý cả ba trường hợp bằng một chiến lược retry giống nhau.

## 4. Dùng ElasticsearchOperations.bulkIndex

Spring Data Elasticsearch cung cấp bulkIndex trên ElasticsearchOperations. API nhận danh sách IndexQuery, BulkOptions và index đích.

Ví dụ entity:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    private String sku;
    private String name;
    private BigDecimal price;

    // getters and setters
}
~~~

Tạo IndexQuery cho từng document:

~~~java
List<IndexQuery> queries = products.stream()
        .map(product -> IndexQuery.builder()
                .withId(product.getId())
                .withObject(product)
                .build())
        .toList();
~~~

Gọi bulk:

~~~java
List<IndexedObjectInformation> indexed =
        operations.bulkIndex(
                queries,
                BulkOptions.defaultOptions(),
                IndexCoordinates.of("products"));
~~~

bulkIndex trả về thông tin các document được index khi các item thành công. Nếu có lỗi item, Spring Data Elasticsearch có thể ném BulkFailureException chứa thông tin các document thất bại.

### 4.1. Tạo IndexQuery với ID rõ ràng

Đối với import/replay, nên gán document ID xác định:

~~~java
IndexQuery query = IndexQuery.builder()
        .withId(product.getId())
        .withObject(product)
        .build();
~~~

ID ổn định giúp một lần retry index cùng source vào cùng document. Nếu để Elasticsearch tự sinh ID, retry sau timeout có thể tạo document trùng.

Nếu entity đã có @Id, mapping có thể lấy ID từ entity object; tuy nhiên, khi xây batch và cần đối chiếu lỗi với record nguồn, việc tạo map ID rõ ràng vẫn hữu ích.

### 4.2. Dùng BulkOptions

BulkOptions cho phép truyền một số tùy chọn request:

~~~java
BulkOptions options = BulkOptions.builder()
        .withTimeout(Duration.ofSeconds(30))
        .withRefreshPolicy(RefreshPolicy.NONE)
        .build();

List<IndexedObjectInformation> result = operations.bulkIndex(
        queries,
        options,
        IndexCoordinates.of("products"));
~~~

Các tùy chọn thường gặp gồm:

- timeout: thời gian chờ một số bước vận hành như tạo index tự động, cập nhật mapping động và active shards.
- refreshPolicy: thời điểm dữ liệu được hiển thị với search.
- waitForActiveShards: số shard copies cần active trước khi thao tác tiếp tục.
- pipeline: ingest pipeline cần áp dụng.
- routingId: routing mặc định nếu phù hợp với request.

Timeout của BulkOptions không đồng nghĩa socket timeout của HTTP client. Một request có thể timeout ở tầng client dù server vẫn đang xử lý.

### 4.3. Refresh không nên bật sau mọi batch

Refresh ngay sau từng batch có thể làm giảm indexing throughput. Với ingestion lớn, thường để refresh policy mặc định/NONE và refresh sau khi hoàn tất import hoặc theo lịch.

Chỉ dùng IMMEDIATE hoặc WAIT_UNTIL nếu ứng dụng cần search visibility ngay sau request. Việc refresh không làm bulk trở thành transaction.

## 5. Xử lý BulkFailureException trong Spring Data

BulkFailureException là exception Spring Data Elasticsearch dùng để báo lỗi trong bulk operation. API hiện hành cung cấp:

- getFailedDocuments(): map các document thất bại.
- Key của map là document ID.
- Value là FailureDetails.
- FailureDetails có status và errorMessage.

Ví dụ:

~~~java
try {
    operations.bulkIndex(
            queries,
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("products"));
} catch (BulkFailureException exception) {
    exception.getFailedDocuments().forEach((documentId, failure) -> {
        log.warn(
                "Failed to index document id={}, status={}, reason={}",
                documentId,
                failure.status(),
                failure.errorMessage());
    });
}
~~~

Không log toàn bộ entity/source khi xử lý lỗi nếu document có dữ liệu cá nhân hoặc bí mật. Log ID, status, error type/reason đã được rút gọn và correlation ID thường đủ để điều tra.

### 5.1. Đối chiếu lỗi với record nguồn

Trước khi gửi batch, tạo map ID về record hoặc message metadata:

~~~java
Map<String, ProductInput> sourceById = new HashMap<>();
List<IndexQuery> queries = new ArrayList<>();

for (ProductInput input : batch) {
    ProductDocument document = mapper.toDocument(input);
    sourceById.put(document.getId(), input);

    queries.add(IndexQuery.builder()
            .withId(document.getId())
            .withObject(document)
            .build());
}
~~~

Khi bắt exception:

~~~java
try {
    operations.bulkIndex(
            queries,
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("products"));
} catch (BulkFailureException exception) {
    exception.getFailedDocuments().forEach((id, failure) -> {
        ProductInput original = sourceById.get(id);
        handleFailure(original, id, failure.status(), failure.errorMessage());
    });
}
~~~

Giữ cả source record hoặc một reference bền vững tới source record để có thể retry hoặc ghi DLQ. Không chỉ giữ một exception message rồi bỏ mất payload cần khôi phục.

### 5.2. Giới hạn của BulkFailureException

FailureDetails trong Spring Data hiện hành chỉ cung cấp HTTP status và errorMessage. Nếu cần phân loại sâu theo Elasticsearch error type, reason, shard failure hoặc cần giữ context của từng operation, hãy dùng Elasticsearch Java API Client BulkResponse hoặc BulkIngester listener.

Ngoài ra, nếu một batch có nhiều operation cùng document ID, map lỗi theo ID không đủ để phân biệt từng operation. Tránh duplicate ID trong cùng batch hoặc dùng low-level response có thứ tự/context cho từng item.

### 5.3. Không bắt exception rồi bỏ qua

Ví dụ nguy hiểm:

~~~java
try {
    operations.bulkIndex(queries, index);
} catch (BulkFailureException ignored) {
    // continue
}
~~~

Đoạn code này làm mất thông tin document thất bại. Nếu caller sau đó xác nhận batch/message đã xử lý, các record lỗi có thể bị mất vĩnh viễn.

Luôn phân loại từng failure và đưa nó vào một trạng thái có thể theo dõi: retry, DLQ, reject hoặc stop pipeline.

## 6. Đọc từng BulkResponseItem bằng Elasticsearch Java API Client

Khi cần đầy đủ thông tin item-level, có thể gọi ElasticsearchClient trực tiếp trong một adapter riêng:

~~~java
BulkResponse response = elasticsearchClient.bulk(request -> request
        .index("products")
        .operations(operation -> operation
                .index(index -> index
                        .id("p-100")
                        .document(productDocument))));

if (response.errors()) {
    for (BulkResponseItem item : response.items()) {
        if (item.error() != null) {
            log.warn(
                    "Bulk item failed id={}, status={}, type={}, reason={}",
                    item.id(),
                    item.status(),
                    item.error().type(),
                    item.error().reason());
        }
    }
}
~~~

BulkResponse có:

- errors: true nếu có ít nhất một operation thất bại.
- items: kết quả từng operation theo đúng thứ tự đã gửi.
- status: HTTP status của từng item.
- error: loại lỗi và lý do khi item thất bại.
- _id/_index/result/version/sequence metadata khi phù hợp.

HTTP status 200 của toàn request không có nghĩa mọi item thành công. Phải kiểm tra errors và từng item.error().

### 6.1. Duy trì mapping giữa request item và input

Bulk API trả item theo thứ tự operation trong request. Có thể giữ danh sách input theo cùng thứ tự:

~~~java
List<ProductInput> inputs = batch;
BulkResponse response = sendBulk(inputs);

for (int i = 0; i < response.items().size(); i++) {
    ProductInput input = inputs.get(i);
    BulkResponseItem item = response.items().get(i);

    if (item.error() == null) {
        markIndexed(input, item.id());
    } else {
        handleItemFailure(input, item);
    }
}
~~~

Đây là cách chính xác khi ID có thể trùng hoặc khi một batch có nhiều loại action. Không sắp xếp lại danh sách response trước khi đối chiếu.

### 6.2. Một item có thể là index, create, update hoặc delete

Response item là union theo loại action. Nếu code cần lấy result hoặc error, hãy đọc đúng variant tương ứng và null-check. Không giả định mọi operation đều là index.

### 6.3. Khi nào nên dùng client trực tiếp?

Ưu tiên Spring Data Operations khi:

- Entity mapping và repository abstraction đã đủ.
- Cần batch index/update đơn giản.
- Cần exception map cơ bản.

Dùng Elasticsearch Java API Client trực tiếp khi:

- Cần error type/reason đầy đủ.
- Cần correlation context từng item.
- Cần BulkIngester tự gom và gửi operation.
- Cần kiểm soát action metadata chi tiết.
- Cần sử dụng tính năng bulk mới chưa được Spring Data abstraction expose.

Có thể giữ client trực tiếp trong một adapter/repository chuyên biệt để domain service không phụ thuộc API transport.

## 7. Phân loại lỗi từng document

Không phải lỗi nào cũng nên retry. Một ma trận khởi đầu:

| HTTP status / lỗi | Ví dụ | Hành động thường phù hợp |
|---|---|---|
| 400 | mapper_parsing_exception, illegal_argument_exception | Permanent; sửa dữ liệu/mapping, đưa DLQ |
| 401 | authentication_exception | Dừng hoặc pause pipeline; sửa credential |
| 403 | security_exception | Sửa privilege/role; không retry liên tục |
| 404 | index_not_found_exception | Kiểm tra deployment/index provisioning |
| 409 | version_conflict_engine_exception | Xử lý theo version/idempotency semantics |
| 413 | request entity too large | Chia batch nhỏ hơn |
| 429 | es_rejected_execution_exception | Retry subset với backoff |
| 502/503/504 | gateway/service unavailable | Retry có giới hạn |
| Network timeout/reset | Không nhận được response | Outcome có thể chưa rõ; retry chỉ khi thao tác an toàn |

Phân loại phải dựa trên cả status và error type/reason. Một status code có thể có nhiều nguyên nhân và không phải mọi lỗi cùng status đều có cùng cách khắc phục.

### 7.1. Lỗi dữ liệu/mapping là permanent cho payload hiện tại

Ví dụ:

- price gửi chuỗi nhưng mapping là numeric.
- date không parse được.
- Field object có cấu trúc không tương thích mapping.
- Giá trị vượt giới hạn hoặc vi phạm validation.
- Document chứa field không hợp lệ với ingest pipeline.

Retry cùng payload mà không sửa dữ liệu thường thất bại lặp lại. Đưa item vào DLQ hoặc bảng rejected record, lưu lỗi và source payload để điều tra.

### 7.2. 429 là lỗi có thể retry

429 thường cho biết Elasticsearch đang bị quá tải hoặc từ chối công việc. Cách xử lý:

- Chỉ retry item thất bại.
- Exponential backoff.
- Thêm jitter để các consumer không retry đồng loạt.
- Giới hạn số lần thử.
- Giảm batch size hoặc concurrency nếu 429 kéo dài.
- Theo dõi rejection rate và queue lag.

Không retry ngay lập tức trong vòng lặp tight loop. Việc đó làm tải tăng thêm và có thể khiến cluster khó phục hồi.

### 7.3. 409 version conflict cần hiểu semantics

Version conflict có thể là:

- Duplicate create.
- Event cũ đến sau event mới.
- Optimistic concurrency control phát hiện document đã thay đổi.

Không tự động coi mọi 409 là thành công. Nếu event cũ bị từ chối vì source version thấp hơn, có thể đánh dấu stale/ignored. Nếu conflict do một update cần áp dụng, cần đọc lại và xử lý theo business rule.

### 7.4. Timeout là outcome không chắc chắn

Client timeout không chứng minh Elasticsearch chưa ghi document. Server có thể đã xử lý request nhưng response không tới client.

Với index operation dùng stable _id và snapshot payload, retry thường an toàn về trạng thái cuối. Với script tăng số lượng hoặc delta update, retry có thể áp dụng thay đổi hai lần.

Nếu timeout xảy ra ở cấp toàn request, không có item response để xác định chính xác item nào đã thành công. Idempotency, stable IDs và reconciliation là lớp bảo vệ quan trọng.

## 8. Retry chỉ các item thất bại

Giả sử batch có 500 document:

- 490 item thành công.
- 7 item bị 429.
- 3 item bị mapping error.

Chiến lược đúng:

- Ghi nhận 490 item thành công.
- Đưa 7 item 429 vào retry queue.
- Đưa 3 item mapping error vào DLQ/rejected records.
- Không gửi lại 490 item thành công nếu không có lý do.

Luồng:

~~~text
Batch of 500
     |
     v
Bulk request
     |
     v
Per-item results
     |
     +---- 490 success ----> Mark complete
     |
     +---- 7 transient ----> Retry queue
     |
     +---- 3 permanent ----> DLQ
~~~

### 8.1. Retry có giới hạn

Ví dụ policy:

~~~java
Duration delayFor(int attempt) {
    long baseMillis = 200;
    long maxMillis = 10_000;
    long exponential = Math.min(
            maxMillis,
            baseMillis * (1L << Math.min(attempt, 10)));

    long jitter = ThreadLocalRandom.current()
            .nextLong(Math.max(1, exponential / 2), exponential + 1);

    return Duration.ofMillis(jitter);
}
~~~

Đây là ví dụ backoff có jitter. Production nên dùng thư viện retry/resilience đã được chuẩn hóa, giới hạn attempt và tổng thời gian retry.

Không dùng phép shift hoặc nhân có thể overflow nếu attempt không được giới hạn.

### 8.2. Retry budget

Ngoài max attempts, có thể giới hạn:

- Tổng thời gian retry.
- Số item retry cùng lúc.
- Số batch retry đồng thời.
- Tỷ lệ retry trên throughput bình thường.

Nếu vượt retry budget, đưa item sang DLQ hoặc dừng pipeline và cảnh báo. Không để một nhóm item lỗi giữ worker vô hạn.

### 8.3. Retry riêng lẻ hay gom lại?

Retry từng item tạo nhiều request nhỏ. Có thể gom các item retryable thành batch mới để giảm overhead:

~~~text
Retry queue
    |
    +-- item p-101
    +-- item p-108
    +-- item p-209
           |
           v
    New bulk request
~~~

Khi gom lại, vẫn phải giữ metadata nguồn và giới hạn batch size. Không trộn item đã quá hạn hoặc version stale vào batch chỉ vì chúng nằm cùng queue.

## 9. Xử lý partial success trong message consumer

Một consumer có thể nhận batch event từ Kafka, RabbitMQ hoặc một nguồn khác rồi index vào Elasticsearch.

Điểm quan trọng là acknowledgement/offset commit phải phản ánh trạng thái xử lý của từng record.

### 9.1. Không ack cả batch khi một item bị bỏ quên

Nếu consumer nhận 100 event, 98 thành công, 1 retryable và 1 permanent:

- 98 event đã được index.
- 1 event cần retry.
- 1 event cần được ghi DLQ bền vững.

Chỉ ack/commit theo chính sách khi mọi record trong phạm vi commit đã có kết quả được lưu bền vững. Permanent failure có thể được coi là đã xử lý sau khi DLQ write thành công.

### 9.2. Kafka offset được commit theo partition

Kafka commit offset là tiến độ theo partition, không phải một ack độc lập tùy ý cho từng record trong cùng partition. Nếu record offset 10 thất bại nhưng record 11 thành công, không commit vượt qua 10 nếu điều đó khiến consumer không bao giờ nhận lại record lỗi.

Các lựa chọn:

- Dừng/pause partition tới khi retry record lỗi hoàn tất.
- Lưu record lỗi vào DLQ bền vững rồi mới commit offset tiếp theo.
- Dùng retry topic có semantics ordering được thiết kế rõ.
- Dùng framework hỗ trợ partial batch acknowledgement và kiểm soát offset.

Với nhiều partition, có thể tiếp tục xử lý partition khác trong khi một partition bị pause, tùy cấu hình consumer.

### 9.3. RabbitMQ acknowledgement

Với RabbitMQ, chỉ ack message sau khi thao tác Elasticsearch thành công hoặc message lỗi đã được chuyển DLQ theo policy. Requeue liên tục cùng message poison có thể tạo vòng lặp nóng.

### 9.4. DLQ write cũng phải đáng tin cậy

Không commit offset/ack message trước khi DLQ record được ghi bền vững. DLQ nên lưu:

- Original message hoặc payload đã mã hóa phù hợp.
- eventId/correlationId.
- Document ID và index đích.
- Error status/type/reason.
- Attempt count.
- Source partition/offset hoặc message metadata.
- First/last failure time.
- Schema version và consumer version.

Hạn chế lưu dữ liệu nhạy cảm không cần thiết và đặt retention/access policy cho DLQ.

## 10. Idempotency và stable document ID

Retry chỉ an toàn khi thao tác có thể lặp mà không làm sai trạng thái.

Với snapshot:

~~~java
ProductDocument document = mapper.toDocument(event);
document.setId(event.productId());
repository.save(document);
~~~

Mỗi lần retry ghi cùng document ID và cùng snapshot. Trạng thái cuối không tạo bản sao.

Với update dạng tăng:

~~~json
{
  "script": {
    "source": "ctx._source.stock += params.delta",
    "params": {
      "delta": 2
    }
  }
}
~~~

Retry cùng event có thể cộng hai lần. Cần deduplication hoặc version guard.

### 10.1. Dùng deterministic ID

Document ID thường lấy từ source primary key hoặc composite tenant/source key:

~~~text
tenant-7:product-100
~~~

Không dùng UUID ngẫu nhiên mới mỗi lần retry nếu document đại diện trạng thái hiện tại của cùng một entity.

### 10.2. Version guard

Nếu event có aggregateVersion, có thể dùng external versioning hoặc update script có điều kiện để event cũ không ghi đè event mới. Khi retry cùng version, phải định nghĩa rõ conflict/duplicate semantics.

### 10.3. Index action và create action

Nếu dùng index action, retry có thể thay thế cùng _id. Nếu dùng create, retry sau khi lần đầu đã thành công sẽ nhận conflict. Có thể coi conflict là duplicate hợp lệ chỉ khi xác minh event/document identity và semantics đúng.

## 11. Chia batch theo số lượng và kích thước bytes

Batch size quá nhỏ:

- Nhiều HTTP request.
- Tăng network overhead.
- Throughput có thể thấp.

Batch size quá lớn:

- Request payload lớn.
- Tốn heap để giữ source và serialized request.
- Tăng thời gian xử lý và khả năng timeout.
- Một lỗi transport làm outcome của nhiều item khó xác định.
- Tăng memory pressure và queueing ở cluster.

Không có một số lượng document đúng cho mọi workload. Kích thước phụ thuộc:

- Average document size.
- Số field và độ sâu JSON.
- Số shard.
- Ingest pipeline.
- Cluster hardware và tải search đồng thời.
- Network latency.
- Mapping và vector fields.
- Replicas và refresh settings.

### 11.1. Dùng cả giới hạn count và byte

Một điểm khởi đầu thường được thử nghiệm là vài trăm đến khoảng một nghìn operation mỗi batch, đồng thời giới hạn payload theo bytes. Elasticsearch Java BulkIngester có default maxOperations 1000 và maxSize 5 MiB; đó là default của helper, không phải giới hạn bắt buộc hoặc giá trị tối ưu cho mọi hệ thống.

Đo throughput và p95/p99 latency trong môi trường gần production rồi điều chỉnh.

### 11.2. Chia List thành chunk có giới hạn

Ví dụ chia theo số document:

~~~java
static <T> List<List<T>> partition(List<T> items, int batchSize) {
    List<List<T>> batches = new ArrayList<>();

    for (int start = 0; start < items.size(); start += batchSize) {
        int end = Math.min(start + batchSize, items.size());
        batches.add(items.subList(start, end));
    }

    return batches;
}
~~~

Sử dụng:

~~~java
for (List<ProductInput> batch : partition(inputs, 500)) {
    processBatch(batch);
}
~~~

Đây là ví dụ đơn giản theo count. Với document có kích thước rất khác nhau, cần thêm giới hạn serialized bytes hoặc dùng BulkIngester.

### 11.3. Không giữ toàn bộ file import trong heap

Tránh:

~~~java
List<ProductInput> all = readEntireFileIntoMemory();
processAll(all);
~~~

Với file lớn, đọc theo stream hoặc cursor:

~~~text
Input stream
    |
    v
Parse bounded batch
    |
    v
Index batch
    |
    v
Persist batch result/checkpoint
    |
    v
Read next batch
~~~

Giữ số batch đang xử lý đồng thời ở mức giới hạn. Nếu producer đọc nhanh hơn Elasticsearch xử lý, queue không giới hạn sẽ làm heap tăng liên tục.

## 12. BulkIngester cho ingestion liên tục

Elasticsearch Java API Client cung cấp BulkIngester để tự gom operation thành bulk request dựa trên:

- Số operation tối đa.
- Kích thước bytes tối đa.
- Flush interval.
- Số request đồng thời.

Ví dụ:

~~~java
BulkIngester<Void> ingester = BulkIngester.of(builder -> builder
        .client(elasticsearchClient)
        .maxOperations(500)
        .maxSize(5 * 1024 * 1024)
        .flushInterval(1, TimeUnit.SECONDS)
        .maxConcurrentRequests(1));

for (ProductDocument product : products) {
    ingester.add(operation -> operation
            .index(index -> index
                    .index("products")
                    .id(product.getId())
                    .document(product)));
}

ingester.close();
~~~

close sẽ flush operation còn đang chờ và giải phóng tài nguyên. Trong ứng dụng chạy lâu dài, cần quản lý lifecycle của ingester đúng cách; không tạo một ingester mới cho từng document.

### 12.1. Backpressure

BulkIngester có giới hạn request đồng thời. Khi đã đạt giới hạn và buffer đầy, thao tác add có thể block để tạo backpressure thay vì tiếp tục tích lũy vô hạn.

Đây là hành vi có chủ đích:

- Elasticsearch chậm thì producer bị chậm lại.
- Queue trong memory được giữ ở giới hạn.
- Hệ thống không tiếp tục nhận dữ liệu nhanh hơn khả năng index.

Nếu dùng executor hoặc queue riêng, cần đặt capacity và chính sách khi queue đầy.

### 12.2. BulkListener và context từng item

BulkIngester hỗ trợ listener:

~~~java
BulkListener<String> listener = new BulkListener<>() {

    @Override
    public void beforeBulk(
            long executionId,
            BulkRequest request,
            List<String> contexts) {
        // contexts correspond to operations in this request
    }

    @Override
    public void afterBulk(
            long executionId,
            BulkRequest request,
            List<String> contexts,
            BulkResponse response) {

        for (int i = 0; i < response.items().size(); i++) {
            BulkResponseItem item = response.items().get(i);
            String sourceReference = contexts.get(i);

            if (item.error() != null) {
                handleFailure(
                        sourceReference,
                        item.status(),
                        item.error().type(),
                        item.error().reason());
            } else {
                markIndexed(sourceReference, item.id());
            }
        }
    }

    @Override
    public void afterBulk(
            long executionId,
            BulkRequest request,
            List<String> contexts,
            Throwable failure) {
        // The whole request could not be sent or completed.
        handleRequestFailure(contexts, failure);
    }
};
~~~

Khi thêm operation, truyền context:

~~~java
ingester.add(
        operation -> operation.index(index -> index
                .index("products")
                .id(product.getId())
                .document(product)),
        sourceRecordId);
~~~

Context giúp liên kết từng response item với record/message gốc mà không phải suy luận từ log hoặc chỉ dựa vào document ID.

### 12.3. Không retry vô hạn ngay trong listener

Listener nên phân loại kết quả và chuyển item retryable vào retry scheduler/queue có giới hạn. Nếu listener lập tức add lại cùng item không có giới hạn, có thể tạo vòng lặp và làm ingester không bao giờ drain.

### 12.4. Đóng ingester khi ứng dụng shutdown

BulkIngester giữ buffer và có thể có request đang chạy. Cần gọi close ở lifecycle shutdown để flush pending operations và chờ tài nguyên được giải phóng theo semantics của API. Nếu process bị kill đột ngột, nguồn dữ liệu phải có checkpoint/replay để không mất item chưa được xác nhận.

## 13. Reactive ingestion với Spring Data Elasticsearch

ReactiveDocumentOperations không cung cấp cùng kiểu bulkIndex imperative trả về danh sách IndexedObjectInformation. Thay vào đó, API hỗ trợ save Flux theo batch size:

~~~java
Flux<ProductDocument> saved = reactiveOperations.save(
        productFlux,
        ProductDocument.class,
        500);
~~~

API gom entity thành các batch có tối đa bulkSize phần tử và có timeout buffer tối đa 200 ms trước khi gửi bulk operation.

Một ví dụ:

~~~java
return readProducts()
        .map(mapper::toDocument)
        .buffer(500)
        .concatMap(batch ->
                reactiveOperations.save(
                        Flux.fromIterable(batch),
                        ProductDocument.class,
                        500)
                    .collectList());
~~~

Ở ví dụ này, buffer tạo batch ở tầng ứng dụng; save Flux cũng có bulkSize riêng. Có thể đơn giản hóa bằng cách truyền một Flux liên tục vào save(..., bulkSize) nếu không cần xử lý từng batch ở tầng ứng dụng.

### 13.1. Giới hạn concurrency

Tránh:

~~~java
productFlux.flatMap(
        product -> reactiveOperations.save(product),
        1000);
~~~

Concurrency 1000 có thể tạo quá nhiều request đồng thời và làm cluster quá tải. Chọn concurrency nhỏ, đo latency và dùng backpressure.

### 13.2. Lỗi trong reactive batch

Bulk save có thể phát BulkFailureException trong reactive chain. Xử lý bằng onErrorResume hoặc retryWhen theo policy:

~~~java
return reactiveOperations.save(
            Flux.fromIterable(batch),
            ProductDocument.class,
            batch.size())
        .collectList()
        .onErrorResume(BulkFailureException.class, error -> {
            return handleBulkFailure(batch, error);
        });
~~~

Không dùng onErrorContinue như một cách chung để bỏ qua mọi lỗi. Nó có thể làm mất mối liên hệ giữa record và failure, đồng thời khiến pipeline tiếp tục dù dữ liệu không được lưu.

### 13.3. RetryWhen không được retry mọi exception

Retry chỉ lỗi transient và thao tác idempotent. Không retry mapping error, validation error hoặc authentication error vô hạn. Với bulk exception, phân loại từng document failure trước khi quyết định retry.

## 14. Retry toàn request khi không có response

Nếu client nhận timeout hoặc connection reset, không có BulkResponse để phân loại item. Có thể một phần hoặc toàn bộ thao tác đã được Elasticsearch xử lý.

Ví dụ:

~~~text
Client sends bulk
       |
       v
Elasticsearch indexes 70 items
       |
       | connection drops before response
       v
Client sees timeout
~~~

Client không thể suy ra 70 item nào đã ghi chỉ từ timeout.

Quy tắc:

- Dùng stable document IDs.
- Ưu tiên snapshot/index operation idempotent.
- Lưu batch source/checkpoint để replay.
- Không retry delta scripts nếu chưa có dedup/version guard.
- Sau retry, có thể reconciliation bằng ID/sourceVersion.
- Giới hạn retry và cảnh báo khi timeout tăng.

Không dùng một request timeout lớn hơn như giải pháp duy nhất. Điều tra cluster load, shard latency, network và payload size.

## 15. Kiểm soát ordering và version conflict

Nhiều batch hoặc consumer có thể cập nhật cùng một document đồng thời. Nếu event cũ xử lý sau event mới, dữ liệu mới có thể bị ghi đè.

Ví dụ:

~~~text
Product version 10: price = 100
Product version 11: price = 120

Worker A gửi version 10 (chậm)
Worker B gửi version 11 (nhanh)
Worker B ghi trước
Worker A ghi sau
~~~

Document có thể quay về price = 100 nếu không có version guard.

Các giải pháp:

- Partition message theo aggregate ID để giữ ordering trong cùng partition.
- Giữ một consumer xử lý tuần tự theo key khi cần.
- Dùng external versioning từ source version.
- Dùng if_seq_no/if_primary_term cho optimistic concurrency control.
- Bỏ qua stale event theo sourceVersion.

Bulk action hỗ trợ version và optimistic concurrency metadata theo từng item. Không coi internal Elasticsearch _version là version nghiệp vụ của database nếu chưa có quy tắc ánh xạ.

## 16. Bulk update và script có an toàn khi retry?

Bulk update có thể dùng partial document hoặc script.

Gán giá trị:

~~~json
{"update":{"_id":"p-100"}}
{"doc":{"price":1299000}}
~~~

Retry cùng giá trị thường giữ trạng thái cuối như nhau.

Cộng delta:

~~~json
{"update":{"_id":"p-100"}}
{"script":{"source":"ctx._source.stock += params.delta","params":{"delta":2}}}
~~~

Retry cùng operation sẽ cộng hai lần. Cần:

- eventId deduplication.
- sourceVersion check.
- script ghi version cùng thao tác.
- hoặc chuyển delta thành snapshot tuyệt đối trước khi index.

Bulk update có thể có partial failures như bulk index. Kiểm tra lỗi từng item và không retry mù các script không idempotent.

### 16.1. retry_on_conflict không giải quyết mọi lỗi

Update action hỗ trợ retry_on_conflict để retry update khi có version conflict do concurrent modification. Nó không phải retry policy cho mapping errors, 429, network timeout hoặc duplicate event.

Không nhầm retry_on_conflict với retry toàn request hoặc deduplication event.

## 17. Chia retry queue và Dead Letter Queue

DLQ lưu những item không thể xử lý tự động sau số lần retry hoặc lỗi permanent:

~~~text
Bulk item failure
       |
       v
Classify error
       |
       +---- transient ----> Retry queue
       |
       +---- permanent ----> DLQ
       |
       +---- unknown ------> Quarantine / operator review
~~~

DLQ record nên chứa:

~~~json
{
  "sourceRecordId": "evt-100",
  "documentId": "product-100",
  "targetIndex": "products",
  "attempts": 5,
  "firstFailedAt": "2026-11-13T09:00:00Z",
  "lastFailedAt": "2026-11-13T09:02:00Z",
  "status": 400,
  "errorType": "mapper_parsing_exception",
  "errorMessage": "failed to parse field [price]",
  "sourceVersion": 18,
  "payloadReference": "object-store://failed-events/evt-100"
}
~~~

Payload có thể được lưu trực tiếp hoặc lưu ở object storage/database với reference. Chọn retention, encryption và access policy phù hợp với dữ liệu.

### 17.1. Redrive DLQ

Quy trình redrive:

1. Xác định nguyên nhân lỗi.
2. Sửa dữ liệu, mapping hoặc code.
3. Kiểm tra event chưa stale so với source version hiện tại.
4. Reprocess bằng cùng document ID/idempotency key.
5. Ghi kết quả redrive.
6. Đánh dấu DLQ record đã xử lý.

Không replay toàn bộ DLQ không kiểm soát sau khi sửa một lỗi mapping; một số event có thể đã cũ hoặc không còn hợp lệ.

### 17.2. DLQ không phải nơi bỏ quên dữ liệu

Theo dõi:

- Số item trong DLQ.
- Tuổi item cũ nhất.
- Lỗi theo type/index/producer.
- Tỷ lệ redrive thành công.
- Số item bị stale/duplicate.

Đặt owner và quy trình xử lý cho DLQ. Nếu không có cảnh báo và redrive, DLQ chỉ biến lỗi mất dữ liệu thành lỗi khó nhìn thấy hơn.

## 18. Checkpoint và khả năng khôi phục import

Với import file hoặc batch job, ghi checkpoint sau mỗi batch đã có kết quả bền vững:

~~~text
Read source records 1..500
       |
       v
Bulk index
       |
       v
Classify all item results
       |
       +---- success -> mark complete
       +---- retry -> persist retry state
       +---- permanent -> persist DLQ
       |
       v
Commit source checkpoint
       |
       v
Read records 501..1000
~~~

Checkpoint có thể là:

- File offset hoặc line number.
- Database primary key/cursor.
- Kafka partition offset.
- Change log sequence number.
- Batch ID và trạng thái xử lý.

Không commit checkpoint trước khi trạng thái của từng item đã được lưu. Nếu job crash sau khi index nhưng trước checkpoint, batch có thể được replay; stable ID và idempotent operations giúp an toàn.

### 18.1. Batch ledger

Với import quan trọng, có thể lưu batch ledger:

| Batch ID | Source range | Success | Retry | DLQ | State |
|---|---|---:|---:|---:|---|
| run-01-0001 | 1–500 | 498 | 1 | 1 | Partial |
| run-01-0002 | 501–1000 | 500 | 0 | 0 | Complete |

Ledger giúp restart job, điều tra và đối soát mà không phải suy luận từ log.

### 18.2. Không đánh dấu batch complete chỉ vì Bulk API trả HTTP 200

Batch chỉ complete khi mọi item đã:

- Index/update/delete thành công; hoặc
- Được xác định duplicate/stale theo policy; hoặc
- Được lưu DLQ/rejected record một cách bền vững.

Item đang retry hoặc chưa rõ outcome vẫn là trạng thái chưa hoàn tất.

## 19. Tối ưu throughput và ổn định cluster

Bulk throughput phụ thuộc nhiều yếu tố:

- Batch count và byte size.
- Số request đồng thời.
- Số shard và routing distribution.
- Refresh interval.
- Replica count.
- Ingest pipeline.
- Mapping/dynamic fields.
- Document size.
- Search workload cạnh tranh.

Một cách tuning:

1. Bắt đầu bằng batch vừa phải, ví dụ 500 operations.
2. Giới hạn payload bytes.
3. Đặt concurrency thấp ban đầu.
4. Đo throughput và latency.
5. Tăng batch/concurrency từng bước.
6. Theo dõi 429, heap, indexing pressure và search latency.
7. Dừng tăng khi throughput không còn cải thiện hoặc cluster bắt đầu bị từ chối.

### 19.1. Refresh interval

Trong bulk import lớn, có thể cân nhắc tăng refresh interval hoặc tạm tắt automatic refresh theo kế hoạch vận hành, rồi refresh sau import. Không làm điều này trên index đang phục vụ search mà không hiểu tác động tới visibility.

Nếu tạm đặt refresh_interval = -1, cần khôi phục setting sau khi hoàn tất và refresh để dữ liệu hiển thị.

### 19.2. Replicas

Trong một số lần bulk load lớn vào index mới, có thể điều chỉnh replicas trong quy trình có kiểm soát để giảm công việc ghi replica, rồi khôi phục replicas và đợi cluster health phù hợp. Đây là thao tác vận hành cần đánh giá durability/availability; không tự động thay đổi replica setting cho mọi batch.

### 19.3. Dynamic mapping

Nếu mỗi batch đưa field mới không kiểm soát, dynamic mapping có thể tạo nhiều field và làm cluster state phình to. Định nghĩa mapping/template trước, validate payload và giới hạn số field.

## 20. Observability cho batch ingestion

Mỗi batch nên có batchId/correlationId và các số liệu:

- input_count.
- indexed_count.
- updated_count.
- failed_count.
- retry_count.
- dlq_count.
- duplicate/stale_count.
- request_latency.
- bulk_bytes.
- retry_delay.
- batch_age.
- consumer_lag.

Metrics theo loại lỗi:

~~~text
bulk_items_total{result="success"}
bulk_items_total{result="retry"}
bulk_items_total{result="dlq"}
bulk_items_total{result="duplicate"}
bulk_requests_total
bulk_request_duration_seconds
bulk_payload_bytes
bulk_retry_attempts
bulk_dlq_depth
~~~

Tránh dùng document ID hoặc user ID làm metric label vì cardinality có thể tăng không giới hạn. Các ID cụ thể nên nằm trong structured logs hoặc trace attributes có kiểm soát.

### 20.1. Structured log

Ví dụ:

~~~json
{
  "event": "elasticsearch_bulk_item_failed",
  "batchId": "import-2026-11-13-001",
  "documentId": "product-100",
  "sourceRecordId": "evt-100",
  "index": "products",
  "status": 429,
  "errorType": "es_rejected_execution_exception",
  "attempt": 2,
  "decision": "RETRY"
}
~~~

Không log toàn bộ payload nếu có dữ liệu nhạy cảm. Lưu payload trong kho có kiểm soát và log reference khi cần.

### 20.2. Alert

Các cảnh báo hữu ích:

- Tỷ lệ 429 tăng kéo dài.
- Bulk timeout vượt ngưỡng.
- DLQ depth tăng.
- Retry queue age quá cao.
- Import job không tiến triển.
- Số item permanent failure tăng đột biến.
- Consumer lag tăng liên tục.
- Cluster indexing pressure/heap cao.

## 21. Kiểm thử bulk ingestion

Test nên bao gồm cả thành công và partial failure.

### 21.1. Test batch thành công

1. Tạo index và mapping.
2. Tạo 3–5 document.
3. Gọi bulkIndex.
4. Refresh index nếu test search ngay.
5. Xác nhận document tồn tại và field đúng.

### 21.2. Test mapping error ở một document

Tạo batch có một document sai kiểu field:

~~~text
product-1 price = 1000
product-2 price = "not-a-number"
product-3 price = 2000
~~~

Xác nhận:

- Item hợp lệ được index.
- Item sai mapping xuất hiện trong failedDocuments hoặc BulkResponse item error.
- Batch không bị coi là transaction rollback.
- Source record sai được đưa DLQ/rejected queue.

### 21.3. Test chỉ retry item transient

Mock BulkResponse hoặc retry classifier:

- 429 được retry.
- 400 mapping error được DLQ.
- 403 không retry liên tục.
- 409 được xử lý theo version/duplicate semantics.

Xác nhận retry queue chỉ chứa đúng item cần retry.

### 21.4. Test timeout ambiguous outcome

Mô phỏng transport timeout sau khi server có thể đã nhận request. Gửi lại snapshot với stable ID và xác nhận không tạo document trùng.

Với delta operation, test phải chứng minh dedup/version guard ngăn áp dụng hai lần.

### 21.5. Test batch boundary

Kiểm tra:

- Ít hơn batch size.
- Đúng batch size.
- Batch size + 1.
- Document lớn bất thường.
- Batch có một record không hợp lệ.
- Batch rỗng.

Không tạo một integration test cực lớn cho mọi boundary; có thể unit test partitioner và dùng integration test nhỏ để xác nhận semantics Elasticsearch.

### 21.6. Test message acknowledgement

Xác nhận offset/ack không tiến qua record chưa được xử lý hoặc chưa được ghi DLQ. Kiểm tra trường hợp một partition có record lỗi và partition khác vẫn tiến triển.

### 21.7. Test shutdown

Với BulkIngester hoặc background batch worker, kiểm tra shutdown flush pending operations hoặc lưu checkpoint để lần khởi động sau tiếp tục.

## 22. Ví dụ BatchIndexer hoàn chỉnh với Spring Data

Ví dụ service minh họa:

~~~java
@Service
public class ProductBatchIndexer {

    private static final int BATCH_SIZE = 500;

    private final ElasticsearchOperations operations;
    private final ProductMapper mapper;
    private final FailedItemHandler failedItemHandler;

    public ProductBatchIndexer(
            ElasticsearchOperations operations,
            ProductMapper mapper,
            FailedItemHandler failedItemHandler) {
        this.operations = operations;
        this.mapper = mapper;
        this.failedItemHandler = failedItemHandler;
    }

    public void index(List<ProductInput> inputs) {
        for (int start = 0; start < inputs.size(); start += BATCH_SIZE) {
            int end = Math.min(start + BATCH_SIZE, inputs.size());
            processBatch(inputs.subList(start, end));
        }
    }

    private void processBatch(List<ProductInput> batch) {
        Map<String, ProductInput> inputById = new HashMap<>();
        List<IndexQuery> queries = new ArrayList<>();

        for (ProductInput input : batch) {
            ProductDocument document = mapper.toDocument(input);
            inputById.put(document.getId(), input);

            queries.add(IndexQuery.builder()
                    .withId(document.getId())
                    .withObject(document)
                    .build());
        }

        try {
            operations.bulkIndex(
                    queries,
                    BulkOptions.defaultOptions(),
                    IndexCoordinates.of("products"));
        } catch (BulkFailureException exception) {
            exception.getFailedDocuments().forEach((id, failure) -> {
                ProductInput original = inputById.get(id);
                failedItemHandler.handle(
                        original,
                        id,
                        failure.status(),
                        failure.errorMessage());
            });
        }
    }
}
~~~

Đây là skeleton để minh họa ranh giới xử lý. Production cần bổ sung:

- Validate input trước khi tạo query.
- Bảo đảm ID không trùng trong batch.
- Phân loại lỗi theo status/reason.
- Retry queue và DLQ bền vững.
- Checkpoint/ack semantics.
- Xử lý lỗi request-level ngoài BulkFailureException.
- Metrics và structured logs.
- Giới hạn payload bytes, không chỉ số lượng.
- Reconciliation khi timeout khiến outcome không rõ.

Nếu chỉ dùng BulkFailureException, FailureDetails không có error type riêng. Khi cần phân loại sâu hơn, chuyển sang BulkResponse từ Elasticsearch Java API Client.

## 23. Ví dụ xử lý từng item với BulkResponse

Một adapter low-level có thể trả về kết quả đã được chuẩn hóa:

~~~java
public record BulkItemOutcome(
        String sourceId,
        String documentId,
        boolean success,
        Integer status,
        String errorType,
        String errorReason) {
}
~~~

Gửi request và ghép response:

~~~java
public List<BulkItemOutcome> indexBatch(List<ProductInput> inputs) {
    BulkResponse response = elasticsearchClient.bulk(request -> {
        request.index("products");

        for (ProductInput input : inputs) {
            ProductDocument document = mapper.toDocument(input);

            request.operations(operation -> operation
                    .index(index -> index
                            .index("products")
                            .id(document.getId())
                            .document(document)));
        }

        return request;
    });

    List<BulkItemOutcome> outcomes = new ArrayList<>();

    for (int i = 0; i < response.items().size(); i++) {
        ProductInput input = inputs.get(i);
        BulkResponseItem item = response.items().get(i);

        if (item.error() == null) {
            outcomes.add(new BulkItemOutcome(
                    input.sourceId(),
                    item.id(),
                    true,
                    item.status(),
                    null,
                    null));
        } else {
            outcomes.add(new BulkItemOutcome(
                    input.sourceId(),
                    item.id(),
                    false,
                    item.status(),
                    item.error().type(),
                    item.error().reason()));
        }
    }

    return outcomes;
}
~~~

Trong code thực tế, nên tạo operation list trước và giữ cùng một list context/source ID. Đoạn code minh họa việc response items được ghép theo thứ tự request; không sửa hoặc sort response trước khi đối chiếu.

## 24. Các lỗi thường gặp

### Chỉ kiểm tra HTTP status của bulk request

Bulk có thể trả HTTP 200 nhưng errors = true. Kiểm tra từng item.

### Coi bulk là transaction

Một số item có thể thành công trong khi item khác thất bại. Xử lý partial success.

### Retry toàn bộ batch sau một item lỗi

Tốn tài nguyên và có thể lặp delta update. Chỉ retry item phù hợp.

### Dùng ID ngẫu nhiên mỗi lần retry

Timeout/redelivery có thể tạo document trùng. Dùng deterministic ID.

### Retry mapping error

Payload vẫn sai nên retry không giải quyết được. DLQ hoặc sửa dữ liệu/mapping.

### Retry 429 ngay lập tức

Tăng tải và làm cluster khó hồi phục. Dùng backoff, jitter và giới hạn concurrency.

### Retry mọi 409

Version conflict có thể biểu thị stale event hoặc duplicate create. Xử lý theo semantics.

### Bắt BulkFailureException rồi bỏ qua

Document thất bại bị mất dấu. Đọc getFailedDocuments và lưu retry/DLQ.

### Chỉ log exception message

Không đủ để retry đúng item. Giữ document ID, source reference, status, error type và payload reference.

### Giả định BulkFailureException chứa đầy đủ error type

FailureDetails hiện hành chỉ có status và errorMessage. Dùng low-level BulkResponse nếu cần error type/reason chi tiết.

### Có nhiều operation cùng ID trong batch

Map lỗi theo ID có thể không phân biệt operation. Deduplicate batch hoặc dùng response context theo thứ tự.

### Không giới hạn bytes

500 document nhỏ và 500 document rất lớn có payload khác nhau nhiều. Giới hạn cả count lẫn byte.

### Đọc toàn bộ source vào heap

Import lớn có thể gây OutOfMemoryError. Stream dữ liệu và xử lý batch bounded.

### Concurrency quá cao

Tạo 429, queue và latency. Bắt đầu thấp, đo rồi điều chỉnh.

### Ack message trước khi lưu kết quả

Crash có thể làm mất item chưa index. Ack/commit sau khi success hoặc DLQ/retry state được lưu bền vững.

### Commit Kafka offset vượt qua record lỗi

Record lỗi có thể không được giao lại. Quản lý offset theo partition và contiguous progress.

### Bulk update delta không idempotent

Retry có thể cộng/trừ hai lần. Dùng event ID/version guard hoặc snapshot.

### Không flush BulkIngester khi shutdown

Operation còn trong buffer có thể không được gửi. Quản lý lifecycle và checkpoint.

### Refresh sau từng batch

Có thể giảm throughput. Chọn refresh policy theo yêu cầu search visibility.

### DLQ không có quy trình redrive

Item lỗi bị bỏ quên. Theo dõi DLQ depth/age và định nghĩa owner.

## 25. Quy trình nhập dữ liệu theo lô

Khi xây pipeline import:

1. Đọc source theo stream/cursor thay vì tải toàn bộ dữ liệu vào memory.
2. Validate và normalize từng record trước khi tạo IndexQuery.
3. Tạo document ID xác định từ khóa nguồn.
4. Giữ map/context giữa operation và source record.
5. Gom batch theo cả operation count và serialized bytes.
6. Gửi bulkIndex hoặc BulkIngester với concurrency có giới hạn.
7. Kiểm tra BulkFailureException hoặc từng BulkResponseItem.
8. Phân loại lỗi request-level và item-level.
9. Đánh dấu item thành công.
10. Retry chỉ lỗi transient với backoff, jitter và retry budget.
11. Ghi lỗi permanent/poison vào DLQ hoặc rejected-record store.
12. Xử lý version conflict, duplicate và ambiguous timeout theo idempotency policy.
13. Chỉ commit source checkpoint/ack khi từng record đã có kết quả bền vững.
14. Theo dõi metrics, consumer lag, retry queue và DLQ.
15. Reconcile source với Elasticsearch sau import hoặc khi outcome không rõ.
16. Refresh index theo yêu cầu visibility, không ép refresh sau mọi request.
17. Kiểm thử partial success, timeout, retry, DLQ, shutdown và replay.

## 26. Tổng kết

Bulk API giảm overhead và tăng throughput khi nhập nhiều document, nhưng mỗi action vẫn có kết quả riêng. Một bulk request có thể trả HTTP 200 trong khi một số item thất bại. Spring Data Elasticsearch cung cấp ElasticsearchOperations.bulkIndex(...) và BulkFailureException để truy cập các document lỗi; FailureDetails hiện hành chứa status và errorMessage. Khi cần error type/reason đầy đủ hoặc context theo từng operation, dùng Elasticsearch Java API Client BulkResponse hoặc BulkIngester listener.

Batch phải được giới hạn theo số operation và kích thước bytes. Không có một batch size đúng cho mọi workload; đo throughput, latency, 429 và memory để điều chỉnh. BulkIngester hỗ trợ gom operation, flush theo count/size/time và backpressure qua giới hạn request đồng thời. Reactive Spring Data có thể dùng save(Flux, type, bulkSize) để gom Flux thành các bulk operation.

Xử lý lỗi theo từng document: retry lỗi transient như 429 với exponential backoff và jitter; đưa mapping/validation errors vào DLQ; xử lý 401/403 như lỗi cấu hình/quyền; xem 409 theo version semantics; chia nhỏ request khi payload quá lớn. Timeout toàn request có thể tạo ambiguous outcome, vì vậy stable document ID, snapshot/idempotent operation, checkpoint và reconciliation rất quan trọng.

Không ack message hoặc commit source checkpoint trước khi item đã được index, được xác định là duplicate/stale theo policy, hoặc được lưu DLQ bền vững. Bulk không phải transaction; các item thành công không tự rollback khi item khác thất bại. Một pipeline tốt phải giữ liên kết từ từng source record đến operation, response, retry và DLQ để có thể khôi phục chính xác.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – DocumentOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/DocumentOperations.html)
- [Spring Data Elasticsearch – BulkFailureException API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/BulkFailureException.html)
- [Spring Data Elasticsearch – BulkFailureException.FailureDetails API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/BulkFailureException.FailureDetails.html)
- [Spring Data Elasticsearch – BulkOptions API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/BulkOptions.html)
- [Spring Data Elasticsearch – IndexQueryBuilder API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/IndexQueryBuilder.html)
- [Spring Data Elasticsearch – ReactiveDocumentOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ReactiveDocumentOperations.html)
- [Elasticsearch – Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
- [Elasticsearch Java API Client – Bulk indexing](https://www.elastic.co/docs/reference/elasticsearch/clients/java/usage/indexing-bulk)
- [Elasticsearch Java API Client – BulkIngester](https://www.elastic.co/docs/reference/elasticsearch/clients/java/usage/indexing-bulk)
- [Elasticsearch – Tune for indexing speed](https://www.elastic.co/guide/en/elasticsearch/reference/current/tune-for-indexing-speed.html)
- [Elasticsearch – Optimistic concurrency control](https://www.elastic.co/guide/en/elasticsearch/reference/current/optimistic-concurrency-control.html)
