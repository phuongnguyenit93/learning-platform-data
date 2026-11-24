# Di chuyển cấu hình bảo mật, trusted proxies và Actuator

Nâng cấp Spring Cloud Gateway thường kéo theo thay đổi ở Spring Boot, Spring Security và cách ứng dụng nhận diện request đi qua reverse proxy. Nếu chỉ cập nhật dependency mà giữ nguyên cấu hình cũ, Gateway có thể khởi động nhưng áp dụng sai luật xác thực, tạo URL với scheme hoặc host không đúng, ghi nhận sai địa chỉ client, hoặc vô tình mở rộng quyền truy cập Actuator.

Bài học này trình bày cách di chuyển ba phần liên quan chặt chẽ với nhau: cấu hình bảo mật WebFlux, danh sách proxy được tin cậy và các endpoint quản trị Actuator. Các ví dụ tập trung vào Spring Cloud Gateway Server WebFlux. Cần đối chiếu phiên bản Spring Boot, Spring Cloud Gateway và Spring Security thực tế trước khi áp dụng vì tên thuộc tính đã thay đổi giữa các thế hệ.

## 1. Lập bản đồ phiên bản trước khi sửa cấu hình

Spring Cloud Gateway đi cùng một thế hệ Spring Boot và Spring Framework nhất định. Không nâng riêng Spring Security hoặc Spring Framework bằng cách ép version trong build file nếu Spring Cloud release train đã quản lý các phiên bản đó.

| Thế hệ | Nền tảng thường đi cùng | Prefix cấu hình Gateway WebFlux | Cấu hình forwarded header của Boot |
|---|---|---|---|
| Spring Cloud Gateway 4.x | Spring Boot 3.x, Spring Framework 6, Spring Security 6 | `spring.cloud.gateway.*` | `server.forward-headers-strategy` |
| Spring Cloud Gateway 5.x | Spring Boot 4.x, Spring Framework 7, Spring Security 7 | `spring.cloud.gateway.server.webflux.*` | `server.request.header.forwarded.strategy` |

Bảng này định hướng theo các dòng phát hành chính. Hãy kiểm tra compatibility matrix của Spring Cloud release train và tài liệu đúng minor version trước khi chọn JDK, Spring Boot và Gateway. Gateway Server WebFlux và Gateway Server Web MVC cũng có namespace riêng trong các dòng mới; không sao chép cấu hình của MVC vào ứng dụng WebFlux.

Trước khi nâng cấp, lưu lại các thông tin sau:

- Phiên bản JDK, Spring Boot, Spring Cloud release train, Spring Cloud Gateway và Spring Security hiện tại.
- Dependency trực tiếp và dependency được kéo theo, đặc biệt là starter security, OAuth2 resource server, Actuator và service discovery.
- Toàn bộ cấu hình `SecurityWebFilterChain`, bộ lọc Gateway, CORS, forwarded headers, management port và exposure của Actuator.
- Danh sách địa chỉ hoặc dải mạng của load balancer, ingress controller và reverse proxy thực sự kết nối trực tiếp đến Gateway.
- Kết quả kiểm tra hiện tại cho request công khai, request cần JWT, preflight CORS, route theo địa chỉ client và endpoint quản trị.

Giữ lại bộ request mẫu và kết quả trước nâng cấp để so sánh sau khi chuyển đổi. Một cấu hình chạy được chưa đủ chứng minh chính sách bảo mật vẫn giữ nguyên.

## 2. Chuyển cấu hình bảo mật WebFlux sang SecurityWebFilterChain

Gateway Server WebFlux sử dụng reactive security stack. Khi chuyển từ cấu hình cũ sang Spring Security 6 hoặc mới hơn, hãy khai báo luật truy cập bằng bean `SecurityWebFilterChain` nhận `ServerHttpSecurity`. Không dùng ví dụ của Spring MVC với `HttpSecurity`, `SecurityFilterChain` hoặc `authorizeHttpRequests` cho Gateway WebFlux.

Trong hệ thống cũ, module Servlet có thể còn lớp kế thừa `WebSecurityConfigurerAdapter`; lớp này thuộc Servlet stack và không phải cấu hình thay thế cho Gateway WebFlux. Với Gateway reactive, hãy đặt luật truy cập vào `SecurityWebFilterChain`, giúp phân chia rõ API công khai, API cần token và endpoint vận hành.

