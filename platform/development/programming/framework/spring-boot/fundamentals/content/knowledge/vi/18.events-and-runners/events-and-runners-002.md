# ApplicationStartingEvent và ApplicationEnvironmentPreparedEvent

Spring Boot phát ra các application event trong suốt quá trình khởi động. Một số event xuất hiện rất sớm, trước khi ApplicationContext được tạo hoặc refresh. Hai event quan trọng ở giai đoạn này là `ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent`.

Chúng giúp listener quan sát hai mốc khác nhau: ứng dụng vừa bắt đầu chạy và Environment dành cho ApplicationContext đã được chuẩn bị. Hiểu rõ thời điểm phát, dữ liệu có thể truy cập và cách đăng ký listener giúp đặt logic bootstrap đúng chỗ.

## 1. ApplicationStartingEvent

`ApplicationStartingEvent` thuộc package `org.springframework.boot.context.event`. Spring Boot phát event này ở đầu quá trình `SpringApplication.run()`, trước khi Environment của ứng dụng và ApplicationContext được tạo.

Ở thời điểm này, có thể ghi nhận rằng quá trình khởi động đã bắt đầu, nhưng chưa thể dựa vào:

- ApplicationContext của ứng dụng.
- Các bean nghiệp vụ.
- Environment đã được chuẩn bị với toàn bộ nguồn cấu hình của ứng dụng.
- Các giá trị cấu hình được nạp từ `application.yml` và profile.

Event phù hợp với các tác vụ rất sớm, chẳng hạn ghi dấu mốc khởi động, khởi tạo cơ chế quan sát bootstrap độc lập với context hoặc thu thập thông tin không phụ thuộc vào cấu hình ứng dụng.

Không nên dùng event này để đọc property của ứng dụng hoặc lấy service từ Spring container vì các thành phần đó chưa sẵn sàng.

## 2. ApplicationEnvironmentPreparedEvent

Spring Boot phát `ApplicationEnvironmentPreparedEvent` khi Environment được chuẩn bị cho ApplicationContext, trước khi chính context được tạo. Việc công bố event cũng kích hoạt các listener chuẩn bị Environment, trong đó có listener gọi các `EnvironmentPostProcessor`.

Listener có thể lấy Environment từ event:

~~~java
ConfigurableEnvironment environment =
        event.getEnvironment();
~~~

Environment cung cấp quyền truy cập tới:

- Các property source hiện có.
- Giá trị cấu hình như `spring.application.name`.
- Active profiles và default profiles.
- Các thuộc tính môi trường được dùng để quyết định cấu hình ứng dụng.

Ví dụ, có thể đọc tên ứng dụng và profile:

~~~java
String applicationName = environment.getProperty(
        "spring.application.name",
        "unnamed"
);

String[] activeProfiles = environment.getActiveProfiles();
~~~

Tuy nhiên, đây vẫn là giai đoạn trước khi ApplicationContext được tạo. Listener chưa thể lấy bean nghiệp vụ từ context. Nếu cần đăng ký bean, hãy dùng cơ chế cấu hình Spring; nếu cần bổ sung hoặc điều chỉnh Environment ở giai đoạn chuẩn bị, hãy cân nhắc `EnvironmentPostProcessor`.

### Lưu ý về Config Data và thứ tự listener

Spring Boot xử lý Environment thông qua nhiều bước và các `EnvironmentPostProcessor`. Khi `ApplicationEnvironmentPreparedEvent` được phát, listener chuyên trách của Boot gọi các processor này. Cơ chế Config Data, bao gồm việc nạp `application.yml`, file theo profile và import cấu hình, tham gia giai đoạn chuẩn bị Environment này.

`ApplicationEnvironmentPreparedEvent` là mốc thông báo Environment đã được tạo và đưa vào quá trình chuẩn bị context. Nếu một listener cần quan sát kết quả sau một EnvironmentPostProcessor cụ thể, thứ tự listener phải được xác định rõ. Không nên giả định mọi listener đều nhìn thấy cùng một trạng thái Environment nếu chúng được sắp xếp ở các thời điểm khác nhau trong quá trình phát event.

Nếu mục tiêu là thay đổi Environment trước khi điều kiện cấu hình hoặc Config Data được xử lý, `EnvironmentPostProcessor` là extension point chuyên biệt. Việc dùng listener để thay đổi Environment cần cân nhắc thứ tự xử lý và thời điểm event.

## 3. So sánh hai event

