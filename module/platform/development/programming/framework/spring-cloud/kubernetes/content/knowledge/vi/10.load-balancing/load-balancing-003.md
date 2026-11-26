# Phân biệt chế độ POD và SERVICE khi bản phát hành hỗ trợ

## 1. Điều cần phân biệt: Spring chọn Pod hay chọn Service?

Trong chương **Cân bằng tải** của module **SPRING_CLOUD_KUBERNETES**, hai chế độ `POD` và `SERVICE` mô tả loại đích mà tích hợp Spring Cloud Kubernetes LoadBalancer cung cấp cho quá trình chọn instance. Chúng không phải hai giá trị của `Service.spec.type` trong Kubernetes.

Với một Service thông thường tên `orders` trong namespace `shop`, cổng Service 80 ánh xạ đến ứng dụng ở 8080:

```text
POD
http://orders/demo/identity
  -> Spring LoadBalancer chọn một endpoint
  -> http://<Pod-IP>:8080/demo/identity

SERVICE
http://orders/demo/identity
  -> Spring LoadBalancer chọn một đích Service
  -> http://orders.shop.svc.cluster.local:80/demo/identity
  -> mạng Service của Kubernetes chuyển đến backend:8080
```

Ví dụ SERVICE trên giả định Service có ClusterIP và domain cụm là `cluster.local`. Với headless Service hoặc service mesh, cần xét thêm cơ chế mạng thực tế.

Điểm cần nhớ là **đơn vị được Spring lựa chọn**. Khi dùng POD, danh sách ứng viên thường biểu diễn các backend. Khi dùng SERVICE, ứng viên biểu diễn Service theo tên DNS và cổng Service; việc chọn backend phía sau Service thông thường do lớp mạng Kubernetes xử lý.

Bài này đi từ điều kiện hỗ trợ phiên bản đến cấu hình, cách chọn cổng và phép thực hành phân biệt hai đường gọi. Các manifest, mã Java và đầu ra là ví dụ để người học triển khai; không phải kết quả đã chạy trên một cụm cụ thể.

## 2. Kiểm tra bản phát hành trước khi áp dụng cấu hình

### 2.1. Không suy ra khả năng hỗ trợ chỉ từ tên thuộc tính

Tài liệu Spring Cloud Kubernetes của nhánh 3.3 và tài liệu 5.1 mô tả hai chế độ cùng thuộc tính:

```properties
spring.cloud.kubernetes.loadbalancer.mode=POD
```

hoặc:

```properties
spring.cloud.kubernetes.loadbalancer.mode=SERVICE
```

