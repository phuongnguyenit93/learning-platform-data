# Thiết lập shutdown hook và ApplicationContextFactory trong SpringApplication

**Chủ đề:** Spring Boot Application Runtime → Thiết lập SpringApplication. Bài này tập trung vào hai điểm cấu hình cấp ứng dụng: cách Spring Boot đăng ký cơ chế đóng `ApplicationContext` khi JVM kết thúc và cách chọn chiến lược tạo `ApplicationContext` lúc khởi động. Ví dụ dưới đây dùng **Java 17+ và Spring Boot 3.3.x**; khi sử dụng phiên bản khác, hãy đối chiếu API và mặc định shutdown theo tài liệu của phiên bản đó.

## 1. Mục tiêu cần nắm

Sau bài học, bạn cần:

1. Nói rõ `SpringApplication` tạo, cấu hình, refresh và đóng `ApplicationContext` ở đâu trong vòng đời.
2. Giải thích `setRegisterShutdownHook(true/false)`, giá trị mặc định và trường hợp cần tự gọi `close()`.
3. Phân biệt **JVM shutdown hook** với **graceful shutdown của web server**, callback hủy bean và dừng tiến trình bằng hệ điều hành.
4. Giải thích `ApplicationContextFactory`, `WebApplicationType` và ba loại context thường gặp: servlet, reactive, non-web.
5. Cấu hình factory qua `setApplicationContextFactory(...)`, kiểm tra loại context thực sự tạo ra và nhận biết mismatch gây lỗi khởi động.
6. Thử các tình huống dừng ứng dụng và ghi lại bằng chứng từ log, response HTTP và callback giải phóng tài nguyên.

Hai lựa chọn phục vụ **hai thời điểm khác nhau**:

| Cấu hình | Xảy ra khi nào? | Điều khiển gì? | Giá trị dùng thông thường |
|---|---|---|---|
| `setApplicationContextFactory(...)` | Trước khi refresh context trong startup | Đối tượng `ConfigurableApplicationContext` nào được tạo | Giữ factory mặc định nếu không có yêu cầu đặc biệt |
| `setRegisterShutdownHook(true/false)` | Trong quá trình ứng dụng đăng ký vòng đời với JVM | Có đăng ký hook để đóng context khi JVM shutdown hay không | Để `true` nếu JVM sở hữu vòng đời ứng dụng |
| `server.shutdown` | Khi đóng context của web app | Web server dừng theo kiểu graceful hay immediate | Chọn theo phiên bản và yêu cầu vận hành |
| `@PreDestroy` / `DisposableBean` | Khi Spring destroy bean trong quá trình đóng context | Tài nguyên do bean quản lý được dọn thế nào | Cài callback cleanup ngắn, tin cậy |

Không nên dùng một cấu hình làm thay việc của cấu hình khác: chọn đúng context **không** tự quyết định cách JVM dừng; shutdown hook **không** tự sửa được các bean không đóng tài nguyên.

## 2. Vòng đời và vị trí hai điểm cấu hình

~~~text
main(String[] args)
    |
    v
new SpringApplication(Source.class)
    |  setApplicationContextFactory(factory)
    |  setRegisterShutdownHook(true/false)
    v
SpringApplication.run(args)
    |
    +-- suy ra hoặc nhận WebApplicationType (SERVLET / REACTIVE / NONE)
    +-- chuẩn bị Environment và nguồn cấu hình
    +-- gọi factory tạo ConfigurableApplicationContext CHƯA refresh
    +-- cấu hình context, đăng ký nguồn bean, refresh context
    +-- khởi động embedded web server nếu là web application
    +-- chạy ApplicationRunner / CommandLineRunner
    +-- công bố ApplicationReadyEvent khi startup thành công
    |
    v
Ứng dụng hoạt động: nhận HTTP request / xử lý job
    |
    +-- JVM shutdown hợp lệ, nếu hook đăng ký --------+
    +-- hoặc ứng dụng gọi context.close() ------------+
                                                       |
                                                       v
                                              ApplicationContext.close()
                                                       |
                                 +---------------------+-------------------+
                                 |                                         |
                       ContextClosedEvent                         dừng SmartLifecycle,
                       và các listener                            destroy singleton bean
                                                                         |
                                                                   @PreDestroy,
                                                                   DisposableBean,
                                                                   destroy method
~~~

