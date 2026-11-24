# ObservationDocumentation trong Micrometer Observation

Khi một ứng dụng Spring Boot có ít thao tác nghiệp vụ, lập trình viên có thể tự đặt tên cho từng phép đo. Khi hệ thống mở rộng, nhiều nhóm cùng instrument metrics và distributed tracing, những tên hoặc tag không nhất quán sẽ khiến dashboard phân mảnh, truy vấn không đầy đủ và việc điều tra lỗi khó khăn.

`ObservationDocumentation` là interface trong package `io.micrometer.observation.docs`. Nó cho phép mô tả **một loại Observation như một hợp đồng** gồm tên, convention mặc định, các key low/high cardinality và thông tin phục vụ sinh tài liệu. Cách triển khai thường dùng là một `enum`, sau đó gọi chính hằng enum khi tạo Observation. Đây là phần thiết kế quan trọng của hệ thống observability dùng **Micrometer Observation, metrics, logs và tracing** trong Spring Boot.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của `ObservationDocumentation` trong hệ sinh thái Micrometer.
2. Phân biệt `Observation`, `Observation.Context`, `ObservationConvention`, `ObservationRegistry` và `ObservationHandler`.
3. Khai báo một enum `ObservationDocumentation` có convention mặc định và bộ key được công bố.
4. Sử dụng enum để instrument nghiệp vụ trong Spring Boot; tùy chỉnh convention khi cần.
5. Quản lý tag/cardinality, hiểu phạm vi của exporter, sampling và context propagation.
6. Sinh tài liệu về metrics/spans, kiểm thử hợp đồng và phát hiện những sai lệch giữa tài liệu với tín hiệu thực.

## 1. Vì sao cần ObservationDocumentation?

Giả sử `order-service` gọi `inventory-service` để giữ hàng. Ba nhóm có thể tự tạo Observation với các tên:

~~~java
Observation.createNotStarted("reserveStock", registry);
Observation.createNotStarted("inventory.reserve", registry);
Observation.createNotStarted("reserve.inventory", registry);
~~~

Đây là ba chuỗi tên khác nhau dù ý nghĩa nghiệp vụ tương tự. Dashboard thống kê `inventory.reserve` sẽ không tìm được dữ liệu có tên khác. Một vấn đề khác là nhóm A dùng tag `channel=web`, nhóm B dùng `source=WEB`, nhóm C vô tình đưa `orderId` vào metric label và làm số time series tăng vọt.

Một hợp đồng Observation giúp thống nhất những điều sau:

| Câu hỏi thiết kế | Thành phần chịu trách nhiệm |
| --- | --- |
| Đang đo thao tác nào? | Tên kỹ thuật ổn định, chẳng hạn `inventory.reserve` |
| Tên trong trace nên dễ đọc ra sao? | Contextual name, ví dụ `reserve inventory` |
| Dữ liệu một lần thực thi đến từ đâu? | `Observation.Context` |
| Dữ liệu nào trở thành tag và tên là gì? | `ObservationConvention` |
| Những key nào được công bố cho người dùng instrumentation? | `ObservationDocumentation` |
| Khi chạy thực tế, ai tạo metric hoặc span? | `ObservationHandler` được đăng ký với `ObservationRegistry` |
| Người vận hành xem hợp đồng tên/tag ở đâu? | Tài liệu sinh từ mã nguồn bằng Micrometer Docs Generator |

`ObservationDocumentation` **không phải exporter** và không tự ghi metric, log hoặc span. Nó khai báo hợp đồng. Runtime phải tạo Observation, thực thi lifecycle và có các handler thích hợp.

### 1.1. Các thành phần phối hợp

~~~mermaid
flowchart TD
    Doc["ObservationDocumentation enum<br/>Tên, key, default convention"] --> Inst["Instrumentation code"]
    Conv["ObservationConvention<br/>Tên và KeyValues từ Context"] --> Inst
    Ctx["Observation.Context<br/>Dữ liệu một lần thực thi"] --> Inst
    Inst --> Obs["Observation"]
    Obs --> Registry["ObservationRegistry + handlers"]
    Registry --> Metrics["Metrics / MeterRegistry"]
    Registry --> Tracing["Tracing / spans"]
    Doc --> Generator["Micrometer Docs Generator"]
    Conv --> Generator
    Generator --> Ascii["Tài liệu AsciiDoc"]
