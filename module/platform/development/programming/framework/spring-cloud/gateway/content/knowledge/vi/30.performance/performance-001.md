# Đo thông lượng và các phân vị độ trễ qua từng chặng trong Spring Cloud Gateway

Một API Gateway có thể nhận **2.000 request/giây** và vẫn làm người dùng khó chịu nếu 1% request mất nhiều giây. Ngược lại, độ trễ trung bình 30 ms không chứng minh hệ thống có thể chịu thêm tải: hàng chờ kết nối, event loop bị chặn hoặc downstream quá tải có thể khiến **P99 tăng đột biến** ngay trước khi thông lượng bắt đầu giảm.

Bài thuộc chương **Hiệu năng** của **SPRING_CLOUD_GATEWAY**, tập trung vào một năng lực đo lường cụ thể: **đo thông lượng và các phân vị độ trễ qua từng chặng**. Ta sẽ phân biệt thời gian nhìn từ client, ingress, Gateway và backend; thiết lập Micrometer/Prometheus cùng distributed tracing; viết PromQL tính RPS/P50/P95/P99; chạy benchmark có kiểm soát; tìm nguyên nhân khi route predicate, filter chain, biến đổi path/header, service discovery, xác thực, rate limiting, circuit breaker, retry hoặc TLS làm đường đi của request chậm hơn.

Đến cuối bài, bạn có thể trả lời bằng số liệu, không bằng phỏng đoán:

1. Ở một mức tải cụ thể, **bao nhiêu requests thực sự hoàn thành mỗi giây** và bao nhiêu thất bại/bị từ chối?
2. Độ trễ **P50, P95, P99, P99.9** là gì; chúng đang đo **TTFB hay toàn bộ response**?
3. Thời gian tăng nằm ở client/ingress, Security, Gateway filters, queue/connection acquire, DNS/TLS, downstream xử lý hay download về client?
4. Retry, circuit breaker, fallback và cache làm **số lần gọi backend** khác **số request người dùng** như thế nào?
5. Một tối ưu có cải thiện **tail latency dưới cùng mức traffic và error rate** hay chỉ làm tăng throughput nhờ bỏ qua request?

> **Phạm vi:** Minh họa chính dùng **Spring Cloud Gateway Server WebFlux**, Reactor Netty, Spring Boot Actuator, Micrometer và Prometheus. **Gateway Server Web MVC** có Servlet thread model, handler/filter APIs và instrumentation khác: không tự áp chỉ số Netty hay `GlobalFilter` WebFlux vào MVC. Tên starter, namespace cấu hình, tên meter, labels và các điểm đo cụ thể thay đổi theo release train. Hãy xem dữ liệu được ứng dụng **thực sự export** trước khi kết luận. Các giá trị/ngưỡng số trong bài là ví dụ học thuật, không phải SLO production mặc định.

## 1. Tư duy đầu tiên: đo một giao dịch ở nhiều ranh giới

Một HTTP request đi qua nhiều chặng, mỗi chặng có thể có **thời gian chờ**, **thời gian xử lý** và **thời gian truyền dữ liệu**. Trong Gateway Server WebFlux, đường đi phổ biến:

~~~mermaid
flowchart LR
    C["Client / load generator"] --> E["DNS / TCP / TLS / ingress"]
    E --> G["Gateway HTTP server"]
    G --> S["Spring Security / WebFilters"]
    S --> P["Route predicates / filter chain"]
    P --> Q["HTTP client pool / load balancer / TLS"]
    Q --> B["Backend HTTP server"]
    B --> D["Business logic / DB / cache"]
    D --> B
    B --> Q
    Q --> P
    P --> G
    G --> E
    E --> C
~~~

**Các hộp không tự tạo thành các timer độc lập cộng được ngay.** Một timer Gateway có thể đã bao gồm cả route filters lẫn thời gian chờ backend; một timer backend có thể bao gồm thời gian query DB; một span HTTP client có thể bao gồm kết nối, chuyển request và nhận response. Phải nắm **điểm bắt đầu/điểm kết thúc** và **inclusive/exclusive** của từng phép đo.

### Tách ba lớp quan sát

| Vị trí | Đo được | Không tự biết |
|---|---|---|
| **Client/load generator** | Thời gian người gọi chờ, lỗi mạng, response body, TTFB/total | Gateway đã tiêu bao nhiêu CPU hay backend queue bao lâu |
| **Gateway ingress + route metrics** | Requests được nhận/route, HTTP status, route ID, thời gian xử lý ở ranh giới đo | Cần tracing/client metrics để phân rã downstream phase |
| **Downstream HTTP client + backend** | Connection/pool/HTTP attempts, backend server duration, DB/cache spans | Không thể suy trải nghiệm client nếu thiếu ingress/network |

Một request bị WAF chặn **không đến Gateway**. Request bị Spring Security từ chối trước route selection có thể hiện trong inbound HTTP server metric nhưng không có trong Gateway route metric. Đây là lý do phải định nghĩa **mẫu số** trước khi so sánh RPS và error ratio.

## 2. Định nghĩa chính xác thông lượng và các loại RPS

**Thông lượng** (throughput) là lượng công việc **thực sự hoàn tất** trong một đơn vị thời gian. Với HTTP Gateway, người ta thường dùng **requests/second (RPS)**, nhưng có nhiều cách đếm.

\[
\text{Completed RPS} = \frac{\text{số request hoàn tất trong cửa sổ đo}}{\text{độ dài cửa sổ tính bằng giây}}
\]

| Chỉ số | Điều gì được đếm? | Dùng để trả lời |
|---|---|---|
| **Offered RPS** | Tốc độ client/load generator cố gắng phát request | Hệ thống được đặt dưới tải bao nhiêu? |
| **Accepted RPS** | Requests đi vào ingress/Gateway theo điểm đo | Có request bị chặn trước ứng dụng không? |
| **Gateway routed RPS** | Requests đã match route và được Gateway meter ghi | Route nào nhận traffic? |
| **Completed RPS** | Requests nhận terminal HTTP response hoặc kết thúc thành công theo định nghĩa test | Bao nhiêu công việc được hoàn tất? |
| **Successful RPS** | Các response hợp lệ theo tiêu chí thành công (ví dụ 2xx + body đúng) | Hệ thống đang cung cấp giá trị thật bao nhiêu? |
| **Rejected RPS** | 401/403/429/413... bị từ chối theo policy | Thông lượng có bị đẩy xuống bởi auth/quota không? |
| **Downstream attempts/s** | Tổng số outbound HTTP attempts | Retry/fan-out có nhân tải backend không? |
| **Byte throughput** | Bytes/s upload hoặc download ở một ranh giới | Mạng/streaming có bão hòa không? |

**Một hệ thống trả nhanh 429 cho 80% request không được coi là nhanh/khỏe chỉ vì completed RPS và latency trung bình rất đẹp.** Luôn xem song song **thành công, lỗi, từ chối và request phát thực tế**.

### Ví dụ tính

Trong 60 giây lab:

- Client cố phát 12.000 requests: offered = **200 RPS**.
- Gateway hoàn thành 11.700: completed = **195 RPS**.
- Trong đó 11.100 đúng hợp đồng, 400 là 429 và 200 là 5xx.
- Successful throughput = **185 RPS**; 429 = **6,67 RPS**; 5xx = **3,33 RPS**.

**Không lấy 195 RPS làm “công suất thành công”**, vì 600 request không đem lại kết quả nghiệp vụ mong đợi.

## 3. Concurrency, arrival rate và Little's Law

Thông lượng tăng không có nghĩa latency sẽ giữ nguyên. Khi mỗi request giữ kết nối lâu hơn, số requests đang xử lý đồng thời tăng.

Một phiên bản thường dùng của **Little's Law** ở trạng thái ổn định:

\[
L = \lambda W
\]

Trong đó:

- `L` là **số giao dịch trung bình đang ở trong hệ thống**;
- `\lambda` là **tốc độ hoàn tất/đến trung bình** trong trạng thái ổn định (requests/s);
- `W` là **thời gian trung bình một giao dịch ở trong hệ thống** (giây).

Ví dụ ở **200 RPS**, thời gian xử lý trung bình **250 ms** (0,25 giây), mức đồng thời trung bình tương ứng khoảng:

\[
L = 200 \times 0.25 = 50\ \text{request in-flight}
\]

Nếu khi tải tăng, `W` tăng lên 1 giây trong khi RPS giữ 200, số request in-flight trung bình có thể thành **200**. Điều này tạo áp lực lên connection pool, heap/direct memory, queues và backend.

**Không dùng Little's Law như công thức dự đoán tuyệt đối ở thời gian ngắn, khi traffic thay đổi mạnh hoặc requests đang bị drop/time out.** Nó áp dụng tốt nhất cho hệ thống đã đạt trạng thái tương đối ổn định, với cùng ranh giới đo và định nghĩa completion.

### Open-loop và closed-loop load

- **Closed-loop:** Mỗi virtual user chờ response xong mới phát request kế tiếp. Khi backend chậm, offered RPS tự giảm; nếu nhìn riêng p95, bạn có thể tưởng hệ thống chịu tải tốt.
- **Open-loop / arrival-rate:** Load generator cố giữ tốc độ đến đã chọn, dù response chậm, trong giới hạn công cụ. Dễ nhìn thấy queue growth/saturation hơn nếu đã cấp đủ tài nguyên phát tải.
- **Bài test cần cả hai:** closed-loop gần mô phỏng user think time; arrival-rate cho phép khảo sát một mức offered load cố định.

