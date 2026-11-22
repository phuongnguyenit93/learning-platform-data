# Ma trận chọn test slice theo thành phần và bằng chứng cần thu được

Trong Spring Boot, *test slice* là một cấu hình kiểm thử chỉ nạp **phần Spring ApplicationContext liên quan đến một công nghệ hoặc tầng cụ thể** thay vì tự động khởi tạo toàn bộ ứng dụng. Ví dụ, `@WebMvcTest` tập trung vào Spring MVC controller, còn `@DataJpaTest` tập trung vào JPA entity/repository. Điều quan trọng không phải chỉ là “test nào nhanh hơn”, mà là **lỗi nào bài test có khả năng phát hiện, và lỗi nào nằm ngoài phạm vi của nó**.

Một web slice kiểm đúng HTTP status/JSON **không chứng minh** SQL query thật; một JPA slice kiểm đúng mapping/query **không chứng minh** URL/controller/security; unit test với Mockito **không chứng minh** Spring dependency injection. Bài này đưa ra ma trận từ **thành phần cần kiểm → bằng chứng phải thu được → slice phù hợp → dependency bị loại → khi nào cần nâng lên integration/full-context**, kèm ví dụ Java 17+, Spring Boot 3.5 và JUnit Jupiter có thể chạy được.

## 1. Hiểu đúng: test slice nạp gì, không nạp gì?

Một slice thường kết hợp các cơ chế:

1. **Giới hạn component scanning:** chọn những loại bean liên quan, ví dụ controller, converter, MVC advice cho web slice; entity/repository cho data slice.
2. **Chỉ nạp tập auto-configuration cần thiết:** `@WebMvcTest` hỗ trợ MVC, JSON, validation/filter liên quan; `@DataJpaTest` hỗ trợ entity manager, repository, datasource/transaction.
3. **Cung cấp test utilities đúng mục tiêu:** `MockMvc`, `WebTestClient`, `TestEntityManager`, `JacksonTester`, `MockRestServiceServer` hoặc `GraphQlTester` tùy slice và phiên bản.
4. **Cache context theo cấu hình:** các test có cùng loại slice, bean overrides, properties/profile tương thích có thể tái dùng context; đổi cấu hình có thể tạo context mới.

**Slice không có nghĩa là một class duy nhất:** `@WebMvcTest` vẫn nạp nhiều MVC infrastructure beans, và `@DataJpaTest` có thể nạp Hibernate, DataSource và repositories. Ngược lại, slice cũng **không bảo đảm** không có I/O: JPA slice có thể truy cập DB thật, Redis/Mongo slice có thể kết nối service thật nếu test configuration chỉ đến chúng. “Slice” chủ yếu nói về **biên context**, không phải “chắc chắn chỉ mock”.

Khi một bean ứng dụng cần dependency nằm **ngoài** slice, cần cung cấp collaborator qua `@MockitoBean`, `@Import`, `@TestConfiguration` hoặc cơ chế phù hợp **có chủ đích**. Nếu import dần toàn bộ lớp sản xuất vào web slice chỉ để context chạy, slice đã mất ý nghĩa. Hãy nâng test lên cấp tích hợp khi cần chứng minh ranh giới thật.

## 2. Ma trận chính: thành phần → bằng chứng → slice

