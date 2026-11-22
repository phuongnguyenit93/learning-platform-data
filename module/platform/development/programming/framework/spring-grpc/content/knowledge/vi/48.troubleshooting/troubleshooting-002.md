# Server chạy nhưng client không resolve target

## 1. Hiểu đúng lỗi target resolution

Trong **SPRING_GRPC**, client gọi service bằng gRPC trên HTTP/2 và dùng hợp đồng Protocol Buffers để trao đổi request/response. Khi server vẫn chạy nhưng client báo không resolve được target, vấn đề thường nằm ở tên đích, cú pháp target URI, DNS hoặc name resolver của gRPC Java.

Target là thông tin client dùng để tìm địa chỉ server. Nó thường gồm hostname và port, hoặc một URI có scheme để chọn cơ chế phân giải:

~~~text
dns:///orders-grpc.backend.svc.cluster.local:9090
~~~

gRPC name resolver chuyển target thành một hay nhiều địa chỉ socket. Sau bước đó, channel mới có thể thử kết nối TCP, thực hiện TLS/HTTP2 và gọi service.

~~~mermaid
flowchart TD
    A["gRPC target string"] --> B["Parse URI / resolver scheme"]
    B --> C["NameResolver"]
    C --> D["DNS / service discovery"]
    D --> E["Resolved socket addresses"]
    E --> F["TCP connect"]
    F --> G["TLS + HTTP/2"]
    G --> H["gRPC service / method"]
    B -->|invalid target / scheme| X["Target parse error"]
    C -->|provider missing| Y["Resolver provider error"]
    D -->|name not found / no records| Z["Resolution failure"]
~~~

Thông báo “server chạy” chỉ chứng minh tiến trình server đang hoạt động ở đâu đó. Client vẫn có thể dùng hostname sai, port sai, namespace DNS khác hoặc resolver scheme không được hỗ trợ.

## 2. Phân biệt resolve target với kết nối TCP

Hai giai đoạn thường bị nhầm lẫn:

- **Name resolution:** chuyển hostname/service name thành địa chỉ IP.
- **Connection:** mở TCP socket đến địa chỉ IP và port đã resolve.

| Dấu hiệu | Giai đoạn có khả năng lỗi | Hướng kiểm tra |
|---|---|---|
| `UnknownHostException`, `NameResolver` không tìm được địa chỉ | DNS/name resolution | Hostname, DNS search domain, namespace, resolver |
| `Unable to resolve host` hoặc `No DNS records` | DNS/name resolution | A/AAAA record, service discovery, DNS cache |
| `No resolver found for scheme` | Chọn resolver | Scheme trong target và dependency/provider |
| `Invalid target URI` | Parse target | Cú pháp URI, dấu slash, hostname và port |
| `Connection refused` | TCP sau khi resolve | Listener, port, route và bind address |
| `Connection timed out` | TCP/network sau khi resolve | Firewall, route, security group |
| `SSLHandshakeException` | TLS sau khi TCP kết nối | Certificate, SAN, SNI, trust chain |

Một lỗi `UNAVAILABLE` có thể bao bọc lỗi ở nhiều giai đoạn. Hãy đọc nested cause để xác định client đã resolve được địa chỉ hay chưa. Nếu đã có IP và lỗi là `Connection refused`, không tiếp tục sửa DNS.

## 3. Kiểm tra target string mà client thực sự sử dụng

Target thường được tạo từ cấu hình, environment variable hoặc service discovery. Ghi lại giá trị hiệu lực tại runtime (che thông tin nội bộ nhạy cảm nếu cần) và kiểm tra:

- Hostname có đúng tên service không?
- Port có đúng port gRPC mà server listen không?
- Có vô tình dùng port HTTP/actuator thay cho port gRPC không?
- Target có chứa `http://` hoặc `https://` như một URL REST không?
- Có thừa khoảng trắng, dấu slash, dấu colon hoặc ký tự bị encode sai không?
- Profile, environment variable hoặc ConfigMap có override target không?

gRPC target không phải URL REST. Ví dụ `https://orders.internal:9090` không phải target thông thường để truyền vào `ManagedChannelBuilder.forTarget(...)`. Với DNS resolver, dùng cú pháp rõ ràng:

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///orders-grpc.backend.svc.cluster.local:9090")
        .usePlaintext()
        .build();
