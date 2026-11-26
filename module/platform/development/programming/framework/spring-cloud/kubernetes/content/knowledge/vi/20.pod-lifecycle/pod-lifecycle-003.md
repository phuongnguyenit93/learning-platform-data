# Readiness và thời điểm Pod được đưa vào tập endpoint

Trong chương **Vòng đời Pod** của **SPRING_CLOUD_KUBERNETES**, readiness trả lời câu hỏi: một Pod có nên được nhận thêm lưu lượng qua cơ chế định tuyến của Service lúc này hay không? Đây là câu hỏi khác với việc container đã chạy, cổng HTTP đã mở hay đối tượng Pod đã xuất hiện trong Kubernetes API.

Một Pod có thể đã xuất hiện trong **EndpointSlice** nhưng endpoint tương ứng vẫn mang `ready: false`. Sau khi Pod chuyển sang Ready, bộ điều khiển cập nhật EndpointSlice và các thành phần định tuyến còn phải tiếp nhận thay đổi. Vì vậy, “có địa chỉ trong EndpointSlice”, “được đánh dấu sẵn sàng” và “đã nhận request qua Service” là ba mốc cần phân biệt.

Bài học dùng một dịch vụ danh mục có hai replica để quan sát các mốc đó. Phần ứng dụng minh họa dùng Java 17 và Spring Boot 3.5.x; phần Kubernetes sử dụng `discovery.k8s.io/v1` EndpointSlice và một Service ClusterIP có selector. Khi áp dụng vào dự án khác, chọn phiên bản Spring Boot và Spring Cloud tương thích với BOM của dự án.

## 1. Hai nghĩa khác nhau của “được đưa vào tập endpoint”

Khi nói “Pod chưa ready thì chưa có trong endpoint”, cần xác định đang nói đến tập nào:

| Tập đang quan sát | Có thể chứa Pod chưa Ready? | Ý nghĩa |
| --- | --- | --- |
| Các Pod khớp selector của Service | Có | Đây là lựa chọn theo nhãn |
| Các địa chỉ được mô tả trong EndpointSlice | Có | Endpoint có địa chỉ và các điều kiện đi kèm |
| Các backend đủ điều kiện nhận lưu lượng thông thường | Thông thường loại endpoint chưa ready | Bộ định tuyến còn xét điều kiện và chính sách lưu lượng |
| Danh sách instance mà một client đang giữ | Tùy cách discovery, bộ lọc và cache | Có thể chưa phản ánh thay đổi mới nhất |

