# Chủ động phát sự kiện thay đổi trạng thái ứng dụng trong Spring Boot 3.3

## 1. Mục tiêu

Spring Boot có cơ chế **Application Availability** để biểu diễn tình trạng của một ứng dụng đang chạy. Bên cạnh các sự kiện do chính Spring Boot phát trong quá trình khởi động và tắt ứng dụng, **một component của ứng dụng cũng có thể chủ động phát `AvailabilityChangeEvent`** khi điều kiện hoạt động thay đổi.

Hai nhóm trạng thái thường gặp:

- **`ReadinessState`**: ứng dụng có nên nhận thêm traffic hoặc công việc mới hay không.
- **`LivenessState`**: ứng dụng còn có thể tự hoạt động/phục hồi đúng cách hay đã hỏng ở mức cần khởi động lại.

Khi một component chủ động phát event, các listener có thể nhận sự kiện; đồng thời Spring Boot cập nhật trạng thái mà bean `ApplicationAvailability` báo cáo. Khi có Spring Boot Actuator với probes cấu hình phù hợp, trạng thái này còn có thể được phản ánh trong health groups cho hệ thống điều phối như Kubernetes.

**Mục tiêu thực hành:**

1. Phân biệt **sự kiện** `AvailabilityChangeEvent<S>` với **giá trị trạng thái** `ReadinessState`/`LivenessState` và **bean truy vấn** `ApplicationAvailability`.
2. Phát đúng hai dạng API `AvailabilityChangeEvent.publish(context, state)` hoặc `AvailabilityChangeEvent.publish(publisher, source, state)`.
3. Dùng constructor injection để phát/nhận event và truy vấn lại trạng thái.
4. Chọn `REFUSING_TRAFFIC` khi cần tạm rút ứng dụng khỏi luồng nhận việc, thay vì đánh dấu liveness `BROKEN` một cách tùy tiện.
5. Hiểu tương tác giữa trạng thái tự phát và event tự động của Spring Boot lúc startup/shutdown.
6. Chạy ví dụ Java 21 + Spring Boot 3.3.13, quan sát thứ tự trạng thái, kiểm thử với JUnit và biết cách gắn Actuator readiness/liveness probes.

**Nguyên tắc cốt lõi:** thay đổi availability state là một **tín hiệu về khả năng phục vụ**, không phải lệnh tự động tắt JVM, kill pod, khởi động lại container hay dừng mọi request đang xử lý.

## 2. Mô hình ba thành phần

```text
Một component phát hiện điều kiện bất thường
          |
          | AvailabilityChangeEvent.publish(...)
          v
Spring ApplicationEventPublisher
          |
          +--> AvailabilityChangeEvent<ReadinessState>
          |     +--> ApplicationAvailability ghi nhận state mới
          |     +--> Listener quan sát, ghi log/metrics
          |     +--> Actuator readiness health group (nếu cấu hình)
          |
          +--> AvailabilityChangeEvent<LivenessState>
                +--> ApplicationAvailability ghi nhận state mới
                +--> Listener quan sát
                +--> Actuator liveness health group (nếu cấu hình)
```

Có ba khái niệm dễ bị nhầm:

| Thành phần | Vai trò | Cách dùng |
| --- | --- | --- |
| `AvailabilityState` | Interface đánh dấu một loại state | `ReadinessState`, `LivenessState` là các enum triển khai |
| `AvailabilityChangeEvent<S extends AvailabilityState>` | Một application event nói rằng state vừa thay đổi | `AvailabilityChangeEvent.publish(...)`, `event.getState()` |
| `ApplicationAvailability` | Đọc state đã được công bố gần nhất cho một loại availability | `getReadinessState()`, `getLivenessState()`, `getState(...)` |

**Chú ý:** `ApplicationAvailability` dùng để **đọc**, không phải giao diện có setter như `setReadinessState(...)`. Để cập nhật state, hãy **phát `AvailabilityChangeEvent` qua Spring event publisher/context**.

### 2.1. Các giá trị readiness

`org.springframework.boot.availability.ReadinessState` có hai giá trị chính:

- **`ReadinessState.ACCEPTING_TRAFFIC`**: ứng dụng thông báo rằng nó có thể nhận traffic hoặc tác vụ mới.
- **`ReadinessState.REFUSING_TRAFFIC`**: ứng dụng thông báo rằng nó chưa nên nhận thêm traffic hoặc tác vụ mới.

Ví dụ phù hợp với `REFUSING_TRAFFIC`: service cần tạm rút khỏi load balancer để giảm tải, hết khả năng xử lý an toàn, đang phục hồi dữ liệu nội bộ cần thiết, hoặc chuẩn bị bước bảo trì có kiểm soát.

Readiness không nói rằng JVM đã chết. Một ứng dụng vẫn có thể **live** trong lúc nó **not ready**.

### 2.2. Các giá trị liveness

`org.springframework.boot.availability.LivenessState` có hai giá trị chính:

- **`LivenessState.CORRECT`**: trạng thái bên trong vẫn cho phép ứng dụng hoạt động đúng.
- **`LivenessState.BROKEN`**: ứng dụng đã rơi vào trạng thái nội bộ mà nó không thể phục hồi đúng cách nếu không có tác động bên ngoài, thường cần restart theo chính sách vận hành.

