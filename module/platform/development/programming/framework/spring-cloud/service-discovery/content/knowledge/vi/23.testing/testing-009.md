# Kiểm thử đường mạng, chứng thư và quyền truy cập bị từ chối

Service discovery chỉ hoạt động khi các thành phần có thể kết nối đến đúng endpoint, xác minh được danh tính của peer và có đủ quyền thực hiện thao tác cần thiết. Một consumer có thể không tìm thấy service vì DNS không phân giải được, TCP bị chặn, TLS từ chối certificate, registry yêu cầu thông tin xác thực hoặc ACL không cho phép đọc catalog. Các lỗi này nhìn bề ngoài đều có thể xuất hiện thành “không có instance”, nhưng cách khắc phục hoàn toàn khác nhau.

Kiểm thử cần xác nhận cả đường đi thành công và đường đi bị từ chối. Với mỗi lớp, phải chứng minh rằng kết nối hợp lệ được chấp nhận và kết nối sai cấu hình hoặc không đủ quyền bị chặn đúng chỗ.

Bài này tập trung vào các kết nối giữa provider, consumer và registry trong Spring Cloud Service Discovery, đặc biệt với Eureka và Consul. Nội dung gồm kiểm tra DNS/TCP/routing, TLS và mutual TLS, xác thực registry, quyền đọc/ghi catalog, kiểm thử HTTP 401/403, NetworkPolicy, kiểm thử tích hợp và xử lý lỗi fail-closed.

## 1. Các lớp cần kiểm thử

Một request service discovery có thể đi qua nhiều lớp:

~~~mermaid
flowchart LR
    APP["Spring Boot provider / consumer"]
    DNS["DNS"]
    NET["Routing / Firewall / NetworkPolicy"]
    TLS["TLS / mTLS"]
    AUTH["Authentication"]
    ACL["Authorization / ACL"]
    REG[("Eureka / Consul")]
    DATA["Service endpoint"]

    APP --> DNS --> NET --> TLS --> AUTH --> ACL --> REG
    APP --> DATA
~~~

Mỗi lớp trả lời một câu hỏi riêng:

| Lớp | Câu hỏi | Dấu hiệu lỗi |
|---|---|---|
| DNS | Hostname có phân giải đúng không? | NXDOMAIN, sai IP, timeout DNS |
| Routing/TCP | Có đường mạng và port đang lắng nghe không? | Connection refused, timeout, no route |
| TLS | Hai bên có tin cậy certificate và tên máy không? | Unknown CA, SAN mismatch, expired certificate |
| mTLS | Client có certificate hợp lệ khi server yêu cầu không? | Handshake failure, certificate required |
| Authentication | Client có chứng minh được danh tính không? | HTTP 401 hoặc lỗi xác thực tương ứng |
| Authorization | Danh tính có quyền thực hiện hành động không? | HTTP 403, ACL permission denied |
| Discovery | Registry có trả đúng service và instance không? | Danh sách rỗng, instance bị filter |

Không gộp tất cả lỗi thành một assertion “service không truy cập được”. Test phải xác định lỗi xuất hiện ở DNS, TCP, TLS, authentication hay authorization. Khi xác định đúng lớp, log và kết quả test mới chỉ ra được nguyên nhân.

## 2. Thiết kế test matrix

Trước khi viết test, lập bảng cho từng luồng cần bảo vệ:

- Provider đăng ký instance vào registry.
- Consumer đọc danh sách service và instance.
- Consumer gọi endpoint của provider.
- Registry server nhận request từ client.
- Monitoring hoặc operator đọc trạng thái registry.
- Health check agent gọi endpoint của provider.

Một luồng có thể cần quyền khác luồng còn lại. Ví dụ provider cần quyền ghi registration của chính service; consumer cần quyền đọc service mà nó phụ thuộc; operator mới có quyền quản trị ACL.

| Nhóm test | Trường hợp hợp lệ | Trường hợp phải bị từ chối |
|---|---|---|
| DNS | Registry hostname phân giải đúng | Hostname sai hoặc không tồn tại |
| TCP | Pod được phép kết nối đúng port | Pod không nằm trong allow rule |
| TLS server | CA, chain, SAN và thời hạn hợp lệ | CA không tin cậy, SAN sai, certificate hết hạn |
| mTLS client | Client certificate được tin cậy | Thiếu certificate hoặc certificate không hợp lệ |
| Eureka authentication | Client có credential hợp lệ | Thiếu hoặc sai Basic Auth |
| Consul ACL | Token có service permission phù hợp | Token thiếu, sai hoặc thiếu quyền đọc/ghi |
| Service authorization | Consumer được gọi API được cấp quyền | Consumer không có role/scope |
| Discovery | Consumer nhìn thấy instance hợp lệ | Không đọc được catalog hoặc instance bị health filter |

Mỗi test case nên ghi rõ:

