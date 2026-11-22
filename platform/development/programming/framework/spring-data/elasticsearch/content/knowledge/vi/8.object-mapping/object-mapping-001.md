# Quy trình chuyển Java object sang Document và đọc ngược

Spring Data Elasticsearch giúp ứng dụng làm việc với document Elasticsearch bằng các đối tượng Java. Khi lưu một entity, framework chuyển các thuộc tính Java thành cấu trúc document phù hợp với index. Khi đọc kết quả, framework chuyển dữ liệu document trở lại kiểu Java mà ứng dụng yêu cầu.

Thành phần trung tâm của quá trình này là MappingElasticsearchConverter. Converter sử dụng metadata của entity, các annotation ánh xạ và hệ thống custom conversions để quyết định tên field, kiểu dữ liệu, cách xử lý object lồng nhau và cách khôi phục giá trị khi đọc.

Hiểu luồng chuyển đổi giúp giải thích vì sao một thuộc tính Java có thể trở thành một field Elasticsearch khác tên, vì sao ID không nằm trong phần JSON source, vì sao kiểu ngày giờ cần quy ước rõ ràng và cách mở rộng converter khi có kiểu dữ liệu nghiệp vụ riêng.

## 1. Java object, Document và Elasticsearch _source

Ba khái niệm thường được nhắc đến khi chuyển đổi dữ liệu:

- **Java object:** đối tượng trong bộ nhớ, ví dụ Product hoặc Order.
- **Spring Data Document:** cấu trúc document dạng map mà Spring Data dùng trong tầng chuyển đổi và thao tác dữ liệu.
- **Elasticsearch _source:** nội dung JSON được lưu cho document trong index, thường chứa các field nghiệp vụ.

Ví dụ Java object:

~~~java
public class Product {

    private String id;
    private String name;
    private BigDecimal price;
    private List<String> tags;

    // constructors, getters and setters
}
~~~

Document logic có thể có cấu trúc tương tự:

~~~json
{
  "name": "Mechanical Keyboard",
  "price": 89.90,
  "tags": ["keyboard", "peripheral"]
}
~~~

Khi ghi vào Elasticsearch, nội dung nghiệp vụ này thường trở thành phần _source. Document còn có metadata do Elasticsearch quản lý, chẳng hạn _id, routing, version hoặc thông tin sequence number. Những metadata đó không nhất thiết nằm trong JSON _source.

Vì vậy không nên đồng nhất toàn bộ Elasticsearch hit với phần _source. Một search hit có thể gồm:

~~~text
SearchHit
  ├── _index
  ├── _id
  ├── _score
  ├── _routing (nếu có)
  └── _source
        ├── name
        ├── price
        └── tags
~~~

Spring Data phối hợp converter với tầng truy cập Elasticsearch để ánh xạ cả dữ liệu entity lẫn metadata cần thiết.

## 2. Vai trò của MappingElasticsearchConverter

MappingElasticsearchConverter là thành phần chuyển đổi giữa object Java và Document. Nó hoạt động dựa trên Elasticsearch mapping metadata, thường được cung cấp qua ElasticsearchMappingContext.

Các thành phần chính có thể hình dung như sau:

~~~text
Java entity
    |
    v
ElasticsearchMappingContext
    |
    | mô tả entity, property, annotation
    v
MappingElasticsearchConverter
    |
    | ghi object thành Document
    | đọc Document thành object
    v
Spring Data Document
    |
    v
ElasticsearchOperations / Repository
    |
    v
Elasticsearch Java Client
    |
    v
Elasticsearch index
~~~

MappingElasticsearchConverter chịu trách nhiệm chuyển đổi dữ liệu theo metadata. ElasticsearchOperations hoặc repository chịu trách nhiệm thực hiện thao tác lưu, lấy, tìm kiếm và kết nối với Elasticsearch.

Không nên xem converter là một JSON serializer tổng quát. Nó hiểu metadata của Spring Data Elasticsearch như @Id, @Field, @Document, cấu trúc entity và các custom converters đã đăng ký. Điều này khác với việc dùng Jackson để tuần tự hóa một DTO cho REST API.

### 2.1. ElasticsearchMappingContext

Mapping context giữ thông tin ánh xạ của các entity được Spring Data quản lý:

- Tên và kiểu của entity.
- Thuộc tính nào là ID.
- Tên field Elasticsearch tương ứng.
- Kiểu field được khai báo qua @Field.
- Cấu trúc object lồng nhau và collection.
- Metadata cần cho việc tạo và đọc entity.

Mapping context được xây dựng từ class Java và annotation. Khi converter xử lý Product, nó có thể biết id là ID, name là text, category là keyword hoặc một thuộc tính được đổi tên bằng @Field(name = "...").

### 2.2. Custom conversions

Custom conversions cho phép ứng dụng chỉ định cách chuyển kiểu nghiệp vụ riêng sang kiểu mà Elasticsearch có thể lưu, và cách khôi phục kiểu đó khi đọc.

Ví dụ, một kiểu EmailAddress có thể được lưu thành chuỗi keyword. Converter ghi sẽ lấy giá trị chuỗi; converter đọc sẽ tạo lại EmailAddress từ chuỗi đó.

## 3. Khai báo entity và metadata ánh xạ

Hãy bắt đầu từ một entity có metadata tường minh:

~~~java
import java.math.BigDecimal;
import java.util.List;

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

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Keyword)
    private List<String> tags;

    // constructors, getters and setters
}
~~~

Metadata quyết định cách converter xử lý từng thuộc tính:

| Thuộc tính Java | Metadata | Ý nghĩa khi chuyển đổi |
|---|---|---|
| id | @Id | Ánh xạ thành Elasticsearch document ID |
| name | FieldType.Text | Lưu giá trị văn bản để tìm kiếm toàn văn |
| category | FieldType.Keyword | Lưu giá trị chính xác để lọc hoặc aggregation |
| price | FieldType.Double | Chuyển giá trị số sang kiểu số phù hợp trong document |
| tags | FieldType.Keyword | Chuyển collection thành danh sách giá trị keyword |

Annotation @Field điều khiển mapping của field. Converter chịu trách nhiệm chuyển giá trị Java tương ứng vào Document. Việc một field có kiểu text hay keyword chủ yếu ảnh hưởng mapping và hành vi tìm kiếm của Elasticsearch; nó không có nghĩa converter tự phân tích ngôn ngữ của chuỗi.

Nếu không khai báo một số metadata, Spring Data có thể suy luận mapping theo kiểu Java và quy tắc mặc định. Với field quan trọng cho tìm kiếm, lọc hoặc sắp xếp, nên khai báo tường minh để hợp đồng dữ liệu dễ hiểu và ổn định.

## 4. Quy trình ghi: Java object sang Document

Khi gọi repository.save(product) hoặc ElasticsearchOperations.save(product), Spring Data thực hiện một chuỗi bước ở mức khái niệm.

### 4.1. Nhận entity và xác định metadata

Ứng dụng đưa object Product vào tầng repository hoặc operations. Spring Data xác định entity type, đọc metadata tương ứng từ mapping context và tìm thông tin index đích từ @Document.

Ví dụ:

~~~java
Product product = new Product();
product.setId("product-100");
product.setName("Mechanical Keyboard");
product.setCategory("peripherals");
product.setPrice(new BigDecimal("89.90"));
product.setTags(List.of("keyboard", "office"));

productRepository.save(product);
~~~

Repository biết entity Product tương ứng với index products. ID và field mapping được lấy từ metadata.

### 4.2. Duyệt thuộc tính và chuyển giá trị

Converter đọc từng persistent property và chuyển giá trị:

- Thuộc tính ID được xử lý như document ID.
- Kiểu đơn giản như String, Boolean và số được chuyển thành giá trị tương ứng.
- Enum được chuyển theo quy tắc conversion đã cấu hình.
- Date/time được chuyển theo converter và kiểu Java được hỗ trợ.
- Collection được chuyển thành danh sách giá trị hoặc danh sách object.
- Map được chuyển thành cấu trúc key/value phù hợp.
- Object lồng nhau được chuyển thành cấu trúc document con.
- Custom converter được áp dụng khi kiểu thuộc tính có conversion đã đăng ký.

Nếu một property có tên field khác tên thuộc tính Java, metadata sẽ hướng converter ghi vào tên field đã cấu hình.

