# Lỗi tên miền, NAT, TLS, xác thực và đồng bộ thời gian

Service discovery có thể trả về một instance hợp lệ nhưng consumer vẫn không gọi được service. Nguyên nhân thường nằm trong năm nhóm: DNS phân giải sai, địa chỉ được công bố không đi qua được NAT/routing, TLS không xác minh được certificate, registry từ chối xác thực/ủy quyền hoặc đồng hồ giữa các máy bị lệch.

Khi xử lý sự cố trong Spring Cloud Service Discovery, cần phân biệt **địa chỉ registry** với **địa chỉ instance được công bố**. Provider dùng địa chỉ thứ nhất để đăng ký; consumer dùng địa chỉ thứ hai để gọi request nghiệp vụ. Một lỗi DNS ở registry endpoint có thể khiến provider không đăng ký được, trong khi một lỗi NAT ở advertised endpoint có thể khiến registration thành công nhưng mọi request đều timeout.

Bài học này thuộc module SPRING_CLOUD_SERVICE_DISCOVERY, tập trung vào chẩn đoán Eureka, Consul, ZooKeeper và Kubernetes từ góc nhìn provider, consumer, registry và health checker. Các bước bên dưới đi từ lớp mạng thấp đến lớp bảo mật và thời gian để khoanh vùng nguyên nhân bằng bằng chứng.

## 1. Nhận diện triệu chứng trước khi thay đổi cấu hình

Không nên bắt đầu bằng việc đổi hostname, tắt TLS hoặc mở firewall rộng. Trước tiên, phân loại lỗi theo biểu hiện quan sát được:

| Triệu chứng | Lớp cần kiểm tra đầu tiên | Dấu hiệu thường gặp |
|---|---|---|
| Provider không kết nối được registry | DNS, route, TCP | `UnknownHostException`, timeout, `Connection refused`. |
| Provider đăng ký được nhưng consumer không gọi được | Advertised host, NAT, port, firewall | Registry có record nhưng request timeout hoặc connection refused. |
| HTTPS không kết nối được | TLS, certificate, SNI, truststore | `SSLHandshakeException`, `PKIX path building failed`, hostname mismatch. |
| Registry trả `401` | Authentication | Thiếu hoặc sai credentials/token. |
| Registry trả `403` | Authorization/ACL/RBAC | Đã đến server nhưng danh tính không có quyền thao tác. |
| Token hoặc certificate đột nhiên không hợp lệ | Đồng bộ thời gian | `not yet valid`, `expired`, JWT `nbf`/`exp`, Kerberos clock skew. |
| Health check fail nhưng request từ provider vẫn chạy | Health checker network path | Agent/kubelet không truy cập được advertised health URL. |
| Lỗi xảy ra theo subnet hoặc zone | DNS view, route, NAT, firewall | Một nhóm consumer gọi được, nhóm khác timeout. |

Một lỗi `UnknownHostException` chưa liên quan đến ACL. Một lỗi `403` thường cho thấy DNS, TCP và HTTP đã đi được đến server; khi đó cần kiểm tra quyền thay vì đổi DNS. Phân biệt lớp lỗi giúp tránh sửa sai thành phần và tạo thêm rủi ro.

## 2. Phân biệt các địa chỉ trong service discovery

Một hệ thống thường có ít nhất ba loại địa chỉ:

1. **Registry endpoint:** địa chỉ provider/consumer dùng để kết nối Eureka, Consul, ZooKeeper hoặc Kubernetes API.
2. **Advertised service endpoint:** hostname/IP và port mà provider đăng ký để consumer gọi.
3. **Health-check endpoint:** địa chỉ và path mà Consul agent, kubelet hoặc hệ thống monitor sử dụng để kiểm tra service.

Ví dụ:

```yaml
spring:
  application:
    name: payment-service
  cloud:
    consul:
      host: consul.internal.example
      port: 8500
      discovery:
        hostname: payment-01.apps.internal.example
        port: 8080
        health-check-path: /actuator/health
```

Trong ví dụ này, `consul.internal.example:8500` là registry endpoint; `payment-01.apps.internal.example:8080` là advertised service endpoint; health checker gọi path `/actuator/health` trên endpoint được đăng ký theo cách Consul integration cấu hình.

Mở firewall đến Consul không tự động cho phép consumer truy cập payment service. Tương tự, provider tự gọi `localhost:8080` thành công không chứng minh consumer ở subnet khác có thể truy cập hostname được công bố.

## 3. Chẩn đoán DNS và tên miền

### 3.1. Kiểm tra từ đúng vị trí mạng

DNS có thể trả kết quả khác nhau tùy private zone, search domain, resolver, VPN hoặc namespace. Hãy chạy kiểm tra từ chính provider, consumer và health checker.

Linux:

```bash
getent hosts consul.internal.example
getent ahosts payment-01.apps.internal.example
nslookup payment-01.apps.internal.example
dig payment-01.apps.internal.example A
dig payment-01.apps.internal.example AAAA
```

