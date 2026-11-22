# ConfigurableApplicationContext.close và SpringApplicationShutdownHook

Một ứng dụng Spring Boot không chỉ cần **khởi động đúng** mà còn phải **dừng đúng**. Khi kết thúc, container cần thông báo cho các thành phần đang chạy ngừng nhận việc mới, cho những công việc phù hợp thời gian hoàn tất, gọi callback hủy bean và giải phóng kết nối/tài nguyên. Hai tên thường xuất hiện khi đọc mã nguồn là:

- **`ConfigurableApplicationContext.close()`**: lời gọi **tường minh** để đóng một Spring `ApplicationContext` đang hoạt động.
- **`SpringApplicationShutdownHook`**: cơ chế nội bộ mà **Spring Boot** dùng để đăng ký với **JVM shutdown** và đóng những application context đã đăng ký khi tiến trình đi tới bước shutdown.

Hai cơ chế có liên quan nhưng **không phải một**. `close()` không cần đợi JVM thoát; JVM shutdown hook không phải một lệnh mà ứng dụng cần gọi mỗi lần đóng context. Phân biệt chúng giúp tránh các lỗi khó tìm: “đã đóng context nhưng Java process còn chạy”, “tại sao `@PreDestroy` được gọi khi nhấn Ctrl+C?”, “vì sao thêm shutdown hook mà callback chạy không đúng thứ tự?”, hoặc “`SpringApplication.exit` có tự kết thúc JVM không?”.

Bài học sử dụng **Spring Boot 3.3.x / Spring Framework 6.1 / Java 17+**, tập trung vào **dừng ứng dụng**, không đi sâu vào toàn bộ quá trình startup. Có ví dụ Gradle/Java chạy được, hai chế độ quan sát **manual close** và **JVM shutdown**, phương án sử dụng shutdown handlers, thứ tự sự kiện, graceful HTTP shutdown, kiểm thử và xử lý lỗi.

## 1. Bốn khái niệm thường bị gộp nhầm

| Khái niệm | Thuộc cấp nào? | Mục đích |
| --- | --- | --- |
| `ConfigurableApplicationContext.close()` | Spring Framework container | Đóng một context, dừng lifecycle beans, hủy singleton do context quản lý |
| `SpringApplicationShutdownHook` | Nội bộ Spring Boot | Phối hợp việc đóng các context đã đăng ký khi JVM shutdown |
| `Runtime.getRuntime().addShutdownHook(...)` | Java/JVM | Đăng ký một thread chạy trong quá trình JVM shutdown thông thường |
| `System.exit(status)` | Java/JVM | Yêu cầu **tiến trình JVM** thoát với exit status; kích hoạt shutdown sequence |

Ví dụ:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

// Đóng context nhưng không trực tiếp yêu cầu JVM kết thúc:
context.close();
~~~

Đoạn trên là minh họa trong phương thức có `MyApplication` và các import tương ứng. **`context.close()` không gọi `System.exit(...)`**. Nếu tiến trình còn non-daemon threads hoặc các tài nguyên nằm ngoài context, JVM có thể tiếp tục sống. Nếu không còn non-daemon thread nào, JVM có thể kết thúc sau khi `main` trả về.

Ngược lại, nếu dùng:

~~~java
System.exit(0);
~~~

JVM bắt đầu shutdown; nếu Spring Boot đã đăng ký shutdown hook theo mặc định, hook có thể gọi `close()` lên context còn hoạt động. **`System.exit` không phải API đóng Spring bean trực tiếp**: nó là yêu cầu kết thúc JVM, và việc dọn dẹp Spring diễn ra thông qua hook.

## 2. Bản đồ tổng quan: hai con đường dẫn tới đóng context

~~~text
                     SPRING APPLICATION ĐANG CHẠY
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
       Mã ứng dụng gọi close()       JVM bắt đầu shutdown
                    |                 (System.exit, SIGTERM,
                    |                  Ctrl+C phù hợp, ...)
                    |                           |
                    |                           v
                    |              SpringApplicationShutdownHook
                    |                  duyệt các context đăng ký
                    |                           |
                    +------------+--------------+
                                 |
                                 v
                 ConfigurableApplicationContext.close()
                                 |
                                 v
                       AbstractApplicationContext
                          thực hiện doClose()
                                 |
                   +-------------+-------------+
                   |             |             |
                   v             v             v
             ContextClosed   Lifecycle      destroy các
                 Event     Processor.stop    singleton
                   |             |             |
                   +-------------+-------------+
                                 |
                                 v
                          context inactive
                                 |
               +-----------------+--------------------+
               |                                      |
               v                                      v
     Nếu chỉ gọi close()                     Nếu JVM shutdown:
     mã Java có thể chạy tiếp                JVM tiếp tục thoát;
                                              Boot shutdown handlers
                                              có thể được gọi sau
                                              khi context đóng
~~~

Sơ đồ gộp hai đường vào **một cơ chế đóng context** để dễ học; thứ tự chi tiết chính xác là **`ContextClosedEvent` → `LifecycleProcessor.onClose()` → hủy singleton → đóng bean factory** trong đường close bình thường của `AbstractApplicationContext`. Các callback thất bại hoặc một context tùy biến có thể khiến quan sát thực tế phức tạp hơn.

Câu cần nhớ:

> **Hook là tác nhân kích hoạt đóng context khi JVM chuẩn bị thoát; `close()` là thao tác đóng context.** Không nên dùng hai tên này như hai phương án có tác động hoàn toàn độc lập.

## 3. `ConfigurableApplicationContext.close()` làm gì?

`ConfigurableApplicationContext` là giao diện cho context có thể cấu hình, mở rộng các khả năng của `ApplicationContext` và hỗ trợ đóng. `SpringApplication.run(...)` trả về một `ConfigurableApplicationContext` trên đường khởi động thành công.

Một ví dụ quen thuộc:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

try {
    // Sử dụng các bean, thực hiện công việc.
} finally {
    context.close();
}
~~~

Với ứng dụng CLI hoặc một thành phần tự quản lý vòng đời, mẫu `try/finally` giúp giải phóng context khi tác vụ xong hoặc xảy ra lỗi. Có thể dùng `try-with-resources` vì `ConfigurableApplicationContext` là `AutoCloseable`:

~~~java
try (ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args)) {
    // Dùng context trong phạm vi này.
}
// context.close() đã được gọi khi thoát khối.
~~~

**Không đặt `try-with-resources` quanh một web server dự kiến chạy mãi**, nếu mã `main` lập tức thoát khỏi khối: context sẽ bị đóng ngay và server dừng. Với web app chạy lâu dài, thông thường để Spring Boot/JVM shutdown hook điều phối khi có tín hiệu dừng.

