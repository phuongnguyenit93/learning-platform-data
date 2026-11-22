# MappingElasticsearchConverter và metadata ánh xạ

Spring Data Elasticsearch cho phép ứng dụng làm việc với document Elasticsearch bằng các class Java. Khi lưu một object, ứng dụng cần chuyển các thuộc tính Java thành cấu trúc document phù hợp; khi đọc kết quả, ứng dụng cần chuyển document trở lại object. `MappingElasticsearchConverter` đảm nhiệm phần chuyển đổi hai chiều này dựa trên metadata ánh xạ do Spring Data thu thập từ class, field, kiểu dữ liệu và các annotation.

Để hiểu converter, cần phân biệt ba thành phần: **entity Java** là mô hình dữ liệu trong ứng dụng; **mapping metadata** mô tả cách entity và property tương ứng với document; **Elasticsearch index mapping** là cấu trúc field được lưu ở cluster. Ba thành phần có liên hệ nhưng không phải một. Converter dùng metadata của ứng dụng để chuyển đổi dữ liệu; cluster dùng index mapping để phân tích, lập chỉ mục và truy vấn dữ liệu.

## 1. Vị trí của MappingElasticsearchConverter trong luồng dữ liệu

### 1.1. Chuyển đổi hai chiều

Giả sử ứng dụng có class `ProductDocument` và muốn lưu một sản phẩm vào index `products`. Service thường gọi repository hoặc `ElasticsearchOperations`. Spring Data sử dụng converter để biến object thành document trước khi gửi request đến Elasticsearch.

Khi tìm kiếm, Elasticsearch trả về dữ liệu document. Spring Data chuyển document đó thành object Java trước khi trả kết quả cho service.

~~~mermaid
flowchart TD
    A[ProductDocument object] --> B[MappingElasticsearchConverter]
    B --> C[Document representation]
    C --> D[Elasticsearch Java client]
    D --> E[Elasticsearch index]
    E --> D
    D --> F[Document response]
    F --> G[MappingElasticsearchConverter]
    G --> H[ProductDocument object]
~~~

Có thể tóm tắt hai chiều:

| Hướng | Đầu vào | Đầu ra | Mục đích |
|---|---|---|---|
| Write | Object Java | Document | Chuẩn bị dữ liệu để index hoặc cập nhật |
| Read | Document | Object Java | Ánh xạ kết quả tìm kiếm về kiểu ứng dụng |

Converter giúp service làm việc với object có kiểu rõ ràng thay vì tự tạo JSON cho từng thao tác. Các thao tác repository và `ElasticsearchOperations` có thể dùng chung cơ chế mapping này.

### 1.2. Converter không phải HTTP client

Cần phân biệt trách nhiệm:

- `MappingElasticsearchConverter` chuyển đổi giữa object Java và biểu diễn document của Spring Data.
- `ElasticsearchOperations` cung cấp API thao tác cấp cao như lưu, tìm kiếm, xóa và thực thi query.
- Repository cung cấp abstraction truy cập dữ liệu dựa trên interface.
- Elasticsearch Java client gửi request HTTP đến cluster và nhận response.
- Elasticsearch index mapping quy định cách cluster hiểu và lập chỉ mục các field.

Converter không tự mở kết nối mạng, không xác thực tài khoản và không gửi request HTTP. Những phần đó thuộc client và cấu hình kết nối. Converter cũng không tự thực hiện nghiệp vụ tìm kiếm hoặc quyết định document nào cần được lưu.

### 1.3. Converter được Spring quản lý

Trong ứng dụng Spring Boot dùng cấu hình Spring Data Elasticsearch thông thường, các thành phần mapping được cấu hình và quản lý trong application context. Repository và `ElasticsearchOperations` sử dụng converter tương ứng.

Bạn thường không cần tự khởi tạo `MappingElasticsearchConverter` trong service. Hãy khai báo entity và metadata đúng; chỉ tùy chỉnh conversion khi kiểu dữ liệu của ứng dụng cần cách biểu diễn đặc biệt.

## 2. Mapping metadata là gì?

### 2.1. Metadata mô tả entity và property

Metadata là thông tin mô tả cấu trúc entity và cách từng property được ánh xạ. Spring Data thu thập metadata từ:

