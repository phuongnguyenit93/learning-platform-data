# Kiểm thử convention trong Micrometer Observation

Khi một dịch vụ Spring Boot phát sinh metrics và distributed traces, **`ObservationConvention`** quyết định nhiều thông tin mà người vận hành nhìn thấy: tên thao tác, tên span, nhãn metrics và thuộc tính phục vụ điều tra. Một lỗi nhỏ như thay `inventory.channel` bằng `channel`, đưa mã đơn hàng vào low-cardinality tag hoặc để convention áp dụng nhầm loại context có thể không làm hỏng API nghiệp vụ, nhưng khiến dashboard, alert và traces sai lệch.

Vì vậy, **kiểm thử convention** là một phần của chất lượng observability: cần kiểm tra **hợp đồng đặt tên và key-values**, **quy tắc chọn custom/global/default convention**, **tương tác với filter**, **vòng đời Observation** và **kết quả thực tế ở metrics/traces/logs**. Bài thuộc chương **Convention và filter** của module **SPRING_BOOT_OBSERVABILITY**, tập trung vào Spring Boot kết hợp Micrometer Observation, metrics, logs, distributed tracing và các quyết định liên quan đến context propagation, cardinality, exporter, sampling.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định những thuộc tính quan trọng cần kiểm thử đối với một `ObservationConvention`.
2. Viết unit test cho tên, contextual name, `supportsContext` và các `KeyValues`.
3. Sử dụng `TestObservationRegistry` để kiểm chứng Observation thực sự được tạo, dừng và mang key-values đúng.
4. Kiểm tra thứ tự ưu tiên **custom > global > default** theo API tạo Observation có nhận convention.
5. Kiểm thử tương tác của `ObservationFilter` với context và phân biệt filter với convention.
6. Phát hiện lỗi cardinality và dữ liệu nhạy cảm trước khi metadata xuất hiện trong metrics hoặc traces.
7. Chọn đúng mức kiểm thử khi cần xác minh handler, exporter, sampling, logs và propagation trong ứng dụng Spring Boot.

## 1. Kiểm thử điều gì và vì sao?

Một `Observation` đại diện cho một lần thực thi, ví dụ thao tác giữ hàng. `Observation.Context` giữ dữ liệu liên quan đến lần thực thi đó. `ObservationConvention<T>` diễn giải context thành tên và metadata của tín hiệu quan sát.

| Đối tượng | Trách nhiệm | Câu hỏi kiểm thử |
| --- | --- | --- |
| `Observation.Context` | Mang dữ liệu của một lần chạy | Dữ liệu có được chuẩn hóa trước khi thành tag không? |
| `ObservationConvention<T>` | Chọn tên, contextual name và key-values | Có đúng tên, đúng bộ key, đúng low/high cardinality không? |
| `GlobalObservationConvention<T>` | Cung cấp convention đăng ký tại registry cho context phù hợp | Có được chọn đúng lúc và tránh áp dụng nhầm context không? |
| `ObservationFilter` | Điều chỉnh `Observation.Context` trong lifecycle | Có bổ sung metadata mong muốn và tránh rò rỉ dữ liệu không? |
| `ObservationPredicate` | Quyết định có ghi nhận observation hay dùng no-op | Luồng cần theo dõi có vô tình bị loại không? |
| `ObservationRegistry` và handlers | Xử lý lifecycle để có metrics, spans hoặc các tác động khác | Observation có dừng, ghi lỗi và được handler xử lý không? |
| Exporter và backend | Vận chuyển/lưu dữ liệu | Metrics hoặc trace có thật sự đến nơi người vận hành tra cứu không? |

Một convention tốt phải thỏa các bất biến cơ bản:

- Tên kỹ thuật ổn định, ví dụ `inventory.reserve`; không chứa ID của từng request.
- `supportsContext` chỉ trả về `true` cho context mà convention thực sự xử lý được.
- Tập key low cardinality có tên và giá trị được kiểm soát, không tăng theo lượng request.
- High-cardinality metadata không bị đưa thành label metrics và không chứa dữ liệu bí mật.
- Contextual name dễ đọc, không thay đổi tùy tiện giữa các bản phát hành.
- Hợp đồng tài liệu (`ObservationDocumentation` nếu có) khớp với key-values runtime.

