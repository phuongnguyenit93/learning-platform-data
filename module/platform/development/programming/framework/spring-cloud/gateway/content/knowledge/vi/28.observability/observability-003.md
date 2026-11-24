# Tích hợp Prometheus và xây dựng bảng theo dõi cho Spring Cloud Gateway

Một API Gateway thường là **điểm vào chung** của hệ thống microservices. Khi người dùng gặp lỗi `502/503/504`, request chậm hoặc bị giới hạn lưu lượng, chỉ nhìn log của một backend sẽ không trả lời được câu hỏi: request đã đi qua route nào, Gateway hay downstream chậm, có retry bao nhiêu lần, circuit breaker có mở hay không, hoặc sự cố chỉ xảy ra ở một Gateway instance?

Trong **SPRING_CLOUD_GATEWAY**, thực hành **Quan sát hệ thống** cần kết hợp **metrics, traces và logs**; riêng bài này tập trung vào **tích hợp Prometheus và xây dựng bảng theo dõi (dashboard)** có khả năng trả lời những câu hỏi vận hành thật. Prometheus thu thập chuỗi thời gian từ **Micrometer/Actuator**, còn Grafana (hoặc một giao diện truy vấn tương đương) trình bày lưu lượng, tỷ lệ lỗi, độ trễ, mức bão hòa, tình trạng scrape và các chỉ số của route predicate, filter chain, service discovery, authentication, rate limiting, retry, circuit breaker, TLS.

Mục tiêu sau bài học:

1. Bật đúng Micrometer Prometheus Registry và endpoint `/actuator/prometheus` trên Gateway.
2. Phân biệt metric **request vào ứng dụng**, **request đã được Gateway route** và **attempt gửi xuống backend**.
3. Xác nhận tên meter, tags và đơn vị từ **runtime thật** thay vì sao chép PromQL không khớp phiên bản.
4. Viết truy vấn PromQL cho RPS, HTTP 5xx, latency trung bình, P95/P99 và trạng thái scrape.
5. Thiết kế dashboard theo các câu hỏi vận hành, có biến lọc route/instance và cảnh báo hữu ích.
6. Hạn chế cardinality, bảo vệ endpoint metrics và kiểm thử những trường hợp có retries, rate limiting, fallback, caching và nhiều Gateway instances.

> **Phạm vi:** Ví dụ triển khai chính trên **Spring Cloud Gateway Server WebFlux** với Spring Boot Actuator và Micrometer. **Gateway Server Web MVC** có web stack và metrics integration khác; không mặc định cùng tên meter, tags hoặc cách bật gateway metrics ở mọi release train. Tên starter, namespace cấu hình, meter và labels cần được đối chiếu với **Spring Boot/Spring Cloud/Gateway phiên bản thực đang dùng**. Các URI/port trong bài là môi trường lab; Prometheus endpoint thực tế phải được bảo vệ.

## 1. Kiến trúc quan sát: từ Gateway đến Prometheus và Grafana

Prometheus thường dùng mô hình **pull**: định kỳ gửi HTTP GET đến một endpoint phát metrics và lưu các time series. Với ứng dụng Spring Boot, Actuator kết hợp Micrometer Registry có thể xuất dữ liệu ở dạng Prometheus.

~~~mermaid
flowchart LR
    C["Client / ingress"] --> G1["Gateway instance A"]
    C --> G2["Gateway instance B"]
    G1 --> S["Microservices / lb://"]
    G2 --> S
    G1 --> A1["Actuator /prometheus A"]
    G2 --> A2["Actuator /prometheus B"]
    P["Prometheus"] -->|"scrape 15s"| A1
    P -->|"scrape 15s"| A2
    P --> TS["Time-series storage"]
    GF["Grafana dashboards"] -->|"PromQL"| P
    AL["Alert rules / Alertmanager"] <-->|"evaluation/notifications"| P
    L["Logs + distributed traces"] -.->|"phân tích bổ trợ"| GF
~~~

**Prometheus không tự nhận từng HTTP request**. Nó lấy số liệu được ứng dụng tổng hợp thành counters, timers, gauges hoặc histograms qua mỗi lần scrape. Vì vậy, một lỗi xuất hiện rồi biến mất giữa hai lần scrape vẫn có thể được phản ánh trong **counter tăng**, nhưng không nên giả định mọi sự kiện đơn lẻ đều có một dòng log ở Prometheus.

### Vai trò của từng thành phần

| Thành phần | Vai trò | Không tự làm được |
|---|---|---|
| **Spring Boot Actuator** | Cung cấp management endpoints và nhiều metrics JVM/HTTP | Không tự tạo dashboard Grafana |
| **Micrometer** | API/instrumentation cho counters, timers, gauges, tags | Không lưu tất cả metrics lâu dài nếu chưa có backend |
| **Prometheus Registry** | Xuất meter theo định dạng scrape Prometheus | Không tự bật network ACL hoặc bảo mật endpoint |
| **Prometheus** | Scrape, lưu time series, chạy PromQL và alert rules | Không biết route/business semantics nếu app không instrument |
| **Grafana** | Trực quan hóa và xây dashboard/variables | Không sửa được sự thiếu sót của metrics nguồn |
| **Logs/tracing** | Giải thích request hoặc call path cụ thể | Không thay thế aggregate latency/error-rate metrics |

**Một dashboard đẹp không phải bằng chứng hệ thống được quan sát đầy đủ.** Cần kiểm tra dữ liệu được thu thập ở điểm nào của request lifecycle, điều kiện nào bị bỏ sót và semantics của từng chỉ số.

## 2. Bắt đầu từ câu hỏi vận hành, không bắt đầu từ biểu đồ

Trong một Gateway microservices, người trực vận hành thường cần trả lời:

| Câu hỏi | Tín hiệu cần đo | Quyết định hỗ trợ |
|---|---|---|
| Có bao nhiêu requests/giây vào Gateway? | Inbound request rate | Capacity, traffic spike |
| Route nào tăng lưu lượng? | Gateway requests theo route ID | Xác định dịch vụ liên quan |
| Bao nhiêu requests trả 5xx? | Error ratio theo route/status | Phát hiện lỗi hệ thống |
| Người dùng có bị chậm? | Latency P50/P95/P99 | Đánh giá SLO thay vì trung bình |
| Có route đang trả nhiều 429? | 429 rate, rate limiter outcomes | Quota hay Redis có vấn đề? |
| Retry có nhân tải backend? | Incoming requests so với downstream attempts | Ngăn retry storm |
| Circuit breaker có mở/fallback nhiều? | Breaker state, fallback counter nếu được instrument | Chẩn đoán dependency outage |
| Route có dùng cache đúng không? | Cache hit/miss thật và origin request count | Đo offload, correctness |
| Một node có lỗi hơn các node khác? | Metrics per-instance và scrape `up` | Xử lý deployment/network |
| Gateway bị bão hòa? | CPU, heap/direct memory, connection pool, threads/event loop | Scale hoặc sửa bottleneck |
| Dashboard bị trắng vì lỗi app hay lỗi scrape? | Prometheus `up`, target discovery, sample count | Phân biệt mất dữ liệu và traffic bằng 0 |

Nên tổ chức dashboard theo **bốn tín hiệu vàng**: *traffic, errors, latency, saturation*, sau đó có panels riêng cho **resilience** và **control-plane/routing changes**.

## 3. Phân biệt ba lớp request metrics

Đây là điều quan trọng nhất trước khi viết truy vấn.

