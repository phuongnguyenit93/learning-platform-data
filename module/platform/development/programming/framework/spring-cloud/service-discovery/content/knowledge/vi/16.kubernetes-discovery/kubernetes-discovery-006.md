# Trạng thái readiness và danh sách endpoint sẵn sàng

## 1. Readiness có vai trò gì trong service discovery?

Trong Kubernetes, một Pod có thể đang chạy nhưng chưa sẵn sàng nhận request. Ví dụ, ứng dụng vừa khởi động và còn tải cấu hình, kết nối database hoặc nạp dữ liệu ban đầu. Nếu Service gửi traffic đến Pod trong giai đoạn này, request có thể thất bại dù container vẫn ở trạng thái Running.

Kubernetes dùng **readiness** để biểu thị Pod có nên nhận traffic hay không. Kết quả readiness được phản ánh trong trạng thái Pod và danh sách endpoint mà Service công bố. Nhờ đó, client hoặc proxy có thể chọn những địa chỉ đã sẵn sàng.

Trong Spring Cloud Service Discovery, cần phân biệt ba khái niệm:

- **Pod readiness:** trạng thái sẵn sàng của một Pod theo kết quả probe và readiness gate.
- **Service endpoint:** địa chỉ IP/port của Pod được Service quản lý, cùng các điều kiện như ready, serving và terminating.
- **Discovery result:** danh sách instance mà ứng dụng lấy từ Kubernetes API hoặc abstraction DiscoveryClient.

Readiness giúp loại Pod chưa sẵn sàng khỏi tập endpoint nhận traffic thông thường. Nó không chứng minh mọi thao tác nghiệp vụ đều thành công và cũng không thay thế timeout, retry hay health check ở phía gọi dịch vụ.

## 2. Readiness probe, liveness probe và startup probe

Kubernetes có ba loại probe thường gặp. Mỗi probe trả lời một câu hỏi khác nhau:

| Probe | Câu hỏi | Khi thất bại |
|---|---|---|
| Readiness | Container có thể nhận traffic ngay lúc này không? | Pod được đánh dấu NotReady; endpoint thông thường không được chọn để nhận traffic |
| Liveness | Container còn hoạt động hay đã rơi vào trạng thái cần khởi động lại? | Kubelet khởi động lại container sau ngưỡng failure |
| Startup | Ứng dụng đã hoàn tất khởi động ban đầu chưa? | Kubelet tiếp tục kiểm tra startup; liveness/readiness được trì hoãn cho đến khi startup thành công |

Readiness probe thất bại không tự khởi động lại container. Container vẫn có thể chạy, xử lý tác vụ nội bộ hoặc phục hồi dependency rồi trở lại Ready khi probe thành công.

Liveness probe không nên kiểm tra các dependency bên ngoài theo cách khiến một sự cố database làm Kubernetes khởi động lại hàng loạt Pod. Readiness phù hợp hơn để tạm ngừng đưa traffic vào Pod không thể phục vụ request.

## 3. Cấu hình readiness probe cho ứng dụng Spring Boot

Một ứng dụng Spring Boot thường cung cấp health endpoint qua Spring Boot Actuator. Khi bật health endpoint, có thể cấu hình readiness probe HTTP trỏ đến nhóm trạng thái readiness:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health
~~~

Trong Kubernetes Deployment, cấu hình readiness probe có thể như sau:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: payment-service
  template:
    metadata:
      labels:
        app: payment-service
    spec:
      containers:
        - name: payment-service
          image: example/payment-service:2.5.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            initialDelaySeconds: 5
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
~~~

Các tham số trên chỉ là ví dụ. Hãy điều chỉnh thời gian khởi động, độ trễ phản hồi và ngưỡng lỗi theo ứng dụng. Nếu ứng dụng cần thời gian khởi động dài, cân nhắc startup probe để readiness và liveness không đánh giá container quá sớm.

### 3.1. Chọn health indicator cho readiness

Spring Boot Actuator có thể cung cấp các health group như liveness và readiness. Ứng dụng nên đưa vào readiness group những điều kiện thật sự quyết định khả năng nhận request.

Ví dụ:

- Ứng dụng không thể xử lý request nếu không tải được cấu hình bắt buộc.
- Một service phụ thuộc database đồng bộ có thể cần kiểm tra khả năng kết nối database.
- Một worker không nhận HTTP traffic có thể cần tiêu chí readiness khác với một web API.

