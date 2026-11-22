# ApplicationFailedEvent và thông tin lỗi khởi động

Một ứng dụng Spring Boot có thể thất bại ngay khi chuẩn bị `Environment`, trong lúc tạo `ApplicationContext`, khi khởi tạo bean hoặc khi chạy một tác vụ khởi động. Những lỗi này xảy ra **trước khi ứng dụng thực sự sẵn sàng phục vụ**, nên đôi khi hệ thống giám sát qua HTTP hay một bean xử lý nghiệp vụ cũng chưa hoạt động.

**ApplicationFailedEvent** là sự kiện Spring Boot phát ra khi quá trình khởi động do `SpringApplication` quản lý gặp lỗi. Sự kiện này mang theo ngoại lệ gây thất bại và, nếu đã tạo được, tham chiếu đến application context. Đây là điểm mở rộng để thu thập thông tin lỗi khởi động, ghi log bổ sung hoặc thông báo cho cơ chế giám sát có thể hoạt động ở giai đoạn sớm.

Bài học nằm trong chủ đề **Sự kiện và runner** vì lỗi có thể xuất hiện cả trước lẫn trong quá trình thực thi `ApplicationRunner` hoặc `CommandLineRunner`. Để dùng sự kiện hiệu quả, cần hiểu thời điểm phát sự kiện, dữ liệu có thể đọc và giới hạn của các thành phần chưa được khởi tạo.

## 1. ApplicationFailedEvent là gì?

`ApplicationFailedEvent` thuộc package:

~~~java
org.springframework.boot.context.event.ApplicationFailedEvent
~~~

Đây là một sự kiện vòng đời của Spring Boot, được phát khi `SpringApplication` xử lý một lỗi làm quá trình startup không hoàn tất. Nó thuộc nhóm sự kiện của `SpringApplication`, không chỉ là một thông báo lỗi của một bean riêng lẻ.

Ví dụ những tình huống có thể dẫn đến sự kiện:

- Cấu hình không hợp lệ hoặc một giá trị cấu hình không thể bind sang Java object.
- Bean không tạo được vì thiếu dependency, vòng phụ thuộc hoặc exception trong constructor.
- Server nhúng không bind được cổng đang sử dụng.
- `@Bean` factory method ném exception khi container tạo bean.
- Một `ApplicationRunner` hoặc `CommandLineRunner` ném exception.
- Một callback trong quá trình startup làm `SpringApplication.run(...)` thất bại.

Điểm quan trọng: **ApplicationFailedEvent thông báo việc khởi động đã gặp lỗi; tự nó không sửa lỗi hay làm ứng dụng tiếp tục chạy.** Thông thường Spring Boot tiếp tục xử lý thất bại, đóng context nếu cần và chuyển exception cho phía gọi `run(...)`.

Sự kiện này không được bảo đảm xuất hiện với những sự cố nằm ngoài luồng startup mà `SpringApplication` có thể bắt và phát sự kiện, ví dụ lỗi xảy ra trước khi gọi `run(...)`, JVM bị kết thúc đột ngột hoặc tiến trình bị hệ điều hành hủy.

## 2. Vị trí của sự kiện trong vòng đời Spring Boot

Trong một lần khởi động thành công, những mốc quan trọng thường là:

~~~text
main()
  |
  v
SpringApplication.run(args)
  |
  v
Chuẩn bị Environment và ApplicationContext
  |
  v
Đọc cấu hình, tạo bean definitions, refresh context
  |
  v
ApplicationStartedEvent
  |
  v
Chạy ApplicationRunner / CommandLineRunner
  |
  v
ApplicationReadyEvent
  |
  v
Ứng dụng sẵn sàng
~~~

Nếu có exception làm startup thất bại, luồng sẽ đi sang nhánh xử lý lỗi:

~~~text
SpringApplication.run(args)
       |
       +-- Chuẩn bị môi trường ------ lỗi --+
       |                                    |
       +-- Chuẩn bị/refresh context - lỗi --+--> ApplicationFailedEvent
       |                                    |      |
       +-- Chạy runners ------------- lỗi --+      v
       |                                    |   Xử lý thất bại
       +-- Hoàn tất startup --------- lỗi --+   và kết thúc run
       |
       +-- Không có lỗi --> ApplicationReadyEvent
~~~

Đây là sơ đồ khái quát, không liệt kê mọi sự kiện và callback nội bộ của Spring Boot.

Hai hệ quả cần nhớ:

1. Nếu lỗi xuất hiện **trước khi context được tạo**, `ApplicationFailedEvent` vẫn có thể được phát nhưng không có `ApplicationContext` để truy cập.
2. Nếu lỗi nằm trong một runner, context thường đã được refresh và `ApplicationStartedEvent` thường đã phát, nhưng `ApplicationReadyEvent` chưa được phát thành công.

