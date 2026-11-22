# ApplicationRunner, CommandLineRunner và ảnh hưởng tới thời gian sẵn sàng

Trong ứng dụng Spring Boot, việc web server đã khởi động **không đồng nghĩa** ứng dụng đã sẵn sàng nhận lưu lượng nghiệp vụ. Sau khi Spring tạo và refresh `ApplicationContext`, các bean `ApplicationRunner` và `CommandLineRunner` vẫn có thể thực hiện công việc trước khi Spring Boot công bố trạng thái `ReadinessState.ACCEPTING_TRAFFIC`. Vì thế, một tác vụ chạy trong runner có thể kéo dài thời gian từ khi process được khởi động đến lúc instance đủ điều kiện nhận request từ load balancer hoặc Kubernetes.

Bài này tập trung vào **vị trí của runners trong quá trình khởi động máy chủ**, cách dùng đúng hai giao diện, ảnh hưởng đến readiness, xử lý lỗi, đo lường và tổ chức các tác vụ khởi tạo an toàn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Viết và chạy `ApplicationRunner` hoặc `CommandLineRunner` trong Spring Boot.
- Phân biệt `String... args` với `ApplicationArguments`, hiểu cách sắp thứ tự bằng `@Order`.
- Xác định thứ tự `ApplicationStartedEvent` → runners → `ApplicationReadyEvent` → `ReadinessState.ACCEPTING_TRAFFIC`.
- Giải thích vì sao log “Started ...” hoặc cổng HTTP đã mở chưa đủ để chứng minh ứng dụng **ready**.
- Đánh giá tác vụ nào nên chặn readiness, tác vụ nào nên chạy nền, và cách xử lý timeout, lỗi, retry.
- Quan sát tác động bằng Actuator readiness probe và hai metric `application.started.time`, `application.ready.time`.
- Tránh chạy các công việc chỉ được thực hiện một lần cho toàn cụm trên **mọi replica**.

## 2. Runner là gì và khác nhau ở đâu?

Spring Boot cung cấp hai functional interface để thực thi logic sau khi application context đã được khởi tạo:

```java
@FunctionalInterface
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}

@FunctionalInterface
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
```

Đây là **chữ ký giao diện được rút gọn để học**; khi viết ứng dụng, import hai interface có sẵn từ `org.springframework.boot`, không tự định nghĩa lại.

| Tiêu chí | `CommandLineRunner` | `ApplicationRunner` |
| --- | --- | --- |
| Đối số nhận vào | `String... args`, dữ liệu gốc | `ApplicationArguments`, đã được Spring Boot phân tích |
| Đọc tham số `--mode=demo` | Tự phân tích mảng chuỗi | `getOptionValues("mode")` |
| Đọc cờ `--dry-run` | Tự kiểm tra trong mảng | `containsOption("dry-run")` |
| Đọc đối số không có `--` | Tự lọc | `getNonOptionArgs()` |
| Thời điểm chạy | Sau `ApplicationStartedEvent`, trước `ApplicationReadyEvent` | Giống `CommandLineRunner` |
| Tác động readiness | Nếu `run` chưa kết thúc, Boot chưa chuyển sang ready | Tương tự |
| Trình tự giữa các bean | Có thể đặt `@Order` hoặc `Ordered` | Có thể đặt `@Order` hoặc `Ordered` |

Ví dụ khi chương trình khởi chạy với:

```bash
java -jar app.jar --mode=demo input.csv
```

- `CommandLineRunner` nhận mảng `["--mode=demo", "input.csv"]`.
- `ApplicationRunner` có `getOptionValues("mode")` trả về danh sách `["demo"]` và `getNonOptionArgs()` trả về `["input.csv"]`.
- `containsOption("mode")` trả về `true`. Cần kiểm tra `null`/danh sách rỗng khi gọi `getOptionValues` nếu tham số có thể không được cung cấp hoặc không có giá trị.

**Lựa chọn thực tế:** ưu tiên `ApplicationRunner` khi tác vụ cần tham số CLI có tên; dùng `CommandLineRunner` khi cần chuỗi đối số thô hoặc thư viện đã cung cấp bộ phân tích riêng. Hai interface không tạo ra hai mức readiness khác nhau.

Một ứng dụng có thể có nhiều bean runner. Các bean được chạy theo thứ tự có thể điều khiển bằng `@Order` hoặc `Ordered`. Không nên dựa vào thứ tự tình cờ của tên class, thứ tự khai báo bean, hoặc giả định rằng *mọi* `ApplicationRunner` luôn chạy trước *mọi* `CommandLineRunner`.

## 3. Runner nằm ở đâu trong vòng đời Spring Boot?

### 3.1. Trình tự khởi động tiêu biểu

Trong Spring Boot 3.x, luồng chính của một lần gọi `SpringApplication.run(...)` có các mốc quan trọng sau:

```text
main()
  |
  +-- Chuẩn bị Environment và ApplicationContext
  |
  +-- Khởi tạo bean, dependency injection, refresh context
  |       |
  |       +-- Embedded web server được khởi tạo / bắt đầu lắng nghe
  |       +-- ContextRefreshedEvent và WebServerInitializedEvent
  |
  +-- ApplicationStartedEvent
  |
  +-- LivenessState.CORRECT
  |
  +-- Gọi các ApplicationRunner / CommandLineRunner theo thứ tự
  |       |
  |       +-- run() thứ nhất: đồng bộ, chờ xong
  |       +-- run() thứ hai: đồng bộ, chờ xong
  |       +-- ...
  |
  +-- ApplicationReadyEvent
  |
  +-- ReadinessState.ACCEPTING_TRAFFIC
  |
  +-- SpringApplication.run(...) trả về
```

Đây là sơ đồ các mốc chính, không phải danh sách đầy đủ tất cả callback nội bộ của Spring.

**Điểm mấu chốt:** `ApplicationStartedEvent` có trước các runners, trong khi `ApplicationReadyEvent` có sau khi các runners hoàn tất. Sự kiện đổi readiness sang `ACCEPTING_TRAFFIC` được phát **sau** `ApplicationReadyEvent`. Các event listener mặc định chạy đồng bộ trên thread phát sự kiện, nên một listener chậm cũng có thể tác động đến quá trình khởi động.

### 3.2. “Started”, “live”, “ready”, “cổng mở” là bốn khái niệm khác nhau

| Mốc / tín hiệu | Ý nghĩa đúng | Có đủ để nhận lưu lượng không? |
| --- | --- | --- |
| Log `Started DemoApplication in ...` | Context đã khởi động; log khởi động có thể xuất hiện trước khi runners xong | **Chưa đủ** |
| Web server đã bind cổng `8080` | Socket/HTTP server hiện diện | **Chưa đủ** |
| `LivenessState.CORRECT` | Trạng thái nội bộ cho thấy process có thể hoạt động | **Chưa đủ** |
| `ReadinessState.REFUSING_TRAFFIC` | Instance chưa sẵn sàng nhận lưu lượng | **Không**; hạ tầng nên ngừng route đến instance |
| `ApplicationReadyEvent` | Các runners đã được gọi xong, Boot đang ở giai đoạn hoàn tất startup | Gần ready nhưng chưa phải sự kiện chuyển readiness |
| `ReadinessState.ACCEPTING_TRAFFIC` | Spring Boot công bố trạng thái sẵn sàng | **Có theo hợp đồng readiness**, với điều kiện hạ tầng thật sự dùng tín hiệu này |

Phải phân biệt **trạng thái readiness trong Spring** và **việc chặn HTTP thực tế**. Boot công bố trạng thái; Kubernetes, ingress, service mesh hoặc load balancer phải được cấu hình kiểm tra readiness thì mới ngừng chuyển request tới instance chưa sẵn sàng. Nếu người dùng gọi thẳng địa chỉ và cổng đã lắng nghe, không nên mặc định Spring tự từ chối mọi endpoint nghiệp vụ chỉ vì readiness đang `REFUSING_TRAFFIC`.

### 3.3. Thời gian runners tác động như thế nào?

Giả sử (thời gian minh họa):

- Từ start process đến context-started: 2,0 giây.
- `ApplicationRunner` nạp cache bắt buộc: 4,0 giây.
- `CommandLineRunner` kiểm tra cấu hình: 0,5 giây.
- Hoàn tất các sự kiện cuối: 0,1 giây.

Khi đó, thời gian tới `started` khoảng **2,0 giây**, nhưng thời gian tới `ready` khoảng **6,6 giây**. Nếu mở rộng service từ 3 lên 20 pod, mỗi pod đều chạy các runner của chính mình. Một runner chậm có thể làm rollout/scale-out chậm hoặc khiến probe thất bại trước khi ứng dụng hoàn thành khởi tạo.

Cần đo độc lập thời gian khởi động context, thời gian từng runner và thời gian đến readiness. Ví dụ con số chỉ cho thấy cách suy luận, không đại diện hiệu năng mặc định của Spring Boot.

## 4. Ví dụ Java 17+: quan sát chính xác thứ tự runners và readiness

Ví dụ dưới đây là một ứng dụng **Spring Boot 3.x** dùng Spring MVC, Actuator và Java 17+. Tạo dự án bằng Spring Initializr với dependencies **Spring Web** và **Spring Boot Actuator**, sau đó đặt nguyên file sau tại:

`src/main/java/demo/RunnerReadinessDemo.java`