Windows PowerShell:

```powershell
Resolve-DnsName consul.internal.example
Resolve-DnsName payment-01.apps.internal.example
Test-NetConnection payment-01.apps.internal.example -Port 8080
```

Đối chiếu A record, AAAA record và địa chỉ mà ứng dụng thực sự chọn. Nếu DNS trả cả IPv4 và IPv6 nhưng chỉ một đường có route, client có thể gặp lỗi không ổn định tùy thứ tự lựa chọn địa chỉ và cơ chế fallback.

### 3.2. Private DNS và split-horizon DNS

Split-horizon DNS trả các câu trả lời khác nhau tùy mạng truy vấn. Ví dụ:

- Provider trong VPC A phân giải `payment.internal.example` thành IP private của subnet A.
- Consumer trong VPC B nhận cùng tên nhưng được trả IP cũ hoặc IP chỉ route được từ VPC A.
- Laptop qua VPN dùng resolver public thay vì private DNS zone.
- Container dùng DNS resolver khác với host.

Cách xử lý:

- Xác định resolver mà tiến trình thực sự sử dụng.
- Kiểm tra private hosted zone đã liên kết với đúng VPC/network chưa.
- Kiểm tra DNS forwarding giữa các VPC, subnet hoặc cluster.
- Dùng FQDN rõ namespace/domain thay vì dựa vào search suffix không ổn định.
- Bảo đảm mọi consumer cần gọi instance đều nhận được một địa chỉ có thể định tuyến.

Không sửa lỗi split-horizon bằng cách ghi cứng IP vào source code. IP có thể đổi khi rollout, failover hoặc thay đổi subnet.

### 3.3. DNS cache và bản ghi cũ

Ngay cả khi DNS server đã cập nhật record, JVM, OS resolver, sidecar proxy hoặc HTTP client có thể vẫn giữ kết quả cũ. Thời gian cache phụ thuộc TTL, runtime và cấu hình cụ thể.

Kiểm tra:

- TTL của record trên DNS server.
- Cache DNS trong OS/container runtime.
- Chính sách cache DNS của JVM đang dùng.
- DNS cache của proxy/service mesh và HTTP client.
- Connection pool đang giữ TCP connection đến địa chỉ cũ.

Không giả định thay đổi DNS sẽ lập tức đóng các kết nối đang tồn tại. Khi cần kiểm thử, tạo request mới sau khi cache hết hạn hoặc khởi tạo client mới để tách vấn đề DNS khỏi connection reuse.

### 3.4. Kiểm tra tên service trong Kubernetes

Trong Kubernetes, Service thường được phân giải theo dạng:

```text
service-name.namespace.svc.cluster-domain
```

Ví dụ `payment-service.commerce.svc.cluster.local`. `cluster.local` là domain thường gặp, nhưng cluster có thể dùng domain khác. Pod trong namespace khác nên dùng tên có namespace/FQDN để tránh search path phân giải nhầm.

Lệnh kiểm tra:

```bash
kubectl get svc payment-service -n commerce
kubectl get endpoints payment-service -n commerce
kubectl get endpointslices -n commerce -l kubernetes.io/service-name=payment-service
```

Nếu DNS phân giải được ClusterIP nhưng request timeout, kiểm tra Service port, targetPort, endpoint readiness, CNI và NetworkPolicy. DNS thành công chỉ chứng minh tên đã được phân giải, không chứng minh backend nhận được traffic.

## 4. NAT, routing và địa chỉ được công bố

### 4.1. Bind address khác advertised address

Một server có thể bind trên `0.0.0.0:8080` nhưng cần công bố hostname/IP riêng để consumer kết nối. `0.0.0.0` là địa chỉ wildcard dùng khi listen; không phải địa chỉ đích hợp lệ để đăng ký cho consumer. `127.0.0.1` và `localhost` chỉ trỏ về chính network namespace đang gọi.

Ví dụ lỗi:

```yaml
eureka:
  instance:
    hostname: localhost
```

Provider có thể đăng ký thành công, nhưng consumer nhận `localhost` và kết nối vào chính máy consumer. Cấu hình đúng phải công bố DNS name hoặc IP mà mọi consumer được phép truy cập.

### 4.2. Hiểu đường đi qua NAT

Một request qua NAT có thể đi qua các bước:

```text
Consumer private IP
    -> route / VPN / peering
    -> NAT hoặc load balancer
    -> provider private/public IP
    -> service port
```

Cần phân biệt:

- **SNAT:** thay đổi source IP của packet.
- **DNAT:** thay đổi destination IP/port.
- **Port mapping:** ánh xạ port bên ngoài vào port container hoặc VM.
- **Hairpin NAT:** client trong mạng nội bộ truy cập địa chỉ public rồi quay lại backend nội bộ.
- **Asymmetric routing:** chiều đi và chiều về qua các route/firewall khác nhau.

