# Kiểm thử analyzer, converter và một vòng ghi đọc

Một ứng dụng Spring Data Elasticsearch có thể chạy mà không báo lỗi nhưng vẫn lưu hoặc tìm dữ liệu sai. Analyzer có thể tách từ không đúng kỳ vọng; converter có thể serialize một kiểu Java thành giá trị không thể đọc lại; mapping có thể thiếu field hoặc khai báo sai kiểu; một vòng save rồi get có thể làm mất dữ liệu do chuyển đổi không đối xứng.

Vì vậy, kiểm thử tích hợp nên xác nhận ba phần phối hợp với nhau:

1. **Analyzer và mapping:** Elasticsearch phân tích văn bản theo đúng cấu hình field.
2. **Converter:** Spring Data chuyển đổi entity sang Document và đọc Document trở lại đúng kiểu Java.
3. **Một vòng ghi đọc thực tế:** entity được lưu vào Elasticsearch, sau đó được đọc lại và giữ đúng dữ liệu nghiệp vụ.

Các kiểm thử này bổ sung cho unit test của service. Chúng cần một Elasticsearch thật tương thích với phiên bản Spring Data của dự án, thường được khởi chạy bằng Testcontainers trong lúc test. Mock ElasticsearchOperations không thể chứng minh analyzer, mapping, serialization và truy vấn thực sự hoạt động trên cluster.

## 1. Ba lớp cần kiểm thử

Analyzer, converter và mapping có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm | Câu hỏi kiểm thử |
|---|---|---|
| Mapping | Khai báo field type, analyzer, format và các thuộc tính index | Elasticsearch có nhận đúng mapping không? |
| Analyzer | Chuyển văn bản thành token để index hoặc search | Văn bản đầu vào tạo ra những token nào? |
| Converter | Chuyển kiểu Java sang Document và ngược lại | Giá trị có được serialize và deserialize đúng không? |
| Write/read integration | Kết hợp mapping, converter, client và cluster | Save xong đọc lại có còn đúng dữ liệu không? |

Không nên dùng một assertion duy nhất để kết luận mọi lớp đều đúng. Ví dụ, đọc lại document theo ID thành công chưa chứng minh analyzer tách token đúng. Ngược lại, _analyze trả token đúng cũng chưa chứng minh custom converter lưu được entity.

Luồng kiểm thử tổng thể:

~~~text
        Entity Java
             |
             v
    Spring Data Converter
             |
             v
       Elasticsearch Document
             |
             v
       Index + Mapping
             |
             v
       Analyzer khi index
             |
             v
       Lucene inverted index
             |
             v
       Search / Analyze API
             |
             v
      SearchHit / Document
             |
             v
    Spring Data Converter
             |
             v
        Entity Java
~~~

## 2. Dùng Elasticsearch thật trong integration test

Analyzer và mapping được thực thi bởi Elasticsearch. Vì vậy, test analyzer cần một node Elasticsearch thật. Testcontainers giúp tạo và hủy node theo vòng đời test, tránh phụ thuộc vào cluster dùng chung trên máy developer.

Với Maven, dự án thường cần các dependency test tương ứng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>elasticsearch</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
~~~

Phiên bản Testcontainers cần tương thích với JDK, Spring Boot và cách quản lý dependency của dự án. Không nên tự nâng riêng Testcontainers hoặc Elasticsearch image lên một major version khác mà chưa kiểm tra ma trận tương thích.

### 2.1. Khởi chạy container

Ví dụ với JUnit 5 và Testcontainers:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.elasticsearch.ElasticsearchContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class ProductElasticsearchIntegrationTest {

    @Container
    static final ElasticsearchContainer elasticsearch =
            new ElasticsearchContainer(
                    DockerImageName.parse(
                            "docker.elastic.co/elasticsearch/elasticsearch:8.15.5"
                    )
            ).withPassword("test-password");

    @DynamicPropertySource
    static void elasticsearchProperties(
            DynamicPropertyRegistry registry
    ) {
        registry.add(
                "spring.elasticsearch.uris",
                elasticsearch::getHttpHostAddress
        );
        registry.add(
                "spring.elasticsearch.username",
                () -> "elastic"
        );
        registry.add(
                "spring.elasticsearch.password",
                elasticsearch::getPassword
        );
    }
}
~~~