| Thành phần hoặc rủi ro | Lựa chọn khởi đầu | Bằng chứng có thể thu được | Không chứng minh được mặc định |
|---|---|---|---|
| Hàm domain, validator tự viết, chính sách giá/chiết khấu thuần Java | **JUnit Jupiter + Mockito/fake**, không cần Spring | Nhánh logic, invariant, exception, interaction với fake | DI, annotation, HTTP, SQL, transaction thật |
| **Spring MVC controller**, binding, validation, `@ControllerAdvice`, status/JSON | **`@WebMvcTest(Controller.class)`** + `MockMvc` | MVC route, HTTP serialization, filter/security được nạp, error mapping | Service/JPA thật nếu đã mock collaborator; không kiểm TCP socket |
| **Spring WebFlux controller/handler** | **`@WebFluxTest`** + `WebTestClient` thích hợp | Reactive web routing, status/body, codec/filter trong slice | End-to-end với remote dependencies, real database, toàn bộ reactive service graph |
| Jackson serialization/deserialization, custom JSON module, field name/format | **`@JsonTest`** + `JacksonTester` hoặc JSON tester khác | Object ↔ JSON, custom serializer/deserializer/config được nạp | Controller mapping, HTTP status/filter, DB, service |
| **JPA entity**, repository query, mapping, flush, constraint cơ bản | **`@DataJpaTest`** | Entity mapping, JPA repository thực và SQL trên test DB, transaction của slice | Controller/service wiring, production DB dialect khi dùng H2, concurrency ngoài test transaction |
| Spring Data JDBC aggregate/repository | **`@DataJdbcTest`** | Spring Data JDBC mapping và repository với test DB | Hibernate/JPA semantics hoặc business workflow tổng thể |
| `JdbcTemplate`, `JdbcClient`, SQL/RowMapper thủ công | **`@JdbcTest`** | SQL statement, row mapping, datasource/transaction trong slice | JPA repository hoặc web |
| jOOQ DSL và SQL mapping | **`@JooqTest`** | jOOQ DSLContext/query trên datasource test | Web/controller, service orchestration |
| Reactive SQL, R2DBC repository | **`@DataR2dbcTest`** | Reactive repository và mapping trên DB/R2DBC test | Servlet/JPA behavior; transaction/rollback như JDBC khi không cấu hình rõ |
| MongoDB / Redis / Elasticsearch / Cassandra / Couchbase / Neo4j data access | **Slice data tương ứng** (`@DataMongoTest`, `@DataRedisTest`, `@DataElasticsearchTest`, v.v.) | Repository/client mapping, query/interaction với dependency thực hoặc test fixture đã cấu hình | Ràng buộc/behavior của môi trường production nếu chỉ mock hoặc dùng server khác |
| **REST client đồng bộ** dùng `RestTemplate`/`RestClient` | **`@RestClientTest(Client.class)`** | URL, method, headers, JSON, error mapping qua mock HTTP server | Server remote thật, TLS/network thật và business workflow của caller |
| GraphQL controller, schema/query/resolver | **`@GraphQlTest`** + `GraphQlTester` | GraphQL document, data fetcher/controller mapping, response và lỗi trong slice | HTTP transport thật, database hoặc service thật nếu đã mock |
| SOAP client/server | **`@WebServiceClientTest` / `@WebServiceServerTest`** | XML/soap mapping, marshaling, endpoint/client behavior trong slice | Remote SOAP service/network thật |
| Chạy ứng dụng đầy đủ và phối hợp controller → service → repository | **`@SpringBootTest`** (không phải slice) + công cụ test thích hợp | Spring wiring và nhiều tầng thật cùng hoạt động | Đường mạng thực nếu dùng `MOCK`, hạ tầng production nếu môi trường test khác |
| End-to-end HTTP qua socket, transaction across request, external services | **`@SpringBootTest(webEnvironment = RANDOM_PORT)`** + DB/containers/contract | HTTP server thật, serialization, wiring nhiều tầng, integration với dependency được chọn | Reverse proxy, TLS/deployment thật nếu môi trường không bao gồm chúng |

**Cách đọc bảng:** bắt đầu từ **bằng chứng cần thu**, không từ tên package. Ví dụ “controller trả 404 đúng khi service không tìm thấy” → web slice với mocked service đủ cho **mapping**; “tìm bản ghi bằng SKU thật có đúng không” → JPA slice; “gọi GET lấy giá từ DB qua controller có đúng không” → cần một test tích hợp nối cả hai, không thể suy ra chỉ từ hai test slice rời rạc.

Các slice nêu ở bảng trên được hỗ trợ theo công nghệ và phiên bản Spring Boot đã khai báo dependency phù hợp; không nên đưa cả bộ vào một module chỉ vì thấy danh sách dài.

## 3. Sơ đồ quyết định nhanh

```text
Điều gì có thể hỏng và cần chứng minh?
 |
 +-- Chỉ điều kiện/thuật toán trong object? ------> JUnit thuần + fake/mock
 |
 +-- Object ↔ JSON serialization? ----------------> @JsonTest
 |
 +-- HTTP request mapping/controller?
 |      |
 |      +-- Servlet MVC? --------------------------> @WebMvcTest + MockMvc
 |      +-- Reactive WebFlux? ---------------------> @WebFluxTest + WebTestClient
 |      +-- Phải đi qua HTTP socket thật? ---------> @SpringBootTest(RANDOM_PORT)
 |
 +-- Persistence/query?
 |      |
 |      +-- JPA/Hibernate? ------------------------> @DataJpaTest
 |      +-- Spring Data JDBC? ---------------------> @DataJdbcTest
 |      +-- SQL/JdbcTemplate/JdbcClient? ----------> @JdbcTest
 |      +-- R2DBC hoặc NoSQL? ---------------------> Slice data tương ứng
 |
 +-- Gọi API bên ngoài, kiểm request/response? ----> @RestClientTest
 |
 +-- GraphQL schema/resolver? --------------------> @GraphQlTest
 |
 +-- Quan hệ nhiều tầng, transaction, wiring? ----> @SpringBootTest/Integration
```

