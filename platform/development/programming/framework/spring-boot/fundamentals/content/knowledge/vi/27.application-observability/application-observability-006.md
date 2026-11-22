# loggers, metrics và các tín hiệu vận hành cơ bản

Khi ứng dụng Spring Boot chạy trên máy cá nhân, bạn có thể biết nó đang làm gì bằng cách nhìn console. Nhưng khi ứng dụng chạy trong container, trên nhiều máy chủ hoặc phục vụ hàng nghìn request, chỉ thấy dòng chữ “Started Application” là chưa đủ. Bạn cần trả lời được những câu hỏi thực tế:

- Ứng dụng còn sống và có thể nhận traffic không?
- Một request chậm ở đâu? Tỷ lệ lỗi có đang tăng không?
- Hàng đợi công việc có đang tích tụ?
- Log đang để mức nào và có thể tăng mức DEBUG khi xử lý sự cố không?
- Lượng request, thời gian đáp ứng và số lỗi thay đổi thế nào theo thời gian?
- Khi một dependency như database gặp vấn đề, hệ thống có phát ra tín hiệu phù hợp không?

Spring Boot cung cấp các mảnh ghép để quan sát tình trạng ứng dụng: **logging**, **Micrometer metrics**, **Actuator endpoints**, **health indicators**, **application availability** và khả năng tích hợp với hệ giám sát bên ngoài. Những thành phần này không thay thế nhau; chúng cung cấp các góc nhìn bổ sung cho cùng một ứng dụng.

Bài học thuộc chương **Quan sát ứng dụng** của **Spring Boot Fundamentals**. Trọng tâm là `loggers`, `metrics` và các tín hiệu vận hành cơ bản: cách kích hoạt, đọc, diễn giải, mở rộng và bảo vệ chúng.

## 1. Quan sát ứng dụng là gì?

Trong vận hành phần mềm, **observability** là khả năng hiểu trạng thái và hành vi bên trong hệ thống từ những tín hiệu mà nó phát ra. Với Spring Boot, các tín hiệu thường gặp là:

| Tín hiệu | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **Logs** | Sự kiện cụ thể nào đã xảy ra? | “Payment failed: orderId=ORD-123” |
| **Metrics** | Tần suất, tỷ lệ hoặc xu hướng thế nào? | 100 request/giây, 2% lỗi, độ trễ P95 300 ms |
| **Traces** | Một thao tác đi qua những thành phần nào? | API → Service → Database → Gateway |
| **Health/availability** | Instance còn sống và có sẵn sàng nhận traffic không? | `UP`, `DOWN`, accepting/refusing traffic |
| **Application events** | Ứng dụng vừa chuyển giai đoạn lifecycle nào? | Started, Ready, shutdown |
| **Alerts** | Khi nào người vận hành cần hành động? | Tỷ lệ HTTP 5xx vượt ngưỡng trong một khoảng thời gian |

Bài này tập trung sâu vào logs, metrics và availability/health, đồng thời chỉ ra nơi traces và alerts kết nối với chúng.

### 1.1. Ba tầng câu hỏi

Giả sử người dùng báo: “Thanh toán đang rất chậm”.

**Tầng 1 — Có vấn đề rộng không?**

Xem metrics:

```text
request rate          : 250 requests/s
HTTP 5xx rate         : 7%
P95 request duration  : 1.8 s
```

Các con số này là ví dụ minh họa, không phải số liệu đo được từ một hệ thống cụ thể.

**Tầng 2 — Có sự kiện lỗi cụ thể nào?**

Xem log:

```text
ERROR Payment gateway timeout: orderId=ORD-123 attempt=3
java.net.SocketTimeoutException: Read timed out
    at ...
```

**Tầng 3 — Một request đi qua đâu?**

Nếu có tracing, xem các spans của cùng request để xác định dependency hoặc operation nào chiếm phần lớn thời gian.

Metrics nói về *quy mô và xu hướng*, logs nói về *sự kiện cụ thể*, traces nói về *đường đi của thao tác*. Health cho biết trạng thái vận hành hiện tại theo quy tắc bạn cấu hình.

### 1.2. Monitoring không tự xuất hiện chỉ vì có log

Một ứng dụng có thể ghi log đầy đủ mà vẫn chưa có dashboard, alerting hay hệ thống lưu metrics. Spring Boot cung cấp API và endpoint để phát ra tín hiệu; bạn vẫn cần chọn nơi thu thập, lưu trữ, trực quan hóa và cảnh báo phù hợp.

Sơ đồ khái quát:

```text
                  Spring Boot Application
               ┌──────────────┬──────────────┐
               │              │              │
               ▼              ▼              ▼
          SLF4J Logger   Micrometer       Actuator
               │          Metrics       Health/Info
               ▼              │              │
         Console/JSON          ▼              ▼
               │        Registry/Export   Probes
               ▼              │              │
         Log Collector         ▼              ▼
               │         Metrics Backend  Orchestrator
               └──────────────┬──────────────┘
                              ▼
                      Dashboard / Alert
```

Không phải ứng dụng nào cũng cần tất cả công cụ trên ngay từ đầu. Điều quan trọng là biết tín hiệu nào giải quyết vấn đề gì.

## 2. Spring Boot Actuator đóng vai trò gì?

**Spring Boot Actuator** là module cung cấp các endpoint và integration phục vụ quản lý, giám sát ứng dụng. Nó cho phép quan sát nhiều thông tin như health, metrics, logger configuration và application info.

Trong Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Trong Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Sau khi thêm starter và khởi động ứng dụng có web environment phù hợp, bạn có thể sử dụng các web endpoints được expose.

Ví dụ:

```text
GET http://localhost:8080/actuator/health
```

Kết quả cơ bản:

```json
{
  "status": "UP"
}
```

### 2.1. Endpoint tồn tại không có nghĩa đã được expose qua HTTP

Actuator có nhiều endpoint như:

- `health`
- `info`
- `loggers`
- `metrics`
- `env`
- `beans`
- `conditions`
- `configprops`
- `threaddump`
- `heapdump`
- `prometheus` nếu có registry phù hợp

Nhưng **không phải tất cả đều được expose mặc định qua web**. Trong cấu hình Boot thường gặp, `health` là endpoint web được expose mặc định; muốn truy cập `loggers` hay `metrics` qua HTTP, bạn cần cấu hình exposure.

Đây là một lựa chọn bảo mật quan trọng: nhiều endpoint cung cấp thông tin nội bộ hoặc khả năng điều khiển ứng dụng.

### 2.2. Ví dụ expose những endpoint cần thiết

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,loggers
```

Khi đó, tùy security và web configuration, các endpoint tương ứng có thể được truy cập theo đường dẫn `/actuator/...`.

Không nên đặt:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
```

trong production nếu chưa có lý do, chính sách truy cập và biện pháp bảo vệ rõ ràng.

### 2.3. Actuator không nhất thiết phải sử dụng trên cổng ứng dụng chính

Có thể cấu hình management server port riêng trong môi trường hỗ trợ:

```yaml
management:
  server:
    port: 9090
```

Khi đó các web management endpoints có thể phục vụ qua cổng khác với server chính.

Việc tách cổng giúp áp dụng network policy riêng, nhưng **không tự động đảm bảo endpoint an toàn**. Bạn vẫn cần authentication, authorization, TLS hoặc giới hạn network access phù hợp.

## 3. Logger và log level là gì?

Một logger thường gắn với tên class hoặc package:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);
```

SLF4J cung cấp các mức phổ biến:

- `TRACE`: chi tiết rất sâu, thường dùng khi điều tra đường đi của code.
- `DEBUG`: thông tin chẩn đoán cho developer.
- `INFO`: sự kiện hoạt động đáng quan tâm.
- `WARN`: bất thường nhưng ứng dụng có thể tiếp tục.
- `ERROR`: lỗi khiến operation thất bại hoặc cần chú ý.

Ví dụ:

```java
log.info("Order accepted: orderId={}", orderId);

log.debug(
        "Order validation: orderId={} itemCount={}",
        orderId,
        itemCount
);

log.warn(
        "Payment retry: orderId={} attempt={}",
        orderId,
        attempt
);

log.error(
        "Payment failed: orderId={}",
        orderId,
        exception
);
```

Cú pháp `{}` giúp tham số hóa thông điệp; khi truyền `Throwable` ở vị trí cause phù hợp, backend có thể ghi stack trace.

### 3.1. Logger name và package hierarchy

Với:

```java
LoggerFactory.getLogger(
        "com.example.orders.service.OrderService"
);
```

logger có tên `com.example.orders.service.OrderService`.

Một logger có thể kế thừa mức hiệu lực từ logger cha nếu không có mức cấu hình riêng.

Ví dụ:

```text
ROOT = INFO
  └── com.example = DEBUG
        └── com.example.orders = (không khai báo riêng)
             └── OrderService
```

`OrderService` có thể nhận effective level `DEBUG` từ `com.example`.

### 3.2. Configured level khác effective level

Hai khái niệm:

- **Configured level:** mức được cấu hình trực tiếp cho logger đó, có thể `null` nếu logger kế thừa.
- **Effective level:** mức log thực sự được áp dụng sau khi tính đến hierarchy và quy tắc backend.

Ví dụ:

```text
ROOT: configuredLevel=INFO, effectiveLevel=INFO
com.example: configuredLevel=DEBUG, effectiveLevel=DEBUG
com.example.orders: configuredLevel=null, effectiveLevel=DEBUG
```

Một logger không có configured level riêng không có nghĩa là nó không ghi log.

## 4. Cấu hình logger bằng application.yml

Cách phổ biến nhất để thiết lập mức log lúc khởi động là `logging.level`.

```yaml
logging:
  level:
    root: INFO
    com.example.orders: DEBUG
    org.springframework.web: WARN
