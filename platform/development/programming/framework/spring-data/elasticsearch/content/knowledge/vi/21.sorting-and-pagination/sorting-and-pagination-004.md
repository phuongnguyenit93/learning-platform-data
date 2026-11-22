# Xử lý trường thiếu, giá trị nhiều phần tử và nested sort

Sắp xếp kết quả tìm kiếm trong Elasticsearch phức tạp hơn việc chọn một field rồi đặt thứ tự tăng dần hoặc giảm dần. Một document có thể không có giá trị cho field được sort; một field có thể chứa nhiều giá trị; hoặc giá trị cần sắp xếp nằm trong một mảng object được mapping kiểu nested.

Spring Data Elasticsearch cung cấp các abstraction như Sort, Pageable và NativeQuery để xây dựng sort. Với trường hợp đơn giản, Sort.by(...) thường đủ. Khi cần quy định cách xử lý giá trị thiếu, chọn một giá trị đại diện từ field nhiều phần tử hoặc lọc nested object trước khi sort, ứng dụng cần cấu hình các tùy chọn sort của Elasticsearch Query DSL.

Bài này giải thích ba tình huống:

- **Missing values:** document không có giá trị có thể dùng để sort.
- **Multi-valued fields:** một field có nhiều giá trị và cần chọn giá trị nào đại diện cho document.
- **Nested sort:** sắp xếp document cha dựa trên field của các nested object con.

## 1. Sort hoạt động trên field đã được lập chỉ mục

Elasticsearch sắp xếp dựa trên giá trị đã được index và khả năng sort của mapping. Sort không đơn giản là lấy chuỗi trong _source rồi so sánh như Java.

Ví dụ:

~~~json
{
  "sku": "KB-1042",
  "name": "Mechanical Keyboard",
  "price": 129.5,
  "createdAt": "2026-03-12T08:30:00Z"
}
~~~

Query DSL sort theo giá tăng dần:

~~~json
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
    }
  ]
}
~~~

Với Spring Data Elasticsearch, sort cơ bản có thể viết:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

NativeQuery query = NativeQuery.builder()
    .withQuery(textQuery)
    .withSort(Sort.by(Sort.Order.asc("price")))
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Sort.Order.asc("price") biểu diễn thứ tự tăng dần và PageRequest giới hạn số kết quả mỗi trang. Với sort field đơn giản, Spring Data chuyển abstraction này thành sort request của Elasticsearch.

### 1.1. Field nào có thể sort?

| Kiểu field | Khả năng sort và lưu ý |
| --- | --- |
| keyword | Sort theo thứ tự từ vựng; thường dùng cho mã, trạng thái, tên chuẩn hóa |
| numeric | Sort theo giá trị số |
| date/date_nanos | Sort theo thời điểm |
| boolean | Sort theo giá trị boolean |
| ip | Có thể sort theo thứ tự địa chỉ IP |
| geo_point | Dùng geo distance sort thay vì sort giá trị thông thường |
| text | Mặc định không phù hợp để sort; thường sort trên multi-field keyword |
| object | Không sort trực tiếp theo toàn bộ object; chỉ định field con phù hợp |
| nested | Cần nested sort khi sort theo field của nested object |

Ví dụ field text có multi-field:

~~~json
{
  "properties": {
    "name": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword"
        }
      }
    }
  }
}
~~~

Sort theo name.keyword để so sánh giá trị keyword. Không nên bật fielddata trên text chỉ để sort nếu chưa đánh giá chi phí bộ nhớ; multi-field keyword thường là lựa chọn phù hợp hơn.

## 2. Xử lý document thiếu giá trị sort

Một document có thể không chứa field đang dùng để sort. Ví dụ:

~~~json
[
  {
    "sku": "A-100",
    "price": 100
  },
  {
    "sku": "A-200",
    "price": 150
  },
  {
    "sku": "A-300"
  },
  {
    "sku": "A-400",
    "price": null
  }
]
~~~

Khi sort theo price, document không có giá trị indexable cho field này cần được đặt ở một vị trí nhất định. Elasticsearch cho phép cấu hình thuộc tính missing trong sort.

### 2.1. Đặt giá trị thiếu ở cuối

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

missing: "_last" đặt các hit không có giá trị sort ở cuối kết quả. Đây thường là lựa chọn phù hợp khi sắp xếp giá tăng dần và muốn các sản phẩm chưa có giá nằm sau sản phẩm có giá.

### 2.2. Đặt giá trị thiếu ở đầu

~~~json
{
  "sort": [
    {
      "price": {
        "order": "desc",
        "missing": "_first"
      }
    }
  ]
}
~~~

missing: "_first" đặt các hit thiếu giá trị ở đầu. Có thể dùng khi giao diện muốn ưu tiên các document cần bổ sung dữ liệu.

### 2.3. Dùng một giá trị thay thế