**Không đánh dấu `BROKEN` chỉ vì một dịch vụ bên ngoài (database, cache từ xa, API, DNS) tạm thời lỗi.** Nếu liveness probe thất bại, nền tảng điều phối có thể restart pod liên tục. Khi nhiều pod phụ thuộc chung một hệ thống ngoài, điều này còn tạo thảm họa restart dây chuyền. Với sự cố bên ngoài mà ứng dụng vẫn có thể phục hồi, cân nhắc readiness và recovery/backoff thích hợp.

### 2.3. Hai trục độc lập

| Tình huống | Liveness | Readiness | Giải thích |
| --- | --- | --- | --- |
| Ứng dụng đã khởi động hoàn tất, đủ năng lực phục vụ | `CORRECT` | `ACCEPTING_TRAFFIC` | Có thể nhận việc mới |
| Đang startup, runner chưa xong | Có thể đã `CORRECT` | `REFUSING_TRAFFIC` | Context đã refresh nhưng chưa ready |
| Quá tải tạm thời, cần giảm traffic | `CORRECT` | `REFUSING_TRAFFIC` | Chưa cần restart; ưu tiên phục hồi |
| Trạng thái nội bộ không thể phục hồi | `BROKEN` | Tùy chính sách | Liveness probe có thể yêu cầu restart |
| Đang graceful shutdown | Thường vẫn `CORRECT` lúc bắt đầu dừng | `REFUSING_TRAFFIC` | Ngừng nhận việc mới và giải quyết việc đang xử lý |

Không cố gắng biểu diễn mọi vấn đề dưới dạng `LivenessState.BROKEN`. Khi cần, trạng thái readiness có thể đổi qua lại nhiều lần trong suốt thời gian ứng dụng hoạt động.

## 3. Spring Boot tự phát AvailabilityChangeEvent khi nào?

Trong một lần startup thành công:

```text
ApplicationContext.refresh()
   |
   +-- ApplicationStartedEvent
   +-- AvailabilityChangeEvent(LivenessState.CORRECT)
   |
   +-- ApplicationRunner / CommandLineRunner
   |
   +-- ApplicationReadyEvent
   +-- AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
   |
   +-- SpringApplication.run(...) trả về
```

Spring Boot xem application **live** khi context đã refresh thành công và xem **ready** sau khi các runners đã trả về bình thường.

Điểm quan trọng:

- `ApplicationStartedEvent` và `ApplicationReadyEvent` **không đồng nghĩa** với `AvailabilityChangeEvent`.
- Boot phát `LivenessState.CORRECT` **sau** `ApplicationStartedEvent`.
- Boot phát `ReadinessState.ACCEPTING_TRAFFIC` **sau** `ApplicationReadyEvent`.
- Khi startup chưa hoàn tất, readiness thông thường ở mức từ chối traffic.
- Trong shutdown/graceful shutdown, readiness thường chuyển sang từ chối traffic; các hook/lifecycle có thể phụ thuộc loại application và cấu hình.
- Nếu runner ném exception, luồng startup thành công không đi tới mốc ready bình thường.

**Bẫy thường gặp:** Nếu bạn phát `ReadinessState.REFUSING_TRAFFIC` ngay trong một listener nhận `ApplicationReadyEvent`, sau khi listener đó trả về **Spring Boot còn phát `ReadinessState.ACCEPTING_TRAFFIC`** trong luồng startup chuẩn. Giá trị tự phát trước đó có thể bị ghi đè. Đừng dùng ready listener để “khóa readiness mãi mãi” mà không xét thứ tự startup. Nếu điều kiện bắt buộc phải được bảo đảm trước ready, hãy kiểm soát công việc của runner hoặc lifecycle bằng timeout và xử lý lỗi rõ ràng; sau startup, mới dùng trạng thái động để tạm từ chối traffic khi điều kiện thay đổi.

## 4. API để chủ động phát event

### 4.1. Cách 1: có ApplicationContext

Chữ ký tiện ích trong Spring Boot 3.3:

```java
public static <S extends AvailabilityState> void publish(
        ApplicationContext context, S state);
```

Đây là **chữ ký API minh họa**, không phải khai báo một phương thức trong ứng dụng. Ví dụ sử dụng sau khi context đã sẵn sàng:

```java
AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.REFUSING_TRAFFIC);
```

`applicationContext` phải là một Spring `ApplicationContext` hợp lệ, thường được lấy từ dependency injection hoặc giá trị `SpringApplication.run(...)` trả về. API này phát một application event tới context đã chỉ định.

Cách này thuận tiện trong code điều phối ở mức ứng dụng, công cụ quản trị hoặc code demo đã giữ được tham chiếu context.

### 4.2. Cách 2: có ApplicationEventPublisher và source

Chữ ký tiện ích khác:

```java
public static <S extends AvailabilityState> void publish(
        ApplicationEventPublisher publisher, Object source, S state);
```

Ví dụ:

```java
AvailabilityChangeEvent.publish(
        eventPublisher,
        this,
        ReadinessState.REFUSING_TRAFFIC);
```

Đây là **đoạn minh họa bên trong một bean có biến `eventPublisher`**. Dùng constructor injection để nhận publisher; `this` là source cho biết thành phần nào yêu cầu thay đổi state. Nếu sự thay đổi do exception phát hiện, có thể truyền exception làm source để phục vụ quan sát, nhưng không nên log payload chứa bí mật.

