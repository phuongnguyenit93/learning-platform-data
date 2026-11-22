# @AutoConfigureMockMvc với context đầy đủ

## 1. Mục tiêu: chạy Spring MVC gần với ứng dụng thật, nhưng không mở HTTP server

Khi kiểm thử một API Spring Boot, ta không chỉ muốn biết phương thức trong controller trả về gì. Nhiều lỗi chỉ xuất hiện khi request thật đi qua **request mapping, chuyển đổi JSON, validation, các servlet filter, xử lý exception, service và repository**. Với ứng dụng sử dụng Spring MVC (Servlet stack), kết hợp:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class ProductApiTest {
    // Các bài kiểm thử với MockMvc.
}
```

cho phép nạp **application context đầy đủ của Spring Boot**, đồng thời tự cấu hình một bean `MockMvc` để gửi request **trong tiến trình test**. `MockMvc` sử dụng mock request/response của Servlet API và cơ chế xử lý của Spring MVC, **không mở cổng mạng hoặc khởi động embedded HTTP server**.

Đó là điểm cần hiểu chính xác: **context đầy đủ ≠ HTTP server thật**. Bộ test có thể dùng controller/service/repository thật nhưng vẫn không kiểm tra socket, TLS, proxy, HTTP/2, container/network behavior hay toàn bộ đặc điểm triển khai production.

Sau bài này, bạn có thể:

- Phân biệt `@SpringBootTest + @AutoConfigureMockMvc` với `@WebMvcTest`, `MockMvcBuilders.standaloneSetup(...)` và kiểm thử `RANDOM_PORT`.
- Thiết lập một test Spring MVC dùng **real application beans** theo kiến trúc controller → service → repository.
- Kiểm tra status, JSON body, content type, lỗi 404, request validation và lỗi malformed JSON bằng JUnit Jupiter.
- Hiểu `addFilters`, Spring Security, CSRF, `@ActiveProfiles`, bean mocking, transaction và context cache.
- Đọc đúng import/dependency theo Spring Boot 3.x và Spring Boot 4.x; khắc phục các lỗi IDE/CLI/CI thường gặp.

**Ngữ cảnh:** Spring Boot Testing, Java 17+, JUnit Jupiter. Ví dụ có thể chạy độc lập trong **một dự án Spring Boot 3.x Servlet MVC** với các dependency đã nêu; không có database, Docker, mạng hay Spring Security trong sample cơ bản. Các ví dụ cho Boot 4.x được đánh dấu riêng, vì package/module đã thay đổi.

## 2. Cơ chế thực thi và trách nhiệm từng annotation

### 2.1. `@SpringBootTest`: nạp cấu hình ứng dụng

`@SpringBootTest` khởi tạo Spring Boot ApplicationContext theo cấu hình ứng dụng, thay vì chỉ nạp một “lát cắt” MVC. Trong application thông thường có `@SpringBootApplication`, điều đó bao gồm component scan và auto-configuration áp dụng cho các dependency hiện có.

Ví dụ context có thể chứa:

- `@RestController` / `@ControllerAdvice`;
- `@Service`, `@Repository` và dependency của chúng;
- `@ConfigurationProperties`, bean cấu hình, MVC converters, validator;
- Security filter chain nếu Spring Security được kích hoạt;
- DataSource/JPA/migrations/client kết nối ngoài nếu application configuration yêu cầu.

**“Đầy đủ” phải hiểu trong phạm vi cấu hình test thực sự được nạp.** Profile test, `properties`, exclusions, conditional beans và mock override có thể khiến context khác production. `@SpringBootTest` không tự tải những integration phụ thuộc không nằm trong classpath hoặc đã được vô hiệu hóa.

Khi dùng `WebEnvironment.MOCK` trên Servlet MVC:

- Tạo web application context với mock servlet environment.
- **Không** khởi động embedded Tomcat/Jetty/Undertow để lắng nghe HTTP.
- Cho phép kiểm tra các bean thật trong context.
- Không cần lấy `@LocalServerPort` vì không có real listening port.

`MOCK` là mặc định của `@SpringBootTest`, nhưng ghi tường minh trong bài học hoặc integration test có thể làm ý định rõ hơn. Nếu không có Servlet MVC trên classpath, cách Boot phát hiện web application type sẽ khác; đừng áp dụng `MockMvc` cho ứng dụng chỉ dùng WebFlux mà chưa kiểm tra cấu hình.

### 2.2. `@AutoConfigureMockMvc`: tạo MockMvc theo context

Annotation này **không thay thế** `@SpringBootTest` và không tự biến test thành `@WebMvcTest`. Nó bổ sung auto-configuration cho `MockMvc` dựa trên web application context đang được test.

Trong một bài test tiêu chuẩn:

```java
@Autowired
MockMvc mockMvc;
```

là đủ để thực hiện request. Không cần tự viết `MockMvcBuilders.standaloneSetup(controller)`, vì như vậy bạn có thể vô tình bỏ qua controller advice, filter, message converter hoặc cấu hình MVC của application context thật.

Đường xử lý khái niệm:

```text
JUnit Jupiter
   │
   ├── Spring TestContext → khởi tạo / dùng cached ApplicationContext
   │     ├── Spring MVC infrastructure và DispatcherServlet
   │     ├── Controller + ControllerAdvice
   │     ├── Service thật + Repository thật (nếu có)
   │     └── Filter, Converter, Validator, Security ... theo cấu hình
   │
   └── MockMvc.perform(mock request)
         → [Servlet Filter chain nếu được đăng ký]
         → DispatcherServlet → HandlerMapping
         → Controller → Service → Repository
         → HttpMessageConverter / ExceptionResolver
         → mock HTTP response
         → andExpect(...) để assert
