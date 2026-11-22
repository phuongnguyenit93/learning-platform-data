# Bulk index, create, update và delete

Elasticsearch Bulk API cho phép gửi nhiều thao tác trên document trong một request. Một bulk request có thể chứa các thao tác index, create, update và delete, nhờ đó giảm số lần round-trip giữa ứng dụng và cluster khi nhập dữ liệu hoặc xử lý một tập document lớn.

Spring Data Elasticsearch cung cấp các API bulk ở mức abstraction như bulkIndex và bulkUpdate thông qua ElasticsearchOperations/DocumentOperations. Với thao tác xóa theo điều kiện, có thể dùng DeleteQuery. Khi cần bulk delete theo danh sách ID hoặc trộn create, index, update và delete trong cùng một request, ứng dụng có thể dùng Elasticsearch Java API Client trực tiếp.

Điểm cần nhớ là bulk chỉ gom các thao tác vào một request. Nó không tạo transaction ACID cho tất cả document: mỗi item có thể thành công hoặc thất bại độc lập. Vì vậy, code nhập liệu phải kiểm tra lỗi từng item, chia batch theo kích thước hợp lý, retry có chọn lọc và bảo đảm thao tác có thể chạy lại an toàn.

## 1. Bulk API giải quyết vấn đề gì?

Giả sử ứng dụng cần ghi 10.000 sản phẩm. Nếu gọi một request cho mỗi document, ứng dụng phải thực hiện hàng nghìn lượt trao đổi mạng:

~~~text
Ghi từng document:

Application -- index product 1 --> Elasticsearch
Application -- index product 2 --> Elasticsearch
Application -- index product 3 --> Elasticsearch
...
Application -- index product 10000 --> Elasticsearch
~~~

Bulk gom nhiều thao tác:

~~~text
Application
    |
    | một bulk request chứa nhiều actions
    v
Elasticsearch
    |
    +-- index product 1
    +-- index product 2
    +-- create product 3
    +-- update product 4
    +-- delete product 5
    +-- ...
~~~

Lợi ích chính:

- Giảm chi phí mạng và HTTP overhead.
- Tăng throughput khi nhập nhiều document.
- Có thể kết hợp nhiều loại thao tác trong cùng request.
- Cho phép kiểm soát pipeline, refresh policy, routing và timeout ở cấp request.
- Nhận kết quả theo từng item để biết document nào thành công hoặc thất bại.

Bulk đặc biệt hữu ích cho import dữ liệu, đồng bộ projection, cập nhật trạng thái theo batch, xử lý event và các job định kỳ.

## 2. Bốn loại thao tác trong Bulk API

Bulk API hỗ trợ bốn action chính:

| Action | Ý nghĩa | Document đã tồn tại |
|---|---|---|
| index | Ghi document; tạo mới nếu chưa có | Thay thế nội dung document theo ID |
| create | Chỉ tạo document mới | Thất bại với version conflict nếu ID đã tồn tại |
| update | Cập nhật một phần document hoặc chạy script | Cập nhật document hiện có; có thể cấu hình upsert |
| delete | Xóa document theo ID | Trả kết quả not found nếu document không tồn tại theo semantics của API |

Hai thao tác dễ nhầm là index và create:

- index phù hợp khi muốn ghi trạng thái document hiện tại và chấp nhận thay thế document cùng ID.
- create phù hợp khi chỉ được phép tạo ID chưa tồn tại; nếu ID đã có, Elasticsearch trả lỗi conflict thay vì ghi đè.

Update thường dùng partial document hoặc script. Delete chỉ cần metadata của action, không cần dòng source tiếp theo trong NDJSON.

## 3. Cấu trúc NDJSON của một bulk request

Bulk API dùng NDJSON (Newline Delimited JSON). Mỗi action có một dòng metadata; index/create/update còn có dòng payload theo sau.

Ví dụ một request có đủ bốn loại action:

~~~http
POST _bulk
{"index":{"_index":"products","_id":"p-100"}}
{"name":"Wireless Keyboard","price":1299000,"active":true}
{"create":{"_index":"products","_id":"p-101"}}
{"name":"Ergonomic Mouse","price":599000,"active":true}
{"update":{"_index":"products","_id":"p-102","retry_on_conflict":3}}
{"doc":{"price":1499000,"active":true}}
{"delete":{"_index":"products","_id":"p-103"}}
~~~

Quy tắc:

- Mỗi action bắt đầu bằng một dòng JSON metadata.
- index và create cần một dòng JSON document ngay sau action.
- update cần một dòng JSON mô tả partial document, script hoặc upsert.
- delete không có dòng payload tiếp theo.
- Các dòng phải được phân tách bằng newline.
- Request phải có newline kết thúc cuối cùng.
- Content-Type của request là application/x-ndjson.

Nếu gửi qua curl, có thể dùng file NDJSON:

~~~bash
curl -X POST "http://localhost:9200/_bulk" \
  -H "Content-Type: application/x-ndjson" \
  --data-binary "@products-bulk.ndjson"
~~~

Không dùng application/json cho body NDJSON và không serialize toàn bộ các action thành một JSON array. Bulk API yêu cầu đúng định dạng từng dòng.

## 4. Phân biệt index, create, update và delete

### 4.1. Index: tạo mới hoặc thay thế

Ví dụ:

~~~http
POST products/_bulk
{"index":{"_id":"p-100"}}
{"name":"Wireless Keyboard","price":1299000,"active":true}
~~~

Nếu p-100 chưa tồn tại, document được tạo. Nếu đã tồn tại, nội dung _source được thay thế bằng document gửi lên. Những field không có trong payload mới có thể biến mất khỏi document.

Vì vậy, index phù hợp khi ứng dụng có trạng thái đầy đủ của document.

### 4.2. Create: chỉ tạo nếu ID chưa tồn tại

~~~http
POST products/_bulk
{"create":{"_id":"p-101"}}
{"name":"Ergonomic Mouse","price":599000,"active":true}
~~~

Nếu p-101 đã tồn tại, action create thất bại với HTTP status 409 cho item đó. Các action khác trong bulk vẫn có thể tiếp tục.

Create hữu ích khi import dữ liệu mới và muốn phát hiện ID trùng thay vì âm thầm ghi đè. Đây cũng là lựa chọn phù hợp cho các luồng chỉ được append, ví dụ một số trường hợp ghi vào data stream.

