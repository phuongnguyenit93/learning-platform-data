# Quan sát thay đổi qua `AvailabilityChangeEvent`

Trong Spring Boot, việc một ứng dụng **đã tạo xong các bean** không đồng nghĩa với việc ứng dụng **đã sẵn sàng nhận lưu lượng**. Một dịch vụ có thể đang khởi động, đang chạy tác vụ chuẩn bị dữ liệu, tạm ngừng tiếp nhận request để bảo trì, hoặc đang đóng. Để quan sát các mốc này theo cách nhất quán, Spring Boot cung cấp **Application Availability** và các sự kiện **`AvailabilityChangeEvent`**.

Bài học thuộc phần **Trạng thái sẵn sàng** của module **Spring Boot Application Runtime**, tập trung vào **cách lắng nghe, đọc, phát và kiểm chứng các thay đổi liveness/readiness qua sự kiện**. Các API và ví dụ dựa trên **Spring Boot 3.3.x / Spring Framework 6.1, Java 17+**.

Mục tiêu sau khi học:

- Phân biệt **liveness** (ứng dụng có còn ở trạng thái hoạt động đúng/khả năng tự hồi phục?) với **readiness** (có nên nhận traffic ngay lúc này?).
- Hiểu `AvailabilityChangeEvent<S extends AvailabilityState>`, `ApplicationAvailability` và các trạng thái tương ứng.
- Viết listener với `@EventListener` hoặc `ApplicationListener` để quan sát thay đổi.
- Chủ động phát sự kiện `ReadinessState.REFUSING_TRAFFIC` / `ACCEPTING_TRAFFIC` khi một thành phần cần điều chỉnh khả năng nhận traffic.
- Kiểm tra trình tự sự kiện trong vòng đời `SpringApplication.run(...)`, không nhầm log startup hoặc `ApplicationReadyEvent` với readiness hiện tại.
- Biết khi nào trạng thái nội bộ được phản ánh ra probe HTTP của Spring Boot Actuator và Kubernetes.

## 1. Tại sao cần quan sát trạng thái sẵn sàng?

Một hệ thống triển khai nhiều bản sao có thể gặp các tình huống:

1. **Khởi động:** Spring đã refresh context, nhưng một `ApplicationRunner` vẫn tải dữ liệu ban đầu. Ứng dụng đã hoạt động ở mức container song chưa nên nhận lưu lượng.
2. **Hoạt động bình thường:** Các công việc khởi động hoàn tất; ứng dụng có thể phục vụ request.
3. **Tạm ngừng:** Hàng đợi nội bộ vượt ngưỡng hoặc hệ thống đang thực hiện bảo trì ngắn; ứng dụng vẫn sống, nhưng nên ngừng nhận **traffic mới**.
4. **Phục hồi:** Nguyên nhân tạm ngừng được xử lý, ứng dụng có thể nhận traffic trở lại.
5. **Shutdown:** Container chuẩn bị đóng; một cơ chế graceful shutdown sẽ tránh nhận thêm request và cố hoàn tất việc đang xử lý.

Nếu chỉ dựa vào việc cổng TCP đã mở hoặc log `Started ...`, khó phân biệt các trạng thái trên. Spring Boot vì thế cho phép biểu diễn **liveness** và **readiness** ở cấp ứng dụng, và dùng sự kiện để thông báo chúng thay đổi.

Phải phân biệt **trạng thái được công bố** với **khả năng kiểm chứng bên ngoài**. Đặt readiness `REFUSING_TRAFFIC` không tự làm mọi reverse proxy hay client ngừng gửi request ngay lập tức. Hạ tầng (ví dụ Kubernetes) phải cấu hình và kiểm tra readiness probe, rồi cập nhật việc định tuyến; có độ trễ giữa sự kiện nội bộ và tác động trên mạng.

## 2. Hai chiều của Application Availability

### Liveness: `LivenessState`

`org.springframework.boot.availability.LivenessState` có hai giá trị:

| Giá trị | Ý nghĩa | Hệ quả vận hành thường mong muốn |
| --- | --- | --- |
| `CORRECT` | Trạng thái nội bộ cho phép ứng dụng tiếp tục hoạt động đúng hoặc có khả năng tự phục hồi | Liveness probe nên thành công |
| `BROKEN` | Ứng dụng hỏng ở mức nội bộ mà không tự hồi phục được | Hạ tầng có thể cần khởi động lại tiến trình |

**Không lấy mọi lỗi kết nối đến cơ sở dữ liệu, Redis hoặc một API bên ngoài làm lý do chuyển liveness sang `BROKEN`.** Phụ thuộc chung của nhiều instance bị lỗi có thể dẫn tới việc hạ tầng liên tục restart toàn bộ instance và khuếch đại sự cố. Liveness dành cho tình trạng nghiêm trọng **của chính tiến trình**.

### Readiness: `ReadinessState`

`org.springframework.boot.availability.ReadinessState` có hai giá trị:

| Giá trị | Ý nghĩa | Hệ quả vận hành thường mong muốn |
| --- | --- | --- |
| `ACCEPTING_TRAFFIC` | Ứng dụng tự xác nhận có thể phục vụ lưu lượng mới | Readiness probe có thể cho phép điều phối traffic |
| `REFUSING_TRAFFIC` | Tạm thời không nên đưa thêm lưu lượng mới tới ứng dụng | Readiness probe nên báo chưa sẵn sàng |

Readiness có thể thay đổi trong **cùng một tiến trình**: từ `REFUSING_TRAFFIC` sang `ACCEPTING_TRAFFIC` sau startup, rồi trở về `REFUSING_TRAFFIC` lúc bảo trì, và phục hồi `ACCEPTING_TRAFFIC` mà không cần restart.

### Liveness không phải readiness

~~~text
Ứng dụng vẫn sống nhưng chưa sẵn sàng:
Liveness = CORRECT
Readiness = REFUSING_TRAFFIC

