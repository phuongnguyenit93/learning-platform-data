# Kiểm thử dữ liệu sau một vòng ghi và đọc

Trong Spring Data Elasticsearch, một object Java không được lưu nguyên dạng trong Elasticsearch. Spring Data chuyển object thành document JSON theo mapping metadata, HTTP client gửi document tới cluster, Elasticsearch lập chỉ mục các field, rồi khi đọc dữ liệu Spring Data chuyển document trả về thành object Java.

Một bài kiểm thử **round-trip** xác nhận toàn bộ đường đi này hoạt động đúng:

~~~text
Object Java
    |
    v
Spring Data mapping / custom converters
    |
    v
Document JSON
    |
    v
Elasticsearch index
    |
    v
Document JSON được đọc lại
    |
    v
Spring Data mapping / custom converters
    |
    v
Object Java sau khi đọc
~~~

Kiểm thử này giúp phát hiện những lỗi mà unit test thông thường không thể thấy, chẳng hạn sai tên field, kiểu dữ liệu không tương thích với mapping, enum chuyển đổi sai, ngày giờ mất độ chính xác, collection không được ánh xạ như mong muốn hoặc custom converter chỉ hoạt động ở một chiều.

## 1. Round-trip test kiểm tra điều gì?

Giả sử ứng dụng lưu một sản phẩm:

~~~java
Product input = new Product(
    "P-1001",
    "SKU-1001",
    "Wireless Mouse",
    259900L,
    true,
    List.of("accessory", "wireless"),
    Instant.parse("2026-11-13T10:15:30.123Z")
);
~~~

Sau khi ghi, ứng dụng đọc document theo ID:

~~~java
operations.save(input);

Product actual = operations.get(
    input.getId(),
    Product.class
);
~~~

Nếu dữ liệu được ánh xạ đúng, object đọc lại phải giữ được các giá trị nghiệp vụ mong đợi.

Một round-trip test nên kiểm tra nhiều lớp:

| Lớp cần kiểm tra | Nội dung |
|---|---|
| Định danh | ID của document được ghi đúng và đọc lại đúng. |
| Tên field | Property Java được ánh xạ tới field Elasticsearch dự kiến. |
| Kiểu dữ liệu | Số, boolean, ngày giờ, enum và collection được chuyển đổi đúng. |
| Cấu trúc lồng nhau | Object con, list và nested field giữ đúng cấu trúc. |
| Giá trị biên | Null, chuỗi rỗng, Unicode, số lớn, thời gian và collection rỗng. |
| Custom conversion | Converter ghi và converter đọc hoạt động theo hai chiều. |
| Mapping thực tế | Index đang chạy có settings và mappings phù hợp với entity. |
| Truy vấn | Document có thể được tìm thấy theo ID hoặc query nghiệp vụ. |

Không nên chỉ kiểm tra object trả về từ chính lời gọi save(). Một số API trả lại object đầu vào hoặc object có ID đã được gán, nhưng điều đó chưa chứng minh document đã được ghi và đọc lại thành công. Hãy thực hiện một thao tác đọc riêng sau khi ghi.

## 2. Phân biệt unit test và integration test

Hai loại kiểm thử có mục đích khác nhau.

**Unit test** phù hợp để kiểm tra logic thuần Java, quy tắc tạo document hoặc custom converter khi có thể gọi converter trực tiếp. Unit test chạy nhanh và không cần Elasticsearch.

**Integration test** cần một Elasticsearch thật để xác nhận HTTP request, index, mapping, serialization, lưu document và đọc lại. Có thể dùng Testcontainers để khởi chạy Elasticsearch riêng cho test.

| Tiêu chí | Unit test | Integration test |
|---|---|---|
| Elasticsearch cần chạy | Không | Có |
| Kiểm tra mapping trên cluster | Không đầy đủ | Có |
| Kiểm tra ghi/đọc thực tế | Không | Có |
| Tốc độ | Nhanh | Chậm hơn |
| Phát hiện lỗi cấu hình server/client | Hạn chế | Tốt hơn |
| Dùng cho | Logic, converter, validator | Round-trip, repository, query và mapping |

Một cách tổ chức hợp lý là giữ unit test cho các quy tắc chuyển đổi nhỏ và dùng integration test cho các luồng quan trọng. Không cần khởi động Elasticsearch cho mọi test của ứng dụng.

## 3. Chuẩn bị Elasticsearch cho integration test

