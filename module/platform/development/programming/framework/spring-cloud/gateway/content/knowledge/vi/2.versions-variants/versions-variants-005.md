# Đối chiếu tên starter và tiền tố cấu hình giữa các dòng phiên bản Spring Cloud Gateway

## 1. Vì sao phải đối chiếu cả starter lẫn tiền tố cấu hình?

**Spring Cloud Gateway** là API Gateway của hệ sinh thái Spring, dùng để định tuyến yêu cầu đến các microservice thông qua **route predicate**, áp dụng **filter chain** để sửa đường dẫn/header, kết hợp **service discovery** và bổ sung các cơ chế như xác thực, rate limiting, circuit breaker, retry, TLS và quan sát lưu lượng. Trong quá trình nâng cấp, một cấu hình có thể vẫn là YAML hợp lệ nhưng không còn được Gateway đọc do **tên dependency hoặc namespace cấu hình đã đổi**.

Hãy phân biệt ba lớp thông tin:

1. **Spring Boot / Spring Cloud release train / Spring Cloud Gateway**: bộ ba phiên bản cần tương thích với nhau. Ví dụ, Spring Cloud `2025.0.x` quản lý Gateway `4.3.x`, còn `2025.1.x` quản lý Gateway `5.0.x`.
2. **Starter**: artifact Maven/Gradle khai báo để tạo ứng dụng Gateway, ví dụ `spring-cloud-starter-gateway-server-webflux`.
3. **Tiền tố cấu hình (property prefix)**: đường dẫn Spring Boot dùng để bind thuộc tính, ví dụ `spring.cloud.gateway.server.webflux.routes`.

> **Mấu chốt:** từ Gateway **4.3** (Spring Cloud **2025.0**), các tên starter và namespace mới mô tả rõ vai trò **Server/Proxy Exchange** và công nghệ **WebFlux/Web MVC**. Tên cũ được đánh dấu deprecated trong dòng chuyển tiếp 4.3; Gateway 5.x dùng bộ tên mới. Không thể kết luận một khóa cấu hình còn hiệu lực chỉ vì ứng dụng khởi động thành công.

Mục tiêu của bài: xác định đúng dependency theo phiên bản và web stack; đổi chính xác tiền tố của route, filter, discovery và các thuộc tính vận hành; đọc được cấu hình cũ và tránh việc nâng cấp xong Gateway không tạo route.

## 2. Bảng đối chiếu theo dòng phiên bản

Các tên starter trong bảng có chung `groupId` **`org.springframework.cloud`**. Cột prefix là cấu hình **Gateway Server** trong `application.yml`/`application.properties`, không phải prefix chung của Spring Boot.

| Dòng Gateway | Spring Cloud release train tiêu biểu | Server WebFlux: starter | Server WebFlux: prefix route | Server Web MVC: starter và prefix |
|---|---|---|---|---|
| 2.x–3.1.x | Các train thời Spring Boot 2, gồm `2021.0.x` ở dòng 3.1 | `spring-cloud-starter-gateway` | `spring.cloud.gateway.routes` | Chưa có biến thể **Server MVC** chính thức tương ứng các dòng này |
| 4.0.x | `2022.0.x` | `spring-cloud-starter-gateway` | `spring.cloud.gateway.routes` | Chưa có Server MVC (xuất hiện từ 4.1) |
| 4.1.x–4.2.x | `2023.0.x`–`2024.0.x` | `spring-cloud-starter-gateway` | `spring.cloud.gateway.routes` | `spring-cloud-starter-gateway-mvc`, prefix `spring.cloud.gateway.mvc.*` |
| **4.3.x** | **`2025.0.x`** | **`spring-cloud-starter-gateway-server-webflux`** | **`spring.cloud.gateway.server.webflux.routes`** | **`spring-cloud-starter-gateway-server-webmvc`**, prefix **`spring.cloud.gateway.server.webmvc.*`** |
| **5.0.x** | **`2025.1.x`** | `spring-cloud-starter-gateway-server-webflux` | `spring.cloud.gateway.server.webflux.routes` | `spring-cloud-starter-gateway-server-webmvc`, prefix `spring.cloud.gateway.server.webmvc.*` |
| **5.1.x** | **`2026.0.x`** | `spring-cloud-starter-gateway-server-webflux` | `spring.cloud.gateway.server.webflux.routes` | `spring-cloud-starter-gateway-server-webmvc`, prefix `spring.cloud.gateway.server.webmvc.*` |

