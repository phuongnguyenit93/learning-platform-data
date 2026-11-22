# Health status khác với liveness hoặc readiness

Khi giám sát một ứng dụng Spring Boot, có thể gặp ba câu hỏi nghe rất giống nhau:

1. **Ứng dụng có đang khỏe không?** — Một báo cáo health tổng hợp có thể trả lời trạng thái của những thành phần đang được kiểm tra.
2. **Tiến trình có còn hoạt động đúng để tiếp tục chạy không?** — Đây là góc nhìn **liveness**.
3. **Instance hiện tại đã sẵn sàng nhận lưu lượng mới chưa?** — Đây là góc nhìn **readiness**.

Ba câu hỏi không đồng nghĩa. Một ứng dụng có thể **còn sống nhưng chưa sẵn sàng nhận request** khi đang warm-up; một dependency ngoài bị lỗi có thể khiến health tổng hợp báo `DOWN`, dù tiến trình ứng dụng vẫn hoạt động và không nên bị restart; một instance đang graceful shutdown có thể còn sống nhưng phải ngừng nhận request mới.

Spring Boot Actuator cung cấp endpoint health và, khi bật chức năng phù hợp, các health group dành cho liveness/readiness. Để vận hành đúng, phải phân biệt **Health status** do các health indicator tổng hợp với **availability state** do lifecycle ứng dụng quản lý, rồi hiểu Kubernetes hoặc load balancer sẽ làm gì với từng tín hiệu.

## 1. Khái niệm: health, liveness, readiness

### Health status

**Health status** là kết quả đánh giá tình trạng của một hoặc nhiều thành phần: database, disk space, message broker, dịch vụ tích hợp hoặc indicator do ứng dụng tự viết.

Ví dụ:

~~~json
{
  "status": "UP"
}
~~~

Hoặc khi bật hiển thị chi tiết với quyền phù hợp:

~~~json
{
  "status": "DOWN",
  "components": {
    "db": {
      "status": "DOWN"
    },
    "diskSpace": {
      "status": "UP"
    },
    "ping": {
      "status": "UP"
    }
  }
}
~~~

Báo cáo này phản ánh **những indicator mà endpoint/group thực sự bao gồm**, không phải lời hứa rằng mọi chức năng nghiệp vụ của ứng dụng đều chính xác.

### Liveness

**Liveness** trả lời: *Tiến trình hiện tại có đang ở trạng thái hoạt động hợp lệ, hay rơi vào tình huống cần khởi động lại để phục hồi?*

Với Kubernetes, liveness probe thất bại liên tiếp theo chính sách sẽ khiến kubelet **restart container**. Đây là hành động mạnh, nên không gắn liveness với lỗi của những dependency bên ngoài mà restart cũng không giải quyết được.

### Readiness

**Readiness** trả lời: *Instance có nên nhận request mới tại thời điểm này không?*

Với Kubernetes, readiness probe thất bại khiến Pod không được xem là ready và thông thường bị loại khỏi danh sách endpoint được Service dùng để định tuyến traffic. **Readiness failure tự nó không yêu cầu restart container**.

Readiness phù hợp với thời điểm warm-up, chưa hoàn tất initialization, đang drain khi shutdown hoặc một điều kiện tạm thời khiến instance không phục vụ request mới an toàn.

### So sánh nhanh

| Tín hiệu | Câu hỏi | Hành động điển hình của Kubernetes |
|---|---|---|
| Health tổng hợp | Các thành phần được kiểm tra có hoạt động không? | Không có ý nghĩa restart/routing cố định trừ khi được cấu hình thành probe |
| Liveness | Container có cần được restart không? | Restart nếu probe thất bại vượt ngưỡng |
| Readiness | Pod có được nhận traffic mới không? | Ngừng đưa vào routing khi không ready |
| Startup probe | Ứng dụng đã vượt qua pha khởi động ban đầu chưa? | Trì hoãn liveness/readiness; restart nếu startup không thành công theo ngưỡng |

**Quy tắc:** Đừng dùng cùng một phép kiểm tra cho mọi câu hỏi mà chưa xem xét hành động của hệ thống vận hành sau khi check thất bại.

## 2. Bật Spring Boot Actuator

Trong Gradle Groovy DSL, với dự án đã dùng Spring Boot plugin và dependency management tương ứng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Một ứng dụng Spring Boot tối thiểu:

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

Khi Actuator được cấu hình đúng, HTTP health endpoint thường có đường dẫn:

~~~text
GET /actuator/health
~~~

Ví dụ:

~~~bash
curl -i http://localhost:8080/actuator/health
~~~

Phản hồi điển hình:

~~~http
HTTP/1.1 200
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
~~~

Media type và body thực tế phụ thuộc phiên bản, trạng thái và cấu hình hiển thị. Ví dụ trên chỉ minh họa `UP`.

Không nhất thiết phải expose tất cả Actuator endpoints. Trong cấu hình HTTP mặc định của nhiều dòng Spring Boot hiện đại, health endpoint được phép truy cập; khi thay đổi management base path, port, security hoặc exposure settings, đường dẫn và quyền truy cập có thể khác.

## 3. HealthIndicator và Health status hoạt động thế nào?

Mỗi `HealthIndicator` đóng góp một đối tượng `Health`:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;

public final class InventoryHealthIndicator implements HealthIndicator {

    @Override
    public Health health() {
        boolean available = checkInventoryLocally();

        if (available) {
            return Health.up().build();
        }
        return Health.down().build();
    }

    private boolean checkInventoryLocally() {
        // Minh họa. Thực tế dùng kiểm tra phù hợp, nhẹ và có timeout.
        return true;
    }
}
~~~

Với ứng dụng Spring Boot có database và actuator, có thể có các contributor như:

- `db`: phản ánh tình trạng database theo health indicator được auto-configure.
- `diskSpace`: kiểm tra không gian đĩa theo ngưỡng.
- `ping`: indicator đơn giản xác nhận endpoint xử lý được request.
- Indicator tùy chỉnh do ứng dụng hoặc thư viện khai báo.

Endpoint `/actuator/health` có thể tổng hợp các contributor bằng `StatusAggregator`.

### Những status phổ biến

| Status | Diễn giải thông thường |
|---|---|
| `UP` | Thành phần được kiểm tra hoạt động theo tiêu chí indicator |
| `DOWN` | Thành phần không đáp ứng tiêu chí health check |
| `OUT_OF_SERVICE` | Thành phần/instance hiện không nên tham gia phục vụ |
| `UNKNOWN` | Không xác định được tình trạng theo cách kiểm tra hiện tại |

