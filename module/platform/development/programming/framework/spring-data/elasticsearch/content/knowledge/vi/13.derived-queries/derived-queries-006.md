# True, False, Exists, IsNull và IsNotNull

Spring Data Elasticsearch hỗ trợ nhiều keyword để tạo query từ tên method của repository. Trong nhóm truy vấn theo tên, `True`, `False`, `Exists`, `IsNull` và `IsNotNull` giúp kiểm tra trạng thái boolean hoặc sự hiện diện của một field.

Các keyword này nhìn khá giống nhau nhưng mang ý nghĩa khác nhau:

- `True` và `False` kiểm tra giá trị boolean.
- `Exists` kiểm tra field có giá trị được lập chỉ mục hay không.
- `IsNull` tìm document mà field không có giá trị được lập chỉ mục.
- `IsNotNull` tìm document mà field có giá trị được lập chỉ mục.

Để sử dụng đúng, cần hiểu cách Spring Data phân tích tên method, cách Elasticsearch xử lý giá trị null và sự khác nhau giữa một field tồn tại với một document tồn tại.

## 1. Chuẩn bị entity và repository

Giả sử ứng dụng quản lý sản phẩm. Một sản phẩm có thể đang được kích hoạt hoặc tạm ngừng; ngoài ra, một số thuộc tính như mô tả hoặc ghi chú có thể chưa được cung cấp.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Boolean)
    private Boolean available;

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Keyword)
    private String internalNote;

    // Constructors, getters and setters
}
~~~

Chọn `Boolean` thay vì `boolean` khi thuộc tính có thể chưa được xác định. Kiểu wrapper `Boolean` có ba trạng thái trong Java:

- `true`: đã xác nhận đang hoạt động.
- `false`: đã xác nhận không hoạt động.
- `null`: chưa có giá trị hoặc chưa được xác định.

Nếu dùng primitive `boolean`, thuộc tính chỉ có `true` hoặc `false`; Java không thể biểu diễn trạng thái null.

Repository:

~~~java
import java.util.List;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByAvailableTrue();

    List<ProductDocument> findByAvailableFalse();

    List<ProductDocument> findByInternalNoteExists();

    List<ProductDocument> findByInternalNoteIsNull();

    List<ProductDocument> findByInternalNoteIsNotNull();
}
~~~

Spring Data phân tích phần tên method sau `By` thành các điều kiện. Các method trên không cần truyền tham số vì điều kiện đã được mô tả trực tiếp trong tên method.

## 2. True và IsTrue: tìm giá trị boolean true

`True` và `IsTrue` là hai cách viết tương đương trong query derivation.

Ví dụ:

~~~java
List<ProductDocument> findByAvailableTrue();

List<ProductDocument> findByAvailableIsTrue();
~~~

Hai method này tìm các document có field `available` mang giá trị boolean `true`.

Tương tự, với query DSL trực tiếp:

~~~json
{
  "query": {
    "term": {
      "available": true
    }
  }
}
~~~

Một lưu ý về cách Spring Data Elasticsearch tạo query: tài liệu query method hiện hành minh họa `findByAvailableTrue` bằng `query_string` với giá trị `"true"` trên field `available`. Khi tự viết query DSL, có thể dùng `term` với giá trị boolean như ví dụ trên.

### Khi nào dùng True?

Dùng `True` khi muốn lấy các document đã xác nhận trạng thái bật, hợp lệ hoặc được phép:

~~~java
List<ProductDocument> findByAvailableTrue();
~~~

Ví dụ nghiệp vụ:

- Sản phẩm đang được bán.
- Tài khoản đang hoạt động.
- Tính năng đã được bật.
- Bản ghi được xác nhận là hợp lệ.

Không nên hiểu `True` là “field có tồn tại”. Một field boolean có thể tồn tại nhưng mang giá trị `false`; khi đó nó không thỏa điều kiện `True`.

## 3. False và IsFalse: tìm giá trị boolean false

`False` và `IsFalse` cũng là hai cách viết tương đương:

~~~java
List<ProductDocument> findByAvailableFalse();

