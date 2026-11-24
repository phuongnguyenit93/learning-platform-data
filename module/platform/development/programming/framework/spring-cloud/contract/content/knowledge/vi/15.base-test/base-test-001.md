# Vai trò base class trong kiểm thử phía producer

Trong **Spring Cloud Contract**, producer và consumer thống nhất hành vi API bằng **Groovy/YAML DSL**. Plugin đọc hợp đồng rồi **sinh kiểm thử phía producer**, nhưng bài test được sinh không tự biết ứng dụng phải khởi động thế nào, gọi HTTP qua công cụ gì, dữ liệu test đến từ đâu hoặc kích hoạt message bằng phương thức nào.

**Base test class** (*lớp cơ sở kiểm thử*) giải quyết phần kết nối đó. Đây là lớp do **nhóm producer duy trì**, cung cấp ngữ cảnh thực thi để generated contract tests gọi implementation thật và kiểm tra các cam kết HTTP hoặc thông điệp. Khi producer tests đạt, nhóm có thể phát hành stub cho consumer sử dụng với **Stub Runner** và đưa quy trình kiểm tra thay đổi API không tương thích vào **CI**.

Bài này thuộc chương **Base test** trong lộ trình **SPRING_CLOUD_CONTRACT**. Mục tiêu là hiểu rõ trách nhiệm của base class, cách liên kết nó với generated tests trong Maven/Gradle, cách chuẩn bị fixture ổn định và cách chẩn đoán các lỗi xuất phát từ môi trường kiểm thử.

## 1. Base class ở đâu trong luồng kiểm thử hợp đồng?

```mermaid
flowchart TD
    A[Consumer và producer thỏa thuận hành vi] --> B[Viết contract Groovy hoặc YAML]
    B --> C[Spring Cloud Contract plugin sinh producer tests]
    D[Base class: context, HTTP/message adapter, fixture] --> E[Generated tests kế thừa base class]
    C --> E
    E --> F[Chạy trên implementation producer]
    F --> G{Kết quả khớp contract?}
    G -- Không --> H[Sửa implementation, fixture hoặc contract qua review]
    H --> F
    G -- Có --> I[Đóng gói stub có version]
    I --> J[Consumer dùng Stub Runner]
    J --> K[Consumer tests và CI]
```

Một hợp đồng có thể mô tả:

- Request `GET /api/orders/ORDER-42`;
- Response `200 OK` với `status=PAID`;
- Hoặc hành vi message `ORDER_PAID` với payload cụ thể.

Nhưng nó không tự tạo bản ghi `ORDER-42`, khởi động Spring Boot application context, cấp JWT kiểm thử hoặc tạo broker. **Base class và các helper của nó chuẩn bị môi trường đó.**

### 1.1. Phân biệt trách nhiệm của từng thành phần

| Thành phần | Nguồn tạo | Vai trò |
|---|---|---|
| **Contract DSL** | Nhóm producer/consumer cùng thống nhất | Định nghĩa hành vi bên ngoài: request, response, matcher, message |
| **Generated producer test** | Plugin Spring Cloud Contract sinh | Gọi producer và assert các kỳ vọng trong DSL |
| **Base test class** | Nhóm producer tự viết | Setup test context, HTTP adapter, fixture, auth, message trigger |
| **Producer implementation** | Code ứng dụng thực | Hiện thực nghiệp vụ mà contract đang bảo vệ |
| **Stub mappings/artifact** | Sinh từ contract và đóng gói | Mô phỏng producer cho consumer |
| **Consumer integration test** | Nhóm consumer tự viết | Kiểm tra client của consumer thông qua Stub Runner |

**Quy tắc sửa lỗi:** thay đổi cam kết HTTP thì sửa contract; sửa setup dữ liệu thì sửa base/fixture; sửa hành vi nghiệp vụ thì sửa implementation. Không sửa trực tiếp generated source vì sẽ bị ghi đè trong lần generate tiếp theo.

## 2. Base class thường đảm nhận những việc gì?

Một base class có thể:

1. **Khởi chạy môi trường:** cấu hình `@SpringBootTest`, Spring TestContext hoặc test mode phù hợp.
2. **Cấu hình HTTP adapter:** `MockMvc`/`RestAssuredMockMvc` hoặc HTTP test client với server thật.
3. **Khởi tạo dữ liệu:** seed hoặc reset database, cache, test account, quyền truy cập và trạng thái nghiệp vụ.
4. **Cấp test identity:** tạo test JWT/credentials và bảo đảm security filter chain được kiểm tra đúng.
5. **Cung cấp message trigger:** phương thức được DSL `triggeredBy(...)` tham chiếu.
6. **Quản lý phụ thuộc:** Clock, ID generator, broker, external service stub hoặc feature flags.
7. **Cô lập trạng thái:** giúp các generated tests chạy riêng hoặc theo nhiều thứ tự mà vẫn ổn định.
8. **Hỗ trợ chẩn đoán:** ghi log có kiểm soát về fixture, request và response, không lộ dữ liệu nhạy cảm.