Một địa chỉ public có thể truy cập được từ Internet nhưng không truy cập được từ subnet nội bộ nếu hairpin NAT không được hỗ trợ. Ngược lại, private IP trong registry có thể truy cập được từ cùng VPC nhưng không thể truy cập từ consumer ở VPC khác nếu thiếu peering/VPN/route.

### 4.3. Kiểm tra port và listener

Linux:

```bash
ss -lntp
ip route get 10.20.5.21
nc -vz payment-01.apps.internal.example 8080
```

Windows:

```powershell
Get-NetTCPConnection -State Listen
Test-NetConnection payment-01.apps.internal.example -Port 8080
```

Kiểm tra trên provider xem process có listen đúng interface và port không. Nếu chỉ bind `127.0.0.1`, request từ máy khác không thể vào dù firewall đã mở. Nếu container listen port `8080` nhưng host publish port `18080`, registry phải công bố endpoint mà consumer thực sự sử dụng theo network topology.

### 4.4. Xử lý advertised address theo từng registry

| Công nghệ | Registry endpoint | Thông tin instance cần kiểm tra |
|---|---|---|
| Eureka | `eureka.client.service-url.defaultZone` | `eureka.instance.hostname`, `ip-address`, `prefer-ip-address`, port. |
| Consul | `spring.cloud.consul.host` và `port` | `spring.cloud.consul.discovery.hostname`, `ip-address`, `port`, `prefer-ip-address`. |
| ZooKeeper | `spring.cloud.zookeeper.connect-string` | `spring.cloud.zookeeper.discovery.instance-host`, `instance-port`, `prefer-ip-address`. |
| Kubernetes | Kubernetes API endpoint | Service DNS/ClusterIP, Pod IP, port và namespace theo request path. |

Ví dụ Eureka công bố IP có thể truy cập từ consumer:

```yaml
eureka:
  client:
    service-url:
      defaultZone: https://eureka.internal.example:8761/eureka/
  instance:
    prefer-ip-address: true
    ip-address: 10.20.5.21
    non-secure-port: 8080
```

Ví dụ Consul công bố hostname:

```yaml
spring:
  cloud:
    consul:
      host: consul.internal.example
      port: 8500
      discovery:
        hostname: payment-01.apps.internal.example
        prefer-ip-address: false
        port: 8080
```

Tên thuộc tính và hành vi ưu tiên host/IP cần được xác nhận theo phiên bản Spring Cloud đang dùng. Sau khi cấu hình, đọc lại bản ghi trong registry và `ServiceInstance` ở consumer. Không chỉ kiểm tra biến môi trường của provider.

### 4.5. Dấu hiệu lỗi NAT và routing

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Registry có record nhưng TCP timeout | Advertised private IP không route được từ consumer. | Route table, VPN/peering, firewall, flow logs. |
| Provider gọi localhost được nhưng consumer không gọi được | App chỉ bind loopback hoặc advertise loopback. | `ss -lntp`, `getHost()`, `getUri()`. |
| Kết nối được trong cùng subnet nhưng fail giữa VPC | Thiếu route/peering hoặc security group. | Route hai chiều, SG/NACL, NAT. |
| Kết nối public được nhưng nội bộ timeout | Hairpin NAT hoặc split DNS không đúng. | So sánh DNS nội bộ và public, thử private endpoint. |
| Một chiều kết nối được, response timeout | Asymmetric routing hoặc NACL chặn ephemeral return port. | Flow logs, firewall state, route chiều về. |
| Container port đúng nhưng host port sai | Docker/Kubernetes port mapping nhầm. | Container port, Service port, targetPort, published port. |

## 5. TLS, certificate, SNI và mTLS

### 5.1. Phân biệt lỗi TLS với lỗi mạng

TLS chỉ bắt đầu sau khi TCP connection được thiết lập. Vì vậy, thứ tự chẩn đoán là:

1. DNS có phân giải đúng không?
2. TCP có kết nối đến đúng IP/port không?
3. Server có trả TLS handshake không?
4. Client có tin cậy certificate chain không?
5. Certificate có hợp lệ với hostname và thời gian hiện tại không?
6. Nếu dùng mTLS, server có xác minh được client certificate không?

Các lỗi thường gặp:

- `PKIX path building failed`: client không xây dựng được trust chain đến CA tin cậy.
- `No subject alternative DNS name matching ...`: hostname không khớp SAN trong certificate.
- `certificate has expired` hoặc `not yet valid`: thời hạn certificate không hợp lệ theo clock của client.
- `handshake_failure` hoặc `bad_certificate`: có thể sai protocol/cipher, thiếu client certificate hoặc server từ chối certificate.
- Kết nối đến IP thay vì hostname làm SNI hoặc SAN không khớp.

### 5.2. SAN và SNI

Certificate cần chứa Subject Alternative Name phù hợp với tên client sử dụng. Nếu consumer kết nối `https://payment.internal.example:8443`, certificate phải có DNS SAN `payment.internal.example`. Nếu kết nối bằng IP literal, certificate cần IP SAN tương ứng.

