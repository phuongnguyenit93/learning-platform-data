# Đo độ trễ, lỗi và số lần truy vấn cấu hình

Spring Cloud Config phân phối cấu hình qua các request giữa Config Client và Config Server. Một client thường truy vấn cấu hình khi khởi động hoặc khi được refresh; nó không hỏi Config Server mỗi lần một bean đọc property. Vì vậy, muốn quan sát hoạt động cấu hình cần đo đúng các sự kiện: số lần client fetch, thời gian mỗi lần fetch, lỗi kết nối hoặc xử lý, số lần refresh và thời gian Config Server phục vụ request.

Ba chỉ số quan trọng là **độ trễ**, **lỗi** và **lưu lượng truy vấn**. Độ trễ cho biết client phải chờ bao lâu để nhận cấu hình. Tỷ lệ lỗi cho biết mức độ tin cậy của Config Server và các nguồn phía sau như Git. Số request cho biết startup, retry hoặc refresh đang tạo bao nhiêu tải. Khi kết hợp ba chỉ số theo application, instance và loại thao tác, nhóm vận hành có thể phát hiện Config Server chậm, lỗi xác thực, refresh storm hoặc một nhóm replica liên tục fetch lại cấu hình.

Bài học này trình bày cách dùng Micrometer, Spring Boot Actuator, Prometheus, log có cấu trúc và tracing để quan sát luồng cấu hình từ client tới server và repository. Bạn cũng sẽ thiết kế metric riêng cho Config Client, phân biệt lỗi HTTP với lỗi parse/bind sau khi nhận response, xây dashboard, đặt cảnh báo và tránh làm lộ secret hoặc tạo metric có cardinality quá lớn.

Sau bài học, bạn có thể:

- Xác định những điểm cần đo ở Config Client, Config Server và repository.
- Phân biệt request lấy Environment với thao tác đọc property trong ứng dụng.
- Đo số lần fetch, thời gian fetch, tỷ lệ lỗi và số lần refresh.
- Dùng metric HTTP có sẵn của Spring Boot khi HTTP client/server được instrument.
- Tạo metric nghiệp vụ riêng bằng Micrometer khi cần theo dõi config fetch.
- Xuất metric qua Actuator và Prometheus.
- Viết truy vấn PromQL cho p95 latency, request rate và error ratio.
- Kết hợp log, trace và config revision để điều tra sự cố.
- Giới hạn cardinality và bảo vệ dữ liệu cấu hình nhạy cảm.

## 1. Quan sát từ đầu đến cuối luồng lấy cấu hình

Một lần lấy cấu hình có thể đi qua nhiều thành phần:

~~~mermaid
flowchart LR
    A["Application startup / refresh"] --> B["Config Client"]
    B -->|"HTTP request"| C["Load balancer"]
    C --> D["Config Server"]
    D --> E["EnvironmentRepository"]
    E --> F["Git / Vault / backend"]
    D -->|"Environment response"| B
    B --> G["Parse, decrypt, bind"]
    G --> H["Application Environment"]
~~~

Mỗi tầng trả lời một câu hỏi khác nhau:

| Điểm đo | Câu hỏi | Ví dụ chỉ số |
|---|---|---|
| Config Client | Client fetch mất bao lâu? Có retry hoặc timeout không? | Fetch duration, attempt count, error count |
| Load balancer | Request có bị phân phối lệch hoặc timeout không? | Upstream latency, retry, 5xx |
| Config Server HTTP | Server nhận bao nhiêu request và trả mã gì? | HTTP request count, duration, status |
| Repository backend | Git/Vault/Consul mất bao lâu để trả dữ liệu? | Repository lookup duration, backend errors |
| Client processing | Response có parse, decrypt và bind thành công không? | Parse/decrypt/bind failure count |
| Refresh lifecycle | Có bao nhiêu refresh và kết quả ra sao? | Refresh event, refresh success/failure |
| Runtime | Cấu hình mới có làm dịch vụ lỗi không? | Readiness, business error rate, latency |

