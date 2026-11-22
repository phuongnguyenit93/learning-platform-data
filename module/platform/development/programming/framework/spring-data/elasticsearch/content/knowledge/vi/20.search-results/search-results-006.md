# Source filtering với danh sách trường được lấy hoặc loại bỏ

Khi tìm kiếm trong Elasticsearch, mỗi hit thường trả về cả metadata và nội dung document trong `_source`. Một document có thể chứa nhiều field, trong khi màn hình hoặc API chỉ cần một vài giá trị. Source filtering cho phép chỉ định field nào được đưa vào `_source` của response hoặc field nào cần loại khỏi response.

Ví dụ document sản phẩm có `sku`, `name`, `price`, `description`, `internalNotes` và `auditTrail`. Trang danh sách chỉ cần `sku`, `name`, `price`. Thay vì tải toàn bộ source rồi loại field trong Java, search request có thể yêu cầu Elasticsearch chỉ trả về ba field cần thiết.

Source filtering là một phần của Search API. Nó điều khiển phần `_source` được trả về cho từng hit; không thay đổi document đang lưu, không sửa mapping, không thay đổi điều kiện query và không thay thế cơ chế phân quyền dữ liệu.

## 1. `_source` trong search response

Elasticsearch lưu nội dung document trong `_source` dưới dạng JSON. Một search response thông thường có cấu trúc rút gọn như sau:

```json
{
  "hits": {
    "total": {
      "value": 1,
      "relation": "eq"
    },
    "hits": [
      {
        "_index": "products",
        "_id": "product-1001",
        "_score": 1.2,
        "_source": {
          "sku": "SKU-1001",
          "name": "Bàn phím cơ",
          "price": 185000,
          "description": "Wireless mechanical keyboard",
          "internalNotes": "Supplier discount",
          "auditTrail": ["created", "reviewed"]
        }
      }
    ]
  }
}
```

Trong đó:

- `_index` là index chứa document.
- `_id` là định danh document trong index.
- `_score` là relevance score nếu query có scoring.
- `_source` là nội dung JSON của document được trả về.

Nếu không cấu hình source filtering, Search API thường trả về toàn bộ `_source` (trừ trường hợp source bị tắt ở mapping hoặc request có cấu hình khác). Với document lớn, trả về tất cả field có thể làm response nặng và tăng lượng dữ liệu truyền qua mạng.

## 2. Hai cách chỉ định field: includes và excludes

Elasticsearch hỗ trợ hai danh sách chính:

- **includes**: các field hoặc pattern được phép lấy trong `_source` response.
- **excludes**: các field hoặc pattern cần loại khỏi `_source` response.

Có thể dùng một trong hai danh sách hoặc kết hợp cả hai.

### 2.1 Chỉ lấy một danh sách field

Request sau chỉ trả về `sku`, `name` và `price`:

```http
GET /products/_search
{
  "query": {
    "match_all": {}
  },
  "_source": ["sku", "name", "price"]
}
```

Dạng mảng ngắn này tương đương với cấu hình `includes`:

```json
"_source": {
  "includes": ["sku", "name", "price"]
}
```

Response `_source` của mỗi hit chỉ chứa các field được chọn:

```json
{
  "_index": "products",
  "_id": "product-1001",
  "_source": {
    "sku": "SKU-1001",
    "name": "Bàn phím cơ",
    "price": 185000
  }
}
```

Các field khác vẫn tồn tại trong document đã lưu. Chúng chỉ không được đưa vào phần `_source` của response này.

### 2.2 Loại một số field và giữ phần còn lại

Nếu chỉ muốn loại `internalNotes` và `auditTrail`, có thể dùng `excludes`:

```http
GET /products/_search
{
  "query": {
    "match_all": {}
  },
  "_source": {
    "excludes": ["internalNotes", "auditTrail"]
  }
}
```

Khi chỉ có `excludes`, Elasticsearch trả về các field còn lại trong source, trừ những field khớp danh sách loại bỏ.