```

Ý nghĩa:

- Mặc định hệ thống ghi từ INFO trở lên.
- Package `com.example.orders` cho phép xem log DEBUG.
- Spring Web giảm mức chi tiết xuống WARN cho các logger tương ứng.

Ví dụ tương đương trong `application.properties`:

```properties
logging.level.root=INFO
logging.level.com.example.orders=DEBUG
logging.level.org.springframework.web=WARN
```

### 4.1. Một class có thể có level riêng

```properties
logging.level.com.example.orders.service.OrderService=TRACE
```

Cấu hình này nhắm vào logger name cụ thể.

Nhưng không nên bật TRACE hoặc DEBUG rộng khắp trong production lâu dài nếu chưa tính tới:

- Lượng log sinh ra.
- Chi phí disk/network và lưu trữ.
- Dữ liệu có thể bị lộ.
- Ảnh hưởng hiệu năng khi log tần suất cao.

### 4.2. Cấu hình không đồng nghĩa một dòng log chắc chắn được xuất

Nếu đặt:

```properties
logging.level.com.example.orders=INFO
```

thì:

```java
log.debug("Order id={}", orderId);
```

có thể không được xuất vì DEBUG thấp hơn effective level INFO.

Ngoài log level, output còn phụ thuộc backend, appender, filter, sampling và cấu hình collector.

### 4.3. Dùng placeholder cho message

Nên viết:

```java
log.info(
        "Order created: orderId={} customerId={}",
        orderId,
        customerId
);
```

thay vì:

```java
log.info("Order created: " + orderId);
```

Parameterized logging cho phép backend trì hoãn định dạng chuỗi khi level bị tắt. Tuy nhiên, Java vẫn đánh giá các biểu thức argument trước khi gọi logger, nên đừng đưa phép tính tốn kém vào DEBUG log mà không cân nhắc.

## 5. Endpoint /actuator/loggers dùng để làm gì?

Actuator cung cấp endpoint `loggers` để **xem cấu hình logger** và, nếu được phép, **thay đổi mức log tại runtime**.

Ví dụ truy vấn:

```bash
curl http://localhost:8080/actuator/loggers
```

Endpoint có thể cung cấp danh sách logger names và các level mà logging system hỗ trợ.

Để xem một logger cụ thể:

```bash
curl http://localhost:8080/actuator/loggers/com.example.orders
```

Response minh họa:

```json
{
  "configuredLevel": null,
  "effectiveLevel": "INFO"
}
```

Giá trị thực tế phụ thuộc vào cấu hình của ứng dụng. `configuredLevel=null` có thể có nghĩa logger đang kế thừa level từ logger cha.

### 5.1. Vì sao cần đổi level khi ứng dụng đã chạy?

Giả sử production có một lỗi hiếm gặp. Bạn muốn tạm tăng log chi tiết cho package `com.example.orders.payment` trong một khoảng thời gian ngắn để thu thập bằng chứng, nhưng không muốn restart một tiến trình đang phục vụ traffic.

Nếu Actuator loggers endpoint được expose và được bảo vệ phù hợp, bạn có thể thay đổi configured level của logger đó tại runtime.

Đây là một công cụ chẩn đoán hữu ích, đồng thời là **một khả năng điều khiển hệ thống** cần giới hạn quyền truy cập.

## 6. Thay đổi logger level tại runtime

Ví dụ yêu cầu HTTP POST tới loggers endpoint:

```bash
curl -X POST \
  http://localhost:8080/actuator/loggers/com.example.orders.payment \
  -H "Content-Type: application/json" \
  -d '{"configuredLevel":"DEBUG"}'
```

Với endpoint được expose, write operation được cho phép và security phù hợp, yêu cầu này đặt logger `com.example.orders.payment` thành DEBUG.

Đọc lại:

```bash
curl http://localhost:8080/actuator/loggers/com.example.orders.payment
```

Response minh họa:

```json
{
  "configuredLevel": "DEBUG",
  "effectiveLevel": "DEBUG"
}
```

### 6.1. Xóa configured level để logger kế thừa

Bạn có thể gửi `null` để xóa mức cấu hình riêng của logger:

```bash
curl -X POST \
  http://localhost:8080/actuator/loggers/com.example.orders.payment \
  -H "Content-Type: application/json" \
  -d '{"configuredLevel":null}'
```

Khi đó effective level lại phụ thuộc vào logger hierarchy và backend.

### 6.2. Thay đổi này có được lưu vào application.yml không?

**Không.** Việc đổi logger qua Actuator thường thay đổi cấu hình logging **trong tiến trình đang chạy**. Nó không sửa file `application.yml` của project.

Khi application restart, logging system được khởi tạo lại từ các nguồn cấu hình tương ứng; thay đổi runtime trước đó thường không được giữ.

Vì vậy:

- Dùng endpoint để chẩn đoán tạm thời.
- Dùng configuration-as-code để thiết lập chính sách log ổn định.
- Ghi lại quá trình bật/tắt DEBUG nếu ứng dụng có quy trình vận hành yêu cầu audit.

### 6.3. Mỗi replica có logger state riêng

Nếu ứng dụng chạy ba replica:

```text
orders-api replica A
orders-api replica B
orders-api replica C
```

thay đổi logger level qua endpoint của replica A **không tự cập nhật** replica B và C. Đây là trạng thái runtime của từng process.

Nếu muốn thay đổi mức log nhất quán trên toàn bộ cluster, cần công cụ/quy trình vận hành áp dụng cho các instance thích hợp hoặc cập nhật cấu hình triển khai và rollout.

### 6.4. Không mở quyền POST loggers công khai

Khả năng thay đổi log level có thể khiến ứng dụng ghi nhiều dữ liệu nhạy cảm hoặc làm tăng tải I/O. Khi expose endpoint, hãy đặt nó sau authentication/authorization và giới hạn mạng cần thiết.

Không nên cho mọi người dùng Internet gọi POST tùy ý vào `/actuator/loggers`.

## 7. Metrics là gì?

**Metric** là một phép đo có thể quan sát được theo thời gian, thường dùng để tính tỷ lệ, xu hướng hoặc so sánh trạng thái.

Ví dụ:

- Tổng số request xử lý.
- Thời lượng mỗi HTTP request.
- Số tác vụ đang chờ.
- CPU utilization.
- JVM heap used.
- Số lần retry.
- Số kết nối trong pool.
- Số exception hoặc lỗi theo loại.

Nếu logs là nhiều “câu chuyện riêng lẻ”, metrics là các dãy số phù hợp để tính toán và vẽ biểu đồ.

### 7.1. Metric name và tags

Một metric có thể có:

```text
name:  app.orders.created
tags:
  channel: web
  outcome: success
value: 128
```

`name` cho biết đang đo điều gì; `tags` (labels/dimensions) giúp phân nhóm dữ liệu. Ví dụ metric đếm đơn hàng theo channel.

Không nên nhầm tags của metric với text trong log. Tags tạo ra các **time series riêng biệt** trong monitoring backend, nên số lượng giá trị tag ảnh hưởng trực tiếp đến chi phí và hiệu năng hệ thống giám sát.

### 7.2. Ba loại đo phổ biến

| Loại | Mô tả | Ví dụ |
|---|---|---|
| **Counter** | Giá trị tăng dần theo số sự kiện | Số đơn hàng đã tạo |
| **Gauge** | Đo giá trị hiện tại có thể tăng/giảm | Độ sâu hàng đợi |
| **Timer** | Ghi nhận số lần và thời lượng thao tác | Thời gian xử lý đơn |

Ngoài ra Micrometer còn có distribution summary, long task timer và nhiều loại meter khác phù hợp với các use case cụ thể.

## 8. Micrometer và MeterRegistry

Spring Boot sử dụng **Micrometer** như abstraction phổ biến cho metrics.

Các API quan trọng:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Timer;
```

**`MeterRegistry`** là nơi đăng ký, tìm và quản lý meters.

Sơ đồ:

```text
Application code / Auto-configured instrumentation
                    │
                    ▼
               Micrometer API
                    │
                    ▼
               MeterRegistry
                    │
                    ▼
       Registry implementation/export
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
    Prometheus              Other backend
         │                     │
         ▼                     ▼
      Scrape/query         Push/publish/query
```

Spring Boot Actuator và các starter tương ứng thường cung cấp nhiều instrumentation tự động. Muốn xuất metrics sang một backend cụ thể, bạn có thể cần thêm registry dependency và cấu hình exposure/export.

### 8.1. Không nhầm MeterRegistry với HTTP endpoint

Bạn có thể dùng `MeterRegistry` trong code mà chưa expose `/actuator/metrics` qua HTTP.

Ngược lại, endpoint `/actuator/metrics` là một cách **kiểm tra/diagnose** metrics trong application, không nhất thiết là format ingest chuẩn của một monitoring backend.

Ví dụ Prometheus thường thu thập từ endpoint `/actuator/prometheus`, chứ không trực tiếp scrape JSON của `/actuator/metrics`.

## 9. Endpoint /actuator/metrics

