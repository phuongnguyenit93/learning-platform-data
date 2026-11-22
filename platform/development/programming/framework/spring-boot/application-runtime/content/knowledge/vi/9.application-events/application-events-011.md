# AvailabilityChangeEvent chuyển trạng thái readiness sau ApplicationReadyEvent

**Module:** Spring Boot Application Runtime. **Nhóm:** Sự kiện ứng dụng. Bài học tập trung vào chuỗi sự kiện lúc ứng dụng chuyển từ giai đoạn khởi động sang sẵn sàng nhận lưu lượng: Spring Boot phát `ApplicationReadyEvent` khi quá trình startup, bao gồm các runner, đã kết thúc thành công; **sau đó** Boot công bố `AvailabilityChangeEvent<ReadinessState>` mang giá trị `ReadinessState.ACCEPTING_TRAFFIC`. Nội dung dùng **Java 17+ và Spring Boot 3.5.x** với Spring MVC, Actuator và ví dụ tái lập được; hành vi chi tiết cần đối chiếu lại theo dòng Spring Boot đang dùng.

## 1. Mục tiêu học

Sau bài này, người học có thể:

1. Giải thích sự khác nhau giữa `ApplicationReadyEvent`, `AvailabilityChangeEvent`, `ApplicationAvailability`, `ReadinessState` và `LivenessState`.
2. Xác định chính xác thứ tự: **refresh context → started event → runners → ready event → công bố readiness nhận traffic** trong startup thông thường.
3. Hiểu ý nghĩa của hai readiness states `REFUSING_TRAFFIC` và `ACCEPTING_TRAFFIC`; phân biệt readiness và liveness.
4. Đọc trạng thái qua API `ApplicationAvailability.getReadinessState()` và nhận event bằng `@EventListener`.
5. Kiểm tra `/actuator/health/readiness` / `/actuator/health/liveness`, diễn giải `200 UP` và `503 OUT_OF_SERVICE` theo mapping mặc định.
6. Tự công bố một sự kiện readiness có kiểm soát trong môi trường lab, rồi xác nhận giá trị trong JVM và ở HTTP probe thay đổi.
7. Thiết kế đúng việc nhận traffic trong container/orchestrator: health probe, startup probe, grace period, shutdown và giới hạn của việc chỉ nhìn log.

**Thông điệp chính:** `ApplicationReadyEvent` là một **mốc sự kiện startup**, còn `ReadinessState.ACCEPTING_TRAFFIC` là **trạng thái sẵn sàng được công bố sau mốc đó**. Cả hai không phải lời cam kết rằng mọi request nghiệp vụ sẽ thành công, mọi kết nối bên ngoài đều khỏe, hoặc Kubernetes đã lập tức gửi traffic.

## 2. Các khái niệm cần phân biệt

### 2.1. ApplicationReadyEvent

`org.springframework.boot.context.event.ApplicationReadyEvent` được phát khi `SpringApplication` hoàn thành startup và các `ApplicationRunner`/`CommandLineRunner` đã kết thúc. Đây là sự kiện đến muộn trong startup. Nếu một runner ném exception, ứng dụng thường **không** đạt mốc ready. Một ứng dụng có nhiều context hoặc listener bất đồng bộ có thể có chi tiết khác, nhưng contract cốt lõi vẫn là ready event đứng sau runner trong luồng Boot thông thường.

Một listener có thể viết:

~~~java
@EventListener(ApplicationReadyEvent.class)
public void onReady() {
    System.out.println("LAB_APPLICATION_READY_EVENT");
}
~~~

Đây là method snippet đặt trong một Spring-managed bean, **không phải chương trình Java độc lập**.

### 2.2. AvailabilityChangeEvent

`org.springframework.boot.availability.AvailabilityChangeEvent<S extends AvailabilityState>` là Spring application event thông báo một trạng thái availability đã thay đổi. `getState()` trả về trạng thái được công bố. Spring Boot sử dụng sự kiện này để cập nhật `ApplicationAvailability` và cho các thành phần quan sát phản ứng.

Ví dụ sự kiện có type state là `ReadinessState`. Sự kiện chứa **giá trị trạng thái**, khác với listener đọc một property trong file cấu hình. Framework hoặc ứng dụng có thể publish sự kiện mới khi tình trạng thay đổi; trạng thái mới sẽ là trạng thái hiện hành theo cơ chế xử lý sự kiện.

