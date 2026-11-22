# AvailabilityChangeEvent chuyển trạng thái liveness sau started trong Spring Boot

## 1. Ý nghĩa chính xác của sự kiện sau ApplicationStartedEvent

Trong quá trình khởi động Spring Boot, **khởi tạo xong ApplicationContext** và **sẵn sàng nhận lưu lượng** là hai mốc khác nhau. Sau khi context được refresh thành công, Spring Boot phát `ApplicationStartedEvent`. **Ngay sau sự kiện này, Boot phát `AvailabilityChangeEvent<LivenessState>` với trạng thái `LivenessState.CORRECT`**. Sau đó các `ApplicationRunner` và `CommandLineRunner` mới được gọi. Khi các runner hoàn tất thành công, Boot phát `ApplicationReadyEvent` rồi phát `AvailabilityChangeEvent<ReadinessState>` với `ReadinessState.ACCEPTING_TRAFFIC`.

Đây là quy tắc quan trọng khi viết listener, kiểm tra health probe và điều phối triển khai. Không được hiểu rằng tên `ApplicationStartedEvent` đồng nghĩa application đã sẵn sàng phục vụ user, hoặc rằng `LivenessState.CORRECT` là bằng chứng mọi phụ thuộc bên ngoài đều khỏe.

Ba lớp khái niệm cần tách riêng:

| Khái niệm | Biểu diễn | Ý nghĩa |
| --- | --- | --- |
| Sự kiện vòng đời | `ApplicationStartedEvent`, `ApplicationReadyEvent` | Thông báo Spring Boot đã đạt một mốc startup nhất định |
| Sự kiện thay đổi khả dụng | `AvailabilityChangeEvent<S>` | Thông báo một `AvailabilityState` vừa đổi; `S` thường là `LivenessState` hoặc `ReadinessState` |
| Trạng thái được lưu | `ApplicationAvailability` | API để đọc trạng thái liveness/readiness mới nhất mà ứng dụng đang biết |
| Đầu dò/health probe | Actuator health groups, Kubernetes liveness/readiness probes | Cơ chế để bên ngoài quan sát trạng thái và đưa ra quyết định điều phối |

`AvailabilityChangeEvent` là **Spring application event** trong bộ nhớ tiến trình. Bản thân nó không mở một HTTP endpoint, không tự cấu hình Kubernetes và không bảo đảm request bị từ chối. Khi có Spring Boot Actuator và cấu hình phù hợp, state mới có thể được phản ánh lên health endpoint để nền tảng hạ tầng kiểm tra.

## 2. Thứ tự startup: từ context refreshed tới liveness CORRECT và readiness ACCEPTING_TRAFFIC

Spring Boot công bố thứ tự các mốc chính như sau:

~~~mermaid
flowchart TD
  A["SpringApplication.run(args)"] --> B["ApplicationStartingEvent"]
  B --> C["ApplicationEnvironmentPreparedEvent"]
  C --> D["ApplicationContextInitializedEvent"]
  D --> E["ApplicationPreparedEvent"]
  E --> F["refresh ApplicationContext"]
  F --> G["ApplicationStartedEvent"]
  G --> H["AvailabilityChangeEvent: LivenessState.CORRECT"]
  H --> I["ApplicationRunner / CommandLineRunner"]
  I --> J["ApplicationReadyEvent"]
  J --> K["AvailabilityChangeEvent: ReadinessState.ACCEPTING_TRAFFIC"]
~~~

Đây là **thứ tự sự kiện chính**, đã bỏ qua nhiều chi tiết như load cấu hình, bean definitions, context lifecycle, web server events và các bean post-processors. Trong thực tế, lỗi startup có thể cắt ngang chuỗi và làm Boot phát `ApplicationFailedEvent`; không nên tự gán rằng mọi sự kiện trong sơ đồ đều sẽ xảy ra nếu khởi động lỗi.

Bảng trạng thái khái niệm trong startup thông thường:

| Thời điểm | LivenessState | ReadinessState | Ý nghĩa vận hành |
| --- | --- | --- | --- |
| Đang khởi động, chưa refresh xong | `BROKEN` | `REFUSING_TRAFFIC` | Chưa nên xem tiến trình có khả năng xử lý request |
| Sau `ApplicationStartedEvent` và liveness event | `CORRECT` | `REFUSING_TRAFFIC` | Context đã refresh; runner có thể còn công việc startup |
| Sau runners, `ApplicationReadyEvent` và readiness event | `CORRECT` | `ACCEPTING_TRAFFIC` | Boot đánh dấu ứng dụng có thể phục vụ lưu lượng |

