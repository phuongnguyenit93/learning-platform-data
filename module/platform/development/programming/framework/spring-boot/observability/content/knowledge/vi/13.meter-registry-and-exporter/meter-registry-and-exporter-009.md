# Exporter step và batch: nhịp xuất metrics và gom dữ liệu trong Spring Boot

> **Chương:** Meter registry và exporter  
> **Bài:** Exporter step và batch  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Bài toán: metric đã tăng nhưng backend chưa hiển thị ngay

Giả sử dịch vụ `order-service` ghi một `Counter` mỗi khi nhận yêu cầu tạo đơn. Trong log ứng dụng, bạn thấy 100 yêu cầu được xử lý thành công, nhưng dashboard metrics ở hệ thống giám sát chỉ cập nhật theo từng đợt, chậm vài chục giây. Một lần triển khai khác khiến số request xuất qua OTLP tăng mạnh, CPU và lưu lượng mạng của exporter cũng tăng. Vì sao?

Trong một hệ thống observability, **thời điểm ứng dụng ghi một phép đo** và **thời điểm hệ thống giám sát nhận được dữ liệu** là hai thời điểm khác nhau:

- `MeterRegistry` cập nhật trạng thái meter khi code gọi `Counter.increment()`, `Timer.record(...)` hoặc khi `Gauge` được đọc.
- Với một **step/push registry**, dữ liệu thường được chuẩn bị và xuất theo một chu kỳ `step` định trước, thay vì gửi HTTP request cho mỗi lần `increment()`.
- Một lần xuất có thể chứa **nhiều metrics/data points**. Tại lớp trung gian như OpenTelemetry Collector, bộ xử lý `batch` còn có thể gom nhiều dữ liệu nhận được để gửi theo kích thước hoặc timeout.
- Với **Prometheus pull**, chính Prometheus chủ động scrape endpoint theo `scrape_interval`; cơ chế này khác với `step` của các push registry.

Do đó cần phân biệt hai câu hỏi:

1. **Exporter step:** bao lâu ứng dụng chuẩn bị và gửi một đợt số liệu?
2. **Batch:** mỗi đợt giao tiếp gom những datapoints nào, khi nào được gửi tiếp, và giới hạn tài nguyên nằm ở đâu?

**Mục tiêu:** hiểu cả hai lớp, cấu hình Spring Boot và OTLP/Prometheus đúng cách, ước lượng độ trễ–chi phí, giám sát thất bại xuất dữ liệu và tránh nhầm batch với số lượng sự kiện nghiệp vụ hoặc trace sampling.

## 2. Từ lời gọi instrument đến dữ liệu trên dashboard

Các thuật ngữ nền tảng:

| Khái niệm | Diễn giải | Ví dụ |
| --- | --- | --- |
| **Meter** | Một Counter, Timer, Gauge, DistributionSummary, LongTaskTimer… có tên và tags | `orders.processing.duration{outcome="success"}` |
| **Measurement** | Đại lượng đọc được từ meter | Count, total time, giá trị gauge |
| **Data point** | Một giá trị/nhóm thống kê có thuộc tính, timestamp và kiểu dữ liệu được đưa vào payload hoặc backend | Count theo `outcome=error` trong khoảng xuất |
| **Step** | Khoảng thời gian dùng để tính và/hoặc xuất số liệu ở registry kiểu step | 30 giây |
| **Publish/export** | Lần registry gửi một payload tới backend/collector hoặc hệ thống tương ứng | Gửi OTLP HTTP request |
| **Batch** | Nhóm nhiều data points/records được vận chuyển hoặc xử lý cùng đợt | Collector gom đến ngưỡng kích thước hoặc timeout |
| **Scrape interval** | Chu kỳ bên thu thập chủ động gọi endpoint pull | Prometheus scrape mỗi 15 giây |
| **Temporality** | Cách biểu diễn metric theo khoảng tăng thêm hoặc tích lũy | Delta và cumulative |
| **Retention** | Thời gian backend lưu dữ liệu đã nhận | Phụ thuộc chính sách hệ thống giám sát |

~~~mermaid
flowchart LR
    A["Request / batch job"] --> B["Micrometer Counter, Timer, Gauge"]
    B --> C["MeterRegistry"]
    C --> D{"Kiểu xuất metrics"}
    D -->|"Push/step"| E["Chốt kỳ step + publish"]
    D -->|"Pull"| F["Endpoint /actuator/prometheus"]
    E --> G["OTLP / vendor backend"]
    G --> H["Collector batch nếu có"]
    H --> I["Backend lưu metrics"]
    F --> J["Prometheus scrape interval"]
    J --> I
    I --> K["Dashboard / alerts"]
~~~

Sơ đồ chỉ mô tả các **lộ trình phổ biến**. Không phải mọi `MeterRegistry` đều có cùng logic publish; không phải mọi push exporter đều sử dụng cùng định dạng hoặc có hỗ trợ cấu hình batch-size; một hệ thống có thể không sử dụng Collector.

**Điểm quan trọng:** mặc dù code tạo và cập nhật meter ngay, người xem dashboard phải chờ registry, mạng, collector, backend và chu kỳ query hoàn tất. Sự trễ đó không đồng nghĩa code instrument thất bại.

## 3. Step trong Micrometer nghĩa là gì?

Micrometer cung cấp họ registry dạng step, thường thông qua `StepMeterRegistry` và các implementation phù hợp. `StepMeterRegistry` sử dụng cấu hình chu kỳ xuất để tổ chức những lần publish. Các backend triển khai registry khác có thể hoạt động theo mô hình khác.

Một ví dụ cấu hình:

~~~yaml
management:
  otlp:
    metrics:
      export:
        step: 30s
~~~

Với ứng dụng Spring Boot 3.x có OTLP registry phù hợp, ví dụ này yêu cầu nhịp xuất OTLP metrics theo khoảng **30 giây**. Mặc định `step` có thể khác theo loại registry, phiên bản và cấu hình. Đừng mặc định mọi backend đều có bước 1 phút hoặc mọi loại metric cùng cách tổng hợp.

