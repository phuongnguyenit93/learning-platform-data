# Lý do lỗi dịch vụ bên ngoài không nên mặc nhiên làm liveness thất bại

Một ứng dụng Spring Boot có thể **vẫn hoạt động đúng về mặt tiến trình** dù database, cache, message broker hoặc HTTP API mà nó gọi đang gặp sự cố. Lúc ấy, ứng dụng có thể trả lỗi có kiểm soát, retry, mở circuit breaker, phục vụ chức năng còn hoạt động hoặc chờ dependency hồi phục. Nếu mỗi lần dependency lỗi đều khiến **liveness probe** thất bại, Kubernetes có thể liên tục khởi động lại những container vốn không hỏng. Kết quả thường là nhiều gián đoạn hơn, không phải khả năng tự phục hồi tốt hơn.

Nguyên tắc thiết kế:

> **Liveness trả lời: “Tiến trình này có bị hỏng đến mức cần khởi động lại để phục hồi không?” Readiness trả lời: “Instance này hiện có nên nhận traffic mới không?” Trạng thái một dependency bên ngoài không tự động trả lời được cả hai câu hỏi.**

Bài học tập trung vào Spring Boot Application Runtime, `ApplicationAvailability`, Spring Boot Actuator và Kubernetes probes. Các ví dụ dùng **Java 17+ và Spring Boot 3.3.x**; cách lựa chọn liveness/readiness cũng áp dụng cho hệ thống container tương tự.

## 1. Ba loại probe có mục đích khác nhau

Kubernetes thường sử dụng ba loại probe:

| Probe | Câu hỏi thực chất | Điều Kubernetes thường làm khi thất bại đạt ngưỡng |
|---|---|---|
| **Liveness** | Container này còn khả năng hoạt động hoặc tự hồi phục không? | **Khởi động lại container** theo chính sách của Pod. |
| **Readiness** | Instance hiện có đủ điều kiện nhận request mới không? | Đánh dấu Pod **NotReady**, bỏ khỏi tập endpoint phục vụ traffic của Service tương ứng; không tự restart chỉ vì readiness thất bại. |
| **Startup** | Ứng dụng đã khởi động đủ để bắt đầu các kiểm tra thông thường chưa? | Cho startup một khoảng thời gian riêng; nếu liên tiếp thất bại quá ngưỡng, container bị restart. Khi startup probe chưa thành công, Kubernetes chưa chạy liveness/readiness probes. |

Đừng dùng ba probe với cùng ý nghĩa “mọi dependency đều phải UP”. Các phản ứng vận hành của Kubernetes **khác nhau**; do đó một phép kiểm tra không phù hợp có thể biến lỗi tạm thời thành vòng lặp restart.

Hai ví dụ đối lập:

- **Có thể cần liveness thất bại:** một deadlock nghiêm trọng khiến tiến trình không còn xử lý được công việc và không thể tự phục hồi. Restart có khả năng giải quyết vấn đề nội bộ đó.
- **Không nên mặc nhiên làm liveness thất bại:** database đang timeout trong 30 giây, trong khi JVM vẫn nhận request, trả lỗi có kiểm soát, cập nhật metrics và sẽ tự kết nối lại khi database hồi phục.

Liveness nên **rẻ, nhanh, phản ánh trạng thái nội bộ**, không phải một bài kiểm tra tích hợp liên tục gọi nhiều dịch vụ mạng.

## 2. Hậu quả của việc gắn liveness vào database/API ngoài

Giả sử có ba Pod Spring Boot dùng chung một database:

~~~text
                Kubernetes Service
                  /     |     \
                Pod A  Pod B  Pod C
                  \     |     /
                  Database (dùng chung)
~~~

Nếu mỗi liveness probe đều mở kết nối đến database và báo fail khi database lỗi, diễn biến có thể là:

~~~mermaid
flowchart TD
    A["Database dùng chung gặp sự cố ngắn"] --> B["Probe ở Pod A/B/C đều thất bại"]
    B --> C["Kubernetes restart nhiều container"]
    C --> D["Instance đang phục vụ tốt bị dừng"]
    D --> E["Warm-up lại cache, tạo pool kết nối, chạy initialization"]
    E --> F["Lưu lượng và kết nối dồn thêm vào dependency"]
    F --> G["Có nguy cơ lỗi dây chuyền/restart lặp"]
~~~

Vấn đề cơ bản là **restart ứng dụng không sửa được một database ở bên ngoài**. Thậm chí khi database hồi phục, việc cả loạt Pod cùng tạo pool kết nối, chạy truy vấn khởi động và làm nóng cache có thể gây áp lực mới lên dependency.

Các tác động thường gặp:

1. **Mất capacity:** những Pod đang trả được response hợp lệ cho các endpoint không cần database cũng bị restart.
2. **Gián đoạn request:** kết nối và request đang xử lý có thể bị ngắt, tùy graceful shutdown và timeout.
3. **Tăng áp lực dependency:** nhiều instance đồng thời reconnect, refresh token, rebuild cache hoặc subscribe lại broker.
4. **Mất lợi ích của retry/fallback:** logic resilience trong ứng dụng không có thời gian để phát huy tác dụng.
5. **Khó chẩn đoán:** restart count tăng liên tục che lấp root cause thực sự ở database/API bên ngoài.
6. **Lỗi có thể lan rộng:** trong lúc một số Pod đang restart, tải dồn vào số Pod còn lại.

Đây là một dạng **cascading failure** hay “thundering herd”. Vì vậy Spring Boot khuyến cáo không đưa kiểm tra hệ thống bên ngoài vào nhóm liveness một cách mặc định.

## 3. Spring Boot biểu diễn liveness và readiness ra sao?

Spring Boot có abstraction `ApplicationAvailability`, với hai nhóm trạng thái quan trọng:

| Trạng thái | Các giá trị thường gặp | Ý nghĩa |
|---|---|---|
| `LivenessState` | `CORRECT`, `BROKEN` | Trạng thái nội bộ có phù hợp để tiến trình tiếp tục chạy/tự phục hồi không. |
| `ReadinessState` | `ACCEPTING_TRAFFIC`, `REFUSING_TRAFFIC` | Instance có sẵn sàng nhận traffic mới hay không. |

Spring Boot quản lý thay đổi availability trong chuỗi khởi động và đóng ứng dụng. Một cách hiểu đơn giản:

~~~text
Startup ban đầu:
    liveness  = BROKEN
    readiness = REFUSING_TRAFFIC
Khi context đã khởi động đủ:
    liveness  = CORRECT
    readiness = REFUSING_TRAFFIC (runner có thể còn chạy)
Sau khi startup hoàn tất bình thường:
    liveness  = CORRECT
    readiness = ACCEPTING_TRAFFIC
Khi bắt đầu shutdown có kiểm soát:
    readiness = REFUSING_TRAFFIC
~~~

Các mốc trên mô tả state nội bộ; **endpoint HTTP có thể chưa tồn tại** trong một số pha startup hoặc đã dừng ở pha shutdown. Đừng suy ra có thể luôn truy cập endpoint chỉ vì state đã được đặt trong bộ nhớ.

Khi có `spring-boot-starter-actuator`, Actuator có thể biểu diễn các trạng thái đó bằng:

- `LivenessStateHealthIndicator` trong health group `liveness`.
- `ReadinessStateHealthIndicator` trong health group `readiness`.

Đường dẫn thông thường:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Khi chạy trong Kubernetes, Spring Boot hỗ trợ tự bật probe health groups khi phát hiện môi trường. Khi chạy **cục bộ ngoài Kubernetes**, bạn có thể bật rõ ràng bằng:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

**Điểm quan trọng:** Theo mặc định, Spring Boot **không tự thêm** kiểm tra `db`, `redis`, `diskSpace` hoặc các health contributor khác vào nhóm liveness/readiness chỉ vì chúng hiện diện trong health endpoint chung.

Vì thế:

- `/actuator/health` có thể báo `DOWN` do một database health indicator thất bại.
- `/actuator/health/liveness` vẫn có thể là `UP` vì trạng thái nội bộ còn `CORRECT`.
- `/actuator/health/readiness` có thể vẫn là `UP` nếu ứng dụng còn `ACCEPTING_TRAFFIC` và chưa bổ sung kiểm tra dependency vào readiness.

Ba kết quả ấy **không mâu thuẫn**; chúng trả lời các câu hỏi khác nhau.

## 4. Khi một dependency hỏng, nên chuyển trạng thái nào?

Không có quy tắc “dependency DOWN = readiness DOWN” áp dụng cho mọi dịch vụ. Hãy phân biệt **phụ thuộc thiết yếu** và **phụ thuộc có thể suy giảm chức năng**.