Các giá trị trong bảng phản ánh **mô hình availability của Boot**, không có nghĩa HTTP server ở mọi môi trường sẽ trả về một mã HTTP cụ thể tại mọi thời điểm. Trước khi web connector thực sự hoạt động, probe có thể không truy cập được; nếu không có platform dùng readiness, một HTTP request gọi trực tiếp vào cổng có thể vẫn được server xử lý trong thời gian startup. Chính nền tảng như Kubernetes mới dùng readiness probe để tránh điều hướng traffic vào instance chưa sẵn sàng.

### Mốc ApplicationStartedEvent

`ApplicationStartedEvent` được phát **sau** `ApplicationContext.refresh()` và **trước** `ApplicationRunner` / `CommandLineRunner`. Vì context đã được làm mới, Spring Boot suy luận phần hạ tầng nội bộ nền tảng hoạt động đủ để tiếp tục startup. Đây là thời điểm đánh dấu liveness là `CORRECT`.

Tuy vậy, có thể còn công việc ở runner như nạp dữ liệu cục bộ, xác minh điều kiện phục vụ hoặc chuẩn bị cache. Việc chúng chưa xong giải thích tại sao readiness vẫn là `REFUSING_TRAFFIC` ở giai đoạn này.

### Mốc AvailabilityChangeEvent với CORRECT

Ngay sau started, Boot phát sự kiện mà payload/state là `LivenessState.CORRECT`. Listener chuyên cho `AvailabilityChangeEvent<LivenessState>` có thể nhận sự kiện. Implementation `ApplicationAvailability` cập nhật state cuối cùng đã nhận, cho phép các component khác kiểm tra.

**Điểm dễ nhầm:** `ApplicationStartedEvent` không phải cùng một object/sự kiện với `AvailabilityChangeEvent`. Sự kiện liveness được phát **sau** event started; một listener đang xử lý `ApplicationStartedEvent` không nên suy luận sự kiện liveness chắc chắn đã được publish trước khi chính listener đó chạy.

### Mốc ApplicationReadyEvent và readiness

Sau khi Boot gọi xong các runner mà không gặp lỗi, nó phát `ApplicationReadyEvent`, rồi phát tiếp `AvailabilityChangeEvent` với `ReadinessState.ACCEPTING_TRAFFIC`. Hai event này cũng khác nhau. Trong callback xử lý `ApplicationReadyEvent`, việc đọc readiness ngay lập tức chưa nhất thiết cho giá trị `ACCEPTING_TRAFFIC`, vì readiness event chuẩn được publish **ngay sau** ready event.

Tùy phiên bản và các listener custom, state có thể bị ứng dụng chủ động thay đổi. Một mô hình đúng phải dựa vào chính event availability đang xử lý hoặc đọc trạng thái cuối cùng từ `ApplicationAvailability` ở thời điểm cần thiết.

## 3. Liveness: CORRECT khác BROKEN thế nào?

`LivenessState` biểu thị khả năng **tiến trình còn có thể hoạt động đúng hoặc tự phục hồi**. Nó hỗ trợ nền tảng quyết định liệu khởi động lại instance có giúp ích hay không.

Hai giá trị cốt lõi:

- `LivenessState.CORRECT`: ứng dụng được xem là live, internal state phù hợp để làm việc. Sau context refresh, Spring Boot mặc định xem ứng dụng ở trạng thái này.
- `LivenessState.BROKEN`: ứng dụng ở tình trạng nội bộ được xem là không thể phục hồi đúng cách; nền tảng có thể cần restart instance để khôi phục.

Liveness **không có nghĩa** mọi API, database, message broker, remote dependency đều khỏe. Nếu database bên ngoài tạm thời down mà liveness chuyển `BROKEN`, Kubernetes có thể restart hàng loạt instance; việc restart nhiều lần thường không làm database tốt lên, còn gây sự cố lan rộng. Do đó **không đưa các phép kiểm tra hệ thống ngoài vào liveness một cách máy móc**.

