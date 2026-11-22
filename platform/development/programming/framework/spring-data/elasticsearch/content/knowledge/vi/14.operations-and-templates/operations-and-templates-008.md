# Thao tác cập nhật, bulk và reindex qua API thích hợp

Spring Data Elasticsearch cung cấp nhiều cách ghi và thay đổi document: lưu entity, cập nhật một phần, cập nhật theo điều kiện, gửi nhiều thao tác trong một bulk request và sao chép dữ liệu sang index khác bằng reindex. Những thao tác này có mục tiêu khác nhau. Chọn sai API có thể ghi đè các field không chủ ý, tạo nhiều request không cần thiết hoặc làm mất dữ liệu trong quá trình chuyển đổi index.

Bài học này trình bày cách chọn API theo phạm vi công việc, cách dùng `ElasticsearchOperations`/`DocumentOperations` để cập nhật document, cách chạy bulk index và bulk update, cách dùng Update By Query và Reindex API, cũng như cách kiểm soát lỗi, xung đột phiên bản, refresh và migration alias.

## 1. Chọn đúng thao tác

Trước khi viết code, hãy xác định mục tiêu:

| Nhu cầu | API phù hợp | Phạm vi |
|---|---|---|
| Ghi mới hoặc thay thế toàn bộ document theo ID | `save(entity)` hoặc `index(...)` | Một document |
| Chỉ thay đổi một vài field của document | `update(entity)` hoặc `update(UpdateQuery, index)` | Một document |
| Cập nhật nhiều document theo cùng điều kiện | `updateByQuery(...)` | Các document khớp query trong index |
| Gửi nhiều thao tác index/update trong một lần gọi | `bulkIndex(...)`, `bulkUpdate(...)` hoặc Bulk API | Nhiều document được chỉ định |
| Chép dữ liệu sang index khác, thường để đổi mapping/settings | `reindex(...)` hoặc `_reindex` | Một tập document từ nguồn sang đích |

Các API có thể trông giống nhau vì đều làm thay đổi dữ liệu, nhưng semantics khác nhau:

- `save` ghi document theo kiểu index, thường thay thế nội dung `_source` hiện có bằng nội dung entity được gửi.
- `update` dùng Elasticsearch Update API để áp dụng partial document hoặc script lên document đã có.
- `updateByQuery` tìm một tập document rồi áp dụng cùng một update/script cho từng document.
- `bulk` gom nhiều action độc lập vào một request để giảm round-trip.
- `reindex` đọc document từ nguồn rồi ghi sang một index đích khác; nó không sửa index nguồn.

## 2. Các abstraction của Spring Data Elasticsearch

Spring Data chia API thao tác Elasticsearch thành các interface theo nhóm:

| Interface | Trách nhiệm chính |
|---|---|
| `DocumentOperations` | Lưu, đọc, cập nhật, xóa document theo ID; bulk và reindex |
| `SearchOperations` | Tìm kiếm nhiều document bằng query |
| `IndexOperations` | Tạo/xóa index, đọc và cập nhật mapping/settings, alias |
| `ElasticsearchOperations` | Kết hợp các abstraction thao tác document, search và một số tiện ích chung |

