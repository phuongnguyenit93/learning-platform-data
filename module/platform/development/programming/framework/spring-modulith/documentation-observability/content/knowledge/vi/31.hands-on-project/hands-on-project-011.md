# Viết test cho endpoint và telemetry

## 1. Bài thực hành tổng hợp: kiểm thử điều gì?

Trong ứng dụng Spring Boot được tổ chức bằng **Spring Modulith**, một HTTP endpoint có thể trả `202 Accepted` ngay sau khi đơn hàng được ghi nhận, còn listener của application module khác tiếp tục xử lý sự kiện bất đồng bộ. Nếu chỉ kiểm tra HTTP status, nhóm phát triển chưa biết transaction có commit, sự kiện có được nhận hay hệ thống observability có ghi lại quá trình xử lý.

Bài **Viết test cho endpoint và telemetry** thuộc chương **Thực hành tổng hợp** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Mục tiêu là nối các kỹ thuật sinh tài liệu ranh giới application module, **module graph**, Spring Boot **Actuator**, **event metrics**, **tracing** và **context propagation** thành một bộ kiểm thử có thể tái hiện kết quả.

Sau bài này, người học có thể:

1. Viết test cho HTTP endpoint bằng MockMvc, xác nhận status, JSON contract và xử lý đầu vào lỗi.
2. Viết test xác minh ranh giới module bằng `ApplicationModules.verify()` và kiểm tra event được phát bằng `PublishedEvents`.
3. Kiểm thử listener xử lý sau commit, bất đồng bộ và có tác dụng phụ bền vững.
4. Xác minh custom `Observation` tạo metric đúng tên, có tag **low-cardinality** và không lộ event ID thành metric label.
5. Kiểm tra Actuator/Prometheus, trace và context propagation đúng theo phạm vi mà mỗi loại test có thể chứng minh.
6. Kết hợp smoke test với backend thật và thiết lập tiêu chí chấp nhận trong CI/CD.

> Ví dụ sử dụng **Java 17+, Spring Boot 3.x và một nhánh Spring Modulith 1.x tương thích** để minh họa các import kiểm thử. Với Spring Boot 4.x / Spring Modulith 2.x, cần đối chiếu phiên bản starter, package test support và release notes. Không gắn phiên bản tùy ý cho các dependency được Boot/Modulith BOM quản lý. Các đoạn code theo domain giả định được đánh dấu rõ, cần hoàn thiện repository và dữ liệu thử trước khi chạy.

## 2. Hệ thống minh họa và bằng chứng cần thu thập

Giả sử ứng dụng bán hàng có hai application module:

- **orders:** nhận `POST /api/orders`, kiểm tra request, ghi đơn hàng trong transaction rồi phát `OrderPlaced`.
- **shipping:** xử lý `OrderPlaced` bằng `@ApplicationModuleListener` để tạo yêu cầu giao hàng trong một transaction riêng.

Chúng ta muốn quan sát toàn bộ chuỗi:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as HTTP client
    participant O as orders module
    participant D as Database
    participant P as Event infrastructure/registry
    participant S as shipping listener
    participant T as Telemetry pipeline

    C->>O: POST /api/orders
    O->>D: Lưu Order trong transaction
    O->>P: publishEvent(OrderPlaced)
    O->>T: Observation order submission / event publish
    O->>D: Commit transaction nguồn
    O-->>C: 202 Accepted + orderId, eventId
    P-->>S: Dispatch listener sau commit
    S->>D: Tạo shipment (transaction riêng)
    S->>T: Observation, metric, log, trace
    S-->>P: Đánh dấu publication completed nếu có registry
~~~

Sơ đồ trình bày **hành vi logic**. Thứ tự chính xác của HTTP response, dispatch và ghi nhận publication phụ thuộc transaction/listener/executor. Đặc biệt, một listener rất nhanh có thể chạy gần như đồng thời với lúc trả HTTP response; không nên viết test yêu cầu listener *chưa* chạy ngay tại thời điểm response.

Các điểm cần bằng chứng:

| Tín hiệu | Chứng minh được | Chưa chứng minh được |
| --- | --- | --- |
| HTTP 202 và response JSON | Endpoint chấp nhận request theo hợp đồng | Listener đã xử lý xong |
| Record order trong database | Order được ghi và nhìn thấy sau commit | Shipping đã thành công |
| `PublishedEvents` chứa `OrderPlaced` | Application service đã phát event | Listener đã commit |
| Có shipment record duy nhất | Hậu điều kiện nghiệp vụ đã được lưu | Backend tracing đã nhận span |
| Metric `shop.order.submit` tăng | Observation của thao tác đã được ghi vào registry | Trace đã được export |
| Span tồn tại trong in-memory exporter | Tracing instrumentation tạo span | Collector staging đã nhận span |
| Trace trong Jaeger/Tempo | Trace đã đi qua pipeline export | Publication registry đã đánh dấu completed |
| Publication completed | Registry ghi nhận listener hoàn tất theo semantics implementation | Không có duplicate side effect từ các lần thử trước |

Nguyên tắc xuyên suốt: **mỗi assertion cần tương ứng với một hành vi cụ thể**. Không xem một chỉ số duy nhất là bằng chứng cho toàn bộ quy trình.

## 3. Chia tầng kiểm thử hợp lý

| Tầng kiểm thử | Công cụ | Mục tiêu | Chi phí tương đối |
| --- | --- | --- | --- |
| Controller slice | `@WebMvcTest`, MockMvc, Mockito | HTTP status, JSON request/response, validation mapping | Thấp |
| Module architecture | `ApplicationModules.verify()` | Ranh giới package và phụ thuộc được công bố | Thấp |
| Module event | `@ApplicationModuleTest`, `PublishedEvents` | Module orders phát đúng sự kiện | Vừa |
| Metric/Observation unit | `SimpleMeterRegistry` + `ObservationRegistry` | Tên meter, tags, count, low/high cardinality | Thấp |
| Integration | `@SpringBootTest`, Testcontainers, Awaitility | Controller → transaction → async listener → persisted side effect | Cao hơn |
| Actuator contract | HTTP client hoặc MockMvc | Health/metrics/module endpoints và quyền truy cập | Vừa |
| Tracing integration | Test exporter / collector nhận OTLP | Span attributes, trace linkage, export | Vừa đến cao |
| Staging smoke | HTTP tới ứng dụng đã deploy + backend thật | Hành vi hạ tầng, network, database và telemetry end-to-end | Cao |

