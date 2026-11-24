# Thực hiện rolling update và kiểm tra instance ngừng nhận lưu lượng

Rolling update thay thế dần các instance của một service bằng phiên bản mới trong khi hệ thống vẫn phục vụ request. Một rollout thành công không chỉ có nghĩa Pod mới chuyển sang trạng thái Ready; cần xác minh instance cũ ngừng nhận **request mới**, request đang xử lý có thời gian hoàn tất, registry hoặc Kubernetes Service không tiếp tục chọn instance đã drain, và tổng thể không gây gián đoạn ngoài SLO.

Trong Spring Cloud Service Discovery, consumer có thể tìm instance qua Eureka, Consul, ZooKeeper hoặc Kubernetes DiscoveryClient rồi dùng Spring Cloud LoadBalancer để chọn endpoint. Vì vậy, khi rolling update, cần điều phối cả readiness, đăng ký/deregister, cache discovery, connection pool và graceful shutdown. Nếu chỉ dừng tiến trình, consumer có thể vẫn chọn địa chỉ cũ trong một khoảng thời gian.

Bài thực hành này xây dựng một quy trình rolling update có thể quan sát được, kiểm tra luồng traffic trước/trong/sau rollout, phân biệt Kubernetes Service với registry-based discovery và thực hiện rollback khi phiên bản mới không đạt điều kiện sẵn sàng.

## 1. Mục tiêu và tiêu chí hoàn thành

Sau bài thực hành, có thể:

- Cấu hình Deployment rolling update để instance mới Ready trước khi instance cũ bị loại bỏ.
- Dùng readiness probe để ngừng đưa instance không còn nhận traffic vào Kubernetes Service endpoints.
- Kết hợp Spring Boot graceful shutdown và một giai đoạn drain để xử lý request đang chạy.
- Hiểu sự khác nhau giữa Pod readiness, Eureka status, Consul health và registry cache của consumer.
- Quan sát instance ID/version trong request để xác định Pod nào đang nhận traffic.
- Xác minh instance cũ không nhận request mới sau khi drain đã hội tụ.
- Kiểm tra request đang xử lý được hoàn tất hoặc bị giới hạn bởi shutdown timeout.
- Rollback Deployment nếu phiên bản mới không Ready hoặc làm tăng lỗi.

Một rollout được xem là đạt khi:

1. Số instance sẵn sàng luôn đáp ứng capacity tối thiểu đã đặt.
2. Instance mới chỉ được đưa vào traffic sau khi readiness đạt.
3. Instance cũ được đánh dấu không nhận traffic mới trước khi tiến trình kết thúc.
4. Request đang chạy được hoàn tất trong thời gian graceful shutdown cho phép.
5. Consumer ngừng chọn instance cũ sau khi endpoint/registry/cache hội tụ.
6. Không có lỗi 5xx hoặc timeout vượt ngưỡng SLO trong suốt rollout.
7. Có thể xác định phiên bản và instance nhận từng request từ log/metrics.

## 2. Các thành phần tham gia vào quá trình drain

Một rolling update đi qua nhiều lớp:

| Thành phần | Trách nhiệm khi rollout |
|---|---|
| Deployment controller | Tạo Pod phiên bản mới và giảm dần Pod phiên bản cũ theo maxSurge/maxUnavailable. |
| Readiness probe | Xác định Pod có đủ điều kiện nhận request mới hay không. |
| Kubernetes Service/EndpointSlice | Chỉ phân phối traffic đến endpoint phù hợp; endpoint đang terminating được đánh dấu theo condition riêng. |
| Spring Boot application | Chuyển readiness sang REFUSING_TRAFFIC, ngừng nhận request mới và hoàn tất request đang xử lý. |
| Registry client | Cập nhật trạng thái hoặc deregister instance khỏi Eureka/Consul/ZooKeeper theo integration. |
| Consumer DiscoveryClient | Nhận registry/endpoint mới và loại instance cũ khỏi góc nhìn discovery. |
| Spring Cloud LoadBalancer | Làm mới danh sách instance được cache và chọn endpoint còn hợp lệ. |
| Ingress/proxy/connection pool | Ngừng gửi kết nối mới đến backend cũ và xử lý connection draining/keep-alive. |

