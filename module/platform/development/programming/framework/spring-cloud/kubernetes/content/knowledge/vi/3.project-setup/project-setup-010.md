# Tạo dự án tối thiểu và xác minh kết nối đầu tiên

## 1. Mục tiêu

Một dự án Spring Cloud Kubernetes nên bắt đầu bằng một đường đi nhỏ có thể kiểm chứng:

1. Ứng dụng Spring khởi động được.
2. Ứng dụng cung cấp HTTP endpoint và health endpoint.
3. Kubernetes Service cung cấp tên truy cập ổn định.
4. Một client trong cluster gọi được Service qua DNS.
5. Người học phân biệt được lỗi ứng dụng, Service, DNS và mạng.

Sau khi đường cơ bản hoạt động, mới quyết định có cần DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer hoặc Configuration Watcher. Cách này giúp dependency, manifest và RBAC có lý do rõ ràng.

Ví dụ dùng hai workload:

- orders cung cấp API HTTP;
- checkout gọi orders bằng tên Service.

~~~text
+-------------------+       http://orders:8080       +------------------+
| checkout Pod      | ----------------------------> | orders Service   |
| Spring HTTP client|                               | ClusterIP        |
+-------------------+                               +--------+---------+
                                                            |
                                                       EndpointSlice
                                                            |
                                                            v
                                                    +---------------+
                                                    | orders Pod    |
                                                    +---------------+
~~~

DNS phân giải tên Service; Service chuyển kết nối đến Pod sẵn sàng. checkout không cần liệt kê Pod để gửi request.

## 2. Chọn dependency với phạm vi nhỏ

| Khả năng | Thành phần cần cân nhắc | Bắt buộc ở bước đầu? |
| --- | --- | --- |
| HTTP server | Spring Web hoặc starter tương đương | Có |
| Health endpoint | Spring Boot Actuator | Nên có |
| HTTP client | RestClient, WebClient hoặc client tương đương | Có cho checkout |
| Gọi Service qua DNS | DNS Kubernetes và HTTP client | Có |
| Discovery bằng Kubernetes API | Spring Cloud Kubernetes Discovery | Chưa |
| Đọc ConfigMap/Secret qua API | Spring Cloud Kubernetes Config | Chưa |
| Client-side load balancing | Spring Cloud LoadBalancer | Chưa |
| Theo dõi cấu hình runtime | Watcher hoặc reload integration | Chưa |

Tên starter và version phải khớp với Spring Boot, Spring Cloud và Spring Cloud Kubernetes được quản lý trong dự án. Không sao chép version ngẫu nhiên giữa các release train.

Nếu checkout chỉ gọi http://orders:8080, thêm discovery sẽ tăng dependency, cấu hình và quyền RBAC mà chưa tạo ra giá trị tương ứng. Kubernetes Service và DNS đã giải quyết việc định địa chỉ.

## 3. Tạo ứng dụng orders

### 3.1. Lớp khởi động và controller

Cấu trúc logic tối thiểu:

~~~text
orders/
  src/main/java/.../OrdersApplication.java
  src/main/java/.../OrdersController.java
  src/main/resources/application.yml
~~~

Lớp khởi động:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Controller dùng để kiểm tra đường kết nối:

~~~java
package com.example.orders;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {

    @GetMapping("/orders/{id}")
    Map<String, Object> findOrder(@PathVariable String id) {
        return Map.of(
                "id", id,
                "status", "CONFIRMED",
                "source", "orders");
    }
}
~~~

Endpoint này chỉ là điểm kiểm tra. Ứng dụng thật cần DTO, validation, authentication và xử lý lỗi theo hợp đồng API.

### 3.2. Cổng và health endpoint

~~~yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
~~~

Khi dùng Actuator readiness và liveness, cần kiểm tra endpoint thật sự được cung cấp và không bị security config chặn. Nếu management server chạy cổng riêng, phải khai báo đúng cổng trong container và probe.

Khai báo containerPort không tự làm process listen trên cổng. Ứng dụng Spring vẫn phải bind đúng server.port hoặc cổng management.

