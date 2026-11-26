# Bảo vệ các endpoint refresh và thay đổi trạng thái

## Mục tiêu và phạm vi

Trong chương **Actuator và sức khỏe** của module **SPRING_CLOUD_KUBERNETES**, bài này hướng dẫn kiểm soát những thao tác quản trị có thể thay đổi ứng dụng đang chạy: refresh cấu hình, thay đổi log level, cập nhật Environment, khởi động lại hoặc dừng ứng dụng.

Bối cảnh thực hành là `order-service` chạy nhiều Pod trên Kubernetes. Configuration Watcher cần gửi thông báo refresh khi ConfigMap hoặc Secret thay đổi. Kubelet cần đọc probe, Prometheus cần đọc metric, còn người gọi nghiệp vụ không được tự kích hoạt thao tác quản trị.

Kết quả cần đạt:

- Chỉ bật và expose endpoint thực sự cần.
- Phân quyền theo danh tính, thao tác và HTTP method.
- Thiết kế đường gọi an toàn cho Configuration Watcher.
- Hiểu RBAC Kubernetes, NetworkPolicy và Spring Security bảo vệ những lớp khác nhau.
- Giữ probe hoạt động mà không mở toàn bộ Actuator.
- Xác minh cả trường hợp được phép và bị từ chối.

Ví dụ dùng ứng dụng Servlet/Spring MVC trên JVM với Spring Boot 3.5, Spring Security 6.5, Spring Cloud Commons 4.3 và Spring Cloud Kubernetes 3.3; các dependency Spring Cloud được quản lý bằng BOM tương thích. WebFlux dùng API security khác, không chép nguyên `SecurityFilterChain` của Servlet sang đó.

## 1. Endpoint thay đổi trạng thái là một quyền vận hành

### 1.1 Refresh không phải phép kiểm tra sức khỏe

`POST /actuator/refresh` có thể nạp lại cấu hình và làm mới bean trong refresh scope. Dù request không có body, nó vẫn gây thay đổi trong tiến trình. Không dùng nó làm readiness probe hoặc lịch kiểm tra định kỳ chỉ để xem ứng dụng có sống không.

Những tác động cần cân nhắc gồm tạo lại bean, đổi chính sách nghiệp vụ, thay credential hoặc làm phát sinh các yêu cầu kết nối mới. Refresh thành công ở cấp phương thức cũng chưa chứng minh mọi target lazy đã khởi tạo và mọi replica đã áp dụng cấu hình.