Các lớp này không cập nhật cùng một thời điểm. Readiness của Pod có thể đổi trước khi consumer registry cache được refresh. Một load balancer bên ngoài có thể cần thời gian deregistration riêng. Vì vậy, Pod đã Terminating và không còn request mới đến instance là hai điều kiện khác nhau.

## 3. Phân biệt readiness, liveness và graceful shutdown

- **Readiness:** Pod có sẵn sàng nhận request hay không. Khi readiness fail, Kubernetes không nên đưa Pod vào danh sách endpoint phục vụ bình thường.
- **Liveness:** tiến trình có còn sống và cần tiếp tục chạy hay không. Liveness fail có thể khiến kubelet restart container.
- **Startup probe:** cho ứng dụng đủ thời gian khởi động trước khi liveness/readiness được đánh giá.
- **Graceful shutdown:** khi nhận SIGTERM, server ngừng nhận request mới và chờ request đang xử lý hoàn tất trong khoảng thời gian cấu hình.
- **Drain:** giai đoạn báo cho các lớp routing/discovery biết instance sắp ngừng phục vụ và chờ thay đổi đó lan truyền.

Không dùng liveness để biểu diễn trạng thái drain. Nếu liveness fail, Kubernetes có thể restart container trong lúc đang rollout, khiến request đang xử lý bị cắt. Drain thường được thể hiện bằng readiness chuyển sang REFUSING_TRAFFIC.

## 4. Cấu hình Spring Boot cho readiness và graceful shutdown

Ví dụ cấu hình ứng dụng:

```yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
```

Ý nghĩa:

- server.shutdown: graceful bật chế độ shutdown có kiểm soát của embedded web server.
- spring.lifecycle.timeout-per-shutdown-phase: 30s đặt giới hạn chờ cho một phase shutdown.
- management.endpoint.health.probes.enabled: true bật health group readiness và liveness.
- /actuator/health/readiness được dùng làm readiness probe; /actuator/health/liveness được dùng làm liveness probe.

Graceful shutdown không tự động thay thế readiness drain. Nó bắt đầu phát huy tác dụng khi ứng dụng nhận tín hiệu shutdown; readiness cần đổi sớm hơn để các lớp routing ngừng gửi request mới trong lúc server vẫn còn thời gian hoàn tất request hiện tại.

### 4.1. Endpoint nội bộ để chuyển readiness sang từ chối traffic

Một cách chủ động là cung cấp endpoint nội bộ chỉ được gọi trong lifecycle hook. Endpoint này phát AvailabilityChangeEvent để Spring Boot chuyển trạng thái readiness:

```java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class DrainController {

    private final ApplicationContext applicationContext;

    DrainController(ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    @PostMapping("/internal/drain")
    ResponseEntity<Void> drain() {
        AvailabilityChangeEvent.publish(
                applicationContext,
                ReadinessState.REFUSING_TRAFFIC
        );
        return ResponseEntity.accepted().build();
    }
}
```

Khi endpoint được gọi, health group readiness phản ánh trạng thái từ chối traffic. Kubelet sẽ quan sát readiness fail và Kubernetes cập nhật endpoint routing. Endpoint này cần được bảo vệ: chỉ cho phép lifecycle hook gọi từ loopback/container nội bộ hoặc một identity quản trị riêng; không expose cho người dùng bên ngoài.

Nếu ứng dụng đã có cơ chế drain/readiness riêng, hãy tái sử dụng cơ chế đó thay vì tạo thêm endpoint. Cần kiểm tra endpoint /actuator/health/readiness thực sự chuyển sang HTTP status không thành công sau khi drain.

## 5. Cấu hình Kubernetes Service và Deployment

Service dùng selector ổn định theo tên ứng dụng. Không đưa version vào selector của Service nếu mục tiêu là một Service phục vụ đồng thời Pod cũ và mới trong rollout.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: payment-service
  namespace: commerce
spec:
  selector:
    app: payment-service
  ports:
    - name: http
      port: 80
      targetPort: http
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
  namespace: commerce
spec:
  replicas: 3
  minReadySeconds: 10
  progressDeadlineSeconds: 600
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: payment-service
  template:
    metadata:
      labels:
        app: payment-service
        app.kubernetes.io/name: payment-service
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: payment
          image: registry.example.internal/payment-service:2.4.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: INSTANCE_ID
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 3
            timeoutSeconds: 2
            failureThreshold: 1
          lifecycle:
            preStop:
              exec:
                command:
                  - /bin/sh
                  - -c
                  - "curl -fsS -X POST http://127.0.0.1:8080/internal/drain && sleep 10"