~~~

- **`Observation`** là một lần thực thi cụ thể. Nó có `start`, `stop`, `Scope`, `Event`, có thể ghi nhận exception.
- **`Observation.Context`** chứa dữ liệu có liên quan đến lần thực thi đó. Không phải mọi trường trong context đều tự động trở thành tag.
- **`ObservationConvention<T>`** chuyển một context thành tên kỹ thuật, contextual name và các `KeyValues` với mức cardinality tương ứng.
- **`ObservationDocumentation`** công bố metadata: convention mặc định, prefix và các key. Nó có các phương thức tiện ích tạo Observation theo convention đã được chọn.
- **`ObservationRegistry`** quản lý cấu hình convention, predicate, filter và handler. Handler theo dõi lifecycle để ghi metric hoặc tạo span khi được cấu hình.

Một Observation có thể góp phần tạo **metrics** và **traces**. **Logs** thường được phát sinh riêng bằng framework logging; có thể liên kết với trace nhờ trace ID và span ID được truyền trong ngữ cảnh, nhưng enum tài liệu không tự tạo log.

### 1.2. Tên kỹ thuật khác contextual name

Tên kỹ thuật như `inventory.reserve` cần ổn định cho truy vấn và tổng hợp. Contextual name như `reserve inventory` có thể giúp người đọc trace hiểu thao tác. Backend có thể chuyển đổi tên theo chuẩn registry hoặc exporter, vì vậy luôn kiểm tra dữ liệu thực sau khi xuất.

Đừng đưa biến động của request vào tên, ví dụ `inventory.reserve.order-123`. Hãy giữ tên ổn định và dùng tag có tập giá trị được kiểm soát để phân nhóm.

## 2. Thiết kế một hợp đồng cho thao tác giữ hàng

Bài học dùng ví dụ Spring Boot `order-service` gọi hệ thống tồn kho. Chúng ta muốn đo độ trễ của mỗi lần giữ hàng, quan sát bước gọi này trong distributed trace và phân nhóm theo nguồn phát sinh.

| Thành phần | Giá trị mẫu | Ý nghĩa |
| --- | --- | --- |
| Observation name | `inventory.reserve` | Tên kỹ thuật của thao tác |
| Contextual name | `reserve inventory` | Tên hiển thị trong trace |
| Key prefix | `inventory` | Không gian tên thống nhất |
| Low-cardinality key | `inventory.channel` | `web` hoặc `batch` |
| Low-cardinality key | `inventory.operation` | Giá trị `reserve` |
| High-cardinality key | `inventory.attempt.id` | Mã lần thử gọi nội bộ để tương quan |

Mã `inventory.attempt.id` là mã giả danh dành riêng cho thao tác, không chứa dữ liệu cá nhân, token hoặc nội dung đơn hàng. Mã này có nhiều giá trị nên không được dùng làm metric label; chỉ giữ trong trace khi có nhu cầu điều tra và quy định dữ liệu cho phép.

### 2.1. Context giữ dữ liệu của một lần chạy

~~~java
package com.example.orders.observation;

import io.micrometer.observation.Observation;

final class InventoryReserveContext extends Observation.Context {
    private final String channel;
    private final String attemptId;

    InventoryReserveContext(String channel, String attemptId) {
        this.channel = channel;
        this.attemptId = attemptId;
    }

    String channel() {
        return channel;
    }

    String attemptId() {
        return attemptId;
    }
}
~~~

`channel` phải được chuẩn hóa **trước khi tạo context**, chỉ có hai giá trị `web` và `batch`. Không nên lấy trường tự do của client làm low-cardinality tag. Với dữ liệu có nguồn khác, hãy quy định giá trị `other` hoặc mở rộng danh sách theo một thay đổi hợp đồng đã được đánh giá.

## 3. Tạo ObservationConvention mặc định

`ObservationConvention` xác định **giá trị xuất hiện ở runtime**, được tính từ context. Một interface dành riêng cho loại context giúp người dùng instrumentation thay thế convention mà không sửa logic xử lý.

~~~java
package com.example.orders.observation;

import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;