Sự khác biệt thứ hai rất hữu ích: **Started** có nghĩa context đã được refresh và Spring Boot chuẩn bị chạy runners; **Ready** thể hiện quá trình startup đã đi qua các runners và tới giai đoạn sẵn sàng.

## 3. Những thông tin có trong ApplicationFailedEvent

Các API cần dùng thường xuyên:

| API | Ý nghĩa | Cách dùng |
|---|---|---|
| `event.getException()` | Trả về `Throwable` liên quan đến lỗi startup | Ghi đầy đủ stack trace, phân tích chuỗi nguyên nhân |
| `event.getApplicationContext()` | Trả về context nếu đã được tạo, có thể là `null` | Đọc thông tin context đơn giản nếu tồn tại |
| `event.getSpringApplication()` | Trả về đối tượng `SpringApplication` liên quan | Xác định ứng dụng đã được chạy |
| `event.getArgs()` | Trả về mảng đối số khởi động | Chỉ dùng khi thực sự cần; tránh ghi bí mật từ command line |

Ví dụ:

~~~java
@Override
public void onApplicationEvent(ApplicationFailedEvent event) {
    Throwable failure = event.getException();

    ConfigurableApplicationContext context =
            event.getApplicationContext();

    System.err.println("Loại lỗi: " + failure.getClass().getName());

    if (context != null) {
        System.err.println("Context ID: " + context.getId());
    } else {
        System.err.println("ApplicationContext chưa được tạo.");
    }
}
~~~

Đoạn trên minh họa cách đọc event; trong ứng dụng thực tế nên sử dụng logger phù hợp thay cho `System.err` khi hệ thống logging đã sẵn sàng.

### Vì sao getApplicationContext() có thể là null?

Spring Boot phải thực hiện một số việc **trước khi có context**, như xử lý các nguồn cấu hình ban đầu và chuẩn bị môi trường. Nếu quá trình startup dừng ở giai đoạn này, không có context để cung cấp cho listener.

Ngay cả khi `getApplicationContext()` khác `null`, context cũng chưa chắc đã refresh thành công, còn active hoặc chứa mọi bean thông thường. Vì vậy, **không được suy luận rằng context tồn tại thì có thể gọi mọi service trong đó**.

Một listener an toàn cần chịu được cả ba trạng thái:

- Context chưa được tạo: `null`.
- Context đã được tạo nhưng quá trình refresh thất bại.
- Context đã refresh, rồi một runner hoặc callback startup ném exception.

## 4. Cách đăng ký listener đủ sớm để bắt lỗi startup

Vì lỗi có thể xảy ra khi bean ứng dụng chưa được tạo, cách dễ hiểu và tin cậy cho ví dụ này là **đăng ký listener trực tiếp vào SpringApplication trước khi gọi run**.

Giả sử dự án Spring Boot có package `com.example.startup`.

File `DemoApplication.java`:

~~~java
package com.example.startup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.addListeners(new StartupFailureListener());
        application.run(args);
    }
}
~~~

File `StartupFailureListener.java`:

~~~java
package com.example.startup;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;

public final class StartupFailureListener
        implements ApplicationListener<ApplicationFailedEvent> {

    private static final Logger log =
            LoggerFactory.getLogger(StartupFailureListener.class);

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable failure = event.getException();
        ConfigurableApplicationContext context =
                event.getApplicationContext();

        String contextId = context == null
                ? "(chưa có context)"
                : context.getId();

        log.error("Khởi động Spring Boot thất bại; context=" + contextId,
                failure);
    }
}
~~~

Ở đây:

1. `main()` tự tạo `SpringApplication`.
2. `addListeners(...)` đăng ký listener trước khi `run(args)` bắt đầu.
3. Khi Spring Boot phát `ApplicationFailedEvent` trong quá trình startup, listener nhận sự kiện.
4. Listener đọc context theo cách an toàn với `null`.
5. Lời gọi `log.error(message, failure)` ghi kèm đối tượng `Throwable`, nhờ đó logger có thể ghi stack trace.

Hai file trên dùng các API thông dụng của Spring Boot, Spring Context và SLF4J. Với một project có `spring-boot-starter` hoặc các starter Boot phù hợp, các thư viện cần thiết thường đã nằm trong dependency graph.

### Vì sao lại đăng ký trên SpringApplication?

Cách viết thông thường:

~~~java
SpringApplication.run(DemoApplication.class, args);
~~~

