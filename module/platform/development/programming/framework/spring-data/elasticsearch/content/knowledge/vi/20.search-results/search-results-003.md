# Đọc _score, sort values, tên index và định danh kết quả

Khi tìm kiếm bằng Elasticsearch, kết quả không chỉ là danh sách document. Mỗi kết quả còn mang metadata giúp ứng dụng hiểu vì sao document được trả về, thứ tự sắp xếp, document nằm trong index nào và định danh của nó là gì.

Trong Spring Data Elasticsearch, các metadata này được cung cấp qua `SearchHit<T>` và `SearchHits<T>`. Khi làm việc với Java API Client trực tiếp, các thông tin tương ứng nằm trong từng hit của `SearchResponse<T>`.

Bốn thông tin cần đọc đúng:

- **`_score`**: điểm liên quan do Elasticsearch tính cho kết quả khi query có scoring.
- **Sort values**: các giá trị thực tế được dùng để sắp xếp một hit, đồng thời có thể dùng làm con trỏ cho `search_after`.
- **Index name (`_index`)**: index vật lý chứa document được trả về.
- **Document ID (`_id`)**: định danh document trong index đó.

Các metadata này hữu ích khi xây trang kết quả tìm kiếm, giải thích thứ tự, phân trang sâu, xử lý index versioning và tạo liên kết tới document cụ thể.

## 1. SearchHit và SearchHits trong Spring Data Elasticsearch

Khi gọi `ElasticsearchOperations.search(...)`, Spring Data Elasticsearch thường trả về `SearchHits<T>` thay vì chỉ trả về một danh sách entity.

Hai kiểu có vai trò khác nhau:

| Kiểu | Vai trò |
|---|---|
| `SearchHit<T>` | Đại diện cho một kết quả, gồm entity và metadata của hit |
| `SearchHits<T>` | Bao bọc toàn bộ kết quả tìm kiếm và metadata cấp response |

Ví dụ:

~~~java
SearchHits<ProductDocument> searchHits =
        operations.search(query, ProductDocument.class);

for (SearchHit<ProductDocument> hit : searchHits) {
    ProductDocument product = hit.getContent();

    String id = hit.getId();
    String index = hit.getIndex();
    float score = hit.getScore();
    List<Object> sortValues = hit.getSortValues();
}
~~~

Một `SearchHit<T>` thường cung cấp:

- `getContent()`: entity đã được Spring Data chuyển đổi từ document.
- `getId()`: document ID, tương ứng metadata `_id`.
- `getIndex()`: tên index chứa document.
- `getScore()`: điểm liên quan `_score` của hit.
- `getSortValues()`: danh sách giá trị sort theo thứ tự các sort clause.
- Các metadata khác như highlight hoặc explanation khi response và query có yêu cầu tương ứng.

`SearchHits<T>` cung cấp thông tin ở cấp tập kết quả, chẳng hạn tổng số hit, max score, danh sách hit và aggregation nếu có.

Không nên chỉ gọi `getContent()` rồi bỏ toàn bộ `SearchHit` nếu giao diện cần hiển thị điểm liên quan, index nguồn, định danh hoặc hỗ trợ phân trang bằng sort values.

## 2. _score là gì?

`_score` là điểm liên quan mà Elasticsearch tính cho một document đối với query hiện tại. Với truy vấn tìm kiếm toàn văn như `match`, điểm này giúp xếp hạng document theo mức độ phù hợp với từ khóa và các yếu tố liên quan trong thuật toán scoring.

Ví dụ:

~~~json
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Một kết quả có thể có dạng:

~~~json
{
  "_index": "products-v2",
  "_id": "P-1001",
  "_score": 3.82,
  "_source": {
    "name": "Wireless Mechanical Keyboard"
  }
}
~~~

Trong đó:

- `_score: 3.82` là điểm liên quan của hit với query này.
- Điểm cao hơn thường cho biết document phù hợp hơn trong cùng ngữ cảnh truy vấn.
- Điểm không phải phần trăm, xác suất hay đánh giá chất lượng tuyệt đối.

### _score được tính từ đâu?

Với full-text search, Elasticsearch thường dùng thuật toán BM25 làm similarity mặc định. Điểm có thể phụ thuộc vào:

- Mức độ khớp term giữa query và document.
- Tần suất term trong document.
- Độ phổ biến của term trong tập document.
- Độ dài field so với độ dài trung bình.
- Cấu trúc query, boost và các scoring function được cấu hình.

Vì điểm phụ thuộc cả query lẫn dữ liệu trong index, không nên so sánh trực tiếp `_score` của hai query khác nhau như thể chúng cùng một thang đo.

### Khi nào score không có ý nghĩa xếp hạng?

Không phải query nào cũng cần scoring:

- `term` trong `filter` dùng để giới hạn kết quả, không tính relevance score.
- `exists` trong filter chỉ kiểm tra field có giá trị được lập chỉ mục.
- Query chỉ có filter không dùng điểm liên quan để quyết định thứ tự.
- `match_all` có thể trả một điểm giống nhau cho các document, nên điểm không giúp phân biệt mức độ phù hợp.

Nếu query có scoring nhưng request sắp xếp theo field như giá hoặc ngày, thứ tự kết quả được quyết định bởi sort field. Elasticsearch có thể không tính score khi sort theo field nếu không yêu cầu theo dõi score.

### Muốn giữ score khi sort theo field

Search request hỗ trợ `track_scores`. Khi bật, Elasticsearch vẫn tính và trả score dù kết quả được sắp xếp theo field.

Ví dụ request:

~~~http
POST /products/_search
Content-Type: application/json

{
  "track_scores": true,
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ]
}
~~~

Kết quả được sắp xếp theo giá tăng dần, nhưng score vẫn được tính và trả về để ứng dụng có thể hiển thị hoặc phân tích. Bật `track_scores` có chi phí tính toán; chỉ dùng khi ứng dụng thực sự cần score trong trường hợp sort theo field.

## 3. Đọc score bằng SearchHit

Ví dụ service:

~~~java
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void printResults(Query query) {
        SearchHits<ProductDocument> results =
                operations.search(query, ProductDocument.class);

        for (SearchHit<ProductDocument> hit : results) {
            ProductDocument product = hit.getContent();

            System.out.println("Name: " + product.getName());
            System.out.println("Score: " + hit.getScore());
        }
    }
}
~~~

`getScore()` đọc score được trả về cho từng hit. Nếu query hoặc cách sort không yêu cầu scoring, đừng giả định score là một giá trị xếp hạng hữu ích. Hãy xác định query có scoring hay không và có bật track scores khi sort theo field hay không.

Ở tầng API, nên quyết định có cần trả score ra client hay không. Thường score hữu ích cho debug, relevance tuning hoặc giao diện chuyên biệt; phần lớn API nghiệp vụ không cần công khai điểm này như một chỉ số chất lượng.

## 4. Sort values là gì?

Khi Search API sắp xếp kết quả, mỗi hit có thể chứa mảng `sort` trong response. Đây là các giá trị thực tế của từng sort clause đối với document đó.

Ví dụ request:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    },
    {
      "createdAt": {
        "order": "desc"
      }
    }
  ]
}
~~~

Một hit có thể trả về:

~~~json
{
  "_index": "products-v2",
  "_id": "P-1001",
  "_score": 1.74,
  "sort": [
    1299000,
    "2026-10-20T08:30:00.000Z"
  ],
  "_source": {
    "name": "Wireless Keyboard",
    "price": 1299000,
    "createdAt": "2026-10-20T08:30:00.000Z"
  }
}
~~~

Mảng sort có hai phần tử vì request có hai sort clause:

1. `1299000` là giá trị của field `price`.
2. `"2026-10-20T08:30:00.000Z"` là giá trị của field `createdAt`.