1. Nguồn gọi: provider, consumer, registry server hay debug Pod.
2. Đích gọi: hostname, port, path và protocol.
3. Danh tính: service account, username, ACL token hoặc client certificate.
4. Quyền mong đợi: read, register, deregister hoặc invoke API.
5. Kết quả mong đợi: success, timeout, TLS failure, 401 hay 403.
6. Log/metric cần xuất hiện để hỗ trợ điều tra.

Test từ đúng môi trường chạy ứng dụng. Lệnh chạy trên laptop có thể thành công trong khi Pod bị NetworkPolicy chặn, DNS search path khác hoặc truststore của JVM không có CA nội bộ.

## 3. Kiểm thử DNS, routing và TCP

### 3.1. Xác minh DNS

Trước khi kiểm tra TLS hoặc ACL, xác minh hostname registry và service endpoint có phân giải đúng từ network namespace của workload.

Ví dụ trên Linux container:

~~~bash
getent hosts consul.service.internal
nslookup consul.service.internal
~~~

Nếu dùng Kubernetes, kiểm tra từ Pod trong cùng namespace với provider hoặc consumer:

~~~bash
kubectl exec deploy/inventory-service -- nslookup consul-server.registry.svc.cluster.local
~~~

Các trường hợp nên kiểm thử:

- Hostname hợp lệ trả về đúng địa chỉ.
- Hostname không tồn tại trả về NXDOMAIN.
- DNS nội bộ không bị ghi đè bởi search domain hoặc DNS record cũ.
- Pod có thể truy cập DNS server qua UDP và TCP port 53.
- Service discovery dùng DNS SRV phải trả đúng target và port nếu kiến trúc phụ thuộc SRV.

DNS thành công chỉ chứng minh tên được phân giải. Nó không chứng minh port có thể kết nối hoặc certificate của endpoint hợp lệ.

### 3.2. Kiểm tra TCP và port

Dùng công cụ TCP từ chính workload hoặc debug Pod có cùng policy:

~~~bash
nc -vz consul.service.internal 8501
nc -vz eureka.service.internal 8761
~~~

Có thể dùng curl để kiểm tra kết nối HTTP/HTTPS:

~~~bash
curl --connect-timeout 3 --max-time 8 -v https://consul.service.internal:8501/v1/status/leader
~~~

Diễn giải thường gặp:

| Kết quả | Ý nghĩa có thể có | Kiểm tra tiếp |
|---|---|---|
| Connection refused | Host reachable nhưng port không có listener hoặc bị reject | Service port, targetPort, process |
| Connection timed out | Packet bị drop, route lỗi hoặc policy chặn | NetworkPolicy, firewall, route, CNI |
| No route to host | Không có route phù hợp hoặc lỗi mạng | Routing table, subnet, gateway |
| DNS lookup failed | Hostname không phân giải | DNS zone, CoreDNS, search path |
| TCP connect thành công | Đã mở được socket | Tiếp tục kiểm tra TLS và HTTP |

Timeout không tự chứng minh NetworkPolicy là nguyên nhân. Cần so sánh từ Pod được phép và Pod bị chặn, kiểm tra CNI/firewall và xác nhận packet có tới đích hay không.

### 3.3. Kiểm thử Kubernetes NetworkPolicy

Kubernetes NetworkPolicy kiểm soát traffic ở lớp L3/L4. Một Pod bị cô lập cho egress chỉ được kết nối tới các đích được rule cho phép; Pod đích cũng cần có ingress rule cho phép nếu nó bị cô lập ingress. Các rule của nhiều policy được cộng dồn, không có quy tắc “deny thắng allow” theo thứ tự khai báo. Cluster phải dùng CNI có hỗ trợ thực thi NetworkPolicy.

Ví dụ policy giới hạn traffic của inventory-service:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: inventory-network-access
  namespace: apps
spec:
  podSelector:
    matchLabels:
      app: inventory-service
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: gateway
          podSelector:
            matchLabels:
              app: api-gateway
      ports:
        - protocol: TCP
          port: 8080
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: registry
          podSelector:
            matchLabels:
              app: consul
      ports:
        - protocol: TCP
          port: 8501
~~~

Đây là policy minh họa. Nhãn namespace và Pod DNS thay đổi theo cluster; hãy kiểm tra nhãn thực tế bằng lệnh **kubectl get namespace --show-labels** và **kubectl get pods -n kube-system --show-labels**. Nếu ứng dụng còn cần database, message broker, telemetry hoặc endpoint khác, phải thêm allow rule tương ứng. Default-deny egress cũng chặn DNS nếu chưa cho phép DNS riêng.

Bộ test cần có cả đường cho phép và đường bị chặn:

1. Pod api-gateway trong namespace được phép gọi inventory-service:8080: kết nối thành công.
2. Pod ở namespace không được phép gọi cùng endpoint: kết nối bị chặn.
3. inventory-service gọi Consul port 8501: kết nối thành công.
4. inventory-service gọi port không được phép: kết nối thất bại.
5. inventory-service phân giải hostname Consul: DNS vẫn hoạt động nhờ rule UDP/TCP 53.