Không nhất thiết kiểm thử mọi implementation chi tiết. Kiểm thử nên bảo vệ **những đặc tính mà dashboard, alert, truy vấn và người trực sự cố phụ thuộc**.

## 2. Phân biệt các tầng kiểm thử

~~~mermaid
flowchart TD
    A["Unit test ObservationConvention"] --> B["Runtime test với TestObservationRegistry"]
    B --> C["Metric handler test với SimpleMeterRegistry"]
    C --> D["Spring Boot integration test"]
    D --> E["Kiểm chứng exporter, backend và correlation"]
~~~

| Tầng | Có thể xác minh | Chưa chứng minh được |
| --- | --- | --- |
| **Unit test convention** | `getName`, `getContextualName`, `supportsContext`, low/high KeyValues | Registry hoặc handler có sử dụng convention không |
| **TestObservationRegistry** | Lựa chọn convention trong thực thi, lifecycle, lỗi, key-values trên context | Metrics/spans đã xuất sang backend |
| **SimpleMeterRegistry** | Tên metric, low-cardinality tags, số lần và thời gian được ghi | OTLP/Prometheus exporter hoạt động trên môi trường thật |
| **Spring Boot integration test** | Bean auto-configuration, registry được inject, luồng ứng dụng hoạt động | Pipeline production đầy đủ hoặc hành vi sampling thực tế |
| **Staging/end-to-end** | Trace nối nhiều service, log correlation, exporter và backend nhận tín hiệu | Mọi request production đều có trace; sampling/retention có thể gây thiếu |

Đặt test gần logic cần bảo vệ. Một unit test pure Java nhanh và giúp phát hiện đổi tên key. Kiểm thử end-to-end đắt hơn nhưng cần thiết cho ranh giới mà unit test không thấy, chẳng hạn HTTP propagation hoặc lỗi Collector.

## 3. Ví dụ nghiệp vụ: giữ hàng cho đơn đặt hàng

Giả sử ứng dụng `order-service` (Spring Boot) gọi `inventory-service`. Một thao tác `inventory.reserve` được chạy từ web hoặc job batch. Ta muốn theo dõi thời gian giữ hàng theo nguồn gọi, rồi mở trace của một lần thử khi có timeout.

Hợp đồng kỳ vọng:

| Thành phần | Giá trị | Phạm vi |
| --- | --- | --- |
| Tên observation | `inventory.reserve` | Ổn định để truy vấn |
| Contextual name | `reserve inventory` | Hiển thị trong trace |
| `inventory.channel` | `web` hoặc `batch` | Low cardinality |
| `inventory.operation` | `reserve` | Low cardinality |
| `inventory.attempt.id` | ID giả danh của lần thử | High cardinality |

Không dùng order ID, user ID, email, token, đường dẫn URL thô hoặc exception message làm low-cardinality tag. Nếu thật sự cần metadata nhiều giá trị để điều tra, hãy bảo đảm nguồn dữ liệu an toàn và dùng high cardinality một cách có kiểm soát.

### 3.1. Context nhận đầu vào đã được kiểm soát

Trong một tệp `ReserveContext.java`:

~~~java
package com.example.observability;

import io.micrometer.observation.Observation;

public final class ReserveContext extends Observation.Context {
    private final String channel;
    private final String attemptId;

