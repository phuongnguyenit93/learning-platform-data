# Tách cổng quản trị và đánh giá quyền truy cập endpoint trong Spring Boot

## 1. Vấn đề cần giải quyết

Một ứng dụng Spring Boot thường có hai nhóm HTTP traffic:

- **Traffic nghiệp vụ:** khách hàng, frontend hoặc hệ thống khác gọi `/api/orders`, `/api/products`, đăng nhập, tải tài nguyên và thực hiện các chức năng được thiết kế cho người dùng.
- **Traffic vận hành:** Kubernetes, load balancer, Prometheus, hệ thống giám sát hoặc nhân sự vận hành cần xem `health`, `readiness`, `metrics`, `info`, `loggers`, `mappings` hay các Actuator endpoints khác.

Nếu đặt tất cả Actuator endpoints ở cổng public và expose rộng, hệ thống có thể làm lộ cấu hình, danh sách bean, routes, metrics chi tiết, thậm chí mở thao tác thay đổi trạng thái runtime. Nếu tách một cổng quản trị nhưng **không hạn chế người được phép kết nối và endpoint được expose**, rủi ro vẫn tồn tại.

Bài học tập trung vào hai mục tiêu:

1. **Tách mạng HTTP quản trị khỏi HTTP ứng dụng khi cần:** cấu hình `management.server.port`, bind address, base path, SSL và hiểu giới hạn của cổng riêng.
2. **Đánh giá quyền truy cập từng endpoint theo nhiều lớp:** tồn tại hay không, có expose qua HTTP hay không, ai có quyền gọi và response có để lộ thông tin nhạy cảm hay không.

Ví dụ chính dùng **Spring Boot 3.5.16, Spring Framework 6.2.x, Spring Security 6.x, Java 17+ và Maven**. Ứng dụng có cổng nghiệp vụ `8080`, cổng quản trị `9091` chỉ bind `127.0.0.1`, health có thể đọc không đăng nhập, metrics yêu cầu role `OPS` và các endpoint nhạy cảm như env/beans/loggers/mappings không được expose.

**Điểm mấu chốt:** *Tách cổng là một biện pháp giảm bề mặt tấn công, không phải cơ chế xác thực hoặc phân quyền.* Phải kết hợp network policy, HTTP exposure, actuator access controls, Spring Security và kiểm thử từ các đường mạng khác nhau.

## 2. Spring Boot Actuator là gì?

`spring-boot-starter-actuator` cung cấp các khả năng **quan sát và quản trị** của ứng dụng. Endpoint ID không phải nhất thiết là URL đầy đủ: web mapping mặc định là `/actuator/{id}`. Một số endpoint thông dụng:

| Endpoint ID | Ý nghĩa | Độ nhạy cảm và lưu ý |
| --- | --- | --- |
| `health` | Trạng thái sức khỏe ứng dụng, các health contributors | Có thể public ở mức tổng quan; hạn chế details |
| `info` | Metadata ứng dụng được cấu hình | Xem dữ liệu được đưa vào info |
| `metrics` | Danh sách metric và số đo Micrometer | Dùng cho người vận hành; có thể tiết lộ topology |
| `prometheus` | Metric exposition cho Prometheus | Cần dependency registry và kiểm soát scraper |
| `httpexchanges` | Các HTTP request/response gần đây | Cần repository; có thể nhạy cảm |
| `mappings` | Danh sách các request mappings | Tiết lộ routes/endpoints |
| `beans` | Các bean trong Spring context | Tiết lộ kiến trúc runtime |
| `conditions` | Auto-configuration conditions | Thông tin vận hành nội bộ |
| `configprops` | Giá trị configuration properties | Có sanitization; vẫn có thể nhạy cảm |
| `env` | Environment properties | Có sanitization nhưng rất nhạy cảm |
| `loggers` | Xem và có thể chỉnh log levels | Có operations thay đổi cấu hình runtime |
| `threaddump` | Thread dump | Có thể chứa trạng thái và thông tin nội bộ |
| `heapdump` | Heap dump | Rất nhạy cảm, có thể chứa secrets và dữ liệu người dùng |
| `shutdown` | Tắt ứng dụng có kiểm soát | Bị vô hiệu mặc định; không mở ra Internet |

Không phải mọi ID đều tự hoạt động khi thêm Actuator. Một số endpoint cần dependency riêng, bean bổ sung hoặc access/exposure phù hợp. Ví dụ `prometheus` cần `micrometer-registry-prometheus`; `httpexchanges` cần `HttpExchangeRepository`. Việc **có Actuator trên classpath** không đồng nghĩa đã tạo và expose tất cả endpoints.

### 2.1. Default có lợi cho bảo mật

Trong **Spring Boot 3.5**, mặc định chỉ endpoint `health` được expose qua HTTP; Actuator **không** tự mở `env`, `beans`, `heapdump` hoặc `loggers` ra mạng. Nếu Spring Security có trên classpath và **không có custom `SecurityFilterChain` bean**, Boot auto-configure bảo vệ các Actuator endpoints trừ health.

Nhưng khi ứng dụng **tự định nghĩa `SecurityFilterChain`**, cấu hình bảo mật mặc định của Boot nhường quyền. Bạn phải tự kiểm tra lại **cả Actuator lẫn API ứng dụng**, tránh nghĩ rằng thêm `spring-boot-starter-security` là đủ.

### 2.2. Hai kiểu observability khác nhau

- **Read-only monitoring**: health, readiness, metrics. Thường tự động được scraper/liveness probe truy vấn.
- **Operations/management**: thay đổi log level, lấy dumps, shutdown, xem env/beans, trigger hành động. Cần kiểm soát chặt hơn nhiều; không nên có mặt chỉ vì “cần xem metrics”.

Tách hai use cases giúp cấp quyền tối thiểu. Có thể chỉ expose `health,metrics` và không cho phép bất kỳ operation thay đổi trạng thái nào.

## 3. Ba lớp kiểm soát độc lập: access, exposure và security

Spring Boot Actuator 3.5 có **khái niệm access level của endpoint** bên cạnh exposure. Khi phân tích một URL, cần kiểm tra cả ba:

1. **Endpoint access (`management.endpoint.<id>.access`)**: endpoint/operations có được cho phép tồn tại hay không; có thể là `none`, `read-only`, `unrestricted`.
2. **Exposure (`management.endpoints.web.exposure.include/exclude`)**: endpoint đã được phép có được xuất hiện qua **HTTP** không? JMX có exposure policy riêng.
3. **HTTP authentication/authorization (Spring Security, proxy, firewall)**: request tới endpoint đã exposed có được caller thực hiện không? Có thể cho phép health anonymous và yêu cầu role OPS cho metrics.

Sơ đồ:

```text
Request GET /actuator/metrics
          |
          v
Actuator endpoint access policy
      (metrics: read-only?)
          |
          v
HTTP exposure list
      (metrics included?)
          |
          v
Network route / listener / firewall
      (management port reachable?)
          |
          v
Spring Security / proxy authorization
      (caller has ROLE_OPS?)
          |
          v
     Response metrics
```

Sơ đồ là mô hình **logic của các điều kiện**, không khẳng định các filter chạy theo thứ tự implementation đúng như hình. Việc Actuator endpoint không tồn tại vì access=none có thể dẫn tới `404`; endpoint được expose nhưng caller không đăng nhập có thể trả `401`, còn đã đăng nhập nhưng thiếu quyền có thể trả `403`. Đôi khi proxy hoặc SecurityFilterChain phản hồi trước khiến status khác, vì vậy phải đối chiếu log và security configuration.

### 3.1. Access level (Boot 3.5)

```properties
management.endpoints.access.default=none
management.endpoint.health.access=read-only
management.endpoint.metrics.access=read-only
```

Cấu hình này chọn phương pháp **opt-in**: các endpoint mặc định không được cấp quyền access, chỉ health và metrics được cấp quyền đọc. `read-only` cho phép read operations; các thao tác ghi/thay đổi không được phép.