| Tiêu chí | ApplicationStartingEvent | ApplicationEnvironmentPreparedEvent |
|---|---|---|
| Thời điểm | Đầu quá trình chạy SpringApplication | Khi Environment được tạo và đưa vào giai đoạn chuẩn bị |
| Environment ứng dụng | Chưa có | Có thể truy cập qua event |
| ApplicationContext | Chưa được tạo | Chưa được tạo |
| Bean nghiệp vụ | Chưa có | Chưa có |
| Công việc phù hợp | Ghi nhận mốc bắt đầu, bootstrap độc lập | Đọc thông tin Environment, quan sát cấu hình |
| Có thể dùng để lấy bean | Không | Không |

Luồng khởi động rút gọn:

~~~text
SpringApplication.run()
        |
        v
ApplicationStartingEvent
        |
        v
Tạo và chuẩn bị Environment
        |
        v
ApplicationEnvironmentPreparedEvent
        |
        v
EnvironmentPostProcessor / Config Data
(được gọi bởi listener của Boot theo thứ tự)
        |
        v
Tạo ApplicationContext
        |
        v
ApplicationContextInitializer
        |
        v
ApplicationContextInitializedEvent
        |
        v
Nạp bean definitions
        |
        v
ApplicationPreparedEvent
        |
        v
refresh()
~~~

Sơ đồ thể hiện các mốc chính. Việc xử lý Environment và phát event có thể bao gồm nhiều listener được sắp xếp theo order; khi cần can thiệp ở một thời điểm chính xác, hãy dùng extension point được thiết kế cho giai đoạn đó.

## 4. Đăng ký listener cho các event sớm

Vì hai event được phát trước khi bean của ứng dụng được tạo, không thể dựa vào một lớp `@Component` hoặc phương thức `@EventListener` trong bean để bắt chúng. Listener phải được đăng ký với `SpringApplication` trước khi gọi `run()`, hoặc được phát hiện qua cơ chế Spring factories.

Ví dụ, một listener quan sát cả hai event:

~~~java
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;

public class EarlyStartupListener
        implements ApplicationListener<ApplicationEvent> {

    @Override
    public void onApplicationEvent(ApplicationEvent event) {
        if (event instanceof ApplicationStartingEvent) {
            System.out.println("Application startup is beginning");
            return;
        }

        if (event instanceof ApplicationEnvironmentPreparedEvent prepared) {
            String applicationName = prepared.getEnvironment().getProperty(
                    "spring.application.name",
                    "unnamed"
            );

            String[] activeProfiles =
                    prepared.getEnvironment().getActiveProfiles();

            System.out.println("Application: " + applicationName);
            System.out.println(
                    "Active profiles: "
                            + String.join(", ", activeProfiles)
            );
        }
    }
}
~~~

Đăng ký listener trước khi khởi chạy:

~~~java
import org.springframework.boot.SpringApplication;

public class ApplicationLauncher {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(Application.class);

        application.addListeners(new EarlyStartupListener());

        application.run(args);
    }
}
~~~

Khi `run()` bắt đầu, listener đã nằm trong danh sách listener của `SpringApplication`, nên có thể nhận các event sớm. Cách đăng ký này phù hợp khi ứng dụng sở hữu lớp main và muốn kiểm soát rõ listener nào được dùng.

Có thể đăng ký nhiều listener:

~~~java
application.addListeners(
        new EarlyStartupListener(),
        new StartupMetricsListener()
);
~~~

Nếu listener chỉ cần một loại event, có thể triển khai interface với kiểu event cụ thể:

~~~java
public class StartingListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("SpringApplication is starting");
    }
}
~~~

Cách dùng kiểu cụ thể giúp compiler thể hiện rõ event mà listener xử lý.

## 5. Đăng ký listener qua Spring factories

Một thư viện có thể tự công bố listener để ứng dụng sử dụng thư viện tự động phát hiện nó. Với Spring Boot, có thể khai báo trong resource `META-INF/spring.factories`:

~~~properties
org.springframework.context.ApplicationListener=\
com.example.bootstrap.EarlyStartupListener
~~~

Spring Boot sử dụng `SpringFactoriesLoader` để phát hiện các listener theo key tương ứng. Khi đóng gói thư viện, cần kiểm tra file được đưa vào JAR đúng đường dẫn và tên class đầy đủ chính xác.

Cơ chế này hữu ích khi viết thư viện hoặc starter cần quan sát event sớm mà không yêu cầu ứng dụng tự tạo listener trong lớp main.

Cần phân biệt hai dạng đăng ký:

- `SpringApplication.addListeners(...)`: ứng dụng chủ động đăng ký instance listener.
- `META-INF/spring.factories`: thư viện công bố implementation để Spring Boot phát hiện.

Đối với event rất sớm, listener cần được đăng ký trước khi `SpringApplication.run()` phát event tương ứng. Đăng ký listener sau khi ứng dụng đã chạy không làm nó nhận lại các event đã phát.