### Thứ tự đóng của `AbstractApplicationContext`

Ở Spring Framework 6.1, đường bình thường có thể hiểu như sau:

~~~text
context.close()
   |
   +-- Đánh dấu/điều phối quá trình đóng
   |
   +-- publishEvent(new ContextClosedEvent(context))
   |
   +-- lifecycleProcessor.onClose()
   |      Dừng các bean Lifecycle / SmartLifecycle đang chạy
   |      Theo phase và quan hệ phụ thuộc
   |
   +-- destroyBeans()
   |      @PreDestroy, DisposableBean.destroy(),
   |      destroyMethod trên các singleton thích hợp
   |
   +-- closeBeanFactory()
   |
   +-- Các bước đóng context còn lại
   |
   v
context.isActive() == false
~~~

**`ContextClosedEvent` xuất hiện trước khi các bean lifecycle hoàn tất stop và trước các callback destroy thông thường.** Listener nhận event đó không nên giả định “mọi kết nối đã đóng”. Nó là **tín hiệu quá trình đóng context đã bắt đầu**, không phải một sự kiện cam kết toàn bộ dọn dẹp hoàn tất.

Các bước tương ứng nằm trong `org.springframework.context.support.AbstractApplicationContext`; context subclass có thể có thêm xử lý riêng. Nếu trong một callback có ngoại lệ, Spring có cơ chế ghi log và tiếp tục các bước phù hợp, nhưng **đừng dựa vào khả năng phục hồi khỏi mọi loại lỗi nghiêm trọng** như `OutOfMemoryError` hay tiến trình bị kill cưỡng bức.

### `close()` không hủy mọi object Java

Spring chỉ biết các bean và tài nguyên mà context quản lý qua hợp đồng scope/lifecycle. Object tạo bằng `new` bên ngoài context, `ExecutorService` không được đăng ký làm bean, thread chạy nền tự tạo hoặc tài nguyên của thư viện không tích hợp lifecycle **không tự động được hủy chỉ vì gọi `close()`**.

Ví dụ sai:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(4);
context.close();
// executor chưa được Spring quản lý -> vẫn có thể giữ non-daemon threads.
~~~

Đoạn trên là fragment, cần import `ExecutorService` và `Executors` cùng biến `context` hợp lệ. Phải gọi `executor.shutdown()` hoặc thiết kế bean với destroy method thích hợp.

## 4. `SpringApplicationShutdownHook` là gì?

Trong Spring Boot 3.3, `org.springframework.boot.SpringApplicationShutdownHook` là **lớp triển khai nội bộ ở package `org.springframework.boot`**, không phải một extension point công khai mà mã nghiệp vụ nên tự tạo hoặc gọi trực tiếp.

Mã nguồn `SpringApplication` 3.3.13 có một shutdown hook dùng chung để quản lý các context được đăng ký. Theo hợp đồng cấu hình, **`SpringApplication.setRegisterShutdownHook(true)` là mặc định**. Khi chạy:

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.run(args);
~~~

Spring Boot sẽ đăng ký context được tạo với cơ chế shutdown hook nếu không tắt tính năng này. Khi JVM bắt đầu quá trình shutdown bình thường, hook đóng các context đăng ký còn hoạt động.

Ở mức ý tưởng:

~~~text
SpringApplication.run(...)
   |
   +-- registerShutdownHook = true (mặc định)
   |
   +-- tạo ApplicationContext
   |
   +-- đăng ký context với SpringApplicationShutdownHook
   |
   +-- refresh và tiếp tục startup
   |
   v
ApplicationContext hoạt động
   |
   ... thời gian chạy ứng dụng ...
   |
   v
JVM shutdown
   |
   +-- Thread của Boot shutdown hook chạy
   |
   +-- close() các context được quản lý chưa đóng
   |
   +-- chờ context thành inactive khi cần
   |
   +-- chạy các SpringApplicationShutdownHandlers đã đăng ký
   v
JVM tiếp tục kết thúc
~~~

Trong triển khai 3.3, hook còn theo dõi context đã phát `ContextClosedEvent` để tránh việc bối cảnh đóng song song bị bỏ quên. Đây là **chi tiết triển khai để hiểu code**, không phải API để ứng dụng tự can thiệp vào danh sách context nội bộ.

**Đừng nhầm `SpringApplicationShutdownHook` với `ConfigurableApplicationContext.registerShutdownHook()`.** Phương thức thứ hai là API của **Spring Framework**, có thể đăng ký JVM hook của riêng một context. Spring Boot có cơ chế phối hợp shutdown ở cấp `SpringApplication`; trong ứng dụng Boot thông thường không cần tự gọi thêm `context.registerShutdownHook()`.

## 5. Mặc định đã có hook; khi nào nên cấu hình?

Spring Boot cho phép:

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.setRegisterShutdownHook(false);
ConfigurableApplicationContext context = application.run(args);
~~~

Đây là fragment nằm trong phương thức có class `MyApplication` phù hợp. Khi tắt đăng ký hook, **ứng dụng phải chủ động quản lý việc đóng context** trên các đường kết thúc mà nó chịu trách nhiệm. Không đặt `false` chỉ để “tăng tốc shutdown”; làm vậy có thể khiến `@PreDestroy` và các callback lifecycle không được gọi khi JVM thoát.

Cấu hình ngoài tương ứng:

~~~properties
spring.main.register-shutdown-hook=false
~~~

Đây là lựa chọn có thể được dùng trong những kiến trúc **nhúng Spring Boot vào một host quản lý vòng đời riêng**, một số chương trình kiểm thử đặc biệt hoặc tình huống phải phối hợp shutdown với phần mềm bên ngoài. Trong phần lớn ứng dụng Boot chạy như một tiến trình độc lập, **giữ mặc định `true`**.

### Các trường hợp dễ nhầm

- Gọi `context.close()` thủ công **không yêu cầu** tắt shutdown hook. Khi context đã đóng, hook biết trạng thái để không cần hủy bean một lần nữa trên luồng bình thường.
- Tắt hook **không ngăn** việc gọi `context.close()`: bạn vẫn có thể đóng context tường minh.
- Tắt hook **không làm JVM sống lâu hơn** nếu không còn non-daemon threads. Số luồng đang chạy và vòng đời JVM là vấn đề khác.
- Nếu ứng dụng có nhiều `ApplicationContext`, cần hiểu ai tạo/đăng ký/đóng từng context; đừng giả định đóng một context sẽ tự đóng mọi context độc lập.
- `spring.main.register-shutdown-hook` là thiết lập của `SpringApplication`, không phải cờ chung tác động đến mọi hook mà Java hoặc thư viện khác đã đăng ký.