Không nên phụ thuộc vào một Elasticsearch đang chạy trên máy phát triển hoặc một cluster dùng chung. Test cần một môi trường có thể tạo mới, kiểm soát phiên bản và dọn dẹp sau khi chạy.

Testcontainers có thể khởi chạy Elasticsearch trong Docker. Với Gradle, các dependency thường cần có:

~~~groovy
dependencies {
    testImplementation "org.testcontainers:junit-jupiter"
    testImplementation "org.testcontainers:elasticsearch"
}
~~~

Nên quản lý version Testcontainers qua BOM để các module cùng dùng một bộ version tương thích.

Ví dụ cấu hình container với Elasticsearch 8.x:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.StringQuery;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.elasticsearch.ElasticsearchContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class ProductRoundTripIT {

    @Container
    static final ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer(
            DockerImageName.parse(
                "docker.elastic.co/elasticsearch/elasticsearch:8.13.4"
            )
        )
        .withEnv("discovery.type", "single-node")
        .withEnv("xpack.security.enabled", "false");

    @DynamicPropertySource
    static void elasticsearchProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.elasticsearch.uris",
            elasticsearch::getHttpHostAddress
        );
    }
}
~~~

Đây là cấu hình minh họa. Chọn image có phiên bản Elasticsearch tương thích với Elasticsearch client và Spring Data Elasticsearch mà ứng dụng đang sử dụng. Một số cấu hình container hoặc client của các phiên bản khác nhau có thể yêu cầu cách thiết lập authentication/TLS khác. Nếu dùng Elasticsearch có bảo mật bật, hãy truyền thông tin xác thực và cấu hình SSL phù hợp thay vì tắt bảo mật.

@DynamicPropertySource cung cấp URI do container tạo ra cho Spring Boot trước khi application context khởi tạo client. Vì vậy test dùng đúng địa chỉ Elasticsearch của container trong lần chạy đó.

Để chạy được ví dụ, máy hoặc CI runner cần có Docker hoạt động. Nếu môi trường kiểm thử không có Docker, có thể dùng một Elasticsearch service riêng dành riêng cho test, nhưng phải bảo đảm index và dữ liệu được cô lập giữa các lần chạy.

Phần khai báo container ở trên và các test method bên dưới thuộc cùng class `ProductRoundTripIT`. Hãy ghép các field, method cấu hình container và method kiểm thử vào một class duy nhất.

## 4. Khai báo entity dùng trong bài kiểm thử

Ví dụ entity có nhiều kiểu dữ liệu để kiểm tra:

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.DateFormat;