## 6. Các event tiếp theo trong quá trình khởi động

Sau hai event đầu, Spring Boot tiếp tục phát các event đánh dấu những giai đoạn khác nhau:

| Event | Thời điểm | Thành phần có thể sử dụng |
|---|---|---|
| `ApplicationContextInitializedEvent` | Context đã được tạo và các initializer đã chạy, trước khi bean definitions được nạp | Context đã tồn tại; có thể truy cập Environment và context metadata |
| `ApplicationPreparedEvent` | Bean definitions đã được nạp, ngay trước khi refresh | Context và bean definitions đã được chuẩn bị |
| `ContextRefreshedEvent` | ApplicationContext hoàn tất refresh | Bean đã được tạo theo quá trình refresh |
| `ApplicationStartedEvent` | Context đã refresh, trước khi chạy ApplicationRunner và CommandLineRunner | Các bean đã sẵn sàng; runner chưa hoàn tất |
| `ApplicationReadyEvent` | Sau khi các runner hoàn tất | Spring Boot phát tín hiệu ứng dụng đã sẵn sàng |
| `ApplicationFailedEvent` | Quá trình khởi động thất bại | Thông tin lỗi và context nếu context đã được tạo |

Hai event đầu không thay thế các event sau. Hãy chọn event theo trạng thái thực tế mà logic cần sử dụng.

Ví dụ:

- Chỉ cần ghi dấu ứng dụng bắt đầu: `ApplicationStartingEvent`.
- Cần đọc Environment trước khi context tạo: `ApplicationEnvironmentPreparedEvent`.
- Cần biết các initializer đã hoàn tất: `ApplicationContextInitializedEvent`.
- Cần quan sát bean definitions đã được nạp trước refresh: `ApplicationPreparedEvent`.
- Cần chạy công việc sau khi context refresh: `ApplicationStartedEvent` hoặc runner tùy yêu cầu.
- Cần biết startup workflow của Spring Boot đã hoàn tất: `ApplicationReadyEvent`.

### ApplicationStartedEvent và ApplicationReadyEvent

Hai event này dễ bị nhầm lẫn. `ApplicationStartedEvent` được phát sau khi context refresh, nhưng trước khi `ApplicationRunner` và `CommandLineRunner` chạy. `ApplicationReadyEvent` được phát sau khi các runner hoàn tất và là tín hiệu readiness ở cấp Spring Boot.

Nếu công việc cần dùng các bean đã được tạo nhưng không cần đợi runner, có thể xem xét `ApplicationStartedEvent`. Nếu cần thực hiện hoặc quan sát trạng thái sau các runner, dùng `ApplicationReadyEvent`.

Không nên dùng event sớm để chạy tác vụ dài hoặc gọi hệ thống bên ngoài nếu tác vụ đó không cần thiết cho bootstrap. Các listener chạy trong quá trình startup có thể kéo dài thời gian khởi động và làm startup thất bại nếu ném exception.

## 7. ApplicationListener và @EventListener

Spring cung cấp hai cách phổ biến để xử lý application event.

### ApplicationListener

`ApplicationListener<E>` là interface kiểu hóa theo event. Có thể đăng ký listener trực tiếp với `SpringApplication` để nhận event sớm:

~~~java
public class StartingListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        // Xử lý mốc bắt đầu.
    }
}
~~~

Cách này phù hợp với event phát trước khi ApplicationContext tạo hoặc trước khi bean được nạp.

### @EventListener

`@EventListener` là annotation đặt trên phương thức của bean:

~~~java
@Component
public class ReadyEventHandler {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("Application is ready");
    }
}
~~~

Bean chứa phương thức này chỉ được đăng ký khi context xử lý bean definitions và khởi tạo bean. Vì vậy, đây là cách phù hợp với event được phát sau khi context đã có listener bean, chẳng hạn `ApplicationReadyEvent`.

Không nên đặt `@EventListener` trong một bean để xử lý `ApplicationStartingEvent` hoặc `ApplicationEnvironmentPreparedEvent`, bởi bean chưa được tạo tại thời điểm các event đó phát ra. Hãy dùng listener đăng ký sớm với `SpringApplication`.

## 8. Những lưu ý khi xử lý event khởi động

### Không giả định Environment đã có ở ApplicationStartingEvent

Event này phát trước khi Environment ứng dụng được chuẩn bị. Nếu cần đọc property, đợi `ApplicationEnvironmentPreparedEvent` hoặc dùng extension point tương ứng.

### Không giả định ApplicationContext đã tồn tại ở ApplicationEnvironmentPreparedEvent

Environment đã có nhưng context chưa được tạo. Listener không thể lấy bean nghiệp vụ từ context ở giai đoạn này.

