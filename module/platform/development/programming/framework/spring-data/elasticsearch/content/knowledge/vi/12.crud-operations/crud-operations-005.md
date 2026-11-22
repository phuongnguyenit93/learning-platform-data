# Phân biệt lấy trực tiếp theo id và tìm kiếm qua index

Elasticsearch cung cấp hai cách phổ biến để đọc document:

- **Lấy trực tiếp theo ID**: chỉ định document ID và index cần đọc. Elasticsearch đi thẳng tới shard chứa document để lấy document đó.
- **Tìm kiếm qua index**: gửi query tới Search API để tìm các document thỏa điều kiện dựa trên inverted index và các cấu trúc tìm kiếm khác.

Hai cách có mục đích và đặc tính khác nhau. Khi biết chính xác document ID, lấy trực tiếp thường đơn giản và nhanh hơn. Khi cần tìm theo tên, trạng thái, mã nghiệp vụ, nội dung hoặc nhiều điều kiện, cần dùng search.

## 1. Document ID và index

Mỗi document trong Elasticsearch thuộc một index và có metadata ID là `_id`. Ví dụ:

~~~http
PUT /products/_doc/KB-1001
Content-Type: application/json

{
  "name": "Wireless Mechanical Keyboard",
  "sku": "KB-1001",
  "status": "PUBLISHED",
  "price": 1299000
}
~~~

Trong ví dụ:

- `products` là index.
- `KB-1001` là document ID.
- `name`, `sku`, `status` và `price` là các field trong document source.
- `_id` là metadata định danh do Elasticsearch quản lý.

Document ID có thể được ứng dụng gán trước hoặc để Elasticsearch tự sinh. Khi lưu bằng Spring Data Elasticsearch, thuộc tính Java được đánh dấu `@Id` ánh xạ tới metadata `_id`.

Ví dụ entity:

~~~java
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

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String status;

    // Constructors, getters and setters
}
~~~

`id` trong entity là giá trị Spring Data dùng làm document ID. Nó không tự động trở thành field nghiệp vụ để truy vấn, sort hoặc aggregation như `sku` hay `status`.

## 2. Lấy trực tiếp document theo ID

Elasticsearch cung cấp Get API để lấy một document theo index và ID:

~~~http
GET /products/_doc/KB-1001
~~~

Đây là thao tác đọc trực tiếp. Request không cần gửi query DSL và không phải tìm các term trong inverted index như Search API.

Phản hồi khi document tồn tại có dạng:

~~~json
{
  "_index": "products",
  "_id": "KB-1001",
  "_version": 3,
  "found": true,
  "_source": {
    "name": "Wireless Mechanical Keyboard",
    "sku": "KB-1001",
    "status": "PUBLISHED",
    "price": 1299000
  }
}
~~~

Nếu document không tồn tại, Get API trả về phản hồi không tìm thấy (HTTP 404). Ứng dụng cần xử lý trường hợp này như một kết quả bình thường của thao tác đọc.

### Đặc điểm của Get API

- Cần biết index và document ID.
- Trả về tối đa một document cho một ID trong index được chỉ định.
- Không hỗ trợ điều kiện tìm kiếm như `name contains...` hoặc `status = ...`.
- Không tính relevance score.
- Có thể lấy `_source` hoặc chọn lọc các phần source cần trả về.
- Mặc định là thao tác realtime: document vừa được index hoặc cập nhật có thể được đọc bằng Get API ngay cả khi thay đổi đó chưa xuất hiện trong kết quả Search API sau refresh.

Get API phù hợp khi ứng dụng đã có ID từ URL, khóa tham chiếu hoặc kết quả của một thao tác ghi trước đó.

## 3. Lấy nhiều document theo ID bằng Multi Get

Nếu đã biết nhiều ID và muốn lấy các document tương ứng, không cần gửi một request Get riêng cho từng document. Elasticsearch có Multi Get API:

~~~http
POST /products/_mget
Content-Type: application/json

{
  "ids": ["KB-1001", "KB-1002", "KB-1003"]
}
~~~

Hoặc chỉ định ID và routing riêng cho từng document:

~~~http
POST /_mget
Content-Type: application/json

{
  "docs": [
    {
      "_index": "products",
      "_id": "KB-1001"
    },
    {
      "_index": "products",
      "_id": "KB-1002"
    }
  ]
}
~~~

Multi Get trả về kết quả theo từng document. Một ID không tồn tại không có nghĩa toàn bộ request thất bại; cần kiểm tra trạng thái từng phần tử trong phản hồi.

Dùng Multi Get khi:

- Danh sách ID đã có sẵn từ một nguồn khác.
- Cần lấy một nhóm document để dựng màn hình hoặc xử lý nghiệp vụ.
- Muốn giảm số lần round trip so với việc gọi Get API tuần tự.

Nếu danh sách ID rất lớn, cần chia batch hợp lý để kiểm soát kích thước request, tải mạng và bộ nhớ.

## 4. Tìm kiếm document qua index

Search API tìm các document thỏa điều kiện bằng query DSL:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Elasticsearch phân tích nội dung truy vấn theo search analyzer của field, sau đó tìm các term phù hợp trong inverted index và tính điểm liên quan khi query có scoring.

Search API có thể trả về nhiều document, kèm theo:

- Tổng số kết quả theo cấu hình track total hits.
- Relevance score (`_score`) nếu query có tính điểm.
- Các field source hoặc stored fields được yêu cầu.
- Thông tin sort, highlight, aggregation và phân trang.

Ví dụ lọc theo trạng thái:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "term": {
      "status": "PUBLISHED"
    }
  }
}
~~~

Ví dụ tìm theo mã SKU:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "term": {
      "sku": "KB-1001"
    }
  }
}
~~~

Dù chỉ mong muốn một kết quả, nếu tìm theo field nghiệp vụ như `sku`, ứng dụng vẫn đang thực hiện tìm kiếm qua index. Elasticsearch phải tìm term tương ứng trong field đã được lập chỉ mục.

### Đặc điểm của Search API

- Tìm theo field và điều kiện query, không yêu cầu biết document ID trước.
- Có thể trả về một hoặc nhiều document.
- Hỗ trợ full-text query, filter, range, sort, aggregation, highlight và phân trang.
- Có thể tính relevance score cho kết quả.
- Kết quả phụ thuộc vào trạng thái search index sau refresh, nên Search API có tính near-real-time.

## 5. Khác biệt về thời điểm nhìn thấy dữ liệu: realtime và near-real-time

Một điểm quan trọng là Get API và Search API có cơ chế nhìn thấy dữ liệu khác nhau.

Elasticsearch là hệ thống tìm kiếm near-real-time. Sau khi index hoặc cập nhật document, thay đổi chưa chắc xuất hiện ngay trong Search API. Document trở nên có thể tìm kiếm sau khi index được refresh.

Trong khi đó, Get API mặc định đọc theo cơ chế realtime, nên có thể trả về phiên bản mới ngay cả khi Search API chưa tìm thấy phiên bản đó.

Ví dụ:

1. Ứng dụng lưu sản phẩm `KB-1001` với tên `Wireless Keyboard`.
2. Save API trả về thành công.
3. Ứng dụng gọi Get API theo ID `KB-1001`: có thể đọc được dữ liệu mới ngay.
4. Ứng dụng lập tức gọi Search API với `name = Wireless Keyboard`: kết quả có thể chưa xuất hiện cho đến lần refresh tiếp theo.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant ES as Elasticsearch
    App->>ES: Index document KB-1001
    ES-->>App: Index thành công
    App->>ES: GET /products/_doc/KB-1001
    ES-->>App: Trả document mới (realtime)
    App->>ES: POST /products/_search
    ES-->>App: Kết quả theo search index hiện tại
    Note over ES: Sau refresh, document mới có thể tìm kiếm qua Search API
~~~

Không nên coi việc Search API chưa trả về document ngay sau save là bằng chứng document chưa được lưu. Khi cần xác nhận kết quả ghi ngay lập tức theo ID, Get API là lựa chọn phù hợp.

### Refresh và refresh=wait_for

