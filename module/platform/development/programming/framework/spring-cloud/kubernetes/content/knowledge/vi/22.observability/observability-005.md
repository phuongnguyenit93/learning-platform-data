# Quan sát số dịch vụ, endpoint và danh sách bản sao

Trong chương **Khả năng quan sát** của module **Spring Cloud Kubernetes**, bài này hướng dẫn trả lời ba câu hỏi: ứng dụng nhìn thấy những dịch vụ nào, mỗi dịch vụ có bao nhiêu đích kết nối và các đích ấy tương ứng với bản sao nào đang chạy.

Các câu trả lời giúp điều tra lỗi DiscoveryClient hoặc Spring Cloud LoadBalancer khi scale, rollout hay thay đổi readiness. Chúng cũng giúp phân biệt thay đổi topology với thay đổi cấu hình từ ConfigMap, Secret hoặc Configuration Watcher. Mục tiêu là chọn đúng nguồn dữ liệu để quan sát, với quyền đọc vừa đủ cho chức năng đã chọn.

## Mục tiêu và môi trường

Sau bài học, bạn có thể:

- Phân biệt số Service, tên dịch vụ, EndpointSlice, địa chỉ kết nối và replica.
- Đọc góc nhìn DiscoveryClient mà không gọi mọi phần tử trong danh sách là Pod khỏe mạnh.
- Đối chiếu dữ liệu ứng dụng với Service, EndpointSlice, Pod và Deployment.
- Thiết kế phép đo số lượng có phạm vi, thời gian thu thập và trạng thái lỗi rõ ràng.
- Giải thích sai lệch khi rollout, readiness thay đổi hoặc cache chưa cập nhật.

Phần Java dùng Spring Boot 3.5, Java 17 trở lên và Spring Cloud Kubernetes dòng 3.3 với bộ BOM tương thích; các chi tiết implementation được dẫn đến mã nguồn **3.3.0, Fabric8**. Đây là mốc minh họa, không phải yêu cầu nâng cấp. Với release hoặc client khác, kiểm tra lại nguồn API, cơ chế cache và cấu trúc instance.

Phần Kubernetes dùng EndpointSlice API `discovery.k8s.io/v1`. Các lệnh minh họa chạy trong PowerShell trên namespace thử nghiệm `learning`; ứng dụng được quan sát là `orders-api`. Những kết quả số liệu dưới đây là tình huống học tập, chưa phải kết quả chạy trên cluster của bạn.

## 1. Xác định đối tượng trước khi đếm

Từ “endpoint” có thể chỉ URL HTTP như `/actuator/health`, tài nguyên `Endpoints` cũ, hoặc một đích mạng phía sau Kubernetes Service. Trong bài, endpoint phía sau Service là đối tượng cần quan sát; đường dẫn HTTP của ứng dụng chỉ là một phần của phép kiểm tra kết nối.

| Đại lượng | Đang đếm cái gì? | Có bằng số replica không? |
| --- | --- | --- |
| Số đối tượng Service | Các tài nguyên Service trong phạm vi truy vấn | Không |
| Số tên dịch vụ discovery | Tên do `getServices()` trả về, sau khi loại trùng | Không |
| Số EndpointSlice | Các tài nguyên chia nhóm backend cho Service | Không |
| Số bản ghi instance | Phần tử do `getInstances(serviceId)` trả về | Chỉ có thể trùng trong điều kiện cụ thể |
| Số đích mạng phân biệt | Bộ định danh địa chỉ, cổng và các chiều liên quan | Không luôn bằng số Pod |
| Số Pod phân biệt | Pod được nhận diện bằng UID trong phạm vi xác định | Không luôn bằng số replica mong muốn |
| Replica mong muốn | `Deployment.spec.replicas` | Là mục tiêu của controller |
| Replica ready/available | Các trường trạng thái tương ứng của Deployment | Là kết quả quan sát của controller |

Một Service có thể chọn Pod thuộc nhiều workload. Một Pod có thể phục vụ nhiều Service hoặc nhiều cổng. Service kiểu `ExternalName` có thể trỏ đến tên DNS bên ngoài và không đại diện cho Pod trong cluster. Vì vậy, không có công thức tổng quát “một Service bằng một Deployment”.

