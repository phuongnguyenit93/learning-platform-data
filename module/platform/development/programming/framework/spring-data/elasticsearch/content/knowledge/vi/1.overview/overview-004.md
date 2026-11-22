# Luồng xử lý từ lời gọi Java đến yêu cầu HTTP và kết quả tìm kiếm

Khi một ứng dụng Spring gọi phương thức tìm kiếm của Spring Data Elasticsearch, lời gọi đó đi qua nhiều lớp trước khi trở thành một yêu cầu HTTP. Elasticsearch xử lý yêu cầu trên các shard, trả về JSON, rồi Spring Data chuyển từng hit thành đối tượng Java và đóng gói metadata cho ứng dụng.

Có thể chia toàn bộ luồng thành bốn chặng:

1. **Lời gọi Java:** service gọi repository hoặc `ElasticsearchOperations`.
2. **Chuẩn bị yêu cầu:** Spring Data xác định index, chuyển query, sort và phân trang thành request của Elasticsearch Java API Client.
3. **Trao đổi HTTP và thực thi tìm kiếm:** client gửi request đến cluster; node điều phối phân phối công việc đến các shard.
4. **Đọc kết quả:** client nhận response; Spring Data chuyển `_source` thành entity và trả kết quả cho service.

Bài học tập trung vào đường tìm kiếm đồng bộ thường gặp trong ứng dụng Spring. Một số chi tiết của lớp client và cấu hình transport thay đổi theo phiên bản Spring Data Elasticsearch và Elasticsearch đang dùng.

## 1. Bắt đầu từ lời gọi Java

Một ứng dụng thường không tự tạo HTTP request. Code nghiệp vụ gọi một phương thức có kiểu dữ liệu rõ ràng, chẳng hạn repository:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private double price;

    // constructors, getters, setters
}

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);
}
~~~

Service sử dụng repository như một dependency thông thường:

~~~java
@Service
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public List<Product> findProductsInCategory(String category) {
        return productRepository.findByCategory(category);
    }
}
~~~

Khi controller gọi `findProductsInCategory("computer")`, service gọi `findByCategory("computer")`. Tại thời điểm này, ứng dụng vẫn đang làm việc với Java object và kiểu trả về `List<Product>`. Repository chưa phải là một HTTP client mà là giao diện Spring Data cung cấp.

### Repository proxy tiếp nhận lời gọi

Spring Data tạo implementation cho repository trong lúc khởi động ứng dụng. Thông thường, đối tượng được inject vào service là một proxy do Spring quản lý.

Khi code gọi `findByCategory`, proxy chuyển lời gọi đến cơ chế thực thi query của Spring Data:

- Các phương thức nền tảng như `save`, `findById` và `deleteById` được xử lý bởi implementation repository cơ sở.
- Phương thức truy vấn khai báo bằng tên như `findByCategory` được phân tích theo quy tắc đặt tên của Spring Data.
- Phương thức có `@Query` sử dụng query được khai báo trong annotation.
- Phương thức tùy biến có thể gọi trực tiếp `ElasticsearchOperations`.

Với `findByCategory`, Spring Data phân tích tên phương thức, nhận ra thuộc tính `category` và tham số cần so khớp. Nó tạo một đối tượng query nội bộ biểu diễn điều kiện tìm kiếm. Query DSL cuối cùng phụ thuộc vào loại field, mapping và phiên bản thư viện.

Ví dụ, `category` được khai báo là `keyword`, nên đây là field phù hợp cho phép so khớp chính xác. Nếu đổi field thành `text`, Elasticsearch có thể phân tích nội dung thành token; cách tìm kiếm và kết quả sẽ khác.

### Repository chuyển công việc cho lớp Operations

Repository thường ủy quyền phần thao tác Elasticsearch cho `ElasticsearchOperations`. Đây là abstraction của Spring Data dùng để thực hiện các thao tác như tìm kiếm, lưu, xóa và tạo index.

Implementation phổ biến trong các ứng dụng dùng Java API Client là `ElasticsearchTemplate`. Lớp template nhận query cùng thông tin entity, sau đó chuẩn bị request và gọi client.

