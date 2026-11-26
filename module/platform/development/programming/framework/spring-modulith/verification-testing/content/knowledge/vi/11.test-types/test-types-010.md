# Chi phí khởi động context ở từng loại test

> **Chương:** Test types  
> **Module học:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Trọng tâm:** Đánh giá chi phí khởi tạo Spring TestContext theo từng loại test, lựa chọn phạm vi kiểm thử cho Spring Modulith và tối ưu thời gian CI mà không đánh mất bằng chứng về dependency, database, event hay giao tiếp giữa module.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **khởi động JVM/test engine**, **tạo Spring ApplicationContext**, **chuẩn bị database/container** và **thực thi bài test**.
2. Giải thích vì sao unit test không khởi tạo Spring nhanh hơn về chi phí môi trường, còn slice/module/integration/E2E test tạo những context có phạm vi khác nhau.
3. Lựa chọn `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@ApplicationModuleTest`, `@SpringBootTest` hoặc architectural test theo **bằng chứng cần thu**, không chỉ theo thời gian chạy.
4. Dự đoán tác động của `BootstrapMode.STANDALONE`, `DIRECT_DEPENDENCIES` và `ALL_DEPENDENCIES` trong Spring Modulith.
5. Hiểu và quan sát **Spring TestContext cache**: cache key, hit/miss, eviction, `@DirtiesContext`, test profiles và bean overrides.
6. Thiết kế phép đo *cold/warm*, tách độ trễ container và build overhead, tránh kết luận bằng một lần chạy đơn lẻ.
7. Xây dựng quality gate CI có nhiều lớp kiểm thử, phân bổ chi phí phù hợp với rủi ro kiến trúc và hành vi.

**Thông điệp quan trọng:** Test nhỏ thường cho phản hồi nhanh hơn, nhưng **nhanh không đồng nghĩa đủ bằng chứng**. Nếu cần chứng minh listener xử lý sự kiện sau commit hay PostgreSQL unique constraint hoạt động, không thể thay bằng mock chỉ để giảm vài giây khởi động.

## 2. Chi phí nào thực sự được gọi là “khởi động context”?

Trong JUnit/Spring Test, thời gian toàn bộ suite có nhiều thành phần:

~~~mermaid
flowchart LR
    J["Khởi động JVM<br/>Gradle/JUnit"] --> C["Tạo hoặc lấy lại<br/>ApplicationContext"]
    C --> B["Khởi tạo bean,<br/>proxy, auto-config"]
    B --> D["Database/container,<br/>schema, migration"]
    D --> T["Chạy từng test method"]
    T --> X["Cleanup/teardown"]
~~~

Sơ đồ là cách phân rã khái niệm; **các bước thực tế có thể đan xen**. Ví dụ container có thể bắt đầu trước khi context yêu cầu datasource, và migration có thể chạy trong lúc context khởi tạo.

Có thể mô hình hóa tổng thời gian gần đúng:

\[
T_{\text{suite}} \approx T_{\text{JVM/engine}} + \sum_{c \in C_{\text{unique}}} T_{\text{context},c} + T_{\text{external infrastructure}} + \sum_{i=1}^{n} T_{\text{test},i} + T_{\text{cleanup}}
\]

Trong đó:

- `C_unique` là tập những **Spring test context khác nhau phải tạo** trong một tiến trình test, không nhất thiết bằng số class.
- `T_context,c` bao gồm tìm cấu hình, component scanning, auto-configuration, tạo bean, proxy và những bước được kích hoạt trong quá trình refresh context.
- `T_external infrastructure` bao gồm khởi chạy PostgreSQL/Kafka/Testcontainers hoặc hạ tầng test khác; một phần thời gian này có thể trùng lặp với `T_context,c` khi đo theo wall-clock, nên **không cộng thô số liệu log**.
- `T_test,i` là thời gian thực thi fixture, assertion, HTTP call, chờ event, transaction và database query của từng test.
- `T_cleanup` bao gồm dọn dữ liệu, đóng tài nguyên và dừng container khi cần.

Mô hình trên giúp suy luận, **không phải công thức đo thời gian chính xác**. Cách đo theo thời gian thực tế vẫn phải ghi lại điểm bắt đầu/kết thúc và các điều kiện môi trường.

### Cold start và warm start

**Cold start:** Một context chưa có trong Spring TestContext cache của tiến trình; framework phải tạo và refresh context.

**Warm reuse:** Một test khác yêu cầu đúng cấu hình đã cache và context chưa bị invalidated/evicted; framework có thể tái sử dụng context, nên không trả lại toàn bộ chi phí khởi tạo.

Vì vậy, nhận định “mỗi `@SpringBootTest` tốn một lần khởi động ứng dụng” **không luôn đúng**. Hai class test có cùng cache key trong cùng JVM có thể dùng chung context. Ngược lại, mười class test trông gần giống nhau nhưng có `@ActiveProfiles` hoặc `@MockitoBean` khác nhau có thể làm sinh nhiều context.

## 3. Đừng gán một con số cố định cho từng annotation

Thời gian khởi động chịu ảnh hưởng từ:

- Số bean được đưa vào context, auto-configuration và component scanning.
- Số application module/dependency thực sự được bootstrap.
- Flyway/Liquibase migration, JPA entity scanning, Hibernate metadata và query validation.
- Kết nối database, pool connection, network, DNS, TLS và dịch vụ ngoài nếu có.
- Cấu hình Spring Security, messaging, scheduling, async executor.
- Máy developer so với CI, CPU/RAM, filesystem, cache, I/O và container image.
- Version Spring Boot/Spring Modulith/JDK; AOT hay native image nếu dự án sử dụng.
- Spring TestContext cache hit/miss, số JVM fork, số class và thứ tự chạy test.

Do đó, bảng so sánh dưới đây chỉ dùng **mức chi phí tương đối**, không phải lời hứa test sẽ hoàn tất trong một số mili giây cụ thể.

