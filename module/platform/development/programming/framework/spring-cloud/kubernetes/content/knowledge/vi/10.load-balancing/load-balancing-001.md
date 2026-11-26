# Tích hợp Spring Cloud LoadBalancer với Kubernetes DiscoveryClient

Trong chương **Cân bằng tải** của module **SPRING_CLOUD_KUBERNETES**, mục tiêu của việc tích hợp là để ứng dụng gọi một **service ID ổn định**, còn địa chỉ instance được tìm và lựa chọn khi thực hiện yêu cầu.

Ví dụ xuyên suốt bài học: orders-api cần gọi inventory-api có ba Pod. Mã nghiệp vụ dùng địa chỉ logic http://inventory-api/internal/identity thay vì giữ danh sách IP Pod. Kubernetes DiscoveryClient cung cấp các instance; Spring Cloud LoadBalancer chọn một instance; HTTP client gửi yêu cầu đến địa chỉ đã chọn.

Đây là một phần của việc tích hợp ứng dụng Spring với Kubernetes bên cạnh ConfigMap, Secret và Configuration Watcher. Cân bằng tải chỉ cần những thành phần phục vụ khám phá và gọi dịch vụ. Không cần bật thêm cơ chế cập nhật cấu hình hay cấp quyền đọc Secret chỉ để gọi được một service ID.

Sau bài học, bạn có thể:

- Giải thích trách nhiệm riêng của DiscoveryClient, LoadBalancer và HTTP client.
- Chọn dependency phù hợp cho một luồng discovery dựa trên Kubernetes.
- Cấu hình WebClient có hỗ trợ LoadBalancer và gọi bằng service ID.
- Đối chiếu Service, namespace, endpoint, cổng và quyền RBAC.
- Kiểm chứng yêu cầu thực sự đi tới nhiều instance.
- Nhận diện ảnh hưởng của readiness, cache, timeout và retry khi Pod thay đổi.

## 1. Từ service ID tới một yêu cầu HTTP thật

Giả sử inventory-api có các endpoint sẵn sàng sau:

| Instance | Địa chỉ | Cổng ứng dụng |
| --- | --- | --- |
| inventory-api-a | 10.42.1.11 | 8080 |
| inventory-api-b | 10.42.2.12 | 8080 |
| inventory-api-c | 10.42.3.13 | 8080 |

Các địa chỉ trong bảng chỉ minh họa. Không chép chúng vào cấu hình ứng dụng.

~~~mermaid
sequenceDiagram
    participant A as Mã gọi trong orders-api
    participant W as WebClient có LoadBalancer
    participant L as Spring Cloud LoadBalancer
    participant D as Kubernetes DiscoveryClient
    participant P as Một instance inventory-api
    A->>W: GET http://inventory-api/internal/identity
    W->>L: Chọn đích cho service ID inventory-api
    L->>D: Lấy danh sách instance qua supplier
    D-->>L: Danh sách ServiceInstance
    L-->>W: Instance được chọn, ví dụ 10.42.2.12:8080
    W->>P: GET /internal/identity
    P-->>A: Kết quả nghiệp vụ
~~~

Sơ đồ thể hiện quan hệ trách nhiệm. Nó không có nghĩa mỗi yêu cầu đều tạo một lần đọc trực tiếp từ Kubernetes API. Danh sách có thể đi qua bộ nhớ đệm và cơ chế theo dõi tài nguyên.

| Thành phần | Trách nhiệm | Điều không tự thực hiện |
| --- | --- | --- |
| Kubernetes DiscoveryClient | Tìm dịch vụ và cung cấp ServiceInstance | Chọn thay ứng dụng mọi chính sách cân bằng tải |
| ServiceInstanceListSupplier | Cung cấp danh sách ứng viên cho LoadBalancer | Gửi HTTP request nghiệp vụ |
| Spring Cloud LoadBalancer | Chọn một ứng viên theo thuật toán và cấu hình | Tạo Pod hoặc tăng số replica |
| WebClient được tích hợp | Ánh xạ địa chỉ logic thành đích thực và gửi HTTP | Tự cấp quyền truy cập Kubernetes API |
| Kubernetes | Quản lý Service, endpoint, Pod và mạng | Tự gắn bộ lọc LoadBalancer vào mọi HTTP client Java |