Thay vì đặt ở đầu hoặc cuối, có thể coi giá trị thiếu như một giá trị cụ thể:

~~~json
{
  "sort": [
    {
      "price": {
        "order": "asc",
        "missing": 0
      }
    }
  ]
}
~~~

Với sort kiểu keyword, giá trị thay thế cần tương thích kiểu field:

~~~json
{
  "sort": [
    {
      "status": {
        "order": "asc",
        "missing": "unknown"
      }
    }
  ]
}
~~~

Giá trị thay thế ảnh hưởng trực tiếp vị trí của document trong kết quả. Chỉ dùng giá trị có ý nghĩa nghiệp vụ và tương thích mapping; không chọn một sentinel tùy tiện khiến dữ liệu thật bị xếp sai.

### 2.4. Missing mặc định

Nếu không khai báo missing, Elasticsearch mặc định đặt các document thiếu giá trị ở cuối danh sách sort. Tuy nhiên, nên khai báo rõ khi thứ tự của document thiếu dữ liệu có ý nghĩa đối với giao diện hoặc hợp đồng API.

Quy tắc này áp dụng cho sort của field không có giá trị indexable. Với một số kiểu field hoặc request đặc thù, hãy kiểm tra tài liệu đúng phiên bản Elasticsearch.

## 3. Null, field không tồn tại và null_value

Trong Elasticsearch, các trường hợp sau không nhất thiết được phân biệt khi sort:

- Field không xuất hiện trong JSON.
- Field có giá trị JSON là null.
- Field là mảng rỗng.
- Field có mảng nhưng không có phần tử nào có thể index.

Thông thường, giá trị null không tạo giá trị indexable. Khi sort, các trường hợp này được xử lý như missing value.

### 3.1. Dùng null_value trong mapping

Mapping có thể quy định một giá trị thay thế khi nhận null:

~~~json
{
  "properties": {
    "priority": {
      "type": "integer",
      "null_value": -1
    }
  }
}
~~~

Khi một document gửi "priority": null, Elasticsearch index giá trị thay thế -1 cho mục đích tìm kiếm và sort. null_value không tự thêm field vào nội dung _source; nó ảnh hưởng cách giá trị null được index.

Nếu document không gửi field priority, không có giá trị null để thay thế và field vẫn là missing. Vì vậy, null_value không đồng nghĩa với missing trong sort.

### 3.2. Phân biệt null_value và missing

| Cơ chế | Thời điểm tác động | Ý nghĩa |
| --- | --- | --- |
| mapping null_value | Khi index document có giá trị null | Index một giá trị thay thế cho null |
| sort missing | Khi thực hiện sort | Quy định cách xếp hit không có giá trị sort |

Nếu muốn mọi document chưa có priority được coi như priority 0 trong truy vấn và sort, có thể cần kết hợp quy tắc ghi dữ liệu hoặc mapping phù hợp. Đừng giả định null_value tự xử lý cả trường hợp field bị bỏ qua.

## 4. Missing trong tìm kiếm nhiều index

Khi tìm kiếm qua nhiều index, một số index có thể không có field đang dùng để sort. Trường hợp này khác với document thiếu field trong index đã có mapping.

Ví dụ:

- catalog-products-v1 có field price.
- catalog-products-v2 có field price và discountPrice.
- Một index lịch sử chưa khai báo discountPrice.

Có thể dùng unmapped_type trong sort để chỉ rõ kiểu của field khi một index không có mapping tương ứng:

~~~json
{
  "sort": [
    {
      "discountPrice": {
        "order": "asc",
        "unmapped_type": "double",
        "missing": "_last"
      }
    }
  ]
}
~~~

unmapped_type xử lý trường hợp field không được mapping trong một index thuộc tập tìm kiếm. missing xử lý document không có giá trị cho field đã được mapping. Hai thuộc tính giải quyết hai tình huống khác nhau.

Nếu các index khai báo cùng một field nhưng dùng kiểu không tương thích, cần chuẩn hóa mapping hoặc dùng giải pháp phù hợp cho từng index. unmapped_type không sửa được xung đột kiểu mapping đã tồn tại.

## 5. Field có nhiều giá trị

Elasticsearch cho phép một field chứa nhiều giá trị cùng kiểu mà không cần khai báo kiểu array riêng.

Ví dụ:

~~~json
{
  "sku": "KB-1042",
  "priceHistory": [120, 100, 95]
}
~~~

Nếu sort theo priceHistory, Elasticsearch cần chọn một giá trị đại diện để so sánh document với các document khác. Thuộc tính mode quyết định cách chọn hoặc tổng hợp giá trị.

### 5.1. Các sort mode