```java
package demo;

import java.util.Arrays;
import java.util.List;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class RunnerReadinessDemo {

    public static void main(String[] args) {
        SpringApplication.run(RunnerReadinessDemo.class, args);
        System.out.println("5 SpringApplication.run returned");
    }
}

@Component
@Order(1)
class PrepareRunner implements ApplicationRunner {

    private final ApplicationAvailability availability;

    PrepareRunner(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        List<String> values = args.getOptionValues("mode");
        String mode = (values == null || values.isEmpty())
                ? "default" : values.get(0);

        System.out.println("1 ApplicationRunner: mode=" + mode
                + ", files=" + args.getNonOptionArgs()
                + ", readiness=" + availability.getReadinessState());

        if (args.containsOption("fail")) {
            throw new IllegalStateException("Required preparation failed");
        }

        // Chỉ để quan sát readiness; không dùng sleep khi triển khai thật.
        TimeUnit.SECONDS.sleep(6);
    }
}

@Component
@Order(2)
class PrintArgsRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("2 CommandLineRunner: raw="
                + Arrays.toString(args));
    }
}

@Component
class StartupEvents {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("3 ApplicationReadyEvent");
    }

    @EventListener
    public void onReadinessChange(
            AvailabilityChangeEvent<ReadinessState> event) {
        if (event.getState() == ReadinessState.ACCEPTING_TRAFFIC) {
            System.out.println("4 readiness=ACCEPTING_TRAFFIC");
        }
    }
}
```

Đây là **một file Java hoàn chỉnh**: chỉ `RunnerReadinessDemo` là public; các class còn lại cùng package `demo` và được component scan phát hiện. `@Order(1)` và `@Order(2)` bảo đảm thứ tự hai runner. Việc phát sự kiện và log ở ví dụ dựa trên cấu hình mặc định với application event multicaster đồng bộ.

Cấu hình `src/main/resources/application.properties`:

```properties
server.port=8080

# Cho phép dùng readiness/liveness probe ngay cả ngoài Kubernetes
management.endpoint.health.probes.enabled=true

# Tạo /readyz và /livez trên cổng web chính
management.endpoint.health.probes.add-additional-paths=true

# Chỉ để quan sát metric trong môi trường học tập
management.endpoints.web.exposure.include=health,info,metrics
```

Nếu dự án dùng Gradle Wrapper, chạy tại thư mục gốc dự án:

```bash
./gradlew bootRun --args='--mode=demo input.csv'
```

Trên Windows PowerShell, dùng:

```powershell
.\gradlew.bat bootRun --args='--mode=demo input.csv'
```

Bỏ qua banner và các dòng log tự động của Spring, **các dòng do code ví dụ in ra** sẽ theo thứ tự:

```text
1 ApplicationRunner: mode=demo, files=[input.csv], readiness=REFUSING_TRAFFIC
2 CommandLineRunner: raw=[--mode=demo, input.csv]
3 ApplicationReadyEvent
4 readiness=ACCEPTING_TRAFFIC
5 SpringApplication.run returned
```

Lưu ý: log Tomcat và Spring có thể xen giữa các dòng. `TimeUnit.SECONDS.sleep(6)` chỉ là khoảng chờ có chủ đích để thử readiness, không phải giải pháp khởi tạo thực tế. Dùng Ctrl+C để dừng chương trình.

### 4.1. Quan sát readiness trong khi runner đang chạy

Mở terminal thứ hai ngay khi Spring đã chạy web server nhưng runner số 1 vẫn đang chờ:

```bash
curl -i http://localhost:8080/readyz
```

Khi endpoint đã có thể truy cập nhưng runner chưa hoàn thành, kết quả thường có mã HTTP **503 Service Unavailable**, với health status:

```json
{"status":"OUT_OF_SERVICE"}
```

Sau khi cả hai runner kết thúc và Boot chuyển sang `ACCEPTING_TRAFFIC`, gọi lại sẽ thấy HTTP **200 OK**, body thường là:

```json
{"status":"UP"}
```

Ví dụ dùng HTTP response mặc định của Actuator health group và chưa tùy biến mapper/status detail. Nếu gọi quá sớm, có thể gặp lỗi không kết nối vì cổng chưa mở; nếu gọi quá muộn, chỉ thấy `UP` vì runner đã xong. Hai trường hợp này không làm thay đổi thứ tự lifecycle.

### 4.2. Thử runner thất bại

Chạy một lần mới với cờ `--fail`:

```bash
./gradlew bootRun --args='--mode=demo --fail'
```

`PrepareRunner` ném `IllegalStateException("Required preparation failed")`. Quá trình startup thông thường sẽ báo lỗi và không hoàn tất readiness. Những dòng `2 CommandLineRunner`, `3 ApplicationReadyEvent`, `4 readiness=ACCEPTING_TRAFFIC`, `5 SpringApplication.run returned` **không xuất hiện** trong lần chạy lỗi này vì exception xảy ra ngay tại runner đầu. Spring Boot phát sự kiện thất bại (`ApplicationFailedEvent`) và đóng context khi startup không hoàn tất.

Đừng dùng cờ giả lập lỗi trong production; ví dụ nhằm chứng minh rằng **runner lỗi không được coi là startup thành công**.

### 4.3. Khi không cần nhận tham số CLI

Với tác vụ cố định, bạn có thể viết runner dưới dạng bean ngắn:

```java
@Bean
ApplicationRunner auditOnBoot() {
    return args -> auditService.verifyConfiguration();
}
```

Đây là **snippet** nằm trong một class `@Configuration` hoặc `@SpringBootApplication`; nó giả sử đã có bean `auditService`, không phải chương trình độc lập. Nếu tác vụ này cần transaction, timeout hoặc retries có cấu hình, nên đặt logic trong một service riêng và runner chỉ gọi service đó.

