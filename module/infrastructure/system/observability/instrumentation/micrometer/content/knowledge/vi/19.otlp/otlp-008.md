# Gửi qua Collector và kiểm chứng dữ liệu bằng một đích thử nghiệm

Micrometer có thể xuất metric theo OpenTelemetry Protocol (OTLP) đến OpenTelemetry Collector. Collector nhận dữ liệu từ ứng dụng, xử lý qua pipeline rồi chuyển đến một exporter. Khi cần kiểm tra đường truyền trước khi nối backend giám sát thật, có thể dùng `debug` exporter làm đích thử nghiệm: Collector in resource, metric, attribute và datapoint nhận được ra log.

Luồng này giúp kiểm chứng cả cấu hình phía ứng dụng lẫn cấu hình phía Collector. Một metric chỉ xuất hiện trong registry của JVM chưa chứng minh nó đã được gửi đi; một request OTLP thành công cũng chưa chứng minh metric đã được chuyển đến backend lưu trữ. Đọc log của test sink giúp xác nhận Collector thực sự nhận được dữ liệu và hiểu nó dưới dạng OTLP Metrics.

## Kiến trúc luồng dữ liệu

Trong ứng dụng Spring Boot, `micrometer-registry-otlp` cung cấp registry gửi metric qua OTLP. Ứng dụng ghi nhận số đo bằng API Micrometer quen thuộc. Registry xuất metric theo chu kỳ cấu hình đến OTLP receiver của Collector. Collector đưa dữ liệu qua pipeline metrics rồi chuyển đến `debug` exporter.

```mermaid
flowchart LR
    A[Service Java] --> B[MeterRegistry]
    B --> C[OtlpMeterRegistry]
    C -->|OTLP HTTP /v1/metrics| D[OTLP Receiver]
    D --> E[Metrics Pipeline]
    E --> F[Batch Processor]
    F --> G[Debug Exporter]
    G --> H[Collector logs]
```

Các thành phần có trách nhiệm riêng:

- **Micrometer instrumentation:** định nghĩa metric, loại meter, tag và thời điểm ghi nhận.
- **OTLP registry:** chuyển meter thành cấu trúc OTLP Metrics và gửi theo lịch xuất.
- **OTLP receiver:** nhận payload OTLP từ ứng dụng.
- **Collector pipeline:** nối receiver, processor và exporter cho tín hiệu metrics.
- **Debug exporter:** in dữ liệu đã nhận để kiểm tra trong môi trường thử nghiệm.

Collector không tự tạo metric nghiệp vụ. Nếu service chưa ghi nhận observation, Collector không thể in ra một giá trị nghiệp vụ mới chỉ nhờ có receiver.

## Thêm OTLP registry vào ứng dụng

Với Gradle và Spring Boot:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-otlp")
}
```

Với Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-otlp</artifactId>
    <scope>runtime</scope>
</dependency>
```

Các ví dụ giả định dự án dùng Spring Boot dependency management hoặc BOM tương thích để quản lý phiên bản Micrometer. Không tự ghép phiên bản `micrometer-registry-otlp` khác dòng với Micrometer Core do Spring Boot quản lý.

Khi registry implementation có trên classpath và cấu hình export được bật, Spring Boot có thể auto-configure OTLP registry. Service nghiệp vụ tiếp tục inject `MeterRegistry`; không cần phụ thuộc trực tiếp vào `OtlpMeterRegistry`.

## Cấu hình endpoint OTLP/HTTP

Micrometer OTLP registry gửi metrics qua OTLP HTTP/protobuf. Collector OTLP receiver thường lắng nghe HTTP ở cổng `4318`; endpoint nhận metrics có đường dẫn `/v1/metrics`.

Ví dụ `application.yml` cho ứng dụng chạy trực tiếp trên máy host:

```yaml
management:
  otlp:
    metrics:
      export:
        url: http://localhost:4318/v1/metrics
        step: 10s
        connect-timeout: 2s
        read-timeout: 5s
        resource-attributes:
          "service.name": checkout-service
          "deployment.environment": local
```

Ý nghĩa các thuộc tính:

- `url`: địa chỉ OTLP HTTP metrics endpoint của Collector, gồm cả `/v1/metrics`.
- `step`: khoảng xuất dữ liệu của registry. Ví dụ `10s` nghĩa là registry gửi metric theo chu kỳ khoảng 10 giây.
- `connect-timeout`: giới hạn thời gian thiết lập kết nối.
- `read-timeout`: giới hạn thời gian chờ phản hồi.
- `resource-attributes`: thuộc tính mô tả resource phát metric, ví dụ tên service và môi trường triển khai.