Không nên chỉ đo HTTP 200 ở Config Server. Server có thể trả response thành công nhưng client vẫn gặp lỗi parse, decrypt, validation hoặc bind. Ngược lại, client có thể timeout dù server đã xử lý xong request nhưng response không tới được client.

## 2. Đếm đúng số lần truy vấn cấu hình

Config Client thường lấy Environment theo application, profile và label khi startup hoặc khi được yêu cầu refresh. Một request nghiệp vụ đọc <code>@Value</code> hoặc <code>@ConfigurationProperties</code> thường sử dụng giá trị đã nạp trong process, không tạo một request mới tới Config Server.

Cần phân biệt:

- **Environment fetch:** một lần client gọi Config Server để lấy property source.
- **HTTP attempt:** một lần gửi request thực tế; retry có thể tạo nhiều attempt cho một fetch logic.
- **Refresh event:** yêu cầu làm mới được nhận từ endpoint hoặc Bus.
- **Property access:** đọc một giá trị trong Environment hoặc bean, thường không gọi Config Server.
- **Server request:** request HTTP Config Server nhận được; có thể gồm retry và request từ nhiều client.

Ví dụ, một lần startup fetch bị timeout hai lần rồi thành công ở lần thứ ba có thể được ghi nhận là:

| Chỉ số | Giá trị |
|---|---:|
| Logical fetch | 1 |
| HTTP attempts | 3 |
| Failed attempts | 2 |
| Successful attempts | 1 |
| Startup config operation | 1 |

Nếu chỉ nhìn số HTTP request ở Config Server, bạn sẽ thấy ba request. Nếu chỉ đếm lần startup fetch, bạn sẽ thấy một. Cả hai đều hữu ích nhưng trả lời hai câu hỏi khác nhau.

Một lần <code>busrefresh</code> cũng không đồng nghĩa một lần Config Server query. Một Bus event có thể được phát tới nhiều client; mỗi client phù hợp sẽ thực hiện fetch riêng. Khi có retry, số request thực tế còn tăng thêm.

## 3. Metric HTTP có sẵn từ Spring Boot

Spring Boot Actuator và Micrometer có thể cung cấp metric HTTP cho server và client khi các thành phần tương ứng được instrument.

Ở phía server, metric phổ biến là:

- <code>http.server.requests</code>: thời gian và số lượng request HTTP đi vào ứng dụng.
- Các tag thường gặp: <code>method</code>, <code>uri</code>, <code>status</code>, <code>outcome</code>, <code>exception</code>.

Ở phía client, <code>http.client.requests</code> có thể được ghi khi HTTP client được hỗ trợ và instrument, ví dụ RestClient, WebClient hoặc RestTemplate theo cấu hình và phiên bản Spring Boot đang dùng.

Không nên mặc định mọi phiên bản Spring Cloud Config Client đều xuất ra một metric tên cố định như <code>config.client.requests</code>. Việc có <code>http.client.requests</code> còn phụ thuộc HTTP client mà Config Client sử dụng và cơ chế instrumentation đang bật. Hãy kiểm tra metric thực tế tại <code>/actuator/metrics</code> hoặc Prometheus trước khi viết dashboard.

### Metric server cho Config Server

Các request lấy Environment thường xuất hiện trong <code>http.server.requests</code>. Có thể lọc theo URI template, method và status để xem:

- Bao nhiêu request GET được nhận.
- Request nào trả 2xx, 4xx hoặc 5xx.
- p50, p95 và p99 latency.
- Request nào chậm bất thường theo instance Config Server.

URI tag nên là route template do framework ghi nhận, không nên tự đưa URL có giá trị động, token hoặc toàn bộ label vào tag.

### Metric client cho Config Client

Nếu HTTP client được instrument, <code>http.client.requests</code> giúp quan sát thời gian gọi Config Server và trạng thái response. Nếu không có metric phù hợp hoặc cần phân biệt startup, refresh, retry, parse và bind, hãy bổ sung metric riêng ở ranh giới Config Client.

## 4. Bật Actuator và Prometheus endpoint

Thêm dependency Actuator và registry Prometheus phù hợp với Spring Boot version của dự án. Ví dụ cấu hình:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: ${spring.application.name}
    distribution:
      percentiles-histogram:
        http.server.requests: true
        http.client.requests: true
        config.client.fetch: true
