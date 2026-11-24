# Endpoint /actuator/metrics để tìm và đọc phép đo

Spring Boot Actuator cung cấp endpoint `/actuator/metrics` để khám phá tên các meter đang có trong ứng dụng và đọc số đo của một meter cụ thể. Endpoint này hữu ích khi phát triển instrumentation, kiểm tra metric tự động do Spring Boot tạo ra và điều tra nhanh một giá trị đang được Micrometer quản lý.

Endpoint có hai thao tác chính: gọi `/actuator/metrics` để xem danh sách tên meter; gọi `/actuator/metrics/{metricName}` để đọc các measurement của một meter, có thể lọc theo tag. Kết quả là JSON phản ánh dữ liệu hiện có trong `MeterRegistry` tại thời điểm truy vấn.

Endpoint này phục vụ việc kiểm tra và chẩn đoán. Nó không phải API truy vấn lịch sử như PromQL và cũng không phải định dạng exposition mà Prometheus scrape. Với Prometheus, endpoint chuyên dụng thường là `/actuator/prometheus` khi ứng dụng có Prometheus registry.

## 1. Vai trò của endpoint /actuator/metrics

Trong ứng dụng thuộc module OBSERVABILITY_INSTRUMENTATION_MICROMETER, các component có thể đăng ký `Counter`, `Gauge`, `Timer`, `DistributionSummary` hoặc function-tracking meter thông qua `MeterRegistry`. Spring Boot còn có thể tự đăng ký meter từ JVM, HTTP server, datasource, cache và các thành phần được hỗ trợ.

Endpoint `/actuator/metrics` giúp quan sát những meter đó mà không cần viết controller riêng. Có thể dùng nó để:

- Khám phá metric name thực tế đang được đăng ký.
- Kiểm tra meter tùy chỉnh sau khi gọi một luồng nghiệp vụ.
- Xem loại measurement mà meter cung cấp, chẳng hạn `COUNT`, `TOTAL_TIME`, `MAX` hoặc `VALUE`.
- Khám phá tag key và các tag value có sẵn.
- Lọc một meter theo tag để kiểm tra từng nhóm dữ liệu.
- Phát hiện metric chưa được đăng ký, tag sai hoặc tên metric không đúng với dự kiến.

Endpoint trả về snapshot hiện tại từ registry. Nó không lưu lịch sử theo thời gian và không thay thế backend giám sát.

## 2. Thêm Actuator và expose endpoint metrics

Với Maven, thêm Spring Boot Actuator vào ứng dụng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Micrometer thường đã được đưa vào thông qua các dependency quản lý metrics của Spring Boot. Nếu ứng dụng dùng một registry cụ thể như Prometheus hoặc OTLP, cần thêm dependency registry tương ứng theo kiến trúc export.

Endpoint web không tự động được expose chỉ vì Actuator có trên classpath. Cấu hình `application.yml` để expose `metrics`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - metrics
```

Nếu chỉ cần endpoint metrics trong môi trường phát triển, có thể expose riêng endpoint đó theo policy của dự án. Không nên expose toàn bộ actuator endpoint một cách tùy tiện.

Với cấu hình mặc định, URL thường là:

```text
http://localhost:8080/actuator/metrics
```

URL thực tế còn phụ thuộc `management.server.port`, `management.endpoints.web.base-path`, context path và cấu hình reverse proxy. Nếu management server chạy ở port riêng, hãy dùng port đó thay cho cổng ứng dụng.

## 3. Liệt kê các tên meter

Gửi GET đến `/actuator/metrics` để nhận danh sách tên meter mà registry đang cung cấp:

```bash
curl.exe -i http://localhost:8080/actuator/metrics
```

Phản hồi thường có cấu trúc tương tự:

```json
{
  "names": [
    "application.ready.time",
    "http.server.requests",
    "jvm.memory.used",
    "process.cpu.usage",
    "shop.orders.created",
    "shop.checkout.duration"
  ]
}
```

Danh sách trên chỉ là ví dụ minh họa. Tên và số lượng meter phụ thuộc dependency, binder, cấu hình và những meter đã được đăng ký trong ứng dụng.

### 3.1. Tên trong endpoint là tên Micrometer

Endpoint metrics làm việc với tên meter trong `MeterRegistry`. Ví dụ, nếu code đăng ký:

```java
Counter.builder("shop.orders.created")
        .description("Number of successfully created orders")
        .register(registry);
