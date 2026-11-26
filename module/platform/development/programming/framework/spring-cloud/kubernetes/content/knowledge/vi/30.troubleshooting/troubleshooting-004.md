# DiscoveryClient không trả về dịch vụ hoặc bản sao

## 1. Bối cảnh và mục tiêu

Ứng dụng Spring gọi getServices() và nhận danh sách rỗng, hoặc tìm thấy tên inventory nhưng getInstances("inventory") không có phần tử. Đây là hai triệu chứng khác nhau, cần được đối chiếu với dữ liệu và cấu hình ở đúng lớp.

Trong module **SPRING_CLOUD_KUBERNETES**, bài học này thuộc chương **Chẩn đoán sự cố**. Mục tiêu là tìm được nguyên nhân cụ thể trên đường từ Kubernetes API tới DiscoveryClient, rồi xác minh cả việc tìm instance và gọi dịch vụ.

Sau bài học, bạn có thể:

- Phân biệt thiếu client, danh sách rỗng và lỗi chọn instance ở LoadBalancer.
- Kiểm tra đúng Service ID, namespace và bộ lọc.
- Đối chiếu Service, Pod, Endpoints/EndpointSlice và readiness.
- Kiểm tra danh tính, RBAC, kết nối API và trạng thái cache.
- Tách lỗi ở ứng dụng khỏi lỗi tại DiscoveryServer khi dùng client HTTP.

Ví dụ dùng orders trong namespace checkout gọi Service inventory trong namespace commerce. Các lệnh là hướng dẫn trên môi trường thử nghiệm; thay tên Pod và tài nguyên theo hệ thống thực tế.

## 2. Xác định triệu chứng trước khi sửa cấu hình

### 2.1. Bảng phân loại ban đầu

| Quan sát | Nhánh cần kiểm tra trước |
| --- | --- |
| Không inject được DiscoveryClient | Dependency, auto-configuration, profile và thuộc tính enable |
| getServices() rỗng | Client thực tế, phạm vi namespace, bộ lọc, quyền đọc và đồng bộ |
| Có inventory nhưng getInstances("inventory") rỗng | Service ID, endpoint, readiness và đường đọc endpoint |
| Có một phần instance mong đợi | Pod nào Ready, các slice, phạm vi, cache và thời điểm lấy mẫu |
| DiscoveryClient có instance nhưng LoadBalancer báo không có đích | Supplier, bộ lọc và cache của LoadBalancer |
| Có host/port nhưng request thất bại | Cổng, protocol, mạng và ứng dụng đích |
| Chỉ lỗi lúc khởi động hoặc sau một thời gian | Đồng bộ ban đầu, WATCH, reconnect, token và cache |
| Máy quản trị thấy tài nguyên nhưng ứng dụng không thấy | Cụm, danh tính, namespace và API thực sự mà ứng dụng dùng |

Đừng biến mọi ngoại lệ thành danh sách rỗng trong đoạn đo chẩn đoán. Nếu mã ứng dụng đang catch lỗi rồi trả List.of(), cần ghi nhận loại lỗi và nguyên nhân đã được làm sạch.

### 2.2. Tên dịch vụ khác địa chỉ DNS