@Document(indexName = "products-roundtrip")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Long)
    private Long priceInCents;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    @Field(type = FieldType.Keyword)
    private List<String> tags;

    @Field(type = FieldType.Date, format = DateFormat.date_time)
    private Instant createdAt;

    protected Product() {
    }

    public Product(
            String id,
            String sku,
            String name,
            Long priceInCents,
            Boolean active,
            List<String> tags,
            Instant createdAt) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.priceInCents = priceInCents;
        this.active = active;
        this.tags = tags;
        this.createdAt = createdAt;
    }

    public String getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public Long getPriceInCents() {
        return priceInCents;
    }

    public Boolean getActive() {
        return active;
    }

    public List<String> getTags() {
        return tags;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

Các kiểu field được chọn có chủ đích:

- id được đánh dấu @Id để làm định danh document.
- sku là keyword để lọc chính xác.
- name là text để tìm kiếm toàn văn.
- priceInCents là số nguyên để biểu diễn giá theo đơn vị nhỏ nhất, tránh sai số nhị phân khi dùng số thực cho tiền.
- active là boolean.
- tags là danh sách giá trị keyword.
- createdAt là thời điểm dạng Instant.

Spring Data cần constructor hoặc cơ chế truy cập phù hợp để tạo object khi đọc. Ví dụ dùng constructor không tham số và getter; có thể bổ sung setter nếu mapping strategy của ứng dụng yêu cầu.

Nếu entity thật có nested object, enum, custom value object hoặc converter riêng, hãy thêm những trường đó vào test. Một test chỉ kiểm tra vài field đơn giản chưa chứng minh mọi kiểu dữ liệu của domain đều round-trip chính xác.

## 5. Tạo index và mapping rõ ràng trong test

Integration test nên xác định rõ index được dùng và mapping cần có. Không nên phụ thuộc hoàn toàn vào dynamic mapping do Elasticsearch tự tạo khi document đầu tiên được ghi.

Với ElasticsearchOperations, có thể dùng IndexOperations:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.document.Document;

IndexOperations indexOperations =
    operations.indexOps(Product.class);

if (indexOperations.exists()) {
    indexOperations.delete();
}

indexOperations.create();

Document mapping = indexOperations.createMapping();
indexOperations.putMapping(mapping);
~~~

Trong test, thao tác này tạo lại index và áp dụng mapping được sinh từ metadata của entity. Nếu entity có settings riêng, chẳng hạn analyzer hoặc normalizer, hãy đưa settings vào quá trình tạo index bằng cơ chế cấu hình tương ứng của phiên bản Spring Data đang dùng.

Đặt phần chuẩn bị index trong @BeforeEach nếu muốn mỗi test có dữ liệu độc lập. Nếu index creation tốn thời gian và các test có thể dùng chung index an toàn, có thể tạo một lần trong @BeforeAll, sau đó dùng ID riêng và dọn dữ liệu theo từng test.

Không chạy các test ghi/xóa trên index production hoặc cluster dùng chung. Hãy dùng tên index có suffix test hoặc một container riêng.

## 6. Kiểm thử một vòng ghi và đọc bằng ElasticsearchOperations

Ví dụ test sau thực hiện thao tác ghi, sau đó đọc document riêng theo ID:

Các import đã được minh họa ở phần entity và cấu hình container; đoạn dưới đây là phần thân bổ sung cho class `ProductRoundTripIT` ở trên.

~~~java
    @Autowired
    ElasticsearchOperations operations;

    private IndexOperations indexOperations;

    @BeforeEach
    void prepareIndex() {
        indexOperations = operations.indexOps(Product.class);

        if (indexOperations.exists()) {
            indexOperations.delete();
        }

        indexOperations.create();
        indexOperations.putMapping(indexOperations.createMapping());
    }

    @Test
    void shouldWriteAndReadProduct() {
        Instant createdAt = Instant.parse(
            "2026-11-13T10:15:30.123Z"
        );

        Product expected = new Product(
            "P-1001",
            "SKU-1001",
            "Wireless Mouse",
            259900L,
            true,
            List.of("accessory", "wireless"),
            createdAt
        );

        operations.save(expected);

        Product actual = operations.get(
            expected.getId(),
            Product.class
        );

        assertNotNull(actual);
        assertEquals(expected.getId(), actual.getId());
        assertEquals(expected.getSku(), actual.getSku());
        assertEquals(expected.getName(), actual.getName());
        assertEquals(
            expected.getPriceInCents(),
            actual.getPriceInCents()
        );
        assertEquals(expected.getActive(), actual.getActive());
        assertEquals(expected.getTags(), actual.getTags());
        assertEquals(expected.getCreatedAt(), actual.getCreatedAt());
    }
~~~

Điều quan trọng là test gọi operations.get(...) sau operations.save(...). Đây là một lần đọc riêng từ Elasticsearch, vì vậy nó kiểm tra cả bước ghi lẫn bước chuyển đổi document trở lại object.

ElasticsearchOperations.get dùng thao tác lấy document theo ID. Get API của Elasticsearch có tính realtime đối với document đã được ghi thành công, nên không cần refresh index chỉ để đọc lại theo ID như ví dụ trên.

Nếu phiên bản Spring Data đang dùng có chữ ký API khác, điều chỉnh theo đúng version của project. Nguyên tắc test vẫn là lưu object, sau đó thực hiện một lần đọc độc lập và so sánh từng giá trị quan trọng.

## 7. Kiểm tra qua Repository

Nếu ứng dụng sử dụng repository, nên có ít nhất một integration test xác nhận repository hoạt động với mapping thực tế:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Test:

~~~java
@Autowired
ProductRepository productRepository;

@Test
void shouldRoundTripThroughRepository() {
    Product expected = new Product(
        "P-2001",
        "SKU-2001",
        "Mechanical Keyboard",
        1899000L,
        true,
        List.of("keyboard", "mechanical"),
        Instant.parse("2026-11-13T11:00:00.000Z")
    );

    productRepository.save(expected);

    Product actual = productRepository.findById("P-2001")
        .orElseThrow();

    assertEquals(expected.getSku(), actual.getSku());
    assertEquals(expected.getName(), actual.getName());
    assertEquals(
        expected.getPriceInCents(),
        actual.getPriceInCents()
    );
    assertEquals(expected.getTags(), actual.getTags());
}
~~~

Test repository giúp xác nhận wiring giữa repository, mapping context và Elasticsearch client. Nếu ứng dụng dùng ElasticsearchOperations trực tiếp trong service, hãy test cả service đó ở tầng phù hợp.

Không cần lặp lại cùng một tập assertion trong hàng chục test repository. Hãy chọn các trường hợp đại diện để xác nhận hành vi của abstraction mà ứng dụng thực sự dùng.

## 8. Phân biệt Get API và Search API khi kiểm thử

Một lỗi thường gặp là ghi document rồi lập tức chạy search và cho rằng kết quả rỗng đồng nghĩa thao tác ghi thất bại.

Elasticsearch là hệ thống near-real-time đối với tìm kiếm. Document vừa được index có thể chưa xuất hiện trong Search API cho đến lần refresh tiếp theo. Trong khi đó, Get API theo ID có thể đọc document mới ngay sau khi ghi.

Vì vậy:

- Dùng operations.get(id, ...) để kiểm tra round-trip theo ID.
- Nếu cần kiểm tra query tìm kiếm, hãy refresh index trong test trước khi search.
- Không ép refresh sau mọi lần ghi trong production chỉ để có kết quả tức thì.

Ví dụ:

~~~java
operations.save(expected);

indexOperations.refresh();

SearchHits<Product> hits = operations.search(
    new StringQuery("""
        {"term":{"sku":"SKU-1001"}}
        """),
    Product.class
);

assertEquals(1, hits.getTotalHits());
assertEquals("P-1001", hits.getSearchHit(0).getContent().getId());
~~~

IndexOperations.refresh() yêu cầu Elasticsearch làm cho các thay đổi đã index có thể được nhìn thấy trong search. Đây là cách rõ ràng cho integration test cần kiểm tra Search API. Với các test chạy song song hoặc nhiều test dùng chung index, cần cô lập dữ liệu bằng ID duy nhất và tránh refresh/cleanup ảnh hưởng lẫn nhau.

## 9. Kiểm tra document JSON thực tế

Nếu round-trip test thất bại, cần biết lỗi nằm ở bước ghi hay bước đọc. Có thể đọc document trực tiếp bằng Elasticsearch REST API:

~~~http
GET /products-roundtrip/_doc/P-1001
~~~

Response có dạng:

~~~json
{
  "_index": "products-roundtrip",
  "_id": "P-1001",
  "found": true,
  "_source": {
    "sku": "SKU-1001",
    "name": "Wireless Mouse",
    "priceInCents": 259900,
    "active": true,
    "tags": [
      "accessory",
      "wireless"
    ],
    "createdAt": "2026-11-13T10:15:30.123Z"
  }
}
~~~

So sánh _source với object đầu vào:

- Nếu _source sai, kiểm tra mapping metadata, converter ghi, tên field và kiểu dữ liệu khi serialize.
- Nếu _source đúng nhưng object đọc sai, kiểm tra converter đọc, constructor, property access và kiểu Java.
- Nếu document không tồn tại, kiểm tra ID, index đích, quyền ghi và response của thao tác save.

_source là nội dung JSON được lưu để truy xuất document. Nó không cho biết toàn bộ term đã được phân tích hoặc chuẩn hóa trong inverted index. Nếu cần kiểm tra analyzer/normalizer, hãy dùng Analyze API và kiểm tra mapping.

## 10. Những kiểu dữ liệu cần kiểm thử kỹ

### 10.1. Ngày giờ và độ chính xác

Elasticsearch date thường được lưu dưới dạng số mili giây kể từ epoch hoặc chuỗi ngày theo format mapping. Độ chính xác phổ biến của date là milliseconds.

Nếu object Java dùng Instant với nanoseconds, dữ liệu đọc lại có thể không giữ đủ phần nanosecond. Ví dụ:

~~~java
Instant value = Instant.parse(
    "2026-11-13T10:15:30.123456789Z"
);
~~~

Khi round-trip qua date field có độ chính xác mili giây, không nên mặc định rằng kết quả sẽ bằng tuyệt đối giá trị nanosecond ban đầu. Có thể chuẩn hóa dữ liệu đầu vào:

~~~java
Instant normalized = value.truncatedTo(
    ChronoUnit.MILLIS
);
~~~

Hoặc trong test, so sánh theo độ chính xác mà hệ thống cam kết. Quan trọng là định nghĩa rõ format, timezone và độ chính xác của thời gian nghiệp vụ.

### 10.2. Số nguyên và số thực

Các kiểu long, integer, double và float có giới hạn biểu diễn khác nhau. Kiểm thử nên bao gồm:

- Giá trị nhỏ và giá trị lớn gần giới hạn kiểu Java.
- Giá trị âm nếu nghiệp vụ cho phép.
- Null nếu field nullable.
- Giá trị thập phân nếu mapping là float/double.

Với tiền tệ, thường nên lưu số nguyên theo đơn vị nhỏ nhất (ví dụ cents) hoặc dùng chiến lược scaled_float có scaling factor được thiết kế rõ ràng. Tránh so sánh số thực bằng equality nếu phép chuyển đổi có thể tạo sai số làm tròn.

### 10.3. Enum

Nếu field Java là enum, hãy kiểm tra dạng được ghi vào _source và cách đọc lại. Thông thường Spring Data có thể chuyển enum thành tên chuỗi, nhưng nếu ứng dụng có custom converter thì phải xác nhận quy tắc cụ thể.

Ví dụ, enum:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

Test cần xác nhận PAID được ghi và đọc lại thành đúng enum. Nếu muốn lưu mã khác tên enum, hãy kiểm thử converter hai chiều và tính tương thích khi enum được đổi tên.

### 10.4. Collection và object lồng nhau

Một field List<String> cần kiểm tra thứ tự phần tử nếu thứ tự có ý nghĩa ở tầng ứng dụng. Elasticsearch có thể lưu array trong _source, nhưng semantics tìm kiếm của array không giống cấu trúc list có thứ tự trong mọi query.

Với object lồng nhau, phân biệt object và nested mapping. Nếu cần truy vấn các thuộc tính phải thuộc cùng một phần tử trong array object, nested có semantics riêng. Round-trip test nên xác nhận cả cấu trúc dữ liệu đọc lại và query trên nested field nếu ứng dụng sử dụng nó.

### 10.5. Null, field vắng mặt và giá trị mặc định

Một property Java null có thể không được serialize thành field trong _source, tùy cấu hình mapping/converter. Khi đọc lại, property có thể vẫn null hoặc nhận giá trị mặc định từ constructor.

Hãy phân biệt:

- Field có giá trị null.
- Field không xuất hiện trong JSON.
- Field được gán giá trị mặc định trong Java.
- Field bị loại trừ bởi cấu hình source hoặc converter.

Nếu nghiệp vụ cần phân biệt "không có dữ liệu" với "giá trị rỗng", test phải xác nhận semantics này.

### 10.6. Unicode và ký tự đặc biệt

Kiểm thử chuỗi có dấu tiếng Việt, ký tự emoji, dấu nháy, ký tự escape, khoảng trắng và chuỗi dài. Những trường hợp này giúp phát hiện lỗi encoding hoặc custom converter không xử lý Unicode đúng.

Không chỉ assert rằng object không null. Hãy so sánh nội dung chuỗi chính xác nếu dữ liệu phải được giữ nguyên.

## 11. Kiểm thử custom converter theo hai chiều

Spring Data Elasticsearch cho phép đăng ký custom conversions để chuyển kiểu domain sang dạng Elasticsearch có thể lưu và chuyển ngược lại khi đọc.

Ví dụ domain có value object:

~~~java
public record Money(long amountInCents, String currency) {
}
~~~

Nếu ứng dụng có converter chuyển Money thành chuỗi hoặc một cấu trúc document riêng, hãy kiểm thử cả hai chiều:

~~~text
Money trong Java
      |
      v
Writing Converter
      |
      v
Dạng JSON / giá trị lưu trong Elasticsearch
      |
      v
Reading Converter
      |
      v
Money trong Java
~~~

Các trường hợp cần kiểm tra:

- Writing converter tạo đúng representation.
- Reading converter khôi phục đúng giá trị.
- Currency, scale và đơn vị tiền không bị mất.
- Giá trị null được xử lý nhất quán.
- Dữ liệu cũ vẫn đọc được nếu representation thay đổi theo phiên bản.

Có thể viết unit test trực tiếp cho converter để kiểm tra logic nhanh, sau đó có ít nhất một integration test round-trip để xác nhận Spring Data thực sự đăng ký và sử dụng converter đó trong mapping context. Một converter chạy đúng khi gọi thủ công chưa chắc đã được đăng ký vào client mà repository đang sử dụng.

## 12. Kiểm thử mapping và query cùng với round-trip

Round-trip theo ID xác nhận dữ liệu có thể được đọc lại, nhưng chưa đủ để chứng minh query nghiệp vụ hoạt động.

Ví dụ entity có:

- sku là keyword.
- name là text.
- active là boolean.

Có thể kiểm tra hai loại truy vấn khác nhau:

~~~http
GET /products-roundtrip/_search
{
  "query": {
    "term": {
      "sku": "SKU-1001"
    }
  }
}
~~~

và:

~~~http
GET /products-roundtrip/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  }
}
~~~