```

thì tên cần dùng để tra cứu trong endpoint thường là `shop.orders.created`.

Đừng tự đổi tên thành `shop_orders_created_total` khi gọi `/actuator/metrics` chỉ vì Prometheus export counter với tên đã chuẩn hóa. Endpoint Actuator và endpoint Prometheus có mục đích, cách biểu diễn khác nhau.

### 3.2. Metric chỉ xuất hiện khi meter được đăng ký

Danh sách tên phản ánh meter mà registry biết tại thời điểm truy vấn. Một metric tùy chỉnh có thể chưa xuất hiện nếu:

- Bean chứa instrumentation chưa được tạo do điều kiện cấu hình.
- Đường nghiệp vụ chưa khởi tạo meter theo cách mà ứng dụng đang dùng.
- Một `MeterFilter` từ chối meter.
- Tên metric bị nhập sai khi tra cứu.
- Meter được đăng ký vào registry khác với registry mà Actuator endpoint đang sử dụng.

Với các meter được đăng ký tĩnh trong constructor của bean singleton, chúng thường có mặt sau khi application context khởi động thành công. Với meter chỉ được tạo khi một nhánh code chạy, hãy kích hoạt nhánh đó trước khi kết luận metric không tồn tại.

## 4. Đọc một meter cụ thể

Sau khi tìm được tên, gọi endpoint với tên meter ở phần path:

```bash
curl.exe -i http://localhost:8080/actuator/metrics/shop.orders.created
```

Ví dụ phản hồi cho một counter:

```json
{
  "name": "shop.orders.created",
  "description": "Number of successfully created orders",
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 42.0
    }
  ],
  "availableTags": [
    {
      "tag": "channel",
      "values": ["web", "mobile"]
    }
  ]
}
```

Các trường thường gặp:

| Trường | Ý nghĩa |
| --- | --- |
| `name` | Tên meter theo registry mà endpoint đang đọc. |
| `description` | Mô tả meter nếu được khai báo. |
| `baseUnit` | Đơn vị cơ sở nếu meter cung cấp. |
| `measurements` | Danh sách các thống kê và giá trị hiện tại. |
| `availableTags` | Các tag key và value có thể dùng để lọc meter. |

Một meter có thể trả về nhiều measurement. Ý nghĩa cụ thể phụ thuộc loại meter và registry. Không nên giả định mọi meter đều có cùng tập statistic.

## 5. Hiểu measurements theo từng loại meter

Endpoint không trả về một trường `value` chung cho tất cả loại meter. Thay vào đó, `measurements` chứa các cặp `statistic` và `value`.

### 5.1. Counter

Counter thường cung cấp statistic `COUNT`, thể hiện tổng số lần tăng tích lũy:

```json
{
  "name": "shop.orders.created",
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 42.0
    }
  ],
  "availableTags": []
}
```

Nếu gọi `increment()` thêm một lần, lần truy vấn sau có thể thấy count tăng lên 43. Endpoint chỉ cho biết giá trị tại thời điểm đọc; muốn tính tốc độ tăng theo thời gian cần một hệ thống lưu mẫu và phép tính như `rate()` hoặc `increase()`.

### 5.2. Gauge

Gauge thường cung cấp statistic `VALUE`, thể hiện trạng thái tại thời điểm callback được đọc:

```json
{
  "name": "app.queue.depth",
  "measurements": [
    {
      "statistic": "VALUE",
      "value": 7.0
    }
  ],
  "availableTags": []
}
```

Giá trị có thể tăng hoặc giảm giữa các lần gọi endpoint. Nếu queue thay đổi sau khi truy vấn, kết quả JSON trước đó không tự cập nhật; cần gọi lại endpoint để lấy snapshot mới.

### 5.3. Timer

Timer thường cung cấp các statistic như `COUNT`, `TOTAL_TIME` và `MAX`:

```json
{
  "name": "shop.checkout.duration",
  "description": "Time spent completing checkout",
  "baseUnit": "seconds",
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 3.0
    },
    {
      "statistic": "TOTAL_TIME",
      "value": 0.84
    },
    {
      "statistic": "MAX",
      "value": 0.42
    }
  ],
  "availableTags": []
}
```

Trong ví dụ, ba thao tác có tổng thời lượng 0,84 giây và max hiện tại 0,42 giây. Giá trị `MAX` của Micrometer có thể là time-window maximum; nó có thể giảm hoặc trở về 0 khi các mẫu cũ hết hạn và không có mẫu mới. Không diễn giải nó như max trọn đời.

### 5.4. DistributionSummary

DistributionSummary thường cung cấp `COUNT`, `TOTAL` và `MAX` cho các giá trị đã ghi nhận:

```json
{
  "name": "app.payload.size",
  "baseUnit": "bytes",
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 4.0
    },
    {
      "statistic": "TOTAL",
      "value": 16384.0
    },
    {
      "statistic": "MAX",
      "value": 8192.0
    }
  ],
  "availableTags": []
}
```

Đây là số đo ví dụ. Tập statistic thực tế tùy cấu hình và implementation. Nếu cần phân tích phân phối hoặc percentile, hãy cấu hình histogram phù hợp và dùng backend lưu trữ metrics; endpoint Actuator không thay thế truy vấn lịch sử.

## 6. Khám phá tag qua availableTags

Trường `availableTags` cho biết các tag key và value hiện có cho meter name đang được tra cứu. Ví dụ:

```json
{
  "name": "http.server.requests",
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 128.0
    }
  ],
  "availableTags": [
    {
      "tag": "method",
      "values": ["GET", "POST"]
    },
    {
      "tag": "status",
      "values": ["200", "400", "500"]
    },
    {
      "tag": "uri",
      "values": ["/orders", "/orders/{id}"]
    }
  ]
}
```

Danh sách này giúp khám phá cách meter được phân loại. Ví dụ, `http.server.requests` có thể có các chiều method, status và uri. Bạn có thể chọn một hoặc nhiều tag để drill-down.

`availableTags` không phải danh sách schema được khai báo vĩnh viễn cho mọi môi trường. Nó phản ánh các tag value mà registry hiện có cho meter đó. Nếu một route hoặc trạng thái chưa từng xuất hiện, value đó có thể chưa được liệt kê.

Nếu thấy tag có giá trị động như URL chứa order ID, user ID hoặc request ID, đó là dấu hiệu cần xem lại instrumentation vì cardinality có thể tăng mạnh.

## 7. Lọc meter theo tag

Thêm query parameter `tag` theo dạng `KEY:VALUE` để chỉ đọc meter phù hợp với tag đó:

```bash
curl.exe "http://localhost:8080/actuator/metrics/http.server.requests?tag=method:GET"
```

Có thể truyền nhiều tag để lọc một tổ hợp:

```bash
curl.exe "http://localhost:8080/actuator/metrics/http.server.requests?tag=method:GET&tag=status:200"
```

Ví dụ đọc timer checkout theo kênh web:

```bash
curl.exe "http://localhost:8080/actuator/metrics/shop.checkout.duration?tag=channel:web"
```

Nếu meter có các tag `channel` và `result`, có thể lọc cả hai:

```bash
curl.exe "http://localhost:8080/actuator/metrics/shop.checkout.duration?tag=channel:web&tag=result:success"
```

Khi value có dấu cách, ký tự đặc biệt hoặc dấu phân cách, hãy URL-encode query parameter theo quy tắc HTTP. Dùng đúng tag key/value đã được đăng ký; endpoint không tự chuẩn hóa giá trị đầu vào theo logic nghiệp vụ của ứng dụng.

### 7.1. Lọc tag để điều tra một nhóm dữ liệu

Giả sử metric `http.server.requests` có tag method, status và uri. Có thể tiến hành:

1. Gọi endpoint không có tag để xem các tag value hiện có.
2. Chọn một method như `POST`.
3. Thêm status như `500` để tập trung vào request lỗi.
4. Thêm uri template để tìm route có vấn đề.
5. So sánh các measurement của nhóm đã lọc với kết quả không lọc.

Ví dụ:

```bash
curl.exe "http://localhost:8080/actuator/metrics/http.server.requests?tag=method:POST&tag=status:500&tag=uri:/orders"
```

Nếu tag value chứa ký tự `/`, dấu cách hoặc `&`, nên encode URL đầy đủ bằng client HTTP phù hợp để tránh parser hiểu sai query string.

## 8. Đăng ký metric tùy chỉnh để kiểm tra qua endpoint

Ví dụ component đăng ký counter và timer bằng constructor injection:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public class CheckoutMetrics {
    private final Counter checkoutsCompleted;
    private final Timer checkoutDuration;

    public CheckoutMetrics(MeterRegistry registry) {
        this.checkoutsCompleted = Counter.builder("shop.checkout.completed")
                .description("Number of completed checkouts")
                .tag("channel", "web")
                .register(registry);

        this.checkoutDuration = Timer.builder("shop.checkout.duration")
                .description("Time spent completing checkout")
                .tag("channel", "web")
                .register(registry);
    }

    public void recordCompleted(long durationMillis) {
        checkoutsCompleted.increment();
        checkoutDuration.record(durationMillis, TimeUnit.MILLISECONDS);
    }
}
```