Trong ứng dụng Spring Boot, có thể inject `ElasticsearchOperations`:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductDataService {

    private final ElasticsearchOperations operations;

    public ProductDataService(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
```

`ElasticsearchOperations` cung cấp cách thao tác độc lập với repository. Repository vẫn phù hợp cho CRUD và query method thông thường; operations phù hợp khi cần điều khiển rõ `UpdateQuery`, bulk options, reindex hoặc query phức tạp.

Từ Spring Data Elasticsearch 4.0, `DocumentOperations` và `SearchOperations` được tách thành các interface chuyên trách; `ElasticsearchOperations` kết hợp chúng. Các method được bổ sung qua nhiều release train, vì vậy hãy đối chiếu Javadoc của phiên bản dependency mà Spring Boot đang quản lý.

## 3. Phân biệt `save` và `update`

### 3.1. `save` ghi toàn bộ document

Ví dụ entity:

```java
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
    private Long priceInCents;

    // Constructors, getters and setters
}
```

Lưu entity:

```java
Product product = new Product("p-100", "Mechanical Keyboard", "accessories", 1299000L);
Product saved = operations.save(product);
```

`save` sử dụng index operation của Elasticsearch. Nếu document có ID đã tồn tại, nội dung document được ghi mới sẽ thay thế `_source` hiện tại cho ID đó. Nếu chưa tồn tại, document được tạo. Đây là lựa chọn đúng khi entity đại diện cho trạng thái đầy đủ mà ứng dụng muốn lưu.

Điểm cần nhớ: nếu `_source` hiện tại có field được một hệ thống khác bổ sung, việc index lại entity không chứa field đó có thể làm field ấy biến mất khỏi document mới. Khi chỉ muốn thay đổi một vài field, hãy dùng partial update.

### 3.2. `update(entity)` cập nhật một phần

`DocumentOperations` có method `update(entity)` để cập nhật một document một phần dựa trên entity. Ví dụ:

```java
Product patch = new Product();
patch.setId("p-100");
patch.setPriceInCents(1399000L);

operations.update(patch);
```

API này được bổ sung từ Spring Data Elasticsearch 5.0. Cách chuyển đổi entity thành partial document phụ thuộc mapping converter và phiên bản thư viện. Khi cần kiểm soát chính xác field nào được gửi, `UpdateQuery` với `Document` tường minh thường dễ hiểu hơn.

Không giả định rằng một entity thiếu giá trị sẽ luôn được xử lý theo cách bạn mong muốn. Hãy xác định cách converter xử lý field `null`, field không có giá trị và nested object. Nếu cần bảo đảm chỉ một field được cập nhật, hãy tạo partial document chỉ chứa field đó.

### 3.3. Elasticsearch Update API làm gì?

Update API cho phép gửi một phần document (`doc`) hoặc một script. Ở phía Elasticsearch, thao tác cập nhật được thực hiện theo cơ chế đọc document hiện tại, áp dụng thay đổi rồi ghi document mới. Nó không sửa một vài byte trực tiếp bên trong segment Lucene.

REST API ví dụ:

```http
POST products/_update/p-100
{
  "doc": {
    "priceInCents": 1399000
  }
}
```

Các field không xuất hiện trong `doc` được giữ nguyên. Nếu document không tồn tại, Update API thường trả lỗi document missing trừ khi request có cấu hình upsert.

## 4. Dùng `UpdateQuery` để cập nhật một document

`UpdateQuery` biểu diễn một update request. Có thể tạo query theo ID và truyền partial document bằng `Document`.

```java
import java.util.Map;

import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;
import org.springframework.data.elasticsearch.core.query.UpdateResponse;

UpdateQuery updateQuery = UpdateQuery.builder("p-100")
        .withDocument(Document.from(Map.of(
                "priceInCents", 1399000L,
                "category", "mechanical-keyboards")))
        .build();

UpdateResponse response = operations.update(
        updateQuery,
        IndexCoordinates.of("products"));
```

`Document.from(Map)` tạo partial document từ các cặp key-value. Trong ví dụ, chỉ `priceInCents` và `category` được gửi trong phần document update. Các field khác của sản phẩm không bị thay thế bằng `null` chỉ vì object Java không có giá trị.

`UpdateQuery.builder(String id)` dùng cho cập nhật một document theo ID. `operations.update(updateQuery, index)` thực hiện partial update và trả về `UpdateResponse`.

### 4.1. Upsert khi document chưa tồn tại

Nếu muốn tạo document khi chưa có, có thể dùng `doc_as_upsert`:

```java
UpdateQuery updateOrInsert = UpdateQuery.builder("p-200")
        .withDocument(Document.from(Map.of(
                "name", "Wireless Mouse",
                "category", "accessories",
                "priceInCents", 499000L)))
        .withDocAsUpsert(true)
        .build();

operations.update(updateOrInsert, IndexCoordinates.of("products"));
```

Khi document chưa tồn tại, phần `doc` được dùng để tạo document mới. Khi đã tồn tại, các field trong `doc` được áp dụng như partial update.

Một cách khác là truyền `upsert` riêng bằng `withUpsert(Document)`. Cách này hữu ích khi nội dung cần tạo mới khác với phần document dùng để cập nhật.

```java
UpdateQuery updateQuery = UpdateQuery.builder("p-201")
        .withDocument(Document.from(Map.of("lastSeenAt", "2026-11-13T10:00:00Z")))
        .withUpsert(Document.from(Map.of(
                "name", "New Device",
                "status", "NEW",
                "lastSeenAt", "2026-11-13T10:00:00Z")))
        .build();
```

Hãy bảo đảm nội dung upsert có đủ các field bắt buộc theo mapping và quy tắc nghiệp vụ. Không bật upsert chỉ để tránh xử lý lỗi ID sai; nó có thể tạo document ngoài dự kiến.

### 4.2. Cập nhật bằng Painless script

Khi muốn thực hiện phép tính dựa trên giá trị hiện tại của document, script phù hợp hơn việc đọc document về Java, sửa rồi ghi lại.

Ví dụ tăng số lượt xem:

```java
import java.util.Map;

UpdateQuery incrementViews = UpdateQuery.builder("p-100")
        .withScript("ctx._source.viewCount += params.delta")
        .withParams(Map.of("delta", 1))
        .build();

operations.update(incrementViews, IndexCoordinates.of("products"));
```

Script chạy tại Elasticsearch, dùng `params` để truyền dữ liệu. Không nối chuỗi đầu vào của người dùng trực tiếp vào script. Dùng tham số giúp tách code khỏi dữ liệu và giảm rủi ro lỗi hoặc injection.

Có thể dùng script để thêm/xóa field, tính giá trị mới hoặc bỏ qua document nếu không cần thay đổi. Script cần tương thích với Painless và cấu trúc `_source` thực tế.

### 4.3. Optimistic concurrency control

Nếu nhiều tiến trình có thể cập nhật cùng document, cần tránh ghi đè thay đổi của nhau. Elasticsearch cung cấp `seq_no` và `primary_term` để kiểm soát phiên bản document.

Một request update có thể yêu cầu chỉ cập nhật nếu document vẫn ở sequence number và primary term đã đọc trước đó:

```java
UpdateQuery guardedUpdate = UpdateQuery.builder("p-100")
        .withDocument(Document.from(Map.of("priceInCents", 1499000L)))
        .withIfSeqNo(42L)
        .withIfPrimaryTerm(3L)
        .build();
```

Nếu document đã thay đổi sau lần đọc, Elasticsearch trả version conflict thay vì âm thầm ghi đè. Ứng dụng có thể đọc lại, tính toán lại và thử lần nữa theo quy tắc nghiệp vụ.

`withRetryOnConflict(n)` là cơ chế khác: yêu cầu Elasticsearch thử lại update khi có conflict. Nó phù hợp với một số update script có thể chạy lại an toàn. Không dùng retry mù quáng cho script không idempotent hoặc nghiệp vụ có side effect ngoài Elasticsearch.

## 5. Cập nhật nhiều document theo điều kiện: Update By Query

Nếu nhiều document thỏa một điều kiện cần nhận cùng thay đổi, không cần đọc từng document về ứng dụng. Dùng Elasticsearch Update By Query API.

Ví dụ chuyển tất cả sản phẩm thuộc danh mục cũ sang danh mục mới:

```http
POST products/_update_by_query
{
  "query": {
    "term": {
      "category": "old-accessories"
    }
  },
  "script": {
    "lang": "painless",
    "source": "ctx._source.category = params.newCategory",
    "params": {
      "newCategory": "accessories"
    }
  }
}
```

Elasticsearch tìm document khớp query rồi áp dụng script cho từng document. Update By Query phù hợp khi một quy tắc chuyển đổi có thể thực hiện ngay tại cluster.

### 5.1. Dùng `updateByQuery` từ Spring Data

`DocumentOperations` có method `updateByQuery(UpdateQuery, IndexCoordinates)`. Có thể kết hợp `CriteriaQuery` làm query chọn document và script làm thay đổi:

```java
import java.util.Map;

import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.ByQueryResponse;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

CriteriaQuery selection = new CriteriaQuery(
        Criteria.where("category").is("old-accessories"));

UpdateQuery updateByQuery = UpdateQuery.builder(selection)
        .withScript("ctx._source.category = params.newCategory")
        .withParams(Map.of("newCategory", "accessories"))
        .withBatchSize(500)
        .withAbortOnVersionConflict(false)
        .build();

ByQueryResponse response = operations.updateByQuery(
        updateByQuery,
        IndexCoordinates.of("products"));
```

`UpdateQuery.builder(Query)` dùng khi thao tác theo query thay vì ID. `withBatchSize` điều chỉnh số document trong một batch. `withAbortOnVersionConflict(false)` yêu cầu tiếp tục khi gặp version conflict; cần xem số conflict trong response và có kế hoạch xử lý các document chưa cập nhật.

Update By Query được thêm vào `DocumentOperations` từ Spring Data Elasticsearch 4.2. Các tùy chọn cụ thể của `UpdateQuery` có thể khác giữa các phiên bản; kiểm tra Javadoc đúng release train.

### 5.2. Version conflict và xử lý lỗi

Update By Query mặc định có thể dừng khi gặp version conflict. Có thể chọn `abort` hoặc `proceed`:

- `abort`: dừng khi gặp conflict; phù hợp khi muốn phát hiện mọi thay đổi đồng thời và xử lý rõ ràng.
- `proceed`: tiếp tục các document còn lại; response vẫn báo số conflict.

`proceed` không tự giải quyết conflict. Những document xung đột có thể chưa được cập nhật; ứng dụng cần ghi nhận và xử lý lại nếu nghiệp vụ yêu cầu tất cả document phải đạt trạng thái mới.

Update By Query dùng tìm kiếm theo batch/scroll ở phía Elasticsearch. Với tập dữ liệu lớn, cần chú ý batch size, thời gian scroll, timeout và tải cluster.

### 5.3. Giới hạn tốc độ và slicing

Update By Query có thể giới hạn tốc độ xử lý bằng `requests_per_second` và chia công việc thành slices. Trong `UpdateQuery.Builder`, các tùy chọn tương ứng có thể được biểu diễn bằng `withRequestsPerSecond(...)`, `withSlices(...)`, `withMaxDocs(...)` và `withTimeout(...)` tùy phiên bản.

Throttling hữu ích khi cập nhật index đang phục vụ traffic thật. Slicing có thể tăng mức song song nhưng cũng tăng tải lên cluster; không nên đặt số slice cao mà chưa theo dõi CPU, I/O và thread pool.

### 5.4. Chạy bất đồng bộ và theo dõi task

Với một tác vụ Update By Query dài, Elasticsearch REST API hỗ trợ `wait_for_completion=false` để trả task ID thay vì giữ kết nối tới khi hoàn tất. Ứng dụng có thể dùng Tasks API để xem trạng thái hoặc hủy task.

Ví dụ REST:

```http
POST products/_update_by_query?wait_for_completion=false&requests_per_second=500
{
  "query": {
    "term": {
      "status": "LEGACY"
    }
  },
  "script": {
    "source": "ctx._source.status = 'ARCHIVED'"
  }
}
```

Response trả task ID. Dùng `GET _tasks/{task_id}` để kiểm tra tiến độ và `POST _tasks/{task_id}/_cancel` nếu cần hủy. Hủy task không tự rollback những document đã cập nhật trước đó.

## 6. Bulk API: nhiều thao tác trong một request

Bulk API nhận một chuỗi NDJSON gồm các action. Mỗi action có metadata và, tùy loại thao tác, có thêm dòng document hoặc update source.

Các action chính:

| Action | Hành vi |
|---|---|
| `index` | Tạo hoặc thay thế document theo ID |
| `create` | Chỉ tạo mới; thất bại nếu ID đã tồn tại |
| `update` | Cập nhật một phần hoặc chạy script trên document |
| `delete` | Xóa document theo ID |

Ví dụ một bulk request gồm ba loại thao tác:

```http
POST _bulk
{"index":{"_index":"products","_id":"p-101"}}
{"name":"Keyboard","category":"accessories","priceInCents":1299000}
{"update":{"_index":"products","_id":"p-102","retry_on_conflict":3}}
{"doc":{"priceInCents":1399000}}
{"delete":{"_index":"products","_id":"p-103"}}
```

Body của Bulk API phải dùng NDJSON, mỗi dòng là một JSON object riêng và request phải kết thúc bằng newline. Với HTTP client, content type phù hợp là `application/x-ndjson`.

Bulk giúp giảm số lần kết nối/round-trip, nhưng không biến toàn bộ request thành một transaction. Mỗi action được xử lý độc lập; một item thất bại không nhất thiết làm các item khác thất bại.

### 6.1. Đọc response của Bulk API

Response thường có các trường:

- `took`: thời gian xử lý request.
- `errors`: `true` nếu có ít nhất một action thất bại.
- `items`: kết quả riêng cho từng action, theo thứ tự đã gửi.

HTTP status 200 không có nghĩa mọi item đều thành công. Ứng dụng phải kiểm tra `errors` và từng phần tử trong `items`, sau đó retry hoặc ghi nhận các item lỗi theo chính sách.

Ví dụ response có lỗi:

```json
{
  "took": 18,
  "errors": true,
  "items": [
    {
      "index": {
        "_id": "p-101",
        "status": 201,
        "result": "created"
      }
    },
    {
      "update": {
        "_id": "p-102",
        "status": 404,
        "error": {
          "type": "document_missing_exception",
          "reason": "document missing"
        }
      }
    }
  ]
}
```

Item đầu tiên thành công, item thứ hai thất bại vì document chưa tồn tại. Không nên retry toàn bộ batch một cách mù quáng; hãy phân loại lỗi và chỉ retry những action có thể thử lại an toàn.

## 7. Bulk index bằng Spring Data Elasticsearch

Spring Data cung cấp `bulkIndex(List<IndexQuery>, ...)` trong `DocumentOperations`. Method này thực hiện bulk index và có semantics save/update cho từng document.

Ví dụ tạo `IndexQuery` từ danh sách entity:

```java
import java.util.List;

import org.springframework.data.elasticsearch.core.IndexedObjectInformation;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;

List<IndexQuery> queries = products.stream()
        .map(product -> new IndexQueryBuilder()
                .withId(product.getId())
                .withObject(product)
                .build())
        .toList();

List<IndexedObjectInformation> indexed = operations.bulkIndex(
        queries,
        IndexCoordinates.of("products"));
```

`IndexQueryBuilder` cho phép chỉ định ID, object, routing, version và operation type. Nếu cần bảo đảm chỉ tạo mới, có thể đặt `IndexQuery.OpType.CREATE` thay cho hành vi index mặc định:

```java
IndexQuery createOnly = new IndexQueryBuilder()
        .withId(product.getId())
        .withObject(product)
        .withOpType(IndexQuery.OpType.CREATE)
        .build();
```

Khi ID đã tồn tại, action create sẽ báo conflict thay vì thay thế document. Chọn `CREATE` khi dữ liệu đầu vào phải là bản ghi mới và việc ghi đè là lỗi nghiệp vụ.

### 7.1. Cấu hình `BulkOptions`

Có thể truyền `BulkOptions` để cấu hình pipeline, refresh policy, timeout, routing hoặc số shard cần active:

```java
import java.time.Duration;

import org.springframework.data.elasticsearch.core.RefreshPolicy;
import org.springframework.data.elasticsearch.core.query.BulkOptions;

BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.NONE)
        .withTimeout(Duration.ofSeconds(30))
        .build();

