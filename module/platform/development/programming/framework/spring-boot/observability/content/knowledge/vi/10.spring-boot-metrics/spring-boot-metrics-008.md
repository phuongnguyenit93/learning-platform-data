# Binders trong Spring Boot Metrics: từ MeterRegistry đến tín hiệu vận hành

Khi một ứng dụng Spring Boot chạy trên production, nhóm vận hành cần biết JVM sử dụng bao nhiêu bộ nhớ, CPU có bị quá tải không, hàng đợi có đang tích tụ công việc và connection pool còn đủ kết nối hay không. Nhiều số liệu trong đó không gắn trực tiếp với một HTTP request. Chúng mô tả **trạng thái hoặc hoạt động của một thành phần** và cần được đăng ký với hệ thống metrics trước khi có thể thu thập.

Trong Micrometer, **`MeterBinder`** là cơ chế đóng gói việc đăng ký một hoặc nhiều `Meter` vào `MeterRegistry`. Spring Boot có thể tự cấu hình nhiều binder cho JVM và môi trường chạy, đồng thời cho phép ứng dụng định nghĩa binder riêng cho dữ liệu nghiệp vụ. Nhờ đó, cùng một hợp đồng metrics có thể được áp dụng vào registry mà ứng dụng đang sử dụng.

Bài thuộc chương **Spring Boot metrics** của module **SPRING_BOOT_OBSERVABILITY**, với mục tiêu thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Chúng ta sẽ tìm hiểu binder từ nguyên lý đến code, tags/cardinality, exporter và cách sử dụng chung với tracing, sampling và context propagation để điều tra lỗi hoặc độ trễ trong môi trường thực.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `MeterBinder` là gì, khi nào được gọi và khác `Meter` hoặc `MeterRegistry` ra sao.
2. Nhận biết các nhóm metrics có thể được binder mặc định của Spring Boot/Micrometer cung cấp và điều kiện để chúng xuất hiện.
3. Tạo một custom `MeterBinder` đăng ký gauge đo độ sâu hàng đợi nghiệp vụ.
4. Đăng ký binder như Spring bean hoặc gọi `bindTo` khi tự quản lý registry.
5. Xác minh meter qua `/actuator/metrics`, `/actuator/prometheus` và `SimpleMeterRegistry` trong test.
6. Kiểm soát labels, cardinality, vòng đời đối tượng được quan sát và chi phí thu thập.
7. Phân biệt metrics từ binders với metrics từ Observation và việc tương quan metrics, logs, traces.

## 1. Ba khái niệm nền tảng: Meter, MeterRegistry và MeterBinder

**`Meter`** là đơn vị đo trong Micrometer. Ví dụ `Counter` đếm sự kiện tăng dần, `Timer` ghi số lần và thời gian hoàn tất thao tác, còn `Gauge` đọc giá trị hiện tại của một đối tượng hoặc đại lượng. Các loại meter thường gặp gồm:

| Meter | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `Counter` | Tổng số sự kiện tăng dần | Số job đã được xử lý |
| `Gauge` | Giá trị hiện tại tại thời điểm đọc | Số công việc chờ trong hàng đợi |
| `Timer` | Số lần và phân bố thời gian của thao tác hoàn tất | Thời gian gọi inventory-service |
| `DistributionSummary` | Phân bố một đại lượng số không phải thời gian | Kích thước payload, số sản phẩm trong đơn |
| `LongTaskTimer` | Theo dõi những công việc đang chạy kéo dài | Số batch job lâu và thời gian chúng đang chạy |

**`MeterRegistry`** là nơi đăng ký và quản lý các meter. Registry cụ thể quyết định cách dữ liệu được biểu diễn và xuất ra. Chẳng hạn:

- `SimpleMeterRegistry`: lưu meters trong bộ nhớ, hữu ích cho kiểm thử.
- `PrometheusMeterRegistry`: cung cấp dữ liệu theo định dạng Prometheus để hệ thống thu thập bằng scrape.
- Registry/exporter khác: có thể gửi dữ liệu sang hệ thống giám sát tương ứng, tùy thư viện và cấu hình.

**`MeterBinder`** là interface có phương thức cốt lõi:

~~~java
package io.micrometer.core.instrument.binder;

import io.micrometer.core.instrument.MeterRegistry;

@FunctionalInterface
public interface MeterBinder {
    void bindTo(MeterRegistry registry);
}
~~~

Đoạn trên minh họa chữ ký API, **không cần chép interface của thư viện vào dự án**. Khi gọi `bindTo(registry)`, binder đăng ký các meter tương ứng. Sau đó meter được cập nhật hoặc được đọc theo cơ chế riêng: một gauge có thể lấy trạng thái hiện tại khi registry được scrape; timer/counter cần có sự kiện ghi nhận trong lúc ứng dụng chạy.

### 1.1. Binder làm gì và không làm gì?

