# Kết nối qua proxy và môi trường bị giới hạn mạng

## 1. Vì sao Kubernetes client gặp khó trong mạng doanh nghiệp?

Ứng dụng Spring Cloud Kubernetes có thể cần gọi Kubernetes API để discovery, đọc ConfigMap hoặc Secret, theo dõi thay đổi và lấy metadata Pod. Trong mạng doanh nghiệp, đường đi có thể bị chi phối bởi:

- Proxy HTTP/HTTPS bắt buộc cho egress.
- API server nằm trong mạng private hoặc qua load balancer nội bộ.
- DNS split-horizon và zone chỉ phân giải trong một số mạng.
- NetworkPolicy giới hạn egress từ namespace.
- Firewall hoặc security group chặn cổng.
- Proxy TLS interception thay certificate máy chủ.
- Service mesh hoặc sidecar thay đổi đường đi và chứng thư.
- Kubeconfig local trỏ tới endpoint không thể truy cập từ Pod.

Một request tới API server phải đi qua nhiều lớp:

~~~text
Spring Cloud Kubernetes
    |
    v
Kubernetes client configuration
    |
    +-- URL/port
    +-- proxy và NO_PROXY
    +-- DNS và route
    +-- TLS/CA
    +-- token/authentication
    '-- timeout/retry
    |
    v
Kubernetes API server
~~~

Lỗi ở mỗi lớp có biểu hiện khác nhau. Không chữa timeout bằng RBAC, không chữa 403 bằng proxy, và không tắt TLS verification để vượt qua certificate mismatch.

Bài học thuộc phần **Kết nối Kubernetes API** của module **Spring Cloud Kubernetes**. Mục tiêu là thiết kế đường kết nối đáng tin cậy cho DiscoveryClient, ConfigMap, Secret và Configuration Watcher trong môi trường có proxy hoặc giới hạn mạng.

## 2. Proxy làm gì với request API?

Proxy là điểm trung gian giữa client và đích. Client có thể gửi request theo các mô hình:

1. Proxy HTTP nhận request tới một URL HTTP.
2. Proxy HTTPS dùng CONNECT để tạo tunnel tới đích TLS.
3. Proxy chấm dứt TLS, kiểm tra nội dung rồi tạo kết nối TLS khác tới API server.
4. Proxy chuyển tiếp theo policy và yêu cầu authentication riêng.

API server Kubernetes thường được truy cập bằng HTTPS. Với proxy tunnel, client vẫn xác minh certificate của API server sau khi tunnel được thiết lập. Với TLS interception, client có thể nhìn thấy certificate do proxy phát hành thay vì certificate gốc của API server. Khi đó truststore phải tin CA của proxy theo chính sách bảo mật doanh nghiệp.

Sơ đồ hai kiểu:

~~~text
HTTPS proxy tunnel:
Client -- CONNECT --> Proxy ===== TLS tới API server =====> API server

TLS interception:
Client ===== TLS tới Proxy =====> Proxy ===== TLS khác =====> API server
       tin CA proxy                         proxy tin CA server
~~~

Không bật trust-all để xử lý interception. Phải xác định CA đúng, phạm vi truststore và trách nhiệm quản trị certificate. Nếu proxy không được phép intercept traffic tới control plane, dùng tunnel hoặc bypass đúng hostname qua policy thay vì làm suy yếu client.

## 3. Cấu hình proxy trong Kubernetes client

Tên property và cách client đọc proxy phụ thuộc họ client, phiên bản và HTTP transport. Có thể có các nguồn:

- Property riêng của Kubernetes client.
- System property của JVM.
- Biến môi trường chuẩn của proxy.
- Cấu hình kubeconfig.
- Cấu hình của HTTP transport.
- Cấu hình do platform hoặc sidecar inject.

Vì vậy không nên viết một property minh họa thành quy tắc áp dụng cho mọi release. Trước khi triển khai, xác định:

- Client Java thực tế là Fabric8 hay Kubernetes Java Client.
- HTTP transport nào đang được dùng.
- Property nào được bind vào client.
- Proxy áp dụng cho HTTP, HTTPS hay cả hai.
- Proxy cần username/password, certificate hay token không.
- Có hỗ trợ proxy bypass theo hostname hoặc CIDR không.