List<ProductDocument> findByAvailableIsFalse();
~~~

Query DSL tương ứng:

~~~json
{
  "query": {
    "term": {
      "available": false
    }
  }
}
~~~

Method này tìm document có giá trị boolean `false`. Nó không tìm các document bị thiếu field `available` hoặc có giá trị null.

### Phân biệt false và null

Giả sử có ba document:

~~~json
[
  {
    "_id": "p1",
    "available": true
  },
  {
    "_id": "p2",
    "available": false
  },
  {
    "_id": "p3",
    "name": "Keyboard"
  }
]
~~~

Kết quả:

| Document | Giá trị available | `findByAvailableTrue()` | `findByAvailableFalse()` |
|---|---|---|---|
| p1 | `true` | Có | Không |
| p2 | `false` | Không | Có |
| p3 | Không có field | Không | Không |

`false` là một giá trị boolean cụ thể. Field không có giá trị không tự động được xem là `false`.

Nếu nghiệp vụ cần tìm cả các bản ghi chưa được xác định trạng thái, hãy dùng kiểm tra null/exists phù hợp.

## 4. Exists: kiểm tra field có giá trị được lập chỉ mục

`Exists` là predicate keyword để kiểm tra sự tồn tại của giá trị trong một field.

Ví dụ:

~~~java
List<ProductDocument> findByInternalNoteExists();
~~~

Method này tìm các document có field `internalNote` chứa giá trị được Elasticsearch lập chỉ mục.

Query DSL tương ứng:

~~~json
{
  "query": {
    "exists": {
      "field": "internalNote"
    }
  }
}
~~~

`Exists` không có nghĩa là document tồn tại. Nó kiểm tra field được chỉ định trong document có giá trị được lập chỉ mục hay không.

Ví dụ, nếu một sản phẩm có `name` nhưng không có `internalNote`, document vẫn tồn tại trong index, nhưng không thỏa `findByInternalNoteExists()`.

### Exists không chỉ kiểm tra key trong _source

Elasticsearch xây dựng exists query dựa trên giá trị có thể tìm kiếm trong index. Vì vậy, kết quả có thể khác với việc chỉ kiểm tra JSON có chứa tên thuộc tính hay không.

Thông thường:

- Field có chuỗi `""` (chuỗi rỗng): được xem là có giá trị.
- Field có giá trị `null`: không có giá trị được lập chỉ mục theo mặc định.
- Field là mảng rỗng `[]`: được xem là không có giá trị.
- Field không xuất hiện trong document: không có giá trị được lập chỉ mục.

Một số cấu hình như `null_value`, `ignore_above` hoặc `ignore_malformed` có thể ảnh hưởng đến kết quả exists. Cần xem mapping thực tế để giải thích chính xác kết quả.

## 5. IsNull và Null: tìm field không có giá trị

`IsNull` và `Null` là hai cách viết tương đương:

~~~java
List<ProductDocument> findByInternalNoteIsNull();

List<ProductDocument> findByInternalNoteNull();
~~~

Trong Elasticsearch, Spring Data tạo điều kiện phủ định exists query:

~~~json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "exists": {
            "field": "internalNote"
          }
        }
      ]
    }
  }
}
~~~

Điều kiện này trả về document mà field `internalNote` không có giá trị được lập chỉ mục.

Điểm quan trọng: `IsNull` thường bao gồm cả hai trường hợp:

1. Document có thuộc tính `internalNote: null`.
2. Document hoàn toàn không có thuộc tính `internalNote`.

Ngoài ra, field có mặt trong `_source` nhưng không được lập chỉ mục vì mapping hoặc quy tắc bỏ qua giá trị cũng có thể được xem là không tồn tại đối với exists query.

Vì vậy, không nên diễn giải `IsNull` như phép kiểm tra chính xác “JSON có key với giá trị null”.

## 6. IsNotNull và NotNull: tìm field có giá trị

`IsNotNull` và `NotNull` là hai cách viết tương đương:

~~~java
List<ProductDocument> findByInternalNoteIsNotNull();