### 3.1. Vòng đời của một bước 30 giây

Giả sử một registry đưa số liệu theo chu kỳ, và một Counter nhận sự kiện trong suốt các khoảng:

~~~text
Thời gian        00:00             00:30             01:00
                 |-----------------|-----------------|
Ứng dụng         + + + + + + + +   + + + + + + ...
Step             kỳ A              kỳ B
Publish                               ^                 ^
Backend nhận                        sau mốc A        sau mốc B
~~~

Nếu sự kiện xảy ra lúc `00:12`, bạn có thể chưa thấy dữ liệu mới trên backend cho đến khi kỳ A được publish, truyền đi, xử lý và lưu. Nếu sự kiện xảy ra lúc `00:31`, nó thuộc kỳ kế tiếp theo cách tổ chức của step registry, nên thời điểm backend thấy thay đổi có thể muộn hơn.

Các mốc là **minh họa**, không phải cam kết đồng hồ luôn đồng bộ đúng giây thứ 00/30. Scheduler, thời gian thực hiện publish, độ trễ mạng, runtime pause và phiên bản registry có thể làm thời điểm thực tế lệch.

### 3.2. Step không phải “mỗi 30 giây ứng dụng mới bắt đầu đo”

Đây là nhầm lẫn thường gặp. Với `Counter.increment()`, trạng thái meter được cập nhật khi sự kiện xảy ra. Step chủ yếu quyết định **kỳ tập hợp/đọc** và **lịch truyền số liệu** của registry kiểu step. Không cần code nghiệp vụ tự tích lũy 30 giây mới gọi `increment()`.

Tương tự, `Timer.record(...)` ghi thời lượng vào meter khi thao tác hoàn tất; exporter mới lấy các thống kê tương ứng để xuất theo kỳ. Step không biến một Timer thành một log riêng cho mọi lần gọi. Metric vẫn là dữ liệu **tổng hợp**.

### 3.3. Vì sao step quan trọng với Counter và Timer?

Trong nhiều step-based registry, Counter và Timer có thống kê được xử lý theo từng khoảng step, chẳng hạn số lần và tổng duration trong kỳ. Nhưng **định dạng gửi ra backend còn phụ thuộc registry và giao thức**. Một số backend mong rate; một số dùng delta/cumulative và tự tính rate.

Không được kết luận chỉ từ `step=30s` rằng giá trị Counter trên backend “luôn là tổng tích lũy từ lúc ứng dụng khởi động”, cũng không được mặc định là “số lần mỗi giây”. Hãy kiểm tra temporality/đơn vị của exporter và convention của backend cụ thể.

## 4. Step, reporting latency và tính mới của dữ liệu

Độ trễ từ một sự kiện nghiệp vụ đến khi nó hiển thị trên dashboard có nhiều lớp:

~~~text
Sự kiện được ghi
  -> chờ hết kỳ step (nếu registry push/step)
  -> publish / serialize / network
  -> nhận vào Collector (nếu dùng)
  -> chờ Collector batch hoặc queue
  -> exporter tới backend
  -> backend ingest/index
  -> chu kỳ query hoặc refresh dashboard
~~~

Có thể mô hình hóa gần đúng:

~~~text
visibility_delay ≈ wait_to_next_step
                 + publish_duration
                 + network_delay
                 + collector_queue_and_batch_delay
                 + backend_ingest_delay
                 + dashboard_refresh_delay
~~~

Đây là **mô hình phân tích**, không phải công thức dự đoán chính xác hoặc một SLA được đảm bảo. Trong điều kiện lỗi, queue đầy, retry, backend nghẽn hoặc ứng dụng tắt, độ trễ có thể vượt xa kỳ step; dữ liệu có thể không được giao thành công.

| Tình huống | Ý nghĩa của step |
| --- | --- |
| Sự kiện vừa xảy ra sau mốc publish | Có thể phải chờ gần hết một kỳ mới có lần publish tiếp |
| Publish bị chậm vì mạng | Chu kỳ trên config không đảm bảo backend nhận đúng giờ |
| Pod bị dừng trước publish tiếp theo | Phần số liệu chưa xuất có nguy cơ mất, tùy cơ chế đóng/mở và retry của registry |
| Backend refresh mỗi phút | Dù exporter gửi mỗi 15 giây, người dùng vẫn có thể chỉ thấy cập nhật khi dashboard refresh |
| Scrape Prometheus mỗi 15 giây | Đây là thời điểm **pull**, không phải lịch push từ `StepMeterRegistry` |

### Chọn step từ yêu cầu vận hành

Nếu alert cần phát hiện sự cố trong khoảng 1 phút, step 5 phút có thể quá thưa. Nếu chỉ quan tâm tổng hợp batch theo giờ, gửi metrics mỗi 5 giây có thể gây lưu lượng thừa. Nhưng đặt step cực ngắn **không mặc nhiên** cải thiện độ chính xác: tăng overhead, network và backend ingestion, đặc biệt khi cardinality/histogram lớn.

## 5. Batch là gì và được thực hiện ở những lớp nào?

Từ “batch” có thể chỉ các hành vi khác nhau. Cần luôn nói rõ **batch tại đâu**.

| Lớp | Batch thường có nghĩa gì? | Có phụ thuộc step không? |
| --- | --- | --- |
| Mã nghiệp vụ | Xử lý nhiều bản ghi hoặc message trong một job | Không nhất thiết |
| MeterRegistry / exporter | Gom nhiều meters/data points trong một hoặc nhiều payload xuất | Có thể phát sinh ở một lần publish step |
| HTTP/gRPC transport | Một request truyền nhiều data points | Phụ thuộc client/protocol |
| OpenTelemetry Collector `batch` processor | Gom telemetry records/data points trước khi chuyển tới exporter kế tiếp | Do timeout/ngưỡng size riêng, không kế thừa cấu hình step của Micrometer |
| Backend ingest | Gom, nén hoặc tổ chức dữ liệu để ghi lưu trữ | Phụ thuộc backend |