| Lớp đo | Ví dụ meter / nguồn | Những request được tính |
|---|---|---|
| **HTTP server inbound** | Spring Boot `http.server.requests` khi instrumentation được bật | Các requests ứng dụng HTTP nhận và instrument được, có thể gồm 401/403/404 không đi qua Gateway route |
| **Gateway route-level** | `spring.cloud.gateway.requests` ở những bản Gateway hỗ trợ | Requests được quan sát qua Gateway metrics filter trên các routes, theo semantics filter/version |
| **Outbound/downstream attempts** | Reactor Netty/HTTP client metrics hoặc counter tùy biến đã xác minh | Những lượt gọi từ Gateway đến backend, có thể **nhiều hơn một cho mỗi client request** |

Một request từ client:

~~~text
GET /api/orders/42
  ├─ Spring Security xác thực
  ├─ Gateway chọn route orders-read
  ├─ RequestRateLimiter kiểm tra quota
  ├─ Retry attempt #1 -> orders-service: 503
  ├─ Retry attempt #2 -> orders-service: 200
  └─ Client nhận 200
~~~

Ở đây **một request client** đã có thể tạo **hai lượt outbound**. Nếu chỉ nhìn `spring.cloud.gateway.requests`, bạn không được mặc định nó thể hiện hai backend attempts; nếu nhìn HTTP client metrics, bạn không được gọi mỗi attempt là một user request.

### Những request có thể không nằm trong meter route-level

- Request không match bất kỳ Gateway route nào.
- Request bị Spring Security từ chối **trước route matching**.
- Request được một handler không phải Gateway phục vụ.
- Request bị ingress/WAF chặn trước khi đến ứng dụng.
- Các trường hợp filter short-circuit, retry/fallback/caching tùy thứ tự và implementation.

**Không suy tỷ lệ 401/403/404 trên toàn ứng dụng từ riêng gateway-route meter** nếu một số request đã bị chặn trước khi đến Gateway metrics filter. Dùng thêm inbound server metrics, access logs, security counters hoặc ingress telemetry phù hợp.

## 4. Thêm dependency cho Actuator và Prometheus

Trong một ứng dụng **Gateway Server WebFlux** có **BOM Spring Boot/Spring Cloud tương thích** quản lý phiên bản:

~~~groovy
dependencies {
    // Chọn đúng starter Gateway Server WebFlux của release train.
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'

    // Management endpoints và Micrometer integration của Spring Boot.
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Prometheus registry cho Micrometer.
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Ở những dòng Spring Cloud Gateway cũ hơn, starter có thể mang tên `spring-cloud-starter-gateway` và namespace có thể là `spring.cloud.gateway.*` thay vì `spring.cloud.gateway.server.webflux.*`. **Không thêm song song các starter khác dòng** chỉ để thử.

### Vì sao cần cả ba?

- Gateway starter cung cấp route/routing/filter engine.
- Actuator tích hợp management endpoints và metrics của ứng dụng Spring Boot.
- Prometheus registry chuyển dữ liệu Micrometer thành định dạng Prometheus; **chỉ có Actuator chưa chắc có endpoint `/actuator/prometheus`**.

Đừng tự gán version Micrometer tùy ý trái Spring Boot BOM. Đổi registry hoặc cách xuất metric có thể thay naming conventions và làm dashboard cũ trả dữ liệu rỗng.

## 5. Cấu hình Actuator cho môi trường lab

Ví dụ ứng dụng Gateway chạy trên **cổng 8080**, management endpoints trên **cổng 9091**:

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

**Đây là cấu hình lab**, không đủ để coi management endpoint đã an toàn. Ở production:

1. Dùng **network ACL / Kubernetes NetworkPolicy / service mesh policy** để chỉ Prometheus và người quản trị được truy cập management port.
2. Có thể bật TLS/authentication phù hợp với công cụ scrape và cách triển khai; quản lý credentials qua Secret, không nhúng vào Git.
3. Hạn chế endpoints được expose: `metrics` hữu ích để tra tên meter ở lab nhưng không nhất thiết public cho Prometheus ở production.
4. Kiểm tra Actuator đang chạy trên management context/port nào và Spring Security bảo vệ context ấy ra sao.
5. Không expose `env`, `configprops`, `heapdump`, `gateway route mutation` hoặc `*` ra Internet chỉ để debug.
6. Đặt rõ scrape timeout, network routing và health checks.

**Tách management port không tự bảo mật nó.** Một cổng 9091 vẫn có thể bị truy cập từ Internet nếu firewall/load balancer expose sai.

### Kiểm tra endpoint bằng curl

~~~bash
# Chỉ ví dụ khi curl chạy cùng host/network namespace với Gateway.
curl -i "http://127.0.0.1:9091/actuator/health"

# Chỉ cần trong lab để khám phá meter names:
curl -sS "http://127.0.0.1:9091/actuator/metrics"

# Prometheus text exposition:
curl -sS "http://127.0.0.1:9091/actuator/prometheus" \
  | grep '^spring_cloud_gateway_requests'
~~~

Nếu Gateway ở container khác, `127.0.0.1` trong Prometheus container là **chính Prometheus**, không phải Gateway. Khi chạy Docker/Kubernetes cần DNS/service target thích hợp. Nếu actuator endpoint có authentication/TLS, các lệnh lab phải dùng cơ chế truy cập đã được cấp quyền thay vì tắt auth.

## 6. Bật Gateway route metrics và xác minh tên thực tế

Trong nhiều dòng Spring Cloud Gateway Server WebFlux, **Gateway Metrics Filter** khi Actuator có mặt có thể ghi meter:

~~~text
spring.cloud.gateway.requests
~~~

Đây là **tên meter Micrometer**, không phải tên time series Prometheus. Prometheus thường chuyển tên timer sang dạng:

~~~text
spring_cloud_gateway_requests_seconds_count
spring_cloud_gateway_requests_seconds_sum
spring_cloud_gateway_requests_seconds_max
~~~

Tên cụ thể và series có mặt phụ thuộc registry/phiên bản/cấu hình. **Không tự giả định mọi Gateway version luôn phát đủ cả ba series hoặc dùng đúng những tags bên dưới**; hãy kiểm tra văn bản trả về ở `/actuator/prometheus`.

### Các tags Gateway thường có

| Micrometer tag | Ý nghĩa | Cảnh báo |
|---|---|---|
| `routeId` | ID của Gateway route | Dynamic route IDs quá nhiều gây cardinality cao |
| `routeUri` | URI đích/route URI | Có thể làm lộ topology và tăng số series |
| `outcome` | Nhóm kết quả HTTP | Cần biết chính xác nhóm của version |
| `status` | Trạng thái HTTP theo cách meter mô tả | Đừng nhầm với trường `httpStatusCode` |
| `httpStatusCode` | Mã HTTP, ví dụ `200`, `503` | Thường dùng cho lọc 5xx |
| `httpMethod` | GET/POST/PUT/... | Chỉ cho phép giá trị hữu hạn |
| `path` (optional) | Request path khi bật tag tương ứng | **Nguy cơ cardinality/PII lớn** |

Tài liệu Gateway của một số dòng cho phép bật tag path qua cấu hình kiểu:

~~~properties
# Ví dụ ở các bản dùng namespace cũ:
spring.cloud.gateway.metrics.tags.path.enabled=false
~~~

Các bản namespace mới có thể đặt thuộc tính dưới `spring.cloud.gateway.server.webflux.metrics...`. **Không copy property cũ sang bản mới rồi coi là đang có tác dụng.** Dùng `/actuator/configprops` trong môi trường được bảo vệ, startup logs hoặc tài liệu đúng release train để xác nhận binding. **Giữ path-tag disabled** nếu route chứa ID tự do, token hoặc giá trị nhạy cảm.

### Đọc meter ở Actuator

~~~bash
curl -sS \
  "http://127.0.0.1:9091/actuator/metrics/spring.cloud.gateway.requests"
~~~

Nếu endpoint `metrics` được expose và đã có traffic match Gateway route, response có thể mô tả meter và các available tags. Nếu nó không tồn tại:

- Chưa có traffic thích hợp để meter được khởi tạo.
- Thiếu Actuator/registry hoặc Gateway metrics filter chưa hoạt động.
- Property/namespace thay đổi hoặc metrics bị tắt.
- Ứng dụng đang chạy Gateway **Server Web MVC** hoặc Proxy Exchange với bộ meter khác.
- Endpoint management bị bảo vệ (401/403) hoặc scrape sai port.

**Đừng “chữa” bằng cách viết PromQL giả định một metric không có.** Xác minh meter ở runtime, rồi mới xây dashboard.

## 7. Histogram và vì sao P95/P99 không tự có

Timer thông thường thường cung cấp **count** và **sum** (đơn vị seconds khi xuất Prometheus), từ đó tính được **độ trễ trung bình**. Nhưng để tính **P95/P99 tổng hợp qua nhiều Gateway instances**, cần các **histogram buckets** (`..._bucket`) được instrument và export theo cấu hình phù hợp.

Ví dụ bật **percentile histogram cho riêng** meter `spring.cloud.gateway.requests` trong Spring Boot có hỗ trợ property binding này:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        "[spring.cloud.gateway.requests]": true
~~~

Dấu ngoặc vuông trong map key giúp giữ nguyên tên meter có dấu chấm khi Spring Boot binder áp quy tắc map keys; kiểm tra cấu hình hiệu lực ở phiên bản cụ thể.

Sau đó truy cập:

~~~bash
curl -sS "http://127.0.0.1:9091/actuator/prometheus" \
  | grep '^spring_cloud_gateway_requests_seconds_bucket'
~~~

Nếu không thấy `_bucket`:

1. Chưa có meter/traffic.
2. Histogram chưa bật đúng tên timer.
3. Tên meter thực khác dự kiến.
4. Exporter/registry không phát histogram như cấu hình.
5. Đang dùng loại metric khác timer hoặc stack khác.

**Histogram không miễn phí.** Mỗi bộ tag values nhân với nhiều buckets, làm tăng số lượng time series, RAM và chi phí lưu trữ. Chỉ bật histogram ở những timer cần percentile SLO; quản lý số route IDs/URI và số bucket phù hợp.

### Đơn vị và cách diễn giải

| Series | Ý nghĩa | Đơn vị |
|---|---|---|
| `..._seconds_count` | Số measurements đã ghi | Lượt |
| `..._seconds_sum` | Tổng thời gian của các measurements | Giây |
| `..._seconds_bucket{le="..."}` | Số measurements có giá trị ≤ bucket boundary | Lượt, counter tích lũy |
| `..._seconds_max` (nếu có) | Max theo semantics của Micrometer time-window | Giây, **không phải P99** |

**Không nhân nhầm 1.000 hai lần.** Dữ liệu `seconds` trên Prometheus thường là **giây**; Grafana có thể format Unit = seconds hoặc tự đổi hiển thị sang milliseconds.

## 8. Thiết lập scrape job trong Prometheus

Ví dụ file cấu hình Prometheus **chỉ dành cho lab khi Prometheus và Gateway share network namespace/host**:

~~~yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: gateway-edge
    metrics_path: /actuator/prometheus
    scheme: http
    static_configs:
      - targets:
          - "127.0.0.1:9091"
        labels:
          environment: lab
~~~

Trong Docker Compose, thay `127.0.0.1` bằng DNS/service name có thể truy cập trong network chung; trong Kubernetes dùng Service/Pod discovery hoặc Prometheus Operator `ServiceMonitor`/`PodMonitor` khi đã cài những CRDs ấy. **Không tự giả định Prometheus tự phát hiện Gateway pods**.

### Các tham số cần quan tâm

| Trường | Tác dụng |
|---|---|
| `job_name` | Nhóm target scrape, dùng làm label `job` |
| `metrics_path` | Path Actuator Prometheus |
| `scrape_interval` | Khoảng thời gian lấy mẫu |
| `scrape_timeout` | Giới hạn thời gian một scrape |
| `static_configs` hoặc service discovery | Những targets được lấy dữ liệu |
| `relabel_configs` | Chuẩn hóa/giới hạn labels từ discovery |
| TLS/Auth config | Truy cập management endpoint an toàn |
| `metric_relabel_configs` | Lọc series ở giai đoạn ingestion; cần review chi phí/mất dữ liệu |

**Đừng chèn username/password hoặc bearer token thô vào file config chia sẻ công khai.** Khi cần xác thực scrape, sử dụng secret file/Secret và config TLS/auth phù hợp; giới hạn quyền đọc credentials của Prometheus.

### Prometheus đang scrape thành công hay chưa?

Truy vấn:

~~~promql
up{job="gateway-edge"}
~~~

Ý nghĩa:

- `1`: lần scrape gần nhất thành công với target tương ứng.
- `0`: target tồn tại trong discovery/config nhưng scrape thất bại.
- **Không có series**: target có thể chưa được discovery, job không tồn tại, series hết retention/lookback hoặc truy vấn label sai.

`up=1` chứng minh **scrape thành công**, **không chứng minh Gateway routing và backend khỏe**. Kết hợp route-level metrics, traffic probes và health checks.

## 9. PromQL cơ bản: request rate (RPS)

Các ví dụ sau **giả định** runtime thật đã phát series `spring_cloud_gateway_requests_seconds_count` với các labels `job`, `routeId`, `httpStatusCode`. Nếu tên labels khác, thay cho đúng series được scrape.

### Tổng RPS của Gateway routes

~~~promql
sum(
  rate(spring_cloud_gateway_requests_seconds_count{job="gateway-edge"}[5m])
)
~~~

`rate(counter[5m])` ước lượng tốc độ tăng trung bình mỗi giây trong cửa sổ 5 phút và xử lý counter reset (ví dụ khi pod restart) tốt hơn phép trừ counter thô.

### RPS theo route ID

~~~promql
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_count{job="gateway-edge"}[5m])
)
~~~

Kết quả cho thấy `catalog-read`, `orders-write`... nhận bao nhiêu traffic trên toàn bộ Gateway instances được scrape trong job đó. Đảm bảo route IDs nhất quán giữa các nodes; route IDs sinh ngẫu nhiên theo mỗi lần deploy sẽ làm dashboard khó so sánh.

### RPS theo HTTP method

~~~promql
sum by (httpMethod) (
  rate(spring_cloud_gateway_requests_seconds_count{job="gateway-edge"}[5m])
)
~~~

Khi muốn so sánh GET và POST của một route, thêm filter `routeId="catalog-read"` hoặc Grafana variable theo phần dashboard.

### Tổng requests trong 1 giờ

~~~promql
sum(
  increase(spring_cloud_gateway_requests_seconds_count{job="gateway-edge"}[1h])
)
~~~

`increase` tính mức tăng counter được điều chỉnh cho resets và nội suy theo cửa sổ; kết quả có thể không nguyên tuyệt đối. Nó phù hợp mô tả xu hướng và tổng ước lượng trong một khoảng, **không phải log chính xác của từng request**.

## 10. PromQL tỷ lệ lỗi: 5xx, 4xx và 429

Một dashboard Gateway cần tách **lỗi server** khỏi **lỗi client**, vì 401/403 từ chính sách xác thực không đồng nghĩa Gateway bị sự cố.