```

Cấu hình trên minh họa một workload ba replica:

- maxSurge: 1 cho phép tạo thêm tối đa một Pod trong lúc rollout.
- maxUnavailable: 0 yêu cầu Deployment duy trì đủ số replica available theo desired count trong quá trình thay thế, miễn là cluster còn tài nguyên để tạo Pod surge.
- minReadySeconds: 10 yêu cầu Pod mới giữ trạng thái Ready đủ thời gian trước khi được tính là available.
- terminationGracePeriodSeconds: 60 dành thời gian cho preStop và quá trình shutdown.
- preStop gọi endpoint drain nội bộ, sau đó chờ 10 giây để readiness/endpoint thay đổi lan truyền.
- Readiness probe kiểm tra khả năng nhận traffic; liveness probe kiểm tra tiến trình còn hoạt động.

Image cần có /bin/sh và curl để chạy ví dụ preStop. Nếu base image không có các công cụ đó, hãy đóng gói một drain script phù hợp hoặc dùng một lifecycle hook khác. Thời gian sleep 10 chỉ là khoảng chờ minh họa; cần đo thời gian hội tụ của cluster và ingress/load balancer để chọn giá trị thực tế.

preStop được chạy trong thời gian termination grace period và hoàn tất trước khi kubelet gửi tín hiệu kết thúc tiến trình. EndpointSlice update và việc thực thi hook có thể diễn ra gần như đồng thời; khoảng chờ giúp routing có thời gian cập nhật. Nó không phải bảo đảm tuyệt đối rằng mọi client cache bên ngoài đã nhận thay đổi.

## 6. Hiểu thứ tự khi một Pod bị thay thế

Khi Deployment thay một Pod cũ:

1. Deployment tạo Pod mới.
2. Pod mới khởi động và vượt qua startup/liveness.
3. Readiness của Pod mới chuyển sang thành công.
4. Sau minReadySeconds, Deployment có thể tính Pod mới là available.
5. Deployment bắt đầu giảm Pod cũ theo chiến lược rolling update.
6. Pod cũ bước vào trạng thái terminating; Kubernetes cập nhật EndpointSlice để phản ánh endpoint đang kết thúc.
7. preStop gọi drain endpoint; ứng dụng chuyển readiness sang REFUSING_TRAFFIC.
8. Hook chờ routing/health/discovery có thời gian cập nhật.
9. Kubelet gửi SIGTERM sau khi hook kết thúc.
10. Spring Boot graceful shutdown ngừng nhận request mới và chờ request đang chạy hoàn tất.
11. Process kết thúc; nếu vượt quá grace period, kubelet có thể gửi SIGKILL.

Thứ tự chính xác giữa EndpointSlice update, probe và preStop không nên được giả định là đồng bộ tức thì. Hãy quan sát Pod condition, EndpointSlice condition, log drain và request thực tế để xác định thời gian của môi trường.

terminationGracePeriodSeconds bao gồm thời gian chạy preStop. Với ví dụ trên, 10 giây drain cộng tối đa 30 giây graceful shutdown cần nằm trong 60 giây grace period, có thêm khoảng dự phòng cho hook và tiến trình kết thúc.

## 7. Theo dõi instance ID và version trong request

Để xác minh Pod cũ ngừng nhận request, mỗi response cần nhận diện instance. Có thể tạo endpoint kiểm thử:

```java
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class InstanceIdentityController {

    @Value("${INSTANCE_ID:local}")
    private String instanceId;

    @Value("${APP_VERSION:dev}")
    private String appVersion;

    @GetMapping("/test/identity")
    Map<String, String> identity() {
        return Map.of(
                "instanceId", instanceId,
                "version", appVersion
        );
    }
}
```

Trong production, không nhất thiết expose endpoint này cho người dùng. Có thể đưa instance ID và version vào structured log, response header nội bộ hoặc metric label có kiểm soát. Tránh đưa Pod UID không giới hạn vào metric label nếu gây cardinality cao.

Một request log hữu ích có các trường:

- service.name
- service.instance.id
- service.version
- trace_id hoặc correlation_id
- thời điểm nhận request
- thời gian xử lý
- kết quả HTTP

Từ đó có thể xác định request cuối cùng được xử lý bởi instance cũ và request đầu tiên được xử lý bởi instance mới.

## 8. Thực hành rolling update từng bước

### Bước 1: Triển khai phiên bản ban đầu

Triển khai ba replica phiên bản 2.4.0:

```bash
kubectl apply -f payment-service.yaml
kubectl rollout status deployment/payment-service -n commerce
kubectl get pods -n commerce -l app=payment-service -o wide
kubectl get endpointslices -n commerce \
  -l kubernetes.io/service-name=payment-service