Không nên đưa mọi dependency tùy chọn vào readiness. Nếu một dịch vụ phụ trợ không thiết yếu tạm thời lỗi mà Pod vẫn có thể xử lý phần lớn request, đánh dấu toàn bộ Pod NotReady có thể làm giảm capacity không cần thiết.

## 4. Từ Pod readiness đến EndpointSlice

Service Kubernetes chọn Pod thông qua label selector. EndpointSlice controller theo dõi các Pod khớp selector và tạo hoặc cập nhật EndpointSlice chứa địa chỉ endpoint.

Khi readiness của Pod thay đổi:

1. Kubelet cập nhật trạng thái Pod sau khi probe được đánh giá.
2. Pod condition Ready thay đổi.
3. EndpointSlice controller quan sát thay đổi của Pod.
4. Điều kiện endpoint trong EndpointSlice được cập nhật.
5. Kube-proxy, ingress controller hoặc client dùng Kubernetes API có thể cập nhật tập địa chỉ mà chúng sử dụng.

~~~mermaid
flowchart TD
    PROBE[Readiness probe của container] --> POD[Pod condition Ready]
    POD --> CTRL[EndpointSlice controller]
    CTRL --> SLICE[EndpointSlice conditions và addresses]
    SLICE --> PROXY[Kube-proxy / Ingress / Gateway]
    SLICE --> DISC[Spring Cloud Kubernetes Discovery]
    PROXY --> TRAFFIC[Traffic đến endpoint phù hợp]
    DISC --> CLIENT[DiscoveryClient / LoadBalancer]
~~~

EndpointSlice là API hiện đại để biểu diễn các endpoint của Service. Kubernetes vẫn có tài nguyên Endpoints dạng cũ để tương thích, nhưng EndpointSlice phù hợp hơn khi có nhiều endpoint hoặc cần phân chia danh sách thành nhiều slice.

## 5. Đọc điều kiện endpoint

Một endpoint trong EndpointSlice có thể có các điều kiện:

| Điều kiện | Ý nghĩa |
|---|---|
| ready | Endpoint sẵn sàng nhận traffic theo quy tắc của Service |
| serving | Endpoint hiện đang phục vụ; hữu ích khi phân biệt trạng thái phục vụ với quá trình kết thúc |
| terminating | Endpoint đang trong quá trình chấm dứt |

Trường ready có thể không được ghi rõ trong một số phản hồi cũ hoặc tình huống tương thích. Khi điều kiện ready không được đặt, client cần áp dụng quy tắc mặc định của API thay vì tự coi giá trị thiếu là false.

Endpoint đang terminating có thể vẫn được giữ trong EndpointSlice trong thời gian graceful shutdown. Tùy chính sách và phiên bản, endpoint có thể không còn được xem là ready cho traffic mới nhưng vẫn được đánh dấu serving trong lúc hoàn tất các kết nối hiện có.

Với Service có thiết lập publishNotReadyAddresses, endpoint có thể được công bố ngay cả khi Pod chưa Ready. Đây là hành vi có chủ đích trong một số hệ thống peer discovery hoặc bootstrap; không bật tùy chọn này cho Service HTTP thông thường nếu muốn readiness loại Pod chưa sẵn sàng khỏi traffic.

## 6. Service selector và danh sách endpoint

Ví dụ Service chọn các Pod có label app=payment-service:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: payment-service
spec:
  selector:
    app: payment-service
  ports:
    - name: http
      port: 80
      targetPort: http
  type: ClusterIP
~~~

Deployment phải gắn label tương ứng lên Pod template. Nếu selector không khớp label, Service sẽ không có endpoint dù Pod đang Running và Ready.

Service port và container port có thể khác nhau. Trong ví dụ, client gọi port 80 của Service, còn traffic được chuyển đến container port có tên http (8080). Khi xem EndpointSlice, cần kiểm tra port đích được công bố, không suy luận rằng nó luôn bằng Service port.

### 6.1. Kiểm tra bằng kubectl

Liệt kê Service:

~~~bash
kubectl get service payment-service
~~~

Đọc EndpointSlice:

~~~bash
kubectl get endpointslices -l kubernetes.io/service-name=payment-service
~~~

Xem chi tiết địa chỉ và điều kiện:

~~~bash
kubectl describe endpointslice -l kubernetes.io/service-name=payment-service
~~~