Đây là cấu trúc minh họa cho Testcontainers 1.x và Spring Boot 3.x. API container, cách bật security và property name có thể thay đổi theo phiên bản. Dùng image Elasticsearch cùng major/minor phù hợp với client mà ứng dụng hỗ trợ; nếu dự án đã có cấu hình container riêng, giữ nguyên cơ chế đó và chỉ bổ sung test cần thiết.

Testcontainers cần Docker daemon hoạt động. Nếu Docker không khả dụng, test sẽ không thể khởi chạy node; đó là lỗi môi trường test, không phải bằng chứng analyzer hoặc converter sai.

### 2.2. Không dùng cluster dùng chung cho test ghi dữ liệu

Một test ghi document vào index cố định có thể ảnh hưởng test khác hoặc dữ liệu developer. Hãy:

- Dùng index dành riêng cho integration test.
- Xóa và tạo lại index trước mỗi test cần trạng thái sạch.
- Không trỏ test tới production hoặc cluster dùng chung.
- Dọn index sau test nếu index không tự bị xóa cùng container.
- Tránh chạy song song nhiều test cùng ghi một index cố định nếu chưa có cơ chế cô lập.

Với test chạy song song, dùng index name riêng cho từng test hoặc từng test class. Tên index phải viết thường theo quy tắc của Elasticsearch.

## 3. Khai báo mapping và analyzer kiểm thử

Giả sử field `name` cần xử lý chữ hoa/thường và dấu tiếng Việt hoặc dấu Latin. Ta định nghĩa custom analyzer gồm:

- Standard tokenizer để tách token theo ranh giới từ.
- Lowercase filter để chuẩn hóa chữ thường.
- Asciifolding filter để chuyển một số ký tự có dấu sang dạng ASCII tương ứng.

Ví dụ file settings:

`src/test/resources/settings/products-settings.json`

~~~json
{
  "analysis": {
    "analyzer": {
      "product_text": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": [
          "lowercase",
          "asciifolding"
        ]
      }
    }
  }
}
~~~

Mapping:

`src/test/resources/mappings/products-mapping.json`

~~~json
{
  "properties": {
    "name": {
      "type": "text",
      "analyzer": "product_text",
      "search_analyzer": "product_text"
    },
    "status": {
      "type": "keyword"
    },
    "price": {
      "type": "keyword"
    },
    "createdAt": {
      "type": "date"
    }
  }
}
~~~

Trong ví dụ này `price` được map thành keyword vì phần sau sẽ dùng custom converter biến một value object thành chuỗi có định dạng cố định. Nếu cần lọc hoặc sort theo số tiền, nên thiết kế mapping numeric phù hợp thay vì lưu mọi giá trị tiền dưới dạng keyword.

### 3.1. Gắn settings và mapping vào entity test

Spring Data Elasticsearch có thể đọc file settings và mapping từ classpath thông qua annotation:

~~~java
@Document(indexName = "products-it")
@Setting(settingPath = "/settings/products-settings.json")
@Mapping(mappingPath = "/mappings/products-mapping.json")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "product_text")
    private String name;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Keyword)
    private Money price;

    @Field(type = FieldType.Date)
    private Instant createdAt;
}
~~~

Các annotation và thuộc tính cần có trong release train Spring Data Elasticsearch của dự án. Nếu ứng dụng quản lý mapping bằng JSON riêng hoặc index template, hãy tạo index bằng đúng cơ chế production sử dụng để test không bị lệch cấu hình.

Không chỉ kiểm tra annotation trên entity. Điều quan trọng là mapping thực tế được cài trên index. Một annotation đúng nhưng index đã tồn tại với mapping cũ sẽ không tự động thay đổi field mapping hiện có.

## 4. Kiểm thử mapping thực tế

Sau khi tạo index, đọc mapping từ Elasticsearch để xác nhận field có đúng type và analyzer:

~~~java
@Autowired
ElasticsearchOperations operations;

@Test
void createsIndexWithExpectedMapping() {
    IndexOperations indexOperations =
            operations.indexOps(ProductDocument.class);

    if (indexOperations.exists()) {
        indexOperations.delete();
    }

    assertThat(indexOperations.createWithMapping()).isTrue();

    Map<String, Object> mapping = indexOperations.getMapping();
    assertThat(mapping).isNotEmpty();
}
~~~

Đoạn test trên minh họa tạo index bằng metadata của entity và đọc mapping. Để kiểm tra chi tiết, có thể dùng Elasticsearch Java Client `indices().getMapping(...)` hoặc REST Get Mapping API rồi kiểm tra `properties.name.type`, `properties.name.analyzer` và các field liên quan.

Ví dụ API:

~~~http
GET /products-it/_mapping
~~~

Mapping cần được xác nhận sau khi index được tạo. Nếu test chỉ gọi `createWithMapping()` nhưng không assert hoặc quan sát mapping thực tế, test chưa chứng minh field đã được cấu hình như mong đợi.

### 4.1. Mapping không thể thay đổi tùy ý sau khi index đã có dữ liệu

Một số thay đổi mapping, đặc biệt thay đổi field type, không thể thực hiện trực tiếp trên field hiện có. Nếu mapping sai, cần tạo index mới với mapping đúng và reindex dữ liệu theo quy trình phù hợp.

Do đó, mỗi integration test nên bắt đầu với index mới hoặc xóa/tạo lại index. Nếu test tái sử dụng index cũ, có thể vô tình kiểm tra mapping từ lượt chạy trước.

## 5. Kiểm thử analyzer bằng Analyze API

Analyze API cho phép gửi văn bản và quan sát token do analyzer tạo ra. Đây là cách trực tiếp để xác nhận tokenizer và token filters.

Ví dụ kiểm tra field `name`:

~~~java
import co.elastic.clients.elasticsearch.indices.AnalyzeResponse;

AnalyzeResponse response = elasticsearchClient.indices().analyze(
        request -> request
                .index("products-it")
                .field("name")
                .text("Café KEYBOARD")
);

List<String> tokens = response.tokens().stream()
        .map(token -> token.token())
        .toList();

assertThat(tokens).containsExactly("cafe", "keyboard");
~~~

Sử dụng field thay vì chỉ chỉ định tên analyzer giúp test analyzer đang gắn với field mapping. Nếu mapping field bị thiếu hoặc analyzer không được cài, test sẽ phát hiện lỗi cấu hình.

Có thể gọi trực tiếp REST API để điều tra:

~~~http
POST /products-it/_analyze
Content-Type: application/json

{
  "field": "name",
  "text": "Café KEYBOARD"
}
~~~

Kết quả token mong đợi trong ví dụ là `cafe` và `keyboard`. Khi dùng dữ liệu tiếng Việt, cần chọn từ có dấu và xác định rõ kỳ vọng với dấu, chữ hoa, dấu câu, từ ghép và tokenizer. Asciifolding không phải bộ tách từ tiếng Việt chuyên sâu; nó chỉ xử lý chuyển đổi ký tự theo filter được hỗ trợ.

### 5.1. Test analyzer index-time và search-time

Mapping có thể khai báo analyzer khác nhau cho lúc index và lúc search. Cần kiểm tra cả hai nếu ứng dụng có cấu hình riêng:

- `analyzer`: token hóa nội dung khi index.
- `search_analyzer`: token hóa query text khi search.

Analyze API có thể chỉ rõ analyzer hoặc field. Kiểm thử field cho biết analyzer gắn trên field; kiểm thử tên analyzer riêng hữu ích để xác định chính xác từng cấu hình.

Nếu search analyzer khác index analyzer, hãy test cả hai đầu vào để bảo đảm chúng tạo token tương thích. Một analyzer index tốt nhưng search analyzer không tương thích có thể khiến từ khóa người dùng không tìm thấy document.

### 5.2. Test các trường hợp văn bản biên