NetworkPolicy không thay thế TLS hoặc ACL. Một kết nối được phép qua port 8501 vẫn phải xác minh certificate và token. Ngược lại, token hợp lệ không thể giúp request đi qua một đường mạng bị chặn.

## 4. Kiểm thử TLS certificate

TLS server authentication giúp client xác minh server đang kết nối là endpoint được tin cậy. Không chỉ kiểm tra rằng handshake hoàn tất; cần xác minh toàn bộ chain, hostname và thời hạn certificate.

Các điều kiện cần kiểm tra:

- Certificate server còn hiệu lực theo thời gian hiện tại.
- Certificate chưa đến NotBefore và chưa vượt NotAfter.
- Chain có thể nối tới CA được truststore tin cậy.
- Subject Alternative Name (SAN) khớp hostname client sử dụng.
- Extended Key Usage cho phép serverAuth.
- Server gửi đủ intermediate certificate cần thiết.
- SNI được gửi đúng nếu endpoint phục vụ nhiều hostname trên cùng IP.
- Protocol/cipher được hai bên hỗ trợ theo chính sách bảo mật.

### 4.1. Kiểm tra certificate và SAN

Dùng OpenSSL để đọc certificate:

~~~bash
openssl x509 -in server.crt -noout -subject -issuer -dates -ext subjectAltName -ext extendedKeyUsage
~~~

Dùng keytool để xem nội dung truststore:

~~~bash
keytool -list -v -keystore registry-truststore.p12 -storetype PKCS12
~~~

Kiểm tra fingerprint CA theo một kênh đáng tin cậy trước khi import certificate vào truststore. Không import một certificate chỉ vì nó được tải về từ chính endpoint đang cần xác minh.

### 4.2. Kiểm tra TLS server bằng OpenSSL

~~~bash
openssl s_client \
  -connect consul.service.internal:8501 \
  -servername consul.service.internal \
  -verify_hostname consul.service.internal \
  -CAfile registry-ca.pem \
  -verify_return_error \
  </dev/null
~~~

Các tham số có ý nghĩa:

- -connect: địa chỉ và port TCP.
- -servername: hostname gửi trong TLS SNI.
- -verify_hostname: xác minh hostname có khớp certificate hay không.
- -CAfile: CA được client tin cậy.
- -verify_return_error: dừng khi xác minh certificate thất bại.

Handshake chỉ được xem là hợp lệ khi xác minh chain và hostname thành công. Tham số -showcerts có thể hiển thị các certificate server gửi, nhưng danh sách hiển thị không tự chứng minh chain đã được xác minh.

### 4.3. Kiểm thử lỗi certificate có chủ đích

Tạo certificate kiểm thử riêng trong môi trường test, không sửa certificate production. Các test âm tính nên gồm:

| Test | Cách tạo điều kiện lỗi | Kết quả mong đợi |
|---|---|---|
| Unknown CA | Dùng CA khác với truststore | TLS verification thất bại |
| SAN mismatch | Gọi hostname không có trong SAN | Hostname verification thất bại |
| Expired certificate | Dùng cert đã hết hạn | Client từ chối handshake |
| Not-yet-valid | Dùng cert có NotBefore trong tương lai | Client từ chối handshake |
| Missing intermediate | Server không gửi intermediate cần thiết | Chain validation thất bại nếu client không có intermediate |
| Wrong SNI | Gửi SNI khác với virtual host cần kiểm tra | Nhận certificate sai hoặc handshake/verification thất bại |
| Weak protocol | Chỉ bật protocol không được client cho phép | Handshake thất bại |

Không dùng curl -k, --insecure, trust-all manager hoặc tắt hostname verification để làm test pass. Những lựa chọn này bỏ qua đúng cơ chế mà test cần xác minh.

## 5. Kiểm thử mutual TLS

Mutual TLS (mTLS) yêu cầu cả client và server trình certificate để xác minh danh tính ở tầng TLS:

- Client xác minh certificate server bằng truststore.
- Server xác minh certificate client bằng CA truststore của server.
- Server có thể yêu cầu certificate (need) hoặc chỉ yêu cầu nếu client gửi (want), tùy cấu hình.

Khi registry hoặc service endpoint yêu cầu client certificate, test tối thiểu cần có:

1. Client có certificate hợp lệ do CA được server tin cậy cấp: handshake thành công.
2. Client không gửi certificate: server từ chối khi cấu hình bắt buộc client cert.
3. Client gửi certificate do CA không tin cậy cấp: server từ chối.
4. Client gửi certificate hết hạn hoặc sai mục đích clientAuth: server từ chối.
5. Client certificate hợp lệ nhưng ACL/application authorization không đủ: TLS có thể thành công nhưng request vẫn bị từ chối ở lớp authorization.

Với embedded web server của Spring Boot, cấu hình mTLS bắt buộc có thể dùng `server.ssl.client-auth: need` cùng keystore của server và truststore chứa CA cấp client certificate:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    client-auth: need
    key-store: file:/run/secrets/service-server.p12
    key-store-type: PKCS12
    key-store-password: "<secret injected by deployment>"
    trust-store: file:/run/secrets/client-ca-truststore.p12
    trust-store-type: PKCS12
    trust-store-password: "<secret injected by deployment>"
