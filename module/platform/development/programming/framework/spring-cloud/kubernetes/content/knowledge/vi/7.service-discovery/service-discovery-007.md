# Khám phá Pod chưa sẵn sàng khi có yêu cầu đặc biệt

Thuộc chương **Khám phá dịch vụ** của module **SPRING_CLOUD_KUBERNETES**.

Spring Cloud Kubernetes hỗ trợ tích hợp ứng dụng Spring với Kubernetes qua DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer và Configuration Watcher. Trong bài này, ta tập trung vào một lựa chọn có phạm vi hẹp: cho phép một thành phần quan sát hoặc khởi tạo cụm tìm thấy cả endpoint của Pod chưa sẵn sàng. Nội dung gắn lựa chọn đó với readiness, quyền RBAC và cách sử dụng danh sách instance sau discovery.

Sau bài học, bạn có thể:

- Giải thích vì sao Pod đang chạy vẫn có thể không xuất hiện trong danh sách instance dùng cho nghiệp vụ.
- Bật khám phá địa chỉ chưa sẵn sàng cho đúng ứng dụng cần quan sát hoặc tìm peer.
- Phân biệt cấu hình của DiscoveryClient với việc Kubernetes công bố endpoint chưa sẵn sàng.
- Kiểm chứng hành vi bằng trạng thái Pod, EndpointSlice và kết quả DiscoveryClient, thay vì chỉ nhìn số lượng instance.

## 1. Địa chỉ tồn tại và ứng dụng sẵn sàng là hai điều khác nhau

Xét dịch vụ `catalog-api` có ba Pod. Hai Pod đã nạp dữ liệu và phục vụ bình thường; Pod còn lại đang làm nóng bộ nhớ đệm. Pod thứ ba đã có IP và có thể đã mở cổng HTTP, nhưng chưa nên nhận yêu cầu tra cứu sản phẩm.

Trong thiết kế này, việc không đưa Pod đang khởi tạo vào danh sách phục vụ là hành vi mong muốn. Tuy nhiên, thành phần giám sát có thể vẫn cần truy cập Pod đó để biết vì sao quá trình khởi tạo kéo dài.

| Quan sát | Điều có thể kết luận | Điều chưa thể kết luận |
| --- | --- | --- |
| Pod có IP | Đã có một địa chỉ để tham chiếu | Cổng đích đang lắng nghe |
| Pod có phase `Running` | Pod đã đi vào giai đoạn chạy | Tất cả điều kiện để nhận nghiệp vụ đã thỏa mãn |
| Kết nối TCP thành công | Đường mạng và listener đáp ứng tại thời điểm kiểm tra | Xử lý đơn hàng, giao dịch hoặc truy vấn sẽ thành công |
| Pod có condition `Ready=True` | Kubernetes ghi nhận Pod sẵn sàng theo các điều kiện đã cấu hình | Ứng dụng sẽ luôn thành công sau thời điểm kiểm tra |
| DiscoveryClient trả về một instance | Instance thuộc tập kết quả theo cấu hình discovery hiện tại | Có thể bỏ qua timeout, xác thực hoặc kiểm tra giao thức |