Không cần chạy Docker, Collector hoặc toàn bộ ứng dụng cho **mọi** test. Những assertion về nhãn metric có thể thực hiện với registry trong bộ nhớ; phần xuất OTLP thật được kiểm tra ở tầng thích hợp.

## 4. Dependencies và cấu hình kiểm thử

Ví dụ Gradle Groovy DSL cho ứng dụng Spring Boot 3.x và Spring Modulith tương thích. Giả định đã import Spring Boot BOM và Spring Modulith BOM phù hợp:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")

    implementation("org.springframework.modulith:spring-modulith-starter-core")

    runtimeOnly("org.postgresql:postgresql")

    // Tracing của ứng dụng khi chạy thật:
    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")

    // Registry publication lưu bền nếu chọn JDBC:
    implementation("org.springframework.modulith:spring-modulith-starter-jdbc")

    // Test:
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.modulith:spring-modulith-starter-test")
    testImplementation("org.springframework.modulith:spring-modulith-docs")
    testImplementation("io.micrometer:micrometer-observation-test")

    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
    testImplementation("org.awaitility:awaitility")
}
~~~

Tùy phiên bản Spring Modulith, starter core và starter JDBC có thể kéo những thành phần khác nhau; dùng dependency tree để kiểm tra runtime classpath. Nếu dự án đã dùng JPA registry, không tự ý thêm JDBC registry song song. Dự án cần schema migration cho bảng domain và publication registry khi lưu bền.

Trong test, tránh để OTLP exporter mặc định đẩy span tới backend production. Có thể tắt exporter cho test nội bộ hoặc cung cấp endpoint giả; ở smoke test staging mới định tuyến tới Collector staging thật.

Cấu hình `src/test/resources/application-test.yml` minh họa:

~~~yaml
spring:
  application:
    name: shop-modulith-test

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  tracing:
    sampling:
      probability: 1.0
~~~

Cấu hình trên chưa khai báo external telemetry exporter để không phụ thuộc backend thật ở mọi unit/integration test. Cách vô hiệu hóa exporter hoặc sử dụng exporter in-memory phụ thuộc vào starter/phiên bản. Với các test Spring Boot, **observability thường không được tự cấu hình đầy đủ** trừ khi chủ động bật bằng test annotation/cấu hình phù hợp; lưu ý này đặc biệt quan trọng khi kiểm tra metrics/traces tự động.

## 5. Chuẩn bị contract và mã nghiệp vụ dùng xuyên các test

Một bộ test tự chứa nên có hợp đồng API và domain event rõ ràng. Ví dụ API:

~~~http
POST /api/orders
Content-Type: application/json

{"clientReference":"IT-ORDER-001"}
~~~

Kết quả thành công:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "orderId": "c1cc62d1-9e60-4795-a0a0-6b6222672091",
  "eventId": "9ad998cc-75c6-4cf3-a281-dc7a739975e8"
}
~~~

`202 Accepted` ở đây nghĩa là order đã được chấp nhận để tiếp tục xử lý; client **không nên hiểu** shipment đã hoàn tất.

### 5.1. Request, response và event

~~~java
package com.example.shop.orders;

import java.util.UUID;

public record CreateOrderRequest(String clientReference) {}
public record OrderAccepted(UUID orderId, UUID eventId) {}
public record OrderPlaced(UUID eventId, UUID orderId) {}
~~~

Trong Java thực tế, các public top-level record này cần đặt ở **các file nguồn tương ứng**. Chúng được gộp vào một khối để tập trung trình bày giao diện.

`OrderPlaced` nằm trong API công khai của module orders, để shipping có thể nhận sự kiện mà không phụ thuộc lớp nội bộ. Một `eventId` ổn định hỗ trợ đối chiếu log/trace và idempotency khi cần xử lý lại.

### 5.2. Controller đơn giản để thực hành

~~~java
package com.example.shop.orders;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@RestController
@RequestMapping("/api/orders")
public class OrdersController {

    private final OrderApplicationService service;

    public OrdersController(OrderApplicationService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<OrderAccepted> create(
            @RequestBody CreateOrderRequest request) {

        if (request == null ||
            request.clientReference() == null ||
            request.clientReference().isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "clientReference is required");
        }

        return ResponseEntity.accepted()
            .body(service.submit(request.clientReference()));
    }
}
~~~

Ví dụ trên tự kiểm tra `clientReference` để minh họa test validation cơ bản. Ứng dụng thực tế nên dùng Jakarta Bean Validation với `@Valid`, `@NotBlank` và mapping lỗi nhất quán, nếu đã có starter validation.

### 5.3. Publisher trong transaction

~~~java
package com.example.shop.orders;

import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrdersRepository repository;
    private final ApplicationEventPublisher publisher;
    private final OrderTelemetry telemetry;

    public OrderApplicationService(
            OrdersRepository repository,
            ApplicationEventPublisher publisher,
            OrderTelemetry telemetry) {
        this.repository = repository;
        this.publisher = publisher;
        this.telemetry = telemetry;
    }

    @Transactional
    public OrderAccepted submit(String clientReference) {
        UUID orderId = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();

        telemetry.observeSubmit(eventId, () -> {
            repository.insert(orderId, clientReference);
            publisher.publishEvent(new OrderPlaced(eventId, orderId));
        });

        return new OrderAccepted(orderId, eventId);
    }
}
~~~

`OrdersRepository.insert` là phương thức repository giả định cần triển khai bằng JPA/JDBC thật. `OrderTelemetry` sẽ được định nghĩa ở phần metric. Lưu ý Observation trong method được bọc **kết thúc trước transaction commit cuối method**, nên nó không phải metric “listener completed” hoặc “database commit latency”.