~~~mermaid
flowchart TD
    App["Spring Boot application"] --> Binder["MeterBinder: đăng ký meters"]
    Binder --> Registry["MeterRegistry"]
    Runtime["JVM / CPU / pool / queue"] --> Meters["Counter, Gauge, Timer..."]
    Registry --> Meters
    Meters --> Export["Prometheus scrape hoặc metrics exporter"]
    Export --> Backend["Metrics backend / Grafana"]
    App --> Observation["Micrometer Observation"]
    Observation --> Handler["MeterObservationHandler"]
    Handler --> Registry
    Observation --> Tracing["Tracing handler / spans"]
~~~

Binder **định nghĩa cách đăng ký meter**, không mặc nhiên gửi HTTP request đến backend, không tạo distributed trace, không sinh log và không chuyển trace context sang một thread khác. Một `MeterBinder` có thể đăng ký cùng loại meter với code trực tiếp sử dụng `MeterRegistry`; lợi ích là đóng gói và tái sử dụng phần thiết lập.

Một tên dễ nhầm là **`MeterObservationHandler`**. Handler này phản ứng với vòng đời của `Observation` để ghi metrics, còn `MeterBinder` đăng ký các meter cho một đối tượng/hệ thống. Hai cơ chế có thể cùng tồn tại và cùng ghi dữ liệu vào một `MeterRegistry` nhưng không phải một API.

## 2. Vòng đời bindTo và cách dữ liệu được cập nhật

Hãy xét binder đo độ sâu hàng đợi:

1. Ứng dụng khởi tạo đối tượng hàng đợi và `MeterRegistry`.
2. Binder được tạo, sau đó `bindTo(registry)` đăng ký một `Gauge` gắn với đối tượng hàng đợi.
3. Khi số công việc chờ thay đổi, **đối tượng hàng đợi** giữ giá trị mới.
4. Lúc hệ thống metrics đọc gauge, callback cung cấp giá trị hiện tại.
5. Registry/exporter làm dữ liệu có thể được truy vấn tại backend.

~~~mermaid
sequenceDiagram
    participant Boot as Spring Boot
    participant Binder as QueueMeterBinder
    participant Registry as MeterRegistry
    participant Queue as Business queue
    participant Prom as Prometheus
    Boot->>Binder: Tạo bean
    Boot->>Registry: Áp dụng binder vào registry
    Registry->>Binder: bindTo(registry)
    Binder->>Registry: Gauge.builder(...).register(...)
    Queue->>Queue: Độ sâu thay đổi theo công việc
    Prom->>Registry: Scrape tại /actuator/prometheus
    Registry->>Queue: Đọc queue.size()
    Queue-->>Registry: Số công việc hiện tại
    Registry-->>Prom: Metric và tags
~~~

Điểm quan trọng: **Gauge là phép đo trạng thái tức thời**. Nếu hàng đợi tăng lên 1.000 rồi giảm về 0 giữa hai lần scrape, backend có thể không nhìn thấy đỉnh tăng đó. Nếu cần biết *số công việc đã xử lý trong một khoảng*, dùng counter được tăng theo sự kiện; nếu cần thời gian xử lý, dùng timer. Đừng cố biến Gauge thành bộ đếm tích lũy.

### 2.1. Có nên gọi bindTo nhiều lần?

Thông thường binder chỉ cần được áp dụng **một lần trên mỗi registry**. Spring Boot tự áp dụng các bean `MeterBinder` phù hợp cho những registry do nó quản lý. Nếu đã khai báo binder như bean, đừng đồng thời gọi thủ công `binder.bindTo(registry)` trên cùng registry nếu không có lý do rõ ràng; đăng ký lặp có thể dẫn tới cấu hình trùng, cảnh báo hoặc khó giải thích giá trị.

Nếu dùng nhiều registry độc lập, binder có thể được áp dụng vào từng registry. Cần bảo đảm meter name/tags và chi phí thu thập ở mỗi đích được kiểm soát.

## 3. Các binder và metrics có sẵn trong Spring Boot

Khi thêm `spring-boot-starter-actuator`, Spring Boot có thể tự cấu hình nhiều nhóm metrics nếu điều kiện về lớp thư viện, bean và môi trường thực thi được thỏa mãn. Một phần sử dụng các **binder Micrometer có sẵn**; phần khác đến từ instrumentation hoặc tích hợp chuyên biệt.

| Nhóm tín hiệu | Ví dụ meter thường thấy | Điều kiện hoặc nguồn đo |
| --- | --- | --- |
| **JVM memory** | `jvm.memory.used`, `jvm.memory.committed`, `jvm.memory.max` | JVM memory binder |
| **GC** | `jvm.gc.pause` và các số liệu GC liên quan | JVM GC binder, tùy collector/JDK |
| **Threads** | `jvm.threads.live`, `jvm.threads.daemon` | JVM thread binder |
| **Classes** | `jvm.classes.loaded` | Class loader binder |
| **Process / CPU** | `process.cpu.usage`, `process.uptime`, `system.cpu.usage` | Process/system binder, tùy nền tảng |
| **Disk space** | `disk.free`, `disk.total` | Disk space binder, phụ thuộc đường dẫn đo |
| **Connection pool** | Ví dụ `hikaricp.connections.active` | Có DataSource/HikariCP và tích hợp metrics phù hợp |
| **Cache** | Ví dụ `cache.gets`, `cache.puts` | Có cache manager/provider được hỗ trợ, đôi khi cần bật thống kê |
| **HTTP server** | `http.server.requests` | Thường do HTTP instrumentation / Micrometer Observation, không nên đồng nhất với JVM binder |

