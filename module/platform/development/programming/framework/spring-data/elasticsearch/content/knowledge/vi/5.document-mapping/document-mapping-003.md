# `@Field`, tên trường Java và tên trường trong Elasticsearch

Trong Spring Data Elasticsearch, tên thuộc tính trong class Java có thể khác tên field được lưu trong document Elasticsearch. Ví dụ, Java dùng `firstName` theo quy ước camelCase, trong khi index có thể lưu JSON field là `first_name` theo quy ước snake_case.

Annotation `@Field` cho phép khai báo tên và metadata mapping của một thuộc tính. Spring Data dùng mapping metadata này khi chuyển đổi object Java thành document và khi đọc document trở lại object. Nhờ đó, code Java có thể giữ tên thuộc tính dễ đọc trong khi cấu trúc document tuân theo hợp đồng dữ liệu của Elasticsearch.

```text
Java property                 Elasticsearch document
-------------                 ----------------------
firstName          ------->   first_name
email              ------->   email_address
createdAt          ------->   created_at
lineItems          ------->   line_items
```

Điểm quan trọng là cần phân biệt **tên thuộc tính Java**, **tên field trong Elasticsearch** và **kiểu mapping của field**. Ba khái niệm này có liên quan nhưng không phải một.

## 1. Tên thuộc tính Java và tên field Elasticsearch

Giả sử ứng dụng có class:

```java
public class CustomerDocument {
    private String firstName;
    private String email;
}
```

Tên `firstName` và `email` là tên property mà code Java sử dụng. Khi Spring Data tạo mapping theo mặc định, tên field tương ứng thường được lấy từ tên property Java nếu không có cấu hình đổi tên.

Document Elasticsearch có thể trông như sau:

```json
{
  "firstName": "An",
  "email": "an@example.com"
}
```

Tên field trong Elasticsearch là tên xuất hiện trong `_source` và mapping của index. Tên này được dùng khi viết Query DSL trực tiếp, xem mapping hoặc thao tác với Java API Client ở mức thấp.

Nếu hợp đồng dữ liệu yêu cầu snake_case, ta có thể đổi tên field trong Elasticsearch mà vẫn giữ nguyên tên property Java:

```java
public class CustomerDocument {

    @Field(name = "first_name", type = FieldType.Text)
    private String firstName;

    @Field(name = "email_address", type = FieldType.Keyword)
    private String email;
}
```

Document được lưu sẽ có dạng:

```json
{
  "first_name": "An",
  "email_address": "an@example.com"
}
```

Trong service Java, ta vẫn truy cập `customer.getFirstName()` và `customer.getEmail()`. Annotation chỉ định tên field ở tầng Elasticsearch; nó không đổi tên property, getter, setter hoặc biến trong source code Java.

## 2. Cấu trúc và ý nghĩa của `@Field`

`@Field` thuộc package:

```java
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
```

Annotation này mô tả cách một property được ánh xạ thành field Elasticsearch. Hai thuộc tính thường dùng nhất là:

- `name`: tên field trong Elasticsearch. Nếu bỏ qua, Spring Data sử dụng tên property theo mapping mặc định.
- `type`: kiểu field Elasticsearch, ví dụ `Text`, `Keyword`, `Long`, `Integer`, `Date`, `Boolean`, `Object` hoặc `Nested`.

Ví dụ:

```java
@Field(name = "product_name", type = FieldType.Text)
private String productName;

@Field(name = "sku", type = FieldType.Keyword)
private String sku;

@Field(name = "quantity", type = FieldType.Integer)
private Integer quantity;
```

`name` giải quyết vấn đề đặt tên. `type` quyết định Elasticsearch hiểu và lập chỉ mục giá trị như thế nào. Chỉ đổi `name` không tự đổi kiểu mapping; chỉ đổi `type` không tự đổi tên field.

### Một số kiểu mapping thường gặp