```

**Không có network hop** trong sơ đồ này. Request được xử lý ngay trong JVM test và response là `MockHttpServletResponse`.

### 2.3. Không nhầm “MockMvc” với “mọi bean đã mock”

Từ `Mock` trong tên **MockMvc** chỉ nói mock **Servlet API request/response**, không có nghĩa `@Service` hay `@Repository` tự động là Mockito mock. Khi kết hợp `@SpringBootTest` với `@AutoConfigureMockMvc`, các service/repository thật có thể chạy nếu bạn không chủ động thay thế chúng.

Khi service cần database thật, test có thể chạy SQL thật; khi bean khởi động gọi API ngoài, test cũng có thể gây I/O thật nếu không cách ly. Đó vừa là ưu điểm kiểm tra phối hợp nhiều lớp, vừa là trách nhiệm setup fixture.

## 3. Chọn đúng loại kiểm thử: bảng so sánh

| Cách làm | Context / hạ tầng | Phù hợp với mục tiêu |
|---|---|---|
| Unit test controller gọi method trực tiếp | Không Spring MVC pipeline | Logic rất nhỏ trong method, nhanh nhất |
| `MockMvcBuilders.standaloneSetup(controller)` | Mock MVC cấu hình thủ công cho controller | Mapping/binding/exception behavior có kiểm soát, không load cả Spring |
| `@WebMvcTest(Controller.class)` | **MVC slice**; giới hạn component scan và auto-configuration | Test web layer nhanh, các dependency ngoài MVC thường mock/import |
| **`@SpringBootTest + @AutoConfigureMockMvc`** | **ApplicationContext đầy đủ** + mock Servlet, không real server | Integration từ HTTP contract qua MVC, service và bean thật |
| `@SpringBootTest(webEnvironment = RANDOM_PORT)` | Context đầy đủ **và embedded server thật** | Kiểm tra real HTTP stack, network, port, serialization từ client |
| End-to-end triển khai staging/production-like | Hệ thống triển khai và phụ thuộc ngoài thực | Kiểm tra ingress, TLS, proxy, cloud/network/config ngoài JVM |

**Ưu tiên phương án có phạm vi nhỏ nhất mà vẫn bắt được lỗi bạn muốn tìm.** Không phải mọi controller test đều cần full context; cũng không nên chỉ dùng `@WebMvcTest` nếu lỗi đang nằm ở cách service và repository phối hợp.

### 3.1. Vì sao `@WebMvcTest` và full context khác nhau?

`@WebMvcTest` chỉ nạp những component liên quan MVC, ví dụ controller, controller advice, filter, converter và các loại MVC infrastructure được annotation hỗ trợ. Service/repository thông thường **không được scan tự động như full application**. Người viết thường cung cấp dependency của controller bằng mock/test configuration.

Trong khi đó, `@SpringBootTest` khởi tạo toàn bộ application configuration. Nếu service thật có JPA repository, migrations hay một bean external client, chúng có thể được khởi tạo. Điều này làm test có độ bao phủ tích hợp cao hơn nhưng cũng chậm hơn hoặc khó cô lập hơn.

**Lưu ý:** `@WebMvcTest` đã tự cấu hình MockMvc. Việc thêm `@AutoConfigureMockMvc` vào `@WebMvcTest` không biến slice đó thành full context. Chỉ khi dùng `@SpringBootTest` (và không cấu hình giới hạn context theo cách khác) bạn mới có mô hình full application mà bài này hướng đến.

### 3.2. Vì sao `RANDOM_PORT` không cần MockMvc để test HTTP thật?

Với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, Spring Boot mở embedded HTTP server trên cổng ngẫu nhiên. Bạn có thể dùng `TestRestTemplate`, `WebTestClient` hoặc client phù hợp để gửi request qua socket thật.

Ngược lại, `MockMvc.perform(...)` **không gửi HTTP tới server đó**; nó chạy qua mock Servlet pipeline. Nếu bài test dùng RANDOM_PORT nhưng vẫn chỉ gọi MockMvc, bạn chưa kiểm thử network hop. Tránh nhầm một bài in-process integration test với real HTTP integration test.

## 4. Version và dependency: xác định trước khi sao chép code

### 4.1. Spring Boot 3.x

Trong Boot 3.x, import phổ biến:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
```

Một dự án **Spring Boot 3.x, Java 17+** với REST MVC, JSON và Bean Validation thường cần các dependency sau:

**Gradle Groovy DSL — phần liên quan trong `build.gradle`:**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Maven — phần liên quan trong `pom.xml`:**

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Các đoạn này **không phải build file độc lập**: build thực tế cần Boot plugin/parent/BOM, repositories, compiler/toolchain và Surefire/JUnit Platform phù hợp. Không khai báo dependency trùng nếu dự án đã có. Boot 3.x dùng Jakarta namespace, ví dụ `jakarta.validation.Valid` và `jakarta.validation.constraints.Min`.

**Vì sao thêm validation starter?** Từ các nhánh Spring Boot hiện đại, không nên mặc định web starter đã bao gồm implementation Bean Validation. Ví dụ ở phần 5 có `@Valid` + `@Min` và kỳ vọng HTTP 400 cho đầu vào không hợp lệ; cần một Bean Validation provider hoạt động, thường do `spring-boot-starter-validation` đưa vào.

### 4.2. Spring Boot 4.x thay đổi package và module

Ở **Spring Boot 4.x**, package của annotation tương ứng đã được tổ chức trong module MVC test:

```java
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
```

