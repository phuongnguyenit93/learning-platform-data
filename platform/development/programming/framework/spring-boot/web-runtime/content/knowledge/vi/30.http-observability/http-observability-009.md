# Kết nối Actuator, health và readiness với trạng thái web runtime trong Spring Boot

Một Spring Boot web application có thể **đã khởi động JVM nhưng chưa sẵn sàng nhận request**, hoặc **vẫn sống nhưng không đủ điều kiện phục vụ traffic**. Trong hệ thống có load balancer/Kubernetes, quyết định **restart tiến trình**, **tạm ngừng gửi request đến một instance**, hay **tiếp tục cho instance phục vụ** không nên dựa vào một endpoint luôn trả chuỗi "OK". Spring Boot Actuator cung cấp **HealthEndpoint**, **health groups** và **ApplicationAvailability** để phản ánh các trạng thái này qua các HTTP probes.

Bài thuộc **Spring Boot - web-runtime → Quan sát HTTP**, đi sâu vào **kết nối Actuator, health và readiness với vòng đời web server, Servlet request, health checks và quy trình vận hành**. Ví dụ dùng **Java 17+, Spring Boot 3.3.13, Spring MVC, embedded Tomcat và Maven**. Có cấu hình liveness/readiness probes trên **cổng HTTP chính**, một custom HealthIndicator có thể đổi trạng thái, demo phát AvailabilityChangeEvent và integration test dùng HTTP thật. Phần Kubernetes, reverse proxy, Spring Security, graceful shutdown và failure scenarios được giải thích để tránh thiết kế probe gây downtime.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

1. Phân biệt **process alive**, **HTTP listener reachable**, **application health**, **liveness**, **readiness** và **startup**.
2. Hiểu **ApplicationAvailability**, **LivenessState.CORRECT/BROKEN**, **ReadinessState.ACCEPTING_TRAFFIC/REFUSING_TRAFFIC**, cũng như các mốc ApplicationStartedEvent và ApplicationReadyEvent.
3. Bật **spring-boot-starter-actuator** và xem **/actuator/health**, **/actuator/health/liveness**, **/actuator/health/readiness**.
4. Dùng **management.endpoint.health.probes.enabled** ở môi trường không phải Kubernetes và **management.endpoint.health.probes.add-additional-paths** để tạo **/livez** và **/readyz** ngay trên main server port.
5. Phân biệt **management.server.port** với **server.port**, hiểu vì sao health check ở management connector riêng có thể báo UP dù web connector chính không nhận được kết nối.
6. Tạo **HealthIndicator** và đưa vào readiness group bằng **management.endpoint.health.group.readiness.include**, trong khi giữ liveness độc lập với dependencies ngoài.
7. Phát **AvailabilityChangeEvent** đúng lúc để tạm ngừng nhận traffic hoặc khôi phục nhận traffic trong trường hợp nghiệp vụ phù hợp.
8. Viết **@SpringBootTest(RANDOM_PORT)** test HTTP status 200/503 khi liveness và readiness khác trạng thái, không phụ thuộc riêng MockMvc.
9. Cấu hình **Kubernetes livenessProbe, readinessProbe, startupProbe** hợp lý, hiểu tác động của các ngưỡng period/timeout/failure và thời gian drain.
10. Chẩn đoán các tình huống false positive, false negative, cascading restarts, 503, health endpoint bị 401/404, startup chậm, proxy sai cổng và readiness phụ thuộc upstream không ổn định.

Kiến thức cần trước: Maven/Java 17, Spring Boot embedded web runtime, HTTP status code, dependency injection, Servlet container, và khái niệm deployment nhiều replicas.

## 2. "App đang chạy" không đồng nghĩa "sẵn sàng nhận traffic"

Hãy tưởng tượng ứng dụng khởi động qua các bước:

~~~text
JVM process launched
    |
    v
Spring ApplicationContext đang tạo beans
    |
    v
Embedded Tomcat HTTP connector khởi tạo
    |
    v
ApplicationStartedEvent, context đã refresh
    |
    v
ApplicationRunner / CommandLineRunner
    warmup cache, chuẩn bị tài nguyên
    |
    v
ApplicationReadyEvent
    |
    v
ApplicationAvailability:
    ReadinessState.ACCEPTING_TRAFFIC
    |
    v
Kubernetes/load balancer có thể route traffic
~~~

**Ba khái niệm quan trọng:**

- **Liveness:** tiến trình còn ở trạng thái có thể hoạt động đúng hoặc tự phục hồi không? Nếu bị hỏng không thể khôi phục, hạ tầng có thể **restart instance**.
- **Readiness:** instance **ngay lúc này** có nên được gửi traffic mới không? Nếu chưa sẵn sàng, hạ tầng nên **tạm loại nó khỏi endpoints cân bằng tải**, nhưng không nhất thiết restart.
- **Startup:** đã cho phép hệ thống kiểm tra liveness/readiness định kỳ chưa? Kubernetes có startupProbe riêng để trì hoãn đánh giá hai probes còn lại khi startup cần nhiều thời gian.

Một process có PID tồn tại **không** chứng minh HTTP route được; một HTTP port mở **không** chứng minh ứng dụng đã load xong; và **/actuator/health trả 200** không chứng minh tất cả use cases nghiệp vụ đều thành công.

### 2.1. Bảng quyết định vận hành

| Tín hiệu | Câu hỏi | Phản ứng hạ tầng thích hợp |
| --- | --- | --- |
| Process/container exit | Tiến trình còn không? | Container restart theo restart policy. |
| Startup probe fail | Startup đã hoàn tất mức tối thiểu chưa? | Chưa chạy liveness/readiness; khi vượt ngưỡng thì restart theo policy. |
| Liveness fail | Tiến trình bị mắc kẹt/không thể tự phục hồi? | Restart instance khi vượt failureThreshold. |
| Readiness fail | Instance hiện có nhận thêm request được không? | Loại instance khỏi Service endpoints; **không restart chỉ vì readiness fail**. |
| Business endpoint fail | Một chức năng cụ thể có lỗi không? | Theo dõi SLO, alert, retry/circuit breaker/fallback phù hợp; không tự quy thành liveness fail. |
| Actuator health detail | Có health contributors nào DOWN/UP? | Phân tích thành phần; quyết định đưa indicator vào group nào. |

**Thiết kế chính:** liveness phải đơn giản và đáng tin; readiness phản ánh khả năng phục vụ traffic của **chính instance**. Không lấy **global /actuator/health** làm liveness theo quán tính, bởi global health có thể tổng hợp database, disk space hoặc service phụ thuộc và vô tình gây restart hàng loạt.

## 3. Spring Boot ApplicationAvailability

Spring Boot cung cấp **org.springframework.boot.availability.ApplicationAvailability** với hai khía cạnh:

- **LivenessState**: thường **CORRECT** hoặc **BROKEN**.
- **ReadinessState**: thường **ACCEPTING_TRAFFIC** hoặc **REFUSING_TRAFFIC**.

Đây là **in-memory states của application instance**, không phải phản hồi HTTP. Actuator sử dụng các health indicators tương ứng để biến states thành HTTP health groups. Việc thay đổi một availability state không tự biến tất cả HTTP controller thành 503: **orchestrator/load balancer** cần đọc probe rồi quyết định routing, và một request gọi trực tiếp Pod IP vẫn có thể đi tới application khi connector đang hoạt động.

### 3.1. Lifecycle khi khởi động

| Giai đoạn Spring Boot 3.3 | Liveness | Readiness | Ý nghĩa |
| --- | --- | --- | --- |
| Đang khởi động | **BROKEN** | **REFUSING_TRAFFIC** | Application chưa được xem là live/ready; HTTP endpoint có thể chưa tồn tại. |
| Context đã refresh, ApplicationStartedEvent | **CORRECT** | **REFUSING_TRAFFIC** | Ứng dụng live nhưng startup runners chưa hoàn tất. |
| ApplicationReadyEvent và availability event kế tiếp | **CORRECT** | **ACCEPTING_TRAFFIC** | Startup tasks đã xong, được xem là ready. |