### 4.3. Update: thay đổi một phần document

~~~http
POST products/_bulk
{"update":{"_id":"p-100"}}
{"doc":{"price":1399000}}
~~~

Chỉ field price được thay đổi; các field khác được giữ nguyên. Nếu document không tồn tại, update thường thất bại trừ khi cấu hình upsert.

Update có thể dùng script:

~~~http
POST products/_bulk
{"update":{"_id":"p-100","retry_on_conflict":3}}
{"script":{"source":"ctx._source.stock -= params.quantity","params":{"quantity":2}}}
~~~

Script phù hợp khi thay đổi phụ thuộc trạng thái hiện tại của document. Phải kiểm soát idempotency: chạy lại script giảm stock có thể làm giảm thêm lần nữa.

### 4.4. Delete: xóa document theo ID

~~~http
POST products/_bulk
{"delete":{"_id":"p-103"}}
~~~

Delete chỉ cần dòng metadata. Khi request dùng index ở URL, action có thể bỏ _index trong metadata. Khi dùng endpoint _bulk chung hoặc trộn nhiều index, chỉ rõ _index cho từng action.

## 5. Các API bulk trong Spring Data Elasticsearch

Trong Spring Data Elasticsearch hiện hành, các thao tác bulk ở DocumentOperations có các method chính:

| Method | Đầu vào | Kết quả |
|---|---|---|
| bulkIndex(List<IndexQuery>, Class hoặc IndexCoordinates) | Danh sách IndexQuery | Danh sách IndexedObjectInformation |
| bulkIndex(List<IndexQuery>, BulkOptions, Class hoặc IndexCoordinates) | Danh sách query và options | Danh sách IndexedObjectInformation |
| bulkUpdate(List<UpdateQuery>, Class hoặc IndexCoordinates) | Danh sách UpdateQuery | void |
| bulkUpdate(List<UpdateQuery>, BulkOptions, IndexCoordinates) | Danh sách query và options | void |
| delete(String id, IndexCoordinates) | Một document ID | ID đã xóa |
| delete(DeleteQuery, Class, IndexCoordinates) | Query xác định tập document | ByQueryResponse |

Lưu ý về delete: DocumentOperations không cung cấp method công khai có tên bulkDelete(List<...>) tương tự bulkIndex/bulkUpdate. Với nhiều ID đã biết, dùng Elasticsearch Java API Client BulkRequest hoặc REST Bulk API để gửi các delete action. Với điều kiện query, dùng DeleteQuery; thao tác này được Elasticsearch thực thi theo cơ chế delete-by-query.

Nếu cần trộn index, create, update và delete trong cùng một bulk request, Elasticsearch Java API Client là abstraction trực tiếp hơn. Không nên tự tạo một lớp tên BulkOperations rồi giả định Spring Data Elasticsearch có sẵn API đó.

## 6. Chuẩn bị entity và mapping

Ví dụ sử dụng index products:

~~~java
package com.example.catalog.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Long)
    private Long price;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    public Product() {
    }

    public Product(String id, String name, String category, Long price, Boolean active) {
        this.id = id;
        this.name = name;
        this.category = category;
        this.price = price;
        this.active = active;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public Long getPrice() {
        return price;
    }

    public Boolean getActive() {
        return active;
    }
}
~~~

Bulk không bỏ qua mapping. Nếu một item gửi string vào field long hoặc object sai cấu trúc, chỉ item đó có thể thất bại với lỗi parsing/mapping trong khi các item hợp lệ khác vẫn được ghi.

Trước khi import dữ liệu lớn, hãy tạo index và mapping đúng:

~~~http
PUT products
{
  "mappings": {
    "properties": {
      "name": {"type": "text"},
      "category": {"type": "keyword"},
      "price": {"type": "long"},
      "active": {"type": "boolean"}
    }
  }
}
~~~

Kiểm tra mapping bằng GET products/_mapping. Nếu dữ liệu mới có field hoặc kiểu không tương thích với mapping, hãy sửa schema hoặc transform dữ liệu trước khi gửi bulk.

## 7. Bulk index bằng ElasticsearchOperations

Spring Data biểu diễn một action index bằng IndexQuery. Mỗi query có thể chứa ID, object hoặc source JSON, routing, version, sequence number/primary term và operation type.

Ví dụ tạo danh sách IndexQuery:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexedObjectInformation;
import org.springframework.data.elasticsearch.core.query.BulkOptions;

public List<IndexedObjectInformation> indexProducts(
        ElasticsearchOperations operations,
        List<Product> products) {

    List<IndexQuery> queries = products.stream()
            .map(product -> IndexQuery.builder()
                    .withId(product.getId())
                    .withObject(product)
                    .build())
            .toList();

    return operations.bulkIndex(
            queries,
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("products"));
}
~~~

IndexQueryBuilder.withObject nhận object Java. Spring Data sử dụng ElasticsearchConverter để chuyển object thành JSON theo mapping metadata. Nếu cần gửi source JSON đã chuẩn bị sẵn, có thể dùng withSource thay cho withObject.

### 7.1. Chọn index hay create bằng OpType

IndexQuery.OpType có hai giá trị:

- INDEX: tạo mới hoặc thay thế document theo ID.
- CREATE: chỉ tạo nếu ID chưa tồn tại.

Ví dụ import chỉ cho phép tạo mới:

~~~java
List<IndexQuery> createQueries = products.stream()
        .map(product -> IndexQuery.builder()
                .withId(product.getId())
                .withObject(product)
                .withOpType(IndexQuery.OpType.CREATE)
                .build())
        .toList();

List<IndexedObjectInformation> created = operations.bulkIndex(
        createQueries,
        BulkOptions.defaultOptions(),
        IndexCoordinates.of("products"));
~~~

Nếu ID đã tồn tại, item create tương ứng sẽ thất bại. Spring Data báo lỗi bulk bằng BulkFailureException và cung cấp thông tin các document lỗi. Không nên tự động đổi CREATE thành INDEX khi gặp conflict nếu yêu cầu nghiệp vụ là cấm ghi đè.

### 7.2. Khi nào dùng bulkIndex và khi nào dùng saveAll?

Repository saveAll phù hợp với thao tác lưu một iterable entity theo abstraction repository. bulkIndex phù hợp khi cần kiểm soát IndexQuery, operation type, routing, version hoặc BulkOptions.