Ngoài ra có thể đặt giới hạn toàn ứng dụng:

```properties
management.endpoints.access.max-permitted=read-only
```

Property này giới hạn mức truy cập cao nhất; không thể cấp `unrestricted` thực sự nếu global max-permitted chỉ là read-only. Với Boot 3.5, `none` làm endpoint không còn tồn tại trong application context, không giống việc chỉ HTTP 403.

**Phân biệt với phiên bản khác:** property group/access levels là tính năng của Boot 3.4+ và có trong Boot 3.5. Không áp dụng nguyên `management.endpoints.access.default` cho dự án Boot 2.x quá cũ nếu metadata của nó không hỗ trợ.

### 3.2. Web exposure

```properties
management.endpoints.web.exposure.include=health,metrics
```

Chỉ health và metrics được đưa ra HTTP. Dù `management.endpoint.env.access=unrestricted`, nếu `env` **không được expose**, bạn vẫn không thể gọi `/actuator/env` qua HTTP.

Cẩn thận với cấu hình:

```properties
management.endpoints.web.exposure.include=*
```

Đây là **ví dụ cấu hình nguy hiểm nếu không kiểm soát**, không dùng trong bài demo chính. Nó cố gắng expose mọi endpoint được phép và được tạo; `management.endpoints.web.exposure.exclude` có precedence cao hơn `include`. Đừng dựa vào danh sách exclude vài endpoint rồi quên các endpoint mới xuất hiện khi nâng phiên bản.

### 3.3. Spring Security

Trong custom `SecurityFilterChain`, có thể dùng matcher của Boot:

```java
http.securityMatcher(EndpointRequest.toAnyEndpoint())
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(EndpointRequest.to(HealthEndpoint.class))
        .permitAll()
        .anyRequest().hasRole("OPS"))
    .httpBasic(Customizer.withDefaults());
```

Đây là **snippet**, xem tệp hoàn chỉnh ở mục 9. `EndpointRequest.toAnyEndpoint()` chỉ match các **Actuator endpoints**, không phải “mọi request đi vào management port”. Một URL không thuộc Actuator trên management port có thể rơi xuống filter chain khác, nên đừng giả định matching theo **port** khi bạn chỉ cấu hình matcher theo **endpoint**.

### 3.4. Bảng kết quả quyền truy cập

| Access | Exposed HTTP? | Security | Kết quả hợp lý |
| --- | --- | --- | --- |
| `none` | Bất kỳ | Bất kỳ | Endpoint không được tạo; URL không có endpoint hợp lệ |
| `read-only` | Không | Bất kỳ | Không gọi được qua HTTP; có thể tồn tại qua kênh khác nếu expose riêng |
| `read-only` | Có | Permit anonymous | Có thể GET/HEAD nếu operation phù hợp |
| `read-only` | Có | Require OPS | 401 khi chưa xác thực, 403 nếu thiếu role, 200 nếu OPS hợp lệ |
| `unrestricted` | Có | Require OPS | Có thể gọi operations kể cả ghi **nếu endpoint hỗ trợ**, không nên cấp tùy tiện |
| `unrestricted` | Có | Không có network ACL | Có thể bị truy cập từ mạng ngoài nếu endpoint reachable |
| `read-only` | Có | Firewall chỉ monitoring CIDR | Hạn chế mạng, nhưng vẫn cần security để phòng ngừa bypass |

**Một lớp kiểm soát không thay hai lớp còn lại.** Port riêng không làm một endpoint khác tự thành private; role OPS không bảo vệ được khi application security matchers permitAll nhầm đường dẫn.

## 4. Tách cổng management khỏi cổng ứng dụng

### 4.1. Cấu hình tối thiểu

```properties
server.port=8080
management.server.port=9091
```

Ứng dụng bình thường lắng nghe ở `8080`; Actuator HTTP endpoints ở `9091` nếu Actuator được cấu hình. Spring Boot tạo **management web application context riêng** khi dùng một management port khác, có web server/dispatcher riêng cho management.

Ví dụ:

```text
Client
    |
    +-----> :8080 (main application)
    |           /api/ping
    |           /api/orders
    |
    +-----> :9091 (management context)
                /actuator/health
                /actuator/metrics
```

Khi đã tách, không kỳ vọng `http://localhost:8080/actuator/metrics` vẫn được đăng ký trên main port. Tuy nhiên **một số additional health paths** có thể được chủ ý đưa về main port, trình bày ở mục 7.

### 4.2. Chỉ bind management vào loopback

```properties
management.server.port=9091
management.server.address=127.0.0.1
```

Spring Boot chỉ cho đặt management bind address **khác** main server khi management port thật sự khác. Với local machine, `127.0.0.1` cho phép kết nối từ cùng network namespace, **không** cho remote host truy cập trực tiếp qua public IP.

Nhưng trong Docker/Kubernetes, loopback bên trong container/pod có nghĩa khác. Prometheus bên ngoài pod thường **không** kết nối được tới `127.0.0.1` của container, trừ khi có sidecar/forwarding/port-forward phù hợp. Nếu metrics cần scrape từ monitoring namespace, có thể bind vào pod interface và bảo vệ bằng **NetworkPolicy, firewall, security groups, mTLS và auth** thay vì mở public.

### 4.3. Management cổng riêng không phải bảo đảm cách ly tuyệt đối

- Hai listeners vẫn có thể cùng JVM/process, chia sẻ heap, GC, business state và nhiều dependencies.
- Management health có thể 200 trong khi main servlet thread pool bị nghẽn, nên chỉ kiểm tra management port có thể **bỏ sót lỗi main listener**.
- Nếu firewall/ingress vô tình publish 9091, endpoint vẫn reachable từ bên ngoài.
- Nếu reverse proxy forward `/actuator/**` công khai tới 9091, việc management bind nội bộ chỉ bảo vệ trước proxy, không bảo vệ path proxy đã mở.
- Đặt management trên port khác không thay thế TLS, role-based authorization và audit logs.

### 4.4. Tắt HTTP management endpoints

Nếu không cần management HTTP listener:

```properties
management.server.port=-1
```

Hoặc giữ listener nhưng không expose endpoint:

```properties
management.endpoints.web.exposure.exclude=*
```

Hai lựa chọn **không đồng nhất**: `port=-1` tắt web management HTTP; `exclude=*` không expose các endpoint qua HTTP nhưng các kênh/thiết lập khác còn tùy cấu hình. Đừng dùng `management.server.port=-1` nếu deployment vẫn yêu cầu Actuator liveness/readiness HTTP.

## 5. Đường dẫn management: base path và context path

### 5.1. Base path mặc định

```properties
management.endpoints.web.base-path=/actuator
```

Nếu management dùng **cùng port với ứng dụng Servlet**, path này thường tương đối với `server.servlet.context-path`. Ví dụ:

```properties
server.port=8080
server.servlet.context-path=/shop
management.endpoints.web.base-path=/actuator
```

URL health khi **chưa tách cổng** có thể là `http://localhost:8080/shop/actuator/health`.

### 5.2. Khi management port khác

```properties
server.port=8080
server.servlet.context-path=/shop

management.server.port=9091
management.server.base-path=/ops
management.endpoints.web.base-path=/actuator
```

Cổng chính có route dưới `/shop`. Cổng management có Actuator URL `http://localhost:9091/ops/actuator/health` — **không** mặc nhiên là `/shop/ops/actuator/health`. Tài liệu Boot 3.5 nêu rõ `management.endpoints.web.base-path` được tính tương đối với `management.server.base-path` khi management port riêng.

Không đồng nhất:

| Property | Phạm vi | Ví dụ |
| --- | --- | --- |
| `server.servlet.context-path` | Main Servlet app | `/shop` |
| `management.server.port` | Management listener | `9091` |
| `management.server.base-path` | Management web context, khi port riêng | `/ops` |
| `management.endpoints.web.base-path` | Prefix endpoint URLs | `/actuator` |
| `management.endpoints.web.path-mapping.health` | Đổi tên path của riêng health | `healthcheck` |

