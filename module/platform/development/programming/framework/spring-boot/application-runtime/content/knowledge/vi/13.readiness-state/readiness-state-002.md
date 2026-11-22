# LivenessState.CORRECT và BROKEN: sức khỏe nội bộ của ứng dụng Spring Boot

## 1. Liveness trả lời câu hỏi gì?

Khi vận hành một ứng dụng Spring Boot, cần phân biệt ít nhất ba câu hỏi: tiến trình còn tồn tại không, ứng dụng có **khả năng hoạt động đúng từ bên trong** không, và ứng dụng **đã sẵn sàng nhận yêu cầu** chưa. Một JVM đang chạy vẫn có thể bị kẹt trong trạng thái nội bộ không thể phục hồi; ngược lại, một dịch vụ chưa sẵn sàng vì đang kết nối lại database chưa chắc phải bị khởi động lại.

Spring Boot dùng `org.springframework.boot.availability.LivenessState` để diễn tả câu hỏi thứ hai. Enum này chỉ có hai giá trị:

- `LivenessState.CORRECT`: ứng dụng đang ở trạng thái nội bộ được xem là đúng, có thể tiếp tục hoạt động.
- `LivenessState.BROKEN`: trạng thái nội bộ bị hỏng và **không thể tự phục hồi** theo chính sách của ứng dụng; hạ tầng vận hành nên cân nhắc **khởi động lại instance**.

Liveness là **tín hiệu để quyết định có nên restart một instance** chứ không phải tổng hợp mọi phép kiểm tra sức khỏe có thể nghĩ ra. Trạng thái `BROKEN` có ý nghĩa mạnh; báo nhầm có thể khiến Kubernetes liên tục khởi động lại các pod đang còn khả năng phục vụ.

Trong Spring Boot 3.3, liveness là một phần của hệ thống `ApplicationAvailability`. Khi có Actuator, các trạng thái này có thể được đưa ra qua health group và Kubernetes HTTP probes. Bản thân enum chỉ là **trạng thái trong bộ nhớ của ứng dụng**; HTTP endpoint, kubelet và chính sách restart là những lớp khác.

Bài học dùng **Spring Boot 3.3.x, Java 17+**. Nội dung sẽ giải thích khi nào dùng `CORRECT`/`BROKEN`, các mốc tự động trong lifecycle, cách đọc/công bố trạng thái, kiểm thử, cấu hình Actuator và cách tránh lỗi vận hành.

## 2. Ý nghĩa chính xác của CORRECT và BROKEN

| Trạng thái | Ý nghĩa | Cách phản ứng thường phù hợp |
| --- | --- | --- |
| `CORRECT` | Những bất biến nội bộ thiết yếu vẫn đúng; ứng dụng có thể hoạt động hoặc tự xử lý sự cố bình thường | Giữ instance chạy, quan sát lỗi và readiness độc lập |
| `BROKEN` | Có lỗi nội bộ không thể tự sửa trong instance hiện tại; tiếp tục sử dụng instance có thể không an toàn | Để cơ chế giám sát/orchestrator phát hiện và restart, hoặc thực hiện chiến lược khôi phục đã định nghĩa |

### 2.1. CORRECT không có nghĩa mọi request đều thành công

Ví dụ, một service mất kết nối tới API đối tác trong 30 giây, nhưng vẫn có cơ chế retry/backoff/circuit breaker và có thể phục hồi khi API trở lại. **Liveness vẫn có thể là CORRECT**. Một endpoint nghiệp vụ phụ thuộc đối tác có thể tạm thất bại; điều đó **không biến trạng thái nội bộ thành BROKEN**.

Tương tự, `CORRECT` không có nghĩa:

- 100% request HTTP trả về 200.
- Database, Redis, Kafka, DNS hoặc mạng bên ngoài luôn sẵn sàng.
- Tất cả cache đều đã ấm, mọi batch đã xong.
- Ứng dụng đã công bố `ReadinessState.ACCEPTING_TRAFFIC`.
- Không có cảnh báo về bộ nhớ, latency hay CPU.
- Máy chủ HTTP trên port chính thực sự còn nhận kết nối.

Liveness và các tín hiệu khác cần được quan sát **cùng nhau**, chứ không thay thế nhau.

### 2.2. BROKEN không phải tên gọi chung cho một lỗi tạm thời

`BROKEN` phù hợp khi **instance không còn khả năng tự trở về trạng thái hoạt động đúng**, ví dụ:

- Một thành phần điều phối cốt lõi bị hỏng không thể tái tạo trong process.
- Dữ liệu trạng thái chỉ tồn tại trong bộ nhớ bị corrupt nghiêm trọng và ứng dụng không thể xây lại an toàn.
- Một invariant nội bộ bắt buộc bị vi phạm đến mức tiếp tục xử lý có thể tạo kết quả sai.
- Một subsystem thiết yếu chết hẳn, không còn cơ chế restart/recreate đáng tin cậy trong process.

Đây là **những ví dụ phụ thuộc thiết kế ứng dụng**, không phải quy tắc tự động rằng mọi exception, mọi thread bị dừng hay mọi lỗi cache đều phải chuyển sang `BROKEN`. Nếu một lỗi có thể khôi phục an toàn trong process, chưa có cơ sở để yêu cầu restart chỉ dựa vào lỗi đó.

### 2.3. Từ BROKEN không tự làm JVM thoát

Việc publish `LivenessState.BROKEN`:

1. Tạo một `AvailabilityChangeEvent`.
2. Cập nhật trạng thái được `ApplicationAvailability` theo dõi khi event được xử lý.
3. Khi probes và Actuator được cấu hình, có thể khiến liveness health group báo không khỏe.
4. **Không tự gọi `System.exit`, không tự restart JVM và không tự khởi động lại Kubernetes pod.**

Việc restart phụ thuộc **hạ tầng đang kiểm tra liveness**, cấu hình ngưỡng probe và restart policy. Trong CLI hoặc local JVM không có orchestrator, trạng thái `BROKEN` có thể chỉ tồn tại trong bộ nhớ mà không có hành động tự động nào.

## 3. Liveness khác readiness và health tổng quát

Spring Boot có hai trục availability chính:

| Câu hỏi | API/trạng thái | Phản ứng khi thất bại |
| --- | --- | --- |
| Instance có bị hỏng nội bộ không thể tự phục hồi không? | `LivenessState.CORRECT` / `BROKEN` | Thường **restart instance** |
| Instance có nên nhận traffic/công việc mới lúc này không? | `ReadinessState.ACCEPTING_TRAFFIC` / `REFUSING_TRAFFIC` | Thường **ngừng định tuyến traffic**, giữ instance sống |
| Dependency hoặc subsystem đang khỏe không? | `HealthIndicator`/`HealthContributor`, các health groups | Tùy group và mục đích, có thể báo lỗi cho monitoring |
| Tiến trình JVM có còn chạy không? | PID/process monitor | Giám sát mức hệ điều hành/container |
| HTTP endpoint có thể truy cập không? | Probe HTTP và network path | Phụ thuộc server, firewall, port, route và chính sách hạ tầng |

