# Khai báo truy vấn bằng `@Query` trên Repository

Spring Data Elasticsearch cho phép khai báo truy vấn ngay trên method của repository bằng annotation `@Query`. Thay vì để Spring suy luận query từ tên method, lập trình viên viết trực tiếp phần JSON Query DSL mà Elasticsearch sẽ thực thi. Cách này hữu ích khi query cần `bool`, `match`, `term`, `range`, `ids`, các điều kiện lồng nhau hoặc khi tên method dẫn xuất trở nên dài và khó đọc.

`@Query` giữ phần lớn code truy vấn ở gần repository interface, trong khi Spring Data vẫn đảm nhiệm việc bind tham số, chuyển đổi kết quả thành entity và hỗ trợ các kiểu trả về như `List`, `Page` hoặc `SearchHits`. Để sử dụng hiệu quả, cần hiểu JSON mà annotation nhận, quy tắc placeholder, SpEL, phân trang và giới hạn của query khai báo so với `NativeQuery` hoặc `ElasticsearchOperations`.

## 1. Khi nào nên dùng `@Query`?

Spring Data Elasticsearch có nhiều cách tạo query:

| Cách tạo query | Cách hoạt động | Phù hợp khi |
|---|---|---|
| Derived query | Spring phân tích tên method như `findByCategoryAndPriceGreaterThan` | Điều kiện đơn giản, tên method vẫn dễ đọc |
| `@Query` | Khai báo JSON Query DSL trên repository method | Cần kiểm soát cấu trúc query nhưng vẫn muốn dùng repository abstraction |
| `@SearchTemplateQuery` | Gọi search template đã lưu trong Elasticsearch | Query template được quản lý riêng trên cluster và tái sử dụng |
| `CriteriaQuery` | Xây query bằng các đối tượng `Criteria` | Muốn xây query bằng Java API theo kiểu fluent |
| `NativeQuery` | Dùng query builder của Elasticsearch Java API Client | Cần nhiều tính năng của Search API hoặc Query DSL nâng cao |

Không cần dùng `@Query` cho mọi method. Một method như `findByStatus(String status)` thường dễ đọc hơn khi để Spring Data tự tạo query. Nhưng nếu cần kết hợp `must`, `filter`, `should`, `minimum_should_match`, nested query hoặc một cấu trúc Query DSL cụ thể, `@Query` thường diễn đạt rõ ràng hơn.

## 2. Cấu trúc repository và entity mẫu

Ví dụ trong bài sử dụng entity `Product` được lưu trong index `products`:

```java
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
    private Long priceInCents;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    // Constructors, getters and setters
}
```

Mapping này có ý nghĩa:

- `name` là `text`, phù hợp với full-text query như `match`.
- `category` là `keyword`, phù hợp với so khớp chính xác bằng `term` hoặc `terms`.
- `priceInCents` là `long`, phù hợp với range query số học.
- `active` là `boolean`, phù hợp với điều kiện true/false.

Repository kế thừa `ElasticsearchRepository`:

```java
package com.example.catalog.repository;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import com.example.catalog.domain.Product;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

Annotation `@Query` được import từ `org.springframework.data.elasticsearch.annotations.Query` và đặt trực tiếp trên method của interface repository.

## 3. Query đầu tiên với `@Query`

Ví dụ tìm sản phẩm theo tên bằng `match`:

```java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("{\"match\": {\"name\": {\"query\": \"?0\"}}}")
    List<Product> searchByName(String text);
}
```

`?0` là placeholder cho tham số thứ nhất của method. Khi gọi:

```java
List<Product> products = productRepository.searchByName("mechanical keyboard");
```

Spring Data bind giá trị tham số vào query và tạo search request có phần query tương đương:

```json
{
  "query": {
    "match": {
      "name": {
        "query": "mechanical keyboard"
      }
    }
  }
}
```

Giá trị của `@Query` phải là JSON Query DSL hợp lệ. Spring Data sử dụng chuỗi này làm giá trị của phần `query` trong search request. Vì vậy, nội dung annotation thường bắt đầu bằng query clause như `match`, `bool`, `term` hoặc `range`; không bọc thêm một lớp ngoài `{"query": ...}`.

### 3.1. Dùng Java text block để dễ đọc JSON

Với Java 15 trở lên, text block giúp tránh phải escape mọi dấu ngoặc kép:

```java
@Query("""
    {
      "match": {
        "name": {
          "query": "?0"
        }
      }
    }
    """)
