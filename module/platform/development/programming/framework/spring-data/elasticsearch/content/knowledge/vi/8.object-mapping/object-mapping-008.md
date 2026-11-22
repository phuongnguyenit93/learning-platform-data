# Giới hạn của cấu hình Jackson đối với cơ chế mapping của Spring Data

Jackson là thư viện phổ biến trong hệ sinh thái Java để chuyển đổi object thành JSON và ngược lại. Trong ứng dụng Spring Boot, Jackson thường được dùng để đọc request HTTP, tạo response JSON, xử lý DTO và serialize dữ liệu. Vì vậy, khi một ứng dụng dùng Spring Data Elasticsearch, nhiều người kỳ vọng rằng các annotation như `@JsonProperty`, `@JsonIgnore`, `@JsonFormat` hoặc cấu hình `ObjectMapper` cũng sẽ điều khiển cách entity được lưu vào Elasticsearch.

Kỳ vọng đó không đúng với luồng mapping thông thường của Spring Data Elasticsearch. Spring Data có cơ chế ánh xạ đối tượng riêng, dựa trên mapping metadata và `MappingElasticsearchConverter`. Jackson có thể xuất hiện ở tầng JSON transport hoặc trong API HTTP của ứng dụng, nhưng cấu hình Jackson không tự động trở thành cấu hình mapping entity của Spring Data.

Hiểu rõ ranh giới này giúp tránh những lỗi khó nhận ra: một thuộc tính đã được `@JsonIgnore` khỏi response API nhưng vẫn được lưu trong Elasticsearch; tên field trong index không đổi dù đã cấu hình Jackson snake case; hoặc định dạng ngày trong `@JsonFormat` không khớp với mapping date của index.

## 1. Phân biệt mapping đối tượng và serialize JSON

Hai công việc thường bị nhầm lẫn:

**Object mapping của Spring Data Elasticsearch** chuyển đổi entity Java thành cấu trúc dữ liệu mà Spring Data dùng để lưu hoặc truy vấn Elasticsearch. Quá trình này đọc metadata của entity, kiểu thuộc tính, annotation Spring Data, custom conversions và thông tin type mapping.

**JSON serialization của Jackson** chuyển đổi object Java thành chuỗi JSON hoặc đọc chuỗi JSON thành object Java theo `ObjectMapper`, Jackson annotations, modules, naming strategy và serializer/deserializer đã đăng ký.

Hai cơ chế có thể cùng xuất hiện trong một ứng dụng nhưng phục vụ các điểm khác nhau trong luồng xử lý.

### 1.1. Luồng ghi bằng Spring Data Elasticsearch

Với thao tác qua `ElasticsearchRepository` hoặc `ElasticsearchOperations`, luồng khái quát là:

~~~text
Entity Java
    |
    v
Spring Data Mapping Metadata
    |
    v
MappingElasticsearchConverter
    |
    v
Document / Map representation
    |
    v
Elasticsearch Java API Client
    |
    v
JSON transport mapper
    |
    v
HTTP request tới Elasticsearch
~~~

`MappingElasticsearchConverter` chịu trách nhiệm chuyển đổi entity theo metadata của Spring Data. Sau đó, Elasticsearch Java API Client gửi request qua transport và một JSON-P mapper serialize các cấu trúc request thành JSON. Mapper ở tầng transport có thể được cấu hình bằng Jackson-backed implementation tùy cách tạo client, nhưng nó không thay thế bước mapping entity của Spring Data.

### 1.2. Luồng đọc bằng Spring Data Elasticsearch

Khi đọc document bằng repository hoặc operations, luồng được thực hiện theo chiều ngược lại:

~~~text
HTTP response JSON
    |
    v
Elasticsearch Java API Client / JSON transport mapper
    |
    v
Document / Map representation
    |
    v
MappingElasticsearchConverter
    |
    v
Entity Java
~~~

JSON transport mapper giải mã response của Elasticsearch thành các cấu trúc dữ liệu của client. Spring Data converter tiếp tục tạo entity theo metadata, constructor, property accessor và custom conversions.

### 1.3. Luồng Jackson của Spring MVC là luồng khác

Khi controller nhận hoặc trả JSON, Spring MVC thường dùng HttpMessageConverter dựa trên Jackson:

~~~text
HTTP request JSON
    |
    v
Jackson ObjectMapper
    |
    v
Request DTO
    |
    v
Controller / Application Service
    |
    v
Spring Data Elasticsearch
    |
    v
Elasticsearch
~~~

Ở chiều trả response, Jackson serialize DTO hoặc object trả về từ controller thành JSON HTTP. Cấu hình Jackson cho API này không tự động điều khiển document được Spring Data ghi vào Elasticsearch.

## 2. Jackson annotations không phải annotation mapping của Elasticsearch

Jackson annotations mô tả cách Jackson nhìn nhận một object khi serialize hoặc deserialize JSON. Spring Data Elasticsearch sử dụng bộ annotation và metadata của Spring Data để quyết định cách lưu entity.

Một số annotation thường gặp và giới hạn của chúng:

| Jackson annotation/cấu hình | Mục đích trong Jackson | Cách kiểm soát persistence của Spring Data |
| --- | --- | --- |
| `@JsonProperty` | Đổi tên property trong JSON Jackson | Dùng `@Field(name = "...")` để đặt tên field trong Elasticsearch |
| `@JsonIgnore` | Bỏ qua property khi Jackson đọc/ghi JSON | Dùng `@Transient` nếu property không được lưu |
| `@JsonFormat` | Điều khiển định dạng JSON cho kiểu ngày, giờ hoặc số | Dùng `@Field(type = FieldType.Date, format = ..., pattern = ...)` hoặc custom conversion phù hợp |
| `@JsonInclude` | Quy định khi nào Jackson đưa property vào JSON | Xử lý null theo mapping/conversion của Spring Data và Elasticsearch |
| `@JsonSerialize` / `@JsonDeserialize` | Chỉ định serializer/deserializer của Jackson | Dùng Spring Data custom conversions hoặc property converter |
| `@JsonNaming` | Chọn naming strategy cho JSON Jackson | Đặt tên field bằng `@Field(name = "...")` hoặc mapping JSON |
| `@JsonView` | Chọn nhóm property khi serialize/deserialize JSON | Không phải cơ chế chọn field để lưu trong Elasticsearch |
| `@JsonTypeInfo` | Thêm thông tin kiểu cho JSON Jackson | Dùng type mapping của Spring Data hoặc thiết kế field/type metadata riêng |

Không nên suy luận rằng một annotation Jackson sẽ có hiệu lực trong repository chỉ vì nó có hiệu lực khi trả JSON từ controller. Cần xác định object đang đi qua Jackson hay `MappingElasticsearchConverter`.

## 3. Ví dụ: tên JSON API khác tên field Elasticsearch

Giả sử API muốn trả property display_name, trong khi index lưu field tên product_name:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "catalog-products")
public class ProductDocument {

    @Id
    private String id;

    @JsonProperty("display_name")
    @Field(name = "product_name", type = FieldType.Text)
    private String name;

    // Constructors, getters và setters
}
~~~

Trong ví dụ này:

- Jackson dùng display_name khi serialize hoặc deserialize object theo cấu hình Jackson.
- Spring Data Elasticsearch dùng product_name làm tên field trong document được lưu.

Hai tên có thể khác nhau vì chúng thuộc hai hợp đồng dữ liệu khác nhau. Tuy nhiên, cần cân nhắc việc một thuộc tính có hai tên để tránh gây nhầm lẫn cho nhóm phát triển. Nếu API và index không có lý do nghiệp vụ để khác tên, nên chọn quy ước nhất quán.

Nếu chỉ cấu hình ObjectMapper với PropertyNamingStrategies.SNAKE_CASE, điều đó không có nghĩa Spring Data sẽ tự đổi tên property thành snake case trong Elasticsearch. Để kiểm soát tên persistence, hãy khai báo `@Field(name = "product_name")` hoặc mô tả field trong mapping JSON.

## 4. Ví dụ: @JsonIgnore không tự loại property khỏi Elasticsearch

Giả sử entity có một trường nội bộ không muốn trả ra API:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(indexName = "catalog-products")
public class ProductDocument {

    private String id;
    private String name;

    @JsonIgnore
    private String internalNote;

    // Constructors, getters và setters
}
~~~