Ví dụ biến môi trường thường được dùng trong nhiều công cụ:

~~~text
HTTPS_PROXY=http://proxy.example:8080
HTTP_PROXY=http://proxy.example:8080
NO_PROXY=localhost,127.0.0.1,.svc,.cluster.local
~~~

Tên chữ hoa/chữ thường và việc thư viện có đọc biến đó hay không có thể khác nhau. Đặc biệt, NO_PROXY không phải lúc nào được mọi Java HTTP client diễn giải giống nhau. Hãy kiểm thử bằng chính transport của ứng dụng.

Credential proxy không phải credential Kubernetes. Proxy authentication trả lời “client được phép đi qua proxy không”; ServiceAccount token trả lời “client là ai với Kubernetes API”. Không dùng token Kubernetes cho proxy trừ khi hệ thống được thiết kế rõ ràng như vậy.

## 4. NO_PROXY cần được thiết kế cẩn thận

NO_PROXY quyết định đích nào bỏ qua proxy. Cấu hình quá rộng có thể đưa traffic ra ngoài kiểm soát; quá hẹp có thể làm request nội bộ đi qua proxy không phù hợp.

Các nhóm hostname cần xem xét:

- API server hostname nội bộ.
- Tên Service Kubernetes như kubernetes.default.svc.
- Hậu tố .svc và .cluster.local nếu policy cho phép bypass.
- localhost và 127.0.0.1 cho health hoặc sidecar.
- Địa chỉ private của control plane hoặc endpoint nội bộ.
- Hostname của service mesh hoặc metadata endpoint nếu thật sự cần.

Ví dụ minh họa:

~~~text
NO_PROXY=localhost,127.0.0.1,kubernetes.default.svc,.svc,.cluster.local
~~~

Đây không phải giá trị dùng chung cho mọi cluster. Có hệ thống yêu cầu API server đi qua proxy để kiểm soát egress; có hệ thống chỉ cho phép đường private trực tiếp. Quyết định phải dựa trên network policy và thiết kế doanh nghiệp.

Kiểm tra:

- NO_PROXY có chứa hostname mà client thực sự dùng không?
- Client dùng tên DNS hay IP sau khi resolve?
- Parser có hỗ trợ wildcard, leading dot và port không?
- Có cần thêm cả hostname và IP không?
- Sidecar có đọc cùng biến môi trường không?
- Proxy bypass có làm mất lớp giám sát bắt buộc không?

Không suy ra rằng thêm .cluster.local luôn an toàn. Một suffix rộng có thể bypass proxy cho nhiều dịch vụ hơn phạm vi dự kiến.

## 5. API server trong mạng private

Pod có thể không truy cập được API server public nhưng lại truy cập được endpoint private. Kubeconfig hoặc in-cluster detection phải trỏ tới URL reachable từ đúng network namespace.

Cần phân biệt:

| Thành phần | Câu hỏi |
|---|---|
| DNS | Hostname API server phân giải thành địa chỉ nào trong Pod? |
| Route | Node/Pod có route tới địa chỉ đó không? |
| Firewall | Cổng API server có được cho phép không? |
| NetworkPolicy | Namespace có được egress tới control plane không? |
| Proxy | Request cần proxy hay bypass? |
| TLS | Certificate có hợp lệ với hostname được dùng không? |

Nếu dùng IP thay hostname để sửa DNS, certificate có thể không còn khớp. Nếu dùng hostname public trong Pod nhưng policy chỉ cho private route, timeout có thể xảy ra. Nếu dùng hostname private mà CA được cấp cho tên khác, TLS có thể fail.

Một endpoint reachable cần thỏa cả mạng và TLS:

~~~text
DNS đúng
    -> route đúng
    -> cổng mở
    -> proxy path đúng
    -> TLS hostname/CA đúng
    -> credential đúng
    -> RBAC đúng
~~~

Không dừng ở ping. ICMP có thể bị chặn dù HTTPS hoạt động, hoặc ping thành công nhưng cổng API bị firewall chặn. Kiểm tra theo giao thức và cổng mà client thực sự dùng.

