# Phân biệt xuất metrics OTLP với xuất trace OTLP

## 1. Cùng một giao thức, hai loại câu hỏi khác nhau

Khi thấy cả `/v1/metrics` và `/v1/traces` cùng nằm trên một Collector, rất dễ nghĩ rằng chỉ cần bật “OTLP” là ứng dụng tự gửi đủ mọi dữ liệu. Muốn cấu hình đúng, cần tách **loại dữ liệu được tạo ra** khỏi **giao thức dùng để chuyển dữ liệu**.

**Metrics** là các phép đo số được tổ chức theo tên, thời gian và tập thuộc tính. Chúng giúp trả lời câu hỏi tổng thể: tốc độ xử lý là bao nhiêu, tỷ lệ lỗi có tăng không, bộ nhớ đang dùng bao nhiêu, thời gian xử lý phân bố thế nào?

**Trace** là dấu vết của một lần thực thi, có thể đi qua nhiều dịch vụ. Một trace gồm các **span**; mỗi span mô tả một hoạt động với thời điểm bắt đầu/kết thúc, định danh và quan hệ với hoạt động khác. Trace giúp điều tra một lần xử lý cụ thể: yêu cầu này đi qua đâu, bước nào chậm, thao tác nào gây lỗi?

| Tiêu chí | Metrics | Trace |
| --- | --- | --- |
| Đơn vị quan sát | Điểm dữ liệu số, bộ đếm, phân phối hoặc giá trị tức thời | Span thuộc một trace |
| Góc nhìn thường dùng | Tập hợp hoạt động theo thời gian | Một lần thực thi và quan hệ giữa các hoạt động |
| Ví dụ | Số yêu cầu, lượng bộ nhớ, phân phối thời gian xử lý | Span server nhận yêu cầu, span client gọi dịch vụ khác |
| Khóa để phân tích | Tên metric và tập thuộc tính | Trace ID, Span ID, quan hệ cha–con và thuộc tính |
| Câu hỏi điển hình | “Tỷ lệ lỗi 5 phút vừa qua là bao nhiêu?” | “Yêu cầu bị lỗi này thất bại ở bước nào?” |

Ví dụ giả định có ba thao tác kéo dài 10, 20 và 90 ms:

- Một timer có thể ghi nhận tổng số là 3 và tổng thời gian là 120 ms; từ đó tính được trung bình 40 ms.
- Các span tương ứng có thể giữ thông tin từng thao tác và quan hệ của chúng trong các trace.
- Chỉ biết trung bình 40 ms không đủ để tái tạo thời gian và đường đi của từng yêu cầu.
- Có một vài trace chậm cũng chưa đủ để kết luận tỷ lệ chậm của toàn bộ lưu lượng nếu chưa hiểu cách lấy mẫu.

