# Triển khai server và xác định phạm vi tài nguyên được đọc

Trong chương **Discovery Server** của module **SPRING_CLOUD_KUBERNETES**, triển khai server không chỉ là tạo một Deployment chạy được. Bạn còn phải xác định server dùng danh tính nào, được đọc loại tài nguyên nào, ở namespace nào và ai được nhận dữ liệu discovery qua HTTP.

Module hướng tới tích hợp ứng dụng Spring với Kubernetes qua DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer và Configuration Watcher. Với bài này, ta chỉ bật những phần cần cho discovery. Việc ứng dụng khác cần đọc cấu hình hoặc theo dõi ConfigMap không phải lý do để cấp thêm quyền tương ứng cho Discovery Server.

Sau bài học, bạn có thể:

- Phác họa luồng từ HTTP DiscoveryClient đến Kubernetes API.
- Triển khai server với ServiceAccount riêng và quyền đọc được giới hạn.
- Phân biệt namespace chứa server với namespace chứa dịch vụ cần khám phá.
- Đồng bộ cấu hình discovery, RBAC và lựa chọn Endpoints/EndpointSlice.
- Kiểm tra cả phạm vi được phép và phạm vi phải bị từ chối.
- Phân biệt Pod khỏe, quyền đọc đúng và danh mục discovery có dữ liệu đúng.

## 1. Xác định đúng trách nhiệm của server

Spring Cloud Kubernetes Discovery Server cung cấp HTTP API để ứng dụng lấy thông tin khám phá dịch vụ. HTTP DiscoveryClient dùng dữ liệu này để hiện thực giao diện DiscoveryClient phía ứng dụng. Server lấy thông tin từ Kubernetes; ứng dụng nghiệp vụ không cần tự đăng ký instance vào một kho riêng của server. Các endpoint được tài liệu hóa có GET /apps và GET /apps/{name}. [Tài liệu Discovery Server của Spring](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-discoveryserver.html).

~~~mermaid
flowchart LR
    C["Ứng dụng dùng HTTP DiscoveryClient"] -->|"HTTP discovery"| S["Service của Discovery Server"]
    S --> D["Pod Discovery Server"]
    D -->|"ServiceAccount và RBAC"| K["Kubernetes API"]
    K --> R["Service, Pod, EndpointSlice trong namespace cho phép"]
    C -->|"Lưu lượng nghiệp vụ tới đích đã chọn"| B["Dịch vụ nghiệp vụ"]
~~~

Đây là hai luồng khác nhau:

1. **Luồng khám phá:** client hỏi server để lấy danh sách dịch vụ hoặc instance.
2. **Luồng nghiệp vụ:** client hoặc thành phần cân bằng tải dùng thông tin đó để gọi đích.

Triển khai Discovery Server không tự mở đường mạng từ client đến địa chỉ instance. Một ứng dụng ngoài cluster có thể gọi được HTTP API của server nhưng vẫn không kết nối được IP Pod mà API trả về. Thiết kế định tuyến, TLS và chính sách mạng cho luồng nghiệp vụ phải được kiểm tra riêng.

Trước khi bổ sung server, xác định nhu cầu của ứng dụng. Nếu Kubernetes DNS và Service đã đáp ứng cách gọi dịch vụ, một tầng HTTP discovery có thể không cần thiết. Nếu cần giao diện DiscoveryClient qua HTTP để tập trung việc truy cập Kubernetes API, server trở thành một thành phần có quyền đọc cần được vận hành rõ ràng.

## 2. Ba phạm vi không được đánh đồng

Giả sử server chạy trong namespace platform-discovery nhưng cần khám phá dịch vụ của team-orders.

| Phạm vi | Câu hỏi | Ví dụ của bài |
| --- | --- | --- |
| Nơi chạy server | Pod và ServiceAccount tồn tại ở đâu? | platform-discovery |
| Phạm vi đọc Kubernetes API | Danh tính của server được đọc gì, ở đâu? | Pod, Service, EndpointSlice trong team-orders |
| Phạm vi dữ liệu trả qua HTTP | Người gọi nào được nhận danh mục nào? | Các client nội bộ được cho phép gọi server |