| Mode | Cách chọn giá trị | Phù hợp với |
| --- | --- | --- |
| min | Giá trị nhỏ nhất trong các phần tử | Giá thấp nhất, ngày sớm nhất |
| max | Giá trị lớn nhất trong các phần tử | Giá cao nhất, ngày muộn nhất |
| sum | Tổng các giá trị | Tổng số lượng hoặc tổng điểm |
| avg | Trung bình các giá trị | Điểm trung bình hoặc giá trung bình |
| median | Trung vị các giá trị | Giá trị giữa, ít bị ảnh hưởng bởi ngoại lệ |

min và max có thể dùng với nhiều kiểu sort. sum, avg và median phù hợp với kiểu số; không dùng chúng như cách tổng hợp chuỗi keyword.

### 5.2. Sort theo giá thấp nhất

~~~json
{
  "sort": [
    {
      "priceHistory": {
        "order": "asc",
        "mode": "min"
      }
    }
  ]
}
~~~

Document có mảng [120, 100, 95] được so sánh theo giá trị 95.

### 5.3. Sort theo giá cao nhất

~~~json
{
  "sort": [
    {
      "priceHistory": {
        "order": "desc",
        "mode": "max"
      }
    }
  ]
}
~~~

Document trên được so sánh theo giá trị 120.

### 5.4. Sort theo trung bình và trung vị

~~~json
{
  "sort": [
    {
      "ratingHistory": {
        "order": "desc",
        "mode": "avg"
      }
    },
    {
      "responseTimes": {
        "order": "asc",
        "mode": "median"
      }
    }
  ]
}
~~~

Nếu ratingHistory là [3, 5, 4], giá trị dùng để sort theo avg là 4. Median hữu ích khi dữ liệu có ngoại lệ lớn và muốn dùng trung vị làm đại diện. Hãy kiểm tra chi phí và tính phù hợp với quy mô mảng của document.

### 5.5. Mode mặc định

Nếu không khai báo mode:

- Sort tăng dần thường dùng min.
- Sort giảm dần thường dùng max.

Quy tắc này giúp chọn giá trị gần đầu danh sách theo hướng sort. Tuy nhiên, nên khai báo mode rõ ràng nếu kết quả có ý nghĩa nghiệp vụ, đặc biệt khi cùng một query có thể thay đổi chiều sort.

## 6. Multi-valued string và keyword

Một field keyword có thể chứa nhiều giá trị:

~~~json
{
  "name": "Keyboard",
  "aliases": ["keyboard", "mechanical keyboard", "key board"]
}
~~~

Sort trên field keyword nhiều giá trị thường dùng min hoặc max theo thứ tự từ vựng. Đây là thứ tự của giá trị đã index, không phải thứ tự theo độ liên quan hoặc độ dài chuỗi.

~~~json
{
  "sort": [
    {
      "aliases": {
        "order": "asc",
        "mode": "min"
      }
    }
  ]
}
~~~

Nếu mục tiêu là sắp xếp theo một tên hiển thị chính, nên lưu field riêng như displayName.keyword thay vì kỳ vọng Elasticsearch tự chọn alias phù hợp với người dùng.

## 7. Nested sort là gì?

Giả sử document sản phẩm chứa danh sách offer:

~~~json
{
  "sku": "KB-1042",
  "offers": [
    {
      "seller": "seller-a",
      "price": 120,
      "available": true
    },
    {
      "seller": "seller-b",
      "price": 95,
      "available": true
    },
    {
      "seller": "seller-c",
      "price": 80,
      "available": false
    }
  ]
}
~~~

Nếu offers được mapping là nested, sort theo offers.price cần biết nested document nào được xét và cách kết hợp giá trị của chúng thành một sort value cho document cha.

Nested sort có ba phần quan trọng:

1. path xác định nested field.
2. filter giới hạn nested document được dùng để tính sort value.
3. mode chọn giá trị hoặc phép tổng hợp trên các nested document đã lọc.

Nested sort vẫn sắp xếp document cha. Nó không biến kết quả tìm kiếm thành danh sách offer.

### 7.1. Mapping nested

~~~java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "catalog-products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Nested)
    private List<ProductOffer> offers;

    // Constructors, getters và setters
}

public class ProductOffer {

    @Field(type = FieldType.Keyword)
    private String seller;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Boolean)
    private boolean available;

    // Constructors, getters và setters
}
~~~

Mapping JSON tương ứng:

~~~json
{
  "properties": {
    "sku": {
      "type": "keyword"
    },
    "offers": {
      "type": "nested",
      "properties": {
        "seller": {
          "type": "keyword"
        },
        "price": {
          "type": "double"
        },
        "available": {
          "type": "boolean"
        }
      }
    }
  }
}
~~~

Nếu offers là object thông thường, Elasticsearch không thể thực hiện nested sort theo semantics của nested document. Mapping phải là nested từ đầu. Muốn đổi object thành nested, cần tạo index mới và reindex dữ liệu.

### 7.2. Sort theo offer rẻ nhất