Các giá trị phản ánh mô hình vòng đời **Spring Boot 3.3**, không phải lời hứa rằng có thể luôn kết nối HTTP vào mọi thời điểm của giai đoạn startup. Khi connector chưa bind cổng, probe trả **connection refused/timeout**, không có JSON 503 từ Actuator để đọc.

**ApplicationRunner/CommandLineRunner** thích hợp cho các công việc cần hoàn thành trước readiness, ví dụ tải cấu hình bắt buộc hoặc chuẩn bị một dữ liệu cục bộ thiết yếu. Không đặt tác vụ warmup nghiêm trọng trong **@PostConstruct** rồi xem nó là tín hiệu hoàn thành readiness: lifecycle của bean và application ready event khác nhau.

### 3.2. Lifecycle khi shutdown

Khi ứng dụng nhận yêu cầu dừng, Spring Boot có thể chuyển **ReadinessState.REFUSING_TRAFFIC**, sau đó tiến hành graceful shutdown nếu được cấu hình. HTTP connector có thể ngừng nhận request mới trong quá trình drain và probes có thể **không còn trả JSON**, dù in-memory state vẫn tồn tại trong một khoảng thời gian.

~~~text
Running: liveness CORRECT, readiness ACCEPTING_TRAFFIC
    |
    v
SIGTERM / graceful shutdown
    |
    v
readiness REFUSING_TRAFFIC
    |
    v
Ngừng nhận request mới, xử lý in-flight requests
    |
    v
Đóng context và connector
~~~

Kubernetes Pod termination còn có EndpointSlice updates và terminationGracePeriodSeconds, không chỉ dựa vào HTTP probe. Vì vậy phải phối hợp readiness, preStop khi cần, graceful shutdown timeout và load balancer propagation delay.

### 3.3. Đọc trạng thái từ Java

~~~java
package com.example.probe;

import java.util.Map;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AvailabilityController {
    private final ApplicationAvailability availability;

    public AvailabilityController(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @GetMapping("/demo/availability")
    public Map<String, String> currentState() {
        return Map.of(
            "liveness", availability.getLivenessState().name(),
            "readiness", availability.getReadinessState().name());
    }
}
~~~

Class này sẽ xuất hiện trong demo. Sau startup thành công, endpoint thường trả **CORRECT/ACCEPTING_TRAFFIC**. **Đây là trạng thái availability đơn thuần**: nó **không kiểm tra custom HealthIndicator** nào bạn đã đưa vào readiness group. Có thể thấy ApplicationAvailability vẫn ACCEPTING_TRAFFIC trong khi readiness HTTP trả 503 do một health contributor DOWN; đó không phải mâu thuẫn.

## 4. Actuator HealthEndpoint, status và HTTP response

### 4.1. Bật Actuator

Thêm Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Mặc định, Spring Boot 3.3 **chỉ expose health endpoint qua HTTP**; muốn truy cập metrics/info cần cấu hình exposure phù hợp. URL mặc định là:

~~~text
GET http://localhost:8080/actuator/health
~~~

Response tối giản khi UP:

~~~json
{"status":"UP"}
~~~

**Health details mặc định không phơi bày toàn bộ**. Không bật show-details=always trên public endpoint chỉ để debug một bài học; có thể tiết lộ hostname, filesystem, DB hoặc thông tin nội bộ.

### 4.2. HealthContributor và HealthIndicator

Actuator tổng hợp trạng thái từ những **HealthContributor**; các **HealthIndicator** ví dụ gồm diskSpace, db khi có DataSource, redis khi có connector tương ứng, custom indicator do ứng dụng cung cấp. Một indicator có thể trả:

- **UP:** thành phần hoạt động bình thường.
- **DOWN:** thành phần thất bại.
- **OUT_OF_SERVICE:** thành phần hiện không nên phục vụ.
- **UNKNOWN:** không có kết luận đủ rõ.

Tổng hợp health dùng **StatusAggregator**; status HTTP dùng **HttpCodeStatusMapper**. Mặc định:

| Health status | HTTP response mặc định |
| --- | --- |
| UP | 200 OK |
| DOWN | **503 Service Unavailable** |
| OUT_OF_SERVICE | **503 Service Unavailable** |
| UNKNOWN | Thường **200** do không có custom mapping |

Tùy chính sách custom status mappings, có thể thay behavior; nếu tự cấu hình mapping, lưu ý các default mappings DOWN/OUT_OF_SERVICE có thể cần khai báo lại. **Đừng viết Kubernetes probe dựa vào raw JSON text "UP" khi HTTP status là signal chính**.

### 4.3. Global health không phải liveness

~~~text
/actuator/health                Tổng hợp các contributors có trong global health
/actuator/health/liveness       Nhóm liveness (thường livenessState)
/actuator/health/readiness      Nhóm readiness (thường readinessState)
/livez                         Liveness path trên main server port nếu bật
/readyz                        Readiness path trên main server port nếu bật
~~~

Nếu database health contributor DOWN, global /actuator/health có thể trả **503**; liveness vẫn **200** vì tiến trình còn đúng. Chính sự tách biệt này giúp tránh restart một fleet ứng dụng khi database tập trung bị sự cố.

## 5. Bật liveness/readiness probes theo đúng phiên bản Boot 3.3

### 5.1. Auto enable trong Kubernetes

Spring Boot 3.3 có khả năng phát hiện môi trường Kubernetes và tự enable nhóm **liveness** và **readiness** khi ứng dụng chạy trong Kubernetes. Nếu chạy ở máy local không có môi trường này, cần **bật chủ động**:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Việc bật probes không tự thay đổi policy của Kubernetes: bạn vẫn phải khai báo **livenessProbe/readinessProbe** trong workload manifest nếu muốn kubelet gọi endpoint.

### 5.2. Health group URLs

Khi probes enabled:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

Khi ứng dụng vừa sẵn sàng và không có indicator nào lỗi, hai response thường là HTTP **200** và body:

~~~json
{"status":"UP"}
~~~

Đây là hai **nhóm health khác nhau**. Đừng dùng tên readiness cho liveness vì cả hai đều trả UP trong điều kiện bình thường.

### 5.3. Tạo /livez và /readyz ngay trên cổng web chính

Một cấu hình quan trọng:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Trong Spring Boot 3.3, setting **management.endpoint.health.probes.add-additional-paths=true** cung cấp:

~~~text
/livez    -> nhóm liveness trên main server port
/readyz   -> nhóm readiness trên main server port
~~~

Nếu có **server.servlet.context-path**, hãy kiểm tra URL thực tế của main server. Nếu đặt management port khác, nhóm **/actuator/health/...** có thể ở management port, còn **/livez và /readyz** ở **main server port**. Các đường dẫn tùy chỉnh khác cần dùng group additional-path có prefix **server:** hoặc **management:** theo API Spring Boot.

### 5.4. Tại sao main port probe quan trọng?

Xét topology:

~~~text
                 +--> Port 8080 (main web server)
kubelet / LB ----|
                 +--> Port 8081 (management web server)
~~~

Khi **management.server.port=8081**, actuator có thể phục vụ bằng **một web infrastructure/connector riêng**. Kết quả:

- Cổng management 8081 vẫn trả /actuator/health/readiness **200**.
- Nhưng cổng ứng dụng 8080 có thể không nhận được kết nối mới vì thread pool/resource/connector hoặc network route bị lỗi.
- Kubernetes probe chỉ gọi 8081 sẽ **false positive**, tiếp tục route traffic vào app không phục vụ được.

Cho kubelet gọi **/livez và /readyz trên port 8080** giúp probe kiểm tra ít nhất **đường HTTP của connector chính**, đồng thời đánh giá availability/group health. Dù vậy, endpoint nhẹ thành công **không chứng minh mọi API, database, authentication hay message queue đều khỏe**; cần SLO monitoring và các nghiệp vụ có kiểm tra riêng.

## 6. Readiness có nên kiểm tra database/Redis/API bên ngoài?

### 6.1. Không đưa dependencies ngoài vào liveness

**Liveness** nên phản ánh lỗi nội bộ không thể tự phục hồi. Nếu bạn thêm db, redis, partner API vào liveness, một lần DB outage có thể gây **restart tất cả pods**. Restarts tạo thêm kết nối, cache misses và startup load, biến lỗi dependency thành **cascading failure**.

**Quy tắc bảo thủ:** để liveness dùng **livenessState** mặc định; chỉ bổ sung indicator nếu bạn có tín hiệu nội bộ đáng tin cho trạng thái thật sự không thể recover mà restart giúp được.

### 6.2. Readiness cũng không nên check mọi dependency

Readiness phản ánh **instance này có nên nhận traffic không**. Có thể hợp lý nếu:
- Instance cần một **local data snapshot** để trả kết quả đúng.
- Client pool/local resource của riêng replica đang cạn và cần cooldown.
- Cache local bắt buộc chưa warm xong.
- Instance cần hoàn tất một nhiệm vụ bootstrap trước khi sẵn sàng.

Cẩn thận nếu:
- Database là hệ thống dùng chung của **mọi replicas**: khi DB outage, tất cả instance cùng unready, làm Service không còn endpoints.
- Một optional recommendation service thất bại nhưng API còn fallback; loại toàn app khỏi traffic là không cần thiết.
- Probe mỗi vài giây tạo network calls đắt hoặc có timeout kéo dài, gây thêm load cho hệ thống lỗi.

**Khuyến nghị:** readiness group có **readinessState** và chỉ những indicator có liên hệ trực tiếp đến khả năng nhận traffic của **instance**, với timeout chặt và chi phí thấp. Availability state, fallback/circuit breaker và SLO alerts thường phù hợp hơn việc gọi HTTP đến mọi downstream từ probe.

### 6.3. Tùy chỉnh group

Spring Boot cho phép include danh sách health contributor IDs:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: "readinessState,localCapacity"
~~~

Trong cấu hình này:
- **readinessState** là indicator do Boot tạo từ ApplicationAvailability.
- **localCapacity** là custom HealthIndicator ở ví dụ tiếp theo.
- Nhóm liveness không thêm localCapacity, nên custom indicator DOWN không tự tạo liveness fail.

**Quan trọng:** Spring Boot có validation health group membership. Nếu bạn include một ID không tồn tại, startup có thể fail. Hãy kiểm tra tên bean indicator, nhất là quy tắc bỏ hậu tố **HealthIndicator**. Không tắt **management.endpoint.health.validate-group-membership** để che lỗi cấu hình thay vì sửa ID.

## 7. Dự án Spring Boot Java 17 hoàn chỉnh

Demo thực hiện những điều sau:
1. Web app có GET **/demo/ping** và GET **/demo/availability**.
2. Actuator health groups và **/livez**, **/readyz** nằm trên main HTTP port.
3. HealthIndicator **localCapacity** phụ thuộc một AtomicBoolean, mặc định UP.
4. Một controller điều khiển trạng thái **chỉ tồn tại dưới profile demo**, cho phép thử chuyển **ReadinessState.REFUSING_TRAFFIC** và custom indicator DOWN.
5. JUnit integration test dùng **HTTP request thật** và kiểm tra chính xác status **200/503**, liveness không bị ảnh hưởng bởi thay đổi readiness.
6. Các demo control endpoints **không được bật khi deploy**. Profile demo chỉ bind loopback để giảm rủi ro trong lab.

### 7.1. Cây thư mục

~~~text
web-runtime-health-demo/
  pom.xml
  mvnw
  mvnw.cmd
  src/
    main/
      java/com/example/probe/
        ProbeApplication.java
        ProbeController.java
        LocalCapacityState.java
        LocalCapacityHealthIndicator.java
        DemoControlController.java
      resources/
        application.yml
        application-demo.yml
    test/
      java/com/example/probe/
        ProbeIntegrationTest.java
~~~

Package name của tất cả Java files là **com.example.probe**; main class nằm ở root package để Spring component scan tìm các classes. Maven wrapper thường do Spring Initializr sinh, nếu tự tạo POM không có wrapper thì dùng lệnh **mvn** thay thế.

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>web-runtime-health-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Version cố định để minh họa Spring Boot 3.3 APIs. Với production, chọn release còn được bảo trì và security patches; không đưa demo control endpoints/profile vào deployment.

### 7.3. ProbeApplication.java

**src/main/java/com/example/probe/ProbeApplication.java**

~~~java
package com.example.probe;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProbeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProbeApplication.class, args);
    }
}
~~~