Test cần xác nhận mapping đúng với query được sử dụng. Ví dụ dùng term cho field text đã phân tích thường không có semantics giống match; ngược lại match trên keyword không tách từ như text.

Nếu ứng dụng dùng normalizer, analyzer, nested query, alias hoặc multi-fields, hãy thêm test cho những cấu hình đó. Round-trip object thành công không đồng nghĩa mọi query sẽ có kết quả đúng.

## 13. Cô lập dữ liệu giữa các test

Test chạy lặp lại phải cho kết quả ổn định. Một số cách cô lập thường dùng:

**Tạo lại index trước mỗi test.** Cách này đơn giản, phù hợp với bộ test nhỏ. Chi phí tạo index tăng khi số test lớn.

**Dùng ID duy nhất cho mỗi test.** Có thể dùng UUID hoặc suffix theo test case để tránh ghi đè document của test khác.

**Dùng index riêng theo test class hoặc worker.** Cách này hữu ích khi test chạy song song. Tên index nên tuân thủ quy tắc lowercase và ký tự hợp lệ của Elasticsearch.

**Xóa dữ liệu sau test.** Có thể xóa document theo ID hoặc xóa index test. Đảm bảo cleanup không chạy nhầm trên môi trường khác.

Nếu dùng một container dùng chung cho cả class, tránh để test phụ thuộc vào thứ tự chạy. Một test không nên cần dữ liệu do test trước tạo ra trừ khi đó là một scenario có chủ đích.