rất gọn nhưng không cho bạn một biến `SpringApplication` để gọi `addListeners(...)` trước khi chạy. Khi cần một listener sớm, tạo instance và đăng ký tường minh giúp người đọc thấy rõ trình tự.

**Không cần dùng dependency injection để tạo StartupFailureListener trong ví dụ này.** Listener chỉ dùng logger và dữ liệu được truyền qua event, nên nó hoạt động độc lập với các service nghiệp vụ có thể chưa khởi tạo.

## 5. Có nên dùng @EventListener hoặc @Component không?

Trong Spring, các sự kiện thường được xử lý bằng method có `@EventListener`:

~~~java
@Component
public class FailureEventHandler {

    @EventListener
    public void onFailed(ApplicationFailedEvent event) {
        // Xử lý thông tin lỗi.
    }
}
~~~

Cách này thuận tiện cho những sự kiện được publish **sau khi context đã sẵn sàng tiếp nhận event**. Tuy nhiên, `ApplicationFailedEvent` có thể được phát khi Spring vẫn đang xây dựng context hoặc đã thất bại trước lúc đăng ký đầy đủ các listener đến từ bean.

Vì vậy, **không nên phụ thuộc duy nhất vào một `@EventListener` nằm trong bean ứng dụng nếu yêu cầu là quan sát lỗi startup ở mọi giai đoạn sớm**. Ngay cả một `@Component` triển khai `ApplicationListener<ApplicationFailedEvent>` cũng có giới hạn tương tự khi Spring chưa tạo hoặc chưa đăng ký bean đó.

So sánh:

| Cách đăng ký | Ưu điểm | Giới hạn chính |
|---|---|---|
| `application.addListeners(new StartupFailureListener())` trước `run()` | Listener được đăng ký từ đầu trong `SpringApplication` | Tự quản lý các dependency của listener |
| `@Component` kết hợp `ApplicationListener` | Dễ tích hợp với bean ứng dụng | Bean/listener có thể chưa sẵn sàng khi startup thất bại sớm |
| Method `@EventListener` trong một bean | Ngắn gọn, quen thuộc với sự kiện runtime | Phụ thuộc vào quá trình khởi tạo và xử lý annotation của context |

Một listener bắt lỗi khởi động cần **ít dependency**, không yêu cầu bean nghiệp vụ và xử lý tốt tình huống context vắng mặt.

## 6. ApplicationFailedEvent khi ApplicationRunner thất bại

`ApplicationRunner` và `CommandLineRunner` cho phép chạy tác vụ sau khi context đã refresh nhưng trước mốc ready của ứng dụng.

Ví dụ một runner ném lỗi để mô phỏng quá trình chuẩn bị dữ liệu thất bại:

~~~java
package com.example.startup;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class StartupTaskConfiguration {

    @Bean
    ApplicationRunner prepareInitialData() {
        return args -> {
            System.out.println("Đang chuẩn bị dữ liệu ban đầu...");
            throw new IllegalStateException(
                    "Không thể chuẩn bị dữ liệu ban đầu");
        };
    }
}
~~~

Nếu component này được Spring Boot phát hiện:

1. Spring khởi tạo và refresh context.
2. Spring Boot phát `ApplicationStartedEvent`.
3. Spring Boot gọi `prepareInitialData()` qua cơ chế `ApplicationRunner`.
4. Runner ném `IllegalStateException`.
5. `SpringApplication` xử lý lỗi và phát `ApplicationFailedEvent`.
6. `ApplicationReadyEvent` không được phát như một mốc startup thành công.

Nếu đã đăng ký `StartupFailureListener` ở phần trước, listener sẽ ghi một thông báo lỗi và stack trace liên quan. Việc nhận `ApplicationFailedEvent` không khiến Spring Boot tiếp tục chạy những runner còn lại hay chuyển sang trạng thái ready.

### Với CommandLineRunner thì sao?

`CommandLineRunner` có thời điểm thực thi tương tự:

~~~java
@Bean
CommandLineRunner validateStartupState() {
    return args -> {
        if (!isStartupStateValid()) {
            throw new IllegalStateException(
                    "Trạng thái khởi động không hợp lệ");
        }
    };
}
~~~

`isStartupStateValid()` là phương thức giả định do ứng dụng tự định nghĩa. Ý chính là: **nếu runner ném exception thoát ra ngoài, nó có thể khiến toàn bộ lần khởi động bị coi là thất bại** và dẫn đến `ApplicationFailedEvent`.

Trong dự án thực tế, không nên cố tình ném lỗi để quan sát sự kiện ở môi trường production. Có thể dùng một cấu hình hoặc runner mô phỏng trong môi trường học tập riêng.

## 7. Phân biệt ApplicationStartedEvent, ApplicationReadyEvent và ApplicationFailedEvent

