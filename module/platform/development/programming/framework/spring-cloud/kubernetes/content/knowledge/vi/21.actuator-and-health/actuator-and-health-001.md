# Thông tin Kubernetes được bổ sung vào endpoint info

Trong chương **Actuator và sức khỏe** của module **Spring Cloud Kubernetes**, bài này giải thích cách ứng dụng công bố danh tính Pod qua endpoint `info`. Những thông tin ấy giúp người vận hành biết request đang đến bản sao nào, chạy trong namespace nào và sử dụng ServiceAccount nào khi triển khai hoặc điều tra sự cố.

Spring Cloud Kubernetes hỗ trợ nhiều nhu cầu: DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer và Configuration Watcher. Bổ sung metadata cho Actuator là một khả năng riêng; nhu cầu xem danh tính Pod không đồng nghĩa phải bật toàn bộ các khả năng đó.

## Mục tiêu và phạm vi thực hành

Sau bài học, bạn có thể:

- Giải thích vai trò của Kubernetes `InfoContributor` trong phản hồi `/actuator/info`.
- Đọc các trường định danh Pod và nhận biết giới hạn của chúng.
- Cấu hình exposure, quyền truy cập endpoint và RBAC để thử nghiệm trong cluster.
- Phân biệt thông tin triển khai với tín hiệu readiness/liveness.
- Chọn contributor có sẵn hoặc Downward API theo dữ liệu thực sự cần.

Ví dụ dùng ứng dụng Spring Boot dạng web, cổng 8080 và đường dẫn Actuator mặc định. Phần mô tả implementation được neo vào **Spring Cloud Kubernetes 3.3.0, Fabric8**, phù hợp để học trên dòng Spring Boot 3.5 với bộ dependency tương thích. Đây là mốc giải thích hành vi, không phải khuyến nghị nâng cấp. Nếu dùng release khác hoặc Kubernetes Java Client, đối chiếu tài liệu và mã nguồn của đúng release trước khi phụ thuộc vào cấu trúc JSON.

Bạn cần một ứng dụng Spring Boot đã chạy được, một image của ứng dụng và một namespace thử nghiệm. Các lệnh triển khai trong bài là hướng dẫn cho môi trường đó, không phải kết quả đã thực thi sẵn.

## 1. Endpoint info trả lời câu hỏi nào?

Giả sử `orders-api` có ba replica. Trong lúc rolling update, một số Pod dùng bản ứng dụng cũ, các Pod còn lại dùng bản mới. Đội vận hành nhận được một phản hồi bất thường nhưng tên Service vẫn là `orders-api`.

Metadata của instance giúp nối phản hồi với Pod cụ thể để tìm log và mô tả tài nguyên tương ứng. Thông tin build hoặc Git, nếu đã được cấu hình riêng, còn giúp đối chiếu bản mã đang chạy.

| Câu hỏi vận hành | Nguồn thông tin thích hợp |
| --- | --- |
| Instance nào trả lời request chẩn đoán? | Metadata Pod trong `info` |
| Instance đó chạy bản ứng dụng nào? | Build/Git contributor nếu ứng dụng có dữ liệu tương ứng |
| Instance có sẵn sàng nhận traffic không? | Readiness |
| Tiến trình có cần được khởi động lại không? | Liveness theo thiết kế của ứng dụng |
| Tại sao container bị restart trước đó? | Pod status, events và log container |

HTTP 200 từ `info` chỉ cho biết request tới endpoint đã được xử lý thành công. Nó không kiểm tra một giao dịch tạo đơn hàng, không xác nhận database hoạt động và không đảm bảo mọi replica đều giống nhau.

Nếu gọi endpoint qua Service hoặc Ingress, request chẩn đoán có thể đến một Pod khác với request nghiệp vụ đang điều tra. Khi cần đối chiếu chính xác, truy cập một Pod được chọn hoặc dùng correlation ID cùng metadata instance trong hệ thống log.

## 2. Kubernetes InfoContributor tham gia như thế nào?

`InfoContributor` là điểm mở rộng của Actuator. Mỗi contributor bổ sung một phần dữ liệu qua `Info.Builder`; ứng dụng có thể có nhiều contributor cùng tham gia một phản hồi. Kubernetes contributor bổ sung nhánh `kubernetes`, không thay thế endpoint bằng một controller nghiệp vụ. Xem hợp đồng tại [Spring Boot InfoContributor API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/info/InfoContributor.html).

