# Ranh giới với Service Discovery, Kubernetes và Service Broker

## 1. Bối cảnh và mục tiêu

Trong module **Spring Cloud Provider Integration**, ứng dụng Spring Boot kết nối các dịch vụ managed của AWS, Azure và Google Cloud qua thư viện Spring Cloud, SDK và connector tương ứng. Khi một hệ thống được tách thành nhiều service, ứng dụng phải giải quyết ba câu hỏi khác nhau:

- **Service Discovery:** service cần gọi đang ở đâu và endpoint nào đang khả dụng?
- **Service Binding:** ứng dụng nhận endpoint, resource metadata và thông tin xác thực để kết nối với một service instance như thế nào?
- **Service Broker:** ai provision, bind, unbind, update hoặc deprovision một managed service theo yêu cầu của platform?

Các câu hỏi này liên quan nhưng thuộc những ranh giới kiến trúc khác nhau. Discovery chủ yếu hỗ trợ tìm và định tuyến tới service đang chạy. Binding cung cấp dữ liệu kết nối cho workload. Broker quản lý vòng đời tài nguyên qua control plane. Kubernetes bổ sung các primitive như Service, DNS, EndpointSlice, Ingress/Gateway và API discovery. Spring Cloud cung cấp abstraction cho discovery client và load balancing, nhưng không thay thế Kubernetes networking hoặc service broker API.

Bài học giúp người học phân biệt rõ các thành phần, chọn đúng cơ chế theo runtime/platform, hiểu cách Spring Cloud DiscoveryClient và Spring Cloud Kubernetes hoạt động, đồng thời nhận biết dịch vụ tương đương hoặc gần tương đương trên AWS, Azure và Google Cloud.

Sau bài học, bạn có thể:

1. Phân biệt service discovery, service binding, service broker và service mesh.
2. Mô tả luồng discovery và request routing trong ứng dụng Spring Boot.
3. Giải thích Kubernetes Service, DNS, EndpointSlice và kube-proxy/data plane.
4. Dùng Spring Cloud DiscoveryClient và Spring Cloud LoadBalancer khi phù hợp.
5. Chọn Kubernetes native discovery, Eureka, Consul hoặc DNS-based discovery.
6. Phân biệt Open Service Broker API với Kubernetes Service Binding Specification.
7. Đối chiếu AWS Cloud Map, Azure discovery options và Google Cloud Service Directory/DNS.
8. Xác định ranh giới control plane, data plane, identity và network policy.
9. Kiểm thử discovery, failover, endpoint update và broker lifecycle.
10. Thiết kế observability, security và runbook cho production.

> **Phạm vi:** Service Discovery tìm endpoint của service; Service Binding cung cấp thông tin kết nối; Service Broker quản lý vòng đời service instance/binding. Một nền tảng có thể tích hợp nhiều cơ chế, nhưng không nên coi chúng là một API hoặc một thành phần duy nhất.

## 2. Bốn khái niệm cần tách biệt

### 2.1. Service Discovery: tìm địa chỉ của service

Giả sử Reservation Service cần gọi Pricing Service. Khi chạy local, địa chỉ có thể là localhost và port cố định. Trong production, Pricing Service có nhiều replica, IP thay đổi khi rollout hoặc scale. Hard-code một IP vào application config khiến client nhanh chóng lỗi thời.

Service discovery cung cấp cách tìm endpoint hiện tại bằng logical service name. Client hoặc load balancer dùng registry, DNS hoặc platform API để lấy một hay nhiều instance:

~~~mermaid
flowchart LR
    A["Reservation Service"] --> B["Discovery client / DNS"]
    B --> C["Registry or platform endpoints"]
    C --> D["Pricing instance A"]
    C --> E["Pricing instance B"]
    C --> F["Pricing instance C"]
    A --> G["Load balancer"]
    G --> D
    G --> E
    G --> F
~~~

Discovery trả lời câu hỏi định tuyến: gọi service nào, endpoint nào, endpoint còn healthy hay không. Nó không nhất thiết cung cấp credential hoặc tạo database/queue.

### 2.2. Service Binding: cung cấp thông tin kết nối

Service binding gắn một workload với một service instance. Binding data có thể chứa host, port, database name, username, password, URI, certificate, bucket, queue URL hoặc resource identifier. Nền tảng có thể mount file, inject environment variable hoặc cung cấp metadata theo contract như Kubernetes Service Binding Specification hay Cloud Foundry VCAP_SERVICES.

Ví dụ binding cho database giúp Spring Boot tạo datasource. Binding không nhất thiết tìm instance động cho mỗi request; nhiều binding được đọc khi startup và dùng trong suốt vòng đời process.

Với cloud API sử dụng IAM/Managed Identity/Workload Identity, binding thường chỉ cần resource name, project/Region/endpoint. SDK lấy token từ workload identity provider. Không cần nhúng access key vào binding nếu runtime identity đã có quyền.

### 2.3. Service Broker: quản lý vòng đời tài nguyên

Service broker là thành phần control plane nhận yêu cầu từ platform để thực hiện thao tác với dịch vụ:

- Provision một service instance.
- Bind application/workload với instance và cấp binding data/credential.
- Unbind và thu hồi binding credential.
- Update plan/parameters nếu broker hỗ trợ.
- Deprovision instance khi platform yêu cầu.

Ví dụ một developer yêu cầu PostgreSQL plan `standard`. Platform gọi broker để tạo database, sau đó bind database vào application. Broker có thể tạo user riêng, trả endpoint/credential và thu hồi user khi unbind.

Service broker không phải runtime discovery registry. Broker có thể tạo service và cấp endpoint; ứng dụng sau đó sử dụng endpoint hoặc discovery mechanism phù hợp.

### 2.4. Service Mesh: quản lý giao tiếp giữa service

Service mesh như Istio, Linkerd hoặc Consul service mesh cung cấp một lớp hạ tầng cho traffic giữa service, thường gồm mTLS, identity, policy, telemetry, retry và traffic shifting. Mesh có thể dùng Kubernetes service discovery hoặc registry riêng làm nguồn endpoint.

Mesh không đồng nghĩa service discovery. Discovery cung cấp danh sách/địa chỉ endpoint; mesh điều khiển cách traffic được bảo vệ và chuyển tiếp. Không cần triển khai mesh chỉ để phân giải DNS tên Service trong Kubernetes.

### 2.5. Bảng phân biệt

| Thành phần | Câu hỏi chính | Input | Output |
| --- | --- | --- | --- |
| Service Discovery | Service đang ở đâu? | Logical service name | Endpoint/instance list |
| Service Binding | Workload kết nối service instance bằng gì? | Binding resource/metadata | Connection properties/credentials |
| Service Broker | Ai tạo và quản lý service instance? | Provision/bind/unbind request | Resource và binding lifecycle |
| Service Mesh | Traffic giữa service được bảo vệ/điều khiển thế nào? | Service identity, policy, route | mTLS, routing, telemetry |
| Kubernetes Service | Client gọi một nhóm pod ổn định bằng cách nào? | Selector/EndpointSlice | Virtual IP và DNS name |
| Ingress/Gateway | Traffic từ ngoài cluster vào thế nào? | Host/path/route | Entry point và routing |

