# GlobalObservationConvention: cấu hình convention dùng chung trong ObservationRegistry

Khi phát triển ứng dụng Spring Boot, nhiều thao tác có thể được theo dõi bằng **Micrometer Observation**: nhận HTTP request, gọi dịch vụ khác, truy vấn cơ sở dữ liệu và thực hiện nghiệp vụ. Mỗi Observation có tên và các key-value dùng để tổng hợp **metrics** hoặc làm thuộc tính của **distributed tracing**. Nếu từng nơi tự đặt tên và gắn tag theo cách riêng, nhóm vận hành sẽ khó so sánh độ trễ, ghép nối các tín hiệu và duy trì dashboard.

`GlobalObservationConvention` giúp ứng dụng định nghĩa **quy tắc đặt tên và tạo key-value dùng chung ở cấp `ObservationRegistry` cho các loại `Observation.Context` phù hợp**. Với Spring Boot, ta có thể đăng ký convention này dưới dạng bean hoặc cấu hình trực tiếp trên registry, tùy cách khởi tạo ứng dụng. Bài học giải thích cơ chế chọn convention, cách dùng an toàn, những giới hạn cần biết và quy trình kiểm tra kết quả khi xuất metrics, logs và traces.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `GlobalObservationConvention`, `ObservationConvention`, `ObservationFilter` và các thành phần của `ObservationRegistry`.
2. Giải thích khi nào global convention được lựa chọn và cách nó tương tác với custom/default convention.
3. Viết global convention có `supportsContext` rõ ràng, tên ổn định và key-values được kiểm soát.
4. Đăng ký một global convention trong Spring Boot hoặc trên `ObservationRegistry` độc lập.
5. Phân tích ảnh hưởng của convention đến metric labels, span attributes, cardinality, sampling và context propagation.
6. Kiểm thử giá trị runtime, tìm nguyên nhân khi global convention không có hiệu lực và quản lý thay đổi hợp đồng telemetry.

## 1. ObservationConvention là gì?

Một `Observation` biểu diễn **một lần thực thi** của hoạt động cần quan sát, ví dụ một request gọi giữ hàng. Trong lúc chạy, observation mang một `Observation.Context` chứa dữ liệu về hoạt động đó. `ObservationConvention<T>` là hợp đồng xác định cách đặt tên và tạo `KeyValues` từ context kiểu `T`.

Convention có thể cung cấp:

| Thành phần | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| `getName()` | Tên kỹ thuật ổn định của observation là gì? | `inventory.reserve` |
| `getContextualName(context)` | Trong trace, nên diễn đạt hoạt động như thế nào? | `reserve inventory` |
| `getLowCardinalityKeyValues(context)` | Những giá trị hữu hạn nào phù hợp để tổng hợp metrics? | `inventory.channel=web` |
| `getHighCardinalityKeyValues(context)` | Thuộc tính nhiều giá trị nào có thể giúp điều tra từng trace? | `inventory.attempt.id=...` |
| `supportsContext(context)` | Convention này có hiểu loại context đang xử lý không? | `context instanceof InventoryReserveContext` |

**GlobalObservationConvention** là một biến thể của `ObservationConvention` được đăng ký trên registry để có thể được lựa chọn **tại nhiều nơi tạo Observation** nếu context phù hợp. Từ “global” mô tả **phạm vi đăng ký**, không có nghĩa mọi observation trong ứng dụng đều bắt buộc có cùng tên và tag.

Một global convention cho request HTTP server không nhất thiết áp dụng cho observation nghiệp vụ; một global convention chỉ hỗ trợ `InventoryReserveContext` sẽ không áp dụng cho context của JDBC, Kafka hay HTTP server.

### 1.1. Cơ chế tổng quát

~~~mermaid
flowchart TB
    Factory["Mã instrument tạo Observation với Context và conventions"] --> Selection{"Chọn convention"}
    Custom["Custom convention tại điểm gọi"] --> Selection
    Global["GlobalObservationConvention trong registry"] --> Selection
    Default["Default convention của instrumentation"] --> Selection
    Selection --> Obs["Observation: start / scope / event / error / stop"]
    Obs --> Registry["ObservationRegistry và ObservationHandler"]
    Registry --> Meter["Metrics: tên và low-cardinality tags"]
    Registry --> Span["Traces: spans và attributes"]
    App["Application logger + context tương quan"] --> Log["Logs"]
    Span -. "trace ID / span ID" .-> Log