### 5.3. Tùy biến đường dẫn không phải bảo mật

Đổi `/actuator` sang `/admin` hoặc `/monitor` chỉ là **URL routing**. Không phải credential hay network ACL. Scanner có thể tìm được endpoint, và proxy còn có thể map ngược.

```properties
management.endpoints.web.base-path=/manage
management.endpoints.web.path-mapping.health=healthcheck
```

Tùy có `management.server.base-path`, health sẽ xuất hiện tại `/manage/healthcheck` hoặc `/ops/manage/healthcheck`. Với security policy, ưu tiên `EndpointRequest` hơn hardcode chỉ một chuỗi `/actuator/**` nếu dự án có thể đổi base path.

## 6. TLS và network policy cho cổng quản trị

### 6.1. SSL riêng khi management port khác

Spring Boot cho cấu hình SSL management qua `management.server.ssl.*` khi management có **port riêng**. Ví dụ main HTTPS và management HTTPS dùng certificates khác nhau (minh họa, cần tệp đã cung cấp):

```properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=file:/run/secrets/main.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${MAIN_KEYSTORE_PASSWORD}

management.server.port=9443
management.server.ssl.enabled=true
management.server.ssl.key-store=file:/run/secrets/management.p12
management.server.ssl.key-store-type=PKCS12
management.server.ssl.key-store-password=${MANAGEMENT_KEYSTORE_PASSWORD}
```

Ở đây không có certificate được tạo sẵn trong tài liệu; đây là **fragment production-style, không copy để chạy demo**. Bạn cần certificate/hostname/trust chain đúng, secret store và renewal. Spring Boot hỗ trợ SSL bundles; nếu dùng bundle, cấu hình theo đúng version và không trộn tùy tiện với các discrete key-store properties.

### 6.2. Management HTTP local

Trong project demo, management bind `127.0.0.1:9091` và dùng HTTP **chỉ cho local development**. Không gửi Basic credentials qua HTTP ở mạng không tin cậy vì Basic credentials chỉ được mã hóa Base64, không có bảo mật transport.

Trong production, bảo vệ management bằng **HTTPS/mTLS nếu đi qua mạng**, và dùng một trong những chiến lược:

- Scraper sidecar cùng pod/host truy cập loopback.
- Monitoring service trong private network được NetworkPolicy/ACL giới hạn.
- Proxy nội bộ có mTLS, auth và IP allowlist, không public route quản trị.
- Port-forward có xác thực/ghi audit chỉ khi xử lý sự cố.

Không mở `9091` ở load balancer public chỉ vì đã bật Spring Security. Defense-in-depth yêu cầu **network segmentation + authentication + authorization + endpoint minimization**.

### 6.3. Kiểm tra network thực

Trên host local Linux/macOS:

```bash
curl -i http://127.0.0.1:9091/actuator/health
```

Một kết nối tới địa chỉ public của máy có thể **không vào được** management listener nếu bind đúng loopback. Nhưng không được tuyên bố Internet không truy cập được nếu chưa kiểm tra port publication của Docker, firewall/SG, Ingress và proxy.

Lưu ý port mapping của Docker `-p 9091:9091` không làm một listener bind chỉ `127.0.0.1` bên trong container trở thành reachable từ mọi host. Muốn Prometheus scrape qua network cần cấu hình listener và policy đúng, không chỉ publish port.

## 7. Health, liveness, readiness và cổng ứng dụng

### 7.1. Health tổng quan

`GET /actuator/health` có thể trả:

```json
{"status":"UP"}
```

Đây là response đơn giản khi ứng dụng và health contributors đều khỏe. Status có thể là `DOWN`/`OUT_OF_SERVICE` và HTTP status có thể 503 theo mapping mặc định; không giả định `200` trong mọi tình trạng.

`management.endpoint.health.show-details=never` giúp tránh trả details về DB, disk, service names và stack information cho người không được phép. Spring Boot 3.5 cho các mức `never`, `when-authorized` và `always`. Trong production, ưu tiên `never` hoặc `when-authorized` với role cụ thể; không mở `always` công khai.

### 7.2. Liveness khác readiness

- **Liveness**: tiến trình ứng dụng có còn ở trạng thái hoạt động mà restart có thể giúp không? Không nên phụ thuộc DB/Redis/downstream để tránh restart tất cả replicas khi dịch vụ chung bị lỗi.
- **Readiness**: instance hiện có thể nhận traffic nghiệp vụ không? Có thể kiểm tra thêm một số điều kiện cần, nhưng cần cân nhắc tác động nếu phụ thuộc external services.
- **Startup**: ứng dụng khởi động dài có thể cần Kubernetes `startupProbe`, tránh bị liveness kill quá sớm.

Spring Boot 3.5 hỗ trợ các health groups `liveness` và `readiness` qua `ApplicationAvailability`, ví dụ:

```text
/actuator/health/liveness
/actuator/health/readiness
```

Ở môi trường không phải Kubernetes, có thể bật rõ ràng:

```properties
management.endpoint.health.probes.enabled=true
```

### 7.3. Vì sao chỉ probe management port chưa đủ?

Khi management và main app chạy trên hai web server/context khác nhau, `9091` vẫn có thể trả `UP` trong khi main port `8080` không nhận request do thread pool bão hòa hoặc connector gặp lỗi. Tài liệu Spring Boot khuyến nghị cân nhắc **additional probe paths trên main server port**:

```properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
```

Kết quả:

- Management port: `/actuator/health/liveness`, `/actuator/health/readiness`.
- **Main port:** `/livez` và `/readyz` (theo default additional paths).

Các additional paths giúp kiểm tra tầng web listener chính nhưng **không tự chứng minh mọi endpoint, DB và business use case đều ổn**. Phải giám sát lỗi/latency thực của API.

### 7.4. Kubernetes probes mẫu

Với app chính ở 8080 và đã bật additional paths:

```yaml
livenessProbe:
  httpGet:
    path: /livez
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10
readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
```

Đây là **fragment container spec** nằm bên trong Kubernetes Pod/Deployment container definition, không phải YAML manifest độc lập. Timings chỉ là ví dụ; cần đánh giá thời gian khởi động, timeout/failureThreshold theo SLO.

Nếu ứng dụng có `server.servlet.context-path=/shop`, phải kiểm tra URL thực của additional paths tương ứng, không sao chép `/livez` của demo mặc định khi context path đã thay. Với liveness của Kubernetes, không đặt dependency DB chung vào liveness check vì có thể gây cascading restarts.

### 7.5. Đánh giá endpoint health trả bao nhiêu chi tiết

| Caller | Dữ liệu nên thấy | Gợi ý |
| --- | --- | --- |
| Internet/public LB | Up/down tối thiểu nếu bắt buộc cần | Không tiết lộ components, internal hostnames |
| Kubelet | Liveness/readiness status | Additional paths ở main port |
| Prometheus scraper | Metrics được phép | Chỉ monitoring network và credentials hợp lệ |
| SRE/ops | Metrics chi tiết, logs theo quyền | Role-based access + audit |
| Người dùng sản phẩm | Business API | Không cần các management internals |

Health “UP” không phải giấy chứng nhận bảo mật; nó là một chỉ báo khả dụng theo các checks đã cấu hình.

## 8. Thiết kế phân quyền endpoint theo nhu cầu

### 8.1. Một access matrix có thể audit