Namespace của Deployment không tự giới hạn mọi truy vấn mà chương trình có thể thực hiện. Ngược lại, đặt danh sách namespace trong cấu hình không tự tạo quyền đọc.

Có thể hình dung dữ liệu discovery dự kiến là những đối tượng thuộc namespace được chọn, được RBAC cho phép đọc và đáp ứng điều kiện khám phá. Mô hình này chỉ mô tả ý định khi quá trình đọc và đồng bộ hoạt động bình thường. Khi thiếu quyền, server có thể báo lỗi hoặc không khởi động; không nên giả định nó luôn bỏ qua phần bị cấm và trả về một tập con hoàn chỉnh.

Ví dụ cần phân biệt:

- Cấu hình chỉ đọc team-orders nhưng tài khoản có quyền trên cả cluster: kết quả trước mắt có thể đúng, nhưng quyền vẫn quá rộng.
- Cấu hình đọc team-orders và team-payments nhưng RBAC chỉ cho team-orders: cấu hình và quyền mâu thuẫn.
- RBAC chỉ cho team-orders nhưng HTTP API mở cho mọi workload: quyền Kubernetes đúng chưa giải quyết được việc ai nhận dữ liệu discovery.

RBAC Kubernetes kiểm tra danh tính thực hiện yêu cầu tới API server. Với kiến trúc này, đó là ServiceAccount của Discovery Server. Không được mặc định rằng quyền Kubernetes của từng HTTP client sẽ được dùng lại để lọc response cho client đó.

## 3. Lập hợp đồng đọc trước khi viết manifest

Bài thực hành dùng hợp đồng sau:

| Thành phần | Giá trị dự kiến |
| --- | --- |
| Namespace của server | platform-discovery |
| ServiceAccount | discovery-reader |
| Namespace được khám phá lúc đầu | team-orders |
| Namespace ngoài phạm vi kiểm tra | team-payments |
| Nguồn địa chỉ instance | EndpointSlice |
| Loại tài nguyên được đọc | services, pods, endpointslices |
| Thao tác | get, list, watch |
| Secret và ConfigMap | Không cấp quyền cho nhiệm vụ discovery này |
| Quyền thay đổi workload | Không cấp |
| Cách đưa HTTP API vào mạng | Service kiểu ClusterIP |

Đây là lựa chọn cho một bài thực hành, không phải danh sách quyền áp dụng cho mọi image hay tính năng mở rộng.