Kubernetes lưu backend trong EndpointSlice và đang thay thế API Endpoints cũ; API cũ có các giới hạn như không hỗ trợ dual stack và có thể cắt bớt dữ liệu khi quá nhiều địa chỉ. Xem [Kubernetes Service: EndpointSlices và Endpoints](https://kubernetes.io/docs/concepts/services-networking/service/#endpointslices).

### 1.1. Đặt phạm vi cho từng con số

Trước khi so sánh, ghi lại:

- Cluster và namespace đang đọc.
- Service hoặc bộ lọc được áp dụng.
- Nguồn dữ liệu: API Kubernetes, DiscoveryClient hay cache của thành phần khác.
- Quy tắc readiness và lựa chọn cổng.
- Thời điểm bắt đầu/kết thúc thu thập.

Ví dụ: “DiscoveryClient của observer A thấy hai đích cho `orders-api` trong namespace `learning` lúc 10:00:15” có thể kiểm tra được. Câu “hệ thống có hai replica” thiếu cả đối tượng lẫn phạm vi.

### 1.2. Tên dịch vụ và danh tính tài nguyên

`DiscoveryClient.getServices()` trả danh sách tên; Spring Cloud Kubernetes loại tên trùng khi cùng tên xuất hiện ở nhiều namespace. Do đó, hai Service `team-a/orders-api` và `team-b/orders-api` có thể chỉ đóng góp một tên `orders-api` trong danh sách discovery. Xem [DiscoveryClient: tên dịch vụ và instance](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/discovery-client.html).

Đối với kiểm kê tài nguyên, dùng khóa:

~~~text
(cluster, namespace, serviceName)
~~~

Đối với danh sách đích kết nối, thêm địa chỉ, cổng và giao thức hoặc scheme theo dữ liệu nguồn. Đối với số Pod, ưu tiên Pod UID. Không coi `host:port` là định danh Pod bền vững vì địa chỉ có thể được tái sử dụng.

## 2. Theo dõi đường đi từ replica đến đích mà ứng dụng thấy

~~~mermaid
flowchart LR
    Desired["Deployment: replica mong muốn"] --> Pods["Pod và trạng thái Ready"]
    Selector["Service selector"] --> Slices["EndpointSlice và điều kiện endpoint"]
    Pods --> Slices
    Slices --> Source["Nguồn topology mà client sử dụng"]
    Source --> Discovery["DiscoveryClient: danh sách instance"]
    Discovery --> LB["Spring Cloud LoadBalancer và cache nếu có"]
    LB --> Request["Kết nối thực tế của request"]
~~~

Sơ đồ thể hiện quan hệ để đối chiếu, không khẳng định mọi implementation đều đọc EndpointSlice trực tiếp. Ở Fabric8 3.3.0, đường `getInstances()` trong [KubernetesDiscoveryClient](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.0/spring-cloud-kubernetes-fabric8-discovery/src/main/java/org/springframework/cloud/kubernetes/fabric8/discovery/KubernetesDiscoveryClient.java) đọc tài nguyên Endpoints; EndpointSlice được dùng trong bài như nguồn đối chiếu của Kubernetes. Không suy ra rằng một cờ cấu hình liên quan đến EndpointSlice sẽ thay đổi mọi đường đọc của mọi phiên bản.

Trong một ca đơn giản, có ba replica mong muốn, ba Pod được Service chọn nhưng một Pod chưa Ready:

| Góc nhìn | Giá trị minh họa |
| --- | --- |
| Deployment mong muốn | 3 |
| Pod được selector chọn | 3 |
| Pod Ready | 2 |
| Backend đủ điều kiện theo chính sách thông thường | 2 |
| Instance discovery khi không bao gồm địa chỉ chưa ready | Có thể là 2 |
| Request nghiệp vụ thành công | Cần kiểm tra riêng |

Giá trị “2” không tự chứng minh mất một Pod. Nó có thể phản ánh chính sách readiness đúng như dự kiến.

Ở Kubernetes, EndpointSlice có các điều kiện `ready`, `serving`, `terminating`. API quy định giá trị thiếu của `ready` được diễn giải là true; giá trị thiếu của `terminating` là false. Đừng biến trường thiếu thành false một cách máy móc. Xem [EndpointSlice API: EndpointConditions](https://kubernetes.io/docs/reference/kubernetes-api/discovery/endpoint-slice-v1/#EndpointConditions).

Service bật `publishNotReadyAddresses` làm thay đổi ý nghĩa thông thường của `ready`. Khi cần kiểm tra Pod thực sự Ready, đối chiếu Pod condition và các điều kiện endpoint phù hợp. Không dùng một bộ lọc ready tùy ý thay cho đầy đủ chính sách định tuyến của kube-proxy hoặc service mesh.

## 3. Lấy dữ liệu gốc bằng kubectl

### 3.1. Xem Service, workload và Pod

~~~powershell
kubectl config current-context
kubectl -n learning get services
kubectl -n learning get service orders-api -o yaml
kubectl -n learning get deployment orders-api
kubectl -n learning get pods -l app=orders-api -o wide
~~~

Bộ lọc `app=orders-api` chỉ đúng nếu khớp selector thực tế của Service và workload trong môi trường thử nghiệm. Luôn đọc `spec.selector` trước khi sử dụng lại một bộ lọc từ ví dụ. Với Service không có selector, cần xem ai quản lý EndpointSlice thay vì tự suy ra danh sách Pod.

Đếm đối tượng Service bằng JSON, có kiểm tra lỗi lệnh:

~~~powershell
$serviceJson = kubectl -n learning get services -o json
if ($LASTEXITCODE -ne 0) {
    throw 'Không đọc được danh sách Service'
}
$serviceList = $serviceJson | ConvertFrom-Json
@($serviceList.items).Count
~~~

Đây là số đối tượng Service mà tài khoản `kubectl` đọc được trong namespace. Nó không tự bằng số tên DiscoveryClient nhìn thấy, vì danh tính truy cập và bộ lọc có thể khác. Cú pháp JSON, label selector và output của lệnh được mô tả tại [kubectl get](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_get/).

### 3.2. Xem tất cả EndpointSlice của một Service

~~~powershell
kubectl -n learning get endpointslices -l kubernetes.io/service-name=orders-api
kubectl -n learning get endpointslices -l kubernetes.io/service-name=orders-api -o yaml
~~~

Kiểm tra `addressType`, `ports`, `endpoints.addresses`, `conditions` và `targetRef`. Một Service có nhiều slice không có nghĩa nó có cùng số replica.

Khi tổng hợp, đọc tất cả slice của Service và loại các đích trùng. Endpoint có thể xuất hiện lặp trong các slice; dual stack còn có thể cho một Pod nhiều địa chỉ. Xem [EndpointSlices: quản lý và endpoint trùng](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/#duplicate-endpoints).

### 3.3. Liệt kê địa chỉ và Pod đích để đối chiếu

Đoạn PowerShell sau chỉ tạo bảng địa chỉ, không tự tính “replica khỏe mạnh”:

~~~powershell
$sliceJson = kubectl -n learning get endpointslices -l kubernetes.io/service-name=orders-api -o json
if ($LASTEXITCODE -ne 0) {
    throw 'Không đọc được EndpointSlice'
}
$sliceList = $sliceJson | ConvertFrom-Json

$rows = @(
    foreach ($slice in $sliceList.items) {
        foreach ($endpoint in $slice.endpoints) {
            foreach ($address in $endpoint.addresses) {
                [pscustomobject]@{
                    Slice       = $slice.metadata.name
                    AddressType = $slice.addressType
                    Address     = $address
                    Pod         = $endpoint.targetRef.name
                    PodUid      = $endpoint.targetRef.uid
                    Ready       = $endpoint.conditions.ready
                    Serving     = $endpoint.conditions.serving
                    Terminating = $endpoint.conditions.terminating
                }
            }
        }
    }
)
$rows | Format-Table -AutoSize
~~~

Bảng có thể có nhiều dòng cho một Pod. Chỉ đếm Pod UID khi `targetRef.kind` là `Pod`, UID có giá trị và đối tượng nằm trong phạm vi cần quan sát. Endpoint bên ngoài hoặc tài nguyên tự quản lý có thể không có Pod đích.

Để đếm đích mạng, kết hợp địa chỉ với cổng/giao thức của slice, rồi loại trùng theo định nghĩa đã chọn. Nếu nhiều bản ghi cùng khóa có trạng thái khác nhau trong lúc chuyển tiếp, giữ lại dấu hiệu bất nhất để điều tra; không tùy tiện chọn bản ghi đầu tiên.

### 3.4. Xem replica và tiến độ rollout

~~~powershell
kubectl -n learning get deployment orders-api -o jsonpath='{.spec.replicas}{"\n"}{.status.replicas}{"\n"}{.status.readyReplicas}{"\n"}{.status.availableReplicas}{"\n"}{.status.updatedReplicas}{"\n"}'
kubectl -n learning rollout status deployment/orders-api
~~~

Các dòng lần lượt là replica mong muốn, replica trong status, ready, available và updated; một số trường status có thể chưa tồn tại. Trong rolling update, replica cũ và mới có thể cùng tồn tại. `available` còn chịu điều kiện như `minReadySeconds`. Xem [Kubernetes Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/).

Các lần đọc Service, Pod, EndpointSlice và Deployment diễn ra ở những thời điểm khác nhau. Chênh lệch ngắn trong lúc rollout cần được quan sát lại trước khi diễn giải thành lỗi.

## 4. Đọc góc nhìn DiscoveryClient từ ứng dụng

Quan sát từ `kubectl` dùng tài khoản của người vận hành. Để biết ứng dụng thực sự nhìn thấy gì, cần đọc chính `DiscoveryClient` trong tiến trình đó.

Ví dụ sau tạo endpoint Actuator **do ứng dụng tự viết**, tên `discoveryinventory`. Đây không phải endpoint mặc định của Spring Cloud Kubernetes. Nó phục vụ hai thao tác chẩn đoán:

~~~text
GET /actuator/discoveryinventory
    Danh sách tên dịch vụ và số tên phân biệt

GET /actuator/discoveryinventory/orders-api
    Danh sách instance và số đích phân biệt của orders-api
~~~

Mỗi lần đọc chỉ liệt kê catalog hoặc tra cứu một dịch vụ. Ví dụ không quét `getInstances()` cho toàn bộ catalog mỗi lần lấy metric.

### 4.1. Dependency và cấu hình phạm vi

Trong ứng dụng Spring Boot đã quản lý phiên bản bằng BOM tương thích:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-fabric8</artifactId>
</dependency>
~~~

Cấu hình ví dụ:

~~~yaml
spring:
  application:
    name: discovery-observer
  cloud:
    kubernetes:
      client:
        namespace: learning
      discovery:
        enabled: true
        all-namespaces: false
        namespaces:
          - learning
        include-not-ready-addresses: false
        include-external-name-services: false
        catalog-services-watch:
          enabled: false
        metadata:
          add-labels: false
          add-annotations: false
          add-ports: false
          add-pod-labels: false
          add-pod-annotations: false

management:
  endpoints:
    web:
      exposure:
        include: "health,discoveryinventory"
~~~

Các lựa chọn readiness và metadata được khai báo rõ để dễ đối chiếu; chúng không biểu thị mặc định chung cho mọi phiên bản. Có thể kiểm tra các trường cấu hình tại [KubernetesDiscoveryProperties 3.3.0](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/discovery/KubernetesDiscoveryProperties.java).

Bài thử nghiệm chỉ dùng một nguồn discovery là Kubernetes. Nếu ứng dụng thực tế có CompositeDiscoveryClient hoặc nhiều registry, phải xác định client nào đóng góp dữ liệu. Các abstraction chung không bảo đảm catalog chỉ đến từ Kubernetes; xem [Spring Cloud Commons: DiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html).

### 4.2. Viết endpoint kiểm kê

Đặt lớp sau trong package được Spring Boot quét:

~~~java
package com.example.observer;

import java.time.Instant;
import java.util.List;
import java.util.Objects;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.Selector;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.kubernetes.commons.discovery.KubernetesServiceInstance;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "discoveryinventory")
public class DiscoveryInventoryEndpoint {

    private final DiscoveryClient discoveryClient;

    public DiscoveryInventoryEndpoint(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @ReadOperation
    public CatalogView catalog() {
        Instant startedAt = Instant.now();
        List<String> names = discoveryClient.getServices().stream()
                .filter(Objects::nonNull)
                .distinct()
                .sorted()
                .toList();

        return new CatalogView(discoveryClient.description(), startedAt,
                Instant.now(), names.size(), names);
    }

    @ReadOperation
    public ServiceView service(@Selector String serviceId) {
        Instant startedAt = Instant.now();
        List<InstanceView> instances = discoveryClient.getInstances(serviceId)
                .stream()
                .map(this::toView)
                .toList();

        long uniqueTargets = instances.stream()
                .map(instance -> new TargetKey(instance.namespace(),
                        instance.host(), instance.port(), instance.secure()))
                .distinct()
                .count();

        return new ServiceView(discoveryClient.description(), serviceId,
                startedAt, Instant.now(), instances.size(),
                uniqueTargets, instances);
    }

    private InstanceView toView(ServiceInstance instance) {
        String namespace = instance instanceof KubernetesServiceInstance kubernetes
                ? kubernetes.getNamespace() : null;

        return new InstanceView(namespace, instance.getInstanceId(),
                instance.getHost(), instance.getPort(), instance.isSecure());
    }

    private record TargetKey(
            String namespace, String host, int port, boolean secure) {
    }

    public record CatalogView(
            String source, Instant startedAt, Instant completedAt,
            int serviceNameCount, List<String> serviceNames) {
    }

    public record ServiceView(
            String source, String serviceId,
            Instant startedAt, Instant completedAt,
            int instanceEntryCount, long uniqueTargetCount,
            List<InstanceView> instances) {
    }

    public record InstanceView(
            String namespace, String instanceId,
            String host, int port, boolean secure) {
    }
}
~~~

`@Selector` ánh xạ tên dịch vụ vào đoạn đường dẫn. Cơ chế endpoint tùy chỉnh và HTTP exposure được mô tả tại [Spring Boot: implementing custom endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom).

Điểm quan trọng trong thiết kế ví dụ:

- `serviceNameCount` đếm tên phân biệt, không đếm đối tượng Service trên toàn cluster.
- `instanceEntryCount` giữ số bản ghi client trả về, kể cả bản ghi lặp.
- `uniqueTargetCount` loại trùng theo namespace, host, port và secure trong **một dịch vụ của một cluster**.
- `namespace` lấy qua interface Kubernetes khi có; null nghĩa là không lấy được thông tin này, không tự gán namespace mặc định.
- `startedAt` và `completedAt` ghi khoảng thời gian gọi client, không chứng minh dữ liệu bên dưới là mới đến thời điểm đó.
- Lỗi được client ném ra sẽ làm request thất bại; lớp không biến exception thành danh sách rỗng.

Interface `KubernetesServiceInstance` có phương thức `getNamespace()`; không cần đoán tên một khóa metadata tùy ý. Xem [KubernetesServiceInstance 3.3.0](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/discovery/KubernetesServiceInstance.java).

Khóa loại trùng trên không đếm UID của Pod, không phân loại EndpointSlice conditions và không đại diện cho mọi giao thức. Các trường ấy không nằm trong hợp đồng `ServiceInstance` thông thường. Nếu cần dữ liệu đó, dùng nguồn Kubernetes tương ứng.

Endpoint cũng không thể phát hiện mọi trường hợp một implementation tự xử lý lỗi rồi trả rỗng. Vì vậy, kết quả thành công vẫn cần được đọc cùng log và trạng thái của client. Với serviceId không tồn tại và Service có zero backend, cả hai đều có thể cho danh sách instance rỗng.

### 4.3. RBAC cho đường đọc đã chọn

Với ví dụ Fabric8 3.3.0 dùng các phép đọc trực tiếp, có thể chuẩn bị Role trong namespace thử nghiệm như sau. Namespace `learning` phải tồn tại trước:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: discovery-observer
  namespace: learning
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: discovery-observer-reader
  namespace: learning
rules:
  - apiGroups: [""]
    resources: ["services", "endpoints"]
    verbs: ["get", "list"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: discovery-observer-reader
  namespace: learning
subjects:
  - kind: ServiceAccount
    name: discovery-observer
    namespace: learning
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: discovery-observer-reader
~~~

Quyền đọc Pod phục vụ các thành phần nhận diện Pod/health đi kèm nếu chúng hoạt động. Role không cho ứng dụng xem trạng thái Deployment hoặc liệt kê Pod; những phép đối chiếu bằng `kubectl` trong bài dùng tài khoản riêng của người vận hành.

Gắn `serviceAccountName: discovery-observer` vào Pod template của Deployment observer và bảo đảm client có thông tin xác thực cần thiết. Chọn đúng namespace cho cả workload lẫn RoleBinding.

Nếu client thực tế đọc/watch EndpointSlice, bổ sung quy tắc tương ứng với API group `discovery.k8s.io` và resource `endpointslices`, cùng đúng các verb được sử dụng. Nếu sử dụng informer hoặc catalog watch, đánh giá thêm quyền `watch`. Không coi Role của ví dụ là một danh sách quyền đủ cho mọi backend/client.

Khi kiểm tra quyền, dùng đúng ServiceAccount thay vì tài khoản admin:

~~~powershell
kubectl auth can-i list services -n learning --as system:serviceaccount:learning:discovery-observer
kubectl auth can-i list endpoints -n learning --as system:serviceaccount:learning:discovery-observer
~~~

Người thực hiện `--as` phải có quyền impersonation. Lỗi impersonation không chứng minh ServiceAccount của ứng dụng thiếu quyền đọc tài nguyên.

### 4.4. Gọi endpoint và đọc kết quả

Giả sử Deployment observer đã được triển khai với cổng HTTP 8080, chọn một Pod để cố định góc nhìn:

~~~powershell
$observerPod = kubectl -n learning get pods -l app=discovery-observer -o jsonpath='{.items[0].metadata.name}'
kubectl -n learning port-forward "pod/$observerPod" 18080:8080
~~~

Trong terminal khác:

~~~powershell
curl.exe -i http://localhost:18080/actuator/discoveryinventory
curl.exe -i http://localhost:18080/actuator/discoveryinventory/orders-api
~~~

Nếu có Spring Security hoặc gateway, cung cấp thông tin xác thực theo môi trường. Exposure không thay thế phân quyền HTTP. Giới hạn endpoint này cho người vận hành vì nó công bố topology nội bộ.

Phản hồi instance minh họa:

~~~json
{
  "source": "Fabric8 Kubernetes Discovery Client",
  "serviceId": "orders-api",
  "startedAt": "2026-11-24T03:00:15Z",
  "completedAt": "2026-11-24T03:00:15.080Z",
  "instanceEntryCount": 2,
  "uniqueTargetCount": 2,
  "instances": [
    {
      "namespace": "learning",
      "instanceId": "pod-uid-a",
      "host": "10.244.1.11",
      "port": 8080,
      "secure": false
    },
    {
      "namespace": "learning",
      "instanceId": "pod-uid-b",
      "host": "10.244.2.12",
      "port": 8080,
      "secure": false
    }
  ]
}
~~~

Các giá trị instanceId ở đây chỉ minh họa. Không mặc định instanceId luôn là Pod UID cho mọi loại instance, đặc biệt với endpoint bên ngoài hoặc Service không có Pod đích.

Đối chiếu host và port với tài nguyên nguồn mà client thực sự dùng. Với đường đọc Endpoints trong mốc Fabric8 đã chọn:

~~~powershell
kubectl -n learning get endpoints orders-api -o yaml
~~~

EndpointSlice giúp kiểm tra topology hiện đại, còn lệnh Endpoints giúp giải thích góc nhìn của client cũ. Khi có sai lệch do giới hạn nguồn dữ liệu, xử lý theo client/release được hỗ trợ thay vì chỉ sửa cách đếm trên dashboard.

## 5. Chuyển việc kiểm tra thành quan sát liên tục

Endpoint chẩn đoán giúp mở danh sách chi tiết. Dashboard cần các phép đo tổng hợp theo thời gian. Hai nhu cầu này nên dùng chung định nghĩa số lượng nhưng không nhất thiết dùng chung cách gọi nguồn dữ liệu.

### 5.1. Định nghĩa metric trước khi đặt tên

Các tên dưới đây là **đề xuất metric tùy chỉnh cho bài học**, chưa được đăng ký bởi lớp Java ở phần trước và không phải cam kết về metric có sẵn trong Spring Cloud Kubernetes:

| Tên metric minh họa | Loại | Ý nghĩa |
| --- | --- | --- |
| `learning.discovery.service.names` | Gauge | Số tên discovery phân biệt trong phạm vi observer |
| `learning.discovery.instance.entries` | Gauge | Số bản ghi của một serviceId |
| `learning.discovery.targets.unique` | Gauge | Số đích phân biệt theo khóa đã định nghĩa |
| `learning.discovery.collection.success` | Gauge | 1 nếu lần thu thập tương ứng thành công, 0 nếu thất bại |
| `learning.discovery.snapshot.age` | Gauge, đơn vị giây | Tuổi của kết quả thu thập thành công gần nhất |
| `learning.discovery.collection.errors` | Counter | Số lần thu thập thất bại |

Số Service và số instance tăng giảm theo topology nên phù hợp với gauge; số lỗi tích lũy là counter. Cách gauge được lấy mẫu được giải thích tại [Micrometer Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html).

Khi triển khai thật, cần bổ sung collector, đăng ký meter và backend xuất metric phù hợp. Việc expose `discoveryinventory` không tự tạo các time series trong bảng.

### 5.2. Thu thập ngoài luồng scrape

Một mô hình có thể áp dụng:

~~~text
Tác vụ thu thập có chu kỳ và timeout
    -> Đọc DiscoveryClient cho phạm vi đã chọn
    -> Tạo snapshot bất biến
    -> Công bố snapshot bằng một lần thay tham chiếu
    -> Gauge chỉ đọc dữ liệu trong bộ nhớ

Endpoint quản trị
    -> Đọc snapshot và danh sách instance khi cần điều tra
~~~

Ví dụ có thể bắt đầu với chu kỳ 30 giây trong cluster nhỏ rồi điều chỉnh theo độ trễ cần quan sát và chi phí thực tế. Đây là lựa chọn thiết kế của bài, không phải mặc định của framework.

Không gọi API Kubernetes trong hàm đọc gauge. Nếu backend scrape thường xuyên hoặc có nhiều observer, cách đó làm tải thu thập phụ thuộc trực tiếp vào số request giám sát. Quét toàn bộ catalog còn có thể tạo nhiều lần gọi nguồn cho mỗi chu kỳ.

Snapshot cần ghi tối thiểu phạm vi, nguồn client, thời điểm bắt đầu/kết thúc và kết quả của từng truy vấn. Thời gian thu thập mới không chứng minh cache discovery bên dưới mới; nếu có thể, quan sát thêm thời điểm cập nhật nguồn/cache hoặc xác nhận bằng phép đối chiếu độc lập.

Nếu một dịch vụ lỗi trong khi các dịch vụ khác đọc được, ghi rõ snapshot là một phần. Không trình bày tổng từ phần dữ liệu thành công như tổng đầy đủ của toàn bộ phạm vi.

### 5.3. Không biến lỗi thành zero backend

Giả sử lần thu thập gần nhất thấy hai đích. Lần tiếp theo API server bị timeout:

~~~text
Kết quả đúng về mặt quan sát:
    lần đọc mới nhất thất bại
    kết quả thành công gần nhất vẫn là 2
    dữ liệu đó đã cũ thêm bao nhiêu giây

Kết quả dễ gây hiểu lầm:
    số backend = 0
    không có thông tin về lỗi thu thập
~~~

Có thể giữ giá trị thành công gần nhất kèm trạng thái lỗi và tuổi dữ liệu, hoặc biểu diễn giá trị hiện tại là không xác định theo khả năng của backend. Khi quá hạn độ mới cho phép, dashboard phải làm rõ kết quả không còn đáng tin cho quyết định hiện tại.

Danh sách rỗng sau một phép đọc thành công cũng cần ngữ cảnh: Service có thể bị xóa, không khớp selector, không có backend ready hoặc bị loại bởi bộ lọc client. Một kết quả zero chỉ nên mang nghĩa đã được định nghĩa, không gộp mọi nguyên nhân.

### 5.4. Giữ danh tính chi tiết ở đúng nơi

Metric tổng hợp thường có các chiều ổn định như cluster, namespace và service. Danh sách Pod UID, IP, instanceId và nội dung metadata phù hợp hơn với bảng chi tiết hoặc log có kiểm soát.

Không gắn cả danh sách replica hoặc giá trị annotation tùy ý thành label metric. Các giá trị thay đổi liên tục có thể tạo nhiều chuỗi thời gian và làm việc tổng hợp khó hiểu.

Nếu ba observer cùng nhìn thấy ba đích, cộng các gauge có thể cho 9. Kết quả đó đếm ba lần cùng một góc nhìn topology. Giữ chiều observer để phát hiện sai lệch, hoặc thiết kế một collector đại diện; không diễn giải tổng qua observer thành số replica.

Một dashboard đủ dùng cho bài thực hành có:

1. Phạm vi cluster/namespace và loại client.
2. Số tên dịch vụ cùng trạng thái thu thập.
3. Số instance của từng dịch vụ và số đích phân biệt.
4. Replica mong muốn, ready và available từ nguồn workload.
5. Tuổi snapshot, lỗi nguồn và độ trễ thu thập.
6. Liên kết mở danh sách instance/Pod tương ứng.

Thông tin workload không tự xuất hiện trong DiscoveryClient. Nếu dashboard cần so sánh desired và ready, dùng nguồn theo dõi tài nguyên workload được cấp quyền riêng.

## 6. Diễn giải thay đổi và tìm nguyên nhân sai lệch

### 6.1. Những tình huống cần phân biệt

| Quan sát | Giải thích có thể có | Bước đối chiếu tiếp theo |
| --- | --- | --- |
| Service còn, instance bằng 0 | Không có backend đủ điều kiện, sai selector hoặc client lọc hết | Service selector, EndpointSlice, nguồn topology client dùng |
| Pod ở phase Running nhưng chưa vào discovery | Pod chưa Ready hoặc readiness bị nguồn khác diễn giải khác | Pod conditions và điều kiện endpoint |
| Deployment mong muốn 3, discovery thấy 4 | Rollout đang có replica cũ và mới, nhiều workload cùng selector hoặc dữ liệu chuyển tiếp | OwnerReference, ReplicaSet, UID và thời điểm đọc |
| EndpointSlice có nhiều dòng hơn Pod | Nhiều địa chỉ, nhiều cổng hoặc bản ghi trùng | Loại trùng theo mục tiêu đo; đếm UID nếu cần số Pod |
| kubectl thấy backend nhưng ứng dụng không thấy | Khác namespace, quyền, bộ lọc, client hoặc cache | Danh tính ServiceAccount và cấu hình discovery |
| DiscoveryClient thấy đích nhưng request lỗi | Sai cổng, scheme, đường mạng hoặc lỗi nghiệp vụ | Thử kết nối có kiểm soát và xem log request |
| Nhiều observer báo kết quả khác nhau | Khác phạm vi hoặc độ mới của dữ liệu | So sánh nguồn, thời điểm và cấu hình từng observer |
| Địa chỉ biến mất ở nguồn nhưng request cũ còn hoạt động | Cache phía gọi hoặc kết nối đang được tái sử dụng | Log đích thực tế, vòng đời cache và connection pool |

Đối với Service nhiều cổng, phải kiểm tra cổng mà DiscoveryClient chọn. Số instance đúng vẫn có thể đi cùng cổng sai. Đường đọc Endpoints ở Fabric8 đã chọn xử lý địa chỉ ready và tùy chọn địa chỉ chưa ready trong [Fabric8KubernetesDiscoveryClientUtils](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.0/spring-cloud-kubernetes-fabric8-discovery/src/main/java/org/springframework/cloud/kubernetes/fabric8/discovery/Fabric8KubernetesDiscoveryClientUtils.java).

Quy trình kiểm tra Service và endpoint từ nguồn Kubernetes được trình bày tại [Debug Services](https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/). Dùng quy trình đó cùng góc nhìn client để xác định tầng bắt đầu có sai lệch.

### 6.2. Phân biệt topology với việc cập nhật cấu hình

Configuration Watcher theo dõi thay đổi cấu hình theo chức năng được bật; nó không phải bằng chứng rằng catalog discovery hoặc cache LoadBalancer đã đổi cùng thời điểm.

Ví dụ, cập nhật ConfigMap làm ứng dụng khởi động lại hoặc thay đổi readiness. Sự kiện cấu hình có thể dẫn đến thay đổi Pod và backend, nhưng cần quan sát từng bước. Không kết luận “Watcher lỗi” chỉ vì số instance chưa đổi ngay sau khi lưu ConfigMap.

Ngược lại, scale Deployment làm topology thay đổi mà không nhất thiết thay ConfigMap hay Secret. Chọn tín hiệu từ workload và service discovery cho tình huống đó.

### 6.3. Đặt điều kiện cảnh báo theo dữ liệu có thể tin cậy

Một chính sách minh họa cho dịch vụ bắt buộc luôn có backend:

~~~text
Chỉ đánh giá sự cố thiếu backend khi:
    phép thu thập của đúng service thành công
    dữ liệu chưa vượt ngưỡng tuổi cho phép
    dịch vụ nằm trong danh sách cần theo dõi
    zero backend kéo dài vượt cửa sổ chuyển tiếp đã chấp nhận
~~~

Cần cảnh báo riêng cho lỗi hoặc mất dữ liệu quan sát. Nếu truy vấn nguồn thất bại, hệ thống giám sát nên nói “không xác định được topology” thay vì khẳng định “mọi replica đã chết”.

Cửa sổ chuyển tiếp phải xét thời gian rollout, cập nhật readiness, chu kỳ collector và cache nếu có. Chọn con số theo yêu cầu của hệ thống; không mặc định mọi chênh lệch giữa desired và discovered đều cần báo động.

## 7. Thực hành có kiểm soát

Thực hiện trong namespace thử nghiệm, với workload do bạn quản lý:

1. Ghi lại context, selector, nguồn discovery và trạng thái ban đầu của Service, Deployment, Pod, EndpointSlice cùng endpoint kiểm kê.
2. Nếu môi trường không bị HPA hoặc bộ điều phối khác quản lý số replica, scale `orders-api` từ một lên ba replica bằng quy trình của bạn.
3. Quan sát từng nguồn cho đến khi trạng thái ổn định. Giải thích vì sao số tên dịch vụ có thể giữ nguyên trong khi danh sách instance dài hơn.
4. Cho một Pod chưa Ready bằng cơ chế thử nghiệm đã chuẩn bị, rồi so sánh số Pod tồn tại, số Pod Ready và các instance discovery trả về.
5. Thực hiện một rollout và phân biệt bản sao cũ/mới bằng UID, owner và thời điểm quan sát. Không chỉ dùng tổng số dòng để đánh giá.
6. Thử một tình huống đọc nguồn thất bại trong môi trường cô lập. Kiểm tra việc báo lỗi, giữ hoặc vô hiệu hóa snapshot cũ theo thiết kế; không ghi zero giả.
7. Đưa workload về trạng thái và số replica ban đầu theo quy trình thử nghiệm.

Không chỉnh trực tiếp EndpointSlice do controller quản lý để tạo kết quả giả cho bài thử. Thay đổi workload hoặc Service theo tình huống cần quan sát, rồi theo dõi controller cập nhật nguồn.

## 8. Câu hỏi tự kiểm tra

- Hai namespace đều có `orders-api`: vì sao số tên từ `getServices()` có thể là một?
- Một Service có hai EndpointSlice và ba Pod: cần đọc thêm gì trước khi nói có bao nhiêu backend?
- Vì sao `Running`, `Ready`, `availableReplicas` và instance discovery là các tín hiệu khác nhau?
- Khi nào số đích IP/cổng lớn hơn số Pod UID mà không có lỗi?
- Một observer thấy zero instance, observer khác thấy ba: dữ liệu nào giúp xác định nguyên nhân?
- Vì sao tăng quyền RBAC không sửa được lỗi chọn sai cổng hoặc cache chưa cập nhật?
- Cần bổ sung gì trước khi biến endpoint chẩn đoán trong bài thành nguồn metric chạy thường xuyên?
