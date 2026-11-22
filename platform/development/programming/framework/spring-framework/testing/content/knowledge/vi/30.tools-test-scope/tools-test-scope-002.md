# `@SpringBootTest` thuộc Spring Boot và phạm vi nạp ứng dụng

`@SpringBootTest` là annotation kiểm thử tích hợp của **Spring Boot**, không phải annotation thuộc Spring Framework core. Nó yêu cầu Spring TestContext khởi tạo ứng dụng bằng cơ chế `SpringApplication` của Boot, từ đó nạp cấu hình chính, component scan, auto-configuration và các bean mà ứng dụng tạo ra trong môi trường test. Phạm vi này rộng hơn một test chỉ dựng một controller hoặc repository riêng lẻ, nên phù hợp khi cần kiểm tra nhiều thành phần phối hợp trong application context gần với cách ứng dụng khởi động.

Tên “full application context” thường được dùng để mô tả loại test này, nhưng không có nghĩa mọi class trong repository đều được nạp. Context chỉ chứa những bean được cấu hình, scan, import hoặc tạo bởi auto-configuration trong điều kiện hiện tại. Profile, property, điều kiện `@Conditional`, loại web environment và cấu hình test đều có thể làm thay đổi tập bean thực tế.

## Annotation thuộc Spring Boot

`@SpringBootTest` nằm trong package:

```java
import org.springframework.boot.test.context.SpringBootTest;
```

Annotation này được cung cấp bởi module `spring-boot-test`. Trong ứng dụng Spring Boot thông thường, dependency `spring-boot-starter-test` đã đưa các thư viện kiểm thử cần thiết vào test classpath:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Hãy để Spring Boot dependency management quản lý version. Không nên tự chọn một version `spring-boot-test` khác dòng với `spring-boot` mà ứng dụng đang chạy.

Spring Framework cung cấp Spring TestContext Framework, `@ContextConfiguration`, `@WebAppConfiguration`, `@Transactional` cho test và các integration với JUnit. Spring Boot bổ sung bootstrapper và test support để khởi động ứng dụng theo cách Boot thực hiện. `@SpringBootTest` sử dụng hạ tầng TestContext của Spring, nhưng quyết định cách tạo context dựa trên `SpringApplication` và các quy tắc cấu hình của Boot.

## `@SpringBootTest` khởi tạo context như thế nào?

Khi test được chạy, Spring Boot TestContext bootstrapper tìm cấu hình ứng dụng, chuẩn bị `SpringApplication`, áp dụng các thuộc tính và customizer của test, rồi khởi tạo `ApplicationContext`. Quá trình này có thể bao gồm:

- Đọc cấu hình chính được đánh dấu `@SpringBootConfiguration`, thường là class có `@SpringBootApplication`.
- Thực hiện component scanning theo cấu hình ứng dụng.
- Áp dụng auto-configuration phù hợp với classpath, properties và các điều kiện `@Conditional`.
- Nạp các bean từ `@Configuration`, `@Import`, component scan và cấu hình test được khai báo.
- Áp dụng active profiles, inline properties, dynamic properties và các customizer của Spring Boot Test.
- Tạo mock web application context hoặc khởi động embedded web server tùy `webEnvironment`.

Ví dụ ứng dụng:

```java
@SpringBootApplication
public class StoreApplication {

    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
```

`@SpringBootApplication` kết hợp vai trò cấu hình Boot, bật auto-configuration và component scan. Khi test tìm được class này, Boot có điểm bắt đầu để tạo context tương tự ứng dụng.

Test tích hợp cơ bản:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class StoreApplicationTests {

    @Test
    void applicationContextLoads() {
        // Nếu context không khởi tạo được, test thất bại trước khi vào method.
        assertThat(true).isTrue();
    }
}
```

Test này xác nhận ứng dụng có thể khởi tạo context trong cấu hình test hiện tại. Nó không tự chứng minh mọi endpoint, truy vấn hoặc quy tắc nghiệp vụ đều hoạt động đúng; các hành vi đó cần assertion cụ thể.

## Boot tìm cấu hình ứng dụng ở đâu?

Nếu không chỉ định `classes`, `@SpringBootTest` tìm cấu hình chính từ test class. Thông thường, Boot tìm class được đánh dấu `@SpringBootConfiguration` bằng cách đi ngược từ package của test qua các package cha. Trong dự án thông thường, annotation đó được cung cấp gián tiếp bởi `@SpringBootApplication`.

Ví dụ cấu trúc package:

```text
com.example.store
    StoreApplication.java          (@SpringBootApplication)
    order/
        OrderService.java
        OrderRepository.java
    web/
        OrderController.java
    test/
        StoreApplicationTests.java