**Batch không đồng nghĩa “chờ cho đủ 100 đơn hàng rồi mới ghi Counter”.** Metrics tổng hợp được ghi vào meter trong lúc ứng dụng xử lý; transport hoặc collector có thể gộp nhiều data points để giảm số request.

Một batch có thể gồm dữ liệu của hàng trăm tên metric và các tổ hợp tags, không nhất thiết một metric phản ánh một event. Ngược lại, một Timer có histogram có thể xuất nhiều data points cho cùng tên metric và tags.

### 5.1. Hai kiểu giới hạn batch phổ biến

- **Ngưỡng kích thước:** khi đủ số records/data points, bộ gom dữ liệu kích hoạt gửi. Với Collector, ý nghĩa cụ thể của ngưỡng phụ thuộc signal và phiên bản processor.
- **Timeout:** nếu chưa đủ ngưỡng nhưng đã chờ đủ thời gian, bộ gom dữ liệu gửi những gì đã có để hạn chế latency.

Trong nhiều hệ thống, batch lớn giảm số request nhưng tăng thời gian chờ và memory footprint; batch nhỏ gửi nhanh nhưng làm overhead transport lớn. Không có một kích thước phù hợp cho mọi traffic và backend.

## 6. OTLP push: Spring Boot phát metrics theo step

Một cấu hình thường gặp là Spring Boot dùng Micrometer OTLP registry để đẩy metrics đến OpenTelemetry Collector qua OTLP/HTTP.

### 6.1. Dependencies Maven

Với Spring Boot 3.x đang sử dụng parent/BOM quản lý phiên bản:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-otlp</artifactId>
    </dependency>
</dependencies>
~~~

`spring-boot-starter-actuator` hỗ trợ metrics/management; `micrometer-registry-otlp` cung cấp registry xuất metrics OTLP. Không cần tự tạo một `MeterRegistry` mới trong service vì nó có thể không sử dụng cấu hình/exporter Spring Boot đang quản lý.

### 6.2. application.yml minh họa

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: http://localhost:4318/v1/metrics
        step: 30s
  metrics:
    tags:
      application: order-service
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Diễn giải:

- `management.otlp.metrics.export.url` là điểm nhận OTLP metrics; `/v1/metrics` là đường dẫn phổ biến của OTLP/HTTP metrics receiver.
- `management.otlp.metrics.export.step` điều chỉnh nhịp publish của registry này.
- `application=order-service` là nhãn hữu hạn hữu ích khi tìm metrics theo service.
- `/actuator/metrics` là endpoint nội bộ để kiểm tra meter. **Có metrics trong Actuator không chứng minh OTLP export thành công.**
- Một hệ thống đang chạy trong container không thể mặc định dùng `localhost:4318` để kết nối đến Collector ở container khác. `localhost` trỏ về **chính network namespace/container** đó; cần địa chỉ service/host tương ứng với triển khai.

**Phạm vi phiên bản:** ví dụ dùng hệ property của Spring Boot 3.x. Với phiên bản Spring Boot khác hoặc registry đời khác, cần kiểm tra metadata cấu hình và documentation của phiên bản tương ứng. Không chuyển máy móc từ `management.metrics.export.*` của các đời Boot cũ sang namespace mới.

### 6.3. Thay đổi step không thay đổi tần suất HTTP request

Nếu ứng dụng xử lý 1.000 request/giây và step là 30 giây, mỗi event vẫn cập nhật Counter/Timer tương ứng khi code gọi. Registry có thể gửi một payload chứa các thống kê tổng hợp sau mỗi kỳ; **không** có nghĩa exporter sẽ mở 30.000 HTTP connections hoặc tạo 30.000 OTLP requests trong 30 giây.

Số payload thực tế phụ thuộc số meters, labels, histogram, giới hạn exporter, cách mã hóa và bất kỳ phân tách batch nào. Khi có retry, số request HTTP còn có thể lớn hơn số lần publish định kỳ.

## 7. Ví dụ Java: ghi metrics nghiệp vụ trước khi exporter làm việc

Để thấy ranh giới trách nhiệm, dùng một service nhận `MeterRegistry` qua constructor. Service không biết OTLP URL hay step.