## 3. Discovery trong kiến trúc Spring Cloud

### 3.1. DiscoveryClient abstraction

Spring Cloud Commons định nghĩa abstraction `DiscoveryClient` để application hoặc framework hỏi các service instance theo service ID. Các implementation có thể dựa trên Eureka, Consul, Zookeeper, Kubernetes hoặc discovery provider khác.

Ý tưởng sử dụng:

~~~java
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class PricingEndpointLookup {

    private final DiscoveryClient discoveryClient;

    public PricingEndpointLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> instances() {
        return discoveryClient.getInstances("pricing-service");
    }
}
~~~

`getInstances` trả danh sách instance mà implementation biết. Code trên chỉ minh họa lookup; không nên tự chọn instance đầu tiên và gửi request trực tiếp trong ứng dụng production nếu cần load balancing, retry, health-aware routing hoặc circuit breaker.

### 3.2. Spring Cloud LoadBalancer

Spring Cloud LoadBalancer chọn instance cho request dựa trên service ID. Với Spring `RestClient`, `RestTemplate` hoặc `WebClient`, có thể tích hợp load-balancing interceptor/filter theo phiên bản Spring Cloud.

Ví dụ khai báo HTTP client có thể dùng logical service name:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Một client sử dụng service ID thay cho hostname cụ thể:

~~~java
@Service
class PricingClient {

    private final RestClient restClient;