### 2.3. ReadinessState

`org.springframework.boot.availability.ReadinessState` có hai giá trị chuẩn:

| ReadinessState | Ý nghĩa | Hành động khuyến nghị cho hạ tầng |
|---|---|---|
| `REFUSING_TRAFFIC` | Instance không sẵn lòng nhận thêm traffic | Tạm ngừng đưa request mới vào instance |
| `ACCEPTING_TRAFFIC` | Instance công bố sẵn sàng nhận traffic | Instance có thể được cân nhắc đưa vào tuyến traffic |

`REFUSING_TRAFFIC` không có nghĩa JVM đã chết, không có nghĩa process phải restart và cũng không khẳng định mọi endpoint tại cổng HTTP đều tự động trả 503. Nó là **tín hiệu về khả năng nhận traffic**, thường được chuyển thành kết quả HTTP probe qua Spring Boot Actuator.

### 2.4. LivenessState

`LivenessState.CORRECT` nghĩa là ứng dụng ở trạng thái sống bình thường theo tín hiệu nội bộ; `BROKEN` là trạng thái không thể tự phục hồi theo định nghĩa liveness. Khác biệt quan trọng:

- **Readiness thất bại:** tạm dừng routing traffic đến instance, chờ khôi phục hoặc xử lý.
- **Liveness thất bại:** orchestrator có thể restart instance; vì vậy **không** gắn liveness với một database chung đang outage, kẻo tất cả replica restart vòng lặp.
- `LivenessState.CORRECT` có thể tồn tại song song với `ReadinessState.REFUSING_TRAFFIC` — ví dụ runner còn đang làm việc hoặc ứng dụng tạm ngưng nhận traffic.

### 2.5. ApplicationAvailability

`ApplicationAvailability` là interface để code đọc snapshot availability. Hai method tiện dùng:

~~~java
ReadinessState readiness = availability.getReadinessState();
LivenessState liveness = availability.getLivenessState();
~~~

Ứng dụng nên dùng event để **thay đổi** trạng thái, thay vì cố can thiệp state nội bộ của implementation. `ApplicationAvailabilityBean` là implementation mặc định của Spring Boot và theo dõi các sự kiện thay đổi trạng thái.

## 3. Thứ tự chính xác của startup và dấu mốc readiness

~~~text
main()
   |
   v
SpringApplication.run(args)
   |
   +-- Environment, ApplicationContext, bean definitions
   +-- ApplicationContext.refresh() hoàn thành
   |     +-- ContextRefreshedEvent
   |
   +-- ApplicationStartedEvent
   +-- AvailabilityChangeEvent<LivenessState.CORRECT>
   |
   +-- ApplicationRunner / CommandLineRunner thực thi
   |     +-- nếu còn bận: readiness vẫn REFUSING_TRAFFIC
   |     +-- nếu lỗi: không tiến đến ready thông thường
   |
   +-- ApplicationReadyEvent
   |     +-- listener nhận mốc ready
   |
   +-- AvailabilityChangeEvent<ReadinessState.ACCEPTING_TRAFFIC>
   |     +-- ApplicationAvailability cập nhật
   |     +-- readiness health indicator trả UP
   |
   v
Instance sẵn lòng nhận traffic
~~~

Sơ đồ mô tả **luồng startup thành công** của Spring Boot 3.5. Thứ tự thực thi các listener có thể phụ thuộc cơ chế multicast, nhưng event readiness `ACCEPTING_TRAFFIC` do Boot phát theo vòng đời mặc định xảy ra **sau** khi phát `ApplicationReadyEvent`. Đừng kiểm tra readiness bằng cách giả định giá trị đã là `ACCEPTING_TRAFFIC` **bên trong chính listener `ApplicationReadyEvent`**: ở thời điểm đó event thay đổi readiness mặc định chưa được phát, nên snapshot có thể vẫn là `REFUSING_TRAFFIC`.

Bởi vậy:

- `ContextRefreshedEvent`: context đã refresh; **không** phải mốc sẵn sàng.
- `ApplicationStartedEvent`: refresh xong, còn runner.
- `ApplicationReadyEvent`: runner đã hoàn thành; Boot đã phát mốc ready.
- `AvailabilityChangeEvent<ReadinessState.ACCEPTING_TRAFFIC>`: signal readiness hậu ready.
- Hạ tầng probe/orchestrator: cần thăm dò trạng thái, có cache/chu kỳ kiểm tra riêng nên có thể nhận biết muộn hơn sự kiện JVM.