**Không có overload hai tham số `(ApplicationEventPublisher, ReadinessState)` trong Spring Boot 3.3.13.** Nếu chỉ có biến kiểu `ApplicationEventPublisher`, dùng overload ba tham số hoặc phát trực tiếp event object.

### 4.3. Cách 3: phát trực tiếp event object

Cơ chế tương đương:

```java
publisher.publishEvent(
        new AvailabilityChangeEvent<>(
                this, ReadinessState.REFUSING_TRAFFIC));
```

Đây là **đoạn minh họa**; cần import `org.springframework.boot.availability.AvailabilityChangeEvent`, `ReadinessState` và biến `publisher` loại `ApplicationEventPublisher`.

Tuy có thể dùng constructor, nên ưu tiên phương thức static `publish(...)` để thể hiện rõ ý định. **Đừng chỉ tự tạo `new AvailabilityChangeEvent<>(...)` mà không đưa vào publisher**: object chưa được phát thì bean `ApplicationAvailability` không nhận thay đổi.

### 4.4. Ví dụ chuyển về ACCEPTING_TRAFFIC

Khi nguyên nhân tạm từ chối đã được giải quyết và hệ thống thật sự có thể nhận việc, chủ động phát:

```java
AvailabilityChangeEvent.publish(
        eventPublisher,
        this,
        ReadinessState.ACCEPTING_TRAFFIC);
```

Không tự động chuyển về accepting sau một khoảng thời gian nếu nguyên nhân vẫn còn. Nên xác nhận điều kiện phục hồi qua state machine, health checks hoặc kiểm tra nghiệp vụ.

### 4.5. Ví dụ thông báo lỗi nội bộ không phục hồi được

```java
AvailabilityChangeEvent.publish(
        eventPublisher,
        this,
        LivenessState.BROKEN);
```

Đây là tín hiệu **cần rất thận trọng**. Nó không trực tiếp gọi `System.exit`, không đảm bảo Kubernetes sẽ restart ngay lập tức, và không tự sửa trạng thái hỏng. Tác dụng trong triển khai phụ thuộc vào việc nền tảng có đọc liveness probe hay cơ chế tương đương hay không.

## 5. Đọc state sau khi phát sự kiện

Inject `org.springframework.boot.availability.ApplicationAvailability`:

```java
@Component
public class StateReporter {

    private final ApplicationAvailability availability;

    public StateReporter(ApplicationAvailability availability) {
        this.availability = availability;
    }

    public ReadinessState readiness() {
        return availability.getReadinessState();
    }

    public LivenessState liveness() {
        return availability.getLivenessState();
    }
}
```

Đây là **mẫu bean minh họa**, cần import `@Component`, `ApplicationAvailability`, `ReadinessState`, `LivenessState`.

Các API quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `getReadinessState()` | Trạng thái readiness hiện có |
| `getLivenessState()` | Trạng thái liveness hiện có |
| `getState(ReadinessState.class)` | Trạng thái của một loại state chỉ định; có thể chưa có event trước đó |
| `getState(ReadinessState.class, ReadinessState.REFUSING_TRAFFIC)` | Trạng thái hoặc giá trị mặc định nếu chưa có event |
| `getLastChangeEvent(ReadinessState.class)` | Event gần nhất cho loại readiness, có thể chưa tồn tại |

Nếu dùng `getLastChangeEvent`, nên xử lý trường hợp `null` khi chưa có sự kiện:

```java
AvailabilityChangeEvent<ReadinessState> last =
        availability.getLastChangeEvent(ReadinessState.class);
if (last != null) {
    System.out.println("Latest readiness: " + last.getState());
}
```

**Không nhầm state với event:** `getReadinessState()` trả enum, không phải event. `getLastChangeEvent(...)` cho phép xem state cùng metadata của event (ví dụ source và timestamp) nếu muốn audit.

Thông thường, với publisher mặc định và listeners đồng bộ trong một context đã khởi động, bean `ApplicationAvailability` được cập nhật khi event được xử lý. Nếu đã tùy chỉnh global event multicaster theo cách bất đồng bộ, đừng mặc định mọi listener đã hoàn tất ngay khi phương thức publish trả về; cần test chính cách cấu hình thực tế.

## 6. Nhận sự kiện thay đổi trạng thái bằng listener

Một Spring bean có thể nhận event readiness:

```java
@Component
public class ReadinessObserver {

    @EventListener
    public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
        if (event.getState() == ReadinessState.REFUSING_TRAFFIC) {
            System.out.println("Stop taking new work");
        }
        else {
            System.out.println("Ready to accept new work");
        }
    }
}
```

Đây là **mẫu minh họa**, cần import `@Component`, `@EventListener`, `AvailabilityChangeEvent`, `ReadinessState`.

Nhờ `AvailabilityChangeEvent` có generic state type và hỗ trợ `ResolvableType`, listener có thể phân biệt:

```java
@EventListener
void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
    // readiness only
}

@EventListener
void onLiveness(AvailabilityChangeEvent<LivenessState> event) {
    // liveness only
}
```

Hai methods ở trên là **đoạn minh họa đặt bên trong một Spring bean**, không phải file Java độc lập. Trong ứng dụng thực tế, có thể dùng `ApplicationListener` để nhận sự kiện tương tự.