Prefix và thuộc tính cấu hình có thể thay đổi theo phiên bản Spring Boot. Hãy đối chiếu metadata cấu hình của phiên bản dự án đang dùng nếu binder không nhận thuộc tính. Không đặt API key hoặc thông tin bí mật trực tiếp trong file cấu hình được commit.

Nếu ứng dụng cũng chạy trong Docker Compose cùng Collector, `localhost` bên trong container ứng dụng là chính container đó. Khi đó dùng tên service trên network Compose, ví dụ `http://otel-collector:4318/v1/metrics`. Nếu ứng dụng chạy trên host và Collector chạy trong container, dùng `http://localhost:4318/v1/metrics` khi cổng đã publish về loopback host.

Không nhầm cổng OTLP/HTTP `4318` với cổng OTLP/gRPC `4317`. Một endpoint gRPC không thể được dùng như endpoint HTTP chỉ bằng cách đổi port. Cấu hình protocol của client phải khớp receiver đang bật ở Collector.

## Ghi nhận metric mẫu trong ứng dụng

Tạo một component nhỏ để ghi nhận Counter và Timer. Ví dụ sử dụng tag có tập giá trị hữu hạn:

```java
import java.util.function.Supplier;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class CheckoutMetrics {
    private final MeterRegistry registry;
    private final Timer paymentDuration;

    public CheckoutMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.paymentDuration = Timer.builder("payment.processing")
                .description("Thời gian xử lý thanh toán")
                .register(registry);
    }

    public void orderCreated(String channel) {
        registry.counter(
                "orders.created",
                "channel", normalizeChannel(channel))
                .increment();
    }

    public <T> T measurePayment(Supplier<T> operation) {
        return paymentDuration.record(operation);
    }

    private String normalizeChannel(String channel) {
        return switch (channel) {
            case "web", "mobile", "partner" -> channel;
            default -> "other";
        };
    }
}
```

Gọi `orderCreated(...)` sau khi đơn hàng được xác nhận theo định nghĩa nghiệp vụ của ứng dụng. Dùng `measurePayment(...)` để bọc thao tác thanh toán cần đo. `normalizeChannel(...)` giới hạn label về bốn giá trị; không đưa `orderId`, email hoặc request ID vào attribute.

Tên metric và attribute trong OTLP không nên được đoán từ quy tắc Prometheus. OTLP giữ cấu trúc metric và attribute theo mô hình OpenTelemetry; cách biểu diễn trong debug output có thể giữ dấu chấm của tên meter. Hãy quan sát payload đã nhận thay vì giả định tên phải đổi thành dấu gạch dưới như Prometheus exposition.

## Tạo Collector pipeline với debug exporter

Tạo file `otel-collector.yaml` trong thư mục chạy thử nghiệm:

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 5s
    send_batch_size: 512

exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
```

Pipeline `metrics` khai báo rõ ba giai đoạn:

- `receivers: [otlp]` nhận dữ liệu metrics từ OTLP HTTP receiver.
- `processors: [batch]` gom dữ liệu trước khi chuyển tiếp, giúp giảm số lần gọi exporter.
- `exporters: [debug]` in dữ liệu đã xử lý ra log để kiểm chứng.

Collector chỉ khởi tạo component được khai báo trong pipeline. Nếu receiver hoặc exporter không được nối vào pipeline `metrics`, nó sẽ không tham gia luồng dữ liệu dù phần cấu hình component có tồn tại.

`debug` exporter là test sink, không phải backend lưu trữ. Nó không cung cấp truy vấn lịch sử, retention, dashboard hoặc cảnh báo. Dùng nó để xác nhận Collector nhận đúng dữ liệu trong quá trình phát triển; khi triển khai thật, thay hoặc bổ sung exporter gửi đến backend quan sát.

## Chạy Collector thử nghiệm bằng Docker Compose

Tạo `compose.yaml` cạnh file cấu hình Collector:

```yaml
services:
  otel-collector:
    image: otel/opentelemetry-collector:<pinned-version>
    command: ["--config=/etc/otelcol/config.yaml"]
    volumes:
      - ./otel-collector.yaml:/etc/otelcol/config.yaml:ro
    ports:
      - "127.0.0.1:4318:4318"