Không chỉ test một chuỗi tiếng Anh đơn giản. Xác định bộ input đại diện:

| Input | Điều cần quan sát |
|---|---|
| `Café KEYBOARD` | Lowercase và folding |
| `WIRELESS mouse` | Chuyển chữ hoa thành chữ thường |
| `wireless-mouse` | Ranh giới token do tokenizer |
| Chuỗi có dấu câu | Tokenizer xử lý punctuation |
| Chuỗi rỗng | Không tạo token ngoài mong đợi |
| Chỉ có khoảng trắng | Không tạo token |
| Ký tự Unicode ngoài Latin | Hành vi thực tế của tokenizer/filter |

Expected tokens phải dựa trên analyzer thật và ngôn ngữ dữ liệu của sản phẩm. Không tự giả định mọi dấu tiếng Việt hoặc mọi ký tự Unicode đều được xử lý giống nhau bởi asciifolding.

## 6. Custom converter trong Spring Data Elasticsearch

Converter chịu trách nhiệm chuyển kiểu Java sang cấu trúc Document mà Elasticsearch lưu và đọc cấu trúc đó trở lại kiểu Java.

Ví dụ domain có value object `Money`:

~~~java
public record Money(long minorUnits, String currency) {
}
~~~

Ứng dụng muốn lưu `Money(1299, "USD")` thành chuỗi `USD:1299`. Khi đọc lại, converter phải phân tích chuỗi và tạo lại value object.

### 6.1. Writing converter

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class MoneyToStringConverter
        implements Converter<Money, String> {

    @Override
    public String convert(Money source) {
        return source.currency() + ":" + source.minorUnits();
    }
}
~~~

### 6.2. Reading converter

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class StringToMoneyConverter
        implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        String[] parts = source.split(":", 2);
        if (parts.length != 2) {
            throw new IllegalArgumentException(
                    "Invalid money representation"
            );
        }

        return new Money(
                Long.parseLong(parts[1]),
                parts[0]
        );
    }
}
~~~

Đánh dấu hướng chuyển đổi bằng `@WritingConverter` và `@ReadingConverter` giúp Spring Data phân biệt converter dùng khi ghi và khi đọc, đặc biệt khi hai kiểu nguồn/đích đều là kiểu đơn giản.

Định dạng chuỗi là hợp đồng dữ liệu. Cần xác định rõ currency, scale, separator, locale và cách xử lý dữ liệu cũ. Không dùng `toString()` tùy tiện nếu chuỗi đó không có format ổn định.

### 6.3. Đăng ký custom conversions

Đăng ký converter với `ElasticsearchCustomConversions` trong cấu hình Spring Data Elasticsearch:

~~~java
@Bean
ElasticsearchCustomConversions elasticsearchCustomConversions() {
    return new ElasticsearchCustomConversions(
            List.of(
                    new MoneyToStringConverter(),
                    new StringToMoneyConverter()
            )
    );
}
~~~

Trong cấu hình kế thừa `AbstractElasticsearchConfiguration`, có thể override method cung cấp custom conversions theo API của phiên bản. Với Spring Boot auto-configuration, xác nhận bean custom conversions được sử dụng bởi `ElasticsearchConverter` thực tế. Không chỉ tạo bean converter rời mà không đăng ký nó vào mapping converter.

Nếu ứng dụng có nhiều cấu hình converter, kiểm tra danh sách conversion đã đăng ký và tránh hai converter xung đột cho cùng cặp kiểu.

## 7. Unit test converter độc lập

Trước khi khởi chạy Elasticsearch, có thể kiểm tra riêng chuyển đổi entity thành Document và đọc Document trở lại bằng `ElasticsearchConverter`.

Ví dụ:

~~~java
@Autowired
ElasticsearchConverter converter;

@Test
void convertsMoneyToDocumentAndBack() {
    ProductDocument product = new ProductDocument();
    product.setId("product-42");
    product.setName("Keyboard");
    product.setPrice(new Money(1299, "USD"));

    Document document = Document.create();
    converter.write(product, document);

    assertThat(document.get("price")).isEqualTo("USD:1299");

    ProductDocument restored =
            converter.read(ProductDocument.class, document);

    assertThat(restored.getPrice())
            .isEqualTo(new Money(1299, "USD"));
}
~~~