Đây là cách phù hợp khi document có nhiều field và ứng dụng muốn giữ gần như toàn bộ source, chỉ bỏ một vài field lớn hoặc không cần cho response hiện tại.

### 2.3 Kết hợp includes và excludes

Có thể chỉ định cả hai danh sách:

```http
GET /products/_search
{
  "query": {
    "match_all": {}
  },
  "_source": {
    "includes": ["sku", "name", "price", "description"],
    "excludes": ["description"]
  }
}
```

Elasticsearch chọn các field theo `includes`, sau đó áp dụng `excludes` để loại những field không muốn trả về. Vì vậy, trong ví dụ này `description` bị loại dù nó xuất hiện trong danh sách includes.

Khi kết hợp hai danh sách, nên viết chúng rõ ràng và tránh pattern chồng lấn khó hiểu. Nếu chỉ cần một danh sách field chính xác, dùng `includes` đơn giản hơn.

### 2.4 Khi nào dùng includes, khi nào dùng excludes?

| Tình huống | Cách phù hợp |
|---|---|
| API chỉ cần 3 field trong document có hàng chục field | Dùng `includes` |
| Hầu hết field cần trả về, chỉ bỏ 1-2 field lớn | Dùng `excludes` |
| Cần chọn một nhóm field và loại thêm một số field trong nhóm đó | Kết hợp cả hai |
| Chỉ cần metadata, không cần JSON source | `_source: false` |

## 3. Đường dẫn field lồng nhau

Source filtering hỗ trợ đường dẫn field lồng nhau bằng dấu chấm.

Document:

```json
{
  "name": "Bàn phím cơ",
  "manufacturer": {
    "name": "Northwind",
    "country": "VN",
    "contact": {
      "email": "support@example.test",
      "phone": "0000000000"
    }
  }
}
```

Chỉ lấy tên sản phẩm và tên/quốc gia nhà sản xuất:

```http
GET /products/_search
{
  "query": {
    "match_all": {}
  },
  "_source": {
    "includes": [
      "name",
      "manufacturer.name",
      "manufacturer.country"
    ]
  }
}
```

Response vẫn giữ cấu trúc object lồng nhau nhưng chỉ chứa các field được chọn:

```json
{
  "name": "Bàn phím cơ",
  "manufacturer": {
    "name": "Northwind",
    "country": "VN"
  }
}
```

Nếu chỉ include `manufacturer`, toàn bộ object con có thể được trả về. Nếu chỉ include một đường dẫn con, các phần khác của object không được lấy trong source response.

### 3.1 Wildcard pattern

Includes và excludes có thể sử dụng wildcard để chọn nhóm field:

```http
GET /products/_search
{
  "query": {
    "match_all": {}
  },
  "_source": {
    "includes": ["sku", "name", "attributes.*"],
    "excludes": ["attributes.internal*"]
  }
}
```

Trong ví dụ:

- `attributes.*` chọn các field con của `attributes`.
- `attributes.internal*` loại các field con có tên bắt đầu bằng `internal`.

Wildcard hữu ích khi một object có nhiều field mở rộng hoặc cấu trúc metadata thay đổi. Tuy nhiên, pattern rộng có thể vô tình lấy thêm field mới được bổ sung trong tương lai. Với API public có response contract cố định, danh sách includes tường minh thường dễ kiểm soát hơn.

### 3.2 Mảng object

Giả sử document chứa:

```json
{
  "name": "Áo khoác",
  "variants": [
    {
      "sku": "JACKET-RED-M",
      "color": "red",
      "size": "M",
      "internalCost": 120000
    },
    {
      "sku": "JACKET-BLUE-L",
      "color": "blue",
      "size": "L",
      "internalCost": 125000
    }
  ]
}
```

Có thể chỉ lấy SKU, màu và size của từng phần tử:

```json
"_source": {
  "includes": [
    "name",
    "variants.sku",
    "variants.color",
    "variants.size"
  ]
}
```