Đây là **gợi ý điểm khởi đầu**, không phải quy tắc cứng. Một controller có logic tính toán phức tạp vẫn nên có unit test ở domain/service; HTTP slice kiểm lớp web, còn phép tính chi tiết do test nghiệp vụ đảm nhận. Test tốt thường là **tập nhiều cấp có phạm vi bổ sung nhau**, không phải chọn một annotation rồi bỏ các cấp còn lại.

## 4. Ma trận “đã chứng minh/chưa chứng minh” theo chuỗi yêu cầu

Xét request `GET /api/products/BOOK-1/price` qua controller → service → repository → database.

| Bằng chứng cần khẳng định | Unit `ProductService` với fake | `@WebMvcTest` | `@DataJpaTest` | `@SpringBootTest(MOCK)` + MockMvc + DB test | `@SpringBootTest(RANDOM_PORT)` + DB test |
|---|---|---|---|---|---|
| Service xử lý đúng khi repository trả sản phẩm | **Có** | Không (service thường được mock) | Không | **Có** nếu dùng service thật | **Có** nếu dùng service thật |
| URL, `@PathVariable`, status và JSON | Không | **Có** | Không | **Có** | **Có** |
| JPA entity/query và DB round-trip | Không | Không | **Có** | **Có** | **Có** |
| Spring DI nối controller → service → repository | Không | **Không đầy đủ** nếu mock service | Không | **Có** | **Có** |
| HTTP server thật xử lý request qua socket | Không | Không | Không | Không | **Có** |
| Tính tương thích với PostgreSQL production | Không | Không | **Chỉ khi dùng DB phù hợp** | **Chỉ khi dùng DB phù hợp** | **Chỉ khi dùng DB phù hợp** |
| Toàn bộ hạ tầng deployment (proxy, TLS, gateway) | Không | Không | Không | Không | **Chưa đủ** nếu test chỉ localhost |

Ô “Có” luôn có điều kiện: assertions phải thực sự kiểm đúng hành vi và bean/database phải là loại được nêu. `@SpringBootTest` nạp nhiều bean nhưng nếu `@MockitoBean` thay repository thì test không chứng minh SQL thật. Tên annotation không thay thế việc xem **dependency nào bị mock**.

## 5. Ví dụ runnable Java 17 + Spring Boot 3.5: hai slice và một test nối tầng

Ví dụ thực hành minh họa ba ranh giới:

1. `@WebMvcTest` chứng minh **routing, JSON và 404** với service được mock.
2. `@DataJpaTest` chứng minh **JPA mapping/query** với H2 in-memory thật.
3. `@SpringBootTest(MOCK)` + `MockMvc` chứng minh **controller → service → JPA repository → H2** trong một context; vẫn không kiểm socket HTTP.

Giả sử sản phẩm có SKU và giá VND. API `GET /api/products/{sku}/price` trả `{"sku":"BOOK-1","priceVnd":120000}` khi có bản ghi và HTTP 404 khi không tìm thấy.

### 5.1. Cây thư mục

```text
product-slice-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/shop/
    │   ├── ShopApplication.java
    │   ├── Product.java
    │   ├── ProductRepository.java
    │   ├── ProductService.java
    │   └── PriceController.java
    └── test/java/com/example/shop/
        ├── PriceControllerSliceTest.java
        ├── ProductRepositorySliceTest.java
        └── ProductFlowIntegrationTest.java
```

### 5.2. Maven POM

File **`pom.xml`** dùng Spring Boot **3.5.0**, Java 17; khi áp dụng thực tế hãy nâng đến patch được dự án phê duyệt:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>product-slice-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

H2 là lựa chọn **dạy cách chạy slice**, không phải lời bảo đảm mọi SQL hoặc transaction trên PostgreSQL/MySQL production đều tương đương. `spring-boot-starter-test` đưa JUnit Jupiter, AssertJ, MockMvc, Mockito và Spring TestContext vào test classpath theo dependency quản lý của Boot.

### 5.3. Mã ứng dụng

File **`src/main/java/com/example/shop/ShopApplication.java`**:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

File **`src/main/java/com/example/shop/Product.java`**:

```java
package com.example.shop;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private long priceVnd;

    protected Product() {
        // JPA requires a no-arg constructor.
    }

    public Product(String sku, long priceVnd) {
        this.sku = sku;
        this.priceVnd = priceVnd;
    }

    public String getSku() {
        return sku;
    }

    public long getPriceVnd() {
        return priceVnd;
    }
}
```

