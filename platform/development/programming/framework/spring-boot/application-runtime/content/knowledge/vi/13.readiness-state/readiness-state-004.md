# Đọc trạng thái hiện tại qua ApplicationAvailability trong Spring Boot

## 1. Mục tiêu bài học và ý nghĩa của “trạng thái hiện tại”

Spring Boot có cơ chế **application availability** để ứng dụng và hệ thống vận hành hiểu hai câu hỏi riêng biệt:

1. **Liveness:** tiến trình và trạng thái nội bộ còn đủ đúng để tiếp tục chạy hoặc tự hồi phục hay không?
2. **Readiness:** ở thời điểm hiện tại, instance có **sẵn sàng nhận lưu lượng mới** hay không?

Cơ chế này nằm trong `org.springframework.boot.availability`. Khi muốn **đọc ảnh chụp trạng thái đang được Spring Boot biết**, hãy inject interface `ApplicationAvailability` rồi gọi `getLivenessState()`, `getReadinessState()`, hoặc các phương thức tổng quát `getState(...)`.

Điều cần phân biệt ngay từ đầu:

- `ApplicationAvailability` trả về **trạng thái do các availability events cuối cùng công bố** và các giá trị fallback hợp lý, không tự chạy kiểm tra database hoặc một HTTP health check mỗi lần gọi.
- `AvailabilityChangeEvent<S>` là sự kiện **thay đổi trạng thái**; một component muốn tự thay đổi readiness/liveness phải publish event, không gọi setter vì interface `ApplicationAvailability` không có setter.
- `ApplicationAvailabilityBean` là implementation có sẵn của Boot, nhận `AvailabilityChangeEvent` để giữ thông tin mới nhất. Ở business code, **inject interface** thay vì phụ thuộc trực tiếp implementation.
- Spring Boot dùng cơ chế availability cả trong ứng dụng web, command-line và batch. Để nền tảng bên ngoài quan sát qua HTTP, cần thêm lớp health/probe thích hợp, thường là Spring Boot Actuator.

~~~mermaid
flowchart LR
    E["Spring Boot lifecycle và application code"] -->|"publish"| EV["AvailabilityChangeEvent"]
    EV -->|"listener lưu trạng thái"| A["ApplicationAvailabilityBean"]
    A -->|"implements"| API["ApplicationAvailability"]
    API -->|"getLivenessState / getReadinessState"| S["Bean nghiệp vụ, runner, exporter"]
    A -->|"health indicator khi có Actuator"| P["Health probe cho nền tảng"]
~~~

Đây là sơ đồ luồng dữ liệu, không phải mô tả chi tiết thứ tự listener đồng bộ/bất đồng bộ trong mọi cấu hình.

## 2. Hai loại state không thay thế nhau

| Nhóm | Trạng thái | Ý nghĩa | Quyết định phổ biến của nền tảng |
| --- | --- | --- | --- |
| `LivenessState` | `CORRECT` | Trạng thái nội bộ được đánh giá còn hoạt động đúng hoặc có thể tự phục hồi | Tiếp tục cho instance chạy |
| `LivenessState` | `BROKEN` | Trạng thái nội bộ đã hỏng, không thể tự phục hồi đáng tin | Có thể restart tiến trình/container khi liveness probe thất bại |
| `ReadinessState` | `ACCEPTING_TRAFFIC` | Instance sẵn sàng được điều hướng lưu lượng mới | Cho tham gia tập endpoint phục vụ |
| `ReadinessState` | `REFUSING_TRAFFIC` | Instance tạm thời không nên nhận lưu lượng mới | Tạm loại khỏi nơi route traffic, không nhất thiết restart |

**Liveness khác readiness.** Một instance có thể `CORRECT` về liveness nhưng vẫn `REFUSING_TRAFFIC` về readiness, điển hình là khi `ApplicationRunner` đang khởi tạo dữ liệu sau lúc context refresh. Ngược lại, khi một thành phần thật sự hỏng không thể khôi phục, việc báo liveness `BROKEN` mang hệ quả mạnh hơn: orchestrator có thể restart container.

Không nên chuyển liveness sang `BROKEN` chỉ vì một database, cache hoặc external API tạm thời không phản hồi: restart toàn bộ replica thường không sửa được dependency chung, thậm chí gây cascading failure. Đối với readiness, có thể kiểm tra thêm những điều kiện thật sự cần cho khả năng phục vụ, nhưng cũng phải xét rủi ro toàn bộ instance bị loại khỏi load balancer cùng lúc.

### Điều API có thể và không thể kết luận

Nếu:

~~~java
ReadinessState readiness = availability.getReadinessState();
~~~

và giá trị là `ACCEPTING_TRAFFIC`, ta biết state **do application availability quản lý** hiện là accepting. Điều đó không tự chứng minh DNS, ingress, kết nối giữa các node, security filter hay database đều khỏe. Ngược lại, readiness `REFUSING_TRAFFIC` không tự làm đóng cổng TCP; platform phải dùng probe hoặc tích hợp khác để điều hướng.

Đọc state là thao tác lấy trạng thái quan sát **tại thời điểm gọi**. Sau khi trả về, một thread/event khác vẫn có thể publish state mới; không coi một lần đọc là khóa bất biến cho toàn bộ một workflow kéo dài.

## 3. API quan trọng nhất của ApplicationAvailability

Interface `ApplicationAvailability` có các phương thức sau trong Spring Boot 3.5.x:

| Phương thức | Kiểu trả về | Ngữ nghĩa |
| --- | --- | --- |
| `getLivenessState()` | `LivenessState` | Lấy liveness mới nhất hoặc fallback `BROKEN` nếu chưa có event của loại này |
| `getReadinessState()` | `ReadinessState` | Lấy readiness mới nhất hoặc fallback `REFUSING_TRAFFIC` nếu chưa có event của loại này |
| `getState(LivenessState.class)` | `LivenessState` hoặc `null` | Trạng thái **đã được sự kiện công bố**; `null` khi chưa có event của loại này |
| `getState(ReadinessState.class)` | `ReadinessState` hoặc `null` | Tương tự cho readiness, không tự áp dụng fallback |
| `getState(ReadinessState.class, ReadinessState.REFUSING_TRAFFIC)` | `ReadinessState` | Phiên bản có fallback do caller cung cấp, bắt buộc non-null |
| `getLastChangeEvent(ReadinessState.class)` | `AvailabilityChangeEvent<ReadinessState>` hoặc `null` | Sự kiện readiness gần nhất **mà implementation đã nhận** |
| `getLastChangeEvent(LivenessState.class)` | `AvailabilityChangeEvent<LivenessState>` hoặc `null` | Sự kiện liveness gần nhất đã nhận |

### 3.1 Đọc ngắn gọn qua hai convenience methods

~~~java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;

boolean live = availability.getLivenessState()
        == LivenessState.CORRECT;

boolean ready = availability.getReadinessState()
        == ReadinessState.ACCEPTING_TRAFFIC;
~~~

Đoạn trên đặt trong method của class có biến `availability` đã được inject. Đây là hai cách đọc ưu tiên nếu chỉ cần quyết định live/ready theo chính sách mặc định.

### 3.2 Hiểu rõ giá trị fallback, tránh giải thích nhầm

Theo source của interface, logic tương đương:

~~~java
default LivenessState getLivenessState() {
    return getState(LivenessState.class, LivenessState.BROKEN);
}

default ReadinessState getReadinessState() {
    return getState(
            ReadinessState.class,
            ReadinessState.REFUSING_TRAFFIC);
}
~~~

**Hệ quả:** khi không có sự kiện availability nào từng được phát cho loại đó, hai convenience methods vẫn trả về một trạng thái **an toàn**. Chúng không cần tạo “sự kiện giả” để có fallback.

Ngược lại, `getState(ReadinessState.class)` có thể là `null` khi chưa có readiness event. Vì vậy:

~~~java
ReadinessState raw = availability.getState(ReadinessState.class);

// Có thể true ở lúc startup dù convenience method trả REFUSING_TRAFFIC.
boolean notYetPublished = raw == null;

ReadinessState safe = availability.getState(
        ReadinessState.class,
        ReadinessState.REFUSING_TRAFFIC);
~~~

**Không được kết luận** rằng `getReadinessState() == REFUSING_TRAFFIC` chứng minh đã phát một event `REFUSING_TRAFFIC`. Giá trị đó có thể chỉ là fallback.

### 3.3 Vì sao getState(Class, defaultState) hữu ích?

Overload tổng quát cho phép một `AvailabilityState` được đọc với fallback do bạn đặt, miễn là fallback **không null** và cùng kiểu với `stateType`. Ví dụ:

~~~java
LivenessState liveState = availability.getState(
        LivenessState.class,
        LivenessState.BROKEN);
~~~

Đây là hình thức tường minh của cách convenience method chọn mặc định. Với loại trạng thái tùy biến do một extension cung cấp, overload này cũng hữu ích để xác định chính sách khi chưa nhận event. Nhưng ứng dụng thông thường chỉ cần hai enum tiêu chuẩn; không nhất thiết phải tự tạo availability state loại mới.

### 3.4 getLastChangeEvent: khi cần biết event gần nhất

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;

AvailabilityChangeEvent<ReadinessState> latest =
        availability.getLastChangeEvent(ReadinessState.class);

if (latest == null) {
    System.out.println("No readiness event has been received");
} else {
    System.out.println("Last readiness event state=" + latest.getState());
}
~~~

Ngoài `getState()`, `AvailabilityChangeEvent` kế thừa khả năng đọc `getSource()` và `getTimestamp()` từ Spring application event. Chúng có thể hữu ích để chẩn đoán, nhưng **không** phải một lịch sử đầy đủ, không có guarantee tính liên tục như event log bền vững, và timestamp sự kiện không tự là thời gian “đến lúc sẵn sàng”.

Các giới hạn cần nhớ:
- Trả **event gần nhất của một loại state**, không phải toàn bộ sự kiện từ lúc tiến trình start.
- Có thể là `null` khi chưa nhận event nào của loại đó.
- Một app hoặc thư viện có thể tự publish event thay đổi state; không phải mọi event đều có nguồn từ các mốc startup của Boot.
- Trạng thái “mới nhất” là theo thứ tự sự kiện mà implementation đã **nhận**, không nhất thiết trùng thứ tự thời gian thực giữa nhiều publisher trong những thiết kế async phức tạp.

## 4. Cơ chế lưu state và mối quan hệ với AvailabilityChangeEvent

Spring Boot cung cấp `ApplicationAvailabilityBean`, vừa implement `ApplicationAvailability` vừa là listener cho `AvailabilityChangeEvent<?>`. Khi nó nhận sự kiện state, nó ghi nhận event đó để việc đọc qua `getState(...)` và `getLastChangeEvent(...)` phản ánh thông tin mới.

Để **đổi state**, ứng dụng phải publish `AvailabilityChangeEvent` qua Spring event infrastructure:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
class TrafficAdmission {
    private final ApplicationEventPublisher publisher;

    TrafficAdmission(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    void pause() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.REFUSING_TRAFFIC);
    }

    void resume() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