~~~

Ví dụ trên dùng plaintext để minh họa target resolution. Trong môi trường production, cấu hình TLS/credentials theo security policy của hệ thống. Không bật `usePlaintext()` chỉ để che một lỗi TLS.

## 4. Hiểu cú pháp dns:///host:port

Target `dns:///orders-grpc.backend.svc.cluster.local:9090` gồm:

| Thành phần | Ý nghĩa |
|---|---|
| `dns` | Chọn DNS name resolver |
| `://` | Phần phân cách scheme của URI |
| `//` tiếp theo | Authority rỗng trong URI |
| `/orders-grpc.backend.svc.cluster.local:9090` | Địa chỉ DNS và port cần phân giải |

Ba dấu slash trong `dns:///` là có chủ đích: URI dùng scheme `dns`, authority rỗng và phần địa chỉ nằm trong path. Không tự rút gọn thành `dns://orders-grpc:9090` nếu chưa xác minh cú pháp mà resolver đang dùng.

Nên ghi rõ port. Nếu bỏ port, default port của resolver hoặc channel có thể khác cấu hình server, làm chẩn đoán khó hơn.

Các target khác nhau có thể chọn resolver khác nhau. Ví dụ `dns:///...` chọn DNS resolver; một scheme riêng chỉ hoạt động khi ứng dụng có `NameResolverProvider` tương ứng.

## 5. Kiểm tra hostname từ đúng môi trường client

DNS của máy developer có thể khác DNS bên trong Docker container, Kubernetes pod, VM hoặc network production. Chạy lệnh kiểm tra trong cùng môi trường và network namespace với JVM đang tạo gRPC channel.

Windows PowerShell:

~~~powershell
Resolve-DnsName orders-grpc.backend.svc.cluster.local
~~~

Linux:

~~~bash
getent hosts orders-grpc.backend.svc.cluster.local
nslookup orders-grpc.backend.svc.cluster.local
~~~

Nếu có `dig`:

~~~bash
dig A orders-grpc.backend.svc.cluster.local
dig AAAA orders-grpc.backend.svc.cluster.local
~~~

Kiểm tra cả bản ghi IPv4 (A) và IPv6 (AAAA) nếu client có thể chọn cả hai. Một bản ghi AAAA tồn tại nhưng route IPv6 không hoạt động có thể khiến một số môi trường gặp lỗi hoặc chậm trước khi thử địa chỉ khác.

Nếu DNS trả nhiều địa chỉ, xác minh chúng thuộc đúng service/backend và còn khả dụng. Nếu không trả địa chỉ, kiểm tra tên, search domain, DNS server và service discovery trước khi đổi port.

## 6. Kubernetes DNS: service name và namespace

Trong Kubernetes, DNS name thường có dạng:

~~~text
<service>.<namespace>.svc.<cluster-domain>
~~~

Ví dụ:

~~~text
orders-grpc.backend.svc.cluster.local
~~~

`cluster.local` là cluster domain phổ biến nhưng có thể được tùy chỉnh. Hãy dùng domain thực tế của cluster.

Quy tắc tên ngắn:

- Client và Service cùng namespace: có thể gọi `orders-grpc`.
- Khác namespace: dùng ít nhất `orders-grpc.backend`.
- Muốn target rõ ràng và ít phụ thuộc search path: dùng FQDN đầy đủ.

Tên ngắn có thể resolve sai nếu client ở namespace khác và có một service trùng tên trong namespace hiện tại. Dùng FQDN giúp loại bỏ sự mơ hồ đó.

Kiểm tra service và endpoint:

~~~bash
kubectl get svc orders-grpc -n backend -o wide
kubectl get endpointslice -n backend -l kubernetes.io/service-name=orders-grpc
kubectl get pods -n backend -o wide
kubectl get pods -n backend --show-labels
~~~

Service DNS có thể tồn tại dù selector không khớp pod hoặc không có endpoint Ready. Khi đó DNS có thể resolve bình thường nhưng kết nối đến service vẫn thất bại. Đây là lỗi endpoint/routing sau resolution, không phải DNS lookup failure.