Các starter theo kiến trúc modular gồm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-webmvc-test'
}
```

Đây là **snippet định hướng cho dự án Boot 4.x**, không phải hướng dẫn thay package trong dự án 3.x. Boot 4 cũng có các thay đổi Java, testing libraries, JSON và module khác; hãy kiểm tra dependency BOM, API/JUnit và tài liệu phiên bản dự án trước khi chuyển toàn bộ code.

**Quan trọng:** thấy lỗi `Cannot resolve symbol AutoConfigureMockMvc` không có nghĩa annotation bị xóa. Trước tiên xác minh chính xác Boot major version và import đúng package, sau đó kiểm tra test dependency đã resolve. Không ghép module Boot 4 với Boot 3 theo cách tự phát.

### 4.3. Một số option của annotation

Trên Boot 3.x, `@AutoConfigureMockMvc` hỗ trợ các tùy chọn thường dùng:

- `addFilters = true` (**mặc định**): đưa những Servlet Filter từ application context vào MockMvc.
- `addFilters = false`: bỏ bước thêm filters từ context vào MockMvc; không nên dùng như cách “sửa” 401/403 nếu security là mục tiêu kiểm thử.
- `print` và `printOnlyOnFailure`: điều khiển việc in request/response diagnostic theo cấu hình và test outcome.
- Các tích hợp HtmlUnit/Selenium được bật khi có dependency phù hợp, tùy phiên bản và option hỗ trợ.

Sang Boot 4.x, các option HtmlUnit/WebDriver được sắp xếp khác; không mặc định mọi attribute ở Boot 3 vẫn tồn tại nguyên tên. Các thuộc tính `addFilters`, `print` và `printOnlyOnFailure` vẫn có trong tài liệu annotation Boot 4.

## 5. Ví dụ hoàn chỉnh: GET/POST qua controller, service và repository thật

Chúng ta xây một REST API nhỏ không phụ thuộc database ngoài, để chứng minh full context chạy bean thật. Repository giữ **bảng giá bất biến** trong bộ nhớ; không có test nào sửa dữ liệu dùng chung.

Các endpoint:

- `GET /api/products/BOOK` → JSON thông tin sản phẩm.
- `GET /api/products/UNKNOWN` → HTTP 404.
- `POST /api/products/BOOK/quotes` với body JSON `{"quantity":3}` → HTTP 201, total = 3600.
- POST số lượng 0 → HTTP 400 do Bean Validation.
- POST body JSON hỏng → HTTP 400 do message conversion.

Chọn **Java 17+ / Spring Boot 3.x** như phần 4.1. Không thêm Spring Security cho ví dụ chính; nếu ứng dụng đang học đã có security starter, hãy xem phần 8 trước khi chạy các request dự kiến trả 200/201.

### 5.1. Cấu trúc file

```text
project/
├── build.gradle                   # hoặc pom.xml
└── src/
    ├── main/java/com/example/fullmvc/
    │   ├── FullMvcApplication.java
    │   ├── ProductRepository.java
    │   ├── ProductService.java
    │   └── ProductController.java
    └── test/java/com/example/fullmvc/
        └── ProductApiIntegrationTest.java
```

App class được đặt trong package gốc `com.example.fullmvc`. Các class còn lại cùng package nên nằm trong vùng component scan mặc định của `@SpringBootApplication`.

### 5.2. Application entry point

**File `src/main/java/com/example/fullmvc/FullMvcApplication.java`:**

```java
package com.example.fullmvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FullMvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(FullMvcApplication.class, args);
    }
}
```

Không cần tạo servlet hoặc `MockMvc` thủ công trong production code. Spring Boot cấu hình MVC dựa trên classpath; `MockMvc` là công cụ test.

### 5.3. Repository thật với dữ liệu không thay đổi

**File `src/main/java/com/example/fullmvc/ProductRepository.java`:**

```java
package com.example.fullmvc;

import java.util.Map;
import java.util.Optional;

import org.springframework.stereotype.Repository;

@Repository
public class ProductRepository {
    private final Map<String, Long> prices = Map.of(
            "BOOK", 1200L,
            "PEN", 500L
    );

    public Optional<Long> findUnitPrice(String sku) {
        return Optional.ofNullable(prices.get(sku));
    }
}
```

Đây là một bean `@Repository` thật. Nó không dùng Mockito và không cần database. `Map.of(...)` không cho sửa cấu trúc, giúp test không ảnh hưởng nhau vì dữ liệu dùng chung không bị mutate. Nếu thay repository bằng JPA thật, bạn phải chuẩn bị database và fixture theo phần 9.

### 5.4. Service thật thực thi quy tắc nghiệp vụ

**File `src/main/java/com/example/fullmvc/ProductService.java`:**

```java
package com.example.fullmvc;

import java.util.Optional;

import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Optional<ProductView> find(String sku) {
        return repository.findUnitPrice(sku)
                .map(price -> new ProductView(sku, price));
    }

    public Optional<QuoteView> quote(String sku, int quantity) {
        return repository.findUnitPrice(sku)
                .map(price -> new QuoteView(
                        sku,
                        quantity,
                        Math.multiplyExact(price, (long) quantity)
                ));
    }

    public record ProductView(String sku, long unitPrice) {}

    public record QuoteView(
            String sku,
            int quantity,
            long total
    ) {}
}
```

Service không biết HTTP status, JSON hay `MockMvc`. Nó dùng dependency thật thông qua constructor và trả các Java record. `Math.multiplyExact` bảo vệ phép nhân khỏi overflow, nhưng ví dụ không cần test nhánh overflow; hãy thêm case tương ứng nếu đó là hợp đồng nghiệp vụ của dự án.

### 5.5. Controller thật và validation

**File `src/main/java/com/example/fullmvc/ProductController.java`:**

```java
package com.example.fullmvc;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/products")
public class ProductController {
    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/{sku}")
    public ProductService.ProductView get(
            @PathVariable String sku
    ) {
        return service.find(sku).orElseThrow(() ->
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Product not found"));
    }

    @PostMapping("/{sku}/quotes")
    @ResponseStatus(HttpStatus.CREATED)
    public ProductService.QuoteView quote(
            @PathVariable String sku,
            @Valid @RequestBody QuoteRequest request
    ) {
        return service.quote(sku, request.quantity())
                .orElseThrow(() ->
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND,
                                "Product not found"));
    }