Ứng dụng đang phục vụ bình thường:
Liveness = CORRECT
Readiness = ACCEPTING_TRAFFIC
~~~

Hai chiều này độc lập về ý nghĩa. **Một instance sống nhưng từ chối traffic là trạng thái hoàn toàn hợp lệ**, đặc biệt trong startup hoặc quá trình tạm ngừng có kiểm soát.

## 3. `AvailabilityChangeEvent` là gì?

`AvailabilityChangeEvent<S extends AvailabilityState>` thuộc package:

~~~java
org.springframework.boot.availability
~~~

Đây là một `ApplicationEvent` mang theo một trạng thái `S`, trong đó `S` triển khai giao diện `AvailabilityState`. Với Spring Boot 3.3, class này mở rộng `PayloadApplicationEvent<S>`.

Các thao tác đáng chú ý:

| API | Vai trò |
| --- | --- |
| `event.getState()` | Đọc giá trị liveness/readiness được đưa vào sự kiện |
| `event.getSource()` | Nguồn phát của sự kiện, tùy cách tạo/publish |
| `AvailabilityChangeEvent.publish(context, state)` | Gửi event qua một `ApplicationContext` |
| `AvailabilityChangeEvent.publish(publisher, source, state)` | Gửi qua `ApplicationEventPublisher` với nguồn do caller chỉ định |

Ví dụ ý tưởng:

~~~java
AvailabilityChangeEvent.publish(
        context, ReadinessState.REFUSING_TRAFFIC);
~~~

Đoạn trên cần biến `context` là một `ApplicationContext` đang hoạt động và các import Spring Boot thích hợp; đây chưa phải một chương trình chạy độc lập.

**Cần phân biệt sự kiện và trạng thái hiện tại:**

- Sự kiện là **thông điệp tại một thời điểm**: “Có người vừa công bố giá trị `REFUSING_TRAFFIC`”.
- Trạng thái hiện tại là **giá trị được giữ lại để tra cứu** qua `ApplicationAvailability`.
- Nếu bỏ lỡ sự kiện vì listener được đăng ký muộn, ta **không** tự nhận lại toàn bộ lịch sử sự kiện. Khi chỉ cần trạng thái mới nhất, hỏi `ApplicationAvailability`.
- Tên “change event” không có nghĩa framework từ chối phát hai sự kiện liên tiếp mang cùng một giá trị. Code phát event phải tự cân nhắc trùng lặp và tính idempotent nếu hành động của listener có tác dụng phụ.

Event là phương tiện truyền trạng thái **trong ứng dụng**, không phải một message broker phân tán và không thay thế tín hiệu/probe từ hạ tầng.

## 4. `ApplicationAvailability` lưu trạng thái mới nhất như thế nào?

`ApplicationAvailability` là giao diện có thể inject vào bean để hỏi trạng thái hiện tại. Spring Boot cung cấp `ApplicationAvailabilityBean` làm triển khai thu nhận các sự kiện thay đổi và lưu giá trị cuối cho từng loại trạng thái.

Các API chính:

~~~java
LivenessState liveness = availability.getLivenessState();
ReadinessState readiness = availability.getReadinessState();

ReadinessState state = availability.getState(ReadinessState.class);
AvailabilityChangeEvent<ReadinessState> lastEvent =
        availability.getLastChangeEvent(ReadinessState.class);
~~~

Trong đó `availability` là biến kiểu `ApplicationAvailability` đã được inject. Đoạn trên là **ví dụ về API bên trong một phương thức**, không phải một file Java độc lập.

- `getLivenessState()` / `getReadinessState()`: đọc trạng thái theo hai chiều thông dụng.
- `getState(ReadinessState.class)`: có thể trả `null` nếu loại trạng thái này chưa từng được công bố qua event, tùy hợp đồng API.
- `getState(ReadinessState.class, ReadinessState.REFUSING_TRAFFIC)`: truyền một **fallback** nếu chưa có event loại đó.
- `getLastChangeEvent(ReadinessState.class)`: đọc **sự kiện gần nhất** cho loại trạng thái, có thể chưa có nếu ứng dụng chưa công bố event tương ứng.

Lưu ý: trạng thái mặc định/hành vi fallback khác với việc đã từng có một event. Khi ứng dụng mới bắt đầu, `getLastChangeEvent(...)` có thể chưa có giá trị dù một phương thức đọc trạng thái có giá trị mặc định hợp lý. **Không suy ra rằng mọi giá trị mặc định đều đã được phát bằng `AvailabilityChangeEvent`.**

### Đừng cập nhật implementation lưu trữ trực tiếp

Để báo trạng thái mới, Spring Boot hướng dẫn **phát `AvailabilityChangeEvent`**, thay vì tìm cách sửa trường nội bộ của `ApplicationAvailabilityBean`. Khi công bố event, cả những listener khác và thành phần theo dõi trạng thái đều có cơ hội biết thay đổi.

~~~java
AvailabilityChangeEvent.publish(
        eventPublisher, this, ReadinessState.REFUSING_TRAFFIC);
~~~

Trong đó `eventPublisher` là `ApplicationEventPublisher` được inject. Event có thể được nhiều bên lắng nghe; nên chỉ publish khi thực sự có lý do nghiệp vụ/vận hành rõ ràng.

## 5. Thứ tự sự kiện availability trong khởi động Spring Boot

Theo tài liệu Spring Boot 3.3, luồng thành công liên quan trực tiếp đến liveness/readiness là:

~~~text
main()
 |
 v