### 5xx rate theo route

~~~promql
sum by (routeId) (
  rate(
    spring_cloud_gateway_requests_seconds_count{
      job="gateway-edge",
      httpStatusCode=~"5.."
    }[5m]
  )
)
~~~

### Tỷ lệ 5xx (%) theo route

~~~promql
100 *
sum by (routeId) (
  rate(
    spring_cloud_gateway_requests_seconds_count{
      job="gateway-edge",
      httpStatusCode=~"5.."
    }[5m]
  )
)
/
sum by (routeId) (
  rate(
    spring_cloud_gateway_requests_seconds_count{
      job="gateway-edge"
    }[5m]
  )
)
~~~

Công thức:

\[
\mathrm{5xx\ ratio} = \frac{\mathrm{5xx\ requests}}{\mathrm{all\ measured\ gateway\ requests}}\times100\%
\]

**Lưu ý về mẫu số:** chỉ tính những requests mà *gateway-route meter* đã quan sát. Nó không mặc định đại diện tất cả inbound requests, đặc biệt khi Spring Security chặn trước route hoặc request không match route.

### 429 rate

~~~promql
sum by (routeId) (
  rate(
    spring_cloud_gateway_requests_seconds_count{
      job="gateway-edge",
      httpStatusCode="429"
    }[5m]
  )
)
~~~

`429 Too Many Requests` có thể từ `RequestRateLimiter`, ingress hoặc downstream. **Không mặc định 429 từ tất cả các tầng đều được Gateway route meter ghi nhận**; kiểm chứng filter ordering và đối chiếu inbound/ingress logs.

### 401/403 và 404

- 401/403 có thể phản ánh Spring Security chặn trước khi Gateway route metrics được ghi.
- 404 có thể do route không match hoặc backend trả 404 sau khi route đã match.
- 5xx cũng có thể do fallback/circuit breaker hoặc lỗi client connection, không chỉ do backend.

Vì vậy, một **inbound HTTP dashboard** nên dùng thêm `http.server.requests` nếu metric đó thực sự được export trong ứng dụng, và dashboard **downstream health** nên có counters riêng theo target.

### Xử lý mẫu số bằng 0

Khi một route không nhận request trong 5 phút, mẫu số bằng 0 hoặc series không tồn tại. Không nên hiển thị “0% errors” như bằng chứng route khỏe. Dashboard nên hiển thị **No data / No traffic** khi mẫu số không có ý nghĩa, và đặt ngưỡng lượng traffic tối thiểu cho alert.

## 11. PromQL latency: trung bình, P95 và P99

### Average latency (seconds)

~~~promql
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_sum{job="gateway-edge"}[5m])
)
/
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_count{job="gateway-edge"}[5m])
)
~~~

Average latency là thông tin hữu ích để thấy trend, nhưng **không đủ để đánh giá tail latency**. Một route có 95% request 20ms và 5% request 5s có average tương đối thấp hơn trải nghiệm của nhóm người dùng chậm.

### P95 theo route, khi histogram buckets thực sự tồn tại

~~~promql
histogram_quantile(
  0.95,
  sum by (le, routeId) (
    rate(
      spring_cloud_gateway_requests_seconds_bucket{
        job="gateway-edge"
      }[5m]
    )
  )
)
~~~

### P99 theo route

~~~promql
histogram_quantile(
  0.99,
  sum by (le, routeId) (
    rate(
      spring_cloud_gateway_requests_seconds_bucket{
        job="gateway-edge"
      }[5m]
    )
  )
)
~~~

**`le` phải được giữ** trong `sum by (le, routeId)` vì `histogram_quantile` cần các bucket bounds. Nếu muốn tính P95 **toàn bộ Gateway**, thay bằng `sum by (le)`. Không lấy trung bình các P95 của từng instance để suy P95 toàn cluster.

### Những giới hạn của percentile đo bằng histogram

- Histogram cho **ước lượng percentile dựa trên bucket boundaries**, không phải timestamp chính xác của từng request.
- Buckets quá thưa quanh ngưỡng SLO có thể làm percentile ước lượng kém chính xác.
- Cửa sổ 5 phút quá ít requests sẽ làm P99 dao động mạnh.
- Một số latency metric đo giai đoạn **Gateway filtering/routing**, không nhất thiết bằng thời gian người dùng cuối trải nghiệm qua CDN/ingress/network.
- Nếu không có `_bucket`, **không biến `_max` hoặc average thành P99**.

### Ví dụ đọc kết quả

Giả sử dashboard cho route `catalog-read`:

| Chỉ số | Giá trị minh họa | Cách hiểu |
|---|---:|---|
| RPS | 240 requests/s | Lưu lượng đo qua gateway-route meter |
| Average | 75 ms | Trung bình giai đoạn đo |
| P95 | 180 ms | Khoảng 95% measurements ở dưới mức ước lượng |
| P99 | 650 ms | Tail latency; cần điều tra nếu SLO thấp |
| 5xx ratio | 0,4% | Không nhất thiết do Gateway bản thân lỗi |
| 429 rate | 15 req/s | Cần xác định layer tạo 429 và quota policy |

Các số này chỉ là **dữ liệu giả lập để tập diễn giải**, không phải kết quả thu được từ một hệ thống thực.

## 12. Thiết kế dashboard Grafana theo luồng điều tra

Một dashboard có ích nên cho phép đi từ **toàn cảnh → route → instance → downstream**, thay vì xếp nhiều biểu đồ không liên quan.

### Bố cục đề xuất

| Hàng | Panel | Kiểu biểu đồ | Mục đích |
|---|---|---|---|
| 1. Health | Scrape `up` per instance | State/Stat | Data đang còn thu thập được không? |
| 1. Health | Total inbound RPS, Gateway routed RPS | Time series | Phân biệt mất traffic, unmatched/denied |
| 1. Health | Global 5xx ratio | Stat + sparkline | Nhìn nhanh rủi ro availability |
| 1. Health | Global P95/P99 | Time series | Tail latency toàn Gateway |
| 2. Routes | RPS by route ID | Stacked time series / table | Route hot, traffic shifting |
| 2. Routes | 5xx rate by route | Time series / table | Khoanh vùng lỗi |
| 2. Routes | P95/P99 by route | Time series | Route chậm |
| 2. Routes | Status code breakdown | Time series | Phân biệt 401/403/404/429/5xx |
| 3. Infrastructure | CPU, heap, GC, thread/event-loop hoặc pool metrics | Time series | Saturation/resource leaks |
| 3. Infrastructure | JVM/process uptime/restarts | Stat | Liên hệ cold start/deploy |
| 4. Resilience | Retry attempts, breaker state, fallback count | Time series | Phát hiện cascade/retry storm |
| 4. Resilience | Cache hits/misses, rate-limit decisions | Time series | Hiệu quả/không đúng quota |
| 5. Deployment | Route revision, app version, node health | Table | Configuration drift/canary |

**Không phải mọi panel đều có metric built-in.** Hàng resilience cần instrument tại điểm phù hợp hoặc nối metrics của Resilience4j/Redis/cache/LoadBalancer khi phiên bản và binder có hỗ trợ. Dashboard phải ẩn hoặc ghi rõ **Not instrumented** cho các panel chưa có nguồn dữ liệu, không tự hiển thị 0 như thể tính năng chưa từng lỗi.

### Grafana variables

Các biến hữu ích:

- `$job` hoặc `$application`: chọn dịch vụ Gateway.
- `$environment`: staging/prod.
- `$instance`: xem node cụ thể hoặc chọn All.
- `$routeId`: lọc một route quan tâm.
- `$statusClass`: chọn 2xx/4xx/5xx ở panel chuyên biệt.