    public ReserveContext(String channel, String attemptId) {
        if (!"web".equals(channel) && !"batch".equals(channel)) {
            throw new IllegalArgumentException("Unsupported channel");
        }
        if (attemptId == null || attemptId.isBlank()) {
            throw new IllegalArgumentException("Missing attemptId");
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

`attemptId` được giả định là mã ngẫu nhiên nội bộ, không suy ra dữ liệu cá nhân và có giới hạn độ dài tại nơi sinh. Kiểm tra ở constructor bảo đảm test sẽ thất bại sớm nếu lập trình viên định dùng giá trị channel tùy ý.

### 3.2. Convention mặc định

Trong `ReserveConvention.java`:

~~~java
package com.example.observability;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;

public class ReserveConvention implements ObservationConvention<ReserveContext> {
    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof ReserveContext;
    }

    @Override
    public String getName() {
        return "inventory.reserve";
    }

    @Override
    public String getContextualName(ReserveContext context) {
        return "reserve inventory";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(ReserveContext context) {
        return KeyValues.of(
                KeyValue.of("inventory.channel", context.channel()),
                KeyValue.of("inventory.operation", "reserve"));
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(ReserveContext context) {
        return KeyValues.of(
                KeyValue.of("inventory.attempt.id", context.attemptId()));
    }
}
~~~

Convention chỉ hỗ trợ `ReserveContext`. Không thực hiện network call, truy vấn database hoặc xử lý nghiệp vụ bên trong các phương thức convention: convention nên dễ dự đoán và có thể kiểm thử trực tiếp.

## 4. Unit test thuần cho ObservationConvention

Phần này minh họa JUnit 5 và AssertJ. Ví dụ sử dụng Java 17+, tương ứng với nhiều dự án Spring Boot 3.x.

~~~java
package com.example.observability;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.stream.StreamSupport;

import static org.assertj.core.api.Assertions.assertThat;

class ReserveConventionTest {
    private final ReserveConvention convention = new ReserveConvention();

    private static List<KeyValue> values(KeyValues keyValues) {
        return StreamSupport.stream(keyValues.spliterator(), false).toList();
    }

    @Test
    void supportsOnlyReserveContext() {
        assertThat(convention.supportsContext(
                new ReserveContext("web", "attempt-01"))).isTrue();
        assertThat(convention.supportsContext(new Observation.Context())).isFalse();
    }

    @Test
    void keepsStableNames() {
        ReserveContext context = new ReserveContext("batch", "attempt-02");
        assertThat(convention.getName()).isEqualTo("inventory.reserve");
        assertThat(convention.getContextualName(context))
                .isEqualTo("reserve inventory");
    }

    @Test
    void placesKeysInCorrectCardinalityGroup() {
        ReserveContext context = new ReserveContext("web", "attempt-03");

        assertThat(values(convention.getLowCardinalityKeyValues(context)))
                .containsExactlyInAnyOrder(
                        KeyValue.of("inventory.channel", "web"),
                        KeyValue.of("inventory.operation", "reserve"));
        assertThat(values(convention.getHighCardinalityKeyValues(context)))
                .containsExactly(KeyValue.of("inventory.attempt.id", "attempt-03"));
    }
}
~~~

Hai lựa chọn ở test này có ý nghĩa:

1. So sánh **cả tên key và giá trị**; chỉ kiểm tra số phần tử không phát hiện được sai chính tả `inventory.channel` thành `channel`.
2. So sánh cả **hai nhóm low và high**; nếu ID động bị đưa sang low cardinality, test phải thất bại.

Test `supportsContext` dùng `Observation.Context` thông thường để phát hiện lỗi trả về `true` vô điều kiện. Nó không cần dựng toàn bộ ứng dụng Spring Boot.

### 4.1. Kiểm thử giá trị không hợp lệ

Nên có test cho `channel` ngoài `web`/`batch`, `attemptId` rỗng, hoặc dữ liệu vượt quá quy định độ dài khi đã có validator. Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

assertThatThrownBy(() -> new ReserveContext("user-283746", "attempt-04"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("Unsupported channel");
~~~

Chỉ chấp nhận tập giá trị hữu hạn có ý nghĩa vận hành. Không dùng logic `channel = request.getHeader("X-Channel")` rồi truyền thẳng vào metric tags nếu header không được kiểm soát.

## 5. Kiểm thử runtime với TestObservationRegistry

Kiểm tra convention trực tiếp chưa chứng minh instrumentation **thật sự dùng** convention đó. `TestObservationRegistry` từ `micrometer-observation-test` cho phép thực thi Observation và xác minh tên, tags, lifecycle mà không cần Prometheus hoặc OTLP Collector.

Ví dụ một test sử dụng default convention:

~~~java
package com.example.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistryAssert;
import org.junit.jupiter.api.Test;

class ReserveObservationRuntimeTest {

    @Test
    void stopsObservationWithDocumentedMetadata() {
        TestObservationRegistry registry = TestObservationRegistry.create();

        Observation.createNotStarted(
                null,                       // Không truyền custom convention.
                new ReserveConvention(),    // Default convention.
                () -> new ReserveContext("web", "attempt-05"),
                registry)
            .observe(() -> { /* giả lập lần giữ hàng thành công */ });

        TestObservationRegistryAssert.assertThat(registry)
                .hasSingleObservationThat()
                .hasBeenStopped()
                .hasNameEqualTo("inventory.reserve")
                .hasLowCardinalityKeyValue("inventory.channel", "web")
                .hasLowCardinalityKeyValue("inventory.operation", "reserve")
                .hasHighCardinalityKeyValue("inventory.attempt.id", "attempt-05")
                .doesNotHaveError();
    }
}
~~~

Lời gọi `Observation.createNotStarted(custom, default, supplier, registry)` là **factory có xét convention**; đây là điểm quan trọng để kiểm tra hành vi lựa chọn custom/global/default. Sau khi tạo, `observe(...)` bắt đầu Observation, mở scope, chạy lambda, đóng scope và dừng Observation kể cả khi có exception.

Kết quả test chứng minh metadata có trên Observation runtime và đã hoàn tất lifecycle. Nó **không chứng minh** metric đã được ghi vào `MeterRegistry`, một span đã được exporter gửi hay trace đã được backend lưu.

### 5.1. Test đường đi ném lỗi

Khi nghiệp vụ thất bại, hãy xác minh exception **không bị nuốt**, Observation vẫn được dừng và thông tin lỗi được ghi nhận. Mẫu:

~~~java
TestObservationRegistry registry = TestObservationRegistry.create();

assertThatThrownBy(() ->
        Observation.createNotStarted(
                null,
                new ReserveConvention(),
                () -> new ReserveContext("web", "attempt-failed"),
                registry)
            .observe(() -> {
                throw new IllegalStateException("inventory timeout");
            }))
    .isInstanceOf(IllegalStateException.class);

// Tiếp tục dùng TestObservationRegistryAssert để kiểm tra
// Observation đã stop và mang lỗi theo API phiên bản đang dùng.
~~~

Trong đoạn trên, `assertThatThrownBy` được import từ `org.assertj.core.api.Assertions`. Test lỗi cần một hàm assertion phù hợp với phiên bản `micrometer-observation-test` để kiểm tra Throwable và trạng thái kết thúc, tránh phụ thuộc vào chi tiết nội bộ của handler.

## 6. Kiểm thử thứ tự ưu tiên custom, global và default

Một mục tiêu kiểm thử quan trọng là xác định **convention nào thực sự được chọn**. Với API tạo Observation nhận đủ custom, default và context supplier, thứ tự ưu tiên thường là:

1. **Custom convention** truyền vào lời gọi, nếu có.
2. **GlobalObservationConvention** đăng ký trên registry và hỗ trợ context đó.
3. **Default convention** truyền vào factory, nếu không có hai lựa chọn trên.

### 6.1. Tạo convention global cho test

Trong test, có thể dùng một marker low cardinality **có giá trị hữu hạn** để phân biệt convention được chọn. Marker này chỉ phục vụ kiểm thử lựa chọn; không cần thêm vào metric production.

~~~java
package com.example.observability;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.GlobalObservationConvention;

public final class GlobalReserveConvention extends ReserveConvention
        implements GlobalObservationConvention<ReserveContext> {

    @Override
    public KeyValues getLowCardinalityKeyValues(ReserveContext context) {
        return KeyValues.of(
                KeyValue.of("inventory.channel", context.channel()),
                KeyValue.of("convention.source", "global"));
    }
}
~~~

`GlobalReserveConvention` kế thừa `supportsContext` từ `ReserveConvention`, vì vậy vẫn chỉ áp dụng cho `ReserveContext`.

### 6.2. Kiểm tra global được chọn

~~~java
TestObservationRegistry registry = TestObservationRegistry.create();
registry.observationConfig()
        .observationConvention(new GlobalReserveConvention());

Observation.createNotStarted(
        null,
        new ReserveConvention(),
        () -> new ReserveContext("batch", "attempt-global"),
        registry)
    .observe(() -> { });

TestObservationRegistryAssert.assertThat(registry)
        .hasSingleObservationThat()
        .hasBeenStopped()
        .hasLowCardinalityKeyValue("convention.source", "global");
~~~

Nếu bỏ lệnh đăng ký global, factory sẽ dùng `ReserveConvention` (default) và key `convention.source=global` sẽ không còn. Đó là cách kiểm tra **fallback**, không chỉ kiểm tra rằng chương trình chạy không lỗi.

### 6.3. Kiểm tra custom thắng global

Có thể xây dựng một custom convention từ `ReserveConvention` để thêm marker `convention.source=custom`, sau đó truyền instance custom vào tham số đầu của factory. Khi registry có cả global, test kỳ vọng thấy giá trị `custom` và không thấy `global`. Như vậy test thực sự phân biệt thứ tự ưu tiên.

Đặc biệt, **đăng ký global convention không có nghĩa nó áp dụng cho mọi Observation**. Nếu instrumentation tạo Observation bằng chuỗi tên trực tiếp, hoặc đã chọn custom convention chuyên biệt, đường chọn global có thể không được sử dụng. Do đó test phải dùng **đúng factory và loại context** của code thực tế.

Không nên có hai global conventions cùng báo `supportsContext=true` cho một loại context rồi dựa vào thứ tự khởi tạo bean để quyết định quy tắc. Hãy thu hẹp phạm vi và viết test chống chồng lấn.

## 7. Kiểm thử ObservationFilter

`ObservationFilter` không phải `ObservationConvention`. Convention chọn tên và tập key-values từ context; filter có thể chỉnh sửa `Observation.Context` trong lifecycle. Một nhu cầu filter thường gặp là thêm nhãn môi trường ổn định vào những Observation thích hợp, nhưng phải tránh tác động ngoài ý muốn.

Ví dụ ở test:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;

TestObservationRegistry registry = TestObservationRegistry.create();
registry.observationConfig().observationFilter(context -> {
    context.addLowCardinalityKeyValue(
            KeyValue.of("deployment.environment", "test"));
    return context;
});

Observation.createNotStarted("inventory.reserve", registry)
        .lowCardinalityKeyValue("inventory.channel", "web")
        .observe(() -> { });

TestObservationRegistryAssert.assertThat(registry)
        .hasSingleObservationThat()
        .hasBeenStopped()
        .hasLowCardinalityKeyValue("deployment.environment", "test");
~~~

Những điều nên kiểm tra:

- Filter **không làm mất** tag mà convention hoặc instrumentation đã tạo.
- Key chung có cardinality hữu hạn, ví dụ `deployment.environment=staging`.
- Không vô tình thêm ID người dùng, email hoặc request path thô vào low-cardinality tags.
- Không phụ thuộc sai vào thời điểm thực thi: metadata chỉ có ở cuối Observation có thể khác metadata cần ngay lúc start.
- Filter không được giả định mọi context là `ReserveContext`; nếu cần cast thì kiểm tra kiểu trước.

**Chú ý:** các handler có thể đọc metadata ở những thời điểm khác nhau trong vòng đời. Một filter bổ sung key gần lúc kết thúc Observation không bảo đảm mọi thuộc tính sẽ xuất hiện trên span ở ngay thời điểm bắt đầu. Hãy kiểm tra hành vi handler đang dùng, đặc biệt khi thử nghiệm tracing và metrics.

Nếu mục tiêu đơn giản là thêm common tags vào **tất cả metrics**, `MeterRegistry` common tags có thể dễ quản lý hơn. Nếu mục tiêu loại bỏ một Observation không cần đo, hãy xem xét `ObservationPredicate` và viết test rằng các luồng quan trọng không bị bỏ sót.

## 8. Xác minh metric labels bằng SimpleMeterRegistry

`TestObservationRegistry` tập trung vào Observation và metadata; để chứng minh tên/tag thực sự được chuyển thành metrics, có thể sử dụng một registry trong bộ nhớ cùng metrics handler.

~~~java
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import static org.assertj.core.api.Assertions.assertThat;

SimpleMeterRegistry meters = new SimpleMeterRegistry();
ObservationRegistry registry = ObservationRegistry.create();
registry.observationConfig()
        .observationHandler(new DefaultMeterObservationHandler(meters));

Observation.createNotStarted(
        null,
        new ReserveConvention(),
        () -> new ReserveContext("web", "attempt-not-a-metric-label"),
        registry)
    .observe(() -> { });

Timer timer = meters.find("inventory.reserve")
        .tag("inventory.channel", "web")
        .timer();

assertThat(timer).isNotNull();
assertThat(timer.count()).isEqualTo(1);
assertThat(timer.getId().getTag("inventory.attempt.id")).isNull();
~~~

Ví dụ sử dụng các lớp Micrometer tương ứng với phiên bản dependency đã chọn. Test kiểm tra:

1. Handler đã ghi một lần Observation vào Timer với tên đúng.
2. Nhãn low-cardinality được tạo đúng.
3. `inventory.attempt.id` thuộc nhóm high cardinality, **không xuất hiện** trong `Meter.Id` của timer.

Một số instrumentation có thể bổ sung nhãn khác hoặc xuất tên đã chuyển đổi theo naming convention của backend; test này kiểm tra `SimpleMeterRegistry` trong bộ nhớ, không phải tên series Prometheus sau export.

Không nên kiểm tra chính xác thời gian tính bằng vài nanosecond: thời gian chạy thực phụ thuộc máy và scheduler. Có thể kiểm tra Timer tồn tại, count chính xác, thời gian không âm; chỉ đưa time assertions với ngưỡng rộng khi thật sự cần chứng minh hành vi thời gian.

## 9. Kiểm thử trong ứng dụng Spring Boot

Đối với một dự án dùng Spring Boot 3.x với Micrometer, những dependency Gradle phổ biến gồm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    // Chỉ cần nếu hệ thống sử dụng OpenTelemetry tracing:
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.micrometer:micrometer-observation-test'
}
~~~

Phiên bản cụ thể nên theo dependency management/BOM của dự án. Với `@SpringBootTest` hoặc một integration test phù hợp, hãy inject **chính bean `ObservationRegistry` được ứng dụng sử dụng** để xác minh:

1. Bean `ObservationConvention` hoặc `GlobalObservationConvention` đã được đăng ký qua auto-configuration đúng như thiết kế.
2. Service không vô tình tạo một `ObservationRegistry.create()` riêng thiếu handler/filter của ứng dụng.
3. Instrumentation ở controller/service dùng đúng context, đúng convention và tên ổn định.
4. Filter đã được đăng ký, không nhân đôi tags hoặc thay thế metadata bất ngờ.
5. Khi kết hợp tracing, logs có trace ID/span ID ở những đường đi được ghi nhận.

Không khẳng định một bean global được sử dụng cho mọi HTTP request: các HTTP server/client integrations của Spring có thể dùng convention chuyên biệt và custom convention được ưu tiên. Với HTTP, nên dùng interface convention phù hợp của instrumentation thay vì cast nhầm mọi context về một kiểu nghiệp vụ.

### 9.1. Kiểm thử qua exporter và backend

Vòng kiểm thử rộng hơn cần một pipeline telemetry giống môi trường thật:

~~~mermaid
flowchart LR
    A["Spring Boot + ObservationRegistry"] --> B["Metrics handler"]
    A --> C["Tracing handler"]
    A --> D["Logs + correlation"]
    B --> E["Prometheus / backend metrics"]
    C --> F["OTLP exporter / Collector"]
    F --> G["Trace backend"]
    D --> H["Log backend"]
    G -. "trace ID" .-> H
~~~

Trong staging, có thể tạo request chứa đường đi thành công và timeout giả lập, rồi xác minh:

- Metrics của `inventory.reserve` được lưu, tổng hợp theo `inventory.channel` và không có `inventory.attempt.id` trong label.
- Span tương ứng xuất hiện trong trace khi được sampling giữ; có contextual name và attributes phù hợp.
- Trace từ `order-service` đến `inventory-service` có quan hệ parent/child hợp lý khi HTTP client và downstream được instrument.
- Logs có trace ID giúp tìm bản ghi thời gian timeout; không có dữ liệu nhạy cảm.
- Collector/exporter không báo lỗi hoặc bỏ dữ liệu một cách im lặng.

Điểm cần tách bạch: **unit test convention thành công không có nghĩa exporter hoạt động**; có trace ID trong logs cũng không đồng nghĩa trace đã được lưu ở backend.

### 9.2. Ảnh hưởng của sampling và context propagation

Nếu sampler lấy 10% trace, một request cụ thể có thể không có trace trong backend dù Observation được tạo và metrics đã được ghi. Test xác minh trace nên dùng cấu hình sampling thích hợp với môi trường kiểm thử và hiểu giới hạn của head/tail sampling.

Khi chuyển qua `@Async`, executor, Reactor, messaging hoặc một HTTP client không được instrument, context có thể bị mất. Một convention đúng tên và tags vẫn không tự sửa được lỗi propagation. Hãy test đường đi qua ranh giới đó, kiểm tra W3C `traceparent` và cơ chế truyền ngữ cảnh tương ứng với phiên bản Spring.

## 10. Kiểm thử thay đổi hợp đồng và cardinality

Giả sử có 3 vùng, 2 channel, 4 outcome và 100 instance. Một metric có thể có tới **3 × 2 × 4 × 100 = 2.400** tổ hợp series trước khi tính các nhãn khác. Nếu ai đó thêm `orderId` với hàng trăm nghìn giá trị vào low-cardinality tags, số series có thể tăng cùng số request.

Vì vậy, khi review thay đổi convention, nên kiểm tra:

| Loại thay đổi | Rủi ro | Kiểm thử hoặc biện pháp |
| --- | --- | --- |
| Đổi tên `inventory.reserve` | Dashboard/alert không truy vấn được tên cũ | Contract test tên, kiểm tra truy vấn đã sử dụng |
| Đổi `inventory.channel` thành `channel` | Dashboard tách dữ liệu thành các schema khác | Contract test key, kế hoạch chuyển đổi |
| Thêm `inventory.region` | Tăng số tổ hợp time series | Giới hạn giá trị, ước lượng cardinality |
| Thêm `orderId` vào low cardinality | Bùng nổ series, có thể lộ dữ liệu | Test tag không chứa ID động, chặn ở review |
| Chuyển `attempt.id` từ high sang low | Suy giảm hiệu năng metrics | Test tách riêng tập low/high |
| Thay `supportsContext` thành `true` | Global convention áp dụng nhầm | Test context không hỗ trợ |
| Thêm filter chung | Trùng key hoặc ghi đè metadata | Test trước/sau filter |
| Đổi phiên bản Spring/Micrometer | Factory và auto-configuration có thể thay đổi | Chạy lại unit + integration tests liên quan |

**Không có một phép đo tổng cardinality tự động đáng tin cậy chỉ từ test Java**, vì các nhãn backend và tập giá trị thực tế có thể khác. Test nên bảo vệ những ràng buộc có thể kiểm tra sớm; còn khả năng mở rộng cần đánh giá với traffic, registry và dashboard thực.

### 10.1. Có cần snapshot toàn bộ tên tag không?

Snapshot có thể hữu ích khi hợp đồng ổn định và số key nhỏ, nhưng snapshot quá lớn hoặc phụ thuộc thứ tự không quan trọng sẽ dễ vỡ. Với convention, thường tốt hơn khi viết assertion **cụ thể theo giá trị và tập key có nghĩa**. Ví dụ test nhóm low/high riêng, dùng `containsExactlyInAnyOrder` để tránh lỗi chỉ do thứ tự nội bộ của `KeyValues`.

## 11. Quy trình điều tra khi test thất bại

| Triệu chứng | Câu hỏi cần kiểm tra | Hướng khắc phục |
| --- | --- | --- |
| `getName` đổi bất ngờ | Có sửa convention hoặc rename thao tác không? | Xác nhận thay đổi hợp đồng và cập nhật dashboard có chủ đích |
| Global convention không được chọn | Factory có custom khác `null`? `supportsContext` trả gì? | Dùng đúng factory/context, tránh chồng lấn |
| Unit test pass nhưng TestObservationRegistry fail | Instrumentation có tạo Observation bằng tên chuỗi không? | Kiểm tra đường tạo và đăng ký registry |
| Low/high keys bị lẫn | Key được trả từ method nào? | Chuyển ID động về high hoặc bỏ |
| Filter làm mất tag | Filter có sửa context theo cách ngoài ý muốn? | Thu hẹp điều kiện áp dụng, thêm test âm |
| Có Observation nhưng không có Timer | Metrics handler/MeterRegistry đã đăng ký chưa? | Kiểm tra handler và thời điểm stop |
| Có Timer nhưng không thấy trên Prometheus | Endpoint, registry hoặc scrape/exporter lỗi? | Kiểm tra pipeline metrics riêng |
| Có metrics nhưng không có trace | Sampler, bridge, propagation, exporter, backend? | Kiểm tra lần lượt, không kết luận do convention |
| Trace bị tách qua async/service | Context đã được truyền chưa? | Kiểm tra HTTP client, `traceparent`, executor |
| Logs không liên kết trace | MDC/correlation layout có được cấu hình không? | Kiểm tra logging và scope |

Khi test runtime thất bại, ưu tiên quan sát **đường tạo Observation** và **registry đang được dùng** trước khi sửa exporter. Khi backend thiếu dữ liệu, phân biệt giữa không instrument, no-op predicate, sampling không giữ, propagation bị mất và pipeline telemetry bị gián đoạn.

## 12. Checklist cho pull request thay đổi convention

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Tên và contextual name rõ ràng | Unit test với chuỗi tên kỳ vọng |
| Phạm vi context được hỗ trợ đúng | Test positive và negative cho `supportsContext` |
| Low-cardinality keys ổn định | Assert cả tên/giá trị, danh sách hữu hạn |
| High-cardinality keys được tách rõ | Test không lẫn ID vào low cardinality |
| Dữ liệu nhạy cảm được loại bỏ | Validator/review/test cho metadata nguy cơ cao |
| Custom/global/default ưu tiên như kỳ vọng | Runtime test phân biệt marker convention |
| Filters không làm hỏng context | Test metadata trước và sau khi filter |
| Observation hoàn tất lifecycle | `hasBeenStopped` và test lỗi |
| Metrics handler tạo Timer phù hợp | `SimpleMeterRegistry` test |
| Tích hợp Spring Boot chính xác | Integration test dùng registry được inject |
| Traces/logs/propagation được kiểm chứng | Staging test cho hành trình qua service/async |
| Dashboard và alert được cập nhật | Kế hoạch chuyển đổi tên/tag khi cần |

## 13. Bài thực hành: kiểm thử convention của inventory-service

**Bối cảnh:** đội phát triển Spring Boot vừa tạo `ReserveConvention` để instrument hai nguồn gọi `web` và `batch`. Một thành viên muốn thêm `inventory.order.id` vào metric tags để tìm request lỗi nhanh hơn; một thành viên khác đề xuất thay default convention bằng global để áp dụng cho mọi lần giữ hàng.

**Nhiệm vụ:**

1. Xây dựng `ReserveContext` và `ReserveConvention` theo ví dụ, định nghĩa rõ tên và bộ low/high keys.
2. Viết unit test cho `supportsContext`, `getName`, contextual name và cả hai nhóm `KeyValues`.
3. Dùng `TestObservationRegistry` tạo hai Observation (thành công và ném exception), xác minh lifecycle và metadata.
4. Đăng ký `GlobalReserveConvention`, test rằng global được chọn khi không có custom và hỗ trợ context; sau đó test custom được ưu tiên.
5. Thêm một `ObservationFilter` bổ sung `deployment.environment=test` và kiểm tra tag này không làm mất `inventory.channel`.
6. Dùng `SimpleMeterRegistry` để chứng minh `inventory.attempt.id` không xuất hiện trong metric labels.
7. Đề xuất cách tương quan request lỗi mà không đưa `inventory.order.id` vào low-cardinality tags.
8. Ở môi trường thử nghiệm có tracing, xác minh một trace nối `order-service` đến `inventory-service`; giải thích vì sao một request bị sampling bỏ qua không có trace trong backend.
9. Viết một đoạn hướng dẫn migration nếu đổi tên tag `inventory.channel` thành `channel`, bao gồm dashboard, alert và dữ liệu lịch sử.

**Kết quả mong đợi:** một bộ test bảo vệ hợp đồng tên/tag, test thể hiện thứ tự ưu tiên convention, minh chứng metrics không có ID động, cùng ghi chú về trace, exporter, sampling và cách xử lý trường hợp mất propagation.

## 14. Ghi nhớ

Kiểm thử `ObservationConvention` nên đi từ **hợp đồng thuần** tới **đường chạy thực tế**. Unit test bảo vệ tên và phân loại key; `TestObservationRegistry` chứng minh convention đã được áp dụng và Observation dừng đúng; `SimpleMeterRegistry` xác minh metadata phục vụ metrics; integration test và thử nghiệm backend kiểm chứng Spring Boot auto-configuration, tracing, exporter, logs và propagation.

Convention và filter đúng giúp dữ liệu quan sát nhất quán, nhưng chỉ khi kết hợp với **sampling được hiểu rõ, cardinality được kiểm soát, pipeline exporter hoạt động và khả năng tương quan metrics–logs–traces** thì nhóm vận hành mới có thể điều tra lỗi và độ trễ đáng tin cậy.

**Tài liệu tham khảo:**

- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer — Testing Observations](https://docs.micrometer.io/micrometer/reference/observation/testing.html)
- [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