Ngoài các status mặc định, ứng dụng có thể định nghĩa status tùy chỉnh. Khi đó cần hiểu cách tổng hợp và ánh xạ sang HTTP status phù hợp.

### Aggregation không có nghĩa “mọi thứ đều hoạt động”

Ví dụ một response:

~~~json
{
  "status": "DOWN",
  "components": {
    "db": {"status": "DOWN"},
    "diskSpace": {"status": "UP"}
  }
}
~~~

Nó chỉ cho biết kết quả của `db` và `diskSpace` trong group hiện tại. Một nghiệp vụ gọi dịch vụ thanh toán bên ngoài có thể đang lỗi dù health vẫn `UP` nếu không có indicator nào kiểm tra chức năng đó.

Ngược lại, health báo `DOWN` vì một database dùng cho tác vụ nền cũng không tự chứng minh toàn bộ API còn lại phải dừng nhận request.

## 4. HTTP status khác với trường "status" trong JSON

Actuator health có thể trả về body:

~~~json
{"status":"UP"}
~~~

và HTTP 200. Với status không khỏe như `DOWN` hoặc `OUT_OF_SERVICE`, mặc định Spring Boot thường ánh xạ sang HTTP 503 (Service Unavailable). `UNKNOWN` thường vẫn được ánh xạ sang HTTP 200 theo mặc định.

Một ví dụ:

| Health status | HTTP code mặc định thường gặp |
|---|---|
| `UP` | 200 |
| `DOWN` | 503 |
| `OUT_OF_SERVICE` | 503 |
| `UNKNOWN` | 200 |

Có thể cấu hình `management.endpoint.health.status.http-mapping.*` để thay đổi mapping trong các phiên bản hỗ trợ, cũng như cấu hình thứ tự ưu tiên của custom statuses. Tuy nhiên, khi dùng Kubernetes HTTP probes, chính **HTTP response status code** là tín hiệu chính; kubelet không đọc chuỗi `status` trong JSON để tự suy luận.

### Ví dụ custom HTTP mapping

~~~properties
management.endpoint.health.status.http-mapping.fatal=503
~~~

Ví dụ chỉ có ý nghĩa nếu ứng dụng có một custom `Status("FATAL")` và cấu hình status aggregation phù hợp. Khi thay thế mapping, cần xem tài liệu phiên bản đang dùng vì khai báo mapping tùy chỉnh có thể ảnh hưởng mapping mặc định của `DOWN` và `OUT_OF_SERVICE`; nếu cần, hãy khai báo chúng tường minh.

Không nên đổi `DOWN` thành HTTP 200 chỉ để tránh probe thất bại: điều đó có thể che giấu lỗi thực sự đối với hệ thống điều phối.

## 5. Vấn đề lớn nhất: health tổng hợp không bằng liveness

Giả sử ứng dụng có ba replicas và một database dùng chung:

~~~text
                   Kubernetes Service
                         |
              +----------+----------+
              |          |          |
              v          v          v
           Pod A       Pod B       Pod C
              \          |          /
               \         |         /
                +--------+--------+
                         |
                         v
                    Shared DB
~~~

Nếu database tạm thời lỗi, `db` health indicator trên cả ba Pods có thể trả về `DOWN`.

Nếu bạn dùng `/actuator/health` làm **liveness probe**, Kubernetes có thể restart cả ba Pods liên tục. Restart ứng dụng **không sửa được lỗi của database bên ngoài**. Thay vào đó, nó còn có thể gây:

- Mất kết nối và state tạm thời không cần thiết.
- Tăng tải tạo connection khi database đang phục hồi.
- Làm quá trình recovery chậm hơn.
- Tạo restart loop ở toàn bộ replicas.
- Che mất tín hiệu lỗi gốc vì log liên tục bị ngắt giữa startup/shutdown.

Đây là lý do Spring Boot khuyến nghị **không đưa external-system health checks vào liveness**.

Một instance còn sống có thể tạm thời không gọi database được. Liveness chỉ nên thất bại khi bản thân instance rơi vào trạng thái mà **restart là hành động phục hồi hợp lý**.

## 6. Readiness cũng không nên sao chép health tổng hợp một cách máy móc

Một phản ứng thường gặp là: “Vậy chuyển toàn bộ health checks sang readiness”. Cách này vẫn cần suy nghĩ.

Nếu database dùng chung bị mất kết nối và readiness của mọi Pod đều trả về 503, Kubernetes có thể không còn endpoint ready nào để route traffic. Hậu quả ở phía caller là toàn bộ Service có thể không nhận request, kể cả các endpoint **không cần database**.

Có những hệ thống mà quyết định đó là đúng: nếu mọi request quan trọng đều bắt buộc truy cập database thì không nên tiếp tục nhận traffic để rồi lỗi hàng loạt.

Nhưng cũng có hệ thống có các chức năng đọc cache, health information hoặc API độc lập vẫn phục vụ được khi database tạm thời không sẵn sàng. Khi đó, đánh dấu toàn bộ Pod là unready có thể làm phạm vi sự cố lớn hơn.

**Readiness là quyết định về khả năng phục vụ traffic của instance, không chỉ là phép AND giữa mọi dependency.**

Các câu hỏi cần trả lời:

1. Dependency bị lỗi có thực sự khiến instance này không thể phục vụ loại traffic mà load balancer sẽ gửi không?
2. Các Pods khác có thể phục vụ thay thế không, hay tất cả cùng phụ thuộc hệ thống đó?
3. Khi loại Pod khỏi routing, người dùng có trải nghiệm tốt hơn hay chỉ nhận 503 ngay tại gateway?
4. Lỗi dependency là tạm thời và ứng dụng có thể retry/circuit-break hay không?
5. Health check có đủ nhanh, ổn định và nhẹ để bị gọi lặp lại không?

## 7. ApplicationAvailability: mô hình trạng thái sống và sẵn sàng

Spring Boot có abstraction `ApplicationAvailability` để theo dõi trạng thái availability của ứng dụng.

Hai enum quan trọng là:

~~~java
org.springframework.boot.availability.LivenessState
org.springframework.boot.availability.ReadinessState
~~~

Những giá trị phổ biến:

**LivenessState**

- `CORRECT`: tiến trình được xem là đang ở trạng thái hoạt động bình thường.
- `BROKEN`: tiến trình ở tình trạng không còn hoạt động đúng và việc restart có thể cần thiết.

**ReadinessState**

- `ACCEPTING_TRAFFIC`: instance có thể nhận traffic.
- `REFUSING_TRAFFIC`: instance chưa hoặc không còn nên nhận traffic mới.