Danh sách trên là **ví dụ**, không phải cam kết tất cả xuất hiện trong mọi ứng dụng. Tên meter và kiểu dữ liệu còn phụ thuộc Spring Boot, Micrometer, JDK, runtime, provider và naming convention của registry. Khi thiếu một meter, phải kiểm tra thành phần đó có tồn tại và được instrument hay không.

### 3.1. Thử các binder Micrometer trực tiếp

Đoạn sau minh họa cách dùng một số binder có sẵn ngoài Spring Boot auto-configuration:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.jvm.JvmMemoryMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmThreadMetrics;
import io.micrometer.core.instrument.binder.system.ProcessorMetrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

try (MeterRegistry registry = new SimpleMeterRegistry()) {
    new JvmMemoryMetrics().bindTo(registry);
    new JvmThreadMetrics().bindTo(registry);
    new ProcessorMetrics().bindTo(registry);

    // Registry hiện có JVM/process-related meters tương ứng.
    registry.getMeters().forEach(meter ->
            System.out.println(meter.getId().getName()));
}
~~~

Code dùng registry độc lập để minh họa binder. **Trong ứng dụng Spring Boot thật**, nếu các binder tương ứng đã được auto-configure, không cần đăng ký lại theo cách này. Một số meter có thể không có giá trị hoặc không khả dụng trên một JVM/OS/container cụ thể.

### 3.2. Phân biệt metric hạ tầng và tín hiệu ảnh hưởng người dùng

Khi `jvm.memory.used` tăng, ứng dụng chưa chắc đã lỗi; khi `process.cpu.usage` cao, người dùng chưa chắc bị chậm. Những metrics này giải thích tình trạng tài nguyên và **hỗ trợ điều tra nguyên nhân**, nhưng thường không nên là SLI duy nhất.

Một dịch vụ tạo đơn nên kết hợp:

- **Tín hiệu người dùng**: HTTP 5xx, tỷ lệ hoàn tất đơn, request duration p95/p99.
- **Tín hiệu phụ thuộc**: thời gian gọi inventory-service, số timeout, retry.
- **Tín hiệu tài nguyên**: JVM memory, GC pause, CPU, connection pool, hàng đợi.

Nhờ đó, khi request chậm, đội vận hành có thể xem mức sử dụng tài nguyên có cùng tăng với độ trễ không.

## 4. Tạo custom MeterBinder đo hàng đợi nghiệp vụ

Ví dụ ứng dụng nhận yêu cầu tạo đơn, sau đó đưa công việc sang hàng đợi xử lý nền. Chúng ta muốn theo dõi **số đơn đang chờ xử lý ở thời điểm hiện tại**.

Chọn hợp đồng:

| Thành phần | Giá trị |
| --- | --- |
| Tên meter | `orders.queue.pending` |
| Loại meter | `Gauge` |
| Đơn vị cơ sở | `tasks` |
| Tag có tập giá trị hữu hạn | `queue=orders` |
| Dữ liệu đọc | Số tác vụ chờ trong một queue do ứng dụng quản lý |

### 4.1. Định nghĩa đối tượng được quan sát

Trong `PendingOrderQueue.java`:

~~~java
package com.example.orders.metrics;

public interface PendingOrderQueue {
    int size();
}
~~~

Interface này là API minh họa. Ứng dụng cần cung cấp bean triển khai thật, ví dụ adapter đọc kích thước của hàng đợi trong bộ nhớ. Nếu hàng đợi đặt ở hệ thống bên ngoài, việc truy vấn kích thước qua mạng có thể chậm hoặc thất bại; nên thiết kế nguồn dữ liệu sẵn có, rẻ để đọc và biết rõ độ mới của giá trị.

### 4.2. Viết binder

Trong `PendingOrderQueueMeterBinder.java`:

~~~java
package com.example.orders.metrics;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;

import java.util.Objects;

public final class PendingOrderQueueMeterBinder implements MeterBinder {
    private final PendingOrderQueue queue;

    public PendingOrderQueueMeterBinder(PendingOrderQueue queue) {
        this.queue = Objects.requireNonNull(queue);
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder("orders.queue.pending", queue, PendingOrderQueue::size)
                .description("Number of orders currently waiting in the queue")
                .baseUnit("tasks")
                .tag("queue", "orders")
                .register(registry);
    }
}
~~~

`Gauge.builder(name, object, function)` dùng callback để đọc giá trị từ `queue` khi registry cần. `baseUnit("tasks")` diễn đạt đại lượng đang đo, không biến nó thành counter. Trong backend Prometheus, tên xuất ra có thể nhận suffix đơn vị (chẳng hạn `_tasks`), vì thế hãy kiểm tra kết quả xuất thật trước khi viết PromQL.