### 7.4. ProbeController.java — đọc AvailabilityState

**src/main/java/com/example/probe/ProbeController.java**

~~~java
package com.example.probe;

import java.util.Map;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {

    private final ApplicationAvailability availability;

    public ProbeController(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @GetMapping("/demo/ping")
    public Map<String, String> ping() {
        return Map.of("message", "pong");
    }

    @GetMapping("/demo/availability")
    public Map<String, String> availability() {
        return Map.of(
                "liveness", availability.getLivenessState().name(),
                "readiness", availability.getReadinessState().name());
    }
}
~~~

**GET /demo/availability** đọc trạng thái **Spring Boot ApplicationAvailability**, không tổng hợp các health contributors. Nếu custom localCapacity indicator DOWN, endpoint này vẫn có thể hiện readiness **ACCEPTING_TRAFFIC**, trong khi **/readyz** trả **503**. Điều đó đúng: health group kết hợp **readinessState và localCapacity**, không buộc phải ghi ngược vào ApplicationAvailability.

### 7.5. LocalCapacityState.java — state giả lập tại một replica

**src/main/java/com/example/probe/LocalCapacityState.java**

~~~java
package com.example.probe;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class LocalCapacityState {

    private final AtomicBoolean accepting =
            new AtomicBoolean(true);

    public boolean isAccepting() {
        return accepting.get();
    }

    public void setAccepting(boolean value) {
        accepting.set(value);
    }
}
~~~

**AtomicBoolean** an toàn cho việc đọc/ghi một cờ giữa request threads trong lab. Nó không đại diện database capacity thật, không được đồng bộ qua pods và không tự lưu bền vững. Một readiness predicate production phải dựa trên điều kiện có thể quan sát được với timeout, failure handling và concurrency policy rõ ràng.

### 7.6. LocalCapacityHealthIndicator.java

**src/main/java/com/example/probe/LocalCapacityHealthIndicator.java**

~~~java
package com.example.probe;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("localCapacityHealthIndicator")
public class LocalCapacityHealthIndicator implements HealthIndicator {

    private final LocalCapacityState state;

    public LocalCapacityHealthIndicator(LocalCapacityState state) {
        this.state = state;
    }

    @Override
    public Health health() {
        if (state.isAccepting()) {
            return Health.up().build();
        }

        return Health.down()
                .withDetail("reason", "local capacity unavailable")
                .build();
    }
}
~~~

**Tên bean localCapacityHealthIndicator** thường được Actuator ánh xạ thành indicator ID **localCapacity** sau khi bỏ hậu tố HealthIndicator. Vì vậy application.yml có **readiness.include: readinessState,localCapacity**.

Khi state=false:
- Indicator trả **DOWN**.
- Readiness health group tổng hợp **DOWN** và HTTP **503**.
- Liveness group chỉ gồm livenessState vẫn **UP/200** nếu application liveness CORRECT.
- Global health **có thể cũng DOWN** vì nó tổng hợp các indicators; không dùng global health làm liveness.

**Không để health method gọi API bên ngoài không timeout**, chạy truy vấn DB nặng hoặc ném unchecked exception thiếu xử lý ở tần suất probe cao. Health check phải nhanh, không gây side effect, và thông tin health details chỉ nên hiển thị cho người được phép.

### 7.7. DemoControlController.java — đổi readiness bằng event

**src/main/java/com/example/probe/DemoControlController.java**

~~~java
package com.example.probe;

import java.util.Map;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Profile("demo")
@RestController
@RequestMapping("/demo/control")
public class DemoControlController {

    private final ApplicationEventPublisher events;
    private final LocalCapacityState capacity;

    public DemoControlController(
            ApplicationEventPublisher events,
            LocalCapacityState capacity) {
        this.events = events;
        this.capacity = capacity;
    }

    @PostMapping("/refuse")
    public Map<String, String> refuse() {
        AvailabilityChangeEvent.publish(
                events, this, ReadinessState.REFUSING_TRAFFIC);
        return Map.of("readiness", "REFUSING_TRAFFIC");
    }

    @PostMapping("/accept")
    public Map<String, String> accept() {
        AvailabilityChangeEvent.publish(
                events, this, ReadinessState.ACCEPTING_TRAFFIC);
        return Map.of("readiness", "ACCEPTING_TRAFFIC");
    }

    @PostMapping("/capacity/off")
    public Map<String, Boolean> capacityOff() {
        capacity.setAccepting(false);
        return Map.of("localCapacity", false);
    }

    @PostMapping("/capacity/on")
    public Map<String, Boolean> capacityOn() {
        capacity.setAccepting(true);
        return Map.of("localCapacity", true);
    }
}
~~~

**AvailabilityChangeEvent.publish(...)** là API Spring Boot để thông báo đổi availability state. Khi đổi sang **REFUSING_TRAFFIC**, readinessState indicator trả **OUT_OF_SERVICE**, làm /readyz 503 trong khi liveness vẫn UP.

**Cảnh báo:** Đây là controller thử nghiệm có khả năng tác động load balancing; **tuyệt đối không expose trong production**. @Profile("demo") loại class khỏi các profiles khác, và application-demo.yml sẽ bind chỉ loopback cho lab. Không coi @Profile một mình là authentication; nếu bật profile demo trên môi trường có người truy cập, các POST này vẫn cần bảo vệ. Production nên đổi readiness qua internal lifecycle code, overload control hoặc maintenance workflow an toàn, không qua một API công khai.

### 7.8. application.yml — tích hợp probes

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: web-runtime-health-demo

server:
  port: 8080
  shutdown: graceful

management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
        add-additional-paths: true
      group:
        readiness:
          include: "readinessState,localCapacity"

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

**Lưu ý cú pháp YAML quan trọng:** Trong file thật, **không đặt hai root key spring: riêng như đoạn minh họa trên**, bởi một số YAML parsers sẽ xem đó là duplicate mapping và lỗi startup. Hãy dùng **bản application.yml hợp nhất dưới đây**, đây mới là cấu hình chính thức để copy:

~~~yaml
spring:
  application:
    name: web-runtime-health-demo
  lifecycle:
    timeout-per-shutdown-phase: 30s

server:
  port: 8080
  shutdown: graceful

management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
        add-additional-paths: true
      group:
        readiness:
          include: "readinessState,localCapacity"
~~~

**Chỉ dùng block YAML thứ hai** trong src/main/resources/application.yml. Nó khai báo:
- **health,info** là HTTP Actuator endpoints được expose; không expose env, beans, heapdump.
- **probes.enabled: true** để lab local không cần giả làm Kubernetes.
- **add-additional-paths: true** mở /livez và /readyz trên main server port.
- **readiness.include** kết hợp availability state với localCapacity indicator.
- **graceful** và **timeout-per-shutdown-phase: 30s** giúp Spring Boot xử lý in-flight requests khi shutdown, trong giới hạn timeout.
- **show-details: never** tránh lộ details ra HTTP public health endpoint.

**Đừng nhầm root YAML snippet giải thích với file runnable**; chỉ bản hợp nhất là file dùng trong project. Khi cấu hình bằng ConfigMap/Helm, kiểm tra parser thực tế và giữ keys không trùng.

### 7.9. application-demo.yml — chỉ bind loopback trong lab

**src/main/resources/application-demo.yml**

~~~yaml
server:
  address: 127.0.0.1
~~~

Khi kích hoạt **demo profile**, application HTTP chỉ lắng nghe loopback, giảm nguy cơ người khác gọi POST /demo/control/* trên mạng. Default production profile không kích hoạt controller này và không dùng server.address=127.0.0.1, nên khi deploy Kubernetes app có thể lắng nghe trên Pod IP (trừ khi deployment override).

**Không đóng gói/bật demo profile trong production manifest**. Hãy bảo vệ cổng quản trị bằng network policies và service mesh/ingress config theo tiêu chuẩn tổ chức.

### 7.10. Chạy project

Linux/macOS:

~~~bash
./mvnw clean package
java -jar target/web-runtime-health-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=demo
~~~

Windows PowerShell/CMD:

~~~text
mvnw.cmd clean package
java -jar target/web-runtime-health-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=demo
~~~

Nếu project chưa có Maven wrapper, dùng **mvn clean package**. Cổng 8080 phải chưa bị chiếm; khi Spring Boot đã ready, gọi:

~~~bash
curl -i http://localhost:8080/demo/ping
curl -i http://localhost:8080/demo/availability
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
~~~

Khi đã hoàn tất startup và localCapacity=true, các health routes trên trả **HTTP 200** với body status UP. Availability JSON có cấu trúc như:

~~~json
{"liveness":"CORRECT","readiness":"ACCEPTING_TRAFFIC"}
~~~

Thứ tự JSON object keys không phải contract; chỉ xét giá trị.

## 8. Thực nghiệm: readiness 503 nhưng liveness 200

### 8.1. Đổi ApplicationAvailability readiness

Trong lab profile demo:

~~~bash
curl -i -X POST http://localhost:8080/demo/control/refuse
curl -i http://localhost:8080/demo/availability
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/livez
~~~

Kỳ vọng:
- POST /demo/control/refuse trả 200 JSON theo code controller.
- GET /demo/availability thấy **REFUSING_TRAFFIC**.
- GET /readyz trả **503 Service Unavailable**; body thông thường **{"status":"OUT_OF_SERVICE"}** vì readinessState group.
- GET /livez vẫn **200 {"status":"UP"}** vì liveness không đổi.

**Tại sao /readyz còn truy cập được dù REFUSING_TRAFFIC?** Readiness là một tín hiệu **để Kubernetes loại instance khỏi Service traffic**; khi gọi trực tiếp localhost và HTTP connector còn hoạt động, handler vẫn có thể nhận request. Không được coi readiness=false như một firewall tự chặn mọi traffic direct.

Khôi phục:

~~~bash
curl -i -X POST http://localhost:8080/demo/control/accept
curl -i http://localhost:8080/readyz
~~~

Kỳ vọng readiness trở lại **200 UP**, nếu localCapacity vẫn healthy.

### 8.2. Custom HealthIndicator làm readiness fail độc lập

~~~bash
curl -i -X POST http://localhost:8080/demo/control/capacity/off
curl -i http://localhost:8080/demo/availability
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/actuator/health
~~~

Kỳ vọng:
- ApplicationAvailability có thể **vẫn ACCEPTING_TRAFFIC** vì chưa publish readiness event.
- **/readyz** trả **503 DOWN** do **localCapacity** health contributor.
- **/livez** vẫn **200 UP**.
- **/actuator/health** global có thể trả **503** vì có custom DOWN indicator.

Đây là lý do cần phân biệt **AvailabilityState** với **health group aggregation**. Readiness group status có thể fail vì một thành phần dù application readiness enum vẫn ACCEPTING_TRAFFIC.

Khôi phục:

~~~bash
curl -i -X POST http://localhost:8080/demo/control/capacity/on
curl -i http://localhost:8080/readyz
~~~

Chú ý nếu bạn vẫn đang ở REFUSING_TRAFFIC từ thí nghiệm trước, chỉ bật capacity không đủ: cần gọi cả **/demo/control/accept**.

### 8.3. Tổ hợp trạng thái

| LivenessState | ReadinessState | localCapacity | /livez | /readyz |
| --- | --- | --- | --- | --- |
| CORRECT | ACCEPTING_TRAFFIC | true | 200 UP | 200 UP |
| CORRECT | REFUSING_TRAFFIC | true | 200 UP | 503 OUT_OF_SERVICE |
| CORRECT | ACCEPTING_TRAFFIC | false | 200 UP | 503 DOWN |
| CORRECT | REFUSING_TRAFFIC | false | 200 UP | 503 (group có hơn một trạng thái lỗi) |
| BROKEN | Bất kỳ | Bất kỳ | 503 DOWN | Phụ thuộc readiness group |

**Khi liveness BROKEN**, đó thường là lý do để orchestrator restart, không phải trạng thái để thử đặt thủ công trong production nhằm “làm app lành lại”. Mã demo chỉ đổi readiness, không có API giả lập broken liveness để tránh khuyến khích restart không cần thiết.

## 9. Integration test: chạy HTTP thật và kiểm tra 200/503

Chỉ dùng MockMvc có thể xác minh behavior của controller và HealthEndpoint, nhưng không chứng minh endpoint được bind trên main HTTP connector, không kiểm tra port, và không phân biệt management port với app port. Với bài này, ưu tiên **@SpringBootTest(webEnvironment=RANDOM_PORT)** và **TestRestTemplate** để gửi network request tới Tomcat thật.

### 9.1. ProbeIntegrationTest.java hoàn chỉnh

**src/test/java/com/example/probe/ProbeIntegrationTest.java**

~~~java
package com.example.probe;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("demo")
class ProbeIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate http;

    private String url(String path) {
        return "http://localhost:" + port + path;
    }

    private int status(String path) {
        return http.getForEntity(url(path), String.class)
                .getStatusCode().value();
    }

    private void post(String path) {
        ResponseEntity<String> response =
                http.postForEntity(
                        url(path), null, String.class);
        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.OK);
    }

    @Test
    void readinessCanFailWithoutLivenessFailing() {
        try {
            post("/demo/control/accept");
            post("/demo/control/capacity/on");

            assertThat(status("/demo/ping")).isEqualTo(200);
            assertThat(status("/livez")).isEqualTo(200);
            assertThat(status("/readyz")).isEqualTo(200);
            assertThat(status("/actuator/health/readiness"))
                    .isEqualTo(200);

            // Publish ReadinessState.REFUSING_TRAFFIC.
            post("/demo/control/refuse");

            assertThat(status("/readyz")).isEqualTo(503);
            assertThat(status("/livez")).isEqualTo(200);

            // Accept traffic again; local capacity then fails.
            post("/demo/control/accept");
            post("/demo/control/capacity/off");

            assertThat(status("/readyz")).isEqualTo(503);
            assertThat(status("/livez")).isEqualTo(200);
            assertThat(status("/actuator/health")).isEqualTo(503);

            post("/demo/control/capacity/on");
            assertThat(status("/readyz")).isEqualTo(200);
        }
        finally {
            // Reset shared test ApplicationContext state.
            post("/demo/control/accept");
            post("/demo/control/capacity/on");
        }
    }
}
~~~