~~~

Ở đây, **custom**, **global** và **default** là các nguồn quy tắc được xét khi Observation được tạo qua API hỗ trợ convention. Sau khi chọn, handler trong registry xử lý lifecycle và có thể tạo metrics hoặc spans. Logs thường được phát sinh riêng, rồi liên kết bằng trace/span ID nếu tracing đã được cấu hình.

## 2. Khi nào GlobalObservationConvention được chọn?

Khi một instrumentation tạo Observation qua factory nhận **custom convention**, **default convention**, **context supplier** và **registry**, quy tắc ưu tiên thông thường là:

1. **Custom convention** được truyền trực tiếp: có ưu tiên cao nhất.
2. **Global convention** đã đăng ký trên registry và báo hỗ trợ context: được xét nếu không có custom convention.
3. **Default convention** do instrumentation truyền vào: dùng khi không có hai lựa chọn trên.

Trong trường hợp không có convention phù hợp, hành vi còn phụ thuộc factory và instrumentation cụ thể. Vì vậy nên luôn cung cấp default convention hợp lệ cho phần nghiệp vụ tự viết.

| Tình huống | Convention kỳ vọng |
| --- | --- |
| Custom convention được truyền trực tiếp | Custom |
| Custom là `null`, có global hỗ trợ context | Global |
| Custom là `null`, không có global hỗ trợ | Default |
| Global chỉ hỗ trợ context khác | Không chọn global đó |
| Đã gọi `Observation.createNotStarted("fixed.name", registry)` bằng tên trực tiếp | Không tự suy ra rằng global sẽ ghi đè tên; đây là cách tạo khác với factory có chọn convention |

Điểm cuối dễ gây hiểu nhầm: **đăng ký bean `GlobalObservationConvention` không bảo đảm mọi Observation trong ứng dụng đi qua nó**. Instrumentation cần sử dụng API/context-aware convention tương ứng. Với các HTTP, client hoặc framework integrations, cần kiểm tra chúng có tạo Observation thông qua convention nào và có custom convention cụ thể nào đang chiếm ưu tiên hay không.

### 2.1. Phân biệt global convention và ObservationFilter

Hai cơ chế này giải quyết những nhu cầu khác nhau:

- **GlobalObservationConvention**: chọn *tên và tập KeyValues dựa trên một loại context* khi xây dựng Observation. Nó thích hợp khi muốn thay quy tắc của một nhóm hoạt động, ví dụ tất cả thao tác giữ hàng có cùng `inventory.channel`.
- **ObservationFilter**: can thiệp vào `Observation.Context` trong lifecycle để bổ sung/chỉnh sửa thông tin theo chính sách phù hợp. Nó thường được dùng khi muốn bổ sung key-value chung (ví dụ môi trường triển khai) và cần hiểu rõ thời điểm áp dụng.
- **ObservationPredicate**: quyết định một Observation có được ghi nhận hay nên là no-op, ví dụ bỏ qua một luồng không cần quan sát.
- **ObservationHandler**: nhận các callback lifecycle và tạo tín hiệu thực tế như metrics hoặc tracing.

Nếu mục tiêu chỉ là gắn nhãn ứng dụng/môi trường cho **tất cả metrics**, cấu hình common tags của `MeterRegistry` có thể phù hợp hơn. Nếu mục tiêu là ghi một thuộc tính vào **tất cả spans**, cần xem cơ chế tracing/handler tương ứng. Đừng lạm dụng global convention để áp đặt cùng một tên hay cùng một tập key cho các context không liên quan.

## 3. Thiết kế ví dụ cho Spring Boot

Giả sử `order-service` gọi `inventory-service` để giữ hàng. Có hai nguồn gọi: `web` từ API và `batch` từ job. Ta cần quan sát:

- Số lần giữ hàng, thời gian thực thi và tỷ lệ lỗi theo nguồn gọi.
- Thời gian của bước gọi `inventory-service` trong một trace.
- Khả năng tra logs của thao tác theo trace ID khi gặp timeout.

Hợp đồng tín hiệu dự kiến:

| Trường | Giá trị | Lý do |
| --- | --- | --- |
| Tên observation | `inventory.reserve` | Ổn định giữa các nơi gọi |
| Contextual name | `reserve inventory` | Dễ đọc trên trace |
| Low-cardinality `inventory.channel` | `web`, `batch` | Hữu hạn, phù hợp tổng hợp |
| Low-cardinality `inventory.operation` | `reserve` | Tên thao tác |
| High-cardinality `inventory.attempt.id` | Mã thử gọi giả danh | Dùng để tương quan từng lần gọi khi cần |

**Không đưa** order ID, user ID, URL thô, exception message hoặc access token vào metric label. Các thuộc tính high-cardinality cũng phải tuân thủ bảo mật vì có thể được gửi tới trace backend.

### 3.1. Context có kiểu cụ thể

Khi khai báo context riêng, `supportsContext` có thể nhận biết chính xác những Observation mà global convention được phép áp dụng.

~~~java
package com.example.orders.observation;

import io.micrometer.observation.Observation;

public final class InventoryReserveContext extends Observation.Context {
    private final String channel;
    private final String attemptId;

    public InventoryReserveContext(String channel, String attemptId) {
        // Trong ứng dụng thật, hãy chuẩn hóa/kiểm tra channel ở ranh giới đầu vào.
        if (!"web".equals(channel) && !"batch".equals(channel)) {
            throw new IllegalArgumentException("Unsupported channel");
        }
        this.channel = channel;
        this.attemptId = attemptId;
    }

    public String channel() {
        return channel;
    }

    public String attemptId() {
        return attemptId;
    }
}
~~~

Context chỉ chứa dữ liệu của lần gọi; các field này không tự trở thành tag. Convention quyết định field nào được đưa ra ngoài, ở mức cardinality nào và với tên gì.

### 3.2. Default convention dự phòng

Default convention giúp instrumentation của nghiệp vụ có một hợp đồng ổn định ngay cả khi không đăng ký global convention. Trong ví dụ này, default có cùng tên với global nhưng chỉ công bố hai low-cardinality keys.

~~~java
package com.example.orders.observation;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;

public class DefaultInventoryReserveConvention
        implements ObservationConvention<InventoryReserveContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof InventoryReserveContext;
    }

    @Override
    public String getName() {
        return "inventory.reserve";
    }

    @Override
    public String getContextualName(InventoryReserveContext context) {
        return "reserve inventory";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(InventoryReserveContext context) {
        return KeyValues.of(
                KeyValue.of("inventory.channel", context.channel()),
                KeyValue.of("inventory.operation", "reserve"));
    }
}
~~~

Ở đây mọi code dùng tên `inventory.reserve` và tập key xác định rõ. Khi không cần phân tích theo `inventory.operation`, có thể bỏ key này khỏi **cả hợp đồng lẫn truy vấn**, bởi tên metric đã chỉ rõ thao tác; quyết định nên dựa trên nhu cầu vận hành.

## 4. Viết GlobalObservationConvention

Ta tạo một convention toàn cục **chỉ hỗ trợ `InventoryReserveContext`**. Ngoài các low-cardinality key đã có, ví dụ còn công bố mã lần thử gọi ở mức high cardinality.

~~~java
package com.example.orders.observation;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.GlobalObservationConvention;
import io.micrometer.observation.Observation;

