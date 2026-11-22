# Chọn @WebMvcTest, @WebFluxTest, @JsonTest hoặc slice dữ liệu

## 1. Test slice là gì và tại sao phải chọn đúng?

Trong **Spring Boot - testing**, một bài test không nhất thiết cần nạp mọi bean của ứng dụng. Ví dụ, khi kiểm tra endpoint REST, ta cần bộ định tuyến HTTP, controller, chuyển đổi JSON và một đối tượng thay thế cho service; không cần tạo repository, datasource, scheduler và client gửi email thật.

**Test slice** là một cấu hình kiểm thử do Spring Boot cung cấp để chỉ nạp một **phần (slice) của ApplicationContext**: chọn những bean, component scan và auto-configuration có liên quan đến tầng đang kiểm tra. Việc này thường giúp test nhanh hơn và làm lỗi dễ định vị hơn so với nạp toàn ứng dụng bằng `@SpringBootTest`.

Bốn câu hỏi quyết định annotation:

1. **Đang kiểm tra trách nhiệm nào?** HTTP mapping/validation/response, reactive web pipeline, JSON serialization, hay repository/database?
2. **Ứng dụng dùng công nghệ nào?** Spring MVC, Spring WebFlux, Jackson/Gson/JSON-B, JPA, JDBC, MongoDB, R2DBC...?
3. **Cần chạy phụ thuộc nào thật?** Controller thật nhưng service mock? Entity/repository thật với DB test? Hay chỉ logic POJO?
4. **Cần chứng minh tính tích hợp đến đâu?** Chỉ một tầng hay toàn bộ luồng HTTP → service → persistence?

Một slice test **vẫn nạp Spring context**, nhưng nhỏ hơn toàn bộ ứng dụng. Nó không đồng nghĩa unit test thuần Java không có Spring. Chọn slice nhỏ nhất **vẫn đủ chứng minh hành vi được yêu cầu**, chứ không chọn slice nhỏ nhất bằng mọi giá.

### Ma trận chọn nhanh

| Mục tiêu cần chứng minh | Annotation phù hợp | Công cụ kiểm thử nổi bật | Thường không nạp |
| --- | --- | --- | --- |
| Spring **MVC** controller, route, status, JSON body, advice, filter | `@WebMvcTest(Controller.class)` | `MockMvc`, có thể `MockMvcTester` | Service/repository thông thường |
| Spring **WebFlux** controller, reactive response, route | `@WebFluxTest(Controller.class)` | `WebTestClient` | Service/repository thông thường |
| Một object serialize/deserialize JSON đúng hợp đồng | `@JsonTest` | `JacksonTester<T>`, `ObjectMapper`, Gson/JSON-B tester tùy stack | Controller, service, repository |
| JPA entity/repository/query | `@DataJpaTest` | Spring Data JPA repository, `TestEntityManager`, `EntityManager` | Web controller, service thông thường |
| Truy vấn SQL thuần với `DataSource`/`JdbcTemplate` | `@JdbcTest` | `JdbcTemplate` | JPA repositories, web |
| Spring Data JDBC repository | `@DataJdbcTest` | Repository, `JdbcTemplate` | Web, JPA |
| Reactive SQL với Spring Data R2DBC | `@DataR2dbcTest` | R2DBC repository, `R2dbcEntityTemplate` | Web, JPA |
| MongoDB document/repository | `@DataMongoTest` | `MongoTemplate`, Mongo repository | Web/service thông thường |
| Luồng thật xuyên nhiều tầng, wiring toàn ứng dụng | `@SpringBootTest` | `MockMvc`/`WebTestClient` hoặc server thật tùy cấu hình | Không giới hạn theo slice |
| Hàm nghiệp vụ không cần Spring | JUnit + Mockito (nếu cần) | `new`, `assertEquals`, `@Mock` | Toàn bộ Spring context |

Các slice khác như `@DataRedisTest`, `@DataNeo4jTest`, `@JooqTest`, `@RestClientTest` và `@WebClientTest` cũng tồn tại trong hệ sinh thái Boot 3.x. Hãy chọn theo **technology boundary**, không dựa đơn thuần vào tên package.

**Nguyên tắc quan trọng:** Spring Boot **không hỗ trợ gắn nhiều annotation slice** như `@WebMvcTest` và `@DataJpaTest` cùng lúc lên một class test. Khi cần thêm chức năng, có thể dùng một slice và tùy chỉnh các `@AutoConfigure...`/`@ImportAutoConfiguration` thích hợp; nếu đã cần phần lớn ứng dụng, hãy cân nhắc `@SpringBootTest`.

## 2. Test slice thật sự giới hạn những gì?

Một `@...Test` thường thực hiện đồng thời:

- Giới hạn thành phần được component scan (không nạp mọi `@Service`, `@Repository`, `@ConfigurationProperties` theo cách ứng dụng đầy đủ).
- Chỉ bật tập **auto-configuration được phép** cho tầng đó, ví dụ MVC test infrastructure hoặc JPA repositories.
- Đăng ký tích hợp JUnit Jupiter/Spring TestContext và các test helper phù hợp.
- Vẫn dùng cơ chế **Spring context cache**; các test class có cấu hình tương đương có thể tái dùng context.

