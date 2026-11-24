# Giới hạn mạng và quyền truy cập Dashboard, API cùng Actuator

Service registry và Spring Boot Actuator cung cấp thông tin quan trọng về topology, địa chỉ instance, trạng thái health và cấu hình vận hành. Nếu Dashboard, API quản trị hoặc Actuator được mở cho mọi mạng và mọi người dùng, kẻ tấn công có thể thu thập sơ đồ nội bộ, đăng ký instance giả, thay đổi trạng thái service hoặc đọc thông tin nhạy cảm.

Trong hệ thống Spring Cloud Service Discovery, cần bảo vệ riêng các bề mặt truy cập: **Dashboard** dành cho người vận hành; **registry API** dành cho provider/consumer và công cụ quản trị; **Actuator** dành cho health checker, monitoring và vận hành ứng dụng. Các bề mặt này có thể dùng chung một tiến trình hoặc port, nhưng không nên mặc định có cùng quyền truy cập.

## 1. Những bề mặt cần bảo vệ

| Bề mặt | Ví dụ | Dữ liệu/hành động có thể truy cập | Nhóm truy cập phù hợp |
|---|---|---|---|
| Eureka Dashboard | Trang web tại `/` trên Eureka Server | Danh sách application, instance, host, port, status và metadata. | SRE/platform operator qua mạng quản trị. |
| Eureka REST API | `/eureka/**` | Đọc registry, đăng ký, gia hạn, hủy đăng ký và cập nhật trạng thái instance. | Eureka client có xác thực; admin có quyền cao hơn. |
| Consul UI | Giao diện web của Consul | Catalog, health, node, service và thông tin vận hành. | Operator được cấp ACL token phù hợp. |
| Consul HTTP API | `/v1/agent/**`, `/v1/catalog/**`, `/v1/health/**` và API khác | Đăng ký service, đọc catalog, truy vấn health và một số thao tác quản trị. | Provider/consumer theo ACL tối thiểu; admin theo quyền riêng. |
| ZooKeeper admin/management | AdminServer, công cụ quản trị và znode client interface | Cây znode, session, ACL và trạng thái ensemble. | Quản trị viên ZooKeeper trên mạng quản trị. |
| Spring Boot Actuator | `/actuator/health`, `/actuator/info`, `/actuator/prometheus`... | Health, metrics, thông tin ứng dụng và các endpoint vận hành. | Health checker, monitoring hoặc operator theo từng endpoint. |
| Kubernetes API | API server và resource Service/Endpoints/EndpointSlices | Đọc hoặc thay đổi resource tùy RBAC. | ServiceAccount/workload có quyền tối thiểu; operator qua danh tính quản trị. |

Dashboard và API thường cung cấp nhiều thông tin hơn giao diện người dùng thông thường. Một endpoint đọc registry có thể tiết lộ hostname, IP, port, phiên bản và quan hệ giữa các service. Endpoint ghi có thể tạo hoặc thay đổi registration. Actuator có thể tiết lộ cấu hình, biến môi trường, thread dump hoặc khả năng thay đổi log level. Vì vậy, cần phân quyền theo mục đích thay vì cấp một quyền quản trị chung cho mọi thành phần.

## 2. Nguyên tắc bảo vệ theo lớp

Một cấu hình an toàn thường kết hợp nhiều lớp:

1. **Phân vùng mạng:** chỉ cho phép subnet, namespace hoặc workload cần thiết truy cập Dashboard, API và management port.
2. **Xác thực:** xác định danh tính của người dùng, provider, consumer, agent hoặc monitoring scraper.
3. **Ủy quyền:** giới hạn hành động đọc, đăng ký, thay đổi trạng thái, truy vấn metrics và quản trị.
4. **Mã hóa:** dùng TLS/mTLS cho kết nối qua mạng; xác minh certificate của cả hai phía khi cần.
5. **Giới hạn endpoint:** chỉ expose endpoint cần thiết; không công khai tất cả Actuator endpoint.
6. **Giám sát và audit:** ghi nhận truy cập, thao tác đăng ký, thay đổi ACL và request bị từ chối.