Source filtering chỉ điều chỉnh cấu trúc JSON được trả về. Nó không lọc các phần tử mảng theo điều kiện query và không thay thế `nested query` hay `inner_hits`. Nếu query match một variant cụ thể nhưng source filter chọn `variants.*`, source response vẫn có thể chứa thông tin từ các variant khác theo cấu trúc document.

## 4. Tắt `_source` trong response

Nếu request chỉ cần metadata hit, aggregation hoặc dữ liệu lấy từ cơ chế khác, có thể không trả `_source`:

```http
GET /products/_search
{
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "_source": false
}
```

Response vẫn có thể chứa `_index`, `_id`, `_score`, `sort`, `highlight` hoặc các metadata khác tùy request, nhưng không có nội dung `_source`.

`_source: false` ở cấp request khác với việc tắt lưu `_source` trong mapping. Request-level setting chỉ yêu cầu không trả source cho lần search hiện tại. Nếu mapping index đã đặt `_source.enabled: false`, dữ liệu source không được lưu theo cách thông thường và request không thể bật lại nó.

### 4.1 Khi nào không nên tắt source?

Không tắt `_source` nếu ứng dụng cần ánh xạ kết quả thành entity đầy đủ, hiển thị nội dung document, dùng dữ liệu nguồn để xử lý tiếp hoặc cần các thao tác phụ thuộc `_source` ở những luồng khác.

Nếu tắt source nhưng không cấu hình `fields`, stored fields hoặc cơ chế trả dữ liệu khác, kết quả Java có thể không có nội dung để populate entity. Hãy xác định chính xác response cần gì trước khi tắt.

## 5. Source filtering không thay đổi query

Source filtering chỉ áp dụng khi lấy nội dung hit. Nó không ảnh hưởng tới việc Elasticsearch chọn document phù hợp.

Ví dụ query lọc sản phẩm đang hoạt động, giá dưới 500.000, nhưng chỉ trả `sku` và `name`:

```http
GET /products/_search
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } },
        { "range": { "price": { "lte": 500000 } } }
      ]
    }
  },
  "_source": {
    "includes": ["sku", "name"]
  }
}
```

Elasticsearch vẫn dùng `active` và `price` để lọc document dù hai field đó không được trả về trong `_source`. Điều kiện query và source projection là hai phần độc lập.

Tương tự, source filtering không thay đổi:

- Query scoring hoặc thứ tự relevance.
- Field dùng để sort.
- Field dùng trong aggregation.
- Mapping hoặc analyzer.
- Document đã lưu trong index.

Nếu query cần một field nhưng response không cần field đó, vẫn có thể dùng field trong query và loại nó khỏi `_source`.

## 6. Highlight độc lập với source filtering

Highlight là metadata riêng trong search hit, không phải field gốc của `_source`. Một field có thể được dùng để highlight ngay cả khi không được include trong source response, miễn là query và highlighter hỗ trợ field đó.

Ví dụ:

```http
GET /products/_search
{
  "query": {
    "match": {
      "description": "wireless keyboard"
    }
  },
  "_source": {
    "includes": ["sku", "name", "price"]
  },
  "highlight": {
    "fields": {
      "description": {}
    }
  }
}
```

Response có thể không chứa `description` trong `_source`, nhưng vẫn có `highlight.description` chứa fragment được đánh dấu. Điều này hữu ích khi giao diện chỉ cần snippet liên quan chứ không cần toàn bộ nội dung field.

Trong Spring Data, đọc highlight từ `SearchHit.getHighlightFields()`. Đừng tìm fragment trong entity nếu field source đã bị loại khỏi response.

## 7. Sử dụng source filtering trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp `FetchSourceFilter` để biểu diễn danh sách includes và excludes. Có thể gắn source filter vào `NativeQuery` khi xây dựng search request.

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

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Text)
    private String internalNotes;

    protected Product() {
    }

    // Constructors and accessors omitted for brevity.
}
```

### 7.1 Chỉ lấy các field cần thiết

```java
import org.springframework.data.elasticsearch.core.query.FetchSourceFilter;

