# Liveness, readiness và sự khác nhau về mục đích

Một ứng dụng Spring Boot có thể vẫn còn chạy nhưng chưa đủ điều kiện phục vụ request. Ví dụ, tiến trình Java và HTTP server đều hoạt động, trong khi dữ liệu khởi tạo chưa nạp xong, hệ thống đang ngừng nhận yêu cầu để bảo trì, hoặc một thành phần thiết yếu chưa sẵn sàng. Ngược lại, một ứng dụng có thể rơi vào trạng thái lỗi nghiêm trọng mà cách hợp lý nhất để phục hồi là khởi động lại tiến trình.

Hai câu hỏi này tương ứng với hai khái niệm:

- **Liveness:** Tiến trình ứng dụng còn hoạt động đủ tốt để tiếp tục chạy hay đã ở trạng thái hỏng đến mức nên khởi động lại?
- **Readiness:** Instance ứng dụng hiện có sẵn sàng nhận lưu lượng truy cập mới hay chưa?

Spring Boot thể hiện chúng qua `ApplicationAvailability`, `LivenessState` và `ReadinessState`; Spring Boot Actuator có thể cung cấp endpoint health probe cho hệ thống triển khai như Kubernetes.

**Phân biệt đúng mục đích là điều quan trọng nhất:** liveness thường quyết định *có nên restart container hay không*, còn readiness thường quyết định *có nên đưa traffic mới tới instance hay không*. Nếu dùng liveness để kiểm tra mọi dependency bên ngoài, một sự cố database ngắn có thể kích hoạt hàng loạt lần restart không cần thiết. Nếu chỉ kiểm tra liveness mà không có readiness, request có thể được đưa đến instance chưa khởi động xong.

Bài học giải thích các trạng thái availability trong Spring Boot, vòng đời startup và shutdown, cách bật endpoint Actuator, cấu hình Kubernetes probes, xử lý phụ thuộc bên ngoài và các tình huống thực tế khi cần thay đổi trạng thái.

## 1. Hai câu hỏi, hai hành động vận hành khác nhau

Hãy hình dung ứng dụng bán hàng có ba instance chạy sau một load balancer:

~~~text
             Client requests
                    |
                    v
              Load balancer
             /      |      \
            v       v       v
        Instance A  B       C
         Ready     Not ready Ready
~~~

Instance B vẫn chạy, JVM chưa chết, nhưng đang nạp dữ liệu cần thiết. Không cần khởi động lại B; chỉ cần tạm thời không điều phối request mới tới nó. Đây là tình huống **readiness**.

Một tình huống khác: instance C mắc lỗi nội bộ không thể hồi phục bằng retry thông thường, chẳng hạn luồng xử lý thiết yếu dừng vĩnh viễn và ứng dụng đã chủ động chuyển sang trạng thái broken. Khởi động lại C có thể là cách phục hồi. Đây là tình huống **liveness**.

| Khía cạnh | Liveness | Readiness |
| --- | --- | --- |
| Câu hỏi | Ứng dụng còn nên tiếp tục chạy không? | Ứng dụng đã sẵn sàng phục vụ request mới chưa? |
| Mục tiêu | Phát hiện trạng thái hỏng cần phục hồi bằng restart | Kiểm soát việc nhận traffic |
| Khi kiểm tra thất bại trong Kubernetes | Kubelet có thể restart container theo cấu hình probe | Pod bị đánh dấu không sẵn sàng; Service ngừng chọn endpoint đó cho traffic mới |
| Trường hợp thường gặp | Deadlock/lỗi nội bộ nghiêm trọng không phục hồi | Đang startup, đang drain, chưa xong khởi tạo |
| Có nên phụ thuộc database bên ngoài? | Thường **không** | Chỉ nếu database thực sự là điều kiện để instance phục vụ traffic |
| Có thay thế health check toàn hệ thống không? | Không | Không |

Readiness thất bại không đồng nghĩa ứng dụng “chết”. Liveness thành công cũng không chứng minh ứng dụng đã phục vụ được nghiệp vụ.

## 2. ApplicationAvailability của Spring Boot

Spring Boot cung cấp API `ApplicationAvailability` để truy vấn trạng thái hoạt động của ứng dụng.

Các kiểu chính:

~~~java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
~~~

`ApplicationAvailability` quản lý và cung cấp trạng thái availability hiện tại, dựa trên các sự kiện chuyển trạng thái trong ứng dụng.

### 2.1. Hai giá trị của LivenessState

`LivenessState` có hai giá trị cơ bản:

- `CORRECT`: Ứng dụng được xem là đang ở trạng thái sống bình thường.
- `BROKEN`: Ứng dụng được xem là hỏng, không thể tiếp tục hoạt động đúng.

Ví dụ:

~~~java
LivenessState state = applicationAvailability.getLivenessState();

if (state == LivenessState.CORRECT) {
    System.out.println("Application is live");
}
~~~

Không nên chuyển sang `BROKEN` chỉ vì một dịch vụ phụ trợ bên ngoài tạm thời không phản hồi. Restart ứng dụng thường không sửa được sự cố của database hoặc hệ thống chung đó.

### 2.2. Hai giá trị của ReadinessState

`ReadinessState` có hai giá trị cơ bản:

- `ACCEPTING_TRAFFIC`: Instance sẵn sàng nhận traffic.
- `REFUSING_TRAFFIC`: Instance hiện chưa nên nhận traffic mới.

Ví dụ:

~~~java
ReadinessState state = applicationAvailability.getReadinessState();

if (state == ReadinessState.REFUSING_TRAFFIC) {
    System.out.println("Instance is not ready for new requests");
}
~~~

Một instance có thể cùng lúc:

~~~text
LivenessState = CORRECT
ReadinessState = REFUSING_TRAFFIC
~~~

Đây là trạng thái hoàn toàn hợp lệ. Ứng dụng vẫn khỏe ở mức tiến trình nhưng đang tạm ngừng nhận request.

### 2.3. Đọc trạng thái từ một component