## 4. Availability, HTTP health probe và traffic routing là ba lớp

**Lớp 1 — JVM:** `ApplicationAvailability.getReadinessState()` là snapshot trạng thái của process.

**Lớp 2 — Spring Boot Actuator:** `ReadinessStateHealthIndicator` chuyển trạng thái đó thành health status. Với cấu hình thông thường, `ACCEPTING_TRAFFIC` → `UP`, `REFUSING_TRAFFIC` → `OUT_OF_SERVICE`. Theo HTTP mapping mặc định, `UP` trả HTTP 200 và `OUT_OF_SERVICE` trả HTTP 503. Nếu thay health group hoặc HTTP status mapping, kết quả có thể khác.

**Lớp 3 — hạ tầng:** Kubernetes hoặc load balancer gọi probe theo chu kỳ, quyết định có chuyển request vào instance không. **Không** có quan hệ đồng bộ tức thời “event in log → load balancer chuyển traffic ngay”.

Đặc biệt, trước khi embedded web server mở cổng, probe có thể **không kết nối được**; không phải lúc nào phase chưa ready cũng quan sát được một HTTP 503. Khi web server đã mở nhưng readiness chưa đạt, probe có thể trả 503. Sau khi shutdown, HTTP server lại có thể không truy cập được dù trạng thái shutdown đã được công bố trước đó.

Bảng theo luồng mặc định:

| Pha | Liveness | Readiness | Nhận định |
|---|---|---|---|
| Mới khởi động | Có thể chưa sống theo probe | `REFUSING_TRAFFIC` | Không dùng traffic để kiểm tra app trước startup |
| Context đã refresh, runner chưa xong | `CORRECT` | `REFUSING_TRAFFIC` | Process sống nhưng chưa nên nhận traffic |
| Sau ready + readiness change | `CORRECT` | `ACCEPTING_TRAFFIC` | Instance đã phát tín hiệu sẵn sàng |
| Chủ động giảm tải | Thường `CORRECT` | `REFUSING_TRAFFIC` | Tạm bỏ instance khỏi routing |
| Graceful shutdown | Có thể vẫn `CORRECT` | `REFUSING_TRAFFIC` | Ngừng đưa traffic mới, dọn request đang chạy |
| Kết thúc process | Không còn | Không còn | Probe không thể gọi được |

## 5. Dựng ứng dụng mẫu Java 17 / Spring Boot 3.5

### 5.1. Tạo project

Sử dụng Spring Initializr tạo Maven project:

- Group: `com.example`
- Artifact: `readiness-lab`
- Package: `com.example.readinesslab`
- Java: **17**
- Spring Boot: **3.5.x**
- Dependencies: **Spring Web**, **Spring Boot Actuator**
- Packaging: JAR.

Giữ `pom.xml` và Maven Wrapper sinh từ Initializr. Tạo cấu trúc:

~~~text
readiness-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/readinesslab/
    ReadinessLabApplication.java
    ReadinessEventLogger.java
    ReadinessController.java
  src/main/resources/
    application.properties
~~~

Các file Java bên dưới là chương trình hoàn chỉnh **khi đặt trong cùng project và Maven classpath**. Không chạy `javac ReadinessLabApplication.java` riêng lẻ khi chưa có các Spring dependencies.

### 5.2. Main, runner và marker ApplicationReadyEvent

File `src/main/java/com/example/readinesslab/ReadinessLabApplication.java`:

~~~java
package com.example.readinesslab;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class ReadinessLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReadinessLabApplication.class, args);
    }

    @Bean
    ApplicationRunner startupRunner(
            @Value("${lab.runner.delay-ms:0}") long delayMillis) {
        return args -> {
            System.out.println("LAB_RUNNER_BEGIN");
            if (delayMillis > 0) {
                Thread.sleep(delayMillis);
            }
            System.out.println("LAB_RUNNER_DONE");
        };
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady(
            ApplicationReadyEvent event) {
        ApplicationAvailability availability =
                event.getApplicationContext()
                        .getBean(ApplicationAvailability.class);
        System.out.println("LAB_APPLICATION_READY_EVENT"
                + " currentReadiness="
                + availability.getReadinessState());
    }
}
~~~