### 4.3. Xây dựng Document

Với entity ví dụ, phần source có thể tương đương:

~~~json
{
  "name": "Mechanical Keyboard",
  "category": "peripherals",
  "price": 89.90,
  "tags": ["keyboard", "office"]
}
~~~

Giá trị id thường được dùng làm _id của document trong Elasticsearch, không nhất thiết xuất hiện trong _source. Khi cần lấy ID từ kết quả, tầng mapping và operations kết hợp metadata của hit để gán lại vào thuộc tính @Id.

### 4.4. Gửi request đến Elasticsearch

Sau khi có Document, tầng operations sử dụng index đích và metadata liên quan để tạo request ghi. Elasticsearch nhận document, áp dụng mapping của index và lập chỉ mục dữ liệu.

Điều này có nghĩa có hai lớp quy tắc:

- Spring Data mapping quyết định cách Java object được chuyển thành dữ liệu document.
- Elasticsearch mapping quyết định cách Elasticsearch hiểu, lập chỉ mục và truy vấn từng field.

Hai lớp phải tương thích. Converter có thể ghi được một giá trị JSON nhưng Elasticsearch vẫn từ chối nếu giá trị đó không phù hợp mapping, ví dụ chuỗi ngày sai format hoặc object không phù hợp kiểu field đã khai báo.

## 5. Quy trình đọc: Document sang Java object

Khi ứng dụng lấy một document theo ID hoặc tìm kiếm, Elasticsearch trả về các hit. Mỗi hit có metadata và phần source. Spring Data dùng mapping context cùng converter để tạo object thuộc kiểu ứng dụng yêu cầu.

### 5.1. Lấy dữ liệu từ Elasticsearch

Ví dụ dùng repository:

~~~java
Optional<Product> result = productRepository.findById("product-100");

result.ifPresent(product -> {
    System.out.println(product.getName());
    System.out.println(product.getPrice());
});
~~~

Hoặc dùng ElasticsearchOperations khi cần chỉ định rõ index:

~~~java
Product product = operations.get(
        "product-100",
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Chữ ký API cụ thể có thể khác giữa các release train; hãy dùng overload có trong phiên bản Spring Data Elasticsearch của dự án.

### 5.2. Đọc source và metadata

Elasticsearch trả về _source cùng metadata của hit. Tầng Spring Data tạo cấu trúc Document cho converter và cung cấp thông tin ID hoặc metadata khác theo API tương ứng.

Converter không thể suy luận mọi kiểu Java chỉ từ JSON. Nó cần kiểu đích Product và metadata mapping để biết cách dựng đối tượng.

### 5.3. Tạo object đích

MappingElasticsearchConverter đọc từng field:

- Tìm persistent property tương ứng với tên field.
- Chuyển kiểu dữ liệu từ giá trị Document sang kiểu Java.
- Tạo object lồng nhau và collection nếu có.
- Khôi phục thuộc tính ID từ metadata document.
- Áp dụng custom reading converter nếu kiểu property yêu cầu.
- Khởi tạo entity qua constructor hoặc cơ chế property access phù hợp với metadata.

Kết quả là một object Java mà ứng dụng có thể tiếp tục sử dụng:

~~~text
Elasticsearch hit
      |
      v
Document source + metadata
      |
      v
MappingElasticsearchConverter
      |
      | tìm metadata Product
      | chuyển từng field
      | dựng nested object
      | khôi phục ID
      v
Product Java object
~~~

## 6. Ánh xạ tên field và ID

### 6.1. Đổi tên field

Tên thuộc tính Java không bắt buộc phải trùng tên field Elasticsearch. Có thể dùng thuộc tính name của @Field:

~~~java
@Field(name = "product_name", type = FieldType.Text)
private String name;
~~~

Khi ghi, converter sử dụng product_name làm tên field trong Document. Khi đọc, converter tìm product_name và gán giá trị cho thuộc tính name.

Điều này hữu ích khi API hoặc index đã có quy ước snake_case, trong khi mã Java dùng camelCase.

### 6.2. ID là metadata riêng

Thuộc tính được đánh dấu @Id được Spring Data sử dụng làm Elasticsearch document ID. ID giúp định vị document cho các thao tác get, update và delete.

Ví dụ:

~~~java
@Id
private String id;
~~~

ID không cần lặp lại trong _source nếu ứng dụng chỉ cần nó như document identity. Nếu nghiệp vụ cũng cần truy vấn ID như một field thông thường, có thể lưu thêm một thuộc tính dữ liệu riêng hoặc thiết kế field phù hợp, nhưng cần tránh nhầm field nghiệp vụ với metadata _id.

Nếu entity chưa có ID, hành vi tạo ID phụ thuộc thao tác và API được dùng. Elasticsearch có thể sinh ID cho thao tác index không chỉ định ID; ứng dụng cần kiểm tra cách ID được trả về và gán lại vào entity trong phiên bản Spring Data đang dùng. Với repository CRUD thông thường, nên xác định rõ chiến lược ID thay vì dựa vào giả định về giá trị null.

## 7. Chuyển đổi object lồng nhau và collection

Document Elasticsearch có thể chứa object lồng nhau. Spring Data converter có thể chuyển đổi các kiểu object và collection thành cấu trúc tương ứng.

Ví dụ:

~~~java
public class Manufacturer {

    private String name;
    private String country;

    // constructors, getters and setters
}

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String name;

    private Manufacturer manufacturer;

    private List<String> tags;

    // constructors, getters and setters
}
~~~