```

Nếu test nằm trong package con của `com.example.store`, Boot thường tìm được `StoreApplication`. Nếu test nằm ngoài cây package đó, hoặc dự án có nhiều cấu hình Boot, có thể cần chỉ rõ class để tránh chọn nhầm cấu hình.

```java
@SpringBootTest(classes = StoreApplication.class)
class OrderIntegrationTest {
}
```

Thuộc tính `classes` nhận một hoặc nhiều class cấu hình dùng để tạo test context. Khi khai báo rõ `classes`, test không phải dựa vào việc dò tìm cấu hình mặc định. Các class bổ sung có thể là cấu hình test, nhưng cần hiểu chúng sẽ tham gia vào context cùng cấu hình chính như thế nào.

## `classes`, `@TestConfiguration` và cấu hình bổ sung

Khi cần thay một dependency hoặc thêm bean chỉ dùng trong test, không nhất thiết phải tạo một ứng dụng giả hoàn toàn. Có thể bổ sung cấu hình test bằng `@TestConfiguration`:

```java
@SpringBootTest
class OrderIntegrationTest {

    @TestConfiguration
    static class TestBeans {

        @Bean
        Clock testClock() {
            return Clock.fixed(
                    Instant.parse("2030-01-15T10:00:00Z"),
                    ZoneOffset.UTC);
        }
    }
}
```

`@TestConfiguration` được thiết kế để bổ sung bean dành riêng cho test mà không biến class đó thành cấu hình chính được component scan thông thường tự động chọn. Một nested `@TestConfiguration` trong test được Spring Boot Test thêm vào application configuration.

Nếu dùng nested class có `@Configuration` thông thường, nó có thể được xem là cấu hình thay thế trong quá trình tìm cấu hình test tùy cách bootstrap. Khi muốn giữ cấu hình ứng dụng chính và thêm bean test, dùng `@TestConfiguration` hoặc `@Import(TestConfig.class)` để biểu đạt ý định rõ.

Một cách khai báo rõ ràng khác:

```java
@SpringBootTest(classes = {
        StoreApplication.class,
        PaymentGatewayTestConfiguration.class
})
class PaymentIntegrationTest {
}
```

Chỉ đưa cấu hình test vào khi cần thay đổi hành vi cụ thể. Nếu thay toàn bộ cấu hình chính bằng một class nhỏ, test có thể không còn kiểm tra auto-configuration và component scan mà ứng dụng thật sử dụng.

## Inline properties và command-line arguments

`@SpringBootTest` cho phép đặt properties riêng cho test:

```java
@SpringBootTest(properties = {
        "store.tax.enabled=false",
        "store.currency=VND",
        "spring.main.banner-mode=off"
})
class StoreConfigurationTest {
}
```

Thuộc tính `value` là alias của `properties`. Có thể dùng `args` để truyền command-line arguments cho `SpringApplication`:

```java
@SpringBootTest(args = {
        "--store.import.enabled=true",
        "--store.import.batch-size=50"
})
class ImportStartupIntegrationTest {

    @Autowired
    private ApplicationArguments applicationArguments;