~~~java
package example.orders;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class OrderProcessingService {
    private final MeterRegistry meterRegistry;

    public OrderProcessingService(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    public void processOrder(String incomingChannel, Runnable operation) {
        String channel = normalizeChannel(incomingChannel);
        String outcome = "success";
        Timer.Sample sample = Timer.start(meterRegistry);

        try {
            operation.run();
        } catch (RuntimeException | Error ex) {
            outcome = "error";
            throw ex;
        } finally {
            Timer duration = Timer.builder("orders.processing.duration")
                .description("Duration of completed order attempts")
                .tag("channel", channel)
                .tag("outcome", outcome)
                .register(meterRegistry);

            sample.stop(duration);
        }
    }

    private static String normalizeChannel(String value) {
        if ("web".equals(value)) return "web";
        if ("mobile".equals(value)) return "mobile";
        if ("partner".equals(value)) return "partner";
        return "other";
    }
}
~~~

Với một lần gọi `processOrder(...)`:

1. `Timer.Sample` bắt đầu đo thời lượng thao tác đồng bộ.
2. Khi công việc kết thúc hoặc lỗi, `sample.stop(duration)` ghi **một mẫu thời lượng** vào registry tương ứng.
3. `channel` và `outcome` là low-cardinality tags. Không thêm `orderId` hoặc `requestId` làm metric label.
4. Registry đích quyết định cách biểu diễn count, sum và histogram (nếu đã cấu hình), cùng thời điểm exporter publish. **Service không phải gửi OTLP trực tiếp.**
5. Nếu một đường code đã được đo bằng `@Observed` hoặc instrumentation tương đương, không đặt thêm Timer thủ công cùng một ý nghĩa một lần nữa; nếu không, có thể đếm trùng.

Nếu `operation.run()` chỉ *submit* một công việc async rồi trả về, Timer trên đo thời gian submit chứ không đo thời gian đến khi async hoàn tất. Cần đặt ranh giới đo theo thời điểm thực sự hoàn thành hoặc dùng instrument phù hợp với async.

### 7.1. Liên hệ với ObservationRegistry

Một đoạn code cũng có thể dùng `ObservationRegistry`:

~~~java
Observation.createNotStarted("orders.processing", observationRegistry)
    .lowCardinalityKeyValue("channel", "web")
    .observe(() -> doBusinessWork());
~~~

Khi Spring Boot đã đăng ký Meter ObservationHandler, Observation có thể tạo meter tương ứng; nếu tracing handler hoạt động, nó còn tạo span. **Không tự ghi Timer thủ công cùng boundary** nếu Observation đã cung cấp đúng metric cần đo. Phần exporter step/batch diễn ra **sau** việc ghi meter, bất kể meter đến từ API trực tiếp hay Observation handler.

## 8. OpenTelemetry Collector batch processor: gom sau khi nhận OTLP

Một triển khai thường gặp:

~~~mermaid
flowchart LR
    A["Spring Boot + Micrometer OTLP"] -->|"step 30s, OTLP/HTTP"| B["OTLP receiver"]
    B --> C["Collector batch processor"]
    C -->|"size trigger / timeout 5s"| D["Collector exporter"]
    D --> E["Metrics backend"]
    E --> F["Dashboard và alert"]
~~~

Collector batch processor **không thay đổi step của Micrometer**. Nó nhận dữ liệu đã được ứng dụng export, rồi quyết định khi nào chuyển dữ liệu tiếp theo.

### 8.1. Ví dụ collector-config.yaml dùng cho môi trường học tập

~~~yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 5s
    send_batch_size: 1024
    send_batch_max_size: 2048

exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
~~~

**Ví dụ này dùng exporter debug** để quan sát dữ liệu trong log của Collector khi học, không phải cấu hình production gửi metrics tới một nền tảng giám sát lâu dài. Collector distribution/version phải có receiver, processor và exporter nêu trên.

Ý nghĩa:

- `receivers.otlp.protocols.http` nhận payload OTLP/HTTP, thường tại cổng `4318`.
- `batch.timeout=5s` giúp batch được gửi tiếp sau thời gian chờ ngay cả khi chưa đủ ngưỡng kích thước.
- `send_batch_size=1024` là **ngưỡng kích hoạt** batch, không phải cam kết mọi batch luôn có đúng 1.024 đơn vị.
- `send_batch_max_size=2048` giới hạn kích thước mỗi batch khi tính năng và phiên bản processor hỗ trợ; đơn vị đếm cụ thể có thể là spans, metric data points hoặc log records tùy signal.
- `exporters.debug` in dữ liệu ra log Collector để kiểm chứng, nhưng có thể gây lượng log rất lớn và làm lộ metadata. Chỉ dùng trong môi trường thử nghiệm được kiểm soát.
- `endpoint=0.0.0.0:4318` lắng nghe trên các interface của container/host; cần giới hạn mạng, xác thực/TLS nếu triển khai thật. Không đưa endpoint debug hoặc Collector không bảo vệ ra Internet.

### 8.2. Ví dụ timeline khi step và batch khác nhau

Giả sử Micrometer publish tại khoảng `00:30`. Collector nhận sau đó và chưa đạt ngưỡng size; batch timeout 5 giây thì có thể chuyển tiếp khoảng `00:35`. Nếu chỉ có một request/đợt nhỏ, Collector không cần chờ đến 1.024 data points mới gửi vì timeout cũng kích hoạt flush.

Ngược lại, nếu hàng chục instance cùng publish tạo đủ dữ liệu, batch có thể được gửi sớm khi đạt ngưỡng. **Sự kết hợp 30s + 5s không có nghĩa backend luôn nhận dữ liệu chính xác sau 35 giây.** Network delay, scheduling, queue, retry, rate limit và backend ingestion còn tác động.

### 8.3. Batch không phải durable queue

Batch processor tối ưu việc gom và gửi dữ liệu. Nó **không tự cung cấp bảo đảm lưu bền vững** nếu tiến trình Collector hoặc exporter bị dừng trước khi gửi. Để tăng độ tin cậy, một số exporter và Collector deployment cung cấp retry, sending queue và có thể cơ chế lưu bền vững riêng; phải cấu hình theo component/version thực tế và kiểm tra bằng thử nghiệm lỗi.

Nếu backend không nhận dữ liệu, đừng mặc định rằng “Collector sẽ tự giữ lại mọi metric đến khi mạng hoạt động”. Cần xem logs, self-telemetry, queue capacity, chính sách retry và số liệu bị drop.

## 9. Prometheus pull: scrape interval không phải exporter step

Với **PrometheusMeterRegistry**, ứng dụng thường **không chủ động push** metrics lên Prometheus mỗi 30 giây. Prometheus yêu cầu dữ liệu qua `/actuator/prometheus` theo lịch `scrape_interval` của Prometheus server.

### 9.1. Spring Boot cấu hình endpoint pull

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

### 9.2. Prometheus scrape config minh họa

~~~yaml
scrape_configs:
  - job_name: order-service
    scrape_interval: 15s
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["order-service:8080"]
~~~

Trong ví dụ, **Prometheus** chủ động gọi endpoint khoảng 15 giây/lần. Cấu hình này là của Prometheus, **không thuộc `application.yml` của Spring Boot**. Khi ứng dụng ở Kubernetes, cấu hình target thường đến từ cơ chế service discovery/monitoring tương ứng thay vì một target tĩnh.

| Câu hỏi | OTLP push registry theo step | Prometheus pull |
| --- | --- | --- |
| Ai khởi tạo trao đổi dữ liệu? | Ứng dụng/registry khi đến kỳ publish | Prometheus server khi đến kỳ scrape |
| Cấu hình nhịp ở đâu? | Thuộc tính exporter `step` trong Spring Boot/registry | `scrape_interval` trong Prometheus |
| Endpoint của ứng dụng | Gửi tới receiver OTLP | Phơi bày `/actuator/prometheus` |
| Cơ chế batch | Payload ứng dụng và có thể Collector batch phía sau | HTTP response chứa nhiều series mỗi lần scrape; backend tự xử lý |
| Thay đổi nhịp bằng cách nào? | Điều chỉnh step và phụ thuộc exporter | Điều chỉnh scrape interval và khả năng target/backend |
| Sai lầm phổ biến | Tưởng mỗi sự kiện được push ngay | Tưởng cấu hình step OTLP đổi được lịch scrape |

**Không cấu hình `management.otlp.metrics.export.step` rồi kỳ vọng nó điều khiển tần suất scrape Prometheus**. Hai pipeline khác nhau; ứng dụng có thể bật cả hai registry, và lúc đó cùng một phép đo có thể được xuất tới hai nơi theo cơ chế riêng.

## 10. Temporality: step không đồng nghĩa một định dạng Counter cố định

Khi đọc metrics từ OTLP hoặc backend khác, phải hiểu một Counter đại diện cho **delta** hay **cumulative**.

| Kiểu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Delta** | Giá trị phát sinh trong khoảng đo được mô tả | 120 đơn hàng trong cửa sổ 30 giây |
| **Cumulative** | Giá trị tích lũy từ mốc start time tương ứng | Tổng 5.320 đơn hàng từ khi tiến trình bắt đầu |
| **Gauge** | Giá trị tại thời điểm đọc | 32 job đang chờ xử lý |
| **Timer histogram/distribution** | Nhiều thống kê/bucket của duration | Count, sum, bucket theo latency |

Một registry kiểu step có thể sử dụng phép tổng hợp theo cửa sổ; nhưng **temporality được mã hóa trong OTLP và semantics phía backend phụ thuộc implementation/phiên bản**, nên không được suy chỉ từ thuộc tính `step`.

### 10.1. Hệ quả khi tính rate

Nếu backend lưu cumulative Counter, có thể tính tốc độ từ độ chênh tăng theo thời gian và xử lý restart/reset. Với Prometheus, ta thường truy vấn:

~~~promql
sum(
  rate(orders_processing_duration_seconds_count[5m])
)
~~~

Ví dụ chỉ đúng nếu Timer được xuất trong Prometheus với tên series tương ứng. Trên một backend nhận delta OTLP, cách nội suy rate có thể khác; một số backend tự chuyển đổi hoặc tính trên các delta đã gửi. **Không lấy một giá trị step rồi tùy tiện chia hai lần theo số giây**, vì có thể backend đã biểu diễn rate hoặc đã thực hiện chuyển đổi.

### 10.2. Khi process restart

Nếu metric cumulative reset theo tiến trình và bạn so sánh hai điểm khác nhau, giá trị có thể giảm do restart; đây không phải doanh số âm. Một số hệ thống có cơ chế phân biệt start time/temporality để xử lý. Với step/delta, nếu mất một lần publish, backend có thể thiếu một phần tổng lượng sự kiện tùy exporter và chính sách retry.

**Bài học:** muốn debug giá trị bất thường, kiểm tra signal type, đơn vị, timestamps, temporality, process restarts và cách backend tổng hợp; không chỉ nhìn tên `Counter`.

## 11. Chọn step và batch dựa trên độ trễ, chi phí và số series

Không có một step lý tưởng cho mọi dịch vụ. Cân nhắc thời gian phát hiện sự cố, số data points, mức sử dụng CPU, băng thông và khả năng ingest của backend.

| Cấu hình minh họa | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- |
| Step 10s | Cập nhật push thường xuyên hơn trong điều kiện bình thường | Nhiều lần publish, payload và overhead transport |
| Step 30s | Cân bằng giữa tính mới và overhead cho nhiều dịch vụ | Alert thời gian rất ngắn có thể bị trễ |
| Step 60s | Ít lần publish hơn | Khó phát hiện biến động nhanh, độ trễ hiển thị lớn hơn |
| Step 5m | Phù hợp một số chỉ số ít cần cập nhật | Dễ bỏ lỡ thời điểm cần phản ứng nhanh, công việc đứt quãng |
| Collector batch nhỏ | Dữ liệu được chuyển tiếp nhanh hơn | Tăng số request từ Collector |
| Collector batch lớn | Có thể giảm overhead của đường truyền | Tăng memory và latency, cần quan sát queue/failure |

Các mốc trên chỉ là **điểm bắt đầu để thảo luận**; cần đo thực tế. Ví dụ, nếu 10 instance có 5.000 chuỗi xuất một data point mỗi step 30 giây:

~~~text
Số lần publish trên mỗi instance mỗi ngày:
  86.400 / 30 = 2.880

Data points/ngày (giả sử một data point mỗi series mỗi kỳ):
  10 × 5.000 × 2.880 = 144.000.000
~~~

Đây là ước tính có giả định, **không phải** số data points thật của một Micrometer exporter: Timer có thể phát nhiều thống kê/bucket, một số series không phát ở kỳ không có dữ liệu, backend có thể thêm metadata hoặc giới hạn. Mục đích là thấy **cardinality × tần suất publish** quyết định quy mô vận hành.

### Công thức ước lượng chi phí đơn giản

~~~text
publishes_per_day ≈ 86.400 / step_seconds

data_points_per_day ≈ active_series_or_points_per_publish
                    × publishes_per_day
                    × number_of_instances

network_bytes_per_day ≈ average_bytes_per_publish
                      × publishes_per_day
                      × number_of_instances
~~~

Nếu tăng step từ 30s lên 60s trong điều kiện số điểm/payload tương đương, số lần publish giảm khoảng một nửa; nhưng số lượng events nghiệp vụ vẫn như cũ. Tần suất thay đổi có thể làm tính mới của dashboard, độ phân giải và xử lý lỗi khác đi, nên không chọn chỉ vì tiết kiệm network.

## 12. Cardinality và histogram ảnh hưởng batch như thế nào?

Một `Counter` có một metric name nhưng nhiều tổ hợp tags, mỗi tổ hợp có thể trở thành một series/data point. Ví dụ:

| Tag | Số giá trị |
| --- | ---: |
| `channel`: web/mobile/partner/other | 4 |
| `outcome`: success/rejected/error | 3 |
| `region`: north/central/south | 3 |
| `instance` (nhãn đích scrape hoặc resource) | 8 |

Số tổ hợp tối đa khi tất cả xuất hiện: **4 × 3 × 3 × 8 = 288**. Khi có histogram latency với 20 bucket cho mỗi tổ hợp (nếu được bật và backend dùng dạng bucket đó), số chuỗi/phần dữ liệu có thể tăng mạnh. Việc bật `@Timed` hoặc Observation không làm vấn đề này biến mất; cardinality xuất phát từ **tập tag values và số loại đo**.

**Không đưa** `requestId`, `orderId`, email, exception message, URL chứa ID hoặc payload tự do thành metric tag. Nếu mỗi request tạo tổ hợp tags mới, một batch có thể lớn dù có rất ít request trong mỗi khoảng step, vì registry có thể tích lũy các meter/series theo thời gian sống của ứng dụng.

Khi cần lần theo một giao dịch cụ thể:

- Dùng metrics low-cardinality để tìm thời gian/điểm nóng.
- Dùng tracing với high-cardinality span attributes được kiểm soát để xem đường gọi và lỗi.
- Dùng logs có `traceId/spanId` khi logging correlation được cấu hình.
- Hiểu rằng sampling của traces và `step` của metrics **không phải cùng một khái niệm**: giảm tỷ lệ sampling tracing không mặc nhiên giảm số điểm metrics.

**Tối ưu đầu tiên:** giảm cardinality không cần thiết, thu hẹp histogram dùng cho nơi cần SLO, và loại metrics không có mục đích rõ ràng. Tăng batch-size chỉ giúp tiết kiệm request ở một số tầng; nó không chữa được việc tạo quá nhiều time series.

## 13. Khi exporter hoặc collector gặp sự cố

Một pipeline metrics có thể gặp những lỗi khác nhau:

| Tình huống | Hậu quả có thể | Cần xem |
| --- | --- | --- |
| OTLP URL sai hoặc Collector không lắng nghe | Ứng dụng vẫn tạo meter nhưng không xuất được đến collector | Config URL/port/protocol, error logs |
| Kết nối bị timeout/chập chờn | Publish chậm, thất bại hoặc bị retry tùy implementation | Latency mạng, retry/backoff, log exporter |
| Collector batch chờ timeout | Có thêm độ trễ hợp lệ trước khi backend nhận | `batch.timeout`, trigger ngưỡng |
| Collector backend bị nghẽn | Queue tích tụ, retry hoặc drop khi vượt giới hạn | Collector self-telemetry, queue/retry policy |
| Pod dừng trong lúc chưa publish | Có nguy cơ mất dữ liệu chưa gửi | Shutdown behavior của registry, termination grace period |
| Backend từ chối quá nhiều series | Mất/giới hạn ingest, dashboard thiếu dữ liệu | Cardinality, quotas, error responses |
| Số series và histogram tăng mạnh | Payload lớn, publish lâu hoặc Collector quá tải | Số meters/tags, histogram buckets, resource usage |
| Prometheus target down | Không scrape được dù ứng dụng đang hoạt động | Targets/up, network, auth, endpoint |
| Prometheus scrape quá thưa | Không thấy biến động rất ngắn của gauge | `scrape_interval`, phù hợp độ phân giải |
| Metrics bình thường nhưng traces thiếu | Tracing exporter, sampling hoặc propagation độc lập | Trace pipeline, `traceparent`, Collector traces |

**Không mặc định thành công chỉ vì `/actuator/metrics` trả dữ liệu.** Endpoint này cho biết registry đang chứa meters; OTLP exporter có thể gửi lỗi ở phía sau. Tương tự, `/actuator/prometheus` có output không đồng nghĩa Prometheus đang scrape target thành công.

### Retry và backpressure

Các exporter có thể có chính sách retry/backoff khác nhau; Collector exporter có thể hỗ trợ sending queue hoặc persistent storage khi được cấu hình phù hợp. Nhưng **không có bảo đảm giao hàng chính xác một lần (exactly once) phổ quát** cho pipeline metrics.

Nếu cần audit số giao dịch không được mất, lưu sự kiện hoặc số liệu vào hệ thống nghiệp vụ có tính bền vững; metrics dành cho quan sát vận hành, không thay thế transaction log.

Khi tăng `batch size` hoặc `step` để giảm tải, phải cân nhắc ảnh hưởng đến **time-to-detect** và khả năng mất dữ liệu tại shutdown. Khi giảm `step` để báo nhanh hơn, phải theo dõi tải serialization, memory, network và Collector.

## 14. Cách kiểm chứng từng chặng của exporter

### 14.1. Kiểm tra registry trong ứng dụng

Với Spring Boot có Actuator:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/orders.processing.duration
~~~

Hãy gọi `OrderProcessingService.processOrder(...)` bằng một workload thử. Nếu metric không có ở Actuator, vấn đề có thể nằm ở code path, registry không đúng, MeterFilter hoặc instrumentation chưa chạy. **Đây chưa phải lỗi step/batch** nếu meter còn chưa được tạo.

### 14.2. Kiểm tra publish OTLP

Dùng một Collector thử nghiệm nhận OTLP và in ra debug logs. Sau khi chạy workload, quan sát:

- App có log lỗi kết nối đến `http://localhost:4318/v1/metrics` không?
- Collector có nhận được metric name, tags và datapoints mong muốn không?
- Lần nhận dữ liệu có tương ứng với chu kỳ `step` đã cấu hình trong điều kiện bình thường không?
- Collector batch có flush vào exporter theo timeout hoặc kích thước không?
- Backend có đang nhận dữ liệu không, và có gap theo timestamp không?

**Cẩn trọng:** vì dữ liệu được gom, một request OTLP không nhất thiết bằng một đơn hàng; không so sánh số OTLP HTTP requests với số order attempts. Hãy kiểm tra **datapoints và thống kê Counter/Timer**, không chỉ đếm request transport.

### 14.3. Kiểm tra Prometheus pull

Khi dùng Prometheus registry:

~~~bash
curl -s http://localhost:8080/actuator/prometheus
~~~

Sau đó kiểm tra target status ở Prometheus và metric `up` hoặc các self-metrics phù hợp. Nếu endpoint trả dữ liệu nhưng target `up=0`, nguyên nhân có thể ở network/path/auth của Prometheus; đổi `step` OTLP sẽ không khắc phục.

### 14.4. Kiểm tra tính đúng của số liệu

Trong môi trường test không có traffic nền, thực thi **100 thao tác thành công**, ghi nhận chênh lệch count theo đúng registry và backend. Nếu có retry hoặc shutdown, kết quả có thể khác; trước khi kết luận lỗi phải xác định có bao nhiêu lần thực thi nghiệp vụ thật và phép đo mang semantics “attempt” hay “logical order”.

Sử dụng một lượng dữ liệu nhỏ, tags hữu hạn và step ngắn vừa đủ để quan sát các lần publish. Không thử gây nghẽn Collector trên môi trường production chỉ để xem queue hoạt động.

## 15. Theo dõi sức khỏe exporter và Collector

Một hệ thống có rất nhiều metrics nghiệp vụ nhưng **không giám sát pipeline telemetry của chính nó** sẽ khó phân biệt ứng dụng không hoạt động với exporter không hoạt động.

Những tín hiệu nên theo dõi (tên metric cụ thể phụ thuộc phiên bản):

- **Số lần export thất bại** và số lần retry tại ứng dụng/registry nếu exporter phát telemetry.
- **Thời gian publish** của mỗi kỳ, đặc biệt khi tiến gần hoặc vượt `step`.
- **Số lượng data points và bytes** theo đợt xuất, để phát hiện bùng nổ cardinality.
- **Queue size/capacity và số dữ liệu bị drop** tại Collector khi có queue.
- **Latency của Collector exporter và tình trạng backend ingest**.
- **Scrape target up/down, scrape duration và số samples** khi dùng Prometheus pull.
- **CPU, memory và GC của ứng dụng/Collector** để kiểm tra overhead do serialization/batch.

Đừng đặt một tên self-metric cố định vào dashboard trước khi xem Collector distribution và cấu hình hiện có: tên có thể khác theo phiên bản, kiểu exporter và self-telemetry. Nên kiểm tra endpoint/self-telemetry của Collector hoặc công cụ monitoring của backend.

### Điều tra qua metrics, logs và tracing

Nếu dashboard thiếu metrics trong 2 phút, hãy so sánh thời điểm thiếu với logs exporter, trạng thái Collector và các spans/request traces của ứng dụng. Một ứng dụng vẫn có thể trả HTTP 200 và tạo tracing spans nhưng đường xuất metrics bị lỗi; chiều ngược lại cũng đúng.

Các đường tín hiệu độc lập có thể giúp xác nhận giả thuyết, song **không suy sampling trace là sampling metric**. Nếu cần exemplar kết nối một điểm metric với trace, stack phải hỗ trợ và cấu hình exemplar; không gắn `traceId` thành tag trên mọi series.

## 16. Tình huống thực tế: chậm metric sau khi giảm lưu lượng export

**Bối cảnh.** Dịch vụ `order-service` chạy 12 instances. Để giảm tải backend, nhóm thay `management.otlp.metrics.export.step` từ `15s` thành `60s`. Đồng thời Collector có `batch.timeout=10s`. Sau đó, dashboard theo dõi số lần checkout cập nhật thưa hơn, và cảnh báo lỗi ít nhạy với sự cố kéo dài 20–30 giây.

**Phân tích:**

1. Code vẫn ghi Timer/Counter trên từng checkout. Đổi step không làm giảm số checkout được instrument.
2. Vì publish thường chỉ xảy ra mỗi 60 giây, một sự kiện ngay sau lần publish có thể phải chờ gần một kỳ đến lần xuất tiếp, rồi tiếp tục qua Collector batch/queue/backend.
3. Nếu Collector nhận một payload đủ lớn, ngưỡng `send_batch_size` có thể khiến nó gửi sớm; nếu không, timeout thêm thời gian chờ. **Batch timeout không thay thế step ở phía ứng dụng**.
4. Dashboard refresh và backend query có thể bổ sung độ trễ.
5. Nếu ứng dụng restart trước kỳ publish tiếp theo, dữ liệu đang trong bộ tổng hợp có thể bị ảnh hưởng theo đặc tính exporter và shutdown.

**Giải pháp có cơ sở:** xác định yêu cầu time-to-detect của cảnh báo. Với alert cần phản hồi trong vòng một phút, cân nhắc giảm step (ví dụ 15–30s sau khi đo tải), điều chỉnh Collector batch/queue và đánh giá chi phí datapoints. Dữ liệu cần truy vết giao dịch chính xác phải được lưu bởi hệ thống nghiệp vụ, không trông chờ tính bền vững của metrics push.

**Kiểm chứng:** dùng workload có số lần và timestamps biết trước, quan sát Actuator, thời điểm Collector nhận, thời điểm backend ingest và thời điểm dashboard hiển thị. Sau đó tính phân bố độ trễ end-to-end thực tế, không chỉ nhìn giá trị `step` trong cấu hình.

## 17. Bài tập thực hành

### Bài tập A — hiểu các mốc thời gian

Ứng dụng sử dụng exporter step 30 giây, Collector batch timeout 5 giây, dashboard refresh 15 giây. Một Counter được tăng tại thời điểm ngay sau lần publish gần nhất.

1. Liệt kê các giai đoạn dữ liệu phải đi qua trước khi thấy trên dashboard.
2. Giải thích vì sao không thể khẳng định **chính xác sau 50 giây** metric sẽ hiển thị.
3. Nếu Collector đạt ngưỡng batch size trước timeout, điều gì có thể thay đổi?
4. Nếu network bị lỗi trong 3 phút, những cơ chế nào cần kiểm tra trước khi nói dữ liệu được giữ lại đầy đủ?

### Bài tập B — cấu hình hai pipeline

Viết cấu hình cho hai môi trường thử nghiệm riêng:

- **Push:** Spring Boot + `micrometer-registry-otlp`, URL Collector `http://localhost:4318/v1/metrics` và step `30s`; Collector có batch processor `timeout=5s`.
- **Pull:** Spring Boot + `micrometer-registry-prometheus` và `/actuator/prometheus`; Prometheus scrape mỗi `15s`.

Giải thích **vì sao đặt `management.otlp.metrics.export.step=10s` không làm Prometheus scrape nhanh hơn**.

### Bài tập C — tính quy mô dữ liệu

Có 6 instances, mỗi instance xuất 2.000 data points trong một kỳ:

1. Với step 30 giây, có khoảng bao nhiêu lần publish/instance/ngày?
2. Ước tính data points/ngày toàn cụm nếu mọi kỳ có 2.000 điểm.
3. Nếu thêm tag chứa `orderId` gần như mới mỗi request, vì sao batch size hoặc network load có thể bùng nổ?
4. Nếu bật 30 histogram buckets cho một số Timer, ước lượng hướng tăng của số data points; không cần giả định mọi exporter có cùng định dạng bucket.

**Đáp án hai câu đầu:** 86.400 / 30 = **2.880 publishes/instance/ngày**; 6 × 2.000 × 2.880 = **34.560.000 data points/ngày** theo giả định đã cho.

### Bài tập D — debug một metric bị mất

Một HTTP service vẫn trả request bình thường. `/actuator/metrics/orders.processing.duration` có COUNT tăng, nhưng backend OTLP không thấy metric mới.

Hãy kiểm tra tuần tự:

1. Registry OTLP đã được thêm và cấu hình vào Spring Boot chưa?
2. URL, port và protocol có khớp Collector receiver không? `localhost` có trỏ đúng nơi nếu chạy Docker/Kubernetes?
3. Có log lỗi khi publish, timeout hoặc mã HTTP từ backend/Collector không?
4. Collector receiver có thấy payload? Batch processor có đang giữ chờ hoặc drop không?
5. Exporter Collector có kết nối backend thành công không; quota/capacity còn không?
6. Temporality và tên metric có đúng cách query của backend không?
7. Đã chờ đủ chu kỳ step, batch timeout và dashboard refresh chưa?

### Bài tập E — kiểm tra tính đúng ngữ nghĩa

Một người viết code vừa dùng `@Observed` vừa dùng `Timer.Sample` thủ công để đo cùng một phương thức. Sau đó tăng `step` từ 30s lên 60s, nhưng số lần xử lý trên dashboard vẫn gấp đôi.

Hãy giải thích vì sao **đổi step không sửa được double instrumentation** và xác định cách chọn một owner đo cho một boundary nghiệp vụ. Nếu cả metrics lẫn tracing cần thiết, nên dùng một Observation với các handlers phù hợp thay vì tạo hai lần observation cùng ý nghĩa.

### Câu hỏi tự kiểm tra

1. Khác biệt giữa lúc `Counter.increment()` và lúc exporter publish là gì?
2. `step` có đồng nghĩa với `scrape_interval` hay không?
3. Batch processor của Collector có tự đặt step cho ứng dụng không?
4. Khi nào size trigger, khi nào timeout trigger việc flush batch?
5. Vì sao một payload OTLP có thể đại diện cho hàng nghìn requests nhưng không chứa hàng nghìn bản ghi request riêng?
6. Temporality delta và cumulative khác nhau thế nào? Có thể suy temporality chỉ từ step không?
7. Batch lớn có tự chữa metric cardinality cao do `requestId` không?
8. Vì sao app Actuator có metrics nhưng backend vẫn có thể thiếu?
9. Trong trường hợp exporter thất bại, có nên mặc định số liệu sẽ được lưu bền vững đến khi mạng hồi phục không?
10. Làm thế nào dùng logs và tracing để kiểm tra ứng dụng vẫn xử lý request khi pipeline metrics không xuất được?

**Tiêu chí hoàn thành:** phân biệt step, publish, batch, scrape interval và temporality; cấu hình được pipeline push OTLP/Collector hoặc pull Prometheus; đọc đúng độ trễ và số data points; kiểm soát cardinality, retry/queue và báo cáo lỗi exporter; không nhầm sampling traces với nhịp metrics.

## 18. Ghi nhớ

- **Step** là nhịp/kỳ xử lý và publish của registry kiểu step. Nó không có nghĩa ứng dụng chỉ cập nhật Counter một lần mỗi kỳ.
- **Batch** là cách gom dữ liệu để vận chuyển hoặc xử lý. Batch trong Collector có timeout/size riêng, không thay thế cấu hình step trong Micrometer.
- **OTLP push** và **Prometheus pull** là hai đường xuất khác nhau. `management.otlp.metrics.export.step` không điều khiển `scrape_interval` của Prometheus.
- **Temporality** (delta/cumulative) và đơn vị phải được kiểm tra tại exporter/backend; không suy ý nghĩa giá trị Counter chỉ từ tên meter hoặc step.
- Step ngắn thường giúp dữ liệu mới đến nhanh hơn nhưng tốn overhead; step dài tiết kiệm lần publish nhưng tăng khả năng phát hiện muộn. Batch lớn có thể giảm request nhưng tăng thời gian chờ/memory.
- **Cardinality và histogram** thường quyết định kích thước payload lớn hơn tối ưu batch đơn lẻ. Giữ metric tags hữu hạn; đặt request ID vào logs/traces thay vì metric labels.
- Quan sát **toàn tuyến**: meter trong ứng dụng → publish → Collector → exporter → backend → dashboard. Có dữ liệu ở Actuator không chứng minh đã export thành công.
- Bảo đảm logging, tracing propagation và sampling được cấu hình riêng. Metrics dùng để phát hiện xu hướng; traces/logs giúp tìm thao tác cụ thể khi điều tra lỗi hoặc độ trễ.

## Tài liệu tham khảo

- [Micrometer Reference — Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer Reference — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [OpenTelemetry Collector — Batch processor](https://github.com/open-telemetry/opentelemetry-collector/tree/main/processor/batchprocessor)
- [OpenTelemetry — Metrics data model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/)
- [Prometheus — Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)