Ví dụ một component đọc availability:

~~~java
package com.example.demo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.stereotype.Component;

@Component
public class AvailabilityReporter implements ApplicationRunner {

    private final ApplicationAvailability availability;

    public AvailabilityReporter(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Liveness: " + availability.getLivenessState()
        );
        System.out.println(
                "Readiness: " + availability.getReadinessState()
        );
    }
}
~~~

`ApplicationRunner` chạy sau khi ApplicationContext đã refresh, nhưng trước khi Spring Boot phát `ApplicationReadyEvent`. Vì thế ở thời điểm runner đang chạy, liveness thông thường đã là `CORRECT`, còn readiness thường vẫn `REFUSING_TRAFFIC`.

Đây không phải lỗi: readiness đang đợi hoàn tất giai đoạn startup, bao gồm cả các runner.

## 3. Vòng đời startup và trạng thái availability

Spring Boot quản lý trạng thái availability theo các mốc lifecycle. Với trình tự startup thông thường:

~~~text
SpringApplication.run()
        |
        v
   Đang khởi động
   Liveness = BROKEN
   Readiness = REFUSING_TRAFFIC
        |
        v
 ApplicationContext được refresh
        |
        v
 ApplicationStartedEvent
   Liveness = CORRECT
   Readiness = REFUSING_TRAFFIC
        |
        v
 ApplicationRunner / CommandLineRunner
        |
        v
 ApplicationReadyEvent
        |
        v
 Readiness = ACCEPTING_TRAFFIC
        |
        v
  Sẵn sàng nhận traffic
~~~

Trong vòng đời chuẩn, các mốc availability của Spring Boot có thể được tóm tắt như sau:

| Giai đoạn | Liveness | Readiness | Ý nghĩa |
| --- | --- | --- | --- |
| Bắt đầu startup | `BROKEN` | `REFUSING_TRAFFIC` | Chưa khởi động đủ |
| Sau context refresh, trước khi runner hoàn tất | `CORRECT` | `REFUSING_TRAFFIC` | Tiến trình hoạt động nhưng chưa ready |
| Sau khi startup hoàn tất | `CORRECT` | `ACCEPTING_TRAFFIC` | Có thể nhận traffic |
| Bắt đầu quá trình dừng có kiểm soát | Thường vẫn `CORRECT` | `REFUSING_TRAFFIC` | Ngừng tiếp nhận traffic mới để đóng ứng dụng |

Một số mốc diễn ra trước khi HTTP server có thể phục vụ health endpoint. Vì vậy startup probe và cấu hình thời gian kiểm tra bên ngoài vẫn quan trọng.

### 3.1. ApplicationStartedEvent khác ApplicationReadyEvent

`ApplicationStartedEvent` được phát sau khi ApplicationContext refresh, **trước** khi các runner chạy.

`ApplicationReadyEvent` được phát khi các runner đã hoàn tất, gần cuối quá trình startup.

Readiness thường chuyển sang `ACCEPTING_TRAFFIC` sau mốc ready. Vì vậy, không nên suy luận rằng việc xử lý một `ApplicationReadyEvent` đồng nghĩa readiness indicator nhất thiết đã trả `UP` ngay tại thời điểm listener đang thực thi: cần xét chính xác thứ tự phát sự kiện và cập nhật availability.

### 3.2. Tại sao runner có thể giữ instance ở trạng thái chưa ready?

Giả sử một runner cần nạp dữ liệu tham chiếu:

~~~java
@Component
public class ReferenceDataLoader implements ApplicationRunner {

    private final ReferenceDataService referenceDataService;

    public ReferenceDataLoader(
            ReferenceDataService referenceDataService) {
        this.referenceDataService = referenceDataService;
    }

    @Override
    public void run(ApplicationArguments args) {
        referenceDataService.loadRequiredData();
    }
}
~~~

`ReferenceDataService` là service ứng dụng thực hiện nạp dữ liệu bắt buộc.

Khi runner còn chạy, Spring Boot chưa kết thúc startup và chưa thông báo readiness chấp nhận traffic. Nếu việc nạp dữ liệu là điều kiện bắt buộc để phục vụ request, runner có thể là lifecycle hook phù hợp.

Tuy nhiên, không nên đặt mọi tác vụ nền không bắt buộc vào runner nếu chúng làm kéo dài startup không cần thiết. Hãy phân biệt dữ liệu *phải có trước khi nhận request* và công việc *có thể hoàn tất sau khi ứng dụng ready*.

## 4. Actuator hiển thị liveness và readiness như thế nào?

Spring Boot Actuator có thể chuyển availability thành health indicators và health groups để hệ thống triển khai truy vấn qua HTTP.

Thêm dependency vào Maven project Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Khi health probes được bật và HTTP server/Actuator được cấu hình phù hợp, thường có hai endpoint:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Liveness group có contribution `livenessState`. Readiness group có contribution `readinessState`.

Khi liveness correct, response có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
~~~

Khi readiness từ chối traffic, response có thể là:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"OUT_OF_SERVICE"}
~~~

Kết quả hiển thị và media type có thể khác theo phiên bản/cấu hình Actuator. Điều quan trọng đối với một HTTP probe là **mã trạng thái HTTP**: thông thường nhóm health trả 2xx cho `UP` và 503 cho `DOWN` hoặc `OUT_OF_SERVICE`.

### 4.1. Bật probes ngoài môi trường Kubernetes

Spring Boot có thể tự bật hỗ trợ probes khi phát hiện đang chạy trên Kubernetes. Nếu muốn kiểm thử các endpoint trên máy local, có thể bật rõ ràng:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Hoặc trong `application.properties`:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

Sau khi ứng dụng khởi động, thử:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

Ví dụ giả định ứng dụng dùng port `8080`, context path mặc định, Actuator trên cùng cổng và HTTP health endpoint có thể truy cập được. Nếu dự án đổi `server.port`, `management.server.port`, base path hoặc bảo mật, URL thực tế có thể khác.