**Test logic:** nhận kết quả thực từ main web port random, chuyển availability và local indicator, xác nhận readiness có thể fail trong khi liveness vẫn UP. **TestRestTemplate** cố ý không ném exception mặc định khi gặp 4xx/5xx nên test đọc được HTTP 503.

**Lưu ý thực tế:** test này sửa state trong một Spring ApplicationContext chung. Nếu suite chạy tests song song với cùng instance, cần isolate context hoặc đồng bộ test để tránh race. Test cũng không kiểm tra startup window vì **@SpringBootTest chỉ chạy test sau khi application context đã khởi động thành công**. Muốn đo readiness trong quá trình khởi động phải thiết kế test riêng có process và concurrent client.

### 9.2. Chạy test

~~~bash
./mvnw test
~~~

Trong dự án có đủ POM trên, Spring Boot Test và AssertJ/JUnit được cung cấp bởi starter-test. Test yêu cầu profile demo để có controller /demo/control; nếu bỏ **@ActiveProfiles("demo")**, POST endpoints sẽ trả 404, không phải Actuator lỗi.

### 9.3. Điều gì được xác minh và chưa được xác minh?

**Đã kiểm tra qua HTTP thật:**
- /livez và /readyz được map trên main server port.
- AvailabilityChangeEvent thay đổi readiness health group.
- localCapacity indicator có ảnh hưởng tới group.
- HTTP 503 cho readiness fail không kéo liveness thành fail.
- Global health có thể DOWN độc lập với liveness.

