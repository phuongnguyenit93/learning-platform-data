# Xuất số đo, hoàn tất gửi dữ liệu và vòng đời tiến trình ngắn

Một ứng dụng **Spring Cloud Task** thường chỉ chạy vài giây hoặc vài phút: khởi động Spring Boot, nhận tham số, thực hiện một tác vụ nhập dữ liệu/báo cáo/bảo trì, cập nhật `TaskExecution` rồi thoát. Trong khoảng thời gian ngắn đó, ứng dụng có thể tạo **metrics** qua Micrometer, **traces** qua Micrometer Tracing/OpenTelemetry và **logs**. Nhưng **tạo số đo trong bộ nhớ không đồng nghĩa backend đã nhận được số đo**.

Ví dụ tác vụ `invoice-report-task` kết thúc sau **8 giây**, trong khi một metrics registry có chu kỳ xuất dữ liệu **60 giây**. Kết quả nghiệp vụ và `TASK_EXECUTION.EXIT_CODE` có thể đúng, nhưng dashboard không có biểu đồ cho lần chạy. Nếu tiến trình bị kết thúc đột ngột trước khi exporter gửi lô dữ liệu cuối, một phần metric/span/log cũng có thể bị mất. Vì thế, bài thuộc chương **Quan sát** này tập trung vào **xuất số đo, flush/shutdown và vòng đời tiến trình ngắn**.

Bài giải thích sự khác nhau giữa **TaskRepository, metrics, traces, logs**; lựa chọn cơ chế **pull, push, Prometheus Pushgateway và OTLP**; thiết kế thời điểm hoàn tất trước khi đóng ApplicationContext; cấu hình Spring Boot/Spring Cloud Task; kiểm thử giả lập Task chạy ngắn và quy tắc quan sát đáng tin cậy khi vận hành.

> **Phạm vi phiên bản:** Ví dụ hướng tới Spring Boot 3.x, Spring Cloud Task 3.x và Micrometer tương thích; thuộc tính exporter, dependency và API có thể thay đổi ở phiên bản mới. Luôn dùng BOM tương thích và đối chiếu tài liệu cấu hình cho bản đang chạy. Không có một thuộc tính chung nào bảo đảm “flush mọi metrics, traces và logs thành công” trên tất cả exporter.

## 1. Bốn nguồn thông tin không thay thế nhau

| Nguồn | Lưu gì? | Mục đích | Giới hạn khi Task ngắn |
| --- | --- | --- | --- |
| **TaskRepository** | `TaskExecution`: ID, tên task, thời điểm, đối số, mã thoát, exit message | Xác minh một tiến trình Task đã chạy và kết thúc ra sao | Có thể thiếu kết quả cuối khi Pod bị kill trước khi cập nhật |
| **Metrics** | Counter, Timer, Gauge; ví dụ số bản ghi nhập, thời lượng | Tổng hợp xu hướng, SLO, tỷ lệ thành công, throughput | Exporter định kỳ có thể chưa kịp đẩy; scrape có thể không kịp |
| **Traces** | Span cho Task, runner, JDBC/HTTP và các bước nghiệp vụ | Điều tra độ trễ và quan hệ nhân quả | Batch span processor có thể đang giữ span chưa gửi |
| **Logs** | Sự kiện chi tiết với timestamp, lỗi và correlation ID | Điều tra từng TaskExecution, đối số an toàn, stack trace | Buffer/log agent hoặc Pod bị dọn trước khi thu thập |

**Một TaskExecution `COMPLETED` không chứng minh metrics đã xuất**, và **có metrics không chứng minh TaskRepository được cập nhật thành công**. Muốn vận hành tốt cần liên kết các nguồn, nhưng vẫn biết nguồn nào có thẩm quyền đối với từng loại trạng thái.

Ví dụ dashboard thấy lần chạy tạo 3.200 hóa đơn: số này chỉ có ý nghĩa nếu có **bằng chứng nghiệp vụ** (bảng kết quả, checksum, report ID) và trạng thái Job/Task phù hợp. Metric chỉ hỗ trợ quan sát và cảnh báo, không phải kho lưu kết quả chính.

## 2. Vòng đời một Task và các điểm dễ mất telemetry

~~~mermaid
sequenceDiagram
    participant K as Kubernetes Job / Scheduler
    participant T as Spring Cloud Task
    participant M as Micrometer / OTel SDK
    participant E as Exporter / Collector
    participant R as TaskRepository

    K->>T: Khởi chạy tiến trình Java
    T->>R: Tạo TaskExecution
    T->>M: Bắt đầu observation / counters / spans
    T->>T: Runner xử lý nghiệp vụ
    T->>M: Ghi số đo và đóng các span nghiệp vụ
    T->>R: Cập nhật TaskExecution kết thúc
    T->>M: Đóng context / exporter theo lifecycle
    M-->>E: Gửi batch cuối nếu exporter hỗ trợ và còn thời gian
    T-->>K: Process exit code
~~~

Sơ đồ thể hiện **ý tưởng vòng đời**, không cam kết đúng thứ tự từng callback nội bộ trong mọi phiên bản và mọi exporter. Đặc biệt, observation bao quanh **toàn bộ Task** có thể kết thúc khác thời điểm với observation quanh **runner**; số đo chỉ được chốt khi observation/timer được stop. Nếu flush **trước khi số đo cuối hình thành**, exporter không thể gửi dữ liệu chưa tồn tại.

Các thời điểm quan trọng:

1. **Startup:** Spring Boot dựng context, TaskRepository, ObservationRegistry và MeterRegistry; có thể mất nhiều thời gian hơn chính phần nghiệp vụ.
2. **Runner chạy:** ứng dụng bắt đầu timer, tăng counter, tạo span, ghi log.
3. **Runner hoàn tất:** timer của nghiệp vụ cần được stop; bất đồng bộ phải thực sự hoàn tất trước khi được tính là xong.
4. **Kết thúc Task:** Spring Cloud Task ghi trạng thái `TaskExecution`, gọi các listener liên quan và có thể tạo observation kết thúc.
5. **Đóng context:** exporter/SDK có cơ hội chạy shutdown logic; việc xuất thành công **tùy backend, SDK, deadline và lỗi mạng**.
6. **Tiến trình thoát:** bộ điều phối thấy exit code; telemetry trong bộ nhớ không còn tồn tại.

