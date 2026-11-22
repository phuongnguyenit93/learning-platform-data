# ApplicationReadyEvent trong Spring Boot Application Events

## 1. Khái niệm và mục đích

`ApplicationReadyEvent` là một sự kiện vòng đời do **Spring Boot** phát khi quá trình khởi động qua `SpringApplication` đã đạt tới mốc sẵn sàng phục vụ. Đây là một tín hiệu xuất hiện rất muộn trong startup: sau khi `ApplicationContext` được tạo và refresh, sau khi Boot phát `ApplicationStartedEvent` và **sau khi các `ApplicationRunner` / `CommandLineRunner` đã được gọi và hoàn tất bình thường**.

Tên lớp:

```java
org.springframework.boot.context.event.ApplicationReadyEvent
```

Lớp này kế thừa `SpringApplicationEvent`, không phải một sự kiện do ứng dụng tự phát mỗi khi có request. Spring Boot phát nó để thông báo mốc **kết thúc quá trình khởi động thành công**, không phải để xử lý từng nghiệp vụ.

Ví dụ: một hệ thống quản lý đơn hàng cần khởi tạo bean, đọc cấu hình, thực hiện các bước kiểm tra startup và nạp dữ liệu thiết yếu. Sau khi các bước startup bắt buộc xong, một listener muốn ghi nhận số đo thời gian khởi động hoặc đăng ký một tác vụ hậu startup không quan trọng. `ApplicationReadyEvent` là nơi phù hợp để quan sát mốc này.

**Giới hạn quan trọng:** nhận được event không tự chứng minh tất cả hệ thống ngoài đều khỏe, không có request nào đang lỗi, mọi tác vụ nền đã hoàn thành, hoặc ứng dụng mãi mãi sẵn sàng phục vụ. Những điều đó cần được đánh giá bằng readiness/health checks và cơ chế nghiệp vụ phù hợp.

## 2. ApplicationReadyEvent nằm ở đâu trong quá trình khởi động?

Theo chuỗi Spring Boot `SpringApplication.run(...)` thành công:

```text
SpringApplication.run(args)
          |
          +--> ApplicationStartingEvent
          |
          +--> ApplicationEnvironmentPreparedEvent
          |
          +--> ApplicationContextInitializedEvent
          |
          +--> ApplicationPreparedEvent
          |
          +--> Refresh ApplicationContext
          |      +--> ContextRefreshedEvent
          |      +--> WebServerInitializedEvent (nếu có web server)
          |
          +--> ApplicationStartedEvent
          |
          +--> AvailabilityChangeEvent(LivenessState.CORRECT)
          |
          +--> Chạy ApplicationRunner / CommandLineRunner
          |
          +--> ApplicationReadyEvent
          |
          +--> AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
          |
          +--> SpringApplication.run(...) hoàn tất
```

**Thứ tự cốt lõi:** `ApplicationStartedEvent` → các runner → `ApplicationReadyEvent` → readiness state `ACCEPTING_TRAFFIC`.

Một số lưu ý:

- `ApplicationStartedEvent` được phát **sau khi context refresh**, nhưng **trước** các runner.
- Các `ApplicationRunner` và `CommandLineRunner` được Spring Boot gọi sau `ApplicationStartedEvent`. Một runner có thể thực hiện điều kiện khởi động bắt buộc.
- `ApplicationReadyEvent` phát **sau các runner** trong đường startup thành công.
- Ngay sau đó, Boot phát `AvailabilityChangeEvent` với `ReadinessState.ACCEPTING_TRAFFIC` để công bố readiness theo cơ chế availability.
- Nếu startup ném exception trước khi hoàn tất, Boot có thể phát `ApplicationFailedEvent`; không mong đợi có ready event của lần chạy thất bại.
- Với ứng dụng web, `WebServerInitializedEvent` liên quan việc web server đã khởi tạo, **không đồng nhất** với việc mọi runner đã hoàn tất.

Sơ đồ thể hiện thứ tự logic của các cột mốc, không bảo đảm mọi loại sự kiện chỉ được nhận một lần trong hệ thống có nhiều context hoặc có các listener được đăng ký ở nhiều phạm vi.

### So sánh những sự kiện dễ nhầm