~~~

<code>micrometer-registry-prometheus</code> cung cấp registry để Prometheus scrape. Endpoint thường là:

~~~http
GET /actuator/prometheus
~~~

Có thể xem một metric cụ thể qua:

~~~http
GET /actuator/metrics/http.server.requests
~~~

<code>/actuator/metrics</code> hữu ích để kiểm tra tại chỗ, còn Prometheus endpoint phục vụ scrape và lưu chuỗi thời gian. Các endpoint quản trị/metric nên được giới hạn trên management port hoặc private network và bảo vệ bằng authentication/authorization phù hợp. Không expose toàn bộ Actuator ra Internet chỉ để Prometheus đọc metric.

### Kiểm tra metric thực tế

Trước khi xây dashboard:

1. Gọi một request Config Client tới Config Server.
2. Kiểm tra <code>http.server.requests</code> ở Config Server.
3. Kiểm tra <code>http.client.requests</code> ở client nếu HTTP instrumentation có mặt.
4. Kiểm tra endpoint Prometheus có xuất metric và tag mong muốn.
5. Xác nhận request bị lỗi cũng được ghi nhận.
6. Kiểm tra URI tag không chứa token, secret hoặc giá trị động nhạy cảm.

Nếu metric client không xuất hiện, xác minh HTTP client instrumentation và dependency trước khi tự tạo một metric trùng tên hoặc kết luận Config Client không fetch.

## 5. Thiết kế metric riêng cho Config Client

Khi cần tách lần fetch logic khỏi từng HTTP attempt, nên tạo metric mang ý nghĩa cấu hình. Một bộ metric có thể gồm:

| Metric | Loại | Ý nghĩa |
|---|---|---|
| <code>config.client.fetch</code> | Timer | Thời gian một lần fetch logic |
| <code>config.client.fetch.attempts</code> | Counter | Số HTTP attempt thực tế |
| <code>config.client.fetch.errors</code> | Counter | Số fetch thất bại |
| <code>config.client.refresh.events</code> | Counter | Số refresh event nhận được |
| <code>config.client.refresh.failures</code> | Counter | Số refresh không hoàn tất |
| <code>config.client.config.age</code> | Gauge | Tuổi của revision đang dùng |
| <code>config.client.last.success</code> | Gauge | Thời điểm fetch thành công gần nhất, nếu cần |

Đây là tên metric do ứng dụng/nhóm nền tảng định nghĩa, không phải tên mặc định được đảm bảo bởi Spring Cloud Config. Chọn một naming convention thống nhất và ghi rõ đơn vị, ý nghĩa, vị trí instrumentation.

Timer Micrometer tự giữ số lần ghi nhận và tổng thời gian. Khi bật histogram, nó còn xuất bucket để tính percentile ở Prometheus. Vì vậy, <code>config.client.fetch</code> vừa dùng để tính latency vừa cho biết số lần fetch logic qua hậu tố <code>_count</code>.

### Tag nên dùng

Các tag có giá trị hữu hạn, dễ nhóm:

- <code>application</code>: tên service từ danh sách đã kiểm soát.
- <code>trigger</code>: <code>startup</code>, <code>refresh</code>, <code>bus</code> hoặc <code>scheduled</code>.
- <code>outcome</code>: <code>success</code> hoặc <code>error</code>.
- <code>error_type</code>: nhóm lỗi như <code>timeout</code>, <code>network</code>, <code>http_4xx</code>, <code>http_5xx</code>, <code>parse</code>, <code>decrypt</code>, <code>bind</code>, <code>other</code>.

Không dùng tag có giá trị gần như duy nhất cho mỗi request:

- Token, password, secret hoặc nội dung Environment.
- Property key bất kỳ.
- Full URL có query string.
- Exception message.
- Commit SHA hoặc label thay đổi theo từng release.
- Request ID, trace ID hoặc user ID.

Các giá trị có cardinality cao nên để trong log/trace có kiểm soát, không đưa thành label Prometheus.

## 6. Ghi nhận thời gian fetch và lỗi bằng Micrometer