```

Xác nhận ba Pod đều Ready và EndpointSlice chứa ba endpoint phục vụ. Ghi lại Pod name, instance ID và version của từng Pod.

### Bước 2: Tạo traffic liên tục

Chạy một consumer hoặc load generator gửi request liên tục đến Kubernetes Service:

```bash
while true; do
  date -u
  curl -fsS http://payment-service.commerce.svc.cluster.local/test/identity
  sleep 0.2
done
```

Đây là ví dụ chạy từ một Pod consumer có DNS/network access đến Service. Trong test thực tế, ghi response vào log để phân loại instance ID/version, đồng thời đếm timeout và mã HTTP lỗi. Nếu consumer dùng Spring Cloud LoadBalancer, gửi request qua service ID thay vì gọi DNS ClusterIP để kiểm tra đúng đường discovery đang triển khai.

### Bước 3: Bắt đầu rolling update

Đổi image sang phiên bản mới, ví dụ 2.5.0:

```bash
kubectl set image deployment/payment-service \
  payment=registry.example.internal/payment-service:2.5.0 \
  -n commerce

kubectl rollout status deployment/payment-service -n commerce
```

Theo dõi đồng thời Pod và EndpointSlice:

```bash
kubectl get pods -n commerce -l app=payment-service -w
kubectl get endpointslices -n commerce \
  -l kubernetes.io/service-name=payment-service -w
```

Quan sát Pod mới chỉ được tính available sau khi readiness đạt và minReadySeconds hoàn tất. Pod cũ chỉ bị giảm sau khi Deployment có đủ availability theo chiến lược.

### Bước 4: Xác minh Pod cũ ngừng nhận request mới

Khi Pod cũ chuyển sang terminating:

- Kiểm tra log endpoint /internal/drain được gọi thành công.
- Kiểm tra /actuator/health/readiness chuyển sang trạng thái không sẵn sàng.
- Quan sát EndpointSlice: endpoint cũ được đánh dấu terminating và không còn ready cho traffic mới theo semantics Kubernetes.
- Quan sát request log: instance cũ không nhận request mới sau thời điểm drain đã hội tụ.
- Kiểm tra request đang xử lý trước thời điểm drain có hoàn tất trong giới hạn shutdown timeout hay không.

Lệnh xem Pod:

```bash
kubectl describe pod <old-pod-name> -n commerce
kubectl logs <old-pod-name> -n commerce --since=10m
kubectl get endpointslices -n commerce \
  -l kubernetes.io/service-name=payment-service -o yaml
```

EndpointSlice có các condition như ready, serving và terminating tùy phiên bản Kubernetes. Endpoint đang terminating có thể vẫn được biểu diễn để hỗ trợ proxy/connection draining, nhưng không được xem như endpoint ready thông thường. Kiểm tra đúng condition thay vì chỉ tìm địa chỉ IP còn xuất hiện trong YAML.

### Bước 5: Xác minh phiên bản mới phục vụ bình thường

Sau khi rollout:

```bash
kubectl rollout status deployment/payment-service -n commerce
kubectl get deployment payment-service -n commerce
kubectl get pods -n commerce -l app=payment-service -o wide
```

Gửi request mới và xác nhận version là 2.5.0. Kiểm tra tỷ lệ lỗi, latency, số request theo instance và log của provider. Không chỉ dựa vào trạng thái Available=True của Deployment để kết luận không có request nào bị lỗi.

## 9. Điều chỉnh cho Eureka-based discovery

Khi provider đăng ký trực tiếp vào Eureka, Kubernetes readiness không tự động đồng nghĩa Eureka consumer lập tức ngừng chọn instance. Eureka có registry cache ở client và chu kỳ fetch; Spring Cloud LoadBalancer cũng có thể cache danh sách instance riêng.

Một quy trình drain với Eureka cần phối hợp:

1. Đánh dấu instance OUT_OF_SERVICE trước khi dừng nhận traffic.
2. Chờ Eureka Server nhận status update.
3. Chờ consumer fetch registry mới và LoadBalancer cache làm mới.
4. Xác minh consumer không còn chọn instance cũ.
5. Chờ request đang xử lý hoàn tất.
6. Đóng application context để Eureka Client hủy registration theo lifecycle.
7. Kết thúc process trong thời gian shutdown grace.

Có thể cập nhật trạng thái bằng ApplicationInfoManager trong Spring Cloud Netflix:

```java
import com.netflix.appinfo.ApplicationInfoManager;
import com.netflix.appinfo.InstanceInfo;