Expose:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
```

Sau đó:

```bash
curl http://localhost:8080/actuator/metrics
```

Response có thể liệt kê các metric names đang được registry ghi nhận:

```json
{
  "names": [
    "jvm.memory.used",
    "process.cpu.usage",
    "http.server.requests"
  ]
}
```

Đây là response minh họa. Tên metric thực tế phụ thuộc dependency, version, loại ứng dụng và có hoạt động nào đã phát sinh hay chưa.

### 9.1. Xem một metric cụ thể

```bash
curl http://localhost:8080/actuator/metrics/jvm.memory.used
```

Response minh họa:

```json
{
  "name": "jvm.memory.used",
  "measurements": [
    {
      "statistic": "VALUE",
      "value": 73400320.0
    }
  ],
  "availableTags": [
    {
      "tag": "area",
      "values": ["heap", "nonheap"]
    }
  ]
}
```

`VALUE` và con số trong ví dụ chỉ để minh họa. Các tag và giá trị cụ thể có thể khác.

### 9.2. Lọc metric theo tags

Ví dụ:

```bash
curl "http://localhost:8080/actuator/metrics/jvm.memory.used?tag=area:heap"
```

Query `tag=key:value` cho phép chọn những meter phù hợp với tag được hỗ trợ.

Khi HTTP metrics có tag như method, status hoặc URI template, bạn cũng có thể lọc theo các tag thực tế mà endpoint báo. Không đoán tên/giá trị tag nếu ứng dụng chưa có meter tương ứng.

### 9.3. Vì sao metrics chưa xuất hiện?

Một vài metric chỉ được tạo khi instrumentation có dependency phù hợp hoặc khi operation đầu tiên diễn ra.

Ví dụ, tên `http.server.requests` có thể chưa xuất hiện nếu ứng dụng không phải web application, chưa có request, instrumentation bị vô hiệu hóa, hoặc phiên bản/framework sử dụng convention khác.

Không nên kết luận Actuator bị hỏng chỉ vì một metric name dự đoán trước không có trong danh sách.

## 10. Counter: đếm sự kiện nghiệp vụ

Giả sử bạn muốn biết số lần ứng dụng tạo đơn hàng thành công.

Một service có thể inject `MeterRegistry`:

```java
package com.example.orders;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final MeterRegistry registry;

    public OrderService(MeterRegistry registry) {
        this.registry = registry;
    }

    public void createOrder(String orderId) {
        // Thực hiện nghiệp vụ tạo đơn hàng.
        saveOrder(orderId);

        registry.counter(
                "app.orders.created",
                "channel",
                "web"
        ).increment();
    }

    private void saveOrder(String orderId) {
        // Ví dụ minh họa: triển khai repository thực tế.
    }
}
```

Mỗi khi gọi `increment()`, counter tăng thêm một đơn vị.

### 10.1. Counter đo sự kiện chứ không phải trạng thái hiện tại

Counter phù hợp với “đã xảy ra bao nhiêu lần”:

```text
orders created total = 10
orders created total = 11
orders created total = 12
```

Đừng dùng counter để đo “hiện có bao nhiêu đơn đang chờ”. Trạng thái hiện tại có thể tăng hoặc giảm, nên thường phù hợp với gauge.

### 10.2. Đo rate thay vì nhìn total đơn thuần

Trong một monitoring backend, counter có thể được dùng để tính số sự kiện/giây hoặc sự kiện/phút.

Nếu một instance restart, số counter trong tiến trình có thể trở về 0. Monitoring backend thường có hàm tính rate/increase xử lý counter resets trong điều kiện phù hợp.

Đừng tự lấy hai giá trị counter từ hai thời điểm xa nhau rồi coi hiệu số luôn đúng nếu không xét restart, scrape gaps và backend semantics.

### 10.3. Đặt tên metric nhất quán

Với Micrometer, tên dạng dấu chấm như:

```text
app.orders.created
```

là cách đặt tên dễ đọc. Khi export sang backend, tên có thể được chuyển đổi để phù hợp naming convention.

Ví dụ Prometheus thường dùng dấu gạch dưới và hậu tố đơn vị/loại metric. Không nên hard-code một tên backend-specific vào logic nghiệp vụ nếu có thể dùng naming convention của Micrometer.

## 11. Gauge: quan sát giá trị hiện tại

Gauge phù hợp với trạng thái có thể tăng hoặc giảm:

- Queue depth.
- Số worker đang bận.
- Số kết nối hiện có.
- Số tác vụ đang xử lý.

Ví dụ một object giữ độ sâu hàng đợi:

```java
package com.example.orders;

import java.util.concurrent.atomic.AtomicInteger;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import org.springframework.stereotype.Component;

@Component
public class QueueDepthMonitor {

    private final AtomicInteger depth = new AtomicInteger();

    public QueueDepthMonitor(MeterRegistry registry) {
        registry.gauge(
                "app.queue.depth",
                Tags.of("queue", "orders"),
                depth
        );
    }

    public void setDepth(int value) {
        depth.set(value);
    }
}
```

Khi code cập nhật `depth`, Micrometer có thể quan sát giá trị hiện tại tại thời điểm metric được đọc/publish.

### 11.1. Không tăng gauge như counter

Nếu bạn cần đếm tổng số tasks đã xử lý, dùng counter. Nếu cần đo số tasks đang đợi xử lý, dùng gauge.

Một queue depth có thể là:

```text
09:00 -> 10
09:01 -> 25
09:02 -> 18
09:03 -> 2
```

Chỉ nhìn số cuối không nói được trong giờ qua có bao nhiêu tasks đã đi qua queue; đó là một câu hỏi cần counter khác.

### 11.2. Tránh tạo object gauge tạm rồi mất reference

Micrometer thường giữ tham chiếu yếu với object được đo ở một số cơ chế gauge. Nếu bạn tạo một object chỉ trong constructor/method và không còn strong reference, gauge có thể không hoạt động ổn định khi object bị garbage collected.

Trong ví dụ `QueueDepthMonitor`, field `depth` được giữ bởi bean sống lâu, nên phù hợp cho phép đo.

### 11.3. Khi lấy số queue depth từ hệ thống bên ngoài

Nếu queue nằm ở message broker, bạn cần dùng API hoặc exporter thích hợp để lấy độ sâu hàng đợi. Một local `AtomicInteger` trong ứng dụng không tự phản ánh queue depth thật của Kafka/RabbitMQ/SQS.

Chỉ đặt tên metric “queue depth” khi nguồn dữ liệu thật sự có nghĩa như vậy.

## 12. Timer: đo thời lượng và số lần thực hiện

Timer là loại meter quan trọng cho latency.

Ví dụ:

```java
package com.example.orders;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final MeterRegistry registry;

    public PaymentService(MeterRegistry registry) {
        this.registry = registry;
    }

    public void pay(String orderId) {
        Timer.Sample sample = Timer.start(registry);

        try {
            performPayment(orderId);
        } finally {
            sample.stop(registry.timer(
                    "app.payment.duration",
                    "operation",
                    "pay"
            ));
        }
    }

    private void performPayment(String orderId) {
        // Gọi payment gateway và xử lý kết quả.
    }
}
```

`Timer.Sample` ghi nhận thời điểm bắt đầu, rồi `stop(...)` ghi thời lượng vào một Timer.

Dùng `finally` giúp thời lượng vẫn được ghi khi operation ném exception. Tuy nhiên, timer đơn giản này chưa phân loại outcome.

### 12.1. Timer thường cung cấp những phép đo nào?

Tùy registry/backend, một Timer có thể hỗ trợ:

- Số lần ghi nhận (`count`).
- Tổng thời gian (`total time`).
- Thời gian lớn nhất trong một khoảng ghi nhận (`max`), tùy implementation/window.
- Histogram buckets và percentile estimates nếu được bật.
- Các thống kê khác theo registry.

Không nên giả định histogram hay P95 được xuất mặc định cho mọi Timer. Cần cấu hình distribution statistics thích hợp.

### 12.2. Đo cả kết quả thành công và lỗi

Ví dụ:

```java
public void pay(String orderId) {
    Timer.Sample sample = Timer.start(registry);
    String outcome = "success";

    try {
        performPayment(orderId);
    } catch (RuntimeException ex) {
        outcome = "error";
        throw ex;
    } finally {
        sample.stop(registry.timer(
                "app.payment.duration",
                "operation", "pay",
                "outcome", outcome
        ));
    }
}
```

`outcome` chỉ có hai giá trị cố định `success` và `error`, giúp giữ cardinality thấp.

Nếu gọi một gateway có retry, hãy xác định Timer đang đo một attempt, toàn bộ workflow hay end-to-end response time. Tên metric và documentation cần phản ánh đúng điều được đo.

## 13. Histogram và percentile: đọc độ trễ đúng cách

Giả sử 100 request có thời lượng:

- 90 request hoàn thành trong 100 ms.
- 9 request hoàn thành trong 500 ms.
- 1 request mất 5 giây.

Trung bình có thể trông khá tốt, nhưng request chậm nhất vẫn ảnh hưởng trải nghiệm người dùng.

Các percentile được quan tâm:

- **P50:** khoảng 50% request có thời lượng không vượt quá mức này.
- **P95:** khoảng 95% request có thời lượng không vượt quá mức này.
- **P99:** khoảng 99% request có thời lượng không vượt quá mức này.

### 13.1. Percentile không phải trung bình

Hai hệ thống có cùng average latency nhưng tail latency rất khác nhau.

Ví dụ:

```text
System A: đa số request 100 ms, gần như không có outlier
System B: đa số request 20 ms, nhưng có một số request 5 s
```

Trung bình có thể đánh lừa. Với API production, người vận hành thường theo dõi P95 hoặc P99 bên cạnh throughput và error rate.

### 13.2. Histogram có chi phí

Khi bật histogram buckets, số time series tăng theo:

```text
metric × label combinations × buckets
```

Vì vậy, không nên bật histogram cho mọi timer có nhiều tags không kiểm soát. Hãy chọn những latency metrics quan trọng, với số lượng tag values giới hạn và buckets phù hợp với mục tiêu SLO.

### 13.3. Đừng trung bình các P95 của nhiều instance

P95 tính riêng trên mỗi instance không thể được tổng hợp chính xác bằng phép tính trung bình đơn giản.

Nếu cần P95 toàn hệ thống, dùng histogram hoặc cơ chế aggregation phù hợp mà monitoring backend hỗ trợ. Đây là lý do thiết kế metric type và export format quan trọng, chứ không chỉ chọn một con số để hiển thị.

## 14. Metric tags và bài toán cardinality

Tags giúp phân nhóm metric, nhưng có rủi ro rất lớn nếu giá trị của chúng gần như vô hạn.

### 14.1. Tag cardinality thấp

Ví dụ tốt:

```text
app.orders.created
  channel=web
  result=success
