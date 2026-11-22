# Truyền chuỗi, số, boolean, collection và giá trị đặc biệt

Trong Spring Data Elasticsearch, annotation **@Query** cho phép khai báo Query DSL dưới dạng chuỗi JSON ngay trên repository method. Khi query có giá trị thay đổi theo tham số đầu vào, ta dùng placeholder theo vị trí như **?0**, **?1** để Spring Data gắn giá trị từ method vào query.

Việc truyền tham số cần giữ đúng kiểu JSON. Chuỗi phải nằm trong dấu nháy kép, số và boolean là literal JSON không có dấu nháy, còn collection thường được truyền dưới dạng mảng JSON cho các query như **terms**. Ngoài kiểu dữ liệu, cần chú ý escaping ký tự đặc biệt, giá trị null, collection rỗng, ngày giờ và sự khác nhau giữa việc thay một giá trị với việc thay đổi cấu trúc Query DSL.

Bài học này trình bày cách truyền các kiểu tham số thường gặp trong query JSON, cách viết repository method rõ ràng, các lỗi thường gặp và thời điểm nên chuyển sang **ElasticsearchOperations** để xây dựng query động.

## 1. Placeholder trong @Query hoạt động như thế nào?

Một repository method có thể khai báo query JSON với placeholder:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "term": {
            "status": "?0"
          }
        }
        """)
    List<Product> findByStatusValue(String status);
}
~~~

Placeholder **?0** tham chiếu tham số đầu tiên trong danh sách tham số của method. Chỉ số bắt đầu từ 0:

- **?0** là tham số thứ nhất.
- **?1** là tham số thứ hai.
- **?2** là tham số thứ ba.

Ví dụ:

~~~java
@Query("""
    {
      "range": {
        "price": {
          "gte": ?0,
          "lte": ?1
        }
      }
    }
    """)
List<Product> findInPriceRange(
    Double minPrice,
    Double maxPrice
);
~~~

Ở đây, **?0** nhận minPrice và **?1** nhận maxPrice. Thứ tự placeholder phải khớp với thứ tự tham số Java, không dựa trên tên biến.

Có thể dùng lại cùng một placeholder nhiều lần nếu query cần cùng một giá trị ở nhiều vị trí. Tránh sao chép một giá trị vào chuỗi query bằng phép nối Java; placeholder giúp tách cấu trúc Query DSL khỏi dữ liệu đầu vào.

### Placeholder chỉ thay giá trị

Placeholder dùng để truyền dữ liệu vào vị trí giá trị trong JSON. Không nên dùng nó để thay tên field, tên query, toán tử hoặc một đoạn cấu trúc JSON tùy ý.

Ví dụ, không thiết kế method với mục đích truyền tên field vào chỗ này:

~~~json
{
  "term": {
    "?0": "?1"
  }
}
~~~

Tên field và loại query là một phần cấu trúc của request. Nếu ứng dụng cần chọn field hoặc chiến lược tìm kiếm theo điều kiện runtime, hãy dùng code để chọn một cấu trúc query đã được kiểm soát, hoặc xây dựng query bằng Criteria/NativeQuery. Không nhận tên field tùy ý từ request công khai rồi chèn vào JSON.

## 2. Truyền giá trị kiểu String

Với một giá trị chuỗi, placeholder nằm trong dấu nháy kép vì Query DSL là JSON:

~~~java
@Query("""
    {
      "term": {
        "status": "?0"
      }
    }
    """)
List<Product> findByStatus(String status);
~~~

Nếu truyền **"ACTIVE"**, giá trị được dùng cho field status. Field nên có mapping phù hợp, thường là **keyword** khi cần exact match.

Ví dụ mapping:

~~~java
@Field(type = FieldType.Keyword)
private String status;
~~~

Với full-text search trên field text, dùng **match** thay vì term:

~~~java
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
List<Product> searchName(String phrase);
~~~

Sự khác biệt nằm ở semantics của query:

- **term** so khớp term chính xác, thường phù hợp với keyword field.
- **match** phân tích chuỗi truy vấn theo analyzer của field, phù hợp với full-text search.

### Chuỗi có khoảng trắng

Chuỗi có dấu cách vẫn là một giá trị JSON string bình thường:

~~~java
@Query("""
    {
      "match_phrase": {
        "name": "?0"
      }
    }
    """)
List<Product> findNamePhrase(String phrase);
~~~

Không cần tự chia chuỗi thành token trong Java nếu mục tiêu là để analyzer và Query DSL xử lý nội dung. Hãy chọn đúng query type theo hành vi tìm kiếm mong muốn.

### Chuỗi có dấu tiếng Việt và Unicode

JSON hỗ trợ Unicode. Có thể truyền trực tiếp chuỗi như **"Bàn phím cơ"**, **"Đồ gia dụng"** hoặc tên chứa ký tự ngoài ASCII. Kết quả tìm kiếm còn phụ thuộc analyzer, normalizer và mapping của field.

Không nên mặc định rằng mọi analyzer đều xử lý dấu tiếng Việt theo cùng một cách. Nếu cần tìm không phân biệt dấu hoặc chữ hoa/chữ thường, thiết kế analyzer/normalizer phù hợp và kiểm tra bằng dữ liệu thực tế.

## 3. Truyền số: integer, long và decimal

Giá trị số trong JSON không được đặt trong dấu nháy kép. Ví dụ range query:

~~~java
@Query("""
    {
      "range": {
        "price": {
          "gte": ?0,
          "lt": ?1
        }
      }
    }
    """)
List<Product> findPriceRange(
    Double minPrice,
    Double maxPrice
);
~~~

Nếu minPrice là 20.5 và maxPrice là 100.0, các giá trị được đưa vào vị trí số trong JSON. Field Elasticsearch phải có kiểu numeric tương thích, ví dụ **double**, **float**, **integer** hoặc **long**.

Mapping:

~~~java
@Field(type = FieldType.Double)
private Double price;

@Field(type = FieldType.Integer)
private Integer quantity;

@Field(type = FieldType.Long)
private Long viewCount;
~~~

### Không truyền số dưới dạng chuỗi nếu query cần số

Hai JSON value sau khác kiểu:

~~~json
{
  "term": {
    "quantity": 12
  }
}
~~~

~~~json
{
  "term": {
    "quantity": "12"
  }
}
~~~

Giá trị đầu là number; giá trị sau là string. Nếu field được mapping là numeric, dùng số đúng kiểu. Không thêm dấu nháy quanh placeholder số.

### Độ chính xác và giới hạn số

Dùng kiểu Java phù hợp với miền giá trị:

- **Integer** cho số nguyên trong giới hạn 32-bit.
- **Long** cho số nguyên lớn hơn.
- **Double** hoặc **Float** cho số thực khi độ chính xác nhị phân phù hợp.
- **BigDecimal** trong domain khi cần biểu diễn tiền tệ với quy tắc decimal rõ ràng; khi tạo query JSON, cần đảm bảo giá trị được serialize thành JSON number theo API đang dùng.

Đừng dùng số thực nhị phân như một cách lưu tiền tệ mà không cân nhắc sai số. Với giá trị tài chính, cần thống nhất kiểu dữ liệu, scale và cách mapping ngay từ thiết kế index.

### Không phụ thuộc định dạng số theo locale

JSON number dùng dấu chấm cho phần thập phân. Không đưa chuỗi **"12,5"** vào vị trí number vì dấu phẩy là dấu phân cách trong JSON, không phải dấu thập phân. Hãy truyền giá trị numeric Java và để cơ chế binding/serialization tạo literal JSON phù hợp.

## 4. Truyền boolean

Boolean trong JSON là literal **true** hoặc **false**, viết thường và không có dấu nháy:

~~~java
@Query("""
    {
      "term": {
        "available": ?0
      }
    }
    """)
List<Product> findByAvailability(Boolean available);
~~~

Mapping entity:

~~~java
@Field(type = FieldType.Boolean)
private Boolean available;
~~~

Không viết placeholder boolean thành **"?0"** nếu field là boolean. Khi có dấu nháy, JSON value trở thành string thay vì boolean.

Ví dụ kết hợp nhiều kiểu:

~~~java
@Query("""
    {
      "bool": {
        "filter": [
          { "term": { "status": "?0" } },
          { "term": { "available": ?1 } },
          { "range": { "price": { "gte": ?2 } } }
        ]
      }
    }
    """)
List<Product> searchAvailableProducts(
    String status,
    Boolean available,
    Double minPrice
);
~~~

Trong ví dụ này:

- status là chuỗi nên placeholder có dấu nháy.
- available là boolean nên placeholder không có dấu nháy.
- minPrice là số nên placeholder không có dấu nháy.

## 5. Truyền collection và mảng

Với một danh sách giá trị, query thường dùng **terms**. Placeholder collection nằm ở vị trí JSON array và không được đặt trong dấu nháy:

~~~java
@Query("""
    {
      "terms": {
        "category": ?0
      }
    }
    """)
List<Product> findByCategories(Collection<String> categories);
~~~

Tham số có thể là **List**, **Set**, **Collection** hoặc mảng phù hợp với kiểu binding mà phiên bản Spring Data hỗ trợ. Ví dụ:

~~~java
List<String> categories =
    List.of("accessories", "office", "computer");

List<Product> products =
    repository.findByCategories(categories);
~~~

Với terms query, Elasticsearch tìm các document có giá trị field thuộc tập được truyền vào. Đây thường là exact match trên keyword field.

Mapping:

~~~java
@Field(type = FieldType.Keyword)
private String category;
~~~

### Collection số

Collection số cũng được truyền vào vị trí array:

~~~java
@Query("""
    {
      "terms": {
        "rating": ?0
      }
    }
    """)
List<Product> findByRatings(Collection<Integer> ratings);
~~~

Các phần tử phải tương thích với kiểu field được query. Không trộn chuỗi và số trong cùng một collection nếu mapping và nghiệp vụ không định nghĩa rõ cách xử lý.

### Collection enum

Nếu domain dùng enum, hãy thống nhất cách lưu enum trong Elasticsearch. Ví dụ enum được lưu bằng tên:

~~~java
public enum ProductStatus {
    ACTIVE,
    DISCONTINUED,
    DRAFT
}
~~~

Khi truyền collection enum, cần xác nhận converter và cơ chế binding tạo đúng giá trị JSON mà mapping đang lưu. Nếu không chắc, chuyển enum sang danh sách chuỗi rõ ràng ở tầng service:

~~~java
List<String> statusNames = statuses.stream()
    .map(Enum::name)
    .toList();
~~~

Không giả định enum luôn được serialize theo name(), toString() hoặc một converter cụ thể nếu ứng dụng đã tùy chỉnh conversion.

### Collection rỗng

Collection rỗng là trường hợp cần quyết định rõ. Một terms query với danh sách rỗng không có nghĩa là bỏ điều kiện lọc; thông thường nó không khớp document nào.

Ví dụ, nếu categories rỗng có nghĩa người dùng chưa chọn category và muốn tìm mọi category, đừng gọi method trên với danh sách rỗng. Hãy bỏ filter đó khỏi query. Nếu danh sách rỗng có nghĩa không có giá trị nào được phép, query không kết quả có thể là hành vi đúng.

Có thể kiểm tra trước khi gọi repository:

~~~java
if (categories == null || categories.isEmpty()) {
    return repository.findAll();
}

return repository.findByCategories(categories);
~~~

Đây chỉ là ví dụ cho một use case đơn giản; trong ứng dụng thực tế, nên tạo query phù hợp với các filter còn lại thay vì gọi findAll nếu vẫn cần những điều kiện khác.

## 6. Truyền ngày giờ và giá trị thời gian

Elasticsearch thường lưu date dưới dạng giá trị thời gian được index theo mapping **date** hoặc **date_nanos**. Query JSON có thể dùng chuỗi ISO 8601 hoặc giá trị epoch phù hợp với date format được cấu hình.

Ví dụ:

~~~java
@Query("""
    {
      "range": {
        "createdAt": {
          "gte": "?0",
          "lt": "?1"
        }
      }
    }
    """)
List<Product> findCreatedBetween(
    String from,
    String to
);
~~~

Giá trị truyền vào có thể là chuỗi ISO 8601, ví dụ:

~~~text
2026-01-01T00:00:00Z
2026-02-01T00:00:00Z
~~~

Dùng khoảng nửa mở **gte** và **lt** thường thuận tiện cho khoảng ngày liên tiếp: thời điểm đầu được tính, thời điểm cuối không được tính. Nhờ vậy, hai khoảng liền nhau không bị trùng ở ranh giới.

### Dùng Instant hoặc LocalDate

Trong domain, có thể dùng **Instant**, **LocalDate** hoặc **OffsetDateTime**. Tuy nhiên, cách tham số được chuyển thành giá trị trong chuỗi query annotation phụ thuộc cơ chế conversion và phiên bản Spring Data Elasticsearch.

Nếu cần định dạng chắc chắn, có thể chuẩn hóa tham số thành chuỗi ISO 8601 trước khi gọi repository:

~~~java
String fromValue = from.toString();
String toValue = to.toString();

return repository.findCreatedBetween(fromValue, toValue);
~~~

Với **LocalDate**, cần xác định múi giờ và thời điểm bắt đầu/kết thúc ngày trước khi tạo range. Một ngày theo lịch ở một múi giờ cụ thể không nhất thiết tương ứng với một khoảng UTC cố định 24 giờ trong mọi trường hợp chuyển đổi múi giờ.

Nếu date field dùng format tùy chỉnh hoặc cần date math như **now-7d/d**, hãy kiểm tra mapping và Query DSL. Date math là cú pháp giá trị của Elasticsearch, không phải biểu thức Java.

## 7. Giá trị null và field bị thiếu

Null cần được phân biệt với việc không đưa điều kiện vào query.

Một JSON value null:

~~~json
{
  "term": {
    "discountCode": null
  }
}
~~~

không có nghĩa là query mọi document không có discountCode. Elasticsearch không index giá trị null theo cách giống một giá trị term thông thường, trừ khi mapping dùng tùy chọn như **null_value**. Để tìm document không có field, thường dùng **must_not** kết hợp **exists**:

~~~json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "exists": {
            "field": "discountCode"
          }
        }
      ]
    }
  }
}
~~~

### Không dùng null để biểu diễn filter tùy chọn

Giả sử màn hình tìm kiếm có category không bắt buộc. Nếu category là null, nghiệp vụ có thể muốn bỏ điều kiện category khỏi query.

Không nên mặc định truyền null vào placeholder và kỳ vọng Spring Data tự xóa toàn bộ clause. Placeholder thay giá trị; nó không tự quyết định có nên bỏ một nhánh query hay không.

Với query động, xây dựng các filter chỉ khi tham số có giá trị:

~~~java
Criteria criteria = new Criteria();

if (category != null && !category.isBlank()) {
    criteria.and("category").is(category);
}

if (minPrice != null) {
    criteria.and("price").greaterThanEqual(minPrice);
}
~~~

Ví dụ dùng Criteria để minh họa ý tưởng. Cần điều chỉnh cách khởi tạo và kết hợp Criteria theo API của phiên bản đang dùng. Với Query DSL phức tạp, dùng NativeQuery để thêm hoặc bỏ từng clause có điều kiện.

### Phân biệt null, missing và empty string

Ba trạng thái này không giống nhau:

| Trạng thái | Ý nghĩa |
|---|---|
| null | Giá trị được gửi hoặc lưu là null |
| Missing | Document không có field đó trong _source/index |
| Empty string | Field tồn tại với chuỗi rỗng "" |

Cách Elasticsearch index và query các trạng thái này phụ thuộc mapping, null_value và dữ liệu được ghi. Hãy định nghĩa rõ nghiệp vụ muốn tìm trạng thái nào.

## 8. Chuỗi có ký tự đặc biệt và escaping

Giá trị người dùng có thể chứa dấu nháy kép, dấu gạch chéo ngược, ký tự xuống dòng, dấu tiếng Việt hoặc các ký tự có ý nghĩa đặc biệt trong Query DSL.

Ví dụ chuỗi:

~~~text
Keyboard "Pro" \ Edition
~~~

Khi truyền bằng placeholder, để Spring Data thực hiện cơ chế binding/escaping mà phiên bản hỗ trợ. Không tự nối chuỗi vào JSON và không tự thêm dấu nháy lần thứ hai. Nếu tự ghép JSON, dấu nháy hoặc backslash trong dữ liệu có thể làm JSON không hợp lệ hoặc thay đổi ý nghĩa query.

Ví dụ cách nên dùng:

~~~java
@Query("""
    {
      "term": {
        "displayName": "?0"
      }
    }
    """)
List<Product> findByDisplayName(String displayName);
~~~

Tránh cách ghép chuỗi:

~~~java
String json = "{\"term\":{\"displayName\":\"" + displayName + "\"}}";
~~~

Cách ghép trên dễ lỗi khi displayName có dấu nháy hoặc backslash. Nó cũng khiến cấu trúc query và dữ liệu đầu vào bị trộn lẫn.

### JSON escaping và Query DSL escaping là hai việc khác nhau

Một chuỗi có thể hợp lệ trong JSON nhưng vẫn mang ý nghĩa đặc biệt đối với query con.

Ví dụ **query_string** dùng cú pháp riêng với các ký tự như:

~~~text
+ - = && || > < ! ( ) { } [ ] ^ " ~ * ? : \ /
~~~

JSON escaping chỉ bảo đảm chuỗi là JSON hợp lệ. Nó không tự động vô hiệu hóa cú pháp query_string. Nếu đưa input người dùng vào query_string, các ký tự có thể được diễn giải như toán tử hoặc cú pháp tìm kiếm.

Với tìm kiếm thông thường, ưu tiên **match** hoặc **multi_match** để analyzer xử lý văn bản. Chỉ dùng query_string khi sản phẩm thực sự muốn cung cấp một ngôn ngữ truy vấn cho người dùng và đã có quy tắc escaping/validation phù hợp.

### Wildcard và ký tự đại diện

Nếu nghiệp vụ cần wildcard, dùng query type rõ ràng:

~~~java
@Query("""
    {
      "wildcard": {
        "sku": {
          "value": "?0"
        }
      }
    }
    """)
List<Product> findBySkuPattern(String pattern);
~~~

Giá trị như **KB-*** có thể dùng dấu * theo semantics wildcard. Đây là cú pháp của query, không phải JSON escaping. Hãy kiểm soát độ phức tạp của pattern vì wildcard rộng, đặc biệt pattern bắt đầu bằng *, có thể tốn tài nguyên.

Đừng dùng wildcard query thay cho full-text search. Với nội dung dài và nhiều từ, match query thường phù hợp hơn.

## 9. Truyền nhiều kiểu trong một query

Một query có thể kết hợp string, boolean, number và collection. Ví dụ:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "bool": {
            "filter": [
              {
                "term": {
                  "status": "?0"
                }
              },
              {
                "term": {
                  "available": ?1
                }
              },
              {
                "range": {
                  "price": {
                    "gte": ?2,
                    "lte": ?3
                  }
                }
              },
              {
                "terms": {
                  "category": ?4
                }
              }
            ]
          }
        }
        """)
    List<Product> searchProducts(
        String status,
        Boolean available,
        Double minPrice,
        Double maxPrice,
        Collection<String> categories
    );
}
~~~