@Component
class EurekaDrainService {

    private final ApplicationInfoManager applicationInfoManager;

    EurekaDrainService(ApplicationInfoManager applicationInfoManager) {
        this.applicationInfoManager = applicationInfoManager;
    }

    void markOutOfService() {
        applicationInfoManager.setInstanceStatus(
                InstanceInfo.InstanceStatus.OUT_OF_SERVICE
        );
    }
}
```

Đây là ví dụ provider dùng Eureka Client. Cần xác minh Spring Cloud Netflix version và cấu hình security/status propagation của hệ thống. Đổi status không bảo đảm mọi consumer lập tức loại instance khỏi cache; cần chờ và kiểm tra từ consumer thực tế. Có thể kết hợp readiness/traffic drain ở ingress hoặc Kubernetes để ngừng traffic ở lớp mạng trong lúc Eureka propagation diễn ra.

Eureka heartbeat/lease và cancellation là cơ chế vòng đời registry. Graceful cancellation khác với việc process chết đột ngột rồi chờ lease hết hạn. Bài thực hành nên kiểm tra hai kịch bản riêng nếu cần xác minh failure detection.

## 10. Điều chỉnh cho Consul-based discovery

Với Consul, health check có thể được cấu hình để phản ánh readiness:

```yaml
spring:
  cloud:
    consul:
      discovery:
        register-health-check: true
        health-check-path: /actuator/health/readiness
        health-check-interval: 5s
        query-passing: true