Với Service có selector, control plane quản lý EndpointSlice mô tả các backend tương ứng. Selector không biến thành “nhãn cộng với kết quả health check”; trạng thái sẵn sàng được thể hiện bằng điều kiện của endpoint. [Kubernetes Service và selector](https://kubernetes.io/docs/concepts/services-networking/service/#defining-a-service).

Ví dụ một địa chỉ đã được mô tả nhưng chưa đủ điều kiện nhận lưu lượng:

~~~yaml
apiVersion: discovery.k8s.io/v1
kind: EndpointSlice
metadata:
  name: catalog-service-example
  namespace: readiness-lab
  labels:
    kubernetes.io/service-name: catalog-service
addressType: IPv4
ports:
  - name: http
    protocol: TCP
    port: 8080
endpoints:
  - addresses:
      - "10.244.1.20"
    targetRef:
      kind: Pod
      namespace: readiness-lab
      name: catalog-service-example-pod
    conditions:
      ready: false
      serving: false
      terminating: false
~~~

Đây là minh họa để đọc dữ liệu, không phải manifest cần tự apply. Trong bài thực hành, EndpointSlice do Kubernetes quản lý; không tự sửa nó để ép một Pod vào luồng lưu lượng.

Các điều kiện chính gồm:

- `ready`: tín hiệu endpoint đủ điều kiện nhận lưu lượng theo cách sử dụng thông thường.
- `serving`: khả năng phục vụ; đối với endpoint dựa trên Pod, gắn với trạng thái Ready của Pod.
- `terminating`: endpoint đang trong quá trình kết thúc.

Thông thường, `ready` thể hiện trạng thái đang phục vụ và không terminating. Có ngoại lệ khi Service bật `publishNotReadyAddresses`. [Điều kiện EndpointSlice](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/#conditions).

Nếu một trường điều kiện không xuất hiện, không tự mặc định mọi trường đều là false: API quy định giá trị vắng mặt của `ready` và `serving` được hiểu là true, còn `terminating` là false. Khi chẩn đoán, đọc đúng hợp đồng API thay vì chỉ kiểm tra trường có tồn tại hay không. [EndpointConditions API](https://kubernetes.io/docs/reference/kubernetes-api/discovery/endpoint-slice-v1/#EndpointConditions).

## 2. Từ readiness trong ứng dụng đến lưu lượng thực tế

Luồng điển hình có nhiều tác nhân độc lập:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng Spring
    participant Kubelet as Kubelet
    participant API as Kubernetes API
    participant Controller as EndpointSlice controller
    participant Router as Thành phần định tuyến
    participant Caller as Client

    App->>App: Hoàn thành khởi tạo cần thiết
    Kubelet->>App: GET readiness endpoint
    App-->>Kubelet: HTTP thành công
    Kubelet->>API: Cập nhật Pod Ready
    API-->>Controller: Thay đổi trạng thái Pod
    Controller->>API: Cập nhật điều kiện endpoint
    API-->>Router: Thay đổi EndpointSlice
    Router->>Router: Cập nhật backend có thể chọn
    Caller->>Router: Kết nối đến Service
    Router->>App: Chọn Pod làm backend
~~~

Sơ đồ biểu diễn một đường đi thành công; nó không cam kết mọi consumer đều cập nhật cùng thời điểm hoặc request tiếp theo chắc chắn chọn Pod mới.

### Các mốc cần ghi nhận

| Mốc | Điều gì vừa xảy ra? | Điều chưa thể suy ra |
| --- | --- | --- |
| Container Running | Tiến trình đã bắt đầu chạy | Ứng dụng đã tải xong dữ liệu cần thiết |
| HTTP server lắng nghe | Cổng đã nhận được kết nối | Pod đã Ready |
| Readiness HTTP thành công | Ứng dụng trả kết quả thành công cho lần probe | Kubelet đã công bố trạng thái mới |
| Pod Ready=True | Trạng thái Pod phản ánh điều kiện sẵn sàng | Mọi EndpointSlice và proxy đã cập nhật |
| Endpoint đủ điều kiện | Control plane đã công bố backend có thể dùng | Mọi client đã loại bỏ cache cũ |
| Có request vào Pod | Một đường gọi thực tế đã chọn Pod | Mọi đường gọi trong hệ thống đều đã hội tụ |

Pod Ready còn có thể phụ thuộc vào các container khác và `readinessGates`. Nếu gate tùy chỉnh chưa được cập nhật hoặc chưa là True, một probe thành công trong container ứng dụng chưa đủ để Pod Ready. Cần đọc điều kiện Pod thay vì chỉ nhìn cột `STATUS=Running`. [Pod readiness và readiness gates](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-readiness).

### Vì sao không có một thời điểm tức thời duy nhất?

Có thể phân rã độ trễ để lập kế hoạch quan sát:

~~~text
Thời gian đến lúc Pod bắt đầu đủ điều kiện nhận lưu lượng
≈ thời gian khởi tạo ứng dụng
+ thời gian chờ và thực hiện probe
+ thời gian cập nhật trạng thái Pod
+ thời gian cập nhật EndpointSlice
+ thời gian consumer cập nhật backend.
~~~

Nếu client tự giữ danh sách Pod IP, còn phải xét cache và cơ chế làm mới của client đó. Công thức trên là cách phân tích nguyên nhân, không phải giới hạn thời gian do Kubernetes bảo đảm.

Tương tự, khi readiness hỏng, cần thời gian để phát hiện đủ số lần thất bại rồi truyền thay đổi qua các tầng. Một lần đổi trạng thái trong Spring không đồng nghĩa mọi nơi lập tức ngừng gửi request.

## 3. Readiness, liveness và startup giải quyết ba câu hỏi

| Probe | Câu hỏi | Hành động khi thất bại đến ngưỡng |
| --- | --- | --- |
| Readiness | Có nên gửi thêm lưu lượng đến container/Pod? | Làm container không ready; ảnh hưởng điều kiện Pod và lựa chọn backend |
| Liveness | Tiến trình có cần bị khởi động lại để phục hồi? | Kubelet xử lý khởi động lại container theo cấu hình |
| Startup | Giai đoạn khởi động ban đầu đã hoàn thành chưa? | Nếu vượt ngưỡng, container bị xử lý như khởi động thất bại |

Khi có startup probe, liveness và readiness probe chờ startup probe thành công. Readiness thất bại không tự khởi động lại container. Nếu không khai báo readiness probe, Kubernetes không có phép đo mức sẵn sàng nghiệp vụ từ endpoint mà bạn định cung cấp. [Vai trò của ba loại probe](https://kubernetes.io/docs/concepts/workloads/pods/probes/).

Một ứng dụng mất kết nối đến nguồn dữ liệu cần thiết có thể tạm thời không sẵn sàng nhưng JVM vẫn hoạt động đúng. Đưa tình trạng đó vào liveness dễ biến sự cố phụ thuộc thành việc khởi động lại hàng loạt replica.

Ngược lại, dùng một endpoint TCP chỉ chứng minh cổng có thể mở, chưa chứng minh cache đã sẵn sàng hoặc đường xử lý chính dùng được. Readiness cần diễn đạt khả năng phục vụ của chính ứng dụng, với chi phí kiểm tra nhỏ và thời gian trả lời có giới hạn.

### Không dùng thời gian chờ cố định làm điều kiện nghiệp vụ

`initialDelaySeconds: 30` chỉ trì hoãn thời điểm bắt đầu probe. Nó không chứng minh sau 30 giây dữ liệu đã được tải xong.

Một bản triển khai cần 15 giây để khởi động, bản khác cần 45 giây vì tài nguyên hoặc dữ liệu thay đổi. Cách phù hợp hơn là:

- Ứng dụng tự giữ trạng thái chưa sẵn sàng khi việc khởi tạo bắt buộc còn dang dở.
- Startup probe cung cấp ngân sách khởi động có giới hạn.
- Readiness probe kiểm tra điều kiện thực tế thay vì chờ một mốc thời gian rồi mặc định thành công.

## 4. Biểu diễn readiness trong Spring Boot

Ứng dụng mẫu chỉ cần Web và Actuator. Nó không cần quyền gọi Kubernetes API để kubelet kiểm tra readiness và để EndpointSlice controller theo dõi Pod.

Đây là phần dependency trong dự án đã quản lý phiên bản Spring Boot qua parent hoặc BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Cấu hình `application.yml` của ứng dụng:

~~~yaml
spring:
  application:
    name: catalog-service

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

Hai đường dẫn được dùng trong bài là:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

Spring Boot lấy thông tin availability để cung cấp các health group tương ứng. Trong mẫu, Actuator và API nghiệp vụ dùng cùng cổng 8080. Nếu dự án tách management sang cổng khác, probe thành công trên management chưa chứng minh web server chính nhận được kết nối. Có thể dùng `management.endpoint.health.probes.add-additional-paths=true` để cung cấp `/livez` và `/readyz` trên cổng chính rồi cấu hình probe phù hợp. [Spring Boot Kubernetes probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

### 4.1. Ứng dụng chính

Mỗi lớp dưới đây nằm trong một tệp Java riêng, cùng package `example.readiness`.

~~~java
package example.readiness;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

### 4.2. Mô phỏng khởi tạo trước khi sẵn sàng

Trong profile `readiness-lab`, thêm một runner giữ giai đoạn khởi tạo trong 20 giây:

~~~java
package example.readiness;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Profile("readiness-lab")
@Configuration(proxyBeanMethods = false)
public class ReadinessLabConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(ReadinessLabConfiguration.class);

    @Bean
    ApplicationRunner simulateCatalogWarmup() {
        return args -> {
            log.info("WARMUP_STARTED");
            Thread.sleep(20_000);
            log.info("WARMUP_COMPLETED");
        };
    }
}
~~~

`Thread.sleep` chỉ tạo khoảng thời gian đủ dài để quan sát trong bài thực hành. Trong nghiệp vụ thật, thay nó bằng bước tải dữ liệu cần thiết, có timeout và xử lý thất bại rõ ràng.

Spring Boot coi ứng dụng sẵn sàng sau khi các application runner và command-line runner hoàn thành. Vì vậy, runner đồng bộ phù hợp để minh họa công việc bắt buộc trước readiness. Nếu chuyển việc này sang nền rồi cho runner trả về ngay, phải tự phản ánh phần khởi tạo còn dang dở vào readiness; Boot không tự biết tác vụ nền đã xong hay chưa. [SpringApplication: readiness và runner](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html#features.spring-application.application-availability.readiness).

### 4.3. Điều khiển trạng thái để quan sát việc rút endpoint

Controller dưới đây chỉ tồn tại trong profile lab. `/who` trả về Pod đang xử lý request; `POST /lab/readiness` cho phép đổi trạng thái để quan sát chuỗi cập nhật.

~~~java
package example.readiness;

import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Profile("readiness-lab")
@RestController
public class ReadinessLabController {

    private static final Logger log =
            LoggerFactory.getLogger(ReadinessLabController.class);

    private final ApplicationContext context;
    private final ApplicationAvailability availability;
    private final String podName;

    public ReadinessLabController(
            ApplicationContext context,
            ApplicationAvailability availability,
            @Value("${POD_NAME:local}") String podName) {
        this.context = context;
        this.availability = availability;
        this.podName = podName;
    }

    @GetMapping("/who")
    public Map<String, String> who() {
        log.info("WHO_REQUEST pod={}", podName);
        return Map.of(
                "pod", podName,
                "readiness", availability.getReadinessState().name());
    }

    @PostMapping("/lab/readiness")
    public Map<String, String> changeReadiness(
            @RequestParam("accepting") boolean accepting) {
        ReadinessState next = accepting
                ? ReadinessState.ACCEPTING_TRAFFIC
                : ReadinessState.REFUSING_TRAFFIC;

        AvailabilityChangeEvent.publish(context, next);
        log.info("READINESS_CHANGED pod={} state={}", podName, next);

        return Map.of("pod", podName, "state", next.name());
    }
}
~~~

`AvailabilityChangeEvent.publish` cập nhật trạng thái availability trong ứng dụng. Nó không gọi Kubernetes API để chỉnh Pod hoặc EndpointSlice. Kubelet vẫn phải đọc probe và truyền trạng thái qua luồng điều phối. [AvailabilityChangeEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html).

Chỉ bật profile này trong môi trường thực hành và không đưa đường điều khiển trạng thái ra luồng truy cập công khai. Trong ứng dụng thật, thành phần quản lý khả năng phục vụ mới quyết định trạng thái; client nghiệp vụ không được tùy ý bật/tắt readiness.

Một chi tiết cố ý trong mẫu: `/who` vẫn có thể trả HTTP 200 khi readiness là `REFUSING_TRAFFIC` nếu gọi thẳng đến Pod. Readiness là tín hiệu cho hạ tầng chọn backend, không tự cài một bộ lọc chặn mọi request trong ứng dụng.

## 5. Deployment và Service để kiểm chứng

Lưu manifest thực hành dưới đây thành `readiness-lab.yaml` trong dự án mẫu của người học. Image phải được build từ ứng dụng chứa ba lớp Java và cấu hình vừa trình bày; thay tên image bằng image thực tế có thể kéo được trong cụm.

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: readiness-lab
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
  namespace: readiness-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog-service
  template:
    metadata:
      labels:
        app: catalog-service
    spec:
      automountServiceAccountToken: false
      containers:
        - name: app
          image: example/catalog-service:readiness-lab
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: readiness-lab
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 3
            successThreshold: 1
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 1
            failureThreshold: 3
---
apiVersion: v1
kind: Service
metadata:
  name: catalog-service
  namespace: readiness-lab
spec:
  type: ClusterIP
  publishNotReadyAddresses: false
  selector:
    app: catalog-service
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

Các lựa chọn trong manifest có chủ đích:

- Hai replica cho phép rút một Pod mà vẫn còn backend phục vụ.
- Selector của Service khớp nhãn trên Pod template.
- `targetPort: http` trỏ đến cổng container 8080 đã đặt tên.
- Startup probe kiểm tra liveness để không nhầm “chưa hoàn tất runner” với “cần khởi động lại ngay”.
- Readiness probe kiểm tra group readiness, không dùng health tổng hợp.
- `publishNotReadyAddresses: false` giữ quy tắc loại backend chưa sẵn sàng trong tình huống thông thường.
- Server mẫu không gọi Kubernetes API nên không cần ServiceAccount token hay RBAC đọc endpoint.

Các tham số probe điều khiển tần suất, timeout và số kết quả liên tiếp cần thiết để đổi trạng thái. Ngân sách `30 × 2` giây của startup probe là ước lượng cấu hình, không phải lời hứa rằng mọi lần khởi động có đúng 60 giây. Tương tự, không suy ra readiness chắc chắn bị rút sau đúng `3 × 2` giây; còn có thời điểm lần probe đầu, thời gian đáp ứng và độ trễ cập nhật. [Cấu hình các tham số probe](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/#configure-probes).

## 6. Quan sát từng mốc trong bài thực hành

Các bước dưới đây là hướng dẫn chạy trong cụm thử nghiệm sau khi đã thay image. Chúng không phải kết quả của một lần triển khai đã chạy sẵn.

### 6.1. Theo dõi Pod và EndpointSlice ngay từ lúc khởi động

Mở một terminal theo dõi Pod, một terminal theo dõi EndpointSlice, rồi triển khai manifest từ terminal khác:

~~~powershell
kubectl get pods -n readiness-lab -l app=catalog-service -w
~~~

~~~powershell
kubectl get endpointslices -n readiness-lab -l kubernetes.io/service-name=catalog-service -w -o yaml
~~~

~~~powershell
kubectl apply -f readiness-lab.yaml
~~~

Nếu namespace chưa được tạo ở thời điểm bắt đầu watch, chạy lại lệnh watch sau khi apply đã tạo namespace.

Trong giai đoạn khởi động, đối chiếu log:

~~~powershell
kubectl logs -n readiness-lab -l app=catalog-service --prefix=true --tail=100 -f
~~~

Kỳ vọng có một khoảng thời gian container đã chạy nhưng runner còn ghi nhận `WARMUP_STARTED` mà chưa có `WARMUP_COMPLETED`. Trong khoảng đó, readiness chưa thành công. Địa chỉ Pod có thể đã được mô tả trong EndpointSlice với điều kiện không ready.

Sau khi runner hoàn thành, quan sát tiếp cho đến khi Pod Ready và điều kiện endpoint đổi. Không dùng một dòng log “server started” làm bằng chứng rằng mọi proxy đã bắt đầu chọn Pod.

### 6.2. Đọc điều kiện endpoint thành bảng

Lệnh sau đọc tất cả slice gắn với Service, thay vì giả định một Service luôn chỉ có một slice:

~~~powershell
$slices = kubectl get endpointslices -n readiness-lab -l kubernetes.io/service-name=catalog-service -o json | ConvertFrom-Json

$slices.items | ForEach-Object {
    $sliceName = $_.metadata.name
    $_.endpoints | ForEach-Object {
        [pscustomobject]@{
            Slice       = $sliceName
            Pod         = $_.targetRef.name
            Addresses   = ($_.addresses -join ',')
            Ready       = $_.conditions.ready
            Serving     = $_.conditions.serving
            Terminating = $_.conditions.terminating
        }
    }
} | Format-Table -AutoSize
~~~

Nếu trường hiển thị trống, kiểm tra YAML gốc và áp dụng ý nghĩa giá trị vắng mặt theo API. Đừng đếm số địa chỉ trong bảng rồi xem đó là số backend sẵn sàng.

Trong môi trường nhiều địa chỉ hoặc nhiều slice, một client tự đọc dữ liệu cần tổng hợp và xử lý trùng lặp đúng cách. Với bài thực hành hai replica, mục tiêu chính là đối chiếu tên Pod, IP và điều kiện endpoint.

### 6.3. Chọn một Pod và gọi trực tiếp

Đợi hai replica sẵn sàng trước khi thử đổi trạng thái thủ công:

~~~powershell
kubectl wait --for=condition=Ready pod -n readiness-lab -l app=catalog-service --timeout=180s

$pods = kubectl get pods -n readiness-lab -l app=catalog-service -o json | ConvertFrom-Json
$targetPod = $pods.items[0].metadata.name

kubectl port-forward -n readiness-lab "pod/$targetPod" 18080:8080
~~~

Giữ terminal port-forward hoạt động. Từ một terminal PowerShell khác:

~~~powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:18080/who'
curl.exe -i --max-time 3 'http://127.0.0.1:18080/actuator/health/readiness'
~~~

Ghi lại trường `pod` để biết chính xác replica đang điều khiển.

Port-forward đến Pod dùng để chẩn đoán trực tiếp, không đi qua quy trình chọn backend của Service. Ngay cả `kubectl port-forward service/...` cũng không phải phép thử tương đương lưu lượng qua ClusterIP, vì công cụ chọn một Pod để chuyển tiếp.

### 6.4. Làm một Pod không ready mà không giết tiến trình

Sau khi ứng dụng đã hoàn thành khởi tạo, đổi trạng thái của Pod đang port-forward:

~~~powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18080/lab/readiness?accepting=false'

curl.exe -i --max-time 3 'http://127.0.0.1:18080/actuator/health/readiness'
Invoke-RestMethod -Uri 'http://127.0.0.1:18080/who'
~~~

Kỳ vọng của mẫu:

- Endpoint readiness trả trạng thái HTTP không thành công, mặc định là 503 với trạng thái từ chối lưu lượng.
- Gọi trực tiếp `/who` vẫn có thể trả 200 và cho biết `REFUSING_TRAFFIC`.
- Sau khi đạt ngưỡng probe thất bại, Pod chuyển thành không Ready.
- Endpoint tương ứng trong EndpointSlice không còn được đánh dấu ready.
- Container vẫn Running và số lần restart không tăng chỉ vì readiness thất bại.

Quan sát Pod bằng:

~~~powershell
kubectl get pods -n readiness-lab -l app=catalog-service
kubectl describe pod -n readiness-lab $targetPod
~~~

Hai lệnh có biến `$targetPod` cần chạy ở terminal đã khai báo biến, hoặc khai báo lại đúng tên Pod ở terminal đang dùng.

Nếu probe không thay đổi như dự kiến, kiểm tra đường dẫn, cổng, mã HTTP và cấu hình bảo mật. Ví dụ này không thêm Spring Security; dự án có security phải cho phép kubelet truy cập đúng đường health đã chọn.

### 6.5. Kiểm tra bằng đường Service thực sự

Để kiểm tra định tuyến nội bộ, dùng một Pod công cụ có curl trong cùng namespace. Ví dụ dưới đây dùng `curlimages/curl`; môi trường có registry riêng có thể thay bằng image công cụ tương ứng:

~~~powershell
kubectl run readiness-caller -n readiness-lab --image=curlimages/curl --restart=Never --rm -it --command -- sh
~~~

Trong shell của Pod công cụ, gọi nhiều lần:

~~~sh
curl --http1.1 -H 'Connection: close' -sS --max-time 3 http://catalog-service/who
~~~

Mỗi lần gọi mới giúp quan sát việc chọn backend mà không giữ một kết nối HTTP lâu dài. Khi trạng thái đã hội tụ và một replica không ready, các lần gọi Service thông thường nên đến replica còn sẵn sàng.

Không đòi hỏi hai Pod luân phiên chính xác trước khi rút một Pod. Việc chọn backend còn phụ thuộc cơ chế mạng và chính sách của cụm.

Khôi phục Pod đã rút bằng terminal gọi trực tiếp:

~~~powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18080/lab/readiness?accepting=true'
~~~

Tiếp tục quan sát Pod, EndpointSlice và các lần gọi mới qua Service. Khi readiness thành công đủ ngưỡng và các consumer cập nhật, replica được phép tham gia lại mà không cần tạo Pod mới.

### 6.6. Ghi nhận đúng kết quả

Một bảng quan sát hữu ích có dạng:

| Thao tác | Trạng thái trong Spring | Pod Ready | Endpoint ready | Gọi Service mới sau hội tụ |
| --- | --- | --- | --- | --- |
| Runner chưa xong | REFUSING_TRAFFIC | False | False hoặc chưa có địa chỉ | Chọn replica khác nếu có |
| Runner đã xong | ACCEPTING_TRAFFIC | Chuyển sang True | Chuyển sang True | Có thể chọn replica này |
| POST accepting=false | Đổi ngay trong ứng dụng | Đổi sau probe | Đổi sau cập nhật controller | Tránh replica này |
| POST accepting=true | Đổi ngay trong ứng dụng | Đổi sau probe | Đổi sau cập nhật controller | Có thể chọn lại |

Đây là trình tự kỳ vọng để kiểm chứng, không phải cam kết mỗi mốc xảy ra trong cùng một giây. Ghi thời điểm quan sát cùng tên Pod và IP; không so sánh lớn/nhỏ `resourceVersion` của Pod với `resourceVersion` của EndpointSlice để suy ra thời gian toàn cục.

## 7. Điều gì thay đổi khi dùng Spring Cloud Kubernetes?

Readiness của Pod do ứng dụng, kubelet và điều kiện Pod phối hợp biểu diễn. Spring Cloud Kubernetes sử dụng dữ liệu Kubernetes để khám phá hoặc chọn đích gọi; nó không thay thế luồng readiness đó.

Có hai đường gọi cần phân biệt:

~~~text
Đường A:
Client -> DNS/ClusterIP của Service -> cơ chế mạng của cụm -> Pod

Đường B:
DiscoveryClient -> danh sách ServiceInstance/Pod IP
Client + Spring Cloud LoadBalancer -> Pod được chọn
~~~

Trong đường A, bộ định tuyến của Service theo dõi backend. Trong đường B, ứng dụng client cũng tham gia quyết định chọn Pod và có thể giữ dữ liệu cũ trong một khoảng thời gian.

Spring Cloud Kubernetes LoadBalancer có chế độ `POD` và `SERVICE`. Chế độ POD dùng DiscoveryClient để tìm instance; chế độ SERVICE tạo đích gọi theo Service. Khi điều tra, phải biết ứng dụng đang dùng chế độ nào thay vì chỉ nhìn thấy một tên service trong URL. [LoadBalancer for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/load-balancer.html).

### 7.1. Không chủ động đưa instance chưa ready vào luồng nghiệp vụ

Với client khám phá endpoint, cấu hình liên quan là:

~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        include-not-ready-addresses: false
~~~

Giá trị mặc định được tài liệu mô tả là false. Bật true có thể hữu ích cho công cụ giám sát cần tiếp cận instance chưa ready, nhưng có thể khiến client nghiệp vụ tự chọn một Pod mà luồng Service thông thường đang tránh. [DiscoveryClient: địa chỉ chưa ready](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Đừng nhầm hai tùy chọn sau:

| Tùy chọn | Đặt ở đâu? | Tác động chính |
| --- | --- | --- |
| `spec.publishNotReadyAddresses` | Kubernetes Service | Thay đổi cách công bố endpoint của Service |
| `include-not-ready-addresses` | Spring Cloud Kubernetes client | Thay đổi việc client đưa địa chỉ chưa ready vào kết quả discovery |

Giữ cấu hình client false không thể sửa lại ý nghĩa readiness nếu Service đã công bố mọi endpoint là ready bằng `publishNotReadyAddresses: true`.

### 7.2. Biết client đang đọc Endpoints hay EndpointSlices

Nếu phiên bản và implementation hỗ trợ, client có thể được cấu hình đọc EndpointSlices:

~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        use-endpoint-slices: true
        include-not-ready-addresses: false
~~~

Đây là cấu hình của **ứng dụng gọi**, không phải cấu hình bắt buộc cho server đang được probe. Client cần quyền đọc API tương ứng trong namespace đích, chẳng hạn nhóm `discovery.k8s.io`, tài nguyên `endpointslices`, với các verb cần dùng như `get/list/watch`. Những quyền đọc Service hoặc Pod khác phụ thuộc chức năng discovery được bật. [DiscoveryClient: EndpointSlices và RBAC](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Nếu client dùng Endpoints API cũ, dữ liệu thường tách thành `addresses` và `notReadyAddresses` trong từng subset. Đừng đối chiếu “tổng số địa chỉ” của hai kiểu API rồi kết luận readiness khác nhau. So sánh cùng Pod, cùng trạng thái và cùng bộ lọc client.

### 7.3. Endpoint đã đổi nhưng client vẫn có thể giữ danh sách cũ

Spring Cloud LoadBalancer có lớp cache cho danh sách instance; DiscoveryClient hoặc cấu hình tùy chỉnh cũng có thể giữ dữ liệu riêng. Cần kiểm tra chuỗi supplier và cache thực tế, tránh giả định mỗi request đều đọc Kubernetes API mới. [Spring Cloud LoadBalancer caching](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html#spring-cloud-loadbalancer-caching).

Khi client vẫn gọi Pod đã bị rút:

1. Xác nhận điều kiện endpoint ở API đã thay đổi.
2. Xem kết quả discovery bên trong đúng tiến trình client.
3. Xác định lớp cache, thời gian làm mới và việc tái sử dụng kết nối.
4. Kiểm tra client có gọi Pod IP trực tiếp hoặc dùng danh sách instance tùy chỉnh không.

Không vô hiệu hóa mọi cache ngay để chữa triệu chứng. Trước tiên xác định lớp nào gây độ trễ và nhu cầu cập nhật của hệ thống.

Với yêu cầu chỉ gọi một Service ổn định qua DNS, có thể dùng đường Service mà không thêm DiscoveryClient và LoadBalancer phía client. Chỉ thêm các tính năng này khi ứng dụng thực sự cần lựa chọn instance hoặc metadata tương ứng.

## 8. Các ngoại lệ và giới hạn cần hiểu

### 8.1. publishNotReadyAddresses thay đổi giả định mặc định

`publishNotReadyAddresses: true` thường phục vụ các trường hợp peer discovery, chẳng hạn một headless Service cho StatefulSet cần công bố địa chỉ các thành viên trước khi chúng sẵn sàng phục vụ nghiệp vụ. Các controller tạo endpoint sẽ coi endpoint là ready theo tùy chọn đó, dù Pod chưa Ready. [Service API: publishNotReadyAddresses](https://kubernetes.io/docs/reference/kubernetes-api/core/service-v1/#ServiceSpec).

Vì vậy, một Service dùng cho peer discovery và một Service phục vụ request nghiệp vụ có thể cần chính sách khác nhau. Không bật tùy chọn này chỉ để làm mất dấu hiện tượng “chưa thấy backend ready”.

### 8.2. Không Ready không có nghĩa không thể truy cập bằng mọi đường

Readiness không phải NetworkPolicy hay tường lửa. Gọi Pod IP trực tiếp, port-forward hoặc một đường proxy khác có thể vẫn đến tiến trình.

Việc đổi backend cũng không đồng nghĩa mọi kết nối đã tồn tại bị đóng. Kết nối TCP, HTTP keep-alive, HTTP/2 hoặc stream dài có thể tiếp tục theo cơ chế của từng tầng. Nếu ứng dụng phải tự từ chối thao tác mới trong giai đoạn drain, cần xử lý tại tầng ứng dụng và phối hợp đóng kết nối phù hợp.

Readiness cũng không tự dừng scheduled task hay consumer nhận thông điệp. Chúng không đi qua việc chọn backend HTTP của Service.

### 8.3. Trường hợp Pod đang kết thúc

Trong quá trình kết thúc, có thể thấy `terminating: true`, `ready: false` nhưng `serving: true`. Điều này hỗ trợ phân biệt endpoint còn phục vụ trong lúc đang drain với endpoint bình thường.

Một số đường xử lý proxy có thể dùng endpoint vừa serving vừa terminating khi mọi endpoint khả dụng đều đang terminating. Do đó, không mở rộng quy tắc “ready=false thì không có bất kỳ lưu lượng nào” thành một bảo đảm tuyệt đối cho mọi kịch bản kết thúc. [EndpointSlice: serving và terminating](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/#conditions).

Bài thực hành đổi readiness khi Pod còn sống giúp tách tình huống chưa sẵn sàng khỏi trình tự kết thúc Pod. Graceful shutdown và connection draining cần được thiết kế riêng khi triển khai thật.

### 8.4. Khi mọi replica đều không ready

Service ClusterIP và bản ghi DNS của nó vẫn có thể tồn tại dù không còn backend đủ điều kiện. DNS phân giải thành công chưa chứng minh ứng dụng dùng được.

Cũng không nên kỳ vọng mọi lần gọi đều trả HTTP 503. Service là cơ chế định tuyến mạng; khi không có đích phù hợp, client có thể gặp lỗi kết nối hoặc timeout. Một Ingress, Gateway hay proxy HTTP phía trước có thể tạo phản hồi HTTP riêng.

Điều cần đo là khả năng phục vụ request và nguyên nhân thất bại ở đúng tầng, không chỉ một mã HTTP duy nhất.

## 9. Chọn điều kiện readiness có ý nghĩa

Một điều kiện readiness hữu ích cần gắn với khả năng phục vụ hiện tại của instance, đủ nhẹ để kiểm tra thường xuyên và có đường phục hồi rõ ràng.

Ví dụ đối với dịch vụ danh mục:

| Điều kiện | Có thể đưa vào readiness? | Cần cân nhắc |
| --- | --- | --- |
| Dữ liệu danh mục bắt buộc chưa tải xong | Có | Không nhận request khi chưa có dữ liệu để trả |
| HTTP server chính không tiếp nhận được kết nối | Có | Probe trên cổng management riêng có thể không phát hiện |
| Cache phụ hỏng nhưng có thể fallback | Thường không cần rút cả Pod | Hệ thống còn phục vụ được ở mức chấp nhận không? |
| Cơ sở dữ liệu dùng chung đang hỏng | Cần quyết định theo nghiệp vụ | Đưa mọi replica ra khỏi luồng có giúp hệ thống hơn không? |
| Một request vừa gặp lỗi đơn lẻ | Không đủ để kết luận toàn Pod không ready | Tránh dao động trạng thái vì lỗi cục bộ |
| Dịch vụ quan sát/log phụ trợ tạm lỗi | Thường không nên chặn nghiệp vụ | Có thực sự ngăn ứng dụng phục vụ không? |

Spring Boot mặc định không tự thêm mọi health indicator bên ngoài vào readiness group. Nếu muốn kiểm tra thành phần khác, phải đưa indicator phù hợp vào group; đồng thời không làm liveness phụ thuộc các hệ thống ngoài. [Spring Boot: kiểm tra trạng thái bên ngoài](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.external-state).

Nếu có nhiều thành phần có quyền thay đổi trạng thái, cần một chính sách tổng hợp. Một thành phần tải cache xong không được tự đưa ứng dụng trở lại ACCEPTING_TRAFFIC trong khi một thành phần khác vẫn đang drain hoặc có lỗi bắt buộc. Controller trong bài chỉ minh họa việc phát tín hiệu; nó chưa phải bộ quản lý mọi nguyên nhân sẵn sàng của ứng dụng sản xuất.

ConfigMap hoặc Secret cung cấp đầu vào cấu hình, còn Configuration Watcher hỗ trợ phát hiện thay đổi cấu hình trong các kiến trúc có dùng nó. Chúng không tự chứng minh cấu hình mới đã được ứng dụng kiểm tra và sử dụng thành công. Nếu cập nhật làm khả năng phục vụ thay đổi, ứng dụng cần phản ánh kết quả đó vào readiness.

### Tránh readiness dao động

Probe timeout quá ngắn dưới tải cao hoặc một health check gọi phụ thuộc chậm có thể làm Pod liên tục ra/vào tập backend. Khi một Pod bị rút, tải tăng lên các Pod còn lại; nếu chúng cũng có cùng ngưỡng nhạy, tình trạng có thể lan rộng.

Cần điều chỉnh dựa trên quan sát:

- Thời gian trả lời health endpoint trong điều kiện bình thường và khi quá tải.
- Số lần thất bại liên tiếp cần để rút Pod.
- Số lần thành công liên tiếp cần để đưa Pod trở lại.
- Sức tải dự phòng khi một replica bị rút.
- Cách phục hồi và việc tránh bật lại readiness quá sớm.

Các giá trị nhỏ nhất không tự tạo ra cấu hình tốt nhất. Mục tiêu là phát hiện đúng trạng thái, có thời gian phản ứng phù hợp và giữ hệ thống ổn định.

## 10. Chẩn đoán theo đúng tầng

| Hiện tượng | Tầng cần kiểm tra | Bằng chứng nên thu |
| --- | --- | --- |
| Pod Running nhưng chưa nhận request | Readiness và khởi tạo ứng dụng | Runner, kết quả probe, điều kiện Pod |
| Readiness HTTP trả 200 nhưng Pod chưa Ready | Kubelet, container khác hoặc readiness gate | `kubectl describe pod`, `status.conditions`, trạng thái từng container |
| Pod Ready nhưng không thấy endpoint tương ứng | Selector, Pod IP, cổng và controller | Service YAML, nhãn Pod, toàn bộ EndpointSlices |
| Endpoint có địa chỉ nhưng ready=false | Trạng thái sẵn sàng | Conditions của Pod và endpoint, không chỉ danh sách IP |
| Endpoint ready=true nhưng request thất bại | Đường mạng và ứng dụng | targetPort, cổng đang nghe, NetworkPolicy, proxy, log ứng dụng |
| Endpoint đã bị rút nhưng client vẫn gọi Pod | Client hoặc kết nối cũ | DiscoveryClient, cache, Pod IP trực tiếp, connection pool |
| Readiness trả 401/403 hoặc bị redirect | Đường health và bảo mật | HTTP thực tế mà kubelet nhận |
| Readiness thất bại làm container restart | Có thể đã cấu hình nhầm probe hoặc lỗi khác | Liveness/startup event, OOM, exit code, restart reason |
| Không còn backend nhưng DNS vẫn phân giải | Phân biệt danh tính Service với backend | ClusterIP, EndpointSlices và kết nối thực tế |

Để kiểm tra condition trực tiếp:

~~~powershell
$pod = kubectl get pod -n readiness-lab $targetPod -o json | ConvertFrom-Json
$pod.status.conditions | Format-Table type,status,reason,lastTransitionTime -AutoSize
$pod.status.containerStatuses | Format-Table name,ready,restartCount -AutoSize
~~~

Khi xác định nguyên nhân, bắt đầu từ ứng dụng và đi theo chuỗi:

~~~text
Trạng thái sẵn sàng trong Spring
-> kết quả kubelet probe
-> Pod Ready
-> điều kiện EndpointSlice
-> backend mà đường định tuyến đang dùng
-> request thực tế và kết nối của client.
~~~

Bài thực hành đạt mục tiêu khi bạn quan sát được một Pod vẫn Running nhưng bị rút khỏi lựa chọn backend do readiness, rồi tham gia lại sau khi phục hồi mà không restart. Đồng thời, cần giải thích được vì sao địa chỉ vẫn có thể hiện diện trong EndpointSlice, vì sao các mốc cập nhật có độ trễ và vì sao một lần gọi trực tiếp thành công chưa chứng minh Service hoặc DiscoveryClient đang chọn đúng backend.