**Giải thích:** `ApplicationRunner` chạy sau refresh nhưng trước ready. Cấu hình `lab.runner.delay-ms` dùng để cố tình kéo dài runner trong lab mà không cần thay code. `Thread.sleep(...)` ở đây chỉ để **quan sát pha startup**; production không nên chặn runner bằng sleep tùy ý. Nếu runner ném exception hoặc bị dừng, app không đạt mốc ready bình thường.

Listener `ApplicationReadyEvent` đọc `ApplicationAvailability` để minh họa rằng việc nhận ready event và việc có state `ACCEPTING_TRAFFIC` là hai thời điểm sát nhau nhưng **khác nhau**. Khi không có các publisher tùy chỉnh can thiệp, giá trị in tại đây thông thường vẫn là `REFUSING_TRAFFIC`; ngay sau đó Boot phát sự kiện accepting.

### 5.3. Listener nhận AvailabilityChangeEvent<ReadinessState>

File `src/main/java/com/example/readinesslab/ReadinessEventLogger.java`:

~~~java
package com.example.readinesslab;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadinessEventLogger {

    @EventListener
    public void onReadinessChanged(
            AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println(
                "LAB_READINESS_EVENT=" + event.getState());
    }
}
~~~

Ở đây, type parameter `ReadinessState` làm listener tập trung vào các sự kiện readiness. Spring có thể có các availability events khác cho liveness; chúng không phải mục tiêu của listener này. Khi chạy, marker `LAB_READINESS_EVENT=ACCEPTING_TRAFFIC` xuất hiện sau marker `LAB_APPLICATION_READY_EVENT` theo flow mặc định.

Không dùng marker này làm điều kiện bảo đảm mọi bean lazy hoặc dependency ngoài đã khỏe; nó chỉ xác nhận availability change đã được công bố.

### 5.4. Controller đọc và công bố trạng thái có kiểm soát

File `src/main/java/com/example/readinesslab/ReadinessController.java`:

~~~java
package com.example.readinesslab;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReadinessController {

    private final ApplicationAvailability availability;
    private final ApplicationContext context;

    public ReadinessController(
            ApplicationAvailability availability,
            ApplicationContext context) {
        this.availability = availability;
        this.context = context;
    }

    @GetMapping("/demo/status")
    public ReadinessStatus status() {
        return new ReadinessStatus(
                availability.getReadinessState().name(),
                availability.getLivenessState().name());
    }

    @PostMapping("/demo/refuse")
    public ReadinessStatus refuse() {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.REFUSING_TRAFFIC);
        return status();
    }

    @PostMapping("/demo/accept")
    public ReadinessStatus accept() {
        AvailabilityChangeEvent.publish(
                context, ReadinessState.ACCEPTING_TRAFFIC);
        return status();
    }

    public record ReadinessStatus(
            String readiness, String liveness) {
    }
}
~~~

Đây là **lab minh họa**. `AvailabilityChangeEvent.publish(ApplicationContext, state)` là API chính thức để phát event. Trong multicaster mặc định đồng bộ, implementation của `ApplicationAvailability` cập nhật theo event trước khi method trả response; nếu ứng dụng thay cơ chế event sang bất đồng bộ, cần kiểm tra lại tính tức thời khi đọc.

**Bảo mật:** hai endpoint POST thay readiness phải **chỉ tồn tại trong môi trường học thử**, không triển khai công khai không có authentication/authorization. Ai gọi được endpoint có thể ảnh hưởng routing của instance. Không dùng một HTTP GET để làm hành động thay đổi readiness vì GET nên mang ngữ nghĩa đọc.

### 5.5. application.properties và health probe

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=readiness-lab
server.address=127.0.0.1
server.port=8080
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

`management.endpoint.health.probes.enabled=true` cho phép health groups liveness/readiness cả khi không chạy trong môi trường Kubernetes. `health` được expose qua HTTP; `readiness` và `liveness` là nhóm của health endpoint. `server.address=127.0.0.1` giới hạn lắng nghe local để endpoint lab không bị mở ra mạng bên ngoài theo cấu hình mẫu. Trong container Kubernetes thật, phải đổi binding cho phù hợp giao tiếp mạng, không sao chép giới hạn loopback của lab.

## 6. Chạy thử và kiểm tra kết quả

### 6.1. Chạy ứng dụng

Trên Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd spring-boot:run
~~~