Document source có thể có cấu trúc:

~~~json
{
  "name": "Mechanical Keyboard",
  "manufacturer": {
    "name": "Example Devices",
    "country": "VN"
  },
  "tags": ["keyboard", "office"]
}
~~~

Khi đọc, converter dựng Manufacturer và danh sách tags từ các cấu trúc con. Khi ghi, converter duyệt object con và chuyển các thuộc tính của nó thành map lồng nhau.

### 7.1. Object và nested là hai khái niệm khác nhau

Trong Elasticsearch, object field và nested field có cách truy vấn khác nhau. Nếu một field là object, các giá trị bên trong có thể được làm phẳng khi lập chỉ mục. Với một mảng object, việc tìm nhiều điều kiện có thể vô tình khớp các thuộc tính thuộc những phần tử khác nhau.

Kiểu nested duy trì ranh giới từng object con để truy vấn nested query chính xác hơn, đổi lại có chi phí lưu trữ và truy vấn riêng.

Có thể khai báo:

~~~java
@Field(type = FieldType.Nested)
private List<OrderLine> lines;
~~~

Converter chuyển đổi cấu trúc Java thành document lồng nhau; mapping Elasticsearch xác định field đó là nested. Chỉ dùng FieldType.Nested khi yêu cầu truy vấn cần ngữ nghĩa nested. Không phải cứ có List object là luôn phải chọn nested.

## 8. Kiểu dữ liệu phổ biến và chuyển đổi

Một số kiểu Java thường được ánh xạ như sau:

| Kiểu Java | Giá trị document thường gặp | Lưu ý |
|---|---|---|
| String | Chuỗi | Mapping text hoặc keyword quyết định cách lập chỉ mục |
| Boolean | true/false | Dùng field boolean |
| Integer, Long | Số nguyên | Chọn kiểu số phù hợp với miền giá trị |
| Double, BigDecimal | Số | Cân nhắc precision và mapping số |
| Enum | Giá trị biểu diễn enum theo conversion | Nên thống nhất lưu tên hay mã nghiệp vụ |
| Instant | Timestamp | Chọn date hoặc date_nanos theo độ chính xác |
| LocalDate | Ngày lịch | Cần phân biệt ngày lịch với thời điểm tuyệt đối |
| Collection | Mảng giá trị hoặc object | Mapping field phải phù hợp nội dung |
| Map | Object key/value | Cần kiểm soát cấu trúc key và kiểu value |

Converter chuyển kiểu Java sang giá trị mà Document có thể biểu diễn. Elasticsearch mapping tiếp tục quyết định cách lưu và truy vấn giá trị đó. Ví dụ BigDecimal có thể được chuyển thành giá trị số, nhưng độ chính xác của phép tính và kiểu numeric mapping vẫn cần được thiết kế phù hợp với nghiệp vụ tiền tệ.

## 9. Custom conversions cho kiểu nghiệp vụ riêng