Ví dụ resource server xác thực JWT cho API:

```java
import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/public/**").permitAll()
                        .pathMatchers("/api/admin/**").hasAuthority("SCOPE_gateway.admin")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(withDefaults()))
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
```

Khai báo issuer để Spring Security tìm metadata và khóa xác minh JWT:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/platform
```

Trong ví dụ, scope `gateway.admin` được ánh xạ thành authority `SCOPE_gateway.admin`. Tên scope phải khớp với claim mà Identity Provider phát hành hoặc với bộ chuyển đổi authority do ứng dụng tự cấu hình. Khi xác thực JWT, kiểm tra issuer, chữ ký, thời hạn và audience theo hợp đồng token của hệ thống. Không coi việc token giải mã được là đủ để cho phép truy cập.

`csrf().disable()` chỉ phù hợp với API stateless dùng bearer token trong header và không dựa vào cookie phiên trình duyệt để xác thực. Nếu Gateway phục vụ giao diện web, dùng session cookie hoặc có endpoint nhận thao tác thay đổi trạng thái từ trình duyệt, hãy giữ CSRF protection và cấu hình token CSRF phù hợp. CORS cũng là chính sách riêng; cho phép origin không đồng nghĩa với xác thực người dùng.

### Tách luật bảo mật cho Actuator

Khi ứng dụng tự khai báo `SecurityWebFilterChain`, cấu hình bảo mật mặc định của Spring Boot có thể nhường quyền kiểm soát cho cấu hình của ứng dụng. Vì vậy, không nên chỉ thêm luật cho `/api/**` rồi giả định Actuator vẫn được bảo vệ như trước. Hãy tạo chain riêng cho management endpoint và đặt thứ tự ưu tiên cao hơn chain API.

Ví dụ dưới đây cho phép health check công khai và yêu cầu token có scope vận hành với các endpoint Actuator còn lại:

```java
import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
public class GatewaySecurityConfiguration {

    @Bean
    @Order(0)
    SecurityWebFilterChain actuatorSecurity(ServerHttpSecurity http) {
        return http
                .securityMatcher(ServerWebExchangeMatchers.pathMatchers("/actuator/**"))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/actuator/health", "/actuator/health/**").permitAll()
                        .anyExchange().hasAuthority("SCOPE_ops"))
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(withDefaults()))
                .build();
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/public/**").permitAll()
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(withDefaults()))
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
```

Các chain được xét theo thứ tự. Chain đầu chỉ khớp `/actuator/**`; chain API xử lý những request còn lại. Nếu thay `management.endpoints.web.base-path` từ `/actuator` sang `/manage`, phải cập nhật matcher tương ứng. Nếu management server dùng cổng riêng, vẫn cần bảo vệ cổng đó bằng network policy hoặc firewall; matcher trong ứng dụng không thay thế kiểm soát mạng.

Trong ví dụ, scope `ops` cần được cấp có chủ đích cho tài khoản hoặc workload vận hành. Không cấp scope này cho token người dùng thông thường. Nếu tổ chức dùng HTTP Basic hoặc một hệ thống danh tính riêng cho management plane, thay cơ chế xác thực trong chain Actuator theo chuẩn vận hành của tổ chức.

## 3. Di chuyển trusted proxies và forwarded headers

Khi request đi qua load balancer hoặc reverse proxy, Gateway nhìn thấy kết nối TCP từ proxy. Proxy có thể gửi thêm thông tin về request ban đầu bằng header chuẩn `Forwarded` hoặc các header phổ biến `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Port`, `X-Forwarded-Proto` và `X-Forwarded-Prefix`.

Các header này ảnh hưởng đến địa chỉ client, scheme HTTPS, host công khai, URL redirect, cookie bảo mật, log và route predicate dựa trên địa chỉ. Nếu tin header do client tùy ý gửi, kẻ tấn công có thể giả mạo IP, làm sai quyết định rate limit hoặc khiến ứng dụng tạo redirect tới host không đáng tin cậy.

Hãy phân biệt hai lớp cấu hình:

1. **Spring Boot forwarded-header strategy** điều khiển cách web server hoặc Spring Framework diễn giải thông tin forwarded để xây dựng request hiện tại, ví dụ scheme và host mà ứng dụng nhìn thấy.
2. **Spring Cloud Gateway trusted proxies** xác định proxy nào được tin cậy khi Gateway tạo hoặc nối thêm `Forwarded` và `X-Forwarded-*` headers gửi đến dịch vụ phía sau.

Hai cấu hình có liên quan nhưng không thay thế nhau. Cấu hình Boot không tự xác định danh sách proxy được Gateway tin cậy; thuộc tính Gateway cũng không tự cô lập cổng Gateway khỏi client bên ngoài.

### Cấu hình theo phiên bản

Với Spring Boot 3 và Spring Cloud Gateway 4.x, cấu hình WebFlux có thể dùng dạng:

```yaml
server:
  forward-headers-strategy: framework

spring:
  cloud:
    gateway:
      trusted-proxies: '^(?:10\.20\.0\.10|10\.20\.0\.11)$'
```

Với Spring Boot 4 và Spring Cloud Gateway 5.x Server WebFlux, namespace đã chuyển sang dạng:

```yaml
server:
  request:
    header:
      forwarded:
        strategy: web-server

spring:
  cloud:
    gateway:
      server:
        webflux:
          trusted-proxies: '^(?:10\.20\.0\.10|10\.20\.0\.11)$'
```

Trong hai ví dụ, `10.20.0.10` và `10.20.0.11` chỉ là địa chỉ minh họa của các proxy kết nối trực tiếp đến Gateway. Thay chúng bằng địa chỉ thực tế trong hạ tầng. Biểu thức là Java regular expression; kiểm tra giá trị địa chỉ mà ứng dụng nhận được trong môi trường triển khai để bảo đảm biểu thức khớp đúng.

Ở Boot 3, `framework` dùng hỗ trợ forwarded header của Spring Framework, trong đó reactive stack sử dụng `ForwardedHeaderTransformer`; `native` dùng khả năng của web server nếu có hỗ trợ. Ở Boot 4, thuộc tính được tổ chức lại thành `server.request.header.forwarded.strategy`; chọn `web-server` khi máy chủ hỗ trợ đầy đủ, hoặc `framework` khi cần cơ chế chung của Spring Framework. Không chuyển nguyên văn tên thuộc tính giữa Boot 3 và Boot 4.

Nếu ứng dụng Gateway dùng Web MVC trong Spring Cloud Gateway 5.x, namespace tương ứng là `spring.cloud.gateway.server.webmvc.*`. Không dùng `server.webflux.trusted-proxies` cho MVC.

### Xây dựng ranh giới tin cậy tại proxy biên

Một cấu hình trusted proxy an toàn cần đi cùng thiết kế mạng:

- Chỉ cho phép load balancer hoặc ingress đã biết kết nối đến cổng Gateway. Dùng security group, firewall, network policy hoặc private subnet để chặn đường truy cập trực tiếp từ Internet.
- Tại proxy biên, xóa các header `Forwarded` và `X-Forwarded-*` do client gửi vào, sau đó ghi lại giá trị dựa trên kết nối mà proxy thực sự nhận được.
- Chỉ tin cậy địa chỉ hoặc dải mạng của những hop nằm trong chuỗi proxy đã kiểm soát. Không đặt biểu thức `.*` hoặc cấu hình tin cậy mọi proxy trong production.
- Nếu có nhiều lớp proxy, ghi lại thứ tự các hop và thống nhất cách nối chuỗi header. Không giả định phần tử đầu tiên của `X-Forwarded-For` luôn là IP đáng tin cậy.
- Chỉ chuyển tiếp những trường downstream thực sự cần. Hạn chế `X-Forwarded-Host` nếu service phía sau không cần biết host công khai; kiểm tra host allowlist trước khi dùng nó tạo URL hoặc redirect.

Gateway có các filter tạo header `Forwarded` và `X-Forwarded-*`. Khi cần, có thể bật hoặc tắt từng trường và kiểm soát việc nối thêm giá trị. Ví dụ chỉ bật các trường cần dùng trong SCG 5.x:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          x-forwarded:
            enabled: true
            for-enabled: true
            host-enabled: true
            port-enabled: true
            proto-enabled: true
            prefix-enabled: false
```

Tên thuộc tính tương ứng ở SCG 4.x nằm dưới `spring.cloud.gateway.x-forwarded.*`. Chỉ bật `prefix` nếu kiến trúc proxy thực sự strip một path prefix và downstream cần khôi phục prefix gốc. Không để cả proxy biên lẫn Gateway tự nối cùng một giá trị mà không có quy ước rõ ràng.

### Địa chỉ client và RemoteAddr predicate

`RemoteAddr` predicate mặc định có thể nhìn thấy địa chỉ của peer kết nối trực tiếp đến Gateway, tức địa chỉ load balancer thay vì địa chỉ client cuối. Nếu route hoặc rate limiter cần địa chỉ client, phải xác định rõ nguồn địa chỉ đáng tin cậy và số hop proxy được phép đi qua.

Spring Cloud Gateway cung cấp `XForwardedRemoteAddressResolver` để đọc địa chỉ từ `X-Forwarded-For`. Với chuỗi proxy có cấu trúc cố định, chọn `maxTrustedIndex(n)` theo số proxy tin cậy đã xác định. Không dùng resolver tin mọi giá trị forwarded khi request có thể đi thẳng từ Internet đến Gateway. Nếu topology thay đổi, cập nhật index và kiểm thử lại vì chọn sai hop có thể làm sai ACL hoặc giới hạn lưu lượng.

Không dùng IP forwarded làm danh tính duy nhất cho người dùng. IP có thể dùng cho kiểm soát mạng hoặc rate limit bổ trợ; xác thực người dùng vẫn phải dựa trên token hoặc cơ chế danh tính phù hợp.

## 4. Di chuyển cấu hình Actuator an toàn

Actuator cung cấp health, metrics, thông tin cấu hình và endpoint quản trị Gateway. Sau nâng cấp, hãy kiểm tra đồng thời ba điều kiện: endpoint đã được bật, được expose qua HTTP hoặc JMX, và người gọi có quyền truy cập. Một endpoint không xuất hiện có thể do chưa được expose hoặc đã bị vô hiệu hóa; lỗi 401/403 thường liên quan đến security policy.

Chỉ expose những endpoint cần thiết. Ví dụ cho Spring Boot 3.4+ hoặc Boot 4, có thể đặt mặc định không cho endpoint truy cập rồi mở read-only cho các endpoint vận hành cần dùng:

```yaml
management:
  endpoints:
    access:
      default: none
    web:
      exposure:
        include: health,info,metrics,prometheus,gateway
  endpoint:
    health:
      access: read-only
    info:
      access: read-only
    metrics:
      access: read-only
    prometheus:
      access: read-only
    gateway:
      access: read-only
```

`access: read-only` giới hạn thao tác endpoint ở mức đọc. Điều này đặc biệt hữu ích với Gateway Actuator endpoint có thể cung cấp thao tác thay đổi route hoặc refresh tùy phiên bản. Hãy xác nhận endpoint `gateway` tồn tại và các thao tác được hỗ trợ trong đúng phiên bản Spring Cloud Gateway đang dùng.

Với Spring Boot 3.0 đến 3.3, dùng cấu hình enablement và exposure tương ứng của thế hệ đó, sau đó bảo vệ endpoint bằng security chain và network policy:

```yaml
management:
  endpoint:
    gateway:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus,gateway
```

Trong các phiên bản này, không giả định thuộc tính `management.endpoints.access.default` hoặc `management.endpoint.<id>.access` đã có sẵn. Kiểm tra tài liệu theo minor version thay vì đưa thuộc tính mới vào ứng dụng cũ rồi nghĩ rằng nó đã giới hạn quyền.

Có thể đặt management server ở cổng riêng và chỉ bind vào interface nội bộ:

```yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
```

Địa chỉ `127.0.0.1` phù hợp khi agent giám sát chạy cùng network namespace với Gateway. Trong Kubernetes hoặc môi trường có Prometheus scrape từ pod khác, cần bind vào interface mạng phù hợp rồi giới hạn bằng NetworkPolicy, firewall và xác thực. Một cổng riêng không tự động an toàn nếu nó vẫn được publish ra mạng công cộng.

Không expose `*` chỉ để tiện kiểm tra. Các endpoint như `env`, `configprops`, `beans`, `heapdump`, `loggers` hoặc `gateway` có thể tiết lộ thông tin nội bộ hoặc thay đổi hành vi ứng dụng. Nếu Prometheus cần scrape không dùng bearer token, hãy cho phép riêng endpoint metrics trên mạng scrape nội bộ; không mở toàn bộ Actuator cho mọi nguồn.

## 5. Kiểm tra tương thích sau khi chuyển đổi

Sau khi sửa cấu hình, khởi chạy Gateway trong môi trường staging có topology proxy giống production. Dùng một bộ kiểm thử có cả trường hợp hợp lệ lẫn trường hợp cố tình giả mạo.

| Trường hợp | Kết quả cần xác nhận |
|---|---|
| Request công khai đến route public | Được định tuyến đúng và không cần token |
| Request đến API riêng tư không có token | Bị từ chối với 401 |
| Token sai chữ ký, issuer, audience hoặc hết hạn | Bị từ chối; không được chuyển tiếp như request đã xác thực |
| Token thiếu scope quản trị | Không truy cập được route admin hoặc Actuator quản trị |
| Preflight `OPTIONS` từ origin được phép | Trả CORS header đúng; không làm lộ route cần xác thực |
| Request đi qua proxy tin cậy | Scheme, host và địa chỉ client phản ánh đúng topology đã khai báo |
| Client gửi `X-Forwarded-For` giả từ nguồn không tin cậy | Giá trị giả không được dùng để xác định IP hoặc tạo header downstream |
| Request đi thẳng vào địa chỉ Gateway từ Internet | Bị chặn ở lớp mạng hoặc không thể giả làm request qua proxy |
| `/actuator/health` | Chỉ mở theo chính sách health check đã chọn |
| `/actuator/gateway/routes` và `/actuator/metrics` | Chỉ tài khoản hoặc mạng vận hành được phép đọc |
| Thao tác ghi của Gateway Actuator | Bị chặn nếu môi trường chỉ cho phép read-only |

Ví dụ kiểm tra health endpoint và endpoint quản trị:

```bash
curl -i https://api.example.com/actuator/health

# Không có token vận hành: kỳ vọng 401 hoặc 403
curl -i https://api.example.com/actuator/gateway/routes

# Token cần có scope ops theo cấu hình security
curl -i \
  -H 'Authorization: Bearer <OPS_ACCESS_TOKEN>' \
  https://api.example.com/actuator/gateway/routes
```

Để kiểm tra forwarded headers, gửi request qua đúng load balancer và xem log hoặc endpoint thử nghiệm ở downstream. So sánh request qua proxy tin cậy với request giả mạo header từ một nguồn không tin cậy. Không chỉ kiểm tra header trên response; cần xác nhận giá trị mà Gateway thực sự dùng để đánh giá route predicate, ghi log và tạo header gửi upstream.

Khi TLS kết thúc tại load balancer, kiểm tra `X-Forwarded-Proto` hoặc `Forwarded: proto=https` được xử lý đúng. URL redirect và cookie phải giữ scheme HTTPS bên ngoài. Nếu ứng dụng tạo redirect sang HTTP, kiểm tra forwarded-header strategy và cấu hình proxy. Không giải quyết lỗi bằng cách tin mọi forwarded header.

## 6. Quy trình nâng cấp có kiểm soát

1. **Chốt ma trận phiên bản:** chọn Spring Boot và Spring Cloud release train tương thích; để BOM quản lý version của Gateway và Spring Security.
2. **Lưu baseline:** ghi lại luật security, endpoint Actuator được expose, cấu hình proxy, route predicate phụ thuộc địa chỉ và các request kiểm thử.
3. **Di chuyển API bảo mật:** thay cấu hình cũ bằng `SecurityWebFilterChain` reactive; xác định rõ route public, route cần JWT, scope và chính sách CSRF.
4. **Tách management policy:** thêm chain riêng cho Actuator, đặt thứ tự ưu tiên và giới hạn quyền đọc/ghi theo phiên bản Boot.
5. **Chuyển tên thuộc tính:** đổi Gateway prefix khi lên SCG 5.x; đổi forwarded-header property khi lên Boot 4. Không đổi tên theo trí nhớ, hãy kiểm tra configuration metadata của dependency mục tiêu.
6. **Thiết lập proxy trust:** cập nhật danh sách proxy trực tiếp, cấu hình proxy biên xóa header do client gửi và giới hạn đường truy cập mạng đến Gateway.
7. **Kiểm thử staging:** chạy ma trận ở phần trước, so sánh log, route, redirect, IP, status và quyền Actuator với baseline.
8. **Triển khai theo đợt:** theo dõi 401/403, 404, redirect, tỷ lệ lỗi, latency và access log; giữ bản cấu hình có thể rollback nếu chính sách mới gây ảnh hưởng.

Nếu nâng từ Boot 3/SCG 4 lên Boot 4/SCG 5, hãy xử lý việc chuyển namespace như một thay đổi cấu hình có kiểm soát. Một số thuộc tính cũ có thể bị bỏ qua mà ứng dụng vẫn khởi động bình thường; do đó cần kiểm tra giá trị runtime hoặc hành vi thực tế, không chỉ dựa vào việc không có lỗi startup.

## 7. Lỗi thường gặp khi di chuyển

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Mọi API bất ngờ yêu cầu đăng nhập | Chain tùy chỉnh đã thay thế cấu hình mặc định; luật `permitAll` chưa khai báo | Kiểm tra thứ tự chain và các matcher; thử route public |
| API trả 403 dù JWT hợp lệ | Scope/authority không khớp, audience sai hoặc luật CSRF áp dụng cho request | Đọc claim token đã được che dữ liệu, kiểm tra authority converter và phương thức HTTP |
| Actuator trước đây truy cập được nay trả 401/403 | Chain mới đã bắt cả management path | Kiểm tra matcher `/actuator/**`, role/scope và thứ tự `@Order` |
| Actuator trả 404 sau nâng cấp | Endpoint chưa được expose, không được enable hoặc management base path đã đổi | Kiểm tra `management.endpoints.web.exposure`, endpoint access và base path |
| Gateway bỏ qua trusted proxy sau nâng cấp | Dùng prefix cũ trên SCG 5.x hoặc regex không khớp peer address | Kiểm tra namespace `server.webflux` và địa chỉ socket thực tế |
| Client IP trở thành IP load balancer | Forwarded headers không được xử lý hoặc resolver chọn sai hop | Kiểm tra Boot strategy, Gateway trusted proxies và số hop của resolver |
| Redirect tạo URL HTTP hoặc host lạ | Scheme/host forwarded sai hoặc proxy biên không ghi đè header client | Kiểm tra `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host` và allowlist host |
| Route theo `RemoteAddr` thay đổi kết quả | Predicate đang dùng địa chỉ peer khác sau khi thay đổi proxy topology | Xác định nguồn IP được phép tin cậy và kiểm thử từng đường vào |

## 8. Bài tập thực hành

1. Lấy một cấu hình Gateway WebFlux dùng Spring Cloud Gateway 4.x. Ghi lại prefix `spring.cloud.gateway.*`, cấu hình `server.forward-headers-strategy` và các bean security hiện có.
2. Chuyển API sang một `SecurityWebFilterChain` dùng JWT. Tạo route public và route yêu cầu scope; xác nhận token thiếu hoặc sai scope bị từ chối.
3. Thêm chain Actuator với `@Order(0)`. Cho phép health check theo chính sách của môi trường và yêu cầu scope vận hành cho endpoint còn lại.
4. Tạo hai profile cấu hình minh họa cho SCG 4.x/Boot 3 và SCG 5.x/Boot 4. Đối chiếu namespace trusted proxy và forwarded-header strategy giữa hai profile.
5. Trong staging, gửi request qua proxy tin cậy và request giả mạo `X-Forwarded-For` từ nguồn không tin cậy. Xác nhận IP client mà Gateway ghi nhận không thể bị client tự chọn.
6. Chỉ expose endpoint Actuator cần thiết. Kiểm tra người không có quyền không đọc được route list hoặc metrics, và thao tác ghi bị chặn khi endpoint được cấu hình read-only.
7. So sánh redirect HTTPS, CORS preflight, route predicate theo địa chỉ và log request trước/sau nâng cấp. Ghi lại mọi khác biệt cần xử lý trước khi triển khai production.

## Tài liệu tham khảo

- [Spring Cloud Gateway 4.3 – Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/4.3/configprops.html)
- [Spring Cloud Gateway 5.0 – Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/5.0/configprops.html)
- [Spring Cloud Gateway – HTTP Headers Filters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/httpheadersfilters.html)
- [Spring Cloud Gateway – RemoteAddr Route Predicate and XForwardedRemoteAddressResolver](https://docs.spring.io/spring-cloud-gateway/docs/current/reference/html/index.html#the-remoteaddr-route-predicate-factory)
- [Spring Boot 3.5 – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Boot 4.0 – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/4.0/how-to/webserver.html)
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Security – WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security – Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