SNI cho phép client gửi hostname dự định truy cập trong TLS handshake để reverse proxy/server chọn đúng certificate. Nếu gọi bằng IP hoặc proxy thay đổi hostname, server có thể trả certificate mặc định không khớp.

Kiểm tra:

```bash
openssl s_client \
  -connect payment.internal.example:8443 \
  -servername payment.internal.example \
  -showcerts
```

Kiểm tra HTTP với CA được cấp:

```bash
curl --verbose \
  --cacert /etc/ssl/certs/internal-ca.pem \
  https://payment.internal.example:8443/actuator/health
```

Không dùng `curl -k` hoặc tắt hostname verification làm cách sửa production. Những tùy chọn đó bỏ qua kiểm tra danh tính server và có thể che lỗi certificate thực.

### 5.3. Truststore và keystore

| Thành phần | Chứa gì | Dùng để |
|---|---|---|
| Truststore | CA hoặc certificate mà client tin cậy. | Xác minh certificate của registry/provider. |
| Keystore | Private key và certificate của chính ứng dụng. | Cung cấp danh tính server hoặc client trong mTLS. |

Trong mTLS, client cần keystore chứa certificate/private key của client; đồng thời cần truststore để xác minh server. Chỉ cấu hình truststore không làm client có danh tính để server xác thực.

Kiểm tra nội dung keystore/truststore:

```bash
keytool -list -v -keystore client-truststore.p12
keytool -list -v -keystore payment-client-keystore.p12
```

Không in hoặc chia sẻ private key, password keystore hay secret trong log. Dùng secret manager hoặc secret volume có quyền đọc tối thiểu.

### 5.4. Kiểm tra certificate chain và thời hạn

Dùng OpenSSL:

```bash
openssl s_client \
  -connect eureka.internal.example:8761 \
  -servername eureka.internal.example \
  -verify_return_error
```

Kiểm tra certificate đã lưu:

```bash
openssl x509 -in server.crt -noout -subject -issuer -dates -ext subjectAltName
```

Đối chiếu:

- Issuer có nằm trong CA mà client tin cậy không?
- Certificate còn hiệu lực không?
- SAN có đúng hostname/IP advertised không?
- Intermediate CA có được server gửi đủ không?
- Proxy/load balancer có đang terminate TLS và dùng certificate khác không?
- Đồng hồ client/server có lệch khiến certificate bị coi là chưa có hiệu lực hoặc hết hạn không?

### 5.5. Debug TLS trong Java

Khi cần xác định lỗi handshake, có thể bật debug tạm thời trong môi trường test:

```text
-Djavax.net.debug=ssl,handshake,trustmanager
```

Log có thể rất lớn và chứa thông tin về certificate/connection. Chỉ bật trong thời gian chẩn đoán, giới hạn quyền đọc log và tắt sau khi hoàn tất. Không bật rộng trên production traffic nếu chưa đánh giá tác động.

## 6. Xác thực và phân quyền registry

Kết nối đến được registry chưa có nghĩa client có quyền thao tác. Phân biệt authentication (xác minh danh tính) và authorization (kiểm tra quyền).

### 6.1. Nhận diện mã lỗi

| Kết quả | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| DNS lookup failure | Không tìm được địa chỉ server. | DNS zone, resolver, hostname. |
| TCP timeout | Không thiết lập được kết nối hoặc response bị chặn. | Route, firewall, NAT, listener. |
| Connection refused | Đến được host nhưng port không có listener hoặc bị reject. | Service status, bind address, port mapping. |
| TLS handshake failure | TCP đã kết nối nhưng xác minh/mã hóa thất bại. | CA, SAN, SNI, protocol, mTLS, clock. |
| HTTP 401 | Thiếu/sai credentials hoặc token. | Username/password, token, secret rotation. |
| HTTP 403 | Danh tính đã được nhận diện nhưng không đủ quyền. | Role, ACL policy, RBAC, HTTP method. |
| HTTP 404 | Sai path/service ID hoặc resource không tồn tại. | Context path, API version, service name. |

Một số server có thể trả `404` thay cho `403` để che giấu resource; cần đọc log server và cấu hình security thay vì suy luận chỉ từ status code.

### 6.2. Eureka

Eureka Server có thể được bảo vệ bằng Spring Security. Eureka Client cần credentials hợp lệ nếu server bật HTTP Basic hoặc cơ chế xác thực khác. Kiểm tra URL trong `eureka.client.service-url.defaultZone`, scheme, context path và secret được inject.

Ví dụ cấu hình không ghi credential trực tiếp:

```yaml
eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_SERVER_URL}
```

Secret `EUREKA_SERVER_URL` được cung cấp từ secret manager hoặc biến môi trường runtime. Tránh commit URL có user-info vào Git hoặc ghi URL đầy đủ vào log.