Ví dụ cú pháp **Grafana Prometheus variable query** (không phải PromQL dùng trực tiếp ở Prometheus expression browser):

~~~text
label_values(
  spring_cloud_gateway_requests_seconds_count{job="gateway-edge"},
  routeId
)
~~~

Ở panel PromQL, dùng biến được Grafana xử lý:

~~~promql
sum by (routeId) (
  rate(
    spring_cloud_gateway_requests_seconds_count{
      job="gateway-edge",
      routeId=~"$routeId"
    }[5m]
  )
)
~~~

**Biến `$routeId` là cú pháp template của Grafana, không phải cú pháp PromQL thuần.** Khi bật All/multiselect, bảo đảm format/escape regex của biến phù hợp. Không để bất kỳ người xem nào biến dashboard thành công cụ query toàn bộ PII labels (vốn không nên có).

### Tổ chức đơn vị/axes

- RPS: `req/s`.
- Error ratio: phần trăm `0–100%`.
- Latency: seconds hoặc milliseconds, **cùng một chuẩn** giữa các panels.
- Memory: bytes/MiB/GiB, phân biệt heap và direct memory.
- CPU: percent theo process/container, tránh trộn với CPU cores.
- `up`: hiển thị 0/1 theo instance, không biến “không có series” thành 1.

Đưa ghi chú ngay trong dashboard: **meter nào, đo ở đâu, sample window bao lâu, có tính 401/404/429 hay không**.

## 13. Tối ưu cardinality và ngân sách time series

Prometheus lưu mỗi tổ hợp **metric name + labels** thành một time series. Với Gateway, dữ liệu dễ tăng nhanh vì có nhiều routes, status codes, methods, instances và histogram buckets.

Giả sử một histogram có:

- 100 route IDs;
- 6 HTTP status codes;
- 4 methods;
- 8 instances;
- 15 buckets (minh họa).

Chỉ riêng bucket series có thể đạt:

\[
100\times6\times4\times8\times15 = 288{,}000
\]

Đây là **ước lượng worst-case nếu mọi tổ hợp đều xuất hiện**, chưa tính `_sum`/`_count`, labels khác và các metrics khác. Không phải mỗi Gateway tự tạo đúng số series đó.

### Nên và không nên gắn nhãn

| Tag | Khuyến nghị | Vì sao |
|---|---|---|
| `routeId` | Có nếu tập route được kiểm soát | Dùng để phân tích per-route |
| `application`, `environment`, `region` | Có, giá trị hữu hạn | So sánh môi trường |
| `httpMethod` | Có | Cardinality hữu hạn |
| `httpStatusCode` | Có | Điều tra lỗi |
| `routeUri` | Cân nhắc | Có thể biến động/lộ topology |
| `path` đầy đủ | **Tránh** | `/users/1`, `/users/2`,... sinh vô hạn series |
| URL có query | **Không** | PII/token, cardinality |
| `userId`, `tenantId` tự do | **Không** | Không giới hạn cardinality, có thể là dữ liệu nhạy cảm |
| JWT/token/API key/cookie | **Tuyệt đối không** | Rò credentials |
| `traceId`/`requestId` | Không làm metric tag | Mỗi request một giá trị; dùng trace/log/exemplar nếu phù hợp |
| Raw exception message | Không | PII, internal detail và cardinality |

### Path template thay vì raw path

Nếu thực sự cần phân biệt API resource patterns, ưu tiên **route ID** hoặc một **route template được chuẩn hóa** như `/api/orders/{id}` do platform cấp. Không tạo tag từ `request.getURI().getRawPath()` hoặc query user nhập.

Với **dynamic routes**, kiểm soát số route IDs mới mỗi phút/ngày, chu kỳ xóa, và cardinality của `routeUri`/optional `path`. Một portal tạo mỗi request thành route ID mới có thể khiến Prometheus và Grafana bị quá tải.

### Histogram đúng lúc

Bật histogram cho 2–3 timers thật sự cần P95/P99 trước; đo số series tại Prometheus bằng `scrape_samples_scraped`, `prometheus_tsdb_head_series` (nếu có), hoặc dashboard internal metrics của Prometheus. Không bật histogram đại trà cho mọi endpoint và mọi tag chỉ vì muốn “nhiều dữ liệu”.

## 14. Theo dõi Retry, CircuitBreaker, RateLimiter, cache và LoadBalancer

Các tính năng resilience ảnh hưởng cách giải thích dữ liệu từ Gateway.

### Retry: requests và attempts khác nhau

Một client request GET có thể được thử 3 lần trước khi thành công. Nếu dashboard chỉ có Gateway request count và error ratio cuối là 0%, có thể backend đang nhận **lượng tải gấp 3** mà người vận hành không thấy.

Nên đo thêm (nếu instrumentation hỗ trợ):

~~~text
gateway_downstream_attempts_total{
  route_id="catalog-read",
  outcome="success|failure"
}
~~~

Đây là **quy ước counter tùy biến đề xuất**, **không phải metric mặc định của Gateway**. Mỗi **attempt outbound** cần được ghi **một lần** tại điểm thật sự phát request; nếu đặt counter sai chỗ trong filter chain, bạn có thể chỉ đếm một lần cho cả chuỗi retry hoặc đếm trùng.

Một tỷ lệ hữu ích:

\[
\mathrm{Attempt\ amplification}
=
\frac{\mathrm{Downstream\ attempts}}
     {\mathrm{Gateway\ routed\ requests}}
\]

Tỷ lệ xấp xỉ 1 là trạng thái thường mong đợi ở những route mỗi request tạo một outbound call; giá trị cao có thể do retry, nhưng cũng có thể do fan-out có chủ đích. **Không dùng làm alert chung cho mọi BFF/aggregation endpoint**.

### CircuitBreaker và fallback

Nếu sử dụng Spring Cloud CircuitBreaker/Resilience4j, có thể có metrics về call outcomes, states và slow calls **khi bindings/registry được bật đúng cách**. Tên series phụ thuộc integration/version; không tự giả định luôn có `resilience4j_circuitbreaker_state` hoặc chính xác một giá trị state trên mọi bản.

Một failure có thể bị fallback thành response 200; Gateway HTTP 5xx ratio khi đó **không phản ánh đầy đủ độ suy giảm chất lượng**. Cần một **fallback counter** riêng và dashboard phân biệt normal success với degraded success.

### RequestRateLimiter và Redis

`RequestRateLimiter` có thể trả `429` khi quota vượt, nhưng chưa đủ để kết luận Redis khỏe. Nếu phụ thuộc Redis:

- Theo dõi Redis connectivity/latency qua client/Redis metrics thực tế.
- Đếm allowed/denied/error theo một **low-cardinality policy ID** khi có instrumentation.
- Không gắn `principal` hoặc raw API key làm metric tag.
- Phân biệt 429 do Gateway limiter, ingress hoặc downstream.

### LocalResponseCache

Một response cache có thể giảm outbound calls, nhưng **HTTP 200 nhanh không phải bằng chứng cache hit**. Cần đo lookup hit/miss thật ở implementation hỗ trợ và đối chiếu backend calls. Cache metrics có thể đến từ Caffeine binder hoặc filter custom được instrument, không mặc định có tên `gateway_cache_hits_total`.

Đừng tối ưu hit ratio đến mức cache nhầm response user/tenant; **correctness và isolation** phải được kiểm thử độc lập.

### Service discovery / LoadBalancer