Đây là class minh họa một chính sách runtime: `pause()` dùng khi instance cần tạm rút khỏi routing; `resume()` chỉ gọi khi đã xác nhận điều kiện phục vụ thực sự đạt. Nó **không** tự chạy vào lúc startup, không phải giải pháp cho mọi lỗi database, và không trực tiếp đóng socket hay restart pod.

Ở event publishing mặc định đồng bộ, `ApplicationAvailabilityBean` thường cập nhật state trong quá trình xử lý event. Nếu dự án tùy biến multicaster/executor, không nên dựa vào giả định mọi listener đã hoàn tất cập nhật tức thì. Trong code thực cần đồng bộ, đọc lại sau khi publish và thiết kế rõ ràng chuỗi xử lý.

### Vì sao không sửa trực tiếp ApplicationAvailabilityBean?

`ApplicationAvailability` là giao diện **read-oriented**. Truy cập implementation để gọi `onApplicationEvent(...)` trực tiếp sẽ bỏ qua event multicaster và các listener khác; thậm chí dùng một instance implementation tự tạo không liên quan context đang chạy. Muốn state mới được hệ thống quan sát nhất quán, hãy **publish event** qua `ApplicationContext` hoặc `ApplicationEventPublisher`.

### Nghe thay đổi thay vì polling liên tục

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class ReadinessAudit {
    @EventListener
    public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("READINESS_CHANGED=" + event.getState());
    }
}
~~~

Nếu cần hành động ở **mỗi lần readiness đổi**, listener phù hợp hơn việc polling lặp mỗi vài mili-giây. Nếu chỉ cần **snapshot ngay lúc một request/job bắt đầu**, inject `ApplicationAvailability` rồi đọc trực tiếp.

## 5. Trạng thái thay đổi thế nào trong startup?

Một phần quan trọng của việc đọc state là hiểu **đọc vào mốc nào**.

~~~mermaid
flowchart TD
    A["SpringApplication.run(args)"] --> B["Chuẩn bị Environment/Context"]
    B --> C["refresh ApplicationContext"]
    C --> D["ApplicationStartedEvent"]
    D --> E["AvailabilityChangeEvent: LivenessState.CORRECT"]
    E --> F["ApplicationRunner / CommandLineRunner"]
    F --> G["ApplicationReadyEvent"]
    G --> H["AvailabilityChangeEvent: ReadinessState.ACCEPTING_TRAFFIC"]
~~~

Bảng cho startup thành công tiêu chuẩn:

| Pha | `getLivenessState()` | `getReadinessState()` | Nguyên nhân |
| --- | --- | --- | --- |
| Trước khi có liveness event | `BROKEN` (fallback) | `REFUSING_TRAFFIC` (fallback) | Chưa được công bố live/ready |
| Trong listener `ApplicationStartedEvent` | Thường vẫn `BROKEN` nếu chưa có event liveness | `REFUSING_TRAFFIC` | Boot phát liveness event **sau** started |
| Trong `ApplicationRunner` thông thường | `CORRECT` | `REFUSING_TRAFFIC` | Started/liveness đã xong; runner chưa hoàn tất |
| Trong listener `ApplicationReadyEvent` | `CORRECT` | Thường vẫn `REFUSING_TRAFFIC` | Boot phát readiness accepting event **sau** ready |
| Sau `AvailabilityChangeEvent<ReadinessState>` với accepting | `CORRECT` | `ACCEPTING_TRAFFIC` | Boot đánh dấu instance ready |

Bảng giả định **không có listener hoặc thành phần custom tự publish state khác**. Trong một ứng dụng thực, có thể có thay đổi readiness giữa các mốc, ví dụ hệ thống tạm drain traffic.

### Đọc ngay trong ApplicationStartedEvent

`ApplicationStartedEvent` diễn ra sau khi context đã refresh nhưng **trước khi** Boot publish `LivenessState.CORRECT`. Nếu callback đọc `getLivenessState()` mà thấy `BROKEN`, không nhất thiết có nghĩa ứng dụng gặp sự cố: đó có thể là fallback trước event liveness. Hãy phân biệt trạng thái do sự kiện thực sự công bố với giá trị fallback, và đừng dùng một lần đọc quá sớm để đưa ra kết luận vận hành sai.

### Đọc trong ApplicationRunner

Runner chạy sau liveness CORRECT và trước readiness ACCEPTING_TRAFFIC. Đây là vị trí hữu ích để demo snapshot:

~~~java
@Bean
ApplicationRunner inspect(ApplicationAvailability availability) {
    return args -> {
        System.out.println(availability.getLivenessState());
        System.out.println(availability.getReadinessState());
    };
}
~~~

Đặt method này trong một `@Configuration` hoặc class có `@SpringBootApplication`, với import phù hợp. Khi startup không có availability event custom, hai dòng do runner in thường là:

~~~text
CORRECT
REFUSING_TRAFFIC
~~~

Đây không phải lỗi readiness; runner chính là một phần công việc cần hoàn thành **trước** mốc ready.

### Đọc trong ApplicationReadyEvent

`ApplicationReadyEvent` được publish sau runners, nhưng **ngay sau event này** Boot mới publish `AvailabilityChangeEvent<ReadinessState>` với `ACCEPTING_TRAFFIC`. Vì vậy trong một `@EventListener(ApplicationReadyEvent)` đồng bộ, trạng thái readiness có thể vẫn `REFUSING_TRAFFIC`. Muốn bắt chính xác bước chuyển, nhận sự kiện typed `AvailabilityChangeEvent<ReadinessState>`.

### Shutdown và trạng thái sau ready

Trong graceful shutdown, Boot có thể chuyển readiness về `REFUSING_TRAFFIC` để platform ngừng route request mới. Liveness có thể vẫn `CORRECT` trong giai đoạn drain hợp lệ. Sau khi context đóng, không nên dựa vào một bean availability đã không còn lifecycle thích hợp để truy vấn từ bên ngoài.