| Endpoint/path | Caller | Quyền mong muốn | Lý do |
| --- | --- | --- | --- |
| `GET :8080/api/ping` | Không đăng nhập | `200` | Demo public health-like app route |
| `GET :9091/actuator/health` | Không đăng nhập trên localhost | `200` khi UP | Health status tối thiểu |
| `GET :9091/actuator/metrics` | Không đăng nhập | `401` | Chỉ ops đọc metrics |
| `GET :9091/actuator/metrics` | User role OPS | `200` | Authorized operator |
| `GET :9091/actuator/env` | Kể cả ops | Không phải endpoint exposed | Không cấp do dữ liệu nhạy cảm |
| `GET :9091/actuator/beans` | Kể cả ops | Không exposed | Giảm bề mặt tấn công |
| `GET :9091/actuator/heapdump` | Kể cả ops | Không enabled/exposed | Memory có thể chứa secrets |
| `POST :9091/actuator/loggers/...` | Kể cả ops | Không enabled/exposed | Tránh thay runtime logging |
| `GET :8080/actuator/metrics` | Kể cả ops | Không 200 | Actuator nằm ở management port |
| `GET :8080/livez`, `/readyz` | Kubelet/giám sát | `200` khi healthy | Kiểm tra main listener |

Đây là access matrix **cho project demo**, không phải quyền mặc định của mọi ứng dụng. Khi điều chỉnh URL, role, security chain hoặc proxy, phải cập nhật tests.

### 8.2. Ba phép thử phân biệt lỗi

- **401 Unauthorized**: endpoint exposed nhưng thiếu xác thực. Với Basic có thể có `WWW-Authenticate: Basic`.
- **403 Forbidden**: caller đã được xử lý nhưng không được phép; cũng có thể do CSRF trên unsafe requests, WAF/proxy hoặc policy khác.
- **404 Not Found**: endpoint không tồn tại/không exposed/không có mapping; cũng có thể bị security chain trả response khác trước khi router kịp trả 404.

Không suy ra “404 = secure tuyệt đối”. Một route 404 qua public listener có thể vẫn tồn tại qua private listener hoặc JMX, nếu configuration cho phép.

### 8.3. HTTP basic chỉ là phương tiện demo

Trong ví dụ có user `ops` và role `OPS`, password đọc từ environment. Basic auth qua **loopback HTTP local** để học cách tạo `401/200`; production nên dùng TLS/mTLS và cơ chế identity có quản lý. Không hardcode password, không gửi token/password vào log/chat, không dùng `permitAll` cho metrics khi cổng public reachable.

## 9. Demo đầy đủ: Spring Boot 3.5.16 với main 8080 và management 9091

### 9.1. Cấu trúc

```text
management-boundary-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/management/
    │   │   ├── ManagementBoundaryApplication.java
    │   │   ├── PingController.java
    │   │   └── SecurityConfiguration.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/management/
            └── ManagementPortTest.java
```

Project chạy **Spring MVC** trên embedded Tomcat. Tách management port được Boot/Actuator tự cấu hình, không tự viết Tomcat connector.

### 9.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>management-boundary-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Với starter Actuator và Spring Security, `EndpointRequest` matcher và `HealthEndpoint` có mặt. `starter-test` chứa JUnit/TestRestTemplate cho HTTP integration tests. Không cần thêm Jersey/WebFlux hay Prometheus dependency vào demo vì chỉ dùng built-in `metrics` endpoint; khi cần `/actuator/prometheus` mới thêm registry riêng.

### 9.3. Main class

Tệp `src/main/java/com/example/management/ManagementBoundaryApplication.java`:

```java
package com.example.management;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ManagementBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(ManagementBoundaryApplication.class, args);
    }
}
```

### 9.4. Business endpoint

Tệp `src/main/java/com/example/management/PingController.java`:

```java
package com.example.management;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class PingController {

    @GetMapping("/ping")
    public Map<String, String> ping() {
        return Map.of("message", "pong");
    }
}
```

Route ở **main port**: `http://localhost:8080/api/ping` trả JSON `{"message":"pong"}` nếu app khỏe. Không phải Actuator endpoint. Đây là business route đơn giản để so sánh đường mạng.

### 9.5. Security configuration với hai filter chains

Tệp `src/main/java/com/example/management/SecurityConfiguration.java`:

```java
package com.example.management;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http)
            throws Exception {
        return http
                .securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                EndpointRequest.to(HealthEndpoint.class))
                        .permitAll()
                        .anyRequest().hasRole("OPS"))
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/ping").permitAll()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            @Value("${demo.ops.password}") String password,
            PasswordEncoder encoder) {
        UserDetails ops = User.withUsername("ops")
                .password(encoder.encode(password))
                .roles("OPS")
                .build();
        return new InMemoryUserDetailsManager(ops);
    }
}
```

**Cách đọc cấu hình:**

- `@Order(1)` xét Actuator matcher trước: `health` công khai, các endpoint khác cần `ROLE_OPS`.
- `EndpointRequest.toAnyEndpoint()` match **Actuator endpoint mappings**, bao gồm links và additional health paths khi phù hợp; **không match mọi URL chỉ vì nằm trên port 9091**.
- `@Order(2)` là fallback cho application requests: `/api/ping` public, còn lại denyAll. Đây là policy **thu hẹp cho demo**, không phải luật cho hệ thống bán hàng thật.
- Hai chains **không tự là hai port-specific chains**. Cơ chế lựa chọn dựa matcher. Một unknown path trên management listener có thể đi qua application chain; cần kiểm tra status thật, không dự đoán mọi unknown path sẽ 404.
- Spring Boot auto security backing off khi bạn tạo custom `SecurityFilterChain`, vì vậy phải khai báo cả rule cho app như ví dụ.
- `BCryptPasswordEncoder` hash password lưu trong memory khi app startup, tránh lưu password plain trong user store. Dù vậy **Basic auth header trên HTTP vẫn có thể bị nhìn thấy** nếu đường truyền không mã hóa; chỉ dùng trên loopback demo.
- `User.withUsername(...).roles("OPS")` tạo authority `ROLE_OPS`; với `hasRole("OPS")` là đúng. Không dùng `hasRole("ROLE_OPS")` gây lặp prefix.

**CSRF:** ví dụ chỉ có GET/HEAD read operations, giữ cấu hình CSRF mặc định. Khi expose operations POST/PUT/DELETE như `loggers` hoặc `shutdown`, CSRF/authorization cần đánh giá riêng; không tắt CSRF toàn cục chỉ để vượt một HTTP 403.

### 9.6. `application.properties` hoàn chỉnh

Tệp `src/main/resources/application.properties`:

```properties
spring.application.name=management-boundary-demo

# Main application listener
server.port=8080

# Management listener riêng, local-only cho demo
management.server.port=9091
management.server.address=127.0.0.1

# Actuator web path: /actuator/{id}
management.endpoints.web.base-path=/actuator

# Opt-in: chỉ cho tồn tại các read-only endpoints đã chọn
management.endpoints.access.default=none
management.endpoint.health.access=read-only
management.endpoint.metrics.access=read-only
management.endpoints.access.max-permitted=read-only

# Chỉ expose hai endpoints qua HTTP
management.endpoints.web.exposure.include=health,metrics

# Không công khai health details
management.endpoint.health.show-details=never

# Probe paths trên management, và /livez /readyz tại main port
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true

# Bắt buộc lấy password từ environment; không có fallback production
demo.ops.password=${OPS_PASSWORD}
```

**Không có mật khẩu thật trong file.** Nếu `OPS_PASSWORD` chưa được cấu hình, startup có thể thất bại vì placeholder không resolve; đó là chủ đích. Cần đặt password từ environment khi chạy; demo chỉ dùng một in-memory user, không phải mô hình quản trị production.

**Quan trọng:** `management.server.address=127.0.0.1` nghĩa metrics listener chỉ nhận traffic loopback tại máy/process network namespace hiện tại. Nếu chạy trên cluster, kiểm tra khả năng scraping trước khi copy cấu hình này.

### 9.7. Build và chạy ở local

Với Bash/Linux/macOS:

```bash
export OPS_PASSWORD='local-example-secret-only'
mvn clean package
java -jar target/management-boundary-demo-1.0.0.jar
```

Với PowerShell:

```powershell
$env:OPS_PASSWORD = 'local-example-secret-only'
mvn clean package
java -jar target/management-boundary-demo-1.0.0.jar
```