Listener nên ngắn gọn, tránh thao tác I/O nặng làm block thread publish. Nếu listener được chuyển sang executor bất đồng bộ, cần xử lý thứ tự hoàn tất, exception, retries và việc không còn sẵn transaction/request context.

**Hệ quả quan trọng:** Một listener có thể nhận event cả từ **Spring Boot tự phát** lẫn **ứng dụng chủ động phát**. Đừng kết luận event quan sát được nhất thiết là do đoạn code `publish(...)` của bạn tạo ra; có thể xem source và thời điểm event để chẩn đoán.

## 7. Ví dụ hoàn chỉnh — Java 21 và Spring Boot 3.3.13

Ví dụ dùng ứng dụng **non-web** với các thành phần:

1. `AvailabilityDemoApplication`: khởi động Spring Boot và thực hiện chuyển trạng thái sau khi `run(...)` kết thúc.
2. `ReadinessController`: chủ động phát `REFUSING_TRAFFIC` rồi `ACCEPTING_TRAFFIC` qua `ApplicationEventPublisher`.
3. `AvailabilityObserver`: in mỗi event readiness/liveness đã nhận.
4. `ApplicationAvailability`: đọc state thực tế sau mỗi lần phát.

### 7.1. Cấu trúc thư mục

```text
availability-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/availability/
    │       ├── AvailabilityDemoApplication.java
    │       ├── ReadinessController.java
    │       └── AvailabilityObserver.java
    └── test/
        └── java/com/example/availability/
            └── ReadinessControllerTest.java
```

### 7.2. Maven pom.xml

Tệp `pom.xml`:

```xml
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
    <artifactId>availability-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
```

`spring-boot-starter` cung cấp các thành phần cho ứng dụng CLI; `spring-boot-starter-test` cung cấp công cụ test. Demo không có actuator hoặc HTTP server; phần cấu hình probes cho production ở mục riêng.

### 7.3. Component chủ động thay đổi readiness

Tệp `src/main/java/com/example/availability/ReadinessController.java`:

```java
package com.example.availability;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class ReadinessController {

    private final ApplicationEventPublisher publisher;

    public ReadinessController(ApplicationEventPublisher publisher) {
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
```

Mỗi method chỉ phát tín hiệu. Nó **không dừng** một HTTP server và **không tự cấu hình** Kubernetes hoặc load balancer. Trong production, bên ngoài cần đọc readiness probe hoặc service discovery thích hợp để thật sự điều chỉnh traffic.

### 7.4. Listener quan sát hai loại state

Tệp `src/main/java/com/example/availability/AvailabilityObserver.java`:

```java
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
        System.out.println("EVENT readiness=" + event.getState());
    }

    @EventListener
    public void onLiveness(AvailabilityChangeEvent<LivenessState> event) {
        System.out.println("EVENT liveness=" + event.getState());
    }
}
```

`@EventListener` ở đây nhận **cả sự kiện tự động của Boot** và sự kiện mà `ReadinessController` phát. Các event có generic type khác nhau nên hai phương thức không bị nhầm lẫn.

### 7.5. Main thực hiện chuyển trạng thái sau khi app ready

Tệp `src/main/java/com/example/availability/AvailabilityDemoApplication.java`:

```java
package com.example.availability;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class AvailabilityDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(AvailabilityDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            ApplicationAvailability availability =
                    context.getBean(ApplicationAvailability.class);
            ReadinessController controller =
                    context.getBean(ReadinessController.class);

            System.out.println("MAIN initial="
                    + availability.getReadinessState());

            controller.pauseNewTraffic();
            System.out.println("MAIN paused="
                    + availability.getReadinessState());

            controller.resumeNewTraffic();
            System.out.println("MAIN resumed="
                    + availability.getReadinessState());
        }
    }
}
```

**Vì sao thay đổi state sau `app.run(args)`?** Trong luồng startup thành công, Spring Boot đã phát `ApplicationReadyEvent` và event `ReadinessState.ACCEPTING_TRAFFIC` trước khi `run` trả về. Demo vì thế quan sát một thay đổi do ứng dụng chủ động thực hiện **trong thời gian chạy sau startup**, không bị Boot ghi đè bởi bước công bố readiness cuối cùng của startup.

`try-with-resources` đóng `ConfigurableApplicationContext` sau khi demo đã in xong. Trong khi context đóng, các availability/shutdown listeners của Boot có thể phát thêm sự kiện; chúng không làm sai các dòng đã quan sát **trước lúc đóng**.

### 7.6. Build và chạy

Cần JDK 21, Maven và quyền tải dependencies:

```bash
java -version
mvn -version
mvn test
mvn package
java -jar target/availability-demo-0.0.1-SNAPSHOT.jar
```

Những dòng do code ví dụ in **đến hết `MAIN resumed`**, lọc bỏ banner/log Spring Boot, phải có thứ tự:

```text
EVENT liveness=CORRECT
EVENT readiness=ACCEPTING_TRAFFIC
MAIN initial=ACCEPTING_TRAFFIC
EVENT readiness=REFUSING_TRAFFIC
MAIN paused=REFUSING_TRAFFIC
EVENT readiness=ACCEPTING_TRAFFIC
MAIN resumed=ACCEPTING_TRAFFIC
```

Sau khi code thoát khỏi `try`, Spring đóng context và có thể còn log hoặc availability event liên quan shutdown. **Khối trên chỉ mô tả phần trước khi đóng context, không phải toàn bộ stdout**.

