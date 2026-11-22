# Không kết nối được đến port gRPC

## 1. Xác định tầng đang thất bại

Trong **SPRING_GRPC**, một client gọi service qua gRPC bằng HTTP/2 và hợp đồng Protocol Buffers. Khi client báo không kết nối được đến port, cần xác định lỗi xảy ra ở DNS, TCP, TLS, HTTP/2 hay chính RPC. Mỗi tầng có dấu hiệu và cách khắc phục khác nhau.

Luồng kết nối:

~~~mermaid
flowchart TD
    A["Client target: host:port"] --> B["DNS / name resolution"]
    B --> C["TCP connection"]
    C --> D["TLS handshake (nếu bật TLS)"]
    D --> E["HTTP/2 + ALPN h2"]
    E --> F["gRPC protocol / service method"]
    F --> G["Application handler"]
    B -->|fail| X["DNS / target error"]
    C -->|refused / timeout| Y["Listener / route / firewall"]
    D -->|fail| Z["Certificate / TLS mode"]
    E -->|fail| H["Proxy / HTTP2 configuration"]
    F -->|status error| I["Authentication / method / application"]
~~~

Không bắt đầu bằng cách sửa service implementation khi TCP chưa thiết lập được. Một lỗi connection refused không được giải quyết bằng cách thay đổi protobuf hoặc logic trong handler.

## 2. Đọc đúng thông báo lỗi

Thông báo từ gRPC thường chứa UNAVAILABLE, nhưng status này chỉ cho biết transport/service hiện không khả dụng; nguyên nhân cụ thể có thể nằm ở DNS, TCP, TLS, proxy hoặc server restart.

| Dấu hiệu | Ý nghĩa thường gặp | Kiểm tra đầu tiên |
|---|---|---|
| Connection refused | Host có thể tới được nhưng port không có listener, hoặc firewall chủ động từ chối | Kiểm tra port và địa chỉ bind trên server |
| Connection timed out | Gói tin không nhận được phản hồi trong thời gian chờ | Route, firewall, network policy, IP/port đích |
| UnknownHostException / DNS lookup failed | Tên host không phân giải được từ môi trường client | DNS, namespace, service name |
| UNAVAILABLE: io exception | Lỗi kết nối hoặc transport; cần đọc nested cause | Tìm ConnectException, timeout, TLS exception |
| SSLHandshakeException | TCP thường đã kết nối nhưng TLS handshake thất bại | Trust chain, SAN, SNI, client certificate |
| ALPN không chọn được h2 | TLS có thể thành công nhưng HTTP/2 negotiation thất bại | TLS terminator, proxy và ALPN |
| UNIMPLEMENTED | Đã tới một gRPC server nhưng method/service không tồn tại hoặc chưa được đăng ký | Package, service name, generated stub, server registration |
| UNAUTHENTICATED / PERMISSION_DENIED | Request đã tới server hoặc security layer và bị từ chối | Credential, token, authorization policy |
| DEADLINE_EXCEEDED | Thời hạn call hết trước khi có kết quả | Kết nối chậm, server chậm, queue hoặc deadline quá ngắn |

Phải đọc cả exception lồng bên trong. Chỉ nhìn StatusRuntimeException: UNAVAILABLE chưa đủ để kết luận port bị đóng.

## 3. Xác nhận target host và port từ phía client

Trước tiên ghi lại target thực tế mà client sử dụng, ví dụ grpc.internal.example:9090. Kiểm tra:

- Hostname có đúng môi trường (local, test, staging, production) không?
- Port có phải port gRPC hay chỉ là port HTTP của Spring Boot không?
- Client có đang chạy trong container hoặc Kubernetes pod với DNS/network riêng không?
- Target có bị override bởi environment variable, profile hoặc service discovery không?
- Client có đang dùng localhost trong khi server ở container/pod khác không?

Trong container, localhost trỏ về chính container đó. Trong Kubernetes, localhost trỏ về pod hiện tại, không tự trỏ đến một service khác. Dùng DNS service name và port mà service công bố.

Ví dụ, ứng dụng có thể phục vụ HTTP actuator trên 8080 và gRPC trên 9090. Gọi localhost:8080 bằng generated gRPC stub sẽ không biến HTTP port thành gRPC port. Kiểm tra log khởi động và cấu hình hiệu lực để biết port nào thực sự được gRPC server mở.