Ví dụ sau minh họa một wrapper đo một lần fetch logic. <code>trigger</code> phải đến từ tập giá trị cố định, không lấy tùy ý từ request:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.Timer.Sample;

import java.util.function.Supplier;

public final class ConfigFetchMetrics {

    private final MeterRegistry registry;

    public ConfigFetchMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T record(String trigger, Supplier<T> fetch) {
        Sample sample = Timer.start(registry);
        String outcome = "success";
        String errorType = "none";

        try {
            return fetch.get();
        } catch (RuntimeException ex) {
            outcome = "error";
            errorType = classify(ex);
            throw ex;
        } finally {
            sample.stop(Timer.builder("config.client.fetch")
                .tag("trigger", trigger)
                .tag("outcome", outcome)
                .register(registry));

            if ("error".equals(outcome)) {
                Counter.builder("config.client.fetch.errors")
                    .tag("trigger", trigger)
                    .tag("error_type", errorType)
                    .register(registry)
                    .increment();
            }
        }
    }

    private String classify(RuntimeException ex) {
        // Ánh xạ sang một số nhóm lỗi cố định.
        // Không dùng exception message làm metric tag.
        Throwable cause = ex;
        while (cause != null) {
            if (cause instanceof java.net.SocketTimeoutException) {
                return "timeout";
            }
            cause = cause.getCause();
        }
        return "other";
    }
}
~~~

Wrapper này đo thời gian từ lúc bắt đầu gọi <code>fetch</code> tới khi kết quả trả về hoặc exception thoát ra. Nó không tự biết cách Config Client nội bộ retry hoặc parse nếu phần đó nằm ngoài supplier. Đặt wrapper quanh đúng ranh giới cần đo.

Để đếm từng HTTP attempt, instrument ở tầng HTTP client hoặc retry callback. Nếu wrapper nằm ngoài retry template, Timer đếm một logical fetch; nếu nằm bên trong, nó có thể đếm mỗi attempt. Đặt tên metric và mô tả theo đúng vị trí để tránh diễn giải sai.

Trong ứng dụng thực tế, phân loại lỗi nên bao gồm các nhóm hữu hạn: network/timeout, HTTP authorization, HTTP server, repository, parse, decrypt và bind. Exception class cụ thể có thể được ánh xạ sang nhóm; tránh tag bằng tên message hoặc nội dung lỗi có thể chứa dữ liệu nhạy cảm.

## 7. Đo riêng thời gian repository backend

Thời gian Config Server trả Environment có thể bao gồm nhiều phần:

- Nhận và xác thực request.
- Tìm application/profile/label.
- Đọc property source từ repository.
- Fetch hoặc cập nhật Git clone nếu cần.
- Giải mã giá trị <code>{cipher}</code>.
- Tạo response và serialize dữ liệu.

Metric <code>http.server.requests</code> đo thời gian xử lý request tổng thể ở server, nhưng không cho biết phần nào chiếm nhiều thời gian. Nếu Git hoặc Vault là nút thắt, cần instrument riêng thao tác backend.

Một số metric tùy chỉnh có thể gồm:

| Metric | Ý nghĩa |
|---|---|
| <code>config.server.repository.lookup</code> | Thời gian đọc EnvironmentRepository |
| <code>config.server.git.fetch</code> | Thời gian fetch/pull Git nếu thao tác đó diễn ra |
| <code>config.server.git.clone</code> | Thời gian clone repository |
| <code>config.server.decrypt</code> | Thời gian giải mã property |
| <code>config.server.environment.errors</code> | Lỗi tạo Environment |

Không phải request nào cũng fetch Git từ upstream. Một request có thể đọc local clone đã có sẵn. Vì vậy, số lần Environment request và số lần Git fetch không nhất thiết bằng nhau. Instrument tại đúng thao tác repository để đo được số lần backend thực sự được gọi.

Nếu dùng nhiều backend như Git, Vault hoặc Consul, nên có tag <code>backend</code> với tập giá trị nhỏ, ví dụ <code>git</code>, <code>vault</code>, <code>consul</code>. Không tag tên repository riêng tư hoặc URL chứa credential.