SpringApplication.run(args)
 |
 +-- Chuẩn bị Environment và ApplicationContext
 |
 +-- Refresh ApplicationContext
 |
 +-- ApplicationStartedEvent
 |
 +-- AvailabilityChangeEvent<LivenessState>
 |      state = CORRECT
 |
 +-- ApplicationRunner và CommandLineRunner
 |
 +-- ApplicationReadyEvent
 |
 +-- AvailabilityChangeEvent<ReadinessState>
 |      state = ACCEPTING_TRAFFIC
 |
 v
run(args) trả về ApplicationContext
~~~

Đây là **thứ tự mốc** để quan sát, không cố liệt kê mọi sự kiện, callback bean hoặc khởi tạo máy chủ web khác.

Bảng trạng thái điển hình:

| Giai đoạn | Liveness | Readiness | Điều kiện |
| --- | --- | --- | --- |
| Đang bắt đầu | `BROKEN` | `REFUSING_TRAFFIC` | Context chưa được refresh |
| Context đã refresh, đang xử lý runner | `CORRECT` | `REFUSING_TRAFFIC` | Đã qua mốc started nhưng chưa qua ready |
| Startup hoàn tất thành công | `CORRECT` | `ACCEPTING_TRAFFIC` | Runners xong; Spring Boot công bố ready |

**Ba bẫy thường gặp:**

1. **`ApplicationStartedEvent` không đồng nghĩa `ApplicationReadyEvent`.** Event started xảy ra trước runner, nên readiness thường còn `REFUSING_TRAFFIC`.
2. **`ApplicationReadyEvent` không đồng nhất với event readiness.** Spring Boot phát `AvailabilityChangeEvent<ReadinessState>` với `ACCEPTING_TRAFFIC` **sau** `ApplicationReadyEvent`. Trong một handler chạy *ngay khi* `ApplicationReadyEvent`, không nên mặc định sự kiện readiness sau đó đã phát.
3. **`run` có thể không thành công**. Nếu startup hoặc runner ném exception, đường thành công không đi tới readiness `ACCEPTING_TRAFFIC`; ứng dụng có thể phát `ApplicationFailedEvent`.

Một listener cho `AvailabilityChangeEvent<ReadinessState>` được định nghĩa trong context vẫn có thể quan sát event mặc định lúc startup **vì event này xảy ra sau khi context đã refresh**. Không cần đăng ký qua `spring.factories` chỉ để bắt sự kiện readiness bình thường.

## 6. Quan sát sự kiện bằng `@EventListener`

Trong đa số ứng dụng, viết một bean thông thường là đủ:

~~~java
package com.example.availability;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class AvailabilityObserver {

    @EventListener
    public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("READINESS changed-to=" + event.getState());
    }

    @EventListener
    public void onLiveness(AvailabilityChangeEvent<LivenessState> event) {
        System.out.println("LIVENESS changed-to=" + event.getState());
    }
}
~~~

Đây là một class hoàn chỉnh **khi biên dịch trong dự án Spring Boot 3.3 có dependency thích hợp**. Hai phương thức có kiểu generic cụ thể, cho phép cơ chế listener của Spring nhận đúng sự kiện tương ứng.

- `onReadiness(...)` nhận event có payload `ReadinessState`.
- `onLiveness(...)` nhận event có payload `LivenessState`.
- `getState()` cho biết **giá trị được công bố bởi event hiện tại**.
- `@Component` cho phép Spring đưa class vào `ApplicationContext` thông qua component scanning.

**Không nên dùng một listener của readiness để suy diễn trạng thái liveness**, cũng không nên dựa trên tên class của `getSource()` vì người phát event có thể khác nhau theo từng trường hợp.

### Cách viết bằng `ApplicationListener`

Có thể dùng giao diện thay cho annotation:

~~~java
package com.example.availability;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

@Component
public class ReadinessOnlyListener
        implements ApplicationListener<AvailabilityChangeEvent<ReadinessState>> {

    @Override
    public void onApplicationEvent(AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("READINESS changed-to=" + event.getState());
    }
}
~~~

Đây là **lựa chọn thay thế** cho listener readiness trước đó, không nên đăng ký cả hai nếu bạn muốn mỗi sự kiện chỉ in một dòng.

Một `ApplicationListener<AvailabilityChangeEvent<ReadinessState>>` có thể đăng ký làm bean vì các event availability quan trọng trong startup xuất hiện khi context đã tồn tại. Nếu thư viện cần lắng nghe một mốc **trước khi bean được tạo**, mới cần đăng ký sớm qua `SpringApplication.addListeners(...)`, builder hoặc `spring.factories` tùy event đó.

## 7. Phát sự kiện để tạm ngừng nhận lưu lượng

Giả sử dịch vụ đã chạy, nhưng cần tạm thời ngừng nhận request mới khi đang phục hồi bộ nhớ đệm quan trọng. Thay vì đánh dấu tiến trình là không sống, ứng dụng có thể **chuyển readiness sang `REFUSING_TRAFFIC`**:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;

public class TrafficGate {

    private final ApplicationEventPublisher publisher;

    public TrafficGate(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void pauseNewTraffic() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.REFUSING_TRAFFIC);
    }

    public void resumeNewTraffic() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

Đây là class Java hoàn chỉnh xét về cấu trúc (khi chạy trong dự án có Spring Boot dependency); để Spring quản lý/inject, cần đăng ký bằng `@Component` hoặc `@Bean`. Nó minh họa đúng cách gọi overload nhận `ApplicationEventPublisher`, một đối tượng `source` và state.

Luồng vận hành:

~~~text
Ứng dụng đang nhận traffic
    |
    | phát REFUSING_TRAFFIC
    v
ApplicationAvailability đổi readiness
    |
    v
Listener ghi nhận trạng thái mới
    |
    v
Probe/readiness endpoint (nếu cấu hình) phản ánh trạng thái
    |
    v
Hạ tầng cập nhật định tuyến sau những lần probe
    |
    | nguyên nhân tạm ngừng được xử lý
    | phát ACCEPTING_TRAFFIC
    v