List<Product> searchByName(String text);
```

Nếu project dùng Java cũ hơn, dùng chuỗi Java thông thường và escape dấu ngoặc kép như ví dụ đầu tiên. Cả hai cách đều khai báo cùng một JSON query.

## 4. Placeholder `?0`, `?1`, `?2`

Các tham số của repository method có thể được đưa vào query bằng placeholder đánh số từ 0:

- `?0`: tham số bind đầu tiên.
- `?1`: tham số bind thứ hai.
- `?2`: tham số bind thứ ba.

Ví dụ tìm sản phẩm theo category và khoảng giá:

```java
@Query("""
    {
      "bool": {
        "filter": [
          { "term": { "category": "?0" } },
          { "range": { "priceInCents": {
            "gte": ?1,
            "lte": ?2
          } } }
        ]
      }
    }
    """)
List<Product> findInCategoryAndPriceRange(
        String category,
        Long minimumPrice,
        Long maximumPrice);
```

Gọi method:

```java
List<Product> products = repository.findInCategoryAndPriceRange(
        "keyboards", 500000L, 2000000L);
```

Chuỗi JSON sau khi bind có cấu trúc tương đương:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "category": "keyboards" } },
        { "range": { "priceInCents": {
          "gte": 500000,
          "lte": 2000000
        } } }
      ]
    }
  }
}
```

### 4.1. Quote placeholder theo kiểu dữ liệu JSON

Placeholder cần nằm đúng vị trí của kiểu JSON mà Elasticsearch mong đợi:

| Giá trị tham số | Cách đặt placeholder |
|---|---|
| Chuỗi đơn | `"?0"` |
| Số nguyên/số thực | `?0` |
| Boolean | `?0` |
| Collection/array JSON | `?0` không đặt trong dấu nháy |
| Object JSON | Đặt placeholder ở vị trí object nếu kiểu bind hỗ trợ cấu trúc đó |

Ví dụ numeric:

```java
@Query("{\"range\": {\"priceInCents\": {\"gte\": ?0}}}")
List<Product> findWithMinimumPrice(Long minimumPrice);
```

Ví dụ chuỗi:

```java
@Query("{\"term\": {\"category\": \"?0\"}}")
List<Product> findByExactCategory(String category);
```

Không đặt `"?0"` quanh một collection nếu query cần JSON array. Nếu quote sai, Elasticsearch có thể nhận chuỗi thay vì mảng và trả lỗi parse hoặc query không có semantics mong muốn.

### 4.2. Placeholder không phải nối chuỗi thủ công

Hãy để Spring Data bind tham số vào query. Tránh tự ghép giá trị người dùng vào JSON bằng `String.format`, toán tử `+` hoặc template chuỗi trước khi gọi client. Nối chuỗi thủ công dễ tạo JSON sai khi dữ liệu chứa dấu nháy, dấu gạch chéo hoặc ký tự đặc biệt.

Placeholder có chỉ số tính theo thứ tự tham số query, không phải vị trí byte hay tên biến. Khi thay đổi thứ tự tham số của method, hãy kiểm tra lại toàn bộ `?0`, `?1` và các placeholder tiếp theo.

## 5. Khai báo các loại Query DSL phổ biến

`@Query` không giới hạn ở `match`. Bất kỳ query clause hợp lệ nào của Elasticsearch mà repository query execution hỗ trợ đều có thể được khai báo dưới dạng JSON.

### 5.1. Full-text query với `match`

```java
@Query("""
    {
      "match": {
        "name": {
          "query": "?0",
          "operator": "and"
        }
      }
    }
    """)
List<Product> searchNameContainingAllTerms(String text);
```