Nếu service inject `ElasticsearchOperations` và gọi `search` trực tiếp, luồng sẽ bỏ qua repository proxy và bước phân tích tên phương thức. Những bước chuẩn bị request, gửi HTTP và chuyển đổi response vẫn diễn ra ở lớp operations và các lớp phía dưới.

## 2. Spring Data chuẩn bị request

Trước khi gửi request, Spring Data phải xác định **tìm ở đâu**, **tìm theo điều kiện nào** và **cần lấy kết quả nào**.

### Xác định entity và index

Kiểu entity truyền vào thao tác tìm kiếm giúp Spring Data tra cứu mapping metadata. Với ví dụ trên:

- `@Document(indexName = "products")` khai báo index mặc định của entity.
- `@Id` đánh dấu thuộc tính đại diện cho Elasticsearch document ID.
- `@Field` mô tả kiểu field và một số tùy chọn mapping như analyzer.
- Các metadata khác có thể mô tả date format, nested object, field name hoặc chiến lược mapping.

Index có thể là index cụ thể hoặc alias. Một số thao tác cho phép truyền `IndexCoordinates` để chỉ định index đích tại thời điểm gọi. Vì vậy, tên index cuối cùng đến từ metadata hoặc tham số của thao tác, không nhất thiết được viết cứng trong service.

Mapping trong class Java giúp Spring Data biết cách chuyển đổi dữ liệu. Mapping thực tế trên cluster vẫn là cấu hình của Elasticsearch. Nếu index đã tồn tại với mapping cũ, việc sửa annotation trong Java không đồng nghĩa Elasticsearch tự động thay đổi mapping hiện có. Cần kiểm tra mapping của index khi hành vi tìm kiếm không đúng như mong đợi.

### Tạo biểu diễn query

Spring Data hỗ trợ nhiều cách diễn đạt điều kiện tìm kiếm:

| Cách khai báo | Vai trò |
|---|---|
| Derived query, ví dụ `findByCategory` | Spring Data phân tích tên phương thức và tạo query |
| `@Query` | Khai báo nội dung query JSON cùng tham số |
| `CriteriaQuery` | Xây dựng điều kiện bằng API Criteria của Spring Data |
| `NativeQuery` | Xây dựng query dựa trên Elasticsearch Java API Client và Query DSL |
| `ElasticsearchOperations.search(...)` | Gọi lớp operations trực tiếp với một đối tượng `Query` |

Query còn có thể chứa các thông tin ngoài điều kiện lọc:

- `Pageable` xác định trang và kích thước trang.
- `Sort` xác định thứ tự sắp xếp.
- Highlight xác định field cần trích đoạn khớp.
- Aggregation yêu cầu Elasticsearch tính toán thống kê hoặc nhóm dữ liệu.
- Source filtering giới hạn các field lấy từ `_source`.
- Routing, preference và các tùy chọn tìm kiếm khác ảnh hưởng đến phạm vi hoặc cách thực thi request.

Các thông tin này được tổng hợp thành một yêu cầu tìm kiếm hoàn chỉnh.

### Chuyển query Spring Data thành request của Elasticsearch

Trong đường đi dùng Java API Client, lớp chuyển đổi request của Spring Data biến đối tượng `Query` thành request mà Elasticsearch client hiểu được, thường là một `SearchRequest`.

Quá trình này cần kết hợp:

- Index hoặc `IndexCoordinates`.
- Query DSL.
- `from` và `size` cho phân trang kiểu offset.
- Sort, source filter, highlight và aggregation nếu có.
- Routing hoặc các tùy chọn tìm kiếm khác nếu được cấu hình.

`ElasticsearchConverter` và mapping metadata cung cấp thông tin cần thiết để làm việc với entity. Khi lưu hoặc đọc entity, converter chịu trách nhiệm chuyển đổi giữa Java object và biểu diễn document. Phần chuyển query thành request cũng phải giữ đúng thông tin index và các tùy chọn mà Spring Data hỗ trợ.