## 4. Kiểm tra DNS từ đúng môi trường chạy client

Tên host phân giải được trên máy developer không chứng minh container hoặc pod cũng phân giải được. Chạy kiểm tra ngay trong môi trường chứa client.

PowerShell:

~~~powershell
Resolve-DnsName grpc.internal.example
~~~

Linux:

~~~bash
getent hosts grpc.internal.example
nslookup grpc.internal.example
~~~

Nếu DNS trả nhiều địa chỉ, kiểm tra từng địa chỉ có route và listener phù hợp. Service discovery có thể trả IP cũ sau khi instance thay đổi; kiểm tra TTL, DNS cache và endpoint registration.

Trong Kubernetes, dùng DNS name đúng namespace, ví dụ orders-grpc.backend.svc.cluster.local. Nếu client và service cùng namespace, tên ngắn orders-grpc thường đủ khi cluster DNS được cấu hình bình thường.

## 5. Xác nhận gRPC server thật sự đang listen

Kiểm tra log startup của ứng dụng. Tìm dòng cho biết gRPC server đã khởi động và port bind thành công. Nếu server không khởi động, xem exception do port conflict, cấu hình sai, TLS certificate không đọc được hoặc bean/service registration lỗi.

Trên Linux:

~~~bash
ss -lntp
ss -lntp | grep ':9090'
~~~

Có thể dùng lsof -nP -iTCP:9090 -sTCP:LISTEN nếu công cụ này được cài đặt.

Trên Windows PowerShell:

~~~powershell
Get-NetTCPConnection -LocalPort 9090 -State Listen
netstat -ano | findstr :9090
~~~

Nếu không có socket ở trạng thái LISTEN, client không thể kết nối đến port đó. Xác định process sở hữu port và xem server có khởi động đúng profile/configuration không.

Nếu port đã được process khác chiếm, server có thể thất bại khi bind hoặc được cấu hình sang port khác. Không chỉ nhìn server.port; HTTP server và gRPC server có thể có cấu hình port riêng.

## 6. Kiểm tra địa chỉ bind

Server bind vào 127.0.0.1 hoặc ::1 chỉ nhận kết nối loopback tương ứng. Client ở máy khác, container khác hoặc pod khác sẽ không thể truy cập qua network interface bên ngoài.

Trong môi trường cần nhận kết nối từ mạng, gRPC server thường phải bind vào interface phù hợp, ví dụ 0.0.0.0 cho IPv4 hoặc địa chỉ interface cụ thể. Chỉ mở rộng bind address khi network policy và firewall đã giới hạn nguồn truy cập đúng cách.

Phân biệt:

- 127.0.0.1:9090: chỉ loopback IPv4.
- [::1]:9090: chỉ loopback IPv6.
- 0.0.0.0:9090: lắng nghe trên mọi interface IPv4.
- [::]:9090: wildcard IPv6; khả năng nhận IPv4 còn tùy cấu hình socket/OS.

Một lỗi hay gặp là server chạy trong container và chỉ bind loopback. Port được publish ra host nhưng tiến trình trong container không nhận kết nối từ interface container. Kiểm tra cả địa chỉ bind bên trong container lẫn port mapping.

## 7. Kiểm tra TCP từ client đến đúng host:port

Khi DNS đã đúng và server có listener, kiểm tra TCP từ cùng network namespace với client.

PowerShell:

~~~powershell
Test-NetConnection grpc.internal.example -Port 9090
~~~

Linux:

~~~bash
nc -vz -w 3 grpc.internal.example 9090
~~~

Kết quả TCP thành công chỉ chứng minh socket có thể mở. Nó chưa chứng minh server nói gRPC, TLS hợp lệ hoặc HTTP/2 hoạt động.

Nếu Connection refused, quay lại listener, bind address, port mapping và firewall. Nếu timeout, kiểm tra route, security group, firewall, Kubernetes NetworkPolicy, load balancer và địa chỉ đích. Đừng tăng client deadline để che một route bị chặn.

## 8. Kiểm tra port và cấu hình trong Spring gRPC

Tên property phụ thuộc starter và phiên bản Spring gRPC đang sử dụng. Một số hệ thống dùng property thuộc namespace spring.grpc.server.*; starter cũ hoặc thư viện khác có thể dùng grpc.server.*. Không sao chép property từ một dự án khác mà chưa xác minh dependency đang chạy.

