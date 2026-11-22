# Phân biệt dừng sớm có chủ đích với thử lại vô hạn trong lúc khởi động

## Mục tiêu học tập

Khởi động một ứng dụng Spring Boot không chỉ là mở được JVM hay bind một cổng TCP. Ứng dụng có thể phải đọc cấu hình, tạo `ApplicationContext`, khởi tạo singleton beans, mở connection, xác thực dependency, nạp dữ liệu nền và chạy các startup runners trước khi **sẵn sàng phục vụ**. Khi một điều kiện bắt buộc thất bại, ứng dụng cần một quyết định rõ ràng: **dừng sớm có chủ đích** (*fail fast*), **thử lại hữu hạn** (*bounded retry*) hoặc hoạt động ở trạng thái **giảm năng lực** (*degraded mode*) nếu hợp đồng cho phép.

Bài này thuộc **Spring Boot Application Runtime → Lỗi khởi động**, tập trung vào sự khác nhau giữa **dừng sớm đúng cách** và **retry vô hạn trong startup**. Ngữ cảnh kỹ thuật: Java 17+, Spring Boot 3.3.x và Spring Framework 6.1.x.

Sau bài học, bạn sẽ:

1. Giải thích vì sao một startup failure có **tín hiệu lỗi rõ** thường tốt hơn một tiến trình sống mãi nhưng không bao giờ ready.
2. Phân loại lỗi **vĩnh viễn** (cấu hình sai, input không hợp lệ, quyền bị từ chối) và lỗi **tạm thời** (connection refused, timeout, 503, broker chưa sẵn sàng).
3. Thiết kế retry có **max attempts, tổng deadline, per-attempt timeout, backoff, jitter**, xử lý interrupt và cleanup.
4. Hiểu các mốc `ApplicationStartedEvent`, `ApplicationRunner`, `ApplicationReadyEvent`, `ApplicationFailedEvent` và availability states.
5. Biết khi nào cần fail fast trong `@Bean`/`@PostConstruct`, khi nào dùng runner và khi nào chuyển sang runtime recovery.
6. Chạy project hoàn chỉnh **Java 17+ / Spring Boot 3.3.13 / Gradle** có ba mode: `fatal`, `recover` và `exhaust`, với output chính xác.
7. Phân biệt retry vô hạn bên trong JVM với **CrashLoopBackOff** do Kubernetes restart những JVM đã exit.
8. Kiểm soát readiness/liveness/startup probes và ngân sách shutdown ở môi trường triển khai.
9. Kiểm thử cả số lần gọi, quyết định retry, mốc ready và mã thoát process mà không dùng một vòng lặp không kết thúc.

**Nguyên tắc:** Chỉ retry khi lỗi **có khả năng tự phục hồi**; retry phải có **điều kiện dừng hữu hạn**. Một lỗi cấu hình không thể tự sửa bằng thời gian cần được báo ngay, thay vì giấu dưới vô hạn lần kết nối lại.

## 1. Bốn cách phản ứng với lỗi khởi động

| Cách xử lý | Cơ chế | Kết quả quan sát được | Khi dùng |
| --- | --- | --- | --- |
| **Fail fast** | Gặp lỗi không thể tiếp tục, ném exception và dừng startup | Failure/exit non-zero, không đạt ready | Cấu hình sai, schema không tương thích, quyền truy cập sai |
| **Bounded retry** | Thử lại có giới hạn; thành công thì tiếp tục; hết ngân sách thì fail | Luôn có kết luận success/failure hữu hạn nếu từng attempt có timeout | Dịch vụ bắt buộc đang khởi động chậm, mạng gián đoạn ngắn |
| **Infinite retry** | Cứ gọi lại mãi, thường không deadline và không phân loại lỗi | Có thể JVM sống nhưng không ready và không báo kết luận | Không khuyến nghị trong đường startup |
| **Degraded startup** | Cho hệ thống chạy khi một tính năng phụ có fallback | Core có thể ready, tính năng phụ báo unavailable | Dependency thực sự tùy chọn và fallback không vi phạm nghiệp vụ |

**Fail fast không đồng nghĩa không bao giờ retry.** Chính sách có thể kết hợp:

~~~text
Lỗi permanent                  → dừng ngay
Lỗi transient, còn ngân sách   → retry có backoff
Lỗi transient, hết ngân sách   → báo startup failure
Lỗi tính năng optional        → degrade/reconnect, nếu được phép
~~~

Mọi lựa chọn phải xuất phát từ **hợp đồng nghiệp vụ**. Một hệ thống thanh toán không thể đánh dấu “ready” khi thiếu khóa xác thực bắt buộc chỉ để có log khởi động thành công. Ngược lại, một website có thể phục vụ nội dung cốt lõi dù hệ thống gợi ý sản phẩm tạm thời offline.

### Ví dụ dễ phân loại

- `APP_SECRET` là property bắt buộc nhưng không có: **fail fast**.
- URL JDBC không thể parse: **fail fast**.
- Database từ chối do password sai đã được xác nhận: thường **fail fast**; nếu nền tảng có cơ chế cập nhật secret đang diễn ra, phải xác định chính sách chờ có hạn.
- Database đang boot và từ chối kết nối vài giây: có thể **bounded retry**.
- API trả 429/503 tạm thời: có thể retry với `Retry-After`/backoff trong ngân sách.
- Hệ thống analytics tùy chọn không thể truy cập: có thể degrade nếu không ảnh hưởng chức năng thiết yếu.
- Lỗi `NullPointerException` do bug ở logic setup: **không** retry mù quáng 100 lần.
- Schema version cũ không tương thích với binary mới: retry network không sửa được; phải sửa migration/deployment.

## 2. Startup lifecycle của Spring Boot: started khác ready

Spring Boot 3.3 có các mốc chính:

~~~text
main(String[] args)
   |
   +-- SpringApplication.run(args)
         |
         +-- Chuẩn bị Environment
         +-- Tạo ApplicationContext
         +-- refresh context
         |     +-- load bean definitions
         |     +-- tạo singleton non-lazy
         |     +-- injection, @PostConstruct, init hooks
         |     +-- SmartLifecycle auto-start theo hợp đồng
         |
         +-- ApplicationStartedEvent
         +-- LivenessState.CORRECT
         |
         +-- ApplicationRunner / CommandLineRunner
         |     +-- kiểm tra điều kiện trước khi ready
         |     +-- retry hữu hạn khi phù hợp
         |     +-- ném exception nếu không thể tiếp tục
         |
         +-- ApplicationReadyEvent
         +-- ReadinessState.ACCEPTING_TRAFFIC
         |
         +-- SpringApplication.run trả về context
~~~

Sơ đồ rút gọn các mốc nghiệp vụ quan trọng, không phải bản sao đầy đủ mọi lời gọi nội bộ của framework.

**ApplicationStartedEvent** được phát sau refresh, **trước** runners. **ApplicationReadyEvent** đến sau runners thành công. Vì vậy, một log “Started” hoặc listener `ApplicationStartedEvent` đã chạy không chứng minh startup gate đã hoàn tất.