Spring Cloud Kubernetes trả tên Service từ metadata.name qua getServices(); các tên có thể được gộp duy nhất khi tìm ở nhiều namespace. [DiscoveryClient và Service ID](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Với Service inventory:

~~~text
getInstances("inventory")                 -> tra Service ID

http://inventory.commerce.svc:8080        -> địa chỉ dùng theo đường DNS
~~~

Không tự thay Service ID bằng inventory.commerce.svc rồi kỳ vọng mọi implementation hiểu đây là inventory trong commerce.

Tương tự, đặt spring.application.name cho một ứng dụng không tự tạo Kubernetes Service hoặc sửa metadata.name của Service đã triển khai. Kiểm tra tài nguyên thật.

### 2.3. DNS thành công chưa chứng minh discovery thành công

Một HTTP client thường có thể gọi Service qua DNS trong khi DiscoveryClient thiếu quyền đọc API. Ngược lại, có danh sách instance không bảo đảm kết nối tới host/port đó được phép.

Đặc biệt, client được cấu hình dùng Spring Cloud LoadBalancer có thể hiểu phần host của URL là Service ID. Xác định lời gọi đang đi qua DNS thông thường hay qua cơ chế chọn instance trước khi so sánh kết quả.

## 3. Xác định đúng implementation đang chạy

### 3.1. Hai đường dữ liệu khác nhau

~~~text
Client trực tiếp trong ứng dụng:
orders -> Kubernetes API -> Service/endpoint -> DiscoveryClient

Client HTTP:
orders -> DiscoveryServer -> Kubernetes API
               |
               +-> dữ liệu trả về cho DiscoveryClient phía orders
~~~

Spring Cloud Kubernetes hỗ trợ Fabric8, Kubernetes Java Client và client HTTP dùng DiscoveryServer. [Các implementation được hỗ trợ](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Với client trực tiếp, kiểm tra ServiceAccount, cấu hình API và namespace của tiến trình orders. Với client HTTP, những kiểm tra Kubernetes này chủ yếu nằm ở server discovery; phía orders còn có một chặng HTTP riêng.

Nếu có CompositeDiscoveryClient, wrapper hoặc proxy, cần biết delegate nào đang trả kết quả. Tên lớp proxy không đủ để kết luận implementation đích.

### 3.2. Kiểm tra dependency và điều kiện cấu hình

Ghi lại:

- Phiên bản Spring Boot, Spring Cloud, Spring Cloud Kubernetes và Kubernetes client.
- Starter đã chọn cho chức năng discovery.
- Profile đang có hiệu lực và các nguồn cấu hình ghi đè.
- Client blocking hay reactive mà đoạn nghiệp vụ đang sử dụng.
- Thuộc tính discovery.enabled và các điều kiện nhận diện môi trường.
- Các bean DiscoveryClient tùy biến hoặc implementation khác cùng tồn tại.

Dùng condition report hoặc endpoint conditions đã được bảo vệ khi phù hợp. Actuator hỗ trợ quan sát điều kiện và bean, nhưng phải kiểm soát exposure và quyền truy cập. [Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).

Không coi ứng dụng khởi động được là bằng chứng Kubernetes discovery đã được bật. Nó có thể đang chạy với cấu hình khác dự kiến.

### 3.3. Đo ngay tại DiscoveryClient

Một helper cho client blocking có thể lấy snapshot như sau:

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

public final class DiscoveryProbe {

    private DiscoveryProbe() {
    }

    public static void inspect(DiscoveryClient client, String serviceId) {
        var services = client.getServices();
        var instances = client.getInstances(serviceId);

        System.out.printf(
                "client=%s services=%s target=%s instanceCount=%d%n",
                client.getClass().getName(),
                services,
                serviceId,
                instances.size()
        );

        for (ServiceInstance instance : instances) {
            System.out.printf(
                    "serviceId=%s host=%s port=%d secure=%s%n",
                    instance.getServiceId(),
                    instance.getHost(),
                    instance.getPort(),
                    instance.isSecure()
            );
        }
    }
}
~~~

Gọi helper với bean thực tế và serviceId bằng inventory từ một điểm chẩn đoán nội bộ được kiểm soát. Ví dụ chỉ in thông tin cần đối chiếu, không dump toàn bộ metadata hoặc cấu hình xác thực.

Một snapshot ở thời điểm khởi động có thể chưa phản ánh trạng thái sau đồng bộ. Ghi thời điểm và lấy lại sau khi kiểm tra trạng thái client.

Với client reactive, dùng API và luồng thực thi tương ứng; không chèn lời gọi blocking tùy tiện vào event loop chỉ để lấy mẫu.

## 4. Kiểm tra namespace và bộ lọc trước khi mở rộng phạm vi

### 4.1. Namespace của caller không tự là namespace của đích

Trong ví dụ:

~~~text
orders đang chạy: checkout
inventory tồn tại: commerce
~~~

Nếu discovery chỉ tìm namespace mặc định của orders, inventory ở commerce có thể nằm ngoài phạm vi.

Ví dụ cấu hình dành cho client trực tiếp, khi thực sự chỉ cần tìm ở commerce:

~~~yaml
spring:
  application:
    name: orders
  cloud:
    kubernetes:
      discovery:
        enabled: true
        all-namespaces: false
        namespaces:
          - commerce
        service-labels:
          discovery-scope: commerce
        primary-port-name: http
        use-endpoint-slices: true
        include-not-ready-addresses: false
        wait-cache-ready: true
~~~

Đây là cấu hình minh họa để đối chiếu với phiên bản đã chọn. Các thuộc tính namespace, nhãn, EndpointSlice và cache có ý nghĩa riêng. [Danh mục thuộc tính discovery](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

Nếu ứng dụng đang dùng client HTTP, phải đặt phạm vi đọc Kubernetes tại DiscoveryServer theo implementation; đổi namespace ở sai phía sẽ không sửa dữ liệu mà server đã thu thập.

Không bật all-namespaces chỉ để làm một Service xuất hiện mà chưa xác định nhu cầu, quyền và chi phí. Chọn đúng namespace cần thiết rồi kiểm tra kết quả.

### 4.2. Xác minh namespace thực tế

Trên máy quản trị:

~~~bash
kubectl config current-context
kubectl get service inventory -n commerce -o yaml
kubectl get pod orders-example -n checkout -o 'custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,SA:.spec.serviceAccountName'
~~~

Thay orders-example bằng Pod caller thực tế. Đối chiếu API server mà client đang cấu hình; kubectl có thể đang xem một cụm khác với ứng dụng.

Khi không cấu hình namespace rõ ràng, Spring Cloud Kubernetes có cơ chế phân giải dựa trên cấu hình và môi trường của client. File namespace mặc định trong Pod cũng có thể tham gia. [Namespace resolution](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/namespace-resolution.html).

Nếu đã tắt automount token, bộ file mặc định có thể không tồn tại. Không chỉ kiểm tra tên namespace trong Deployment; cần xem client đã phân giải thành giá trị nào và có lỗi khởi tạo hay không.

### 4.3. Nhãn lọc Service khác nhãn chọn Pod

Với service-labels trong ví dụ, Service phải có nhãn phù hợp ở metadata.labels:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: inventory
  namespace: commerce
  labels:
    discovery-scope: commerce
spec:
  selector:
    app: inventory
  ports:
    - name: http
      port: 8080
      targetPort: 8080
~~~

Hai phép chọn độc lập:

- metadata.labels.discovery-scope giúp discovery chọn Service.
- spec.selector.app giúp Service chọn Pod.

Chỉ gắn discovery-scope lên Pod không làm Service tự có nhãn đó. Ngược lại, Service có nhãn discovery đúng nhưng selector không khớp Pod vẫn có thể không có backend.

Kiểm tra:

~~~bash
kubectl get services -n commerce -l discovery-scope=commerce --show-labels
kubectl get pods -n commerce -l app=inventory --show-labels
~~~

### 4.4. Kiểm tra cả filter bổ sung

Thuộc tính discovery.filter dùng biểu thức SpEL để lọc sau khi đã lấy tài nguyên; kiểu đối tượng phụ thuộc client. [Thuộc tính filter](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

Nếu Service có trong API nhưng không có ở kết quả client, xem cả service-labels, filter và lớp lọc tùy biến của ứng dụng.

Thu hẹp chẩn đoán bằng cách đối chiếu điều kiện với một Service cụ thể. Khi thử bỏ một filter trong môi trường kiểm soát, chỉ thay một yếu tố để biết điều gì làm kết quả đổi.

Không mặc định mọi biểu thức sai đều chỉ trả rỗng. Có thể có lỗi đánh giá hoặc lỗi khởi tạo cần được ghi nhận.

## 5. Kiểm tra Service có backend thực sự hay không

### 5.1. Pod tồn tại không đồng nghĩa Service chọn được Pod

Đọc selector của Service và nhãn trên Pod:

~~~bash
kubectl get service inventory -n commerce -o yaml
kubectl get pods -n commerce --show-labels
kubectl get pods -n commerce -l app=inventory -o wide
~~~

Với Service có selector, Kubernetes dùng những Pod khớp để quản lý dữ liệu backend. Một lỗi chính tả ở selector hoặc nhãn Pod có thể làm backend trống. [Chẩn đoán Service và selector](https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/).

Kiểm tra cả namespace: Service có selector không tự chọn Pod cùng nhãn ở namespace khác.

Nếu Service không có selector, cần biết thành phần nào đang cung cấp endpoint. Không kỳ vọng Kubernetes tự chọn Deployment chỉ từ sự giống nhau giữa tên.

### 5.2. Đọc đúng tài nguyên mà client sử dụng

Khi dùng EndpointSlice:

~~~bash
kubectl get endpointslices -n commerce -l kubernetes.io/service-name=inventory -o yaml
~~~

Khi client được cấu hình đọc Endpoints:

~~~bash
kubectl get endpoints inventory -n commerce -o yaml
~~~

Đối chiếu:

| Nội dung | Câu hỏi |
| --- | --- |
| Namespace và tên Service liên kết | Có đúng inventory ở commerce không? |
| Địa chỉ | Có backend thực tế không? |
| Cổng và protocol | Có đúng cổng mà ứng dụng đích phục vụ không? |
| Điều kiện endpoint | Địa chỉ nào sẵn sàng hoặc đang kết thúc? |
| targetRef nếu có | Địa chỉ thuộc Pod nào? |
| Nhiều slice | Đã đọc đủ tập endpoint, không chỉ một slice chưa? |

EndpointSlice có thể chia backend thành nhiều đối tượng theo các tổ hợp địa chỉ, protocol và cổng. [Cấu trúc EndpointSlice](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/).

Nếu client đọc Endpoints nhưng bạn chỉ kiểm tra EndpointSlice, hoặc ngược lại, vẫn còn một khoảng trống trong chẩn đoán. Xác nhận cấu hình có hiệu lực và request API thực tế.

### 5.3. Chưa Ready có thể là nguyên nhân thiếu instance

Kiểm tra Pod đích:

~~~bash
kubectl get pods -n commerce -l app=inventory -o wide
kubectl describe pod inventory-example -n commerce
kubectl logs inventory-example -n commerce -c app --tail=100
~~~

Thay tên Pod và container thực tế. Pod ở phase Running chưa đủ để khẳng định Ready. Xem probe, lỗi khởi động, cổng lắng nghe và các phụ thuộc của ứng dụng.

Số replica mong muốn của Deployment không phải số instance đủ điều kiện discovery ở mọi thời điểm. Trong rollout, một số Pod mới chưa sẵn sàng, một số Pod cũ đang kết thúc.

Thuộc tính include-not-ready-addresses có thể cho phép đưa địa chỉ chưa Ready vào kết quả theo hỗ trợ của client. Nó không sửa ứng dụng đích hoặc probe bị lỗi. Giữ chính sách phù hợp với mục đích gọi nghiệp vụ và xử lý nguyên nhân readiness. [Thuộc tính địa chỉ chưa Ready](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

## 6. Kiểm tra cổng, loại Service và kỳ vọng số instance

### 6.1. Cổng không đúng khác với không có instance

Trong Service nhiều cổng, xác định tên cổng nghiệp vụ và cấu hình primary-port-name khi cần. Đối chiếu host/port được DiscoveryClient trả về với dữ liệu endpoint và cấu hình Service.

Service port và targetPort có thể khác nhau. Khi gọi trực tiếp Pod IP, phải dùng cổng backend tương ứng; không mặc định mọi địa chỉ đều dùng cùng một cổng.

Nếu DiscoveryClient đã trả instance nhưng request đi sai cổng hoặc protocol, chuyển sang nhánh kết nối. Một danh sách có phần tử chưa chứng minh request nghiệp vụ sẽ thành công.

### 6.2. ExternalName và headless Service có kỳ vọng khác

ExternalName biểu diễn tên bên ngoài và không có tập Pod backend như Service có selector. Headless Service cũng không có ClusterIP thông thường. [Các loại Service](https://kubernetes.io/docs/concepts/services-networking/service/).

Hỗ trợ ExternalName trong DiscoveryClient cần tùy chọn tương ứng của Spring Cloud Kubernetes. [ExternalName trong discovery](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Trước khi kết luận “thiếu tất cả replica”, xác định Service đang thuộc mô hình nào và client hỗ trợ mô hình đó ra sao. Không sửa một ExternalName bằng cách thêm selector Pod không liên quan.

### 6.3. Có ít instance hơn số Pod chưa chắc là lỗi client

Cần tính đến:

- Pod có thực sự được Service chọn hay không.
- Trạng thái readiness và termination.
- Namespace và filter đang áp dụng.
- Cách biểu diễn địa chỉ, cổng và các slice.
- Thời điểm dữ liệu API và snapshot client được lấy.

Với nhiều namespace có Service trùng tên, đối chiếu thêm namespace trong thông tin kết quả hoặc metadata được hỗ trợ; một tên duy nhất trong getServices không chứng minh chỉ có một nguồn Service.

## 7. Kiểm tra quyền đọc bằng đúng danh tính

### 7.1. Quyền của kubectl không phải quyền của ứng dụng

Máy quản trị có thể list Service nhưng orders-runtime trong checkout vẫn không có quyền list/watch tài nguyên ở commerce.

Lấy ServiceAccount thực tế:

~~~bash
kubectl get pod orders-example -n checkout -o 'jsonpath={.spec.serviceAccountName}'
~~~

Nếu dùng client HTTP, thực hiện bước này với Pod DiscoveryServer thay vì mặc định dùng danh tính của orders.

### 7.2. Kiểm tra từng tài nguyên và động từ

Ví dụ từ tài khoản quản trị có quyền impersonation:

~~~bash
kubectl auth can-i list services -n commerce --as=system:serviceaccount:checkout:orders-runtime --as-group=system:serviceaccounts --as-group=system:serviceaccounts:checkout --as-group=system:authenticated
kubectl auth can-i list endpointslices.discovery.k8s.io -n commerce --as=system:serviceaccount:checkout:orders-runtime --as-group=system:serviceaccounts --as-group=system:serviceaccounts:checkout --as-group=system:authenticated
kubectl auth can-i watch endpointslices.discovery.k8s.io -n commerce --as=system:serviceaccount:checkout:orders-runtime --as-group=system:serviceaccounts --as-group=system:serviceaccounts:checkout --as-group=system:authenticated
~~~

Kiểm tra thêm get/list/watch cho các tài nguyên implementation thực sự sử dụng. Kết quả list được không tự chứng minh watch được.

kubectl auth can-i kiểm tra quyền của danh tính được mô phỏng. Người chạy cần quyền impersonation phù hợp; lỗi không được impersonate không phải kết quả quyền của ứng dụng. [kubectl auth can-i](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/).

Kết quả yes cũng không chứng minh tiến trình có token hợp lệ hoặc kết nối được API. Phải kiểm tra các lớp đó riêng.

### 7.3. Ví dụ quyền theo namespace cho EndpointSlice

Trong ví dụ client trực tiếp dùng Service và EndpointSlice, một Role và RoleBinding có thể là:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: inventory-discovery-reader
  namespace: commerce
rules:
  - apiGroups: [""]
    resources: ["services"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: orders-inventory-discovery
  namespace: commerce
subjects:
  - kind: ServiceAccount
    name: orders-runtime
    namespace: checkout
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: inventory-discovery-reader
~~~

Role và RoleBinding nằm ở namespace chứa tài nguyên được đọc; subject có thể là ServiceAccount ở namespace khác. [Phân quyền RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Đây là quyền cho giả định của ví dụ. Nếu client dùng Endpoints hoặc một chức năng bổ sung cần Pod, phải đối chiếu tài nguyên và quyền tương ứng. Không mặc định discovery cần quyền đọc Secret.

Nếu client đang list toàn cụm, Role ở commerce không cấp quyền cho yêu cầu toàn cụm. Sửa phạm vi về nhu cầu thực hoặc thiết kế quyền có căn cứ; không tự chuyển sang cluster-admin để làm lỗi biến mất.

## 8. Kiểm tra thông tin xác thực, TLS và đường API

### 8.1. Client có bộ thông tin cần thiết hay không?

Client trong Pod thường cần địa chỉ API, CA và thông tin xác thực được cấu hình phù hợp. Cơ chế in-cluster có thể sử dụng bộ file ServiceAccount được mount. [Truy cập API từ Pod](https://kubernetes.io/docs/tasks/run-application/access-api-from-pod/).

Đối chiếu:

- serviceAccountName và automountServiceAccountToken của Pod thực tế.
- Volume token, CA và đường dẫn mà client đọc.
- Cấu hình API server, proxy và nguồn kubeconfig nếu có.
- Cách client nhận token mới sau khi token được làm mới.
- Danh tính ở phía API trong lỗi hoặc audit được phép truy cập.

Không in token ra terminal hoặc log để kiểm tra. Tồn tại file cũng chưa chứng minh token còn hợp lệ hoặc có đúng audience.

Một WATCH còn mở có thể tiếp tục cung cấp dữ liệu trong khi lần xác thực tiếp theo gặp vấn đề. Vì vậy, lỗi chỉ xuất hiện sau reconnect cần được ghép với vòng đời thông tin xác thực.

### 8.2. Đọc lỗi theo đúng lớp

| Dấu hiệu | Lớp cần điều tra |
| --- | --- |
| Không tạo được client hoặc không tìm thấy namespace/token | Cấu hình và môi trường khởi tạo |
| HTTP 401 từ API | Thông tin xác thực không được chấp nhận, hết hạn hoặc sai đích |
| HTTP 403 từ API | Danh tính đang được xử lý không có quyền phù hợp |
| Lỗi xác minh chứng chỉ | CA, hostname hoặc trust material |
| DNS lỗi, timeout kết nối | Địa chỉ API, DNS, proxy, egress hoặc định tuyến |
| HTTP 404 khi gọi tài nguyên | Đường dẫn, tên, namespace hoặc API được sử dụng |
| HTTP 429 hoặc lỗi máy chủ | Áp lực phía server và hành vi retry/backoff |

Không khẳng định mọi 403 đều chứng minh token ServiceAccount hợp lệ. Yêu cầu có thể được xử lý dưới danh tính anonymous tùy cấu hình; xem chủ thể và phản hồi cụ thể.

Với lỗi TLS, sửa cấu hình tin cậy và địa chỉ đúng. Tắt xác minh chứng chỉ không giải thích nguyên nhân và không phải cấu hình khắc phục lâu dài.

### 8.3. Tách đường tới API khỏi đường tới inventory

~~~text
orders -> Kubernetes API
    cần cho discovery trực tiếp

orders -> inventory endpoint
    cần cho request nghiệp vụ
~~~

NetworkPolicy có thể cho phép một đường và chặn đường còn lại. Một Pod khác gọi API được không chứng minh orders gọi được, vì nhãn, namespace và đường mạng có thể khác.

Khi dùng công cụ chẩn đoán, bảo đảm nó quan sát đúng Pod hoặc bối cảnh mạng cần kiểm tra. Một lần port-forward từ máy quản trị không mô phỏng đường egress API của ứng dụng.

## 9. Cache ban đầu, WATCH và kết quả cũ

### 9.1. Rỗng tạm thời hay lỗi kéo dài?

Một số implementation dùng store/lister được cập nhật bất đồng bộ. Ghi lại thời điểm lấy mẫu so với khởi động client và lần đồng bộ tài nguyên.

Thuộc tính wait-cache-ready và thời hạn tải cache điều khiển hành vi khởi tạo theo hỗ trợ của phiên bản. [Cấu hình chờ cache](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

Nếu cache không tải được vì thiếu quyền hoặc API không kết nối được, chỉ tăng timeout không giải quyết nguyên nhân. Ngược lại, lấy kết quả quá sớm rồi lưu rỗng vĩnh viễn trong mã ứng dụng có thể làm một khoảng trống tạm thời trở thành lỗi kéo dài.

Hãy xác định ai giữ danh sách:

~~~text
Store tài nguyên Kubernetes
    -> kết quả DiscoveryClient
    -> cache kết quả, nếu có
    -> ServiceInstanceListSupplier
    -> cache hoặc trạng thái của LoadBalancer
    -> tham chiếu do ứng dụng tự giữ
~~~

Không mặc định mọi lớp trên luôn có, hoặc cùng thời hạn cập nhật.

### 9.2. Kiểm tra cập nhật sau lần đồng bộ đầu

Trong thử nghiệm có kiểm soát, thay đổi trạng thái một backend và theo dõi:

1. API đã phản ánh endpoint mới hoặc bị loại.
2. Client có nhận thay đổi qua WATCH hoặc đường đồng bộ tương ứng.
3. getInstances phản ánh tập đủ điều kiện hiện tại.
4. LoadBalancer sử dụng danh sách mới.
5. Không còn lỗi gọi tới instance đã dừng ngoài khoảng chuyển tiếp mong muốn.

Khi lịch sử resourceVersion cần cho WATCH không còn, Kubernetes có thể trả 410 Gone; client phải phục hồi trạng thái và tiếp tục theo dõi theo giao thức. [Cơ chế LIST/WATCH và phục hồi](https://kubernetes.io/docs/reference/using-api/api-concepts/).

Một lần 410 rồi phục hồi thành công khác với vòng lỗi kéo dài. Tìm dấu hiệu reconnect, list lại, 401/403, timeout hoặc xử lý lỗi bị dừng.

### 9.3. Quan sát có giới hạn

Có thể bật tạm mức DEBUG cho phần tích hợp:

~~~yaml
logging:
  level:
    org.springframework.cloud.kubernetes: DEBUG
~~~

Package của client HTTP hoặc Kubernetes client bên dưới có thể cần cấu hình riêng theo phiên bản. Chỉ bật phần liên quan và ghi lại trong khoảng thời gian đủ để tái hiện.

Không dùng TRACE toàn bộ HTTP hoặc xuất cấu hình nhạy cảm như một bước mặc định. Khi chia sẻ log, loại bỏ token, header xác thực và metadata không cần thiết.

Restart làm kết quả xuất hiện lại chỉ là một dấu hiệu về vòng đời hoặc cache. Cần tiếp tục xác minh cập nhật sau đó; một hệ thống chỉ hoạt động ngay sau restart vẫn chưa được sửa hoàn chỉnh.

## 10. Nhánh riêng khi dùng DiscoveryServer

### 10.1. Kiểm tra từng chặng

~~~text
orders
  -> URL và kết nối HTTP tới DiscoveryServer
  -> phản hồi của đúng server/replica
  -> cache và cấu hình phía client HTTP

DiscoveryServer
  -> namespace và bộ lọc
  -> danh tính và quyền Kubernetes
  -> Service/endpoint và cache phía server
~~~

DiscoveryServer cung cấp các endpoint /apps và /apps/{name} để xem dữ liệu dịch vụ và instance. [API của DiscoveryServer](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-discoveryserver.html).

Giả sử môi trường thử nghiệm có Service discovery-server ở namespace platform, công bố cổng 80:

~~~bash
curl --silent --show-error --max-time 5 -i http://discovery-server.platform.svc:80/apps
curl --silent --show-error --max-time 5 -i http://discovery-server.platform.svc:80/apps/inventory
~~~

Địa chỉ và cổng là giả định minh họa; dùng URL thật từ cấu hình có hiệu lực của client. Nếu endpoint được bảo vệ, dùng công cụ quản trị đã được cấu hình xác thực phù hợp.

Đọc cả HTTP status và nội dung. Không mặc định mọi lỗi HTTP đều đã được biến thành danh sách rỗng.

### 10.2. Diễn giải kết quả đối chiếu

| API Kubernetes / server | Client orders | Nhánh cần kiểm tra |
| --- | --- | --- |
| Kubernetes không có backend phù hợp | Rỗng | Sửa dữ liệu Service/Pod/endpoint |
| Kubernetes có, DiscoveryServer không có | Rỗng | Quyền, phạm vi, filter, cache ở server |
| DiscoveryServer có inventory và instance | Rỗng | URL, kết nối, xử lý phản hồi hoặc cache phía client |
| Server trả 401/403 | Lỗi hoặc rỗng do mã xử lý | Xác thực HTTP server, chưa thể quy ngay cho Kubernetes RBAC |
| Chỉ một replica server có dữ liệu đúng | Lúc được lúc không | So sánh cấu hình và trạng thái từng replica |

Với nhiều replica DiscoveryServer, một request qua Service chỉ phản ánh replica được chọn. Kiểm tra từng server cần thiết và thời điểm đồng bộ.

Không sửa Role của orders nếu orders chỉ gọi HTTP và DiscoveryServer mới là thành phần thiếu quyền API. Xác định đúng chủ thể rồi cấp đúng phạm vi.

## 11. DiscoveryClient có dữ liệu nhưng LoadBalancer vẫn không có đích

Spring Cloud LoadBalancer sử dụng ServiceInstanceListSupplier và có thể có cache hoặc các lớp lựa chọn bổ sung. [Luồng lấy instance của LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html).

Khi helper ở mục 3 đã trả instance, nhưng request load-balanced vẫn báo không có đích, đối chiếu:

- Service ID thực tế mà URL hoặc cấu hình client đưa vào.
- Supplier đang dùng đúng DiscoveryClient/delegate hay không.
- Bộ lọc theo health, zone, hint hoặc metadata tùy cấu hình.
- Cache có đang giữ kết quả cũ hoặc rỗng từ trước không.
- Các cấu hình riêng theo Service ID.
- Thời điểm khởi tạo context và vòng đời cập nhật danh sách.

Một bộ lọc yêu cầu metadata không được đưa vào ServiceInstance có thể loại mọi instance dù discovery đã tìm thấy endpoint.

Đo ở các ranh giới có thể kiểm soát:

~~~text
getInstances("inventory") có phần tử?
    |
    +-- Không -> tiếp tục nhánh discovery/API
    |
    +-- Có -> supplier trước lọc có phần tử?
                  |
                  +-> sau lọc/cache còn phần tử?
                         |
                         +-> instance được chọn có đúng host/port?
~~~

Nếu instance đã được chọn và request chỉ thất bại khi kết nối, chuyển sang kiểm tra cổng, TLS, NetworkPolicy hoặc ứng dụng đích. Không tiếp tục gọi đó là lỗi “DiscoveryClient không trả bản sao”.

## 12. Ba tình huống chẩn đoán thực tế

### 12.1. Service có nhãn trên Pod nhưng thiếu nhãn trên Service

Quan sát:

~~~text
kubectl thấy Service inventory
Pod inventory có discovery-scope=commerce
getServices không có inventory
service-labels đang yêu cầu discovery-scope=commerce
~~~

Kiểm tra metadata.labels của Service xác nhận nhãn thiếu ở đúng đối tượng được lọc.

Khắc phục bằng thay đổi nhãn hoặc bộ lọc theo thiết kế, qua nguồn triển khai đang quản lý. Sau đó kiểm tra Service khớp selector discovery, cache cập nhật và getInstances có các endpoint đủ điều kiện.

Đừng thêm nhãn ngẫu nhiên lên mọi Pod rồi kết luận đã sửa filter của Service.

### 12.2. Có Service nhưng tất cả backend chưa Ready

Quan sát:

~~~text
getServices có inventory
getInstances("inventory") rỗng
Service selector khớp Pod
Endpoint có địa chỉ nhưng readiness chưa đạt
~~~

Kiểm tra probe cho thấy đang gọi sai cổng hoặc ứng dụng chưa đáp ứng điều kiện sẵn sàng. Sửa đúng probe/ứng dụng theo hợp đồng sức khỏe, chờ trạng thái Ready và đối chiếu lại endpoint.

Không dùng việc đưa địa chỉ chưa Ready vào discovery như bằng chứng backend đã phục vụ được. Sau khi có instance, vẫn cần kiểm tra request nghiệp vụ.

### 12.3. Có quyền list Service nhưng thiếu quyền EndpointSlice

Quan sát:

~~~text
kubectl của quản trị thấy đầy đủ dữ liệu
ServiceAccount của client list services được
Client cấu hình use-endpoint-slices=true
Log cho thấy truy cập endpointslices bị 403
~~~

Xác định đúng ServiceAccount, namespace và API group discovery.k8s.io. Cập nhật Role/RoleBinding theo quyền cần thiết, rồi kiểm tra lại cả get/list/watch.

Tùy implementation và cấu hình, lỗi này có thể làm khởi động thất bại, cache không sẵn sàng hoặc đường đọc instance không có dữ liệu; không mặc định luôn cùng một biểu hiện.

Sau sửa, xác nhận client vừa đọc được tập endpoint ban đầu vừa nhận được thay đổi mới. Một snapshot đúng chưa đủ chứng minh WATCH đã hoạt động lâu dài.

## 13. Runbook ngắn để tái hiện và xác nhận đã sửa

### 13.1. Thu thập một bộ bằng chứng tối thiểu

Ghi lại:

| Nhóm | Nội dung |
| --- | --- |
| Caller | Pod, namespace, ServiceAccount và implementation |
| Mục tiêu | Service ID, tên Service và namespace thực tế |
| Phiên bản | Spring Boot/Cloud/Kubernetes client đang dùng |
| Cấu hình | Phạm vi, filter, tài nguyên endpoint và các nguồn ghi đè |
| Dữ liệu Kubernetes | Nhãn Service, selector, Pod và endpoint đủ điều kiện |
| Quyền và kết nối | Kết quả cần thiết, lỗi đã được làm sạch |
| Client | Snapshot getServices/getInstances cùng thời điểm |
| Các lớp sau | Supplier, cache, host/port và kết quả gọi dịch vụ |

Chỉ thu thập dữ liệu phục vụ chẩn đoán. Không đưa token, Secret hoặc toàn bộ metadata vào báo cáo.

### 13.2. Kiểm tra theo thứ tự

~~~text
Client và Service ID
    -> namespace và filter
    -> Service/selector
    -> endpoint/readiness
    -> tài nguyên API và quyền đúng danh tính
    -> xác thực/TLS/mạng
    -> cache/LIST/WATCH
    -> DiscoveryServer, nếu có
    -> LoadBalancer và đường gọi thực tế
~~~

Nếu một bước đã có bằng chứng rõ, chuyển sang bước tiếp theo. Không đồng thời mở toàn cụm, bỏ readiness, nới quyền và restart mọi Pod vì sẽ khó biết nguyên nhân nào đã thay đổi kết quả.

### 13.3. Tiêu chí hoàn thành

Sự cố được xem là đã xử lý khi có bằng chứng:

- Client đúng được tạo và cấu hình có hiệu lực đúng phạm vi.
- Service ID được gọi khớp với mô hình discovery.
- Service có backend đủ điều kiện theo chính sách readiness.
- Danh tính thực tế có quyền và đường API cần thiết.
- getServices và getInstances phản ánh đúng dữ liệu mong muốn sau đồng bộ.
- Thay đổi endpoint tiếp theo được cập nhật trong hành vi đã kiểm chứng.
- LoadBalancer chọn được instance phù hợp, nếu được sử dụng.
- Request nghiệp vụ tới đích đúng cổng/protocol hoạt động.
- Không giữ các cấu hình chẩn đoán mở rộng quyền hoặc log ngoài nhu cầu.

Kết luận nên nêu nguyên nhân đã xác định, thay đổi đã sửa và bằng chứng tại từng lớp liên quan. Một lần restart hoặc một request thành công đơn lẻ chưa đủ thay thế chuỗi xác minh đó.