```

Một vài giá trị `channel`/`result` có thể được kiểm soát:

```text
channel ∈ {web, mobile, partner}
result  ∈ {success, failure}
```

Số tổ hợp tag hữu hạn, dễ theo dõi.

### 14.2. Tag cardinality cao

Không nên:

```java
registry.counter(
        "app.orders.created",
        "orderId",
        orderId
).increment();
```

Nếu mỗi order có ID khác nhau, hệ thống tạo một time series mới cho gần như mỗi đơn hàng.

Tương tự, tránh dùng:

- `userId`.
- `sessionId`.
- Raw request URL chứa ID.
- Email address.
- Trace ID.
- UUID tạo mới cho từng request.
- Error message tùy ý làm tag.

Những giá trị đó phù hợp hơn với **logs hoặc traces**, không phải metrics tags.

### 14.3. Vì sao cardinality tăng nhanh?

Giả sử một metric có:

```text
10 routes
× 5 status categories
× 4 methods
× 3 instances
= 600 time series
```

Nếu thêm `userId` với 100.000 giá trị, số tổ hợp tiềm năng có thể tăng cực lớn.

Đây là phép tính minh họa về cardinality, không phải dự báo số time series thực tế. Số lượng phụ thuộc tổ hợp thực sự xuất hiện và cách backend xử lý.

### 14.4. Dùng URI template thay raw path

Với HTTP request metric, giá trị tag như:

```text
/orders/{id}
```

thường phù hợp hơn:

```text
/orders/123456
/orders/123457
/orders/123458
```

Spring Boot web instrumentation thường cố gắng dùng route template khi có thông tin routing phù hợp. Nhưng các request không match hoặc custom tags có thể tạo cardinality ngoài ý muốn nếu bạn ghi raw path.

## 15. Những metrics có sẵn thường hữu ích

Khi có Actuator/Micrometer và instrumentation tương ứng, ứng dụng có thể cung cấp nhiều metrics.

| Nhóm | Ví dụ metric names | Ý nghĩa |
|---|---|---|
| JVM | `jvm.memory.used` | Bộ nhớ JVM đang sử dụng |
| JVM | `jvm.gc.pause` | Thời lượng GC pause |
| Threads | `jvm.threads.live` | Số Java threads còn sống |
| CPU | `process.cpu.usage` | CPU usage của process theo registry |
| Process | `process.uptime` | Thời gian process đã chạy |
| HTTP | `http.server.requests` | Số lượng/thời lượng HTTP server requests |
| Database pool | `hikaricp.connections.active` | Số kết nối active khi có HikariCP instrumentation |
| Executor | `executor.active` hoặc convention tương ứng | Hoạt động executor nếu có instrumentation |
| Disk | `disk.free` | Dung lượng đĩa khả dụng trong nguồn đo phù hợp |

Tên chính xác, sự hiện diện và các tag phụ thuộc phiên bản Spring Boot, Micrometer, registry, platform và thư viện runtime. Đừng coi bảng này là một danh sách chắc chắn sẽ xuất hiện trong mọi ứng dụng.

### 15.1. JVM metrics giúp gì?

Một biểu đồ `jvm.memory.used` có thể cho thấy memory usage tăng dần. Nhưng chỉ dựa vào heap used mà kết luận memory leak là vội vàng.

Bạn còn cần xem:

- Heap max/committed.
- GC frequency và pause time.
- Allocation rate nếu có instrumentation.
- Workload và traffic.
- Thread count.
- Container memory limits.

Metrics định hướng điều tra; để chẩn đoán memory leak có thể cần profiler, heap dump và phân tích sâu hơn.

### 15.2. HTTP metrics nói được điều gì?

Với `http.server.requests`, bạn có thể quan sát:

- Request count và rate.
- Duration.
- Status code/outcome groups.
- HTTP method.
- URI template.
- Exception tag khi instrumentation ghi nhận được.

Một số status labels có thể bị thay đổi/mất chi tiết tùy backend; kiểm tra tags có thực tế trước khi viết dashboard query.

## 16. HTTP traffic: rate, errors, duration, saturation

Một khung quan sát hữu ích cho service là **traffic, errors, latency và saturation**.

### 16.1. Traffic / request rate

Đo số request/giây hoặc request/phút.

Ví dụ:

```text
09:00 - 100 req/s
09:05 - 250 req/s
09:10 - 270 req/s
```

Traffic tăng không tự động nghĩa là có lỗi. Nó có thể do chiến dịch marketing, batch clients hoặc một client gọi quá thường xuyên.

### 16.2. Error rate

Ví dụ:

```text
total requests = 10,000
failed requests = 200
error rate = 2%
```

Bạn cần định nghĩa “failed” cho hệ thống:

- HTTP 5xx thường phản ánh server error.
- HTTP 4xx có thể là lỗi input bình thường hoặc sự cố tùy API.
- Timeout ở upstream proxy có thể không tạo HTTP response từ ứng dụng.
- Business failure có thể vẫn trả HTTP 200 nếu contract thiết kế như vậy.

Do đó error rate của HTTP và business failure rate có thể khác nhau.

### 16.3. Duration / latency

Theo dõi P50/P95/P99 thay vì chỉ average.

Một API xử lý rất nhanh ở đa số request nhưng có P99 cao vẫn có thể gây trải nghiệm xấu.

### 16.4. Saturation

Đo mức độ tài nguyên gần giới hạn:

- Connection pool active/idle/pending.
- Queue depth.
- Thread pool saturation.
- CPU.
- Memory/GC.
- Disk.
- Open connections.

Saturation tăng cùng latency và error rate là dấu hiệu đáng điều tra. Tuy nhiên, đừng gán ngay nguyên nhân nếu chưa kiểm tra workload và dependency.

## 17. Prometheus và /actuator/prometheus

Prometheus là một backend phổ biến để lưu và truy vấn time series. Với Spring Boot, bạn thường cần thêm Micrometer Prometheus registry dependency.

Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Maven:

```xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
```

Expose endpoint:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

Sau đó:

```bash
curl http://localhost:8080/actuator/prometheus
```

Nếu registry và endpoint được cấu hình phù hợp, response thường dùng Prometheus/OpenMetrics exposition format thay vì JSON của Actuator metrics endpoint.

### 17.1. Hai endpoint metrics khác nhau

| Endpoint | Mục đích chủ yếu | Format điển hình |
|---|---|---|
| `/actuator/metrics` | Xem danh sách và chi tiết metric qua Actuator | JSON |
| `/actuator/prometheus` | Để Prometheus scrape metrics | Text exposition |

Đừng cấu hình Prometheus scrape `/actuator/metrics` chỉ vì tên endpoint nghe có vẻ đúng. Hãy dùng đúng endpoint và registry phù hợp với backend.

### 17.2. Prometheus cần cấu hình scrape

Chỉ bật endpoint chưa có nghĩa Prometheus đã biết nơi thu thập.

Ví dụ một scrape config tối giản:

```yaml
scrape_configs:
  - job_name: "orders-api"
    metrics_path: "/actuator/prometheus"
    static_configs:
      - targets: ["localhost:8080"]