Khi bật Spring Security, kiểm tra CSRF matcher cho các HTTP method mà Eureka Client dùng để register/renew/deregister. Không tắt CSRF toàn ứng dụng chỉ để client đăng ký được; chỉ cấu hình ngoại lệ hẹp cho API path cần thiết theo security design.

### 6.3. Consul ACL

Consul dùng ACL token và policy để giới hạn service registration, catalog read, health query hoặc thao tác agent. Các token nên tách theo vai trò:

- Provider: chỉ quyền đăng ký/cập nhật service mà nó sở hữu và quyền cần thiết cho health/agent integration.
- Consumer: chỉ quyền đọc catalog/health của service được phép tìm.
- Monitoring: chỉ quyền truy vấn metrics/status cần thiết.
- Operator: quyền quản trị theo quy trình riêng.

Kiểm tra token qua secret store và quyền policy. `401` có thể cho biết token không được cung cấp/không hợp lệ; `403` thường cho biết token hợp lệ nhưng thiếu policy. Cách phản hồi cụ thể phụ thuộc endpoint và cấu hình ACL.

Không dùng management token cho mọi provider/consumer. Khi rotate token, cập nhật secret và xác nhận client đã tải credential mới trước khi thu hồi token cũ theo quy trình.

### 6.4. ZooKeeper authentication và ACL

ZooKeeper phân biệt authentication scheme với ACL trên znode. Client có thể kết nối được ensemble nhưng vẫn nhận `NoAuth` khi đọc/ghi path đăng ký.

Kiểm tra:

- Client có dùng đúng SASL/digest/x509 identity không?
- Identity có quyền `CREATE`, `READ`, `WRITE`, `DELETE` hoặc `ADMIN` phù hợp không?
- Root path và node con có ACL đúng không?
- Provider có quyền tạo ephemeral znode và consumer có quyền đọc payload không?
- Chroot/root path có khớp giữa provider và consumer không?

Không dùng ACL mở quyền ghi cho `world:anyone` trong production. Việc đổi ACL cần tính đến node đã tồn tại, vì cập nhật cấu hình client không nhất thiết sửa ACL của các znode cũ.

### 6.5. Kubernetes RBAC và ServiceAccount

Spring Cloud Kubernetes DiscoveryClient gọi Kubernetes API bằng danh tính workload, thường là ServiceAccount. Lỗi `Forbidden` thường liên quan Role/ClusterRole hoặc namespace scope.

Kiểm tra danh tính và quyền:

```bash
kubectl auth can-i list services \
  --as=system:serviceaccount:commerce:payment-consumer \
  -n commerce

kubectl auth can-i watch endpointslices.discovery.k8s.io \
  --as=system:serviceaccount:commerce:payment-consumer \
  -n commerce
```

Resource và verb chính xác phụ thuộc phiên bản Spring Cloud Kubernetes và implementation đang dùng. Cấp quyền tối thiểu trên namespace cần thiết; không gán `cluster-admin` cho service account chỉ để khắc phục discovery.

## 7. Đồng bộ thời gian và clock skew

### 7.1. Phân biệt timezone với clock skew

Timezone chỉ ảnh hưởng cách hiển thị thời gian. Hai máy có thể dùng timezone khác nhau nhưng cùng một thời điểm UTC. Clock skew là đồng hồ thực tế giữa các máy lệch nhau.

Ví dụ log một máy hiển thị 10:00 UTC+7 và máy khác 03:00 UTC; chúng có thể hoàn toàn đồng bộ. Nhưng nếu cả hai cùng hiển thị UTC mà lệch vài phút, cần điều tra NTP/time synchronization.

Dùng UTC trong log và telemetry giúp đối chiếu sự kiện giữa provider, registry và consumer. Không đổi timezone để sửa clock skew.

### 7.2. Tác động của clock skew

Clock lệch có thể gây ra:

- TLS certificate bị coi là `not yet valid` hoặc `expired`.
- JWT/OAuth token bị từ chối do `nbf` (not before) hoặc `exp` (expiration).
- Kerberos authentication thất bại vì vượt quá clock skew được phép.
- Log giữa provider, registry và consumer không khớp thứ tự thời gian, gây khó điều tra.
- Scheduler, retry/backoff hoặc job theo thời điểm chạy sớm/muộn ngoài dự kiến.
- Các thao tác phụ thuộc timestamp hoặc lease ở nhiều node khó quan sát và phân tích.

Không nên mặc định mọi lỗi heartbeat/lease đều do clock skew. Nhiều registry đo timeout bằng timer/clock nội bộ của server hoặc session. Hãy xem clock là một yếu tố cần kiểm tra, đồng thời xác minh network, heartbeat, lease và session theo cơ chế riêng của registry.

### 7.3. Kiểm tra thời gian trên Linux

```bash
date -u
timedatectl status
chronyc tracking
chronyc sources -v
```

`timedatectl` cho biết đồng hồ hệ thống và trạng thái đồng bộ. `chronyc tracking` hiển thị offset và trạng thái nguồn thời gian nếu máy dùng Chrony.