Thứ tự trong mảng phải khớp thứ tự sort clause của request. Kiểu dữ liệu cũng được giữ theo kiểu giá trị sort: number, string hoặc kiểu tương ứng mà Elasticsearch trả về.

Sort values không phải toàn bộ dữ liệu entity và cũng không phải một danh sách field name. Chúng là các giá trị dùng để xác định vị trí của hit trong thứ tự kết quả.

### Đọc sort values bằng Spring Data

~~~java
for (SearchHit<ProductDocument> hit : searchHits) {
    List<Object> values = hit.getSortValues();

    System.out.println("Sort values: " + values);
}
~~~

Nếu sort theo `price` rồi `createdAt`, danh sách sort values có thứ tự tương ứng. Khi cần dùng các giá trị này cho phân trang tiếp theo, giữ nguyên cả danh sách và thứ tự; không tự chuyển mọi giá trị thành chuỗi.

## 5. Sort values dùng cho search_after

Với phân trang thông thường, ứng dụng có thể dùng `from` và `size`. Nhưng khi đi sâu vào nhiều trang, `from/size` ngày càng tốn tài nguyên vì Elasticsearch phải xử lý và giữ các kết quả trước vị trí cần trả về.

`search_after` cho phép tiếp tục từ sort values của hit cuối cùng ở trang trước.

Ví dụ trang đầu:

~~~http
POST /products/_search
Content-Type: application/json

{
  "size": 2,
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    },
    {
      "productId": {
        "order": "asc"
      }
    }
  ]
}
~~~

Giả sử hit cuối cùng của trang đầu có sort values:

~~~json
"sort": [1299000, "P-1002"]
~~~

Request trang tiếp theo truyền chính mảng đó vào `search_after`:

~~~http
POST /products/_search
Content-Type: application/json

{
  "size": 2,
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    },
    {
      "productId": {
        "order": "asc"
      }
    }
  ],
  "search_after": [1299000, "P-1002"]
}
~~~

Request tiếp theo phải giữ nguyên query và thứ tự sort. Elasticsearch trả các hit đứng sau vị trí được chỉ ra bởi sort values.

### Vì sao cần sort có thứ tự ổn định?

Nếu chỉ sort theo `price`, nhiều document có thể cùng giá. Khi đó, thứ tự giữa các document bằng giá có thể không ổn định giữa các request, khiến kết quả phân trang bị lặp hoặc bỏ sót.

Hãy thêm một field tie-breaker duy nhất, chẳng hạn `productId` kiểu keyword, có doc values:

~~~json
{
  "mappings": {
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "price": {
        "type": "long"
      }
    }
  }
}
~~~

Không nên sort trực tiếp theo metadata `_id` như một field thông thường. `_id` không được thiết kế để sort/aggregate theo cách của keyword field có doc values. Nếu cần tie-breaker nghiệp vụ, lưu ID đó thêm thành field keyword riêng như `productId`.

Với phân trang ổn định qua nhiều request trong lúc dữ liệu có thể thay đổi, nên cân nhắc Point in Time (PIT) kết hợp `search_after`. PIT giữ một góc nhìn nhất quán của index trong khoảng thời gian được chỉ định; Elasticsearch có thể dùng `_shard_doc` làm tie-breaker nội bộ khi tìm kiếm qua PIT.

## 6. Sort field phải có mapping phù hợp

Không phải field nào cũng có thể dùng để sort hiệu quả.

| Kiểu field | Khả năng sort | Ghi chú |
|---|---|---|
| `keyword` | Có | Phù hợp cho mã, trạng thái, tên cần sắp xếp |
| Numeric (`integer`, `long`, `double`) | Có | Phù hợp cho giá, số lượng, điểm |
| `date` | Có | Phù hợp cho ngày tạo, ngày cập nhật |
| `text` | Không phù hợp mặc định | Thường dùng subfield keyword để sort |
| `object` | Không sort trực tiếp như scalar | Cần chọn field con |
| `nested` | Cần cấu hình nested sort | Phải xác định nested path |