Ba sự kiện này cho biết ba trạng thái khác nhau trong quá trình startup:

| Sự kiện | Thời điểm thường gặp | Điều có thể kết luận |
|---|---|---|
| `ApplicationStartedEvent` | Context đã được refresh, trước khi runners chạy | Container đã qua giai đoạn refresh; startup còn bước tiếp |
| `ApplicationReadyEvent` | Runners đã hoàn thành và Spring Boot đi tới giai đoạn ready | Quá trình khởi động chính đã hoàn tất thành công |
| `ApplicationFailedEvent` | Có lỗi làm `SpringApplication` không hoàn tất startup | Cần xem exception và xử lý việc ứng dụng không khởi động được |

Các ví dụ:

**Tình huống A — Sai cấu hình từ rất sớm:** Có thể nhận `ApplicationFailedEvent` mà không có context; `ApplicationStartedEvent` và `ApplicationReadyEvent` chưa xảy ra.

**Tình huống B — BeanCreationException trong refresh:** Context có thể đã được tạo nhưng chưa khởi tạo xong. `ApplicationStartedEvent` thường chưa phát.

**Tình huống C — ApplicationRunner ném exception:** `ApplicationStartedEvent` thường đã xảy ra; `ApplicationFailedEvent` được phát; ứng dụng không đạt mốc ready thành công.

Điều này có ý nghĩa khi quan sát log: thấy `ApplicationStartedEvent` không đủ để kết luận ứng dụng đã sẵn sàng nhận lưu lượng. Nếu còn runner cần chạy, mốc ready vẫn ở phía sau.

## 8. Đọc exception đúng cách

`event.getException()` trả về một `Throwable`. Lỗi quan sát được ở lớp ngoài có thể là exception của container, trong khi nguyên nhân kỹ thuật nằm sâu hơn trong chuỗi `cause`.

Ví dụ dạng chuỗi nguyên nhân:

~~~text
BeanCreationException
  |
  +-- UnsatisfiedDependencyException
        |
        +-- IllegalArgumentException
              |
              +-- "Giá trị cấu hình không hợp lệ"
~~~

Stack trace và chuỗi `Caused by` giúp xác định:

- Bean hoặc factory method nào gặp lỗi.
- Dependency nào không được đáp ứng.
- Lớp và dòng mã nào ném exception ban đầu.
- Có lỗi I/O, cấu hình, kết nối hoặc kiểu dữ liệu bên dưới hay không.

### Ghi cả Throwable, thay vì chỉ lấy message

Cách ghi thiếu thông tin:

~~~java
log.error("Startup failed: {}", event.getException().getMessage());
~~~

Dòng trên chỉ ghi message. Nó bỏ mất stack trace và những `cause` lồng nhau cần thiết để điều tra.

Cách đầy đủ hơn:

~~~java
Throwable failure = event.getException();
log.error("Spring Boot không khởi động được", failure);
~~~

Nếu cần hiển thị loại lỗi:

~~~java
log.error("Startup failed; type=" +
        failure.getClass().getName(), failure);
~~~

Khi logger nhận trực tiếp đối tượng `Throwable`, thông tin exception chain thường được trình bày đầy đủ theo cấu hình logging.

### Lấy nguyên nhân sâu nhất để bổ sung chẩn đoán

Có thể đi qua chuỗi `getCause()`:

~~~java
static Throwable deepestCause(Throwable failure) {
    Throwable current = failure;

    while (current.getCause() != null &&
           current.getCause() != current) {
        current = current.getCause();
    }
    return current;
}
~~~

Sử dụng:

~~~java
Throwable failure = event.getException();
Throwable root = deepestCause(failure);

log.error("Startup failed; deepestCause=" +
        root.getClass().getSimpleName() +
        "; message=" + root.getMessage(), failure);
~~~

Đây là minh họa cho các chuỗi cause thông thường. Khi tự viết tiện ích tổng quát xử lý Throwable từ nguồn không kiểm soát, có thể cần phát hiện cả vòng tham chiếu phức tạp hơn giữa các cause.

**Không thay thế toàn bộ stack trace bằng root cause.** Lỗi ngoài cùng cũng quan trọng vì nó cho biết bean hoặc giai đoạn startup nào thất bại.

## 9. Các lỗi khởi động thường gặp và hướng điều tra