~~~

Chỉ dùng `need` khi mọi client trên listener đó phải gửi certificate. Nếu chỉ muốn yêu cầu certificate với một số route, cần thiết kế listener hoặc gateway phù hợp; mTLS ở handshake không phân quyền theo HTTP path.

Kiểm thử bằng OpenSSL:

~~~bash
openssl s_client \
  -connect registry.service.internal:8501 \
  -servername registry.service.internal \
  -verify_hostname registry.service.internal \
  -CAfile registry-ca.pem \
  -cert discovery-client.crt \
  -key discovery-client.key \
  -verify_return_error \
  </dev/null
~~~

Test không có -cert và -key phải thất bại nếu server yêu cầu mTLS. Test với client certificate không tin cậy cũng phải thất bại.

mTLS xác thực certificate của peer ở tầng kết nối. Nó không tự cấp quyền đọc service payment-service hay ghi registration của inventory-service; quyền nghiệp vụ vẫn cần ACL hoặc authorization riêng.

## 6. Kiểm thử HTTPS với Spring Boot

Spring Boot cung cấp SSL Bundles để gom keystore, truststore và thông tin TLS thành cấu hình có tên. Ví dụ cấu hình bundle JKS/PKCS12 cho một client:

~~~yaml
spring:
  ssl:
    bundle:
      jks:
        registry-client:
          keystore:
            location: file:/run/secrets/discovery-client.p12
            password: "<secret injected by deployment>"
            type: PKCS12
          truststore:
            location: file:/run/secrets/registry-truststore.p12
            password: "<secret injected by deployment>"
            type: PKCS12
~~~

Bundle có thể được lấy qua bean SslBundles để tạo SSLContext cho HTTP client tùy chỉnh. Không giả định mọi thư viện client tự động sử dụng bundle này; phải xác minh adapter HTTP thực tế đang dùng truststore và keystore mong muốn.

### 6.1. Eureka client TLS

Spring Cloud Netflix có cấu hình TLS riêng cho Eureka client:

~~~yaml
eureka:
  client:
    tls:
      enabled: true
      key-store: file:/run/secrets/eureka-client.p12
      key-store-type: PKCS12
      key-store-password: "<secret injected by deployment>"
      key-password: "<secret injected by deployment>"
      trust-store: file:/run/secrets/eureka-truststore.p12
      trust-store-type: PKCS12
      trust-store-password: "<secret injected by deployment>"
~~~

eureka.client.tls.enabled phải bật để Eureka client dùng TLS material được cấu hình. Nếu không khai báo truststore, client có thể sử dụng JVM default truststore. Trong test, hãy cố ý dùng truststore chỉ chứa CA test để chứng minh client thực sự xác minh đúng CA nội bộ.

### 6.2. Consul client HTTPS và service scheme

Spring Cloud Consul phân biệt scheme dùng để gọi Consul Agent với scheme công bố cho service instance:

- spring.cloud.consul.scheme: HTTP/HTTPS của kết nối tới Consul Agent.
- spring.cloud.consul.discovery.scheme: scheme của service được đăng ký trong catalog.

Ví dụ:

~~~yaml
spring:
  cloud:
    consul:
      scheme: https
      host: consul.service.internal
      port: 8501
      discovery:
        scheme: https
        acl-token: "<discovery token injected by secret manager>"
~~~

Cấu hình trust material và client certificate phải khớp với TLS listener của Consul và phiên bản Spring Cloud Consul đang dùng. Không bật health-check-tls-skip-verify trong production để che lỗi certificate; chỉ dùng tùy chọn bỏ xác minh trong fixture test có chủ đích và khẳng định nó đang được tắt ở cấu hình triển khai.

### 6.3. Kiểm tra bằng curl

HTTPS với CA nội bộ:

~~~bash
curl --cacert registry-ca.pem \
  --connect-timeout 3 \
  https://consul.service.internal:8501/v1/status/leader
~~~

mTLS với client certificate:

~~~bash
curl --cacert registry-ca.pem \
  --cert discovery-client.crt \
  --key discovery-client.key \
  https://consul.service.internal:8501/v1/status/leader
~~~

Để kiểm thử certificate sai, dùng CA/certificate fixture không hợp lệ và xác nhận curl dừng ở lỗi TLS. Không dùng --insecure trong test thành công.

## 7. Kiểm thử xác thực và bảo vệ Eureka

Eureka server có thể được bảo vệ bằng Spring Security. Client có thể dùng HTTP Basic Authentication; Spring Cloud Netflix tự thêm Basic Auth khi URL eureka.client.serviceUrl.defaultZone chứa credentials theo dạng URL. Với nhu cầu phức tạp hơn, có thể tùy biến DiscoveryClientOptionalArgs và ClientFilter.

Ví dụ URL minh họa:

~~~yaml
eureka:
  client:
    serviceUrl:
      defaultZone: https://<username>:<password>@eureka.service.internal/eureka/