~~~json
{
  "sort": [
    {
      "offers.price": {
        "order": "asc",
        "mode": "min",
        "nested": {
          "path": "offers"
        }
      }
    }
  ]
}
~~~

Elasticsearch xem các nested offer của mỗi sản phẩm, lấy giá nhỏ nhất và dùng giá đó để sắp xếp parent document.

Với dữ liệu ví dụ, giá dùng để sort là 80. Nhưng offer giá 80 đang unavailable. Nếu giao diện muốn sort theo giá thấp nhất có thể mua, cần thêm nested filter.

### 7.3. Lọc nested document trước khi sort

~~~json
{
  "sort": [
    {
      "offers.price": {
        "order": "asc",
        "mode": "min",
        "nested": {
          "path": "offers",
          "filter": {
            "term": {
              "offers.available": true
            }
          }
        }
      }
    }
  ]
}
~~~

Giờ chỉ các offer có available=true được dùng để tính sort value. Với ví dụ, giá thấp nhất được dùng là 95 thay vì 80.

### 7.4. Nested sort filter khác query filter

Đây là điểm dễ gây nhầm lẫn:

- Nested query filter quyết định parent document nào được trả về.
- Nested sort filter quyết định nested document nào bên trong parent được dùng để tính giá trị sort.

Ví dụ query có thể yêu cầu sản phẩm có ít nhất một offer của seller-a:

~~~json
{
  "query": {
    "nested": {
      "path": "offers",
      "query": {
        "term": {
          "offers.seller": "seller-a"
        }
      }
    }
  }
}
~~~

Nếu sort chỉ có nested path mà không có filter seller-a, Elasticsearch có thể tính sort value từ tất cả offer của sản phẩm, kể cả seller-b hoặc seller-c. Điều kiện trong nested query không tự động giới hạn tập nested document dùng cho nested sort.

Nếu mục tiêu là sắp xếp theo giá offer của seller-a, cần lặp điều kiện seller-a trong nested sort filter:

~~~json
{
  "sort": [
    {
      "offers.price": {
        "order": "asc",
        "mode": "min",
        "nested": {
          "path": "offers",
          "filter": {
            "term": {
              "offers.seller": "seller-a"
            }
          }
        }
      }
    }
  ]
}
~~~

Tách riêng hai điều kiện giúp kiểm soát chính xác cả tập parent document được chọn và nested values được dùng để xếp thứ tự.

### 7.5. Không có nested document nào thỏa filter

Nếu một parent document có offers nhưng không có offer nào thỏa nested sort filter, sort không có giá trị để dùng cho parent đó. Khi đó, thuộc tính missing của sort có thể quyết định vị trí của parent document.

~~~json
{
  "sort": [
    {
      "offers.price": {
        "order": "asc",
        "mode": "min",
        "missing": "_last",
        "nested": {
          "path": "offers",
          "filter": {
            "term": {
              "offers.available": true
            }
          }
        }
      }
    }
  ]
}
~~~

Document không có offer available sẽ được xử lý như thiếu sort value và nằm cuối. Nếu nghiệp vụ cần coi trường hợp đó là một mức giá thay thế, có thể dùng missing sentinel tương thích kiểu số.

## 8. Nested sort nhiều cấp

Mapping có thể có nested object lồng nhau, ví dụ đơn hàng có items và mỗi item có discounts:

~~~json
{
  "properties": {
    "items": {
      "type": "nested",
      "properties": {
        "sku": {
          "type": "keyword"
        },
        "discounts": {
          "type": "nested",
          "properties": {
            "amount": {
              "type": "double"
            }
          }
        }
      }
    }
  }
}
~~~

Khi sort theo field ở nested level sâu, nested sort cần biểu diễn đầy đủ đường dẫn lồng nhau:

~~~json
{
  "sort": [
    {
      "items.discounts.amount": {
        "order": "desc",
        "mode": "max",
        "nested": {
          "path": "items",
          "nested": {
            "path": "items.discounts"
          }
        }
      }
    }
  ]
}
~~~

Với nested nhiều cấp, filter ở từng level có thể giới hạn object con phù hợp. Hãy kiểm tra mapping và đường dẫn thực tế; sai nested path khiến Elasticsearch không xác định được nested context.

Nested sort nhiều cấp phức tạp hơn và có thể tốn tài nguyên. Nếu thường xuyên cần sort theo một giá trị tổng hợp sâu, cân nhắc duy trì một field denormalized ở document cha để sort trực tiếp.

## 9. Sort với NativeQuery và Elasticsearch Java API Client

Sort.by(...) thuận tiện cho field đơn giản. Khi cần missing, mode, unmapped_type hoặc nested sort filter, typed sort DSL của Elasticsearch Java API Client cung cấp quyền kiểm soát chi tiết hơn.

### 9.1. Numeric sort có missing và mode

Ví dụ sort theo giá thấp nhất trong một field nhiều giá trị, đưa document thiếu giá về cuối:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.SortMode;
import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.SortOrder;