Một điểm cần phân biệt: **đối tượng query Java không phải là JSON HTTP hoàn chỉnh**. Nó là mô hình ở tầng ứng dụng. Các lớp adapter và client mới chuyển mô hình đó thành request wire format.

## 3. Từ Elasticsearch Java API Client đến HTTP

Trong các cấu hình Spring Data Elasticsearch hiện đại, đường client phổ biến sử dụng Elasticsearch Java API Client (`co.elastic.clients.elasticsearch.ElasticsearchClient`) cùng transport và REST client bên dưới. Những dự án cũ có thể sử dụng client hoặc cấu hình transport khác; cần xem dependency và cấu hình thực tế của dự án để xác định đúng lớp đang chạy.

Java API Client cung cấp API Java có kiểu dữ liệu. Ứng dụng hoặc Spring Data không cần tự nối chuỗi JSON rồi tự quản lý HTTP cho từng truy vấn. Client nhận request object, serialize request và chuyển nó qua transport.

### Transport thực hiện việc trao đổi mạng

Transport chịu trách nhiệm gửi request đến một node Elasticsearch được cấu hình. Tùy cấu hình client, các thành phần ở tầng này có thể xử lý:

- Kết nối đến một hoặc nhiều node.
- Connection pooling và tái sử dụng kết nối.
- TLS/HTTPS.
- Authentication và HTTP headers.
- Timeout, lỗi kết nối và chính sách retry hoặc chuyển node theo cấu hình client.

Request được serialize thành HTTP method, URL, header và body. Với tìm kiếm trên một index cụ thể, request thường có dạng:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "laptop"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "computer"
          }
        }
      ]
    }
  },
  "from": 0,
  "size": 10
}
~~~

Đây là hình dạng HTTP minh họa cho một tìm kiếm; request thực tế có thể chứa thêm header, tham số URL hoặc các phần body khác. Nếu tìm trên nhiều index hoặc alias, phần đường dẫn có thể khác. Một số API cũng cho phép gửi request tìm kiếm ở endpoint cấp cluster.

Các thành phần chính trong ví dụ:

- `POST /products/_search`: gọi Search API trên index `products`.
- `match`: tìm nội dung `name` theo cách phân tích của field.
- `term`: so khớp giá trị chính xác trên field `keyword` như `category`.
- `from`: vị trí bắt đầu của trang kết quả.
- `size`: số hit tối đa cần lấy trong trang.

Với truy vấn phân trang sâu, `from`/`size` có thể tốn tài nguyên vì Elasticsearch phải giữ và sắp xếp nhiều kết quả trung gian. Với trường hợp cần duyệt lượng lớn dữ liệu, nên xem xét `search_after` kết hợp sort phù hợp hoặc cơ chế cuộn dữ liệu thích hợp với phiên bản Elasticsearch.

### HTTP request không chứa toàn bộ entity Java

Request tìm kiếm chủ yếu mô tả điều kiện và cách lấy document. Nó không gửi nguyên object `Product` lên cluster. Elasticsearch chỉ biết index, mapping và dữ liệu đã được lưu trong index.

Đường lưu dữ liệu có cùng ý tưởng phân lớp nhưng request khác. Chẳng hạn `save(product)` chuyển entity thành document rồi gọi API index hoặc update document. Một lần tìm kiếm tiếp theo đọc document đã được index; thời điểm document xuất hiện trong kết quả còn phụ thuộc refresh của Elasticsearch.

## 4. Elasticsearch tiếp nhận và thực thi tìm kiếm

Sau khi nhận HTTP request, Elasticsearch xử lý yêu cầu trong cluster. Node nhận request đóng vai trò điều phối cho thao tác tìm kiếm.

### Xác định index và shard

Elasticsearch phân giải tên index hoặc alias trong URL, kiểm tra quyền truy cập và xác định shard cần tham gia.

Một index có thể gồm nhiều primary shard và replica shard. Node điều phối chọn shard copy phù hợp theo trạng thái cluster, routing và các tùy chọn request. Nếu request có `routing`, phạm vi shard có thể được thu hẹp; nếu không, một truy vấn thông thường có thể cần hỏi nhiều shard.