interface InventoryReserveObservationConvention
        extends ObservationConvention<InventoryReserveContext> {

    @Override
    default boolean supportsContext(Observation.Context context) {
        return context instanceof InventoryReserveContext;
    }
}

final class DefaultInventoryReserveObservationConvention
        implements InventoryReserveObservationConvention {

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
                InventoryReserveObservationDocumentation.LowCardinalityKeyNames
                        .CHANNEL.withValue(context.channel()),
                InventoryReserveObservationDocumentation.LowCardinalityKeyNames
                        .OPERATION.withValue("reserve"));
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(InventoryReserveContext context) {
        return KeyValues.of(
                InventoryReserveObservationDocumentation.HighCardinalityKeyNames
                        .ATTEMPT_ID.withValue(context.attemptId()));
    }
}
~~~

`supportsContext` nhận biết loại context. `getName` và `getContextualName` quy định tên. `getLowCardinalityKeyValues` và `getHighCardinalityKeyValues` trả về giá trị tag. Ở đây tên của key được tham chiếu từ enum sẽ tạo trong phần tiếp theo để tránh lặp chuỗi tên tại nhiều nơi.

Đổi `getName()` khi hệ thống đã chạy có thể làm gãy dashboard và alert. Thêm một low-cardinality key cũng có thể làm tăng số series, vì vậy không phải thay đổi hoàn toàn mang tính nội bộ.

## 4. Định nghĩa enum ObservationDocumentation

Hình thức thông dụng là `enum implements ObservationDocumentation`. Mỗi hằng enum đại diện cho một loại thao tác. `KeyName` trong package `io.micrometer.common.docs` mô tả tên từng tag.

~~~java
package com.example.orders.observation;

import io.micrometer.common.docs.KeyName;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;
import io.micrometer.observation.docs.ObservationDocumentation;

/** Hợp đồng tín hiệu cho các thao tác với inventory-service. */
public enum InventoryReserveObservationDocumentation implements ObservationDocumentation {

    /** Một lần giữ hàng ở hệ thống tồn kho. */
    RESERVE {
        @Override
        public Class<? extends ObservationConvention<? extends Observation.Context>>
                getDefaultConvention() {
            return DefaultInventoryReserveObservationConvention.class;
        }

        @Override
        public String getContextualName() {
            return "reserve inventory";
        }

        @Override
        public String getPrefix() {
            return "inventory";
        }

        @Override
        public KeyName[] getLowCardinalityKeyNames() {
            return LowCardinalityKeyNames.values();
        }

        @Override
        public KeyName[] getHighCardinalityKeyNames() {
            return HighCardinalityKeyNames.values();
        }
    };

    /** Tên key có tập giá trị hữu hạn, phù hợp cho metrics. */
    public enum LowCardinalityKeyNames implements KeyName {
        /** Nguồn gọi được chuẩn hóa thành web hoặc batch. */
        CHANNEL {
            @Override
            public String asString() {
                return "inventory.channel";
            }
        },
        /** Loại thao tác đang theo dõi. */
        OPERATION {
            @Override
            public String asString() {
                return "inventory.operation";
            }
        }
    }

    /** Tên key có nhiều giá trị, dùng có kiểm soát khi cần tracing. */
    public enum HighCardinalityKeyNames implements KeyName {
        /** Mã giả danh của một lần thử gọi, không chứa dữ liệu nhạy cảm. */
        ATTEMPT_ID {
            @Override
            public String asString() {
                return "inventory.attempt.id";
            }
        }
    }
}
~~~

### 4.1. Đọc hợp đồng từng phương thức

| Phương thức | Vai trò |
| --- | --- |
| `getDefaultConvention()` | Khai báo class convention mặc định, hữu ích cho hợp đồng và công cụ sinh tài liệu |
| `getContextualName()` | Metadata tên theo ngữ cảnh, ví dụ `reserve inventory` |
| `getPrefix()` | Prefix được yêu cầu cho tag, ví dụ `inventory` |
| `getLowCardinalityKeyNames()` | Danh sách tên key có tập giá trị hữu hạn |
| `getHighCardinalityKeyNames()` | Danh sách tên key có thể có rất nhiều giá trị |
| `KeyName.asString()` | Trả về chuỗi tên key thực tế |