~~~

Credentials phải được inject từ secret store, không commit vào source control hoặc log URL đầy đủ. Tài liệu Eureka cũng lưu ý giới hạn về nhiều bộ Basic Auth theo từng server URL; kiểm tra kỹ nếu cấu hình nhiều Eureka server với credential khác nhau.

### 7.1. Bảo vệ endpoint Eureka bằng Spring Security

Ví dụ cấu hình filter chain:

~~~java
@Bean
SecurityFilterChain eurekaSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/eureka/**").hasRole("REGISTRY_CLIENT")
            .requestMatchers("/admin/**").hasRole("REGISTRY_ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .csrf(csrf -> csrf.ignoringRequestMatchers("/eureka/**"));

    return http.build();
}
~~~

Eureka client không thường gửi CSRF token. Vì vậy ví dụ bỏ CSRF cho endpoint registry /eureka/** để client có thể đăng ký và heartbeat. Chỉ bỏ CSRF ở path registry cần thiết; không tắt CSRF toàn ứng dụng theo thói quen.

Trong hệ thống thực tế, nên tách quyền registry client, dashboard operator và endpoint quản trị. Không cấp quyền admin cho mọi service chỉ để client có thể register.

### 7.2. Test authentication và authorization

Với Eureka endpoint yêu cầu Basic Auth, kiểm thử:

| Request | Kết quả mong đợi |
|---|---|
| Không gửi credentials | 401 Unauthorized |
| Username/password sai | 401 Unauthorized |
| Credentials hợp lệ và đúng role | Thành công |
| Đã xác thực nhưng thiếu role cần thiết | 403 Forbidden |
| Client gửi POST registration với policy CSRF đã cấu hình | Không bị từ chối vì thiếu CSRF token ở /eureka/** |
| POST vào endpoint quản trị không có quyền | 403 Forbidden |

401 thường biểu thị request chưa được xác thực; 403 biểu thị danh tính đã được nhận diện nhưng không có quyền. Tuy nhiên, status code cụ thể còn phụ thuộc authentication entry point, reverse proxy và framework. Hãy kiểm thử contract của hệ thống đang chạy, đồng thời xác nhận response body/log không tiết lộ credential.

## 8. Kiểm thử Consul ACL

Consul dùng ACL token để xác thực request và policy để cấp quyền. HTTP API chấp nhận token qua header X-Consul-Token hoặc Bearer authorization header. Khi bật ACL, không có token thì Consul có thể dùng default token hoặc anonymous token tùy cấu hình; do đó test thiếu header phải xác minh chính sách anonymous/default thực tế.

Spring Cloud Consul có property riêng:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        acl-token: "<service discovery token from secret manager>"
~~~

Không nhầm spring.cloud.consul.discovery.acl-token với spring.cloud.consul.config.acl-token. Một token dành cho đọc cấu hình KV không tự động là token phù hợp cho service registration/discovery.

### 8.1. Quyền tối thiểu cho provider và consumer

Provider thường cần quyền ghi registration của chính service. Consumer cần quyền đọc những service mà nó phải tìm. Ví dụ policy Consul HCL:

~~~hcl
service "inventory-service" {
  policy = "write"
}

service "order-service" {
  policy = "read"
}

node_prefix "" {
  policy = "read"
}
~~~

Nếu consumer phải khám phá nhiều service, cấp quyền đọc theo đúng danh sách service hoặc prefix được phê duyệt. Tránh dùng token global-management cho ứng dụng. node:read có thể cần cho một số thao tác Catalog/Health hoặc service mesh; xác định quyền theo API và kiến trúc đang dùng.

### 8.2. Kiểm tra request Consul

Ví dụ query Catalog với token:

~~~bash
curl \
  --header "X-Consul-Token: $CONSUL_HTTP_TOKEN" \
  https://consul.service.internal:8501/v1/catalog/services \
  --cacert registry-ca.pem
~~~

Kiểm tra Health API của một service:

~~~bash
curl \
  --header "X-Consul-Token: $CONSUL_HTTP_TOKEN" \
  "https://consul.service.internal:8501/v1/health/service/inventory-service" \
  --cacert registry-ca.pem
~~~

Có thể dùng Bearer token nếu API client được cấu hình theo cách đó:

~~~http
Authorization: Bearer <consul-token>
~~~

Không đưa token vào query string vì URL thường bị ghi vào access log, proxy log hoặc telemetry. Không bật debug logging chứa toàn bộ HTTP headers khi chạy test với token thật.

### 8.3. Các test ACL bắt buộc

| Token | Hành động | Kết quả mong đợi |
|---|---|---|
| Không có token | Đọc catalog | Chỉ thành công nếu anonymous/default policy cho phép |
| Token không hợp lệ | Đọc catalog | Bị từ chối |
| Token chỉ có service read | Đọc service được phép | Thành công |
| Token chỉ có service read | Register hoặc update service | Bị từ chối |
| Token có write cho inventory-service | Register inventory-service | Thành công |
| Token có write cho inventory-service | Register payment-service | Bị từ chối |
| Token của consumer chỉ đọc order-service | Query inventory-service | Bị từ chối hoặc không trả dữ liệu theo policy/version |
| Token service | Tạo ACL policy/token | Bị từ chối vì không có acl:write |

Với Consul, một số endpoint có thể lọc kết quả theo quyền thay vì trả toàn bộ dữ liệu. Vì vậy, test cần xác minh cả HTTP status, response body và việc entry không xuất hiện. Không chỉ assert status code.

## 9. Phân biệt 401, 403 và lỗi TLS

Không phải mọi request bị từ chối đều trả cùng loại lỗi. TLS handshake xảy ra trước HTTP; nếu TLS thất bại, server chưa nhận được HTTP request nên không có HTTP 401/403.

| Lỗi | Lớp | Cách nhận biết |
|---|---|---|
| TLS handshake failure | TLS | OpenSSL/JVM báo lỗi certificate hoặc handshake; không có HTTP response |
| 401 Unauthorized | Authentication | Thiếu hoặc sai credential theo authentication entry point |
| 403 Forbidden | Authorization/CSRF | Đã xác thực nhưng không đủ quyền hoặc request thiếu CSRF token |
| 404 Not Found | HTTP routing/filtering | Sai path hoặc API cố ý che resource không được phép |
| 429 Too Many Requests | Rate limit | Request vượt quota/rate limit |
| 5xx | Server/proxy | Lỗi xử lý phía server, upstream hoặc gateway |
| TCP timeout | Network | Không hoàn thành kết nối trước timeout |

Một ACL denial của Consul có thể có response code/body theo endpoint và phiên bản. Hãy kiểm tra thông điệp permission denied và policy evaluation thay vì giả định mọi ACL failure luôn là 403.

## 10. Kiểm thử authorization ở ứng dụng Spring Security

Registry ACL kiểm soát ai được đọc/ghi catalog. Nó không thay thế authorization cho API nghiệp vụ. Một consumer tìm thấy payment-service không có nghĩa consumer được quyền gọi mọi endpoint của service đó.

Dùng spring-security-test để kiểm tra rule ở tầng web:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ServiceAccessTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotReadInternalEndpoint() throws Exception {
        mvc.perform(get("/internal/instances"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "READER")
    void readerCannotRegisterService() throws Exception {
        mvc.perform(post("/internal/registry/register").with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "REGISTRY_ADMIN")
    void registryAdminCanRegisterService() throws Exception {
        mvc.perform(post("/internal/registry/register").with(csrf()))
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

Các path và role trong ví dụ là do ứng dụng tự định nghĩa. Nếu endpoint POST không nằm trong CSRF ignore list, test cần gửi CSRF token hợp lệ; test thiếu hoặc sai token phải bị từ chối.

MockMvc kiểm tra Spring MVC và security filter chain. Nó không kiểm tra DNS, NetworkPolicy, TLS handshake thật hoặc ACL của Consul. Cần test ở các tầng tương ứng.

## 11. Kiểm thử tích hợp với registry thật

Unit test có thể mock DiscoveryClient, nhưng mock không chứng minh rằng client có thể kết nối, xác minh certificate, gửi token hoặc xử lý quyền bị từ chối đúng cách.

Một bộ integration test nên chạy với registry có version cố định trong môi trường cô lập:

- Eureka Server có Spring Security và TLS được cấu hình như production.
- Consul Agent/server bật ACL và HTTPS.
- Spring Boot provider đăng ký instance.
- Spring Boot consumer gọi DiscoveryClient và LoadBalancer.
- CA, client certificate, truststore và ACL token là fixture test ngắn hạn.

Kịch bản tối thiểu:

1. Khởi động registry và kiểm tra health.
2. Provider dùng certificate/token hợp lệ đăng ký service.
3. Consumer có quyền đọc nhìn thấy service.
4. Consumer gọi instance và nhận response thành công.
5. Provider dùng token read-only thử register: phải bị từ chối.
6. Consumer dùng token không có quyền read thử discovery: phải bị từ chối hoặc không thấy entry theo ACL contract.
7. Client dùng CA sai hoặc hostname sai: TLS phải thất bại trước HTTP.
8. Client không có certificate khi mTLS bắt buộc: handshake phải thất bại.
9. Chặn TCP bằng network policy: client không thể kết nối dù token và certificate hợp lệ.
10. Khôi phục policy/credential hợp lệ: service registration và discovery hoạt động trở lại.

Dùng Testcontainers hoặc môi trường ephemeral tương đương để tạo registry và network dependencies có thể tái lập. Pin version image theo release đang triển khai; không dùng latest trong CI vì thay đổi phiên bản có thể làm kết quả test không ổn định.

## 12. Kiểm thử fail-closed và không hạ cấp bảo mật

Khi registry không truy cập được hoặc token bị từ chối, ứng dụng phải có hành vi đã được xác định trước:

- Provider không được giả vờ registration thành công khi registry từ chối ghi.
- Consumer không được chuyển sang HTTP không mã hóa chỉ vì HTTPS lỗi.
- Client không được bỏ qua certificate validation để tiếp tục kết nối.
- Token thiếu quyền không được thay bằng token quản trị hoặc anonymous quyền rộng.
- Không được dùng endpoint tĩnh không kiểm soát như fallback để vượt qua policy discovery.
- Nếu consumer dùng cache cũ trong thời gian registry outage, phải có policy rõ về thời gian chấp nhận dữ liệu stale và cách xử lý endpoint đã bị thu hồi.

Không phải hệ thống nào cũng cần dừng toàn bộ ứng dụng khi registry outage. Quyết định fail-fast hay tiếp tục phục vụ từ cache phụ thuộc vai trò service và SLO. Điều bắt buộc là không che giấu lỗi xác thực/phân quyền bằng cách âm thầm chuyển sang một đường kết nối kém an toàn hơn.

Kiểm tra các tình huống:

| Tình huống | Hành vi cần xác minh |
|---|---|
| Registry timeout khi startup | Startup fail hoặc degraded theo policy đã định nghĩa; có log/metric |
| Registration bị 403 | Không đánh dấu instance đã đăng ký thành công |
| Discovery query bị ACL deny | Không trả danh sách giả hoặc fallback trái phép |
| Certificate hết hạn | Client từ chối TLS và cảnh báo |
| Truststore thiếu CA mới | Kết nối thất bại rõ ràng, không trust-all |
| Registry outage sau khi đã cache | Cache chỉ được dùng trong giới hạn stale-data policy |
| Credential bị revoke | Request tiếp theo bị từ chối và hệ thống không tiếp tục dùng credential cũ vô thời hạn |

## 13. Kiểm thử rotation certificate và token

Certificate và ACL token đều có vòng đời. Test chỉ chạy lúc khởi động sẽ không phát hiện lỗi khi credential được xoay vòng.

### 13.1. Certificate rotation

Kiểm thử quy trình CA/certificate mới:

1. Client trust cả CA cũ và CA mới trong giai đoạn chuyển tiếp.
2. Server chuyển certificate sang CA mới.
3. Client xác minh handshake thành công với certificate mới.
4. Xác minh log không còn lỗi trust hoặc hostname.
5. Sau khi toàn bộ client đã chuyển, loại CA cũ khỏi truststore.
6. Xác minh certificate cũ không còn được chấp nhận.

Nếu Spring Boot SSL Bundle bật reload-on-update, kiểm tra file watcher và component tiêu thụ bundle có hỗ trợ reload. Không giả định mọi HTTP client của Eureka/Consul tự động reload truststore chỉ vì file đã đổi; cần kiểm thử đúng client implementation.

### 13.2. ACL token rotation

1. Tạo token mới với đúng policy tối thiểu.
2. Deploy token mới vào provider/consumer.
3. Xác minh register, discovery và health query thành công.
4. Revoke token cũ.
5. Xác minh token cũ bị từ chối.
6. Kiểm tra log, environment và secret volume không còn giữ token cũ ngoài thời gian cho phép.

Không ghi secret ID vào test report. Chỉ ghi token alias, policy name, thời điểm rotation và kết quả.

## 14. Quan sát và chẩn đoán

Test bảo mật cần để lại đủ dữ liệu để tìm lỗi nhưng không làm lộ secret.

Các tín hiệu hữu ích:

- DNS resolution failures.
- TCP connect timeout/refused.
- TLS handshake failure theo nhóm nguyên nhân.
- Certificate expiry và số ngày còn lại.
- Eureka registration/authentication failure.
- Consul ACL permission denied.
- HTTP 401/403 theo endpoint và client identity.
- Discovery result count và số instance bị filter.
- Thời điểm token/certificate rotation.

Không ghi:

- Password, Basic Auth header hoặc URL có credentials.
- X-Consul-Token hoặc Bearer token.
- Private key, keystore password hoặc nội dung secret.
- Toàn bộ request header khi debug HTTP client.

Khi log một lỗi, ghi service name, registry endpoint alias, operation, error category, correlation ID và status code. Hostname/IP có thể được đưa vào log nội bộ theo policy, nhưng không đưa chúng vào metric label có cardinality không giới hạn.

## 15. Ma trận kiểm thử mẫu cho CI/CD

Có thể dùng ma trận sau làm tiêu chí nghiệm thu:

| ID | Điều kiện | Kết quả mong đợi |
|---|---|---|
| NET-01 | DNS registry hợp lệ | Resolve đúng hostname |
| NET-02 | DNS hostname sai | NXDOMAIN/resolve failure được phát hiện |
| NET-03 | Pod được allow kết nối registry | TCP connect thành công |
| NET-04 | Pod bị deny egress | Không mở được TCP connection |
| TLS-01 | Server cert hợp lệ, đúng SAN | TLS handshake thành công |
| TLS-02 | CA không được trust | TLS handshake thất bại |
| TLS-03 | SAN không khớp | Hostname verification thất bại |
| TLS-04 | Server cert hết hạn | TLS verification thất bại |
| MTLS-01 | Client cert hợp lệ | Handshake thành công |
| MTLS-02 | Thiếu client cert | Server từ chối khi mTLS bắt buộc |
| MTLS-03 | Client cert từ CA sai | Server từ chối |
| EUREKA-01 | Basic Auth đúng | Client đọc/ghi registry theo quyền |
| EUREKA-02 | Basic Auth sai | Request bị từ chối |
| CONSUL-01 | Token có service write | Provider đăng ký service được cấp quyền |
| CONSUL-02 | Token chỉ read | Register bị từ chối |
| CONSUL-03 | Token thiếu service read | Consumer không đọc được service ngoài scope |
| AUTH-01 | Request anonymous vào endpoint nội bộ | 401 theo security contract |
| AUTH-02 | User đã xác thực nhưng thiếu role | 403 theo security contract |
| AUTH-03 | CSRF token thiếu/sai ở endpoint có bảo vệ CSRF | 403 |
| ROT-01 | Token mới được triển khai | Request hợp lệ thành công |
| ROT-02 | Token cũ bị revoke | Request dùng token cũ bị từ chối |

Một test chỉ PASS khi xác nhận cả hành vi cho phép và hành vi từ chối. Ví dụ, test token read-only không chỉ cần thấy request register thất bại; cần kiểm tra service vẫn đọc được đúng catalog mà token được cấp quyền, để tránh test “đạt” do registry hoàn toàn không kết nối được.

## 16. Quy trình điều tra khi test thất bại

Khi consumer không tìm thấy service hoặc registration thất bại:

1. Kiểm tra hostname và DNS từ Pod đang chạy ứng dụng.
2. Kiểm tra TCP tới đúng host/port.
3. Nếu HTTPS, xác minh chain, SAN, expiry và SNI bằng OpenSSL.
4. Nếu mTLS, kiểm tra client certificate và CA trust của server.
5. Kiểm tra HTTP status và response body sau khi TLS thành công.
6. Kiểm tra Basic Auth hoặc Consul ACL token.
7. Đối chiếu policy với hành động read/register/deregister cụ thể.
8. Kiểm tra NetworkPolicy ingress/egress và CNI enforcement.
9. Kiểm tra application log, registry log và metric cùng timestamp.
10. Chạy lại positive test sau khi sửa để bảo đảm đường hợp lệ vẫn hoạt động.

Không đổi đồng thời firewall, truststore, token và policy trong một lần thử. Thay từng lớp để giữ được quan hệ nguyên nhân-kết quả.

## 17. Ghi nhớ

- DNS, TCP, TLS, authentication và authorization là các lớp độc lập; test cần xác định lỗi đúng lớp.
- NetworkPolicy chỉ kiểm soát traffic L3/L4; cả egress của nguồn và ingress của đích có thể cần cho phép.
- TLS cần xác minh chain, SAN, thời hạn, SNI và mục đích certificate.
- mTLS xác minh certificate client nhưng không tự cấp quyền đọc/ghi registry.
- Eureka có thể dùng Basic Auth và cấu hình TLS riêng qua eureka.client.tls.*.
- Consul dùng ACL token; Spring Cloud Consul có spring.cloud.consul.discovery.acl-token.
- Consul phân biệt spring.cloud.consul.scheme cho kết nối Agent và spring.cloud.consul.discovery.scheme cho service registration.
- 401 thường liên quan authentication; 403 thường liên quan authorization hoặc CSRF; TLS handshake failure xảy ra trước HTTP.
- MockMvc không thay thế test mạng, TLS hoặc registry thật.
- Không dùng curl -k, trust-all, token admin hoặc fallback HTTP để làm test pass.
- Kiểm thử rotation certificate và token, không chỉ kiểm tra lúc startup.
- Log đủ thông tin chẩn đoán nhưng tuyệt đối không ghi credential hoặc private key.

Kiểm thử đường mạng, certificate và quyền bị từ chối giúp xác minh rằng service chỉ được đăng ký, khám phá và gọi qua những kết nối được phép. Khi positive test và negative test chạy từ đúng môi trường triển khai, nhóm phát triển có thể phát hiện sớm lỗi DNS, policy, TLS, credential và ACL trước khi chúng biến thành sự cố discovery trong production.

## Tài liệu tham khảo

- [Spring Cloud Netflix — Authenticating with Eureka Server and Client TLS](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Spring Cloud Consul — Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [Spring Cloud Consul — Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Boot — SSL Bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Spring Security — CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [Consul — HTTP API Authentication](https://developer.hashicorp.com/consul/api-docs/api-structure)
- [Consul — ACL Rules](https://developer.hashicorp.com/consul/docs/secure/acl/rule)
- [Consul — Service Tokens](https://developer.hashicorp.com/consul/docs/secure/acl/token/service)
- [OpenSSL — s_client](https://docs.openssl.org/master/man1/openssl-s_client/)
- [Oracle JDK — keytool](https://docs.oracle.com/en/java/javase/25/docs/specs/man/keytool.html)
