# Ranh giới giữa trạng thái vòng đời với các health group của Actuator

## 1. Vấn đề cần giải quyết

Spring Boot hỗ trợ hai cơ chế liên quan nhưng không đồng nhất:

- **Trạng thái khả dụng của ứng dụng (Application Availability)**: các giá trị trong bộ nhớ phản ánh tiến trình khởi động, khả năng hoạt động và khả năng tiếp nhận traffic. Hai trục là `LivenessState` và `ReadinessState`.
- **Actuator Health Endpoint / Health Group**: tập hợp kết quả từ các `HealthIndicator`, tổng hợp thành `Status` rồi chuyển thành phản hồi HTTP. Hai health group quan trọng là `liveness` và `readiness`.

Không thể suy ra chắc chắn một health endpoint trả 200 chỉ từ `ApplicationAvailability.getReadinessState() == ACCEPTING_TRAFFIC`. Ví dụ, nếu readiness group được cấu hình bao gồm một custom HealthIndicator báo `DOWN`, endpoint `/actuator/health/readiness` có thể trả **503** trong khi trạng thái vòng đời vẫn là `ACCEPTING_TRAFFIC`.

Ngược lại, `/actuator/health` toàn cục báo `DOWN` không chứng minh `/actuator/health/readiness` cũng `DOWN`, vì hai endpoint có thể kiểm tra những contributor khác nhau.

Đây là ranh giới quan trọng trong nhóm **Trạng thái sẵn sàng** của Spring Boot Application Runtime: trạng thái là **tín hiệu nội bộ**, còn health group là **chính sách đánh giá và công bố** cho hệ thống giám sát, load balancer hoặc Kubernetes.

### Những câu hỏi bạn sẽ trả lời được

1. `ApplicationAvailability` và `AvailabilityChangeEvent` khác HealthIndicator như thế nào?
2. Khi nào Spring Boot công bố `LivenessState.CORRECT` và `ReadinessState.ACCEPTING_TRAFFIC`?
3. Vì sao readiness health group không tự bao gồm mọi database, Redis và external service indicator?
4. Vì sao state đang accepting nhưng readiness probe HTTP lại là 503?
5. Khi nào thêm external dependency vào readiness là hợp lý, khi nào gây mất traffic toàn bộ hệ thống?
6. Cách viết ứng dụng Spring Boot Java 17+ để tự kiểm chứng sự phân biệt này.

## 2. Mô hình bốn tầng

~~~text
    Các sự kiện SpringApplication và quyết định của ứng dụng
                              |
                   AvailabilityChangeEvent
                              |
                              v
                  ApplicationAvailability
                  /                    \
                 v                      v
           LivenessState            ReadinessState
          CORRECT / BROKEN         ACCEPTING_TRAFFIC /
                                   REFUSING_TRAFFIC
                 |                      |
                 v                      v
       LivenessStateHealthIndicator  ReadinessStateHealthIndicator
                 |                      |
                 v                      v
        Health Group: liveness    Health Group: readiness
           (livenessState)       (readinessState, và tùy chọn khác)
                                        |
                         +--------------+-------------+
                         |                            |
                    Custom HealthIndicator        StatusAggregator
                    như demoDependency            + HttpCodeStatusMapper
                         |                            |
                         +----------------------------+
                                        |
                                 HTTP health response
                           /actuator/health/readiness
                                        |
                         Kubelet / load balancer / monitor
~~~

Mô hình này có bốn lớp:

| Lớp | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Availability state** | Lưu tín hiệu vòng đời/khả dụng nội bộ | `ReadinessState.ACCEPTING_TRAFFIC` |
| **Availability event** | Phát thông tin thay đổi trạng thái | `AvailabilityChangeEvent<ReadinessState>` |
| **Health contributor** | Kiểm tra một điều kiện và trả `Health/Status` | `Health.down().build()` |
| **Health group + HTTP** | Chọn contributor, tổng hợp, ánh xạ status | `/actuator/health/readiness` → 503 |

Một HealthIndicator có thể dựa vào availability state, nhưng một indicator khác có thể kiểm tra cache, disk space hoặc kết nối bên ngoài. Health group quyết định **indicator nào có quyền ảnh hưởng overall status của group**. Đó chính là nơi xuất hiện ranh giới.

### Có ApplicationAvailability thì có Actuator HTTP không?

Không. `ApplicationAvailability` là tính năng của Spring Boot và có thể được inject ngay cả khi không cài Actuator. Muốn có các endpoint HTTP của Actuator, dự án cần dependency `spring-boot-starter-actuator`, một web server/transport thích hợp và cấu hình cho phép phơi bày endpoint.

Thêm Actuator cũng không làm mọi health endpoint đều sẵn sàng ở mọi thời điểm: nếu HTTP server chưa lắng nghe, đang đóng hoặc bị network chặn, bạn có thể gặp lỗi kết nối thay vì nhận một JSON status.

## 3. LivenessState và ReadinessState

### LivenessState: ứng dụng có cần restart?

Spring Boot có hai giá trị chính:

- `CORRECT`: trạng thái nội bộ được xem là còn có thể hoạt động. Một sự cố bên ngoài có thể tự hồi phục không nhất thiết làm liveness hỏng.
- `BROKEN`: ứng dụng được xác định ở tình trạng không thể tự hồi phục theo chính sách, có thể cần restart instance.

**Không nên đưa một phép kiểm tra database hoặc external API vào liveness một cách mặc định.** Nếu database dùng chung bị gián đoạn, restart hàng loạt pod không sửa được database, thậm chí còn gây bão kết nối khi phục hồi.

### ReadinessState: có nên nhận traffic mới?

- `ACCEPTING_TRAFFIC`: ứng dụng thông báo sẵn sàng nhận traffic.
- `REFUSING_TRAFFIC`: ứng dụng thông báo chưa nên nhận traffic mới.

Khác với liveness, readiness có thể tạm từ chối traffic khi đang khởi động, warm-up, quá tải hoặc chuẩn bị shutdown. Kubelet thường sử dụng readiness probe để đưa pod vào hoặc rút pod khỏi danh sách endpoint phục vụ Service. **Readiness fail không phải yêu cầu restart pod**.

### Hai trục là độc lập

Một trạng thái hoàn toàn hợp lý là:

~~~text
LivenessState  = CORRECT
ReadinessState = REFUSING_TRAFFIC
~~~

Nghĩa là JVM và Spring context đang vận hành bình thường nhưng ứng dụng chưa muốn nhận request mới. Đây thường là khoảng thời gian sau refresh context và trước khi runner hoàn thành.

### API truy cập

Trong một bean Spring Boot:

~~~java
@Component
class AvailabilityView {
    private final ApplicationAvailability availability;

    AvailabilityView(ApplicationAvailability availability) {
        this.availability = availability;
    }

    void show() {
        System.out.println(availability.getLivenessState());
        System.out.println(availability.getReadinessState());
    }
}
~~~

Đây là đoạn minh họa, **không phải chương trình Java độc lập**. Cần import `org.springframework.stereotype.Component` và `org.springframework.boot.availability.ApplicationAvailability`; muốn chạy phải nằm trong một Spring Boot application.

Trạng thái này không tự có một phép đo sức khỏe của DB hoặc cache. Nó phản ánh sự kiện availability mà Boot và thành phần ứng dụng đã công bố.

## 4. Mốc vòng đời và trạng thái mặc định

Trình tự Spring Boot 3.5 khái quát:

~~~text
SpringApplication.run(...)
  |
  +-- ApplicationStartingEvent
  +-- Chuẩn bị Environment / ApplicationContext
  +-- ApplicationContext.refresh()
  |
  +-- ApplicationStartedEvent
  +-- AvailabilityChangeEvent: LivenessState.CORRECT
  |
  +-- ApplicationRunner / CommandLineRunner
  |      readiness mặc định vẫn REFUSING_TRAFFIC
  |
  +-- ApplicationReadyEvent
  +-- AvailabilityChangeEvent: ReadinessState.ACCEPTING_TRAFFIC
  |
  v
run() thành công
~~~

Trong giai đoạn chưa startup hoàn tất, Spring Boot xem liveness là `BROKEN` và readiness là `REFUSING_TRAFFIC` theo vòng đời availability. Liveness chuyển sang `CORRECT` sau khi context refresh, còn readiness chỉ chuyển sang `ACCEPTING_TRAFFIC` sau runner và Ready event.

Đáng chú ý: **`ApplicationReadyEvent` đến trước availability event chuyển sang accepting**. Vì thế đừng mặc định một listener nhận chính `ApplicationReadyEvent` đã thấy `getReadinessState() == ACCEPTING_TRAFFIC`.

Trong shutdown, readiness có thể trở lại `REFUSING_TRAFFIC` để hỗ trợ ngừng nhận request mới. Tuy nhiên khi HTTP server đã ngừng chấp nhận kết nối, probe không nhất thiết nhận được response 503; có thể không kết nối được nữa.

| Giai đoạn | Liveness thông thường | Readiness thông thường | HTTP probe |
| --- | --- | --- | --- |
| Bắt đầu, server chưa chạy | `BROKEN` | `REFUSING_TRAFFIC` | Có thể chưa có endpoint để gọi |
| Sau context refresh, trong lúc runner chạy | `CORRECT` | `REFUSING_TRAFFIC` | Có thể phản ánh not ready nếu HTTP đã phục vụ |
| Sau Ready và availability event | `CORRECT` | `ACCEPTING_TRAFFIC` | Thường ready nếu group không có indicator lỗi |
| Graceful shutdown | `CORRECT` | `REFUSING_TRAFFIC` | Có thể không còn phục vụ probe mới |
| Shutdown hoàn tất | Không còn context hoạt động | Không còn context hoạt động | Endpoint đã dừng |

Sự khác biệt giữa state trong bộ nhớ và probe thực tế đặc biệt quan trọng khi phân tích startup timeout hoặc graceful shutdown trên Kubernetes.