Firewall hoặc NetworkPolicy giúp giới hạn nơi có thể kết nối, nhưng không xác định người dùng bên trong mạng đó có quyền gì. Ngược lại, Basic Auth hoặc ACL không thay thế phân vùng mạng. Cần cả hai khi bề mặt truy cập có ảnh hưởng đến topology và hoạt động của hệ thống.

## 3. Phân tách mạng cho operator, registry client và monitoring

Hãy xác định nhóm nguồn được phép truy cập từng bề mặt:

| Nguồn | Dashboard | Registry API | Actuator health | Actuator metrics/management |
|---|---|---|---|---|
| Provider instance | Không cần | Chỉ endpoint register/renew/deregister cần thiết | Thường không cần gọi lẫn nhau | Không cần mặc định |
| Consumer instance | Không cần | Chỉ quyền đọc/fetch registry nếu dùng registry client | Không cần mặc định | Không cần mặc định |
| SRE/platform operator | Có, qua mạng quản trị | Có, theo vai trò quản trị | Có | Có theo quyền được cấp |
| Health checker | Không | Chỉ khi cơ chế check cần registry API | Có, từ đúng agent/node | Không cần mặc định |
| Monitoring scraper | Không | Không cần mặc định | Có thể đọc health nếu được yêu cầu | Chỉ metrics endpoint |
| Public Internet | Không | Không | Không | Không |

Ví dụ, có thể đặt Dashboard và API quản trị trên private subnet hoặc chỉ sau VPN/bastion. Provider được phép kết nối đến registry API qua security group/workload identity; consumer chỉ có quyền đọc. Monitoring scraper được phép truy cập `/actuator/prometheus` từ namespace monitoring. Người dùng cuối không cần truy cập các endpoint quản trị này.

### 3.1. Registry port và management port

Không nhầm port ứng dụng với port quản trị. Ví dụ một provider có thể dùng:

```yaml
server:
  port: 8080

management:
  server:
    port: 9001
```

Port `8080` nhận request nghiệp vụ; port `9001` phục vụ Actuator. Firewall có thể cho phép consumer gọi `8080`, còn `9001` chỉ cho phép monitoring và operator. Nếu dùng cùng port, vẫn cần bảo vệ path và quyền truy cập ở tầng HTTP.

Nếu cấu hình `management.server.address`, địa chỉ đó phải là interface có thật trong môi trường chạy. Không bind management port vào interface public nếu chỉ cần truy cập từ mạng quản trị. Khi chạy container, cần xem cả địa chỉ bind bên trong container và port mapping/Service bên ngoài.

## 4. Bảo vệ Eureka Dashboard và REST API

Eureka Server cung cấp Dashboard và REST API trên endpoint của server. Dashboard giúp quan sát registry; API phục vụ Eureka Client đăng ký, renew, fetch registry và deregister. Một cấu hình production cần xác thực người truy cập và giới hạn đường mạng đến server.

### 4.1. Bật Spring Security cho Eureka Server