| Tình huống | Liveness | Readiness nên cân nhắc | Xử lý ứng dụng |
|---|---|---|---|
| API gửi email lỗi, các API chính vẫn hoạt động | Giữ thành công | Thường giữ sẵn sàng | Queue/retry gửi email, báo metric/cảnh báo. |
| Redis cache lỗi, ứng dụng có thể fallback xuống database | Giữ thành công | Có thể giữ sẵn sàng nếu vẫn chịu tải tốt | Circuit breaker, giới hạn tải, fallback và monitor. |
| Database quan trọng không truy cập được nhưng chỉ một nhóm tính năng cần nó | Giữ thành công | Tùy traffic, routing và khả năng phục vụ một phần | Trả lỗi có kiểm soát cho nghiệp vụ liên quan, không nhất thiết loại cả Pod. |
| Một dependency **chỉ riêng Pod A** không dùng được do credentials hoặc cấu hình cục bộ | Giữ thành công nếu tiến trình còn khả năng phục hồi | Có thể cho Pod A NotReady | Cách ly instance lỗi, giữ những Pod khác phục vụ. |
| Tất cả instance không truy cập được một database dùng chung | Giữ thành công | **Cần cân nhắc kỹ**: loại hết Pod có thể làm cả Service mất endpoint | Retry, circuit breaker, fallback; quyết định theo hợp đồng API và hệ thống điều phối. |
| Deadlock nội bộ không thể tự phục hồi, ứng dụng ngừng tiến triển | Có thể thất bại nếu phát hiện đáng tin cậy | Thường cũng không sẵn sàng | Restart có thể giúp nếu lỗi thuộc instance. |

Với dependency dùng chung mà **mọi Pod** cùng kiểm tra trong readiness: nếu tất cả báo NotReady, Service có thể **không còn endpoint nào nhận kết nối**. Khi đó ứng dụng không còn cơ hội phục vụ các tác vụ độc lập hoặc trả lỗi nghiệp vụ có kiểm soát, và hành vi của gateway/ingress/load balancer có thể trở nên khó dự đoán.

Vì vậy hãy hỏi:

1. Dependency lỗi khiến **mọi request** không thể xử lý hay chỉ một chức năng?
2. Lỗi ảnh hưởng **một instance** hay **mọi instance**?
3. Có fallback, cache, retry, queue, circuit breaker hoặc degraded mode không?
4. Khi loại instance khỏi traffic, có những instance khác còn khả năng xử lý tốt hơn không?
5. Restart instance có tác động tích cực đến root cause hay chỉ làm tăng áp lực?

Một lựa chọn tốt có thể là **giữ liveness và readiness thành công**, đồng thời endpoint nghiệp vụ chịu ảnh hưởng trả lỗi phù hợp và hệ thống phát cảnh báo độc lập.

## 5. Ví dụ Spring Boot chạy được: upstream lỗi, liveness vẫn UP

Ví dụ sau minh họa **sự khác biệt giữa hai trạng thái**, không tự gọi database ngoài. Ta xây dựng một REST endpoint chỉ bật trong profile `demo` để **giả lập** một lỗi dependency thiết yếu: chuyển readiness sang `REFUSING_TRAFFIC`, nhưng **không** đổi liveness.

Cấu hình dùng **Spring Boot 3.3.5, Java 17, Spring Web và Actuator**.

### Cấu trúc dự án

~~~text
probe-demo/
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── com/example/probe/
        │       └── DependencyProbeApplication.java
        └── resources/
            └── application.properties
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

springBoot {
    mainClass = 'com.example.probe.DependencyProbeApplication'
}
~~~

Tạo `src/main/resources/application.properties`:

~~~properties
spring.application.name=dependency-probe-demo
server.port=8080

management.endpoints.web.exposure.include=health
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
management.endpoint.health.show-details=never
~~~

Ở đây:

- `probes.enabled=true` bảo đảm nhóm liveness/readiness được bật ngay cả khi chạy local, ngoài Kubernetes.
- `add-additional-paths=true` làm xuất hiện `/livez` và `/readyz` trên **cổng ứng dụng chính**, bên cạnh các đường dẫn Actuator.
- Chúng ta cố ý **không** thêm health check của dịch vụ ngoài vào nhóm liveness.
- `show-details=never` giúp không công khai chi tiết nội bộ của health indicators.

Tạo file Java đầy đủ `src/main/java/com/example/probe/DependencyProbeApplication.java`:

~~~java
package com.example.probe;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DependencyProbeApplication {

    public static void main(String[] args) {
        SpringApplication.run(DependencyProbeApplication.class, args);
    }

    // Chỉ dùng trong demo; không mở API đổi readiness tại production.
    @Profile("demo")
    @RestController
    public static class SimulationController {

        private final ApplicationEventPublisher events;

        public SimulationController(ApplicationEventPublisher events) {
            this.events = events;
        }

        @PostMapping("/demo/upstream/down")
        public String simulateUpstreamDown() {
            AvailabilityChangeEvent.publish(
                    events, ReadinessState.REFUSING_TRAFFIC);
            return "readiness=REFUSING_TRAFFIC";
        }

        @PostMapping("/demo/upstream/up")
        public String simulateUpstreamRecovered() {
            AvailabilityChangeEvent.publish(
                    events, ReadinessState.ACCEPTING_TRAFFIC);
            return "readiness=ACCEPTING_TRAFFIC";
        }
    }
}
~~~

