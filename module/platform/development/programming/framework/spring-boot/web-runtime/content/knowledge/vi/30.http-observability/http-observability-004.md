# HTTP server metrics, thời gian phản hồi và số yêu cầu đang xử lý

## 1. Đặt vấn đề: API vẫn trả 200 nhưng người dùng thấy chậm

Một API Spring Boot có thể phục vụ hàng nghìn HTTP requests mỗi phút. Khi ứng dụng bị chậm, chỉ nhìn log “200 OK” không đủ trả lời:

- Trong một giây có bao nhiêu requests đến, bao nhiêu requests thành công/thất bại?
- Request `GET /api/products/{id}` mất bao lâu: trung bình, p95, p99?
- Có bao nhiêu requests **đang xử lý tại thời điểm quan sát**, thay vì đã hoàn tất?
- Độ trễ tăng vì một vài requests rất lâu, hay vì toàn bộ requests chậm hơn?
- Máy chủ hết servlet worker threads, queue backlog, downstream database chậm hay proxy đang trả 502?
- Histogram và active-request count đo ở **mỗi instance** hay tất cả replicas?
- Vì sao dashboard có RPS và latency nhưng không biết một request đang bị treo?

Trong hệ sinh thái Spring Boot, ba mảnh ghép chính là:

1. **Spring Boot Actuator**: thu thập và công bố chẩn đoán/metrics khi có cấu hình phù hợp.
2. **Micrometer Metrics + Observation**: đặt tên, gắn tags, đo duration/count/active và tích hợp các registries.
3. **Prometheus/Grafana hoặc backend telemetry khác**: scrape, lưu series, tính rate/quantile và cảnh báo.

Bài này thuộc mục **Quan sát HTTP** và tập trung vào các metric **ở phía HTTP server nhận request**:
- `http.server.requests` — **Timer** cho requests đã kết thúc.
- `http.server.requests.active` — **LongTaskTimer** theo dõi những request observations đang hoạt động trong Spring Boot 3.5 khi long-task timer của observations được bật.
- Những series Prometheus thường gặp như `http_server_requests_seconds_count`, `http_server_requests_seconds_sum`, `http_server_requests_seconds_bucket` và `http_server_requests_active_seconds_count`.

**Phân biệt ngay từ đầu:** Timer của completed requests, LongTaskTimer của in-flight requests và số TCP connections/threads đang busy **không phải một con số**. Một kết nối HTTP/2 có thể có nhiều active request streams; một TCP connection HTTP/1.1 keep-alive có thể đang idle và không có request nào chạy.

> **Phiên bản thực hành:** Spring Boot **3.5.x**, Java **17+**, Spring MVC với embedded Tomcat, Micrometer do Boot quản lý và Prometheus registry. Các bản Boot 4.x có thể đổi cấu hình, đặc biệt cơ chế active long-task timers; nếu nâng phiên bản, kiểm tra metric thật ở runtime thay vì mặc định các series cũ luôn tồn tại. Code Spring MVC trong ví dụ dùng `Thread.sleep` **cố ý để mô phỏng latency** trên Servlet thread; **không dùng cách blocking này trong WebFlux event loop**.

## 2. Sơ đồ quan sát request end-to-end

~~~text
Client / Browser
       |
       | HTTP request
       v
CDN / Load Balancer / Reverse Proxy
       |
       | upstream request
       v
Spring Boot (Tomcat / Jetty / Reactor Netty)
       |
       +--> HTTP server observation starts
       |          |
       |          +--> LongTaskTimer active: +1
       |          |
       +--> Filters / Security / Dispatcher
       |          |
       +--> Controller / business / DB / HTTP client
       |          |
       +--> response processing completes
                  |
                  +--> Timer records elapsed time
                  +--> LongTaskTimer active: -1
                  |
                  v
             HTTP response

Micrometer MeterRegistry
       |
       +--> /actuator/metrics (chẩn đoán theo meter name)
       +--> /actuator/prometheus (Prometheus exposition)
                     |
                     v
             Prometheus scrape
                     |
                     v
           PromQL + Grafana + Alerts
~~~

Sơ đồ là **mô hình khái niệm**; vị trí cụ thể của observation filter và xử lý async khác theo Spring MVC, WebFlux, security filters, container và version. Trước khi kết luận metric có bao phủ một lỗi, phải xác minh request có đi qua observation instrumentation hay đã bị chặn tại proxy/gateway.

**Observations** trong Spring Framework có thể đồng thời phục vụ metrics và tracing. Metrics là số liệu tổng hợp; distributed trace là dấu vết chi tiết của một request. Chúng bổ sung cho nhau, không thể thay thế lẫn nhau khi điều tra latency.

## 3. Hiểu “thời gian phản hồi” được tính ở đâu

Khi nói “request mất 500 ms”, hãy hỏi rõ bắt đầu và kết thúc tại đâu.

### Server-side latency

Micrometer HTTP server observation đo thời gian từ khi server instrumentation bắt đầu xử lý request đến khi observation kết thúc, tùy stack/async lifecycle. Nó có thể bao gồm routing, filter, business logic, một phần serialization/response processing; **không nhất thiết** bằng tổng thời gian người dùng thấy trên mạng từ đầu đến cuối.

### Client end-to-end latency

Browser có thể thấy thêm:
- DNS lookup, TCP/TLS handshake.
- Queueing tại CDN/LB/proxy.
- Network RTT, packet loss, retransmission.
- Download body lớn hoặc connection congestion.
- Client scheduling/rendering.

Từ đó:

~~~text
Client-observed latency
  ≈ Network/TLS + Edge/proxy + Queue + Origin processing
    + Response transfer + Client-side effects
~~~

Công thức chỉ mang tính trực giác; các giai đoạn có thể chồng lấn và không đơn giản cộng độc lập. **Không dùng server timer làm đại diện duy nhất cho trải nghiệm người dùng**. Khi cần phân tích end-to-end, kết hợp RUM, edge metrics, `http.client.requests` của các service gọi downstream, tracing và origin HTTP server metrics.

### Streaming và kết nối dài

Một request SSE giữ response mở 20 phút có thể còn được LongTaskTimer xem là **active trong 20 phút**, trong khi Timer completed chỉ ghi sample khi observation hoàn tất. Điều đó **không** có nghĩa một request xử lý CPU liên tục 20 phút. Phải phân loại rõ các streaming/long-poll routes và không trộn chúng với SLO latency của các JSON APIs hoàn tất nhanh.

## 4. Hai metric HTTP server cốt lõi: Timer và LongTaskTimer

### 4.1. `http.server.requests` — Timer cho request đã hoàn tất

Trong Spring Boot 3.5, instrumentation mặc định của Spring MVC/WebFlux thường ghi một timer tên `http.server.requests` theo các observations của web stack. Micrometer Timer có các measurement thường gặp:

| Statistic | Ý nghĩa | Dùng khi nào |
|---|---|---|
| `COUNT` | Số measurements đã hoàn thành và được ghi vào timer | Tính tổng requests, throughput/RPS |
| `TOTAL_TIME` | Tổng thời gian của các requests được ghi | Tính latency trung bình |
| `MAX` | Giá trị lớn nhất trong **cửa sổ thời gian** của implementation | Chẩn đoán spike, không coi là max từ lúc process chạy |
| Histogram buckets (nếu bật) | Số requests hoàn tất có duration không vượt từng boundary | Tính p95/p99 aggregable và tỷ lệ dưới SLO |

Tại thời điểm một request bắt đầu và chưa xong, **COUNT của Timer không nhất thiết tăng ngay**. Timer theo dõi **completed** observations. Muốn nhìn số request còn đang mở, hãy xem `http.server.requests.active` hoặc một công cụ đo inflight phù hợp.

**Ví dụ:** 10 requests hoàn tất có tổng duration 2.5s ⇒ trung bình 0.25s = 250ms. Nhưng chưa biết có bao nhiêu requests 2s và bao nhiêu requests 5ms; trung bình che giấu tail latency.

### 4.2. `http.server.requests.active` — LongTaskTimer khi request vẫn chạy

Trong Boot 3.5, property `management.observations.long-task-timer.enabled` mặc định là **true** theo Common Application Properties. LongTaskTimer được tạo cho observations, bao gồm HTTP server observations phù hợp; tên thường là `http.server.requests.active`.

LongTaskTimer đưa ra:
- **ACTIVE_TASKS**: số samples/requests đang được theo dõi *ngay thời điểm đọc*.
- **DURATION** hoặc total duration của các active tasks: tổng tuổi hiện tại của các requests chưa hoàn tất.
- **MAX** của các active tasks: tuổi của task dài nhất đang chạy, tùy backend/registry.