Có thể yêu cầu Elasticsearch chờ refresh để thay đổi có thể tìm kiếm:

- `refresh=false`: không yêu cầu refresh ngay; dùng hành vi mặc định.
- `refresh=wait_for`: đợi một refresh làm cho thay đổi có thể tìm kiếm.
- `refresh=true`: yêu cầu refresh ngay, làm thay đổi trở nên searchable sớm hơn nhưng có thể tăng chi phí hệ thống.

Ví dụ:

~~~http
PUT /products/_doc/KB-1001?refresh=wait_for
Content-Type: application/json

{
  "name": "Wireless Keyboard",
  "sku": "KB-1001",
  "status": "PUBLISHED"
}
~~~

`refresh=wait_for` hữu ích khi luồng nghiệp vụ cần ghi xong rồi tìm kiếm ngay trong cùng một quy trình. Không nên bật `refresh=true` cho mọi request ghi trong production vì refresh thường xuyên làm giảm hiệu quả indexing.

Nếu không cần tìm kiếm ngay, hãy để refresh theo cấu hình index và chấp nhận độ trễ near-real-time bình thường.

## 6. So sánh Get API, Multi Get và Search API

| Tiêu chí | Get API | Multi Get API | Search API |
|---|---|---|---|
| Đầu vào | Một ID | Danh sách ID | Query DSL |
| Số document | Một | Nhiều ID đã biết | Một hoặc nhiều kết quả phù hợp |
| Tìm theo field nghiệp vụ | Không | Không | Có |
| Full-text query | Không | Không | Có |
| Relevance score | Không | Không | Có thể có |
| Aggregation | Không | Không | Có |
| Sort và phân trang | Không | Không | Có |
| Tính sẵn sàng sau ghi | Realtime mặc định | Realtime mặc định cho từng document | Near-real-time sau refresh |
| Trường hợp điển hình | Chi tiết theo ID | Tải nhiều document theo ID | Tìm kiếm và lọc |

## 7. Truy vấn bằng ID qua Search API có gì khác Get API?

Elasticsearch cũng có `ids` query:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "ids": {
      "values": ["KB-1001", "KB-1002"]
    }
  }
}
~~~

Query này tìm các document có ID nằm trong danh sách. Tuy nhiên, nó vẫn chạy qua Search API và phụ thuộc vào search visibility sau refresh.

So sánh:

~~~http
GET /products/_doc/KB-1001
~~~

và:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "ids": {
      "values": ["KB-1001"]
    }
  }
}
~~~

Cả hai đều nhắm tới ID, nhưng đường thực thi khác nhau:

- Get API đọc trực tiếp một document theo index và ID.
- `ids` query là một truy vấn search, trả về Search Hits và tuân theo near-real-time visibility.

Dùng Get API khi cần một document cụ thể. Dùng `ids` query khi cần kết hợp danh sách ID với các điều kiện search khác, hoặc cần kết quả dưới dạng Search Hits cùng sort, aggregation và các khả năng của Search API.

## 8. Sử dụng lấy trực tiếp theo ID trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp Repository abstraction và `ElasticsearchOperations` cho thao tác đọc theo ID.

### Dùng ElasticsearchRepository.findById

Repository có thể khai báo:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
~~~

Đọc theo ID:

~~~java
import java.util.Optional;

Optional<ProductDocument> product =
        productRepository.findById("KB-1001");
~~~

`findById` là thao tác đọc theo định danh của entity. Kiểu ID phải khớp generic ID trong repository.

Kết quả là `Optional`:

- Có document: `Optional.of(product)`.
- Không có document: `Optional.empty()`.

Ví dụ service:

~~~java
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class ProductService {

    private final ProductRepository repository;

    public ProductDocument getRequired(String id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Product not found: " + id
                        )
                );
    }
}
~~~

Không dùng `findById` để tìm theo SKU nếu SKU không phải giá trị được ánh xạ vào `@Id`. Khi đó, cần dùng finder method theo field hoặc Search API.

### Dùng ElasticsearchOperations.get