### Query phase

Ở query phase, các shard thực hiện phần tìm kiếm trên dữ liệu cục bộ:

1. Đọc cấu trúc index và áp dụng query DSL.
2. Xác định document phù hợp.
3. Tính score nếu truy vấn có xếp hạng relevance.
4. Áp dụng sort và giữ các ứng viên cần thiết cho trang kết quả.
5. Tính toán phần aggregation tương ứng nếu request yêu cầu.

Mỗi shard trả thông tin ứng viên về node điều phối. Node điều phối hợp nhất kết quả từ các shard, xử lý thứ tự toàn cục và xác định các hit thuộc trang cần trả.

### Fetch phase

Sau khi biết document nào cần trả, Elasticsearch thực hiện fetch phase để lấy nội dung và field cần thiết của các hit đó. Tùy request, phần dữ liệu này có thể bao gồm `_source`, stored fields, doc values, highlight hoặc metadata khác.

Node điều phối hợp nhất phần fetch thành response cuối cùng. Với request tìm kiếm phân tán, response vì vậy không đơn giản là kết quả từ một shard duy nhất.

### Vì sao lưu xong chưa chắc tìm thấy ngay?

Một thao tác index thành công có nghĩa Elasticsearch đã chấp nhận việc ghi document. Khả năng document xuất hiện trong search còn liên quan đến refresh: refresh làm các thay đổi đã ghi trở nên nhìn thấy được qua thao tác tìm kiếm.

Do đó, nếu ứng dụng gọi `save` rồi lập tức gọi `search` mà chưa thấy document, hãy kiểm tra refresh interval và refresh policy của thao tác ghi. Không nên mặc định rằng mọi lần ghi đều buộc cluster refresh ngay, vì refresh thường xuyên có thể ảnh hưởng hiệu năng.

## 5. Response quay lại Java

Elasticsearch trả response HTTP, thường có JSON chứa thông tin thực thi và danh sách hit. Một response rút gọn có thể trông như sau:

~~~json
{
  "took": 4,
  "timed_out": false,
  "_shards": {
    "total": 3,
    "successful": 3,
    "skipped": 0,
    "failed": 0
  },
  "hits": {
    "total": {
      "value": 42,
      "relation": "eq"
    },
    "max_score": 1.7,
    "hits": [
      {
        "_index": "products",
        "_id": "p-100",
        "_score": 1.7,
        "_source": {
          "name": "Laptop Pro",
          "category": "computer",
          "price": 1200.0
        }
      }
    ]
  }
}
~~~

Các trường thường cần chú ý:

- `took`: thời gian Elasticsearch báo cáo cho việc xử lý search, tính bằng millisecond.
- `_shards`: số shard tham gia và trạng thái thành công/thất bại.
- `hits.total.value`: số lượng hit phù hợp theo thông tin total hits.
- `hits.total.relation`: cho biết số lượng là chính xác (`eq`) hay chỉ là cận dưới (`gte`).
- `_id`: document ID trong Elasticsearch.
- `_score`: điểm relevance khi có xếp hạng.
- `_source`: dữ liệu document được trả về.

Java API Client giải mã response thành các kiểu Java của client. Lớp adapter của Spring Data tiếp tục chuyển response đó thành mô hình kết quả của Spring Data.

### Chuyển `_source` thành entity

Với kiểu đích là `Product`, Spring Data dùng converter và mapping metadata để tạo object Java:

- Đọc các field từ `_source`.
- Chuyển kiểu dữ liệu JSON sang kiểu thuộc tính Java.
- Áp dụng custom converter nếu dự án đã khai báo.
- Lấy document ID từ metadata của hit để gán cho thuộc tính được đánh dấu `@Id`.
- Giữ các metadata tìm kiếm như score, sort values, highlight và inner hits trong đối tượng hit tương ứng.