Đây là sơ đồ khái niệm; tiến trình thực có nhiều sự kiện startup và shutdown khác. `ApplicationContextFactory` tạo context **chưa được cấu hình/refresh đầy đủ**. `SpringApplication` tiếp tục chuẩn bị environment, nguồn bean, refresh và các cơ chế tích hợp. Factory không nên tự gọi `refresh()` hoặc tự đóng context vừa tạo.

Khi `close()` bắt đầu, Spring phát `ContextClosedEvent`, ngừng các thành phần lifecycle và chạy các callback destroy phù hợp. Thứ tự giữa các callback của nhiều bean, thread log hoặc các thao tác bất đồng bộ có thể khác; tránh thiết kế nghiệp vụ dựa trên một thứ tự log tùy ý.

## 3. Giá trị mặc định và điều gì thật sự được bảo đảm

Theo API Spring Boot 3.3, `SpringApplication#setRegisterShutdownHook(boolean)` mặc định là `true`. Vì vậy, ứng dụng Boot thông thường đã đăng ký hook để yêu cầu đóng context khi JVM shutdown. Trường hợp JVM nhận tín hiệu kết thúc có xử lý bình thường, hook giúp Spring chạy các callback dọn tài nguyên.

Tuy nhiên, **hook không phải bảo hiểm cho mọi kiểu chấm dứt tiến trình**. `SIGKILL` (ví dụ `kill -9` trên Linux), dừng cưỡng bức không cho JVM chạy shutdown sequence, sự cố phần cứng hoặc một số trường hợp crash không bảo đảm hook được chạy. `System.exit(...)` kích hoạt trình tự shutdown của JVM; `Runtime.halt(...)` bỏ qua shutdown hooks. Cách IDE, container hay hệ điều hành gửi tín hiệu cũng ảnh hưởng việc hook có cơ hội chạy hay không.

Về loại context, Boot thường suy ra từ classpath và `WebApplicationType`:

| WebApplicationType | Context mặc định khi dùng Boot 3.3 | Trường hợp điển hình |
|---|---|---|
| `SERVLET` | `AnnotationConfigServletWebServerApplicationContext` | Spring MVC với embedded servlet server |
| `REACTIVE` | `AnnotationConfigReactiveWebServerApplicationContext` | WebFlux reactive server |
| `NONE` | `AnnotationConfigApplicationContext` | CLI, batch worker, tác vụ không dùng web server |

Khi **Spring MVC và WebFlux cùng có trên classpath**, Boot thường chọn loại servlet. Có thể chủ động đặt `setWebApplicationType(WebApplicationType.NONE)` cho chương trình CLI, nhưng không nên nhầm nó với việc thay factory. `WebApplicationType` nói ứng dụng thuộc mô hình nào; factory quyết định tạo **đối tượng context cụ thể** nào tương thích với mô hình đó.

## 4. Ứng dụng mẫu chạy được: quan sát context và shutdown

### 4.1. Tạo dự án

Tạo một project Maven tên `lifecycle-lab` trên Spring Initializr, với group `com.example`, package `com.example.lifecyclelab`, Java 17, Spring Boot 3.3.x và dependency **Spring Web**. Initializr tạo sẵn Maven Wrapper; giữ nguyên `pom.xml` và phiên bản starter do Initializr sinh. Không cần cài Tomcat ngoài.

Tạo các file:

~~~text
lifecycle-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/lifecyclelab/
    LifecycleLabApplication.java
    ProbeController.java
  src/main/resources/
    application.properties
~~~

### 4.2. Main class: cấu hình cả shutdown hook và factory

File `src/main/java/com/example/lifecyclelab/LifecycleLabApplication.java`:

~~~java
package com.example.lifecyclelab;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.ApplicationContextFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.web.servlet.context.AnnotationConfigServletWebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class LifecycleLabApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                LifecycleLabApplication.class);

        // Mac dinh da la true; dat tuong minh de de quan sat.
        app.setRegisterShutdownHook(true);

        // Lab su dung Spring MVC: chon context servlet tuong thich.
        app.setApplicationContextFactory(
                ApplicationContextFactory.ofContextClass(
                        AnnotationConfigServletWebServerApplicationContext.class));

        ConfigurableApplicationContext context = app.run(args);
        System.out.println("LAB_CONTEXT_TYPE="
                + context.getClass().getSimpleName());
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("LAB_APPLICATION_READY");
    }

    @EventListener(ContextClosedEvent.class)
    public void onClosed() {
        System.out.println("LAB_CONTEXT_CLOSED");
    }

    @Bean
    CleanupProbe cleanupProbe() {
        return new CleanupProbe();
    }

    public static final class CleanupProbe {
        @PreDestroy
        public void cleanup() {
            System.out.println("LAB_PRE_DESTROY");
        }
    }
}
~~~