### 4.2. Đừng nhầm /actuator/health với từng probe

Endpoint tổng:

~~~text
/actuator/health
~~~

có thể tổng hợp nhiều health indicator như database, disk space hoặc thành phần ứng dụng.

Hai nhóm:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

có mục đích riêng và mặc định tập trung vào trạng thái availability tương ứng khi được bật.

Không nên cấu hình Kubernetes liveness probe chỉ trỏ vào endpoint health tổng nếu endpoint tổng có thêm database check. Sự cố database có thể khiến toàn bộ health tổng trả lỗi và kích hoạt restart dù ứng dụng vẫn hoạt động bình thường.

## 5. Vì sao liveness không nên kiểm tra dependency bên ngoài?

Giả sử ứng dụng có 10 instance, tất cả cùng kết nối một database. Database gặp sự cố mạng 30 giây.

Nếu liveness probe của từng instance cũng kiểm tra database:

~~~text
Database tạm thời không truy cập được
                 |
                 v
       Health tổng báo DOWN
                 |
                 v
    Liveness của 10 instance fail
                 |
                 v
       Kubernetes restart cả 10
                 |
                 v
  Database trở lại nhưng ứng dụng vẫn
  phải startup / kết nối / warm-up lại
~~~

Việc restart hàng loạt không sửa được database và có thể làm sự cố kéo dài. Khi database phục hồi, các instance lại phải kết nối đồng thời, tạo tải bổ sung.

Vì thế liveness nên phản ánh vấn đề **nội tại và không tự phục hồi** của ứng dụng. Một số ví dụ cần phân tích:

- Một thành phần cốt lõi ngừng vĩnh viễn và không có cơ chế phục hồi.
- Một trạng thái nội bộ khiến ứng dụng không thể tiếp tục phục vụ đúng dù có traffic hay không.
- Deadlock nghiêm trọng hoặc lỗi tiến trình mà restart là lựa chọn phục hồi hợp lý.

Không phải mọi lỗi nội bộ đều cần làm liveness fail. Nhiều lỗi request, exception, tắc nghẽn ngắn hoặc timeout có thể tự phục hồi và nên được xử lý bằng retry, backpressure, timeout hoặc cơ chế điều phối riêng.

**Quy tắc thiết kế:** một tín hiệu liveness thất bại chỉ nên được kích hoạt khi restart có khả năng cải thiện tình hình. Nếu restart không giúp gì hoặc làm sự cố nặng hơn, tín hiệu đó không phù hợp với liveness.

## 6. Readiness nên kiểm tra những gì?

Readiness trả lời câu hỏi liệu **instance hiện tại có thể nhận traffic mới** hay không.

Nó thường từ chối traffic khi:

- Ứng dụng chưa hoàn tất startup.
- Một bước nạp dữ liệu thiết yếu chưa hoàn thành.
- Instance đang drain để shutdown hoặc bảo trì.
- Một thành phần nội bộ cần thiết để phục vụ request bị gián đoạn tạm thời.
- Một phụ thuộc thiết yếu khiến mọi request quan trọng đều không thể phục vụ được.

Tuy nhiên, **không nên đưa tất cả dependency bên ngoài vào readiness theo phản xạ**.

Ví dụ, nếu hệ thống gửi email bị lỗi nhưng chức năng xem sản phẩm vẫn hoạt động, việc đánh dấu toàn bộ instance not-ready có thể làm ngừng cả các chức năng không liên quan. Nếu một hệ thống chung ngừng hoạt động cho mọi instance, đưa lỗi đó vào readiness của tất cả instance có thể khiến cả Service không còn endpoint ready nào.

Hãy hỏi:

1. Nếu dependency này lỗi, instance có còn xử lý hữu ích được traffic không?
2. Lỗi là riêng instance hay ảnh hưởng tất cả instance?
3. Nếu loại instance khỏi load balancer, có instance khác xử lý tốt hơn không?
4. Readiness fail có giúp giảm lỗi người dùng hay chỉ khiến tất cả traffic mất nơi đến?
5. Phép kiểm tra có nhanh, ổn định và có timeout rõ ràng không?

Readiness là quyết định về **nhận traffic**, không phải báo cáo toàn bộ tình trạng hệ thống bên ngoài.

### 6.1. Tập health indicator mặc định

Khi bật probe health groups, Spring Boot thường chỉ đưa `livenessState` vào nhóm liveness và `readinessState` vào nhóm readiness.

Các health indicator khác như database, Redis hoặc disk space không tự động bị gom vào readiness chỉ vì chúng tồn tại trong context. Đây là lựa chọn có chủ đích: ứng dụng cần tự quyết định kiểm tra nào phù hợp với khả năng nhận traffic.

### 6.2. Thêm một dependency thực sự thiết yếu vào readiness

Nếu database là điều kiện bắt buộc để *mọi request cần phục vụ* hoạt động, có thể thêm health contributor `db` vào readiness group:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.group.readiness.include=readinessState,db
~~~

Cấu hình này giả định ứng dụng có datasource và health indicator tên `db` đã được đăng ký. Nếu contributor `db` không tồn tại, cần xem xét lại điều kiện và cấu hình nhóm health, vì Boot có thể báo lỗi khi nhóm tham chiếu đến contributor không có.

Không thêm `db` vào liveness chỉ vì cần “kiểm tra toàn diện hơn”.

### 6.3. Custom HealthIndicator cho readiness

Nếu muốn kiểm tra trạng thái riêng của ứng dụng, có thể tạo `HealthIndicator`:

~~~java
@Component("inventoryGateHealthIndicator")
public class InventoryGateHealthIndicator implements HealthIndicator {

    private final InventoryGate inventoryGate;

    public InventoryGateHealthIndicator(InventoryGate inventoryGate) {
        this.inventoryGate = inventoryGate;
    }

    @Override
    public Health health() {
        return inventoryGate.canServeRequests()
                ? Health.up().build()
                : Health.outOfService().build();
    }
}
~~~