Một URI `lb://orders-service` có thể chọn nhiều instances. Gateway route metrics nhìn thấy `routeUri` nhưng **không nhất thiết ghi instance cuối được chọn**. Muốn tìm backend instance bị lỗi, dùng metrics/traces từ HTTP client, load balancer hoặc backend được instrument, tránh gắn raw host động tạo cardinality vô hạn.

## 15. Theo dõi saturations: JVM, Netty, pools và TLS

Dù lỗi backend dễ thấy ở HTTP status, Gateway cũng có thể chậm do chính nó bị bão hòa.

| Nhóm | Metric/source thường có | Điều cần quan sát |
|---|---|---|
| JVM heap | `jvm.memory.used` / `jvm.memory.max` | Memory pressure, leak |
| JVM GC | `jvm.gc.pause` | GC pauses làm tăng tail latency |
| Process CPU | `process.cpu.usage` hoặc container metrics | CPU saturation |
| Threads | `jvm.threads.live` | Thread growth; stack-specific |
| Reactor Netty HTTP client | Connection pool/HTTP client metrics khi đã enable | Pending acquire, active connections, timeout |
| Server connections | Netty/container/ingress metrics | Client concurrency, slow connections |
| TLS | Handshake failures từ client/server/ingress metrics & logs | Certificate/SNI/trust issues |
| Redis/Discovery | Client/service metrics khi instrument | External dependency bottleneck |
| Host/container | CPU throttling, memory limits, OOM kills | Infrastructure bottleneck |

**Tên meter Reactor Netty có thể khác theo version và cách bật metrics**, không phải lúc nào Gateway tự export connection pool metrics khi thêm Prometheus registry. Trước khi tạo panel, kiểm tra meter list và hỗ trợ của HTTP client đang dùng.

### Vì sao P99 Gateway tăng dù backend P99 không tăng?

Có thể do:

1. Gateway event loop/Servlet threads bị block.
2. Connection pool hết chỗ hoặc chờ acquire.
3. DNS/TLS handshake hoặc service discovery chậm.
4. Retry/backoff tăng tổng thời gian.
5. Request/response body filter buffer file lớn.
6. Redis limiter chậm hoặc circuit breaker chuyển trạng thái.
7. Scrape/dashboard đang so hai nhóm time series khác nhau.

Dùng trace spans và logs có correlation ID để khoanh vùng **hop chậm**, không chỉ suy từ một panel latency.

## 16. Alerting: cảnh báo có điều kiện và runbook

Alert cần trả lời: **người trực phải làm gì sau khi nhận?** Nếu không có hành động rõ, dashboard mới chỉ là biểu đồ.

### Ví dụ alert 5xx ratio cao khi có đủ traffic

File Prometheus rule **minh họa**:

~~~yaml
groups:
  - name: gateway-edge.rules
    rules:
      - alert: GatewayHigh5xxRatio
        expr: |
          (
            sum by (job) (
              rate(spring_cloud_gateway_requests_seconds_count{
                job="gateway-edge",
                httpStatusCode=~"5.."
              }[5m])
            )
            /
            sum by (job) (
              rate(spring_cloud_gateway_requests_seconds_count{
                job="gateway-edge"
              }[5m])
            )
          ) > 0.05
          and on (job)
          sum by (job) (
            rate(spring_cloud_gateway_requests_seconds_count{
              job="gateway-edge"
            }[5m])
          ) > 1
        for: 10m
        labels:
          severity: warning
          service: api-gateway
        annotations:
          summary: "Gateway 5xx ratio cao"
          description: "Tỷ lệ 5xx trên traffic đủ mẫu vượt 5% trong 10 phút."
~~~

**5%, 1 req/s và 10 phút là ngưỡng minh họa**, không phải SLO chung. Trong production, xây ngưỡng theo mức rủi ro, error budget và khung thời gian của service. Điều kiện traffic tối thiểu giúp hạn chế báo động tỷ lệ cao nhưng chỉ có 1–2 request.

### Cảnh báo scrape lỗi

~~~promql
up{job="gateway-edge"} == 0
~~~

Bổ sung rule/logic cho **target biến mất khỏi discovery**: nếu series `up` không tồn tại, biểu thức `up == 0` **không tự bắt được**. Không dùng “không có dữ liệu = khỏe”.

### Cảnh báo latency P99 cao

~~~promql
histogram_quantile(
  0.99,
  sum by (le, routeId) (
    rate(spring_cloud_gateway_requests_seconds_bucket{
      job="gateway-edge"
    }[5m])
  )
) > 1
~~~

Đây là ngưỡng **1 giây** minh họa. Nên kết hợp lượng traffic tối thiểu và thời gian `for`; route ít request khiến P99 nhiễu. Với API streaming/WebSocket hoặc upload lớn, dùng SLO latency riêng, không áp cùng ngưỡng 1 giây cho mọi route.

### Runbook tối thiểu khi alert 5xx

1. Kiểm tra `up` và sample freshness; tránh kết luận hệ thống lỗi từ dashboard trắng.
2. Xác định top routes gây tăng 5xx.
3. So P95/P99, traffic và method/status code distribution.
4. Kiểm tra retry amplification, circuit breaker opens/fallback, 429, Redis và backend metrics.
5. So giữa Gateway instances/pods, deploy revision và route configuration changes.
6. Dùng trace/log có correlation ID (không raw token) để tìm hop lỗi.
7. Nếu issue theo canary/config, rollback có kiểm soát; nếu dependency outage, giảm retry pressure/throttle hoặc điều phối incident.
8. Sau khôi phục, ghi postmortem và chỉnh alert/dashboard nếu metric bị thiếu hoặc bị đếm sai.

## 17. Bài thực hành: tạo traffic rồi truy vấn Prometheus

### Điều kiện lab

Giả sử:

- Gateway Server WebFlux: `http://localhost:8080`.
- Actuator management: `http://127.0.0.1:9091`.
- Backend catalog: `http://localhost:9090`, có endpoint `GET /catalog/items/42`.
- Prometheus có một target `gateway-edge` trỏ đúng management endpoint.
- Đã bật histogram cho meter route-level và đã xác minh có `_bucket`.
- Có quyền truy cập lab; không gửi traffic kiểm thử ồ ạt đến production.

Route mẫu trong các dòng Gateway sử dụng namespace cấu hình cũ:

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

Với `GET /api/catalog/items/42`, `StripPrefix=1` loại `/api` để backend nhận `/catalog/items/42`. Nếu đang dùng Gateway Server WebFlux với namespace cấu hình mới, đặt route ở namespace **đúng release train** (ví dụ nhóm `server.webflux` tương ứng) và xác nhận route thực sự được nạp trước khi đo metrics.

### Bước 1 — Gọi thử và kiểm tra đường đi

~~~bash
curl -i "http://localhost:8080/api/catalog/items/42"
~~~

Xác nhận backend được gọi đúng. Status là 200, 404 hay lỗi khác tùy endpoint test. Nếu request không match route, không dùng nó làm bằng chứng meter route-level bị lỗi.

### Bước 2 — Tạo vài requests tuần tự

~~~bash
for n in 1 2 3 4 5; do
  curl -sS -o /dev/null \
    -w "code=%{http_code} time=%{time_total}s\n" \
    "http://localhost:8080/api/catalog/items/42"
done
~~~

Tập request nhỏ là để kiểm tra **counter tăng**, không phải để tính P99 đáng tin. Tránh kết luận percentile chính xác từ 5 samples.

### Bước 3 — Xác minh meter ở Actuator

~~~bash
curl -sS "http://127.0.0.1:9091/actuator/metrics" \
  | grep -o 'spring.cloud.gateway.requests'

