# Điều kiện `Is`, `Not`, `And` và `Or`

Spring Data Elasticsearch cho phép định nghĩa truy vấn ngay trong tên phương thức repository. Cơ chế này thường được gọi là query derivation: Spring Data phân tích tên phương thức, nhận diện thuộc tính và các từ khóa như `Is`, `Not`, `And`, `Or`, rồi tạo truy vấn Elasticsearch tương ứng.

Các từ khóa này giúp viết những điều kiện phổ biến mà không cần tự xây dựng JSON Query DSL. Để dùng đúng, cần hiểu `Is` biểu thị điều kiện bằng, `Not` phủ định một điều kiện, `And` yêu cầu tất cả điều kiện liên quan cùng đúng, còn `Or` cho phép một trong các nhánh đúng. Với truy vấn có nhiều điều kiện, cách Spring Data nhóm `And` và `Or` ảnh hưởng trực tiếp tới kết quả.

## 1. Cấu trúc tên phương thức repository

Một phương thức truy vấn dẫn xuất thường có dạng:

```text
findBy<Property><Operator>
```

Hoặc kết hợp nhiều thuộc tính:

```text
findBy<PropertyA><Operator>And<PropertyB><Operator>
```

Ví dụ repository:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Optional<ProductDocument> findBySkuIs(String sku);

    List<ProductDocument> findByStatusNot(String status);

    List<ProductDocument> findByStatusIsAndCategoryIdIs(
            String status,
            String categoryId);

    List<ProductDocument> findByStatusIsOrCategoryIdIs(
            String status,
            String categoryId);
}
```

Spring Data phân tích phần đứng sau `By` dựa trên tên thuộc tính Java của document. Ví dụ `CategoryId` thường ánh xạ tới property `categoryId`; `Status` ánh xạ tới `status`. Tên property phải khớp với mô hình document, không phải tùy ý lấy tên field JSON nếu chúng khác tên thuộc tính Java.

Ví dụ document:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Keyword)
    private String categoryId;

    @Field(type = FieldType.Boolean)
    private Boolean available;

    // Constructors, getters and setters
}
```

Trong các ví dụ dưới đây, `status`, `sku` và `categoryId` là `keyword` để điều kiện bằng/khác có ngữ nghĩa so khớp giá trị chính xác.

## 2. Điều kiện `Is`

`Is` biểu thị điều kiện bằng với giá trị được truyền vào. Đây là cách viết tường minh của một điều kiện equality trong tên phương thức.

```java
Optional<ProductDocument> findBySkuIs(String sku);

List<ProductDocument> findByStatusIs(String status);
```

Gọi repository:

```java
Optional<ProductDocument> product =
    productRepository.findBySkuIs("COFFEE-001");

List<ProductDocument> published =
    productRepository.findByStatusIs("PUBLISHED");
```

Điều kiện `findByStatusIs("PUBLISHED")` tìm các document có `status` bằng `PUBLISHED`. Trong Elasticsearch, điều kiện bằng trên field `keyword` thường được thực hiện bằng truy vấn chính xác như `term`.

### `Is` có thể được lược bỏ

Với điều kiện bằng đơn giản, Spring Data thường cho phép viết:

```java
List<ProductDocument> findByStatus(String status);
```

Phương thức này có cùng ý nghĩa equality với `findByStatusIs(status)`. Dùng `Is` giúp tên phương thức thể hiện rõ điều kiện hơn khi kết hợp với các toán tử khác.

### `Is` và kiểu mapping

Tên phương thức không thay thế mapping. Nếu cần so khớp chính xác một mã hoặc trạng thái, nên dùng `keyword`. Với `text`, nội dung được analyzer tách thành token; truy vấn equality không nhất thiết có nghĩa là so sánh toàn bộ chuỗi gốc như trong SQL.

Ví dụ, nếu `name` là `text`, tên sản phẩm `"Máy pha cà phê"` có thể được phân tích thành nhiều token. Không nên dùng `findByNameIs("Máy pha cà phê")` với kỳ vọng nó luôn là phép so sánh nguyên chuỗi. Nếu cần cả tìm toàn văn và so khớp/sort theo toàn bộ giá trị, khai báo multi-field có subfield `keyword` và truy vấn property tương ứng nếu mô hình Java đã biểu diễn subfield, hoặc dùng truy vấn tùy chỉnh.

