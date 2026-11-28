# Đặt tag low-cardinality theo module

## 1. Bài toán thiết kế

Ứng dụng Spring Boot sử dụng Spring Modulith có thể chia thành các **application module** như `orders`, `inventory`, `payments` và `shipping`. Tài liệu **module graph** cho thấy ranh giới phụ thuộc giữa các module, nhưng khi ứng dụng chạy, nhóm vận hành còn cần biết:

- Module nào phát nhiều sự kiện nhất?
- Module nào có tỷ lệ lỗi hoặc thời gian xử lý cao?
- Listener của module nào đang xử lý chậm sau khi nhận event?
- Một request đi qua những module nào, có mất tracing context khi chạy bất đồng bộ hay không?
- Khi có sự cố, số liệu của một module có thể so sánh ổn định giữa staging và production không?

Muốn trả lời, chúng ta cần gắn các **tag** (còn gọi là *labels* hoặc *key-values*) có tên và giá trị nhất quán lên metric và Observation. Sai lầm thường gặp là đưa `orderId`, `userId`, `eventId` hoặc tên URL đầy đủ vào nhãn metric: mỗi request có thể tạo một chuỗi thời gian mới, khiến Prometheus/Grafana khó vận hành.

Bài **Đặt tag low-cardinality theo module** thuộc chương **Thiết kế thực tế**, trong module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Mục tiêu là kết hợp module graph, Spring Boot Actuator, Micrometer Observation, event metrics, tracing và context propagation thành một quy ước nhãn **có tập giá trị hữu hạn, dễ truy vấn, có thể kiểm thử**.

Sau bài học, người học có thể:

1. Phân biệt tag **low-cardinality** và **high-cardinality**, hiểu vì sao metric backend nhạy cảm với số tổ hợp nhãn.
2. Chọn `module.identifier`, loại event, loại operation và outcome theo danh mục được kiểm soát.
3. Áp dụng Observation và MeterRegistry để đo thao tác nghiệp vụ, event publication và event listener.
4. Tận dụng nhãn sẵn có từ Spring Modulith khi phiên bản đang dùng hỗ trợ, tránh tạo metric trùng.
5. Tách eventId/traceId khỏi metric tags, nhưng vẫn dùng chúng để tìm trace và log.
6. Kiểm tra nhãn qua Actuator/Prometheus, tạo dashboard theo module và viết test bảo vệ cardinality.

> Các ví dụ sử dụng Java 17+, Spring Boot cùng phiên bản Spring Modulith/Micrometer tương thích qua BOM. API Micrometer Observation dùng ở mức ổn định; **tên artifact và tên metric tự động của Spring Modulith thay đổi theo release train**, vì vậy phải đối chiếu với tài liệu và meter thực tế của ứng dụng.

## 2. Cardinality là gì?

Với metric, một **time series** thường được xác định bởi tên metric và **tập giá trị của các labels**. Nếu tên metric giống nhau nhưng một label có giá trị mới, backend thường phải lưu một chuỗi thời gian khác.

Giả sử có metric `app.module.operation` với các nhãn:

| Tag | Số giá trị dự kiến | Ví dụ |
| --- | ---: | --- |
| `module.identifier` | 8 | `orders`, `inventory`, `shipping` |
| `operation` | 5 | `submit`, `reserve`, `dispatch` |
| `outcome` | 3 | `success`, `failure`, `rejected` |
| `environment` | 2 | `staging`, `production` |

Số tổ hợp tối đa theo bảng trên là:

\[
8 \times 5 \times 3 \times 2 = 240
\]

Đó mới là số tổ hợp nhãn cho **một tên metric** trong giả định mọi tổ hợp đều có thể xuất hiện. Thực tế còn bị ảnh hưởng bởi số instance/pod, histogram bucket, percentiles, recording rules và cách backend triển khai. Không nên coi 240 là tổng số series của cả dịch vụ.

Nếu thêm `eventId` có hàng chục nghìn giá trị mỗi ngày, số tổ hợp có thể tăng lên hàng triệu. Ngay cả khi hệ thống ít tải, các time series sống ngắn nhưng liên tục được tạo cũng tăng chi phí lưu trữ, CPU và bộ nhớ của hệ thống giám sát.

### Low-cardinality và high-cardinality

| Dữ liệu | Phân loại điển hình | Cách sử dụng |
| --- | --- | --- |
| `module.identifier=orders` | Low, khi module thuộc tập hữu hạn | Metric tag; span attribute |
| `event.type=OrderPlaced` | Low, nếu kiểu event thuộc danh mục được quản lý | Metric tag; span attribute |
| `operation=submit` | Low, nếu là mã operation cố định | Metric tag; span attribute |
| `outcome=success` | Low | Metric tag; span attribute |
| `environment=staging` | Low | Resource tag/metric tag theo policy |
| `orderId=...` | High | Log hoặc span attribute khi cần và được phép |
| `eventId=...` | High | Correlation trong log/trace, **không làm metric label** |
| `traceId=...` | High | Truy tìm trace, không làm metric label |
| `http.url=/orders/12345` | High | Dùng route template `/orders/{id}` khi cần metric |
| Exception message / SQL / email | High và có thể nhạy cảm | Tránh gắn lên metric; hạn chế trong log/trace |

**Low-cardinality không được xác định chỉ bằng tên tag.** Một tag đặt tên `module` có thể trở thành high-cardinality nếu giá trị được lấy trực tiếp từ HTTP parameter do người dùng gửi, hoặc ghép với timestamp.