Chọn theo nhu cầu:

| Nhu cầu | Cách dùng |
|---|---|
| Lưu một entity | repository.save hoặc operations.save |
| Lưu một nhóm entity đơn giản | repository.saveAll hoặc operations.save(Iterable) |
| Bulk có CREATE/INDEX rõ ràng | bulkIndex với IndexQuery.OpType |
| Mỗi item có routing/version riêng | IndexQuery với metadata tương ứng |
| Cần BulkOptions như pipeline hoặc refresh policy | bulkIndex với BulkOptions |
| Trộn index/create/update/delete trong một request | Elasticsearch Java API Client BulkRequest |

Không nên giả định mọi overload saveAll có cùng cách chia batch hoặc cùng options với bulkIndex. Khi yêu cầu bulk cụ thể, dùng API bulk tường minh.

## 8. Bulk update bằng UpdateQuery

UpdateQuery biểu diễn một update request. Nó có thể chứa:

- ID document hoặc Query cho update-by-query.
- Partial document.
- Painless script và params.
- Upsert document.
- Routing.
- if_seq_no và if_primary_term.
- retry_on_conflict.
- Refresh policy và các tùy chọn liên quan.

Ví dụ cập nhật giá cho nhiều sản phẩm:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.BulkOptions;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

public void updatePrices(
        ElasticsearchOperations operations,
        Map<String, Long> priceByProductId) {

    List<UpdateQuery> updates = priceByProductId.entrySet().stream()
            .map(entry -> UpdateQuery.builder(entry.getKey())
                    .withDocument(Document.from(Map.of(
                            "price", entry.getValue())))
                    .build())
            .toList();

    operations.bulkUpdate(
            updates,
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("products"));
}
~~~

Mỗi UpdateQuery có ID và partial document riêng. Các field không có trong partial document được giữ nguyên. Nếu một document không tồn tại, update item đó thường thất bại trừ khi cấu hình upsert.

### 8.1. Partial document và script update

Partial document phù hợp khi ứng dụng đã biết giá trị mới:

~~~java
UpdateQuery update = UpdateQuery.builder("p-100")
        .withDocument(Document.from(Map.of(
                "price", 1399000L,
                "active", true)))
        .build();
~~~

Script phù hợp khi thay đổi phụ thuộc vào giá trị hiện tại trong document:

~~~java
UpdateQuery update = UpdateQuery.builder("p-100")
        .withScript("ctx._source.stock += params.amount")
        .withParams(Map.of("amount", 10))
        .build();
~~~

Script được thực thi trên Elasticsearch. Hãy truyền dữ liệu qua params thay vì nối chuỗi vào script. Điều này giúp tách code script khỏi dữ liệu và tránh tạo script source khác nhau cho mỗi giá trị.

### 8.2. Upsert

Nếu document có thể chưa tồn tại, có thể cấu hình partial document làm upsert:

~~~java
UpdateQuery update = UpdateQuery.builder("p-200")
        .withDocument(Document.from(Map.of(
                "name", "Vertical Mouse",
                "price", 799000L)))
        .withDocAsUpsert(true)
        .build();
~~~

doc_as_upsert nghĩa là nếu document chưa tồn tại, partial document được dùng để tạo document mới. Hãy bảo đảm partial document đủ field bắt buộc theo mapping và nghiệp vụ. Nếu document mới cần nhiều field khác, dùng withUpsert(Document) để cung cấp một source đầy đủ.

### 8.3. Retry khi có version conflict

UpdateQuery hỗ trợ withRetryOnConflict:

~~~java
UpdateQuery update = UpdateQuery.builder("p-100")
        .withDocument(Document.from(Map.of("stock", 25)))
        .withRetryOnConflict(3)
        .build();
~~~

Elasticsearch có thể retry update khi có version conflict. Retry phù hợp với thao tác gán trạng thái hoặc script được thiết kế để chạy lại an toàn. Với phép cộng/trừ, hãy hiểu rõ semantics của script và retry để tránh cập nhật sai do event được gửi lặp.

Nếu cần optimistic concurrency theo một phiên bản đã đọc, dùng if_seq_no và if_primary_term. Khi document đã thay đổi, update bị conflict để ứng dụng đọc lại và quyết định bước tiếp theo.

### 8.4. Bulk update không phải update-by-query

bulkUpdate nhận danh sách UpdateQuery, thường mỗi query gắn với một ID và một nội dung update riêng.

Update-by-query nhận một query xác định tập document và một script hoặc partial update dùng chung cho các document khớp. Trong Spring Data, có thể dùng UpdateQuery.builder(query) rồi gọi operations.updateByQuery(...).

Ví dụ update-by-query:

~~~java
CriteriaQuery selection = new CriteriaQuery(
        Criteria.where("category").is("accessories"));

UpdateQuery updateByQuery = UpdateQuery.builder(selection)
        .withScript("ctx._source.active = params.active")
        .withParams(Map.of("active", false))
        .withBatchSize(500)
        .build();

ByQueryResponse response = operations.updateByQuery(
        updateByQuery,
        IndexCoordinates.of("products"));
~~~

Chọn bulkUpdate khi đã biết từng ID và giá trị cần cập nhật. Chọn updateByQuery khi Elasticsearch có thể tìm document theo điều kiện và áp dụng cùng một thay đổi.

## 9. Xóa một document

Spring Data Elasticsearch cung cấp delete theo ID:

~~~java
String deletedId = operations.delete(
        "p-100",
        IndexCoordinates.of("products"));
~~~

Hoặc xóa qua repository:

~~~java
productRepository.deleteById("p-100");
~~~

Đây là thao tác đơn lẻ. Nếu có nhiều ID và muốn gom thành một bulk request, dùng Bulk API qua Elasticsearch Java API Client.

## 10. Xóa theo điều kiện bằng DeleteQuery

DeleteQuery biểu diễn điều kiện xóa. Spring Data chuyển thao tác này sang Elasticsearch Delete By Query API:

~~~java
import org.springframework.data.elasticsearch.core.query.ByQueryResponse;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.DeleteQuery;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

CriteriaQuery criteriaQuery = new CriteriaQuery(
        Criteria.where("active").is(false));

DeleteQuery deleteQuery = DeleteQuery.builder(criteriaQuery).build();

ByQueryResponse response = operations.delete(
        deleteQuery,
        Product.class,
        IndexCoordinates.of("products"));

