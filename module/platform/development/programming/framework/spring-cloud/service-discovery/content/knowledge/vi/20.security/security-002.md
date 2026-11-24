# Ngăn đăng ký giả và công bố địa chỉ dịch vụ độc hại

Service registry là nguồn dữ liệu điều khiển việc định tuyến giữa các microservice. Nếu một tác nhân không được phép có thể đăng ký service giả, sửa địa chỉ instance hoặc công bố metadata độc hại, consumer có thể gửi request tới máy của kẻ tấn công, nhầm lẫn với service hợp lệ hoặc lộ dữ liệu nội bộ. Đây là dạng registry poisoning: dữ liệu discovery bị đầu độc để chuyển hướng traffic.

Trong Spring Cloud, `DiscoveryClient` và `ServiceRegistry` cung cấp abstraction cho việc tra cứu và đăng ký; chúng không tự xác thực danh tính workload. Eureka cần được bảo vệ ở HTTP API và mạng; Consul cần ACL token cùng quyền tối thiểu. Ở cả hai trường hợp, consumer vẫn phải kiểm tra endpoint mà registry trả về và chỉ kết nối tới địa chỉ thuộc phạm vi tin cậy.

## 1. Mô hình đe dọa

Một registration thường chứa service name, instance ID, hostname/IP, port, scheme, health-check URL, tags và metadata. Consumer lấy các trường này từ registry để chọn endpoint. Nếu người đăng ký không được xác thực hoặc được cấp quyền quá rộng, họ có thể khai báo dữ liệu sai nhưng vẫn có hình thức hợp lệ.

| Mối đe dọa | Ví dụ | Hậu quả |
|---|---|---|
| Đăng ký giả (rogue registration) | Tác nhân đăng ký một instance mới dưới tên `payment-service` | Consumer có thể chọn instance giả và gửi dữ liệu giao dịch tới đó |
| Giả mạo service identity | Một workload không phải `inventory-service` dùng credential chung để đăng ký tên này | Mất khả năng phân biệt service hợp lệ và workload giả |
| Address poisoning | Đăng ký `127.0.0.1`, IP quản trị, IP metadata cloud hoặc hostname do kẻ tấn công kiểm soát | Consumer bị chuyển hướng tới endpoint không mong muốn; có thể tạo SSRF |
| Port/scheme poisoning | Công bố cổng quản trị hoặc dùng HTTP thay cho HTTPS | Lộ actuator/admin endpoint hoặc làm mất bảo vệ TLS |
| Metadata/tag poisoning | Đăng ký tag `trusted`, `zone=prod` hoặc metadata giả | Routing/filter tùy chỉnh có thể chọn nhầm instance |
| Health-check giả | Endpoint luôn trả `UP` dù không phải service hợp lệ | Instance độc hại tồn tại trong tập instance passing |
| Deregistration trái phép | Xóa instance thật hoặc làm thay đổi trạng thái của nó | Gây gián đoạn hoặc ép traffic sang instance giả |
| Credential theft | Lộ Eureka password hoặc Consul ACL token | Kẻ tấn công dùng quyền của workload thật để thao tác registry |

Đừng giả định record có trạng thái `UP` hoặc `passing` là record đáng tin cậy. Health check chứng minh endpoint trả lời theo phép kiểm tra đã cấu hình; nó không chứng minh process thuộc đúng service identity.

## 2. Các lớp bảo vệ cần phối hợp

```mermaid
flowchart TD
    A[Workload khởi động] --> B[Danh tính workload / secret]
    B --> C[Authentication: TLS, Basic Auth hoặc ACL token]
    C --> D[Authorization: workload chỉ được đăng ký service cho phép]
    D --> E[Registry nhận registration]
    E --> F[Validate service ID, address, port và metadata]
    F --> G[Registry / consumer discovery cache]
    G --> H[Consumer kiểm tra endpoint và egress policy]
    H --> I[mTLS hoặc TLS xác minh service đích]
    I --> J[Request tới đúng workload]
```

Phòng thủ nên có nhiều lớp:

1. **Authentication:** xác định workload nào đang gọi registry bằng credential hoặc chứng thư riêng.
2. **Authorization:** giới hạn workload đó được đăng ký, cập nhật, hủy đăng ký hoặc đọc những service nào.
3. **Registration validation:** kiểm tra service ID, instance ID, địa chỉ, port, scheme và metadata theo chính sách.
4. **Network isolation:** chỉ workload và node được phép mới truy cập API registry; không mở cổng quản trị ra Internet.
5. **Consumer-side validation:** không coi hostname/IP từ registry là đích kết nối được tin cậy tuyệt đối.
6. **Service-to-service identity:** dùng TLS/mTLS hoặc service mesh để xác minh peer thực sự khi thiết lập kết nối.
7. **Audit và detection:** theo dõi thay đổi registration, credential và địa chỉ bất thường.

## 3. Bảo vệ Eureka Server

Spring Cloud Netflix tự đăng ký ứng dụng khi starter Eureka Client có trên classpath. Vì vậy, một ứng dụng vừa có thể là producer (đăng ký chính nó), vừa là consumer (đọc registry). Nếu ứng dụng chỉ cần tra cứu, hãy tắt hành vi đăng ký để giảm bề mặt tấn công và tránh đăng ký nhầm:

```yaml
eureka:
  client:
    register-with-eureka: false
    fetch-registry: true
```

Đối với Eureka Server, chỉ cho phép các mạng ứng dụng đã xác định truy cập `/eureka/**`. Dashboard và API registry không nên được public. Hạn chế quyền truy cập ở firewall, security group, ingress hoặc network policy trước khi dựa vào authentication của ứng dụng.

### 3.1. Bật Spring Security cho Eureka Server

Thêm dependency Spring Security vào Eureka Server:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
```

Cấu hình một tài khoản cho ví dụ local hoặc môi trường thử nghiệm:

```yaml
spring:
  security:
    user:
      name: ${EUREKA_USERNAME}
      password: ${EUREKA_PASSWORD}
```

Ví dụ `SecurityFilterChain` cho Spring Security hiện đại:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class EurekaSecurityConfiguration {

    @Bean
    SecurityFilterChain eurekaSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/actuator/health").permitAll()
                        .requestMatchers("/eureka/**").authenticated()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .csrf(csrf -> csrf
                        .ignoringRequestMatchers("/eureka/**"))
                .build();
    }
}
```

Eureka client thường không có CSRF token để gửi cùng request đăng ký/heartbeat. Vì vậy Spring Cloud Netflix hướng dẫn bỏ qua CSRF cho `/eureka/**`. Chỉ bỏ qua CSRF trên API registry này; không tắt CSRF toàn bộ ứng dụng nếu dashboard hoặc các endpoint khác dùng cookie/session.

Đoạn cấu hình trên xác thực mọi request và dùng HTTP Basic. Với hệ thống nhiều workload, một tài khoản dùng chung chỉ xác nhận caller biết cùng credential; nó không tự ràng buộc `inventory-service` chỉ được đăng ký dưới tên `inventory-service`. Muốn phân quyền theo service name, cần danh tính riêng cho từng workload và lớp authorization tùy chỉnh kiểm tra principal với service ID trong request đăng ký. Không xem một SecurityFilterChain chỉ có `.authenticated()` là kiểm soát đầy đủ registry poisoning.

### 3.2. Cấu hình Eureka Client xác thực với server

Spring Cloud Netflix tự thêm HTTP Basic khi URL `defaultZone` chứa username/password:

```yaml
eureka:
  client:
    service-url:
      defaultZone: https://${EUREKA_USERNAME}:${EUREKA_PASSWORD}@eureka.internal:8761/eureka/
```

Đưa credential qua secret manager hoặc environment injection. Ký tự đặc biệt trong username/password cần được URL-encode. Tránh in URL này ra log, exception hoặc Actuator environment endpoint vì URL chứa credential.

Với yêu cầu client certificate authentication, Spring Cloud Netflix hỗ trợ cấu hình key store và trust store:

```yaml
eureka:
  client:
    tls:
      enabled: true
      key-store: ${EUREKA_CLIENT_KEYSTORE}
      key-store-type: PKCS12
      key-store-password: ${EUREKA_CLIENT_KEYSTORE_PASSWORD}
      key-password: ${EUREKA_CLIENT_KEY_PASSWORD}
      trust-store: ${EUREKA_TRUSTSTORE}
      trust-store-type: PKCS12
      trust-store-password: ${EUREKA_TRUSTSTORE_PASSWORD}
```

TLS xác minh server và client certificate giúp bảo vệ đường truyền, đồng thời có thể xác thực workload ở tầng transport nếu server được cấu hình yêu cầu chứng thư. Basic Auth và TLS giải quyết hai lớp khác nhau; không truyền Basic credentials qua HTTP thuần.

### 3.3. Bảo vệ peer replication

Trong Eureka cluster, peer replication là đường gọi nội bộ giữa các Eureka Server. Tài liệu Spring Cloud Netflix lưu ý các request replication như `/eureka/peerreplication/**` không đi qua Spring Security filter chain thông thường. Vì vậy, Basic Auth hoặc OAuth2 filter dùng cho client registration không tự động bảo vệ peer replication.

Với cluster nhiều peer:

- Giới hạn peer traffic bằng private network, firewall và security group chỉ cho các Eureka node.
- Dùng TLS/mTLS cho kết nối giữa các peer.
- Nếu cần header xác thực riêng, cấu hình `ReplicationClientAdditionalFilters` để thêm authentication header cho replication client.
- Kiểm thử riêng register/heartbeat từ application và replication giữa peer; không suy luận bảo vệ peer từ việc dashboard đã yêu cầu đăng nhập.

### 3.4. Địa chỉ và metadata Eureka

Eureka nhận host, port, health URL và metadata từ client. Các giá trị này do client cung cấp; server không tự chứng minh IP đó thuộc workload có tên service tương ứng.

Ví dụ cấu hình service quảng bá endpoint HTTPS:

```yaml
eureka:
  instance:
    non-secure-port-enabled: false
    secure-port-enabled: true
    status-page-url: https://${SERVICE_HOST}/actuator/info
    health-check-url: https://${SERVICE_HOST}/actuator/health
```

Chỉ quảng bá hostname thuộc DNS zone tin cậy và có chứng thư TLS hợp lệ. Không đưa URL quản trị, địa chỉ loopback, IP metadata hoặc host do request bên ngoài điều khiển vào instance metadata.

## 4. Bảo vệ Consul bằng ACL

Consul ACL xác thực request bằng token và phân quyền theo resource. Với datacenter mới, cấu hình `acl.enabled=true` và `acl.default_policy="deny"` để mọi thao tác cần được policy cho phép. Khi bật ACL trên cluster đang hoạt động, triển khai token cho server/agent và workload theo quy trình rollout; không đổi sang deny đột ngột khi các thành phần chưa có token phù hợp.

Ví dụ cấu hình agent:

```hcl
acl {
  enabled = true
  default_policy = "deny"
}
```

### 4.1. Token riêng cho từng workload

Producer `inventory-service` chỉ cần đăng ký service của chính nó có thể dùng policy:

```hcl
service "inventory-service" {
  policy = "write"
}
```

Consumer `order-service` chỉ cần tra cứu `inventory-service` có thể dùng:

```hcl
service "inventory-service" {
  policy = "read"
}

node_prefix "" {
  policy = "read"
}
```

`service:write` cho phép cập nhật registration của service name được chỉ định; `service:read` cho phép đọc service; `node:read` có thể cần để đọc thông tin node/address qua Health API. Giữ rule ở phạm vi service cụ thể khi có thể. Nếu consumer cần đọc nhiều service, chỉ mở rộng prefix theo đúng danh sách upstream mà workload được phép gọi.

HashiCorp cung cấp `builtin/service` templated policy cho use case service identity phổ biến. Template này cấp quyền write/read cho service và node read; nó tiện lợi khi service vừa đăng ký vừa khám phá. Nếu producer chỉ cần đăng ký một service và không cần discovery, custom policy `service "inventory-service" { policy = "write" }` hẹp hơn.

Tạo token từ policy bằng Consul CLI quản trị:

```bash
consul acl policy create \
  -name "inventory-register" \
  -rules @inventory-register.hcl

consul acl token create \
  -description "inventory-service registration token" \
  -policy-name "inventory-register"
```

Token trả về có `AccessorID` và `SecretID`. Lưu `SecretID` vào secret manager; không commit token vào repository, Docker image hoặc log.

### 4.2. Cấu hình Spring Cloud Consul

Producer cần token registration riêng:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: ${CONSUL_HOST}
      port: ${CONSUL_PORT:8500}
      discovery:
        register: true
        acl-token: ${CONSUL_DISCOVERY_TOKEN}
```

Consumer chỉ tra cứu và không cần đăng ký chính nó:

```yaml
spring:
  cloud:
    consul:
      discovery:
        register: false
        acl-token: ${CONSUL_READ_TOKEN}
```

`spring.cloud.consul.discovery.acl-token` là token cho Discovery integration. Nếu ứng dụng còn dùng Consul Config/KV, cấp token riêng với `key_prefix` read đúng phạm vi và cấu hình `spring.cloud.consul.config.acl-token`. Không dùng management token làm token discovery cho mọi service.

### 4.3. ACL không xác thực địa chỉ được công bố

ACL service rule kiểm soát service name và thao tác read/write. Nó không phải chính sách kiểm tra rằng `Address`, `Port`, `TaggedAddresses` hoặc metadata do workload gửi lên có thuộc subnet/host hợp lệ hay không. Một token hợp lệ có `service:write` cho `inventory-service` vẫn có thể bị lạm dụng để đăng ký địa chỉ sai nếu credential bị đánh cắp.

Vì vậy, ngoài ACL cần:

- Cấp token riêng cho từng workload và thu hồi khi workload bị loại bỏ.
- Không cho ứng dụng dùng token của Consul Agent hoặc token management.
- Giới hạn Agent HTTP API trong mạng quản trị/workload tin cậy; không phơi cổng `8500` ra Internet.
- Bật HTTPS/TLS cho API và xác minh chứng thư server; dùng client certificate khi yêu cầu mutual authentication.
- Dùng network policy/firewall để chỉ producer hợp lệ truy cập API đăng ký.
- Audit các thay đổi service registration và đối chiếu address/port với hạ tầng triển khai.

Consul Agent API còn có khả năng nhận health check/script check trong registration. Nếu HTTP API có thể truy cập từ xa, giữ `enable_script_checks=false` trừ khi có nhu cầu và biện pháp bảo vệ cụ thể; HashiCorp cảnh báo script checks có thể tạo rủi ro thực thi lệnh từ xa khi API bị phơi bày.

### 4.4. Consul service mesh là lớp xác thực traffic riêng

Consul ACL bảo vệ thao tác với API/catalog. Nếu dùng Consul Connect service mesh, mTLS và service intentions có thể xác minh service identity khi service-to-service traffic đi qua proxy. Đây là lớp bảo vệ data plane bổ sung; chỉ bật ACL không tự mã hóa hoặc xác thực mọi kết nối HTTP trực tiếp giữa hai ứng dụng.

## 5. Kiểm tra địa chỉ và cổng trước khi tin registry

Consumer thường lấy `ServiceInstance` từ `DiscoveryClient` rồi để LoadBalancer chọn endpoint. Nếu registry bị đầu độc, consumer có thể gọi host do attacker đăng ký. Vì vậy, với service nhạy cảm, cần kiểm tra endpoint theo chính sách của service ID trước khi gửi request.

Ví dụ chính sách:

| Service ID | Scheme được phép | Mạng/hostname được phép | Port được phép |
|---|---|---|---|
| `inventory-service` | `https` | `inventory-*.svc.internal` hoặc subnet workload inventory cụ thể | `8443` |
| `payment-service` | `https` | subnet payment riêng hoặc DNS zone payment | `9443` |
| `notification-service` | `https` | DNS zone notification | `8443` |

Kiểm tra tối thiểu:

1. Service ID có nằm trong allowlist upstream của consumer không?
2. Scheme có phải `https` theo policy không?
3. Hostname có thuộc DNS zone hoặc IP có thuộc CIDR đã phê duyệt không?
4. Port có đúng danh sách port của service không?
5. Instance ID có duy nhất và phù hợp naming convention không?
6. Metadata/tag có đúng schema và giá trị được phép không?
7. TLS certificate của endpoint có xác minh được hostname/service identity mong đợi không?

Không chỉ kiểm tra chuỗi IP bằng regex. Với hostname, cần xét DNS resolution và bảo vệ trước DNS rebinding; đồng thời áp dụng egress firewall/network policy để process không thể kết nối tới loopback, link-local, metadata endpoint hoặc mạng quản trị ngoài phạm vi được phép. Trong hạ tầng dùng private IP, allowlist phải là CIDR của workload cụ thể, không phải chặn toàn bộ dải private.

### 5.1. Ví dụ kiểm tra ServiceInstance ở tầng ứng dụng

Ví dụ dưới đây minh họa policy kiểm tra service ID, HTTPS, port và suffix hostname trước khi tạo request. Trong production, `allowedHosts` nên đến từ cấu hình tin cậy và cần bổ sung kiểm tra DNS/CIDR cùng egress policy:

```java
import java.net.URI;
import java.util.Set;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.stereotype.Component;