| Sự kiện | Thời điểm | Có phải mốc ready sau runner? |
| --- | --- | --- |
| `ContextRefreshedEvent` | Spring Framework hoàn tất refresh context | Không |
| `ApplicationStartedEvent` | Spring Boot đã refresh context, trước runner | Không |
| `ApplicationReadyEvent` | Spring Boot gọi xong các runner và chuẩn bị công bố sẵn sàng | **Có** |
| `AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)` | Boot công bố trạng thái cho phép nhận traffic, ngay sau ready event | Đây là thay đổi readiness state |
| `ApplicationFailedEvent` | Lỗi trong startup | Không, là đường thất bại |
| `ContextClosedEvent` | Context đang đóng | Không, thuộc shutdown |

`ApplicationReadyEvent` là **sự kiện một mốc startup**, còn `ReadinessState` là trạng thái có thể tiếp tục thay đổi nhiều lần khi ứng dụng đã chạy.

## 3. Cách đăng ký listener

### 3.1. Phương thức `@EventListener`

```java
@Component
public class ReadyNotification {

    @EventListener
    public void afterStartup(ApplicationReadyEvent event) {
        System.out.println("Spring Boot reached ready milestone");
    }
}
```

Đây là đoạn minh họa để đặt trong một dự án Boot có component scan; cần import `@Component`, `@EventListener` và `ApplicationReadyEvent`. Khi context quản lý bean `ReadyNotification`, Spring có thể phát hiện phương thức nhận event theo kiểu tham số. Không cần tự gọi phương thức này từ `main`.

Nếu không sử dụng thông tin event, có thể khai báo `@EventListener(ApplicationReadyEvent.class)` trên phương thức không tham số:

```java
@EventListener(ApplicationReadyEvent.class)
public void announceReady() {
    // Ghi nhận startup thành công.
}
```

Đây cũng là đoạn minh họa, không phải chương trình độc lập.

### 3.2. Interface `ApplicationListener<ApplicationReadyEvent>`

```java
@Component
public class ReadyObserver
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("Ready: "
                + event.getApplicationContext().getId());
    }
}
```

Dùng interface là hợp lệ nếu muốn loại event thể hiện trong khai báo class. Một listener chỉ cần đăng ký bằng một cơ chế rõ ràng để tránh vô tình chạy trùng.

### 3.3. Vì sao listener Spring bean nhận được ready event?

Một số event Boot rất sớm, như `ApplicationStartingEvent`, xuất hiện **trước khi các bean được tạo**, nên không thể chỉ dựa vào `@EventListener` trên bean để nhận. Trái lại, `ApplicationReadyEvent` xuất hiện sau khi context đã khởi tạo. Vì vậy, bean thông thường được khai báo qua `@Component` hoặc `@Bean` là đủ để nhận event ready.

Khi phải nghe sự kiện **trước khi có context/bean**, có thể đăng ký listener sớm qua `SpringApplication.addListeners(...)` hoặc cơ chế do Boot hỗ trợ; đừng đưa yêu cầu này vào listener ready khi không cần thiết.

## 4. API của ApplicationReadyEvent

Một số phương thức hay dùng:

| Phương thức | Giá trị cung cấp | Ứng dụng |
| --- | --- | --- |
| `getApplicationContext()` | `ConfigurableApplicationContext` liên quan đến event | Phân biệt context nguồn |
| `getSpringApplication()` | `SpringApplication` nguồn | Quan sát mốc của lần chạy Boot |
| `getArgs()` | Đối số đầu vào khi chạy application | Chẩn đoán với quy định bảo mật phù hợp |
| `getTimeTaken()` | `Duration`, hoặc `null` nếu không xác định được | Theo dõi thời gian startup |

Ví dụ đọc thời gian:

```java
@EventListener
public void onReady(ApplicationReadyEvent event) {
    Duration duration = event.getTimeTaken();
    if (duration != null) {
        System.out.println("Startup duration: "
                + duration.toMillis() + " ms");
    }
}
```

Đoạn này cần import `Duration` và thuộc một bean Spring. `getTimeTaken()` có thể là `null`, nên không gọi `toMillis()` trước khi kiểm tra. Giá trị thời gian thay đổi theo máy và môi trường; **không bao giờ ghi một stdout số mili-giây cố định** làm kết quả kỳ vọng cho test.

Đừng log nguyên văn `getArgs()` trong môi trường sản xuất nếu command-line arguments có thể chứa thông tin nhạy cảm.

## 5. Ví dụ đầy đủ với Java 17 và Spring Boot 3.5.0

Ví dụ console không có web server, minh họa chính xác thứ tự giữa:

1. `ApplicationStartedEvent`.
2. Một `ApplicationRunner` đã hoàn tất.
3. `ApplicationReadyEvent`.

Chỉ có **một runner** để kết quả in không phụ thuộc thứ tự giữa nhiều runner. Ứng dụng đóng context sau khi `SpringApplication.run(...)` trả về.

### 5.1. Cấu trúc thư mục

```text
ready-event-demo/
├── pom.xml
└── src/main/java/example/ReadyEventDemo.java
```

### 5.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>ready-event-demo</artifactId>
    <version>1.0.0</version>

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
```

### 5.3. Tệp src/main/java/example/ReadyEventDemo.java

```java
package example;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication(proxyBeanMethods = false)
public class ReadyEventDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(ReadyEventDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            // SpringApplication.run đã hoàn thành các runner
            // và phát ApplicationReadyEvent trước khi trả về.
        }
    }

    @Bean
    public ApplicationRunner prepareDemoData() {
        return new ApplicationRunner() {
            @Override
            public void run(ApplicationArguments args) {
                System.out.println("02 ApplicationRunner completed");
            }
        };
    }

    @Bean
    public StartupObserver startupObserver() {
        return new StartupObserver();
    }

    public static class StartupObserver {
        @EventListener
        public void onStarted(ApplicationStartedEvent event) {
            System.out.println("01 ApplicationStartedEvent");
        }

        @EventListener
        public void onReady(ApplicationReadyEvent event) {
            System.out.println("03 ApplicationReadyEvent");
        }
    }
}
```

### 5.4. Chạy

Mở terminal tại thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn -q spring-boot:run
```

**Các dòng do mã nguồn ví dụ in**, không tính log Boot/Maven (nếu có):

```text
01 ApplicationStartedEvent
02 ApplicationRunner completed
03 ApplicationReadyEvent
```

Giải thích:

- `@SpringBootApplication` và `SpringApplication.run` khởi động context.
- Bean `StartupObserver` được Spring tạo qua `@Bean`, và các phương thức `@EventListener` được đăng ký trước mốc startup cuối.
- Sau refresh, Spring Boot phát `ApplicationStartedEvent`; callback đầu tiên in dòng 01.
- Spring Boot thực thi `ApplicationRunner.run`; dòng 02 xuất hiện khi runner đã chạy.
- Boot phát `ApplicationReadyEvent` sau runner thành công; callback in dòng 03.
- Theo chuỗi startup chuẩn, Boot tiếp tục công bố `ReadinessState.ACCEPTING_TRAFFIC`. Ví dụ không in event availability.
- `SpringApplication.run(...)` trả về context; `try-with-resources` gọi `close()` để ứng dụng console thoát.

Dùng `spring-boot-starter` (không phải `spring-boot-starter-web`) và đặt `WebApplicationType.NONE` để tránh mở HTTP server. Ví dụ in theo thứ tự xác định vì chỉ có một runner và listener mặc định chạy đồng bộ. Chúng ta không dùng `Thread.sleep(...)` hoặc giả định timing ngẫu nhiên.

**Phạm vi bằng chứng:** ví dụ chứng minh thứ tự các **mốc Boot**, không có nghĩa mọi task nền mà runner tự kích hoạt cũng đã kết thúc. Nếu runner gửi tác vụ bất đồng bộ rồi trả về ngay, Boot chỉ biết runner đã **trả về**, không biết task đó đã hoàn tất.

## 6. ApplicationRunner và CommandLineRunner so với ready event

Hai giao diện đều được Boot gọi khi context đã start, **trước ApplicationReadyEvent**:

- `ApplicationRunner.run(ApplicationArguments args)` nhận đối số được parse qua `ApplicationArguments`.
- `CommandLineRunner.run(String... args)` nhận đối số dạng mảng `String`.

Ví dụ hai cách viết tương đương về mục đích:

```java
@Bean
ApplicationRunner validateStartupConfig() {
    return args -> {
        // Kiểm tra cấu hình bắt buộc.
    };
}

@Bean
CommandLineRunner verifyRequiredSchema() {
    return args -> {
        // Kiểm tra một điều kiện bắt buộc khác.
    };
}
```

Đây là mã minh họa tích hợp; nếu đưa cả hai vào ứng dụng, cần import tương ứng. Khi có nhiều runner và yêu cầu thứ tự, Spring Boot hỗ trợ `Ordered`/`@Order`. Đừng mặc định thứ tự chạy dựa vào tên method, vị trí khai báo trong file hoặc loại interface.

