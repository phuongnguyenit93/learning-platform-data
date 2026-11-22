# Kết hợp and, or, not và biểu thức nhóm

CriteriaQuery của Spring Data Elasticsearch cho phép ghép nhiều điều kiện tìm kiếm bằng **and**, **or**, **not** và các nhóm điều kiện lồng nhau. Đây là cách xây dựng truy vấn theo từng bước bằng Java khi ứng dụng cần biểu diễn bộ lọc động, chẳng hạn tìm sản phẩm đang bán thuộc một số danh mục, có giá trong khoảng cho phép và không nằm trong danh sách bị ẩn.

Điểm quan trọng nhất khi kết hợp điều kiện là phải giữ đúng ý nghĩa logic. Một chuỗi and hoặc or đơn giản thường dễ hiểu, nhưng khi biểu thức có cả hai toán tử, ứng dụng cần xác định rõ nhóm nào phải được đánh giá cùng nhau. Spring Data Elasticsearch cung cấp **subCriteria(...)** để tạo nhóm con. Nếu biểu thức quá phức tạp hoặc cần kiểm soát chính xác Bool Query của Elasticsearch, có thể dùng **NativeQuery** hoặc **StringQuery**.

## 1. Từ biểu thức nghiệp vụ đến CriteriaQuery

Giả sử trang tìm kiếm sản phẩm có các điều kiện:

- Sản phẩm phải đang được xuất bản.
- Sản phẩm thuộc danh mục sách hoặc trò chơi.
- Giá thấp hơn 500.
- Sản phẩm không bị đánh dấu ngừng kinh doanh.

Biểu thức logic:

~~~text
status = "published"
AND (category = "books" OR category = "games")
AND price < 500
AND NOT discontinued
~~~

CriteriaQuery giúp biểu diễn từng điều kiện thành **Criteria**, sau đó kết hợp chúng thành một **Query**:

~~~java
Criteria criteria = new Criteria("status").is("published")
        .subCriteria(
                new Criteria().or("category").is("books")
                        .or("category").is("games")
        )
        .and("price").lessThan(500)
        .and("discontinued").not().is(true);

Query query = new CriteriaQuery(criteria);
~~~

Ví dụ minh họa cách nhóm điều kiện. Chữ ký method và cách diễn giải một số thao tác có thể thay đổi theo release train; hãy kiểm tra Javadoc của đúng phiên bản Spring Data Elasticsearch mà dự án sử dụng.

Trước khi viết Criteria, nên diễn đạt truy vấn thành biểu thức logic hoặc bảng điều kiện. Khi đó có thể xác định được điều kiện nào là bắt buộc, điều kiện nào là lựa chọn thay thế và nhóm nào cần được đặt trong ngoặc.

## 2. Ý nghĩa của AND

**and(...)** ghép điều kiện theo logic AND. Document chỉ thỏa mãn nhóm AND khi tất cả điều kiện thành phần đều đúng.

Ví dụ:

~~~java
Criteria criteria = new Criteria("status").is("published")
        .and("category").is("books")
        .and("price").lessThan(500);

Query query = new CriteriaQuery(criteria);
~~~

Biểu thức tương ứng:

~~~text
status = "published"
AND category = "books"
AND price < 500
~~~

Có thể dùng Criteria trên cùng field để kết hợp nhiều giới hạn. Ví dụ tìm sản phẩm có giá từ 100 đến dưới 500:

~~~java
Criteria priceCriteria = new Criteria("price")
        .greaterThanEqual(100)
        .lessThan(500);
~~~

Các điều kiện được thêm vào cùng một Criteria cũng được kết hợp theo AND. Cách viết này hữu ích với range query hoặc khi cùng một field cần nhiều ràng buộc.

### 2.1. AND trên nhiều field

Mỗi lần gọi and("fieldName") tạo Criteria tiếp theo trong chuỗi:

~~~java
Criteria criteria = Criteria.where("country").is("VN")
        .and("active").is(true)
        .and("age").greaterThanEqual(18);