`match` phân tích chuỗi tìm kiếm bằng search analyzer của field. Với `operator: and`, các term được phân tích phải cùng thỏa điều kiện; nếu bỏ `operator`, mặc định của `match` thường là `or`.

### 5.2. So khớp chính xác với `term`

```java
@Query("""
    {
      "term": {
        "category": "?0"
      }
    }
    """)
List<Product> findByCategoryExact(String category);
```

`term` so khớp giá trị term đã được lập chỉ mục. Nó thường phù hợp với `keyword`, ID, mã trạng thái hoặc giá trị phân loại. Không dùng `term` trên field `text` với kỳ vọng Elasticsearch sẽ phân tích chuỗi giống `match`.

### 5.3. Tập giá trị với `terms`

`terms` kiểm tra một field có khớp một trong các giá trị được cung cấp hay không:

```java
@Query("{\"terms\": {\"category\": ?0}}")
List<Product> findByAnyCategory(Collection<String> categories);
```

Khi gọi với `List.of("keyboards", "mice")`, query nhận một mảng JSON:

```json
{
  "query": {
    "terms": {
      "category": ["keyboards", "mice"]
    }
  }
}
```

Collection placeholder được đặt không có dấu nháy vì giá trị cần là JSON array.

### 5.4. Khoảng giá với `range`

```java
@Query("""
    {
      "range": {
        "priceInCents": {
          "gte": ?0,
          "lt": ?1
        }
      }
    }
    """)
List<Product> findByPriceRange(Long fromInclusive, Long toExclusive);
```

`gte` bao gồm cận dưới; `lt` loại trừ cận trên. Cặp `gte` và `lt` thường hữu ích khi truy vấn khoảng liên tiếp mà không bị chồng lấn ở điểm biên.

### 5.5. Kết hợp điều kiện bằng `bool`

Ví dụ tìm sản phẩm có tên phù hợp, category chính xác, giá tối thiểu và trạng thái active:

```java
@Query("""
    {
      "bool": {
        "must": [
          {
            "match": {
              "name": {
                "query": "?0"
              }
            }
          }
        ],
        "filter": [
          { "term": { "category": "?1" } },
          { "range": { "priceInCents": { "gte": ?2 } } },
          { "term": { "active": true } }
        ]
      }
    }
    """)
List<Product> searchActiveProducts(
        String text,
        String category,
        Long minimumPrice);
```

Trong `bool`:

- `must` yêu cầu clause phải khớp và thường đóng góp vào score.
- `filter` yêu cầu clause phải khớp nhưng không tính điểm relevance; phù hợp với điều kiện lọc chính xác.
- `should` biểu diễn điều kiện khuyến khích hoặc điều kiện OR, tùy `minimum_should_match` và cấu trúc bool.
- `must_not` loại document khớp clause khỏi kết quả.

### 5.6. Truy vấn ID với `ids`

```java
@Query("{\"ids\": {\"values\": ?0}}")
List<Product> findDocumentsByIds(Collection<String> ids);
```

Query `ids` nhận một mảng document ID. Cách này hữu ích khi đã có danh sách ID và muốn lấy các document tương ứng bằng một query thay vì gọi `findById` nhiều lần.

### 5.7. Kiểm tra field tồn tại với `exists`

```java
@Query("{\"exists\": {\"field\": \"category\"}}")
List<Product> findProductsWithCategory();
```

`exists` kiểm tra field có giá trị được lập chỉ mục hay không theo semantics của Elasticsearch. Nó không đơn giản tương đương với việc kiểm tra thuộc tính Java khác `null`, vì mapping, `null_value`, empty value và `_source` có thể ảnh hưởng kết quả.

## 6. Dùng SpEL trong `@Query`

Ngoài placeholder theo vị trí, Spring Data Elasticsearch hỗ trợ biểu thức SpEL trong query được khai báo bằng `@Query`. SpEL hữu ích khi cần tham chiếu tham số theo tên, lấy property từ object tham số, biến đổi collection hoặc đọc một bean của Spring.

### 6.1. Tham chiếu tham số theo tên

Ví dụ dùng `@Param` để đặt tên ổn định cho tham số:

```java
import org.springframework.data.repository.query.Param;

@Query("""
    {
      "term": {
        "category": "#{#category}"
      }
    }
    """)
List<Product> findByCategoryWithSpel(@Param("category") String value);
```

`#{#category}` tham chiếu tham số được đặt tên `category`. Dùng `@Param` giúp query không phụ thuộc việc compiler có lưu tên tham số Java hay không.

### 6.2. Truy cập property của object tham số

Có thể truyền một object chứa nhiều điều kiện:

```java
public record ProductSearchCriteria(String category, Long minimumPrice) {
}
```

Repository:

```java
@Query("""
    {
      "bool": {
        "filter": [
          { "term": { "category": "#{#criteria.category}" } },
          { "range": { "priceInCents": {
            "gte": #{#criteria.minimumPrice}
          } } }
        ]
      }
    }
    """)
List<Product> search(@Param("criteria") ProductSearchCriteria criteria);
```

SpEL truy cập property qua dấu chấm. Hãy bảo đảm property tồn tại và có kiểu dữ liệu tương thích với vị trí JSON được dùng.

### 6.3. Truyền collection qua SpEL

Khi dùng SpEL để chèn collection vào `terms`, không đặt collection trong dấu nháy:

```java
@Query("""
    {
      "terms": {
        "category": #{#categories}
      }
    }
    """)
List<Product> findByCategories(
        @Param("categories") Collection<String> categories);
```

Với `List.of("keyboards", "mice")`, biểu thức tạo mảng JSON:

```json
{
  "terms": {
    "category": ["keyboards", "mice"]
  }
}
```

Nếu collection chứa object thay vì chuỗi, SpEL collection projection có thể trích property cần dùng:

```java
public record CategoryFilter(String value) {
}
```

```java
@Query("""
    {
      "terms": {
        "category": #{#filters.![value]}
      }
    }
    """)
List<Product> findByCategoryFilters(
        @Param("filters") Collection<CategoryFilter> filters);
```

Biểu thức `![value]` tạo collection mới chứa property `value` từ từng phần tử.

### 6.4. Tham chiếu bean Spring

SpEL cũng có thể truy cập bean theo tên bằng ký hiệu `@`:

```java
@Query("""
    {
      "term": {
        "tenantId": "#{@tenantContext.currentTenantId()}"
      }
    }
    """)
List<Product> findForCurrentTenant();
```

Trong ví dụ, Spring gọi bean `tenantContext` để lấy tenant hiện tại. Cách này có thể hữu ích với giá trị ngữ cảnh dùng chung, nhưng làm query phụ thuộc vào bean bên ngoài repository. Với logic nghiệp vụ phức tạp, cân nhắc tạo custom repository/service để dependency và luồng xử lý rõ ràng hơn.

Biểu thức SpEL trong annotation là cấu hình do nhà phát triển khai báo. Không xây dựng expression từ nội dung tùy ý do người dùng gửi lên và không cho phép người dùng điều khiển expression cần được thực thi.

## 7. Phân trang và sắp xếp

Repository method có `@Query` có thể nhận `Pageable` để phân trang:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

@Query("""
    {
      "match": {
        "name": {
          "query": "?0"
        }
      }
    }
    """)
Page<Product> searchByName(String text, Pageable pageable);
```

Gọi method:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.ASC, "priceInCents"));

Page<Product> page = repository.searchByName("keyboard", pageable);
```

`PageRequest.of(0, 20, ...)` lấy trang đầu tiên với tối đa 20 kết quả và sắp xếp theo giá tăng dần. `Pageable` là tham số điều khiển phân trang/sắp xếp, không phải placeholder query thông thường cần đưa vào JSON.

### 7.1. `Page`, `List` và `SearchHits`

| Kiểu trả về | Nội dung |
|---|---|
| `List<Product>` | Danh sách entity tìm được |
| `Page<Product>` | Nội dung một trang cùng thông tin phân trang/tổng số phần tử |
| `SearchHits<Product>` | SearchHit metadata như score, ID, sort values và thông tin tổng hit |
| `List<SearchHit<Product>>` | Danh sách hit kèm metadata cho từng kết quả |
| `Stream<Product>` hoặc `Stream<SearchHit<Product>>` | Dòng kết quả để xử lý tuần tự; cần đóng stream khi hoàn tất |
| `SearchPage<Product>` | Trang các SearchHit, giữ metadata tìm kiếm |