Nếu runner ném exception không xử lý, `SpringApplication.run(...)` đi vào nhánh startup failure: Spring Boot báo lỗi, phát `ApplicationFailedEvent` khi phù hợp và cố cleanup context đã có. Đường thành công **không** đến `ApplicationReadyEvent`. Nếu lỗi xảy ra quá sớm, một listener chỉ là bean Spring có thể chưa tồn tại; không được giả định mọi listener đều nhận mọi startup failure.

### Một điều dễ bị nhầm

- **JVM sống:** process chưa thoát.
- **Context refreshed:** bean factory/context đã qua pha refresh.
- **Application started:** Spring Boot đến mốc Started.
- **Application ready:** các runners đã hoàn tất và Boot chuyển availability theo đường thành công.
- **Một endpoint đã sử dụng được:** còn phụ thuộc vào các dependency runtime, readiness policy và trạng thái của tính năng đó.

Một vòng lặp vô hạn có thể giữ một trạng thái ở giữa những mốc này mãi mãi. Sự tồn tại của process không phải một bảo đảm chất lượng dịch vụ.

## 3. Infinite retry trong startup nguy hiểm thế nào?

Ví dụ một runner viết sai:

~~~java
@Override
public void run(ApplicationArguments args) {
    while (true) {
        try {
            checkMandatoryDatabase();
            return;
        }
        catch (Exception ignored) {
            // Lặp lại ngay lập tức, không log và không có deadline.
        }
    }
}
~~~

**Đây là anti-pattern, không phải chương trình chạy được**: `checkMandatoryDatabase()` chưa định nghĩa. Không dùng nó trong sản phẩm hoặc chạy test thiếu timeout.

Những rủi ro:

1. **Never-ready:** runner không bao giờ return, nên ứng dụng không đạt ready theo đường bình thường.
2. **Che lỗi permanent:** sai mật khẩu hoặc config cũng bị lặp y hệt timeout thoáng qua.
3. **CPU/network storm:** retry tức thời có thể chiếm CPU và gây tải lớn lên database/API.
4. **Không có trạng thái kết luận:** scheduler/CI không nhận được process exit code phản ánh lỗi.
5. **Shutdown khó khăn:** một blocking call không timeout hoặc một loop bỏ qua interrupt có thể giữ thread khi process cần thoát.
6. **Thất bại âm thầm:** logs có thể chỉ dừng ở một mốc “Starting ...”, khó phân biệt treo với tiến trình đang chuẩn bị.
7. **Thêm instance làm tình hình tệ hơn:** mọi replica cùng retry có thể ngăn dependency hồi phục.
8. **Kéo dài rollout:** deployment controller đợi pod ready cho tới deadline của nó, chứ không nhận failure nhanh để rollback.
9. **Làm hỏng đo startup:** thời gian khởi động không có giới hạn rõ.
10. **Giữ resource dở dang:** mỗi attempt mở connection/thread mới nhưng không dọn đúng sẽ tạo leak theo cấp số lần thử.

Thêm `Thread.sleep(1000)` vào loop chỉ giảm tốc độ; **không** biến infinite retry thành một startup policy có thể dự đoán.

## 4. Bước đầu tiên: phân loại lỗi permanent hay transient

### Permanent failure: lỗi khó tự thay đổi nếu chỉ chờ

| Loại | Tín hiệu thường thấy | Cách xử lý |
| --- | --- | --- |
| Thiếu property bắt buộc | Binding/validation thiếu giá trị | Nêu key cần sửa và fail |
| Config sai định dạng | Port, URL, duration không hợp lệ | Fail trước khi mở resource |
| Credential không hợp lệ | Xác thực bị từ chối rõ ràng | Fail hoặc kích hoạt cơ chế secret rotation có deadline |
| Không tương thích version | Schema/service API không hỗ trợ | Fail, chặn rollout sai |
| Thiếu artifact/class | File/cert/classpath không có | Fail, kiểm tra packaging |
| Logic bug | `ClassCastException`, `NullPointerException` | Fail, sửa code |
| Input batch sai | File đầu vào format không được hỗ trợ | Fail với category non-retryable |

### Transient failure: có thể thay đổi trong một khoảng thời gian ngắn

| Loại | Tình huống | Điều kiện để retry |
| --- | --- | --- |
| Connection refused | Dependency đang restart | Đúng endpoint, có connect timeout |
| Network timeout | Mạng gián đoạn | Có per-attempt timeout |
| HTTP 503 | Dịch vụ quá tải | Backoff+jitter, giới hạn tổng |
| HTTP 429 | Bị throttle | Xem `Retry-After` trong budget |
| Broker rebalance | Consumer chưa được assign | Chờ có giới hạn và trạng thái |
| Lock đang bận | Một instance khác đang setup | Có hợp đồng lock/lease |
| DNS tạm lỗi | Resolver không đáp ứng | Retry có trần, log rõ |

**Không có bảng phân loại chung đúng cho mọi hệ thống.** HTTP 401 thường là permanent, nhưng trong một hệ thống refresh token có hợp đồng riêng, có thể có một bước refresh hợp lệ trước khi fail. Connection timeout có thể là transient, nhưng nếu hostname bị gõ sai thì lặp lại hàng giờ cũng không giúp.

### Exception taxonomy

Không nên:

~~~java
catch (Exception any) {
    retryAgain();
}
~~~

Đây là snippet phản ví dụ, chưa độc lập. Nó retry cả lỗi validation và lỗi lập trình.

Nên tách rõ:

~~~java
try {
    client.verifyConnection();
}
catch (ConfigurationRejectedException permanent) {
    throw new StartupConfigurationException(permanent);
}
catch (TemporaryNetworkException temporary) {
    // Chỉ retry nếu còn số lần và deadline.
}
~~~

Đây là snippet minh họa cần class/API thực tế. Nếu SDK chỉ ném một exception rộng, dùng status code, error code hoặc cause chain để phân loại; không suy từ chuỗi `getMessage()` chưa ổn định.

## 5. Retry có giới hạn cần những ranh giới nào?

### 5.1. Giới hạn số lần thử

Quy định `maxAttempts` là **tổng số lần gọi**, bao gồm lần đầu.

~~~text
maxAttempts = 3
Attempt 1 = lần đầu
Attempt 2 = retry lần thứ nhất
Attempt 3 = retry lần thứ hai
Sau Attempt 3 thất bại → FAIL
~~~

Không nhầm “3 attempts” thành “3 retries sau lần đầu”. Với Spring Retry 2.0, builder `maxAttempts(3)` cũng có ý nghĩa tổng attempts.

### 5.2. Deadline tổng

Nếu mỗi attempt timeout 20 giây, ba attempts vẫn có thể tốn 60 giây chưa kể backoff. Cần một ngân sách **max elapsed time** đủ phù hợp với deployment.