Convention xác định các **giá trị** của tag; enum công bố **tên và phân loại** của tag. Hai phần phải nhất quán. Ví dụ `getPrefix() = "inventory"` đi với `inventory.channel`, `inventory.operation`; một key trần `channel` sẽ không tuân theo quy ước prefix này.

`getDefaultConvention()` trả về `Class` để mô tả convention. Để chạy ở runtime, ứng dụng vẫn truyền **instance** convention phù hợp khi tạo Observation. Enum không tự đăng ký instance đó vào registry.

### 4.2. Hợp đồng không tự xác minh toàn bộ runtime

Enum không tự động ngăn một đoạn mã khác thêm tag chưa khai báo; không bảo đảm mọi key đều xuất hiện trong các Observation đã chạy; không bảo đảm exporter hoạt động hoặc các high-cardinality key an toàn dữ liệu. Các thuộc tính này cần được xác minh bằng unit/integration test và theo dõi backend.

## 5. Instrument nghiệp vụ bằng hằng enum

Trong Spring Boot có Actuator/Micrometer, `ObservationRegistry` được quản lý như bean và có thể inject vào service. Đây là ví dụ gọi giữ hàng bằng API tiện ích `.observation(...)` của enum:

~~~java
package com.example.orders.observation;

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
        // channel đã được chuẩn hóa thành web hoặc batch.
        InventoryReserveContext context = new InventoryReserveContext(channel, attemptId);

        InventoryReserveObservationDocumentation.RESERVE
                .observation(
                        null, // Không có custom convention: chọn global hoặc default.
                        new DefaultInventoryReserveObservationConvention(),
                        () -> context,
                        registry)
                .observe(() -> gateway.reserve(sku, quantity));
    }
}

interface InventoryGateway {
    void reserve(String sku, int quantity);
}
~~~

Ví dụ chia thành nhiều snippet để tập trung giải thích; trong dự án thật, hãy đặt mỗi public type vào file Java cùng tên và cung cấp implementation `InventoryGateway`. Khi `.observe(...)` chạy, Micrometer bắt đầu Observation, đưa nó vào scope, thực thi lambda, ghi nhận lỗi nếu có exception, đóng scope và dừng Observation. Handler được cấu hình trên registry quyết định những tín hiệu được ghi nhận.

### 5.1. Thứ tự ưu tiên khi chọn convention

Khi tạo Observation với **custom convention**, **default convention**, **context supplier** và **registry**, Micrometer chọn convention theo thứ tự:

1. Custom convention truyền trực tiếp, nếu không phải `null`.
2. Global convention đăng ký trên registry, hỗ trợ loại context.
3. Default convention truyền vào lời gọi, khi không có hai lựa chọn trên.

Một `CustomInventoryReserveObservationConvention` có thể đổi tên hoặc bổ sung nhãn `inventory.region` (với tập giá trị hữu hạn) mà không cần thay code gọi gateway. Khi thay tên/tag, phải cập nhật hợp đồng, tài liệu, truy vấn và cảnh báo liên quan.

Nếu cần bổ sung một tag cố định cho **mọi** observation bất kể convention nào được chọn, có thể xem xét `ObservationFilter` phù hợp; `ObservationPredicate` lại dùng để quyết định có tạo Observation thực sự hay no-op. Hai cơ chế này khác với việc khai báo metadata trong `ObservationDocumentation`.

## 6. Kết nối với metrics, traces, logs và propagation

~~~mermaid
sequenceDiagram
    participant Order as order-service
    participant Doc as ObservationDocumentation
    participant Reg as ObservationRegistry
    participant Metric as Metrics handler
    participant Trace as Tracing handler
    participant Inventory as inventory-service
    Order->>Doc: RESERVE.observation(...)
    Doc->>Reg: Tạo Observation với context/convention
    Order->>Reg: observe(...)
    Reg->>Metric: onStart / onStop
    Reg->>Trace: onStart / onStop
    Order->>Inventory: HTTP có traceparent khi được instrument
    Inventory-->>Order: Kết quả giữ hàng
~~~