Chọn `Page` khi giao diện cần số trang/tổng số kết quả. Chọn `SearchHits` khi cần score hoặc metadata của Elasticsearch. Chọn `List` khi chỉ cần các entity và số lượng kết quả được giới hạn hợp lý.

### 7.2. Sort trên field phù hợp

Elasticsearch không thể sort thông thường trên mọi field `text`. Với dữ liệu cần vừa full-text search vừa sort, thường khai báo multi-field `keyword`:

```java
@Field(type = FieldType.Text, fielddata = false)
private String name;
```

Mapping tương ứng có thể thêm subfield:

```json
{
  "name": {
    "type": "text",
    "fields": {
      "keyword": {
        "type": "keyword"
      }
    }
  }
}
```

Khi sort theo tên, dùng field keyword như `name.keyword` nếu mapping đã có field đó. Không bật `fielddata` trên `text` chỉ để sort nếu chưa đánh giá chi phí bộ nhớ.

## 8. Query lookup strategy

Spring Data repository infrastructure cần quyết định cách tạo query cho mỗi method. Các chiến lược phổ biến:

| Strategy | Cách hoạt động |
|---|---|
| `CREATE` | Tạo query từ tên method |
| `USE_DECLARED_QUERY` | Yêu cầu có query khai báo; không tìm thấy query thì lỗi khi khởi tạo repository |
| `CREATE_IF_NOT_FOUND` | Tìm query khai báo trước, nếu không có thì tạo từ tên method; đây là mặc định |

Với `@Query`, method có declared query. Theo chiến lược mặc định `CREATE_IF_NOT_FOUND`, Spring Data sử dụng query khai báo thay vì cố phân tích tên method thành derived query.

Có thể cấu hình strategy trên `@EnableElasticsearchRepositories` nếu ứng dụng có nhu cầu thống nhất cách lookup. Thông thường không cần đổi mặc định chỉ để dùng `@Query`.

## 9. `@Query` chỉ mô tả query clause, không phải toàn bộ Search API request

Điểm quan trọng là chuỗi trong `@Query` được Spring Data đặt vào phần `query` của search request. Ví dụ annotation:

```java
@Query("{\"match\": {\"name\": \"?0\"}}")
List<Product> findByName(String name);
```

được bao trong search request tương đương:

```json
{
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
```

Không khai báo annotation theo dạng:

```java
@Query("{\"query\": {\"match\": {\"name\": \"?0\"}}}")
```

vì khi đó một object có key `query` lại được đặt vào vị trí của query clause, dẫn tới cấu trúc lồng sai.

`@Query` phù hợp để khai báo phần query. Khi cần điều khiển nhiều phần khác của Search API như aggregations, highlight, collapse, suggest, runtime mappings, search after hoặc các tùy chọn nâng cao khác, hãy xem xét `NativeQuery` và `ElasticsearchOperations`. Phạm vi cụ thể phụ thuộc phiên bản Spring Data Elasticsearch và API client tương ứng.

## 10. Khi nào nên dùng `@SearchTemplateQuery`?

Nếu query được lưu thành search template trên Elasticsearch, repository method có thể tham chiếu template bằng `@SearchTemplateQuery`:

```java
import org.springframework.data.elasticsearch.annotations.SearchTemplateQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

@SearchTemplateQuery(id = "product-by-title")
SearchHits<Product> searchByTitle(String title);
```

Method parameters được gửi tới search template dưới dạng key/value theo tên tham số. Search template phải được tạo và quản lý trên Elasticsearch trước khi method được gọi.

Khác biệt chính:

- `@Query` lưu JSON query trong mã nguồn ứng dụng.
- `@SearchTemplateQuery` tham chiếu template được lưu trên cluster.