**Rủi ro cốt lõi:** một `Counter.increment()` trong runner chỉ làm bộ đếm của MeterRegistry thay đổi. Nếu registry xuất định kỳ, có thể chưa một lần nào chạy publish trước khi JVM thoát. `Timer` chỉ có kết quả hoàn chỉnh khi kết thúc đo; `Span` thường chỉ sẵn sàng xuất sau khi `span.end()`.

## 3. Spring Cloud Task cung cấp observation gì?

Spring Cloud Task tích hợp **Micrometer Observation** để đo thời gian thực thi Task và runner. Theo tài liệu observability chính thức, các tên quan sát/metric tiêu biểu là:

| Tên | Loại | Ý nghĩa |
| --- | --- | --- |
| `spring.cloud.task` | Timer | Thời lượng vòng đời TaskExecution |
| `spring.cloud.task.active` | Long Task Timer | Thông tin Task đang chạy trong thời gian observation còn hoạt động |
| `spring.cloud.task.runner` | Timer | Thời lượng một `ApplicationRunner`/`CommandLineRunner` |
| `spring.cloud.task.runner.active` | Long Task Timer | Runner hiện còn đang thực thi |

Về tracing, tài liệu cũng mô tả các span `spring.cloud.task` và `spring.cloud.task.runner` khi có tracing integration. Tên metric hiển thị trên Prometheus hoặc OTLP có thể được **chuyển đổi đơn vị/đặt tên** theo registry; tránh hardcode tên backend mà chưa kiểm tra series thực tế.

Có thể bật observation cho runner ở những phiên bản hỗ trợ:

~~~yaml
spring:
  cloud:
    task:
      observation:
        enabled: true
~~~

Để xuất metrics ra backend, cần ít nhất **`spring-boot-starter-actuator`** và một **Micrometer registry** tương ứng, cùng cấu hình exporter. Để xuất traces, cần thêm **Micrometer Tracing** và bridge/exporter phù hợp. Chỉ đặt cờ `observation.enabled=true` **không tự tạo Collector, dashboard hoặc bộ đẩy telemetry**.

Tài liệu Spring Cloud Task có một số tag như tên task, trạng thái, exit code, task execution ID, parent/external execution ID. Không phải mọi tag đều phù hợp làm chiều của một dashboard tổng hợp vì một số ID thay đổi **sau mỗi lượt chạy**; kiểm tra cardinality thực tế tại registry và backend. Trong metric nghiệp vụ tự định nghĩa, hãy ưu tiên các tag thấp cardinality.

### 3.1. Phân biệt số đo mặc định với số đo nghiệp vụ

Task observation giúp biết một tiến trình mất bao lâu và trạng thái tổng quát. Để theo dõi **nhập bao nhiêu dòng, loại bao nhiêu dòng, đã tạo bao nhiêu báo cáo**, ứng dụng nên tự tạo metric:

- `business.task.records` — số bản ghi đã xử lý, phân loại theo `result=accepted|rejected`.
- `business.task.duration` — Timer cho một thao tác.
- `business.task.outcome` — Counter theo `outcome=success|failure|skipped`.
- `business.task.export.failure` — Counter hoặc log cho lỗi ở đường gửi telemetry (nếu có instrumentation phù hợp).

Những tên trên là **thiết kế ví dụ**, không phải metric mà Spring Cloud Task phát tự động.

## 4. Pull và push: tại sao Task chạy ngắn là trường hợp đặc biệt?

### 4.1. Prometheus pull / scrape

Prometheus thường **scrape** endpoint `/actuator/prometheus` từ một tiến trình đang chạy:

~~~text
Prometheus --(HTTP scrape mỗi 30s)--> /actuator/prometheus
~~~

Với server chạy dài hạn, cách này tự nhiên vì luôn có endpoint hoạt động. Nhưng một Task chạy **8 giây** có thể:

- Kết thúc trước lần scrape đầu tiên.
- Không mở HTTP server do `spring.main.web-application-type=none`.
- Được Kubernetes Job tạo ở một Pod ngắn hạn, chưa kịp được ServiceMonitor/PodMonitor phát hiện.
- Có timer chỉ ghi kết quả vào lúc Task sắp kết thúc; scrape giữa lúc chạy chưa thấy kết quả.

Do đó, **chỉ thêm `micrometer-registry-prometheus` và mở Actuator không đảm bảo quan sát được Task ngắn**. Với task hữu hạn, hãy cân nhắc **push** telemetry hoặc nguồn quan sát dựa trên `TaskRepository`/Kubernetes Job events.

### 4.2. Push metrics qua OTLP hoặc registry tương ứng

Một `OtlpMeterRegistry` có thể đẩy metrics tới **OpenTelemetry Collector** qua HTTP OTLP. Cấu hình ví dụ Spring Boot 3.x:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: "http://otel-collector.monitoring.svc:4318/v1/metrics"
        step: 10s
        connect-timeout: 2s
        read-timeout: 5s
~~~

Thêm dependency phù hợp với BOM:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-otlp</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

**`step` là chu kỳ xuất định kỳ**, không phải cam kết “gửi ngay khi Task kết thúc”. Theo Micrometer OTLP, chu kỳ mặc định thường là **1 phút**. Đặt `10s` có thể giúp ứng dụng sống đủ lâu gửi nhiều lần, nhưng nếu Task chỉ chạy 2 giây, vẫn có khả năng **không có lượt push định kỳ nào**.

