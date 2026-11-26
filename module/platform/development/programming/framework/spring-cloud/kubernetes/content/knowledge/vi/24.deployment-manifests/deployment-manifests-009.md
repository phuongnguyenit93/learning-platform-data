# Triển khai Discovery Server và Configuration Watcher khi cần

## Mục tiêu bài học

Trong chương **Manifest triển khai** của **SPRING_CLOUD_KUBERNETES**, không phải ứng dụng nào cũng cần thêm Discovery Server hoặc Configuration Watcher. Hai thành phần này phục vụ hai nhu cầu khác nhau và tạo thêm trách nhiệm vận hành, phân quyền, theo dõi sức khỏe.

Sau bài học, bạn có thể:

- Quyết định khi nào dùng Kubernetes Service/DNS, DiscoveryClient trực tiếp hoặc HTTP Discovery Server.
- Triển khai Discovery Server với ServiceAccount và quyền đọc danh mục dịch vụ trong phạm vi cần thiết.
- Triển khai Configuration Watcher khi ứng dụng thật sự cần refresh mà không thay Pod.
- Kết nối đúng nhãn nguồn cấu hình, tên Service, instance ứng dụng và endpoint quản trị.
- Kiểm tra từng replica thay vì kết luận từ một lần gọi qua Service.
- Nhận diện giới hạn refresh, độ trễ cập nhật volume và yêu cầu bảo vệ đường quản trị.

Bài dùng namespace lab `sck-controllers-lab`. Các manifest là ví dụ để người học lưu và áp dụng trong lab; cần thay mọi image digest placeholder trước khi chạy. Không có Secret thật và không cần cấp quyền đọc Secret cho các thành phần trong ví dụ chính.

## 1. Bắt đầu từ nhu cầu, không bắt đầu từ tên thành phần

| Nhu cầu thực tế | Lựa chọn ban đầu | Có cần thêm controller/server? |
| --- | --- | --- |
| Gọi một dịch vụ bằng tên ổn định | Kubernetes Service và DNS | Không nhất thiết |
| Ứng dụng cần danh sách instance, metadata qua DiscoveryClient | Client Fabric8 hoặc Kubernetes Java Client | Không cần Discovery Server nếu ứng dụng đọc API trực tiếp |
| Cần DiscoveryClient nhưng muốn tập trung quyền đọc API ở một dịch vụ | HTTP DiscoveryClient và Discovery Server | Cần Discovery Server |
| Thay cấu hình theo bản phát hành, chấp nhận rolling update | Tài nguyên cấu hình có phiên bản và rollout | Không cần Watcher |
| Cần đổi một số cấu hình trong khi giữ tiến trình và Pod | Refresh được kiểm chứng và Configuration Watcher | Có thể cần Watcher |
| Đã dùng Spring Cloud Bus cho refresh | Đánh giá tích hợp messaging của Watcher | Cần xem cả broker và phạm vi sự kiện |

Một ứng dụng có thể dùng:

- Không thành phần nào: gọi Service bằng DNS, nạp cấu hình khi khởi động.
- Chỉ Discovery Server: lấy thông tin instance qua HTTP, cập nhật cấu hình bằng rollout.
- Chỉ Configuration Watcher: đọc cấu hình từ volume, để Watcher dùng discovery trực tiếp qua Kubernetes API.
- Cả hai: khi hai nhu cầu độc lập đều tồn tại.

Spring Cloud LoadBalancer có thể sử dụng dữ liệu instance trong ứng dụng gọi dịch vụ. Nó không tự tạo ra yêu cầu phải có Discovery Server nếu cơ chế discovery đang dùng đã đáp ứng được.

## 2. Hai luồng dữ liệu khác nhau

### 2.1. Discovery Server cung cấp thông tin, không chuyển tiếp request nghiệp vụ

```text
Ứng dụng gọi
    |
    | HTTP DiscoveryClient lấy danh sách instance
    v
Discovery Server ── ServiceAccount/RBAC ──> Kubernetes API
    |
    | trả địa chỉ, cổng và metadata
    v
Ứng dụng gọi ── HTTP nghiệp vụ ──> instance hoặc dịch vụ đích
```

Discovery Server không phải Eureka Server dù ví dụ thường dùng cổng `8761`. Nó cũng không phải API gateway hoặc proxy tự vận chuyển mọi request đến dịch vụ đích.

Ứng dụng bên ngoài cluster lấy được địa chỉ Pod không có nghĩa nó truy cập được địa chỉ đó. Vẫn phải giải quyết routing, firewall và chính sách mạng.