Readiness probe giúp Kubernetes quyết định khả năng nhận lưu lượng của Pod; liveness probe phục vụ phát hiện tình trạng cần khởi động lại container. Startup probe dành cho giai đoạn khởi động trước khi các probe còn lại bắt đầu. Readiness thất bại không tự làm container khởi động lại. Vì vậy, không nên đổi sang liveness hoặc xóa readiness chỉ để một công cụ nhìn thấy Pod. [Tài liệu Kubernetes về các loại probe](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

Trong bài này, “khám phá Pod” là cách nói ngắn cho việc khám phá **địa chỉ endpoint của Service được hậu thuẫn bởi Pod**. Đây không phải thao tác liệt kê mọi Pod của namespace. Pod chưa được lập lịch, chưa có IP hoặc không thuộc tập endpoint liên quan không tự xuất hiện chỉ nhờ bật một thuộc tính.

## 2. Khi nào cần nhìn thấy endpoint chưa sẵn sàng?

### 2.1. Quan sát một instance đang khởi tạo hoặc gặp lỗi

Một ứng dụng quan sát nội bộ có thể cần tìm từng instance để kiểm tra cổng quản trị, ghi nhận tiến độ warm-up hoặc đối chiếu lỗi kết nối. Nếu chỉ thấy các instance đã Ready, ứng dụng quan sát sẽ thiếu đúng nhóm cần điều tra.

Đường kiểm tra này nên có mục đích cụ thể: lấy trạng thái, không làm thay đổi dữ liệu nghiệp vụ. Nếu tiến trình chưa mở cổng, timeout hoặc lỗi kết nối là một kết quả cần được ghi nhận, thay vì một lý do để lập tức gửi thêm nhiều yêu cầu.

Spring Boot thường cung cấp thông tin sức khỏe qua `/actuator/health`, cùng các nhóm `/actuator/health/liveness` và `/actuator/health/readiness`. Cổng và đường dẫn thực tế phụ thuộc cấu hình ứng dụng. Probe của Kubernetes cũng có thể kiểm tra một điều kiện khác với nhóm readiness của Actuator. [Tài liệu Spring Boot về health và Kubernetes probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).

### 2.2. Các thành viên cần tìm nhau trước khi sẵn sàng

Giả sử một cụm xử lý phân tán cần trao đổi thông tin peer trước khi công bố khả năng nhận yêu cầu. Có thể xuất hiện vòng chờ:

~~~text
Muốn Ready -> phải tìm đủ peer
Muốn được peer tìm thấy -> phải Ready
~~~

Cho phép khám phá endpoint chưa sẵn sàng có thể giúp phá vỡ vòng chờ **nếu giao thức peer đã hoạt động trong giai đoạn đó**. Nó không tự tạo quorum, không tự hoàn tất đồng bộ và không khắc phục một listener chưa được mở.

Nếu hệ thống dùng DNS để tìm peer, cần thiết kế ở tầng Kubernetes Service/DNS. Nếu hệ thống dùng DiscoveryClient gọi Kubernetes API, cần xem cấu hình ở phía discovery. Hai đường tìm kiếm này có điểm cấu hình khác nhau.

### 2.3. Khi nào nên giữ hành vi mặc định?

Giữ chính sách chỉ nhận endpoint sẵn sàng cho các ứng dụng đặt hàng, thanh toán hoặc API công khai. Nếu mục tiêu chỉ là gọi một Service bình thường trong cluster, hãy đánh giá khả năng dùng DNS và Service trước khi bổ sung discovery ở phía ứng dụng.

Một yêu cầu ngoại lệ cần nêu được người tiêu thụ danh sách endpoint, giao thức được phép dùng và lý do phải liên lạc trước readiness. “Muốn có nhiều instance hơn” chưa phải một lý do vận hành đủ rõ.

## 3. Cấu hình trọng tâm của Spring Cloud Kubernetes

Thuộc tính cần dùng là:

~~~properties
spring.cloud.kubernetes.discovery.include-not-ready-addresses=true
~~~

Giá trị mặc định là `false`. Khi bật, discovery có thể đưa thêm các địa chỉ endpoint chưa được Kubernetes đánh dấu sẵn sàng vào kết quả. Spring nêu việc kiểm tra sức khỏe instance chưa Ready là một trường hợp sử dụng của tính năng này. [DiscoveryClient for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Ví dụ đặt trong cấu hình của **ứng dụng quan sát**:

~~~yaml
spring:
  application:
    name: endpoint-inspector
  cloud:
    kubernetes:
      discovery:
        all-namespaces: false
        namespaces:
          - discovery-lab
        include-not-ready-addresses: true
        use-endpoint-slices: true
        primary-port-name: http
~~~

Trong ví dụ:

- `discovery-lab` là namespace của lab, không phải namespace mặc định áp dụng cho mọi hệ thống.
- `include-not-ready-addresses` mở rộng tập ứng viên được khám phá.
- `use-endpoint-slices` chọn nguồn endpoint là EndpointSlice; cần phiên bản thư viện hỗ trợ và quyền đọc API tương ứng.
- `primary-port-name` giúp xác định cổng khi Service có nhiều cổng; lab dùng một cổng `http` để việc đối chiếu đơn giản.

Các thuộc tính và giá trị mặc định nên được đối chiếu với đúng dòng Spring Cloud Kubernetes đang dùng. Bài không ấn định phiên bản Spring Boot, Spring Cloud hoặc starter cho dự án của bạn. [Danh mục cấu hình Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

Có thể đặt nhóm cấu hình trên trong profile `inspection` của ứng dụng quan sát. Ứng dụng phục vụ nghiệp vụ giữ cấu hình riêng:

~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        include-not-ready-addresses: false
~~~

Đây là lựa chọn ảnh hưởng tới discovery của tiến trình sử dụng nó. Khi cùng một DiscoveryClient được nhiều thành phần trong ứng dụng sử dụng, cần xác định tất cả nơi tiêu thụ trước khi bật. Một profile chỉ giúp tổ chức cấu hình; nó không tự tạo hai DiscoveryClient có chính sách độc lập trong cùng application context.

Không giả định rằng sửa ConfigMap sẽ làm chính sách này đổi ngay trong tiến trình đang chạy. Cách nạp lại thuộc tính phụ thuộc cấu hình và vòng đời bean. Trong lab, khởi động lại ứng dụng quan sát sau mỗi lần đổi thuộc tính để kết quả đối chiếu rõ ràng. Không cần bật Configuration Watcher hoặc đọc Secret chỉ để minh họa tùy chọn discovery này.

## 4. DiscoveryClient và Kubernetes Service tác động ở những tầng khác nhau

~~~mermaid
flowchart TD
    P["Pod và trạng thái Ready"] --> E["EndpointSlice hoặc Endpoints"]
    E --> D["Spring Cloud Kubernetes DiscoveryClient"]
    D --> C["Danh sách ServiceInstance"]
    C --> O["Ứng dụng quan sát hoặc giao thức peer"]
    C --> L["Bộ chọn instance nếu được cấu hình sử dụng"]
    L --> B["Lời gọi nghiệp vụ"]
    E --> K["Cơ chế Service và DNS của Kubernetes"]
    K --> N["Client gọi tên Service"]
~~~

Thuộc tính `include-not-ready-addresses` điều chỉnh nhánh DiscoveryClient. Nó không trực tiếp sửa condition của Pod, không viết lại Service và không cấu hình CoreDNS.

Với nguồn Endpoints truyền thống, dữ liệu phân biệt `addresses` và `notReadyAddresses`. Với EndpointSlice, thông tin nằm trong các condition của từng endpoint. Bài dùng EndpointSlice cho lab; khi triển khai trên hệ thống khác, cần kiểm tra đúng backend và phiên bản discovery thực tế.

EndpointSlice có các condition `ready`, `serving` và `terminating`. Khi `publishNotReadyAddresses` không bật, `ready` thường thể hiện endpoint đang phục vụ và không kết thúc. Một endpoint đang terminating cần được xử lý theo giao thức dừng của ứng dụng, thay vì coi mọi endpoint chưa Ready đều là một Pod đang warm-up. [Tài liệu Kubernetes về condition của EndpointSlice](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/).

### 4.1. Thuộc tính publishNotReadyAddresses

Kubernetes Service có trường:

~~~yaml
spec:
  publishNotReadyAddresses: true
~~~

Trường này yêu cầu các thành phần xử lý endpoint của Service bỏ qua phân biệt ready/not-ready. Controller Kubernetes có thể công bố endpoint là ready dù Pod phía sau chưa Ready. Một trường hợp sử dụng chính là headless Service của StatefulSet phục vụ tìm peer qua DNS. [Đặc tả Kubernetes Service](https://kubernetes.io/docs/reference/kubernetes-api/core/service-v1/).

| Cấu hình | Nơi đặt | Mục đích thiết kế |
| --- | --- | --- |
| `include-not-ready-addresses: true` | Ứng dụng hoặc thành phần discovery Spring | Cho thành phần đó lấy thêm endpoint chưa sẵn sàng |
| `publishNotReadyAddresses: true` | Kubernetes Service | Công bố endpoint của Service theo chính sách bỏ qua readiness |
| Readiness probe | Cấu hình container trong Pod | Cung cấp tín hiệu sẵn sàng theo điều kiện kiểm tra |
| Bộ lọc hoặc bộ chọn instance | Thành phần tiêu thụ kết quả discovery | Quyết định có dùng một ứng viên cho loại yêu cầu cụ thể hay không |

Hệ quả cần lưu ý: khi Service công bố endpoint bất kể readiness, cấu hình discovery `include-not-ready-addresses: false` không đủ để suy ra Pod thực sự Ready. Discovery có thể chỉ nhìn thấy dữ liệu đã được công bố dưới dạng ready.

Nếu cần cả đường peer và đường nghiệp vụ, có thể thiết kế hai Service cùng chọn một nhóm Pod nhưng phục vụ hai mục đích:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: worker-peers
  namespace: discovery-lab
spec:
  clusterIP: None
  publishNotReadyAddresses: true
  selector:
    app: cluster-worker
  ports:
    - name: peer
      port: 7800
      targetPort: peer
---
apiVersion: v1
kind: Service
metadata:
  name: worker-api
  namespace: discovery-lab
spec:
  publishNotReadyAddresses: false
  selector:
    app: cluster-worker
  ports:
    - name: http
      port: 8080
      targetPort: http
~~~

Đây là phương án kiến trúc minh họa, tách khỏi lab ở phần sau. Workload tương ứng phải thực sự mở các cổng có tên `peer` và `http`; nếu là StatefulSet thì cấu hình governing Service phải khớp với thiết kế. Giao thức peer cần chấp nhận trạng thái khởi tạo, có xác thực và giới hạn thời gian trao đổi. Không bật công bố endpoint chưa Ready trên Service nghiệp vụ chỉ để giải quyết vòng chờ của giao thức peer.

## 5. Một ứng dụng Spring chỉ dùng để quan sát

### 5.1. Điều kiện sử dụng ví dụ

Ví dụ Java dùng Java 17 trở lên và API Servlet của Spring Web. Ứng dụng cần Spring Boot Web, Actuator nếu sử dụng health endpoint và **một** starter discovery phù hợp, chẳng hạn `org.springframework.cloud:spring-cloud-starter-kubernetes-fabric8`. Quản lý phiên bản theo BOM tương thích của dự án.

Các lớp mẫu dưới đây thuộc cùng package. Không cần thêm Spring Cloud LoadBalancer chỉ để liệt kê instance. Trong lab, ứng dụng chạy trong cluster với ServiceAccount được chỉ định; máy phát triển thường không có đường mạng trực tiếp tới Pod IP.

~~~java
package example.discovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;

@SpringBootApplication
@EnableDiscoveryClient
public class EndpointInspectorApplication {

    public static void main(String[] args) {
        SpringApplication.run(EndpointInspectorApplication.class, args);
    }
}
~~~

### 5.2. Đọc danh sách địa chỉ, chưa gửi yêu cầu nghiệp vụ

~~~java
package example.discovery;

import java.util.List;

import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("inspection")
public class EndpointInspectionController {

    private final DiscoveryClient discoveryClient;

    public EndpointInspectionController(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @GetMapping("/internal/discovery/readiness-demo")
    public List<Target> targets() {
        return discoveryClient.getInstances("readiness-demo")
                .stream()
                .map(instance -> new Target(
                        instance.getHost(),
                        instance.getPort(),
                        instance.getScheme()))
                .toList();
    }

    public record Target(String host, int port, String scheme) {
    }
}
~~~

Đường dẫn cố định vào Service của lab giúp ví dụ không biến thành API cho phép người gọi tùy ý thăm dò mọi tên dịch vụ. Endpoint này vẫn cần được giới hạn truy cập trong môi trường triển khai thực tế.

Giả sử dữ liệu quan sát được là:

~~~json
[
  {"host": "10.42.1.20", "port": 8080, "scheme": "http"},
  {"host": "10.42.2.31", "port": 8080, "scheme": "http"}
]
~~~

Các IP trên chỉ minh họa. Không suy luận instance đầu tiên Ready và instance thứ hai NotReady từ vị trí trong mảng. Danh sách có thể đổi thứ tự; kiểu `ServiceInstance` không phải hợp đồng chứa đầy đủ condition của Pod hay EndpointSlice. Ví dụ cố ý không tạo trường `ready` từ một metadata không được bảo đảm tồn tại.

Để đối chiếu readiness, dùng dữ liệu Kubernetes tương ứng hoặc một hợp đồng quản trị được thiết kế riêng. Một lần gọi HTTP trả 200 chỉ chứng minh thao tác đó đã thành công tại thời điểm gọi; nó không thay thế mọi điều kiện readiness của Pod.

### 5.3. Nếu cần kiểm tra sức khỏe từng địa chỉ

Khi đã có quyền truy cập và biết đúng cổng quản trị, có thể kiểm tra từ một môi trường trong cluster:

~~~bash
curl --connect-timeout 1 --max-time 3 -i   http://10.42.2.31:8080/actuator/health/readiness
~~~

Thay địa chỉ bằng endpoint thực tế. Đây là ví dụ cho ứng dụng Spring Boot có Actuator trên cổng 8080; workload BusyBox trong lab không có đường dẫn Actuator.

Khi triển khai bộ quan sát, nên ghi nhận riêng ít nhất ba kết quả: phản hồi HTTP có trạng thái sức khỏe, lỗi kết nối và hết thời gian chờ. Giới hạn số yêu cầu đồng thời, khoảng thời gian giữa các lần kiểm tra và tổng thời gian xử lý một vòng. Gọi dồn tới mọi Pod đang khởi tạo có thể làm quá trình khởi tạo chậm thêm.

Nếu dùng HTTPS hoặc cổng quản trị riêng, cần dùng đúng scheme, cổng, chứng thư và cơ chế xác thực. Không gắn đường dẫn quản trị vào mọi URI được discovery trả về mà chưa kiểm tra hợp đồng của Service.

## 6. RBAC cho ứng dụng quan sát

Trong lab dùng EndpointSlice, ứng dụng cần đọc Service và EndpointSlice trong namespace `discovery-lab`. Không cần quyền ghi các tài nguyên này.

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: discovery-lab
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: endpoint-inspector
  namespace: discovery-lab
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: endpoint-inspector-reader
  namespace: discovery-lab
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
  name: endpoint-inspector-reader
  namespace: discovery-lab
subjects:
  - kind: ServiceAccount
    name: endpoint-inspector
    namespace: discovery-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: endpoint-inspector-reader
~~~

RoleBinding liên kết ServiceAccount với Role có phạm vi namespace. Khi cần đọc nhiều namespace, phải thiết kế quyền cho các namespace đó; thay một thuộc tính discovery không tự cấp thêm quyền. [Tài liệu Kubernetes về Role và RoleBinding](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Đây là quyền dành cho phạm vi minh họa. Nếu phiên bản hoặc tính năng discovery đang dùng còn đọc Endpoints hay Pod, hãy xác định yêu cầu API cụ thể rồi bổ sung quyền đọc tương ứng. Không mặc định cấp `cluster-admin`; cũng không thêm quyền đọc ConfigMap và Secret cho một ứng dụng chỉ cần liệt kê endpoint.

Kiểm tra bằng tài khoản vận hành được phép kiểm tra quyền hoặc impersonate ServiceAccount:

~~~bash
kubectl auth can-i list services   --namespace discovery-lab   --as system:serviceaccount:discovery-lab:endpoint-inspector

kubectl auth can-i watch endpointslices.discovery.k8s.io   --namespace discovery-lab   --as system:serviceaccount:discovery-lab:endpoint-inspector
~~~

Nếu tài khoản đang chạy lệnh không được phép impersonate, lỗi của phép kiểm tra không tự chứng minh Role của ứng dụng sai. Cần kiểm tra trong bối cảnh xác thực thích hợp.

RBAC cho phép đọc API Kubernetes. Khả năng kết nối tới Pod IP còn phụ thuộc routing, NetworkPolicy, service mesh, cổng lắng nghe và xác thực của ứng dụng. Hai nhóm quyền này cần được kiểm chứng riêng.

## 7. Lab: một Pod Ready và một Pod NotReady

### 7.1. Mục tiêu và điều kiện

Lab tách hai hiện tượng để dễ quan sát:

1. Cả hai container đều phục vụ HTTP trên cổng 8080.
2. Chỉ một Pod thỏa readiness probe.
3. Service giữ `publishNotReadyAddresses: false`.
4. Ứng dụng quan sát lần lượt chạy với `include-not-ready-addresses` là `false` và `true`.

Bạn cần một cluster thử nghiệm có EndpointSlice API, công cụ `kubectl`, quyền tạo các tài nguyên của lab và khả năng kéo image BusyBox. Các lệnh dưới đây là hướng dẫn thực hành; IP và thời gian hội tụ phụ thuộc cluster của bạn.

Tạo namespace và RBAC ở phần trước. Có thể lưu các khối YAML vào các tệp của môi trường lab rồi dùng `kubectl apply -f <tệp>`. Không áp dụng ví dụ peer Service ở phần 4 để thay thế Service của lab, vì như vậy phép so sánh sẽ có thêm một biến khác.

### 7.2. Service và hai Pod thử nghiệm

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: readiness-demo
  namespace: discovery-lab
spec:
  publishNotReadyAddresses: false
  selector:
    app: readiness-demo
  ports:
    - name: http
      port: 8080
      targetPort: http
---
apiVersion: v1
kind: Pod
metadata:
  name: readiness-demo-ready
  namespace: discovery-lab
  labels:
    app: readiness-demo
spec:
  containers:
    - name: http
      image: busybox:1.36
      command: ["sh", "-c"]
      args:
        - |
          mkdir -p /www
          echo "ready-demo" > /www/index.html
          touch /tmp/ready
          exec httpd -f -p 8080 -h /www
      ports:
        - name: http
          containerPort: 8080
      readinessProbe:
        exec:
          command: ["test", "-f", "/tmp/ready"]
        periodSeconds: 2
        failureThreshold: 1
        successThreshold: 1
---
apiVersion: v1
kind: Pod
metadata:
  name: readiness-demo-warming
  namespace: discovery-lab
  labels:
    app: readiness-demo
spec:
  containers:
    - name: http
      image: busybox:1.36
      command: ["sh", "-c"]
      args:
        - |
          mkdir -p /www
          echo "warming-demo" > /www/index.html
          exec httpd -f -p 8080 -h /www
      ports:
        - name: http
          containerPort: 8080
      readinessProbe:
        exec:
          command: ["test", "-f", "/tmp/ready"]
        periodSeconds: 2
        failureThreshold: 1
        successThreshold: 1
~~~

Pod `readiness-demo-warming` cố ý không tạo `/tmp/ready`. Đây là mô phỏng điều kiện nghiệp vụ chưa hoàn tất; server HTTP vẫn hoạt động. Lab không sửa health indicator hay trạng thái readiness của một ứng dụng Spring thật.

### 7.3. Kiểm tra dữ liệu gốc trước khi nhìn DiscoveryClient

~~~bash
kubectl get pods --namespace discovery-lab --output wide

kubectl get endpointslices   --namespace discovery-lab   --selector kubernetes.io/service-name=readiness-demo   --output yaml
~~~

Chờ container khởi động và controller cập nhật dữ liệu. Trong môi trường lab ổn định, kỳ vọng:

| Pod | Cột READY | EndpointSlice |
| --- | --- | --- |
| `readiness-demo-ready` | `1/1` | Địa chỉ tương ứng có `ready: true` |
| `readiness-demo-warming` | `0/1` | Địa chỉ tương ứng có `ready: false` |

Cột READY trên kết quả `kubectl get pods` đếm container sẵn sàng; khi hệ thống có readiness gate hoặc nhiều container, cần xem thêm condition của Pod. Lab chỉ có một container mỗi Pod và không có readiness gate bổ sung.

Endpoint có thể nằm trong nhiều EndpointSlice. Khi đối chiếu, đọc toàn bộ các slice mang nhãn của Service, kiểm tra `addresses` và `targetRef`; không chỉ xem phần tử đầu tiên.

Nếu Pod warming chưa có IP vì lỗi kéo image hoặc lập lịch, hãy xử lý lỗi đó trước. Phép thử chỉ có ý nghĩa khi endpoint NotReady đã thực sự tồn tại trong dữ liệu Kubernetes.

### 7.4. Chạy ứng dụng quan sát với cấu hình thứ nhất

Đóng gói ứng dụng Spring mẫu thành image theo quy trình của bạn và chạy trong namespace `discovery-lab`. Bật profile `inspection`, gắn ServiceAccount `endpoint-inspector` và sử dụng cấu hình ở phần 3, nhưng đặt `include-not-ready-addresses: false` cho lượt đầu.

Đoạn trích sau minh họa vị trí gắn ServiceAccount và profile trong Pod template của Deployment ứng dụng quan sát; thay tên container và image bằng giá trị của bạn:

~~~yaml
spec:
  template:
    spec:
      serviceAccountName: endpoint-inspector
      containers:
        - name: endpoint-inspector
          image: your-registry/endpoint-inspector:lab
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: inspection
~~~

Đây là đoạn cấu hình cần ghép vào Deployment hợp lệ, không phải manifest hoàn chỉnh. Giả sử Deployment của ứng dụng có tên `endpoint-inspector`, có thể mở đường tới HTTP endpoint để quan sát từ máy phát triển:

~~~bash
kubectl port-forward   --namespace discovery-lab   deployment/endpoint-inspector 18080:8080
~~~

Trong terminal khác:

~~~bash
curl http://localhost:18080/internal/discovery/readiness-demo
~~~

Với dữ liệu Kubernetes đã ổn định, kỳ vọng nhận một instance có host trùng IP của Pod Ready. Ứng dụng quan sát nằm trong cluster nên có thể đọc API theo ServiceAccount; port-forward chỉ đưa endpoint liệt kê kết quả ra máy phát triển.

### 7.5. Bật khám phá endpoint chưa Ready

Đổi đúng thuộc tính sau trong cấu hình hiệu lực của ứng dụng quan sát rồi khởi động lại hoặc triển khai lại ứng dụng đó:

~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        include-not-ready-addresses: true
~~~

Giữ nguyên các thiết lập namespace, EndpointSlice, ServiceAccount và Service. Sau khi ứng dụng hoàn tất khởi động, thực hiện lại yêu cầu HTTP liệt kê instance. Nếu port-forward bị ngắt khi Pod quan sát thay đổi, mở lại lệnh port-forward.

Kỳ vọng lúc này có hai địa chỉ, khớp hai Pod. Không chỉ kiểm tra `size() == 2`; đối chiếu từng host với IP trong EndpointSlice để tránh nhầm với endpoint của một workload khác.

### 7.6. Chuyển Pod warming sang Ready mà không đổi Service

~~~bash
kubectl exec   --namespace discovery-lab   readiness-demo-warming -- touch /tmp/ready
~~~

Chờ readiness probe và dữ liệu endpoint cập nhật. Sau đó cả hai Pod phải thỏa readiness của lab.

Để thử chiều ngược lại:

~~~bash
kubectl exec   --namespace discovery-lab   readiness-demo-warming -- rm -f /tmp/ready
~~~

Lệnh thứ hai chỉ xóa tệp cờ được tạo trong container lab. Cả hai thao tác không thay selector hay chính sách công bố của Service.

Ma trận kỳ vọng sau khi các thành phần đã hội tụ:

| Trạng thái Pod warming | Thuộc tính discovery | Số instance dự kiến |
| --- | --- | --- |
| NotReady, có endpoint | `false` | 1 |
| NotReady, có endpoint | `true` | 2 |
| Ready | `false` | 2 |
| Ready | `true` | 2 |

Ma trận giả định có đúng hai Pod của lab, chỉ một namespace được quan sát và `publishNotReadyAddresses: false`. Thay đổi một trong các điều kiện này cần được ghi lại trước khi giải thích kết quả.

### 7.7. Điều mà lab chứng minh

Trong ví dụ, Pod warming vẫn có thể trả trang `warming-demo` khi gọi trực tiếp Pod IP từ môi trường được phép kết nối. Readiness probe kiểm tra tệp cờ; nó không đóng listener HTTP.

Vì vậy, discovery mở rộng danh sách ứng viên có thể giúp quan sát Pod NotReady, đồng thời cũng tạo khả năng một client gọi vào Pod đó. Việc bảo vệ yêu cầu nghiệp vụ phải nằm trong thiết kế định tuyến và hợp đồng xử lý của ứng dụng. Không dùng việc truy cập HTTP thành công để khẳng định cấu hình readiness sai: readiness có thể còn biểu diễn một điều kiện nghiệp vụ khác.

## 8. Ảnh hưởng khi danh sách đi vào Spring Cloud LoadBalancer

Hãy xác định đường đi của yêu cầu trong ứng dụng thực tế:

~~~text
Tên dịch vụ
  -> nguồn danh sách ServiceInstance
  -> bộ lọc hoặc bộ chọn instance
  -> địa chỉ được chọn
  -> kết nối tới ứng dụng đích
~~~

Nếu thành phần cân bằng tải sử dụng danh sách đã bao gồm endpoint chưa Ready và không có bộ lọc thích hợp, endpoint đó có thể trở thành ứng viên cho yêu cầu nghiệp vụ. Đây là hệ quả của thiết kế tiêu thụ danh sách; không phải mọi chế độ Spring Cloud Kubernetes LoadBalancer đều lấy instance theo cùng một cách.

Ví dụ, cơ chế chọn Pod trực tiếp và cơ chế chọn Kubernetes Service có đường định tuyến khác nhau. Cần kiểm tra chế độ đang sử dụng và nơi áp dụng readiness, thay vì suy từ tên thư viện rằng mọi yêu cầu đều được Kubernetes lọc lại. [Tài liệu Spring Cloud Kubernetes LoadBalancer](https://docs.spring.io/spring-cloud-kubernetes/reference/load-balancer.html).

Trong một hệ thống bán hàng, có thể áp dụng thiết kế sau:

- `endpoint-inspector` bật khám phá NotReady để hỗ trợ điều tra.
- `checkout-api` giữ discovery mặc định hoặc gọi DNS của Service nghiệp vụ.
- Giao thức peer dùng Service riêng và quy trình bootstrap riêng nếu có nhu cầu thực sự.
- Dữ liệu quan sát không tự trở thành nguồn ứng viên cho client nghiệp vụ.

Nếu buộc phải dùng hai chính sách trong cùng một tiến trình, cần thiết kế rõ nguồn dữ liệu và bộ chọn của từng đường gọi. Không chỉ bật một thuộc tính toàn cục rồi kỳ vọng các client sẽ tự hiểu mục đích khác nhau.

Timeout ngắn, retry có giới hạn và circuit breaker vẫn cần thiết cho lời gọi mạng. Chúng giúp xử lý lỗi khi endpoint thay đổi hoặc không phản hồi, nhưng không thay thế quyết định chọn đúng nhóm endpoint. Tránh retry dồn vào cùng một Pod đang warm-up.

## 9. Chẩn đoán theo từng lớp

| Hiện tượng | Kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| Bật thuộc tính nhưng vẫn chỉ thấy Pod Ready | Thuộc tính hiệu lực, profile, lần khởi động lại, backend discovery | Xác nhận đúng thành phần đang đọc cấu hình; với discovery qua server trung gian, kiểm tra nơi thực sự tạo danh sách |
| Không có instance nào | Namespace, Service name, selector, cổng và các EndpointSlice | Xác định dữ liệu đầu vào trước khi thay chính sách readiness |
| Kubernetes API trả 403 | ServiceAccount, RoleBinding, API group và verb cụ thể | Cấp quyền đọc đúng tài nguyên cần dùng |
| Nhìn thấy IP nhưng kết nối bị từ chối | Listener, target port, quá trình khởi tạo | Chờ hoặc xử lý server chưa mở cổng; thuộc tính discovery không mở cổng thay ứng dụng |
| Kết nối hết thời gian chờ | Đường mạng, NetworkPolicy, mesh, thời gian phản hồi | Đối chiếu từ vị trí chạy client; phân biệt lỗi mạng với health không đạt |
| Pod NotReady xuất hiện dù thuộc tính là false | `publishNotReadyAddresses` và condition thực tế của endpoint | Kiểm tra chính sách công bố của Service, rồi đối chiếu Pod |
| Gọi Actuator trả 404 hoặc 401 | Dependency, đường dẫn, cổng quản trị, exposure và xác thực | Dùng đúng hợp đồng quản trị của ứng dụng |
| Kết quả chưa đổi ngay sau khi sửa tệp cờ | Probe, controller, informer hoặc cache ở client | Quan sát quá trình hội tụ; so sánh các mốc thời gian thay vì giả định cập nhật đồng bộ |

Một quy trình điều tra có thể bắt đầu bằng:

~~~bash
kubectl describe pod readiness-demo-warming   --namespace discovery-lab

kubectl get service readiness-demo   --namespace discovery-lab   --output yaml

kubectl get endpointslices   --namespace discovery-lab   --selector kubernetes.io/service-name=readiness-demo   --output yaml
~~~

Sau đó đối chiếu kết quả `/internal/discovery/readiness-demo` của ứng dụng quan sát. Ghi lại namespace, thời điểm đọc, địa chỉ và tài nguyên liên quan. Giữ dữ liệu quan sát đủ để phân biệt “endpoint chưa tồn tại”, “endpoint đã tồn tại nhưng bị lọc” và “endpoint đã trả về nhưng không thể kết nối”.

Không suy luận mọi chậm trễ đều do Configuration Watcher. Theo dõi endpoint phục vụ discovery và cập nhật cấu hình từ ConfigMap/Secret là các luồng chức năng khác nhau; chỉ bật thêm thành phần khi đã xác định nhu cầu của luồng đó.

## 10. Tiêu chí lựa chọn trước khi triển khai

Trước khi áp dụng ngoại lệ discovery, hãy viết được một mô tả cụ thể, chẳng hạn:

> Ứng dụng quan sát nội bộ trong namespace dịch vụ cần thấy endpoint chưa Ready để kiểm tra tiến độ khởi tạo; danh sách này không cấp cho đường gọi đặt hàng.

Từ mô tả đó, xác định các điểm cần kiểm chứng:

1. Thành phần tiêu thụ là công cụ quan sát hoặc giao thức peer có hỗ trợ giai đoạn khởi tạo.
2. Nguồn endpoint và phiên bản Spring Cloud Kubernetes hỗ trợ cấu hình được sử dụng.
3. Namespace, Service và quyền đọc API có phạm vi phù hợp.
4. Cổng, scheme và xác thực của thao tác được phép gọi đã rõ.
5. Service nghiệp vụ và đường cân bằng tải vẫn tuân theo chính sách sẵn sàng mong muốn.
6. Hệ thống chịu được endpoint biến mất, timeout, rollout và khoảng trễ cập nhật.
7. Có cách quay lại cấu hình mặc định và kiểm tra lại danh sách sau khi thay đổi.

Các mục trên là tiêu chí vận hành cho tính năng, không đòi hỏi triển khai toàn bộ Spring Cloud Kubernetes. Chỉ cần bật phần discovery cần thiết, rồi bổ sung các tích hợp khác khi bài toán cấu hình hoặc quan sát yêu cầu.

## 11. Điều cần ghi nhớ

`spring.cloud.kubernetes.discovery.include-not-ready-addresses=true` mở rộng khả năng nhìn thấy endpoint cho những mục đích có chủ đích. Nó không làm Pod trở thành Ready và không bảo đảm cổng hoặc nghiệp vụ đã hoạt động.

Lựa chọn phù hợp thường bắt đầu bằng việc giữ hành vi mặc định cho nghiệp vụ, giới hạn ngoại lệ cho ứng dụng quan sát hoặc giao thức peer, rồi kiểm chứng đồng thời dữ liệu Kubernetes và danh sách DiscoveryClient. Khi dùng `publishNotReadyAddresses`, cần đánh giá tác động ở tầng Service và cách endpoint được công bố trước khi dựa vào bất kỳ bộ lọc readiness nào ở phía client.