Ngoài ra, OTLP exporter chỉ có thể gửi khi Collector reachable, DNS/TLS/auth hợp lệ, mạng thông suốt và exporter thực sự chạy. Một response HTTP thành công từ Collector cũng không nhất thiết có nghĩa backend lưu trữ cuối đã ingest và có thể query ngay; có thể có pipeline/buffer/retry phía Collector.

### 4.3. Prometheus Pushgateway cho service-level batch job

Spring Boot có hỗ trợ tích hợp **Prometheus Pushgateway** cho các tác vụ ngắn, nếu thêm dependency exporter tương ứng và bật:

~~~yaml
management:
  prometheus:
    metrics:
      export:
        pushgateway:
          enabled: true
~~~

Cần có Pushgateway thực sự đang chạy và cấu hình base URL, grouping key, authentication/network phù hợp phiên bản Spring Boot. Pushgateway **không phải** một Prometheus server; nó giữ metrics đã được đẩy để **Prometheus scrape Pushgateway**.

~~~mermaid
flowchart LR
    A["Task chạy 5–20 giây"] -->|Push metrics| P[("Prometheus Pushgateway")]
    S["Prometheus"] -->|Scrape Pushgateway| P
    S --> G["Dashboard / alerts"]
~~~

**Cảnh báo quan trọng từ Prometheus:** Pushgateway là bộ nhớ đệm **tách khỏi vòng đời tiến trình**. Nếu Task kết thúc mà không có chính sách dọn metrics cũ, các series có thể nằm đó vô thời hạn và tạo ảo giác một Job vẫn còn hoạt động. Prometheus khuyến nghị dùng Pushgateway chủ yếu cho **service-level batch jobs**, không dùng như nơi gom metrics tùy tiện của mọi Pod; nên tránh label `pod` hoặc `instance` biến động liên tục trong grouping key.

Một tùy chọn shutdown của Pushgateway có thể là gửi metrics lần cuối hoặc xóa group, tùy phiên bản và cấu hình. **Nếu xóa group ngay khi Task kết thúc, Prometheus có thể chưa kịp scrape**. Do đó không bật shutdown DELETE tùy tiện cho một Task rất ngắn; chọn chính sách gửi và dọn dựa vào ý nghĩa của nhóm metrics, chu kỳ scrape và yêu cầu theo dõi lịch sử.

### 4.4. Bảng lựa chọn exporter

| Hướng xuất | Phù hợp | Lưu ý khi Task ngắn |
| --- | --- | --- |
| Actuator Prometheus pull | Ứng dụng chạy lâu, endpoint tồn tại đủ thời gian | Pod biến mất trước scrape sẽ mất số đo của lần chạy |
| Prometheus Pushgateway | Kết quả **batch job ở mức dịch vụ** với grouping key ổn định | Cần push cuối và dọn series cũ có kiểm soát |
| OTLP push tới Collector | Hạ tầng đã dùng OTel Collector, muốn liên kết metrics/traces/logs | Step/flush/shutdown và thời gian chờ exporter rất quan trọng |
| StatsD hoặc push backend khác | Đã có agent/backend và cơ chế gửi phù hợp | Gửi không đồng nghĩa được lưu; có thể mất gói hoặc buffer |
| TaskRepository + bộ gom trạng thái | Cần kết quả cuối của mỗi lần chạy, kể cả không có HTTP endpoint | Phải truy vấn repository/đối soát với Kubernetes Job |
| Structured logs → log collector | Điều tra từng TaskExecution | Phụ thuộc thu gom, buffer và retention |

**Một hệ thống thực tế thường kết hợp** TaskRepository, logs và một đường metrics/tracing; không nên ép tất cả dữ liệu quan sát qua một cơ chế duy nhất.

## 5. “Đã tạo số đo” khác “đã gửi hoàn tất”

Xét ba giai đoạn:

~~~text
Ứng dụng ghi metric trong bộ nhớ
    → Registry / SDK chuẩn bị lô
    → Transport gửi đến Collector/Pushgateway
    → Backend lưu trữ và query được
~~~

Các mốc thành công khác nhau:

| Mốc | Chứng minh được | Chưa chứng minh được |
| --- | --- | --- |
| `Counter.increment()` đã chạy | Giá trị trong registry tăng | Exporter đã gửi |
| Exporter ghi log “send started” | Có yêu cầu gửi | Bên nhận thành công |
| Transport nhận HTTP 2xx | Đích HTTP đã nhận/xử lý theo giao thức | Toàn pipeline và dashboard đã xuất hiện ngay |
| Collector báo nhận points | Collector ingest bước đầu | Backend sau Collector đã lưu bền vững |
| Dashboard truy vấn được series | Backend đã có dữ liệu ở thời điểm truy vấn | Tất cả lượt chạy trong quá khứ đều không mất |
| TaskRepository ghi `exitCode=0` | Lần chạy Task đã hoàn tất thành công về kỹ thuật | Metrics cũng thành công hoặc nghiệp vụ hoàn toàn đúng |

Vì vậy, **flush** không đồng nghĩa **backend cuối đã lưu bền vững**. Một hệ thống có thể chấp nhận best-effort telemetry; hệ thống kiểm toán nghiêm ngặt nên lấy bảng nghiệp vụ/TaskRepository làm nguồn dữ liệu có thẩm quyền.

### 5.1. Cơ chế ForceFlush và Shutdown trong OpenTelemetry

Theo đặc tả OpenTelemetry:

- `forceFlush` trên `TracerProvider` yêu cầu đẩy các **span đã hoàn tất** còn được giữ trong processors.
- `forceFlush` trên `MeterProvider` với push readers yêu cầu thu thập và xuất metrics trong khả năng của exporter.
- `shutdown` yêu cầu dọn tài nguyên và thường bao gồm flush theo ngữ nghĩa SDK; cần có **timeout và kiểm tra kết quả**.
- Với exporter kiểu **pull**, ForceFlush không thay thế việc Prometheus scrape endpoint.

Các API cụ thể phụ thuộc SDK và cách Spring Boot tự cấu hình. **Không tự tạo một OpenTelemetry SDK thứ hai** trong ứng dụng đã được Spring Boot/agent quản lý chỉ để gọi `forceFlush`; có thể dẫn tới duplicate spans/metrics hoặc hai bộ resource attributes không nhất quán.