long deletedCount = response.getDeleted();
~~~

Delete By Query phù hợp khi cần xóa tất cả document thỏa điều kiện, ví dụ xóa dữ liệu tạm đã hết hạn hoặc projection thuộc một tenant đã bị xóa theo chính sách.

Response ByQueryResponse có các thông tin:

- getTotal(): số document đã được xử lý.
- getDeleted(): số document đã xóa thành công.
- getBatches(): số batch scroll đã xử lý.
- getVersionConflicts(): số version conflict.
- getFailures(): lỗi ở các thao tác bulk bên trong.
- getSearchFailures(): lỗi ở giai đoạn tìm document.
- getTimedOut(): có sub-request nào timeout hay không.
- getTook(): tổng thời gian thực hiện theo millisecond.

Delete By Query không phải một thao tác nguyên tử trên toàn bộ tập document. Trong khi chạy, document có thể bị cập nhật hoặc xóa bởi writer khác; cần đọc response và xử lý conflict/failure theo nghiệp vụ.

## 11. Bulk delete theo danh sách ID

Trong API hiện hành, DocumentOperations không có bulkDelete(List<String>) công khai. Nếu cần xóa nhiều ID trong một request, dùng Elasticsearch Java API Client.

Ví dụ:

~~~java
import java.util.List;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.BulkRequest;
import co.elastic.clients.elasticsearch.core.BulkResponse;
import co.elastic.clients.elasticsearch.core.bulk.BulkResponseItem;

public void deleteProducts(
        ElasticsearchClient client,
        List<String> productIds) throws IOException {

    BulkRequest.Builder request = new BulkRequest.Builder();

    for (String id : productIds) {
        request.operations(operation -> operation
                .delete(delete -> delete
                        .index("products")
                        .id(id)));
    }

    BulkResponse response = client.bulk(request.build());

    if (response.errors()) {
        for (BulkResponseItem item : response.items()) {
            if (item.error() != null) {
                log.warn(
                        "Delete failed: index={}, id={}, status={}, reason={}",
                        item.index(),
                        item.id(),
                        item.status(),
                        item.error().reason());
            }
        }
    }
}
~~~

Ví dụ này sử dụng Elasticsearch Java API Client đã được cấu hình trong ứng dụng. Nếu dùng Spring Boot, client có thể được auto-configure tùy dependency và cấu hình; nên tái sử dụng client bean dùng chung với Spring Data thay vì tự tạo kết nối riêng.

BulkRequest có thể chứa các loại BulkOperation khác nhau. Điều đó cho phép kết hợp create, index, update và delete trong cùng request khi use case cần. Nếu chỉ dùng Spring Data abstraction, hãy dùng bulkIndex/bulkUpdate cho hai nhóm được hỗ trợ trực tiếp và dùng native client cho bulk delete theo ID.

## 12. Kết hợp nhiều action trong một bulk request

NDJSON có thể trộn các action theo thứ tự:

~~~http
POST _bulk
{"create":{"_index":"products","_id":"p-201"}}
{"name":"USB Hub","price":299000,"active":true}
{"index":{"_index":"products","_id":"p-202"}}
{"name":"Laptop Stand","price":499000,"active":true}
{"update":{"_index":"products","_id":"p-203","retry_on_conflict":3}}
{"doc":{"price":549000}}
{"delete":{"_index":"products","_id":"p-204"}}
~~~

Bulk Java Client biểu diễn mỗi action bằng một biến thể của BulkOperation:

- operation.create(...)
- operation.index(...)
- operation.update(...)
- operation.delete(...)

Mỗi item có thể nhắm tới một index cụ thể. Đây là cách phù hợp khi một luồng ingest cần ghi vào nhiều index hoặc thực hiện các action khác loại trong cùng batch.

Tuy nhiên, trộn nhiều loại action làm việc kiểm tra và retry phức tạp hơn. Hãy giữ correlation giữa action và dữ liệu nguồn, chẳng hạn lưu index, ID, operation type và event ID cho từng item.

## 13. BulkOptions

BulkOptions cung cấp các tùy chọn chung cho bulkIndex và bulkUpdate:

| Tùy chọn | Ý nghĩa |
|---|---|
| withRefreshPolicy | Chính sách refresh sau bulk |
| withTimeout | Thời gian chờ các điều kiện request |
| withWaitForActiveShards | Số shard copy cần active trước khi tiếp tục |
| withPipeline | Ingest pipeline áp dụng cho request |
| withRoutingId | Routing ID chung cho request |

Ví dụ:

~~~java
import java.time.Duration;

import org.springframework.data.elasticsearch.core.RefreshPolicy;
import org.springframework.data.elasticsearch.core.query.BulkOptions;

BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.NONE)
        .withTimeout(Duration.ofSeconds(60))
        .withWaitForActiveShards(ActiveShardCount.ONE)
        .withPipeline("normalize-product")
        .build();
~~~

Sau đó truyền options vào bulkIndex hoặc bulkUpdate:

~~~java
operations.bulkIndex(
        indexQueries,
        options,
        IndexCoordinates.of("products"));
~~~

BulkOptions không phải nơi cấu hình nội dung từng document. Những thông tin như ID, object, routing riêng hoặc version của một item nằm trong IndexQuery/UpdateQuery tương ứng.

### 13.1. Refresh policy

Refresh quyết định khi nào dữ liệu vừa ghi có thể được nhìn thấy qua search:

| Policy | Hành vi |
|---|---|
| NONE | Không yêu cầu refresh riêng sau request |
| IMMEDIATE | Refresh ngay các shard liên quan sau request |
| WAIT_UNTIL | Chờ lần refresh kế tiếp làm dữ liệu hiển thị |

Với import lớn, thường tránh IMMEDIATE cho từng batch vì refresh quá thường xuyên làm giảm throughput indexing. Nếu ứng dụng cần search nhìn thấy dữ liệu sau khi import xong, có thể chọn WAIT_UNTIL hoặc chủ động refresh một lần sau giai đoạn ghi.

Refresh chỉ liên quan tới search visibility. Nó không biến bulk thành transaction và không bảo đảm các index khác đã được cập nhật.

### 13.2. Ingest pipeline

BulkOptions có thể chọn ingest pipeline:

~~~java
BulkOptions options = BulkOptions.builder()
        .withPipeline("normalize-product")
        .build();