**Vấn đề vòng đời:** Micrometer thường chỉ giữ **weak reference** tới đối tượng được Gauge theo dõi. Nếu đối tượng `queue` không còn được ứng dụng giữ tham chiếu mạnh, Gauge có thể mất nguồn đọc hoặc trả giá trị không hợp lệ. Ở ví dụ này, `PendingOrderQueueMeterBinder` giữ tham chiếu tới queue, và bean queue của ứng dụng cũng phải có vòng đời phù hợp. Không tạo một đối tượng tạm trong `Gauge.builder` rồi để nó bị thu gom rác.

### 4.3. Đăng ký binder dưới dạng Spring bean

Trong `MetricsConfiguration.java`:

~~~java
package com.example.orders.metrics;

import io.micrometer.core.instrument.binder.MeterBinder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsConfiguration {

    @Bean
    MeterBinder pendingOrderQueueMeterBinder(PendingOrderQueue queue) {
        return new PendingOrderQueueMeterBinder(queue);
    }
}
~~~

Với **Spring Boot 3.x có metrics auto-configuration**, bean loại `MeterBinder` được áp dụng vào `MeterRegistry` do ứng dụng quản lý. `PendingOrderQueue` phải là bean thật để Spring inject. Khi không dùng Spring Boot auto-configuration hoặc tự quản lý một registry khác, bạn có thể đăng ký thủ công:

~~~java
MeterRegistry registry = /* registry do ứng dụng cung cấp */;
PendingOrderQueue queue = /* thành phần đang sống của ứng dụng */;

new PendingOrderQueueMeterBinder(queue).bindTo(registry);
~~~

Đoạn mã này minh họa cách gọi thủ công, không phải hướng dẫn tạo thêm một `MeterRegistry` mới bên trong service. Trong ứng dụng Spring Boot, hãy ưu tiên inject registry đã được cấu hình chung để các exporter, common tags và filters hoạt động nhất quán.

### 4.4. Vì sao không gọi size() để set giá trị Gauge bằng tay?

Gauge là phép đo trạng thái, nên bạn **đăng ký một callback** để đọc giá trị. Khi hàng đợi tăng từ 3 lên 7 rồi giảm xuống 2, callback sẽ trả về giá trị hiện tại tại thời điểm scrape. Không có khái niệm `gauge.increment()` để đếm tổng số đơn đã xử lý trong mô hình này.

Nếu cần đếm tổng số tác vụ thành công/thất bại, hãy sử dụng `Counter` ở nơi xử lý sự kiện; nếu cần độ trễ, dùng `Timer` hoặc một `Observation` phù hợp. Binder có thể đăng ký các meter đó, nhưng việc ghi sự kiện đúng lúc vẫn là trách nhiệm của code instrument.

## 5. Cấu hình Spring Boot Actuator và exporter metrics

Các dependency cơ bản khi dùng Spring Boot có hỗ trợ Micrometer và Prometheus:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Một cấu hình minh họa trong `application.yml`:

~~~yaml
spring:
  application:
    name: order-service

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"
  metrics:
    tags:
      application: order-service
~~~

Khi ứng dụng đã chạy và endpoint được truy cập từ mạng được phép, có thể xem:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/orders.queue.pending
curl -s http://localhost:8080/actuator/prometheus
~~~

Ý nghĩa:

- **`/actuator/metrics`** liệt kê tên meter được Actuator nhìn thấy. Endpoint `/actuator/metrics/orders.queue.pending` trả thông tin tổng hợp và các measurement/tag liên quan theo định dạng Actuator.
- **`/actuator/prometheus`** phơi bày định dạng metrics để Prometheus scrape; nó chỉ có nếu registry Prometheus và endpoint exposure phù hợp.
- **`management.metrics.tags.application`** bổ sung một common tag có tập giá trị nhỏ; đừng dùng giá trị động như request ID.

Tên meter ở endpoint Actuator (ví dụ `orders.queue.pending`) **khác** với tên series có thể được chuẩn hóa ở Prometheus (ví dụ chuyển dấu chấm thành gạch dưới và thêm suffix đơn vị). Tên thực tế còn tùy registry và version; không nên đoán tên series khi viết dashboard.

**Bảo mật:** endpoint metrics/prometheus có thể để lộ tên dịch vụ, instance, hostname, trạng thái tài nguyên và nhãn vận hành. Trong production, cần giới hạn quyền truy cập hoặc dùng mạng quản trị phù hợp; không công khai endpoint chỉ để tiện scrape.

### 5.1. Registry và exporter là hai vấn đề riêng

Một meter được đăng ký thành công **chưa chứng minh** backend đã nhận dữ liệu. Ví dụ:

1. `MeterBinder` đã gắn `Gauge` vào `MeterRegistry`.
2. `/actuator/metrics` có thể nhìn thấy meter.
3. `/actuator/prometheus` có thể xuất series.
4. Prometheus server cần scrape endpoint đúng đích, đúng thời điểm.
5. Backend/dashboard cần có truy vấn, label và thời gian lưu đúng.