## 5. Có nên dùng runner để khởi tạo dữ liệu hay kiểm tra phụ thuộc?

Câu trả lời phụ thuộc vào một điều kiện: **Không hoàn thành tác vụ này thì instance có phục vụ request đúng và an toàn hay không?**

| Công việc | Cách làm phù hợp | Ảnh hưởng readiness cần chấp nhận |
| --- | --- | --- |
| Kiểm tra biến cấu hình bắt buộc, xác thực chứng chỉ/config cục bộ | Runner hoặc validation trong startup | Nếu lỗi thì dừng startup; nên rất nhanh |
| Nạp bộ dữ liệu cục bộ nhỏ mà mọi request bắt buộc dùng | `ApplicationRunner` đồng bộ, có deadline | Chưa nạp xong thì chưa ready |
| Kiểm tra khả năng truy cập dependency thiết yếu | Preflight ngắn có timeout; kết hợp health/readiness runtime | Có thể chặn ready; tránh retry vô hạn |
| Warm cache tùy chọn để tăng tốc request đầu tiên | Chạy nền có executor giới hạn hoặc lazy-load | Không cần kéo dài ready nếu ứng dụng phục vụ được khi cache lạnh |
| Seed dữ liệu mẫu trong môi trường local/dev | Runner có profile/flag cụ thể, idempotent | Không để chạy mặc định trong production |
| Migration schema DB | Ưu tiên Flyway/Liquibase hoặc migration Job quản lý riêng | Duy trì thứ tự trước khi dữ liệu bị truy cập; không tùy tiện viết lại trong runner |
| Công việc chỉ chạy một lần **toàn cluster** | Kubernetes Job, scheduler có lock/leader election | Không dùng runner trên mọi pod nếu tác vụ không an toàn khi lặp |
| Gửi email hàng loạt, đồng bộ toàn bộ hệ thống, tải dữ liệu nhiều phút | Batch/queue/background worker riêng | Không giữ readiness của web service hàng phút chỉ để hoàn tất công việc phụ |
| Tác vụ định kỳ | `@Scheduled`/job scheduler có cơ chế điều phối | Runner chỉ dùng khởi tạo schedule nếu thật cần |

**Điểm chọn lựa:** một bước bắt buộc để đảm bảo đúng dữ liệu nên kết thúc **trước** readiness; một bước tối ưu hóa hoặc việc nền có thể tách ra, miễn là request vẫn hoạt động đúng khi nó chưa hoàn thành. Không nên đánh dấu `ACCEPTING_TRAFFIC` khi tài nguyên tối quan trọng chưa được chuẩn bị.

## 6. Runner đồng bộ, chạy nền và hiểu nhầm phổ biến

### 6.1. Runner đồng bộ chặn tiến trình hoàn tất startup

Mặc định Spring Boot gọi các phương thức `run(...)` theo thứ tự và chờ chúng trả về. Nếu runner đầu mất 30 giây, runner sau không bắt đầu trong lúc đó và `ApplicationReadyEvent` chưa được phát. Nếu việc chờ thực chất là I/O đến database hoặc HTTP server, thời gian khởi động sẽ phụ thuộc vào latency và tình trạng của hệ thống bên ngoài.

Sai lầm:

```java
@Override
public void run(ApplicationArguments args) throws Exception {
    while (!externalSystemAvailable()) {
        Thread.sleep(1000); // Không giới hạn thời gian và số lần thử
    }
}
```

Đây là **snippet phản ví dụ**, với `externalSystemAvailable()` là hàm minh họa. Nếu dependency không bao giờ hồi phục, pod có thể luôn ở trạng thái chưa ready; hệ thống triển khai có thể restart liên tục theo deadline của startup/liveness probe.

Cách thiết kế đúng hơn: có **deadline tổng**, timeout cho từng request, số lần retry giới hạn, backoff có jitter nếu cần, thông báo lỗi rõ ràng và chính sách fail-fast có chủ đích khi dependency bắt buộc không khả dụng.

### 6.2. Tự tạo Future hoặc @Async có thể khiến readiness chuyển quá sớm

Xem snippet:

```java
@Override
public void run(ApplicationArguments args) {
    CompletableFuture.runAsync(() -> warmRequiredCache());
}
```

Hàm `run` trả về ngay sau khi lịch làm việc nền được tạo. Spring Boot **không đợi** `CompletableFuture` hoàn thành; nó tiếp tục các runner còn lại và có thể chuyển sang ready trong khi cache bắt buộc vẫn rỗng. Cùng rủi ro xuất hiện khi dùng `@Async` mà không có cơ chế phối hợp phù hợp. Trong ví dụ, `warmRequiredCache()` là tác vụ giả định và code cần import `java.util.concurrent.CompletableFuture`.

Nếu cache là **bắt buộc** để phục vụ request đúng, hãy chờ hữu hạn trong runner và chỉ trả về khi kiểm tra hoàn tất; nếu cache **không bắt buộc**, hãy cho phép cache lạnh, giới hạn hàng đợi và không lấy readiness làm tín hiệu công việc nền đã xong.