```

Khi drain endpoint chuyển readiness sang REFUSING_TRAFFIC, Consul agent sẽ quan sát health check fail theo chu kỳ. Consumer query với query-passing=true có thể loại instance không passing khỏi danh sách. Tuy nhiên, thời gian check interval, timeout, catalog update và LoadBalancer cache vẫn tạo ra độ trễ.

Một quy trình phù hợp:

- Bắt đầu drain readiness.
- Chờ Consul Health API báo instance không còn passing.
- Chờ consumer DiscoveryClient không còn trả instance theo query policy.
- Chờ LoadBalancer cache refresh.
- Hoàn tất request đang chạy và đóng provider.
- Xác minh service record được deregister theo cấu hình shutdown/agent.

Một health check critical không nhất thiết xóa service record khỏi Catalog. Cần phân biệt “đã đăng ký nhưng không passing” với “đã deregister”. Nếu cấu hình deregisterCriticalServiceAfter, thời gian và điều kiện deregistration cần được tính riêng.

## 11. Điều chỉnh cho Kubernetes DiscoveryClient và DNS

Có hai request path thường gặp:

### 11.1. Gọi qua ClusterIP DNS

Consumer gọi http://payment-service.commerce.svc.cluster.local. Kubernetes Service dataplane phân phối đến endpoint ready. Readiness fail và trạng thái terminating trong EndpointSlice giúp loại Pod cũ khỏi lựa chọn backend khi cập nhật đã lan truyền.

DNS name của ClusterIP thường không đổi khi Pod thay thế. Không cần consumer resolve lại DNS chỉ vì một Pod được rollout; thay đổi chủ yếu nằm trong EndpointSlice/dataplane.

### 11.2. Gọi Pod endpoint qua DiscoveryClient

Nếu Spring Cloud Kubernetes DiscoveryClient trả danh sách Pod/endpoint và Spring Cloud LoadBalancer chọn trực tiếp, cần xác minh:

- Discovery client có quan sát được endpoint mới không.
- Endpoint terminating/not-ready có bị loại khỏi danh sách theo phiên bản và cấu hình không.
- LoadBalancer cache đã refresh chưa.
- Consumer có đang giữ connection đến Pod cũ không.

Nếu dùng headless Service, DNS có thể trả trực tiếp nhiều Pod IP. DNS resolver và client cache có thể giữ IP cũ; thời gian TTL và connection pool cần được tính vào drain window.

Không kết hợp một cách ngoài ý muốn client-side load balancing trên Pod IP với ClusterIP load balancing. Hãy xác định lớp nào chọn Pod cuối cùng và kiểm tra traffic tại lớp đó.

## 12. Connection draining và request đang xử lý

Readiness chỉ ảnh hưởng việc chọn endpoint cho request mới qua routing layer. Nó không tự đóng các kết nối TCP đã thiết lập và không tự hoàn tất request đang chạy.

Cần phân biệt:

- **Request mới:** phải được chuyển sang instance khác sau khi drain hội tụ.
- **Request đang chạy:** cần đủ thời gian hoàn tất trước khi process dừng.
- **Keep-alive connection:** có thể giữ kết nối đến instance cũ; behavior phụ thuộc server, client, proxy và connection pool.
- **Streaming/WebSocket/long polling:** có thể sống lâu hơn thời gian graceful shutdown mặc định; cần chính sách riêng.
- **Retry:** có thể chuyển request sang instance khác nhưng cần idempotency để tránh xử lý nghiệp vụ hai lần.

Spring Boot graceful shutdown giúp server ngừng nhận request mới theo semantics của embedded server và chờ request đang xử lý. Tuy nhiên, thời gian chờ có giới hạn. Request kéo dài hơn timeout-per-shutdown-phase có thể bị ngắt khi process kết thúc. Hãy thiết kế timeout nghiệp vụ thấp hơn shutdown budget hoặc có cơ chế tiếp tục/resume.

Nếu có Ingress, cloud load balancer hoặc service mesh, cấu hình deregistration/drain delay ở tầng đó. Thời gian của proxy phải phù hợp với terminationGracePeriodSeconds và thời gian ứng dụng chờ request đang chạy.

## 13. Chọn thời gian drain và shutdown

Tổng thời gian termination phải đủ cho:

- Hook preStop chuyển readiness/status.
- Endpoint/registry propagation.
- Consumer cache refresh nếu dùng registry-based discovery.
- Connection draining ở ingress/proxy.
- Request đang chạy hoàn tất.
- Spring lifecycle shutdown và cleanup tài nguyên.

Ví dụ ngân sách:

| Giai đoạn | Thời gian minh họa |
|---|---:|
| Chuyển readiness sang refusing traffic | 1 giây |
| Chờ EndpointSlice/Consul/Eureka và proxy cập nhật | 10–15 giây |
| Chờ request đang xử lý | 25 giây |
| Đóng client, connection pool và tài nguyên | 5 giây |
| Dự phòng | 10 giây |
| Tổng | 51–56 giây |

Đây là ví dụ lập ngân sách, không phải default chung. Với Eureka, fetch interval có thể dài hơn 15 giây; với Consul, health-check interval và query behavior khác nhau; với Kubernetes Service, EndpointSlice propagation thường khác registry cache. Đo p95/p99 thực tế rồi đặt grace period đủ lớn.

Không đặt terminationGracePeriodSeconds nhỏ hơn thời gian preStop cộng shutdown timeout. Nếu vượt grace period, kubelet có thể buộc dừng container và làm mất request đang xử lý.

## 14. Quan sát và đo lường trong rollout

Các tín hiệu nên theo dõi:

| Tín hiệu | Câu hỏi cần trả lời |
|---|---|
| Pod Ready/NotReady | Instance mới đã sẵn sàng chưa? Instance cũ đã ngừng được coi là ready chưa? |
| EndpointSlice conditions | Endpoint cũ có còn ready không? Có đang terminating không? |
| Registry status | Eureka có OUT_OF_SERVICE? Consul check có passing? Znode đã bị xóa? |
| DiscoveryClient instances | Consumer còn nhìn thấy instance cũ không? |
| LoadBalancer selection | Consumer còn chọn instance cũ không? |
| Request count theo instance ID | Instance cũ có nhận request mới sau thời điểm drain không? |
| In-flight request | Có request nào bị cắt khi SIGTERM không? |
| HTTP 5xx/timeout | Rollout có tạo lỗi vượt SLO không? |
| Shutdown logs | App có hoàn tất graceful shutdown hay bị SIGKILL? |

Để xác minh “ngừng nhận lưu lượng”, không chỉ đếm tổng request trước và sau rollout. Ghi timestamp drain và instance ID; xác định request mới cuối cùng đến instance cũ. Request đã bắt đầu trước drain có thể kết thúc sau drain và không nên bị tính nhầm là traffic mới.

## 15. Kịch bản kiểm thử và tiêu chí PASS/FAIL

| Kịch bản | Thao tác | PASS khi | FAIL khi |
|---|---|---|---|
| Rollout bình thường | Cập nhật image từ 2.4.0 sang 2.5.0. | Pod mới Ready trước khi Pod cũ bị giảm; traffic chuyển dần. | Capacity tụt dưới ngưỡng hoặc request lỗi vượt SLO. |
| Readiness fail ở Pod mới | Làm readiness endpoint trả lỗi. | Deployment giữ Pod cũ và không tính Pod mới là available. | Pod mới nhận traffic khi chưa Ready. |
| Drain Pod cũ | Gọi /internal/drain. | Readiness fail, endpoint không còn ready và request mới chuyển sang instance khác. | Instance cũ tiếp tục nhận request mới sau drain window. |
| Request dài đang chạy | Gửi request có thời gian xử lý dài rồi bắt đầu rollout. | Request hoàn tất trong shutdown budget. | Process bị dừng trước khi request kết thúc. |
| Registry propagation chậm | Tăng fetch interval/cache TTL trong test. | Test quan sát được thời gian consumer ngừng chọn instance cũ và vẫn giữ capacity. | Consumer tiếp tục chọn endpoint đã dừng hoặc timeout không được xử lý. |
| Instance mới lỗi | Triển khai version mới có lỗi startup/readiness. | Rollout dừng, phiên bản cũ tiếp tục phục vụ. | Deployment loại hết Pod cũ trước khi version mới Ready. |
| Rollback | Chạy kubectl rollout undo. | Version trước quay lại Ready và traffic ổn định. | Rollback không khôi phục endpoint hoặc schema incompatibility gây lỗi. |

## 16. Lệnh quan sát và rollback

Theo dõi tiến trình rollout:

```bash
kubectl rollout status deployment/payment-service -n commerce
kubectl rollout history deployment/payment-service -n commerce
kubectl get deployment payment-service -n commerce -o wide
kubectl get pods -n commerce -l app=payment-service -w
```

Quan sát EndpointSlice:

```bash
kubectl get endpointslices -n commerce \
  -l kubernetes.io/service-name=payment-service -o yaml