Giải thích:

- Event `CORRECT` là liveness event Boot phát sau context refresh.
- Event `ACCEPTING_TRAFFIC` đầu tiên là readiness event Boot phát sau các runners và ready event.
- `MAIN initial` đọc được accepting vì `SpringApplication.run` đã hoàn tất.
- `controller.pauseNewTraffic()` phát refusing, listener nhận event và `ApplicationAvailability` ghi nhận.
- `controller.resumeNewTraffic()` phát accepting trở lại.
- Vì multicaster mặc định đồng bộ, ở demo này state có thể được đọc ngay sau khi publish trả về; nếu thay đổi cách dispatch, hãy điều chỉnh test/đồng bộ cho tương ứng.

### 7.7. Thử trực tiếp overload dùng ApplicationContext

Bạn có thể thay lời gọi của controller trong main bằng:

```java
AvailabilityChangeEvent.publish(
        context, ReadinessState.REFUSING_TRAFFIC);
```

Đây là **đoạn minh họa trong `try` đã có biến `context`**; không phải chương trình độc lập. Trong ví dụ này, sau khi phát qua context, listener vẫn nhận `AvailabilityChangeEvent<ReadinessState>` và `ApplicationAvailability` ghi nhận state mới.

## 8. Kiểm thử bằng Spring Boot Test

Để kiểm tra hợp đồng chủ động thay đổi readiness, dùng integration test thực sự tạo context và bean `ApplicationAvailability`, sau đó publish rồi assert. Không cần mở web server.

Tệp `src/test/java/com/example/availability/ReadinessControllerTest.java`:

```java
package com.example.availability;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        classes = AvailabilityDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ReadinessControllerTest {

    @Autowired
    private ReadinessController controller;

    @Autowired
    private ApplicationAvailability availability;

    @Test
    void publishesAndTracksReadinessChanges() {
        controller.pauseNewTraffic();
        assertEquals(ReadinessState.REFUSING_TRAFFIC,
                availability.getReadinessState());

        controller.resumeNewTraffic();
        assertEquals(ReadinessState.ACCEPTING_TRAFFIC,
                availability.getReadinessState());
    }
}
```

Test dùng bean thật và multicaster mặc định. Annotation `@DirtiesContext` giúp context test không bị tái sử dụng với trạng thái do bài test chủ động thay đổi. Không cần kiểm tra trạng thái ban đầu của test vì trạng thái sau từng lời gọi mới là hợp đồng cần chứng minh.

Nếu một dự án đã tùy biến multicaster sang async, assertion tức thời sau publish có thể không còn phù hợp; hãy cấu hình test đúng cách dispatch thực tế hoặc sử dụng đồng bộ hóa/polling có timeout.

### 8.1. Vì sao không chỉ new event rồi assert?

Đoạn sau không kiểm tra khả năng cập nhật state của Boot:

```java
new AvailabilityChangeEvent<>(
        this, ReadinessState.REFUSING_TRAFFIC);
```

Nó chỉ tạo event object, **không publish**. Test đúng phải dùng publisher/context để Boot nhận event.

### 8.2. Vì sao test controller trực tiếp vẫn chưa đủ?

Một unit test chỉ mock `ApplicationEventPublisher` và verify method `publishEvent(...)` có thể khẳng định controller phát event, nhưng **không chứng minh** bean `ApplicationAvailability` đã cập nhật. Integration test trên kiểm tra cả đường phát event và trạng thái được ghi nhận.

### 8.3. Tránh gây tác dụng phụ vào các test khác

Nếu test chỉ muốn kiểm tra một trạng thái rồi kết thúc, khôi phục state gốc trong `finally` hoặc đánh dấu context không tái sử dụng. Việc để state `REFUSING_TRAFFIC` rò sang test khác có thể làm test kết quả không ổn định, nhất là khi bộ test dùng context cache.

## 9. Dùng Actuator để liên kết trạng thái với probes

Trong ứng dụng **web** có Spring Boot Actuator, availability states có thể được biểu diễn thông qua health groups:

- **Liveness probe**: thường ở `/actuator/health/liveness`.
- **Readiness probe**: thường ở `/actuator/health/readiness`.

**Demo mục 7 là non-web và không có Actuator, nên không mở hai URL này.** Muốn kiểm thử HTTP probes, cần thay đổi cấu hình ứng dụng và dependencies; không thể chỉ gọi `AvailabilityChangeEvent.publish(...)` rồi mong xuất hiện endpoint HTTP.

### 9.1. Dependencies bổ sung cho ứng dụng web

Dùng `spring-boot-starter-web` và `spring-boot-starter-actuator` trong một dự án Spring Boot web (đây là **cấu hình mở rộng**, không phải pom đầy đủ ở mục 7):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Bỏ `app.setWebApplicationType(WebApplicationType.NONE)` để cho Boot tự chọn servlet web app. Có thể bật probes bằng cấu hình sau:

```properties
management.endpoint.health.probes.enabled=true
```

Khi cần health group ở cổng chính dành cho Kubernetes, có thể xem cấu hình `management.endpoint.health.probes.add-additional-paths=true` (đường liveness/readiness bổ sung trên server port chính; cần kiểm tra exposure và security). **Không công khai bừa bãi** tất cả management endpoints. Khi deploy, cần xác định đúng port, base path, bảo mật, service mesh, proxy và health group.