Với ứng dụng CLI/batch, cũng có state và events dù không có HTTP server. Do đó `ACCEPTING_TRAFFIC` trong một CLI app biểu thị mốc availability của Boot, không có nghĩa app đã mở socket HTTP.

## 6. Ví dụ hoàn chỉnh Java 17+, Maven và Spring Boot 3.5.x

Mục tiêu là **đọc trạng thái thật ở các thời điểm khác nhau**, quan sát `getLastChangeEvent(...)`, phân biệt event với snapshot và nhìn thấy rõ khoảng giữa started với ready.

Tạo project Maven sau. Nó không dùng web starter hay Actuator, để chứng minh availability là tính năng của Spring Boot core.

~~~text
availability-reader/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/availability/
    │       ├── AvailabilityReaderApplication.java
    │       └── StartupAvailabilityObserver.java
    └── test/
        └── java/com/example/availability/
            └── ApplicationAvailabilityBeanTest.java
~~~

### File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>availability-reader</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
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
~~~

### File src/main/java/com/example/availability/AvailabilityReaderApplication.java

~~~java
package com.example.availability;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class AvailabilityReaderApplication {

    public static void main(String[] args) {
        SpringApplication.run(AvailabilityReaderApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectState(ApplicationAvailability availability) {
        return args -> {
            System.out.println("03.RUNNER_LIVENESS="
                    + availability.getLivenessState());
            System.out.println("04.RUNNER_READINESS="
                    + availability.getReadinessState());

            AvailabilityChangeEvent<LivenessState> event =
                    availability.getLastChangeEvent(LivenessState.class);

            System.out.println("05.LAST_LIVENESS_EVENT="
                    + (event == null ? "none" : event.getState()));
        };
    }
}
~~~

### File src/main/java/com/example/availability/StartupAvailabilityObserver.java

~~~java
package com.example.availability;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupAvailabilityObserver {

    private final ApplicationAvailability availability;

    public StartupAvailabilityObserver(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("01.STARTED_SNAPSHOT="
                + availability.getLivenessState());
    }

    @EventListener
    public void onLiveness(AvailabilityChangeEvent<LivenessState> event) {
        if (event.getState() == LivenessState.CORRECT) {
            System.out.println("02.LIVENESS_EVENT=CORRECT");
        }
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("06.READY_SNAPSHOT="
                + availability.getReadinessState());
    }

    @EventListener
    public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
        if (event.getState() == ReadinessState.ACCEPTING_TRAFFIC) {
            System.out.println("07.READINESS_EVENT=ACCEPTING_TRAFFIC");
        }
    }
}
~~~

Chú ý: trong `onLiveness` và `onReadiness`, ta in **payload của sự kiện** thay vì đọc lại `ApplicationAvailability` ngay trong callback của cùng event. Điều này tránh ngầm dựa vào thứ tự chạy giữa listener ghi state và listener custom. Trong runner và listener ở mốc tiếp theo, đọc snapshot đã có khoảng thời gian lifecycle rõ ràng hơn.

### Chạy ứng dụng

Từ thư mục chứa `pom.xml`, với Maven và Java 17+:

~~~bash
mvn -q test
mvn -q -DskipTests package
java -jar target/availability-reader-0.0.1-SNAPSHOT.jar
~~~

Những dòng **do code ví dụ chủ động in ra** với startup mặc định:

~~~text
01.STARTED_SNAPSHOT=BROKEN
02.LIVENESS_EVENT=CORRECT
03.RUNNER_LIVENESS=CORRECT
04.RUNNER_READINESS=REFUSING_TRAFFIC
05.LAST_LIVENESS_EVENT=CORRECT
06.READY_SNAPSHOT=REFUSING_TRAFFIC
07.READINESS_EVENT=ACCEPTING_TRAFFIC
~~~

Spring Boot có thể in thêm banner và log khác xen kẽ; khối này chỉ liệt kê những dòng có prefix từ `01.` đến `07.`. Kết quả trên giả định startup đồng bộ chuẩn, không có publisher/listener custom bổ sung làm thay đổi state.

Giải thích:
1. `01`: trong `ApplicationStartedEvent`, Boot chưa publish liveness CORRECT event chuẩn, nên convenience method trả fallback BROKEN.
2. `02`: listener nhận event liveness CORRECT được Boot phát sau started.
3. `03`: runner đọc liveness mới nhất và nhận CORRECT.
4. `04`: readiness vẫn REFUSING_TRAFFIC, vì runner chưa kết thúc.
5. `05`: sự kiện liveness gần nhất đã được lưu với state CORRECT.
6. `06`: khi callback `ApplicationReadyEvent` đang chạy, availability event readiness ACCEPTING_TRAFFIC chuẩn chưa được publish; snapshot vẫn refusing.
7. `07`: listener nhận chính event readiness ACCEPTING_TRAFFIC.

**Đừng suy diễn từ một lần chạy CLI** rằng ứng dụng có web endpoint: ví dụ này không có web server, nên process có thể kết thúc nhanh sau khi các startup callbacks hoàn tất. Trạng thái và event vẫn có ý nghĩa bên trong Boot lifecycle.

### Chuyện gì xảy ra nếu runner thất bại?

Nếu thêm một runner ném exception trước khi ready, Spring Boot có thể đã phát liveness `CORRECT`, nhưng đường startup không đi đến ready/readiness accepting bình thường. Lần chạy có thể chuyển sang `ApplicationFailedEvent`. Đây là ví dụ cho sự khác biệt giữa “context đã refresh” và “startup thành công toàn bộ”.

## 7. Unit test: phân biệt default, null và event thật

Để kiểm tra behavior của implementation mà không cần tạo context và không cần web server, có thể khởi tạo `ApplicationAvailabilityBean` trực tiếp rồi đưa event vào **như một unit test cho class đó**. Việc gọi `onApplicationEvent` trực tiếp chỉ phục vụ test; ở ứng dụng production nên publish thông qua Spring event infrastructure như mục 4.

### File src/test/java/com/example/availability/ApplicationAvailabilityBeanTest.java

~~~java
package com.example.availability;

import org.junit.jupiter.api.Test;
import org.springframework.boot.availability.ApplicationAvailabilityBean;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;

import static org.junit.jupiter.api.Assertions.*;

class ApplicationAvailabilityBeanTest {

    @Test
    void defaultsExistBeforeAnyEvent() {
        ApplicationAvailabilityBean availability =
                new ApplicationAvailabilityBean();

        assertEquals(
                LivenessState.BROKEN,
                availability.getLivenessState());
        assertEquals(
                ReadinessState.REFUSING_TRAFFIC,
                availability.getReadinessState());

        // Phiên bản không fallback vẫn null.
        assertNull(availability.getState(LivenessState.class));
        assertNull(availability.getState(ReadinessState.class));
        assertNull(
                availability.getLastChangeEvent(ReadinessState.class));

        assertEquals(
                ReadinessState.REFUSING_TRAFFIC,
                availability.getState(
                        ReadinessState.class,
                        ReadinessState.REFUSING_TRAFFIC));
    }

    @Test
    void lastEventAndCurrentStateAdvanceTogether() {
        ApplicationAvailabilityBean availability =
                new ApplicationAvailabilityBean();

        AvailabilityChangeEvent<ReadinessState> accepting =
                new AvailabilityChangeEvent<>(
                        "unit-test", ReadinessState.ACCEPTING_TRAFFIC);

        availability.onApplicationEvent(accepting);

        assertEquals(
                ReadinessState.ACCEPTING_TRAFFIC,
                availability.getReadinessState());
        assertSame(
                accepting,
                availability.getLastChangeEvent(ReadinessState.class));
        assertEquals(
                "unit-test",
                availability.getLastChangeEvent(ReadinessState.class)
                        .getSource());

        AvailabilityChangeEvent<ReadinessState> refusing =
                new AvailabilityChangeEvent<>(
                        "maintenance", ReadinessState.REFUSING_TRAFFIC);

        availability.onApplicationEvent(refusing);

        assertEquals(
                ReadinessState.REFUSING_TRAFFIC,
                availability.getReadinessState());
        assertSame(
                refusing,
                availability.getLastChangeEvent(ReadinessState.class));

        // Chưa có liveness event: hai loại state độc lập.
        assertNull(availability.getState(LivenessState.class));
        assertEquals(
                LivenessState.BROKEN,
                availability.getLivenessState());
    }

    @Test
    void livenessEventDoesNotOverwriteReadiness() {
        ApplicationAvailabilityBean availability =
                new ApplicationAvailabilityBean();

        availability.onApplicationEvent(
                new AvailabilityChangeEvent<>(
                        this, LivenessState.CORRECT));

        assertEquals(
                LivenessState.CORRECT,
                availability.getLivenessState());
        assertEquals(
                ReadinessState.REFUSING_TRAFFIC,
                availability.getReadinessState());
        assertNull(
                availability.getLastChangeEvent(ReadinessState.class));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Ba test có chủ đích:
- Test 1 cho thấy `getReadinessState()` có thể trả `REFUSING_TRAFFIC` ngay cả khi `getState(ReadinessState.class)` và `getLastChangeEvent(ReadinessState.class)` là `null`.
- Test 2 cho thấy event mới nhất của **cùng loại** thay thế event cũ trong snapshot, và giữ thông tin source.
- Test 3 cho thấy liveness và readiness là **hai loại state độc lập**, không phải một enum hoặc một cờ boolean chung.

Không dùng unit test implementation này để suy ra rằng mọi Spring Boot integration startup đều có cùng thứ tự thực thi. Muốn kiểm chứng mốc `ApplicationStartedEvent`/`ApplicationReadyEvent`, chạy ứng dụng ví dụ đầy đủ ở mục 6 hoặc viết integration test cho `SpringApplication.run(...)`.

## 8. Đọc state trong service nghiệp vụ

Một service có thể inject `ApplicationAvailability` như collaborator bình thường:

~~~java
package com.example.availability;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Service;

@Service
public class AdmissionPolicy {
    private final ApplicationAvailability availability;

    public AdmissionPolicy(ApplicationAvailability availability) {
        this.availability = availability;
    }

    public boolean canAcceptNewWork() {
        return availability.getReadinessState()
                == ReadinessState.ACCEPTING_TRAFFIC;
    }
}
~~~

Đặt class này trong package được component scan. `canAcceptNewWork()` đọc snapshot hiện tại của state; nếu workflow enqueue job có độ ưu tiên cao, còn cần cơ chế đồng bộ/idempotency riêng để chống race khi readiness đổi ngay sau lần đọc.

### Dùng một snapshot cho một quyết định ngắn

~~~java
ReadinessState state = availability.getReadinessState();

if (state == ReadinessState.ACCEPTING_TRAFFIC) {
    // Có thể cân nhắc nhận đơn vị công việc mới.
} else {
    // Tạm từ chối hoặc đưa vào hàng đợi theo chính sách.
}
~~~

Đoạn này chỉ là skeleton logic của method, không phải một hệ thống admission control hoàn chỉnh. Nếu service ở sau load balancer đã có readiness probe, bạn có thể không cần thực hiện check ở mỗi request. Ngược lại, với consumer đọc từ queue, trạng thái readiness của HTTP route chưa chắc tự pause polling queue; cần controller của chính consumer hoặc cơ chế pause/resume tương ứng.

### Tránh kiểm tra khả dụng trong constructor hoặc @PostConstruct

Constructor và `@PostConstruct` được chạy trong lúc container tạo bean, **trước** khi các mốc started/ready xảy ra. Đọc state ở đó có thể trả fallback BROKEN/REFUSING_TRAFFIC rất bình thường. Không ném startup exception chỉ vì bean mới tạo đọc thấy `getReadinessState() != ACCEPTING_TRAFFIC`; nó chưa thể accepting cho đến khi startup hoàn tất.

Nếu cần chạy kiểm tra sau context refresh mà trước ready, dùng `ApplicationRunner` và xử lý kết quả theo yêu cầu. Nếu cần callback khi readiness chuyển từ refusing sang accepting, dùng `@EventListener` nhận `AvailabilityChangeEvent<ReadinessState>`.

## 9. Đọc event và snapshot không phải cùng một thao tác

Câu hỏi vận hành cần quyết định API:

| Cần biết | Cách dùng |
| --- | --- |
| “Bây giờ có đang ready không?” | `getReadinessState() == ACCEPTING_TRAFFIC` |
| “Bây giờ có đang live không?” | `getLivenessState() == CORRECT` |
| “Đã từng nhận event readiness chưa?” | `getLastChangeEvent(ReadinessState.class) != null` |
| “Giá trị nào thực sự được event publish lần cuối?” | `getState(ReadinessState.class)`, nhớ có thể null |
| “Đọc kèm fallback rõ ràng?” | `getState(ReadinessState.class, REFUSING_TRAFFIC)` |
| “Mỗi khi readiness thay đổi thì xử lý ngay?” | `@EventListener` với `AvailabilityChangeEvent<ReadinessState>` |
| “Ai/cái gì là source của event gần nhất?” | `getLastChangeEvent(...).getSource()` sau null check |
| “Cần toàn bộ lịch sử thay đổi?” | Thiết lập log/metrics/event storage riêng; API chỉ giữ event gần nhất |

**Snapshot không tạo ra event:** gọi `getReadinessState()` một nghìn lần không phát một nghìn `AvailabilityChangeEvent`.

**Event không đồng nghĩa health probe:** đọc `event.getState()` trong application event listener không có nghĩa Kubernetes đã biết state mới; kubelet quan sát kết quả probe theo chu kỳ và thông số cấu hình.

### Không dùng timestamp như một thời lượng

`ApplicationEvent.getTimestamp()` có thể cho biết thời điểm đối tượng event được tạo. Nhưng từ timestamp một mình không thể kết luận độ trễ giữa service nhận event và platform bắt đầu route traffic, cũng không thể suy ra thời gian hoàn thành database warm-up. Muốn đo duration, cần mốc thời gian start/end phù hợp với đồng hồ và metrics riêng.

## 10. Quan hệ với Actuator liveness/readiness probes

Khi ứng dụng dùng Spring Boot Actuator và web runtime, availability states có thể được biểu diễn bằng health indicators/groups cho hạ tầng quan sát. Các đường dẫn phổ biến:

- `/actuator/health/liveness` tương ứng `LivenessState`.
- `/actuator/health/readiness` tương ứng `ReadinessState`.

Nếu bật health probes ở môi trường không tự bật:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Đây là cấu hình **chỉ liên quan khi có Actuator và web endpoint thích hợp**. Nó không tự mở web server trong một ứng dụng chỉ có `spring-boot-starter` như mục 6.

### Đọc state trong Java hay gọi endpoint qua HTTP?

- **Trong cùng tiến trình:** inject `ApplicationAvailability`, thao tác nhanh, không cần HTTP request, không phụ thuộc vào management port.
- **Từ orchestrator hoặc máy bên ngoài:** dùng health probe qua Actuator/HTTP hay probe khác; nơi bên ngoài không thể inject một bean của tiến trình JVM đang chạy.
- **Khi cần check end-to-end:** dùng endpoint/health checks riêng phù hợp mục tiêu, thay vì kỳ vọng liveness/readiness thuần túy phản ánh toàn bộ upstream.

### Cơ chế probe có thể ra mã HTTP gì?

Trong cấu hình Actuator điển hình, liveness `CORRECT` tương ứng health `UP`, `BROKEN` tương ứng `DOWN`; readiness `ACCEPTING_TRAFFIC` tương ứng `UP`, `REFUSING_TRAFFIC` tương ứng `OUT_OF_SERVICE`. Các health status có mapping HTTP mặc định nhưng có thể cấu hình lại; không viết client business buộc phải khớp một mã HTTP duy nhất mà không xét policy của app.

Ví dụ lệnh quan sát nếu endpoint đã được bật:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

Các lệnh này **không dùng** với ứng dụng CLI của mục 6 vì project đó không khởi chạy web server. Với ứng dụng production, cần xác nhận base path, management port, Spring Security, network policy, ingress và quyền truy cập probe.

### Nếu management port khác business port

Một probe chỉ tới management port có thể khỏe trong khi business connector có vấn đề. Spring Boot hỗ trợ thêm alias probe vào cổng ứng dụng chính, khi có điều kiện phù hợp:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

Những alias mặc định thường là `/livez` và `/readyz` trên main server port; hãy xác nhận đường dẫn hiệu lực thực tế trước khi cấu hình Kubernetes.

### Kubernetes thường sử dụng state thế nào?

Liveness failure có thể khiến kubelet restart container. Readiness failure thường khiến pod bị loại khỏi tập endpoint nhận traffic của Service. Việc ứng dụng publish `ReadinessState.REFUSING_TRAFFIC` **không** tự thay đổi Kubernetes object; Actuator/probe endpoint phải phản ánh state, và kubelet cần có probe cấu hình đúng để quan sát.

Trong startup lâu, có thể cần `startupProbe` để không restart container trước khi context refresh và liveness được đánh dấu CORRECT. Cấu hình probe phải căn cứ vào thời gian startup thực đo, tránh quá nhạy gây restart liên tục.

## 11. Tình huống vận hành: đọc state theo đúng mục đích

### A. Warm-up sau khi context refresh

Một runner cần nạp local lookup table. Trong runner, trạng thái thường là `CORRECT` / `REFUSING_TRAFFIC`. Đó là điều mong đợi: không nên fail vì thấy readiness refusing khi chính runner chưa hoàn tất. Sau runner, Boot mới publish mốc ready.

### B. Tạm dừng nhận traffic nhưng không restart process

Ứng dụng cần maintenance hoặc chuyển vai trò. Nó publish `ReadinessState.REFUSING_TRAFFIC`, giữ liveness `CORRECT`. Các component có thể kiểm tra `getReadinessState()` trước khi nhận job mới. Kubelet sẽ quan sát readiness probe và ngừng route traffic theo chu kỳ của nó.

### C. Cache nội bộ mất khả năng tự phục hồi

Nếu một thành phần thực sự hỏng không thể phục hồi, ứng dụng có thể publish `LivenessState.BROKEN`. Đừng làm điều này cho một timeout ngoài đơn lẻ. Sau khi publish, việc restart còn tùy thuộc platform, cấu hình probe và chính sách restart.

### D. Không còn event nào trong implementation vừa tự tạo

Một unit test gọi `new ApplicationAvailabilityBean()` mà không đưa event vào sẽ nhận fallback BROKEN/REFUSING_TRAFFIC, trong khi `getState(...)` trả null. Không nên xem đó là lỗi “Spring Boot chưa chạy”: object test tự tạo vốn chưa là bean đăng ký trong application lifecycle.

### E. Sau graceful shutdown

Khi app bắt đầu ngừng phục vụ, readiness có thể trở về `REFUSING_TRAFFIC` để nhận ít traffic mới, trong khi liveness vẫn là CORRECT trong thời gian xử lý các request đang chạy. Sau khi context đóng, đừng giữ một reference tới bean availability để làm health check ngoài tiến trình.

## 12. Lỗi thường gặp và cách chẩn đoán

### “getReadinessState() luôn REFUSING_TRAFFIC trong @PostConstruct”

`@PostConstruct` chạy khi bean đang khởi tạo, trước `ApplicationReadyEvent`. Đây thường là fallback hợp lệ, không chứng minh server không bao giờ ready. Đọc ở runner/after-ready hoặc lắng nghe event readiness accepting.

### “getState(ReadinessState.class) là null nhưng getReadinessState() không null”

Đó là **đúng API contract**. Bản không fallback trả null nếu chưa có event. Convenience method dùng `REFUSING_TRAFFIC` làm fallback. Nếu cần biết event đã thực sự tới chưa, kiểm tra `getLastChangeEvent(ReadinessState.class)`.

### “Trong ApplicationReadyEvent, readiness vẫn refusing”

Boot publish `ApplicationReadyEvent` rồi mới publish `AvailabilityChangeEvent` readiness accepting. Hãy chờ event typed hoặc đọc state sau mốc đó. Đừng đánh đồng tên “ReadyEvent” với trạng thái availability đã được ghi.

### “Tôi sửa enum trong biến cục bộ nhưng state thực không đổi”

`ReadinessState state = availability.getReadinessState()` chỉ đọc một giá trị. Gán `state = ACCEPTING_TRAFFIC` không thay state lưu trong `ApplicationAvailabilityBean`. Phải publish `AvailabilityChangeEvent` qua Spring event infrastructure.

### “Publish event rồi ApplicationAvailability vẫn trả trạng thái cũ”

Kiểm tra bạn có publish qua context/publisher **đang được dùng** hay không, listener nào nhận event, có context hierarchy, custom multicaster, async executor hoặc một nguồn khác publish state sau đó không. Tránh khởi tạo một `ApplicationAvailabilityBean` riêng rồi so sánh nó với bean của context.

### “Readiness accepting nhưng request vẫn không vào”

Readiness nội bộ không thay thế probe, load balancer, network, security, port binding hay dependency health. Kiểm tra cấu hình health group/probe, lịch polling của kubelet, EndpointSlice/Service và ingress. Đừng chữa bằng cách publish state accepting liên tục.

### “Readiness refusing làm mọi replica bị loại”

Nếu gắn readiness với một dịch vụ bên ngoài dùng chung và dịch vụ đó down, tất cả pod có thể cùng unready. Cần cân nhắc hành vi fail-open/fail-closed theo nghiệp vụ, retry/fallback và mục tiêu routing trước khi thêm dependency check vào readiness group.

### “Liveness BROKEN nhưng kubelet không restart”

Có thể không có livenessProbe, path/port sai, health endpoint không phản ánh state, hoặc ngưỡng failure chưa đạt. `ApplicationAvailability` chỉ lưu tín hiệu nội bộ; restart thuộc quyền điều phối của nền tảng.

### “Test đoán chính xác số event rồi bị fail”

Boot và các extension có thể publish thêm availability changes; hãy test theo **loại state** và trạng thái mục tiêu hoặc kiểm thử một unit `ApplicationAvailabilityBean` độc lập. Đừng viết một integration test giả định chỉ có đúng hai event trong cả đời ứng dụng.

### “Hai lần đọc state liên tiếp không khớp”

Đây có thể là cập nhật hợp lệ giữa hai lần đọc. Nếu logic yêu cầu một quyết định nhất quán, đọc một snapshot vào biến cục bộ tại điểm quyết định và thiết kế sự phối hợp bổ sung khi có nhiều thread; API không cấp transaction cho quy trình nghiệp vụ.

## 13. Checklist sử dụng đúng ApplicationAvailability

1. Inject `ApplicationAvailability` từ context thay vì tự `new ApplicationAvailabilityBean()` trong production service.
2. Phân biệt **liveness** (khả năng hoạt động nội bộ) với **readiness** (được phép nhận traffic mới).
3. Dùng `getLivenessState()` / `getReadinessState()` cho việc kiểm tra có fallback.
4. Dùng `getState(Class)` khi cần biết **state nào thực sự đã được công bố**, và xử lý khả năng `null`.
5. Dùng `getLastChangeEvent(Class)` khi cần event gần nhất hoặc metadata, nhớ xử lý `null`.
6. Không gọi `getReadinessState()` quá sớm rồi coi `REFUSING_TRAFFIC` là startup failure.
7. Muốn **thay đổi state**, publish `AvailabilityChangeEvent`; không tự thay object reference cục bộ.
8. Muốn xử lý theo lần chuyển state, lắng nghe `AvailabilityChangeEvent<S>` đúng generic type.
9. Không dùng availability state thay thế kiểm tra health kỹ thuật cần thiết khác.
10. Không gắn tất cả dependency ngoài vào liveness probe.
11. Khi có Kubernetes, kiểm tra thực tế Actuator path, management/main port, security và probe thresholds.
12. Với test, phân biệt unit test `ApplicationAvailabilityBean` và integration test lifecycle `SpringApplication`.

## 14. Câu hỏi tự kiểm tra

**1. `ApplicationAvailability` có trả trạng thái hiện tại mà không cần gọi HTTP không?**  
Có. Đó là interface được inject trong cùng ứng dụng, đọc state được quản lý trong bộ nhớ.

**2. `getLivenessState()` trả gì trước khi có liveness event?**  
`LivenessState.BROKEN` theo fallback tiêu chuẩn.

**3. `getReadinessState()` trả gì trước khi có readiness event?**  
`ReadinessState.REFUSING_TRAFFIC` theo fallback tiêu chuẩn.

**4. `getState(ReadinessState.class)` có chắc khác null không?**  
Không; nó có thể trả `null` khi chưa có event readiness.

**5. `getState(ReadinessState.class, REFUSING_TRAFFIC)` khác gì?**  
Có fallback không null theo lựa chọn của caller nếu chưa có event.

**6. Muốn biết sự kiện readiness gần nhất, dùng API nào?**  
`getLastChangeEvent(ReadinessState.class)`, nhớ xử lý `null`.

**7. `ApplicationAvailabilityBean` giữ toàn bộ lịch sử event không?**  
Không; API này cung cấp state và event gần nhất theo loại, không phải durable event log.

**8. Đọc readiness trong `ApplicationRunner` thường thấy gì?**  
`REFUSING_TRAFFIC`, vì runner chạy trước khi Boot phát readiness accepting.

**9. Tại sao `ApplicationReadyEvent` có thể vẫn thấy refusing?**  
Vì availability event accepting được publish ngay sau `ApplicationReadyEvent`.

**10. Muốn tạm dừng nhận traffic, có nên publish `LivenessState.BROKEN` không?**  
Thông thường không. Dùng `ReadinessState.REFUSING_TRAFFIC` nếu process vẫn live và có thể phục hồi.

**11. Nếu database ngoài down, có nên luôn chuyển liveness BROKEN?**  
Không; một dependency dùng chung lỗi không nhất thiết khiến restart từng instance có ích.

**12. `getReadinessState()==ACCEPTING_TRAFFIC` có tự đảm bảo Kubernetes đã route traffic không?**  
Không; platform còn phụ thuộc probe polling, Service/ingress/network và các quy tắc điều phối.

**13. Có thể dùng `ApplicationAvailability` trong batch app không có HTTP không?**  
Có. Availability là một cơ chế của Spring Boot core, không bắt buộc web server.

**14. Một event availability đã publish có tự tạo Actuator endpoint không?**  
Không. Cần dependency/config cho Actuator và web exposure phù hợp.

**15. Nên đọc state hay nghe event?**  
Đọc state để quyết định tức thời; nghe event khi cần thực hiện hành động mỗi lần chuyển trạng thái.

## 15. Tài liệu chính thức và đối chiếu phiên bản

- [Spring Boot 3.5 — ApplicationAvailability API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailability.html): định nghĩa các phương thức `getState`, `getLastChangeEvent`, `getLivenessState` và `getReadinessState`.
- [Spring Boot 3.5 — ApplicationAvailabilityBean API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailabilityBean.html): implementation cập nhật state từ sự kiện.
- [Spring Boot 3.5 — AvailabilityChangeEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html): generic event, `getState` và `publish`.
- [Spring Boot 3.5 — SpringApplication / Application Availability](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): ý nghĩa liveness, readiness, cách đọc và thứ tự sự kiện.
- [Spring Boot 3.5 — Actuator Kubernetes Probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): giai đoạn startup/shutdown, health probes, endpoint và cơ chế tích hợp.
- [Spring Boot 3.5 — LivenessState](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/LivenessState.html) và [ReadinessState](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ReadinessState.html): giá trị enum và semantics.

Bài học sử dụng Java 17+ và Spring Boot 3.5.16 cho ví dụ. Khi triển khai ở phiên bản khác, hãy đối chiếu đúng Spring Boot và Spring Framework trong dependency tree của dự án, nhất là khi sử dụng custom application event multicaster hoặc các health probe extension.