Thực thi trong thư mục có `pom.xml`, JDK 17+ và Maven. Ports 8080, 9091 phải rảnh. Lệnh chạy chỉ là ví dụ development; giá trị `local-example-secret-only` **không phải production secret**. Với hệ thống thật, dùng secret manager và không đặt password trong shell history.

### 9.8. Kiểm tra business route trên main port

```bash
curl -i http://127.0.0.1:8080/api/ping
```

Khi thành công:

```http
HTTP/1.1 200
Content-Type: application/json

{"message":"pong"}
```

Đây là response rút gọn; headers có thể bổ sung `Cache-Control`, `X-Content-Type-Options` và các giá trị khác tùy Spring Security/server. Thứ tự JSON keys không phải vấn đề ở đây.

### 9.9. Health public trên management port

```bash
curl -i http://127.0.0.1:9091/actuator/health
```

Khi ứng dụng khỏe, response tiêu biểu:

```http
HTTP/1.1 200
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
```

`Content-Type` có thể có parameters hoặc khác theo Accept/content negotiation; điều quan trọng là status và body. Nếu application health DOWN, HTTP có thể trả 503. Health được permitAll ở chain Actuator, nhưng **chỉ reachable từ loopback** do management bind address.

### 9.10. Metrics yêu cầu role OPS

Không có credential:

```bash
curl -i http://127.0.0.1:9091/actuator/metrics
```

Kỳ vọng **HTTP 401 Unauthorized**, thường kèm `WWW-Authenticate: Basic`. Client chưa đăng nhập nên không được đọc danh sách metric names/measurements.

Gửi Basic credentials tương tác, để curl hỏi password thay vì để trong command line:

```bash
curl --user ops -i http://127.0.0.1:9091/actuator/metrics
```

Nhập password của `OPS_PASSWORD` khi được hỏi. Kết quả thành công là **HTTP 200** và JSON có danh sách `names`, chẳng hạn một số metrics JVM/HTTP tùy runtime. **Không cam kết toàn bộ metric names** vì classpath/traffic/config khác nhau.

Trong production không dùng Basic qua HTTP. Với TLS, endpoint có thể là `https://...` và certificate phải được verify đúng.

### 9.11. Endpoint nhạy cảm không được expose

```bash
curl -i http://127.0.0.1:9091/actuator/env
curl -i http://127.0.0.1:9091/actuator/beans
curl -i http://127.0.0.1:9091/actuator/loggers
curl -i http://127.0.0.1:9091/actuator/shutdown
```

Các URL này **không có handler Actuator được expose trong demo**. Do fallback SecurityFilterChain, response có thể là `403` thay vì `404`; tiêu chí QA là **không được trả 200 dữ liệu và không được thực thi thao tác quản trị**, kể cả khi thêm credentials OPS. Không dùng mỗi một HTTP status code để khẳng định endpoint được vô hiệu hóa nếu custom security/filter có thể trả trước.

### 9.12. Kiểm tra không lẫn hai ports

```bash
curl -i http://127.0.0.1:8080/actuator/metrics
curl -i http://127.0.0.1:9091/api/ping
```

Cả hai **không** phải URL hợp lệ để lấy nội dung tương ứng. Endpoint metrics chỉ nằm trên management context và business controller chỉ ở main app. Do fallback security, response đối với URL sai có thể là 401/403/404; **không xem là phép thử chỉ 404**.

### 9.13. Additional probes trên main port

```bash
curl -i http://127.0.0.1:8080/livez
curl -i http://127.0.0.1:8080/readyz
curl -i http://127.0.0.1:9091/actuator/health/liveness
curl -i http://127.0.0.1:9091/actuator/health/readiness
```

Khi app healthy/ready, cả bốn endpoint trả thành công với dữ liệu health theo group. Liveness/readiness có thể DOWN/503 trong các trạng thái khởi động, dừng hoặc lỗi được nhận diện. Lý do xuất hiện `/livez` và `/readyz` trên main port là `management.endpoint.health.probes.add-additional-paths=true`, **không** phải vì Actuator vô tình bị expose toàn bộ ở main port.

## 10. Kiểm thử HTTP thực với hai ports ngẫu nhiên

Test dưới đây kiểm tra quyền truy cập trên **hai listeners riêng** thay vì chỉ MockMvc. `MockMvc` chủ yếu chạy Spring MVC filter/controller pipeline, không chứng minh management web server thứ hai thực sự được bind và accessible.

Tệp `src/test/java/com/example/management/ManagementPortTest.java`:

```java
package com.example.management;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "management.server.port=0",
                "management.server.address=127.0.0.1",
                "demo.ops.password=test-only-secret"
        })
class ManagementPortTest {

    @LocalServerPort
    int appPort;

    @LocalManagementPort
    int managementPort;

    @Autowired
    TestRestTemplate http;

    private String app(String path) {
        return "http://127.0.0.1:" + appPort + path;
    }

    private String mgmt(String path) {
        return "http://127.0.0.1:" + managementPort + path;
    }

    @Test
    void mainBusinessRouteWorks() {
        ResponseEntity<String> result =
                http.getForEntity(app("/api/ping"), String.class);
        assertEquals(HttpStatus.OK, result.getStatusCode());
        assertTrue(result.getBody().contains("pong"));
    }

    @Test
    void healthAllowsAnonymousOnManagementPort() {
        ResponseEntity<String> result =
                http.getForEntity(
                        mgmt("/actuator/health"), String.class);
        assertEquals(HttpStatus.OK, result.getStatusCode());
        assertTrue(result.getBody().contains("UP"));
    }

    @Test
    void metricsRequireOpsAuthentication() {
        String url = mgmt("/actuator/metrics");

        ResponseEntity<String> anonymous =
                http.getForEntity(url, String.class);
        assertEquals(HttpStatus.UNAUTHORIZED,
                     anonymous.getStatusCode());

        ResponseEntity<String> ops =
                http.withBasicAuth("ops", "test-only-secret")
                    .getForEntity(url, String.class);
        assertEquals(HttpStatus.OK, ops.getStatusCode());
        assertTrue(ops.getBody().contains("names"));
    }

    @Test
    void sensitiveEndpointIsNotReadableEvenWithOps() {
        ResponseEntity<String> result =
                http.withBasicAuth("ops", "test-only-secret")
                    .getForEntity(
                            mgmt("/actuator/env"), String.class);
        assertNotEquals(HttpStatus.OK, result.getStatusCode());
    }

    @Test
    void metricsAreNotExposedOnMainPort() {
        ResponseEntity<String> result =
                http.withBasicAuth("ops", "test-only-secret")
                    .getForEntity(
                            app("/actuator/metrics"), String.class);
        assertNotEquals(HttpStatus.OK, result.getStatusCode());
    }

    @Test
    void livenessAlsoChecksMainWebListener() {
        ResponseEntity<String> result =
                http.getForEntity(app("/livez"), String.class);
        assertEquals(HttpStatus.OK, result.getStatusCode());
    }
}
```

### 10.1. Vì sao test cần `@LocalManagementPort`?

- `@SpringBootTest(webEnvironment=RANDOM_PORT)` chọn **main port ngẫu nhiên**.
- `management.server.port=0` làm **management port ngẫu nhiên**, tránh xung đột cổng 9091 khi chạy CI.
- `@LocalServerPort` và `@LocalManagementPort` lấy đúng số port sau startup. Hai số thường khác nhau.
- `TestRestTemplate` gửi HTTP qua TCP tới từng listener; security filters, session và management context được xử lý thật.
- Test `env` chỉ yêu cầu **not 200**, vì endpoint access=none và không expose, còn fallback security có thể làm status cụ thể khác.
- Test `metricsRequireOpsAuthentication` xác minh cả positive và negative authorization cho metrics.
- Password test `test-only-secret` là giá trị cố định **trong test context**, không dùng cho môi trường thật.

Chạy tại thư mục có POM:

```bash
mvn test
```