## 8. Phân loại lỗi để biết hỏng ở tầng nào

Một dashboard chỉ có <code>status=5xx</code> không đủ giải thích toàn bộ lỗi cấu hình.

| Nhóm lỗi | Ví dụ | Điểm quan sát |
|---|---|---|
| Network/timeout | DNS lỗi, connect timeout, read timeout | Client HTTP, load balancer |
| Authentication/authorization | Config Client bị 401/403 | HTTP response, security audit |
| Not found | Sai application/profile/label | Config Server response và log |
| Repository | Git fetch, credential hoặc clone lỗi | EnvironmentRepository/Git instrumentation |
| Parse | YAML/Properties không hợp lệ | Client processing hoặc server parser |
| Decrypt | Ciphertext sai hoặc thiếu key | Config Server decrypt processing |
| Bind/validation | Kiểu dữ liệu hoặc constraint sai | Client startup/refresh logs |
| Refresh lifecycle | Event nhận được nhưng bean/resource tạo lại lỗi | Refresh event và application logs |

Một số lỗi parse/decrypt có thể xảy ra ở server trước khi response được trả. Lỗi bind có thể chỉ xuất hiện sau khi client nhận response. Cần thu metric ở cả hai phía để phân biệt.

### Tách error rate của HTTP và error rate của config operation

Ví dụ Config Server trả HTTP 200 nhưng client không bind được thuộc tính. HTTP server error rate có thể bằng 0, trong khi config operation failure rate lớn hơn 0. Ngược lại, client có thể timeout trước khi nhận response dù server đã hoàn tất request.

Vì thế, hãy theo dõi riêng:

- HTTP request success/error ở Config Server.
- HTTP fetch success/error ở Config Client.
- Config parse/decrypt/bind success/error.
- Refresh operation success/error.
- Business health sau khi cấu hình mới được áp dụng.

## 9. PromQL cho latency, request count và error ratio

Giả sử Timer Micrometer tên <code>config.client.fetch</code> được export qua Prometheus. Tên metric thường được chuẩn hóa thành <code>config_client_fetch_seconds_*</code>.

### p95 latency

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(config_client_fetch_seconds_bucket[5m])
  )
)
~~~

Biểu đồ này cho biết 95% logical fetch có thời gian nhỏ hơn hoặc bằng giá trị p95 trong cửa sổ 5 phút. Cần bật histogram cho Timer và scrape đủ dữ liệu.

### Số lần fetch trong một giờ

~~~promql
sum(increase(config_client_fetch_seconds_count[1h]))
~~~

Timer <code>_count</code> đếm số lần wrapper ghi nhận. Nếu wrapper đặt ngoài retry, đây là số logical fetch; nếu đặt bên trong retry, nó có thể là số attempt.

### Tỷ lệ fetch thất bại

~~~promql
sum(rate(config_client_fetch_seconds_count{outcome="error"}[5m]))
/
clamp_min(sum(rate(config_client_fetch_seconds_count[5m])), 1)
~~~

Đây là tỷ lệ các lần fetch được ghi nhận với outcome error. Nếu cần error counter độc lập, có thể dùng <code>config_client_fetch_errors_total</code>:

~~~promql
sum(rate(config_client_fetch_errors_total[5m]))
~~~

### Request rate ở Config Server

Metric HTTP server của Spring Boot thường được export dưới tên tương tự:

~~~promql
sum by (uri, status) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

Tên tag/metric có thể thay đổi theo phiên bản và registry. Kiểm tra output thực tế ở <code>/actuator/prometheus</code> trước khi dùng truy vấn trong dashboard.

### p95 latency của Config Server

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Giữ số lượng URI group nhỏ bằng route template. Không nhóm theo raw URL hoặc path chứa label tùy ý.

## 10. Thiết kế dashboard vận hành

Một dashboard hiệu quả nên cho phép nhìn thấy tổng quan rồi drill-down vào ứng dụng hoặc instance bị lỗi.