**Chọn nơi đặt logic:**

| Nhu cầu | Nơi nên đặt | Lý do |
| --- | --- | --- |
| Điều kiện phải hoàn thành trước khi phục vụ | `ApplicationRunner` / `CommandLineRunner` | Boot đợi runner trong luồng startup |
| Ghi metric/log khi startup thành công | `ApplicationReadyEvent` listener | Quan sát đúng mốc ready |
| Khởi tạo một bean | Constructor/DI/lifecycle thích hợp | Trách nhiệm nằm ở bean sở hữu |
| Việc hậu startup được phép thất bại mà không ảnh hưởng readiness | Listener ready hoặc job nền có quản lý | Không giữ chặt đường startup |
| Công việc nền bắt buộc phải hoàn thành trước traffic | Runner đợi task, hoặc cơ chế readiness rõ ràng | Tránh công bố ready quá sớm |

Spring Boot khuyến nghị các tác vụ startup cần thiết chạy bằng runner thay vì đẩy một công việc dài vào `@PostConstruct`. `@PostConstruct` phục vụ khởi tạo bean, diễn ra trong quá trình xây context và dễ tạo phụ thuộc thứ tự bean khó kiểm soát.

## 7. Phân biệt ApplicationReadyEvent và ReadinessState

Tên `ApplicationReadyEvent` dễ khiến ta nghĩ readiness chỉ có hai trạng thái “chưa ready / đã ready” trong suốt vòng đời. Thực tế:

- **Event ready** là một thông báo gắn với **lần startup**.
- **Readiness state** phản ánh ứng dụng có muốn/được phép nhận thêm traffic **tại thời điểm hiện tại**.
- `ApplicationAvailability` là API để lấy trạng thái availability hiện hành.
- `AvailabilityChangeEvent` dùng để công bố một lần chuyển availability state.

Hai trạng thái readiness chuẩn là:

| `ReadinessState` | Ý nghĩa |
| --- | --- |
| `ACCEPTING_TRAFFIC` | Ứng dụng sẵn sàng tiếp nhận traffic |
| `REFUSING_TRAFFIC` | Ứng dụng chưa/không muốn tiếp nhận traffic |

Theo cơ chế Spring Boot, readiness được công bố là `ACCEPTING_TRAFFIC` **sau** `ApplicationReadyEvent`. Do vậy **đọc `ApplicationAvailability.getReadinessState()` bên trong listener ready có thể vẫn thấy trạng thái trước đó**; không dùng callback ready như một phép assert rằng availability event `ACCEPTING_TRAFFIC` đã phát xong.

Một listener quan sát thay đổi readiness:

```java
@EventListener
public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
    if (event.getState() == ReadinessState.ACCEPTING_TRAFFIC) {
        // Sẵn sàng nhận traffic.
    } else {
        // Chưa muốn nhận traffic.
    }
}
```

Đoạn này cần import `AvailabilityChangeEvent`, `ReadinessState`, `@EventListener` và đặt trong Spring bean; nó không thuộc ví dụ chạy mục 5.

`ApplicationReadyEvent` là mốc cố định của lần startup; trạng thái readiness có thể chuyển thành `REFUSING_TRAFFIC` khi dịch vụ quá tải rồi trở lại `ACCEPTING_TRAFFIC` mà không tạo thêm một `ApplicationReadyEvent` mới.

### Actuator readiness probe và Kubernetes

Khi dùng Spring Boot Actuator và health probes được cấu hình phù hợp, một readiness endpoint có thể được Kubernetes hoặc load balancer đọc để quyết định khi nào route request. Event `ApplicationReadyEvent` **không phải HTTP readiness endpoint**. Cơ chế probe cần cấu hình Actuator và policy của môi trường triển khai; event không tự biến thành một route HTTP.

Cũng cần phân biệt **liveness** với **readiness**. Liveness hỏi process còn ở trạng thái hợp lệ để tiếp tục vận hành không; readiness hỏi có nên gửi traffic mới đến nó không. Phụ thuộc một API ngoài đang tạm lỗi thường có ý nghĩa với readiness, không nhất thiết buộc restart liên tục vì liveness.

## 8. Sử dụng @Async ở listener ready

Một số tác vụ hậu startup như tạo báo cáo thống kê best-effort có thể chạy nền:

```java
@Component
public class ReadyBackgroundJob {
    @Async("maintenanceExecutor")
    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        // Công việc không bắt buộc trước khi phục vụ.
    }
}
```

Đây là mã minh họa cần `@EnableAsync`, bean executor `maintenanceExecutor` và import tương ứng. Với Spring `@Async`, lời gọi listener có thể được giao cho một thread pool, cho phép Boot tiếp tục startup.

**Rủi ro:** sau khi listener gửi task vào executor, Boot vẫn có thể công bố `ReadinessState.ACCEPTING_TRAFFIC`, dù task chưa hoàn tất. Nếu task đó nạp dữ liệu bắt buộc hoặc kiểm tra migration thiết yếu, ứng dụng có thể nhận request với trạng thái chưa đầy đủ.

Mẫu chống chỉ định về thiết kế:

```java
@Async("maintenanceExecutor")
@EventListener
public void onReady(ApplicationReadyEvent event) {
    mandatoryCatalog.loadAll();
}
```

Đoạn này cần dependency `mandatoryCatalog`; không phải chương trình độc lập. Nếu catalog là điều kiện không thể thiếu trước nhận traffic, hãy thực hiện/đợi nó trong runner, hoặc điều phối readiness rõ ràng bằng hệ thống health/checkpoint thích hợp. Đừng chỉ thấy annotation `@Async` chạy nhanh mà kết luận startup đã an toàn.

Các hệ quả khác khi dùng async:

1. Exception trong phương thức `@Async void` không tự truyền về caller; cần `AsyncUncaughtExceptionHandler` hoặc xử lý lỗi phù hợp.
2. Pool quá tải có thể từ chối task; cần quan sát `TaskRejectedException` và chính sách retry/backpressure.
3. Thread worker không tự mang transaction, security context hoặc MDC của luồng startup.
4. Process crash có thể làm mất task nằm trong bộ nhớ; dùng cơ chế bền vững nếu công việc không được phép mất.
5. Không được giả định thứ tự hoàn thành giữa nhiều listener async giống thứ tự đăng ký.

**Lưu ý tinh vi:** Boot công bố `ACCEPTING_TRAFFIC` **sau callback ready**. Do đó, nếu một listener ready tự phát `ReadinessState.REFUSING_TRAFFIC` ngay trong callback, trạng thái này có thể bị bước công bố accepting tiếp theo của Boot ghi đè. Nếu buộc phải kiểm soát readiness của startup, hãy dùng một điều kiện runner/health đúng thời điểm thay vì dựa vào việc đổi trạng thái bên trong callback ready.

## 9. Thay đổi readiness sau startup

Trong quá trình chạy, ứng dụng có thể bị quá tải hoặc mất một tài nguyên quan trọng. Có thể công bố trạng thái từ một Spring bean đã inject `ApplicationEventPublisher`:

```java
AvailabilityChangeEvent.publish(
        publisher, this, ReadinessState.REFUSING_TRAFFIC);
```

Khi phục hồi và thực sự có thể nhận thêm request:

```java
AvailabilityChangeEvent.publish(
        publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
```

Hai trích đoạn này cần import `AvailabilityChangeEvent`, `ReadinessState`, và biến `publisher` được inject; không phải ví dụ standalone. Chúng điều khiển **availability state** ở runtime; không thay thế `ApplicationReadyEvent` và không trực tiếp cấp phát hay đóng resource.

Đừng phát `ACCEPTING_TRAFFIC` chỉ vì một dependency vừa ping được nếu hệ thống còn chưa sẵn sàng về mặt nghiệp vụ. Hãy định nghĩa tập điều kiện đầy đủ cho readiness và khả năng khôi phục.

## 10. Vì sao ApplicationReadyEvent có thể không được phát?

Một số nguyên nhân điển hình:

| Hiện tượng | Khả năng giải thích | Cách kiểm tra |
| --- | --- | --- |
| Startup dừng trước ready | Bean/configuration hoặc runner ném exception | Xem lỗi gốc, đường `ApplicationFailedEvent` |
| Listener không nhận | Lớp không phải Spring bean, ngoài component scan hoặc sai loại event | Kiểm tra `@Bean`/`@Component` và chữ ký |
| Chạy `AnnotationConfigApplicationContext.refresh()` trực tiếp | Đây là Spring Framework context, không phải chuỗi `SpringApplication.run` | Dùng Boot `SpringApplication` để kiểm thử event Boot |
| Log ready xuất hiện muộn | Listener async hoặc quá trình startup mất thời gian | Quan sát runner, executor, thread và timestamp |
| Hệ thống nhiều context | Event nguồn từ context khác, listener có thể được gọi nhiều lần | Kiểm tra `event.getApplicationContext()` |
| Context bị dừng trước ready | Startup fail hoặc process bị hủy sớm | Xem lifecycle và nguyên nhân shutdown |