## 3. Chọn danh mục nhãn theo ranh giới module

Spring Modulith phát hiện **application module** dựa trên mô hình package/configuration. Trong ứng dụng đơn giản:

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── OrderPlaced.java
│   └── internal/
├── inventory/
│   └── internal/
└── shipping/
    └── internal/
~~~

Ba định danh module giả định là `orders`, `inventory`, `shipping`. Nếu ứng dụng tùy chỉnh module detection, named interfaces hoặc package model, hãy lấy **danh mục module thực tế** từ `ApplicationModules` và tài liệu đã sinh; tránh tự suy diễn từ class name.

### 3.1. Quy ước nhãn khuyến nghị

| Key | Ý nghĩa | Giá trị hợp lệ ví dụ | Quy tắc |
| --- | --- | --- | --- |
| `module.identifier` | Module mà phép đo thuộc về | `orders`, `inventory`, `shipping` | ID ổn định, tập giá trị hữu hạn |
| `module.name` | Tên hiển thị module khi instrumentation có cung cấp | `Orders`, `Shipping` | Tránh coi là khóa định danh bền vững |
| `operation` | Loại thao tác | `submit_order`, `reserve_stock` | Enum hoặc danh mục cố định |
| `module.event.type` | Loại sự kiện | `OrderPlaced`, `StockReserved` | Tên kiểu sự kiện có kiểm soát |
| `outcome` | Kết quả tổng quát | `success`, `failure`, `rejected` | Không chứa error message |
| `module.invocation-type` | Kiểu lời gọi mà Spring Modulith quan sát | `bean`, `event listener` | Kiểm tra danh mục theo version |
| `environment` | Môi trường chạy | `staging`, `production` | Nguồn cấu hình triển khai |

Có thể sử dụng key do Spring Modulith cung cấp (`module.identifier`, `module.name`, `module.event.type`) để đồng bộ với metric tự động. Với phép đo **tự tạo**, cũng có thể dùng key tên `application.module` hoặc `module`; hãy **chọn một quy ước** và tài liệu hóa. Tránh gắn đồng thời `module`, `module_name`, `module.identifier` vào cùng metric chỉ để diễn đạt cùng một thông tin.

### 3.2. Module identifier có cần version không?

Thông thường **không** nên dùng `module.identifier=orders-v20261127-build217` vì một lần deploy tạo giá trị mới. ID module phản ánh **ranh giới kiến trúc**, còn build version/commit nên được ghi ở resource metadata hoặc release dashboard nếu chính sách cardinality cho phép.

Khi đổi tên module từ `shipping` thành `fulfillment`, đây là thay đổi danh mục nhãn. Dashboard và alert phải được cập nhật có kiểm soát, có thể theo dõi hai tên trong giai đoạn chuyển tiếp. Đổi tên label giữa chừng làm số liệu lịch sử bị chia thành hai chuỗi.

## 4. Kiểm chứng module identifier bằng Spring Modulith

Kiểm tra kiến trúc trước khi đưa số đo vào production:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleArchitectureTests {

    @Test
    void verifyBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }

    @Test
    void writeModuleGraph() {
        var modules = ApplicationModules.of(ShopApplication.class);
        new Documenter(modules).writeDocumentation();
    }
}
~~~

`ShopApplication` là class Spring Boot entrypoint của ứng dụng giả định; cần thay bằng class thật. `Documenter` yêu cầu artifact documentation ở test classpath.

**Module graph** trả lời “orders được phép gọi module nào, thông qua interface nào?”. **Metric gắn module.identifier** trả lời “module nào có bao nhiêu request, event hoặc lỗi?”. **Trace** trả lời “trong lần thực thi này, những module nào tham gia, thứ tự và thời lượng ra sao?”.

Chúng bổ sung cho nhau: nếu một module được đổi tên trong module graph mà bộ đo vẫn dùng label cũ, pipeline giám sát đã có **configuration drift**.

## 5. Dùng nhãn có sẵn của Spring Modulith trước

Trong các release train Spring Modulith hỗ trợ observability, integration có thể tự tạo Observation cho lời gọi vào API module và metric cho application events.

Tài liệu Spring Modulith Production-ready Features mô tả các nhãn quan sát module, gồm:

- **Span tương tác module:** `module.identifier`, `module.name`, `module.invocation-type`, `module.method`.
- **Metric tổng hợp publication** `module.events.published`: low-cardinality keys `module.event.type`, `module.identifier`, `module.name`.
- **Metric theo loại event và module** có dạng `module.events.published.<moduleIdentifier>.<simpleEventTypeName>`: các nhãn module tùy phiên bản/cấu hình.

Điều này giúp truy vấn module mà **không phải tự instrument mọi lời gọi**. Tuy nhiên, tên span/metric và tag keys có thể khác giữa các phiên bản: kiểm tra trực tiếp `/actuator/metrics` và backend trước khi viết truy vấn dashboard.

### 5.1. Phụ thuộc cần thiết

Ví dụ cấu hình Gradle theo release train Spring Modulith có `spring-modulith-starter-insight`:

~~~groovy
dependencies {
    implementation("org.springframework.modulith:spring-modulith-starter-core")
    runtimeOnly("org.springframework.modulith:spring-modulith-starter-insight")

    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")

    // Chỉ khi cần xuất trace qua OpenTelemetry/OTLP:
    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")

    // Sinh tài liệu ranh giới application module:
    testImplementation("org.springframework.modulith:spring-modulith-docs")
    testImplementation("org.springframework.modulith:spring-modulith-starter-test")
}
~~~