**Ví dụ A — database tạm mất kết nối:** ứng dụng có thể retry và phục hồi. Không nên tự động đổi liveness thành `BROKEN` chỉ vì kết nối database thất bại. Có thể xử lý lỗi tại request, dùng circuit breaker, hoặc điều chỉnh readiness nếu việc phục vụ traffic thật sự không còn an toàn.

**Ví dụ B — startup nạp cache:** container đã refresh, trạng thái liveness có thể là `CORRECT` nhưng `ApplicationRunner` còn đang thực hiện công việc bắt buộc. Readiness thường vẫn `REFUSING_TRAFFIC`. Không nên restart vì chưa ready.

**Ví dụ C — bộ điều phối nội bộ bị corrupt không thể tái tạo:** instance không còn đáng tin dù database và mạng đều tốt. Khi đó công bố `BROKEN` có thể phù hợp hơn việc chỉ trả `REFUSING_TRAFFIC` mãi mãi.

**Ví dụ D — bảo trì tạm hoặc quá tải:** ứng dụng vẫn đúng về mặt nội bộ, nhưng cần từ chối nhận công việc mới. `ReadinessState.REFUSING_TRAFFIC` thường đúng ý nghĩa hơn `LivenessState.BROKEN`.

Điều quan trọng: **một instance có thể live nhưng chưa ready**. Đây là trạng thái bình thường trong startup và một số thời điểm vận hành.

## 4. Trạng thái mặc định theo vòng đời Spring Boot

Spring Boot tự quản lý các mốc availability cơ bản. Với một lần `SpringApplication.run(...)` thông thường:

```text
SpringApplication bắt đầu
    |
    | LivenessState.BROKEN
    | ReadinessState.REFUSING_TRAFFIC
    | (trạng thái bảo vệ ban đầu: chưa tuyên bố ứng dụng đã sống/ready)
    |
Tạo ApplicationContext / chuẩn bị Environment
    |
context.refresh()
    |
ContextRefreshedEvent
    |
ApplicationStartedEvent
    |
AvailabilityChangeEvent<LivenessState.CORRECT>
    |
    | Liveness = CORRECT
    | Readiness = REFUSING_TRAFFIC
    |
ApplicationRunner và CommandLineRunner
    |
ApplicationReadyEvent
    |
AvailabilityChangeEvent<ReadinessState.ACCEPTING_TRAFFIC>
    |
    | Liveness = CORRECT
    | Readiness = ACCEPTING_TRAFFIC
    |
Vận hành
    |
Khi shutdown bình thường: readiness chuyển về REFUSING_TRAFFIC
    |
Đóng ApplicationContext, dừng HTTP server
```

Các dòng thể hiện **trật tự và giá trị mặc định điển hình**, không phải đảm bảo HTTP endpoint liveness đã truy cập được từ lúc tiến trình mới bắt đầu. Lúc startup, web server có thể chưa mở nên probe có thể nhận connection refused. Đến khi context refresh, việc mở HTTP server và đăng ký route vẫn phụ thuộc loại ứng dụng/cấu hình.

### 4.1. Tại sao lúc bắt đầu lại là BROKEN?

Trong bảng lifecycle/probe của Spring Boot, trạng thái liveness ban đầu được mô tả là `BROKEN`. Điều này **không có nghĩa Boot đã phát hiện một lỗi nghiêm trọng thực sự** ngay khi khởi tạo. Đó là cách mặc định **chưa xác nhận instance live** trước khi startup qua được mốc cần thiết.

Khi context đã refresh và Spring Boot phát `ApplicationStartedEvent`, Boot phát tiếp `AvailabilityChangeEvent` mang `LivenessState.CORRECT`. Vì thế, **BROKEN trong startup** và **BROKEN sau khi ứng dụng đang chạy do lỗi nội bộ** có bối cảnh khác nhau. Không đọc một chữ `BROKEN` không kèm thời gian/lifecycle rồi kết luận ứng dụng bị corrupt.

### 4.2. CORRECT trước khi runner hoàn tất

Theo trình tự Spring Boot 3.3:

1. `ApplicationStartedEvent` được phát sau khi context refresh và trước runner.
2. Spring Boot công bố `LivenessState.CORRECT`.
3. Sau đó mới gọi `ApplicationRunner`/`CommandLineRunner`.
4. `ApplicationReadyEvent` xuất hiện sau các runner.
5. Spring Boot công bố `ReadinessState.ACCEPTING_TRAFFIC`.

Do đó, code bên trong một runner có thể thấy:

```text
liveness = CORRECT
readiness = REFUSING_TRAFFIC
```

Hai giá trị **không mâu thuẫn**. Chúng diễn tả ứng dụng đã đủ điều kiện tự hoạt động, nhưng các bước startup trước khi nhận traffic chưa hoàn tất.

### 4.3. Không nhầm ApplicationReadyEvent với state-change event

Một listener nhận `ApplicationReadyEvent` chạy **trước** sự kiện riêng đưa readiness thành `ACCEPTING_TRAFFIC`. Vì vậy nếu cần xác nhận **đúng trạng thái availability đã thay đổi**, hãy nghe `AvailabilityChangeEvent<ReadinessState>` hoặc đọc trạng thái tại thời điểm phù hợp, thay vì giả định snapshot readiness bên trong mọi `ApplicationReadyEvent` nhất thiết đã là accepting.

`ApplicationReadyEvent` vẫn là mốc quan trọng của Boot; điểm cần phân biệt chỉ là thứ tự giữa **application event** và **availability state event**.

## 5. API: LivenessState, AvailabilityState và ApplicationAvailability

`LivenessState` là enum trong package:

```java
org.springframework.boot.availability.LivenessState
```

Nó implement `AvailabilityState` và có hai hằng `CORRECT`, `BROKEN`. Muốn **đọc** trạng thái hiện hành, dùng `ApplicationAvailability`:

```java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;

LivenessState state = availability.getLivenessState();
```

Đây là snippet, biến `availability` được inject qua constructor hoặc method bean. Trong ví dụ ứng dụng hoàn chỉnh ở phần sau sẽ cho thấy cách lấy bean đúng.

Các API liên quan:

| API | Ý nghĩa |
| --- | --- |
| `availability.getLivenessState()` | Lấy trạng thái liveness hiện tại |
| `availability.getReadinessState()` | Lấy trạng thái readiness hiện tại |
| `availability.getState(LivenessState.class)` | Lấy liveness qua interface tổng quát; có thể trả `null` nếu chưa có state event |
| `availability.getState(LivenessState.class, LivenessState.BROKEN)` | Lấy state với giá trị fallback do caller định nghĩa |
| `availability.getLastChangeEvent(LivenessState.class)` | Lấy sự kiện thay đổi cuối nếu có, để chẩn đoán nguồn/timing |

`ApplicationAvailability` là abstraction **đọc thông tin**, không có method `setLivenessState(...)`. Để đổi trạng thái, Spring Boot thiết kế `AvailabilityChangeEvent`.