### 6.3. Có thể trì hoãn readiness sau lúc ready event?

Boot phát `ApplicationReadyEvent` rồi mới phát sự kiện trạng thái `ReadinessState.ACCEPTING_TRAFFIC`. Nếu một listener của `ApplicationReadyEvent` tự phát `REFUSING_TRAFFIC` vào thời điểm đó, thay đổi này có thể bị sự kiện `ACCEPTING_TRAFFIC` của Boot phát sau đó ghi đè. Đừng xây logic trì hoãn readiness bằng cách “đánh dấu REFUSING đúng một lần ở listener Ready”.

Nếu phải có pha chuẩn bị **bắt buộc**, giải pháp đơn giản và ít sai nhất là hoàn tất pha đó đồng bộ trong runner trước `ApplicationReadyEvent`. Nếu có quy trình warm-up dài bắt buộc chạy nền, hãy thiết kế một cơ chế readiness riêng (chẳng hạn custom `HealthIndicator` trong readiness group phản ánh điều kiện nghiệp vụ thực) và kiểm thử toàn bộ chuyển trạng thái khi thành công, thất bại và khi ứng dụng shutdown.

### 6.4. Vì sao không để mọi việc trong @PostConstruct?

`@PostConstruct` chạy trong quá trình bean được khởi tạo, khi các bean/khả năng kết nối khác hoặc toàn bộ context có thể chưa ở trạng thái bạn cần. Nó cũng dễ làm ẩn thời gian khởi tạo đằng sau một constructor hoặc bean lifecycle.

Dùng `@PostConstruct` cho chuẩn bị **cục bộ, ngắn, chỉ phụ thuộc trạng thái bean**; dùng runner cho bước khởi tạo thuộc **toàn ứng dụng**, cần các Spring bean đã sẵn sàng và cần có trước khi nhận traffic. Không phải mọi tác vụ trong runner đều tốt: tác vụ càng dài hoặc nhiều side effect thì càng cần có quy trình điều phối riêng.

## 7. Thiết kế runner chịu lỗi và khởi động lại an toàn

### 7.1. Xác định bắt buộc hay tùy chọn

Đặt rõ hai nhánh:

- **Bắt buộc:** nếu thiếu dữ liệu hoặc kết nối thì request sai hoặc rò rỉ dữ liệu. Runner kiểm tra, thực hiện với timeout và **ném exception** khi không thành công để startup fail. Tín hiệu readiness không được bật sau một lỗi nghiêm trọng.
- **Tùy chọn:** ứng dụng vẫn xử lý request đúng khi chức năng phụ chưa sẵn sàng. Ghi log/metric cảnh báo, triển khai retry bên ngoài luồng startup, có fallback. Nếu bắt lỗi để bỏ qua, phải chắc chắn rằng bỏ qua là **an toàn**, không chỉ để “app lên xanh”.

Đối với một thao tác có transaction, nên gọi service `@Transactional` từ runner thay vì nhồi transaction boundary, I/O và retries trực tiếp vào `run`. Phân biệt lỗi **tạm thời** (timeout, 503) với lỗi **không thể phục hồi** (thiếu cấu hình, schema không tương thích). Đặt giới hạn retry vì mỗi replica cũng có thể đang retry cùng lúc.

### 7.2. Một lần khởi động instance không có nghĩa một lần toàn hệ thống

`ApplicationRunner` và `CommandLineRunner` được gọi trong **mỗi lần `SpringApplication` khởi động instance**. Nếu bạn chạy 10 pod, mỗi pod có runner của mình; restart, rolling update và scale-out có thể chạy lại cùng logic. Vì vậy:

- Seed/upsert dữ liệu phải idempotent: chạy lại không tạo bản ghi trùng, không gửi email lặp.
- Nếu nhiều instance cùng ghi tài nguyên chia sẻ, có khóa hoặc cơ chế điều phối rõ ràng.
- Dùng migration tool dành riêng cho việc thay đổi schema và dùng Job/leader election nếu chỉ một tác vụ được phép xử lý trên toàn cụm.
- Không giả định `@Order` giữa các runner của **những instance khác nhau** có ý nghĩa đồng bộ.

Ví dụ gây lỗi: runner đọc `COUNT(*)=0` rồi đồng loạt `INSERT` bản ghi mặc định ở nhiều replica. Cả hai thấy bảng trống và cùng ghi. Cần unique constraint + thao tác upsert/transaction đúng hoặc chuyển việc seed sang Job có điều phối.

### 7.3. Timeout, hủy và tính nhất quán

Với lời gọi HTTP/DB bên trong runner, đặt timeout tại **client/driver**, không chỉ `Thread.sleep` hoặc bộ đếm tổng. Cân nhắc cả thời gian bắt connection, đọc response và tổng deadline của nghiệp vụ. Nếu runner bị lỗi sau khi đã thực hiện một phần side effect, có thể cần compensation, transaction hoặc idempotency key để lần khởi động sau không làm hỏng dữ liệu.