**BOM của Spring Boot và Spring Modulith phải tương thích**, quản lý version ở cấp build thay vì gắn các version lẻ vào ví dụ trên. Ở nhánh Modulith 1.x, tên artifact observability có thể khác 2.x. Nếu chỉ dùng Spring Boot Actuator cùng custom Observations mà không muốn starter Insight, có thể bỏ Insight và khai báo đúng hỗ trợ Modulith cần thiết theo version.

Ví dụ `application.yml` cho môi trường kiểm thử:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  tracing:
    sampling:
      probability: 1.0

spring:
  application:
    name: shop-modulith
~~~

Giá trị sampling 100% chỉ phục vụ lab nhỏ; môi trường tải lớn cần policy phù hợp. Mở metrics/Prometheus endpoint phải áp dụng private network và/hoặc authentication; không để endpoint giám sát nội bộ công khai tùy ý.

### 5.2. Có nên tự gắn thêm `module.identifier` lên metric sẵn có?

Nếu metric Spring Modulith đã có `module.identifier`, hãy **dùng trực tiếp**. Thêm custom metric khác chỉ vì muốn đếm lại cùng một publication có thể dẫn đến số liệu trùng và dashboard hiểu nhầm.

Chỉ thêm nhãn khi có câu hỏi mới, ví dụ số listener failures theo module hoặc số lần nghiệp vụ bị từ chối, và nhãn đó có danh mục hữu hạn. Khi dùng customizer cho event metrics theo phiên bản Spring Modulith hỗ trợ, không truyền raw event fields có nhiều giá trị vào `tags(...)`: framework vẫn có thể coi chúng là metric labels và gây cardinality bùng nổ.

## 6. Chuẩn hóa danh mục module bằng enum

Để tránh tên module do dữ liệu request quyết định, ứng dụng có thể định nghĩa một danh mục module **cố định**:

~~~java
package com.example.shop.observability;

public enum ModuleTag {
    ORDERS("orders"),
    INVENTORY("inventory"),
    SHIPPING("shipping");

    private final String identifier;

    ModuleTag(String identifier) {
        this.identifier = identifier;
    }

    public String identifier() {
        return identifier;
    }
}
~~~

Danh mục operation cũng nên cố định:

~~~java
package com.example.shop.observability;

public enum OperationTag {
    SUBMIT_ORDER("submit_order"),
    RESERVE_STOCK("reserve_stock"),
    CREATE_SHIPMENT("create_shipment");

    private final String value;

    OperationTag(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }
}
~~~

Cả enum chỉ là **quy ước nhãn nội bộ**, không thay thế cách Spring Modulith tự phát hiện module. Cần đối chiếu `ModuleTag` với danh sách `ApplicationModules` thực tế trong bài kiểm tra kiến trúc; nếu xuất hiện một module mới, phải cập nhật danh mục trước khi phát hành.

Lưu ý: enum tạo bộ giá trị hữu hạn, nhưng không ngăn người lập trình gọi `ModuleTag.ORDERS` trong mã thực chất thuộc shipping. Trách nhiệm gắn nhãn đúng vẫn cần được review và kiểm thử nghiệp vụ.

## 7. Đo operation bằng Micrometer Observation

`ObservationRegistry` được Spring Boot tạo và cấu hình khi có hạ tầng Actuator/observability thích hợp. Các Observation có thể sinh **metric** và **trace** thông qua handler đã cài.

Tạo component đo một thao tác:

~~~java
package com.example.shop.observability;

import java.util.function.Supplier;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Component;

@Component
public class ModuleOperationObserver {

    private final ObservationRegistry registry;

    public ModuleOperationObserver(ObservationRegistry registry) {
        this.registry = registry;
    }

    public <T> T observe(
            ModuleTag module,
            OperationTag operation,
            Supplier<T> action) {

        return Observation.createNotStarted(
                "app.module.operation", registry)
            .contextualName(module.identifier() + " " + operation.value())
            .lowCardinalityKeyValue(
                "module.identifier", module.identifier())
            .lowCardinalityKeyValue(
                "operation", operation.value())
            .observe(action);
    }
}
~~~

Áp dụng trong service:

~~~java
@Service
public class OrderApplicationService {

    private final ModuleOperationObserver observer;
    private final OrderRepository repository;

    public OrderApplicationService(
            ModuleOperationObserver observer,
            OrderRepository repository) {
        this.observer = observer;
        this.repository = repository;
    }

    public OrderReceipt submit(OrderDraft draft) {
        return observer.observe(
            ModuleTag.ORDERS,
            OperationTag.SUBMIT_ORDER,
            () -> repository.saveOrder(draft));
    }
}
~~~

Trong ví dụ trên, `OrderRepository`, `OrderDraft` và `OrderReceipt` là các kiểu của domain cần được ứng dụng định nghĩa. Class service cũng cần import `org.springframework.stereotype.Service` và các kiểu domain/module đã tạo.

**Kết quả quan sát:** metric có tên `app.module.operation` có thể được gắn `module.identifier=orders`, `operation=submit_order`; nếu đã bật tracing, span tương ứng cũng có thể mang các thuộc tính này. Hàm `observe(...)` quản lý vòng đời start/scope/stop và ghi nhận lỗi nếu `action` ném exception theo hành vi Micrometer Observation.