## 5. HealthIndicator và Actuator Status

### HealthIndicator không giống AvailabilityState

Trong Spring Boot 3.5, `org.springframework.boot.actuate.health.HealthIndicator` có method `Health health()`. Một HealthIndicator kiểm tra điều kiện cụ thể tại thời điểm được gọi và trả một `Health`.

Ví dụ:

~~~java
@Bean("demoDependency")
HealthIndicator demoDependency(DemoDependencyState state) {
    return () -> state.isUp()
            ? Health.up().build()
            : Health.down().build();
}
~~~

Đoạn trên **minh họa**, cần `@Bean`, `Health`, `HealthIndicator` và lớp `DemoDependencyState`. Chương trình chạy hoàn chỉnh ở mục 8.

Nếu dependency đổi từ UP sang DOWN, indicator sẽ báo `Status.DOWN`. Thao tác đó **không tự phát** `AvailabilityChangeEvent<ReadinessState>` và không nhất thiết làm thay đổi `ApplicationAvailability`.

Ngược lại, khi application phát `ReadinessState.REFUSING_TRAFFIC`, những indicator khác như disk space hoặc demoDependency vẫn có thể `UP`.

### Status và HTTP code

Health của Actuator thường dùng:

| `Status` | Ý nghĩa | HTTP mặc định thường gặp |
| --- | --- | --- |
| `UP` | Thành phần/nhóm đáp ứng điều kiện khỏe | 200 |
| `DOWN` | Thành phần/nhóm bị lỗi | 503 |
| `OUT_OF_SERVICE` | Thành phần/nhóm không nên được dùng | 503 |
| `UNKNOWN` | Chưa xác định được | 200 theo mapping mặc định |

Đây là các quy tắc mặc định, không phải mã cố định cho mọi dự án. Spring Boot cho phép tùy chỉnh `StatusAggregator` và `HttpCodeStatusMapper`, kể cả ở mức health group. Cần phân biệt:

1. **Tổng hợp:** chọn status đại diện từ các contributor trong group.
2. **Ánh xạ:** chuyển status đại diện thành mã HTTP.

Với bộ converter mặc định:

- `LivenessState.CORRECT` thường được `LivenessStateHealthIndicator` biểu diễn thành `UP`.
- `LivenessState.BROKEN` thành `DOWN`.
- `ReadinessState.ACCEPTING_TRAFFIC` thành `UP`.
- `ReadinessState.REFUSING_TRAFFIC` thành `OUT_OF_SERVICE`.

Đây là **phép chuyển đổi state sang health**, không phải một phép đồng nhất enum.

### Global health và health group có thể khác nhau

Actuator có endpoint global `/actuator/health` thường kiểm tra nhiều contributor đang bật. Trong khi đó, `/actuator/health/readiness` chỉ kiểm tra các contributor thuộc readiness group. Vì vậy có thể:

~~~text
ApplicationAvailability.readiness = ACCEPTING_TRAFFIC
/actuator/health/readiness       = UP   (HTTP 200)
/actuator/health                 = DOWN (HTTP 503)
~~~

Một database indicator bị DOWN ở global health nhưng không nằm trong readiness group là ví dụ điển hình. Đây là hành vi theo **chính sách thành viên của group**, không phải lỗi hệ thống.

## 6. Hai health group liveness và readiness

### Bật probe trên máy local

Spring Boot tự bật các health group liveness/readiness trong môi trường Kubernetes được nhận diện. Để bật rõ ràng ở mọi môi trường:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

Khi có Actuator và ứng dụng web, có thể truy cập:

~~~text
/actuator/health
/actuator/health/liveness
/actuator/health/readiness
~~~

Thông thường chỉ health endpoint được expose qua HTTP mặc định; không cần cấu hình expose toàn bộ endpoint quản trị.

### Thành viên mặc định của hai nhóm

~~~text
liveness Health Group:
  livenessState

readiness Health Group:
  readinessState
~~~

Spring Boot **không tự đưa toàn bộ indicator như database, Redis, API bên ngoài vào readiness hoặc liveness group**. Điều này giúp tránh hệ thống mất hàng loạt replica khi một dependency chung gặp sự cố.

### Mở rộng readiness group

Khi nghiệp vụ thật sự cần thêm custom check `demoDependency`:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,demoDependency
~~~

Khi đó:

~~~text
readinessState    -> UP
demoDependency    -> DOWN
          |
          v
StatusAggregator  -> DOWN
          |
          v
HttpCodeStatusMapper -> HTTP 503
~~~

Dù `ApplicationAvailability.getReadinessState()` vẫn là `ACCEPTING_TRAFFIC`, **readiness group đang fail**. Đó chính là chủ đề cốt lõi.

Không nên sao chép `include=*` hoặc đưa mọi external health check vào readiness một cách máy móc. Cần xác định indicator nào có liên hệ **trực tiếp tới khả năng phục vụ traffic thiết yếu**.