**Giải thích từng dòng then chốt:**

- `new SpringApplication(LifecycleLabApplication.class)` cho phép gọi setter trước `run(...)`; cách viết ngắn `SpringApplication.run(Source.class, args)` không cho ta biến ứng dụng để tùy chỉnh trực tiếp.
- `setRegisterShutdownHook(true)` minh họa cấu hình tường minh. Trong môi trường thông thường có thể bỏ dòng này vì `true` là mặc định.
- `ApplicationContextFactory.ofContextClass(...)` tạo factory từ một lớp context có thể khởi tạo; ở đây lớp servlet tương thích với dependency Spring Web.
- `app.run(args)` mới tạo/refresh context và chạy ứng dụng. Đừng gọi `context.close()` ngay sau `run` trong web server muốn phục vụ liên tục.
- `ApplicationReadyEvent` và `ContextClosedEvent` tạo marker khi ứng dụng sẵn sàng hoặc bắt đầu đóng; `@PreDestroy` là callback dọn tài nguyên của bean singleton `CleanupProbe`.
- `LAB_CONTEXT_TYPE` được in **sau khi `run` trả về**, vì thế marker `LAB_APPLICATION_READY` có thể xuất hiện trước dòng loại context; đây là hành vi hợp lý.

Để tránh đặt chữ tiếng Việt trong mã nguồn Java ở môi trường chưa thống nhất encoding, chuỗi log và comment trong ví dụ chỉ dùng ASCII; phần giải thích và output vẫn dùng tiếng Việt.

### 4.3. Endpoint cho bằng chứng ứng dụng đang phục vụ

File `src/main/java/com/example/lifecyclelab/ProbeController.java`:

~~~java
package com.example.lifecyclelab;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {
    @GetMapping("/probe")
    public Map<String, String> probe() {
        return Map.of("status", "running");
    }
}
~~~

Khi context là servlet web context và embedded server đang nghe cổng, endpoint `GET /probe` trả JSON với một khóa.

### 4.4. Cấu hình web shutdown

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=lifecycle-lab
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Chúng ta ghi `server.shutdown=graceful` tường minh để người học nhìn thấy cấu hình. Trong Spring Boot 3.3, cần đặt `server.shutdown=graceful` để bật graceful shutdown cho embedded web server được hỗ trợ; giá trị mặc định không tự bật chế độ này. `spring.lifecycle.timeout-per-shutdown-phase` đặt khoảng thời gian tối đa cho **một phase** dừng lifecycle, không phải lời hứa toàn bộ tiến trình sẽ kết thúc đúng 20 giây. Giá trị này không quyết định việc JVM có đăng ký shutdown hook hay không.

### 4.5. Chạy và đối chiếu marker

Tại thư mục `lifecycle-lab`, Linux/macOS:

~~~bash
java -version
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd spring-boot:run
~~~

Trong terminal khác:

~~~bash
curl -i http://localhost:8080/probe
~~~

Nếu dùng Windows PowerShell có alias `curl`, gọi `curl.exe -i http://localhost:8080/probe`. Với project chạy đúng, HTTP có status 200 và body tương đương:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"status":"running"}
~~~

Trong console ứng dụng tìm hai marker:

~~~text
LAB_APPLICATION_READY
LAB_CONTEXT_TYPE=AnnotationConfigServletWebServerApplicationContext
~~~

Các dòng log Tomcat, timestamp và PID thay đổi theo môi trường. Sự có mặt của hai marker cùng response HTTP hợp lệ chứng minh factory tạo context tương thích và startup đã hoàn tất.

Sau đó bấm **Ctrl+C** ở terminal đang chạy ứng dụng (hoặc gửi tín hiệu kết thúc hợp lệ cho tiến trình JVM). Khi cơ chế shutdown có cơ hội thực hiện, thường thấy:

~~~text
LAB_CONTEXT_CLOSED
LAB_PRE_DESTROY
~~~

Log graceful shutdown của server có thể xen vào. Nếu chạy qua Maven plugin, signal/terminal/IDE có thể tác động cả Maven và JVM con; để quan sát rõ hơn, hãy chạy file JAR như chặng tiếp theo. **Không** lấy việc thiếu marker khi tiến trình bị cưỡng bức làm bằng chứng `@PreDestroy` hỏng.