Giữ terminal chạy ứng dụng. Kết quả marker **tương đối** trong lần startup mặc định:

~~~text
LAB_RUNNER_BEGIN
LAB_RUNNER_DONE
LAB_APPLICATION_READY_EVENT currentReadiness=REFUSING_TRAFFIC
LAB_READINESS_EVENT=ACCEPTING_TRAFFIC
~~~

Các log framework, PID, timestamp và thứ tự marker của những listener khác có thể xen vào. Dòng `currentReadiness=REFUSING_TRAFFIC` thuộc startup mặc định và không có custom publisher sớm; vì vậy có thể khác nếu một thư viện hoặc code khác tự công bố availability state.

**Lý do thứ tự quan trọng:** Boot chỉ chuyển trạng thái chuẩn sang `ACCEPTING_TRAFFIC` sau khi phát `ApplicationReadyEvent`. Nếu nhìn thấy event ready mà bỏ qua marker readiness, không thể kết luận riêng về state snapshot hiện tại.

### 6.2. Thử HTTP sau khi startup hoàn tất

Trong terminal thứ hai:

~~~bash
curl -i http://127.0.0.1:8080/demo/status
curl -i http://127.0.0.1:8080/actuator/health/readiness
curl -i http://127.0.0.1:8080/actuator/health/liveness
~~~

Với ứng dụng thành công và probe mapping mặc định:

~~~json
{"readiness":"ACCEPTING_TRAFFIC","liveness":"CORRECT"}
~~~

Readiness probe trả body tương đương:

~~~json
{"status":"UP"}
~~~

Liveness probe cũng trả `{"status":"UP"}` trong lab bình thường; cả hai thường là HTTP 200. Không dùng response body exact byte-for-byte làm assertion vì Spring/Jackson có thể thêm trường nếu thay cấu hình health show-details hoặc group.

### 6.3. Chủ động chuyển sang REFUSING_TRAFFIC

Gọi API thử nghiệm:

~~~bash
curl -i -X POST http://127.0.0.1:8080/demo/refuse
curl -i http://127.0.0.1:8080/demo/status
curl -i http://127.0.0.1:8080/actuator/health/readiness
curl -i http://127.0.0.1:8080/actuator/health/liveness
~~~

Kỳ vọng:

- Console có marker `LAB_READINESS_EVENT=REFUSING_TRAFFIC`.
- `GET /demo/status` trả readiness `REFUSING_TRAFFIC` nhưng liveness vẫn `CORRECT`.
- `GET /actuator/health/readiness` báo `{"status":"OUT_OF_SERVICE"}` và HTTP **503** với mapping mặc định.
- `GET /actuator/health/liveness` vẫn trả HTTP **200** với `{"status":"UP"}`.
- HTTP endpoint `/demo/status` vẫn có thể trả **200** khi readiness đang `REFUSING_TRAFFIC`, vì state không tự cài middleware chặn tất cả request. Đây chính là lý do hạ tầng cần đọc readiness probe để tránh routing.

Nếu endpoint bị quản lý bởi security config hoặc health group tùy chỉnh, status code và khả năng truy cập có thể khác. Trong project mẫu không thêm Spring Security, đường local đơn giản như trên.

### 6.4. Chuyển lại ACCEPTING_TRAFFIC

~~~bash
curl -i -X POST http://127.0.0.1:8080/demo/accept
curl -i http://127.0.0.1:8080/actuator/health/readiness
~~~

Console in `LAB_READINESS_EVENT=ACCEPTING_TRAFFIC`; readiness probe trở lại HTTP 200 với `UP`. Đây là **sự kiện readiness phát sau startup bởi code của người dùng**, không phải một lần `ApplicationReadyEvent` mới. Boot không cần refresh context lại để thay đổi readiness.

## 7. Quan sát khoảng thời gian runner chưa hoàn tất

Để phân biệt rõ started với ready, build JAR:

~~~bash
./mvnw clean package
java -jar target/readiness-lab-0.0.1-SNAPSHOT.jar --lab.runner.delay-ms=12000
~~~

Tên JAR là ví dụ nếu project được tạo với version `0.0.1-SNAPSHOT`; dùng tên thật trong thư mục `target` nếu version khác. Trên Windows dùng `./mvnw.cmd clean package`. Dừng ứng dụng cũ trước khi chạy để không xung đột port.