Test này xác nhận mapping converter sử dụng đúng cặp converter theo hai chiều. Nó không cần network hoặc Elasticsearch node, nhưng cần Spring context cung cấp `ElasticsearchConverter` đã đăng ký custom conversions.

Nếu muốn unit test converter thuần, có thể gọi trực tiếp `MoneyToStringConverter` và `StringToMoneyConverter`. Tuy nhiên, test trực tiếp converter không chứng minh Spring Data đã đăng ký và gọi chúng trong quá trình map entity. Test qua `ElasticsearchConverter` bao phủ thêm bước đăng ký và mapping.

### 7.1. Kiểm thử dữ liệu sai định dạng

Reading converter cần xử lý rõ:

- Chuỗi null hoặc rỗng.
- Thiếu currency.
- Thiếu amount.
- Amount không phải số.
- Currency không hợp lệ.
- Dữ liệu legacy có format khác.

Tùy hợp đồng domain, converter có thể ném exception rõ ràng hoặc hỗ trợ format cũ có chủ đích. Không âm thầm chuyển dữ liệu lỗi thành giá trị mặc định vì sẽ che mất lỗi lưu trữ.

## 8. Một vòng ghi đọc qua Elasticsearch thật

Unit test converter chưa chứng minh toàn bộ đường ghi đọc. Integration test cần lưu entity qua `ElasticsearchOperations`, để converter tạo document, Elasticsearch index dữ liệu, rồi đọc lại qua cùng mapping converter.

Entity ví dụ:

~~~java
@Document(indexName = "products-it")
@Setting(settingPath = "/settings/products-settings.json")
@Mapping(mappingPath = "/mappings/products-mapping.json")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "product_text")
    private String name;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Keyword)
    private Money price;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    // getters and setters
}
~~~

Integration test:

~~~java
@Autowired
ElasticsearchOperations operations;

@Test
void writesAndReadsProductWithCustomMoneyConversion() {
    IndexOperations indexOperations =
            operations.indexOps(ProductDocument.class);

    if (indexOperations.exists()) {
        indexOperations.delete();
    }
    assertThat(indexOperations.createWithMapping()).isTrue();

    ProductDocument product = new ProductDocument();
    product.setId("product-42");
    product.setName("Café Keyboard");
    product.setStatus("ACTIVE");
    product.setPrice(new Money(1299, "USD"));
    product.setCreatedAt(Instant.parse("2026-11-13T08:00:00Z"));

    ProductDocument saved = operations.save(product);

    ProductDocument loaded = operations.get(
            saved.getId(),
            ProductDocument.class
    );

    assertThat(loaded).isNotNull();
    assertThat(loaded.getName()).isEqualTo("Café Keyboard");
    assertThat(loaded.getStatus()).isEqualTo("ACTIVE");
    assertThat(loaded.getPrice())
            .isEqualTo(new Money(1299, "USD"));
    assertThat(loaded.getCreatedAt())
            .isEqualTo(Instant.parse("2026-11-13T08:00:00Z"));
}
~~~

Ví dụ này dùng get theo document ID. Get API theo ID là real-time theo mặc định, nên có thể đọc document mới mà không cần chờ refresh. Nếu mục tiêu test là Search API, hãy refresh index trước khi search.

### 8.1. Xác nhận Search visibility

Sau khi save:

~~~java
indexOperations.refresh();

Query query = NativeQuery.builder()
        .withQuery(q -> q.term(t -> t
                .field("status")
                .value("ACTIVE")
        ))
        .build();

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);

assertThat(hits.getSearchHits())
        .extracting(hit -> hit.getContent().getId())
        .contains("product-42");
~~~

Refresh ở đây phục vụ Search visibility. Nó không phải điều kiện để converter ghi đúng hoặc để Get API theo ID đọc document mới.

### 8.2. Kiểm tra giá trị được lưu ở dạng nào

