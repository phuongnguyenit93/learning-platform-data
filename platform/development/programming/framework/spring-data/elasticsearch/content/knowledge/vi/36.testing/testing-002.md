# Phạm vi tự cấu hình của @DataElasticsearchTest

`@DataElasticsearchTest` là test slice của Spring Boot dành cho Spring Data Elasticsearch. Annotation này tạo một `ApplicationContext` tập trung vào phần truy cập dữ liệu Elasticsearch: cấu hình client/template phù hợp, converter, repository và các entity được đánh dấu `@Document`. Nó giúp kiểm thử repository và mapping mà không phải khởi tạo toàn bộ ứng dụng.

Điểm quan trọng là hiểu **phạm vi bean được tự cấu hình**. `@DataElasticsearchTest` không phải phiên bản rút gọn của `@SpringBootTest` theo nghĩa chỉ bỏ web server. Nó dùng cơ chế test slicing để giới hạn auto-configuration và component scanning. Các `@Component`, service, controller và `@ConfigurationProperties` thông thường không tự động được đưa vào context chỉ vì chúng nằm trong package ứng dụng. Khi test cần một bean ngoài slice, hãy import hoặc bật đúng cấu hình đó một cách có chủ đích.

Annotation cũng không tự khởi chạy một Elasticsearch server nhúng. Test cần kết nối tới một Elasticsearch instance có thể truy cập được, chẳng hạn container dùng cho integration test hoặc service test riêng. Cấu hình kết nối được lấy từ Spring Boot Environment giống các cấu hình Elasticsearch khác.

## 1. Test slice là gì?

Một ứng dụng Spring Boot thường có nhiều loại bean:

- Web layer: controller, filter, handler, web configuration.
- Application layer: service điều phối use case.
- Persistence layer: Spring Data repositories, template/operations, converter.
- Integration: HTTP clients, message producers, event handlers.
- Configuration: `@Configuration`, `@ConfigurationProperties` và các bean dùng chung.

Khi kiểm thử repository, phần lớn các bean trên không cần thiết. Khởi tạo toàn bộ context làm test chậm hơn, tăng số dependency cần chuẩn bị và khiến lỗi ở một thành phần không liên quan có thể làm test repository thất bại.

Test slice tạo context nhỏ hơn, chỉ bật nhóm auto-configuration và thành phần cần cho một khu vực. `@DataElasticsearchTest` là slice cho Elasticsearch:

```java
import org.springframework.boot.test.autoconfigure.data.elasticsearch.DataElasticsearchTest;
import org.springframework.beans.factory.annotation.Autowired;

@DataElasticsearchTest
class ProductRepositoryTests {

    @Autowired
    ProductRepository products;

    // Tests for repository queries and Elasticsearch mapping.
}
```

Trong ví dụ, Spring Boot tìm repository Spring Data Elasticsearch và entity `@Document`, sau đó cấu hình các thành phần Elasticsearch cần thiết cho thao tác dữ liệu. Test không cần khởi tạo controller, service hoặc web server nếu mục tiêu chỉ là kiểm tra repository.

### 1.1 So sánh với @SpringBootTest

| Tiêu chí | `@DataElasticsearchTest` | `@SpringBootTest` |
|---|---|---|
| Phạm vi | Slice tập trung vào Elasticsearch data layer | Có thể tải gần như toàn bộ application context |
| Repository Elasticsearch | Được cấu hình để kiểm thử | Được cấu hình nếu auto-configuration và scan của ứng dụng bật |
| Entity `@Document` | Được scan theo quy tắc slice | Được tìm theo cấu hình ứng dụng |
| Service/controller thông thường | Không tự scan | Thường được scan từ application configuration |
| Web environment | Không phải mục tiêu của slice | Có thể mock hoặc khởi chạy server |
| Thời gian khởi tạo | Thường nhỏ hơn | Thường lớn hơn |
| Use case phù hợp | Repository, mapping, query, template | Kiểm thử tích hợp nhiều tầng hoặc toàn ứng dụng |

Không cần chọn `@SpringBootTest` chỉ vì repository test cần kết nối Elasticsearch thật. `@DataElasticsearchTest` vẫn có thể dùng một Elasticsearch server thật; khác biệt nằm ở phạm vi Spring context, không phải việc database có thật hay giả.

### 1.2 Test slice không phải mock repository

`@DataElasticsearchTest` không mặc định thay repository bằng Mockito mock. Mục đích của nó là cấu hình Spring Data Elasticsearch để test tương tác với Elasticsearch. Nếu chỉ muốn unit test service và không cần kiểm tra mapping/query thực tế, có thể dùng Mockito trong test không tải Spring context.

Ngược lại, nếu cần kiểm tra query DSL, mapping, converter, analyzer hoặc hành vi repository thật, hãy dùng test slice với một Elasticsearch instance phù hợp.

## 2. Những gì @DataElasticsearchTest tự cấu hình

Ở mức khái niệm, slice này bật cấu hình liên quan đến Spring Data Elasticsearch và giới hạn component scan vào các thành phần dữ liệu Elasticsearch.

Các thành phần thường có trong context:

- Spring Data Elasticsearch repositories được phát hiện trong phạm vi scan.
- Entity được đánh dấu `@Document`.
- Elasticsearch client và cấu hình kết nối do Spring Boot auto-configuration cung cấp.
- Template/Operations và converter tương ứng với dòng Spring Data Elasticsearch đang dùng.
- Index operations và mapping metadata cần thiết cho thao tác dữ liệu.
- Các auto-configuration test/data liên quan được import bởi slice.

