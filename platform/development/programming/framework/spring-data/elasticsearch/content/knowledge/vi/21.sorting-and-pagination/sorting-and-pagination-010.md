# Kiểm soát thuộc tính sắp xếp và kích thước trang từ đầu vào

Trong ứng dụng Spring Data Elasticsearch, API tìm kiếm thường nhận các tham số như `page`, `size`, `sortBy` và `direction` từ request. Những giá trị này được chuyển thành `Pageable` và `Sort` để điều khiển số kết quả, vị trí trang và thứ tự document trả về.

Không nên chuyển thẳng mọi giá trị sort từ client thành tên field Elasticsearch. Ứng dụng cần kiểm tra page, giới hạn kích thước trang, chỉ cho phép sắp xếp trên những field đã xác định và xác thực chiều `ASC`/`DESC`. Cách làm này giúp API có hành vi ổn định, tránh query vào field không hỗ trợ sort và kiểm soát chi phí tìm kiếm.

Trong Spring Data Elasticsearch, `PageRequest` biểu diễn trang và kích thước trang; `Sort` biểu diễn một hoặc nhiều tiêu chí sắp xếp; `Pageable` kết hợp hai phần đó. Có thể truyền `Pageable` vào repository hoặc gắn nó vào `CriteriaQuery`/`NativeQuery` trước khi gọi `ElasticsearchOperations`.

## 1. Phân trang và sắp xếp trong Search API

Elasticsearch Search API sử dụng `from` và `size` để phân trang theo offset:

- `from`: số hit bỏ qua trước khi lấy kết quả.
- `size`: số hit tối đa cần trả về.
- `sort`: danh sách tiêu chí sắp xếp theo thứ tự ưu tiên.

Ví dụ REST:

```json
GET /products/_search
{
  "from": 20,
  "size": 10,
  "sort": [
    { "price": { "order": "asc" } },
    { "sku": { "order": "asc" } }
  ],
  "query": {
    "match_all": {}
  }
}
```

Request lấy 10 document bắt đầu từ offset 20, sắp xếp theo giá tăng dần; nếu nhiều document có cùng giá thì dùng SKU tăng dần làm tiêu chí tiếp theo.

Spring Data dùng `Pageable` để biểu diễn page/size và sort. Với `PageRequest`, số trang bắt đầu từ 0:

```java
Pageable pageable = PageRequest.of(
    2,
    10,
    Sort.by(Sort.Order.asc("price"), Sort.Order.asc("sku"))
);
```

Đối tượng này tương ứng trang thứ ba, tối đa 10 kết quả mỗi trang. Offset được tính từ `page * size`, tức là 20 trong ví dụ.

## 2. Đầu vào tìm kiếm từ API

Một request có thể khai báo các trường:

```java
public record ProductSearchRequest(
    Integer page,
    Integer size,
    String sortBy,
    String direction,
    String keyword
) {
}
```

Ví dụ client gửi:

```http
GET /products?keyword=keyboard&page=0&size=20&sortBy=price&direction=ASC
```

Ứng dụng cần quyết định:

- Giá trị mặc định khi client không truyền page hoặc size.
- Có chấp nhận page âm hoặc size bằng 0 không.
- Kích thước trang tối đa là bao nhiêu.
- Những field nào được phép sort.
- Chiều sort nào được phép.
- Sort mặc định và tiêu chí phụ để ổn định thứ tự.
- Có cho phép truy vấn offset sâu hay phải chuyển sang cursor pagination.

Đây là quy tắc của API và nghiệp vụ. Không nên để hành vi phụ thuộc ngẫu nhiên vào exception từ Elasticsearch hoặc vào mọi khả năng mà `Sort` có thể biểu diễn.

## 3. Xác thực page và size

Page number và page size đến từ bên ngoài nên cần được kiểm tra trước khi tạo `PageRequest`.

### 3.1 Quy ước mặc định

Một quy ước thường dùng:

| Tham số | Mặc định ví dụ | Giới hạn |
|---|---:|---|
| `page` | `0` | Không âm |
| `size` | `20` | Từ 1 đến 100 |
| `sortBy` | `createdAt` | Phải nằm trong allowlist |
| `direction` | `DESC` | Chỉ `ASC` hoặc `DESC` |