FetchSourceFilter sourceFilter = new FetchSourceFilter(
    new String[] {"sku", "name", "price"},
    null
);
```

Tham số đầu tiên là `includes`; tham số thứ hai là `excludes`. Truyền `null` ở danh sách không sử dụng.

### 7.2 Loại các field không cần

```java
FetchSourceFilter sourceFilter = new FetchSourceFilter(
    null,
    new String[] {"internalNotes", "auditTrail"}
);
```

Khi chỉ truyền excludes, các field khác được giữ trong source response.

### 7.3 Kết hợp includes và excludes

```java
FetchSourceFilter sourceFilter = new FetchSourceFilter(
    new String[] {"sku", "name", "price", "description"},
    new String[] {"description"}
);
```

Danh sách excludes loại `description` khỏi nhóm field đã chọn.

### 7.4 Gắn filter vào NativeQuery

Ví dụ dưới đây sử dụng phong cách API của Spring Data Elasticsearch 5.x với Elasticsearch Java Client:

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.FetchSourceFilter;

FetchSourceFilter sourceFilter = new FetchSourceFilter(
    new String[] {"sku", "name", "price"},
    new String[] {"internalNotes"}
);

Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("wireless keyboard")
    ))
    .withSourceFilter(sourceFilter)
    .build();
```

Thực thi qua `ElasticsearchOperations`:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<Product> hits = operations.search(query, Product.class);
```

`FetchSourceFilter` được chuyển thành source filtering trong Search API. Tên method và builder có thể khác giữa các dòng Spring Data Elasticsearch; hãy đối chiếu Javadoc của dependency dự án nếu đang dùng phiên bản khác. Ý nghĩa của includes/excludes vẫn tương ứng với `_source` trong REST API.

### 7.5 Ví dụ service hoàn chỉnh

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.FetchSourceFilter;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Product> searchForListPage(String text) {
        FetchSourceFilter sourceFilter = new FetchSourceFilter(
            new String[] {"sku", "name", "price"},
            new String[] {"internalNotes", "auditTrail"}
        );

        Query query = NativeQuery.builder()
            .withQuery(q -> q.match(m -> m
                .field("name")
                .query(text)
            ))
            .withSourceFilter(sourceFilter)
            .build();

        return operations.search(query, Product.class);
    }
}
```

Search result ở đây chỉ có source cho `sku`, `name` và `price`. Những thuộc tính khác trong lớp `Product` có thể không được populate. Hãy coi kết quả là dữ liệu đọc rút gọn, không phải entity đầy đủ để ghi lại.

### 7.6 Tắt source qua FetchSourceFilter

`FetchSourceFilter` có constructor cho phép chỉ định có fetch source hay không trong các phiên bản hỗ trợ:

```java
FetchSourceFilter sourceFilter = new FetchSourceFilter(
    false,
    null,
    null
);
```

Đây là cách biểu diễn tương đương request `_source: false`. Chỉ dùng khi ứng dụng không cần `_source` để tạo entity đầy đủ. Nếu constructor hoặc API khác trong phiên bản dự án, dùng source-filter API tương ứng được cung cấp bởi phiên bản đó.

## 8. Entity được ánh xạ từ source bị lọc

Đây là điểm cần đặc biệt chú ý khi sử dụng source filtering với Spring Data. Nếu query trả về `Product` nhưng chỉ include `sku`, `name` và `price`, mapping converter chỉ nhận được những field đó từ `_source`.

Ví dụ entity đầy đủ có:

```java
private String sku;
private String name;
private Double price;
private String description;
private String internalNotes;
```

Sau source filtering, `description` và `internalNotes` có thể là `null` hoặc giá trị mặc định trong object kết quả. Điều này không chứng minh dữ liệu trong Elasticsearch đã bị xóa.

### 8.1 Không save lại entity partial

Không nên làm như sau:

```java
Product product = hits.getSearchHit(0).getContent();
product.setPrice(199000.0);
productRepository.save(product);
```

Entity đã được đọc với source filtering có thể thiếu nhiều field. Gọi `save` có thể ghi document mới chỉ từ những field được populate và làm mất các field không có trong object.