**Giới hạn:** phép đo chỉ bao quanh đoạn `repository.saveOrder` được truyền vào action. Nếu transaction được commit sau lúc `submit` trả về bởi interceptor `@Transactional`, Observation bên trong method có thể kết thúc **trước khi commit hoàn toàn**. Không đặt tên metric này là `order_commit_duration` khi chưa đo đúng ranh giới transaction.

### Vì sao chọn Observation thay vì tạo Timer ở mọi service?

Observation giúp tái sử dụng cùng bộ metadata cho metrics và tracing. Khi yêu cầu thêm thông tin chỉ dành cho trace, ta dùng **high-cardinality values** riêng mà không tăng số metric series. Còn MeterRegistry/Counter vẫn phù hợp cho các bộ đếm đơn giản, ví dụ số lần listener thử xử lý.

Nếu Spring Modulith đã tự tạo module entry span, custom Observation này có thể xuất hiện **lồng bên trong span tự động**. Cần xem trace trước khi tạo quá nhiều span trùng ý nghĩa.

## 8. Gắn tag cho event publication và listener

Xét sự kiện thuộc public API của module orders:

~~~java
package com.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID eventId, UUID orderId) {
}
~~~

Listener ở shipping xử lý sự kiện và có thể được Spring Modulith chạy bất đồng bộ sau commit:

~~~java
package com.example.shop.shipping;

import com.example.shop.orders.OrderPlaced;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
public class OrderPlacedListener {

    private final ShipmentService shipmentService;
    private final ObservationRegistry observations;

    public OrderPlacedListener(
            ShipmentService shipmentService,
            ObservationRegistry observations) {
        this.shipmentService = shipmentService;
        this.observations = observations;
    }

    @ApplicationModuleListener
    public void on(OrderPlaced event) {
        Observation.createNotStarted(
                "app.event.listener", observations)
            .lowCardinalityKeyValue(
                "module.identifier", "shipping")
            .lowCardinalityKeyValue(
                "module.event.type", "OrderPlaced")
            .highCardinalityKeyValue(
                "event.id", event.eventId().toString())
            .observe(() ->
                shipmentService.createShipment(
                    event.orderId(), event.eventId()));
    }
}
~~~

`ShipmentService` là một service nghiệp vụ giả định. Với phiên bản Spring Modulith tương ứng, `@ApplicationModuleListener` là annotation hỗ trợ xử lý sau commit, bất đồng bộ và transaction riêng; hãy xác minh semantics thực tế theo release train đã chọn.

**Ba điều cần lưu ý:**

1. `module.identifier` và `module.event.type` có tập giá trị cố định nên phù hợp với **metric labels**.
2. `event.id` thay đổi theo từng sự kiện và được khai báo **high-cardinality**. Với Micrometer Observation mặc định, high-cardinality key-values phục vụ tracing, **không được đưa vào meter tags**. Chỉ lưu eventId trong span/log khi chính sách dữ liệu cho phép.
3. Span của listener đo **đoạn code bên trong callback**, không bảo đảm registry đã đánh dấu event publication completed hay transaction chứa callback đã hoàn tất commit.

Nếu listener thất bại, không bắt exception rồi bỏ qua: cơ chế quản lý completion có thể coi lần xử lý là thành công. Để exception lan ra theo contract của listener; đồng thời thiết kế idempotency vì retry có thể gọi xử lý lại.

### 8.1. Phân biệt `published`, `consumed` và `completed`

| Mốc | Ai ghi nhận? | Metric nào hợp lý? |
| --- | --- | --- |
| Publisher gọi `publishEvent` | Module orders / event infrastructure | Publication counter |
| Transaction phát sự kiện commit | Transaction manager | Commit success/failure theo nhu cầu; không đồng nhất với publication |
| Listener bắt đầu | Module shipping | Listener attempts |
| Listener ném exception | Module shipping | Failure attempts |
| Listener xử lý xong | Module shipping | Processing duration, success attempts |
| Registry đánh dấu completed | Event publication registry | Outstanding/completed publications theo semantics implementation |

Không thể suy ra “mọi event đã hoàn tất” chỉ vì metric publication tăng. Đối với hàng đợi thất bại, cần đọc registry, hậu điều kiện lưu trữ hoặc nghiệp vụ đã commit. Không tạo `outcome=success` cho publication khi listener chưa chạy.

## 9. Dùng Counter có tag outcome cố định

Nếu muốn đếm riêng lượt listener thành công và thất bại, có thể thêm MeterRegistry:

~~~java
package com.example.shop.observability;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class ListenerAttemptMetrics {

    private final Counter shippingSucceeded;
    private final Counter shippingFailed;

    public ListenerAttemptMetrics(MeterRegistry registry) {
        shippingSucceeded =
            Counter.builder("app.event.listener.attempts")
                .tag("module.identifier", "shipping")
                .tag("module.event.type", "OrderPlaced")
                .tag("outcome", "success")
                .register(registry);

        shippingFailed =
            Counter.builder("app.event.listener.attempts")
                .tag("module.identifier", "shipping")
                .tag("module.event.type", "OrderPlaced")
                .tag("outcome", "failure")
                .register(registry);
    }

    public void success() {
        shippingSucceeded.increment();
    }

    public void failure() {
        shippingFailed.increment();
    }
}
~~~