Khi test chạy song song, không dùng cùng một index và ID cố định nếu các test có thể ghi/xóa lẫn nhau. Hãy tạo namespace riêng cho mỗi class hoặc test worker.

## 14. Ma trận test round-trip nên có

Một bộ test thực tế có thể tổ chức theo các nhóm sau:

| Nhóm | Dữ liệu đầu vào | Điều cần xác nhận |
|---|---|---|
| Giá trị cơ bản | ID, chuỗi, số, boolean | Ghi và đọc đúng mọi field |
| Collection | List rỗng, list nhiều phần tử | Cấu trúc và giá trị được giữ đúng |
| Date/time | Instant có mili giây, timezone | Format và độ chính xác đúng |
| Null/default | Property null, field vắng mặt | Semantics null/default đúng |
| Unicode | Tiếng Việt, emoji, ký tự đặc biệt | Encoding và nội dung không mất |
| Enum | Mỗi trạng thái nghiệp vụ | Representation và chuyển đổi đúng |
| Nested | Object và list object | Cấu trúc và truy vấn nested đúng |
| Custom converter | Value object riêng | Cả chiều ghi và chiều đọc |
| Mapping/query | Keyword, text, normalizer | Query nghiệp vụ trả đúng document |
| Update | Ghi lần đầu, cập nhật field | Giá trị mới được đọc lại, field khác không bị mất ngoài ý muốn |