`@JsonIgnore` yêu cầu Jackson bỏ qua property theo quy tắc Jackson. Nhưng khi lưu entity bằng `ElasticsearchRepository.save(...)`, Spring Data converter không dựa vào `@JsonIgnore` để quyết định property persistence. Vì vậy, internalNote vẫn có thể được ghi vào Elasticsearch.

Nếu property thực sự không được lưu trong Elasticsearch, dùng annotation của Spring Data:

~~~java
import org.springframework.data.annotation.Transient;

@Transient
private String internalNote;
~~~

`@Transient` đánh dấu property không thuộc persistent metadata của Spring Data. Khi đó, property không được ghi/đọc như một field thông thường của entity qua mapping converter.

Nếu cần các hành vi đọc/ghi bất đối xứng, có thể xem xét `@ReadOnlyProperty` và `@WriteOnlyProperty` theo semantics của Spring Data Elasticsearch và phiên bản đang sử dụng:

- `@ReadOnlyProperty`: property được đọc từ Elasticsearch nhưng không được ghi theo luồng persistence thông thường.
- `@WriteOnlyProperty`: property được ghi nhưng không được đọc vào entity theo luồng persistence thông thường.

Các annotation này phục vụ persistence mapping. Chúng không thay thế `@JsonIgnore` nếu API HTTP cũng cần ẩn property. Trong một ứng dụng, có thể cần cả annotation Jackson và Spring Data trên cùng thuộc tính, hoặc tốt hơn là tách DTO API khỏi document persistence.

## 5. Định dạng ngày: @JsonFormat và @Field

Một lỗi phổ biến là dùng `@JsonFormat` rồi kỳ vọng Elasticsearch tự nhận được mapping date tương ứng:

~~~java
import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.Instant;

@JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
private Instant createdAt;
~~~

Annotation trên mô tả cách Jackson serialize/deserialize createdAt. Nó không tự định nghĩa kiểu mapping của field trong Elasticsearch, cũng không tự bảo đảm chuỗi ngày được index theo đúng format mong muốn.

Với Spring Data Elasticsearch, khai báo kiểu và định dạng trong mapping:

~~~java
import java.time.Instant;

import org.springframework.data.elasticsearch.annotations.DateFormat;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Field(
    type = FieldType.Date,
    format = DateFormat.date_time
)
private Instant createdAt;
~~~

Nếu cần format tùy chỉnh, có thể dùng pattern cùng format custom theo annotation API của phiên bản Spring Data Elasticsearch:

~~~java
@Field(
    type = FieldType.Date,
    format = DateFormat.custom,
    pattern = "uuuu-MM-dd HH:mm:ss"
)
private Instant createdAt;
~~~

Format mapping cần tương thích với giá trị mà converter ghi ra và dữ liệu mà Elasticsearch nhận. Khi ứng dụng dùng Instant, OffsetDateTime, LocalDate hoặc kiểu ngày khác, hãy xác định rõ múi giờ và độ chính xác cần lưu. Không nên chỉ thay đổi format JSON của API rồi cho rằng mapping date cũng đã thay đổi.

## 6. Jackson custom serializer không thay thế Spring Data custom conversion

Jackson cho phép viết serializer để biến một kiểu Java thành dạng JSON tùy chỉnh:

~~~java
public class MoneySerializer extends JsonSerializer<Money> {

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider serializers) throws IOException {

        generator.writeString(value.toPlainString());
    }
}
~~~

Nếu gắn `@JsonSerialize(using = MoneySerializer.class)`, serializer này được Jackson gọi trong luồng serialize JSON. Nhưng khi lưu entity bằng `MappingElasticsearchConverter`, không nên kỳ vọng Jackson serializer tự được gọi.

Để chuyển kiểu miền như Money sang kiểu dữ liệu Elasticsearch, hãy dùng Spring Data custom conversions. Ví dụ dưới đây minh họa chuyển Money thành chuỗi và đọc chuỗi trở lại:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class MoneyToStringConverter implements Converter<Money, String> {

    @Override
    public String convert(Money source) {
        return source.toPlainString();
    }
}

@ReadingConverter
public class StringToMoneyConverter implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        return Money.parse(source);
    }
}
~~~

Đăng ký converter trong cấu hình Spring Data Elasticsearch:

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