Đây là **trạng thái availability theo lifecycle**, không phải kết quả tự động quét tất cả external dependencies.

### Sơ đồ lifecycle

~~~text
Application đang khởi động
  Liveness: BROKEN
  Readiness: REFUSING_TRAFFIC
            |
            v
Application context đã refresh
  Liveness: CORRECT
  Readiness: REFUSING_TRAFFIC
            |
            v
ApplicationRunner / CommandLineRunner hoàn tất
            |
            v
Application ready
  Liveness: CORRECT
  Readiness: ACCEPTING_TRAFFIC
            |
            v
Bắt đầu graceful shutdown
  Readiness: REFUSING_TRAFFIC
  Liveness: có thể vẫn CORRECT trong lúc dừng
~~~

Các thời điểm chuyển trạng thái chi tiết tùy lifecycle/phiên bản, nhưng ý nghĩa quan trọng là **liveness có thể tốt trước khi readiness tốt**.

Một ứng dụng có thể vừa tạo xong context, hoạt động bình thường về mặt process nhưng chưa hoàn tất runner hoặc công việc chuẩn bị, nên chưa nhận request mới.

## 8. Đọc ApplicationAvailability trong code

Spring Boot có thể cung cấp `ApplicationAvailability` cho các bean ứng dụng:

~~~java
package com.example.orders.monitoring;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Component;

@Component
public class AvailabilitySnapshot {

    private final ApplicationAvailability availability;

    public AvailabilitySnapshot(ApplicationAvailability availability) {
        this.availability = availability;
    }

    public boolean isAlive() {
        return availability.getLivenessState()
                == LivenessState.CORRECT;
    }

    public boolean isReady() {
        return availability.getReadinessState()
                == ReadinessState.ACCEPTING_TRAFFIC;
    }
}
~~~

Đây là cách đọc state trong quá trình chạy. Không nên thay thế toàn bộ quyết định nghiệp vụ của controller bằng việc gọi `isReady()` ở mọi request nếu load balancer đã dùng readiness để điều phối. Việc xử lý request đang đến trong lúc chuyển state còn phụ thuộc chính sách graceful shutdown.

### Đọc khi ứng dụng đã sẵn sàng