**Nếu một `ApplicationRunner` ném lỗi**, Boot không hoàn tất đường startup thành công và không phát ready event tương ứng. Việc bắt lỗi rồi tiếp tục trong runner chỉ để “cho Boot ready” có thể che một điều kiện bắt buộc chưa đạt.

Một listener ready đồng bộ ném exception chưa được xử lý có thể ảnh hưởng đường hoàn tất `SpringApplication.run(...)`. Nếu chỉ dùng để gửi log phụ, cần cân nhắc xử lý lỗi tại callback để không khiến lỗi quan sát nhỏ thành lỗi khởi động.

## 11. Nhiều ApplicationContext và event bị nhận nhiều lần

Spring Boot có thể sử dụng hierarchy của `SpringApplication` hoặc `ApplicationContext`. Event được publish từ context con có thể được chuyển lên context cha, khiến listener ở context cha nhận các event tương ứng. Với nghiệp vụ chỉ xử lý “ready của chính context này”, hãy so sánh nguồn:

```java
@Component
public class LocalReadyOnly {
    private final ApplicationContext ownContext;

    public LocalReadyOnly(ApplicationContext ownContext) {
        this.ownContext = ownContext;
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return;
        }
        // Chỉ xử lý ready của đúng context.
    }
}
```

Đây là đoạn tích hợp cần import `ApplicationContext`, `@Component`, `@EventListener` và `ApplicationReadyEvent`. Khi ứng dụng chỉ có một context, có thể không cần bộ lọc này. Với nhiều context, đừng đánh đồng một child context sẵn sàng với **toàn bộ process** đã sẵn sàng.

Ngoài ra, ứng dụng restart hoặc deploy lại sẽ có lần startup mới. Một callback thực hiện tác dụng phụ quan trọng (ví dụ gửi thông báo ra ngoài) nên được thiết kế idempotent để không tạo trùng trong những lần khởi động/retry hợp lệ.

## 12. Kiểm thử sự kiện và mốc ready

Bộ kiểm thử nên tách ba ý:

1. **Có event:** `ApplicationReadyEvent` thực sự được phát khi Boot startup thành công.
2. **Đúng thời điểm:** event xảy ra sau runner, nhưng trước readiness accepting được công bố.
3. **Đúng điều kiện:** startup lỗi không được coi là ready; background task chưa hoàn thành không được che giấu.

Ma trận tối thiểu:

| Tình huống | Kỳ vọng |
| --- | --- |
| Một runner chạy thành công | `ApplicationStartedEvent` → runner → `ApplicationReadyEvent` |
| Runner ném exception | Không có ready thành công cho lần startup |
| `getTimeTaken()` có giá trị | Kiểm tra kiểu `Duration` và thời gian không âm, không assert số cố định |
| Listener `@Async` chạy công việc dài | Không kết luận công việc đã hoàn tất khi Boot công bố ready |
| Context thuần không chạy `SpringApplication` | Không kỳ vọng Boot ready event tự phát |
| Ứng dụng có context cha/con | Kiểm tra event thuộc context nào |
| Instance đã ready nhưng sau đó mất khả năng phục vụ | Readiness state có thể thay đổi mà không cần event ready mới |

Kiểm thử ví dụ mục 5 bằng cách chạy với Maven và đối chiếu ba dòng `01`, `02`, `03`. Nếu thay runner bằng một đoạn ném lỗi để thử startup failure, dùng fixture hoặc process riêng và xác nhận callback ready không được gọi. Không test bằng cách gọi trực tiếp `new ReadyEventDemo.StartupObserver().onReady(...)` rồi xem đó là bằng chứng Boot đã phát event.

Với `@SpringBootTest`, Spring context có thể đã được khởi tạo **trước khi method test chạy**. Vì thế một listener được tạo muộn trong thân test sẽ bỏ lỡ các mốc startup. Hãy đăng ký listener đúng trong vòng đời khởi động cần kiểm thử và đợi kết quả bất đồng bộ bằng latch/future có timeout, không chỉ dựa vào `Thread.sleep(...)`.