Các mốc đáng nhớ:

- Gateway **3.1** thuộc thế hệ Spring Boot 2; Gateway **4.x** thuộc thế hệ Spring Boot 3; Gateway **5.x** thuộc thế hệ Spring Boot 4. Ví dụ chính thức: Spring Cloud `2025.0` tương thích Spring Boot **3.5**, `2025.1` dùng Spring Boot **4.x**, và `2026.0.0` phát hành cùng Spring Boot **4.2.0**.
- Gateway **4.1** bổ sung Server MVC chạy trên Servlet stack (như Tomcat/Jetty), trong khi Server WebFlux dùng Reactor Netty. Chúng là hai biến thể Gateway Server có mô hình xử lý khác nhau.
- Gateway **4.3** là mốc đổi tên: starter cũ được đánh dấu deprecated, và các prefix cũ được chuyển sang namespace mới. Một số trang ví dụ ở tài liệu 4.3 vẫn minh họa đường dẫn cũ; nên đối chiếu **release notes 2025.0** và danh mục **Configuration Properties** đúng phiên bản trước khi sao chép.
- Gateway **5.0 trở lên** loại bỏ các artifact cũ đã deprecated. Với dự án mới, dùng luôn tên starter và prefix mới tương ứng stack.

Không nên tự chọn riêng `spring-cloud-gateway` version trong khi BOM của Spring Cloud đang quản lý phiên bản khác. Khi nâng cấp, hãy chọn **Spring Boot tương thích → release train Spring Cloud → Gateway do BOM quản lý**.

## 3. Đổi tên starter: chọn đúng WebFlux hay Web MVC

| Vai trò | Starter/artifact cũ | Tên mới từ Gateway 4.3 | Ý nghĩa |
|---|---|---|---|
| **Gateway Server WebFlux** | `spring-cloud-starter-gateway` | `spring-cloud-starter-gateway-server-webflux` | API gateway reactive, chạy với Spring WebFlux và Reactor Netty |
| **Gateway Server Web MVC** | `spring-cloud-starter-gateway-mvc` | `spring-cloud-starter-gateway-server-webmvc` | API gateway trên Spring MVC, dùng Servlet runtime |
| **Proxy Exchange WebFlux** | `spring-cloud-gateway-webflux` | `spring-cloud-gateway-proxyexchange-webflux` | Dùng đối tượng `ProxyExchange` trong web handler; không phải gateway server độc lập |
| **Proxy Exchange Web MVC** | `spring-cloud-gateway-mvc` | `spring-cloud-gateway-proxyexchange-webmvc` | Dùng `ProxyExchange` trên MVC; không đồng nghĩa với starter Gateway Server MVC |

**Lưu ý phân biệt tên rất dễ nhầm:** `spring-cloud-starter-gateway-mvc` (có `starter`) là Gateway **Server MVC** đời cũ; `spring-cloud-gateway-mvc` (không có `starter`) từng thuộc nhóm **Proxy Exchange**. Khi nâng cấp, so khớp theo **vai trò module**, không chỉ thay một đoạn chuỗi `mvc`.

Ví dụ khai báo starter mới trong Maven, với **BOM đã chọn phiên bản Spring Cloud tương thích**:

```xml
<!-- pom.xml: phần dependencyManagement -->
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>2026.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<!-- pom.xml: Gateway Server WebFlux, Spring Cloud Gateway 5.1.x -->
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
</dependencies>
```