Không phải mọi base class phải làm tất cả. Với producer HTTP đơn giản, `MockMvc` và một vài dữ liệu cố định có thể đủ. Với producer phát Kafka/RabbitMQ events, cần thêm binder, message verifier hoặc broker test.

**Một base class tốt thường mỏng.** Có thể dùng một số helper test riêng biệt:

```text
OrderContractTestBase
├── Spring Boot test context
├── MockMvc / RestAssuredMockMvc
├── OrderContractFixtures
├── TestClockConfig
├── TestSecurityConfig
└── Message test hook (khi cần)
```

Tránh biến base class thành một lớp rất lớn chứa tất cả business assertions của mọi consumer. Nó dễ gây khởi tạo thừa, coupling và race condition.

## 3. Ví dụ HTTP contract: dữ liệu mà base class cần chuẩn bị

Giả sử **Order Service** là producer và **Checkout** là consumer.

```http
GET /api/orders/ORDER-42
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json

{"id":"ORDER-42","customerId":"CUSTOMER-7","status":"PAID","totalAmount":125000}
```

Một contract Groovy hợp lệ về ý tưởng:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'checkout_get_paid_order_200'
    description 'Checkout đọc đơn hàng đã thanh toán'

    request {
        method GET()
        url '/api/orders/ORDER-42'
        headers {
            header 'Accept', 'application/json'
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: 'ORDER-42',
            customerId: 'CUSTOMER-7',
            status: 'PAID',
            totalAmount: 125000
        )
    }
}
```

Hợp đồng này quy định **cái gì phải xảy ra**, không nói ứng dụng cần mở kết nối database ra sao. Nếu ứng dụng truy vấn `ORDER-42` mà database test chưa có đơn hàng ấy, generated test có thể trả `404` dù code và DSL không có lỗi cú pháp.

Một file YAML mô tả cùng kỳ vọng:

```yaml
name: checkout_get_paid_order_200
description: Checkout đọc đơn hàng đã thanh toán
request:
  method: GET
  url: /api/orders/ORDER-42
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORDER-42
    customerId: CUSTOMER-7
    status: PAID
    totalAmount: 125000
```

Khi học, **chỉ giữ một trong hai biểu diễn** làm nguồn cho kịch bản này để tránh sinh test/mapping trùng lặp. Dự án có thể dùng nhiều DSL, nhưng các request matcher chồng lấn cần được thiết kế có chủ đích.

## 4. Base class với Spring Boot, MockMvc và RestAssuredMockMvc

Với producer dùng **Spring MVC**, một cách phổ biến là kết hợp:

- `@SpringBootTest` để nạp Spring Boot application context;
- `@AutoConfigureMockMvc` để cấu hình HTTP test adapter `MockMvc`;
- `RestAssuredMockMvc.mockMvc(mockMvc)` để những generated tests sử dụng MockMvc;
- `@BeforeEach` để khởi tạo dữ liệu trước khi chạy từng generated test.

Ví dụ base class:

```java
package com.example.order.contract;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
public abstract class OrderContractTestBase {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private OrderContractFixtures fixtures;