- Kiểu class và kiểu property trong Java.
- Annotation ở cấp class như `@Document`.
- Annotation ở cấp property như `@Id`, `@Field`, `@Transient` và `@MultiField`.
- Thông tin constructor hoặc factory method dùng để tạo object.
- Quy tắc chuyển đổi kiểu dữ liệu mặc định và custom conversions.

Ví dụ:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(name = "product_name", type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    public ProductDocument() {
    }

    // Constructor, getter và setter được lược bớt.
}
~~~

Từ class trên, Spring Data có thể nhận biết:

- `ProductDocument` là entity được lưu trong index `products`.
- `id` là định danh document.
- `name` được ánh xạ sang field `product_name` có kiểu `text`.
- `category` là field `keyword`.
- `price` được ánh xạ sang kiểu số `double`.

Tên Java property không nhất thiết phải trùng tên field trong Elasticsearch. Metadata cho phép khai báo tên field đích bằng `@Field(name = "...")`.

### 2.2. Mapping context

Spring Data sử dụng mapping context để quản lý thông tin về các entity và property. Trong Spring Data Elasticsearch, `SimpleElasticsearchMappingContext` là một implementation mapping context chuyên cho Elasticsearch.

Mapping context cung cấp mô hình metadata mà converter có thể tra cứu, chẳng hạn:

- Entity class tương ứng với loại document nào.
- Entity có những property nào.
- Property nào là ID.
- Tên field trong document là gì.
- Kiểu dữ liệu của property là gì.
- Property có annotation mapping đặc biệt nào.
- Property lồng nhau được mô tả như thế nào.

Trong mô hình Spring Data, metadata entity và property thường được biểu diễn qua các abstraction như `ElasticsearchPersistentEntity` và `ElasticsearchPersistentProperty`.

Có thể hình dung:

~~~text
ProductDocument.class
       |
       v
Mapping Context
       |
       +--> Entity metadata
       |      indexName = products
       |
       +--> Property metadata
              id       -> document id
              name     -> product_name / text
              category -> category / keyword
              price    -> price / double
       |
       v
MappingElasticsearchConverter
~~~

Mapping context là metadata phía ứng dụng. Nó không phải bản mapping đang lưu trên Elasticsearch cluster. Cluster có thể đang chứa mapping cũ hoặc mapping được tạo thủ công; vì vậy metadata Java và mapping thực tế cần được giữ nhất quán.

### 2.3. Metadata được xây dựng và tái sử dụng

Mapping metadata được Spring Data xây dựng từ các kiểu entity mà ứng dụng sử dụng. Converter tra cứu metadata này khi đọc hoặc ghi document. Nhờ vậy, converter không cần phân tích lại toàn bộ annotation của class ở mỗi lần lưu.

Nếu thay đổi tên property, kiểu Java hoặc annotation, metadata của ứng dụng sẽ phản ánh thay đổi sau khi ứng dụng được khởi động lại với code mới. Tuy nhiên, index mapping đã tồn tại trên cluster không tự động được thay đổi chỉ vì class Java đã đổi.

## 3. Annotation ở cấp entity

### 3.1. `@Document`

`@Document` đánh dấu một class là entity được ánh xạ tới Elasticsearch document. Thuộc tính thường gặp nhất là `indexName`.

~~~java
@Document(indexName = "products")
public class ProductDocument {
    // Các property của document.
}
~~~

`indexName` cho biết tên index mà entity gắn với. Các thao tác repository hoặc operations dựa trên entity có thể dùng metadata này để xác định index đích.

Một số thuộc tính khác của `@Document` có thể điều khiển hành vi liên quan đến tạo index và type hint, tùy phiên bản Spring Data Elasticsearch. Hãy xem tài liệu của đúng phiên bản đang dùng khi cần thay đổi các tùy chọn đó.

`@Document` không có nghĩa class Java tự tạo ra một Elasticsearch cluster. Nó cung cấp metadata để Spring Data hiểu entity thuộc index nào và áp dụng mapping tương ứng.

### 3.2. Một class thường đại diện cho một loại document

Ví dụ ứng dụng có hai loại dữ liệu:

~~~java
@Document(indexName = "products")
public class ProductDocument {
    @Id
    private String id;

    private String name;
}