~~~mermaid
flowchart LR
    Operator["Người vận hành"] --> Endpoint["GET /actuator/info"]
    Endpoint --> Other["Contributor khác nếu được cấu hình"]
    Endpoint --> Kube["Kubernetes InfoContributor"]
    Kube --> Utils["PodUtils"]
    Utils --> Client["Kubernetes client"]
    Client --> Pod["Đọc Pod hiện tại qua API server"]
~~~

Sơ đồ thể hiện nguồn dữ liệu logic. Không nên suy ra rằng mỗi request HTTP đều thực hiện một lần gọi API server. Implementation có thể giữ lại đối tượng Pod đã lấy được.

Ở Fabric8 3.3.0, auto-configuration yêu cầu Actuator có mặt và môi trường được nhận diện là Kubernetes. Bean info còn chịu điều kiện `management.info.kubernetes.enabled`. Việc thêm dependency vào một tiến trình chạy ngoài cluster không đủ để bảo đảm xuất hiện nhánh `kubernetes`. Các điều kiện này có thể kiểm tra trong [Fabric8ActuatorConfiguration](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.0/spring-cloud-kubernetes-fabric8-autoconfig/src/main/java/org/springframework/cloud/kubernetes/fabric8/Fabric8ActuatorConfiguration.java) và [annotation điều kiện Kubernetes](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/autoconfig/ConditionalOnKubernetesHealthIndicatorEnabled.java).

Đừng ép cấu hình môi trường thành Kubernetes chỉ để có JSON giống ví dụ. Nhận diện môi trường, thông tin xác thực và khả năng đọc Pod là các điều kiện khác nhau.

## 3. Đọc phần kubernetes trong JSON

Ví dụ phản hồi minh họa của contributor Fabric8 khi lấy được Pod:

~~~json
{
  "kubernetes": {
    "inside": true,
    "namespace": "learning",
    "podName": "orders-api-6f78bc9d45-k7q2m",
    "podIp": "10.244.2.17",
    "hostIp": "192.168.10.23",
    "serviceAccount": "orders-observer",
    "nodeName": "worker-02"
  }
}
~~~

Các tên trường trên dựa vào [Fabric8InfoContributor 3.3.0](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.0/spring-cloud-kubernetes-fabric8-autoconfig/src/main/java/org/springframework/cloud/kubernetes/fabric8/Fabric8InfoContributor.java). Đây là ví dụ theo implementation đó; không coi mọi phiên bản hoặc mọi client đều có một schema bất biến.

| Trường | Giá trị của Pod được sử dụng | Khi đọc cần nhớ |
| --- | --- | --- |
| `inside` | Contributor có lấy được Pod hiện tại hay không | Không phải kết quả kiểm tra sức khỏe |
| `namespace` | `metadata.namespace` | Dùng cùng tên Pod để xác định đúng đối tượng |
| `podName` | `metadata.name` | Có thể thay đổi khi Deployment tạo Pod mới |
| `podIp` | `status.podIP` | Không phải địa chỉ Service ổn định |
| `hostIp` | `status.hostIP` | Địa chỉ host được ghi trong trạng thái Pod |
| `serviceAccount` | `spec.serviceAccountName` | Là tên tài khoản của workload, không phải token |
| `nodeName` | `spec.nodeName` | Giúp đối chiếu Pod với vị trí chạy |

Tên ServiceAccount không cho biết toàn bộ quyền hiệu lực. Cũng không thể suy ra một địa chỉ có thể truy cập từ máy cá nhân chỉ vì địa chỉ ấy xuất hiện trong JSON.

Nếu không lấy được đối tượng Pod, implementation này có thể trả:

~~~json
{
  "kubernetes": {
    "inside": false
  }
}
~~~

Vì vậy, `inside: false` không đủ để kết luận tiến trình chắc chắn đang chạy ngoài Kubernetes. Nguyên nhân còn có thể là thiếu token, sai namespace, sai tên Pod hoặc không đọc được API server. Hành vi đọc Pod và xử lý lỗi có thể xem tại [Fabric8PodUtils](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.0/spring-cloud-kubernetes-fabric8-autoconfig/src/main/java/org/springframework/cloud/kubernetes/fabric8/Fabric8PodUtils.java).