## 5. Chạy JAR và tự kiểm tra đóng context bằng tín hiệu

Đóng phiên Maven trước để giải phóng cổng, rồi build:

~~~bash
./mvnw clean package
java -jar target/lifecycle-lab-0.0.1-SNAPSHOT.jar
~~~

Nếu dùng Windows: `./mvnw.cmd clean package`, rồi lệnh `java -jar` tương tự. Tên JAR ví dụ áp dụng khi version project là `0.0.1-SNAPSHOT`; nếu cấu hình version khác hãy lấy đúng tên JAR sinh ra trong `target/`.

Với Linux/macOS, có thể chạy tiến trình từ shell và lưu log (không dùng cách này để mô phỏng `SIGKILL`):

~~~bash
java -jar target/lifecycle-lab-0.0.1-SNAPSHOT.jar > app.log 2>&1 &
app_pid=$!
curl -i http://localhost:8080/probe
kill -TERM "$app_pid"
wait "$app_pid"
~~~

Nếu `curl` chạy trước khi ứng dụng sẵn sàng, chờ log `LAB_APPLICATION_READY` rồi thử lại; đây là lỗi thời điểm khởi động, không phải lỗi shutdown hook. Với `kill -TERM`, shell có thể báo exit status không bằng 0 khi tiến trình dừng vì tín hiệu; hãy xem log để kết luận về callback. Không dùng kill PID khác hoặc trên dịch vụ đang phục vụ người dùng thật.

Sau shutdown, kiểm tra `app.log` có `LAB_CONTEXT_CLOSED` và `LAB_PRE_DESTROY`. Sau khi tiến trình thực sự dừng và không có server khác ở cổng 8080, request đến `/probe` không còn kết nối được.

**Phân biệt bốn bằng chứng:**

| Quan sát | Điều có thể kết luận | Điều chưa thể kết luận |
|---|---|---|
| `LAB_CONTEXT_TYPE=...Servlet...` | Factory trả context servlet trong lần chạy đó | HTTP endpoint nghiệp vụ nhất định đúng |
| `LAB_APPLICATION_READY` | Startup đi đến mốc ready event | Mọi request tương lai đều thành công |
| `LAB_CONTEXT_CLOSED` | Context đã bước vào pha đóng và phát sự kiện | Tất cả resource bên ngoài đã được giải phóng |
| `LAB_PRE_DESTROY` | Bean được Spring gọi callback destroy | Hook có thể chạy cả khi tiến trình bị `SIGKILL` |
| Ngừng kết nối cổng 8080 | Không còn listener ở cổng đó (nếu đã loại trừ service khác) | Mọi job nền và dữ liệu đã được commit |

## 6. Khi nào tắt shutdown hook và tự quản lý close()

API:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setRegisterShutdownHook(false);
~~~

Giá trị `false` ngăn ứng dụng tự đăng ký hook đóng context cho JVM theo cơ chế của `SpringApplication`. Nó **không** tự động gọi `close()`, không khiến `@PreDestroy` chạy khi `main()` trả về, cũng không có nghĩa web server ngừng nghe cổng. Khi tắt hook, **một cơ chế sở hữu vòng đời khác phải đóng context**.

Trường hợp phù hợp là một ứng dụng được nhúng vào host có lifecycle riêng, chương trình CLI/batch cần xác định rõ phạm vi tài nguyên, hoặc test harness chủ động tạo và đóng context. Thường không cần tắt ở một Spring Boot web service triển khai độc lập.

### Ví dụ non-web tự đóng sau khi xong việc

Ví dụ dưới đây là **main class cho dự án CLI riêng**, không đặt cùng lúc với một `@SpringBootApplication` khác trong cùng phạm vi component scan. Có thể dùng project chỉ với dependency Spring Boot starter cơ bản.

File `src/main/java/com/example/clilab/CliLabApplication.java`:

~~~java
package com.example.clilab;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.ApplicationContextFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

@SpringBootApplication
public class CliLabApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(CliLabApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setRegisterShutdownHook(false);
        app.setApplicationContextFactory(
                ApplicationContextFactory.ofContextClass(
                        AnnotationConfigApplicationContext.class));

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("LAB_CLI_WORK_COMPLETE");
        }
        System.out.println("LAB_CLI_CONTEXT_CLOSED");
    }

    @Bean
    Cleanup cleanup() {
        return new Cleanup();
    }

    public static final class Cleanup {
        @PreDestroy
        public void destroy() {
            System.out.println("LAB_CLI_PRE_DESTROY");
        }
    }
}
~~~