## 3. Điều kiện `Not`

`Not` phủ định điều kiện của thuộc tính. Ví dụ:

```java
List<ProductDocument> findByStatusNot(String status);
```

Gọi:

```java
List<ProductDocument> notDeleted =
    productRepository.findByStatusNot("DELETED");
```

Ý nghĩa là lấy các document không khớp điều kiện `status = DELETED`. Về mặt Query DSL, phép phủ định thường được biểu diễn bằng `bool.must_not` bao quanh điều kiện tương ứng.

Ví dụ minh họa ý nghĩa truy vấn:

```json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "term": {
            "status": "DELETED"
          }
        }
      ]
    }
  }
}
```

Đây là cách diễn giải logic cho field `keyword`; JSON thực tế mà Spring Data phát ra có thể khác cấu trúc tùy phiên bản và loại query.

### `Not` không đồng nghĩa với `IsNull`

Elasticsearch không có ngữ nghĩa `NULL` giống hệt cơ sở dữ liệu quan hệ. Field bị thiếu hoặc có giá trị JSON `null` thường không được lập chỉ mục như một giá trị có thể so khớp. Vì vậy, một truy vấn `must_not` có thể trả về cả document không có field đó, bên cạnh document có giá trị khác với giá trị bị phủ định.

Ví dụ, `findByStatusNot("DELETED")` không nên mặc định được hiểu là “status tồn tại và khác DELETED”. Nếu nghiệp vụ yêu cầu field phải tồn tại, cần thêm điều kiện existence tương ứng. Một số phiên bản Spring Data hỗ trợ các từ khóa như `IsNotNull`/`IsNull`; hãy xác nhận query derivation của phiên bản đang dùng và kiểm tra truy vấn thực tế.

Mapping có thuộc tính `null_value` cũng có thể thay đổi cách Elasticsearch xử lý giá trị null khi lập chỉ mục. Hãy xét cấu hình mapping trước khi kết luận kết quả của điều kiện phủ định.

### Không truyền `null` để biểu thị phủ định

Không nên dùng `findByStatusNot(null)` với kỳ vọng nó luôn có nghĩa “status khác null”. Hành vi của tham số null và các từ khóa null phụ thuộc query derivation cùng mapping. Hãy dùng điều kiện kiểm tra tồn tại/không tồn tại được hỗ trợ tường minh, hoặc viết truy vấn tùy chỉnh khi ngữ nghĩa null là yêu cầu quan trọng.

## 4. Kết hợp điều kiện bằng `And`

`And` yêu cầu tất cả các điều kiện nối với nó đều thỏa mãn. Ví dụ:

```java
List<ProductDocument> findByStatusIsAndCategoryIdIs(
        String status,
        String categoryId);
```

Gọi:

```java
List<ProductDocument> products =
    productRepository.findByStatusIsAndCategoryIdIs(
        "PUBLISHED",
        "coffee"
    );
```

Kết quả chỉ gồm document có `status = PUBLISHED` và đồng thời `categoryId = coffee`.

Có thể thêm nhiều điều kiện:

```java
List<ProductDocument> findByStatusIsAndCategoryIdIsAndAvailableIsTrue(
        String status,
        String categoryId);
```

Phương thức trên yêu cầu cả ba điều kiện: trạng thái bằng giá trị truyền vào, danh mục bằng giá trị truyền vào và `available` là `true`.

Ở mức Query DSL, logic AND thường được biểu diễn bằng các điều kiện trong `bool.filter` hoặc `bool.must`. `filter` phù hợp với điều kiện lọc không cần tính điểm relevance; `must` là điều kiện bắt buộc có thể tham gia tính điểm tùy loại query. Cách Spring Data tạo query cụ thể do implementation của phiên bản quyết định.

## 5. Kết hợp điều kiện bằng `Or`

`Or` cho phép kết quả thỏa mãn ít nhất một nhánh điều kiện.