Cách đọc tham số:

| Placeholder | Java parameter | JSON value |
|---|---|---|
| **?0** | String status | String, có dấu nháy |
| **?1** | Boolean available | Boolean, không có dấu nháy |
| **?2** | Double minPrice | Number, không có dấu nháy |
| **?3** | Double maxPrice | Number, không có dấu nháy |
| **?4** | Collection<String> categories | JSON array, không có dấu nháy bao quanh placeholder |

Ví dụ này giả định tất cả filter đều bắt buộc và categories không rỗng. Nếu một filter là tùy chọn, hãy xây dựng query động thay vì truyền null rồi mong clause tự biến mất.

## 10. Tham số có giá trị mặc định và filter tùy chọn

Repository method với @Query thường phù hợp khi cấu trúc JSON cố định. Khi số filter tùy chọn tăng lên, một annotation có thể trở nên khó sử dụng.

Ví dụ use case:

- keyword có thể trống.
- category có thể không được chọn.
- minPrice và maxPrice độc lập.
- available có thể là true, false hoặc không lọc.
- danh sách brand có thể rỗng.

Nếu cố đưa tất cả vào một query JSON cố định, ta phải định nghĩa chính xác semantics của từng trạng thái. Query không tự biết null có nghĩa là bỏ clause, còn false là giá trị boolean cần lọc.