Nếu một contributor được cấu hình trong group nhưng không tồn tại, Spring Boot mặc định có thể làm startup thất bại do xác minh membership. Hãy dùng đúng contributor ID, không tắt validation chỉ để che lỗi cấu hình.

### Khi nào nên đưa dependency bên ngoài vào readiness?

Cần trả lời:

- Nếu dependency hỏng, mọi request đều không thể phục vụ được hay vẫn có fallback?
- Dependency có được chia sẻ giữa tất cả pod không?
- Một số chức năng không dùng dependency đó vẫn có thể phục vụ không?
- Health check có nhẹ và có timeout phù hợp không?
- Nếu toàn bộ pod bị rút khỏi load balancer, user có nhận trải nghiệm tốt hơn không?

**Liveness** nên tránh dựa vào dịch vụ bên ngoài vì thất bại của dịch vụ chung có thể kích hoạt restart storm. **Readiness** có thể chứa external check nếu thiếu nó làm instance không thể phục vụ, nhưng đây là quyết định kiến trúc, không phải mặc định của Boot.

## 7. Ma trận tình huống dễ nhầm

Giả định readiness group đã được mở rộng gồm `readinessState` và `demoDependency`, còn liveness group chỉ gồm `livenessState`; mapping mặc định được giữ nguyên.

| Liveness state | Readiness state | Demo dependency | Health liveness | Health readiness |
| --- | --- | --- | --- | --- |
| `CORRECT` | `ACCEPTING_TRAFFIC` | `UP` | UP / 200 | UP / 200 |
| `CORRECT` | `ACCEPTING_TRAFFIC` | `DOWN` | UP / 200 | DOWN / 503 |
| `CORRECT` | `REFUSING_TRAFFIC` | `UP` | UP / 200 | OUT_OF_SERVICE / 503 |
| `CORRECT` | `REFUSING_TRAFFIC` | `DOWN` | UP / 200 | Status xấu / 503 |
| `BROKEN` | `ACCEPTING_TRAFFIC` | `UP` | DOWN / 503 | UP / 200 |

Dòng cuối minh họa hai trục độc lập, không có ý khuyến nghị đặt liveness `BROKEN` trong lúc readiness accepting. Hạ tầng có thể restart instance do liveness probe fail dù readiness group vẫn UP.

Bảng chỉ có ý nghĩa **khi HTTP server đang phục vụ endpoint**. Nếu tiến trình chết, cổng bị chặn hoặc kết thúc shutdown, không có bảo đảm một response HTTP được trả về.

## 8. Ví dụ Java 17+ chạy được với Spring Boot 3.5.16

Chúng ta tạo một ứng dụng Spring MVC + Actuator có một custom HealthIndicator. API demo cho phép đổi độc lập:

- Health của `demoDependency`: UP ↔ DOWN.
- `ReadinessState` của Spring Boot: ACCEPTING_TRAFFIC ↔ REFUSING_TRAFFIC.

Nhờ vậy có thể trực tiếp thấy readiness group không đơn thuần là kết quả của `ApplicationAvailability`.

**Chỉ dùng các endpoint thay đổi trạng thái trong môi trường local/thực hành. Không phơi chúng ở production hoặc mạng công cộng.**

### 8.1. Cấu trúc dự án

~~~text
health-boundary-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/healthboundary/
    │   └── HealthBoundaryApplication.java
    └── resources/
        └── application.properties
~~~