Việc chuyển đổi chỉ thành công nếu dữ liệu trả về tương thích với kiểu Java và mapping. Ví dụ, một field ngày tháng có format khác với converter mong đợi có thể gây lỗi chuyển đổi dù query đã được Elasticsearch thực thi thành công.

### `SearchHits` và `SearchHit`

Khi dùng `ElasticsearchOperations.search`, kết quả thường có kiểu `SearchHits<T>`. Đây là wrapper giữ cả danh sách kết quả lẫn metadata của toàn bộ lần tìm kiếm.

Mỗi phần tử `SearchHit<T>` có thể cung cấp:

- `getContent()`: entity đã chuyển đổi.
- `getId()`: document ID.
- `getScore()`: score của hit.
- `getSortValues()`: giá trị sort được Elasticsearch trả về.
- `getHighlightFields()`: nội dung highlight.
- Metadata khác như inner hits tùy loại query.

Ví dụ:

~~~java
SearchHits<Product> hits = operations.search(query, Product.class);

long totalHits = hits.getTotalHits();

for (SearchHit<Product> hit : hits.getSearchHits()) {
    Product product = hit.getContent();

    System.out.println("id = " + hit.getId());
    System.out.println("score = " + hit.getScore());
    System.out.println("name = " + product.getName());
}
~~~

Nếu repository trả về `List<Product>`, ứng dụng nhận danh sách entity và không trực tiếp giữ toàn bộ metadata của `SearchHits`. Khi cần total hits, score, highlight hoặc sort values, hãy chọn kiểu trả về giàu metadata phù hợp với API repository hoặc gọi `ElasticsearchOperations`.

### Kết quả quay về service và controller

Sau khi converter hoàn tất, kết quả được trả ngược qua các lớp đã gọi:

1. Client trả response cho lớp operations.
2. Operations chuyển response thành `SearchHits`, `SearchPage` hoặc kiểu kết quả tương ứng.
3. Repository trả kiểu dữ liệu đã khai báo trong phương thức.
4. Service nhận kết quả và áp dụng logic nghiệp vụ.
5. Controller có thể chuyển kết quả thành response API của ứng dụng.

Spring Data không tự quyết định cấu trúc JSON công khai của REST API ứng dụng. Controller và lớp trình bày vẫn chịu trách nhiệm chọn field nào được trả về cho client bên ngoài.

## 6. Gọi tìm kiếm trực tiếp qua `ElasticsearchOperations`

Repository phù hợp với truy vấn phổ biến và quy ước rõ ràng. Khi cần Query DSL phức tạp, có thể xây dựng `NativeQuery` rồi gọi operations trực tiếp.

Ví dụ sau tìm sản phẩm có tên khớp với từ `laptop`, lọc chính xác category là `computer`, và lấy 10 kết quả đầu:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q
        .bool(b -> b
            .must(m -> m
                .match(mm -> mm
                    .field("name")
                    .query("laptop")
                )
            )
            .filter(f -> f
                .term(t -> t
                    .field("category")
                    .value(FieldValue.of("computer"))
                )
            )
        )
    )
    .withPageable(PageRequest.of(0, 10))
    .build();

SearchHits<Product> hits = operations.search(query, Product.class);

for (SearchHit<Product> hit : hits.getSearchHits()) {
    Product product = hit.getContent();
    // Xử lý product và metadata của hit
}
~~~

`NativeQuery` cho phép mô tả query bằng API Java của Elasticsearch. `PageRequest` cung cấp thông tin trang cho Spring Data. `operations.search` nhận query cùng kiểu entity để xác định mapping và chuyển document trong response thành `Product`.

Tên field trong Query DSL phải phù hợp với mapping trên index. Nếu Java property được ánh xạ sang tên field khác, hãy kiểm tra mapping thực tế và request được gửi để bảo đảm DSL đang tham chiếu đúng field.

API cụ thể có thể khác giữa các phiên bản Java API Client và Spring Data Elasticsearch. Khi áp dụng ví dụ vào dự án, dùng dependency đang có trong dự án làm chuẩn và kiểm tra import của `NativeQuery`, `Query` cùng kiểu `FieldValue`.

## 7. So sánh các thao tác Java với HTTP API