public final class GlobalInventoryReserveConvention
        implements GlobalObservationConvention<InventoryReserveContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof InventoryReserveContext;
    }

    @Override
    public String getName() {
        return "inventory.reserve";
    }

    @Override
    public String getContextualName(InventoryReserveContext context) {
        return "reserve inventory";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(InventoryReserveContext context) {
        return KeyValues.of(
                KeyValue.of("inventory.channel", context.channel()),
                KeyValue.of("inventory.operation", "reserve"));
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(InventoryReserveContext context) {
        return KeyValues.of(
                KeyValue.of("inventory.attempt.id", context.attemptId()));
    }
}
~~~

Các quyết định cần chú ý:

1. **Không trả về `true` vô điều kiện từ `supportsContext`** trừ khi thật sự thiết kế một convention áp dụng được cho mọi kiểu context. Một convention muốn cast về `InventoryReserveContext` phải kiểm tra kiểu trước.
2. **Tên kỹ thuật cố định**. Tránh thêm SKU, mã đơn hoặc exception message vào `getName()`.
3. **Giá trị low cardinality hữu hạn**. Context đã giới hạn `channel`; `operation` chỉ có một giá trị trong ví dụ.
4. **High cardinality tách khỏi metrics**. `attemptId` dùng để phân tích trace theo một lần gọi, không phải một nhãn để tổng hợp nhiều request.
5. **Không đòi hỏi mọi handler đều dùng mọi key**. Việc metric/span chứa key nào còn phụ thuộc handler và exporter; kiểm tra ở backend thực.

Giá trị `attemptId` có thể rỗng hoặc không có ở một số luồng trong thực tế. Khi triển khai, cần thống nhất quy tắc chuẩn hóa hoặc bỏ key không hợp lệ, tránh gửi `null` vào `KeyValue.of`. Để ví dụ dễ đọc, ở đây giả định đầu vào hợp lệ và không chứa bí mật.

## 5. Đăng ký convention vào ObservationRegistry

Có hai cách thường gặp. **Chọn một cách phù hợp với nơi tạo registry**, tránh đăng ký cùng một instance hai lần không cần thiết.

### 5.1. Spring Boot: khai báo bean

Với Spring Boot 3.x có observation auto-configuration, các bean thuộc loại `GlobalObservationConvention` được thu nhận để cấu hình `ObservationRegistry` do Boot quản lý.

~~~java
package com.example.orders.observation;

import io.micrometer.observation.GlobalObservationConvention;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ObservationConfiguration {

    @Bean
    GlobalObservationConvention<?> inventoryReserveGlobalConvention() {
        return new GlobalInventoryReserveConvention();
    }
}
~~~

Không cần tạo thêm một `ObservationRegistry` bằng `ObservationRegistry.create()` trong service vì việc đó có thể tạo registry riêng, thiếu các handler/filter do Spring Boot đã cấu hình. Hãy inject bean `ObservationRegistry` được ứng dụng quản lý.

Nếu dự án tự tạo registry hoặc vô hiệu hóa auto-configuration, phải tự kiểm tra cách các convention bean được kết nối với registry đang thực sự sử dụng.

### 5.2. Java thuần hoặc registry tự quản lý

Nếu không dùng Spring Boot auto-configuration, có thể đăng ký convention trực tiếp:

~~~java
import io.micrometer.observation.ObservationRegistry;

ObservationRegistry registry = ObservationRegistry.create();

registry.observationConfig()
        .observationConvention(new GlobalInventoryReserveConvention());
~~~

Đây chỉ là phần **chọn convention**. Một registry mới tạo chưa chắc có metrics/tracing handler, nên chưa thể suy ra rằng Prometheus, OTLP Collector hay trace backend sẽ có dữ liệu. Phải đăng ký handler, registry/exporter và cấu hình pipeline theo hệ thống thực tế.

### 5.3. Sử dụng ở nhiều nơi tạo Observation

Tạo Observation bằng overload nhận custom/default convention và context supplier:

~~~java
package com.example.orders.observation;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class InventoryReservationService {
    private final ObservationRegistry registry;
    private final InventoryGateway gateway;

    public InventoryReservationService(ObservationRegistry registry,
                                       InventoryGateway gateway) {
        this.registry = registry;
        this.gateway = gateway;
    }

    public void reserve(String sku, int quantity, String channel, String attemptId) {
        Observation.createNotStarted(
                null, // Không truyền custom convention.
                new DefaultInventoryReserveConvention(),
                () -> new InventoryReserveContext(channel, attemptId),
                registry)
            .observe(() -> gateway.reserve(sku, quantity));
    }
}

interface InventoryGateway {
    void reserve(String sku, int quantity);
}
~~~

Với bean global convention đã đăng ký và `supportsContext` trả về `true`, lần gọi này chọn global convention. Nếu bỏ bean global, lần gọi vẫn dùng default convention. Nếu truyền một custom convention tại vị trí `null`, custom có ưu tiên cao hơn global.

Khi lambda thực thi, `observe(...)` quản lý start, scope, stop và ghi nhận lỗi nếu lambda ném exception. Nếu gateway gọi API HTTP, cần client được instrument để có span con và truyền trace context sang `inventory-service`.

**Phạm vi của ví dụ:** các public class nên ở những tệp Java riêng theo quy tắc đặt tên của Java; `InventoryGateway` là interface ứng dụng cần triển khai. Cách viết service nhằm minh họa lựa chọn convention và không thay thế xử lý retry, timeout, xác thực hoặc lỗi nghiệp vụ.

## 6. Custom convention, global convention và default convention qua tình huống

Giả sử service giữ hàng được gọi từ HTTP và job. Lúc ban đầu nó sử dụng `DefaultInventoryReserveConvention`. Sau đó đội muốn thống nhất cách quan sát các nguồn gọi ở phạm vi toàn ứng dụng.

| Bối cảnh | Cách khai báo | Kết quả dự kiến |
| --- | --- | --- |
| Chưa đăng ký global | `custom=null`, default được truyền | Dùng `DefaultInventoryReserveConvention` |
| Đăng ký global có `supportsContext` phù hợp | `custom=null`, default được truyền | Dùng `GlobalInventoryReserveConvention` |
| Truyền custom riêng cho một điểm gọi | `custom` khác `null` | Dùng custom, không chọn global |
| Observation dùng `Observation.Context` kiểu khác | Global chỉ hỗ trợ `InventoryReserveContext` | Global không áp dụng; dùng convention phù hợp với context đó |
| Tạo Observation bằng API nhận tên trực tiếp | Không có thông tin custom/default convention | Không giả định global được xét |

Ví dụ về một custom convention tại điểm gọi:

~~~java
// Chỉ minh họa thứ tự ưu tiên; implementation custom phải được
// định nghĩa riêng và hỗ trợ InventoryReserveContext.
Observation.createNotStarted(
        new CustomInventoryReserveConvention(),
        new DefaultInventoryReserveConvention(),
        () -> new InventoryReserveContext("web", "attempt-42"),
        registry)
    .observe(() -> gateway.reserve("SKU-DEMO", 1));
~~~

Không nên định nghĩa nhiều global conventions cùng `supportsContext` cho một loại context rồi dựa vào thứ tự bean hoặc danh sách registry để “đoán” cái nào thắng. Cách an toàn là **giới hạn phạm vi hỗ trợ cho rõ ràng** và kiểm tra hợp đồng trong test khi ứng dụng khởi động.

### 6.1. Global không có nghĩa thay đổi toàn bộ HTTP telemetry

Spring MVC, WebFlux và các HTTP client có convention riêng để tạo tên/tag như route, method, status, outcome. Một custom convention chuyên biệt có thể được cấu hình ở instrumentation đó và có độ ưu tiên cao. Nếu mục tiêu là điều chỉnh metric/tag HTTP, hãy kiểm tra interface convention chuyên biệt tương ứng trước, thay vì dùng một global convention cast mọi context về kiểu tự đặt.

Ví dụ, đưa path thô `/orders/123` vào tag URI sẽ tạo cardinality lớn. Đối với HTTP server, instrumentation thường dùng route template như `/orders/{id}` khi có thông tin mapping; ta nên duy trì quy tắc chuẩn hóa đó khi custom hóa.

## 7. Kết quả ở metrics, traces và logs

Spring Boot có thể cấu hình tích hợp:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    // Chỉ khi cần gửi distributed traces qua OpenTelemetry:
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    // Dùng cho kiểm thử Observation:
    testImplementation 'io.micrometer:micrometer-observation-test'
}
~~~