Nếu dùng NTP service khác, kiểm tra service đang hoạt động và nguồn time server được cấu hình. Không chạy nhiều dịch vụ NTP cạnh tranh trên cùng máy.

### 7.4. Kiểm tra thời gian trên Windows

```powershell
([DateTime]::UtcNow).ToString("o")
w32tm /query /status
w32tm /query /source
w32tm /stripchart /computer:ntp.internal.example /samples:5 /dataonly
```

Trong domain Windows, nguồn thời gian thường cần theo hierarchy của domain controller. Dùng nguồn NTP theo chính sách tổ chức thay vì tự ý đổi sang một server Internet không được phê duyệt.

### 7.5. Đồng bộ thời gian trong container và Kubernetes

Container thường dùng clock của kernel host; thay đổi timezone trong container không sửa clock của host. Nếu nhiều Pod trên một node có cùng sai lệch, kiểm tra node trước. Nếu chỉ một node lệch, so sánh NTP source và offset của node đó.

Với cluster nhiều node, bảo đảm tất cả control plane, worker, registry server, VM và hệ thống identity dùng nguồn thời gian tin cậy. Theo dõi offset và cảnh báo khi vượt ngưỡng vận hành của TLS/token/Kerberos.

Không chỉnh lùi/tiến đồng hồ thủ công trên node đang chạy workload nếu chưa đánh giá tác động. Thay đổi thời gian đột ngột có thể ảnh hưởng log, scheduler và ứng dụng phụ thuộc wall-clock.

## 8. Cấu hình minh họa cho các nhóm lỗi thường gặp

### 8.1. Eureka: registry URL và advertised IP

```yaml
eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_SERVER_URL}
  instance:
    prefer-ip-address: true
    ip-address: ${SERVICE_ADVERTISE_IP}
    non-secure-port: 8080
```

`EUREKA_SERVER_URL` trỏ đến registry. `SERVICE_ADVERTISE_IP` phải là IP mà consumer thực sự route được. Nếu dùng HTTPS hoặc secure port, cấu hình scheme/port và certificate tương ứng. Không chọn IP interface chỉ tồn tại trong subnet provider.

### 8.2. Consul: tách registry endpoint và instance endpoint

```yaml
spring:
  cloud:
    consul:
      host: ${CONSUL_HOST}
      port: 8501
      scheme: https
      discovery:
        hostname: ${SERVICE_ADVERTISE_HOST}
        port: 8080
        prefer-ip-address: false
```

Ví dụ giả định Consul API được cấu hình HTTPS trên port `8501`. Provider phải tin cậy CA của Consul và có ACL token nếu ACL bật. `SERVICE_ADVERTISE_HOST` là hostname mà consumer gọi; không dùng hostname chỉ phân giải được từ Consul agent nếu consumer nằm ở network khác.

### 8.3. ZooKeeper: tách ensemble và instance address

```yaml
spring:
  cloud:
    zookeeper:
      connect-string: ${ZOOKEEPER_CONNECT_STRING}
      discovery:
        root: /services/production
        instance-host: ${SERVICE_ADVERTISE_HOST}
        instance-port: 8080
```

`ZOOKEEPER_CONNECT_STRING` là client endpoint của ensemble. `instance-host` và `instance-port` là thông tin được công bố cho consumer. Nếu bật TLS/SASL/ACL, cấu hình identity và trust phù hợp với cluster; kết nối TCP đến `2181` không chứng minh quyền znode hợp lệ.

## 9. Quy trình chẩn đoán theo từng lớp

Khi consumer không gọi được service, thực hiện theo thứ tự sau và ghi lại kết quả ở mỗi bước:

1. **Lấy dữ liệu registry:** service ID, instance ID, hostname/IP, port, scheme, status và metadata.
2. **Xác định nguồn kiểm tra:** provider, consumer, health checker hoặc registry node. Không dùng laptop quản trị làm đại diện cho tất cả.
3. **Kiểm tra DNS:** phân giải registry hostname và advertised hostname từ đúng nguồn.
4. **Kiểm tra route:** xác nhận route đến IP đích, NAT/peering/VPN và chiều phản hồi.
5. **Kiểm tra listener/TCP:** kiểm tra bind address, port, security group, firewall và NetworkPolicy.
6. **Kiểm tra TLS:** SNI, SAN, CA chain, thời hạn certificate, truststore/keystore và mTLS.
7. **Kiểm tra authentication:** username/password, ACL token, SASL identity hoặc ServiceAccount token.
8. **Kiểm tra authorization:** role, policy, ACL và RBAC cho đúng API/resource/method.
9. **Kiểm tra clock:** UTC, NTP source, offset, certificate validity và token time claims.
10. **Kiểm tra lại từ consumer:** gọi endpoint qua `ServiceInstance.getUri()` hoặc LoadBalancer và đối chiếu log provider.

### 9.1. Lệnh kiểm tra nhanh theo thứ tự