Giới hạn `100` chỉ là ví dụ chính sách API. Hãy chọn theo kích thước document, latency, tải cluster và nhu cầu giao diện. Không có một page size tối ưu cho mọi hệ thống.

### 3.2 Từ chối page/size không hợp lệ

Có thể trả lỗi validation nếu:

- `page` nhỏ hơn 0.
- `size` nhỏ hơn 1.
- `size` vượt quá giới hạn ứng dụng.
- `page * size` vượt quá cửa sổ phân trang cho phép.

Không nên tự động biến size cực lớn thành một request không giới hạn. Nếu muốn clamp size về max, hãy làm điều đó như một quy ước API rõ ràng và trả lại page metadata phản ánh kích thước thực tế. Từ chối đầu vào sai thường dễ phát hiện lỗi client hơn.

### 3.3 Kiểm tra offset bằng kiểu số đủ lớn

Offset là tích `page * size`. Hãy tính bằng `long` để tránh overflow khi nhân hai giá trị `int` lớn:

```java
long from = (long) page * size;
long endExclusive = from + size;
```

Sau đó so sánh với `max_result_window` mà hệ thống cho phép. Elasticsearch mặc định thường có `index.max_result_window` là 10.000, nhưng setting có thể được thay đổi theo index. Ứng dụng nên cấu hình giới hạn pagination phù hợp với index thay vì giả định mọi cluster đều giống nhau.

## 4. Không nhận tên field sort tùy ý từ client

Tên field sort có ảnh hưởng trực tiếp đến query Elasticsearch. Không nên làm như sau:

```java
Sort sort = Sort.by(request.sortBy());
```

Code trên cho phép client gửi bất kỳ tên field nào. Có thể phát sinh các vấn đề:

- Field không tồn tại hoặc không hỗ trợ sort, khiến query lỗi.
- Field có kiểu `text` không có doc values và không thể sort theo cách thông thường.
- Client có thể yêu cầu sort trên field rất lớn hoặc field không phù hợp với endpoint.
- Tên field nội bộ bị lộ qua lỗi hoặc hành vi API.
- API mất khả năng kiểm soát ổn định khi mapping thay đổi.

Đây không phải SQL injection theo nghĩa truyền thống, nhưng vẫn là đầu vào query cần được kiểm soát. Hãy ánh xạ một tập sort key công khai sang field Elasticsearch đã được cho phép.

### 4.1 Dùng allowlist sort key

Client gửi một key có ý nghĩa API như `price`, `newest` hoặc `name`. Server ánh xạ key đó sang property được hỗ trợ:

```java
private static final Map<String, String> SORT_FIELDS = Map.of(
    "price", "price",
    "newest", "createdAt",
    "name", "nameSort",
    "sku", "sku"
);
```

Ở đây `nameSort` là field keyword dành riêng cho sort. Nếu mapping dùng multi-field, có thể ánh xạ key `name` sang sub-field keyword tương ứng theo API của dự án. Điều quan trọng là client chỉ chọn một key trong allowlist; client không tự quyết định đường dẫn field Elasticsearch.

### 4.2 Mapping phải hỗ trợ sort

Ví dụ mapping:

```json
PUT /products
{
  "mappings": {
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      },
      "nameSort": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
```

Các kiểu `keyword`, số và date thường phù hợp cho sort. Field `text` được phân tích thành token và thường không có doc values; sort trực tiếp trên field text có thể bị từ chối hoặc cần cấu hình không phù hợp. Nếu cần vừa full-text search vừa sort theo chuỗi, hãy dùng multi-field keyword hoặc một field sort riêng.

Ví dụ multi-field ở mapping:

```json
"name": {
  "type": "text",
  "fields": {
    "raw": {
      "type": "keyword"
    }
  }
}
```

Field `name` dùng cho full-text search; `name.raw` dùng cho exact match, aggregation hoặc sort. Khi sử dụng `Sort` qua Spring Data, cần xác nhận cách phiên bản đang dùng ánh xạ tên property/sub-field; với sort native nâng cao, có thể khai báo trực tiếp trong `NativeQuery` bằng Elasticsearch Java Client.

## 5. Kiểm soát chiều sắp xếp

Client thường gửi `ASC` hoặc `DESC`. Chỉ chấp nhận hai giá trị này:

```java
Sort.Direction direction = Sort.Direction.fromString(inputDirection);
```