### 5.1. Đọc trạng thái mà không làm lại health check

`ApplicationAvailability` lưu dấu vết những thay đổi availability do event điều khiển. `getLivenessState()` không phải một hàm đi ping database hay kiểm tra đường HTTP mới mỗi lần gọi.

Nó là **snapshot trạng thái được công bố**. Nếu logic monitor của bạn đã ngừng phát hiện lỗi hoặc chưa từng phát sự kiện `BROKEN`, `getLivenessState()` không tự phát hiện mọi sự cố chỉ vì có lệnh đọc.

Nếu muốn xác minh một subsystem phức tạp theo thời gian, cần một monitor/HealthIndicator có contract riêng, sau đó **quyết định có cần chuyển liveness hay không** dựa trên khả năng phục hồi nội bộ.

### 5.2. Đọc trước sự kiện đầu tiên

Trong các extension point rất sớm, hoặc unit test tạo `ApplicationAvailability` theo cách tùy biến, thông tin state có thể chưa được công bố. API `getState(type)` có thể trả `null`; API với tham số fallback cho phép định nghĩa giá trị dự phòng phù hợp.

Đừng coi `null` là một enum thứ ba của `LivenessState`. Enum chỉ có hai hằng; `null` là **chưa có dữ liệu trong cách đọc API cụ thể**. Khi cần làm việc trong startup rất sớm, xác định rõ điểm đang quan sát và lifecycle thay vì thử suy luận từ một snapshot chưa hoàn chỉnh.

## 6. Cập nhật liveness bằng AvailabilityChangeEvent

Spring Boot cho phép thành phần ứng dụng publish:

```java
AvailabilityChangeEvent.publish(publisher, this, LivenessState.BROKEN);
```

Đoạn này nằm trong một bean có field `ApplicationEventPublisher publisher`. `this` là **source** của event; có thể dùng một object ngoại lệ hoặc một component làm nguồn, nhưng tránh đưa bí mật vào log/metadata.

Có thêm overload:

```java
AvailabilityChangeEvent.publish(applicationContext, LivenessState.BROKEN);
```

Đoạn trên cần một `ApplicationContext applicationContext` thực và chỉ nên gọi khi thật sự có một lỗi nội bộ không thể phục hồi.

Khi sự kiện được phát, Spring Boot có listener quản lý `ApplicationAvailability`; health indicator của Actuator đọc availability này để quyết định kết quả liveness group khi được bật.

### 6.1. Không dùng như một phép gán boolean tùy tiện

Cách làm nguy hiểm:

```java
try {
    remoteApi.call();
} catch (Exception ex) {
    AvailabilityChangeEvent.publish(publisher, ex, LivenessState.BROKEN);
}
```

Đây là **ví dụ phản diện**, giả định `remoteApi` và `publisher` đã tồn tại. Một lỗi mạng/ngắt kết nối ngắn từ dịch vụ ngoài không chứng minh trạng thái nội bộ không thể phục hồi. Đánh dấu `BROKEN` ở đây có thể làm hàng loạt instances bị restart dù tất cả chỉ đang chờ cùng một API.

Cách đúng là đánh giá: lỗi có thể được retry/điều chỉnh readiness/chặn một chức năng không? Nếu có, xử lý theo chính sách tương ứng. Chỉ publish `BROKEN` khi lỗi **không có đường phục hồi an toàn trong instance hiện tại**.

### 6.2. Công bố CORRECT sau khi đã khôi phục?

Spring Boot hỗ trợ publish state thay đổi, nên về API có thể gửi `LivenessState.CORRECT`. Nhưng nếu hệ thống đã đánh dấu một lỗi **không thể tự hồi phục**, tự gửi `CORRECT` ngay sau vài giây mà không có bằng chứng invariant đã phục hồi sẽ làm mất ý nghĩa của liveness.

Hãy phân biệt:

- **Tín hiệu BROKEN bị phát sai:** sửa điều kiện monitor, đánh giá lại trạng thái và xử lý theo vận hành.
- **Một thành phần có thể phục hồi trong process:** thiết kế đó có thể không nên dùng BROKEN ngay từ đầu.
- **Một lỗi thật sự không thể phục hồi:** instance nên được thay thế/restart theo hạ tầng.

Không nên tự viết timer cứ mỗi phút phát lại `CORRECT` để “cho probe xanh” khi lỗi nền tảng còn tồn tại.

## 7. Ví dụ Java 17+ hoàn chỉnh: quan sát CORRECT rồi mô phỏng BROKEN an toàn

Ví dụ này sử dụng một ứng dụng **non-web**. Không mở cổng HTTP, không cấu hình Kubernetes probe và không làm hệ thống production bị restart. Mục tiêu chỉ là **quan sát thứ tự event và trạng thái in-memory** của Spring Boot.

**Yêu cầu:** Java 17+, Spring Boot 3.3.x; project Gradle có Spring Boot plugin, dependency management và `spring-boot-starter`.

**File:** `src/main/java/com/example/availability/LivenessLessonApplication.java`

```java
package com.example.availability;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LivenessLessonApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(LivenessLessonApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            ApplicationAvailability availability =
                    context.getBean(ApplicationAvailability.class);

            System.out.println("4 AFTER_RUN liveness="
                    + availability.getLivenessState());
            System.out.println("5 AFTER_RUN readiness="
                    + availability.getReadinessState());

            boolean simulate = context.getEnvironment()
                    .getProperty("demo.simulate-broken", Boolean.class, false);

            if (simulate) {
                AvailabilityChangeEvent.publish(
                        context, LivenessState.BROKEN);
                System.out.println("7 AFTER_SIMULATION liveness="
                        + availability.getLivenessState());
            }
        }
    }

    @Bean
    ApplicationListener<AvailabilityChangeEvent<LivenessState>>
            livenessEventLogger() {
        return event -> System.out.println(
                (event.getState() == LivenessState.CORRECT
                        ? "1 EVENT_LIVENESS="
                        : "6 EVENT_LIVENESS=")
                + event.getState());
    }

    @Bean
    ApplicationRunner reportRunnerState(
            ApplicationAvailability availability) {
        return arguments -> {
            System.out.println("2 RUNNER liveness="
                    + availability.getLivenessState());
            System.out.println("3 RUNNER readiness="
                    + availability.getReadinessState());
        };
    }
}
```

Đây là **file Java đầy đủ**, trong đó `@SpringBootApplication` tự cấu hình Boot, `@Bean` đăng ký một event listener type-safe và một runner. Tên file đúng với public class.

### 7.1. Vì sao chọn ApplicationListener dạng generic?

`ApplicationListener<AvailabilityChangeEvent<LivenessState>>` giúp Spring phân biệt **LivenessState event** với `AvailabilityChangeEvent<ReadinessState>`. Nhờ đó log trong bài chỉ theo dõi state liveness, không in mọi biến động readiness.

`AvailabilityChangeEvent` cung cấp `ResolvableType` để Spring có thể xét generic event type. Với một bean listener Spring thông thường, loại `LivenessState` có thể được dùng để chọn sự kiện phù hợp; không cần tự cast mọi event sang liveness.