Theo [tài liệu Discovery Server](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-discoveryserver.html), HTTP API gồm các đường như `/apps` và `/apps/{name}`, phục vụ HTTP DiscoveryClient của Spring Cloud Kubernetes.

### 2.2. Watcher gửi tín hiệu, không đẩy giá trị mới vào mọi bean

```text
ConfigMap thay đổi
    |
    +── kubelet đồng bộ nội dung volume tới Pod
    |
    +── Watcher nhận sự kiện
              |
              | tìm ServiceInstance cần tác động
              v
         POST endpoint refresh trên từng instance
              |
              v
         Spring đọc lại nguồn và refresh phần được hỗ trợ
```

Có hai quá trình cùng diễn ra: dữ liệu tới Pod và tín hiệu refresh tới ứng dụng. Chúng không tự tạo thành một giao dịch.

Watcher có HTTP implementation và messaging implementation. Ví dụ chính dùng HTTP; Watcher tự dùng DiscoveryClient Kubernetes để tìm instance nên không cần đi qua Discovery Server. Xem [Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

## 3. Phạm vi và giả định của lab

Ví dụ tập trung vào một namespace, ứng dụng JVM, ConfigMap không nhạy cảm và HTTP refresh.

Trước khi triển khai:

1. Chọn Spring Boot, Spring Cloud release train và Spring Cloud Kubernetes tương thích.
2. Giữ HTTP DiscoveryClient và Discovery Server ở phiên bản tương thích; ưu tiên cùng phiên bản Spring Cloud Kubernetes.
3. Chọn image controller đúng phiên bản đã kiểm tra và ghim digest.
4. Dùng cluster hỗ trợ EndpointSlice; các controller dưới đây bật đường discovery này.
5. Dùng CNI thực thi NetworkPolicy cho phần lab mở endpoint refresh.

Các thuộc tính minh họa được đối chiếu với tài liệu Spring Cloud Kubernetes 5.1. Không giả định cấu hình HA hoặc property của thế hệ này có mặt trong mọi bản cũ.

Các quyền dưới đây có chủ đích:

| Danh tính | Đọc danh mục dịch vụ | Đọc ConfigMap | Đọc Secret |
| --- | --- | --- | --- |
| `discovery-server` | Có, trong namespace lab | Không | Không |
| `config-watcher` | Có, để tìm instance | Có, để theo dõi nguồn | Không |
| `catalog-runtime` | Không, chỉ đọc volume | Không qua API | Không |

Việc mount ConfigMap vào ứng dụng không đòi hỏi cấp quyền API cho `catalog-runtime`. Trách nhiệm này khác với quyền của hai controller.

Tạo namespace bằng manifest `namespace.yml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: sck-controllers-lab
```

## 4. Triển khai Discovery Server khi cần HTTP discovery

### 4.1. ServiceAccount và RBAC riêng

Lưu bộ manifest ở phần này thành `discovery-server.yml`.

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: discovery-server
  namespace: sck-controllers-lab
automountServiceAccountToken: true
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: discovery-catalog-reader
  namespace: sck-controllers-lab
rules:
  - apiGroups: [""]
    resources: ["pods", "services"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: discovery-catalog-reader
  namespace: sck-controllers-lab
subjects:
  - kind: ServiceAccount
    name: discovery-server
    namespace: sck-controllers-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: discovery-catalog-reader
```

Role không có Secret, ConfigMap hoặc quyền sửa workload. Nó chỉ có hiệu lực trong namespace lab.

Ví dụ bật `spring.cloud.kubernetes.discovery.use-endpoint-slices=true` nên cấp quyền trên `discovery.k8s.io/endpointslices`. Nếu chọn đường Endpoints của phiên bản khác, điều chỉnh cả property lẫn quyền nguồn tương ứng. Xem [lựa chọn EndpointSlice trong DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Không thêm `cluster-admin` khi gặp lỗi 403. Kiểm tra tài nguyên và namespace trong lỗi, rồi đối chiếu đúng lời gọi của controller.

### 4.2. Deployment và Service

Nối tiếp cùng tệp `discovery-server.yml`:

```yaml
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k8s-discovery
  namespace: sck-controllers-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: k8s-discovery
  template:
    metadata:
      labels:
        app: k8s-discovery
    spec:
      serviceAccountName: discovery-server
      containers:
        - name: server
          image: springcloud/spring-cloud-kubernetes-discoveryserver@sha256:REPLACE_WITH_VERIFIED_DIGEST
          ports:
            - name: http
              containerPort: 8761
          env:
            - name: SERVER_PORT
              value: "8761"
            - name: SPRING_CLOUD_KUBERNETES_DISCOVERY_NAMESPACES_0
              value: sck-controllers-lab
            - name: SPRING_CLOUD_KUBERNETES_DISCOVERY_USE_ENDPOINT_SLICES
              value: "true"
            - name: MANAGEMENT_ENDPOINT_HEALTH_PROBES_ENABLED
              value: "true"
            - name: MANAGEMENT_ENDPOINT_HEALTH_GROUP_LIVENESS_INCLUDE
              value: livenessState
            - name: MANAGEMENT_ENDPOINT_HEALTH_GROUP_READINESS_INCLUDE
              value: readinessState,kubernetes
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              memory: 512Mi
---
apiVersion: v1
kind: Service
metadata:
  name: k8s-discovery
  namespace: sck-controllers-lab
spec:
  type: ClusterIP
  selector:
    app: k8s-discovery
  ports:
    - name: http
      port: 8761
      targetPort: http
```

Service tạo địa chỉ ổn định `http://k8s-discovery.sck-controllers-lab.svc:8761`. Không tạo Ingress công khai chỉ để ứng dụng trong cluster đọc discovery.

Ví dụ giữ liveness ở trạng thái tiến trình, readiness có thêm health indicator Kubernetes của image controller. Cần xác minh nhóm health với image đã ghim; probe xanh chưa thay thế kiểm tra `/apps` và khả năng cập nhật danh mục.

Hai replica tăng khả năng phục vụ HTTP nhưng mỗi replica vẫn có dữ liệu quan sát riêng và độ trễ cập nhật. Không coi kết quả hai cache là nhất quán tức thời.

Thông tin discovery có thể chứa địa chỉ nội bộ và metadata. Chỉ cấp quyền gọi cho những consumer cần dùng; không đưa thông tin nhạy cảm vào Service annotation được công bố qua metadata.

### 4.3. Cấu hình ứng dụng gọi qua HTTP

Trong ứng dụng caller, dùng starter HTTP được quản lý bằng BOM của dự án:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-discoveryclient</artifactId>
</dependency>
```

Cấu hình:

```yaml
spring:
  application:
    name: order-service
  cloud:
    kubernetes:
      client:
        namespace: sck-controllers-lab
      discovery:
        discovery-server-url: http://k8s-discovery.sck-controllers-lab.svc:8761
```

Property `discovery-server-url` được liệt kê trong [Common application properties](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

Không thêm đồng thời các starter discovery trực tiếp nếu không có thiết kế rõ để chọn implementation. Caller chỉ dùng HTTP discovery không cần quyền đọc catalog Kubernetes cho nhu cầu này; kiểm tra các tích hợp khác trước khi tắt mount ServiceAccount token.

Phạm vi namespace của HTTP discovery được cấu hình ở server. Đặt namespace trong caller không tự mở rộng dữ liệu mà server được phép đọc.

Kubernetes quản lý đăng ký dịch vụ bằng Service và endpoint. Một ứng dụng không cần tự đăng ký kiểu Eureka để Discovery Server nhìn thấy nó.

## 5. Chuẩn bị ứng dụng có thể refresh

Lab Watcher độc lập với phần Discovery Server. Ứng dụng `catalog-service` chỉ cần Web, Actuator và Spring Cloud Context, chẳng hạn qua `spring-cloud-starter`. Không cần starter discovery cho chính ứng dụng nếu nó không sử dụng DiscoveryClient.

### 5.1. Tạo đường kiểm tra giá trị không nhạy cảm

Đặt lớp sau dưới package mà `@SpringBootApplication` quét được:

```java
package com.example.catalog;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RefreshScope
public class MessageController {

    private final String message;
    private final String podName;

    public MessageController(
            @Value("${demo.message}") String message,
            @Value("${POD_NAME:unknown}") String podName) {
        this.message = message;
        this.podName = podName;
    }

    @GetMapping("/demo/message")
    public Map<String, String> message() {
        return Map.of("message", message, "pod", podName);
    }
}
```

`@RefreshScope` cho phép đối tượng đích được tạo lại sau refresh. Lần gọi tiếp theo đọc giá trị đã được Spring nạp lại; đây không phải cơ chế tự thay mọi trường Java đang tồn tại. Xem [Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html#refresh-scope).

Không dùng endpoint minh họa để trả token, mật khẩu hoặc toàn bộ Environment.

### 5.2. Cấu hình cố định trong ứng dụng

```yaml
spring:
  application:
    name: catalog-service

server:
  port: 8080

management:
  server:
    port: 9090
  endpoints:
    web:
      exposure:
        include: health,refresh
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
```

Đây là ứng dụng lab JVM có Spring Cloud Context, chưa bật Spring Security. Cổng quản trị `9090` được tách khỏi cổng nghiệp vụ `8080` và bị giới hạn bằng NetworkPolicy ở phần sau.

Trong môi trường thật, tích hợp xác thực/mTLS cho đường quản trị và cấu hình cơ chế gửi tương thích của Watcher hoặc lớp proxy quản trị. Expose endpoint chỉ làm nó khả dụng; không tự tạo thông tin xác thực cho Watcher.

## 6. Nguồn cấu hình, Service và các Pod đích

### 6.1. ConfigMap có nhãn theo dõi và đích refresh

Lưu thành `catalog-settings.yml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-settings
  namespace: sck-controllers-lab
  labels:
    spring.cloud.kubernetes.config: "true"
  annotations:
    spring.cloud.kubernetes.configmap.apps: "catalog-service"
data:
  application.yml: |
    demo:
      message: "Gia tri ban dau"
```

Ví dụ cố ý dùng tên ConfigMap khác tên ứng dụng để minh họa annotation đích. Không có `immutable: true` vì lab cần cập nhật dữ liệu cùng tài nguyên.

Ba phần phải được hiểu riêng:

- Label `spring.cloud.kubernetes.config: "true"` giúp Watcher chọn nguồn cần theo dõi.
- Annotation `spring.cloud.kubernetes.configmap.apps` nêu tên ứng dụng đích trong discovery.
- Nội dung `data.application.yml` cung cấp giá trị khi ứng dụng đọc nguồn.

Thêm annotation đích không tự tạo volume hoặc khiến ứng dụng đọc ConfigMap. Thêm label theo dõi cũng không cấp thêm quyền RBAC cho Watcher.

### 6.2. Deployment và Service của ứng dụng

Lưu thành `catalog-app.yml`, thay image placeholder bằng image ứng dụng đã có lớp và cấu hình ở trên:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: catalog-runtime
  namespace: sck-controllers-lab
automountServiceAccountToken: false
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
  namespace: sck-controllers-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog-service
  template:
    metadata:
      labels:
        app: catalog-service
        discovery-client: "true"
    spec:
      serviceAccountName: catalog-runtime
      automountServiceAccountToken: false
      containers:
        - name: app
          image: registry.example.com/catalog-service@sha256:REPLACE_WITH_VERIFIED_DIGEST
          ports:
            - name: http
              containerPort: 8080
            - name: management
              containerPort: 9090
          env:
            - name: SPRING_CONFIG_IMPORT
              value: "file:/etc/catalog/application.yml"
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
          volumeMounts:
            - name: settings
              mountPath: /etc/catalog
              readOnly: true
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: management
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: management
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: management
            periodSeconds: 10
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              memory: 512Mi
      volumes:
        - name: settings
          configMap:
            name: catalog-settings
            items:
              - key: application.yml
                path: application.yml
---
apiVersion: v1
kind: Service
metadata:
  name: catalog-service
  namespace: sck-controllers-lab
  annotations:
    boot.spring.io/actuator: "http://:9090/actuator"
spec:
  type: ClusterIP
  selector:
    app: catalog-service
  ports:
    - name: http
      port: 8080
      targetPort: http
```

Service chỉ công bố cổng nghiệp vụ. Annotation `boot.spring.io/actuator` cho HTTP Watcher biết cổng và đường quản trị khác mặc định; Watcher vẫn cần đi được tới cổng `9090` trên từng instance.

Nhãn Pod `discovery-client: "true"` ở đây chỉ dành cho ví dụ NetworkPolicy cho phép gọi Discovery Server. Nó không tự bật một DiscoveryClient trong Java; có thể bỏ nếu không thực hành HTTP discovery.

Không dùng `subPath` cho tệp ConfigMap trong bài này vì cần nhận đồng bộ nội dung volume. Cũng không kỳ vọng giá trị lấy qua biến môi trường thay đổi trong container đang chạy.

## 7. Triển khai Configuration Watcher độc lập

### 7.1. Quyền đọc ConfigMap và danh mục instance

Lưu thành `config-watcher.yml`:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: config-watcher
  namespace: sck-controllers-lab
automountServiceAccountToken: true
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: configuration-events-reader
  namespace: sck-controllers-lab
rules:
  - apiGroups: [""]
    resources: ["configmaps", "pods", "services"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: configuration-events-reader
  namespace: sck-controllers-lab
subjects:
  - kind: ServiceAccount
    name: config-watcher
    namespace: sck-controllers-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: configuration-events-reader
```

Quyền ConfigMap ở đây cho phép đọc dữ liệu của tài nguyên trong namespace, không chỉ nhìn metadata có nhãn phù hợp. Label filtering là tiêu chí xử lý sự kiện, không phải ranh giới cấp quyền.

Role không cấp quyền sửa Deployment để rollout và không cấp quyền đọc Secret. Bài dùng HTTP refresh nên Watcher không cần sửa workload.

### 7.2. Deployment một replica cho lab

Nối tiếp cùng tệp:

```yaml
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: config-watcher
  namespace: sck-controllers-lab
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: config-watcher
  template:
    metadata:
      labels:
        app: config-watcher
    spec:
      serviceAccountName: config-watcher
      containers:
        - name: watcher
          image: springcloud/spring-cloud-kubernetes-configuration-watcher@sha256:REPLACE_WITH_VERIFIED_DIGEST
          ports:
            - name: http
              containerPort: 8888
          env:
            - name: SERVER_PORT
              value: "8888"
            - name: SPRING_CLOUD_KUBERNETES_RELOAD_NAMESPACES_0
              value: sck-controllers-lab
            - name: SPRING_CLOUD_KUBERNETES_DISCOVERY_NAMESPACES_0
              value: sck-controllers-lab
            - name: SPRING_CLOUD_KUBERNETES_DISCOVERY_USE_ENDPOINT_SLICES
              value: "true"
            - name: SPRING_CLOUD_KUBERNETES_DISCOVERY_METADATA_ADD_ANNOTATIONS
              value: "true"
            - name: SPRING_CLOUD_KUBERNETES_SECRETS_ENABLED
              value: "false"
            - name: SPRING_CLOUD_KUBERNETES_RELOAD_MONITORING_SECRETS
              value: "false"
            - name: SPRING_CLOUD_KUBERNETES_CONFIGURATION_WATCHER_REFRESHDELAY
              value: "120000"
            - name: SPRING_CLOUD_KUBERNETES_CONFIGURATION_WATCHER_HA_ENABLED
              value: "false"
            - name: MANAGEMENT_ENDPOINT_HEALTH_PROBES_ENABLED
              value: "true"
            - name: MANAGEMENT_ENDPOINT_HEALTH_GROUP_LIVENESS_INCLUDE
              value: livenessState
            - name: MANAGEMENT_ENDPOINT_HEALTH_GROUP_READINESS_INCLUDE
              value: readinessState
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              memory: 512Mi
```

Watcher nhận sự kiện từ Kubernetes và chủ động gọi ứng dụng. Nó không cần một Service inbound để thực hiện hai việc đó; chỉ thêm ClusterIP nếu có consumer hoặc nhu cầu quan sát cần địa chỉ ổn định.

`Recreate` tránh hai bản Watcher chồng nhau trong lúc cập nhật lab khi chưa bật HA. Đổi lại có khoảng gián đoạn theo dõi. Đây không phải thiết kế HA production.

Readiness xanh chỉ chứng minh trạng thái đã chọn cho probe. Cần phép thử cập nhật cấu hình để kiểm tra chuỗi informer → discovery → refresh thực sự chạy.

### 7.3. Refresh delay không phải cam kết đồng bộ

`120000` có đơn vị mili giây, tức 120 giây. Đây là khoảng chờ mẫu trước khi phát tín hiệu, để volume có thời gian nhận dữ liệu mới.

Khoảng chờ không phải hàng rào xác nhận từng Pod đã thấy ConfigMap mới. Nếu cluster đồng bộ chậm hơn, Watcher có thể gửi refresh khi ứng dụng vẫn đọc tệp cũ.

Khi chẩn đoán, đối chiếu thời điểm cập nhật tài nguyên, thời điểm dữ liệu tới volume và thời điểm refresh. Chọn delay dựa trên quan sát cluster; nếu cần bảo đảm phiên bản chặt chẽ, thiết kế xác nhận phiên bản hoặc dùng rollout.

Ví dụ này chỉ đổi một khóa không nhạy cảm. Với Secret, còn phải đánh giá khả năng xoay thông tin truy cập và ảnh hưởng tới kết nối đang mở; không bật theo dõi Secret chỉ vì image hỗ trợ.

## 8. Giới hạn kết nối tới endpoint quản trị

Lưu thành `network-policies.yml`. Bộ policy dưới đây giả định không có policy khác mở rộng các đường vào tương ứng:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: catalog-application-and-management
  namespace: sck-controllers-lab
spec:
  podSelector:
    matchLabels:
      app: catalog-service
  policyTypes: ["Ingress"]
  ingress:
    - from:
        - podSelector: {}
      ports:
        - protocol: TCP
          port: 8080
    - from:
        - podSelector:
            matchLabels:
              app: config-watcher
      ports:
        - protocol: TCP
          port: 9090
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: discovery-authorized-callers
  namespace: sck-controllers-lab
spec:
  podSelector:
    matchLabels:
      app: k8s-discovery
  policyTypes: ["Ingress"]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              discovery-client: "true"
      ports:
        - protocol: TCP
          port: 8761
```

`podSelector` trong các nguồn này chọn Pod cùng namespace. Policy đầu cho Pod trong lab gọi cổng nghiệp vụ, còn cổng quản trị chỉ mở cho Pod Watcher theo nhãn.

NetworkPolicy cần CNI hỗ trợ và các policy có hiệu lực cộng dồn. Nhãn không phải bằng chứng danh tính chống giả mạo; quyền tạo/sửa Pod trong namespace cũng phải được kiểm soát. Xem [Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/).

Ví dụ chỉ giới hạn ingress. Nếu môi trường có egress isolation, cần cho controller truy cập API server/DNS và cho Watcher đi tới cổng quản trị của ứng dụng. Không áp một policy chặn mọi egress rồi giả định discovery vẫn hoạt động.

Thử cả trường hợp Watcher được phép và một Pod không được phép truy cập cổng quản trị. Port-forward không thay thế phép thử mạng Pod-to-Pod.

## 9. Áp dụng và kiểm chứng từng đường đi

### 9.1. Tạo tài nguyên theo nhu cầu

Các lệnh dùng cú pháp Bash. Sau khi thay image placeholder:

```bash
kubectl apply -f namespace.yml
kubectl apply -f network-policies.yml
```

Nếu cần thực hành Discovery Server:

```bash
kubectl apply --dry-run=server -f discovery-server.yml
kubectl apply -f discovery-server.yml
kubectl -n sck-controllers-lab rollout status deployment/k8s-discovery --timeout=180s
```

Nếu cần thực hành Watcher:

```bash
kubectl apply -f catalog-settings.yml
kubectl apply --dry-run=server -f catalog-app.yml
kubectl apply -f catalog-app.yml
kubectl -n sck-controllers-lab rollout status deployment/catalog-service --timeout=180s

kubectl apply --dry-run=server -f config-watcher.yml
kubectl apply -f config-watcher.yml
kubectl -n sck-controllers-lab rollout status deployment/config-watcher --timeout=180s
```

Dry-run kiểm tra schema/admission; không chứng minh RBAC, đường mạng, khả năng refresh hoặc image chạy đúng.

### 9.2. Kiểm tra quyền dự kiến

Tài khoản vận hành có quyền impersonate có thể chạy:

```bash
kubectl auth can-i list endpointslices.discovery.k8s.io \
  --as=system:serviceaccount:sck-controllers-lab:discovery-server \
  -n sck-controllers-lab

kubectl auth can-i watch configmaps \
  --as=system:serviceaccount:sck-controllers-lab:config-watcher \
  -n sck-controllers-lab

kubectl auth can-i list secrets \
  --as=system:serviceaccount:sck-controllers-lab:config-watcher \
  -n sck-controllers-lab

kubectl auth can-i list services \
  --as=system:serviceaccount:sck-controllers-lab:catalog-runtime \
  -n sck-controllers-lab
```

Với bộ Role riêng trong lab và không có grant kế thừa khác, mong đợi lần lượt `yes`, `yes`, `no`, `no`. Nếu lệnh không được phép impersonate, chưa thể dùng kết quả đó để kết luận quyền ServiceAccount.

RBAC là cơ chế cấp quyền cộng dồn. Một Role không ghi Secret không thu hồi grant Secret từ binding khác. Tham khảo [Using RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

### 9.3. Kiểm tra Discovery Server

Port-forward dùng cho chẩn đoán nội bộ:

```bash
kubectl -n sck-controllers-lab port-forward service/k8s-discovery 8761:8761
```

Trong terminal khác:

```bash
curl -fsS http://localhost:8761/apps
curl -fsS http://localhost:8761/apps/catalog-service
```

Lệnh thứ hai cần Service ứng dụng đã được tạo. Kiểm tra có đủ địa chỉ/cổng của các instance Ready mà bạn mong đợi. Sau đó thử caller thật có nhãn được phép đi qua Service DNS để kiểm tra cả NetworkPolicy và cấu hình HTTP client.

Discovery Server thấy `catalog-service` nhờ tài nguyên Kubernetes, kể cả ứng dụng catalog không cài HTTP DiscoveryClient. Có tên Service trong `/apps` cũng chưa chứng minh lời gọi nghiệp vụ tới địa chỉ trả về sẽ thành công.

### 9.4. Kiểm tra Watcher trên từng replica

Liệt kê Pod và ghi nhận tên trước khi đổi cấu hình:

```bash
kubectl -n sck-controllers-lab get pods -l app=catalog-service
kubectl -n sck-controllers-lab logs deployment/config-watcher --tail=100
```

Chọn một Pod:

```bash
POD=catalog-service-REPLACE_WITH_POD_NAME
kubectl -n sck-controllers-lab port-forward pod/"$POD" 8080:8080
```

Trong terminal khác:

```bash
curl -fsS http://localhost:8080/demo/message
```

Kết quả chứa tên Pod và `"Gia tri ban dau"`. Thực hiện tương tự với replica còn lại.

Sửa **chỉ giá trị** `demo.message` trong `catalog-settings.yml` thành `"Gia tri sau refresh"` rồi áp dụng lại ConfigMap:

```bash
kubectl apply -f catalog-settings.yml
kubectl -n sck-controllers-lab logs deployment/config-watcher --tail=100
```

Chờ quá trình đồng bộ volume và khoảng delay cấu hình, rồi kiểm tra riêng từng Pod. Điều kiện đạt:

- Cả hai Pod trả thông điệp mới.
- Tên/UID Pod không đổi và restart count không tăng vì phép refresh.
- Không cần gọi refresh thủ công cho từng Pod để hoàn thành lượt kiểm chứng Watcher.
- Log không có lỗi RBAC, không tìm thấy instance hoặc gọi endpoint thất bại.

Một lần gọi qua Service có thể chỉ rơi vào một replica. Nó không chứng minh mọi instance đã được refresh. Tương tự, HTTP 200 của lời gọi refresh không chứng minh bean/client nghiệp vụ đã sử dụng phiên bản mới; endpoint kiểm tra hành vi mới là bằng chứng cần có.

## 10. Vận hành ngoài lab: phạm vi, HA và tính đúng đắn

### 10.1. Mở rộng namespace có hai phần

Muốn controller theo dõi thêm namespace, phải điều chỉnh cả cấu hình chọn namespace và quyền tại namespace đó.

Có thể đặt ServiceAccount trong namespace hạ tầng và tạo RoleBinding tham chiếu ServiceAccount ấy ở từng namespace ứng dụng. Namespace của `RoleBinding` quyết định phạm vi quyền được cấp, còn namespace trong `subjects` chỉ danh tính ServiceAccount.

Không bật `all-namespaces` rồi cấp quyền cluster-wide để tránh quản lý danh sách namespace. Một controller có phạm vi rộng làm tăng ảnh hưởng khi cấu hình hoặc thông tin xác thực của nó bị lỗi.

### 10.2. Không tăng replica Watcher một cách máy móc

Hai replica hoạt động độc lập có thể cùng phát refresh cho một thay đổi. Hành động refresh và khởi tạo lại tài nguyên cần chịu được tín hiệu lặp, kể cả khi đã dùng leader election.

Tài liệu 5.1 có tùy chọn `spring.cloud.kubernetes.configuration.watcher.ha.enabled=true`, sử dụng leader election và cần quyền `get/create/update` cho Lease thuộc `coordination.k8s.io`. Khi dùng, chọn namespace/lock tương ứng quyền được cấp và kiểm tra failover.

Không chỉ đổi `replicas: 1` thành `2` trong manifest lab rồi coi là HA. Với bản chưa hỗ trợ cơ chế này, chọn cách triển khai mà nhóm đã xác minh thay vì giả định thuộc tính mới có hiệu lực.

Watcher không phải nhật ký cấu hình bền vững cho nghiệp vụ. Sau gián đoạn hoặc đổi leader, cần quan sát phiên bản ứng dụng đang dùng và có cách khôi phục tới trạng thái mong muốn.

### 10.3. Refresh không thay thế mọi rollout

Cần rollout khi:

- Thay đổi ảnh hưởng cấu trúc bean hoặc đường khởi tạo không được hỗ trợ refresh.
- Thư viện/client giữ bản sao cấu hình và không được tái tạo đúng.
- Quy trình cần chuyển cả bộ cấu hình có phiên bản và rollback rõ ràng.
- Cách đóng gói hoặc runtime không hỗ trợ Context Refresh.

Đặc biệt, Context Refresh có giới hạn với Spring AOT/native image; không mặc định mang thiết kế Watcher HTTP của ứng dụng JVM sang native. Với connection pool, TLS và thông tin xác thực, kiểm thử tài nguyên đang dùng thay vì chỉ nhìn giá trị property.

Khi xóa một property, cũng không giả định refresh sẽ tự khôi phục bean về trạng thái như khởi động mới. Thử đúng hành vi mà hệ thống cần.

### 10.4. Messaging là lựa chọn khác, có phạm vi khác

Watcher có thể phát sự kiện qua Spring Cloud Bus khi dùng cấu hình messaging phù hợp. Điều đó cần broker, credential, topology và cơ chế xác định đích.

Phạm vi sự kiện Bus không tự bị giới hạn bởi namespace Kubernetes: ứng dụng khác cùng nối broker có thể chịu ảnh hưởng theo cách định tuyến đã chọn. Chỉ dùng khi hệ thống thật sự cần và nhóm vận hành được phần hạ tầng này.

Với một ứng dụng ít thay đổi cấu hình, rollout có thể dễ kiểm tra và phục hồi hơn việc thêm broker hoặc controller mới.

## 11. Chẩn đoán theo luồng thay vì thêm quyền tùy ý

| Hiện tượng | Điểm cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Discovery Server không Ready | Quyền Service/Pod/EndpointSlice, cache khởi tạo, API | Kiểm tra đúng API group và namespace |
| `/apps` có tên nhưng không có instance mong đợi | Service selector, endpoint Ready, phạm vi discovery | Đối chiếu Service và EndpointSlice |
| Caller HTTP không nhận được dữ liệu | URL server, DNS, NetworkPolicy, starter client | Kiểm tra từng chặng caller → server |
| Watcher không nhận thay đổi | Namespace reload, label ConfigMap, quyền watch | Sửa nguồn theo dõi trước khi xem refresh |
| Watcher nhận sự kiện nhưng không có đích | Annotation `*.apps`, tên Service, discovery namespace | Đồng bộ định danh nguồn và ứng dụng |
| Gọi sai cổng/path | Annotation `boot.spring.io/actuator`, metadata | Đối chiếu địa chỉ quản trị thực tế |
| Refresh trả 401/403 | Xác thực, phân quyền hoặc CSRF của ứng dụng | Cấu hình đường quản trị và client gửi phù hợp |
| Refresh thành công nhưng giá trị cũ | Volume chưa đồng bộ, nguồn bị ghi đè, bean chưa refresh | Kiểm tra dữ liệu và hành vi từng Pod |
| Chỉ một replica đổi giá trị | Đích instance thiếu hoặc chỉ kiểm tra qua Service | Đếm instance và kiểm tra từng Pod |
| Refresh bị gửi nhiều lần | Nhiều Watcher, rollout chồng lấp, sự kiện lặp | Kiểm tra cơ chế HA và khả năng chịu tín hiệu lặp |

Khi thấy 403, xác định nó đến từ Kubernetes API hay endpoint quản trị. Hai lỗi đó thuộc hai hệ thống phân quyền khác nhau; thêm Role đọc ConfigMap không sửa được quyền HTTP refresh.

Không log Secret, ServiceAccount token hoặc header xác thực để chẩn đoán. Chỉ ghi namespace, tên tài nguyên, phiên bản cấu hình, đích không nhạy cảm và kết quả thao tác.

## 12. Bài thực hành và tiêu chí hoàn thành

Trong namespace lab:

1. Viết quyết định kiến trúc: cần Discovery Server, Watcher, cả hai hay không thành phần nào; nêu nhu cầu dẫn tới lựa chọn.
2. Nếu dùng Discovery Server, chứng minh HTTP caller lấy được instance trong phạm vi cho phép mà không có quyền đọc catalog API cho nhu cầu đó.
3. Nếu dùng Watcher, đổi một giá trị ConfigMap không nhạy cảm và chứng minh từng replica đổi hành vi mà không thay Pod.
4. Bỏ label theo dõi trong một lượt thử riêng; giải thích vì sao volume có thể đổi nhưng Watcher không gửi tín hiệu như mong đợi.
5. Khôi phục label, rồi thử tên ứng dụng đích sai; tìm lỗi ở bước khám phá instance.
6. Kiểm tra một Pod không được phép không truy cập được cổng quản trị.
7. Xác nhận ServiceAccount Watcher không có quyền đọc Secret trong bộ lab.
8. Ghi quy trình quay về rollout nếu refresh không đáp ứng tính đúng đắn hoặc yêu cầu phục hồi.

Bài làm đạt yêu cầu khi bạn triển khai đúng thành phần cần dùng, xác định được quyền và đường mạng của từng danh tính, đồng thời chứng minh hiệu quả ở ứng dụng đích thay vì chỉ nhìn trạng thái Running của controller.