~~~java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class ReadyDiagnostics {

    private final ApplicationAvailability availability;

    ReadyDiagnostics(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @EventListener(ApplicationReadyEvent.class)
    void onReady() {
        System.out.println(
                "Readiness at ready event: "
                + availability.getReadinessState()
        );
    }
}
~~~

Listener này được tạo như bean và hoạt động ở giai đoạn context đã được chuẩn bị. Nó không phải cơ chế để nhận những startup events xảy ra trước khi context tồn tại.

Đừng dùng logging của availability state như bằng chứng duy nhất cho sức khỏe hệ thống ngoài; chỉ là state do application lifecycle/event quản lý.

## 9. LivenessStateHealthIndicator và ReadinessStateHealthIndicator

Spring Boot Actuator tích hợp availability với health bằng những indicator tương ứng:

- `LivenessStateHealthIndicator` dựa trên `LivenessState`.
- `ReadinessStateHealthIndicator` dựa trên `ReadinessState`.

Chúng chuyển những state của `ApplicationAvailability` thành health status có thể xuất qua HTTP health groups.

Ví dụ ý nghĩa:

| Availability state | Health status đại diện thường gặp | HTTP kết quả mặc định |
|---|---|---|
| `LivenessState.CORRECT` | `UP` | 200 |
| `LivenessState.BROKEN` | `DOWN` | 503 |
| `ReadinessState.ACCEPTING_TRAFFIC` | `UP` | 200 |
| `ReadinessState.REFUSING_TRAFFIC` | `OUT_OF_SERVICE` | 503 |

Khi thiết lập probes được bật, Actuator cung cấp các group dành riêng, thường có URL:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Đây là các **health groups**, không phải hai process, hai Spring context hoặc hai web server riêng.

## 10. Bật liveness/readiness probes ngoài Kubernetes

Trong môi trường Kubernetes được Spring Boot nhận diện, support cho probes thường được tự động kích hoạt khi Actuator và các điều kiện tương ứng có mặt.

Nếu chạy local, trong VM hoặc môi trường không được nhận diện là Kubernetes, có thể bật tường minh:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

Hoặc YAML:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Khi chức năng phù hợp đã được bật, thử:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

Phản hồi minh họa của instance đã sẵn sàng:

~~~json
{"status":"UP"}
~~~

Nếu readiness đang từ chối traffic:

~~~http
HTTP/1.1 503 Service Unavailable

{"status":"OUT_OF_SERVICE"}
~~~

Đường dẫn này giả định Actuator web base path là `/actuator`, management port dùng chung với application port và các endpoint/group không bị điều chỉnh bởi security hoặc exposure settings.

### Lưu ý phiên bản

Health groups cho Kubernetes probes được Spring Boot phát triển trong những dòng hiện đại, nổi bật từ Boot 2.3 trở đi. Các property và hành vi phụ trợ có thể thay đổi theo phiên bản. Với dự án đang sử dụng Boot 2.x đời cũ, không nên sao chép nguyên cấu hình Boot 3 mà bỏ qua tài liệu của bản đang chạy.

## 11. Health tổng hợp và các group có tập indicator khác nhau

Một điểm rất dễ nhầm:

~~~text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

**không nhất thiết** đánh giá cùng một tập contributor.

Ví dụ:

~~~text
Health root:
  db
  diskSpace
  ping
  other enabled health contributors

Liveness group:
  livenessState

Readiness group:
  readinessState
~~~

Trong cấu hình Kubernetes probes mặc định thông dụng của Spring Boot, liveness/readiness groups được tạo từ những availability-state indicators tương ứng. Các external health indicators như `db` thường **không tự động được đưa vào liveness/readiness groups**.

Vì vậy, hoàn toàn có thể có trạng thái:

| Endpoint | Kết quả | Giải thích |
|---|---|---|
| `/actuator/health` | `DOWN` | Một contributor như database đang lỗi |
| `/actuator/health/liveness` | `UP` | Process vẫn sống và không cần restart |
| `/actuator/health/readiness` | `UP` | ApplicationAvailability vẫn cho phép nhận traffic |

Đây không nhất thiết là mâu thuẫn hay bug. Các endpoint trả lời **các câu hỏi khác nhau**.

Nếu muốn readiness có thêm dependency check, cần chủ động cấu hình group — nhưng chỉ sau khi đánh giá tác động tới routing.

## 12. Kubernetes livenessProbe: chỉ nên thất bại nếu restart hữu ích

Ví dụ cấu hình một container trong Kubernetes Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-service
  template:
    metadata:
      labels:
        app: orders-service
    spec:
      containers:
        - name: app
          image: example/orders-service:1.0
          ports:
            - name: http
              containerPort: 8080
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
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
~~~

Ví dụ giả định container nghe cổng 8080 và Actuator/probes endpoints có thể truy cập từ kubelet.

Kubernetes liveness HTTP probe kiểm tra response HTTP. Nếu liveness liên tục thất bại đủ `failureThreshold` lần, kubelet sẽ coi container không healthy và khởi động lại nó theo chính sách container/Pod.

### Một số trường hợp liveness nên phản ánh BROKEN

- Một lỗi trạng thái nội bộ không thể phục hồi bằng retry hoặc tiếp tục xử lý.
- Một thành phần điều khiển cốt lõi của process bị mắc kẹt nghiêm trọng, cần restart.
- Ứng dụng phát hiện invariant nội bộ không thể phục hồi và chủ động phát readiness/liveness state phù hợp.

### Một số trường hợp không nên làm liveness DOWN

- Database tạm thời không truy cập được.
- Payment provider bên ngoài trả lỗi 503.
- Một message broker dùng chung giữa mọi replica bị mất kết nối.
- Một downstream API vượt timeout.
- Bộ cache bên ngoài mất kết nối nhưng process vẫn có thể chạy/retry.

Liveness là quyết định “restart container có hợp lý không”, không phải “tất cả dịch vụ phụ thuộc có đang UP không”.

## 13. Kubernetes readinessProbe: quyết định nhận traffic

Cùng Deployment ở trên, readinessProbe dùng:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Khi endpoint readiness không còn thành công, Kubernetes sẽ đánh dấu Pod không ready. Các Service dựa trên endpoint readiness thường không định tuyến request mới tới Pod đó.

Tuy nhiên:

- Container **không tự restart chỉ vì readiness failure**.
- Một Pod có thể tiếp tục chạy công việc nền.
- Khi readiness phục hồi, Pod có thể lại tham gia nhận traffic mà không cần restart.
- Thay đổi trạng thái readiness không tự đóng toàn bộ connection đang mở hoặc bảo đảm các request in-flight dừng ngay tức thì.

Readiness hữu ích cho:

1. Ứng dụng chưa sẵn sàng sau bootstrap.
2. Instance đang warm-up dữ liệu nội bộ thiết yếu.
3. Replica chưa đồng bộ state cần thiết.
4. Instance chuyển sang chế độ drain để bảo trì.
5. Instance đang graceful shutdown, cần dừng nhận request mới.

### Không biến readiness thành phép health check quá nặng

Kubelet có thể gọi readiness nhiều lần mỗi phút trên mỗi replica. Nếu mỗi request readiness lại chạy một SQL query phức tạp hoặc gọi một upstream chậm, chính hệ thống probe có thể tạo thêm tải đáng kể.

Với dependency bên ngoài, cân nhắc dùng trạng thái được cập nhật định kỳ có timeout/circuit breaker và được quan sát riêng, thay vì tạo network call dài trong mỗi health request.

## 14. Startup probe: giải quyết bài toán khởi động lâu

Một ứng dụng có thể cần thời gian để tải cache, tạo connection pool, áp dụng initialization hoặc thực hiện các bước bootstrap hợp lệ.

Nếu livenessProbe bắt đầu kiểm tra quá sớm, nó có thể restart container trước khi ứng dụng kịp khởi động. Kubernetes có **startupProbe** để xử lý giai đoạn này.

Ví dụ:

~~~yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 30
~~~

Với cấu hình minh họa, startup probe có ngân sách thất bại khoảng 30 lần kiểm tra, mỗi lần cách nhau 5 giây, trước khi Kubernetes coi startup không thành công. Đây là ngân sách về số lần/thời điểm kiểm tra, không phải một lời hứa tổng thời gian chính xác vì timeout, scheduling và các yếu tố runtime khác cũng tác động.

Khi startupProbe được cấu hình, Kubernetes **trì hoãn thực thi liveness và readiness probes** cho đến khi startupProbe thành công. Sau đó, liveness và readiness hoạt động theo cấu hình riêng.

Sơ đồ:

~~~text
Container started
       |
       v
startupProbe
       |
  +----+----+
  |         |
Fail      Success
  |         |
Retry       v
  |    Start liveness/readiness checks
  v
Over threshold
  |
  v
Restart container
~~~

Startup probe thường có thể dùng cùng endpoint liveness phù hợp với ứng dụng. Nó **không phải** một Actuator status mới; đây là cơ chế của Kubernetes.

### Khi nào nên dùng startupProbe?

- Thời gian boot có thể dài hoặc biến động đáng kể.
- Kubelet kiểm tra liveness trước khi HTTP server kịp lắng nghe.
- Ứng dụng cần warm-up nhưng không muốn nới lỏng liveness threshold cho toàn bộ thời gian vận hành.

Nếu ứng dụng nhanh và ổn định, startupProbe có thể không cần thiết. Nhưng với hệ thống thực tế có khởi động phức tạp, nó thường rõ ràng hơn việc đặt `initialDelaySeconds` của liveness quá lớn rồi chấp nhận phát hiện deadlock chậm trong suốt vòng đời.

## 15. Liveness/readiness còn liên quan đến graceful shutdown

Một ứng dụng đang shutdown không nhất thiết “chết” ngay lập tức. Nó có thể cần dừng nhận request mới, hoàn tất request đang xử lý và giải phóng tài nguyên.

Spring Boot có cơ chế graceful shutdown của embedded web server trên những phiên bản/hệ thống hỗ trợ. Ví dụ:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Khi ứng dụng chuyển sang shutdown, readiness có thể trở thành `REFUSING_TRAFFIC` để thông báo không nên nhận request mới, trong khi process vẫn còn sống đủ lâu để dọn dẹp tài nguyên.

Các yếu tố cần phối hợp:

- Readiness state chuyển sang refusing khi dừng.
- Kubernetes loại Pod khỏi các EndpointSlices/đường định tuyến theo readiness.
- Load balancer và proxy cần thời gian cập nhật trạng thái.
- In-flight requests cần thời gian xử lý.
- `terminationGracePeriodSeconds` ở Kubernetes cần phù hợp với chính sách graceful shutdown.
- Ứng dụng phải xử lý tín hiệu dừng phù hợp, không chỉ bị kill ngay.

Không nên ép liveness thành `BROKEN` chỉ vì muốn Pod ngừng nhận traffic. Liveness failure có thể kích hoạt restart trong lúc điều bạn cần là drain và shutdown có trật tự.

## 16. Khi management port khác application port

Spring Boot Actuator có thể chạy trên management port riêng:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
~~~

Khi đó:

~~~text
Main application server: 8080
Management HTTP server: 8081
~~~

Một vấn đề vận hành quan trọng: **probe chạy thành công trên management port không nhất thiết chứng minh application port đang chấp nhận kết nối**.

Ví dụ management context/server vẫn trả HTTP 200 nhưng main server listener gặp lỗi riêng. Kubernetes có thể tiếp tục coi container ready dù request thực tế vào cổng ứng dụng không phục vụ được.

### 16.1. Additional paths trên main application port

Với các dòng Spring Boot hỗ trợ, có thể bật thêm probe endpoints trên main server port:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

Các đường dẫn bổ sung điển hình trên **main application port**:

~~~text
GET /livez
GET /readyz
~~~

Khi cấu hình đó có hiệu lực, Kubernetes có thể kiểm tra trực tiếp cổng ứng dụng:

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

Vẫn phải hiểu rằng một HTTP endpoint đơn giản trả 200 không chứng minh mọi route nghiệp vụ đang hoạt động. Tuy nhiên, việc check cùng main server port giúp tránh một lớp sai lệch rõ ràng giữa management server và application server.

### 16.2. Port riêng không đồng nghĩa luôn sai

Có những hệ thống chủ động tách management port để bảo vệ endpoint, giới hạn quyền truy cập hoặc tách monitoring traffic. Điều đó có thể hợp lý.

Nhưng với liveness/readiness của một web workload, hãy quyết định rõ probe cần kiểm tra:

- Chỉ process availability state?
- Hay còn cả khả năng main application server nhận HTTP request?

Với Kubernetes HTTP workload, endpoint cùng main server port thường cung cấp tín hiệu gần hơn với khả năng phục vụ thực tế.

## 17. Tự tạo HealthIndicator cho dependency quan trọng

Giả sử ứng dụng phụ thuộc vào một search backend. Bạn muốn có một health indicator riêng để quan sát nó.

Ví dụ service lưu trạng thái nhẹ đã được xác định bởi một cơ chế kiểm tra định kỳ:

~~~java
package com.example.orders.monitoring;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class SearchBackendState {

    private final AtomicBoolean available = new AtomicBoolean(true);

    public boolean isAvailable() {
        return available.get();
    }

    public void setAvailable(boolean value) {
        available.set(value);
    }
}
~~~

Một health indicator:

~~~java
package com.example.orders.monitoring;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("searchBackendHealthIndicator")
public class SearchBackendHealthIndicator implements HealthIndicator {

    private final SearchBackendState state;

    public SearchBackendHealthIndicator(SearchBackendState state) {
        this.state = state;
    }

    @Override
    public Health health() {
        if (state.isAvailable()) {
            return Health.up().build();
        }
        return Health.down().build();
    }
}
~~~

Ví dụ này chỉ minh họa việc report một state. `AtomicBoolean(true)` không phải cách production để kiểm tra một search backend thật; trạng thái phải đến từ một cơ chế giám sát có ý nghĩa, tránh giữ false/true vĩnh viễn sau thay đổi thực tế.

Ở mức Spring Boot Actuator, bean có hậu tố `HealthIndicator` thường đóng góp health contributor tên `searchBackend`.

### 17.1. Chỉ thêm dependency đó vào readiness khi có chủ đích

Một lựa chọn cấu hình:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.group.readiness.include=readinessState,searchBackend
~~~

Khi đó readiness group xét cả state của ứng dụng và indicator `searchBackend`.

**Tác động cần cân nhắc:** Nếu search backend dùng chung cho tất cả Pods bị lỗi, readiness của tất cả Pods có thể về 503. Hãy xác nhận đây thực sự là hành vi mong muốn.

Không thêm `searchBackend` vào liveness chỉ vì muốn “giám sát đầy đủ”. Một dependency bên ngoài không nhất thiết liên quan tới việc restart process.

### 17.2. Nếu muốn quan sát dependency mà không làm Pod unready

Bạn vẫn có thể để `searchBackend` trong health root hoặc tạo một group giám sát riêng, trong khi readiness chỉ phản ánh availability state.

Ý nghĩa kiến trúc:

~~~text
/actuator/health
   -> giám sát tổng hợp các component

/actuator/health/liveness
   -> quyết định có nên restart instance không

/actuator/health/readiness
   -> quyết định instance có nhận traffic mới không
~~~

Tách các mục tiêu này giúp monitoring alert có thể nhận diện lỗi của dependency mà không vô tình kích hoạt hàng loạt thao tác điều phối không cần thiết.

## 18. Tạo health group riêng cho một hệ thống con

Spring Boot Actuator có thể nhóm health contributors theo mục tiêu kiểm tra. Ví dụ cấu hình một group dành cho backend phụ trợ:

~~~yaml
management:
  endpoint:
    health:
      group:
        search:
          include: searchBackend
          show-details: never
~~~

Khi group được khai báo và endpoint được expose phù hợp:

~~~text
GET /actuator/health/search
~~~

Một group riêng giúp hệ thống giám sát backend hiểu tình trạng search mà không buộc Kubernetes phải dùng kết quả đó làm liveness hoặc readiness.

### Các group không phải Kubernetes probes tự động

Tự tạo group `search` **không làm Kubernetes tự biết đến nó**. Kubernetes chỉ sử dụng những URL mà Deployment/Pod `livenessProbe`, `readinessProbe` hoặc `startupProbe` đã cấu hình.

Tương tự, một health group có status `DOWN` không tự gây restart container nếu không có hệ thống điều phối nào dùng nó làm liveness probe.

### Phạm vi check ảnh hưởng ý nghĩa kết quả

Một group có thể chọn contributor khác nhau, nên cần đặt tên theo mục đích. Ví dụ `dependencies` chỉ kiểm tra downstream services không nên được giới thiệu cho người vận hành như một câu trả lời “pod có cần restart không”.

## 19. Chủ động thay đổi ReadinessState trong ứng dụng

Trong một số bài toán, ứng dụng có một pha warm-up hoặc cần từ chối traffic trong lúc chuyển đổi trạng thái. Có thể xuất bản `AvailabilityChangeEvent` để thay đổi availability state.

Ví dụ service bật/tắt readiness theo trạng thái bảo trì:

~~~java
package com.example.orders.monitoring;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class TrafficControlService {

    private final ApplicationEventPublisher publisher;

    public TrafficControlService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void refuseNewTraffic() {
        AvailabilityChangeEvent.publish(
                publisher,
                ReadinessState.REFUSING_TRAFFIC
        );
    }

    public void acceptTraffic() {
        AvailabilityChangeEvent.publish(
                publisher,
                ReadinessState.ACCEPTING_TRAFFIC
        );
    }
}
~~~

Khi group readiness dùng `readinessState` indicator, việc thay state tương ứng sẽ làm endpoint phản ánh state mới.

### Cần điều kiện chuyển trạng thái rõ ràng

Không nên tự đặt `ACCEPTING_TRAFFIC` ngay đầu một constructor hoặc `@PostConstruct` mà chưa chứng minh ứng dụng đã sẵn sàng. Spring Boot tự quản lý những mốc lifecycle thông thường; publication thủ công nên dành cho tình huống ứng dụng có thêm điều kiện thật sự.

Nếu có nhiều thành phần cùng phát readiness change events, cần thiết kế nguồn sở hữu state và cách phối hợp. Một component tự phát `ACCEPTING_TRAFFIC` không nên vô tình ghi đè quyết định từ chối traffic của một quá trình bảo trì quan trọng khác.

### Đánh dấu LivenessState.BROKEN

Ứng dụng cũng có thể phát `LivenessState.BROKEN` cho một lỗi nội bộ không thể phục hồi. Nhưng cần rất thận trọng: làm vậy có thể dẫn đến restart liên tục, đặc biệt nếu nguyên nhân là dependency bên ngoài đang lỗi.

Chỉ chọn `BROKEN` khi process đang ở trạng thái mà **restart là hành động phục hồi phù hợp**, không phải để thay thế logging hoặc alerting.

## 20. Một health check có thể gây ảnh hưởng đến ứng dụng

Health indicator là code chạy trong ứng dụng. Nếu check quá nặng, không timeout hoặc ném exception không được xử lý đúng, hệ thống monitoring có thể góp phần làm dịch vụ chậm hoặc mất khả năng phục vụ.

Một số rủi ro:

- Mỗi probe thực hiện query phức tạp trên database.
- Mỗi probe yêu cầu HTTP request tới nhiều downstream services.
- Health check chiếm hết thread pool hoặc connection pool.
- Nhiều Pods cùng probe một shared dependency theo nhịp, tạo tải đột biến.
- Probe timeout quá thấp gây false negative khi hệ thống chỉ chậm nhất thời.
- Probe timeout quá cao làm việc phát hiện sự cố chậm.
- Health check chứa side effect làm thay đổi dữ liệu thay vì chỉ quan sát trạng thái.

### Thiết kế HealthIndicator an toàn hơn

Một indicator nên:

1. Kiểm tra đúng điều kiện mà người vận hành cần quan sát.
2. Có thời gian xử lý ngắn, timeout và giới hạn tài nguyên.
3. Không thay đổi state nghiệp vụ.
4. Trả trạng thái rõ ràng thay vì im lặng nuốt exception.
5. Hạn chế thông tin nhạy cảm trong details.
6. Không biến sự cố của downstream thành vòng lặp restart không cần thiết.

Có thể dùng **cached state** được cập nhật bởi cơ chế giám sát riêng cho những dependency kiểm tra tốn kém. Nhưng cached state cũng phải có TTL hoặc cơ chế đánh dấu stale rõ ràng; một giá trị “UP” cũ vô hạn không đáng tin.

## 21. Liveness failure và readiness failure có hậu quả khác nhau

Giả sử có ba Pods A, B, C.

### Tình huống A: Pod A bị deadlock nội bộ

~~~text
Pod A: Liveness DOWN, Readiness có thể không phản hồi
Pod B: Liveness UP, Readiness UP
Pod C: Liveness UP, Readiness UP
~~~

Kubernetes có thể restart container của Pod A. B và C tiếp tục nhận traffic. Nếu deadlock chỉ ảnh hưởng một instance và restart khắc phục được, liveness failure có ích.

### Tình huống B: Pod A đang warm-up cache

~~~text
Pod A: Liveness UP, Readiness OUT_OF_SERVICE
Pod B: Liveness UP, Readiness UP
Pod C: Liveness UP, Readiness UP
~~~

Pod A vẫn sống và tiếp tục warm-up; Kubernetes không route request mới tới A cho đến khi nó ready. Restart A lúc này có thể phá hỏng tiến độ warm-up.

### Tình huống C: Database dùng chung bị lỗi

~~~text
Shared database DOWN
          |
     +----+----+
     |    |    |
    Pod A Pod B Pod C
~~~

Một health tổng hợp có thể `DOWN` ở cả ba Pods. Không nên mặc nhiên suy ra cả ba process phải restart. Readiness có nên `OUT_OF_SERVICE` không là quyết định theo khả năng phục vụ nghiệp vụ của từng Pod và toàn hệ thống.

### Tình huống D: Rolling deployment

Pod mới vừa được tạo nhưng chưa ready. Pod cũ vẫn phục vụ traffic.

Readiness giúp Kubernetes biết **khi nào instance mới có thể tham gia routing**. Nếu readiness báo `UP` quá sớm trước khi ứng dụng thực sự sử dụng được, rolling deployment có thể đưa traffic tới instance chưa sẵn sàng và gây lỗi gián đoạn.

Đây là lý do readiness không chỉ là một phép kiểm tra process “có trả HTTP 200 hay không”.

## 22. Định nghĩa probes và thresholds trong Kubernetes

Một cấu hình đầy đủ hơn:

~~~yaml
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
  failureThreshold: 3
  successThreshold: 1

startupProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 30
~~~

Ví dụ này dùng main-port aliases `/livez` và `/readyz`, nên ứng dụng phải bật cấu hình `management.endpoint.health.probes.add-additional-paths=true` (hoặc cấu hình tương đương được hỗ trợ) trước khi triển khai.

Ý nghĩa một số tham số:

| Tham số | Mục đích |
|---|---|
| `periodSeconds` | Chu kỳ chạy probe |
| `timeoutSeconds` | Giới hạn thời gian chờ mỗi lần check |
| `failureThreshold` | Số lần thất bại liên tiếp trước khi coi probe thất bại theo chính sách |
| `successThreshold` | Số lần thành công liên tiếp để được coi thành công trong trường hợp hỗ trợ |
| `initialDelaySeconds` | Khoảng chờ trước khi bắt đầu probe, với điều kiện/tương tác cùng các probe khác theo Kubernetes |

Không đặt timeout/failureThreshold theo cảm tính. Một ứng dụng có GC pauses, slow startup hoặc đặc điểm latency khác sẽ cần ngưỡng hợp lý; đặt ngưỡng quá nhạy có thể tạo restart hoặc traffic flap dù ứng dụng chưa hỏng thật.

## 23. HTTP endpoint trả 200 không đủ chứng minh nghiệp vụ hoạt động

Ngay cả khi `/actuator/health/liveness` và `/readiness` đều trả 200, vẫn có thể xảy ra:

- Một endpoint nghiệp vụ trả exception.
- Database query quan trọng bị lỗi.
- Một payment gateway không thể thực hiện giao dịch.
- Dữ liệu cache đã cũ.
- Một background queue consumer bị dừng.
- Ứng dụng trả HTTP 200 cho request nhưng xử lý sai dữ liệu.

Vì vậy, **health probes không thay thế toàn bộ observability**.

Các tín hiệu bổ sung:

- Metrics: error rate, latency, saturation, queue lag.
- Logs: exception và thông tin có cấu trúc, không chứa secret.
- Distributed tracing: luồng request qua nhiều services.
- Business-level monitoring: các chỉ số phản ánh công việc thực.
- Synthetic checks: kiểm tra những hành trình nghiệp vụ quan trọng.
- Alerting: dựa trên SLO và tác động người dùng, không chỉ một health endpoint.

Health endpoint là một giao diện hữu ích cho điều phối, không phải chứng nhận chất lượng toàn bộ ứng dụng.

## 24. Bảo mật và quyền truy cập health endpoints

Actuator endpoints có thể trả status và, nếu được cấu hình, các chi tiết như database, disk space hoặc custom contributor. Dữ liệu này có thể hữu ích cho người vận hành nhưng cũng có thể tiết lộ cấu trúc hạ tầng.

Ví dụ property:

~~~yaml
management:
  endpoint:
    health:
      show-details: never
~~~

Các giá trị hiển thị details có thể gồm `never`, `when_authorized`, `always` theo phiên bản. Các health groups có thể có thiết lập riêng.

Nguyên tắc:

- Không expose mọi Actuator endpoints ra Internet chỉ vì cần kubelet gọi health probe.
- Dùng network policy, authentication và authorization phù hợp.
- Không đưa connection strings chứa password, token hoặc nội dung secret vào `Health.withDetail(...)`.
- Cân nhắc việc expose health endpoint trên main port: nội dung nên tối giản cho probe, phần diagnostic chuyên sâu để ở hệ thống giám sát bảo vệ tốt hơn.
- Nếu dùng `management.server.port` riêng, phải kiểm soát cả network access và khả năng probe phản ánh đúng main server.

Một health check có thể trả ít thông tin ra ngoài trong khi hệ thống monitoring nội bộ vẫn có metrics/alerts chi tiết riêng.

## 25. Kiểm thử health và availability ở đúng phạm vi

Một unit test cho custom `HealthIndicator` có thể kiểm tra logic:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Status;

class SearchBackendHealthIndicatorTest {

    @Test
    void returnsDownWhenSearchBackendUnavailable() {
        SearchBackendState state = new SearchBackendState();
        state.setAvailable(false);

        SearchBackendHealthIndicator indicator =
                new SearchBackendHealthIndicator(state);

        assertThat(indicator.health().getStatus())
                .isEqualTo(Status.DOWN);
    }
}
~~~

Test trên chứng minh logic indicator, **không chứng minh** readiness group đã được cấu hình bao gồm indicator đó.

### 25.1. Kiểm tra endpoint sau khi ứng dụng khởi động

Có thể tạo một integration test với Actuator endpoint đã bật:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "management.endpoint.health.probes.enabled=true"
)
class HealthProbesIntegrationTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void livenessEndpointRespondsAfterStartup() {
        ResponseEntity<String> response = rest.getForEntity(
                "/actuator/health/liveness",
                String.class
        );

        assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(response.getBody()).contains("UP");
    }
}
~~~

Ví dụ giả định application context đã khởi động thành công, Actuator health endpoint được expose trên cùng port và không bị security rule chặn test client. Nếu dự án có management port khác, authentication hoặc custom base path, cần điều chỉnh test phù hợp.

### 25.2. Test readiness khi từ chối traffic

Nếu ứng dụng chủ động phát `AvailabilityChangeEvent` với `ReadinessState.REFUSING_TRAFFIC`, có thể kiểm thử rằng readiness indicator/group trả status tương ứng, rồi chuyển lại `ACCEPTING_TRAFFIC` sau test.

Cần tránh chia sẻ một application context có readiness state bị thay đổi giữa nhiều tests mà không reset. Nếu không, các test phía sau có thể thất bại do state còn sót lại.

### 25.3. Kiểm tra từ Kubernetes, không chỉ test Spring

Một endpoint trả đúng status trong test không bảo đảm manifest Kubernetes đã trỏ đúng URL/port.

Khi triển khai, kiểm tra:

- Pod spec có `livenessProbe`, `readinessProbe` và `startupProbe` nếu cần.
- Probe path đúng với Actuator base path hoặc aliases.
- Probe port là main application port hay management port như thiết kế.
- Kubelet có thể kết nối tới port đó không.
- `readiness` failure thực sự làm Pod chuyển trạng thái NotReady.
- `liveness` failure được xử lý theo policy restart như mong muốn.
- Thresholds phù hợp với startup và độ trễ ứng dụng.