| Kiểu Spring Data | Kiểu Elasticsearch | Trường hợp sử dụng thường gặp |
|---|---|---|
| `FieldType.Text` | `text` | Nội dung văn bản cần phân tích để full-text search. |
| `FieldType.Keyword` | `keyword` | Mã, trạng thái, email, giá trị cần so khớp chính xác hoặc aggregation. |
| `FieldType.Integer` | `integer` | Số nguyên trong phạm vi 32-bit. |
| `FieldType.Long` | `long` | Số nguyên có phạm vi lớn hơn. |
| `FieldType.Double` | `double` | Số thực độ chính xác kép. |
| `FieldType.Boolean` | `boolean` | Giá trị đúng/sai. |
| `FieldType.Date` | `date` | Ngày giờ theo định dạng được cấu hình. |
| `FieldType.Object` | `object` | Object JSON thông thường. |
| `FieldType.Nested` | `nested` | Mảng object cần giữ quan hệ giữa các field trong cùng phần tử. |

Không nên chọn kiểu chỉ dựa vào kiểu Java. Ví dụ `String` có thể ánh xạ thành `text` hoặc `keyword` tùy cách sử dụng. Tên sản phẩm cần full-text search có thể là `text`; mã sản phẩm thường phù hợp với `keyword`.

## 3. Ví dụ đầy đủ: Java camelCase, Elasticsearch snake_case

Giả sử index `customers` cần các field theo snake_case. Entity có thể viết như sau:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "customers")
public class CustomerDocument {

    @Id
    private String id;

    @Field(name = "customer_code", type = FieldType.Keyword)
    private String customerCode;

    @Field(name = "first_name", type = FieldType.Text)
    private String firstName;

    @Field(name = "last_name", type = FieldType.Text)
    private String lastName;

    @Field(name = "email_address", type = FieldType.Keyword)
    private String email;

    @Field(name = "is_active", type = FieldType.Boolean)
    private Boolean active;

    // constructors, getters, setters
}
```

Khi lưu một object, `_source` có thể chứa:

```json
{
  "customer_code": "CUS-001",
  "first_name": "An",
  "last_name": "Nguyen",
  "email_address": "an@example.com",
  "is_active": true
}
```

Ở đây:

- Java code sử dụng `customerCode`, `firstName`, `lastName`, `email`, `active`.
- Elasticsearch document sử dụng `customer_code`, `first_name`, `last_name`, `email_address`, `is_active`.
- Mapping type được khai báo riêng cho từng field.

Khi Spring Data đọc document, converter dựa trên mapping metadata để gán `first_name` vào property `firstName`, `email_address` vào `email`, v.v. Ứng dụng không cần tự viết đoạn chuyển đổi tên cho mỗi lần lưu hoặc đọc.

## 4. `@Id` khác với `@Field`

`@Id` đánh dấu property Java được dùng làm document id của Elasticsearch. Document id được lưu trong metadata `_id`, không phải một field thông thường trong `_source`.

Ví dụ:

```java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(name = "product_name", type = FieldType.Text)
    private String name;
}
```

Document có thể có metadata:

```text
_index: products
_id:    P-100
```

và `_source`:

```json
{
  "product_name": "Java Fundamentals"
}
```

Không nên kỳ vọng property `id` sẽ tự xuất hiện thành JSON field `id`. Nếu nghiệp vụ cần lưu thêm mã định danh trong `_source` để truy vấn hoặc hiển thị như một field bình thường, hãy khai báo một property riêng, chẳng hạn `productCode`, và ánh xạ nó bằng `@Field`.

## 5. Tên field trong object lồng nhau

`@Field(name = ...)` cũng áp dụng cho property bên trong object. Ví dụ:

```java
public class Address {

    @Field(name = "street_name", type = FieldType.Text)
    private String street;

    @Field(name = "city_name", type = FieldType.Keyword)
    private String city;
}

@Document(indexName = "customers")
public class CustomerDocument {

    @Id
    private String id;

    @Field(name = "full_name", type = FieldType.Text)
    private String fullName;

    private Address address;
}
```

Document tương ứng:

```json
{
  "full_name": "An Nguyen",
  "address": {
    "street_name": "12 Le Loi",
    "city_name": "Ho Chi Minh City"
  }
}
```

Đường dẫn field trong Elasticsearch là `address.city_name`, không phải `address.city`. Khi làm việc với raw Query DSL, phải dùng đúng tên field theo mapping Elasticsearch.

Đối với mảng object, cần phân biệt `object` và `nested`. Object thông thường có thể làm phẳng các giá trị khi lập chỉ mục; nếu cần giữ quan hệ giữa các field của từng phần tử mảng trong truy vấn, khai báo `FieldType.Nested` và dùng nested query.

Ví dụ:

```java
public class OrderLine {