Ví dụ giả định kiểu Money có các phương thức toPlainString() và parse(). Trong ứng dụng thật, cần dùng API của kiểu tiền tệ đang sử dụng, quy định rõ đơn vị tiền, độ chính xác và quy tắc làm tròn.

Spring Data Elasticsearch cũng cung cấp `@ValueConverter` cho trường hợp cần converter gắn trực tiếp với một property. Custom conversion phù hợp khi một kiểu miền có quy tắc biểu diễn riêng, hoặc khi cần kiểm soát chính xác kiểu dữ liệu ghi vào và đọc ra.

Không nên dùng một custom conversion chỉ để đổi tên field. Tên field thuộc mapping metadata và có thể được khai báo bằng `@Field(name = "...")`.

## 7. Cấu hình ObjectMapper không điều khiển Elasticsearch mapping

Một ứng dụng Spring Boot có thể cấu hình Jackson thông qua bean ObjectMapper, Jackson2ObjectMapperBuilderCustomizer hoặc các thuộc tính spring.jackson.*.

Ví dụ:

~~~java
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ApiJacksonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer apiJacksonCustomizer() {
        return builder -> builder
            .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
    }
}
~~~

Customizer này điều khiển cách Jackson được Spring Boot dùng trong các luồng JSON phù hợp, chẳng hạn serialize response HTTP. Nó không tự cấu hình:

- Tên field Elasticsearch.
- Kiểu text, keyword, date, nested, object hoặc kiểu dữ liệu khác.
- Analyzer, normalizer, doc values, index hay fielddata.
- Multi-fields, dynamic templates hoặc mapping metadata.
- Việc property có được lưu bởi MappingElasticsearchConverter hay không.
- Cách Spring Data chuyển một kiểu miền tùy chỉnh thành kiểu lưu trữ.

Các nội dung trên phải được cấu hình bằng annotation Spring Data, mapping JSON, custom conversions hoặc Elasticsearch index settings/mappings tương ứng.

## 8. JSON mapper của Elasticsearch Java Client là một tầng riêng

Spring Data Elasticsearch hiện đại sử dụng Elasticsearch Java API Client làm client giao tiếp với Elasticsearch. Client này có một thành phần JsonpMapper để chuyển đổi các request/response model của Java API Client sang JSON và ngược lại.

Trong một số cách cấu hình, JsonpMapper có thể được tạo với Jackson thông qua JacksonJsonpMapper. Tuy nhiên, cần phân biệt:

1. ObjectMapper của Spring MVC: phục vụ JSON HTTP của ứng dụng.
2. JsonpMapper của Elasticsearch Java API Client: phục vụ JSON transport cho API client.
3. MappingElasticsearchConverter của Spring Data: chuyển entity persistence thành document representation và ngược lại.

Đây là ba vai trò riêng. Việc tùy chỉnh một thành phần không mặc nhiên thay đổi hai thành phần còn lại.

Khi dùng repository hoặc ElasticsearchOperations, Spring Data converter vẫn chịu trách nhiệm mapping entity theo metadata. Khi gọi trực tiếp Java API Client với một kiểu request model hoặc dữ liệu JSON cấp thấp, JsonpMapper có thể tham gia serialize/deserialize dữ liệu ở tầng client. Hành vi cụ thể phụ thuộc API đang gọi và cách client được cấu hình.

Vì vậy, nếu một Jackson annotation không có hiệu lực trong ElasticsearchRepository.save(...), việc thay ObjectMapper của Spring MVC thường không giải quyết được nguyên nhân. Hãy xác định object đang đi qua converter nào trước khi sửa cấu hình.

## 9. Những cơ chế Spring Data nên dùng cho persistence mapping

Spring Data Elasticsearch có các annotation và API riêng cho những nhu cầu thường bị nhầm với Jackson.