Để hiểu lỗi `NoSuchBeanDefinitionException`, cần nhớ: **bị loại khỏi slice không nhất thiết nghĩa là code ứng dụng thiếu bean**. Có thể bean đó tồn tại khi chạy thật, nhưng slice chủ đích không scan nó. Khi test controller cần một service, dùng `@MockitoBean` để thêm mock thay thế ở **Spring context**, hoặc import một cấu hình thật có chủ đích.

Ví dụ `@WebMvcTest(ProductController.class)` chỉ tải controller mục tiêu và hạ tầng web liên quan; nó không tự khởi tạo mọi `@Service` được controller inject. Nếu test muốn chứng minh service thật và repository thật tương tác, `@WebMvcTest` không phải công cụ chính.

### Vì sao không dùng @SpringBootTest cho tất cả?

`@SpringBootTest` có thể là lựa chọn đúng cho integration test, nhưng khi dùng để chứng minh một quy tắc JSON hoặc route đơn lẻ, nó có thể:

- Phải khởi tạo thêm hạ tầng không liên quan, dẫn tới test chậm.
- Thất bại vì cấu hình database/email/queue, che lấp lỗi của mục tiêu chính.
- Buộc sử dụng nhiều mock hơn cần thiết.
- Tạo nhiều biến thể context/cache khi profile, properties hoặc bộ mock khác nhau.

Tuy vậy, **slice không bảo đảm nhanh trong mọi dự án**: context nhỏ vẫn phải tạo, và cách tổ chức test/configuration ảnh hưởng cache reuse. Cần đo kết quả thực, không mặc định rằng mọi slice test đều nhanh hơn mọi unit test hay mọi full-context test.

## 3. Phiên bản, cấu trúc dự án và dependencies

Các ví dụ bên dưới chọn **Java 17 + Spring Boot 3.5.x + JUnit Jupiter** để có API và import nhất quán. Ở Boot 3.4/3.5, annotation `@MockitoBean` thuộc:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
~~~

Nó thay/đăng ký bean mock trong Spring TestContext. `@Mock` thuần của Mockito **không tự thay Spring bean**. `@MockBean` cũ trong Spring Boot 3.4/3.5 đã deprecated và hướng tới `@MockitoBean`. Không sao chép nguyên các import của Boot 3.5 sang **Spring Boot 4.x** mà chưa kiểm tra lại: các module test và package auto-configuration đã được tổ chức lại.

Để tránh nhầm stack, bài dùng **hai dự án ví dụ độc lập**:

- **Dự án A — `slice-web-data`:** Spring MVC, Jackson JSON và Spring Data JPA/H2. Các test `@WebMvcTest`, `@JsonTest`, `@DataJpaTest` nằm cùng project nhưng kiểm tra các slice khác nhau.
- **Dự án B — `slice-webflux`:** chỉ dùng Spring WebFlux (không kéo `spring-boot-starter-web`), có test `@WebFluxTest` riêng.

Giữ riêng WebFlux ở dự án B là quyết định có chủ đích. Khi Spring MVC và WebFlux **cùng nằm trên classpath**, Boot mặc định ưu tiên **MVC** khi suy ra loại ứng dụng; trong full application test muốn reactive cần chọn web application type phù hợp. Test của hai web stack không nên bị trộn lẫn một cách vô tình.

### Cấu hình Gradle nền tảng

**Dự án A — phần liên quan trong `build.gradle` (Groovy DSL):**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Dự án B — phần liên quan trong `build.gradle`:**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Hai khối trên là **đoạn cấu hình**, giả định từng dự án đã có Spring Boot plugin 3.5.x, repository, dependency management và Java toolchain 17+. Không dán hai khối vào cùng một project để chạy mọi ví dụ. Các lớp Java đặt trong đúng package và source set `src/main/java` hoặc `src/test/java`.

Nếu dự án A dùng Spring Security, cần thêm test support tương ứng và thiết kế các ca xác thực/ủy quyền. Các ví dụ runnable dưới đây giả định **chưa cài đặt Spring Security**, để không vô tình nhận `401`/`403` do filter chain.

## 4. @WebMvcTest: kiểm tra Spring MVC controller bằng MockMvc

**Khi chọn:** ứng dụng dùng servlet stack/Spring MVC với `@RestController`, `@GetMapping`, `@PostMapping`, validation của web, exception handler, filter hoặc JSON response. Bạn muốn chạy routing và serialization của Spring MVC **thật**, nhưng không gọi database hay remote service.

`@WebMvcTest` thường nạp `@Controller`, `@ControllerAdvice`, `@JsonComponent`, một số converter, filter, interceptor và các MVC infrastructure được Boot cho phép. Các `@Service`/`@Repository` thông thường **không được tự scan**. `MockMvc` thực hiện request qua MVC stack **không cần khởi động HTTP server thật**.

### 4.1. Ví dụ hoàn chỉnh ở dự án A

Tất cả các tệp thuộc package `com.example.slicedemo`.

**`src/main/java/com/example/slicedemo/SliceDemoApplication.java`:**

~~~java
package com.example.slicedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SliceDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SliceDemoApplication.class, args);
    }
}
~~~

Lớp này giúp các slice test tìm được cấu hình gốc khi chạy. Bản demo nạp từng slice; không cần khởi động toàn ứng dụng để chứng minh test MVC/JSON/JPA.