## 6. Điều gì xảy ra khi JVM shutdown?

JVM bắt đầu shutdown trong một số trường hợp thường gặp:

- `System.exit(status)`.
- Người dùng gửi tín hiệu dừng bình thường, ví dụ `SIGTERM` trên Unix/Linux, và JVM có thể chạy shutdown hooks.
- Người dùng nhấn `Ctrl+C` khi tiến trình chạy foreground trong terminal thích hợp.
- JVM tự đi tới shutdown khi **không còn non-daemon threads** (lúc ứng dụng console kết thúc).

Khi JVM đi vào shutdown sequence, những hook đã đăng ký bằng `Runtime.addShutdownHook(Thread)` được chạy. Spring Boot đăng ký hook của mình để yêu cầu đóng context. Tuy nhiên, không phải mọi cách dừng đều chạy hook:

| Cách dừng | Thường chạy JVM shutdown hooks? | Điểm cần lưu ý |
| --- | --- | --- |
| `context.close()` | **Không tự bắt đầu JVM shutdown** | Có thể tiếp tục dùng JVM sau khi đóng context |
| `System.exit(0)` | Có, trên đường shutdown bình thường | Chạy hooks rồi JVM kết thúc |
| `SIGTERM`/`kill -TERM` | Thông thường có trên HotSpot/OpenJDK | Phụ thuộc hệ điều hành, cách tiến trình nhận tín hiệu |
| `Ctrl+C` foreground | Thông thường có | IDE/terminal có thể dừng theo cách khác |
| `kill -9`/`SIGKILL` | **Không** | OS cưỡng bức kết thúc tiến trình |
| `Runtime.getRuntime().halt(...)` | **Không** | Bỏ qua shutdown hooks; dùng cực kỳ thận trọng |
| Mất điện, container bị cưỡng bức dừng | Không được bảo đảm | Có thể không chạy bất kỳ callback Java nào |

**Lưu ý vận hành:** “chạy hook” không đồng nghĩa mọi công việc cleanup **chắc chắn hoàn thành**. Container orchestration có hạn chót dừng; nếu quá hạn, tiến trình có thể bị kill. Dừng bình thường cũng cần thiết kế timeout, giới hạn blocking, idempotence và khả năng phục hồi sau sự cố.

### Không tự gọi `Thread.run()` của một hook

Một JVM shutdown hook là thread được JVM gọi vào thời điểm shutdown. Bạn không nên giữ reference rồi gọi `run()` thủ công để “giả lập JVM shutdown”; hành động đó chỉ thực thi `Runnable` trên luồng hiện tại, không tái tạo hợp đồng hoặc trạng thái shutdown của JVM.

Muốn chủ động đóng context trong mã, hãy gọi **`context.close()`**.

## 7. Thứ tự `ContextClosedEvent`, `SmartLifecycle` và destroy callback

Ba cơ chế này thường xuất hiện trong cùng một log shutdown:

### `ContextClosedEvent`

Được phát **khi context bắt đầu đóng**, trước pha dừng lifecycle trong `AbstractApplicationContext` thông thường.

~~~java
@EventListener
public void onClose(ContextClosedEvent event) {
    System.out.println("EVENT ContextClosedEvent");
}
~~~

Đây là một method ví dụ trong bean Spring, cần import `@EventListener` và `ContextClosedEvent`.

### `LifecycleProcessor.onClose()`

Spring dừng những bean `Lifecycle`/`SmartLifecycle` đang running thông qua `LifecycleProcessor`. Với `SmartLifecycle`, method `stop(Runnable callback)` cho phép báo đã dừng thực sự.

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stop();
    } finally {
        callback.run();
    }
}
~~~

Đây là fragment trong class triển khai `SmartLifecycle`. Với dừng **bất đồng bộ**, chỉ gọi callback sau khi xử lý đang chạy đã hoàn tất theo hợp đồng. Quên callback có thể khiến bộ điều phối chờ tới timeout của phase.

Thứ tự stop thường đi từ **phase cao xuống phase thấp** (đối nghịch start từ thấp lên cao), đồng thời xét quan hệ phụ thuộc. Không nên gán mức `phase` ngẫu nhiên: nếu consumer đang dùng một kết nối, thường cần dừng consumer nhận việc trước rồi mới đóng kết nối mà nó cần.

### `@PreDestroy`, `DisposableBean.destroy()`, destroy method

Sau bước stop lifecycle thông thường, context tiến hành hủy các singleton được nó quản lý:

~~~java
@PreDestroy
public void preDestroy() {
    System.out.println("DESTROY @PreDestroy");
}
~~~

Hoặc cấu hình:

~~~java
@Bean(destroyMethod = "cleanup")
ExternalResource resource() {
    return new ExternalResource();
}
~~~

Những đoạn trên là fragments, cần class và import phù hợp; ví dụ đầy đủ ở phần 9. **Stop không đồng nghĩa destroy**: một bean có thể ngừng chạy trước khi được hủy, và callback hủy không phải nơi lý tưởng để thực hiện một vòng chờ vô hạn.

### Chuỗi đúng để nhớ

~~~text
close() bắt đầu
   -> ContextClosedEvent
   -> LifecycleProcessor.onClose()
        -> SmartLifecycle.stop(callback)
   -> destroyBeans()
        -> @PreDestroy
        -> DisposableBean.destroy() nếu có
        -> destroy method cấu hình
   -> đóng BeanFactory/context
   -> isActive() == false
~~~

Với một bean dùng nhiều cơ chế hủy, Spring định nghĩa thứ tự giữa chúng. Đoạn trên là hướng dẫn đường bình thường, không cam kết mọi bean có đủ cả ba callback.

## 8. `SpringApplicationShutdownHandlers` khác `SpringApplicationShutdownHook` thế nào?

`SpringApplicationShutdownHook` là **lớp điều phối nội bộ**, còn `SpringApplicationShutdownHandlers` là **giao diện công khai** để người dùng Spring Boot đăng ký các hành động chạy trong quá trình JVM shutdown:

~~~java
SpringApplication.getShutdownHandlers().add(() -> {
    System.out.println("BOOT shutdown handler");
});
~~~

Trong Spring Boot 3.3, những handler được đăng ký qua `SpringApplication.getShutdownHandlers()`:

- Chạy **khi JVM shutdown**, **không phải ngay sau một lời gọi `context.close()`** trong JVM vẫn đang hoạt động.
- Được Boot điều phối **tuần tự** thay vì để các hook JVM độc lập chạy theo thứ tự không xác định.
- Theo hợp đồng API, được gọi **sau khi các `ApplicationContext` đã đăng ký được đóng và không còn active**.
- Thích hợp với công việc **sau khi Spring context đóng**, không thích hợp nếu hành động còn đòi inject/tra cứu các bean đang hoạt động.