Đây là kiểm thử tích hợp giữa ứng dụng và orchestrator, không thể thay hoàn toàn bằng unit test.

## 26. Chẩn đoán những lỗi hay gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `/actuator/health` trả UP nhưng readiness trả 503 | AvailabilityState là `REFUSING_TRAFFIC` | Kiểm tra lifecycle, runner, warm-up hoặc event đổi readiness |
| `/actuator/health` DOWN nhưng liveness UP | Health root có contributor down; liveness chỉ phản ánh process state | Đây có thể là thiết kế đúng; phân biệt health và khả năng restart |
| `/actuator/health/liveness` trả 404 | Probe groups chưa bật hoặc path/base path khác | Bật `management.endpoint.health.probes.enabled`, kiểm tra Actuator configuration |
| Kubernetes restart liên tục khi DB lỗi | Dùng `/actuator/health` làm liveness hoặc đưa DB vào liveness | Chỉ dùng livenessState, để external dependency ra khỏi liveness |
| Tất cả Pods NotReady khi backend chung lỗi | Readiness phụ thuộc backend chung | Đánh giá có thực sự nên ngắt toàn Service không |
| Pod sống nhưng không nhận traffic | Readiness failing hoặc service selector/endpoints không đúng | Xem readiness endpoint, Pod conditions, Service/EndpointSlice |
| Health trên management port UP nhưng API port lỗi | Probe chỉ chạy trên management context/server | Cân nhắc main-port `/livez`, `/readyz` |
| Pod mới bị restart trước khi startup xong | Liveness timeout/ngưỡng quá ngắn, chưa có startupProbe | Thêm startupProbe và chỉnh ngân sách bootstrap |
| Probe chậm làm tốn nhiều tài nguyên | Indicator truy vấn DB/upstream nặng mỗi lần | Dùng check nhẹ/cached state có TTL và timeout |
| Readiness luôn 503 sau khi ứng dụng đã ready | Event/logic ứng dụng liên tục giữ `REFUSING_TRAFFIC` | Kiểm tra ownership và thứ tự `AvailabilityChangeEvent` |
| Custom indicator không xuất hiện trong group | Sai contributor ID hoặc group include config | Kiểm tra tên bean và cấu hình include |
| Actuator endpoint trả 401/403 | Security hạn chế truy cập probe | Cho phép đường dẫn cần thiết theo chính sách, không mở toàn bộ Actuator |
| Pod báo Ready nhưng request thực tế lỗi | Probe không kiểm tra đủ các điều kiện phục vụ | Kiểm tra main port, metrics/error rate và readiness semantics |