Nếu dùng cơ chế xuất metrics khác (chẳng hạn push qua OTLP), cần registry/exporter chuyên biệt theo phiên bản Spring Boot và Micrometer. Không nhầm **OTLP metrics exporter** với **OTLP tracing exporter**: chúng có pipeline và đích nhận dữ liệu có thể khác nhau.

## 6. Kiểm thử custom MeterBinder

Không cần khởi động Spring Boot hay Prometheus để kiểm tra binder có đăng ký Gauge đúng tên/tag và đọc đúng giá trị. `SimpleMeterRegistry` là lựa chọn gọn cho unit test.

### 6.1. Unit test sử dụng SimpleMeterRegistry

~~~java
package com.example.orders.metrics;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class PendingOrderQueueMeterBinderTest {

    @Test
    void gaugeReflectsCurrentQueueDepth() {
        AtomicInteger pending = new AtomicInteger(3);
        PendingOrderQueue queue = pending::get;

        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            new PendingOrderQueueMeterBinder(queue).bindTo(registry);

            Gauge gauge = registry.find("orders.queue.pending")
                    .tag("queue", "orders")
                    .gauge();

            assertNotNull(gauge);
            assertEquals(3.0, gauge.value(), 0.001);

            pending.set(7);
            assertEquals(7.0, gauge.value(), 0.001);

            pending.set(2);
            assertEquals(2.0, gauge.value(), 0.001);
        }
    }
}
~~~

Test bảo vệ hai yêu cầu quan trọng: Gauge đã đăng ký đúng tên/tag và callback lấy **giá trị hiện tại**, không giữ một giá trị được chụp duy nhất tại lúc đăng ký.

Nó không chứng minh tên metric Prometheus đã được chuẩn hóa chính xác, exporter hoạt động hay Spring Boot đã áp dụng bean `MeterBinder`. Vì vậy, với ứng dụng thực tế cần thêm kiểm thử tích hợp ở ranh giới thích hợp.

### 6.2. Kiểm thử tích hợp Spring Boot

Một kịch bản `@SpringBootTest` hoặc integration test có cấu hình tối thiểu nên xác minh:

1. `PendingOrderQueue` là bean và `MeterBinder` được auto-configuration nhận diện.
2. `MeterRegistry` inject vào service/Actuator là registry mà binder đã đăng ký vào.
3. Meter `orders.queue.pending` có mặt và thay đổi theo trạng thái hàng đợi thử nghiệm.
4. Có một tập tags hữu hạn; không xuất hiện order ID, user ID, trace ID trong labels.
5. Khi Prometheus registry được cấu hình, kết quả scrape thể hiện gauge với đơn vị và tên series đúng kỳ vọng.

Không cần viết integration test lặp lại tất cả assertion của unit test. Mục đích của test tích hợp là xác minh **mối nối Spring Boot ↔ bean binder ↔ registry ↔ exporter**, vốn không có trong unit test độc lập.

## 7. Đọc và sử dụng metrics từ binders trong dashboard

Với các binder mặc định, dashboard có thể cung cấp bối cảnh để điều tra chậm hoặc lỗi:

| Dashboard | Tín hiệu nên có | Câu hỏi |
| --- | --- | --- |
| JVM | Heap used, GC pause, thread count | Ứng dụng có chịu áp lực bộ nhớ hoặc GC không? |
| Process | CPU usage, uptime | CPU có tăng cùng độ trễ không? Có restart gần đây không? |
| Connection pool | Active, idle, pending connections nếu provider hỗ trợ | Request có bị chờ kết nối không? |
| Queue | Current pending tasks, retry count, age of oldest task | Backlog có đang tăng và xử lý kịp không? |
| HTTP/Business | Request rate, lỗi 5xx, p95/p99, số lần thành công | Người dùng bị ảnh hưởng tới mức nào? |

Các truy vấn PromQL sau là ví dụ; tên series thật phải được lấy từ `/actuator/prometheus` hoặc backend đang dùng.

### 7.1. Bộ nhớ heap đã sử dụng theo instance

~~~promql
sum by (instance) (
  jvm_memory_used_bytes{area="heap",application="order-service"}
)
~~~

Đây thường là **gauge** và kết quả có đơn vị byte. Không dùng `rate(...)` cho lượng heap đang sử dụng như thể nó là counter; nếu muốn xem xu hướng tăng giảm, dùng biểu đồ theo thời gian hoặc hàm phù hợp với gauge.

### 7.2. CPU sử dụng trung bình trong 5 phút

~~~promql
avg_over_time(
  process_cpu_usage{application="order-service"}[5m]
)
~~~

`process_cpu_usage` thường biểu diễn một tỷ lệ (0 đến 1 trong cách đo thông thường của meter), không phải số lần tích lũy. Không dùng `rate(process_cpu_usage[5m])` để suy ra mức CPU sử dụng. Cách metric được cung cấp phụ thuộc runtime và binder; cần kiểm tra giá trị cụ thể.