Một tình huống thực tế: cần ghi marker cuối cùng vào một cơ chế logging độc lập với Spring bean để biết JVM đã qua bước đóng context. Tuy nhiên, callback không nên phụ thuộc một `DataSource` hoặc bean logger đã bị destroy.

Muốn huỷ đăng ký:

~~~java
Runnable action = () -> System.out.println("late cleanup");
SpringApplication.getShutdownHandlers().add(action);

// Ở vị trí khác, trước JVM shutdown:
SpringApplication.getShutdownHandlers().remove(action);
~~~

Hai đoạn là **minh họa cùng một instance `Runnable`**. Cần dùng cùng object nếu muốn remove; đừng trông chờ hai lambda có cùng nội dung là cùng identity.

### Cần phân biệt hai loại callback

| Hành động | `ContextClosedEvent` listener | `SpringApplicationShutdownHandlers` |
| --- | --- | --- |
| Kích hoạt khi mã gọi `context.close()` | Có | Không chỉ vì close |
| Kích hoạt khi JVM shutdown và context được hook đóng | Có | Có nếu hook được đăng ký/chạy |
| Thời điểm so với destroy bean | **Trước** stop/destroy | **Sau** các context được đăng ký đóng |
| Có nên gọi bean Spring đang hoạt động? | Cẩn trọng: shutdown đã bắt đầu | **Không giả định bean còn tồn tại** |
| Cần Spring-managed bean listener? | Thường có thể là bean | Không bắt buộc |
| Phù hợp | Dừng nhận việc, ghi nhận mốc bắt đầu đóng | Tác vụ nhỏ cuối cùng độc lập context |

**Không dựa vào thứ tự giữa các `Runtime.addShutdownHook(...)` tùy ý**. JVM có thể chạy những hook khác nhau **đồng thời**, không có thứ tự được bảo đảm. Nếu thật sự cần “sau khi Spring context đóng”, dùng hợp đồng `SpringApplicationShutdownHandlers` thay vì một hook JVM ngẫu nhiên.

## 9. Ví dụ chạy được: so sánh `close()` và JVM shutdown

Ta tạo một **Spring Boot CLI không mở web server** để stdout dễ quan sát. Demo có:

- Bean `SmartLifecycle` in mốc `start`/`stop`.
- `ApplicationRunner` xác nhận ứng dụng đã đi qua khởi động.
- Listener `ContextClosedEvent` in khi quá trình đóng context bắt đầu.
- Bean `DemoResource` có `@PreDestroy` và `destroyMethod`.
- Một `SpringApplicationShutdownHandlers` in kết quả kiểm tra `context.isActive()` **khi JVM shutdown**.
- Hai chế độ `--demo.mode=manual` và `--demo.mode=exit`.

Trong ứng dụng production, **không gọi `System.exit` trực tiếp từ HTTP controller**. Nhánh `exit` của demo chỉ chạy khi bạn chủ động yêu cầu trong tiến trình thử nghiệm cục bộ.

### 9.1. Cấu trúc dự án

~~~text
shutdown-hook-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/shutdown/
    └── ShutdownDemoApplication.java
~~~

### 9.2. `settings.gradle`

~~~groovy
rootProject.name = 'shutdown-hook-demo'
~~~

### 9.3. `build.gradle`

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
    // BOM giải quyết phiên bản các module Spring Boot/Jakarta.
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'jakarta.annotation:jakarta.annotation-api'
}
~~~

Plugin Spring Boot được ghép với **Gradle native BOM**, vì `spring-boot-starter` không có version tường minh. JDK 17 trở lên và Gradle tương thích Spring Boot 3.3 được yêu cầu.

### 9.4. `ShutdownDemoApplication.java`

~~~java
package com.example.shutdown;

import java.util.Arrays;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class ShutdownDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ShutdownDemoApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        // Không tắt registerShutdownHook (mặc định true).
        ConfigurableApplicationContext context = application.run(args);

        SpringApplication.getShutdownHandlers().add(() ->
                System.out.println("BOOT_HANDLER active=" + context.isActive()));

        System.out.println("MAIN active=" + context.isActive());

        boolean exitMode = Arrays.asList(args).contains("--demo.mode=exit");
        if (exitMode) {
            System.out.println("MAIN request System.exit");
            System.exit(0);
        }

        System.out.println("MAIN explicit close");
        context.close();
        System.out.println("MAIN after close active=" + context.isActive());
    }

    @Bean
    SmartLifecycle demoWorker() {
        return new DemoWorker();
    }

    @Bean(destroyMethod = "cleanup")
    DemoResource demoResource() {
        return new DemoResource();
    }

    @Bean
    ApplicationRunner showRunner() {
        return args -> System.out.println("RUNNER");
    }

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        System.out.println("EVENT ContextClosedEvent");
    }

    static final class DemoWorker implements SmartLifecycle {
        private volatile boolean running;

        @Override
        public void start() {
            if (!running) {
                running = true;
                System.out.println("WORKER start");
            }
        }

        @Override
        public void stop() {
            if (running) {
                running = false;
                System.out.println("WORKER stop");
            }
        }

        @Override
        public void stop(Runnable callback) {
            try {
                stop();
            } finally {
                callback.run();
            }
        }

        @Override
        public boolean isRunning() {
            return running;
        }

        @Override
        public boolean isAutoStartup() {
            return true;
        }

        @Override
        public int getPhase() {
            return 0;
        }
    }

    static final class DemoResource {
        @PreDestroy
        public void beforeDestroy() {
            System.out.println("RESOURCE @PreDestroy");
        }

        public void cleanup() {
            System.out.println("RESOURCE cleanup");
        }
    }
}
~~~

Trong demo, `DemoWorker` auto-start ở cuối quá trình refresh context vì triển khai `SmartLifecycle` với `isAutoStartup() == true`. `ApplicationRunner` chạy sau refresh. Bean `DemoResource` không làm việc nền; nó tồn tại để quan sát giai đoạn destroy.

Chương trình chỉ có một context, một worker và một resource để kết quả ổn định. Trong ứng dụng thực tế có nhiều `SmartLifecycle`, mốc `stop` có thể bị chia theo phase và phụ thuộc.

### 9.5. Chạy chế độ manual close

Nếu có Gradle Wrapper:

~~~bash
./gradlew bootRun --args="--demo.mode=manual"
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--demo.mode=manual"
~~~

Hoặc với Gradle đã cài (khi chưa có wrapper):

~~~bash
gradle bootRun --args="--demo.mode=manual"
~~~