~~~text
Startup budget: ví dụ 20 giây
Timeout mỗi network attempt: ví dụ tối đa 3 giây
Backoff: ví dụ 200 ms → 400 ms → 800 ms, có jitter
Hết deadline trước attempt tiếp theo: FAIL
~~~

Các số này là **ví dụ thiết kế**. Dịch vụ khác nhau cần timeout khác nhau; phải dựa trên SLA, thời gian cold-start, giới hạn hệ điều hành, proxy và orchestrator.

### 5.3. Per-attempt I/O timeout

`maxAttempts=3` **không tạo giới hạn thời gian** nếu attempt thứ nhất có thể bị treo mãi. HTTP connect timeout, read timeout, JDBC login timeout hoặc timeout của broker client phải được cấu hình riêng.

`Future.get(timeout)` chỉ giới hạn thời gian **chờ ở thread gọi**; không tự bảo đảm underlying work đã dừng hay socket đã đóng. Cần cancellation/cleanup đúng API.

### 5.4. Backoff và jitter

~~~text
Ví dụ delay tăng dần:
200ms → 400ms → 800ms → 1600ms, cap 2s
Jitter: phân tán delay một khoảng ngẫu nhiên có giới hạn
Không bao giờ sleep vượt tổng startup deadline
~~~

Backoff chống việc cả trăm replica thử lại cùng lúc khi database vừa hồi phục. Đặt fixed 1 ms cho mọi replica có thể gây **thundering herd**.

### 5.5. Xử lý interrupt

Nếu shutdown gửi tín hiệu interrupt trong lúc chờ retry, không nuốt nó:

~~~java
try {
    Thread.sleep(delayMillis);
}
catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException(
            "Startup retry interrupted", interrupted);
}
~~~

Đây là method fragment, cần biến `delayMillis`. Restore interrupt flag rồi chuyển sang đường cancellation/failure theo contract, không tiếp tục `while(true)`.

## 6. Quy trình quyết định fail fast hay retry

~~~text
Bắt đầu startup validation
            |
            v
Có bắt buộc để phục vụ an toàn?
   |                        |
  KHÔNG                     CÓ
   |                        |
Có fallback?           Phân loại lỗi
  |    |                |          |
 CÓ   KHÔNG          Permanent   Transient
  |    |                |          |
  |  Xem lại            v          v
  |  contract        FAIL FAST   Thử kết nối
  |                               |
Degraded                        Thành công?
+ metrics                         |      |
                                CÓ     KHÔNG
                                 |       |
                               READY     v
                                      Còn attempts?
                                      Còn deadline?
                                      Lỗi còn retryable?
                                        |       |
                                       CÓ      KHÔNG
                                        |       |
                                  backoff +    FAIL
                                  jitter rồi   WITH
                                  thử lại      REASON
~~~

**Dừng sớm là quyết định có điều kiện**, không phải phản ứng nóng vội. Nó giúp một lỗi không thể tự sửa được biểu hiện thành kết quả hữu hạn, để vận hành nhận được cảnh báo và sửa nguyên nhân.

Với dependency **tùy chọn**, startup có thể thành công trong degraded mode chỉ khi fallback đủ an toàn và có health/metrics rõ. Nếu cơ chế fallback làm sai yêu cầu về bảo mật, dữ liệu hoặc SLA, dependency đó không còn “tùy chọn”.

## 7. Đặt logic ở đúng giai đoạn Spring Boot

| Hook | Thời điểm | Gợi ý |
| --- | --- | --- |
| Code trong `main` trước `run` | Trước Spring context | Validate argv/config tối thiểu, cleanup tự quản |
| `@Bean` factory method | Bean creation | Tạo resource; không retry vô hạn; rollback partial init |
| Constructor | Khi tạo object | Hạn chế I/O dài; không block vô hạn |
| `@PostConstruct` | Bean initialization | Khởi tạo cục bộ; không biến thành startup retry loop kéo dài |
| `SmartLifecycle.start()` | Trong context refresh | Start có timeout và rollback rõ |
| `ApplicationRunner` | Sau refresh, trước ready | Thích hợp cho startup gate bắt buộc, bounded retry |
| `CommandLineRunner` | Sau refresh, trước ready | Tương tự; nhận raw `String...` |
| `ApplicationReadyEvent` listener | Sau runners | Quan sát ready; không nên block vô hạn |
| HTTP/request/consumer sau ready | Runtime | Retry/circuit breaker/readiness riêng |

Spring Boot 3.3 khuyến nghị các startup tasks nên đặt vào `ApplicationRunner`/`CommandLineRunner` thay vì lạm dụng initialization callbacks như `@PostConstruct`. Nhưng những điều kiện **cần có để bean đúng cấu trúc** (property hợp lệ, dependency constructor) vẫn nên validate sớm; không trì hoãn lỗi quan trọng một cách vô nghĩa.

### Vòng lặp trong runner ảnh hưởng ready

Runner chạy sau refresh, trước `ApplicationReadyEvent`. Nếu runner chờ vô hạn, có thể context đã refresh và `ApplicationStartedEvent` đã xảy ra nhưng ready chưa bao giờ tới. Nếu runner throw, Boot đi đường startup failure.

### Retry trong @PostConstruct có khác không?

`@PostConstruct` xảy ra khi bean đang initialize, trước khi context hoàn tất refresh. Nếu loop kẹt ở đây, có thể **chưa có ApplicationStartedEvent** và cơ chế quan sát/probe chưa sẵn sàng. Hãy tránh giữ quá nhiều logic I/O hoặc retry lâu trong bean creation.

### Lazy bean không phải bảo đảm thành công startup

Nếu bật `spring.main.lazy-initialization=true`, một bean cấu hình sai có thể không được tạo cho tới request đầu tiên. Do đó một ứng dụng đạt ready chưa chắc mọi tính năng lazy đều hợp lệ. Với bean thực sự bắt buộc, cần explicit startup validation/eager init theo chính sách.

## 8. Project runnable Java 17+: ba đường xử lý startup

Project dưới dùng **Spring Boot 3.3.13**, **Java 17+**, **Gradle**, không dùng mạng, database hoặc web starter. Mục tiêu là **minh họa chính sách**, không giả vờ đo độ trễ của dependency thật.

Ba mode:

- `fatal`: lỗi cấu hình; không retry.
- `recover`: dependency giả lập hỏng ở những attempts đầu rồi phục hồi; runner return, Boot phát ready.
- `exhaust`: dependency giả lập hỏng cả ba attempts; runner ném exception, startup fail.

Có thêm biến `demo.succeed-at` để quyết định attempt nào thành công trong mode `recover`. Ví dụ luôn có giới hạn, không sleep và không tạo vòng lặp vô hạn.

### 8.1. Cấu trúc project

~~~text
startup-policy-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/startup/
    └── StartupPolicyApplication.java
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'startup-policy-demo'
~~~

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.startup.StartupPolicyApplication'
}
~~~

Cần Gradle tương thích với Spring Boot 3.3 và JDK 17 trở lên. Nếu có Gradle Wrapper có thể dùng wrapper; project mẫu không sinh wrapper sẵn.