Ngược lại, một phản hồi không có nhánh `kubernetes` cũng không tương đương với `inside: false`. Contributor có thể chưa được đăng ký, bị tắt hoặc gặp lỗi trước khi bổ sung dữ liệu.

## 4. Chuẩn bị dependency và cấu hình

### 4.1. Dùng dependency tương thích với ứng dụng

Trong ứng dụng Spring Boot đã có web starter, bạn có thể dùng các dependency sau. Phiên bản phải do bộ Spring Boot/Spring Cloud BOM tương thích của dự án quản lý; không trộn tùy ý các phiên bản riêng lẻ.

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-fabric8</artifactId>
</dependency>
~~~

Ví dụ dùng một client duy nhất là Fabric8. Starter trên kéo theo module discovery theo [POM của starter 3.3.0](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.0/spring-cloud-starter-kubernetes-fabric8/pom.xml), nên cần chủ động tắt discovery trong bài thực hành này. Không cần thêm starter `all`, config hoặc loadbalancer chỉ để xem metadata.

### 4.2. Bật contributor và expose đúng endpoint

Nội dung cấu hình minh họa cho ứng dụng:

~~~yaml
spring:
  application:
    name: orders-api
  cloud:
    kubernetes:
      discovery:
        enabled: false

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  info:
    kubernetes:
      enabled: true
~~~

Spring Boot mặc định chỉ expose `health` qua HTTP. Thuộc tính exposure mở đường truy cập; nó không cấp quyền HTTP cho người gọi. Nếu dùng Spring Security hoặc gateway, áp dụng quy tắc truy cập riêng cho `info`. Xem [Spring Boot: exposure và bảo vệ Actuator](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.exposing).

Nếu đổi base path, context path hoặc cổng management, URL thực tế sẽ khác `http://localhost:8080/actuator/info`. Các thuộc tính liên quan được mô tả tại [Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.5/reference/actuator/monitoring.html).

### 4.3. Tách ba loại công tắc

| Cấu hình | Phạm vi ảnh hưởng |
| --- | --- |
| `management.endpoints.web.exposure.include` | Endpoint nào được expose qua HTTP |
| `management.info.kubernetes.enabled` | Kubernetes contributor có tham gia `info` |
| `management.health.kubernetes.enabled` | Kubernetes health contributor |

Ví dụ, muốn giữ các contributor khác trong `info` nhưng bỏ metadata Kubernetes:

~~~yaml
management:
  info:
    kubernetes:
      enabled: false
~~~

Đây là công tắc được nêu trong [tài liệu Info Contributor của Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/info-contributor.html). Tắt contributor này không tự thu hồi RBAC của ServiceAccount, cũng không tự tắt DiscoveryClient hoặc các thành phần khác.