Đọc Pod và readiness:

~~~bash
kubectl get pods -l app=payment-service
kubectl describe pod <pod-name>
~~~

Để xem JSON có cấu trúc:

~~~bash
kubectl get endpointslices -l kubernetes.io/service-name=payment-service -o yaml
~~~

Trong output, kiểm tra:

- addresses: địa chỉ IP của endpoint.
- ports: port đích được công bố.
- conditions.ready: endpoint có sẵn sàng hay không.
- conditions.serving: endpoint có đang phục vụ hay không.
- conditions.terminating: endpoint có đang kết thúc hay không.
- targetRef: Pod hoặc đối tượng mà endpoint đại diện.

## 7. EndpointSlice và tài nguyên Endpoints cũ

Lệnh sau vẫn thường được dùng để xem danh sách endpoint tương thích:

~~~bash
kubectl get endpoints payment-service
~~~

Tài nguyên Endpoints cũ có thể hiển thị các địa chỉ trong subsets:

- addresses: địa chỉ endpoint được xem là sẵn sàng.
- notReadyAddresses: địa chỉ chưa sẵn sàng.
- ports: port được Service công bố cho endpoint.

EndpointSlice chia danh sách thành các slice nhỏ và hỗ trợ các điều kiện endpoint phong phú hơn. Khi debug Kubernetes hiện đại, nên kiểm tra EndpointSlice; có thể đối chiếu Endpoints nếu một công cụ cũ hoặc client vẫn đọc API này.

Không nên giả định output Endpoints và EndpointSlice luôn có cùng hình thức. Hai tài nguyên có mô hình dữ liệu khác nhau và EndpointSlice là nguồn được Kubernetes ưu tiên cho nhiều thành phần mạng hiện đại.

## 8. Spring Cloud Kubernetes sử dụng endpoint sẵn sàng

Spring Cloud Kubernetes Discovery tích hợp với Kubernetes API để tìm Service và các Pod/endpoint tương ứng. Tùy discovery mode, phiên bản và cấu hình, ứng dụng có thể lấy thông tin từ Service, Endpoints hoặc EndpointSlices.

Ở mức ứng dụng, Spring Cloud cung cấp abstraction DiscoveryClient để tra cứu instance theo service ID. Ví dụ:

~~~java
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class ServiceLookup {
    private final DiscoveryClient discoveryClient;

    public ServiceLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findPaymentInstances() {
        return discoveryClient.getInstances("payment-service");
    }
}
~~~

Khi chạy trong Kubernetes, tên service ID thường gắn với tên Kubernetes Service. Kết quả cụ thể phụ thuộc discovery provider và cách ứng dụng được cấu hình. Nếu ứng dụng chỉ gọi DNS của Kubernetes Service, việc chọn endpoint thường do Kubernetes networking thực hiện; nếu ứng dụng dùng Spring Cloud Kubernetes Discovery và LoadBalancer, ứng dụng có thể nhận danh sách instance để chọn ở phía client.

Hai mô hình này có hành vi khác nhau:

| Mô hình | Ai chọn Pod đích? | Dữ liệu client nhìn thấy |
|---|---|---|
| Gọi DNS/ClusterIP của Service | Kube-proxy hoặc data plane tương ứng | Một địa chỉ Service ổn định |
| DiscoveryClient + client-side LoadBalancer | Ứng dụng và LoadBalancer | Danh sách instance mà discovery provider trả về |

Nếu dùng client-side discovery, cần xác minh provider có lọc endpoint chưa Ready theo cấu hình hiện tại. Không nên suy luận chỉ từ việc Pod Ready=false rằng mọi thư viện discovery bên thứ ba chắc chắn sẽ loại endpoint theo cùng một cách ở mọi phiên bản.

## 9. Cấu hình và quyền truy cập Kubernetes API

Spring Cloud Kubernetes Discovery cần truy cập API server để đọc tài nguyên discovery. Trong cluster, ứng dụng thường xác thực bằng ServiceAccount gắn với Pod. Cấp quyền theo nguyên tắc tối thiểu, chỉ cho phép đọc những loại tài nguyên mà discovery mode cần.

Ví dụ RBAC cơ bản để đọc Service, EndpointSlice, Endpoints và Pod trong một namespace:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: payment-discovery-reader
  namespace: app
