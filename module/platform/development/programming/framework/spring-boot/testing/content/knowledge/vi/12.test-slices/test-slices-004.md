# Test slice: Bổ sung dependency cần thiết bằng import hoặc bean thay thế

## 1. Vì sao một test slice lại thiếu bean?

Một bài kiểm thử `@SpringBootTest` có thể khởi động thành công, nhưng khi thay bằng `@WebMvcTest(ProductController.class)` bạn thấy lỗi:

~~~text
UnsatisfiedDependencyException: Error creating bean 'productController'
No qualifying bean of type 'example.slices.ProductCatalog' available
~~~

Đây thường là **hệ quả có chủ đích** của test slice, không phải bằng chứng application production bị lỗi. Spring Boot chỉ đưa vào `ApplicationContext` một phần ứng dụng cần cho lớp đang kiểm. `@WebMvcTest` cấu hình các thành phần Spring MVC và những web components được phép, nhưng không quét mọi `@Service`, `@Repository` hoặc `@Component` thông thường.

Giả sử controller nhận ba dependency:

~~~text
ProductController            ← SUT: giữ chạy thật
  ├─ ProductCatalog          ← @Service: ngoài web slice
  ├─ PriceFormatter          ← @Component thường: ngoài web slice
  └─ Clock                   ← @Bean trong @Configuration: ngoài web slice
~~~

Để có một test MVC gọn, ta sẽ **giữ controller thật**, rồi chọn có chủ đích:

- Import `PriceFormatter` thật vì test cần xác nhận format giá.
- Đưa `Clock.fixed(...)` bằng `@TestConfiguration + @Bean`, tránh phụ thuộc ngày hiện tại.
- Thay `ProductCatalog` bằng `@MockitoBean` để stub/verify lời gọi, hoặc bằng fake `@Bean` để chạy quy tắc đơn giản.

Bài học này giải thích cách lựa chọn, các annotation tương ứng, lỗi phổ biến và ví dụ **Java 17+/Spring Boot 3.5.x/JUnit Jupiter** có thể chạy trong một dự án Gradle đã cấu hình Spring Boot.

## 2. Nguyên tắc thiết kế: chỉ thêm phần thực sự cần

**Test slice** là Spring Boot test context được tạo bằng annotation chuyên biệt như `@WebMvcTest`, `@WebFluxTest`, `@DataJpaTest`, `@JdbcTest` hoặc `@JsonTest`. Khác với full-context `@SpringBootTest`, mỗi slice lọc bean và chỉ nạp một số auto-configuration phù hợp.

| Test slice | Phạm vi chủ yếu | Dependency thường bị loại |
| --- | --- | --- |
| `@WebMvcTest` | MVC controllers, advice, filters/converters được phép, `MockMvc` | Business `@Service`, repository, nhiều `@Component` thông thường |
| `@WebFluxTest` | Reactive controller, web codecs, `WebTestClient` | Service/repository không thuộc reactive web slice |
| `@JsonTest` | JSON serialization/deserialization | MVC controller, business service, DB |
| `@DataJpaTest` | JPA mapping, entity manager, repository và transaction support | MVC controller, phần lớn service |
| `@JdbcTest` | JDBC, datasource và transaction support của slice | HTTP/MVC, business service |
| `@DataMongoTest` | MongoDB components và repositories | MVC/business graph đầy đủ |

Lượng bean cụ thể phụ thuộc **classpath, Spring Boot version, profile, conditions và customizations**. Không suy luận rằng mọi repository hay converter đều hiện diện chỉ vì cùng một module Java.

Câu hỏi đầu tiên khi thiếu dependency không phải “import class nào để hết exception?”, mà là:

> **Hành vi của dependency này có phải thứ bài test cần chứng minh hay chỉ là đầu vào/hệ thống ngoài?**

| Điều muốn kiểm | Lựa chọn hợp lý |
| --- | --- |
| Logic thật của mapper/formatter tham gia kết quả HTTP | `@Import(RealFormatter.class)` |
| Giá trị thời gian hoặc cờ cấu hình cố định | `@TestConfiguration + @Bean` |
| Controller gọi service đúng tham số/trả status/JSON | `@MockitoBean` cho service |
| Chuỗi hành vi cần state đơn giản, không cần DB thật | Fake implementation cấp qua `@Bean` |
| `@ConfigurationProperties` phải bind đúng | `@EnableConfigurationProperties(Settings.class)` |
| Thêm auto-configuration của Spring Boot | `@ImportAutoConfiguration` |
| Transaction, query SQL, entity mapping, schema thật | JPA/JDBC slice với database thật |
| Tương tác controller + service + repository + advice toàn ứng dụng | `@SpringBootTest`, tài nguyên test phù hợp |