### 9.2. Probe thay đổi ra sao khi phát state?

Trong một app web có Actuator/probes được bật, trình tự khái niệm:

```text
Đang phục vụ:
    ReadinessState.ACCEPTING_TRAFFIC
    -> /actuator/health/readiness báo UP
    -> nền tảng có thể route traffic

Tạm ngừng nhận việc:
    AvailabilityChangeEvent.publish(..., REFUSING_TRAFFIC)
    -> ReadinessState.REFUSING_TRAFFIC
    -> readiness health group báo OUT_OF_SERVICE
    -> thường phản ánh qua HTTP 503
    -> nền tảng ngừng route tới pod khi lần probe sau phát hiện

Phục hồi:
    publish(..., ACCEPTING_TRAFFIC)
    -> readiness health group báo UP trở lại
    -> nền tảng có thể route traffic sau khi probe đạt
```

Đây là mô hình hành vi **khi probe và các status mapping mặc định phù hợp**, không phải cam kết rằng load balancer dừng gửi request ngay lập tức. Kubernetes probe có chu kỳ, failure thresholds và thời gian cập nhật endpoints. Traffic đang xử lý có thể vẫn tiếp tục; nếu cần drain connections phải kết hợp cơ chế shutdown/routing tương ứng.

### 9.3. Không nhầm readiness health với liveness health

Nếu chỉ phát `ReadinessState.REFUSING_TRAFFIC`, liveness có thể vẫn `CORRECT`. Mục tiêu là **rút khỏi traffic**, không phải **yêu cầu restart**. Chỉ phát `LivenessState.BROKEN` trong một tình huống thật sự không thể phục hồi về mặt nội bộ.

Cũng không nên cho liveness phụ thuộc trực tiếp vào nhiều external services. Một database outage chung không nên gây tất cả pods bị restart liên tục chỉ vì liveness probe cùng kiểm tra database.

### 9.4. `AvailabilityChangeEvent` không buộc code nhận request phải từ chối

Ứng dụng **công bố trạng thái**, còn việc giảm traffic cần môi trường điều phối thực hiện. Nếu không có load balancer/probe đọc state, service của bạn có thể vẫn nhận HTTP requests dù `ApplicationAvailability` báo `REFUSING_TRAFFIC`. Khi có yêu cầu tự chặn request tại ứng dụng, phải bổ sung logic lọc/routing thích hợp; thay đổi availability state đơn thuần không phải middleware chặn requests.

## 10. Mẫu thiết kế thực tế: tạm giảm tải và phục hồi

Một service xử lý tác vụ đôi khi quá tải do hàng đợi hoặc bộ nhớ. Dùng readiness để báo “tạm thời không nhận thêm việc” có thể hợp lý:

```text
RUNNING
  | queue depth vượt ngưỡng cao trong một khoảng ổn định
  v
PAUSED (REFUSING_TRAFFIC)
  | backlog giảm dưới ngưỡng thấp trong một khoảng ổn định
  v
RUNNING (ACCEPTING_TRAFFIC)
```

**Hysteresis** (ngưỡng cao và thấp khác nhau) giúp tránh dao động trạng thái liên tục khi metrics gần một ngưỡng. Có thể thêm thời gian tối thiểu giữa hai lần đổi state, kiểm tra sức khỏe của các dependencies thiết yếu và các điều kiện phục hồi cụ thể.

### 10.1. Ví dụ pseudo-code cho điều phối

```java
if (queueDepth >= highWatermark && currentlyAccepting) {
    AvailabilityChangeEvent.publish(
            publisher, this, ReadinessState.REFUSING_TRAFFIC);
}
else if (queueDepth <= lowWatermark && currentlyRefusing
        && dependenciesHealthy) {
    AvailabilityChangeEvent.publish(
            publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
}
```

**Đây là pseudo-code Java**, không phải một file biên dịch độc lập: cần định nghĩa `queueDepth`, thresholds, các cờ kiểm tra và dependencies. Với production, không nên dùng các cờ local thiếu đồng bộ trong nhiều threads; dùng một coordinator/state machine và bảo vệ tranh chấp phù hợp.

### 10.2. Nhiều thành phần có thể cùng công bố readiness

Vấn đề nguy hiểm: A phát `REFUSING_TRAFFIC` vì database chưa sẵn; B phát `ACCEPTING_TRAFFIC` vì cache đã xong. Nếu mỗi component tự công bố trạng thái cuối cùng, **event mới hơn có thể ghi đè trạng thái từ component khác** dù nguyên nhân từ chối của A vẫn còn.

Hãy có **một bộ điều phối readiness** để tổng hợp các lý do:

```text
databaseHealthy AND cacheReady AND queueCapacityAvailable
        => ACCEPTING_TRAFFIC
ngược lại
        => REFUSING_TRAFFIC
```

Mỗi component cập nhật trạng thái riêng của nó với coordinator; coordinator mới là nơi chủ động publish availability event theo kết quả tổng hợp. Cách này tránh “last writer wins” gây sẵn sàng giả.

### 10.3. Tránh báo ACCEPTING_TRAFFIC quá sớm