Có thể đọc trực tiếp qua `ElasticsearchOperations`:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductLookupService {

    private final ElasticsearchOperations operations;

    public ProductLookupService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public ProductDocument getById(String id) {
        return operations.get(id, ProductDocument.class);
    }
}
~~~

`operations.get(id, ProductDocument.class)` lấy document theo ID và chuyển đổi thành entity `ProductDocument`. Kết quả không tìm thấy thường được biểu diễn bằng `null`; hãy xử lý trường hợp này trước khi sử dụng.

Repository phù hợp với CRUD thông thường. `ElasticsearchOperations` hữu ích khi service cần kiểm soát rõ loại entity, index metadata hoặc kết hợp với các thao tác Spring Data khác.

## 9. Sử dụng Search API trong Spring Data Elasticsearch

Khi tìm theo tên, trạng thái, khoảng giá hoặc nhiều field, hãy dùng search query.

Ví dụ với `NativeQuery` và Elasticsearch Java API Client:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

public SearchHits<ProductDocument> searchByName(
        ElasticsearchOperations operations,
        String text
) {
    Query query = Query.of(q -> q
            .match(m -> m
                    .field("name")
                    .query(text)
            )
    );

    NativeQuery nativeQuery = NativeQuery.builder()
            .withQuery(query)
            .build();

    return operations.search(nativeQuery, ProductDocument.class);
}
~~~

Trong ví dụ:

- `Query` biểu diễn query DSL của Elasticsearch Java API Client.
- `match` tìm kiếm toàn văn trên field `name`.
- `NativeQuery` đóng gói query để Spring Data thực thi.
- `operations.search(...)` trả về `SearchHits`, bao gồm metadata và các kết quả phù hợp.

Có thể dùng `term` để lọc chính xác theo trạng thái:

~~~java
Query query = Query.of(q -> q
        .term(t -> t
                .field("status")
                .value("PUBLISHED")
        )
);
~~~

Trong ứng dụng thực tế, nên kết hợp các điều kiện trong `bool` query, dùng `filter` cho điều kiện lọc không cần relevance score và `must` cho phần tìm kiếm toàn văn.

### Search bằng repository finder method

Spring Data cũng hỗ trợ query derivation theo tên method:

~~~java
import java.util.List;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByStatus(String status);

    List<ProductDocument> findBySku(String sku);
}
~~~

Các finder method này tìm theo field trong entity, không phải lấy trực tiếp theo `@Id`. Nếu cần full-text query, nhiều điều kiện, sort hoặc aggregation phức tạp, dùng query tùy chỉnh hoặc `ElasticsearchOperations.search(...)`.

## 10. Khi nào chọn ID và khi nào chọn search field?

Hãy dựa vào loại thông tin đầu vào và mục đích thao tác.

| Yêu cầu nghiệp vụ | Cách phù hợp |
|---|---|
| Mở trang chi tiết sản phẩm theo ID trong URL | Get API / `findById` |
| Kiểm tra một document theo ID đã biết | Get API |
| Lấy nhiều document theo danh sách ID | Multi Get API |
| Tìm sản phẩm theo tên | Search API với `match` |
| Tìm theo SKU nhưng SKU không phải document ID | Search API với `term` hoặc repository finder |
| Lọc theo trạng thái và khoảng giá | Search API với `bool`, `filter`, `range` |
| Tìm theo nhiều điều kiện và tính relevance | Search API |
| Đếm số sản phẩm theo trạng thái | Search API với aggregation |

Ví dụ thực tế:

- Frontend gọi `GET /api/products/KB-1001`: service thường dùng `findById("KB-1001")`.
- Frontend gọi `GET /api/products?keyword=keyboard`: service cần Search API với full-text query.
- Frontend gọi `GET /api/products?status=PUBLISHED`: service có thể dùng repository finder hoặc Search API với filter.
- Một job đã có danh sách ID từ hệ thống khác: cân nhắc Multi Get thay vì chạy một query search cho từng ID.

## 11. Lưu ý về routing và index alias

### Custom routing

Elasticsearch có thể dùng routing để xác định shard chứa document. Khi index document với routing tùy chỉnh, thao tác Get hoặc Multi Get cần cung cấp cùng routing value để truy cập đúng shard.