Có thể thêm `spring-boot-starter-security` vào Eureka Server và cấu hình quyền theo URL. Ví dụ dưới đây minh họa phân biệt người vận hành và registry client:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class RegistrySecurityConfiguration {

    @Bean
    SecurityFilterChain registrySecurity(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.ignoringRequestMatchers("/eureka/**"))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/eureka/**")
                    .hasAnyRole("REGISTRY_READER", "REGISTRY_CLIENT", "OPS")
                .requestMatchers("/eureka/**")
                    .hasAnyRole("REGISTRY_CLIENT", "OPS")
                .anyRequest().hasRole("OPS")
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Trong ví dụ:

- Người có role `OPS` có thể mở Dashboard và thực hiện thao tác quản trị.
- `REGISTRY_READER` chỉ được GET registry API.
- `REGISTRY_CLIENT` được GET và thực hiện các thao tác API mà Eureka Client cần.
- CSRF chỉ được bỏ qua cho `/eureka/**`, vì Eureka Client dùng các HTTP method như POST, PUT và DELETE. Không tắt CSRF toàn bộ ứng dụng chỉ để làm cho client đăng ký được.

Đây là ví dụ Spring Security cho servlet application. Cần cấu hình `UserDetailsService`, LDAP hoặc identity provider để ánh xạ tài khoản thành các role trên; không dùng user mặc định hoặc tài khoản dùng chung không kiểm soát. Nếu có context path hoặc Eureka path tùy chỉnh, matcher phải khớp đường dẫn thực tế. Kiểm tra lại luồng Dashboard, register, renew, fetch và deregister sau khi bật security.

### 4.2. Xác thực Eureka Client

Eureka Client có thể dùng HTTP Basic credentials trong URL của `defaultZone`. Giá trị phải được cấp qua secret hoặc biến môi trường, không commit username/password vào repository:

```yaml
eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_SERVER_URL}
```

Giá trị runtime của `EUREKA_SERVER_URL` có thể chứa user-info theo định dạng Eureka Client hỗ trợ, ví dụ `https://user:password@eureka.internal.example:8761/eureka/`. Trong production, dùng secret manager/Kubernetes Secret và hạn chế quyền đọc secret. Tránh ghi URL đã chứa credentials vào log, exception hoặc metric label.

Nếu dùng HTTPS, cấu hình truststore để client xác minh certificate của Eureka Server. Khi yêu cầu mTLS, cấu hình client certificate và private key phù hợp. Không dùng HTTP Basic qua mạng không mã hóa trên subnet không tin cậy.

### 4.3. Giới hạn mạng Dashboard

Dashboard thường không cần được truy cập từ mọi microservice. Chỉ cho phép mạng quản trị, VPN hoặc bastion truy cập giao diện. Có thể dùng reverse proxy nội bộ để áp dụng SSO, MFA, audit log và rate limiting; proxy không thay thế việc bảo vệ REST API phía sau.

## 5. Bảo vệ Consul UI và HTTP API

Consul cung cấp UI và HTTP API. Cả hai sử dụng cơ chế ACL của Consul khi ACL được bật. Token có thể cho phép đọc catalog, truy vấn health, đăng ký service hoặc thao tác agent; quyền cần được giới hạn theo vai trò.

### 5.1. Bật ACL và dùng token theo workload

Trong môi trường production, bật ACL với chính sách mặc định từ chối và cấp token riêng cho từng vai trò. Ví dụ policy HCL cho consumer chỉ đọc service:

```hcl
service_prefix "" {
  policy = "read"
}

node_prefix "" {
  policy = "read"
}
```

Provider chỉ đăng ký service `payment-service` có thể được cấp policy giới hạn:

```hcl
service "payment-service" {
  policy = "write"
}
```

Các thao tác agent API hoặc catalog có thể cần thêm quyền tương ứng tùy cách ứng dụng kết nối đến Consul agent/server và phiên bản Consul. Hãy xác minh quyền tối thiểu bằng API thực tế, không cấp `global-management` token cho mọi service.

Token nên được cấp riêng cho provider, consumer, monitoring và operator. Nếu token bị lộ, có thể thu hồi đúng token đó mà không phải thay credential của toàn bộ cluster.

### 5.2. Gửi token an toàn

Consul HTTP API thường nhận token qua header `X-Consul-Token` hoặc cơ chế token được cấu hình cho client:

```bash
curl \
  -H "X-Consul-Token: ${CONSUL_READ_TOKEN}" \
  https://consul.internal.example:8501/v1/catalog/services
```

Không truyền token trong query string hoặc ghi token thật vào shell history, source code hay log. Với Spring Cloud Consul, dùng thuộc tính token được phiên bản integration hỗ trợ và inject từ secret store; kiểm tra cấu hình release train đang sử dụng.

### 5.3. Giới hạn Consul UI và API

- Bind HTTP API vào loopback hoặc private interface phù hợp, không mở public listener không cần thiết.
- Dùng HTTPS/TLS cho API đi qua mạng.
- Bật ACL và giới hạn token theo service, node hoặc thao tác.
- Chỉ cho phép subnet operator truy cập UI.
- Tách port API client khỏi RPC/gossip port nội bộ của Consul cluster.
- Audit token creation, policy change, service registration và thao tác quản trị.

UI không phải một ranh giới bảo mật riêng: người dùng UI có thể thực hiện các API request mà token của họ cho phép. Vì vậy, cần giới hạn token UI và mạng truy cập cùng lúc.

## 6. Bảo vệ ZooKeeper và công cụ quản trị

ZooKeeper lưu registration dưới dạng znode. Bảo mật cần kiểm soát quyền đọc, tạo, cập nhật và xóa trên root path và các node con. Công cụ quản trị hoặc AdminServer cũng cần được giới hạn trong mạng quản trị.

Các nguyên tắc chính:

- Không dùng ACL `world:anyone` với quyền ghi (`cdrwa`) cho namespace service discovery trong production.
- Dùng SASL, digest hoặc cơ chế xác thực được cluster hỗ trợ để xác định client.
- Cấp quyền đọc cho consumer và quyền tạo/cập nhật/xóa ephemeral node cho provider trong namespace cần thiết.
- Dùng TLS cho client connection nếu chính sách hạ tầng yêu cầu mã hóa đường truyền.
- Giới hạn client port và AdminServer bằng firewall/private interface.
- Chỉ mở các port quorum như peer synchronization và leader election giữa các ZooKeeper server; không mở cho toàn bộ microservice.
- Không công khai công cụ quản trị hoặc bốn-letter commands ra mạng người dùng.

Khi đổi ACL trên root znode, kiểm tra quyền kế thừa/thao tác trên node con và quy trình tạo ephemeral node của Spring Cloud Zookeeper/Curator. Một policy chỉ cho đọc root nhưng không cho provider tạo node con sẽ làm registration thất bại.

## 7. Giới hạn Spring Boot Actuator

Actuator cung cấp endpoint phục vụ health, metrics và vận hành. Spring Boot chỉ expose một số endpoint mặc định qua HTTP; các endpoint khác cần được bật và expose rõ ràng. Việc expose endpoint và việc bảo vệ endpoint là hai việc riêng: endpoint đã expose vẫn cần authentication/authorization và giới hạn mạng.

### 7.1. Chỉ expose endpoint cần thiết

Ví dụ một provider chỉ expose health, info và Prometheus metrics:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      show-details: when-authorized
      roles: OPS
      probes:
        enabled: true
```

Để dùng `/actuator/prometheus`, ứng dụng cần Micrometer Prometheus registry dependency tương ứng. Chỉ thêm endpoint vào `include` khi có nhu cầu thực tế. Tránh `include: "*"` trên ứng dụng có thể truy cập từ mạng không tin cậy.

Một số endpoint nhạy cảm cần cân nhắc kỹ trước khi expose:

| Endpoint | Rủi ro | Khuyến nghị |
|---|---|---|
| `/actuator/env` | Có thể tiết lộ property và thông tin môi trường. | Không expose công khai; giới hạn cho operator và che dữ liệu nhạy cảm. |
| `/actuator/configprops` | Tiết lộ cấu hình binding của ứng dụng. | Chỉ dùng trong điều tra có kiểm soát. |
| `/actuator/heapdump` | Có thể chứa dữ liệu nhạy cảm trong memory. | Không expose ra mạng thông thường; chỉ thu thập theo quy trình sự cố. |
| `/actuator/threaddump` | Tiết lộ stack, tên thread và chi tiết vận hành. | Giới hạn quyền operator. |
| `/actuator/loggers` | Có thể thay đổi log level khi dùng thao tác ghi. | Chỉ cấp cho operator được ủy quyền. |
| `/actuator/mappings` | Tiết lộ route và cấu trúc API. | Không expose rộng rãi. |
| `/actuator/conditions` | Tiết lộ điều kiện auto-configuration và classpath behavior. | Chỉ phục vụ chẩn đoán nội bộ. |
| `/actuator/shutdown` | Có thể dừng ứng dụng nếu được bật và expose. | Mặc định không bật; không expose trừ khi có quy trình đặc biệt và bảo vệ nghiêm ngặt. |

`health` cũng có thể tiết lộ tên dependency hoặc chi tiết nội bộ nếu cấu hình show-details quá rộng. Dùng `when-authorized` hoặc `never` tùy yêu cầu; health checker thường chỉ cần trạng thái tổng quát.

### 7.2. Tách management port

Có thể tách Actuator sang port riêng và bind vào interface quản trị:

```yaml
server:
  port: 8080

management:
  server:
    port: 9001
    address: 10.20.5.21
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      show-details: when-authorized
      roles: OPS
      probes:
        enabled: true
```

Trong ví dụ, request nghiệp vụ dùng port `8080`, còn Actuator dùng port `9001` trên địa chỉ quản trị `10.20.5.21`. Địa chỉ bind phải tồn tại trong network namespace của ứng dụng. Với container, hãy kiểm tra interface và mapping; không bind vào IP của host nếu IP đó không tồn tại bên trong container.

Nếu kubelet cần gọi readiness/liveness endpoint trên management port riêng, cấu hình probe port tương ứng và xác minh node-to-Pod route. Nếu muốn probe đi qua application port, có thể giữ health group trên server port theo cấu hình Spring Boot phù hợp. Không tách port mà quên cập nhật health checker hoặc monitoring scraper.

## 8. Bảo vệ Actuator bằng Spring Security

Ví dụ dưới đây minh họa servlet application: health tổng quát được đọc không cần đăng nhập, Prometheus chỉ cho monitoring role, các endpoint Actuator khác yêu cầu operator role. Các request còn lại yêu cầu xác thực theo policy ứng dụng.

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ActuatorSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .requestMatchers(EndpointRequest.to("prometheus"))
                    .hasRole("METRICS")
                .requestMatchers(EndpointRequest.toAnyEndpoint())
                    .hasRole("OPS")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

`EndpointRequest` giúp matcher theo Actuator endpoint thay vì hard-code mọi URL. Health chi tiết vẫn được kiểm soát bằng `show-details` và `roles`. Prometheus scraper cần credential có role `METRICS`; operator có role `OPS` có thể truy cập các endpoint còn lại đã được expose.

Đây là ví dụ cho Spring MVC/Servlet. Với WebFlux, dùng `SecurityWebFilterChain` và matcher tương ứng. Cần khai báo user store/identity provider, role mapping, session policy và CSRF theo cách ứng dụng xác thực. Không sao chép ví dụ rồi bỏ xác thực cho mọi request. Nếu ứng dụng có nhiều `SecurityFilterChain`, kiểm tra thứ tự và `securityMatcher` để chắc chắn request Actuator thực sự đi qua chain mong muốn.

## 9. Bảo vệ Kubernetes API và Dashboard quản trị

Nếu Spring Cloud Kubernetes DiscoveryClient dùng Kubernetes API, ServiceAccount chỉ nên có quyền đọc resource cần thiết. Consumer discovery thông thường không cần quyền tạo hoặc xóa Service/Pod.

Ví dụ Role chỉ cho phép đọc Service và EndpointSlice trong namespace `commerce`:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: service-discovery-reader
  namespace: commerce
rules:
  - apiGroups: [""]
    resources: ["services", "endpoints"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
```

Sau đó gắn Role với ServiceAccount của ứng dụng bằng RoleBinding. Resource và verb chính xác phụ thuộc phiên bản Spring Cloud Kubernetes và loại resource implementation đang truy vấn. Nếu client không đọc EndpointSlice, không cấp quyền chỉ vì ví dụ có resource đó; kiểm tra log `Forbidden` và tài liệu phiên bản để xác định quyền tối thiểu.

Kubernetes Dashboard hoặc công cụ quản trị cluster không nên được expose công khai với quyền cluster-admin. Dùng identity provider, MFA, RBAC theo namespace và audit log. Không cấp kubeconfig admin cho ứng dụng microservice chỉ để nó đọc service discovery.

## 10. Ví dụ NetworkPolicy giới hạn Actuator và registry management

NetworkPolicy có thể giới hạn port Actuator chỉ cho namespace monitoring và operator. Ví dụ sau áp dụng cho Pod có label `app: payment` trong namespace `commerce`:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payment-management-ingress
  namespace: commerce
spec:
  podSelector:
    matchLabels:
      app: payment
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring
      ports:
        - protocol: TCP
          port: 9001
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: platform-ops
      ports:
        - protocol: TCP
          port: 9001
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: orders
      ports:
        - protocol: TCP
          port: 8080
```

Policy cho phép monitoring và operator truy cập management port `9001`; consumer từ namespace `orders` chỉ truy cập application port `8080`. Đây là ví dụ minh họa, cần thay namespace, label và port theo cluster. Nếu Prometheus chạy ngoài cluster, dùng CIDR hoặc cơ chế policy phù hợp. Nếu health probe do kubelet/node thực hiện, kiểm tra behavior của CNI với traffic node-to-Pod trước khi áp dụng default-deny.

NetworkPolicy không xác thực người dùng và không phân quyền endpoint HTTP. Một Pod được phép đến port `9001` vẫn cần Spring Security bảo vệ `/actuator/**`. Tương tự, security group/firewall nên giới hạn subnet nguồn nhưng API vẫn cần authentication/authorization.

## 11. Ma trận quyền truy cập tham khảo

| Vai trò | Registry Dashboard | Registry read API | Registry write API | Actuator health | Metrics | Actuator quản trị |
|---|---|---|---|---|---|---|
| `OPS` | Cho phép | Cho phép | Cho phép theo quy trình | Cho phép | Cho phép | Cho phép endpoint đã phê duyệt |
| `REGISTRY_READER` | Không mặc định | Cho phép | Từ chối | Không mặc định | Không mặc định | Từ chối |
| `REGISTRY_CLIENT` | Từ chối | Cho phép | Chỉ API cần cho register/renew/deregister | Không mặc định | Không mặc định | Từ chối |
| `METRICS` | Từ chối | Từ chối | Từ chối | Có thể đọc trạng thái tổng quát | Cho phép | Từ chối |
| `HEALTH_CHECKER` | Từ chối | Từ chối | Từ chối | Cho phép endpoint health tối thiểu | Từ chối | Từ chối |
| `APP_USER` | Từ chối | Từ chối | Từ chối | Theo nhu cầu rất hạn chế | Từ chối | Từ chối |

Đây là ma trận tham khảo, không phải role có sẵn trong Spring Cloud hoặc Consul. Cần ánh xạ role vào Spring Security, ACL policy, identity provider và NetworkPolicy của môi trường. Một số registry API dùng cùng endpoint cho đọc và ghi; khi đó cần phân quyền theo HTTP method hoặc policy của registry.

## 12. Audit, logging và xử lý sự cố

Các sự kiện cần theo dõi:

- Đăng nhập thất bại hoặc request bị `401`/`403`.
- Thay đổi Consul ACL token, policy, role và service registration.
- Eureka instance đăng ký, renew, deregister hoặc đổi status.
- Thao tác ZooKeeper ACL và thay đổi znode trong root discovery.
- Request đến Actuator endpoint nhạy cảm, đặc biệt `env`, `heapdump`, `loggers` và `shutdown` nếu được bật.
- Kubernetes API request bị RBAC từ chối hoặc truy cập ngoài namespace dự kiến.
- Flow log cho kết nối đến registry port, management port và service port.

Không ghi access token, password, session cookie hoặc nội dung nhạy cảm từ `/env` vào log. Log cần có danh tính, endpoint, thời điểm, kết quả và correlation/request ID đủ để điều tra nhưng không làm lộ credential.

### 12.1. Chẩn đoán theo mã lỗi

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Dashboard trả `401` | Chưa xác thực hoặc credentials sai. | Kiểm tra identity provider và tài khoản operator. |
| Dashboard trả `403` | Đã xác thực nhưng role không đủ. | Cấp role tối thiểu phù hợp, không nâng mọi người lên admin. |
| Eureka Client không đăng ký được sau khi bật Security | Basic Auth sai, CSRF chặn POST/PUT/DELETE hoặc matcher không đúng. | Kiểm tra URL credentials, chỉ ignore CSRF cho Eureka API path và xác minh role client. |
| Consul API trả `403` | ACL token thiếu quyền service/node/agent phù hợp. | Xem audit/log ACL và cấp policy tối thiểu cho API thực tế. |
| ZooKeeper báo `NoAuth` | ACL/SASL identity không có quyền trên znode. | Kiểm tra ACL root và node con, scheme xác thực và quyền create/write/delete. |
| Actuator trả `404` | Endpoint không enabled/exposed hoặc base path/port khác. | Kiểm tra `management.endpoints.web.exposure` và management port. |
| Actuator trả `401`/`403` | Security chain hoặc role không cho phép. | Kiểm tra matcher, role mapping và credentials của scraper/operator. |
| Prometheus scrape thất bại | Endpoint chưa expose, thiếu registry dependency, port/network bị chặn hoặc thiếu role. | Kiểm tra `/actuator/prometheus`, dependency, NetworkPolicy và auth. |
| Health checker timeout | Probe không đến được management port hoặc endpoint phản hồi quá chậm. | Kiểm tra source subnet, route, probe path/port và timeout. |
| Public user truy cập được Dashboard/API | Listener public, reverse proxy hoặc firewall rule quá rộng. | Giới hạn bind/network, yêu cầu auth và kiểm tra ingress path. |

## 13. Checklist trước khi đưa vào production

- Dashboard chỉ truy cập được từ mạng quản trị/VPN/bastion.
- Registry API yêu cầu authentication và phân quyền theo vai trò hoặc ACL.
- Provider có credential riêng cho register/renew; consumer có quyền đọc phù hợp.
- Consul ACL bật, token mặc định không có quyền rộng và token theo workload có thể thu hồi riêng.
- ZooKeeper root znode và node con dùng ACL; không có quyền ghi `world:anyone`.
- Kubernetes ServiceAccount chỉ có RBAC đọc resource discovery cần thiết.
- Actuator chỉ expose endpoint thực sự cần thiết; không dùng `include: "*"` tùy tiện.
- Health details không tiết lộ dependency hoặc thông tin nội bộ cho người chưa được phép.
- Prometheus endpoint chỉ cho monitoring scraper truy cập và có xác thực nếu môi trường yêu cầu.
- Actuator management port được tách và bind vào mạng/interface phù hợp nếu cần.
- Spring Security bảo vệ endpoint bằng role; matcher và thứ tự filter chain đã được kiểm thử.
- Eureka CSRF exception chỉ giới hạn ở API path cần thiết cho client.
- TLS/mTLS được xác minh đúng certificate SAN, CA và client identity.
- Firewall, security group và NetworkPolicy chỉ mở đúng nguồn/đích/port.
- Có audit log cho truy cập Dashboard, API, Actuator và thao tác thay đổi registry.
- Đã thử cả trường hợp người dùng đúng role, sai role, không có credentials và nguồn mạng không được phép.

## Kết luận

Dashboard, registry API và Actuator là các bề mặt quản trị quan trọng của service discovery. Cần tách mạng quản trị khỏi traffic nghiệp vụ, cấp quyền riêng cho operator, registry client, health checker và monitoring, đồng thời chỉ expose những endpoint thật sự cần thiết. Eureka có thể được bảo vệ bằng Spring Security; Consul dùng ACL token và policy; ZooKeeper dùng authentication cùng ACL trên znode; Kubernetes discovery cần ServiceAccount/RBAC tối thiểu; Actuator cần exposure allowlist, management port phù hợp và authorization theo endpoint.

Không có một lớp bảo vệ đơn lẻ nào đủ an toàn. Phân vùng mạng, xác thực, ủy quyền, TLS, giới hạn endpoint và audit cần phối hợp để tránh lộ topology hoặc cho phép thay đổi registry từ workload không được phép. Sau khi cấu hình, hãy kiểm thử từng vai trò và từng luồng mạng để xác nhận quyền đúng với nhu cầu vận hành.