Nếu ứng dụng **sở hữu trực tiếp** `SdkTracerProvider` hoặc `SdkMeterProvider`, có thể chủ động gọi `forceFlush` theo API của phiên bản SDK và **đợi kết quả với deadline hữu hạn** trước khi đóng SDK. Nếu Spring Boot/Micrometer quản lý exporter, ưu tiên lifecycle của context và cơ chế flush/shutdown mà **registry cụ thể** hỗ trợ; kiểm thử ngay trên bản dependency thực tế.

### 5.2. Tránh flush quá sớm

Một nhầm lẫn là flush **ngay trong runner** trước khi phương thức `run()` trả về, rồi cho rằng đã gửi toàn bộ metric của Task.

~~~text
Runner bắt đầu
  → ứng dụng tạo Counter
  → gọi flush trong run()
  → runner trở về
  → observation spring.cloud.task.runner được stop
  → TaskExecution được cập nhật
  → observation spring.cloud.task có thể mới được hoàn tất
~~~

Với trình tự này, flush sớm **không thể gửi Timer của runner/Task vẫn chưa stop**. Chiến lược đúng là để **đối tượng quan sát kết thúc trước**, rồi sử dụng cơ chế final export ở thời điểm shutdown mà exporter hỗ trợ. Đối với metric nghiệp vụ tạo trong runner, có thể kiểm thử riêng một mốc gửi sớm, nhưng nó không thay thế final export sau Task lifecycle.

## 6. ApplicationContext và thời gian kết thúc tiến trình

Trong Spring Cloud Task, có thể dùng:

~~~yaml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      closecontext-enabled: true
~~~

`spring.cloud.task.closecontext-enabled=true` yêu cầu Spring Cloud Task **đóng ApplicationContext sau khi tác vụ hoàn tất**, giúp tài nguyên/threads được dọn và tiến trình có thể kết thúc. Nó có thể giúp các bean exporter tham gia **destroy callbacks** khi context đóng.

**Nhưng đây không phải lệnh “forceFlush tất cả exporter thành công”.** Registry/SDK có thể:

- Gửi dữ liệu khi đóng hoặc chỉ ngừng scheduler nội bộ, tùy implementation.
- Có timeout thấp hơn thời gian mạng cần để gửi.
- Báo lỗi mà không làm Task thất bại, nếu telemetry là best-effort.
- Chưa có số đo cuối nếu lifecycle của observation và destroy callback không được phối hợp đúng.

Không được dùng `Thread.sleep(60000)` như một giải pháp chung chỉ để đợi `step=60s`: nó tăng chi phí Job, giữ tài nguyên và vẫn không bảo đảm một lần xuất thành công. Cần kiểm chứng **cơ chế close/flush của exporter thật**, hoặc thiết kế một đường xuất phù hợp với short-lived process.

### 6.1. Công việc bất đồng bộ phải kết thúc trước khi Task thoát

Ví dụ **không an toàn**:

~~~java
@Bean
ApplicationRunner unsafeRunner(ExecutorService executor) {
    return args -> {
        executor.submit(() -> generateReport()); // Runner trả về ngay.
    };
}
~~~

Nếu runner trả về ngay, Spring Cloud Task có thể coi công việc xong trong khi thread xử lý còn chạy. Context đóng có thể chặn/interrupt thread; thời lượng Task và số bản ghi xử lý trở nên sai.

Ví dụ an toàn hơn:

~~~java
@Bean
ApplicationRunner safeRunner(ExecutorService executor) {
    return args -> {
        Future<?> result = executor.submit(() -> generateReport());
        result.get(); // Chờ, đồng thời đưa exception về runner.
    };
}
~~~

Ví dụ cần bean `ExecutorService`, phương thức `generateReport()`, quản lý shutdown executor và xử lý interrupt phù hợp. **Không chờ vô hạn** trong sản xuất: đặt deadline nghiệp vụ, hủy tác vụ an toàn và trả mã thoát lỗi khi timeout.

## 7. Ví dụ thực hành: ghi Counter và Timer qua Micrometer

Giả sử một Task nhập dữ liệu theo ngày. Ta muốn đo:

- Số bản ghi **thành công/từ chối**.
- Thời lượng xử lý của runner.
- Kết quả cuối **success/failure** theo category có số lượng giá trị nhỏ.

Một `ApplicationRunner` có thể dùng `MeterRegistry` do Spring Boot inject:

~~~java
import java.time.LocalDate;
import java.util.List;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ImportMetricsConfiguration {

    @Bean
    ApplicationRunner importRunner(
            MeterRegistry registry, ImportService importer) {

        return args -> {
            LocalDate date = requiredDate(args);
            Timer.Sample sample = Timer.start(registry);
            String outcome = "failure";

            try {
                ImportResult result = importer.importFor(date);

                registry.counter(
                        "business.task.records",
                        "result", "accepted").increment(result.accepted());
                registry.counter(
                        "business.task.records",
                        "result", "rejected").increment(result.rejected());

                outcome = "success";
            } finally {
                sample.stop(registry.timer(
                        "business.task.duration",
                        "operation", "import"));

                registry.counter(
                        "business.task.outcome",
                        "operation", "import",
                        "outcome", outcome).increment();
            }
        };
    }

    private static LocalDate requiredDate(ApplicationArguments args) {
        List<String> values = args.getOptionValues("business-date");
        if (values == null || values.size() != 1) {
            throw new IllegalArgumentException(
                    "Expected --business-date=yyyy-MM-dd");
        }
        return LocalDate.parse(values.get(0));
    }
}

interface ImportService {
    ImportResult importFor(LocalDate businessDate);
}

record ImportResult(long accepted, long rejected) {}
~~~