Với convention trong ví dụ, ta mong đợi:

| Tín hiệu | Những gì có thể quan sát | Điều kiện cần |
| --- | --- | --- |
| **Metrics** | Timer/đếm số lần và thời gian của `inventory.reserve`, phân nhóm theo `inventory.channel` | Metrics handler, `MeterRegistry`, exporter/scrape phù hợp |
| **Traces** | Span của `reserve inventory` nằm trong trace của request, có thuộc tính liên quan | Tracing handler, propagation, sampling và exporter phù hợp |
| **Logs** | Log lỗi/timeout có trace ID và span ID giúp tìm tới trace | Logging được cấu hình correlation và có trace context |

Tên series Prometheus có thể được chuyển đổi từ tên Observation, ví dụ timer tính bằng giây có các series `_seconds_count` hoặc `_seconds_sum`; hãy kiểm tra tên thực ở endpoint `/actuator/prometheus` và backend trước khi viết truy vấn dashboard.

**GlobalObservationConvention không đảm nhận việc gửi dữ liệu.** Metrics phụ thuộc registry; traces phụ thuộc bridge, sampler, exporter và Collector; logs phụ thuộc hệ thống logging. Nếu tracing lấy mẫu 10%, ta không thể kỳ vọng lưu đủ 100% traces, dù metrics vẫn có thể tổng hợp đầy đủ theo đường đi được instrument.