File **`src/main/java/com/example/shop/ProductRepository.java`**:

```java
package com.example.shop;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {
    Optional<Product> findBySku(String sku);
}
```

File **`src/main/java/com/example/shop/ProductService.java`**:

```java
package com.example.shop;

import java.util.NoSuchElementException;

import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public long priceOf(String sku) {
        return repository.findBySku(sku)
                .orElseThrow(() -> new NoSuchElementException("Missing SKU: " + sku))
                .getPriceVnd();
    }
}
```

File **`src/main/java/com/example/shop/PriceController.java`**:

```java
package com.example.shop;

import java.util.NoSuchElementException;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/products")
public class PriceController {
    private final ProductService service;

    public PriceController(ProductService service) {
        this.service = service;
    }

    public record PriceResponse(String sku, long priceVnd) {
    }

    @GetMapping("/{sku}/price")
    public PriceResponse price(@PathVariable String sku) {
        try {
            return new PriceResponse(sku, service.priceOf(sku));
        } catch (NoSuchElementException ex) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Product not found", ex);
        }
    }
}
```

Controller chuyển “không tìm thấy” thành HTTP 404; service không phụ thuộc vào HTTP status mà chỉ biết repository. `Product` là JPA entity thật; `ProductRepository` sẽ thực thi SQL khi context có datasource. Các lớp đều nằm dưới `com.example.shop` để cấu hình gốc được phát hiện.

### 5.4. Web slice: mock service, kiểm HTTP mapping

File **`src/test/java/com/example/shop/PriceControllerSliceTest.java`**:

```java
package com.example.shop;

import java.util.NoSuchElementException;

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

@WebMvcTest(PriceController.class)
class PriceControllerSliceTest {
    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private ProductService service;

    @Test
    void returnsJsonFromControllerForKnownSku() throws Exception {
        when(service.priceOf("BOOK-1")).thenReturn(120_000L);

        mvc.perform(get("/api/products/BOOK-1/price"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku").value("BOOK-1"))
                .andExpect(jsonPath("$.priceVnd").value(120_000));

        verify(service).priceOf("BOOK-1");
    }

    @Test
    void mapsMissingProductTo404() throws Exception {
        when(service.priceOf("MISSING"))
                .thenThrow(new NoSuchElementException("MISSING"));

        mvc.perform(get("/api/products/MISSING/price"))
                .andExpect(status().isNotFound());

        verify(service).priceOf("MISSING");
    }
}
```

**Bằng chứng có được:** đường dẫn, `@PathVariable`, JSON serialization, HTTP 200/404 và lời gọi controller tới service collaborator. **Không có bằng chứng** repository đã chạy SQL: service là **Mockito mock trong Spring context**. `@WebMvcTest` tự cấu hình `MockMvc` nhưng không nạp toàn bộ service/repository như `@SpringBootTest`.

`@MockitoBean` trong ví dụ dùng import thuộc **Spring Framework 6.2+**, có trong bộ Spring Boot 3.5. Trong web slice, bean `ProductService` gốc thường không được scan; mặc định `@MockitoBean` có thể **tạo mock bean mới** để thoả dependency. Đừng dùng `enforceOverride = true` trong tình huống cố ý chỉ có mock này nếu không có service bean gốc để thay.

**Security lưu ý:** khi Spring Security nằm trên classpath, các filter/security auto-configuration phù hợp có thể tham gia web slice. Test 200/404 có thể cần authentication/CSRF setup hoặc security-specific test dependency. Không tắt filter tùy tiện chỉ để test xanh khi chính authorization là điều muốn chứng minh.

### 5.5. JPA slice: repository và SQL thật trên test DB

File **`src/test/java/com/example/shop/ProductRepositorySliceTest.java`**:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest
class ProductRepositorySliceTest {
    @Autowired
    private ProductRepository repository;

    @Test
    void findsPersistedProductBySku() {
        repository.saveAndFlush(new Product("BOOK-2", 150_000L));

        Product found = repository.findBySku("BOOK-2").orElseThrow();

        assertEquals("BOOK-2", found.getSku());
        assertEquals(150_000L, found.getPriceVnd());
    }