Các dòng **do `System.out.println` của chương trình in ra** trên đường chạy thành công, theo thứ tự:

~~~text
WORKER start
RUNNER
MAIN active=true
MAIN explicit close
EVENT ContextClosedEvent
WORKER stop
RESOURCE @PreDestroy
RESOURCE cleanup
MAIN after close active=false
BOOT_HANDLER active=false
~~~

Có thể có thêm log Spring Boot và output của Gradle. Dòng `BOOT_HANDLER active=false` xảy ra **lúc JVM shutdown sau khi `main` kết thúc**, không phải do `context.close()` trực tiếp gọi handler.

Điểm rút ra:

1. `context.close()` được gọi từ code `main`.
2. Listener nhận `ContextClosedEvent` trước khi worker stop.
3. Worker stop trước giai đoạn hủy resource.
4. `@PreDestroy` chạy trước phương thức destroy `cleanup` được cấu hình.
5. Sau `close()`, `context.isActive()` là `false`.
6. **Mặc dù context đã đóng**, handler được đăng ký với Spring Boot có thể vẫn được gọi về sau khi JVM tiến tới shutdown.

### 9.6. Chạy chế độ JVM shutdown

Chạy lại từ **một JVM mới**:

~~~bash
./gradlew bootRun --args="--demo.mode=exit"
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun --args="--demo.mode=exit"
~~~

Các dòng do mã demo in trong đường bình thường:

~~~text
WORKER start
RUNNER
MAIN active=true
MAIN request System.exit
EVENT ContextClosedEvent
WORKER stop
RESOURCE @PreDestroy
RESOURCE cleanup
BOOT_HANDLER active=false
~~~

**Không có dòng `MAIN after close active=false`** trong nhánh này vì `System.exit(0)` yêu cầu JVM kết thúc, thay vì quay lại tiếp tục thực thi dòng mã ở cuối `main`. JVM gọi Spring Boot shutdown hook; hook yêu cầu đóng context và sau đó handler được gọi.

Hai lượt cho thấy **cùng một chuỗi dọn dẹp Spring**, nhưng tác nhân kích hoạt khác nhau:

- Nhánh manual: code gọi `context.close()`.
- Nhánh exit: JVM shutdown kích hoạt `SpringApplicationShutdownHook` và hook gọi `close()`.

**Đừng dùng `System.exit` trong test runner, IDE chung hoặc server production chỉ để “xem log”:** nó kết thúc cả JVM, có thể ảnh hưởng mọi ứng dụng/chương trình khác trong tiến trình. Demo chỉ nên chạy như executable độc lập.

### 9.7. Chạy bằng JAR

Build:

~~~bash
./gradlew clean bootJar
~~~

Sau khi build thành công, với project trên tên JAR thường là:

~~~text
build/libs/shutdown-hook-demo-1.0.0.jar
~~~

Chạy:

~~~bash
java -jar build/libs/shutdown-hook-demo-1.0.0.jar --demo.mode=manual
java -jar build/libs/shutdown-hook-demo-1.0.0.jar --demo.mode=exit
~~~

Hai lệnh tạo **hai lần chạy JVM riêng biệt**, không gọi đồng thời trong cùng tiến trình. Kiểm tra tên JAR thực tế nếu bạn đã thay cấu hình artifact.

## 10. Dùng `SpringApplication.exit(context)` đúng chỗ

Spring Boot có API:

~~~java
int exitCode = SpringApplication.exit(context);
~~~

Ý nghĩa chính:

- Kích hoạt **đóng context** cùng logic exit-code liên quan của Spring Boot.
- Có thể tập hợp giá trị từ những `ExitCodeGenerator` thích hợp.
- **Trả về một `int`**, không tự bảo đảm JVM kết thúc chỉ vì method trả về.

Nếu ứng dụng CLI muốn kết thúc tiến trình với mã trạng thái cụ thể:

~~~java
int exitCode = SpringApplication.exit(context);
System.exit(exitCode);
~~~

Đây là **fragment thay thế** cách manual close ở `main`, không nên nối với `context.close()` một cách thừa hoặc gọi lặp để “đóng kỹ hơn”.

Một bean có thể triển khai `ExitCodeGenerator`:

~~~java
@Bean
ExitCodeGenerator exitCodeGenerator() {
    return () -> 7;
}
~~~

Đây là fragment trong class cấu hình Spring, cần import `org.springframework.boot.ExitCodeGenerator`. Giá trị `7` chỉ là ví dụ. Khi code gọi `SpringApplication.exit(context)`, Spring Boot có thể dùng các generator này để xác định exit code. **Gọi `context.close()` trực tiếp không tự tính/đưa exit code đó ra hệ điều hành.**

Phân biệt:

| Phương án | Đóng context? | JVM chắc chắn kết thúc ngay? | Mã trả về |
| --- | --- | --- | --- |
| `context.close()` | Có | Không | `void` |
| `SpringApplication.exit(context)` | Có | Không tự động | `int` |
| `System.exit(code)` | Gián tiếp qua hook nếu đã đăng ký và hoạt động | Yêu cầu JVM thoát | Exit status gửi OS |
| `Runtime.halt(code)` | **Không bảo đảm/không chạy hooks** | Dừng cưỡng bức | Exit status gửi OS |

Với **ứng dụng web có traffic thật**, muốn shutdown nên dùng lifecycle của tiến trình/container và graceful shutdown. Không tạo HTTP endpoint công khai chỉ để gọi `System.exit`.

## 11. `ContextClosedEvent` là “bắt đầu đóng”, không phải “đóng xong”

Nếu code có:

~~~java
@EventListener
public void onClose(ContextClosedEvent event) {
    System.out.println("Context is closing");
}
~~~

listener có thể chạy trong lúc những bean khác **vẫn đang running**. Do đó, hạn chế:

- Gọi API của bean khác với giả định nó sẽ tồn tại suốt một nhiệm vụ dài.
- Bắt đầu I/O mới hoặc transaction mới vào lúc context đang đóng.
- Chờ vô hạn bên trong event listener.
- Gọi `context.close()` đệ quy.
- Coi event close là mốc “mọi request đã được drain”.

Nếu mục tiêu là **ngừng consumer, scheduler hoặc nhận việc mới**, dùng `SmartLifecycle` với phase và `stop(Runnable)`, hoặc một callback shutdown được thiết kế và kiểm thử rõ. Nếu cần **giải phóng socket/file**, `@PreDestroy`/destroy method là điểm thích hợp. Nếu cần **mã chạy sau khi tất cả context đã đóng tại JVM shutdown**, xem `SpringApplicationShutdownHandlers` và bảo đảm code không phụ thuộc Spring beans.