Ví dụ hai requests đang chạy, một request đã xử lý 8s, một request 2s:

~~~text
ACTIVE_TASKS = 2
DURATION ≈ 10s
MAX ≈ 8s
~~~

Nếu cả hai hoàn tất, active count có thể về **0**, mặc dù Timer completed count vừa tăng **2**. `DURATION` của LongTaskTimer không phải tổng thời gian requests đã hoàn thành theo kiểu monotonic counter; nó thay đổi theo số tasks còn active.

**Cẩn trọng với label:** khi request vẫn in-flight, một số tags như final `status`, `outcome`, `uri` có thể chưa xác định hoặc hiển thị `UNKNOWN`. Đừng đòi active metric phải có `uri="/api/slow/{id}"` và `status="200"` như completed Timer. Trước tiên tổng hợp active count trên **những series thực tế được xuất ra**.

### 4.3. So sánh nhanh

| Câu hỏi | Timer `http.server.requests` | LongTaskTimer `http.server.requests.active` |
|---|---|---|
| Requests đã hoàn thành bao nhiêu? | Có, `COUNT` | Không |
| Latency của các requests đã xong? | Có | Không |
| Hiện đang còn bao nhiêu request observations? | Không trực tiếp | Có, active count |
| Yêu cầu đang treo lâu nhất? | Không trực tiếp | Có thể xem current active max duration |
| Có phải counter tích lũy? | `COUNT` thường tăng theo completed events (reset khi process restart) | **Không**, active count là snapshot |
| Có phải số TCP sockets? | Không | Không |
| Có phải số Tomcat worker threads busy? | Không | Không |
| Phù hợp tính RPS với `rate()`? | Có, với Prometheus `_count` | Không dùng `rate()` trên active gauge |

### 4.4. Lưu ý khi nâng phiên bản

Tên và sự hiện diện của active long-task timer **phụ thuộc phiên bản và observability config**. Một số nhánh Spring Boot 4.x thay đổi cách tạo active timers. Trong bài này dùng Boot 3.5.x đã kiểm tra property `management.observations.long-task-timer.enabled=true`. Sau nâng cấp, tra release notes, config và `/actuator/metrics` trước khi đặt alert; nếu metric biến mất, không diễn giải nó là “ứng dụng không có requests đang chạy”.

## 5. HTTP metric tags: method, uri, status, outcome, exception

Một Timer tên `http.server.requests` không chỉ có một số tổng; nó có thể phân nhóm theo **tags (dimensions)** như:

| Tag | Ví dụ | Ý nghĩa |
|---|---|---|
| `method` | `GET`, `POST` | HTTP method |
| `uri` | `/api/items/{id}` | Route pattern/template được xử lý, khi xác định được |
| `status` | `200`, `404`, `503` | Status HTTP khi request kết thúc |
| `outcome` | `SUCCESS`, `CLIENT_ERROR`, `SERVER_ERROR` | Nhóm status theo semantics |
| `exception` / `error` | `none` hoặc tên exception | Ghi dấu lỗi theo observation/registry version |
| `instance`, `job` | Do Prometheus scrape/infra gắn | Replica và logical scrape target |

Ví dụ:

~~~text
http.server.requests{
  method=GET,
  uri=/api/slow/{jobId},
  status=200,
  outcome=SUCCESS
}
~~~

Đây là **biểu diễn khái niệm của một meter cùng tags**, không phải dòng Prometheus exposition trực tiếp.

### Vì sao cần uri template?

Giả sử có 1 triệu `/api/items/123`, `/api/items/124` ... Nếu dùng URL raw làm `uri`, có thể tạo tới 1 triệu label values, gây **metric cardinality explosion**. Spring web observations thường cố gắng dùng route pattern như `/api/items/{id}` để gom requests cùng loại.

**Không tự đưa** user ID, UUID đơn hàng, query string, email, access token, session ID, full URL/path chứa dữ liệu cá nhân vào tags. Các series Prometheus có chi phí memory/CPU/storage; cardinality ≈ tích của số giá trị mỗi tag. Với 10 methods × 20 statuses × 200 routes × 5 instances đã có tới 200.000 combinations lý thuyết trước khi tính tags khác, nên cần đo series count thực tế.

### Request đã xử lý lỗi nhưng `exception=none`?

Có thể xảy ra khi exception đã được controller advice/handler giải quyết thành response. Spring Boot/Spring Framework tài liệu hóa rằng **handled exceptions không luôn được ghi là exception tags** mặc định. Sử dụng `status`/`outcome` để tính lỗi HTTP, và trace/log riêng để phân tích exception root cause. Không đánh đồng `exception=none` với “request không xảy ra bất kỳ lỗi nghiệp vụ nào”.

Các lỗi chặn ở load balancer, WAF hoặc API gateway trước khi đến JVM **không nằm trong HTTP server metrics của origin**. Cần edge metrics/logs bổ sung nếu muốn tỷ lệ lỗi người dùng cuối.

## 6. Khởi tạo dự án Spring Boot 3.5 với Actuator và Prometheus

### 6.1. Dependencies

Tạo dự án bằng Spring Initializr:
- Java **17+**, Gradle, Spring Boot **3.5.x**.
- **Spring Web**, **Spring Boot Actuator**.
- Tự thêm Prometheus registry nếu template chưa có.

Trong một project Initializr đã có Spring Boot Gradle plugin và dependency management, phần `dependencies`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Đây là **Gradle dependency fragment**, không phải toàn bộ `build.gradle`. Spring Boot dependency management tự chọn phiên bản tương thích của Micrometer. Với Spring Boot 4.x, starter MVC tương ứng thường là `spring-boot-starter-webmvc`; không vô tình trộn MVC và WebFlux khi chỉ muốn demo một stack.

**Không cần tự tạo `Counter` cho từng HTTP request đã được Spring Framework instrument**. Nếu tự tăng counter và coi nó là “http.server.requests” trong cùng dashboard, rất dễ double count hoặc mất cùng semantics/tagging.

### 6.2. Cấu hình application.yml