`fromString` có thể ném `IllegalArgumentException` nếu giá trị không hợp lệ. Hãy chuyển lỗi đó thành lỗi validation API có thông điệp rõ ràng.

Không nối chuỗi direction vào JSON Query DSL. Dùng enum `Sort.Direction` để chỉ biểu diễn hai hướng hợp lệ.

Ví dụ xử lý mặc định:

```java
private Sort.Direction parseDirection(String value) {
    if (value == null || value.isBlank()) {
        return Sort.Direction.DESC;
    }

    try {
        return Sort.Direction.fromString(value.trim());
    } catch (IllegalArgumentException exception) {
        throw new IllegalArgumentException(
            "direction must be ASC or DESC",
            exception
        );
    }
}
```

## 6. Sort nhiều tiêu chí và thứ tự ổn định

Một sort có thể gồm nhiều tiêu chí. Elasticsearch áp dụng tiêu chí theo thứ tự trong danh sách: tiêu chí đầu tiên quan trọng nhất; tiêu chí sau dùng để phân định khi giá trị trước bằng nhau.

```java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.asc("sku")
);
```

Ví dụ: sản phẩm mới nhất đứng trước; nếu cùng thời điểm thì SKU tăng dần.

### 6.1 Vì sao cần tie-breaker?

Nếu sort chỉ theo `price`, nhiều sản phẩm có thể có cùng giá. Khi các document có cùng giá, thứ tự tương đối giữa chúng có thể không ổn định giữa các lần tìm kiếm hoặc giữa các trang.

Thêm một field duy nhất và có thể sort làm tie-breaker giúp thứ tự xác định hơn:

```java
Sort sort = Sort.by(
    Sort.Order.asc("price"),
    Sort.Order.asc("sku")
);
```

Ví dụ dùng `sku` làm tie-breaker với giả định SKU duy nhất và được mapping là keyword. Nếu SKU không duy nhất, chọn một field sort duy nhất khác được lưu trong document, ví dụ `sortId`.

Không nên mặc định `_id` luôn là field sort tối ưu. Nếu cần sort ổn định theo định danh, có thể lưu một bản sao ID vào field keyword có doc values để sort. Hãy thiết kế field tie-breaker rõ ràng trong mapping.

### 6.2 Sort mặc định

Nếu người dùng không truyền sort, API nên có thứ tự mặc định rõ ràng. Ví dụ danh sách sản phẩm mới nhất:

```java
Sort defaultSort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.asc("sku")
);
```

Nếu endpoint là tìm kiếm toàn văn và muốn relevance cao nhất trước, có thể không đặt sort field để Elasticsearch dùng `_score` mặc định, hoặc cấu hình `_score` rõ ràng trong native query. Đừng dùng một sort field tùy tiện khiến relevance score không còn là tiêu chí chính.

## 7. Xây dựng Pageable đã được kiểm soát

Ví dụ dưới đây kết hợp:

- Page mặc định là 0.
- Size mặc định là 20, tối đa 100.
- Sort key được chọn từ allowlist.
- Direction chỉ nhận ASC/DESC.
- Sort có tie-breaker `sku` nếu field chính không phải SKU.
- Offset không vượt quá giới hạn pagination đã cấu hình.

```java
import java.util.Map;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

public class ProductPageableFactory {

    private static final int DEFAULT_PAGE = 0;
    private static final int DEFAULT_SIZE = 20;
    private static final int MAX_SIZE = 100;
    private static final long MAX_RESULT_WINDOW = 10_000L;

    private static final Map<String, String> SORT_FIELDS = Map.of(
        "price", "price",
        "newest", "createdAt",
        "name", "nameSort",
        "sku", "sku"
    );

    public Pageable create(ProductSearchRequest request) {
        int page = request.page() == null
            ? DEFAULT_PAGE
            : request.page();

        int size = request.size() == null
            ? DEFAULT_SIZE
            : request.size();

        if (page < 0) {
            throw new IllegalArgumentException("page must be zero or greater");
        }

        if (size < 1 || size > MAX_SIZE) {
            throw new IllegalArgumentException(
                "size must be between 1 and " + MAX_SIZE
            );
        }

        long from = (long) page * size;
        long endExclusive = from + size;
        if (endExclusive > MAX_RESULT_WINDOW) {
            throw new IllegalArgumentException(
                "requested page exceeds the supported result window"
            );
        }

        String sortKey = request.sortBy() == null || request.sortBy().isBlank()
            ? "newest"
            : request.sortBy().trim();

        String sortField = SORT_FIELDS.get(sortKey);
        if (sortField == null) {
            throw new IllegalArgumentException("unsupported sortBy: " + sortKey);
        }

        Sort.Direction direction = parseDirection(request.direction());

        Sort sort = Sort.by(new Sort.Order(direction, sortField));
        if (!"sku".equals(sortField)) {
            sort = sort.and(Sort.by(Sort.Order.asc("sku")));
        }

        return PageRequest.of(page, size, sort);
    }

    private Sort.Direction parseDirection(String value) {
        if (value == null || value.isBlank()) {
            return Sort.Direction.DESC;
        }

        try {
            return Sort.Direction.fromString(value.trim());
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException(
                "direction must be ASC or DESC",
                exception
            );
        }
    }
}
```