### Vì sao callback `stop(Runnable)` quan trọng?

Nếu bean cần dừng bất đồng bộ:

~~~java
@Override
public void stop(Runnable callback) {
    stopAcceptingJobs();
    executor.execute(() -> {
        try {
            waitForInFlightJobs();
        } finally {
            callback.run();
        }
    });
}
~~~

Đây là **mã mô tả** trong một bean `SmartLifecycle` có `executor` và các phương thức hỗ trợ đã tồn tại. Callback phải được gọi khi đã hoàn tất dừng; tránh gọi quá sớm hoặc quên gọi. Với code production còn phải xử lý việc `executor.execute` có thể từ chối tác vụ khi shutdown.

Mục tiêu là để lifecycle processor biết khi nào có thể tiếp tục dừng các phase kế tiếp.

## 12. Graceful shutdown của Spring Boot web server

Một HTTP server đóng context không đồng nghĩa **mọi request đang chạy sẽ bị chấm dứt tức thì**; Spring Boot có graceful shutdown để hạn chế nhận thêm request mới và cho request hiện tại cơ hội hoàn tất trong một khoảng thời gian.

Với **Spring Boot 3.3**, cấu hình điển hình:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Giải thích:

- `server.shutdown=graceful` bật chế độ graceful shutdown của web server nhúng tương ứng.
- `spring.lifecycle.timeout-per-shutdown-phase=20s` đặt giới hạn chờ theo phase khi dừng các `SmartLifecycle`; không phải “JVM chắc chắn dừng sau đúng 20 giây”.
- Trong Spring Boot 3.3, graceful shutdown được hỗ trợ trên **Tomcat, Jetty, Reactor Netty và Undertow** với cách ngừng nhận request mới phụ thuộc server.
- Nó được thực hiện trong quá trình **đóng context**, ở giai đoạn sớm của việc dừng `SmartLifecycle`.
- Nếu hệ thống orchestration gửi `SIGKILL` trước khi hết khoảng grace, Spring không thể hoàn tất mọi callback.

**Lưu ý phiên bản:** các bản Spring Boot khác có thể có mặc định graceful shutdown khác. Với module 3.3, nên cấu hình tường minh nếu muốn graceful; không mượn mặc định của bản mới hơn để suy diễn.

### Readiness khác việc socket đã đóng

Khi bắt đầu graceful shutdown, Spring Boot có thể chuyển readiness sang `ReadinessState.REFUSING_TRAFFIC`. Nhưng probe HTTP có thể chưa nhận thấy ngay vì còn chu kỳ kubelet/readiness và cập nhật endpoint. Mốc trạng thái nội bộ, việc web server từ chối request mới và thời điểm load balancer ngừng gửi traffic là **những mốc khác nhau**.

Với Kubernetes, cần phối hợp:

- `terminationGracePeriodSeconds` đủ cho việc drain/stop được cấu hình.
- Readiness probe và thời điểm loại Pod khỏi Service.
- `preStop` khi thực sự có nhu cầu trì hoãn/điều phối để traffic được drain.
- Thời gian stop của queue consumer, connection pool và worker.
- Các request cũ đang xử lý và chính sách timeout.

Không thể bảo đảm graceful shutdown bằng một callback `@PreDestroy` đơn lẻ nếu vẫn còn request/task đang chạy.

## 13. Tắt hook Boot có đồng nghĩa không còn shutdown hook?

**Không.** Chỉ xét `SpringApplication.setRegisterShutdownHook(false)`: bạn yêu cầu `SpringApplication` không dùng cơ chế hook của chính nó để đăng ký context mới. Nhưng:

- JVM vẫn có thể có hooks khác do thư viện hoặc mã ứng dụng đăng ký.
- Một context độc lập có thể tự gọi `registerShutdownHook()` của Spring Framework.
- Những tài nguyên không do Spring quản lý có cơ chế shutdown riêng.
- `System.exit` vẫn yêu cầu JVM shutdown, bất kể cờ của Spring Boot.

Vì vậy, nếu thử nghiệm trong JVM đã có nhiều hook, không thể lấy một dòng callback chạy như bằng chứng rằng Boot hook đã được đăng ký.

### Có nên tự đăng ký cả hai loại hook?

Thông thường **không**:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);
context.registerShutdownHook();
~~~

Đây là **đoạn thể hiện một thao tác thường không cần làm trong Boot**, không phải khuyến nghị. Spring Boot đã có cơ chế đóng context khi JVM shutdown mặc định. Đăng ký thêm một hook framework riêng có thể khiến nhiều hook cùng nhắm vào context, làm tăng độ khó suy luận thứ tự đóng, mặc dù implementation Spring có cơ chế bảo vệ để tránh hủy bean lặp.

Nếu đang viết ứng dụng Spring Framework thuần **không qua `SpringApplication`**, phương thức `context.registerShutdownHook()` lại có thể là lựa chọn phù hợp. Luôn chọn theo **ai sở hữu vòng đời context**.

## 14. Nhiều context trong một JVM

Một tiến trình có thể tạo nhiều `ApplicationContext`, ví dụ chạy hai phần nghiệp vụ riêng hoặc sử dụng parent/child contexts. Khi đó:

- `SpringApplicationShutdownHook` có thể quản lý những context đã đăng ký qua các lần chạy Boot tương ứng.
- `contextA.close()` chỉ nhắm tới `contextA` theo hợp đồng; đừng tự suy ra `contextB` độc lập cũng đóng.
- Context cha/con có quan hệ vòng đời và truyền sự kiện riêng, cần đọc API của kiểu context đang dùng; không dựa vào “đóng một cái chắc đóng tất cả”.
- Những context không do Boot đăng ký qua đường đó cần cơ chế sở hữu/đóng riêng.
- `SpringApplicationShutdownHandlers` được gọi **sau các context đã đăng ký** ngừng active ở JVM shutdown; không nên truy cập bean của chúng trong handler.

Vì vậy, với nhiều context hoặc nhiều thư viện cùng đăng ký JVM hooks, **đừng thiết kế nghiệp vụ phụ thuộc vào một thứ tự toàn cục ngầm định**. Hãy xác định context nào sở hữu resource nào và đặt logic stop/destroy ở chính context sở hữu.

## 15. Tại sao `close()` đã chạy nhưng JVM vẫn sống?

Đây là lỗi vận hành phổ biến với CLI, batch processor hoặc ứng dụng tự tạo background thread.

Kiểm tra theo thứ tự:

1. `context.isActive()` đã chuyển `false` chưa?
2. Có `ExecutorService` hoặc `Thread` **non-daemon** nào được tạo ngoài container không?
3. Có SDK hoặc library giữ connection/worker threads sống?
4. Các bean `SmartLifecycle` đã stop chưa; `stop(Runnable)` có gọi callback không?
5. `@PreDestroy`/destroy method đã chạy hay bị chặn vô hạn?
6. Nếu dùng virtual threads, các non-daemon carrier/keep-alive hoặc các thành phần khác có ảnh hưởng vòng đời JVM không?
7. Có một JVM shutdown hook khác đang chờ vô hạn khi quá trình shutdown đã bắt đầu?

Ví dụ lỗi:

~~~java
ExecutorService externalPool = Executors.newSingleThreadExecutor();
externalPool.submit(() -> {
    while (!Thread.currentThread().isInterrupted()) {
        // Không có điều kiện kết thúc thực tế.
    }
});

context.close();
// externalPool không thuộc Spring bean lifecycle.
// JVM có thể vẫn sống vì worker thread.
~~~

Đây là **ví dụ cố ý không tốt**, cần import tương ứng và biến `context` hợp lệ, không nên chạy nguyên xi vì vòng lặp có thể tốn CPU. Cách khắc phục là thiết kế job có cơ chế hủy, dừng executor và chờ kết thúc có timeout, không dùng `System.exit(0)` để che lỗi quản lý thread.

Nếu `context.close()` **chưa trả về**, hãy tìm các callback stop/destroy đang chờ, đặc biệt `SmartLifecycle.stop(Runnable)`, và kiểm tra thread dump, logging và timeout. Nếu `close()` **đã trả về** nhưng JVM sống, ưu tiên kiểm tra non-daemon threads ngoài context.

## 16. Vì sao `@PreDestroy` không được gọi khi bị kill?

Một số khả năng:

- Tiến trình bị `SIGKILL`/`kill -9` hoặc container cưỡng bức terminate, nên JVM **không chạy shutdown hooks**.
- `SpringApplication.setRegisterShutdownHook(false)` được sử dụng mà không có cơ chế đóng thay thế.
- Object được tạo bằng `new` bên ngoài Spring, không phải bean singleton do container quản lý.
- Bean thuộc `prototype`: Spring thường **không tự quản lý callback hủy từng instance prototype**.
- Context chưa được khởi tạo xong hoặc quá trình khởi động thất bại trước khi bean được tạo.
- Code cleanup bị kẹt/bị lỗi hoặc JVM chạm giới hạn thời gian shutdown của orchestration.
- Bạn nhầm giữa đóng context do test framework quản lý và thao tác kill process thực sự.

Không giải quyết mọi trường hợp bằng cách gắn thêm nhiều `Runtime.addShutdownHook(...)`. Phải xác định có nhận được **shutdown bình thường** không, tài nguyên thuộc ai và callback đặt ở vòng đời đúng chưa.

## 17. Viết shutdown code an toàn

Các nguyên tắc nên áp dụng:

**Idempotent:** dừng/hủy lặp không gây tác dụng phụ nguy hiểm. `close()` của context Spring có bảo vệ trạng thái, nhưng tài nguyên tự viết vẫn cần logic an toàn.

**Bounded:** có timeout cho việc chờ request, message hay transaction đang xử lý. Một handler treo vô hạn có thể khiến orchestrator kill process sau grace period.

**Không phụ thuộc bean đã hủy:** Spring shutdown handlers chạy sau khi context đóng; dùng dữ liệu tự có hoặc logging độc lập, không gọi vào bean đã hết vòng đời.

**Không bắt đầu tác vụ mới:** khi context đang đóng, tránh tạo thêm request/job không thể hoàn tất.

**Quan sát được:** log rõ mốc nhận shutdown, bắt đầu/ngừng nhận việc, stop completed, destroy completed, application exited. Không log dữ liệu nhạy cảm.

**Không giả định thứ tự JVM hooks:** các hook độc lập có thể chạy đồng thời. Nếu có thứ tự bắt buộc, dùng lifecycle phase hoặc handler API có hợp đồng phù hợp.

**Tài nguyên bên ngoài được bảo vệ:** dữ liệu quan trọng phải được thiết kế với transaction, ack/retry/idempotency, không dựa hoàn toàn vào việc hook luôn được chạy.

## 18. Kiểm thử shutdown bằng JVM độc lập

### Kiểm thử manual close

Chạy demo `--demo.mode=manual` và đối chiếu các mốc:

~~~text
EVENT ContextClosedEvent
WORKER stop
RESOURCE @PreDestroy
RESOURCE cleanup
MAIN after close active=false
BOOT_HANDLER active=false
~~~

Đây là **các dòng phần cuối** của demo. `BOOT_HANDLER` chỉ xuất hiện khi JVM thật sự shutdown sau đó. Nếu trong một JVM còn non-daemon thread khác, thời điểm handler xuất hiện có thể muộn hơn.

### Kiểm thử System.exit

Chạy JVM mới với `--demo.mode=exit` và so sánh:

~~~text
MAIN request System.exit
EVENT ContextClosedEvent
WORKER stop
RESOURCE @PreDestroy
RESOURCE cleanup
BOOT_HANDLER active=false
~~~

Lưu ý: đây là thử nghiệm **cố ý kết thúc JVM**; không chạy bên trong JUnit test runner của dự án hoặc tiến trình chứa dịch vụ khác.

### Kiểm thử SIGTERM trên môi trường tương tự production

Với Unix/Linux và ứng dụng web chạy lâu dài:

~~~bash
java -jar my-service.jar --server.shutdown=graceful &
pid=$!

# Khi đã xác nhận app ready từ probe:
kill -TERM "$pid"
wait "$pid"
~~~

Đây là **script minh họa**, không phải giải pháp kiểm tra readiness hoàn chỉnh. Trong thử nghiệm thực tế, đợi health/readiness bằng một điều kiện có timeout, không đoán thời gian bằng một `sleep` cố định. `SIGTERM` thường kích hoạt JVM shutdown hooks trên OpenJDK, nhưng hành vi còn phụ thuộc OS/runtime/container.

### Kiểm thử lỗi cưỡng bức

Không bao giờ dùng `kill -9` như thử nghiệm thường xuyên trên hệ thống thật có dữ liệu quan trọng. Trong một môi trường cô lập có dữ liệu giả, có thể kiểm chứng rằng `SIGKILL` không bảo đảm callback chạy, để thiết kế phục hồi từ message queue và transactional storage phù hợp.

### Kiểm thử tự động

Đối với bean lifecycle, có thể viết `@SpringBootTest` và kiểm tra callback qua test context tùy biến. Tuy nhiên, **không gọi `System.exit` trong cùng JVM JUnit/Gradle test worker**: nó có thể giết cả tiến trình chạy test. Nếu cần kiểm thử đúng JVM hook, dùng **subprocess độc lập** và một test harness chờ stdout/exit code với timeout rõ ràng.