```

Thay `<pinned-version>` bằng phiên bản Collector đã chọn và cố định trong môi trường dự án. Cổng được bind vào loopback host để chỉ cho phép máy local truy cập trong bài thử nghiệm. Receiver lắng nghe `0.0.0.0` bên trong container để nhận kết nối qua cổng được publish.

Khởi động Collector:

```bash
docker compose up -d
docker compose logs -f otel-collector
```

Kiểm tra log khởi động để xác nhận OTLP receiver đã lắng nghe ở `4318` và metrics pipeline đã được tạo. Nếu Collector báo component không tồn tại, kiểm tra image distribution có chứa OTLP receiver và debug exporter, đồng thời kiểm tra cú pháp file cấu hình theo đúng phiên bản image.

## Kiểm chứng dữ liệu đã đến test sink

Thực hiện theo thứ tự:

1. Khởi động Collector và theo dõi log của service `otel-collector`.
2. Khởi động ứng dụng Spring Boot với OTLP registry và URL trỏ đến Collector.
3. Gọi luồng nghiệp vụ tạo đơn hàng hoặc thanh toán để phát sinh metric.
4. Chờ ít nhất một chu kỳ `step` và thêm thời gian cho batch processor chuyển dữ liệu.
5. Quan sát log Collector để tìm resource, metric name, type, attributes và datapoint.

Một phần log debug có thể có hình dạng tương tự:

```text
ResourceMetrics #0
  Resource attributes:
    -> service.name: Str(checkout-service)
    -> deployment.environment: Str(local)
  ScopeMetrics #0
    Metrics #0
      Name: orders.created
      Description: Số đơn hàng được tạo
      DataType: Sum
      Data points:
        Data point attributes:
          -> channel: Str(web)
        Value: 1