Mẫu này minh họa **cách ghi số đo**, không tự cấu hình exporter. Ứng dụng thật cần bean `ImportService` và cấu hình Spring Boot/Micrometer/TaskRepository. Phần xử lý là **đồng bộ**. Khi importer ném exception, `finally` vẫn ghi Timer và counter `failure`, rồi exception tiếp tục truyền ra để Task/Kubernetes biết lỗi.

**Giới hạn:** nếu exception xảy ra tại `requiredDate(args)` **trước** `try`, các meter nghiệp vụ trong ví dụ chưa được ghi. Nếu muốn đo cả lỗi validation, chuyển bước parse vào vùng `try/finally` và đặt outcome phù hợp. Với tiến trình bị kill bằng `SIGKILL`, `finally` cũng không có bảo đảm chạy.

### 7.1. Vì sao không dùng taskExecutionId làm metric tag?

Không nên ghi:

~~~java
registry.counter(
        "business.task.outcome",
        "taskExecutionId", "4101",
        "tenantId", "tenant-" + dynamicTenantId);
~~~

Mỗi TaskExecution ID và nhiều tenant sẽ tạo **time series mới**; chi phí lưu trữ và truy vấn có thể tăng rất nhanh. Với metrics tổng hợp, dùng các tag ít giá trị như `operation=import`, `outcome=success|failure`, `environment=prod`. Đưa TaskExecution ID vào **log, trace hoặc bảng metadata** để tra cứu chi tiết.

### 7.2. Lưu số liệu nghiệp vụ theo nguồn có thẩm quyền

Nếu kết quả `accepted=980, rejected=20` cần đối soát/hạch toán, không chỉ `counter.increment(980)`. Nên lưu thông tin vào bảng nghiệp vụ, ví dụ:

~~~sql
CREATE TABLE import_run (
    source_id       varchar(120) NOT NULL,
    business_date   date NOT NULL,
    status          varchar(30) NOT NULL,
    accepted_count  bigint NOT NULL DEFAULT 0,
    rejected_count  bigint NOT NULL DEFAULT 0,
    completed_at    timestamptz,
    PRIMARY KEY (source_id, business_date)
);
~~~

Bảng trên là mô hình tối giản; ứng dụng cần transaction, trạng thái `RUNNING/FAILED/COMPLETED` và chính sách retry/claim an toàn. Metric là **bản sao để quan sát**, không thay thế bảng kết quả khi cần tính đúng và khả năng phục hồi.

## 8. Đóng exporter: phối hợp với Spring Boot, Micrometer và OTel

Một ứng dụng có thể sử dụng **Micrometer MeterRegistry** để phát metrics và **Micrometer Tracing** dùng bridge OTel để phát traces. Dù cùng thuộc observability, **quy trình xuất của metrics và traces có thể khác nhau**:

| Thành phần | Bộ đệm thường gặp | Khi nào dữ liệu sẵn sàng? | Cách kết thúc cần xem xét |
| --- | --- | --- | --- |
| `Timer` Micrometer | MeterRegistry aggregation | Khi stop timer/sample | Final publish hoặc close registry nếu implementation hỗ trợ |
| `Counter` Micrometer | Số đo trong registry | Ngay khi tăng số đếm | Publish bước cuối trước khi thoát nếu exporter hỗ trợ |
| `LongTaskTimer` | Trạng thái tác vụ đang hoạt động | Khi đang chạy, qua scrape/publish | Task ngắn có thể kết thúc trước lần thu thập |
| OTel `Span` | BatchSpanProcessor | Khi span kết thúc | ForceFlush/Shutdown của SDK được quản lý |
| App logs | Buffer logger/collector | Khi log được append | Logback/Log4j shutdown + thu gom stdout |
| TaskRepository | JDBC transaction | Sau khi repository cập nhật và commit | DB kết nối ổn định, không bị kill trước callback kết thúc |

**Đừng đóng MeterRegistry bên trong `ApplicationRunner`** nếu Spring còn đang tạo observation liên quan đến runner/Task. Nó có thể khiến observation cuối không được xuất hoặc khiến những bean khác dùng một registry đã đóng.

**Đừng gọi `System.exit(0)` đột ngột ngay sau khi tăng counter**, bỏ qua cơ chế đóng context và destroy hooks. Việc sử dụng Spring Boot lifecycle phải có đường kết thúc rõ ràng, cùng timeout hợp lý cho exporter.

Nếu phải **tự quản lý OTel SDK** (không phải SDK do Spring/agent tạo), luồng khái niệm là:

~~~text
1. Dừng tạo công việc mới; chờ mọi Future/Step hoàn tất.
2. Kết thúc các span/observations đang mở.
3. Gọi forceFlush trên các provider có hỗ trợ.
4. Đợi kết quả với timeout hữu hạn; ghi nhận lỗi.
5. Gọi shutdown/close để giải phóng tài nguyên.
6. Kết thúc tiến trình với exit code theo kết quả nghiệp vụ.
~~~

**Cần dùng API đúng phiên bản** của `SdkTracerProvider`, `SdkMeterProvider` hoặc registry cụ thể; đoạn trên không phải mã Java có thể chạy trực tiếp. Trong ứng dụng Spring Boot auto-configured, thường để **ApplicationContext quản lý vòng đời** và kiểm tra callback shutdown/behavior của exporter trước khi thêm flush thủ công.

### 8.1. Không để shutdown block vô hạn

Một Collector chết hoặc network timeout dài có thể khiến tiến trình giữ Pod quá lâu. Thiết kế hạn mức thời gian:

~~~text
Tổng thời gian Job tối đa  =  15 phút
Ngân sách cho nghiệp vụ    =  14 phút
Ngân sách shutdown/telemetry = 20 giây
Biên dự phòng Kubernetes   =  40 giây
~~~

Đây là phân bổ ví dụ, không phải mặc định. Nếu Kubernetes Job bị kill bởi `activeDeadlineSeconds` hoặc Pod không đủ `terminationGracePeriodSeconds`, quá trình flush có thể bị cắt giữa chừng. Ngược lại, đặt timeout quá dài cho telemetry có thể làm một tác vụ nghiệp vụ thành công bị Job coi là lỗi chỉ vì hệ thống quan sát không phản hồi.