## 4. Tạo ứng dụng checkout

### 4.1. Cấu hình URL

Checkout nhận URL orders từ property:

~~~yaml
orders:
  base-url: http://orders:8080
~~~

Trong manifest, có thể map biến ORDERS_BASE_URL vào property theo quy tắc binding của Spring Boot. Không ghi IP Pod vào cấu hình vì IP có thể đổi khi rollout, reschedule hoặc scale. Tên Service là địa chỉ ổn định hơn.

### 4.2. Cấu hình type-safe và HTTP client

Dùng Configuration Properties để tránh ràng buộc vào một placeholder cụ thể:

~~~java
package com.example.checkout;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "orders")
public record OrdersProperties(String baseUrl) {
}
~~~

Cần đăng ký record này bằng cơ chế enable configuration properties phù hợp với dự án. Tạo RestClient:

~~~java
package com.example.checkout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class OrdersClientConfiguration {

    @Bean
    RestClient ordersRestClient(
            RestClient.Builder builder,
            OrdersProperties properties) {
        return builder.baseUrl(properties.baseUrl()).build();
    }
}
~~~

Gateway gọi orders:

~~~java
package com.example.checkout;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class OrdersGateway {

    private final RestClient client;

    public OrdersGateway(
            @Qualifier("ordersRestClient") RestClient client) {
        this.client = client;
    }

    public String findOrder(String id) {
        return client.get()
                .uri("/orders/{id}", id)
                .retrieve()
                .body(String.class);
    }
}
~~~

Controller để kiểm tra từ bên ngoài checkout:

~~~java
package com.example.checkout;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CheckoutController {

    private final OrdersGateway ordersGateway;

    public CheckoutController(OrdersGateway ordersGateway) {
        this.ordersGateway = ordersGateway;
    }

    @GetMapping("/checkout/orders/{id}")
    String order(@PathVariable String id) {
        return ordersGateway.findOrder(id);
    }
}
~~~

Ví dụ này không dùng service ID qua LoadBalancer. Host orders được xử lý như hostname thông thường bởi DNS trong Pod.

Client thật cần timeout kết nối, timeout đọc response, giới hạn thời gian nghiệp vụ, xử lý status code và retry có điều kiện. Retry thao tác tạo dữ liệu có thể gây trùng nếu API không idempotent.

## 5. Manifest cho orders

### 5.1. Deployment

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
  namespace: shop
spec:
  replicas: 1
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
    spec:
      containers:
        - name: orders
          image: registry.example.com/orders:1.0.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

Image là placeholder và phải được thay bằng image thực tế. Readiness giúp Service tránh gửi traffic đến Pod chưa sẵn sàng. Liveness chỉ nên kiểm tra trạng thái mà restart có khả năng cải thiện. Nếu ứng dụng khởi động lâu, cân nhắc startupProbe thay vì đặt liveness quá gắt.

### 5.2. Service

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: orders
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: orders
  ports:
    - name: http
      port: 8080
      targetPort: http
~~~

Quan hệ cần kiểm tra:

- Service selector app: orders phải khớp label trong Pod template.
- port 8080 là cổng client gọi trên Service.
- targetPort http tham chiếu cổng container có tên http.
- Service name orders tạo tên DNS trong namespace.
- Pod chưa Ready không nên là backend sẵn sàng cho traffic thông thường.

Selector sai có thể làm DNS vẫn phân giải được nhưng Service không có endpoint.

## 6. Manifest cho checkout

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout
  namespace: shop
spec:
  replicas: 1
  selector:
    matchLabels:
      app: checkout
  template:
    metadata:
      labels:
        app: checkout
    spec:
      containers:
        - name: checkout
          image: registry.example.com/checkout:1.0.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: ORDERS_BASE_URL
              value: http://orders:8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
~~~

Nếu cần gọi checkout từ một client trong cluster:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: checkout
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: checkout
  ports:
    - name: http
      port: 8080
      targetPort: http
~~~

Client trong namespace shop có thể gọi http://checkout:8080. Client ở namespace khác có thể dùng tên có namespace nếu DNS và NetworkPolicy cho phép.