Một cách triển khai rõ ràng là tạo query từ criteria:

~~~java
public SearchHits<Product> search(ProductFilter filter) {
    Criteria criteria = new Criteria();

    if (filter.keyword() != null && !filter.keyword().isBlank()) {
        criteria.and("name").matches(filter.keyword());
    }

    if (filter.category() != null) {
        criteria.and("category").is(filter.category());
    }

    if (filter.minPrice() != null) {
        criteria.and("price").greaterThanEqual(filter.minPrice());
    }

    if (filter.maxPrice() != null) {
        criteria.and("price").lessThanEqual(filter.maxPrice());
    }

    Query query = new CriteriaQuery(criteria);

    return operations.search(query, Product.class);
}
~~~

Đây là ví dụ khái niệm; cách ghép nhiều Criteria, đặc biệt với cùng một property hoặc nested condition, cần kiểm tra theo API version. Nếu cần nhiều nhánh bool hoặc query đặc biệt, NativeQuery thường cho cấu trúc rõ hơn.

### Phân biệt boolean false với không lọc

Đối với Boolean nullable:

- **true** có nghĩa lọc các document có available true.
- **false** có nghĩa lọc các document có available false.
- **null** có thể có nghĩa không áp dụng filter.

Không dùng điều kiện if (available) vì cách viết đó bỏ qua giá trị false. Hãy kiểm tra available khác null:

~~~java
if (available != null) {
    criteria.and("available").is(available);
}
~~~

Đây là lỗi phổ biến trong filter tìm kiếm có boolean tùy chọn.

## 11. Giá trị đặc biệt: enum, ID, text và các kiểu domain

### Enum

Quyết định enum được lưu bằng tên, mã nghiệp vụ hay chuỗi tùy chỉnh. Query parameter phải dùng đúng representation đã index.

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

Nếu mapping lưu PAID, query exact match phải truyền PAID. Nếu converter lưu mã như P, hãy truyền mã tương ứng. Không mặc định enum trong Java và giá trị trong index luôn giống nhau.

### Document ID

Nếu query trên _id, cần dùng query phù hợp:

~~~java
@Query("""
    {
      "ids": {
        "values": ?0
      }
    }
    """)
List<Product> findByDocumentIds(Collection<String> ids);
~~~

ids query nhận danh sách ID. Không nhầm _id với một property nghiệp vụ khác tên id trong _source.

### Giá trị text đã phân tích

Đối với field text, match query thường nhận một chuỗi và analyzer xử lý nó:

~~~java
@Query("""
    {
      "match": {
        "description": {
          "query": "?0"
        }
      }
    }
    """)
List<Product> searchDescription(String text);
~~~

Nếu muốn tìm chính xác cả chuỗi, dùng keyword subfield và term query. Cần hiểu rõ analyzer/normalizer trước khi quyết định query.