**Chưa tự động kiểm tra:**
- Kubelet loại Pod khỏi EndpointSlice trong cluster thật.
- Hành vi load balancer/ingress trong lúc drain.
- Termination grace period khi SIGTERM.
- Spring Security/network policy khi triển khai.
- StartupProbe của Kubernetes và các thresholds.
- Sức chịu tải web connector khi nghẽn thật.

Để nghiệm thu production, cần thử staging với manifests, proxy và các điều kiện lỗi thật.

## 10. Kubernetes Probes: cấu hình và ý nghĩa

### 10.1. Ví dụ Deployment YAML

Với ứng dụng đóng gói container, expose main HTTP port **8080** và không bật profile demo. Trong Kubernetes deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-runtime-health-demo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: web-runtime-health-demo
  template:
    metadata:
      labels:
        app: web-runtime-health-demo
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: example.invalid/web-runtime-health-demo:1.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 24
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
            successThreshold: 1
~~~

**example.invalid/...** là tên image minh họa, không phải registry có sẵn. Bạn cần build/push image thực tế và thiết kế Service, resources, security context, volumes, network policy trước khi deploy.

**Quan trọng:** Deployment này **không bật Spring profile demo**, do đó app không bind loopback theo application-demo.yml và không có POST /demo/control endpoints. Nếu cấu hình môi trường khác đặt server.address=127.0.0.1, kubelet gọi Pod IP có thể bị connection refused; trong container thực cần bind **0.0.0.0** hoặc địa chỉ mà Pod network truy cập được.

### 10.2. Phân biệt các probes trong manifest

- **startupProbe**: trước khi thành công, kubelet **không chạy liveness/readiness probes**; tránh kill app đang khởi động lâu. 5 giây × 24 lần nghĩa là có budget xấp xỉ 120 giây theo kỳ gọi và timeout policy, không phải cam kết chính xác đến mili-giây.
- **livenessProbe**: khi fail liên tục vượt threshold, kubelet restart container.
- **readinessProbe**: khi fail, Pod được đánh dấu không ready và bị loại khỏi tuyến traffic Service tương ứng; tiến trình vẫn có cơ hội tự phục hồi.
- **periodSeconds**: khoảng thời gian dự kiến giữa các lần probe.
- **timeoutSeconds**: chờ tối đa cho một phép đo probe.
- **failureThreshold**: số lần thất bại liên tiếp trước action.
- **successThreshold**: với readiness, số lần pass để quay về ready; thường mặc định 1.

Không đặt ngưỡng quá nhạy với GC pause, cold start, TLS handshake hoặc jitter; cũng không đặt quá lỏng khiến instance lỗi nhận traffic quá lâu. Chọn theo startup distribution, p99 latency, SLO và thực nghiệm load test.

### 10.3. Có cần startupProbe luôn không?

Không nhất thiết. Spring Boot readiness ban đầu là REFUSING_TRAFFIC trong startup, nên readiness failure không tự làm kubelet restart. Nhưng **livenessProbe có thể restart ứng dụng nếu startup lâu**, nhất là JVM khởi động lần đầu, database migration, cache warmup. **startupProbe** thích hợp khi startup time biến động lớn hoặc dài, giúp liveness evaluation bắt đầu sau startup tối thiểu.

Dùng **/livez** cho startupProbe trong bài lab kiểm tra khi app đã đạt live state và HTTP connector chính có thể đáp ứng; **/readyz** cũng có thể là lựa chọn startupProbe nếu muốn startup chỉ hoàn tất khi sẵn sàng traffic, nhưng phải tránh deadlock hoặc dependencies không bao giờ ready. Cần thiết kế theo application lifecycle cụ thể, không chỉ copy một path cho mọi workload.