~~~

Pipeline có thể chuẩn hóa dữ liệu, thêm field dẫn xuất hoặc xử lý timestamp trước khi document được lập chỉ mục. Nếu pipeline làm thay đổi source, hãy kiểm tra kết quả sau ingest và bảo đảm pipeline áp dụng nhất quán giữa import, update và các luồng ghi khác.

### 13.3. Routing

Nếu index dùng custom routing, thao tác phải cung cấp đúng routing value để document đến đúng shard. Routing có thể được đặt trên từng IndexQuery hoặc UpdateQuery. BulkOptions.withRoutingId dùng một routing ID chung khi tất cả thao tác trong request chia sẻ cùng giá trị.

Nếu một batch chứa nhiều tenant hoặc nhiều routing key, hãy gắn routing riêng cho từng item thay vì dùng một routing ID chung cho cả request. Khi đọc, update hoặc delete, routing cũng phải được truyền đúng.

## 14. Kiểm tra kết quả và BulkFailureException

Một bulk request có thể trả HTTP status thành công ở cấp request nhưng vẫn có item thất bại. Vì vậy, không được chỉ kiểm tra request có ném exception hay không hoặc HTTP status có phải 200 hay không.

Trong Elasticsearch Bulk API response:

- errors = false nghĩa là mọi item hoàn tất thành công.
- errors = true nghĩa là ít nhất một item thất bại.
- items chứa kết quả theo đúng thứ tự action gửi lên.
- Mỗi item có status, result hoặc error tùy kết quả.

Ví dụ response rút gọn:

~~~json
{
  "errors": true,
  "items": [
    {
      "index": {
        "_index": "products",
        "_id": "p-201",
        "status": 201,
        "result": "created"
      }
    },
    {
      "create": {
        "_index": "products",
        "_id": "p-202",
        "status": 409,
        "error": {
          "type": "version_conflict_engine_exception",
          "reason": "document already exists"
        }
      }
    }
  ]
}
~~~

Spring Data bulkIndex và bulkUpdate có thể ném BulkFailureException khi có thao tác thất bại. Exception cung cấp getFailedDocuments(), một map từ document ID tới FailureDetails gồm status và errorMessage.

Ví dụ:

~~~java
import org.springframework.data.elasticsearch.BulkFailureException;

try {
    operations.bulkIndex(
            indexQueries,
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("products"));
} catch (BulkFailureException exception) {
    exception.getFailedDocuments().forEach((id, failure) -> {
        log.warn(
                "Bulk item failed: id={}, status={}, error={}",
                id,
                failure.status(),
                failure.errorMessage());
    });

    throw exception;
}
~~~

Các item thành công không tự động rollback khi có item thất bại. Exception là tín hiệu để ứng dụng ghi nhận lỗi và phục hồi, không phải bằng chứng rằng toàn bộ batch chưa được ghi.

## 15. Phân loại lỗi và retry

Không phải lỗi nào cũng nên retry:

| Lỗi | Ví dụ status | Hướng xử lý |
|---|---:|---|
| ID create đã tồn tại | 409 | Kiểm tra duplicate; không retry mù |
| Version conflict | 409 | Đọc version mới hoặc retry theo chính sách concurrency |
| Mapping/parsing error | 400 | Sửa dữ liệu hoặc mapping; retry nguyên payload không giải quyết được |
| Rejected execution / quá tải | 429 | Retry có backoff và giảm tốc độ gửi |
| Service unavailable / lỗi tạm thời | 5xx | Retry có giới hạn sau khi kiểm tra cluster |
| Authentication/authorization | 401/403 | Sửa credential hoặc quyền |
| Document missing khi update | 404 | Kiểm tra vòng đời document; dùng upsert nếu đúng nghiệp vụ |

### 15.1. Retry có chọn lọc

Với bulk response từ Java client, chỉ đưa các item lỗi tạm thời vào batch retry. Không gửi lại tất cả action vì một số item có thể đã thành công.

Với BulkFailureException của Spring Data, dùng map failedDocuments để biết ID và lỗi. Nếu cần biết đầy đủ operation type hoặc payload gốc, ứng dụng nên giữ một correlation map từ ID sang command/event đầu vào.

### 15.2. Exponential backoff

Khi cluster trả 429 hoặc lỗi tạm thời, retry ngay liên tục có thể làm tình trạng quá tải nặng hơn. Có thể dùng exponential backoff với jitter:

~~~text
delay = min(maxDelay, baseDelay * 2^attempt) + randomJitter
~~~

Ví dụ cấu hình minh họa:

| Lần thử | Delay cơ sở |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.600 ms |
| 5 | 3.200 ms |

Đặt giới hạn số lần thử và tổng thời gian retry. Khi vượt ngưỡng, ghi item vào dead-letter queue hoặc bảng lỗi để có thể xử lý lại sau.

### 15.3. Idempotency

Retry an toàn nhất khi action có thể chạy lại mà không làm sai trạng thái:

- Index cùng một ID với cùng payload thường hội tụ về cùng source.
- Create cùng ID lần hai sẽ conflict; cần phân biệt duplicate hợp lệ với lỗi.
- Partial update gán một giá trị cụ thể thường dễ retry hơn script cộng/trừ.
- Delete cùng ID có thể gặp not found ở lần chạy sau; quyết định xem đó là thành công theo trạng thái cuối hay là lỗi cần ghi nhận.
- Script tăng counter không idempotent nếu event bị gửi lại.

Với event-driven ingestion, nên có event ID/version và ghi nhận item nào đã hoàn tất. Đừng chỉ đánh dấu cả batch thành công khi một phần item đã lỗi.

## 16. Chia batch theo kích thước

Không nên đưa toàn bộ dữ liệu hàng triệu document vào một List rồi gửi trong một bulk request. Batch quá lớn có thể gây:

- Tăng heap ở ứng dụng.
- Request body lớn, tăng áp lực mạng.
- Node nhận request phải giữ nhiều dữ liệu và xử lý nhiều action.
- Thời gian xử lý dài, tăng xác suất timeout.
- Khi lỗi, việc xác định và retry phần nhỏ trở nên khó hơn.

Batch quá nhỏ lại làm tăng overhead và giảm throughput. Cần đo bằng dữ liệu gần production.

### 16.1. Chia theo số item

Ví dụ xử lý theo lô:

~~~java
int batchSize = 500;

for (int start = 0; start < products.size(); start += batchSize) {
    int end = Math.min(start + batchSize, products.size());
    List<Product> batch = products.subList(start, end);

    indexBatch(operations, batch);
}
~~~

500 chỉ là giá trị minh họa. Tùy kích thước JSON, số field, pipeline, shard count và tải cluster, batch phù hợp có thể khác đáng kể.

### 16.2. Theo dõi kích thước byte

Số lượng item không phản ánh đầy đủ kích thước request. 500 document nhỏ có thể nhẹ hơn 20 document chứa nội dung lớn.

Nên theo dõi:

- Số item mỗi batch.
- Kích thước NDJSON theo byte.
- Thời gian request.
- Số item lỗi và loại lỗi.
- CPU, heap, indexing pressure và thread pool của cluster.

Tăng batch size từ từ, đo throughput và latency, sau đó dừng khi throughput không tăng hoặc cluster bắt đầu có dấu hiệu quá tải.

### 16.3. Giới hạn concurrency

Gửi nhiều bulk request song song có thể tăng throughput đến một mức nhất định. Quá nhiều request đồng thời có thể làm indexing pressure và queue tăng.

Đặt giới hạn số request in-flight. Nếu dùng producer/consumer, cần backpressure để producer không đẩy dữ liệu nhanh hơn khả năng xử lý của Elasticsearch.

## 17. BulkIngester cho luồng ingest liên tục

Nếu ứng dụng liên tục tạo action thay vì đã có sẵn một danh sách batch, Elasticsearch Java API Client cung cấp BulkIngester. Component này tự gom operation, gửi bulk khi đạt ngưỡng số action/kích thước hoặc khi hết thời gian flush, đồng thời có thể giới hạn số request đồng thời.

Ví dụ khung:

~~~java
import java.util.concurrent.TimeUnit;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch._helpers.bulk.BulkIngester;

BulkIngester<Void> ingester = BulkIngester.of(builder -> builder
        .client(client)
        .maxOperations(500)
        .flushInterval(1, TimeUnit.SECONDS));

for (Product product : productStream) {
    ingester.add(operation -> operation
            .index(index -> index
                    .index("products")
                    .id(product.getId())
                    .document(product)));
}

ingester.close();
~~~

close() cần được gọi để flush các operation còn đang chờ và giải phóng tài nguyên. Trong ứng dụng chạy lâu dài, quản lý lifecycle của BulkIngester theo lifecycle của worker/service.

BulkIngester có thể nhận listener để theo dõi kết quả từng bulk execution và các context gắn với operation. Dùng listener để ghi lỗi theo ID/event và tạo retry queue. Đừng chỉ log tổng số request mà bỏ qua item failures.

BulkIngester là tiện ích của Elasticsearch Java API Client, không phải method của ElasticsearchOperations. Nếu dự án chỉ dùng các batch hữu hạn, bulkIndex/bulkUpdate của Spring Data thường đơn giản hơn.

## 18. Refresh, shard và hiệu năng indexing

### 18.1. Tránh refresh sau từng document

Refresh thường xuyên tạo nhiều segment nhỏ và làm tăng chi phí merge. Với import lớn:

1. Gửi nhiều batch với RefreshPolicy.NONE.
2. Theo dõi kết quả và lỗi.
3. Khi hoàn tất, refresh index một lần nếu cần search nhìn thấy dữ liệu ngay.

Nếu index có refresh interval phù hợp, có thể để refresh tự động xử lý visibility.

### 18.2. wait_for_active_shards

BulkOptions cho phép cấu hình số shard copy cần active trước khi request tiếp tục. Giá trị này ảnh hưởng điều kiện sẵn sàng của thao tác ghi, không phải số lượng replica sẽ được ghi bởi ứng dụng.

Chọn chính sách phù hợp với yêu cầu durability/availability. Đặt chờ tất cả shard copy có thể làm request chờ lâu nếu một replica chưa sẵn sàng.

### 18.3. Pipeline và mapping

Ingest pipeline có thể chuẩn hóa dữ liệu trước khi index. Mapping phải phù hợp với output pipeline. Nếu pipeline thêm field mới hoặc đổi kiểu dữ liệu, kiểm tra index mapping và test với payload đại diện.

### 18.4. Routing và shard distribution

Custom routing có thể giảm fan-out nếu query luôn có routing key, nhưng routing không đồng đều có thể tạo hot shard. Bulk batch có routing key tập trung vào một shard có thể làm shard đó quá tải.

Nếu dùng routing, bảo đảm cùng một document luôn được ghi, update, get và delete với routing value phù hợp.

## 19. Bulk trên alias và data stream

Bulk action có thể nhắm tới index, alias hoặc data stream. Khi dùng alias làm đích ghi, cần kiểm tra alias có write index rõ ràng nếu alias trỏ nhiều index.

Data stream có semantics append-oriented và Bulk API chỉ hỗ trợ action create cho data stream. Không gửi update hoặc delete action trực tiếp vào data stream như với index thông thường. Nếu cần sửa/xóa document cũ, cần xác định backing index và quy trình phù hợp, đồng thời xem xét lifecycle của data stream.

Khi import production, có thể dùng require_alias để buộc request ghi qua alias thay vì vô tình tạo index mới do sai tên. Đây là biện pháp hữu ích khi ứng dụng dùng alias cho index versioning.

## 20. Kiểm soát concurrency và dữ liệu cũ

Bulk request có thể chạy đồng thời với request khác. Nếu hai writer cùng cập nhật một document, kết quả phụ thuộc thứ tự ghi và concurrency control.

Các cơ chế thường dùng:

- if_seq_no và if_primary_term để chỉ cập nhật nếu document chưa thay đổi kể từ lần đọc.
- retry_on_conflict cho Update API khi muốn Elasticsearch thử lại thao tác update sau conflict.
- Version nghiệp vụ trong document/event để bỏ qua event cũ.
- Idempotent command để retry không tạo trạng thái sai.

Không nên dùng một bulk batch để ghi đè toàn bộ document nếu mỗi producer chỉ sở hữu một phần field. Dùng partial update hoặc một projection writer có quyền sở hữu rõ ràng.

Nếu bulk request có cùng ID lặp nhiều lần, thứ tự action trong request có thể ảnh hưởng trạng thái cuối. Hãy loại duplicate ID trong batch hoặc xác định rõ thứ tự mong muốn trước khi gửi.