**Chính sách lỗi cần tường minh:** nếu telemetry là best-effort, thất bại xuất metrics nên được ghi cảnh báo, không tự biến giao dịch nghiệp vụ thành thất bại. Nếu có yêu cầu kiểm toán bắt buộc, lưu kết quả vào CSDL/outbox bền vững rồi đồng bộ sang backend; đừng phụ thuộc vào lệnh flush trong JVM như cam kết giao hàng chính xác một lần.

## 9. Kubernetes: Pod có thể bị dừng trước khi số đo ra ngoài

Kubernetes CronJob/Job có thể tạo một Pod mỗi lượt chạy và dọn Pod cũ theo retention. Các tình huống phổ biến:

- **Container exit bình thường:** context shutdown có cơ hội chạy; backend vẫn có thể mất metric nếu exporter không flush.
- **SIGTERM:** ứng dụng có một khoảng graceful shutdown, nhưng phải có hook/logic đóng phù hợp và hoàn tất trong thời hạn.
- **SIGKILL/OOM:** process không chạy shutdown hooks, không thể tin `finally`, exporter hay TaskRepository sẽ cập nhật cuối.
- **Eviction/node failure:** Pod có thể chết trong lúc xuất telemetry hoặc trước khi log collector đọc xong.
- **Image pull/config failure:** ứng dụng chưa chạy, nên **không có TaskExecution và metric nghiệp vụ**; chỉ còn tín hiệu Kubernetes.

Manifest minh họa:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: invoice-report-observability-test
spec:
  backoffLimit: 1
  activeDeadlineSeconds: 900
  template:
    spec:
      restartPolicy: Never
      terminationGracePeriodSeconds: 40
      containers:
        - name: task
          image: registry.example.com/batch/invoice-report-task:1.0.0
          args:
            - "--business-date=2026-11-23"
          env:
            - name: OTEL_SERVICE_NAME
              value: "invoice-report-task"
            - name: TASK_DB_URL
              valueFrom:
                secretKeyRef:
                  name: invoice-task-db
                  key: jdbc-url
            - name: TASK_DB_USER
              valueFrom:
                secretKeyRef:
                  name: invoice-task-db
                  key: username
            - name: TASK_DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: invoice-task-db
                  key: password
~~~

Manifest này **chưa chỉ định OTLP Collector URL và credentials**, và giả định image có cấu hình liên quan; cần cấu hình `management.otlp.metrics.export.url` trong ứng dụng hoặc biến môi trường tương ứng. Secret phải được tạo trước. Trường `terminationGracePeriodSeconds` không đảm bảo có 40 giây khi Job đã vượt các giới hạn khác hoặc Pod chết không graceful.

Khi dùng exporter push qua HTTP, cần xác minh **DNS/network policy/TLS/auth** từ namespace của Job tới Collector/Pushgateway. Một cổng mở trên laptop không chứng minh Pod truy cập được endpoint này.

## 10. Kiểm chứng dữ liệu thực sự đến backend

Không kết luận thành công chỉ vì trong code đã gọi `Counter.increment()`. Thực hiện thử nghiệm có thể lặp lại:

### 10.1. Thiết lập thử nghiệm

1. Dùng môi trường thử nghiệm với Collector/Pushgateway hoặc backend có khả năng tra cứu metrics.
2. Cấu hình đúng registry, endpoint, authentication và service name.
3. Cho Task chạy **ngắn hơn một chu kỳ export** (ví dụ 5 giây so với `step=60s`).
4. Ghi một counter và timer, đồng thời lưu `TaskExecution ID` và `businessDate` trong log/bảng nghiệp vụ.
5. Đợi backend xử lý theo SLA ingest của hạ tầng, rồi tìm metric theo `service.name`, `operation`, `outcome`, thời điểm.
6. Quan sát log exporter và lỗi timeout; không chỉ xem dashboard tổng hợp.
7. Thử đường shutdown bình thường và trường hợp gửi thất bại để xác định chính sách lỗi.

### 10.2. Ma trận kiểm chứng

| Kịch bản | Thao tác | Điều phải kiểm tra |
| --- | --- | --- |
| **A. Nhanh hơn chu kỳ xuất** | Task 5s, OTLP `step=60s` | Có thể chưa xuất trước exit; cần chứng minh exporter shutdown có gửi được |
| **B. Thời gian đủ dài** | Task 70s, OTLP `step=10s` | Backend nhận nhiều lượt xuất nhưng kết quả cuối vẫn cần kiểm chứng |
| **C. Mất mạng lúc kết thúc** | Chặn kết nối Collector trước shutdown | Exporter báo lỗi/timeout; Task có giữ đúng outcome nghiệp vụ? |
| **D. Collector nhận rồi backend chậm** | Quan sát pipeline có buffering | Không kết luận backend hỏng chỉ vì dashboard chưa thấy ngay |
| **E. Timer chưa stop** | Đặt flush trước khi runner về | Metric duration cuối có thể thiếu |
| **F. SIGTERM** | Cho Job nhận graceful shutdown | Có thời gian đóng context, nhưng phải đo timeout thực tế |
| **G. SIGKILL/OOM** | Dừng process đột ngột trong môi trường test | Không có bảo đảm final flush và `END_TIME` |
| **H. Pushgateway stale series** | Task push rồi không chạy lượt tiếp theo | Metrics tồn tại cho đến khi có cơ chế dọn; không xem đó là Task đang chạy |
| **I. Retry** | Cho Job fail rồi retry cùng business key | Không cộng số đo như thể hai lượt là hai báo cáo thành công nếu nghiệp vụ chỉ hoàn tất một lần |
| **J. Backend off nhưng nghiệp vụ đúng** | Tắt exporter/Collector ở môi trường test | Đối soát `TaskExecution`, bảng nghiệp vụ và policy best-effort |