```

Ví dụ giả định Prometheus có thể kết nối tới `localhost:8080` từ nơi nó chạy. Trong container/Kubernetes, `localhost` của Prometheus thường không phải localhost của application container; phải dùng địa chỉ service/target phù hợp.

### 17.3. Backend conventions có thể đổi tên metric

Micrometer code:

```java
registry.counter("app.orders.created").increment();
```

Trong Prometheus output, tên có thể được chuẩn hóa và có suffix theo kiểu meter/backend. Hãy xem exposition thực tế để viết query đúng, thay vì dựa vào tên Java method trong mọi trường hợp.

## 18. Health endpoint trả lời câu hỏi gì?

`/actuator/health` cung cấp đánh giá về trạng thái sức khỏe theo các `HealthIndicator` được áp dụng.

Ví dụ đơn giản:

```bash
curl http://localhost:8080/actuator/health
```

Response:

```json
{
  "status": "UP"
}
```

Nếu indicator quan trọng báo lỗi:

```json
{
  "status": "DOWN"
}
```

Thông tin thực tế còn phụ thuộc health aggregation, health groups, các indicators được bật và cách application quản lý trạng thái.

### 18.1. UP không phải bảo đảm nghiệp vụ hoàn hảo

`UP` có nghĩa các health checks được cấu hình đánh giá là healthy tại thời điểm được kiểm tra.

Nó **không có nghĩa**:

- Mọi endpoint đang đáp ứng trong thời gian cho phép.
- Không có request thất bại.
- Database không bao giờ timeout.
- Mọi queue đã trống.
- Mọi external service đều khả dụng.
- Không có memory leak.

Health check là một tín hiệu hữu ích nhưng có phạm vi giới hạn.

### 18.2. Health và HTTP status

Trong cấu hình Actuator thông thường, một số health statuses được ánh xạ sang HTTP status:

- `UP` thường tương ứng HTTP 200.
- `DOWN` hoặc `OUT_OF_SERVICE` thường tương ứng HTTP 503.
- Custom statuses có thể yêu cầu mapping phù hợp.

Lúc thiết kế readiness probe, orchestrator thường quan tâm HTTP status thành công/thất bại hơn toàn bộ JSON details.

### 18.3. Health details có thể nhạy cảm

Ví dụ datasource health indicator có thể cung cấp một số chi tiết của dependency. Nên hạn chế việc hiển thị details với người không có quyền.

Property thường dùng:

```yaml
management:
  endpoint:
    health:
      show-details: never
```

Các chế độ có thể bao gồm `never`, `when_authorized` và `always` tùy phiên bản. Trong production, tránh bật `always` công khai nếu details có thể tiết lộ hạ tầng.

## 19. Viết HealthIndicator tùy chỉnh

Spring Boot cho phép đăng ký `HealthIndicator` cho một subsystem mà ứng dụng muốn kiểm tra.

Ví dụ một kiểm tra cục bộ đơn giản:

```java
package com.example.orders.health;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class OrderProcessingHealthIndicator
        implements HealthIndicator {

    private final OrderProcessingState state;

    public OrderProcessingHealthIndicator(
            OrderProcessingState state
    ) {
        this.state = state;
    }

    @Override
    public Health health() {
        if (state.isOperational()) {
            return Health.up()
                    .withDetail("component", "order-processing")
                    .build();
        }

        return Health.down()
                .withDetail("component", "order-processing")
                .build();
    }
}
```

Trong đó `OrderProcessingState` là abstraction do ứng dụng tự định nghĩa, ví dụ:

```java
package com.example.orders.health;

import org.springframework.stereotype.Component;

@Component
public class OrderProcessingState {

    public boolean isOperational() {
        // Ví dụ: kiểm tra trạng thái cục bộ nhanh.
        return true;
    }
}
```

Indicator trên trả trạng thái tại thời điểm được truy vấn.

### 19.1. Đặt tên và aggregation

Một bean `OrderProcessingHealthIndicator` thường được ánh xạ thành health contributor với tên suy ra như `orderProcessing`.

Nó có thể tham gia health tổng hợp, tùy HealthContributorRegistry và health groups được cấu hình.

Đừng thêm một indicator báo DOWN vì điều kiện không thiết yếu nếu điều đó khiến toàn bộ service bị orchestrator loại khỏi traffic không cần thiết.

### 19.2. Health checks phải nhanh và có giới hạn

Không nên thực hiện một truy vấn rất nặng hoặc gọi một external service không có timeout mỗi khi health endpoint được gọi.

Health probe có thể chạy thường xuyên. Một check bị treo có thể tự làm tăng tải và làm sai lệch trạng thái vận hành.

Nếu cần kiểm tra dependency ngoài, hãy thiết kế:

- Timeout ngắn và rõ ràng.
- Chính sách cache khi thích hợp.
- Ranh giới health group phù hợp.
- Phân biệt dependency bắt buộc và optional.
- Tránh side effects.

## 20. Liveness và readiness khác nhau thế nào?

Hai tín hiệu đặc biệt quan trọng trong container orchestration.

**Liveness** trả lời:

> “Tiến trình này có đang ở trạng thái cần được restart hay không?”

**Readiness** trả lời:

> “Instance này có sẵn sàng nhận traffic hay không?”

Hai câu hỏi không giống nhau.

| Tình huống | Liveness | Readiness |
|---|---|---|
| Instance mới khởi động, chưa hoàn tất warm-up | Thường có thể live | Chưa ready |
| Instance hoạt động bình thường | Live | Ready |
| Instance muốn tạm ngừng nhận traffic | Vẫn live | Not ready |
| Tiến trình bị lỗi không thể phục hồi | Có thể không live | Not ready |
| Một dependency ngoài bị sự cố | Không nhất thiết ảnh hưởng liveness | Có thể ảnh hưởng readiness nếu là dependency bắt buộc |

### 20.1. Vì sao không gộp tất cả dependency vào liveness?

Giả sử database tạm thời mất kết nối trong 30 giây. Nếu liveness của mọi application instance phụ thuộc trực tiếp vào database, orchestrator có thể restart liên tục tất cả instances đúng lúc database đang có sự cố.

Điều này có thể tạo một **restart storm** và làm tình huống xấu hơn.

Liveness nên phản ánh trạng thái cục bộ cho thấy process thật sự cần restart. Dependency availability thường phù hợp hơn để đánh giá readiness hoặc một metric/alert riêng, tùy thiết kế.

### 20.2. Readiness không phải metric latency

Readiness chỉ cho phép/không cho phép nhận traffic theo chính sách. Một instance có thể “ready” nhưng vẫn chậm.

Vì vậy cần kết hợp readiness với request duration, error rate, queue depth và resource metrics.

## 21. Spring Boot availability states

Spring Boot cung cấp abstraction `ApplicationAvailability`, với hai nhóm trạng thái:

- `LivenessState`.
- `ReadinessState`.

Ví dụ các trạng thái tiêu biểu:

```text
LivenessState.CORRECT
LivenessState.BROKEN

ReadinessState.ACCEPTING_TRAFFIC
ReadinessState.REFUSING_TRAFFIC
```

Trong vòng đời khởi động thông thường:

```text
SpringApplication bắt đầu
        │
        ▼
Chuẩn bị và refresh context
        │
        ▼
ApplicationStartedEvent
        │
        ▼
LivenessState.CORRECT
        │
        ▼
ApplicationRunner / CommandLineRunner
        │
        ▼
ApplicationReadyEvent
        │
        ▼
ReadinessState.ACCEPTING_TRAFFIC
```

Sơ đồ chỉ minh họa những mốc chính; các trạng thái availability còn chịu ảnh hưởng của events và vòng đời dừng ứng dụng.

### 21.1. Đọc trạng thái từ ApplicationAvailability

```java
package com.example.orders;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Service;

@Service
public class AvailabilityReporter {

    private final ApplicationAvailability availability;

    public AvailabilityReporter(
            ApplicationAvailability availability
    ) {
        this.availability = availability;
    }

    public boolean isAcceptingTraffic() {
        return availability.getReadinessState()
                == ReadinessState.ACCEPTING_TRAFFIC;
    }

    public boolean isLive() {
        return availability.getLivenessState()
                == LivenessState.CORRECT;
    }
}
```

Có thể đọc hai trạng thái này trong code nếu có use case phù hợp, nhưng đừng gọi vào mỗi request chỉ để quyết định mọi business action khi readiness đã được orchestration layer sử dụng.

### 21.2. Thay đổi readiness có chủ đích

Ví dụ, một ứng dụng cần tạm ngừng nhận traffic trước khi thực hiện thao tác bảo trì:

```java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;

AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.REFUSING_TRAFFIC
);
```

Khi bảo trì hoàn tất và ứng dụng có thể nhận traffic trở lại:

```java
AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.ACCEPTING_TRAFFIC
);
```

Đây là thao tác điều khiển readiness của chính ứng dụng, không phải một cách “sửa” lỗi dependency bất kỳ. Việc thay đổi state cần được thiết kế cẩn thận để tránh tuyên bố ready khi ứng dụng chưa sẵn sàng.

## 22. Actuator liveness/readiness probes

Khi các health probes được bật, Spring Boot cung cấp health groups tương ứng.

Ví dụ endpoint:

```text
GET /actuator/health/liveness
GET /actuator/health/readiness
```

Trong môi trường Kubernetes được Spring Boot nhận diện, probes có thể được bật tự động; trong các môi trường khác, bạn có thể bật tường minh:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
```

Sau đó kiểm tra:

```bash
curl http://localhost:8080/actuator/health/liveness
curl http://localhost:8080/actuator/health/readiness
```

### 22.1. Mục tiêu của từng probe

Liveness thường dùng trạng thái liveness của ứng dụng; readiness thường dùng readiness state. Các health groups có thể được cấu hình thêm những indicators khác khi phù hợp.

Không nên thêm mọi external dependency vào liveness group chỉ vì muốn “check thật kỹ”. Hãy xem hậu quả nếu dependency thất bại và orchestrator restart nhiều instances.

### 22.2. Probe trên management port riêng

Nếu management server chạy cổng riêng, endpoint health có thể trả lời tốt trong khi server HTTP chính gặp vấn đề. Đó là một hạn chế vận hành cần biết.

Trong một số dòng Spring Boot, bạn có thể cấu hình additional probe paths trên **main server port** để probe kiểm tra đường đi gần với traffic thực tế hơn. Hãy kiểm tra khả năng và property tương ứng của phiên bản đang dùng.