Kiểm tra các nguồn cấu hình:

1. application.yml/application.properties.
2. Profile đang active, ví dụ application-prod.yml.
3. Environment variables và command-line arguments.
4. Config map/secret hoặc cấu hình được inject khi deploy.
5. Log startup và effective configuration nếu actuator/configuration diagnostics được bật an toàn.

Ví dụ minh họa cấu hình theo Spring gRPC starter mới:

~~~yaml
spring:
  grpc:
    server:
      port: 9090
~~~

Ví dụ minh họa kiểu property thường gặp ở starter cũ:

~~~yaml
grpc:
  server:
    port: 9090
~~~

Hai ví dụ trên thuộc các hệ sinh thái starter khác nhau; không khai báo đồng thời chỉ để thử cho chạy. Xác định đúng starter, property binding và default port trong phiên bản thực tế.

Ngoài port, xác minh server starter đã được đưa vào runtime classpath, service implementation được đăng ký bằng annotation/cấu hình phù hợp, và không có lỗi khởi động bị che trong log.

## 9. Container và Kubernetes: kiểm tra từng lớp port mapping

Trong container, cần phân biệt:

1. Port tiến trình gRPC listen bên trong container.
2. Port được publish/mapping ra host nếu truy cập từ ngoài.
3. Port của Kubernetes Service.
4. targetPort trỏ đến port container.

Ví dụ Docker:

~~~bash
docker ps
docker port orders-service
docker logs orders-service
~~~

Nếu server listen ở 9090 trong container nhưng không publish port, client từ host không thể truy cập qua host port. Khi dùng Docker network nội bộ, container client nên gọi service/container name và container port; không cần vòng qua localhost của host.

Trong Kubernetes:

~~~bash
kubectl get svc orders-grpc -n backend -o yaml
kubectl get endpointslice -n backend -l kubernetes.io/service-name=orders-grpc
kubectl get pods -n backend -o wide
kubectl logs deploy/orders-service -n backend
~~~

Kiểm tra port, targetPort, selector, EndpointSlice có endpoint Ready và pod IP có đúng không. Service tồn tại nhưng không có endpoint Ready thường dẫn đến kết nối không thành công hoặc bị từ chối tùy network implementation.

Chạy probe từ một pod trong cùng network policy:

~~~bash
kubectl exec -n backend deploy/orders-client -- \
  sh -c 'nc -vz orders-grpc 9090'
~~~

Nếu container image không có nc, dùng ephemeral debug container hoặc công cụ đã được phê duyệt trong môi trường. Không cài tiện ích tùy tiện vào production image chỉ để chẩn đoán.

## 10. Phân biệt plaintext và TLS

Sau khi TCP kết nối được, client và server phải thống nhất chế độ bảo mật:

- Server plaintext nhưng client dùng TLS: handshake thất bại.
- Server TLS nhưng client dùng plaintext: byte handshake/protocol không khớp, thường báo lỗi transport.
- Cả hai dùng TLS nhưng trust chain, SAN hoặc SNI sai: certificate validation/handshake thất bại.
- Dùng mTLS nhưng thiếu hoặc sai client certificate: server từ chối handshake.

Dùng grpcurl để probe:

~~~bash
# Chỉ dùng khi server được cấu hình plaintext.
grpcurl -plaintext grpc.internal.example:9090 list

# TLS với xác minh certificate theo trust store mặc định.
grpcurl grpc.internal.example:9090 list

# Chỉ cho môi trường test có kiểm soát; bỏ qua xác minh certificate.
grpcurl -insecure grpc.internal.example:9090 list
~~~

-insecure không phải cách sửa lỗi production. Nó chỉ giúp xác định liệu lỗi có liên quan đến certificate verification hay không; cần sửa trust roots/SAN/SNI rồi bật xác minh trở lại.

Nếu server không bật reflection, lệnh list có thể báo không có reflection dù kết nối gRPC đã thành công. Khi đó dùng .proto hoặc protoset với grpcurl -import-path ... -proto ... describe ... hoặc -d ... để gọi method. Reflection bị tắt không đồng nghĩa port không kết nối được.

## 11. Kiểm tra certificate, SNI và HTTP/2 ALPN

Với TLS, hostname client dùng để kết nối phải khớp Subject Alternative Name (SAN) trong certificate, hoặc phải có cấu hình authority override có chủ đích. Certificate chain phải được client tin cậy. Với mTLS, server cũng cần trust client certificate.

