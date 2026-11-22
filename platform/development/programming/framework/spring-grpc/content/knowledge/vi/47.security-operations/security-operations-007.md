# Network policy cho port gRPC

gRPC chạy trên HTTP/2 qua TCP. Trong Kubernetes, NetworkPolicy kiểm soát pod nào được phép mở kết nối tới pod nào và qua port nào. Với Spring gRPC, cấu hình đúng policy giúp chỉ workload cần thiết truy cập listener gRPC, đồng thời giữ DNS, health check và các luồng phụ trợ hoạt động theo yêu cầu triển khai.

NetworkPolicy là kiểm soát mạng ở Layer 3/4. Nó có thể cho phép TCP tới port gRPC, nhưng không phân biệt method như `GetOrder` hay `CancelOrder`, không xác thực user và không thay thế TLS. Phân quyền method vẫn cần authentication/authorization trong ứng dụng hoặc một lớp proxy/service mesh có khả năng kiểm soát Layer 7.

## 1. Xác định port thực sự được bảo vệ

Một gRPC service thường mở một listener TCP và multiplex nhiều RPC trên cùng HTTP/2 connection. Vì vậy, NetworkPolicy thường chỉ cần cho phép TCP tới port listener; không tạo một port riêng cho từng RPC method.

Ví dụ workload:

| Thành phần | Giá trị minh họa |
| --- | --- |
| Namespace server | `catalog` |
| Pod label server | `app: catalog-grpc` |
| Container listener | TCP `9090` |
| Kubernetes Service | `catalog-grpc` |
| Namespace client | `commerce` |
| Pod label client | `app: checkout` |
| Service DNS | `catalog-grpc.catalog.svc.cluster.local` |

Ví dụ Service:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-grpc
  namespace: catalog
spec:
  selector:
    app: catalog-grpc
  ports:
    - name: grpc
      protocol: TCP
      port: 9090
      targetPort: 9090
~~~

`port` là port mà client gọi trên Service; `targetPort` là port listener trong pod. Trong NetworkPolicy, rule thường phải khớp port đích trên pod, tức `targetPort`/listener `9090`. Nếu Service dùng `port: 443` nhưng chuyển tiếp tới `targetPort: 9090`, hãy kiểm tra policy theo port mà CNI thực thi trên endpoint pod và xác minh bằng test thực tế; không mặc định port Service và port container giống nhau.

## 2. Hiểu quy tắc isolation và allow của Kubernetes

NetworkPolicy có các semantics quan trọng:

- Pod không được chọn bởi policy ingress vẫn nhận ingress theo mặc định.
- Khi một policy có `policyTypes: [Ingress]` chọn pod, pod đó trở thành ingress-isolated; chỉ các luồng được allow bởi những policy ingress áp dụng mới vào được.
- Egress hoạt động tương tự: pod chỉ bị egress-isolated khi có policy egress chọn nó.
- Các rule allow từ nhiều NetworkPolicy được cộng lại; policy không có thứ tự ưu tiên kiểu deny-overrides.
- Với kết nối giữa hai pod, egress policy của nguồn và ingress policy của đích đều phải cho phép.
- Kết nối được cho phép là stateful; packet phản hồi của kết nối đó được phép quay lại mà không cần mở một rule inbound ngược chiều.

Do rule allow được cộng lại, thêm một policy hẹp không thu hẹp một policy rộng đã tồn tại. Trước khi áp dụng default-deny, cần kiểm tra các policy hiện hữu trong namespace để hiểu toàn bộ tập rule đang có hiệu lực.

## 3. Default-deny ingress cho namespace server

Đầu tiên, cô lập ingress vào các pod trong namespace `catalog`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: catalog
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress: []
~~~

Policy này chọn mọi pod trong namespace `catalog` và không mở ingress rule nào. Những pod cần nhận traffic phải có policy allow riêng. Nếu namespace chứa nhiều workload khác nhau, có thể chọn theo label hoặc tách namespace để quản lý phạm vi rõ ràng.

## 4. Chỉ cho phép client đã chọn gọi gRPC server

Policy sau cho phép pod `app: checkout` trong namespace `commerce` truy cập pod `app: catalog-grpc` ở TCP port `9090`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-checkout-to-catalog-grpc
  namespace: catalog