Không phải kiểu Java nào cũng có thể chuyển đổi đúng theo quy tắc mặc định. Khi có kiểu riêng như EmailAddress, Money, PhoneNumber hoặc một value object, có thể đăng ký converter ghi và converter đọc.

Ví dụ value object:

~~~java
public record EmailAddress(String value) {
}
~~~

Converter ghi:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class EmailAddressWritingConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}
~~~

Converter đọc:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class EmailAddressReadingConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

Khi ghi, EmailAddress được chuyển thành chuỗi. Khi đọc, chuỗi được chuyển ngược thành EmailAddress. Field có thể được khai báo là keyword nếu ứng dụng cần lọc hoặc so khớp chính xác:

~~~java
@Field(type = FieldType.Keyword)
private EmailAddress email;
~~~

### 9.1. Đăng ký custom conversions

Spring Data Elasticsearch cung cấp ElasticsearchCustomConversions để đăng ký converter bổ sung. Cách khai báo bean có thể khác đôi chút theo phiên bản và cấu hình ứng dụng, nhưng ý tưởng là cung cấp danh sách converter cho hạ tầng mapping:

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
                new EmailAddressWritingConverter(),
                new EmailAddressReadingConverter()
        ));
    }
}
~~~

Hãy kiểm tra package, constructor và cách Spring Boot phát hiện bean theo đúng release train của dự án. Các converter phải được đăng ký vào đúng Elasticsearch converter infrastructure; chỉ tạo class Converter mà không đăng ký thì không bảo đảm nó được sử dụng.

### 9.2. Khi nào nên dùng custom converter?

Nên dùng custom converter khi:

- Kiểu nghiệp vụ không có cách biểu diễn mặc định phù hợp.
- Muốn kiểm soát rõ format ghi và đọc.
- Cần duy trì tương thích với dữ liệu cũ.
- Muốn chuẩn hóa value object ở một nơi thay vì lặp logic trong service.

Không nên viết converter cho mọi kiểu dữ liệu đơn giản nếu Spring Data đã hỗ trợ tốt. Mỗi converter là một phần của hợp đồng dữ liệu và cần được kiểm thử cả hai chiều.

## 10. Constructor, property access và bất biến của entity

Đọc Document thành Java object không chỉ là gán từng field sau khi gọi constructor rỗng. Spring Data có cơ chế entity instantiation và property population dựa trên metadata.

Với entity có constructor phù hợp, Spring Data có thể dùng constructor để tạo đối tượng từ các giá trị đã đọc. Điều này hỗ trợ các lớp bất biến hoặc value object. Tên tham số constructor, metadata và cách truy cập property phải phù hợp với cấu hình mapping của dự án.

Ví dụ:

~~~java
@Document(indexName = "products")
public class ProductSummary {

    @Id
    private final String id;

    private final String name;