Cần log tên tác vụ, thời gian bắt đầu/kết thúc, thời lượng, kết quả và mã lỗi; không ghi token, mật khẩu hoặc dữ liệu nhạy cảm vào startup log. Thông báo đủ rõ để vận hành biết **khởi động hỏng ở bước nào**.

## 8. Cấu hình readiness và liveness probe khi triển khai

Để Kubernetes phân phối lưu lượng dựa trên readiness, thêm Spring Boot Actuator và bật probes. Với các thuộc tính trong ví dụ, `/readyz` và `/livez` nằm trên **cổng HTTP chính**. Cấu hình Kubernetes mẫu:

```yaml
startupProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 5
  failureThreshold: 30

readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
  periodSeconds: 3
  failureThreshold: 2

livenessProbe:
  httpGet:
    path: /livez
    port: 8080
  periodSeconds: 10
  failureThreshold: 3
```

Đây là **đoạn cấu hình trong một Kubernetes container spec**, không phải manifest Deployment độc lập. Các giá trị chỉ là ví dụ: chọn theo phân phối thực tế của thời gian startup, thời gian probe, tài nguyên và yêu cầu triển khai.

- **Startup probe:** tạo khoảng thời gian đủ để khởi tạo; khi startup probe chưa thành công, Kubernetes chưa thực hiện liveness/readiness probe theo lịch bình thường. Chọn ngân sách timeout phù hợp phần khởi động dài nhất được chấp nhận.
- **Readiness probe:** khi báo lỗi, Kubernetes không chọn pod đó làm endpoint sẵn sàng để nhận lưu lượng qua Service. Đây là tín hiệu quan trọng nhất để runners bắt buộc được hoàn thành trước khi traffic tới.
- **Liveness probe:** cho biết process còn hoạt động hợp lệ hay cần restart; **không** thêm kiểm tra mạng ngoài/DB dễ biến lỗi phụ thuộc chung thành làn sóng restart toàn bộ pod.

Nếu bạn không bật `management.endpoint.health.probes.add-additional-paths=true`, có thể dùng `/actuator/health/readiness` và `/actuator/health/liveness` khi Actuator health probes được kích hoạt. Nếu Actuator phục vụ trên `management.server.port` riêng, ưu tiên cân nhắc probe trên cổng ứng dụng chính để kiểm tra đúng hạ tầng HTTP mà người dùng thật dùng. Hãy bảo vệ các endpoint quản trị theo chính sách mạng và bảo mật của hệ thống.

**Lưu ý quan trọng:** Spring Boot có thể đã khởi động HTTP connector trong lúc runner còn chạy. Một hệ thống không dùng readiness probe hoặc cấu hình load balancer sai vẫn có thể chuyển request đến pod quá sớm. Vì vậy, test rollout phải xác nhận **hạ tầng thực sự loại pod chưa ready** chứ không chỉ nhìn endpoint JSON.

## 9. Đo thời gian sẵn sàng và tìm runner chậm

Spring Boot Actuator/Micrometer có hai metric về startup:

- `application.started.time`: thời gian để application đạt mốc started.
- `application.ready.time`: thời gian để application đạt mốc ready.

Hai metric phản ánh các mốc khác nhau. Khi runner đồng bộ làm việc dài, thời gian ready thường tăng so với started. Tuy nhiên, **chênh lệch metric không phải profiler chính xác của riêng runners** vì còn có chi phí callback, listener và xử lý giai đoạn cuối. Nên đo từng runner bằng `System.nanoTime()` hoặc Micrometer timer để xác định nguyên nhân.

Nếu đã cấu hình expose `metrics` ở môi trường an toàn:

```bash
curl -s http://localhost:8080/actuator/metrics/application.started.time
curl -s http://localhost:8080/actuator/metrics/application.ready.time
```

Sau khi app ready, metric endpoint có thể trả số liệu thời gian tương ứng. Dữ liệu thực tế tùy exporter, cấu hình Actuator, phiên bản và meter registry; không cố đo metric này bằng một request thực hiện trong lúc app chưa ready.

### 9.1. Gắn log thời gian cho tác vụ bắt buộc

Ví dụ snippet nằm trong `run` của một runner, giả sử service `warmupService` đã được inject:

```java
long start = System.nanoTime();
try {
    warmupService.prepare(); // Có deadline/timeout ở service
} finally {
    long elapsedMs =
            TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start);
    logger.info("startup.warmup.elapsed_ms={}", elapsedMs);
}
```

Đây là **snippet**, không phải class độc lập; cần `logger` (ví dụ SLF4J), `warmupService` và import `java.util.concurrent.TimeUnit`. Khi nhiều runner tồn tại, dùng tên ổn định cho từng công việc (ví dụ `startup.cache`, `startup.config`), không dựa vào log tổng “Started” để kết luận runner nào chiếm thời gian.

### 9.2. Đo startup thật trong hệ thống triển khai

Đo ở ít nhất ba kịch bản:

1. **Cold start:** image/container/JVM chưa warm, caches trống, kết nối phụ thuộc chưa thiết lập.
2. **Rolling update:** nhiều replica mới cùng chạy runner, có thể gây spike đến DB/API.
3. **Degraded dependency:** DB chậm, DNS chậm, HTTP 503 hoặc cache unavailable.