### 5.4. Listener sau commit

~~~java
package com.example.shop.shipping;

import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;
import com.example.shop.orders.OrderPlaced;

@Component
public class OrderPlacedListener {

    private final ShippingService shipping;

    public OrderPlacedListener(ShippingService shipping) {
        this.shipping = shipping;
    }

    @ApplicationModuleListener
    public void on(OrderPlaced event) {
        shipping.createShipmentOnce(
            event.orderId(), event.eventId());
    }
}
~~~

`ShippingService` được giả định có **idempotency**, ví dụ ràng buộc unique theo eventId hoặc orderId. Với các dòng Spring Modulith thông dụng, `@ApplicationModuleListener` cung cấp listener sau commit, bất đồng bộ và transaction riêng; kiểm tra annotation semantics của phiên bản đang dùng.

## 6. Test endpoint ở tầng controller

Trước hết viết test nhanh chỉ kiểm tra **hợp đồng HTTP**. Ví dụ Boot 3.5 / Spring Framework 6.2 với `@MockitoBean`:

~~~java
package com.example.shop.orders;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import org.springframework.http.MediaType;

@WebMvcTest(OrdersController.class)
class OrdersControllerWebTest {

    @Autowired MockMvc mvc;
    @MockitoBean OrderApplicationService service;

    @Test
    void acceptsValidRequestAndReturnsIds() throws Exception {
        var orderId = UUID.randomUUID();
        var eventId = UUID.randomUUID();

        when(service.submit("WEB-1"))
            .thenReturn(new OrderAccepted(orderId, eventId));

        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"clientReference\":\"WEB-1\"}"))
            .andExpect(status().isAccepted())
            .andExpect(jsonPath("$.orderId").value(orderId.toString()))
            .andExpect(jsonPath("$.eventId").value(eventId.toString()));

        verify(service).submit("WEB-1");
    }

    @Test
    void rejectsBlankReferenceBeforeCallingService() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"clientReference\":\"\"}"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Tại đây, `OrderApplicationService` là mock nên test **không chứng minh** event đã được phát hoặc database đã ghi dữ liệu. Đó là điều có chủ đích ở tầng controller slice.

Nếu ứng dụng bật Spring Security cho API, MockMvc có thể nhận 401/403 trước khi vào controller. Cấu hình authentication test (`@WithMockUser`, request post-processor hoặc test security filter) theo chính sách của ứng dụng thay vì vô hiệu hóa bảo mật một cách vô điều kiện.

### Các assertion endpoint nên có

| Ca | Request | Kết quả kỳ vọng |
| --- | --- | --- |
| Hợp lệ | `clientReference="WEB-1"` | HTTP 202, có orderId/eventId dạng UUID |
| Rỗng | `clientReference=""` | HTTP 400 |
| Thiếu field | `{}` | HTTP 400 |
| JSON lỗi cú pháp | `{"clientReference":` | HTTP 400 trước khi gọi service |
| Content type sai | `text/plain` | HTTP 415 nếu endpoint chỉ nhận JSON |
| Không đủ quyền | Token/user không được phép | 401/403 theo security contract |
| Request lặp | Cùng khóa idempotency nghiệp vụ | Phản hồi theo chính sách được công bố |

Không yêu cầu test mọi trạng thái trong một method. Một test nên có tên mô tả **một hành vi** và assertion đủ để phát hiện regression cụ thể.

## 7. Test hợp đồng module và tài liệu kiến trúc

Chạy kiểm thử ranh giới độc lập với giao thức HTTP:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModulithStructureTests {

    @Test
    void applicationModuleDependenciesAreValid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`ShopApplication` là Spring Boot entrypoint giả định. Nếu shipping gọi trực tiếp lớp `orders.internal` không được công bố, hoặc tồn tại chu trình phụ thuộc bị cấm, `verify()` giúp phát hiện tùy cấu trúc module và quy tắc đã khai báo.

Để sinh module graph khi build:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModulithDocumentationTests {

    @Test
    void generatesDocumentationForCurrentSource() {
        var modules = ApplicationModules.of(ShopApplication.class);
        new Documenter(modules).writeDocumentation();
    }
}
~~~

`Documenter` cần dependency docs và ghi tài liệu vào vị trí do thư viện/build cấu hình. Không dùng file graph sinh trước đó để chứng minh cấu trúc của code vừa thay đổi; CI nên kiểm tra graph theo **cùng commit** được deploy.

**Phân biệt bằng chứng:** một graph hợp lệ không chứng minh request đã chạy qua shipping; trace runtime mới cho biết execution path của một lần gọi cụ thể.

## 8. Test application event bằng PublishedEvents

Spring Modulith cung cấp `PublishedEvents` để kiểm tra **event được publish** trong một module test.

~~~java
package com.example.shop.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class OrdersModuleEventTests {

    @Autowired OrderApplicationService service;

    @Test
    void publishesEventWithMatchingOrderId(PublishedEvents events) {
        var accepted = service.submit("MODULE-TEST-1");

        assertThat(events.ofType(OrderPlaced.class))
            .anyMatch(event ->
                event.orderId().equals(accepted.orderId()) &&
                event.eventId().equals(accepted.eventId()));
    }
}
~~~

**Giới hạn của test:** `PublishedEvents` chứng minh publication đã xảy ra theo instrumentation của test. Nó **không chứng minh** shipping listener đã nhận, side effect đã commit hoặc có trace trong backend.

Module test cần repository, transaction manager, dữ liệu thử và các bean mà orders sử dụng. Nếu cấu hình module bootstrap cô lập shipping, việc không khởi tạo shipping listener là bình thường.

### Tránh vấn đề transaction trong test

Một listener có `AFTER_COMMIT` chỉ chạy khi transaction nguồn commit. Nếu method test có `@Transactional` và framework rollback ở cuối, listener sau commit có thể không chạy dù `PublishedEvents` đã thấy event. Vì thế:

- Test publication có thể kiểm tra event độc lập với listener.
- Test listener end-to-end nên để transaction của `OrderApplicationService.submit` **commit thật** trước khi chờ kết quả.
- Không thêm `@Transactional` ở lớp test end-to-end trừ khi thiết kế rõ cơ chế commit trong test.

## 9. Test tích hợp endpoint → event → listener với database thật

Để kiểm tra side effect, dùng PostgreSQL qua Testcontainers thay vì giả định một unit test hoặc mock đã kiểm chứng transaction.

Ví dụ khung integration test với `MockMvc`, Testcontainers và Awaitility:

~~~java
import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import com.jayway.jsonpath.JsonPath;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Testcontainers
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class OrderFlowIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry props) {
        props.add("spring.datasource.url", postgres::getJdbcUrl);
        props.add("spring.datasource.username", postgres::getUsername);
        props.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired MockMvc mvc;
    @Autowired ShippingQueries shippingQueries;

    @Test
    void acceptedOrderEventuallyCreatesOneShipment() throws Exception {
        var reference = "IT-" + UUID.randomUUID();

        String response = mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"clientReference\":\"" + reference + "\"}"))
            .andExpect(status().isAccepted())
            .andReturn()
            .getResponse()
            .getContentAsString();

        UUID orderId = UUID.fromString(
            JsonPath.read(response, "$.orderId"));

        await().atMost(Duration.ofSeconds(10))
            .untilAsserted(() ->
                assertThat(shippingQueries.countByOrderId(orderId))
                    .isEqualTo(1L));
    }
}
~~~