    @Field(name = "product_code", type = FieldType.Keyword)
    private String productCode;

    @Field(name = "unit_price", type = FieldType.Double)
    private Double unitPrice;
}

@Document(indexName = "orders")
public class OrderDocument {

    @Id
    private String id;

    @Field(name = "line_items", type = FieldType.Nested)
    private List<OrderLine> lineItems;
}
```

Đường dẫn field tương ứng là `line_items.product_code` và `line_items.unit_price`. Việc dùng `Nested` cần đi cùng nested query khi truy vấn theo điều kiện phải khớp trên cùng một phần tử.

## 6. Tên property được dùng ở đâu và tên Elasticsearch được dùng ở đâu?

Đây là điểm dễ nhầm khi một class Java dùng `firstName` nhưng mapping lưu `first_name`.

### Repository method dựa trên property Java

Với query method được Spring Data phân tích từ tên method, tên thuộc tính thường là tên property trong entity:

```java
public interface CustomerRepository
        extends ElasticsearchRepository<CustomerDocument, String> {

    List<CustomerDocument> findByFirstName(String firstName);

    Optional<CustomerDocument> findByEmail(String email);
}
```

Ở đây `FirstName` và `Email` tham chiếu đến property Java `firstName` và `email`. Spring Data sử dụng mapping metadata để chuyển điều kiện sang field tương ứng trong Elasticsearch, ví dụ `first_name` hoặc `email_address`.

### Raw Query JSON sử dụng tên field Elasticsearch

Với `@Query`, nội dung JSON là Query DSL được gửi đến Elasticsearch. Vì vậy, field trong JSON cần dùng tên theo mapping Elasticsearch:

```java
@Query("{\"term\": {\"email_address\": \"?0\"}}")
List<CustomerDocument> searchByEmailAddress(String email);
```

Nếu viết `email` trong JSON trong khi mapping thực tế là `email_address`, query sẽ tìm sai field và thường không trả về kết quả mong đợi.

### Java API Client trực tiếp sử dụng tên field Elasticsearch

Khi gọi Elasticsearch Java API Client ở mức thấp, tên field cũng là tên trong mapping:

```java
SearchResponse<CustomerDocument> response = client.search(s -> s
        .index("customers")
        .query(q -> q
                .term(t -> t
                        .field("email_address")
                        .value(v -> v.stringValue("an@example.com"))
                )
        ), CustomerDocument.class);