Linux:

```bash
# DNS
getent hosts eureka.internal.example
getent hosts payment-01.apps.internal.example

# Route và listener
ip route get 10.20.5.21
ss -lntp

# TCP
nc -vz eureka.internal.example 8761
nc -vz payment-01.apps.internal.example 8080

# TLS
openssl s_client -connect eureka.internal.example:8761 \
  -servername eureka.internal.example -verify_return_error

# Thời gian
date -u
timedatectl status
chronyc tracking
```

Windows:

```powershell
Resolve-DnsName eureka.internal.example
Resolve-DnsName payment-01.apps.internal.example
Test-NetConnection eureka.internal.example -Port 8761
Test-NetConnection payment-01.apps.internal.example -Port 8080
([DateTime]::UtcNow).ToString("o")
w32tm /query /status
```

Các lệnh chỉ là điểm bắt đầu. `nc`/`Test-NetConnection` xác nhận TCP, không xác nhận TLS hoặc quyền API. `openssl s_client` kiểm tra handshake và certificate nhưng không chứng minh authorization ở tầng HTTP. Hãy dùng nhiều lớp kiểm tra theo đúng trình tự.

## 10. Ma trận triệu chứng và nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Bằng chứng cần thu thập | Hướng xử lý |
|---|---|---|---|
| `UnknownHostException` khi provider khởi động | Registry hostname sai hoặc private DNS không được liên kết. | Resolver, A/AAAA record, search domain. | Sửa DNS view/forwarding và kiểm tra từ provider. |
| Consumer nhận host không đúng subnet | Registry lưu advertised IP/hostname sai. | Record native và `ServiceInstance.getHost()`. | Cấu hình lại advertised address theo network consumer. |
| TCP timeout qua VPC | Route, peering, NAT, SG/NACL hoặc firewall. | Route table, flow log, source/destination IP. | Sửa đường đi và chiều về; giới hạn rule theo nguồn/port. |
| TCP connection refused | Không có listener hoặc port mapping sai. | `ss -lntp`, container port, Service targetPort. | Sửa bind address, port hoặc mapping. |
| TLS `PKIX path building failed` | Thiếu CA/intermediate hoặc truststore sai. | Issuer chain, truststore contents. | Cập nhật CA chain/truststore đúng. |
| TLS hostname mismatch | SAN không chứa advertised hostname/IP hoặc SNI sai. | Certificate SAN và hostname request. | Dùng hostname phù hợp hoặc cấp lại certificate. |
| TLS `not yet valid`/`expired` bất thường | Certificate date hoặc clock skew. | Certificate dates, UTC, NTP offset. | Sửa clock sync hoặc cấp lại certificate nếu thực sự hết hạn. |
| Registry trả `401` | Credentials/token thiếu hoặc sai. | Auth config, secret version, server auth log. | Cập nhật secret đúng và rotate an toàn. |
| Registry trả `403`/ZooKeeper `NoAuth` | Danh tính hợp lệ nhưng thiếu ACL/RBAC. | Policy, role, znode ACL, Kubernetes `can-i`. | Cấp quyền tối thiểu cho resource/action cần thiết. |
| JWT bị `nbf` hoặc `exp` | Clock lệch hoặc token hết hạn. | Claims, issuer clock, client clock. | Đồng bộ NTP và cấp token mới. |
| Consul health check critical | Agent không truy cập endpoint hoặc check TLS/auth fail. | Agent log, health URL, source IP, check output. | Sửa route/advertised host/credential/check config. |
| Eureka registration lặp lỗi renew | Registry URL, auth, TLS hoặc mạng không ổn định. | Client log, renew response, server log. | Khoanh vùng DNS/TCP/TLS/auth trước khi chỉnh lease. |
| ZooKeeper session mất liên tục | Network flap, session timeout, ensemble endpoint hoặc TLS/SASL. | Curator connection state, server log, network metrics. | Sửa mạng/session config và xác thực. |

## 11. Những cách sửa dễ gây rủi ro

Tránh các biện pháp sau như cách khắc phục lâu dài:

- Tắt certificate verification hoặc dùng `curl -k` trong production.
- Công bố `localhost`, loopback hoặc `0.0.0.0` làm endpoint của instance.
- Mở toàn bộ CIDR hoặc mọi port để “thử xem có hết lỗi không”.
- Cấp Consul management token hoặc Kubernetes `cluster-admin` cho tất cả service.
- Tắt ZooKeeper ACL hoặc cho `world:anyone` quyền ghi.
- Đưa password, ACL token, private key hoặc URL có credentials vào Git/log.
- Tăng lease/session timeout khi chưa chứng minh lỗi đến từ timeout.
- Thay IP bằng một địa chỉ public mà không kiểm tra route nội bộ và hairpin NAT.
- Chỉnh đồng hồ thủ công trên node production mà không có quy trình time synchronization.
- Chỉ kiểm tra từ provider localhost rồi kết luận consumer có thể truy cập.