## 7. Headless Service và nhiều địa chỉ trả về

Kubernetes Service thông thường thường resolve đến ClusterIP. Headless Service (`clusterIP: None`) có thể resolve thành nhiều địa chỉ pod. DNS resolver có thể nhận danh sách IP thay vì một IP duy nhất.

Điều này ảnh hưởng cách client phân phối kết nối:

- Với ClusterIP, Kubernetes Service/network dataplane thường chọn backend.
- Với headless Service, client resolver có thể nhìn thấy nhiều địa chỉ pod và gRPC load balancing policy quyết định cách dùng chúng.
- Pod thay đổi IP khi restart; resolver cần cập nhật địa chỉ theo DNS refresh.
- Nếu client giữ channel lâu dài, không nên giả định danh sách địa chỉ chỉ được resolve một lần rồi luôn đúng.

Nếu dùng headless Service, kiểm tra readiness, DNS record của pod và policy load balancing của channel. Nếu cần cân bằng tải qua nhiều backend, xác định rõ muốn Kubernetes Service chọn backend hay gRPC client-side load balancing.

## 8. Name resolver scheme và provider

gRPC Java chọn resolver dựa trên scheme trong target. DNS resolver là lựa chọn phổ biến; các scheme như `consul`, `xds` hoặc scheme nội bộ cần provider được đăng ký trong runtime.

Nếu gặp lỗi kiểu “no resolver available for scheme”, kiểm tra:

1. Scheme trong target có đúng chính tả và đúng chữ thường không?
2. Dependency chứa resolver provider có nằm trong runtime classpath không?
3. Provider có được đăng ký đúng cơ chế `NameResolverProvider`/ServiceLoader không?
4. Phiên bản provider có tương thích với gRPC Java core không?
5. Khi đóng gói executable JAR hoặc native image, metadata ServiceLoader có được giữ lại không?

Ví dụ, nếu ứng dụng dùng target `consul:///orders`, nhưng runtime chỉ có DNS resolver, client không thể tự hiểu Consul. Cần thêm resolver integration tương ứng hoặc chuyển target sang DNS name nếu kiến trúc cho phép.

Không thay scheme thành `dns` chỉ để loại bỏ lỗi nếu service discovery thực sự yêu cầu resolver tùy chỉnh. Điều đó có thể làm client bỏ qua routing, health hoặc service config do resolver chuyên biệt cung cấp.

## 9. Tạo channel bằng target đúng trong Java

Một channel thường được tạo một lần và tái sử dụng, không tạo mới cho mỗi RPC:

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///orders-grpc.backend.svc.cluster.local:9090")
        .defaultLoadBalancingPolicy("round_robin")
        .useTransportSecurity()
        .build();

OrdersIngressGrpc.OrdersIngressBlockingStub stub =
        OrdersIngressGrpc.newBlockingStub(channel);

try {
    GetOrderReply reply = stub
            .withDeadlineAfter(2, TimeUnit.SECONDS)
            .getOrder(request);
} finally {
    channel.shutdown();
}
~~~

Đây là ví dụ độc lập minh họa lifecycle. Trong ứng dụng Spring, channel thường được quản lý như bean/singleton theo cấu hình starter để tái sử dụng qua nhiều request; không shutdown channel sau từng RPC. Chỉ shutdown khi ứng dụng đóng hoặc channel cần được thay thế có kiểm soát.

`defaultLoadBalancingPolicy("round_robin")` chỉ hữu ích khi resolver trả nhiều địa chỉ và policy được hỗ trợ/cấu hình đúng. Nó không sửa được hostname không resolve.

## 10. Phân biệt target host với TLS authority/SNI

Target hostname thường tham gia vào việc chọn địa chỉ và xác định authority của kết nối. Với TLS, certificate phải hợp lệ cho tên server mà client xác minh. DNS resolution thành công không đảm bảo certificate cũng hợp lệ.

Ví dụ client target là `orders-grpc.backend.svc.cluster.local`, nhưng certificate chỉ có SAN `orders.example.internal`. TCP có thể kết nối và DNS có thể đúng, song TLS hostname verification vẫn thất bại.