Khi thấy `LAB_RUNNER_BEGIN` nhưng chưa thấy `LAB_RUNNER_DONE`, gọi trong terminal khác:

~~~bash
curl -i http://127.0.0.1:8080/actuator/health/readiness
curl -i http://127.0.0.1:8080/actuator/health/liveness
~~~

Trong khoảng web server đã thực sự lắng nghe nhưng runner còn chạy, readiness có thể là **`REFUSING_TRAFFIC`** với `OUT_OF_SERVICE`/503, liveness có thể là **`CORRECT`**/200. Nhưng nếu request gửi quá sớm, bạn có thể nhận “connection refused”; đó là khác biệt giữa **cổng chưa mở** và **readiness chưa đạt**, không phải lỗi của event.

Sau runner hoàn tất, chờ `LAB_APPLICATION_READY_EVENT` rồi `LAB_READINESS_EVENT=ACCEPTING_TRAFFIC` và thử lại readiness probe để thấy 200. Không dựa trên một `sleep 1` cứng để xác nhận event; luôn nhìn marker và probe thực tế.

### 7.1. Nếu runner thất bại thì sao?

Trong một bản lab thử riêng, thay thân runner bằng logic ném exception:

~~~java
@Bean
ApplicationRunner startupRunner() {
    return args -> {
        System.out.println("LAB_RUNNER_FAIL");
        throw new IllegalStateException("LAB_INTENTIONAL_FAILURE");
    };
}
~~~

**Đây là snippet thay phương thức trong main class**, không phải file Java độc lập. Khi runner ném lỗi, `ApplicationReadyEvent` và readiness `ACCEPTING_TRAFFIC` mặc định của lần chạy đó thường **không** xảy ra. Boot báo startup failure; phân tích `Caused by` của stack trace, không kết luận app đã ready chỉ vì context refresh hay server log có dòng “started”.

## 8. Readiness không phải phép kiểm sức khỏe của mọi dependency

Một số hiểu sai cần tránh:

1. `ACCEPTING_TRAFFIC` không chứng minh database, Redis, broker hoặc upstream API đang phản hồi tốt. Trạng thái phản ánh lifecycle/decision của ứng dụng theo cơ chế publish event.
2. Theo mặc định, Spring Boot **không tự đưa mọi health indicator bên ngoài** vào readiness probe; người thiết kế phải chọn dependency nào thực sự cần để phục vụ request.
3. Một cache tạm lỗi có fallback tốt có thể **không** nên đưa vào readiness, vì rút toàn bộ replica khỏi routing có thể gây outage lớn hơn.
4. Một dependency chung như database có thể làm mọi replica đồng thời unready; cần cân nhắc circuit breaker, fallback và chính sách readiness thay vì rút toàn bộ instance một cách mù quáng.
5. Không nên đưa dependency ngoài vào **liveness**, vì outage bên ngoài không tự biến JVM thành không thể phục hồi; restart hàng loạt thường gây cascades.

Nếu muốn readiness dựa trên tình trạng nghiệp vụ, có thể bổ sung `HealthIndicator` vào readiness health group hoặc publish availability state theo một state machine có chủ sở hữu rõ ràng. Tránh hai thành phần độc lập thay đổi readiness liên tục và ghi đè nhau mà không có chính sách ưu tiên.

Ví dụ cấu hình **minh họa** khi đã tự đăng ký `HealthIndicator` có ID `customCheck`:

~~~properties
management.endpoint.health.group.readiness.include=readinessState,customCheck
~~~

Chỉ sử dụng khi thật sự đã có `customCheck`; cấu hình không phải phần bắt buộc của lab này. Tham số này thay kết quả tổng hợp health group, không làm các bean khác tự động phát `AvailabilityChangeEvent`.

## 9. Kubernetes readinessProbe, livenessProbe và startupProbe

Trong Kubernetes, kubelet thăm dò Pod bằng `readinessProbe` và `livenessProbe`. Ví dụ YAML **đoạn container config**, không phải file manifest Deployment đầy đủ:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 24
~~~

Giá trị timeout/threshold chỉ để minh họa, cần đo thời gian thực tế. `startupProbe` tạo khoảng bảo vệ cho container khởi động chậm: khi startup probe chưa thành công, Kubernetes chưa bắt đầu đánh giá liveness/readiness theo cách thông thường; tránh restart sớm lúc app cần nhiều thời gian. Khi readiness thất bại, Kubernetes loại Pod khỏi các endpoint được phục vụ trong điều kiện routing thích hợp; bản thân JVM không bị giết chỉ vì readiness false.