SortOptions priceSort = SortOptions.of(s -> s
    .field(f -> f
        .field("priceHistory")
        .order(SortOrder.Asc)
        .mode(SortMode.Min)
        .missing(FieldValue.of("_last"))
    )
);

NativeQuery query = NativeQuery.builder()
    .withQuery(productQuery)
    .withSortOptions(priceSort)
    .build();
~~~

Các kiểu và builder method thuộc Elasticsearch Java API Client. Tên overload hoặc cách truyền danh sách sort options có thể khác theo phiên bản; dùng đúng client version được Spring Boot quản lý.

### 9.2. Nested sort với filter

Ví dụ sort sản phẩm theo giá thấp nhất trong các offer đang available:

~~~java
import co.elastic.clients.elasticsearch._types.SortMode;
import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.SortOrder;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query availableOfferFilter = Query.of(q -> q
    .term(t -> t
        .field("offers.available")
        .value(true)
    )
);

SortOptions availableOfferPriceSort = SortOptions.of(s -> s
    .field(f -> f
        .field("offers.price")
        .order(SortOrder.Asc)
        .mode(SortMode.Min)
        .missing(FieldValue.of("_last"))
        .nested(n -> n
            .path("offers")
            .filter(availableOfferFilter)
        )
    )
);

NativeQuery query = NativeQuery.builder()
    .withQuery(productQuery)
    .withSortOptions(availableOfferPriceSort)
    .build();
~~~

Ở một số phiên bản Java API Client, tham số missing được biểu diễn bằng FieldValue; ví dụ có thể cần dùng FieldValue.of("_last") thay cho chuỗi trực tiếp. Tương tự, API withSortOptions có thể nhận một hoặc nhiều sort options. Hãy đối chiếu chữ ký builder của dependency đang dùng.

### 9.3. Kết hợp sort với Pageable

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(productQuery)
    .withSortOptions(availableOfferPriceSort)
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Pageable giới hạn kết quả cha được trả về. Nested sort chỉ quyết định thứ tự các parent hit dựa trên nested values đã lọc.

Nếu đã dùng sort options chi tiết trong NativeQuery, không nên đồng thời đặt một sort khác trong Pageable hoặc Spring Data Sort mà không xác định rõ cách các sort clause được kết hợp. Giữ thứ tự sort trong một nơi để tránh vô tình thêm hoặc thay đổi tiêu chí sắp xếp.

## 10. Sort cơ bản bằng Spring Data Sort

Với sort field đơn giản, có thể dùng:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("price"),
    Sort.Order.desc("createdAt")
);

PageRequest pageRequest = PageRequest.of(0, 20, sort);

NativeQuery query = NativeQuery.builder()
    .withQuery(productQuery)
    .withPageable(pageRequest)
    .build();
~~~

Sort cũng có thể dùng với repository:

~~~java
List<ProductDocument> products =
    productRepository.findByCategory(
        "accessories",
        Sort.by(Sort.Order.asc("price"))
    );
~~~

Các query method hỗ trợ sort phụ thuộc chữ ký method và kiểu trả về. Với sort phức tạp theo nested field, missing value hoặc multi-value mode, dùng NativeQuery với typed sort options thường rõ ràng hơn.

## 11. Sort và pagination phải dùng cùng một thứ tự ổn định

Khi phân trang, Elasticsearch cần xác định document nào thuộc trang đầu, trang tiếp theo. Nếu nhiều document có cùng sort value, thứ tự giữa chúng có thể không ổn định nếu không có tiêu chí phụ.

Ví dụ chỉ sort theo category:

~~~json
{
  "sort": [
    {
      "category": {
        "order": "asc"
      }
    }
  ]
}
~~~

Nhiều sản phẩm có cùng category. Để có thứ tự ổn định hơn, thêm một field keyword duy nhất làm tie-breaker:

~~~json
{
  "sort": [
    {
      "category": {
        "order": "asc"
      }
    },
    {
      "sku": {
        "order": "asc"
      }
    }
  ]
}
~~~

Field tie-breaker cần có doc values và giá trị duy nhất hoặc đủ ổn định trong tập kết quả. Không mặc định sort trực tiếp theo _id là lựa chọn tốt; _id không được thiết kế như một field sort thông thường. Có thể lưu một bản sao ID nghiệp vụ vào field keyword có doc values để dùng làm tie-breaker.

### 11.1. Offset pagination

Với số trang nhỏ, có thể dùng from/size thông qua Pageable:

~~~java
PageRequest.of(0, 20);
PageRequest.of(1, 20);
~~~

Offset pagination đơn giản nhưng tốn kém khi đi sâu vào tập kết quả lớn. Elasticsearch cũng giới hạn tổng số hit có thể truy cập bằng from/size theo index setting.

### 11.2. search_after