Không sửa lỗi certificate bằng cách thay target thành IP nếu certificate không có IP SAN tương ứng. Cách đúng là cấp certificate có SAN phù hợp hoặc cấu hình authority override có chủ đích theo topology, đồng thời vẫn xác minh certificate chain và hostname mong muốn.

`overrideAuthority(...)` tác động đến authority được dùng trong gRPC; nó không phải DNS resolver và không sửa được hostname không phân giải. Chỉ sử dụng khi hiểu rõ tác động đến HTTP/2 `:authority`, TLS verification và SNI trong transport đang dùng.

## 11. IPv4, IPv6 và literal IP

Một số lỗi target xuất phát từ cách biểu diễn địa chỉ:

- Hostname nên có port tách rõ, ví dụ `orders.internal:9090`.
- IPv4 literal có dạng `10.20.1.15:9090`.
- IPv6 literal phải đặt trong ngoặc vuông, ví dụ `[2001:db8::15]:9090`.
- Không ghép IPv6 và port bằng cách đoán vị trí dấu colon cuối nếu chưa dùng parser URI chuẩn.

Kết nối bằng IP literal có thể giúp cô lập lỗi DNS, nhưng chỉ là phép thử chẩn đoán. Với TLS, certificate phải có SAN phù hợp với IP hoặc phải dùng authority/certificate design đúng. Production thường nên dùng DNS/service identity ổn định thay vì ghim IP pod có thể thay đổi.

## 12. DNS cache và channel tồn tại lâu

DNS record thay đổi không nhất thiết được mọi client nhìn thấy ngay lập tức. Kết quả có thể bị ảnh hưởng bởi:

- DNS TTL và cache của DNS server.
- Cache phân giải tên của JVM/OS.
- Refresh behavior của gRPC name resolver.
- Channel đang giữ kết nối đến backend cũ.
- Service discovery cập nhật endpoint chậm.

Không tạo channel mới liên tục để ép DNS refresh; cách đó gây tốn socket, thread và handshake. Trước tiên xác minh TTL/cache và resolver behavior của phiên bản đang dùng. Khi endpoint thay đổi, gRPC resolver có thể cập nhật địa chỉ cho channel theo cơ chế refresh; ứng dụng không nên tự tạo channel mỗi request.

Nếu cần chuyển target hoặc credentials, quản lý channel lifecycle: tạo channel mới, chuyển traffic, rồi graceful shutdown channel cũ. Đừng thay đổi cấu hình DNS và kỳ vọng mọi channel đang chạy lập tức chuyển sang địa chỉ mới.

## 13. Chẩn đoán bằng grpcurl và công cụ DNS

`grpcurl` giúp kiểm tra một target từ môi trường shell:

~~~bash
# Server plaintext, reflection được bật.
grpcurl -plaintext orders-grpc.backend.svc.cluster.local:9090 list

# Server TLS, xác minh certificate theo trust store.
grpcurl orders-grpc.backend.svc.cluster.local:9090 list
~~~

Nếu `getent hosts` không resolve, xử lý DNS trước. Nếu DNS resolve nhưng `grpcurl` báo connection refused, chuyển sang kiểm tra TCP/listener. Nếu `grpcurl` thành công nhưng ứng dụng Java không resolve, tập trung vào target string, resolver scheme/provider, JVM/container DNS, proxy và cấu hình channel.

`grpcurl` và JVM có thể dùng resolver/runtime khác nhau. Vì vậy, kết quả thành công của grpcurl không chứng minh Java resolver chắc chắn có cùng hành vi; nó chỉ giúp khoanh vùng sự khác biệt giữa công cụ và ứng dụng.

Nếu reflection tắt, `grpcurl list` có thể thất bại dù target và gRPC server hoạt động. Dùng `.proto` hoặc protoset để gọi method; không kết luận DNS lỗi chỉ từ thông báo reflection unavailable.

## 14. Checklist khi client không resolve target

Thực hiện theo thứ tự:

1. **Ghi target runtime:** log host, port, scheme và profile hiệu lực; không log credential.
2. **Kiểm tra cú pháp:** target gRPC không phải URL REST; xác nhận `dns:///host:port` nếu dùng DNS resolver.
3. **Kiểm tra DNS từ client runtime:** `Resolve-DnsName`, `getent`, `nslookup` hoặc `dig`.
4. **Kiểm tra Kubernetes namespace/FQDN:** service name, cluster domain và DNS search path.
5. **Kiểm tra endpoint:** Service selector, EndpointSlice, pod readiness và headless service behavior.
6. **Kiểm tra resolver provider:** scheme, dependency, ServiceLoader và phiên bản gRPC.
7. **Kiểm tra địa chỉ và port:** A/AAAA record, IPv4/IPv6, port gRPC thực tế.
8. **Kiểm tra TLS identity:** SAN, SNI và authority sau khi resolution đã thành công.
9. **So sánh bằng grpcurl:** chạy từ cùng môi trường và đối chiếu với Java client.

Ghi lại từng kết quả để xác định bước đầu tiên thất bại. Không thay đồng thời hostname, port, TLS và load balancing vì sẽ mất khả năng biết thay đổi nào giải quyết vấn đề.

## 15. Bảng triệu chứng và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `UnknownHostException` | Hostname sai hoặc DNS không biết tên | Kiểm tra FQDN và DNS từ client runtime |
| Service name chỉ resolve trong một namespace | Dùng tên ngắn ở namespace khác | Dùng `service.namespace` hoặc FQDN |
| `No resolver found for scheme` | Thiếu resolver provider hoặc target sai scheme | Kiểm tra scheme và runtime dependency |
| Target URI parse error | Sai slash, port hoặc URL syntax | Dùng target URI đúng định dạng |
| DNS resolve nhưng TCP refused | Không có listener/endpoint hoặc port sai | Kiểm tra Service, EndpointSlice, targetPort |
| DNS trả nhiều IP nhưng một số IP lỗi | Endpoint cũ, pod chưa Ready hoặc stale record | Kiểm tra endpoint health và resolver refresh |
| Java lỗi nhưng grpcurl thành công | Khác target, JVM DNS, provider hoặc proxy | So sánh runtime config và resolver |
| DNS thành công nhưng TLS hostname fail | SAN không khớp authority | Cấp certificate đúng identity hoặc authority config có chủ đích |
| Chỉ lỗi IPv6 | AAAA record có nhưng route IPv6 không hoạt động | Kiểm tra IPv6 path và resolver/address policy |
| Channel cũ không chuyển backend | DNS cache/resolver refresh hoặc connection còn sống | Kiểm tra TTL, resolver policy và channel lifecycle |

## 16. Những lỗi cấu hình thường gặp

| Cách làm sai | Hậu quả | Cách làm đúng |
|---|---|---|
| Truyền `https://host:port` vào `forTarget` | Resolver không nhận target như mong đợi | Dùng target URI theo resolver, ví dụ `dns:///host:port` |
| Dùng tên Service ngắn từ namespace khác | DNS tìm sai suffix hoặc không thấy tên | Dùng FQDN Kubernetes |
| Dùng `localhost` để gọi pod/service khác | Resolve đến loopback của client | Dùng DNS service name |
| Dùng custom scheme nhưng thiếu provider | Không có resolver xử lý target | Thêm resolver dependency/registration phù hợp |
| Sửa DNS khi lỗi thực tế là TLS | Không khắc phục SAN/SNI mismatch | Tách resolution và TLS thành hai bước |
| Ghim IP pod trong production | Pod restart làm target lỗi | Dùng Service DNS/service discovery |
| Tạo channel mỗi RPC để refresh DNS | Rò rỉ socket và tăng handshake | Tái sử dụng channel, quản lý resolver/lifecycle |
| Dùng `overrideAuthority` để chữa DNS | Authority thay đổi nhưng hostname vẫn không resolve | Sửa target DNS; chỉ override authority cho TLS/authority đúng chủ đích |

**Ghi nhớ:** Khi server chạy nhưng client không resolve target, hãy kiểm tra target string và name resolver trước khi kiểm tra TCP. Dùng `dns:///host:port` cho DNS resolver, xác minh DNS từ đúng container/pod, dùng FQDN khi khác Kubernetes namespace, và bảo đảm custom scheme có provider trong runtime. Phân biệt DNS resolution với endpoint/TCP và TLS authority/SNI; channel nên được tái sử dụng để resolver cập nhật địa chỉ theo cơ chế của nó.