`ShippingQueries` là giao diện truy vấn hậu điều kiện do dự án cung cấp. Database/schema migration, implementation repository và module listener phải tồn tại; đây là **khung tích hợp**, không phải ứng dụng mẫu hoàn chỉnh. Để xác minh registry bền vững, thêm đúng schema/cấu hình Spring Modulith publication registry tương ứng.

Vì sao dùng `Awaitility`?

- Listener bất đồng bộ có thể hoàn thành sau lúc MockMvc nhận response.
- `Thread.sleep(1000)` vừa chậm vừa dễ flaky khi CI có tải.
- `untilAsserted` sẽ thử lại assertion đến khi đạt hoặc hết timeout, cung cấp lỗi có ý nghĩa.

**Không chỉ đếm shipment một lần:** với yêu cầu chống duplicate khi retry, cần test riêng trường hợp event được xử lý lại và xác minh unique constraint/idempotency.

### Kiểm tra transaction rollback

Thêm một service operation cố ý phát event rồi ném exception trước khi transaction commit. Kiểm tra order không được lưu và shipping không tạo shipment cho event đó. Với trường hợp “không xảy ra sự kiện”, đợi một khoảng **có giới hạn theo thiết kế** rồi xác minh không có side effect; không dùng quan sát tức thời để khẳng định listener sẽ không chạy muộn.

## 10. Instrumentation phục vụ bài test telemetry

Để có metric chủ đích và dễ test, tạo một helper Micrometer Observation ghi nhận đoạn thực thi thuộc module orders:

~~~java
package com.example.shop.orders;

import java.util.UUID;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Component;

@Component
public class OrderTelemetry {

    private final ObservationRegistry registry;