    PricingClient(RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    PricingQuote quote(String productId) {
        return restClient.get()
                .uri("http://pricing-service/api/quotes/{id}", productId)
                .retrieve()
                .body(PricingQuote.class);
    }
}
~~~

Trong ví dụ, `pricing-service` được resolver/load balancer xử lý nếu builder được cấu hình đúng và có DiscoveryClient implementation. Không dùng builder load-balanced cho mọi external URL; chỉ dùng cho logical service ID thuộc discovery namespace.

### 3.3. Discovery không đồng nghĩa health check

Registry có thể lưu instance nhưng instance đã chết hoặc không còn nhận request. Nguồn endpoint và health signal cần được đồng bộ. Các hệ thống có thể dùng:

- Kubernetes readiness probe để quyết định pod có nằm trong Service endpoint hay không.
- Eureka heartbeat/lease và health status.
- Consul health check.
- Cloud Map health check hoặc integration với orchestrator.
- Load balancer health check ở tầng network/application.

Liveness và readiness có mục đích khác nhau. Liveness xác định process cần restart; readiness xác định instance có nên nhận traffic. Không dùng liveness probe phụ thuộc database chập chờn nếu điều đó khiến toàn bộ pod restart liên tục.

### 3.4. Client-side và server-side load balancing

| Mô hình | Cách hoạt động | Ví dụ |
| --- | --- | --- |
| Client-side | Client lấy instance list rồi chọn endpoint | Spring Cloud LoadBalancer + Eureka/Consul |
| Server-side | Client gọi một stable address; proxy/load balancer chọn backend | Kubernetes Service ClusterIP, cloud load balancer |
| DNS-based | DNS trả một hoặc nhiều địa chỉ; client/resolver chọn | Kubernetes Service DNS, Route 53 private DNS |
| Mesh/proxy-based | Sidecar/node proxy chọn upstream theo policy | Istio/Envoy, Linkerd |

Kubernetes Service thường dùng server-side virtual IP/data plane: client gọi DNS name ổn định, traffic được chuyển tới endpoint phù hợp. Ứng dụng không cần truy vấn Kubernetes API mỗi request. Với Spring Cloud Kubernetes DiscoveryClient, application có thể lấy instance metadata và dùng client-side load balancing; đây là lựa chọn khác với gọi trực tiếp Service DNS.

### 3.5. Khi nào cần DiscoveryClient?

Dùng abstraction discovery khi ứng dụng thực sự cần biết danh sách instance hoặc chọn endpoint động ở application layer. Nếu chỉ cần gọi một Kubernetes Service qua DNS, HTTP client bình thường với DNS name thường đơn giản hơn. Nếu cần traffic policy, mTLS và telemetry xuyên service, xem xét mesh hoặc gateway.

Không thêm Eureka/Consul vào cluster chỉ vì muốn dùng `@LoadBalanced`. Hãy xác định nền tảng hiện tại đã cung cấp discovery nào và client cần semantics nào.

## 4. Kubernetes native service discovery

### 4.1. Service và Pod IP

Pod IP có thể thay đổi khi pod được tạo lại, reschedule hoặc scale. Kubernetes Service tạo một logical endpoint ổn định cho một nhóm pod được chọn bằng label selector.

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: pricing-service
  namespace: commerce
spec:
  selector:
    app: pricing
  ports:
    - name: http
      port: 80
      targetPort: 8080
  type: ClusterIP
~~~

Pod có label `app: pricing` và port container `8080` sẽ trở thành backend endpoint khi đủ điều kiện. Service `ClusterIP` cung cấp địa chỉ ổn định bên trong cluster; kube-proxy hoặc data plane tương đương thực hiện chuyển tiếp traffic.

### 4.2. DNS name trong cluster

CoreDNS cung cấp DNS record cho Service. Trong cùng namespace, client thường có thể gọi `http://pricing-service`; namespace khác có thể dùng `pricing-service.commerce` hoặc FQDN `pricing-service.commerce.svc.cluster.local`.

DNS name ổn định hơn Pod IP. Tuy nhiên, DNS caching và client connection pooling có thể ảnh hưởng thời gian nhận endpoint mới. Với headless Service, DNS có thể trả các Pod IP thay vì ClusterIP; client có thể cần xử lý nhiều địa chỉ và thay đổi endpoint.

### 4.3. EndpointSlice

EndpointSlice lưu tập hợp endpoint thuộc Service và hỗ trợ scale tốt hơn so với một Endpoints object lớn. Controller cập nhật EndpointSlice khi Pod readiness, selector hoặc topology thay đổi. Data plane sử dụng endpoint information để route traffic.

Không sửa EndpointSlice thủ công cho Service selector-managed trừ khi có use case đặc biệt. Để chẩn đoán:

~~~bash
kubectl get service pricing-service -n commerce
kubectl get endpointslice -n commerce -l kubernetes.io/service-name=pricing-service
kubectl get pods -n commerce -l app=pricing -o wide
~~~

Nếu Service không có endpoint, kiểm tra selector/label, readiness probe, port mapping và namespace.

### 4.4. Readiness và traffic eligibility

Pod đang Running chưa chắc nhận traffic. Readiness probe phải thành công để endpoint được coi là ready theo cấu hình. Ví dụ:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 3
~~~

Spring Boot Actuator có thể cung cấp readiness/liveness health group. Chỉ expose health endpoint cần thiết. Readiness check nên kiểm tra khả năng nhận traffic; không nhất thiết fail chỉ vì một dependency optional tạm unavailable.

### 4.5. Headless Service và StatefulSet

Headless Service (`clusterIP: None`) không cấp virtual IP thông thường. DNS trả record theo Pod endpoint, phù hợp StatefulSet hoặc hệ thống cần định danh từng replica. StatefulSet có ordinal/network identity ổn định, ví dụ `database-0.database-headless.namespace.svc.cluster.local`.

Không dùng headless Service như thay thế mặc định cho ClusterIP. Client cần hiểu DNS multi-record, endpoint lifecycle và readiness semantics.

### 4.6. Ingress, Gateway và traffic east-west

Kubernetes Service phục vụ traffic nội bộ. Ingress/Gateway API xử lý traffic đi vào cluster hoặc route giữa gateway và backend. Chúng không thay thế Service DNS cho mọi giao tiếp nội bộ. NetworkPolicy quyết định pod nào được phép giao tiếp; DNS resolve thành công không có nghĩa kết nối được phép.
## 5. Spring Cloud Kubernetes và Kubernetes DiscoveryClient

### 5.1. Khi nào cần Spring Cloud Kubernetes?

Spring Cloud Kubernetes tích hợp Spring application với Kubernetes API. Tùy starter/implementation, nó có thể cung cấp DiscoveryClient, ConfigMap/Secret integration, load-balancing integration và các tính năng khác.

Hai cách kết nối phổ biến:

- **DNS qua Kubernetes Service:** application gọi hostname của Service. Kubernetes data plane xử lý endpoint routing; không cần application đọc Kubernetes API.
- **DiscoveryClient qua Kubernetes API:** application lấy service/endpoint metadata từ API rồi Spring Cloud LoadBalancer chọn instance.

Chọn DNS khi cần gọi service nội bộ thông thường. Chọn DiscoveryClient khi application cần instance metadata, custom routing hoặc client-side load balancing. Tránh bật cả hai cơ chế cho cùng một luồng nếu không có lý do rõ ràng.

### 5.2. Dependency và version alignment

Spring Cloud Kubernetes có các starter dựa trên Kubernetes Java Client hoặc Fabric8. Ví dụ dependency cho discovery với Kubernetes Client có thể dùng:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-client-discovery</artifactId>
</dependency>
~~~

Artifact cụ thể và tên starter có thể thay đổi theo release train. Chọn một client implementation phù hợp (Kubernetes Client hoặc Fabric8), quản lý version qua Spring Cloud BOM và kiểm tra ma trận tương thích với Spring Boot. Không thêm đồng thời nhiều implementation discovery nếu không chủ đích.

### 5.3. Service ID và namespace

Discovery client thường ánh xạ service name trong Kubernetes thành service ID. Một service có thể được tìm theo namespace hiện tại hoặc nhiều namespace tùy cấu hình. Cross-namespace discovery cần quyền API và policy rõ ràng.

Ví dụ, service `pricing-service` trong namespace `commerce` có thể được tìm từ client theo logical ID, nhưng việc chọn namespace, port và protocol phụ thuộc implementation. Đừng suy ra port chỉ từ container port; Kubernetes Service có `port` và `targetPort` riêng.

### 5.4. RBAC cho DiscoveryClient

Nếu discovery implementation truy vấn Kubernetes API, ServiceAccount của pod cần quyền đọc resource liên quan. Ví dụ policy tối thiểu theo use case có thể gồm `get`, `list`, `watch` trên Services, Endpoints/EndpointSlices và có thể Pods:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: service-discovery-reader
  namespace: commerce
rules:
  - apiGroups: [""]
    resources: ["services", "endpoints", "pods"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
~~~

RoleBinding chỉ gắn quyền cho ServiceAccount của workload cần discovery. Nếu đọc nhiều namespace, cần RoleBinding ở từng namespace hoặc ClusterRole/ClusterRoleBinding được review cẩn thận. Không cấp `cluster-admin` để giải quyết lỗi discovery.

Nếu application chỉ gọi Service DNS, nó thường không cần quyền đọc Kubernetes API. Đây là lợi ích vận hành và security quan trọng của native DNS approach.

### 5.5. Discovery lifecycle và caching

Kubernetes API watch/cache có thể giúp cập nhật endpoint mà không polling liên tục. Tuy nhiên, API connectivity, watch reconnect, cache staleness và permission failure vẫn cần xử lý. Xác định:

- Discovery client lấy service/endpoint từ namespace nào?
- Port nào được chọn khi Service có nhiều port?
- Endpoint not-ready có được lọc không?
- Cache update và watch reconnect behavior là gì?
- Khi API server unavailable, client dùng cache hay fail?
- LoadBalancer chọn instance và retry thế nào?

Không gọi API server cho mỗi request. Dùng client/cache implementation có lifecycle rõ và giới hạn scope.

### 5.6. Spring Cloud Kubernetes không thay thế NetworkPolicy

Discovery chỉ cho biết endpoint. NetworkPolicy, security group, service mesh policy và cloud firewall quyết định traffic có được phép đi qua hay không. Nếu service được phát hiện nhưng connection timeout, kiểm tra DNS, route, NetworkPolicy, port, TLS và readiness riêng biệt.

## 6. Eureka, Consul và DNS-based discovery

### 6.1. Eureka

Eureka là registry trong hệ sinh thái Spring Cloud Netflix. Service instance đăng ký với Eureka Server và gửi heartbeat; client lấy registry để chọn instance. Đây là mô hình application-level registry, thường hữu ích cho hệ thống Spring Cloud đã dùng Eureka hoặc môi trường không có discovery primitive chung.

Các dependency thường dùng:

~~~xml
<!-- Eureka Server -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-server</artifactId>
</dependency>

<!-- Eureka Client -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
</dependency>
~~~

Server được bật bằng `@EnableEurekaServer`; client dùng `spring.application.name` và cấu hình server URL. Cần bảo vệ registry, bật TLS/authentication phù hợp, kiểm soát self-preservation và heartbeat/lease. Eureka registry là thêm một dependency runtime; không triển khai nếu Kubernetes Service DNS đã đáp ứng nhu cầu.

### 6.2. Consul

Consul cung cấp service registry, health checks và các tính năng khác như KV/service mesh tùy kiến trúc. Spring Cloud Consul Discovery cho phép service đăng ký và client truy vấn Consul.

Dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-consul-discovery</artifactId>
</dependency>
~~~

Consul phù hợp với môi trường hybrid/multi-platform khi cần registry chung cho VM, Kubernetes và service ngoài cluster. Phải thiết kế Consul cluster quorum, ACL token, gossip encryption, TLS, health check và network connectivity giữa các environment.

Consul health status không tự chứng minh toàn bộ request path hoạt động. Health check cần phản ánh readiness và được bảo vệ khỏi credential leakage.

### 6.3. DNS-based discovery

DNS là lựa chọn đơn giản khi platform cung cấp tên service ổn định. Kubernetes Service DNS, Route 53 private hosted zone, Azure Private DNS hoặc Cloud DNS có thể phân giải hostname nội bộ.

DNS discovery phụ thuộc TTL, caching ở JVM/OS/resolver, connection pool và load balancing ở tầng sau. Một DNS record trả nhiều IP không đảm bảo client phân phối request đồng đều; cần hiểu resolver behavior và connection reuse.

### 6.4. Chọn registry nào?

| Runtime/nhu cầu | Lựa chọn nên xem xét | Lý do |
| --- | --- | --- |
| Kubernetes service nội bộ | Kubernetes Service DNS | Native, ít thành phần, routing qua cluster data plane |
| Spring app cần endpoint metadata từ Kubernetes API | Spring Cloud Kubernetes DiscoveryClient | Tích hợp discovery và LoadBalancer |
| Spring Cloud legacy hoặc platform registry hiện hữu | Eureka | Application-level registry đã có trong hệ thống |
| Hybrid VM + Kubernetes + nhiều network zone | Consul | Registry chung và health checks xuyên môi trường |
| External/private endpoint ổn định | DNS/private DNS | Đơn giản, dùng được nhiều ngôn ngữ |
| Traffic policy/mTLS/telemetry nâng cao | Service mesh hoặc gateway | Quản lý data plane và policy |

Không có registry tốt nhất cho mọi kiến trúc. Cần xét topology, failure domain, protocol, identity, latency, operational ownership và khả năng vận hành cluster/registry.

## 7. Service Broker và Open Service Broker API

### 7.1. Broker thuộc control plane

Open Service Broker API (OSB API) định nghĩa contract HTTP giữa platform và service broker để quản lý service offering, plan, instance và binding. Nhiều nền tảng Cloud Foundry sử dụng broker tương thích OSB API để cung cấp managed database, cache, messaging hoặc dịch vụ bên ngoài.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant User as Developer / Operator
    participant Platform as Platform control plane
    participant Broker as Service Broker
    participant Managed as Managed Service
    participant App as Application

    User->>Platform: Request service instance
    Platform->>Broker: Catalog / provision
    Broker->>Managed: Create resource
    Managed-->>Broker: Resource details
    Broker-->>Platform: Provision result
    User->>Platform: Bind application
    Platform->>Broker: Bind instance
    Broker->>Managed: Create scoped credential
    Broker-->>Platform: Binding data
    Platform->>App: Inject binding data
    App->>Managed: Connect at runtime
~~~

Broker thực hiện lifecycle operation qua API. Application thường không gọi OSB API trong mỗi request nghiệp vụ. Platform chịu trách nhiệm gọi broker và phân phối binding data tới workload.

### 7.2. Các operation thường gặp

| Operation | Ý nghĩa |
| --- | --- |
| Catalog | Liệt kê service offering và plan broker hỗ trợ |
| Provision | Tạo service instance |
| Update | Thay đổi plan/parameters nếu broker hỗ trợ |
| Bind | Tạo binding credentials/metadata cho consumer |
| Unbind | Thu hồi hoặc xóa binding |
| Deprovision | Xóa service instance |
| Last operation | Poll trạng thái operation bất đồng bộ |

Provision/bind có thể là asynchronous operation. Platform phải poll trạng thái theo contract và xử lý retry/idempotency. Broker cần xử lý request lặp an toàn, vì timeout ở platform không chứng minh broker chưa tạo tài nguyên.

### 7.3. OSB API không phải Kubernetes Service Binding Specification

Hai specification giải quyết hai lớp khác nhau:

- **OSB API:** platform gọi broker để provision, bind, unbind và deprovision.
- **Kubernetes Service Binding Specification:** chuẩn hóa cách binding data được biểu diễn và cung cấp cho workload, thường qua directory/filesystem.
- **Spring Cloud Bindings:** thư viện phía ứng dụng đọc các format binding được hỗ trợ và ánh xạ vào Spring Environment.

Có thể kết hợp cả ba: platform gọi OSB broker tạo database và binding credentials; platform/operator đưa binding data vào pod theo Service Binding Specification; Spring Cloud Bindings đọc data và tạo datasource properties.

Không phải mọi Kubernetes Service Binding Operator đều gọi OSB API; operator có thể lấy data từ Kubernetes resource/Secret hoặc provider-specific resource. Không suy ra OSB API chỉ vì pod có binding directory.

### 7.4. Broker lifecycle và idempotency

Broker cần xử lý trường hợp platform gửi lại provision/bind sau timeout. Dùng instance ID/binding ID ổn định theo contract, lưu trạng thái operation và bảo đảm thao tác lặp không tạo database/user trùng. Unbind cần thu hồi credential đúng binding; deprovision chỉ xóa resource sau khi platform xác nhận lifecycle phù hợp.

Với thao tác destructive, broker phải phân biệt unbind với deprovision. Xóa một binding không đồng nghĩa xóa database chứa dữ liệu. Backup, retention và deletion policy phải theo plan/service contract.

### 7.5. Security của broker API

Broker API có thể tạo/xóa database, user, queue hoặc cloud resource; đây là control plane đặc quyền cao. Bảo vệ bằng TLS, authentication giữa platform và broker, authorization theo operation, audit và network isolation. Không expose broker endpoint ra public internet nếu không cần.

Broker credential dùng để provision resource thường có quyền cao hơn workload runtime identity. Tách hai identity:
- **Broker/platform identity:** provision, bind, unbind, rotate và deprovision resource.
- **Application workload identity/credential:** chỉ truy cập resource đã được bind.
## 8. Service discovery trên AWS, Azure và Google Cloud

### 8.1. AWS Cloud Map và Route 53

AWS Cloud Map là dịch vụ registry để đăng ký và khám phá resource/service instance. Một namespace có thể hỗ trợ discovery qua API hoặc DNS. ECS Service Discovery có thể tích hợp Cloud Map để đăng ký task endpoint khi task được tạo và deregister khi task dừng. Route 53 private hosted zone cung cấp DNS discovery trong VPC.

Các hướng lựa chọn:

- **ECS service discovery:** ECS đăng ký task vào Cloud Map; client có thể dùng DNS hoặc Cloud Map API.
- **EKS:** ưu tiên Kubernetes Service/DNS cho service trong cluster; Cloud Map có thể hữu ích cho discovery ngoài cluster hoặc tích hợp hệ thống hybrid khi được cấu hình.
- **EC2/VM:** có thể đăng ký instance bằng Cloud Map API hoặc dùng Route 53 private DNS.
- **Application client:** có thể dùng AWS SDK Cloud Map `DiscoverInstances` hoặc DNS resolver. Không mặc định Spring Cloud có Cloud Map DiscoveryClient implementation tương thích; cần kiểm tra connector hoặc viết adapter nếu muốn dùng Spring abstraction.

Cloud Map registry không cấp quyền gọi resource. AWS IAM role/policy, VPC routing, security group và TLS vẫn quyết định request có thành công hay không. Nếu dùng DNS, cần tính TTL và cache; nếu dùng API, cần quản lý cache, API throttling và health filter.

### 8.2. Azure AKS, Container Apps và Private DNS

Azure không có một registry duy nhất áp dụng cho mọi compute/service như một abstraction chung. Cách discovery phụ thuộc runtime:

- **AKS:** Kubernetes Service, CoreDNS, EndpointSlice và Ingress/Gateway là lựa chọn native trong cluster.
- **Azure Container Apps:** environment có internal ingress/service discovery cho app-to-app communication; dùng app name/internal FQDN theo cấu hình environment.
- **Azure Private DNS:** phân giải private endpoint và hostname nội bộ trong virtual network.
- **Service Fabric:** có Naming Service và service discovery riêng cho workload Service Fabric.
- **Hybrid:** Consul hoặc registry riêng có thể phù hợp nếu cần discovery xuyên VM, AKS và datacenter.

Với Container Apps, xác minh internal/external ingress, environment boundary và DNS suffix theo region/configuration. Không dùng public endpoint cho east-west traffic nếu internal ingress đáp ứng nhu cầu.

Spring Cloud application có thể gọi internal FQDN qua HTTP client bình thường. Chỉ cần DiscoveryClient nếu cần instance list hoặc integration với registry. Managed Identity xác thực tới Azure API/service; DNS hoặc internal endpoint không cấp quyền data-plane.

### 8.3. Google Cloud GKE, Cloud DNS và Service Directory

Các lựa chọn thường gặp:

- **GKE:** Kubernetes Service/DNS và EndpointSlice cho discovery trong cluster.
- **Cloud DNS private zones:** phân giải hostname trong VPC hoặc hybrid network.
- **Service Directory:** registry managed cho service endpoint/metadata, hữu ích với service cần discovery qua nhiều môi trường/network.
- **Cloud Run:** service có URL ổn định; service-to-service invocation cần IAM authentication và có thể dùng internal ingress/network path theo thiết kế.
- **Hybrid:** Service Directory hoặc Consul có thể kết hợp với workload Kubernetes/VM khi cần registry chung.

Service Directory API/Cloud DNS không tự động tạo Spring Cloud DiscoveryClient. Dùng Google Cloud client hoặc custom adapter nếu application cần query registry ở runtime. Nếu Cloud Run service URL đã ổn định, HTTP client có thể gọi trực tiếp; thêm registry chỉ khi có yêu cầu metadata/routing động.

Cloud Run service URL không phải authorization. Caller cần identity có quyền invoke và gửi ID token phù hợp. Với GKE, Workload Identity cấp credential cho workload; Kubernetes Service DNS chỉ cung cấp địa chỉ.

### 8.4. So sánh lựa chọn discovery

| Môi trường | Discovery native thường gặp | Khi cần registry bổ sung |
| --- | --- | --- |
| AWS ECS | ECS Service Discovery + Cloud Map/Route 53 | Hybrid, custom attributes hoặc registry đa nền tảng |
| AWS EKS | Kubernetes Service/DNS | Discovery xuyên cluster/VPC hoặc ngoài Kubernetes |
| Azure AKS | Kubernetes Service/DNS | Hybrid hoặc nhiều cluster/network zone |
| Azure Container Apps | Internal ingress và app DNS | Multi-environment/hybrid registry |
| GKE | Kubernetes Service/DNS | Discovery xuyên cluster/VPC hoặc external workload |
| Cloud Run | Service URL và internal routing | Registry động theo service metadata/endpoint |
| VM/multi-cloud | Private DNS, Cloud Map, Service Directory, Consul | Cần health-aware registry thống nhất |

Không có Spring Cloud starter chung tự động hỗ trợ mọi native discovery service. Kiểm tra connector có sẵn, protocol/API và maintenance status trước khi quyết định tự viết DiscoveryClient adapter.

## 9. Service Broker và resource provisioning trên cloud

### 9.1. Không phải mọi cloud service catalog đều là OSB broker

AWS, Azure và Google Cloud cung cấp nhiều cách provision managed resource, nhưng không phải cách nào cũng triển khai Open Service Broker API.

| Nền tảng/cơ chế | Vai trò | Có tự động là OSB API không? |
| --- | --- | --- |
| Cloud Foundry service broker | Provision/bind managed service cho platform | Thường có thể triển khai OSB API |
| Kubernetes operator/controller | Reconcile resource từ Kubernetes custom resource | Không, trừ khi operator có adapter OSB riêng |
| AWS Service Catalog | Quản trị catalog/product và provisioning AWS resource | Không mặc định |
| AWS Controllers for Kubernetes (ACK) | Quản lý AWS resource bằng Kubernetes API | Không |
| Azure Service Operator | Quản lý Azure resource qua Kubernetes custom resource | Không |
| Google Config Connector | Quản lý Google Cloud resource từ Kubernetes | Không |
| Crossplane provider | Expose cloud resource như Kubernetes API và composition | Không mặc định |
| Provider SDK/CLI/IaC | Provision resource theo pipeline hoặc code | Không |

Một operator có thể tạo database/queue và ghi connection data vào Secret, nhưng điều đó không biến nó thành service broker theo OSB API. Phải xem contract mà platform và application thực sự sử dụng.

### 9.2. AWS Service Catalog, ACK và CloudFormation

AWS Service Catalog quản lý danh mục sản phẩm AWS đã được phê duyệt và quyền provisioning. CloudFormation/IaC hoặc pipeline có thể tạo RDS, S3, SQS, MSK và các resource khác. ACK cho phép quản lý nhiều AWS resource qua Kubernetes custom resource.

Các công cụ này có thể provision resource nhưng binding application vẫn cần cơ chế riêng: tạo Secret/config, inject resource ARN/URL, gắn IAM role hoặc cung cấp service binding contract. Không nhầm quyền provisioning của pipeline/controller với quyền runtime của application.

### 9.3. Azure Service Operator và resource management

Azure Service Operator cho phép khai báo Azure resource bằng Kubernetes custom resource và controller reconcile trạng thái desired với Azure control plane. Azure Resource Manager/Bicep/Terraform cũng có thể provision managed service.

Sau khi tạo resource, platform phải quyết định cách phân phối connection data:
- Endpoint/resource ID qua ConfigMap hoặc binding metadata.
- Secret qua Key Vault/Secret Store CSI/Kubernetes Secret.
- Identity qua Managed Identity/Workload Identity.
- Network access qua VNet/private endpoint/firewall.

Operator provisioning không đồng nghĩa application đã có quyền truy cập resource.

### 9.4. Google Config Connector và Crossplane

Config Connector quản lý Google Cloud resource từ Kubernetes custom resource; Crossplane có thể compose resource và expose abstraction theo platform API. Chúng là control plane reconciliation/provisioning. Binding data và runtime identity cần được thiết kế riêng.

Ví dụ, Config Connector tạo Cloud SQL instance và Secret chứa database metadata; workload vẫn cần Cloud SQL Client IAM role hoặc connector permission và database authentication phù hợp. Không cấp quyền quản trị project cho ứng dụng chỉ vì controller cần quyền provisioning.

### 9.5. Khi nào dùng OSB API?

OSB API phù hợp khi platform đã có broker ecosystem hoặc cần contract chuẩn giữa platform và nhiều service broker. Dùng Kubernetes operator/controller khi team vận hành Kubernetes-native control plane và resource lifecycle qua CRD. Dùng IaC/pipeline khi provisioning gắn với release infrastructure và không cần application self-service bind/unbind.

Chọn theo:
- Platform có hiểu OSB API hay không?
- Ai là owner của provisioning và deprovisioning?
- Cần self-service catalog/plan không?
- Binding credential có scope riêng theo application không?
- Unbind có thu hồi credential và deprovision có bảo vệ dữ liệu không?
- Có audit, approval, quota và cost allocation không?
- Có thể reconcile drift và recover operation timeout không?
## 10. Kết hợp discovery, binding và broker trong một kiến trúc

### 10.1. Tách control plane và data plane

Một kiến trúc hoàn chỉnh có thể sử dụng cả ba cơ chế:

- Control plane provision database/queue bằng broker hoặc operator.
- Binding layer đưa endpoint/resource metadata/credential tới workload.
- Discovery layer giúp service tìm endpoint của service khác.
- Data plane gửi request tới service hoặc managed resource.
- Identity/network layer xác thực và cho phép request.

~~~mermaid
flowchart TB
    subgraph Control["Control plane"]
      P["Platform / GitOps / IaC"]
      B["Service Broker / Operator"]
      M["Managed resource provisioning"]
      P --> B --> M
    end
    subgraph Runtime["Workload runtime"]
      S["Service binding / config"]
      D["Service discovery / DNS"]
      A["Spring Boot application"]
      I["Workload identity"]
      A --> S
      A --> D
      A --> I
    end
    M --> S
    D --> A
    A --> M
~~~

Ví dụ:
1. Platform tạo SQS queue hoặc PostgreSQL database.
2. Operator/broker lưu queue URL hoặc DB endpoint vào binding.
3. Workload nhận binding directory/Secret và IAM role.
4. Spring Boot ánh xạ binding thành datasource hoặc AWS client configuration.
5. Reservation Service dùng Kubernetes DNS hoặc DiscoveryClient để gọi Pricing Service.
6. AWS SDK dùng IAM role để gọi SQS; binding chỉ cung cấp queue URL/Region.

### 10.2. Một request không đi qua service broker

Service broker không nằm trên đường đi của HTTP request thông thường. Khi Reservation Service gọi Pricing Service, request đi qua DNS/registry, load balancer, network và service endpoint. Broker chỉ tham gia khi platform provision/update/bind/unbind resource.

Nếu mỗi request nghiệp vụ đều gọi broker để lấy endpoint hoặc credential, kiến trúc đã trộn control plane với data plane và tạo dependency/latency không cần thiết.

### 10.3. Chọn mechanism theo từng dependency

| Dependency | Cơ chế phù hợp | Lý do |
| --- | --- | --- |
| Pricing Service trong cùng Kubernetes cluster | Kubernetes Service DNS | Endpoint ổn định và routing native |
| Service trong nhiều cluster | Private DNS, service mesh multi-cluster, Consul hoặc registry phù hợp | Cần discovery xuyên network/cluster |
| PostgreSQL managed instance | Service binding/config + workload/database identity | Cần endpoint và credential/authorization |
| S3 bucket | Resource metadata qua config/binding + IAM role | Bucket name không phải credential |
| Queue được platform self-service tạo | Broker/operator provision + binding | Cần lifecycle và scoped access |
| Cloud Run service | Service URL/internal routing + IAM invocation identity | URL và authorization là hai lớp riêng |

### 10.4. Không tạo hai source of truth

Nếu Kubernetes Service DNS đã là nguồn endpoint của Pricing Service, không nên đồng thời duy trì Eureka registry cho cùng endpoint nếu không có yêu cầu đồng bộ. Nếu broker cấp database endpoint vào binding, không hard-code một endpoint khác trong Config Server. Nếu workload identity đã cung cấp credential ngắn hạn, không tạo static password song song.

Mỗi resource cần có một owner cho endpoint, credential và lifecycle. Các nguồn khác chỉ nên giữ reference hoặc metadata cần thiết.

## 11. Security boundary: discovery không cấp quyền

### 11.1. Phát hiện endpoint không đồng nghĩa được phép truy cập

DNS resolve thành công hoặc DiscoveryClient trả về instance không chứng minh caller có quyền gọi service. Authorization phải được enforce ở application, gateway, mesh hoặc resource IAM policy.

Ví dụ:
- Kubernetes NetworkPolicy giới hạn pod nào có thể mở connection.
- mTLS/service mesh xác thực workload identity và áp policy east-west.
- JWT/OAuth kiểm tra principal/claim ở application API.
- AWS IAM, Azure RBAC hoặc Google IAM cho phép API operation tới managed resource.
- Database role kiểm soát quyền SQL sau khi kết nối.

Không dùng việc service có mặt trong registry làm authorization check.

### 11.2. Bảo vệ registry và Kubernetes API

Registry chứa hostname, IP, port, health metadata và đôi khi tags/attributes nội bộ. Giới hạn ai có quyền đăng ký, deregister và query registry. Bật TLS/authentication, ACL và audit. Không đưa token/password vào service metadata hoặc tag.

Với Spring Cloud Kubernetes DiscoveryClient, ServiceAccount chỉ nên có quyền đọc đúng namespace/resource cần thiết. Không cấp quyền ghi Service/EndpointSlice hoặc quyền đọc Secret nếu discovery không cần.

### 11.3. Broker credential và workload credential

Broker có thể cần quyền quản trị để tạo database, user, queue, IAM policy hoặc secret. Application workload thường chỉ cần quyền sử dụng resource. Hai identity phải được tách biệt.

- Broker credential: lưu trong secret store, chỉ platform/broker runtime đọc.
- Binding credential: scope theo instance/binding/application, có thể revoke.
- Workload identity: dùng token ngắn hạn theo role/identity của workload.
- Human/admin identity: dùng cho approval, break-glass và vận hành có audit.

Không mount broker master credential vào Spring Boot application.

### 11.4. SSRF và endpoint injection

Nếu application nhận endpoint từ binding/config, validate scheme, host và port theo allow-list. Không cho HTTP request từ user ghi đè service URL hoặc binding path. Nếu service discovery có custom metadata, không dùng giá trị không tin cậy làm URL đích tùy ý; có thể tạo SSRF tới metadata endpoint hoặc internal admin service.

Khi tạo custom binding reader, chống path traversal/symlink và chỉ chọn binding name từ cấu hình tin cậy. Không đọc file tùy ý từ filesystem dựa trên request parameter.

### 11.5. TLS, mTLS và certificate lifecycle

Discovery cung cấp endpoint, không tự thiết lập trust. Với HTTPS/mTLS:
- Xác minh DNS name khớp certificate SAN.
- Quản lý CA/client certificate và rotation.
- Không tắt hostname verification.
- Với service mesh, hiểu nơi TLS được terminate và identity được xác thực.
- Với managed service private endpoint, kiểm tra private DNS và certificate hostname.

## 12. Kiểm thử discovery và service broker

### 12.1. Unit test service selection

Nếu application có custom service selection logic, test với fake DiscoveryClient hoặc mock instance list. Kiểm tra:
- Service ID chính xác.
- Empty instance list được xử lý an toàn.
- Instance unhealthy/metadata thiếu bị loại bỏ.
- Port/protocol được chọn đúng.
- Không fallback sang hostname production hard-code.

Không cần mock Kubernetes API trong mọi unit test nếu logic chỉ dùng HTTP client thông thường gọi Service DNS.

### 12.2. Kubernetes integration test

Trên kind/minikube hoặc cluster test, kiểm tra:
1. Deployment pod có label đúng.
2. Service selector khớp pod.
3. EndpointSlice có endpoint ready.
4. DNS phân giải Service name.
5. Readiness failure loại pod khỏi endpoint.
6. Pod restart/scale cập nhật endpoint.
7. NetworkPolicy cho phép đúng traffic.
8. DiscoveryClient có quyền RBAC đúng nếu được dùng.

Có thể dùng Testcontainers cho dependency nhưng nó không thay thế kiểm thử Kubernetes DNS, RBAC và EndpointSlice.

### 12.3. Test Spring Cloud DiscoveryClient

Dùng test registry hoặc test context với implementation discovery phù hợp. Kiểm tra client-side load balancing chọn instance từ registry, xử lý empty list và refresh khi instance deregister. Nếu dùng Eureka/Consul, kiểm tra heartbeat/health status và registry availability.

Với DNS-based discovery, test resolver/network path và connection pool behavior. Test không nên giả định DNS record thay đổi sẽ lập tức làm mọi JVM connection chuyển sang endpoint mới.

### 12.4. Test broker lifecycle

Broker/operator integration test cần kiểm tra:
- Catalog trả đúng service offering/plan.
- Provision tạo đúng resource và operation status.
- Retry provision không tạo resource trùng.
- Bind tạo credential riêng và trả đúng metadata.
- Unbind thu hồi credential đúng binding.
- Deprovision tuân thủ retention/backup/deletion policy.
- Lỗi provider API có retry/backoff và operation state rõ.
- Audit ghi nhận actor/resource/operation.

Dùng fake provider API hoặc ephemeral cloud resource trong CI. Không test deprovision trên resource chứa dữ liệu production.

### 12.5. Contract test binding handoff

Sau khi broker/operator tạo binding, test platform có đưa data tới workload theo đúng contract hay không:
- Kubernetes Service Binding directory có đúng metadata/type/key.
- Cloud Foundry VCAP_SERVICES có đúng label/name/credentials.
- Secret/volume mount đúng namespace và permission.
- Spring Cloud Bindings đọc đúng binding.
- Spring Boot tạo datasource/client.
- Workload identity có quyền riêng để gọi managed resource.

Đây là contract giữa control plane và runtime; test riêng broker thành công không chứng minh application đã nhận binding đúng.

## 13. Observability và vận hành

### 13.1. Discovery signals

Theo dõi:
- Số instance được đăng ký và healthy theo service ID.
- Discovery lookup latency/error rate.
- DNS lookup failure và latency.
- Endpoint churn/deregister/re-register.
- LoadBalancer selected instance và retry.
- Kubernetes EndpointSlice count/ready endpoint.
- Registry heartbeat, leader/quorum và watch reconnect.

Không dùng IP hoặc instance ID cardinality cao làm label metric không giới hạn.

### 13.2. Broker signals

Theo dõi:
- Provision/bind/unbind/deprovision request count.
- Operation duration và asynchronous polling age.
- Broker API error/retry rate.
- Resource provisioning failure và orphan resource count.
- Binding credential creation/revocation.
- Catalog/plan version và quota.
- Drift giữa desired resource và actual provider resource.

Broker outage có thể ảnh hưởng self-service provisioning nhưng không nhất thiết làm request runtime tới service hiện hữu dừng ngay. Runbook cần phân biệt control plane unavailable với data plane unavailable.

### 13.3. Correlation và audit

Mỗi lifecycle operation nên có request/instance/binding ID và correlation ID xuyên platform, broker và provider API. Log metadata như service offering, plan, operation state, duration và provider error code. Không log binding credential, access token hoặc secret payload.

Discovery log có thể ghi service ID, selected endpoint đã mask theo policy, request correlation ID và error category. Không log authorization header hoặc full URL nếu query string có token.

### 13.4. Runbook theo triệu chứng

**Service DNS không resolve:** kiểm tra namespace, Service name, CoreDNS, search domain, NetworkPolicy tới DNS và private DNS zone.

**Service resolve nhưng không connect:** kiểm tra EndpointSlice, readiness, port/targetPort, network route, security group/NetworkPolicy, TLS và application listener.

**DiscoveryClient trả empty list:** kiểm tra registry registration, namespace/filter, ServiceAccount RBAC, cache/watch và service ID mapping.

**Instance cũ tiếp tục được gọi:** kiểm tra readiness/deregister propagation, DNS TTL, client cache, connection pool và registry health check.

**Broker provision timeout:** tra operation ID và broker state trước khi retry; không gửi request mới với instance ID khác nếu operation cũ có thể đã thành công.

**Binding tồn tại nhưng app không kết nối:** kiểm tra binding parser/property mapping, credential version, workload identity, resource IAM và network độc lập.

## 14. Lỗi kiến trúc thường gặp

| Triệu chứng/thiết kế | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Gọi Pod IP trực tiếp | Pod IP thay đổi khi reschedule | Gọi Kubernetes Service DNS hoặc discovery registry |
| Triển khai Eureka trong mọi cluster | Không tận dụng Kubernetes Service DNS | Đánh giá DNS trước; chỉ thêm registry khi cần |
| Service được discover nhưng AccessDenied | Discovery không cấp IAM/RBAC | Cấu hình workload identity và resource policy |
| Service Broker bị gọi trong request path | Trộn control plane và data plane | Chỉ dùng broker cho lifecycle operation |
| OSB API bị gọi nhầm là Service Binding Spec | Nhầm provisioning contract với binding delivery contract | Tách broker API và runtime binding format |
| Operator tạo resource nhưng app không kết nối | Thiếu binding/secret/identity/network | Kiểm tra từng handoff boundary |
| Discovery trả instance cũ | Health check/cache/deregister chậm | Kiểm tra TTL, heartbeat, watch và readiness |
| DNS đổi nhưng request vẫn tới IP cũ | JVM/client cache hoặc keep-alive connection | Điều chỉnh DNS cache và connection lifecycle có căn cứ |
| Broker retry tạo resource trùng | Provision/bind không idempotent | Dùng operation/instance ID và state persistence |
| Unbind xóa nhầm database | Nhầm unbind với deprovision | Tách lifecycle và deletion policy |
| Cấp cluster-admin cho discovery | RBAC quá rộng | Role/RoleBinding chỉ đọc resource cần thiết |
| Dùng binding credential thay IAM role | Không phân biệt authentication model | Ưu tiên workload identity cho cloud API |

## 15. Checklist trước production

1. **Boundary:** phân biệt discovery, binding, broker và mesh trong sơ đồ kiến trúc.
2. **Discovery source:** chọn Kubernetes DNS, registry, Cloud Map, Service Directory hoặc private DNS theo runtime.
3. **Routing:** hiểu client-side/server-side load balancing, health check, TTL và connection reuse.
4. **Kubernetes:** Service selector, port, EndpointSlice, readiness và DNS đã được kiểm tra.
5. **Spring integration:** DiscoveryClient/LoadBalancer chỉ bật khi cần; version/BOM tương thích.
6. **RBAC:** DiscoveryClient chỉ đọc namespace/resource cần thiết.
7. **Broker contract:** xác định OSB API, operator/CRD hay IaC provisioning; không trộn với binding spec.
8. **Idempotency:** provision/bind/unbind xử lý retry và operation timeout an toàn.
9. **Binding handoff:** endpoint/metadata/credential được chuyển đúng format tới workload.
10. **Identity:** broker identity và application workload identity tách biệt; least privilege.
11. **Network/TLS:** DNS, route, firewall, NetworkPolicy, certificate và mTLS được kiểm chứng.
12. **Lifecycle:** rotation, unbind, deprovision, backup và retention có owner/runbook.
13. **Testing:** unit, registry, Kubernetes, broker lifecycle và binding contract test.
14. **Observability:** discovery health, endpoint churn, broker operation và orphan resource có metric/alert.
15. **Recovery:** có cách phục hồi registry outage, broker outage và stale binding.

## 16. Bài tập tự luyện

1. Vẽ sơ đồ phân biệt Service Discovery, Service Binding, Service Broker và Service Mesh cho một hệ thống Reservation/Pricing/Billing.
2. Tạo Kubernetes Service cho Pricing Service; kiểm tra DNS và EndpointSlice khi scale deployment.
3. So sánh gọi Service DNS với Spring Cloud Kubernetes DiscoveryClient và Spring Cloud LoadBalancer.
4. Thiết kế RBAC tối thiểu cho DiscoveryClient đọc Services/EndpointSlices trong một namespace.
5. Chọn Eureka, Consul hoặc Kubernetes DNS cho hệ thống có VM, Kubernetes và Cloud Run; giải thích failure domain và vận hành.
6. So sánh AWS Cloud Map, Azure Container Apps internal discovery, AKS DNS, GKE DNS và Google Service Directory.
7. Mô tả OSB API provision/bind/unbind/deprovision và phân biệt với Kubernetes Service Binding Specification.
8. Thiết kế broker idempotent khi platform retry provision sau timeout.
9. Dùng operator/ACK/Config Connector để provision một resource; mô tả riêng cách binding metadata và workload identity được cấp.
10. Mô phỏng binding tồn tại nhưng application bị AccessDenied; tìm lỗi ở identity, IAM/RBAC hay network.
11. Thiết kế runbook khi endpoint cũ tiếp tục được gọi sau rollout.
12. Vẽ control plane/data plane và xác định broker outage có ảnh hưởng tới traffic runtime hiện hữu hay không.

**Tiêu chí hoàn thành:** người học phân biệt được discovery, binding và broker; chọn được cơ chế discovery phù hợp cho Kubernetes hoặc managed cloud runtime; giải thích được Service Broker/OSB API và binding handoff; cấu hình được Spring Cloud discovery khi cần; và kiểm thử được endpoint lifecycle, identity, network và provisioning idempotency.

## Tài liệu tham khảo

- [Spring Cloud Commons — DiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): discovery abstraction và common client features.
- [Spring Cloud Kubernetes Reference](https://docs.spring.io/spring-cloud-kubernetes/reference/): Kubernetes discovery, config và load balancing.
- [Spring Cloud Netflix Eureka](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html): Eureka server/client integration.
- [Spring Cloud Consul](https://docs.spring.io/spring-cloud-consul/reference/): Consul discovery và health checks.
- [Kubernetes Services, Load Balancing, and Networking](https://kubernetes.io/docs/concepts/services-networking/service/): Service, ClusterIP, headless service và endpoint routing.
- [Kubernetes DNS for Services and Pods](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/): DNS name trong cluster.
- [Kubernetes EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/): endpoint representation và lifecycle.
- [Kubernetes Service Binding Specification](https://servicebinding.io/spec/core/1.0.0/): binding data contract cho workload.
- [Open Service Broker API](https://github.com/openservicebrokerapi/servicebroker): broker lifecycle API contract.
- [Cloud Foundry Services](https://docs.cloudfoundry.org/services/): service brokers, catalog, provision và bind.
- [AWS Cloud Map](https://docs.aws.amazon.com/cloud-map/latest/dg/what-is-cloud-map.html): service registry và discovery.
- [Amazon ECS Service Discovery](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-discovery.html): ECS tích hợp Cloud Map.
- [Azure Container Apps service discovery](https://learn.microsoft.com/azure/container-apps/connect-apps): internal app-to-app connectivity.
- [Azure Private DNS](https://learn.microsoft.com/azure/dns/private-dns-overview): private DNS zones và name resolution.
- [Google Cloud Service Directory](https://cloud.google.com/service-directory/docs/overview): managed service registry.
- [Google Kubernetes Engine Services](https://cloud.google.com/kubernetes-engine/docs/concepts/service): service networking trong GKE.
- [Google Cloud Run service-to-service authentication](https://cloud.google.com/run/docs/authenticating/service-to-service): IAM identity và ID token khi gọi service.