- **Metrics:** khi có metrics handler và `MeterRegistry` phù hợp, Observation có thể tạo đo lường thời gian và tags low cardinality. Định dạng tên xuất sang Prometheus có thể thay đổi, chẳng hạn timer được biểu diễn thành các series `_seconds_count` và `_seconds_sum`.
- **Tracing:** tracing handler có thể tạo span, kết hợp thông tin low/high cardinality khi phù hợp. Việc span xuất hiện ở backend phụ thuộc sampling, exporter, collector và cấu hình của tracing bridge.
- **Logs:** logger ứng dụng ghi sự kiện riêng. MDC có thể mang trace ID/span ID để tìm log thuộc cùng trace, nhưng enum tài liệu không tự phát log.
- **Propagation:** khi service gọi service khác, cần HTTP client được instrument và truyền W3C Trace Context (thường là header `traceparent`). Với `@Async` hoặc executor, phải thiết lập cơ chế truyền ngữ cảnh tương ứng. `ObservationDocumentation` không tự bảo đảm trace không bị đứt ở những ranh giới này.

Ví dụ các dependency Gradle khi ứng dụng dùng BOM quản lý phiên bản của Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    testImplementation 'io.micrometer:micrometer-observation-test'
}
~~~

Đây là các dependency tham khảo cho dòng Spring Boot có tích hợp Micrometer tương thích. Muốn xem metrics ở `/actuator/prometheus`, phải cấu hình endpoint và giới hạn quyền truy cập phù hợp. Muốn xem traces, phải cấu hình exporter, Collector/backend và sampling; thêm thư viện chưa đồng nghĩa dữ liệu đã đến backend.

## 7. Cardinality: hợp đồng tốt giúp kiểm soát chi phí

| Tag | Giá trị minh họa | Cardinality | Khuyến nghị |
| --- | --- | --- | --- |
| `inventory.channel` | `web`, `batch` | Low | Phù hợp tổng hợp metrics |
| `inventory.operation` | `reserve` | Low | Hợp lý, dù có thể thừa nếu tên đã đủ rõ |
| `inventory.outcome` | `success`, `failure` | Low | Có thể thêm, nhưng phải cập nhật enum và convention |
| `inventory.attempt.id` | Mỗi lần thử một mã | High | Không đưa vào metric label |
| `inventory.order.id` | Mỗi đơn một mã | High | Không đưa vào metric label; cần đánh giá bảo mật |
| `http.url` nguyên bản | `/orders/123456` | High | Dùng template `/orders/{id}` thay thế |

Nếu một metric có 3 vùng, 2 channel, 4 outcome và 100 instance, số tổ hợp label có thể lên đến **3 × 2 × 4 × 100 = 2.400** cho riêng metric đó, trước khi cộng thêm các nhãn khác. Đây là ví dụ nhân số lượng tập giá trị, không phải con số mặc định của Micrometer.

High-cardinality key không tự động là “chỉ dùng nội bộ”: nó có thể được xuất trong trace, lưu ở backend và truy cập bởi người dùng hệ thống quan sát. Vì vậy vẫn phải áp dụng phân loại dữ liệu, giới hạn quyền, thời gian lưu và chính sách loại bỏ thông tin nhạy cảm.

Khi thêm một key `inventory.outcome`, cần bảo đảm giá trị được cập nhật đúng vào lúc quyết định kết quả, tập nhãn nhất quán ở các đường đi thành công/thất bại, và hợp đồng có mô tả. Không gắn tag động theo request ID, exception message hoặc một URL chưa chuẩn hóa.

## 8. Sinh tài liệu bằng Micrometer Docs Generator

**Micrometer Docs Generator** là công cụ riêng có thể quét mã nguồn chứa `ObservationDocumentation` và các convention để sinh tài liệu AsciiDoc về metrics, spans và conventions. Công cụ không chạy tự động chỉ vì có dependency Actuator.

~~~mermaid
flowchart LR
    Doc["ObservationDocumentation enum"] --> Generator["Docs Generator"]
    Conv["Default Convention"] --> Generator
    Generator --> M["_metrics.adoc"]
    Generator --> S["_spans.adoc"]
    Generator --> C["_conventions.adoc (tùy cấu hình)"]
    M --> Docs["Tài liệu kỹ thuật / runbook"]
    S --> Docs
    C --> Docs
~~~

Một task Gradle tham khảo (khai báo `micrometerDocsVersion` ở nơi quản lý phiên bản của dự án):

~~~groovy
configurations {
    observabilityDocs
}