Readiness cho phép nhận traffic trở lại
~~~

**Không có bảo đảm tức thời**: từ lúc publish event cho tới lúc Kubernetes loại instance khỏi danh sách endpoint có thể có độ trễ theo lịch probe và các thành phần điều phối. Nếu một thao tác bảo trì yêu cầu tuyệt đối không nhận request mới, phải thiết kế thêm cơ chế chặn/điều phối phù hợp, không chỉ trông chờ event.

### Khi nào không nên chuyển liveness sang BROKEN?

Nếu một API ngoài bị chậm nhưng ứng dụng vẫn có thể fallback hoặc tự retry, đây thường không phải lỗi liveness. Cần đánh giá liệu readiness có cần tạm ngừng hay không, và cân nhắc circuit breaker. Chuyển liveness sang `BROKEN` khiến hệ thống điều phối có thể restart instance, vốn không nhất thiết giải quyết được sự cố phụ thuộc ngoài.

## 8. Ví dụ thực hành hoàn chỉnh: quan sát startup và chuyển readiness thủ công

Bài thực hành dùng **Java 17 + Spring Boot 3.3.13 + Gradle**, khởi chạy như **console application**. Không cần máy chủ HTTP hay Spring Boot Actuator, bởi mục tiêu là kiểm chứng cơ chế phát/nhận event và `ApplicationAvailability` **ngay trong JVM**.

### 8.1. Cấu trúc dự án

~~~text
availability-events-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/availability/
    └── AvailabilityEventsDemo.java
~~~

### 8.2. Gradle cấu hình đúng version dependency

`settings.gradle`:

~~~groovy
rootProject.name = 'availability-events-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    // Gradle native BOM quản lý phiên bản các module của Spring Boot.
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)

    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

BOM là một phần thiết yếu của ví dụ: nếu chỉ áp dụng plugin `org.springframework.boot` mà khai báo dependency không có version **không kèm cơ chế quản lý dependency**, bản build có thể không phân giải được starter. Với BOM phía trên, `spring-boot-starter` nhận phiên bản tương thích với Spring Boot 3.3.13.

Cần sử dụng Gradle tương thích với Spring Boot 3.3 và JDK 17+. Dự án mẫu chỉ chứa starter cơ bản nên không tự mở cổng HTTP và không có endpoint Actuator.

### 8.3. Lớp ứng dụng

Tạo `src/main/java/com/example/availability/AvailabilityEventsDemo.java`:

~~~java
package com.example.availability;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class AvailabilityEventsDemo {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(AvailabilityEventsDemo.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = application.run(args)) {
            ApplicationAvailability availability =
                    context.getBean(ApplicationAvailability.class);

            System.out.println(
                    "MAIN after-run readiness=" + availability.getReadinessState());

            AvailabilityChangeEvent.publish(
                    context, ReadinessState.REFUSING_TRAFFIC);
            System.out.println(
                    "MAIN paused readiness=" + availability.getReadinessState());

            AvailabilityChangeEvent.publish(
                    context, ReadinessState.ACCEPTING_TRAFFIC);
            System.out.println(
                    "MAIN resumed readiness=" + availability.getReadinessState());
        }

        System.out.println("MAIN context closed");
    }

    @Bean
    ApplicationRunner inspectDuringStartup(ApplicationAvailability availability) {
        return args -> System.out.println(
                "RUNNER liveness=" + availability.getLivenessState()
                        + " readiness=" + availability.getReadinessState());
    }

    @EventListener
    public void onLiveness(AvailabilityChangeEvent<LivenessState> event) {
        System.out.println("EVENT liveness=" + event.getState());
    }

    @EventListener
    public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("EVENT readiness=" + event.getState());
    }
}
~~~

Giải thích mã:

1. `WebApplicationType.NONE` biến demo thành ứng dụng console; **không cần Tomcat** để phát availability event.
2. `@EventListener` trên class `@SpringBootApplication` đăng ký listener thông qua bean của context sau khi nó được tạo.
3. Spring Boot tự phát `AvailabilityChangeEvent<LivenessState>` với `CORRECT` sau `ApplicationStartedEvent` và trước runner.
4. `ApplicationRunner` in ra hai trạng thái đang có **trước khi `ApplicationReadyEvent` và event readiness `ACCEPTING_TRAFFIC` được phát**.
5. Khi `run(args)` trả về thành công, readiness đã được Spring Boot công bố là `ACCEPTING_TRAFFIC`.
6. Mã trong `main` chủ động publish `REFUSING_TRAFFIC` rồi `ACCEPTING_TRAFFIC`, cho thấy **một instance sống có thể đổi readiness nhiều lần**.
7. `try-with-resources` gọi `context.close()` khi kết thúc, giải phóng tài nguyên Spring theo hợp đồng đóng context.

### 8.4. Chạy

Nếu có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu chưa có wrapper nhưng đã cài Gradle tương thích:

~~~bash
gradle bootRun
~~~

Trong một lượt chạy thành công theo cấu hình demo, **các dòng chính do `System.out.println` của mã trên tạo ra**, theo thứ tự, bao gồm:

~~~text
EVENT liveness=CORRECT
RUNNER liveness=CORRECT readiness=REFUSING_TRAFFIC
EVENT readiness=ACCEPTING_TRAFFIC
MAIN after-run readiness=ACCEPTING_TRAFFIC
EVENT readiness=REFUSING_TRAFFIC
MAIN paused readiness=REFUSING_TRAFFIC
EVENT readiness=ACCEPTING_TRAFFIC
MAIN resumed readiness=ACCEPTING_TRAFFIC
~~~

Đây là **chuỗi mốc để đối chiếu**, không phải cam kết chỉ có đúng tám dòng stdout. Trong quá trình đóng context, Spring Boot có thể phát **thêm** sự kiện readiness `REFUSING_TRAFFIC`, nên listener có thể in thêm một dòng trước `MAIN context closed`. Ngoài ra còn có thể có log từ Spring Framework hoặc Gradle. Nội dung có thể khác nếu bạn thêm listener, runner, hoặc cấu hình tùy biến quá trình availability.