**Tiêu chí đạt:** giải thích được sự khác nhau giữa số đo trong bộ nhớ, lời gọi xuất, dữ liệu Collector nhận và series đã có ở backend; tái hiện được Task rất ngắn; chứng minh kết quả Task không phụ thuộc ngẫu nhiên vào chu kỳ scrape.

## 11. Giám sát Task chạy theo lịch và retry

Một CronJob chạy hằng ngày có ba loại lỗi cần báo động:

1. **Không được chạy:** CronJob bị suspend, missed schedule, image pull lỗi, thiếu Pod. Lúc này **không có metric trong ứng dụng Task**; cần quan sát Kubernetes CronJob/Job và lịch kỳ vọng.
2. **Chạy rồi thất bại:** TaskExecution có exit code khác `0` hoặc Spring Batch JobExecution FAILED, kèm Pod fail; backend metrics có thể thiếu nếu exporter không flush.
3. **Báo thành công nhưng nghiệp vụ thiếu dữ liệu:** Task/Job exit code `0` nhưng báo cáo chưa có hoặc số dòng không khớp; cần đối soát bảng nghiệp vụ/artifact.

**Không dùng “không có metric” như một tín hiệu duy nhất để kết luận Task chưa chạy.** Nó có thể đã chạy và hoàn thành trước scrape, hoặc Collector đã lỗi. Tương tự, metric `last_success` nằm trong Pushgateway có thể **cũ**, không chứng minh lịch hôm nay đã chạy.

Một dashboard tốt có thể kết hợp:

| Chỉ số/câu hỏi | Nguồn ưu tiên |
| --- | --- |
| Có Job theo lịch hôm nay không? | Kubernetes CronJob/Job hoặc scheduler |
| Task đã khởi động và kết thúc chưa? | TaskRepository `TASK_EXECUTION` |
| Lần nào thất bại? | Exit code, Pod status, log, JobRepository nếu có Batch |
| Xử lý bao nhiêu dòng, có trùng không? | Bảng nghiệp vụ/checksum/unique key |
| Thời lượng trung vị/p95 của các lần hoàn tất | Metrics timer, được xuất thành công |
| Độ trễ của exporter hoặc lỗi gửi telemetry | Exporter logs, Collector metrics, pipeline health |

### 11.1. Truy vấn TaskRepository để đối soát

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'invoice-report-task'
ORDER BY START_TIME DESC;
~~~

Nếu Task bị kill, `END_TIME IS NULL` **không chứng minh nó vẫn còn chạy**. Phải đối chiếu Pod/Job và giờ chạy. Nếu tài khoản chỉ có quyền read TaskRepository, dùng kết quả này cùng log; không tự sửa metadata để làm dashboard hiện xanh.

### 11.2. Định danh xuyên các tầng

Dùng correlation ID có thể truy vết:

~~~text
Kubernetes Job name/UID
   ↔ TaskExecution ID
   ↔ Spring Batch JobExecution ID (nếu có)
   ↔ businessKey = (tenantId, businessDate, reportVersion)
   ↔ traceId/spanId
~~~

**Không** đặt mọi ID thành Micrometer metric tag. Giữ correlation ID trong structured log và tracing; với metrics chỉ dùng các dimensions ổn định như tên task, môi trường, operation, status. Cần tránh thông tin cá nhân, tenant ID quy mô lớn, token, filename bí mật và dữ liệu nguồn trong labels/attributes.

## 12. Những sai lầm thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `TaskExecution` có dữ liệu, metrics không có | Registry chỉ nằm trong bộ nhớ, không có exporter hoặc Task ngắn hơn export step | Kiểm tra dependency, `management.*.export`, shutdown/publish |
| Prometheus không scrape được Pod | Task chạy xong nhanh, không có HTTP server, discovery chậm | Dùng push thích hợp hoặc giám sát repository/scheduler |
| Backend thấy vài lần push nhưng không thấy duration cuối | Timer/Task observation chưa stop khi publish | Đảm bảo đóng observation trước final export |
| `step=10s` vẫn mất metric khi Task chỉ 2s | Không đến chu kỳ xuất định kỳ | Đừng dựa vào `step` thay cho cơ chế final flush/shutdown |
| JVM không thoát vì exporter/thread | Thread không daemon hoặc context chưa đóng | Kiểm tra `closecontext-enabled`, lifecycle bean, timeout |
| Pod bị kill trong lúc push | Job deadline/termination grace quá ngắn, hạ tầng lỗi | Giới hạn và kiểm thử timeout; dùng nguồn dữ liệu bền vững |
| Trace thiếu span cuối | BatchSpanProcessor chưa flush, span chưa end hoặc SDK đóng sớm | Kiểm tra end/forceFlush/shutdown theo SDK thực tế |
| Pushgateway luôn thấy `success=1` từ hôm qua | Series tồn tại sau Task exit | Quản lý grouping key, stale cleanup, timestamp kỳ vọng |
| Metrics đột biến nhiều series | Tag chứa TaskExecution ID, Pod UID, tenant không giới hạn | Giảm cardinality, chuyển ID sang log/traces |
| Task báo success dù import lỗi | Exception bị nuốt hoặc Batch failure không phản ánh exit code | Sửa xử lý lỗi; đối soát nghiệp vụ/TaskRepository |
| Không có metrics vì Task không khởi động | Image pull/config/DB lỗi trước khi Micrometer được tạo | Xem Pod events/Job status và startup logs |
| Exporter down làm Task treo | Retry/timeout quá lớn khi shutdown | Đặt deadline và policy best-effort rõ ràng |

## 13. Quy tắc thiết kế cho production