```java
List<ProductDocument> findByStatusIsOrCategoryIdIs(
        String status,
        String categoryId);
```

Gọi:

```java
List<ProductDocument> products =
    productRepository.findByStatusIsOrCategoryIdIs(
        "FEATURED",
        "coffee"
    );
```

Kết quả gồm document có `status = FEATURED`, hoặc có `categoryId = coffee`, hoặc đồng thời thỏa cả hai.

Trong Query DSL, OR thường được biểu diễn bằng `bool.should`. Khi không có điều kiện bắt buộc khác, ít nhất một nhánh `should` phải khớp. Nếu tự viết bool query có cả `must`/`filter` và `should`, cần chú ý `minimum_should_match`, vì mặc định của Elasticsearch có thể làm các nhánh `should` trở thành tùy chọn khi đã có `must` hoặc `filter`.

Ví dụ logic OR:

```json
{
  "query": {
    "bool": {
      "should": [
        { "term": { "status": "FEATURED" } },
        { "term": { "categoryId": "coffee" } }
      ],
      "minimum_should_match": 1
    }
  }
}
```

## 6. Kết hợp `And` và `Or` trong cùng tên phương thức

Khi tên phương thức có cả `And` và `Or`, việc nhóm điều kiện rất quan trọng. Spring Data phân tích các phần `Or` thành những nhánh; trong mỗi nhánh, các điều kiện `And` được kết hợp với nhau.

Ví dụ:

```java
List<ProductDocument> findByStatusIsAndCategoryIdIsOrAvailableIsTrue(
        String status,
        String categoryId);
```

Phương thức này được nhóm theo logic:

```text
(status = ?0 AND categoryId = ?1)
OR available = true
```

Nó trả về sản phẩm thuộc đúng trạng thái và danh mục, hoặc bất kỳ sản phẩm nào có `available = true`. Nếu mục tiêu nghiệp vụ khác với cách nhóm này, kết quả có thể rộng hơn dự kiến.

Ví dụ ngược lại:

```java
List<ProductDocument> findByStatusIsOrCategoryIdIsAndAvailableIsTrue(
        String status,
        String categoryId);
```

Được nhóm thành:

```text
status = ?0
OR (categoryId = ?1 AND available = true)
```

Hãy đọc tên phương thức theo từng nhóm `Or` thay vì chỉ đọc tuần tự như một câu văn. Khi logic có nhiều nhánh, tên phương thức dài và khó hiểu là dấu hiệu nên cân nhắc truy vấn tường minh.

### Muốn biểu diễn `(A OR B) AND C` thì sao?

Một tên phương thức đơn giản theo dạng PartTree không phải lúc nào cũng biểu đạt rõ mọi cách lồng ngoặc tùy ý. Ví dụ, nếu cần:

```text
(status = PUBLISHED OR status = FEATURED)
AND available = true
```

hãy cân nhắc một truy vấn tùy chỉnh để thể hiện nhóm OR bên trong nhóm AND, thay vì cố tạo một tên phương thức quá dài và dễ hiểu sai.

## 7. Ví dụ tổng hợp cho repository

Một repository có thể định nghĩa các phương thức theo từng mục đích:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    // Equality
    Optional<ProductDocument> findBySkuIs(String sku);

    // Negation
    List<ProductDocument> findByStatusNot(String status);

    // AND
    List<ProductDocument> findByStatusIsAndCategoryIdIs(
            String status,
            String categoryId);

    // OR
    List<ProductDocument> findByStatusIsOrCategoryIdIs(
            String status,
            String categoryId);

    // One AND group, then OR another condition
    List<ProductDocument> findByStatusIsAndCategoryIdIsOrAvailableIsTrue(
            String status,
            String categoryId);
}
```

Ví dụ gọi các phương thức:

```java
Optional<ProductDocument> bySku =
    productRepository.findBySkuIs("COFFEE-001");

List<ProductDocument> notArchived =
    productRepository.findByStatusNot("ARCHIVED");

List<ProductDocument> publishedCoffee =
    productRepository.findByStatusIsAndCategoryIdIs(
        "PUBLISHED",
        "coffee"
    );