Tên class cụ thể của template/client thay đổi theo thế hệ Spring Data Elasticsearch. Ví dụ các phiên bản cũ có `ElasticsearchRestTemplate`; các phiên bản mới có `ElasticsearchTemplate` dựa trên Elasticsearch Java API Client. Khi đọc ví dụ hoặc kiểm tra bean, hãy dùng đúng API của dependency trong dự án.

Ví dụ inject template:

```java
@DataElasticsearchTest
class ProductTemplateTests {

    @Autowired
    ElasticsearchOperations operations;

    @Autowired
    ProductRepository products;
}
```

`ElasticsearchOperations` là abstraction phù hợp khi test cần kiểm tra hành vi template mà không muốn phụ thuộc trực tiếp vào implementation class. Nếu cần kiểm tra API cụ thể của template, có thể inject implementation mà phiên bản đang dùng cung cấp.

### 2.1 Repository và entity được scan

Slice tìm các repository Spring Data Elasticsearch và các entity được đánh dấu `@Document` theo quy tắc scan của Spring Boot. Vì vậy repository có thể được inject mà không cần khai báo thủ công từng bean:

```java
@Document(indexName = "products-test")
class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;
}

interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Optional<ProductDocument> findBySku(String sku);
}
```

Ví dụ rút gọn để minh họa mapping và repository. Trong ứng dụng thật, entity/repository thường là public top-level type và nằm trong package được cấu hình scan.

### 2.2 Không scan tất cả component

`@DataElasticsearchTest` không tự động đưa các bean `@Component` thông thường vào context. Điều này bao gồm nhiều loại bean như:

- `@Service`.
- `@Controller` / `@RestController`.
- Component custom.
- Component chứa business logic.
- Các class cấu hình không thuộc phần auto-configuration của slice.
- `@ConfigurationProperties` bean nếu chưa bật đăng ký tương ứng.

Ví dụ:

```java
@Service
class ProductPricingService {
    // Business logic.
}
```

Không nên giả định `ProductPricingService` sẽ được inject chỉ vì package của nó nằm dưới package chứa `@SpringBootApplication`. Nếu test cần service, import service/configuration cần thiết hoặc chuyển sang `@SpringBootTest` nếu mục tiêu là kiểm thử integration giữa nhiều tầng.

### 2.3 Không tự khởi tạo Elasticsearch nhúng

Khác với một số slice database quan hệ có thể tự chọn embedded database nếu dependency phù hợp có trên classpath, Elasticsearch slice không có một embedded Elasticsearch server mặc định để mỗi test tự khởi chạy. Test cần một endpoint Elasticsearch đang hoạt động và cấu hình kết nối đúng.

Do đó, context có thể khởi tạo thành công nhưng request đầu tiên tới repository thất bại vì Elasticsearch không chạy, sai URI, sai credential, TLS hoặc network. Đây là lỗi hạ tầng kết nối, không phải bằng chứng repository scan bị thiếu.

## 3. Cấu trúc meta-annotation và ý nghĩa của scope

`@DataElasticsearchTest` được xây dựng từ các annotation Spring Boot test khác. Trong các dòng Spring Boot 3.x, API của annotation thể hiện các thành phần như:

- `@BootstrapWith`: chọn context bootstrapper riêng cho Elasticsearch test slice.
- `@ExtendWith(SpringExtension.class)`: tích hợp Spring TestContext với JUnit Jupiter.
- `@OverrideAutoConfiguration(enabled = false)`: không bật toàn bộ auto-configuration như một ứng dụng đầy đủ.
- `@TypeExcludeFilters`: áp dụng filter để giới hạn component scanning cho slice.
- `@AutoConfigureDataElasticsearch`: bật auto-configuration dành cho Elasticsearch test.
- `@ImportAutoConfiguration`: nhập các auto-configuration được chọn cho slice.

Một số bản Spring Boot 3.x còn có các annotation cấu hình test phụ như `@AutoConfigureCache`. Danh sách meta-annotation và package có thể thay đổi theo major version; không nên sao chép nguyên import hoặc nội bộ annotation từ một release khác.

Ý nghĩa thực tế: slice không chỉ là một tập bean được tạo sẵn. Nó còn điều khiển auto-configuration và loại component nào được phép đi vào `ApplicationContext`.

### 3.1 Auto-configuration bị giới hạn

`@OverrideAutoConfiguration(enabled = false)` ngăn việc bật toàn bộ auto-configuration thông thường theo cách của full application context. Các auto-configuration cần cho slice được import có chọn lọc.

Điều này giải thích vì sao một bean tự động có trong ứng dụng khi chạy thật có thể không tồn tại trong `@DataElasticsearchTest`. Nếu bean đó không thuộc phần auto-configuration của Elasticsearch slice, hãy bổ sung cấu hình rõ ràng hoặc dùng một loại test phù hợp hơn.

### 3.2 Type exclude filter

Type exclude filter là cơ chế giúp component scan tôn trọng ranh giới slice. Spring Boot dùng filter để loại các loại component không thuộc slice, kể cả khi chúng nằm trong package được scan.

Đây là lý do một service hoặc controller cùng package với repository không tự động xuất hiện trong context. Package nằm trong phạm vi scan không đồng nghĩa mọi stereotype bean đều được đưa vào.

### 3.3 Không nên vô hiệu hóa slice filter tùy tiện

Nếu context thiếu một bean, đừng lập tức bật toàn bộ component scan hoặc thêm `@SpringBootTest`. Trước tiên xác định bean đó thuộc loại nào:

- Entity/repository: kiểm tra package và annotation.
- Configuration properties: dùng `@EnableConfigurationProperties`.
- Bean test riêng: dùng `@TestConfiguration`.
- Bean component cần dùng trong test: dùng `@Import` hoặc include filter.
- Auto-configuration bổ sung: dùng `@ImportAutoConfiguration`.
- Nhiều tầng ứng dụng cần chạy cùng nhau: cân nhắc `@SpringBootTest`.

Chọn cơ chế bổ sung theo đúng loại bean giúp giữ test context nhỏ và dễ hiểu.

## 4. Phạm vi component scan và primary configuration

Spring Boot thường tìm primary configuration từ package của test đi ngược lên cho tới khi tìm thấy class `@SpringBootApplication` hoặc `@SpringBootConfiguration`. Primary configuration này cung cấp thông tin gốc để xây context.

Tuy nhiên, nếu application class khai báo `@ComponentScan` tùy chỉnh, filter mặc định phục vụ test slicing có thể bị vô hiệu hóa. Khi đó slice có thể bất ngờ scan thêm service, controller hoặc configuration mà lẽ ra phải bị loại.

Ví dụ cấu hình dễ gây bất ngờ:

```java
@SpringBootApplication
@ComponentScan("com.example")
public class Application {
}
```

`@ComponentScan` trực tiếp có thể ghi đè cấu hình scan mặc định mà Spring Boot sử dụng để hỗ trợ slice. Khi test `@DataElasticsearchTest` thấy quá nhiều bean, hãy kiểm tra component scan trên primary configuration trước khi thêm exclude filter ở từng test.

### 4.1 Tách component scan tùy chỉnh

Nếu ứng dụng cần scan package đặc biệt, cân nhắc tách cấu hình đó khỏi primary `@SpringBootApplication`:

```java
@SpringBootApplication
public class Application {
}

@Configuration
@ComponentScan("com.example.integration")
class IntegrationComponentsConfiguration {
}
```

Chỉ import `IntegrationComponentsConfiguration` ở context cần nó. Cách này giúp test slice giữ được filter mặc định và tránh kéo component ngoài scope vào mọi test.

### 4.2 Dùng @SpringBootConfiguration riêng khi cần

Nếu primary configuration của ứng dụng có cấu trúc scan đặc biệt và không thể thay đổi, có thể cung cấp một `@SpringBootConfiguration` test phù hợp hoặc chỉ định configuration source cho test. Đây là cách điều khiển nguồn cấu hình, nhưng cần bảo đảm class test configuration không vô tình biến slice thành full application scan.

## 5. Bổ sung bean cần thiết bằng @Import

Nếu test cần một component cụ thể ngoài slice, có thể import class đó:

```java
@DataElasticsearchTest
@Import(ProductProjectionMapper.class)
class ProductRepositoryTests {

    @Autowired
    ProductRepository products;

    @Autowired
    ProductProjectionMapper mapper;
}
```

`@Import` đăng ký class được chỉ định vào context. Nó hữu ích khi test cần một mapper, converter adapter hoặc component nhỏ có dependency đã có trong slice.

Không nên import toàn bộ package hoặc một configuration kéo theo nhiều service và client không liên quan. Mỗi import nên thể hiện một dependency mà test thực sự cần.

### 5.1 Import nhiều bean qua test configuration

Với nhiều bean chỉ dùng trong test, dùng nested `@TestConfiguration`:

```java
@DataElasticsearchTest
class ProductRepositoryTests {

    @Autowired
    ProductRepository products;

    @TestConfiguration(proxyBeanMethods = false)
    static class TestBeans {

        @Bean
        ProductFixtureFactory productFixtureFactory() {
            return new ProductFixtureFactory();
        }
    }
}
```

`@TestConfiguration` được dùng bổ sung cho primary configuration. Nested class không thay thế application configuration mà test slice đang sử dụng. `proxyBeanMethods = false` phù hợp khi các method bean không gọi lẫn nhau qua method Java.

Nếu `TestConfiguration` là top-level class, có thể import rõ ràng vào test:

```java
@DataElasticsearchTest
@Import(ProductElasticsearchTestConfiguration.class)
class ProductRepositoryTests {
}
```

### 5.2 Phân biệt @Configuration và @TestConfiguration

Một nested class chỉ gắn `@Configuration` có thể được xem như nguồn cấu hình thay thế trong một số cách bootstrap test. `@TestConfiguration` được thiết kế để bổ sung cấu hình test mà vẫn giữ primary configuration được phát hiện từ ứng dụng.

Khi muốn thêm bean cho một slice, nested `@TestConfiguration` thường diễn đạt đúng ý định hơn. Nếu dùng top-level test configuration, import rõ ràng để tránh component scan tự động đưa nó vào những context không liên quan.

## 6. Đăng ký @ConfigurationProperties có chọn lọc

`@DataElasticsearchTest` không tự scan mọi `@ConfigurationProperties` bean. Nếu một cấu hình có kiểu properties cần cho test, đăng ký nó bằng `@EnableConfigurationProperties`:

```java
@ConfigurationProperties(prefix = "catalog.search")
public class CatalogSearchProperties {

    private int defaultPageSize = 20;

    public int getDefaultPageSize() {
        return defaultPageSize;
    }

    public void setDefaultPageSize(int defaultPageSize) {
        this.defaultPageSize = defaultPageSize;
    }
}
```

Test:

```java
@DataElasticsearchTest
@EnableConfigurationProperties(CatalogSearchProperties.class)
class ProductRepositoryTests {

    @Autowired
    CatalogSearchProperties properties;
}
```

Nếu properties chỉ được dùng bởi một service ngoài slice, có thể import service và đăng ký properties tương ứng. Không cần bật toàn bộ configuration properties scanning của ứng dụng nếu test chỉ cần một class.