### 8.2. Toàn bộ Java source

**`src/main/java/com/example/startup/StartupPolicyApplication.java`:**

~~~java
package com.example.startup;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class StartupPolicyApplication {

    private static final int MAX_ATTEMPTS = 3;

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(StartupPolicyApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN: run returned");
        }

        System.out.println("MAIN: context closed");
    }

    @Bean
    ApplicationRunner startupGate(
            @Value("${demo.mode:recover}") String mode,
            @Value("${demo.succeed-at:3}") int succeedAt) {

        return args -> {
            System.out.println("GATE: mode=" + mode);

            if ("fatal".equals(mode)) {
                System.out.println("GATE: invalid configuration");
                throw new FatalStartupException(
                        "Required configuration is invalid");
            }

            if (!"recover".equals(mode) && !"exhaust".equals(mode)) {
                System.out.println("GATE: unknown mode");
                throw new FatalStartupException(
                        "Unknown demo.mode: " + mode);
            }

            if (succeedAt < 1 || succeedAt > MAX_ATTEMPTS) {
                System.out.println("GATE: invalid succeed-at");
                throw new FatalStartupException(
                        "demo.succeed-at must be between 1 and 3");
            }

            for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {

                boolean ready = "recover".equals(mode)
                        && attempt >= succeedAt;

                System.out.println(
                        "CHECK: attempt=" + attempt
                        + " result="
                        + (ready ? "SUCCESS" : "TRANSIENT_FAILURE"));

                if (ready) {
                    System.out.println("GATE: dependency ready");
                    return;
                }
            }

            System.out.println("GATE: retry budget exhausted");
            throw new DependencyUnavailableException(
                    "Required dependency unavailable after 3 attempts");
        };
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("EVENT: ApplicationReadyEvent");
    }

    public static final class FatalStartupException
            extends IllegalStateException implements ExitCodeGenerator {

        public FatalStartupException(String message) {
            super(message);
        }

        @Override
        public int getExitCode() {
            return 20;
        }
    }

    public static final class DependencyUnavailableException
            extends IllegalStateException implements ExitCodeGenerator {

        public DependencyUnavailableException(String message) {
            super(message);
        }

        @Override
        public int getExitCode() {
            return 30;
        }
    }
}
~~~

### 8.3. Giải thích mã

- `ApplicationRunner` là một bean được Boot gọi sau context refresh và trước ready.
- Với `fatal`, vòng `for` không chạy; lỗi cấu hình bị từ chối ngay.
- Với `recover`, lần thử thứ `succeedAt` và những lần sau được mô phỏng thành công. Khi thành công, runner return; không cần dùng hết budget.
- Với `exhaust`, cả ba attempts thất bại; sau attempt cuối, chương trình **ném exception**, không quay lại lần đầu.
- Một mode lạ và giá trị `succeedAt` ngoài khoảng 1..3 là lỗi cấu hình, không đáng retry.
- Hai exception implements `ExitCodeGenerator` cho phép Spring Boot nhận mã 20 (config error) hoặc 30 (retry exhausted) khi startup failure. Đây là bảng mã **riêng của demo**.
- `ApplicationReadyEvent` chỉ được in trong đường Boot đạt ready thành công.
- `try-with-resources` ở main chỉ chạy khi `SpringApplication.run` đã trả context. Khi startup fail, Boot xử lý đường failure/cleanup riêng.
- Không tự gọi `System.exit(...)` trong runner, tránh cắt ngang cleanup và error reporting.

### 8.4. Build

Trong thư mục `startup-policy-demo`:

~~~bash
gradle bootJar
~~~

Có thể dùng `./gradlew bootJar` (Linux/macOS) hoặc `.\gradlew.bat bootJar` (Windows) nếu project đã có wrapper.

Tên executable JAR theo cấu hình mặc định:

~~~text
build/libs/startup-policy-demo-0.0.1-SNAPSHOT.jar
~~~

Nếu đổi `rootProject.name` hoặc `version`, hãy kiểm tra file trong `build/libs` thay vì giữ nguyên tên mẫu.

### 8.5. Recovery thành công ở attempt 3

~~~bash
java -jar build/libs/startup-policy-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=recover --demo.succeed-at=3
echo $?
~~~

**Các dòng do Java code của ví dụ in** (không tính log của Spring Boot hoặc Gradle):

~~~text
GATE: mode=recover
CHECK: attempt=1 result=TRANSIENT_FAILURE
CHECK: attempt=2 result=TRANSIENT_FAILURE
CHECK: attempt=3 result=SUCCESS
GATE: dependency ready
EVENT: ApplicationReadyEvent
MAIN: run returned
MAIN: context closed
~~~

Mã thoát JVM dự kiến: **0**. Runner return, Boot phát ready, `run` trả context và main đóng context bình thường.

### 8.6. Recovery thành công ngay ở attempt 2

~~~bash
java -jar build/libs/startup-policy-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=recover --demo.succeed-at=2
echo $?
~~~

Output của Java:

~~~text
GATE: mode=recover
CHECK: attempt=1 result=TRANSIENT_FAILURE
CHECK: attempt=2 result=SUCCESS
GATE: dependency ready
EVENT: ApplicationReadyEvent
MAIN: run returned
MAIN: context closed
~~~

Không có attempt 3 vì loop return ngay khi thành công.

### 8.7. Fail fast với cấu hình sai

~~~bash
java -jar build/libs/startup-policy-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=fatal
echo $?
~~~

Các dòng của Java:

~~~text
GATE: mode=fatal
GATE: invalid configuration
~~~

**Không có** `EVENT: ApplicationReadyEvent` hoặc các dòng `MAIN` sau khi `run` trả về, vì runner ném exception. Ngoài các dòng trên, Spring Boot có thể in error report và stack trace.

Khi chạy executable JAR theo Spring Boot launcher thông thường, mã thoát JVM được kỳ vọng là **20** từ `FatalStartupException.getExitCode()`.

### 8.8. Hết ngân sách retry

~~~bash
java -jar build/libs/startup-policy-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=exhaust
echo $?
~~~

Output Java:

~~~text
GATE: mode=exhaust
CHECK: attempt=1 result=TRANSIENT_FAILURE
CHECK: attempt=2 result=TRANSIENT_FAILURE
CHECK: attempt=3 result=TRANSIENT_FAILURE
GATE: retry budget exhausted
~~~

Đường này **không** có ready event. Exception `DependencyUnavailableException` cung cấp mã **30** theo policy của demo. Khi chạy bằng executable JAR/launcher thông thường, mã thoát JVM kỳ vọng là 30.

### 8.9. Mode không được hỗ trợ

~~~bash
java -jar build/libs/startup-policy-demo-0.0.1-SNAPSHOT.jar \
  --demo.mode=typo
echo $?
~~~

Output Java:

~~~text
GATE: mode=typo
GATE: unknown mode
~~~