Lý do chọn `ApplicationEventPublisher` và `AvailabilityChangeEvent.publish(...)`: Spring Boot lắng nghe sự kiện thay đổi availability và cập nhật trạng thái mà health indicators dùng để trả lời probe. Chúng ta **chỉ** phát `ReadinessState`; ứng dụng không bị gắn cờ `LivenessState.BROKEN`.

Chạy từ thư mục dự án có Gradle wrapper, sau khi tạo wrapper tương thích với plugin:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=demo'
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=demo"
~~~

Nếu chưa có Gradle wrapper, cần cài Gradle hoặc tạo wrapper trong dự án trước. Mã Java này có dependency Spring Boot nên **không thể** biên dịch bằng một lệnh `javac` độc lập thiếu classpath.

### Kiểm chứng bằng HTTP

Đợi ứng dụng khởi động xong, gọi:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

Trong điều kiện startup thành công và không có customization khác, cả hai thông thường có:

~~~text
HTTP 200
{"status":"UP"}
~~~

Tiếp theo giả lập upstream không sẵn sàng:

~~~bash
curl -i -X POST http://localhost:8080/demo/upstream/down
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/actuator/health/liveness
~~~

Kết quả cần quan sát:

| Request | HTTP status kỳ vọng | Nội dung chính |
|---|---|---|
| `POST /demo/upstream/down` | `200` | `readiness=REFUSING_TRAFFIC` |
| `GET /actuator/health/readiness` | **`503`** | `{"status":"OUT_OF_SERVICE"}` |
| `GET /actuator/health/liveness` | **`200`** | `{"status":"UP"}` |

Các con số trên là **kết quả kỳ vọng của chương trình theo cấu hình đã cho**; toàn bộ HTTP headers, timestamp và thứ tự chi tiết không được cố định ở đây. Spring Boot mặc định ánh xạ health status `OUT_OF_SERVICE` thành HTTP 503 và `UP` thành HTTP 200.

Cho upstream “hồi phục”:

~~~bash
curl -i -X POST http://localhost:8080/demo/upstream/up
curl -i http://localhost:8080/actuator/health/readiness
~~~

Readiness sẽ trở về `UP`, HTTP 200. **Không có restart JVM** trong quá trình giả lập này.

Để quan sát qua cổng ứng dụng chính thay cho Actuator path, bạn cũng có thể gọi:

~~~text
GET /livez
GET /readyz
~~~

Hai path này được tạo bởi `management.endpoint.health.probes.add-additional-paths=true`.

**Giới hạn quan trọng của demo:** API `/demo/upstream/down` chỉ **phát sự kiện giả lập**, không kiểm tra mạng hay một database thật. Đừng tạo endpoint public để bất kỳ client nào có thể đổi availability của production. Trong hệ thống thật, logic theo dõi trạng thái phải nằm trong thành phần nội bộ được bảo vệ, có debounce/hysteresis và chiến lược phục hồi phù hợp.

## 6. Khi nào bổ sung external check vào readiness group?

Spring Boot Actuator cho phép cấu hình health group. Nếu một dependency thật sự quyết định **instance nào có thể phục vụ traffic**, bạn có thể thêm health contributor vào **readiness**, ví dụ:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,db
~~~

Cấu hình này phù hợp **chỉ khi** ứng dụng thực sự có health contributor mang ID `db`, chẳng hạn khi Spring Boot kích hoạt `DataSourceHealthIndicator` cho datasource thích hợp. Nếu không có contributor `db`, việc tham chiếu tên không tồn tại có thể khiến cấu hình health group không hợp lệ. Không sao chép cấu hình này vào demo mục 5, vì demo không khai báo database.

Không thêm tương tự vào liveness:

~~~properties
# Không nên làm như một mặc định chung:
management.endpoint.health.group.liveness.include=livenessState,db
~~~

Dòng trên minh họa **một lựa chọn nên tránh** với dependency ngoài. Việc database lỗi sẽ ảnh hưởng liveness health group và có thể dẫn đến Kubernetes restart các container đang hoàn toàn có khả năng tự phục hồi.

### Chọn readiness theo bản chất dependency

Một health contributor có thể là:

- **Per-instance:** khóa cấu hình, credentials, kết nối cục bộ, dữ liệu cache nền quan trọng của một Pod. Đưa vào readiness có thể hợp lý vì Pod lỗi có thể được loại khỏi traffic trong khi Pod khác vẫn tốt.
- **Shared across all instances:** database hay API chung. Đưa vào readiness có thể làm **mọi** Pod NotReady cùng lúc, khiến Service không còn endpoint. Cần cân nhắc kỹ với phương án giữ Pod hoạt động và xử lý lỗi ở tầng ứng dụng/caller.
- **Optional:** hệ thống analytics, email, cache có fallback. Đưa vào readiness thường làm gián đoạn quá rộng so với ảnh hưởng nghiệp vụ thực tế.

Nếu tự viết `HealthIndicator` để đại diện dependency, hãy tránh tạo cuộc gọi remote chậm hoặc đắt đỏ ở **mỗi lần probe**. Readiness sẽ được kubelet gọi lặp thường xuyên; kiểm tra tốt nên có timeout ngắn, đánh giá trạng thái cục bộ/cached state hợp lý và không làm tắc request handling khi dependency đang quá tải.

Các health contributor **ngoài** liveness/readiness vẫn có thể được dùng ở endpoint health tổng quát hoặc nhóm health chuyên biệt cho monitoring. Hãy tách việc **cảnh báo sự cố dependency** khỏi quyết định **restart một container**.

## 7. Ví dụ cấu hình Kubernetes probe hợp lý

Đoạn YAML sau là **phần cấu hình bên trong một container của Pod/Deployment**, không phải một manifest Deployment hoàn chỉnh:

~~~yaml
startupProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 30

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
~~~

Giải thích:

- `startupProbe` cùng liveness endpoint cho phép tiến trình có khoảng thời gian startup riêng trước khi Kubernetes bắt đầu dùng liveness/readiness. Ví dụ `failureThreshold=30` và `periodSeconds=10` cung cấp một khoảng dung sai tính theo chu kỳ probe; thời điểm restart còn phụ thuộc timeout và cách kubelet lập lịch.
- `livenessProbe` chỉ phản ánh trạng thái nội bộ; lỗi external không nên là lý do mặc định để fail.
- `readinessProbe` cho biết Pod có nhận traffic mới hay không. Khi fail, Kubernetes tiếp tục chạy Pod, tiếp tục kiểm tra và có thể tự đưa Pod trở lại Service khi probe thành công.
- Cả hai dùng `/livez` và `/readyz` trên cổng **main HTTP server** thay vì port management tách biệt.

Các ngưỡng chỉ là **ví dụ ban đầu**, không phải giá trị tối ưu cho mọi dịch vụ. Cần đo thời gian startup thực tế, độ trễ xử lý request, timeout của ứng dụng và khả năng chịu tải để điều chỉnh. Probe quá nhạy có thể đánh dấu thất bại do GC pause, CPU contention hoặc spike tải ngắn.

### Vì sao nên thận trọng với management port riêng?

Nếu cấu hình `management.server.port` khác với cổng ứng dụng, Actuator có thể dùng hạ tầng web riêng. Khi đó probe ở management port có thể vẫn trả thành công **dù main server không nhận kết nối**. Spring Boot cung cấp tùy chọn `management.endpoint.health.probes.add-additional-paths=true` để xuất thêm `/livez` và `/readyz` trên cổng ứng dụng chính.

Chạy probe qua main port không có nghĩa liveness phải gọi database. Nó chỉ giúp xác nhận đường HTTP của ứng dụng có khả năng phản hồi probe, mà không lẫn việc phụ thuộc hệ thống ngoài.

## 8. Phân biệt sự cố không tự phục hồi với lỗi tạm thời

Một câu hỏi kỹ thuật quan trọng là: **restart instance có cơ hội cải thiện tình hình hay không?**

| Lỗi | Restart có thường sửa được root cause? | Phản ứng phù hợp để cân nhắc |
|---|---|---|
| Database chung bị mất mạng | Không | Retry có backoff, circuit breaker, lỗi nghiệp vụ kiểm soát, alert. |
| API payment ở ngoài trả 503 tạm thời | Không | Timeout, retry có giới hạn, queue/degraded mode, alert. |
| Redis cache lỗi nhưng ứng dụng có fallback | Không cần | Fallback, rate limit và bảo vệ database phía sau. |
| Credentials cấu hình sai cố định | Restart không sửa cấu hình sai | Báo lỗi/NotReady tùy trường hợp; sửa secret/config và rollout có kiểm soát. |
| Deadlock thực sự của JVM/application và không có cơ chế phục hồi | Có thể | Liveness fail/restart nếu phát hiện đáng tin cậy; đồng thời tìm và sửa bug. |
| Memory leak nghiêm trọng, instance không thể tiếp tục hoạt động | Restart có thể tạm giảm triệu chứng | Restart theo chính sách; bắt buộc điều tra leak và capacity. |
| Instance bị quá tải ngắn hạn | Restart có thể làm tệ hơn | Backpressure, autoscale, giới hạn concurrency, readiness khi cần. |