### 7.2. Dependency

Trong project Gradle đã thiết lập plugin Spring Boot 3.3.x và Java 17+, khai báo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Đây là **phần của build.gradle**, không phải toàn bộ build script. Không cần `spring-boot-starter-web` hoặc Actuator cho ví dụ non-web.

Từ thư mục có Gradle Wrapper, chạy:

```bash
./gradlew bootRun
```

Trên Windows CMD là `gradlew.bat bootRun`; PowerShell là `.\gradlew.bat bootRun`.

### 7.3. Kết quả khi không mô phỏng sự cố

Bỏ qua banner và INFO logs của Boot/Gradle. Trong ứng dụng mẫu với một runner và một listener, các dòng do code bài học in ra theo thứ tự kỳ vọng:

```text
1 EVENT_LIVENESS=CORRECT
2 RUNNER liveness=CORRECT
3 RUNNER readiness=REFUSING_TRAFFIC
4 AFTER_RUN liveness=CORRECT
5 AFTER_RUN readiness=ACCEPTING_TRAFFIC
```

Giải thích:

- Dòng 1 xuất hiện sau `ApplicationStartedEvent`, khi Boot công bố liveness `CORRECT`.
- Dòng 2–3 ở runner: app đã được coi live nhưng chưa ready.
- Dòng 4–5 ở main **sau khi `app.run(...)` trả về**, tức Boot đã hoàn tất runner và đã cập nhật readiness.
- Sau đó `try-with-resources` đóng context; không thêm log liveness của ví dụ chỉ vì đóng context.

Không nên hứa rằng toàn bộ log framework luôn xen kẽ theo một thứ tự cố định. Đây là thứ tự **các dòng do chính ví dụ này in** trong đường startup bình thường.

### 7.4. Tùy chọn mô phỏng BROKEN

Để thử thay đổi state **trong một JVM non-web**, dùng:

```bash
./gradlew bootRun --args="--demo.simulate-broken=true"
```

`--args` là tùy chọn của tác vụ `bootRun`/`JavaExec` cho đối số ứng dụng. Trên Windows cũng có thể chạy `gradlew.bat bootRun --args="--demo.simulate-broken=true"`.

Ngoài năm dòng ở mục 7.3, chương trình in thêm:

```text
6 EVENT_LIVENESS=BROKEN
7 AFTER_SIMULATION liveness=BROKEN
```

Điều đó chứng minh:

1. `AvailabilityChangeEvent.publish(context, LivenessState.BROKEN)` phát một event.
2. `ApplicationAvailability` đổi state được quan sát trong cùng context.
3. Do ví dụ là non-web và không có Kubernetes probe, **không có container nào tự restart JVM**. Nó chỉ đóng context theo `try-with-resources` sau khi in xong.

**Không bật cờ mô phỏng này trong ứng dụng production**; đây chỉ là một thí nghiệm minh họa, không phải cơ chế kiểm tra invariant thực tế.

## 8. Ví dụ ứng dụng: phát BROKEN khi một invariant nội bộ thật sự không thể khôi phục

Trong ứng dụng thực, một component hiểu rõ tính đúng đắn của hệ thống nên quyết định việc báo `BROKEN`. Một mẫu code hoàn chỉnh cho **cơ chế báo lỗi**:

**File:** `src/main/java/com/example/availability/LocalInvariantFailureReporter.java`

```java
package com.example.availability;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public final class LocalInvariantFailureReporter {

    private final ApplicationEventPublisher publisher;

    public LocalInvariantFailureReporter(
            ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void reportUnrecoverableState(Throwable cause) {
        if (cause == null) {
            throw new IllegalArgumentException("cause must not be null");
        }

        AvailabilityChangeEvent.publish(
                publisher, cause, LivenessState.BROKEN);
    }
}
```

Class này **biên dịch trong project Spring Boot 3.3 đã cấu hình starter**, nhưng không tự gây lỗi; một thành phần phát hiện invariant hỏng phải **chủ động gọi** `reportUnrecoverableState(cause)`. Việc phân loại lỗi thành “unrecoverable” là **trách nhiệm thiết kế ứng dụng**, không được class này tự đoán dựa trên loại Throwable.

Ví dụ sử dụng trong một component khác:

```java
try {
    localCoordinator.verifyInvariant();
} catch (IrrecoverableStateException ex) {
    failureReporter.reportUnrecoverableState(ex);
}
```

Đây là **đoạn minh họa**, không phải file đầy đủ: `localCoordinator`, `failureReporter` và `IrrecoverableStateException` phải có trong project. Nó chỉ có ý nghĩa khi lỗi này thật sự không có chiến lược khôi phục an toàn bên trong process.

### 8.1. Tại sao không xử lý mọi Exception như BROKEN?

- Thất bại I/O có thể là tạm thời.
- Timeout có thể do một dependency bên ngoài.
- ValidationException có thể là lỗi dữ liệu của một request.
- Một task riêng thất bại không nhất thiết làm mọi subsystem của ứng dụng hỏng.
- `InterruptedException` có thể là tín hiệu dừng có chủ đích.
- Một cache có thể xây lại được thì nên thử khôi phục theo chính sách phù hợp.

Đặt trách nhiệm phát `BROKEN` ở lớp hiểu **mức nghiêm trọng và khả năng phục hồi** của lỗi, có test và log có chọn lọc. Không đặt trong một `catch (Exception)` bao quanh mọi endpoint chỉ để làm liveness chuyển đỏ.

## 9. Cách nghe AvailabilityChangeEvent một cách type-safe

Với sự kiện Spring Boot availability, có hai hướng phổ biến:

**Hướng 1 — `@EventListener` trong bean:**

```java
@Component
public class LivenessAudit {

    @EventListener
    public void onLiveness(AvailabilityChangeEvent<LivenessState> event) {
        System.out.println("Liveness changed: " + event.getState());
    }
}
```

Đây là **class minh họa** cần import `Component`, `EventListener`, `AvailabilityChangeEvent`, `LivenessState`. Bạn có thể đặt class vào package được quét component.

**Hướng 2 — `ApplicationListener` như ví dụ hoàn chỉnh phần 7:**

```java
@Bean
ApplicationListener<AvailabilityChangeEvent<LivenessState>> listener() {
    return event -> System.out.println(event.getState());
}
```

Đây là snippet trong class có `@Configuration` hoặc `@SpringBootApplication`; cần import `Bean`, `ApplicationListener` và các type availability. Hai phương án trên là **lựa chọn thay thế** nếu bạn chỉ muốn một lần log mỗi event; không nên đăng ký cả hai và rồi hiểu nhầm hai dòng log là hai event.

Lưu ý: nếu cần bắt những sự kiện **trước khi BeanFactory đã tạo bean listener**, hãy đăng ký listener với `SpringApplication` sớm hơn. Nhưng sự kiện `CORRECT` mặc định sau started đến khi context đã refresh, nên một bean listener phù hợp có thể nhận được.