Ở đây `InventoryGate` là abstraction do ứng dụng định nghĩa, cung cấp method `canServeRequests()`. Trong project thật cần định nghĩa và đăng ký bean tương ứng.

Bean `inventoryGateHealthIndicator` tạo health contributor có tên `inventoryGate`. Có thể đưa vào readiness group:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,inventoryGate
~~~

Khi gate không cho nhận request, readiness group có thể trả `OUT_OF_SERVICE`, bất kể `ReadinessState` của Boot đã là `ACCEPTING_TRAFFIC` hay chưa.

Cần làm cho phép kiểm tra nhanh và an toàn; nếu nó gọi dịch vụ mạng, phải đặt timeout và giới hạn tác động. Probe là một lời gọi lặp lại thường xuyên từ hệ thống vận hành.

## 7. Cấu hình Kubernetes livenessProbe và readinessProbe

Trong Kubernetes, kubelet định kỳ gọi các probe do Deployment hoặc Pod spec cấu hình. Một ví dụ:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: catalog-service
  template:
    metadata:
      labels:
        app: catalog-service
    spec:
      containers:
        - name: application
          image: example/catalog-service:1.0.0
          ports:
            - containerPort: 8080
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
~~~

Đây là cấu hình minh họa. Image, cổng, chu kỳ và ngưỡng phải điều chỉnh theo hệ thống thực tế.

### 7.1. Khi liveness probe thất bại

Nếu liveness probe thất bại đủ số lần theo cấu hình, kubelet có thể kết thúc container và khởi động lại theo chính sách restart.

Ví dụ:

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  failureThreshold: 3
~~~

Đừng suy luận rằng sau đúng 30 giây container chắc chắn sẽ restart trong mọi trường hợp: thời điểm thực tế còn phụ thuộc thời gian bắt đầu probe, timeout, scheduling, trạng thái Pod và cấu hình khác. Các giá trị trên chỉ định nhịp kiểm tra và ngưỡng lỗi.

### 7.2. Khi readiness probe thất bại

Kubernetes đánh dấu container/Pod không ready và không chọn Pod đó làm endpoint ready cho Service routing thông thường.

Đây là hành vi điều phối traffic. Readiness thất bại **không trực tiếp yêu cầu restart container**.

Ví dụ, một Pod đang nạp cache có thể vẫn sống, nhưng readiness trả lỗi. Khi tải cache xong, probe thành công, Pod trở lại danh sách endpoint ready.

Readiness điều khiển traffic mới; những kết nối đã tồn tại, request đang xử lý và hành vi của proxy/load balancer cần được xử lý riêng khi graceful shutdown.

### 7.3. HTTP code và health status

Kubernetes HTTP probe coi response HTTP thuộc dải thành công theo quy tắc của Kubernetes là thành công; HTTP status lỗi như `503` là thất bại.

Với cấu hình health Actuator thông thường:

| Spring health status | HTTP response thường gặp | Probe |
| --- | --- | --- |
| `UP` | `200 OK` | Thành công |
| `DOWN` | `503 Service Unavailable` | Thất bại |
| `OUT_OF_SERVICE` | `503 Service Unavailable` | Thất bại |

Nếu ứng dụng tùy chỉnh mapping status-to-HTTP-code, hãy bảo đảm Kubernetes probe vẫn nhận được tín hiệu đúng.

## 8. Startup probe: bảo vệ ứng dụng khởi động chậm

Một liveness probe bắt đầu quá sớm có thể restart ứng dụng khi nó vẫn đang khởi động bình thường. Ví dụ, lần startup đầu tiên phải nạp class, khởi tạo connection pool hoặc xây dựng cache, mất lâu hơn mức probe cho phép.

Kubernetes có **startupProbe** để xử lý tình huống này.

~~~yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 24
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  failureThreshold: 3
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 2
~~~

Trong ví dụ, startup probe có một khoảng dung sai tương đối rộng cho giai đoạn khởi động. Cho tới khi startup probe thành công, Kubernetes chưa bắt đầu thực thi liveness và readiness probes.

Sau khi startup probe thành công, liveness và readiness hoạt động theo cấu hình bình thường.

### 8.1. Vì sao startupProbe thường trỏ tới liveness?

Startup probe chỉ cần xác định ứng dụng đã khởi động đủ để các probe khác bắt đầu. Với Spring Boot, endpoint liveness thường là lựa chọn phù hợp. Readiness có thể còn từ chối traffic do runner hoặc bước khởi tạo kéo dài hơn.

Nếu startup probe trỏ tới readiness, container có thể bị restart chỉ vì một bước nạp dữ liệu hoặc phụ thuộc bên ngoài chưa sẵn sàng, ngay cả khi tiến trình đang tiến triển bình thường. Cần quyết định dựa trên loại startup workload và chính sách vận hành.

### 8.2. StartupProbe không thay readiness

Startup probe thành công không có nghĩa ứng dụng đã sẵn sàng phục vụ mọi request. Readiness vẫn cần xác nhận ứng dụng có nên nhận traffic không.

Ba probe phối hợp:

~~~text
Startup probe: Đã khởi động đủ để kiểm tra bình thường chưa?
Liveness:      Có cần restart tiến trình không?
Readiness:     Có nên gửi traffic mới vào instance không?
~~~

Không phải ứng dụng nào cũng cần startupProbe, nhưng nó hữu ích khi startup có thể kéo dài hoặc biến động đáng kể.

## 9. Management port riêng và rủi ro kiểm tra sai cổng

Spring Boot Actuator có thể chạy cùng cổng ứng dụng hoặc trên một cổng management riêng.

Ví dụ:

~~~properties
server.port=8080
management.server.port=9090
management.endpoint.health.probes.enabled=true
~~~

Khi đó health endpoint có thể được phục vụ trên `9090`, còn request nghiệp vụ chạy trên `8080`.

Có một rủi ro: management port có thể trả health thành công dù connector của ứng dụng trên cổng chính đang gặp vấn đề. Probe chỉ xác nhận cổng mà nó gọi, nên nếu hệ thống cần kiểm tra khả năng phục vụ HTTP thật, một đường dẫn probe trên cổng chính có thể hữu ích hơn.