Đừng kết luận “DB lỗi thì Pod chết” chỉ vì đường nghiệp vụ trả HTTP 500 hoặc 503. Những status từ **endpoint nghiệp vụ** khác với status của **liveness endpoint**. Thậm chí endpoint health tổng hợp báo `DOWN` cũng không đồng nghĩa liveness group phải báo `DOWN`.

## 9. Circuit breaker, retry và degraded mode

Mục tiêu của resilience là cho ứng dụng **tiếp tục tồn tại và hồi phục** khi một dependency hỏng, thay vì bị restart liên tục.

Các kỹ thuật thường phối hợp:

1. **Timeout rõ ràng:** request tới upstream phải kết thúc trong thời gian giới hạn, không giữ thread vô hạn.
2. **Retry có kiểm soát:** chỉ retry thao tác an toàn/idempotent hoặc có cơ chế chống lặp; dùng backoff và jitter để tránh các Pod cùng retry đồng thời.
3. **Circuit breaker:** khi upstream lỗi liên tục, tạm ngừng gửi thêm request để bảo vệ hệ thống và nhanh chóng trả fallback/error.
4. **Bulkhead và giới hạn concurrency:** lỗi của một upstream không được dùng cạn thread pool của toàn ứng dụng.
5. **Fallback/degraded mode:** phục vụ dữ liệu cache, queue công việc hoặc vô hiệu hóa chức năng phụ; không nhất thiết làm toàn bộ Pod NotReady.
6. **Metrics, tracing và alert:** phản ánh tỷ lệ lỗi upstream cho người vận hành mà không kích hoạt restart sai.

Ví dụ, một endpoint gửi email có thể đưa message vào queue khi email provider đang lỗi. Lúc này hệ thống vẫn chấp nhận request thành công nếu hợp đồng nghiệp vụ cho phép xử lý bất đồng bộ. Gắn email provider vào liveness sẽ biến lỗi tạm thời thành mất service một cách không cần thiết.

Ngược lại, nếu ứng dụng chỉ có một trách nhiệm là thực hiện giao dịch trực tiếp lên database và không thể phục vụ request nào khi database mất kết nối, readiness có thể cần phản ánh trạng thái đó. **Ngay cả lúc ấy, liveness vẫn không nên fail chỉ vì database lỗi**.

## 10. Readiness fail cũng không phải lúc nào là câu trả lời đúng

Readiness thường ít phá hoại hơn liveness vì **không tự restart**, nhưng không nên đánh dấu NotReady vô điều kiện cho mọi lỗi external.

Một ví dụ: 10 Pod đọc cùng một database. Khi database lỗi toàn cục và tất cả readiness health group phụ thuộc trực tiếp vào `db`, cả 10 Pod có thể NotReady. Kubernetes Service không còn endpoint sẵn sàng, ngay cả khi ứng dụng vẫn có thể trả cache, thông báo lỗi rõ ràng hoặc xử lý request không chạm database.

Có hai hướng thiết kế, tùy nhu cầu:

- **Include dependency trong readiness:** phù hợp khi loại instance bị lỗi giúp traffic chuyển sang **instance khác thực sự khỏe hơn**, hoặc khi đảm bảo mọi request tới instance đó phải có dependency.
- **Không include shared dependency trong readiness:** phù hợp khi mọi instance chịu cùng lỗi, khi có fallback/degraded mode, hoặc khi giữ service reachable để trả lỗi có kiểm soát tốt hơn.

Nếu cần phân biệt nhiều mức khả dụng, hãy dùng **các health groups riêng cho monitoring** và metrics theo loại nghiệp vụ, thay vì gom mọi lỗi vào một boolean của liveness/readiness.

Hãy kiểm tra hành vi gateway, load balancer và Service thực tế: khi mọi endpoint NotReady, client có thể gặp lỗi kết nối thay vì nhận một JSON 503 từ ứng dụng. Kết quả cụ thể phụ thuộc topology và controller điều phối.

## 11. Startup probe không dùng để kiểm tra external service mãi mãi

Startup probe có vai trò **cho phép ứng dụng khởi động chậm** mà không bị liveness probe giết quá sớm. Ví dụ ứng dụng cần load model, tạo cache nội bộ hoặc warm up trong một khoảng đo được.

Nếu startup probe phụ thuộc vào một database ở ngoài đang lỗi, nó có thể vẫn dẫn đến restart lặp. Khi thiết kế:

- Startup probe nên phản ánh **mốc khởi tạo của chính tiến trình**, tránh khóa startup vào một external service không bắt buộc.
- Readiness vẫn có thể ở `REFUSING_TRAFFIC` đến khi ứng dụng thật sự nhận request được.
- Khi startup probe thành công, Kubernetes mới bắt đầu liveness và readiness probe thông thường.

Đừng dùng startup probe để biến các lỗi external lâu dài thành lý do restart, trừ khi có hợp đồng kỹ thuật rõ rằng restart instance sẽ giúp hồi phục.

## 12. Liveness endpoint nên kiểm tra điều gì?

Một số tiêu chí phù hợp:

- Tiến trình và HTTP handling tối thiểu còn phản hồi trong ngưỡng thời gian hợp lý.
- `ApplicationAvailability.getLivenessState()` đang ở `CORRECT`.
- Một lỗi **nội bộ không thể tự phục hồi**, được phát hiện và chứng minh đáng tin, có thể làm `LivenessState.BROKEN`.

Những điều **không nên mặc nhiên** thuộc liveness:

- Mở kết nối database mới.
- Gọi HTTP health endpoint của upstream.
- Đọc message broker/Redis để xác định mọi phụ thuộc đều online.
- Kiểm tra một chức năng nghiệp vụ cụ thể phụ thuộc nhiều dịch vụ.
- Đòi cache đã warm hoàn toàn hoặc job nền hoàn tất.

Nếu custom liveness handler tự chạy một cuộc gọi mạng blocking và upstream bị treo, handler có thể timeout; Kubernetes sẽ tưởng JVM bị hỏng và restart. Vì vậy **logic liveness càng ít phụ thuộc external và càng nhẹ càng tốt**.

Trong trường hợp thực sự cần đánh dấu một lỗi không phục hồi được của chính ứng dụng, có thể chủ động phát `AvailabilityChangeEvent` cho `LivenessState.BROKEN` theo cơ chế Spring Boot. Nhưng đây là **quyết định nghiêm trọng**: cần xác định rõ tín hiệu đó có đáng để Kubernetes restart hay không. Không dùng state `BROKEN` làm nhãn chung cho mọi exception.

## 13. Observability cần tách khỏi quyết định restart

Probe chỉ có một nhiệm vụ điều phối tương đối hẹp, trong khi quan sát sức khỏe hệ thống cần nhiều tín hiệu:

| Tín hiệu | Ví dụ | Mục tiêu |
|---|---|---|
| Metrics upstream | Timeout rate, connection errors, circuit breaker state, latency | Phát hiện sự cố dependency. |
| Health group chuyên biệt | Database, cache, broker, external API | Điều tra/monitor dependency. |
| Liveness | Trạng thái nội bộ của process | Quyết định restart khi cần. |
| Readiness | Khả năng nhận request mới của instance | Điều phối traffic. |
| Logs và traces | Root cause, request correlation | Debug và phân tích lỗi. |
| Kubernetes events | Probe failures, restart count, NotReady | Đánh giá hành vi của platform. |

Một hệ thống có thể báo:

~~~text
Liveness: UP
Readiness: UP
Payment API error rate: 100%
Circuit breaker: OPEN
~~~

Đây có thể là **mô hình đúng** nếu các chức năng khác vẫn phục vụ bình thường và payment không phải dependency bắt buộc của toàn bộ request. Hệ thống monitoring vẫn phải cảnh báo lỗi payment; không cần cố biến liveness thành DOWN để tạo cảnh báo.

Cũng có thể có:

~~~text
Liveness: UP
Readiness: OUT_OF_SERVICE
External dependency: DOWN
~~~

Đây có thể là **mô hình đúng** khi instance không nên nhận request mới nhưng vẫn còn khả năng tự hồi phục. Kubernetes nên tạm rút traffic, không restart nó.

## 14. Các lỗi thiết kế thường gặp

**Lỗi 1 — Đặt livenessProbe trỏ vào `/actuator/health` tổng quát.**

Health tổng quát có thể bao gồm datasource, Redis, disk space và những contributor khác. Nếu một dependency fail kéo health tổng quát xuống, kubelet có thể restart container không hỏng. Hãy dùng **`/actuator/health/liveness`** hoặc `/livez` đúng mục đích.

**Lỗi 2 — Thêm `db` vào nhóm liveness.**

Một database lỗi sẽ bị diễn giải thành “ứng dụng nên restart”. Đây không phải cơ chế khôi phục database. Nếu dependency ảnh hưởng khả năng phục vụ, cân nhắc readiness dựa trên nhu cầu thật, chứ không tự động gắn vào liveness.

**Lỗi 3 — Thấy readiness DOWN rồi tự gọi `System.exit(...)`.**