Một quy trình điều tra hiệu quả:

~~~text
1. Đọc HTTP status + body từ endpoint được cấu hình
            |
            v
2. Xem endpoint là health root, liveness hay readiness
            |
            v
3. Xác định indicator/group nào đóng góp vào status
            |
            v
4. Kiểm tra ApplicationAvailability và lifecycle state
            |
            v
5. Kiểm tra Kubernetes probe path, port, thresholds
            |
            v
6. Xác định lỗi local instance hay dependency dùng chung
            |
            v
7. Chọn restart, drain, retry, alert hoặc khắc phục backend
~~~

## 27. Các quan niệm sai phổ biến

| Quan niệm | Cách hiểu đúng |
|---|---|
| “Health là UP thì ứng dụng chắc chắn phục vụ mọi request.” | Health chỉ bao phủ tập indicator được cấu hình. |
| “Health DOWN nghĩa là phải restart process.” | Health DOWN có thể vì dependency ngoài mà restart không giải quyết được. |
| “Liveness và readiness là cùng một endpoint đổi tên.” | Chúng phản ánh hai quyết định vận hành khác nhau. |
| “Readiness fail thì Kubernetes restart container.” | Readiness thất bại ảnh hưởng routing, không tự yêu cầu restart. |
| “Liveness fail thì Kubernetes chỉ ngừng gửi traffic.” | Liveness thất bại vượt ngưỡng khiến kubelet restart container. |
| “Startup probe là một HealthIndicator đặc biệt của Spring Boot.” | Startup probe là cơ chế của Kubernetes; có thể dùng endpoint Boot sẵn có. |
| “Mọi HealthIndicator tự động nằm trong readiness.” | Mặc định group thường chỉ gồm readinessState; muốn thêm contributor cần cấu hình. |
| “DB chập chờn nên liveness phải DOWN.” | Restart process có thể làm tình hình xấu hơn; dùng monitoring/retry/readiness theo nhu cầu. |
| “Actuator trên port khác trả UP nên main port chắc chắn ổn.” | Management server có thể còn hoạt động khi main server không nhận request. |
| “Chỉ cần readiness UP là không cần metrics, log hay traces.” | Availability probes không thay thế observability và SLO monitoring. |