### 22.3. Kubernetes probe ví dụ

Một cấu hình khái niệm:

```yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
```

Đây chỉ là ví dụ về đường dẫn, không phải khuyến nghị timing cho mọi ứng dụng. Hãy chọn startupProbe, failureThreshold, timeoutSeconds và periodSeconds dựa trên startup time và failure behavior thực tế.

## 23. Startup, readiness và shutdown

Observability không chỉ là nhìn trạng thái trong khi request đang xử lý; các tín hiệu lifecycle cũng rất quan trọng.

### 23.1. Startup

Một ứng dụng có thể đã mở cổng TCP nhưng chưa hoàn tất warm-up hoặc startup tasks. Không nên chỉ dựa vào việc port đang listen để kết luận service đã ready.

`ApplicationRunner` và `CommandLineRunner` có thể thực hiện một số tác vụ bắt buộc trước khi mốc ready được công bố.

Nếu runner chặn quá lâu hoặc ném exception, ứng dụng có thể không đến `ApplicationReadyEvent`.

### 23.2. Shutdown

Khi application bắt đầu dừng, readiness có thể được chuyển sang trạng thái từ chối traffic theo lifecycle. Kết hợp điều này với graceful shutdown ở web server và orchestrator giúp hạn chế request bị cắt ngang.

Ví dụ cấu hình web server graceful shutdown trong những phiên bản hỗ trợ:

```yaml
server:
  shutdown: graceful
```

Thời gian cho các phase shutdown có thể được giới hạn qua configuration lifecycle của Spring Boot:

```yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
```

Các property trên có ý nghĩa trong những ứng dụng/embedded servers có hỗ trợ, không làm mọi resource bên ngoài tự được đóng đúng cách.

### 23.3. Theo dõi restart và uptime

Metrics như `process.uptime` hoặc signals từ orchestrator cho biết instance đã chạy bao lâu và có restart bất thường không.

Ví dụ:

```text
Instance A uptime: 3 days
Instance B uptime: 2 minutes
Instance C uptime: 1 minute
```

Nếu B/C liên tục có uptime rất ngắn, hãy điều tra startup failures, liveness restarts, memory limits và deployment events.

Uptime tự thân không giải thích nguyên nhân restart; nó là tín hiệu dẫn đường.

## 24. Application events và tín hiệu vận hành

Spring Boot phát một số lifecycle events mà bạn có thể dùng để quan sát startup.

Ví dụ:

```java
package com.example.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ApplicationLifecycleLogger {

    private static final Logger log =
            LoggerFactory.getLogger(ApplicationLifecycleLogger.class);

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        log.info("Application startup completed and ready");
    }
}
```

Đây là một log sự kiện lifecycle, không thay thế readiness endpoint/metric của orchestrator.

### 24.1. Không làm event listener chặn hệ thống tùy tiện

Một listener chạy đồng bộ có thể kéo dài xử lý event, tùy event multicaster và cấu hình. Hãy tránh đặt tác vụ nặng vào lifecycle listener chỉ để phát một dòng log.

### 24.2. Event khác alert

Một log “Application is ready” là một event. Một cảnh báo “10 lần restart trong 5 phút” thường cần backend hoặc hệ monitoring áp dụng quy tắc qua thời gian.

Không nên trộn hai khái niệm: Spring event không tự động là alert đã được gửi tới đội vận hành.

## 25. Kết nối logs và metrics bằng ngữ cảnh

Giả sử metric:

```text
app.payment.duration{outcome="error"}
```

đột ngột tăng cùng error rate. Bạn cần tìm log liên quan để biết operation nào và dependency nào gây ra.

Log có thể chứa:

```text
Payment failed: orderId=ORD-123 gateway=primary attempt=3
```

Trong khi metric nên có những label ổn định:

```text
operation=pay
gateway=primary
outcome=error
```

**Order ID** thích hợp với log, nhưng không nên là metric tag vì cardinality rất cao.

### 25.1. Correlation ID

Một request ID hoặc trace ID trong log giúp theo dõi các sự kiện thuộc cùng thao tác.

Ví dụ:

```text
traceId=abc123 INFO Order accepted orderId=ORD-123
traceId=abc123 DEBUG Calling payment gateway
traceId=abc123 ERROR Gateway timed out
```

Nếu dùng SLF4J MDC hoặc hệ tracing tích hợp, bạn có thể gắn correlation fields vào logging event.

### 25.2. MDC không tự lan qua mọi thread

MDC thường liên quan tới thread-local state, nên khi dùng `@Async`, executor hoặc reactive programming, cần context propagation phù hợp.

Không nên giả định chỉ đặt `MDC.put("traceId", ...)` trong controller là giá trị tự xuất hiện ở mọi asynchronous callback.

### 25.3. Tracing là mảnh ghép bổ sung

Spring Boot có integration với Micrometer Observation/Tracing trong những phiên bản và dependency thích hợp. Nhưng chỉ thêm `spring-boot-starter-actuator` không có nghĩa ứng dụng đã xuất end-to-end distributed traces tới một backend.

Bạn cần bridge, exporter, sampling và collector phù hợp. Bài này chỉ nêu vị trí của traces trong observability; metrics và logs vẫn có giá trị riêng.

## 26. Một ví dụ Spring Boot có logs, counter và timer

Ta thiết kế một ứng dụng đơn giản xử lý đơn hàng. Mục tiêu là thấy ba tín hiệu cùng xuất hiện:

- Log mô tả sự kiện.
- Counter đếm đơn hàng thành công/thất bại.
- Timer đo thời lượng xử lý.

### 26.1. Dependency Gradle

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Ví dụ giả định project đã quản lý versions và repositories đúng với Spring Boot plugin đang dùng.

### 26.2. Cấu hình application.yml

```yaml
spring:
  application:
    name: orders-api

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus,loggers
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
  metrics:
    tags:
      application: orders-api

logging:
  level:
    root: INFO
    com.example.orders: INFO
```

Đây là cấu hình học tập. Khi triển khai production, các endpoint như `loggers` và `metrics` cần được bảo vệ bằng network/security phù hợp. Không copy nguyên trạng cấu hình exposure vào một service Internet-facing mà chưa thiết kế access control.

### 26.3. Main application

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

### 26.4. Service có metric và logger

```java
package com.example.orders;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);

    private final MeterRegistry registry;

    public OrderService(MeterRegistry registry) {
        this.registry = registry;
    }

    public String create(String orderId, boolean fail) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            log.info("Creating order: orderId={}", orderId);

            if (fail) {
                throw new IllegalStateException(
                        "Simulated order processing failure"
                );
            }

            registry.counter(
                    "app.orders.processed",
                    "outcome",
                    "success"
            ).increment();

            log.info("Order created: orderId={}", orderId);
            return "created";

        } catch (RuntimeException ex) {
            outcome = "error";

            registry.counter(
                    "app.orders.processed",
                    "outcome",
                    "error"
            ).increment();

            log.error(
                    "Order processing failed: orderId={}",
                    orderId,
                    ex
            );
            throw ex;

        } finally {
            sample.stop(registry.timer(
                    "app.orders.processing.duration",
                    "outcome",
                    outcome
            ));
        }
    }
}
```

Ở đây, chỉ có hai giá trị `outcome` cố định, không tạo metric tag từ `orderId`.

Lưu ý ví dụ cố tình log exception ở service để minh họa. Trong ứng dụng thực tế, nếu controller advice cũng ghi cùng exception ở ERROR, hãy xác định rõ error boundary để tránh duplicate stack traces.

### 26.5. Controller

```java
package com.example.orders;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping("/orders")
    public ResponseEntity<String> create(
            @RequestParam String orderId,
            @RequestParam(defaultValue = "false") boolean fail
    ) {
        return ResponseEntity.ok(service.create(orderId, fail));
    }
}
```

Ví dụ này dùng query parameters chỉ để minh họa nhanh; API production nên có validation, request body/contract và error handling thích hợp.

### 26.6. Gọi thử hai request

Thành công:

```bash
curl -X POST "http://localhost:8080/orders?orderId=ORD-001"
```

Lỗi giả lập:

```bash
curl -X POST "http://localhost:8080/orders?orderId=ORD-002&fail=true"
```

Quan sát:

- Log `Order created` hoặc `Order processing failed`.
- Counter `app.orders.processed` với outcome tương ứng.
- Timer `app.orders.processing.duration` có thêm một observation.
- HTTP metrics có thể ghi nhận request và status.
- `/actuator/health` vẫn có thể là `UP` vì một operation thất bại không đồng nghĩa process unhealthy.

### 26.7. Xem metrics sau khi gọi request

```bash
curl http://localhost:8080/actuator/metrics/app.orders.processed
```

Hoặc lọc:

```bash
curl "http://localhost:8080/actuator/metrics/app.orders.processed?tag=outcome:success"
```

Counter values và available tags sẽ phản ánh những operation đã diễn ra trong instance này.

### 26.8. Tăng DEBUG tạm thời

```bash
curl -X POST \
  http://localhost:8080/actuator/loggers/com.example.orders \
  -H "Content-Type: application/json" \
  -d '{"configuredLevel":"DEBUG"}'
```

Trong ví dụ, chỉ tăng logger level. Nếu code không có lời gọi `log.debug(...)`, thay đổi này không tự sinh thêm thông điệp DEBUG từ class đó.