Ví dụ hợp lý để cân nhắc `BROKEN` là một thành phần nội bộ cốt lõi đã rơi vào trạng thái hỏng không thể tự phục hồi, như logic xử lý state trong bộ nhớ bị phá vỡ bất biến quan trọng. Việc quyết định phát `BROKEN` phải căn cứ vào khả năng phục hồi thực tế; không phát chỉ vì một request trả HTTP 500, một DB query timeout hoặc một cache remote tạm unavailable.

### Liveness được đánh dấu CORRECT là một giả định startup

Spring Boot mặc định dựa nhiều vào `ApplicationContext` làm đại diện trạng thái nội bộ. Khi refresh thành công, Boot phát `CORRECT` theo lifecycle chuẩn. Nhưng `CORRECT` không phải kết quả của một đợt kiểm thử toàn bộ endpoint nghiệp vụ. Đó là **tín hiệu trạng thái nội bộ**, dùng cùng logging, metrics, tracing và health checks khác để chẩn đoán.

Một lỗi startup xảy ra **trước** context refresh có thể khiến `ApplicationStartedEvent` không bao giờ xuất hiện, kéo theo không có liveness `CORRECT` từ chuỗi chuẩn. Nếu exception xảy ra **trong runner** thì liveness `CORRECT` có thể đã được phát, nhưng `ApplicationReadyEvent` và readiness `ACCEPTING_TRAFFIC` sẽ không xảy ra trong nhánh startup lỗi đó.

## 4. Readiness: tại sao started nhưng vẫn REFUSING_TRAFFIC?

Readiness là tín hiệu ứng dụng **có nên nhận traffic mới ở thời điểm này**. Trạng thái tiêu biểu:

- `ReadinessState.REFUSING_TRAFFIC`: nền tảng nên tạm ngừng chuyển request tới instance.
- `ReadinessState.ACCEPTING_TRAFFIC`: Boot/ứng dụng đánh dấu instance sẵn sàng nhận traffic.

Readiness chủ yếu có tác dụng trong môi trường load balancer/orchestrator. Dưới đây là các tình huống có thể có liveness `CORRECT` nhưng readiness `REFUSING_TRAFFIC`:

1. Context đã được refresh nhưng `ApplicationRunner` đang chạy bước khởi tạo dài.
2. Ứng dụng đã ready nhưng cần tạm dừng nhận traffic mới để phục vụ một tình huống vận hành.
3. Instance chuẩn bị graceful shutdown, cần được đưa ra khỏi tập endpoint nhận request mới.
4. Một dependency cần thiết riêng cho instance đã xuống, ứng dụng quyết định dừng traffic nhưng vẫn có khả năng tự hồi phục.

Không nên dựa vào readiness để kết luận process cần restart. Nền tảng Kubernetes thường **đưa pod ra khỏi endpoint phục vụ traffic** khi readiness fail, còn liveness fail có thể kích hoạt restart container.

### Startup có runner dài

Nếu dùng `ApplicationRunner` để warm up dữ liệu, khoảng giữa `CORRECT` và `ACCEPTING_TRAFFIC` dài hơn. Đây là hành vi được thiết kế: ứng dụng đã đủ live để chạy startup task nhưng chưa ready để phục vụ request. Nếu runner throw exception, startup fail; không có bảo đảm Boot sẽ publish readiness accepting.

### Khi app không phải web

Một Spring Boot CLI/batch app vẫn có lifecycle event và `ApplicationAvailability` dù không có embedded web server. Khi đó event `ReadinessState.ACCEPTING_TRAFFIC` thể hiện mốc đã hoàn thành startup theo cơ chế Boot, nhưng không có HTTP traffic để route. Đừng tưởng event tự tạo listener HTTP.

## 5. API ApplicationAvailability và AvailabilityChangeEvent

Các kiểu dữ liệu chính nằm ở package `org.springframework.boot.availability`:

| Kiểu | Vai trò |
| --- | --- |
| `ApplicationAvailability` | Dịch vụ đọc state; có `getLivenessState()`, `getReadinessState()`, `getState(Class<S>)`, `getLastChangeEvent(Class<S>)` |
| `AvailabilityState` | Marker interface cho loại trạng thái |
| `LivenessState` | Enum với `CORRECT` và `BROKEN` |
| `ReadinessState` | Enum với `ACCEPTING_TRAFFIC` và `REFUSING_TRAFFIC` |
| `AvailabilityChangeEvent<S extends AvailabilityState>` | Application event có `getState()`; phát khi state đổi |
| `AvailabilityChangeEvent.publish(...)` | Helper để publish event thay đổi state thông qua `ApplicationContext` hoặc `ApplicationEventPublisher` |

Để đọc state trong bean:

~~~java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;

class AvailabilitySnapshot {
    private final ApplicationAvailability availability;

    AvailabilitySnapshot(ApplicationAvailability availability) {
        this.availability = availability;
    }

    boolean isLive() {
        return availability.getLivenessState() == LivenessState.CORRECT;
    }

    boolean isReady() {
        return availability.getReadinessState()
                == ReadinessState.ACCEPTING_TRAFFIC;
    }
}
~~~

Đây là một **snippet Java** minh họa đọc state, chưa phải một bean đầy đủ vì không có `@Component` và không nằm trong project hoàn chỉnh. Trong ví dụ lớn hơn, constructor injection `ApplicationAvailability` được Spring Boot cung cấp khi ứng dụng chạy.

Một ứng dụng có thể publish sự kiện để đổi readiness chủ động:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
class TrafficGate {
    private final ApplicationEventPublisher publisher;

    TrafficGate(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    void pauseNewTraffic() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.REFUSING_TRAFFIC);
    }

    void resumeNewTraffic() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

**Giải thích:** phát event thông qua `ApplicationEventPublisher` làm các listener availability nhận thay đổi, trong đó có state service của Boot. Nó **không** trực tiếp điều khiển socket, đóng server, hay bảo đảm load balancer đổi route ngay lập tức. Cần có các health probes, chính sách routing, polling interval và hệ thống điều phối phù hợp.

Với liveness, chỉ publish `LivenessState.BROKEN` khi bạn có lý do xác thực rằng instance bị hỏng nội bộ không thể tự phục hồi; đó là thông báo mang hệ quả vận hành mạnh hơn việc đánh dấu unready.

## 6. Lắng nghe event: phân biệt event type, state và generic parameter

Spring Framework hỗ trợ `@EventListener` để nhận các application event. Có thể tạo hai handler với generic parameter cụ thể:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class AvailabilityAudit {
    @EventListener
    public void onLiveness(AvailabilityChangeEvent<LivenessState> event) {
        System.out.println("LIVENESS=" + event.getState());
    }

    @EventListener
    public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("READINESS=" + event.getState());
    }
}
~~~

Spring Boot cung cấp thông tin generic type khi publish `AvailabilityChangeEvent<S>`, cho phép những listener được khai báo theo loại state. Không nên đổi generic `<LivenessState>` thành một kiểu bất kỳ rồi dùng cast không kiểm tra; một sự kiện readiness cũng là `AvailabilityChangeEvent` nhưng **khác loại state**.

`@EventListener` là cách tiện cho bean đã tồn tại trong context. Những event rất sớm như `ApplicationStartingEvent` diễn ra trước lúc tạo context, nên không thể dựa vào một `@Component` thông thường để nhận chúng. Trái lại, event `AvailabilityChangeEvent` đánh dấu `CORRECT` xảy ra sau refresh, nên listener được container quản lý có thể quan sát được.

**Cần tránh logic dựa vào thứ tự listener tùy ý.** Mặc định, event listener thường chạy đồng bộ; nếu cấu hình async event multicaster hoặc async listener, thời điểm log có thể khác và exception handling cũng khác. Nếu cần một kết luận chính xác về state, xét payload `event.getState()` và API `ApplicationAvailability`, thay vì suy luận chỉ từ một dòng log.

## 7. Ví dụ đầy đủ Java 17+: chứng minh đúng thứ tự sự kiện

Ví dụ dưới đây chạy trên Spring Boot 3.5.x, Java 17+ và Maven. Nó cố ý không dùng web starter hay Actuator, để thấy `AvailabilityChangeEvent` đến từ **Spring Boot startup**, không phụ thuộc HTTP endpoint.

Cấu trúc tệp:

~~~text
availability-demo/
├── pom.xml
└── src/main/java/com/example/availability/
    ├── AvailabilityDemoApplication.java
    └── LifecycleObserver.java
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
    <artifactId>availability-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