Search template hữu ích khi cùng một query cần được quản lý hoặc cập nhật độc lập với lần phát hành ứng dụng. Nếu query chỉ dùng trong một repository và ít thay đổi, `@Query` thường đơn giản hơn.

## 11. So sánh `@Query` với `CriteriaQuery` và `NativeQuery`

| Tiêu chí | `@Query` | `CriteriaQuery` | `NativeQuery` |
|---|---|---|---|
| Nơi định nghĩa | Annotation trên repository method | Java code | Java code dùng query builder của Elasticsearch client |
| Định dạng | JSON Query DSL | Criteria object | Native Elasticsearch query objects |
| Bind tham số | Placeholder và SpEL | Java variables | Java variables/builders |
| Phân trang/sort | Qua tham số repository như `Pageable` | Qua query object | Qua query builder |
| Query phức tạp | Tốt với cấu trúc DSL tĩnh và tham số | Tốt với điều kiện được ghép động | Tốt khi cần các tính năng Search API/DSL cụ thể |
| Aggregations/highlight và search options | Không phải mục tiêu chính của annotation | Phạm vi phụ thuộc abstraction | Phù hợp hơn khi cần kiểm soát request nâng cao |

Ví dụ, nếu số điều kiện thay đổi theo request, tạo query trong service bằng `CriteriaQuery` hoặc `NativeQuery` có thể dễ bảo trì hơn một annotation JSON rất dài với nhiều biểu thức SpEL.

## 12. Lỗi thường gặp khi khai báo `@Query`

### JSON không hợp lệ

Annotation chứa chuỗi JSON, vì vậy dấu ngoặc, dấu phẩy, dấu nháy và escape phải đúng. Lỗi JSON có thể khiến Elasticsearch trả lỗi parse khi query được thực thi.

Với Java string thông thường, dấu `"` cần escape thành `\"`. Nếu dùng Java text block, JSON dễ đọc hơn nhưng vẫn phải là JSON hợp lệ.

### Đặt thêm wrapper `query` bên trong annotation

`@Query` cung cấp query clause cho phần `query` của search request. Không bọc thêm một object `query` bên ngoài trừ khi cấu trúc đó thực sự là một query clause hợp lệ của Elasticsearch.

### Dùng sai placeholder index

Placeholder bắt đầu từ `?0`, không phải `?1`. Khi thêm hoặc đổi thứ tự tham số, hãy rà soát mọi placeholder.

### Quote sai kiểu dữ liệu

Chuỗi thường cần nằm trong dấu nháy JSON; số và collection cần ở vị trí JSON number/array tương ứng. Quote collection khiến Elasticsearch nhận string thay vì array.

### Dùng `term` cho field `text`

`term` không phân tích chuỗi như `match`. Nếu cần full-text search trên field `text`, dùng `match`; nếu cần exact match, dùng field `keyword` và `term`.

### Dùng tên thuộc tính Java thay vì tên field Elasticsearch

Nếu mapping đổi tên field bằng `@Field(name = "product_category")`, query DSL phải tham chiếu đúng field trong mapping thực tế. Kiểm tra `_mapping` khi query báo không khớp hoặc không trả kết quả.

### Trông đợi `@Query` hỗ trợ toàn bộ search options

`@Query` chủ yếu khai báo query clause. Với aggregation, highlight hoặc search option phức tạp, dùng `NativeQuery`/`ElasticsearchOperations`.

### Dùng query_string khi chỉ cần match

`query_string` có cú pháp riêng với toán tử, dấu ngoặc và ký tự đặc biệt. Nếu muốn tìm toàn văn thông thường, `match` thường an toàn và dễ hiểu hơn. Chỉ dùng `query_string` khi thực sự cần cú pháp query string.

### Không kiểm tra mapping và analyzer

Query hợp lệ vẫn có thể trả về rỗng nếu field sai kiểu hoặc analyzer không phù hợp. Kiểm tra mapping và dùng Analyze API khi cần xác định token của field/query.

## 13. Kiểm thử repository method có `@Query`

Nên kiểm thử query trên Elasticsearch thật hoặc Testcontainers khi cần xác minh semantics của Query DSL, mapping và analyzer. Ví dụ kiểm tra một method tìm theo category:

```java
@Test
void findsProductsByExactCategory() {
    repository.save(new Product(
            "p-100", "Mechanical Keyboard", "keyboards", 1299000L, true));
    repository.save(new Product(
            "p-200", "Wireless Mouse", "mice", 499000L, true));

    // Refresh or use a test refresh policy before asserting search results.
    List<Product> result = repository.findByExactCategory("keyboards");

    assertThat(result)
            .extracting(Product::getId)
            .containsExactly("p-100");
}
```

Đoạn test minh họa luồng kiểm tra; constructor và setup test cần khớp entity thực tế. Elasticsearch là hệ thống near-real-time, vì vậy phải tính tới refresh trước khi xác minh kết quả search ngay sau khi ghi.

Các trường hợp nên có trong integration test:

- String chứa dấu nháy hoặc ký tự đặc biệt để kiểm tra binding.
- Numeric placeholder để xác nhận JSON number không bị quote thành string.
- Collection rỗng và collection có nhiều phần tử.
- Giá trị biên của range query.
- `match` trên field text và `term` trên field keyword.
- Phân trang, sort và tổng số hit.
- Query không có kết quả và dữ liệu có field thiếu/null.
- Tên field đã đổi bằng mapping annotation.

Mock repository có thể kiểm tra service gọi đúng method, nhưng không xác minh Elasticsearch hiểu JSON query hoặc mapping như mong đợi.

## 14. Quy trình viết một repository method với `@Query`

Khi cần khai báo một truy vấn mới, có thể thực hiện theo trình tự:

1. Xác định field và kiểu mapping thực tế trong Elasticsearch.
2. Chọn Query DSL phù hợp: `match`, `term`, `terms`, `range`, `bool`, `ids`, `exists` hoặc query khác.
3. Thử query JSON trực tiếp trên Dev Tools/REST API với dữ liệu đại diện.
4. Đưa query clause vào `@Query`, không thêm wrapper `query` bên ngoài.
5. Thay giá trị cố định bằng placeholder `?0`, `?1` hoặc SpEL khi cần.
6. Đặt chuỗi, số, boolean và collection đúng kiểu JSON.
7. Chọn kiểu trả về như `List`, `Page`, `SearchHits` hoặc `SearchPage`.
8. Thêm `Pageable`/`Sort` nếu cần phân trang hoặc sắp xếp.
9. Viết integration test với dữ liệu đại diện và xác nhận refresh.
10. Nếu query cần cấu trúc động hoặc search options nâng cao, cân nhắc `CriteriaQuery`, `NativeQuery` hoặc custom repository.

## 15. Tổng kết

`@Query` cho phép khai báo trực tiếp Elasticsearch JSON Query DSL trên repository method. Spring Data bind tham số bằng placeholder theo vị trí như `?0`, `?1`, hỗ trợ collection và SpEL, sau đó thực thi query và ánh xạ kết quả về kiểu trả về của repository. Annotation phù hợp với query có cấu trúc rõ ràng, ổn định và vẫn muốn giữ trong repository interface.

Khi viết `@Query`, hãy nhớ chuỗi annotation là query clause được đặt vào phần `query` của search request; không bọc thêm `query` lần nữa. Đặt placeholder đúng kiểu JSON, dùng `match` cho full-text và `term` cho exact match trên field phù hợp. `Pageable` và kiểu trả về giúp bổ sung phân trang, sắp xếp và metadata. Khi cần query được tạo động hoặc toàn bộ tính năng Search API, chuyển sang `CriteriaQuery`, `NativeQuery` hoặc `ElasticsearchOperations` sẽ phù hợp hơn.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – Query methods and `@Query`](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/elasticsearch-repository-queries.html)
- [Spring Data Elasticsearch – Search operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Elasticsearch – Query DSL](https://www.elastic.co/docs/reference/query-languages/querydsl)
- [Elasticsearch – Match query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-match-query)
- [Elasticsearch – Term query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-term-query)
- [Elasticsearch – Bool query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-bool-query)