~~~

Kết quả chỉ gồm document có country là VN, active là true và age từ 18 trở lên.

### 2.2. AND trên các điều kiện cùng field

~~~java
Criteria criteria = Criteria.where("price")
        .greaterThan(100)
        .lessThanEqual(500);
~~~

Điều kiện yêu cầu giá lớn hơn 100 và nhỏ hơn hoặc bằng 500. Cách kết hợp này tương đương một khoảng giá có hai đầu mút khác nhau.

## 3. Ý nghĩa của OR

**or(...)** ghép điều kiện theo logic OR. Document chỉ cần thỏa mãn ít nhất một nhánh trong nhóm OR.

Ví dụ:

~~~java
Criteria criteria = new Criteria().or("category").is("books")
        .or("category").is("games");

Query query = new CriteriaQuery(criteria);
~~~

Biểu thức:

~~~text
category = "books"
OR category = "games"
~~~

Có thể đọc truy vấn này như “sản phẩm thuộc danh mục sách hoặc trò chơi”. Khi chỉ có một điều kiện, OR không tạo thêm lợi ích; nó có ý nghĩa khi có từ hai nhánh trở lên.

### 3.1. OR giữa các field khác nhau

OR cũng có thể kết hợp các field khác nhau:

~~~java
Criteria criteria = new Criteria().or("sku").is("KB-100")
        .or("barcode").is("893000000001");
~~~

Biểu thức:

~~~text
sku = "KB-100"
OR barcode = "893000000001"
~~~

Đây là trường hợp người dùng có thể nhập một mã và hệ thống tìm mã đó trong nhiều trường định danh.

### 3.2. OR không phải là match query

OR trong Criteria kết hợp nhiều điều kiện truy vấn. Nó không đồng nghĩa với việc analyzer tìm các từ theo toán tử OR trong một field text.

Ví dụ:

~~~java
Criteria criteria = new Criteria().or("category").is("books")
        .or("category").is("games");
~~~

đang tạo hai nhánh điều kiện trên field category. Nếu cần tìm văn bản có một trong nhiều từ, hãy chọn match query và cấu hình toán tử match phù hợp. Cần phân biệt logic giữa các Criteria với logic phân tích nội dung của một field text.

## 4. Ý nghĩa của NOT

NOT phủ định một điều kiện. Trong Criteria API, **not()** đặt cờ negating cho Criteria. Có thể dùng nó trước phép so sánh cần phủ định:

~~~java
Criteria criteria = Criteria.where("status")
        .not()
        .is("deleted");
~~~

Ý nghĩa là document không thỏa điều kiện status = deleted.

Khi muốn loại một tập giá trị, có thể dùng **notIn(...)**:

~~~java
Criteria criteria = Criteria.where("status")
        .notIn("deleted", "archived");
~~~

Hai cách trên diễn đạt phủ định ở mức điều kiện field. Với tập giá trị, notIn thường dễ đọc hơn.

### 4.1. NOT và field không tồn tại

Trong Elasticsearch, một điều kiện phủ định thường được biểu diễn bằng must_not. Document không có field cũng có thể không khớp điều kiện bị phủ định, do đó vẫn xuất hiện trong kết quả.

Ví dụ, điều kiện loại status deleted có thể vẫn trả về document không có status. Nếu nghiệp vụ yêu cầu status phải tồn tại và không phải deleted, hãy kết hợp điều kiện exists:

~~~java
Criteria criteria = Criteria.where("status").exists()
        .not()
        .is("deleted");
~~~

Vì cách kết hợp negation và entries trong Criteria có thể khó đọc, với điều kiện exists cộng phủ định, hãy xác nhận query DSL được sinh ra trong phiên bản đang dùng. Khi cần kiểm soát rõ ràng, dùng Bool Query có filter chứa exists và must_not chứa điều kiện bị loại.

### 4.2. NOT một tập giá trị