| Loại test | Có Spring ApplicationContext? | Mức chi phí khởi tạo thường thấy | Bằng chứng chính |
| --- | --- | --- | --- |
| **Unit test thuần Java** | Không | Thấp nhất về context | Thuật toán, validation, domain rule |
| **Architectural test `ApplicationModules.verify()`** | Không cần Spring context | Thấp đến vừa do phân tích class/module | Package API, vòng và whitelist dependency |
| **`@JsonTest`** | Có, slice hẹp | Thường thấp | Jackson serialization/deserialization |
| **`@WebMvcTest`** | Có, web slice | Thấp đến vừa | Controller, MVC mapping, validation, security slice |
| **`@DataJpaTest`** | Có, persistence slice | Vừa; có thể tăng do JPA/schema/database | Repository, entity mapping, query |
| **`@RestClientTest`** | Có, client slice | Thường thấp đến vừa | HTTP client adapter và mapping |
| **`@ApplicationModuleTest(STANDALONE)`** | Có, theo module | Phụ thuộc quy mô module và auto-config | Service, wiring, transaction, event, persistence của module |
| **`@ApplicationModuleTest(DIRECT_DEPENDENCIES)`** | Có, module + dependency trực tiếp | Có thể lớn hơn `STANDALONE` | Hành vi kết hợp dependency trực tiếp |
| **`@ApplicationModuleTest(ALL_DEPENDENCIES)`** | Có, thêm dependency bắc cầu | Có thể lớn hơn hai mode trên | Luồng cần chuỗi dependency |
| **`@SpringBootTest(webEnvironment = NONE)`** | Có, toàn ứng dụng | Thường lớn hơn slice | Logic tích hợp nhiều module, không mở server |
| **`@SpringBootTest(RANDOM_PORT)`** | Có, toàn ứng dụng + HTTP server thật | Thường cao hơn `NONE` | Request/response qua mạng và luồng API |
| **Test có Testcontainers/broker** | Tùy annotation nền | Có chi phí hạ tầng bổ sung đáng kể | Hành vi với engine/dịch vụ thật trong phạm vi test |

**Không suy diễn thứ tự tuyệt đối:** Một `@DataJpaTest` chạy migration lớn với database ngoài có thể chậm hơn `@SpringBootTest` đơn giản có context đã cache. Một `@ApplicationModuleTest` có JPA và nhiều dependency cũng không mặc nhiên rẻ hơn mọi `@SpringBootTest`.

## 4. Unit test: loại bỏ hẳn chi phí Spring context khi không cần

Giả sử domain có quy tắc tính tổng tiền:

~~~java
package com.acme.shop.orders.internal.domain;

import java.math.BigDecimal;

public final class OrderTotalCalculator {

    public BigDecimal calculate(
            BigDecimal unitPrice, int quantity) {

        if (unitPrice == null || unitPrice.signum() < 0
                || quantity <= 0) {
            throw new IllegalArgumentException("Invalid order line");
        }

        return unitPrice.multiply(
                BigDecimal.valueOf(quantity));
    }
}
~~~

Một JUnit test tương ứng:

~~~java
package com.acme.shop.orders.internal.domain;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class OrderTotalCalculatorTest {

    @Test
    void multiplies_price_without_floating_point_error() {
        var calculator = new OrderTotalCalculator();

        var result = calculator.calculate(
                new BigDecimal("19.99"), 3);

        assertThat(result)
                .isEqualByComparingTo("59.97");
    }
}
~~~

Không có `@SpringBootTest`, `@ExtendWith(SpringExtension.class)` hay bean injection. JUnit vẫn cần engine/JVM, nhưng **không có chi phí tạo Spring ApplicationContext**.

**Bằng chứng đủ:** Phép tính số thập phân trả đúng kết quả cho input đã thử.

**Bằng chứng còn thiếu:** Service có thực sự dùng calculator này, cấu hình transaction có đúng, dữ liệu đi qua repository hoặc HTTP có bị sửa sai không. Những mệnh đề ấy cần test ở cấp cao hơn.

### Sai lầm hiệu năng phổ biến

~~~java
@SpringBootTest
class OrderTotalCalculatorTest {
    // Chỉ new OrderTotalCalculator() và gọi calculate(...)
}
~~~

Nếu test không dùng Spring, annotation này chỉ làm context phải khởi tạo hoặc lấy cache, tăng chi phí mà **không tăng bằng chứng** về phép tính. Bỏ annotation là một tối ưu đúng vì không đánh mất hành vi cần kiểm tra.

## 5. Slice test: chỉ khởi tạo phần hạ tầng thuộc hợp đồng

Spring Boot cung cấp các test slice giới hạn bean và auto-configuration theo mục tiêu. Chúng thường khởi tạo nhanh hơn context đầy đủ, nhưng không phải “unit test không Spring”.

### 5.1. Web slice với @WebMvcTest

~~~java
package com.acme.shop.orders.internal.web;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import com.acme.shop.orders.OrderManagement;

