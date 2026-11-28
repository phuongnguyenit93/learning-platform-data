# Định tuyến qua gateway và reverse proxy

## 1. Vì sao cần định tuyến riêng cho Actuator?

Trong ứng dụng Spring Boot dùng **Spring Modulith**, Actuator cung cấp các endpoint để kiểm tra sức khỏe, xem metrics và đọc thông tin về application module. Ví dụ, nhóm vận hành có thể cần `/actuator/health`, `/actuator/prometheus` hoặc endpoint `modulith` để xác minh module model của bản ứng dụng đang chạy.

Khi ứng dụng được triển khai sau API gateway, ingress controller hoặc reverse proxy, client không truy cập trực tiếp địa chỉ và port nội bộ của ứng dụng. Gateway nhận URL công khai, áp dụng chính sách xác thực/định tuyến, rồi chuyển request tới upstream. Vì vậy, đường dẫn bên ngoài có thể khác đường dẫn Actuator mà Spring Boot thực sự phục vụ.

Ví dụ:

```text
Client / monitoring
  https://ops.example.com/ops/shop/actuator/health
                  |
                  v
            API Gateway
                  |
          StripPrefix(2)
                  |
                  v
  http://shop-app:8081/actuator/health
                  |
                  v
        Spring Boot Actuator
```

Mục tiêu của bài này là cấu hình định tuyến qua **Spring Cloud Gateway** và **reverse proxy**, hiểu cách xử lý prefix/forwarded headers, giới hạn endpoint được công khai và kiểm tra đúng đường đi từ bên ngoài tới management server.

Trong `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`, Actuator là một phần của bức tranh vận hành gồm module graph, event metrics, tracing và context propagation. Định tuyến đúng giúp monitoring đọc được dữ liệu cần thiết mà không vô tình mở các endpoint quản trị cho mạng công cộng.

## 2. Phân biệt URL bên ngoài và URL nội bộ

Một request đi qua proxy có thể có nhiều dạng path:

| Lớp | Ví dụ | Ai xử lý? |
| --- | --- | --- |
| Public URL | `/ops/shop/actuator/health` | Client, DNS, TLS termination |
| Gateway route path | `/ops/shop/actuator/health` | Route predicate/filter |
| Upstream path | `/actuator/health` | Spring Boot Actuator |
| Management base path | `/actuator` hoặc `/manage` | Cấu hình Actuator |
| Context path | `/shop` nếu được cấu hình | Servlet/WebFlux application |

Đừng mặc định path công khai phải giống path nội bộ. Một gateway có thể bỏ prefix `/ops/shop`; reverse proxy cũng có thể rewrite `/monitoring/shop` thành `/actuator`. Cần ghi rõ **đường dẫn nào được match, bao nhiêu segment bị bỏ, upstream path cuối cùng là gì**.

Ví dụ, nếu public path là `/ops/shop/actuator/health` và filter bỏ hai segment đầu (`ops`, `shop`), upstream nhận `/actuator/health`. Nếu bỏ ba segment, upstream chỉ còn `/health` và Actuator trả `404` trừ khi base path được cấu hình tương ứng.

## 3. Actuator endpoint và base path

Spring Boot mặc định ánh xạ web endpoint theo dạng:

```text
/actuator/{endpoint-id}
```

Ví dụ `/actuator/health`. Mặc định chỉ endpoint `health` được expose qua HTTP; các endpoint khác cần được bật rõ ràng. `prometheus` yêu cầu Micrometer Prometheus registry, còn `modulith` cần tích hợp Spring Modulith Insight/Actuator tương ứng.

Có thể thay đổi prefix bằng `management.endpoints.web.base-path`:

```yaml
management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info,metrics,prometheus,modulith
```

Sau cấu hình này, endpoint health nằm ở `/manage/health`, không còn ở `/actuator/health`. Danh sách `include` ở đây là ví dụ cho **mạng quản trị nội bộ**; không nên expose tất cả endpoint ra internet chỉ vì gateway đã có route.

Khi ứng dụng dùng cùng port cho traffic nghiệp vụ và management, base path liên quan tới `server.servlet.context-path` (Servlet) hoặc `spring.webflux.base-path` (WebFlux). Nếu cấu hình `management.server.port` riêng, `management.endpoints.web.base-path` được tính tương đối với `management.server.base-path`. Hãy xác định đầy đủ cả context path lẫn management base path trước khi viết route.

### 3.1. Chỉ expose endpoint thật sự cần thiết