Output có ý nghĩa kỳ vọng:

~~~text
LAB_CLI_WORK_COMPLETE
LAB_CLI_PRE_DESTROY
LAB_CLI_CONTEXT_CLOSED
~~~

Dòng `LAB_CLI_PRE_DESTROY` xuất hiện khi thoát khối `try-with-resources`, bởi `ConfigurableApplicationContext` hỗ trợ `close()`. Trong ví dụ này callback **do explicit close kích hoạt**, không phải do shutdown hook. Đừng đưa `try-with-resources` bao quanh `run()` của web server khi bạn muốn ứng dụng tiếp tục phục vụ sau khi `main()` kết thúc, vì nó sẽ đóng ngay context.

Một lựa chọn khác là giữ tham chiếu `ConfigurableApplicationContext` rồi gọi `context.close()` trong `finally`. Nếu cần trả exit code cho CLI, có thể sử dụng `SpringApplication.exit(context)` theo API thích hợp; phải hiểu rằng việc đóng Spring context và việc kết thúc tiến trình JVM là hai hành động liên quan nhưng khác nhau.

## 7. ApplicationContextFactory: chọn đúng loại context

`ApplicationContextFactory` là interface chiến lược nhận `WebApplicationType` và trả một `ConfigurableApplicationContext`. Boot cung cấp:

- `ApplicationContextFactory.DEFAULT`: chọn implementation phù hợp với servlet, reactive hoặc none.
- `ApplicationContextFactory.ofContextClass(ContextClass.class)`: dùng một lớp context cụ thể.
- `ApplicationContextFactory.of(ContextType::new)`: tạo context qua `Supplier`.
- Factory tự viết: tạo context có điều kiện theo `WebApplicationType`; thường nên ủy quyền về `DEFAULT` cho trường hợp không đặc biệt.

### 7.1. Khi không cần custom

Với hầu hết ứng dụng, đoạn sau là đủ:

~~~java
SpringApplication.run(LifecycleLabApplication.class, args);
~~~

Classpath và cấu hình chọn context. Việc chỉ muốn **quan sát** loại context thường không đủ lý do để thay factory; có thể lấy context trả về từ `run()` rồi in tên lớp. Chỉ custom khi cần dùng một implementation context đặc biệt, đáp ứng hệ thống host, hoặc kiểm thử hành vi tạo context.

### 7.2. Chọn context servlet tường minh

Ví dụ trong mục 4 dùng:

~~~java
app.setApplicationContextFactory(
        ApplicationContextFactory.ofContextClass(
                AnnotationConfigServletWebServerApplicationContext.class));
~~~

Lớp này thuộc package `org.springframework.boot.web.servlet.context` của Spring Boot 3.3. Nếu dự án sử dụng Spring MVC nhưng lại ép tạo `AnnotationConfigApplicationContext` thông thường, lifecycle web server có thể không tương thích hoặc lỗi khi chạy. Đừng chỉ đổi tên class với kỳ vọng Spring tự chuyển mọi bean web sang non-web.

### 7.3. Ghi log khi factory được gọi mà vẫn giữ cơ chế mặc định

Có thể thay dòng cấu hình factory ở mục 4 bằng **một** factory ủy quyền sau:

~~~java
app.setApplicationContextFactory(webType -> {
    ConfigurableApplicationContext context =
            ApplicationContextFactory.DEFAULT.create(webType);
    System.out.println("LAB_FACTORY_CALLED webType=" + webType
            + " context=" + context.getClass().getSimpleName());
    return context;
});
~~~

Thử nghiệm này dùng `DEFAULT` để tạo đúng context, sau đó ghi lại loại thực tế; nó không refresh context thủ công. Một số môi trường có nhu cầu custom `Environment`; `ApplicationContextFactory` còn có các phương thức mặc định liên quan kiểu và việc tạo environment. Khi thay thế hoàn toàn factory, cần bảo đảm environment/context tương thích; chỉ minh họa việc tạo context chưa đủ để chứng minh một custom factory sản xuất đã đúng.

### 7.4. Factory chọn theo WebApplicationType

Nếu thật sự cần chính sách cụ thể theo loại ứng dụng, có thể tạo một factory theo nhánh, mặc định delegate cho Spring Boot:

~~~java
app.setApplicationContextFactory(type -> {
    if (type == WebApplicationType.NONE) {
        return new AnnotationConfigApplicationContext();
    }
    return ApplicationContextFactory.DEFAULT.create(type);
});
~~~

Đoạn này là **snippet đặt trong main class đã import `WebApplicationType`, `AnnotationConfigApplicationContext` và `ApplicationContextFactory`**; không phải file Java độc lập. Bản thân ví dụ vẫn giữ semantics servlet/reactive cho các loại web. Nếu cần hỗ trợ cả nhiều kiểu context và environment riêng biệt, nên thiết kế một implementation đầy đủ và kiểm thử trên mọi `WebApplicationType` được hỗ trợ.

### 7.5. Factory không thay thế việc chọn web mode

Hai dòng dưới đây khác nhau:

~~~java
app.setWebApplicationType(WebApplicationType.NONE);
// Chon che do ung dung khong khoi dong web server.

app.setApplicationContextFactory(
        ApplicationContextFactory.ofContextClass(
                AnnotationConfigApplicationContext.class));
// Chon implementation context cu the.
~~~

Dùng cả hai cho một CLI là hợp lý. Nếu chỉ đặt `NONE` và giữ factory mặc định, Boot cũng tự tạo non-web context phù hợp. Nếu chỉ ép context thường nhưng để Boot suy ra `SERVLET`, cấu hình dễ bất nhất. Với ứng dụng web, giữ factory mặc định là lựa chọn đơn giản và ít rủi ro nhất trừ khi cần custom vì yêu cầu rõ ràng.

## 8. Shutdown hook và graceful shutdown: hai tầng trách nhiệm

Mô hình:

~~~text
JVM nhận tín hiệu dừng thông thường
    |
    +-- shutdown hook do SpringApplication đăng ký (mặc định)
            |
            +-- đóng ApplicationContext
                    |
                    +-- phát ContextClosedEvent
                    +-- dừng SmartLifecycle và embedded web server
                    |      +-- graceful: xử lý request đang phục vụ
                    |          trong thời gian được cấu hình
                    +-- destroy các bean phù hợp
                           +-- @PreDestroy / DisposableBean / destroyMethod
~~~

**Hook** là cơ chế nối JVM shutdown vào việc đóng context. **Graceful shutdown** là chính sách dừng server khi context đang được đóng; mục tiêu là cho request đang xử lý có thời gian hoàn tất và ngừng nhận request mới theo cơ chế của server. **Bean cleanup** là nơi ứng dụng trả resource như thread, socket, connection pool, file handle hoặc flush buffer nếu bean quản lý chúng.

Trong Spring Boot 3.3, bật graceful shutdown cho embedded web server được hỗ trợ bằng cấu hình sau:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Nếu dùng Boot 3.3 hoặc dòng khác, kiểm tra tài liệu đúng phiên bản để biết mặc định. Khi thử nghiệm tải, thời gian xử lý thực tế của request, server, phase và cách client giữ kết nối có thể thay đổi. `@PreDestroy` nên dọn tài nguyên trong thời gian hữu hạn; một callback bị treo có thể làm quá trình shutdown chậm hoặc không kết thúc như kỳ vọng.

**Tình huống thường nhầm:** đổi `server.shutdown=graceful` nhưng tắt hook và không gọi `close()`. Trong hoàn cảnh đó, JVM có thể kết thúc mà không cho Spring lifecycle chạy; tùy chọn graceful đơn lẻ không bảo đảm được dừng mềm. Ngược lại, giữ hook mặc định nhưng tự tạo thêm một `Runtime.getRuntime().addShutdownHook(...)` chỉ để gọi lại `context.close()` thường là thừa và làm khó xác định chủ sở hữu lifecycle.

## 9. Thực hành đối chiếu ba kịch bản

### Kịch bản A — Hook mặc định, web app còn hoạt động

1. Chạy JAR của mục 4 với `setRegisterShutdownHook(true)`.
2. Gọi `GET /probe`; lưu status HTTP, body và marker startup.
3. Gửi tín hiệu dừng hợp lệ, không cưỡng bức.
4. Tìm `LAB_CONTEXT_CLOSED` và `LAB_PRE_DESTROY`; sau đó xác minh tiến trình ngừng phục vụ.

**Kết luận hợp lệ:** JVM đã có cơ hội chạy hook; context tiến vào pha đóng và bean nhận destroy callback. Không suy ra dữ liệu người dùng đã an toàn nếu ứng dụng chưa có cơ chế commit/flush đúng.