Công tắc health thuộc một contributor khác, được mô tả riêng tại [Pod Health Indicator](https://docs.spring.io/spring-cloud-kubernetes/reference/pod-health-indicator.html). Không dùng nó để điều khiển dữ liệu của `info`.

## 5. Thực hành đọc metadata trong cluster

### 5.1. Giới hạn quyền theo thao tác cần dùng

Hai luồng quyền cần được hiểu riêng:

~~~text
Người vận hành -> /actuator/info
    Chịu xác thực/phân quyền HTTP và chính sách mạng

Ứng dụng -> Kubernetes API -> Pod
    Chịu danh tính ServiceAccount và Kubernetes RBAC
~~~

Cấp quyền gọi endpoint cho người vận hành không làm ứng dụng có quyền đọc Pod. Cấp RBAC cho ứng dụng cũng không bảo vệ endpoint khỏi người gọi HTTP.

Với phạm vi Fabric8 trong bài, thao tác lấy Pod hiện tại là đọc theo tên. Ví dụ dưới đây chỉ cấp `get` đối với `pods` trong namespace thử nghiệm. Role vẫn cho phép đọc bất kỳ Pod nào trong namespace đó; đây không phải cơ chế tự giới hạn vào “chính Pod của mình”. Xem ý nghĩa phạm vi Role và RoleBinding tại [Kubernetes RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: learning
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-observer
  namespace: learning
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: orders-pod-info-reader
  namespace: learning
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: orders-pod-info-reader
  namespace: learning
subjects:
  - kind: ServiceAccount
    name: orders-observer
    namespace: learning
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: orders-pod-info-reader
~~~

Manifest này chỉ phục vụ phần đọc metadata. Nếu ứng dụng bật discovery, đọc ConfigMap/Secret bằng API hoặc watch tài nguyên, cần phân tích thêm quyền của từng chức năng. Không bổ sung các quyền đó chỉ để làm biến mất thông báo lỗi của một dependency chưa thật sự cần.

### 5.2. Gắn ServiceAccount cho workload

Ví dụ Deployment, giả sử image đã chứa cấu hình ở phần trước:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: learning
spec:
  replicas: 1
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-observer
      automountServiceAccountToken: true
      containers:
        - name: orders-api
          image: registry.example.com/learning/orders-api:1.0.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_CLOUD_KUBERNETES_CLIENT_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
~~~

Thay địa chỉ image minh họa bằng image thực tế trước khi triển khai. Biến môi trường ở đây đặt namespace cho client một cách tường minh. Việc gắn ServiceAccount cung cấp danh tính; RoleBinding ở bước trước mới cấp quyền tương ứng.

Không tùy biến `hostname` trong bài thử nghiệm này. Fabric8PodUtils ở mốc mã nguồn đã chọn dùng biến `HOSTNAME` khi tìm Pod theo tên. Nếu hostname không còn khớp tên Pod, phải xem lại cơ chế tìm Pod trước khi kết luận RBAC sai.

Manifest bật automount token để phục vụ client gọi API. Với workload cố ý không có token, hãy cân nhắc cách lấy metadata qua Downward API ở phần sau thay vì mặc định tăng quyền.

### 5.3. Kiểm tra quyền và chọn đúng Pod

Sau khi bạn áp dụng các manifest bằng quy trình triển khai của mình, dùng PowerShell để chọn Pod:

~~~powershell
kubectl -n learning rollout status deployment/orders-api

$podName = kubectl -n learning get pods -l app=orders-api -o jsonpath='{.items[0].metadata.name}'
kubectl -n learning get pod $podName -o wide

kubectl auth can-i get "pods/$podName" --namespace learning --as system:serviceaccount:learning:orders-observer
~~~

Kỳ vọng kiểm tra quyền trả `yes`. Người thực hiện lệnh có `--as` phải được phép impersonate danh tính đó. Nếu lỗi đến từ impersonation, nhờ người quản trị thực hiện phép kiểm tra; không diễn giải nó thành bằng chứng ứng dụng thiếu quyền đọc Pod.

Mở port-forward đến Pod được chọn:

~~~powershell
kubectl -n learning port-forward "pod/$podName" 18080:8080
~~~

Giữ terminal này chạy. Trong terminal khác, gọi:

~~~powershell
curl.exe -i http://localhost:18080/actuator/info
~~~

Nếu endpoint có xác thực, sử dụng thông tin xác thực theo cơ chế của môi trường thử nghiệm. Port-forward không bỏ qua bộ lọc bảo mật HTTP của ứng dụng.

Port-forward này cố định đích vào một Pod. Khi Pod bị thay thế, chọn lại Pod và mở lại kết nối; không giả định tunnel cũ đi theo Deployment.

### 5.4. Đối chiếu kết quả với tài nguyên thật

Dùng cùng tên Pod và namespace:

~~~powershell
kubectl -n learning get pod $podName -o jsonpath='{.metadata.name}{"\n"}{.metadata.namespace}{"\n"}{.spec.serviceAccountName}{"\n"}{.spec.nodeName}{"\n"}{.status.podIP}{"\n"}{.status.hostIP}{"\n"}'
~~~

Kiểm tra các quan hệ sau:

- `podName` và `namespace` khớp Pod đã port-forward.
- `serviceAccount` là `orders-observer`.
- `nodeName`, `podIp`, `hostIp` tương ứng với dữ liệu Pod tại thời điểm kiểm tra.
- Các contributor khác, nếu có, vẫn giữ phần dữ liệu riêng của chúng.

Nếu thay image nhưng giữ cùng cấu hình runtime, thông tin Pod không tự chứng minh phiên bản artifact. Muốn xác nhận bản triển khai, kết hợp nguồn build/Git đã chuẩn bị riêng và image của container.

### 5.5. Thử tắt Kubernetes contributor

Đổi cấu hình ứng dụng thành `management.info.kubernetes.enabled=false`, tạo lại artifact hoặc cập nhật cấu hình theo cơ chế triển khai đang dùng, rồi thực hiện rollout. Sau đó chọn lại Pod và port-forward lại.

Kỳ vọng nhánh `kubernetes` biến mất. `info` vẫn có thể trả dữ liệu contributor khác, hoặc đối tượng rỗng nếu không contributor nào đóng góp dữ liệu.

Bài thử này không giả định sửa ConfigMap sẽ lập tức thay đổi bean contributor của tiến trình hiện tại. Việc cập nhật cấu hình và Configuration Watcher có vòng đời riêng; kiểm tra khả năng áp dụng từng thuộc tính trước khi dựa vào refresh.

## 6. Chẩn đoán theo dấu hiệu quan sát được

| Dấu hiệu | Hướng kiểm tra trước |
| --- | --- |
| 404 ở `/actuator/info` | Exposure, đường dẫn/cổng management, endpoint access và định tuyến proxy |
| 401 hoặc 403 khi gọi endpoint | Spring Security hoặc gateway; xác định thành phần trả mã lỗi |
| 200 nhưng không có `kubernetes` | Dependency, điều kiện auto-configuration, cờ contributor và log |
| Có `inside: false` trong Pod | Namespace, tên Pod, token/CA, RBAC và đường mạng đến API server |
| Log báo API server trả 403 | Quyền của đúng ServiceAccount đối với thao tác và namespace bị từ chối |
| Metadata không đổi sau khi sửa đối tượng Pod | Khả năng dữ liệu đã được giữ lại trong tiến trình |
| Qua Service thấy các `podName` khác nhau | Có thể đang đi đến các replica khác nhau; kiểm tra trên từng Pod |

Một lỗi 403 có ít nhất hai bối cảnh: người dùng không được gọi Actuator, hoặc ứng dụng không được đọc Kubernetes API. Dựa vào URL đích và log để xác định bối cảnh trước khi sửa cấu hình.

Không suy luận “API server khỏe” chỉ từ nhánh `kubernetes` đầy đủ. Tại Fabric8 3.3.0, PodUtils dùng cơ chế lazy giữ kết quả khác null; request `info` sau đó có thể dùng đối tượng đã đọc trước đây. Xem [LazilyInstantiate](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/LazilyInstantiate.java). Do đó, endpoint này không phải phép đo độ mới của Pod status hoặc kiểm tra kết nối API server theo thời gian thực.

Ngoài ra, lớp contributor chung bắt exception khi lấy dữ liệu và ghi cảnh báo. Vì thế, lỗi lấy metadata có thể làm thiếu nhánh dữ liệu mà endpoint vẫn phục vụ các contributor khác. Đây là hành vi trong [AbstractKubernetesInfoContributor](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/AbstractKubernetesInfoContributor.java).

Khi cần kiểm tra health, dùng endpoint và health group được thiết kế cho mục đích đó. `/actuator/info` không nên làm đích readiness hoặc liveness chỉ vì nó trả HTTP thành công.

## 7. Chọn dữ liệu cần công bố và cách lấy

### 7.1. Phạm vi sử dụng metadata

Metadata triển khai giúp điều tra sự cố nhưng cũng mô tả cấu trúc nội bộ. Một chính sách thực tế là chỉ cho đội vận hành truy cập `info` qua đường quản trị đã kiểm soát, đồng thời giới hạn những trường thật sự hữu ích.

Không đưa token, mật khẩu, giá trị Secret, dữ liệu kết nối chứa thông tin xác thực hoặc nội dung cấu hình nhạy cảm vào contributor tùy chỉnh. Không giả định dữ liệu do chính ứng dụng đóng góp vào `info` sẽ được tự động che giống các endpoint cấu hình khác.

Nếu downstream cần một hợp đồng dữ liệu lâu dài, định nghĩa schema do ứng dụng sở hữu thay vì phụ thuộc vào toàn bộ JSON của implementation thư viện.

### 7.2. Khi chỉ cần danh tính Pod: Downward API

Nếu chỉ cần tên Pod và namespace, có thể để kubelet đưa hai giá trị vào biến môi trường. Ứng dụng không phải tự gọi API server để lấy hai trường đó. Cách ánh xạ bằng `fieldRef` được mô tả tại [Kubernetes Downward API qua biến môi trường](https://kubernetes.io/docs/tasks/inject-data-application/environment-variable-expose-pod-information/).

Phần `env` trong container:

~~~yaml
env:
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
  - name: POD_NAMESPACE
    valueFrom:
      fieldRef:
        fieldPath: metadata.namespace
~~~

Trong ứng dụng, tạo contributor với nhánh riêng. Đặt lớp trong package được Spring Boot quét:

~~~java
package com.example.orders;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class WorkloadInfoContributor implements InfoContributor {

    private final Environment environment;

    public WorkloadInfoContributor(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void contribute(Info.Builder builder) {
        Map<String, Object> details = new LinkedHashMap<>();
        addIfPresent(details, "podName", "POD_NAME");
        addIfPresent(details, "namespace", "POD_NAMESPACE");

        if (!details.isEmpty()) {
            builder.withDetail("workload", details);
        }
    }

    private void addIfPresent(
            Map<String, Object> details, String key, String property) {
        String value = environment.getProperty(property);
        if (value != null && !value.isBlank()) {
            details.put(key, value);
        }
    }
}
~~~

Ví dụ đầu ra:

~~~json
{
  "workload": {
    "podName": "orders-api-6f78bc9d45-k7q2m",
    "namespace": "learning"
  }
}
~~~

Nhánh `workload` phân biệt rõ dữ liệu ứng dụng tự đóng góp. Khi chạy local mà thiếu biến môi trường, lớp bỏ qua trường đó. Việc triển khai `InfoContributor` trực tiếp không tự nhận công tắc `management.info.workload.enabled`; muốn có công tắc riêng, ứng dụng phải định nghĩa điều kiện đăng ký bean.

Nếu chọn cách này thay hoàn toàn contributor Kubernetes, có thể tắt contributor có sẵn và không cần Spring Cloud Kubernetes chỉ để công bố hai giá trị trên. Việc bỏ token hoặc RBAC chỉ phù hợp khi không còn thành phần nào khác của workload cần gọi API server. Chỉ tắt `info` chưa đủ để kết luận có thể thu hồi mọi quyền.

Biến môi trường từ Downward API được cung cấp khi container khởi động; không xem đây là kênh watch tài nguyên. Ví dụ cũng không mô phỏng cờ `inside`, health hoặc danh sách replica.

### 7.3. Quyết định theo nhu cầu triển khai

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Đã dùng client và cần metadata Pod theo contributor có sẵn | Bật Kubernetes contributor, cấp quyền đọc cần thiết |
| Chỉ cần tên Pod và namespace, muốn giảm phụ thuộc API | Downward API và contributor nhỏ do ứng dụng sở hữu |
| Cần biết bản mã của từng replica trong rollout | Bổ sung nguồn build/Git và đối chiếu metadata Pod |
| Cần quyết định có nhận traffic hay restart không | Thiết kế readiness/liveness; không dùng `info` |
| Cần theo dõi thay đổi ConfigMap/Secret | Chọn cơ chế cấu hình/Watcher riêng và phân tích RBAC tương ứng |

## 8. Bài tập củng cố

1. Truy cập trực tiếp một Pod bằng port-forward, ghi lại namespace, tên Pod và ServiceAccount; đối chiếu với `kubectl get pod`.
2. Tạo một rollout trong môi trường thử nghiệm rồi chọn Pod mới. Giải thích vì sao tên Service có thể giữ nguyên trong khi `podName` thay đổi.
3. Tắt Kubernetes contributor và xác nhận nhánh dữ liệu biến mất sau khi tiến trình dùng cấu hình mới. Phân biệt kết quả này với lỗi 404 của cả endpoint.
4. Xem một phản hồi `inside: false`. Nêu ít nhất ba nguyên nhân cần kiểm tra trước khi kết luận ứng dụng ở ngoài cluster.
5. Với ứng dụng chỉ cần tên Pod và namespace, giải thích lựa chọn Downward API và những điều kiện phải kiểm tra trước khi bỏ quyền gọi API server.

Bạn đã nắm được bài khi có thể xác định đúng instance từ metadata, chỉ ra nguồn và giới hạn của dữ liệu, rồi chọn mức tích hợp Kubernetes vừa đủ cho ứng dụng. Một phản hồi `info` hữu ích cần giúp truy vết triển khai mà không bị dùng thay cho kết luận về sức khỏe.