## 6. NetworkPolicy và egress

NetworkPolicy có thể chặn Pod gửi kết nối tới API server. Khi đó client có thể báo timeout hoặc connection refused tùy hạ tầng. Một Role đúng không thể mở đường mạng đã bị policy chặn.

Thiết kế egress cần xác định:

- Namespace nào được phép gọi API server?
- Gọi qua Service DNS hay private IP?
- Cổng đích là 443 hay cổng tùy cluster?
- Có cần cho DNS resolver không?
- Proxy nằm ở namespace/địa chỉ nào?
- Sidecar có cần đường riêng tới proxy không?
- Policy có cho phép reconnect watch dài không?

Sơ đồ suy luận:

~~~text
Pod Spring
  |
  +-- DNS resolver được phép?
  |
  +-- API server trực tiếp được phép?
  |       hoặc
  +-- Proxy được phép?
  |
  '-- reconnect/timeout có đi cùng policy không?
~~~

Một policy có thể cho phép mở kết nối đầu tiên nhưng chặn reconnect tới địa chỉ khác sau khi DNS thay đổi. Watch dài cũng có thể bị idle timeout của firewall hoặc proxy.

Khi thay đổi NetworkPolicy, chỉ mở host/port cần thiết. Không cho toàn bộ egress để che một lỗi cấu hình. Cần kiểm thử cả startup, discovery refresh và watch reconnect.

## 7. TLS interception và truststore

Trong môi trường có proxy kiểm tra TLS, client có thể cần trust CA của proxy. Trước khi thêm CA:

1. Xác định proxy có thực sự chấm dứt TLS không.
2. Lấy CA từ kênh quản trị tin cậy.
3. Xác định truststore nào mà JVM hoặc HTTP client sử dụng.
4. Xác định phạm vi ảnh hưởng: chỉ process này hay toàn JVM.
5. Ghi lại vòng đời certificate và quy trình thay mới.
6. Kiểm thử hostname verification vẫn bật.

Không import CA tùy tiện từ một endpoint không xác minh được. Không dùng truststore “tin mọi CA” cho ứng dụng. Truststore quá rộng làm giảm khả năng phát hiện máy chủ giả.

Cần phân biệt:

~~~text
CA của cluster/API server
    -> tin certificate API server

CA của proxy
    -> tin certificate do proxy cấp khi interception

CA của service nghiệp vụ
    -> tin các service khác nếu ứng dụng gọi TLS tới chúng
~~~

Có thể cần nhiều CA, nhưng không nên gộp chúng vào một truststore chung mà không có lý do. Hãy xác định transport nào dùng truststore nào và log tên truststore hoặc alias theo cách không lộ private key.

## 8. Proxy authentication và Secret

Proxy có thể yêu cầu authentication. Credential proxy phải được quản lý như Secret, không viết plaintext trong image hoặc log.

Một mô hình triển khai:

~~~yaml
env:
  - name: HTTPS_PROXY
    value: http://proxy.example:8080
  - name: PROXY_USERNAME
    valueFrom:
      secretKeyRef:
        name: egress-proxy
        key: username
  - name: PROXY_PASSWORD
    valueFrom:
      secretKeyRef:
        name: egress-proxy
        key: password
~~~

Cách truyền credential phụ thuộc client. Một URL proxy chứa username/password có thể bị lộ trong process arguments, exception, dump hoặc log. Hãy dùng cơ chế credential được thư viện hỗ trợ mà không in URL hoàn chỉnh.

Không trộn proxy credential, Kubernetes ServiceAccount token, TLS private key và Secret của ứng dụng nghiệp vụ. Mỗi loại có mục đích, vòng đời và quyền truy cập khác nhau. Nếu Configuration Watcher đọc Secret qua API, watcher cần RBAC; nếu proxy credential được inject trực tiếp, ứng dụng có thể không cần quyền đọc Secret đó qua Kubernetes API.

## 9. Timeout, idle connection và watch

Proxy và firewall thường có idle timeout. Kubernetes client dùng watch có thể giữ kết nối lâu, nên cần xử lý:

- Kết nối watch bị đóng bình thường hoặc do proxy.
- Client reconnect với backoff.
- Resource version cũ không còn phù hợp và cần list lại.
- Nhiều Pod reconnect cùng lúc sau sự cố proxy.
- Connection pool giữ kết nối tới endpoint cũ.
- Request startup không chờ vô hạn.

Bảng tách timeout:

| Loại | Vai trò |
|---|---|
| Connect timeout | Giới hạn thời gian mở socket/proxy tunnel |
| TLS handshake timeout | Giới hạn thương lượng TLS |
| Read timeout | Giới hạn chờ phản hồi |
| Idle timeout | Xử lý kết nối không có dữ liệu quá lâu |
| Watch reconnect backoff | Tránh reconnect dồn dập |
| Overall startup timeout | Giới hạn thời gian ứng dụng chờ dependency từ xa |

Watch không phải đường truyền vĩnh viễn. Integration phải có khả năng nối lại và đồng bộ cache. Khi proxy đóng connection, client không nên làm liveness fail ngay nếu ứng dụng vẫn có thể chạy với cache và chính sách stale data được chấp nhận.

Không đặt retry vô hạn. Với mỗi retry, xác định request là read-only hay write, tác động của lặp request và tải tạo ra trên API server hoặc proxy.

## 10. Chẩn đoán theo lớp

Khi API server không truy cập được, dùng bảng sau:

| Hiện tượng | Lớp kiểm tra trước | Hướng xử lý |
|---|---|---|
| DNS failure | Resolver, search domain, private zone | Xác nhận hostname client đang dùng |
| Connection refused | Route, port, firewall | Kiểm tra endpoint và egress |
| Timeout | NetworkPolicy, proxy, idle timeout | Kiểm tra đường trực tiếp và đường proxy |
| Proxy 407 | Proxy authentication | Kiểm tra credential proxy và cách client bind |
| TLS handshake fail | CA, hostname, interception | Kiểm tra truststore và certificate chain |
| 401 Unauthorized | Kubernetes credential | Kiểm tra token/kubeconfig, không đổi RBAC trước |
| 403 Forbidden | RBAC | Kiểm tra ServiceAccount, Role, namespace, verb |
| 404 Not Found | URL/path/resource version | Kiểm tra client version và API path |
| Watch đóng liên tục | Proxy/firewall/timeout/resource version | Kiểm tra reconnect và resync |
| Discovery rỗng | Namespace, Service, endpoint, filter | Tách mạng khỏi dữ liệu discovery |

Điều tra nên bắt đầu bằng request read-only và hostname thật, không dùng URL khác rồi suy luận. Ghi timestamp, endpoint đã che credential, mã lỗi và thời gian phản hồi.

Một lệnh kết nối tới API server thành công chỉ chứng minh đường mạng, TLS và authentication có thể hoạt động cho request đó. Nó không chứng minh quyền list EndpointSlice hay đọc ConfigMap.

## 11. Local, CI và Pod có đường đi khác nhau

Cùng một ứng dụng có thể có ba topology:

~~~text
Local
  -> kubeconfig -> proxy công ty hoặc VPN -> API server

CI
  -> runner network -> egress proxy/private route -> API server

Pod
  -> ServiceAccount + in-cluster endpoint
  -> NetworkPolicy/service mesh -> API server hoặc proxy
~~~

Không dùng kết quả local để kết luận Pod production. Local có thể dùng VPN, DNS khác, kubeconfig user rộng và proxy đã cài CA. Pod có thể nằm trong namespace bị chặn egress và chỉ có ServiceAccount giới hạn.

Nên có kiểm thử theo môi trường:

- Local: xác nhận property và kubeconfig path.
- CI: xác nhận proxy, truststore và credential job.
- Pod: xác nhận in-cluster endpoint, ServiceAccount, egress và RBAC.
- Sau deploy: xác nhận discovery/config/watch reconnect.

Khi cùng một property được đặt trong file, environment và command-line, cần ghi lại nguồn chính và precedence. Tránh để CI vô tình inject endpoint production vào image dùng cho cluster dev.