spec:
  podSelector:
    matchLabels:
      app: catalog-grpc
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: commerce
          podSelector:
            matchLabels:
              app: checkout
      ports:
        - protocol: TCP
          port: 9090
~~~

`namespaceSelector` và `podSelector` nằm trong cùng một peer item nên được kết hợp theo phép AND: nguồn phải là pod `app: checkout` thuộc namespace `commerce`. Nếu tách chúng thành hai item trong danh sách `from`, ý nghĩa sẽ là OR và policy có thể cho phép rộng hơn dự kiến.

Label `kubernetes.io/metadata.name` thường được Kubernetes gắn tự động cho Namespace. Nếu cluster hoặc môi trường test không có label này, dùng label namespace do tổ chức quản lý và xác minh selector khớp đúng namespace.

Nếu traffic đi qua ingress controller, gateway hoặc service mesh gateway, nguồn mà server nhìn thấy có thể là pod gateway thay vì pod client. Khi đó rule cần allow đúng namespace/pod gateway. Không mở toàn bộ CIDR hoặc mọi namespace chỉ để làm kết nối chạy được.

## 5. Default-deny egress và allow từ client

Nếu client namespace áp dụng egress default-deny, client cần được cấp quyền tới gRPC server và DNS resolver. Ví dụ default-deny cho pod checkout:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: checkout-default-deny-egress
  namespace: commerce
spec:
  podSelector:
    matchLabels:
      app: checkout
  policyTypes:
    - Egress
  egress: []
~~~

Policy sau mở đúng gRPC destination và DNS:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: checkout-egress
  namespace: commerce
spec:
  podSelector:
    matchLabels:
      app: checkout
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: catalog
          podSelector:
            matchLabels:
              app: catalog-grpc
      ports:
        - protocol: TCP
          port: 9090
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
~~~

Rule DNS cho phép client phân giải tên Service trước khi kết nối. Label CoreDNS/kube-dns thay đổi theo cách cài cluster; kiểm tra label pod DNS thực tế và điều chỉnh selector. Một số CNI có cách xử lý traffic tới DNS Service IP hoặc node-local DNS riêng, nên cần xác minh policy trên CNI đang dùng.

Default-deny egress sẽ chặn các dependency khác của checkout nếu chưa có allow rule: database, identity provider, telemetry collector, message broker hoặc external API. Bổ sung từng luồng theo destination, protocol và port cần thiết; không mở `0.0.0.0/0 TCP` chỉ để tránh lỗi kết nối.

## 6. Port, protocol và HTTP/2

gRPC thông thường dùng TCP. NetworkPolicy cho listener phải ghi `protocol: TCP`; mở UDP cùng port không làm gRPC hoạt động. Một HTTP/2 connection có thể mang nhiều RPC đồng thời, nên tất cả method của cùng listener đi qua cùng port.

Một số điểm cần kiểm tra:

- Container listener thực sự bind vào `0.0.0.0:9090` hoặc địa chỉ pod phù hợp; bind vào `127.0.0.1` sẽ không nhận traffic từ pod khác.
- `containerPort`, Service `targetPort` và NetworkPolicy destination port phải nhất quán.
- Nếu TLS terminate tại gRPC server, policy vẫn cho phép TCP tới listener TLS đó.
- Nếu TLS terminate ở gateway, policy giữa gateway và backend phải cho phép port backend thực tế.
- HTTP/2 keepalive không cần mở thêm port riêng; nó dùng connection TCP hiện có.

NetworkPolicy không đọc ALPN, HTTP/2 frame, `:path` hay gRPC method. Không thể tạo rule Kubernetes chuẩn kiểu “chỉ cho phép `/acme.orders.v1.OrderService/GetOrder`”. Dùng interceptor, authorization policy hoặc proxy/service mesh L7 nếu cần kiểm soát theo RPC method.

## 7. Kết hợp NetworkPolicy với TLS và authentication

NetworkPolicy giới hạn nguồn mạng có thể tiếp cận pod. Nó không chứng minh caller là workload hợp lệ và không mã hóa dữ liệu. Một pod được phép vào port `9090` vẫn có thể là pod bị xâm nhập hoặc gửi request giả mạo.

Một lớp bảo vệ đầy đủ thường gồm:

1. **NetworkPolicy:** giới hạn namespace, pod, direction và TCP port.
2. **TLS/mTLS:** mã hóa transport; mTLS xác thực danh tính workload bằng certificate.
3. **Authentication:** xác minh principal/token nếu API yêu cầu danh tính người dùng hoặc service account.
4. **Authorization:** kiểm tra principal có quyền gọi service/method và truy cập resource hay không.
5. **Audit/telemetry:** ghi nhận danh tính, method, status và quyết định truy cập mà không log secret.

Không coi NetworkPolicy là ranh giới bảo mật duy nhất. Khi một client pod được allow vào port gRPC, server vẫn phải xác thực và phân quyền theo contract.

## 8. Health check và các luồng vận hành

Kubernetes có thể thực hiện liveness/readiness probe tới port của container; gRPC cũng có thể cung cấp Health Checking Protocol qua service `grpc.health.v1.Health`. Cần phân biệt:

- **Kubelet probe:** traffic do node/kubelet phát ra. Cách CNI áp dụng NetworkPolicy cho traffic node-originated phụ thuộc implementation và cấu hình.
- **Health check từ client/proxy:** traffic từ pod khác, cần allow selector và port tương ứng.
- **gRPC health RPC:** dùng listener gRPC; không cần port mới nếu health service cùng listener.

Không mặc định mọi CNI xử lý kubelet probe giống nhau. Khi bật default-deny ingress, xác minh readiness/liveness probe vẫn tới được pod trên CNI thực tế. Nếu cần rule riêng cho node hoặc probe source, dùng cơ chế được CNI hỗ trợ và giới hạn đúng node/port; tránh mở ingress toàn mạng.

Ngoài health check, kiểm tra các luồng vận hành khác:

| Luồng | Hướng | Cần cân nhắc |
| --- | --- | --- |
| Prometheus scrape | Ingress vào metrics port | Chỉ allow namespace/pod scraper |
| Export trace/metric | Egress từ server | Allow collector cụ thể và port cần dùng |
| DNS | Egress từ client/server | UDP/TCP 53 tới resolver phù hợp |
| Identity provider | Egress | Chỉ allow endpoint/port xác minh credential |
| Database/broker | Egress từ worker/service | Rule riêng theo workload và port |
| Ingress gateway | Ingress vào gRPC pod | Allow đúng gateway pod/namespace |

Nếu metrics listener dùng port khác `9090`, không gộp nó vào rule gRPC nếu scraper là một workload khác. Tách policy giúp quyền truy cập có phạm vi rõ ràng.

## 9. IPBlock, Service IP và giới hạn tính di động

`ipBlock` hữu ích cho CIDR ngoài cluster hoặc dải mạng cố định, nhưng thường không phải lựa chọn tốt để nhận diện pod trong cluster. Pod IP có thể thay đổi khi rollout hoặc reschedule; dùng namespace/pod selector cho workload nội bộ.

Khi áp dụng policy cho traffic đi qua NodePort, LoadBalancer, NAT hoặc ingress gateway, địa chỉ nguồn/đích quan sát được tại điểm enforcement có thể phụ thuộc CNI, kube-proxy mode và đường đi của traffic. Không giả định `ipBlock` luôn nhìn thấy IP client ban đầu. Với luồng production, xác minh bằng tài liệu CNI và flow log.

NetworkPolicy chuẩn không hỗ trợ FQDN selector portable. Một số CNI cung cấp policy mở rộng theo FQDN, nhưng đó là tính năng riêng của CNI và cần được quản lý như một dependency nền tảng.

## 10. Quy trình triển khai an toàn

Áp dụng policy theo từng bước:

1. Xác định listener port, namespace, pod labels, client, gateway, DNS và health/metrics traffic.
2. Liệt kê các luồng ingress/egress hiện tại từ manifest, service map và telemetry.
3. Kiểm tra CNI có hỗ trợ Kubernetes NetworkPolicy và semantics cần dùng.
4. Tạo allow policy hẹp cho luồng gRPC dự kiến.
5. Kiểm tra selector khớp đúng pod; selector sai có thể làm policy không chọn workload nào.
6. Áp dụng default-deny trong phạm vi nhỏ, sau đó xác minh từng luồng cần thiết.
7. Theo dõi connection failure, readiness, DNS và CNI flow log trong rollout.
8. Mở rộng policy sang namespace/workload tiếp theo sau khi đã kiểm chứng.