List<ProductDocument> featuredOrCoffee =
    productRepository.findByStatusIsOrCategoryIdIs(
        "FEATURED",
        "coffee"
    );
```

## 8. Dùng `@Query` khi cần nhóm logic rõ ràng

Khi điều kiện có nhiều nhóm AND/OR, có nested query, range, boosting hoặc các yêu cầu Query DSL cụ thể, có thể định nghĩa truy vấn tường minh bằng `@Query`.

Ví dụ cần `(status = PUBLISHED OR status = FEATURED) AND available = true`:

```java
import org.springframework.data.elasticsearch.annotations.Query;

@Query("""
{
  "bool": {
    "filter": [
      { "term": { "available": true } },
      {
        "bool": {
          "should": [
            { "term": { "status": "?0" } },
            { "term": { "status": "?1" } }
          ],
          "minimum_should_match": 1
        }
      }
    ]
  }
}
""")
List<ProductDocument> findVisibleByStatuses(
        String firstStatus,
        String secondStatus);
```

Text block Java yêu cầu Java 15 trở lên. Nếu dự án dùng Java thấp hơn, viết chuỗi JSON theo cú pháp string phù hợp. Cú pháp placeholder `?0`, `?1` và cách bind tham số cần theo phiên bản Spring Data Elasticsearch; nếu phiên bản không hỗ trợ kiểu text block trong source thì chỉ thay cú pháp Java, không thay nội dung Query DSL.

`@Query` giúp nhìn thấy nhóm điều kiện trực tiếp, nhưng đổi lại phải tự quản lý tên field JSON, kiểu dữ liệu và cấu trúc query. Hãy kiểm tra JSON với mapping thực tế và kiểm thử truy vấn trước khi sử dụng.

## 9. Những lưu ý về kiểu dữ liệu và mapping

### Equality và `keyword`

Các điều kiện `Is` và `Not` thường được dùng cho trạng thái, mã, loại hoặc danh mục. Những field này nên có mapping `keyword` để so khớp chính xác.

```java
@Field(type = FieldType.Keyword)
private String status;

@Field(type = FieldType.Keyword)
private String categoryId;
```

Nếu field là `text`, analyzer có thể biến đổi chuỗi thành nhiều token. Một truy vấn bằng trên field đó có thể không mang nghĩa so sánh nguyên chuỗi như người dùng kỳ vọng.

### Boolean

Với field Boolean, có thể dùng từ khóa như `True` hoặc `False` trong tên phương thức:

```java
List<ProductDocument> findByAvailableIsTrue();