## 7. Điều khiển properties của test

Annotation hỗ trợ thuộc tính `properties` để thêm property vào Spring Environment trước khi context chạy:

```java
@DataElasticsearchTest(properties = {
    "spring.elasticsearch.uris=http://localhost:9200",
    "spring.elasticsearch.connection-timeout=2s",
    "spring.elasticsearch.socket-timeout=5s"
})
class ProductRepositoryTests {
}
```

Tên property cụ thể phụ thuộc Spring Boot version và client generation. Với cấu hình Elasticsearch thông dụng, `spring.elasticsearch.uris` xác định endpoint; username/password, API key, TLS bundle và timeout có thể được cấu hình bằng các property tương ứng của phiên bản.

Không đặt credential production trong source code hoặc annotation test được commit vào repository. Dùng environment variable, secret manager hoặc cấu hình test riêng.

### 7.1 @TestPropertySource

Có thể dùng `@TestPropertySource` để đọc file properties hoặc khai báo inline:

```java
@DataElasticsearchTest
@TestPropertySource(properties = {
    "spring.elasticsearch.uris=http://localhost:9200"
})
class ProductRepositoryTests {
}
```

Chọn một cơ chế cấu hình thống nhất để tránh trùng lặp và khó hiểu thứ tự ưu tiên. Nếu nhiều nguồn cùng khai báo một key, hãy kiểm tra property source precedence của Spring Test/Boot thay vì đoán giá trị cuối cùng.

### 7.2 @DynamicPropertySource

Khi endpoint chỉ biết lúc test runtime, ví dụ container nhận port động, dùng `@DynamicPropertySource`:

```java
@DataElasticsearchTest
class ProductRepositoryTests {

    @DynamicPropertySource
    static void elasticsearchProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.elasticsearch.uris",
            () -> "http://localhost:9200"
        );
    }
}
```

Ví dụ dùng URI cố định để minh họa hook. Với Testcontainers, supplier có thể lấy host/port từ container đang chạy. Dynamic property được đăng ký trước khi context cần property đó được tạo.

### 7.3 Property không tự tạo server

Khai báo `spring.elasticsearch.uris` chỉ cho client biết kết nối tới đâu. Nó không tải Docker image, khởi động Elasticsearch, tạo index hoặc bảo đảm endpoint sẵn sàng. Lifecycle của test server phải được quản lý riêng bằng Testcontainers, test fixture hoặc môi trường integration test.
## 8. includeFilters và excludeFilters

Khi test cần thêm hoặc loại một component cụ thể trong quá trình scan, `@DataElasticsearchTest` cung cấp `includeFilters` và `excludeFilters`. Hai thuộc tính này nhận các filter kiểu component scan của Spring.

Các loại filter thường gặp:

- `FilterType.ASSIGNABLE_TYPE`: chọn một class hoặc subtype cụ thể.
- `FilterType.ANNOTATION`: chọn component có annotation chỉ định.
- `FilterType.REGEX`: chọn theo tên class khớp regular expression.
- `FilterType.ASPECTJ`: chọn theo AspectJ type pattern.
- `FilterType.CUSTOM`: dùng filter implementation tùy biến.

### 8.1 Include một component cụ thể

Ví dụ cần mapper trong test slice:

```java
@DataElasticsearchTest(
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = ProductProjectionMapper.class
    )
)
class ProductRepositoryTests {

    @Autowired
    ProductProjectionMapper mapper;
}
```

Include filter cho phép component vốn bị slice loại trừ được đưa vào scan. Cách này hữu ích khi class được quản lý như component và muốn giữ cơ chế scan thay vì import từng bean thủ công.

### 8.2 Exclude một component

Nếu một component mặc định được đưa vào context nhưng không phù hợp với test, có thể loại nó:

```java
@DataElasticsearchTest(
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = LegacySearchConfiguration.class
    )
)
class ProductRepositoryTests {
}
```

Chỉ dùng exclude filter khi xác định rõ component đó được đưa vào từ đâu. Nếu một service đã bị slice loại mặc định, thêm exclude filter cho nó không giải quyết vấn đề nào và khiến cấu hình khó đọc hơn.

### 8.3 Khi nào dùng include filter hay @Import?

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Thêm một bean cụ thể, không cần scan | `@Import` |
| Thêm một nhóm class theo stereotype/type scan | `includeFilters` |
| Thêm nhiều bean test chỉ dùng trong test | `@TestConfiguration` |
| Bật một configuration properties class | `@EnableConfigurationProperties` |
| Bật auto-configuration khác | `@ImportAutoConfiguration` |

Ưu tiên cơ chế thể hiện rõ ý định và thêm ít thành phần nhất. Include filter có thể kéo theo dependency khác nếu component được import có constructor phụ thuộc vào nhiều bean.

### 8.4 useDefaultFilters

Annotation có thuộc tính `useDefaultFilters` để điều khiển việc áp dụng default filter khi kết hợp với primary `@SpringBootApplication`. Giá trị mặc định và tương tác với include/exclude filters được mô tả trong Javadoc của đúng phiên bản.

Đây là tùy chọn nâng cao. Không nên đặt `useDefaultFilters = false` chỉ để “làm test chạy được”, vì thay đổi này có thể khiến các thành phần mặc định của slice không còn được phát hiện như mong đợi. Nếu cần tùy biến scan sâu, hãy xem Javadoc và kiểm tra tập bean thực tế trong context.

## 9. excludeAutoConfiguration

`excludeAutoConfiguration` cho phép loại một hoặc nhiều auto-configuration khỏi slice:

```java
@DataElasticsearchTest(
    excludeAutoConfiguration = {
        SomeOptionalAutoConfiguration.class
    }
)
class ProductRepositoryTests {
}
```

`SomeOptionalAutoConfiguration` là placeholder minh họa; thay bằng class auto-configuration thật trong dependency đang dùng. Thuộc tính này là alias cho danh sách exclude của `@ImportAutoConfiguration`.

Chỉ exclude auto-configuration khi biết rõ bean nào đang được cấu hình và vì sao không muốn nó xuất hiện. Nếu exclude nhầm cấu hình Elasticsearch cốt lõi, template/client/repository có thể không được tạo và test sẽ lỗi khi inject hoặc thực thi query.

### 9.1 Import thêm auto-configuration

Nếu test cần một auto-configuration khác, có thể thêm qua `@ImportAutoConfiguration`:

```java
@DataElasticsearchTest
@ImportAutoConfiguration(ExtraTestAutoConfiguration.class)
class ProductRepositoryTests {
}
```

`@ImportAutoConfiguration` dành cho class auto-configuration được thiết kế để được import theo cơ chế Spring Boot. Với một `@Configuration` thông thường hoặc component cụ thể, dùng `@Import`.

Không nhầm hai annotation:

- `@Import` đăng ký configuration/component được chỉ định.
- `@ImportAutoConfiguration` nhập auto-configuration và tuân theo cơ chế import/exclusion của Spring Boot.

## 10. Khi nào dùng @AutoConfigureDataElasticsearch với @SpringBootTest?

Nếu muốn chạy full application context nhưng vẫn cần auto-configuration test/data Elasticsearch, có thể dùng `@AutoConfigureDataElasticsearch` cùng `@SpringBootTest`:

```java
@SpringBootTest
@AutoConfigureDataElasticsearch
class ProductApplicationIntegrationTests {

    @Autowired
    ProductService productService;

    @Autowired
    ProductRepository products;
}
```

Tên package của `@AutoConfigureDataElasticsearch` phụ thuộc Spring Boot version. Cách kết hợp này phù hợp khi test cần service, event listener, security configuration hoặc các bean ứng dụng khác cùng repository.

Không nên gắn nhiều test slice annotations vào cùng một test class với hy vọng Spring sẽ hợp nhất các slice. Spring Boot không hỗ trợ tùy ý kết hợp nhiều `@...Test` slices. Chọn một slice chính và thêm các `@AutoConfigure...` annotations phù hợp, hoặc dùng `@SpringBootTest` khi mục tiêu là full context.

### 10.1 Chọn loại test theo câu hỏi cần trả lời

| Câu hỏi | Cách test |
|---|---|
| Query method có trả đúng document không? | `@DataElasticsearchTest` |
| Mapping/converter serialize field đúng không? | `@DataElasticsearchTest` |
| Custom repository/Operations có gọi đúng query không? | `@DataElasticsearchTest` |
| Service phối hợp repository và client ngoài ra sao? | Unit test service hoặc `@SpringBootTest` tùy phạm vi |
| Controller, security và repository tích hợp ra sao? | `@SpringBootTest` với web test client phù hợp |
| Chỉ kiểm tra thuật toán Java, không cần Spring/Elasticsearch | Unit test thuần |

## 11. Kết nối tới Elasticsearch trong test

`@DataElasticsearchTest` cấu hình Spring beans, nhưng Elasticsearch server phải được cung cấp riêng. Có thể dùng:

1. Elasticsearch local dành riêng cho integration test.
2. Elasticsearch trong Docker/Testcontainers.
3. Một test service dùng chung cho CI.

Tránh chạy test với cluster production hoặc index production. Test có thể tạo, xóa và cập nhật document; nên dùng cluster/index dành riêng cho test.

### 11.1 Cấu hình endpoint tĩnh

Ví dụ dùng test profile:

```properties
spring.elasticsearch.uris=http://localhost:9200
```

Hoặc cấu hình trực tiếp trên test:

```java
@DataElasticsearchTest(properties = {
    "spring.elasticsearch.uris=http://localhost:9200"
})
class ProductRepositoryTests {
}
```

Đảm bảo server thực sự chạy trước khi test context hoặc repository gửi request. Nếu cluster yêu cầu authentication/TLS, cung cấp các thuộc tính tương ứng theo Spring Boot version.

### 11.2 Dynamic endpoint với Testcontainers

Testcontainers có thể khởi chạy Elasticsearch cho integration test. Ví dụ dưới đây minh họa cấu trúc; version image, module Testcontainers và cấu hình security phải tương thích với Elasticsearch/client của dự án:

```java
@DataElasticsearchTest
class ProductRepositoryTests {

    @Container
    static final ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer(
            DockerImageName.parse(
                "docker.elastic.co/elasticsearch/elasticsearch:8.17.0"
            )
        );

    @DynamicPropertySource
    static void elasticsearchProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.elasticsearch.uris",
            elasticsearch::getHttpHostAddress
        );
    }
}
```

Một số image Elasticsearch yêu cầu password hoặc TLS. Khi đó container cần được cấu hình tương ứng và test phải đăng ký username/password hoặc SSL settings vào Environment. Không copy version image ví dụ mà không kiểm tra compatibility matrix.

Nếu dùng JUnit 5/Testcontainers extension, bảo đảm lifecycle container bắt đầu trước khi Spring tạo client/context cần endpoint. Với context caching, container nên có lifecycle tương thích với thời gian context được cache; nếu container dừng quá sớm, test sau có thể dùng context cũ trỏ tới endpoint không còn tồn tại.