List<IndexedObjectInformation> result = operations.bulkIndex(
        queries,
        options,
        IndexCoordinates.of("products"));
```

`RefreshPolicy.NONE` tránh yêu cầu refresh ngay sau bulk. Nếu ứng dụng cần tìm thấy document ngay sau khi ghi, có thể cân nhắc `WAIT_UNTIL` hoặc `IMMEDIATE`, nhưng refresh thường xuyên làm giảm hiệu năng indexing.

`BulkOptions` không thay thế việc chia batch. Ứng dụng vẫn cần quyết định kích thước mỗi lô dữ liệu phù hợp với dung lượng document, băng thông và tài nguyên cluster.

### 7.2. Bulk update bằng `UpdateQuery`

Khi đã biết ID của từng document và chỉ muốn cập nhật một số field, tạo danh sách `UpdateQuery`:

```java
import java.util.List;
import java.util.Map;

import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

List<UpdateQuery> updates = List.of(
        UpdateQuery.builder("p-101")
                .withDocument(Document.from(Map.of("priceInCents", 1299000L)))
                .build(),
        UpdateQuery.builder("p-102")
                .withDocument(Document.from(Map.of("priceInCents", 1399000L)))
                .build(),
        UpdateQuery.builder("p-103")
                .withDocument(Document.from(Map.of("priceInCents", 1499000L)))
                .build()
);