    public record QuoteRequest(@Min(1) int quantity) {}
}
```

Giải thích các lớp trách nhiệm:

- `@GetMapping`/`@PostMapping` tạo route.
- `@PathVariable` nhận SKU từ đường dẫn.
- `@RequestBody` kết hợp JSON converter để deserialize request thành record.
- `@Valid` yêu cầu validation; `@Min(1)` cấm số lượng bằng 0 hoặc âm.
- `@ResponseStatus(CREATED)` đặt HTTP 201 khi tạo quote thành công.
- `ResponseStatusException(NOT_FOUND)` được MVC exception resolver xử lý thành 404.
- Object response được serialise thành JSON bởi converter phù hợp có trên classpath.

Controller nhận **service thật** qua constructor; service nhận **repository thật**. Không có fake hoặc mock dependency trong source này.

### 5.6. JUnit Jupiter integration test dùng MockMvc

**File `src/test/java/com/example/fullmvc/ProductApiIntegrationTest.java`:**

```java
package com.example.fullmvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        classes = FullMvcApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
class ProductApiIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ApplicationContext context;

    @Autowired
    ProductService service;

    @Autowired
    ProductRepository repository;

    @Test
    void loadsControllerServiceAndRepositoryFromFullContext() {
        assertThat(context.getBean(ProductController.class))
                .isNotNull();
        assertThat(context.getBean(ProductService.class))
                .isSameAs(service);
        assertThat(context.getBean(ProductRepository.class))
                .isSameAs(repository);
    }

    @Test
    void getProductReturnsJsonThroughRealComponents()
            throws Exception {
        mvc.perform(get("/api/products/BOOK")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.sku").value("BOOK"))
                .andExpect(jsonPath("$.unitPrice").value(1200));
    }

    @Test
    void unknownProductReturnsNotFound()
            throws Exception {
        mvc.perform(get("/api/products/UNKNOWN"))
                .andExpect(status().isNotFound());
    }

    @Test
    void validQuoteReturnsCreatedAndCalculatedTotal()
            throws Exception {
        mvc.perform(post("/api/products/BOOK/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"quantity\":3}"))
                .andExpect(status().isCreated())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.sku").value("BOOK"))
                .andExpect(jsonPath("$.quantity").value(3))
                .andExpect(jsonPath("$.total").value(3600));
    }

    @Test
    void nonPositiveQuantityFailsBeanValidation()
            throws Exception {
        mvc.perform(post("/api/products/BOOK/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"quantity\":0}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void malformedJsonIsRejectedByMessageConverter()
            throws Exception {
        mvc.perform(post("/api/products/BOOK/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{"))
                .andExpect(status().isBadRequest());
    }
}
```

Bộ test có **6 phương thức `@Test`**, không cần `@ExtendWith(SpringExtension.class)` riêng vì `@SpringBootTest` đã tích hợp Spring TestContext với JUnit Jupiter trong cấu hình hỗ trợ.

**Kỳ vọng:** trong dự án Spring Boot 3.x sạch với dependencies nêu trên và không có cấu hình bảo mật hoặc backend ngoài khác, cả **6 test pass**. Code không chủ động ghi stdout. Không chốt một dòng log cụ thể vì Gradle, Maven và IDE có định dạng report khác nhau.

### 5.7. Chạy bằng Gradle/Maven Wrapper

Linux/macOS:

```bash
# Dùng nếu dự án chạy Gradle:
./gradlew test --tests "com.example.fullmvc.ProductApiIntegrationTest"

# Hoặc nếu dự án chạy Maven:
./mvnw -Dtest=ProductApiIntegrationTest test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.fullmvc.ProductApiIntegrationTest"

# Hoặc Maven:
.\mvnw.cmd "-Dtest=ProductApiIntegrationTest" test
```

Chỉ chạy **một** nhóm lệnh tương ứng build tool của dự án. Với Maven multi-module hoặc Gradle multi-project, chọn đúng module và test task/goal. Nếu application context được cache, lần chạy thứ hai có thể nhanh hơn nhưng bạn vẫn cần xem test report để chắc chắn đã khám phá và thực thi đủ sáu phương thức.

## 6. Đọc từng lớp trong request pipeline từ ví dụ

### 6.1. GET sản phẩm hợp lệ

Lệnh:

```java
mvc.perform(get("/api/products/BOOK"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.unitPrice").value(1200));
```

là **đoạn trích** từ test hoàn chỉnh.

Chuỗi hoạt động:

1. MockMvc tạo một mock Servlet request với method GET và đường dẫn được cung cấp.
2. Spring MVC tìm handler cho `/api/products/{sku}`.
3. Path variable `BOOK` được bind vào tham số `sku`.
4. Controller gọi `ProductService.find("BOOK")`.
5. Service gọi repository thật, tìm giá `1200L`.
6. Spring MVC chuyển record `ProductView("BOOK", 1200L)` thành JSON.
7. `andExpect` xác minh status và payload.

Nếu trong production bạn sửa tên route, bỏ bean service, thay converter hoặc đổi kiểu response, test có thể phát hiện lỗi phối hợp này — điều mà unit test chỉ gọi `controller.get("BOOK")` có thể bỏ sót.

### 6.2. POST quote hợp lệ

Request có header `Content-Type: application/json` và JSON `{"quantity":3}`. RequestBody converter tạo `QuoteRequest(3)`; Bean Validation chấp nhận giá trị; service nhân `1200 × 3 = 3600`; response status là 201.

Test chứng minh **nhiều lớp cùng hoạt động**: route POST, JSON deserialization, annotation-based validation, service calculation, repository lookup, JSON serialization và HTTP status.

**Chú ý:** mã có `@ResponseStatus(CREATED)` chỉ định “201” cho ví dụ quote; một API ngoài đời có thể dùng 200 nếu quote chỉ là phép tính không tạo resource. Hãy chọn status theo API contract dự án; không gắn 201 cho mọi POST chỉ vì đó là POST.

### 6.3. Request invalid và malformed JSON

Hai test đều kỳ vọng 400 nhưng vì **hai nguyên nhân khác nhau**:

- `{"quantity":0}` là JSON hợp lệ, deserialize được, nhưng vi phạm `@Min(1)`. Spring MVC xử lý lỗi validation.
- `"{"` là JSON cú pháp sai, request không deserialize thành object được; message converter dẫn đến lỗi request body, thường là `HttpMessageNotReadableException`.

Khi debug 400, xem *resolved exception* và binding/validation errors thay vì mặc định mọi 400 do `@Valid`. Có thể lấy `MvcResult` để điều tra:

```java
var result = mvc.perform(post("/api/products/BOOK/quotes")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"quantity\":0}"))
        .andExpect(status().isBadRequest())
        .andReturn();

assertThat(result.getResolvedException()).isNotNull();
```

Đoạn này **chỉ là minh họa trong test đã có `mvc` và imports cần thiết**; không yêu cầu tất cả API trả body lỗi cùng định dạng, vì Spring Boot có thể dùng cấu hình ErrorAttributes/ProblemDetail/controller advice khác nhau.

### 6.4. GET không tồn tại và 404

Với SKU không nằm trong map, repository trả `Optional.empty()`; service trả empty; controller ném `ResponseStatusException(HttpStatus.NOT_FOUND, ...)` và MVC resolver biến nó thành HTTP 404.

Test nên assert 404 ở **ranh giới API**, không chỉ assert repository trả empty. Như vậy nếu controller vô tình đổi thành 200 với body null, test sẽ bắt được sai lệch hợp đồng.

## 7. Bật/tắt Servlet filters: `addFilters` ảnh hưởng điều gì?

Mặc định của `@AutoConfigureMockMvc` là `addFilters = true`. Các `Filter` từ context được đăng ký với MockMvc, điều này quan trọng khi request phải đi qua:

- Spring Security filter chain;
- CORS hoặc filter xử lý correlation/request ID;
- Filter logging, locale, encoding, tenant, tracing;
- Filter tự định nghĩa của dự án.

Nếu bạn viết:

```java
@AutoConfigureMockMvc(addFilters = false)
```

thì bạn chủ động yêu cầu **không đăng ký các filters từ ApplicationContext vào MockMvc theo cơ chế auto-configuration**. Điều này có thể hữu ích để cô lập vấn đề routing khi debug, nhưng test lúc đó **không còn chứng minh behavior của các filters bị bỏ qua**.

### 7.1. Vì sao `addFilters=false` có thể làm test “xanh giả”?

Giả sử endpoint yêu cầu authentication và CSRF. Một request POST không đăng nhập, không CSRF token đáng lẽ bị chặn. Nếu loại filters, request có thể đến controller và trả 201; test xanh nhưng luồng security thật đang bị bỏ qua.

**Nguyên tắc:** nếu test có mục tiêu kiểm tra hành vi ứng dụng với bảo mật, hãy **giữ filters** và tạo authenticated test user/token bằng cơ chế Spring Security Test. Chỉ vô hiệu hóa filter khi phạm vi test đã được xác định rõ và được kiểm chứng bảo mật ở test khác.

### 7.2. Spring Security có mặt thì status thay đổi

Khi thêm `spring-boot-starter-security` mà chưa có cấu hình override phù hợp, endpoint có thể bị bảo vệ bởi Spring Security auto-configuration:

- Request GET không có thông tin xác thực có thể nhận 401 hoặc redirect/403 tùy authentication entry point và client headers.
- Request POST thiếu CSRF token có thể bị 403 **trước khi** controller hoặc Bean Validation chạy.
- Vì vậy test POST `{"quantity":0}` có thể nhận 403, không phải 400. Đó không tự động là lỗi validation; filter chain đã chặn request từ đầu.

Khi test endpoint yêu cầu authenticated user, Spring Security Test hỗ trợ `@WithMockUser` hoặc request post-processor như `user(...)`. Khi CSRF được bật, thêm `with(csrf())` cho unsafe methods như POST.

**Snippet cho dự án đã thêm `spring-security-test`, không thuộc ví dụ runnable ở phần 5:**

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;

// Đoạn bên trong một test đã có MockMvc:
mvc.perform(post("/api/products/BOOK/quotes")
        .with(user("alice").roles("USER"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"quantity\":3}"))
        .andExpect(status().isCreated());
```

Đoạn chỉ pass nếu security policy của ứng dụng cho phép role đó gọi endpoint và các config khác hợp lệ. Không coi user giả trong test là xác thực production; test cần thêm case bị từ chối (401/403) để bảo đảm access rules.

**Phân biệt:** `@WithMockUser` và `with(csrf())` phục vụ hai điều kiện khác nhau. Có authenticated user chưa chắc đã vượt CSRF nếu chính sách đang bật.

## 8. Context đầy đủ nhưng vẫn có thể cô lập dependency ngoài

Bài test phần 5 không có DB/network. Trong ứng dụng thật, nạp full context có thể làm một số bean cần:

- DataSource, migrations, Hibernate EntityManager;
- Kafka/RabbitMQ broker, S3 hoặc REST client;
- Redis, OpenSearch, email gateway;
- OAuth/OIDC discovery, secrets hoặc configuration server;
- Schedulers, runners hoặc startup listeners.

**Không nên vô hiệu hóa mọi bean một cách mù quáng để context vừa đủ khởi động.** Thay vào đó, xác định integration boundary của test:

1. Nếu muốn kiểm chứng **controller + service + repository + database**, dùng database test phù hợp, ví dụ Testcontainers, migration/seed/cleanup rõ và transaction phù hợp.
2. Nếu muốn kiểm chứng **controller + service thật nhưng không gửi API bên ngoài**, có thể override bean external gateway bằng mock/fake; các tầng nghiệp vụ trong phạm vi vẫn chạy thật.
3. Nếu chỉ muốn kiểm chứng **mapping/serialization/validation của controller**, `@WebMvcTest` với mock dependency thường nhẹ và rõ hơn.

### 8.1. `@MockitoBean`, `@MockBean` và version

Trong Spring Framework **6.2+** (thường với Spring Boot 3.4+), test bean overriding có `@MockitoBean`. Các dự án Boot 3.3.x trở xuống thường dùng `@MockBean` của Spring Boot; annotation Boot cũ bị deprecate ở các nhánh mới.

**Snippet chỉ minh họa kiểu override trong dự án Spring Framework có hỗ trợ, không chạy độc lập:**

```java
@MockitoBean
RemotePriceGateway remotePriceGateway;
```

Nếu `RemotePriceGateway` là bean thật của application, annotation thay hoặc tạo bean mock theo quy tắc của framework và cách khai báo. Sau đó cấu hình mock trong test bằng Mockito để kiểm soát phản hồi. Bạn phải **đặt import đúng phiên bản** và bảo đảm service đang nhận chính bean override đó.

Không dùng `@Mock` từ Mockito thay cho `@MockitoBean` rồi kỳ vọng Spring tự inject object đó vào controller/service; `@Mock` riêng lẻ chỉ tạo một mock trong lớp test, không tự thay singleton bean bên trong ApplicationContext.

### 8.2. Test profile và cấu hình theo môi trường

Dùng `@ActiveProfiles("test")` và `src/test/resources/application-test.properties` khi cần cấu hình test khác production. Có thể dùng `@SpringBootTest(properties = "...")` cho một vài override đơn giản.

Ví dụ:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK,
    properties = {
        "app.external-notifications.enabled=false",
        "app.jobs.auto-start=false"
    }
)
@AutoConfigureMockMvc
@ActiveProfiles("test")
class FullContextApiTest {
}
```

Đây là snippet, chỉ có ý nghĩa nếu ứng dụng thật sự có những property đó và bean được thiết kế tôn trọng chúng. Spring Boot không tự hiểu `app.external-notifications.enabled` hay `app.jobs.auto-start` vì đó là tên giả định của ứng dụng.

### 8.3. Không tự coi full context test là end-to-end

Ngay cả khi mock gateway ngoài và dùng DB test thật, request vẫn đi qua mock Servlet API. Nếu bug chỉ xuất hiện ở reverse proxy header, TLS handshake, HTTP connection reuse, server port hoặc server container, MockMvc không phải công cụ xác nhận đầy đủ. Dùng thêm test `RANDOM_PORT` hoặc environment triển khai thích hợp.

## 9. Transaction, dữ liệu và tính độc lập của test

### 9.1. `@Transactional` ở test class làm gì?

Khi test method chạy trong transaction do Spring TestContext mở, thường Spring sẽ **rollback transaction đó sau mỗi test** theo mặc định. Trong mô hình `MOCK`, xử lý servlet request đồng bộ thường ở **cùng thread** với test và có thể tham gia transaction test nếu transaction manager/propagation phù hợp.

Nhưng rollback **không áp dụng thần kỳ lên mọi side effect**:

- Transaction của test không bao phủ HTTP call tới server thật ở thread khác.
- Transaction/async work tách thread có ngữ cảnh giao dịch riêng.
- Database code dùng propagation `REQUIRES_NEW` có thể commit độc lập.
- Message publish, file write, external email hay cache có thể không rollback.
- Repository trong ví dụ dùng `Map.of(...)`, nên **không có database transaction** để rollback.

Với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, client và server xử lý qua các thread khác nhau, nên transaction bắt đầu tại test method **không tự rollback giao dịch của request phía server**. Đây là khác biệt quan trọng khi chuyển test từ MockMvc sang real HTTP.

### 9.2. Chiến lược fixture phù hợp

- Dữ liệu bất biến như map ở ví dụ: không cần cleanup.
- JPA database: seed có chủ đích, cleanup/rollback theo kiến trúc thật; tránh dùng trạng thái từ test khác.
- Test thay bảng giá/clock/cache: reset state trong teardown hoặc tạo bean fixture mới theo phạm vi.
- Test có scheduler: khóa/disable job ngoài phạm vi để không tạo race với assertion.
- Test với Testcontainers: dùng container schema/fixture tách biệt và tránh phụ thuộc port cố định.

**Không dùng `@DirtiesContext` như cách mặc định làm sạch mọi database.** Nó đánh dấu Spring context không thể tái sử dụng trong cache và tốn startup; không bảo đảm dữ liệu nằm ngoài context được reset. Hãy thiết kế cleanup đúng tài nguyên.

## 10. Context cache, hiệu năng và phạm vi kiểm thử

Full context thường khởi động đắt hơn một MVC slice vì phải tạo nhiều bean. Spring TestContext cache context theo key dựa trên cấu hình, profile, test properties, bean override và các customizers liên quan.

Khi nhiều class test có cùng context configuration, chúng có thể tái sử dụng context. Điều này giúp suite chạy nhanh nhưng cũng nhắc bạn **không mutate singleton state bừa bãi**. Một service hoặc repository in-memory mutable dùng chung có thể làm test sau gặp dữ liệu không còn như kỳ vọng.

Các nguyên tắc:

- Tránh khai báo nhiều biến thể annotation/property không cần thiết giữa các lớp nếu chúng dùng cùng một hệ thống.
- Ưu tiên test unit/slice cho các trường hợp không đòi full context.
- Tránh mở Spring context chỉ để kiểm tra phép tính thuần Java.
- Chỉ dùng `@DirtiesContext` khi test thực sự làm hỏng state của context không thể reset.
- Với nested/parameterized tests, giữ fixture riêng và biết khi nào context được tái sử dụng.
- Đừng suy luận thời gian chạy ngắn nghĩa là test đã chạy; Gradle còn có up-to-date/task cache.

## 11. Đọc response và tăng chất lượng assertion

### 11.1. Status là cần thiết nhưng chưa đủ

Ví dụ này **quá yếu**:

```java
mvc.perform(get("/api/products/BOOK"))
        .andExpect(status().isOk());
```

Status 200 chưa chứng minh JSON đúng. Hãy kiểm tra thêm:

- Content type tương thích `application/json`.
- Tên và kiểu trường quan trọng.
- Giá trị nghiệp vụ do service tính.
- Trường không được lộ (nếu privacy/security là hợp đồng).
- Quy tắc lỗi 4xx/5xx và error body nếu API có schema rõ.

Đoạn đầy đủ ở phần 5 kiểm tra `$.sku` và `$.unitPrice`; trường quote kiểm tra cả SKU, quantity và total. Khi API có nhiều property, chỉ assert những điều thuộc hợp đồng, không khóa test vào serialization detail không quan trọng.

### 11.2. Assert response với `jsonPath`

`jsonPath("$.total").value(3600)` kiểm tra giá trị tại đường JSONPath. Cú pháp này độc lập với việc bean controller đã mock hay là real: nó kiểm tra mock HTTP response. Trong hệ thống có JSON type đặc biệt như `BigDecimal`, timestamp/timezone hoặc enum, phải có assertion tương thích serialization contract.

Tránh so sánh **nguyên JSON string** nếu thứ tự property không là hợp đồng. Có thể dùng JSONPath hoặc content JSON comparison để tránh flaky do thứ tự trường.

### 11.3. Debug với `andDo(print())`

Khi test thất bại và cần xem request/response, có thể dùng:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;

// Trong test:
mvc.perform(get("/api/products/BOOK"))
        .andDo(print())
        .andExpect(status().isOk());
```

Đây là snippet minh họa, không phải file hoàn chỉnh. `print()` có thể đưa headers/body vào log test, vì vậy **không in token, cookie nhạy cảm hoặc dữ liệu cá nhân thật** vào CI artifact. Với `@AutoConfigureMockMvc`, có thể cấu hình `printOnlyOnFailure` theo phiên bản để giảm ồn.

### 11.4. Kiểm tra resolved exception

Khi muốn biết 400/404/500 đến từ đâu, dùng `MvcResult.getResolvedException()`. Với exception đã được resolver xử lý, thuộc tính đó có thể chứa exception tương ứng; với lỗi xảy ra trước khi resolver hoặc thất bại từ test runner, cách biểu hiện có thể khác. Đừng khẳng định mọi lỗi đều nằm trong field này.

## 12. Spring MVC async và filter behavior

Nếu controller trả `Callable`, `DeferredResult`, `CompletableFuture` hoặc một dạng async được MVC hỗ trợ, MockMvc có thể cần **hai pha**: khởi tạo request rồi dispatch kết quả bất đồng bộ.

**Snippet minh họa (giả định endpoint `/api/async` thật sự có xử lý async):**

```java
var mvcResult = mvc.perform(get("/api/async"))
        .andExpect(request().asyncStarted())
        .andReturn();

mvc.perform(asyncDispatch(mvcResult))
        .andExpect(status().isOk());
```

Cần static imports `request` và `asyncDispatch` từ Spring MVC Test. Đây không phải ví dụ runnable độc lập. Không áp dụng `asyncDispatch` cho endpoint đồng bộ trong phần 5.

**Chú ý:** async code chạy ở thread khác có thể không chia sẻ ThreadLocal security/transaction/request context nếu chưa có cơ chế propagation phù hợp. Vì vậy một MockMvc test đồng bộ pass chưa đủ chứng minh async behavior ổn định.

## 13. Các lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân hay gặp | Hướng kiểm tra |
|---|---|---|
| `No qualifying bean of type MockMvc` | Thiếu `@AutoConfigureMockMvc` hoặc không có Servlet MVC test configuration | Kiểm tra annotation, starter, web environment |
| Context báo `Failed to load ApplicationContext` | Thiếu bean, DB, migration, remote client, profile/secret sai | Đọc root cause đầu tiên có ý nghĩa |
| 404 ở endpoint chắc chắn có trong source | Sai package scan, route/prefix, method, active profile hoặc test app class | Kiểm tra `@SpringBootApplication` root và `RequestMapping` |
| GET trả 401/403 thay vì 200 | Spring Security filters đang chạy | Thiết lập auth trong test và policy hợp lệ |
| POST trả 403 thay vì 201/400 | CSRF hoặc security policy chặn trước MVC | Thêm test user/CSRF theo đúng yêu cầu bảo mật |
| POST quantity=0 vẫn trả 201 | Chưa có Bean Validation provider, thiếu `@Valid`, annotation ở sai DTO field | Kiểm tra `spring-boot-starter-validation` và validation configuration |
| JSON body trả 400 trước controller | Malformed JSON, content type sai, converter không đọc được DTO | Kiểm tra request body, MediaType, record/constructor |
| Response có body nhưng assertion JSON fail | Tên field/kiểu dữ liệu/serialization khác expected | Đọc actual response, JSONPath và contract |
| `@Autowired ProductRepository` thất bại | Bean chưa được scan hoặc config conditional loại nó | Kiểm tra package, annotation và các dependency |
| Test riêng pass, full suite fail | Shared mutable singleton, DB fixture hoặc cache/global state bị rò | Cô lập và reset đúng tài nguyên |
| MockMvc thấy route nhưng không thể kết nối qua localhost | MockMvc không mở HTTP server | Dùng RANDOM_PORT khi cần network request |
| MockMvc chạy nhưng security bị bỏ qua | `addFilters=false` hoặc custom MockMvc setup thiếu filter chain | Giữ filters và kiểm chứng access-control tests |
| IDE compile nhưng Gradle/Maven lỗi import | Spring Boot 3 và 4 dùng package test khác nhau | Kiểm tra version/dependency/import tương ứng |
| Test chạy 0 phương thức | JUnit Platform/Surefire/filter sai hoặc task bị skip/cache | Đọc test reports, task options, test count |
| Test chậm bất thường | Full context nạp DB/remote config hoặc bị dirty/cache miss liên tục | Phân nhóm test, tối ưu fixture, dùng slice đúng chỗ |
| Test MockMvc pass, server thật fail | Container/network/proxy/TLS khác mock Servlet | Viết thêm RANDOM_PORT/end-to-end tests |

### 13.1. Quy trình debug theo từng lớp

Khi test fail, không sửa annotation vô hướng. Hãy kiểm tra tuần tự:

1. **Test có được chạy không?** JUnit Jupiter/Surefire/Gradle discovery, số test.
2. **Context có tạo được không?** Nếu không, đọc root cause bean/configuration.
3. **MockMvc có được inject không?** Nếu thiếu, kiểm tra Servlet MVC classpath và `@AutoConfigureMockMvc`.
4. **Filter có chặn trước controller không?** Đặc biệt authentication/CSRF.
5. **Route có match không?** Method, path variable, mapping prefix, content type.
6. **Body parse và validation có pass không?** JSON converter, DTO, `@Valid`.
7. **Service/repository có đúng dữ liệu không?** Fixture, transaction, business logic.
8. **Response serialization và status đúng không?** MVC exception handler, JSONPath.
9. **Có lệch IDE/CLI/CI không?** JDK, resolved dependencies, active profiles, environment, cache và test command.

Một lỗi ở bước 2 (context fail) không thể được sửa bằng cách đổi `jsonPath` ở bước 8. Một 403 do security filter không chứng minh Bean Validation sai.

## 14. Best practices cho dự án Spring Boot thực tế

### 14.1. Tổ chức test theo mục tiêu

Một cấu trúc hợp lý có thể gồm:

- **Unit tests:** tính toán/quy tắc nghiệp vụ, không Spring context.
- **MVC slice tests:** controller advice, mapping, JSON/validation, mock service nếu phù hợp.
- **Full-context MockMvc tests:** một số luồng nghiệp vụ then chốt qua controller → service → repository, filter và transaction.
- **HTTP integration tests:** các luồng cần embedded server/socket hoặc client thực.
- **End-to-end tests:** những thuộc tính môi trường triển khai mà các mức test trước không chứng minh được.

Không cố gộp mọi trường hợp vào full context test; cũng không loại hết integration tests vì unit tests chạy nhanh.

### 14.2. Cấu hình test rõ ràng, không phụ thuộc máy cá nhân

- Dùng Gradle/Maven Wrapper và JDK/toolchain chung với CI.
- Ưu tiên `@ActiveProfiles("test")`/test resources cho environment.
- Không truy cập production DB, queue hoặc email trong test.
- Không in secrets vào `print()` hoặc failure logs.
- Seed/cleanup fixtures theo mỗi test hoặc transaction đã kiểm chứng.
- Không đổi HTTP contract chỉ để làm test xanh trên một máy.
- Ghi rõ framework major version và test starter trong README dự án.

### 14.3. Kiểm chứng điều gì trước khi tạo pull request?

Sau khi chạy một test đơn lẻ, cần chạy bộ test được build/CI công nhận, chẳng hạn `./gradlew test` hoặc `./mvnw test` theo repo. Đọc report để biết test count, skipped tests và lỗi xảy ra ở đâu. Với Gradle, trạng thái `UP-TO-DATE` hoặc `FROM-CACHE` không chứng minh test vừa chạy lại; dùng `--rerun-tasks` khi cần ép xác minh thực thi mới.

Khi module có test task cho integration riêng, cần chạy đúng task/goal đó. Một `@SpringBootTest` vẫn có thể được project cấu hình tách riêng khỏi task `test`; annotation **không tự quyết định** task nào sẽ thực thi class.

## 15. Bài tập ứng dụng

### Bài tập A: Chọn phạm vi test hợp lý

Một controller chỉ cần kiểm tra mapping và JSON field từ service đã được mock. Full-context MockMvc hay `@WebMvcTest`?

**Gợi ý:** `@WebMvcTest` thường thích hợp hơn. Nó kiểm tra MVC behavior mà không nạp hạ tầng ngoài. Nếu lỗi nghi ngờ là việc bean service/repository được wire sai trong ứng dụng thật, thêm một full-context MockMvc test có giá trị.

### Bài tập B: Đọc HTTP 403

Test POST quote gửi JSON hợp lệ nhưng trả 403 khi dự án thêm Spring Security. Cần sửa điều gì?

**Đáp án:** xác định security filter chain và CSRF policy. Nếu endpoint cần authenticated user, cấu hình Spring Security Test với user/roles và CSRF token phù hợp. **Không đặt `addFilters=false` để làm request vượt qua bảo mật rồi kết luận API đã được kiểm chứng.**

### Bài tập C: Validation có chạy không?

Test `POST ... {"quantity":0}` trả HTTP 201. Kiểm tra ít nhất ba điểm?

**Đáp án:** DTO có `@Min(1)` không; method có `@Valid @RequestBody` không; test runtime có Jakarta Bean Validation provider (ví dụ `spring-boot-starter-validation`) không. Sau đó xác nhận đúng endpoint/method đang nhận request và không có custom handler bỏ qua validation.

### Bài tập D: Full context nhưng vẫn không có cổng HTTP

Vì sao `@Autowired MockMvc` hoạt động nhưng `http://localhost:8080/api/products/BOOK` không kết nối?

**Đáp án:** `@SpringBootTest(webEnvironment=MOCK)` không khởi động HTTP server. `MockMvc.perform(get(...))` chạy trong JVM trên mock request/response; muốn thật sự gửi HTTP qua socket, dùng `RANDOM_PORT` và client thích hợp.

### Bài tập E: Kiểm tra xuyên tầng

Trong ví dụ, nếu repository không có `BOOK` hoặc service tính sai total, test nào có thể bắt được?

**Đáp án:** GET thành công kiểm tra dữ liệu repository và JSON; POST quote kiểm tra quy tắc của service và contract response. Nếu muốn bắt lỗi chính xác hơn, viết thêm unit test cho `ProductService.quote(...)` và giữ một số full-context tests kiểm tra wiring/request pipeline.

### Bảng kiểm trước khi kết luận test đạt

- [ ] Version của `@AutoConfigureMockMvc` và starter/import phù hợp Spring Boot.
- [ ] `@SpringBootTest(webEnvironment=MOCK)` thực sự tạo Servlet MVC context.
- [ ] `MockMvc` được inject từ context, không bị thay bằng standalone setup ngoài ý muốn.
- [ ] Controller, service, repository trong phạm vi kiểm thử là bean thật hoặc override được xác định rõ.
- [ ] Request GET/POST kiểm tra status và payload/các field nghiệp vụ.
- [ ] Có test lỗi: not found, invalid body/validation và error handler theo API contract.
- [ ] Filter/Spring Security/CSRF không bị bỏ qua nếu thuộc hợp đồng.
- [ ] Dữ liệu test độc lập, rollback/cleanup phù hợp với thread và side effects.
- [ ] Không gọi external services thật ngoài phạm vi; không kết nối production.
- [ ] Không nhầm MockMvc in-process với real HTTP server integration.
- [ ] Context cache được dùng hợp lý, không lạm dụng `@DirtiesContext`.
- [ ] JUnit/Gradle/Maven/CI thực thi đúng bộ test và ghi report.
- [ ] Không để fixture hoặc các assertions phụ thuộc thứ tự test.
- [ ] Nội dung log/debug không lộ token, cookie hoặc dữ liệu nhạy cảm.

## 16. Kết luận

**`@SpringBootTest + @AutoConfigureMockMvc` là lựa chọn cho Spring MVC integration testing với application context đầy đủ, nhưng vẫn sử dụng mock Servlet request/response và không mở HTTP server.** Nó phù hợp khi bạn cần xác minh một request đi qua MVC pipeline tới service/repository thật, đồng thời kiểm soát cấu hình test trong cùng JVM. `@WebMvcTest` nhỏ hơn, thường nhanh hơn; `RANDOM_PORT` kiểm tra nhiều thuộc tính real HTTP hơn.

Hiểu đúng ranh giới này sẽ giúp bạn chọn loại test vừa đủ mạnh, viết assertion có giá trị, tránh bỏ qua security filters, giữ dữ liệu độc lập và giảm sai lệch giữa máy phát triển với CI.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `MOCK`, `@AutoConfigureMockMvc` và MVC testing.
- [Spring Boot 3.5 — @AutoConfigureMockMvc Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/AutoConfigureMockMvc.html): package, `addFilters`, `print` và các option.
- [Spring Boot 4.0 — @AutoConfigureMockMvc Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/webmvc/test/autoconfigure/AutoConfigureMockMvc.html): package/module mới của Boot 4.
- [Spring Boot 4 — Build Systems & Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html): `spring-boot-starter-webmvc` và `spring-boot-starter-webmvc-test`.
- [Spring Framework — MockMvc Overview](https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html): cơ chế DispatcherServlet với mock Servlet API, không có real server.
- [Spring Framework — Configuring MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/setup.html): `standaloneSetup` so với `webAppContextSetup`.
- [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): tích hợp filter chain và security test.
- [Spring Security — Testing CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): dùng `with(csrf())` cho những method HTTP cần CSRF.