### 7.3. Backlog hiện tại của queue

Giả sử tên series sau khi xuất sang Prometheus là `orders_queue_pending_tasks`:

~~~promql
orders_queue_pending_tasks{application="order-service",queue="orders"}
~~~

Đối với **queue riêng trên từng instance**, có thể dùng `sum by (queue)` để xem tổng công việc chưa xử lý của cả cụm. Nhưng nếu tất cả instance đều đo **cùng một queue chia sẻ**, cộng các Gauge có thể **đếm cùng một backlog nhiều lần**. Trước khi viết phép cộng, cần biết mỗi series đại diện cho đại lượng độc lập hay cùng một nguồn trạng thái.

Với queue có thể tăng đột biến giữa các lần scrape, cần cân nhắc tần suất thu thập, `max_over_time(...)`, hoặc các metrics bổ sung về số job nhận/xử lý và tuổi job cũ nhất.

### 7.4. So sánh trạng thái tài nguyên với độ trễ người dùng

Khi p95 của `POST /orders` tăng, một luồng điều tra có thể là:

1. Kiểm tra request rate, error rate và p95 để xác nhận ảnh hưởng đến người dùng.
2. Đối chiếu thời điểm tăng với CPU, GC pause, heap hoặc pool connections.
3. Nếu backlog tăng, xem số job vào/ra, retry và thời gian chờ.
4. Tìm trace chậm đã được lấy mẫu, xem span của bước gọi database hoặc inventory-service.
5. Dùng trace ID tìm logs liên quan tới timeout hoặc lỗi upstream.

MeterBinder giúp cung cấp **bối cảnh tài nguyên và hệ thống**. Để trả lời “request nào chậm và vì sao?”, vẫn cần instrumentation của request/operation qua Observation, cùng tracing và logging tương quan.

## 8. Tags và cardinality khi dùng binder

Chỉ một Gauge có số lượng nhãn quá nhiều cũng có thể làm tăng số series:

| Tag | Ví dụ | Đánh giá |
| --- | --- | --- |
| `application` | `order-service` | Phù hợp, tập giá trị nhỏ |
| `environment` | `staging`, `production` | Phù hợp |
| `queue` | `orders`, `notifications` | Phù hợp nếu số queue hữu hạn |
| `instance` | Định danh instance được hệ thống giám sát cấp | Cần cho vận hành, số series nhân theo instance |
| `order.id` | Một giá trị khác cho mỗi đơn | **Không phù hợp** làm metric label |
| `user.email` | Email từng người dùng | **Không thu thập** trong metrics |
| `trace.id` | Khác nhau theo request | **Không đưa vào metric label** |

Giả sử một binder đăng ký metric với 3 vùng triển khai, 4 môi trường và 20 instance. Nếu các nhãn này tạo tất cả tổ hợp, một tên metric có thể có **3 × 4 × 20 = 240** series. Thêm 100.000 giá trị `order.id` sẽ làm cardinality tăng theo lưu lượng và khiến metrics mất ý nghĩa tổng hợp.

**Quy tắc nên áp dụng:**

- Đặt meter name ổn định, mô tả rõ đơn vị và ý nghĩa.
- Chỉ đưa vào tags những nhãn có tập giá trị hữu hạn, phục vụ một câu hỏi phân tích cụ thể.
- Không gắn dữ liệu cá nhân, token hoặc request payload vào tags.
- Không đăng ký một meter mới cho từng request; đăng ký meter ổn định và ghi giá trị/sự kiện lên meter đó.
- Khi thêm tag hoặc histogram, tính số series có thể tăng, vì histogram còn nhân số ranh giới bucket.
- Với multi-instance, xác định tính cộng gộp: cùng một backlog được đo từ nhiều instance có thể không được cộng.

### 8.1. Common tags và MeterFilter

Spring Boot có thể thiết lập common tags qua `management.metrics.tags.*` để thống nhất `application` hoặc `environment`. Với yêu cầu phức tạp hơn, `MeterFilter` cho phép thay đổi hoặc từ chối meter theo chính sách đăng ký, chẳng hạn quản lý một tên metric không mong muốn hoặc bộ tag bị sai.

`MeterFilter` khác **`ObservationFilter`**:

- `MeterFilter` làm việc tại tầng **MeterRegistry và Meter.Id**.
- `ObservationFilter` làm việc với **Observation.Context** trong lifecycle.
- `ObservationConvention` quyết định cách đặt tên và key-values của một loại Observation.
- `MeterBinder` đăng ký meter, có thể hoạt động hoàn toàn không cần Observation.

Không nên dùng filter để che giấu thiết kế tags sai từ nguồn. Hãy sửa binder/instrumentation và dùng filter như một lớp chính sách bổ sung khi thật sự cần.

## 9. Binders, logs và distributed tracing phối hợp thế nào?

Một binder quan sát JVM, CPU hoặc backlog **không có trace ID của từng request**. Đó là điều bình thường: nó đang mô tả đại lượng của cả ứng dụng hoặc một thành phần. Trái lại, một custom `Observation` và tracing handler có thể tạo span nằm trong trace của một request.