Tài liệu server của Spring liệt kê Pod, Service, Endpoint và các quyền đọc tương ứng. Khi bật chế độ EndpointSlice, cần đối chiếu khả năng của phiên bản đã chọn và thay quyền đọc nguồn endpoint cho phù hợp. Không gộp mọi loại tài nguyên có thể gặp vào một Role chỉ để tránh lỗi quyền. [Quyền của Discovery Server](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-discoveryserver.html), [thuộc tính discovery](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

Ba thao tác đọc có mục đích khác nhau:

| Thao tác | Vai trò trong một cơ chế theo dõi tài nguyên |
| --- | --- |
| get | Đọc một đối tượng cụ thể |
| list | Lấy tập đối tượng, thường dùng để xây dựng trạng thái ban đầu |
| watch | Nhận thay đổi sau thời điểm theo dõi |

Chỉ thử một lệnh get thành công chưa chứng minh server có thể tạo danh mục và cập nhật danh mục khi Pod thay đổi.

Không cấp quyền đọc Secret chỉ vì server chạy trong Kubernetes. Nếu server được bổ sung cơ chế nạp cấu hình qua API, phải phân tích quyền cho chức năng đó như một nhu cầu riêng. Configuration Watcher cũng là một vai trò riêng, không phải quyền mặc định cần thêm vào server discovery.

## 4. Chọn phiên bản và nguồn endpoint nhất quán

Trước khi dùng manifest, ghi nhận:

1. Phiên bản Spring Cloud Kubernetes của server và HTTP client.
2. Tag hoặc digest image đã được nhóm triển khai xác nhận.
3. Cluster có hỗ trợ API EndpointSlice cần dùng hay không.
4. Chế độ endpoint mà server thực sự được cấu hình sử dụng.
5. Cổng HTTP, cổng quản lý và đường dẫn probe của image đó.

Không lấy một tag cũ trong ví dụ tài liệu rồi xem đó là lựa chọn mặc định cho mọi dự án. Trong manifest bên dưới, REPLACE_WITH_VALIDATED_TAG là chỗ bắt buộc thay bằng tag có thật đã được kiểm tra tương thích. Manifest chưa thể dùng nguyên trạng để kéo image thành công.

Thuộc tính spring.cloud.kubernetes.discovery.use-endpoint-slices lựa chọn EndpointSlice thay cho Endpoints khi implementation hỗ trợ. Ví dụ của bài đặt rõ giá trị true để quyền và cấu hình cùng theo một chế độ. [Danh sách thuộc tính Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

| Chế độ | Resource đọc địa chỉ | API group trong RBAC |
| --- | --- | --- |
| Endpoints | endpoints | Chuỗi rỗng, tức core API group |
| EndpointSlice | endpointslices | discovery.k8s.io |

EndpointSlice là tài nguyên có namespace. Một Service có thể gắn với nhiều slice; khi chẩn đoán, cần xem các slice liên quan thay vì chỉ tìm một đối tượng trùng tên Service. [Tài liệu EndpointSlice của Kubernetes](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/).

Không cấp endpointslices trong apiGroups: [""] và không cấp services trong apiGroups: ["apps"]. Tên API group trong quy tắc phải khớp tài nguyên thật; apiVersion của Deployment không quyết định API group của các tài nguyên server đọc.

## 5. Manifest triển khai giới hạn ở một namespace nghiệp vụ

Ví dụ dưới đây dành cho môi trường thực hành. Namespace platform-discovery và team-orders cần tồn tại trước; team-payments cần tồn tại nếu dùng các phép kiểm tra ngoài phạm vi ở phần sau. Không cần di chuyển workload nghiệp vụ sang namespace của server.

### 5.1. ServiceAccount, Role và RoleBinding

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: discovery-reader
  namespace: platform-discovery
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: discovery-resource-reader
  namespace: team-orders
rules:
  - apiGroups: [""]
    resources: ["services", "pods"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: discovery-resource-reader
  namespace: team-orders
subjects:
  - kind: ServiceAccount
    name: discovery-reader
    namespace: platform-discovery
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: discovery-resource-reader
~~~

Chú ý hai namespace có mục đích khác nhau:

- metadata.namespace của Role và RoleBinding là team-orders: nơi cấp quyền đọc tài nguyên.
- subjects[].namespace là platform-discovery: nơi ServiceAccount được tham chiếu tồn tại.

RoleBinding có thể cấp quyền trong namespace của nó cho một ServiceAccount nằm ở namespace khác. Role được roleRef tham chiếu phải nằm cùng namespace với RoleBinding; nếu tham chiếu ClusterRole thì đó là đối tượng cấp cluster được tái sử dụng trong namespace này. [Quy tắc RoleBinding của Kubernetes](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

### 5.2. Deployment và Service

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: discovery-server
  namespace: platform-discovery
spec:
  replicas: 1
  selector:
    matchLabels:
      app: discovery-server
  template:
    metadata:
      labels:
        app: discovery-server
    spec:
      serviceAccountName: discovery-reader
      automountServiceAccountToken: true
      containers:
        - name: discovery-server
          image: springcloud/spring-cloud-kubernetes-discoveryserver:REPLACE_WITH_VALIDATED_TAG
          ports:
            - name: http
              containerPort: 8761
          env:
            - name: SPRING_APPLICATION_JSON
              value: |
                {
                  "server": {
                    "port": 8761
                  },
                  "management": {
                    "endpoint": {
                      "health": {
                        "probes": {
                          "enabled": true
                        }
                      }
                    }
                  },
                  "spring": {
                    "cloud": {
                      "kubernetes": {
                        "discovery": {
                          "all-namespaces": false,
                          "namespaces": ["team-orders"],
                          "use-endpoint-slices": true
                        }
                      }
                    }
                  }
                }
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 36
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
          resources:
            requests:
              cpu: "100m"
              memory: "256Mi"
            limits:
              memory: "512Mi"
---
apiVersion: v1
kind: Service
metadata:
  name: discovery-server
  namespace: platform-discovery
spec:
  type: ClusterIP
  selector:
    app: discovery-server
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

SPRING_APPLICATION_JSON là cơ chế đưa một cấu trúc thuộc tính JSON vào Spring Environment. Nó giúp ví dụ thể hiện trực tiếp danh sách namespace và các tên thuộc tính có dấu gạch nối mà không cần một ConfigMap riêng. Đây là cấu hình không chứa bí mật. [Cấu hình ngoài của Spring Boot](https://docs.spring.io/spring-boot/reference/features/external-config.html).

Cấu hình namespace nằm trên **server**. Với HTTP DiscoveryClient, thay danh sách namespace ở ứng dụng gọi không làm một server từ xa tự đổi phạm vi đọc. [Cấu hình phạm vi discovery của Spring](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

ServiceAccount của server cần thông tin xác thực khi gọi Kubernetes API. Ví dụ bật việc gắn token vào Pod, không chép token tĩnh vào biến môi trường hoặc image. Nếu môi trường dùng cách cung cấp danh tính khác, cấu hình phải được điều chỉnh theo cơ chế đó. [ServiceAccount của Kubernetes](https://kubernetes.io/docs/concepts/security/service-accounts/).

Các giới hạn CPU, bộ nhớ và khoảng probe chỉ là điểm bắt đầu cho môi trường thực hành. Cần đo thời gian khởi động, số đối tượng được theo dõi và tải HTTP trước khi chọn giá trị cho vận hành thực tế.

### 5.3. Kiểm tra những liên kết dễ sai

Trước khi áp dụng, đối chiếu:

- Pod dùng đúng serviceAccountName: discovery-reader.
- Service chọn đúng label app của Pod.
- Service port 80 chuyển tới cổng http, tức 8761 trong container.
- Cấu hình namespace là team-orders, phù hợp RoleBinding.
- Chế độ EndpointSlice đi kèm quyền endpointslices trong discovery.k8s.io.
- Image cung cấp các endpoint Actuator được probe sử dụng.

ClusterIP là cách đưa server vào mạng nội bộ cluster trong ví dụ. Nó không phải một chính sách xác thực người gọi. Cần thiết kế quyền truy cập HTTP theo mô hình mạng và bảo vệ API của hệ thống.

## 6. Hiểu đúng các probe

Startup probe cho tiến trình thời gian khởi động. Readiness quyết định thời điểm Pod sẵn sàng nhận lưu lượng qua Service. Liveness kiểm tra trạng thái sống để Kubernetes quyết định có khởi động lại container hay không. [Các loại probe của Kubernetes](https://kubernetes.io/docs/concepts/workloads/pods/probes/).

Các endpoint /actuator/health/liveness và /actuator/health/readiness phản ánh nhóm sức khỏe do Spring Boot cung cấp. Không mặc định xem readiness thành công là bằng chứng server đã đọc đúng mọi namespace hay danh mục discovery không rỗng. [Health probe của Spring Boot](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).

Ví dụ:

- Pod Ready nhưng cấu hình chọn nhầm namespace: HTTP hoạt động, danh mục vẫn sai.
- Pod liên tục khởi động lại vì thiếu quyền khi tạo cache: cần xem lỗi API và cấu hình, không chỉ tăng thời gian probe.
- Kubernetes API tạm mất kết nối: nếu gắn mọi lỗi phụ thuộc ngoài vào liveness, có thể tạo vòng khởi động lại mà không xử lý được nguyên nhân.

Quyết định một tình trạng discovery suy giảm có làm server mất readiness hay không là chính sách vận hành cần xác định. Nếu có yêu cầu đó, phải dùng chỉ báo phù hợp với implementation; không suy ra rằng hai probe mặc định đã kiểm tra toàn bộ điều kiện nghiệp vụ.

## 7. Kiểm tra RBAC trước khi kết luận discovery bị lỗi

Các lệnh trong bài là hướng dẫn thực hành để người học chạy trong cluster được phép sử dụng, không phải kết quả đã được thực thi ở một cluster cụ thể.

### 7.1. Kiểm tra quyền theo đúng danh tính server

~~~powershell
$readerIdentity = "system:serviceaccount:platform-discovery:discovery-reader"

kubectl auth can-i list services -n team-orders --as=$readerIdentity
kubectl auth can-i watch pods -n team-orders --as=$readerIdentity
kubectl auth can-i list endpointslices.discovery.k8s.io -n team-orders --as=$readerIdentity
kubectl auth can-i watch endpointslices.discovery.k8s.io -n team-orders --as=$readerIdentity

kubectl auth can-i list services -n team-payments --as=$readerIdentity
kubectl auth can-i list secrets -n team-orders --as=$readerIdentity
kubectl auth can-i create deployments.apps -n team-orders --as=$readerIdentity
kubectl auth can-i list services --all-namespaces --as=$readerIdentity
~~~

Kỳ vọng của hợp đồng thực hành:

| Nhóm kiểm tra | Kết quả dự kiến |
| --- | --- |
| Đọc các resource đã cấp trong team-orders | yes |
| Đọc Service trong team-payments | no |
| Đọc Secret trong team-orders | no |
| Tạo Deployment trong team-orders | no |
| Liệt kê Service trên toàn cluster | no |

Cần kiểm tra đủ get, list, watch cho các resource thực sự sử dụng. Đoạn lệnh trên minh họa các trường hợp quan trọng, không thay thế toàn bộ ma trận quyền.

Người chạy lệnh có --as phải được phép impersonate danh tính tương ứng. Nếu công cụ báo lỗi impersonation, đó chưa phải kết luận ServiceAccount thiếu quyền discovery. Nhờ người có quyền kiểm tra thực hiện phép thử hoặc dùng cơ chế kiểm chứng danh tính được môi trường cho phép.

RBAC có tính cộng dồn: một binding mới không thu hồi quyền đã được cấp từ binding khác. Nếu một phép thử dự kiến no lại trả yes, cần tìm quyền bổ sung đang áp dụng cho danh tính hoặc nhóm của danh tính đó; sửa riêng Role vừa tạo có thể chưa đủ. [Cơ chế cấp quyền RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

### 7.2. Kiểm tra trạng thái triển khai và nguồn dữ liệu

~~~powershell
kubectl -n platform-discovery rollout status deployment/discovery-server
kubectl -n platform-discovery get pods -l app=discovery-server
kubectl -n platform-discovery logs deployment/discovery-server --tail=100

kubectl -n team-orders get services
kubectl -n team-orders get endpointslices -l kubernetes.io/service-name=orders-api
~~~

orders-api là tên Service minh họa. Cần thay bằng một Service có thật trong namespace thực hành.

Các lệnh get ở trên thường chạy bằng danh tính của người vận hành. Chúng giúp kiểm tra dữ liệu nguồn nhưng không chứng minh server có cùng quyền với người đó. Phép kiểm tra theo ServiceAccount và kiểm tra dữ liệu nguồn phải được đọc cùng nhau.

Với lỗi Forbidden, ghi nhận ít nhất: danh tính, verb, API group, resource và namespace trong thông báo. Ví dụ, quyền list services trong team-orders không bù cho quyền watch endpointslices còn thiếu.

### 7.3. Kiểm tra đầu ra HTTP

Có thể mở cổng tạm cho phiên kiểm tra có quyền:

~~~powershell
kubectl -n platform-discovery port-forward service/discovery-server 18761:80
~~~

Giữ tiến trình này chạy, rồi dùng một terminal khác:

~~~powershell
curl.exe --fail http://localhost:18761/actuator/health/readiness
curl.exe --fail http://localhost:18761/apps
curl.exe --fail http://localhost:18761/apps/orders-api
~~~

Port-forward chỉ phục vụ phiên kiểm tra; không dùng nó làm kiến trúc truy cập production.

Đừng chỉ quan sát mã HTTP 200. Hãy đối chiếu Service dự kiến, namespace trong dữ liệu nếu response của phiên bản có trường này, địa chỉ, cổng và số instance. Có thể cần chờ quá trình đồng bộ sau khi workload thay đổi; một lần đọc ngay sau rollout chưa mô tả toàn bộ hành vi cập nhật.

Một bài thử có sức phân biệt gồm:

1. Chọn Service có endpoint sẵn sàng trong team-orders.
2. Xác nhận server trả dữ liệu phù hợp cho Service đó.
3. Chọn một Service khác trong team-payments.
4. Xác nhận nó không xuất hiện trong danh mục của server ở cấu hình ban đầu.
5. Trong môi trường thực hành, tạo thay đổi có kiểm soát ở workload thuộc team-orders và quan sát sự cập nhật.

Trường hợp ngoài phạm vi không được mặc định phải trả một mã HTTP cụ thể. Điều cần kiểm tra ở bài này là dữ liệu ngoài hợp đồng không được công bố; cách biểu diễn dịch vụ không tìm thấy phải theo API của phiên bản đang dùng.

## 8. Mở rộng sang hai namespace mà không mở toàn cluster

Giả sử hợp đồng mới cho phép server đọc thêm team-payments.

Cần thay đổi đồng thời hai mặt:

1. Thêm team-payments vào cấu hình danh sách namespace trên server.
2. Cấp đúng các quyền đọc cần thiết trong namespace team-payments cho cùng ServiceAccount.

Phần discovery trong SPRING_APPLICATION_JSON trở thành:

~~~json
{
  "all-namespaces": false,
  "namespaces": ["team-orders", "team-payments"],
  "use-endpoint-slices": true
}
~~~

Đây là phần nằm dưới spring.cloud.kubernetes.discovery trong JSON đầy đủ, không phải toàn bộ biến môi trường.

Bổ sung Role và RoleBinding:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: discovery-resource-reader
  namespace: team-payments
rules:
  - apiGroups: [""]
    resources: ["services", "pods"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: discovery-resource-reader
  namespace: team-payments
subjects:
  - kind: ServiceAccount
    name: discovery-reader
    namespace: platform-discovery
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: discovery-resource-reader
~~~

Sau khi rollout cấu hình mới, kiểm tra quyền và dữ liệu của cả hai namespace, đồng thời giữ một namespace thứ ba làm trường hợp ngoài phạm vi.

Khi nhiều namespace dùng chung một bộ quy tắc, có thể khai báo một ClusterRole chỉ đọc rồi tạo RoleBinding tại từng namespace được duyệt. ClusterRole định nghĩa bộ quyền dùng lại; RoleBinding giới hạn nơi cấp bộ quyền đó. Không cần chuyển sang ClusterRoleBinding chỉ vì có từ hai namespace trở lên. [Phạm vi RoleBinding và ClusterRoleBinding](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Nếu có các Service trùng tên giữa hai namespace, cần kiểm tra cách API và client của phiên bản đang dùng định danh hoặc tập hợp kết quả. Việc thêm quyền đọc không tự giải quyết sự mơ hồ về tên dịch vụ. Hãy đưa quy ước tên hoặc cách tách server vào thiết kế trước khi client phụ thuộc vào kết quả.

## 9. Vì sao all-namespaces cần quyết định riêng?

Danh sách namespace tường minh giúp mô tả phạm vi dự kiến. Khi bật all-namespaces, phạm vi có thể bao gồm các namespace xuất hiện sau này nếu danh tính cũng có quyền đọc toàn cluster. Bài toán khi đó chuyển từ quản lý một danh sách đã duyệt sang quản lý khả năng quan sát tài nguyên ở quy mô cluster.

Không xử lý một lỗi thiếu quyền bằng cách bật all-namespaces và cấp cluster-admin. Cần xác định yêu cầu nào đang thất bại và có đúng là server phải đọc ngoài danh sách ban đầu hay không.

Trước khi chọn phạm vi toàn cluster, trả lời:

- Người sở hữu server có chịu trách nhiệm cho mọi namespace mà nó có thể đọc không?
- Danh mục của các đội có được phép dùng chung cho cùng nhóm HTTP client không?
- Số Service, Pod và endpoint tăng lên sẽ ảnh hưởng bộ nhớ, đồng bộ và thời gian khởi động như thế nào?
- Namespace mới có tự động trở thành nguồn discovery được chấp nhận không?
- Có cần tách server theo môi trường hoặc nhóm sử dụng không?

Các bộ lọc theo label hoặc điều kiện discovery có thể giúp chọn dữ liệu cần trả, nhưng không thay thế ranh giới quyền của Kubernetes. Nếu tài khoản vẫn có quyền đọc toàn bộ Service trong một namespace, một bộ lọc trong ứng dụng không biến quyền đó thành quyền chỉ đọc những Service có label được chọn.

Tương tự, resourceNames trong RBAC không phải lối tắt chắc chắn để một discovery client theo dõi tùy ý từng Service. Yêu cầu list/watch bị giới hạn theo tên đòi hỏi field selector phù hợp; không tự thêm cấu hình này rồi giả định client sẽ gửi truy vấn tương ứng. [Giới hạn theo tên tài nguyên trong RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

## 10. Bảo vệ đầu ra và tách quyền theo vai trò

Quyền đọc của server là một nửa hợp đồng. Nửa còn lại là quyền gọi HTTP API và cách dùng dữ liệu được trả.

| Thành phần | Trách nhiệm cần xác định |
| --- | --- |
| Discovery Server | Đọc tài nguyên phục vụ discovery, công bố danh mục cho client được phép |
| Ứng dụng dùng HTTP DiscoveryClient | Gọi API discovery; không mặc định cần quyền đọc Kubernetes API cho riêng luồng này |
| Spring Cloud LoadBalancer | Dùng danh sách instance theo cấu hình của ứng dụng; không tự bảo đảm đường mạng tới instance |
| Thành phần đọc ConfigMap/Secret | Có danh tính và quyền theo nhu cầu nạp cấu hình |
| Configuration Watcher | Có phạm vi theo dõi và cơ chế thông báo cập nhật riêng |

Một server đọc được nhiều namespace rồi trả cùng danh mục cho mọi client sẽ không tự có cách ly theo tenant. Nếu cần các nhóm client nhìn thấy các phạm vi khác nhau, phải chọn một thiết kế rõ ràng: tách server theo phạm vi, hoặc bổ sung lớp kiểm soát đã được thiết kế và kiểm chứng cho API đó.

Không đưa password, token hoặc dữ liệu cá nhân vào label/annotation với kỳ vọng chỉ cần chặn quyền đọc Secret là đủ. Metadata có thể theo luồng discovery ra ngoài nơi lưu ban đầu. Chỉ công bố các trường thực sự cần cho việc chọn và gọi dịch vụ.

Việc server cần egress đến Kubernetes API và client cần ingress đến HTTP API của server cũng phải được phản ánh trong chính sách mạng nếu cluster áp dụng hạn chế. Một lỗi timeout do mạng khác với Forbidden do phân quyền; mở thêm RBAC không xử lý được timeout mạng.

## 11. Chẩn đoán theo triệu chứng

| Triệu chứng | Điều cần kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| Forbidden khi list/watch | ServiceAccount thực tế, API group, resource, namespace | Bổ sung đúng quyền còn thiếu trong phạm vi đã duyệt |
| Server chạy nhưng danh mục trống | Namespace cấu hình, dữ liệu Service/endpoint nguồn, log đồng bộ | So khớp cấu hình với namespace có workload |
| Service xuất hiện nhưng không có instance dùng được | EndpointSlice, trạng thái sẵn sàng, lựa chọn cổng | Kiểm tra workload và địa chỉ/cổng nguồn |
| Chỉ thấy namespace của server | Cấu hình chưa được đặt ở server hoặc chưa rollout | Kiểm tra cấu hình hiệu lực của Pod server |
| Gọi được /apps nhưng không gọi được nghiệp vụ | Khả năng định tuyến tới địa chỉ được trả | Xử lý đường mạng và mô hình truy cập đích |
| Thiếu dữ liệu sau khi chuyển EndpointSlice | Phiên bản hỗ trợ, thuộc tính hiệu lực, quyền discovery.k8s.io | Đồng bộ chế độ và quyền |
| Một quyền dự kiến bị cấm lại được phép | Những binding khác của tài khoản và nhóm liên quan | Loại bỏ nguồn cấp quyền thừa theo quy trình vận hành |
| Kết quả khác nhau sau rollout nhiều replica | Phiên bản image, cấu hình, log và quá trình đồng bộ từng Pod | Xác nhận các replica dùng cùng hợp đồng đọc |

Không tăng replica để chữa sai namespace hoặc thiếu quyền. Mỗi replica mới cũng cần đọc và đồng bộ tài nguyên. Chỉ tăng số lượng khi đã hiểu hành vi đồng bộ, lượng tài nguyên và nhu cầu sẵn sàng của server.

Khi thu hẹp phạm vi, cần bỏ namespace khỏi cấu hình, điều chỉnh các binding liên quan và xác minh đầu ra sau khi trạng thái đã được đồng bộ hoặc server đã được rollout phù hợp. Thu hồi quyền API không bảo đảm mọi bản sao dữ liệu cũ ở cache và client lập tức biến mất.

## 12. Tiêu chí hoàn thành bài thực hành

Một triển khai đạt mục tiêu khi có bằng chứng cho các điểm sau:

- Image có phiên bản được xác nhận; server và client được kiểm tra tương thích.
- Deployment dùng ServiceAccount riêng đúng tên và namespace.
- Danh sách namespace trên server trùng với hợp đồng đọc.
- Loại endpoint đã chọn khớp API group và resource được cấp quyền.
- Các phép thử đọc cần thiết trả kết quả được phép.
- Các phép thử ngoài namespace, đọc Secret và ghi workload trả kết quả bị từ chối theo hợp đồng.
- Probe hoạt động, đồng thời dữ liệu HTTP được đối chiếu với tài nguyên nguồn.
- Thay đổi endpoint trong phạm vi được phản ánh theo hành vi đồng bộ dự kiến.
- Client có đường mạng phù hợp tới server và các đích nghiệp vụ cần dùng.
- Quyền gọi HTTP API và phạm vi dữ liệu công bố có người chịu trách nhiệm.

Kết quả cần lưu cho việc vận hành là một hợp đồng cụ thể: server nào, danh tính nào, đọc tài nguyên nào, trong namespace nào và phục vụ nhóm client nào. Khi một trong các yếu tố đó thay đổi, cập nhật cấu hình, quyền và phép kiểm chứng tương ứng trước khi xem việc triển khai đã hoàn tất.