### Không đăng ký listener quá muộn

Listener phải được thêm vào trước khi event phát. Gọi `addListeners()` sau `run()` không làm các event trước đó được phát lại.

### Không thực hiện công việc nặng trong listener

Listener chạy đồng bộ trong quá trình phát event. I/O chậm, gọi mạng hoặc xử lý dài có thể làm startup kéo dài. Chỉ thực hiện phần cần thiết cho giai đoạn tương ứng và đặt timeout rõ ràng nếu có thao tác bên ngoài.

### Xác định thứ tự listener khi cần quan sát kết quả của listener khác

Nhiều listener có thể cùng nhận một event. Nếu một listener phụ thuộc vào thay đổi Environment của listener khác, cần khai báo thứ tự bằng `Ordered` hoặc `@Order` theo cơ chế hỗ trợ và kiểm thử kết quả. Không dựa vào thứ tự tình cờ của classpath hoặc thứ tự component scan.

### Xử lý lỗi khởi động có chủ đích

Nếu listener ném exception trong quá trình startup, ứng dụng có thể không khởi động thành công. Nếu lỗi là điều kiện bắt buộc, hãy ném exception có thông điệp rõ ràng. Nếu chỉ là telemetry hoặc ghi log, hãy cô lập lỗi của hệ thống quan sát để tránh làm hỏng startup vì một thao tác phụ.

## 9. Kiểm tra listener và thứ tự event

Có thể kiểm tra listener bằng cách khởi chạy một `SpringApplication` thử nghiệm và thu thập thứ tự event. Một listener đơn giản có thể ghi tên event vào danh sách hoặc log:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;

public class StartupEventRecorder
        implements ApplicationListener<ApplicationEvent> {

    private final List<String> events = new ArrayList<>();

    @Override
    public void onApplicationEvent(ApplicationEvent event) {
        if (event instanceof ApplicationStartingEvent) {
            events.add("starting");
        } else if (event instanceof ApplicationEnvironmentPreparedEvent) {
            events.add("environment-prepared");
        } else if (event instanceof ApplicationContextInitializedEvent) {
            events.add("context-initialized");
        } else if (event instanceof ApplicationPreparedEvent) {
            events.add("prepared");
        } else if (event instanceof ApplicationStartedEvent) {
            events.add("started");
        } else if (event instanceof ApplicationReadyEvent) {
            events.add("ready");
        }
    }

    public List<String> getEvents() {
        return List.copyOf(events);
    }
}
~~~

Trong test tích hợp, đăng ký recorder với `SpringApplication` trước khi chạy. Sau khi startup hoàn tất, kiểm tra thứ tự các mốc quan trọng:

~~~text
starting
environment-prepared
context-initialized
prepared
started
ready
~~~

Khi viết test, cần lưu ý các event có thể được phát thêm trong những kịch bản đặc biệt như parent/child context hoặc khởi động nhiều context. Nên kiểm tra các quan hệ thứ tự cần thiết thay vì giả định mọi ứng dụng đều chỉ phát đúng một event cho toàn bộ vòng đời.

## 10. Quy trình chọn event phù hợp

Khi cần phản ứng với một giai đoạn startup, hãy xác định trạng thái tối thiểu mà logic cần:

1. Nếu chỉ cần biết lệnh khởi động đã bắt đầu, dùng `ApplicationStartingEvent`.
2. Nếu cần đọc Environment trước khi context được tạo, dùng `ApplicationEnvironmentPreparedEvent`.
3. Nếu cần tùy chỉnh Environment trước Config Data, xem xét `EnvironmentPostProcessor`.
4. Nếu cần tùy chỉnh context trước refresh, xem xét `ApplicationContextInitializer`.
5. Nếu cần xử lý bean definitions, dùng `BeanFactoryPostProcessor` ở đúng giai đoạn refresh.
6. Nếu cần bean nghiệp vụ đã sẵn sàng, chọn event hoặc runner sau refresh.
7. Đăng ký listener trước thời điểm event phát và xác định thứ tự nếu các listener phụ thuộc nhau.
8. Giữ listener nhanh, có thể kiểm soát lỗi và tránh truy cập bean trước khi context sẵn sàng.

`ApplicationStartingEvent` đánh dấu lúc Spring Boot bắt đầu khởi chạy; `ApplicationEnvironmentPreparedEvent` đánh dấu lúc Environment đã có để chuẩn bị ApplicationContext. Phân biệt hai mốc này giúp đọc cấu hình đúng thời điểm, đăng ký listener đúng cách và đặt công việc bootstrap vào giai đoạn phù hợp của vòng đời Spring Boot.