```

Định dạng log cụ thể thay đổi theo phiên bản Collector. Các trường cần xác nhận là:

- Resource có `service.name` đúng với ứng dụng gửi.
- Metric có tên và loại phù hợp với meter đã đăng ký.
- Attribute của datapoint có tag như `channel=web`.
- Giá trị count hoặc sum thay đổi sau khi gọi nghiệp vụ.
- Timestamp và temporality có mặt theo cấu trúc metric được xuất.

Nếu tạo hai đơn hàng qua channel `web`, có thể thấy giá trị counter tương ứng tăng. Nếu chạy payment operation, Timer cung cấp dữ liệu count và duration; nếu bật histogram, dữ liệu phân phối cũng có thể xuất hiện tùy cấu hình và registry.

## Phân biệt Resource attributes và metric attributes

OTLP phân biệt thông tin resource với attribute gắn trên datapoint:

| Loại dữ liệu | Ví dụ | Ý nghĩa |
|---|---|---|
| Resource attributes | `service.name`, `deployment.environment`, `service.instance.id` | Mô tả tiến trình hoặc service phát metric |
| Metric/datapoint attributes | `channel`, `outcome`, `payment.provider` | Phân biệt nhóm quan sát của một metric |
| Instrumentation scope | Tên thư viện hoặc scope instrumentation | Cho biết thành phần tạo ra telemetry |

Không đưa `service.name` vào từng meter tag nếu nó là thuộc tính chung của resource và đã được cấu hình ở resource attributes. Tách đúng hai lớp giúp payload gọn, giữ định danh service nhất quán và tránh nhân bản các tag chung trên mọi datapoint.

`service.instance.id` có thể phân biệt từng instance nếu backend cần phân tích theo tiến trình. Giá trị này nên ổn định trong vòng đời một instance và không được tạo ngẫu nhiên ở mỗi lần scrape hoặc mỗi lần publish. Các resource attribute và cách tạo instance ID phụ thuộc cấu hình registry, Spring Boot và môi trường triển khai.

## Step, batch và độ trễ xuất dữ liệu

`step` của OTLP registry xác định khoảng tổng hợp/xuất metric. Nếu đặt `step: 10s`, đừng kỳ vọng mỗi lần gọi `increment()` lập tức tạo một log ở Collector. Registry có thể gửi dữ liệu khi step được đóng hoặc theo lịch publisher.

`batch` processor ở Collector là một lớp gom dữ liệu khác với step của Micrometer:

- Step thuộc phía registry, quyết định chu kỳ xuất metric từ ứng dụng.
- Batch processor thuộc phía Collector, gom các request hoặc phần dữ liệu đã nhận trước khi chuyển đến exporter.

Hai khoảng thời gian này có thể cộng thêm độ trễ quan sát. Trong thử nghiệm, chờ ít nhất một step cộng thời gian batch là hợp lý. Trong production, chọn step và batch timeout dựa trên yêu cầu độ trễ cảnh báo, lượng metric, số instance và chi phí ingest.

Nếu metric không xuất hiện ngay sau một request, trước tiên kiểm tra step và lịch publish. Đừng kết luận endpoint sai chỉ vì chưa có log trong vài mili giây đầu.

## Temporality và cách diễn giải dữ liệu

OTLP metric có thể biểu diễn dữ liệu theo cumulative hoặc delta temporality tùy loại metric và cấu hình registry. Cumulative giữ giá trị tích lũy từ một thời điểm bắt đầu; delta biểu diễn phần tăng trong một khoảng. Backend cần hiểu đúng temporality để tính rate, tổng và cửa sổ dữ liệu.

Trong debug output, kiểm tra metric type, aggregation temporality và start timestamp nếu có. Không mặc định mọi registry OTLP đều gửi cùng temporality hoặc cùng cách biểu diễn histogram. Cấu hình Micrometer OTLP registry và phiên bản thư viện quyết định chi tiết; Collector chuyển tiếp cấu trúc nhận được nếu pipeline không có processor biến đổi nó.

Nếu backend nhận delta mà truy vấn xử lý như cumulative counter, kết quả có thể sai. Ngược lại, nếu dữ liệu cumulative bị cộng lặp như các delta độc lập, tổng sẽ bị đếm nhiều lần. Khi thay registry hoặc backend, hãy xác minh temporality bằng dữ liệu thực tế trước khi triển khai dashboard và alert.

## Thay test sink bằng backend thật

Sau khi xác nhận debug exporter nhận đúng metric, có thể thay bằng exporter gửi đến backend OTLP. Pipeline vẫn giữ receiver và processor, chỉ đổi exporter đích. Ví dụ cấu trúc:

```yaml
exporters:
  otlp/backend:
    endpoint: telemetry-backend:4317
    tls:
      insecure: true

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp/backend]
```

Đây là cấu hình minh họa cho backend OTLP/gRPC trong mạng thử nghiệm. Thay hostname, cổng, TLS và xác thực theo tài liệu backend thực tế. `insecure: true` chỉ phù hợp cho môi trường thử nghiệm không dùng TLS; không dùng cấu hình đó để gửi telemetry qua mạng không tin cậy.

Có thể giữ cả `debug` và exporter backend trong pipeline khi cần đối chiếu, nhưng log chi tiết có thể chứa giá trị metric và attribute. Không bật debug exporter lâu dài trong production nếu log không được kiểm soát về dung lượng và quyền truy cập.

## Chẩn đoán khi Collector không nhận được metric

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Connection refused | Collector chưa chạy, cổng chưa publish hoặc ứng dụng dùng sai hostname | Kiểm tra trạng thái container, port mapping và địa chỉ từ network của ứng dụng |
| HTTP 404 | Sai path, thường thiếu `/v1/metrics` | Kiểm tra URL OTLP metrics endpoint và HTTP receiver |
| HTTP 400 hoặc lỗi decode | Client và receiver không cùng protocol/content type hoặc payload không hợp lệ | Xác nhận client dùng OTLP HTTP/protobuf và receiver bật `http` |
| Collector chạy nhưng không có log metric | Metrics pipeline chưa nối receiver/exporter, chưa hết step hoặc app chưa ghi observation | Kiểm tra pipeline, chờ step và phát sinh metric mẫu |
| Có log metric nhưng thiếu attribute | Tag chưa được thêm hoặc filter loại bỏ meter/tag | Kiểm tra meter trong ứng dụng và payload debug |
| Resource thiếu `service.name` | Resource attributes chưa bind hoặc sai cấu hình | Kiểm tra thuộc tính resource và cấu hình export của Spring Boot |
| Metric xuất hiện trễ | Step hoặc batch timeout dài | Đối chiếu chu kỳ registry với batch processor |
| Backend thật không có dữ liệu dù debug có | Exporter backend sai endpoint, TLS, auth hoặc pipeline | Kiểm tra log exporter, xác thực và trạng thái ingest phía backend |
| Dữ liệu bị nhân đôi | Gửi cùng metric qua nhiều đường hoặc backend hợp nhất trùng dữ liệu | Kiểm tra pipeline và các đường export đang hoạt động |

Một cách khoanh vùng hiệu quả là kiểm tra lần lượt ba điểm: registry có tạo dữ liệu không; Collector có nhận payload OTLP không; exporter cuối có chuyển payload đến backend không. Debug exporter giúp xác nhận điểm thứ hai. Nếu debug có dữ liệu nhưng backend không có, lỗi nằm ở exporter đích hoặc backend ingest thay vì instrumentation ban đầu.

## Kiểm thử tự động và thủ công

Unit test với `SimpleMeterRegistry` phù hợp để xác nhận service gọi `increment()` hoặc `record(...)` đúng lúc. Nó không kiểm tra OTLP serialization hoặc mạng. Để kiểm chứng đường gửi, cần integration test có OTLP receiver thật hoặc receiver giả lập tương thích giao thức.

Một bài kiểm thử tích hợp nên xác nhận:

1. Ứng dụng khởi tạo OTLP registry với endpoint của Collector.
2. Một thao tác nghiệp vụ tạo ra metric có tên đã dự kiến.
3. Resource attributes nhận diện đúng service và môi trường.
4. Meter tag xuất hiện dưới dạng datapoint attributes.
5. Count, sum hoặc histogram thay đổi đúng sau thao tác.
6. Collector ghi nhận payload trong metrics pipeline.
7. Khi backend tạm ngừng, ứng dụng không bị treo vô hạn và lỗi export được quan sát qua log hoặc metric sức khỏe phù hợp.

Không dựa vào một `Thread.sleep(...)` ngắn cố định rồi khẳng định dữ liệu phải xuất hiện. Dùng step có thể kiểm soát, timeout đủ dài, log collector hoặc test receiver có latch để xác nhận request đã đến. Đóng registry và ứng dụng sau test để publisher nền được dừng đúng cách.

## Bảo mật và vận hành Collector

OTLP receiver có thể nhận telemetry từ nhiều ứng dụng. Trong môi trường local, chỉ publish cổng ra loopback host như ví dụ Compose. Trong môi trường dùng chung, đặt receiver sau network policy, firewall, TLS và xác thực phù hợp; tránh mở cổng nhận telemetry không xác thực ra Internet.

Metric attribute có thể chứa dữ liệu do ứng dụng tạo. Không gửi token, email, thông tin cá nhân hoặc ID nhạy cảm trong tag. Debug exporter in payload ra log, do đó log của test sink cũng cần được bảo vệ và dọn dẹp theo chính sách môi trường.

Trong production, Collector cần được theo dõi sức khỏe riêng: receiver có nhận dữ liệu, processor có làm rơi dữ liệu do giới hạn, exporter có gửi thành công, queue/retry có tăng và Collector có đủ CPU/bộ nhớ hay không. Cấu hình batch, retry, sending queue và memory limiter theo năng lực của backend và lưu lượng telemetry.

## Checklist hoàn thành

- [ ] Ứng dụng có `micrometer-registry-otlp` tương thích với Spring Boot.
- [ ] OTLP registry trỏ đúng HTTP endpoint `/v1/metrics` của Collector.
- [ ] Cổng và protocol khớp: OTLP/HTTP thường dùng `4318`, OTLP/gRPC thường dùng `4317`.
- [ ] `step`, timeout và resource attributes được cấu hình có chủ đích.
- [ ] Collector có OTLP receiver và metrics pipeline nối đến `debug` exporter.
- [ ] Collector khởi động thành công và lắng nghe đúng địa chỉ/cổng.
- [ ] Đã phát sinh metric từ luồng nghiệp vụ và chờ qua ít nhất một step.
- [ ] Debug output xác nhận resource, metric name, type, attributes và datapoint value.
- [ ] Đã kiểm tra temporality và cấu trúc histogram trước khi viết query backend.
- [ ] Đã phân biệt test sink với backend lưu trữ thật.
- [ ] Cổng receiver, log debug và metric attributes được bảo vệ phù hợp.

Khi debug exporter in ra đúng resource và datapoint, đã xác nhận được đường gửi từ Micrometer qua OTLP receiver và metrics pipeline của Collector. Bước tiếp theo là thay test sink bằng exporter backend, cấu hình bảo mật và xác minh dữ liệu sau ingest. Giữ riêng kiểm thử instrumentation, kiểm thử truyền OTLP và kiểm thử backend sẽ giúp khoanh vùng lỗi nhanh khi metric không xuất hiện.