Không nhất thiết mọi nhóm phải là một test method riêng. Có thể dùng parameterized test cho các giá trị biên và giữ các scenario phức tạp thành test riêng để thông báo lỗi dễ hiểu.

## 15. Chẩn đoán khi round-trip test thất bại

Khi assertion sai, đừng vội thay mapping. Hãy xác định dữ liệu sai ở giai đoạn nào.

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không tìm thấy document | Sai ID, index hoặc thao tác ghi thất bại | Đọc response ghi, kiểm tra index và Get API trực tiếp |
| Field bị null sau khi đọc | Sai tên field, mapping constructor hoặc converter | Xem _source, mapping và object mapping metadata |
| Số đọc lại khác số ghi | Kiểu số không tương thích hoặc precision | Kiểm tra JSON, field type và phép chuyển đổi |
| Ngày giờ lệch | Format/timezone hoặc precision milliseconds | Kiểm tra _source, format mapping và timezone |
| Collection rỗng hoặc mất phần tử | Mapping/converter hoặc JSON representation sai | Kiểm tra _source và kiểu property |
| Enum không đọc được | Giá trị lưu không tương ứng enum hoặc converter lỗi | Kiểm tra chuỗi trong _source và reading converter |
| Get thành công nhưng Search không thấy | Chưa refresh hoặc query sai | Refresh index trong test, kiểm tra mapping/query |
| Mapping không đúng | Index được tạo trước khi settings/annotation mong muốn áp dụng | Đọc _mapping, _settings; tạo lại index test |
| Test chạy riêng pass nhưng chạy cả suite fail | Dữ liệu hoặc index dùng chung | Cô lập index/ID, kiểm tra cleanup và parallel execution |