### 7.1. Propagation giữa service và thread

Nếu `order-service` gọi `inventory-service`, HTTP client cần truyền W3C Trace Context (thường có header `traceparent`) để hai span nằm trong cùng trace. Nên sử dụng client được Spring Boot instrument qua builder do Spring quản lý và kiểm tra thực tế ở cả hai phía.

Khi xử lý bất đồng bộ qua `@Async`, executor, Reactor hoặc messaging, cần cơ chế propagation phù hợp. Đăng ký global convention chỉ quyết định tên và tag, **không tự chuyển trace ID giữa các thread hoặc tiến trình**.

Sơ đồ điều tra:

~~~mermaid
sequenceDiagram
    participant User as Client
    participant Order as order-service
    participant Inventory as inventory-service
    participant Otlp as Collector / backend
    User->>Order: POST /orders
    Note over Order: Observation của HTTP request
    Order->>Order: inventory.reserve (global convention)
    Order->>Inventory: reserve + traceparent
    Inventory-->>Order: timeout
    Note over Order: Metrics ghi thời gian; log có trace ID
    Order-->>User: HTTP 503
    Order-->>Otlp: Spans nếu được sampling giữ
    Inventory-->>Otlp: Span phía dịch vụ nhận, nếu có
~~~

Khi gặp lỗi, dùng metrics để biết phạm vi và xu hướng, trace để biết bước nào chậm, logs để xem thông tin timeout và mã lỗi. Một trace đơn lẻ chỉ đại diện cho request đó, không tự chứng minh hiện tượng trên toàn bộ lưu lượng.

## 8. Kiểm soát cardinality và bảo mật

Với mỗi giá trị của một tag, hệ thống metrics có thể tạo tổ hợp time series mới. Nếu `inventory.channel` có 2 giá trị, `inventory.region` có 4, `outcome` có 3 và ứng dụng có 80 instance, một tên metric có thể tạo ra đến **2 × 4 × 3 × 80 = 1.920** tổ hợp series trước khi tính nhãn khác.

| Tag | Mức độ | Quyết định |
| --- | --- | --- |
| `inventory.channel=web/batch` | Low | Dùng nếu cần so sánh nguồn gọi |
| `inventory.operation=reserve` | Low | Dùng khi có lý do rõ ràng |
| `inventory.region=apac/eu/...` | Low nếu danh sách có giới hạn | Kiểm tra số lượng giá trị |
| `inventory.attempt.id=attempt-...` | High | Không đưa vào metric label; cân nhắc trace |
| `inventory.order.id` | High | Tránh metric label; đánh giá rủi ro dữ liệu |
| `exception.message` | High, không ổn định | Không đưa vào nhãn hay span attribute theo mặc định |

Đừng dựa vào cái tên “global” để gắn mọi dữ liệu vào mọi Observation. Chỉ công bố những thuộc tính mà đội vận hành thật sự cần để truy vấn, và chỉ khi dữ liệu được phép thu thập. Cần giới hạn dữ liệu cá nhân và bí mật trong cả low/high cardinality tags, traces và logs.

Quy tắc nên áp dụng trong review:

- Tên Observation ổn định, không chứa thông tin của từng request.
- Low-cardinality tag có danh sách giá trị nhỏ, đã chuẩn hóa và có ý nghĩa vận hành.
- High-cardinality tag chỉ dùng khi cần tương quan; không chứa token, email, payload hoặc thông tin nhạy cảm.
- Có quy ước cách đặt tên, cách đổi schema và chính sách giữ dữ liệu.
- Biết số lượng time series tăng thêm khi bổ sung một low-cardinality key.

## 9. Kiểm thử GlobalObservationConvention

`TestObservationRegistry` thuộc `micrometer-observation-test` cho phép kiểm tra Observation đã được tạo và kết thúc với tên/tag đúng. Một bài kiểm thử nên xác nhận **cả lựa chọn global convention lẫn fallback**.

Ví dụ JUnit 5 và AssertJ:

~~~java
package com.example.orders.observation;