**`src/main/java/com/example/slicedemo/ProductView.java`:**

~~~java
package com.example.slicedemo;

public record ProductView(String sku, String name) {
}
~~~

**`src/main/java/com/example/slicedemo/ProductCatalog.java`:**

~~~java
package com.example.slicedemo;

public interface ProductCatalog {
    ProductView findBySku(String sku);
}
~~~

**`src/main/java/com/example/slicedemo/ProductController.java`:**

~~~java
package com.example.slicedemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/products")
public class ProductController {
    private final ProductCatalog catalog;

    public ProductController(ProductCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/{sku}")
    public ProductView find(@PathVariable String sku) {
        return catalog.findBySku(sku);
    }
}
~~~

**`src/test/java/com/example/slicedemo/ProductControllerTest.java`:**

~~~java
package com.example.slicedemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
class ProductControllerTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    ProductCatalog catalog;

    @Test
    void getProduct_whenCatalogReturnsData_writesJsonResponse()
            throws Exception {
        when(catalog.findBySku("P-1"))
                .thenReturn(new ProductView("P-1", "Notebook"));

        mvc.perform(get("/products/P-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku").value("P-1"))
                .andExpect(jsonPath("$.name").value("Notebook"));

        verify(catalog).findBySku("P-1");
    }

    @Test
    void getUnknownPath_returnsNotFoundWithoutCallingCatalog()
            throws Exception {
        mvc.perform(get("/not-an-endpoint"))
                .andExpect(status().isNotFound());
    }
}
~~~

**Những gì test chứng minh:**

- URL `GET /products/P-1` được map đến method controller và trả HTTP 200.
- `ProductView` được JSON converter serialize thành body có `sku`/`name` đúng.
- Controller thực sự gọi collaborator `ProductCatalog` với SKU đúng.
- URL không có route trả 404 (trong cấu hình web test đang dùng).

`@MockitoBean` cung cấp mock **bên trong ApplicationContext**. Controller là bean thật. Nếu thay `@MockitoBean` bằng `@Mock` thuần Mockito thì controller có thể thiếu dependency trong slice hoặc dùng bean khác, vì `@Mock` không tự đăng ký vào Spring context.

### 4.2. MVC validation, security và exception handler

Với POST nhận `@Valid @RequestBody`, nếu dự án có `spring-boot-starter-validation`, `@WebMvcTest` là nơi phù hợp để kiểm tra HTTP 400 khi DTO vi phạm Jakarta constraint. Tương tự, `@ControllerAdvice`/`@ExceptionHandler` có thể được kiểm tra bằng request thật đi qua Spring MVC test infrastructure.

Nếu Spring Security có trên classpath, security filter có thể được áp dụng trong `@WebMvcTest`. Kiểm tra `401`/`403` là hành vi có ý nghĩa. Để mô phỏng người dùng hoặc CSRF, dùng `spring-security-test` và helper như `@WithMockUser`, `csrf()` khi thích hợp. Không tắt filter bằng `@AutoConfigureMockMvc(addFilters = false)` chỉ để làm test xanh, trừ khi **mục tiêu của test chủ động loại security** và có test bảo vệ security ở nơi khác.

`@WebMvcTest` không chứng minh database transaction hoặc service logic thật. Nếu endpoint được cho là trả 404 khi không có entity nhưng controller chỉ truyền thẳng kết quả của mock, cần stub hoặc cấu hình nhánh lỗi tương ứng; một `404` từ đường dẫn không tồn tại **không thay thế** ca service báo thiếu dữ liệu.

## 5. @WebFluxTest: kiểm tra reactive controller bằng WebTestClient

**Khi chọn:** ứng dụng thực sự dùng **Spring WebFlux**, endpoint trả `Mono<T>`/`Flux<T>` hoặc xử lý luồng reactive và cần kiểm tra routing/JSON/status mà không khởi động toàn app. `@WebFluxTest` tải các thành phần web reactive đã cho phép, nhưng không tự scan mọi service hay repository.

`WebTestClient` gửi request đến **mock WebFlux infrastructure**; trong chế độ slice này không cần lắng nghe cổng HTTP thật. `exchange()` bắt đầu gửi request qua chuỗi xử lý reactive, sau đó dùng `expectStatus()`/`expectBody()`.

### 5.1. Ví dụ hoàn chỉnh ở dự án B (WebFlux riêng)

Package là `com.example.fluxdemo`.

**`src/main/java/com/example/fluxdemo/FluxDemoApplication.java`:**