Đây là một mẫu smoke/integration test; để đánh giá security đầy đủ nên kiểm tra thêm role sai, HTTP methods không hợp lệ, inbound gateway, TLS, NetworkPolicy, rate limits và audit logs.

### 10.2. Test thêm một user không có OPS role

Với hệ thống thật, có thể dùng Spring Security test user hoặc identity test provider để tạo người dùng thường (role USER). Cần xác nhận người đó nhận **403 Forbidden** khi gọi metrics sau khi xác thực, thay vì chỉ có case anonymous 401 và OPS 200. Project tối giản chỉ định nghĩa duy nhất user ops để không cần thiết lập identity backend phức tạp.

Đây là ví dụ yêu cầu test bổ sung, không phải tuyên bố code đang có user thường.

## 11. Đánh giá security cho cổng quản trị trong production

### 11.1. Threat model

Khi mở management endpoints, cần đánh giá ít nhất:

- **External attacker** tìm endpoint `/actuator`, brute-force credentials, khai thác misconfiguration.
- **Compromised workload** trong cùng private subnet có thể truy cập port 9091 nếu network policy quá rộng.
- **Insider** có quyền monitoring nhưng không nên xem env/heapdump/shutdown.
- **Service account / scraper** cần metrics/health nhưng không cần quyền chỉnh log level.
- **Reverse proxy/Ingress** vô tình publish đường dẫn quản trị hoặc strip auth headers.
- **Supply-chain vulnerability** làm Actuator/runtime library cần cập nhật patch.
- **Sensitive data leakage** qua `env`, `configprops`, `beans`, `mappings`, `logfile`, `heapdump`, `httpexchanges`, high-cardinality metric tags.
- **Denial of service** bằng requests đắt tiền như thread dump/heap dump hoặc scrape metrics tần suất quá cao.

Định nghĩa security principal, network source, endpoint ID, allowed operation và retention/audit policy theo từng role.

### 11.2. Nguyên tắc cấp quyền tối thiểu

**Mẫu phân vai:**

| Vai trò | Nhu cầu | Chính sách nên cân nhắc |
| --- | --- | --- |
| Anonymous/Kubelet | Liveness/readiness không chứa details | Chỉ health/probes, network hạn chế |
| Metrics scraper | Read metrics | Dedicated identity và read-only endpoint |
| SRE readonly | Xem metrics, info, có thể mappings nội bộ | Authenticated readonly, audit |
| SRE privileged | Chỉnh log level theo sự cố | Chỉ có giới hạn, thời gian phê duyệt và audit |
| Runtime admin | Dump/shutdown | Không thường xuyên expose qua HTTP; dùng công cụ vận hành riêng |

Đừng trao quyền `ROLE_OPS` rộng cho tất cả pods chỉ để Prometheus scrape metrics. Nếu cần phân biệt scraper và SRE, hãy dùng matchers/identity có scope và kiểm thử quyền âm tính.

### 11.3. CORS không thay authentication

Browser CORS chỉ kiểm soát JavaScript từ origin khác có được đọc response; nó không chặn curl, backend-to-backend client, proxy hoặc attacker nói chung. `management.endpoints.web.cors.allowed-origins` có thể dùng cho dashboard cần cross-origin access, nhưng **không** thay Spring Security, network ACL, token validation hay mTLS. Không mở wildcard CORS với credentials cho Actuator.

### 11.4. CSRF khi có operations thay đổi trạng thái

Mặc định Spring Security áp CSRF protection lên các HTTP methods không an toàn. Các Actuator operations `POST`/`PUT`/`DELETE` có thể trả 403 dù user có role đúng nếu token thiếu, tùy chain/csrf config.

Không “chữa” bằng cách tắt CSRF cho toàn ứng dụng. Nếu Actuator chỉ được gọi từ máy với token/mTLS và không dùng browser cookies, có thể đánh giá policy riêng có scope hẹp. Trong demo đã **không expose** write operations nên không cần nới CSRF.

### 11.5. Audit và monitoring

Khi quản lý endpoint có quyền:

- Log **ai** gọi, **endpoint ID**, result status, client IP tin cậy, request ID, thời điểm.
- Không log Basic Authorization header, bearer token, cookie hoặc heap dump content.
- Theo dõi `401`/`403` spikes, các request tới denied endpoints và traffic bất thường từ các mạng khác.
- Chỉ tiêu SLO cho scrape availability và p95 response time.
- Thường xuyên test từ mạng **không được phép** rằng management listener/route không reachable.
- Rà soát ingress/LB/cloud firewall sau mỗi deployment, không chỉ mỗi lần cấu hình code.

## 12. Tách cổng quản trị với Spring WebFlux và nhiều runtime

### 12.1. Spring MVC

Ví dụ chính dùng Servlet stack/Tomcat. Management listener riêng do Boot tạo, security áp dụng bằng servlet `SecurityFilterChain` và `EndpointRequest`. Các health additional paths ở main port có thể được expose để probe dùng cùng web infrastructure với request nghiệp vụ.

### 12.2. Spring WebFlux

Spring WebFlux thường dùng Reactor Netty và **`SecurityWebFilterChain`**, không phải `HttpSecurity`/`SecurityFilterChain` của Servlet. Một policy bảo vệ reactive Actuator phải dùng API/reactive matcher tương ứng, ví dụ Boot `EndpointRequest` thuộc namespace reactive.

Đây là nguyên tắc, **không copy Java security source của demo MVC sang WebFlux**. Các properties `management.server.port`, `management.endpoints.web.exposure.include` và `management.endpoint.health.*` là khái niệm tương ứng, nhưng hãy xem docs đúng runtime.

### 12.3. Hai servers không đồng nghĩa hai processes

Một Spring Boot app với port `8080` và port `9091` có thể là **một JVM có hai web application contexts**. Nó vẫn chia sẻ failure modes ở process level. Muốn cách ly tài nguyên, quyền hệ điều hành hoặc network tuyệt đối hơn, cần thiết kế deployment/process-level boundary riêng, không chỉ dựa vào `management.server.port`.

### 12.4. Spring Boot versioning