@Document(indexName = "categories")
public class CategoryDocument {
    @Id
    private String id;

    private String name;
}
~~~

Hai class có metadata index khác nhau. Repository của từng entity thao tác với loại document tương ứng.

Việc chọn index name nên ổn định và phù hợp với cách triển khai. Nếu cần tách dữ liệu theo môi trường, có thể cấu hình tên index theo chiến lược ứng dụng hỗ trợ; tránh để service tự ghép tên index tùy tiện ở nhiều nơi.

## 4. Annotation ở cấp property

### 4.1. `@Id`

`@Id` đánh dấu property làm định danh của document:

~~~java
@Id
private String id;
~~~

Elasticsearch lưu định danh document trong metadata `_id`. Spring Data dùng property được đánh dấu để đọc hoặc ghi ID khi thao tác document.

ID không giống một field tìm kiếm thông thường. Nếu cần tìm theo mã nghiệp vụ như `productCode`, hãy khai báo property riêng và mapping field phù hợp; không mặc định rằng mọi mã nghiệp vụ đều là `_id`.

### 4.2. `@Field`

`@Field` cung cấp metadata cho một property. Các thông tin quan trọng có thể gồm tên field, kiểu dữ liệu Elasticsearch, analyzer, search analyzer, format ngày giờ, khả năng index hoặc lưu trữ và các tùy chọn mapping khác.

Ví dụ:

~~~java
@Field(name = "product_name", type = FieldType.Text, analyzer = "standard")
private String name;

@Field(type = FieldType.Keyword)
private String category;

@Field(type = FieldType.Boolean)
private boolean available;

@Field(type = FieldType.Long)
private Long stockQuantity;
~~~

Các kiểu thường gặp:

| FieldType | Mục đích |
|---|---|
| `Text` | Văn bản được phân tích để tìm kiếm toàn văn |
| `Keyword` | Chuỗi dùng cho so khớp chính xác, lọc, nhóm hoặc sắp xếp |
| `Integer`, `Long` | Số nguyên |
| `Float`, `Double`, `Half_Float`, `Scaled_Float` | Số thực theo kiểu mapping đã chọn |
| `Boolean` | Giá trị đúng/sai |
| `Date` | Ngày hoặc thời điểm |
| `Object` | Đối tượng JSON lồng nhau |
| `Nested` | Mảng object cần giữ quan hệ field trong từng phần tử khi truy vấn |
| `Binary` | Dữ liệu nhị phân theo hỗ trợ của Elasticsearch |

Không nên chọn `FieldType` chỉ vì tên nó gần giống kiểu Java. Hãy chọn theo cách dữ liệu được truy vấn. Ví dụ, một chuỗi trạng thái thường phù hợp với `Keyword`, trong khi phần mô tả dài thường phù hợp với `Text`.

### 4.3. Đổi tên field trong document

Khi tên field trong Elasticsearch khác tên property Java, dùng `name`:

~~~java
@Field(name = "created_at", type = FieldType.Date)
private Instant createdAt;
~~~

Ứng dụng vẫn dùng tên Java `createdAt`, còn document sử dụng field `created_at`. Converter dựa trên metadata để ánh xạ đúng hai tên.

Đổi tên field trong class không tự đổi tên field cũ trên cluster. Nếu index hiện tại có field `createdAt` mà code mới dùng `created_at`, cần có kế hoạch chuyển dữ liệu hoặc tạo index mới và reindex nếu cần giữ dữ liệu cũ.

### 4.4. `@Transient`

Một property chỉ phục vụ tính toán trong ứng dụng và không nên được lưu vào document có thể được đánh dấu `@Transient`:

~~~java
@Transient
private String displayLabel;
~~~

Converter bỏ qua property transient trong quá trình mapping thông thường. Khi đọc document, property này không được khôi phục từ Elasticsearch và ứng dụng cần tự tính hoặc gán giá trị nếu cần.

Không dùng `@Transient` cho dữ liệu nghiệp vụ cần được lưu và tìm kiếm. Nếu một property cần được ghi hoặc đọc theo hướng riêng, hãy kiểm tra các annotation read-only/write-only được Spring Data Elasticsearch hỗ trợ trong phiên bản đang sử dụng.

## 5. Mapping object lồng nhau và collection

### 5.1. Object lồng nhau