### Geo và các giá trị có cấu trúc

Một số kiểu dữ liệu cần cấu trúc JSON riêng, ví dụ geo point:

~~~json
{
  "geo_distance": {
    "distance": "10km",
    "location": {
      "lat": 10.78,
      "lon": 106.69
    }
  }
}
~~~

Nếu phải truyền object có nhiều field như tọa độ, range hoặc một cấu trúc lồng nhau, việc bind cả object qua một placeholder có thể phụ thuộc serializer và phiên bản. Có thể truyền các giá trị scalar riêng hoặc dùng NativeQuery để tạo object query có kiểu dữ liệu rõ ràng.

Không nên biến một object Java thành chuỗi JSON bằng toString() rồi chèn vào query. toString() không phải JSON serializer.

## 12. Những giới hạn của placeholder

Placeholder rất hữu ích, nhưng có giới hạn.

### Không thể thay đổi cấu trúc query theo tham số

Một placeholder không tự thêm hoặc xóa clause. Nếu cần chọn một trong nhiều loại query, hãy tạo cấu trúc bằng code.

### Không thay tên field an toàn

Tên field phải là phần cấu trúc do ứng dụng kiểm soát. Dùng allowlist để chọn field hợp lệ nếu sort hoặc search field có thể thay đổi.

### Không xử lý mọi trường hợp null và collection rỗng thay bạn