| Dấu hiệu trên log | Khả năng cần kiểm tra | Hướng tiếp cận |
|---|---|---|
| `UnsatisfiedDependencyException` | Không tìm thấy dependency phù hợp hoặc có nhiều ứng viên không phân giải được | Kiểm tra component scanning, `@Bean`, `@Qualifier`, `@Primary` và profile |
| `BeanCreationException` | Constructor, init method hoặc factory method thất bại | Xem `Caused by` và vị trí thực sự ném lỗi |
| `NoSuchBeanDefinitionException` | Thiếu bean mong đợi | Xem cấu hình đăng ký bean, conditional configuration và phạm vi scan |
| Lỗi bind `@ConfigurationProperties` | Giá trị cấu hình không khớp kiểu hoặc validation thất bại | Kiểm tra file cấu hình, tên property, định dạng và constraint |
| Thông báo cổng đang được sử dụng | Embedded web server không bind được port | Xem process chiếm cổng hoặc cấu hình `server.port` |
| Lỗi kết nối DB hay service ngoài | Endpoint, credential, DNS, kết nối hoặc migration có vấn đề | Xem exception gốc, kiểm tra kết nối và cấu hình môi trường |
| Lỗi trong `ApplicationRunner` | Tác vụ chuẩn bị dữ liệu hoặc kiểm tra startup thất bại | Đọc stack trace của runner, kiểm tra điều kiện đầu vào |
| Lỗi circular reference | Các bean phụ thuộc vòng nhau | Thiết kế lại dependency để phá vòng phụ thuộc |

Tên exception có thể khác nhau tùy lớp ném lỗi và phiên bản thư viện. Bảng chỉ hướng đọc log ban đầu; chẩn đoán cuối cùng phải dựa vào message, cause và cấu hình thực tế.

### Ví dụ: thiếu bean do component scanning

Giả sử `OrderService` yêu cầu `PaymentGateway` qua constructor, nhưng implementation nằm ngoài vùng component scan. Container có thể báo thiếu dependency trong lúc tạo service. Listener nhận `ApplicationFailedEvent` và ghi stack trace, nhưng bản thân listener không thể đăng ký bổ sung dependency để lần startup hiện tại tiếp tục.

Cách xử lý là sửa cấu hình scan hoặc đăng ký bean đúng cách, sau đó khởi động lại.

### Ví dụ: một runner kiểm tra dữ liệu bắt buộc

Một runner có thể kiểm tra schema hay tài nguyên cần thiết trước khi ứng dụng sẵn sàng. Khi điều kiện bắt buộc không đạt, runner ném exception để Spring Boot không công bố trạng thái ready. Listener giúp log nguyên nhân đầy đủ, còn logic runner chịu trách nhiệm đưa ra thông báo rõ ràng về dữ liệu hoặc điều kiện không hợp lệ.

## 10. Spring Boot đã có thông tin lỗi nào trước khi tự viết listener?

Spring Boot thường tự ghi log khi startup thất bại. Với những lỗi mà cơ chế **FailureAnalyzer** nhận diện được, output có thể có dạng:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:
    Mô tả điều kiện dẫn đến lỗi khởi động.

Action:
    Gợi ý cấu hình hoặc thao tác khắc phục.
~~~

Đây là dạng minh họa. Nội dung thực tế phụ thuộc loại exception và việc có `FailureAnalyzer` tương ứng hay không.

Các thành phần liên quan:

- **FailureAnalyzer:** nhận diện một số exception cụ thể và chuyển chúng thành `FailureAnalysis` dễ đọc.
- **FailureAnalysis:** chứa mô tả và hành động khắc phục nếu phân tích được.
- **FailureAnalysisReporter:** hiển thị hoặc báo cáo kết quả phân tích.

`ApplicationFailedEvent` và `FailureAnalyzer` giải quyết những việc khác nhau:

| Cơ chế | Mục đích chính |
|---|---|
| `ApplicationFailedEvent` | Cho listener biết startup đã thất bại và cung cấp Throwable/context nếu có |
| `FailureAnalyzer` | Chuyển một loại lỗi đã biết thành thông tin nguyên nhân và gợi ý sửa |
| Logging mặc định của Boot | Ghi nhận lỗi và những thông tin cần thiết khi startup thất bại |

Với ứng dụng thông thường, hãy **đọc log mặc định của Boot trước**. Chỉ thêm listener khi cần ghi thông tin đặc thù của hệ thống hoặc tích hợp với công cụ quan sát khác.

### Khi nào dùng --debug?

Có thể chạy ứng dụng với:

~~~bash
java -jar app.jar --debug
~~~

Trong các tình huống liên quan auto-configuration, chế độ debug giúp hiển thị thông tin chi tiết hơn, thường bao gồm **Condition Evaluation Report** để phân biệt những điều kiện cấu hình nào match hoặc không match.

`--debug` không có nghĩa mọi bean, mọi lệnh SQL hay mọi network request đều được tự động ghi chi tiết. Khi cần điều tra một package cụ thể, có thể cấu hình logging level tương ứng thay vì bật log rất rộng.