Hai kết luận từ demo:

- **Liveness không đổi** khi ứng dụng thủ công chuyển readiness từ nhận sang từ chối traffic và ngược lại.
- **`AvailabilityChangeEvent` không chỉ dùng cho startup.** Thành phần nghiệp vụ có thể phát nó trong khi ứng dụng đang chạy để điều khiển tín hiệu readiness.

### 8.5. Biến thể chỉ quan sát, không thay đổi

Nếu mục tiêu chỉ là **quan sát**, bỏ hai lời gọi `AvailabilityChangeEvent.publish(...)` trong `main`. Giữ các listener `onReadiness` và `onLiveness` cùng dòng đọc `ApplicationAvailability`. Khi đó ứng dụng vẫn tự phát các event của vòng đời bình thường; ta không chủ động tạo thêm lần chuyển readiness.

Nếu muốn chạy mã ứng dụng lâu dài trong JVM, dùng web server hoặc một cơ chế quản lý tiến trình phù hợp. Demo console chủ động đóng context để kết thúc và dễ quan sát; **không dùng việc console tự kết thúc để suy diễn hành vi của ứng dụng web thật**.

## 9. Đọc trạng thái trong listener: một lưu ý về thứ tự nhận sự kiện

Khi nhận `AvailabilityChangeEvent<ReadinessState>`:

~~~java
@EventListener
public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
    ReadinessState announced = event.getState();
    System.out.println("Event state = " + announced);
}
~~~

`event.getState()` chính là **giá trị đang được công bố**, nên đây là cách rõ ràng nhất để viết log chuyển trạng thái.

Đừng tùy tiện thay bằng:

~~~java
@EventListener
public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
    System.out.println(availability.getReadinessState());
}
~~~

rồi coi kết quả đó chắc chắn là event vừa nhận trong mọi hoàn cảnh. Vì `ApplicationAvailabilityBean` cũng nhận sự kiện và cập nhật snapshot, **thứ tự các listener có thể ảnh hưởng giá trị snapshot nhìn thấy bên trong một callback**, nhất là khi có cơ chế multicaster tùy biến. Nếu cần trạng thái của **event đang xử lý**, dùng `event.getState()`; nếu cần giá trị **hiện thời để quyết định hoạt động sau khi event được phân phối**, hỏi `ApplicationAvailability` ở thời điểm phù hợp.

Trong cơ chế mặc định, event multicaster của Spring thường phát đồng bộ và việc gọi `publish(...)` trả về sau khi các listener đồng bộ đã được xử lý. Nhưng khi có executor/multicaster bất đồng bộ, thứ tự và tính tức thời cần được kiểm tra riêng. Không đưa giả định “mọi listener đều chạy đồng bộ” vào logic nghiệp vụ.

## 10. Chỉ ghi nhận chuyển trạng thái thật sự, tránh thao tác lặp

Event có thể được phát lặp với cùng state. Để listener không thực hiện những side effect đắt đỏ nhiều lần, có thể giữ trạng thái đã xử lý gần nhất.

Ví dụ minh họa:

~~~java
@Component
public class ReadinessChangeLogger {

    private final AtomicReference<ReadinessState> last =
            new AtomicReference<>();

    @EventListener
    public void observe(AvailabilityChangeEvent<ReadinessState> event) {
        ReadinessState next = event.getState();
        ReadinessState previous = last.getAndSet(next);
        if (previous != next) {
            System.out.println("Readiness " + previous + " -> " + next);
        }
    }
}
~~~

Đây là **đoạn class minh họa**, cần các import `java.util.concurrent.atomic.AtomicReference`, `ReadinessState`, `AvailabilityChangeEvent`, `@Component` và `@EventListener` để biên dịch trong dự án Spring Boot. `AtomicReference` tránh lỗi đọc/ghi không đồng bộ đơn giản nếu các sự kiện được phát từ nhiều thread. Nó **không** biến chuỗi event thành giao dịch phân tán hay bảo đảm thứ tự toàn hệ thống khi nhiều publisher hoạt động đồng thời.

Mặc dù lọc trùng lặp hữu ích, vẫn phải cân nhắc:

- Khi listener mới được tạo, `previous` có thể là `null`; log “`null → ACCEPTING_TRAFFIC`” chỉ nghĩa là **lần đầu listener quan sát**, không nhất thiết ứng dụng trước đó không có readiness.
- Trong hệ thống nhiều context hoặc nhiều application instance, mỗi listener có trạng thái cục bộ riêng.
- Nếu việc xử lý event thất bại, chỉ lưu `last` rồi bỏ qua event lặp có thể bỏ lỡ retry. Side effect quan trọng cần cơ chế retry/ghi nhận riêng.
- Nếu chỉ dùng listener để ghi log, không nhất thiết phải thêm logic lọc trùng lặp; đôi khi log mọi lần publish lại có ích cho chẩn đoán.

## 11. Kết nối với Spring Boot Actuator và readiness probe

`AvailabilityChangeEvent` là sự kiện **nội bộ** của Spring Boot. Muốn hạ tầng bên ngoài nhìn thấy trạng thái qua HTTP, ứng dụng web cần cấu hình **Spring Boot Actuator** và mở các health groups thích hợp.

Trong một dự án Spring Boot 3.3 đã có web starter và Actuator, dependency ví dụ:

~~~groovy
dependencies {
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Đây là **mảnh cấu hình thay thế/điều chỉnh** trong một dự án Gradle Spring Boot hợp lệ, không thêm web starter vào demo console phía trên nếu chỉ muốn theo dõi stdout.

Spring Boot Actuator có thể expose hai health group:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Trong Kubernetes, Spring Boot có thể bật các probe group này khi nhận biết môi trường Kubernetes. Khi chạy thử **ngoài Kubernetes**, có thể bật thủ công:

~~~properties
management.endpoint.health.probes.enabled=true
~~~

Nếu cần mở probe trên **cùng cổng HTTP chính** thay vì chỉ cổng quản trị riêng, Spring Boot còn hỗ trợ:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

Khi bật tùy chọn này, có thể kiểm tra:

~~~text
GET /livez
GET /readyz
~~~

trên cổng ứng dụng chính, tùy cấu hình web/management của hệ thống.

### Trạng thái nội bộ không đồng nghĩa kết quả HTTP mọi lúc

- `ApplicationAvailability` lưu state hiện tại trong JVM.
- Actuator chuyển state thành kết quả health của nhóm readiness/liveness khi endpoint khả dụng và được cấu hình.
- Hạ tầng thực hiện HTTP probe và dựa vào kết quả để xử lý traffic/restart.
- Trong lúc ứng dụng chưa mở cổng hoặc đang shutdown, probe **có thể chưa truy cập được**, dù state nội bộ đã tồn tại.

Ví dụ khi readiness `REFUSING_TRAFFIC`, readiness health group thường không thành công và có thể dẫn tới HTTP 503 theo mapping health status. Nhưng **không phải mọi hệ thống gọi probe đều nhất thiết nhận được một HTTP 503**: nếu ứng dụng chưa mở cổng hoặc load balancer đã loại instance, kết nối có thể bị từ chối hoặc được xử lý theo tầng hạ tầng.

### Cấu hình Kubernetes mẫu

~~~yaml
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

Đây là **một trích đoạn của `containers[]` trong Pod/Deployment**, không phải một Kubernetes manifest hoàn chỉnh; cổng `8080` giả định ứng dụng thực sự expose Actuator health ở cổng đó. Nếu dùng cổng quản trị riêng hoặc `management.endpoints.web.base-path` khác, phải chỉnh probe tương ứng.

**Không để liveness phụ thuộc cứng vào một dịch vụ ngoài**. Nếu Redis chung gặp lỗi làm toàn bộ liveness probe thất bại, Kubernetes có thể restart liên tục mọi bản sao. Readiness có thể cần cân nhắc một số dependency bắt buộc, nhưng việc kéo cả dependency dùng chung vào readiness có thể dẫn tới việc **toàn bộ instance bị loại khỏi traffic** cùng lúc. Phải quyết định theo khả năng fallback và yêu cầu nghiệp vụ.

## 12. Những giới hạn của readiness event trong vận hành

Sự kiện `AvailabilityChangeEvent` **không tự** làm mọi điều dưới đây:

| Mong muốn | Event tự làm được? | Cơ chế còn cần |
| --- | --- | --- |
| Thay giá trị readiness/liveness nội bộ | Có, thông qua hệ thống event/availability của Spring Boot | Event được phát trong context phù hợp |
| Ghi log mỗi lần readiness đổi | Có nếu có listener | Listener ghi log/metrics |
| Đổi kết quả Actuator readiness probe | Có khi Actuator theo dõi state | Phụ thuộc Actuator, health group và endpoint hoạt động |
| Loại instance khỏi Kubernetes Service ngay tức khắc | **Không** | Kubelet probe, EndpointSlice và hạ tầng định tuyến |
| Chặn mọi request đã tới hoặc đã xử lý | **Không** | Server middleware, graceful shutdown hoặc điều phối request riêng |
| Tự đóng toàn bộ `ApplicationContext` | **Không** | Lệnh đóng context hoặc shutdown hợp lệ |
| Tự restart tiến trình khi `BROKEN` | **Không** | Hệ thống giám sát và chính sách restart |
| Tự kiểm tra mọi dependency của ứng dụng | **Không** | Health indicator, kiểm tra nghiệp vụ, circuit breaker |
| Lưu lịch sử state qua lần restart | **Không** | Hệ thống log, metrics hoặc storage bên ngoài |

Do đó, event là **điểm móc quan sát và điều phối ở cấp ứng dụng**, không phải một giải pháp đầy đủ cho traffic management.

## 13. Trường hợp có nhiều nguồn phát event

Một ứng dụng thực tế có thể có các nguồn phát readiness:

- Spring Boot tự phát `ACCEPTING_TRAFFIC` sau startup thành công.
- Bộ điều phối bảo trì phát `REFUSING_TRAFFIC` để tạm ngừng.
- Bộ kiểm soát quá tải phát `REFUSING_TRAFFIC` khi giới hạn bị vượt.
- Bộ phục hồi cache phát `ACCEPTING_TRAFFIC` khi hệ thống phục hồi.
- Quá trình shutdown phát `REFUSING_TRAFFIC` khi ứng dụng sắp dừng.

Nếu các thành phần này phát độc lập, có thể xảy ra **ghi đè trạng thái hợp lệ của nhau**. Ví dụ: ứng dụng đang quá tải; bộ bảo trì vừa xong lại phát `ACCEPTING_TRAFFIC` dù quá tải vẫn tồn tại.

Giải pháp tốt hơn là **tập trung quyết định readiness**:

~~~text
Maintenance requested?  ----yes----\
Overload active?         ----yes-----+--> REFUSING_TRAFFIC
Required local setup ok? ----no-----/
                                   
Tất cả điều kiện phù hợp ------------> ACCEPTING_TRAFFIC
~~~

Một service chuyên trách có thể giữ tập lý do “chưa sẵn sàng” và chỉ phát `ACCEPTING_TRAFFIC` khi **không còn lý do chặn**. Mỗi thành phần cập nhật điều kiện của nó thay vì trực tiếp tự ý công bố ACCEPTING.

Tương tự, cần cân nhắc **race condition** khi nhiều thread phát event. Hệ thống event mặc định thường đồng bộ trong phạm vi lần publish, nhưng không cung cấp một giao dịch nguyên tử bao trùm mọi publisher và external side effect. Nếu readiness ảnh hưởng traffic quan trọng, cần thiết kế đồng bộ hoá, idempotence và giám sát trạng thái đã công bố.

## 14. Quan sát khi ứng dụng chuẩn bị đóng

Khi nhận tín hiệu shutdown bình thường, Spring Boot có thể đưa readiness sang `REFUSING_TRAFFIC` và triển khai graceful shutdown theo cấu hình. Vì vậy listener readiness có thể tiếp tục nhận sự kiện **sau khi ứng dụng đã chạy một thời gian**, không chỉ trong startup.

Ví dụ cấu hình graceful shutdown trong ứng dụng web:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Giải thích:

- `server.shutdown=graceful` yêu cầu server hỗ trợ cơ chế ngừng nhận request mới và chờ request đang xử lý theo hợp đồng tích hợp.
- `spring.lifecycle.timeout-per-shutdown-phase` quy định thời gian chờ theo phase đối với các thành phần được LifecycleProcessor dừng.
- Cần phối hợp với hạn chót dừng của container/OS; nếu bị kill cưỡng bức, listener và shutdown hook có thể không chạy hết.
- Đừng coi một `ContextClosedEvent` là bằng chứng rằng tất cả HTTP request đã hoàn tất. Quá trình ngừng/dọn dẹp có thể diễn ra tiếp sau event.

**Cẩn trọng trong listener shutdown:** cố gọi một bean đã bị destroy, tạo thread mới hoặc gửi I/O dài trong callback sự kiện có thể làm shutdown bị trì hoãn hoặc lỗi. Với công việc cần hoàn tất trước khi dừng, thiết kế cơ chế dừng rõ ràng, thay vì phụ thuộc vào log của event availability.

## 15. Lỗi phổ biến khi quan sát `AvailabilityChangeEvent`

| Hiện tượng | Nguyên nhân có thể | Cách chẩn đoán |
| --- | --- | --- |
| Chỉ thấy event readiness `ACCEPTING_TRAFFIC`, không thấy `REFUSING_TRAFFIC` đầu startup | `REFUSING_TRAFFIC` có thể là trạng thái mặc định trước khi một event được phát; listener bean chưa tồn tại rất sớm | Phân biệt default state với event thực sự; đọc `ApplicationAvailability` |
| Listener `@EventListener` không chạy | Class không thành bean, ngoài component scan hoặc generic event không khớp | Kiểm tra `@Component`/`@Bean` và kiểu `AvailabilityChangeEvent<ReadinessState>` |
| `ApplicationStartedEvent` đã chạy nhưng readiness vẫn `REFUSING_TRAFFIC` | Chưa qua runners/`ApplicationReadyEvent` | Đây là thứ tự bình thường, không phải bug |
| `ApplicationReadyEvent` đã phát nhưng chưa thấy event `ACCEPTING_TRAFFIC` trong chính handler đó | Readiness event được phát **sau** `ApplicationReadyEvent` | Quan sát trực tiếp `AvailabilityChangeEvent<ReadinessState>` |
| Log bắt được readiness nhưng query qua HTTP vẫn khác | Probe chưa bật, bị cache, hạ tầng có độ trễ, endpoint/port khác | Kiểm tra Actuator health groups và cổng đang expose |
| Đặt readiness `REFUSING_TRAFFIC` nhưng request vẫn đến | Hạ tầng chưa probe/cập nhật, request cũ đang xử lý hoặc không có probe | Xem cấu hình kubelet, interval, đường dẫn và cơ chế chặn bổ sung |
| Đặt liveness `BROKEN` khi database ngoài hỏng rồi Pod restart liên tục | Nhầm lỗi phụ thuộc bên ngoài với lỗi không thể phục hồi nội bộ | Dùng readiness/circuit breaker phù hợp hơn |
| Listener ghi log trùng | Hai cách đăng ký cùng logic, nhiều instance hoặc event được phát lặp | Kiểm tra nơi đăng ký, loại event và thiết kế idempotent |
| `getLastChangeEvent(...)` trả `null` | Chưa có event tương ứng | Kiểm tra mốc startup/đăng ký và dùng fallback có chủ ý |
| Listener phụ thuộc bean không sẵn sàng | Đăng ký quá sớm và truy cập container khi chưa refresh | Chọn mốc event phù hợp hoặc dùng bean listener sau refresh |
| Một thành phần báo ACCEPTING quá sớm | Nhiều publisher không phối hợp | Tập trung chính sách readiness, chỉ chuyển khi mọi điều kiện đã đạt |
| Không thấy event khi JVM bị kill cưỡng bức | Shutdown hook và Spring close không thực thi đầy đủ | Dựa vào hạ tầng quản lý tiến trình và cơ chế phục hồi dữ liệu |

### Trường hợp dùng listener generic kiểu quá rộng

~~~java
@EventListener
public void onAnyAvailability(AvailabilityChangeEvent<?> event) {
    System.out.println(event.getState());
}
~~~

Đoạn trên minh họa một listener quan sát **mọi AvailabilityState**, không chỉ readiness. Nếu muốn log tách rõ hai loại, có thể kiểm tra `event.getState() instanceof ReadinessState` hoặc sử dụng hai handler có generic cụ thể. Đừng ép kiểu payload readiness mà không kiểm tra type.

## 16. Kiểm thử và xác minh

### Kiểm thử đơn giản qua mã ví dụ

Trong demo console, hãy đối chiếu:

1. Có event liveness `CORRECT` trước runner.
2. Runner thấy `CORRECT` + `REFUSING_TRAFFIC`.
3. Sau runner có event readiness `ACCEPTING_TRAFFIC`.
4. Sau `run`, `ApplicationAvailability.getReadinessState()` là `ACCEPTING_TRAFFIC`.
5. Khi publish `REFUSING_TRAFFIC`, listener in đúng giá trị mới; đọc lại snapshot xác nhận.
6. Khi publish `ACCEPTING_TRAFFIC`, listener và snapshot phản ánh phục hồi.
7. Nếu thêm shutdown listener/log, có thể thấy event chuyển readiness khi context đóng.

### Kiểm thử với ứng dụng web + Actuator

Nếu app web đã expose Actuator, thực hiện trên môi trường test:

~~~bash
curl -i http://localhost:8080/actuator/health/readiness
~~~

Lặp lại trước và sau khi một thành phần có kiểm soát phát `REFUSING_TRAFFIC`, rồi `ACCEPTING_TRAFFIC`. Với readiness khỏe, health group thông thường trả mã thành công; khi refusal, health group có thể trả lỗi dịch vụ theo mapping trạng thái. **Không hardcode mọi lần kết quả là đúng 200 hoặc 503 trong mọi môi trường**, vì security, port, base path, health group và HTTP proxy có thể thay đổi kết quả.

Khi viết test tự động, hãy tránh phụ thuộc vào thời gian ngủ tùy ý để “chờ event”. Trong trường hợp mặc định đồng bộ, có thể publish rồi kiểm tra `ApplicationAvailability`, hoặc dùng một listener/test probe có đồng bộ hóa rõ ràng. Nếu cấu hình multicaster bất đồng bộ, dùng cơ chế chờ event có timeout hợp lý.

## 17. Bài tự kiểm tra kiến thức

1. **`AvailabilityChangeEvent` mang theo dữ liệu gì?** Một `AvailabilityState`, ví dụ `LivenessState.CORRECT` hoặc `ReadinessState.REFUSING_TRAFFIC`.
2. **Muốn biết giá trị readiness mới vừa được publish, dùng gì?** `event.getState()`.
3. **Muốn đọc readiness hiện tại từ bean bất kỳ, dùng gì?** Inject `ApplicationAvailability` và gọi `getReadinessState()`.
4. **`ApplicationStartedEvent` và event `LivenessState.CORRECT` liên hệ ra sao?** Spring Boot công bố liveness `CORRECT` ngay sau event started trên đường thành công.
5. **`ApplicationReadyEvent` và event `ReadinessState.ACCEPTING_TRAFFIC` liên hệ ra sao?** Event readiness `ACCEPTING_TRAFFIC` được publish ngay sau ApplicationReadyEvent.
6. **Có thể đang `CORRECT` nhưng `REFUSING_TRAFFIC` không?** Có, đây là trạng thái hợp lệ khi đang chạy runner/bảo trì/quá tải.
7. **Muốn tạm ngừng traffic có nên publish `LivenessState.BROKEN` trước không?** Không, trừ khi tiến trình thực sự hỏng và không thể tự hồi phục; thông thường dùng readiness.
8. **Có cần `spring.factories` để nhận readiness event trong một bean `@Component` không?** Không, listener bean sau refresh thường đủ.
9. **`getLastChangeEvent(ReadinessState.class)` luôn khác `null` khi app bắt đầu không?** Không; có thể chưa có event loại đó.
10. **Publish readiness `REFUSING_TRAFFIC` có đảm bảo Kubernetes lập tức ngừng mọi request không?** Không; còn probe, cập nhật định tuyến và các request đã đến.
11. **Tại sao không nên dùng kiểm tra DB ngoài làm liveness probe?** Sự cố chung có thể khiến toàn bộ instance bị restart tạo lỗi dây chuyền.
12. **Nếu hai service đồng thời quyết định readiness, rủi ro gì?** Một service có thể công bố `ACCEPTING_TRAFFIC` dù lý do refusal của service khác vẫn còn; cần phối hợp chính sách.
13. **Readiness state trong Spring có phải là HTTP endpoint tự động không?** Không. Muốn probe HTTP, cần Actuator/cấu hình liên quan và ứng dụng HTTP.
14. **Một `ApplicationReadyEvent` có nghĩa các thành phần external đều khỏe vĩnh viễn không?** Không; nó là mốc vòng đời và trạng thái có thể thay đổi sau đó.
15. **Vì sao trong event handler nên dùng `event.getState()` hơn đọc lại snapshot?** Vì đây là giá trị được công bố bởi chính event, không phụ thuộc thứ tự cập nhật snapshot giữa nhiều listener.

**Tổng kết:** `AvailabilityChangeEvent` là cầu nối giữa **sự kiện thay đổi trạng thái** và việc **quan sát, phản ứng hoặc công bố liveness/readiness** trong Spring Boot. `ApplicationAvailability` phục vụ truy vấn trạng thái hiện tại; `@EventListener` phục vụ quan sát từng event; `AvailabilityChangeEvent.publish(...)` phục vụ việc công bố chuyển trạng thái. Khi kết hợp với Actuator/Kubernetes probes, các tín hiệu này hỗ trợ điều phối lưu lượng, nhưng không thay thế thiết kế shutdown, kiểm tra nghiệp vụ và xử lý hạ tầng.

### Tài liệu tham khảo

- Spring Boot 3.3.13 — **SpringApplication: Application Availability**, liveness/readiness và phát sự kiện: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — **AvailabilityChangeEvent API** (`getState`, `publish`): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html
- Spring Boot 3.3.13 — **ApplicationAvailability API** (`getReadinessState`, `getLastChangeEvent`): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ApplicationAvailability.html
- Spring Boot 3.3.13 — **Actuator Endpoints: Kubernetes Probes**: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — **Gradle Plugin: Managing Dependencies**: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
- Kubernetes — **Liveness, Readiness, and Startup Probes**: https://kubernetes.io/docs/concepts/workloads/pods/probes/