rules:
  - apiGroups: [""]
    resources: ["services", "endpoints", "pods"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
~~~

Gắn Role vào ServiceAccount mà ứng dụng sử dụng:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: payment-discovery-reader
  namespace: app
subjects:
  - kind: ServiceAccount
    name: payment-service
    namespace: app
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: payment-discovery-reader
~~~

Đây là ví dụ quyền đọc cho một số discovery mode. Tài nguyên thực sự cần thiết phụ thuộc provider, phiên bản và cấu hình; nếu chỉ dùng Kubernetes Service DNS thì ứng dụng có thể không cần quyền đọc Pod hoặc EndpointSlice. Không cấp quyền cluster-wide nếu discovery chỉ hoạt động trong một namespace.

Kiểm tra quyền bằng:

~~~bash
kubectl auth can-i list services --as=system:serviceaccount:app:payment-service -n app
kubectl auth can-i watch endpointslices.discovery.k8s.io --as=system:serviceaccount:app:payment-service -n app
~~~

## 10. Readiness trong rolling update

Khi Deployment cập nhật image, Kubernetes tạo Pod mới và chờ Pod đạt Ready trước khi coi nó là endpoint sẵn sàng. Với rolling update, các tham số maxSurge và maxUnavailable quyết định số Pod mới được tạo thêm và số Pod cũ có thể tạm thời không khả dụng.

Ví dụ:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
~~~

Với cấu hình này, Deployment có thể tạo thêm tối đa một Pod vượt số replicas và không chủ động giảm số Pod khả dụng xuống dưới replicas trong quá trình rollout. Nếu readiness probe cấu hình quá lỏng, Pod mới có thể được đưa vào endpoint trước khi thực sự phục vụ tốt. Nếu probe quá chặt, rollout có thể bị chậm hoặc không tiến triển.

Khi Pod cũ bị xóa, Kubernetes có thể đánh dấu endpoint đang terminating và phối hợp quá trình ngừng nhận traffic mới với graceful shutdown. Ứng dụng nên xử lý SIGTERM, ngừng nhận request mới, hoàn tất request đang chạy trong thời hạn terminationGracePeriodSeconds và đóng kết nối đúng cách.

## 11. Readiness gate và trạng thái phục vụ tùy chỉnh

Ngoài probe, Pod có thể dùng readiness gates để bổ sung điều kiện Ready từ một controller hoặc hệ thống bên ngoài. Pod chỉ được coi là Ready khi các điều kiện readiness gate yêu cầu đã chuyển sang True cùng với trạng thái container sẵn sàng.

Ví dụ khai báo một readiness gate tùy chỉnh:

~~~yaml
spec:
  readinessGates:
    - conditionType: "example.com/registration-ready"
~~~

Controller bên ngoài có trách nhiệm cập nhật Pod condition tương ứng. Chỉ khai báo readiness gate mà không có thành phần cập nhật condition sẽ khiến Pod không đạt Ready.

Readiness gate hữu ích khi ứng dụng cần chờ một bước ngoài probe HTTP, chẳng hạn đăng ký với hệ thống điều phối riêng hoặc hoàn tất đồng bộ dữ liệu. Không nên thêm gate nếu không có controller đáng tin cậy chịu trách nhiệm cập nhật trạng thái.

## 12. Các tình huống thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Pod Running nhưng Service không có endpoint ready | Readiness probe thất bại hoặc selector không khớp | Describe Pod, Service và EndpointSlice |
| Pod Ready nhưng endpoint không xuất hiện | Service selector sai, controller chậm hoặc namespace nhầm | Kiểm tra labels, selector và namespace |
| EndpointSlice có địa chỉ nhưng ready=false | Pod chưa Ready hoặc endpoint đang trong trạng thái chuyển tiếp | Kiểm tra Pod conditions và probe events |
| Spring Discovery không thấy instance | RBAC thiếu quyền, discovery mode hoặc cache chưa cập nhật | Kiểm tra log API, Role/RoleBinding và cấu hình discovery |
| Client vẫn gọi Pod vừa NotReady | Cache phía client, LoadBalancer hoặc data plane chưa cập nhật | Đối chiếu EndpointSlice, DiscoveryClient và danh sách supplier |
| Rollout đứng ở trạng thái Progressing | Pod mới không đạt readiness hoặc thiếu capacity | Describe Deployment/Pod và đọc probe events |
| Pod terminating vẫn có kết nối đang chạy | Graceful shutdown và endpoint termination đang diễn ra | Kiểm tra terminationGracePeriodSeconds, preStop và connection draining |
| Service không có endpoint nào | Không có Pod khớp selector hoặc mọi Pod đều NotReady | So sánh selector, labels và conditions |

## 13. Quy trình chẩn đoán endpoint không sẵn sàng

Khi một service không nhận được traffic hoặc client không tìm thấy instance, kiểm tra từ nguồn trạng thái đến nơi tiêu thụ:

1. Đọc Pod labels và conditions để xác định Pod có Ready hay không.
2. Xem sự kiện và log probe để tìm nguyên nhân readiness thất bại.
3. Kiểm tra Service selector có khớp labels của Pod không.
4. Đọc EndpointSlice để xác nhận địa chỉ, port và các condition ready/serving/terminating.
5. Đối chiếu tài nguyên Endpoints nếu một thành phần cũ đang sử dụng API đó.
6. Kiểm tra ServiceAccount, Role và RoleBinding nếu Spring Cloud Kubernetes đọc Kubernetes API trực tiếp.
7. Kiểm tra DiscoveryClient và danh sách instance mà LoadBalancer supplier cung cấp.
8. Nếu danh sách đã đúng nhưng request vẫn thất bại, kiểm tra NetworkPolicy, port, protocol, TLS và health của endpoint nghiệp vụ.

~~~mermaid
flowchart TD
    START[Client không thấy endpoint sẵn sàng] --> POD[Kiểm tra Pod Ready và probe]
    POD -->|NotReady| PROBE[Đọc events, logs và health group]
    POD -->|Ready| SVC[Kiểm tra Service selector và namespace]
    SVC -->|Không khớp| LABEL[Sửa selector hoặc Pod labels]
    SVC -->|Khớp| EPS[Kiểm tra EndpointSlice conditions]
    EPS -->|Thiếu hoặc chưa ready| CTRL[Kiểm tra controller, publishNotReadyAddresses và Pod state]
    EPS -->|Ready| DISC[Kiểm tra RBAC và DiscoveryClient]
    DISC -->|Không thấy| CACHE[Kiểm tra API watch, cache và provider]
    DISC -->|Đã thấy| NET[Kiểm tra LoadBalancer, network và port]
~~~

## 14. Nguyên tắc thiết kế readiness

- Readiness nên phản ánh khả năng xử lý request thực tế của ứng dụng.
- Chỉ đưa dependency thiết yếu vào readiness; tránh làm cả fleet NotReady vì một dependency tùy chọn.
- Dùng startup probe cho ứng dụng khởi động chậm thay vì nới lỏng mọi probe.
- Đặt timeout và failure threshold dựa trên số liệu thực tế.
- Bảo đảm Service selector và Pod labels có quy ước rõ ràng.
- Kiểm tra EndpointSlice conditions thay vì chỉ nhìn trạng thái Running của Pod.
- Thiết kế graceful shutdown để endpoint ngừng nhận traffic mới trước khi tiến trình kết thúc.
- Nếu dùng Spring Cloud Kubernetes Discovery, xác minh RBAC, discovery mode và hành vi lọc endpoint của phiên bản đang chạy.
- Không xem cache discovery là trạng thái tức thời; client vẫn phải xử lý lỗi kết nối và endpoint vừa mất khả năng phục vụ.

## 15. Tổng kết

Readiness cho biết Pod có nên nhận traffic hay không. Kubelet đánh giá readiness probe và các readiness gate, sau đó EndpointSlice controller cập nhật danh sách endpoint của Service. EndpointSlice chứa địa chỉ cùng các điều kiện ready, serving và terminating; tài nguyên Endpoints cũ vẫn có thể được dùng bởi công cụ tương thích.

Spring Cloud Kubernetes Discovery có thể đọc Service và danh sách endpoint từ Kubernetes API để cung cấp instance cho DiscoveryClient và LoadBalancer. Cần phân biệt mô hình gọi qua ClusterIP với client-side discovery, đồng thời xác minh provider có lọc endpoint chưa sẵn sàng như mong đợi. Khi điều tra, hãy đi từ Pod readiness, Service selector, EndpointSlice, RBAC đến DiscoveryClient và LoadBalancer để tìm đúng nơi danh sách endpoint bị thiếu hoặc cũ.