### 9.1. Cẩn thận trong hệ thống nhiều ApplicationContext

Sự kiện phát trong context con có thể được chuyển lên listeners ở ancestor contexts. Khi bạn quản lý hierarchy, một listener cha có thể nhận `AvailabilityChangeEvent` của child. Nếu một action chỉ thuộc context hiện tại, hãy thiết kế filter theo context hoặc nguồn event có contract rõ ràng; **không** mặc nhiên suy luận `event.getSource()` luôn là application context cho mọi `AvailabilityChangeEvent`, vì overload publish có thể nhận source tùy ý như exception/component.

Với mọi event mang state, đừng chỉ xem `CORRECT`/`BROKEN` mà bỏ qua **instance nào đã phát** và **event thuộc loại availability nào**.

## 10. Liveness và Spring Boot Actuator

Thêm Actuator để đưa availability ra hệ thống giám sát:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Hai dependencies trên là phương án cho **một ứng dụng web riêng** hoặc cấu hình thay thế ví dụ `NONE`; **không chỉ thêm starter-web vào ví dụ phần 7 rồi mong mở server**, vì main của ví dụ đã ép `WebApplicationType.NONE`. Với ứng dụng web thực tế, không ép `NONE`.

Trong `src/main/resources/application.properties`:

```properties
server.port=8080

# Bật health groups liveness/readiness cả ngoài Kubernetes.
management.endpoint.health.probes.enabled=true

# Xuất thêm các probe trên port chính:
management.endpoint.health.probes.add-additional-paths=true
```

Lưu ý `spring-boot-starter-actuator` phải có trên classpath, health endpoint phải được enable/expose theo cấu hình và policy bảo mật thực tế. Trong Kubernetes, Spring Boot tự bật các probe health groups theo phát hiện môi trường; cấu hình `enabled=true` ở trên giúp thí nghiệm được ở local.

### 10.1. Endpoint nào phản ánh liveness?

Spring Boot dùng `LivenessStateHealthIndicator` cho liveness health group; endpoint mặc định khi được bật:

```text
GET /actuator/health/liveness
```

Với `management.endpoint.health.probes.add-additional-paths=true`, nó còn được xuất qua **port của HTTP server chính** tại:

```text
GET /livez
```

Tương tự readiness là `/actuator/health/readiness` và `/readyz`. Các path bổ sung hữu ích nếu actuator chạy ở management port riêng: probe trên port chính giảm nguy cơ management endpoint xanh nhưng web server phục vụ request thật đang hỏng.

Thử ở một **ứng dụng web** đã bật probes:

```bash
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
```

Khi ứng dụng chạy bình thường và không đổi các health mappings, response liveness thường là:

```http
HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
```

Đây là **minh họa rút gọn** của status/body. Header `Content-Type` chính xác và một số header khác phụ thuộc phiên bản và HTTP negotiation. Khi state `BROKEN`, liveness indicator thông thường chuyển kết quả group sang `DOWN`; mặc định HTTP status của `DOWN` được ánh xạ thành **503 Service Unavailable**.

Không coi một request lỗi vì **không mở được TCP connection** là bằng chứng liveness enum đang `BROKEN`. Server có thể chưa start, đã shutdown, cổng/path sai, security policy chặn hoặc network đang lỗi.

### 10.2. Global health khác health group liveness

`/actuator/health` có thể tổng hợp nhiều `HealthIndicator`, gồm database và các subsystem khi các thư viện liên quan có mặt. Không nên cấu hình `livenessProbe` của Kubernetes trỏ thẳng vào **global health** nếu global health chứa external dependencies.

`/actuator/health/liveness` hoặc `/livez` được thiết kế cho **liveness state**, không mặc định kéo mọi indicator của hệ thống ngoài vào. Hãy giữ sự khác biệt này khi làm dashboard và cấu hình probe.

### 10.3. Liveness state và actual probe khác nhau

`ApplicationAvailability` là trạng thái trong bộ nhớ. HTTP probe cần thêm:

- Một HTTP server đã được tạo, đang nhận kết nối.
- Route/Actuator health group được bật và expose.
- Đúng port, path, scheme, network policy và security.
- Request đến đúng instance.
- Các ngưỡng timeout/failure được orchestrator thiết lập.

Ví dụ app có state `CORRECT` nhưng web server bị kẹt đến mức kubelet không thể gọi endpoint: **probe vẫn có thể thất bại**, và hạ tầng có thể quyết định restart dù bộ nhớ Spring đang lưu `CORRECT`.

Ngược lại, nếu probe chạy trên **management port riêng** và port chính hỏng, probe có thể trả 200 trong khi traffic thực không được phục vụ. Đây là lý do nên cân nhắc các path `/livez`, `/readyz` trên cổng chính.

## 11. Kubernetes: dùng livenessProbe, readinessProbe và startupProbe

Một phần cấu hình container trong Kubernetes Pod/Deployment có thể dùng:

```yaml
containers:
  - name: application
    image: example/my-service:1.0
    ports:
      - containerPort: 8080
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
    startupProbe:
      httpGet:
        path: /livez
        port: 8080
      periodSeconds: 5
      failureThreshold: 30
```

Đây là **đoạn YAML thuộc `spec.containers`**, không phải một file Deployment độc lập. Nó giả định ứng dụng web có HTTP server cổng 8080 và đã bật thêm path `/livez`/`/readyz` như mục 10. Image là ví dụ về cấu trúc triển khai; thay bằng image thật của dự án nếu sử dụng.

**Ý nghĩa từng loại probe:**

- `livenessProbe` thất bại đủ ngưỡng: kubelet có thể restart container theo chính sách nền tảng.
- `readinessProbe` thất bại: container không được coi là ready để nhận traffic qua Service, nhưng không vì vậy mà lập tức bị restart.
- `startupProbe`: nếu cấu hình, cho phép ứng dụng có thêm thời gian startup trước khi liveness/readiness probes bắt đầu có hiệu lực, tránh bị kill khi startup còn chậm.

Các giá trị thời gian trong YAML chỉ để **minh họa**, phải đo startup thực tế, thời gian GC, tải CPU và yêu cầu hệ thống trước khi áp dụng. Một `startupProbe` quá ngắn vẫn có thể giết pod lúc ứng dụng chưa kịp refresh; một probe quá dễ dãi có thể để instance bị kẹt lâu mà không xử lý.

### 11.1. Tại sao không thêm database check vào livenessProbe?

Giả sử 20 pod dùng chung một database. Database tạm unavailable:

1. Nếu liveness phụ thuộc DB, cả 20 pod cùng bị coi không live.
2. Kubelet có thể restart hàng loạt pod.
3. Mỗi pod khởi động lại, tạo pool và thử kết nối DB cùng lúc.
4. Database càng chịu tải, hệ thống dễ rơi vào vòng lặp khởi động thất bại.

Đó là **cascading failure**. Một lỗi external dependency thường không được sửa bằng cách restart tất cả instance, nên Spring Boot khuyến nghị **không dùng external checks trong liveness**.