### File src/main/java/com/example/availability/AvailabilityDemoApplication.java

~~~java
package com.example.availability;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class AvailabilityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AvailabilityDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner startupTask(ApplicationAvailability availability) {
        return args -> System.out.println(
                "03.RUNNER=" + availability.getLivenessState()
                + "/" + availability.getReadinessState());
    }
}
~~~

### File src/main/java/com/example/availability/LifecycleObserver.java

~~~java
package com.example.availability;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class LifecycleObserver {

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("01.STARTED");
    }

    @EventListener
    public void onLiveness(AvailabilityChangeEvent<LivenessState> event) {
        if (event.getState() == LivenessState.CORRECT) {
            System.out.println("02.LIVENESS=CORRECT");
        }
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("04.READY");
    }

    @EventListener
    public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
        if (event.getState() == ReadinessState.ACCEPTING_TRAFFIC) {
            System.out.println("05.READINESS=ACCEPTING_TRAFFIC");
        }
    }
}
~~~

**Chạy** trong thư mục `availability-demo`:

~~~bash
mvn -q -DskipTests package
java -jar target/availability-demo-0.0.1-SNAPSHOT.jar
~~~

Với Spring Boot startup mặc định, không có listener bất thường và không có exception trong runner, những dòng **do chương trình ví dụ chủ động in ra** sẽ theo thứ tự:

~~~text
01.STARTED
02.LIVENESS=CORRECT
03.RUNNER=CORRECT/REFUSING_TRAFFIC
04.READY
05.READINESS=ACCEPTING_TRAFFIC
~~~

Spring Boot có thể in thêm log của framework; khối trên chỉ liệt kê các dòng prefix `01.` đến `05.`, không phải toàn bộ stdout.

**Phân tích sự kiện:**

1. `ApplicationStartedEvent` là mốc đầu tiên được observer ghi trong ví dụ, sau khi context refresh.
2. Boot sau đó publish liveness event `CORRECT`, observer ghi dòng `02`.
3. `ApplicationRunner` được gọi; lúc này liveness đã là `CORRECT` nhưng readiness vẫn `REFUSING_TRAFFIC`, đúng dòng `03`.
4. Khi runner hoàn tất, Boot publish `ApplicationReadyEvent`, observer ghi dòng `04`.
5. Tiếp theo Boot publish readiness event `ACCEPTING_TRAFFIC`; dòng `05` là mốc công bố sẵn sàng nhận traffic.

Thứ tự logic `ApplicationStartedEvent` → liveness → runner → `ApplicationReadyEvent` → readiness đã được tài liệu Spring Boot chính thức xác nhận. Tuy nhiên nếu ứng dụng tự publish state khác, tùy biến event handling sang bất đồng bộ hoặc runner ném exception, output có thể khác. Demo này chủ ý chỉ dùng event listener chuẩn trong context, không cài thêm event multicaster.

**Lưu ý về chương trình CLI:** vì không có web server hay long-running process khác, Java process có thể kết thúc sau khi khởi động xong; điều đó không phủ định việc các event startup đã được phát trước khi kết thúc.

## 8. Đưa trạng thái vào Actuator và Kubernetes probes

Trong ứng dụng web, `spring-boot-starter-actuator` dùng `ApplicationAvailability` để phản ánh liveness/readiness vào health indicators. Khi health probe groups được bật, các URL thông dụng là:

- `/actuator/health/liveness`: diễn giải `LivenessState` thành health status theo quy tắc của probe.
- `/actuator/health/readiness`: diễn giải `ReadinessState`.
- `/actuator/health`: health tổng quát, có thể chứa các indicator khác; **không đồng nghĩa** với riêng liveness.

Cần có web runtime và Actuator để các endpoint HTTP này thực sự tồn tại. Đối với môi trường Kubernetes được Spring Boot phát hiện, các probe group có thể được kích hoạt tự động; ở môi trường khác có thể bật rõ ràng:

~~~yaml
# src/main/resources/application.yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Cấu hình trên minh họa khi dự án đã có Spring Web/Actuator; nó không tự tạo web server nếu thiếu starter web và không bỏ qua Spring Security/network policy.

Ví dụ probes của Kubernetes:

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  initialDelaySeconds: 2
  periodSeconds: 5