    @Test
    void receivesBootCommandLineArguments() {
        assertThat(applicationArguments.getOptionNames())
                .contains("store.import.enabled", "store.import.batch-size");
    }
}
```

`properties` đặt giá trị trong Environment của test context. `args` mô phỏng tham số command line được truyền vào `SpringApplication`; các option dạng `--name=value` cũng có thể xuất hiện trong `ApplicationArguments`. Chọn `args` khi cần kiểm tra hành vi phụ thuộc command-line options, còn `properties` phù hợp để điều chỉnh cấu hình test.

Có thể dùng `@ActiveProfiles` để kích hoạt profile:

```java
@SpringBootTest
@ActiveProfiles("integration")
class IntegrationProfileTest {
}
```

Profile ảnh hưởng đến bean và file cấu hình được chọn. Hãy kiểm tra profile của test một cách tường minh, đặc biệt khi cấu hình local, CI và production khác nhau.

Với giá trị chỉ có sau khi tạo tài nguyên test, ví dụ URL của Testcontainers, dùng `@DynamicPropertySource`:

```java
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class DatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> database =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", database::getJdbcUrl);
        registry.add("spring.datasource.username", database::getUsername);
        registry.add("spring.datasource.password", database::getPassword);
    }
}
```

Đoạn ví dụ giả định dự án đã cấu hình Testcontainers và lifecycle container phù hợp. Dynamic properties được đăng ký để Spring đọc khi tạo context; chúng hữu ích khi giá trị cấu hình không thể biết trước lúc test khởi động.

## Phạm vi web được quyết định bởi webEnvironment

`@SpringBootTest` có thuộc tính `webEnvironment` để quyết định loại context và cách kiểm thử web. Mặc định là `MOCK`.

| Giá trị | Hành vi | Có embedded server không? |
|---|---|---|
| `MOCK` | Tạo mock web environment nếu ứng dụng có web stack phù hợp; không khởi động server thật | Không |
| `RANDOM_PORT` | Khởi động web server trên cổng ngẫu nhiên | Có |
| `DEFINED_PORT` | Khởi động web server trên cổng được cấu hình, hoặc cổng mặc định của server | Có |
| `NONE` | Tạo application context không phải web environment và đặt web application type thành `NONE` | Không |

### MOCK: context web mô phỏng

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class OrderMockMvcIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsOrder() throws Exception {
        mockMvc.perform(get("/api/orders/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42));
    }
}
```

`MOCK` không mở port và không gửi request qua network stack. `@AutoConfigureMockMvc` yêu cầu Spring Boot cấu hình `MockMvc` để gửi request qua `DispatcherServlet` và MVC infrastructure của context. Chỉ thêm `@SpringBootTest` không đồng nghĩa `MockMvc` luôn được tạo; cần annotation cấu hình MockMvc hoặc tự dựng nó.

Môi trường này phù hợp khi cần full Boot application context cùng khả năng kiểm thử MVC bằng mock servlet API. Nó không kiểm tra connector, TLS, socket hoặc hành vi riêng của servlet container.

### RANDOM_PORT: khởi động server trên cổng ngẫu nhiên

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @LocalServerPort
    private int port;

    @Autowired
    private TestRestTemplate restTemplate;

    @Test
    void servesOrderOverHttp() {
        ResponseEntity<OrderResponse> response = restTemplate.getForEntity(
                "http://localhost:" + port + "/api/orders/42",
                OrderResponse.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().id()).isEqualTo(42L);
    }
}
```

`RANDOM_PORT` khởi động embedded server trên cổng được hệ điều hành cấp. `@LocalServerPort` inject cổng thực tế để test gửi request đến server. Đây là cách kiểm tra HTTP qua network stack của server nhúng; nó phù hợp khi cần xác nhận cấu hình server, filter chain, serialization và các thành phần hoạt động qua HTTP thật trong test environment.

### DEFINED_PORT: dùng cổng cấu hình

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.DEFINED_PORT)
class FixedPortHttpTest {
}
```

`DEFINED_PORT` dùng `server.port` nếu được cấu hình; nếu không, server dùng cổng mặc định. Kiểu này hữu ích khi môi trường test cần một cổng đã biết, nhưng có nguy cơ xung đột khi nhiều test hoặc nhiều tiến trình chạy đồng thời. Nếu không có lý do cần cổng cố định, `RANDOM_PORT` thường cô lập tốt hơn.