Nếu job cache warm-up bắt buộc mới bắt đầu chạy async, việc phát `ACCEPTING_TRAFFIC` là sớm. Hoàn tất công việc thật, có deadline/timeout, xác nhận trạng thái thực rồi mới chuyển sang accepting. Với tác vụ startup cần chặn ready, ưu tiên chạy/đợi trong `ApplicationRunner` hoặc một startup coordinator đúng lifecycle.

### 10.4. Trạng thái liveness là quyết định vận hành nghiêm trọng

`LivenessState.BROKEN` nên được dành cho lỗi bên trong không thể phục hồi: chẳng hạn corruption bất khả khôi phục của state nội bộ cốt lõi. Đừng dùng nó để báo latency cao hoặc dependency bên ngoài timeout tạm thời. Một event `BROKEN` không tự đóng context; cần infrastructure và runbook vận hành tương ứng.

## 11. Lỗi thường gặp

| Lỗi hoặc suy luận sai | Tác hại | Cách khắc phục |
| --- | --- | --- |
| Gọi `availability.setReadinessState(...)` | Không có setter tương ứng trong API | Phát `AvailabilityChangeEvent` |
| Gọi `AvailabilityChangeEvent.publish(publisher, state)` | Không khớp overload của Boot 3.3 | Dùng `(publisher, source, state)` hoặc `(context, state)` |
| Tạo `new AvailabilityChangeEvent` nhưng không publish | State của Boot không đổi | `publisher.publishEvent(...)` hoặc static `publish(...)` |
| Phát refusing trong `ApplicationReadyEvent` listener để giữ mãi | Boot còn công bố accepting sau ready event | Sắp xếp lifecycle phù hợp; phát sau startup nếu là thay đổi động |
| Phát liveness `BROKEN` khi DB bên ngoài timeout | Pod có thể bị restart liên tục | Xử lý retry/backoff; cân nhắc readiness, không dùng liveness cho lỗi ngoài |
| Hiểu readiness refusing là đóng socket ngay | Probe chỉ báo trạng thái; không tự đóng server | Cấu hình orchestrator/routing và drain |
| Có `AvailabilityChangeEvent` nhưng health URL không tồn tại | Ứng dụng không có Actuator/web hoặc probes chưa bật | Thêm dependencies, cấu hình probes và kiểm tra endpoint |
| Quên source trong overload publisher | Gọi sai chữ ký phương thức | Truyền `this`, exception hoặc object source có ý nghĩa |
| Dùng nhiều service tự publish `ACCEPTING_TRAFFIC` | Thành phần khỏe ghi đè thành phần chưa khỏe | Một readiness coordinator tổng hợp điều kiện |
| Giữ `REFUSING_TRAFFIC` khi ứng dụng đã phục hồi | Instance không nhận traffic mới | Publish `ACCEPTING_TRAFFIC` khi điều kiện hồi phục thật |
| Dựa vào event async rồi đọc state ngay lập tức | Thao tác có thể chưa được xử lý | Sử dụng dispatch đồng bộ hoặc test completion với timeout |
| Cho listener availability làm network I/O nặng | Chậm publish, startup, shutdown hoặc rủi ro exception | Listener nhẹ; tách tác vụ nền có quản lý |
| Log toàn bộ event source không kiểm tra | Có thể lộ thông tin nhạy cảm | Log loại state/metadata cần thiết, không dump secret |
| Đánh dấu readiness healthy thay cho kiểm tra nghiệp vụ | Đánh lừa load balancer, tăng lỗi request | Chỉ công bố accepting khi tiêu chí phục vụ được xác nhận |

### 11.1. Checklist chẩn đoán

Khi đọc trạng thái sau publish nhưng thấy giá trị cũ:

1. Đã phát event qua **đúng** `ApplicationContext` hoặc `ApplicationEventPublisher` chưa?
2. Có dùng đúng overload `publish(context, state)` hoặc `publish(publisher, source, state)` không?
3. Có listener hoặc Spring Boot startup/shutdown callback nào phát state khác sau đó không?
4. Có nhiều contexts (parent/child) khiến events được truyền lên parent hoặc bean availability cần kiểm tra khác context không?
5. Có custom event multicaster async, executor hoặc event handler gây trễ/lỗi không?
6. Có nhiều components ghi đè readiness lẫn nhau không?
7. Ứng dụng đã hoàn tất startup trước khi bạn tự đổi readiness chưa?
8. Actuator health group/probe có thực sự được bật và được platform đọc chưa?

Không kết luận một lần `getReadinessState()` trả giá trị mong muốn nghĩa là hệ thống đã ngừng nhận traffic ngay ở phía load balancer.

## 12. Những tình huống áp dụng

### 12.1. Deployment rolling update

Trước khi shutdown hoặc drain, ứng dụng có thể chuyển `REFUSING_TRAFFIC` để báo platform ngừng gửi request mới, đồng thời cho các request đang chạy thời gian kết thúc. Phải kết hợp lifecycle/drain và readiness probe, không chỉ phát event rồi exit ngay lập tức.

### 12.2. Worker xử lý hàng đợi

Khi bộ nhớ hoặc queue quá tải, worker có thể tạm từ chối công việc mới. Nếu nó không phục vụ HTTP, readiness phải được nối đến cơ chế bên điều phối/consumer thật sự sử dụng; một enum local không tự pause Kafka/RabbitMQ consumer. Có thể cần tạm dừng consumer, giảm concurrency hoặc triển khai backpressure riêng.

### 12.3. Phục hồi cấu hình runtime

