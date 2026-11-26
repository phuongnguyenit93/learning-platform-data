# Ảnh hưởng của headless Service đến danh sách bản sao

## Mục tiêu của bài học

Trong chương **ServiceInstance và cổng** của module **SPRING_CLOUD_KUBERNETES**, bài này giải thích vì sao headless Service làm thay đổi cách tìm địa chỉ đích nhưng không mặc nhiên làm thay đổi số phần tử mà `DiscoveryClient` trả về.

Sau bài học, bạn có thể:

- Phân biệt số replica mong muốn, số Pod đang chạy, số endpoint và số `ServiceInstance`.
- Giải thích khác biệt giữa phân giải DNS và discovery qua Kubernetes API.
- Dự đoán danh sách instance khi Pod chưa Ready hoặc Service bật `publishNotReadyAddresses`.
- Chọn đường gọi qua Service hay gọi trực tiếp từng Pod, đồng thời kiểm tra đúng cổng.

Ví dụ sử dụng ứng dụng Spring Boot `catalog-api` trong namespace `demo`, có ba Pod và phục vụ HTTP trên cổng `8080`. Các địa chỉ IP trong bài chỉ là dữ liệu minh họa.

## 1. Headless Service thay đổi điều gì?

Service thông thường được cấp ClusterIP để client sử dụng một địa chỉ ảo ổn định. Với headless Service, bạn đặt `spec.clusterIP: None`. Kubernetes không cấp ClusterIP và không thực hiện cân bằng tải qua địa chỉ ảo của Service đó. Nếu Service có selector, các backend vẫn được biểu diễn bằng EndpointSlice. [Tài liệu Service của Kubernetes](https://kubernetes.io/docs/concepts/services-networking/service/#headless-services)

Điều này tạo ra hai đường tìm địa chỉ cần phân biệt:

| Đường tìm địa chỉ | Service thông thường | Headless Service |
| --- | --- | --- |
| DNS A/AAAA của tên Service | Trả về ClusterIP theo họ địa chỉ được cấu hình | Trả về các địa chỉ backend đủ điều kiện công bố |
| Discovery qua Kubernetes API | Có thể đọc các endpoint đứng sau Service | Cũng có thể đọc các endpoint đứng sau Service |
| Điểm kết nối khi gọi theo DNS | Địa chỉ ảo của Service | Một địa chỉ backend do client chọn |
| Thành phần quyết định backend | Cơ chế chuyển tiếp Service của cụm | Client hoặc một thành phần khác trên đường đi |

Ví dụ ở cụm chỉ dùng IPv4:

~~~text
catalog-api.demo.svc.cluster.local
    -> 10.96.20.10                 # ClusterIP

catalog-api-headless.demo.svc.cluster.local
    -> 10.42.1.21, 10.42.2.35      # IP của hai backend được công bố
~~~

`cluster.local` là miền giả định trong ví dụ; cụm thực tế có thể dùng miền khác. A/AAAA chứa địa chỉ IP, không chứa cổng. DNS SRV cho cổng được đặt tên có thể cung cấp thêm thông tin cổng và đích. [Tài liệu DNS của Kubernetes](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/#services)

**Không thể lấy số IP trong kết quả DNS của Service thường để kết luận ứng dụng chỉ có một bản sao.** Một ClusterIP có thể đại diện cho nhiều backend.

## 2. DiscoveryClient không chỉ phân giải tên DNS

Với triển khai Kubernetes DiscoveryClient dùng Kubernetes API, lời gọi:

~~~java
List<ServiceInstance> instances =
        discoveryClient.getInstances("catalog-api");
~~~

tìm instance từ tài nguyên discovery mà client được cấu hình sử dụng. Nó không đơn thuần gọi DNS, nhận ClusterIP rồi tạo đúng một instance.

Mỗi `ServiceInstance` cung cấp những dữ liệu để gọi một đích, như `serviceId`, `host`, `port`, `uri` và metadata. Các triển khai Spring Cloud Kubernetes có thể sử dụng Endpoints hoặc EndpointSlice theo cấu hình và phiên bản; thuộc tính `spring.cloud.kubernetes.discovery.use-endpoint-slices=true` chọn đường EndpointSlice ở các phiên bản hỗ trợ. [Tài liệu Kubernetes DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html)

Do đó, nếu hai Service chọn cùng các Pod và áp dụng cùng điều kiện lọc, đổi sang headless không phải lý do để danh sách từ một phần tử trở thành ba phần tử. DiscoveryClient vốn có thể biết từng endpoint của Service thường.

Một mô hình tư duy hữu ích:

~~~text
Deployment.spec.replicas
    -> số Pod bộ điều khiển cố gắng duy trì

Service.spec.selector + trạng thái Pod
    -> backend được biểu diễn trong EndpointSlice

namespace + bộ lọc + readiness + lựa chọn cổng + dữ liệu client đang thấy
    -> danh sách ServiceInstance tại thời điểm truy vấn

thuật toán chọn instance + kết nối HTTP
    -> backend thực sự nhận request
~~~

Các dòng trên là những tầng khác nhau. Chúng không tạo thành một phép đếm đồng bộ tuyệt đối.

## 3. Ví dụ: ba Pod nhưng chỉ hai instance dùng được

Giả sử ba Pod cùng có label `app: catalog-api`:

| Pod | IP | Running | Ready | Cổng HTTP |
| --- | --- | --- | --- | --- |
| catalog-api-a | 10.42.1.21 | Có | Có | 8080 |
| catalog-api-b | 10.42.2.35 | Có | Có | 8080 |
| catalog-api-c | 10.42.3.48 | Có | Không | 8080 |

Tạo hai Service độc lập cùng selector. Đây là hai đối tượng phục vụ so sánh, không phải lệnh chuyển đổi Service đang chạy:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: demo
spec:
  type: ClusterIP
  selector:
    app: catalog-api
  ports:
    - name: http
      protocol: TCP
      port: 8080
      targetPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: catalog-api-headless
  namespace: demo
spec:
  type: ClusterIP
  clusterIP: None
  publishNotReadyAddresses: false
  selector:
    app: catalog-api
  ports:
    - name: http
      protocol: TCP
      port: 8080
      targetPort: 8080
~~~

Headless ở đây vẫn có `type: ClusterIP`; không có giá trị `type: Headless`. Thuộc tính `clusterIP: None` xác định việc không cấp địa chỉ ảo.

Với discovery loại trừ endpoint chưa ready, dữ liệu đã hội tụ, một họ địa chỉ IPv4 và một cổng HTTP, kết quả dự kiến là:

~~~text
getInstances("catalog-api")
    catalog-api          10.42.1.21:8080
    catalog-api          10.42.2.35:8080

getInstances("catalog-api-headless")
    catalog-api-headless 10.42.1.21:8080
    catalog-api-headless 10.42.2.35:8080
~~~

Hai danh sách có cùng tập đích mạng, nhưng khác `serviceId` vì thuộc về hai Service khác tên. Không so sánh chúng bằng cách giả định toàn bộ đối tượng hoặc `instanceId` phải giống nhau.

Trong kịch bản này:

~~~text
replica mong muốn             = 3
Pod Running                   = 3
Pod Ready                     = 2
instance của mỗi Service      = 2
ClusterIP của Service thường  = 1 địa chỉ IPv4
~~~

Khi Pod thứ ba chuyển Ready, danh sách có thể tăng lên ba sau khi các thành phần liên quan cập nhật. Nguyên nhân là backend đủ điều kiện, không phải vì headless tạo thêm Pod.

## 4. Readiness và hai cơ chế dễ bị nhầm

### 4.1. Lọc ở phía Spring Cloud Kubernetes

Thuộc tính sau điều khiển việc đưa địa chỉ chưa được Kubernetes đánh dấu ready vào kết quả discovery:

~~~properties
spring.cloud.kubernetes.discovery.include-not-ready-addresses=false
~~~

Giá trị mặc định được tài liệu Spring Cloud Kubernetes mô tả là `false`. Bật thành `true` có thể hữu ích cho công cụ quan sát muốn tìm cả instance chưa sẵn sàng; nó cũng có thể đưa đích chưa đủ điều kiện xử lý nghiệp vụ vào danh sách mà client sử dụng. [Thuộc tính discovery](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html)

Đây là cấu hình phía discovery. Nó không tự thay đổi readiness probe của Pod và không buộc DNS Kubernetes công bố thêm bản ghi.

### 4.2. Công bố endpoint ở phía Kubernetes Service

Service có thể bật:

~~~yaml
spec:
  clusterIP: None
  publishNotReadyAddresses: true
~~~

Với endpoint do Kubernetes quản lý, cờ này yêu cầu bỏ qua phân biệt ready/not-ready để công bố endpoint; controller có thể biểu diễn endpoint là ready ngay cả khi Pod chưa Ready. Vì vậy, `include-not-ready-addresses=false` ở phía Spring không bảo đảm loại được Pod chưa Ready trong trường hợp này. [Định nghĩa API Service](https://kubernetes.io/docs/reference/kubernetes-api/core/service-v1/)

Giữ nguyên ví dụ ba Pod, giả định các endpoint đã tồn tại và bỏ qua trạng thái terminating:

| publishNotReadyAddresses | include-not-ready-addresses | Kết quả dự kiến |
| --- | --- | --- |
| false | false | Hai endpoint ready |
| false | true | Có thể gồm cả endpoint của Pod chưa Ready |
| true | false | Có thể gồm cả ba vì endpoint đã được công bố là ready |
| true | true | Cũng có thể gồm cả ba |

Bảng là dự đoán cho điều kiện nêu trên, không phải cam kết rằng mọi trạng thái chuyển tiếp đều cho một con số cố định. Pod chưa có IP hoặc chưa được controller đưa vào endpoint không xuất hiện chỉ vì bật một trong hai cờ.

Một tình huống thực tế là nhóm thành viên cần nhìn thấy nhau trước khi hoàn tất khởi tạo. Nếu readiness lại phụ thuộc việc tìm được thành viên, yêu cầu mọi thành viên Ready trước discovery có thể tạo vòng chờ. Công bố địa chỉ sớm giúp bước nhận diện thành viên, nhưng ứng dụng vẫn phải xử lý trường hợp thành viên chưa nhận được request nghiệp vụ.

Nếu có cả nhu cầu tìm peer và nhu cầu gọi nghiệp vụ, có thể thiết kế hai Service với chính sách công bố khác nhau: một Service cho peer discovery, một Service cho traffic cần readiness. Khi đó phải nêu rõ Service nào được từng client sử dụng.

## 5. Số ServiceInstance không phải số replica chính thức

Trong ví dụ đơn giản, một endpoint IPv4 trên một cổng tương ứng một Pod nên việc đếm khá trực quan. Ngoài thực tế, cần kiểm tra thêm:

- **Selector:** Service có thể chọn ít Pod hơn Deployment, hoặc chọn Pod từ nhiều workload nếu label trùng.
- **Namespace:** Nếu discovery tìm nhiều namespace, các Service cùng tên có thể làm phạm vi kết quả rộng hơn dự kiến.
- **Readiness và vòng đời:** Pod đang khởi động, kết thúc hoặc thay thế có thể xuất hiện khác nhau tại các thời điểm quan sát.
- **Nhiều EndpointSlice:** Một Service có thể có nhiều slice. Đếm số slice không phải đếm backend.
- **Nhiều họ địa chỉ và nhiều nhóm cổng:** Một Pod hoặc một Service có thể được biểu diễn qua nhiều đối tượng mạng; cần đối chiếu danh tính và địa chỉ trước khi kết luận có thêm replica.
- **Endpoint được quản lý thủ công:** Service không có selector không tự được controller tạo EndpointSlice từ Pod; backend có thể không đại diện cho replica của Deployment.

EndpointSlice có thể chứa `targetRef` trỏ về Pod và các điều kiện `ready`, `serving`, `terminating`. Khi tổng hợp thủ công, cần đọc các slice thuộc Service và xử lý endpoint trùng; không cộng mù quáng số dòng địa chỉ. [Tài liệu EndpointSlice](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/)

Để tìm số replica mong muốn, hãy xem workload tương ứng. Để tìm đích mà client có thể chọn lúc này, hãy quan sát danh sách instance của chính client. Hai câu hỏi này cần hai nguồn dữ liệu khác nhau.

## 6. Headless Service không chuyển tiếp cổng giúp client

Trong ví dụ ban đầu, tất cả dùng `8080` để cô lập ảnh hưởng của headless. Xét một cấu hình khác:

~~~yaml
ports:
  - name: http
    port: 80
    targetPort: 8080
~~~

Với Service thông thường, kết nối vào `ClusterIP:80` có thể được chuyển tiếp tới backend trên `8080`.

Với tên DNS của headless Service, A/AAAA đưa client tới IP backend. Nếu HTTP client xây URL `http://catalog-api-headless:80`, nó có thể kết nối thẳng `PodIP:80`. Việc YAML ghi `targetPort: 8080` không tạo một bộ chuyển tiếp `80 -> 8080` tại địa chỉ Pod.

Vì vậy, luôn ghi lại cặp **host và port** mà client thực sự dùng:

~~~text
10.42.1.21:8080  # đích đúng nếu ứng dụng đang nghe 8080
10.42.1.21:80    # không tương đương chỉ vì Service có port 80
~~~

Với discovery dựa trên endpoint, kiểm tra cổng được biểu diễn trong tài nguyên endpoint và giá trị `ServiceInstance.getPort()`. Khi có nhiều cổng, khai báo tên rõ ràng và cấu hình cổng chính thay vì dựa vào vị trí phần tử.

Headless không tự bật HTTPS. Scheme, cổng và chứng chỉ phải phù hợp với đường kết nối trực tiếp tới backend; nếu dùng TLS, cần xét cả tên mà client dùng để xác thực chứng chỉ.

## 7. Spring Cloud LoadBalancer nhìn danh sách nào?

Spring Cloud Kubernetes LoadBalancer có chế độ `POD` và `SERVICE`. Trong chế độ `POD`, nó dùng DiscoveryClient để lấy các instance. Chế độ `SERVICE` xây đích theo tên DNS của Service và cổng Service. [Tài liệu LoadBalancer](https://docs.spring.io/spring-cloud-kubernetes/reference/load-balancer.html)

Điều đó dẫn đến các cách đọc kết quả khác nhau:

| Cách gọi | Tập đích mà ứng dụng cần hiểu |
| --- | --- |
| LoadBalancer chế độ POD | Những instance discovery trả về sau các bước lọc và cập nhật dữ liệu |
| LoadBalancer chế độ SERVICE với Service thường | Tên Service dẫn tới địa chỉ ảo; cụm chuyển tiếp tới backend |
| Đường gọi DNS tới headless Service | Tên Service có thể dẫn tới nhiều IP; cách resolver và HTTP client sử dụng chúng quyết định kết nối |

Với headless, việc có nhiều địa chỉ DNS không chứng minh client đã chọn đều các Pod. Resolver có thể cache; HTTP client có thể tái sử dụng kết nối tới một địa chỉ. Đếm số request qua một kết nối đang được giữ lại không phải phép kiểm tra đầy đủ cho khả năng khám phá bản sao.

Khi mục tiêu là client chọn từng Pod dựa trên metadata hoặc chính sách riêng, hãy quan sát đường discovery ở chế độ POD. Khi mục tiêu chỉ là gọi một API qua Service ổn định, Service thường và DNS Kubernetes có thể đáp ứng yêu cầu mà không cần đưa danh sách từng Pod vào ứng dụng.

## 8. Quan sát ServiceInstance trong ứng dụng Spring

Giả định ứng dụng đã có Kubernetes DiscoveryClient phù hợp với bộ phiên bản Spring Boot/Spring Cloud đang dùng. Ví dụ cấu hình cho phép quan sát EndpointSlice trong namespace `demo`:

~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        all-namespaces: false
        namespaces:
          - demo
        use-endpoint-slices: true
        include-not-ready-addresses: false
        primary-port-name: http
      loadbalancer:
        mode: POD
~~~

Phần `loadbalancer` chỉ cần khi ứng dụng có tích hợp LoadBalancer tương ứng. Các thuộc tính discovery cần đặt tại thành phần thực sự đọc Kubernetes API; nếu dùng Discovery Server qua HTTP, hãy cấu hình và phân quyền phía server theo kiến trúc đó.

Có thể thêm controller chẩn đoán trong môi trường thực hành:

~~~java
package example.discovery;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DiscoveryInspectionController {

    private final DiscoveryClient discoveryClient;

    public DiscoveryInspectionController(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @GetMapping("/internal/discovery/{serviceId}")
    public List<Map<String, Object>> inspect(
            @PathVariable("serviceId") String serviceId) {

        return discoveryClient.getInstances(serviceId).stream()
                .map(this::describe)
                .toList();
    }

    private Map<String, Object> describe(ServiceInstance instance) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("serviceId", instance.getServiceId());
        row.put("instanceId", instance.getInstanceId());
        row.put("host", instance.getHost());
        row.put("port", instance.getPort());
        row.put("uri", instance.getUri().toString());
        row.put("metadata", instance.getMetadata());
        return row;
    }
}
~~~

Đoạn Java dùng `Stream.toList()`, cần Java 16 trở lên. Đường chẩn đoán nên chỉ truy cập được trong môi trường hoặc mạng được phép quan sát hạ tầng.

Gọi lần lượt:

~~~text
GET /internal/discovery/catalog-api
GET /internal/discovery/catalog-api-headless
~~~

So sánh tập `host:port`, `serviceId` và namespace trong metadata nếu có. Không dựa vào thứ tự mảng để gán ý nghĩa “Pod số một”, cũng không dùng IP làm định danh bền vững của thành viên sau khi Pod được tạo lại.

Đây là thao tác liệt kê đích; controller chưa gửi HTTP tới từng đích. Có instance trong danh sách không chứng minh đường mạng, ứng dụng và TLS đều hoạt động.

## 9. RBAC cần theo đúng đường discovery

Ứng dụng gọi DNS thông thường không cần quyền đọc Kubernetes API chỉ để phân giải tên. Client hoặc Discovery Server đọc API phải có quyền tương ứng.

Ví dụ dưới đây là phần quyền đọc Service và EndpointSlice ở namespace `demo`, dành cho đường EndpointSlice trong bài:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: catalog-discovery-reader
  namespace: demo
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
  name: catalog-discovery-reader
  namespace: demo
subjects:
  - kind: ServiceAccount
    name: catalog-caller
    namespace: demo
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: catalog-discovery-reader
~~~

Giả định ServiceAccount `catalog-caller` đã tồn tại và Pod gọi API sử dụng account đó. Đây là quyền cho hai loại tài nguyên đang xét, không phải bộ quyền tổng quát cho mọi tính năng Spring Cloud Kubernetes.

Nếu client dùng Endpoints, phải cấp quyền cho `endpoints` trong API group rỗng. Nếu một chức năng khác cần đọc Pod metadata, cần xem thêm yêu cầu quyền của chức năng đó. Không thêm quyền đọc Secret hay ConfigMap chỉ để khắc phục việc thiếu quyền đọc EndpointSlice.

## 10. Quy trình đối chiếu trên môi trường thực hành

Các lệnh dưới đây dành cho người học chạy ở cụm đã có ví dụ tương ứng. Chúng không tự triển khai workload hoặc tự tạo Service.

### Bước 1: Kiểm tra selector và loại Service

~~~sh
kubectl -n demo get service catalog-api catalog-api-headless -o yaml
kubectl -n demo get pods -l app=catalog-api -o wide
~~~

Đối chiếu `clusterIP`, selector, `publishNotReadyAddresses`, tên cổng, `port` và `targetPort`. Kiểm tra label trên Pod thay vì chỉ nhìn tên Deployment.

### Bước 2: Đọc toàn bộ EndpointSlice của từng Service

~~~sh
kubectl -n demo get endpointslices \
  -l kubernetes.io/service-name=catalog-api -o yaml

kubectl -n demo get endpointslices \
  -l kubernetes.io/service-name=catalog-api-headless -o yaml
~~~

Lệnh nhiều dòng sử dụng cú pháp shell kiểu POSIX; với PowerShell có thể đặt cả lệnh trên một dòng.

Ghi lại:

- `addressType`, `endpoints[].addresses` và `targetRef` nếu có.
- `conditions.ready`, `serving`, `terminating` nếu được biểu diễn.
- `ports[].name` và `ports[].port`.

Nếu ứng dụng đọc Endpoints, đối chiếu thêm đúng tài nguyên đó:

~~~sh
kubectl -n demo get endpoints catalog-api catalog-api-headless -o yaml
~~~

### Bước 3: Kiểm tra DNS từ một Pod trong cụm

Nếu Pod công cụ `dns-tools` đã tồn tại và có `nslookup`:

~~~sh
kubectl -n demo exec dns-tools -- \
  nslookup catalog-api.demo.svc.cluster.local

kubectl -n demo exec dns-tools -- \
  nslookup catalog-api-headless.demo.svc.cluster.local
~~~

Phân biệt địa chỉ của DNS server trong output với phần câu trả lời cho Service. Nếu dữ liệu DNS và API chưa khớp ngay, ghi thời điểm quan sát và xét thời gian cập nhật/cache trước khi kết luận.

### Bước 4: Quan sát ứng dụng

Dùng controller chẩn đoán ở phần trước để lấy hai danh sách. Với dữ liệu đã hội tụ như ví dụ, kỳ vọng hai đích `10.42.1.21:8080` và `10.42.2.35:8080` trong mỗi danh sách.

Sau khi một Pod chuyển trạng thái readiness trong môi trường thử nghiệm, quan sát lại cả tài nguyên Kubernetes và kết quả từ ứng dụng. Đừng chỉ đợi một khoảng thời gian cố định rồi coi mọi lớp cache đã đồng bộ.

### Bước 5: Kiểm tra đích nhận request

Nếu ứng dụng đích có endpoint trả về tên Pod, gửi nhiều request bằng đúng HTTP client thực tế sẽ dùng. So sánh với tập instance đã khám phá, đồng thời xem log kết nối và lỗi.

Phép quan sát này giúp tách ba câu hỏi: client nhìn thấy đích nào, client chọn đích nào và đích đó có xử lý thành công hay không.

## 11. Các chẩn đoán thường gặp

| Hiện tượng | Điều nên kiểm tra |
| --- | --- |
| Headless DNS trả nhiều IP nhưng DiscoveryClient rỗng | Namespace, bộ lọc Service, RBAC, API discovery được chọn và log client |
| Có ba Pod Running nhưng chỉ hai instance | Readiness, PodIP, endpoint của Pod còn lại và thời điểm cập nhật |
| Bật headless nhưng số instance không đổi | Có thể hoàn toàn đúng nếu trước đó discovery đã liệt kê từng endpoint |
| Đặt include-not-ready-addresses=false nhưng vẫn thấy Pod chưa Ready | publishNotReadyAddresses và trạng thái ready thực tế của endpoint |
| Instance tồn tại nhưng gọi bị connection refused | host:port, cổng ứng dụng đang nghe và vòng đời Pod |
| Chỉ một Pod nhận nhiều request qua headless DNS | Resolver, cache, connection pool và cách HTTP client chọn địa chỉ |
| Hai danh sách có vẻ chứa bản sao trùng | Phạm vi namespace, họ địa chỉ, nhiều slice và cách tổng hợp dữ liệu |
| Gọi PodIP thất bại nhưng gọi Service thành công | Cổng, NetworkPolicy, đường đi qua proxy/mesh và TLS của hai cách gọi |

Ví dụ: nếu `catalog-api-c` chưa Ready nhưng xuất hiện trong danh sách, đừng lập tức giảm replica hoặc đổi thuật toán LoadBalancer. Trước hết đọc endpoint của chính Pod đó và kiểm tra cờ công bố địa chỉ. Cách này tìm nguyên nhân ở tầng tạo dữ liệu trước khi sửa tầng chọn đích.

## 12. Lựa chọn tính năng cho triển khai

Headless Service phù hợp khi ứng dụng cần nhận diện từng backend hoặc tự thực hiện cơ chế tìm thành viên. Nó không tự cung cấp thuật toán phân phối request, kiểm tra sức khỏe ứng dụng hay quản lý replica.

Với ứng dụng Spring chỉ cần gọi API qua tên Service, hãy bắt đầu từ yêu cầu kết nối cụ thể. Chỉ thêm DiscoveryClient và Spring Cloud LoadBalancer khi ứng dụng cần danh sách endpoint, metadata hoặc quyền lựa chọn đích ở phía client.

ConfigMap, Secret và Configuration Watcher phục vụ quản lý cấu hình trong phạm vi module, nhưng không phải thành phần tạo ra danh sách replica cho headless Service. Nếu ứng dụng dùng cấu hình ngoài để điều khiển readiness hoặc discovery, việc cấu hình được cập nhật vẫn cần được quan sát riêng với việc endpoint đã thay đổi.

Khi đọc một danh sách `ServiceInstance`, hãy luôn gắn nó với **Service nào, namespace nào, nguồn endpoint nào, điều kiện readiness nào và cổng nào**. Đó là cơ sở để giải thích chính xác vì sao có hai, ba hoặc không có đích tại thời điểm quan sát.