    @BeforeEach
    protected void setUpContractTest() {
        fixtures.resetContractOrders();
        fixtures.insertPaidOrder("ORDER-42", "CUSTOMER-7", 125000);
        fixtures.ensureOrderAbsent("ORDER-MISSING");

        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
```

**Cần hiểu phạm vi của đoạn code:**

- `OrderContractFixtures` **không phải** lớp có sẵn trong Spring Cloud Contract; dự án phải tự viết hoặc thay bằng phương pháp seed khác.
- `@BeforeEach` là annotation của JUnit Jupiter/JUnit 5. Nếu dự án đang dùng JUnit 4, lifecycle và import sẽ khác.
- `protected` giúp phương thức setup có thể được kế thừa khi generated test nằm trong package khác.
- `@SpringBootTest` không đồng nghĩa mọi bean/service ngoài đều sẵn sàng: cần khai báo test profile, repository, MockMvc và dependency phù hợp.
- `@AutoConfigureMockMvc` giúp dùng infrastructure Spring MVC; base class này **không dùng nguyên xi** cho WebFlux hoặc một test mode chạy HTTP trên cổng thật.
- `fixtures.resetContractOrders()` chỉ an toàn nếu database được dành riêng cho test. Hai test chạy song song và cùng reset một DB có thể xóa dữ liệu của nhau.

Đoạn này minh họa nơi kết nối **generated HTTP test** với producer. Để biên dịch, project cần ứng dụng Spring Boot, helper fixture thực tế và các dependency của Spring Boot Test, RestAssured MockMvc và Spring Cloud Contract Verifier tương thích.

### 4.1. Kịch bản `404` cũng do base class hỗ trợ

Ví dụ hợp đồng YAML cho tài nguyên không tồn tại:

```yaml
name: checkout_get_missing_order_404
request:
  method: GET
  url: /api/orders/ORDER-MISSING
response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: ORDER_NOT_FOUND
```

Base class gọi `fixtures.ensureOrderAbsent("ORDER-MISSING")`. Do đó kịch bản `404` không phụ thuộc vào một test khác đã xóa bản ghi này trước đó.

Mục tiêu không phải mọi test dùng cùng dữ liệu, mà là **mọi test có dữ liệu ban đầu đúng với kịch bản của mình**.

## 5. Generated test kế thừa base class như thế nào?

Khi plugin được cấu hình đúng, mã sinh về ý tưởng có dạng:

```java
// Đoạn minh họa kiến trúc, không phải generated output chính xác.
class GeneratedPaidOrderTest extends OrderContractTestBase {

    @Test
    void checkout_get_paid_order_200() {
        // HTTP request được sinh từ contract.
        // Assertions được sinh từ response body/status/matchers.
    }
}
```

Trình tự test chạy:

1. JUnit khởi tạo generated test instance.
2. Spring TestContext xử lý các annotation và injection ở base class.
3. Lifecycle setup (`@BeforeEach`) chuẩn bị fixture và HTTP adapter.
4. Generated test gửi request vào implementation producer.
5. Assertions được sinh đối chiếu response/message với contract.
6. Cleanup hoặc rollback diễn ra theo cách test infrastructure đã cấu hình.

Generated source cụ thể có thể khác về package, class name, JUnit version hoặc REST adapter. Đừng đoán tên method chỉ từ file DSL. **Sau lần generate đầu tiên, hãy mở generated test để xác nhận nó kế thừa đúng base class và đang gọi API nào.**

Nếu generated test không kế thừa base class hoặc gọi sai adapter, không sửa file generated. Hãy sửa plugin config, classpath hoặc test mode rồi generate lại.

## 6. Cấu hình Maven chọn base class

Spring Cloud Contract Maven plugin hỗ trợ cấu hình tên lớp cơ sở bằng `baseClassForTests`. Ví dụ trong phần `build/plugins` của `pom.xml`:

```xml
<!-- Ví dụ rút gọn: version plugin do dự án quản lý. -->
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>VERSION_PHU_HOP</version>
    <extensions>true</extensions>
    <configuration>
        <baseClassForTests>com.example.order.contract.OrderContractTestBase</baseClassForTests>
    </configuration>
</plugin>
```

`VERSION_PHU_HOP` là placeholder, **không phải version artifact thật**. Cần đối chiếu Spring Boot, Spring Cloud release train, JDK và phiên bản Spring Cloud Contract plugin trước khi sử dụng. Nếu project đặt version bằng property, hãy dùng property được project định nghĩa và kiểm tra effective POM.

Ví dụ lệnh sử dụng Maven Wrapper:

```bash
./mvnw -version
./mvnw clean test
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd -version
.\mvnw.cmd clean test
```

Khi test hoàn thành, xác minh:

- File Groovy/YAML được plugin nhận diện từ đúng thư mục.
- Generated test kế thừa **FQN** `com.example.order.contract.OrderContractTestBase`.
- Class base có mặt trên test source set/classpath.
- `@BeforeEach` chạy và fixture thực sự được seed.
- Generated test được **thực thi**, không chỉ compile.
- Test report hiển thị các contract cases đã mong đợi.

**Build xanh nhưng không có generated contract tests chưa chứng minh producer tuân thủ hợp đồng.**

## 7. Cấu hình Gradle chọn base class

Với producer dùng Gradle và Spring Cloud Contract plugin, cấu hình tham khảo trong **Groovy build script**:

```groovy
// build.gradle: giả định Spring Cloud Contract plugin đã được áp dụng.
contracts {
    baseClassForTests = 'com.example.order.contract.OrderContractTestBase'
}
```

Đây là đoạn cấu hình **minh họa**, chưa phải file build hoàn chỉnh; plugin phải được áp dụng bằng phiên bản tương thích, test dependencies phải có đủ, và đường dẫn DSL/test sources phải đúng. Với `build.gradle.kts`, cú pháp Kotlin DSL của cấu hình Gradle có thể khác. Kiểm tra tài liệu **đúng phiên bản** trước khi sao chép.

Chạy với Gradle Wrapper:

```bash
./gradlew --version
./gradlew clean test
./gradlew build
```

Khi plugin có tác vụ sinh test như `generateContractTests`, cần kiểm tra nó thực sự được nối vào lifecycle; chỉ thấy tác vụ trong `tasks --all` chưa đủ.

### 7.1. Nếu không muốn một base class cho tất cả contract

Spring Cloud Contract có các cơ chế cấu hình **base-class mappings** hoặc suy tên base từ package/folder trong những phiên bản tương ứng. Chẳng hạn HTTP tests và message tests có thể cần setup khác nhau.

Không tự đoán chính xác cách một phiên bản map folder `checkout` hay `billing` sang tên class. Hãy:

1. Chọn quy tắc tổ chức contract theo consumer hoặc loại giao tiếp.
2. Tra tài liệu đúng phiên bản về `baseClassForTests`, `packageWithBaseClasses` và `baseClassMappings` nếu chúng có trong phiên bản đang dùng.
3. Sinh test và kiểm tra từng generated class kế thừa đúng base class.
4. Giữ shared fixture utilities tách biệt khỏi base class chuyên cho HTTP/message.

Tham khảo: [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/), [Spring Cloud release trains](https://spring.io/projects/spring-cloud) và [Spring Boot system requirements](https://docs.spring.io/spring-boot/system-requirements.html).

## 8. Test mode quyết định base class cần chuẩn bị gì

Không có một base class phù hợp cho mọi producer.

| Kiểu test | Base class thường cần | Lưu ý |
|---|---|---|
| **Spring MVC / MockMvc** | `MockMvc` và RestAssuredMockMvc, Spring MVC context | Không bypass filter chain nếu cần xác thực |
| **HTTP qua server thật** | Khởi động web server test, base URI và HTTP client | Dùng port động, tránh tranh chấp CI |
| **Spring WebFlux** | Hạ tầng reactive test và adapter được phiên bản hỗ trợ | Không copy máy móc setup MockMvc |
| **JAX-RS hoặc framework khác** | Adapter tương ứng theo plugin/test mode | Kiểm tra compatibility chính thức |
| **Message contract** | Message verifier, broker/binder test, trigger method | Không dùng HTTP setup thay thế kiểm tra message |

Base class ở mục 4 dành cho **Spring MVC** với test mode phù hợp. Nếu plugin sinh generated test dùng RestAssured gọi server thật nhưng base class chỉ gắn `RestAssuredMockMvc`, generated test có thể sai loại adapter.

Trong mọi trường hợp, nguyên tắc là **xem generated code và đối chiếu với base class**, không chỉ dựa trên cấu hình có vẻ đúng.

### 8.1. MockMvc so với server thật

**MockMvc** xử lý request thông qua Spring MVC test infrastructure, thường không cần mở một cổng HTTP độc lập. Nó hữu ích để kiểm tra controller và filter trong application context.

**Test qua web server thật** thực hiện request HTTP trên socket, phù hợp khi muốn kiểm chứng nhiều lớp hạ tầng hơn. Nó cần quản lý startup, teardown, port, base URI và những dependency ngoài.

Mỗi mode đều có giá trị, nhưng base class phải khớp mode. Khi chạy CI song song, không hard-code `localhost:8080` nếu nhiều job có thể tranh cổng.

## 9. Dữ liệu fixture cần được tái tạo trước mỗi test

Đối với producer verification, test input phải nhất quán với trạng thái trước request. Một hợp đồng `GET` có thể yêu cầu đơn hàng `PAID`; một hợp đồng `404` yêu cầu ID không tồn tại; một hợp đồng `409` yêu cầu đơn đã chuyển sang `SHIPPED`.

| Kịch bản | Fixture cần có | Response |
|---|---|---|
| Đọc đơn đã thanh toán | `ORDER-42` với `status=PAID` | `200` |
| Đọc đơn không tồn tại | `ORDER-MISSING` vắng mặt | `404` |
| Hủy đơn đã giao | `ORDER-SHIPPED` có `status=SHIPPED` | `409` |
| API yêu cầu scope | Test identity có scope phù hợp | `200` hoặc `403` |
| Token không hợp lệ | Test token bị từ chối | `401` |

Các chiến lược:

- `@BeforeEach` với fixture helper/repository;
- SQL script hoặc `@Sql`;
- Testcontainers và migrations;
- Database/schema hoặc namespace riêng cho tests;
- Mock một dependency ngoài phạm vi contract khi có lý do rõ ràng.

SQL minh họa cho database test có schema tương ứng:

```sql
DELETE FROM orders
WHERE id IN ('ORDER-42', 'ORDER-MISSING');

INSERT INTO orders
    (id, customer_id, status, total_amount)
VALUES
    ('ORDER-42', 'CUSTOMER-7', 'PAID', 125000);
```

**Không chạy đoạn xóa trên database thật/dùng chung.** Schema/cột và cú pháp cần chỉnh theo database của dự án. Nếu có cache, bảng outbox, search index hoặc broker, reset bảng `orders` có thể chưa đủ.

### 9.1. Không phụ thuộc thứ tự generated tests

Thiết kế sai:

```text
Test 1 tạo ORDER-42.
Test 2 GET ORDER-42 và chờ 200.
Test 3 xóa ORDER-42 và chờ 204.
```

Nếu test 2 chỉ đạt sau test 1 thì nó thiếu fixture độc lập. Với contract testing, mỗi test nên có **điều kiện đầu vào tự xác định**. Nếu cần chứng minh toàn bộ chuỗi tạo→đọc→xóa, viết một **workflow integration test** riêng tự quản lý ID, trạng thái và cleanup.

### 9.2. `@BeforeEach` không tự giải quyết race condition

Khi hai tests chạy song song và cùng thực hiện `resetContractOrders()` trên một DB, test này có thể xóa bản ghi mà test kia đang dùng. Cần chọn DB/schema, namespace hoặc fixture ID riêng theo test/job, hoặc tổ chức concurrency phù hợp.

`@Transactional` cũng không mặc định rollback mọi request chạy qua web server thật, vì chúng có thể sử dụng transaction khác. `@DirtiesContext` làm mới Spring TestContext khi cần, **không tự xóa broker, Redis, DB ngoài hoặc mọi trạng thái hệ thống**.

## 10. Base class và xác thực

Một API có thể yêu cầu:

```http
GET /api/orders/ORDER-42
Authorization: Bearer contract-reader-token
```

Base class có thể chuẩn bị test identity, mock introspector hoặc test JWT. Nhưng nếu nó làm test bỏ qua Spring Security filters thì bài test `200` không còn bảo vệ hành vi xác thực.

Ví dụ cấu hình MockMvc cần cho test có security filters:

```java
@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
public abstract class SecuredOrderContractTestBase {

    @Autowired
    MockMvc mockMvc;

    @BeforeEach
    protected void setupHttp() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
```

Các imports tương tự mục 4. `addFilters = true` cho phép MockMvc áp dụng các filters đã được Spring context cấu hình; nó **không tự tạo security configuration**. Khi test cần xác thực, phải thiết kế token và roles/scopes fixture phù hợp.

Tránh:

- `MockMvcBuilders.standaloneSetup(controller)` không tích hợp filter chain mà tưởng đã kiểm tra auth.
- Test profile `permitAll()` cho mọi endpoint chỉ để test xanh.
- Dùng `@WithMockUser` trên tất cả generated tests khi muốn xác minh chính header `Authorization`.
- Copy access token production vào DSL hoặc log.
- Coi một chuỗi placeholder như `contract-reader-token` là JWT hợp lệ mặc định.

Contract test kiểm tra hành vi mà consumer phụ thuộc. Security integration tests riêng vẫn cần thiết để kiểm chứng JWT signature, issuer, audience, expiry và các luật phân quyền phức tạp.

## 11. Base class và dữ liệu động

Nếu API trả ID do server sinh hoặc timestamp hiện tại, một base class có thể giúp kiểm soát tính ngẫu nhiên bằng:

- `Clock.fixed(...)` cho thời gian xác định;
- bộ tạo ID thử nghiệm khi cần so sánh ID chính xác;
- test token và fixture riêng, không bị hết hạn bất ngờ;
- mock dependency ngoài phạm vi kiểm thử;
- cleanup state trước/sau mỗi request.

Ví dụ cấu hình Clock:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration
class FixedClockForContractTests {

    @Bean
    @Primary
    Clock contractClock() {
        return Clock.fixed(
            Instant.parse("2026-01-15T09:30:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

Test configuration cần được import vào test context; production code cũng phải dùng bean `Clock` thay vì gọi trực tiếp `Instant.now()`. Nếu không, khai báo bean không giúp tạo thời gian cố định.

Đối với dữ liệu được phép biến động, hợp đồng có thể dùng **matcher phù hợp** thay cho hard-code. Khi đó base class quản lý nguồn dữ liệu, còn DSL diễn đạt ràng buộc consumer thực sự cần. Không nên dùng `.*` cho mọi giá trị để tránh test đỏ, vì matcher quá lỏng có thể che thay đổi API không tương thích.

## 12. Message contract: base class chứa hook để kích hoạt

Spring Cloud Contract còn hỗ trợ message contracts. Ví dụ producer **Order Service** phát sự kiện `ORDER_PAID` cho **Billing**.

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'billing_order_paid_event_v1'
    label 'billing_order_paid_v1'

    input {
        triggeredBy('publishOrderPaid()')
    }

    outputMessage {
        sentTo('orders.events')
        body(
            eventType: 'ORDER_PAID',
            orderId: 'ORDER-42',
            totalAmount: 125000
        )
    }
}
```

Trong ví dụ này:

- `triggeredBy('publishOrderPaid()')` yêu cầu phương thức **do producer cung cấp** để kích hoạt ứng dụng.
- `label` định danh kịch bản để cơ chế stub/message triggering sử dụng ở phía consumer, nếu phiên bản và cấu hình hỗ trợ.
- `sentTo` khai báo destination của output message.

Một base class định hướng:

```java
public abstract class OrderMessageContractTestBase {

    protected void publishOrderPaid() {
        // Gọi service thực của producer để phát ORDER_PAID.
        // Có thể cần seed ORDER-42 và setup broker/binder test.
    }
}
```

Đây là **mã minh họa**, không phải một chương trình hoàn chỉnh. Khi dùng thật cần:

1. Hạ tầng message verifier/binder phù hợp phiên bản.
2. Test Spring context và service đủ để phát message thật.
3. Fixture chuẩn bị trạng thái đơn hàng.
4. Hook có đúng tên, phạm vi truy cập và signature theo generated tests.
5. Topic/queue hoặc broker test nhận message.
6. Cơ chế correlation ID và cleanup tránh nhận sự kiện từ test trước.

Không đặt một phương thức gọi trực tiếp mock publisher trả kết quả giả rồi cho rằng đã kiểm chứng producer message logic nếu logic đó là phần cần bảo vệ.

### 12.1. HTTP và message có bắt buộc dùng chung base class không?

Không. HTTP base class thường có MockMvc, trong khi message base class có trigger/message verifier. Có thể tách:

```text
SharedContractFixtures
├── OrderHttpContractTestBase
│   └── MockMvc + RestAssuredMockMvc
└── OrderMessageContractTestBase
    └── message hooks + binder/broker test
```

Khi phiên bản plugin hỗ trợ ánh xạ base class theo package/contract group, thiết lập tương ứng rồi xác minh generated source. Tránh tạo một God class khởi động toàn bộ infrastructure cho mọi bài test.

## 13. Chẩn đoán lỗi: base class hay hợp đồng?

| Hiện tượng | Nơi điều tra đầu tiên |
|---|---|
| `cannot find symbol: OrderContractTestBase` | FQN, package, test classpath, plugin `baseClassForTests` |
| `NoSuchBeanDefinitionException` | Spring context, component scan, test configuration, profile |
| `mockMvc` bằng null | Dependency injection, test mode, context setup |
| Generated test không dùng RestAssuredMockMvc | Plugin đang sinh adapter/test mode khác |
| `@BeforeEach` không chạy | JUnit version, visibility, class inheritance, lifecycle |
| `200` thành `404` | Fixture/DB thiếu bản ghi hoặc URL sai |
| `200` thành `409` | Fixture chứa trạng thái sai hoặc test khác thay đổi |
| `200` thành `401`/`403` | Authentication/authorization setup, token fixture, filters |
| Request không cần token vẫn `200` | Có thể security bị bypass trong test base |
| Hook `publishOrderPaid()` không tìm thấy | Tên/signature/visibility method, generated call |
| Message test timeout | Broker/binder, trigger hoặc correlation key |
| Test compile nhưng không có trong report | Plugin/source directory chưa nối test task hoặc test bị skip |
| Stub Runner trả response khác | Artifact/version hoặc mappings/matcher không đúng |

Quy trình tìm nguyên nhân hiệu quả:

1. Kiểm tra Spring Boot, Spring Cloud Contract plugin, JDK và build tool.
2. Kiểm tra DSL đã được plugin quét và generated test đã được sinh.
3. Đọc generated class để xác nhận base class, test mode, request/message API đang gọi.
4. Xem base class có setup đúng context/adapter/fixture/hook chưa.
5. Quan sát request/response hoặc message thực tế, so sánh kỳ vọng DSL.
6. Sửa **đúng lớp**: plugin/build, base/fixture, contract hoặc implementation.
7. Chạy lại producer verification và consumer tests khi cần.

Không đổi status trong contract để che `NoSuchBeanDefinitionException`, cũng không chỉnh generated code bằng tay. Một lỗi môi trường không nhất thiết chứng minh cam kết API đã sai.

## 14. CI và cổng phát hành stub

```mermaid
flowchart TD
    A[Chọn JDK và Wrapper phù hợp] --> B[Đọc Groovy/YAML contracts]
    B --> C[Sinh generated producer tests]
    C --> D[Khởi động base class, fixture và adapter]
    D --> E[Chạy implementation producer]
    E --> F{Producer contract tests đạt?}
    F -- Không --> G[Chẩn đoán contract, base hoặc implementation]
    G --> D
    F -- Có --> H[Đóng gói stub artifact version cố định]
    H --> I[Consumer dùng Stub Runner]
    I --> J{Consumer integration test đạt?}
    J -- Không --> K[Sửa consumer hoặc thương lượng contract]
    K --> B
    J -- Có --> L[Cho phép tích hợp/phát hành]
```

Một CI đáng tin nên xác minh:

- Contract files được phát hiện đúng và số lượng generated tests phù hợp.
- Generated tests **thực sự chạy**, không bị skip bằng `-DskipTests` hoặc exclude.
- Base class có thể tạo Spring context và adapter đúng test mode.
- Fixture được tạo trên môi trường test cô lập, không dùng production data.
- Security filters, clock và message dependencies được cấu hình đúng.
- Producer verification đạt trước khi **phát hành stub đã xác minh**.
- Stub artifact có tọa độ/version rõ ràng, consumer dùng đúng bản.
- Consumer tests chạy qua **client thật** với Stub Runner, không chỉ gọi stub từ một client giả khác.
- Log đủ thông tin để debug nhưng không in token/PII.

Stub dùng để phát triển sớm trước khi producer hoàn thành có thể là bản **preview**, nhưng chưa nên coi nó đã được implementation xác minh. Cổng phát hành phải dựa trên producer contract tests thực sự đạt.

## 15. Bài thực hành: viết base class cho Order Service

Yêu cầu: producer `order-service`, consumer `checkout-service` và project đã có Spring Boot/Contract plugin tương thích.

### Giai đoạn A — viết contract

1. Tạo Groovy hoặc YAML contract `GET /api/orders/ORDER-42` trả `200` với `status=PAID`.
2. Tạo contract `GET /api/orders/ORDER-MISSING` trả `404`.
3. Đặt tên kịch bản rõ ràng, tránh hai file cùng method/path/request matcher trả response trái nhau.

### Giai đoạn B — viết base class

1. Tạo `OrderContractTestBase` trong test sources, sử dụng Spring context và `MockMvc` phù hợp.
2. Tạo helper `OrderContractFixtures`, seed đơn hàng `ORDER-42` và bảo đảm `ORDER-MISSING` vắng mặt.
3. Thiết lập `RestAssuredMockMvc.mockMvc(mockMvc)` trong lifecycle setup.
4. Nếu API có authentication, thêm test security config và kiểm tra filter chain.
5. Bảo đảm việc seed/reset không ảnh hưởng DB, cache hoặc broker của test khác.

### Giai đoạn C — nối plugin và sinh tests

1. Cấu hình `baseClassForTests` theo đúng FQN.
2. Chạy Maven Wrapper hoặc Gradle Wrapper của dự án để sinh và chạy tests.
3. Kiểm tra generated source **extends** base class mong muốn.
4. Kiểm tra generated requests, status/body assertions và test report.
5. Chạy từng test riêng lẻ rồi chạy cùng suite; kết quả phải nhất quán.

### Giai đoạn D — tạo lỗi có chủ đích

1. Xóa fixture `ORDER-42`. Bài `200` nên thất bại vì tài nguyên không tồn tại.
2. Seed nhầm trạng thái `CANCELLED` thay vì `PAID`. Bài `200` phải phát hiện khác biệt body.
3. Cố ý cấu hình sai FQN base class, quan sát lỗi compile của generated tests rồi sửa lại.
4. Nếu có security, thử bỏ header Authorization và kiểm tra producer thực sự từ chối.
5. Khôi phục code/fixture sau các thí nghiệm.

### Giai đoạn E — stub và CI

1. Chạy lại producer contract tests đầy đủ.
2. Đóng gói stub artifact từ build đạt test.
3. Cho consumer dùng Stub Runner với stub artifact/version đã ghim.
4. Viết consumer integration test gọi qua HTTP client thật.
5. Đưa test generation, producer verification, packaging và consumer tests vào CI.

**Tiêu chí hoàn thành:** generated producer tests kế thừa đúng base class, dữ liệu test tự tái tạo được, tests không phụ thuộc thứ tự và stub chỉ được công bố là đã xác minh sau khi implementation producer vượt kiểm thử.

## 16. Checklist review base class

| Câu hỏi | Tiêu chí đạt |
|---|---|
| Contract có được plugin nhận diện? | Có generated tests tương ứng |
| Generated tests kế thừa đúng base class? | FQN và classpath chính xác |
| HTTP adapter phù hợp test mode? | MockMvc/server client setup đúng |
| Spring context và dependency có sẵn? | Bean/test profile được khởi tạo |
| Fixture đúng trạng thái trước request? | Mỗi test chạy riêng lẻ cũng đạt |
| Fixture an toàn khi chạy song song? | Database/schema/namespace không xung đột |
| Security cần kiểm tra có chạy thật? | Không bypass filters ngoài chủ đích |
| Message trigger hoạt động? | Hook đúng signature, verifier/broker nhận message |
| Clock và ID generator có kiểm soát? | Test có thể tái lập, matcher phù hợp |
| CI có thực sự chạy producer tests? | Test report và release gate kiểm tra |
| Stub có đúng nguồn gốc? | Artifact/version có thể truy vết tới build đạt test |

Checklist này xác minh **thiết lập kỹ thuật**, không thay thế vòng Content QA của tài liệu hoặc các bài kiểm thử chuyên sâu về bảo mật/hiệu năng.

## 17. Sai lầm phổ biến

**“Có DSL thì mọi test tự chạy được.”** Không. Plugin có thể sinh code, nhưng producer test vẫn cần Spring context, adapter, fixture hoặc message hook thích hợp.

**“Chỉ cần base class là mọi producer đều tuân thủ hợp đồng.”** Không. Base class hỗ trợ chạy test, còn producer implementation phải trả đúng hành vi trong DSL.

**“Base class nên chứa tất cả assertions.”** Không cần. Phần lớn assertions thuộc generated tests từ contract; những kiểm tra bảo mật/semantic đặc thù có thể đặt ở integration tests riêng.

**“`@BeforeEach` reset DB đã bảo đảm không có race.”** Chưa chắc, vì hai tests có thể cùng reset một DB khi chạy song song.

**“`@DirtiesContext` xóa cả database và broker.”** Không; tài nguyên bên ngoài Spring context cần cleanup riêng.

**“`@Transactional` luôn rollback request qua HTTP server thật.”** Không mặc định; request có thể chạy trong transaction khác.

**“Dùng standalone MockMvc thì đã kiểm tra Spring Security.”** Chỉ đúng nếu filter chain được tích hợp đầy đủ. Nếu không, test có thể xanh dù không xác thực.

**“Cần sửa file generated khi thiếu bean.”** Không. Sửa cấu hình build/base class/test context rồi generate lại.

**“Consumer Stub Runner xanh đủ để chứng minh implementation producer.”** Không. Nó kiểm tra consumer trên stub; producer verification chạy trên implementation mới là bằng chứng phía cung cấp.

**“Mọi HTTP/message contract dùng chung một base class.”** Không bắt buộc. Có thể tách theo test mode/hạ tầng nếu plugin hỗ trợ mapping đúng.

## 18. Câu hỏi tự kiểm tra

1. **Base class khác contract ở đâu?** Contract định nghĩa hành vi; base class cung cấp môi trường để generated tests chạy trên producer.
2. **`RestAssuredMockMvc.mockMvc(mockMvc)` làm gì?** Gắn MockMvc từ Spring MVC test context để generated tests sử dụng RestAssured MockMvc adapter.
3. **Tại sao generated tests cần kế thừa đúng FQN?** Để dùng context, fixture và setup; sai tên/package dẫn đến lỗi compile hoặc runtime.
4. **Base class có tự suy ra dữ liệu `ORDER-42` từ DSL không?** Không. Producer phải seed fixture.
5. **Tại sao test `404` cần fixture?** Phải bảo đảm ID được yêu cầu không tồn tại.
6. **Nếu test đọc đơn chỉ đạt sau test tạo đơn, có ổn không?** Không nếu hai tests được coi là độc lập; phải chuẩn bị dữ liệu riêng.
7. **`@BeforeEach` có đủ cho chạy song song trên cùng DB không?** Không, phải bảo đảm isolation.
8. **`@Transactional` có rollback mọi HTTP request không?** Không mặc định; tùy transaction boundary.
9. **MockMvc không có security filters có kiểm chứng authentication không?** Không.
10. **`triggeredBy('publishOrderPaid()')` có vai trò gì?** Tên hook để generated producer message test kích hoạt hành vi phát event.
11. **`label` có giống `triggeredBy` không?** Không. Label nhận diện kịch bản stub, trigger là hook producer verification.
12. **Khi generated test thiếu base class, nên sửa file generated không?** Không, sửa plugin config/classpath hoặc base source.
13. **Có thể dùng một base class cho cả HTTP và message không?** Có nếu cùng hạ tầng phù hợp, nhưng không bắt buộc.
14. **Stub Runner xanh có chứng minh producer trả JSON đúng không?** Chưa; cần generated producer tests trên implementation.
15. **Trước khi publish stub CI phải xác minh gì?** Sinh và chạy producer contract tests thật, fixture ổn định, base class đúng, mọi assertions cần thiết đạt.

## Kết luận

**Base test class là cầu nối giữa hợp đồng và implementation producer** trong Spring Cloud Contract. Nó chuẩn bị **Spring test context, HTTP/message adapter, fixture, security test và hook kích hoạt** để các generated tests xác minh hành vi đã được định nghĩa bằng Groovy/YAML DSL. Khi cấu hình Maven/Gradle trỏ đúng base class, test mode phù hợp, dữ liệu cô lập và producer verification chạy bắt buộc trong CI, stub phát hành cho consumer qua **Stub Runner** mới có cơ sở tin cậy để phát hiện thay đổi API không tương thích.