Một document có thể chứa object lồng nhau:

~~~java
public class BrandDocument {

    private String code;

    @Field(type = FieldType.Keyword)
    private String name;

    public BrandDocument() {
    }
}

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Object)
    private BrandDocument brand;
}
~~~

Document có thể có cấu trúc:

~~~json
{
  "name": "Mechanical Keyboard",
  "brand": {
    "code": "B01",
    "name": "Example"
  }
}
~~~

Converter tiếp tục sử dụng metadata của class lồng nhau để chuyển đổi các property bên trong object. Vì vậy, metadata không chỉ áp dụng cho entity gốc mà còn quan trọng với các kiểu object được tham chiếu.

### 5.2. Danh sách object

Một property dạng collection cũng có thể chứa các object:

~~~java
public class ProductImage {

    @Field(type = FieldType.Keyword)
    private String url;

    @Field(type = FieldType.Integer)
    private Integer position;

    public ProductImage() {
    }
}

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Object)
    private List<ProductImage> images;
}
~~~

Converter ánh xạ từng phần tử trong collection theo kiểu phần tử. Khi đọc document, nó tạo collection và chuyển từng object lồng thành `ProductImage`.

Kiểu Java `List<ProductImage>` mô tả cấu trúc dữ liệu trong ứng dụng. Annotation `Object` hay `Nested` mô tả cách Elasticsearch hiểu cấu trúc đó khi lập chỉ mục và truy vấn.

### 5.3. Phân biệt `Object` và `Nested`

Đây là điểm quan trọng khi thiết kế mapping. `Object` và `Nested` đều có thể chứa object lồng nhau, nhưng cách Elasticsearch xử lý mảng object khác nhau.

Giả sử một đơn hàng có hai dòng:

~~~json
{
  "lines": [
    { "product": "Keyboard", "color": "Black" },
    { "product": "Mouse", "color": "White" }
  ]
}
~~~

Với mapping `object` thông thường, Elasticsearch có thể làm phẳng các giá trị field trong mảng object. Một truy vấn kết hợp `product = Keyboard` và `color = White` có nguy cơ khớp các giá trị đến từ hai phần tử khác nhau.

Nếu cần bảo toàn quan hệ giữa các field của từng phần tử khi truy vấn, dùng `nested`:

~~~java
@Field(type = FieldType.Nested)
private List<OrderLine> lines;
~~~

`Nested` có chi phí lưu trữ và truy vấn riêng, vì Elasticsearch xử lý từng phần tử nested như một document nội bộ độc lập. Chỉ chọn nested khi yêu cầu truy vấn cần giữ quan hệ giữa các field trong cùng một phần tử. Converter có thể chuyển đổi object/collection; ý nghĩa truy vấn vẫn do index mapping và loại query quyết định.

## 6. Multi-field và nhiều cách tìm kiếm một property

### 6.1. Vì sao cần multi-field?

Một chuỗi có thể cần được tìm theo nhiều cách. Ví dụ tên sản phẩm cần full-text search, đồng thời cần exact match hoặc sort theo toàn bộ chuỗi. Một field `text` được phân tích thường không phù hợp cho mọi nhu cầu đó.

Elasticsearch hỗ trợ multi-field: cùng một giá trị nguồn được lập chỉ mục theo nhiều cách dưới các field con.

### 6.2. Khai báo bằng `@MultiField`

Ví dụ khai báo tên sản phẩm có field chính kiểu `text` và subfield `keyword`:

~~~java
@MultiField(
    mainField = @Field(type = FieldType.Text, analyzer = "standard"),
    otherFields = {
        @InnerField(suffix = "keyword", type = FieldType.Keyword)
    }
)
private String name;
~~~

Mapping có thể tạo hai field tương ứng:

- `name`: dùng cho full-text search.
- `name.keyword`: dùng cho exact match, aggregation hoặc sort theo giá trị keyword.

Converter ghi giá trị property vào field nguồn; Elasticsearch index mapping xác định các subfield được lập chỉ mục. Bạn không cần khai báo hai property Java riêng chỉ để lưu hai cách phân tích của cùng một giá trị.

Hãy xác minh tên subfield và mapping thực tế đã được tạo trên cluster trước khi viết query. Annotation trong code là metadata đầu vào; index hiện có có thể chưa được cập nhật.