Một quy trình điều tra hữu ích:

1. Kiểm tra exception hoặc response của thao tác ghi.
2. Dùng Get API theo ID để xác nhận document có tồn tại.
3. Đọc _source để xác nhận JSON được ghi.
4. Đọc mapping để xác nhận kiểu field và tên field.
5. Đọc lại qua Spring Data để kiểm tra chiều chuyển đổi về Java.
6. Nếu test query, refresh index rồi kiểm tra query và analyzer/normalizer.
7. Kiểm tra custom conversions và constructor nếu chỉ một số property sai.

Nếu _source đã sai ngay sau khi ghi, tập trung vào chiều serialize và mapping. Nếu _source đúng nhưng object đọc sai, tập trung vào chiều deserialize và converter. Cách phân tách này giúp tìm nguyên nhân nhanh hơn.

## 16. Lưu ý về refresh, retry và tính lặp lại của test

Không nên gọi refresh một cách máy móc sau mọi lần ghi. Với test Get API theo ID, thường không cần refresh. Với test Search API, refresh giúp kết quả nhìn thấy document vừa index.

Không retry assertion liên tục để che giấu lỗi timing. Nếu Search cần refresh, hãy yêu cầu refresh một cách tường minh hoặc cấu hình chính sách refresh phù hợp trong môi trường test. Nếu thao tác ghi trả lỗi, hãy đọc exception gốc trước khi thử lại.

Test round-trip nên có tính lặp lại:

- Dùng dữ liệu xác định.
- Dùng index cô lập.
- Tạo mapping rõ ràng.
- Không phụ thuộc thứ tự test.
- Không dựa vào dữ liệu tồn tại từ lần chạy trước.
- Cleanup có phạm vi chính xác.
- Dùng phiên bản Elasticsearch cố định và tương thích với client.

Trong production, không nên ép refresh sau mỗi lần ghi chỉ để đọc ngay qua search. Test có thể dùng refresh chủ động để xác nhận hành vi search, còn ứng dụng thật nên chọn refresh policy theo yêu cầu độ mới và hiệu năng.

## 17. Checklist trước khi kết luận round-trip đã đúng

Một test round-trip có giá trị khi nó thực sự đi qua Elasticsearch và kiểm tra những field quan trọng của domain. Trước khi kết luận, hãy xác nhận:

- Test kết nối tới Elasticsearch test riêng và phiên bản tương thích.
- Index được tạo với settings và mapping mong muốn.
- Object đầu vào được ghi bằng API của Spring Data mà ứng dụng sử dụng.
- Test đọc document bằng một thao tác riêng sau khi ghi.
- ID và các field nghiệp vụ quan trọng được so sánh.
- Date/time, số, enum, collection, null và nested field được kiểm tra theo yêu cầu.
- Custom converter được kiểm tra cả chiều ghi và chiều đọc.
- Nếu kiểm tra Search, index đã được refresh và query phù hợp mapping.
- Có thể kiểm tra _source để phân biệt lỗi serialize với deserialize.
- Test cô lập dữ liệu, chạy độc lập và không tác động cluster dùng chung.

Kiểm thử sau một vòng ghi và đọc giúp xác nhận Spring Data Elasticsearch chuyển đổi object đúng qua mapping, ghi document vào index và khôi phục dữ liệu thành object Java. Hãy dùng unit test cho logic chuyển đổi thuần, integration test với Elasticsearch thật cho round-trip, đọc lại bằng thao tác riêng, so sánh các giá trị nghiệp vụ và kiểm tra _source khi có sai lệch.