curl -sS \
  "http://127.0.0.1:9091/actuator/metrics/spring.cloud.gateway.requests"
~~~

Nếu `/actuator/metrics` được expose ở lab, response có thể liệt kê available tags. Nếu không có meter, quay lại phần 6 để xem dependencies, property namespace, filter enablement và request route matching.

### Bước 4 — Xem Prometheus text exposition

~~~bash
curl -sS "http://127.0.0.1:9091/actuator/prometheus" \
  | grep '^spring_cloud_gateway_requests_seconds'
~~~

Kiểm tra có những series nào: `_count`, `_sum` và `_bucket`. Ghi lại label names **đúng như thực tế**. Nếu tên không khớp ví dụ, điều chỉnh PromQL.

### Bước 5 — Truy vấn `up` và RPS

Trong Prometheus expression browser:

~~~promql
up{job="gateway-edge"}
~~~

Sau đó:

~~~promql
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_count{
    job="gateway-edge"
  }[5m])
)
~~~

Nếu chỉ có vài requests, `rate[5m]` có thể thấp hoặc không có đủ samples ngay. Đợi Prometheus lấy ít nhất nhiều scrape points và kiểm tra target; **không tăng traffic mù quáng để dashboard xuất hiện biểu đồ**.

### Bước 6 — Tạo lỗi có kiểm soát

Trên **backend lab**, tạo endpoint trả `503` có chủ đích; route đúng path đến endpoint ấy, rồi gọi từ cURL. So sánh:

- Gateway route meter có ghi `httpStatusCode=503` không?
- Inbound HTTP meter có ghi status tương ứng không?
- Có Retry/CircuitBreaker nào biến response cuối thành 200, 502 hay 504 không?
- Backend thực nhận bao nhiêu attempts?
- Biểu đồ 5xx ratio theo route có thay đổi khi Prometheus scrape các số counter mới không?

Không tạo lỗi 503 có chủ đích trên dịch vụ production và không giả định mọi 5xx đều do backend.

### Bước 7 — Tắt một target lab có kiểm soát

Khi một Gateway test instance dừng hoặc management endpoint bị ngắt, quan sát `up=0`. Khi một target bị **xóa khỏi scrape config/discovery**, kiểm tra no-data behavior. Đây là hai tình huống khác nhau; dashboard/alert phải phân biệt.

## 18. Xây Grafana dashboard từng bước

### Bước 1 — Cấu hình datasource

Trong Grafana, thêm **Prometheus datasource** trỏ đến URL của Prometheus server mà **Grafana container/instance** truy cập được. Không dùng nhầm `localhost` của Gateway. Xác nhận Explore có thể chạy:

~~~promql
up{job="gateway-edge"}
~~~

Nếu kết quả không có data, kiểm tra Prometheus target/discovery, scrape errors, datasource URL, RBAC và time range.

### Bước 2 — Tạo các biến lọc

Ví dụ dùng query variable `routeId` với `label_values(...)` như phần 12. Tạo variable `instance` từ label `instance` của series `up`; nhớ bật All/multiselect phù hợp với regex filters. Giá trị route ID phải được kiểm soát; tránh các route IDs chứa input tự do của người dùng.

### Bước 3 — Dựng panel theo thứ tự

1. **Scrape health** trước để biết metrics có còn được gửi không.
2. **Gateway routed RPS**, tiếp theo **5xx ratio**.
3. **P95/P99** khi bucket series thực sự có.
4. **Top routes** theo RPS và 5xx rate.
5. **By instance** khi nghi vấn chỉ một node.
6. **JVM/memory/CPU/connection** ở hàng saturation.
7. **Retry, circuit breaker, cache, rate limiter** khi có data source và metric riêng.
8. **Deployment annotations** để đối chiếu alert với version mới/config mới.

### Bước 4 — Tạo đường dẫn điều tra

Từ một panel route, cung cấp dashboard link/drill-down theo `routeId`, `environment`, `instance`, và đường dẫn đến trace/log viewer nếu đã tích hợp. **Không đưa access token, user ID hoặc raw query vào URL panel**.

### Bước 5 — Kiểm tra bằng sự kiện thật trong lab

- Một request thành công làm tăng counter.
- Một backend 503 trong lab làm tăng 5xx của meter phù hợp.
- Một route chưa có traffic hiện **No data/No traffic**, không bị hiểu là 100% success.
- Một target scrape ngừng trả `up=0` hoặc biến mất nếu discovery thay đổi.
- Một route dùng Retry có backend attempts > incoming requests khi được instrument.
- Grafana time range và timezone được đặt phù hợp với người xem.
- P95/P99 chỉ xuất hiện khi histogram đã phát buckets.

**Dashboard chỉ hoàn thành khi bạn đã kích hoạt và kiểm chứng ít nhất một tình huống cho từng panel quan trọng.**

## 19. Troubleshooting: khi metrics sai hoặc dashboard rỗng

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `/actuator/prometheus` 404 | Thiếu Prometheus registry, endpoint chưa expose, sai path/port | Kiểm tra dependencies, management context, exposure |
| `/actuator/prometheus` 401/403 | Management security yêu cầu quyền | Cấu hình scrape credentials/network hợp lệ; không tắt auth bừa bãi |
| Prometheus `up=0` | Target không kết nối, timeout, TLS/auth sai | Kiểm tra Targets page và scrape error |
| Không có `up` series | Target chưa được discovery, job sai hoặc series không còn | Kiểm tra scrape config/service discovery |
| Có JVM metrics nhưng không có Gateway requests | Chưa có route traffic, Gateway metrics filter chưa hoạt động, sai stack | Kiểm tra meter Actuator và route match |
| Metric tên khác ví dụ | Namespace/release train/Micrometer naming khác | Dùng tên runtime, sửa PromQL |
| Không có `_bucket` | Histogram chưa bật đúng meter | Xác minh distribution config và restart nếu cần |
| P95/P99 trắng nhưng count có | Query sai `le`, không có buckets, regex job/routeId sai | Kiểm tra raw series |
| 5xx ratio 0 dù client thấy lỗi | Lỗi xảy ra trước route metrics, status cuối khác, filter order | So ingress/inbound/backend/request traces |
| 429 không xuất hiện ở route meter | Limiter từ chối trước điểm đo hoặc 429 từ ingress | Bổ sung metric tầng chặn |
| Counter giảm sau deploy | Counter reset khi app restart | Sử dụng `rate`/`increase`, không trừ raw values |
| RPS theo route đột nhiên tăng sau đổi ID | Route IDs thay đổi, labels nhân đôi | So config revision và series cardinality |
| P99 rất nhiễu | Ít traffic hoặc buckets quá thưa | Cửa sổ dài hơn, kiểm tra sample count |
| P99 quá cao sau bật body logging | Buffering/blocking trên Gateway | Bỏ body logging, profile và xem memory |
| Prometheus tốn RAM | Path/user ID labels, histogram quá rộng | Giảm cardinality và số series |
| Dashboard hiển thị số giây thành mili giây sai | Unit conversion sai | Kiểm tra `_seconds_*` và format |
| Retry nhiều nhưng 5xx không tăng | Retry thành công, status cuối là 200 | Instrument downstream attempts |
| Circuit breaker fallback nhiều nhưng request 200 | Degraded success bị che | Instrument fallback counter/state |
| Một node mất traffic trên dashboard | Scrape/down, service discovery hoặc routing lệch | Xem `up`, instance label, deployment |
| Dashboard trắng sau đổi datasource | Grafana datasource/time range/permissions sai | Test `up` trong Explore trước |
| Endpoint metrics lộ topology | routeUri, job/instance labels public | Giới hạn management network và quyền xem |