## 27. Tín hiệu vận hành tối thiểu cho một API

Một Spring Boot REST API có thể bắt đầu với tập quan sát cơ bản:

| Tín hiệu | Câu hỏi vận hành | Hành động gợi ý |
|---|---|---|
| Liveness | Process có cần restart? | Probe phù hợp với orchestrator |
| Readiness | Có thể nhận request? | Thêm/bớt instance khỏi traffic |
| Request rate | Đang có bao nhiêu traffic? | Theo dõi tải và capacity |
| Error rate | Bao nhiêu request thất bại? | Alert khi vượt ngưỡng đáng kể |
| P95/P99 latency | Người dùng chậm tới mức nào? | Tìm bottleneck |
| JVM memory + GC | Memory/GC có bất thường? | Điều tra heap/GC |
| CPU usage | Process có gần giới hạn? | Điều tra saturation |
| Database pool | Pool có thiếu connection? | Kiểm tra pool/queries |
| Application logs | Lỗi nào xảy ra và ngữ cảnh gì? | Điều tra incident |
| Application-specific metric | Workflow nghiệp vụ có ổn? | Theo dõi rate, queue, failure |

Tập tín hiệu cần tùy theo loại ứng dụng:

- Batch job: job success/failure/duration.
- Message consumer: processing rate, lag, DLQ count.
- Scheduler: last execution, duration và failure count.
- API gateway: upstream error rate, latency.
- Background worker: queue depth, saturation và retries.

Không có một bộ metric duy nhất phù hợp với mọi service.

## 28. Alerting: không cảnh báo trên mọi log ERROR

Một hệ thống có thể có vài dòng ERROR do lỗi request cá biệt nhưng vẫn phục vụ tốt. Ngược lại, ứng dụng có thể im lặng không ghi ERROR, nhưng số request giảm về 0 hoặc latency tăng mạnh.

Vì vậy, alerting thường dựa vào metrics và service objectives thay vì chỉ đếm string “ERROR” trong log.

### 28.1. Ví dụ điều kiện cảnh báo

- HTTP 5xx rate tăng vượt một tỷ lệ đáng kể trong 5–10 phút.
- Readiness thất bại liên tiếp trên nhiều replicas.
- P95 latency cao liên tục.
- Queue depth tăng không giảm trong khoảng dài.
- Process restart quá thường xuyên.
- Job quan trọng chưa chạy thành công đúng chu kỳ.

Các khoảng thời gian/ngưỡng trên là ví dụ khái niệm. Phải điều chỉnh theo traffic, baseline và mục tiêu hệ thống thực tế; một tỷ lệ lỗi 5% có thể rất nghiêm trọng đối với API chính nhưng không nói hết câu chuyện ở một batch tool thử nghiệm.

### 28.2. Tránh alert fatigue

Nếu alert được kích hoạt quá dễ, đội vận hành nhận quá nhiều thông báo không cần thiết và có thể bỏ lỡ incident thật.

Nên thiết kế:

- Ngưỡng có ý nghĩa đối với người dùng.
- Khoảng thời gian và số mẫu đủ tin cậy.
- Chính sách route/escalation.
- Runbook ngắn cho từng alert.
- Tách informational signals khỏi actionable alerts.

### 28.3. Health không thay thế SLO

Một service có thể luôn báo `UP` nhưng 20% request trả lỗi hoặc P99 latency rất cao.

Vì thế, SLO về availability/success và latency thường phải dựa vào metrics/tracing ở mức traffic, không chỉ probe health.

## 29. Bảo mật Actuator và dữ liệu quan sát

Observability endpoints rất hữu ích nhưng cũng có thể là bề mặt tấn công hoặc rò rỉ thông tin.

### 29.1. Nguyên tắc expose tối thiểu

Nếu chỉ cần health cho orchestrator:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
```

Nếu hệ monitoring cần Prometheus:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

Nếu đội vận hành cần loggers runtime:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus,loggers
```

Nhưng ở trường hợp cuối, phải bổ sung access control phù hợp.

### 29.2. Authentication và authorization

Nếu Spring Security có trên classpath, cách Spring Boot tự cấu hình bảo vệ Actuator còn phụ thuộc security configuration hiện có. Khi ứng dụng định nghĩa `SecurityFilterChain` riêng, bạn cần xem lại policy cho Actuator endpoints: không giả định auto-security mặc định vẫn bảo vệ mọi endpoint như trước.

Có thể dùng network separation, management port, reverse proxy hoặc Spring Security filter chain để chỉ cho phép các chủ thể vận hành truy cập endpoint nhạy cảm.

### 29.3. Những endpoint có rủi ro cao hơn

Ví dụ:

- `env`, `configprops`: có thể tiết lộ tên keys và cấu hình nội bộ.
- `beans`: cho biết cấu trúc application context.
- `heapdump`: có thể chứa dữ liệu nhạy cảm nằm trong memory.
- `threaddump`: cung cấp thông tin runtime internals.
- `loggers`: có khả năng thay đổi mức log tại runtime nếu write operation cho phép.

Không nên expose các endpoint này công khai chỉ để tiện debug.

### 29.4. Lưu ý về log data

Ngay cả khi Actuator được bảo vệ, log file hoặc collector vẫn có thể chứa secrets, token hoặc thông tin người dùng.

Khi ghi log:

- Chọn business IDs không nhạy cảm.
- Không ghi raw passwords/tokens.
- Tránh dump toàn bộ HTTP body.
- Xem xét exception messages có chứa secret hay không.
- Dùng structured logging/escaping để tránh log injection.
- Đặt retention và access control phù hợp.

## 30. Chẩn đoán khi loggers hoặc metrics endpoint không truy cập được

### 30.1. HTTP 404

Một số khả năng:

- Chưa thêm `spring-boot-starter-actuator`.
- Endpoint không được expose qua web.
- Base path đã thay đổi.
- Application dùng non-web environment.
- Prometheus registry chưa có, nên `prometheus` endpoint không khả dụng.
- Endpoint bị disable hoặc configuration/condition không phù hợp.

Kiểm tra dependency, effective configuration và endpoint mapping của ứng dụng thực tế.

### 30.2. HTTP 401 hoặc 403

Endpoint có thể tồn tại nhưng bị security policy chặn.

- `401 Unauthorized` thường liên quan thiếu/không hợp lệ authentication.
- `403 Forbidden` thường liên quan authorization hoặc cơ chế bảo vệ khác.

Không nên tắt Spring Security toàn bộ chỉ để truy cập metrics; hãy cấu hình quyền cho monitoring service hoặc operator theo đúng nhu cầu.

### 30.3. GET loggers được nhưng POST không thành công

Có thể do:

- HTTP write operation bị giới hạn.
- Security permissions.
- CSRF protection trong một số cấu hình.
- Endpoint chỉ cho phép read ở môi trường đó.
- JSON payload không hợp lệ hoặc level không được hỗ trợ.
- Proxy/firewall không cho phép method POST.

Hãy xem HTTP status, log server và security configuration, không kết luận endpoint “không hoạt động” chỉ vì GET thành công.

### 30.4. Metric name không xuất hiện

Có thể:

- Chưa có request/event tạo meter.
- Micrometer registry không được cấu hình như bạn nghĩ.
- Dependency instrumentation chưa có.
- Metric bị filter/disable.
- Tên metric khác vì version.
- Ứng dụng chạy non-web, nên HTTP server metrics không có.
- Custom service không gọi `increment()` hoặc `record()`.

Một số metric có thể được đăng ký lười (lazily) khi event đầu tiên xảy ra.

### 30.5. Prometheus scrape trống hoặc không tìm thấy target

Kiểm tra:

1. Registry dependency có mặt?
2. `/actuator/prometheus` có được expose?
3. Có authentication/network policy phù hợp?
4. Prometheus có kết nối được target thực tế?
5. Scrape path có đúng?
6. TLS/proxy có biến đổi đường dẫn?
7. Target ở container khác có đang bị nhầm `localhost` không?

### 30.6. Health luôn UP dù người dùng báo lỗi

Có thể các indicators hiện có chỉ kiểm tra process/dependencies cơ bản, không phản ánh business failure.

Khi đó cần xem HTTP error rate, latency, logs và custom metrics. Không nên ép health endpoint trở thành phép kiểm tra nghiệp vụ toàn diện cho mọi request.

## 31. Tránh các hiểu lầm phổ biến

### 31.1. “Có actuator là đã có hệ thống monitoring đầy đủ”

Không. Actuator cung cấp endpoints và integrations. Bạn vẫn cần thu thập, lưu metrics, dashboard, alerts và quyền truy cập.

### 31.2. “Đổi logger qua endpoint là sửa application.yml”

Không. Runtime logger level thường chỉ tồn tại trong process đang chạy và có thể mất sau restart.

### 31.3. “Metrics là log được đếm lại”

Không hoàn toàn. Metrics dùng meter types và tags để ghi nhận dữ liệu định lượng; logs là sự kiện chi tiết. Có thể tính metrics từ logs trong một số platform, nhưng hai mô hình có mục đích và chi phí khác nhau.

### 31.4. “Mỗi request nên có metric tag requestId”

Không. Request ID có cardinality rất cao. Dùng logs/traces cho request-specific identifiers; metrics dùng dimensions hữu hạn.

### 31.5. “Health UP nghĩa là ứng dụng không có lỗi”

Không. Health chỉ đại diện cho các health checks đang được cấu hình ở thời điểm kiểm tra.