Ví dụ Elasticsearch Query DSL:

~~~json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "terms": {
            "status": ["deleted", "archived"]
          }
        }
      ]
    }
  }
}
~~~

Truy vấn này loại document có status khớp deleted hoặc archived. Nếu cần loại cả document thiếu status, thêm exists vào filter.

### 4.3. NOT một nhóm biểu thức

Phủ định một nhóm phức tạp cần xác định chính xác phạm vi bị phủ định. Ví dụ:

~~~text
NOT (category = "books" OR category = "games")
~~~

Theo quy tắc De Morgan, biểu thức tương đương:

~~~text
category != "books"
AND category != "games"
~~~

Khi phủ định cả nhóm OR, không nên chỉ thêm not() vào một field riêng lẻ. Dùng must_not bọc nhóm bool hoặc cấu trúc Criteria lồng nhau phù hợp. Điều này giúp tránh phủ định nhầm một nhánh thay vì toàn bộ biểu thức.

## 5. Vì sao cần nhóm điều kiện?

AND và OR có thể được ghép thành biểu thức phức tạp. Khi đó, thứ tự nhóm rất quan trọng.

Ví dụ:

~~~text
status = "published"
AND (category = "books" OR category = "games")
~~~

Nếu bỏ nhóm ngoặc và kết hợp sai, truy vấn có thể bị hiểu thành:

~~~text
(status = "published" AND category = "books")
OR category = "games"
~~~

Hai biểu thức này khác nhau. Ở biểu thức thứ nhất, mọi document đều phải published. Ở biểu thức thứ hai, mọi document thuộc games đều có thể xuất hiện dù status không phải published.

Không nên dựa vào thứ tự gọi method để giả định Criteria tự áp dụng precedence giống ngôn ngữ Java hoặc SQL. Hãy dùng **subCriteria(...)** để thể hiện nhóm con một cách tường minh.

## 6. Dùng subCriteria để tạo biểu thức nhóm

subCriteria(...) thêm một Criteria con vào Criteria cha. Theo tài liệu Spring Data Elasticsearch, subCriteria được kết hợp với Criteria cha theo AND. Bên trong Criteria con có thể tạo một chuỗi AND hoặc OR riêng.

Ví dụ cần tìm người có họ Miller và tên là John hoặc Jack:

~~~java
Criteria criteria = new Criteria("lastName").is("Miller")
        .subCriteria(
                new Criteria().or("firstName").is("John")
                        .or("firstName").is("Jack")
        );

Query query = new CriteriaQuery(criteria);
~~~

Biểu thức:

~~~text
lastName = "Miller"
AND (
    firstName = "John"
    OR firstName = "Jack"
)
~~~

Đây là mẫu thường dùng cho điều kiện bắt buộc đi cùng một nhóm lựa chọn.

### 6.1. Nhiều nhóm con AND với nhau

Có thể đặt nhiều subCriteria dưới một Criteria cha. Các nhóm con được kết hợp theo AND:

~~~java
Criteria criteria = new Criteria()
        .subCriteria(
                new Criteria().or("status").is("published")
                        .or("status").is("featured")
        )
        .subCriteria(
                new Criteria().or("category").is("books")
                        .or("category").is("games")
        );
~~~

Biểu thức:

~~~text
(status = "published" OR status = "featured")
AND
(category = "books" OR category = "games")
~~~

Mỗi nhóm con tự quyết định các điều kiện bên trong được ghép bằng OR. Criteria cha kết hợp hai nhóm theo AND.

### 6.2. Nhóm OR gồm các nhóm AND

Với biểu thức:

~~~text
(status = "published" AND price < 100)
OR
(featured = true AND category = "books")
~~~

Có thể tạo một Criteria OR không gắn field rồi thêm từng nhóm AND làm subCriteria:

~~~java
Criteria criteria = Criteria.or()
        .subCriteria(
                new Criteria("status").is("published")
                        .and("price").lessThan(100)
        )
        .subCriteria(
                new Criteria("featured").is(true)
                        .and("category").is("books")
        );