Nếu cần cập nhật một phần, dùng Elasticsearch Update API qua `ElasticsearchOperations.update(...)` với `UpdateQuery`. Nếu cần ghi toàn bộ document, hãy đọc đầy đủ source hoặc lấy dữ liệu chuẩn từ nguồn phù hợp trước khi save.

### 8.2 Dùng DTO/projection cho kết quả rút gọn

Một search result chỉ phục vụ danh sách sản phẩm nên có kiểu dữ liệu riêng:

```java
public record ProductListItem(
    String sku,
    String name,
    Double price
) {
}
```

Có thể ánh xạ kết quả từ entity partial sang DTO:

```java
List<ProductListItem> items = hits.getSearchHits().stream()
    .map(hit -> hit.getContent())
    .map(product -> new ProductListItem(
        product.getSku(),
        product.getName(),
        product.getPrice()
    ))
    .toList();
```

Với API cần projection sâu hoặc muốn tránh tạo entity có trạng thái thiếu field, có thể dùng DTO/projection hoặc đọc response native theo cách phù hợp với phiên bản. Điểm cốt lõi là thể hiện rõ đây là dữ liệu đọc một phần.

## 9. Source filtering và hiệu năng

Source filtering thường giúp giảm kích thước response và lượng dữ liệu phải truyền từ Elasticsearch về ứng dụng. Nó cũng giảm công việc deserialize/map những field không cần thiết ở phía client.

Tuy nhiên, cần hiểu đúng giới hạn:

- Elasticsearch vẫn phải tìm document theo query.
- Field được dùng trong query, filter, sort hoặc aggregation vẫn được xử lý theo mapping, dù không trả về trong `_source`.
- Source filtering không làm index nhỏ hơn và không xóa field khỏi document đã lưu.
- Tùy cách lưu `_source` và cấu hình index, Elasticsearch vẫn có thể cần đọc/giải nén source document rồi mới lọc field; vì vậy không nên mặc định rằng chỉ include một field sẽ giảm tương ứng toàn bộ I/O phía server.
- Lợi ích rõ ràng nhất thường là giảm payload mạng và công việc xử lý source ở client, đặc biệt với document lớn.

### 9.1 Chọn field theo use case

Không nhất thiết dùng cùng một source filter cho mọi endpoint. Ví dụ:

| Use case | Field cần trả về |
|---|---|
| Trang danh sách | `sku`, `name`, `price`, `thumbnail` |
| Trang chi tiết | Các field hiển thị đầy đủ của sản phẩm |
| Autocomplete | `name`, `sku` hoặc field gợi ý tối thiểu |
| Search snippet | `name`, `sku` và highlight fragment |
| Báo cáo | Các field phục vụ phép tính hoặc export |

Thiết kế source filter theo response contract giúp tránh gửi dữ liệu thừa và giảm phụ thuộc giữa API với cấu trúc document nội bộ.

### 9.2 Không chọn field quá rộng bằng wildcard nếu không cần

Pattern như `*` hoặc `metadata.*` tiện khi cấu trúc thay đổi, nhưng có thể vô tình đưa field mới vào response sau một lần bổ sung mapping. Với endpoint public, danh sách includes cụ thể dễ dự đoán hơn.

### 9.3 Source filtering không thay thế pagination

Giảm số field trong mỗi hit không làm số hit giảm. Nếu query trả về hàng chục nghìn document, response vẫn có thể lớn dù mỗi document chỉ chứa hai field. Hãy kết hợp source filtering với `size`, `Pageable`, `search_after` hoặc chiến lược pagination phù hợp.

## 10. Phân biệt source filtering với fields và stored fields

Elasticsearch có nhiều cơ chế trả field trong search response. Chúng phục vụ mục đích khác nhau.

| Cơ chế | Nội dung | Phù hợp khi |
|---|---|---|
| `_source` | JSON document đã lưu | Cần nội dung document theo cấu trúc gốc |
| `_source.includes/excludes` | Một phần JSON source | Cần projection đơn giản từ document |
| `fields` | Giá trị field theo mapping và field retrieval API | Cần giá trị đã được xử lý theo field type/runtime field |
| `stored_fields` | Field được cấu hình `store: true` | Có chủ đích lưu riêng field để lấy lại |
| `docvalue_fields` | Giá trị từ doc values | Cần lấy giá trị keyword, số hoặc date có doc values |