### Kịch bản B — Tắt hook nhưng explicit close trong CLI

1. Chạy project CLI của mục 6.
2. Quan sát `LAB_CLI_WORK_COMPLETE`.
3. Quan sát `LAB_CLI_PRE_DESTROY` khi thoát `try` và `LAB_CLI_CONTEXT_CLOSED` sau đó.

**Kết luận hợp lệ:** callback của Spring chạy do `close()` chủ động. So sánh với kịch bản A để phân biệt **nguồn gây đóng** và **hành động đóng**.

### Kịch bản C — Factory được chọn tường minh hoặc delegate

1. Chạy app Spring MVC với `ofContextClass(AnnotationConfigServletWebServerApplicationContext.class)`.
2. Ghi `LAB_CONTEXT_TYPE` và kiểm tra `GET /probe`.
3. Đổi sang factory ủy quyền `DEFAULT.create(webType)` của mục 7.3, build lại, chạy lại trên cùng cổng khi tiến trình cũ đã dừng.
4. So loại context và kết quả HTTP giữa hai lần.

**Kết luận hợp lệ:** factory có thể thay đổi cách tạo context nhưng phải vẫn tương thích với web mode; với cùng classpath và hành vi mặc định, hai cách tạo ra servlet context và endpoint tương đương. Nếu xuất hiện lỗi refresh hoặc server không nghe cổng, kiểm tra web mode/context class và exception gốc thay vì xóa callback shutdown.

## 10. Hướng dẫn chẩn đoán lỗi theo tín hiệu

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý đúng phạm vi |
|---|---|---|
| Không thấy `LAB_PRE_DESTROY` khi dừng bằng `kill -9` | JVM bị kết thúc cưỡng bức; hook không có cơ hội chạy | Thử lại bằng `SIGTERM`/Ctrl+C phù hợp, kiểm tra cơ chế stop của môi trường |
| `setRegisterShutdownHook(false)` nhưng mong callback chạy khi JVM thoát | Không có cơ chế đóng context do ứng dụng quản lý | Gọi `context.close()` / try-with-resources ở đúng owner lifecycle hoặc giữ hook |
| App start nhưng không thấy HTTP listener | `WebApplicationType.NONE`, custom context không tương thích, hoặc startup lỗi | Kiểm tra web type, class factory, exception gốc và cổng thực tế |
| Servlet MVC dùng `AnnotationConfigApplicationContext` | Factory ép context non-web trong ứng dụng cần web lifecycle | Dùng factory mặc định hoặc servlet web server context tương thích |
| Factory tự `refresh()` rồi SpringApplication refresh tiếp | Vi phạm hợp đồng tạo context chưa refresh | Factory chỉ tạo context; SpringApplication thực hiện cấu hình/refresh |
| Context đóng nhưng bean vẫn giữ thread ngoài | Không có shutdown callback phù hợp hoặc thread do app tự quản lý | Thêm cleanup có timeout, thiết kế ownership rõ ràng |
| ContextClosedEvent có nhưng request chờ quá lâu | Request lâu, resource kẹt, graceful shutdown timeout/lifecycle phase | Kiểm tra thời gian request, timeout mỗi phase và log server |
| Lệnh Maven dừng nhưng log thiếu marker | Wrapper/IDE/signal có thể dừng JVM con theo cách khác | Chạy JAR trực tiếp, gửi tín hiệu đúng đến PID JVM rồi đối chiếu |
| Ứng dụng tự thoát ngay khi main kết thúc | Non-web không còn non-daemon thread hoặc code tự close | Xác nhận đây là CLI hay web, kiểm tra web mode và phạm vi try |

**Các điểm kỹ thuật dễ bỏ sót:**

- Với `@PreDestroy` trên Spring Boot 3.x, import `jakarta.annotation.PreDestroy` (không dùng nhầm namespace `javax.annotation` của các stack cũ).
- Spring quản lý callback destroy cho các bean đủ điều kiện, đặc biệt singleton; bean prototype không được Spring tự quản lý toàn bộ vòng đời hủy như singleton.
- `ContextClosedEvent` là dấu mốc bắt đầu quá trình đóng; chỉ nó không bảo đảm tất cả bean đã giải phóng resource.
- Đăng ký nhiều shutdown hooks độc lập có thể khiến các hook chạy đồng thời; không thiết kế phụ thuộc thứ tự giữa hook của các thư viện.
- Factory do ứng dụng tự viết phải trả context thích hợp, chưa refresh; không tạo hai context rồi chỉ trả một, vì context bỏ rơi có thể rò rỉ tài nguyên.
- Không phát tán trace chứa cấu hình bí mật hay dùng endpoint shutdown công khai trong môi trường production. Nếu cần orchestrator, nên cấu hình thời gian grace của môi trường triển khai đủ để JVM hoàn tất shutdown.