Spring Cloud Context còn cung cấp những khả năng quản trị khác như cập nhật Environment, restart và các thao tác lifecycle tùy endpoint được bật. Xem [Spring Cloud Context: Endpoints](https://docs.spring.io/spring-cloud-commons/reference/4.3/spring-cloud-commons/application-context-services.html#_endpoints).

| Khả năng | Loại quyền nên xét | Chính sách khởi đầu |
| --- | --- | --- |
| GET liveness/readiness | Đọc trạng thái tối thiểu | Cho kubelet đọc đúng đường probe |
| GET metric | Đọc thông tin vận hành | Danh tính giám sát riêng |
| POST refresh | Thay đổi cấu hình trong tiến trình | Caller có quyền refresh riêng |
| POST Environment | Ghi trực tiếp vào cấu hình chạy | Giữ tắt nếu không có nhu cầu rõ ràng |
| Thay log level | Thay đổi trạng thái và lượng dữ liệu log | Quyền vận hành riêng, có audit |
| Restart, shutdown, pause/resume | Tác động vòng đời ứng dụng | Mặc định không cấp cho caller refresh |
| Đọc heap dump, env, configprops | Đọc dữ liệu có thể nhạy cảm | Không coi là quyền đọc giám sát thông thường |

Đây là phân loại quyền đề xuất. Endpoint cụ thể chỉ tồn tại nếu dependency, auto-configuration và cấu hình phiên bản tương ứng tạo nó.

### 1.2 Quyền refresh và quyền sửa nguồn là hai việc

Caller có quyền refresh thường không gửi bộ giá trị mới trong body để chỉ định các key sẽ được nạp. Nó yêu cầu ứng dụng đọc lại các nguồn đã cấu hình. Vì vậy, bảo vệ endpoint chưa đủ nếu một danh tính khác có thể sửa ConfigMap, Secret hoặc nguồn cấu hình mà ứng dụng tin cậy.

Ngược lại, một người có quyền sửa nguồn có thể gián tiếp gây refresh thông qua Watcher. Cần quản lý cả hai đường:

~~~text
Quyền sửa nguồn -> nguồn thay đổi -> Watcher -> refresh
Quyền gọi endpoint -> refresh các nguồn ứng dụng đang tin cậy
~~~

Nếu chỉ cho phép thay đổi một tập key nghiệp vụ, áp dụng giới hạn ở mô hình nguồn, validation và quy trình cập nhật tương ứng. Danh sách khóa trả về từ endpoint refresh không phải allowlist quyền ghi.

## 2. Phân biệt các lớp bảo vệ

| Lớp | Câu hỏi được trả lời | Không thay thế được |
| --- | --- | --- |
| Endpoint access | Thao tác của endpoint có được ứng dụng cho tồn tại không? | Xác thực người gọi HTTP |
| HTTP/JMX exposure | Endpoint được đưa ra qua công nghệ nào? | Phân quyền từng caller |
| Spring Security | Caller là ai, có authority nào, được làm thao tác nào? | Cô lập mạng hoặc quyền sửa ConfigMap |
| TLS/mTLS | Kênh truyền và danh tính ở lớp TLS được bảo vệ thế nào? | Quyền nghiệp vụ nếu chưa ánh xạ rõ |
| NetworkPolicy | Pod/namespace/IP nào có thể kết nối tới cổng? | Quy tắc theo URL, HTTP method, JWT scope |
| RBAC Kubernetes | Danh tính nào được thao tác resource trên API server? | Quy tắc HTTP bên trong ứng dụng Spring |
| Audit và kiểm soát tần suất | Ai đã yêu cầu thao tác, có lặp bất thường không? | Các lớp ngăn truy cập trái phép |

Spring Boot 3.5 phân biệt access của endpoint với việc expose endpoint. Giá trị `access: unrestricted` cho phép thao tác endpoint, không có nghĩa bỏ xác thực hay cho anonymous gọi HTTP. Xem [Spring Boot: Controlling Access và Exposing Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html).

Ví dụ, Role cho phép một service account `list configmaps` không tự cấp quyền `POST /actuator/refresh`. Hai request đi tới hai server và chịu hai chính sách khác nhau.

## 3. Thiết kế ma trận quyền trước khi cấu hình

Giả sử hệ thống dùng OAuth 2.0 JWT với audience `order-service` và các scope sau:

| Caller | Authority sau xác thực | Quyền dự kiến |
| --- | --- | --- |
| Kubelet | Không gửi credential ứng dụng trong mẫu này | GET đúng hai URL probe |
| Prometheus | `SCOPE_observe.read` | GET health/metric được expose |
| Refresh controller | `SCOPE_config.refresh` | POST refresh |
| Người gọi API đọc đơn hàng | `SCOPE_orders.read` | GET API nghiệp vụ đã chỉ định |
| Token sai audience, hết hạn hoặc chữ ký không hợp lệ | Không có Authentication hợp lệ | Bị từ chối |
| Người có token hợp lệ nhưng thiếu scope | Không đủ authority cho thao tác | Bị từ chối |

Tên scope trong bảng là lựa chọn của ứng dụng. Authorization Server phải thực sự cấp chúng cho đúng client. Spring Security mặc định ánh xạ scope JWT sang authority có tiền tố `SCOPE_`; cấu hình issuer và audience phải phù hợp với token được phát hành. Xem [OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html).

Tách scope giúp một token chỉ đọc metric không có quyền refresh. Không dùng quy tắc “có token hợp lệ là làm được mọi thao tác Actuator”.

Nếu cùng một credential được chia sẻ cho tất cả Watcher, công cụ giám sát và người vận hành, việc thu hồi quyền và truy vết sẽ khó hơn. Hãy dùng danh tính riêng theo vai trò và thời hạn credential phù hợp.

## 4. Chỉ mở các endpoint cần thiết

### 4.1 Dependency tối thiểu cho ví dụ

Giả định dự án đã có web starter và cơ chế nạp cấu hình Kubernetes. Ví dụ security cần:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Endpoint refresh cần Spring Cloud Context, thường được kéo vào bởi các starter liên quan; nếu khai báo trực tiếp, dùng `org.springframework.cloud:spring-cloud-context` theo BOM. Endpoint Prometheus cần `io.micrometer:micrometer-registry-prometheus`; bỏ nó khỏi exposure nếu không sử dụng.

### 4.2 Cấu hình theo hướng chỉ mở những gì đã chọn

Ví dụ `application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OPS_ISSUER_URI}
          audiences:
            - order-service

management:
  server:
    port: 9090
  endpoints:
    access:
      default: none
    web:
      exposure:
        include: health,refresh,prometheus
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    health:
      access: read-only
      show-details: never
      show-components: never
      probes:
        enabled: true
    prometheus:
      access: read-only
    refresh:
      access: unrestricted
    env:
      access: none
      post:
        enabled: false
    shutdown:
      access: none
~~~

Điểm đáng chú ý:

- Mặc định access là `none`; các endpoint cần dùng được mở rõ ràng.
- Không dùng `web.exposure.include: "*"` cho một nhu cầu chỉ cần refresh.
- Health và Prometheus chỉ cần thao tác đọc.
- Refresh cần thao tác ghi nên không thể chỉ có `access: read-only`.
- HTTP security và JMX là các đường truy cập khác nhau; mẫu không expose endpoint qua JMX.
- `show-details: never` và `show-components: never` giúp probe chỉ trả thông tin tối thiểu.

Nếu môi trường đặt `management.endpoints.access.max-permitted=read-only`, giới hạn toàn cục đó có thể ngăn thao tác refresh dù cấu hình riêng của refresh là `unrestricted`. Xem lại cấu hình hiệu lực khi endpoint không xuất hiện.

Cấu hình trên giả định management port `9090` riêng, base path `/actuator` và không có management context path bổ sung. Nó chưa cấu hình TLS; phần HTTPS bên dưới phải được bổ sung trước khi gửi credential qua đường quản trị không được bảo vệ bằng một lớp truyền tải tương đương.

## 5. Phân quyền theo endpoint và HTTP method

### 5.1 Hai filter chain có phạm vi rõ ràng

Ví dụ sau chỉ dùng Bearer JWT cho các request có xác thực, không dùng form login, HTTP Basic hoặc cookie phiên để cấp quyền vận hành:

~~~java
package com.example.orders.security;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {
        RequestMatcher refreshPost = new AndRequestMatcher(
                EndpointRequest.to("refresh"),
                request -> HttpMethod.POST.matches(request.getMethod()));

        RequestMatcher monitoringGet = new AndRequestMatcher(
                EndpointRequest.to("health", "prometheus"),
                request -> HttpMethod.GET.matches(request.getMethod()));

        http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET,
                    "/actuator/health/liveness",
                    "/actuator/health/readiness")
                    .permitAll()
                .requestMatchers(refreshPost)
                    .hasAuthority("SCOPE_config.refresh")
                .requestMatchers(monitoringGet)
                    .hasAuthority("SCOPE_observe.read")
                .anyRequest().denyAll())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .logout(AbstractHttpConfigurer::disable)
            .csrf(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .logout(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Mẫu chỉ minh họa API nghiệp vụ đọc đơn hàng; các URL khác bị từ chối. Khi ghép vào dự án có API khác, bổ sung quy tắc nghiệp vụ có chủ đích vào chain thứ hai.

Giải thích các quyết định:

1. `EndpointRequest` xác định Actuator theo endpoint được đăng ký, thay vì chỉ dựa vào tiền tố URL.
2. Chỉ `POST` đến refresh được cấp cho `SCOPE_config.refresh`; quyền này không mở mọi method hay endpoint.
3. Hai URL probe được permit riêng; không dùng `permitAll` cho toàn bộ `/actuator/**`.
4. Nhánh giám sát chỉ cho GET đối với các endpoint đọc đã chọn.
5. `anyRequest().denyAll()` trong chain Actuator giữ nguyên trạng thái từ chối khi có endpoint mới.
6. Chain thứ hai không có `securityMatcher` nên nhận các request còn lại; không để một nhóm URL rơi ngoài mọi filter chain.
7. Một token chỉ có `orders.read` không đủ để refresh dù nó hợp lệ với ứng dụng.

Khi bạn tự khai báo `SecurityFilterChain`, Spring Boot giao quyền kiểm soát HTTP security cho cấu hình của bạn; đừng mặc định rằng mọi quy tắc Actuator cũ vẫn được tự áp dụng. Quy tắc chọn chain và hậu quả khi không có chain phù hợp được mô tả trong [Spring Security: Java Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html).

### 5.2 Vì sao tắt CSRF trong chain quản trị này?

Mẫu tắt CSRF **trong chain Actuator dành cho máy gọi bằng Bearer token**, với những giả định cụ thể:

- Credential được gửi chủ động trong header `Authorization: Bearer …`.
- Không dùng session cookie, form login hay HTTP Basic để xác thực các thao tác quản trị.
- Browser không tự mang một credential được ứng dụng chấp nhận tới endpoint này theo cơ chế cookie phiên.
- Network và kênh truyền vẫn được bảo vệ; token không bị lộ.

Đây không phải lý do để tắt CSRF trên mọi chain của ứng dụng. Chỉ đặt `STATELESS` chưa đủ để kết luận không cần CSRF: một cơ chế xác thực được browser tự gửi vẫn phải được đánh giá riêng. Nếu quản trị qua trình duyệt với session/cookie, giữ bảo vệ CSRF và gửi token CSRF đúng cách. Xem [Spring Security: CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html).

CORS không thay thế xác thực, phân quyền hoặc CSRF. Một policy CORS chặt không ngăn máy trong cluster gửi HTTP trực tiếp tới endpoint.

### 5.3 Đường probe và context path phải khớp

`EndpointRequest` hỗ trợ xác định endpoint, nhưng hai đường probe permit trong mẫu vẫn là chuỗi URL cụ thể. Khi đổi base path hoặc thêm các đường `/livez`, `/readyz`, cập nhật security tương ứng và kiểm tra trên từng cổng.

Cho anonymous đọc đúng probe không có nghĩa anonymous được xem toàn bộ cây health. Không để group override `show-details` thành `always` rồi vô tình xuất metadata, địa chỉ nội bộ hoặc thông tin dependency qua probe.

Nếu kubelet vô tình gửi một Bearer token sai/hết hạn, authentication filter vẫn có thể từ chối trước khi tới quy tắc permit. Probe trong mẫu không cần mang token ứng dụng.

## 6. Bảo vệ kênh truyền và tách cổng quản trị

Bearer token cấp quyền cho bên nắm giữ nó. Tách management port giúp tổ chức đường mạng, nhưng tự nó không mã hóa lưu lượng hay xác thực caller.

Có thể cấu hình HTTPS trực tiếp cho management server bằng cách bổ sung các thuộc tính sau vào `management.server` đã có:

~~~yaml
ssl:
  enabled: true
  key-store: file:/etc/ops-tls/server.p12
  key-store-type: PKCS12
  key-store-password: ${OPS_TLS_KEYSTORE_PASSWORD}
~~~

Keystore và mật khẩu được cung cấp qua cơ chế Secret/secret store phù hợp, không ghi giá trị thật vào repository hoặc log. Certificate phải có SAN phù hợp hostname caller sử dụng; client cần tin cậy CA tương ứng.

Một phương án khác là TLS/mTLS qua proxy hoặc service mesh. Khi đó, phải bảo đảm không tồn tại đường gọi trực tiếp bỏ qua lớp xác thực được tin cậy. Nếu proxy xác thực workload nhưng ứng dụng vẫn yêu cầu Bearer JWT như mẫu, caller/proxy vẫn cần cung cấp JWT hợp lệ; chứng chỉ mTLS không tự tạo authority `SCOPE_config.refresh` trong Spring.

Với probe tới cổng HTTPS `9090`, fragment cấu hình có thể là:

~~~yaml
readinessProbe:
  httpGet:
    scheme: HTTPS
    path: /actuator/health/readiness
    port: 9090
  periodSeconds: 5
  timeoutSeconds: 2
livenessProbe:
  httpGet:
    scheme: HTTPS
    path: /actuator/health/liveness
    port: 9090
  periodSeconds: 10
  timeoutSeconds: 2
~~~

Kubelet HTTP probe dùng HTTPS không phải cơ chế xác thực caller bằng JWT hay mTLS. Việc kiểm tra probe ở cổng quản trị riêng cũng không chứng minh hạ tầng phục vụ HTTP trên cổng nghiệp vụ đang nhận được kết nối; lựa chọn cổng probe cần được kiểm tra cùng thiết kế availability.

## 7. Cho Configuration Watcher gọi đúng danh tính

### 7.1 Đường gọi thực tế

Với HTTP implementation, Watcher tìm các instance bằng DiscoveryClient rồi gửi request đến endpoint refresh. Nếu ứng dụng dùng management port/path khác, đích mặc định có thể không còn đúng. Cấu hình annotation `boot.spring.io/actuator` trên Service hoặc thiết lập actuator port/path của Watcher cần khớp bản triển khai. Xem [Configuration Watcher: HTTP Implementation](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/spring-cloud-kubernetes-configuration-watcher.html#_http_implementation).

Ví dụ annotation khi ứng dụng đã bật HTTPS ở cổng `9090`:

~~~yaml
metadata:
  annotations:
    boot.spring.io/actuator: https://:9090/actuator
~~~

Đây chỉ là fragment metadata của Service. Annotation mô tả đường gọi; nó không chứa credential và không tự thiết lập trust CA, client certificate hay Bearer token.

Một đường gọi đầy đủ có các bước:

~~~mermaid
flowchart LR
    C[ConfigMap hoặc Secret thay đổi] --> W[Configuration Watcher]
    W --> D[DiscoveryClient tìm instance]
    D --> N[Đích và cổng quản trị đã kiểm soát]
    N --> T[TLS và kiểm tra trust]
    T --> A[Xác thực caller]
    A --> Z[Kiểm tra quyền config.refresh]
    Z --> R[Thực hiện refresh]
    R --> V[Xác minh cấu hình từng Pod]
~~~

### 7.2 Service account không tự trở thành scope ứng dụng

Service account xác định danh tính workload trong Kubernetes; token được phát hành còn có audience và thời hạn. Xem [Kubernetes: Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/).

Không mặc định lấy token dùng với API Kubernetes rồi gửi sang ứng dụng:

- Ứng dụng phải tin cậy issuer, khóa ký và audience tương ứng.
- Danh tính phải được ánh xạ rõ thành authority mà ứng dụng chấp nhận.
- Token service account không tự có scope OAuth `config.refresh`.
- Quyền `get/list/watch` trong Role không biến thành `SCOPE_config.refresh`.

Nếu tổ chức muốn dùng token service account làm credential cho ứng dụng, phải thiết kế việc phát token đúng audience, xác minh và ánh xạ danh tính riêng. Đó là một mô hình xác thực cần triển khai, không phải tính năng tự có của RBAC.

### 7.3 Chọn cơ chế mà transport thực sự hỗ trợ

| Cách tích hợp | Điều phải triển khai |
| --- | --- |
| OAuth 2.0 machine client | Client lấy token đúng audience/scope, làm mới token và gửi header Bearer |
| mTLS/workload identity | Trust chain, nhận diện đúng workload và policy cho phép thao tác quản trị |
| Proxy kiểm soát vận hành | Xác thực caller, giới hạn đích và ngăn đường gọi bỏ qua proxy |
| Spring Cloud Bus | Xác thực broker, quyền publish/consume và phạm vi phân phối event |

Ví dụ Spring Security trong bài yêu cầu JWT. Để Watcher dùng được, HTTP client của Watcher hoặc thành phần trung gian phải thực sự gửi JWT hợp lệ trên mỗi request cần xác thực. Đừng chỉ đặt một biến môi trường tên “token” rồi giả định thư viện tự sử dụng nó.

Kiểm tra khả năng cấu hình/customize HTTP client của **đúng phiên bản Watcher** đang dùng. Nếu transport chưa hỗ trợ cơ chế nhận token và xoay token cần thiết, phải mở rộng transport hoặc dùng một kiến trúc vận chuyển đã được kiểm soát. Không giải quyết khoảng trống đó bằng cách `permitAll` cho refresh.

Với một watcher/client tự mở rộng, cần có các đặc tính:

- Credential được lấy từ nguồn có kiểm soát, không từ ConfigMap công khai.
- Token ngắn hạn được làm mới trước khi hết hạn; file Secret thay đổi chỉ có tác dụng nếu client có cơ chế đọc lại tương ứng.
- Request xác minh chứng chỉ và hostname đích.
- Không chuyển tiếp credential sang một host tùy ý qua redirect hoặc metadata không tin cậy.
- Phạm vi đích nằm trong các namespace/ứng dụng đã cho phép.
- Lỗi `401`, `403`, TLS và lỗi xử lý refresh được phân loại riêng.

Danh sách này mô tả yêu cầu cho transport, không phải các property built-in của Spring Cloud Kubernetes.

### 7.4 Bảo vệ cả quyền thay đổi metadata và nguồn

Người sửa được Service annotation, endpoint hoặc dữ liệu dùng để chọn ứng dụng đích có thể ảnh hưởng nơi controller gửi request. Hạn chế quyền sửa những resource đó, đặc biệt khi controller mang credential có quyền ở nhiều ứng dụng.

Quyền đọc Secret của Watcher cũng phải phù hợp tính năng thực sự dùng. Không cấp quyền Secret chỉ vì đang dùng ConfigMap hoặc discovery. Phân tách danh tính vận hành, tránh dùng một credential có quyền quản trị toàn cluster để gọi endpoint ứng dụng.

## 8. NetworkPolicy giảm bề mặt truy cập

### 8.1 Tách đường metric, refresh và nghiệp vụ

Ví dụ dưới đây áp dụng cho các Pod `order-service` trong namespace `apps`. Nó cho Watcher trong `platform-ops` và Prometheus trong `monitoring` kết nối đến cổng quản trị `9090`; cho một caller nghiệp vụ mẫu kết nối `8080`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: order-service-ingress
  namespace: apps
spec:
  podSelector:
    matchLabels:
      app: order-service
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: platform-ops
          podSelector:
            matchLabels:
              app: configuration-watcher
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring
          podSelector:
            matchLabels:
              app: prometheus
      ports:
        - protocol: TCP
          port: 9090
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: apps
          podSelector:
            matchLabels:
              app: checkout-client
      ports:
        - protocol: TCP
          port: 8080
~~~

Tên namespace và label là ví dụ; thay bằng inventory của cluster. Policy này không tự mở đường cho ingress controller hoặc các caller nghiệp vụ khác. Khi áp dụng, phải mô tả đầy đủ các nguồn hợp lệ để không cắt nhầm lưu lượng.

Trong mỗi phần tử `from`, `namespaceSelector` và `podSelector` kết hợp để chọn Pod có label đúng **trong** namespace đúng. Các phần tử `from` riêng là những nguồn được phép khác nhau.

NetworkPolicy cần CNI thực thi. Các policy cho cùng Pod có tính cộng dồn: một policy khác mở rộng ingress có thể làm phạm vi thực tế rộng hơn ví dụ này. Xem [Kubernetes: Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/).

### 8.2 Những điều policy này chưa làm

- Prometheus được tới cổng `9090` nhưng vẫn không có quyền POST refresh vì thiếu scope.
- NetworkPolicy không phân biệt `/actuator/prometheus` với `/actuator/refresh`.
- Ingress policy không thiết lập egress cho Watcher, issuer, DNS hoặc API Kubernetes.
- Label không phải một danh tính mật mã. Quyền tạo Pod hoặc sửa label trong namespace phải được kiểm soát.
- Traffic liên quan node/kubelet, host network, mesh và port-forward có đặc điểm phụ thuộc mô hình mạng. Không suy từ một phép thử Pod-to-Pod rằng mọi đường vào đã bị chặn.

Không đưa management port vào public Ingress, NodePort hay LoadBalancer nếu không có nhu cầu quản trị rõ ràng. Chỉ bỏ cổng khỏi Service chưa đủ để ngăn Pod khác gọi trực tiếp Pod IP khi mạng vẫn cho phép.

Port-forward là một đường quản trị qua API Kubernetes; cần kiểm soát quyền trên subresource `pods/portforward` và vẫn giữ xác thực tại ứng dụng. Nó không tự biến người dùng `kubectl` thành caller có scope refresh.

Kubelet probe dùng HTTPS bỏ qua việc xác minh certificate của server theo cơ chế HTTP probe. Vì thế, HTTPS probe không thay thế việc các client quản trị thật phải xác minh CA/hostname. Xem [Kubernetes: HTTP probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

## 9. Kiểm soát các thao tác thay đổi trạng thái khác

### 9.1 Không cấp quyền dây chuyền từ refresh

Ngay cả khi cùng phục vụ vận hành, những thao tác sau có tác động khác nhau:

| Thao tác | Cách kiểm soát phù hợp |
| --- | --- |
| Thay log level | Scope riêng; giới hạn logger có thể chỉnh; audit và thời hạn khi cần |
| Cập nhật Environment | Giữ tắt nếu không dùng; nếu cần thì giới hạn key và caller |
| Restart/shutdown | Quyền vòng đời riêng; xét ảnh hưởng replica, rollout và phục hồi |
| Pause/resume | Chính sách riêng theo lifecycle thực tế; không mặc định tương đương readiness |
| Custom endpoint làm Pod từ chối traffic | Quyền drain riêng, trạng thái rõ ràng và đường khôi phục |
| Thao tác qua Bus | Quyền phát lệnh và phạm vi nhận độc lập với quyền endpoint local |

Mẫu access mặc định `none` và security `denyAll` giúp các thao tác này không tự mở chỉ vì caller có quyền refresh. Nếu bổ sung endpoint mới, phải cập nhật cả access, exposure, method và authority tương ứng.

Một JWT hợp lệ không ngăn việc caller lặp lại nhiều lần một thao tác được cấp quyền. Đặt giới hạn tần suất, giới hạn đồng thời hoặc điều phối tuần tự ở nơi các request thực sự đi qua. Một gateway chỉ giới hạn public traffic không bảo vệ được đường gọi nội bộ bỏ qua gateway.

### 9.2 Readiness không phải trạng thái đăng ký dịch vụ

Health endpoint là đường đọc; không mặc định tồn tại API POST health để đổi readiness.

Nếu tự viết endpoint “drain”, hãy định nghĩa rõ:

- Caller nào được chuyển trạng thái và lý do được ghi nhận ra sao.
- Trạng thái ảnh hưởng tới Pod nào và trong bao lâu.
- Khác biệt giữa từ chối request mới và xử lý request đang chạy.
- Ai có quyền khôi phục, và điều gì xảy ra khi JVM restart.

Spring Cloud Commons có endpoint `serviceregistry` trong những cấu hình có `Registration` phù hợp, nhưng trạng thái đó phụ thuộc implementation. Không chép mô hình trạng thái của Eureka rồi suy rằng nó trực tiếp thay Kubernetes Pod readiness hoặc EndpointSlice. Xem [Service Registry Actuator Endpoint](https://docs.spring.io/spring-cloud-commons/reference/4.3/spring-cloud-commons/common-abstractions.html#_service_registry_actuator_endpoint).

Với Kubernetes, readiness của Pod và cách nền tảng cập nhật endpoint phải được kiểm chứng theo cơ chế triển khai thực tế.

### 9.3 Bus mở một đường điều khiển khác

Nếu dùng Bus, việc khóa HTTP refresh local không tự chặn một refresh event đến từ broker. Cần kiểm soát quyền publish, consume, định danh service/instance và phạm vi event.

Các endpoint như `busrefresh` và `busenv` cũng phải được đánh giá riêng; `busenv` có khả năng truyền cập nhật Environment tới nhiều instance. Xem [Spring Cloud Bus: Bus Endpoints](https://docs.spring.io/spring-cloud-bus/docs/4.0.x/reference/html/#bus-endpoints).

Không mở endpoint Bus chỉ vì đang dùng broker cho nghiệp vụ. Nếu không có nhu cầu refresh động, có thể giữ các endpoint quản trị này đóng và đưa thay đổi cấu hình qua rollout có kiểm soát.

## 10. Audit thao tác mà không lộ credential

Một bản ghi audit cho thao tác quản trị có thể chứa:

~~~json
{
  "event": "management_operation",
  "operation": "refresh",
  "stage": "authorization",
  "outcome": "denied",
  "caller": "metrics-reader",
  "namespace": "apps",
  "pod": "order-service-example-a",
  "requestId": "example-request-id",
  "reasonCode": "missing_required_authority"
}
~~~

Đây là schema đề xuất, không phải log tự có từ cấu hình Java trong bài.

Nên tách các mốc:

- Authentication thất bại: chưa có danh tính đã xác minh.
- Authorization bị từ chối: danh tính đã xác minh nhưng thiếu quyền.
- Thao tác được chấp nhận: request đi vào xử lý.
- Refresh hoàn tất hoặc lỗi: kết quả xử lý trong ứng dụng.
- Cấu hình được xác minh: bean/replica đã dùng dữ liệu mong muốn.

Không ghi token, Authorization header, client secret, mật khẩu keystore hoặc giá trị Secret. Danh tính `caller` phải lấy từ Authentication đã xác minh; không tin một header tự khai báo như `X-User` nếu chưa có hợp đồng với proxy tin cậy.

Nguồn IP cũng có thể bị ảnh hưởng bởi proxy. Chỉ sử dụng forwarded header trong cấu hình trust phù hợp; không dựa vào một header IP do caller tự gửi để cấp quyền refresh.

Phản hồi refresh có thể chứa tên key thay đổi. Xem nó như dữ liệu quản trị; tránh công bố rộng hoặc đưa toàn bộ vào metric label.

Cảnh báo có ích gồm tăng `401/403`, caller giám sát cố gọi thao tác ghi, refresh lặp bất thường và lỗi xác minh cấu hình sau thao tác đã được phép. Khi dùng metric, giữ nhãn hữu hạn theo operation/outcome; request ID, subject và revision nên nằm ở log/audit với chính sách lưu trữ phù hợp.

## 11. Thực hành xác minh các ranh giới

### 11.1 Chuẩn bị môi trường kiểm tra

Trong lab, chuẩn bị:

- Một Pod ứng dụng có endpoint refresh thật và cấu hình nạp nguồn đúng.
- Issuer phát token cho audience `order-service`.
- Token ngắn hạn riêng cho `config.refresh`, `observe.read` và `orders.read`.
- Certificate management server và CA phù hợp, nếu dùng cấu hình HTTPS.
- Cơ chế xác minh một revision cấu hình không nhạy cảm tại đúng Pod.

Đừng dùng credential sản xuất để thử các trường hợp bị từ chối. Các biến môi trường chứa token trong lệnh mẫu được cung cấp bởi cơ chế credential của lab; không in giá trị token ra màn hình hay lưu vào nội dung tài liệu.

Port-forward tới management port trong một terminal:

~~~powershell
kubectl -n apps port-forward pod/<ten-pod-order> 19090:9090
~~~

Thay placeholder bằng tên Pod thật. Ở terminal khác, chuẩn bị tùy chọn curl cho hostname trùng SAN của certificate:

~~~powershell
$opsBase = "https://orders-ops.example.internal:19090"
$opsCurl = @(
    "--silent",
    "--show-error",
    "--include",
    "--cacert", "C:/lab/ops-ca.crt",
    "--resolve", "orders-ops.example.internal:19090:127.0.0.1"
)
~~~

Hostname và đường CA là ví dụ, cần thay theo lab. `--resolve` giữ hostname kiểm tra certificate trong khi kết nối tới cổng local của port-forward. Không dùng `--insecure` để che lỗi TLS trong phép xác minh.

### 11.2 Probe được đọc, refresh anonymous bị chặn

~~~powershell
curl.exe @opsCurl "$opsBase/actuator/health/liveness"
curl.exe @opsCurl -X POST "$opsBase/actuator/refresh"
~~~

Probe trả kết quả sức khỏe tương ứng, thường HTTP 200 hoặc 503 theo trạng thái. Request refresh không credential phải bị chặn trước khi thực hiện; với Resource Server như mẫu, thông thường là 401.

Kiểm tra cả bằng chứng không có lần refresh tương ứng trong log/metric và cấu hình consumer không thay đổi do request bị từ chối. Chỉ nhìn một status code chưa đủ nếu đường xử lý có proxy hoặc handler tùy chỉnh.

### 11.3 Token hợp lệ nhưng sai quyền

~~~powershell
curl.exe @opsCurl -X POST -H "Authorization: Bearer $env:LAB_OBSERVER_TOKEN" "$opsBase/actuator/refresh"
curl.exe @opsCurl -X POST -H "Authorization: Bearer $env:LAB_ORDERS_TOKEN" "$opsBase/actuator/refresh"
~~~

Với JWT hợp lệ nhưng chỉ có scope đọc tương ứng, dự kiến 403. Không có side effect refresh.

Sau đó xác minh observer vẫn đọc được metric:

~~~powershell
curl.exe @opsCurl -H "Authorization: Bearer $env:LAB_OBSERVER_TOKEN" "$opsBase/actuator/prometheus"
~~~

Không dùng một token có đồng thời mọi scope để chứng minh sự phân tách quyền; nó làm mất ý nghĩa của phép thử.

### 11.4 Token có quyền refresh chỉ gọi đúng thao tác

~~~powershell
curl.exe @opsCurl -X POST -H "Authorization: Bearer $env:LAB_REFRESH_TOKEN" "$opsBase/actuator/refresh"
~~~

Nếu authentication, authorization và cơ chế refresh đều đúng, endpoint có thể trả 200 với tập key thay đổi, kể cả `[]` khi không có chênh lệch được phát hiện. Nếu xử lý nguồn hoặc bean lỗi, một kết quả lỗi xử lý không có nghĩa security đã từ chối caller.

Tiếp tục thử cùng token ở thao tác không được cấp:

~~~powershell
curl.exe @opsCurl -H "Authorization: Bearer $env:LAB_REFRESH_TOKEN" "$opsBase/actuator/refresh"
curl.exe @opsCurl -X POST -H "Authorization: Bearer $env:LAB_REFRESH_TOKEN" "$opsBase/actuator/shutdown"
curl.exe @opsCurl -X POST -H "Authorization: Bearer $env:LAB_REFRESH_TOKEN" "$opsBase/actuator/env"
~~~

GET refresh không được cấp bởi rule POST trong mẫu. Endpoint shutdown/env đã đóng; request không được thực hiện thao tác. Status quan sát có thể là 401, 403 hoặc 404 tùy endpoint có tồn tại và chain/error handling thực tế. Tiêu chí bắt buộc là không có thao tác trái phép, không chỉ một mã HTTP cố định.

### 11.5 Token sai và đường mạng bị chặn

| Phép thử | Kết quả cần xác minh |
| --- | --- |
| Token hết hạn | Authentication bị từ chối |
| Token sai issuer/audience | Authentication bị từ chối |
| Token chữ ký sai | Authentication bị từ chối |
| Observer gửi POST refresh | Authorization bị từ chối |
| Caller ngoài nguồn NetworkPolicy cho phép | Kết nối tới management port không thành công theo CNI/policy thực tế |
| Caller mạng được phép nhưng không có token | Không vượt qua authentication |
| JMX không được expose | Không có đường quản trị JMX ngoài thiết kế |
| Public Ingress | Không cung cấp đường đi tới endpoint quản trị |
| Probe kubelet sau triển khai security | Vẫn hoạt động trên đúng path/port/scheme |

Test security dùng token giả lập trong MockMvc có thể hữu ích cho rule authority, nhưng thường không kiểm tra chữ ký, issuer, audience và thời hạn JWT như request thật. Cần một phép thử tích hợp với decoder và token của issuer lab cho các ranh giới đó.

Không chạy shutdown/restart thật trên môi trường dùng chung chỉ để kiểm tra rule. Những endpoint cần thử side effect phải được kiểm tra ở lab riêng và có kế hoạch phục hồi.

## 12. Triển khai chính sách mà vẫn giữ được khả năng cập nhật

Một trình tự triển khai thực tế:

1. Chốt danh tính và quyền của Watcher, hệ thống metric, caller nghiệp vụ và người vận hành.
2. Chuẩn bị token/trust của transport; thử gọi trên một replica lab hoặc canary.
3. Thiết lập access/exposure và HTTP authorization, kiểm tra cả probe.
4. Cấu hình đúng cổng/path/scheme trong discovery và Watcher.
5. Áp dụng chính sách mạng theo danh sách nguồn hợp lệ.
6. Kích hoạt một thay đổi cấu hình không nhạy cảm, xác minh refresh và revision ở từng replica.
7. Thử thu hồi hoặc xoay credential của caller để chắc cơ chế cập nhật hoạt động.
8. Theo dõi lỗi gửi thông báo, lỗi authentication/authorization và kết quả áp dụng cấu hình.

Nếu Watcher bắt đầu nhận 401 sau khi bật security, điều cần sửa là cơ chế danh tính hoặc transport của Watcher. Nếu nhận 403 với token hợp lệ, kiểm tra scope/mapping và rule method. Nếu TLS thất bại, sửa trust/hostname trước; nếu không kết nối được, kiểm tra discovery, port và mạng.

Không nới quyền toàn bộ Actuator để giải quyết một lỗi tích hợp chưa được khoanh vùng. Cũng không coi việc đóng endpoint là nguyên nhân duy nhất khi nguồn không được nạp hoặc refresh hoàn tất nhưng consumer vẫn giữ giá trị cũ.

Đối với module Spring Cloud Kubernetes, lựa chọn tối thiểu thường rõ ràng: chỉ dùng HTTP refresh khi có nhu cầu cập nhật động và một transport được bảo vệ; chỉ dùng Bus khi đã có thiết kế phân phối và quyền broker phù hợp; giữ các thao tác vòng đời đóng khi chúng không phục vụ quy trình vận hành của ứng dụng.