## 11. Thiết kế StartupFailureListener để không gây thêm lỗi

Listener xử lý lỗi startup chạy trong một thời điểm nhạy cảm: chính ứng dụng đang thất bại. Một listener phức tạp có thể tạo ra exception mới và làm log khó đọc hơn.

Nguyên tắc thiết kế:

1. **Ít dependency:** Ưu tiên đọc `event.getException()` và thông tin đơn giản của context.
2. **Không lấy bean nghiệp vụ:** Tránh gọi `context.getBean(...)`; context có thể chưa refresh hoặc đang thất bại.
3. **Không dựa vào web server:** HTTP endpoint, Actuator và service networking của ứng dụng có thể chưa hoạt động.
4. **Không che exception gốc:** Nếu tự thực hiện logging hoặc gửi thông báo, tránh để logic của listener ném lỗi mới.
5. **Không ghi bí mật:** Đối số startup, connection string, token, password và environment có thể chứa dữ liệu nhạy cảm.
6. **Giữ xử lý ngắn:** Không thực hiện công việc dài hoặc blocking làm chậm việc thất bại và thoát của process.

Một listener có tác vụ phụ dễ lỗi, ví dụ gửi thông báo qua kênh ngoài, có thể bảo vệ riêng tác vụ đó:

~~~java
@Override
public void onApplicationEvent(ApplicationFailedEvent event) {
    Throwable startupFailure = event.getException();

    log.error("Startup failed", startupFailure);

    try {
        notifyMonitoringWithoutSpringBeans(startupFailure);
    } catch (Exception notificationFailure) {
        log.warn("Không gửi được thông báo lỗi startup",
                notificationFailure);
    }
}
~~~

`notifyMonitoringWithoutSpringBeans(...)` là phương thức giả định do hệ thống tự xây dựng, không phải API của Spring. Nó phải hoạt động độc lập với bean ứng dụng. Ví dụ nhằm minh họa cách **giữ nguyên lỗi startup gốc** khi chức năng báo lỗi phụ thất bại.

Trong nhiều hệ thống, để log của process/container được agent giám sát bên ngoài thu thập sẽ đơn giản và đáng tin cậy hơn việc mở một kết nối mới ngay trong startup listener.

## 12. Lưu ý về logging và dữ liệu nhạy cảm

Trong giai đoạn sớm, logging có thể chưa hoàn toàn được cấu hình theo mong muốn. Lỗi xảy ra khi khởi tạo chính logging system cũng có thể hạn chế những gì một listener hoặc logger tự viết ghi lại được.

Ngoài ra, **exception message không phải lúc nào cũng an toàn để chuyển nguyên văn sang mọi nơi**. Ví dụ một thư viện có thể đưa URL chứa thông tin xác thực hoặc một phần nội dung kết nối vào message.

Nếu tích hợp với hệ thống giám sát:

- Ưu tiên loại lỗi, tên ứng dụng, môi trường, mốc thời gian và stack trace đã được kiểm soát truy cập.
- Hạn chế ghi toàn bộ `Environment` hoặc `event.getArgs()`.
- Không đưa password, API key hoặc secret vào message tự tạo trong runner.
- Phân biệt dữ liệu chẩn đoán nội bộ với thông tin có thể hiển thị cho người dùng cuối.

Bản thân `ApplicationFailedEvent` không tự áp dụng chính sách ẩn dữ liệu; ứng dụng chịu trách nhiệm đối với những gì listener ghi hoặc gửi đi.

## 13. Khi context tồn tại nhưng chưa usable

Xét các tình huống sau:

~~~text
A. Đọc cấu hình thất bại rất sớm
   getApplicationContext() -> có thể null

B. Đã tạo context, tạo bean thất bại
   getApplicationContext() -> có thể khác null
   nhưng refresh chưa hoàn tất

C. Context đã refresh, runner ném lỗi
   getApplicationContext() -> thường khác null
   nhưng startup sẽ thất bại và context có thể bị đóng
~~~

Không có cách kiểm tra `context != null` nào có thể bảo đảm rằng mọi bean đều sẵn sàng. Ngay cả `context.isActive()` cũng chỉ cho biết một trạng thái của context tại thời điểm kiểm tra; nó không chứng minh mọi dependency hoặc tác vụ startup đều thành công.

Vì vậy, phần lớn listener chỉ nên dùng context cho thông tin đơn giản như `getId()`, nếu có, và lấy chẩn đoán chính từ `getException()`.

Nếu cần xử lý trạng thái của các bean sau khi ứng dụng đã sẵn sàng, đó là một bài toán khác: có thể dùng `ApplicationReadyEvent`, event runtime, health indicator hoặc các cơ chế monitoring phù hợp.