Một lần listener chạy thành công thì gọi `success()`; trong nhánh xử lý ném exception, gọi `failure()` rồi **rethrow**. Nếu muốn đo số lượt bắt đầu thay vì số lượt kết thúc, cần bộ đếm hoặc `outcome=started` riêng và định nghĩa rõ cách đếm.

Tại sao constructor tạo sẵn Counter? Mỗi Counter có **tập tags ổn định** và không phát sinh đăng ký meter mới theo eventId. Nếu mỗi request tạo `Counter.builder(...).tag("eventId", event.eventId())`, số series sẽ tăng theo traffic.

Nếu Observation cho `app.event.listener` đã được cấu hình để tạo timer/error metric, không nhất thiết phải đếm thêm `attempts` nếu dashboard có thể truy vấn count của timer. Chỉ tạo Counter khi nó phục vụ cách diễn giải rõ ràng (ví dụ phân biệt rejected/failed hoặc listener attempts), và tránh đếm hai nguồn lẫn lộn.

## 10. Cần Outcome hay Error ở metric?

Micrometer `DefaultMeterObservationHandler` thường thêm nhãn `error` cho timer dựa trên exception được ghi nhận; giá trị `none` biểu thị không có lỗi.

Trong thiết kế nghiệp vụ, có thể còn những trường hợp **không ném exception** nhưng thao tác bị từ chối theo quy tắc: ví dụ từ chối vì không đủ tồn kho. Khi đó `error=none` và `outcome=rejected` đều có thể đúng theo hai góc nhìn khác nhau.

Quy ước gợi ý:

| Trạng thái | `outcome` | `error` / exception | Ý nghĩa |
| --- | --- | --- | --- |
| Hoàn tất bình thường | `success` | `none` | Thành công nghiệp vụ |
| Bị từ chối theo quy tắc, không exception | `rejected` | `none` | Dữ liệu hợp lệ nhưng không chấp nhận |
| Exception trong xử lý | `failure` | Theo loại exception | Lỗi thực thi |

Không dùng `outcome` để chứa nguyên văn exception message. Nếu cần phân loại lỗi chi tiết, chỉ dùng một **mã lỗi hữu hạn** như `reason=insufficient_stock`; cân nhắc số tổ hợp mới tạo ra.

Một số handler/metric có cách xử lý tag khác nhau theo vòng đời Observation: Timer được tổng hợp lúc `stop` thường nhìn thấy low-cardinality values cuối cùng, trong khi **long-task timer khởi tạo lúc `start` chỉ nhận tags đã có tại thời điểm start**. Vì vậy hãy đặt tag cố định theo module/operation ngay khi tạo Observation; không trông chờ tags thêm sau start xuất hiện ở mọi loại meter.

## 11. Truyền context qua listener bất đồng bộ

Với `@ApplicationModuleListener`, request thread và listener thread có thể khác nhau. Active tracing context nằm trong thread-local hoặc context tương đương; nếu không được truyền, listener có thể xuất hiện trong một trace khác với publisher.