## 13. Lỗi thường gặp

1. **Nhầm `ApplicationStartedEvent` với `ApplicationReadyEvent`.** Started là sau refresh nhưng trước runner, ready là sau runner.
2. **Dùng `ContextRefreshedEvent` làm bằng chứng hoàn tất startup Boot.** Refresh chưa bao gồm các runner.
3. **Cho rằng ready là sự kiện cuối cùng tuyệt đối.** Sau ready còn có `AvailabilityChangeEvent` với `ACCEPTING_TRAFFIC`, và ứng dụng tiếp tục phát nhiều event khác khi chạy.
4. **Cho rằng sự kiện ready đồng nghĩa mọi dependency khỏe.** Cần health/readiness checks riêng.
5. **Làm khởi tạo bắt buộc trong `@Async @EventListener(ApplicationReadyEvent)`.** Boot có thể nhận traffic trước khi tác vụ kết thúc.
6. **Để listener đồng bộ chặn quá lâu.** Callback có thể kéo dài thời gian khởi động, nên cân nhắc runner hoặc tác vụ nền đúng loại.
7. **Quên tạo listener là Spring bean.** Annotation đặt trên object Java do `new` bên ngoài không tự được đăng ký.
8. **Dùng Spring Framework thuần rồi chờ sự kiện Boot.** Phải chạy qua `SpringApplication`.
9. **Đo startup với một thời gian cứng.** `getTimeTaken()` thay đổi và có thể `null`.
10. **Bỏ qua context nguồn.** Trong hierarchy, listener có thể thấy event thuộc context con.
11. **Dùng `@TransactionalEventListener` cho sự kiện ready.** Thông thường không có transaction nghiệp vụ; với `fallbackExecution = false` callback sẽ không chạy. Dùng `@EventListener`.
12. **Tự tạo `ApplicationReadyEvent` để đánh dấu ứng dụng đã ready.** Phát một object event không thực hiện toàn bộ startup của Boot và không thay thế availability state.
13. **Cho rằng listener ready chạy đúng một lần mãi mãi.** Mỗi lần deploy/restart có lifecycle mới; cần idempotency cho tác dụng phụ quan trọng.
14. **Bỏ qua exception trong callback.** Một lỗi trong listener đồng bộ có thể ảnh hưởng startup; một lỗi async có thể chỉ đi vào handler/log.

## 14. Checklist khi áp dụng

- [ ] Đã dùng `ApplicationReadyEvent` từ package `org.springframework.boot.context.event`.
- [ ] Đã hiểu `ApplicationStartedEvent` chạy trước các runner, `ApplicationReadyEvent` chạy sau chúng.
- [ ] Đã phân biệt ready event với `ReadinessState.ACCEPTING_TRAFFIC` được công bố sau đó.
- [ ] Listener là Spring bean hoặc được đăng ký đúng thời điểm.
- [ ] Các điều kiện startup bắt buộc không bị giấu trong task `@Async` fire-and-forget.
- [ ] Tác vụ listener có chính sách timeout, error handling và observability phù hợp.
- [ ] `getTimeTaken()` được kiểm tra `null` trước khi dùng.
- [ ] Đã kiểm thử startup thành công và thất bại, không chỉ gọi phương thức listener thủ công.
- [ ] Với hierarchy nhiều context, biết rõ event đến từ context nào.
- [ ] Không nhầm sự kiện ready một lần với readiness health state thay đổi ở runtime.
- [ ] Tác dụng phụ quan trọng được bảo vệ bằng idempotency/retry hoặc job/outbox bền vững.

**Ghi nhớ:** `ApplicationReadyEvent` là mốc Spring Boot đã thực thi xong các runner trong một lần startup thành công. Để khởi tạo dữ liệu bắt buộc trước nhận traffic, dùng runner và đợi hoàn thành; để quan sát mốc hoàn tất startup, dùng listener ready; để điều phối traffic theo tình trạng đang thay đổi, dùng readiness state và health probes.

## Tài liệu tham khảo

- [Spring Boot — SpringApplication / Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot — Application Availability and Readiness State](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-availability)
- [Spring Boot Javadoc — ApplicationReadyEvent](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html)
- [Spring Boot Javadoc — ApplicationStartedEvent](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html)
- [Spring Boot Javadoc — ReadinessState](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/availability/ReadinessState.html)