Ví dụ này dùng release train `2026.0.0` (tương ứng Spring Boot `4.2.0`); chỉ dành cho dự án đã chọn đúng thế hệ Boot đó. Nếu dùng Server Web MVC, thay artifact bằng `spring-cloud-starter-gateway-server-webmvc`. Không đặt cả hai starter Server vào cùng ví dụ rồi kỳ vọng Gateway tự chọn đúng biến thể.

Trong Gradle, phần dependency tương ứng có dạng:

```kotlin
dependencies {
    // Sau khi cấu hình BOM Spring Cloud tương thích trong build.
    implementation("org.springframework.cloud:spring-cloud-starter-gateway-server-webflux")
}
```

## 4. Bảng ánh xạ tiền tố cấu hình chính xác

### 4.1. Server WebFlux: từ prefix chung sang `server.webflux`

| Công việc | Gateway 4.2 trở về trước | Gateway 4.3+ (tên mới) |
|---|---|---|
| Khai báo route | `spring.cloud.gateway.routes` | `spring.cloud.gateway.server.webflux.routes` |
| Filter mặc định cho các route | `spring.cloud.gateway.default-filters` | `spring.cloud.gateway.server.webflux.default-filters` |
| Tự tạo route từ service discovery | `spring.cloud.gateway.discovery.locator.enabled` | `spring.cloud.gateway.server.webflux.discovery.locator.enabled` |
| Cấu hình CORS chung | `spring.cloud.gateway.globalcors.cors-configurations` | `spring.cloud.gateway.server.webflux.globalcors.cors-configurations` |
| HTTP client kết nối downstream | `spring.cloud.gateway.httpclient.connect-timeout` | `spring.cloud.gateway.server.webflux.httpclient.connect-timeout` |
| Bật metrics Gateway | `spring.cloud.gateway.metrics.enabled` | `spring.cloud.gateway.server.webflux.metrics.enabled` |
| Tham số Redis RateLimiter của Gateway | `spring.cloud.gateway.redis-rate-limiter.*` | `spring.cloud.gateway.server.webflux.redis-rate-limiter.*` |
| Bật/tắt Gateway Server | `spring.cloud.gateway.enabled` | `spring.cloud.gateway.server.webflux.enabled` |

Quy luật là thay phần `spring.cloud.gateway.` bằng `spring.cloud.gateway.server.webflux.` **đối với các thuộc tính Gateway Server WebFlux**. Đây **không phải phép thay thế toàn cục** trên mọi key có chữ `gateway`: các namespace của Spring Boot, Spring Security, Actuator, hoặc Proxy Exchange phải xử lý riêng.

### 4.2. Server Web MVC: từ `mvc` sang `server.webmvc`

| Công việc | Gateway 4.1–4.2 | Gateway 4.3+ |
|---|---|---|
| Khai báo route | `spring.cloud.gateway.mvc.routes` | `spring.cloud.gateway.server.webmvc.routes` |
| Bật/tắt Gateway Server MVC | `spring.cloud.gateway.mvc.enabled` | `spring.cloud.gateway.server.webmvc.enabled` |
| Khai báo routes dạng map | `spring.cloud.gateway.mvc.routes-map` | `spring.cloud.gateway.server.webmvc.routes-map` |
| Khai báo trusted proxies | `spring.cloud.gateway.mvc.trusted-proxies` | `spring.cloud.gateway.server.webmvc.trusted-proxies` |

Ở đây phần thay thế là `spring.cloud.gateway.mvc.` → `spring.cloud.gateway.server.webmvc.`. Đừng đổi MVC thành WebFlux chỉ để cấu hình khớp tên: ứng dụng MVC chạy trên Servlet, còn WebFlux chạy trên Reactor Netty; cách cài filter và nhiều khả năng vận hành cũng khác nhau.

### 4.3. Phần nào không đổi theo quy luật trên?