## 14. ApplicationFailedEvent không thay thế cơ chế quản lý lỗi trong runner

Giả sử runner tải một tài nguyên từ dịch vụ bên ngoài. Không phải mọi lỗi đều cần làm ứng dụng thất bại.

Có hai hướng nghiệp vụ khác nhau:

**Lỗi bắt buộc:** Ứng dụng không thể hoạt động đúng khi dữ liệu cần thiết chưa có. Runner nên ném exception có nội dung rõ ràng. Boot chuyển sang luồng thất bại và listener có cơ hội nhận `ApplicationFailedEvent`.

**Lỗi có thể phục hồi:** Ứng dụng vẫn có thể khởi động với chức năng bị hạn chế hoặc retry sau. Runner có thể xử lý lỗi theo chính sách retry/fallback của hệ thống. Nếu exception không thoát ra ngoài và các bước startup khác thành công, riêng tình huống đó không tạo ra `ApplicationFailedEvent`.

Ví dụ minh họa quyết định bắt buộc:

~~~java
@Bean
ApplicationRunner verifyRequiredConfiguration(
        ApplicationSettings settings) {

    return args -> {
        if (!settings.hasRequiredEndpoint()) {
            throw new IllegalStateException(
                    "Thiếu endpoint bắt buộc để vận hành");
        }
    };
}
~~~

`ApplicationSettings` và `hasRequiredEndpoint()` là lớp/phương thức minh họa do ứng dụng định nghĩa.

Ở đây, **runner quyết định điều kiện thành công của bước startup**; `ApplicationFailedEvent` chỉ phản ánh kết quả khi điều kiện đó khiến startup thất bại. Không nên dùng failure listener để chạy lại tác vụ nghiệp vụ hay cố cứu một context đang được Spring Boot đóng sau thất bại.

## 15. Một quy trình điều tra lỗi startup thực tế

Khi ứng dụng Spring Boot không chạy được, có thể đi theo trình tự:

1. **Xác định lần chạy và thời điểm xảy ra lỗi:** lấy log của đúng process hoặc container.
2. **Tìm thông báo lỗi chính:** xem `APPLICATION FAILED TO START` nếu có và các dòng exception.
3. **Đọc chuỗi `Caused by`:** xác định lỗi gốc cùng bean hoặc runner liên quan.
4. **Xác định giai đoạn:** lỗi khi đọc config, refresh context, tạo server hay chạy runner.
5. **Kiểm tra cấu hình môi trường:** active profiles, giá trị cấu hình, biến môi trường, dependency thực tế.
6. **Dùng thông tin auto-configuration khi phù hợp:** thử `--debug` cho những lỗi điều kiện cấu hình khó giải thích.
7. **Sửa nguyên nhân và khởi động lại:** việc nhận event không tự khởi động lại process.

Ví dụ log đơn giản:

~~~text
INFO  ... Application context initialized
INFO  ... Starting startup runner
ERROR ... Startup failed
java.lang.IllegalStateException: Không thể chuẩn bị dữ liệu ban đầu
    at com.example.startup.StartupTaskConfiguration...
~~~

Nếu log này xuất phát từ runner đã mô tả, có thể suy ra lỗi xảy ra **sau giai đoạn refresh**, nhưng trước khi ứng dụng hoàn tất startup. Cần sửa công việc của runner hoặc điều kiện đầu vào của nó.

Trong một môi trường có orchestrator, quá trình restart process hay chính sách retry được quyết định ở tầng chạy ứng dụng. `ApplicationFailedEvent` chỉ là một nguồn tín hiệu ở trong Spring Boot; nó không tự thiết lập restart policy.

## 16. Thực hành: quan sát sự kiện qua ba kiểu lỗi

Có thể dùng một project Spring Boot tối giản để làm ba thí nghiệm. Giữ nguyên listener đã đăng ký bằng `application.addListeners(...)`, rồi tạo từng lỗi trong môi trường phát triển.

### Thí nghiệm 1: lỗi từ ApplicationRunner

Thêm `StartupTaskConfiguration` ở mục 6, khởi động ứng dụng và quan sát thông báo exception từ listener. Sau đó bỏ exception trong runner, chạy lại và xem ứng dụng hoàn tất startup.

Điều cần nhận ra: nếu runner ném exception, ứng dụng không đạt mốc ready thành công.

### Thí nghiệm 2: lỗi khi tạo bean

Tạo một bean mẫu:

~~~java
@Configuration(proxyBeanMethods = false)
public class BrokenBeanConfiguration {