```

Java API Client không tự suy luận rằng `email_address` tương ứng với property `email` trong class Spring Data. Ứng dụng đang viết Query DSL trực tiếp nên phải dùng tên Elasticsearch.

Với các API truy vấn cấp cao của Spring Data, cách khai báo field phụ thuộc abstraction cụ thể: một số API nhận property path và được mapping qua metadata; các API nhận raw field name hoặc Query DSL thì cần tên Elasticsearch. Khi không chắc, hãy kiểm tra contract của API đang sử dụng và mapping thực tế, thay vì mặc định mọi chuỗi tên field đều được tự chuyển đổi.

## 7. `@Field` không chỉ dùng để đổi tên

Ngoài `name` và `type`, `@Field` còn có các thuộc tính điều khiển cách Elasticsearch lập chỉ mục và tìm kiếm. Một số thuộc tính thường gặp:

| Thuộc tính | Ý nghĩa |
|---|---|
| `index` | Có lập chỉ mục field để tìm kiếm hay không. `false` làm field không được lập chỉ mục theo cách thông thường. |
| `store` | Có lưu thêm giá trị field riêng để truy xuất bằng stored fields hay không; khác với việc lưu trong `_source`. |
| `analyzer` | Analyzer dùng khi lập chỉ mục cho field kiểu `text`. |
| `searchAnalyzer` | Analyzer dùng khi phân tích query cho field. |
| `normalizer` | Normalizer cho field kiểu `keyword` trong các trường hợp cần chuẩn hóa giá trị. |
| `format` / `pattern` | Định dạng ngày giờ được chấp nhận cho field kiểu `date`. |
| `ignoreAbove` | Giới hạn độ dài giá trị keyword được lập chỉ mục theo thiết lập tương ứng. |
| `coerce` | Điều khiển việc Elasticsearch có chuyển đổi một số giá trị đầu vào về kiểu field hay không. |

Ví dụ field chỉ lưu trong `_source` để hiển thị, không cần tìm kiếm:

```java
@Field(name = "internal_note", type = FieldType.Text, index = false)
private String internalNote;
```

Giá trị vẫn có thể nằm trong `_source`, nhưng không thể dùng nó như field được lập chỉ mục để thực hiện truy vấn term/full-text thông thường. `index = false` không đồng nghĩa với `store = true`.

Ví dụ cấu hình ngày:

```java
@Field(name = "created_at", type = FieldType.Date)
private Instant createdAt;
```

Khi dùng kiểu ngày giờ, cần bảo đảm định dạng dữ liệu ghi vào tương thích với mapping date của index. Nếu hệ thống có hợp đồng định dạng riêng, hãy khai báo `format`/`pattern` phù hợp với phiên bản Spring Data và Elasticsearch đang dùng, đồng thời kiểm tra mapping thực tế.

## 8. Multi-fields: một property, nhiều cách tìm kiếm

Đôi khi cùng một giá trị cần được tìm kiếm toàn văn và cũng cần lọc/sắp xếp chính xác. Elasticsearch hỗ trợ multi-fields: một field chính có thể có subfield với kiểu mapping khác.

Ví dụ, tên sản phẩm có thể được phân tích như `text`, đồng thời có subfield `keyword` để sort hoặc aggregation. Spring Data Elasticsearch cung cấp `@MultiField` và `@InnerField` để mô tả cấu trúc này:

```java
@MultiField(
    mainField = @Field(type = FieldType.Text),
    otherFields = {
        @InnerField(suffix = "keyword", type = FieldType.Keyword)
    }
)
private String productName;
```

Mapping có thể có field chính `productName` kiểu `text` và subfield `productName.keyword` kiểu `keyword` (tên field chính có thể được đổi bằng thuộc tính `name` nếu cần). Subfield không phải property Java thứ hai; nó là một phần mapping của cùng một property.

Khi query raw DSL hoặc dùng Java API Client, cần tham chiếu chính xác đường dẫn field/subfield theo mapping Elasticsearch, ví dụ `productName.keyword`.

## 9. Kiểm tra tên field thực tế trên Elasticsearch

Không nên chỉ dựa vào annotation để kết luận index đang có mapping gì. Index có thể đã được tạo từ trước, được tạo bởi template, hoặc được quản lý bởi một tiến trình khác.

Đọc mapping:

```http
GET /customers/_mapping
```

Đọc một document và `_source`:

```http
GET /customers/_doc/CUS-001
```

Kiểm tra các field được lập chỉ mục và kiểu dữ liệu bằng mapping response. Nếu `first_name` là field được khai báo, mapping sẽ hiển thị tên này trong `properties`.

Ví dụ mapping rút gọn:

```json
{
  "customers": {
    "mappings": {
      "properties": {
        "first_name": { "type": "text" },
        "email_address": { "type": "keyword" },
        "is_active": { "type": "boolean" }
      }
    }
  }
}
```

Nếu document có dữ liệu nhưng query không tìm thấy, hãy kiểm tra đồng thời:

1. Tên field trong `_source`.
2. Tên và kiểu field trong mapping.
3. Tên field thực sự được gửi trong Query DSL.
4. Analyzer/normalizer và loại query đang sử dụng.
5. Document đã được refresh để search nhìn thấy hay chưa.

## 10. Đổi tên field khi index đã tồn tại

`@Field(name = "first_name")` mô tả mapping mà Spring Data mong muốn sử dụng. Việc sửa annotation trong source code không tự đổi tên field của index đã tồn tại và cũng không tự chuyển dữ liệu cũ.

Giả sử index cũ có field `firstName`, sau đó entity đổi thành:

```java
@Field(name = "first_name", type = FieldType.Text)
private String firstName;
```

Nếu mapping cũ vẫn là `firstName`, document cũ vẫn lưu dữ liệu theo cấu trúc cũ. Query tìm `first_name` sẽ không tự tìm thấy giá trị đang nằm trong `firstName`. Việc cùng một field path đổi kiểu mapping cũng có thể gây mapping conflict.

Quy trình đổi tên an toàn thường gồm:

1. Tạo index mới với mapping đúng, ví dụ `customers_v2`.
2. Reindex dữ liệu từ index cũ và chuyển đổi field name nếu cần.
3. Kiểm tra số lượng document, mapping, query và dữ liệu mẫu.
4. Chuyển alias đọc/ghi sang index mới theo kế hoạch triển khai.
5. Chỉ xóa index cũ sau khi đã xác nhận việc chuyển đổi và khả năng rollback.

Không nên xóa index production chỉ để annotation mới có hiệu lực. Với dữ liệu cần giữ, hãy thiết kế migration và backup trước khi chuyển đổi.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Query không có kết quả sau khi đổi tên Java property | Query raw vẫn dùng tên cũ hoặc mapping name khác property name. | Xem `_mapping`, `_source` và request Query DSL thực tế. |
| Query method hoạt động nhưng `@Query` không hoạt động | Query method dùng property metadata, còn JSON trong `@Query` đang dùng sai field name. | Đổi JSON sang tên field Elasticsearch. |
| Lưu document báo mapping conflict | Index đã có field cùng tên nhưng kiểu khác với mapping mới. | Đọc mapping và kiểm tra lịch sử tạo index/template. |
| Property Java nhận giá trị null sau khi đọc | Tên field trong document không khớp mapping metadata hoặc dữ liệu được ghi theo schema cũ. | Kiểm tra `_source`, annotation và converter mapping. |
| Field có trong `_source` nhưng query không tìm thấy | Field có thể `index = false`, hoặc query/analyzer không phù hợp. | Kiểm tra mapping và loại query. |
| Sắp xếp/aggregation trên text field gặp lỗi | Field `text` không phù hợp cho sort/aggregation thông thường. | Dùng field `keyword` hoặc multi-field phù hợp. |

## 12. Quy ước đặt tên nên áp dụng

Một quy ước rõ ràng giúp giảm lỗi giữa Java code, mapping và Query DSL:

- Java property dùng camelCase, ví dụ `firstName`, `createdAt`, `lineItems`.
- Elasticsearch field dùng một quy ước thống nhất theo hợp đồng dữ liệu, ví dụ snake_case (`first_name`, `created_at`, `line_items`) hoặc camelCase nếu hệ thống đã chọn cách đó.
- Dùng `@Field(name = "...")` rõ ràng khi tên field cần khác property Java.
- Dùng `@Field(type = ...)` khi kiểu mapping cần được xác định rõ, đặc biệt với `text`, `keyword`, `date`, `nested` và các kiểu số.
- Không dùng hai property Java cùng ánh xạ vào một tên field Elasticsearch nếu không có thiết kế mapping chủ ý.
- Với object lồng nhau, giữ tên đường dẫn nhất quán và tránh tự ý dùng dấu chấm trong tên field để mô phỏng cấu trúc object.
- Query DSL viết trực tiếp phải dùng đúng tên field trong mapping.
- Xem mapping Elasticsearch là hợp đồng dữ liệu đã triển khai; thay đổi tên hoặc kiểu field cần có migration.

## 13. Những điểm cần nhớ

- Tên property Java và tên field Elasticsearch có thể khác nhau.
- Không khai báo `name` thì Spring Data thường dùng tên property theo mapping mặc định.
- `@Field(name = "first_name")` ánh xạ property `firstName` sang field Elasticsearch `first_name`.
- `@Field(type = ...)` khai báo kiểu mapping; chọn `text`, `keyword`, `date`, `nested` theo nhu cầu truy vấn.
- `@Id` ánh xạ property Java sang metadata `_id`, khác với field thông thường trong `_source`.
- Repository query method dựa trên property Java; raw Query DSL và Java API Client trực tiếp dùng tên field Elasticsearch.
- `index`, `store`, analyzer và các thuộc tính khác điều khiển hành vi mapping, không phải cách đổi tên property.
- Sửa annotation không tự sửa mapping và dữ liệu của index đã tồn tại; cần migration/reindex khi thay đổi schema.

Hiểu rõ quan hệ giữa property Java và field Elasticsearch giúp model trong Spring Data giữ được tên dễ đọc, trong khi document vẫn tuân thủ quy ước lưu trữ và tìm kiếm của hệ thống. Khi có sự cố, hãy đối chiếu entity, mapping thực tế, `_source` và Query DSL để xác định lớp nào đang sử dụng sai tên field.