Mọi thay đổi nên giới hạn theo đúng nguồn, đích, danh tính và port cần thiết. Sau khi sửa, kiểm tra lại cả registration, health check và request nghiệp vụ.

## 12. Runbook xử lý sự cố production

Khi có cảnh báo service discovery, người xử lý có thể đi theo runbook sau:

**Bước 1 — Ghi nhận dữ liệu**

- Thời điểm xảy ra theo UTC.
- Provider, consumer, registry node và zone/subnet liên quan.
- Service ID, instance ID, advertised hostname/IP, port và scheme.
- Mã lỗi, exception chain và correlation ID.
- Thay đổi gần nhất về DNS, NAT, certificate, ACL/RBAC hoặc NTP.

**Bước 2 — Xác định phạm vi**

- Một instance hay tất cả instance?
- Một consumer subnet hay mọi consumer?
- Chỉ provider → registry hay cả consumer → provider?
- Health checker có cùng lỗi với consumer không?
- Chỉ HTTPS lỗi hay HTTP cũng lỗi?

**Bước 3 — Kiểm tra từ đúng nguồn**

- DNS lookup từ provider, consumer và checker.
- TCP connect đến registry và advertised endpoint.
- TLS handshake với đúng SNI.
- Authentication/authorization bằng credential của đúng workload.
- Clock offset trên các node liên quan.

**Bước 4 — Sửa có kiểm soát**

- Sửa record/advertised address hoặc route nếu sai.
- Cập nhật CA/certificate/truststore nếu TLS sai.
- Rotate credential hoặc điều chỉnh policy tối thiểu nếu auth fail.
- Khôi phục NTP nếu clock drift.
- Không đồng thời thay nhiều lớp nếu chưa xác định nguyên nhân.

**Bước 5 — Xác minh phục hồi**

- Provider register/renew thành công.
- Registry lưu đúng host, port, status.
- Health checker nhận passing/ready.
- Consumer `DiscoveryClient` nhìn thấy instance.
- Request thực tế qua LoadBalancer hoặc URI instance thành công.
- Metrics và log không còn lỗi lặp lại.

## 13. Checklist phòng ngừa

- Registry hostname và advertised service hostname được quản lý bằng private DNS có chủ đích.
- DNS trả A/AAAA phù hợp với route của từng nhóm consumer.
- DNS TTL và cache policy được hiểu rõ khi rollout hoặc failover.
- Provider bind đúng interface và công bố địa chỉ consumer truy cập được.
- NAT/port mapping, route chiều đi và chiều về được kiểm tra.
- Registry endpoint và service endpoint có firewall rule riêng.
- Certificate có SAN đúng hostname/IP; CA chain và SNI được xác minh.
- Truststore và keystore được quản lý riêng; private key không nằm trong source code.
- mTLS client identity được cấp và rotate có kiểm soát.
- Eureka credentials, Consul ACL token, ZooKeeper identity và Kubernetes ServiceAccount có quyền tối thiểu.
- Secret rotation có overlap và xác nhận client đã nhận secret mới trước khi thu hồi cũ.
- Các node, container host, registry và identity provider đồng bộ NTP.
- Log dùng UTC và có correlation ID để so sánh giữa các thành phần.
- Monitoring cảnh báo DNS failure, connection timeout, TLS handshake, auth denial và clock offset.
- Có runbook kiểm tra từ provider, consumer và health checker.

## Kết luận

Lỗi service discovery thường là kết quả của nhiều lớp phụ thuộc. DNS quyết định tên miền trỏ đến đâu; NAT và routing quyết định consumer có đến được advertised endpoint không; TLS xác minh danh tính và mã hóa kết nối; authentication/authorization quyết định client có quyền thao tác registry; đồng bộ thời gian bảo đảm certificate, token và log được diễn giải đúng.

Hãy phân biệt registry endpoint với advertised service endpoint, kiểm tra từ đúng network vantage point và đi theo thứ tự DNS → route/TCP → TLS → authentication → authorization → time. Sau khi sửa, xác minh lại cả registration, health status và request data-plane. Cách làm theo bằng chứng này giúp xử lý đúng nguyên nhân mà không phải nới lỏng bảo mật hoặc mở rộng mạng ngoài nhu cầu.

## Tài liệu tham khảo

- Spring Cloud Netflix — Eureka Client: https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html
- Spring Cloud Consul — Service Discovery: https://docs.spring.io/spring-cloud-consul/reference/discovery.html
- Spring Cloud Zookeeper — Service Discovery: https://docs.spring.io/spring-cloud-zookeeper/reference/discovery.html
- Kubernetes — DNS for Services and Pods: https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/
- Kubernetes — RBAC: https://kubernetes.io/docs/reference/access-authn-authz/rbac/
- OpenSSL — s_client: https://docs.openssl.org/3.0/man1/openssl-s_client/
- Chrony — chronyc: https://chrony-project.org/doc/4.5/chronyc.html