### 11.3 Không nhầm server container với test slice

Testcontainers giải quyết lifecycle của Elasticsearch process. `@DataElasticsearchTest` giải quyết Spring test context. Hai cơ chế bổ sung cho nhau:

```text
Testcontainers
    -> starts Elasticsearch and exposes host/port

DynamicPropertySource
    -> publishes URI to Spring Environment

@DataElasticsearchTest
    -> configures client/template/repositories in test context

Repository test
    -> sends real requests to the container
```

Nếu container chạy nhưng URI không được đăng ký đúng, client vẫn kết nối sai. Nếu URI đúng nhưng container chưa sẵn sàng, request có thể thất bại do startup race.
## 12. Quản lý index và dữ liệu giữa các test

Elasticsearch không có transaction rollback tự động cho mỗi test như một số relational test slice. Khi repository ghi document, dữ liệu đã được ghi vào Elasticsearch và vẫn tồn tại sau khi method test kết thúc, trừ khi test chủ động xóa hoặc dùng index riêng.

### 12.1 Tạo index/mapping cho test

Có thể dùng `IndexOperations` để tạo index và mapping trước khi chạy test:

```java
@BeforeEach
void ensureIndex() {
    IndexOperations indexOperations =
        operations.indexOps(ProductDocument.class);

    if (!indexOperations.exists()) {
        indexOperations.createWithMapping();
    }
}
```

Tên method và cách tạo mapping phụ thuộc phiên bản Spring Data Elasticsearch. Nếu entity dùng index name cố định, bảo đảm các test không vô tình dùng chung index với môi trường khác.

### 12.2 Dọn dữ liệu sau test

Ví dụ xóa các document trong repository:

```java
@AfterEach
void cleanUp() {
    products.deleteAll();
}
```

Nếu test tạo nhiều loại document hoặc cần kiểm tra delete/index behavior, hãy dọn theo index riêng hoặc dùng một index tên riêng cho test class. Không xóa toàn bộ alias/index dùng chung nếu test khác có thể đang chạy đồng thời.

### 12.3 Dùng index riêng cho từng test suite

Một cách cô lập dữ liệu là dùng index có suffix test:

```java
@Document(indexName = "products-repository-test")
class ProductDocument {
}
```

Trong pipeline chạy song song, tên index cố định vẫn có thể bị chia sẻ giữa các worker. Có thể tạo index động theo test run hoặc class, sau đó cấu hình `IndexCoordinates` cho repository/Operations phù hợp. Việc thay index name động cần được thiết kế nhất quán với mapping metadata và repository; không chỉ thay property tùy tiện nếu annotation `@Document` vẫn trỏ sang index khác.

### 12.4 Context cache không đồng nghĩa dữ liệu được reset

Spring TestContext có thể cache `ApplicationContext` giữa các test có cấu hình tương đương. Context cache giúp giảm thời gian khởi tạo, nhưng không tự xóa document/index sau mỗi test. Quản lý dữ liệu phải là trách nhiệm rõ ràng của test fixture hoặc lifecycle hook.

`@DirtiesContext` đóng/loại context khỏi cache theo phạm vi cấu hình, nhưng không phải cơ chế dọn dữ liệu Elasticsearch đáng tin cậy. Dữ liệu có thể vẫn tồn tại trên server sau khi context bị đóng.

## 13. Transaction và cleanup

Không giả định `@DataElasticsearchTest` tự bọc mỗi test trong transaction và rollback Elasticsearch khi test kết thúc. Elasticsearch không cung cấp transaction ACID đa document tương đương JPA; thao tác write đã thành công không tự hoàn tác chỉ vì test method kết thúc hoặc assertion thất bại.

Vì vậy:

- Tạo dữ liệu fixture có ID dễ nhận biết.
- Dùng index riêng nếu test chạy song song.
- Xóa dữ liệu trong `@AfterEach` hoặc xóa index trong lifecycle phù hợp.
- Không dùng chung dữ liệu mutable giữa test nếu thứ tự chạy có thể thay đổi.
- Kiểm tra cả cleanup khi test fail, không chỉ happy path.

Ví dụ:

```java
@DataElasticsearchTest
class ProductRepositoryTests {

    @Autowired
    ProductRepository products;

    @BeforeEach
    void setUp() {
        products.deleteAll();
    }

    @Test
    void findsProductBySku() {
        products.save(new ProductDocument("p-1", "KB-1001", "Keyboard"));

        assertThat(products.findBySku("KB-1001")).isPresent();
    }
}
```

Đây là ví dụ đơn giản; nếu nhiều test class dùng chung index hoặc chạy song song, xóa toàn bộ repository trong `@BeforeEach` có thể phá dữ liệu của test khác. Khi đó hãy dùng index tách biệt hoặc ID namespace riêng.

## 14. JUnit 5 và JUnit 4

Trong JUnit Jupiter (JUnit 5), `@DataElasticsearchTest` đã tích hợp `SpringExtension`, nên không cần thêm `@ExtendWith(SpringExtension.class)`:

```java
@DataElasticsearchTest
class ProductRepositoryTests {

    @Test
    void testRepository() {
    }
}
```

Với JUnit 4, dùng Spring Runner:

```java
@RunWith(SpringRunner.class)
@DataElasticsearchTest
public class ProductRepositoryTests {

    @Test
    public void testRepository() {
    }
}
```

Nếu quên runner trong JUnit 4, Spring test annotations có thể không được xử lý như mong đợi. Với dự án mới, JUnit 5 thường là lựa chọn mặc định trong Spring Boot hiện đại.

## 15. Khác biệt package giữa Spring Boot 3 và 4