~~~mermaid
flowchart LR
    Binders["JVM / Process / Queue MeterBinders"] --> Registry["MeterRegistry"]
    Registry --> Metrics["Metrics backend: xu hướng tài nguyên"]
    Requests["HTTP + Business Observations"] --> MeterHandler["Metrics handler"]
    MeterHandler --> Registry
    Requests --> TraceHandler["Tracing handler"]
    TraceHandler --> Traces["Trace backend: đường đi request"]
    Requests --> Logs["Logs: sự kiện và mã lỗi"]
    Traces -. "trace ID khi có" .-> Logs
    Metrics -. "service, instance, thời gian" .-> Traces
~~~

Điểm nối giữa binder metrics và traces thường là **service, instance, môi trường, phiên bản triển khai và khoảng thời gian**. Không phải mọi meter có exemplar hoặc liên kết trực tiếp đến một trace. Một số backend hỗ trợ **exemplars** để truy từ metric sang trace, nhưng cần hỗ trợ và cấu hình cụ thể ở registry, tracing và backend.

### 9.1. Context propagation và sampling không điều khiển binder metrics

Khi `order-service` gọi `inventory-service`, các span có thể liên kết nhờ W3C Trace Context, thường qua header `traceparent`. Nếu chạy xử lý bất đồng bộ, cần thiết lập propagation phù hợp để giữ parent-child relationship.

**MeterBinder không truyền context** qua HTTP/thread và cũng không yêu cầu một request đang có span để đo CPU hay queue. Nếu tracing được lấy mẫu 10%, phần lớn traces có thể không được lưu, nhưng các metrics về JVM/queue vẫn có thể được thu thập bình thường. Ngược lại, lỗi Prometheus scrape hoặc exporter metrics có thể làm mất chuỗi time series dù traces vẫn tồn tại.

Vì vậy, khi điều tra, hãy tách các nguyên nhân:

| Hiện tượng | Khả năng cần kiểm tra |
| --- | --- |
| Không thấy `orders.queue.pending` ở `/actuator/metrics` | Bean binder chưa được tạo, registry không được bind, meter bị filter, queue chưa tồn tại |
| Actuator có meter nhưng Prometheus không có | Registry Prometheus, exposure, scrape config, network hoặc tên series |
| Metrics có mà trace không có | Sampling, tracing bridge, exporter, Collector hoặc propagation |
| Trace có mà logs không có correlation | Cấu hình logging/MDC hoặc scope không được duy trì |
| CPU tăng nhưng không có request chậm | CPU do tác vụ nền, GC, cron, hoặc khối lượng không nằm trên request path |

Không suy ra rằng một binder đang hoạt động chỉ vì `/actuator/health` trả `UP`. Health endpoint và metrics giải quyết những câu hỏi khác nhau.

## 10. Các lỗi thường gặp khi tự viết MeterBinder

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tạo Gauge từ một object tạm | Object bị GC, Gauge không còn giá trị đáng tin | Giữ tham chiếu mạnh trong bean có vòng đời phù hợp |
| Gắn request ID làm tag | Cardinality tăng theo lưu lượng | Dùng tags hữu hạn; tương quan request bằng traces/logs |
| Cập nhật Gauge như Counter | Dữ liệu về tổng số sự kiện bị sai | Counter cho tích lũy, Gauge cho trạng thái tức thời |
| Gọi network/DB nặng trong callback Gauge | Scrape chậm, tăng tải và nguy cơ timeout | Cung cấp nguồn đọc nhẹ, cache có giới hạn độ mới |
| Đăng ký binder hai lần vào cùng registry | Đăng ký lặp, cảnh báo hoặc khó hiểu dữ liệu | Để Spring Boot quản lý hoặc gọi bindTo thủ công, chọn một cách |
| Tạo registry mới trong service | Meters không có ở registry đã export | Inject registry được cấu hình chung |
| Đo một queue chia sẻ từ mọi instance rồi cộng | Tổng backlog bị nhân số instance | Hiểu ngữ nghĩa của nguồn dữ liệu trước khi aggregate |
| Gắn timestamp vào meter name | Tên metric thay đổi liên tục | Tên cố định, timestamp là đặc tính thời gian của sample |
| Đổi metric name hoặc baseUnit tùy ý | Dashboard/alert cũ có thể không tìm thấy dữ liệu | Quản lý hợp đồng metrics và kế hoạch di trú |
| Thấy Gauge nhưng không thấy đỉnh ngắn | Scrape chỉ lấy mẫu định kỳ | Đo thêm Counter/Timer, xem lại tần suất scrape |
| Chỉ xem endpoint Actuator | Không biết Prometheus có scrape thành công | Kiểm tra backend đích và trạng thái pipeline |
| Nhầm binder với tracing instrumentation | Không có span của request dù metrics hạ tầng đầy đủ | Instrument request/business bằng Observation và tracing handler |