List<ProductDocument> findByAvailableIsFalse();
```

Đây là ví dụ mở rộng cho cách viết điều kiện đơn giản; hãy xác nhận tập keyword được hỗ trợ bởi phiên bản Spring Data Elasticsearch đang dùng.

### Field lồng nhau

Với property lồng, tên phương thức cần thể hiện đường dẫn property mà Spring Data có thể phân giải. Nếu mô hình có nhiều property tên giống nhau, hãy dùng cách phân tách đường dẫn được hỗ trợ hoặc truy vấn tường minh để tránh parser chọn sai thuộc tính.

### Null và field bị thiếu

Elasticsearch thường không lập chỉ mục giá trị null như một giá trị term thông thường. `Not` vì vậy có thể bao gồm document thiếu field. Nếu nghiệp vụ yêu cầu phân biệt “field không tồn tại”, “field có null” và “field có giá trị”, cần xem xét mapping `null_value`, query `exists` và cách dữ liệu được serialize.

## 10. Đọc và kiểm tra truy vấn được sinh ra

Tên phương thức chỉ cho biết ý định. Khi kết quả không như mong đợi, cần kiểm tra mapping và query thực tế.

Có thể kiểm tra mapping:

```http
GET /products/_mapping
```

Kiểm tra dữ liệu mẫu:

```http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "term": {
      "status": "PUBLISHED"
    }
  }
}
```

Trong môi trường phát triển, bật logging phù hợp cho package Spring Data Elasticsearch hoặc HTTP client để quan sát request được gửi đi. Tên logger và mức độ chi tiết có thể thay đổi theo phiên bản. Không bật log payload/headers chứa dữ liệu nhạy cảm trong production.

Nên tạo bộ document mẫu có các tổ hợp trạng thái, danh mục, Boolean và field thiếu để kiểm tra:

- `Is` chỉ trả về giá trị bằng mong muốn.
- `Not` có bao gồm document thiếu field hay không.
- `And` chỉ trả về document thỏa mọi điều kiện.
- `Or` trả về document thỏa ít nhất một nhánh.
- Tên phương thức có cả `And` và `Or` được nhóm đúng như logic nghiệp vụ.

## 11. Lỗi thường gặp

### Tên property không được phân giải

Tên sau `By` phải trỏ tới property của document class. Nếu dùng `findByCategory(...)` trong khi class chỉ có `categoryId`, Spring Data có thể báo lỗi tạo query lúc khởi động.

### Dùng `Is` trên field `text` để so sánh nguyên chuỗi

Field `text` được analyzer phân tích thành token. Dùng `keyword` hoặc subfield keyword cho equality chính xác; dùng full-text query cho tìm kiếm nội dung.

### `Not` trả về document thiếu field

Điều kiện phủ định trong Elasticsearch có thể khớp cả document không có giá trị được lập chỉ mục cho field. Nếu cần field tồn tại, kết hợp điều kiện exists/null phù hợp hoặc viết Query DSL tường minh.

### Kết hợp `And` và `Or` sai ý nghĩa

Một phương thức như `findByAAndBOrC` thường được nhóm thành `(A AND B) OR C`, không phải `A AND (B OR C)`. Viết lại tên phương thức theo nhóm hoặc dùng `@Query` để biểu diễn ngoặc rõ ràng.

### `Or` trong bool query tùy chỉnh không bắt buộc khớp

Nếu tự viết bool query có cả `filter`/`must` và `should`, kiểm tra `minimum_should_match`. Nếu thiếu, các nhánh `should` có thể chỉ đóng vai trò tăng điểm thay vì điều kiện bắt buộc.

### Dùng `null` như một giá trị thông thường

Field null hoặc bị thiếu không giống một term có giá trị. Không truyền null vào `Not` để thay cho kiểm tra tồn tại; dùng query phù hợp với ngữ nghĩa cần có.

## 12. Quy trình chọn toán tử

Khi tạo method repository, có thể quyết định theo trình tự:

1. Xác định property trong Java document và kiểu mapping của field.
2. Nếu cần giá trị bằng chính xác, dùng `Is` (hoặc dạng equality rút gọn) trên field phù hợp như `keyword`.
3. Nếu cần loại trừ giá trị, dùng `Not` và xác định rõ cách xử lý field thiếu/null.
4. Nếu mọi điều kiện phải đúng, nối các phần bằng `And`.
5. Nếu một trong các nhánh đúng là đủ, dùng `Or`.
6. Khi có cả `And` và `Or`, viết biểu thức logic có ngoặc trước rồi mới chuyển thành tên phương thức.
7. Nếu nhóm ngoặc không biểu đạt rõ bằng tên method, dùng `@Query` hoặc custom repository.
8. Kiểm tra mapping và kết quả bằng dữ liệu đại diện, đặc biệt với field `text`, null và field thiếu.

## 13. Kết luận

Trong query derivation của Spring Data Elasticsearch, `Is` biểu thị equality, `Not` phủ định một điều kiện, `And` kết hợp các điều kiện bắt buộc cùng đúng và `Or` tạo các nhánh mà chỉ cần một nhánh khớp. Các toán tử này được viết trong tên method repository và Spring Data chuyển thành truy vấn Elasticsearch.

Hãy dùng `keyword` cho điều kiện bằng/khác chính xác, hiểu rõ việc `Not` có thể khớp document thiếu field, và chú ý cách nhóm các nhánh khi trộn `And` với `Or`. Với logic có ngoặc phức tạp hoặc yêu cầu Query DSL cụ thể, `@Query` hay custom repository thường rõ ràng hơn một tên phương thức dài. Luôn đối chiếu với mapping và kiểm tra kết quả trên phiên bản Spring Data Elasticsearch thực tế của dự án.