~~~

Đây là hai đoạn **cấu hình trường trong container spec**, cần đặt đúng vị trí như `spec.containers[]` trong manifest Pod/Deployment và điều chỉnh số giây, cổng, thresholds theo đặc điểm của ứng dụng. Không phải cấu hình Spring Boot YAML. Khi liveness thất bại đủ ngưỡng, kubelet có thể restart container; khi readiness thất bại, endpoint đó bị loại khỏi tập phục vụ lưu lượng của Service theo cơ chế Kubernetes.

### Liveness CORRECT không bảo đảm database còn kết nối

Liveness probe nên phản ánh trạng thái nội bộ thực sự không thể phục hồi. Đừng thêm DB/remote cache check vào liveness mà không cân nhắc hậu quả restart nhiều replica đồng thời. Đối với readiness, có thể cân nhắc health check của một thành phần thật sự bắt buộc cho việc nhận traffic; nhưng dependency **dùng chung cho tất cả instance** bị lỗi có thể khiến toàn bộ service unready. Cần đánh giá kiến trúc, circuit breaker, fallback và ảnh hưởng load balancing trước khi bổ sung indicator.

### Health probe endpoint và hạ tầng HTTP thực tế

Nếu Actuator chạy trên một `management.server.port` khác cổng ứng dụng, probe trên cổng quản trị có thể phản hồi thành công ngay cả khi cổng business gặp vấn đề. Spring Boot hỗ trợ làm cho health probes có mặt trên cổng ứng dụng chính:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

Với cấu hình này và web runtime thích hợp, đường dẫn bổ sung trên cổng chính là `/livez` và `/readyz`. Đây là cách giảm rủi ro chỉ kiểm tra được management server mà bỏ sót hạ tầng business port. Vẫn phải xác minh cấu hình security, ingress và routing của môi trường triển khai.

### Startup lâu: khi nào cần startupProbe?

Trong startup, liveness được xem là `BROKEN` trước khi context hoàn tất refresh. Nếu quá trình khởi động lâu hơn giới hạn mà liveness probe cho phép, kubelet có thể restart container trước khi nó có cơ hội trở thành live. `startupProbe` trên Kubernetes là một cách bảo vệ giai đoạn startup: trong lúc startup probe chưa thành công, kubelet không áp dụng liveness/readiness probes theo chu kỳ bình thường. Cần thiết kế ngưỡng dựa trên thời gian startup thực đo, không luôn luôn thêm cho mọi app.

## 9. Chủ động chuyển state sau khi đã started

Một module có thể cần ngừng nhận traffic mới mà không chết process. Ví dụ ứng dụng đang chuyển vai trò leader, tạm khóa nhận job mới hoặc graceful drain. Khi đó publish `ReadinessState.REFUSING_TRAFFIC` thường thích hợp hơn `LivenessState.BROKEN`.

Ví dụ sử dụng lại `TrafficGate` ở mục 5:

~~~java
// Khi đã quyết định tạm ngừng nhận traffic:
trafficGate.pauseNewTraffic();

// Khi đã khôi phục điều kiện phục vụ:
trafficGate.resumeNewTraffic();
~~~

Đây là các lời gọi **minh họa bên trong code ứng dụng**, không phải chương trình độc lập. Hãy tránh gọi `resumeNewTraffic()` vô điều kiện sau một khoảng chờ nếu điều kiện phục vụ chưa được xác minh.

Với một lỗi không thể phục hồi của trạng thái nội bộ, có thể phát liveness broken bằng helper:

~~~java
AvailabilityChangeEvent.publish(
        eventPublisher, this, LivenessState.BROKEN);
~~~

Đoạn này cần đặt trong bean có `eventPublisher` kiểu `ApplicationEventPublisher`; nó chỉ minh họa cú pháp. Nên phân biệt việc **phát tín hiệu** với **tự sửa lỗi**: event không tự rollback state, recreate bean, restart process hoặc thay thế phương án xử lý sự cố.

Ngoài ra, Spring Boot công bố trạng thái liên quan tới shutdown, thường chuyển readiness sang `REFUSING_TRAFFIC` khi graceful shutdown bắt đầu. Không cần tự gán liveness `BROKEN` cho mọi lần tắt ứng dụng có chủ đích.