### 31.6. “Một database DOWN thì liveness cũng nên DOWN”

Không nhất thiết. Dependency ngoài gặp sự cố không phải lúc nào cũng là lý do restart toàn bộ application instances.

### 31.7. “Prometheus đọc JSON từ /actuator/metrics”

Thông thường Prometheus scrape `/actuator/prometheus` khi có Micrometer Prometheus registry và endpoint được expose.

### 31.8. “Bật DEBUG sẽ khiến application tự in mọi dữ liệu cần thiết”

Không. DEBUG chỉ cho phép những log statements đã được viết ở level đó được xuất. Nếu code chưa có log ở vị trí cần điều tra, đổi level không tự sinh thêm thông tin.

### 31.9. “P95 của hệ thống bằng trung bình P95 của từng instance”

Không. Percentiles không thể tổng hợp đúng chỉ bằng tính trung bình các percentiles đã được tính riêng. Cần histogram hoặc phương pháp aggregation phù hợp.

### 31.10. “Gauge và Counter đều chỉ là một con số”

Dù cả hai xuất ra số, chúng biểu diễn semantics khác nhau. Counter đếm sự kiện tích lũy; gauge đo trạng thái hiện tại có thể tăng hoặc giảm.

## 32. Quy trình quan sát một sự cố Spring Boot

Giả sử khách hàng báo API trả lỗi và chậm.

**Bước 1 — Kiểm tra availability**

Xem `/actuator/health` và probes readiness/liveness được cấu hình. Instance có đang bị loại khỏi traffic không? Có restart liên tục không?

**Bước 2 — Kiểm tra traffic và error rate**

Xem request rate, status/outcome metrics. Lỗi bắt đầu từ thời điểm nào? Tập trung ở một endpoint hay toàn hệ thống?

**Bước 3 — Kiểm tra latency**

Xem duration/P95/P99. Tốc độ xấu đi ở tất cả endpoint hay chỉ một operation?

**Bước 4 — Kiểm tra saturation**

CPU, memory/GC, thread pool, DB pool, queue depth. Có resource nào chạm giới hạn không?

**Bước 5 — Đọc logs có ngữ cảnh**

Tìm theo request ID, order ID, component hoặc error code. Xem Throwable/cause chain. Không chỉ tìm từ khóa `ERROR` chung chung.

**Bước 6 — Tạm đổi logger level nếu cần**

Nếu có quyền, tăng DEBUG cho package hẹp qua loggers endpoint trong thời gian ngắn rồi hạ về mức ban đầu.

**Bước 7 — Nếu có tracing, xem đường đi request**

Xác định lời gọi dependency nào chiếm thời gian hoặc bị timeout.

**Bước 8 — Kiểm tra thay đổi gần thời điểm lỗi**

Deployment, config, scaling, network policy, database maintenance hoặc thay đổi traffic.

**Bước 9 — Đánh giá impact và xử lý**

Rollback, scale, giảm tải, sửa dependency hoặc điều chỉnh cấu hình theo đúng nguyên nhân. Không restart hàng loạt chỉ vì một indicator báo DOWN.

**Bước 10 — Sau sự cố**

Bổ sung metric/log/alert nào còn thiếu để lần sau phát hiện và chẩn đoán nhanh hơn.

Một luồng quan sát tốt đi từ **xu hướng tổng thể** đến **trường hợp cụ thể**, sau đó mới đi tới nguyên nhân kỹ thuật.

## 33. Bài thực hành

### Bài 1 — Kích hoạt Actuator

Thêm `spring-boot-starter-actuator` vào Spring Boot project. Khởi động rồi gọi `GET /actuator/health`. Quan sát JSON status.

### Bài 2 — Phân biệt configuredLevel và effectiveLevel

Cấu hình `logging.level.root=INFO` và `logging.level.com.example=DEBUG`. Expose `loggers`, truy vấn một logger thuộc `com.example` và giải thích vì sao `configuredLevel` có thể là `null` nhưng `effectiveLevel` là DEBUG.

### Bài 3 — Đổi log level tại runtime

Dùng POST `/actuator/loggers/com.example` để đặt DEBUG, phát một số request, rồi đặt `configuredLevel=null`. Kiểm tra behavior và xác nhận file cấu hình không bị sửa.

### Bài 4 — Đếm sự kiện bằng Counter

Inject `MeterRegistry` và tạo counter `app.orders.created`. Gọi service ba lần, xem giá trị qua `/actuator/metrics/app.orders.created`.

### Bài 5 — Phân loại success và error

Tạo metric `app.orders.processed` với tag `outcome=success|error`. Thử hai tình huống và dùng query `tag=outcome:...` để lọc.

### Bài 6 — Tạo Gauge

Đăng ký gauge `app.queue.depth` từ một `AtomicInteger` được bean giữ strong reference. Thay đổi giá trị và xem metric.

### Bài 7 — Đo thời gian bằng Timer

Dùng `Timer.Sample` quanh một method có giả lập độ trễ. Xem count, total time và các statistics hiện có. Thử exception để xác nhận `finally` vẫn ghi thời lượng.

### Bài 8 — Kiểm tra HTTP metrics

Tạo controller `GET /products/{id}`, gửi nhiều request thành công và lỗi. Xem `http.server.requests` và các tags thực tế. Không tự thêm product ID làm metric tag.

### Bài 9 — Khảo sát JVM metrics

Quan sát `jvm.memory.used`, `jvm.threads.live`, `jvm.gc.pause` và `process.cpu.usage` nếu có. Giải thích mỗi metric và hạn chế khi suy luận nguyên nhân.

### Bài 10 — Kích hoạt Prometheus

Thêm `micrometer-registry-prometheus`, expose `prometheus` rồi truy cập `/actuator/prometheus`. So sánh format với `/actuator/metrics`.

### Bài 11 — Thử liveness và readiness

Bật probes, truy cập `/actuator/health/liveness` và `/actuator/health/readiness`. Giải thích vì sao trạng thái có thể khác nhau trong giai đoạn khởi động.

### Bài 12 — Custom HealthIndicator

Tạo một `HealthIndicator` dựa trên trạng thái cục bộ. Cho nó lần lượt báo UP/DOWN, quan sát health aggregation và HTTP response theo cấu hình.

### Bài 13 — Xem ảnh hưởng ApplicationRunner tới readiness

Tạo một `ApplicationRunner` thực hiện tác vụ ngắn trước khi sẵn sàng nhận traffic. Quan sát mốc `ApplicationReadyEvent` và trạng thái readiness khi khởi động.

### Bài 14 — Tránh high-cardinality tags

Viết một counter có `orderId` làm tag, rồi giải thích số lượng time series có thể tăng theo mỗi order. Sửa thành `channel`/`outcome` hữu hạn.

### Bài 15 — Bảo vệ Actuator

Cấu hình endpoint exposure tối thiểu. Nếu có Spring Security, chỉ cho phép role/authority vận hành truy cập `loggers` và metrics nhạy cảm. Kiểm tra phản hồi 401/403 và không mở công khai các endpoint nội bộ.

### Bài 16 — Xây mini-dashboard

Từ các metrics có sẵn, thiết kế một dashboard có request rate, HTTP error rate, P95 latency, JVM heap và process uptime. Ghi rõ mỗi panel trả lời câu hỏi nào.

### Bài 17 — Thiết kế alert có ý nghĩa

Chọn một API thử nghiệm, xác định SLO đơn giản, tạo điều kiện cảnh báo khi lỗi hoặc latency duy trì xấu trong một khoảng thời gian. Giải thích vì sao không alert trên một log ERROR cá biệt.

### Bài 18 — Quy trình incident

Giả lập timeout ở một downstream service. Dùng health, request metrics, logs và (nếu có) traces để chẩn đoán. Ghi lại tín hiệu nào xuất hiện trước, tín hiệu nào giúp xác định nguyên nhân và điều gì còn thiếu.

## 34. Tài liệu tham khảo chính thức

- [Spring Boot Reference — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): danh sách endpoint, exposure, access và security.
- [Spring Boot Reference — Monitoring and Management](https://docs.spring.io/spring-boot/reference/actuator/index.html): tổng quan production-ready features.
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer, MeterRegistry, metrics export và custom instrumentation.
- [Spring Boot Reference — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): cấu hình logger levels và logging system.
- [Spring Boot Reference — Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-availability): liveness/readiness states và availability events.
- [Micrometer Documentation](https://docs.micrometer.io/micrometer/reference/): Counter, Gauge, Timer, registries, tags và distribution statistics.
- [Prometheus Documentation — Exposition Formats](https://prometheus.io/docs/instrumenting/exposition_formats/): cơ chế scrape và format metrics.
- [Spring Boot API — HealthIndicator](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/health/HealthIndicator.html): custom health contributions.

**Điều cốt lõi:** `loggers` giúp điều chỉnh độ chi tiết của những sự kiện bạn cần đọc; `metrics` giúp đo tần suất, độ trễ, lỗi và mức sử dụng tài nguyên theo thời gian; `health`, `liveness` và `readiness` giúp hệ thống vận hành quyết định trạng thái của một instance. Một ứng dụng được quan sát tốt không chỉ bật nhiều endpoint, mà còn chọn đúng tín hiệu, giữ metric tags có cardinality thấp, bảo vệ dữ liệu và quyền truy cập, biết khi nào cần nhìn vào logs hay metrics, và kết nối chúng với quy trình xử lý sự cố có thể thực hiện được.