Readiness có thể xét dependency ngoài **một cách chọn lọc** nếu việc mất dependency khiến instance không thể xử lý traffic an toàn. Nhưng nếu dependency đó được chia sẻ cho tất cả pods, đưa nó vào readiness cũng có thể loại toàn bộ instances khỏi Service. Cần quyết định theo kiến trúc và cách xử lý lỗi thực tế.

## 12. Khi nào nên phát BROKEN trong nghiệp vụ?

Một bảng quyết định thực hành:

| Tình huống | Liveness nên làm gì? | Lý do |
| --- | --- | --- |
| Một HTTP request trả 400 do input không hợp lệ | Giữ `CORRECT` | Request lỗi không làm instance hỏng |
| Database timeout, có retry và circuit breaker | Thường giữ `CORRECT` | Lỗi external/recoverable |
| Mất kết nối message broker nhưng consumer có thể reconnect | Thường giữ `CORRECT` | Hệ thống có đường phục hồi |
| Hàng đợi nội bộ tạm đầy, ứng dụng vẫn phục vụ phần khác | Thường giữ `CORRECT`; cân nhắc readiness/load shedding | Quá tải tạm thời không phải corrupt |
| Local in-memory state corrupt không thể rebuild | Cân nhắc `BROKEN` | Không bảo đảm tính đúng đắn trong instance |
| Một thread critical chết và không có cơ chế tái tạo | Cân nhắc `BROKEN` | Có thể cần restart để phục hồi |
| Một background job đơn lẻ thất bại nhưng có retry | Giữ `CORRECT` | Chưa mất khả năng phục hồi tổng thể |
| Ứng dụng đang chạy migration/startup runner | Thường vẫn `CORRECT` sau started, readiness chưa accepting | Startup đang hoàn tất công việc |
| Đang graceful shutdown | Liveness có thể còn `CORRECT`; readiness chuyển refusing | Không nên nhận traffic mới, không nhất thiết bị lỗi nội bộ |
| JVM deadlock khiến không thể phục vụ probe | Probe có thể thất bại dù không kịp publish BROKEN | Hạ tầng phát hiện từ network/timeout |

**Quy tắc phân loại lỗi:** hỏi “Nếu giữ nguyên process và đợi/khôi phục/retry, instance có thể phục vụ đúng trở lại không?”. Nếu câu trả lời đáng tin là **có**, thường chưa nên báo `BROKEN`. Nếu câu trả lời là **không**, và restart thật sự có khả năng làm mới trạng thái cần thiết, `BROKEN` là một tín hiệu phù hợp.

Không phải mọi tình huống chỉ có hai lựa chọn: có thể dùng circuit breaker, failover, readiness, bounded retry hoặc khởi động lại một component riêng thay vì restart cả ứng dụng.

## 13. BROKEN và restart: trách nhiệm của ứng dụng và nền tảng

Khi app publish `BROKEN`, nó **báo tín hiệu** chứ không thực thi restart. Với Kubernetes:

```text
Ứng dụng phát AvailabilityChangeEvent(BROKEN)
          |
ApplicationAvailability cập nhật liveness
          |
LivenessStateHealthIndicator -> DOWN
          |
/livez trả HTTP 503 (nếu endpoint/server còn truy cập được)
          |
Kubelet gọi livenessProbe theo chu kỳ
          |
Đủ số lần thất bại theo failureThreshold
          |
Kubelet restart container
          |
Instance mới khởi động lại từ startup lifecycle
```

Đây là luồng **điển hình** khi cấu hình probe hợp lệ, không phải guarantee mọi lần publish event đều chắc chắn restart. Thực tế có thể bị ảnh hưởng bởi network, pod lifecycle, container restart policy, cấu hình timeout và trạng thái node.

### 13.1. Không nhầm readiness và restart

Readiness thất bại là lời khuyên **đừng gửi traffic mới đến instance này**. Kubernetes không tự restart chỉ vì readiness false. Ngược lại, liveness thất bại đủ ngưỡng là một tín hiệu đề nghị khởi động lại container.

Bởi vậy, một sự cố có thể phục hồi sau vài giây nên tránh đưa vào liveness; dùng readiness hoặc xử lý lỗi ở tầng request nếu phù hợp.

### 13.2. Nếu liveness đã BROKEN thì readiness tự về REFUSING_TRAFFIC?

Không nên giả định như vậy chỉ từ một `AvailabilityChangeEvent<LivenessState>`. Hai loại state được theo dõi độc lập. Một ứng dụng có thể đã công bố `ReadinessState.ACCEPTING_TRAFFIC` trước đó, rồi mới chuyển liveness sang `BROKEN`. Trong khoảng thời gian trước khi kubelet xử lý probe, hành vi nhận traffic còn phụ thuộc server và readiness hiện tại.

Nếu sự cố nghiêm trọng cũng khiến instance không nên nhận công việc mới, thiết kế **chuyển readiness sang REFUSING_TRAFFIC** hoặc cơ chế ngừng nhận traffic phù hợp. Đừng dựa vào liveness enum như một khóa đồng bộ tự động chặn request. Đồng thời đừng làm phức tạp việc xử lý fatal failure bằng những callback có thể tự kẹt.

## 14. Quan hệ với ApplicationContext, SmartLifecycle và shutdown

`LivenessState` là khái niệm **Spring Boot availability**, không phải alias của:

- `ConfigurableApplicationContext.isActive()`.
- `ConfigurableApplicationContext.isRunning()`.
- `SmartLifecycle.isRunning()` của một bean.
- `ContextRefreshedEvent` hay `ContextClosedEvent`.
- PID JVM hoặc process health của container.

Một context active có thể đi kèm trạng thái liveness `BROKEN` nếu ứng dụng công bố một lỗi nội bộ không thể khôi phục **sau** startup. Ngược lại, trong giai đoạn bootstrap rất sớm, liveness mặc định chưa `CORRECT` dù JVM đang chạy.

### 14.1. Trong shutdown

Spring Boot thường chuyển readiness sang `REFUSING_TRAFFIC` trong quá trình đóng có trật tự. Khi graceful shutdown đang diễn ra, liveness không nhất thiết chuyển `BROKEN` vì ứng dụng đang dừng **có chủ đích**, chứ không phải do lỗi không thể tự phục hồi.

Sau khi context đã đóng và HTTP server ngừng, endpoint probe có thể không còn truy cập được; trạng thái enum cuối cùng trong bộ nhớ không phải thứ cần đo khi process đã dừng.

### 14.2. Một SmartLifecycle bean ngừng chạy có luôn là BROKEN?

Không. Có `SmartLifecycle` ngừng theo chính sách quản lý, theo yêu cầu shutdown, hoặc do việc không còn dữ liệu cần xử lý. Ngay cả một failure của component quan trọng cũng có thể được phục hồi bằng cách start lại hoặc tái tạo instance. Chỉ sau khi đánh giá đó là **lỗi không thể phục hồi** mới có cơ sở công bố `BROKEN`.

### 14.3. Probe có phát hiện mọi deadlock không?