### 10.4. Kubernetes Service traffic không bằng direct Pod traffic

Readiness fail khiến EndpointSlice/Service không tiếp tục route thông thường tới Pod đó. Nhưng:
- Gọi trực tiếp Pod IP/localhost có thể vẫn chạm endpoint.
- Network connections đang mở hoặc một số proxy caches có thể tiếp tục gửi request trong thời gian chuyển tiếp.
- Nếu **tất cả pods unready**, Service có thể hết available endpoints; ingress/load balancer có thể trả 503 hoặc lỗi kết nối tùy implementation.
- Readiness fail không bảo vệ request khỏi application bug hoặc authorization lỗi.

Vì vậy cần graceful shutdown, connection draining, retries có giới hạn, idempotency và telemetry, không chỉ health probes.

## 11. Management port tách riêng và các bẫy

### 11.1. Ví dụ hai cổng

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

**Đây là cấu hình thay thế/thêm vào deployment**, không copy cùng project y nguyên rồi mặc định hai web ports đều có health URLs giống nhau. Lúc này:
- **/actuator/health**, **/actuator/health/liveness**, **/actuator/health/readiness** nằm ở **port 8081**.
- **/livez**, **/readyz** nằm ở **main port 8080** khi add-additional-paths=true.
- Nếu management endpoints dùng context/base path tùy chỉnh, URL thay đổi theo rules của Spring Boot.

**Probe của kubelet nên gọi 8080 /livez và /readyz** khi mục tiêu là đánh giá web runtime đang phục vụ. Dùng 8081 để hệ thống monitoring thu health thông tin nội bộ cũng được, nhưng không dùng nó làm phép thử duy nhất cho main HTTP connector.

### 11.2. Vì sao health endpoint riêng không phản ánh main connector?

Hai cổng có thể khác:
- Tomcat connector và thread pools;
- request queue và connection limits;
- TLS certificate/termination;
- network policies, firewall hoặc ingress routing;
- Servlet contexts và filters;
- port binding và lỗi socket.

Management endpoint trả UP vì ApplicationAvailability state đang ACCEPTING_TRAFFIC không chứng minh những request thật qua main listener đều xử lý được. **Liveness/readiness additional paths trên main port cải thiện độ tin cậy của tín hiệu kết nối**, nhưng vẫn cần request metrics và tracing cho web traffic.

### 11.3. Context path và custom paths

Với Servlet app:

~~~yaml
server:
  servlet:
    context-path: /shop

management:
  endpoints:
    web:
      base-path: /manage
~~~

Nếu management port không tách, health endpoint theo base path thông thường là **/shop/manage/health**, còn các additional-paths trên main server cần được xác minh theo context path và mapping thực tế. Khi management.server.port được đặt riêng, management base path lại tương đối với **management.server.base-path** thay vì server.servlet.context-path.

**Không hardcode Kubernetes path bằng suy đoán** nếu ứng dụng có nhiều prefix: test curl tới Pod IP/port thật và quan sát mapping trước deploy.

## 12. HealthIndicator tự tạo nên thiết kế như thế nào?

### 12.1. Không tạo side effect

Một HealthIndicator có thể được gọi liên tục mỗi vài giây, từ nhiều nơi. Nó cần:
- xử lý nhanh và có timeout;
- không thay đổi business data;
- không giữ lock dài hoặc tạo transaction nặng;
- không gọi tất cả partner APIs mỗi lần;
- không giữ reference đến HttpServletRequest bất hợp lệ;
- không log secrets hay raw connection strings;
- trả status rõ ràng khi lỗi.

Custom indicator ở demo đọc một AtomicBoolean nên gần như không tạo overhead. Production có thể dùng **cache kết quả** có TTL ngắn hoặc state cập nhật bởi background worker, nếu check trực tiếp tốn kém. Nhưng tránh cache lâu tới mức trạng thái đã fail mà probe vẫn UP quá lâu.

### 12.2. Health group membership

Spring Boot cho phép custom groups:

~~~yaml
management:
  endpoint:
    health:
      group:
        dependencies:
          include: "db,redis"
~~~

Đây là ví dụ **chỉ hợp lệ nếu indicator IDs db và redis thật sự tồn tại** do project có DataSource/Redis auto-config. Nếu include missing contributor, Spring Boot có thể fail startup do validation. Group này thích hợp cho monitoring nội bộ, **không mặc định dùng nó làm liveness/readiness**.

Có thể dùng per-group show-details/roles/status mapping riêng, nhưng tránh show-details=always trên public endpoint. Custom group naming không biến nó thành một Kubernetes probe trừ khi manifest chỉ rõ endpoint đó.

### 12.3. Reactive HealthIndicator

Nếu ứng dụng dùng **Spring WebFlux/Reactor**, các reactive health checks nên implement **ReactiveHealthIndicator**, trả **Mono<Health>**, không block event loop. Spring Boot có ReactiveHealthContributorRegistry và khả năng adapt một số HealthContributor đồng bộ. Ý nghĩa liveness/readiness, ApplicationAvailability và HTTP status tương tự, nhưng connector/runtime/async behavior khác Spring MVC/Tomcat.

### 12.4. Không coi health status là authentication

HTTP 200 trả về từ /readyz không chứng minh user có quyền hoặc dữ liệu hợp lệ. Health routes kiểm tra viability/readiness, authentication/authorization vẫn bảo vệ application APIs. Không đưa internal business data vào health details rồi expose cho Internet.

## 13. Spring Security, network và quan sát HTTP

### 13.1. Actuator có thể bị security chặn

Nếu project thêm **spring-boot-starter-security**, đường health/probes có thể chịu Spring Security filter chain. Nếu bạn tự định nghĩa **SecurityFilterChain**, Spring Boot nhường quyền security rules cho application; không tự bảo đảm /readyz vẫn anonymous accessible. Một **401 Unauthorized** trên readiness URL là sự cố tích hợp probe, không có nghĩa app unready vì health contributor.

Vận hành đúng:
- Cho kubelet/monitoring được gọi liveness/readiness theo cơ chế auth/network phù hợp.
- Không làm public **env, configprops, heapdump, beans, loggers**.
- Giới hạn IP/network policy cho probe endpoints, đặc biệt management port.
- Khi có auth, test **GET /readyz không có cookie/session** theo kubelet.
- Nếu customize SecurityFilterChain, kiểm tra matcher cho **/livez, /readyz**, actuator health groups và application context path.

### 13.2. EndpointRequest và path-based matchers

Spring Boot Actuator có tiện ích **EndpointRequest** cho security matchers của endpoints. Nhưng **/livez và /readyz** là additional paths trên main server, không phải lúc nào cũng được match bởi một rule chỉ cho /actuator/health. Hãy kiểm chứng actual security behavior, và không biến permitAll("/**") thành cách sửa 401.

Nếu dùng mTLS/sidecar/gateway thay cho anonymous health endpoints, đảm bảo kubelet thật sự có quyền gọi bằng request mà nó phát, tránh phụ thuộc browser cookie hoặc user login.

### 13.3. Metrics, traces và readiness

Khi có Spring Boot Actuator, hệ thống có thể thu HTTP metrics, thread/resource metrics và traces qua instrumentation tương ứng. So sánh:
- **/readyz**: binary signal cho traffic routing.
- **http.server.requests**: latency/errors của HTTP server.
- **Tomcat metrics**: threads, connections, sessions tùy instrumentation.
- **JVM metrics**: GC, heap/memory.
- **Tracing**: nơi request chậm hoặc fail.
- **Business SLO**: tỷ lệ thành công của chức năng quan trọng.

Một instance có /readyz 200 nhưng 40% requests trả 500 vẫn cần incident response. Không ép readiness trả DOWN cho mọi 5xx, vì readiness fail diện rộng có thể làm tất cả pods mất endpoints trong đúng lúc cần phục vụ bằng fallback.