    @Test
    void returnsEmptyForUnknownSku() {
        assertTrue(repository.findBySku("UNKNOWN").isEmpty());
    }
}
```

`@DataJpaTest` nạp Spring Data JPA, entity manager, repositories và datasource/test transaction theo cấu hình. Với H2 trên classpath, test này chạy query thật trên **H2 in-memory**. Các test `@DataJpaTest` thông thường **transactional và rollback cuối mỗi test**, nên fixture của `BOOK-2` không bị giữ lâu dài.

**Bằng chứng có được:** entity mapping, query `findBySku`, flush/đọc lại và giá trị persisted. **Không có bằng chứng** controller route hoặc service HTTP mapping, vì những bean này không thuộc JPA slice.

Nếu code dùng PostgreSQL-specific functions, transaction isolation hoặc migration phức tạp, H2 có thể che lỗi. Khi cần chứng minh tương thích DB production, dùng test database đúng engine — thường qua **Testcontainers** — và vô hiệu hóa thay thế embedded DB nếu cần bằng `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)`, cùng cách cấu hình datasource phù hợp phiên bản. Không tuyên bố JPA slice “không chạm DB thật”: nó chạm database **được cấu hình cho test**, có thể là external DB.

### 5.6. Test nối các slice: chạy controller → service → JPA

File **`src/test/java/com/example/shop/ProductFlowIntegrationTest.java`**:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = WebEnvironment.MOCK)
@AutoConfigureMockMvc
@Transactional
class ProductFlowIntegrationTest {
    @Autowired
    private MockMvc mvc;

    @Autowired
    private ProductRepository repository;

    @Test
    void readsPersistedPriceThroughRealServiceAndController() throws Exception {
        repository.saveAndFlush(new Product("BOOK-3", 160_000L));

        mvc.perform(get("/api/products/BOOK-3/price"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku").value("BOOK-3"))
                .andExpect(jsonPath("$.priceVnd").value(160_000));
    }
}
```

Bài này **không phải slice**. Nó nạp controller, service, repository, datasource và các bean ứng dụng, rồi thực hiện request qua **MockMvc in-process**. Do test này dùng MockMvc đồng bộ với thao tác JPA trong cùng test thread, cấu hình `@Transactional` thường giúp rollback dữ liệu được tạo trong test. Nhưng **không khẳng định điều này cho server HTTP thật** ở `RANDOM_PORT`: request ở server thread có transaction khác, dữ liệu đã commit không tự rollback theo test thread.

Bằng chứng mới thu được là **các tầng được nối đúng bằng Spring DI**. Dù vậy, test vẫn chưa gửi network request thật, và database chỉ là H2. Nếu bug mục tiêu là servlet container, real HTTP client, TLS hoặc PostgreSQL dialect, cần một test tích hợp khác đúng ranh giới.

### 5.7. Chạy các bài test

Trong thư mục Maven project có `pom.xml`:

```bash
mvn test
```

Nếu đã có Maven Wrapper do công cụ tạo project cung cấp:

```bash
./mvnw test
```

Chạy riêng từng loại để quan sát phạm vi:

```bash
./mvnw -Dtest=PriceControllerSliceTest test
./mvnw -Dtest=ProductRepositorySliceTest test
./mvnw -Dtest=ProductFlowIntegrationTest test
```

Trên Windows, sử dụng `mvnw.cmd` nếu có wrapper, hoặc `mvn` khi đã cài Maven. Với đúng ba lớp trên có **5 phương thức `@Test`** (2 web + 2 JPA + 1 integration), kỳ vọng **5 pass, 0 fail** khi các dependency/config H2 được nạp đúng. Đây là các test JUnit, không có stdout nghiệp vụ bắt buộc; Surefire/JUnit có thể định dạng báo cáo khác theo phiên bản.

**Kết luận từ ba test:** web slice + JPA slice cho những bằng chứng *từng tầng*, trong khi test `@SpringBootTest` cho bằng chứng **nối tầng**. Không nên suy ra việc nối tầng đúng chỉ vì từng slice chạy xanh.

## 6. Các slice khác: dùng đúng công cụ ở đúng ranh giới

### `@JsonTest`: serializer và deserializer

Dùng khi risk là tên field, định dạng date/number, custom Jackson module, deserializer hoặc `@JsonComponent`. Thường inject `JacksonTester<MyDto>` / `JsonContent` tùy thư viện và config. Một đoạn khung:

```java
@JsonTest
class PriceJsonTest {
    @Autowired
    private JacksonTester<PriceDto> json;

    // @Test: json.write(...), so với JSON mẫu;
    // @Test: json.parseObject(...), assert các field.
}
```

Đây là **snippet**, không tự biên dịch do `PriceDto` và imports là thành phần ứng dụng. JSON slice không kiểm `@GetMapping`, `@Valid` ở controller hay HTTP status. Nếu chỉ muốn test hai quy tắc của domain và không có serialization, không cần `@JsonTest`.