Không có một probe duy nhất phát hiện mọi lỗi. Nếu HTTP event loop hoặc thread pool xử lý request bị tắc hoàn toàn, probe trên chính port đó có thể timeout dù trạng thái in-memory vẫn `CORRECT`; điều này có thể kích hoạt restart. Ngược lại, nếu probe chạy qua một management server hoàn toàn tách biệt, nó có thể thành công trong khi port chính không còn xử lý được request. Vì vậy **đường đi của probe** cũng là một phần của thiết kế liveness đáng tin cậy.

## 15. Kiểm thử đúng cơ chế liveness

Có ba lớp kiểm thử nên phân biệt.

### 15.1. Unit test logic phân loại unrecoverable

Đưa quyết định “có nên báo BROKEN?” vào một class policy có thể kiểm thử bằng đầu vào: loại lỗi, số lần retry, trạng thái invariant, khả năng tự khôi phục. Test rằng:

- Lỗi request nghiệp vụ bình thường không phát BROKEN.
- Lỗi external dependency có thể retry không phát BROKEN.
- Vi phạm invariant không thể khôi phục phát đúng một lần theo thiết kế.
- Không log token hoặc dữ liệu nhạy cảm.

Không cần khởi động Kubernetes để test logic chọn state.

### 15.2. Integration test ApplicationAvailability

Trong một integration test có context Spring Boot thật, inject `ApplicationAvailability` và `ApplicationEventPublisher`, publish `AvailabilityChangeEvent` với `LivenessState.BROKEN`, rồi xác nhận `getLivenessState()` tương ứng.

Nếu test cần có HTTP health group, dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và Actuator để gọi đúng endpoint. Không dùng một test làm BROKEN ảnh hưởng các test khác đang **reuse cached context** rồi khiến tình trạng availability bị rò sang test kế tiếp; cô lập context hoặc phục hồi trạng thái có chủ đích trong phạm vi test.

### 15.3. Integration test HTTP và Kubernetes

Kiểm tra:

1. Health groups đã bật, đúng port/path.
2. `/livez` báo UP sau started với cấu hình bình thường.
3. Health group trả DOWN/503 khi có sự cố nội bộ được mô phỏng trong môi trường test.
4. `/readyz` tách biệt và phản ánh startup/điều kiện nhận traffic.
5. StartupProbe cho phép ứng dụng startup chậm thực tế.
6. Kubelet restart khi liveness failures liên tiếp **đúng ngưỡng**.
7. Không tạo restart storm khi một dependency dùng chung gặp lỗi.
8. Readiness false không bị nhầm thành liveness failure.
9. Probe trên port chính phát hiện tình trạng port chính không nhận request.
10. Sau restart, instance thật sự có thể hồi phục; nếu không, cần điều tra nguyên nhân gốc thay vì tăng số lần restart.

**Không thử BROKEN trên production để “xem pod có restart không”** nếu chưa có kế hoạch thử nghiệm và cô lập ảnh hưởng. Dùng staging hoặc test environment có chính sách kiểm soát.

## 16. Lỗi phổ biến và cách sửa

| Lỗi hoặc hiểu nhầm | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| “Mất database là liveness BROKEN” | Dependency ngoài thất bại có thể khiến mọi pod restart | Giữ liveness chỉ cho lỗi nội bộ không thể tự phục hồi |
| “CORRECT nghĩa là mọi request 200” | Liveness không đo thành công của từng request | Dùng metrics, health, readiness và error handling phù hợp |
| “CORRECT nghĩa là đã ready” | Runner có thể chưa xong | Đọc `ReadinessState` và readiness probe |
| “BROKEN tự làm JVM exit” | Chỉ cập nhật availability state | Cần orchestrator/probe/restart policy hoặc chủ động shutdown theo thiết kế |
| “Readiness fail thì kubelet restart” | Readiness chỉ loại instance khỏi traffic | Phân biệt hai loại probe |
| “Liveness được set BROKEN ngay startup là lỗi” | Trạng thái bảo vệ trước khi công bố live | Quan sát mốc `ApplicationStartedEvent`/`CORRECT` |
| “Chỉ cần có Actuator là /livez xuất hiện” | Cần cấu hình additional paths nếu muốn /livez | Bật `management.endpoint.health.probes.add-additional-paths=true` |
| “Health toàn cục là liveness” | Global health có thể gồm database/external checks | Dùng `/actuator/health/liveness` hoặc `/livez` |
| “Probe 200 trên management port là port chính cũng khỏe” | Hai port có hạ tầng riêng | Cân nhắc probe trên server port chính |
| “BROKEN và REFUSING_TRAFFIC luôn tự đồng bộ” | Hai trạng thái khác nhau | Công bố readiness/điều phối ngừng traffic phù hợp |
| “Đọc getLivenessState sẽ tự ping mọi dependency” | API trả state hiện hành trong bộ nhớ | Viết monitor/indicator riêng đúng phạm vi |
| “@EventListener nhận mọi availability event là liveness” | Có cả `AvailabilityChangeEvent<ReadinessState>` | Dùng generic type cụ thể |
| “@PostConstruct là chỗ công bố CORRECT” | Thời điểm quá sớm, Boot còn startup | Để Boot tự quản lý state mặc định |
| “BROKEN là giải pháp cho tất cả lỗi không rõ nguyên nhân” | Restart có thể che lỗi và tạo vòng lặp | Chẩn đoán, phân loại phục hồi, dùng backoff và logging |
| “Mọi pod cùng lỗi thì restart mọi pod là tốt” | Có thể khuếch đại sự cố chung | Loại kiểm tra dependency ngoài khỏi liveness |
| “Chỉ cần tăng initialDelaySeconds vô hạn” | Che vấn đề startup, làm chậm phát hiện lỗi | Đo thời gian startup và cân nhắc startupProbe |
| “Một probe xanh nghĩa mọi luồng bên trong chạy đúng” | Probe chỉ đo trạng thái/đường đi của nó | Kết hợp metrics, traces, thread dumps và kiểm tra subsystem |
| “Đánh dấu CORRECT liên tục sẽ sửa được lỗi” | Chỉ thay tín hiệu | Sửa nguyên nhân hoặc restart theo chính sách đúng |

## 17. Kịch bản thiết kế: phân biệt lỗi có thể phục hồi và lỗi fatal

### Kịch bản A — mất mạng tới đối tác

Một REST service gọi API đối tác bằng HTTP client. Đối tác mất kết nối 20 giây. Service có retry giới hạn và circuit breaker. Những request lệ thuộc đối tác có thể thất bại, nhưng process vẫn hoạt động đúng.

**Quyết định:** thường giữ `LivenessState.CORRECT`; đánh giá readiness theo tác động thực tế, dùng timeout/circuit breaker và observability để theo dõi.

### Kịch bản B — corrupt một bảng state chỉ lưu trong RAM

Một engine điều phối chỉ có thể hoạt động nếu một đồ thị in-memory bảo đảm invariant xác định. Engine phát hiện cấu trúc đã hỏng và việc rebuild trong process không an toàn; nếu tiếp tục xử lý sẽ tạo quyết định sai.