Tệp `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>health-boundary-demo</artifactId>
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

Tệp `src/main/java/com/example/healthboundary/HealthBoundaryApplication.java`:

~~~java
package com.example.healthboundary;

import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HealthBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(HealthBoundaryApplication.class, args);
    }

    @Bean
    DemoDependencyState demoDependencyState() {
        return new DemoDependencyState();
    }

    // Tên bean là health contributor ID: demoDependency.
    @Bean("demoDependency")
    HealthIndicator demoDependencyIndicator(DemoDependencyState state) {
        return () -> state.isUp()
                ? Health.up().build()
                : Health.down().build();
    }

    @Bean
    DemoController demoController(
            DemoDependencyState state,
            ApplicationAvailability availability,
            ApplicationEventPublisher publisher) {
        return new DemoController(state, availability, publisher);
    }

    @Bean
    ApplicationRunner startupTrace(ApplicationAvailability availability) {
        return args -> System.out.println(
                "RUNNER_READINESS=" + availability.getReadinessState());
    }

    static final class DemoDependencyState {
        private final AtomicBoolean up = new AtomicBoolean(true);

        boolean isUp() {
            return up.get();
        }

        void setUp(boolean value) {
            up.set(value);
        }
    }

    @RestController
    static final class DemoController {
        private final DemoDependencyState dependency;
        private final ApplicationAvailability availability;
        private final ApplicationEventPublisher publisher;

        DemoController(DemoDependencyState dependency,
                       ApplicationAvailability availability,
                       ApplicationEventPublisher publisher) {
            this.dependency = dependency;
            this.availability = availability;
            this.publisher = publisher;
        }

        @GetMapping(value = "/demo/state",
                produces = MediaType.APPLICATION_JSON_VALUE)
        public Map<String, String> state() {
            return Map.of(
                    "livenessState",
                    availability.getLivenessState().name(),
                    "readinessState",
                    availability.getReadinessState().name(),
                    "dependency",
                    dependency.isUp() ? "UP" : "DOWN");
        }

        @PostMapping("/demo/dependency/down")
        public String dependencyDown() {
            dependency.setUp(false);
            return "DEPENDENCY_DOWN";
        }

        @PostMapping("/demo/dependency/up")
        public String dependencyUp() {
            dependency.setUp(true);
            return "DEPENDENCY_UP";
        }

        @PostMapping("/demo/readiness/refuse")
        public String refuseTraffic() {
            AvailabilityChangeEvent.publish(
                    publisher, this, ReadinessState.REFUSING_TRAFFIC);
            return "READINESS_REFUSING_TRAFFIC";
        }

        @PostMapping("/demo/readiness/accept")
        public String acceptTraffic() {
            AvailabilityChangeEvent.publish(
                    publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
            return "READINESS_ACCEPTING_TRAFFIC";
        }
    }
}
~~~

Đây là một file Java hoàn chỉnh của dự án Maven trên. Controller là bean được đăng ký bằng phương thức `@Bean` và được nhận diện qua annotation `@RestController`. Bean `HealthIndicator` có tên `demoDependency`, khớp chính xác với ID tham chiếu trong cấu hình group.

`DemoDependencyState` dùng `AtomicBoolean` để có thể cập nhật an toàn tình trạng giả lập trong các request khác nhau. Nó không đại diện cho một kết nối thật; ví dụ chỉ phục vụ kiểm chứng ranh giới.

### 8.2. application.properties

Tệp `src/main/resources/application.properties`:

~~~properties
server.port=8080

# Bật liveness/readiness health group ngay cả trên máy local.
management.endpoint.health.probes.enabled=true

# Kết hợp state của Boot với một custom HealthIndicator.
management.endpoint.health.group.readiness.include=readinessState,demoDependency

# Thêm /livez và /readyz trên cổng web chính.
management.endpoint.health.probes.add-additional-paths=true

# Không phơi health details không cần thiết.
management.endpoint.health.show-details=never
~~~

Không đặt `management.server.port` riêng nên web app và Actuator cùng phục vụ trên cổng 8080. Health endpoint được expose mặc định trong cấu hình Actuator thông thường.

### 8.3. Chạy chương trình

Từ thư mục chứa `pom.xml`:

~~~bash
mvn package
java -jar target/health-boundary-demo-0.0.1-SNAPSHOT.jar
~~~

Hoặc:

~~~bash
mvn spring-boot:run
~~~

Trong log startup, một dòng do mã demo tự in:

~~~text
RUNNER_READINESS=REFUSING_TRAFFIC
~~~

Đây là mốc runner, sau khi context đã refresh nhưng trước `ApplicationReadyEvent` và availability event chuyển readiness sang accepting. Các dòng log do Maven và framework in có thể xen giữa. Khi startup hoàn tất, trong đường bình thường, liveness là `CORRECT`, readiness là `ACCEPTING_TRAFFIC`.

### 8.4. Trường hợp bình thường

Sau khi ứng dụng đã startup xong, chạy trên terminal khác:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/actuator/health
curl -s http://localhost:8080/demo/state
~~~

Kết quả kỳ vọng trong demo:

- Liveness group: `UP`, HTTP 200.
- Readiness group: `UP`, HTTP 200.
- Global health: `UP`, HTTP 200.
- State trong `/demo/state`: `livenessState=CORRECT`, `readinessState=ACCEPTING_TRAFFIC`, `dependency=UP`.

Khi ẩn details, một health response có thể giống:

~~~json
{"status":"UP"}
~~~

Một state response có dạng sau; thứ tự JSON key không được bảo đảm:

~~~json
{
  "livenessState": "CORRECT",
  "readinessState": "ACCEPTING_TRAFFIC",
  "dependency": "UP"
}
~~~

### 8.5. Health group bị DOWN trong khi readiness state vẫn ACCEPTING

Gọi:

~~~bash
curl -X POST http://localhost:8080/demo/dependency/down
curl -s http://localhost:8080/demo/state
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health
~~~

Kết quả kỳ vọng:

| Kiểm tra | Kết quả |
| --- | --- |
| `ApplicationAvailability.getReadinessState()` | Vẫn `ACCEPTING_TRAFFIC` |
| Custom HealthIndicator | `DOWN` |
| Readiness health group | `DOWN`, HTTP 503 |
| Liveness health group | `UP`, HTTP 200 |
| Global health | `DOWN`, HTTP 503 trong demo |

Không có availability event nào tự động được phát khi `dependency.setUp(false)`. **Chỉ health indicator đổi kết quả**, và readiness group tổng hợp hai contributor nên trả 503.

Khôi phục:

~~~bash
curl -X POST http://localhost:8080/demo/dependency/up
curl -i http://localhost:8080/actuator/health/readiness
~~~

Readiness group lại `UP`/200 nếu các contributor còn lại đều khỏe.

### 8.6. ReadinessState chuyển REFUSING dù dependency UP

Đảm bảo dependency đã UP rồi gọi:

~~~bash
curl -X POST http://localhost:8080/demo/readiness/refuse
curl -s http://localhost:8080/demo/state
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/actuator/health/liveness
~~~

Kỳ vọng:

- `/demo/state`: `readinessState=REFUSING_TRAFFIC`, `dependency=UP`.
- ReadinessStateHealthIndicator: `OUT_OF_SERVICE`.
- `/actuator/health/readiness`: 503 theo mapping mặc định.
- `/actuator/health/liveness`: vẫn 200 nếu liveness chưa đổi.

Khôi phục readiness:

~~~bash
curl -X POST http://localhost:8080/demo/readiness/accept
curl -i http://localhost:8080/actuator/health/readiness
~~~

Chú ý: trong ứng dụng thật, chỉ phát `ACCEPTING_TRAFFIC` khi có căn cứ nghiệp vụ; không dùng trạng thái này để che lỗi health indicator.

### 8.7. Đổi group membership sẽ đổi kết quả, không đổi state

Xóa dòng cấu hình:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,demoDependency
~~~

Khởi động lại chương trình. Khi gọi `/demo/dependency/down`, global health có thể `DOWN`, nhưng readiness group mặc định chỉ kiểm tra readinessState, nên vẫn `UP` nếu state là `ACCEPTING_TRAFFIC`.

Điều này chứng minh kết quả HTTP phụ thuộc **group membership**. Thay đổi group là thay đổi phép kiểm tra, không thay enum state của `ApplicationAvailability`.

## 9. Kubernetes: liveness, readiness và startup probe

Kubelet dùng các loại probe cho các quyết định khác nhau:

| Probe | Ý nghĩa vận hành | Cách phản ứng thường gặp |
| --- | --- | --- |
| Liveness | Tiến trình có cần restart vì không thể tự phục hồi? | Restart container khi liên tục fail |
| Readiness | Có nên đưa pod vào danh sách endpoint nhận traffic? | Rút hoặc thêm pod vào traffic |
| Startup | Có cần thời gian dài hơn trước khi áp dụng liveness/readiness? | Trì hoãn tác động của các probe còn lại lúc startup |

Ví dụ YAML minh họa cho app trên:

~~~yaml
livenessProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
  periodSeconds: 5
  failureThreshold: 2

startupProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 5
  failureThreshold: 30
~~~

Đây là đoạn cấu hình probe bên trong container spec, **không phải Kubernetes manifest đầy đủ**. Chỉ dùng sau khi kiểm tra image, cổng, thời gian khởi động và tài nguyên thực tế.

`/livez` và `/readyz` có nhờ `management.endpoint.health.probes.add-additional-paths=true`. Nếu không bật additional paths, cần dùng các URL /actuator/health/liveness và /actuator/health/readiness phù hợp với cổng thực tế.

### Management port riêng

Khi Actuator chạy trên `management.server.port` khác cổng nghiệp vụ, health endpoint ở management port có thể trả 200 trong khi web server chính không nhận request. Vì thế nên cân nhắc đặt thêm probe path trên **cổng server chính**; đó là cách kiểm tra gần với con đường traffic nghiệp vụ hơn.

Tuy nhiên, kể cả probe trên main port cũng chỉ kiểm tra điều kiện của group. Không có probe nào tự bảo đảm tất cả endpoint và tất cả upstream đều hoạt động nếu không được kiểm tra.

### Vì sao không đưa database vào liveness?

Khi nhiều instance cùng dùng một DB và DB lỗi tạm thời, nếu liveness group có DB indicator, kubelet có thể restart toàn bộ instance. Việc restart không sửa được DB, còn làm tăng tải trong giai đoạn phục hồi. Chỉ dùng liveness để phát hiện lỗi nội bộ không thể tự hồi phục.

### Có nên đưa DB vào readiness?

Tùy nhu cầu:
- Nếu mọi request đều bắt buộc có DB và không có fallback, việc đưa DB vào readiness có thể hợp lý.
- Nếu hệ thống có cache/circuit breaker phục vụ được khi DB lỗi, đưa DB vào readiness có thể làm mất traffic không cần thiết.
- Nếu DB được chia sẻ bởi tất cả replica, đặt DB trong readiness đồng nghĩa một sự cố DB có thể khiến **tất cả replica unready**. Cần chấp nhận và thiết kế rõ hậu quả này.

Đừng chạy kiểm tra DB quá nặng cho mọi HTTP probe; dùng timeout và tần suất hợp lý.

## 10. Shutdown và thời điểm HTTP không thể phản ánh state

Spring Boot có thể đưa readiness về `REFUSING_TRAFFIC` khi chuẩn bị dừng. Nhưng nếu HTTP server đã ngừng nhận kết nối, một probe không còn được đảm bảo nhận phản hồi 503. Có sự khác biệt giữa:

~~~text
ApplicationAvailability.readiness = REFUSING_TRAFFIC
~~~

và:

~~~text
curl /actuator/health/readiness luôn nhận được HTTP 503
~~~

Mệnh đề thứ hai không đúng trong mọi giai đoạn. Khi JVM crash, bị `SIGKILL`, mất điện hoặc network bị ngắt, không có đường HTTP nào để trả status.

Cấu hình tham khảo cho graceful shutdown trên web server hỗ trợ:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Cần phối hợp với termination grace period và drain của load balancer/Kubernetes. Health endpoint là tín hiệu, không thay thế hoàn toàn cơ chế dừng nhận request mới.

## 11. Những lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Có `ApplicationAvailability` nhưng /readiness 404 | Thiếu Actuator, probes chưa bật ngoài Kubernetes, sai port/path hoặc endpoint không expose | Kiểm tra dependency, `management.endpoint.health.probes.enabled` và web server |
| ReadinessState là `ACCEPTING_TRAFFIC` nhưng /readiness 503 | Thêm health indicator DOWN vào group, mapping tùy biến | Kiểm tra membership, status của từng contributor |
| Global health 503 nhưng readiness 200 | Global và readiness group chọn thành viên khác nhau | So sánh `/actuator/health` với group include |
| Liveness 503 chỉ vì DB bị lỗi | Đưa external check vào liveness | Tách external check khỏi liveness để tránh restart storm |
| Startup fail khi thêm group include | Contributor ID gõ sai hoặc chưa được tạo | Đối chiếu bean name và group membership |
| /readyz 404 | Chưa bật additional paths, sai cổng | Kiểm tra property và main server port |
| Probe 200 nhưng API vẫn lỗi | Tiêu chí probe thiếu điều kiện nghiệp vụ quan trọng | Thiết kế health theo khả năng phục vụ thật |
| Probe 503/200 liên tục | Indicator chậm, phụ thuộc chập chờn, timeout quá nhạy | Giảm chi phí check, điều chỉnh threshold và retry |
| Readiness đã refuse nhưng vẫn thấy request | LB/kubelet chưa cập nhật, có request đang bay, bypass Service | Kiểm tra routing và propagation |
| Actuator management port UP nhưng app main port không kết nối | Hai port dùng đường HTTP khác nhau | Cân nhắc additional paths trên main port |
| Shutdown không trả response 503 cuối cùng | HTTP server đang đóng hoặc bị kill | Không giả định có HTTP response trong mọi giai đoạn |
| Chi tiết health lộ thông tin nội bộ | Cấu hình show-details quá rộng | Ẩn details, giới hạn quyền và endpoint exposure |

### Quy trình debug theo thứ tự

1. Xác định **đúng replica, thời điểm, URL và port**. Đừng so state của pod A với probe của pod B.
2. Kiểm tra `ApplicationAvailability.getReadinessState()` và `getLivenessState()` ở instance cần chẩn đoán.
3. Kiểm tra group membership bằng cấu hình, xác định từng `HealthContributor` trong readiness/liveness.
4. Xác định HTTP response thật do Actuator hay do Ingress/Proxy trả. 404, 401, connection refused và 503 là các loại lỗi khác nhau.
5. Kiểm tra phase startup/shutdown: runner đã xong? Ready event đã phát? Đang graceful shutdown?
6. Xem `StatusAggregator` và HTTP mapping nếu project có tùy biến; đừng mặc định mọi status lạ phải thành 503.
7. Rà timeout, tần suất probe và nguồn phụ thuộc shared, tránh gây restart storm hoặc traffic flapping.
8. Sửa đúng chính sách readiness hoặc lỗi dependency, thay vì ép state sang ACCEPTING_TRAFFIC để che một contributor đang DOWN.

## 12. Câu hỏi tự kiểm tra

**Câu 1:** `ApplicationAvailability.getReadinessState()` là ACCEPTING thì readiness health group chắc chắn UP?

**Trả lời:** Không. Group có thể bao gồm contributor khác đang DOWN, nên overall status có thể DOWN và HTTP 503.

**Câu 2:** Nếu /actuator/health DOWN, readiness group mặc định có nhất thiết DOWN không?

**Trả lời:** Không. Global health có thể bao gồm DB/disk check nhưng readiness mặc định tập trung vào readinessState.

**Câu 3:** Đổi kết quả `HealthIndicator` có làm `AvailabilityChangeEvent` tự được phát không?

**Trả lời:** Không. Một health contributor độc lập chỉ thay đổi kết quả khi được hỏi; sự kiện availability là cơ chế khác.

**Câu 4:** Khi nào Boot thông thường công bố `LivenessState.CORRECT` và `ReadinessState.ACCEPTING_TRAFFIC`?

**Trả lời:** Sau ApplicationStartedEvent là liveness CORRECT; sau các runner và ApplicationReadyEvent là readiness ACCEPTING_TRAFFIC.

**Câu 5:** Readiness fail có tự restart pod không?

**Trả lời:** Không. Readiness chủ yếu loại pod khỏi traffic; liveness fail mới có thể khiến kubelet restart container theo cấu hình probe.

**Câu 6:** Vì sao không dùng `/actuator/health` làm liveness cho mọi ứng dụng?

**Trả lời:** Global health có thể chứa dependency ngoài; một lỗi shared dependency sẽ làm liveness fail, kích hoạt restart hàng loạt dù ứng dụng không hỏng nội bộ.

**Câu 7:** Có thể luôn nhận HTTP 503 khi readiness là REFUSING_TRAFFIC?

**Trả lời:** Không. Nếu HTTP server chưa chạy hoặc đã dừng thì không có response. Khi endpoint còn phục vụ, mapping của readinessState thường trả OUT_OF_SERVICE/503.

**Câu 8:** Health group có thể tự chọn contributor nào tham gia không?

**Trả lời:** Có, thông qua cấu hình include/exclude và contributor registry. Đây là nơi cấu hình chính sách probe ngoài trạng thái vòng đời.

**Câu 9:** Vì sao health indicator chậm có thể làm probe không ổn định?

**Trả lời:** Kết quả HTTP cần đợi phép kiểm tra; network I/O chậm và timeout có thể gây probe failure hoặc nghẽn tài nguyên. Nên thiết kế check nhẹ, có timeout và phản ánh trạng thái có ý nghĩa.

**Câu 10:** Làm sao quan sát độc lập state và health group trong demo?

**Trả lời:** Dùng `/demo/state` xem ApplicationAvailability và demoDependency; dùng `/actuator/health/readiness` xem health group. Tắt dependency mà không phát AvailabilityChangeEvent để thấy khác biệt.

## 13. Bài tập thực hành

**Bài tập A — tách hai nguồn trạng thái:** Chạy demo mục 8. Ghi lại `/demo/state`, liveness HTTP và readiness HTTP trước/sau khi POST /demo/dependency/down. Giải thích vì sao availability không đổi nhưng readiness group fail.

**Bài tập B — thay đổi readiness state:** Khôi phục dependency UP, sau đó POST /demo/readiness/refuse. Đối chiếu health liveness và readiness. Khôi phục bằng POST /demo/readiness/accept.

**Bài tập C — bỏ custom indicator khỏi group:** Xóa cấu hình `readiness.include`, restart và lặp lại bài A. So sánh global health với readiness. Mô tả vai trò của membership.

**Bài tập D — tình huống ba replica:** Giả sử ba pod cùng truy cập một database chung. So sánh kết quả khi đưa DB vào liveness, readiness và chỉ global health. Phân tích bão restart, mất tất cả endpoint và trường hợp có cache fallback.

**Bài tập E — main port và management port:** Thử đặt `management.server.port=8081` rồi bật additional paths. Xác minh `/readyz` trên cổng ứng dụng chính và `/actuator/health/readiness` trên management port. Giải thích vì sao mỗi con đường kiểm tra có giá trị khác nhau.

**Bài tập F — runner kéo dài:** Thêm runner mô phỏng một công việc startup có giới hạn thời gian. Quan sát lúc chạy runner readiness vẫn refuse và chỉ accepting sau Ready. Không dùng `sleep` giả lập làm logic sản xuất.

## 14. Tài liệu chính thức và ghi nhớ

Tài liệu Spring Boot 3.5 dùng để đối chiếu hợp đồng:

- [Spring Boot 3.5 — Application Availability và Application Events](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html).
- [Spring Boot 3.5 — Actuator Health Groups và Kubernetes Probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html).
- [Spring Boot 3.5 — ApplicationAvailability Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailability.html).
- [Spring Boot 3.5 — AvailabilityChangeEvent Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html).
- [Spring Boot 3.5 — HealthIndicator Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/health/HealthIndicator.html).
- [Spring Boot 3.5 — Status Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/health/Status.html).

**Ghi nhớ:**

1. `ApplicationAvailability` giữ tín hiệu vòng đời trong bộ nhớ, không phải bản thân HTTP health endpoint.
2. `AvailabilityChangeEvent` cập nhật state; `HealthIndicator` có thể kiểm tra điều kiện riêng biệt.
3. Liveness và readiness health group chỉ chọn các contributor theo cấu hình, không mặc định bao gồm mọi dependency ngoài.
4. Health group tổng hợp Status và ánh xạ HTTP; ACCEPTING_TRAFFIC có thể cùng tồn tại với readiness group DOWN/503 nếu có custom indicator DOWN.
5. Global health DOWN không tự suy ra readiness group DOWN, và ngược lại.
6. Readiness fail là tín hiệu không nhận traffic; liveness fail thường là tín hiệu có thể cần restart. Đừng làm liveness phụ thuộc DB hoặc hệ thống bên ngoài một cách tùy tiện.
7. Khi chưa có web server hoặc đang shutdown, không đảm bảo probe HTTP trả lời; state nội bộ và khả năng phục vụ endpoint là hai vấn đề.
8. Kiểm thử group membership, HTTP mapper, shutdown, cổng management/main và timing của Kubernetes trước khi quyết định readiness policy.