### `@RestClientTest`: outgoing HTTP client

Khi ứng dụng có **REST client đồng bộ** dùng `RestTemplate` hoặc `RestClient`, slice giúp cấu hình HTTP client và mock server `MockRestServiceServer` để assert **URL, method, headers, body, response mapping** mà không gọi dịch vụ ngoài. Một mẫu ý tưởng:

```java
@RestClientTest(ExchangeRateClient.class)
class ExchangeRateClientTest {
    @Autowired
    private ExchangeRateClient client;

    @Autowired
    private MockRestServiceServer server;

    // @Test: server.expect(requestTo("https://..."))
    //              .andRespond(withSuccess("{...}", APPLICATION_JSON));
    // Gọi client, assert kết quả, server.verify().
}
```

Đoạn này **không độc lập**: `ExchangeRateClient`, URI, JSON contract và imports tùy dự án. Tránh nhầm `@RestClientTest` với test **controller nhận HTTP**: nó tập trung vào **outgoing HTTP client**. Với WebClient/reactive HTTP client, kiểm đúng module/utility của version; không suy đoán mọi WebClient được `MockRestServiceServer` hỗ trợ giống RestTemplate.

### `@GraphQlTest`: query/resolver trong GraphQL

Khi risk là schema, argument binding, data fetcher, error shape hoặc response GraphQL, dùng `@GraphQlTest` với `GraphQlTester`. Cần mock/import collaborator nằm ngoài GraphQL slice. Việc `GraphQlTester` pass **không chứng minh HTTP/WebSocket transport** hoặc DB thật, trừ khi test bổ sung ranh giới đó.

### Slice dữ liệu ngoài JPA

- **`@JdbcTest`**: SQL/JdbcTemplate/JdbcClient khi không cần Spring Data repository.
- **`@DataJdbcTest`**: Spring Data JDBC aggregate/repository, khác ORM/JPA.
- **`@JooqTest`**: query DSL và SQL mapping của jOOQ.
- **`@DataR2dbcTest`**: reactive SQL repository. Reactive transaction và blocking transaction khác nhau; không mặc định `@Transactional` test sẽ rollback như JPA slice khi chưa kiểm rõ.
- **`@DataMongoTest`**, **`@DataRedisTest`**, **`@DataElasticsearchTest`**, **`@DataCassandraTest`**, **`@DataCouchbaseTest`**, **`@DataNeo4jTest`**: data-stack tương ứng. Nhiều công nghệ **không có embedded server được tự tạo**; muốn kiểm thực có thể cần container/service test riêng.

Chọn slice theo **công nghệ implementation thật**. Nếu module viết repository bằng JDBC thủ công, `@DataJpaTest` không giúp chứng minh SQL đúng chỉ vì cả hai đều truy cập relational DB. Và với query phụ thuộc database vendor, chọn đúng DB engine quan trọng hơn tên slice.

## 7. Spring Boot 3.5 và 4.x: tránh copy import sai

**Các ví dụ runnable trong phần 5 cố định theo Spring Boot 3.5.0.** Trong 3.5, những import tiêu biểu là:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

`@MockitoBean` đến từ **Spring Framework 6.2+**, phù hợp với Boot 3.5. `@MockBean` của Spring Boot bị deprecated từ 3.4 và đã bị loại bỏ trong Boot 4.0. Vì vậy việc dùng `@MockitoBean` có chủ đích hơn cho mã định hướng 3.5 → 4.x.

**Spring Boot 4.x tổ chức lại test thành các module/starter theo công nghệ** (ví dụ `spring-boot-webmvc-test`, `spring-boot-data-jpa-test`, `spring-boot-restclient-test`) và có các package auto-configuration khác 3.5. Đừng tự copy import `org.springframework.boot.test.autoconfigure...` trong ví dụ Boot 3.5 sang Boot 4.0 mà không đối chiếu API/Javadoc và dependency tree. Các tên annotation/slice thường vẫn tồn tại, nhưng **vị trí class, module và starter** cần kiểm theo bản đã pin.

Cần đồng thời xác nhận:

1. Java version tối thiểu của dòng Boot/Framework dự án.
2. Dependency test starter/module tương ứng đã có trên test classpath chưa.
3. Tên/import `@...Test` có đúng version không.
4. Bean overrides `@MockitoBean`/`@MockitoSpyBean` có hoạt động và nhắm đúng bean không.
5. Các auto-configuration thực tế được nhập vào slice; xem **appendix test slices** của chính dòng Boot đang sử dụng.