Ghi thời gian từ container bắt đầu đến readiness success, p95/p99 qua nhiều lần khởi động, số lần pod restart, lỗi probe, số lượng connection tạo đồng thời và tác động đến request đang phục vụ. Nếu thêm một runner làm p99 ready tăng vượt ngân sách rollout, cần phân nhỏ tác vụ, giới hạn I/O, chọn phương án chạy nền phù hợp hoặc chuyển việc khỏi web service.

## 10. Kiểm thử và chẩn đoán theo tình huống

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Có log `Started` nhưng `/readyz` trả 503 | Runners hoặc đoạn chuyển trạng thái chưa hoàn tất | Đọc log tác vụ, đo từng runner, kiểm tra timeout |
| HTTP 8080 gọi được nhưng Kubernetes chưa route traffic | Pod chưa ready, probe đang phản ánh đúng vòng đời | Xác nhận readiness group và Service endpoints; đây có thể là hành vi mong muốn |
| Probe không bao giờ UP | Runner kẹt, vòng retry vô hạn, exception hoặc readiness check lỗi | Giới hạn deadline, kiểm tra log và lỗi hệ thống phụ thuộc |
| `ApplicationReadyEvent` xuất hiện nhưng tác vụ warm-up chưa xong | Runner đã tự tạo async task rồi trả về | Bắt buộc thì chờ hữu hạn; tùy chọn thì thiết kế fallback và đánh dấu rõ |
| Hai runner thực hiện ngược thứ tự mong muốn | Chưa cấu hình `@Order` / `Ordered` hoặc cùng order | Gán thứ tự tường minh; nên gom quy trình phụ thuộc nhau vào một service điều phối |
| Mỗi lần scale-out đều tạo dữ liệu trùng | Runner chạy trên mọi replica | Idempotent/upsert, unique constraint, Job có điều phối |
| Tăng startupProbe nhưng app vẫn kẹt | Vấn đề thật nằm ở task chậm/vô hạn hoặc dependency | Sửa logic, timeout và kiểm chứng; tăng ngưỡng probe chỉ khi có lý do |
| Liveness fail khi DB ngắt | Liveness chứa kiểm tra dependency ngoài | Giữ liveness cho tình trạng process, chuyển kiểm tra cần thiết vào readiness hoặc cơ chế phục hồi riêng |
| Readiness probe xanh nhưng request thực bị lỗi | Probe kiểm tra cổng quản trị riêng, thiếu dependency cần thiết hoặc còn task nền | Kiểm tra chính HTTP listener, readiness group và hành vi ứng dụng thật |

### 10.1. Các phép kiểm thử tối thiểu

- Chạy bình thường: xác nhận thứ tự các runner, ready event, readiness accepting và `SpringApplication.run` trả về.
- Thêm runner cố tình chờ hữu hạn: trước khi runner xong, readiness trả không sẵn sàng; sau đó trả UP.
- Ép runner ném exception: không có `ApplicationReadyEvent`/`ACCEPTING_TRAFFIC`, startup báo lỗi rõ.
- Khởi động hai instance độc lập: thấy logic runner chạy ở cả hai, qua đó kiểm tra tính lặp lại an toàn.
- Mô phỏng dependency chậm hoặc không đáp ứng: xác nhận deadline và thời gian startup nằm trong ngân sách đã định.
- Nếu chạy Kubernetes, thử rollout thật: pod mới không nhận request trước khi readiness thành công; pod cũ tiếp tục phục vụ trong quá trình thay thế phù hợp rollout strategy.

## 11. Những lỗi thiết kế dễ gặp

1. **Dùng runner để làm việc vài phút mà request không cần.** Hậu quả là rollout và auto-scaling chậm; chuyển sang batch/background worker.
2. **Xem `ApplicationStartedEvent` là ứng dụng ready.** Đây là mốc trước runners. Dùng `ApplicationReadyEvent` và readiness probes đúng chỗ.
3. **Gọi `CompletableFuture.runAsync(...)` cho dữ liệu bắt buộc rồi trả về.** Spring Boot không tự chờ Future; ready có thể bật quá sớm.
4. **Bắt mọi exception rồi in log WARNING.** Nếu lỗi làm request sai, instance vẫn trở thành ready một cách nguy hiểm; phải fail startup.
5. **Retry vô hạn không deadline.** Có thể khiến pod mãi chưa ready; cấu hình timeout và chiến lược retry cụ thể.
6. **Dùng runner như job chạy một lần cho cả cụm.** Nó được gọi lại trên mỗi instance; cần điều phối hoặc idempotency.
7. **Giả định mở cổng đồng nghĩa Kubernetes sẽ route request.** Hạ tầng phải dựa trên readiness, không chỉ lắng nghe port.
8. **Dựa vào thứ tự bean ngẫu nhiên.** Các runner có quan hệ phụ thuộc cần `@Order`/`Ordered` và thiết kế rõ.
9. **Nhồi schema migration hoặc transaction phức tạp vào runner.** Dùng công cụ migration và service có transaction boundary minh bạch.
10. **Dùng `ApplicationReadyEvent` listener để chạy đồng bộ tác vụ rất dài.** Listener mặc định đồng bộ và có thể tiếp tục trì hoãn quá trình hoàn tất readiness; ưu tiên runner hoặc kiến trúc nền có điều phối.
11. **Đưa dependency ngoài vào liveness probe.** Khi dependency chung hỏng, toàn cụm có thể bị restart dây chuyền.
12. **Quên đo p95/p99 startup.** Một vài lần local nhanh không phản ánh rolling deploy khi nhiều pod cùng khởi chạy.