- **`spring.application.name`**, **`server.port`**, **`server.ssl.*`**, **`management.*`**, **`spring.security.*`** là thuộc tính thuộc Spring Boot/các thành phần khác. Chẳng hạn TLS đầu vào của server thường cấu hình bằng `server.ssl.*`; không chuyển thành `spring.cloud.gateway.server.webflux.server.ssl.*`.
- Giá trị trong một route như `uri`, `predicates`, `filters`, `Path`, `StripPrefix`, `AddRequestHeader`, `Retry` là **nội dung của route**, không phải tiền tố property. Các cấu hình chi tiết có thể khác giữa WebFlux và MVC, nên kiểm tra tài liệu filter của đúng biến thể.
- `spring.cloud.gateway.proxy-exchange.webflux.*` và `spring.cloud.gateway.proxy-exchange.webmvc.*` thuộc **Proxy Exchange**; không dùng để khai báo danh sách route cho Gateway Server.
- Prefix `spring.cloud.gateway.server.webflux.metrics.*` điều khiển tính năng metrics của Gateway. **Tên metric** (ví dụ `spring.cloud.gateway.requests`) không nhất thiết đổi theo prefix cấu hình.

## 5. Ví dụ chuyển đổi: Server WebFlux 4.2 → 4.3/5.x

Giả sử Gateway nhận `GET /api/catalog/items`, chuyển tới dịch vụ `http://localhost:8081` dưới đường dẫn `/catalog/items` và gắn header `X-Gateway: edge`.

**Cấu hình cũ (Gateway 4.2, starter `spring-cloud-starter-gateway`):**

```yaml
# application.yml — Gateway Server WebFlux 4.2
server:
  port: 8080
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-route
          uri: http://localhost:8081
          predicates:
            - Path=/api/catalog/**
          filters:
            - StripPrefix=1
            - AddRequestHeader=X-Gateway, edge
      discovery:
        locator:
          enabled: false
      httpclient:
        connect-timeout: 2000
      metrics:
        enabled: true
```

**Cấu hình mới (Gateway 4.3+, starter `spring-cloud-starter-gateway-server-webflux`):**

```yaml
# application.yml — Gateway Server WebFlux 4.3/5.x
server:
  port: 8080
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-route
              uri: http://localhost:8081
              predicates:
                - Path=/api/catalog/**
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Gateway, edge
          discovery:
            locator:
              enabled: false
          httpclient:
            connect-timeout: 2000
          metrics:
            enabled: true
```

**Điều đã đổi:** `routes`, `discovery`, `httpclient`, `metrics` chuyển từ dưới `gateway` sang `gateway.server.webflux`. **Điều giữ nguyên:** cấu trúc bên trong từng route, path predicate, các filter và tham số của chúng. `StripPrefix=1` loại bỏ đoạn `/api`; backend nhận `/catalog/items`. Nếu backend chưa chạy, lỗi kết nối downstream là vấn đề khác với việc route không được nạp.

Có thể thử khi đã chạy ứng dụng Gateway và backend mẫu:

```bash
curl -i http://localhost:8080/api/catalog/items
```

Khi cấu hình đúng, Gateway lựa chọn `catalog-route`, chuyển tiếp đến `localhost:8081/catalog/items` và gửi header `X-Gateway: edge`. Hãy kiểm tra log của backend để xác nhận đường dẫn và header; mã HTTP cuối cùng do backend và các filter quyết định.

## 6. Ví dụ chuyển đổi: Server MVC 4.2 → 4.3/5.x

**Cũ — Gateway Server MVC 4.2:**

```yaml
spring:
  cloud:
    gateway:
      mvc:
        routes:
          - id: orders-route
            uri: http://localhost:8082
            predicates:
              - Path=/orders/**
            filters:
              - StripPrefix=1
```

**Mới — Gateway Server Web MVC 4.3+:**

```yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: orders-route
              uri: http://localhost:8082
              predicates:
                - Path=/orders/**
              filters:
                - StripPrefix=1
```