### 10.1 `_source` filtering

Ví dụ:

```json
"_source": {
  "includes": ["sku", "name"]
}
```

Trả một phần JSON source. Đây thường là lựa chọn đơn giản nhất khi ứng dụng muốn giảm field trong document response.

### 10.2 `fields`

Ví dụ:

```json
"fields": ["sku", "price", "createdAt"]
```

`fields` có semantics riêng và response thường biểu diễn giá trị dưới dạng mảng theo field. Nó có thể hỗ trợ runtime fields hoặc field format tùy mapping/API. Không nên thay `_source` includes bằng `fields` mà không điều chỉnh cách đọc response.

### 10.3 `stored_fields`

Field cần được khai báo `store: true` trong mapping để lấy qua stored fields. Ví dụ:

```json
"name": {
  "type": "text",
  "store": true
}
```

Stored fields là cơ chế lưu riêng giá trị field trong Lucene. Nó không tự động bật cho mọi field và có thể làm tăng dung lượng index. Không cần bật `store: true` chỉ để lọc `_source` response.

### 10.4 `docvalue_fields`

Doc values là cấu trúc cột phục vụ sort, aggregation và một số thao tác lấy field. Ví dụ lấy ngày đã format:

```json
"docvalue_fields": [
  {
    "field": "createdAt",
    "format": "strict_date_time"
  }
]
```

Không phải mọi kiểu field đều có doc values; `text` thường không có doc values mặc định. Hãy kiểm tra mapping và yêu cầu thực tế trước khi chọn cơ chế này.

## 11. Source filtering và bảo mật dữ liệu

Source filtering không phải cơ chế authorization. Nếu một user có quyền gọi Search API, họ có thể tự gửi request khác để include field mà ứng dụng trước đó đã exclude, trừ khi quyền ở tầng Elasticsearch ngăn việc đó.

Ví dụ API nội bộ có thể gửi:

```json
"_source": {
  "excludes": ["salary", "personalNotes"]
}
```

Điều này chỉ giới hạn response của request đó. Nó không ngăn người dùng sửa request thành:

```json
"_source": true
```

Nếu field nhạy cảm không được phép truy cập, cần áp dụng authorization ở tầng ứng dụng, field-level security/document-level security của Elasticsearch hoặc tách dữ liệu theo boundary bảo mật phù hợp.

Ở tầng API, hãy xây dựng source filter từ quyền của người dùng phía server. Không nhận danh sách includes tùy ý từ client rồi cho phép client tự chọn field nhạy cảm. Ngay cả khi API chỉ trả DTO đã giới hạn, cần bảo đảm query backend và quyền Elasticsearch không mở đường truy cập ngoài ý muốn.

## 12. Kiểm tra source filtering bằng REST API

Khi source response không đúng như mong đợi, hãy kiểm tra trực tiếp bằng Search API.

### 12.1 Chỉ include một số field

```http
GET /products/_search
{
  "size": 5,
  "query": {
    "match_all": {}
  },
  "_source": {
    "includes": ["sku", "name", "price"]
  }
}
```

### 12.2 Exclude field lớn

```http
GET /products/_search
{
  "size": 5,
  "query": {
    "match_all": {}
  },
  "_source": {
    "excludes": ["description", "auditTrail"]
  }
}
```

### 12.3 Kiểm tra field lồng nhau

```http
GET /products/_search
{
  "query": {
    "match_all": {}
  },
  "_source": {
    "includes": ["name", "manufacturer.name", "variants.sku"]
  }
}
```

Đọc `hits.hits[*]._source` để xác nhận field được trả về. Đừng kiểm tra chỉ trên `_source` của document GET nếu request source filtering được gửi qua `_search`; hai request có thể có cấu hình fetch khác nhau.