Để xác nhận converter đã ghi chuỗi `USD:1299` vào `_source`, có thể đọc document raw qua Elasticsearch Java Client hoặc Get API có trả source. Điều này giúp phân biệt:

- Converter write có tạo representation đúng không?
- Elasticsearch mapping có chấp nhận representation đó không?
- Converter read có khôi phục đúng kiểu Java không?

Một vòng `save` rồi `get` thành công chứng minh đường đi hai chiều hoạt động cho giá trị đã test. Nhưng kiểm tra raw source giúp chẩn đoán nếu kết quả sai: lỗi có thể ở serialization hoặc reading conversion.

## 9. Kiểm thử analyzer kết hợp với vòng ghi đọc

Sau khi index một sản phẩm tên `Café Keyboard`, có thể dùng query match để xác nhận analyzer thực tế giúp tìm theo chuỗi chuẩn hóa:

~~~java
Query query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
                .field("name")
                .query("cafe keyboard")
        ))
        .build();

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);

assertThat(hits.getSearchHits())
        .extracting(hit -> hit.getContent().getId())
        .contains("product-42");
~~~

Test này kiểm tra analyzer tham gia vào hành vi search thực tế. Nó bổ sung cho `_analyze` test:

- `_analyze` xác nhận token được tạo ra.
- Match query xác nhận document được index và truy vấn có thể tìm thấy nó theo analyzer đã cấu hình.

Nếu `_analyze` đúng nhưng match query không tìm thấy, kiểm tra mapping của index lúc document được index, field có được index hay không, search analyzer, query field và dữ liệu thực tế.

## 10. Kiểm thử converter không đối xứng

Một converter có thể ghi đúng nhưng đọc sai, hoặc ngược lại. Ví dụ:

- Writing converter ghi `USD:1299`.
- Reading converter lại hiểu amount là major unit thay vì minor unit.
- Currency bị chuyển chữ thường.
- Chuỗi được parse theo locale máy chạy test.
- Giá trị âm hoặc số lớn bị overflow.

Vì vậy, test round-trip nên dùng nhiều giá trị:

| Input Java | Representation mong đợi | Output Java |
|---|---|---|
| `Money(1299, "USD")` | `USD:1299` | `Money(1299, "USD")` |
| `Money(0, "VND")` | `VND:0` | `Money(0, "VND")` |
| `Money(-500, "USD")` | `USD:-500` | `Money(-500, "USD")` |
| Giá trị lớn trong miền cho phép | Chuỗi số nguyên ổn định | Giữ nguyên amount |

Nếu domain không cho phép amount âm, converter có thể từ chối và validation nghiệp vụ nên kiểm tra trước khi ghi. Điều quan trọng là xác định rõ contract và test cả dữ liệu biên được phép lẫn dữ liệu phải bị từ chối.

## 11. Kiểm thử mapping và analyzer khi index đã tồn tại

Một lỗi phổ biến là test chạy lần đầu thành công, nhưng những lần sau dùng lại index với mapping cũ. `createWithMapping()` không có nghĩa mọi field mapping sẽ được ghi đè trên index đang tồn tại.

Chiến lược kiểm thử:

1. Tạo index mới với tên dành riêng cho test.
2. Cài settings và mapping.
3. Kiểm tra mapping thực tế.
4. Chạy `_analyze` trên field đã map.
5. Ghi document.
6. Đọc document và kiểm tra converter.
7. Chạy Search API để xác nhận analyzer index/search.
8. Xóa index sau test hoặc để container disposable hủy toàn bộ dữ liệu.

Nếu ứng dụng dùng index template hoặc component template trong production, integration test nên cài template và tạo index theo cùng cơ chế. Chỉ test annotation trên entity sẽ không phát hiện template production ghi đè settings hoặc mapping.

## 12. Kiểm thử với alias và index versioned

Trong production, ứng dụng có thể ghi qua alias như `products` trỏ tới index versioned `products-v3`. Test cần xác nhận:

- Alias được trỏ tới index đúng.
- Mapping/analyzer tồn tại trên index đích.
- Save qua alias hoạt động theo quyền và routing thực tế.
- Search qua alias dùng analyzer mong muốn.
- Việc đổi alias không làm test phụ thuộc vào index cũ.

Nếu dùng index name cố định trong `@Document`, có thể truyền `IndexCoordinates` vào các thao tác để kiểm thử index cụ thể. Khi làm vậy, phải bảo đảm mapping được tạo trên đúng index coordinates mà thao tác save/search sử dụng.

## 13. Test converter với dữ liệu cũ

Converter thường phải đọc document đã được ghi bởi phiên bản ứng dụng trước. Khi thay đổi format:

- Reading converter có thể cần hỗ trợ format cũ trong giai đoạn migration.
- Writing converter chỉ nên phát format mới sau khi các reader đã tương thích.
- Cần kiểm tra dữ liệu thiếu field hoặc field null.
- Nếu format thay đổi không tương thích, lên kế hoạch reindex hoặc chuyển đổi dữ liệu.

Ví dụ, format cũ là `1299|USD`, format mới là `USD:1299`. Reading converter có thể nhận cả hai trong giai đoạn chuyển tiếp, nhưng writing converter chỉ ghi format chuẩn mới. Hãy test từng format để không vô tình làm hỏng document cũ.

Không biến converter thành nơi chứa toàn bộ logic migration. Converter nên chuyển đổi representation; migration lớn cần một job có kiểm soát, log lỗi và khả năng tiếp tục.

## 14. Phân biệt lỗi analyzer, converter và mapping

Khi test thất bại, xác định lớp lỗi trước khi sửa:

| Triệu chứng | Nơi cần kiểm tra |
|---|---|
| `_analyze` không trả token mong đợi | Analyzer definition, tokenizer, filters, field mapping |
| Field không tồn tại trong mapping | Entity annotation, mapping JSON, index template, thứ tự tạo index |
| Save báo lỗi mapping | Field type, converter output, dữ liệu không phù hợp mapping |
| Raw `_source` sai representation | Writing converter hoặc mapping serialization |
| Raw `_source` đúng nhưng Java object sai | Reading converter hoặc entity mapping |
| Get đúng nhưng Search không thấy | Refresh visibility, field index setting, analyzer, query |
| Match query không tìm thấy từ đồng nghĩa/dạng có dấu | Analyzer index/search và token compatibility |
| Test chạy riêng được nhưng chạy cả suite thất bại | Index dùng chung, test song song, cleanup hoặc container lifecycle |

Không sửa analyzer chỉ để che lỗi converter. Cũng không sửa converter để xử lý một field mapping sai kiểu. Mỗi lớp có trách nhiệm riêng và nên có test riêng.

## 15. Cô lập test và dọn dữ liệu

Một integration test ổn định phải có trạng thái đầu vào xác định:

- Dùng container riêng cho test suite hoặc class.
- Tạo index mới trước test.
- Không để document từ test trước ảnh hưởng query.
- Xóa index sau test nếu cần.
- Chờ container sẵn sàng trước khi Spring context tạo client.
- Tắt parallel execution cho test dùng chung index hoặc dùng index name duy nhất.

Ví dụ cleanup:

~~~java
@AfterEach
void deleteTestIndex() {
    IndexOperations indexOperations =
            operations.indexOps(ProductDocument.class);

    if (indexOperations.exists()) {
        indexOperations.delete();
    }
}
~~~

Nếu mỗi test tự xóa và tạo index trước khi chạy, cleanup sau test là lớp bảo vệ bổ sung. Cần tránh hai test cùng xóa index trong khi test còn lại đang ghi.

## 16. Test slice, Spring context và test thực sự cần

Không phải test nào cũng cần khởi chạy cả Spring Boot context:

- Unit test converter thuần có thể không cần Spring context.
- Test `ElasticsearchConverter` cần converter đã đăng ký custom conversions.
- Test analyzer cần Elasticsearch node thật.
- Test vòng save/read cần Spring Data mapping, client và Elasticsearch node.
- Test controller có thể mock repository nếu mục tiêu chỉ là HTTP contract.