Không chạy attempts nào. Đây là một quyết định fail-fast vì **input sai không thể tự sửa sau khi sleep**.

### 8.10. Kiểm tra status trên PowerShell

~~~powershell
java -jar .\build\libs\startup-policy-demo-0.0.1-SNAPSHOT.jar --demo.mode=exhaust
$LASTEXITCODE
~~~

Trong Bash/Zsh, `$?` là status của **lệnh gần nhất**. Hãy đọc ngay sau `java -jar`, không chèn `echo hi` hoặc một lệnh khác trước nó.

**Vì sao không kiểm tra bằng mỗi `gradle bootRun`?** Gradle là build tool/launcher. Khi JVM con trả non-zero, Gradle có thể tự báo một mã lỗi của task, không nhất thiết giữ nguyên 20/30. Nếu contract liên quan mã thoát process Java, hãy chạy JAR trực tiếp.

## 9. Deadline thực tế với operation có I/O

Demo dùng điều kiện giả lập để kiểm thử số lần. Trong production cần cả **max attempts** lẫn **deadline** và timeout cho từng attempt.

### Mẫu logic hữu hạn

~~~java
static void checkRequiredDependency(
        CheckedOperation operation,
        int maxAttempts,
        long budgetMillis) throws Exception {

    long start = System.nanoTime();
    long budgetNanos = TimeUnit.MILLISECONDS.toNanos(budgetMillis);

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {

        try {
            operation.run(); // Phải tự giới hạn I/O timeout.
            return;
        }
        catch (TransientStartupException temporary) {

            long elapsed = System.nanoTime() - start;

            if (attempt == maxAttempts || elapsed >= budgetNanos) {
                throw temporary;
            }

            long remaining = budgetNanos - elapsed;
            long delayMillis = Math.min(
                    200L * attempt,
                    TimeUnit.NANOSECONDS.toMillis(remaining));

            try {
                Thread.sleep(delayMillis);
            }
            catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Startup interrupted", interrupted);
            }
        }
    }
}
~~~

**Đây là method minh họa**, không phải file chạy độc lập: cần `java.util.concurrent.TimeUnit`, functional interface `CheckedOperation` với `void run() throws Exception` và exception `TransientStartupException`.

Nó cho thấy:

1. Số attempts có giới hạn.
2. Sau lỗi tạm thời, nếu hết attempts/deadline thì throw.
3. Sleep không vượt phần ngân sách đã tính **tại thời điểm bắt đầu sleep**.
4. Interrupt kết thúc chờ thay vì bỏ qua.
5. `System.nanoTime()` đo thời gian trôi qua tương đối, không phụ thuộc wall clock.

**Không phải hard deadline tuyệt đối:** Nếu `operation.run()` có thể treo mãi thì `budgetMillis` không tự ngắt nó. Phải cấu hình timeout ở HTTP/JDBC/broker client và close/cancel theo API tương ứng.

### Backoff có jitter

Một công thức minh họa:

~~~java
long base = 200L;
long cap = 2_000L;
int shift = Math.min(attempt - 1, 4);

long backoff = Math.min(cap, base * (1L << shift));
long half = Math.max(1L, backoff / 2L);
long jittered = ThreadLocalRandom.current()
        .nextLong(half, backoff + half + 1L);
~~~

Cần `attempt >= 1`, import `java.util.concurrent.ThreadLocalRandom`; vẫn phải cap `jittered` với deadline trước sleep. Giới hạn shift tránh overflow ở ví dụ nhỏ. Với một API trả `Retry-After`, cần xét chính sách nhà cung cấp và ngân sách còn lại.

### Retry không làm thay đổi tính idempotent

Nếu một call chỉ **đọc trạng thái**, retry thường ít rủi ro hơn. Nếu call **tạo bản ghi/đặt hàng/gửi email**, một timeout có thể đến **sau khi remote side effect đã commit**. Muốn retry, dùng idempotency key, operation ID, query trạng thái hoặc transaction/outbox thích hợp.

## 10. Spring Retry: hữu ích nhưng không thay thế startup policy

Spring Retry là thư viện riêng, không tự xuất hiện đầy đủ chỉ vì đã thêm `spring-boot-starter`. Nó cung cấp `RetryTemplate` và `@Retryable` khi cấu hình đúng phiên bản/dependency.

Ví dụ **Spring Retry 2.0.x** (minh họa, không nằm trong project mục 8):

~~~java
RetryTemplate retry = RetryTemplate.builder()
        .maxAttempts(3)
        .exponentialBackoff(200, 2.0, 2_000)
        .retryOn(TransientStartupException.class)
        .build();

retry.execute(context -> {
    client.ping();
    return null;
});
~~~

Đoạn này cần dependency Spring Retry tương thích, imports và class `TransientStartupException`, object `client` được định nghĩa. `maxAttempts(3)` gồm lần gọi đầu và tối đa hai retry.

### Giới hạn của annotation @Retryable

Khi dùng AOP proxy:

- Self-invocation thường **không** đi qua proxy và có thể không áp dụng retry.
- `@PostConstruct` có thể chạy trước khi target được proxy hóa như kỳ vọng; không coi annotation trên init method là cách xử lý retry được đảm bảo.
- Exception phát sinh trong background thread sau khi method đã return không tự quay lại caller.
- Cấu hình retry mọi exception có thể gây retry bug lập trình và lỗi cấu hình vĩnh viễn.
- Một startup gate cần kết quả cuối nên gọi `RetryTemplate` hoặc cơ chế retry rõ ràng từ runner và throw khi hết policy.

**Khác biệt phiên bản:** Spring Framework 7 đưa vào API resilience khác. Không copy annotation/API của Framework 7 vào Boot 3.3 / Framework 6.1 mà không thêm dependency tương ứng.

## 11. Readiness, liveness và startup probes

Trong web application có Spring Boot Actuator, các trạng thái availability liên quan đến probe nhưng không đồng nghĩa với nhau.

| Tín hiệu | Câu hỏi trả lời | Phản ứng Kubernetes thường thấy |
| --- | --- | --- |
| **Liveness** | Ứng dụng còn hoạt động nội bộ đúng và có thể tự phục hồi không? | Lỗi đủ ngưỡng → restart container |
| **Readiness** | Instance hiện có thể nhận traffic không? | NotReady → ngừng route request mới đến instance |
| **Startup probe** | Giai đoạn startup có kết thúc trong ngân sách không? | Khi chưa thành công, hoãn kiểm tra liveness/readiness; quá ngưỡng → kill/restart |

### Vì sao DB health không nên quyết định liveness của mọi replica?

Nếu DB tạm ngừng và tất cả pod coi đó là liveness failure, Kubernetes có thể restart **toàn bộ** pod một cách đồng loạt, đẩy thêm tải lên DB khi đang phục hồi. Theo hướng dẫn Spring Boot/Kubernetes, liveness thường nên phản ánh **khả năng hoạt động nội bộ**, không phụ thuộc trực tiếp vào mọi hệ thống bên ngoài.