Ứng dụng phải định nghĩa semantics của các giá trị này trước khi gọi repository.

### Không biến query_string thành an toàn về semantics

Binding chuỗi giúp tách giá trị khỏi cấu trúc JSON, nhưng query_string có cú pháp truy vấn riêng. Cần dùng query phù hợp hoặc escape cú pháp đó theo quy tắc Elasticsearch.

### Không thay thế validation

Dữ liệu vẫn cần kiểm tra:

- Số có nằm trong miền cho phép không?
- Khoảng min/max có hợp lệ không?
- Collection có vượt giới hạn kích thước không?
- String có quá dài không?
- Enum có thuộc tập giá trị được hỗ trợ không?
- Ngày giờ có đúng định dạng và múi giờ không?
- Wildcard có quá rộng không?

Giới hạn đầu vào giúp query ổn định và bảo vệ tài nguyên cluster.

## 13. Khi nào dùng @Query và khi nào dùng Operations?

Dùng **@Query** khi:

- Cấu trúc Query DSL cố định.
- Chỉ một số giá trị scalar hoặc collection thay đổi.
- Query đủ ngắn để đọc và kiểm tra ngay trong repository.
- Kiểu kết quả đơn giản.
- Không cần thêm hoặc bỏ nhiều clause theo input runtime.