Ví dụ cho một ứng dụng cần health, metrics, Prometheus và module metadata:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus,modulith
```

Không dùng `include: "*"` trong môi trường production trừ khi có một thiết kế bảo vệ và lý do vận hành rõ ràng. Các endpoint như `env`, `configprops`, `beans`, `heapdump`, `loggers` hoặc `shutdown` có thể tiết lộ thông tin nhạy cảm hoặc cho phép thao tác có tác động lớn.

Endpoint **được expose** và endpoint **được phép truy cập** là hai việc khác nhau. Gateway route chỉ quyết định request được chuyển tới đâu; ứng dụng vẫn cần network policy và authorization phù hợp.

## 4. Tách management port khỏi cổng ứng dụng

Một cách triển khai là phục vụ traffic nghiệp vụ và management trên hai port khác nhau:

```yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,metrics,prometheus,modulith
```

Khi đó:

| Loại traffic | Địa chỉ nội bộ |
| --- | --- |
| API nghiệp vụ | `http://shop-app:8080/...` |
| Actuator | `http://shop-app:8081/actuator/...` |

Tách port giúp định tuyến và firewall dễ kiểm soát hơn. Tuy nhiên, nó **không tự bảo vệ endpoint**: nếu port 8081 vẫn được publish ra mạng không tin cậy, client vẫn có thể gọi trực tiếp.

Trong môi trường container, gateway ở container khác không thể gọi `127.0.0.1:8081` của container ứng dụng. Nếu bind management chỉ vào loopback, chỉ process trong cùng network namespace mới truy cập được. Hãy dùng địa chỉ/interface nội bộ phù hợp với network topology và giới hạn truy cập bằng firewall, Kubernetes NetworkPolicy hoặc security group. Không bind management ra mọi interface công khai nếu không cần.

## 5. Định tuyến Actuator qua Spring Cloud Gateway

Ví dụ sau dùng **Spring Cloud Gateway Server WebFlux 4.3.x**. Gateway nhận public path `/ops/shop/actuator/health`, bỏ hai segment đầu và gửi tới management port của `shop-app`:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: shop-actuator-health
          uri: http://shop-app:8081
          predicates:
            - Path=/ops/shop/actuator/health
          filters:
            - StripPrefix=2
```

Kết quả:

```text
Request vào gateway:
  /ops/shop/actuator/health

Sau StripPrefix=2:
  /actuator/health

Upstream:
  http://shop-app:8081/actuator/health