## 14. Graceful shutdown và readiness drain

### 14.1. Tác dụng của graceful shutdown

Trong Spring Boot 3.3, cấu hình:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

cho phép Spring Boot quản lý graceful shutdown của web server tương thích. Tomcat thường ngừng nhận request mới và đợi in-flight requests trong giới hạn thời gian, không đảm bảo mọi stream vô hạn hoặc connection đều hoàn tất.

Kubernetes cần **terminationGracePeriodSeconds** lớn hơn budget shutdown và overhead preStop/sidecar nếu có. Trong manifest demo là 45 giây so với shutdown phase 30 giây, chỉ để minh họa; với hệ thật, đo request durations, lifecycle hook duration và load balancer propagation.

### 14.2. Readiness false rồi có cần sleep trước SIGTERM?

Một quy trình bảo trì đôi khi publish REFUSING_TRAFFIC, chờ EndpointSlice/ingress chuyển traffic, rồi gửi shutdown để giảm dropped requests. Nhưng thời gian cần chờ không cố định; phụ thuộc kubelet, scheduler, load balancer và traffic. **Không đơn giản chèn Thread.sleep() tùy tiện** rồi coi drain là bảo đảm. Có thể dùng preStop hook theo hướng dẫn Kubernetes, đồng thời giám sát các kết nối đang xử lý và phân biệt retryable errors.

### 14.3. JVM SIGKILL không có graceful behavior

Nếu container bị OOMKilled, node mất kết nối hoặc bị SIGKILL, không có bảo đảm Spring callbacks hay readiness events chạy. Hạ tầng phải có retry, idempotency, queue redelivery và persistence để xử lý failure bất ngờ, không chỉ phụ thuộc health endpoint.

## 15. Trường hợp lỗi và cách debug

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| **404 /actuator/health/liveness** local | Probes chưa enabled ở môi trường không phải Kubernetes | Bật management.endpoint.health.probes.enabled=true. |
| **404 /livez, /readyz** | Chưa bật add-additional-paths hoặc URL/context path sai | Kiểm tra config và main server mapping. |
| **401/403 từ probe** | SecurityFilterChain/cổng/proxy chặn kubelet | Test request anonymous tương đương kubelet, kiểm tra path matcher/network policy. |
| **/actuator/health 503 nhưng /livez 200** | Global health có contributor DOWN, liveness vẫn CORRECT | Xem health groups và custom indicators, không restart tất cả pods. |
| **/readyz 503, /livez 200** | REFUSING_TRAFFIC hoặc indicator readiness DOWN | Đọc ApplicationAvailability, health group membership và event sources. |
| **/actuator/health/readiness 200 nhưng app cổng chính unreachable** | Quản trị ở port riêng, main connector lỗi | Gọi /readyz trên main server port, xem connector/thread/socket. |
| **Probe bị connection refused khi startup** | HTTP connector chưa bind hoặc Pod chỉ bind loopback | Dùng startupProbe, kiểm tra server.address/port và startup budget. |
| **Pod restart vòng lặp khi DB outage** | Đưa DB vào liveness hoặc dùng global health làm liveness | Giữ liveness độc lập external dependencies. |
| **Tất cả pods unready khi shared DB down** | Readiness include DB chung và thiếu fallback | Đánh giá dependency policy; tránh loại toàn fleet nếu không cần. |
| **App báo ready quá sớm** | Startup công việc thiết yếu chạy async sau ApplicationReadyEvent | Đưa startup tasks bắt buộc vào runners hoặc quản lý readiness rõ. |
| **Không ready dù app xử lý request được** | ReadinessState REFUSING_TRAFFIC, custom indicator DOWN hoặc group sai | Kiểm tra publish events, custom state, HTTP 503 body/status. |
| **Health check chậm/timeout** | Indicator gọi DB/HTTP không timeout hoặc bị lock | Rút gọn check, timeout, cache kết quả, tách monitoring. |
| **Group include lỗi startup** | Member ID không tồn tại | Kiểm tra HealthIndicator bean name/registry, sửa include. |
| **Màn hình monitoring nhìn thấy secrets** | show-details=always hoặc exposed actuator nhạy cảm | Restrict details/roles/network, không log credentials. |
| **K8s liveness Probe pass nhưng 5xx tăng** | Probe chỉ xem viability, không phải business SLO | Dùng metrics/traces/error budgets, cân nhắc overload signal đúng. |
| **503 khi deploy dù local 200** | Context path, management port, proxy rewrite, HTTPS mismatch | Curl trực tiếp Pod/main port và so manifest, config. |
| **Sau SIGTERM còn lỗi request** | Load balancer propagation/in-flight, grace period thiếu | Kiểm tra EndpointSlice, graceful shutdown, preStop, retries. |
| **MockMvc test PASS nhưng K8s vẫn 404 probe** | MockMvc không kiểm tra main connector, package, ingress path | @SpringBootTest RANDOM_PORT và staging Pod test. |
| **UNKNOWN trả 200** | Default HTTP status mapper không map UNKNOWN sang 503 | Xem custom status mappings; không đoán từ tên status. |

### 15.1. Quy trình chẩn đoán có thứ tự

1. Kiểm tra app có **spring-boot-starter-actuator**, Spring Boot version và port đang nghe.
2. Kiểm tra **/actuator/health** có trả JSON/status không.
3. Kiểm tra probes.enabled, add-additional-paths và URLs thật.
4. Gọi **/livez** và **/readyz** trực tiếp trên main port; xác định HTTP 200, 503, 401, 404 hay connection refused.
5. Đọc **ApplicationAvailability** nếu app có diagnostic endpoint nội bộ.
6. Kiểm tra health group includes, indicator bean IDs và slow health checks.
7. Phân biệt management.server.port với server.port, bind address và proxy routing.
8. Kiểm tra Spring Security permit rules và các proxy filters.
9. Với Kubernetes, xem Pod conditions, events, EndpointSlices và probes failure counters.
10. Khi readiness fail diện rộng, đánh giá dependencies chung trước khi restart pods.
11. Khi shutdown, kiểm tra terminationGracePeriodSeconds, graceful shutdown và in-flight connections.
12. Xem metrics/tracing/business SLO để phân tích điều probe không đo được.

Không sửa lỗi bằng cách bật **management.endpoints.web.exposure.include="*"** trên public interface hay vô hiệu hóa security toàn ứng dụng.

## 16. Anti-pattern cần tránh

**1. Dùng /actuator/health làm cả liveness và readiness.** Global health có thể tổng hợp DB/Redis, khiến một dependency chung DOWN làm Kubernetes restart mọi replica.

**2. Mỗi 5 giây chạy truy vấn SELECT lớn trên database trong readiness.** Probe là hoạt động thường xuyên, có thể tăng load khi hệ thống đã chậm. Dùng check nhẹ, timeout và đúng dependency scope.

**3. Bật management.server.port riêng rồi chỉ probe cổng đó.** Cổng main web có thể hỏng trong khi management vẫn UP. Ưu tiên /livez và /readyz trên main server port.

**4. Readiness=false là cơ chế chặn HTTP request.** Không. Orchestrator quyết định routing, còn caller direct Pod IP có thể vẫn gọi được. Cần security và network policy riêng.

**5. Publish LivenessState.BROKEN vì partner API vừa timeout.** Restart app thường không sửa lỗi upstream, có thể tạo cascading failure. Thay bằng circuit breaker, fallback, alert và readiness chỉ khi cần.

**6. Bỏ các lỗi 503 readiness vào HTTP controller @ControllerAdvice để đổi thành 200.** Đây là signal vận hành quan trọng, phải được trả đúng để kubelet xử lý.

**7. Một health check có side effects.** Không dùng readiness để ghi DB, tạo Kafka message, refresh token hoặc xóa cache. Probe phải idempotent và rẻ.

**8. Public demo control endpoints.** Các POST đổi trạng thái readiness trong bài chỉ phục vụ lab loopback; production cần loại bỏ/khóa bằng controls phù hợp.