## 7. Chuyển đổi kiểu dữ liệu

### 7.1. Kiểu đơn giản và kiểu cần conversion

Converter hỗ trợ các kiểu Java phổ biến như chuỗi, số, boolean, enum, ngày giờ, collection, map và object lồng nhau theo các quy tắc mapping của Spring Data Elasticsearch.

Tuy nhiên, ứng dụng có thể có kiểu domain riêng không có biểu diễn trực tiếp phù hợp trong document. Ví dụ:

- `Money` gồm currency và amount.
- `EmailAddress` cần chuẩn hóa chữ thường.
- `Coordinate` cần chuyển thành cấu trúc mà ứng dụng thống nhất.
- Một value object cần lưu dưới dạng chuỗi hoặc object JSON theo quy ước riêng.

Với các kiểu như vậy, có thể đăng ký custom converter để định nghĩa cách ghi và đọc.

### 7.2. Custom writing converter và reading converter

Ví dụ ứng dụng có value object:

~~~java
public record Money(String currency, BigDecimal amount) {
}
~~~

Muốn lưu `Money` thành chuỗi như `USD 19.95`, tạo converter cho chiều ghi:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class MoneyToStringConverter implements Converter<Money, String> {

    @Override
    public String convert(Money source) {
        return source.currency() + " " + source.amount().toPlainString();
    }
}
~~~

Và converter cho chiều đọc:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class StringToMoneyConverter implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        String[] parts = source.split(" ", 2);

        if (parts.length != 2) {
            throw new IllegalArgumentException("Invalid money value: " + source);
        }

        return new Money(parts[0], new BigDecimal(parts[1]));
    }
}
~~~

`@WritingConverter` đánh dấu converter dùng khi ghi dữ liệu; `@ReadingConverter` đánh dấu converter dùng khi đọc dữ liệu. Việc chỉ rõ hướng giúp Spring Data lựa chọn conversion phù hợp, nhất là khi có nhiều converter liên quan đến các kiểu dữ liệu có thể chuyển đổi theo nhiều cách.

Converter thực tế nên xác thực dữ liệu đầu vào và xử lý định dạng lỗi theo quy ước của ứng dụng. Ví dụ trên chỉ minh họa một định dạng đơn giản; nếu dữ liệu có thể chứa khoảng trắng hoặc nhiều quy tắc tiền tệ, hãy dùng một định dạng ổn định hơn.

### 7.3. Đăng ký custom conversions

Các converter cần được đăng ký với `ElasticsearchCustomConversions` để Spring Data sử dụng:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.core.convert.ElasticsearchCustomConversions;

@Configuration
public class ElasticsearchConversionConfiguration {

    @Bean
    ElasticsearchCustomConversions elasticsearchCustomConversions() {
        return new ElasticsearchCustomConversions(List.of(
            new MoneyToStringConverter(),
            new StringToMoneyConverter()
        ));
    }
}
~~~

Trong cấu hình Spring Boot, bean custom conversions được sử dụng để cấu hình conversion service của Spring Data Elasticsearch. Nếu dự án tự tạo cấu hình Elasticsearch riêng, hãy bảo đảm custom conversions được gắn vào đúng mapping converter mà `ElasticsearchOperations` và repository đang sử dụng.

Không tạo một `MappingElasticsearchConverter` độc lập trong service chỉ để gọi thủ công. Làm vậy có thể khiến conversion rules của converter tự tạo khác với converter của repository.

### 7.4. Gắn custom type vào entity

Sau khi đăng ký conversion, entity có thể dùng `Money` như một property:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Keyword)
    private Money price;
}
~~~

Ví dụ trên giả định `Money` được chuyển thành một chuỗi như `USD 19.95`, do đó kiểu `Keyword` phù hợp nếu ứng dụng cần lưu và so khớp chuỗi biểu diễn đó. Nếu cần lọc theo amount hoặc currency riêng biệt, biểu diễn thành object có các field `amount` và `currency` thường phù hợp hơn; custom converter cần được thiết kế tương ứng.

Chọn biểu diễn dữ liệu theo cách ứng dụng truy vấn. Việc một value object có thể chuyển thành chuỗi không đồng nghĩa chuỗi luôn là mapping tốt nhất.