Thao tác này vô hiệu hóa ý nghĩa phân biệt readiness/liveness. NotReady cho phép Pod đang chạy hồi phục và được đưa trở lại traffic. `System.exit(...)` khiến process dừng, có thể gây restart không cần thiết.

**Lỗi 4 — Mọi lỗi upstream đều làm cả Pod NotReady.**

Có thể khiến mọi endpoint biến mất khi lỗi dùng chung hoặc loại cả những chức năng vẫn hoạt động. Cần xét phạm vi lỗi, fallback và routing.

**Lỗi 5 — Health check gọi upstream liên tục, không timeout.**

Probe có thể tự làm tăng tải và tạo vòng lặp timeout, ngay khi hệ thống đã suy yếu. Cân nhắc trạng thái cục bộ, kết quả kiểm tra có cache, timeout ngắn và circuit breaker.

**Lỗi 6 — Liveness và readiness dùng cùng một endpoint trả trạng thái DB.**

Hai probe khác hậu quả nhưng cùng một điều kiện kiểm tra. Kết quả có thể là restart hàng loạt thay vì chỉ tạm ngừng nhận traffic. Hãy tách nghĩa và đường dẫn.

**Lỗi 7 — Quên startup probe với ứng dụng khởi động lâu.**

Nếu liveness bắt đầu quá sớm, tiến trình có thể bị restart trước khi HTTP endpoint tồn tại. Dùng startup probe khi thời gian khởi động thực sự dài hoặc biến thiên lớn.

**Lỗi 8 — Probe ở management port riêng là đủ để kiểm tra main server.**

Không hẳn: management HTTP stack có thể sống trong khi main port không nhận kết nối. Spring Boot hỗ trợ thêm `/livez` và `/readyz` trên main port.

**Lỗi 9 — Dùng probe như hệ thống alert duy nhất.**

Probe nên phục vụ điều phối lifecycle/traffic; phụ thuộc hỏng cần metrics, logs, traces và alert riêng. Không ép liveness DOWN chỉ để người vận hành nhận thông báo.

**Lỗi 10 — Expose endpoint đổi readiness cho người dùng ngoài.**

Trong demo, profile `demo` cho phép chủ động đổi state để học. Production không được mở công khai API kiểu này vì có thể bị lợi dụng để rút Pod khỏi traffic.

## 15. Checklist kiểm tra trước khi triển khai

1. **Xác định mục tiêu:** liveness có thật sự đo lỗi nội bộ khó phục hồi; readiness có đo khả năng nhận traffic?
2. **Tách các endpoint:** cấu hình kubelet dùng `/livez` và `/readyz` hoặc các Actuator health group tương ứng, không dùng health tổng quát thay thế mà không đánh giá contributor.
3. **Xem danh sách health contributors:** dependency nào đã được thêm thủ công vào liveness/readiness? Tại sao?
4. **Phân loại dependency:** thiết yếu, optional, per-instance hay dùng chung mọi Pod?
5. **Thử lỗi có kiểm soát:** khi ngắt database trong staging, đo restart count, Ready state, response nghiệp vụ, retry và pool connections.
6. **Quan sát recovery:** khi database hồi phục, Pod có tự trở lại phục vụ mà không restart không?
7. **Kiểm soát probe cost:** đo latency probe, timeout, tần suất, thread use và áp lực lên dependency.
8. **Đánh giá trạng thái tất cả Pod NotReady:** client và gateway sẽ gặp chuyện gì khi Service hết endpoint?
9. **Bảo đảm graceful shutdown:** khi thực sự cần restart hoặc rollout, ứng dụng phải có thời gian rút traffic và xử lý request đang chạy.
10. **Đặt alert độc lập:** sự cố DB/API phải quan sát được qua metrics/logs, không cần phải ép liveness fail.

### Tài liệu chính thức

- Spring Boot — Actuator endpoints, *Kubernetes Probes* và *Checking External State With Kubernetes Probes*: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot — Application Availability và liveness/readiness state: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Kubernetes — *Liveness, Readiness, and Startup Probes*: https://kubernetes.io/docs/concepts/workloads/pods/probes/
- Kubernetes — *Configure Liveness, Readiness and Startup Probes*: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/

**Tổng kết:** Lỗi của database, cache, broker hoặc API bên ngoài **không đồng nghĩa JVM/Spring Boot instance đã hỏng**. Gắn lỗi bên ngoài vào liveness sẽ làm Kubernetes restart các ứng dụng vốn còn khả năng tự phục hồi, có thể tạo lỗi dây chuyền. Hãy giữ **liveness cho lỗi nội bộ không thể tự phục hồi**, dùng **readiness có chọn lọc** để điều phối traffic, và dùng **resilience + observability** để xử lý lỗi dependency theo đúng phạm vi ảnh hưởng.