Đừng lấy package của Boot **4.x** rồi import vào source Boot 3.5. Trong Boot 3.5, servlet matcher là:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
```

Các bản Boot mới có thể di chuyển packages và thay đổi policy defaults. Cấu hình **phải được thử lại** sau upgrade, đặc biệt access levels, endpoint mapping, security chain ordering, `management.server.base-path`, SSL và test support.

## 13. Phân tích kết quả 401, 403, 404 và lỗi mạng

| Hiện tượng | Nguyên nhân có thể | Phép kiểm tra phù hợp |
| --- | --- | --- |
| `/actuator/health` trả 404 trên 8080 | Management port đã tách | Gọi `127.0.0.1:9091` đúng path |
| Không kết nối được 9091 từ máy khác | Bind loopback hoặc firewall | Kiểm tra listen address và network namespace |
| Không kết nối được 9091 từ Prometheus pod | Pod network khác, management bind loopback | Chọn sidecar/NetworkPolicy hoặc bind interface được bảo vệ |
| 404 trên management dù Actuator dependency có | Endpoint access=none hoặc chưa expose/path sai | Xem `access`, `exposure` và base-path |
| 401 trên `/actuator/metrics` | Thiếu Basic auth | Gửi credentials vào đúng listener (TLS production) |
| 403 dù credentials hợp lệ | Thiếu role OPS hoặc security chain/CSRF | Inspect authorities, matcher, method |
| 200 trên `/actuator/env` | Endpoint nhạy cảm bị expose/sai access config | Thu hẹp include/access, kiểm tra Security |
| 404 thay 401 ở URL sai | Route chưa tồn tại, hoặc security lọc khác | Kiểm tra HTTP path và handler owner |
| 503 trên `/actuator/health` | Health DOWN/OUT_OF_SERVICE | Xem health contributors có kiểm soát |
| Health 200 nhưng API 503 | Management context khỏe, main listener/downstream lỗi | Probe `/readyz` trên main, theo dõi business SLO |
| Metrics 200 nhưng Prometheus không scrape | DNS/NetworkPolicy/proxy/TLS/cert hoặc target config sai | Kiểm tra từ scraper network namespace |
| 401 qua proxy dù local 200 | Proxy auth header/path rewrite sai | So headers/correlation ID per hop |
| `/actuator/prometheus` 404 | Chưa thêm Prometheus registry hoặc chưa expose | Bổ sung registry và policy khi cần |
| `/actuator/loggers` POST 403 | CSRF hoặc role/operation access | Xem access, method, CSRF, không tắt toàn cục |
| Màn hình browser hiện CORS | Browser origin không được phép; có thể che 401/403 | Inspect Network và response thật |
| Main context path `/shop` làm health URL sai | Nhầm main context với management base-path | Xem cách ghép path theo port |
| Cổng management khác lúc chạy test | `management.server.port=0` | Dùng `@LocalManagementPort` |
| Thay đổi Spring Boot major làm import lỗi | Namespace API thay đổi | Dùng docs/JavaDoc đúng Boot version |

### 13.1. Không đoán theo một status

`401` từ Spring Security khác `401` từ reverse proxy. `403` có thể do CSRF hoặc authorization. `404` có thể là endpoint bị vô hiệu đúng cách, nhưng cũng có thể URL/port/base-path sai. `503` health có thể phản ánh health contributor DOWN, nhưng cũng có thể do gateway trả lỗi khác. Phải xác định **ai phát response** bằng headers/logs và kiểm tra request tại đúng hop.

## 14. Kiểm tra bằng công cụ vận hành

### 14.1. Lắng nghe cổng

Trên Linux, một số công cụ:

```bash
ss -lntp
curl -i http://127.0.0.1:8080/api/ping
curl -i http://127.0.0.1:9091/actuator/health
```

Kiểm tra listener `9091` thực sự bind `127.0.0.1`. `ss` có thể không có sẵn trong container tối giản; có thể dùng `netstat` hoặc trình kiểm tra platform.

### 14.2. Docker

Ví dụ start container với chỉ public app port:

```bash
docker run --rm -p 8080:8080 my-management-demo:local
```

Đây là **lệnh minh họa nếu bạn đã build image tên `my-management-demo:local`**, không phải bước bắt buộc của Maven demo. Nếu management bind 127.0.0.1 trong container, chỉ có process cùng network namespace truy cập trực tiếp. **Không** publish cổng 9091 một cách không kiểm soát.

Một image chính thức cho ứng dụng phải được xây dựng theo quy trình riêng; bài này không sinh Dockerfile và không tuyên bố image đã tồn tại.

### 14.3. Kubernetes Services/NetworkPolicy

Một Service public nên route **chỉ main app port**. Nếu monitoring cần access management:

- Tạo internal-only Service/ServiceMonitor/PodMonitor theo platform.
- NetworkPolicy cho phép đúng namespace/pod selector và TCP management port.
- TLS/mTLS/identity nếu traffic đi qua network không tin cậy.
- Không expose management port ở Ingress Internet.
- Theo dõi traffic source và verify deny từ namespace không có quyền.

Port riêng là một chốt cấu hình deployment, **không tự sinh NetworkPolicy**.

### 14.4. Prometheus

`/actuator/metrics` là JSON Actuator metrics API, **khác** `/actuator/prometheus`. Để Prometheus scrape dạng text/OpenMetrics, thêm dependency phù hợp:

```xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
```

và đưa `prometheus` vào access/exposure policy có quản lý, ví dụ:

```properties
management.endpoint.prometheus.access=read-only
management.endpoints.web.exposure.include=health,metrics,prometheus
```

Đây là **fragment mở rộng**, không thuộc demo đang chạy. Khi thêm Prometheus, phải kiểm tra Spring Security matcher/rules cho scraper identity và network. Không bật wildcard chỉ để một scraper gọi được.

### 14.5. Đánh giá network từ bên ngoài

Đừng chỉ chạy curl trên localhost rồi kết luận cổng không public. Phải thực hiện phép thử từ một host/pod **không được phép**, theo quyền và chính sách tổ chức:

- Kiểm tra public LB/Ingress không có route tới 9091.
- Kiểm tra NetworkPolicy security group thực sự chặn.
- Kiểm tra reverse proxy không vô tình expose `/actuator/**` trên 8080.
- Kiểm tra forwarding/port publishing và DNS aliases.
- Đối chiếu audit/network logs và đảm bảo không lộ credentials trong tool output.

## 15. Checklist bảo mật và quan sát HTTP khi triển khai

### 15.1. Trước deploy

- [ ] Xác định actuator endpoints thực sự cần: health, metrics, info hoặc prometheus.
- [ ] Xác định ứng dụng có cần cổng quản trị riêng không, và ai cần scrape/điều khiển nó.
- [ ] Đặt `management.server.port` phù hợp; nếu dùng `management.server.address`, port phải khác main.
- [ ] Chỉ bind address được phép, không expose management vào Internet.
- [ ] Đối chiếu `management.server.base-path` và `management.endpoints.web.base-path`.
- [ ] Đặt `management.endpoints.access.default=none` nếu muốn strict opt-in.
- [ ] Cấp `read-only` cho từng endpoint được phép; giới hạn `max-permitted` khi không có operations ghi.
- [ ] `management.endpoints.web.exposure.include` chỉ liệt kê endpoint cần.
- [ ] Kiểm tra JMX exposure riêng nếu môi trường có JMX và yêu cầu bảo mật.
- [ ] Spring Security có rule health anonymous, metrics/ops authenticated, role/authorities đúng.
- [ ] Khi tự định nghĩa filter chains, khai báo đầy đủ rules cho app, không ỷ lại Boot defaults.
- [ ] Không mở env/beans/heapdump/shutdown/loggers tùy tiện.
- [ ] `management.endpoint.health.show-details` không tiết lộ details cho anonymous.
- [ ] Liveness/readiness health groups và main-port additional paths được test.
- [ ] HTTP management qua network không tin cậy dùng TLS/mTLS hoặc proxy bảo mật.
- [ ] Không hardcode Basic password/secret, có rotation và audit.
- [ ] Không dùng CORS wildcard như giải pháp auth.
- [ ] Có negative tests cho anonymous, role không đủ, endpoint không exposed và sai cổng.
- [ ] Có smoke test từ monitoring network và từ network không được phép.
- [ ] Kiểm tra ingress/LB/cloud firewall/NetworkPolicy, không chỉ application.properties.
- [ ] Giữ endpoint logs/metrics không chứa PII và low-cardinality tags.
- [ ] Sau nâng Boot patch/major, test lại status, path, matcher, listener, role và JMX exposure.

### 15.2. Sau deploy

- [ ] Main business route chạy tốt, không bị actuator config can thiệp.
- [ ] Health 200 khi UP, có tín hiệu DOWN khi thành phần thực sự lỗi.
- [ ] Metrics anonymous 401, OPS/scraper được phép 200 qua network dự kiến.
- [ ] Env/beans/heapdump/shutdown không đọc được.
- [ ] 9091 không reachable từ public Internet.
- [ ] Cổng main có `/livez` và `/readyz` nếu dựa vào additional paths.
- [ ] Kubelet/Prometheus không bị lockout do bind `127.0.0.1` sai topology.
- [ ] Thử reload/restart/rolling deployment và health transitions.
- [ ] Quan sát audit logs cho 401/403 và bất thường probe/scrape.
- [ ] Có runbook cho việc mất quyền OPS, lỗi TLS, network policy và port conflicts.

## 16. Bài tập tình huống và hướng giải

### Tình huống A — Tách cổng nhưng actuator vẫn public

Ứng dụng đặt `management.server.port=9091` nhưng Ingress publish cả 8080 và 9091 tới Internet. `env` được thêm vào web exposure và security permitAll.

**Phân tích:** tách port không tạo security boundary nếu routing vẫn public. Thu hẹp exposure/access, chặn ở ingress/firewall, đặt auth và kiểm tra từ Internet. Không chỉ đổi 9091 sang số khác.

### Tình huống B — Prometheus không scrape được

`management.server.address=127.0.0.1`, Prometheus chạy pod khác. Kết nối bị từ chối.

**Phân tích:** loopback chỉ trong network namespace hiện tại. Nếu cần scrape qua pod network, chọn bind address/service phù hợp và NetworkPolicy/mTLS/auth. Hoặc sidecar cùng pod. Không bỏ tất cả network restrictions một cách tùy tiện.

### Tình huống C — Health 200 nhưng người dùng lỗi toàn bộ API

Management listener độc lập vẫn healthy, nhưng main Servlet thread pool bị exhausted.

**Phân tích:** không chỉ dùng management `/actuator/health` làm bằng chứng main web app nhận traffic; dùng additional `/livez`/`/readyz` trên main port và giám sát business requests. Không đưa mọi external dependency vào liveness khiến pods restart hàng loạt.

### Tình huống D — Có Security starter nhưng metrics công khai

Ứng dụng định nghĩa một custom `SecurityFilterChain` với `anyRequest().permitAll()`. Boot auto security backing off.

**Phân tích:** custom chain đã thay logic bảo vệ mặc định. Dùng `EndpointRequest.toAnyEndpoint()` + role rules và một chain cho app còn lại; thêm negative tests.

### Tình huống E — `/actuator/env` trả 404 dù user OPS

`management.endpoints.web.exposure.include=health,metrics` và `management.endpoints.access.default=none`.

**Phân tích:** `env` không có access và không được expose. Đây là hành vi mong muốn, không phải “role OPS bị hỏng”. Không mở rộng endpoint để chữa một test dùng sai kỳ vọng.

### Tình huống F — Metrics trả 401 từ browser nhưng curl trả 200

Curl có Basic auth; browser fetch không gửi credentials và CORS không phù hợp.

**Phân tích:** kiểm tra actual Authorization/Origin, preflight, Allow-Origin và Security chain. CORS không thay auth; không mở wildcard credentialed CORS cho metrics.

### Tình huống G — Đổi management base path và health biến mất

Ứng dụng thêm:

```properties
management.server.base-path=/ops
management.endpoints.web.base-path=/actuator
```

**Phân tích:** khi management port riêng, URL thực thành `/ops/actuator/health`. Cập nhật monitor/scraper target và smoke tests.

### Tình huống H — SRE có role OPS nhưng POST loggers trả 403

Có thể CSRF đang bật; hoặc loggers operation không được access/expose; hoặc role đã bị map sai.

**Phân tích:** kiểm tra **access → exposure → Security/CSRF → method/operation**. Không tắt CSRF cho toàn app và không cấp unrestricted access chỉ để “thử xem được không”.

### Tình huống I — Endpoint nằm trên cổng quản trị nhưng không match EndpointRequest

Request `GET /unknown` tới 9091 không phải Actuator endpoint.

**Phân tích:** matcher `EndpointRequest.toAnyEndpoint()` chỉ nhận Actuator mappings; request có thể rơi vào filter chain fallback. Nếu muốn chính sách toàn bộ management listener, nghiên cứu management context-specific matcher/chain và tests; đừng dùng `toAnyEndpoint()` rồi coi đó là port matcher.

### Tình huống J — Nâng version rồi sao chép nhầm import mới

Sau khi chuyển tài liệu Boot 4 sang project 3.5, compiler không tìm thấy class `EndpointRequest` ở package mới.

**Phân tích:** sử dụng tài liệu/JavaDoc đúng version 3.5.16; chạy Maven dependency tree, giữ Boot BOM nhất quán. Nâng major có migration guide và regression tests.

## 17. Câu hỏi tự đánh giá

1. **`management.server.port` làm gì?** Tạo listener HTTP quản trị trên cổng khác main khi cấu hình khác `server.port`.
2. **Tách cổng có tự yêu cầu login không?** Không. Security và network policies là lớp riêng.
3. **`management.server.address` có thể đặt khác main khi cùng port không?** Không, cần management port khác.
4. **Default Actuator HTTP expose những gì trong Boot 3.5?** Health.
5. **`management.endpoints.access.default=none` khác `web.exposure.exclude=*` thế nào?** Một cái loại endpoint khỏi context; một cái giới hạn HTTP exposure.
6. **Access `read-only` cho `loggers` có cho đổi log level không?** Không, chỉ read operations.
7. **`EndpointRequest.toAnyEndpoint()` có match mọi URL tại management port không?** Không, nó match Actuator endpoints.
8. **Custom `SecurityFilterChain` ảnh hưởng Boot security mặc định thế nào?** Boot auto security back off; app phải tự bảo vệ routes.
9. **Vì sao có hai security chains trong ví dụ?** Rule riêng cho Actuator và fallback policy cho API application.
10. **`management.server.base-path` có giống `management.endpoints.web.base-path` không?** Không, đường dẫn được ghép theo ngữ cảnh và cổng.
11. **`127.0.0.1` trong container có cho Prometheus pod khác truy cập không?** Không trực tiếp, cần network topology/forwarding phù hợp.
12. **Basic auth qua HTTP ngoài mạng tin cậy có an toàn không?** Không. Dùng TLS/mTLS hoặc proxy bảo mật.
13. **`/actuator/metrics` và `/actuator/prometheus` có cùng format không?** Không; Prometheus cần registry và exposure riêng.
14. **Health 200 trên management port có chứng minh main app khỏe không?** Không hoàn toàn; có hai web infrastructures.
15. **Vì sao thêm additional probe paths?** Để liveness/readiness được kiểm tra qua main listener.
16. **Có nên thêm DB chung vào liveness không?** Thường không, tránh restart tất cả replicas do external outage.
17. **Vì sao không expose heapdump public?** Có thể chứa secrets/dữ liệu nhạy cảm và rất tốn tài nguyên.
18. **Nếu endpoint trả 404, có chắc đã bị bảo mật bởi role không?** Không; có thể không tồn tại hoặc bị unexposed.
19. **Khi metrics anonymous trả 401 có nghĩa gì?** HTTP Security yêu cầu xác thực.
20. **Điều kiện hoàn tất triển khai cổng quản trị là gì?** Endpoint minimization, access policy, auth, network ACL/TLS, probe targets, positive/negative tests và quan sát thực tế.

## 18. Tài liệu chính thức

- [Spring Boot 3.5 — Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/3.5/reference/actuator/monitoring.html): management port/address/base-path/SSL và cách vô hiệu hóa HTTP endpoints.
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): endpoint access levels, web/JMX exposure, Spring Security, health groups và Kubernetes probes.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `management.server.*`, `management.endpoint.*`, `management.endpoints.*`.
- [Spring Boot 3.5 — Actuator How-to](https://docs.spring.io/spring-boot/3.5/how-to/actuator.html): thay đổi HTTP port/address cho Actuator.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest(RANDOM_PORT)`, TestRestTemplate và integration tests.
- [Spring Boot 3.5.16 — LocalManagementPort JavaDoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/web/server/LocalManagementPort.html): lấy management port ngẫu nhiên trong tests.
- [Spring Boot 3.5.16 — EndpointRequest JavaDoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html): matching Actuator endpoints thay vì toàn bộ port.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request matchers, role-based authorization.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF cho operations ghi.
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): thiết kế health probes ở orchestration layer.

**Kết luận:** `management.server.port` và `management.server.address` là công cụ **phân tách đường mạng**; `management.endpoints.access.*` và `management.endpoints.web.exposure.*` quyết định endpoint có sẵn qua các kênh nào; Spring Security và network policies quyết định **ai thực sự được phép dùng**. Khi management context chạy trên cổng riêng, cần kiểm tra **cả hai ports**, bổ sung main-port liveness/readiness khi phù hợp và xác nhận các endpoints nhạy cảm **không thể truy cập** trước khi đưa hệ thống vào production.