import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class GlobalInventoryReserveConventionTest {

    @Test
    void usesGlobalConventionWhenContextIsSupported() {
        TestObservationRegistry registry = TestObservationRegistry.create();
        registry.observationConfig()
                .observationConvention(new GlobalInventoryReserveConvention());

        Observation.createNotStarted(
                null,
                new DefaultInventoryReserveConvention(),
                () -> new InventoryReserveContext("web", "attempt-demo"),
                registry)
            .observe(() -> { /* thực thi thành công */ });

        assertThat(registry)
            .hasSingleObservationThat()
            .hasBeenStopped()
            .hasNameEqualTo("inventory.reserve")
            .hasLowCardinalityKeyValue("inventory.channel", "web")
            .hasHighCardinalityKeyValue("inventory.attempt.id", "attempt-demo")
            .doesNotHaveError();
    }
}
~~~

Ở ví dụ, **default convention không tạo high-cardinality key**, còn global có tạo. Do đó việc xuất hiện `inventory.attempt.id` trong test là dấu hiệu global được chọn. Test này không chứng minh một span đã tới backend; nó chỉ xác minh Observation runtime và convention được dùng.

Những trường hợp nên kiểm thử thêm:

1. **Không đăng ký global:** Observation vẫn có tên `inventory.reserve` và low-cardinality keys do default convention tạo, nhưng không có `inventory.attempt.id`.
2. **Context không được hỗ trợ:** một Observation khác không bị gắn nhầm các tag `inventory.*`.
3. **Custom convention được truyền trực tiếp:** custom được chọn thay global.
4. **Ném exception trong lambda:** Observation ghi nhận lỗi và được dừng; kiểm tra theo API testing của phiên bản Micrometer đang dùng.
5. **Spring Boot context test:** bean global thật sự nằm trong registry do ứng dụng quản lý; không tồn tại registry riêng bị tạo nhầm.
6. **Integration test:** exporter/backend có nhận metrics/traces như mong đợi, còn tag high cardinality không xuất hiện trên metric labels.

Khi nâng cấp Micrometer/Spring Boot, hãy chạy lại các kiểm thử chọn convention, do overload, auto-configuration và cách biểu diễn metric/exporter có thể thay đổi theo phiên bản.

## 10. Tình huống lỗi và cách điều tra

### 10.1. Đã khai báo bean nhưng global convention không được gọi

Kiểm tra lần lượt:

1. Bean có được Spring quét và tạo không? Class cấu hình có nằm trong phạm vi component scan không?
2. Service có sử dụng `ObservationRegistry` do Spring quản lý hay đã tự tạo một registry khác?
3. Instrumentation có dùng factory nhận context và convention không, hay đang gọi API tạo Observation bằng chuỗi tên trực tiếp?
4. Có **custom convention** nào được truyền vào và được ưu tiên hơn global không?
5. `supportsContext(context)` có trả về `true` cho đúng kiểu context runtime không?
6. Có nhiều global conventions cùng hỗ trợ context đó không? Nếu có, hãy loại bỏ phạm vi chồng chéo.

Nếu không thấy metric ở backend sau khi xác nhận global được chọn, tiếp tục kiểm tra handler, registry metrics, endpoint và exporter. Lỗi chọn convention và lỗi xuất dữ liệu là hai vấn đề riêng.

### 10.2. Metrics có tên đúng nhưng tag sai hoặc thiếu

So sánh các field của context với giá trị do `getLowCardinalityKeyValues` trả về. Kiểm tra input có được chuẩn hóa hay không và handler đã xử lý đủ vòng đời chưa. Một số tag bổ sung bởi filter, handler hoặc instrumentation khác có thể xuất hiện trên dữ liệu thực; cần xem toàn bộ pipeline trước khi kết luận convention sai.

### 10.3. Có metrics nhưng không thấy trace

Kiểm tra tracing bridge, xác suất sampling, context propagation qua HTTP client/thread, địa chỉ OTLP exporter, Collector và backend. Sampling có thể loại bỏ trace nhưng không làm thay đổi ý nghĩa của Observation trong test hoặc metrics. Trace ID xuất hiện trong log không bảo đảm trace được lưu ở hệ thống tracing.

### 10.4. Sau release, dashboard ngừng hiển thị dữ liệu