Với pagination sâu, dùng sort ổn định và giá trị sort của hit cuối trang làm con trỏ:

~~~json
{
  "size": 20,
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    },
    {
      "sku": {
        "order": "asc"
      }
    }
  ],
  "search_after": [
    129.5,
    "KB-1042"
  ],
  "query": {
    "match_all": {}
  }
}
~~~

Giá trị trong search_after phải theo đúng thứ tự và kiểu của các sort clause. Có thể lấy các giá trị đó từ SearchHit.getSortValues() của hit cuối trang.

Không dùng from lớn cùng search_after; hai cách pagination có mục đích khác nhau. Với dữ liệu thay đổi liên tục, cân nhắc kết hợp Point in Time (PIT) để giữ một view ổn định trong suốt quá trình phân trang.

### 11.3. Nested sort và search_after

Khi sort theo nested field, sort value của parent hit là giá trị đã được tính theo nested path, filter và mode. search_after dùng sort values của parent hit như các sort khác.

Để pagination chính xác:

- Giữ nguyên nested sort path, filter và mode giữa các trang.
- Giữ nguyên thứ tự sort clause.
- Thêm tie-breaker ổn định ở cấp parent document.
- Nếu dùng PIT, sử dụng PIT ID mới nhất theo response và đóng PIT khi hoàn tất.

Không tự tính lại giá trị nested sort ở phía Java rồi dùng làm con trỏ; hãy dùng sort values Elasticsearch trả về.

## 12. Kết hợp missing, mode và nested filter

Ba khái niệm có thể kết hợp:

- missing: vị trí hoặc giá trị thay thế khi không có sort value.
- mode: cách chọn một giá trị từ nhiều giá trị.
- nested.filter: nested object nào được đưa vào tập giá trị để tính sort.

Ví dụ:

~~~json
{
  "sort": [
    {
      "offers.price": {
        "order": "asc",
        "mode": "min",
        "missing": "_last",
        "nested": {
          "path": "offers",
          "filter": {
            "term": {
              "offers.available": true
            }
          }
        }
      }
    }
  ]
}
~~~

Đọc theo thứ tự:

1. Đi vào nested path offers.
2. Chỉ xét offer có available là true.
3. Lấy giá nhỏ nhất trong các offer còn lại.
4. Sort parent document theo giá tăng dần.
5. Nếu không còn offer phù hợp, đặt parent document ở cuối.

Đây là mẫu hữu ích cho danh mục sản phẩm: xếp sản phẩm theo giá bán thấp nhất có thể mua và đưa sản phẩm không có offer khả dụng xuống cuối.

## 13. Sort theo nhiều nested field

Một truy vấn có thể sort theo nhiều nested field:

~~~json
{
  "sort": [
    {
      "offers.price": {
        "order": "asc",
        "mode": "min",
        "nested": {
          "path": "offers",
          "filter": {
            "term": {
              "offers.available": true
            }
          }
        }
      }
    },
    {
      "offers.seller": {
        "order": "asc",
        "mode": "min",
        "nested": {
          "path": "offers",
          "filter": {
            "term": {
              "offers.available": true
            }
          }
        }
      }
    },
    {
      "sku": {
        "order": "asc"
      }
    }
  ]
}
~~~

Mỗi sort clause có nested context riêng. Nếu nhiều tiêu chí phải dùng cùng một tập nested object, hãy đảm bảo filter của chúng nhất quán. Elasticsearch tính từng sort value theo cấu hình của từng clause; sort theo giá và sort theo seller không mặc nhiên gắn với cùng một offer đã chọn nếu các clause có filter/mode khác nhau.

Nếu nghiệp vụ cần sort theo một offer cụ thể, ví dụ offer có seller được người dùng chọn, hãy lọc theo seller trong từng nested sort clause thay vì chỉ sort toàn bộ offers.

## 14. Nested sort và inner_hits là hai việc khác nhau

Nested sort chọn thứ tự parent document dựa trên nested values. Inner hits trả nested document khớp query trong response.

| Cơ chế | Mục tiêu |
| --- | --- |
| Nested query | Chọn parent document có nested object khớp |
| Nested sort | Tính sort value của parent từ nested object |
| Inner hits | Trả nested object khớp trong kết quả |

Một query có thể dùng cả ba:

- Nested query lọc sản phẩm có offer đang available.
- Nested sort sắp xếp sản phẩm theo giá thấp nhất của offer available.
- Inner hits trả offer available phù hợp để giao diện hiển thị.

Tuy nhiên, filter trong nested query, nested sort và inner hits là các cấu hình riêng. Nếu cần cùng một điều kiện, phải khai báo nhất quán ở từng phần.

## 15. Nested sort với filter kết hợp nhiều điều kiện

Ví dụ chỉ sort theo offer:

- Đang available.
- Thuộc seller-a hoặc seller-b.
- Có giá từ 50 trở lên.

Nested filter:

~~~json
{
  "bool": {
    "filter": [
      {
        "terms": {
          "offers.seller": ["seller-a", "seller-b"]
        }
      },
      {
        "term": {
          "offers.available": true
        }
      },
      {
        "range": {
          "offers.price": {
            "gte": 50
          }
        }
      }
    ]
  }
}
~~~

Đặt filter vào nested sort:

~~~json
{
  "sort": [
    {
      "offers.price": {
        "order": "asc",
        "mode": "min",
        "missing": "_last",
        "nested": {
          "path": "offers",
          "filter": {
            "bool": {
              "filter": [
                {
                  "terms": {
                    "offers.seller": ["seller-a", "seller-b"]
                  }
                },
                {
                  "term": {
                    "offers.available": true
                  }
                },
                {
                  "range": {
                    "offers.price": {
                      "gte": 50
                    }
                  }
                }
              ]
            }
          }
        }
      }
    }
  ]
}
~~~

Nested sort filter chỉ tác động đến việc tính sort value. Nếu chỉ muốn trả các parent document có ít nhất một offer như vậy, cần thêm nested query tương ứng vào phần query chính.

## 16. Sort theo date nhiều giá trị

Một document có thể chứa nhiều thời điểm, ví dụ các ngày giao hàng dự kiến:

~~~json
{
  "orderId": "ORD-1001",
  "deliveryWindows": [
    "2026-03-15T09:00:00Z",
    "2026-03-17T09:00:00Z"
  ]
}
~~~

Sort theo ngày giao sớm nhất:

~~~json
{
  "sort": [
    {
      "deliveryWindows": {
        "order": "asc",
        "mode": "min"
      }
    }
  ]
}
~~~

Sort theo ngày giao muộn nhất:

~~~json
{
  "sort": [
    {
      "deliveryWindows": {
        "order": "desc",
        "mode": "max"
      }
    }
  ]
}
~~~

Với date field nhiều giá trị, mode min/max thường phù hợp hơn. Nếu muốn sắp xếp theo ngày giao khả dụng tiếp theo kể từ hiện tại, có thể cần filter hoặc mô hình hóa riêng; không nên mặc định min luôn là giá trị đúng cho nghiệp vụ.

## 17. Geo distance sort và missing location

Field geo_point có thể sort theo khoảng cách tới một tọa độ:

~~~json
{
  "sort": [
    {
      "_geo_distance": {
        "location": {
          "lat": 10.7769,
          "lon": 106.7009
        },
        "order": "asc",
        "unit": "km",
        "distance_type": "arc",
        "mode": "min"
      }
    }
  ]
}
~~~

Nếu field location thiếu, document không có khoảng cách để sort. Elasticsearch có các quy tắc missing dành cho geo sort tùy API; hãy kiểm tra tài liệu client và phiên bản đang dùng trước khi cấu hình. Nếu giao diện cần giữ document không có tọa độ, có thể tách chúng thành một nhóm hoặc bổ sung field nghiệp vụ thể hiện trạng thái vị trí.

Không dùng numeric sentinel như 0 cho khoảng cách nếu điều đó khiến document không có tọa độ được xếp như thể nằm ngay tại vị trí tìm kiếm.

## 18. Các giới hạn và lưu ý hiệu năng

Sort thường tốn chi phí hơn filter đơn giản vì Elasticsearch phải xác định thứ tự các hit. Một số điểm cần cân nhắc:

- Field sort nên có doc values. Keyword và numeric thường được cấu hình phù hợp mặc định.
- Sort trên text bằng fielddata có thể tiêu thụ nhiều heap; ưu tiên keyword multi-field.
- Multi-valued sort cần tổng hợp nhiều giá trị cho từng document.
- Nested sort cần xét nested documents và có thể áp dụng filter cho từng parent.
- Nested sort nhiều cấp làm query phức tạp và tăng chi phí.
- Nhiều sort clause làm tăng công việc so sánh và lưu sort values.
- Deep pagination bằng from/size tốn tài nguyên; cân nhắc search_after và PIT.
- Không trả quá nhiều nested inner hits chỉ để hiển thị một vài giá trị sort.

Nếu một nested sort được dùng thường xuyên và filter luôn giống nhau, cân nhắc tính sẵn một field ở parent document, ví dụ lowestAvailableOfferPrice. Khi ghi hoặc cập nhật offers, ứng dụng cập nhật field tổng hợp này. Sort trực tiếp trên field cha thường đơn giản và nhanh hơn, đổi lại ứng dụng phải duy trì tính nhất quán của dữ liệu tổng hợp.

## 19. Lỗi thường gặp

**Không cấu hình missing và cho rằng mọi document đều có giá trị.** Document thiếu field có thể xuất hiện ở cuối mặc định. Khai báo rõ missing nếu thứ tự đó là yêu cầu nghiệp vụ.