### Quy trình chẩn đoán sáu lớp

1. **Ứng dụng có hoạt động và route match không?** Thử cURL một endpoint lab có backend thật.
2. **Micrometer có meter không?** Dùng Actuator `/metrics` trong môi trường được bảo vệ.
3. **Prometheus exposition có series không?** Kiểm tra `/actuator/prometheus` và tên labels.
4. **Prometheus có scrape không?** `up`, Targets page, job/instance labels.
5. **PromQL có đúng và đủ samples không?** Test count/rate trước, sau đó 5xx và histogram.
6. **Grafana panel có unit, time range, variables, permissions đúng không?** Kiểm tra datasource Explore và từng panel.

Đừng giải quyết dashboard trắng bằng cách bật mọi endpoint Actuator công khai hoặc log raw request bodies/tokens.

## 20. Checklist nghiệm thu production

- [ ] Tôi dùng **đúng Spring Cloud Gateway variant và release train**, không sao chép metric config từ WebFlux sang MVC khi chưa xác minh.
- [ ] Ứng dụng có `spring-boot-starter-actuator` và `micrometer-registry-prometheus`.
- [ ] `/actuator/prometheus` được expose **chỉ cho Prometheus/đối tượng được cấp quyền**.
- [ ] Management port có network ACL, TLS/auth phù hợp và không lộ route mutation/heapdump/secrets.
- [ ] Prometheus scrape đúng target/service, `up=1` trên mọi instance đang mong đợi.
- [ ] Tôi phân biệt `http.server.requests`, `spring.cloud.gateway.requests` và outbound attempt metrics.
- [ ] Tôi đã xác minh meter/tags thật bằng Actuator/Prometheus exposition.
- [ ] Tôi không coi metric Gateway routes là số đầy đủ của 401/403/404 trước routing.
- [ ] Tôi biết `rate`/`increase` xử lý counter reset và giữ đúng cửa sổ thời gian.
- [ ] Tôi có RPS theo route, 5xx ratio, status breakdown và P95/P99 có ý nghĩa.
- [ ] Tôi chỉ tính P95/P99 từ histogram buckets **được export thật**, không từ `_max`.
- [ ] Tôi kiểm tra time units seconds/ms và không cộng/trung bình percentiles sai cách.
- [ ] Tôi không dùng raw paths, userId, JWT, session, email, query hoặc requestId làm metric labels.
- [ ] Tôi kiểm soát cardinality của routeId, routeUri, histogram buckets và dynamic routes.
- [ ] Tôi có panel `up` và trạng thái **No data** riêng, không coi mất scrape là 0 lỗi.
- [ ] Tôi đo inbound và downstream attempts riêng khi bật Retry.
- [ ] Tôi quan sát 429/RateLimiter, breaker/fallback, cache hit/miss **khi đã instrument thật**.
- [ ] Tôi không mặc định mọi metrics Resilience4j/Redis/Netty đều có sẵn trên mọi version.
- [ ] Tôi theo dõi heap/direct memory, GC, CPU, connections và saturation theo stack.
- [ ] Tôi có dashboard by route/by instance và deployment annotations.
- [ ] Các alert có traffic guard, thời gian `for`, ngưỡng theo SLO và runbook có người chịu trách nhiệm.
- [ ] Tôi kiểm thử một backend 503, một 429, một request không match, một node scrape down và một case retry trong **lab**.
- [ ] Tôi có retention/series budget, data-source permissions và quy trình nâng cấp dashboard cùng phiên bản Gateway.
- [ ] Tôi duy trì logs/traces có correlation ID để điều tra hop chậm mà không đưa PII/credentials vào metrics.

## 21. Bài tập mở rộng

**Bài 1 — RPS và error budget.** Dùng PromQL hiển thị requests/s và 5xx ratio theo `routeId` trên cửa sổ 5 phút và 1 giờ. Giải thích vì sao route chưa có traffic nên hiển thị **No data**, không phải 0% errors.

**Bài 2 — Histogram.** Bật histogram cho `spring.cloud.gateway.requests`, gửi đủ nhiều requests lab, so P50/P95/P99. Dùng `sum by (le)` để tính toàn cluster và `sum by (le, routeId)` để tính per-route; giải thích vì sao không lấy trung bình hai P99 của hai pods.

**Bài 3 — Retry amplification.** Gửi một GET đến backend trả 503 hai lần rồi 200. Tạo counter outbound attempts ở đúng vị trí routing (hoặc dùng client metrics đã xác minh), so với Gateway routed requests. Trình bày điều gì xảy ra nếu đặt counter sai chỗ trong Retry filter chain.

**Bài 4 — Scrape failure.** Tắt một management endpoint ở lab rồi quan sát `up=0`; sau đó bỏ target khỏi discovery và quan sát **absence**. Đề xuất hai alert khác nhau, không tự đồng nhất hai tình huống.

**Bài 5 — Cardinality.** Tạo bộ dữ liệu test có 10.000 URL IDs nhưng chỉ một route ID chuẩn hóa. So số series khi bật/không bật raw path label. Không dùng IDs thật của người dùng hay token.

**Bài 6 — Cảnh báo có hành động.** Viết rule 5xx ratio > 2% trong 10 phút với traffic guard thích hợp cho một route giả định. Mô tả runbook: kiểm tra `up`, route ID, p99, downstream traces, rollout và quyết định rollback.

**Bài 7 — Dashboard review.** Gắn nhãn “Not instrumented” cho các panels breaker/cache/Redis chưa có metric. Bảo vệ Prometheus endpoint bằng network policy và xác minh Grafana vẫn truy vấn được Prometheus mà không cần lộ Actuator ra Internet.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — tìm **Gateway Metrics Filter**, **Actuator API** và **Server WebFlux/Server Web MVC** theo đúng phiên bản.
- [Spring Cloud Gateway Project](https://spring.io/projects/spring-cloud-gateway) — release train và tài liệu phù hợp.
- [Spring Boot Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — Micrometer, distribution histogram, tags và registry configuration.
- [Spring Boot Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — management endpoint exposure/security.
- [Micrometer Reference](https://docs.micrometer.io/micrometer/reference/) — counters, timers, histograms, meter names/tags và cardinality.
- [Prometheus — Getting Started](https://prometheus.io/docs/prometheus/latest/getting_started/) — scrape configuration và truy vấn cơ bản.
- [Prometheus — Querying Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/) — `rate`, `increase`, `histogram_quantile`.
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/) — `for`, labels và annotations.
- [Grafana — Dashboards](https://grafana.com/docs/grafana/latest/dashboards/) — panels, variables, templates và dashboard design.
- [Grafana — Prometheus Data Source](https://grafana.com/docs/grafana/latest/datasources/prometheus/) — cấu hình datasource và PromQL trong Grafana.

**Ghi nhớ:** Tích hợp Prometheus cho Spring Cloud Gateway không chỉ là bật `/actuator/prometheus`. Bạn phải **xác nhận metric và labels thực sự được export**, phân biệt **inbound requests – Gateway routed requests – downstream attempts**, dùng `rate` và **histogram buckets** để tính RPS, lỗi và P95/P99, rồi xây dashboard giúp điều tra **traffic, errors, latency, saturation**. Kiểm soát cardinality và bảo vệ management endpoint là yêu cầu bảo mật bắt buộc; một dashboard có giá trị khi những chỉ số của nó **đúng phạm vi, có thể kiểm chứng và dẫn đến hành động vận hành cụ thể**.