Ví dụ index với routing:

~~~http
PUT /products/_doc/KB-1001?routing=tenant-42
Content-Type: application/json

{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard"
}
~~~

Đọc lại cần cùng routing:

~~~http
GET /products/_doc/KB-1001?routing=tenant-42
~~~

Nếu bỏ routing hoặc truyền sai routing, Get API có thể không tìm thấy document dù document tồn tại trên shard khác. Với ứng dụng multi-tenant, hãy bảo đảm routing được truyền nhất quán qua các thao tác ghi, đọc, cập nhật và xóa.

### Index alias

Ứng dụng có thể dùng alias thay vì tên index vật lý:

~~~java
@Document(
    indexName = "products",
    createIndex = false
)
public class ProductDocument {
    // ...
}
~~~

Alias `products` có thể trỏ tới index versioned như `products-v1`. Khi dùng alias, cần hiểu alias đang trỏ tới index nào và có thể trỏ tới nhiều index hay không.

Get API cần một document ID trong phạm vi index đích. Nếu alias trỏ tới nhiều index, không nên coi Get API như một phép tìm kiếm ID trên tất cả index. Khi cần tìm document theo ID trên nhiều index, dùng Search API với `ids` query hoặc xác định index cụ thể trước khi Get.

## 12. Các lỗi thường gặp

### Dùng findById với business key

Nếu `@Id` ánh xạ thuộc tính `id`, gọi `findById("KB-1001")` sẽ tìm document có ID `KB-1001`. Nó không tự tìm field `sku` trừ khi SKU chính là document ID.

Hãy kiểm tra mapping entity và phân biệt rõ ID với business key.

### Tìm kiếm ngay sau save nhưng chưa refresh

Get API có thể đọc document mới trong khi Search API chưa thấy document đó. Nếu luồng nghiệp vụ cần tìm kiếm ngay, cân nhắc `refresh=wait_for` tại thao tác ghi thay vì ép refresh mỗi request.

### Dùng Search API để lấy một document đã biết ID

Nếu chỉ cần một document theo ID, Search API có thêm overhead của search và chịu độ trễ refresh. Dùng Get API thường phù hợp hơn.

### Dùng Get API để tìm theo một phần tên

Get API không hỗ trợ full-text query. Muốn tìm theo nội dung, dùng `match` trên Search API.

### Quên routing

Document đã được index với custom routing nhưng thao tác Get dùng routing mặc định có thể không tìm thấy. Truyền cùng routing đã dùng lúc ghi.

### Nhầm _id với field trong _source

`_id` là metadata định danh. Nếu muốn truy vấn theo mã nghiệp vụ, hãy lưu mã đó thành field riêng và map đúng kiểu dữ liệu.

## 13. Quy trình lựa chọn trong service

Khi xây dựng một service đọc dữ liệu, có thể thực hiện theo các bước:

1. Xác định đầu vào là document ID hay một điều kiện tìm kiếm.
2. Nếu đã có ID và biết index đích, dùng repository `findById` hoặc `ElasticsearchOperations.get`.
3. Nếu có nhiều ID đã biết, cân nhắc Multi Get.
4. Nếu tìm theo field nghiệp vụ, dùng repository finder hoặc Search API.
5. Nếu cần full-text, scoring, sort, aggregation hoặc nhiều điều kiện, dùng Search API.
6. Nếu ghi xong cần tìm kiếm ngay, hiểu rõ refresh visibility và chọn refresh policy phù hợp.
7. Nếu có custom routing hoặc alias nhiều index, xác định đúng index/routing cho thao tác đọc.

## Kết luận

Lấy trực tiếp theo ID và tìm kiếm qua index phục vụ hai nhu cầu khác nhau. Get API và `findById` đọc một document đã biết định danh theo cơ chế realtime; Search API tìm các document thỏa query dựa trên search index và có tính near-real-time sau refresh. Hãy dùng ID cho thao tác đọc chi tiết, Multi Get cho nhiều ID đã biết, và Search API cho truy vấn theo field, full-text, filter, sort hoặc aggregation.