List<ProductDocument> findByInternalNoteNotNull();
~~~

Spring Data Elasticsearch chuyển điều kiện này thành exists query:

~~~json
{
  "query": {
    "exists": {
      "field": "internalNote"
    }
  }
}
~~~

`IsNotNull` tìm các document có giá trị được lập chỉ mục trong field `internalNote`.

Ví dụ:

| Dữ liệu trong document | Exists / IsNotNull | IsNull |
|---|---|---|
| `"internalNote": "Checked"` | Có | Không |
| `"internalNote": ""` | Có | Không |
| `"internalNote": null` | Không (mặc định) | Có |
| Không có `internalNote` | Không | Có |
| `"internalNote": []` | Không | Có |

`IsNotNull` không có nghĩa là chuỗi khác rỗng. Chuỗi rỗng vẫn là một giá trị được lập chỉ mục trong trường hợp thông thường.

Nếu muốn kiểm tra chuỗi có nội dung thực sự, cần điều kiện khác phù hợp với kiểu field, ví dụ kết hợp exists với wildcard hoặc lưu thêm trạng thái chuẩn hóa.

## 7. So sánh năm keyword

| Keyword | Ý nghĩa | Query Elasticsearch thường được tạo |
|---|---|---|
| `True` / `IsTrue` | Giá trị boolean true | `query_string` với `"true"` trong tài liệu query method hiện hành |
| `False` / `IsFalse` | Giá trị boolean false | `query_string` với `"false"` trong tài liệu query method hiện hành |
| `Exists` | Field có giá trị được lập chỉ mục | `exists` |
| `IsNull` / `Null` | Field không có giá trị được lập chỉ mục | `must_not exists` |
| `IsNotNull` / `NotNull` | Field có giá trị được lập chỉ mục | `exists` |

Các tên keyword là cú pháp query derivation của Spring Data. Không nên nhầm `Exists` với `existsBy...` ở phần đầu tên repository method; hai cách dùng có vai trò khác nhau.

## 8. Phân biệt Exists predicate và existsBy projection

Đây là điểm dễ nhầm nhất khi đặt tên repository method.

### Exists predicate: findByFieldExists

~~~java
List<ProductDocument> findByInternalNoteExists();
~~~

Method này trả về các document có field `internalNote` tồn tại theo nghĩa Elasticsearch exists query.

Nó tương đương điều kiện:

~~~json
{
  "query": {
    "exists": {
      "field": "internalNote"
    }
  }
}
~~~

### Exists projection: existsBy...

~~~java
boolean existsBySku(String sku);
~~~

Đây là một repository method có subject keyword `exists...By`. Nó trả về `boolean` để cho biết có document nào thỏa điều kiện `sku = giá trị truyền vào` hay không.

Nó không phải phép kiểm tra field `sku` có tồn tại trong từng document hay không.

Ví dụ:

~~~java
boolean existsBySku("KB-1001");
~~~

Có nghĩa là kiểm tra có sản phẩm nào mang SKU `KB-1001` hay không.

Còn:

~~~java
List<ProductDocument> findBySkuExists();
~~~

Có nghĩa là lấy các sản phẩm có field `sku` có giá trị được lập chỉ mục.

### ExistsById là phương thức CRUD riêng

`existsById(id)` là phương thức được định nghĩa sẵn trong `CrudRepository`. Nó kiểm tra document có ID tương ứng hay không:

~~~java
boolean exists = productRepository.existsById("p1001");
~~~

Đây là kiểm tra document theo định danh, không phải query predicate `Exists` trên một field bất kỳ.

## 9. Kết hợp các điều kiện

Các predicate có thể kết hợp với `And`, `Or` và những điều kiện khác.

Ví dụ lấy sản phẩm đang bật và có ghi chú:

~~~java
List<ProductDocument> findByAvailableTrueAndInternalNoteExists();
~~~

Ví dụ lấy sản phẩm đang tắt hoặc chưa có trạng thái:

~~~java
List<ProductDocument> findByAvailableFalseOrAvailableIsNull();
~~~

Ví dụ tìm sản phẩm đang bật nhưng chưa có ghi chú:

~~~java
List<ProductDocument> findByAvailableTrueAndInternalNoteIsNull();
~~~

Spring Data chuyển `And` thành các điều kiện phải đồng thời thỏa mãn; `Or` tạo nhánh điều kiện thay thế.

Nếu tên method trở nên dài hoặc khó đọc, hãy cân nhắc dùng `@Query`, `CriteriaQuery` hoặc `NativeQuery` để mô tả query rõ ràng hơn.

## 10. Kiểm soát null_value trong Elasticsearch mapping

Mặc định, Elasticsearch không lập chỉ mục giá trị JSON `null`. Nếu cần xem explicit null như một giá trị có thể truy vấn, một số field type hỗ trợ mapping parameter `null_value`.

Ví dụ với field keyword:

~~~json
{
  "mappings": {
    "properties": {
      "internalNote": {
        "type": "keyword",
        "null_value": "__NULL__"
      }
    }
  }
}
~~~

Với mapping này, giá trị null tường minh có thể được thay bằng giá trị `"__NULL__"` khi lập chỉ mục. Field đó sẽ được xem là có giá trị trong exists query.

Ví dụ document:

~~~json
{
  "internalNote": null
}
~~~

Có thể tìm giá trị thay thế bằng term query:

~~~json
{
  "query": {
    "term": {
      "internalNote": "__NULL__"
    }
  }
}
~~~

Lưu ý:

- `null_value` thay thế giá trị null khi lập chỉ mục; nó không thay đổi nội dung gốc trong `_source`.
- Field bị bỏ qua do không có giá trị hoặc document không có field vẫn không tự động nhận sentinel.
- Khi dùng `null_value`, `IsNotNull` có thể khớp cả giá trị null tường minh vì Elasticsearch đã lập chỉ mục sentinel cho field.
- Cần chọn sentinel không thể bị nhầm với dữ liệu nghiệp vụ bình thường.

Nếu nghiệp vụ phải phân biệt rõ “không gửi field”, “gửi null” và “gửi chuỗi rỗng”, có thể cần thêm field trạng thái hoặc biểu diễn dữ liệu rõ ràng hơn trong document.

## 11. Lưu ý với text, keyword và field bị bỏ qua

Exists query kiểm tra khả năng tìm thấy giá trị trong index. Nó không đơn thuần đọc JSON nguồn.

Một số trường hợp cần lưu ý:

### Field text

Field text được phân tích bằng analyzer. Chuỗi rỗng vẫn được Elasticsearch xem là có giá trị trong ngữ nghĩa exists thông thường, dù analyzer có thể không tạo token tìm kiếm như một từ bình thường.

### Field keyword và ignore_above

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "internalNote": {
        "type": "keyword",
        "ignore_above": 20
      }
    }
  }
}
~~~

Nếu một chuỗi dài hơn giới hạn `ignore_above`, giá trị có thể vẫn còn trong `_source` nhưng không được lập chỉ mục cho field keyword đó. Khi ấy exists query có thể không khớp.

### ignore_malformed

Với field có kiểu dữ liệu cụ thể, giá trị không hợp lệ có thể bị bỏ qua nếu cấu hình `ignore_malformed` cho phép. Giá trị bị bỏ qua không tạo indexed value cho field đó và có thể làm exists query không khớp.

### index và doc_values

Nếu một field không được lập chỉ mục và cũng không có doc values, Elasticsearch có thể không có dữ liệu để thực hiện exists query cho field đó. Hãy xem mapping và cấu hình field trước khi dựa vào `Exists` hoặc `IsNull`.

## 12. Ví dụ repository đầy đủ

Một repository có thể khai báo các method như sau:

~~~java
import java.util.List;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    // Giá trị boolean
    List<ProductDocument> findByAvailableTrue();

    List<ProductDocument> findByAvailableFalse();

    // Field có hoặc không có indexed value
    List<ProductDocument> findByInternalNoteExists();

    List<ProductDocument> findByInternalNoteIsNull();

    List<ProductDocument> findByInternalNoteIsNotNull();

    // Kết hợp điều kiện
    List<ProductDocument> findByAvailableTrueAndInternalNoteExists();

    List<ProductDocument> findByAvailableFalseOrInternalNoteIsNull();

    // Kiểm tra có document thỏa điều kiện hay không
    boolean existsBySku(String sku);

    // CRUD repository method kiểm tra theo document ID
    boolean existsById(String id);
}
~~~