Mock chính controller rồi kiểm đúng giá trị do mock trả về **không phải controller test**. Hãy giữ SUT chạy thật, chỉ thay collaborator tại ranh giới.

## 3. @Import: đưa một implementation thật vào slice

Annotation `org.springframework.context.annotation.Import` cho phép đăng ký tường minh class component hoặc configuration mà slice không tự quét.

~~~java
@WebMvcTest(ProductController.class)
@Import(PriceFormatter.class)
class ProductControllerTest {
    // PriceFormatter thật có mặt trong test context.
}
~~~

Đoạn trên là **mẫu minh họa, chưa đủ dependencies** nếu controller còn cần `Catalog` hoặc `Clock`; xem ví dụ hoàn chỉnh ở mục 8.

Dùng `@Import` khi implementation:

1. Có logic thực sự cần kiểm cùng SUT, ví dụ formatter, mapper, MVC converter.
2. Không cần mạng/DB hoặc có phụ thuộc nhỏ, đã kiểm soát được.
3. Không tạo hàng loạt bean ngoài phạm vi slice.
4. Có tác dụng quan sát được qua assertion, không chỉ để làm context hết lỗi.

Không dùng `@Import(EntireApplication.class)` hoặc `@ComponentScan("...")` rộng chỉ để nạp một formatter. Điều đó có thể làm mất **filters của slice**, gây khởi động scheduler, migrations, datasource hoặc client thật.

Spring Boot lưu ý: explicit `@ComponentScan` trên primary `@SpringBootApplication` có thể khiến default slice exclude filters không được áp dụng như mong đợi. Ưu tiên `@Import` từng dependency cụ thể, giữ root configuration tối giản.

### Import real collaborator hay mock nó?

Giả sử controller cần `PriceFormatter.format(1250)` trả `12.50 USD`. Nếu bạn stub formatter trả chuỗi đó, test chỉ chứng minh controller nhận đúng giá trị được stub; **không phát hiện lỗi format**. Import formatter thật cho phép assertion JSON bắt lỗi production format. Ngược lại, nếu service gọi database ngoài, import nguyên service thật có thể kéo theo graph lớn mà không mang lại bằng chứng về MVC. Khi đó mock service port.

## 4. @TestConfiguration + @Bean: fake hoặc fixture test-only

Spring Boot cung cấp `org.springframework.boot.test.context.TestConfiguration`. Một top-level test configuration trong `src/test/java` thường không bị quét bởi production component scanning và có thể import tường minh khi cần.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
class FixedClockTestConfiguration {
    @Bean
    Clock clock() {
        return Clock.fixed(
                Instant.parse("2026-01-02T00:00:00Z"),
                ZoneOffset.UTC);
    }
}
~~~

Đây là **class minh họa với import**, khi dùng trong package phải đặt nó vào file `FixedClockTestConfiguration.java` ở test sources. Clock chạy logic JDK thật nhưng có giá trị xác định, nên không cần Mockito.

Một fake cũng có thể được cấp qua `@Bean`:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class FakeCatalogTestConfiguration {
    @Bean
    ProductCatalog productCatalog() {
        return sku -> "BOOK".equals(sku)
                ? Optional.of(new Product("BOOK", 1250L))
                : Optional.empty();
    }
}
~~~

Đoạn này cần `ProductCatalog`, `Product` của project và import `java.util.Optional`; bản đầy đủ nằm ở mục 8.

**Phân biệt với nested `@Configuration`:** nested static `@TestConfiguration` có thể được Boot nhận để bổ sung cấu hình test, còn nested `@Configuration` thông thường có thể thay thế primary configuration trong một số đường nạp TestContext. Với nhu cầu dễ đọc, dùng **top-level test configuration + `@Import`** như bài thực hành.

**Tránh bean trùng:** Nếu slice đã có `Clock` từ nơi khác, thêm `@Bean Clock` không phân biệt có thể gây `NoUniqueBeanDefinitionException`. Xem nguồn bean đang có, dùng qualifier hoặc bean override theo mục tiêu. Đừng bật `spring.main.allow-bean-definition-overriding=true` chỉ để che setup thiếu rõ ràng.

## 5. @MockitoBean: mock thực sự được Spring inject vào bean

Spring Framework 6.2 hỗ trợ `org.springframework.test.context.bean.override.mockito.MockitoBean`:

~~~java
@MockitoBean
ProductCatalog catalog;
~~~

`@MockitoBean` đăng ký **mock trong ApplicationContext** do Spring TestContext quản lý. Vì vậy controller được khởi tạo bởi Spring sẽ nhận mock đó.

Ngược lại:

~~~java
@Mock
ProductCatalog catalog;
~~~

`@Mock` thuần Mockito chỉ tạo đối tượng mock cho test field khi Mockito được khởi tạo; nó **không tự động thay bean** trong Spring context. Trong unit test không Spring, `@Mock` và constructor thủ công là lựa chọn tốt. Trong slice cần override dependency của controller, chọn `@MockitoBean`.

### Replace-or-create và enforceOverride

`@MockitoBean` mặc định áp dụng chiến lược **REPLACE_OR_CREATE**:

- Nếu đã có bean phù hợp trong context: thay bean bằng mock.
- Nếu bean không có: tạo mock bean mới cho test.

Điều thứ hai rất quan trọng trong `@WebMvcTest`: `@Service ProductCatalogImpl` production bị filter ra, nên mock thường được **tạo bổ sung**, không có service production để thay.

Nếu cần phát hiện việc “đang thay đúng bean production”, có thể dùng:

~~~java
@MockitoBean(enforceOverride = true)
PaymentGateway gateway;
~~~

Nhưng trong web slice chưa có `PaymentGateway` bean, thuộc tính này có thể làm test khởi động **thất bại** thay vì tạo mock mới. Chỉ bật khi hợp đồng test đòi hỏi bean gốc phải tồn tại.

### Phiên bản Spring

| Stack | Annotation quen dùng |
| --- | --- |
| Spring Boot 3.3 trở về trước | `@MockBean` / `@SpyBean` của Spring Boot |
| Spring Boot 3.4/3.5 + Spring Framework 6.2 | `@MockitoBean` / `@MockitoSpyBean` của Spring TestContext |
| Spring Boot 4.x | `@MockitoBean`, nhưng kiểm package/module test sau migration |

`@MockBean` của Boot bị deprecated từ 3.4; không nhập nhằng các import giữa version. `@MockitoBean` có các quy tắc chọn candidate theo type, bean name và qualifier. Nếu nhiều bean cùng interface, phải xác định **bean nào** cần thay, không dựa vào tên field mơ hồ.

**Rủi ro AOP:** mock thay bean không tự giữ transaction/caching/retry/method-security advice trên bean thật. Nếu mục tiêu là kiểm `@Transactional`, `@Cacheable` hoặc security advice, giữ bean đó thật và mock collaborator thấp hơn.

### @MockitoSpyBean và @TestBean

- `@MockitoSpyBean` bọc bean thật bằng spy, đòi bean target tồn tại phù hợp; method thật chạy theo mặc định. Khi stub spy, `doReturn(...).when(spy)...` thường an toàn hơn `when(spy.method())` vì kiểu thứ hai có thể gọi method thật lúc thiết lập.
- `@TestBean` của Spring Framework tạo bean override từ một **static factory method**, phù hợp khi muốn instance fake mà không dùng Mockito. Factory không nhận tham số, trả về kiểu phù hợp.

~~~java
// Minh họa @TestBean trong class test; không độc lập:
@TestBean(methodName = "catalogForTest")
ProductCatalog catalog;

static ProductCatalog catalogForTest() {
    return sku -> Optional.empty();
}
~~~

`@TestBean` có import `org.springframework.test.context.bean.override.convention.TestBean`. Với nhu cầu bổ sung nhiều fixture khác nhau cho web slice, `@TestConfiguration + @Import` thường thể hiện rõ ràng hơn.

## 6. Ví dụ thực tế sẽ kiểm điều gì?

Ứng dụng mini có endpoint:

~~~text
GET /api/products/BOOK/summary
          |
          v
   ProductController        ← chạy thật trong @WebMvcTest
       |      |       |
       v      v       v
    Catalog Formatter     Clock
     mock     real         fixed
      hoặc
     fake
~~~

Khi catalog cung cấp BOOK giá 1.250 cent, API phải trả JSON chứa:

~~~json
{
  "sku": "BOOK",
  "price": "12.50 USD",
  "asOf": "2026-01-02"
}
~~~

Có hai kiểu test:

- **Test A:** `@MockitoBean ProductCatalog`, `@Import(PriceFormatter.class)` và fixed Clock; kiểm status, JSON, `verify(catalog)`.
- **Test B:** cấp `ProductCatalog` fake qua `@TestConfiguration + @Bean`, vẫn import formatter và Clock; không dùng mock cho catalog.