    public ProductSummary(String id, String name) {
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

Trong thực tế, hãy bảo đảm Spring Data có đủ metadata để liên kết giá trị document với constructor parameter. Nếu dùng Lombok, record hoặc constructor nhiều tham số, kiểm tra cách compiler lưu parameter name và quy tắc mapping của phiên bản đang dùng.

Không nên thay đổi constructor hoặc tên property một cách tùy tiện khi dữ liệu đã được lưu lâu dài. Một thay đổi trong entity có thể làm thay đổi cách đọc document cũ, dù dữ liệu trong Elasticsearch không đổi.

## 11. Type hints và kiểu đích khi đọc

Một document JSON không phải lúc nào cũng chứa đủ thông tin để khôi phục chính xác kiểu Java ban đầu. Ví dụ, một property khai báo bằng interface có thể nhận nhiều implementation khác nhau. Spring Data có thể sử dụng type information trong document để biết kiểu cụ thể khi đọc.

Trong một số cấu hình, type hint có thể được ghi dưới field metadata như _class. Cơ chế type mapping và alias có thể được tùy chỉnh. Nếu ứng dụng tắt type hints hoặc lưu document từ hệ thống khác không có metadata kiểu Java, nên đọc vào một kiểu đích cụ thể hoặc tự định nghĩa quy tắc xác định subtype.

Không nên coi _class là field nghiệp vụ hoặc dùng nó làm cơ chế phân quyền. Đây là metadata phục vụ mapping và cần được xem xét khi chia sẻ index giữa nhiều ứng dụng hoặc nhiều phiên bản model.

## 12. SearchHit, SearchHits và object đã chuyển đổi

Khi tìm kiếm, Spring Data có thể trả về SearchHits<T> thay vì chỉ một danh sách entity. Mỗi SearchHit<T> chứa entity đã được converter dựng cùng metadata tìm kiếm như score, ID, index và routing nếu có.

Ví dụ minh họa:

~~~java
SearchHits<Product> searchHits =
        operations.search(
                query,
                Product.class,
                IndexCoordinates.of("products")
        );

for (SearchHit<Product> hit : searchHits) {
    Product product = hit.getContent();

    System.out.println(product.getName());
    System.out.println(hit.getScore());
    System.out.println(hit.getId());
}
~~~

Chữ ký phương thức tạo query và search có thể thay đổi theo phiên bản Spring Data Elasticsearch. Điểm cần nhớ là nội dung hit đã được chuyển thành Product, còn score và một số thông tin khác nằm ở lớp SearchHit.

Nếu chỉ lấy danh sách entity, ứng dụng có thể dùng API tiện ích chuyển SearchHits thành danh sách content. Khi cần relevance, highlight, sort values hoặc metadata, nên giữ SearchHits để không làm mất thông tin của kết quả tìm kiếm.

## 13. Mapping converter khác Jackson JSON serialization như thế nào?

Hai cơ chế đều có thể tạo JSON hoặc chuyển dữ liệu, nhưng mục tiêu khác nhau:

| Tiêu chí | MappingElasticsearchConverter | Jackson ObjectMapper |
|---|---|---|
| Mục đích | Chuyển entity Spring Data sang Document Elasticsearch và đọc ngược | Tuần tự hóa/giải tuần tự hóa JSON tổng quát |
| Metadata | Dùng @Document, @Id, @Field và mapping context | Dùng Jackson annotations và module |
| Index target | Kết hợp metadata entity với operations | Không tự biết index Elasticsearch |
| Elasticsearch ID | Tầng Spring Data phối hợp ID metadata | Thường chỉ xử lý property JSON theo cấu hình |
| Mapping field | Có thể phản ánh kiểu field Elasticsearch | Không tự thiết kế mapping index |
| Custom conversion | ElasticsearchCustomConversions và conversion infrastructure | Jackson serializers/deserializers |

Nếu controller trả Product thành JSON HTTP response, ứng dụng có thể dùng Jackson. Nếu Product được lưu vào Elasticsearch qua repository hoặc ElasticsearchOperations, Spring Data dùng mapping converter của nó.

Không nên dùng ObjectMapper serialize entity rồi gửi chuỗi JSON vào Elasticsearch và cho rằng toàn bộ metadata @Field, @Id hoặc custom conversions sẽ tự động được áp dụng. Nếu chọn cách thao tác JSON cấp thấp, ứng dụng phải tự chịu trách nhiệm về mapping và metadata.

## 14. Kiểm soát lỗi chuyển đổi

Quá trình chuyển đổi có thể thất bại ở hai phía:

**Khi ghi:**

- Giá trị Java không có converter phù hợp.
- Custom converter ném exception.
- Dữ liệu chuyển đổi không phù hợp mapping của Elasticsearch.
- Field date có chuỗi hoặc đơn vị thời gian sai.
- Object lồng nhau có cấu trúc không hợp lệ.

**Khi đọc:**

- Document cũ thiếu field mà entity mới yêu cầu.
- Giá trị field không chuyển được sang kiểu Java đích.
- Custom reading converter không xử lý được dữ liệu cũ.
- Type hint không còn khớp với class hiện tại.
- Mapping hoặc tên field thay đổi nhưng entity chưa được cập nhật tương thích.

Khi thiết kế entity, hãy cân nhắc khả năng tương thích ngược. Một index có thể chứa document được ghi bởi nhiều phiên bản ứng dụng. Entity mới cần đọc được dữ liệu cũ hoặc phải có migration để chuẩn hóa trước khi deploy.

Đừng giả định mọi field đều luôn có mặt. Nếu dữ liệu được bổ sung theo thời gian, cần xác định field nào bắt buộc, field nào có thể null hoặc có default trong constructor và service.

## 15. Kiểm thử hai chiều của mapping

Mapping cần được kiểm thử cả write và read. Chỉ kiểm tra rằng save không ném exception chưa đủ để bảo đảm document có cấu trúc mong muốn.

Một số nội dung nên kiểm tra:

1. Entity được ghi vào đúng index.
2. @Id được ánh xạ thành đúng document ID.
3. Tên field khớp mapping, bao gồm các field đổi tên.
4. Kiểu số, boolean, date và collection có giá trị mong đợi.
5. Object lồng nhau và nested field có cấu trúc đúng.
6. Custom converter ghi đúng định dạng và converter đọc khôi phục đúng kiểu.
7. Entity đọc lại giữ được các giá trị quan trọng.
8. SearchHit vẫn cung cấp ID, score và metadata cần thiết.
9. Document cũ hoặc thiếu field được xử lý theo quy ước tương thích.

Ví dụ kiểm thử tích hợp khái niệm:

~~~java
Product saved = productRepository.save(product);

Optional<Product> loaded =
        productRepository.findById(saved.getId());

assertThat(loaded).isPresent();
assertThat(loaded.get().getName()).isEqualTo(product.getName());
assertThat(loaded.get().getCategory()).isEqualTo(product.getCategory());
~~~

Để kiểm tra cấu trúc _source và mapping thật, có thể dùng Elasticsearch client hoặc REST API trong test. Việc này giúp phát hiện trường hợp entity được dựng lại đúng nhưng mapping của index chưa đúng với truy vấn dự kiến.

## 16. Ví dụ tổng hợp: chuyển đổi Product theo hai chiều

Entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(name = "product_name", type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Keyword)
    private List<String> tags;

    // constructors, getters and setters
}
~~~

Lưu object:

~~~java
Product product = new Product(
        "product-100",
        "Mechanical Keyboard",
        "peripherals",
        new BigDecimal("89.90"),
        List.of("keyboard", "office")
);

productRepository.save(product);
~~~

Phần source mong đợi:

~~~json
{
  "product_name": "Mechanical Keyboard",
  "category": "peripherals",
  "price": 89.90,
  "tags": ["keyboard", "office"]
}
~~~

Đọc lại:

~~~java
Product loaded = productRepository.findById("product-100")
        .orElseThrow();

System.out.println(loaded.getId());
System.out.println(loaded.getName());
System.out.println(loaded.getPrice());
~~~

Converter dùng tên field product_name để gán lại cho thuộc tính Java name. ID được khôi phục từ metadata của document. Các giá trị category, price và tags được chuyển về kiểu tương ứng theo metadata.

Luồng tổng hợp:

~~~text
Product Java object
       |
       | repository.save()
       v
MappingElasticsearchConverter
       |
       | @Id, @Field, nested values,
       | custom conversions
       v
Spring Data Document
       |
       v
Elasticsearch _source + metadata

Elasticsearch hit
       |
       v
Spring Data Document + hit metadata
       |
       v
MappingElasticsearchConverter
       |
       | target type Product
       | convert fields and nested values
       | restore ID
       v
Product Java object
~~~

## 17. Kết luận

Quy trình chuyển Java object sang Elasticsearch Document và đọc ngược được điều phối bởi MappingElasticsearchConverter cùng metadata từ ElasticsearchMappingContext. Metadata xác định entity, ID, tên field, kiểu field và cấu trúc object; custom conversions mở rộng cách chuyển đổi cho kiểu nghiệp vụ riêng.

Khi ghi, Spring Data đọc metadata, chuyển từng thuộc tính và tạo Document để operations gửi đến Elasticsearch. Khi đọc, framework nhận source cùng metadata của hit, chuyển field sang kiểu Java và dựng object đích. Elasticsearch mapping tiếp tục quyết định cách dữ liệu được lập chỉ mục và truy vấn.

Hãy thiết kế entity và mapping như một hợp đồng dữ liệu hai chiều. Kiểm tra cả cấu trúc document được ghi lẫn object khôi phục được, giữ quy tắc tương thích với dữ liệu cũ và chỉ bổ sung custom converter khi có nhu cầu chuyển đổi rõ ràng.