**9. Mọi indicator luôn trả UP dù code đang lỗi.** Health endpoint giả tạo khiến orchestration và monitoring mất giá trị; phải định nghĩa acceptance criteria thực tế.

**10. Tắt toàn bộ Actuator security vì kubelet nhận 401.** Hãy dùng allow rules/path/network cụ thể, không public env/heapdump/configprops.

## 17. Bài tập thực hành

### Bài 1 — Phân tích lifecycle

Vẽ timeline từ SpringApplication.run đến ApplicationReadyEvent, chỉ ra khi nào liveness CORRECT và readiness ACCEPTING_TRAFFIC. Đặt một ApplicationRunner thực hiện warmup trong môi trường lab và quan sát readiness khi startup chưa xong. Giải thích vì sao listener probe HTTP có thể chưa trả response ở một số giai đoạn.

### Bài 2 — Readiness khác liveness

Chạy demo profile, POST /demo/control/refuse, so status /readyz và /livez. Sau đó POST /demo/control/accept và xác nhận phục hồi. Giải thích vì sao không nên restart instance khi chỉ readiness REFUSING_TRAFFIC.

### Bài 3 — Custom HealthIndicator

POST /demo/control/capacity/off và quan sát /actuator/health, /readyz, /livez, /demo/availability. Giải thích vì sao enum ReadinessState có thể vẫn ACCEPTING_TRAFFIC trong khi readiness group HTTP 503.

### Bài 4 — Management port

Thêm management.server.port=8081. Gọi /actuator/health/readiness qua 8081 và /readyz qua 8080. Giả lập lỗi cấu hình chỉ ảnh hưởng main port trong staging. Giải thích vì sao management probe có thể false positive.

### Bài 5 — Kubernetes rollout

Triển khai với startup/liveness/readiness probes. Tăng thời gian warmup hợp pháp; điều chỉnh threshold để Pod không bị restart trước khi ready. Kiểm tra Pod READY condition, rollout strategy và EndpointSlices. Không bật demo control profile trên cluster.

### Bài 6 — External dependency

Giả sử tất cả replicas chia sẻ một Redis cluster, còn tính năng chính có fallback khi Redis DOWN. Có nên thêm redis vào readiness? So sánh hậu quả "tất cả pods unready" với "vẫn nhận traffic và dùng fallback". Trình bày policy riêng cho liveness/readiness và metric/alert cho Redis outage.

### Bài 7 — Graceful shutdown

Bật server.shutdown=graceful, gửi SIGTERM khi có in-flight requests trong staging. Quan sát log lifecycle, probe behavior, LB drain và requests hoàn tất trước terminationGracePeriodSeconds. Xây dựng SLO: số request bị rớt trong rollout và thời gian phục hồi.

## 18. Checklist trước production

- [ ] Hiểu rõ liveness, readiness, startup và vai trò của Kubernetes đối với từng probe.
- [ ] Actuator dependency/health endpoint có mặt và response status đúng.
- [ ] Probe groups được bật đúng environment; outside Kubernetes đã cấu hình probes.enabled nếu cần.
- [ ] Main server port expose /livez, /readyz; không chỉ dùng management port riêng.
- [ ] Endpoint path/port trong Kubernetes manifest khớp server.servlet.context-path và actual mapping.
- [ ] Liveness không phụ thuộc các external services hoặc DB chung.
- [ ] Readiness include chỉ những checks thiết yếu và instance-specific; thời gian thực thi ngắn.
- [ ] Custom HealthIndicator ID có thật, group membership validation không bị disable che lỗi.
- [ ] HTTP DOWN/OUT_OF_SERVICE trả 503; UP trả 200 theo mapping đã kiểm tra.
- [ ] StartupProbe budget đủ cho cold start/migrations/warmup có giới hạn.
- [ ] Readiness không bị chặn vì auth/session cookie; public Actuator khác vẫn được bảo vệ.
- [ ] Kubelet có thể kết nối Pod IP/main port; không vô tình bind 127.0.0.1.
- [ ] Management port và main port có network/security policy rõ.
- [ ] Graceful shutdown và terminationGracePeriodSeconds được đo và phối hợp.
- [ ] Không có demo readiness toggle endpoints trên production.
- [ ] Probe không làm side effects hoặc log secrets, details không lộ internals.
- [ ] Test 200/503 qua HTTP thật, kiểm tra startup/shutdown trong staging.
- [ ] Có metrics/log/tracing đo tình huống /readyz 200 nhưng business APIs lỗi.
- [ ] Không tự restart toàn fleet khi một external dependency chung DOWN.
- [ ] Runbook phân biệt 401, 404, 503, connection refused và timeout.

## 19. Câu hỏi tự kiểm tra

**1. Readiness fail có khiến Kubernetes restart Pod không?** Không, readiness chủ yếu loại Pod khỏi Service endpoints; liveness hoặc startup failure theo policy mới dẫn tới restart.

**2. Liveness có nên luôn check DB không?** Không. DB outage thường là sự cố external; restart tất cả app replicas có thể gây cascading failure.

**3. Khi nào Boot chuyển readiness sang ACCEPTING_TRAFFIC?** Sau khi SpringApplication chạy xong runners và phát ApplicationReadyEvent rồi availability event tương ứng.

**4. /actuator/health trả 503 có nghĩa /livez cũng 503?** Không. Global health có thể gồm DB/custom contributors, liveness group độc lập.

**5. management.server.port khác main server port có rủi ro gì?** Health trên management web infrastructure có thể báo thành công dù main web connector không phục vụ được.

**6. add-additional-paths=true có tác dụng gì?** Tạo /livez và /readyz health probes trên main server port trong Boot 3.3.

**7. ReadinessState.ACCEPTING_TRAFFIC nhưng /readyz trả 503 có thể xảy ra không?** Có, khi readiness group có một custom HealthIndicator DOWN.

**8. UNKNOWN health status luôn trả 503?** Không theo default status mapping; thường unmapped status gồm UNKNOWN trả HTTP 200.

**9. Vì sao MockMvc không đủ cho bài kiểm tra này?** Nó không xác minh servlet connector/port và network behavior thật; cần RANDOM_PORT HTTP integration test.

**10. StartupProbe dùng để làm gì?** Cho phép ứng dụng có startup dài mà chưa bị đánh giá liveness/readiness; sau khi success, hai probes kia mới chạy.

## 20. Tài liệu chính thức

1. [Spring Boot 3.3 — Actuator Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): health groups, probes.enabled, add-additional-paths, main vs management port, status mappings, liveness/readiness.
2. [Spring Boot 3.3 — SpringApplication and Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): startup events, LivenessState, ReadinessState, ApplicationAvailability, AvailabilityChangeEvent.
3. [Spring Boot 3.3 — Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html): actuator base-path, management port/address, web app runtime.
4. [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): server.shutdown=graceful và lifecycle shutdown timeouts.
5. [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): @SpringBootTest RANDOM_PORT, TestRestTemplate và integration tests.
6. [Kubernetes — Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#container-probes): cơ chế kubelet probes và Pod lifecycle.
7. [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): manifest fields và thời gian probes.
8. [Spring Boot 3.3 — Actuator Health API](https://docs.spring.io/spring-boot/3.3/actuator-api/htmlsingle/#health): HTTP health status và response contract.

**Kết luận:** Muốn kết nối Actuator với web runtime, hãy xem **liveness** là khả năng tiến trình còn hoạt động đúng và **readiness** là quyền nhận thêm traffic của **instance**. Spring Boot quản lý hai trạng thái qua **ApplicationAvailability**, Actuator phản ánh chúng bằng **health groups**, và Kubernetes đưa ra hành động restart/routing dựa trên các probes. Hãy expose **/livez và /readyz trên main HTTP port** khi phù hợp, tránh buộc liveness phụ thuộc database ngoài, thiết kế custom readiness checks gọn và kiểm thử cả **HTTP 200 lẫn 503** qua runtime thật.