**Luôn công bố offered rate và achieved rate**; không chỉ ghi “200 users” vì 200 users không có nghĩa 200 requests/s.

## 4. Độ trễ ở client: TTFB khác tổng thời gian

Client có thể đo nhiều mốc:

| Metric | Khoảng thời gian | Thích hợp cho |
|---|---|---|
| DNS lookup | Tra cứu tên miền nếu không dùng cache | Chẩn đoán DNS |
| TCP connect | Thiết lập kết nối TCP mới | Network/connect latency |
| TLS handshake | Thiết lập TLS nếu cần kết nối mới | Certificate/SNI/crypto cost |
| **TTFB** (*time to first byte*) | Từ lúc bắt đầu request đến byte đầu response theo client/tool | Độ trễ phản hồi ban đầu |
| **TTLB / total time** | Từ lúc bắt đầu đến khi nhận xong response | Trải nghiệm download hoàn chỉnh |
| Download duration | Sau byte đầu đến byte cuối, nếu đo được | Network, proxy buffering, client bandwidth |
| End-to-end transaction | Có thể bao gồm redirect, nhiều requests hoặc workflow | Trải nghiệm nghiệp vụ, không chỉ một HTTP call |

**TTFB và total time gần nhau với JSON 1 KB nhưng có thể khác hàng phút với file 2 GiB, SSE hoặc streaming.** Không dùng cùng một latency SLO cho JSON response ngắn và một stream cố ý kéo dài.

### Dùng curl xem các mốc client

~~~bash
curl -sS -o /dev/null \
  -w 'dns=%{time_namelookup}s connect=%{time_connect}s tls=%{time_appconnect}s pretransfer=%{time_pretransfer}s ttfb=%{time_starttransfer}s total=%{time_total}s code=%{http_code}\n' \
  'http://localhost:8080/api/catalog/items/42'
~~~

Các trường `time_*` của cURL thường là **mốc tích lũy tính từ đầu transfer**, không phải từng segment độc lập. Ví dụ, để ước lượng phần từ khi kết nối xong đến byte đầu, phải trừ hai mốc phù hợp, **không cộng tất cả các mốc DNS/connect/TLS/TTFB/total**.

Với `http://` không dùng TLS, `time_appconnect` thường không có ý nghĩa hoặc bằng 0. Với connection reuse, HTTP/2 multiplexing hoặc cache DNS, các trường kết nối có thể khác request đầu tiên. **Một lệnh curl đơn lẻ không phải benchmark P99.**

## 5. P50, P95, P99 đo điều gì?

Cho một tập `N` phép đo latency hoàn tất và được sắp tăng dần. Một **phân vị p** mô tả mức latency mà khoảng **p% observations** ở dưới hoặc bằng theo thuật toán quantile được chọn.

| Phân vị | Cách đọc thực dụng | Khi dùng |
|---|---|---|
| **P50** (median) | Khoảng một nửa request nhanh hơn, một nửa chậm hơn | Trải nghiệm điển hình |
| **P90** | Khoảng 90% observations ở dưới mức này | Chậm nhưng phổ biến |
| **P95** | Khoảng 5% requests chậm hơn | Mức tail quan trọng cho API |
| **P99** | Khoảng 1% requests chậm hơn | Sự cố tail nhỏ nhưng đáng kể |
| **P99.9** | Khoảng 0,1% requests chậm hơn | Quy mô lớn, cần nhiều samples |

Ví dụ giả định có **10.000 requests** và P99 = **800 ms**: khoảng 100 observations thuộc nhóm chậm nhất có thể vượt vùng 800 ms, tùy phương pháp quantile và phân bố. **Không giải thích P99 là “request mất 99% thời gian ở 800 ms”.**

### Tại sao trung bình có thể đánh lừa?

Một route có 99 request mất 20 ms và 1 request mất 5.000 ms:

\[
\overline{T} = \frac{99\times20 + 1\times5000}{100}=69.8\ \text{ms}
\]

Trung bình khoảng **69,8 ms**, nhưng 1% người dùng phải chờ tới **5 giây**. Nếu tăng retry trong Gateway, trung bình có thể cải thiện khi lỗi được cứu nhưng **P99 tệ đi** do một số requests chờ thêm backoff.

### Phân vị cần ngữ cảnh

Luôn ghi kèm:

- Số samples trong cửa sổ;
- Tỷ lệ request thành công/lỗi;
- Endpoint/route, phương thức HTTP và kích thước payload;
- Khoảng thời gian đo (`1m`, `5m`, `1h`);
- Source đo (client, Gateway, backend) và boundary;
- Algorithm: exact quantile từ raw samples, histogram bucket estimate hay summary percentile.

**P99 với 30 requests/5 phút thường không đủ ổn định để ra quyết định tối ưu production.** Khi số lượng samples thấp, xem count và xu hướng trong cửa sổ dài hơn.

## 6. Không cộng hoặc lấy trung bình các phân vị qua từng chặng

Một sai lầm nghiêm trọng là:

~~~text
P99(client→Gateway) = 30 ms
P99(Gateway)        = 200 ms
P99(backend)        = 300 ms

KHÔNG được kết luận:
P99(end-to-end) = 30 + 200 + 300 = 530 ms
~~~

Các P99 có thể đến từ **những requests khác nhau**. Hơn nữa, timer Gateway có thể đã **bao gồm** backend nên phép cộng đếm trùng. Tương tự, P99 của hai Gateway instances không thể được cộng/trung bình để tìm P99 toàn cluster.

### Cách đúng để phân rã

1. Chọn **cùng một request/trace**.
2. Đo các mốc bắt đầu/kết thúc trong **một timeline** và nhận diện spans inclusive/exclusive.
3. Xác định segment nào nối tiếp và segment nào chồng lấn.
4. Nếu cần P99 end-to-end, tính từ **toàn bộ observations end-to-end** hoặc histogram tổng hợp cùng loại/đơn vị.
5. Nếu cần “P99 thời gian chờ pool”, đo một timer **pool acquire** riêng trên các attempts thực sự acquire, không lấy chênh lệch hai percentiles.

### Ví dụ timeline cho *một* request

~~~mermaid
gantt
    title Mốc thời gian minh họa của một HTTP request duy nhất
    dateFormat x
    axisFormat %L
    section Client
    Toàn bộ request :a, 0, 270
    section Gateway
    HTTP server span :b, 12, 240
    section Outbound
    Client HTTP attempt span :c, 38, 204
    section Backend
    HTTP server span :d, 60, 190
~~~

Các span trên **chồng lấn có chủ đích**. Từ một span Gateway 228 ms và outbound 166 ms, chỉ khi biết boundaries/clock accuracy và cấu trúc xử lý ta mới có thể ước lượng thời gian ngoài outbound. Đây **không phải dữ liệu P95/P99**.

> **Quy tắc:** Tính percentiles từ **raw observations hoặc cùng family histogram buckets**. Dùng **traces** để biết chặng chậm trên *một request*, dùng **metrics** để biết phân bố chậm trên *nhiều requests*.

## 7. Chia các chặng đo trong Gateway Server WebFlux

Một cách đặt ranh giới đủ thực dụng:

| Chặng / điểm đo | Bắt đầu → kết thúc | Công cụ phù hợp | Cạm bẫy |
|---|---|---|---|
| Client → ingress | Bắt đầu request → ingress nhận | Load generator + ingress metrics | Không đồng bộ clock gây sai phép trừ |
| Ingress | Nhận request → chuyển đến Gateway | Reverse proxy access timings/traces | Ingress có thể buffer body |
| Gateway HTTP server | Nhận vào → phát response hoàn tất theo server instrumentation | `http.server.requests`/server observations | Có thể bao gồm handler khác không phải Gateway route |
| Security/WebFilters | Entry → security decision | Tracing/low-cardinality custom timing | Có thể chặn trước route metrics |
| Route matching | Trước chọn route → route đã chọn | Custom instrumentation/trace nếu cần | Không mặc định Gateway có timer riêng cho matcher |
| Gateway filter chain | Từ wrapper trước `chain.filter` đến terminal signal | Custom `GlobalFilter` timer | Inclusive: có thể bao gồm outbound |
| HTTP client acquire | Lấy kết nối từ pool | Reactor Netty/client pool metrics | Không giống TCP connect khi pool reuse |
| DNS / connect / TLS | Tạo connection mới | Client/Netty metrics & spans | Không phát sinh ở connection reuse |
| Backend request | Backend nhận → response theo timer | `http.server.requests` backend | Có thể bao gồm DB/cache |
| Response đến client | Backend bytes → client bytes cuối | Client total, ingress, Netty traces | Streaming/backpressure ảnh hưởng lớn |

**Không khẳng định mọi chặng đều có sẵn một meter trong Gateway.** Spring Boot, Reactor Netty, HTTP client, load balancer và Micrometer Observation có thể bật các telemetry khác nhau theo phiên bản; các phase phức tạp như predicate evaluation có thể cần instrumentation riêng nếu mục tiêu tối ưu thực sự đòi hỏi.

## 8. Tách latency của request và latency của HTTP attempt

Một request client có thể có các nhánh:

~~~mermaid
flowchart TD
    C["1 incoming request"] --> G["Security + route/filter"]
    G --> L{"RateLimiter?"}
    L -->|429| RL["Kết thúc 429, 0 outbound attempts"]
    L -->|Cho phép| A1["Outbound attempt #1"]
    A1 --> R{"Kết quả?"}
    R -->|503 và được retry| W["Backoff"]
    W --> A2["Outbound attempt #2"]
    A2 --> OK["200 → client"]
    R -->|200| OK
    R -->|Circuit open/fallback| FB["Fallback response"]