Query query = new CriteriaQuery(criteria);
~~~

Criteria.or() là factory method tạo Criteria có toán tử OR và không gắn với field cụ thể. Các nhóm con giữ logic AND của riêng chúng. Factory method Criteria.and() có thể được dùng tương tự khi cần một nhóm cha kết hợp các nhóm con bằng AND.

Các factory method Criteria.and(), Criteria.or() và subCriteria(...) được bổ sung từ Spring Data Elasticsearch 4.1. Nếu dự án dùng phiên bản cũ hơn, cần kiểm tra API có sẵn và chọn cách biểu diễn tương thích.

## 7. Chuyển biểu thức nhóm thành Bool Query

CriteriaQuery được chuyển thành truy vấn Elasticsearch. Về mặt khái niệm:

- AND được biểu diễn bằng bool must.
- OR được biểu diễn bằng bool should.
- NOT được biểu diễn bằng bool must_not.

Ví dụ nhóm họ Miller và tên John hoặc Jack:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "term": {
            "lastName": "Miller"
          }
        },
        {
          "bool": {
            "should": [
              {
                "term": {
                  "firstName": "John"
                }
              },
              {
                "term": {
                  "firstName": "Jack"
                }
              }
            ],
            "minimum_should_match": 1
          }
        }
      ]
    }
  }
}
~~~

Bool Query cho phép lồng bool query vào nhau, nhờ đó biểu diễn được nhóm ngoặc nhiều cấp.

### 7.1. must và filter

Elasticsearch có cả must và filter để kết hợp điều kiện AND:

| Clause | Ý nghĩa | Tính điểm relevance |
|---|---|---|
| must | Điều kiện phải khớp | Có tham gia tính score |
| filter | Điều kiện phải khớp | Không tính score, phù hợp điều kiện lọc |
| should | Điều kiện lựa chọn thay thế hoặc tăng mức phù hợp | Có thể ảnh hưởng score |
| must_not | Điều kiện không được khớp | Không tính score |

CriteriaQuery có thể đặt điều kiện vào query context hoặc filter context tùy loại Criteria và cách Spring Data xây dựng truy vấn. Không nên giả định mọi điều kiện AND đều luôn trở thành filter. Nếu cần kiểm soát scoring hoặc filter context chính xác, dùng NativeQuery với Bool Query tường minh.

### 7.2. minimum_should_match

Trong Elasticsearch, should có thể mang ý nghĩa lựa chọn. Giá trị mặc định của minimum_should_match phụ thuộc cấu trúc bool:

- Nếu bool chỉ có should, mặc định cần khớp ít nhất một nhánh.
- Nếu bool có must hoặc filter, mặc định các nhánh should có thể chỉ đóng vai trò tăng score và không bắt buộc khớp.

Vì vậy, khi viết Bool Query thủ công và muốn một nhóm OR thật sự bắt buộc khớp ít nhất một nhánh, hãy đặt:

~~~json
{
  "minimum_should_match": 1
}
~~~

Khi dùng CriteriaQuery, kiểm tra DSL thực tế nếu biểu thức OR nằm trong nhóm có điều kiện must/filter. Với logic quan trọng, đừng để mặc định của bool query quyết định kết quả ngoài ý muốn.

## 8. Ví dụ CriteriaQuery đầy đủ cho tìm kiếm sản phẩm

Giả sử ứng dụng cần lọc:

1. Sản phẩm phải có trạng thái published.
2. Thuộc category books hoặc games.
3. Giá từ 100 đến dưới 500.
4. Không bị đánh dấu discontinued.

Entity rút gọn:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Boolean)
    private Boolean discontinued;
}
~~~

Criteria:

~~~java
Criteria categoryGroup = new Criteria()
        .or("category").is("books")
        .or("category").is("games");