Tạo `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  tomcat:
    mbeanregistry:
      enabled: true

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"
  observations:
    long-task-timer:
      enabled: true
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests:
          - 100ms
          - 300ms
          - 1s
          - 3s
~~~

Giải thích:
- `server.port=8080`: cổng HTTP demo.
- `server.tomcat.mbeanregistry.enabled=true`: bật Tomcat MBean registry để Boot có thể công bố **Tomcat metrics** dưới tên `tomcat.*`. Đây là phép đo bổ sung, **không bắt buộc** cho HTTP request Timer.
- `management.endpoints.web.exposure.include`: expose `/actuator/metrics` và `/actuator/prometheus` để thử bằng curl. **Không mở công khai endpoints này trong production**; chi tiết bảo mật ở mục 18.
- `management.observations.long-task-timer.enabled=true`: explicit hóa default của Boot 3.5, để LongTaskTimer active của observations có thể xuất hiện.
- `management.metrics.distribution.percentiles-histogram.http.server.requests=true`: bật percentile histogram cho tên meter bắt đầu bằng prefix này; cho phép Prometheus `_bucket` để tính p95/p99 **aggregable**. **Tăng số time series/memory**; đừng bật rộng cho mọi meter trong production.
- `management.metrics.distribution.slo.http.server.requests`: thêm các service-level boundaries 100ms, 300ms, 1s, 3s khi histogram/timer registry hỗ trợ. Đây là ngưỡng minh họa, không phải SLO bắt buộc cho mọi API.

**Điểm tinh tế:** property distribution áp dụng theo **meter ID prefix**, vì vậy `http.server.requests.active` cũng bắt đầu bằng `http.server.requests`. Tùy version Micrometer/Boot, một số cấu hình histogram/distribution có thể tác động cả LongTaskTimer active và phát series bổ sung. Kiểm tra `/actuator/prometheus`, cardinality thực tế và cân nhắc tùy chỉnh bằng `MeterFilter` nếu cần tách hẳn hai tên. Không giả định property trên chỉ tạo buckets cho completed Timer trong mọi version.

Nếu chỉ muốn test HTTP request count/latency cơ bản, **có thể bỏ toàn bộ khối `distribution`**; `_count` và `_sum` của completed Timer vẫn có thể được xuất, còn `_bucket` cần histogram/SLO tương ứng.

## 7. Mã Java runnable: fast, slow, error và URI template

Tạo file `src/main/java/demo/httpmetrics/HttpMetricsApplication.java`:

~~~java
package demo.httpmetrics;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@RestController
public class HttpMetricsApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpMetricsApplication.class, args);
    }

    public record SlowResult(String jobId, long sleptMs) { }

    @GetMapping("/api/fast")
    public Map<String, String> fast() {
        return Map.of("message", "ok");
    }

    @GetMapping("/api/slow/{jobId}")
    public SlowResult slow(
            @PathVariable String jobId,
            @RequestParam(defaultValue = "3000") long ms)
            throws InterruptedException {

        if (ms < 0 || ms > 10_000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "ms must be between 0 and 10000"
            );
        }

        // CHỈ để tạo request chậm trong Spring MVC/Tomcat demo.
        // KHÔNG dùng Thread.sleep trong WebFlux event loop.
        Thread.sleep(ms);

        return new SlowResult(jobId, ms);
    }

    @GetMapping("/api/error")
    public void simulatedError() {
        throw new ResponseStatusException(
            HttpStatus.SERVICE_UNAVAILABLE,
            "simulated unavailable"
        );
    }
}
~~~

Đây là **một Java source file đầy đủ** trong project Spring Boot đúng dependencies. Sau khi chạy, bạn có:
- `GET /api/fast`: response JSON `{"message":"ok"}`.
- `GET /api/slow/A?ms=3000`: giữ servlet request ~3s rồi trả JSON có `jobId="A"` và `sleptMs=3000`.
- `GET /api/error`: trả **503 Service Unavailable** từ Spring MVC error handling.

**Điểm chủ đích của demo:** `Thread.sleep` làm chậm một servlet worker thread. Nó phù hợp để tạo request “đang chạy” có thể quan sát trong lớp học. Trong production, không giữ Tomcat worker thread chỉ để sleep; hãy đo downstream thật bằng tracing. Trong **WebFlux**, dùng `Mono.delay(Duration.ofSeconds(...))` hoặc non-blocking service APIs, không gọi `Thread.sleep` trên Reactor event loop.

### 7.1. Khởi động

Ở root project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Mặc định server nghe cổng 8080 như YAML. Nếu cổng đang được dùng, dừng ứng dụng khác trước. Không nên đo latency benchmark chính thức khi chạy debug build, debugger breakpoints hoặc laptop đang bị tải nặng.

### 7.2. Test fast, slow, error

~~~bash
curl -sS -i http://localhost:8080/api/fast
curl -sS -i "http://localhost:8080/api/slow/A?ms=3000"
curl -sS -i http://localhost:8080/api/error
~~~

Kỳ vọng:
- Fast: status **200**, body `{"message":"ok"}`.
- Slow: status **200**, body có fields `jobId="A"` và `sleptMs=3000`.
- Error: status **503**, Spring Boot error body có thể thay đổi theo config; không assert raw JSON lỗi cụ thể.

`Map.of` và Jackson có thể quyết định thứ tự fields; kiểm tra JSON theo key. `ms=3000` đại diện delay cố ý 3s **bên trong controller**, nên client-observed latency có thể lớn hơn 3s đôi chút do routing/serialization/network.

### 7.3. Lặp request tạo dữ liệu thống kê

~~~bash
for i in 1 2 3 4 5; do
  curl -sS -o /dev/null http://localhost:8080/api/fast
done
~~~

Đây là cú pháp Bash/Linux/macOS/Git Bash, **không phải** PowerShell thuần. Trên Windows PowerShell:

~~~powershell
1..5 | ForEach-Object {
  curl.exe -sS -o NUL http://localhost:8080/api/fast
}
~~~

Sau một vài requests, Timer có measurements cho route `/api/fast`; nếu chưa có data ở Actuator, xác nhận endpoint exposure, dependency, web stack và URL thực tế.

## 8. Xem metrics bằng /actuator/metrics

### 8.1. Danh sách tên meter

~~~bash
curl -sS http://localhost:8080/actuator/metrics
~~~

Endpoint trả JSON với trường `names`, ví dụ một phần:

~~~json
{
  "names": [
    "http.server.requests",
    "http.server.requests.active",
    "jvm.memory.used"
  ]
}
~~~

Đây là **trích đoạn minh họa**, không phải danh sách hoàn chỉnh và không cam kết thứ tự. Runtime thực tế còn nhiều meters như JVM, process, system, HTTP connections và Tomcat nếu registry bật.

### 8.2. Xem completed Timer

~~~bash
curl -sS http://localhost:8080/actuator/metrics/http.server.requests
~~~

Một response cấu trúc thường giống:

~~~json
{
  "name": "http.server.requests",
  "measurements": [
    {"statistic": "COUNT", "value": 7.0},
    {"statistic": "TOTAL_TIME", "value": 3.2},
    {"statistic": "MAX", "value": 3.01}
  ],
  "availableTags": []
}
~~~

**Không coi các số 7, 3.2, 3.01 hoặc `availableTags=[]` là output chắc chắn**: chúng hoàn toàn phụ thuộc những requests đã chạy, registry và các tags có mặt. Response có thể liệt kê `description`, `baseUnit`, các tags `method`/`uri`/`status`, và thứ tự khác. Quan trọng là semantics `COUNT`, `TOTAL_TIME`, `MAX`.

Muốn lọc đúng một route/status:

~~~bash
curl -sS \
  "http://localhost:8080/actuator/metrics/http.server.requests?tag=uri:/api/fast&tag=method:GET"
~~~

Route templated:

~~~bash
curl -sS \
  "http://localhost:8080/actuator/metrics/http.server.requests?tag=uri:/api/slow/{jobId}&tag=method:GET"
~~~

Cú pháp URL trong trình duyệt/curl có thể cần percent-encode dấu `{`, `}`; một cách dễ dàng với curl là dùng `--globoff` hoặc `--get --data-urlencode`:

~~~bash
curl -sS --get \
  --data-urlencode 'tag=uri:/api/slow/{jobId}' \
  --data-urlencode 'tag=method:GET' \
  http://localhost:8080/actuator/metrics/http.server.requests
~~~

**Lưu ý:** lệnh có `{jobId}` trong URL thô có thể bị curl coi là URL glob expression; phiên bản `--get --data-urlencode` là cách bền hơn khi dạy. Actuator drill-down dùng **tên meter gốc có dấu chấm**, không dùng tên Prometheus với dấu gạch dưới.

### 8.3. Xem active LongTaskTimer

~~~bash
curl -sS \
  http://localhost:8080/actuator/metrics/http.server.requests.active
~~~

Response measurements có thể gồm `ACTIVE_TASKS` và `DURATION`; khi không có request đang chạy ngoài snapshot, `ACTIVE_TASKS` có thể là 0 hoặc meter chưa được nhìn thấy tùy lifecycle/version. **Đừng giải thích một lần active=0 là không có traffic**: chỉ là không có request observations nằm trong scope tại thời điểm lấy mẫu.

Quan trọng: nếu request slow còn đang mở thì active có thể tăng. Ta sẽ tạo tình huống có thể nhìn thấy ở mục 9.

## 9. Thực hành “request đang xử lý”: hai terminal

### 9.1. Terminal A — bắt đầu một request chậm

Mở một terminal và chạy:

~~~bash
curl -sS -i \
  "http://localhost:8080/api/slow/long-job?ms=10000"
~~~

Controller ngủ tối đa 10 giây. Trong thời gian chưa hoàn thành, **để lệnh chạy**, không nhấn Ctrl+C.

### 9.2. Terminal B — đọc active ngay khi terminal A còn đợi

Trong vòng vài giây sau khi A bắt đầu:

~~~bash
curl -sS \
  http://localhost:8080/actuator/metrics/http.server.requests.active
~~~

Tìm measurement `ACTIVE_TASKS`. Nếu chỉ có một request chậm, active count **có thể khoảng 1**, nhưng có thể thấy các request đồng thời khác (gồm metrics scraping) tùy instrumentation/filter. Chỉ cần chứng minh active count **tăng trong cửa sổ chậm**, không buộc chính xác 1 ở mọi lần đọc.

Nếu quan sát nhiều mẫu cách nhau 2 giây trong khi request còn chạy, active duration của request đó sẽ tăng. Sau khi terminal A kết thúc, active count quay về mức nền, còn `http.server.requests` completed Timer ghi thêm một request.

### 9.3. Vừa đọc live gauge vừa thấy thay đổi completed count

Thử:

~~~bash
curl -sS \
  "http://localhost:8080/actuator/metrics/http.server.requests?tag=uri:/api/slow/{jobId}"
~~~

Dùng phiên bản `--get --data-urlencode` ở mục 8 để tránh URL globbing. Trong lúc A còn đang xử lý, count của completed slow route **có thể chưa tăng**; sau khi A hoàn thành, nó tăng. Đây là điểm khác biệt rõ giữa Timer và LongTaskTimer.

### 9.4. Thử hai yêu cầu slow cùng lúc

Chạy hai terminal hoặc tiến trình độc lập:

~~~bash
curl -sS -o /dev/null \
  "http://localhost:8080/api/slow/A?ms=10000"
~~~

~~~bash
curl -sS -o /dev/null \
  "http://localhost:8080/api/slow/B?ms=10000"
~~~

Trong lúc cả hai đang chờ, scrape active metric ở một terminal thứ ba. Với Tomcat còn đủ worker threads, có thể quan sát active count tăng khoảng **2** so với nền. Nếu hai requests chạy lệch nhau nhiều hoặc sampler trễ, số thấy có thể khác; đó là bản chất của **instantaneous sampling**, không phải sai metric.

### 9.5. Vì sao khó “bắt” request nhanh trong active gauge?

Nếu một request mất 5ms và Prometheus scrape mỗi 15s, xác suất lấy đúng thời điểm request đang diễn ra có thể rất thấp. Các request nhanh vẫn được Timer **đếm sau khi hoàn thành**, nhưng một snapshot active có thể là 0 hầu hết thời gian.

Để hiểu traffic thường xuyên, xem **RPS và latency Timer**. Để xem **concurrency/backlog**, xem active gauge cùng container queues/connections và load test ổn định. Không dùng một snapshot làm bằng chứng không có công việc.

## 10. Prometheus metric naming: đừng nhầm với Actuator meter name

Actuator/Micrometer tên logic:

~~~text
http.server.requests
http.server.requests.active
~~~

Trong Prometheus exposition, tên thường được normalized và thêm unit/statistic suffix:

~~~text
http_server_requests_seconds_count
http_server_requests_seconds_sum
http_server_requests_seconds_max
http_server_requests_seconds_bucket

http_server_requests_active_seconds_count
http_server_requests_active_seconds_sum
http_server_requests_active_seconds_max
~~~

Sự hiện diện của `_bucket` phụ thuộc histogram/SLO config và registry/version. Các tên `active` phía dưới là **LongTaskTimer**, `_count` của nó biểu thị **active tasks tại scrape**, khác với cumulative count của Timer completed phía trên.

Ví dụ **dòng minh họa**, không phải số đo đã chạy từ project:

~~~prometheus
http_server_requests_seconds_count{method="GET",status="200",uri="/api/fast"} 5
http_server_requests_seconds_sum{method="GET",status="200",uri="/api/fast"} 0.045
http_server_requests_active_seconds_count{method="GET",uri="UNKNOWN"} 1
http_server_requests_active_seconds_sum{method="GET",uri="UNKNOWN"} 4.3
~~~

Labels thật có thể còn `exception`, `error`, `outcome`, `job` hoặc `instance`; active `uri` có thể là `UNKNOWN`. `_sum` của active timer **không phải cumulative duration** như `http_server_requests_seconds_sum`.

### Kiểm tra exposition thật

~~~bash
curl -sS http://localhost:8080/actuator/prometheus
~~~

Trong Bash/Linux có thể lọc:

~~~bash
curl -sS http://localhost:8080/actuator/prometheus \
  | grep '^http_server_requests'
~~~

Windows PowerShell:

~~~powershell
(Invoke-WebRequest -UseBasicParsing \
  http://localhost:8080/actuator/prometheus).Content
~~~

PowerShell 5.1 không dùng dấu `\` để nối lệnh như Bash; phiên bản dùng một dòng:

~~~powershell
(Invoke-WebRequest -UseBasicParsing http://localhost:8080/actuator/prometheus).Content
~~~

Khi dùng Docker/Kubernetes, Prometheus phải truy cập **địa chỉ service/Pod thật**, không phải mặc định `localhost` từ process Prometheus. Lệnh ở đây kiểm tra demo chạy trên máy local.

## 11. Cấu hình một Prometheus scrape job tối thiểu

Ví dụ fragment trong `prometheus.yml`:

~~~yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "spring-web-runtime"
    metrics_path: "/actuator/prometheus"
    static_configs:
      - targets: ["localhost:8080"]
~~~

Đây là **config cho Prometheus chạy trên cùng máy với Spring Boot**. Nếu Prometheus chạy trong container riêng, `localhost:8080` trỏ về container Prometheus, nên thay bằng địa chỉ container/network service tương ứng. Production thường dùng Kubernetes service discovery, Operator/ServiceMonitor/PodMonitor, TLS/mTLS/auth và network policies thay vì static target.

### Khi nào series xuất hiện?

- HTTP metrics có thể chỉ được đăng ký sau khi observation đã có sample/active, nên nên gọi `/api/fast` hoặc `/api/slow` trước khi kết luận “không có metric”.
- Prometheus sẽ có thời gian scrape interval; đợi một lần scrape thực tế hoặc vào target-status UI kiểm tra.
- Khi ứng dụng restart, cumulative counters có thể reset. PromQL `rate()`/`increase()` xử lý counter resets hợp lệ; không dùng chênh lệch `count(now)-count(before)` bằng tay trên nhiều process không xét restart.

**Không dùng `/actuator/metrics` làm backend metrics scraper production.** Đây là diagnostic endpoint hiển thị meter names và measurements; Prometheus nên scrape `/actuator/prometheus` theo định dạng phù hợp.

## 12. PromQL: throughput / Requests per second

Prometheus series completed request count thường là:

~~~text
http_server_requests_seconds_count
~~~

### RPS toàn service

~~~promql
sum(rate(http_server_requests_seconds_count{job="spring-web-runtime"}[5m]))
~~~

Giải thích:
- `rate(counter[5m])` ước lượng tốc độ tăng mỗi giây trong cửa sổ 5 phút; có tính đến counter reset.
- `sum(...)` cộng các series theo tags/routes/instances.
- Kết quả là **requests per second trung bình trên 5 phút**, không phải số requests đúng vào một giây cố định.

Nếu có nhiều replica, `sum(rate(...))` tổng hợp throughput toàn service khi labels match đúng các targets.

### RPS theo HTTP method/route

~~~promql
sum by (method, uri) (
  rate(http_server_requests_seconds_count{
    job="spring-web-runtime",
    uri=~"/api/.*"
  }[5m])
)
~~~

Dùng route **template** để số series hữu hạn; không dùng raw `jobId` hay giá trị `ms` trong tags.

### Tổng requests trong 5 phút

~~~promql
sum(increase(http_server_requests_seconds_count{
  job="spring-web-runtime"
}[5m]))
~~~

`increase` là số lượng tăng ước lượng trong cửa sổ, có thể ra giá trị không nguyên do nội suy/sampling; điều này không có nghĩa server nhận “nửa một request”.

**Không áp `rate()` lên `http_server_requests_active_seconds_count`**: series active là một snapshot gauge, không phải counter tăng theo tổng số requests.

## 13. PromQL: thời gian phản hồi trung bình

Nếu `_sum` là tổng duration của completed requests và `_count` là số completed requests, thì:

~~~text
Average latency = ΔTotalDuration / ΔCompletedRequests
~~~

PromQL:

~~~promql
sum(rate(http_server_requests_seconds_sum{
  job="spring-web-runtime"
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    job="spring-web-runtime"
  }[5m])),
  1e-9
)
~~~

Đơn vị kết quả là **seconds/request**; nhân 1000 nếu muốn milliseconds.

### Vì sao không lấy trung bình các instance averages?

Giả sử:
- Instance A phục vụ 100 requests, mean 100ms.
- Instance B phục vụ 1 request, mean 2s.

Trung bình không trọng số của hai means = 1.05s, nhưng mean của tất cả 101 requests sẽ thấp hơn nhiều. Cách đúng là **cộng total duration, cộng count, rồi chia**, không lấy average của per-instance averages.

### Theo route

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_sum{
    job="spring-web-runtime",uri=~"/api/.*"
  }[5m])
)
/
clamp_min(
  sum by (uri) (
    rate(http_server_requests_seconds_count{
      job="spring-web-runtime",uri=~"/api/.*"
    }[5m])
  ),
  1e-9
)
~~~

Đây là **average latency** theo route, không phải p95/p99. Nếu nhu cầu sản phẩm là tail latency, dùng histogram ở mục tiếp theo.

## 14. PromQL: p95/p99 và histogram buckets

### Tại sao average latency không đủ?

Trong 100 requests:
- 95 requests hoàn thành trong 20ms.
- 5 requests hoàn thành trong 3s.

Trung bình bị ảnh hưởng bởi 5 requests chậm, nhưng không kể được **bao nhiêu người dùng rơi vào đuôi** và phân phối thực. Với service latency SLO, p95/p99 thường hữu ích hơn mean.

### Histogram bucket metric

Khi bật histogram ở mục 6:

~~~text
http_server_requests_seconds_bucket{le="0.1", ...}
http_server_requests_seconds_bucket{le="0.3", ...}
http_server_requests_seconds_bucket{le="1.0", ...}
http_server_requests_seconds_bucket{le="+Inf", ...}
~~~

`le` là cumulative bucket boundary tính bằng **giây**; giá trị bucket là số samples có duration **≤ boundary**. Các bucket ví dụ có thể khác trong thực tế theo Micrometer/registry và config.

p95 toàn dịch vụ:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      job="spring-web-runtime"
    }[5m])
  )
)
~~~

p99 theo route:

~~~promql
histogram_quantile(
  0.99,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket{
      job="spring-web-runtime",
      uri=~"/api/.*"
    }[5m])
  )
)
~~~

**Quan trọng:**
- `histogram_quantile` trên classic Prometheus histogram cho kết quả **ước lượng** thông qua bucket interpolation, không phải p95 chính xác từ raw samples.
- Phải giữ nhãn `le` trong phép aggregation của classic histogram.
- Histogram phải được bật và quan sát được `_bucket`; nếu không, query thường không trả dữ liệu.
- Tránh tính p95 cho một route có 1–2 requests trong 5 phút rồi diễn giải như số liệu đáng tin cậy. Cần xét sample volume.
- `management.metrics.distribution.percentiles.http.server.requests=0.95,0.99` là **client-side percentiles** nếu bật riêng; chúng thường **không aggregable chính xác qua instances**. Với Prometheus và nhiều replicas, ưu tiên histogram nếu cardinality budget cho phép.

### Tỷ lệ requests dưới SLO 300ms

Với bucket boundary `0.3` thực sự có tồn tại:

~~~promql
sum(rate(http_server_requests_seconds_bucket{
  job="spring-web-runtime",le="0.3"
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    job="spring-web-runtime"
  }[5m])),
  1e-9
)
~~~

Giá trị từ 0 đến 1 là ước lượng **proportion** requests trong 5 phút hoàn thành ≤300ms, với cùng filter/label scopes. Nếu SLO 99% requests trong 300ms, yêu cầu kết quả ≥0.99 khi lượng traffic đủ lớn.

**Không dùng** `http_server_requests_active_seconds_sum` làm tử số của mean latency hoặc histogram SLO completed requests: đó là tổng tuổi **requests đang chạy**, có tính chất khác hẳn.

## 15. PromQL: tỷ lệ 5xx và phân biệt outcome

Tỷ lệ 5xx trong 5 phút:

~~~promql
sum(rate(http_server_requests_seconds_count{
  job="spring-web-runtime",status=~"5.."
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    job="spring-web-runtime"
  }[5m])),
  1e-9
)
~~~

Kết quả 0.03 tương ứng khoảng **3%** trong cửa sổ nếu traffic đủ để ước lượng. Khi service có 0 traffic, mẫu số clamp tránh NaN nhưng **không thay thế kiểm tra thiếu dữ liệu**. Cần alert riêng cho scrape failures `up == 0` và traffic anomaly nếu phù hợp.

### 4xx không đồng nghĩa sự cố máy chủ

- 400 validation có thể phản ánh clients gửi dữ liệu sai.
- 401/403 từ Security có thể do authentication failure/bot/permission policy.
- 404 có thể do URL không tồn tại.
- 429 là rate limiting, có thể là dấu hiệu overload hoặc throttling chủ động.
- 5xx thường quan trọng để điều tra server/dependency failures.

Các nhóm này nên có biểu đồ riêng và alert theo tác động người dùng, không gom tất cả non-200 thành một “error rate” mơ hồ. Đối với lỗi do gateway/CDN trước origin, **origin `http.server.requests` có thể không thấy**; cần bổ sung metrics ở edge.

### Một số response lỗi không có exception tag

Nếu controller dùng `ResponseStatusException` được handler giải quyết, status cuối có thể là 503 nhưng `exception`/`error` tag có thể là `none` tùy observation handling. Query tính 5xx nên dựa vào `status`/`outcome` đúng theo policy, không chỉ tìm `exception!="none"`.

## 16. PromQL: số request đang xử lý lúc này

### 16.1. Active count dùng LongTaskTimer

Trong Boot 3.5 với LongTaskTimer enabled, Prometheus thường có:

~~~text
http_server_requests_active_seconds_count
~~~

Query toàn service:

~~~promql
sum(http_server_requests_active_seconds_count{
  job="spring-web-runtime"
})
~~~

Query theo instance:

~~~promql
sum by (instance) (
  http_server_requests_active_seconds_count{
    job="spring-web-runtime"
  }
)
~~~

Kết quả này là **snapshot active observations tại mỗi thời điểm Prometheus scrape**, không phải số requests toàn bộ lịch sử và không phải tốc độ request mới.

### 16.2. Tổng tuổi của những requests còn active

~~~promql
sum(http_server_requests_active_seconds_sum{
  job="spring-web-runtime"
})
~~~

Đây là số **giây đang tích lũy của các tasks hiện còn chạy** tại scrape; ví dụ 3 tasks đang chạy với ages 2s, 5s, 8s ⇒ sum≈15s. Nó có thể đột ngột giảm khi task dài kết thúc. **Không dùng `rate()` trên active sum để tính request latency**.

Có thể quan sát series `http_server_requests_active_seconds_max` khi registry xuất ra, nhưng giá trị max này là active age trong snapshot/time window liên quan, không phải max latency của completed requests.

### 16.3. Active ≠ Tomcat busy threads ≠ TCP active connections

| Số đo | Đơn vị | Ví dụ sự khác biệt |
|---|---|---|
| HTTP active requests | Số observations chưa kết thúc | SSE stream 1 giờ có thể tính là active |
| Tomcat busy threads | Số worker threads đang bận | Servlet async có thể giữ request active nhưng không giữ thread liên tục |
| TCP current connections | Số sockets/connections | Một HTTP keep-alive connection có thể idle giữa requests |
| HTTP/2 concurrent streams | Số HTTP/2 request streams hoạt động | Một TCP connection có nhiều streams |
| Queue length | Số tasks/connections chờ được xử lý | Chưa vào HTTP observation nên có thể không được tính active |
| Downstream active calls | Số HTTP client/database calls còn chạy | Một inbound request có thể gọi nhiều outbound calls |

Do đó không có công thức `active HTTP requests = active TCP connections` hay `active requests = Tomcat threads busy` đúng trong mọi runtime.

### 16.4. Nhãn của active metric có thể khác completed metric

Một in-flight request chưa có final status và có thể chưa xác định URI mapping đầy đủ, nên `uri=UNKNOWN` hoặc `status=UNKNOWN` có thể xuất hiện. Nếu query:

~~~promql
http_server_requests_active_seconds_count{uri="/api/slow/{jobId}"}
~~~

trả rỗng, **không kết luận toàn bộ active count không hoạt động**. Hãy kiểm tra series thật ở `/actuator/prometheus`, query không lọc URI, và chỉ dùng labels thực tế có mặt.

## 17. Quan hệ giữa RPS, latency và concurrency: Little's Law

Trong hệ thống gần trạng thái ổn định, Little’s Law cho biết:

\[
L = \lambda W
\]

Trong đó:
- `L` = số request/work items trung bình trong hệ thống đang được đo.
- `λ` = arrival/completion rate tương ứng (requests/second).
- `W` = thời gian trung bình một request nằm trong hệ thống/ranh giới đó (seconds).

Ví dụ ở một ranh giới đo nhất quán:
- 20 requests/second, latency mean 0.25s ⇒ trung bình khoảng **5 requests in-flight**.
- 20 requests/second, latency mean 1s ⇒ trung bình khoảng **20 requests in-flight**.

**Điều kiện quan trọng:** cùng tập requests, cùng boundary, hệ thống ổn định và xét trung bình đủ dài. Nếu metric active bao gồm SSE streams kéo dài còn timer completed chỉ bao gồm các JSON requests ngắn, áp dụng Little’s Law vào hai tập khác nhau là sai. Nếu upstream queue không được tính trong server observation, `L` từ active metric cũng không phản ánh queue đó.

Từ Little’s Law, khi RPS gần không đổi mà active count tăng, latency/queueing có thể đang xấu đi. Nhưng phải quan sát thêm CPU, Tomcat/Netty capacity, downstream pool và timeout để tìm **nguyên nhân**, không suy luận cơ học “cần tăng số threads”.

### Dấu hiệu vận hành

| RPS | Latency | Active count | Nhận định ban đầu |
|---|---|---|---|
| Tăng | Ổn định | Tăng tương ứng | Nhiều công việc hơn; có thể vẫn khỏe |
| Không đổi | Tăng | Tăng | Có thể nghẽn downstream, chờ lock, pool, CPU |
| Giảm | Tăng | Cao | Đang saturation, queue/backpressure hoặc timeout |
| Không đổi | Ổn định | Cao mãi | Streaming/long polling hoặc leaked in-flight work |
| Giảm về 0 | N/A | 0 | Có thể không có traffic **hoặc** metrics/target mất; xem `up` |
| Error rate tăng | Có thể giảm hoặc tăng | Bất kỳ | Fail-fast hoặc timeout; cần phân tích status/trace |

Bảng chỉ là **heuristics**. Chẩn đoán production cần latency distributions, traces, logs và saturation metrics đồng thời.

## 18. Tomcat runtime metrics: bối cảnh để hiểu active HTTP

Trong demo bật:

~~~yaml
server:
  tomcat:
    mbeanregistry:
      enabled: true
~~~

Spring Boot có thể công bố metrics dưới prefix `tomcat.` qua Tomcat MBean Registry. Tùy phiên bản/connector, bạn có thể thấy:
- Worker threads hiện tại/busy.
- Số connections liên quan Tomcat connector.
- Session metrics (nếu server và cấu hình cung cấp).
- Request-processing metrics theo connector.

Dùng:

~~~bash
curl -sS http://localhost:8080/actuator/metrics
~~~

Sau đó kiểm tra tên thật bắt đầu bằng `tomcat.` và drill-down từng meter, **không đoán mọi Tomcat sub-meter luôn tồn tại**. Nếu đang chạy WebFlux trên Reactor Netty, bạn sẽ không có Tomcat MBeans cùng mô hình đó; phải dùng Reactor Netty metrics/connection provider metrics phù hợp.

### Cách đọc phối hợp

Một snapshot có:
- HTTP active requests = 200.
- Tomcat busy threads = 20.
- TCP connections = 900.

Điều này **không mâu thuẫn**: có thể nhiều HTTP async requests không giữ worker thread, còn 900 keep-alive sockets có nhiều connections đang idle. Nếu Tomcat busy threads gần giới hạn và queue/latency tăng, cần tìm blocking/downstream latency. Nếu active requests tăng chủ yếu do SSE, cần quan sát streams/client counts, không tự điều chỉnh Tomcat max threads.

**Đừng dùng `Thread.sleep` của demo như mô hình production capacity**; nó cố ý làm servlet threads bận để người học dễ thấy metric thay đổi.

## 19. Spring WebFlux và reactive HTTP server observations

WebFlux cũng có instrumentation HTTP server mặc định từ Spring Boot Actuator, thường cùng logical meter name `http.server.requests` và active timer tương ứng khi được bật; nhưng runtime hoạt động khác:

- Handler trả `Mono`/`Flux`, Reactor Netty event loop không nên bị block.
- Một request có thể chờ downstream không block event loop, vẫn là active HTTP observation.
- Một `Flux<ServerSentEvent<?>>` streaming lâu có thể giữ observation active, ảnh hưởng active count và timer latency khi kết thúc.
- HTTP/2 multiplexing khiến active request streams không bằng TCP connections.

### Fragment WebFlux đúng cách

~~~java
// Fragment trong @RestController của project WebFlux:
@GetMapping("/api/reactive-slow")
public Mono<Map<String, String>> slow() {
    return Mono.delay(Duration.ofSeconds(3))
        .map(ignored -> Map.of("message", "done"));
}
~~~

Cần imports `reactor.core.publisher.Mono`, `java.time.Duration`, `java.util.Map`, `org.springframework.web.bind.annotation.GetMapping`. Đây là **fragment**, không phải source file standalone. Nó tạo delay async 3s mà không giữ event loop bằng `Thread.sleep`.

**Không chuyển code MVC demo sang WebFlux chỉ bằng cách đổi starter** nếu vẫn giữ `Thread.sleep`. Trong WebFlux, blocking code có thể làm chậm tất cả connections chia sẻ event loop. Dùng async APIs hoặc cô lập thư viện blocking qua `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` khi không thể thay thế.

### Metrics không phải trace của downstream

Nếu WebFlux handler gọi một partner service bằng WebClient, server timer đo vòng đời request inbound theo observation, còn outbound WebClient có thể tạo `http.client.requests` khi dùng auto-configured builder/instrumentation. Để biết latency 3s đến từ database, partner hay serialization, cần child spans/tracing hoặc custom business timers thêm; một HTTP server timer không tự phân rã từng đoạn.

## 20. Quan sát requests bị timeout, cancel và client disconnect

Không phải request nào cũng kết thúc với một `200` hoặc `500` “đẹp”:
- Client hủy request giữa chừng.
- Browser navigation làm cancel streaming.
- Reverse proxy hết timeout và trả 504 cho client, trong khi origin vẫn đang xử lý.
- Servlet asynchronous request timeout.
- Reactor Netty network disconnect.
- Application graceful shutdown cắt long-lived stream.

Hệ quả:
- Active LongTaskTimer giảm khi observation thực sự kết thúc/cancel, nhưng thời điểm có thể trễ do phát hiện disconnect.
- Completed Timer có thể ghi những samples/status phản ánh kết quả ở **origin**, khác trạng thái proxy phát cho client.
- Nếu request bị gateway từ chối trước khi đến ứng dụng, không có origin sample.
- Một response đã commit 200 rồi streaming fail sau đó có thể không đổi được HTTP status về 500; hãy ghi error signals riêng và quan sát client.

Khi tìm timeout:
1. So sánh `http.server.requests` và `http.client.requests` qua service traces.
2. Xem proxy ingress metrics 499/502/503/504 tương ứng với vendor.
3. Xem active count có giảm sau cancellation hay tăng kéo dài.
4. Kiểm tra deadline của client, LB/proxy, Servlet async và Reactor operator.
5. Xác minh có cleanup subscription/resource khi client disconnect hay không.

**Không đánh đồng “request trả 504 tại gateway” với “Spring Boot có status=504”**; gateway có thể sinh response mà JVM chưa biết.

## 21. HTTP server metric name và tùy biến ObservationConvention

Spring Boot 3.5 cho phép đổi tên observation HTTP server bằng:

~~~yaml
management:
  observations:
    http:
      server:
        requests:
          name: http.server.requests
~~~

Tên mặc định đã là `http.server.requests`. Chỉ đổi khi bạn có migration plan cho dashboards, recording rules và alerts; đổi tên sẽ làm query Prometheus cũ không còn thấy series mới.

Để bổ sung low-cardinality tags hoặc thay conventions, Spring Framework cung cấp:
- **MVC:** `org.springframework.http.server.observation.DefaultServerRequestObservationConvention` / `ServerRequestObservationConvention`.
- **WebFlux:** các types tương ứng trong `org.springframework.http.server.reactive.observation`.

Tùy biến nên theo **HTTP route templates**, service tier hoặc tên nhóm API hữu hạn; tránh raw URL/query/user ID. Không tự gắn exception message làm tag. Thay observation convention có thể ảnh hưởng **metrics và trace attributes**, vì cùng được sinh từ observations theo hướng dẫn Framework.

### Trường hợp tự viết Gauge active requests

Một số hệ thống có nhu cầu đo “business requests in progress” không trùng observation boundary: ví dụ chỉ tính một nhóm APIs sau authentication, loại SSE. Khi đó có thể tạo **custom Gauge/AtomicInteger** hoặc LongTaskTimer riêng với scope rõ, nhưng:
- Counter phải tăng/giảm cho mọi path hoàn thành, error, timeout, cancel.
- Async MVC/WebFlux cần đo theo **publisher lifecycle**, không chỉ method enter/exit.
- Tag cardinality và metric name phải tránh đụng built-in meters.
- Không định nghĩa tên custom trùng `http.server.requests.active` rồi vô tình double count.

**Ưu tiên built-in metrics cho HTTP trước**, chỉ thêm custom instrumentation khi ranh giới đo đã được định nghĩa và kiểm thử.

## 22. Dashboard tối thiểu cho một API service

Một dashboard hữu ích nên hiển thị đồng thời:

| Panel | Metric/query | Ý nghĩa |
|---|---|---|
| Traffic RPS | `sum(rate(http_server_requests_seconds_count[5m]))` | Throughput completed requests |
| HTTP 5xx rate | `sum(rate(...{status=~"5.."}[5m]))` | Server errors/second |
| HTTP 5xx ratio | 5xx count rate / total count rate | Error percentage |
| Mean latency | rate(total duration) / rate(count) | Trung bình thời gian completed requests |
| p95/p99 latency | `histogram_quantile` từ `_bucket` | Tail latency |
| Requests under SLO | `le="0.3"` bucket / total | SLO 300ms khi có bucket này |
| Active requests | `sum(http_server_requests_active_seconds_count)` | Số observations đang xử lý |
| Active age | `http_server_requests_active_seconds_max` hoặc active sum | Request đang mở lâu, kiểm tra semantics |
| Tomcat busy/current threads | Names thực trong `tomcat.*` | Worker pool saturation |
| JVM heap/GC/process CPU | Built-in Micrometer JVM/system meters | Runtime pressure |
| Availability | Prometheus `up` / Actuator health | Endpoint có thể scrape/phục vụ không |
| Dependency latency | `http.client.requests`, DB metrics/traces | Nguyên nhân downstream |

**Không dùng traffic RPS = 0 làm bằng chứng tuyệt đối hệ thống “khỏe”**. Nếu Prometheus target down, cả RPS và active gauges có thể không còn series; tạo alert riêng cho `up == 0` và số targets mong đợi.

### Thêm các nhãn hữu dụng, đừng nhân series vô hạn

Các nhãn có thể hợp lý: `application`, `environment`, `region`, `instance`, `method`, `uri template`, `outcome`, `status`. Nhưng phải giới hạn số combinations. Nếu cần drill-down từng request, dùng trace ID trong logs/traces với retention/phân quyền, **không đưa trace ID vào metric labels**.

## 23. Cảnh báo latency và saturation: cần điều kiện traffic

Không nên alert “p99 > 1s” khi một service có đúng một request trong cả 10 phút, hoặc chỉ dựa vào `active_requests > 100` mà không biết đó là SSE subscriptions. Kết hợp:
- Lưu lượng tối thiểu / sample count.
- Error budget hoặc mục tiêu SLO theo route class.
- Thời gian tồn tại vi phạm (ví dụ `for: 5m`).
- Ranh giới metrics: gateway vs origin, completed vs in-flight.
- Hành vi bình thường của streaming routes.
- Capacity của mỗi replica và autoscaling.

Một Prometheus alert rule **minh họa**, không thay toàn bộ SLO của tổ chức:

~~~yaml
groups:
  - name: spring-http
    rules:
      - alert: ElevatedHttp5xxRatio
        expr: |
          (
            sum(rate(http_server_requests_seconds_count{
              job="spring-web-runtime",status=~"5.."
            }[5m]))
            /
            clamp_min(
              sum(rate(http_server_requests_seconds_count{
                job="spring-web-runtime"
              }[5m])),
              1e-9
            )
          ) > 0.05
          and
          sum(rate(http_server_requests_seconds_count{
            job="spring-web-runtime"
          }[5m])) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Spring HTTP 5xx ratio above 5 percent"
~~~

Phép `and` ở đây chỉ kích hoạt khi tỷ lệ lỗi >5% **và** traffic >1 RPS trong cùng phạm vi; những ngưỡng chỉ là ví dụ. Production cần alert cho no-traffic/down-target độc lập để không che outage 100%.

### Active requests alert như thế nào?

Một sample query:

~~~promql
sum by (instance) (
  http_server_requests_active_seconds_count{
    job="spring-web-runtime"
  }
)
~~~

So sánh với baseline và giới hạn thực tế của instance: Tomcat max threads, connection pools, CPU, memory, streaming subscriber counts. Một giá trị 100 có thể bình thường với reactive SSE nhưng đáng lo nếu mỗi request đang giữ một JDBC connection.

**Đừng dùng per-route active alert cứng** nếu metric active không có uri tag xác định trước khi response hoàn tất. Nếu cần metric business inflight theo route, instrument một meter riêng tại ranh giới thích hợp.

## 24. Troubleshooting: metrics không xuất hiện hoặc không đúng

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| `/actuator/metrics` trả 404 | Actuator thiếu/exposure chưa bật, path khác | Kiểm tra starter, include, base-path, management port |
| `/actuator/prometheus` trả 404 | Thiếu registry `micrometer-registry-prometheus` hoặc chưa expose | Thêm registry, include prometheus, restart |
| Metrics endpoint trả 401/403 | Spring Security/management access | Xác thực đúng quyền; không tắt auth đại trà |
| Có JVM metrics nhưng không có `http.server.requests` | Chưa có request được instrument, observation disabled, path không thuộc handler | Gọi `/api/fast` rồi tra meter, kiểm tra config/stack |
| Có completed Timer nhưng không có `http.server.requests.active` | LongTaskTimer disabled/khác version/metric filtered | Kiểm tra property Boot3.5, meter name thật, scrape trong lúc slow request |
| `active_count=0` dù có RPS cao | Scrape trượt những requests quá ngắn | Test request chậm 10s, tăng frequency hoặc đo load ổn định |
| Active theo `uri=/api/slow/{jobId}` không thấy | In-flight tags có `uri=UNKNOWN` hoặc chưa set | Query aggregate không lọc URI và xem labels thực |
| `_bucket` không xuất hiện | Histogram/SLO chưa bật hoặc config/registry khác | Kiểm tra distribution config, metrics output |
| p95 query rỗng/NaN | Không có bucket data, traffic thấp, sai label selection | Kiểm tra `_bucket` và `le` thực tế |
| Mean latency đơn vị rất lớn/nhỏ | Nhầm seconds với ms hoặc lấy `_sum` không chia count | Sử dụng rate(sum)/rate(count), nhân 1000 cho ms |
| RPS bị nhân đôi | Scrape duplicate targets, thêm counter trùng hoặc sai aggregation | Kiểm tra targets và labels/job/instance |
| Counts reset sau deploy | Process restart, Timer counters reset | Dùng `rate()/increase()` phù hợp |
| Max latency “giảm về 0” sau một lúc | Micrometer `MAX` có time-window reset/decay | Không coi MAX là all-time maximum |
| Có HTTP 502 tại CDN nhưng origin 5xx=0 | Edge tạo lỗi trước/ngoài Spring | So sánh gateway/CDN và origin metrics |
| Error `exception=none` dù status=500 | Exception đã handled, tag không phản ánh root cause | Xem status, logs, traces, handler behavior |
| Active metric tăng mãi | Streams SSE/WS, async không complete, cancellation leak | Phân loại routes, xem open connections/subscriptions, thread dump |
| Tomcat busy metrics không xuất hiện | Tomcat MBean registry chưa bật hoặc không dùng Tomcat | `server.tomcat.mbeanregistry.enabled=true`, kiểm tra stack |
| Metrics quá nhiều time series | Raw URL/user ID tags hoặc histogram rộng | URI templates, cardinality budget, scope histograms |
| Prometheus scrape fail trong Docker | Dùng `localhost:8080` sai network namespace | Dùng service hostname/network route hợp lệ |
| Actuator endpoint công khai ra Internet | Exposure không có network/security control | Bảo vệ endpoint bằng auth/mTLS/ingress rules |

### Quy trình chẩn đoán gọn

1. Đảm bảo project chạy đúng Spring Boot version, starter, web stack.
2. Gửi vài requests fast, slow, error.
3. Kiểm tra `/actuator/metrics` có tên `http.server.requests` không.
4. Khi slow request còn mở, kiểm tra `http.server.requests.active`.
5. Kiểm tra `/actuator/prometheus`, phân biệt `_count` completed và active.
6. Kiểm tra Prometheus target status/`up` và series labels.
7. Xác nhận histogram buckets trước khi dùng `histogram_quantile`.
8. Đối chiếu tổng RPS, latency, 5xx và active với logs/traces.
9. Nếu nghi bottleneck, thêm Tomcat/Netty, JVM, DB pool, HTTP client metrics.
10. Đánh giá query/alert theo traffic, deployments và streaming workloads.

## 25. Bảo mật và chi phí của observability

**Actuator metrics có thể tiết lộ thông tin vận hành**: tên routes, trạng thái lỗi, counts, JVM/process metrics, chi tiết môi trường trong các endpoints khác. Không expose toàn bộ `/actuator/**` công khai chỉ vì cần Prometheus. Ngay cả `/actuator/prometheus` cũng nên được bảo vệ bằng một trong các cơ chế thích hợp:
- Private network hoặc service discovery + network policy.
- Dedicated management port gắn private interface/ingress.
- Authentication/authorization của Spring Security hoặc mTLS.
- Scraper credentials/secret rotation, TLS encryption.
- Phân quyền xem dashboards, alert routing và retention policy.

Trong project demo **không có Spring Security** nên `management.endpoints.web.exposure.include` làm metrics có thể được truy cập trực tiếp trên `localhost:8080`. Chỉ chạy môi trường học. Khi thêm `spring-boot-starter-security`, Boot có actuator security defaults khác, và một custom `SecurityFilterChain` có thể thay thế cấu hình tự động; kiểm tra policy thực tế chứ không giả định endpoints luôn private.

**Chi phí metric cardinality:** Histogram buckets nhân số time series theo mỗi combination tags, instances và boundaries. Bật histogram toàn bộ HTTP traffic có thể tăng đáng kể Prometheus ingestion/storage; nên chọn route classes/service SLO quan trọng, kiểm soát labels và theo dõi series count/cost.

## 26. Kiểm thử tự động: Timer xuất hiện và tags không nổ

Các tests thông thường không cần Prometheus server để xác minh Micrometer instrumentation. Trong Spring Boot integration test có Actuator, có thể gọi endpoints thực tế qua `MockMvc` hoặc `TestRestTemplate` rồi xem metrics; nhưng **đừng kỳ vọng mọi test slice tự bật tất cả production registries**. Mỗi test setup có thể thay `MeterRegistry` hoặc disable metrics. Với production QA, kiểm tra ít nhất:
- `GET /api/fast` trả 200 và `http.server.requests` count tăng.
- `GET /api/error` trả 503 và status tag được phản ánh.
- `GET /api/slow/{jobId}` với nhiều job IDs vẫn dùng **một URI template tag**.
- Slow request đang chạy được LongTaskTimer active ghi nhận khi sample.
- Histogram buckets có đúng SLO boundaries cần dùng.
- Prometheus scrape không lỗi và series count dưới budget.
- Nhiều replicas cho mean/p95 aggregate đúng.
- Client disconnect và streaming cancel không để active gauge rò vô hạn.

### Ví dụ kiểm tra bằng curl với một route variable

~~~bash
curl -sS -o /dev/null \
  "http://localhost:8080/api/slow/job-100?ms=1"
curl -sS -o /dev/null \
  "http://localhost:8080/api/slow/job-200?ms=1"
curl -sS -o /dev/null \
  "http://localhost:8080/api/slow/job-300?ms=1"
~~~

Kiểm tra meter theo `uri`:

~~~bash
curl -sS --get \
  --data-urlencode 'tag=uri:/api/slow/{jobId}' \
  http://localhost:8080/actuator/metrics/http.server.requests
~~~

Bạn nên thấy `COUNT` cho cùng template route tăng theo các requests phù hợp, không có ba label URI khác nhau mang giá trị `job-100`, `job-200`, `job-300`. Con số chính xác còn phụ thuộc những lần gọi khác và exposure config; không assert raw output nguyên văn.

## 27. Câu hỏi ôn tập

**1.** `http.server.requests` có đếm một request ngay khi request bắt đầu không?

**Đáp án:** Timer được ghi khi observation hoàn tất. Để biết request đang xử lý, dùng LongTaskTimer `http.server.requests.active` (khi version/config hỗ trợ).

**2.** `http_server_requests_seconds_count` và `http_server_requests_active_seconds_count` đều là cumulative counters?

**Đáp án:** Không. Series đầu thường là completed request count tăng dần; series sau là **active task count snapshot** của LongTaskTimer và có thể tăng/giảm.

**3.** Vì sao không dùng `rate(http_server_requests_active_seconds_count[5m])` để tính RPS?

**Đáp án:** Active count là gauge số công việc đang chạy, không phải counter completed requests. RPS tính từ `rate(http_server_requests_seconds_count[5m])`.

**4.** Làm sao tính latency trung bình từ Prometheus?

**Đáp án:** Lấy `sum(rate(http_server_requests_seconds_sum[5m])) / sum(rate(http_server_requests_seconds_count[5m]))` với labels/scopes giống nhau; đơn vị seconds/request.

**5.** Vì sao p95 toàn hệ thống nên dùng histogram thay vì average các p95 trên từng pod?

**Đáp án:** Percentiles không aggregable bằng trung bình. Histogram buckets có thể cộng theo `le` rồi dùng `histogram_quantile` để ước lượng p95 toàn bộ distribution.

**6.** Nếu `/actuator/metrics/http.server.requests.active` trả active=0 nhưng Timer count lớn, ứng dụng có vấn đề không?

**Đáp án:** Không nhất thiết. Request rất ngắn có thể hoàn tất trước snapshot; hai loại meters đo hai trạng thái khác nhau.

**7.** Một HTTP/2 connection có ba active streams, có phải active HTTP requests=1 không?

**Đáp án:** Không. Một connection có thể mang nhiều request streams; request-level active metric có thể phản ánh nhiều observations.

**8.** Vì sao metric `uri=/api/items/123` theo từng ID là nguy hiểm?

**Đáp án:** Cardinality tăng theo số IDs, gây tốn memory/Prometheus storage. Dùng route template `/api/items/{id}`.

**9.** Lúc client nhận 502 từ gateway nhưng origin metrics không có 502, có mâu thuẫn không?

**Đáp án:** Không. Gateway có thể tạo 502 do upstream timeout/connection failure trước khi origin gửi response. Cần đối chiếu edge metrics và tracing.

**10.** `http.server.requests.active` có phải số Tomcat busy threads không?

**Đáp án:** Không. Async/reactive requests có thể đang active nhưng không giữ worker thread; keep-alive sockets có thể tồn tại khi không có active requests.

**11.** Khi bật histogram cho `http.server.requests`, vì sao cần kiểm tra cost?

**Đáp án:** Mỗi bucket nhân số combinations method/status/uri/instance, làm tăng time series và ingestion/storage.

**12.** Vì sao `http.server.requests.active` có thể thiếu `uri`/`status` tag giống completed Timer?

**Đáp án:** Khi request chưa kết thúc, route/final status có thể chưa xác định tại thời điểm active sample, dẫn đến `UNKNOWN` hoặc tags khác.

**13.** Nên bật `management.endpoints.web.exposure.include="*"` trên public API chỉ để Prometheus scrape không?

**Đáp án:** Không. Expose tối thiểu `metrics`/`prometheus` khi cần và bảo vệ bằng private network/security controls.

**14.** Lấy `http_server_requests_seconds_max` làm max latency từ khi ứng dụng khởi động có đúng không?

**Đáp án:** Không. Micrometer max thường dùng time window/decay, có thể reset về 0 khi không có samples mới.

**15.** Làm sao phát hiện tăng đồng thời RPS và active requests có phải overload?

**Đáp án:** Cần xem latency, error rate, instance capacity, queues, CPU/thread usage và downstream; concurrency tăng tương ứng RPS không tự là dấu hiệu lỗi.

### Bài tập mở rộng

Từ dự án mục 7:
1. Gọi nhanh `/api/fast` 100 lần, đọc completed Timer count và so với RPS từ Prometheus trong một cửa sổ đủ dài.
2. Gửi 2 requests `/api/slow/A?ms=10000` và `/api/slow/B?ms=10000` đồng thời; scrape `http.server.requests.active` khi chúng chưa kết thúc và ghi lại active snapshot, current duration.
3. Sau khi requests hoàn thành, kiểm tra Timer completed count/total duration tăng nhưng active count trở về nền.
4. Thêm 10.000 job IDs khác nhau vào path template và đo label cardinality; **không dùng IDs thật của người dùng**.
5. Bật/tắt `percentiles-histogram`, so sánh `_bucket` và lượng series. Dùng PromQL cho p95, so với mean latency.
6. Chạy service sau NGINX/LB test, tạo gateway timeout và giải thích vì sao origin status/count khác client-observed error.
7. Nếu có WebFlux project, thay delay blocking bằng `Mono.delay` và quan sát active vs threads trong event loop, phân biệt sự khác nhau với MVC.
8. Thiết kế alert error rate có traffic floor và alert `up==0` riêng, rồi diễn giải tình huống ít traffic.

## 28. Nguồn tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Metrics và Observation/HTTP server instrumentation](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot 3.5 — Actuator Endpoints, Exposure và Security](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Spring Boot 3.5 — Metrics Endpoint REST API](https://docs.spring.io/spring-boot/3.5/api/rest/actuator/metrics.html)
- [Micrometer — Concepts: Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer — Concepts: Long Task Timers](https://docs.micrometer.io/micrometer/reference/concepts/long-task-timers.html)
- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Micrometer — Prometheus Registry](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
- [Spring Framework — MVC HTTP Server Observability](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Prometheus — Querying: Rate, Increase, Histogram Quantile](https://prometheus.io/docs/prometheus/latest/querying/functions/)
- [Prometheus — Metric Types: Histogram](https://prometheus.io/docs/concepts/metric_types/)
- [Prometheus — Instrumentation Best Practices](https://prometheus.io/docs/practices/instrumentation/)

**Ghi nhớ:** `http.server.requests` là **completed Timer** để tính throughput, error ratio, average latency và histogram quantiles; `http.server.requests.active` là **in-flight LongTaskTimer** để biết observations đang hoạt động. Khi giám sát HTTP, hãy đo **cùng một boundary**, giữ tags cardinality thấp, dùng PromQL đúng kiểu dữ liệu, so sánh với thread/connection/queue metrics và bảo vệ Actuator trước khi xuất sang Prometheus.