Các phương thức repository khác nhau dẫn đến các Elasticsearch API khác nhau. Bảng dưới đây mô tả endpoint thường gặp để định hướng khi theo dõi request; request thực tế có thể thay đổi theo phiên bản, loại ID, alias và cấu hình.

| Lời gọi Java | Ý nghĩa | API HTTP thường gặp |
|---|---|---|
| `repository.findById(id)` | Đọc một document theo ID | `GET /products/_doc/{id}` |
| `repository.save(product)` | Index hoặc cập nhật document | `PUT /products/_doc/{id}` hoặc API index tương ứng |
| `repository.deleteById(id)` | Xóa document theo ID | `DELETE /products/_doc/{id}` |
| `repository.findByCategory(value)` | Tìm document theo điều kiện | `POST /products/_search` |
| `operations.search(query, Product.class)` | Tìm kiếm với query được xây dựng trong Java | `POST /products/_search` |

Không nên suy luận rằng mọi phương thức `find...` đều gọi Search API. `findById` thường đọc trực tiếp theo document ID; một finder method có điều kiện thường dùng Search API.

## 8. Cách lần theo request khi debug

Khi kết quả không đúng mong đợi, hãy lần theo từng ranh giới trong luồng thay vì chỉ nhìn vào dòng gọi repository.

### Kiểm tra từ tầng ứng dụng

Xác nhận:

- Service gọi đúng repository hoặc operations.
- Tham số truyền vào có giá trị đúng.
- Kiểu trả về có giữ metadata cần dùng không.
- `Pageable` và `Sort` có đúng trang, kích thước và thứ tự không.

Nếu phương thức là derived query, kiểm tra tên property có khớp với entity không. Nếu dùng `@Query` hoặc `NativeQuery`, kiểm tra JSON/DSL và giá trị tham số.

### Kiểm tra index và mapping

Có thể dùng Elasticsearch API hoặc công cụ quản trị cluster để xem mapping:

~~~http
GET /products/_mapping
~~~

Đối chiếu:

- Index hoặc alias có đúng không.
- Field cần tìm là `text`, `keyword`, numeric, date hay kiểu khác.
- Analyzer của field `text` có đúng với cách tìm kiếm mong muốn không.
- Tên field trong Query DSL có khớp mapping thực tế không.
- `_source` có được bật và có chứa field ứng dụng cần đọc không.

Lỗi phổ biến là dùng `term` trên field `text` trong khi mục tiêu là tìm chính xác toàn bộ giá trị, hoặc dùng `match` khi cần so khớp chính xác trên `keyword`.

### Kiểm tra HTTP request và response

Trong môi trường phát triển, có thể bật logging phù hợp ở client/transport hoặc dùng công cụ quan sát request của Elasticsearch. Tên logger và cách bật phụ thuộc phiên bản client. Tránh bật log body chứa dữ liệu nhạy cảm trong môi trường thật nếu chưa kiểm soát quyền truy cập và thời gian lưu log.

Lấy request thực tế rồi chạy lại trong Elasticsearch Dev Tools hoặc một HTTP client. Ví dụ, nếu request là `POST /products/_search`, chạy cùng body để phân biệt lỗi do query với lỗi ở bước chuyển đổi entity.

Có thể dùng thêm:

- `GET /_cat/indices?v` để kiểm tra index có tồn tại và trạng thái ra sao.
- `POST /products/_validate/query?explain=true` để kiểm tra query và xem cách Elasticsearch diễn giải.
- `_explain` cho một document cụ thể để hiểu vì sao document khớp hoặc không khớp.
- Profile API khi cần phân tích chi phí thực thi query; chỉ bật khi cần vì profiling có overhead.

### Phân loại lỗi theo tầng