Đổi cả starter `spring-cloud-starter-gateway-mvc` → `spring-cloud-starter-gateway-server-webmvc`. Với `GET /orders/42`, `StripPrefix=1` khiến backend nhận `/42`. Ví dụ dùng filter được cả hai dòng để minh họa **khác biệt namespace**, không ngụ ý mọi filter WebFlux đều có bản MVC giống hệt.

## 7. Khi nâng cấp hệ thống Gateway thật: trình tự an toàn

1. **Chốt phiên bản:** xác định Spring Boot, Spring Cloud BOM, Gateway version thực tế và loại Server (**WebFlux** hoặc **Web MVC**). Đọc `dependency:tree` của Maven hoặc `dependencies` của Gradle nếu dự án có nhiều module kéo dependency gián tiếp.
2. **Đổi starter theo đúng vai trò:** WebFlux → `spring-cloud-starter-gateway-server-webflux`; MVC → `spring-cloud-starter-gateway-server-webmvc`. Với Gateway 4.3, tên cũ có thể còn hoạt động nhưng đã deprecated; 5.x dùng tên mới.
3. **Chuyển namespace của toàn bộ cấu hình Gateway Server:** ngoài `routes` phải rà các thuộc tính liên quan `default-filters`, discovery, CORS, timeout, load balancer, rate limiter, metrics, trusted proxies... Tham chiếu `Configuration Properties` **đúng phiên bản**.
4. **Giữ tách biệt cấu hình ngoài Gateway:** `server.ssl.*` cho TLS đầu vào, Spring Security cho xác thực/phân quyền, `management.*` cho Actuator. Phần TLS của HTTP client **đi tới backend** nằm trong nhóm `spring.cloud.gateway.server.webflux.httpclient.ssl.*`, nên phân biệt hai đầu kết nối.
5. **Đối chiếu các dependency tính năng:** `lb://service-id` cần cơ chế DiscoveryClient và load balancer thích hợp; CircuitBreaker, RedisRateLimiter, Actuator có thể cần starter/thư viện và cấu hình riêng. Đổi prefix không tự cài thêm các thành phần đó.
6. **Chỉ dùng công cụ chuyển tiếp khi cần:** release notes 2025.0 đề cập `spring-boot-properties-migrator` để hỗ trợ chuyển các property deprecated. Dùng để dò/chuyển cấu hình cũ trong quá trình nâng cấp, sau đó đưa mọi key về namespace mới và loại bỏ nhu cầu migration runtime. Tránh duy trì cùng một route ở **cả prefix cũ lẫn mới**, vì có thể tạo ghi đè/khó xác định nguồn cấu hình hiệu lực.
7. **Kiểm tra hành vi thực tế:** đối chiếu danh sách route đã nạp, truy cập URL thử, xác minh path/header được sửa đúng, kiểm tra `lb://`, retry/circuit breaker, TLS tới backend và metrics. Chỉ mở endpoint Actuator để chẩn đoán với quyền truy cập phù hợp.

### 7.1. Cách điều tra khi Gateway khởi động nhưng trả 404

| Triệu chứng | Kiểm tra trước tiên | Hướng xử lý |
|---|---|---|
| Trả `404` dù `application.yml` có route | Starter, phiên bản Gateway và prefix `routes` có khớp nhau không? | Dùng `gateway.routes` ở 4.2 trở về trước; `gateway.server.webflux.routes` hoặc `gateway.server.webmvc.routes` theo bản 4.3+ và đúng stack |
| Có route nhưng không gọi được dịch vụ | `uri`, DNS, port, service registry, dependency load balancer | Kiểm tra backend, `lb://service-id` và DiscoveryClient; không quy ngay lỗi cho rename |
| Request tới backend nhưng sai path | `Path`, `StripPrefix`, `RewritePath`, thứ tự filter | Dò path trước/sau filter; khi `StripPrefix=1`, `/api/a` thành `/a` |
| Header hoặc retry/circuit breaker không như dự tính | Route có match chưa, có dùng filter được hỗ trợ đúng stack, có đủ dependency? | Kiểm tra filter và thư viện theo version; không suy chỉ từ tên filter |
| Metrics không xuất hiện | Cấu hình `metrics.enabled`, Actuator/Micrometer, endpoint exposure | Chuyển đúng prefix và kiểm tra công cụ quan sát tương ứng |