## 21. BulkFailureException và response từ Java Client

Có hai cách đọc lỗi tùy API:

| API | Cách nhận lỗi |
|---|---|
| Spring Data bulkIndex/bulkUpdate | BulkFailureException.getFailedDocuments() |
| Elasticsearch Java API Client BulkRequest | BulkResponse.errors() và BulkResponse.items() |
| DeleteQuery / updateByQuery | ByQueryResponse.getFailures(), getSearchFailures(), getVersionConflicts(), getTimedOut() |

Khi dùng Java client, response.errors() phải được kiểm tra dù lời gọi client.bulk(...) không ném exception. Với từng item, kiểm tra error() và status().

Khi dùng Spring Data, BulkFailureException là runtime exception. Hãy bắt ở tầng có đủ thông tin để lưu failed item hoặc chuyển sang retry queue. Không nên nuốt exception và tiếp tục như thể batch đã hoàn tất.

## 22. Xử lý lỗi theo từng item

Một chiến lược thực tế:

1. Tạo command cho từng item và giữ lại ID, index, action type cùng payload.
2. Gửi batch.
3. Đọc response hoặc BulkFailureException.
4. Ghép lỗi với command gốc theo ID/correlation.
5. Retry lỗi tạm thời như 429 hoặc một số 5xx.
6. Đưa lỗi dữ liệu/mapping vào DLQ để sửa payload.
7. Xử lý conflict theo quy tắc nghiệp vụ.
8. Ghi nhận batch đã hoàn tất khi mọi item đã thành công hoặc được chuyển sang luồng lỗi có theo dõi.

Ví dụ cấu trúc record lỗi:

~~~json
{
  "batchId": "import-2026-11-13-01",
  "itemId": "p-202",
  "index": "products",
  "operation": "create",
  "attempt": 2,
  "status": 400,
  "error": "mapper_parsing_exception",
  "payloadRef": "object-storage://imports/p-202.json"
}
~~~

Với payload lớn, DLQ có thể lưu tham chiếu tới object storage thay vì sao chép toàn bộ JSON vào message.

## 23. Bulk không phải transaction

Một bulk request có thể có kết quả:

~~~text
Action 1: INDEX  -> SUCCESS
Action 2: CREATE -> CONFLICT
Action 3: UPDATE -> SUCCESS
Action 4: DELETE -> NOT FOUND
Action 5: INDEX  -> MAPPING ERROR
~~~

Elasticsearch không rollback action 1 và 3 vì action 2 và 5 thất bại. Nếu nghiệp vụ cần một nhóm thay đổi tất cả cùng thành công hoặc cùng thất bại, bulk không đáp ứng yêu cầu transaction đó.

Với dữ liệu projection hoặc search index, thường thiết kế eventual consistency, idempotency, retry và reconciliation. Nếu dữ liệu nguồn nằm trong database quan hệ, giữ transaction nghiệp vụ ở database và dùng outbox/CDC để đồng bộ Elasticsearch.

## 24. Khi nào dùng bulkIndex, bulkUpdate, DeleteQuery hay native bulk?

| Tình huống | API nên chọn |
|---|---|
| Import nhiều document đầy đủ | bulkIndex |
| Chỉ tạo mới và từ chối ID trùng | bulkIndex + OpType.CREATE |
| Ghi trạng thái đầy đủ, cho phép thay thế cùng ID | bulkIndex + OpType.INDEX |
| Mỗi document có partial fields khác nhau | bulkUpdate |
| Nhiều document nhận cùng một script theo query | updateByQuery |
| Xóa một document | delete(id, index) hoặc repository.deleteById |
| Xóa mọi document khớp điều kiện | delete(DeleteQuery, ...) |
| Xóa nhiều ID đã biết trong một request | Java API Client BulkRequest với delete actions |
| Trộn create/index/update/delete trong một request | Java API Client BulkRequest |
| Ingest liên tục theo stream với auto batching | BulkIngester |

Đừng chọn updateByQuery chỉ vì có nhiều document. Nếu mỗi document có giá trị cập nhật riêng, bulkUpdate với danh sách ID thường phù hợp hơn. Ngược lại, nếu tất cả document khớp điều kiện nhận cùng thay đổi, updateByQuery hoặc DeleteQuery tránh phải kéo danh sách ID về ứng dụng.

## 25. Kiểm thử bulk

Một integration test với Elasticsearch thật hoặc Testcontainers nên kiểm tra:

- Index tạo document mới.
- Index cùng ID thay thế document hiện tại.
- Create cùng ID lần hai trả conflict.
- Update chỉ thay đổi field được gửi.
- Update document không tồn tại thất bại nếu không upsert.
- Update với doc_as_upsert tạo document khi thiếu.
- Delete theo ID xóa đúng document.
- DeleteQuery chỉ xóa document thỏa điều kiện.
- Một item mapping error không làm mất kết quả của item hợp lệ khác.
- Bulk response có errors=true khi một item thất bại.
- BulkFailureException chứa ID và thông tin lỗi.
- Routing được áp dụng đúng khi index dùng custom routing.
- Refresh policy phù hợp với cách test đọc lại dữ liệu.

### 25.1. Test create và index semantics

Ví dụ kiểm thử logic:

~~~java
@Test
void createDoesNotOverwriteExistingDocument() {
    operations.save(new Product(
            "p-100", "Original Keyboard", "accessories", 1000L, true),
            IndexCoordinates.of("products"));

    IndexQuery create = IndexQuery.builder()
            .withId("p-100")
            .withObject(new Product(
                    "p-100", "New Keyboard", "accessories", 2000L, true))
            .withOpType(IndexQuery.OpType.CREATE)
            .build();

    assertThatThrownBy(() -> operations.bulkIndex(
            List.of(create),
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("products")))
            .isInstanceOf(BulkFailureException.class);
}
~~~

Đây là ví dụ kiểm thử integration; setup index, refresh và cleanup cần được bổ sung theo cấu hình Testcontainers của dự án.

### 25.2. Kiểm thử partial update

Tạo document có nhiều field, chạy UpdateQuery chỉ đổi price, sau đó đọc lại theo ID và xác nhận name/category vẫn giữ nguyên. Test này phát hiện trường hợp dùng index/save nhầm khi muốn partial update.