Spring Cloud LoadBalancer có supplier dựa trên DiscoveryClient và mặc định cung cấp thuật toán round-robin. Các chính sách tùy biến có thể thay đổi hành vi này. [Tài liệu Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html).

Một danh sách instance chính xác vẫn chưa đủ: caller phải có đường mạng đến địa chỉ được trả, dịch vụ phải lắng nghe đúng cổng và yêu cầu phải dùng giao thức phù hợp.

## 2. Phân biệt ba cơ chế thường bị gọi chung là “load balancing”

### 2.1. Gọi Kubernetes Service bằng DNS

Một HTTP client thông thường có thể gọi:

~~~text
http://inventory-api.shop-demo.svc.cluster.local/internal/identity
~~~

Với Service ClusterIP thông thường, tên DNS dẫn đến địa chỉ Service, rồi tầng mạng Kubernetes chuyển lưu lượng tới backend. Việc phân phối thực tế còn phụ thuộc dataplane, kết nối đang dùng và cấu hình Service. Không được mặc định mỗi HTTP request trên một kết nối giữ lâu sẽ đổi Pod.

Nếu nhu cầu chỉ là gọi một Service nội bộ, cách này có thể đã đủ. Không cần thêm DiscoveryClient chỉ vì hệ thống có nhiều replica.

### 2.2. Cân bằng tải phía ứng dụng bằng danh sách instance

Ở luồng chính của bài, Kubernetes DiscoveryClient cung cấp các endpoint ứng viên và Spring Cloud LoadBalancer chọn đích ở phía caller. WebClient nhận URI có service ID:

~~~text
http://inventory-api/internal/identity
~~~

Địa chỉ cuối có thể là IP Pod và cổng endpoint. Cơ chế này hữu ích khi ứng dụng thật sự cần tích hợp với giao diện DiscoveryClient, điều khiển việc chọn instance hoặc dùng các khả năng của Spring Cloud LoadBalancer.

Không phải mọi chuỗi http://inventory-api đều chứng minh đang dùng cơ chế này: một HTTP client thường cũng có thể phân giải tên ngắn qua DNS nếu chạy trong namespace phù hợp.

### 2.3. Kubernetes Service kiểu LoadBalancer