`@DataElasticsearchTest` có từ Spring Boot 2.7. Package import thay đổi giữa major version:

| Spring Boot | Package annotation |
|---|---|
| Spring Boot 2.7 và 3.x | `org.springframework.boot.test.autoconfigure.data.elasticsearch.DataElasticsearchTest` |
| Spring Boot 4.x | `org.springframework.boot.data.elasticsearch.test.autoconfigure.DataElasticsearchTest` |

Ví dụ import trong Boot 3.x:

```java
import org.springframework.boot.test.autoconfigure.data.elasticsearch.DataElasticsearchTest;
```

Ví dụ import trong Boot 4.x:

```java
import org.springframework.boot.data.elasticsearch.test.autoconfigure.DataElasticsearchTest;
```

Boot 4 cũng tổ chức lại một số package test auto-configuration. Khi nâng major version, dùng IDE auto-import hoặc Javadoc đúng version để cập nhật package. Không giải quyết lỗi import bằng cách thêm đồng thời nhiều version Spring Boot test artifacts.

## 16. Các thuộc tính của @DataElasticsearchTest

Các thuộc tính thường gặp của annotation gồm:

| Thuộc tính | Mục đích |
|---|---|
| `properties` | Thêm property dạng `key=value` vào Environment trước khi test chạy |
| `includeFilters` | Bổ sung component vốn bị filter khỏi slice |
| `excludeFilters` | Loại component phù hợp filter khỏi scan |
| `useDefaultFilters` | Điều khiển việc sử dụng default filters khi kết hợp primary configuration |
| `excludeAutoConfiguration` | Loại auto-configuration khỏi danh sách được import |

Ví dụ kết hợp một số thuộc tính:

```java
@DataElasticsearchTest(
    properties = "spring.elasticsearch.uris=http://localhost:9200",
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = ProductProjectionMapper.class
    ),
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = LegacySearchConfiguration.class
    )
)
class ProductRepositoryTests {
}
```

Không nên thêm mọi thuộc tính ngay từ đầu. Bắt đầu với slice mặc định; chỉ mở rộng khi có một dependency cụ thể cần thiết và đã xác định được lý do.

## 17. Chẩn đoán khi bean không xuất hiện

Khi test báo `NoSuchBeanDefinitionException`, hãy phân loại bean bị thiếu trước khi thay annotation:

| Bean bị thiếu | Kiểm tra/hướng xử lý |
|---|---|
| Repository | Kiểm tra package scan, repository enablement và repository type |
| Entity/mapping | Kiểm tra `@Document`, package và mapping metadata |
| `ElasticsearchOperations` | Kiểm tra dependency, auto-configuration và client setup |
| `@ConfigurationProperties` | Đăng ký bằng `@EnableConfigurationProperties` |
| Mapper/helper component | Dùng `@Import`, `@TestConfiguration` hoặc include filter |
| Service/controller | Xác định có thật sự cần full context không; import chọn lọc hoặc dùng `@SpringBootTest` |
| Custom auto-configuration | Dùng `@ImportAutoConfiguration` nếu class đó là auto-configuration phù hợp |

### 17.1 Phân biệt lỗi context và lỗi kết nối

Hai lỗi thường bị nhầm:

- **Bean không tồn tại:** Spring không tạo được repository/template/client bean do scan hoặc auto-configuration.
- **Không kết nối được Elasticsearch:** bean đã tồn tại nhưng endpoint, credential, TLS, network hoặc server lifecycle có vấn đề.

Nếu `@Autowired ProductRepository` thành công nhưng truy vấn ném lỗi connection refused, repository scan không phải vấn đề. Kiểm tra URI và trạng thái Elasticsearch.

### 17.2 Bật debug condition evaluation

Khi cần hiểu auto-configuration nào được bật/tắt, có thể bật debug cho test hoặc xem condition evaluation report từ Spring Boot. Mục tiêu là xác định điều kiện nào không thỏa, class nào bị exclude và bean nào được tạo.

Không nên sửa hàng loạt property hoặc thêm `@Import` ngẫu nhiên trước khi xem nguyên nhân. Một thay đổi nhỏ có thể vô tình bật cả nhóm cấu hình ngoài slice.

## 18. Những lỗi sử dụng thường gặp

### 18.1 Mong service tự động được inject

`@DataElasticsearchTest` chỉ tập trung vào Elasticsearch data slice. Service thông thường không tự scan. Import service nếu test thật sự cần nó, hoặc dùng full application test cho use case nhiều tầng.

### 18.2 Nghĩ annotation tự khởi chạy Elasticsearch

Annotation cấu hình Spring context; nó không tự chạy server. Cần local service, Testcontainers hoặc môi trường test riêng.

### 18.3 Nghĩ mỗi test được rollback dữ liệu

Elasticsearch write không tự rollback theo transaction test. Chủ động dọn document/index hoặc cô lập dữ liệu.

### 18.4 Dùng @SpringBootTest chỉ để thêm một bean

Nếu chỉ thiếu mapper hoặc properties class, dùng `@Import`, `@TestConfiguration` hoặc `@EnableConfigurationProperties`. Full context làm test rộng hơn cần thiết.

### 18.5 Bật component scan rộng

`@ComponentScan` tùy chỉnh trên application class có thể làm slice filter không hoạt động như dự kiến. Tách scan cấu hình đặc biệt hoặc điều khiển import có chọn lọc.

### 18.6 Trộn nhiều test slice annotations

Không kết hợp tùy tiện nhiều `@...Test` slices. Chọn slice chính và bổ sung `@AutoConfigure...` phù hợp, hoặc dùng `@SpringBootTest`.