Criteria criteria = new Criteria("status").is("published")
        .subCriteria(categoryGroup)
        .and("price").greaterThanEqual(100)
        .and("price").lessThan(500)
        .and("discontinued").not().is(true);

Query query = new CriteriaQuery(criteria);
~~~

Thực hiện tìm kiếm:

~~~java
SearchHits<Product> hits = operations.search(query, Product.class);

for (SearchHit<Product> hit : hits) {
    Product product = hit.getContent();
    System.out.println(product.getName());
}
~~~

Phần categoryGroup tạo một nhóm OR, sau đó subCriteria kết hợp nhóm này với điều kiện status. Hai giới hạn giá được thêm vào Criteria chính. Điều kiện discontinued bị phủ định.

Khi dùng ví dụ thực tế, cần bảo đảm field category, status có mapping phù hợp để so khớp chính xác. Nếu field là text, các thao tác term-level có thể không có ý nghĩa như mong đợi. Cũng cần xác định cách xử lý document thiếu discontinued: nếu field không tồn tại, điều kiện phủ định có thể vẫn cho document xuất hiện.

## 9. Dùng NativeQuery khi biểu thức quá phức tạp

CriteriaQuery phù hợp với các điều kiện field và nhóm logic thường gặp. Khi truy vấn cần nhiều nhánh bool sâu, minimum_should_match, nested query, script, function score, aggregation hoặc cú pháp đặc thù của Elasticsearch, NativeQuery thường rõ ràng hơn.

Ví dụ DSL cho biểu thức:

~~~text
status = "published"
AND (
    (category = "books" AND price < 100)
    OR
    (featured = true AND category = "games")
)
AND NOT discontinued
~~~

Bool Query:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "term": {
            "status": "published"
          }
        },
        {
          "bool": {
            "should": [
              {
                "bool": {
                  "must": [
                    {
                      "term": {
                        "category": "books"
                      }
                    },
                    {
                      "range": {
                        "price": {
                          "lt": 100
                        }
                      }
                    }
                  ]
                }
              },
              {
                "bool": {
                  "must": [
                    {
                      "term": {
                        "featured": true
                      }
                    },
                    {
                      "term": {
                        "category": "games"
                      }
                    }
                  ]
                }
              }
            ],
            "minimum_should_match": 1
          }
        }
      ],
      "must_not": [
        {
          "term": {
            "discontinued": true
          }
        }
      ]
    }
  }
}
~~~

NativeQuery sử dụng các kiểu query của Elasticsearch Java Client và cho phép đặt cấu trúc bool rõ ràng. API builder của NativeQuery có thể thay đổi theo phiên bản client, nhưng cấu trúc DSL ở trên thể hiện ý nghĩa logic cần đạt được.

Nếu đã có query JSON, StringQuery cũng là một lựa chọn. Dù dùng CriteriaQuery, NativeQuery hay StringQuery, hãy kiểm tra request thực tế và bảo đảm các field khớp với mapping.

## 10. Kết hợp Criteria với điều kiện động

Trang tìm kiếm thường có các filter tùy chọn. Người dùng có thể nhập category, status, khoảng giá hoặc trạng thái nổi bật. Không nên thêm một điều kiện rỗng hoặc giá trị null vào query khi người dùng không chọn filter đó.

Ví dụ xây dựng Criteria theo input:

~~~java
public Query buildProductQuery(
        String status,
        List<String> categories,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        Boolean featured) {

    Criteria criteria = new Criteria();

    if (status != null && !status.isBlank()) {
        criteria.and("status").is(status);
    }

    if (categories != null && !categories.isEmpty()) {
        criteria.subCriteria(
                new Criteria().or("category").in(categories)
        );
    }

    if (minPrice != null) {
        criteria.and("price").greaterThanEqual(minPrice);
    }

    if (maxPrice != null) {
        criteria.and("price").lessThanEqual(maxPrice);
    }

    if (featured != null) {
        criteria.and("featured").is(featured);
    }

    return new CriteriaQuery(criteria);
}
~~~