~~~

- **Incoming count:** một client request.
- **Routed count:** thường một phép đo ở Gateway route nếu đi qua điểm instrument, nhưng phải kiểm phiên bản.
- **Outbound attempts:** 0, 1, 2 hoặc nhiều hơn.
- **User-perceived latency:** có thể bao gồm retry/backoff và response transfer.
- **Backend server duration:** được backend đo **cho từng attempt**; hai backend attempts có thể thuộc cùng một user request.

### Retry amplification

Một chỉ số đáng theo dõi:

\[
A = \frac{\text{outbound attempts/s}}{\text{incoming routed requests/s}}
\]

Với route bình thường **một request → một outbound call**, `A` gần 1. Khi retries nhiều, `A` tăng. Nhưng với route aggregation/fan-out có chủ đích, `A` có thể lớn hơn 1 ngay cả khi khỏe. Vì vậy **gắn policy và ý nghĩa theo route**, không alert một ngưỡng chung cho mọi loại API.

**HTTP 503 từ backend không tự đồng nghĩa Reactor phát `onError`.** Một HTTP client có thể nhận response có status 503 như kết quả bình thường; Gateway Retry filter hoặc client policy mới quyết định có attempt tiếp theo không.

## 9. Actuator, Micrometer và Prometheus: chuẩn bị dữ liệu đo

Trước tiên cần một nguồn metrics cho Gateway.

Ví dụ dependency Gradle dành cho ứng dụng Gateway Server WebFlux có **Spring Boot/Cloud BOM tương thích**:

~~~groovy
dependencies {
    // Tên starter có thể khác giữa các release train.
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'

    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Một cấu hình **lab** với ứng dụng cổng 8080, quản lý cổng 9091:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9091
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: gateway-edge
      environment: lab
~~~

**Bảo mật:** Tách cổng không đồng nghĩa private. Trong production, endpoint `/actuator/prometheus` phải được giới hạn bằng network ACL/ServiceMonitor permissions, authentication/TLS phù hợp và không expose Actuator nhạy cảm ra Internet. `metrics` endpoint hữu ích ở lab nhưng không nhất thiết cho phép mọi người xem trong production.

### Khám phá những meter thật sự hiện diện

~~~bash
curl -sS 'http://127.0.0.1:9091/actuator/metrics'
curl -sS 'http://127.0.0.1:9091/actuator/metrics/spring.cloud.gateway.requests'
curl -sS 'http://127.0.0.1:9091/actuator/prometheus' \
  | grep -E '^(spring_cloud_gateway_requests|http_server_requests)'
~~~

Trong những dòng Gateway Server WebFlux có **Gateway Metrics Filter**, một timer thường gặp là `spring.cloud.gateway.requests`, được Prometheus xuất thành các series dạng `spring_cloud_gateway_requests_seconds_count` và `..._sum`. Labels thường gồm `routeId`, `routeUri`, `outcome`, `status`, `httpStatusCode`, `httpMethod`; tag path có thể tùy chọn.

**Đừng chép query rồi khẳng định tên metric/label luôn đúng.** Registry naming convention, release train và cách bật filter thay đổi; xác minh `/actuator/metrics` và raw `/actuator/prometheus` của chính runtime. Một số metrics chỉ xuất hiện sau request đầu tiên được instrument.

### HTTP server meter khác Gateway route meter

- `http.server.requests` thường đo requests ở web server/application HTTP layer.
- `spring.cloud.gateway.requests` thường đo kết quả ở **Gateway route instrumentation point**.
- Một request trả 401 trước khi route match có thể **không** làm tăng Gateway route count.
- Một request vào `/actuator/health` có thể được đo bởi management web server riêng, **không** phải route Gateway.
- Requests bị ingress/WAF chặn không thể xuất hiện trong in-process Gateway meter.

Không dùng hai meters này thay nhau nếu muốn tính **thành công hay từ chối trước routing**.

## 10. Bật histogram để có P95/P99 tổng hợp được

Timer `spring.cloud.gateway.requests` có thể xuất count/sum mà **không có histogram buckets**. Từ count + sum chỉ tính được **trung bình**, không suy đúng P95/P99.

Ví dụ cấu hình Spring Boot Micrometer distribution cho **một timer cụ thể**:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        "[spring.cloud.gateway.requests]": true
~~~

Dấu ngoặc vuông ở map key được dùng để giữ nguyên meter name có dấu chấm khi Spring Boot binder xử lý các thuộc tính map; hãy xác minh cấu hình có hiệu lực ở bản bạn sử dụng.

Kiểm raw exposition:

~~~bash
curl -sS 'http://127.0.0.1:9091/actuator/prometheus' \
  | grep '^spring_cloud_gateway_requests_seconds_bucket'
~~~

Nếu không có `_bucket`, kiểm:

1. Timer đã từng được sử dụng chưa?
2. Có đúng tên meter/namespace không?
3. Distribution histogram đã bật trước khi meter được đăng ký chưa?
4. Registry/Prometheus exporter có phát buckets không?
5. App đang dùng Gateway Server WebFlux hay một variant khác?

### Timer metrics và đơn vị

| Series Prometheus ví dụ | Ý nghĩa | Đơn vị |
|---|---|---|
| `..._seconds_count` | Số measurements | Lượt |
| `..._seconds_sum` | Tổng thời gian | Giây |
| `..._seconds_bucket{le="0.25"}` | Số measurements ≤ 250 ms trong bucket tích lũy | Lượt |
| `..._seconds_max` nếu được export | Time-window max tùy meter | Giây, **không phải P99** |

Buckets có thể có nhiều giá trị `le` khác nhau; các ví dụ sau **không giả định** phải tồn tại bucket `0.25` trừ khi nói rõ.

**Histogram làm tăng số time series theo số tổ hợp labels × buckets.** Không bật histogram đại trà cho tất cả routes/URIs/path có cardinality vô hạn.

## 11. Prometheus scrape toàn bộ Gateway instances

Ví dụ config Prometheus dành cho **môi trường lab trên cùng host/network namespace**:

~~~yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: gateway-edge
    metrics_path: /actuator/prometheus
    scheme: http
    scrape_timeout: 5s
    static_configs:
      - targets:
          - '127.0.0.1:9091'
        labels:
          environment: lab
~~~

Nếu Gateway chạy trong Docker/Kubernetes, `127.0.0.1` của Prometheus là **chính container Prometheus**. Hãy dùng DNS/service discovery phù hợp để scrape **từng Gateway instance**, không chỉ một load-balanced Service mà có thể đổi pod ở mỗi lần scrape và làm counters khó tổng hợp.

### Luôn bắt đầu bằng kiểm tra scrape

~~~promql
up{job="gateway-edge"}
~~~

- `up=1`: target được scrape thành công ở lần gần nhất.
- `up=0`: target hiện diện nhưng scrape thất bại.
- Không có `up` series: target có thể chưa được discovery hoặc bị loại khỏi scrape; **không đồng nghĩa khỏe**.

Một dashboard hiệu năng không có panel `up` rất dễ nhầm **mất dữ liệu** thành **RPS bằng 0 hoặc không có lỗi**.

## 12. PromQL: đo RPS và throughput theo route

Các truy vấn dưới đây giả định runtime thật có:

~~~text
spring_cloud_gateway_requests_seconds_count{
  job="gateway-edge",
  routeId="catalog-read",
  httpStatusCode="200"
}
~~~

Hãy đổi tên metric và labels nếu exposition trong môi trường bạn khác ví dụ.

### Tổng Gateway routed RPS

~~~promql
sum(
  rate(spring_cloud_gateway_requests_seconds_count{
    job="gateway-edge"
  }[5m])
)
~~~

`rate(counter[5m])` ước lượng tốc độ tăng trên mỗi giây và xử lý counter resets (ví dụ restart) tốt hơn phép trừ raw counter.

### RPS theo route ID

~~~promql
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_count{
    job="gateway-edge"
  }[5m])
)
~~~

### RPS theo method và route

~~~promql
sum by (routeId, httpMethod) (
  rate(spring_cloud_gateway_requests_seconds_count{
    job="gateway-edge"
  }[5m])
)
~~~

### Số requests ước lượng trong một giờ

~~~promql
sum by (routeId) (
  increase(spring_cloud_gateway_requests_seconds_count{
    job="gateway-edge"
  }[1h])
)
~~~

`increase` có thể đưa ra kết quả không nguyên do nội suy theo cửa sổ, không phải log sự kiện chính xác đến từng request.

### Tách 2xx, 4xx và 5xx

~~~promql
sum by (routeId, httpStatusCode) (
  rate(spring_cloud_gateway_requests_seconds_count{
    job="gateway-edge",
    httpStatusCode=~"[245].."
  }[5m])
)
~~~

Nếu muốn **successful RPS theo nghiệp vụ**, đừng coi mọi 2xx đều “thành công”: một fallback có thể trả HTTP 200 nhưng dữ liệu stale, một API có thể trả 202 mà công việc chưa hoàn thành. Instrument thêm business outcome khi cần, với labels hữu hạn.

## 13. PromQL: độ trễ trung bình, P50, P95 và P99

### Average route latency

~~~promql
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_sum{
    job="gateway-edge"
  }[5m])
)
/
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_count{
    job="gateway-edge"
  }[5m])
)
~~~