    @Bean
    SampleStartupResource sampleStartupResource() {
        throw new IllegalStateException(
                "Không tạo được tài nguyên khi khởi động");
    }
}
~~~

`SampleStartupResource` là kiểu giả định do bạn tự khai báo khi thực hành. Có thể thay bằng một class rỗng đơn giản.

Lỗi này phát sinh trong lúc Spring tạo singleton, trước khi chạy runners. Listener vẫn nhận lỗi startup nếu nó nằm trong luồng xử lý lỗi của `SpringApplication`.

### Thí nghiệm 3: lỗi cấu hình sớm

Thử cung cấp một giá trị cấu hình không hợp lệ cho một thành phần có binding/validation trong project. Quan sát xem context tại thời điểm failure listener chạy có tồn tại hay không. Tùy loại cấu hình và thời điểm phân tích, context có thể chưa có hoặc đã được tạo một phần.

**Không giả định rằng mọi lỗi cấu hình đều làm `getApplicationContext()` trả về `null`.** Điều này phụ thuộc vào giai đoạn phát hiện lỗi.

### Những gì cần tự ghi nhận

| Câu hỏi quan sát | Runner failure | Bean creation failure | Configuration failure |
|---|---|---|---|
| Exception gốc là gì? | Exception từ runner | Exception trong bean/factory method | Exception đọc/bind/validate cấu hình |
| `ApplicationStartedEvent` có thể đã phát? | Thường có | Thường chưa | Tùy giai đoạn, thường chưa |
| Context luôn khác `null`? | Không nên dựa vào như một cam kết chung | Có thể tồn tại nhưng chưa usable | Có thể có hoặc không |
| `ApplicationReadyEvent` thành công? | Không | Không | Không |

Thí nghiệm giúp thấy rằng thời điểm lỗi quyết định những đối tượng nào đã tồn tại, trong khi listener đã đăng ký sớm vẫn có cơ hội ghi nhận `ApplicationFailedEvent`.

## 17. Những nhầm lẫn thường gặp

**“Có ApplicationFailedEvent là context đã được tạo.”** Sai. `getApplicationContext()` có thể là `null`.

**“Chỉ cần thêm @EventListener vào một service là chắc chắn bắt được lỗi startup.”** Không bảo đảm, vì service hoặc cơ chế đăng ký event method có thể chưa khởi tạo trước lúc thất bại.

**“ApplicationStartedEvent nghĩa là ứng dụng ready.”** Không. Runners còn chạy sau sự kiện started.

**“Nếu ApplicationRunner ném lỗi, ApplicationReadyEvent vẫn chạy.”** Với lỗi không được xử lý làm `run()` thất bại, ứng dụng không đi tới mốc ready thành công.

**“Lấy getException().getMessage() là đủ để debug.”** Thường không đủ. Cần stack trace và chuỗi cause.

**“Listener có thể cứu startup bằng cách sửa bean lỗi.”** Failure listener nhận sự kiện khi Spring Boot đang xử lý việc startup thất bại; sửa lỗi cấu hình cần thực hiện ở nguồn rồi khởi động lại.

**“Cứ context khác null thì gọi getBean() được.”** Không an toàn. Context có thể đang refresh dang dở hoặc chuẩn bị đóng.

**“ApplicationFailedEvent sẽ xuất hiện cho mọi crash của JVM.”** Không. Nó phục vụ các lỗi startup mà cơ chế của `SpringApplication` xử lý được.

## Kết luận

`ApplicationFailedEvent` cho phép quan sát một lần khởi động Spring Boot thất bại. Hai thông tin quan trọng nhất là **`getException()`**, dùng để đọc đầy đủ exception chain, và **`getApplicationContext()`**, có thể trả về `null` hoặc một context chưa sẵn sàng.

Để nhận lỗi sớm, có thể triển khai `ApplicationListener<ApplicationFailedEvent>` và đăng ký trực tiếp bằng `SpringApplication.addListeners(...)` trước khi gọi `run(...)`. Giữ listener đơn giản, độc lập với bean nghiệp vụ, ghi stack trace và tránh làm phát sinh lỗi mới trong đường xử lý thất bại.

Trong chủ đề **Sự kiện và runner**, hãy nhớ: `ApplicationStartedEvent` xảy ra trước các runner, `ApplicationReadyEvent` đánh dấu startup đã hoàn tất thành công, còn một exception từ `ApplicationRunner` hoặc `CommandLineRunner` có thể đưa ứng dụng sang `ApplicationFailedEvent`. Khi điều tra, ưu tiên log mặc định của Spring Boot, exception gốc và thông tin cấu hình liên quan, sau đó sửa nguyên nhân khiến startup không hoàn tất.