Có thể kiểm tra handshake và ALPN bằng OpenSSL:

~~~bash
openssl s_client \
  -connect grpc.internal.example:9090 \
  -servername grpc.internal.example \
  -alpn h2
~~~

Kiểm tra:

- Certificate có còn hạn và chain có đầy đủ không?
- SAN có chứa hostname client dùng không?
- SNI có được gửi đúng đến TLS terminator không?
- ALPN có chọn h2 không?
- Proxy/load balancer có terminate TLS rồi chuyển upstream bằng HTTP/2 không?
- Nếu mTLS, client có gửi certificate và private key tương ứng không?

gRPC dùng HTTP/2. Một proxy có thể mở TCP và TLS thành công nhưng chuyển upstream bằng HTTP/1.1, khiến gRPC call thất bại sau handshake. Cấu hình listener/upstream protocol phải hỗ trợ HTTP/2 end-to-end hoặc HTTP/2 ở từng chặng theo topology.

## 12. Dùng grpcurl để kiểm tra gRPC thực sự

Sau khi TCP và TLS đã đúng, dùng grpcurl để kiểm tra protocol và service:

~~~bash
# Liệt kê service nếu reflection được bật.
grpcurl -plaintext localhost:9090 list

# Xem descriptor của một service qua file proto.
grpcurl -plaintext \
  -import-path ./src/main/proto \
  -proto orders.proto \
  localhost:9090 describe orders.v1.OrdersIngress
~~~

Gọi thử một method:

~~~bash
grpcurl -plaintext \
  -import-path ./src/main/proto \
  -proto orders.proto \
  -d '{"customerId":"customer-9"}' \
  localhost:9090 \
  orders.v1.OrdersIngress/GetOrder
~~~

Tên package, service và method phải khớp descriptor thực tế. Nếu grpcurl kết nối được nhưng method trả UNIMPLEMENTED, kiểm tra server đã đăng ký đúng generated service implementation chưa. Nếu trả UNAUTHENTICATED, transport đã tới security layer; chuyển sang kiểm tra credential thay vì tiếp tục đổi port.

Không dùng curl http://host:port như phép thử duy nhất cho gRPC. HTTP/2 prior knowledge, TLS và framing của gRPC khác một REST endpoint thông thường.

## 13. Kiểm tra firewall, route và load balancer

Nếu server listen đúng và TCP probe vẫn timeout, kiểm tra đường đi mạng:

- Firewall trên host server và host client.
- Cloud security group/network ACL.
- Kubernetes NetworkPolicy ingress/egress.
- VPN, subnet route, NAT và DNS trả địa chỉ nội bộ/ngoại bộ phù hợp.
- Load balancer listener, backend pool, health check và port mapping.
- Proxy có yêu cầu HTTP/2, TLS passthrough hoặc TLS termination đúng cách không?

Kiểm tra từ gần đến xa: loopback trên server, IP interface server, container network, pod-to-pod, service DNS, rồi từ client thực tế. Cách này giúp khoanh vùng lớp đầu tiên bị lỗi.

Không mở port ra toàn Internet như bước thử nghiệm mặc định. Chỉ cho phép nguồn client cần thiết, đúng giao thức và đúng môi trường.

## 14. Dùng health check để phân biệt server sống và method hoạt động

TCP port mở chỉ cho biết có process nhận kết nối. Nó không chứng minh service đã sẵn sàng phục vụ nghiệp vụ.

gRPC Health Checking Protocol có thể cung cấp trạng thái SERVING/NOT_SERVING cho service. Nếu dùng health check, xác minh:

- Health service đã được đăng ký và client/probe gọi đúng port.
- Trạng thái phản ánh readiness thực tế, ví dụ dependency bắt buộc đã sẵn sàng.
- Kubernetes gRPC probe hoặc load balancer health check dùng đúng port và service name.
- Health check không báo SERVING quá sớm khi server chưa hoàn tất startup.

NOT_SERVING là phản hồi gRPC hợp lệ sau khi đã kết nối được. Nó khác với TCP connection refused. Health check cũng không thay thế probe cho từng RPC method hoặc kiểm tra authorization.

## 15. Quy trình khoanh vùng theo thứ tự

Thực hiện tuần tự để tránh sửa nhiều lớp cùng lúc:

1. **Ghi lại target và lỗi đầy đủ:** hostname, port, thời điểm, nested exception, TLS/plaintext và môi trường chạy client.
2. **Kiểm tra DNS:** phân giải từ đúng container/pod/host của client.
3. **Kiểm tra listener:** server có khởi động và listen đúng port, đúng interface không?
4. **Probe TCP:** dùng Test-NetConnection hoặc nc từ cùng network namespace với client.
5. **Kiểm tra port mapping/route:** container, Kubernetes Service/EndpointSlice, firewall và load balancer.
6. **Kiểm tra TLS/ALPN:** certificate, SAN, SNI, mTLS và h2.
7. **Probe gRPC:** dùng grpcurl với đúng plaintext/TLS và descriptor.
8. **Kiểm tra service/security:** service registration, reflection, authentication và authorization.

Sau mỗi bước, ghi kết quả và chỉ thay đổi lớp đã có bằng chứng lỗi. Nếu TCP probe đã thành công, đừng tiếp tục chỉnh firewall khi lỗi thực tế nằm ở certificate hoặc HTTP/2.

## 16. Bảng triệu chứng và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Local gọi được, container gọi không được | Bind loopback, DNS hoặc port mapping | Bind interface phù hợp, gọi service name và kiểm tra mapping |
| Container gọi được, pod khác không được | Kubernetes Service, NetworkPolicy hoặc endpoint | Kiểm tra Service, EndpointSlice và policy |
| TCP refused | Không có listener hoặc port sai | Kiểm tra log startup, port, bind address và process |
| TCP timeout | Firewall, route, security group hoặc network policy | Probe từng chặng và kiểm tra rule |
| TLS handshake fail | Plaintext/TLS mismatch, certificate hoặc mTLS | Đồng bộ chế độ, kiểm tra trust chain/SAN/client cert |
| TLS thành công nhưng gRPC fail | ALPN không phải h2, proxy dùng HTTP/1.1 | Sửa HTTP/2 upstream/ALPN |
| grpcurl list báo reflection unavailable | Reflection chưa bật | Dùng .proto/protoset hoặc bật reflection ở môi trường phù hợp |
| UNIMPLEMENTED | Sai package/service/method hoặc chưa register implementation | Kiểm tra descriptor và server registration |
| UNAUTHENTICATED | Thiếu/sai credential | Kiểm tra token, TLS identity và interceptor |
| DEADLINE_EXCEEDED | Connect hoặc xử lý vượt deadline | Đo thời gian từng tầng; đặt deadline hợp lý |

## 17. Những lỗi chẩn đoán thường gặp

| Cách làm sai | Vì sao không hiệu quả | Cách làm đúng |
|---|---|---|
| Đổi server.port mà không xác định port gRPC | HTTP và gRPC có thể dùng port riêng | Xác minh property của đúng starter |
| Gọi localhost từ container để tới host/service khác | Loopback trỏ về chính container | Dùng DNS/service name hoặc host mapping đúng |
| Chỉ kiểm tra port trên máy server | Client có thể bị chặn ở route/firewall | Probe từ đúng network namespace client |
| Thấy UNAVAILABLE rồi kết luận server tắt | Status bao gồm nhiều lỗi transport | Đọc nested cause và phân tầng |
| Dùng curl để kết luận gRPC hoạt động | Không xác minh gRPC framing/service | Dùng grpcurl hoặc client gRPC |
| Tắt TLS verification để sửa production | Che lỗi trust/SAN và làm yếu bảo mật | Cài trust chain và certificate đúng |
| Cho rằng grpcurl list lỗi nghĩa port đóng | Reflection có thể chưa bật | Gọi method bằng proto/protoset |
| Tăng deadline khi TCP timeout | Không sửa route hoặc listener | Sửa nguyên nhân kết nối |

**Ghi nhớ:** Chẩn đoán port gRPC theo từng tầng: DNS → TCP → TLS/ALPN h2 → gRPC service → application. Xác minh đúng target, listener và bind address từ môi trường server; probe TCP từ môi trường client; kiểm tra port mapping, route, firewall và Kubernetes endpoints; sau đó dùng grpcurl để xác nhận gRPC. Phân biệt connection refused, timeout, TLS failure và gRPC status để sửa đúng lớp, không thay đổi cấu hình ngẫu nhiên.