operations.bulkUpdate(
        updates,
        BulkOptions.defaultOptions(),
        IndexCoordinates.of("products"));
```

`bulkUpdate` thực hiện update cho từng `UpdateQuery`. Khác với `bulkIndex`, method này không thay thế toàn bộ document. Có thể dùng `withDocument`, `withScript`, `withUpsert`, `withDocAsUpsert`, `withRetryOnConflict` hoặc concurrency condition tùy trường hợp.

Các method bulk của Spring Data có thể ném `BulkFailureException` khi có action thất bại. Không nên bỏ qua exception và giả định toàn bộ batch đã được ghi thành công.

## 8. Xử lý lỗi bulk trong Spring Data

Spring Data cung cấp `BulkFailureException`, một `DataAccessException` chứa thông tin về các document thất bại. Có thể đọc `getFailedDocuments()` để ghi log hoặc đưa item lỗi vào hàng đợi retry:

```java
import org.springframework.data.elasticsearch.BulkFailureException;

try {
    operations.bulkUpdate(
            updates,
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("products"));
} catch (BulkFailureException ex) {
    ex.getFailedDocuments().forEach((id, failure) -> {
        // Record the document ID, HTTP status and error message.
        System.err.println(id + " -> " + failure.status()
                + ": " + failure.errorMessage());
    });
    throw ex;
}
```

Từ Spring Data Elasticsearch 5.2, `getFailedDocuments()` trả map có value là `BulkFailureException.FailureDetails` với status và error message. Các phiên bản trước có kiểu dữ liệu khác; khi nâng cấp cần kiểm tra migration guide và chữ ký API thực tế.

Nên phân loại lỗi:

- Mapping/parsing error: sửa dữ liệu hoặc mapping trước khi retry.
- Version conflict: đọc lại trạng thái hoặc áp dụng chiến lược retry có kiểm soát.
- Document missing khi update: kiểm tra ID, chuyển sang upsert nếu đúng nghiệp vụ.
- Authentication/authorization: sửa credential hoặc quyền, không retry liên tục.
- Timeout hoặc lỗi mạng: xác định request đã được server xử lý một phần hay chưa trước khi gửi lại.

Retry cần idempotent. Với action index cùng ID và cùng nội dung, gửi lại thường cho cùng trạng thái cuối; với script tăng bộ đếm hoặc các thao tác cộng dồn, retry có thể áp dụng thay đổi hai lần nếu không có cơ chế chống lặp.

## 9. Chọn kích thước batch và vận hành bulk

Không có một kích thước bulk tối ưu cho mọi cluster. Số document chỉ là một phần; kích thước byte của payload, số field, analyzer, ingest pipeline và tốc độ ghi đều ảnh hưởng hiệu năng.

Một số nguyên tắc thực tế:

- Bắt đầu với batch vừa phải, đo throughput và latency rồi điều chỉnh.
- Chia dữ liệu theo số document hoặc tổng byte; tránh tạo một request cực lớn giữ toàn bộ payload trong heap.
- Theo dõi `took`, số item lỗi, bulk thread pool, indexing pressure và dung lượng disk.
- Hạn chế refresh ngay sau từng batch nếu không cần khả năng search tức thời.
- Khi có nhiều producer, tránh để mọi producer cùng gửi batch lớn nhất có thể.
- Dùng backpressure hoặc giới hạn tốc độ khi cluster quá tải.
- Giữ thứ tự thao tác nếu nghiệp vụ yêu cầu, đặc biệt khi nhiều action cập nhật cùng một ID.

Bulk API không phải transaction. Nếu cần một nhóm thao tác phải thành công hoặc thất bại cùng nhau, cần thiết kế cơ chế điều phối/compensation ở tầng ứng dụng; không thể dựa vào một bulk request để rollback toàn bộ item.

## 10. Bulk API trực tiếp và Elasticsearch Java API Client

Khi Spring Data abstraction đáp ứng nhu cầu, `bulkIndex` và `bulkUpdate` giúp tận dụng mapping converter và `IndexCoordinates`. Khi cần kiểm soát action thấp hơn hoặc sử dụng tùy chọn mới của Elasticsearch, có thể dùng Elasticsearch Java API Client hoặc REST Bulk API.

Elasticsearch Java API Client là client chính thức ở các Spring Data Elasticsearch release train hiện đại. Có thể inject `co.elastic.clients.elasticsearch.ElasticsearchClient` nếu cấu hình ứng dụng cung cấp bean tương ứng. Khi dùng client trực tiếp, ứng dụng chịu trách nhiệm tạo request/response đúng với API client và phiên bản server.

Không tự nâng riêng dependency `elasticsearch-java` lên major version khác với phiên bản mà Spring Data/Spring Boot quản lý nếu chưa kiểm tra tương thích. Các request type được sinh theo phiên bản client.

## 11. Reindex dùng khi nào?

Reindex sao chép document từ source index, alias hoặc data stream sang destination index. Đây là API thích hợp khi cần:

- Chuyển dữ liệu sang index mới có mapping khác.
- Đổi analyzer hoặc kiểu field cần lập chỉ mục lại.
- Thay đổi số shard hoặc settings của index.
- Chuẩn hóa dữ liệu bằng script trong lúc chuyển.
- Gộp một số index nguồn vào một index đích.
- Di chuyển dữ liệu sang index có cấu trúc hoặc lifecycle mới.

Reindex không giống `updateByQuery`:

| Thao tác | Source | Destination | Mục đích |
|---|---|---|---|
| Update By Query | Một index được cập nhật tại chỗ | Chính index đó | Sửa document đang có theo query/script |
| Reindex | Một hoặc nhiều nguồn | Index/stream khác | Sao chép document sang đích, có thể biến đổi dữ liệu |

Reindex không xóa document ở nguồn. Sau khi reindex thành công, cả nguồn và đích vẫn tồn tại cho tới khi ứng dụng hoặc quy trình vận hành chuyển alias và dọn nguồn.

## 12. Chuẩn bị destination trước khi reindex

Elasticsearch Reindex API chỉ sao chép document. Nó **không sao chép settings, mappings, số shard, replicas hoặc index template** từ source sang destination.

Vì vậy, phải tạo destination với cấu hình mong muốn trước khi gọi reindex:

```http
PUT products-v2
{
  "settings": {
    "number_of_shards": 2,
    "number_of_replicas": 1
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "category": {
        "type": "keyword"
      },
      "priceInCents": {
        "type": "long"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
```

Sau đó mới chạy reindex. Nguồn cần bật `_source`, vì Reindex API đọc nội dung document từ `_source` để gửi sang đích.

Source và destination phải khác nhau. Không thể reindex một index hoặc data stream vào chính nó. Nếu đích là data stream, thao tác reindex phải dùng `op_type: create` vì data stream là append-only và không cho phép cập nhật document đã có theo cách thông thường.

## 13. Gọi Reindex API bằng REST

Ví dụ sao chép toàn bộ document từ `products-v1` sang `products-v2`:

```http
POST _reindex
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
```

Có thể lọc source bằng Query DSL:

```http
POST _reindex
{
  "source": {
    "index": "products-v1",
    "query": {
      "term": {
        "status": "ACTIVE"
      }
    }
  },
  "dest": {
    "index": "products-v2",
    "op_type": "create"
  }
}
```

`op_type: create` chỉ tạo document mới ở đích. Nếu ID đã tồn tại, action tạo bị conflict thay vì ghi đè document đích.

### 13.1. Biến đổi dữ liệu bằng script trong lúc reindex

Có thể dùng Painless script để đổi dữ liệu trước khi ghi vào đích:

```http
POST _reindex
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  },
  "script": {
    "lang": "painless",
    "source": "ctx._source.category = ctx._source.remove('legacyCategory')"
  }
}
```

Script trên chuyển giá trị từ `legacyCategory` sang `category` rồi loại field cũ khỏi `_source` mới. Hãy thử script trên một tập document nhỏ trước khi chạy toàn bộ dữ liệu.

### 13.2. Version conflict

Reindex mặc định dừng khi gặp version conflict. Có thể đặt `conflicts: proceed` để tiếp tục và đếm conflict:

```http
POST _reindex?wait_for_completion=true
{
  "conflicts": "proceed",
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2",
    "op_type": "create"
  }
}
```

`proceed` không có nghĩa tất cả document đã được sao chép. Kiểm tra `version_conflicts`, `failures`, `created`, `updated` và các bộ đếm trong response. Quyết định xử lý conflict theo mục tiêu migration.

### 13.3. Chạy reindex bất đồng bộ

Với tập dữ liệu lớn, dùng `wait_for_completion=false` để nhận task ID:

```http
POST _reindex?wait_for_completion=false&requests_per_second=500
{
  "source": {
    "index": "products-v1",
    "size": 500
  },
  "dest": {
    "index": "products-v2"
  }
}
```

Kiểm tra task:

```http
GET _tasks/<task_id>
```

Hủy task nếu cần:

```http
POST _tasks/<task_id>/_cancel
```

Task bị hủy không rollback các document đã ghi vào destination. Nếu chạy lại, cần xác định chính sách xử lý document đã được copy một phần, chẳng hạn xóa destination thử nghiệm rồi chạy lại, hoặc dùng `op_type: create` và xử lý conflict.

## 14. Reindex bằng Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp `ReindexRequest` cùng hai method trên `DocumentOperations`:

- `reindex(ReindexRequest)`: thực hiện reindex và trả `ReindexResponse`.
- `submitReindex(ReindexRequest)`: gửi tác vụ và trả task ID.

Hai method này có từ Spring Data Elasticsearch 4.4. Ví dụ tạo request:

```java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.reindex.ReindexRequest;
import org.springframework.data.elasticsearch.core.reindex.ReindexResponse;