Trên Spring Framework hỗ trợ `ContextPropagatingTaskDecorator` (thường từ 6.1 trở lên), có thể cấu hình executor:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class ModuleEventExecutorConfiguration {

    @Bean(name = "taskExecutor")
    ThreadPoolTaskExecutor taskExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("module-event-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

Phải kiểm tra **đúng executor** mà Spring dùng để dispatch listener; ứng dụng có AsyncConfigurer hoặc nhiều executor có thể cần cấu hình khác. Task decorator chụp context **ở lúc submit task**: nó không hồi sinh một span đã kết thúc trước lúc submit sau commit.

Vì vậy:
- **Metric theo module** có thể vẫn đúng ngay cả khi listener khởi tạo trace mới.
- **eventId** phải được mang trong event/log để đối chiếu các trace sau restart/retry.
- **SecurityContext và transaction** không được mặc định truyền qua worker thread; listener phải tuân thủ chính sách bảo mật và transaction riêng.
- **Không biến traceId thành low-cardinality tag** để cố nối span: cách đó làm hỏng metric backend.

## 12. Khóa giới hạn tập nhãn ngay từ thiết kế

Một vài biện pháp phòng tránh:

### 12.1. Đặt allowlist trước khi gắn nhãn

Mọi `module.identifier` trong custom metrics nên lấy từ enum/danh mục đã duyệt hoặc identifier phát hiện từ Spring Modulith. Nếu dữ liệu bắt buộc phải được ánh xạ từ một chuỗi bên ngoài, chỉ trả ra một mã đã biết hoặc `other`:

~~~java
public final class ModuleLabelNormalizer {
    private ModuleLabelNormalizer() {}

    public static String normalize(String externalValue) {
        return switch (externalValue) {
            case "orders" -> "orders";
            case "inventory" -> "inventory";
            case "shipping" -> "shipping";
            default -> "other";
        };
    }
}
~~~

Mục đích của `other` là chặn giá trị lạ tạo series mới. Không nên lạm dụng `other` làm nơi chứa mọi module thật; nếu nhận giá trị lạ trong nội bộ, phải log/alert và bổ sung module theo quy trình. Nếu đầu vào có thể là null, xử lý rõ ràng trước khi dùng `switch` để tránh NullPointerException.

### 12.2. Dùng MeterFilter làm lớp phòng vệ

Micrometer hỗ trợ `MeterFilter.maximumAllowableTags` để giới hạn số giá trị tag được tạo cho một metric:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MetricsCardinalityGuard {

    @Bean
    MeterFilter moduleTagLimit() {
        return MeterFilter.maximumAllowableTags(
            "app.module.operation",
            "module.identifier",
            16,
            MeterFilter.deny());
    }
}
~~~

Giới hạn trên bảo vệ metric có tên bắt đầu bằng `app.module.operation`, cho phép tối đa 16 giá trị của tag được chọn trước khi từ chối các meter mới. Đây là **hàng rào cuối**, không thay thế thiết kế allowlist. Khi meter bị từ chối, số liệu có thể thiếu; cần phát hiện sự kiện này trong diagnostics/test và không âm thầm coi là không có traffic.

Ngoài số giá trị **một tag**, tổng số series còn là tích các chiều labels và các meter khác. Giới hạn mỗi `module.identifier` không giải quyết được nếu `operation` hoặc `error.reason` vẫn có hàng nghìn giá trị.

### 12.3. Đưa metadata triển khai vào đúng chỗ

`service.name`, `environment`, `cluster` và `version` thường được quản lý như **resource metadata** hoặc common tags nếu cần truy vấn. Các giá trị có danh mục theo thời gian, nhưng `pod.uid`, `container.id` hoặc `build.sha` có thể tăng nhanh theo mỗi lần rollout. Chỉ dùng làm metric labels khi đã đánh giá số series và retention.

Đối với dashboards so sánh module theo môi trường, `environment` hữu hạn (`dev`, `staging`, `prod`) là hữu ích. Với metrics cấp instance, hãy hiểu rằng Prometheus có thể thêm `job` và `instance` từ scrape metadata dù code ứng dụng không gắn nhãn đó.

## 13. Kiểm tra tags bằng Actuator và Prometheus

Trước khi thiết kế dashboard, dùng endpoint thật của ứng dụng:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/app.module.operation
curl -s http://localhost:8080/actuator/prometheus
~~~

Các endpoint chỉ hoạt động nếu ứng dụng có Actuator, registry tương ứng, đã expose endpoint và có traffic. Metric custom có thể chỉ xuất hiện sau lần instrument đầu tiên.

Ví dụ payload từ `/actuator/metrics/app.module.operation` sẽ có dạng khái niệm:

~~~json
{
  "name": "app.module.operation",
  "measurements": [
    {"statistic": "COUNT", "value": 17.0},
    {"statistic": "TOTAL_TIME", "value": 0.42}
  ],
  "availableTags": [
    {"tag": "module.identifier", "values": ["orders", "inventory"]},
    {"tag": "operation", "values": ["submit_order", "reserve_stock"]}
  ]
}
~~~

Ví dụ chỉ minh họa định dạng: giá trị và thậm chí danh sách measurement còn phụ thuộc meter/handler đang chạy. Những trường `availableTags` là **tập giá trị ghi nhận**, không khẳng định mọi tổ hợp tags đều đã có traffic.

### 13.1. Gợi ý PromQL

Khi Micrometer export timer `app.module.operation` sang Prometheus, tên metric **thường** được chuẩn hóa thành `app_module_operation_seconds_count` và label `module.identifier` thành `module_identifier`. Trước khi sử dụng truy vấn, hãy xác nhận chính xác tên metric trên endpoint Prometheus.

Số thao tác mỗi giây theo module:

~~~promql
sum by (module_identifier) (
  rate(app_module_operation_seconds_count[5m])
)
~~~

Độ trễ trung bình theo module, cùng cửa sổ:

~~~promql
sum by (module_identifier) (
  rate(app_module_operation_seconds_sum[5m])
)
/
sum by (module_identifier) (
  rate(app_module_operation_seconds_count[5m])
)
~~~

Đếm lượt listener thất bại theo module, dựa trên Counter được thêm ở phần trước:

~~~promql
sum by (module_identifier) (
  rate(app_event_listener_attempts_total{outcome="failure"}[5m])
)
~~~

Nếu biểu đồ phải bao phủ nhiều ứng dụng, nhớ giới hạn bằng `job`, `service_name`, `application` hoặc nhãn resource tương ứng để tránh gộp dữ liệu không liên quan. Với histogram/quantiles, số buckets làm cardinality tăng; không bật histogram cho mọi metric nếu không có mục tiêu SLO cụ thể.

### 13.2. Những gì dashboard theo module nên hiển thị

| Panel | Nhóm theo | Câu hỏi |
| --- | --- | --- |
| Operation throughput | `module.identifier`, `operation` | Module nào chịu tải? |
| Duration / latency | `module.identifier` | Module nào chậm? |
| Listener failure rate | `module.identifier`, `module.event.type` | Event nào gặp lỗi nhiều? |
| Published events | `module.identifier`, `module.event.type` | Module nào phát sự kiện? |
| Outstanding publications | Module/listener theo registry | Module nào có công việc chưa hoàn tất? |
| Module dependency graph | Cấu trúc application module | Module nào phụ thuộc module nào? |

**Không hiển thị một Order ID như một series.** Để điều tra đơn cụ thể, người vận hành chuyển từ dashboard tổng quan sang log/trace dùng eventId, orderId hoặc traceId đã được lưu có kiểm soát.

## 14. Kiểm thử cardinality và nhất quán nhãn

Một quy ước observability tốt cần test tự động. Ngoài test `ApplicationModules.verify()`, hãy xác nhận custom metrics không nhận high-cardinality tag.

Ví dụ integration test dùng `MeterRegistry` thật của Spring Boot:

~~~java
import java.util.Set;
import java.util.stream.Collectors;

import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ModuleTagMetricsTests {

    @Autowired ModuleOperationObserver observer;
    @Autowired MeterRegistry meterRegistry;

    @Test
    void operationMetricsUseOnlyKnownModuleLabels() {
        observer.observe(
            ModuleTag.ORDERS,
            OperationTag.SUBMIT_ORDER,
            () -> "ok");

        observer.observe(
            ModuleTag.INVENTORY,
            OperationTag.RESERVE_STOCK,
            () -> "ok");

        var meters = meterRegistry.getMeters().stream()
            .filter(m -> m.getId().getName()
                .equals("app.module.operation"))
            .toList();

        assertThat(meters).isNotEmpty();

        Set<String> modules = meters.stream()
            .map(m -> m.getId().getTag("module.identifier"))
            .collect(Collectors.toSet());

        assertThat(modules)
            .containsOnly("orders", "inventory");

        assertThat(meters)
            .allSatisfy(m ->
                assertThat(m.getId().getTag("event.id")).isNull());
    }
}
~~~

**Điều kiện test:** môi trường test phải có Observation handler tạo metrics qua MeterRegistry; Spring Boot với Actuator thường cấu hình sẵn. Nếu test bootstrap thuần Java chỉ tạo `ObservationRegistry.create()` mà **không đăng ký handler**, sẽ không có meter để assert.

Test trên chứng minh hai nhãn được cho phép ở phạm vi phép đo, và `event.id` không bị dùng làm meter tag. Trong ứng dụng lớn, nên isolate MeterRegistry để tránh các meter do test khác tạo từ trước; cách đơn giản là test riêng component với `SimpleMeterRegistry` và `DefaultMeterObservationHandler` đã đăng ký.

### 14.1. Test giới hạn cardinality không chỉ assert đúng giá trị

Một bộ test tốt còn nên:

1. Gọi nhiều request có orderId khác nhau rồi xác nhận **số tổ hợp metric tags không tăng theo số order**.
2. Kiểm tra `module.identifier` luôn thuộc allowlist.
3. Kiểm tra tên operation là một enum/danh mục cố định, không tạo từ raw URL.
4. Giả lập listener lỗi, xác nhận nhãn outcome/error hữu hạn và failure metrics tăng.
5. So sánh module labels với danh sách module được Spring Modulith phát hiện trong `ApplicationModules`.
6. Kiểm tra dashboard/query sau khi đổi tên module theo một release đã kiểm soát.

## 15. Khi nào cần tag high-cardinality?

Không phải dữ liệu có nhiều giá trị đều vô dụng. `eventId`, `orderId`, `traceId` rất quan trọng khi điều tra một request cụ thể; vấn đề nằm ở **đích lưu trữ** và **khả năng truy vấn**.

Micrometer Observation phân biệt:

~~~java
Observation.createNotStarted("app.event.listener", registry)
    .lowCardinalityKeyValue("module.identifier", "shipping")
    .lowCardinalityKeyValue("module.event.type", "OrderPlaced")
    .highCardinalityKeyValue("event.id", eventId.toString())
    .observe(this::handleEvent);
~~~

Với handler thông thường, low-cardinality values vào metrics và traces; high-cardinality values có thể vào **traces** nhưng không vào metric tags. Trên production, cần kiểm tra chính sách bảo mật, sampling, bộ exporter và giới hạn số lượng thuộc tính; không nên đưa thông tin cá nhân/secret vào spans.

Các log cũng nên có cấu trúc:

~~~text
traceId=8f12... module=orders eventType=OrderPlaced eventId=E-173 stage=published
traceId=2a51... module=shipping eventType=OrderPlaced eventId=E-173 stage=listener-start
traceId=2a51... module=shipping eventType=OrderPlaced eventId=E-173 stage=listener-completed
~~~

Đây là ví dụ minh họa: hai traceId khác nhau **không có nghĩa event bị thất lạc**. Khi listener chạy sau commit, trên thread khác hoặc được retry sau restart, trace context có thể tách. eventId giữ vai trò nối các lần xử lý.

## 16. Sai lầm thường gặp

### 16.1. Đưa ID nghiệp vụ vào low-cardinality tag

**Sai:**

~~~java
Counter.builder("orders.created")
    .tag("module.identifier", "orders")
    .tag("order.id", orderId.toString())
    .register(registry)
    .increment();
~~~

Mỗi `order.id` khác nhau có thể tạo một meter/time series mới.

**Đúng:** dùng `module.identifier=orders`, `operation=submit_order`, lưu orderId trong structured log/span attribute khi phù hợp. Nếu cần thống kê các nhóm order, sử dụng một số ít category đã được định nghĩa, không dùng ID riêng từng order.

### 16.2. Dùng class/method đầy đủ làm label bừa bãi

`com.example.shop.orders.internal.OrderRepositoryImpl.saveOrder` có thể thay đổi theo refactor và phát sinh nhiều tổ hợp. Nếu cần quan sát method trong **trace**, tận dụng nhãn span/module.method do instrumentation cung cấp. Không tự đưa mọi stack frame hoặc dynamic proxy class name vào metric tags.

### 16.3. Gắn tag qua request header không kiểm soát

Một `X-Module` hoặc `X-Tenant` do client gửi không phải nguồn xác định module thực tế. Dữ liệu này có thể vô hạn và bị thao túng. Module label phải được quyết định bởi **code/module boundary**, không bởi client request.

### 16.4. Tag theo timestamp hay deployment ID

Một tag như `build.sha` đổi theo từng deploy; trong một số hệ thống có thể dùng resource metadata, nhưng không nên đưa vô điều kiện lên tất cả business metrics. Các nhãn lịch sử và số series tăng sau nhiều lần rollout có thể vượt khả năng backend.

### 16.5. Đếm publication thay cho completion

`module.events.published` chỉ giúp quan sát **publication**. Với `@ApplicationModuleListener` bất đồng bộ, hoàn tất thực sự cần được xác minh qua hậu điều kiện, event publication registry và log/trace listener.

### 16.6. Thêm metric custom trùng với metric tự động

Nếu Spring Modulith đã có publication metric theo module/event type, hãy tái sử dụng nó. Khi muốn đo listener failure hoặc processing duration, cần đặt **định nghĩa khác** và ghi rõ cách tính (attempt vs unique event vs completed).

### 16.7. Chỉ giới hạn một tag

Giới hạn 16 giá trị module mà cho phép hàng nghìn `operation` hoặc `error.reason` vẫn gây cardinality explosion. Ngân sách series phải được đánh giá trên **toàn bộ các chiều nhãn**.

## 17. Kịch bản thực hành tổng hợp

Một ứng dụng được chia thành `orders`, `inventory` và `shipping`. Khi khách đặt hàng:

1. orders ghi đơn, phát `OrderPlaced`.
2. inventory nhận event hoặc được gọi qua API được công bố để giữ hàng.
3. shipping xử lý sau khi điều kiện nghiệp vụ được đáp ứng.
4. Actuator/metrics và trace backend ghi nhận hoạt động; eventId nối các lần xử lý.

### Bài tập A — thiết kế nhãn

Thiết kế bảng danh mục `module.identifier`, `operation`, `module.event.type`, `outcome`. Ước lượng số series bằng tích số giá trị và giải thích ảnh hưởng của histogram buckets hoặc số instances. Chọn giá trị từ danh mục code/module graph.

### Bài tập B — instrument operation

Dùng `ModuleOperationObserver` đo một thao tác trong mỗi module. Gửi requests với 100 orderId khác nhau, sau đó kiểm tra `/actuator/metrics/app.module.operation`. Chứng minh rằng module tags không tạo series mới theo từng orderId.

### Bài tập C — đo event listener

Tạo một listener dùng `@ApplicationModuleListener`. Ghi `module.identifier=shipping`, `module.event.type=OrderPlaced`, lỗi thành công/thất bại bằng metric hữu hạn. Đưa eventId vào structured log/high-cardinality span attribute được kiểm soát. Gây lỗi một lần, retry và kiểm tra event completion với registry hoặc hậu điều kiện nghiệp vụ.

### Bài tập D — module graph và dashboard

Sinh module graph, chạy `ApplicationModules.verify()`, tạo dashboard throughput và failure rate nhóm theo module. So sánh các module xuất hiện trên dashboard với danh mục graph. Thử đổi tên một module trong nhánh kiểm thử và đề xuất bước migration cho nhãn lịch sử.

### Bài tập E — context propagation

Cho listener chạy async; quan sát traceId của publisher và listener trước/sau khi cấu hình propagation trên đúng executor. Giải thích vì sao module metric vẫn nhóm được theo module kể cả khi hai span thuộc hai trace khác nhau.

### Tiêu chí hoàn thành

- [ ] Có danh mục module identifier và operation hữu hạn, nhất quán với graph.
- [ ] Các metric theo module dùng low-cardinality keys đã được phê duyệt.
- [ ] eventId/orderId/traceId không xuất hiện trong metric labels.
- [ ] Quan sát event publication và listener có định nghĩa đo rõ ràng, không đếm trùng.
- [ ] Có bằng chứng trong Actuator/Prometheus về tập nhãn và số series ổn định qua nhiều request.
- [ ] Dashboard truy vấn được throughput, duration và failure theo module.
- [ ] Khi async trace bị tách, log/span vẫn có correlation ID thích hợp để điều tra.
- [ ] Đã kiểm tra error/retry và hậu điều kiện hoàn tất sự kiện.
- [ ] Tên nhãn và thay đổi version/module được mô tả trong tài liệu vận hành.

## 18. Tài liệu tham khảo

- [Spring Modulith – Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): Modulith Actuator, module interaction spans và event publication metrics.
- [Micrometer Observation – Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): low/high-cardinality key-values và Observation API.
- [Micrometer Observation – Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): cách ObservationHandler tạo metrics và những tags được sử dụng.
- [Micrometer – High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html): phát hiện/giới hạn sự bùng nổ cardinality.
- [Micrometer Tracing – Configuring with Observation](https://docs.micrometer.io/tracing/reference/configuring.html): mối quan hệ giữa Observation và trace/span.

**Kết quả mong đợi:** Người học xác định được mỗi metric đang đại diện cho **module nào và loại công việc nào**, giữ số nhãn ở mức hữu hạn khi hệ thống tăng tải, đồng thời dùng trace/log để điều tra từng event cụ thể. Cách thiết kế này biến module graph của Spring Modulith thành một hệ quy chiếu ổn định cho Actuator, event metrics, tracing và vận hành ứng dụng Spring Boot.