dependencies {
    observabilityDocs "io.micrometer:micrometer-docs-generator:$micrometerDocsVersion"
}

tasks.register('generateObservabilityDocs', JavaExec) {
    mainClass = 'io.micrometer.docs.DocsGeneratorCommand'
    classpath = configurations.observabilityDocs
    // Source root, inclusion pattern, output folder.
    args project.rootDir.absolutePath, '.*',
            layout.buildDirectory.dir('generated-observability-docs').get().asFile.absolutePath
}
~~~

Sau khi chọn version phù hợp, thêm repository cần thiết và cấu hình task, có thể chạy:

~~~bash
./gradlew generateObservabilityDocs
~~~

Output thường có bảng các tên metrics/spans và tập tag, trong những file như `_metrics.adoc`, `_spans.adoc`. Tùy version và tùy chọn, công cụ còn tạo tài liệu conventions. Phải kiểm tra tài liệu sinh thật: tên file, trường dữ liệu và cấu hình generator có thể thay đổi. Không coi tài liệu được sinh là bằng chứng exporter hoạt động hoặc một trace đã được lưu.

Ví dụ nội dung ta muốn người đọc tìm thấy trong tài liệu (bảng mô phỏng, **không phải output nguyên văn**):

| Metadata | Giá trị kỳ vọng |
| --- | --- |
| Observation | `RESERVE` |
| Convention mặc định | `DefaultInventoryReserveObservationConvention` |
| Tên kỹ thuật | `inventory.reserve` |
| Low-cardinality keys | `inventory.channel`, `inventory.operation` |
| High-cardinality keys | `inventory.attempt.id` |

Chú thích JavaDoc trên enum và từng hằng key giúp tài liệu sinh ra thể hiện được ý nghĩa, không chỉ liệt kê tên. Khi đổi hợp đồng, nên sinh lại tài liệu và xem thay đổi như một phần của review code.

## 9. Kiểm thử hợp đồng và tín hiệu runtime

Thư viện `micrometer-observation-test` cung cấp `TestObservationRegistry` để kiểm tra lifecycle, tên và key thực tế của Observation. Ví dụ đơn vị kiểm thử JUnit 5:

~~~java
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class InventoryReservationServiceTest {

    @Test
    void recordsReservationWithDocumentedKeys() {
        TestObservationRegistry registry = TestObservationRegistry.create();
        InventoryGateway gateway = (sku, quantity) -> { /* thành công */ };
        InventoryReservationService service =
                new InventoryReservationService(registry, gateway);

        service.reserve("SKU-DEMO", 2, "web", "attempt-demo-1");

        assertThat(registry)
                .hasSingleObservationThat()
                .hasBeenStopped()
                .hasNameEqualTo("inventory.reserve")
                .hasLowCardinalityKeyValue("inventory.channel", "web")
                .hasLowCardinalityKeyValue("inventory.operation", "reserve")
                .hasHighCardinalityKeyValue("inventory.attempt.id", "attempt-demo-1")
                .doesNotHaveError();
    }
}
~~~

Đặt test trong cùng package với các type package-private của ví dụ hoặc điều chỉnh phạm vi truy cập. Nên thêm một test cho exception để kiểm tra lỗi được ghi nhận, và một test bảo đảm các key trong enum tương ứng với các key do convention trả về. Đây là những kiểm thử hợp đồng có ý nghĩa hơn việc chỉ tìm xem enum có tồn tại.

| Mức kiểm tra | Cần xác minh |
| --- | --- |
| **Metadata** | Enum khai báo đúng convention, prefix, danh sách key và mô tả |
| **Runtime** | Service tạo Observation qua enum; lifecycle, name và tags đúng |
| **Metrics** | Backend nhận dữ liệu, không có attempt ID trong metric label |
| **Traces** | Có span phù hợp, liên kết parent/child đúng, biết giới hạn sampling |
| **Logs** | Có trace ID khi dùng correlation, không lộ dữ liệu nhạy cảm |
| **Exporter** | Collector/backend nhận dữ liệu và lỗi pipeline được phát hiện |
| **Tài liệu** | Docs Generator tạo bảng tên/key khớp với instrumentation |