- **Đo kết quả có ý nghĩa:** duration, records, retry, outcome; không dùng metrics thay cho nguồn dữ liệu kiểm toán.
- **Chọn đường xuất phù hợp:** pull cho service sống lâu; push/Pushgateway/Collector cho batch chạy ngắn trong đúng phạm vi.
- **Hiểu chu kỳ:** Task 5 giây với exporter step 60 giây có thể không gửi được lần nào trước exit.
- **Hoàn tất trước khi đóng:** chờ I/O nghiệp vụ, commit transaction, stop timer/span, cập nhật TaskRepository, rồi cho lifecycle exporter đóng/flush.
- **Kiểm soát shutdown:** timeout hữu hạn, `terminationGracePeriodSeconds` và Job deadline hợp lý; không dùng sleep tùy ý như cách đảm bảo telemetry.
- **Phân biệt policy lỗi:** metrics/traces thường best-effort, còn kết quả nghiệp vụ cần bền vững; nếu telemetry là bắt buộc, hãy thiết kế outbox/reconciliation thay vì đặt niềm tin vào bộ nhớ JVM.
- **Không lộ bí mật:** auth exporter qua Secret; không ghi password vào CLI, metric tags hoặc log.
- **Tránh cardinality cao:** TaskExecution ID, Pod UID, request ID thuộc logs/traces hoặc metadata.
- **Giám sát sự vắng mặt:** missed CronJob không tạo metric nội bộ; dùng scheduler/Job status và kiểm tra kỳ vọng.
- **Kiểm chứng backend:** sau Task exit, kiểm tra metrics/traces/logs tại điểm nhận cuối; đừng dừng ở việc bean MeterRegistry tồn tại.

## 14. Bài tập tự đánh giá

Một tác vụ `daily-settlement-task` chạy **7 giây** mỗi đêm bằng Kubernetes CronJob. Ứng dụng ghi `business.task.outcome{outcome="success"}`, `business.task.duration` và các span của một lời gọi HTTP; TaskRepository có mã thoát `0`. Hạ tầng dùng Micrometer OTLP với `step=60s`.

1. Giải thích vì sao TaskRepository có dòng thành công nhưng dashboard không thấy metrics.
2. Nếu đổi `step` từ `60s` thành `10s`, liệu đã bảo đảm một lần gửi khi Task chỉ 7 giây chưa? Vì sao?
3. Vẽ thứ tự cần có giữa kết thúc xử lý nghiệp vụ, stop timer/span, đóng context và exporter flush.
4. Phân biệt `spring.cloud.task.closecontext-enabled` với `forceFlush` của OTel SDK.
5. Chọn giữa Prometheus scrape, Pushgateway, OTLP Collector và truy vấn TaskRepository. Giải thích lựa chọn theo yêu cầu giám sát.
6. Nếu Pod bị SIGKILL ở giây thứ 6, số đo và TaskExecution có thể ở trạng thái nào?
7. Một Pushgateway có series thành công từ hôm qua, nhưng CronJob hôm nay không tạo Job: làm sao phát hiện lịch bị bỏ lỡ?
8. Đề xuất các tag low-cardinality cho metrics và nơi lưu `TaskExecution ID`, `traceId` để điều tra.
9. Thiết kế test giả lập Collector outage để kiểm tra policy lỗi: telemetry hỏng không được làm sai kết quả nghiệp vụ.
10. Nếu yêu cầu kiểm toán bắt buộc đủ 100% lần chạy, vì sao phải dùng bảng bền vững/outbox thay cho chỉ counter trong Micrometer?

**Đáp án định hướng:** metric được ghi trong JVM nhưng exporter push định kỳ chưa kịp chạy; `step=10s` vẫn dài hơn một Task 7 giây. Cần kết thúc metric/span trước khi exporter gửi cuối, đồng thời kiểm chứng shutdown của implementation cụ thể. TaskRepository/Job status và bảng nghiệp vụ là nguồn đáng tin cậy để đối soát; telemetry giúp quan sát, không thay thế tính đúng dữ liệu.

## 15. Tổng kết

1. **Vòng đời ngắn là đặc tính thiết kế của Spring Cloud Task**, không phải lỗi. Observability phải được thiết kế cho tiến trình có thể biến mất trước lần scrape/push.
2. **Ghi metric ≠ gửi metric ≠ backend đã lưu metric.** Cần kiểm tra từng ranh giới.
3. Spring Cloud Task có observations về Task/runner; muốn xuất metrics/traces cần Actuator, registry/tracing exporter và Collector/backend phù hợp.
4. **Chu kỳ `step` không đảm bảo final export.** Với Task ngắn, cần cơ chế push cuối/close/flush được hỗ trợ và kiểm thử thực tế.
5. **`closecontext-enabled` không phải nút “forceFlush tất cả”.** Nó đóng context và hỗ trợ lifecycle, còn bảo đảm gửi phụ thuộc registry/SDK, transport và timeout.
6. Đừng đóng exporter **trước khi** runner/Task observation kết thúc; đừng giữ process sống vô hạn chỉ để chờ một chu kỳ gửi.
7. Với Prometheus Pushgateway, quản lý **grouping key và stale series**; với OTLP, kiểm soát **chu kỳ, deadline, Collector và pipeline**.
8. **Metrics là tín hiệu quan sát**, còn TaskRepository, Kubernetes Job và bảng nghiệp vụ xác định việc thực thi và tính đúng kết quả.
9. Luôn kiểm thử **normal exit, timeout, SIGTERM/SIGKILL, outage của exporter và retry** trước khi đưa Task ngắn vào production.

### Tài liệu tham khảo chính thức

- [Spring Cloud Task — Observability](https://docs.spring.io/spring-cloud-task/reference/observability.html)
- [Spring Cloud Task — Features và Enable Task Metrics](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Boot — Actuator Metrics (OTLP, Prometheus, Pushgateway)](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer — OTLP Metrics Registry](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html)
- [OpenTelemetry Specification — Metrics SDK ForceFlush, Shutdown](https://opentelemetry.io/docs/specs/otel/metrics/sdk/)
- [OpenTelemetry Specification — Tracing SDK ForceFlush, Shutdown](https://opentelemetry.io/docs/specs/otel/trace/sdk/)
- [Prometheus — When to use the Pushgateway](https://prometheus.io/docs/practices/pushing/)