## 13. Những lỗi thường gặp

### 13.1 Nhầm source filtering với xóa field

Field không xuất hiện trong response không có nghĩa nó đã bị xóa khỏi document. Source filtering chỉ thay đổi projection của response.

### 13.2 Chỉ dùng excludes trong khi document có field mới

Khi chỉ exclude một vài field, mọi field khác vẫn có thể được trả về, kể cả field mới được thêm trong tương lai. Với API cần contract ổn định, cân nhắc includes tường minh.

### 13.3 Wildcard quá rộng

Pattern rộng có thể lấy dữ liệu ngoài dự kiến. Dùng đường dẫn cụ thể khi cần kiểm soát response.

### 13.4 Entity có field null sau search

Nếu source filter không lấy field, mapping converter không nhận được giá trị để populate. Đây là hành vi bình thường của projection partial, không nhất thiết là dữ liệu bị mất.

### 13.5 Save lại entity được đọc một phần

Entity thiếu field do source filtering có thể ghi đè document đầy đủ nếu được truyền vào `save`. Dùng DTO/projection cho đọc và Update API cho thay đổi một phần.

### 13.6 Dùng source filter như bảo mật

Người gọi có thể thay đổi request. Dùng authorization/field-level security cho dữ liệu nhạy cảm.

### 13.7 Nhầm `_source: false` với mapping `_source.enabled: false`

Một cái chỉ tắt source trong response của request; cái còn lại ảnh hưởng cách index lưu source và có hệ quả lâu dài đối với reindex/update/khả năng truy xuất dữ liệu.

### 13.8 Nghĩ source filtering làm query nhanh hơn trong mọi trường hợp

Nó giảm payload và client-side mapping, nhưng không giảm điều kiện query, số shard hoặc công việc scoring. Phải đo để xác định lợi ích thực tế.

## 14. Checklist thiết kế source filter

Trước khi áp dụng source filtering cho một endpoint, hãy xác định:

1. Response cần những field nào và field nào có thể bỏ.
2. Nên dùng includes tường minh hay excludes.
3. Có field lồng nhau hoặc mảng object cần chọn theo đường dẫn không.
4. Có wildcard nào có thể vô tình lấy field mới trong tương lai không.
5. Entity trả về có bị partial và cần DTO/projection riêng không.
6. Có luồng nào save lại entity partial không; nếu có, cần đổi sang Update API hoặc đọc đầy đủ.
7. Highlight hoặc metadata nào cần trả riêng ngoài `_source`.
8. Có yêu cầu bảo mật field không; nếu có, source filter có đủ không (nó không phải authorization).
9. Kích thước response trước/sau và tác động mạng/client đã được đo chưa.
10. Có pagination phù hợp để giới hạn số hit không.

## 15. Tổng kết

Source filtering cho phép kiểm soát những field được trả về trong `_source` của mỗi search hit. Dùng `includes` để chọn field cần lấy, `excludes` để loại field không cần và wildcard/dotted path để xử lý cấu trúc lồng nhau. Nếu không cần nội dung document, có thể đặt `_source: false` ở cấp request; điều này khác với việc tắt lưu `_source` trong mapping.

Trong Spring Data Elasticsearch, `FetchSourceFilter` biểu diễn danh sách includes/excludes và có thể gắn vào `NativeQuery` trước khi gọi `ElasticsearchOperations.search(...)`. Khi source bị lọc, entity ánh xạ có thể thiếu field; hãy coi nó là dữ liệu đọc một phần, dùng DTO/projection và tránh save lại entity đó như một document đầy đủ. Source filtering giúp giảm payload nhưng không thay đổi query/mapping, không xóa dữ liệu và không phải cơ chế bảo mật. Với field nhạy cảm, cần authorization hoặc field-level security ở tầng phù hợp.

## Tài liệu tham khảo

- [Elasticsearch — Retrieve selected fields](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-fields.html)
- [Elasticsearch — Search API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html)
- [Elasticsearch — `_source` field](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping-source-field.html)
- [Spring Data Elasticsearch Reference — Search Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