Các tài liệu đó ghi mặc định là POD. Đây là bằng chứng cho các nhánh được đối chiếu, không phải khẳng định mọi bản phát hành trong lịch sử đều có cùng API hoặc cùng điều kiện kích hoạt. [LoadBalancer ở nhánh 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/load-balancer.html), [LoadBalancer ở nhánh 5.1](https://docs.spring.io/spring-cloud-kubernetes/reference/load-balancer.html).

Trước khi dùng trong một dự án, cần xác định:

1. Phiên bản Spring Boot, Spring Cloud BOM và Spring Cloud Kubernetes thực tế được resolve.
2. Starter Kubernetes đang dùng thuộc họ Fabric8 hay Kubernetes Java Client.
3. Tài liệu hoặc mã nguồn đúng tag có hỗ trợ `mode` và giá trị SERVICE hay không.
4. Auto-configuration liên quan đã được kích hoạt trong môi trường chạy hay chưa.
5. HTTP client thực sự có tích hợp Spring Cloud LoadBalancer hay chỉ dùng DNS thông thường.

Một khóa xuất hiện trong file cấu hình hoặc trong Environment chưa chứng minh nó đã được bind vào bean hoạt động. Nếu dependency hoặc auto-configuration tương ứng không có, khóa có thể không tạo ra hành vi mong đợi.

### 2.2. Phạm vi ví dụ trong bài

Ví dụ chọn **Fabric8 loadbalancer starter**, một namespace `shop`, Service có selector, backend HTTP và không có supplier tùy biến. Khi chuyển sang Kubernetes Java Client, dùng starter tương ứng và kiểm tra yêu cầu quyền của implementation đó.

Hai starter được tài liệu liệt kê là:

```text
org.springframework.cloud:spring-cloud-starter-kubernetes-fabric8-loadbalancer
org.springframework.cloud:spring-cloud-starter-kubernetes-client-loadbalancer
```

Chọn một họ client theo kiến trúc của ứng dụng và quản lý phiên bản bằng BOM tương thích. Không thêm cả hai chỉ để thử xem cấu hình nào “ăn”. Ngoài starter cân bằng tải, ví dụ WebClient ở dưới cần Spring WebFlux và các dependency discovery phù hợp với cấu hình của release.

Một cấu hình gốc được kiểm chứng bằng mã nguồn tag v3.3.3 có `mode=POD`, `clusterDomain=cluster.local`, `portName=http`. Đối chiếu đúng tag khi cần biết giá trị mặc định của dự án. [KubernetesLoadBalancerProperties v3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/loadbalancer/KubernetesLoadBalancerProperties.java).

## 3. Chế độ POD: danh sách ứng viên là endpoint

Trong POD, Spring dùng DiscoveryClient để lấy các instance tương ứng với tên dịch vụ logic. Cấu hình namespace, bộ lọc và cách chọn cổng của discovery ảnh hưởng đến danh sách này. [Quan hệ POD với DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/load-balancer.html).

Một danh sách giả định:

| serviceId | host | port |
| --- | --- | --- |
| orders | 10.42.1.15 | 8080 |
| orders | 10.42.2.21 | 8080 |
| orders | 10.42.3.18 | 8080 |

Luồng xử lý:

```text
Tên logic orders
  -> DiscoveryClient
  -> danh sách instance theo trạng thái nguồn discovery
  -> thuật toán Spring chọn một instance
  -> HTTP client gọi địa chỉ instance được chọn
```

POD cho ứng dụng cơ hội làm việc ở mức instance. Tuy nhiên chọn POD không tự bật các chính sách theo zone, trọng số, canary, retry hay health check chủ động. Những hành vi đó cần thành phần và cấu hình riêng.

Cũng không có cam kết mọi request kế tiếp sẽ đi đến Pod khác. Thuật toán, cache, tính đồng thời, retry và danh sách ứng viên đều có thể ảnh hưởng kết quả. Mỗi replica của caller còn có trạng thái cân bằng tải riêng; không có một bộ đếm toàn cụm chỉ vì các caller cùng dùng Spring.

Trong cụm có mạng Pod thông thường, đường gọi tới endpoint có thể đi thẳng đến Pod IP mà không dùng VIP Service để chọn backend. Dù vậy Service vẫn thường là tài nguyên giúp xác định tập endpoint; POD không có nghĩa ứng dụng độc lập hoàn toàn với Service và API Kubernetes.

## 4. Chế độ SERVICE: Spring tạo đích là Service

Với SERVICE, implementation Kubernetes tạo ứng viên từ tài nguyên Service và tên DNS theo namespace/domain cụm. Với một Service `orders` duy nhất trong `shop`, ứng viên có thể là:

| serviceId | host | port |
| --- | --- | --- |
| orders | orders.shop.svc.cluster.local | 80 |

Nếu chỉ có một ứng viên Service, Spring không có ba Pod trong danh sách này để tự chọn. Request đến Service thông thường được lớp mạng Service chuyển tới endpoint phù hợp.

Nếu phạm vi tìm kiếm có nhiều Service cùng tên ở nhiều namespace, có thể có nhiều ứng viên Service. Vì vậy cũng không nên nói SERVICE luôn chỉ có đúng một instance. Phải giới hạn phạm vi namespace để tránh vô tình gộp môi trường.

### 4.1. SERVICE vẫn có phần khám phá tài nguyên

Không đồng nhất SERVICE với một HTTP client thuần DNS. Chẳng hạn, supplier Fabric8 ở tag v3.3.3 đọc các Service qua Kubernetes client, theo namespace được cấu hình, rồi ánh xạ chúng thành instance. Nó vẫn cần quyền và kết nối đến API tương ứng. [Fabric8ServicesListSupplier v3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-fabric8-loadbalancer/src/main/java/org/springframework/cloud/kubernetes/fabric8/loadbalancer/Fabric8ServicesListSupplier.java).

Một client thuần DNS có thể gọi trực tiếp:

```text
http://orders.shop.svc.cluster.local:80/demo/identity
```

mà không dùng cơ chế khám phá Service của Spring. Đó là lựa chọn kiến trúc khác. Chỉ đổi `mode: SERVICE` trong một ứng dụng đang dùng Kubernetes loadbalancer starter không tự loại bỏ toàn bộ nhu cầu đọc API.

### 4.2. Loại Service vẫn quyết định đường mạng

| Tài nguyên Kubernetes | Điều cần hiểu khi dùng đích Service |
| --- | --- |
| ClusterIP thông thường | DNS thường dẫn đến IP Service; lớp mạng Service chuyển tới backend |
| NodePort | Tên `.svc` và cổng Service vẫn là đường trong cụm; không tự đổi thành Node IP và nodePort |
| LoadBalancer | Đích `.svc` không tự trở thành địa chỉ external load balancer |
| Headless, `clusterIP: None` | Không có VIP Service để thực hiện đường chuyển tiếp như ClusterIP thông thường |
| ExternalName hoặc Service không selector | Cần kiểm tra hợp đồng hỗ trợ riêng của implementation/release |

Kubernetes phân biệt các loại Service và cơ chế headless. Vì thế không thể chỉ nhìn từ SERVICE trong cấu hình Spring để kết luận có một lớp proxy VIP ở mọi trường hợp. [Các kiểu Kubernetes Service](https://kubernetes.io/docs/concepts/services-networking/service/).

## 5. Bảng so sánh theo trách nhiệm

| Khía cạnh | POD | SERVICE |
| --- | --- | --- |
| Đơn vị ứng viên của Spring trong ca nền | Endpoint backend | Service theo DNS và cổng Service |
| Đích Spring chọn trong ví dụ | `10.42.1.15:8080` | `orders.shop.svc.cluster.local:80` |
| Bên quyết định backend trong ca nền | Spring chọn một instance | Lớp mạng Service chọn backend phía sau |
| Cổng cần đối chiếu | Cổng endpoint/backend | `Service.spec.ports[].port` được chọn |
| Metadata để chọn riêng Pod | Có thể dùng nếu discovery/supplier cung cấp và có chính sách | Instance Service không mặc nhiên chứa metadata từng Pod |
| Phụ thuộc vào danh sách Pod ở caller | Qua nguồn discovery và các lớp cache | Caller có thể chỉ giữ ứng viên Service |
| DNS Service trong đường dữ liệu | Không phải đích chính của ca gọi endpoint trực tiếp | Là thành phần của đường gọi Service |
| Quyền Kubernetes API | Theo discovery thực tế | Theo supplier Service thực tế; không mặc định bằng không |

Bảng mô tả ca nền có Service ClusterIP, không tùy biến supplier và không có thành phần mạng làm đổi đường gọi. Với service mesh, proxy hoặc client tùy biến, phải quan sát đích thực tế trước khi áp dụng kết luận.

## 6. Cấu hình cổng phải theo đúng chế độ

### 6.1. Một Service dùng chung cho hai phép thử

Giả sử namespace `shop` đã có backend `orders`, hai replica Ready, tiến trình lắng nghe 8080 và cổng Pod được đặt tên `app-http`. Service cho bài thực hành:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: orders
  namespace: shop
  labels:
    primary-port-name: http
spec:
  type: ClusterIP
  selector:
    app: orders
  ports:
    - name: http
      protocol: TCP
      port: 80
      targetPort: app-http
```

Phần khai báo cổng trong Pod tương ứng là:

```yaml
ports:
  - name: app-http
    containerPort: 8080
```

Đặt `containerPort: 8080` không tự mở socket; ứng dụng phải thực sự nghe ở cổng đó. Trong ví dụ này, `http` là tên cổng Service còn `app-http` là tên cổng Pod. Hai tên có vai trò khác nhau.

### 6.2. Cấu hình POD

```yaml
spring:
  cloud:
    kubernetes:
      discovery:
        all-namespaces: false
        namespaces:
          - shop
        primary-port-name: http
        include-not-ready-addresses: false
      loadbalancer:
        mode: POD
```

Đích cần quan sát ở ca nền là địa chỉ backend với cổng 8080. Khi discovery đọc endpoint, `targetPort` đã được giải thành cổng backend phù hợp. Nhãn `primary-port-name` và thuộc tính chọn cổng của discovery cần được hiểu theo đúng release. [Quy tắc DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

### 6.3. Cấu hình SERVICE

```yaml
spring:
  cloud:
    kubernetes:
      discovery:
        all-namespaces: false
        namespaces:
          - shop
      loadbalancer:
        mode: SERVICE
        port-name: http
        cluster-domain: cluster.local
```

Đích cần quan sát là `orders.shop.svc.cluster.local:80`. Thuộc tính `cluster-domain` phải khớp domain thực tế của cụm. Sai domain có thể gây lỗi DNS dù Service tồn tại và backend khỏe.

Các tên dạng kebab-case ở YAML tương ứng với thuộc tính được bind trong nhóm `spring.cloud.kubernetes.loadbalancer`; tránh nhầm với nhóm `spring.cloud.loadbalancer` của cơ chế cân bằng tải chung. [Danh mục thuộc tính Kubernetes loadbalancer](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

### 6.4. Service nhiều cổng

Ví dụ thêm cổng quản trị:

```yaml
ports:
  - name: management
    port: 90
    targetPort: 9090
  - name: http
    port: 80
    targetPort: app-http
```

Với SERVICE, tài liệu và mapper v3.3.3 mô tả:

- Một cổng: dùng cổng đó.
- Nhiều cổng: tìm tên cổng theo `loadbalancer.port-name`.
- Không tìm được tên: có fallback về cổng đầu tiên; không nên dùng thứ tự làm hợp đồng.
- Không có cổng: Service không phải đích cân bằng tải hợp lệ theo cơ chế này.

Mapper lấy số từ `ServicePort.port`, không lấy `targetPort` để tạo đích DNS Service. [Fabric8ServiceInstanceMapper v3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-fabric8-loadbalancer/src/main/java/org/springframework/cloud/kubernetes/fabric8/loadbalancer/Fabric8ServiceInstanceMapper.java).

Đối với POD, cổng cuối cùng xuất phát từ instance discovery. Do đó không giả định `discovery.primary-port-name` và `loadbalancer.port-name` là hai tên thay thế cho cùng một thiết lập. Khi có cả hai trong một bộ cấu hình, ghi rõ cái nào phục vụ đường nào.

## 7. HTTP client phải thực sự dùng Spring Cloud LoadBalancer

Chỉ đặt mode chưa đủ. Request phải đi qua client tích hợp cân bằng tải.

Ví dụ ứng dụng caller có Spring WebFlux, starter Fabric8 loadbalancer và các dependency discovery tương thích. Lớp Java sau minh họa WebClient được đánh dấu `@LoadBalanced`:

```java
package lab.caller;

import java.time.Duration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableDiscoveryClient
public class CallerApplication {
    public static void main(String[] args) {
        SpringApplication.run(CallerApplication.class, args);
    }

    @Bean
    @LoadBalanced
    WebClient.Builder ordersClientBuilder() {
        return WebClient.builder();
    }

    @RestController
    static class OrdersCaller {
        private final WebClient client;

        OrdersCaller(@LoadBalanced WebClient.Builder builder) {
            this.client = builder.build();
        }

        @GetMapping("/demo/call-orders")
        Mono<String> callOrders() {
            return client.get()
                .uri("http://orders/demo/identity")
                .retrieve()
                .bodyToMono(String.class)
                .timeout(Duration.ofSeconds(5));
        }
    }
}
```

Backend cần có `GET /demo/identity` trả danh tính, chẳng hạn:

```json
{"app":"orders","pod":"orders-7f9b7c8d6b-k2x4p","port":8080}
```

Mã caller giữ nguyên giữa hai chế độ. Chỉ cấu hình mode và thiết lập cổng liên quan thay đổi. Tên host `orders` trong URI là serviceId mà Spring xử lý trong ví dụ này.

Nếu dùng `WebClient.create()` ở chỗ gọi thay vì builder được tích hợp, request có thể đi theo DNS thông thường. Nó vẫn có khả năng thành công trong cụm, nhưng không chứng minh POD hoặc SERVICE của Spring đã hoạt động.

Tương tự, `curl http://orders` chạy trong một Pod kiểm tra đường DNS/Service; curl không đọc cấu hình Spring của ứng dụng caller. Không dùng kết quả đó như bằng chứng duy nhất cho mode.

## 8. Quan sát đích Spring đã chọn

### 8.1. Vì sao danh tính backend chưa đủ?

Cả POD lẫn SERVICE đều có thể trả về body từ cùng hai backend. Nếu chỉ thống kê trường `pod` trong body, bạn biết backend nào xử lý nhưng chưa biết Spring đã chọn địa chỉ Pod hay địa chỉ Service.

Cần hai loại bằng chứng:

1. Đích instance do Spring LoadBalancer chọn.
2. Phản hồi nghiệp vụ cuối cùng từ backend.

Có thể dùng tracing phù hợp hoặc hook lifecycle của Spring Cloud LoadBalancer. Ví dụ dưới đây dành cho integration WebClient sử dụng kiểu context/response tương ứng, cần kiểm tra API của Spring Cloud Commons đi kèm release.

```java
package lab.caller;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.CompletionContext;
import org.springframework.cloud.client.loadbalancer.LoadBalancerLifecycle;
import org.springframework.cloud.client.loadbalancer.Request;
import org.springframework.cloud.client.loadbalancer.RequestDataContext;
import org.springframework.cloud.client.loadbalancer.Response;
import org.springframework.cloud.client.loadbalancer.ResponseData;
import org.springframework.stereotype.Component;

@Component
public class SelectedTargetLogger implements
        LoadBalancerLifecycle<RequestDataContext, ResponseData, ServiceInstance> {
    private static final System.Logger LOG =
        System.getLogger(SelectedTargetLogger.class.getName());

    @Override
    public void onStart(Request<RequestDataContext> request) {
    }

    @Override
    public void onStartRequest(Request<RequestDataContext> request,
                               Response<ServiceInstance> response) {
        ServiceInstance selected = response.getServer();
        if (selected != null) {
            LOG.log(System.Logger.Level.INFO,
                "Selected service={0}, host={1}, port={2}",
                selected.getServiceId(), selected.getHost(), selected.getPort());
        }
    }

    @Override
    public void onComplete(
        CompletionContext<ResponseData, ServiceInstance, RequestDataContext> context) {
    }
}
```

`onStartRequest` được gọi sau khi chọn instance và trước request cân bằng tải. Ví dụ chỉ log serviceId, host và port, không ghi token hoặc body. Đây là dữ liệu lựa chọn ở tầng Spring, chưa phải bản ghi packet sau DNS, NAT hay sidecar. [LoadBalancerLifecycle của Spring Cloud Commons](https://github.com/spring-cloud/spring-cloud-commons/blob/v4.3.3/spring-cloud-commons/src/main/java/org/springframework/cloud/client/loadbalancer/LoadBalancerLifecycle.java).

Nếu không xuất hiện log, kiểm tra bean lifecycle, client đang dùng, API hỗ trợ của release và quá trình chọn instance; không mặc định kết luận request đã chọn một mode cụ thể.

### 8.2. Dấu hiệu cần quan sát

```text
POD, ví dụ minh họa:
Selected service=orders, host=10.42.1.15, port=8080
Selected service=orders, host=10.42.2.21, port=8080

SERVICE, ví dụ minh họa:
Selected service=orders, host=orders.shop.svc.cluster.local, port=80
Selected service=orders, host=orders.shop.svc.cluster.local, port=80
```

IP và thứ tự thực tế được cấp động. Không viết assertion bắt buộc đúng hai dòng theo thứ tự trên. Nếu tracing phía connector chỉ thấy ClusterIP ở SERVICE, đối chiếu thêm tên đích đã chọn và bước DNS; hai lớp quan sát này có ý nghĩa khác nhau.

## 9. RBAC, DNS và mạng dữ liệu là các điều kiện riêng

Một request thành công cần nhiều chặng hoạt động:

```text
Đọc tài nguyên hoặc nhận dữ liệu discovery
  -> dựng danh sách ứng viên
  -> chọn instance
  -> DNS nếu đích là tên
  -> kết nối TCP/TLS
  -> xử lý HTTP nghiệp vụ
```

### 9.1. Quyền API theo thành phần thực sự đang chạy

Với POD dùng Kubernetes discovery trực tiếp, caller thường cần quyền đọc các Service và nguồn endpoint, có thể thêm Pod theo implementation và tính năng metadata. Nếu chọn EndpointSlice, quyền cho resource đó nằm trong API group `discovery.k8s.io`.

Với SERVICE của Fabric8 đã đối chiếu, supplier đọc Service qua Kubernetes client. Hơn nữa, nếu discovery auto-configuration vẫn chạy cùng ứng dụng, các bean đó có thể còn đọc tài nguyên khác dù đường request đang chọn Service. Không cắt quyền theo suy luận “SERVICE chỉ cần DNS” rồi bỏ qua log khởi tạo discovery.

Mã cấu hình SERVICE v3.3.3 cũng bọc supplier Service bằng cache. Đổi mode không có nghĩa mọi request đều đọc API server lại hoặc dữ liệu tự trở thành đồng bộ tức thời. [Cấu hình supplier SERVICE v3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-fabric8-loadbalancer/src/main/java/org/springframework/cloud/kubernetes/fabric8/loadbalancer/Fabric8LoadBalancerClientConfiguration.java).

Chỉ cấp `get`, `list`, `watch` cho tài nguyên thực sự cần trong phạm vi namespace đã xác minh. Không cần quyền đọc Secret hay sửa ConfigMap chỉ để chọn đích cân bằng tải.

Nếu dùng HTTP Discovery Server cho nguồn discovery của POD, phần đọc Kubernetes API có thể nằm phía server. Điều đó không tự chứng minh starter SERVICE đã được chuyển sang đọc Service từ server HTTP; kiểm tra riêng implementation được khởi tạo.

### 9.2. Đường mạng cần được phép độc lập với RBAC

RBAC không mở đường TCP giữa caller và backend. Trong POD, kiểm tra kết nối từ caller đến địa chỉ endpoint/cổng ứng dụng. Trong SERVICE, kiểm tra thêm DNS, đích Service và quá trình chuyển tiếp tới backend.

Cách NetworkPolicy được áp dụng khi có dịch địa chỉ, CNI, proxy hoặc mesh cần được xác minh trên hệ thống thực tế. Không viết một quy tắc mạng chỉ dựa trên chuỗi host xuất hiện trong log Spring.

Khi dùng HTTPS, đích mà client gọi cần phù hợp certificate và cơ chế trust. Chuyển từ DNS Service sang Pod IP có thể làm thay đổi điều kiện xác minh tên; chọn POD hoặc SERVICE không tự cấp chứng thư hay bật TLS cho backend.

## 10. Thực hành đối chiếu hai caller

### 10.1. Điều kiện chuẩn bị

Chuẩn bị trong namespace thử nghiệm `shop`:

- Backend `orders` có ít nhất hai replica Ready, trả `app`, `pod`, `port` ở `/demo/identity`.
- Service ClusterIP `orders` như mục 6: `port=80`, `targetPort=app-http`, backend 8080.
- Hai Deployment caller dùng cùng mã ứng dụng và cùng bộ dependency, tên `caller-pod` và `caller-service`.
- Cùng một cấu hình namespace, timeout, network policy và khả năng kết nối; chỉ khác cấu hình mode cần so sánh.
- ServiceAccount và quyền được thiết lập theo graph bean/API thực tế của bản phát hành.

Hai Deployment có thể dùng chung image và override mode bằng biến môi trường trong container:

```yaml
# Container của caller-pod
 env:
   - name: SPRING_CLOUD_KUBERNETES_LOADBALANCER_MODE
     value: POD
```

```yaml
# Container của caller-service
 env:
   - name: SPRING_CLOUD_KUBERNETES_LOADBALANCER_MODE
     value: SERVICE
```

Hai đoạn trên là trích phần `env`, không phải Deployment hoàn chỉnh; đặt đúng cấp dưới container trong manifest. Cấu hình chung ở mục 6 vẫn phải cung cấp namespace và lựa chọn cổng phù hợp cho mỗi caller.

### 10.2. Kiểm tra trạng thái nền

Các lệnh sau dành cho môi trường thực hành đã chuẩn bị:

```powershell
kubectl rollout status deployment/orders -n shop --timeout=120s
kubectl rollout status deployment/caller-pod -n shop --timeout=120s
kubectl rollout status deployment/caller-service -n shop --timeout=120s
kubectl get pods -n shop -o wide
kubectl get service orders -n shop -o yaml
kubectl get endpointslices.discovery.k8s.io -n shop -l kubernetes.io/service-name=orders -o yaml
```

Nếu caller dùng nguồn Endpoints thay vì EndpointSlice, đối chiếu đúng nguồn đó nữa. Pod Running chưa thay thế điều kiện Ready; backend phải mở được cổng nghiệp vụ mà ca thử sử dụng.

Mở hai terminal để truy cập caller từ máy cá nhân:

```powershell
kubectl port-forward deployment/caller-pod -n shop 18081:8080
```

```powershell
kubectl port-forward deployment/caller-service -n shop 18082:8080
```

Port-forward chỉ đưa request vào caller. Đường gọi `orders` vẫn được WebClient trong caller thực hiện. Việc truy cập qua port-forward không làm thay đổi mode của Spring.

### 10.3. Thu kết quả và đối chiếu log lựa chọn

Ví dụ gọi tuần tự để thu một mẫu nhỏ:

```powershell
$podResults = @(1..20 | ForEach-Object {
    $response = Invoke-WebRequest `
        -Uri 'http://127.0.0.1:18081/demo/call-orders' `
        -TimeoutSec 10 -UseBasicParsing
    $response.Content | ConvertFrom-Json -ErrorAction Stop
})
$serviceResults = @(1..20 | ForEach-Object {
    $response = Invoke-WebRequest `
        -Uri 'http://127.0.0.1:18082/demo/call-orders' `
        -TimeoutSec 10 -UseBasicParsing
    $response.Content | ConvertFrom-Json -ErrorAction Stop
})
$podResults | Group-Object pod | Select-Object Name, Count
$serviceResults | Group-Object pod | Select-Object Name, Count
```

Đối chiếu log ở hai Deployment:

```powershell
kubectl logs deployment/caller-pod -n shop --since=5m
kubectl logs deployment/caller-service -n shop --since=5m
```

Tiêu chí đúng cho ca nền:

| Bằng chứng | Caller POD | Caller SERVICE |
| --- | --- | --- |
| Đích Spring chọn | Endpoint IP/cổng 8080 thuộc tập discovery hợp lệ | `orders.shop.svc.<domain>` và cổng Service 80 |
| Phản hồi nghiệp vụ | `app=orders`, Pod thuộc backend mong muốn | `app=orders`, Pod thuộc backend mong muốn |
| Mã HTTP | Thành công theo hợp đồng endpoint | Thành công theo hợp đồng endpoint |
| Sai lệch cổng | Không ghép Pod IP với 80 | Không ghép DNS Service với 8080 của backend |

Không yêu cầu 20 request phải chia đúng 10–10 hoặc buộc hai chế độ cho cùng một chuỗi Pod. Hai nhóm request còn được gửi ở hai khoảng thời gian khác nhau; đây là phép nhận diện đường gọi, không phải benchmark công bằng về hiệu năng.

### 10.4. Kiểm tra thay đổi theo thời gian

Trong namespace thử nghiệm, bổ sung các lượt sau, mỗi lượt chỉ thay một yếu tố:

1. Thêm một replica backend: sau hội tụ, POD có thể quan sát thêm ứng viên endpoint; SERVICE vẫn có thể chỉ có một ứng viên Service.
2. Cho một backend không Ready: đối chiếu cập nhật nguồn endpoint và request sau một khoảng hội tụ có giới hạn.
3. Đảo thứ tự cổng Service nhưng giữ tên `http`: kết quả nghiệp vụ phải giữ đúng khi đã cấu hình tên cổng rõ ràng.
4. Đặt `port-name` không tồn tại trong ca SERVICE nhiều cổng: test phải phát hiện chọn nhầm hoặc fallback, thay vì báo xanh chỉ vì health endpoint trả 200.
5. Đặt sai domain cụm ở caller SERVICE: xác minh lỗi thuộc lớp dựng tên/DNS, rồi phục hồi cấu hình.

Mọi thời hạn hội tụ cần xét cache discovery, cache loadbalancer và kết nối đang mở. Không dùng một lần đọc ngay sau thay đổi làm kết luận cuối cùng, cũng không retry vô hạn.

## 11. Vì sao phân phối request có thể khác kỳ vọng?

### 11.1. Mode không đồng nghĩa với thuật toán

Spring Cloud LoadBalancer dùng danh sách từ `ServiceInstanceListSupplier` và một thuật toán chọn instance; framework có các implementation như round-robin và random. Cách tùy biến thuật toán là một quyết định riêng với mode Kubernetes. [Cơ chế Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html).

Chọn SERVICE không tự bật một thuật toán ngẫu nhiên ở Spring. Chọn POD cũng không tự tạo chính sách canary dựa trên label. Muốn dùng metadata cho routing, phải có dữ liệu đúng và supplier/thuật toán thực hiện chính sách đó.

### 11.2. Kết nối lâu dài ảnh hưởng đường Service

Với Service dùng cơ chế chuyển tiếp ở lớp mạng, backend thường được gắn với kết nối theo cách dataplane quản lý. Nhiều request HTTP dùng lại cùng một kết nối có thể tiếp tục đến cùng backend. HTTP/2 còn có thể đưa nhiều stream trên một kết nối.

Do đó, thấy SERVICE gửi nhiều request liên tiếp đến một Pod chưa đủ chứng minh Service hỏng hoặc Spring đang dùng POD. Cần xét connection pool, giao thức, session affinity và chính sách Service thực tế. [Virtual IP và Service proxy của Kubernetes](https://kubernetes.io/docs/reference/networking/virtual-ips/).

Khi đo phân phối, ghi rõ số kết nối, thời gian chạy, concurrency, retry và cấu hình affinity. Nếu cố ý tắt keep-alive để khảo sát, ghi rõ đây là biến thể kiểm thử; không dùng kết quả đó để mô tả mặc định mọi workload.

### 11.3. Đường trực tiếp có thể khác chính sách Service

Một request đến Pod IP không mặc nhiên đi qua các chính sách chỉ áp dụng trên đường VIP Service. Ngược lại, mesh hoặc proxy có thể can thiệp cả đường Pod lẫn Service. Trước khi kết luận POD bỏ qua một lớp mạng, kiểm tra kiến trúc thực tế.

Không cộng cơ học “một lần Spring chia tải” và “một lần Kubernetes chia tải” rồi suy ra phân phối đều hơn. Trong SERVICE với một ứng viên, Spring không có tập Pod để chia đều ở tầng đó.

## 12. Các giới hạn dễ gây hiểu nhầm

### 12.1. Headless không trở thành ClusterIP nhờ mode

Với Service headless, DNS có thể trả các địa chỉ endpoint thay vì VIP. Nếu tên Service cuối cùng phân giải ra Pod IP mà SERVICE vẫn dựng cổng Service 80, trong khi Pod chỉ nghe 8080, đường gọi có thể không hoạt động như ví dụ ClusterIP.

Cần hợp đồng cổng phù hợp cho loại Service đó và kiểm thử trên release đang dùng. Không coi headless là cách thay thế trong suốt cho ClusterIP trong mọi cấu hình SERVICE.

### 12.2. Nhiều namespace có thể làm sai ranh giới môi trường

Nếu bật tìm toàn namespace, các Service cùng tên ở nhiều môi trường có thể cùng lọt vào tập ứng viên. POD có nguy cơ gộp endpoint; SERVICE có nguy cơ tạo các đích DNS thuộc nhiều namespace.

Ưu tiên phạm vi namespace rõ ràng cho mỗi caller. Không mặc định namespace của caller luôn là namespace duy nhất được tìm nếu cấu hình đã chỉ định phạm vi rộng hơn.

### 12.3. Đổi mode qua ConfigMap không bảo đảm đổi bean tức thời

Mode có thể tham gia điều kiện tạo supplier và các bean lúc khởi động. Cập nhật ConfigMap hoặc nhận thông báo từ Configuration Watcher không tự chứng minh graph bean đã chuyển từ POD sang SERVICE.

Khi release không cam kết đổi mode động, cập nhật cấu hình rồi rollout caller; sau đó quan sát lại đích được chọn. Giá trị mới trong một endpoint xem cấu hình chưa đủ chứng minh request đã đi qua supplier mới.

Secret dùng cho credential và ConfigMap dùng cho cấu hình không cần đưa vào quá trình chọn mode nếu bài toán không yêu cầu. Tách phép kiểm tra đã nhận cấu hình khỏi phép kiểm tra đường gọi và quyền truy cập dữ liệu discovery.

### 12.4. Không tự chuyển sang retry an toàn

Hai chế độ đều có thể gặp timeout hoặc backend biến mất sau khi chọn. Retry là chính sách khác, cần giới hạn thời gian và xét tính idempotent của thao tác. Đặc biệt, không lặp lại một request tạo dữ liệu chỉ vì lần gọi trước timeout mà chưa biết backend đã xử lý hay chưa.

## 13. Chọn chế độ theo nhu cầu và bằng chứng

| Nhu cầu | Hướng đánh giá |
| --- | --- |
| Cần chọn riêng instance bằng dữ liệu discovery hoặc chính sách ở ứng dụng | Xem xét POD và cấu hình supplier/thuật toán thực sự đáp ứng yêu cầu |
| Muốn đích của client ở mức Service, giữ việc chuyển tới backend cho đường Service | Xem xét SERVICE nếu release và kiểu Service hỗ trợ phù hợp |
| Chỉ cần gọi một tên Service ổn định, không cần abstraction discovery | Đánh giá HTTP client thuần DNS trước khi thêm Kubernetes loadbalancer |
| Có TLS, mesh hoặc chính sách mạng theo Service | Đối chiếu đường kết nối và nhận diện đích trước khi chọn |
| Chưa xác định release hỗ trợ SERVICE | Xác minh dependency, thuộc tính và auto-configuration; không dùng cấu hình theo suy đoán |

Khi chẩn đoán, đi theo thứ tự bằng chứng: bản phát hành và dependency, bean/client đang hoạt động, danh sách ứng viên, host/cổng được chọn, DNS/mạng/TLS, cuối cùng là phản hồi nghiệp vụ. Một kết quả 200 hoặc một giá trị `mode` đứng riêng không đủ chứng minh toàn bộ chuỗi.

Một quyết định triển khai nên ghi lại mode, phạm vi namespace, cách chọn cổng, loại Service, nguồn discovery, các lớp cache và lý do cần cân bằng tải phía ứng dụng. Nhờ đó đội vận hành có thể giải thích đường đi của request và chỉ sử dụng những tính năng Spring Cloud Kubernetes thực sự cần.