Nếu không thấy một trace, đừng kết luận ngay rằng Observation không chạy. Tracing có thể bị sampling loại bỏ, header ngữ cảnh bị mất ở HTTP client, scope bị đứt khi chuyển thread hoặc exporter/collector không nhận được span. Metrics và logs giúp phân biệt các khả năng này.

## 10. Các lỗi thường gặp khi dùng ObservationDocumentation

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Có enum nhưng vẫn tạo Observation bằng chuỗi tên tự do | Backend có tên khác tài liệu | Tạo qua hằng enum |
| Convention thêm key chưa khai báo | Tài liệu thiếu nhãn thực tế | Đồng bộ enum, convention và test |
| High-cardinality key bị đưa vào metrics | Series tăng không kiểm soát | Chỉ dùng low-cardinality label có tập giá trị hữu hạn |
| Dùng ID/token trong high-cardinality tag | Rủi ro lộ dữ liệu ở trace backend | Giảm thu thập, dùng mã giả danh và phân quyền |
| Đổi `getName()` không cập nhật alert | Dashboard/alert mất dữ liệu | Quản lý thay đổi hợp đồng cùng truy vấn |
| Cho rằng enum tự tạo metric/span | Không có tín hiệu runtime | Cấu hình registry/handler/exporter và gọi Observation |
| Nhầm contextual name với metric name | Khó tìm kiếm hoặc so sánh | Quy ước hai tên và kiểm tra output thực tế |
| Chỉ kiểm tra tài liệu sinh ra | Không thấy sự cố exporter và propagation | Xác minh cả runtime và backend |

Khi đổi tên tag hoặc observation đã vận hành, hãy xác định truy vấn, dashboard, cảnh báo SLO, dữ liệu lịch sử và thời gian giữ schema cũ. Đổi tên một metric không làm lỗi API HTTP, nhưng có thể làm hệ thống cảnh báo không phát hiện được sự cố.

## 11. Bài thực hành

**Bối cảnh:** ứng dụng Spring Boot có hai nguồn giữ hàng: request từ `POST /orders` và job chạy theo lịch. Nhóm vận hành muốn so sánh độ trễ giữa hai nguồn, mở trace của lần giữ hàng chậm và dùng cùng hợp đồng trong code lẫn tài liệu.

**Yêu cầu:**

1. Viết `InventoryReserveObservationDocumentation`, `InventoryReserveContext` và default convention như mẫu; chú thích từng key bằng JavaDoc.
2. Chuẩn hóa channel thành `web` hoặc `batch`, tạo một Observation thành công và một Observation ném exception.
3. Dùng `TestObservationRegistry` kiểm tra tên, lifecycle, tags low/high cardinality và thông tin lỗi.
4. Chạy Docs Generator nếu dự án đã cấu hình công cụ; so sánh tài liệu sinh ra với convention trong mã.
5. Kiểm tra metrics tại backend, mở một span mẫu và đối chiếu trace ID trong logs khi có tích hợp tracing.
6. Giả sử đề xuất thêm `inventory.order.id` vào low-cardinality tags. Phân tích số lượng giá trị có thể tăng và đề xuất phương án thay thế.
7. Giả lập trường hợp không tìm thấy trace; lần lượt kiểm tra sampling, propagation, exporter và collector trước khi kết luận.

**Kết quả mong đợi:** một hợp đồng có thể đọc hiểu, các test xác minh runtime, bảng tên/tag trong tài liệu sinh ra, và ghi chép giải thích tín hiệu metrics/traces/logs nhận được trong môi trường thử nghiệm.

## 12. Ghi nhớ

`ObservationDocumentation` là cách giữ **hợp đồng observability sát với mã nguồn**: một thao tác có tên, convention mặc định và tập key được công bố. `ObservationConvention` tạo giá trị thực tế; `ObservationRegistry` và handler kết nối lifecycle với metrics/tracing; Micrometer Docs Generator đưa hợp đồng đó vào tài liệu. Chất lượng quan sát của ứng dụng Spring Boot còn phụ thuộc cardinality, context propagation, exporter, sampling và cách logs/traces được liên kết trong thực tế.

**Tài liệu tham khảo:**

- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer — Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer — Testing Observations](https://docs.micrometer.io/micrometer/reference/observation/testing.html)
- [Micrometer Docs Generator — Overview](https://docs.micrometer.io/micrometer-docs-generator/reference/)