### NONE: application context không phải web

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class BatchApplicationIntegrationTest {

    @Autowired
    private ImportService importService;

    @Test
    void loadsBatchServices() {
        assertThat(importService).isNotNull();
    }
}
```

`NONE` đặt web application type thành `WebApplicationType.NONE`, phù hợp với ứng dụng batch, command-line hoặc test service không cần web stack. Context vẫn được khởi tạo bằng Spring Boot; chỉ môi trường web được loại bỏ.

## Phân biệt full context với test slice

`@SpringBootTest` hướng đến việc nạp application context theo cấu hình Boot của ứng dụng. Test slice chỉ nạp một phần được chọn cho một tầng cụ thể, giúp test nhanh và tập trung hơn.

| Annotation | Phạm vi điển hình | Mục đích |
|---|---|---|
| `@SpringBootTest` | Application context theo cấu hình Boot | Kiểm thử tích hợp nhiều bean và auto-configuration |
| `@WebMvcTest` | MVC slice | Kiểm tra controller, mapping, converter, validation và advice trong web layer |
| `@DataJpaTest` | JPA slice | Kiểm tra entity, repository và cấu hình persistence liên quan |
| `@JsonTest` | JSON slice | Kiểm tra serialization/deserialization |
| `@RestClientTest` | REST client slice | Kiểm tra HTTP client và message conversion phía client |

Ví dụ, `@WebMvcTest(OrderController.class)` thường không nạp service/repository như một full application context; test có thể cung cấp mock cho dependency controller. Nếu cần xác nhận controller, service, repository và cấu hình ứng dụng phối hợp, dùng `@SpringBootTest` với web environment phù hợp.

Không phải mọi bài kiểm thử đều cần full context. Context đầy đủ có chi phí khởi tạo cao hơn và nhiều bean hơn, trong khi slice test thường nhanh hơn, ít phụ thuộc hạ tầng hơn và giúp xác định lỗi ở một tầng cụ thể.

## @SpringBootTest không tự động bao hàm mọi loại cấu hình kiểm thử

Một số annotation có vai trò riêng và có thể kết hợp với `@SpringBootTest`:

- `@AutoConfigureMockMvc`: cấu hình `MockMvc` trong mock web environment.
- `@AutoConfigureTestDatabase`: điều chỉnh database test cho một số cấu hình persistence.
- `@ActiveProfiles`: chọn profile.
- `@TestPropertySource`: nạp property source dành cho test.
- `@DynamicPropertySource`: đăng ký property động từ tài nguyên test.
- `@Import`: thêm cấu hình hoặc bean vào context.
- `@Transactional`: tạo test-managed transaction cho test method/class theo quy tắc Spring Test.

Không nên cho rằng `@SpringBootTest` tự động tạo database test, mock mọi external service, bật transaction cho test hoặc thay thế tất cả dependency bên ngoài. Những phần đó cần cấu hình riêng theo mục tiêu test.

## Test transaction và server thread

Nếu test method được đánh dấu `@Transactional`, Spring Test thường rollback test-managed transaction khi test kết thúc. Điều này hữu ích cho repository/service test chạy trong cùng transaction của test thread.

Với `RANDOM_PORT` hoặc `DEFINED_PORT`, request HTTP được xử lý trên thread của embedded server. Transaction của request đó là transaction riêng, không tham gia transaction test thread. Vì vậy, rollback test-managed transaction không tự động hoàn tác dữ liệu mà server đã commit trong lúc xử lý request.

Khi test qua HTTP thật, cần dọn dữ liệu đã tạo bằng cách riêng: xóa qua repository/JDBC trong cleanup, dùng database/schema riêng cho test hoặc khởi tạo lại container/database theo chiến lược của suite. Đừng dựa vào `@Transactional` trên test để cô lập side effect của request được xử lý ở server thread.

## Context caching và chi phí khởi tạo

Spring TestContext cache application context để các test có cùng cấu hình có thể dùng lại context đã tạo. `@SpringBootTest` có thể mất thời gian khởi động vì phải nạp nhiều bean, auto-configuration, connection pool và các thành phần hạ tầng.

Các khác biệt về cấu hình như classes, active profiles, property sources, context customizers và web environment có thể tạo cache key khác nhau. Nếu mỗi test khai báo một tập properties hoặc cấu hình riêng, số context được tạo có thể tăng đáng kể.

`@DirtiesContext` yêu cầu Spring loại context khỏi cache và đóng nó sau thời điểm được chỉ định. Chỉ dùng khi test thực sự làm thay đổi trạng thái singleton/context không thể khôi phục; lạm dụng annotation này làm suite chậm vì context phải khởi tạo lại.

Với test cần dùng chung context, hãy gom các cấu hình tương thích, giữ dữ liệu test độc lập và dọn trạng thái mutable sau mỗi test. Nếu một test thay đổi singleton bean hoặc cấu hình context theo cách không thể khôi phục, khi đó mới cân nhắc `@DirtiesContext`.

## `useMainMethod` và phương thức main của ứng dụng

Theo mặc định, Spring Boot Test tạo ứng dụng bằng `SpringApplication` mà không gọi phương thức `main` của class ứng dụng. Nếu phương thức `main` có logic tùy chỉnh cần được kiểm tra, có thể chọn chính sách `useMainMethod`:

```java
@SpringBootTest(useMainMethod = SpringBootTest.UseMainMethod.ALWAYS)
class MainMethodIntegrationTest {
}
```

Các lựa chọn gồm `NEVER`, `WHEN_AVAILABLE` và `ALWAYS`. Dùng `ALWAYS` khi test cần thực thi main method; `WHEN_AVAILABLE` cho phép gọi nếu có phương thức main phù hợp; `NEVER` giữ hành vi khởi tạo trực tiếp mà không gọi main. Đây là tùy chọn nâng cao; phần lớn test chỉ cần khởi động application context nên có thể dùng mặc định.

## Khi nào nên dùng @SpringBootTest?

Dùng `@SpringBootTest` khi câu hỏi kiểm thử liên quan đến sự phối hợp giữa nhiều bean hoặc cấu hình thực tế của ứng dụng: service gọi repository, security và MVC cùng hoạt động, auto-configuration tạo đúng client, hoặc ứng dụng có thể khởi động trong một môi trường cụ thể.

Chọn web environment theo đường đi request cần kiểm tra:

| Nhu cầu | Cấu hình phù hợp |
|---|---|
| Full context nhưng không cần server | `@SpringBootTest(webEnvironment = NONE)` |
| Full context và request qua mock servlet | `@SpringBootTest` + `@AutoConfigureMockMvc` |
| Kiểm tra HTTP qua embedded server | `@SpringBootTest(webEnvironment = RANDOM_PORT)` |
| Cần cổng cố định do môi trường yêu cầu | `@SpringBootTest(webEnvironment = DEFINED_PORT)` |
| Chỉ kiểm tra một tầng web hoặc persistence | Test slice tương ứng như `@WebMvcTest` hoặc `@DataJpaTest` |

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy `@SpringBootConfiguration` | Test nằm ngoài package tree của class ứng dụng hoặc dự án có nhiều cấu hình | Chỉ rõ `classes = StoreApplication.class` |
| Context khởi động nhưng thiếu bean | Bean không được scan/import, profile không đúng hoặc điều kiện auto-config không thỏa | Kiểm tra component scan, `@Import`, active profiles và properties |
| Test quá chậm | Mỗi test tạo một full context khác nhau hoặc khởi động server/container không cần thiết | Tái sử dụng cấu hình context và dùng slice test khi phù hợp |
| Không inject được `MockMvc` | Chỉ dùng `@SpringBootTest` mà chưa cấu hình MockMvc | Thêm `@AutoConfigureMockMvc` hoặc dựng MockMvc thủ công |
| Request không đến server | Dùng `MOCK` nhưng test gọi HTTP client qua port | Chuyển sang `RANDOM_PORT`/`DEFINED_PORT` hoặc dùng MockMvc |
| Port bị chiếm | Dùng `DEFINED_PORT` với nhiều tiến trình/test | Dùng `RANDOM_PORT` nếu không cần port cố định |
| Dữ liệu vẫn còn sau test HTTP | Transaction test không bao phủ transaction của server thread | Cleanup riêng hoặc cô lập database/schema |
| Test profile chạy khác local | Profile/property nguồn khác nhau giữa môi trường | Khai báo `@ActiveProfiles` và test properties rõ ràng |
| Context bị khởi tạo lại liên tục | Cache key khác nhau hoặc dùng `@DirtiesContext` quá nhiều | Chuẩn hóa cấu hình test và chỉ đánh dấu context dirty khi cần |

`@SpringBootTest` là cầu nối từ Spring TestContext sang cách Spring Boot khởi động ứng dụng. Hiểu rõ class cấu hình được chọn, các nguồn property, profile và `webEnvironment` giúp xác định chính xác context nào đang được kiểm thử. Khi cần xác nhận ứng dụng phối hợp như một chỉnh thể, full Boot context là lựa chọn phù hợp; khi chỉ cần kiểm tra một tầng, test slice giữ phạm vi nhỏ và tốc độ tốt hơn.