```

`StripPrefix=2` bỏ hai path segment đầu tiên. Nếu public path là `/ops/shop/actuator/health/readiness`, route cần match thêm path con; `Path=/ops/shop/actuator/health/**` không nhất thiết match endpoint gốc `/health`, vì vậy có thể khai báo cả hai pattern hoặc một pattern bao phủ rõ ràng theo nhu cầu.

### 5.1. Định tuyến một nhóm endpoint cho mạng quản trị

Nếu Prometheus server và công cụ vận hành cần nhiều endpoint, có thể tạo route riêng cho từng endpoint hoặc một route nhóm được bảo vệ:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: shop-actuator-ops
          uri: http://shop-app:8081
          predicates:
            - Path=/ops/shop/actuator/**
          filters:
            - StripPrefix=2
```

Route nhóm này chuyển mọi path còn lại dưới `/ops/shop/actuator/` tới Actuator. **Chỉ dùng khi gateway có authentication/authorization và network access control tương ứng**, đồng thời ứng dụng chỉ expose các endpoint đã duyệt. Với public ingress, thường nên chỉ route health check cần thiết; metrics và module metadata nên đi qua mạng monitoring/ops riêng.

### 5.2. RewritePath khi cần ánh xạ prefix phức tạp

`RewritePath` dùng regular expression để biến đổi path. Ví dụ public path `/monitoring/shop/health` cần chuyển thành `/actuator/health`:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: shop-health-rewrite
          uri: http://shop-app:8081
          predicates:
            - Path=/monitoring/shop/**
          filters:
            - RewritePath=/monitoring/shop/?(?<segment>.*), /actuator/$\{segment}
```

Với YAML, ký hiệu `$` trong replacement cần escape theo cú pháp filter/documentation của phiên bản Gateway; ví dụ chính thức dùng dạng `/$\{segment}`. Hãy kiểm tra log route và request thực tế để xác nhận kết quả rewrite. Với prefix đơn giản, `StripPrefix` thường dễ đọc và ít gây lỗi hơn regex.

Tên property cấu hình Gateway thay đổi giữa các dòng phiên bản và biến thể WebFlux/Web MVC. Ví dụ trên là cấu hình Gateway Server WebFlux 4.3; không sao chép nguyên xi sang Gateway 5.x hoặc Server MVC nếu chưa đối chiếu tài liệu đúng artifact.

## 6. Định tuyến qua Nginx reverse proxy

Nginx có thể nhận request HTTPS công khai rồi proxy tới management port nội bộ. Ví dụ dưới đây chỉ cho phép một số đường dẫn health và readiness:

```nginx
upstream shop_management {
    server shop-app:8081;
}

server {
    listen 443 ssl;
    server_name ops.example.com;

    # Health tổng quát.
    location = /ops/shop/actuator/health {
        proxy_pass http://shop_management/actuator/health;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Prefix /ops/shop;
    }

    # Readiness/liveness groups.
    location ^~ /ops/shop/actuator/health/ {
        proxy_pass http://shop_management/actuator/health/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Prefix /ops/shop;
    }

    # Mặc định không route các Actuator khác từ virtual host này.
    location ^~ /ops/shop/actuator/ {
        return 404;
    }
}
```

Đây là cấu hình minh họa; production cần thêm TLS certificate, access control, giới hạn mạng, rate limiting và logging theo chuẩn của tổ chức. Nếu cần Prometheus scrape, hãy tạo virtual host hoặc location riêng chỉ truy cập được từ mạng monitoring, rồi route `/actuator/prometheus` sau khi xác thực/allowlist phù hợp.

Nginx `proxy_pass` có URI `/actuator/...` thay thế phần prefix khớp trong `location`. Hãy kiểm tra kỹ dấu `/` cuối của `location` và `proxy_pass`: thay đổi dấu slash có thể làm path upstream khác dự kiến. Kiểm thử bằng `curl` trên cả public URL và upstream nội bộ.

## 7. Forwarded headers và prefix bên ngoài

Khi proxy kết thúc TLS hoặc bỏ một prefix, ứng dụng phía sau có thể chỉ nhìn thấy:

```text
scheme = http
host = shop-app:8081
path = /actuator/health
```

Trong khi client thực tế gọi:

```text
scheme = https
host = ops.example.com
path = /ops/shop/actuator/health
```

Proxy có thể truyền thông tin gốc qua `Forwarded` theo RFC 7239 hoặc các header phổ biến `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Port`, `X-Forwarded-For` và `X-Forwarded-Prefix`.

Với Spring Boot 3.5, cấu hình forwarded header strategy có thể dùng:

```yaml
server:
  forward-headers-strategy: framework
```

Các lựa chọn thường gặp:

| Giá trị | Ý nghĩa |
| --- | --- |
| `NONE` | Không xử lý forwarded headers |
| `NATIVE` | Dùng hỗ trợ native của embedded web server |
| `FRAMEWORK` | Dùng hỗ trợ forwarded headers của Spring Framework (`ForwardedHeaderFilter` hoặc transformer tương ứng) |

`X-Forwarded-Prefix` được hỗ trợ khác nhau tùy web server và phiên bản Spring Boot. Nếu ứng dụng cần tạo URL/redirect có prefix công khai, hãy kiểm tra support của phiên bản; Spring Framework strategy có thể phù hợp khi native server không xử lý prefix theo yêu cầu. Spring Boot phiên bản mới có thêm cấu hình forwarded prefix riêng cho native support.

Forwarded headers chỉ đáng tin khi request thực sự đến từ proxy được tin cậy. Proxy biên phải **loại bỏ hoặc ghi đè** các forwarded headers do client gửi tùy ý trước khi thêm giá trị chuẩn. Nếu ứng dụng trực tiếp tin `X-Forwarded-Host` từ internet, kẻ tấn công có thể làm sai host/scheme được ứng dụng sử dụng khi tạo redirect hoặc URL.

## 8. Bảo vệ forwarded headers và management network

Một cấu hình an toàn cần xác định rõ:

1. **Proxy nào được tin cậy?** Chỉ gateway/load balancer thuộc hạ tầng được quản lý mới được phép gửi forwarded headers có hiệu lực.
2. **Client có thể kết nối trực tiếp management port không?** Nếu không, firewall/network policy phải chặn đường truy cập trực tiếp.
3. **Endpoint nào cần được route?** Chỉ expose những ID cần thiết; tránh wildcard.
4. **Ai được phép truy cập?** Dùng authentication/authorization ở gateway và ứng dụng, không dựa riêng vào path khó đoán.
5. **Có cần TLS nội bộ không?** Nếu traffic đi qua network không hoàn toàn tin cậy, dùng TLS/mTLS giữa proxy và upstream.
6. **Có ghi log request quản trị không?** Ghi đủ để audit nhưng tránh log credentials hoặc dữ liệu nhạy cảm.

Không nên xem `X-Forwarded-For` là danh tính đã xác thực. Địa chỉ IP từ header chỉ có ý nghĩa khi chuỗi proxy được tin cậy và được cấu hình xử lý đúng. Authorization nên dựa trên credential/identity được xác thực, không chỉ trên header do client cung cấp.

## 9. Bảo vệ Actuator bằng Spring Security

Nếu Spring Security có mặt và ứng dụng không định nghĩa `SecurityFilterChain` riêng, Spring Boot có thể tự cấu hình bảo vệ Actuator. Khi tự định nghĩa security chain, auto-configuration lùi lại; ứng dụng phải tự viết đầy đủ quy tắc truy cập.

Ví dụ dưới đây cho phép health endpoint phục vụ probe và yêu cầu role `OPS` cho các Actuator endpoint khác:

```java
package com.example.shop.security;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class ActuatorSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .anyRequest().hasRole("OPS"))
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Ví dụ giả định ứng dụng đã cấu hình authentication provider/user hoặc tích hợp identity provider phù hợp. `EndpointRequest` giúp match endpoint Actuator theo endpoint ID và subpath, không cần hardcode `/actuator/**`; điều này hữu ích khi base path thay đổi.

Nếu ứng dụng có management port riêng hoặc nhiều `SecurityFilterChain`, hãy kiểm tra thứ tự và matcher thực tế. Nếu health details cần được bảo vệ, có thể yêu cầu role phù hợp thay vì `permitAll()`. Health endpoint chỉ nên tiết lộ thông tin tối thiểu cho probe.

## 10. Health endpoint và readiness qua gateway

Spring Boot Actuator Health hỗ trợ các nhóm kiểm tra như `liveness` và `readiness` khi được bật theo cấu hình phù hợp. Ví dụ:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,db
```

Các endpoint thường dùng:

```text
/actuator/health
/actuator/health/liveness
/actuator/health/readiness
```

Liveness cho biết process có còn sống để tiếp tục chạy hay không; readiness cho biết instance có nên nhận traffic nghiệp vụ hay chưa. Không đưa mọi dependency ngoài ứng dụng vào liveness check nếu việc đó có thể khiến orchestrator restart hàng loạt instance khi một hệ thống downstream tạm thời gặp sự cố.

Gateway route health endpoint phục vụ mục đích probe phải được thiết kế riêng. Nếu health endpoint chỉ dành cho Kubernetes kubelet trong cùng cluster, thường không cần đưa nó ra public internet. Có thể probe trực tiếp management port qua network nội bộ thay vì đi vòng qua public gateway.

## 11. Route Prometheus và module metadata như thế nào?

`/actuator/prometheus` thường được Prometheus server scrape định kỳ. Nên để scraper truy cập qua private network hoặc service discovery nội bộ, thay vì công khai endpoint trên gateway dành cho người dùng.

Ví dụ route chỉ dành cho mạng monitoring:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: shop-prometheus-internal
          uri: http://shop-app:8081
          predicates:
            - Path=/monitoring/shop/actuator/prometheus
          filters:
            - StripPrefix=2
```

Sau `StripPrefix=2`, upstream nhận `/actuator/prometheus`. Route cần được bảo vệ bằng network policy/allowlist và có thể thêm authentication nếu hạ tầng scrape hỗ trợ. Prometheus registry dependency phải có mặt; nếu không, endpoint `prometheus` không khả dụng.

Spring Modulith Insight có thể cung cấp endpoint `modulith` tại **`/actuator/modulith`** (nếu base path mặc định được giữ nguyên) để đọc metadata module của bản chạy. Chỉ route endpoint này cho nhóm vận hành/kiểm toán kiến trúc có quyền phù hợp. Nó có thể tiết lộ package, tên module và quan hệ dependency; không nên công khai mặc định.

## 12. Discovery page và các vấn đề path mapping

Actuator có discovery page liệt kê link endpoint dưới management base path. Khi proxy bỏ prefix, link trong discovery page có thể cần forwarded prefix được xử lý đúng để trỏ về public URL. Nếu không cần discovery page, có thể tắt:

```yaml
management:
  endpoints:
    web:
      discovery:
        enabled: false
```

Một số ứng dụng chọn expose riêng endpoint cần thiết và tắt discovery page để giảm thông tin công khai. Việc này không thay thế authentication hoặc network restriction.

Nếu dùng `management.endpoints.web.path-mapping`, ví dụ map health sang `/healthcheck`, route proxy phải chuyển đúng path nội bộ. Public `/ops/shop/health` có thể cần rewrite thành `/healthcheck`, không phải `/actuator/health`. Luôn lấy **path cuối cùng sau filter** làm chuẩn kiểm thử.

## 13. Kiểm thử định tuyến qua từng lớp

Không chỉ kiểm tra public URL; cần xác nhận cả upstream và chính sách truy cập:

| Lớp | Kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Ứng dụng nội bộ | `curl http://shop-app:8081/actuator/health` | `200` và health status phù hợp |
| Management port | Thử từ network không được phép | Không kết nối được |
| Gateway route | Gọi `/ops/shop/actuator/health` | Được chuyển tới đúng upstream path |
| Path rewrite | Bật access log tại upstream | Request path là `/actuator/health` |
| Authentication | Gọi endpoint ops không có credential | `401` hoặc `403` theo policy |
| Endpoint exposure | Gọi endpoint không được expose | `404` hoặc không được route |
| Forwarded headers | Kiểm tra host/scheme/prefix trong redirect/link nếu có | Phản ánh URL công khai đã được proxy xác thực |
| Monitoring route | Scrape Prometheus từ mạng monitoring | Chỉ scraper được phép truy cập |

Ví dụ kiểm tra public URL:

```bash
curl -i https://ops.example.com/ops/shop/actuator/health
```

Kiểm tra upstream trong network nội bộ:

```bash
curl -i http://shop-app:8081/actuator/health
```

Nếu endpoint yêu cầu Basic authentication trong môi trường thử nghiệm:

```bash
curl -i -u ops-user:REDACTED \
  https://ops.example.com/ops/shop/actuator/metrics
```

Không ghi mật khẩu thật vào shell history hoặc log CI. Dùng secret manager và cơ chế credential phù hợp khi kiểm thử tự động.

## 14. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `404` ở public URL nhưng upstream trả `200` | Gateway predicate không match hoặc StripPrefix/RewritePath sai | Kiểm tra route match và path sau filter |
| `404` ở cả upstream và gateway | Sai base path, context path, management base path hoặc endpoint chưa expose | Đọc cấu hình Actuator và thử endpoint nội bộ |
| `401` | Thiếu/sai credentials | Kiểm tra authentication tại gateway và app |
| `403` | Identity hợp lệ nhưng không đủ quyền hoặc IP không được allowlist | Kiểm tra role/authorization/network policy |
| `502` hoặc `503` | Gateway không kết nối được upstream hoặc management port chưa listen | Kiểm tra DNS, port, bind address và health của app |
| Redirect dùng `http` thay vì `https` | Forwarded proto không được xử lý hoặc proxy không ghi header | Cấu hình forwarded header strategy và proxy header |
| Discovery link mất `/ops/shop` | `X-Forwarded-Prefix` bị thiếu/không được hỗ trợ | Kiểm tra forwarded prefix theo phiên bản Boot/web server |
| Health public nhưng metrics cũng public | Route wildcard hoặc exposure quá rộng | Giới hạn endpoint route và exposure; thêm auth/network policy |
| Gateway route tới `localhost:8081` nhưng lỗi | `localhost` là gateway container, không phải app container | Dùng service DNS/IP upstream đúng |
| Prometheus không scrape được | Endpoint chưa expose, thiếu registry hoặc route/network sai | Kiểm tra dependency, `/actuator/prometheus` nội bộ và scraper network |
| `modulith` trả `404` | Chưa có Insight/Actuator integration hoặc chưa expose endpoint | Kiểm tra dependency và endpoint ID đúng phiên bản |

Hãy phân biệt lỗi **route**, **upstream**, **exposure** và **authorization**. Tăng wildcard exposure để chữa một lỗi `404` có thể biến vấn đề định tuyến thành lỗ hổng bảo mật.

## 15. Bài thực hành: đưa Actuator qua gateway nội bộ

**Bối cảnh:** `shop-app` chạy API ở port `8080`, management ở port `8081`. Gateway cung cấp public health URL cho load balancer và route Prometheus chỉ dành cho mạng monitoring.

| Bước | Thực hiện | Tiêu chí hoàn thành |
| --- | --- | --- |
| 1 | Cấu hình management port riêng | Actuator phục vụ ở `shop-app:8081` |
| 2 | Chỉ expose `health`, `prometheus`, `modulith` theo nhu cầu | Không bật wildcard |
| 3 | Kiểm tra health trực tiếp từ network nội bộ | Upstream trả kết quả hợp lệ |
| 4 | Tạo Gateway route public health bằng `StripPrefix=2` | Public path được map đúng `/actuator/health` |
| 5 | Tạo route Prometheus trong private network | Chỉ monitoring scraper truy cập được |
| 6 | Thêm Spring Security cho Actuator | Endpoint ops yêu cầu role phù hợp |
| 7 | Cấu hình forwarded headers nếu ứng dụng cần tạo URL công khai | Host/scheme/prefix chính xác |
| 8 | Thử path sai và endpoint chưa expose | Không vô tình mở endpoint khác |
| 9 | Thử truy cập trực tiếp management port từ mạng ngoài | Bị network policy chặn |
| 10 | Đối chiếu endpoint `modulith` với module graph | Metadata phản ánh đúng bản ứng dụng đang chạy |

### 15.1. Câu hỏi tự kiểm tra

1. **Actuator mặc định expose endpoint nào qua HTTP?** Thông thường chỉ `health`; endpoint khác cần cấu hình exposure.
2. **Public path `/ops/shop/actuator/health` dùng `StripPrefix=2` sẽ thành path nào?** `/actuator/health`.
3. **Tại sao tách management port không đủ để bảo vệ Actuator?** Vì port vẫn có thể bị truy cập trực tiếp nếu network không được giới hạn và endpoint không có authorization.
4. **`X-Forwarded-Prefix` dùng để làm gì?** Thể hiện prefix bên ngoài đã bị proxy bỏ trước khi chuyển request tới upstream, hữu ích khi ứng dụng tạo URL/redirect.
5. **Tại sao chỉ tin forwarded headers từ proxy được tin cậy?** Client có thể giả mạo header để làm sai host, scheme hoặc địa chỉ nguồn mà ứng dụng nhìn thấy.
6. **Có nên route `/actuator/**` công khai không?** Không theo mặc định; chỉ route endpoint cần thiết qua mạng và chính sách bảo vệ phù hợp.
7. **Khi Gateway trả `404`, cần kiểm tra gì trước?** Predicate, filter rewrite/strip, upstream path, base path và endpoint exposure.
8. **Endpoint `modulith` giúp gì cho vận hành?** Đọc module metadata của bản đang chạy để đối chiếu module graph và thiết kế kiến trúc.

## 16. Ghi nhớ

Định tuyến Actuator qua gateway/reverse proxy cần phân biệt **public path**, **path sau rewrite**, **upstream path**, **management base path** và **context path**. Spring Boot mặc định dùng `/actuator/{id}` và chỉ expose health qua HTTP; `management.endpoints.web.base-path`, `management.server.port` và `management.server.base-path` có thể thay đổi đường dẫn thực tế.

Spring Cloud Gateway có `StripPrefix` và `RewritePath` để map public URL tới endpoint nội bộ. Nginx có thể proxy các location được allowlist tới management port. Nếu proxy kết thúc TLS hoặc bỏ prefix, forwarded headers như `X-Forwarded-Proto`, `X-Forwarded-Host` và `X-Forwarded-Prefix` cần được ghi đúng và chỉ tin từ proxy đã xác thực.

Chỉ expose và route endpoint cần thiết; dùng authentication/authorization ở ứng dụng, giới hạn management network và kiểm thử cả public URL lẫn upstream. Đặc biệt, giữ `/actuator/prometheus` và module metadata trong mạng monitoring/ops phù hợp. Cách làm này giúp vận hành Spring Modulith qua Actuator mà vẫn kiểm soát được bề mặt quản trị của ứng dụng.

### Tài liệu tham khảo

- [Spring Boot — Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html): base path, management port, address và exposure.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint access, security và exposure.
- [Spring Boot 3.5 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): forwarded headers và `server.forward-headers-strategy`.
- [Spring Cloud Gateway 4.3 — `StripPrefix` Filter](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/stripprefix-factory.html): bỏ path segments trước khi proxy.
- [Spring Cloud Gateway 4.3 — `RewritePath` Filter](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/rewritepath-factory.html): rewrite path bằng regular expression.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): module observability và Actuator integration.