~~~java
package com.example.fluxdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FluxDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FluxDemoApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/fluxdemo/StatusView.java`:**

~~~java
package com.example.fluxdemo;

public record StatusView(String code, String label) {
}
~~~

**`src/main/java/com/example/fluxdemo/StatusLookup.java`:**

~~~java
package com.example.fluxdemo;

import reactor.core.publisher.Mono;

public interface StatusLookup {
    Mono<StatusView> find(String code);
}
~~~

**`src/main/java/com/example/fluxdemo/StatusController.java`:**

~~~java
package com.example.fluxdemo;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/statuses")
public class StatusController {
    private final StatusLookup lookup;

    public StatusController(StatusLookup lookup) {
        this.lookup = lookup;
    }

    @GetMapping("/{code}")
    public Mono<StatusView> get(@PathVariable String code) {
        return lookup.find(code)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND, "Status not found"
                        )
                ));
    }
}
~~~

**`src/test/java/com/example/fluxdemo/StatusControllerTest.java`:**

~~~java
package com.example.fluxdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebFluxTest(StatusController.class)
class StatusControllerTest {
    @Autowired
    WebTestClient client;

    @MockitoBean
    StatusLookup lookup;

    @Test
    void getStatus_whenFound_returnsJson() {
        when(lookup.find("A"))
                .thenReturn(Mono.just(new StatusView("A", "Available")));

        client.get().uri("/statuses/A")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.code").isEqualTo("A")
                .jsonPath("$.label").isEqualTo("Available");

        verify(lookup).find("A");
    }

    @Test
    void getStatus_whenMissing_returns404() {
        when(lookup.find("missing"))
                .thenReturn(Mono.empty());

        client.get().uri("/statuses/missing")
                .exchange()
                .expectStatus().isNotFound();

        verify(lookup).find("missing");
    }
}
~~~

**Điểm khác MVC:**

- Service contract trả một `Mono<StatusView>` chứ không trả `StatusView` trực tiếp.
- Khi lookup trả `Mono.empty()`, controller chuyển thành `ResponseStatusException(404)`; đây là quy tắc được viết rõ, không giả định rằng `Mono.empty()` **tự động** nghĩa là HTTP 404.
- Test dùng `WebTestClient`, không dùng `MockMvc`.
- Không cần mở cổng server; đây vẫn là slice test của controller reactive.

### 5.2. Functional endpoints và custom security

`@WebFluxTest` **không tự phát hiện toàn bộ route tạo bằng `RouterFunction`/functional WebFlux**. Nếu dùng functional routing, cân nhắc test bằng `WebTestClient.bindToRouterFunction(...)` trong Spring Test, `@Import` đúng `RouterFunction`/handler cần thiết hoặc `@SpringBootTest` khi muốn kiểm tra wiring thật. Đừng giả định test controller annotation đã bao phủ một route chức năng không thuộc controller đó.

Một bean `SecurityWebFilterChain` khai báo trong custom `@Configuration` cũng có thể không được slice tự tìm thấy. Nếu cần chứng minh security config, import cấu hình một cách có chủ đích hoặc chọn integration test phù hợp.

### 5.3. Không đồng nhất WebFluxTest với reactive database test

Một ứng dụng WebFlux dùng MongoDB reactive hoặc R2DBC sẽ có hai boundary khác nhau: **web reactive** và **persistence reactive**. `@WebFluxTest` không nhằm test truy vấn Mongo/R2DBC. Với reactive repository, chọn data slice tương ứng (ví dụ `@DataR2dbcTest`) hoặc integration test với DB test thực.

## 6. @JsonTest: kiểm tra hợp đồng JSON mà không gọi controller

**Khi chọn:** yêu cầu chính là serialize/deserialize DTO đúng tên field, định dạng, cấu hình Jackson module, date/time hoặc một `@JsonComponent` tùy chỉnh. Không cần HTTP route, filter hay server.

`@JsonTest` có thể cấu hình các mapper được hỗ trợ hiện diện trên classpath, như **Jackson**, Gson, JSON-B; với Jackson, có thể inject `JacksonTester<T>` hoặc `ObjectMapper`. Nó **không** kiểm tra rằng `@GetMapping` có được đăng ký hay controller có trả status đúng không; đó là mục tiêu của web slice.

### 6.1. Ví dụ hoàn chỉnh trong dự án A

**`src/main/java/com/example/slicedemo/InvoicePayload.java`:**

~~~java
package com.example.slicedemo;

import com.fasterxml.jackson.annotation.JsonProperty;

public record InvoicePayload(
        @JsonProperty("invoice_id") String invoiceId,
        int quantity
) {
}
~~~

**`src/test/java/com/example/slicedemo/InvoicePayloadJsonTest.java`:**

~~~java
package com.example.slicedemo;

import java.io.IOException;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

import static org.assertj.core.api.Assertions.assertThat;

@JsonTest
class InvoicePayloadJsonTest {
    @Autowired
    JacksonTester<InvoicePayload> json;

    @Test
    void serialize_usesConfiguredSnakeCaseField() throws IOException {
        InvoicePayload source = new InvoicePayload("INV-7", 2);

        assertThat(json.write(source))
                .extractingJsonPathStringValue("@.invoice_id")
                .isEqualTo("INV-7");

        assertThat(json.write(source))
                .extractingJsonPathNumberValue("@.quantity")
                .satisfies(number -> assertThat(number.intValue()).isEqualTo(2));
    }

    @Test
    void deserialize_populatesRecordComponents() throws IOException {
        String source = """
                {"invoice_id":"INV-7","quantity":2}
                """;

        InvoicePayload parsed = json.parseObject(source);

        assertThat(parsed).isEqualTo(new InvoicePayload("INV-7", 2));
    }
}
~~~

`@JsonProperty("invoice_id")` là hợp đồng đặt tên của JSON, khác tên component Java `invoiceId`. Hai test chứng minh **hai chiều** serialization/deserialization. So sánh số JSON qua `Number.intValue()` giúp tránh phụ thuộc kiểu Number cụ thể do JSONPath trả về.

Nếu muốn so sánh toàn bộ JSON, dùng `isEqualToJson("expected.json")` với fixture đúng vị trí trong `src/test/resources` hoặc assertion JSON tương đương; không nên so sánh chuỗi JSON thô nếu thứ tự field/whitespace không phải hợp đồng.

### 6.2. Khi @JsonTest là chưa đủ

Nếu hệ thống yêu cầu “request JSON thiếu trường bắt buộc trả HTTP 400”, việc `@JsonTest` deserialize thành công hay thất bại **không chứng minh** controller đã bật `@Valid`, configured exception handler hoặc HTTP status. Hãy dùng `@WebMvcTest`/`@WebFluxTest` để kiểm tra giao tiếp HTTP. Nếu cần test toàn bộ security, validation, transaction và database theo một request thật, cân nhắc full integration test.

Với custom `ObjectMapper` hoặc Jackson `Module`, bảo đảm cấu hình ấy thực sự nằm trong slice theo scan/auto-config/`@Import` phù hợp; không tự kết luận rằng `@JsonTest` đã nạp tất cả `@Configuration` từ ứng dụng.

## 7. @DataJpaTest: kiểm thử repository, entity mapping và query

**Khi chọn:** cần xác minh JPA `@Entity`, ánh xạ cột, repository query, constraint ở tầng DB/JPA và behavior của persistence. `@DataJpaTest` thường scan entity và Spring Data JPA repository, tạo `EntityManager`/`TestEntityManager`, nhưng không scan các `@Service`/controller thông thường.

Theo mặc định, `@DataJpaTest` có **test-managed transaction** và **rollback sau mỗi test**, trong môi trường transaction manager được cấu hình phù hợp. Khi thư viện embedded DB tồn tại trên classpath, Boot có thể cấu hình nó cho test; ví dụ dùng **H2**.

### 7.1. Ví dụ hoàn chỉnh trong dự án A

**`src/main/java/com/example/slicedemo/InventoryItem.java`:**

~~~java
package com.example.slicedemo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    protected InventoryItem() {
    }

    public InventoryItem(String sku) {
        this.sku = sku;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }
}
~~~

**`src/main/java/com/example/slicedemo/InventoryItemRepository.java`:**

~~~java
package com.example.slicedemo;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryItemRepository
        extends JpaRepository<InventoryItem, Long> {
    Optional<InventoryItem> findBySku(String sku);
}
~~~

**`src/test/java/com/example/slicedemo/InventoryItemRepositoryTest.java`:**

~~~java
package com.example.slicedemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(properties = "spring.jpa.hibernate.ddl-auto=create-drop")
class InventoryItemRepositoryTest {
    @Autowired
    TestEntityManager entityManager;

    @Autowired
    InventoryItemRepository repository;

    @Test
    void findBySku_whenRowExists_returnsMappedEntity() {
        InventoryItem stored = new InventoryItem("SKU-7");
        entityManager.persistAndFlush(stored);
        entityManager.clear();

        var found = repository.findBySku("SKU-7");

        assertThat(found).isPresent();
        assertThat(found.orElseThrow().getSku()).isEqualTo("SKU-7");
    }

    @Test
    void findBySku_whenMissing_returnsEmptyOptional() {
        assertThat(repository.findBySku("missing")).isEmpty();
    }
}
~~~

Bài test tạo một entity thật, ghi và `flush` xuống DB test, xóa persistence context của `EntityManager` để buộc truy vấn repository đọc lại, sau đó assert kết quả. Annotation `@DataJpaTest` tạo test slice persistence; không cần mock repository vì **repository là đối tượng cần kiểm tra thật**.

Thuộc tính `spring.jpa.hibernate.ddl-auto=create-drop` trong ví dụ chủ động yêu cầu Hibernate tạo schema test cho mô hình đơn giản. Trong dự án có Flyway/Liquibase, schema/migration thực tế, hãy dùng chiến lược tạo schema nhất quán với mục tiêu của test; không mặc định `create-drop` phù hợp mọi hệ thống.

### 7.2. H2 khác database sản xuất

Test qua H2 hữu ích nhưng **không chứng minh** query và transaction hoạt động giống PostgreSQL, MySQL hay Oracle trong mọi trường hợp. Những khác biệt có thể gồm SQL dialect, collation, tính năng JSON, index, lock, concurrency, native query và constraint semantics.

Khi cần độ trung thực cao hơn, dùng database cùng loại với production qua Testcontainers hoặc DB test chuyên dụng, và cấu hình đúng datasource. `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)` là một cách ngăn Boot thay datasource test đã chủ động cung cấp (áp dụng trong trường hợp phù hợp). Đây là đổi **hạ tầng DB** của data slice, không biến `@DataJpaTest` thành full application test.

**Rollback không tương đương reset mọi thứ:** sequence/identity hoặc side effect bên ngoài transaction có thể không rollback; DB khác nhau có chính sách DDL/transaction khác nhau. Nếu test chạy sang thread/process khác, đừng mặc định chung test-managed transaction.

## 8. Chọn đúng data slice: JPA, JDBC, R2DBC, MongoDB

Chữ **“dữ liệu”** không đồng nghĩa với **JPA**. Chọn theo thư viện và API thật mà ứng dụng sử dụng:

| Stack lưu trữ | Slice | Đối tượng bạn thường cần test | Ghi chú quan trọng |
| --- | --- | --- | --- |
| Hibernate/JPA + Spring Data repository | `@DataJpaTest` | `JpaRepository`, `EntityManager`, entity mapping | Transaction + rollback mặc định |
| SQL bằng `JdbcTemplate` và `DataSource` | `@JdbcTest` | SQL thực thi qua JdbcTemplate | Có DB test và rollback mặc định |
| Spring Data JDBC | `@DataJdbcTest` | Spring Data JDBC repositories | Khác JPA, có transaction/rollback mặc định |
| Spring Data R2DBC | `@DataR2dbcTest` | Reactive repositories, `R2dbcEntityTemplate` | **Không transactional mặc định** theo test slice |
| MongoDB (sync/reactive tùy cấu hình/driver) | `@DataMongoTest` | Mongo repositories, `MongoTemplate` | Cần MongoDB test thực sự khả dụng |
| Neo4j | `@DataNeo4jTest` | Neo4j repositories, graph mapping | Phân biệt reactive access và transaction support |
| Redis | `@DataRedisTest` | Redis repositories, key/value mapping | Không phải một SQL/JPA test |
| jOOQ | `@JooqTest` | `DSLContext`, SQL mapping | Dùng schema/datasource phù hợp |

**Đừng dùng `@DataJpaTest` cho dự án chỉ dùng MongoDB**, cũng đừng dùng `@WebFluxTest` để kiểm tra reactive repository chỉ vì API trả `Flux`. Công nghệ của tầng dữ liệu quyết định data slice.

### @JdbcTest và @DataJdbcTest khác nhau

`@JdbcTest` tập trung `DataSource` và `JdbcTemplate` cho thao tác SQL, không tự tạo toàn bộ Spring Data JDBC repository. `@DataJdbcTest` thêm infrastructure và scan repository của Spring Data JDBC. Nếu code dùng một lớp DAO gọi `JdbcTemplate`, `@JdbcTest` thường vừa đủ; nếu code dùng Spring Data JDBC repository interface, chọn `@DataJdbcTest`.

Một minh họa ngắn cho `@JdbcTest` (đặt trong dự án có H2 và đủ cấu hình test):

~~~java
package com.example.slicedemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@JdbcTest
class ArithmeticJdbcTest {
    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void queryForObject_returnsScalarFromDatabase() {
        Integer value = jdbcTemplate.queryForObject(
                "SELECT 2 + 3", Integer.class
        );

        assertThat(value).isEqualTo(5);
    }
}
~~~

Ví dụ này minh họa **JdbcTemplate thật chạy SQL qua DB test**, không chứng minh một repository nghiệp vụ vì không có DAO riêng. Nếu muốn test DAO thật, import rõ DAO/config hoặc đặt nó trong cấu hình mà slice hỗ trợ; không tự cho rằng mọi `@Repository` của dự án sẽ được scan.

### @DataR2dbcTest có được rollback mặc định không?

**Không.** Theo hành vi mặc định của Spring Boot 3.5, `@DataR2dbcTest` không bao quanh test bằng một transaction tự động như `@DataJpaTest`. Reactive transaction cần ngữ cảnh reactive và cơ chế quản lý riêng. Vì vậy phải tự thiết kế isolation/cleanup của dữ liệu test khi dùng reactive database.

### @DataMongoTest có tự cung cấp MongoDB server không?

Nó cấu hình các thành phần data Mongo như `MongoTemplate` và repositories, nhưng **không có nghĩa chỉ cần annotation thì luôn có MongoDB server chạy sẵn**. Cần một MongoDB test endpoint/instance phù hợp, ví dụ thông qua Testcontainers, môi trường test hoặc công cụ embedded tương thích nếu dự án đã chủ động cấu hình. Không trỏ test vào production MongoDB chỉ để sửa lỗi kết nối.

## 9. Khi thiếu bean trong slice: sửa đúng lớp thay vì làm rộng toàn bộ test

Một triệu chứng điển hình:

~~~text
UnsatisfiedDependencyException:
  No qualifying bean of type 'ProductCatalog' available
~~~

Với `@WebMvcTest(ProductController.class)`, đó thường là hậu quả **có chủ đích** của filter component scan: controller cần `ProductCatalog` nhưng service implement bị loại khỏi slice.

Các cách xử lý, theo mục tiêu:

1. **Mock collaborator bên ngoài phạm vi đang kiểm thử:** `@MockitoBean ProductCatalog catalog;` khi chỉ test controller.
2. **Import implementation/cấu hình thật có chủ đích:** `@Import(...)` nếu cần chạy một formatter, converter, exception mapper hoặc bean hỗ trợ nhỏ mà slice không quét.
3. **Nạp configuration properties có chủ đích:** `@EnableConfigurationProperties(SomeProperties.class)` khi slice cần `@ConfigurationProperties` cụ thể.
4. **Cần nhiều lớp nghiệp vụ và persistence thật:** chuyển sang `@SpringBootTest` hoặc phân tách thành nhiều slice tests kiểm tra từng hợp đồng rõ ràng.

**Không chữa lỗi bằng cách thêm `@ComponentScan("com.example")` vô điều kiện.** Nó có thể phá filter slice, kéo vào nhiều bean ngoài ý muốn và làm test giống full context nhưng khó hiểu hơn. Spring Boot cảnh báo rằng đặt `@ComponentScan` riêng trên lớp `@SpringBootApplication` có thể ghi đè các exclude filters dùng để slicing.

### @Import và @ImportAutoConfiguration khác mục đích

- `@Import(MySmallConfig.class)`: thêm một lớp `@Configuration` hoặc component cụ thể.
- `@ImportAutoConfiguration(SomeAutoConfiguration.class)`: bổ sung **auto-configuration** của Boot theo cơ chế đúng.

Không nên dùng `@Import` thông thường để thêm một auto-configuration vốn phải được xử lý theo cơ chế Boot. Nếu cần thêm hạ tầng, kiểm tra trước liệu slice có `@AutoConfigure...` tương ứng không.

## 10. Khi nào phải chuyển từ slice sang @SpringBootTest?

Chọn `@SpringBootTest` khi mục tiêu thực sự là:

- Kiểm tra controller → service thật → repository thật trong cùng Spring context.
- Chứng minh bean wiring, transaction boundary, security chain hoặc configuration tích hợp nhiều tầng.
- Chạy với server thật trên cổng ngẫu nhiên để kiểm tra HTTP qua socket.
- Kiểm tra quy trình đa thành phần như gửi event, job, queue hoặc tương tác nhiều bean mà test slice cố tình loại bỏ.

Các cấu hình hay gặp:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class FullContextMockMvcTest {
    // Spring MVC, context đầy đủ; HTTP request mock qua MockMvc.
}
~~~

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealServerTest {
    // Context đầy đủ, embedded server thực chạy ở cổng ngẫu nhiên.
}
~~~

Đây là **annotation skeleton**, chưa đủ để chạy như tệp Java độc lập; cần lớp application, dependencies, imports và method `@Test`. Với WebFlux full context, có thể dùng `@AutoConfigureWebTestClient` theo stack phù hợp.

**Chú ý giao dịch:** Một full test có `RANDOM_PORT` thường cho HTTP client và server chạy ở hai luồng khác nhau. `@Transactional` quanh test method ở phía client **không tự rollback transaction trên server**. Không dùng “test có `@Transactional`” như lời bảo đảm dữ liệu server đã sạch sau HTTP request thật.

## 11. Chi phí context, cache và tổ chức bộ test

Spring TestContext cache **ApplicationContext theo cấu hình test**, không theo tên một lớp riêng lẻ. Nếu hai lớp `@WebMvcTest` chọn controller khác nhau, tập mock khác nhau, profile hoặc test property khác nhau, khóa context có thể khác dẫn đến nhiều lần startup.

Một số nguyên tắc vận hành:

- Giữ phạm vi controller mục tiêu rõ ràng, ví dụ `@WebMvcTest(ProductController.class)` thay vì quét tùy ý quá nhiều controller.
- Chỉ khai báo `@MockitoBean` thực sự cần thiết; cùng mục tiêu giữa các lớp nên giữ tên field/qualifier nhất quán để tránh cache key khác không cần thiết.
- Tránh lạm dụng `@DirtiesContext` vì nó có thể khiến cache phải nạp lại.
- Dùng log `org.springframework.test.context.cache=DEBUG` để xem hit/miss nếu startup time trở thành vấn đề.
- Đừng trộn annotation slice khác nhau lên một lớp; nếu cần nhiều tầng, chọn đúng test level.
- Trong CI, đừng kỳ vọng hai JVM test worker riêng có thể chia sẻ static cache của Spring.
- Tách test chạy ngoài Spring (unit test Java) cho quy tắc thuần dữ liệu.

**Cân bằng cần thiết:** hai slice khác nhau tạo hai loại context là chuyện bình thường và đúng đắn. Không tối ưu “ít context nhất” bằng cách bỏ mất kiểm thử quan trọng hoặc dùng một context quá lớn cho mọi bài.

## 12. Lỗi thường gặp khi chọn test slice

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Test `@RestController` MVC bằng `@WebFluxTest` | Test infrastructure khác stack controller | Chọn `@WebMvcTest` cho Spring MVC |
| Test WebFlux controller bằng `MockMvc` | `MockMvc` thuộc servlet MVC | Chọn `@WebFluxTest` + `WebTestClient` |
| Dùng `@JsonTest` để khẳng định HTTP status | Không có routing/web exception handling | Dùng web slice |
| Dùng `@WebMvcTest` rồi đòi load repository thật | Repository thường bị loại | Mock service boundary hoặc test full integration |
| Dùng `@DataJpaTest` cho SQL R2DBC | JPA và R2DBC là hai cơ chế khác | Chọn `@DataR2dbcTest` |
| Cho rằng `@DataJpaTest` luôn dùng production DB | Thường thay bằng embedded DB nếu có | Kiểm tra datasource, dùng test DB phù hợp |
| Cho rằng `@DataMongoTest` tự khởi động Mongo server | Slice chỉ cấu hình hạ tầng Spring Data | Cấp server test bằng Testcontainers hay môi trường |
| Đọc `@Mock` như bean override | Mockito mock chỉ thuộc test field/parameter | Dùng `@MockitoBean` cho Spring context |
| Thiếu Spring Security test support | Filter trả 401/403 khi test kỳ vọng 200 | Kiểm tra auth/CSRF với test security |
| Gắn nhiều slice annotations | Spring Boot không hỗ trợ phối trộn trực tiếp | Chọn một slice, điều chỉnh hoặc full context |
| Nhập `@Import` cho auto-configuration | Auto-config có cơ chế đăng ký riêng | Dùng `@ImportAutoConfiguration` khi cần |
| Tự thêm `@ComponentScan` quá rộng | Có thể phá slice filtering | Dùng import/config có phạm vi nhỏ |
| Không có `@SpringBootConfiguration` được tìm thấy | Test không xác định được cấu hình Boot gốc | Đặt test dưới package app hoặc chỉ định cấu hình phù hợp |
| Dùng H2 để tuyên bố đã test PostgreSQL-specific SQL | Dialect và transaction semantics khác | Test DB cùng loại production |
| Test pass từng lớp nhưng fail khi chạy suite | Dữ liệu/bean mock mutable state bị rò | Cô lập dữ liệu, không phụ thuộc thứ tự |
| Cố làm tất cả bài thành `@SpringBootTest` | Nạp hạ tầng ngoài mục tiêu, suite chậm | Chọn đúng slice và vài integration tests có chủ đích |

## 13. Cách chạy các ví dụ và giới hạn xác nhận

Trong **dự án A**, với tất cả tệp Java đã mô tả và Gradle wrapper:

~~~bash
./gradlew test --tests "com.example.slicedemo.ProductControllerTest"
./gradlew test --tests "com.example.slicedemo.InvoicePayloadJsonTest"
./gradlew test --tests "com.example.slicedemo.InventoryItemRepositoryTest"
./gradlew test --tests "com.example.slicedemo.ArithmeticJdbcTest"
~~~

Trong **dự án B** (starter WebFlux, không có starter MVC):

~~~bash
./gradlew test --tests "com.example.fluxdemo.StatusControllerTest"
~~~

Trên Windows dùng `.\gradlew.bat` thay `./gradlew`. Các test bên trên không gọi `System.out.println`, vì vậy **không có stdout cố định từ mã ứng dụng** để chép lại. Kết quả hiển thị của Gradle/JUnit còn phụ thuộc phiên bản, logging và môi trường.

Những test này cần classpath Spring Boot/JUnit/Mockito/H2/Jackson như đã mô tả; không thể chạy tệp test bằng `javac` thuần thiếu các thư viện đó.

Nếu một ví dụ không khởi động được, kiểm tra theo thứ tự: dependency/version → package của `@SpringBootApplication` → annotation slice đúng stack → bean thật được scan hay mock được override → cấu hình datasource/reactive server → log startup root cause. Không sửa assertion chỉ để làm test xanh khi chưa hiểu lỗi.

## 14. Checklist quyết định annotation trước khi viết test

- [ ] Đã ghi rõ **hành vi cần chứng minh** (HTTP, JSON, persistence hoặc full workflow)?
- [ ] Đã xác định **Spring MVC hay Spring WebFlux**, không chọn chỉ vì thích API reactive?
- [ ] Với MVC: test `@WebMvcTest` dùng `MockMvc`, controller thật, collaborator thích hợp được mock/import.
- [ ] Với WebFlux: `@WebFluxTest` dùng `WebTestClient` và kiểm tra response của publisher reactive.
- [ ] Với JSON: `@JsonTest` kiểm tra cả chiều serialize và deserialize khi đó là hợp đồng.
- [ ] Với data: chọn **JPA/JDBC/R2DBC/MongoDB** theo stack thực, không đánh đồng chúng.
- [ ] Đã kiểm tra điều kiện datasource/H2/Testcontainers và chính sách cleanup/rollback?
- [ ] Không dùng `@Mock` để thay Spring bean; nếu cần override trong context dùng `@MockitoBean` tương ứng với phiên bản.
- [ ] Không gắn nhiều `@...Test` slice trên cùng lớp.
- [ ] Test không quét bean rộng hơn cần thiết; chỉ import cấu hình cụ thể.
- [ ] Nếu có security, đã mô tả và kiểm tra đúng filter, auth và CSRF?
- [ ] Nếu mục tiêu thực sự gồm nhiều tầng, đã bổ sung `@SpringBootTest` phù hợp?
- [ ] Ví dụ/lệnh chạy phù hợp Java, Spring Boot và phiên bản dependency đã chọn?

**Kết luận:** Không có annotation slice “tốt nhất” cho mọi test. **`@WebMvcTest` kiểm tra MVC boundary; `@WebFluxTest` kiểm tra reactive web boundary; `@JsonTest` kiểm tra JSON contract; các data slice kiểm tra tầng lưu trữ theo technology thực tế.** Chọn đúng boundary trước, giữ các collaborator nằm ngoài boundary được thay thế/thiết lập rõ ràng, và chỉ dùng `@SpringBootTest` khi cần chứng minh sự tích hợp giữa các tầng.

### Tài liệu tham khảo

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — Test Auto-configuration Annotations](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html)
- [Spring Framework — @MockitoBean và @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Spring Framework — Spring MVC Test Framework](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html)
- [Spring Framework — Testing WebFlux](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)