**Quyết định:** công bố `BROKEN` có thể đúng vì restart có thể tạo lại state sạch. Đồng thời log nguyên nhân, tránh để các request mới được xử lý sai và xác minh restart thật sự sửa được lỗi.

### Kịch bản C — tạm quá tải hàng đợi nội bộ

Queue in-memory đầy nhưng có khả năng giảm tải sau vài giây, cho phép từ chối công việc mới và tiếp tục xử lý những việc đang chờ.

**Quyết định:** đây thường là **load shedding/readiness** chứ không phải `BROKEN`.

### Kịch bản D — startup mất nhiều phút

Một runner tải dữ liệu ban đầu. Context refresh đã hoàn tất và Boot công bố `CORRECT`, nhưng readiness vẫn từ chối cho tới khi runner xong. Một kubelet có thể thử probe trước khi HTTP endpoint sẵn sàng.

**Quyết định:** cấu hình startupProbe hợp lý nếu thời gian startup dài; đừng bỏ startup work bắt buộc chỉ để liveness xanh nhanh hơn.

### Kịch bản E — deadlock ngăn cả HTTP probe

Ứng dụng không có cơ hội publish `BROKEN` vì những thread cốt lõi đã bị kẹt. Kubelet không truy cập được HTTP probe, ghi nhận timeouts và restart nếu vượt ngưỡng.

**Quyết định:** đây là một lý do phải quan sát **actual probe**, không chỉ trông chờ event in-memory. Sau đó cần tìm nguyên nhân deadlock, không coi restart là sửa tận gốc.

## 18. Câu hỏi tự kiểm tra

**1. LivenessState có mấy giá trị?**

Hai: `CORRECT` và `BROKEN`. Không có enum `STARTING` hoặc `UNKNOWN` trong `LivenessState` của Spring Boot 3.3.

**2. BROKEN có nghĩa database đang down?**

Không. BROKEN diễn tả trạng thái **nội bộ không thể tự phục hồi**, không phải kết quả check một dependency ngoài.

**3. Khi nào Boot công bố CORRECT trong startup mặc định?**

Ngay sau `ApplicationStartedEvent`, tức sau refresh và trước `ApplicationRunner`/`CommandLineRunner`.

**4. Tại sao CORRECT và REFUSING_TRAFFIC cùng xuất hiện?**

Vì liveness và readiness độc lập: container đã chạy đúng, nhưng startup tasks hoặc điều kiện nhận traffic chưa hoàn tất.

**5. Publish AvailabilityChangeEvent(BROKEN) có khởi động lại process ngay không?**

Không. Nó cập nhật state in-memory; restart cần cơ chế giám sát/điều phối phù hợp, ví dụ kubelet với livenessProbe.

**6. Có nên đưa DB HealthIndicator vào liveness group không?**

Thông thường không. Một lỗi DB dùng chung có thể khiến toàn bộ instances restart và khuếch đại sự cố.

**7. Sự khác nhau giữa /actuator/health và /actuator/health/liveness là gì?**

Global health có thể gồm nhiều indicators; liveness group dành riêng để đánh giá trạng thái liveness, không mặc định kéo toàn bộ dependency checks vào.

**8. /livez có luôn tồn tại khi thêm Actuator không?**

Không. Đây là additional path trên main HTTP port khi cấu hình probes/additional paths phù hợp.

**9. Liveness BROKEN có tự đặt readiness REFUSING_TRAFFIC không?**

Không nên giả định. Hai trục trạng thái được theo dõi riêng và có thể cần phối hợp khi xử lý fatal failure.

**10. Một lỗi validation từ người dùng có nên làm instance BROKEN không?**

Không, lỗi dữ liệu một request không làm hỏng trạng thái nội bộ của ứng dụng.

## 19. Checklist vận hành

1. Xác định invariant nội bộ nào thực sự làm một instance **không thể tự phục hồi**.
2. Định nghĩa rõ owner phát sự kiện `BROKEN` và trường hợp không được phát.
3. Không đưa HealthIndicator của database, API ngoài hoặc cache ngoài vào liveness một cách tùy tiện.
4. Đọc `ApplicationAvailability` như snapshot, không coi là công cụ chủ động kiểm tra toàn hệ thống.
5. Quan sát đúng thứ tự `ApplicationStartedEvent → CORRECT → runners → ApplicationReadyEvent → readiness accepting`.
6. Dùng `ReadinessState`/readinessProbe khi cần tạm ngừng nhận traffic thay vì restart.
7. Thiết kế xử lý lỗi, backoff và circuit breaker cho sự cố external.
8. Nếu dùng Actuator, kiểm tra health groups và endpoint/port/security thật sự.
9. Nếu management server port riêng, cân nhắc `/livez` và `/readyz` trên port chính.
10. Cấu hình livenessProbe timeout/period/failure threshold theo tải thực tế.
11. Cân nhắc startupProbe nếu startup chậm để tránh restart vòng lặp.
12. Không bật chức năng mô phỏng BROKEN trong production.
13. Test fatal state và probe trong staging, kiểm tra restart thực sự có tác dụng.
14. Theo dõi restart count, error logs và root cause; không chỉ tăng ngưỡng để che sự cố.
15. Nếu nhiều `ApplicationContext`, xác minh event thuộc đúng context/instance.
16. Không coi CORRECT là bảo đảm API business đúng hoặc mọi dependency đều online.
17. Không quên graceful shutdown và readiness khi xử lý lỗi fatal.
18. Lưu ý báo BROKEN là quyết định vận hành nghiêm trọng, cần có tiêu chí và test.

## 20. Tóm tắt cần nhớ

```text
                APPLICATION AVAILABILITY
                          |
             +------------+------------+
             |                         |
          LIVENESS                  READINESS
             |                         |
      CORRECT / BROKEN      ACCEPTING / REFUSING
             |                         |
    "Có nên restart?"        "Có nên nhận traffic?"
             |                         |
        Liveness Probe          Readiness Probe
             |                         |
       Restart instance      Loại khỏi routing tạm thời
```

**Ba nguyên tắc thực hành:**

- `CORRECT` nghĩa trạng thái nội bộ của instance được xem là đúng; **không** đồng nghĩa tất cả dependency hoặc request đều khỏe.
- `BROKEN` dùng khi trạng thái nội bộ **không thể tự phục hồi**, để hạ tầng cân nhắc restart; đừng gắn nó với mọi lỗi mạng hay database.
- Readiness và liveness là **hai trục riêng**. Kiểm tra đúng nhóm health và đúng đường HTTP probe, không trộn tất cả phép đo thành một “healthy” duy nhất.

## Tài liệu chính thức

- [Spring Boot 3.3 — SpringApplication, Application Availability và Application Events](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — LivenessState API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/LivenessState.html)
- [Spring Boot 3.3 — ApplicationAvailability API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ApplicationAvailability.html)
- [Spring Boot 3.3 — AvailabilityChangeEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html)
- [Spring Boot 3.3 — Actuator endpoints, Kubernetes probes, external dependencies và availability state](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