Ở **Server WebFlux**, khi đã cấu hình Actuator Gateway endpoint thích hợp, có thể kiểm tra các route thông qua đường dẫn dạng `/actuator/gateway/routes`. Cần phân biệt endpoint quản trị với lưu lượng công khai và hạn chế quyền truy cập trong môi trường thật.

## 8. Ba tình huống tự kiểm tra

**Tình huống A.** Dự án nâng cấp từ Spring Cloud `2024.0`/Gateway `4.2` lên `2025.0`/Gateway `4.3`, vẫn giữ `spring-cloud-starter-gateway` và `spring.cloud.gateway.routes`. Cần thay gì?

**Đáp án:** đổi starter thành `spring-cloud-starter-gateway-server-webflux`; chuyển các cấu hình WebFlux sang `spring.cloud.gateway.server.webflux.*`, trước hết là `routes`. Sau đó kiểm tra các thuộc tính khác như discovery, httpclient và metrics. Dòng 4.3 có giai đoạn deprecated/migration, không nên lấy việc cấu hình cũ tạm chạy được làm chuẩn cho nâng cấp 5.x.

**Tình huống B.** Ứng dụng chạy Servlet/Tomcat, trước đây dùng `spring-cloud-starter-gateway-mvc`; đồng đội đề xuất đổi thành `spring-cloud-starter-gateway-server-webflux` vì tên mới phổ biến hơn. Đề xuất có đúng không?

**Đáp án:** không. Biến thể tương ứng là `spring-cloud-starter-gateway-server-webmvc`; namespace route mới là `spring.cloud.gateway.server.webmvc.routes`. Đổi sang WebFlux đồng nghĩa đổi web stack, không phải chỉ đổi tên artifact.

**Tình huống C.** Một ứng dụng Gateway Server WebFlux 5.x có hai danh sách route: `spring.cloud.gateway.routes` và `spring.cloud.gateway.server.webflux.routes`. Dòng nào cần giữ?

**Đáp án:** chuẩn hóa về **`spring.cloud.gateway.server.webflux.routes`**. Xóa cấu hình trùng lặp ở tiền tố cũ sau khi đối chiếu đầy đủ giá trị để tránh phụ thuộc vào cơ chế di trú và tránh ghi đè không mong muốn.

## 9. Tài liệu tham chiếu chính thức

- [Spring Cloud 2025.0 Release Notes — thay đổi starter và namespace Gateway 4.3](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes).
- [Spring Cloud Gateway 4.2 — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/4.2/configprops.html): các prefix `spring.cloud.gateway.*` và `spring.cloud.gateway.mvc.*`.
- [Spring Cloud Gateway 4.3 — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/4.3/configprops.html): thể hiện giai đoạn chuyển tiếp giữa namespace cũ và mới.
- [Spring Cloud Gateway 5.1 — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/5.1/configprops.html): các prefix Server WebFlux/Web MVC mới.
- [Gateway 5.0 — WebFlux starter](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/starter.html) và [Gateway 5.0 — Web MVC starter](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/starter.html).
- [Gateway 5.0 — Proxy Exchange](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-proxy-exchange.html): phân biệt Proxy Exchange với Gateway Server.
- [Spring Cloud 2026.0.0 release announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/): Gateway 5.1.0 tương ứng train 2026.0.0 và Boot 4.2.0.

**Ghi nhớ:** kiểm tra **version → starter → web stack → prefix** theo đúng thứ tự. Hai cấu hình có cú pháp route/filter y hệt vẫn có thể cho kết quả khác nếu được đặt dưới namespace của phiên bản hoặc biến thể khác.