Ví dụ entity có multi-field:

~~~java
@MultiField(
    mainField = @Field(type = FieldType.Text),
    otherFields = {
        @InnerField(suffix = "keyword", type = FieldType.Keyword)
    }
)
private String name;
~~~

Tìm kiếm toàn văn dùng `name`; sắp xếp theo tên dùng `name.keyword`.

Nếu một field có nhiều giá trị, sort có thể cần `mode` như `min`, `max`, `avg` hoặc `median` tùy kiểu dữ liệu và nhu cầu. Với nested object, cần khai báo nested sort để Elasticsearch biết giá trị con nào được dùng.

### Xử lý document thiếu giá trị sort

Sort hỗ trợ tùy chọn `missing` để đặt document thiếu giá trị lên đầu hoặc cuối:

~~~json
{
  "sort": [
    {
      "price": {
        "order": "asc",
        "missing": "_last"
      }
    }
  ]
}
~~~

`missing: "_last"` chỉ quyết định vị trí document thiếu giá trị trong thứ tự. Nó không loại document đó khỏi kết quả. Nếu muốn chỉ trả document có giá, thêm exists filter vào query.

## 7. Tên index trong kết quả tìm kiếm

Mỗi hit có metadata `_index`, cho biết index thực tế chứa document.

Ví dụ ứng dụng tìm kiếm qua alias:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
~~~

Giả sử alias `products` trỏ tới hai index:

- `products-v1`
- `products-v2`

Response có thể chứa các hit từ cả hai index. Mỗi hit trả `_index` tương ứng với index vật lý chứa document, ví dụ:

~~~json
{
  "_index": "products-v2",
  "_id": "P-1001",
  "_source": {
    "name": "Wireless Keyboard"
  }
}
~~~

Tên alias là đích request. Giá trị `_index` trong hit cho biết index cụ thể mà document được đọc ra từ đó.

Điều này quan trọng khi:

- Alias trỏ tới nhiều index trong giai đoạn migration.
- Cần truy vết dữ liệu đang nằm ở phiên bản index nào.
- Cần tạo liên kết tới document hoặc thực hiện thao tác tiếp theo.
- Cần phân tích kết quả đến từ index lịch sử hay index hiện hành.

### Đọc index name trong Spring Data

~~~java
for (SearchHit<ProductDocument> hit : searchHits) {
    String actualIndex = hit.getIndex();
    System.out.println("Index: " + actualIndex);
}
~~~

`getIndex()` cho biết index nguồn của hit. Nếu ứng dụng chỉ tìm trong một index cố định, giá trị này thường giống index đích. Khi tìm qua alias hoặc wildcard nhiều index, các hit có thể đến từ các index vật lý khác nhau.

## 8. Document ID trong kết quả

`_id` là định danh document trong phạm vi một index. Nó không tự động duy nhất trên toàn cluster.

Ví dụ:

| Index | _id | Ý nghĩa |
|---|---|---|
| `products-v1` | `P-1001` | Document trong index v1 |
| `products-v2` | `P-1001` | Document khác trong index v2 |
| `orders` | `P-1001` | Document trong index orders |

Cùng một ID có thể tồn tại ở nhiều index. Vì vậy, khi cần định danh chính xác một hit trong kết quả tìm kiếm nhiều index, hãy xem cặp **(`_index`, `_id`)** là định danh vị trí của document.

### Đọc ID bằng Spring Data

~~~java
for (SearchHit<ProductDocument> hit : searchHits) {
    String documentId = hit.getId();
    ProductDocument product = hit.getContent();

    System.out.println("ID: " + documentId);
    System.out.println("Product name: " + product.getName());
}
~~~

ID lấy từ `SearchHit.getId()` là metadata document ID. Nó không nhất thiết phải được đọc từ một field trong `_source`.