Cả hai không dùng PostgreSQL, HTTP server TCP hay Docker. Chúng kiểm **MVC mapping, JSON và formatter thật**; chúng **không** kiểm cách catalog production truy vấn database.

## 7. Production code hoàn chỉnh (Java 17+)

Mọi file trong ví dụ thuộc package `example.slices`. Trong project Spring Boot dùng Gradle, đặt những file sau ở `src/main/java/example/slices/`.

### SliceDemoApplication.java

~~~java
package example.slices;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SliceDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SliceDemoApplication.class, args);
    }
}
~~~

Đây là root configuration. `@WebMvcTest` được đặt trong cùng package hierarchy để Spring Boot tìm được `@SpringBootApplication`.

### Product.java

~~~java
package example.slices;

public record Product(String sku, long priceCents) {
}
~~~

### ProductSummary.java

~~~java
package example.slices;

public record ProductSummary(String sku, String price, String asOf) {
}
~~~

Record là dữ liệu thật, không cần Mockito mock. Jackson trong Spring Boot web starter có thể serialize thành JSON.

### ProductCatalog.java

~~~java
package example.slices;

import java.util.Optional;

public interface ProductCatalog {
    Optional<Product> findBySku(String sku);
}
~~~

Đây là boundary cho collaborator; test sẽ cung cấp mock hoặc fake.

### InMemoryProductCatalog.java

~~~java
package example.slices;

import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class InMemoryProductCatalog implements ProductCatalog {
    @Override
    public Optional<Product> findBySku(String sku) {
        if ("BOOK".equals(sku)) {
            return Optional.of(new Product("BOOK", 1_250L));
        }
        return Optional.empty();
    }
}
~~~

Trong ứng dụng production thông thường, `@Service` này được component scan. Nhưng `@WebMvcTest(ProductController.class)` **không scan regular service**, nên test sẽ không tự nhận bean của lớp này.

### PriceFormatter.java

~~~java
package example.slices;

import java.math.BigDecimal;
import org.springframework.stereotype.Component;

@Component
public class PriceFormatter {
    public String format(long cents) {
        return BigDecimal.valueOf(cents, 2).toPlainString()
                + " USD";
    }
}
~~~

Với `1_250L`, `BigDecimal.valueOf(cents, 2)` biểu diễn `12.50` chính xác, không phụ thuộc locale hoặc tính toán floating-point. Ta sẽ import formatter thật bằng `@Import`.

### ApplicationClockConfiguration.java