Spring Boot hỗ trợ bổ sung đường dẫn probe trên server port chính:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

Khi bật, các đường dẫn bổ sung mặc định thường là:

~~~text
GET /livez
GET /readyz
~~~

và chúng được phục vụ trên server port chính. Với cấu hình bên trên:

~~~bash
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
~~~

Các đường dẫn cụ thể phụ thuộc cấu hình base path, version và cơ chế additional paths mà ứng dụng dùng. Nên kiểm tra URL thật khi deploy.

### 9.1. Chọn đường dẫn cho Kubernetes

Nếu Actuator và ứng dụng chạy trên cùng cổng, có thể dùng:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

Nếu management port riêng, cân nhắc dùng additional paths trên cổng ứng dụng:

~~~text
/livez
/readyz
~~~

Ví dụ cấu hình Kubernetes:

~~~yaml
livenessProbe:
  httpGet:
    path: /livez
    port: 8080

readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
~~~

Cần phối hợp với `management.endpoint.health.probes.add-additional-paths=true` và cấu hình web thực tế. Đừng lấy URL trong tài liệu làm bằng chứng endpoint đã tồn tại: hãy gọi thử endpoint trong môi trường chạy.

## 10. Thay đổi readiness bằng AvailabilityChangeEvent

Spring Boot phát `AvailabilityChangeEvent` khi trạng thái availability thay đổi. Ứng dụng cũng có thể phát sự kiện này để chủ động cập nhật trạng thái.

Ví dụ, khi bắt đầu một chế độ bảo trì có kiểm soát, instance cần ngừng nhận traffic mới:

~~~java
package com.example.demo;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class TrafficGate {

    private final ApplicationEventPublisher events;

    public TrafficGate(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void refuseNewTraffic() {
        AvailabilityChangeEvent.publish(
                events,
                ReadinessState.REFUSING_TRAFFIC
        );
    }

    public void acceptNewTraffic() {
        AvailabilityChangeEvent.publish(
                events,
                ReadinessState.ACCEPTING_TRAFFIC
        );
    }
}
~~~

Một service điều phối bảo trì có thể gọi `refuseNewTraffic()`, đợi điều phối traffic ngừng gửi request mới rồi thực hiện công việc phù hợp. Sau khi ứng dụng thực sự có thể phục vụ lại, nó có thể gọi `acceptNewTraffic()`.

**Không cung cấp một endpoint công khai cho phép bất kỳ caller nào gọi hai method này.** Việc đổi trạng thái availability là hành động vận hành nội bộ; nếu expose qua API quản trị, cần có phân quyền và kiểm soát phù hợp.

### 10.1. Không phát ACCEPTING_TRAFFIC quá sớm

Nếu ứng dụng còn nạp dữ liệu hoặc chưa khởi tạo xong thành phần thiết yếu, không nên tự phát `ACCEPTING_TRAFFIC` chỉ để làm readiness probe xanh.

Tương tự, nếu readiness group có custom health indicator đang báo `DOWN` hoặc `OUT_OF_SERVICE`, riêng việc phát `ACCEPTING_TRAFFIC` chưa chắc khiến toàn bộ health group trả `UP`.

### 10.2. Không nhầm chuyển state với tắt HTTP server

Phát `REFUSING_TRAFFIC` làm thay đổi availability và health probe tương ứng. Nó **không tự động đóng socket** hoặc buộc mọi request HTTP trực tiếp bị từ chối.

Kubernetes hoặc load balancer phải sử dụng readiness probe để loại instance khỏi việc nhận traffic mới. Nếu một client vẫn gọi trực tiếp IP/port của instance, ứng dụng có thể tiếp tục nhận request tùy logic của nó.

Readiness là **tín hiệu điều phối**, không phải firewall hay bộ chặn request tự động.

### 10.3. Thời điểm cập nhật state trong startup

Spring Boot tự phát các trạng thái availability trong quá trình khởi động. Nếu ứng dụng tự phát readiness `REFUSING_TRAFFIC` quá sớm, một event `ACCEPTING_TRAFFIC` do Boot phát sau khi ready có thể ghi đè giá trị đó.

Với công việc bắt buộc trước ready, hãy để runner hoàn tất hoặc dùng readiness health contributor riêng. Với bảo trì ở runtime, phát state sau khi startup và có quy trình đưa instance quay lại phục vụ rõ ràng.

## 11. Khi nào đánh dấu liveness BROKEN?

Spring Boot cho phép phát `AvailabilityChangeEvent` với `LivenessState.BROKEN`:

~~~java
AvailabilityChangeEvent.publish(
        applicationEventPublisher,
        LivenessState.BROKEN
);
~~~

Đây là tín hiệu mạnh: nếu Kubernetes liveness probe quan sát thấy trạng thái hỏng trong đủ thời gian, container có thể bị restart.

Chỉ dùng khi ứng dụng gặp tình trạng nội tại không thể tiếp tục hoạt động đúng, và restart được xem là cách phục hồi hợp lý. Không phát `BROKEN` vì:

- Database trả timeout một lần.
- Một request trả HTTP 500.
- Một dịch vụ ngoài tạm thời không phản hồi.
- Cache chưa được warm-up.
- Một tác vụ có thể retry đang thất bại.
- Ứng dụng đang drain để shutdown bình thường.

Với các tình huống này, hãy cân nhắc xử lý lỗi, retry, circuit breaker, readiness hoặc cơ chế điều phối thích hợp.

**Lưu ý:** Một liveness probe HTTP còn kiểm tra được việc endpoint có phản hồi hay không. Nếu tiến trình chết, treo hoàn toàn hoặc HTTP server không phục vụ được probe, kubelet cũng có thể phát hiện thất bại dù ứng dụng không phát một event `BROKEN` tường minh.

## 12. Graceful shutdown: liên hệ giữa trạng thái và việc dừng ứng dụng

Khi triển khai bản mới, hệ thống thường cần thay một instance bằng instance khác mà không cắt ngang các request đang xử lý.

Một quy trình dừng có kiểm soát thường gồm:

1. Nhận yêu cầu dừng, ví dụ Kubernetes gửi `SIGTERM`.
2. Instance ngừng được chọn cho traffic mới thông qua readiness hoặc quá trình loại endpoint.
3. Server ngừng chấp nhận kết nối mới và có một khoảng thời gian để xử lý request đang chạy.
4. Các tài nguyên được đóng và tiến trình kết thúc.
5. Hệ thống triển khai thay instance theo chính sách rolling update.

Trong Spring Boot, có thể bật graceful shutdown cho web server được hỗ trợ:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Thuộc tính `spring.lifecycle.timeout-per-shutdown-phase` cấu hình thời gian cho từng shutdown phase. Đây là ví dụ, cần chọn timeout theo đặc điểm request và thời gian cho phép của môi trường triển khai.

Về mặt availability, readiness cần chuyển sang `REFUSING_TRAFFIC` trong giai đoạn dừng. Liveness thường không cần chuyển sang `BROKEN` vì shutdown có kiểm soát không phải lỗi cần restart.

### 12.1. Kubernetes terminationGracePeriodSeconds

Kubernetes có thuộc tính:

~~~yaml
spec:
  terminationGracePeriodSeconds: 45
~~~

Giá trị này đặt giới hạn thời gian Pod được phép kết thúc sau yêu cầu dừng. Nó cần đủ cho preStop hook nếu có, độ trễ ngừng định tuyến và thời gian graceful shutdown của ứng dụng.

Nếu thời gian Kubernetes cho phép quá ngắn, tiến trình có thể bị buộc kết thúc trước khi hoàn tất các request đang chạy. Nếu quá dài, rollout có thể kéo dài ngoài mong muốn. Cần đo và lựa chọn theo tải thực tế.

### 12.2. Readiness fail không ngay lập tức hủy kết nối đang mở

Một Pod chuyển not-ready giúp Service ngừng chọn nó cho traffic mới, nhưng kết nối TCP đã thiết lập, request đang xử lý hoặc cache routing của proxy có thể còn tồn tại trong một khoảng thời gian.

Vì vậy graceful shutdown còn cần cấu hình HTTP server, timeout, kết thúc connection, quản lý long-running request và có thể có preStop/drain policy ở hạ tầng.

### 12.3. Vì sao không dùng liveness để dừng traffic?

Nếu chủ động làm liveness fail khi bảo trì, Kubernetes có thể restart container. Điều này tạo ra hành vi không mong muốn, trong khi mục tiêu thật sự chỉ là rút instance khỏi traffic.

Hãy dùng readiness cho việc ngừng nhận traffic mới và cơ chế shutdown cho việc dừng tiến trình.

## 13. Các tình huống thực tế: chọn liveness hay readiness?

| Tình huống | Liveness | Readiness | Giải thích |
| --- | --- | --- | --- |
| JVM mới khởi động, context chưa xong | Chưa đạt trạng thái live | Not ready | Chờ startup hoặc startupProbe |
| Context refresh xong, runner còn nạp dữ liệu | Live | Not ready | Chưa phục vụ request được |
| Ứng dụng chạy và xử lý request bình thường | Live | Ready | Trạng thái thường xuyên |
| Pod đang drain trước khi shutdown | Live | Not ready | Rút traffic rồi dừng |
| Email provider lỗi nhưng endpoint đọc dữ liệu vẫn hoạt động | Thường live | Có thể vẫn ready | Xử lý lỗi của một chức năng riêng |
| Database dùng chung bị gián đoạn | Không nên tự fail liveness | Phụ thuộc yêu cầu nhận traffic | Restart đồng loạt thường không giúp gì |
| Một instance mất khả năng phục vụ do tài nguyên cục bộ hỏng | Đánh giá khả năng tự phục hồi | Có thể not ready | Rút instance khỏi traffic trước; restart nếu cần |
| Thành phần nội bộ hỏng vĩnh viễn và restart là cách khôi phục | Có thể broken | Có thể not ready | Liveness phục vụ cơ chế restart |
| Cache phụ trợ chưa warm-up nhưng vẫn truy cập DB trực tiếp được | Live | Tùy SLA | Không nhất thiết phải chờ cache |

Điểm quyết định là **hành động mong muốn của hệ thống điều phối**: restart hay tạm thời không gửi traffic. Cùng một loại lỗi có thể cần chính sách khác nhau tùy kiến trúc.

## 14. Kiểm tra thực tế và chẩn đoán khi probe không đúng

### 14.1. Kiểm tra endpoint ở đúng cổng

Chạy thử trên môi trường ứng dụng:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

Nếu dùng additional paths:

~~~bash
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
~~~

Quan sát cả response body và HTTP code. Một response `404` có thể do endpoint chưa bật, đường dẫn khác hoặc management context path thay đổi. `401`/`403` có thể do security configuration. `503` thường phản ánh health không đủ điều kiện theo mapping hiện tại.

### 14.2. Kiểm tra tình trạng Pod

Trong Kubernetes:

~~~bash
kubectl get pods
kubectl describe pod <pod-name>
~~~

`kubectl describe` thường hiển thị các sự kiện liên quan tới probe thất bại và restart. Có thể xem log:

~~~bash
kubectl logs <pod-name>
~~~

Với Pod có nhiều container, cần chỉ định tên container thích hợp. Với container vừa restart, có thể xem log lần chạy trước:

~~~bash
kubectl logs <pod-name> --previous
~~~

Thay `<pod-name>` bằng tên Pod thực tế; đây là placeholder, không phải một lệnh hoàn chỉnh có thể chạy nguyên văn.

### 14.3. Các nguyên nhân probe thất bại

- Probe dùng sai port.
- `management.server.port` khác port ứng dụng.
- Endpoint health probes chưa bật trong môi trường đang kiểm thử.
- Ứng dụng đổi context path hoặc management base path.
- Endpoint bị chặn bởi Spring Security hoặc network policy.
- Startup kéo dài nhưng không có startupProbe thích hợp.
- Timeout quá ngắn so với độ trễ thực tế.
- Health group chứa indicator quá chậm hoặc phụ thuộc ngoài không ổn định.
- Readiness cố ý `REFUSING_TRAFFIC` do ứng dụng đang khởi động hoặc drain.
- Instance đã khởi động nhưng server port chính chưa đáp ứng như dự kiến.

Cần phân biệt lỗi của **HTTP probe** với trạng thái **availability**. Một probe có thể fail vì kết nối timeout hoặc 404 ngay cả khi `ApplicationAvailability` đang báo `CORRECT` và `ACCEPTING_TRAFFIC`.

### 14.4. Health endpoint không thay thế monitoring

Một health probe chỉ là tín hiệu đơn giản cho hệ thống điều phối. Nó không giải thích đầy đủ lý do sự cố.

Để chẩn đoán tốt hơn, kết hợp log, metrics, tracing, JVM/thread diagnostics, connection pool metrics và dashboard. Các thông tin này giúp xác định vì sao readiness bị từ chối hoặc vì sao liveness endpoint không phản hồi.

## 15. Những lỗi thiết kế thường gặp

### 15.1. Dùng health tổng làm liveness

Nếu `/actuator/health` có database, Redis và disk indicator, trỏ liveness vào đó có thể gây restart khi một thành phần ngoài lỗi.

**Cách xử lý:** dùng health group liveness riêng và chỉ thêm các thành phần mà trạng thái broken thực sự cần restart ứng dụng.

### 15.2. Chỉ cấu hình liveness, bỏ readiness

Ứng dụng có thể nhận traffic trước khi hoàn tất startup hoặc trong quá trình drain.

**Cách xử lý:** cấu hình readiness probe bên cạnh liveness.

### 15.3. Dùng readiness fail để mong container restart

Readiness fail chỉ làm instance không sẵn sàng nhận traffic mới. Nó không yêu cầu kubelet restart container.

**Cách xử lý:** nếu có lỗi nội tại không thể tự phục hồi và restart là cách hợp lý, dùng liveness signal riêng.

### 15.4. Thêm mọi hệ thống ngoài vào readiness

Nếu một dependency dùng chung mất kết nối, tất cả instance có thể cùng not-ready và Service mất toàn bộ endpoint.

**Cách xử lý:** chỉ đưa dependency vào readiness khi nó là điều kiện thực sự để phục vụ traffic và việc loại instance có lợi cho khả năng phục vụ.

### 15.5. Đặt probe timeout quá thấp

Health indicator có thể chạy lâu hơn timeout, làm kubelet coi probe là thất bại ngay cả khi ứng dụng vẫn hoạt động.

**Cách xử lý:** đo độ trễ thực tế, giữ phép kiểm tra nhẹ và chọn timeout/ngưỡng đủ chịu được biến động bình thường.

### 15.6. Chạy khởi tạo quá lâu nhưng thiếu startupProbe

Liveness fail lặp lại trong startup làm Pod restart liên tục.

**Cách xử lý:** thêm startupProbe, điều chỉnh ngưỡng phù hợp và xem liệu quá trình khởi tạo có thể tối ưu hoặc tách sang bước khác không.

### 15.7. Nghĩ rằng readiness REFUSING_TRAFFIC chặn mọi HTTP request

Availability chỉ tạo tín hiệu. Nếu traffic được gửi trực tiếp vào port, request vẫn có thể đến ứng dụng.

**Cách xử lý:** bảo đảm load balancer/Kubernetes sử dụng readiness probe và có chính sách drain kết nối thích hợp.

### 15.8. Đánh dấu BROKEN khi một request lỗi

HTTP 500 cho một request không nhất thiết có nghĩa cả instance không phục hồi được.

**Cách xử lý:** xử lý lỗi request ở đúng tầng; chỉ chuyển liveness broken với lỗi thực sự nghiêm trọng, có cơ chế phát hiện đáng tin cậy.

## 16. Ví dụ cấu hình Spring Boot và Kubernetes kết hợp

Giả sử ứng dụng dùng Spring Boot Actuator trên cùng cổng HTTP `8080` và triển khai trên Kubernetes.

`application.yml`:

~~~yaml
server:
  port: 8080

management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Các URL probe trên cổng chính:

~~~text
http://localhost:8080/livez
http://localhost:8080/readyz
~~~

Deployment excerpt:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: inventory-api
  template:
    metadata:
      labels:
        app: inventory-api
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: inventory-api
          image: example/inventory-api:1.0.0
          ports:
            - containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: 8080
            periodSeconds: 5
            failureThreshold: 24
          livenessProbe:
            httpGet:
              path: /livez
              port: 8080
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: 8080
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
~~~

Khi chạy:

1. Startup probe bảo vệ giai đoạn khởi động đầu.
2. Khi startup probe thành công, liveness bắt đầu kiểm tra khả năng tiếp tục chạy.
3. Readiness kiểm tra khả năng nhận request mới.
4. Nếu readiness thất bại, Pod tạm thời không được chọn làm endpoint ready.
5. Nếu liveness thất bại vượt ngưỡng, kubelet có thể restart container.
6. Khi rollout dừng Pod, timeout/graceful shutdown và chính sách routing giúp các request đang xử lý có thời gian hoàn tất.

Cấu hình trên là điểm khởi đầu minh họa. Ứng dụng production cần đối chiếu timeout, resource usage, ingress/load balancer, security và hành vi khi startup/shutdown của chính mình.

## 17. Bài thực hành

### Bài A: Quan sát hai trạng thái trong startup

Tạo một ứng dụng Spring Boot có `spring-boot-starter-actuator`. Bật health probes. Viết `ApplicationRunner` inject `ApplicationAvailability` và in hai state.

So sánh state ở trong runner với kết quả `/actuator/health/readiness` sau khi ứng dụng khởi động hoàn tất. Giải thích vì sao readiness có thể khác nhau giữa hai thời điểm.

### Bài B: Thay đổi readiness ở runtime

Tạo service `TrafficGate` như ví dụ và thêm một điểm kích hoạt nội bộ có kiểm soát. Phát `ReadinessState.REFUSING_TRAFFIC`, sau đó gọi readiness endpoint và kiểm tra HTTP status.

Phát `ReadinessState.ACCEPTING_TRAFFIC` khi ứng dụng thực sự sẵn sàng lại và quan sát kết quả.

### Bài C: Thử thêm database vào health group

Có một ứng dụng với datasource và health contributor `db`. Cấu hình:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,db
~~~

Mô phỏng database mất kết nối và quan sát readiness. Giải thích trường hợp nào cấu hình này làm hệ thống tốt hơn và trường hợp nào có thể làm toàn bộ Service không có endpoint ready.

### Bài D: So sánh startupProbe với livenessProbe

Tạo một runner chạy một bước khởi tạo lâu (chỉ dùng trong môi trường thử nghiệm). Cấu hình liveness probe với ngưỡng thấp, quan sát vòng restart nếu ứng dụng chưa kịp mở endpoint. Sau đó bổ sung startupProbe và quan sát sự khác biệt.

Không dùng bài thực hành mô phỏng lỗi trên môi trường production.

### Bài E: Kiểm tra management port riêng

Đặt:

~~~properties
server.port=8080
management.server.port=9090
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

Quan sát endpoint Actuator trên port management và `/livez`, `/readyz` trên port chính. Giải thích vì sao gọi probe trên port chính có thể phản ánh khả năng phục vụ HTTP tốt hơn trong một số trường hợp.

### Bài F: Thiết kế graceful shutdown

Giả sử một API có request xử lý tối đa 20 giây. Hãy chọn `terminationGracePeriodSeconds` và `spring.lifecycle.timeout-per-shutdown-phase` hợp lý, rồi mô tả cách readiness, Service endpoint và graceful shutdown phối hợp để giảm request bị ngắt.

Đừng chỉ cộng hai con số; hãy cân nhắc độ trễ rút traffic khỏi load balancer, hook và thời gian thực tế của request.

## 18. Câu hỏi tự kiểm tra

**1. Liveness và readiness khác nhau ở câu hỏi nào?**

Liveness hỏi ứng dụng có còn nên tiếp tục chạy hay cần restart. Readiness hỏi instance có nên nhận traffic mới hay chưa.

**2. `CORRECT` có đồng nghĩa `ACCEPTING_TRAFFIC` không?**

Không. Ứng dụng có thể live nhưng chưa ready trong startup hoặc khi drain.

**3. Trong Kubernetes, readiness probe thất bại có tự restart container không?**

Không. Nó làm Pod không được chọn làm endpoint ready cho Service routing thông thường; liveness mới là cơ chế probe có thể kích hoạt restart.

**4. Vì sao không nên đưa database check vào liveness?**

Sự cố database thường không được sửa bằng việc restart mọi instance ứng dụng; hành vi đó có thể làm tăng tải và kéo dài outage.

**5. Vì sao readiness có thể vẫn REFUSING_TRAFFIC khi ApplicationRunner đang chạy?**

Vì Boot chưa hoàn tất giai đoạn startup và chưa chuyển sang sẵn sàng nhận traffic.

**6. Endpoint Actuator nào thường dùng cho hai probe?**

`/actuator/health/liveness` và `/actuator/health/readiness` khi health probes được bật và endpoint được expose đúng cấu hình.

**7. `/livez` và `/readyz` xuất hiện khi nào?**

Khi bật additional paths cho health probes theo cấu hình tương ứng của Spring Boot.

**8. StartupProbe giải quyết vấn đề gì?**

Nó cho phép ứng dụng có thời gian startup trước khi Kubernetes bắt đầu thực thi liveness/readiness probes, giảm nguy cơ restart khi khởi động chậm.

**9. `AvailabilityChangeEvent.publish(..., REFUSING_TRAFFIC)` có tự đóng cổng HTTP không?**

Không. Nó thay đổi trạng thái availability; hệ thống điều phối phải dùng readiness signal để dừng gửi traffic mới.

**10. Khi shutdown có kiểm soát, nên làm readiness hay liveness fail?**

Thông thường readiness nên từ chối traffic. Shutdown bình thường không phải lỗi liveness cần restart.

## 19. Kết luận

**Liveness** và **readiness** đều là tín hiệu trạng thái của Spring Boot, nhưng phục vụ hai quyết định vận hành khác nhau. Liveness phản ánh khả năng tiến trình tiếp tục hoạt động và có thể dẫn đến restart nếu hệ thống điều phối phát hiện lỗi. Readiness phản ánh khả năng instance nhận traffic mới, giúp load balancer hoặc Kubernetes rút instance khỏi routing khi đang khởi động, bảo trì hoặc drain.

Spring Boot cung cấp `ApplicationAvailability`, `LivenessState`, `ReadinessState` và `AvailabilityChangeEvent` để theo dõi hoặc cập nhật các trạng thái này. Spring Boot Actuator có thể xuất các health probes phù hợp; Kubernetes dùng `livenessProbe`, `readinessProbe` và, khi cần, `startupProbe` để thực hiện những hành động tương ứng.

Hãy giữ liveness độc lập với lỗi tạm thời của các hệ thống bên ngoài, chọn readiness theo khả năng phục vụ traffic thực tế, kiểm tra endpoint trên đúng cổng và kết hợp readiness với graceful shutdown khi triển khai phiên bản mới. Thiết kế probe đúng mục đích giúp tránh restart hàng loạt, giảm request lỗi trong startup/shutdown và làm hệ thống ổn định hơn khi có sự cố.

## Tài liệu tham khảo

- [Spring Boot Reference — Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-availability)
- [Spring Boot Reference — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot Reference — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Kubernetes Documentation — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)