| Nhu cầu | Cơ chế Spring Data Elasticsearch |
| --- | --- |
| Chọn index cho entity | `@Document(indexName = "...")` |
| Đánh dấu document ID | `@Id` |
| Đổi tên field lưu trữ | `@Field(name = "...")` |
| Chọn kiểu field Elasticsearch | `@Field(type = FieldType...)` |
| Đặt date format và pattern | `@Field(format = ..., pattern = ...)` |
| Khai báo multi-fields | `@MultiField` và `@InnerField` |
| Bỏ property khỏi persistence mapping | `@Transient` |
| Property chỉ đọc hoặc chỉ ghi | `@ReadOnlyProperty`, `@WriteOnlyProperty` |
| Chuyển đổi kiểu Java tùy chỉnh | `ElasticsearchCustomConversions` hoặc `@ValueConverter` |
| Kiểm soát type alias | `@TypeAlias` và cấu hình type mapper |
| Khai báo mapping JSON | `@Mapping` hoặc API quản lý index |
| Khai báo index settings | `@Setting` hoặc API quản lý index |

### 9.1. Ví dụ entity dùng đúng annotation cho từng mục tiêu

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.elasticsearch.annotations.DateFormat;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

import java.time.Instant;

@Document(indexName = "catalog-products")
public class ProductDocument {

    @Id
    private String id;

    @JsonProperty("display_name")
    @Field(name = "product_name", type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Date, format = DateFormat.date_time)
    private Instant createdAt;

    @JsonIgnore
    @Transient
    private String internalNote;

    // Constructors, getters và setters
}
~~~

Trong ví dụ:

- @JsonProperty phục vụ hợp đồng JSON của Jackson.
- @Field phục vụ tên và kiểu field trong Elasticsearch.
- @Field với kiểu Date và format mô tả mapping ngày.
- @JsonIgnore ẩn property trong luồng Jackson.
- @Transient loại property khỏi persistent mapping của Spring Data.

Nếu API và persistence có yêu cầu khác nhau đáng kể, hãy cân nhắc dùng ProductRequest, ProductResponse và ProductDocument riêng thay vì gắn nhiều annotation của hai hệ thống lên cùng một class.

## 10. Constructor, property access và type metadata

Jackson có cơ chế riêng như JsonCreator, JsonProperty trên constructor parameter và JsonTypeInfo. Những annotation đó không tự cấu hình cách Spring Data tạo entity từ document.

Spring Data sử dụng mapping metadata, constructor được chọn cho persistence và property accessor. Khi cần chỉ định constructor dùng để tạo entity từ dữ liệu lưu trữ, hãy dùng annotation persistence như PersistenceCreator theo phiên bản Spring Data tương ứng.

Ví dụ:

~~~java
import org.springframework.data.annotation.PersistenceCreator;

public class ProductSummary {

    private final String sku;
    private final String name;

    @PersistenceCreator
    public ProductSummary(String sku, String name) {
        this.sku = sku;
        this.name = name;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }
}
~~~

Spring Data Elasticsearch cũng có cơ chế type hint riêng. Mapping converter có thể lưu thông tin kiểu, thường trong field _class, để hỗ trợ khôi phục kiểu cụ thể khi đọc object có kiểu khai báo tổng quát. `@TypeAlias` cho phép định nghĩa alias ngắn hơn cho kiểu. Đây là cơ chế của Spring Data type mapping; không nên coi JsonTypeInfo là cấu hình thay thế.

Nếu cần thay đổi cách lưu type hint, hãy tìm hiểu type mapper và mapping context của Spring Data Elasticsearch. Thay đổi type metadata có thể ảnh hưởng khả năng đọc lại dữ liệu cũ, nên cần được quản lý như một thay đổi schema.

## 11. Map, object lồng nhau và trường động

Jackson có các annotation như JsonAnyGetter, JsonAnySetter hoặc JsonUnwrapped để điều khiển cách object JSON được đọc và ghi. Chúng không thay thế quy tắc mapping của Elasticsearch.

Nếu document có các thuộc tính mở rộng, Spring Data có thể ánh xạ Map<String, Object> theo mapping metadata của property và kiểu dữ liệu thực tế:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Field(type = FieldType.Object)
private Map<String, Object> attributes;
~~~

Elasticsearch vẫn quyết định cách các trường con được lập chỉ mục thông qua mapping của object, dynamic mapping và dynamic templates. Jackson JsonAnySetter không tự tạo dynamic template, không đặt dynamic strict và không quyết định một chuỗi con sẽ là text hay keyword.

Nếu muốn object con được xử lý như nested document, cần khai báo FieldType.Nested hoặc mapping JSON tương ứng. Nếu muốn trường con không được lập chỉ mục, cần thiết kế mapping và dynamic mode thích hợp. Đây là quyết định schema Elasticsearch, không phải quyết định serialize JSON.