@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    OrderManagement orders;

    @Test
    void rejects_missing_customer_id() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"customerId":"","amount":25.00}
                        """))
                .andExpect(status().isBadRequest());
    }
}
~~~

Đây là **trích đoạn phụ thuộc vào `OrderController` có `@Valid` và request DTO phù hợp**, không phải ứng dụng hoàn chỉnh. `@MockitoBean` có từ Spring Framework 6.2 (thường Spring Boot 3.4+); Boot cũ hơn có thể dùng `@MockBean`. Chọn đúng API cho version của dự án.

**Vì sao slice nhanh hơn?** Không bắt buộc tạo mọi service, repository và module khác. Test quan sát request mapping, JSON, validation, MVC infrastructure và những security filter được nạp trong slice.

**Không chứng minh:** JPA repository và consumer của `OrderPlaced` hoạt động. Dùng mock `OrderManagement` trong web slice là hợp lý **vì hợp đồng đang kiểm tra là controller**, không phải service.

### 5.2. JPA slice với @DataJpaTest

~~~java
package com.acme.shop.orders.internal.persistence;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;

    @Test
    void persists_and_queries_an_order() {
        var saved = repository.save(
                new OrderEntity("CUS-1"));

        repository.flush();

        assertThat(repository.findById(saved.getId()))
                .isPresent();
    }
}
~~~

Trích đoạn giả định `OrderEntity` có constructor `OrderEntity(String customerId)` và repository dùng JPA. `@DataJpaTest` có thể cấu hình transaction rollback mặc định và embedded datasource nếu phù hợp. **Chi phí** gồm tạo phần persistence context, DataSource/JPA metadata và database/schema. Với nhiều entity, migration hoặc database thật, slice có thể khởi tạo chậm hơn dự đoán.

**Không chứng minh:** HTTP endpoint hoạt động hoặc transaction hoàn tất ngoài transaction rollback của test. Nếu cần kiểm tra native SQL/locking theo PostgreSQL production, thay database thử nghiệm bằng PostgreSQL Testcontainers phù hợp.

### 5.3. JSON/client slices

`@JsonTest` chỉ cần serialization/deserialization và cấu hình mapper liên quan; `@RestClientTest` nhắm tới adapter gọi HTTP ra ngoài với mock server. Hai loại test này thường không cần tạo toàn bộ Spring Modulith application. Tuy nhiên, một client adapter có OAuth, SSL hoặc custom configuration phức tạp có thể vẫn có chi phí đáng kể.

**Nguyên tắc chọn slice:** Giữ hạ tầng **quyết định câu trả lời của assertion** là thật; các thành phần nằm ngoài ranh giới đó có thể được thay bằng fake/mock.

## 6. @ApplicationModuleTest: chi phí phụ thuộc module và bootstrap mode

Với Spring Modulith, `@ApplicationModuleTest` khởi tạo context cho module gắn với package test, có thể thêm các module dependency theo mode. Nó thường là lựa chọn cân bằng giữa unit/slice test và tích hợp toàn ứng dụng.

Ví dụ cấu trúc:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders/
│   ├── OrderManagement.java             # API công khai
│   ├── OrderPlaced.java                 # event công khai
│   └── internal/
│       ├── OrderApplicationService.java
│       └── persistence/OrderRepository.java
├── inventory/
│   └── StockAvailability.java          # API công khai
└── fulfillment/
    └── internal/OrderPlacedListener.java
~~~

Test đặt trong package `com.acme.shop.orders`:

~~~java
package com.acme.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class OrdersModuleTest {

    @Autowired
    OrderManagement orders;

    @Test
    void creates_order_through_module_api() {
        long id = orders.placeOrder("CUS-100");

        assertThat(id).isPositive();
    }
}
~~~

Đây là **khung minh họa**: `OrderManagement.placeOrder` và persistence/test datasource phải có implementation đúng với dự án. Nếu chỉ cần assert `id > 0`, bằng chứng còn yếu; bài test hoàn chỉnh nên đọc lại trạng thái qua API module và kiểm tra event khi hợp đồng yêu cầu.

### 6.1. Ba chế độ bootstrap

| Mode | Phạm vi application module | Tác động chi phí và bằng chứng |
| --- | --- | --- |
| `STANDALONE` (mặc định) | Module chứa test | Thường ít bean ứng dụng hơn; phù hợp module hoạt động độc lập hoặc dependency ngoài biên được cấp có chủ đích |
| `DIRECT_DEPENDENCIES` | Module chứa test và những module mà nó phụ thuộc trực tiếp | Tăng phạm vi để kiểm tra bean thật ở dependency trực tiếp |
| `ALL_DEPENDENCIES` | Module chứa test và chuỗi dependency bắc cầu | Context lớn hơn; chỉ dùng khi hợp đồng thực sự cần cây dependency |

Ví dụ khai báo:

~~~java
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;

@ApplicationModuleTest(mode = BootstrapMode.DIRECT_DEPENDENCIES)
class OrdersWithInventoryTest {
    // Đặt dưới package orders, kiểm tra luồng cần inventory thật.
}
~~~

Việc nạp nhiều module hơn **thường** làm tăng số bean và chi phí, nhưng không có thứ tự tuyệt đối vì auto-configuration, context caching và hạ tầng đi kèm. Một class `STANDALONE` phải tạo context lạnh trong khi `DIRECT_DEPENDENCIES` dùng context đã cache có thể hoàn thành nhanh hơn tại một lần đo cụ thể.

### 6.2. Chiều dependency không trùng chiều event runtime

Nếu `fulfillment` import kiểu `orders.OrderPlaced`, dependency tĩnh là `fulfillment → orders`. Test đặt trong `orders` với `DIRECT_DEPENDENCIES` không tự nạp `fulfillment`, vì fulfillment là **consumer phụ thuộc vào orders**, không phải dependency của orders.

Để chứng minh consumer xử lý thành công, hãy dùng test đặt trong `fulfillment` với mode phù hợp hoặc integration test bao gồm cả hai module. **Không tối ưu context bằng cách vô tình loại bean cần có để thu bằng chứng.**

### 6.3. Không phải mọi chi phí chỉ đến từ số module

Một module duy nhất nhưng dùng JPA, Flyway, Kafka adapter hoặc remote client vẫn có thể nạp hạ tầng nặng. Ngược lại nhiều module nhỏ thuần Java không nhất thiết làm context nặng tương đương. Hãy đo số context thực, bean được nạp, auto-configuration và các tài nguyên khởi tạo thay vì chỉ đếm package.

## 7. Architectural test: kiểm chứng cấu trúc mà không bootstrap Spring

Để bắt phụ thuộc sai giữa module, **không cần Spring ApplicationContext**.

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureVerificationTest {

    @Test
    void module_dependencies_are_valid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`ApplicationModules.verify()` xác minh các quy tắc kiến trúc theo mô hình Spring Modulith, bao gồm vòng phụ thuộc, truy cập ngoài API module và giới hạn dependency được khai báo nếu có.

Chi phí ở đây chủ yếu là **phân tích class/package và dependency graph**, không phải tạo bean, mở datasource hay chạy servlet container. Test này thường là ứng viên tốt cho quality gate chạy trên mọi pull request.

**Bằng chứng thu được:** Module `orders` không import implementation nội bộ của `inventory`, quan hệ dependency theo cấu hình hợp lệ.

**Không chứng minh:** Application context khởi động thành công; service được inject; SQL đúng; listener sau commit chạy. Architecture test rất nhanh không thể thay thế những bài kiểm thử cần runtime.

### Tối ưu sai cần tránh

Nếu xóa `ApplicationModules.verify()` để tiết kiệm thời gian nhưng vẫn giữ E2E test, một import sai tới `inventory.internal` vẫn có thể compile và E2E xanh. Việc bỏ architectural test làm **mất bằng chứng về ranh giới module** mà không chắc tiết kiệm đáng kể.

## 8. @SpringBootTest: toàn bộ ứng dụng và HTTP server

### 8.1. Không mở HTTP server nếu mục tiêu không cần HTTP

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class OrdersFulfillmentIntegrationTest {
    // Inject các API module và kiểm tra event/DB.
}
~~~

`NONE` cho phép kiểm tra nhiều bean/module trong context của ứng dụng mà **không khởi động embedded HTTP server**. Đây là lựa chọn khi điểm quan sát là API Java và trạng thái trong database sau event.

`WebEnvironment.MOCK` (mặc định của `@SpringBootTest`) chuẩn bị mock web environment khi phù hợp nhưng không mở server trên cổng mạng. Nó không tương đương `RANDOM_PORT`. Nếu không cần MVC/web, `NONE` giúp bỏ phần hạ tầng web không cần thiết.

### 8.2. RANDOM_PORT khi HTTP thật thuộc bằng chứng

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpE2ETest {
    // Gửi HTTP request qua TestRestTemplate hoặc WebTestClient
    // tùy loại ứng dụng và thư viện.
}
~~~

`RANDOM_PORT` khởi động embedded server trên một cổng ngẫu nhiên; test gửi request qua giao thức HTTP thật. Đây là phạm vi phù hợp khi muốn xác nhận routing, Jackson, validation, filters/security và toàn bộ đường đi từ HTTP entry point đến kết quả.

**Chi phí bổ sung** có thể gồm server startup, bind port, web infrastructure và network calls. Tuy nhiên E2E test còn có thể đợi event, database và dịch vụ ngoài — phần lớn thời gian đó **không phải khởi động context**.

### 8.3. Giá trị của test context tải toàn ứng dụng

Một bài `contextLoads` có thể phát hiện ứng dụng không bootstrap được; đó là một bằng chứng hữu ích trong một số tình huống. Nhưng tạo hàng chục class `@SpringBootTest` riêng chỉ để lặp lại cùng assertion “context loads” thường gây chi phí trùng, nhất là nếu mỗi class khác cấu hình, profile hoặc mock.

**Không thay mọi test bằng full context:** Test logic Java vẫn nên là unit test; controller validation nên là web slice khi không cần tầng sâu; module-level wiring nên là `@ApplicationModuleTest` khi đủ phạm vi.

## 9. Testcontainers và database: chi phí hạ tầng không đồng nhất với context

Testcontainers thường làm test chạy lâu hơn do pull image (lần đầu), khởi động container, chờ readiness, mở kết nối và chạy migration. **Đó là chi phí hạ tầng test**, cần phân biệt với Spring context cache.

Ví dụ khung với PostgreSQL:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class OrdersPostgresIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void persists_with_postgres() {
        // Inject API module, ghi/đọc dữ liệu rồi assert.
    }
}
~~~

Đây là khung cấu hình, không phải một test hoàn chỉnh. Cần dependencies Testcontainers Jupiter/PostgreSQL, Spring Boot Testcontainers, JDBC driver và runtime container. `@ServiceConnection` có trong Spring Boot hiện đại (từ Boot 3.1), cần dùng phiên bản tương thích.

### 9.1. Một lần tạo context không đồng nghĩa một lần tạo container

Hai cơ chế tái sử dụng khác nhau:

- **Spring TestContext cache:** lưu các `ApplicationContext` theo cấu hình trong một JVM test.
- **Testcontainers lifecycle:** quản lý container theo khai báo và vòng đời do Testcontainers/Test framework điều khiển.

Không được mặc định rằng context cache sẽ giữ container sống, hoặc container đang sống sẽ khiến context tự được tái sử dụng. Nếu dùng `@Container` static trong từng test class, container thường sống trong vòng đời class đó. **Cảnh báo:** Khi nhiều test class dùng cùng một cached Spring context nhưng container của class trước đã bị dừng, datasource có thể trỏ tới container không còn tồn tại. Cần thống nhất lifecycle container và context; có thể chọn singleton-container pattern hoặc cấu trúc fixture dùng chung được quản lý rõ ràng, thay vì pha trộn vòng đời một cách ngẫu nhiên.

### 9.2. Khi nào chi phí hạ tầng là cần thiết?

| Claim | Hạ tầng hợp lý | Lý do |
| --- | --- | --- |
| Nhân `BigDecimal` đúng | Không cần DB | DB không thuộc claim |
| Controller trả `400` cho request sai | MockMvc web slice | Không cần DB nếu validation nằm ở web |
| Repository chạy native PostgreSQL JSONB query | PostgreSQL Testcontainers | H2 có thể khác dialect |
| Event consumer ghi task sau commit | Database thật/test DB phù hợp | Cần transaction và state quan sát được |
| Event publication sống qua restart | Durable registry và restart scenario | In-memory event không đủ |
| HTTP request được route đúng qua port | `RANDOM_PORT` | Cần embedded server thật |

**Không dùng database thật chỉ để chứng minh một phép tính**, và cũng **không mock database** khi cần kiểm tra SQL, constraint hoặc transaction thật.

## 10. Spring TestContext cache: “đòn bẩy” quan trọng nhất của suite

Spring TestContext Framework có cache tĩnh cho `ApplicationContext` trong phạm vi tiến trình test phù hợp. Mục tiêu là tránh khởi động lại cùng một cấu hình context cho mỗi test class.

~~~mermaid
flowchart TD
    A["JUnit test class"] --> K["Tạo cache key từ cấu hình test"]
    K --> H{"Có context trong cache?"}
    H -- "Hit" --> R["Dùng lại ApplicationContext"]
    H -- "Miss" --> N["Khởi tạo và cache context mới"]
    N --> R
    R --> T["Chạy test methods"]
    T --> D{"@DirtiesContext hoặc eviction?"}
    D -- "Có" --> X["Đóng/loại context khi phù hợp"]
    D -- "Không" --> P["Giữ context để tái sử dụng"]
~~~

### 10.1. Những yếu tố có thể tạo cache key khác nhau

Theo Spring TestContext Framework, cache key được xác định bởi cấu hình test, gồm những yếu tố như:

- `@ContextConfiguration`: classes, locations, context initializer, loader, parent.
- Các **context customizer**, bao gồm bean overrides như `@MockitoBean` / `@MockBean`, `@DynamicPropertySource` và các cấu hình test tích hợp khác.
- `@ActiveProfiles`.
- `@TestPropertySource`: property sources và các thuộc tính inline.
- `@WebAppConfiguration`: resource base path khi áp dụng.

Vì vậy, hai test class khác nhau vẫn **có thể cache hit** nếu cấu hình thực tế giống nhau. Nhưng một profile thêm vào, một mock bean khác tên/kiểu, hoặc thay đổi property có thể tạo context thứ hai.

**Không được kết luận “hai lớp có cùng annotation là có cùng cache key”.** Trong Spring Modulith, phạm vi module và bootstrap mode còn ảnh hưởng cách context được cấu hình. Hãy xem thống kê cache thay vì đoán chỉ từ dòng `@ApplicationModuleTest`.

### 10.2. Ví dụ gây cache fragmentation

~~~java
@SpringBootTest(properties = "feature.shipping=false")
class OrdersFeatureOffTest {
    // Context cấu hình A
}

@SpringBootTest(properties = "feature.shipping=true")
class OrdersFeatureOnTest {
    // Context cấu hình B: khác inline property
}
~~~

Hai cấu hình này phục vụ **hai mệnh đề khác nhau** nên việc có hai context là hợp lý. Nhưng nếu mỗi test class dùng một tập property hoặc mock không cần thiết, suite sẽ tạo nhiều context chỉ vì cách viết test.

Ví dụ khác:

~~~java
@ActiveProfiles("test")
@SpringBootTest
class OrdersTestA {
}

@ActiveProfiles({"test", "integration"})
@SpringBootTest
class OrdersTestB {
}
~~~

Khác active profiles có thể tạo cache key khác nhau. Hãy chuẩn hóa profile và test properties khi mục tiêu giống nhau; **không gộp context** nếu việc đó làm mất phân biệt hành vi cần chứng minh.

### 10.3. @DirtiesContext: chỉ dùng khi context thực sự bị “bẩn”

`@DirtiesContext` báo Spring TestContext không tái sử dụng context theo semantics của annotation, khiến context phải được loại bỏ/đóng và có thể phải khởi tạo lại.

~~~java
import org.springframework.test.annotation.DirtiesContext;

@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest
class MutatesGlobalBeanConfigurationTest {
    // Ví dụ chỉ khi test thực sự làm context không an toàn để dùng lại.
}
~~~

Dùng `@DirtiesContext` để “dọn database sau mỗi test” thường là giải pháp đắt và sai trọng tâm. **Dữ liệu test** có thể dọn bằng transaction rollback phù hợp, fixture độc lập, truncate có kiểm soát hoặc schema riêng; **Spring context** không nhất thiết phải bị xóa.

Một số test event sau commit **không nên** dùng rollback ở test method vì listener chỉ chạy sau commit. Trong trường hợp đó, hãy thiết kế dữ liệu unique, cleanup theo hợp đồng và cơ chế cô lập phù hợp thay vì bật `@Transactional` hoặc `@DirtiesContext` một cách máy móc.

### 10.4. Cache size, eviction và JVM forks

Spring TestContext cache có kích thước tối đa mặc định **32 context** và dùng cơ chế eviction khi vượt giới hạn. Có thể cấu hình qua system property `spring.test.context.cache.maxSize`, chẳng hạn khi thực sự quan sát thấy nhiều context hợp lệ bị evict.

Ví dụ truyền property vào JVM chạy Gradle test:

~~~kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    systemProperty("spring.test.context.cache.maxSize", "64")
}
~~~

**Cẩn trọng:** Tăng cache size có thể tăng mức giữ bộ nhớ vì nhiều context còn sống. Nó không tự làm test nhanh hơn nếu bộ nhớ CI không đủ hoặc test bị chậm do database. Thay đổi chỉ nên dựa trên thống kê cache hit/miss, eviction và RAM.

Context cache là **static trong tiến trình**. Nếu build chạy nhiều JVM test worker/fork, những tiến trình đó không cùng chia sẻ cache. Việc chia test thành nhiều job/machine cũng làm cache tách biệt. Tăng `maxParallelForks` có thể rút ngắn wall-clock khi hạ tầng đủ, nhưng cũng tăng số context được khởi tạo song song và áp lực tài nguyên.

## 11. Đo cache hit/miss thay vì suy đoán

Có thể bật DEBUG cho Spring TestContext cache để xem các thống kê như kích thước cache, số hit và miss.

Ví dụ cấu hình logging test:

~~~properties
# src/test/resources/application-test.properties (minh họa)
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Hoặc cấu hình logging tương ứng trong Logback/test runner, bảo đảm cấu hình được áp dụng từ giai đoạn TestContext hoạt động. Các log cụ thể thay đổi theo phiên bản Spring; không dựa cứng vào đúng một chuỗi output.

### Những tín hiệu cần ghi lại

| Số liệu | Ý nghĩa | Cách diễn giải |
| --- | --- | --- |
| **Cache hit count** | Số lần yêu cầu context tìm thấy context có thể dùng lại | Nhiều hit thường tích cực, nhưng không tự nói test đủ bằng chứng |
| **Cache miss count** | Số lần cần tạo mới theo key chưa có/không còn | Miss tăng nhanh có thể do cấu hình phân mảnh |
| **Cache size** | Số context đang giữ | So với giới hạn và RAM |
| **Eviction/close** | Context bị loại hoặc đóng | Xem `@DirtiesContext`, cache cap và lifecycle |
| **Spring startup log** | Context/application startup tương ứng | Dùng để phân tích tương đối, không đồng nhất với tổng test |
| **Suite wall-clock** | Người dùng/CI phải chờ bao lâu | Bao gồm JVM, build overhead, container và method |

Một số log DEBUG rất nhiều dòng. Chỉ bật khi cần chẩn đoán hoặc trong job đo hiệu năng; không nhất thiết để mức DEBUG trong mọi CI run vì log volume cũng có chi phí.

## 12. Phép đo công bằng: cold, warm và tầng chi phí

Để so sánh hai lựa chọn test, phải chạy **cùng môi trường** và ghi điều kiện thí nghiệm.

### 12.1. Thí nghiệm ba lớp

**Lớp A — Cold isolated:** Chạy riêng một test class trong tiến trình JVM mới; ghi wall-clock và startup information. Điều này ước lượng cái giá “khởi tạo lần đầu” bao gồm overhead test runner.

**Lớp B — Warm context reuse:** Chạy nhiều class với **cấu hình context tương thích** trong cùng test process; xem cache hit/miss và tổng suite time. Điều này phản ánh lợi ích reuse.

**Lớp C — Full CI representative:** Chạy suite theo cách CI chạy thật, kể cả Testcontainers, migration, test fork và parallel settings. Đây là con số quan trọng cho quyết định quality gate.

Ví dụ Gradle (không chạy các lệnh này trong bài học):

~~~bash
# Một class test: dùng để so sánh tương đối.
./gradlew test --tests "com.acme.shop.orders.OrdersModuleTest" --rerun-tasks

# Một class architecture test không cần Spring context.
./gradlew test --tests "com.acme.shop.ArchitectureVerificationTest" --rerun-tasks

# Toàn bộ suite sau khi đã cấu hình Gradle test task.
./gradlew test --rerun-tasks
~~~

`--rerun-tasks` yêu cầu Gradle chạy lại task thay vì dùng task output đã up-to-date; **nó không tự bảo đảm hoàn toàn lạnh các cache JVM, filesystem, Docker image hay Spring context nếu test framework chạy trong cùng tiến trình như một phần của suite**. Muốn kiểm tra cold start, cần quản lý điều kiện fork/tiến trình và hạ tầng phù hợp.

Trên Windows, có thể dùng `gradlew.bat test ...`. Lệnh Gradle trả về thời gian toàn task, **không phải thời gian chỉ riêng ApplicationContext**, nên phải đối chiếu log Spring và dữ liệu container.

### 12.2. Mẫu bảng đo cần điền số thực

| Lần chạy | Test type | JVM fork | Cache hits/misses | Container startup | Tổng wall-clock | Ghi chú |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Unit | Mới | Không áp dụng | Không | *Đo thực tế* | Logic thuần |
| 2 | `@WebMvcTest` | Mới | *Ghi log* | Không | *Đo thực tế* | MVC slice |
| 3 | `@ApplicationModuleTest(STANDALONE)` | Mới | *Ghi log* | Tùy | *Đo thực tế* | Orders |
| 4 | `@ApplicationModuleTest(DIRECT_DEPENDENCIES)` | Mới | *Ghi log* | Tùy | *Đo thực tế* | Orders + inventory |
| 5 | `@SpringBootTest(NONE)` | Mới | *Ghi log* | Tùy | *Đo thực tế* | Cross-module |
| 6 | `@SpringBootTest(RANDOM_PORT)` | Mới | *Ghi log* | Tùy | *Đo thực tế* | HTTP E2E |
| 7 | Full suite | Theo CI | *Ghi log* | Theo CI | *Đo thực tế* | Reuse/parallel |

**Không điền số giả** vào bảng vì kết quả phụ thuộc dự án và phần cứng. Nếu benchmark được chạy lặp lại, báo trung vị và độ biến động (ví dụ p95 hoặc min/max) thay vì chọn một lần nhanh nhất.

### 12.3. Một số điều kiện phải giữ nguyên

- Cùng JDK, Spring Boot/Modulith version và Gradle/JUnit setup.
- Cùng cấu hình RAM/CPU, container runtime và chính sách tải hình ảnh.
- Cùng dữ liệu/migration và mức tải máy.
- Cùng số thread/fork/parallel settings hoặc báo rõ khác biệt.
- Cùng cache state khi so sánh cold với cold, warm với warm.
- Đo số context thực sự khởi tạo, không chỉ số test class.

Khi có nhiều context được reuse, tổng thời gian suite có thể thấp hơn tổng thời gian chạy riêng từng class vì **khởi động context được trả giá một lần**.

## 13. Mô hình chi phí của một suite Spring Modulith

Giả sử một ứng dụng có:

- 60 unit tests thuần Java.
- 20 web/JPA slice tests.
- 12 `@ApplicationModuleTest` cho `orders`, `inventory`, `fulfillment`.
- 4 cross-module integration tests với PostgreSQL.
- 2 HTTP E2E tests.

**Không thể suy ra số ApplicationContext chỉ từ 98 test methods**. Ví dụ:

| Cách tổ chức | Context có thể cần tạo | Đặc điểm |
| --- | --- | --- |
| Nhiều class module test cùng module/mode/profile | Có thể reuse context | Ít cold start hơn nếu cache key trùng |
| Mỗi class thêm một mock/inline property khác nhau | Dễ sinh nhiều context | Cache miss tăng dù hành vi gần giống |
| Nhiều class sử dụng `@DirtiesContext` | Context bị invalidated | Tốn khởi tạo lại |
| Chạy trong nhiều Gradle forks | Cache riêng từng JVM | Có thể tăng cold context song song |
| Dùng Testcontainers per-class | Có thêm container lifecycle | Khác với context cache |
| Tách hết test sang các job độc lập | Mỗi job có JVM/cache riêng | Có thể giảm wall-clock tổng nếu đủ tài nguyên nhưng tăng tổng tài nguyên |

### Ví dụ suy luận chi phí

Giả sử (chỉ là ký hiệu, **không phải số liệu đo**) một context `C_orders` cần khởi tạo một lần, các class test tiếp theo đều reuse nó:

~~~text
Không reuse:
    6 × T_start(C_orders) + Σ T_methods

Có reuse:
    1 × T_start(C_orders) + Σ T_methods
~~~

Đây là cơ sở để **gom cấu hình tương thích**, nhưng không phải lý do ép các bài test có hợp đồng khác nhau dùng cùng context. Một context chung chứa nhiều mock có thể nhanh hơn về khởi động song lại vô hiệu hóa bằng chứng wiring thật.

### Đánh đổi: tốc độ, độ tin cậy và khả năng chẩn đoán

Một test `@SpringBootTest` lớn có thể kiểm tra nhiều bước, nhưng khi thất bại phải tìm trong web, service, database, event và consumer. Một chuỗi unit/slice/module test tập trung thường cho tín hiệu lỗi gần nguyên nhân hơn. Nên giữ **ít test E2E quan trọng** để chứng minh đường đi toàn cục, đồng thời tăng độ bao phủ logic ở những lớp nhanh hơn.

## 14. Tối ưu mà không làm mất bằng chứng

### 14.1. Những tối ưu thường an toàn

1. Bỏ `@SpringBootTest` khỏi unit test thuần Java.
2. Dùng `@WebMvcTest` cho validation/mapping độc lập với database, `@DataJpaTest` cho repository mapping và query.
3. Dùng `@ApplicationModuleTest(STANDALONE)` khi mệnh đề nằm trong một module; mở rộng dependency khi test cần hành vi thật của module khác.
4. Dùng architecture test không Spring để chặn dependency sai, thay vì bootstrap toàn bộ ứng dụng chỉ để kiểm tra import.
5. Chuẩn hóa `@ActiveProfiles` và test properties cho các test có cùng yêu cầu môi trường.
6. Giảm `@DirtiesContext` nếu nguyên nhân thực sự là dữ liệu test; dọn dữ liệu bằng chiến lược riêng.
7. Điều chỉnh JVM forks và Testcontainers lifecycle khi đã đo được bottleneck, không chỉ theo cảm giác.
8. Chạy test cấp thấp và architecture trên mọi PR; giữ integration/E2E bắt buộc cho các luồng có rủi ro tương ứng.

### 14.2. Những “tối ưu” làm mất bằng chứng

| Cách làm | Có thể nhanh hơn? | Vì sao không hợp lệ với claim |
| --- | --- | --- |
| Mock `OrderRepository` khi muốn kiểm tra JPA mapping | Có | Không thực thi SQL/JPA thật |
| Mock `OrderManagement` khi muốn kiểm tra service + transaction | Có | Không kiểm tra wiring/logic service thật |
| Chỉ assert `PublishedEvents` khi muốn chứng minh consumer đã commit | Có | Không quan sát side effect của consumer |
| Chuyển PostgreSQL integration thành H2 khi test native SQL/locking | Có | Không giữ cùng dialect/semantics |
| Bỏ `ApplicationModules.verify()` vì E2E xanh | Có thể | Mất kiểm tra package/dependency |
| Dùng `Thread.sleep` rất ngắn để chờ async | Có thể | Tạo flakiness và false negative |
| Tắt Security filter trong E2E xác thực | Có | Không kiểm tra boundary bảo mật thực |
| Dùng `ALL_DEPENDENCIES` để mọi bean đều có mặt | Thường không | Tăng chi phí và làm mờ phạm vi test |

**Câu hỏi phải trả lời trước khi tối ưu:** Thành phần bị loại khỏi context có thuộc **bằng chứng** cần chứng minh không? Nếu có, tối ưu đó không được phép.

## 15. Context và event-driven test: cạm bẫy riêng của Modulith

Event-driven module test cần phân biệt ít nhất ba mệnh đề:

1. Producer **publish** `OrderPlaced` đúng payload.
2. Transaction producer **commit** và listener sau commit được kích hoạt.
3. Consumer hoàn tất **side effect** trong database, có thể bất đồng bộ.

Phạm vi tối thiểu khác nhau:

| Mệnh đề | Lựa chọn | Chi phí cần chấp nhận |
| --- | --- | --- |
| Publish đúng event | `@ApplicationModuleTest` + `PublishedEvents` | Context producer, có thể có DB |
| Consumer nhận và tạo task sau commit | Integration test cả producer + consumer | Context có listener, transaction, DB và async wait |
| Sự kiện không mất qua restart | Reliability test với durable publication registry | Storage bền vững, failure/restart và replay |
| Consumer không import repository nội bộ của producer | `ApplicationModules.verify()` | Phân tích module graph, không cần DB |

### Vì sao “test chạy nhanh” có thể sai về transaction?

Nếu test được đánh dấu `@Transactional` và framework rollback transaction sau test, listener `@TransactionalEventListener(phase = AFTER_COMMIT)` hoặc `@ApplicationModuleListener` có thể **không chạy** vì không có commit thật. Test không kiểm chứng được giao tiếp sau commit dù context có đủ bean.

Ngược lại, bỏ rollback để cho commit thật rồi không dọn dữ liệu có thể khiến suite bị nhiễu. Giải pháp đúng là **dữ liệu unique/cô lập, cleanup phù hợp** và assertion chờ kết quả có timeout, không phải xóa mọi context bằng `@DirtiesContext`.

### Async timeout thuộc chi phí test method, không phải startup

Một test dùng Awaitility chờ `fulfillment.hasTask(orderId)` tối đa 10 giây có thể tốn thời gian vì consumer, connection pool hay scheduler — dù Spring context đã được reuse. Khi thấy test chậm, đừng mặc định “Spring khởi động chậm”. Hãy phân tách:

~~~text
Tổng test: 12.0 s (minh họa)
    Context startup/cache lookup: ? s
    Container + migration: ? s
    Business method: ? s
    Async wait: ? s
    Cleanup: ? s
~~~

Các dấu hỏi phải được thay bằng **số đo**, không suy ra từ tổng 12,0 giây minh họa.

## 16. Troubleshooting: suite chậm do đâu?

| Triệu chứng | Khả năng nguyên nhân | Cách kiểm tra |
| --- | --- | --- |
| Test class đầu tiên chậm, class sau nhanh | Cold context, cache reuse | Xem Spring startup log và cache hit |
| Mỗi class `@SpringBootTest` đều khởi động lại | Khác cache key, `@DirtiesContext` hoặc tách JVM forks | So sánh profiles, properties, mocks và cache stats |
| Context miss liên tục dù test “giống nhau” | Context customizer/bean override khác | Kiểm tra `@MockitoBean`, `@DynamicPropertySource` và cấu hình |
| Suite chậm sau khi thêm `ALL_DEPENDENCIES` | Tăng số module/bean hoặc hạ tầng | So sánh startup log, scope và actual bean count |
| JPA slice chạy chậm | Hibernate metadata, schema/migration hoặc datasource | Đo riêng DB readiness/migration và query |
| Testcontainers chỉ chậm ở lần chạy đầu | Pull image/start container/readiness | Kiểm tra container logs, image cache và lifecycle |
| Cache hit nhưng test vẫn chậm | Phương thức test, SQL, async wait, I/O | Instrument riêng từng bước của test |
| CI chậm hơn local nhiều | CPU/RAM, I/O, network, concurrency | So sánh môi trường và thời gian theo pha |
| Suite dùng nhiều RAM sau tăng cache size | Giữ nhiều context sống | Quan sát heap và giảm fragmentation/forks |
| Event integration test treo | Listener fail/rollback/không đăng ký, Awaitility timeout | Xem log consumer, transaction, state database |
| Test xanh riêng lẻ nhưng fail khi chạy chung | Dữ liệu chia sẻ, thứ tự chạy, container lifecycle | Cô lập fixture và kiểm tra resource ownership |

Khi lỗi đến từ database migration hoặc container, thay annotation Spring thường không xử lý nguyên nhân. Khi lỗi đến từ context cache miss, tối ưu SQL cũng chưa giải quyết được phần thời gian bootstrap. **Chẩn đoán đúng tầng chi phí trước khi tối ưu.**

## 17. Thiết kế quality gate CI theo chi phí và rủi ro

Một quality gate thực tế có thể chia theo lớp nhưng vẫn buộc những phép thử quan trọng được thực thi:

~~~mermaid
flowchart LR
    PR["Pull request"] --> F["Fast gate<br/>unit + architecture"]
    F --> M["Module gate<br/>slice + @ApplicationModuleTest"]
    M --> I["Integration gate<br/>DB + event"]
    I --> E["Critical E2E<br/>HTTP + workflow"]
    E --> G{"Bắt buộc xanh?"}
    G -- "Có" --> OK["Cho phép merge/release"]
    G -- "Không" --> NO["Chẩn đoán và sửa"]
~~~

| Gate | Rủi ro được bảo vệ | Đề xuất tần suất |
| --- | --- | --- |
| Unit tests | Logic domain | Mọi PR |
| `ApplicationModules.verify()` | Vòng/vi phạm API/dependency | Mọi PR, bắt buộc |
| Slice tests | MVC/JPA/JSON/client adapter | Mọi PR |
| `@ApplicationModuleTest` | Bean wiring và use case trong module | Mọi PR với module thay đổi |
| Cross-module integration | Transaction, event, database và consumer | Mọi PR cho luồng quan trọng |
| Reliability tests | Retry, rollback, idempotency, registry | CI có hạ tầng, theo mức rủi ro |
| API E2E | HTTP entry point và kết quả cuối luồng | Chọn luồng thiết yếu làm gate |

Chia job có thể giúp chạy song song, nhưng **mỗi job có cache/JVM/hạ tầng riêng**; tổng tài nguyên và cold startup có thể tăng. So sánh đồng thời ba số: *thời gian chờ PR*, *tổng CPU/container cost* và *độ ổn định của test*.

Không đặt quy tắc “E2E chậm nên luôn bỏ khỏi PR” cho mọi hệ thống. Nếu một luồng có rủi ro nghiêm trọng, bảo vệ nó trước merge/release quan trọng hơn tối ưu vài giây. Ngược lại, không cần một E2E khổng lồ để kiểm tra mọi nhánh tính toán vốn có thể xác nhận nhanh bằng unit test.

### Baseline và cảnh báo hồi quy hiệu năng

Một nhóm có thể theo dõi:

- **Cold context startup** của các nhóm test đại diện.
- **Tổng suite wall-clock** tại PR gate.
- **Cache hit/miss và số context khác nhau**.
- **Container startup/migration time**.
- **p50/p95** thời gian của nhóm integration/E2E.
- **Tỷ lệ flaky/retry** của các test bất đồng bộ.

Ngưỡng cảnh báo phải dựa trên baseline đã đo của chính repository và CI. Ví dụ mục tiêu “không tăng quá 20% so với baseline trong các lần chạy ổn định” có thể dùng như một chính sách tùy chọn, **không phải chuẩn bắt buộc của Spring Modulith**. Trước khi fail một PR chỉ do performance, kiểm tra môi trường CI có thay đổi hoặc đang chịu tải bất thường hay không.

## 18. Bài thực hành

### Bài A — Phân loại chi phí

Với mỗi bài kiểm thử sau, hãy xác định có Spring ApplicationContext không, hạ tầng nào được khởi tạo và bằng chứng thu được:

1. JUnit tính tổng `BigDecimal`.
2. `ApplicationModules.of(ShopApplication.class).verify()`.
3. `@WebMvcTest(OrderController.class)` với `MockMvc`.
4. `@DataJpaTest` dùng H2.
5. `@ApplicationModuleTest` cho module `orders`.
6. `@SpringBootTest(NONE)` cho `orders → fulfillment`.
7. `@SpringBootTest(RANDOM_PORT)` kết hợp PostgreSQL Testcontainers.

### Bài B — Thiết kế benchmark

Viết bảng kết quả theo mẫu ở mục 12, chạy ít nhất ba lần trong cùng môi trường cho mỗi test type. Ghi:

- JVM/fork và cache state.
- Context hit/miss.
- Có sử dụng Testcontainers không.
- Total wall-clock.
- Vị trí phần thời gian tốn nhất.

So sánh cold với cold, warm với warm. Không kết luận “annotation A luôn nhanh hơn B” chỉ từ một lần đo.

### Bài C — Điều tra cache fragmentation

Tạo hai class test gần như giống nhau nhưng khác một `@TestPropertySource`. Xem thống kê Spring TestContext cache, rồi thử chuẩn hóa cấu hình khi hai class thực sự có cùng mục tiêu.

**Giải thích:** Vì sao chúng có cache key khác nhau, và khi nào việc giữ hai context riêng là đúng?

### Bài D — Sử dụng @DirtiesContext

Chọn một test đang dùng `@DirtiesContext` để dọn database. Thiết kế lại fixture bằng dữ liệu unique và cleanup/rollback phù hợp. Sau đó đo cache miss và suite time trước/sau. Không dùng rollback cho bài event `AFTER_COMMIT` nếu chính commit là hành vi cần kiểm chứng.

### Bài E — So sánh bootstrap mode của Spring Modulith

Đặt module test trong `orders`, lần lượt thử `STANDALONE`, `DIRECT_DEPENDENCIES` và `ALL_DEPENDENCIES`. Ghi các dependency được đưa vào context và thời gian cold. Giải thích vì sao mode có nhiều module hơn chưa chắc cần thiết cho test về `PublishedEvents` của riêng producer.

### Bài F — Tối ưu có giữ bằng chứng

Một test hiện tại dùng `@SpringBootTest(RANDOM_PORT)` chỉ để kiểm tra phép nhân tổng tiền. Hãy chuyển thành unit test, ghi nhận bằng chứng không mất đi. Sau đó xét một test `orders → fulfillment` cần listener sau commit: có được chuyển sang unit test mock publisher để giảm chi phí không? Giải thích phần bằng chứng sẽ bị mất.

### Câu hỏi tự đánh giá

1. Vì sao số lượng test class **không bằng** số lần tạo ApplicationContext?
2. `@SpringBootTest(NONE)` và `RANDOM_PORT` khác nhau ở thành phần và bằng chứng nào?
3. Một `@DataJpaTest` có luôn nhanh hơn mọi `@SpringBootTest` không?
4. `@DirtiesContext` làm gì với khả năng tái sử dụng context?
5. Khi tăng `maxParallelForks`, Spring TestContext cache có chia sẻ giữa các JVM không?
6. Vì sao Testcontainers lifecycle và TestContext cache không phải cùng một cơ chế?
7. Khi `PublishedEvents` có event, điều gì vẫn chưa được chứng minh về listener và transaction?
8. Nếu architectural test rất nhanh, vì sao vẫn cần integration test có database?

## 19. Checklist trước khi chọn hoặc tối ưu test type

- [ ] Mệnh đề cần chứng minh được mô tả rõ.
- [ ] Assertion quan sát đúng kết quả, không chỉ quan sát mock.
- [ ] Đã xác định thành phần Spring/hạ tầng bắt buộc phải thật.
- [ ] Đã chọn unit, slice, module, integration hay E2E ở phạm vi nhỏ nhất **đủ bằng chứng**.
- [ ] Đã phân biệt context startup với container/database startup và thời gian test method.
- [ ] Đã quan sát cold/warm và Spring TestContext cache hit/miss nếu nghi ngờ chậm do context.
- [ ] Profile, test properties, bean overrides nhất quán khi test dùng cùng cấu hình.
- [ ] Không dùng `@DirtiesContext` chỉ để xóa dữ liệu khi có lựa chọn tốt hơn.
- [ ] Event test có commit thật, quan sát async có timeout và dữ liệu cô lập.
- [ ] Các rule `ApplicationModules.verify()` vẫn được chạy trong CI.
- [ ] Test có hạ tầng đắt tiền vẫn được giữ nếu hạ tầng đó thuộc bằng chứng phải thu.
- [ ] Những điều test chưa chứng minh được ghi nhận rõ.

## 20. Ghi nhớ

**Chi phí khởi động context** không chỉ phụ thuộc annotation mà còn phụ thuộc số bean, auto-configuration, phạm vi module, transaction/database, container lifecycle, Spring TestContext cache và JVM fork. Unit/architectural test tránh được việc tạo Spring context; slice test chỉ nạp phần công nghệ liên quan; `@ApplicationModuleTest` giới hạn theo application module và bootstrap mode; `@SpringBootTest` dùng cho tích hợp rộng và `RANDOM_PORT` khi HTTP server thật thuộc hợp đồng.

Khi tối ưu suite Spring Modulith, hãy **đo cold/warm và cache hit/miss trước**, giảm context không cần thiết nhưng **không mock hoặc loại bỏ thành phần quyết định bằng chứng**. Kết hợp `ApplicationModules.verify()` với module test, event/database integration và một số E2E quan trọng trong **quality gate CI** để vừa có vòng phản hồi nhanh, vừa ngăn phụ thuộc sai và hồi quy hành vi.