Cần kiểm tra có đổi `getName()`, key low-cardinality, giá trị tag, cách xuất tên metric hay cấu hình exporter không. Đổi `inventory.channel` sang `source` cần phối hợp với nhóm vận hành và cập nhật truy vấn/alert; nếu cần phải có giai đoạn chuyển tiếp cho schema cũ và mới.

## 11. Checklist thiết kế và vận hành

| Mục cần xác minh | Bằng chứng |
| --- | --- |
| Phạm vi áp dụng chính xác | `supportsContext` giới hạn đúng loại context |
| Có default khi cần | Observation tự viết không phụ thuộc hoàn toàn vào registry global |
| Không có xung đột ưu tiên | Test custom > global > default theo API instrumentation dùng |
| Tên metric/span ổn định | Đã thống nhất tên và cập nhật dashboard/alert |
| Tags low cardinality an toàn | Có tập giá trị hữu hạn và đã ước lượng series |
| Tags high cardinality an toàn | Không chứa bí mật hoặc thông tin cá nhân |
| Registry được quản lý nhất quán | Spring bean hoặc cấu hình thủ công, không dùng registry ngoài ý muốn |
| Metrics và traces thực sự được xuất | Đã xác minh ở hệ thống đích, kể cả tình huống lỗi exporter |
| Log và trace có thể tương quan | Có trace/span ID khi ngữ cảnh hiện diện |
| Quy định sampling/retention rõ ràng | Biết giới hạn tìm trace và chi phí lưu trữ |

## 12. Bài thực hành

**Bối cảnh:** `order-service` có hai luồng thực thi thao tác giữ hàng: API `POST /orders` và job batch. Tỷ lệ request chậm tăng sau đợt triển khai mới. Bạn cần đo thời gian của bước giữ hàng, phân tích theo nguồn gọi và liên kết metrics, logs, traces.

**Yêu cầu thực hiện:**

1. Tạo `InventoryReserveContext` và hai convention như ví dụ, bảo đảm `supportsContext` chỉ áp dụng cho context giữ hàng.
2. Khai báo bean `GlobalObservationConvention<?>` trong Spring Boot, inject `ObservationRegistry` vào service.
3. Gọi thao tác giữ hàng từ hai nguồn `web` và `batch`, lần lượt tạo thành công và timeout giả lập.
4. Viết test chứng minh khi có global convention thì high-cardinality key xuất hiện, và khi không đăng ký global thì default convention được chọn.
5. Kiểm tra metrics ở endpoint/backend và mở trace của một lần giữ hàng chậm nếu trace được sampling giữ lại.
6. Thử thêm custom convention tại một điểm gọi; ghi nhận thứ tự ưu tiên và ảnh hưởng tới tên/tag.
7. Giả lập việc mất trace do sampling hoặc exporter và chứng minh lỗi vẫn có thể được phát hiện bằng metrics/logs.
8. Đề xuất dashboard/alert độ trễ và mô tả cách điều tra khi chỉ một nguồn `batch` bị chậm.

**Kết quả mong đợi:** code của context/conventions/service, test xác minh thứ tự chọn convention, kết quả metrics/tracing và ghi chép điều tra timeout. Nếu backend tracing không sẵn sàng, cần chỉ rõ những bằng chứng có thể kiểm tra tại runtime và giới hạn của kết luận.

## 13. Tổng kết

`GlobalObservationConvention` cho phép đăng ký quy tắc tên và key-values ở cấp `ObservationRegistry` cho **những loại context mà convention hỗ trợ**. Nó hữu ích khi nhiều điểm instrument cần dùng một hợp đồng thống nhất, nhưng vẫn chịu thứ tự ưu tiên của custom/global/default convention. Trong Spring Boot, có thể khai báo bean để tham gia auto-configuration; với registry tự quản lý, cần đăng ký trực tiếp và cấu hình handler/exporter riêng.

Hiệu quả của convention cần được đánh giá trên dữ liệu thật: metrics có tên/tag ổn định và cardinality chấp nhận được; traces giữ đúng mối liên kết qua service/thread; logs hỗ trợ tìm lại trace; sampling và exporter được hiểu rõ. Hợp đồng tốt giúp theo dõi lỗi, độ trễ và hành vi ứng dụng một cách nhất quán ngay cả khi hệ thống lớn dần.

**Tài liệu tra cứu:**

- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer — Testing Observations](https://docs.micrometer.io/micrometer/reference/observation/testing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