## 28. Nguyên tắc thiết kế health/probes

1. **Phân biệt mục tiêu đo:** health tổng hợp để chẩn đoán, liveness để quyết định restart, readiness để quyết định routing.
2. **Liveness chỉ nên phản ánh lỗi local mà restart giúp phục hồi.** Không đặt database, broker hay upstream API dùng chung vào liveness một cách máy móc.
3. **Readiness phản ánh khả năng phục vụ traffic của instance.** Cân nhắc tác động khi mọi Pod cùng phụ thuộc một backend.
4. **Startup probe bảo vệ giai đoạn boot dài.** Đừng dùng liveness threshold quá nhạy để restart ứng dụng trước khi nó khởi động xong.
5. **Sử dụng availability states của Boot.** `LivenessState` và `ReadinessState` giúp diễn đạt lifecycle, còn health groups đưa trạng thái lên HTTP.
6. **Kiểm soát health group membership.** Chỉ thêm contributor khi biết kết quả của nó phải ảnh hưởng quyết định nào.
7. **Giữ checks nhẹ và an toàn.** Có timeout, không tạo side effect và không gọi mạng/DB quá nặng mỗi chu kỳ.
8. **Kiểm tra trên main port khi phù hợp.** Nếu dùng management port riêng, đánh giá nguy cơ probe báo tốt khi server ứng dụng không nhận request.
9. **Không công khai details nhạy cảm.** Hạn chế Actuator endpoints và quyền truy cập.
10. **Kiểm thử từ ứng dụng đến Kubernetes.** Xác minh status code, group, URL/port, Pod conditions, thresholds và hành vi thực tế.
11. **Không dùng probe thay thế metrics, tracing hoặc business monitoring.** Chúng bổ sung cho nhau.
12. **Quan tâm graceful shutdown.** Readiness phải hỗ trợ việc ngừng nhận traffic có trật tự, không biến drain thành restart loop.

## 29. Tổng kết

Trong Spring Boot Actuator, **health status** là kết quả đánh giá các `HealthIndicator`/`HealthContributor` trong một group. **Liveness** là trạng thái của tiến trình cho biết có cần restart khi nó hỏng; **readiness** là trạng thái của instance cho biết có nên nhận traffic mới.

Spring Boot đưa `ApplicationAvailability`, `LivenessState` và `ReadinessState` vào các health groups để Kubernetes có thể gọi `/actuator/health/liveness` và `/actuator/health/readiness`. Kubernetes dùng liveness để quyết định restart container, readiness để quyết định đưa Pod vào routing, còn startup probe để cho ứng dụng đủ thời gian khởi động.

**Điểm cần nhớ:** Không dùng một endpoint health tổng hợp làm liveness chỉ vì nó có tên “health”. Hãy thiết kế từng phép kiểm tra theo **hành động mà hệ thống vận hành sẽ thực hiện khi phép kiểm tra thất bại**. Phân biệt đúng health, liveness và readiness giúp tránh restart hàng loạt không cần thiết, tránh gửi traffic vào instance chưa sẵn sàng và tăng độ ổn định của ứng dụng Spring Boot trong môi trường production.