Đây là mẫu minh họa cách thêm điều kiện theo input. Cần kiểm tra cách Criteria không gắn field xử lý chuỗi con trong phiên bản dự án; với nhiều nhóm động, có thể xây dựng từng Criteria riêng rồi kết hợp bằng and(...), or(...) hoặc subCriteria(...).

Một số quy tắc nên áp dụng:

- Không thêm điều kiện khi input chưa được cung cấp.
- Quyết định rõ collection rỗng có nghĩa bỏ filter hay trả kết quả rỗng.
- Giữ nhóm OR riêng, tránh nối trực tiếp vào Criteria cha nếu làm thay đổi phạm vi điều kiện.
- Xác thực giá trị đầu vào và kiểu dữ liệu trước khi tạo Criteria.
- Giới hạn số nhánh OR nếu input đến từ người dùng.

## 11. Lỗi thường gặp khi kết hợp AND, OR và NOT

### 11.1. Không nhóm OR trước khi kết hợp AND

Biểu thức mong muốn A AND (B OR C) nhưng code lại tạo một chuỗi nối không có subCriteria. Hãy tạo Criteria con chứa B OR C rồi gắn vào A bằng subCriteria(...).

### 11.2. Cho rằng Criteria tự hiểu precedence giống SQL

Không nên dựa vào thứ tự method để ngầm hiểu AND luôn có ưu tiên hơn OR. Hãy biểu diễn ngoặc bằng subCriteria để cấu trúc truy vấn rõ ràng.

### 11.3. Đặt NOT sai phạm vi

not() trên một Criteria phủ định điều kiện của Criteria đó. Nó không tự động phủ định toàn bộ biểu thức cha. Nếu cần NOT (A OR B), hãy dùng một nhóm bool bị phủ định hoặc NativeQuery có must_not chứa nested bool.

### 11.4. Quên document thiếu field

Điều kiện phủ định có thể vẫn trả về document không có field. Nếu nghiệp vụ yêu cầu field phải tồn tại, thêm exists vào filter.

### 11.5. Dùng OR nhưng không kiểm soát minimum_should_match

Khi tự xây dựng Bool Query có cả must/filter và should, hãy xác định rõ có cần ít nhất một nhánh should khớp hay không. Nếu có, đặt minimum_should_match tương ứng.

### 11.6. Dùng sai mapping

Điều kiện is hoặc in trên field text có thể không so khớp toàn chuỗi vì analyzer đã tách token. Dùng keyword cho giá trị cần so khớp chính xác và text cho tìm kiếm toàn văn.

### 11.7. Cố biểu diễn query quá phức tạp bằng Criteria

Nếu Criteria lồng nhiều cấp khiến code khó đọc hoặc khó kiểm chứng, chuyển sang NativeQuery. Mục tiêu là làm cho cấu trúc logic dễ kiểm tra, không phải buộc mọi truy vấn phải dùng một API.

## 12. Cách kiểm tra biểu thức được sinh ra

Khi kết quả không đúng, cần kiểm tra cả Criteria ban đầu lẫn query DSL mà Spring Data gửi đến Elasticsearch.

Các bước:

1. Viết biểu thức logic với ngoặc trước khi viết Java.
2. Tạo Criteria cho từng nhóm điều kiện riêng.
3. Dùng subCriteria(...) để thể hiện nhóm con.
4. Tạo CriteriaQuery từ Criteria gốc.
5. Bật logging request phù hợp với Elasticsearch Java Client và Spring Data Elasticsearch của dự án, hoặc quan sát request trong môi trường test.
6. Đối chiếu must, should, must_not, filter và minimum_should_match.
7. Chạy truy vấn trên một tập document nhỏ có kết quả dự kiến rõ ràng.

Một bộ dữ liệu kiểm thử nên có document thỏa tất cả điều kiện, document chỉ thỏa nhánh OR thứ nhất, document chỉ thỏa nhánh thứ hai, document sai điều kiện AND, document bị loại bởi NOT và document thiếu field.