Đây là lý do không nên dùng một bảng tên slice mà mặc định **mọi version** đều có package, attribute và auto-config giống nhau.

## 8. Khi slice không nạp được bean: sửa đúng phạm vi

Ví dụ `@WebMvcTest(ProductController.class)` báo thiếu `ProductService` là điều dễ hiểu: service thông thường **không thuộc MVC slice**. Ba cách ứng xử hợp lý:

| Mục tiêu | Cách làm |
|---|---|
| Chỉ muốn chứng minh HTTP mapping và controller behavior | Cung cấp `@MockitoBean ProductService`, stub response/exception và assert HTTP |
| Cần thêm một bean cụ thể phục vụ mapping/serialization | `@Import` một config/bean nhỏ hoặc dùng `@TestConfiguration`, không kéo cả app |
| Muốn chứng minh controller dùng service thật và repository thật | Dùng `@SpringBootTest` (có thể MOCK + MockMvc) với test DB, không biến MVC slice thành full context |

**Không import hàng loạt mọi `@Service`, `@Repository`, `@Configuration`** chỉ để slice khởi động. Điều đó tăng thời gian, thay đổi phạm vi và làm mờ kết luận. Nếu service thật là trọng tâm, viết unit test của service trước rồi thêm integration test phù hợp.

Chú ý khi ứng dụng dùng `@ComponentScan` explicit trên `@SpringBootApplication`: nó có thể làm vô hiệu các exclude filters mặc định của slice và kéo vào bean ngoài ý muốn. Nếu test slice có dấu hiệu nạp “quá nhiều”, hãy kiểm cấu hình scan/import thay vì tự sửa bằng các mock tùy tiện.

## 9. Cẩn trọng với DB replacement, transaction và mock

### `@DataJpaTest` không tự đồng nghĩa “production DB”

Với H2 embedded trên classpath, Boot có thể chọn/thay datasource bằng embedded test database. Test này tuyệt vời để phát hiện lỗi mapping/query phổ biến, nhưng có thể **không** bắt lỗi của PostgreSQL-specific SQL, JSONB, collations, locking, isolation hoặc migration production.

Khi cần bằng chứng tương thích chính xác, dùng database test đúng engine, thường Testcontainers, cùng cấu hình datasource thích hợp. `@AutoConfigureTestDatabase(replace = NONE)` là công cụ thường dùng để ngăn replacement khi muốn giữ datasource được chỉ định. Chỉ mở rộng phạm vi dependency khi đó là yêu cầu rủi ro thật, không tự tăng chi phí mọi test.

### Rollback phụ thuộc thread và transaction boundary

Các relational data slice như `@DataJpaTest` thông thường transactional với rollback cuối test. Nhưng **HTTP test dùng server thật** ở `@SpringBootTest(RANDOM_PORT)` chạy server-side ở thread/transaction khác test client; `@Transactional` của test không tự rollback dữ liệu server đã commit. Trong integration test qua socket, cần cleanup rõ và DB test riêng.

### Mock nhiều quá làm “xanh giả”

Nếu `@WebMvcTest` mock cả service, điều đó là **đúng** khi mục tiêu chỉ là HTTP layer. Nó lại là **không đủ** nếu mục tiêu là “hệ thống có lấy đúng giá từ database không”. Đặt câu hỏi về rủi ro trước khi mock, không đo chất lượng test bằng số lượng context xanh.

## 10. Hiệu năng và cách phân tầng test trên CI

Một chiến lược thực tế:

- **Mỗi commit / PR:** nhiều unit test thuần cho rule, tập web/data/JSON/REST client slices có scope nhỏ, và một số integration test quan trọng nối các tầng.
- **Theo pipeline phù hợp:** các integration tests cần DB engine thật/containers, contract tests với dịch vụ ngoài và test HTTP server thật cho đường đi có rủi ro.
- **Trước phát hành:** kịch bản end-to-end cần deployment/proxy/security/migration đúng môi trường nếu đây là cam kết sản phẩm.

Không có tỷ lệ “unit 80%, slice 15%, E2E 5%” áp dụng phổ quát. Chọn theo **chi phí lỗi thực tế, xác suất thay đổi, tốc độ phản hồi và độ tin cậy của môi trường**. Slice thường là điểm cân bằng: phát hiện lỗi framework mapping/cấu hình mà unit thuần không thấy, nhưng rẻ hơn toàn bộ application context.