~~~java
package example.slices;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ApplicationClockConfiguration {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Khi app chạy bình thường, controller sẽ có `Clock` thực. Trong MVC slice, production configuration thông thường này không được tự động đưa vào; test import fixed Clock riêng. Không đặt `@Bean Clock` vào chính root `SliceDemoApplication` để tránh tình huống bean method trên primary configuration vẫn tham gia slice.

### ProductController.java

~~~java
package example.slices;

import java.time.Clock;
import java.time.LocalDate;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {
    private final ProductCatalog catalog;
    private final PriceFormatter formatter;
    private final Clock clock;

    public ProductController(
            ProductCatalog catalog,
            PriceFormatter formatter,
            Clock clock) {
        this.catalog = catalog;
        this.formatter = formatter;
        this.clock = clock;
    }

    @GetMapping("/api/products/{sku}/summary")
    public ResponseEntity<ProductSummary> summary(@PathVariable String sku) {
        return catalog.findBySku(sku)
                .map(product -> ResponseEntity.ok(
                        new ProductSummary(
                                product.sku(),
                                formatter.format(product.priceCents()),
                                LocalDate.now(clock).toString())))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
~~~

Controller giữ toàn bộ phần xử lý request thật: đọc path variable, gọi catalog, chuyển record thành response, chọn 200 hoặc 404. Việc lấy Clock qua constructor làm logic ngày có thể kiểm bằng giá trị cố định mà không đụng `LocalDate.now()` của máy CI.

## 8. Test code đầy đủ: một slice mock, một slice fake

Đặt các file sau trong `src/test/java/example/slices/`, cùng package với ứng dụng.

### FixedClockTestConfiguration.java

~~~java
package example.slices;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
class FixedClockTestConfiguration {
    @Bean
    Clock clock() {
        return Clock.fixed(
                Instant.parse("2026-01-02T00:00:00Z"),
                ZoneOffset.UTC);
    }
}
~~~

Top-level test configuration không bị ứng dụng production tự scan; chỉ test import nó mới nhận Clock cố định.

### FakeCatalogTestConfiguration.java

~~~java
package example.slices;

import java.util.Optional;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
class FakeCatalogTestConfiguration {
    @Bean
    ProductCatalog productCatalog() {
        return sku -> "BOOK".equals(sku)
                ? Optional.of(new Product("BOOK", 1_250L))
                : Optional.empty();
    }
}
~~~

Fake triển khai hợp đồng thực của interface; nó không là Mockito mock và cũng không tự xác minh lời gọi. Không đưa nó vào production source.

### ProductControllerMockitoSliceTest.java

~~~java
package example.slices;

import java.time.Clock;
import java.time.LocalDate;
import java.util.Optional;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
@Import({
        PriceFormatter.class,
        FixedClockTestConfiguration.class
})
@DisplayName("MVC slice: import formatter thật, mock catalog")
class ProductControllerMockitoSliceTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    PriceFormatter formatter;

    @Autowired
    Clock clock;

    @MockitoBean
    ProductCatalog catalog;

    @Test
    @DisplayName("GET summary trả 200 và format giá thật")
    void returnsSummary() throws Exception {
        when(catalog.findBySku("BOOK"))
                .thenReturn(Optional.of(new Product("BOOK", 1_250L)));

        mvc.perform(get("/api/products/BOOK/summary"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku").value("BOOK"))
                .andExpect(jsonPath("$.price").value("12.50 USD"))
                .andExpect(jsonPath("$.asOf").value("2026-01-02"));

        verify(catalog).findBySku("BOOK");
    }

    @Test
    @DisplayName("SKU không tìm thấy trả về 404")
    void returns404() throws Exception {
        when(catalog.findBySku("MISSING"))
                .thenReturn(Optional.empty());

        mvc.perform(get("/api/products/MISSING/summary"))
                .andExpect(status().isNotFound());

        verify(catalog).findBySku("MISSING");
    }

    @Test
    @DisplayName("Formatter và Clock thực sự là bean được import")
    void importedBeansHaveDeterministicBehavior() {
        assertNotNull(formatter);
        assertEquals("12.50 USD", formatter.format(1_250L));
        assertEquals("2026-01-02", LocalDate.now(clock).toString());
    }
}
~~~

Đây là **ba phương thức kiểm thử độc lập**. `@WebMvcTest` auto-configure `MockMvc` nhưng **không mở server TCP**. `@MockitoBean` cấp mock cho Spring context, giúp controller không thiếu `ProductCatalog`. `@Import` đăng ký formatter production và Clock test để mọi collaborator được giải quyết mà không cần database.

**Vì sao không dùng `enforceOverride = true` ở đây?** Catalog service thật bị slice lọc ra, nên mock cần được *create*. Dùng enforce override sẽ đòi bean đã tồn tại, trái với mục tiêu test.

### ProductControllerFakeSliceTest.java

~~~java
package example.slices;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
@Import({
        PriceFormatter.class,
        FixedClockTestConfiguration.class,
        FakeCatalogTestConfiguration.class
})
@DisplayName("MVC slice: fake catalog được cấp qua @Bean")
class ProductControllerFakeSliceTest {

    @Autowired
    MockMvc mvc;

    @Test
    @DisplayName("Fake catalog cấp BOOK cho response")
    void returnsBook() throws Exception {
        mvc.perform(get("/api/products/BOOK/summary"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku").value("BOOK"))
                .andExpect(jsonPath("$.price").value("12.50 USD"))
                .andExpect(jsonPath("$.asOf").value("2026-01-02"));
    }

    @Test
    @DisplayName("Fake không có SKU thì trả 404")
    void missingSkuReturns404() throws Exception {
        mvc.perform(get("/api/products/MISSING/summary"))
                .andExpect(status().isNotFound());
    }
}
~~~

Đây là **hai phương thức kiểm thử** không dùng Mockito. Catalog là bean thật trả từ `@Bean` test-only. Cùng controller và formatter được kiểm như test A, nhưng bằng chứng **không gồm verify số lần gọi catalog**. Khi cần kiểm interaction, mock dễ hơn; khi cần fake có state/logic nhỏ, bean fake thường rõ hơn.

### Hai class test tạo context khác nhau

Test A dùng `@MockitoBean ProductCatalog`; test B dùng `@Import(FakeCatalogTestConfiguration.class)`. Spring TestContext cache context theo cấu hình, imports, customizers, test bean overrides, profiles và properties. Hai class này không buộc phải dùng cùng cache entry. Không nên tạo vô số cấu hình khác nhau chỉ vì mỗi test thích một cách viết tên field.

### Lệnh chạy bằng Gradle

Trong project Spring Boot 3.5.x đã có plugin/dependency management và Java 17 toolchain, phần dependencies trong `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là **đoạn cấu hình**, không phải file `build.gradle` hoàn chỉnh. Trong một dự án Java thuần không có Spring Boot plugin, cần khai báo/version đầy đủ theo Gradle build riêng.

Chạy cả hai lớp:

~~~bash
./gradlew test --tests example.slices.ProductControllerMockitoSliceTest --tests example.slices.ProductControllerFakeSliceTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.slices.ProductControllerMockitoSliceTest --tests example.slices.ProductControllerFakeSliceTest
~~~

**Kỳ vọng:** tổng cộng **5 phương thức JUnit Jupiter PASS** (3 mock-slice, 2 fake-slice) nếu dự án phù hợp. Không có stdout do các test tự in; Gradle/IDE có thể hiển thị test report và `BUILD SUCCESSFUL`. Không cần PostgreSQL, Docker, network ngoài hay HTTP server thật.

**Giới hạn bằng chứng:** test chỉ kiểm Controller + MVC + Formatter + dependency giả. Nó không chứng minh `InMemoryProductCatalog` production đang được scan đúng khi chạy full application, cũng không kiểm database hay security production.

## 9. @EnableConfigurationProperties: khi thiếu bean cấu hình

`@WebMvcTest` không mặc nhiên scan các `@ConfigurationProperties` như regular component. Nếu controller phụ thuộc vào object đã bind từ properties, có thể dùng:

~~~java
@WebMvcTest(CheckoutController.class)
@EnableConfigurationProperties(CheckoutSettings.class)
class CheckoutControllerTest {
    // Spring Boot bind CheckoutSettings từ Environment.
}
~~~

Đây là **mẫu minh họa** với application types `CheckoutController` và `CheckoutSettings` chưa khai báo, không phải test độc lập. `@EnableConfigurationProperties` thích hợp khi muốn kiểm **binding thực** của config type vào controller. Khi chỉ cần object test cố định và không muốn kiểm binder, có thể cung cấp nó qua `@TestConfiguration + @Bean`.

Đừng đưa tất cả configuration properties của production vào web slice. Thêm đúng class cần dùng; tránh property binding vô tình kích hoạt hạ tầng.

## 10. @ImportAutoConfiguration: khác @Import thế nào?

Spring Boot áp dụng auto-configuration thông qua import và điều kiện riêng. Khi cần thêm một auto-configuration cho slice, dùng `@ImportAutoConfiguration` chứ không tùy tiện `@Import(SomeAutoConfiguration.class)`.

Ví dụ minh họa:

~~~java
@JdbcTest
@ImportAutoConfiguration(IntegrationAutoConfiguration.class)
class IntegrationJdbcTest {
    // Các bean vẫn phụ thuộc điều kiện auto-configuration.
}
~~~

Đây là **mẫu annotation**, cần dependency/import phù hợp và các class thuộc Boot, không phải test tự chạy. Lý do: auto-configuration có `@ConditionalOnClass`, `@ConditionalOnMissingBean`, property checks và thứ tự import đặc thù của Boot.

| Muốn bổ sung | Công cụ |
| --- | --- |
| Component business/formatter thật | `@Import(RealClass.class)` |
| Một số `@Bean` cho fixture | `@TestConfiguration` rồi `@Import` |
| Mock trong Spring context | `@MockitoBean` |
| Fake override bằng static factory | `@TestBean` |
| Properties bean | `@EnableConfigurationProperties` |
| Auto-configuration theo cơ chế Boot | `@ImportAutoConfiguration` |

Spring Boot **không hỗ trợ kết hợp nhiều annotation kiểu `@...Test` trên một class chỉ để cộng dồn các slices**. Nếu test cần nhiều tầng, chọn một slice và thêm chính xác `@AutoConfigure...` tương ứng, hoặc dùng `@SpringBootTest` khi mục tiêu vượt phạm vi.

## 11. @DataJpaTest và @JdbcTest: cùng nguyên tắc, khác bằng chứng

Trong `@DataJpaTest`, phần được giữ lại là JPA entities, repositories, transaction/data auto-configuration. Service business không nhất thiết hiện diện. Nếu muốn kiểm `ProductRepository` thì thường nên inject **repository thật** chứ không import một service không liên quan.

Với `@JdbcTest`, một DAO/adapter nhỏ có thể được import vì nó chính là đối tượng cần kiểm:

~~~java
@JdbcTest
@Import(OrderJdbcAdapter.class)
class OrderJdbcAdapterTest {
    @Autowired OrderJdbcAdapter adapter;
    // Kiểm SQL qua DataSource test được cấu hình.
}
~~~

Đoạn này là **minh họa**, không độc lập vì cần `OrderJdbcAdapter`, DB/schema/migrations hoặc SQL fixtures của ứng dụng. Nếu adapter cần một clock hoặc converter nhỏ, import thật hoặc cấp `@Bean` test-only. Nhưng nếu mục tiêu là SQL đúng, **không dùng fake repository** rồi kết luận mapping/JPA transaction đúng.

Các data slices có thể tự dùng embedded DB theo cấu hình, nên cần biết test thực sự kết nối H2 hay PostgreSQL. Khi yêu cầu dialect/schema production, dùng PostgreSQL Testcontainers và cấu hình datasource phù hợp; có thể cần `@AutoConfigureTestDatabase(replace = NONE)` và `@ServiceConnection`/`@DynamicPropertySource` theo version.

Không import cả controller lẫn service điều phối email, broker và HTTP client vào JPA slice chỉ vì service constructor thiếu dependency. Nếu bạn thực sự cần workflow xuyên tầng, một integration test rõ ràng có giá trị hơn.

## 12. Security, advice, MVC converter: dependency cũng có ý nghĩa về hành vi

**Spring Security:** khi security starter có trong classpath, `@WebMvcTest` có thể kích hoạt filter chain. Lệnh request không xác thực có thể trả 401/403. Giải pháp đúng là thêm `spring-security-test` và thiết lập `@WithMockUser`/`csrf()` theo yêu cầu bảo mật; **không mặc định dùng `@AutoConfigureMockMvc(addFilters = false)`** để làm mọi test PASS. Chỉ tắt filter khi bài test cố ý không kiểm security và giới hạn đó được hiểu rõ.

**`@ControllerAdvice`:** thường thuộc nhóm web components được scan; nếu advice được đăng ký bằng cấu hình không thuộc slice, import advice/config liên quan và test status + error body thật.

**Jackson module/Converter:** một custom converter hoặc module đặt trong `@Configuration` thường có thể bị loại khỏi slice. Đưa đúng configuration qua `@Import` nếu cần kiểm JSON contract. Đừng mock chính serializer rồi coi đó là kiểm JSON thật.

**Validation:** để `@Valid` và constraint thật được đánh giá, cần validation provider trong classpath (ví dụ `spring-boot-starter-validation` nếu dự án dùng Bean Validation). Mock toàn bộ validator làm mất bằng chứng về các constraint annotations.

## 13. Sửa lỗi thiếu bean có hệ thống

### Lỗi 1: NoSuchBeanDefinitionException

Từ exception, tìm **type/qualifier thiếu chính xác**. Xác định nó thuộc phạm vi slice không. Chọn import thật nếu logic quan trọng, cấp mock/fake nếu chỉ là boundary. Đừng tự mở rộng component scan toàn ứng dụng.

### Lỗi 2: NoUniqueBeanDefinitionException

Nguyên nhân thường là vừa import real bean vừa cấp fake bean cùng type, hoặc import Clock test trong khi primary configuration đã có Clock. Chỉ giữ một bean phù hợp, hoặc dùng `@Qualifier`/override có mục đích. Tránh bật overriding global để che graph sai.

### Lỗi 3: @Mock field có nhưng controller vẫn không được inject

`@Mock` không tự có trong Spring context. Dùng `@MockitoBean` hoặc bean test config. Nếu unit test thuần Java thì tạo controller bằng constructor và truyền mock trực tiếp; không dùng Spring context khi không cần.

### Lỗi 4: enforceOverride=true làm context không lên

Slice có thể **chưa có bean target** do service bị filter. `@MockitoBean` mặc định REPLACE_OR_CREATE phù hợp khi chỉ muốn cấp collaborator thiếu. Chỉ enforce khi muốn chắc chắn thay bean hiện hữu.

### Lỗi 5: Import service lại thiếu repository/HTTP client

Đó là tín hiệu phạm vi test đang trôi khỏi MVC. Mock port hoặc chuyển sang integration test; không mở rộng imports vô hạn chỉ để hết exception.

### Lỗi 6: Test MVC trả 404/401/403 dù bean đã đủ

Tìm nguyên nhân tại mapping, controller scan, profile, security filters, CSRF, stub args. Không coi mọi status khác 200 là lỗi injection. Xem `MockMvc` response/exception và điều kiện request thực tế.

### Lỗi 7: “Unable to find a @SpringBootConfiguration”

Test không nằm đúng package hierarchy hoặc source root không rõ. Đặt test cùng hoặc dưới package application, hoặc chỉ định primary configuration rõ ràng theo mục tiêu. Không tạo root `@SpringBootApplication` giả trong test rồi vô tình thay phạm vi.

### Lỗi 8: State giả bị rò giữa test methods

Bean fake có thể là singleton trong context cache. Nếu fake có `Map`/`List` mutable, thiết kế reset/cleanup rõ ở `@BeforeEach` hoặc tạo test context riêng đúng mức. Không dùng `@DirtiesContext` cho mọi test chỉ để tránh viết cleanup.

### Lỗi 9: Mockito override làm mất AOP advice

Spring Framework thay mock trực tiếp; transaction, caching, retry và method security advice của target bean không tự được duy trì. Đừng mock đúng bean đang mang hành vi cần chứng minh.

### Lỗi 10: Test slice thành công nhưng production wiring lỗi

Bài slice chứng minh phần được nạp với fake/mock, không chứng minh full app. Dùng thêm `@SpringBootTest` smoke/integration test để kiểm auto-configuration/wiring tổng thể và các contract tests cho hạ tầng.

## 14. Checklist trước khi commit

- [ ] Xác định slice và thành phần SUT đang kiểm, giữ SUT chạy thật.
- [ ] Mỗi dependency thiếu được phân loại: logic thật, dữ liệu cố định, fake có state, boundary I/O hay auto-configuration.
- [ ] Dùng `@Import` cho real component nhỏ cần kiểm, không import cả graph.
- [ ] Dùng `@TestConfiguration + @Bean` cho fixture/fake có chủ đích.
- [ ] Dùng `@MockitoBean` để controller nhận mock **từ Spring context**, phân biệt với `@Mock` thuần Mockito.
- [ ] Hiểu mặc định REPLACE_OR_CREATE và chỉ bật `enforceOverride=true` nếu bean gốc phải tồn tại.
- [ ] Không đưa bean test vào production classpath hay scan rộng khiến các slice khác bị ảnh hưởng.
- [ ] Dùng `@EnableConfigurationProperties` khi cần kiểm binding thật.
- [ ] Dùng `@ImportAutoConfiguration` khi chủ đích bổ sung một auto-config class của Boot.
- [ ] Không chồng nhiều `@...Test` slices hoặc thêm `@SpringBootTest` vào slice chỉ để khắc phục thiếu bean.
- [ ] MVC test kiểm status/body/JSON và formatter thật khi nó thuộc contract.
- [ ] Security được test với identity/role/CSRF phù hợp, không tắt filters vô cớ.
- [ ] Fake stateful được dọn, test không phụ thuộc thứ tự và context cache.
- [ ] Repository/SQL, AOP, transaction, HTTP TCP và hệ thống ngoài có integration test riêng khi cần.
- [ ] Code Java 17+, import/annotation tương thích Spring Boot đang dùng; ví dụ Boot 3.5.x không mặc định áp dụng nguyên xi cho 4.x.

**Ghi nhớ:** test slice loại các dependency ngoài phạm vi **có chủ đích**. `@Import` đưa implementation thật cần chứng minh; `@TestConfiguration + @Bean` đưa fake/fixture xác định; `@MockitoBean` cấp mock đúng vào Spring context; `@EnableConfigurationProperties` bổ sung bean binding; `@ImportAutoConfiguration` bổ sung auto-configuration. Nếu phải đưa cả hệ thống vào chỉ để một controller test chạy, hãy xem lại mục tiêu và chọn đúng tầng kiểm thử.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): test slices, `@WebMvcTest`, `@Import` và `@MockitoBean`.
- [Spring Boot 3.5 — Test Slice Auto-configuration](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): những auto-configuration được nạp cho từng loại slice.
- [Spring Framework 6.2 — MockitoBean / MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): replace-or-create, enforceOverride và spies.
- [Spring Framework — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html): cách thay bean và ảnh hưởng tới AOP.
- [Spring Framework — TestBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-testbean.html): bean test từ static factory method.
- [Spring Boot 4 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): so sánh package/module khi nâng Spring Boot.