Ví dụ bảng kiểm thử cho biểu thức status=published AND (category=books OR category=games) AND NOT discontinued:

| Document | Status | Category | Discontinued | Kết quả mong đợi |
|---|---|---|---|---|
| A | published | books | false | Được chọn |
| B | published | games | false | Được chọn |
| C | draft | books | false | Bị loại do status |
| D | published | toys | false | Bị loại do category |
| E | published | books | true | Bị loại do NOT |
| F | published | games | thiếu | Cần xác định quy tắc cho field thiếu |

Kiểm thử những trường hợp biên này giúp phát hiện lỗi nhóm điều kiện sớm hơn so với chỉ thử một truy vấn có kết quả đúng.

## 13. Lựa chọn giữa CriteriaQuery, NativeQuery và StringQuery

| Cách xây dựng | Phù hợp khi | Điểm cần cân nhắc |
|---|---|---|
| CriteriaQuery | Điều kiện field thông thường, AND/OR và nhóm con vừa phải | Cần hiểu cách chain và subCriteria được chuyển thành bool query |
| NativeQuery | Cần kiểm soát DSL, bool lồng sâu, scoring, nested query hoặc aggregation | Gắn chặt hơn với Elasticsearch Java Client |
| StringQuery | Đã có query JSON và muốn gửi trực tiếp | JSON dạng chuỗi khó refactor và ít an toàn kiểu hơn |
| Repository query method | CRUD và điều kiện đơn giản, ổn định | Không thuận tiện cho nhóm logic động phức tạp |

Không có yêu cầu phải dùng CriteriaQuery cho mọi truy vấn. Hãy chọn abstraction giúp biểu thức dễ đọc, dễ kiểm thử và dễ đối chiếu với DSL thực tế.

## 14. Lưu ý tương thích phiên bản

Criteria API đã được mở rộng qua các phiên bản Spring Data Elasticsearch. Một số điểm cần xác nhận:

- subCriteria(...) và factory method Criteria.and() / Criteria.or() có từ Spring Data Elasticsearch 4.1.
- Các method and, or, not, in, notIn và các overload có thể thay đổi theo release train.
- Cách chuyển Criteria thành query DSL phụ thuộc phiên bản Spring Data và Elasticsearch client.
- NativeQuery sử dụng API của Elasticsearch Java Client, vì vậy builder và kiểu tham số cần khớp dependency thực tế.
- Không nên trộn ví dụ từ tài liệu 4.x, 5.x và 6.x mà chưa xác nhận chữ ký method.

Tài liệu tham khảo chính thức:

- Spring Data Elasticsearch — Elasticsearch Operations và CriteriaQuery: https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html
- Spring Data Elasticsearch — API Criteria: https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/Criteria.html
- Elasticsearch — Boolean query: https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-bool-query.html

## 15. Kết luận

Trong CriteriaQuery, and kết hợp các điều kiện bắt buộc, or tạo các lựa chọn thay thế và not phủ định điều kiện. subCriteria(...) giúp tạo nhóm con để biểu diễn ngoặc logic, nhờ đó có thể xây dựng các biểu thức như A AND (B OR C) hoặc (A AND B) OR (C AND D).

Elasticsearch chuyển các phép kết hợp này thành Bool Query với must, should và must_not. Khi tự xây dựng DSL, hãy chú ý minimum_should_match, filter context và cách xử lý document thiếu field. Với biểu thức phức tạp, NativeQuery cho phép kiểm soát cấu trúc rõ ràng hơn.

Hãy viết biểu thức logic trước, nhóm Criteria theo đúng ngoặc, kiểm tra query DSL được sinh ra và thử với dữ liệu đại diện. Làm rõ phạm vi của từng điều kiện giúp truy vấn dễ hiểu và tránh những lỗi kết hợp AND, OR, NOT khó phát hiện.