Sau khi gọi `recordCompleted(280)` ba lần, có thể đọc hai metric:

```bash
curl.exe "http://localhost:8080/actuator/metrics/shop.checkout.completed?tag=channel:web"
curl.exe "http://localhost:8080/actuator/metrics/shop.checkout.duration?tag=channel:web"
```

Counter cung cấp số lần hoàn tất; Timer cung cấp count, tổng thời lượng và max theo cấu hình. Hai meter dùng cùng tag `channel=web`, giúp kết quả có thể được đối chiếu theo cùng nhóm nghiệp vụ.

Trong ví dụ này, tag value cố định. Nếu channel đến từ request, hãy chuẩn hóa về một tập giá trị hữu hạn trước khi đăng ký meter để tránh cardinality không kiểm soát.

## 9. Phân biệt /actuator/metrics với /actuator/prometheus

Hai endpoint thường bị nhầm vì đều đọc dữ liệu Micrometer, nhưng phục vụ mục đích khác nhau:

| Tiêu chí | `/actuator/metrics` | `/actuator/prometheus` |
| --- | --- | --- |
| Mục đích | Khám phá và đọc một meter để chẩn đoán | Cung cấp toàn bộ exposition cho Prometheus scrape |
| Cách gọi | Gọi tên meter trong path, lọc bằng query tag | Prometheus scrape endpoint theo chu kỳ |
| Định dạng | JSON | Prometheus exposition text |
| Phạm vi | Một meter mỗi lần drill-down | Các metric được Prometheus registry xuất ra |
| Lịch sử | Không cung cấp lịch sử | Endpoint cũng chỉ cung cấp snapshot; Prometheus lưu lịch sử sau scrape |
| Truy vấn | Lọc theo tag cụ thể | PromQL truy vấn dữ liệu đã lưu ở Prometheus |