`MAX_RESULT_WINDOW` trong ví dụ là chính sách ứng dụng giả định khớp với giới hạn index đang dùng. Trong production, hãy đồng bộ giá trị này với cấu hình Elasticsearch thực tế. Không tăng `index.max_result_window` chỉ để cho phép client yêu cầu page rất sâu.

`sku` được dùng làm tie-breaker với giả định field này duy nhất và có kiểu keyword. Nếu hệ thống không bảo đảm điều đó, thay bằng một field sort ID duy nhất.

## 8. Dùng Pageable với ElasticsearchRepository

Repository Spring Data Elasticsearch có thể nhận `Pageable` trong các thao tác đọc:

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

Service:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository repository;
    private final ProductPageableFactory pageableFactory;

    public ProductService(
            ProductRepository repository,
            ProductPageableFactory pageableFactory) {
        this.repository = repository;
        this.pageableFactory = pageableFactory;
    }

    public Page<Product> findAll(ProductSearchRequest request) {
        Pageable pageable = pageableFactory.create(request);
        return repository.findAll(pageable);
    }
}
```

Repository sử dụng `Pageable` để tạo truy vấn phân trang/sort. `Page<Product>` chứa nội dung trang cùng metadata như page number, page size và tổng số phần tử theo kết quả mà repository cung cấp.

Nếu cần filter theo category hoặc status, có thể khai báo query method nhận `Pageable`:

```java
Page<Product> findByStatus(String status, Pageable pageable);
```

Hoặc dùng `ElasticsearchOperations` với `CriteriaQuery`/`NativeQuery` khi điều kiện tìm kiếm phức tạp hơn.

## 9. Dùng Pageable với CriteriaQuery

CriteriaQuery có thể kết hợp Criteria và Pageable:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

Criteria criteria = new Criteria("status").is("ACTIVE");
CriteriaQuery query = new CriteriaQuery(criteria);
query.setPageable(pageable);
```

Thực thi:

```java
SearchHits<Product> hits = operations.search(query, Product.class);
```

`Pageable` mang cả page, size và sort. Criteria quyết định điều kiện document cần match; Pageable quyết định lát kết quả và thứ tự.

## 10. Dùng Pageable với NativeQuery

Với Query DSL linh hoạt, gắn `Pageable` vào `NativeQuery`:

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .filter(f -> f.term(t -> t
            .field("status")
            .value("ACTIVE")
        ))
    ))
    .withPageable(pageable)
    .build();