Readiness có thể kiểm tra điều kiện thiết yếu để nhận request; tuy nhiên **không mặc định** thêm mọi health indicator bên ngoài vào readiness mà không hiểu tác động khi hệ thống phụ gặp sự cố.

### Actuator probe paths

Trong ứng dụng có web starter và `spring-boot-starter-actuator`:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

Các URL thường gặp khi cấu hình phù hợp:

~~~text
/actuator/health/liveness
/actuator/health/readiness
/livez
/readyz
~~~

Đây **không phải endpoint của project CLI mục 8** vì project không có web server/Actuator. Spring Boot 3.3 có thể tự bật health groups liveness/readiness khi chạy trong môi trường Kubernetes; property trên hữu ích khi muốn chủ động bật ở môi trường khác.

### Fragment Kubernetes minh họa

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
  failureThreshold: 3
~~~

Đây là **fragment của container spec**, không phải Kubernetes Deployment hoàn chỉnh. Endpoint/cổng cần khớp thực tế. Startup probe có thể giúp tránh giết ứng dụng hợp lệ chỉ vì initialization mất thời gian; nó **không khắc phục** config sai hoặc dependency đang down.

### Readiness không được giữ lỗi vĩnh viễn trong im lặng

Với một dependency bắt buộc nhưng tạm thời chưa có, instance có thể không ready trong lúc bounded retry. Nhưng với URL sai cố định, một pod NotReady vô hạn không giúp rollback. Lựa chọn fail fast có tín hiệu error/exit rõ thường tốt hơn.

## 12. Infinite retry trong JVM khác CrashLoopBackOff

Cần phân biệt hai vòng lặp:

### A. JVM vẫn chạy và tự retry vô hạn

~~~text
JVM #1
  |
  +-- SpringApplication.run
        |
        +-- runner while(true)
              |
              +-- retry retry retry...
              |
              +-- Không return, không throw
~~~

Ở đây process không kết thúc, có thể không ready, và platform chỉ có thể can thiệp nếu có timeout/probe/monitoring phù hợp.

### B. JVM fail, platform khởi động lại nhiều lần

~~~text
JVM #1 → startup fail, exit non-zero
restartPolicy → JVM #2 → startup fail, exit non-zero
backoff → JVM #3 → startup fail, exit non-zero
...
CrashLoopBackOff
~~~

Đây là cơ chế container restart/backoff, **không** phải bằng chứng trong code có `while(true)`. CrashLoopBackOff chỉ ra một instance liên tục thất bại và bị khởi chạy lại theo policy.

**Hệ quả vận hành:** Nếu một lần startup đã retry 50 lần, rồi orchestrator lại retry process nhiều lần, tổng số call lên dependency có thể rất lớn. Cần xét retry budget ở **cả hai tầng**.

Khi thấy CrashLoopBackOff, hãy kiểm tra logs của lần chạy trước, pod events, exit code, probes, resource limits và cấu hình; đừng chỉ tăng thời gian retry để che lỗi.

## 13. Fail fast và degraded mode có thể cùng tồn tại

### Điều kiện bắt buộc: không chấp nhận degrade tùy tiện

Nếu một service không thể xác thực JWT khi thiếu signing key, hoặc không thể ghi đơn hàng khi database bắt buộc không hoạt động, **không** đánh dấu ready chỉ vì controller đã khởi tạo. Có thể:

- Fail fast với cấu hình sai.
- Bounded retry với dependency đang boot.
- Khi hết budget, fail rõ.
- Hoặc not-ready theo kiến trúc recovery riêng, nhưng cần một deadline/điều kiện kết luận đúng.

### Tính năng tùy chọn: degraded startup có chủ đích

Ví dụ recommendation service:

~~~text
Core checkout: READY
Recommendation: UNAVAILABLE
Fallback: ẩn gợi ý / hiển thị danh sách mặc định
Background reconnect: timeout, backoff, circuit breaker
Monitoring: degraded count, reconnect failures
~~~

Nếu core vẫn làm việc an toàn, không nhất thiết chặn startup vì recommendation đang lỗi. Nhưng nếu SLA đòi mọi request có recommendation thì hợp đồng đã khác.

### Khác nhau giữa startup gate và runtime recovery

- **Startup gate:** kiểm tra điều kiện thiết yếu trước ready.
- **Runtime recovery:** xử lý lỗi sau ready bằng timeout, retry per-operation, circuit breaker và cập nhật readiness/feature state.
- **Reconciliation:** sau khi dependency hồi phục, khôi phục kết nối/cache/checkpoint như hợp đồng.

Một lần startup thành công không đảm bảo dependency tồn tại mãi. Không đưa mọi retry về một runner duy nhất.

## 14. Fail fast vẫn cần cleanup

Dừng sớm **không** có nghĩa gọi `Runtime.halt(...)` hoặc `System.exit(...)` ngay tại constructor/`@PostConstruct`.

Khi một bước tạo tài nguyên rồi thất bại:

1. Giữ exception gốc và cause chain.
2. Cleanup các resource đã acquire trong bước đó, theo thứ tự phù hợp.
3. Cho Boot xử lý startup failure để hủy context/beans đã quản lý khi có thể.
4. Báo exit category rõ; không nuốt lỗi thành ready.
5. Đảm bảo log không chứa password/token/PII.

Ví dụ minh họa:

~~~java
Connection connection = openConnection();

try {
    Subscription subscription = openSubscription(connection);
    return new ManagedClient(connection, subscription);
}
catch (RuntimeException original) {
    try {
        connection.close();
    }
    catch (RuntimeException cleanupFailure) {
        original.addSuppressed(cleanupFailure);
    }
    throw original;
}
~~~

Đây là **snippet chưa độc lập**; cần các classes/helpers tương ứng. Nếu lỗi có thể xảy ra **sau khi subscription đã mở**, cleanup cũng phải đóng subscription trước connection. Không trông chờ `@PreDestroy` của bean chưa hoàn tất init để dọn mọi tài nguyên local mà factory đã mở.

### Mã thoát không thay thế dọn tài nguyên

Demo dùng exceptions implements `ExitCodeGenerator`. Spring Boot có cơ chế chọn mã thoát từ exception trong startup failure. Tuy vậy, exit code chỉ là **tín hiệu kết quả** cho OS, không phải cleanup strategy.

`SpringApplication.exit(context)` là API tính mã và đóng context đã có, khác với việc `SpringApplication.run` chưa trả context vì startup failure. Không gọi `SpringApplication.exit(null)` trong catch để “cứu” một context không tồn tại.

## 15. Ngân sách startup và quá trình deploy

Nếu một pod có startup probe budget khoảng 60 giây mà app retry 5 phút, kubelet có thể kill pod **trước khi** ứng dụng tự kết luận hết retry. Nếu app fail fast sau 2 giây nhưng orchestrator restart lặp lại nhiều lần, bạn sẽ thấy một dạng vòng lặp **ở tầng platform**.

Cần tính:

~~~text
Startup budget cấp deployment
    = JVM/class loading + Spring context refresh
    + tổng các required startup checks
    + retry/backoff trong giới hạn
    + buffer do scheduling, probes, shutdown
~~~

Các mốc không phải lúc nào cũng cộng tuyến tính, nhưng công thức là cách tư duy để tránh cấu hình mâu thuẫn.

### Rolling deployment

- **Config/schema sai:** fail fast giúp deploy phát hiện lỗi sớm và rollback khi policy cho phép.
- **DB boot chậm vài giây:** bounded retry có thể giảm restart không cần thiết.
- **Nhiều pod cùng retry:** jitter/backoff tránh làm DB quá tải khi phục hồi.
- **Ứng dụng never-ready:** rollout có thể treo đến timeout và báo lỗi thiếu ngữ cảnh.
- **Graceful stop:** nếu process nhận SIGTERM khi đang retry, cần interrupt/cancellation và dọn tài nguyên.

Startup probe là công cụ **giám sát/thời gian chờ**, không tự sửa connection URL hoặc dữ liệu migration.

## 16. Logs và metrics để phân biệt quyết định

Mẫu log thành công sau retry:

~~~text
startup_gate_started
dependency_check attempt=1 outcome=transient_failure
dependency_check attempt=2 outcome=transient_failure
dependency_check attempt=3 outcome=success
startup_gate_passed
application_ready
~~~

Mẫu fail fast:

~~~text
startup_gate_started
startup_validation_failed category=permanent key=DB_URL
startup_aborted exit_category=configuration
~~~

Mẫu hết budget:

~~~text
startup_gate_started
dependency_check attempt=3 outcome=transient_failure
startup_retry_exhausted max_attempts=3 elapsed_ms=8200
startup_aborted category=dependency_unavailable
~~~

Đây là **mẫu log nghiệp vụ**, không phải output thật của demo không có mạng. Đừng ghi nguyên chuỗi credential, connection URI chứa password hay payload nhạy cảm.

### Metrics có ích

- `startup.validation.failure.total` theo category.
- `startup.dependency.attempts` và số retries.
- `startup.retry.exhausted.total`.
- `startup.retry.duration`, `startup.total.duration`.
- Thời gian từ process start đến `ApplicationReadyEvent`.
- Pod restart count, số lỗi startup probe, trạng thái readiness.
- Runtime reconnect attempts nếu áp dụng degraded mode.

**Không đưa raw exception message hoặc request ID vào metric label** vì gây cardinality cao. Chọn category hữu hạn và ghi chi tiết trong structured log với policy bảo vệ dữ liệu.

## 17. Kiểm thử startup policy

### Ma trận

| Trường hợp | Số dependency attempts | Ready event? | Kết luận |
| --- | ---: | --- | --- |
| `fatal` | 0 | Không | Fail fast |
| `recover, succeed-at=1` | 1 | Có | Thành công |
| `recover, succeed-at=2` | 2 | Có | Thành công |
| `recover, succeed-at=3` | 3 | Có | Thành công |
| `exhaust` | 3 | Không | Retry exhausted |
| Mode lạ | 0 | Không | Cấu hình sai |
| `succeed-at=0` | 0 | Không | Cấu hình sai |
| Permanent error ở attempt thứ hai | 2 | Không | Dừng ngay |
| Interrupted trong backoff | Dừng ngay | Không | Cancel/failure |
| Network call treo | Phải có per-attempt timeout | Không khi hết budget | Fail hữu hạn |

### Test bằng fake dependency

Một fake operation:

~~~java
AtomicInteger attempts = new AtomicInteger();

Runnable probe = () -> {
    if (attempts.incrementAndGet() < 3) {
        throw new TemporaryNetworkException("Not ready");
    }
};
~~~

Đây là **snippet minh họa**, cần import `AtomicInteger` và định nghĩa `TemporaryNetworkException`, cũng như một retry executor để gọi `probe`. Assert sau khi retry hữu hạn: `attempts.get() == 3`. Với permanent exception, assert không gọi thêm lần thứ hai.

### Process-level integration test

Muốn kiểm tra **mã thoát thực tế**, chạy Spring Boot JAR trong một JVM con bằng `ProcessBuilder` hoặc shell:

1. Build JAR.
2. Chạy lần lượt `recover`, `fatal`, `exhaust`.
3. Đọc stdout/stderr và exit code.
4. Đặt timeout cho JVM con để phát hiện hồi quy thành vòng lặp vô hạn.
5. Xác minh `ApplicationReadyEvent` chỉ có ở mode thành công.
6. Nếu test process quá deadline, kill child process và báo lỗi test; không cho CI treo vô hạn.

Không dùng `System.exit` trong chính JVM chứa JUnit runner. Không dùng `Thread.sleep(1000)` lặp nhiều lần làm cách xác nhận chính sách retry; nên inject clock/sleeper hoặc fake operation.

### ApplicationFailedEvent

Spring Boot có thể phát `ApplicationFailedEvent` khi startup lỗi. Nếu cần quan sát **cả lỗi rất sớm** trước khi context refresh, đăng ký `ApplicationListener` với `SpringApplication` ở đầu quá trình boot. Một bean `@EventListener` chưa được tạo không nhất thiết nhận được event ở giai đoạn trước BeanFactory.

## 18. Lỗi thường gặp

**1. “Chưa ready thì cứ retry mãi.”** Không; nếu sai URL/mật khẩu, thời gian không sửa được lỗi.

**2. “Fail fast có nghĩa bỏ qua mọi lỗi transient.”** Không; có thể retry ngắn, có deadline, rồi fail khi hết budget.

**3. “catch(Exception) là chính sách retry tốt.”** Sai; phải phân loại permanent/transient.

**4. “maxAttempts=3 có nghĩa ba retry cộng lần đầu.”** Sai nếu hợp đồng là tổng số lần; Spring Retry 2.0 cũng tính cả lần đầu trong maxAttempts.

**5. “Chỉ cần maxAttempts là đủ.”** Sai nếu một attempt có thể block vô hạn; cần I/O timeout và tổng deadline.

**6. “Backoff không quan trọng nếu timeout ngắn.”** Nhiều pod cùng retry có thể tạo bão request; cần jitter.

**7. “Nuốt InterruptedException để retry tiếp.”** Có thể khiến startup không phản hồi shutdown.

**8. “@PostConstruct thích hợp cho retry network nhiều phút.”** Thường không; nó chặn bean initialization và context refresh.

**9. “@Retryable luôn chạy qua self-invocation.”** Không với proxy-based retry thông thường.

**10. “Chỉ cần spring-boot-starter là có đủ Spring Retry.”** Không; cần dependency/cấu hình đúng.

**11. “ApplicationStartedEvent là ApplicationReadyEvent.”** Không; runners chạy ở giữa.

**12. “Có port đang listen nghĩa là ready.”** Không; có thể còn startup gate chưa pass.

**13. “ApplicationReadyEvent luôn xảy ra dù runner throw.”** Không trong đường startup bình thường.