## 10. Những lỗi hay gặp khi đọc log hoặc viết listener

### Nhầm started với ready

**Dấu hiệu:** code trong `ApplicationStartedEvent` bắt đầu phục vụ nghiệp vụ hoặc báo ready ra bên ngoài khi `ApplicationRunner` vẫn phải chuẩn bị dữ liệu. **Sửa:** coi started là context refreshed; chỉ báo readiness theo event `ACCEPTING_TRAFFIC` hoặc trạng thái `ApplicationAvailability` sau runner.

### Gọi getReadinessState trong ApplicationReadyEvent rồi thấy REFUSING_TRAFFIC

`ApplicationReadyEvent` được phát trước readiness availability event chuẩn. Đây có thể là hành vi đúng theo thứ tự startup, không phải bug. Nếu muốn xử lý **chính xác thời điểm** readiness chuyển, lắng nghe `AvailabilityChangeEvent<ReadinessState>` và kiểm tra `event.getState()`.

### Bật health URL nhưng endpoint trả 404

Xác minh các starter Spring Web/Actuator, đường dẫn base path, management port, tình trạng enabled health probes, và Spring Security/access. `AvailabilityChangeEvent` và `ApplicationAvailability` tồn tại trong Boot startup không đồng nghĩa endpoint HTTP đã được đăng ký.

### Liveness chuyển BROKEN khi DB down

Đây thường là một cấu hình probe nguy hiểm nếu DB là dịch vụ dùng chung: container restart liên tục khó giúp DB phục hồi, thậm chí làm sự cố lớn hơn. Tách liveness khỏi dependency check ngoài; dùng readiness hoặc xử lý retry/circuit breaker theo nghiệp vụ khi phù hợp.

### App có CORRECT nhưng readiness không bao giờ ACCEPTING_TRAFFIC

Kiểm tra `ApplicationRunner`/`CommandLineRunner` có hoàn tất không; nếu runner bị treo, exception hoặc process dừng, Boot chưa phát ready/readiness accepting theo đường khởi động thành công. Đồng thời kiểm tra listener custom có chủ động publish `REFUSING_TRAFFIC` sau đó hay không.

### Test assert luôn nhận đúng số event

Một số library, processor hoặc ứng dụng có thể phát thêm availability event, ví dụ khi readiness đổi theo tình trạng runtime. Test nên lọc theo **loại state và giá trị**, và xác nhận thứ tự những event có ý nghĩa thay vì giả định chỉ có đúng hai event trong cả đời process.

### Tự publish CORRECT ngay từ ApplicationStartingEvent

Điều đó đi ngược mục đích liveness: context chưa refresh mà đã báo live. Dựa vào lifecycle Boot để đánh dấu `CORRECT` sau started; nếu thực sự viết phần hạ tầng custom, phải hiểu hợp đồng của event và thời điểm container có thể tạo listener.

### Nhầm probe trả HTTP 503 với việc tất cả user nhận HTTP 503

Probe có thể trả mã không khỏe cho **endpoint probe**; Kubernetes thường ngừng route đến instance unready, nên user có thể không trực tiếp nhận 503 từ instance đó. HTTP response ở ingress/load balancer còn phụ thuộc nền tảng và số replica sẵn sàng.

### Gửi state event nhưng không thấy Kubernetes thay đổi

Cần kiểm tra Boot Actuator có phản ánh đúng state không, probes đã enabled, path/port phù hợp, readiness/liveness policies đúng, và probe polling interval. Event là tín hiệu nội bộ trong app; nếu không có probe và nền tảng sử dụng tín hiệu đó, cơ chế triển khai không tự biết về nó.

## 11. Bảng quyết định nhanh