SearchHits<Product> hits = operations.search(query, Product.class);
```

Trong ví dụ, filter chọn sản phẩm ACTIVE, còn `pageable` giới hạn trang và áp dụng sort đã được server kiểm soát. Nếu cần các option sort chuyên biệt như nested sort hoặc missing-value policy, có thể cần cấu hình sort trực tiếp bằng native Elasticsearch Java Client theo API phiên bản.

## 11. Tạo API nhận page/size/sort

Một controller có thể nhận query parameter:

```java
import org.springframework.data.domain.Page;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/products")
    public Page<Product> search(@ModelAttribute ProductSearchRequest request) {
        return service.findAll(request);
    }
}
```

Controller nhận dữ liệu đầu vào, còn service/factory kiểm tra các giới hạn và tạo Pageable. Có thể dùng `@Validated` cùng Bean Validation để kiểm tra page/size ở request DTO, nhưng allowlist sort field vẫn cần được áp dụng ở tầng server.

### 11.1 Dùng Pageable tự động từ Spring MVC

Spring Data Web hỗ trợ bind tham số `page`, `size`, `sort` vào `Pageable` khi cấu hình tương ứng được bật:

```java
@GetMapping("/products")
public Page<Product> search(
        @PageableDefault(size = 20, sort = "createdAt", direction = Sort.Direction.DESC)
        Pageable pageable) {
    return service.findAll(pageable);
}
```

`@PageableDefault` đặt giá trị mặc định, nhưng không tự thay thế mọi chính sách kiểm soát đầu vào. Ứng dụng vẫn cần giới hạn page size và kiểm tra sort property được phép. Có thể cấu hình `PageableHandlerMethodArgumentResolver` để đặt max page size; đồng thời vẫn áp dụng allowlist sort ở tầng service.

Nếu dùng resolver tự động, hãy kiểm tra cách nhiều tham số `sort` được parse và đảm bảo client không thể yêu cầu field nội bộ ngoài chính sách API.

## 12. Sắp xếp theo text, keyword, số và ngày

Không phải field nào cũng có thể sort theo cùng một cách.

| Mapping | Khả năng sort thường dùng | Lưu ý |
|---|---|---|
| `keyword` | Có | Sort theo giá trị chính xác, thường dùng doc values |
| `integer`, `long`, `double` | Có | Sort theo giá trị số |
| `date` | Có | Sort theo thời gian |
| `boolean` | Có | Sort theo giá trị boolean |
| `text` | Thường không trực tiếp | Dùng multi-field keyword hoặc field sort riêng |
| `nested` | Có điều kiện | Cần nested sort context và có thể cần filter |

Nếu field `name` là `text`, sort theo `name` có thể thất bại do field không có doc values. Cấu hình multi-field:

```json
"name": {
  "type": "text",
  "fields": {
    "sort": {
      "type": "keyword",
      "normalizer": "lowercase_normalizer"
    }
  }
}
```

Sau đó dùng sub-field sort tương ứng theo cách ánh xạ mà Spring Data/Java Client hỗ trợ. Normalizer có thể giúp sort không phân biệt chữ hoa/thường theo quy tắc đã cấu hình. Nếu cần sort theo ngôn ngữ hoặc collation phức tạp, hãy thiết kế analyzer/normalizer và kiểm thử kết quả thực tế.

### 12.1 Sort trên nested field

Nếu sản phẩm có danh sách variants và muốn sort theo giá của variant, cần chỉ định nested path. Sort đơn giản như `Sort.by("variants.price")` có thể không đủ vì Elasticsearch cần biết nested document nào tham gia sort và cách tổng hợp nhiều giá trị (min/max/avg).

Ví dụ Query DSL:

```json
GET /products/_search
{
  "sort": [
    {
      "variants.price": {
        "order": "asc",
        "mode": "min",
        "nested": {
          "path": "variants",
          "filter": {
            "term": {
              "variants.available": true
            }
          }
        }
      }
    }
  ],
  "query": {
    "match_all": {}
  }
}
```

Sort này lấy giá thấp nhất trong các variant còn hàng. Đây là sort nâng cao; cần dùng native sort builder hoặc query API hỗ trợ nested sort của phiên bản Spring Data Elasticsearch đang triển khai.

## 13. Phân trang sâu và `max_result_window`

Offset pagination tiện lợi cho trang đầu và một số trang tiếp theo. Nhưng Elasticsearch phải xử lý các kết quả trước offset để trả về trang yêu cầu. Khi page càng sâu, chi phí càng tăng.

Setting `index.max_result_window` mặc định thường là 10.000. Nếu request có `from + size` vượt giới hạn, Elasticsearch có thể từ chối request. Ví dụ `from = 9900`, `size = 100` vừa chạm giới hạn 10.000; `from = 10000`, `size = 20` vượt giới hạn.

Không nên giải quyết bằng cách tăng giới hạn lên một con số rất lớn mà không đánh giá heap, số shard và workload. Với giao diện thông thường, giới hạn số trang là lựa chọn hợp lý. Với export hoặc duyệt hàng trăm nghìn document, nên dùng cursor pagination.

### 13.1 `search_after`

`search_after` dùng sort values của hit cuối trang hiện tại để yêu cầu trang kế tiếp. Không cần bỏ qua toàn bộ document trước đó như offset pagination.

Ví dụ trang đầu:

```json
GET /products/_search
{
  "size": 100,
  "query": {
    "match_all": {}
  },
  "sort": [
    { "createdAt": "desc" },
    { "sku": "asc" }
  ]
}
```

Giả sử hit cuối có sort values:

```json
"sort": ["2025-03-12T10:30:00.000Z", "SKU-1001"]
```

Trang tiếp theo gửi:

```json
GET /products/_search
{
  "size": 100,
  "query": {
    "match_all": {}
  },
  "sort": [
    { "createdAt": "desc" },
    { "sku": "asc" }
  ],
  "search_after": ["2025-03-12T10:30:00.000Z", "SKU-1001"]
}
```

Thứ tự sort phải giữ nguyên giữa các request. Các sort values cần tạo thứ tự đủ xác định; thêm tie-breaker duy nhất để tránh hai document có cùng giá trị sort.

### 13.2 Point in time (PIT)

Nếu index tiếp tục nhận ghi trong lúc client đi qua nhiều trang, tập kết quả có thể thay đổi. Point in time (PIT) tạo một góc nhìn ổn định của index trong một khoảng thời gian. Kết hợp PIT với `search_after` phù hợp cho việc duyệt dữ liệu lớn nhất quán hơn.

Quy trình tổng quát:

1. Mở PIT cho index.
2. Search với PIT ID, sort ổn định và page size giới hạn.
3. Lưu sort values của hit cuối làm cursor.
4. Gửi request tiếp theo với cùng sort và `search_after`.
5. Gia hạn keep-alive khi cần và đóng PIT khi hoàn tất.

PIT giữ tài nguyên phía Elasticsearch. Đặt thời gian sống vừa đủ, đóng PIT sau khi hoàn tất và không giữ cursor vô hạn. API `Pageable`/`PageRequest` chủ yếu phục vụ offset pagination; `search_after`/PIT thường cần native query/client API theo phiên bản.

## 14. Page metadata và tổng số hit

Repository trả `Page<T>` thường cung cấp:

- `getContent()`: các phần tử trong trang.
- `getNumber()`: chỉ số trang hiện tại, bắt đầu từ 0.
- `getSize()`: kích thước trang.
- `getNumberOfElements()`: số phần tử thực tế trong trang.
- `getTotalElements()`: tổng số phần tử theo kết quả query.
- `getTotalPages()`: tổng số trang.
- `hasNext()` / `hasPrevious()`: trạng thái điều hướng.

Với `ElasticsearchOperations.search(...)`, `SearchHits<T>` chứa `getTotalHits()` và danh sách `SearchHit<T>`. Nếu API cần `Page`, có thể tạo response model chứa content, page, size, total và sort; hoặc dùng các helper `SearchHitSupport`/`SearchPage` mà phiên bản Spring Data hỗ trợ.

Tổng số hit chính xác có thể tốn tài nguyên. Với Elasticsearch Search API, `track_total_hits` có thể giới hạn việc đếm chính xác. Nếu API hiển thị tổng trang chính xác, hãy cân nhắc chi phí. Với infinite scroll, chỉ cần biết có kết quả tiếp theo thường là đủ.

## 15. Các lỗi thường gặp

### 15.1 Cho phép size không giới hạn

Một client có thể gửi `size=100000`. Điều này tạo response lớn và tăng tải cluster/client. Đặt max size ở API và cấu hình resolver nếu dùng Pageable binding tự động.

### 15.2 Nhận sort field tùy ý

Field không tồn tại hoặc không hỗ trợ sort có thể khiến Elasticsearch trả lỗi. Dùng allowlist key công khai và ánh xạ sang field đã kiểm tra.

### 15.3 Sort trực tiếp trên field text

Field `text` thường không có doc values. Dùng keyword multi-field hoặc field sort riêng. Kiểm tra mapping trước khi cho phép sort.

### 15.4 Chỉ sort theo một field có nhiều giá trị trùng

Khi nhiều document có cùng sort value, thứ tự tương đối không ổn định. Thêm tie-breaker duy nhất, có thể sort.

### 15.5 Page number quá sâu

Offset lớn làm tăng chi phí và có thể vượt `max_result_window`. Giới hạn offset hoặc chuyển sang `search_after`/PIT.

### 15.6 Không validate direction

Chỉ chấp nhận `ASC`/`DESC`; xử lý giá trị không hợp lệ thành lỗi request rõ ràng.

### 15.7 Dùng sort field không đồng nhất giữa API và mapping

API key `newest` có thể ánh xạ tới `createdAt`; không nhất thiết tên client phải trùng tên field. Duy trì một allowlist tập trung và kiểm tra khi mapping thay đổi.

### 15.8 Nhầm sort với relevance boost

Sort field có thể thay thế thứ tự relevance. Nếu muốn ưu tiên kết quả theo score, không vô tình sort theo một field khác; nếu muốn thứ tự tuyệt đối theo giá/ngày, dùng sort thay vì cố tăng boost.

## 16. Kiểm thử phân trang và sort

Với dữ liệu test có giá trị trùng, cần kiểm tra:

1. Page mặc định và size mặc định đúng.
2. Page âm bị từ chối.
3. Size bằng 0 hoặc vượt max bị từ chối.
4. Sort key không nằm trong allowlist bị từ chối.
5. Direction không phải ASC/DESC bị từ chối.
6. Sort theo keyword, số và ngày trả đúng thứ tự.
7. Sort nhiều field dùng đúng thứ tự ưu tiên.
8. Tie-breaker giúp kết quả ổn định khi field chính trùng.
9. Offset vượt result window bị chặn hoặc chuyển sang cursor flow.
10. Query không có sort vẫn có hành vi mặc định rõ ràng.

Nên có integration test với Elasticsearch tương thích để kiểm tra mapping thực tế và sort. Unit test cho factory có thể xác nhận allowlist, validation và `Pageable` được tạo đúng; integration test mới xác nhận field có thể sort và kết quả thực tế đúng thứ tự.

## 17. Nguyên tắc triển khai

- Dùng `PageRequest`/`Pageable` để biểu diễn page, size và sort.
- Chọn page mặc định và size mặc định có chủ đích.
- Giới hạn page size tối đa ở tầng API.
- Tính `from` bằng `long` và kiểm tra giới hạn result window.
- Chỉ cho phép sort key nằm trong allowlist server-side.
- Chỉ chấp nhận direction `ASC` hoặc `DESC`.
- Chọn field có mapping hỗ trợ sort; dùng keyword cho chuỗi cần sort.
- Thêm tie-breaker duy nhất để ổn định thứ tự.
- Dùng sort mặc định rõ ràng hoặc giữ relevance khi endpoint là full-text search.
- Dùng Pageable với repository, CriteriaQuery hoặc NativeQuery tùy kiểu query.
- Dùng `search_after` và PIT khi cần duyệt sâu/lớn.
- Không coi source filtering, boost hoặc sort là thay thế cho nhau; mỗi cơ chế có mục đích riêng.

## 18. Tổng kết

Để kiểm soát thuộc tính sắp xếp và kích thước trang từ đầu vào, hãy biến các query parameter thành `Pageable` sau khi đã xác thực. Page nên bắt đầu từ 0, size cần có mặc định và giới hạn tối đa, còn offset phải nằm trong result window được hỗ trợ. Không truyền trực tiếp tên sort field do client cung cấp; dùng allowlist để ánh xạ các key API sang field đã được mapping và kiểm tra. Direction chỉ nhận ASC hoặc DESC.

`Sort` hỗ trợ nhiều tiêu chí và nên có tie-breaker duy nhất để thứ tự ổn định. Field sort phải phù hợp mapping: keyword, số và date thường hỗ trợ tốt; text thường cần keyword sub-field hoặc field sort riêng; nested sort cần cấu hình nâng cao. Có thể truyền `Pageable` vào ElasticsearchRepository hoặc gắn vào `CriteriaQuery`/`NativeQuery` khi dùng `ElasticsearchOperations`.

Offset pagination phù hợp với những trang đầu nhưng trở nên tốn kém khi đi sâu và bị giới hạn bởi `index.max_result_window`. Với dữ liệu lớn, hãy chuyển sang `search_after` kết hợp PIT và sort ổn định. Kiểm soát đầu vào theo các quy tắc này giúp search API dễ dự đoán, an toàn về vận hành và phù hợp với mapping Elasticsearch.

## Tài liệu tham khảo

- [Spring Data Elasticsearch Reference — Search Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Commons — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html)
- [Elasticsearch — Paginate search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html)
- [Elasticsearch — Sort search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/sort-search-results.html)
- [Elasticsearch — Search API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html)