Nếu ứng dụng thay đổi cấu hình hoặc reload nội bộ và chưa thể phục vụ an toàn, công bố `REFUSING_TRAFFIC`. Sau khi reload xác nhận thành công, công bố lại `ACCEPTING_TRAFFIC`. Phải bảo vệ trường hợp reload thất bại, không mở traffic chỉ vì đã qua một timeout cố định.

### 12.4. Local corruption không tự phục hồi

Nếu bộ xử lý nội bộ ở trạng thái không thể sửa mà chỉ restart mới khôi phục được, cân nhắc `LivenessState.BROKEN`. Để quyết định đưa liveness vào runbook, cần xác nhận rằng restart thực sự có thể sửa lỗi, tránh vòng lặp restart khi nguyên nhân gốc vẫn tồn tại.

### 12.5. Đo đạc và audit

Một listener `@EventListener(AvailabilityChangeEvent<ReadinessState>)` có thể ghi counter/metric về các lần tạm từ chối và thời lượng phục hồi. Tuy nhiên, event listener có thể nhận cả sự kiện Boot tự phát. Nếu cần audit, hãy ghi rõ timestamp, source, reason code (không lộ secret) và context instance ID.

## 13. Bài tập thực hành

1. Nêu khác biệt giữa `ReadinessState` và `LivenessState`. Khi nào `BROKEN` nguy hiểm hơn `REFUSING_TRAFFIC`?
2. Viết hai overload `AvailabilityChangeEvent.publish(...)` chính thức của Spring Boot 3.3. Khi nào dùng context, khi nào dùng publisher + source?
3. Giải thích vì sao `ApplicationAvailability` không phải đối tượng cần setter để cập nhật trạng thái.
4. Trong demo, vì sao phải đợi `SpringApplication.run(...)` trả về trước khi chủ động thử chuyển readiness?
5. Chạy demo và xác định nguồn gốc của event liveness `CORRECT` và readiness `ACCEPTING_TRAFFIC` đầu tiên.
6. Giải thích thứ tự `EVENT readiness=REFUSING_TRAFFIC` trước `MAIN paused=REFUSING_TRAFFIC` khi dùng multicaster đồng bộ mặc định.
7. Đổi thứ tự hai lời gọi `pauseNewTraffic()` và `resumeNewTraffic()` trong `main`; dự đoán state cuối cùng trước khi đóng context.
8. Thay `AvailabilityChangeEvent.publish(publisher, this, state)` bằng `publisher.publishEvent(new AvailabilityChangeEvent<>(this, state))`. Nêu tại sao hai cách cùng mục đích.
9. Viết listener chỉ nhận `AvailabilityChangeEvent<LivenessState>` rồi in `BROKEN` khi thích hợp; **không** thêm đường thử cố ý báo broken cho môi trường production.
10. Giải thích vì sao Spring Boot có thể phát accepting sau một ready listener đã phát refusing.
11. Thêm integration test kiểm tra hai chuyển đổi readiness, không dựa vào trạng thái trước test.
12. Xây một coordinator giả định có hai điều kiện `databaseHealthy` và `cacheReady`. Chỉ publish `ACCEPTING_TRAFFIC` nếu cả hai true; lý giải rủi ro khi hai component tự publish độc lập.
13. Nếu load balancer vẫn gửi request sau khi readiness đã refusing, bạn sẽ kiểm tra các yếu tố platform nào?
14. Đề xuất hysteresis cho queue depth: ví dụ ngưỡng cao 900 để refusing, ngưỡng thấp 300 để accepting. Vì sao hai ngưỡng khác nhau giảm oscillation?
15. Trong app CLI không có Actuator, điều gì vẫn xảy ra khi `AvailabilityChangeEvent` được publish, và điều gì **không tự xuất hiện**?
16. Tại sao không được coi event `BROKEN` là lời gọi tương đương `System.exit(1)`?
17. Mở rộng app thành web có Actuator probes. Nêu cấu hình tối thiểu và những điểm cần kiểm chứng trước khi deploy Kubernetes.
18. Nếu một listener xử lý bất đồng bộ và state thay đổi liên tục, bạn sẽ kiểm thử ordering, timeout và trạng thái mới nhất bằng cách nào?
19. Phân biệt application readiness state với health của một external service riêng. Khi nào cần endpoint health group tùy chỉnh?
20. Thiết kế trạng thái readiness cho worker queue, bao gồm dừng nhận việc, hoàn tất việc đang xử lý và phục hồi, mà không restart tiến trình.

**Tiêu chí đạt:** giải thích và dùng đúng event API; chủ động phát `REFUSING_TRAFFIC`/`ACCEPTING_TRAFFIC`; đọc state mới bằng `ApplicationAvailability`; hiểu Boot có các event tự động; biết giới hạn của liveness, readiness và sự tương tác với platform.

## 14. Tài liệu chính thức

- Spring Boot 3.3.13 — `AvailabilityChangeEvent` API (hai overload `publish`): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html
- Spring Boot 3.3.13 — `ApplicationAvailability` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ApplicationAvailability.html
- Spring Boot 3.3.13 — `ReadinessState` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ReadinessState.html
- Spring Boot 3.3.13 — `LivenessState` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/LivenessState.html
- Spring Boot 3.3.13 — Application Availability & Events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — Actuator endpoints/probes: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