**Nhầm field null với null_value.** Null chỉ được index theo giá trị thay thế khi mapping khai báo null_value; field bị bỏ qua vẫn là missing.

**Dùng unmapped_type để xử lý document thiếu field.** unmapped_type dành cho index không có mapping field; missing xử lý document không có giá trị.

**Sort multi-valued mà không xác định mode.** Mặc định phụ thuộc chiều sort. Khai báo min/max/avg/sum/median rõ ràng khi có ý nghĩa nghiệp vụ.

**Dùng avg hoặc sum cho keyword.** Các mode tổng hợp số không phù hợp với chuỗi. Keyword thường dùng min hoặc max.

**Sort theo text field.** Dùng keyword subfield thay vì bật fielddata một cách tùy tiện.

**Sort nested field nhưng quên nested path.** Elasticsearch cần biết nested context. Mapping phải là nested và sort cần chỉ rõ path.

**Cho rằng nested query filter tự áp dụng vào nested sort.** Hai cấu hình độc lập. Lặp filter trong nested sort nếu chỉ muốn sort trên các nested object thỏa điều kiện.

**Sort theo giá thấp nhất nhưng không lọc offer khả dụng.** Kết quả có thể dựa vào offer hết hàng. Đặt nested filter cho available hoặc trạng thái nghiệp vụ phù hợp.

**Không đặt missing cho nested sort không có phần tử phù hợp.** Parent document không có nested value sau filter cần được xếp theo quy tắc rõ ràng.

**Dùng nested sort cho field object thường.** Nested sort chỉ dành cho mapping nested. Kiểm tra mapping trước khi viết query.

**Sort nhiều trang mà không có tie-breaker.** Các document cùng giá trị sort có thể đổi thứ tự. Thêm field keyword ổn định và duy nhất.

**Dùng _id làm tie-breaker mà không kiểm tra khả năng sort.** Lưu một bản sao ID vào keyword field có doc values nếu cần sort ổn định.

**Kết hợp nhiều nguồn sort mà không biết thứ tự clause.** Sort trong NativeQuery và Pageable có thể được kết hợp theo builder/version. Giữ sort definition ở một nơi và xác nhận request DSL.

## 20. Quy trình chọn cách sort

Khi thiết kế sort cho kết quả tìm kiếm:

1. Xác định field được sort và kiểu mapping thực tế.
2. Xác định field có thể thiếu, null, mảng nhiều giá trị hay nested object.
3. Với missing value, chọn _first, _last hoặc giá trị thay thế tương thích kiểu.
4. Với multi-valued field, chọn mode min, max, sum, avg hoặc median theo ý nghĩa nghiệp vụ.
5. Với nested field, khai báo path và filter để xác định đúng nested object được xét.
6. Nếu query chính cũng có nested filter, lặp lại điều kiện cần thiết trong nested sort.
7. Chọn Spring Data Sort cho trường hợp đơn giản hoặc NativeQuery typed SortOptions cho cấu hình nâng cao.
8. Kết hợp sort với pagination; thêm tie-breaker ổn định.
9. Với dữ liệu lớn, cân nhắc search_after và PIT thay cho offset sâu.
10. Kiểm tra các trường hợp biên: thiếu field, null, mảng rỗng, nested filter không khớp và nhiều giá trị trùng nhau.
11. Đo hiệu năng trên dữ liệu đại diện và cân nhắc field tổng hợp ở parent nếu nested sort quá tốn kém.

Sort chính xác cần cả mapping đúng và quy tắc chọn giá trị rõ ràng. Missing quyết định vị trí của document không có giá trị; mode quyết định giá trị đại diện cho field nhiều phần tử; nested path và filter quyết định object con nào tham gia sort. Khi ba phần này được xác định đúng, kết quả sắp xếp sẽ phản ánh đúng yêu cầu nghiệp vụ và pagination có thể hoạt động ổn định.

## 21. Tài liệu tham khảo

- [Elasticsearch - Sort search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/sort-search-results): missing values, multi-valued sort, sort mode và nested sort.
- [Elasticsearch - Nested field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/nested): mapping nested và giới hạn nested documents.
- [Elasticsearch - Paginate search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results): from/size, search_after và Point in Time.
- [Elasticsearch - Doc values](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/doc-values): dữ liệu phục vụ sort và aggregation.
- [Spring Data Elasticsearch - Query and sort](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): thực thi query và sử dụng abstraction của Spring Data.
- [Elasticsearch Java API Client - Sorting](https://www.elastic.co/docs/reference/elasticsearch/clients/java/usage/sort): xây dựng sort options bằng Java client.

Các builder method của Spring Data Elasticsearch và Elasticsearch Java API Client có thể thay đổi theo phiên bản. Khi triển khai nested sort hoặc missing/mode options, hãy đối chiếu Javadoc của dependency thực tế và kiểm tra JSON request được gửi tới cluster.