Ví dụ, meter Micrometer có tên `shop.orders.created`. Actuator metrics endpoint thường dùng đúng tên đó. Prometheus endpoint có thể xuất tên đã chuẩn hóa như `shop_orders_created_total`.

Không cấu hình Prometheus scrape `/actuator/metrics` để thu thập exposition. Hãy dùng `/actuator/prometheus` khi ứng dụng có Prometheus registry và endpoint tương ứng đã được expose.

## 10. Đọc endpoint đúng cách và tránh diễn giải sai

Endpoint trả giá trị hiện tại của meter, nhưng mỗi loại statistic có semantics riêng:

- `COUNT` của Counter là tổng tích lũy, không phải tốc độ request/giây.
- `VALUE` của Gauge là trạng thái hiện tại, có thể thay đổi ngay sau khi response được tạo.
- `TOTAL_TIME` của Timer là tổng thời lượng đã ghi nhận, không phải thời gian của request gần nhất.
- `MAX` có thể là max trong cửa sổ thống kê, không phải max trọn đời.
- `availableTags` cho biết các giá trị hiện có để lọc, không đảm bảo tất cả giá trị có thể xuất hiện trong tương lai.

Nếu cần biết tốc độ tăng, xu hướng theo giờ hoặc p95 trong 5 phút, hãy gửi metrics đến backend lưu time series và dùng ngôn ngữ truy vấn tương ứng. Endpoint Actuator không nhận tham số time range để dựng lại lịch sử.

## 11. Bảo mật endpoint metrics

Endpoint metrics có thể tiết lộ tên route, loại request, trạng thái dependency, dung lượng bộ nhớ, số connection và thông tin vận hành khác. Việc expose endpoint qua HTTP không đồng nghĩa mọi người dùng đều nên truy cập được.

Trong production:

- Chỉ expose endpoint cần thiết.
- Giới hạn network access cho management port hoặc route actuator.
- Cấu hình Spring Security để yêu cầu xác thực/ủy quyền nếu endpoint không chỉ dành cho mạng nội bộ tin cậy.
- Không đưa token, email, user ID hoặc dữ liệu nhạy cảm vào tag.
- Cân nhắc tách management port khỏi cổng HTTP nghiệp vụ.
- Theo dõi log truy cập và các request bất thường đến actuator.