@Component
class ServiceInstancePolicy {

    private static final Set<String> ALLOWED_SERVICES =
            Set.of("inventory-service", "payment-service");

    boolean isAllowed(ServiceInstance instance) {
        if (!ALLOWED_SERVICES.contains(instance.getServiceId())) {
            return false;
        }

        URI uri = instance.getUri();
        if (!"https".equalsIgnoreCase(uri.getScheme())) {
            return false;
        }

        String host = uri.getHost();
        if (host == null || !host.endsWith(".svc.internal")) {
            return false;
        }

        return switch (instance.getServiceId()) {
            case "inventory-service" -> instance.getPort() == 8443;
            case "payment-service" -> instance.getPort() == 9443;
            default -> false;
        };
    }
}
```

Đây chỉ là một lớp kiểm tra đơn giản tại consumer. Suffix hostname không thay thế xác minh DNS hoặc chứng thư TLS; attacker có thể kiểm soát DNS nếu zone không được bảo vệ. Với hệ thống lớn, đặt policy trong `ServiceInstanceListSupplier` tùy chỉnh hoặc một adapter discovery dùng chung để mọi đường gọi đều áp dụng cùng quy tắc.

Không chỉ kiểm tra ở controller hoặc một client wrapper nếu ứng dụng có nhiều đường gọi tới cùng service. Mọi client sử dụng discovery cần đi qua lớp kiểm soát thống nhất.

## 6. Bảo vệ metadata, health check và management endpoint

Registry metadata có thể chứa zone, version, weight, tags, status URL và health URL. Nếu custom LoadBalancer hoặc gateway dựa vào metadata để chọn instance, metadata không được xem là dữ liệu đáng tin chỉ vì nó đến từ registry.

Áp dụng các nguyên tắc:

- Chỉ cho phép các key metadata đã định nghĩa; từ chối key tùy ý nếu consumer có thể thực thi logic dựa trên chúng.
- Không dùng tag `trusted`, `admin`, `production` hoặc `internal` như bằng chứng xác thực.
- Không đưa secret, token, password hoặc dữ liệu cá nhân vào metadata.
- Chỉ công bố health/status URL cần thiết; không quảng bá URL actuator quản trị hoặc endpoint chứa thông tin cấu hình.
- Health check cần gọi đúng endpoint và xác minh TLS; trạng thái passing không thay thế service identity.
- Bảo vệ Actuator bằng authentication/network policy và chỉ expose endpoint cần thiết.

Với Eureka, status page và health indicator URL được lưu trong metadata. Với Consul, health check có thể được agent gọi vào ứng dụng. Một registration giả có thể khai báo endpoint health giả nếu không kiểm soát danh tính và địa chỉ của caller.

## 7. Bảo vệ mạng registry và workload

Authentication ở ứng dụng không thay thế network segmentation. Registry là control plane có ảnh hưởng tới nhiều consumer, do đó cần:

- Chỉ mở Eureka `/eureka/**` và Consul HTTP API cho subnet workload/management được phép.
- Tách mạng control plane với traffic nghiệp vụ khi hạ tầng hỗ trợ.
- Dùng TLS cho client-to-registry và peer-to-peer; xác minh certificate chain và hostname.
- Hạn chế truy cập dashboard/UI chỉ cho nhóm vận hành.
- Hạn chế quyền tạo service registration từ CI/CD runner, developer laptop và namespace không tin cậy.
- Dùng Kubernetes NetworkPolicy, firewall hoặc security group để giới hạn producer nào có thể kết nối registry.
- Không expose Consul Agent API, Eureka dashboard hoặc admin endpoint ra Internet công khai.

Nếu registry chạy trong Kubernetes, RBAC cần giới hạn ai được tạo/sửa/xóa `Services`, `Endpoints` và `EndpointSlices`. Admission policy có thể kiểm tra label selector, port, namespace và loại workload được phép publish endpoint. Một service account có quyền sửa EndpointSlice có thể làm thay đổi endpoint mà consumer của Kubernetes Service nhìn thấy.

## 8. Phát hiện registry poisoning

Không chỉ ghi log số lượng instance. Hãy quan sát ai đã thay đổi dữ liệu và trường nào thay đổi.

| Tín hiệu | Điều cần cảnh báo |
|---|---|
| Service name mới | Service ID không thuộc danh sách đã phê duyệt |
| Instance ID | ID trùng, đổi bất thường hoặc không khớp workload identity |
| Address | IP ngoài CIDR service, loopback, link-local, metadata IP hoặc hostname không thuộc DNS zone |
| Port/scheme | Port quản trị, port không được phép hoặc HTTP thay cho HTTPS |
| Metadata/tags | Tag mới, zone/version bất thường hoặc key không nằm trong schema |
| Registration rate | Một token/host đăng ký nhiều service hoặc tạo/xóa instance liên tục |
| Health status | Instance lạ liên tục passing hoặc instance thật đột ngột chuyển critical |
| Credential | Token bị dùng từ host/namespace không mong đợi hoặc xuất hiện sau rotation/revoke |

Với Consul, theo dõi ACL audit/log, AccessorID và các response header cho biết kết quả bị lọc bởi ACL. Với Eureka, theo dõi registration/cancel, instance status, địa chỉ và peer replication. Kết hợp registry event với inventory của orchestrator để đối chiếu instance ID, pod/VM identity và IP thực tế.

## 9. Quy trình xử lý khi phát hiện đăng ký giả

1. Ghi lại service ID, instance ID, address, port, metadata, thời điểm tạo và registry node đã nhận registration.
2. Xác định principal/token/certificate đã thực hiện request nếu hệ thống có audit.
3. So sánh record với orchestrator: pod, VM, deployment, namespace, service account và image version.
4. Chặn traffic tới endpoint nghi vấn bằng network policy/egress rule; không chờ registry cache tự hết hạn nếu có nguy cơ đang bị khai thác.
5. Deregister hoặc đưa instance giả ra khỏi rotation bằng quyền quản trị đã kiểm soát.
6. Thu hồi/rotate credential bị lộ; rà soát các service khác có thể bị đăng ký bằng cùng token.
7. Kiểm tra consumer cache, LoadBalancer cache và connection pool để bảo đảm không còn request tới endpoint cũ.
8. Kiểm tra logs, trace và access logs để xác định request hoặc dữ liệu đã bị chuyển hướng.
9. Khôi phục registration hợp lệ, xác minh health và endpoint từ network của consumer.
10. Tạo cảnh báo và sửa policy/validation gây ra lỗ hổng.

Không chỉ xóa record trong dashboard rồi kết thúc điều tra. Nếu credential vẫn còn hiệu lực hoặc consumer cache chưa cập nhật, tác nhân có thể đăng ký lại hoặc traffic tiếp tục đi tới endpoint cũ.

## 10. Kiểm thử bảo mật trước khi triển khai

Thực hiện trong môi trường staging với token và service giả lập:

1. Gửi registration không có credential; xác nhận bị từ chối.
2. Dùng token của `inventory-service` để đăng ký `payment-service`; xác nhận ACL/custom authorization từ chối.
3. Dùng token consumer read-only để thử registration và deregistration; xác nhận bị từ chối.
4. Đăng ký địa chỉ loopback, IP ngoài CIDR, hostname không thuộc DNS zone và port quản trị; xác nhận validation hoặc egress policy chặn.
5. Đăng ký tag/metadata không được phép; xác nhận consumer không sử dụng nó để nâng quyền hoặc chọn endpoint.
6. Dùng chứng thư TLS không hợp lệ hoặc sai hostname; xác nhận client không kết nối.
7. Thử truy cập registry/dashboard từ mạng không được phép; xác nhận firewall/network policy chặn.
8. Với Eureka cluster, kiểm thử peer replication sau khi bật xác thực; xác nhận peer vẫn đồng bộ và endpoint replication được bảo vệ riêng.
9. Với Consul, thử anonymous request và token sai; xác nhận default-deny hoạt động.
10. Thu hồi token test và xác nhận request mới bị từ chối; kiểm tra rotation không làm lộ token trong log.

Kiểm thử cả chiều producer và consumer. Một registration bị từ chối không đủ chứng minh consumer sẽ từ chối endpoint giả nếu record đó đã tồn tại từ trước hoặc được thêm bởi một nguồn khác.

## 11. Checklist triển khai

- [ ] Registry API chỉ truy cập được từ mạng và workload được phê duyệt.
- [ ] Eureka Server yêu cầu authentication; CSRF chỉ được bỏ qua cho `/eureka/**`.
- [ ] Eureka Client dùng TLS/Basic Auth hoặc client certificate phù hợp; secret không nằm trong Git/log.
- [ ] Eureka peer replication có network isolation và authentication/TLS riêng.
- [ ] Workload chỉ đăng ký nếu thật sự cần; client-only role tắt `register-with-eureka` hoặc `consul.discovery.register`.
- [ ] Consul ACL bật với default policy deny; không dùng management token cho ứng dụng.
- [ ] Mỗi producer có token/policy riêng, giới hạn `service:write` vào đúng service name.
- [ ] Consumer chỉ có quyền read những service/node được phép.
- [ ] Đã hiểu ACL service write không tự xác minh address/port do producer công bố.
- [ ] Address, port, scheme, hostname, instance ID và metadata được kiểm tra theo allowlist.
- [ ] Consumer có egress policy; không kết nối tùy ý tới loopback, link-local, metadata hoặc mạng quản trị.
- [ ] TLS certificate của service đích được xác minh; dùng mTLS/service identity cho service nhạy cảm.
- [ ] Health check không bị coi là bằng chứng xác thực danh tính.
- [ ] Actuator, dashboard và status endpoint được bảo vệ.
- [ ] Có audit/alert cho registration, deregistration, address và metadata thay đổi.
- [ ] Có quy trình xử lý registry poisoning, rotate/revoke credential và làm mới cache.
- [ ] Đã kiểm thử đăng ký giả, token sai quyền, endpoint độc hại và truy cập từ mạng ngoài phạm vi.

## Tài liệu tham khảo

- [Spring Cloud Netflix 5.1.0 — Authenticating with Eureka, Securing Eureka Server and Peer Replication](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Spring Cloud Consul 5.1.0 — Service Discovery and Registration](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Consul — Common Application Properties (`discovery.acl-token`, `discovery.register`)](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [HashiCorp Consul — ACL Best Practices](https://developer.hashicorp.com/consul/docs/secure/acl/best-practice)
- [HashiCorp Consul — Service Registration Tokens](https://developer.hashicorp.com/consul/docs/secure/acl/token/service)
- [HashiCorp Consul — ACL Rules: Service and Node Resources](https://developer.hashicorp.com/consul/docs/secure/acl/rule)
- [HashiCorp Consul — Agent Service Registration API](https://developer.hashicorp.com/consul/api-docs/agent/service)
- [HashiCorp Consul — Core Security Model](https://developer.hashicorp.com/consul/docs/secure/security-model/core)
- [Kubernetes — RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