## 7. Xác minh từng lớp

Các lệnh sau là ví dụ cho người vận hành có quyền phù hợp. Bài không chạy các lệnh này.

### 7.1. Kiểm tra Pod, Service và endpoint

~~~bash
kubectl -n shop get pods -l app=orders
kubectl -n shop get service orders
kubectl -n shop get endpointslices -l kubernetes.io/service-name=orders
~~~

Kiểm tra:

- Pod có Running và Ready không?
- Service selector có khớp label không?
- EndpointSlice có địa chỉ backend không?
- Cổng endpoint có khớp targetPort không?

Nếu Pod Running nhưng không Ready, tập endpoint có thể rỗng hoặc không dùng Pod đó cho traffic.

### 7.2. Kiểm tra DNS từ checkout

Nếu image có nslookup:

~~~bash
kubectl -n shop exec deploy/checkout -- nslookup orders
~~~

Phải kiểm tra từ context của Pod checkout; kết quả DNS trên laptop không đại diện cho DNS nội bộ cluster. Image tối giản có thể không có nslookup. Khi đó dùng công cụ debug phù hợp hoặc Pod chẩn đoán riêng.

### 7.3. Kiểm tra HTTP

Nếu container có curl:

~~~bash
kubectl -n shop exec deploy/checkout -- curl --connect-timeout 2 --max-time 5 http://orders:8080/orders/123
~~~

HTTP 404 vì order không tồn tại vẫn chứng minh request đã đến ứng dụng. Nó khác với lỗi DNS, timeout hoặc connection refused.

Kiểm tra gateway của checkout:

~~~bash
kubectl -n shop exec deploy/checkout -- curl --connect-timeout 2 --max-time 5 http://localhost:8080/checkout/orders/123
~~~

Sau đó đối chiếu log orders để xác nhận request downstream.

## 8. Phân loại lỗi kết nối đầu tiên

| Hiện tượng | Ý nghĩa có thể có | Kiểm tra đầu tiên |
| --- | --- | --- |
| Không phân giải được orders | Sai tên, namespace hoặc DNS | Service name, namespace, DNS policy |
| DNS có kết quả nhưng timeout | Mạng, policy, endpoint hoặc backend | EndpointSlice, NetworkPolicy, readiness |
| Connection refused | Sai cổng hoặc không có process listen | targetPort, server.port và log |
| HTTP 404 từ orders | Request đã tới server nhưng path hoặc dữ liệu sai | Controller mapping và id |
| HTTP 401/403 | API yêu cầu xác thực | Token, credentials và security config |
| HTTP 5xx | Ứng dụng đích hoặc dependency lỗi | Log, health và trace |
| Checkout lỗi trước downstream | Binding property hoặc gateway lỗi | orders.base-url và exception |
| Lúc được lúc lỗi | Replica không đồng nhất hoặc rollout | Image, config và readiness từng Pod |

Không sửa RBAC khi lỗi chỉ là sai port. RBAC liên quan đến Kubernetes API; nó không làm HTTP client hoặc DNS tự đúng.

## 9. Khi nào thêm Spring Cloud Kubernetes?

### DiscoveryClient

Thêm khi ứng dụng cần liệt kê service, biết instance và metadata, hoặc cần một abstraction discovery cho nhiều môi trường. Nếu discovery dựa trên Kubernetes API, cần ServiceAccount và quyền resource đúng. Không cấp quyền toàn cluster chỉ để gọi một Service.

### Config integration

Thêm khi ứng dụng cần đọc ConfigMap hoặc Secret trực tiếp theo integration, thay vì chỉ inject environment hoặc volume. Cần quyết định cấu hình được đọc lúc startup hay runtime, cấu hình sai xử lý thế nào và Secret có thể xuất hiện ở log hoặc actuator hay không.

### Spring Cloud LoadBalancer

Thêm khi client phải chọn instance theo policy riêng. Cần biết nguồn instance trả về địa chỉ Pod, Service, gateway hay danh sách cache. Nếu chỉ gọi một ClusterIP ổn định, LoadBalancer có thể là lớp dư thừa.