spec.type: LoadBalancer là một loại Service Kubernetes dùng để tích hợp với cơ chế cung cấp điểm truy cập mạng bên ngoài được môi trường hỗ trợ. Đây là khái niệm khác với Spring Cloud LoadBalancer chạy trong ứng dụng. Bài thực hành dùng Service ClusterIP, không cần chuyển Service sang loại LoadBalancer. [Các loại Service Kubernetes](https://kubernetes.io/docs/concepts/services-networking/service/).

## 3. Chọn một đường tích hợp rõ ràng

Có hai cách tổ chức dependency cần phân biệt:

| Cách tổ chức | Ý nghĩa |
| --- | --- |
| Kubernetes discovery starter và Spring Cloud LoadBalancer starter chung | Dùng supplier dựa trên DiscoveryClient; đây là đường chính của bài |
| Kubernetes LoadBalancer starter chuyên biệt | Có cấu hình đặc thù Kubernetes, trong đó có chế độ POD và SERVICE |

Spring Cloud Kubernetes cung cấp starter LoadBalancer riêng cho Fabric8 và Kubernetes Java Client. Trong chế độ POD của tích hợp chuyên biệt, việc tìm instance dựa trên DiscoveryClient. Chế độ SERVICE sử dụng đích ở cấp Service và có quy tắc chọn cổng, namespace riêng. [LoadBalancer cho Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/load-balancer.html).

Ví dụ tên dependency chuyên biệt:

~~~xml
<!-- Lựa chọn tích hợp chuyên biệt dùng Fabric8 -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-fabric8-loadbalancer</artifactId>
</dependency>
~~~

Không thêm mọi starter vào cùng một ứng dụng để “chắc chắn đủ”. Cần xem dependency bắc cầu và auto-configuration của phiên bản đang dùng, rồi giữ một cách cung cấp danh sách instance dễ giải thích.

Thuộc tính spring.cloud.kubernetes.loadbalancer.mode thuộc tích hợp Kubernetes LoadBalancer chuyên biệt. Không thêm nó vào cấu hình của đường starter chung rồi giả định nó điều khiển supplier bất kỳ.

Các ví dụ bên dưới chọn:

- Ứng dụng Spring Boot có WebFlux và WebClient.
- Kubernetes DiscoveryClient dùng Fabric8, truy cập API trong cluster.
- Spring Cloud LoadBalancer starter chung.
- Namespace thực hành shop-demo.
- EndpointSlice làm nguồn endpoint; phiên bản thư viện và cluster phải hỗ trợ chế độ này.
- Một caller orders-api và ba replica inventory-api.

## 4. Khai báo dependency ở caller

Đưa các dependency sau vào dự án orders-api đã có Spring Boot và Spring Cloud BOM tương thích:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-kubernetes-fabric8</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
</dependencies>
~~~

Đây là phần dependency, không phải một pom.xml hoàn chỉnh. Version được quản lý bởi cấu hình BOM của dự án; không chọn tùy ý các version riêng cho Spring Boot, Spring Cloud Commons và Spring Cloud Kubernetes.

Fabric8 là implementation được chọn trong bài. Nếu dùng Kubernetes Java Client, chọn discovery starter tương ứng theo tài liệu phiên bản thay cho Fabric8. Không cần nạp đồng thời hai implementation để thực hiện cùng ví dụ. [Các implementation Kubernetes DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Nếu classpath có nhiều nguồn discovery, chẳng hạn Kubernetes và một hệ đăng ký khác, cần xác định supplier và DiscoveryClient nào đang cung cấp dữ liệu. Không mặc định mọi instance được tìm thấy đều thuộc Kubernetes chỉ vì dự án có một Kubernetes starter.

## 5. Tạo Service và endpoint phía inventory-api

Service đích trong namespace shop-demo:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: inventory-api
  namespace: shop-demo
spec:
  type: ClusterIP
  selector:
    app: inventory-api
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

Deployment backend minh họa:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-api
  namespace: shop-demo
spec:
  replicas: 3
  selector:
    matchLabels:
      app: inventory-api
  template:
    metadata:
      labels:
        app: inventory-api
    spec:
      containers:
        - name: inventory-api
          image: registry.example.invalid/learning/inventory-api:REPLACE_WITH_BUILT_TAG
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /internal/identity
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
~~~

Namespace shop-demo cần tồn tại trước. Địa chỉ registry.example.invalid và tag REPLACE_WITH_BUILT_TAG là placeholder; phải thay bằng image có thật của ứng dụng trước khi áp dụng manifest. Ví dụ không khẳng định các image này đã được xây dựng hoặc chạy.

Backend có thể là một ứng dụng Spring Boot WebFlux đơn giản, cổng 8080, với controller sau. Controller này thuộc dự án inventory-api riêng:

~~~java
package com.example.inventory;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/internal/identity")
    public String identity() {
        return System.getenv().getOrDefault("HOSTNAME", "local");
    }
}
~~~

Trong bài thực hành, giá trị HOSTNAME giúp quan sát Pod nào xử lý yêu cầu. Endpoint minh họa chỉ trả một định danh, không xuất toàn bộ biến môi trường hay metadata của Pod.

Có ba liên kết phải đúng:

1. Service tên inventory-api là service ID mà caller sử dụng trong ví dụ.
2. selector của Service phải khớp label app trên Pod.
3. targetPort: http phải tìm được cổng có tên http trong Pod, tương ứng 8080.

spring.application.name của caller có thể là orders-api. Nó không đổi tên Service inventory-api và không làm một Service Kubernetes được tạo tự động.

### Cổng 80 và cổng 8080 đi vào đâu?

| Đường gọi | Địa chỉ dự kiến trong ví dụ |
| --- | --- |
| Gọi Service ClusterIP bằng DNS | inventory-api.shop-demo.svc.cluster.local:80 |
| Gọi instance do discovery cung cấp | Một endpoint, ví dụ 10.42.2.12:8080 |

Với đường gọi instance, phải đối chiếu cổng trong ServiceInstance và EndpointSlice thực tế. Không lấy Service port 80 rồi ghép máy móc với IP Pod đang lắng nghe 8080.

Nếu Service có nhiều cổng, cần chọn tên cổng chính tường minh và xác nhận kết quả. Cổng quản lý hoặc metrics không nên trở thành đích mặc định cho yêu cầu nghiệp vụ.

## 6. Cấp quyền discovery cho caller

Vì ví dụ dùng Fabric8 DiscoveryClient truy cập Kubernetes API trực tiếp, ServiceAccount của orders-api cần quyền đọc nguồn discovery.

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-discovery-reader
  namespace: shop-demo
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: orders-discovery-reader
  namespace: shop-demo
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
  name: orders-discovery-reader
  namespace: shop-demo
subjects:
  - kind: ServiceAccount
    name: orders-discovery-reader
    namespace: shop-demo
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: orders-discovery-reader
~~~

Role là bộ quyền trong shop-demo; RoleBinding gắn bộ quyền đó cho ServiceAccount. Không cần ClusterRoleBinding để đọc một namespace. Nếu tài khoản đang được cấp quyền từ nhiều binding, các quyền được cộng lại, không bị Role mới tự thu hẹp. [RBAC của Kubernetes](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Đối chiếu resource và API group với implementation thực tế. Nếu phiên bản hoặc cấu hình sử dụng Endpoints thay cho EndpointSlice, cần quyền endpoints trong core API group tương ứng. Không cấp tất cả API và mọi verb để tránh phải xác định chế độ đang chạy.

Ví dụ không cấp quyền đọc ConfigMap, Secret hoặc ghi workload. Nếu ứng dụng có chức năng khác cần các quyền đó, phân tích nhu cầu riêng.

Với kiến trúc dùng HTTP DiscoveryClient và Discovery Server, nơi đọc Kubernetes API chuyển sang server. Caller vẫn cần quyền và đường mạng để gọi server, nhưng không mặc định cần quyền đọc Kubernetes API cho riêng luồng HTTP discovery này.

## 7. Cấu hình phạm vi discovery tại orders-api

Phần cấu hình sau được đóng gói trong ứng dụng caller hoặc cung cấp theo cơ chế cấu hình của môi trường:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: orders-api
  cloud:
    kubernetes:
      discovery:
        enabled: true
        all-namespaces: false
        namespaces:
          - shop-demo
        use-endpoint-slices: true
        primary-port-name: http
        include-not-ready-addresses: false
    loadbalancer:
      cache:
        enabled: false
~~~

Ý nghĩa của các lựa chọn:

| Lựa chọn | Mục đích |
| --- | --- |
| namespaces: [shop-demo] | Đặt phạm vi cần khám phá tường minh |
| all-namespaces: false | Giữ phạm vi theo danh sách được chọn |
| use-endpoint-slices: true | Chọn chế độ phù hợp với RBAC của bài |
| primary-port-name: http | Chỉ rõ cổng cần dùng khi phải chọn cổng |
| include-not-ready-addresses: false | Giữ các địa chỉ chưa ready ngoài danh sách thông thường |
| loadbalancer.cache.enabled: false | Tắt lớp cache bổ sung của LoadBalancer trong ví dụ quan sát |

Các thuộc tính discovery cần đối chiếu với tài liệu đúng phiên bản. Đặc biệt, primary-port-name thuộc cấu hình discovery ở đường tích hợp này, không phải thuộc tính portName dành cho chế độ SERVICE của Kubernetes LoadBalancer chuyên biệt. [Thuộc tính Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

Bài thực hành tắt cache bổ sung để giảm một lớp giữ danh sách khi quan sát thay đổi. Điều đó không tắt cache hoặc cơ chế đồng bộ trong DiscoveryClient, và không làm mỗi yêu cầu HTTP tự đọc toàn bộ Kubernetes API. Khi vận hành, cần quyết định cache dựa trên implementation discovery, độ trễ cập nhật và tải thực tế; tránh thêm nhiều lớp giữ cùng dữ liệu mà không hiểu thời hạn của chúng. [Cache của Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html).

Không dùng include-not-ready-addresses: true để làm danh sách “có dữ liệu” khi backend chưa sẵn sàng. Hãy xử lý nguyên nhân readiness trước khi cho phép lưu lượng nghiệp vụ đi tới các địa chỉ đó.

## 8. Tạo WebClient được LoadBalancer xử lý

### 8.1. Đăng ký builder

Các lớp sau thuộc dự án orders-api và nằm trong phạm vi component scan của ứng dụng Spring Boot.

~~~java
package com.example.orders;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    public WebClient.Builder serviceWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

@LoadBalanced đánh dấu builder để tích hợp chọn instance khi gọi bằng tên dịch vụ. LoadBalancer implementation phải có trên classpath. Annotation này không có nghĩa “tạo thêm một Kubernetes Service”. [WebClient với Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html#webclinet-loadbalancer-client).

Đây là cấu hình tối thiểu cho bài học. Trong ứng dụng cần observability hoặc các tùy chỉnh WebClient của Spring Boot, áp dụng các customizer tương ứng theo phiên bản; không mặc định rằng mọi tùy chỉnh của builder do Boot tạo sẽ tự xuất hiện trên một builder được tạo bằng lệnh static.

### 8.2. Gọi service ID

~~~java
package com.example.orders;

import java.time.Duration;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Component
public class InventoryGateway {

    private final WebClient webClient;

    public InventoryGateway(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.clone().build();
    }

    public Mono<String> findHandlingInstance() {
        return webClient.get()
                .uri("http://inventory-api/internal/identity")
                .retrieve()
                .bodyToMono(String.class)
                .timeout(Duration.ofSeconds(3));
    }
}
~~~

Host logic là inventory-api. LoadBalancer dùng service ID đó để lấy danh sách ứng viên và thay bằng đích được chọn. Mã nghiệp vụ không tự lấy phần tử đầu tiên từ DiscoveryClient.

Gateway giữ một WebClient đã xây dựng, thay vì tạo một HTTP client mới cho từng yêu cầu. Builder được clone trước khi dùng để tránh thay đổi cấu hình dùng chung nếu sau này gateway cần bổ sung tùy chọn.

timeout ba giây là giới hạn minh họa cho chuỗi phản ứng được đặt phía trên nó. Nó không thay thế việc cấu hình connect timeout, response timeout và ngân sách thời gian toàn hệ thống. [WebClient và HTTP connector](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html), [API Mono](https://docs.spring.io/projectreactor/reactor-core/docs/current/api/reactor/core/publisher/Mono.html).

Không gọi block() trong controller WebFlux để chờ kết quả. Giữ kiểu trả về Mono để framework quản lý việc đăng ký và xử lý chuỗi bất đồng bộ.

### 8.3. Endpoint kiểm tra ở caller

~~~java
package com.example.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class InventoryDemoController {

    private final InventoryGateway inventoryGateway;

    public InventoryDemoController(InventoryGateway inventoryGateway) {
        this.inventoryGateway = inventoryGateway;
    }

    @GetMapping("/demo/inventory-instance")
    public Mono<String> inventoryInstance() {
        return inventoryGateway.findHandlingInstance();
    }
}
~~~

Endpoint này giúp bài thực hành có một đường gọi hoàn chỉnh:

~~~text
Người kiểm tra
  -> orders-api /demo/inventory-instance
  -> WebClient có LoadBalancer
  -> inventory-api /internal/identity
  -> tên Pod xử lý
~~~

Trong ứng dụng thật, gateway sẽ gọi API nghiệp vụ và trả DTO phù hợp. Endpoint minh họa không phải một chức năng mặc định của Spring Cloud Kubernetes.

### 8.4. Tránh nhầm HTTP client thường với client có LoadBalancer

Lệnh sau tạo một client thường:

~~~java
WebClient directClient = WebClient.create();
~~~

Nếu dùng client này để gọi tên ngắn inventory-api trong cluster, yêu cầu có thể vẫn thành công nhờ DNS Kubernetes. Kết quả đó không kiểm chứng được @LoadBalanced đang hoạt động.

Ngược lại, dùng một client có LoadBalancer để gọi tên máy ngoài như api.partner.example có thể khiến tên đó bị hiểu thành service ID cần khám phá. Khi ứng dụng có cả gọi dịch vụ nội bộ và gọi URL ngoài, tạo và inject các client theo mục đích rõ ràng.

## 9. Gắn đúng ServiceAccount khi triển khai caller

Một Deployment tối thiểu cho orders-api:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: shop-demo
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
      serviceAccountName: orders-discovery-reader
      automountServiceAccountToken: true
      containers:
        - name: orders-api
          image: registry.example.invalid/learning/orders-api:REPLACE_WITH_BUILT_TAG
          ports:
            - name: http
              containerPort: 8080
~~~

Thay image placeholder bằng image đã chứa mã và cấu hình của caller. Deployment này tập trung vào danh tính và cổng; cấu hình probe, tài nguyên và các yêu cầu vận hành khác cần được bổ sung theo ứng dụng triển khai.

Nếu chỉ tạo RoleBinding nhưng Pod vẫn dùng ServiceAccount mặc định, quyền của orders-discovery-reader không tự được chuyển cho Pod.

Cần đồng thời có đường mạng:

- Từ caller tới Kubernetes API để discovery đồng bộ dữ liệu.
- Từ caller tới địa chỉ endpoint của inventory-api để gửi yêu cầu nghiệp vụ.

Được đọc Kubernetes API không có nghĩa NetworkPolicy sẽ cho phép gọi mọi Pod. Một lỗi Forbidden và một lỗi connection timeout cần được chẩn đoán ở hai lớp khác nhau.

## 10. Kiểm chứng từ dữ liệu nguồn đến yêu cầu thực

Các lệnh dưới đây dành cho người học chạy trong cluster thực hành được phép sử dụng. Chúng không phải kết quả đã được thực thi sẵn.

### 10.1. Kiểm tra backend và Service

~~~powershell
kubectl -n shop-demo rollout status deployment/inventory-api
kubectl -n shop-demo get pods -l app=inventory-api -o wide
kubectl -n shop-demo get service inventory-api
kubectl -n shop-demo get endpointslices -l kubernetes.io/service-name=inventory-api -o yaml
~~~

Đối chiếu địa chỉ endpoint, cổng 8080 và trạng thái ready. Đừng chỉ đếm replicas mong muốn trong Deployment: số Pod mong muốn không bảo đảm số endpoint sẵn sàng bằng nhau.

Nếu không có endpoint, kiểm tra selector của Service và label của Pod trước khi sửa thuật toán LoadBalancer.

### 10.2. Kiểm tra quyền theo danh tính caller

~~~powershell
$callerIdentity = "system:serviceaccount:shop-demo:orders-discovery-reader"

kubectl auth can-i list services -n shop-demo --as=$callerIdentity
kubectl auth can-i watch pods -n shop-demo --as=$callerIdentity
kubectl auth can-i list endpointslices.discovery.k8s.io -n shop-demo --as=$callerIdentity
kubectl auth can-i watch endpointslices.discovery.k8s.io -n shop-demo --as=$callerIdentity
kubectl auth can-i list secrets -n shop-demo --as=$callerIdentity
~~~

Các phép đọc đã cấp cần được phép; phép đọc Secret dự kiến bị từ chối nếu danh tính không nhận quyền bổ sung từ nơi khác. Người chạy --as phải có quyền impersonation tương ứng. Kiểm tra bằng tài khoản quản trị mà không chỉ định danh tính caller không chứng minh Pod có đủ quyền.

### 10.3. Quan sát ServiceInstance từ trong ứng dụng

Khi cần chẩn đoán, có thể dùng một đoạn kiểm tra nội bộ như sau ở ngữ cảnh được phép gọi DiscoveryClient:

~~~java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-api");

for (ServiceInstance instance : instances) {
    System.out.printf("service=%s host=%s port=%d secure=%s%n",
            instance.getServiceId(),
            instance.getHost(),
            instance.getPort(),
            instance.isSecure());
}
~~~

Đoạn mã cần các kiểu org.springframework.cloud.client.ServiceInstance, org.springframework.cloud.client.discovery.DiscoveryClient và java.util.List, với DiscoveryClient được inject vào thành phần kiểm tra.

Đây là phép kiểm tra blocking mang tính chẩn đoán; không chèn nó vào mỗi request trên event loop của WebFlux. Chỉ dùng trong phạm vi vận hành phù hợp, không mở một API công khai trả toàn bộ discovery metadata.

Kỳ vọng của ví dụ là có các địa chỉ instance của inventory-api và cổng endpoint phù hợp. Nếu danh sách trống hoặc cổng sai, sửa nguồn discovery trước khi quy lỗi cho lựa chọn round-robin.

### 10.4. Gửi nhiều yêu cầu qua caller

Mở cổng tạm tới Deployment caller:

~~~powershell
kubectl -n shop-demo port-forward deployment/orders-api 18080:8080
~~~

Trong terminal khác:

~~~powershell
$observedPods = 1..12 | ForEach-Object {
    Invoke-RestMethod -Uri "http://localhost:18080/demo/inventory-instance"
}
$observedPods
$observedPods | Group-Object | Select-Object Name, Count
~~~

Khi ba backend đều ổn định và cùng nằm trong danh sách ứng viên, kết quả có thể xuất hiện tên của cả ba Pod. Không dùng một vài yêu cầu để khẳng định tỷ lệ luôn chính xác một phần ba.

Kết quả cần phân tích cùng các yếu tố:

- Có bao nhiêu instance đủ điều kiện tại thời điểm gọi?
- Các yêu cầu có đi qua cùng một caller không?
- Có retry, bộ lọc, tùy biến thuật toán hoặc thay đổi danh sách không?
- Backend có trả định danh thật của Pod xử lý không?
- HTTP client trong gateway có đúng là client đã được tích hợp không?

Ở bài này, port-forward ghim việc kiểm tra vào một Pod caller. Nó giúp quan sát một luồng lựa chọn phía client; không dùng kết quả để suy ra toàn bộ hành vi của nhiều replica caller trong production.

## 11. Pod thay đổi, readiness và cache

Giả sử một Pod inventory-api không còn sẵn sàng. Chuỗi cập nhật có thể đi qua:

~~~text
Trạng thái ứng dụng / readiness
  -> trạng thái Pod và endpoint trong Kubernetes
  -> DiscoveryClient nhận hoặc đồng bộ thay đổi
  -> supplier / cache đang dùng
  -> danh sách ứng viên của lần chọn tiếp theo
~~~

Không coi cập nhật này là tức thời. Trong khoảng chuyển tiếp, caller có thể còn giữ một địa chỉ cũ hoặc một yêu cầu đang bay có thể thất bại.

Ở môi trường thực hành, có thể thay số replica có kiểm soát, rồi quan sát đồng thời EndpointSlice, dữ liệu discovery và kết quả HTTP. Ghi lại thời điểm từng lớp thay đổi thay vì chỉ nhìn lần gọi cuối cùng đã thành công.

Readiness giúp xác định endpoint phù hợp cho lưu lượng, nhưng không bảo đảm mọi nghiệp vụ đều thành công. Một Pod ready vẫn có thể trả lỗi do dữ liệu, phụ thuộc hoặc tải. Muốn xử lý các tình huống đó cần chính sách timeout, giới hạn tải và phục hồi phù hợp, không chỉ một bộ chọn instance.

Nếu dùng health-check supplier hoặc các lớp cache tùy biến, phải hiểu thứ tự áp dụng và khả năng giữ danh sách của từng lớp trước khi bổ sung. Với tích hợp cơ bản đã chạy đúng, không cần thêm cơ chế kiểm tra sức khỏe chủ động chỉ để làm ví dụ phức tạp hơn.

## 12. LoadBalancer không tự giải quyết timeout và retry

LoadBalancer trả lời câu hỏi “gửi lần gọi này tới ứng viên nào”. Nó không tự biết khi nào lặp lại một thao tác nghiệp vụ là an toàn.

Ví dụ:

- GET lấy thông tin kho có thể có chính sách retry giới hạn khi gặp lỗi tạm thời.
- POST trừ tồn kho có thể đã được backend thực hiện dù caller chưa nhận response.
- Gửi lại POST sang Pod khác có thể thực hiện thao tác lần hai nếu không có cơ chế idempotency.

Không thêm retry không giới hạn để che một danh sách instance sai. Khi bật retry ở một hoặc nhiều tầng, cần xác định số lần thử, điều kiện thử lại, đích của lần thử và ngân sách thời gian tổng. Không mặc định mọi lần retry đều chọn một Pod khác.

Với chuỗi phản ứng, vị trí timeout và retry trong pipeline ảnh hưởng thời gian chờ. Timeout cho từng lần thử và giới hạn cho toàn thao tác là hai quyết định khác nhau. Cần đối chiếu hành vi của thư viện và cấu hình thực tế.

Tương tự, circuit breaker, giới hạn đồng thời và xử lý lỗi là các khả năng riêng. Sự có mặt của Spring Cloud LoadBalancer không có nghĩa chúng đã được bật cho mọi yêu cầu.

## 13. Chẩn đoán theo lớp

| Triệu chứng | Lớp cần kiểm tra trước | Dữ liệu cần đối chiếu |
| --- | --- | --- |
| Không có ứng viên cho inventory-api | Discovery | Service tồn tại, namespace, quyền, endpoint sẵn sàng |
| Forbidden từ Kubernetes API | Danh tính và RBAC | ServiceAccount thực tế, verb, resource, API group |
| Danh sách có instance nhưng connection refused | Cổng hoặc ứng dụng đích | Endpoint port, cổng lắng nghe, trạng thái tiến trình |
| Connection timeout tới IP Pod | Mạng | Định tuyến, NetworkPolicy, địa chỉ caller có thể truy cập |
| Lỗi TLS sau khi chọn instance | Giao thức và xác thực TLS | secure, scheme, chứng chỉ và tên máy được kiểm tra |
| Tên ngắn gọi được nhưng chưa chứng minh cân bằng phía ứng dụng | Tích hợp HTTP client | Bean được inject, bộ lọc LoadBalancer, instance đã chọn |
| Chỉ thấy một Pod xử lý | Danh sách và chính sách chọn | Số endpoint ready, thuật toán, nhiều tầng định tuyến |
| Còn gọi endpoint cũ sau rollout | Đồng bộ và cache | Thời điểm thay đổi nguồn, cache discovery và LoadBalancer |
| Service trùng tên ở nhiều namespace | Phạm vi discovery | Danh sách namespace và quy ước service ID |
| Đã đổi ConfigMap nhưng hành vi chưa đổi | Cấu hình hiệu lực | Cách ứng dụng nạp lại cấu hình và vòng đời bean |

Với lỗi phân giải tên, cần quan sát hostname thực sự đang được phân giải và instance đã chọn. Thiếu bộ lọc LoadBalancer là một khả năng, nhưng không phải nguyên nhân duy nhất của mọi lỗi DNS.

Không bật all-namespaces để chữa tên dịch vụ sai. Cấu hình rộng hơn có thể đưa thêm các Service trùng tên hoặc không thuộc phạm vi nghiệp vụ vào danh sách tìm kiếm.

Không ghi toàn bộ metadata vào log để chẩn đoán một cổng sai. Thông tin tối thiểu thường là service ID, host, port, trạng thái yêu cầu và định danh đối chiếu trong phạm vi vận hành được phép.

## 14. Khi nào tích hợp này hoàn thành?

Tích hợp đạt mục tiêu khi bạn có thể lần theo một yêu cầu từ đầu đến cuối:

1. Mã nghiệp vụ gọi inventory-api bằng service ID.
2. WebClient thực sự có hỗ trợ Spring Cloud LoadBalancer.
3. Supplier lấy dữ liệu từ Kubernetes DiscoveryClient đã chọn.
4. Discovery chỉ đọc namespace và tài nguyên được cấp quyền.
5. ServiceInstance trỏ tới endpoint và cổng nghiệp vụ đúng.
6. Caller kết nối được tới endpoint đó.
7. Kết quả kiểm tra cho thấy các instance đủ điều kiện có thể nhận yêu cầu.
8. Thay đổi Pod được phản ánh theo quá trình đồng bộ đã quan sát.
9. Timeout và xử lý lỗi phù hợp với loại thao tác được gọi.

ConfigMap và Secret có thể cung cấp một phần cấu hình của ứng dụng, còn Configuration Watcher có thể tham gia luồng cập nhật cấu hình được thiết kế riêng. Chúng không tự thay thế discovery, chọn instance hay chính sách an toàn khi thử lại yêu cầu.

Giá trị của tích hợp nằm ở một luồng có thể giải thích và kiểm chứng: service ID đi vào HTTP client, danh sách instance đi vào LoadBalancer và một địa chỉ hợp lệ được chọn cho lần gọi. Chỉ giữ các tính năng bổ sung khi chúng phục vụ một nhu cầu cụ thể của ứng dụng triển khai.