ReindexRequest request = ReindexRequest.builder(
                IndexCoordinates.of("products-v1"),
                IndexCoordinates.of("products-v2"))
        .withSourceSize(500)
        .withMaxDocs(100_000L)
        .withConflicts(ReindexRequest.Conflicts.PROCEED)
        .withRefresh(true)
        .build();

ReindexResponse response = operations.reindex(request);
```

`IndexCoordinates` xác định source và destination. `withSourceSize` điều chỉnh batch size đọc từ nguồn; `withMaxDocs` giới hạn số document được xử lý; `withConflicts` chọn cách xử lý version conflict; `withRefresh(true)` yêu cầu refresh destination sau thao tác.

Có thể thêm query để chỉ sao chép document cần thiết:

```java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

ReindexRequest activeProducts = ReindexRequest.builder(
                IndexCoordinates.of("products-v1"),
                IndexCoordinates.of("products-v2"))
        .withSourceQuery(new CriteriaQuery(
                Criteria.where("status").is("ACTIVE")))
        .withSourceSize(500)
        .build();
```

Reindex request builder còn có các tùy chọn như script, destination pipeline, destination routing, operation type, version type, slicing, throttling, scroll duration và timeout. Kiểm tra Javadoc của đúng phiên bản để biết các method khả dụng.

### 14.1. Theo dõi response

`ReindexResponse` cung cấp các thông tin như:

- `getTotal()`: số document đã xử lý thành công.
- `getCreated()`: số document được tạo ở đích.
- `getUpdated()`: số document ở đích được cập nhật.
- `getVersionConflicts()`: số conflict phiên bản.
- `getFailures()`: danh sách lỗi.
- `isTimedOut()`: có sub-request nào timeout hay không.
- `getTook()`: thời gian thực hiện.

Không chỉ kiểm tra `getTotal()`. Hãy xem cả conflict, failures và timeout trước khi kết luận migration hoàn tất.

### 14.2. Submit reindex task

Nếu muốn chạy tác vụ bất đồng bộ:

```java
String taskId = operations.submitReindex(request);
```

Method này trả task ID. Dùng Elasticsearch Tasks API qua Elasticsearch Java API Client hoặc REST API để theo dõi, hủy hoặc lấy kết quả task. `submitReindex` không đồng nghĩa tác vụ đã hoàn tất khi method trả về.

## 15. Quy trình migration index an toàn

Một tình huống điển hình là thay đổi mapping của `products-v1` và tạo `products-v2`. Không thể luôn sửa trực tiếp kiểu field đã lập chỉ mục, nên tạo index mới rồi reindex là cách triển khai phổ biến.

```text
             1. Tạo products-v2
                       |
                       v
             2. Reindex từ v1 sang v2
                       |
                       v
             3. Kiểm tra dữ liệu v2
                       |
                       v
             4. Đồng bộ các ghi mới
                       |
                       v
             5. Chuyển read/write alias
                       |
                       v
             6. Giữ v1 trong thời gian rollback
                       |
                       v
             7. Xóa v1 khi đã xác nhận