| Dấu hiệu | Tầng cần kiểm tra trước |
|---|---|
| Không tạo được repository hoặc thiếu bean | Spring configuration, dependency, repository scanning |
| Không chuyển được query thành request | Query builder, API tương thích giữa các phiên bản |
| Connection refused hoặc timeout | Host, port, TLS, network, timeout và trạng thái cluster |
| HTTP 401 hoặc 403 | Authentication, role và quyền truy cập index |
| HTTP 404 hoặc index not found | Tên index, alias và quá trình tạo index |
| HTTP 400 hoặc query parse error | Query DSL, tên field, kiểu dữ liệu và mapping |
| Shard failure hoặc HTTP 5xx | Cluster health, shard, node và server log |
| Có hit nhưng lỗi khi tạo entity | `_source`, kiểu Java, date format và custom converter |
| Ghi thành công nhưng tìm kiếm chưa thấy | Refresh và khả năng document đã được refresh |

Một request có thể thành công ở tầng HTTP nhưng vẫn có shard failure hoặc lỗi chuyển đổi dữ liệu. Vì vậy, hãy đọc cả status, response body, thông tin `_shards` và exception gốc thay vì chỉ kiểm tra xem client có nhận được response hay không.

## 9. Những điểm cần nhớ khi thiết kế tìm kiếm

**Phân biệt `text` và `keyword`.** `text` thường được phân tích thành token để tìm kiếm nội dung; `keyword` lưu giá trị phù hợp cho so khớp chính xác, lọc, nhóm hoặc sắp xếp. Chọn kiểu field theo mục đích nghiệp vụ.

**Mapping Java và mapping trên cluster phải nhất quán.** Annotation mô tả cách Spring Data chuyển đổi entity và có thể được dùng khi tạo index. Mapping đã tồn tại trên cluster vẫn cần được kiểm tra riêng.

**Phân trang ảnh hưởng đến chi phí tìm kiếm.** `PageRequest` thường được chuyển thành `from` và `size`. Khi duyệt sâu qua nhiều trang, hãy đánh giá `search_after` và sort ổn định.

**Chọn kiểu kết quả theo nhu cầu.** `List<T>` thuận tiện khi chỉ cần entity. `SearchHits<T>` phù hợp khi cần score, total hits, highlight hoặc sort values. Dùng kiểu trả về có metadata giúp tránh phải thực hiện thêm request chỉ để lấy thông tin mà response ban đầu đã có.

**Refresh ảnh hưởng đến khả năng đọc ngay sau khi ghi.** Nếu luồng nghiệp vụ cần đọc lại ngay document vừa lưu, hãy thiết kế refresh policy có chủ đích và cân nhắc chi phí của nó.

**Theo dõi phiên bản client.** Spring Data Elasticsearch, Elasticsearch server và Elasticsearch Java API Client phải tương thích. Khi nâng cấp, kiểm tra dependency, cấu hình transport, kiểu request và API builder thay vì chỉ sửa import cho hết lỗi biên dịch.

## 10. Nhìn lại toàn bộ luồng

Với lời gọi `productRepository.findByCategory("computer")`, đường đi điển hình là:

1. Service gọi phương thức repository.
2. Repository proxy nhận lời gọi và cơ chế query của Spring Data phân tích `findByCategory`.
3. Spring Data tạo query từ property và tham số.
4. Repository ủy quyền thao tác cho `ElasticsearchOperations`.
5. Operations xác định index, kết hợp query và thông tin phân trang.
6. Request converter tạo request cho Elasticsearch Java API Client.
7. Client serialize request, transport gửi HTTP đến Elasticsearch.
8. Node điều phối phân giải index, chọn shard và thực hiện query/fetch.
9. Elasticsearch trả response chứa hit, `_source` và metadata.
10. Client giải mã response; Spring Data converter chuyển dữ liệu thành `Product`.
11. Operations và repository trả kết quả về service.
12. Service chuyển kết quả cho controller hoặc tiếp tục xử lý nghiệp vụ.

Khi hiểu ranh giới giữa repository, operations, converter, Java API Client, HTTP transport và Elasticsearch cluster, ta có thể xác định lỗi nằm ở bước tạo query, gửi request, thực thi trên shard hay chuyển response thành entity. Đó là cách lần theo một lời gọi Java đến tận request HTTP và quay lại kết quả tìm kiếm.