### Liên hệ với @Id trong entity

Spring Data Elasticsearch dùng annotation:

~~~java
import org.springframework.data.annotation.Id;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    private String name;
}
~~~

`@Id` ánh xạ thuộc tính Java `id` với metadata `_id`. Nếu document được index bằng ID do ứng dụng gán hoặc Elasticsearch sinh, Spring Data có thể đưa giá trị định danh vào entity theo mapping metadata.

Nếu ứng dụng có business key riêng như `sku`, hãy phân biệt rõ business key với document ID. `sku` là field nghiệp vụ có mapping riêng; `_id` là metadata định danh document.

### Khi cần lấy document tiếp theo bằng ID

Nếu đã có hit và muốn đọc trực tiếp document, cần biết đúng index và ID. Với custom routing, thao tác Get còn cần cùng routing value đã dùng khi index document.

Đừng chỉ giữ ID nếu kết quả có thể đến từ nhiều index. ID `P-1001` ở `products-v1` khác với ID cùng tên ở `products-v2`.

## 9. Đọc đồng thời score, sort values, index và ID

Ví dụ service trích xuất metadata cho từng kết quả:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductResultService {

    private final ElasticsearchOperations operations;

    public ProductResultService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void printMetadata(Query query) {
        SearchHits<ProductDocument> results =
                operations.search(query, ProductDocument.class);

        System.out.println("Total hits: " + results.getTotalHits());
        System.out.println("Max score: " + results.getMaxScore());

        for (SearchHit<ProductDocument> hit : results) {
            String id = hit.getId();
            String index = hit.getIndex();
            float score = hit.getScore();
            List<Object> sortValues = hit.getSortValues();

            ProductDocument content = hit.getContent();

            System.out.println("ID: " + id);
            System.out.println("Index: " + index);
            System.out.println("Score: " + score);
            System.out.println("Sort values: " + sortValues);
            System.out.println("Name: " + content.getName());
        }
    }
}
~~~

Ví dụ minh họa cách đọc metadata từ SearchHits. Kiểu query và entity cần được import theo dự án; nếu dùng NativeQuery, kiểu query bên trong là Elasticsearch Java Client Query, còn tham số của operations là Spring Data Query abstraction.

Nếu response không có sort clause, danh sách sort values có thể rỗng. Nếu không có scoring, score không nên được xem là tín hiệu xếp hạng. Luôn đọc metadata trong ngữ cảnh request đã tạo ra nó.

## 10. Xây dựng NativeQuery có sort

Với Spring Data Elasticsearch 5.x, có thể tạo query DSL bằng Elasticsearch Java API Client và đóng gói trong `NativeQuery`.

Ví dụ tìm theo tên và sắp xếp theo giá tăng dần, sau đó theo mã sản phẩm:

~~~java
import co.elastic.clients.elasticsearch._types.SortOrder;
import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.domain.PageRequest;

Query query = Query.of(q -> q
        .match(m -> m
                .field("name")
                .query("wireless keyboard")
        )
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(query)
        .withSort(
                SortOptions.of(s -> s.field(f -> f
                        .field("price")
                        .order(SortOrder.Asc)
                )),
                SortOptions.of(s -> s.field(f -> f
                        .field("productId")
                        .order(SortOrder.Asc)
                ))
        )
        .withPageable(PageRequest.of(0, 20))
        .build();

SearchHits<ProductDocument> hits =
        operations.search(nativeQuery, ProductDocument.class);
~~~

Trong ví dụ, `price` và `productId` là hai sort clause. Thứ tự sort values của mỗi hit sẽ lần lượt là giá và mã sản phẩm.

Nếu cần đọc score trong khi sort theo field, hãy bật track scores bằng API builder tương ứng của phiên bản Spring Data Elasticsearch đang dùng hoặc thiết lập `track_scores: true` trong search request. Không mặc định rằng score luôn được tính khi sort theo field.

## 11. Dùng sort values cho phân trang sâu

`SearchHit.getSortValues()` cung cấp các giá trị để ứng dụng có thể lưu con trỏ trang tiếp theo.

Về mặt request, trang tiếp theo có dạng:

~~~json
{
  "size": 20,
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    },
    {
      "productId": {
        "order": "asc"
      }
    }
  ],
  "search_after": [1299000, "P-1002"]
}
~~~