| Tình huống | State/event nên quan sát hoặc điều chỉnh | Vì sao |
| --- | --- | --- |
| Context refresh thành công | Sau `ApplicationStartedEvent` → `LivenessState.CORRECT` | Boot đánh dấu tiến trình live |
| Runner vẫn chuẩn bị dữ liệu | `CORRECT` + `REFUSING_TRAFFIC` | Live nhưng chưa ready |
| Runner hoàn tất, startup thành công | `ApplicationReadyEvent` → `ACCEPTING_TRAFFIC` | Bắt đầu nhận traffic theo chính sách platform |
| Local cache hỏng không thể phục hồi | Cân nhắc `LivenessState.BROKEN` | Có thể cần restart instance |
| DB ngoài tạm timeout | Không tự động BROKEN | Restart app có thể không giải quyết lỗi ngoài |
| Instance cần tạm drain request mới | `ReadinessState.REFUSING_TRAFFIC` | Dừng route traffic mới mà vẫn giữ process |
| Graceful shutdown bắt đầu | Quan sát readiness refusing | Cho thời gian xử lý in-flight requests theo cấu hình |
| Batch/CLI app không mở HTTP | Vẫn có availability events | Event không tự tạo HTTP server |
| Muốn chọn restart hay loại khỏi load balancer | Liveness vs readiness probes | Hai loại probe có hệ quả orchestration khác nhau |

## 12. Các câu hỏi tự kiểm tra

**1.** `ApplicationStartedEvent` phát trước hay sau refresh context?  
**Đáp án:** Sau refresh, trước runners.

**2.** Ngay sau `ApplicationStartedEvent` Spring Boot phát event nào để đánh dấu live?  
**Đáp án:** `AvailabilityChangeEvent` với `LivenessState.CORRECT`.

**3.** Khi `ApplicationRunner` đang chạy, liveness và readiness thường là gì?  
**Đáp án:** `CORRECT` và `REFUSING_TRAFFIC`.

**4.** Có thể khẳng định đã ready ngay khi nhận `ApplicationStartedEvent` không?  
**Đáp án:** Không; còn runners và readiness event.

**5.** `ApplicationReadyEvent` và readiness accepting event có phải cùng một event không?  
**Đáp án:** Không; `AvailabilityChangeEvent<ReadinessState>` với `ACCEPTING_TRAFFIC` được publish ngay sau `ApplicationReadyEvent`.

**6.** Khi DB bên ngoài down có nên tự động publish `LivenessState.BROKEN` không?  
**Đáp án:** Thường không, vì liveness nên dựa vào khả năng phục hồi nội bộ, tránh restart hàng loạt instance do dependency chung.

**7.** Muốn đọc trạng thái cuối cùng từ bean thì inject interface nào?  
**Đáp án:** `ApplicationAvailability`.

**8.** Muốn lắng nghe đúng thay đổi liveness thì handler có thể nhận event type nào?  
**Đáp án:** `AvailabilityChangeEvent<LivenessState>` và xem `getState()`.

**9.** Không có Actuator có còn event `LivenessState.CORRECT` trong startup không?  
**Đáp án:** Có, vì event thuộc cơ chế startup Spring Boot; không có Actuator/web thì không mặc nhiên có HTTP probe.

**10.** Liveness probe fail và readiness probe fail có cùng hệ quả trong Kubernetes không?  
**Đáp án:** Không; liveness có thể kích hoạt restart, còn readiness khiến pod không được route traffic mới.

**11.** ApplicationReadyEvent listener đọc readiness vẫn refusing có chắc là lỗi không?  
**Đáp án:** Không, vì event chuẩn chuyển accepting được publish ngay sau ready event.

**12.** Một lần publish `REFUSING_TRAFFIC` có tự cắt kết nối HTTP hay restart pod không?  
**Đáp án:** Không, nó thay state nội bộ; hành vi điều phối phụ thuộc probe và nền tảng bên ngoài.

## 13. Tài liệu Spring Boot chính thức để đối chiếu

- [Spring Boot — SpringApplication: Application Events and Listeners](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): thứ tự started, liveness, runner, ready, readiness.
- [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html#features.spring-application.application-availability): ý nghĩa liveness, readiness, cách đọc và publish state.
- [Spring Boot — Actuator Endpoints: Kubernetes Probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): health groups, readiness/liveness probes và trạng thái theo startup/shutdown.
- [Spring Boot — AvailabilityChangeEvent API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html): generic state type, `getState()` và `publish(...)`.
- [Spring Boot — ApplicationAvailability API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/availability/ApplicationAvailability.html): cách đọc trạng thái cuối cùng.

Với mỗi dự án thật, phải đối chiếu phiên bản Spring Boot hiện dùng, cách khởi tạo web context, listener custom, cấu hình Actuator và hành vi probe của nền tảng trước khi dựa vào các trạng thái này để điều phối traffic.