**Quan trọng:** file `application.properties` của lab có `server.address=127.0.0.1` để tránh mở API demo ra mạng. Trong Kubernetes thực, container phải lắng nghe trên interface mà kubelet có thể kết nối (thường bỏ `server.address` hoặc đặt `0.0.0.0` theo kiến trúc mạng). Không dùng nguyên bộ lab endpoint POST có quyền thay readiness ở môi trường production.

Nếu dùng management server port riêng, readiness probe chỉ kiểm tra management context có thể bỏ sót lỗi ở port chính; Spring Boot hỗ trợ đường dẫn thêm `/readyz` và `/livez` trên **main server port** bằng:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

Khi bật, điều chỉnh probe paths cho đúng mục tiêu. Không suy đoán port/đường dẫn hoạt động trước khi kiểm bằng curl trong container thực.

## 10. Shutdown: trở lại REFUSING_TRAFFIC

Spring Boot cũng thay đổi availability khi ứng dụng dừng. Với graceful shutdown, mục tiêu là thông báo **không nhận traffic mới** rồi cho request đang xử lý thời gian hoàn tất, sau đó đóng server/context. Trong những thời điểm đó:

- `ReadinessState.REFUSING_TRAFFIC` giúp orchestrator ngừng điều hướng request đến instance.
- Các HTTP probe có thể không truy cập được khi connector đang shutdown; không nhất thiết sẽ luôn trả 503 để bạn thấy.
- `server.shutdown=graceful` điều khiển chính sách shutdown của web server, còn readiness event thể hiện khả năng nhận traffic.
- `spring.lifecycle.timeout-per-shutdown-phase` ảnh hưởng timeout của lifecycle shutdown phase; nó không thay thế termination grace period của Kubernetes.
- JVM bị dừng cưỡng bức (ví dụ `SIGKILL`) không bảo đảm callback hoặc availability event được công bố.

Không dùng `Runtime.getRuntime().halt(...)` hoặc `kill -9` để “thử graceful shutdown”; các cách đó bỏ qua cơ chế cleanup bình thường. Khi dùng Kubernetes, cân nhắc thời gian `terminationGracePeriodSeconds` và độ trễ lan truyền endpoints để tránh request mới đến Pod ngay sau khi signal shutdown được phát.

## 11. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân cần xem | Bước kiểm chứng |
|---|---|---|
| Có `ApplicationReadyEvent` nhưng listener thấy readiness cũ | Event accepting được Boot phát **sau** ready | In marker `AvailabilityChangeEvent<ReadinessState>` riêng |
| `GET /actuator/health/readiness` trả 404 | Chưa thêm Actuator, probes chưa bật, path/base-path đổi, security | Kiểm tra dependency, `management.endpoint.health.probes.enabled`, exposure, route |
| Probe trả 503 nhưng controller vẫn trả 200 | Readiness không tự chặn mọi request | Đọc `/demo/status` và health readiness; cấu hình router |
| Liveness 200, readiness 503 | Process còn sống nhưng từ chối traffic | Phân tích runner, dependency, event gần nhất |
| Readiness vẫn REFUSING sau startup | Runner chưa xong, custom publisher set refuse, startup fail hoặc đang shutdown | Xem marker ready/change, stack trace, poll state |
| Readiness chuyển ACCEPTING trước ready trong log | Code/thư viện khác đã tự publish state hoặc log bất đồng bộ | Xem publisher, listener ordering và phiên bản |
| Probe trước ready bị “connection refused” | Web server chưa lắng nghe | Phân biệt connectivity với HTTP status |
| K8s không đưa Pod vào endpoints dù JVM accepting | Chu kỳ kubelet, network path, readinessProbe không đúng, security | Kiểm tra `kubectl describe pod`, events, probe URL từ Pod |
| K8s restart khi DB chung lỗi | Đã nhầm external health vào liveness | Giới hạn liveness theo internal recoverability |
| Probe xanh nhưng API nghiệp vụ lỗi | Health group không bao trùm yêu cầu nghiệp vụ | Thử end-to-end request, thêm health indicator có chủ đích |
| Custom publisher bị trạng thái khác ghi đè | Nhiều thành phần cùng publish event | Xác định owner của readiness state machine, log source |
| Test dùng web port riêng với management port riêng | Probe không kiểm tra listener port chính | Xem `/readyz` và `/livez` trên main port |
| POST demo không đổi trạng thái như dự kiến | Event bus async hoặc process khác đang phục vụ cổng | Đọc PID, marker, getState sau khi event được xử lý |