## 12. Mapping JSON và Jackson JSON không phải cùng một thứ

Spring Data Elasticsearch hỗ trợ dùng tệp mapping JSON để khai báo schema của index. Ví dụ:

~~~java
@Document(indexName = "catalog-products")
@Mapping(mappingPath = "/elasticsearch/mappings/product-mapping.json")
public class ProductDocument {
    // Các thuộc tính entity
}
~~~

Tệp mapping JSON mô tả settings hoặc mappings theo cấu trúc API của Elasticsearch, ví dụ properties, dynamic_templates, analyzer, fields và type. Tệp này không phải cấu hình Jackson ObjectMapper.

Một mapping có thể khai báo:

~~~json
{
  "properties": {
    "product_name": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword"
        }
      }
    },
    "created_at": {
      "type": "date",
      "format": "strict_date_optional_time||epoch_millis"
    }
  }
}
~~~

Mapping này quyết định cách Elasticsearch lập chỉ mục và truy vấn field. Jackson có thể serialize một object thành JSON có tên property khác, nhưng điều đó không làm thay đổi mapping đã được tạo trong index.

## 13. Kiểm tra đúng tầng khi cấu hình không có hiệu lực

Khi thấy dữ liệu lưu vào Elasticsearch khác với mong đợi, nên xác định chính xác bước gây ra khác biệt.

### 13.1. Kiểm tra mapping của index

Đọc mapping thực tế:

~~~http
GET /catalog-products/_mapping
~~~

Kiểm tra tên field, kiểu dữ liệu, multi-fields, date format, analyzer, nested/object và dynamic templates. Nếu tên field không đúng, hãy xem Field name hoặc mapping JSON.

### 13.2. Kiểm tra document đã lưu

Đọc _source của document:

~~~http
GET /catalog-products/_doc/sku-1001
~~~

Kiểm tra field nào thực sự được ghi, tên field, kiểu giá trị và nội dung. Nếu một property vẫn được lưu dù có JsonIgnore, hãy kiểm tra xem thao tác lưu có đi qua MappingElasticsearchConverter và property có được đánh dấu Transient hay không.

### 13.3. Kiểm tra JSON của API riêng

Nếu response HTTP không có property hoặc tên property không đúng, kiểm tra ObjectMapper, Jackson annotations và cấu hình Spring MVC. Không dùng kết quả JSON của API để suy luận trực tiếp rằng _source trong Elasticsearch cũng có cùng cấu trúc.

### 13.4. Kiểm tra custom conversion

Nếu một kiểu Java được lưu thành dạng không mong muốn, kiểm tra:

- Spring Data có converter mặc định cho kiểu đó hay không.
- Có ElasticsearchCustomConversions hoặc ValueConverter đang áp dụng hay không.
- Converter đọc và ghi có đối xứng về định dạng hay không.
- Mapping Elasticsearch có kiểu tương thích với giá trị converter tạo ra hay không.

Đọc document và mapping thực tế thường cho biết lỗi nằm ở chuyển đổi entity, cấu hình schema hay tầng API JSON.

## 14. Thiết kế class: dùng chung hay tách DTO và Document?

Một class có thể đồng thời dùng annotation Jackson và Spring Data, nhưng việc kết hợp đó tạo ra hai hợp đồng trên cùng một kiểu. Khi API và persistence có vòng đời khác nhau, tách class thường dễ bảo trì hơn.

Ví dụ:

~~~text
ProductRequest
    |
    v
ProductApplicationService
    |
    v
Product (domain model)
    |
    v
ProductDocument (Elasticsearch persistence)
    |
    v
ElasticsearchRepository

ProductResponse
    ^
    |
ProductApplicationService
~~~

Mỗi kiểu có một trách nhiệm:

- ProductRequest: cấu trúc dữ liệu nhận từ client; dùng Jackson để đọc JSON.
- Product: biểu diễn nghiệp vụ; không cần phụ thuộc Jackson hoặc Elasticsearch nếu không có lý do.
- ProductDocument: biểu diễn dữ liệu lưu trong index; dùng annotation và conversion của Spring Data.
- ProductResponse: cấu trúc JSON trả về client; dùng Jackson để serialize theo hợp đồng API.