## 8. Constructor mapping và tạo object khi đọc

### 8.1. Converter phải tạo được instance Java

Khi đọc document, converter cần tạo instance của entity rồi gán các property. Với class mutable, constructor không tham số cùng setter hoặc field access có thể được dùng tùy cách mapping được cấu hình.

Với object immutable, constructor hoặc factory method có thể nhận các giá trị property để tạo instance:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private final String id;

    private final String name;

    public ProductDocument(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Spring Data cần xác định constructor phù hợp và ánh xạ các tham số với property. Tên tham số phải được giữ lại trong metadata biên dịch hoặc được chỉ rõ theo cơ chế mà Spring Data hỗ trợ.

### 8.2. `@PersistenceCreator`

Nếu class có nhiều constructor và Spring Data không thể xác định constructor nào dùng để tạo entity, có thể dùng `@PersistenceCreator` để đánh dấu constructor hoặc factory method phù hợp:

~~~java
@PersistenceCreator
public ProductDocument(String id, String name) {
    this.id = id;
    this.name = name;
}
~~~

Annotation này giúp việc tạo entity khi đọc dữ liệu trở nên rõ ràng. Nó không thay thế metadata cho property; kiểu và tên tham số vẫn phải tương ứng với dữ liệu cần ánh xạ.

Với Java record, các component cung cấp cấu trúc bất biến và constructor canonical. Spring Data hỗ trợ mapping cho record trong các phiên bản phù hợp; vẫn cần kiểm tra kiểu dữ liệu, tên field và custom conversion của từng component.

## 9. Type hints và kiểu dữ liệu đa hình

### 9.1. Vì sao cần type information?

Một property có thể được khai báo bằng interface hoặc class cha nhưng lúc chạy chứa nhiều kiểu con khác nhau. Khi ghi object, converter cần một cách để biết kiểu cụ thể nào đã được lưu. Khi đọc, thông tin kiểu có thể giúp tạo đúng subtype.

Spring Data Elasticsearch hỗ trợ lưu type hints trong document theo cấu hình mapping. Type hint thường được biểu diễn qua field metadata như `_class`; cách ghi và đọc phụ thuộc cấu hình type mapping và phiên bản thư viện.

Ví dụ một thuộc tính có kiểu khai báo là interface:

~~~java
public interface PaymentMethod {
}

public class CardPayment implements PaymentMethod {
    private String lastFourDigits;
}

public class BankTransfer implements PaymentMethod {
    private String bankCode;
}
~~~

Nếu document chứa `PaymentMethod`, converter cần đủ thông tin để khôi phục đúng kiểu cụ thể khi đọc. Nếu tắt hoặc loại bỏ type hint, ứng dụng phải có một quy tắc khác để xác định subtype, chẳng hạn field discriminator do domain tự quản lý.

### 9.2. Kiểm soát type hint

Không nên dựa vào type hint mà không hiểu tác động của nó. Type hint làm document có thêm thông tin kiểu của ứng dụng; điều đó có thể hữu ích cho polymorphic mapping nhưng cũng tạo liên hệ giữa dữ liệu lưu trữ và tên class/package.

Nếu dùng type alias hoặc thay đổi package/class name, cần xem xét dữ liệu đã lưu trước đó. Khi đổi cấu trúc class, các document cũ có thể vẫn chứa type information cũ. Hãy có chiến lược tương thích hoặc chuyển đổi dữ liệu khi cần.

Chỉ tắt type hint khi ứng dụng có cách khôi phục kiểu dữ liệu phù hợp. Với property cụ thể và không đa hình, việc đọc thường đơn giản hơn vì kiểu đích đã được xác định từ metadata của entity.

## 10. Metadata ứng dụng và index mapping trên cluster

### 10.1. Hai loại mapping có liên quan nhưng khác nhau

Cần tách biệt:

**Mapping metadata phía ứng dụng** là mô tả Spring Data thu thập từ class, property, annotation và conversion rules.

**Index mapping phía Elasticsearch** là cấu hình thực tế trên cluster, quyết định kiểu field, analyzer, dynamic behavior và cách dữ liệu được lập chỉ mục.

Converter sử dụng metadata phía ứng dụng để chuyển object và document. Elasticsearch sử dụng index mapping để xử lý dữ liệu. Hai bên cần thống nhất, nhưng một bên không tự động bảo đảm bên kia đã được cập nhật.

### 10.2. Annotation không tự sửa mapping cũ

Giả sử phiên bản đầu khai báo:

~~~java
@Field(type = FieldType.Text)
private String category;
~~~

Sau đó code đổi thành:

~~~java
@Field(type = FieldType.Keyword)
private String category;
~~~

Code mới có metadata `Keyword`, nhưng index hiện có có thể vẫn giữ mapping `text`. Elasticsearch không cho phép tùy ý đổi kiểu một field đã được tạo trong mapping hiện hữu theo cách này.

Cần lập kế hoạch thay đổi index, thường là tạo index mới với mapping mong muốn rồi reindex dữ liệu, sau đó chuyển alias hoặc cấu hình ứng dụng sang index mới. Chiến lược cụ thể phụ thuộc yêu cầu downtime, dung lượng và cách triển khai.

### 10.3. Kiểm tra mapping thực tế

Khi truy vấn cho kết quả không như mong đợi, hãy kiểm tra mapping của index trực tiếp trên Elasticsearch. Đừng chỉ đọc annotation trong Java rồi kết luận cluster đang có cấu hình giống hệt.

Có thể gọi mapping API bằng HTTP:

~~~http
GET /products/_mapping
~~~

Response cho biết kiểu field và các tùy chọn mapping mà cluster đang sử dụng. So sánh với metadata Java để tìm khác biệt về tên field, kiểu field, analyzer, date format hoặc nested structure.

### 10.4. Dynamic mapping

Nếu index cho phép dynamic mapping, Elasticsearch có thể tự suy luận kiểu field khi gặp field mới. Điều này hữu ích khi bắt đầu thử nghiệm, nhưng có thể dẫn đến mapping không mong muốn nếu dữ liệu đầu vào không nhất quán.

Ví dụ, một document đầu tiên gửi `price` dưới dạng số, nhưng một document khác gửi cùng field dưới dạng chuỗi. Mapping đã được tạo trước đó có thể khiến document sau bị từ chối hoặc chuyển đổi không như mong muốn.

Khai báo metadata tường minh và thiết kế mapping trước thường giúp hệ thống ổn định hơn. Dynamic mapping nên được sử dụng có chủ đích, đặc biệt với dữ liệu có cấu trúc thay đổi.

## 11. Luồng ghi và đọc chi tiết

### 11.1. Khi ghi object

Khi ứng dụng gọi `save()` hoặc thao tác ghi tương ứng, luồng khái niệm diễn ra như sau:

1. Repository hoặc `ElasticsearchOperations` nhận object Java.
2. Spring Data xác định entity metadata từ mapping context.
3. `MappingElasticsearchConverter` duyệt các property cần ghi.
4. Converter xác định tên field và quy tắc mapping từ metadata.
5. Giá trị được chuyển đổi theo kiểu dữ liệu và custom conversions đã đăng ký.
6. Object lồng nhau, collection và type information được xử lý theo metadata tương ứng.
7. Converter tạo biểu diễn document cho thao tác ghi.
8. Elasticsearch client gửi request đến cluster.
9. Elasticsearch áp dụng index mapping để lưu và lập chỉ mục document.

### 11.2. Khi đọc document

Khi tìm kiếm hoặc đọc theo ID:

1. Elasticsearch trả document trong response.
2. Spring Data nhận biểu diễn document từ client.
3. `MappingElasticsearchConverter` tra cứu metadata entity đích.
4. Converter xác định constructor hoặc cơ chế tạo instance phù hợp.
5. Các field được đọc theo tên và kiểu đã khai báo.
6. Custom reading converters được áp dụng khi cần.
7. Object lồng nhau, collection và subtype được khôi phục theo metadata.
8. Spring Data trả object Java cho repository hoặc operations.

Nếu một property không thể chuyển đổi, quá trình đọc có thể thất bại. Khi đó cần kiểm tra dữ liệu thực tế trong index, kiểu Java, annotation và custom converter liên quan.

## 12. Các lỗi mapping thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Field trong document có tên khác dự kiến | `@Field(name = "...")` hoặc quy ước tên không khớp | Kiểm tra metadata và `_source` thực tế |
| Lỗi chuyển đổi kiểu khi đọc | Dữ liệu cũ không tương thích kiểu Java hiện tại | Kiểm tra document, custom converter và lịch sử thay đổi schema |
| Không khôi phục được subtype | Thiếu hoặc không tương thích type information | Kiểm tra type hint hoặc discriminator của domain |
| Query không khớp dù object đã lưu | Index mapping/analyzer khác metadata Java | Kiểm tra mapping API và analyzer |
| Property không xuất hiện trong document | Property transient hoặc không được mapping | Kiểm tra `@Transient`, accessor và metadata |
| Object lồng nhau được truy vấn sai | Dùng `object` khi yêu cầu cần `nested` | Thiết kế lại mapping và query phù hợp |
| Thay `Text` thành `Keyword` nhưng query vẫn sai | Index cũ vẫn giữ mapping cũ | Tạo mapping/index mới và reindex nếu cần |
| Custom converter không được áp dụng | Converter chưa được đăng ký vào conversion configuration đang dùng | Kiểm tra bean `ElasticsearchCustomConversions` và client/operations configuration |
| Giá trị ngày giờ bị lỗi | Format hoặc timezone không thống nhất | Kiểm tra Java time type, date format và dữ liệu đã index |

Khi xử lý lỗi, hãy lần theo dữ liệu qua các lớp: object Java, metadata, document được converter tạo ra, request được gửi và mapping thực tế trên cluster. Cách này giúp xác định lỗi nằm ở conversion hay ở cấu hình index/query.

## 13. Thực hành tổng hợp

Giả sử cần ánh xạ sản phẩm có ID, tên, danh mục, giá và thương hiệu. Một ví dụ entity:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @MultiField(
        mainField = @Field(type = FieldType.Text, analyzer = "standard"),
        otherFields = {
            @InnerField(suffix = "keyword", type = FieldType.Keyword)
        }
    )
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Object)
    private BrandDocument brand;

    public ProductDocument() {
    }

    // Constructor, getter và setter được lược bớt.
}
~~~