Ví dụ cấu hình exposure chỉ giới hạn những endpoint cần dùng:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - metrics
```

Cấu hình exposure quyết định endpoint nào có thể được phục vụ qua web. Security policy vẫn cần được thiết lập riêng theo yêu cầu triển khai.

## 12. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `/actuator/metrics` trả 404 | Actuator chưa có hoặc endpoint chưa expose | Kiểm tra dependency và `management.endpoints.web.exposure.include`. |
| `/actuator/metrics` trả 401/403 | Security policy chặn truy cập | Kiểm tra SecurityFilterChain, quyền và thông tin xác thực. |
| Danh sách `names` không có metric tùy chỉnh | Bean chưa tạo, meter chưa đăng ký hoặc bị filter từ chối | Kiểm tra lifecycle bean, registry được inject và meter filter. |
| Truy vấn tên metric trả 404 | Sai tên hoặc meter chưa tồn tại | Sao chép đúng tên từ danh sách `names`. |
| Measurement bằng 0 | Chưa có sự kiện hoặc gauge đang có trạng thái 0 | Gọi luồng nghiệp vụ và truy vấn lại. |
| Không có tag mong đợi | Meter không đăng ký tag đó hoặc chưa có value tương ứng | Kiểm tra `availableTags` và cách tạo meter. |
| Lọc tag không ra kết quả | Sai key/value hoặc tổ hợp tag chưa xuất hiện | Bỏ từng filter để xác định tag gây loại hết kết quả. |
| Không thấy metric ở Prometheus | Nhầm endpoint hoặc Prometheus registry chưa cấu hình | Kiểm tra `/actuator/prometheus` và scrape target. |

Khi điều tra, hãy bắt đầu từ danh sách tên meter, sau đó đọc meter không lọc tag, rồi mới thêm từng tag filter. Cách này giúp xác định rõ lỗi nằm ở tên meter, tag hay dữ liệu chưa được ghi nhận.

## 13. Kiểm thử endpoint bằng Spring Boot integration test

Có thể dùng `MockMvc` để kiểm tra endpoint đã expose và đọc được meter sau khi component được inject:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
        "management.endpoints.web.exposure.include=metrics"
})
@AutoConfigureMockMvc
class MetricsEndpointTest {
    @Autowired
    MockMvc mockMvc;

    @Autowired
    MeterRegistry registry;

    @Test
    void listsAndReadsRegisteredMetric() throws Exception {
        registry.counter("test.orders.created", "channel", "web")
                .increment(2.0);

        mockMvc.perform(get("/actuator/metrics"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.names").isArray());

        mockMvc.perform(get("/actuator/metrics/test.orders.created")
                        .param("tag", "channel:web"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("test.orders.created"))
                .andExpect(jsonPath("$.measurements[0].value").value(2.0));
    }
}
```

Đây là ví dụ cấu trúc cho Spring Boot test với Actuator MVC endpoint. Tùy phiên bản và security config, có thể cần cấu hình test security hoặc import các thành phần ứng dụng phù hợp. Nếu dùng WebFlux, hãy dùng WebTestClient thay cho MockMvc.

Test này xác minh endpoint web và meter trong registry tích hợp. Nó không kiểm tra backend đã lưu lịch sử hoặc Prometheus scrape thành công; các việc đó cần integration test riêng cho đường export.

## 14. Checklist sử dụng /actuator/metrics

- [ ] Thêm `spring-boot-starter-actuator`.
- [ ] Expose endpoint `metrics` qua cấu hình management web exposure.
- [ ] Xác định đúng port, base path và context path của management server.
- [ ] Gọi `/actuator/metrics` để khám phá tên meter.
- [ ] Dùng đúng tên Micrometer trong `/actuator/metrics/{metricName}`.
- [ ] Đọc `measurements` theo statistic và loại meter.
- [ ] Dùng `availableTags` để khám phá tag key/value.
- [ ] Lọc bằng một hoặc nhiều query parameter `tag=KEY:VALUE`.
- [ ] Không nhầm endpoint JSON này với `/actuator/prometheus`.
- [ ] Không xem endpoint như kho dữ liệu lịch sử hoặc công cụ tính rate/percentile.
- [ ] Bảo vệ management endpoint bằng network policy và security phù hợp.
- [ ] Có integration test xác minh endpoint trả metric tùy chỉnh.

`/actuator/metrics` là công cụ chẩn đoán nhanh để tìm meter và đọc snapshot của nó. Bắt đầu từ danh sách tên, mở một meter cụ thể, đọc các statistic và dùng `availableTags` để lọc sâu. Khi cần lịch sử, rate, histogram hoặc percentile theo thời gian, hãy dựa vào backend metrics chuyên dụng; khi cần Prometheus scrape, dùng endpoint exposition riêng.