```

Trình tự triển khai:

1. Tạo `products-v2` với settings, mappings, analyzers và aliases mong muốn.
2. Kiểm tra mapping của index đích trước khi sao chép.
3. Chạy reindex từ `products-v1` sang `products-v2`.
4. Kiểm tra số lượng document, dữ liệu mẫu, mapping, query và aggregation trên index mới.
5. Xử lý các document được ghi vào source trong lúc reindex. Có thể tạm dừng ghi, dual-write, phát lại event hoặc chạy lượt catch-up tùy kiến trúc.
6. Chuyển alias đọc/ghi sang index mới bằng một thao tác Aliases API.
7. Theo dõi lỗi sau chuyển đổi và giữ index cũ trong thời gian rollback.
8. Chỉ xóa index cũ sau khi đã xác nhận dữ liệu và quy trình vận hành ổn định.

Reindex không tự đồng bộ các thay đổi phát sinh sau thời điểm nó đọc document. Nếu ứng dụng tiếp tục ghi vào index cũ trong lúc migration, những thay đổi đó có thể chưa xuất hiện ở index mới. Cần có chiến lược đồng bộ cuối cùng trước khi chuyển alias.

### 15.1. Chuyển alias

Ví dụ chuyển alias `products-read` từ index cũ sang index mới:

```http
POST _aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-read"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-read"
      }
    }
  ]
}
```

Aliases API thực hiện nhóm thay đổi trong một request có tính nguyên tử ở cấp cluster metadata. Với write alias, cần cấu hình `is_write_index` đúng nếu alias trỏ tới nhiều index. Ứng dụng nên dùng alias ổn định thay vì hard-code index version nếu kiến trúc cần migration thường xuyên.

### 15.2. Reindex và data stream

Reindex có thể đọc từ data stream. Khi destination là data stream, phải dùng `op_type: create`; data stream không hỗ trợ update document đã có qua reindex. Hãy tạo destination data stream và template phù hợp trước khi copy dữ liệu.

## 16. Refresh và khả năng nhìn thấy dữ liệu

Elasticsearch là hệ thống near-real-time. Sau `save`, `update`, bulk hoặc reindex, dữ liệu có thể chưa xuất hiện ngay trong search cho tới lần refresh tiếp theo.

Spring Data cung cấp `RefreshPolicy` và các method như `operations.withRefreshPolicy(...)`. Các lựa chọn thường gặp:

| Policy | Ý nghĩa |
|---|---|
| `NONE` | Không yêu cầu refresh riêng; thay đổi sẽ xuất hiện sau refresh kế tiếp |
| `IMMEDIATE` | Refresh ngay sau thao tác để thay đổi sớm có thể tìm thấy |
| `WAIT_UNTIL` | Chờ lần refresh kế tiếp thay vì ép refresh ngay |

Không nên đặt `IMMEDIATE` cho mọi request production chỉ để search thấy dữ liệu tức thì. Refresh thường xuyên làm giảm hiệu năng ghi. Chỉ chọn policy theo yêu cầu nghiệp vụ và kiểm thử.

## 17. Routing, pipeline và các điều kiện nhất quán

Khi ghi document có custom routing, update và bulk action cũng cần dùng routing tương ứng. Nếu không, Elasticsearch có thể tìm sai shard hoặc không tìm thấy document.

`BulkOptions` có thể truyền routing ID chung cho bulk request. `UpdateQuery` cũng có `withRouting(...)`. Với từng document có routing khác nhau, cấu hình action/query riêng phù hợp thay vì dùng một routing chung sai lệch.

Ingest pipeline có thể chạy khi index/bulk index hoặc reindex đích được cấu hình sử dụng pipeline. Khi reindex, có thể chỉ định destination pipeline. Hãy kiểm tra pipeline có chạy lại logic chuẩn hóa mong muốn không và tránh xử lý lặp gây thay đổi dữ liệu ngoài dự kiến.

Đối với các luồng cập nhật đồng thời:

- Dùng `if_seq_no` và `if_primary_term` khi cần optimistic concurrency.
- Dùng `retry_on_conflict` khi update có thể chạy lại an toàn.
- Thiết kế script idempotent nếu request có thể được retry.
- Không coi bulk hoặc reindex là transaction.
- Ghi lại ID, index, action và nguyên nhân lỗi để có thể replay có chọn lọc.

## 18. Các lỗi thường gặp

### Dùng `save` khi chỉ muốn sửa một field

`save` ghi lại document theo entity, có thể làm mất field không có trong object. Dùng `UpdateQuery` hoặc `update(entity)` cho partial update.

### Dùng update cho document chưa tồn tại mà không cấu hình upsert

Update API có thể trả document missing. Nếu nghiệp vụ muốn tạo mới khi chưa tồn tại, cấu hình `doc_as_upsert` hoặc `upsert` rõ ràng.

### Bulk trả HTTP 200 nhưng có item lỗi

Kiểm tra `errors` và từng item trong response; với Spring Data, xử lý `BulkFailureException.getFailedDocuments()`.

### Retry script cộng dồn nhiều lần

Một script tăng counter không idempotent có thể tăng nhiều lần nếu ứng dụng gửi lại action sau timeout. Dùng idempotency key, version check hoặc thiết kế script/luồng xử lý phù hợp.

### Reindex nhưng quên tạo mapping destination

Reindex không copy mapping/settings. Nếu destination tự dynamic mapping, kiểu dữ liệu có thể khác source hoặc dữ liệu bị parse sai. Tạo destination trước với cấu hình đã xác định.

### Reindex trong khi nguồn vẫn tiếp tục nhận ghi

Những thay đổi mới có thể không được copy sang đích. Dùng dual-write, pause writes, catch-up pass hoặc event replay trước khi chuyển alias.

### Dùng `conflicts: proceed` rồi coi migration đã hoàn tất

Conflict vẫn là document chưa được xử lý theo request đó. Kiểm tra số conflict và failures, sau đó quyết định chạy lại hoặc xử lý riêng.

### Không theo dõi task bất đồng bộ

`submitReindex` hoặc `wait_for_completion=false` chỉ trả task ID. Cần theo dõi trạng thái, kết quả, timeout và failures trước khi chuyển alias.

### Bulk batch quá lớn

Request quá lớn có thể gây áp lực heap, network và thread pool. Chia batch, đo throughput và áp dụng backpressure.

## 19. Chọn API theo tình huống

| Tình huống | Lựa chọn đề xuất | Vì sao |
|---|---|---|
| Ghi entity đầy đủ | Repository `save` hoặc `operations.save` | API đơn giản, mapping converter xử lý entity |
| Sửa một vài field của một document | `operations.update(UpdateQuery, index)` | Gửi partial document rõ ràng |
| Tăng counter hoặc tính toán trên giá trị hiện tại | `UpdateQuery` với Painless script | Không cần đọc document về ứng dụng |
| Nhiều document có cùng điều kiện cần cùng thay đổi | `updateByQuery` | Elasticsearch thực hiện tìm và cập nhật theo batch |
| Nhiều document có ID và nội dung riêng | `bulkIndex`/`bulkUpdate` | Gom nhiều action thành bulk request |
| Cần action `create`, `delete` và `update` hỗn hợp | Bulk API/Java API Client | Kiểm soát từng action trong cùng request |
| Đổi mapping hoặc chuyển index version | `reindex` | Sao chép document sang index đã chuẩn bị |
| Chạy reindex lâu và cần task ID | `submitReindex` hoặc REST với `wait_for_completion=false` | Theo dõi và điều khiển task riêng |

## 20. Kiểm thử và xác minh kết quả

Nên kiểm tra cả dữ liệu, response và khả năng search sau thao tác. Ví dụ với partial update:

```java
@Test
void partialUpdateChangesOnlyTheRequestedField() {
    Product original = new Product(
            "p-100", "Keyboard", "accessories", 1299000L);
    operations.save(original);

    UpdateQuery update = UpdateQuery.builder("p-100")
            .withDocument(Document.from(Map.of("priceInCents", 1399000L)))
            .build();

    operations.update(update, IndexCoordinates.of("products"));

    Product loaded = operations.get("p-100", Product.class);
    assertThat(loaded).isNotNull();
    assertThat(loaded.getName()).isEqualTo("Keyboard");
    assertThat(loaded.getPriceInCents()).isEqualTo(1399000L);
}
```

Trong integration test, cần chờ hoặc yêu cầu refresh phù hợp trước khi xác minh bằng search. `get(id, ...)` dùng document retrieval theo ID và không phụ thuộc search visibility theo cùng cách với `_search`.

Với bulk, xác minh số lượng action thành công và danh sách lỗi. Với reindex, kiểm tra mapping destination, số lượng document, các field đã biến đổi, version conflict và query đại diện. Không chỉ so sánh count vì hai document khác nhau có thể có cùng số lượng.

Testcontainers hoặc một Elasticsearch instance thật giúp xác minh semantics của Update API, Bulk API, ingest pipeline và Reindex API. Mock `ElasticsearchOperations` chỉ kiểm tra tương tác ở tầng Java, không xác nhận Elasticsearch server thực thi request đúng như mong đợi.

## 21. Khác biệt API giữa các release train

Spring Data Elasticsearch và Elasticsearch Java API Client thay đổi theo phiên bản. Một số mốc API trong tài liệu hiện hành:

- `DocumentOperations` được tách thành interface chuyên trách từ Spring Data Elasticsearch 4.0.
- `bulkUpdate` có từ 4.1.
- `updateByQuery` có từ 4.2.
- `reindex` và `submitReindex` có từ 4.4.
- `update(entity)` có từ 5.0.
- Từ Spring Data Elasticsearch 5.2, kiểu value trong `BulkFailureException.getFailedDocuments()` là `FailureDetails` thay vì chuỗi lỗi đơn giản ở các bản trước.

Spring Boot quản lý các phiên bản Spring Data và Elasticsearch Java API Client tương thích qua dependency management. Trước khi sao chép ví dụ, kiểm tra phiên bản `spring-data-elasticsearch` thực tế và Javadoc của nó. Không nâng riêng Elasticsearch Java API Client lên một major version khác nếu chưa xác nhận tương thích.

## 22. Quy trình làm việc đề xuất

Khi triển khai một thay đổi dữ liệu lớn, có thể đi theo trình tự:

1. Xác định thay đổi là ghi toàn bộ document, partial update, update theo query, bulk hay reindex.
2. Chọn `ElasticsearchRepository` cho thao tác đơn giản hoặc `ElasticsearchOperations` cho API điều khiển chi tiết.
3. Xác định index, ID, routing và concurrency condition.
4. Thử một số document mẫu trên môi trường phát triển.
5. Chia batch và thiết lập timeout, refresh, retry/throttling phù hợp.
6. Ghi nhận response và xử lý từng item lỗi; không giả định bulk atomic.
7. Với update-by-query hoặc reindex lớn, cân nhắc task bất đồng bộ và theo dõi Tasks API.
8. Với reindex, tạo destination mapping/settings trước, kiểm tra `_source` và chuẩn bị chiến lược đồng bộ ghi mới.
9. So sánh dữ liệu, kiểm thử query, sau đó chuyển alias.
10. Chỉ xóa index cũ sau khi xác nhận và hết thời gian rollback.

## 23. Tổng kết

`save` phù hợp khi muốn ghi đầy đủ trạng thái entity; `update` phù hợp khi chỉ thay đổi một phần document. `UpdateQuery` cho phép gửi partial document, upsert hoặc Painless script. `updateByQuery` áp dụng một thay đổi cho các document khớp điều kiện. Bulk API gom nhiều action độc lập trong một request; phải kiểm tra kết quả từng item và xử lý lỗi một phần. Reindex sao chép document sang index đích đã được cấu hình trước, thường dùng khi thay mapping hoặc chuyển đổi index version.

Trong Spring Data Elasticsearch, `DocumentOperations`/`ElasticsearchOperations` cung cấp các method `update`, `updateByQuery`, `bulkIndex`, `bulkUpdate`, `reindex` và `submitReindex`. Khi abstraction không đáp ứng một tùy chọn mới của Elasticsearch, có thể dùng Elasticsearch Java API Client hoặc REST API. Lựa chọn API đúng với mục tiêu, kiểm soát concurrency và refresh, theo dõi lỗi từng item và chuẩn bị quy trình alias migration giúp các thay đổi dữ liệu có thể dự đoán và vận hành an toàn.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – DocumentOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/DocumentOperations.html)
- [Spring Data Elasticsearch – UpdateQuery API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/UpdateQuery.html)
- [Spring Data Elasticsearch – ReindexRequest API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/reindex/ReindexRequest.html)
- [Elasticsearch – Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
- [Elasticsearch – Update By Query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update-by-query)
- [Elasticsearch – Reindex API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-reindex)