    public OrderTelemetry(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void observeSubmit(UUID eventId, Runnable operation) {
        Observation.createNotStarted("shop.order.submit", registry)
            .lowCardinalityKeyValue("module.identifier", "orders")
            .lowCardinalityKeyValue("operation", "submit")
            .highCardinalityKeyValue("event.id", eventId.toString())
            .observe(operation);
    }
}
~~~

Ý nghĩa nhãn:

| Key | Giá trị ví dụ | Cardinality | Mục đích |
| --- | --- | --- | --- |
| `module.identifier` | `orders` | Thấp: tập module hữu hạn | Nhóm metric/span theo module |
| `operation` | `submit` | Thấp: enum operation | Đọc throughput và latency |
| `event.id` | Một UUID riêng của event | Cao | Đối chiếu một event trong trace/log |

Micrometer Observation phân biệt `lowCardinalityKeyValue` và `highCardinalityKeyValue`: với handler thông dụng, low-cardinality key-values được dùng làm metric labels; high-cardinality values có thể đưa vào tracing nhưng **không nên được dùng làm metric labels**.

**Không gắn** `orderId`, `eventId`, raw URL hay email thành low-cardinality tag. Nếu có hàng nghìn giá trị, số time series của backend metric sẽ tăng mạnh.

## 11. Test Observation bằng registry trong bộ nhớ

Một test nhanh có thể tự khởi tạo `ObservationRegistry` và `SimpleMeterRegistry` mà không cần Spring Boot hay Collector:

~~~java
import java.util.UUID;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OrderTelemetryMetricsTest {

    @Test
    void metricUsesOnlyBoundedModuleTags() {
        try (var meters = new SimpleMeterRegistry()) {
            var observations = ObservationRegistry.create();

            observations.observationConfig()
                .observationHandler(
                    new DefaultMeterObservationHandler(meters));

            var telemetry = new OrderTelemetry(observations);

            for (int i = 0; i < 20; i++) {
                telemetry.observeSubmit(UUID.randomUUID(), () -> {});
            }

            Timer timer = meters.get("shop.order.submit")
                .tag("module.identifier", "orders")
                .tag("operation", "submit")
                .timer();

            assertThat(timer.count()).isEqualTo(20);

            // Event ID khác nhau không tạo metric labels.
            assertThat(timer.getId().getTag("event.id")).isNull();

            long matchingTimers = meters.getMeters().stream()
                .filter(m -> m.getId().getName()
                    .equals("shop.order.submit"))
                .count();

            assertThat(matchingTimers).isEqualTo(1);
        }
    }
}
~~~

Test kiểm tra chính xác:

- `Observation` được đăng ký với handler tạo `Timer`.
- Hai mươi eventId khác nhau vẫn tạo **một** tập metric labels ổn định.
- Metric có tên đã định, module/operation đúng, count bằng 20.

Đây là test metrics **trong bộ nhớ**; không chứng minh Prometheus đã scrape hoặc OTLP exporter gửi span. Nếu cài nhiều Observation handlers thì tên và tag bổ sung có thể khác; nên giữ test helper này độc lập với auto instrumentation của ứng dụng.

### Test đường lỗi của Observation

Nếu `operation` ném exception, test cần xác nhận exception không bị nuốt và Observation đã kết thúc:

~~~java
assertThatThrownBy(() ->
    telemetry.observeSubmit(UUID.randomUUID(), () -> {
        throw new IllegalStateException("test failure");
    }))
    .isInstanceOf(IllegalStateException.class);
~~~

Đoạn này dùng static import `org.assertj.core.api.Assertions.assertThatThrownBy` và được thêm trong test fixture có `telemetry` đã khởi tạo. Với Micrometer handler mặc định, lỗi có thể được phản ánh thành tag `error` hữu hạn theo **loại exception**. Không đưa `exception.getMessage()` hoặc SQL text vào metric tags.

## 12. Test event listener metrics

Trong module shipping, nên đo **attempt** theo event type và kết quả, thay vì nhầm publication count với số event hoàn tất:

~~~java
package com.example.shop.shipping;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class ShippingAttemptMetrics {

    private final Counter succeeded;
    private final Counter failed;

    public ShippingAttemptMetrics(MeterRegistry registry) {
        succeeded = Counter.builder("shop.shipping.attempts")
            .tag("module.identifier", "shipping")
            .tag("event.type", "OrderPlaced")
            .tag("outcome", "success")
            .register(registry);

        failed = Counter.builder("shop.shipping.attempts")
            .tag("module.identifier", "shipping")
            .tag("event.type", "OrderPlaced")
            .tag("outcome", "failure")
            .register(registry);
    }

    public void success() { succeeded.increment(); }
    public void failure() { failed.increment(); }
}
~~~

Có thể gắn vào listener:

~~~java
@ApplicationModuleListener
public void on(OrderPlaced event) {
    try {
        shipping.createShipmentOnce(
            event.orderId(), event.eventId());

        metrics.success();
    } catch (RuntimeException exception) {
        metrics.failure();
        throw exception;
    }
}
~~~

Đây là phiên bản **thay thế phần method listener** ở mục 5 sau khi inject thêm `ShippingAttemptMetrics` vào constructor; không đăng ký một listener thứ hai cho cùng event chỉ để đo metric.

Quan trọng: `success()` ở cuối method ghi nhận **handler trả về bình thường**, không nhất thiết chứng minh transaction ngoài method và bước đánh dấu publication completed đã commit. Vì vậy đặt tên `attempts` rõ ràng; muốn đo completion bền vững phải lấy tín hiệu từ registry hoặc kiểm tra dữ liệu hậu điều kiện.

Test đơn vị cho Counter:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class ShippingAttemptMetricsTest {

    @Test
    void countsOutcomesWithoutPerEventLabels() {
        try (var registry = new SimpleMeterRegistry()) {
            var metrics = new ShippingAttemptMetrics(registry);

            metrics.success();
            metrics.success();
            metrics.failure();

            var success = registry.get("shop.shipping.attempts")
                .tag("module.identifier", "shipping")
                .tag("event.type", "OrderPlaced")
                .tag("outcome", "success")
                .counter();

            var failure = registry.get("shop.shipping.attempts")
                .tag("outcome", "failure")
                .counter();

            assertThat(success.count()).isEqualTo(2);
            assertThat(failure.count()).isEqualTo(1);

            assertThat(registry.getMeters())
                .allSatisfy(m ->
                    assertThat(m.getId().getTag("event.id"))
                        .isNull());
        }
    }
}
~~~

Test không dùng UUID thành Counter label nên số meter chỉ phụ thuộc các tag có danh mục hữu hạn. Khi retry cùng eventId, `attempts` có thể tăng nhiều hơn số event duy nhất — đó là hành vi đúng với tên và định nghĩa phép đo.

## 13. Test Actuator endpoint và dữ liệu metrics

Actuator trả về **HTTP contract** của hệ thống observability. Điều kiện để test hữu ích:

- Có `spring-boot-starter-actuator`.
- `health`, `metrics` được expose trong profile test.
- Cấu hình security dành cho test thể hiện đúng quyền truy cập mong muốn.
- Có meter thực sự được tạo trước khi assert tên một metric cụ thể.

Ví dụ test bằng HTTP với server ngẫu nhiên (Boot 3.x):

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class ActuatorEndpointTest {

    @Autowired TestRestTemplate http;

    @Test
    void healthEndpointResponds() {
        var response = http.getForEntity(
            "/actuator/health", String.class);

        assertThat(response.getStatusCode())
            .isEqualTo(HttpStatus.OK);
        assertThat(response.getBody())
            .contains("status");
    }
}
~~~

Ví dụ này giả định health endpoint mở cho client test và các health indicators được cấu hình đang `UP`. Nếu môi trường bật Spring Security, cần test bằng credential hợp lệ; nếu management server chạy ở **port riêng**, TestRestTemplate hướng tới application port chưa chắc truy cập được Actuator. Lúc đó phải dùng management port thực tế hoặc công cụ test phù hợp.

Test metrics endpoint tương tự:

~~~java
var response = http.getForEntity(
    "/actuator/metrics", String.class);

assertThat(response.getStatusCode())
    .isEqualTo(HttpStatus.OK);
assertThat(response.getBody()).contains("names");
~~~

Đoạn này giả định biến `http` và import AssertJ ở test phía trên. **Không chỉ kiểm tra HTTP 200** rồi tuyên bố metrics chính xác: cần tạo traffic, tìm meter `shop.order.submit` và assert tags/counter phù hợp. Test đó chỉ đáng tin khi observability đã thực sự được bật trong test context; ở nhiều phiên bản Spring Boot có thể dùng `@AutoConfigureObservability` hoặc cấu hình tương ứng để không bị thay ObservationRegistry bằng no-op.

### Kiểm thử Modulith Actuator

Nếu đã cài Modulith Actuator/Insight và expose endpoint module, kiểm tra `/actuator/modulith` bằng role được phép. Assertion nên xác minh các identifier `orders`, `shipping` thực tế và không lộ thông tin không được công khai.

`/actuator/modulith` là endpoint dành cho cấu hình/phiên bản hỗ trợ; nếu không cài extension tương ứng, **không kỳ vọng** endpoint tự xuất hiện chỉ vì có Spring Modulith core.

### Kiểm thử quyền truy cập Actuator

Bổ sung test security:

- Client không xác thực có được phép gọi `/actuator/health` theo chính sách không?
- Client không đủ quyền bị từ chối ở `/actuator/metrics` và `/actuator/modulith` không?
- Role monitoring có thể truy cập đúng endpoint mà không được mở API nghiệp vụ ngoài quyền không?
- Endpoint không hiển thị secret, access token, JDBC URL có mật khẩu hoặc dữ liệu nhạy cảm?

Đặt assertion theo **security contract của dự án**. Một bộ test chỉ mở toàn bộ Actuator bằng `permitAll()` để chạy qua chưa kiểm chứng mức bảo vệ production.

## 14. Test tracing và context propagation

Tracing đo mối quan hệ thực thi: request span, module interaction span, event publisher span, listener span và các thao tác database/HTTP được instrument. Khác metrics, **span** có thể mang các thuộc tính high-cardinality như `event.id` khi chính sách dữ liệu cho phép.

Có ba cấp độ test:

1. **Observation unit test:** gọi helper, kiểm tra tên và low/high tags; không cần exporter.
2. **Tracing integration test:** dùng in-memory span exporter hoặc một collector test để xác minh span được sinh và exporter nhận.
3. **Staging smoke test:** truy vấn Jaeger/Tempo/trace backend thật và xác nhận trace đi qua pipeline.

Đừng đánh đồng các cấp độ. Nếu test chỉ assert một `ObservationRegistry` có timer, chưa chứng minh có span hoặc OTLP export.

### 14.1. Context propagation ở executor

Nếu listener bất đồng bộ được thực thi trên thread pool, active trace context có thể bị mất. Ví dụ cấu hình `ContextPropagatingTaskDecorator` với Spring Framework phiên bản hỗ trợ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class AsyncTelemetryConfiguration {

    @Bean(name = "taskExecutor")
    ThreadPoolTaskExecutor taskExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("events-");
        executor.setTaskDecorator(
            new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

Test cần xác nhận listener thực sự dùng executor có decorator; nếu ứng dụng có `AsyncConfigurer` hoặc nhiều executor, bean tên `taskExecutor` có thể không phải executor được chọn.

**Giới hạn của propagation:** decorator chụp context còn hoạt động **tại thời điểm submit task**. Trong luồng `AFTER_COMMIT`, span của publisher có thể kết thúc trước khi listener được schedule. Do đó không thể yêu cầu **mọi** span listener có cùng traceId với HTTP request một cách tuyệt đối. Cần eventId/correlationId ổn định để liên kết nhiều trace, đặc biệt khi retry sau restart.

### 14.2. Kịch bản test propagation

| Kịch bản | Assertion phù hợp | Không nên assert |
| --- | --- | --- |
| Cùng thread, có active span | Observed work nhìn thấy trace context | Span ID luôn là một giá trị cố định |
| Worker thread, decorator bật | Context đang hoạt động ở lúc submit được phục hồi trong task | Tất cả AFTER_COMMIT listener cùng trace với HTTP |
| Worker thread, decorator tắt | Hậu điều kiện vẫn hoàn tất; đối chiếu eventId | Thiếu traceId đồng nghĩa listener không chạy |
| Retry sau restart | EventId giữ nguyên, attempt được phân biệt | TraceId phải giữ nguyên qua restart |
| Sampling thấp | Sự kiện vẫn xử lý bình thường | Mọi request phải xuất hiện trong trace backend |

Đối với test tích hợp exporter, bật sampling 100% **chỉ trong môi trường test** và dùng exporter nhận dữ liệu tại chỗ. Với pipeline thật, ngoài span name cần xác minh service name, timestamp, attributes có kiểm soát và mối liên hệ quan sát được. Vì export thường bất đồng bộ, dùng polling có timeout, không dựa vào `Thread.sleep` cố định.

### 14.3. Khi nào dùng Micrometer Observation test utilities?

Dependency `micrometer-observation-test` hỗ trợ kiểm tra Observation theo những assertion tiện dụng ở cấp unit/integration. Có thể chọn các test utilities của phiên bản Micrometer đang dùng, hoặc đăng ký handler tùy biến trong `ObservationRegistry` để thu thập các Observation được start/stop.

Tuy nhiên, những assertion này không thay thế **exporter integration**: API test chỉ phản ánh những gì được ghi nhận trong tiến trình. Một test “có Observation tên shop.order.submit” và test “có span shop.order.submit tại Tempo” nên là hai phép xác minh khác nhau.

## 15. Test với event publication registry: hoàn tất và retry

Nếu ứng dụng dùng persistent event publication registry của Spring Modulith, các publication hướng tới transactional listener có thể được ghi lại và đánh dấu completed sau khi listener xử lý thành công.

Hãy viết ít nhất ba test nghiệp vụ:

### 15.1. Thành công

1. Gọi endpoint hợp lệ.
2. Đợi shipment record được tạo và commit.
3. Kiểm tra publication đã hoàn tất theo **API/semantics của implementation** đang sử dụng.
4. Đối chiếu eventId và listener đích nếu dữ liệu registry có thể truy vấn trong test.

### 15.2. Lỗi listener

1. Để shipping service ném exception có kiểm soát.
2. Xác minh không có shipment commit.
3. Xác minh có log/metric thất bại.
4. Xác minh publication **chưa được hoàn tất**; tùy version có thể ở trạng thái outstanding/failed/abandoned khác nhau.
5. Không bắt rồi bỏ exception nếu muốn registry phát hiện lỗi.

### 15.3. Retry/idempotency

1. Khôi phục service rồi kích hoạt resubmission theo API phiên bản đang dùng.
2. Đợi hậu điều kiện shipping xuất hiện.
3. Xác minh shipment count = 1 ngay cả khi cùng event được xử lý nhiều lần.
4. Kiểm tra completion tương ứng và số attempts hợp lý.

Không đặt assertion vào tên bảng/cột registry được sao chép từ phiên bản khác. Schema/transaction semantics và cách khôi phục publication có thể thay đổi theo release train; tài liệu của đúng version là căn cứ để viết test phù hợp.

**Cảnh báo về tính đúng đắn:** persistent registry giúp phục hồi publication nhưng không tự bảo đảm *exactly once*. Giữa commit nghiệp vụ và ghi completion có thể xảy ra lỗi; vì vậy idempotency và unique constraint ở module đích là cần thiết.

## 16. Smoke test trên staging với telemetry backend thật

Một test cục bộ không thể chứng minh network, chứng chỉ, collector pipeline và backend tracing vận hành đúng. Hãy thêm smoke test sau khi deploy **cùng artifact/image digest** lên staging.

~~~mermaid
flowchart TD
    A[Deploy artifact lên staging] --> B[Health/readiness checks]
    B --> C[POST tạo order thử nghiệm]
    C --> D[Đọc order và shipment đã commit]
    D --> E[Đối chiếu eventId, publication status]
    E --> F[Query Actuator/Prometheus]
    F --> G[Query tracing backend theo service/time/eventId]
    G --> H{Đạt đủ bằng chứng?}
    H -- Có --> I[Pass release gate]
    H -- Không --> J[Fail và lưu diagnostics]
~~~

### Ví dụ lời gọi thử nghiệm

~~~bash
curl -i -X POST "https://shop.staging.example.test/api/orders" \
    -H "Content-Type: application/json" \
    -H "X-Test-Run: modulith-smoke-001" \
    --data '{"clientReference":"STG-SMOKE-001"}'
~~~

Cần thu thập lại `orderId` và `eventId` từ response để đối chiếu kết quả; không tái sử dụng `clientReference` gây xung đột qua nhiều lần chạy. Đừng tự coi `X-Test-Run` là metadata được ứng dụng lưu: nó chỉ có tác dụng nếu controller/filter/client đã xử lý.

Sau khi gọi:

- Kiểm tra API và database staging thực sự ghi nhận order.
- Chờ shipment hoặc trạng thái nghiệp vụ cuối cùng với timeout.
- Kiểm tra publication completion/outstanding nếu registry được bật.
- Gọi metrics endpoint và xem meter/tags theo module.
- Tìm trace/spans trong backend staging theo service và khoảng thời gian. Nếu listener thuộc trace khác, dùng eventId/log để liên kết.
- Kiểm tra security của Actuator và đường truy cập nội bộ.
- Ghi lại build version, thời gian chạy, môi trường và test ID để tìm lại sự cố.

Sampling 100% có thể dùng cho một lượt smoke test có kiểm soát; không áp dụng mặc định với lưu lượng production. Với staging nhiều request, cần lọc rõ service/test run để tránh nhầm trace thuộc ca khác.

## 17. Ma trận kiểm thử hoàn chỉnh

| Nhóm | Ca kiểm thử | Kỳ vọng |
| --- | --- | --- |
| HTTP | Valid request | HTTP 202, response chứa orderId/eventId |
| HTTP | Invalid JSON/missing field | HTTP 400, không gọi service |
| HTTP/Security | Truy cập trái phép | 401/403 theo chính sách |
| Module | `ApplicationModules.verify()` | Không vi phạm boundary |
| Docs | `Documenter.writeDocumentation()` | Graph từ commit hiện tại được sinh |
| Publication | `PublishedEvents` | Có `OrderPlaced` với ID khớp |
| Transaction | Rollback publisher | Không có side effect sau commit |
| Async listener | Xử lý hợp lệ | Shipment được commit, số lượng đúng |
| Failure | Listener throw | Exception được ghi nhận; publication chưa completed |
| Recovery | Retry event cũ | Không có duplicate shipment |
| Metric unit | 20 event IDs khác nhau | Count = 20, số series không tăng theo ID |
| Metric unit | Low-cardinality tags | module/operation/outcome đúng danh mục |
| Metric integration | Actuator metrics | Endpoint/meter đúng và được bảo vệ |
| Tracing unit | Observation start/stop | Metadata hợp lệ, không lộ secret |
| Tracing integration | In-memory exporter | Có spans mong đợi khi tracing bật |
| Context | Async executor | Propagation theo thời điểm submit, correlation qua eventId |
| Staging | OTLP Collector + backend | Span thực sự tới trace backend |
| Staging | Prometheus scrape | Metric và labels hiện trên backend |
| Staging | Database/migration | State bền vững và registry hoạt động |

Một vài test không thể chạy độc lập nếu domain chưa triển khai; bảng đóng vai trò **bản thiết kế kiểm chứng** cho dự án thực. Không biến mọi hàng thành một unit test dùng mock vì sẽ đánh mất ý nghĩa tích hợp.

## 18. Các lỗi phổ biến khi test endpoint và telemetry

### 18.1. HTTP 202 nhưng test coi là toàn bộ nghiệp vụ đã thành công

Sai vì listener async có thể thất bại sau lúc response gửi đi. Tách assertion HTTP contract và assertion về hậu điều kiện đã commit; sử dụng Awaitility hoặc polling tương đương.

### 18.2. `PublishedEvents` có event nên kết luận listener chạy thành công

Sai vì `PublishedEvents` tập trung vào publication. Hãy truy vấn dữ liệu shipping và registry để chứng minh completion.

### 18.3. Test method có `@Transactional` nhưng mong listener AFTER_COMMIT chạy

Transaction của test có thể rollback và không kích hoạt listener sau commit. Đưa transaction vào service và để nó commit thật trước khi chờ listener, hoặc dùng TransactionTemplate/thiết kế test transaction có chủ đích.

### 18.4. Tạo `ObservationRegistry` rỗng rồi chờ thấy metric

Observation không tự tạo Timer nếu không có `MeterObservationHandler`. Ở unit test, đăng ký `DefaultMeterObservationHandler`; ở Boot integration test, kiểm tra observability autoconfiguration.

### 18.5. Dùng eventId, orderId làm metric tag

Một ID mới có thể tạo meter/time series mới. Kiểm tra số meter sau nhiều ID khác nhau và assert các high-cardinality fields **không xuất hiện** trong meter IDs.

### 18.6. Test trace chỉ xem MDC traceId

MDC chỉ là dữ liệu trong một context, có thể trống khi sampling hoặc propagation không có. Muốn chứng minh exporter hoạt động, phải đọc spans từ test exporter/collector hoặc backend thật.

### 18.7. Assert chính xác thời gian, trace ID hoặc thứ tự bất đồng bộ

Thời gian và lịch thread phụ thuộc tải môi trường; trace IDs thay đổi theo lần chạy. Dùng assertions về range, cấu trúc, tập nhãn và hậu điều kiện nghiệp vụ; không hardcode span ID hoặc yêu cầu một listener luôn chạy trước response.

### 18.8. Kiểm thử `/actuator/metrics` khi endpoint chưa bật

404/401 chưa chắc do meter sai. Phân biệt chưa expose endpoint, thiếu registry, thiếu auth và không có traffic. Kiểm tra config test và runtime classpath.

### 18.9. Sử dụng backend production cho smoke test

Smoke test staging phải dùng hạ tầng và dữ liệu staging, với secret/network riêng. Không ghi dữ liệu thử hay tắt xác thực TLS ở production để “test nhanh”.

### 18.10. So sánh module graph sinh từ code cũ với runtime mới

Graph phản ánh cấu trúc theo một source commit; telemetry phản ánh artifact đang chạy. Trong CI, gắn tài liệu, binary/image digest và báo cáo test với cùng revision.

## 19. Quy trình kiểm thử trong CI/CD

Một pipeline thực tế:

1. **Compile + unit test:** domain rules, controller slice, Observation/meter tests.
2. **Architecture test:** `ApplicationModules.verify()` và sinh documentation.
3. **Integration test:** Testcontainers PostgreSQL, transaction, published event, async listener, failure/retry.
4. **Telemetry integration:** exporter in-memory/collector test, Actuator endpoint và security.
5. **Build immutable artifact:** gắn source commit và image digest.
6. **Deploy staging:** inject profile và secrets staging.
7. **Smoke test:** HTTP, side effects, registry, metrics, traces trên backend thật.
8. **Release decision:** pass/fail dựa trên bằng chứng đã định nghĩa.

Nên lưu test report với artifact version, test run ID, thời điểm, orderId/eventId và trace URL được phép công bố. Nếu bước cuối fail, lưu diagnostics nhưng không tự khẳng định backend đã thành công chỉ vì các unit test chạy qua.

## 20. Bài tập thực hành và tiêu chí nghiệm thu

**Bài tập A — kiểm thử HTTP.** Tạo `OrdersControllerWebTest` với case valid/invalid JSON, status 202/400 và security theo ứng dụng. Giải thích vì sao mock service không chứng minh event listener hoàn tất.

**Bài tập B — kiểm thử ranh giới module.** Chạy `ApplicationModules.verify()`, sinh module graph. Cố tình cho shipping phụ thuộc một lớp orders.internal rồi xác nhận test kiến trúc phát hiện sai lệch, sau đó sửa bằng API/event được công bố.

**Bài tập C — kiểm thử bất đồng bộ.** Dùng Testcontainers, phát event và chờ shipment xuất hiện. Thêm ca rollback, exception, retry và kiểm chứng idempotency.

**Bài tập D — kiểm thử metrics.** Tạo `OrderTelemetryMetricsTest` với 100 event IDs khác nhau; assert một tập low-cardinality tags ổn định và `event.id` không nằm trong metric ID. Tạo metric lỗi listener với outcome hữu hạn.

**Bài tập E — kiểm thử tracing.** Bật tracing trong test integration, dùng exporter test hoặc Collector staging để chứng minh span xuất hiện. Kiểm tra listener trên thread khác và diễn giải khi traceId thay đổi; dùng eventId để nối các lần xử lý.

**Bài tập F — kiểm thử Actuator và staging.** Gọi health/metrics/module endpoints theo quyền được cấp, xác nhận request tới backend staging thật và truy vấn trace/metrics đã xuất trong hệ thống giám sát.

### Checklist nghiệm thu cuối bài

- [ ] Endpoint test kiểm tra đầy đủ HTTP status, request/response contract và lỗi đầu vào.
- [ ] Module verification và documentation chạy từ đúng source commit.
- [ ] Có test `PublishedEvents` cho event phát từ orders.
- [ ] Có integration test chờ hậu điều kiện shipping đã commit, không dùng sleep cố định.
- [ ] Có kiểm tra rollback, failure và retry/idempotency.
- [ ] Custom metric dùng module/operation/event type hữu hạn, không dùng orderId/eventId/traceId làm metric labels.
- [ ] Test metrics có handler/registry thích hợp và assert tên/tag/count cụ thể.
- [ ] Actuator/metrics endpoints được kiểm tra cùng cấu hình bảo mật.
- [ ] Có test tracing integration hoặc smoke test xác nhận span đến exporter/backend.
- [ ] Có giải thích giới hạn context propagation qua async và cách nối bằng eventId.
- [ ] CI lưu bằng chứng version, test run, eventId và trace/metric phù hợp để điều tra.

**Kết quả mong đợi:** bộ kiểm thử không dừng ở một phản hồi HTTP thành công mà xác minh ranh giới kiến trúc Spring Modulith, publication, listener và hậu điều kiện bền vững; cùng lúc chứng minh telemetry có metric tags ổn định, trace đủ thông tin và được xuất đúng nơi để hỗ trợ vận hành ứng dụng Spring Boot.