## 11. Checklist trước khi đưa một binder lên production

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Meter mô tả một đại lượng rõ ràng | Có tên, loại meter, đơn vị, mô tả, nguồn đo |
| Binder đăng ký đúng một lần/registry | Có quy ước bean hoặc bindTo thủ công rõ ràng |
| Giá trị cập nhật đúng | Unit test thay đổi nguồn đo và kiểm tra Gauge |
| Đối tượng đo có vòng đời phù hợp | Gauge không phụ thuộc object tạm dễ bị GC |
| Chi phí callback chấp nhận được | Không truy vấn chậm hoặc gây side effect khi scrape |
| Tags có cardinality hữu hạn | Không chứa request/user/order ID hoặc dữ liệu nhạy cảm |
| Có thể xác định cách tổng hợp qua instance | Không cộng trùng cùng một queue chia sẻ |
| Actuator nhìn thấy meter | `/actuator/metrics` có tên và measurements phù hợp |
| Exporter/backend đã được xác minh | Scrape hoặc pipeline đích có dữ liệu và timestamp mới |
| Dashboard có ngưỡng gắn với hành động | Ví dụ backlog cao kéo dài dẫn đến kiểm tra consumer |
| Có thể điều tra cùng tín hiệu khác | So sánh với HTTP errors/latency, traces và logs |
| Có kế hoạch đổi schema | Đổi tên/tag/đơn vị phải cập nhật truy vấn, alert và tài liệu |

## 12. Bài thực hành: phát hiện hàng đợi đơn hàng bị nghẽn

**Bối cảnh:** `order-service` nhận `POST /orders` rồi gửi tác vụ xử lý nền đến một queue. Đội vận hành thấy p95 request HTTP vẫn tương đối ổn định nhưng nhiều đơn không hoàn tất đúng hạn. Cần thêm metrics để phân biệt request nhận thành công với xử lý nền bị nghẽn.

**Yêu cầu:**

1. Cài Actuator và Prometheus registry theo phiên bản Spring Boot của dự án, cho phép truy cập endpoint metrics trong môi trường thử nghiệm.
2. Định nghĩa `PendingOrderQueue` có phương thức `size()` và một implementation dùng `AtomicInteger` để mô phỏng số tác vụ chờ.
3. Tạo `PendingOrderQueueMeterBinder` đăng ký `Gauge` `orders.queue.pending`, đơn vị `tasks` và tag `queue=orders`.
4. Khai báo binder làm Spring bean; xác minh bean queue và registry được ứng dụng quản lý.
5. Viết unit test dùng `SimpleMeterRegistry` và thay queue depth từ 3 → 7 → 2. Giải thích tại sao Gauge đọc giá trị hiện tại mà không tích lũy 12.
6. Gửi request giả lập tạo backlog, quan sát meter ở `/actuator/metrics` và series thực tế ở `/actuator/prometheus`.
7. Đề xuất thêm `Counter` số job xử lý thành công/thất bại và `Timer` thời gian xử lý; phân biệt rõ từng câu hỏi mà ba loại meter trả lời.
8. Nếu queue là nguồn chia sẻ bên ngoài, xác định khi nào có thể cộng các Gauge từ nhiều instance và khi nào sẽ đếm trùng.
9. Tạo một tình huống xử lý nền timeout; kết hợp queue depth, failure count, HTTP latency, trace được sampling giữ và log có trace ID để điều tra.
10. Đề xuất cảnh báo khi backlog vượt ngưỡng liên tục, kèm dashboard hiển thị lượng job vào/ra và tuổi của tác vụ chờ lâu nhất nếu nguồn dữ liệu cho phép.

**Kết quả mong đợi:** một binder Java có thể đọc hiểu, test chứng minh Gauge động, cấu hình Spring Boot phù hợp, truy vấn metrics thực tế và bản mô tả ngắn về cách tìm lỗi khi HTTP request thành công nhưng xử lý nền chậm.

## 13. Ghi nhớ

**`MeterBinder` là cơ chế đăng ký meters vào `MeterRegistry`**. Spring Boot/Micrometer có nhiều binder cho JVM, process, hệ thống và một số tích hợp tài nguyên; ứng dụng có thể viết binder riêng cho hàng đợi hoặc trạng thái nghiệp vụ. Một binder chất lượng cần giữ tên/đơn vị ổn định, đọc dữ liệu đúng cách, quản lý vòng đời đối tượng được đo và giới hạn tag/cardinality.

Binder metrics giúp nhận ra tình trạng tài nguyên và xu hướng vận hành. Khi cần xác định *request cụ thể chậm hoặc lỗi ở đâu*, hãy bổ sung **Micrometer Observation, logs có correlation và distributed tracing**. Những tín hiệu này liên kết với nhau bằng bối cảnh service/instance/thời gian hoặc trace ID khi có tracing; chất lượng điều tra còn phụ thuộc context propagation, sampling, exporter và backend thực sự nhận dữ liệu.

**Tài liệu tham khảo:**

- [Micrometer — JVM Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html)
- [Micrometer — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html)
- [Micrometer — Meter Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