### 25.3. Kiểm thử lỗi một phần

Gửi một batch có:

- Một document hợp lệ.
- Một document có kiểu field sai.
- Một create có ID đã tồn tại.

Xác nhận document hợp lệ vẫn được ghi, các item lỗi được báo trong BulkFailureException hoặc BulkResponse. Không chỉ assert tổng request thành công/thất bại.

## 26. Các lỗi thường gặp

### Nghĩ HTTP 200 nghĩa là mọi item thành công

Bulk response có thể trả HTTP 200 nhưng errors=true. Hãy kiểm tra errors và từng item.

### Dùng index khi chỉ muốn create

Index sẽ thay thế document cùng ID. Dùng OpType.CREATE nếu phải từ chối ID đã tồn tại.

### Dùng create khi cần upsert

Create không cập nhật document cũ. Nếu cần tạo mới hoặc thay thế, dùng index; nếu cần partial update/upsert, dùng update với cấu hình upsert.

### Gửi full entity thiếu field

Bulk index thay thế document theo ID. Nếu entity không chứa đầy đủ source, field cũ có thể mất. Dùng bulkUpdate cho partial changes.

### Gửi một batch quá lớn

Request lớn làm tăng heap, indexing pressure và nguy cơ timeout. Chia batch theo cả số item lẫn byte.

### Retry toàn bộ bulk khi một item lỗi

Các item thành công có thể bị chạy lại. Với create có thể conflict; với script cộng dồn có thể cập nhật hai lần. Retry riêng item lỗi và thiết kế action idempotent.

### Không giữ correlation giữa item và payload

Khi nhận lỗi, ứng dụng không biết document nào cần sửa. Giữ ID, action type và event/batch ID để đối chiếu.

### Dùng refresh IMMEDIATE cho mọi batch

Refresh thường xuyên làm giảm indexing throughput. Chỉ refresh khi yêu cầu search visibility cần thiết.

### Dùng routing không nhất quán

Document được ghi bằng routing nhưng update/delete không có routing phù hợp có thể không tìm thấy document. Đưa routing vào command và truyền nhất quán.

### Giả định Spring Data có bulkDelete

DocumentOperations hiện hành có bulkIndex và bulkUpdate, nhưng không có bulkDelete theo danh sách ID. Dùng DeleteQuery cho xóa theo query hoặc native BulkRequest cho delete actions theo ID.

### Dùng DeleteQuery như thao tác nguyên tử

Delete-by-query xử lý theo batch, có thể gặp version conflict và failure. Đọc ByQueryResponse và thiết kế phục hồi.

### Quên giới hạn data stream

Data stream chỉ hỗ trợ create action trong bulk. Không gửi update/delete như với index thường.

## 27. Quy trình triển khai một job bulk

Khi xây job import hoặc đồng bộ dữ liệu:

1. Xác định index/alias/data stream đích và mapping đã được tạo.
2. Xác định action type: create, index, update hoặc delete.
3. Xác định ID và routing cho từng item.
4. Chuẩn hóa dữ liệu và validate trước khi gửi.
5. Tạo IndexQuery/UpdateQuery hoặc BulkOperation.
6. Chia batch theo số item và kích thước byte.
7. Cấu hình BulkOptions như refresh policy, pipeline, timeout và active shards nếu dùng Spring Data.
8. Giới hạn số bulk request đồng thời.
9. Gửi batch và kiểm tra lỗi từng item.
10. Retry có chọn lọc với backoff; đưa lỗi lâu dài vào DLQ.
11. Ghi nhận số item thành công, lỗi, retry và thời gian xử lý.
12. Refresh sau batch nếu cần search nhìn thấy dữ liệu ngay.
13. Chạy đối soát số lượng và trạng thái document sau import.
14. Lưu checkpoint để job có thể tiếp tục sau khi process restart.

## 28. Tổng kết

Bulk API gom nhiều thao tác document vào một request và hỗ trợ bốn action: index, create, update và delete. Index tạo mới hoặc thay thế document; create chỉ tạo khi ID chưa tồn tại; update thay đổi một phần source hoặc chạy script; delete xóa document theo ID. NDJSON yêu cầu một dòng metadata cho mỗi action và dòng payload cho index/create/update, còn delete không có payload line.

Spring Data Elasticsearch cung cấp bulkIndex với IndexQuery và bulkUpdate với UpdateQuery. IndexQuery.OpType phân biệt CREATE và INDEX. BulkOptions điều khiển refresh policy, timeout, active shards, pipeline và routing chung. Với delete, Spring Data hỗ trợ delete theo ID và DeleteQuery để xóa theo điều kiện; DocumentOperations hiện hành không có bulkDelete(List<ID>) công khai. Khi cần bulk delete theo ID hoặc trộn mọi loại action, dùng Elasticsearch Java API Client BulkRequest hoặc REST Bulk API.

Bulk không phải transaction nhiều document. Một request có thể thành công một phần; phải kiểm tra errors và item failures, không retry mù toàn bộ batch. Chia batch theo số item và byte, giới hạn concurrency, chọn refresh phù hợp, giữ correlation với payload, retry lỗi tạm thời có backoff và thiết kế thao tác idempotent. Những nguyên tắc này giúp job bulk có throughput tốt mà vẫn có thể phục hồi khi mapping lỗi, version conflict, timeout hoặc cluster quá tải.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – DocumentOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/DocumentOperations.html)
- [Spring Data Elasticsearch – IndexQuery API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/IndexQuery.html)
- [Spring Data Elasticsearch – IndexQueryBuilder API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/IndexQueryBuilder.html)
- [Spring Data Elasticsearch – UpdateQuery API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/UpdateQuery.html)
- [Spring Data Elasticsearch – UpdateQuery.Builder API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/UpdateQuery.Builder.html)
- [Spring Data Elasticsearch – DeleteQuery API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/DeleteQuery.html)
- [Spring Data Elasticsearch – BulkOptions API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/BulkOptions.html)
- [Spring Data Elasticsearch – BulkFailureException API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/BulkFailureException.html)
- [Elasticsearch – Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
- [Elasticsearch Java API Client – Bulk indexing](https://www.elastic.co/docs/reference/elasticsearch/clients/java/usage/indexing-bulk)
- [Elasticsearch – Update By Query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update-by-query)
- [Elasticsearch – Delete By Query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete-by-query)