Trong Spring Data, có thể lấy sort values từ hit cuối:

~~~java
SearchHit<ProductDocument> lastHit =
        hits.getSearchHits().get(hits.getSearchHits().size() - 1);

List<Object> nextSearchAfter = lastHit.getSortValues();
~~~

Sau đó truyền `nextSearchAfter` vào cơ chế `search_after` của query builder/API tương ứng với phiên bản đang dùng. `NativeQuery` và các API hỗ trợ search_after có thể thay đổi theo phiên bản; cần đối chiếu đúng dependency của dự án.

Các nguyên tắc bắt buộc:

- Giữ nguyên query giữa các trang.
- Giữ nguyên thứ tự và kiểu dữ liệu sort values.
- Dùng sort có thứ tự ổn định, có tie-breaker duy nhất.
- Với dữ liệu thay đổi liên tục, cân nhắc PIT để giữ snapshot nhất quán.
- Không tự tạo lại sort values từ entity nếu response đã cung cấp giá trị chính xác.

Không dùng `from` lớn để mô phỏng search_after. `search_after` được thiết kế cho phân trang sâu và tránh phải bỏ qua lượng lớn hit ở các trang trước.

## 12. Khác biệt giữa metadata hit và dữ liệu _source

Một hit có thể chứa cả metadata và source:

~~~json
{
  "_index": "products-v2",
  "_id": "P-1001",
  "_score": 2.17,
  "sort": [1299000, "P-1001"],
  "_source": {
    "productId": "P-1001",
    "name": "Wireless Keyboard",
    "price": 1299000
  }
}
~~~

Phân biệt:

| Thành phần | Nguồn | Mục đích |
|---|---|---|
| `_index` | Hit metadata | Index vật lý chứa document |
| `_id` | Hit metadata | Document ID |
| `_score` | Hit metadata | Điểm liên quan |
| `sort` | Hit metadata | Giá trị dùng sắp xếp và search_after |
| `_source` | Nội dung document | Dữ liệu entity/document |

Một thuộc tính `productId` trong `_source` có thể trùng giá trị với `_id`, nhưng hai giá trị có vai trò khác nhau. Nếu source filtering loại bỏ field `productId`, metadata `_id` vẫn có thể được trả về.

Ngược lại, nếu request tắt hoặc lọc source, ứng dụng có thể không có đủ field để dựng entity hoàn chỉnh, nhưng vẫn đọc được metadata hit.

## 13. Dùng metadata khi tìm qua alias hoặc nhiều index

Một alias có thể trỏ tới một hoặc nhiều index. Ví dụ:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
~~~

Nếu alias `products` trỏ tới `products-v1` và `products-v2`, kết quả có thể chứa document từ cả hai nơi.

Ứng dụng nên giữ metadata:

~~~java
for (SearchHit<ProductDocument> hit : searchHits) {
    String sourceIndex = hit.getIndex();
    String documentId = hit.getId();

    // Ghi nhận cặp index + id để truy vết kết quả.
}
~~~

Điều này đặc biệt quan trọng khi:

- Cùng document ID tồn tại ở nhiều index.
- Các phiên bản mapping đang được chuyển đổi.
- Cần biết document nào đến từ index lịch sử.
- Cần xử lý kết quả trùng lặp ở tầng ứng dụng.

Nếu hai index cùng chứa một sản phẩm, Elasticsearch có thể trả hai hit riêng biệt. Alias không tự hợp nhất document trùng ID giữa các index. Nếu muốn loại trùng theo business key, ứng dụng cần có quy tắc hợp nhất rõ ràng.