## 12. Cấu hình Spring Cloud Kubernetes

Các integration Spring Cloud Kubernetes có thể dùng property cho client, discovery, config hoặc watcher. Tên property phụ thuộc release train, nên hãy đối chiếu metadata dependency và log startup.

Một cấu trúc minh họa:

~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        enabled: true
      config:
        enabled: true
      client:
        # endpoint/proxy/TLS tùy integration và client
~~~

Khi bật proxy, kiểm tra client thực tế có đọc property đó hay phải dùng system property hoặc biến môi trường. Một property bị nhận nhưng không được áp dụng vẫn có thể khiến ứng dụng khởi động mà client đi sai đường.

Tách capability:

- Discovery cần đường tới API server và quyền đọc resource discovery.
- Config cần đường tới API server nếu đọc ConfigMap/Secret bằng API.
- Watcher cần giữ/reconnect watch và có quyền tương ứng.
- Lời gọi Service bằng DNS có thể không cần API server.
- Actuator probe không cần API server chỉ để kubelet gọi endpoint.

Không thêm proxy vào toàn bộ HTTP client của ứng dụng nếu chỉ Kubernetes API cần proxy. Proxy nghiệp vụ và proxy control plane có thể có policy khác nhau.

## 13. Các nhầm lẫn thường gặp

### “Có proxy là mọi request phải đi qua proxy”

API server private có thể cần bypass proxy; service nội bộ có thể cần bypass khác. Quyết định bằng route và policy, không bằng một biến môi trường copy từ máy developer.

### “NO_PROXY càng dài càng tốt”

Danh sách quá rộng có thể bypass kiểm soát egress cho nhiều hostname. Chỉ thêm phạm vi cần thiết và hiểu parser của transport.

### “Tắt verify TLS để sửa lỗi interception”

TLS interception cần CA của proxy hoặc tunnel đúng policy. Trust-all che certificate mismatch và làm yếu bảo mật.

### “Timeout là do thiếu RBAC”

RBAC tạo 403 sau khi request tới được API server. Timeout cần kiểm tra DNS, route, proxy, firewall và idle timeout trước.

### “Proxy credential và Kubernetes token là một”

Proxy xác thực quyền đi qua proxy; token Kubernetes xác định ServiceAccount với API server. Hai credential không thay thế nhau.

### “Watch phải giữ kết nối mãi”

Proxy hoặc firewall có thể đóng connection. Client phải reconnect, resync và dùng backoff.

### “Local gọi được thì Pod cũng gọi được”

Local có VPN, context và quyền khác. Pod có topology, NetworkPolicy, proxy và ServiceAccount riêng.

## 14. Checklist triển khai trong mạng hạn chế

- API server hostname và port được xác định theo đúng network của Pod chưa?
- Pod đi trực tiếp hay qua proxy?
- Proxy có yêu cầu authentication không?
- NO_PROXY có đúng hostname, suffix và parser của client không?
- DNS private zone được resolve trong Pod chưa?
- NetworkPolicy cho egress tới API server, proxy và DNS chưa?
- TLS dùng CA cluster hay CA proxy interception?
- Hostname verification vẫn bật chưa?
- Proxy credential và Kubernetes token được tách riêng chưa?
- Connect/read/idle timeout và watch reconnect đã cấu hình chưa?
- Local, CI và Pod có được kiểm thử theo topology riêng chưa?
- Lỗi DNS, timeout, 407, TLS, 401 và 403 có được phân loại riêng chưa?
- Discovery/config/watcher có thực sự cần đường tới API server không?
- Log và metric có tránh lộ URL credential, token, Secret và kubeconfig không?

Kết nối Kubernetes API trong môi trường giới hạn mạng là bài toán phối hợp giữa client, proxy, DNS, TLS, egress và RBAC. Khi kiểm tra theo từng lớp và giữ rõ đường đi của từng capability Spring Cloud Kubernetes, ứng dụng có thể dùng DiscoveryClient, ConfigMap, Secret hoặc Configuration Watcher mà không biến lỗi mạng thành thay đổi quyền quá rộng hay suy giảm bảo mật.