### 18.7 Dùng import package sai version

Boot 3.x và Boot 4.x có package test annotation khác nhau. Kiểm tra import theo version dependency đang dùng.

### 18.8 Chia sẻ index giữa test chạy song song

Test có thể xóa hoặc ghi đè document của nhau. Dùng index riêng, ID namespace hoặc chạy tuần tự khi test không thể cô lập.

## 19. Quy trình chọn phạm vi test

Có thể đi theo các bước sau:

1. Xác định test đang kiểm tra repository, mapping hay use case nhiều tầng.
2. Nếu chỉ kiểm tra Elasticsearch data layer, bắt đầu với `@DataElasticsearchTest`.
3. Cấu hình một Elasticsearch endpoint dành riêng cho test.
4. Kiểm tra entity `@Document` và repository được phát hiện.
5. Nếu thiếu một bean phụ, phân loại nó là properties, component, test bean hay auto-configuration.
6. Thêm đúng cơ chế: `@EnableConfigurationProperties`, `@Import`, `@TestConfiguration`, include filter hoặc `@ImportAutoConfiguration`.
7. Nếu cần nhiều service/controller/integration component, cân nhắc `@SpringBootTest` và `@AutoConfigureDataElasticsearch`.
8. Tạo/dọn index và document để test độc lập.
9. Kiểm tra lifecycle Elasticsearch container tương thích với context cache.
10. Giữ test slice nhỏ để lỗi mapping/query được phát hiện nhanh và dễ chẩn đoán.

```mermaid
flowchart TD
    A[Choose test scope] --> B{Only Elasticsearch data layer?}
    B -->|Yes| C[Use @DataElasticsearchTest]
    B -->|No| D{Need full application context?}
    D -->|Yes| E[Use @SpringBootTest + @AutoConfigureDataElasticsearch]
    D -->|No| F[Use a plain unit test or a smaller focused test]
    C --> G{A required bean is missing?}
    G -->|Properties| H[@EnableConfigurationProperties]
    G -->|Specific component| I[@Import or includeFilters]
    G -->|Test-only beans| J[@TestConfiguration]
    G -->|Extra auto-configuration| K[@ImportAutoConfiguration]
    G -->|No| L[Run repository test against test Elasticsearch]
    H --> L
    I --> L
    J --> L
    K --> L
```

## 20. Nguyên tắc triển khai

- Dùng `@DataElasticsearchTest` cho repository, mapping, converter và template test.
- Hiểu đây là test slice có giới hạn auto-configuration và component scan.
- Không kỳ vọng service/controller hoặc mọi `@Component` tự xuất hiện trong context.
- Đăng ký `@ConfigurationProperties` cần thiết bằng `@EnableConfigurationProperties`.
- Dùng `@Import` hoặc `@TestConfiguration` cho bean chỉ test cần.
- Dùng include/exclude filters khi thực sự cần điều khiển component scan.
- Dùng `@ImportAutoConfiguration` cho auto-configuration bổ sung và `excludeAutoConfiguration` để loại cấu hình cụ thể.
- Kiểm tra `@ComponentScan` tùy chỉnh trên primary application configuration nếu slice scan quá rộng.
- Cung cấp Elasticsearch server riêng; annotation không tự khởi chạy embedded server.
- Dùng property tĩnh hoặc `@DynamicPropertySource` để cấu hình endpoint.
- Chủ động tạo/dọn dữ liệu; không giả định test được rollback như JPA.
- Chọn `@SpringBootTest` kết hợp `@AutoConfigureDataElasticsearch` khi cần full application context.
- Kiểm tra package import theo Spring Boot major version.

## 21. Tổng kết

`@DataElasticsearchTest` là test slice tập trung vào Spring Data Elasticsearch. Nó tự cấu hình các thành phần data cần thiết, phát hiện repository và entity `@Document`, đồng thời giới hạn auto-configuration/component scanning để không tải toàn bộ ứng dụng. Các service, controller, component và `@ConfigurationProperties` thông thường không tự động được đưa vào context; hãy bổ sung có chọn lọc bằng `@Import`, `@TestConfiguration`, `@EnableConfigurationProperties`, include filters hoặc `@ImportAutoConfiguration`.

Annotation không tự khởi chạy Elasticsearch server và cũng không tạo transaction rollback dữ liệu sau mỗi test. Cần cung cấp endpoint test, quản lý lifecycle server/container, cấu hình property, tạo/dọn index và cô lập dữ liệu giữa các test. Khi cần kiểm tra toàn bộ service/controller cùng repository, dùng `@SpringBootTest` kết hợp `@AutoConfigureDataElasticsearch` hoặc lựa chọn integration test phù hợp.

Hiểu đúng phạm vi tự cấu hình giúp test chỉ tải những thành phần cần thiết, chạy nhanh hơn và làm rõ lỗi nằm ở repository scan, auto-configuration, bean phụ hay kết nối Elasticsearch. Hãy bắt đầu với slice mặc định rồi mở rộng đúng phần context mà test thực sự cần.

## Tài liệu tham khảo

- [Spring Boot Reference — Auto-configured Data Elasticsearch Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.3 API — DataElasticsearchTest](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/data/elasticsearch/DataElasticsearchTest.html)
- [Spring Boot 4 API — DataElasticsearchTest](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/data/elasticsearch/test/autoconfigure/DataElasticsearchTest.html)
- [Spring Boot Reference — Test Slices and Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Data Elasticsearch Reference](https://docs.spring.io/spring-data/elasticsearch/reference/index.html)
- [Testcontainers — Elasticsearch Module](https://java.testcontainers.org/modules/elasticsearch/)