| Panel | Nội dung | Câu hỏi vận hành |
|---|---|---|
| Config fetch rate | Logical fetch/second và HTTP attempt/second | Có tăng đột biến không? |
| Fetch latency | p50, p95, p99 | Client phải chờ bao lâu? |
| Fetch error ratio | Error/total theo trigger | Startup hay refresh đang lỗi? |
| Config Server request | Request rate theo URI/status | Server nhận tải từ đâu? |
| Repository latency | Git/Vault/Consul operation duration | Backend nào đang chậm? |
| Refresh events | Event count, success, failure | Có refresh storm hoặc Bus issue không? |
| Retry attempts | Attempt count trên mỗi logical fetch | Có lỗi tạm thời kéo dài? |
| Config age | Tuổi revision đang chạy | Instance có dùng cấu hình stale không? |
| JVM and process | CPU, heap, threads, connection pool | Server có cạn tài nguyên không? |

Nên có filter theo <code>application</code>, <code>trigger</code>, <code>outcome</code>, <code>backend</code> và instance từ scrape target. Cẩn thận khi dashboard cho phép chọn label hoặc revision; dùng log/tracing để xem chi tiết release thay vì tạo hàng nghìn series metric.

## 11. Đặt cảnh báo theo SLO và nguyên nhân

Cảnh báo nên dựa trên mức ảnh hưởng và cửa sổ thời gian đủ ổn định. Ví dụ:

- p95 Config fetch vượt startup budget trong nhiều cửa sổ liên tiếp.
- Error ratio tăng cao ở <code>trigger=startup</code>.
- Client refresh failure tăng sau một đợt phát Bus event.
- Config Server 5xx tăng cùng repository latency.
- Số retry trên mỗi logical fetch tăng bất thường.
- Config age của instance vượt giới hạn policy.
- Một Config Server replica không phục vụ đúng revision hoặc liên tục mất readiness.

Không cảnh báo chỉ vì có một request lỗi đơn lẻ nếu hệ thống có retry và request sau đã thành công. Tuy nhiên, lỗi xác thực, decrypt hoặc bind có thể cần cảnh báo ngay vì retry không sửa được nguyên nhân.

Khi thiết kế SLO, phân biệt:

- **Availability:** tỷ lệ config operation thành công.
- **Latency:** thời gian client lấy được cấu hình.
- **Freshness:** cấu hình đang dùng có đúng revision được phát hành không.
- **Correctness:** cấu hình có parse, bind và hoạt động đúng không.

HTTP availability tốt không chứng minh config freshness hoặc correctness tốt.

## 12. Kết hợp log có cấu trúc với metric

Metric cho biết xu hướng và mức độ. Log giúp tìm một operation cụ thể.

Một log event hữu ích có thể có:

~~~json
{
  "event": "config.fetch.completed",
  "application": "orders-service",
  "profile": "prod",
  "trigger": "startup",
  "outcome": "success",
  "duration_ms": 184,
  "attempt": 1,
  "config_revision": "release-2026.11.20",
  "config_server_instance": "config-server-2",
  "correlation_id": "9b1f..."
}
~~~

Đây là ví dụ minh họa. Chỉ ghi metadata cần thiết để điều tra:

- Application và profile.
- Trigger và outcome.
- Duration và attempt number.
- Revision/label đã được chấp nhận.
- Config Server instance hoặc backend.
- Correlation ID/trace ID.
- Error category và HTTP status nếu có.

Không ghi plaintext secret, token, password, toàn bộ Environment, raw response body hoặc ciphertext nhạy cảm. Không dùng exception message nguyên văn nếu nó có thể chứa URL có credential hoặc property value.

Một event có thể ghi <code>config.fetch.started</code>, <code>config.fetch.retrying</code> và <code>config.fetch.completed</code>. Nhờ đó, người vận hành thấy được thời gian giữa các attempt và nguyên nhân cuối cùng.

## 13. Distributed tracing cho request lấy cấu hình

Tracing giúp nối request từ Config Client tới Config Server và các HTTP dependency nếu các thành phần được instrument và truyền trace context.

Một trace có thể gồm:

~~~text
orders-service
  └── config.fetch
       └── HTTP GET Config Server
            └── Config Server request
                 └── EnvironmentRepository lookup
                      └── Git operation (nếu được instrument)