Metrics và trace bổ sung cho nhau. Cần xem tỷ lệ lỗi tăng ở nhóm dịch vụ nào bằng metrics, rồi điều tra những lần thực thi liên quan bằng trace. Khái niệm dữ liệu được trình bày trong tài liệu OpenTelemetry về [metrics](https://opentelemetry.io/docs/concepts/signals/metrics/) và [traces](https://opentelemetry.io/docs/concepts/signals/traces/).

## 2. OTLP không phải công tắc bật mọi tín hiệu

OTLP là **OpenTelemetry Protocol**, giao thức truyền dữ liệu quan sát. Cùng một họ giao thức có các kiểu thông điệp cho từng tín hiệu (signal).

Với OTLP/HTTP, các đường dẫn mặc định là:

| Tín hiệu | Đường dẫn mặc định | Kiểu yêu cầu |
| --- | --- | --- |
| Metrics | `/v1/metrics` | `ExportMetricsServiceRequest` |
| Traces | `/v1/traces` | `ExportTraceServiceRequest` |

Cả hai dùng HTTP POST, nhưng nội dung có cấu trúc riêng. Đổi đuôi URL không chuyển một lô metrics thành các span. Một receiver có thể hỗ trợ cả hai, nhưng vẫn phải xử lý đúng tín hiệu.

OTLP còn có phương thức truyền bằng gRPC. Cổng thường dùng cho HTTP là 4318, cho gRPC là 4317. Đó là mặc định theo giao thức, không phải bằng chứng rằng cổng đang mở trên hệ thống thực tế. Ví dụ trong bài dùng **OTLP/HTTP**; không thay 4318 thành 4317 rồi giữ nguyên cấu hình bộ gửi HTTP.

Các đường dẫn và kiểu thông điệp này được định nghĩa trong [đặc tả OTLP](https://opentelemetry.io/docs/specs/otlp/).

Cần phân biệt thêm ba tên thường xuất hiện cùng nhau:

- **OpenTelemetry:** tập hợp API, SDK, đặc tả và công cụ phục vụ khả năng quan sát.
- **OTLP:** giao thức trao đổi dữ liệu.
- **OpenTelemetry Collector:** tiến trình nhận, xử lý và chuyển tiếp dữ liệu.

Việc ứng dụng dùng OTLP không tự chứng minh rằng mọi phép đo đều được tạo bằng OpenTelemetry Metrics SDK. Trong cách tích hợp Spring Boot 3.3 của bài này, metrics được ghi qua **Micrometer MeterRegistry**, rồi registry OTLP chuyển chúng thành dữ liệu OTLP. Tracing sử dụng Micrometer Tracing cùng cầu nối OpenTelemetry và bộ xuất span.

## 3. Hai luồng trong Spring Boot 3.3

### 3.1. Luồng metrics

```text
Counter / Timer / Gauge
        |
        v
Micrometer MeterRegistry
        |
        v
OtlpMeterRegistry
        |
        v
POST /v1/metrics
        |
        v
Collector: pipeline metrics
```

`MeterRegistry` quản lý các đối tượng đo lường. `OtlpMeterRegistry` là một cách xuất kết quả đo tới nơi nhận OTLP. Một registry Prometheus hoặc một registry khác là lựa chọn đường xuất khác.

Các meter JVM có thể tạo dữ liệu dù ứng dụng không nhận yêu cầu HTTP. Một bộ đếm nghiệp vụ chỉ thay đổi khi mã ứng dụng thực sự tăng bộ đếm đó.

Spring Boot tự cấu hình registry phù hợp với dependency và các điều kiện kích hoạt. Xem [metrics trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 3.2. Luồng trace

```text
Hoạt động được gắn đo lường
        |
        v
Micrometer Observation / Micrometer Tracing
        |
        v
Cầu nối OpenTelemetry và hệ thống tạo span
        |
        v
Bộ xử lý span -> OTLP span exporter
        |
        v
POST /v1/traces
        |
        v
Collector: pipeline traces
```

**Gắn đo lường (instrumentation)** là làm cho một hoạt động có thể được quan sát. HTTP server có thể đã được framework gắn đo lường; một thao tác riêng của ứng dụng có thể cần tự tạo observation hoặc span.

Đường xuất trace cần hoạt động đã được đo, hệ thống tracing, quyết định lấy mẫu và exporter phù hợp. Chỉ có dependency xuất dữ liệu mà không tạo span thì không có một trace nghiệp vụ để gửi.

Ngược lại, có trace context hoặc Trace ID trong log mới chỉ cho thấy ngữ cảnh tracing đã được tạo/lan truyền. Nó chưa chứng minh nơi lưu trữ đã nhận span.

### 3.3. Observation là điểm chung, không gộp hai bộ xuất thành một

`ObservationRegistry` quản lý cấu hình các observation và thành phần phản ứng với vòng đời của chúng. `MeterRegistry` quản lý các phép đo. Hai kiểu này có vai trò khác nhau.

Khi các thành phần xử lý tương ứng được cấu hình, một observation có thể cung cấp đầu vào cho cả metrics lẫn tracing:

```text
                       -> thành phần ghi metrics -> MeterRegistry
Observation của thao tác
                       -> thành phần tracing -> span và bộ xuất trace
```

Nhưng:

- Tăng `Counter` trực tiếp không tự tạo một span.
- Tạo span qua `Tracer` không tự có nghĩa là đã ghi một metric nghiệp vụ tương ứng.
- Một observation có thể đóng góp cho cả hai mà chúng vẫn có lịch xuất, bộ lọc, cách lưu trữ và lỗi truyền riêng.

Trong Boot 3.3, các khóa có số lượng giá trị thấp (low cardinality) của observation được dùng cho metrics và trace; khóa có số lượng giá trị cao (high cardinality) chỉ đi theo trace trong cơ chế này. Vì vậy không đưa Trace ID hoặc mã yêu cầu duy nhất vào tag metrics để cố “nối” mọi điểm dữ liệu với từng yêu cầu.

Xem cơ chế [Observation của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html) và [vòng đời Observation của Micrometer](https://docs.micrometer.io/micrometer/reference/observation/introduction.html). Việc sử dụng tag có số lượng giá trị cao cho trace vẫn phải cân nhắc dữ liệu nhạy cảm và chi phí; trace không phải nơi chứa tùy ý mọi dữ liệu đầu vào.

## 4. Dependency và cấu hình phải đúng từng luồng

Bài này cố định Spring Boot **3.3.x**, với ví dụ chạy ở phiên bản **3.3.13**. Không sao chép các tên thuộc tính hoặc starter của Boot mới hơn rồi mặc định chúng tồn tại trong nhánh 3.3.

### 4.1. Dependency cốt lõi

Ngoài Actuator, từng luồng cần:

| Mục đích | Dependency chính trong ví dụ |
| --- | --- |
| Xuất Micrometer metrics bằng OTLP | `io.micrometer:micrometer-registry-otlp` |
| Nối Micrometer Tracing với OpenTelemetry | `io.micrometer:micrometer-tracing-bridge-otel` |
| Xuất span OpenTelemetry bằng OTLP | `io.opentelemetry:opentelemetry-exporter-otlp` |

Tên artifact `opentelemetry-exporter-otlp` có phạm vi thư viện rộng hơn tên “trace exporter”, nhưng thêm nó vào ứng dụng Boot 3.3 **không tự nối các meter Micrometer sang OpenTelemetry Metrics SDK**. Trong ví dụ, đường metrics vẫn cần registry OTLP riêng.

Boot 3.3 không tự cấu hình đường metrics của OpenTelemetry SDK chỉ vì có SDK trên classpath. Không đồng thời đưa Java Agent hoặc starter OpenTelemetry khác vào ví dụ này; chúng là lựa chọn tích hợp khác, có thể thay đổi cách tạo dữ liệu và làm dữ liệu bị ghi trùng nếu chồng lên nhau thiếu kiểm soát.

Tổ hợp dependency cho tracing được xác nhận trong [Tracing của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

### 4.2. Hai nhánh thuộc tính riêng biệt

| Nội dung | Metrics OTLP | Trace OTLP trong Boot 3.3 |
| --- | --- | --- |
| Đích nhận | `management.otlp.metrics.export.url` | `management.otlp.tracing.endpoint` |
| Header gửi đi | `management.otlp.metrics.export.headers.*` | `management.otlp.tracing.headers.*` |
| Nhịp xuất metrics | `management.otlp.metrics.export.step` | Không dùng khóa step của metrics |
| Lấy mẫu trace | Không do cấu hình sampling của tracing quyết định | `management.tracing.sampling.probability` |
| Tắt nhánh đang xét | `management.otlp.metrics.export.enabled=false` | `management.tracing.enabled=false` tắt tự cấu hình tracing rộng hơn |

Khóa tắt tracing cuối bảng có phạm vi cả việc xuất và lan truyền trace theo tự cấu hình của Boot; đừng hiểu nó là thao tác chỉ tắt một endpoint đích. Cấu hình Java hoặc tích hợp do ứng dụng tự sở hữu phải được xét riêng.

Sự bất đối xứng giữa `url` và `endpoint` là có thật. Các khóa sau không thể dùng thay cho nhau:

```properties
management.otlp.metrics.export.url=http://127.0.0.1:4318/v1/metrics
management.otlp.tracing.endpoint=http://127.0.0.1:4318/v1/traces
```

Một khóa sai có thể không tạo lỗi rõ ràng lúc khởi động; ứng dụng có thể tiếp tục dùng giá trị mặc định hoặc không có bộ xuất như mong muốn. Luôn đối chiếu [danh mục thuộc tính Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html) rồi kiểm chứng dữ liệu nhận được.

### 4.3. Cùng Collector vẫn có cấu hình xác thực riêng

Nếu nơi nhận yêu cầu xác thực, mỗi nhánh phải có header phù hợp:

```yaml
management:
  otlp:
    metrics:
      export:
        headers:
          Authorization: "Bearer ${METRICS_OTLP_TOKEN}"
    tracing:
      headers:
        Authorization: "Bearer ${TRACES_OTLP_TOKEN}"
```

Đây là phần bổ sung vào cấu hình đầy đủ, dành cho nơi nhận thực sự dùng Bearer token. Hai biến có thể được cấp cùng hoặc khác giá trị tùy quyền của hệ thống. Cấu hình header cho metrics không tự được sao chép sang nhánh tracing.

Trong vận hành, cấp token qua cơ chế bí mật của môi trường và dùng HTTPS theo hợp đồng nơi nhận. Trong thí nghiệm cục bộ ở phần sau, receiver chỉ lắng nghe trên loopback và không yêu cầu token để tập trung quan sát khác biệt giữa hai tín hiệu.

## 5. Phân biệt chu kỳ xuất với lấy mẫu trace

### 5.1. Step trả lời “bao lâu công bố metrics một lần?”

Ví dụ `management.otlp.metrics.export.step=10s` cấu hình chu kỳ xuất của registry OTLP. Nó không có nghĩa là chỉ ghi nhận một trong mười yêu cầu, hoặc chỉ ghi nhận sự kiện đúng mỗi giây thứ mười.

Bộ đếm có thể được tăng cho từng lần gọi; tới chu kỳ xuất, registry gửi các điểm dữ liệu được biểu diễn theo quy tắc của meter và cấu hình xuất. Một điểm dữ liệu có thể đại diện cho nhiều hoạt động. Không giả định mỗi yêu cầu nghiệp vụ sẽ tạo một yêu cầu HTTP OTLP riêng.

### 5.2. Sampling trả lời “trace nào được chọn để ghi/xuất?”

`management.tracing.sampling.probability` điều khiển xác suất lấy mẫu trace theo hệ thống tracing. Boot 3.3 mặc định dùng xác suất 0,1; trong môi trường học có thể đặt 1,0 để dễ nhìn thấy trace.

Với các yêu cầu bắt đầu trace mới, xác suất 0,1 không có nghĩa là cứ đủ mười yêu cầu sẽ chắc chắn giữ đúng một trace. Với trace đi từ hệ thống khác vào, quyết định lấy mẫu còn liên quan đến ngữ cảnh cha và bộ lấy mẫu đang dùng.

Thay xác suất thành 0,0 không làm các lệnh `Counter.increment()` trong ứng dụng tự ngừng chạy. Ngược lại, tắt registry OTLP metrics không tự tắt bộ xuất span.

| Thao tác thay đổi | Điều thay đổi trực tiếp | Điều không nên suy ra |
| --- | --- | --- |
| Step metrics 10s -> 30s | Nhịp xuất metrics | Xác suất giữ trace giảm |
| Sampling trace 1,0 -> 0,1 | Quyết định lấy mẫu trace | Chỉ còn 10% sự kiện được tính vào counter |
| Đổi URL metrics | Đích gửi metrics | Đích gửi trace tự thay đổi |
| Gỡ registry OTLP metrics | Khả năng xuất theo registry này | Toàn bộ tracing đã bị gỡ |

### 5.3. Lịch gửi theo lô của span là khái niệm thứ ba

Một span thường cần kết thúc trước khi được xử lý để xuất. Hệ thống tracing có thể gom span thành lô, có hàng đợi, thời điểm gửi và timeout riêng. Các yếu tố này khác với quyết định trace có được lấy mẫu hay không.

Không dùng `management.otlp.metrics.export.step` để chỉnh lịch gửi span. Cũng không tự sáng tác một khóa `management.otlp.tracing.step` chỉ vì muốn hai nhánh trông giống nhau.

Vì có hai bộ xuất, không đòi hỏi metrics và spans phải xuất hiện trong cùng một gói mạng, cùng một giây hoặc cùng một số lượng lô.

## 6. Collector có chung receiver nhưng cần hai pipeline

Một receiver OTLP có thể nhận nhiều tín hiệu, nhưng cấu hình đường xử lý vẫn được khai báo theo loại dữ liệu:

```text
                        -> pipeline metrics -> nơi nhận metrics
Receiver OTLP/HTTP chung
                        -> pipeline traces  -> nơi nhận trace
```

Khai báo receiver mới chỉ mô tả thành phần tiếp nhận. Phải đưa nó vào pipeline thích hợp trong `service.pipelines`. Nếu chỉ có pipeline traces, đừng kỳ vọng cấu hình đó đã tạo đầy đủ đường metrics.

Bộ xử lý và nơi chuyển tiếp cũng có thể khác nhau: trace có thể qua bộ lọc/lấy mẫu ở Collector; metrics có thể qua phép biến đổi hoặc tổng hợp riêng. Thêm một phép chuyển đổi từ spans sang metrics là cấu hình bổ sung, không phải điều OTLP mặc định tự làm.

Nguyên tắc kích hoạt thành phần qua pipeline được mô tả trong [cấu hình OpenTelemetry Collector](https://opentelemetry.io/docs/collector/configuration/).

## 7. Thí nghiệm: cùng một thao tác tạo metrics và span

Thí nghiệm là một dự án Maven độc lập để học cơ chế, không phải hướng dẫn sửa cấu trúc module đang làm việc. Chuẩn bị JDK 21, Maven, quyền tải dependency và một bản Collector có receiver `otlp` cùng exporter `debug`.

Ứng dụng và Collector chạy trực tiếp trên cùng máy; hai cổng 8080 và 4318 phải còn trống. Nếu dùng container, cần điều chỉnh địa chỉ mạng và điểm lắng nghe; `127.0.0.1` trong hai container khác nhau không chỉ cùng một tiến trình.

### 7.1. Tạo dự án tối thiểu

Cấu trúc:

```text
otlp-signals-demo/
├── pom.xml
├── collector.yml
└── src/main/
    ├── java/example/OtlpSignalsApplication.java
    └── resources/application.yml
```

`pom.xml` cố định phiên bản Boot để dependency của hai luồng được quản lý thống nhất:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>otlp-signals-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-otlp</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-tracing-bridge-otel</artifactId>
        </dependency>
        <dependency>
            <groupId>io.opentelemetry</groupId>
            <artifactId>opentelemetry-exporter-otlp</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/OtlpSignalsApplication.java`:

```java
package example;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OtlpSignalsApplication {
    public static void main(String[] args) {
        SpringApplication.run(OtlpSignalsApplication.class, args);
    }
}

@RestController
class DemoController {
    private final Counter calls;
    private final ObservationRegistry observations;

    DemoController(MeterRegistry meters, ObservationRegistry observations) {
        this.calls = Counter.builder("signal.demo.calls").register(meters);
        this.observations = observations;
    }

    @GetMapping("/demo")
    public String demo() {
        calls.increment();
        return Observation.createNotStarted("signal.demo.work", observations)
                .lowCardinalityKeyValue("operation", "demo")
                .observe(() -> "ok\n");
    }
}
```

Mỗi lần gọi `/demo` có hai hành động riêng:

1. `calls.increment()` tăng counter `signal.demo.calls`.
2. Observation `signal.demo.work` bao quanh một thao tác trả về chuỗi, cho phép cơ chế quan sát tạo timer và span khi các thành phần cần thiết được cấu hình.

HTTP server còn có observation/span cho việc phục vụ yêu cầu. Vì vậy một lần gọi không nhất thiết tương ứng đúng một span. Counter nghiệp vụ trong ví dụ chỉ tăng tại `/demo`; đọc endpoint chẩn đoán không tăng counter đó.

Đây là mã Spring Boot đầy đủ trong dự án ở trên. Không dùng `javac` chỉ với tệp Java mà bỏ classpath dependency; Maven đảm nhiệm biên dịch và chạy với các thư viện cần thiết.

### 7.2. Cấu hình hai bộ xuất

`src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: otlp-signals-demo

server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: "health,metrics"
  otlp:
    metrics:
      export:
        enabled: true
        url: http://127.0.0.1:4318/v1/metrics
        step: 10s
    tracing:
      endpoint: http://127.0.0.1:4318/v1/traces
  tracing:
    sampling:
      probability: 1.0
```

Điểm cần đọc đúng:

- Có **hai URL đầy đủ**, mỗi URL ứng với một loại tín hiệu.
- `step: 10s` nằm trong nhánh xuất metrics.
- `probability: 1.0` nằm trong nhánh lấy mẫu tracing.
- Endpoint `metrics` chỉ được mở để chẩn đoán trong thí nghiệm cục bộ; việc xuất ra ngoài không đòi hỏi công khai endpoint này.
- HTTP được dùng trên loopback cho thí nghiệm; cấu hình nơi nhận từ xa cần được triển khai theo yêu cầu TLS và xác thực riêng.

### 7.3. Cấu hình Collector

`collector.yml`:

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 127.0.0.1:4318

exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    metrics:
      receivers: [otlp]
      exporters: [debug]
    traces:
      receivers: [otlp]
      exporters: [debug]
```

Hai pipeline cùng dùng receiver `otlp` và cùng in dữ liệu qua `debug`. Exporter `debug` giúp xem nội dung đã nhận; nó không phải một kho lưu trữ lâu dài hay giao diện tìm kiếm trace.

Mở terminal thứ nhất tại thư mục dự án và chạy Collector đã cài:

```shell
otelcol --config=collector.yml
```

Tên executable có thể là `otelcol.exe` hoặc `otelcol-contrib` tùy bản cài; dùng executable thực có các thành phần trong cấu hình. Kiểm tra log khởi động để xác nhận receiver và cả hai pipeline hoạt động.

Mở terminal thứ hai tại thư mục có `pom.xml`:

```shell
mvn spring-boot:run
```

Chờ ứng dụng khởi động thành công. Các lệnh Maven cần chạy bằng JDK 21; kiểm tra `mvn -version` nếu phiên bản Java trong terminal không đúng.

### 7.4. Tạo dữ liệu và đọc kết quả

Trên PowerShell, gọi ba lần bằng `curl.exe`:

```powershell
1..3 | ForEach-Object {
    curl.exe --fail --silent --show-error http://127.0.0.1:8080/demo
}
```

Stdout của ba phản hồi thành công:

```text
ok
ok
ok
```

Đọc counter:

```powershell
curl.exe --fail --silent --show-error http://127.0.0.1:8080/actuator/metrics/signal.demo.calls
```

Trong lần chạy mới, chưa có ai gọi `/demo` ngoài ba lần trên, measurement `COUNT` phải là 3. Kết quả thực là JSON có các trường mô tả meter; không cần phụ thuộc vào thứ tự trường hoặc khoảng trắng của JSON.

Sau một vài chu kỳ, kiểm tra terminal Collector:

- **Nhánh metrics:** có metric `signal.demo.calls` và dữ liệu đo từ observation `signal.demo.work`; còn có thể có các metric JVM/framework.
- **Nhánh traces:** có span cho thao tác `signal.demo.work`, với Trace ID/Span ID và thời điểm thực thi.
- Span thao tác nằm trong ngữ cảnh của yêu cầu HTTP, nên có thể quan sát quan hệ với span server.

Không đòi hỏi counter, timer và span phải hiện trong cùng một lần in log. Tên khối hiển thị và cách in dữ liệu phụ thuộc phiên bản Collector; hãy nhận diện loại tín hiệu cùng tên metric/span thay vì chép một mẫu log chứa ID cố định.

### 7.5. Thí nghiệm lấy mẫu trace bằng 0

Dừng **ứng dụng**, giữ Collector chạy. Khởi động lại ứng dụng với cấu hình:

```shell
mvn spring-boot:run "-Dspring-boot.run.arguments=--management.tracing.sampling.probability=0.0"
```

Gọi ba lần `/demo` bằng các yêu cầu mới không gửi `traceparent` hoặc ngữ cảnh trace cha. Chỉ đánh giá các dữ liệu có timestamp thuộc lần chạy mới.

Kết quả cần kiểm tra:

| Quan sát | Kỳ vọng trong thí nghiệm này |
| --- | --- |
| Phản hồi nghiệp vụ | Vẫn có ba dòng `ok` |
| Counter của tiến trình mới | `COUNT = 3` |
| Metrics OTLP | Vẫn được gửi theo cấu hình registry |
| Span mới của ba yêu cầu gốc | Không được chọn xuất theo xác suất 0,0 |

Collector có thể vẫn đang hiển thị các lô cũ hoặc metric JVM mới; điều đó không phải trace mới của `/demo`. Cũng không kết luận rằng “không có Trace ID” chỉ từ việc không xuất span: ngữ cảnh trace và quyết định xuất là những phần khác nhau.

### 7.6. Tắt riêng đường xuất metrics OTLP

Dừng ứng dụng rồi chạy lại với sampling 1,0 và tắt registry OTLP metrics:

```shell
mvn spring-boot:run "-Dspring-boot.run.arguments=--management.tracing.sampling.probability=1.0 --management.otlp.metrics.export.enabled=false"
```

Gọi `/demo` và đối chiếu theo timestamp mới:

- Trace vẫn có thể được tạo và xuất qua đường tracing đã cấu hình.
- Registry OTLP metrics bị tắt nên không còn công bố các lô metrics qua nhánh này.
- Điều này không có nghĩa mọi phép đo trong ứng dụng biến mất: registry khác hoặc registry chẩn đoán vẫn có thể tồn tại theo tự cấu hình.

Khôi phục cấu hình đầy đủ khi kết thúc. Mỗi lần khởi động lại làm bộ đếm trong bộ nhớ của ví dụ bắt đầu lại; không so giá trị tuyệt đối giữa hai tiến trình rồi cho rằng đó là mất dữ liệu truyền.

## 8. Kiểm chứng từng tín hiệu bằng đúng loại bằng chứng

### 8.1. Bằng chứng cho metrics

Có thể kiểm tra theo ba lớp:

1. **Trong ứng dụng:** meter tồn tại và giá trị thay đổi khi thao tác xảy ra.
2. **Ở nơi nhận OTLP:** có dữ liệu metrics đúng tên, thuộc tính và thời gian.
3. **Ở hệ thống lưu trữ:** truy vấn thấy chuỗi thời gian tương ứng sau bước chuyển tiếp.

`/actuator/metrics` phục vụ chẩn đoán meter trong ứng dụng. Nó không phải endpoint nhập OTLP và cũng không phải bằng chứng span đã tới Collector.

Nếu dữ liệu hiển thị trên dashboard dưới một tên đã được hệ thống lưu trữ chuyển đổi, đừng nhầm tên đó với tên cần dùng tại endpoint Actuator. Hãy biết từng lớp đang biểu diễn metric theo quy ước nào.

### 8.2. Bằng chứng cho trace

Lần theo một yêu cầu được chọn lấy mẫu:

1. Hoạt động có thực sự được gắn tracing không?
2. Span có được tạo và kết thúc không?
3. Quyết định lấy mẫu có cho phép ghi/xuất nó không?
4. Bộ xuất có gửi tới đúng nhánh nhận trace không?
5. Có thể tìm thấy trace và các span mong đợi tại nơi nhận hoặc nơi lưu trữ không?

Có Trace ID trong log chưa đủ để khẳng định bước 4–5 đã thành công. Ngược lại, không có một trace cụ thể chưa đủ để kết luận metrics của yêu cầu đó đã bị bỏ qua.

Trong thí nghiệm, log `debug` của Collector chứng minh dữ liệu tới bộ thu. Muốn kết luận dữ liệu đã được lưu lâu dài, phải bổ sung nơi xuất/lưu trữ thật và truy vấn tại đó; exporter `debug` không cung cấp bằng chứng này.

### 8.3. Truyền trace context và xuất span là hai đường khác nhau

Giữa hai dịch vụ, ngữ cảnh trace có thể được truyền trong header của **yêu cầu nghiệp vụ**. Span được xuất tới Collector qua một kết nối khác:

```text
Dịch vụ A -- yêu cầu nghiệp vụ + trace context --> Dịch vụ B
    |                                                   |
    +-- xuất span --> Collector <-- xuất span -----------+
```

Cả A và B xuất span thành công nhưng không truyền đúng ngữ cảnh vẫn có thể tạo những trace rời nhau. Một hệ thống truyền được ngữ cảnh nhưng exporter bị lỗi cũng không tạo ra bộ dữ liệu trace đầy đủ ở nơi lưu trữ.

Khi dùng HTTP client trong Boot, hãy dùng builder đã được Boot cấu hình để giữ khả năng tích hợp quan sát và truyền ngữ cảnh. Với luồng bất đồng bộ hoặc nhiều thread, phải kiểm tra thêm việc truyền context; sự tồn tại của registry metrics không giải quyết phần này.

### 8.4. Không đối chiếu số span như đối chiếu bộ đếm

Một yêu cầu có thể tạo span server, span nghiệp vụ, span client và nhiều span khác. Một phần trace có thể bị lấy mẫu hoặc bị loại ở ứng dụng/Collector. Các lô dữ liệu cũng có thể đến khác thời điểm.

Vì vậy không dùng quy tắc “số span phải bằng số request” để đánh giá đường xuất. Trong ví dụ, chỉ có thể đòi hỏi ba span `signal.demo.work` khi ba lần gọi đó đã được instrument, được lấy mẫu và được thu thập đầy đủ theo điều kiện thí nghiệm.

Cùng lý do đó, tổng số span nhìn thấy không phải mẫu số đáng tin cậy để tính tỷ lệ lỗi toàn hệ thống nếu chưa hiểu chính sách lấy mẫu. Metrics ghi nhận trực tiếp ở ứng dụng và metrics tính từ spans là hai nguồn dữ liệu khác nhau, cần xác định rõ trước khi so sánh.

## 9. Những nhầm lẫn cần nhận ra ngay

| Nhận định hoặc triệu chứng | Cách phân tích đúng |
| --- | --- |
| “Đã có `micrometer-registry-otlp` nên chắc chắn có trace” | Dependency này phục vụ registry metrics; kiểm tra cầu nối tracing, exporter span và hoạt động được đo |
| “Có `opentelemetry-exporter-otlp` nên mọi meter Micrometer đã được gửi” | Kiểm tra registry metrics và cấu hình của nó; artifact không tự nối mọi API metrics khác nhau |
| “Metrics tới Collector nên trace cũng đã tới” | Kiểm tra riêng URL trace, pipeline traces, sampling và nội dung span |
| “Tăng sampling lên 1,0 để sửa mất metrics” | Sampling trace không làm counter tăng nhiều hơn; điều tra đường metrics riêng |
| “Đổi `step` để giảm độ trễ gửi span” | Step đó thuộc registry metrics; kiểm tra đường xử lý span |
| “Đổi `/v1/metrics` thành `/v1/traces` là chuyển đổi được dữ liệu” | Kiểu payload không đổi theo chuỗi URL; cần bộ xuất đúng tín hiệu |
| “Chỉ cần mở endpoint Actuator là Collector tự lấy trace” | Ví dụ dùng hai bộ xuất chủ động POST; endpoint chẩn đoán không xuất span thay chúng |
| “Cùng host/port thì header metrics tự dùng cho trace” | Header được cấu hình ở hai nhánh; quyền nhận từng loại dữ liệu có thể khác |
| “Có ba yêu cầu thì backend phải chứa đúng ba span” | Một yêu cầu có thể tạo nhiều span và còn chịu chính sách lấy mẫu |
| “Có một Trace ID trên metric thì đã lưu toàn bộ trace” | Liên kết hoặc exemplar, nếu được hỗ trợ, chỉ giúp điều hướng; vẫn phải xác minh trace thực sự có trong kho |
| “Dùng Java Agent cùng ví dụ sẽ cho kết quả giống hệt” | Agent là cách tích hợp khác; có thể khác quy ước tên, nguồn dữ liệu và gây ghi trùng |

Khi chỉ thiếu một tín hiệu, hãy xác minh lần lượt **nguồn tạo dữ liệu -> thành phần đo -> quyết định lọc/lấy mẫu -> bộ xuất -> đường nhận -> pipeline -> nơi lưu trữ**. Tránh thay hàng loạt cấu hình của cả hai nhánh cùng lúc, vì sẽ khó biết thay đổi nào giải quyết được vấn đề.

## 10. Tự kiểm tra bằng tình huống

**Tình huống 1: Có metric JVM nhưng chưa có trace, dù ứng dụng khởi động bình thường.**

Metric JVM có thể có từ meter mặc định mà không cần một yêu cầu nghiệp vụ. Kiểm tra đường tracing và tạo hoạt động có instrumentation trước; đừng lấy sự tồn tại của metric JVM làm bằng chứng đã tạo span.

**Tình huống 2: Sau khi đặt sampling về 0,0, bộ đếm `signal.demo.calls` vẫn tăng. Có mâu thuẫn không?**

Không. Lệnh tăng counter vẫn chạy khi `/demo` được gọi. Quyết định lấy mẫu trace không vô hiệu hóa lệnh đó. Trong thí nghiệm các yêu cầu gốc mới không có ngữ cảnh cha, không có span được chọn xuất nhưng metrics vẫn được ghi và xuất.

**Tình huống 3: Cả hai URL trỏ tới cùng Collector; nhánh metrics nhận HTTP 401, trace vẫn được chấp nhận.**

Kiểm tra header, credential và quyền của riêng nhánh metrics, cùng chính sách của gateway/receiver. Cùng host không chứng minh hai yêu cầu đang gửi cùng thông tin xác thực hoặc được cấp cùng quyền.

**Tình huống 4: Dashboard metrics cho thấy một nhóm yêu cầu chậm, nhưng không tìm được trace của một yêu cầu cụ thể.**

Có thể trace đó không được chọn lấy mẫu, đã hết thời gian lưu, bị lọc, lỗi truyền hoặc đang được tìm sai điều kiện. Metrics tổng hợp không chứa đủ dữ liệu để tái tạo trace đã không được lưu.

**Tình huống 5: Hai dịch vụ đều gửi span nhưng các hoạt động không nằm trong cùng trace.**

Kiểm tra truyền ngữ cảnh qua yêu cầu nghiệp vụ và qua ranh giới bất đồng bộ. Việc xuất span của từng dịch vụ và việc duy trì quan hệ giữa chúng cần được kiểm chứng riêng.

Sau bài học, người đọc cần giải thích được ba điểm bằng chính cấu hình và bằng chứng: **dữ liệu nào được tạo, bộ xuất nào gửi dữ liệu đó và nơi nào xác nhận đã nhận đúng tín hiệu**.