Kết quả có đơn vị **giây**. Không đồng nhất đây với TTFB client hoặc backend processing time.

### P50 của từng route

~~~promql
histogram_quantile(
  0.50,
  sum by (le, routeId) (
    rate(spring_cloud_gateway_requests_seconds_bucket{
      job="gateway-edge"
    }[5m])
  )
)
~~~

### P95 của từng route

~~~promql
histogram_quantile(
  0.95,
  sum by (le, routeId) (
    rate(spring_cloud_gateway_requests_seconds_bucket{
      job="gateway-edge"
    }[5m])
  )
)
~~~

### P99 của từng route

~~~promql
histogram_quantile(
  0.99,
  sum by (le, routeId) (
    rate(spring_cloud_gateway_requests_seconds_bucket{
      job="gateway-edge"
    }[5m])
  )
)
~~~

**Giữ `le` trong `sum by (le, routeId)`.** Với histogram cổ điển của Prometheus, `histogram_quantile` cần giới hạn mỗi bucket. Nếu muốn P99 **toàn cluster**, dùng `sum by (le)`, *miễn là cùng histogram family, đơn vị và bucket layout phù hợp*.

### Tại sao không lấy trung bình P99 của từng node?

Hai nodes có thể nhận số lượng request và phân bố latency khác nhau. Trung bình `P99_A` và `P99_B` **không tạo ra P99 toàn cluster**. Cách đúng là **gộp bucket counts rồi gọi `histogram_quantile`**, không gộp kết quả quantiles.

**Histogram P99 là ước lượng** theo bucket boundaries. Với traffic ít hoặc buckets thưa, nó có thể lệch đáng kể so với exact percentile từ raw observations. Nếu SLO là 250 ms, cần bucket resolution phù hợp quanh mốc đó.

## 14. Đo SLO latency bằng histogram: đôi khi hữu ích hơn P99

P99 giúp nhìn tail latency, nhưng nhiều hệ thống muốn trả lời: **Bao nhiêu phần trăm requests hoàn thành dưới 300 ms?**

Nếu histogram có bucket **`le="0.3"`**, tỷ lệ request ≤ 300 ms theo route:

~~~promql
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_bucket{
    job="gateway-edge", le="0.3"
  }[5m])
)
/
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_count{
    job="gateway-edge"
  }[5m])
)
~~~

Đây là **tỷ lệ từ 0 đến 1**, không phải phần trăm cho đến khi nhân 100. Nếu không có bucket `0.3`, biểu thức sẽ không cho kết quả như mong muốn; **đừng tự tạo nhãn `le="0.3"` trong query** rồi cho rằng Registry đã đo bucket đó. Cần cấu hình histogram/SLO boundaries theo Micrometer phù hợp với phiên bản.

### Latency SLI đúng phải chọn mẫu số

Một request trả 503 trong 5 ms có nên được tính “nhanh” không?

- Với **availability/error SLO**, nó là lỗi.
- Với **latency SLO**, bạn có thể chọn chỉ requests thành công hoặc tất cả attempts, nhưng phải công bố định nghĩa.
- Với **user journey**, cả status và độ trễ có thể cùng quyết định thành công.

Ví dụ một cách định nghĩa: **“99% requests thành công của route catalog-read hoàn thành dưới 300 ms, đo từ Gateway server nhận đến hoàn tất response”**. Bên cạnh đó phải có **error-rate SLO riêng**, tránh hệ thống đạt latency SLO bằng cách trả lỗi rất nhanh.

## 15. So sánh các chặng bằng distributed tracing

Metrics tổng hợp cho bạn biết route nào có P99 cao; **trace của một request chậm** giúp định vị chặng gây trễ. Với Spring Boot/Micrometer Tracing + OpenTelemetry hoặc một hệ tracing tương đương, có thể thu spans:

~~~text
traceId = 77... (minh họa)
└── edge-gateway.server           0 - 270 ms
    ├── authentication                2 - 18 ms (nếu được instrument)
    ├── route-and-filter             18 - 250 ms (có thể bao outbound)
    │   └── http.client/orders       36 - 235 ms
    │       └── orders-service.http  55 - 210 ms
    │           └── database.query   80 - 190 ms
    └── response-write               250 - 270 ms (nếu được instrument)
~~~

**Các spans lồng nhau/chồng lấn**, không cộng tất cả durations. Client span 199 ms có thể bao gồm backend server span 155 ms; database query 110 ms lại nằm trong backend span.

### Chênh lệch nào có ý nghĩa?

Đối với **một trace**, khi time boundaries tương ứng:

- Gateway có thể mất thời gian ở security/route/filter trước outbound.
- HTTP client span kéo dài có thể là queue/pool acquire, DNS, connect, TLS, upload request, backend waiting và download response.
- Backend server span có thể chứa DB/cache calls.
- Chênh lệch giữa client wait và backend server processing có thể do network/pool/serialization, **nhưng không tách chính xác thành từng phần nếu thiếu instrumentation**.

Muốn tìm **P99 của chặng pool acquire**, phải có **metric/histogram cho acquire duration** hoặc đủ dữ liệu spans để thống kê đúng, **không lấy P99(client) trừ P99(backend)**.

### Trace propagation qua Gateway

- Dùng chuẩn propagation phù hợp, thường có `traceparent`/`tracestate`, qua các hệ thống có hỗ trợ.
- Gateway và backend phải đồng ý propagators để cùng trace ID.
- Sampling thường không lưu **mọi request**: một vài trace chậm là manh mối, không phải mô tả phân bố toàn bộ.
- Không đặt JWT, session ID, API key hay raw query nhạy cảm thành span attributes.
- Clock skew và instrumentation overhead cần được kiểm tra nếu cố phân tích các segment rất ngắn.

**Metrics cho phân bố, tracing cho đường đi, logs cho chi tiết lỗi** là ba công cụ bổ sung lẫn nhau.

## 16. Đo thời gian filter chain đúng cách trong WebFlux

Khi cần một phép đo tùy biến, có thể đặt **`GlobalFilter`** bên ngoài một phần Gateway filter chain để lấy thời gian elapsed. Ví dụ sử dụng Micrometer Timer với tags hữu hạn:

~~~java
package example.gateway.performance;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public final class GatewayChainTimingFilter
        implements GlobalFilter, Ordered {

    private final MeterRegistry meterRegistry;

    public GatewayChainTimingFilter(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @Override
    public int getOrder() {
        return -1000; // Vị trí minh họa; verify effective filter ordering.
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            GatewayFilterChain chain) {

        return Mono.defer(() -> {
            long startNanos = System.nanoTime();

            return chain.filter(exchange)
                .doFinally(signal -> {
                    long elapsedNanos = System.nanoTime() - startNanos;
                    meterRegistry.timer(
                        "edge.gateway.wrapped.chain.duration",
                        "terminal", signal.name())
                        .record(elapsedNanos, TimeUnit.NANOSECONDS);
                });
        });
    }
}
~~~

### Hiểu đúng metric custom này

- `Mono.defer(...)` bắt đầu đo lúc **subscription**, không bắt đầu sớm khi filter graph được tạo.
- `doFinally` chạy trên **complete/error/cancel** và ghi elapsed, do đó `terminal` chỉ có một tập giá trị hữu hạn.
- Timer này đo **toàn chuỗi downstream của filter**, có thể bao gồm routing, backend wait, response composition. Nó **không** đo “chi phí CPU riêng của custom filter”.
- `getOrder()=-1000` là ví dụ. GlobalFilter và route-specific filters được sắp theo `Ordered`; không có gì bảo đảm timer bao tất cả các filter nếu có filter khác chạy ngoài nó.
- Các requests bị Spring Security từ chối **trước Gateway filter chain** sẽ không xuất hiện trong timer này.
- Một request bị short-circuit bởi filter ở trong chuỗi có thể hoàn thành mà **không outbound**; không coi timer này là backend latency.
- `doFinally` có thể được gọi sau terminal signal đi downstream; khi test counter/timer, cần đồng bộ phù hợp, không assert race bằng một phép đọc tức thì.

**Không thêm raw URL, principal, IP, JWT hoặc request ID làm label** vào Timer. Nếu cần phân tích route, ưu tiên Gateway route timer có `routeId` chuẩn hóa; custom timer với route IDs động cần policy cardinality.

### Nếu chỉ muốn đo *một* filter

Một filter có:

~~~java
return chain.filter(exchange)
    .doOnSuccess(ignored -> observeSuccess());
~~~

đo từ trước khi gọi `chain.filter(...)` tới sau khi chain hoàn thành sẽ bao gồm **mọi xử lý bên trong chain**, không phải chỉ thời gian của `observeSuccess()` hoặc của filter.

Muốn đo **chi phí tự thân**, cần bao logic hẹp bằng timer khác, hoặc instrument những operation cụ thể (parse token, look up Redis key, transform header) và tính toán đúng với async execution. Không tạo “Gateway overhead = total timer − backend P95”, vì **chênh lệch P95 sai về thống kê**.

## 17. Connection pool, DNS, TLS và load balancing: những chặng thường bị bỏ sót

Một route `lb://orders-service` có thể được quyết định nhanh nhưng outbound call vẫn chậm do:

1. Service Discovery/LoadBalancer chậm cập nhật instance.
2. HTTP connection pool hết kết nối sẵn, request phải chờ acquire.
3. Tạo TCP connection mới tốn thời gian.
4. DNS bị chậm hoặc thất bại.
5. TLS handshake/certificate validation/SNI gặp vấn đề.
6. Backend vừa scale lên nhưng chưa warmed up.
7. Backend nhận request sớm nhưng response chậm vì DB/cache.

### Đo bằng các metrics phù hợp

| Điểm nghi vấn | Loại quan sát cần có | Dấu hiệu điển hình |
|---|---|---|
| Pool acquire | Pending acquire count/duration | RPS có thể chưa giảm, P99 tăng do queue |
| Connect | New connection time/error | Slow connect, network packet loss |
| TLS | Handshake time/failures | P99 tăng ở kết nối mới, certificate issues |
| DNS | Resolution latency/errors | Lỗi spike khi đổi hostname/instance |
| Backend | HTTP server timer + service spans | P95 backend tăng theo load |
| LoadBalancer | Instance distribution, selected service ID | Một instance nóng/lỗi |
| Ingress | Proxy upstream timings | Gateway không phải nút thắt |

Tên Reactor Netty metrics thay đổi theo version và cách bật instrumentation; **không đoán trước tên meter rồi dựng panel trống**. Kiểm `/actuator/metrics` và raw exposition trước. Ở runtime có tracing, hãy kiểm một trace **tái sử dụng connection** và một trace **kết nối mới** để thấy phần connect/TLS khác nhau.

### HTTP keep-alive và HTTP/2

Một benchmark tạo connection mới ở mỗi request sẽ đo rất nhiều TCP/TLS overhead, khác workload browser/mobile/backend dùng keep-alive. HTTP/2 multiplexing có thể thay đổi số connections và queue behavior, nên báo cáo:

- HTTP protocol version;
- Connection reuse policy;
- Số max connections / pending acquire;
- TLS on/off, endpoint/certificate;
- Load balancer và số backend instances;
- Client concurrency.

**Không so P99 của hai môi trường khác TLS/keep-alive/protocol rồi quy kết cho Gateway filter.**

## 18. Đo payload: TTFB và TTLB cho upload, download, SSE, WebSocket

Một endpoint JSON GET nhỏ có thể dùng `request duration` chung. Nhưng một số traffic phải có SLI riêng.

| Traffic | Metric hữu ích | Metric dễ gây hiểu nhầm |
|---|---|---|
| JSON GET nhỏ | RPS, total latency P95/P99, error ratio | Chỉ lấy average |
| POST JSON nhỏ | Total latency, successful RPS, write conflicts | Retry count như user requests |
| Upload file lớn | Bytes/s, time-to-acknowledge, total upload duration, failure/cancel rate | P99 chung với JSON GET |
| Download file lớn | TTFB, TTLB, bytes/s, checksums, incomplete downloads | TTFB làm đại diện toàn download |
| SSE | Time to first event, inter-event gap, reconnects, active streams | Total connection lifetime như latency |
| WebSocket | Handshake duration, message RTT, active connections, frame errors | Thời gian mở socket như P99 HTTP request |
| gRPC streaming | Per-message/stream SLI theo protocol | Request rate HTTP/1.1 mặc định |

**Body filters** như `CacheRequestBody`, `ModifyRequestBody` hoặc `ModifyResponseBody` có thể làm stream bị buffer. Khi đó:

- TTFB có thể tăng dù backend đã phát chunk sớm.
- Heap/direct memory có thể tăng theo body size × concurrency.
- Timer route-level có thể chờ hết stream, trở nên không so sánh trực tiếp với JSON request.
- Retry request body có thể cần buffering hoặc replay và làm tải backend tăng.

Không tự nâng `max-in-memory-size` vô hạn để đạt RPS tốt hơn; ưu tiên streaming pass-through khi gateway không cần đọc toàn body.

## 19. Thiết kế load test tái lập: không chỉ chạy vài lệnh curl

Một bài test hiệu năng nghiêm túc phải định nghĩa **workload**, **môi trường**, **điều kiện hoàn tất** và **cách kiểm tra kết quả**.

### Checklist trước khi chạy

| Thuộc tính | Cần cố định/ghi lại |
|---|---|
| Code & config | Git revision, Gateway/filter configuration, Spring Boot/Cloud BOM |
| Runtime | Java version, container CPU/memory limits, JVM flags |
| Hạ tầng | Gateway/ingress/backend instances, resource requests/limits |
| Protocol | HTTP/1.1 hoặc HTTP/2, TLS, keep-alive, connection pooling |
| Route mix | Tỷ lệ GET/POST, path patterns, authenticated/anonymous |
| Payload | Body/response sizes, gzip, cacheability |
| Backend behavior | CPU/DB delay, error injection, cache hit ratio |
| Arrival pattern | Constant rate, ramp, burst, closed-loop |
| Measurement | Warm-up, steady-state window, scrape frequency |
| Thành công | Response status, schema/checksum, business side effects |
| Stop rules | Error ratio, memory pressure, downstream health, production isolation |

**Chỉ tạo tải trong môi trường được phép và có giới hạn.** Không dùng benchmark để bắn request lớn, retry storms hoặc stress SSL handshake vào production mà chưa có kế hoạch capacity/rollback.

### Warm-up và steady state

Trong JVM, warm-up có thể ảnh hưởng JIT compilation, class loading, connection pools, TLS sessions và cache. Một workflow cơ bản:

1. Deploy Gateway/backend và ghi version.
2. Warm-up với tải nhỏ, đúng request mix.
3. Chạy **baseline** ở một offered rate cố định.
4. Giữ vài phút đủ samples/scrapes để ước lượng P95/P99.
5. Tăng offered rate theo từng bước có kiểm soát.
6. Quan sát throughput, latency, error ratio, concurrency, pool queues và CPU.
7. Dừng khi vượt giới hạn an toàn, ghi lại ngưỡng bão hòa.
8. Lặp test nhiều lần, tránh lấy một lần duy nhất làm chuẩn.

## 20. Ví dụ k6: constant-arrival-rate và phân vị client

Công cụ load generator như **k6** có executor `constant-arrival-rate` để cố gắng duy trì số iteration bắt đầu mỗi giây, thay vì chờ user cũ hoàn tất rồi mới gửi request mới.

Ví dụ **script lab** `gateway-performance.js`:

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const baseUrl = __ENV.GATEWAY_URL || 'http://localhost:8080';
const success = new Rate('catalog_success');

export const options = {
  scenarios: {
    catalog_read: {
      executor: 'constant-arrival-rate',
      rate: 100,
      timeUnit: '1s',
      duration: '3m',
      preAllocatedVUs: 100,
      maxVUs: 300,
      gracefulStop: '30s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    catalog_success: ['rate>0.99'],
  },
};

export default function () {
  const response = http.get(
    baseUrl + '/api/catalog/items/42',
    { tags: { scenario_name: 'catalog_read' } }
  );

  const valid = check(response, {
    'HTTP 200': (r) => r.status === 200,
    'response has item': (r) => r.body.includes('42'),
  });

  success.add(valid);
}
~~~

Các mục tiêu `100 req/s`, `P95 < 500 ms`, `P99 < 1.000 ms`, tỷ lệ lỗi <1% chỉ là **ngưỡng bài lab**, không phải chuẩn chung. Với script này mỗi iteration gửi một HTTP request. Khi sửa script có nhiều requests/iteration, **iteration rate không còn bằng HTTP RPS**.

### Đọc đúng báo cáo k6

| k6 metric thường gặp | Cách đọc |
|---|---|
| `http_reqs` | Số HTTP requests và tốc độ |
| `http_req_duration` | Thời gian gửi + chờ + nhận response theo semantics k6; không đồng nhất toàn bộ DNS/connect/TLS |
| `http_req_waiting` | Phần chờ tới response đầu (gần TTFB ở phạm vi tool) |
| `http_req_connecting` | Thời gian thiết lập TCP connection |
| `http_req_tls_handshaking` | TLS handshake |
| `http_req_blocked` | Thời gian request bị blocked trước khi bắt đầu gửi |
| `http_req_failed` | Tỷ lệ request k6 coi là failed theo expected response policy |
| `dropped_iterations` | Iterations không thể bắt đầu theo lịch |
| `vus` / `vus_max` | Active/available virtual users |

**Phải kiểm `dropped_iterations` và actual `http_reqs`.** Nếu script cố phát 100 req/s nhưng load generator thiếu CPU/VUs và bỏ nhiều iterations, Gateway **chưa chắc đã nhận tải 100 req/s**. Cũng phải kiểm health của máy phát tải, không chỉ CPU của Gateway.

### Không dùng `sleep` sai chỗ

Với `constant-arrival-rate`, không cần `sleep(1)` ở cuối iteration chỉ để tạo 1 RPS/user; điều đó thay thời gian VU cần giữ và có thể làm thiếu VUs. Tham khảo load-model guide của k6 và test throughput thực.

### Cài/chạy trong lab

~~~bash
k6 run -e GATEWAY_URL=http://localhost:8080 gateway-performance.js
~~~

Đây là lệnh để người học thực hành trong môi trường lab, **không được thực thi trong STEP 4**. Nếu dùng token test, đưa vào secret/env theo chính sách; không commit credential vào script hoặc gửi payload có PII thật lên dashboard.

## 21. Phát hiện coordinated omission và load-generator bottleneck

**Coordinated omission** xảy ra khi hệ thống đo chỉ ghi latency của các request được phát, nhưng **không ghi nhận những request lẽ ra phải đến theo lịch mà bị trì hoãn**. Ở closed-loop workload, khi backend chậm, client không phát request kế tiếp nên histogram có thể thiếu những thời gian chờ mà người dùng chịu trong mô hình arrival độc lập.

### Ví dụ

Giả sử hệ thống được kỳ vọng nhận 100 requests/s, nhưng một lần backend stall 5 giây:

- Closed-loop client chỉ đợi request hiện tại, **giảm offered load**;
- Nếu mỗi VU gửi request kế tiếp sau response, ít samples được tạo trong lúc stall;
- Measured P99 có thể thấp hơn điều xảy ra nếu arrivals vẫn tiếp tục.

**Giải pháp không phải dùng một công cụ “thần kỳ”** mà là:

1. Định nghĩa arrival model đúng workload.
2. Dùng constant-arrival-rate khi đánh giá khả năng giữ SLO dưới tốc độ đến cố định.
3. Đo `dropped_iterations`, generator CPU, network throughput và target achieved RPS.
4. Giữ đủ VUs/connections để request được phát đúng thời điểm.
5. Ghi queueing và timeout, bao gồm các requests bị drop/reject theo policy.
6. Nếu dùng HDRHistogram hoặc công cụ có corrected latency, hiểu chính xác giả định và cách hiệu chỉnh.

**Đừng so hai P99 khi một test có dropped load còn test kia đạt offered rate.**

## 22. Thử nhiều mức tải để tìm saturation knee

Một load test nên trả lời: **tại mức offered RPS nào P95/P99 bắt đầu tăng nhanh trong khi successful throughput không tăng tương xứng?**

Ví dụ dữ liệu *giả định* của một API JSON:

| Offered RPS | Successful RPS | P50 (ms) | P95 (ms) | P99 (ms) | 5xx | Ghi chú |
|---:|---:|---:|---:|---:|---:|---|
| 50 | 50 | 25 | 60 | 100 | 0% | Còn nhiều headroom |
| 100 | 100 | 30 | 75 | 140 | 0% | Ổn định |
| 200 | 198 | 45 | 150 | 350 | 0,5% | Tail bắt đầu tăng |
| 300 | 275 | 100 | 500 | 1.800 | 5% | Queueing/throttling |
| 400 | 285 | 180 | 1.500 | 5.000 | 18% | Đã quá tải |

Dữ liệu này **không phải benchmark thật của Spring Cloud Gateway**. Nó minh họa hiện tượng **throughput gần đạt trần nhưng latency tăng mạnh**. Nếu chỉ đo throughput cao nhất, bạn có thể chọn 400 RPS làm “capacity” dù chỉ 285 RPS thành công và P99 tới 5 giây.

### Xác định mức tải vận hành

Capacity đáp ứng SLO không nhất thiết là throughput tối đa. Một mục tiêu hợp lý phải thỏa **đồng thời**:

- Successful RPS đủ yêu cầu.
- Error ratio dưới budget.
- P95/P99 dưới mục tiêu.
- Không có queue hoặc connection-pool saturation kéo dài.
- JVM CPU/memory, Netty direct memory và backend DB pool có headroom.
- Tình huống mất một instance hoặc tăng burst vẫn có đường phục hồi.

**Đánh giá theo công việc có ích hoàn thành đúng hạn**, không theo tổng request mà server kịp trả một status nào đó.

## 23. Đo thử chi phí route predicates, filters và body transformations

Với Gateway có nhiều routes/filters, ta có thể nghi một custom filter đang làm tăng latency. Cần thiết kế **A/B có kiểm soát**.

### Thí nghiệm từng thay đổi

1. **Baseline:** Route `Path=/api/catalog/**` → backend echo, filter tối thiểu.
2. **Route config:** Thêm một `Header`/`Method` predicate đơn giản, giữ workload.
3. **Header filter:** Thêm `SetRequestHeader`, không đụng body.
4. **Security:** Bật JWT verification với cache/JWK policy xác định.
5. **Rate limiter:** Bật Redis limiter ở quota **không chặn traffic của test** để đo overhead allowed path.
6. **Body transform:** Chỉ test với JSON nhỏ đã giới hạn; so heap/TTFB/P99.
7. **Retries:** Tạo tỷ lệ lỗi 503 xác định ở backend, đo outbound attempts.
8. **Circuit breaker:** Đưa backend chậm có kiểm soát, đo fallback/error distribution.

**Chỉ thay một yếu tố tại một thời điểm**, hoặc dùng thiết kế thí nghiệm có đối chứng rõ. Cùng lúc thay CPU limit, JVM flags, backend latency, cache TTL và filter order thì không thể quy kết P99 thay đổi cho một yếu tố.

### Phân biệt overhead với backend time

- Nếu P99 của Gateway tăng cùng backend server P99, kiểm downstream/DB trước.
- Nếu backend P99 giữ ổn nhưng Gateway HTTP client P99 tăng, kiểm connection pool, TLS/DNS hoặc network.
- Nếu HTTP client timer ổn nhưng Gateway ingress P99 tăng, kiểm Security, routing, body filter hoặc response writing.
- Nếu client P99 tăng trong khi Gateway ingress P99 ổn, kiểm ingress, CDN, network và client download.

Đây là **heuristics để khoanh vùng**, không phải phép trừ percentiles chính xác; dùng traces/instrumentation ở cùng request để xác nhận.

## 24. Security, RateLimiter, Retry, fallback và cache làm sai phép so như thế nào?

Một benchmark phải phân tách các nhánh.

| Cơ chế | Hiệu ứng lên thông lượng/latency | Phải đo cùng |
|---|---|---|
| **Spring Security** | JWT/JWK verification, permission checks, 401/403 short-circuit | % authenticated, auth failures, security timer nếu có |
| **RequestRateLimiter** | 429 sớm có thể làm average latency giảm | Accepted vs rejected RPS, limiter policy |
| **Retry** | Tăng successful responses nhưng kéo dài P99 và tăng backend attempts | Retry count, backoff time, downstream attempts |
| **CircuitBreaker** | Open circuit trả lỗi/fallback nhanh | State, fallback rate, business success |
| **LocalResponseCache** | Cache hit nhanh và không cần backend | Hit/miss ratio, stale data correctness |
| **LoadBalancer** | Phân phối đến các instances có độ trễ khác nhau | Selected instance, per-backend metrics |
| **TLS/mTLS** | Handshake, encryption cost, certificate validation | New vs reused connections, TLS errors |
| **Body filters** | Buffer/transform tăng memory, kéo dài TTFB | Payload size, heap/direct memory, GC |
| **CORS preflight** | Browser có thể phát OPTIONS trước request chính | Request types và end-user journey |
| **Fallback headers** | Có thể chuyển thông tin lỗi tới fallback | Bảo vệ dữ liệu nhạy cảm |

### Đừng “tối ưu” bằng cách trả lỗi nhanh

Giả sử thay vì gọi backend đang chậm, Gateway bật breaker và trả 503 ngay. P99 có thể từ 1.000 ms xuống 20 ms, nhưng **availability giảm**. Dashboard phải thể hiện **cả latency và service outcome**.

Tương tự, Redis rate limiter trả 429 rất nhanh có thể khiến RPS hoàn tất tăng trong khi successful RPS giảm. Một “tối ưu” chỉ được chấp nhận khi **SLO tốc độ, thành công và bảo mật** cùng được đáp ứng.

## 25. Dashboard: đọc được nguyên nhân thay vì chỉ nhìn biểu đồ

Một dashboard hiệu năng nên có các hàng:

| Hàng | Panel | Trả lời câu hỏi |
|---|---|---|
| 1. Data health | `up` per Gateway instance, scrape freshness | Metrics còn được thu thập không? |
| 2. Traffic | Incoming vs routed RPS, successful vs 4xx/429/5xx | Traffic đang đi đâu? |
| 3. Latency | P50/P95/P99 theo route + histogram count | Tail latency tăng ở route nào? |
| 4. Downstream | HTTP client attempts, latency, pool pending, connection errors | Gateway bị chờ network/backend không? |
| 5. Backend | Server P95/P99, DB spans, cache/DB pool | Backend xử lý chậm hay queue? |
| 6. Saturation | CPU, heap/direct memory, GC, threads/event-loop, FD, connections | Hệ thống sắp quá tải? |
| 7. Resilience | Retry amplification, breaker state/fallback, 429 | Có đang che lỗi hoặc nhân tải? |
| 8. Deploy | Version/revision, route change markers | Sự cố bắt đầu sau deploy nào? |

### Grafana variables gợi ý

- `environment`, `application`, `instance`;
- `routeId`, `httpMethod`;
- Một khoảng thời gian chuẩn như 5m/15m khi so trends;
- Links sang logs/traces tương ứng với **route ID, time range và trace ID** (trace ID không làm metric label).

**Không hiển thị “P99 = 0” khi không có histogram samples.** Dùng trạng thái **No data / No traffic**, đồng thời giữ panel `up` để phân biệt traffic bằng 0 với exporter không hoạt động.

### Alert cần traffic guard

Ví dụ **P99 route-level > 1 giây** chỉ có ý nghĩa khi đã có đủ requests trong cửa sổ:

~~~promql
(
  histogram_quantile(
    0.99,
    sum by (le, routeId) (
      rate(spring_cloud_gateway_requests_seconds_bucket{
        job="gateway-edge"
      }[5m])
    )
  ) > 1
)
and on (routeId)
(
  sum by (routeId) (
    rate(spring_cloud_gateway_requests_seconds_count{
      job="gateway-edge"
    }[5m])
  ) > 5
)
~~~

Ngưỡng **1 giây** và **5 RPS** ở đây chỉ để học. Production cần `for` duration, SLO/route, quyền sở hữu alert và runbook; không dùng chung ngưỡng cho upload lớn, WebSocket hay SSE.

## 26. Lab theo chặng: từ client đến Gateway và backend

### Môi trường giả định

- Gateway Server WebFlux: `http://localhost:8080`.
- Backend catalog: `http://localhost:9090`.
- Actuator Gateway: `http://127.0.0.1:9091` (chỉ lab).
- Prometheus job `gateway-edge` scrape Gateway (một hoặc nhiều instances).
- Nếu có, backend cũng export `http.server.requests` và có tracing.
- Máy phát tải độc lập hoặc đủ tài nguyên; không dùng dữ liệu nhạy cảm.

Route lab (theo namespace cũ của những Gateway releases tương ứng):

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-read
          uri: http://localhost:9090
          predicates:
            - Path=/api/catalog/**
            - Method=GET
          filters:
            - StripPrefix=1
~~~

Request `GET /api/catalog/items/42` được forward thành `GET /catalog/items/42`. Nếu release train của bạn dùng namespace `spring.cloud.gateway.server.webflux.routes`, **chuyển cấu hình theo phiên bản**, không copy cả hai namespace rồi tạo route trùng.

### Bước 1 — Baseline trực tiếp backend và qua Gateway

~~~bash
# Gọi backend trực tiếp (đối chứng):
curl -sS -o /dev/null \
  -w 'backend code=%{http_code} ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
  'http://localhost:9090/catalog/items/42'

# Gọi qua Gateway:
curl -sS -o /dev/null \
  -w 'gateway code=%{http_code} ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
  'http://localhost:8080/api/catalog/items/42'
~~~

**Không trừ hai kết quả curl đơn lẻ để tuyên bố “Gateway overhead”**: kết nối, backend cache, network path và trạng thái JVM có thể khác nhau. Dùng nhiều samples, workload tương đương và tracing/server/client instrumentation nếu muốn quy kết latency.

### Bước 2 — Kiểm meter count/sum/buckets

~~~bash
curl -sS 'http://127.0.0.1:9091/actuator/metrics/spring.cloud.gateway.requests'

curl -sS 'http://127.0.0.1:9091/actuator/prometheus' \
  | grep '^spring_cloud_gateway_requests_seconds'
~~~

Nếu không có `_bucket`, sửa histogram setup trước khi tạo P95/P99 query. Nếu labels không có `routeId`, xem tên tag thực của bản Gateway.

### Bước 3 — Chạy test ở một mức tải cố định

~~~bash
k6 run -e GATEWAY_URL=http://localhost:8080 gateway-performance.js
~~~

Quan sát **achieved RPS, failed/dropped iterations, P95/P99 từ k6**. Ghi offered rate, concurrency, payload, backend state và container limits để test tái lập.

### Bước 4 — So Prometheus và k6 đúng boundary

Trong Prometheus:

~~~promql
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_count{
    job="gateway-edge"
  }[5m])
)
~~~

~~~promql
histogram_quantile(
  0.99,
  sum by (le, routeId) (
    rate(spring_cloud_gateway_requests_seconds_bucket{
      job="gateway-edge"
    }[5m])
  )
)
~~~

**Không đòi hai P99 giống hệt**. k6 đo theo client-side `http_req_duration` (không đồng nhất server-side timer); Prometheus dùng histogram estimates, scrape/window khác; latency có thể có network/ingress overhead. Trước tiên, so **xu hướng** và **định nghĩa**.

### Bước 5 — Inject downstream delay và retry có kiểm soát

Cho backend **lab** tăng delay từ 30 ms lên 150 ms trên một tỉ lệ request xác định. Nếu có Retry, cố ý trả 503 cho một số calls để quan sát:

- Backend HTTP server P95/P99;
- Gateway route P95/P99;
- Outbound attempts/s;
- Retry backoff và total request duration;
- Số requests thành công/lỗi ở client.

**Không gây 503/timeout hàng loạt ở production để đo.**

### Bước 6 — So một phiên bản có/không body filter

Trên endpoint JSON nhỏ có giới hạn size, đo P99 và memory khi bật/tắt body-reading filter. Kiểm tra TTFB/total và xem filter đã buffer toàn body không. Đừng đưa file nhiều GiB vào `ModifyRequestBody(String.class, ...)` chỉ để chứng minh nó tốn RAM.

### Bước 7 — Kết luận từ bằng chứng

Ghi bảng kết quả:

| Biến thể | Achieved successful RPS | P95 client | P99 client | P99 gateway | P99 backend | 5xx/429 | Ghi chú |
|---|---:|---:|---:|---:|---:|---|---|
| Baseline | Đo thực | Đo thực | Đo thực | Đo thực | Đo thực | Đo thực | Không có body transform |
| Header filter | Đo thực | Đo thực | Đo thực | Đo thực | Đo thực | Đo thực | Cùng workload |
| JWT auth | Đo thực | Đo thực | Đo thực | Đo thực | Đo thực | Đo thực | Cùng token policy |
| Redis limiter | Đo thực | Đo thực | Đo thực | Đo thực | Đo thực | Đo thực | 429 riêng |
| Retry enabled | Đo thực | Đo thực | Đo thực | Đo thực | Đo thực | Đo thực | Attempts/s riêng |

**Không điền số đo dự đoán vào bảng như kết quả thật.** Nếu chưa instrument backend/outbound, ghi **Not instrumented** thay vì 0 ms.

## 27. Troubleshooting: dấu hiệu hiệu năng → chặng cần điều tra

| Triệu chứng | Giả thuyết cần kiểm | Tín hiệu / bước xác minh |
|---|---|---|
| Client P99 tăng nhưng Gateway P99 ổn | Ingress, network, TLS, client download | Ingress upstream timings, curl, client tracer |
| Gateway P99 tăng, backend P99 ổn | Security/filters, pool acquire, LB/network | Gateway tracing + HTTP client/pool metrics |
| Gateway và backend cùng P99 tăng | Backend/DB hoặc tài nguyên dùng chung | Backend traces, DB pool, CPU/GC |
| P99 tăng mạnh sau một ngưỡng RPS | Queueing/saturation | Inflight, pending acquire, CPU, latency vs offered RPS |
| Completed RPS tăng nhưng successful RPS giảm | 429/5xx nhanh | Response status mix, error SLO |
| 503 giảm, P99 tăng sau bật Retry | Retries cứu lỗi nhưng thêm backoff/attempts | Downstream attempts, retry count, deadlines |
| P99 giảm bất ngờ sau breaker mở | 503/fallback nhanh che outage | Breaker state/fallback rate/business outcome |
| Cache làm backend RPS thấp | Cache hit tốt **hoặc** request bị chặn | Hit/miss metrics và status mix |
| Upload P99 quá lớn so JSON | TTLB phụ thuộc size/bandwidth | TTFB, bytes/s, stream duration |
| SSE P99 “vô hạn” | Meter đo lifetime stream | Đo first event/inter-event gap thay thế |
| Một Gateway node chậm hơn | CPU throttling, JDK/config/deploy drift | Per-instance CPU, P99, version |
| Pool pending acquire tăng | Không đủ idle connections/backend chậm | Netty pool metrics, attempts, retries |
| TLS latency chỉ cao lần đầu | Handshake/connection reuse | So new vs reused connections |
| k6 P99 thấp dù backend stall | Closed-loop/coordinated omission, dropped load | Arrival model, dropped_iterations, offered/achieved |
| Prometheus P99 trống | Histogram chưa bật/labels sai | Raw `_bucket`, `up`, query `le` |
| P99 theo route tính bằng trung bình các pods | Phép tổng hợp percentiles sai | Gộp bucket counts rồi histogram_quantile |
| Prometheus RAM tăng | Raw path/user ID tag, quá nhiều buckets | Cardinality audit và series budget |
| Timer custom nhanh hơn thực tế | Đặt điểm đo sau security/route hoặc trước completion | Filter order, start/end boundaries |
| Metrics thiếu requests 401/403 | Security short-circuit trước route meter | So `http.server.requests` và access logs |
| Status 200 nhưng backend lỗi | Fallback đã trả 200 | Breaker/fallback instrumentation |

### Quy trình điều tra sáu bước

1. **Dữ liệu có đáng tin không?** Xem `up`, scrape latency, sample count, histogram buckets.
2. **Cùng workload không?** So offered/achieved RPS, route mix, cache/TLS/keep-alive và tỉ lệ lỗi.
3. **Client hay Gateway chậm?** So client TTFB/TTLB với Gateway HTTP server timer.
4. **Gateway hay outbound/backend chậm?** So Gateway route timer với HTTP client và backend timer; mở traces cụ thể.
5. **Queue nào đang tăng?** Connection pool pending, CPU throttling, event loop, Redis, DB pool.
6. **Thay đổi nào gây ra?** Kiểm deploy/revision, predicates/filters, retry/breaker/limiter, rollback A/B có kiểm soát.

Không đi thẳng tới “tăng thread pool” hoặc “tăng timeout” khi chưa biết **tải thật, queue nào và loại latency nào**.

## 28. Những sai lầm thống kê và kỹ thuật cần tránh

| Sai lầm | Vì sao sai | Thực hành đúng |
|---|---|---|
| Chỉ báo average latency | Che tail latency | P50/P95/P99 + samples/error mix |
| Cộng P99 các chặng | Quantile không cộng được; span lồng nhau | Trace theo request và histogram riêng |
| Trung bình P99 giữa pods | Không giữ phân bố tổng | Gộp histogram buckets trước tính quantile |
| Lấy `_max` làm P99 | Max khác quantile; có time-window semantics | `histogram_quantile` từ buckets |
| Tính P99 từ count/sum | Chỉ có average | Bật histogram hoặc thu raw samples phù hợp |
| Đo GET nhỏ rồi suy upload/video | Workload khác size/stream lifetime | SLO và benchmark theo endpoint class |
| Đánh giá capacity bằng total RPS | 429/5xx có thể tăng RPS biểu kiến | Successful RPS + error/latency SLO |
| Quên offered/achieved RPS | Generator có thể drop requests | Theo dõi generator health/dropped iterations |
| Chỉ test một cURL | Không đủ để suy P95/P99 | Lặp samples, thời gian ổn định |
| So HTTP/1.1 không TLS với HTTP/2 TLS | Connection/handshake khác | Cố định protocol/keep-alive/TLS |
| Dùng raw `Path` làm label | Cardinality bùng nổ/PII | Stable route ID/path template |
| Filter timer tính cả backend rồi gọi là CPU filter | Boundary inclusive | Instrument operation hẹp |
| Không đo backend attempts | Retry che tải | Counter theo attempt/hop |
| Coi mất scrape là 0 request | Không có data khác với traffic bằng 0 | `up` + no-data states |
| Dùng p99 từ cửa sổ quá ít samples | Nhiễu/thấp độ tin cậy | Hiển thị count, cửa sổ phù hợp |
| Tăng timeout để giảm lỗi | Giữ kết nối/queue lâu, có thể làm p99 tệ hơn | Deadline budget, queue controls, retry policy |
| Mở endpoint metrics ra Internet | Lộ topology/metrics | Network ACL, auth/TLS phù hợp |

## 29. Checklist production trước khi công bố kết quả đo

- [ ] Tôi xác định rõ **HTTP endpoint/route** và **định nghĩa một request thành công**.
- [ ] Tôi phân biệt offered, accepted, routed, completed và **successful RPS**.
- [ ] Tôi kiểm soát rate limiting/429/503 khi diễn giải throughput.
- [ ] Tôi biết `L=\lambda W` chỉ có ý nghĩa trên trạng thái tương đối ổn định và cùng boundary.
- [ ] Tôi phân biệt **TTFB, TTLB và HTTP request lifetime**, đặc biệt với upload/SSE/WebSocket.
- [ ] Tôi ghi **P50/P95/P99/P99.9**, số samples, error rate và time window phù hợp.
- [ ] Tôi không cộng P99 của các chặng hoặc trung bình P99 của các pods.
- [ ] Tôi xác minh meter/tags/units có **thực sự được export** ở Gateway version đang dùng.
- [ ] Tôi có `spring-boot-starter-actuator` + registry phù hợp nếu dùng Prometheus.
- [ ] Tôi bảo vệ management endpoint; không expose `/actuator/**` công khai.
- [ ] Tôi biết `http.server.requests` khác `spring.cloud.gateway.requests` và outbound attempt metrics.
- [ ] Tôi chỉ tính P95/P99 từ histogram buckets có thực, không từ `_max`.
- [ ] Tôi giữ nhãn `le` khi tính histogram_quantile và gộp buckets đúng cách.
- [ ] Tôi kiểm soát histogram cardinality, dynamic route IDs và tránh raw path/userId/token labels.
- [ ] Tôi có scrape health `up` và phát hiện **No data**.
- [ ] Tôi dùng traces để tìm chặng chậm **cùng một request**, không trừ hai percentiles.
- [ ] Tôi có inbound/Gateway/outbound/backend latency boundaries rõ ràng.
- [ ] Tôi không gọi timer filter bao `chain.filter` là “thời gian CPU riêng của filter”.
- [ ] Tôi đo connection-pool acquire, DNS/TCP/TLS, backend/DB khi có nghi vấn và có instrumentation.
- [ ] Tôi ghi protocol, TLS, connection reuse, load balancer, payload, concurrency.
- [ ] Tôi có baseline và một workload mix đủ đại diện traffic thật.
- [ ] Tôi dùng open-loop arrival rate khi cần khảo sát capacity ở tốc độ đến cố định.
- [ ] Tôi kiểm `dropped_iterations`/load-generator saturation và actual achieved RPS.
- [ ] Tôi đo **outbound attempts** và **fallback** khi bật Retry/CircuitBreaker.
- [ ] Tôi kiểm auth, rate limiter, body filter, cache, stream riêng theo workload class.
- [ ] Tôi có A/B test thay một yếu tố và lặp lại trong steady-state windows.
- [ ] Tôi ghi raw kết quả đủ để tái lập và không tự đặt số khi chưa instrument.
- [ ] Tôi có performance budget/SLO, alert traffic guard, runbook và ngưỡng dừng an toàn.
- [ ] Tôi không kết luận tối ưu thành công chỉ vì latency giảm trong khi tỷ lệ thành công giảm.

## 30. Bài tập và câu hỏi luyện tập

**Bài tập 1 — P95/P99 từ histogram.** Với Gateway đã export `spring_cloud_gateway_requests_seconds_bucket`, viết hai PromQL query cho P95 của một route và P99 toàn cluster. Giải thích vì sao phải giữ `le` và không lấy trung bình P99 giữa hai pods.

**Bài tập 2 — Thông lượng có ích.** Trong 60 giây, client phát 18.000 requests; 17.400 hoàn tất, 600 timeout; trong 17.400 có 1.200 trả 429 và 300 trả 503. Tính offered RPS, completed RPS và successful RPS khi success được định nghĩa là phần còn lại đúng hợp đồng.

**Bài tập 3 — Phân rã timeline.** Cho trace có Gateway server span 350 ms, HTTP client span 280 ms và backend server span 200 ms. Tại sao **không** được nói “Gateway overhead = P99 350 − P99 backend 200 = 150 ms”? Đề xuất instrument queue/pool/TLS nào để có bằng chứng.

**Bài tập 4 — Retry amplification.** Backend trả 503 lần đầu, 503 lần hai, 200 lần ba. Với 1.000 client requests, tất cả được retry theo chính sách giống nhau, tính outbound attempts. Theo dõi p99 và 5xx cuối có thể gây ngộ nhận gì?

**Bài tập 5 — Canary.** Chạy baseline và candidate với cùng 200 offered RPS, giống payload/cache/TLS, đo P50/P95/P99 và error ratio. Viết tiêu chí chấp nhận theo **cả successful throughput và P99**, không chỉ trung bình.

**Bài tập 6 — Coordinated omission.** Mô tả một phép thử closed-loop có 50 VUs, backend bị stall 5 giây. Vì sao offered RPS có thể giảm? So sánh với constant-arrival-rate và giải thích vai trò `dropped_iterations`.

**Bài tập 7 — Streaming.** Đo TTFB và TTLB của file 100 MiB qua Gateway khi bật/tắt một response body transform. Làm sao nhận biết transform làm response bị buffer? Vì sao không dùng cùng P99 SLO với JSON GET?

**Bài tập 8 — Bảo mật metrics.** Bật một route động `/api/items/{id}` và thử gắn raw path làm label. Ước lượng số series khi có 100.000 item IDs; đề xuất labels thay thế và cách giới hạn quyền truy cập `/actuator/prometheus`.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — Gateway Metrics Filter, route/filter lifecycle, Reactor Netty HTTP client và variants Server WebFlux/Server Web MVC theo phiên bản.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — Micrometer registries, histogram/percentile distributions và tags.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — quản lý exposure và bảo mật management endpoints.
- [Micrometer Reference](https://docs.micrometer.io/micrometer/reference/) — Timer, Observation, histogram, percentiles và cardinality.
- [Prometheus — Histogram and Summaries](https://prometheus.io/docs/practices/histograms/) — tổng hợp histograms, bucket bounds và lỗi khi cộng quantiles.
- [Prometheus — PromQL Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/) — `rate`, `increase`, `histogram_quantile`.
- [Prometheus — Querying Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/) — time series và labels.
- [Reactor Netty Reference](https://projectreactor.io/docs/netty/release/reference/) — HTTP client/server metrics, connection pool, TLS và timeout.
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/) — scheduling, non-blocking pipelines, backpressure và cancellation.
- [Grafana — Prometheus Data Source](https://grafana.com/docs/grafana/latest/datasources/prometheus/) — dashboards và PromQL.
- [Grafana k6 Documentation](https://grafana.com/docs/k6/latest/) — constant-arrival-rate, HTTP timings, thresholds và các lưu ý load testing.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/) — `traceparent` và sự liên kết giữa các spans across services.

**Ghi nhớ:** Đo hiệu năng Gateway không chỉ là một con số requests/s hay average latency. Hãy đo **offered và successful throughput**, **P50/P95/P99 theo đúng boundary**, và phân biệt **client → ingress → Gateway/security/filter chain → HTTP client/pool/TLS → backend → response**. Dùng **Prometheus histogram** để tính phân vị tổng hợp và **distributed traces của cùng request** để tìm chặng chậm; **không cộng hoặc lấy trung bình các P99**. Khi có retry, 429, fallback, cache hoặc streaming, hãy đo thêm **outbound attempts, business outcome và TTFB/TTLB** để tránh kết luận “nhanh hơn” trong khi hệ thống đang từ chối hoặc làm sai công việc.