Các method này minh họa ba nhóm mục đích:

1. Predicate boolean để lọc theo `true`/`false`.
2. Predicate tồn tại field để lọc theo `exists`/`null`.
3. Projection `existsBy...` để trả về kết quả boolean cho một điều kiện tìm kiếm.

## 13. Các lỗi thường gặp

### Coi false là null

`findByAvailableFalse()` chỉ tìm giá trị false. Field thiếu hoặc null không được coi là false.

### Coi IsNull là kiểm tra key JSON có mặt

`findByInternalNoteIsNull()` dựa trên exists query phủ định. Nó có thể khớp cả field không được gửi trong document, null tường minh và các trường hợp không có indexed value.

### Coi Exists là document tồn tại

`findByInternalNoteExists()` kiểm tra field `internalNote`. Muốn kiểm tra document theo ID, dùng `existsById(id)`.

### Nhầm findByNameExists với existsByName

`findByNameExists()` trả về document có field name tồn tại. `existsByName("Keyboard")` trả về boolean cho biết có document thỏa điều kiện name bằng giá trị truyền vào hay không.

### Cho rằng chuỗi rỗng là null

Chuỗi `""` là một giá trị; exists query thường xem field đó là tồn tại. Nếu cần loại chuỗi rỗng, hãy tạo điều kiện riêng.

### Không kiểm tra mapping null_value

Nếu field dùng `null_value`, null tường minh được lập chỉ mục thành sentinel. Khi đó kết quả `Exists`, `IsNull` và `IsNotNull` có thể khác với mapping mặc định.

### Dùng method keyword không được phiên bản hỗ trợ

Spring Data Commons có danh sách keyword chung, nhưng từng module datastore có thể hỗ trợ khác nhau. Hãy đối chiếu tài liệu query method của đúng phiên bản Spring Data Elasticsearch đang dùng.

## 14. Quy trình chọn keyword

Khi viết repository method, hãy tự xác định mục tiêu:

1. Muốn tìm giá trị boolean true? Dùng `findByAvailableTrue()`.
2. Muốn tìm giá trị boolean false? Dùng `findByAvailableFalse()`.
3. Muốn tìm field có giá trị được lập chỉ mục? Dùng `findByFieldExists()`.
4. Muốn tìm field không có indexed value? Dùng `findByFieldIsNull()`.
5. Muốn tìm field có indexed value? Dùng `findByFieldIsNotNull()`.
6. Muốn biết có document nào thỏa điều kiện hay không? Dùng `existsBy...` với kiểu trả về boolean.
7. Muốn kiểm tra document theo ID? Dùng `existsById(id)`.
8. Cần phân biệt null tường minh với field bị thiếu? Thiết kế mapping hoặc field trạng thái riêng, không chỉ dựa vào `IsNull`.

## Kết luận

`True` và `False` lọc giá trị boolean cụ thể. `Exists` kiểm tra field có giá trị được lập chỉ mục; `IsNull` và `IsNotNull` lần lượt là phủ định và khẳng định của exists query. Trong Elasticsearch, null tường minh và field bị thiếu thường cùng được xem là không có indexed value, trừ khi mapping như `null_value` thay đổi hành vi đó. Cần phân biệt predicate `findByFieldExists()`, projection `existsByField(...)` và phương thức CRUD `existsById(...)` để chọn đúng API.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Query methods](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/elasticsearch-repository-queries.html)
- [Spring Data Elasticsearch — Repository query keywords](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/query-keywords-reference.html)
- [Elasticsearch — Exists query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-exists-query.html)
- [Elasticsearch — null_value mapping parameter](https://www.elastic.co/guide/en/elasticsearch/reference/current/null-value.html)