## 11. Câu hỏi tự kiểm tra có đáp án

**1. Bỏ `setRegisterShutdownHook(true)` khỏi ví dụ web thì Spring Boot 3.3 có còn đăng ký hook không?** Có, vì `true` là mặc định của `SpringApplication`.

**2. Đổi `setRegisterShutdownHook(false)` có làm bean được destroy ngay khi `main()` kết thúc không?** Không. Muốn chạy callback phải có cơ chế đóng `ApplicationContext` hợp lệ; `main()` kết thúc không tương đương `context.close()`.

**3. Thấy `LAB_CONTEXT_CLOSED` nhưng chưa thấy `LAB_PRE_DESTROY` có đủ kết luận tất cả resource đã giải phóng không?** Không. Event context-closed và destroy callback là các mốc riêng của quá trình shutdown.

**4. Vì sao `ofContextClass(AnnotationConfigApplicationContext.class)` không nên ép vào một ứng dụng MVC servlet?** Vì implementation đó không có lifecycle embedded servlet web server như `AnnotationConfigServletWebServerApplicationContext`, nên có thể không tương thích với cách Boot khởi động web app.

**5. Factory có nên gọi `context.refresh()` trước khi trả context không?** Không. `SpringApplication` chịu trách nhiệm cấu hình/refresh sau khi factory tạo instance.

**6. Tắt hook rồi đặt `server.shutdown=graceful` có bảo đảm JVM shutdown mềm không?** Không. Graceful server shutdown chỉ diễn ra khi luồng đóng context được kích hoạt; cần hook hoặc explicit close.

**7. Vì sao gọi `SIGTERM` có thể cho thấy `@PreDestroy`, nhưng `SIGKILL` thì không thể dùng để kiểm chứng?** Vì `SIGTERM` thường cho JVM cơ hội chạy shutdown sequence, còn `SIGKILL` kết thúc tiến trình ngay.

**8. Khi nào giữ factory mặc định thay vì ép context class?** Khi classpath và `WebApplicationType` đã biểu diễn đúng ứng dụng, và bạn không có nhu cầu custom lifecycle/context thực sự. Factory mặc định giảm nguy cơ chọn sai loại context.

## 12. Checklist hoàn thành bài

- [ ] Tạo project Java 17, Spring Boot 3.3.x với Spring Web và chạy thành công.
- [ ] Ghi được `LAB_APPLICATION_READY` và loại context servlet thực tế sau `run`.
- [ ] Kiểm chứng `GET /probe` trả HTTP 200 và JSON phù hợp.
- [ ] Kết thúc JVM theo cách hợp lệ và ghi lại `LAB_CONTEXT_CLOSED`, `LAB_PRE_DESTROY`.
- [ ] Phân biệt được hook JVM, close context, destroy bean và graceful server shutdown.
- [ ] Chạy ví dụ CLI `setRegisterShutdownHook(false)` và chứng minh explicit `close()` kích hoạt destroy.
- [ ] Giải thích ba web types và context mặc định, cùng tác dụng của `setApplicationContextFactory(...)`.
- [ ] So sánh kết quả khi dùng `ofContextClass(...)` và factory delegate `DEFAULT`.
- [ ] Mô tả nguyên nhân một lỗi mismatch context/web type và một tình huống shutdown không chạy.
- [ ] Nêu rõ cơ chế shutdown không bảo đảm cleanup khi bị kết thúc cưỡng bức.

## 13. Tài liệu chính thức để đối chiếu

- Spring Boot 3.3 — SpringApplication và Application Exit: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — API SpringApplication (`setRegisterShutdownHook`, `setApplicationContextFactory`): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 — API ApplicationContextFactory: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationContextFactory.html
- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Framework — vòng đời bean và callback destroy: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html

Khi chuyển sang Spring Boot 4.x, kiểm tra lại package, dependencies và cấu hình theo tài liệu 4.x đang dùng; nguyên tắc **factory tạo context, SpringApplication quản lý startup, shutdown hook/explicit close kích hoạt teardown** vẫn là trục chính để phân tích.