### Configuration Watcher

Thêm khi thay đổi cấu hình phải có hiệu lực trong process đang chạy. Cần thiết kế validation, refresh, reconnect, rollback và behavior khi watcher mất kết nối. Nếu rollout là cách cập nhật được chấp nhận, watcher chưa chắc cần.

## 10. ConfigMap, Secret và RBAC

ConfigMap phù hợp dữ liệu không nhạy cảm:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: checkout-settings
  namespace: shop
data:
  ORDERS_BASE_URL: http://orders:8080
  CHECKOUT_TIMEOUT_MS: "800"
~~~

Có thể inject bằng envFrom hoặc key cụ thể. Environment của process không tự đổi khi ConfigMap thay đổi; cần rollout hoặc cơ chế đọc lại.

Secret dành cho credential hoặc token:

~~~yaml
env:
  - name: ORDERS_API_TOKEN
    valueFrom:
      secretKeyRef:
        name: orders-client
        key: token
~~~

Không đưa Secret vào image, log hoặc endpoint actuator. Rotation cần được thiết kế; giá trị mới không tự thay đổi trong process nếu không có cơ chế reload hoặc rollout.

Nếu checkout chỉ gọi http://orders:8080, không cần đọc Service hay Pod qua Kubernetes API để gửi HTTP. Có thể không cấp quyền list/watch Pod cho ServiceAccount của checkout. Chỉ khi bật discovery, config integration hoặc watcher dựa trên API mới cần RBAC tương ứng.

RBAC và NetworkPolicy là hai lớp khác nhau: có quyền đọc Service không bảo đảm mở được TCP đến backend; có network access không đồng nghĩa đọc được resource qua API.

## 11. Kiểm tra nhiều replica

Sau khi baseline với một replica hoạt động, tăng orders lên ba:

~~~yaml
spec:
  replicas: 3
~~~

Giữ nguyên URL checkout và quan sát:

- tên Service không đổi;
- IP Pod có thể thay đổi;
- EndpointSlice thay đổi theo readiness;
- rollout không đưa Pod chưa Ready vào traffic thông thường;
- request có thể phân bố lệch do connection pool và keep-alive.

Không kết luận mỗi request sẽ chia đều tuyệt đối. Service cân bằng trên đường dữ liệu và kết nối; client HTTP có thể tái sử dụng connection.

## 12. Checklist dự án tối thiểu

- Ứng dụng orders khởi động và health endpoint hoạt động.
- Deployment label khớp Service selector.
- Probe trỏ đúng path, port và scheme.
- Service có đúng port và targetPort.
- checkout nhận đúng base URL orders.
- DNS được kiểm tra từ Pod checkout.
- Lỗi DNS, kết nối và HTTP status được phân biệt.
- HTTP client có timeout và retry phù hợp.
- ConfigMap và Secret có chính sách cập nhật.
- Đường gọi DNS không có RBAC thừa.
- Discovery, config, load balancing hoặc watcher chỉ được thêm khi có nhu cầu cụ thể.

Checklist tạo baseline có thể lặp lại. Khi thêm một integration làm hỏng baseline, phạm vi chẩn đoán nhỏ hơn.

## 13. Kết luận

Dự án Spring Cloud Kubernetes tối thiểu nên bắt đầu bằng HTTP endpoint, health endpoint, Deployment, Service và một client gọi Service qua DNS. Đường đi này xác minh được nền tảng Kubernetes mà chưa cần bật mọi integration.

DiscoveryClient dành cho nhu cầu thông tin service hoặc instance. ConfigMap và Secret có thể đi qua environment hoặc volume nếu cấu hình lúc startup là đủ; Config integration và Configuration Watcher dành cho nhu cầu đọc hoặc cập nhật runtime cụ thể. Spring Cloud LoadBalancer chỉ cần khi client phải chọn instance theo policy riêng.

Tạo dự án nhỏ, kiểm tra từng lớp và giữ RBAC tối thiểu giúp quá trình tích hợp Spring Cloud Kubernetes dễ giải thích, dễ chẩn đoán và dễ mở rộng.