## 14. Những lỗi thường gặp

### Coi _score là phần trăm phù hợp

Score là giá trị ranking nội bộ theo query và dữ liệu index. Không hiển thị `0.82 = 82% phù hợp` nếu không có mô hình hiệu chuẩn riêng.

### So sánh score giữa hai query khác nhau

Thay đổi query, analyzer, corpus hoặc index có thể làm thang điểm thay đổi. Không dùng score của hai request độc lập để kết luận document nào tốt hơn một cách tuyệt đối.

### Sort theo field nhưng vẫn kỳ vọng score được trả về

Khi sort theo field, score có thể không được tính nếu không bật track scores. Nếu giao diện cần cả sort field và score, hãy cấu hình `track_scores`.

### Quên tie-breaker khi dùng search_after

Nhiều document có thể có cùng giá hoặc ngày. Thêm một field keyword duy nhất vào cuối sort để thứ tự ổn định.

### Dùng _id làm sort field

`_id` là metadata định danh và không phải field có doc values để sort/aggregation như keyword thông thường. Lưu một bản sao ID trong field keyword nếu cần sort hoặc tie-breaker nghiệp vụ.

### Chỉ lưu ID mà bỏ index name

Khi tìm qua nhiều index, cùng một ID có thể xuất hiện ở nhiều nơi. Giữ cặp index và ID nếu cần định danh chính xác kết quả.

### Nhầm alias với tên index trả về

Request có thể dùng alias `products`, nhưng hit metadata cho biết index vật lý như `products-v2`. Đây là hai khái niệm khác nhau.

### Tự tạo sort values từ source

Giá trị sort có thể đã được chuẩn hóa hoặc xử lý theo mapping, missing policy, nested sort hay multi-value mode. Dùng `getSortValues()` từ hit để làm con trỏ search_after.

### Không giữ nguyên sort giữa các trang

`search_after` yêu cầu cùng thứ tự sort và query. Thay đổi sort hoặc kiểu dữ liệu giá trị có thể làm phân trang sai.

## 15. Quy trình sử dụng metadata kết quả

Khi xây dựng API hoặc giao diện tìm kiếm:

1. Chọn query và sort phù hợp với mục tiêu tìm kiếm.
2. Xác định có cần hiển thị score hay chỉ dùng score để debug.
3. Nếu sort theo field nhưng vẫn cần score, bật track scores.
4. Đọc entity qua `SearchHit.getContent()`.
5. Đọc định danh qua `getId()` và index nguồn qua `getIndex()`.
6. Đọc sort values qua `getSortValues()` khi cần search_after.
7. Dùng field có mapping hỗ trợ sort; không sort trực tiếp trên text hoặc metadata _id.
8. Thêm tie-breaker duy nhất để thứ tự ổn định.
9. Với phân trang sâu hoặc dữ liệu biến động, dùng search_after kết hợp PIT.
10. Khi truy vấn qua alias nhiều index, giữ index + ID để truy vết.
11. Chỉ trả metadata cần thiết ra API response; không nhất thiết công khai toàn bộ Elasticsearch internals cho client.
12. Kiểm tra mapping, query và response thực tế trước khi phụ thuộc vào metadata trong nghiệp vụ.

## Kết luận

`SearchHit<T>` chứa entity cùng metadata của từng kết quả: score, sort values, tên index và document ID. `_score` phản ánh mức độ liên quan trong ngữ cảnh query; sort values ghi lại các giá trị sắp xếp và hỗ trợ `search_after`; `_index` xác định index vật lý chứa hit; `_id` định danh document trong index đó. Trong Spring Data Elasticsearch, hãy giữ lại `SearchHit` khi cần metadata, dùng sort có tie-breaker ổn định và xem cặp index + ID là định danh vị trí của kết quả khi tìm qua nhiều index.