```

Xem log shutdown và event:

```bash
kubectl logs <old-pod-name> -n commerce --since=10m
kubectl describe pod <old-pod-name> -n commerce
kubectl get events -n commerce --sort-by=.lastTimestamp
```

Nếu version mới không đạt điều kiện:

```bash
kubectl rollout undo deployment/payment-service -n commerce
kubectl rollout status deployment/payment-service -n commerce
```

Có thể pause rollout để điều tra:

```bash
kubectl rollout pause deployment/payment-service -n commerce
kubectl rollout resume deployment/payment-service -n commerce
```

Rollback image không tự hoàn tác database migration hoặc thay đổi message/schema không tương thích. Thiết kế release nên dùng expand/contract migration và giữ khả năng tương thích giữa version cũ/mới trong giai đoạn rollout.

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Pod cũ bị dừng trước khi Pod mới Ready | maxUnavailable quá lớn hoặc readiness probe cấu hình sai. | Dùng maxUnavailable: 0 khi cần giữ capacity và sửa readiness. |
| Pod mới Ready quá sớm | Readiness chỉ kiểm tra process sống, chưa kiểm tra khả năng nhận traffic. | Dùng readiness group phù hợp với điều kiện phục vụ. |
| Pod cũ vẫn nhận request sau khi drain | Endpoint/registry propagation chậm, consumer cache hoặc connection reuse. | Đo từng lớp, tăng drain window phù hợp và kiểm tra LoadBalancer/proxy. |
| Request đang chạy bị ngắt | Grace period ngắn hơn thời gian request/shutdown. | Tăng shutdown budget hoặc giới hạn thời gian request. |
| preStop không gọi được drain endpoint | Image thiếu curl, port/path sai hoặc endpoint bị security chặn. | Kiểm tra hook event/log, thêm tool/script phù hợp và giới hạn quyền nội bộ. |
| Readiness fail nhưng liveness cũng fail | Dùng chung logic health không phân biệt readiness/liveness. | Tách health groups; không restart chỉ vì instance đang drain. |
| Eureka consumer vẫn thấy instance cũ | Status/deregister chưa lan truyền hoặc registry fetch/LB cache còn cũ. | Mark OUT_OF_SERVICE, chờ fetch/cache và xác minh consumer. |
| Consul vẫn trả instance critical | Catalog record còn tồn tại; query không lọc passing. | Dùng health query phù hợp, cấu hình query-passing và xác minh policy. |
| Kubernetes DNS gọi được Pod cũ | Headless DNS/cache hoặc client connection pool giữ IP. | Kiểm tra TTL/resolver/connection pool; ưu tiên Service ClusterIP nếu không cần Pod identity. |
| Rollout bị treo | Pod mới không Ready, thiếu tài nguyên surge hoặc startup timeout. | Kiểm tra events, quota, capacity và probe. |
| SIGKILL xuất hiện | Hook và shutdown vượt terminationGracePeriodSeconds. | Tính lại thời gian tổng và tăng grace period có kiểm soát. |
| Rollback thành công nhưng request vẫn lỗi | Schema/config mới không tương thích version cũ hoặc registry/cache chưa hội tụ. | Kiểm tra backward compatibility và trạng thái discovery sau rollback. |

## 18. Checklist production

- Deployment có maxSurge/maxUnavailable phù hợp capacity và tài nguyên cluster.
- Readiness phản ánh đúng khả năng nhận request; liveness không bị dùng làm tín hiệu drain.
- Spring Boot graceful shutdown được bật và timeout phù hợp.
- Drain endpoint nội bộ được bảo vệ và được gọi thành công trong preStop.
- Thời gian preStop + propagation + in-flight request + shutdown nằm trong termination grace period.
- Pod mới chỉ nhận traffic sau khi readiness đạt và thời gian ổn định tối thiểu hoàn tất.
- Service selector ổn định để cả Pod cũ/mới cùng được quản lý trong rollout.
- Eureka/Consul/Kubernetes discovery semantics được kiểm tra riêng; không giả định readiness tự động cập nhật mọi registry.
- Consumer cache và LoadBalancer cache có thời gian hội tụ được đo.
- Ingress/load balancer/service mesh có cấu hình connection draining tương thích.
- Log/metrics có instance ID và version để xác định request đến Pod nào.
- Có kiểm thử request dài, health fail, registry propagation chậm và rollback.
- Database/schema/message contract tương thích trong giai đoạn hai version cùng tồn tại.
- Có cảnh báo 5xx, timeout, unavailable replicas và rollout progress deadline.

## Kết luận

Rolling update an toàn cần bảo đảm instance mới sẵn sàng trước khi instance cũ rời traffic, đồng thời cho các lớp routing/discovery đủ thời gian ngừng chọn instance cũ. Readiness điều khiển khả năng nhận traffic, preStop tạo khoảng drain, Spring Boot graceful shutdown hoàn tất request đang chạy và registry/LoadBalancer cập nhật danh sách instance theo cơ chế riêng.

Không đánh đồng Pod Terminating với việc mọi consumer đã ngừng gửi request. Hãy quan sát EndpointSlice, registry status, DiscoveryClient, LoadBalancer selection và request log theo instance ID. Khi kết hợp chiến lược maxSurge/maxUnavailable, readiness, drain, connection draining và rollback, có thể triển khai phiên bản mới mà vẫn duy trì capacity và giới hạn gián đoạn theo SLO.

## Tài liệu tham khảo

- Kubernetes — Deployments and rolling updates: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/
- Kubernetes — Pod lifecycle and termination: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
- Kubernetes — Probes: https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/
- Spring Boot — Graceful shutdown: https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html
- Spring Boot — Application availability: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Cloud Netflix — Eureka: https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html
- Spring Cloud Consul — Service discovery: https://docs.spring.io/spring-cloud-consul/reference/discovery.html