## 19. So sánh nhanh các API dừng ứng dụng

| API hoặc cơ chế | Khi nào nên dùng | Không nên suy diễn |
| --- | --- | --- |
| `context.close()` | CLI/batch tự quản lý context, integration test có sở hữu context | Không đồng nghĩa `System.exit` |
| `try-with-resources` với context | Chạy tác vụ trong scope hữu hạn | Không bọc web server lâu dài để rồi đóng ngay |
| `SpringApplication.exit(context)` | Cần đóng context và tính exit code | Không tự gửi exit code cho OS |
| `System.exit(code)` | Kết thúc một JVM độc lập có chủ đích | Không dùng để dừng riêng một bean/request |
| Spring Boot shutdown hook mặc định | JVM shutdown bình thường, ứng dụng Boot do Boot quản lý | Không xử lý `SIGKILL` |
| `context.registerShutdownHook()` | Spring Framework thuần hoặc context tự quản lý ngoài Boot | Không cần đăng ký thêm vô điều kiện trong Boot |
| `SpringApplication.getShutdownHandlers()` | Hành động tuần tự sau khi context đóng tại JVM shutdown | Không chạy chỉ vì gọi `close()` |
| `SmartLifecycle.stop(Runnable)` | Ngừng consumer/worker, thứ tự theo phase | Không phải callback hủy bean cuối cùng |
| `@PreDestroy` / destroy method | Giải phóng tài nguyên bean | Không đảm bảo được gọi trong forced kill |
| `server.shutdown=graceful` | Cho server web cơ hội drain request | Không bảo đảm hạ tầng ngừng traffic tức thì |

## 20. Câu hỏi tự kiểm tra

1. **`ConfigurableApplicationContext.close()` có gọi `System.exit()` không?** Không.
2. **`SpringApplicationShutdownHook` là API mở rộng công khai để tự `new` hay một phần nội bộ?** Là cơ chế nội bộ của Spring Boot.
3. **Spring Boot 3.3 mặc định có đăng ký JVM shutdown hook cho context không?** Có; `setRegisterShutdownHook(true)` là mặc định.
4. **Nếu muốn đóng context ngay khi job CLI hoàn tất, dùng gì?** `context.close()` hoặc `try-with-resources` theo phạm vi sở hữu.
5. **Nếu muốn đóng context đồng thời tính exit code, dùng gì?** `SpringApplication.exit(context)`.
6. **`SpringApplication.exit(context)` có tự kết thúc JVM không?** Không; muốn gửi exit status ra OS có thể gọi `System.exit(code)` sau đó.
7. **Khi JVM nhận `SIGKILL`, shutdown hooks có chắc chạy không?** Không.
8. **`ContextClosedEvent` xuất hiện trước hay sau `SmartLifecycle.stop`?** Trước trong đường `AbstractApplicationContext.doClose()` bình thường.
9. **Bean `@PreDestroy` thường được gọi trước hay sau giai đoạn stop lifecycle?** Sau trong đường đóng context thông thường.
10. **`SpringApplicationShutdownHandlers` chạy khi nào?** Khi JVM shutdown, sau khi các context đã đăng ký được đóng và không còn active.
11. **Gọi `context.close()` nhưng JVM vẫn sống, nên kiểm tra điều gì?** Non-daemon threads, external executor và resources nằm ngoài context.
12. **Có nên tự gọi `context.registerShutdownHook()` trong mọi ứng dụng Boot không?** Không; Boot có hook mặc định.
13. **Cấu hình graceful shutdown HTTP trong Boot 3.3 là gì?** `server.shutdown=graceful`, phối hợp timeout và hệ thống điều phối.
14. **`spring.lifecycle.timeout-per-shutdown-phase=20s` có nghĩa toàn JVM chết đúng sau 20 giây không?** Không; đó là timeout theo phase stop.
15. **Một hook JVM riêng có được bảo đảm chạy sau Spring Boot hook không?** Không; các JVM shutdown hooks độc lập không có thứ tự được bảo đảm.
16. **Nếu cần dọn dẹp resource sau `close()` trong cùng JVM, có phải chờ Boot handler không?** Không. Bạn có thể thực thi code sau lời gọi `close()` trả về, hoặc thiết kế callback thích hợp; Boot handler gắn với JVM shutdown.
17. **Nếu một bean `SmartLifecycle` dừng bất đồng bộ, phải nhớ điều gì?** Gọi `callback.run()` khi việc dừng thực sự hoàn tất.
18. **Vì sao không nên chỉ dựa vào hook để bảo vệ dữ liệu quan trọng?** Vì forced kill, mất điện hoặc timeout có thể ngăn callback; cần cơ chế bền vững ở storage/message broker.

**Tổng kết:** Trong Spring Boot 3.3, **`ConfigurableApplicationContext.close()` là thao tác đóng context**, còn **`SpringApplicationShutdownHook` đưa thao tác đóng đó vào vòng đời shutdown của JVM**. Trên đường bình thường, context phát `ContextClosedEvent`, dừng các `Lifecycle` bean theo `LifecycleProcessor`, hủy singleton và chuyển sang inactive. `SpringApplicationShutdownHandlers` là API riêng cho hành động **sau khi các context đăng ký đã đóng tại JVM shutdown**, không phải callback chạy mỗi lần đóng context thủ công. Muốn vận hành an toàn, hãy giữ hook mặc định trừ khi host quản lý vòng đời riêng, dùng `SmartLifecycle` cho stop có thứ tự, `@PreDestroy` cho cleanup, graceful shutdown cho HTTP server và luôn kiểm thử cả đường dừng bình thường lẫn trường hợp bị kill cưỡng bức.

### Tài liệu tham khảo

- Spring Boot 3.3.13 — `SpringApplication` API (có `setRegisterShutdownHook`, `getShutdownHandlers`, `run`): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3.13 — `SpringApplication` reference, **Application Exit**: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — `SpringApplicationShutdownHandlers` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplicationShutdownHandlers.html
- Spring Boot 3.3.13 — mã nguồn `SpringApplication` (đăng ký hook, refresh context): https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/SpringApplication.java
- Spring Boot 3.3.13 — mã nguồn `SpringApplicationShutdownHook`: https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/SpringApplicationShutdownHook.java
- Spring Framework 6.1 — `AbstractApplicationContext` API (`close`/`doClose`/`registerShutdownHook`): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Boot 3.3 — **Graceful Shutdown**: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — **Actuator health groups / readiness probes**: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — **Gradle Plugin / Managing Dependencies**: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