NetworkPolicy allow có tính cộng dồn. Trước rollout, audit mọi policy đang chọn pod để chắc chắn không còn rule rộng hơn ý định. Duy trì manifest trong GitOps để review thay đổi selector và port như một thay đổi bảo mật.

## 11. Kiểm thử kết nối gRPC

Kiểm tra cả client được phép và client không được phép. Trước hết xem policy và pod labels:

~~~bash
kubectl get networkpolicy -n catalog
kubectl describe networkpolicy allow-checkout-to-catalog-grpc -n catalog
kubectl get pods -n catalog --show-labels
kubectl get pods -n commerce --show-labels
~~~

Từ pod checkout được allow, kiểm tra TCP port:

~~~bash
nc -vz catalog-grpc.catalog.svc.cluster.local 9090
~~~

Sau đó gọi RPC bằng `grpcurl` với TLS/certificate phù hợp môi trường. Ví dụ dưới đây dùng plaintext chỉ cho cluster test đã cấu hình plaintext:

~~~bash
grpcurl -plaintext catalog-grpc.catalog.svc.cluster.local:9090 list
~~~

Lệnh `list` yêu cầu server bật reflection. Nếu production tắt reflection, gọi method cụ thể với proto descriptor hoặc `-proto` thay vì bật reflection chỉ để kiểm thử.

Lặp lại phép thử từ pod thuộc namespace không được allow. Kết nối phải bị chặn ở tầng mạng; xác minh cùng lúc DNS có phân giải được hay không để phân biệt lỗi DNS với lỗi policy. Nếu TCP timeout, kiểm tra CNI flow log hoặc policy trace để xác định rule nào drop traffic.

Một test thành công từ client được phép không đủ chứng minh policy least-privilege. Cần cả negative test từ workload không được phép và kiểm tra những luồng phụ như DNS, health probe, metrics, egress dependency.

## 12. Ma trận kiểm thử đề xuất

| Nguồn | Đích | Kết quả mong đợi |
| --- | --- | --- |
| `commerce/app=checkout` | `catalog/app=catalog-grpc:9090/TCP` | Allow |
| Pod khác trong `commerce` | `catalog/app=catalog-grpc:9090/TCP` | Deny nếu không có policy allow khác |
| Namespace không được phép | `catalog/app=catalog-grpc:9090/TCP` | Deny |
| `commerce/app=checkout` | CoreDNS UDP/TCP 53 | Allow |
| `commerce/app=checkout` | Port khác trên catalog pod | Deny nếu không có rule khác |
| Prometheus scraper | Metrics port | Allow theo policy metrics riêng |
| Kubelet/node | Probe port | Xác minh theo CNI và cấu hình cluster |
| Gateway được chọn | Backend gRPC port | Allow theo selector gateway |

Khi một kết nối bị từ chối, kiểm tra DNS, Service endpoints, port listener, NetworkPolicy selectors và CNI enforcement theo thứ tự. Không sửa bằng cách mở tất cả traffic; xác định đúng cạnh mạng bị thiếu rồi thêm rule hẹp.

## 13. Ghi nhớ và tự kiểm tra

**Network policy cho port gRPC** là cấu hình Layer 3/4 để giới hạn workload nào được kết nối tới listener TCP của Spring gRPC. Dùng default-deny kết hợp allow theo namespace/pod selector và destination port; nếu client egress bị cô lập, phải mở cả DNS và các dependency cần thiết. Policy không phân biệt RPC method, không mã hóa traffic và không xác thực principal, vì vậy vẫn cần TLS/mTLS cùng authentication/authorization ở các lớp phù hợp.

Tự kiểm tra:

1. Vì sao gRPC thường chỉ cần một TCP port cho nhiều RPC method?
2. Khi nào ingress policy của server và egress policy của client đều phải allow?
3. Hai selector trong cùng một peer item kết hợp theo AND hay OR?
4. Vì sao default-deny egress có thể làm DNS lookup thất bại?
5. Vì sao NetworkPolicy không thay thế TLS hoặc authorization?
6. Cần kiểm tra điều gì khi kubelet probe thất bại sau khi bật default-deny?
7. Vì sao cần negative test từ pod không được phép?

NetworkPolicy được thiết kế theo luồng thực tế giúp Spring gRPC chỉ nhận traffic từ workload cần thiết, giảm bề mặt tấn công và giữ các luồng vận hành quan trọng hoạt động ổn định.