Dùng **ElasticsearchOperations** với CriteriaQuery hoặc NativeQuery khi:

- Có nhiều filter tùy chọn.
- Cấu trúc bool thay đổi theo input.
- Cần chọn field, query type hoặc nested path theo quy tắc ứng dụng.
- Cần aggregation, highlight, sort phức tạp hoặc metadata.
- Cần chọn index/alias tại thời điểm gọi.
- Cần xử lý null, collection rỗng hoặc nhiều kiểu dữ liệu theo một chính sách thống nhất.

Ví dụ Operations với NativeQuery có thể thêm filter theo điều kiện:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> {
        b.filter(f -> f.term(t -> t
            .field("status")
            .value("ACTIVE")
        ));

        if (minPrice != null) {
            b.filter(f -> f.range(r -> r
                .number(n -> n
                    .field("price")
                    .gte(minPrice)
                )
            ));
        }

        if (categories != null && !categories.isEmpty()) {
            b.filter(f -> f.terms(t -> t
                .field("category")
                .terms(v -> v.value(
                    categories.stream()
                        .map(FieldValue::of)
                        .toList()
                ))
            ));
        }

        return b;
    }))
    .build();

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

Đoạn code minh họa cách xây dựng query có điều kiện bằng builder của Elasticsearch Java API Client. Tên builder method và kiểu giá trị có thể khác theo phiên bản Spring Data Elasticsearch/client; điều chỉnh theo dependency thực tế. Ý tưởng chính là chỉ thêm clause khi điều kiện nghiệp vụ có mặt.

## 14. Kiểm tra query JSON được tạo và lỗi thường gặp

Khi một method @Query cho kết quả không đúng, kiểm tra theo thứ tự:

1. Placeholder có đúng chỉ số không?
2. Thứ tự tham số Java có khớp placeholder không?
3. String placeholder có nằm trong dấu nháy kép không?
4. Number và boolean có bị đặt trong dấu nháy không?
5. Collection có nằm ở vị trí JSON array không?
6. Field mapping có đúng kiểu với giá trị truyền vào không?
7. Query type có phù hợp với text/keyword/numeric/date không?
8. Null hoặc collection rỗng có semantics đúng với nghiệp vụ không?
9. Giá trị có chứa ký tự cần escaping không?
10. Query DSL có cú pháp riêng như query_string hoặc wildcard không?

### Một số lỗi tiêu biểu

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| JSON query không hợp lệ | Thiếu dấu nháy hoặc placeholder ở sai vị trí | Kiểm tra JSON và kiểu giá trị |
| Boolean không khớp | Truyền "true" thay vì true | Dùng Boolean placeholder không có dấu nháy |
| Range query lỗi hoặc không khớp | Truyền số dưới dạng string hoặc field mapping không numeric | Dùng number và kiểm tra mapping |
| Terms query không khớp | Collection rỗng, sai kiểu phần tử hoặc field không phải keyword phù hợp | Kiểm tra dữ liệu và mapping |
| Chuỗi có dấu nháy làm query lỗi | Tự nối chuỗi JSON hoặc escaping sai | Dùng placeholder, không ghép JSON thủ công |
| Ký tự * hoặc ? tạo kết quả rộng | Nhầm dữ liệu với cú pháp wildcard | Dùng query type rõ ràng và kiểm soát pattern |
| Query string thay đổi ý nghĩa | Ký tự input được diễn giải theo cú pháp query_string | Dùng match hoặc escape query syntax |
| Null không trả document thiếu field | Nhầm null với missing | Dùng exists/must_not hoặc bỏ filter theo yêu cầu |
| Filter false bị bỏ qua | Code kiểm tra boolean bằng điều kiện truthy | Kiểm tra value khác null |
| Ngày bị lệch khoảng | Múi giờ hoặc format không thống nhất | Chuẩn hóa ISO 8601 và định nghĩa boundary |

### Kiểm tra bằng dữ liệu cụ thể

Với mỗi query, hãy thử một tập dữ liệu nhỏ có các trường hợp:

- Chuỗi bình thường và chuỗi có dấu cách.
- Chuỗi chứa dấu nháy, backslash và Unicode.
- Số nguyên, số thập phân và giá trị ở biên.
- Boolean true và false.
- Collection có một phần tử, nhiều phần tử và rỗng.
- Ngày giờ ở hai múi giờ hoặc tại ranh giới ngày.
- Field missing, null và chuỗi rỗng.

Có thể chạy JSON tương đương trực tiếp trong Elasticsearch Dev Tools để tách lỗi Query DSL khỏi lỗi binding của repository. Trong ứng dụng, bật logging request phù hợp ở môi trường phát triển để quan sát query được gửi đi. Không log dữ liệu nhạy cảm hoặc toàn bộ tham số người dùng trong production.

## 15. Ví dụ hoàn chỉnh với ProductRepository

Entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Boolean)
    private Boolean available;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Date)
    private Instant createdAt;
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "bool": {
            "filter": [
              { "term": { "status": "?0" } },
              { "term": { "available": ?1 } },
              { "range": { "price": { "gte": ?2, "lt": ?3 } } },
              { "terms": { "category": ?4 } }
            ]
          }
        }
        """)
    List<Product> findForCatalog(
        String status,
        Boolean available,
        Double minPrice,
        Double maxPrice,
        Collection<String> categories
    );

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
    List<Product> searchName(String phrase);

    @Query("""
        {
          "range": {
            "createdAt": {
              "gte": "?0",
              "lt": "?1"
            }
          }
        }
        """)
    List<Product> findCreatedInPeriod(
        String fromIsoDate,
        String toIsoDate
    );
}
~~~

Service chuẩn hóa và xác thực tham số trước khi gọi repository:

~~~java
public List<Product> findCatalog(
        String status,
        Boolean available,
        Double minPrice,
        Double maxPrice,
        Collection<String> categories) {

    if (minPrice != null && maxPrice != null
            && minPrice > maxPrice) {
        throw new IllegalArgumentException(
            "minPrice must not exceed maxPrice"
        );
    }

    if (categories == null || categories.isEmpty()) {
        // Chọn nhánh query khác theo chính sách nghiệp vụ.
        // Không gọi terms query với collection rỗng một cách mặc định.
        return List.of();
    }

    return repository.findForCatalog(
        status,
        available,
        minPrice,
        maxPrice,
        categories
    );
}
~~~

Method trên minh họa validation, không phải chính sách duy nhất. Nếu categories rỗng có nghĩa không lọc category, service nên gọi một query khác không có terms clause. Nếu rỗng có nghĩa không có category nào được phép, trả danh sách rỗng có thể là hành vi phù hợp.

Đối với filter nullable, cần tạo các method/query phù hợp hoặc chuyển sang Operations để chỉ thêm clause cần thiết. Đừng truyền null vào các placeholder range/term mà không xác định rõ query JSON cuối cùng và semantics mong muốn.

## 16. Nguyên tắc cần nhớ

- Dùng placeholder **?0**, **?1** theo chỉ số tham số bắt đầu từ 0.
- Đặt placeholder String trong dấu nháy kép.
- Đặt placeholder number và boolean không có dấu nháy.
- Đặt placeholder collection tại vị trí JSON array, ví dụ giá trị của **terms**.
- Dùng field mapping phù hợp với kiểu dữ liệu và query type.
- Không nối chuỗi đầu vào vào JSON bằng phép cộng chuỗi.
- Không dùng placeholder để thay tên field hoặc cấu trúc Query DSL.
- Phân biệt null, missing và empty string.
- Xác định rõ ý nghĩa của collection rỗng.
- Chuẩn hóa ngày giờ và múi giờ trước khi query.
- Phân biệt JSON escaping với cú pháp riêng của query_string hoặc wildcard.
- Dùng @Query cho cấu trúc cố định; dùng Operations khi cần thêm/bỏ clause theo runtime.
- Kiểm tra query được tạo với dữ liệu biên và mapping thật.

Truyền tham số đúng kiểu giúp query JSON giữ được cấu trúc hợp lệ và tránh nhầm giữa dữ liệu với cú pháp Query DSL. Khi chỉ giá trị thay đổi, placeholder trong @Query là cách khai báo gọn và dễ bảo trì. Khi chính cấu trúc query cũng thay đổi theo input, hãy xây dựng query bằng Operations để kiểm soát rõ từng điều kiện và cách xử lý giá trị đặc biệt.