Spring TestContext cache dựa vào cấu hình. Hai web slices cùng `@MockitoBean` nhưng khác tên field/qualifier, properties hoặc imports có thể tạo context cache key khác. Hãy đặt tên mock nhất quán khi nhắm cùng bean, tránh `@DirtiesContext` không cần thiết và không dùng shared mutable fixtures để giảm flakiness.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| `@WebMvcTest` thiếu `@Service` | Slice cố ý không scan business service | `@MockitoBean`/import tối thiểu; hoặc nâng `@SpringBootTest` nếu cần service thật |
| `@DataJpaTest` không inject được controller | JPA slice không nạp MVC | Viết web slice hoặc integration test riêng |
| Web test trả 401/403 thay vì 200 | Security/filter đang hoạt động trong MVC slice | Cấu hình user/CSRF/mock authentication đúng mục tiêu; không bỏ security vô ý |
| JSON test pass nhưng endpoint JSON sai | `@JsonTest` không kiểm HTTP/controller mapping | Bổ sung `@WebMvcTest` hoặc integration với HTTP |
| `@RestClientTest` pass nhưng remote API đổi contract | Mock server dùng fixture lạc hậu | Thêm contract/integration test với upstream phù hợp |
| JPA slice pass với H2, production lỗi SQL | Dialect/schema/transaction không tương thích | Dùng đúng engine DB test + migrations, Testcontainers |
| Context test khởi động hàng loạt bean ngoài ý định | `@ComponentScan`/imports làm hỏng slice exclusion | Kiểm scan/exclude filters, tối giản import |
| Mock bean service không ảnh hưởng controller | Mock không nằm trong Spring context hoặc qualifier sai | `@MockitoBean` đúng bean, verify tương tác trên bean được inject |
| Test slice quá chậm | Nhiều cấu hình khác nhau, context cache ít tái sử dụng | Giữ profile/import/override nhất quán, giảm `@DirtiesContext` |
| “Hai slice pass tức full flow pass” | Chưa kiểm DI/wiring giữa các tầng | Thêm integration test nối controller, service, repository |
| Test dùng sai slice cho stack | MVC vs WebFlux, JPA vs JDBC/R2DBC nhầm | Chọn theo implementation thật và rủi ro cần chứng minh |
| Boot 4 compile lỗi import slice cũ | Test modules/package đã tổ chức lại | Xem docs đúng version và thêm test starter/module phù hợp |

## 12. Checklist chọn slice trước khi viết test

- [ ] Tôi diễn đạt được **một lỗi cụ thể cần phát hiện** và assertion chứng minh nó.
- [ ] Tôi xác định đối tượng là **domain, MVC, WebFlux, JSON, JPA, JDBC, client HTTP hay GraphQL**.
- [ ] Tôi biết slice nào nạp bean thật, bean nào **bị loại** hoặc mock.
- [ ] Tôi không dùng `@SpringBootTest` cho logic thuần khi JUnit thuần đã đủ.
- [ ] Tôi không dùng `@WebMvcTest` để tuyên bố đã kiểm SQL hoặc service business thật khi service đang mock.
- [ ] Với JPA slice, tôi biết **database nào** đang chạy và có cần production-like engine không.
- [ ] Với web slice, security/filter, validation, controller advice và JSON config đúng phạm vi test.
- [ ] Nếu test cần chứng minh **tầng A nối tầng B**, có integration test thực sự nối chúng.
- [ ] Nếu cần HTTP socket/TLS/external contract, tôi không nhầm MockMvc với real network.
- [ ] Tôi kiểm tra package/module/annotation tương thích **Spring Boot 3.5 hay 4.x** đang dùng.
- [ ] Tôi đã chạy test qua build tool và xác minh assertions/side effects, không chỉ context start.
- [ ] Tôi cân bằng độ nhanh, độ tin cậy và chi phí lỗi thay vì chọn slice chỉ theo tên.

**Kết luận:** **Chọn slice theo bằng chứng cần thu, không theo sở thích annotation.** `@WebMvcTest` chứng minh lớp HTTP/MVC trong process; `@DataJpaTest` chứng minh persistence trên database test; `@JsonTest` chứng minh serialization; `@RestClientTest` chứng minh outgoing HTTP client; `@SpringBootTest` nối các tầng khi đó là rủi ro. Một bộ test tốt nêu rõ **phạm vi điều đã chứng minh và điều chưa chứng minh**.

### Tài liệu chính thức để đối chiếu version

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — Test Slices và auto-configuration](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html)
- [Spring Boot 4 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot 4 — Test modules](https://docs.spring.io/spring-boot/reference/testing/test-modules.html)
- [Spring Boot 4 — Test Slices](https://docs.spring.io/spring-boot/appendix/test-auto-configuration/slices.html)