Khi lưu object, converter sử dụng metadata để:

- Đưa `id` vào định danh document.
- Ghi `name` theo field chính và mapping multi-field.
- Ghi `category` như giá trị keyword.
- Chuyển `price` thành giá trị số.
- Chuyển `brand` thành object lồng nhau theo metadata của `BrandDocument`.

Sau khi lưu, có thể kiểm tra document và mapping trên cluster để xác nhận dữ liệu thực tế phù hợp với thiết kế.

Bạn có thể tự mở rộng bài thực hành bằng cách thêm property `createdAt` kiểu `Instant`, một collection `images`, hoặc value object `Money` với custom converter. Mỗi lần thêm property, hãy quyết định ba điều: biểu diễn Java là gì, metadata ánh xạ ra sao và truy vấn Elasticsearch cần thực hiện trên field đó như thế nào.

## 14. Những điểm cần ghi nhớ khi làm việc với converter

- `MappingElasticsearchConverter` chuyển đổi object Java và document theo hai chiều.
- Mapping context quản lý metadata entity/property để converter sử dụng.
- `@Document` mô tả entity và index; `@Id` mô tả định danh; `@Field` mô tả field mapping.
- `@Transient` loại property khỏi mapping thông thường.
- Object, collection, nested và multi-field cần được thiết kế theo mục đích truy vấn.
- Custom reading/writing converters dùng cho kiểu domain cần biểu diễn riêng.
- Constructor mapping và type hints ảnh hưởng đến khả năng khôi phục object.
- Metadata Java không đồng nghĩa index mapping trên cluster đã được cập nhật.
- Thay đổi kiểu field hiện có thường cần chiến lược tạo index mới và reindex.
- Repository và `ElasticsearchOperations` nên dùng chung cấu hình converter do Spring quản lý.

Khi hiểu được converter và metadata, bạn có thể đọc các annotation mapping, dự đoán dữ liệu Java sẽ trở thành document như thế nào và tìm nguyên nhân khi kết quả đọc/ghi khác với mong đợi. Đây là nền tảng để tiếp tục thiết kế mapping, truy vấn và xử lý document phức tạp trong Spring Data Elasticsearch.