**14. “Liveness nên kiểm tra mọi dependency.”** Có thể khiến tất cả pod restart khi external DB down.

**15. “Readiness fail mãi giúp chữa config sai.”** Không; nếu lỗi permanent, fail fast thường rõ ràng hơn.

**16. “Startup probe giải quyết mọi lỗi start.”** Không; chỉ điều khiển cách platform đánh giá/chờ/khởi động lại.

**17. “CrashLoopBackOff là dấu hiệu có while(true) trong code.”** Không; đó là hiện tượng platform restart process thất bại.

**18. “Retry nội bộ và restart của Kubernetes độc lập nên không cần phối hợp.”** Sai; tổng số request/tải có thể nhân lên.

**19. “System.exit() trong @Bean là fail fast chuẩn.”** Không nên; có thể cắt ngang error reporting và cleanup.

**20. “gradle bootRun trả đúng exit code của Java app.”** Không bảo đảm; dùng direct JAR để kiểm tra.

**21. “Bật lazy init luôn giúp phát hiện lỗi sớm.”** Không; lỗi lazy bean có thể xuất hiện ở request đầu.

**22. “Có fallback thì mọi dependency đều optional.”** Không khi fallback vi phạm correctness hoặc security.

**23. “Retry write an toàn giống retry read.”** Không; side effect có thể đã commit trước khi client timeout.

**24. “Future timeout nghĩa là underlying task đã chết.”** Không; cần cancel/cleanup với worker hợp tác.

**25. “Startup thành công nghĩa là dependency luôn khỏe.”** Không; runtime recovery là vấn đề riêng.

**26. “Infinite retry không cần metrics vì process vẫn alive.”** Sai; đây có thể là outage never-ready rất khó quan sát.

## 19. Bài thực hành

1. Phân biệt fail fast, bounded retry, infinite retry và degraded startup bằng bốn tình huống.
2. Vì sao thiếu signing key bắt buộc nên fail fast hơn retry connection?
3. Đề xuất maxAttempts/deadline/backoff cho một DB khởi động chậm 5 giây.
4. Nếu một attempt có thể block 60 giây, ba attempts có giúp deadline 10 giây không?
5. Chạy `recover / succeed-at=3`. Vì sao có ba attempts nhưng chỉ một ready event?
6. Chạy `recover / succeed-at=1`. Vì sao không có attempt thứ hai?
7. Chạy `fatal`. Vì sao không in `MAIN: run returned`?
8. Chạy `exhaust`. Vì sao phải throw thay vì quay lại attempt đầu?
9. Chạy mode `typo`. Tại sao đây không phải transient error?
10. Thêm một mode `fatal` do quyền truy cập sai; xác định exit code và log phù hợp.
11. Tại sao `ApplicationStartedEvent` có thể đã phát dù runner sau đó fail?
12. So sánh đặt retry trong constructor với đặt trong runner.
13. Tại sao annotation `@Retryable` có thể không hoạt động khi self-invocation?
14. Dùng fake operation fail hai lần rồi thành công, assert số lần gọi là ba.
15. Đưa fake operation luôn fail; assert stop sau maxAttempts và exception gốc không bị nuốt.
16. Dùng fake clock/sleeper để test tổng deadline mà không sleep thật.
17. Khi thread bị interrupt trong backoff, code phải làm gì?
18. Với HTTP 429/503, thiết kế retry có `Retry-After`, jitter và max elapsed.
19. Một POST tạo resource đã thành công nhưng client timeout. Retry như thế nào để không tạo trùng?
20. Nếu toàn bộ pod restart khi DB down, health liveness của bạn có thể sai ở đâu?
21. Khi startup probe budget 60 giây nhưng retry budget 5 phút, chuyện gì xảy ra?
22. Tại sao CrashLoopBackOff không đồng nghĩa có infinite loop trong JVM?
23. Một tính năng recommendation tùy chọn fail; thiết kế degraded mode và readiness thế nào?
24. Viết integration test chạy JAR và đọc exit code cho `fatal`/`exhaust`/`recover`.
25. Khi SIGTERM xảy ra giữa retry, timeout và cleanup phải phối hợp thế nào?
26. Với rolling deployment, vì sao fail fast do schema mismatch có thể giúp rollback sớm?
27. Nêu ba dấu hiệu cần theo dõi để phân biệt “startup chậm nhưng hợp lệ” và “startup không có khả năng hoàn tất”.
28. Nếu một lazy bean sai cấu hình chỉ được tạo ở request đầu, đó còn là startup failure theo cơ chế `SpringApplication.run` không?
29. Dùng `ExitCodeGenerator` cho ba loại lỗi và mô tả retry policy của scheduler dựa trên các mã đó.
30. Xây dựng checklist code review cho một startup gate kết nối DB, kiểm tra migration và khởi động broker consumer.

## Ghi nhớ

- **Fail fast** là dừng có chủ đích khi một điều kiện thiết yếu không thể tự phục hồi; nó tạo tín hiệu failure rõ, không phải một lỗi thiết kế.
- **Bounded retry** chỉ phù hợp với lỗi transient, kèm **max attempts, tổng deadline, timeout từng attempt, backoff+jitter, interrupt handling và cleanup**.
- **Infinite retry trong startup** có thể khiến `ApplicationReadyEvent` không bao giờ tới và che nguyên nhân lỗi.
- Trong Spring Boot 3.3, `ApplicationStartedEvent` đến **trước** các runners; `ApplicationReadyEvent` đến **sau** runners thành công.
- `ApplicationRunner` thường là nơi phù hợp cho startup task cần hoàn thành trước ready; constructor/`@PostConstruct` không nên block vô hạn.
- **Liveness** chủ yếu phản ánh sức khỏe nội bộ; **readiness** quyết định nhận traffic; **startup probe** cho phép thời gian khởi động hợp lệ.
- **CrashLoopBackOff** là cơ chế restart/backoff của platform khi process thất bại nhiều lần, khác với infinite retry trong một JVM.
- Retry không thay thế validation, idempotency, health, circuit breaker hoặc recovery runtime.
- Mục tiêu của startup policy tốt là **có điểm kết thúc hữu hạn, có nguyên nhân, có log/metrics, và có đường phục hồi**.

### Tài liệu tham khảo

- Spring Boot 3.3 — SpringApplication, Startup Failure, Application Events và Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Actuator, Health Groups và Probes: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — ApplicationRunner Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3 — ApplicationReadyEvent Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
- Spring Boot 3.3 — ExitCodeGenerator Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ExitCodeGenerator.html
- Spring Retry 2.0.x — RetryTemplateBuilder: https://docs.spring.io/spring-retry/docs/2.0.x/apidocs/spring.retry/org/springframework/retry/support/RetryTemplateBuilder.html
- Kubernetes — Liveness, Readiness and Startup Probes: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#container-probes
- Kubernetes — Pod Lifecycle and CrashLoopBackOff: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
- Java SE 17 — System.nanoTime and System.exit: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html