~~~

Các span nên có thuộc tính có cardinality và độ nhạy phù hợp:

- <code>service.name</code>
- <code>config.trigger</code>
- <code>config.application</code>
- <code>config.profile</code>
- <code>config.outcome</code>
- <code>http.response.status_code</code>
- <code>config.backend</code>

Không gắn token, secret, giá trị property, toàn bộ response hoặc raw query string vào span. <code>label</code> hoặc commit hash có thể hữu ích trong log, nhưng cân nhắc cardinality trước khi đưa vào trace attribute hoặc metric tag.

Trace propagation qua HTTP có thể tự hoạt động khi Micrometer Tracing/OpenTelemetry instrumentation được cấu hình. Git operation hoặc thư viện không phát HTTP có thể cần span tùy chỉnh. Không giả định trace từ Config Client tự động đi xuyên qua mọi thao tác Git backend.

## 14. Quan sát refresh và Spring Cloud Bus

Một refresh workflow có nhiều mốc:

1. Operator hoặc automation gửi refresh request.
2. Client nhận request hoặc Bus event.
3. Client fetch lại Environment.
4. Property source được cập nhật.
5. Bean hỗ trợ refresh được rebind hoặc tạo lại.
6. Readiness và business metrics xác nhận ứng dụng ổn định.

Nên có metric riêng cho refresh event và fetch:

| Chỉ số | Ý nghĩa |
|---|---|
| <code>config.client.refresh.events</code> | Số event refresh nhận được |
| <code>config.client.refresh.failures</code> | Số refresh operation lỗi |
| <code>config.client.fetch</code> với <code>trigger=refresh</code> | Thời gian fetch sau refresh |
| <code>config.client.fetch</code> với <code>trigger=bus</code> | Fetch được kích hoạt từ Bus |
| <code>config.client.refresh.duration</code> | Thời gian toàn bộ refresh workflow nếu được instrument |

Bus event được gửi thành công không có nghĩa mọi client đã hoàn tất refresh. Đếm event ở publisher và đếm kết quả ở từng client. Với fan-out, số lần client fetch có thể lớn hơn số lần publisher gửi event.

Nếu không có acknowledgement tập trung, dashboard cần hiển thị kết quả theo instance hoặc service. Không báo rollout hoàn tất chỉ dựa trên HTTP 200 của endpoint <code>/actuator/busrefresh</code>.

## 15. Cardinality và bảo vệ dữ liệu cấu hình

Mỗi tổ hợp tag tạo một time series. Nếu tag chứa giá trị gần như duy nhất, Prometheus có thể tạo số lượng series rất lớn, làm tăng bộ nhớ, chi phí lưu trữ và thời gian query.

Ví dụ không nên dùng làm tag:

~~~text
config.label = 8f9a2d... (commit SHA thay đổi mỗi release)
config.key = customer.12345.api-token
config.url = https://config.internal/app/profile/unique-label
config.exception = full exception message
config.trace_id = ...
~~~

Thay vào đó, dùng tag hữu hạn:

~~~text
application = orders-service
trigger = startup | refresh | bus
outcome = success | error
error_type = timeout | network | http | parse | decrypt | bind | other
backend = git | vault | consul
~~~

Các chi tiết có độ phân giải cao để trong log/trace đã được kiểm soát quyền truy cập. Metrics endpoint cũng là một nguồn thông tin vận hành; bảo vệ nó để người ngoài không thể suy ra tên service, topology hoặc hoạt động nội bộ.

## 16. Quy trình điều tra: Config Client fetch chậm

Giả sử p95 fetch tăng từ 200 ms lên 4 giây và startup của orders-service bắt đầu timeout.

Đi theo trình tự:

1. **Xác định phạm vi:** mọi application hay chỉ orders-service? Tất cả Config Server replica hay một node?
2. **Kiểm tra client latency:** <code>config.client.fetch</code> và <code>http.client.requests</code> có tăng không?
3. **Kiểm tra request rate:** có retry hoặc refresh event tăng đột biến không?
4. **Kiểm tra server latency:** <code>http.server.requests</code> có tăng cùng thời điểm không?
5. **Kiểm tra repository:** Git fetch/clone hoặc backend lookup có chậm không?
6. **Kiểm tra status:** có 401/403, 404, 5xx hoặc timeout?
7. **Mở trace:** request chậm ở network, Config Server, repository hay response processing?
8. **Đối chiếu log:** application/profile/label/revision, retry attempt và Config Server instance.
9. **Kiểm tra tải:** CPU, heap, thread pool, connection pool và network.
10. **Khắc phục và xác minh:** xử lý đúng tầng, sau đó xác nhận latency và error ratio trở về SLO.

Nếu client latency cao nhưng server request latency thấp, vấn đề có thể nằm ở DNS, TLS handshake, load balancer, network hoặc client processing. Nếu server latency tăng cùng Git fetch latency, backend repository có thể là nút thắt. Nếu HTTP 200 nhưng client báo lỗi, kiểm tra parse/decrypt/bind.

## 17. Ví dụ cấu hình và vận hành end-to-end

Một Config Server có Actuator và Prometheus registry:

~~~yaml
management:
  server:
    port: 9001
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: config-server
    distribution:
      percentiles-histogram:
        http.server.requests: true
~~~

Một Config Client có thể bật tag ứng dụng tương tự:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: ${spring.application.name}
    distribution:
      percentiles-histogram:
        http.client.requests: true
        config.client.fetch: true
~~~

Khi đưa vào production:

1. Thêm Micrometer Prometheus registry vào đúng ứng dụng.
2. Expose metrics endpoint trên mạng quản trị riêng.
3. Cấu hình Prometheus scrape Config Server và các client.
4. Tạo metric riêng cho logical fetch, attempts và refresh nếu metric HTTP chưa đủ.
5. Gắn tag hữu hạn cho application, trigger, outcome và error type.
6. Tạo dashboard latency, request count, error ratio và repository latency.
7. Tạo alert theo SLO và startup budget.
8. Thử tình huống timeout, HTTP 401/403, repository chậm và YAML parse lỗi.
9. Xác nhận log/trace không chứa secret hoặc toàn bộ Environment.
10. Diễn tập điều tra từ dashboard tới trace và log.

## 18. Checklist đo lường cấu hình

- [ ] Đã xác định ranh giới đo ở client, server và repository.
- [ ] Phân biệt logical fetch, HTTP attempt, refresh event và property access.
- [ ] Đã kiểm tra <code>http.server.requests</code> ở Config Server.
- [ ] Đã xác minh HTTP client instrumentation trước khi dùng <code>http.client.requests</code>.
- [ ] Có Timer cho fetch duration và count.
- [ ] Có Counter cho lỗi và refresh failure.
- [ ] Đo riêng parse, decrypt, bind hoặc repository operation khi cần.
- [ ] Histogram được bật cho metric cần tính p95/p99.
- [ ] Prometheus scrape endpoint nằm trong mạng được bảo vệ.
- [ ] Dashboard hiển thị request rate, latency, error ratio, retry và config age.
- [ ] Alert phân biệt startup, refresh và Bus-triggered fetch.
- [ ] Log có application/profile/revision/correlation ID nhưng không chứa secret.
- [ ] Trace nối client/server/backend khi instrumentation hỗ trợ.
- [ ] Không dùng raw URL, property key, token, exception message hoặc trace ID làm metric tag.
- [ ] Đã kiểm thử lỗi network, timeout, 4xx/5xx, repository, parse, decrypt và bind.
- [ ] Đã kiểm tra metric và dashboard với retry, refresh storm và nhiều replica.

Để quan sát Spring Cloud Config hiệu quả, hãy đo ở cả client, server và repository. Metric HTTP cho biết request đã tới server và mất bao lâu; metric fetch riêng cho biết một lần lấy cấu hình logic có thành công không; log và trace giúp xác định nguyên nhân nằm ở network, backend hay xử lý phía client. Đếm đúng fetch và retry, theo dõi latency/error ratio, giới hạn cardinality và không ghi secret vào telemetry sẽ giúp vận hành phát hiện sớm sự cố mà vẫn bảo vệ dữ liệu cấu hình.