Chọn phạm vi nhỏ nhất vẫn chứng minh được hành vi. Nếu dùng `@SpringBootTest`, test sẽ kiểm tra wiring thật nhưng khởi động chậm hơn. Một test slice chỉ phù hợp khi slice đó thực sự nạp các bean Elasticsearch và converter mà test cần.

Đừng mock `ElasticsearchOperations` trong bài test được dùng để chứng minh analyzer hoặc mapping. Mock chỉ xác nhận lời gọi của ứng dụng, không chạy Elasticsearch DSL.

## 17. Bộ test đề xuất

Một bộ test có thể chia như sau:

| Test | Loại | Điều được xác nhận |
|---|---|---|
| Money converter write | Unit | Java value object thành representation ổn định |
| Money converter read | Unit | Representation thành Java value object |
| ElasticsearchConverter round-trip | Mapping test | Spring Data đăng ký và gọi converter đúng |
| Index mapping test | Integration | Index có field type/analyzer mong đợi |
| Analyze API test | Integration | Analyzer tạo token đúng |
| Save/get test | Integration | Một vòng ghi đọc giữ đúng field và kiểu |
| Save/refresh/search test | Integration | Analyzer và mapping hoạt động khi tìm kiếm |
| Legacy format test | Unit/integration | Reader xử lý document cũ theo hợp đồng |

Những test này có thể nằm trong cùng test class hoặc được chia theo tốc độ và trách nhiệm. Không cần lặp lại việc khởi chạy container cho từng test nếu một container class-scoped có thể dùng an toàn; tuy nhiên mỗi test vẫn phải cô lập index và document state.

## 18. Checklist trước khi tin vào một vòng ghi đọc

- [ ] Elasticsearch test version tương thích với client và Spring Data.
- [ ] Test dùng node thật, không mock cho analyzer/mapping behavior.
- [ ] Index được tạo mới với settings và mapping dự kiến.
- [ ] Mapping thực tế được đọc và xác nhận.
- [ ] `_analyze` test dùng field mapping hoặc analyzer được chỉ định rõ.
- [ ] Có input chữ hoa, dấu, dấu câu và trường hợp rỗng phù hợp domain.
- [ ] Custom writing converter được đăng ký.
- [ ] Custom reading converter được đăng ký.
- [ ] Converter round-trip giữ đúng giá trị và kiểu Java.
- [ ] Save entity qua ElasticsearchOperations hoặc repository.
- [ ] Get theo ID xác nhận dữ liệu lưu trữ và converter đọc lại.
- [ ] Refresh trước Search assertion nếu test Search visibility.
- [ ] Match query xác nhận analyzer hoạt động trên document đã index.
- [ ] Test có cleanup và không dùng chung index với môi trường khác.
- [ ] Dữ liệu cũ/format legacy được kiểm thử nếu có migration.

## 19. Kết luận

Kiểm thử analyzer, converter và một vòng ghi đọc cần kiểm tra riêng từng trách nhiệm rồi kết hợp chúng trong integration test. Mapping quyết định field type và analyzer; Analyze API xác nhận tokenizer/filter tạo ra token nào; custom converter quyết định representation của kiểu Java trong Document; vòng save/get xác nhận các phần này phối hợp đúng với Elasticsearch thật.

Hãy dùng Elasticsearch Testcontainers tương thích để tạo index sạch, cài settings/mapping, kiểm tra mapping thực tế và gọi `_analyze` trên field. Kiểm tra converter hai chiều qua `ElasticsearchConverter`, sau đó lưu entity bằng Spring Data và đọc lại theo ID. Nếu cần kiểm tra Search, refresh index trước truy vấn vì Get theo ID và Search có semantics visibility khác nhau.

Một vòng round-trip thành công là bằng chứng tốt cho dữ liệu đã chọn, nhưng không thay thế test analyzer, mapping và các trường hợp biên. Khi các test được tách theo trách nhiệm và dùng cùng cấu hình index với production, lỗi chuyển đổi hoặc tìm kiếm sẽ được phát hiện gần nơi phát sinh hơn.