## 12. Bài tập vận dụng

**Bài 1 — nhận diện thứ tự:** Có ba runner được gắn `@Order(10)`, `@Order(1)` và `@Order(5)`. Hỏi trình tự và khi nào phát `ApplicationReadyEvent`?  
**Đáp án:** runner thứ tự 1 → 5 → 10 (nếu không có thứ tự ưu tiên khác như `Ordered.HIGHEST_PRECEDENCE`); `ApplicationReadyEvent` chỉ đến sau khi cả ba chạy xong thành công. Loại interface `ApplicationRunner`/`CommandLineRunner` không tự quyết định thứ tự.

**Bài 2 — startup 90 giây:** Instance mất 3 giây tạo context và 87 giây để tải cache ảnh tùy chọn. Khách hàng vẫn có thể nhận ảnh qua disk cache lạnh. Có nên đặt cả việc tải cache vào runner?  
**Gợi ý:** Không cần chặn ready cho tối ưu hóa tùy chọn. Đưa cache warming ra nền, giới hạn đồng thời và bảo đảm request khi cache lạnh vẫn đúng.

**Bài 3 — nạp danh mục bắt buộc:** Request xử lý giá tiền sai nếu không có bảng tỷ giá hiện tại. Có được `run` gọi async load rồi trả về ngay?  
**Đáp án:** Không. Phải có kiểm tra hoàn tất trước readiness hoặc một readiness indicator phản ánh trạng thái thực; khi tải lỗi phải fail-fast/không nhận traffic theo thiết kế, không chỉ ghi warning.

**Bài 4 — nhiều replicas:** Deployment có 8 pod. Runner thực hiện `INSERT` dữ liệu mặc định sau khi check bảng trống. Rủi ro gì?  
**Đáp án:** Cả 8 pod có thể chạy đồng thời; check-then-insert gây race, trùng dữ liệu hoặc startup lỗi. Dùng migration/Job phối hợp và unique constraint + thao tác idempotent.

**Bài 5 — kiểm tra dấu hiệu ready:** Log đã có `Started MyApp`, `curl localhost:8080/api` trả dữ liệu, nhưng `/readyz` là 503. Có thể khẳng định đây là bug của Spring Boot?  
**Đáp án:** Không. Đây có thể là trạng thái hợp lệ khi runner chưa xong và HTTP connector đã lắng nghe; chỉ có route từ orchestrator dựa trên readiness mới tránh gửi lưu lượng sớm.

## 13. Checklist khi đưa runner vào ứng dụng web

- [ ] Đã xác định tác vụ bắt buộc trước readiness hay chỉ là tối ưu hóa.
- [ ] Đã chọn `ApplicationRunner` hoặc `CommandLineRunner` theo nhu cầu tham số, không theo kỳ vọng hiệu năng.
- [ ] Nếu có nhiều runner phụ thuộc nhau, đã gắn thứ tự rõ ràng hoặc có service điều phối.
- [ ] Mọi lời gọi mạng/DB đều có timeout; retry hữu hạn và failure policy rõ.
- [ ] Công việc chạy mỗi lần khởi động đã idempotent và an toàn khi nhiều replica chạy song song.
- [ ] Tác vụ dài, định kỳ hoặc chỉ một lần toàn cụm đã được đưa sang công cụ phù hợp.
- [ ] Readiness probe phản ánh đủ các điều kiện cần thiết; liveness không phụ thuộc hệ thống ngoài.
- [ ] Đã thử tình huống exception, delay, restart và rolling update thật.
- [ ] Đã đo `application.started.time`, `application.ready.time` và thời gian từng runner.
- [ ] Không sử dụng log “Started” hoặc việc cổng mở làm tiêu chí duy nhất để đánh dấu ready.

## Tài liệu chính thức

- [Spring Boot 3.3 — SpringApplication: Application Events, Application Availability, Runners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — Actuator Endpoints, Kubernetes liveness/readiness probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Boot 3.3 — Application Startup Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Spring Boot API — ApplicationRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/ApplicationRunner.html)
- [Spring Boot API — CommandLineRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/CommandLineRunner.html)
- [Spring Boot API — ApplicationAvailability](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/availability/ApplicationAvailability.html)

Tóm lại, runner là điểm thực thi tác vụ **sau khi context khởi động nhưng trước khi Spring Boot công bố sẵn sàng**. Hãy dùng vị trí đó để hoàn tất các điều kiện thực sự cần cho phục vụ request, giữ việc khởi động có giới hạn thời gian, và để readiness probe điều khiển việc nhận traffic.