Lợi ích của việc tách:

- Có thể đổi tên field trong index mà không làm thay đổi API công khai.
- Có thể ẩn dữ liệu nội bộ khỏi response mà vẫn lưu trong persistence khi cần.
- Có thể thay Elasticsearch bằng một hệ thống lưu trữ khác với ít ảnh hưởng tới domain.
- Mapping schema và API schema có thể được version độc lập.
- Tránh phải dùng nhiều annotation chồng lên nhau trên cùng một property.

Với ứng dụng nhỏ và schema đơn giản, dùng chung một class vẫn có thể hợp lý. Khi đó, cần hiểu rõ annotation nào tác động tới Jackson và annotation nào tác động tới Spring Data.

## 15. Lỗi thường gặp và cách xử lý

**Dùng JsonProperty để đổi tên field trong Elasticsearch.** Annotation này điều khiển Jackson. Dùng Field name hoặc mapping JSON để đổi tên persistence field.

**Dùng JsonIgnore để loại dữ liệu khỏi _source.** Jackson có thể bỏ qua property trong response JSON nhưng Spring Data converter vẫn lưu property. Dùng Transient hoặc tách DTO khỏi document.

**Dùng JsonFormat để sửa lỗi mapping date.** Jackson format không tự định nghĩa date format của Elasticsearch. Khai báo FieldType.Date, format và pattern trong mapping hoặc dùng converter phù hợp.

**Thay ObjectMapper nhưng repository vẫn ghi dữ liệu như cũ.** Repository dùng mapping converter của Spring Data. Hãy cấu hình annotation, custom conversion hoặc mapping metadata đúng tầng.

**Dùng Jackson custom serializer để chuyển kiểu domain.** Serializer chỉ chạy trong luồng Jackson. Dùng ElasticsearchCustomConversions hoặc ValueConverter cho persistence.

**Dùng JsonNaming để áp dụng snake case cho mapping.** Naming strategy của Jackson không tự đổi tên field của Spring Data. Khai báo Field name hoặc mapping JSON.

**Dùng JsonTypeInfo để thay đổi _class.** Type hints của Spring Data có cơ chế riêng. Tìm hiểu TypeAlias và type mapper.

**Thấy response API đúng nên cho rằng document cũng đúng.** Response có thể đã được Jackson biến đổi sau khi đọc entity. Kiểm tra _source và mapping trực tiếp trên Elasticsearch.

## 16. Quy trình lựa chọn cơ chế đúng

Khi cần thay đổi cách dữ liệu được biểu diễn, hãy bắt đầu từ mục tiêu:

1. Nếu muốn đổi tên property trong request hoặc response HTTP, dùng Jackson annotation hoặc cấu hình ObjectMapper.
2. Nếu muốn đổi tên field trong Elasticsearch, dùng Field name hoặc mapping JSON.
3. Nếu muốn bỏ property khỏi persistence, dùng Transient; nếu chỉ muốn ẩn trong API, dùng Jackson hoặc DTO response riêng.
4. Nếu muốn đổi kiểu hoặc định dạng field Elasticsearch, cấu hình Field, mapping JSON hoặc custom conversion.
5. Nếu muốn chuyển kiểu Java miền sang dạng lưu trữ khác, đăng ký ElasticsearchCustomConversions hoặc ValueConverter.
6. Nếu muốn thay cách lưu type hint, xem TypeAlias và type mapping của Spring Data.
7. Nếu dùng Java API Client trực tiếp, xác định JsonpMapper có tham gia serialize/deserialize model request/response hay không.
8. Sau khi thay đổi, kiểm tra cả mapping và _source thực tế; kiểm tra response HTTP riêng nếu API cũng bị ảnh hưởng.

Jackson là công cụ quan trọng trong ứng dụng Spring, nhưng nó không phải cơ chế mapping entity của Spring Data Elasticsearch. MappingElasticsearchConverter cùng metadata của Spring Data quyết định cách entity trở thành document và được khôi phục từ document. Khi phân biệt rõ hai pipeline, ta có thể chọn đúng annotation, converter và cấu hình cho từng mục tiêu mà không vô tình làm thay đổi hợp đồng dữ liệu ở tầng khác.