Trong logs, ưu tiên dùng thông tin có thể đối chiếu: tên event, state, PID, thời điểm, cổng, probe HTTP status. Không kết luận chỉ từ chữ “Started” trong log, vì Boot có thể còn runner, readiness event hoặc điều kiện mạng chưa được xác nhận.

## 12. Bảng thực nghiệm và checklist

### Bảng thực nghiệm gợi ý

| Bước | Lệnh/trigger | Marker mong đợi | Probe/response | Kết luận hợp lệ |
|---|---|---|---|---|
| Startup bình thường | `./mvnw spring-boot:run` | Ready event rồi readiness accepting | readiness UP/200 | State thay đổi sau mốc ready |
| Runner chậm | `--lab.runner.delay-ms=12000` | Runner begin, chưa done | readiness refused/503 nếu server đã mở | Started chưa đồng nghĩa ready |
| Chủ động refuse | `POST /demo/refuse` | readiness refusing | readiness OUT_OF_SERVICE/503 | Có thể thay readiness sau startup |
| Giữ liveness | Sau refuse | Liveness không bị đổi chỉ bởi readiness | liveness UP/200 | Hai trạng thái độc lập |
| Chủ động accept | `POST /demo/accept` | readiness accepting | readiness UP/200 | Không cần refresh context |
| Runner lỗi | Nhánh ném exception trong bản lab thử | Không có ready/accept bình thường | Probe có thể unavailable | Startup failure khác readiness false |
| Graceful stop | Ctrl+C/SIGTERM hợp lệ | Shutdown logs/event tùy lúc | Probe chuyển fail/unavailable | Hạ tầng ngừng routing khi dừng |

### Checklist nghiệm thu

- [ ] Phân biệt `ApplicationReadyEvent` và `AvailabilityChangeEvent` là hai event khác nhau.
- [ ] Trình bày đúng thứ tự `ApplicationStartedEvent` → runners → `ApplicationReadyEvent` → `ReadinessState.ACCEPTING_TRAFFIC`.
- [ ] Nêu ý nghĩa `REFUSING_TRAFFIC` và `ACCEPTING_TRAFFIC`.
- [ ] Dựng được project Java 17 và Spring Boot 3.5.x với Spring Web + Actuator.
- [ ] Thấy log `LAB_APPLICATION_READY_EVENT` trước `LAB_READINESS_EVENT=ACCEPTING_TRAFFIC`.
- [ ] Dùng `ApplicationAvailability` đọc readiness/liveness và nhận availability event bằng listener.
- [ ] Gọi `/actuator/health/readiness`, đối chiếu HTTP 200 và 503 khi thay trạng thái.
- [ ] Chứng minh `REFUSING_TRAFFIC` không đồng nghĩa JVM chết hoặc HTTP controller tự chặn.
- [ ] Thử runner chậm và phân biệt port chưa mở với readiness 503.
- [ ] Hiểu chính sách route của Kubernetes, startup/liveness/readiness probes và main port.
- [ ] Giải thích trường hợp runner fail không có ready event.
- [ ] Không đưa endpoint thay đổi readiness không bảo vệ vào production.

## 13. Tài liệu chính thức

- Spring Boot 3.5 — Application Events and Listeners: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 — Actuator endpoints, Kubernetes probes và Application Lifecycle: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Spring Boot 3.5 — API `AvailabilityChangeEvent`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html
- Spring Boot 3.5 — API `ApplicationAvailability`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailability.html
- Spring Boot 3.5 — API `ReadinessState`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ReadinessState.html

**Kết luận:** Để khẳng định app đã đi hết mốc readiness tiêu chuẩn, cần quan sát cả `ApplicationReadyEvent` **và** sự kiện `AvailabilityChangeEvent<ReadinessState.ACCEPTING_TRAFFIC>` sau đó. Muốn khẳng định hệ thống đang nhận traffic đúng cách, còn phải kiểm probe thực tế, policy routing của hạ tầng và request nghiệp vụ.