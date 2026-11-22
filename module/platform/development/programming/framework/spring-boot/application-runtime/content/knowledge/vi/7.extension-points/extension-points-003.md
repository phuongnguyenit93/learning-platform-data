# Đăng ký ApplicationContextInitializer bằng API hoặc META-INF/spring.factories

**Chủ đề:** Spring Boot Application Runtime → Điểm mở rộng. Bài này hướng dẫn đăng ký `ApplicationContextInitializer` theo hai cơ chế được Spring Boot hỗ trợ: dùng API `SpringApplication.addInitializers(...)` khi tạo ứng dụng và khai báo `META-INF/spring.factories` để tự động nạp từ classpath. Trọng tâm là **thời điểm thực thi**, **cách viết class hợp lệ**, **cách cấu hình cho một ứng dụng hoặc thư viện dùng chung**, **thứ tự**, **đóng gói**, **bằng chứng chạy** và **lỗi thường gặp**.

Các ví dụ sử dụng **Java 17+**, **Spring Boot 3.3.x**, Maven và Spring MVC. Chúng được thiết kế để biên dịch khi tạo project với `Spring Web` từ Spring Initializr và giữ đúng dependency/plugin mà Initializr sinh ra. Nếu dự án dùng một dòng Spring Boot khác, hãy kiểm tra lại tài liệu đúng phiên bản trước khi sao chép package và metadata.

## 1. ApplicationContextInitializer là gì?

`ApplicationContextInitializer<C extends ConfigurableApplicationContext>` là một điểm mở rộng của Spring Framework. Phương thức chính là:

~~~java
void initialize(C applicationContext);
~~~

Spring Boot gọi initializer **sau khi tạo và chuẩn bị `ApplicationContext`, nhưng trước khi nạp bean definitions chính và trước khi refresh context**. Khi initializer chạy, context đã có `Environment`; tuy nhiên nhiều bean ứng dụng chưa được đăng ký, không có bảo đảm `BeanFactory` đã hoàn tất xử lý cấu hình hoặc các singleton đã khởi tạo.

Một initializer phù hợp để:

- Bổ sung hoặc sắp xếp `PropertySource` có ý nghĩa với quá trình nạp/khởi tạo bean tiếp theo.
- Cấu hình đặc tính của context trong phạm vi API hỗ trợ.
- Đăng ký `BeanFactoryPostProcessor` sớm bằng `context.addBeanFactoryPostProcessor(...)` nếu cần xử lý bean definitions ở đúng phase.
- Gắn thông tin bootstrap nhỏ, độc lập với các bean nghiệp vụ.
- Tạo cấu hình dùng chung cho nhiều ứng dụng khi đóng gói thành thư viện.

Không dùng initializer để làm công việc thường xuyên của controller/service, chạy job dài, query repository đã tạo, hoặc gọi `getBean(...)` để truy cập singleton ứng dụng. Những việc đó thuộc giai đoạn sau khi container đã refresh.

### 1.1. Vị trí của initializer trong chuỗi khởi động

~~~text
main()
   |
   v
new SpringApplication(MyApplication.class)
   |        +-- nạp các initializer khai báo qua spring.factories
   |        +-- nhận thêm initializer qua API addInitializers(...)
   v
springApplication.run(args)
   |
   +-- chuẩn bị Environment, profiles, command-line properties
   +-- tạo ConfigurableApplicationContext
   +-- chuẩn bị context và gắn Environment
   +-- chạy ApplicationContextInitializer.initialize(context)
   +-- ApplicationContextInitializedEvent
   +-- nạp bean definitions từ primary sources
   +-- ApplicationPreparedEvent
   +-- refresh ApplicationContext
   |     +-- xử lý bean definitions và post-processors
   |     +-- tạo các singleton cần thiết
   |     +-- ContextRefreshedEvent
   +-- ApplicationStartedEvent
   +-- ApplicationRunner / CommandLineRunner
   +-- ApplicationReadyEvent
   v
ứng dụng phục vụ HTTP / xử lý công việc
~~~

Đây là chuỗi trọng yếu theo Spring Boot 3.3; các thao tác nội bộ có thể thay đổi giữa phiên bản. Điểm chắc chắn để kiểm chứng là: initializer chạy **trước `ApplicationContextInitializedEvent`**, trước `ApplicationPreparedEvent` và **trước `refresh()`**. Vì vậy một `@Bean` bình thường không phải cơ chế đăng ký đáng tin cậy cho initializer cần hoạt động trong cùng lượt startup: `@Bean` chỉ được tạo khi Spring đang xử lý context ở thời điểm sau.

### 1.2. Hai cách đăng ký

| Tiêu chí | Qua `SpringApplication` API | Qua `META-INF/spring.factories` |
|---|---|---|
| Điểm đăng ký | Trong `main()` hoặc code tạo `SpringApplication` | Resource nằm trong JAR/module trên runtime classpath |
| Cú pháp cốt lõi | `app.addInitializers(new MyInitializer())` | `org.springframework.context.ApplicationContextInitializer=...MyInitializer` |
| Phạm vi | Instance `SpringApplication` được cấu hình | Các `SpringApplication` có thể thấy resource trên classpath |
| Cách tạo instance | Code tạo đối tượng trực tiếp | Spring Boot nạp lớp và tạo instance theo hợp đồng factories |
| Phù hợp | Cấu hình riêng của một ứng dụng, lựa chọn theo runtime | Thư viện dùng chung, integration module tự đăng ký |
| Kiểm chứng | Đặt marker log, kiểm tra `getInitializers()` và kết quả | Kiểm tra `spring.factories` trong artifact/classpath, log và kết quả |
| Bẫy hay gặp | Gọi `addInitializers` sau `run`, dùng nhầm `setInitializers` | Sai key, sai FQCN, thiếu file trong JAR, constructor không hợp lệ |

Cả hai cuối cùng đều dẫn đến việc Spring Boot gọi `initialize(...)` trên một đối tượng initializer. Chúng khác nhau chủ yếu ở nơi cấu hình và cách initializer được phát hiện.

## 2. Hợp đồng và giới hạn của initialize(...)

Một initializer hợp lệ, có thể được dùng ở thời điểm context chưa refresh:

~~~java
package com.example.initializerlab;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;

public final class SimpleInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        System.out.println("LAB_SIMPLE_INITIALIZER");
    }
}
~~~

Interface generic được chọn là `ConfigurableApplicationContext` vì nó dùng được với cả servlet, reactive và non-web context. Nếu bạn dùng tham số kiểu quá chuyên biệt, ví dụ chỉ chấp nhận một subclass servlet context, việc ứng dụng chạy với context khác có thể gây lỗi kiểu/khởi động; hãy kiểm tra đúng `WebApplicationType` và context thực tế.

**Những gì có thể tin vào ở thời điểm này:**

1. Có một `ConfigurableApplicationContext` do Spring Boot tạo.
2. Có thể lấy `context.getEnvironment()` để đọc hoặc bổ sung nguồn cấu hình đã chuẩn bị.
3. Có thể đăng ký thêm một số hook liên quan BeanFactory trước refresh.
4. Chưa được xem đây là một container đã fully initialized; thông thường không gọi `context.getBean(MyService.class)`.
5. Không gọi `context.refresh()` bên trong initializer: `SpringApplication` sẽ điều phối refresh; gọi sớm có thể khiến cấu hình bị xử lý lệch thứ tự.
6. Không giả định tất cả sự kiện startup đã phát hoặc embedded server đã lắng nghe cổng.

Cần phân biệt rõ thay đổi property **ở thời điểm initializer** với thay đổi property **rất sớm** khi Spring Boot đang xác định config-data locations. Một số quyết định cấu hình (đặc biệt việc tìm và tải `application.properties` / `application.yml`) đã diễn ra trước khi initializer được gọi. Nếu phải can thiệp giai đoạn chuẩn bị `Environment` và config-data, hãy nghiên cứu `EnvironmentPostProcessor` hoặc cơ chế bootstrap phù hợp; không dùng initializer để thay đổi muộn `spring.config.location` rồi kỳ vọng Spring tự nạp lại toàn bộ.

## 3. Dựng project mẫu chạy được

Tạo dự án bằng Spring Initializr với lựa chọn:

- Project: **Maven**, Language: **Java**, Java: **17**.
- Group: `com.example`; Artifact: `initializer-lab`; package: `com.example.initializerlab`.
- Spring Boot: **3.3.x**; dependency **Spring Web**.
- Packaging: **Jar**.

Giữ nguyên Maven Wrapper và `pom.xml` sinh ra. Tạo các file sau:

~~~text
initializer-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/initializerlab/
    InitializerLabApplication.java
    ApiInitializer.java
    FactoriesInitializer.java
    InitializerController.java
  src/main/resources/
    application.properties
    META-INF/
      spring.factories
~~~

Mỗi public Java class nằm trong file trùng tên và package đúng như mã. Không dùng `javac` độc lập chỉ với các file Java vì class cần dependency Spring Boot/MVC từ Maven; dùng Maven Wrapper để biên dịch và chạy. Các lớp initializer **không** cần `@Component` và không cần `@Bean` để được Spring Boot nhận theo hai cách đăng ký này.

### 3.1. Main class: đăng ký qua API

File `src/main/java/com/example/initializerlab/InitializerLabApplication.java`:

~~~java
package com.example.initializerlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class InitializerLabApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(InitializerLabApplication.class);

        // Cach 1: them initializer rieng cho SpringApplication nay.
        application.addInitializers(new ApiInitializer());

        // Listener duoc them som de quan sat context truoc refresh.
        application.addListeners(
                (ApplicationListener<ApplicationContextInitializedEvent>) event -> {
                    var env = event.getApplicationContext().getEnvironment();
                    System.out.println("LAB_CONTEXT_INITIALIZED api="
                            + env.getProperty("lab.api.initialized", "false")
                            + " factories="
                            + env.getProperty("lab.factories.initialized", "false"));
                });

        application.run(args);
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("LAB_APPLICATION_READY");
    }
}
~~~

**Điểm cần chú ý:** `new SpringApplication(...)` cho phép cấu hình trước khi `run()`. Việc viết tắt `SpringApplication.run(InitializerLabApplication.class, args)` vẫn đúng cho app không cần cấu hình thêm, nhưng trong ví dụ này ta cần giữ instance `SpringApplication` để đăng ký initializer.

`ApplicationContextInitializedEvent` là dấu mốc xảy ra **sau các initializer nhưng trước khi các primary bean definitions được nạp**. Listener được đăng ký trực tiếp trên `SpringApplication` vì một listener tạo bằng `@Bean` có thể xuất hiện quá muộn cho sự kiện sớm này. `ApplicationReadyEvent` là mốc sau refresh và sau runners; log của nó phục vụ đối chứng.

### 3.2. Initializer thứ nhất: đăng ký trực tiếp qua API

File `src/main/java/com/example/initializerlab/ApiInitializer.java`:

~~~java
package com.example.initializerlab;

import java.util.Map;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.Ordered;
import org.springframework.core.env.MapPropertySource;

public final class ApiInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext>,
                   Ordered {

    @Override
    public int getOrder() {
        return 0;
    }

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        System.out.println("LAB_API_INITIALIZER");

        context.getEnvironment().getPropertySources().addLast(
                new MapPropertySource(
                        "labApiSource",
                        Map.of("lab.api.initialized", "true")));
    }
}
~~~

`getOrder() == 0` thể hiện initializer có độ ưu tiên cao hơn initializer nhận giá trị `10` ở ví dụ tiếp theo: trong thứ tự `Ordered`, **số nhỏ chạy trước**. Thứ tự đối với các initializer framework khác có thể xen kẽ; chỉ so sánh hai initializer của lab với nhau.

`MapPropertySource` là một nguồn giá trị được bổ sung vào `Environment` trước khi container khởi tạo bean ứng dụng. Dùng `addLast(...)` để nguồn cấu hình mẫu có mức ưu tiên thấp hơn các property source đã được chuẩn bị. Nếu muốn chủ động override nhiều nguồn hiện có thì `addFirst(...)` có độ ưu tiên cao hơn, nhưng cần thiết kế và giải thích chính sách precedence rõ ràng; không thay cấu hình người vận hành một cách âm thầm.

Giá trị `"true"` ở đây là chuỗi, và controller sẽ đọc lại chuỗi đó. Nó không chứng minh mọi dependency đã init; nó chứng minh initializer thực sự được gọi và đã bổ sung một thuộc tính có thể thấy ở giai đoạn sau.

### 3.3. Initializer thứ hai: đăng ký tự động qua spring.factories

File `src/main/java/com/example/initializerlab/FactoriesInitializer.java`:

~~~java
package com.example.initializerlab;

import java.util.Map;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.Ordered;
import org.springframework.core.env.MapPropertySource;

public final class FactoriesInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext>,
                   Ordered {

    public FactoriesInitializer() {
        // Constructor khong tham so cho co che factories loading.
    }

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        System.out.println("LAB_FACTORIES_INITIALIZER");

        context.getEnvironment().getPropertySources().addLast(
                new MapPropertySource(
                        "labFactoriesSource",
                        Map.of("lab.factories.initialized", "true")));
    }
}
~~~

Khi nạp qua `spring.factories`, Spring Boot cần tạo đối tượng initializer. Trong ví dụ này, class là `public`, có public no-argument constructor và không phụ thuộc một bean ứng dụng chưa được tạo. Không tiêm `@Autowired SomeService` vào constructor của initializer dạng factories rồi chờ Spring container cấp service như một bean, bởi việc tạo instance cho cơ chế factories diễn ra trước khi các bean thường sẵn sàng.

### 3.4. Khai báo đúng META-INF/spring.factories

Tạo **đúng đường dẫn và tên file**:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Nội dung file:

~~~properties
org.springframework.context.ApplicationContextInitializer=com.example.initializerlab.FactoriesInitializer
~~~

Đây là định dạng Java `.properties`. **Key** là tên đầy đủ của interface `org.springframework.context.ApplicationContextInitializer`; **value** là tên lớp đầy đủ của implementation. Đừng viết `ApplicationContextInitializer=...` rút gọn, đừng dùng slash thay dấu chấm trong FQCN, và đừng đặt resource ở cạnh file Java hoặc trong `src/main/java`.

Khi cần khai báo nhiều initializer dưới cùng một key, tách các class bằng dấu phẩy. Ví dụ cú pháp:

~~~properties
org.springframework.context.ApplicationContextInitializer=com.example.initializerlab.FirstInitializer,com.example.initializerlab.SecondInitializer
~~~

Hai class `FirstInitializer` và `SecondInitializer` trong đoạn cú pháp trên chỉ minh họa **định dạng danh sách**; chúng không thuộc project mẫu và không cần thêm vào `spring.factories` khi chạy lab. Nếu tổ chức file trên nhiều dòng với ký tự `\` của Java properties, hãy đảm bảo dấu continuation và khoảng trắng đúng; với bài này một dòng là dễ kiểm tra nhất.

Nhiều thư viện JAR có thể cung cấp `META-INF/spring.factories` riêng. Spring Boot sử dụng factory loading từ classpath để tìm các khai báo phù hợp và tạo instance. Đây không phải component scan, cũng không phải Java `ServiceLoader` thuần. Nếu một initializer nằm trong dependency JAR và resource `spring.factories` nằm trong chính JAR đó, ứng dụng dùng dependency có thể nhận initializer mà không phải sửa `main()`.

### 3.5. Controller xác nhận hiệu quả của cả hai initializer

File `src/main/java/com/example/initializerlab/InitializerController.java`:

~~~java
package com.example.initializerlab;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InitializerController {
    private final Environment environment;

    public InitializerController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/initializer-status")
    public InitializerStatus status() {
        return new InitializerStatus(
                environment.getProperty("lab.api.initialized", "false"),
                environment.getProperty("lab.factories.initialized", "false"));
    }

    public record InitializerStatus(String api, String factories) {
    }
}
~~~

`Environment` được inject vào bean controller trong quá trình refresh. Khi endpoint gọi, nó đọc hai giá trị do initializer đặt trước đó. Kiểu `record` của Java 17 được Jackson trong Spring Web serialize thành JSON. Với tất cả file đúng và hai initializer chạy, HTTP body chứa:

~~~json
{"api":"true","factories":"true"}
~~~

Thứ tự khóa JSON không phải tiêu chí quan trọng; chỉ cần hai khóa và giá trị đúng. Nếu ứng dụng được truyền command-line property cùng tên để override nguồn `addLast`, body sẽ phản ánh giá trị hiệu lực của `Environment`; khi test cơ chế đăng ký, không truyền các override đó.

### 3.6. Cấu hình ứng dụng

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=initializer-lab
server.port=8080
~~~

Không tự thêm hai marker vào file này, vì mục tiêu là chứng minh chúng được initializer đưa vào `Environment`. Chỉ cần dependency Spring Web; Spring Boot tạo web server nhúng và HTTP endpoint cho ta bằng chứng độc lập với log.

## 4. Chạy ứng dụng và kiểm chứng các mốc

### 4.1. Maven Wrapper

Ở thư mục gốc project, trên Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd spring-boot:run
~~~

Cần dùng Java 17 hoặc phiên bản tương thích đã chọn. Maven Wrapper sẽ dùng Maven và dependency theo project. Nếu cổng 8080 đã có process khác nghe, dừng process đó hoặc đổi `server.port` cho lab và dùng cổng mới trong câu lệnh `curl`.

Khi chạy, lọc console theo chuỗi bắt đầu bằng `LAB_`. Bằng chứng tương đối được kỳ vọng là:

~~~text
LAB_API_INITIALIZER
LAB_FACTORIES_INITIALIZER
LAB_CONTEXT_INITIALIZED api=true factories=true
LAB_APPLICATION_READY
~~~

Các log framework khác có thể xen vào. Marker API phải đứng trước marker factories trong lab vì hai class có `Ordered` là `0` và `10`; marker event initialized chỉ xuất hiện sau khi cả hai hoàn tất. `LAB_APPLICATION_READY` nằm sau refresh và sau các runner. Nếu dùng thêm initializer khác, log của chúng có thể xen giữa các marker nhưng không thay đổi mục tiêu đối chiếu của hai initializer trong bài.

### 4.2. Kiểm tra kết quả bằng HTTP

Mở terminal mới, giữ terminal đang chạy app hoạt động:

~~~bash
curl -i "http://localhost:8080/initializer-status"
~~~

Trên PowerShell có thể dùng `curl.exe -i "http://localhost:8080/initializer-status"` để tránh alias của `curl`. Kết quả mong đợi có HTTP status `200` và JSON chứa `api=true`, `factories=true` dưới dạng string, ví dụ:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"api":"true","factories":"true"}
~~~

Header như `Date` hoặc `Content-Length` thay đổi theo runtime. Một số serializer có thể thay thứ tự property. Quan sát HTTP chứng minh cả hai nguồn đã có mặt ở giai đoạn controller sử dụng; log cho biết initializer đã được gọi trước context refresh.

### 4.3. Đóng gói và kiểm tra spring.factories nằm trong JAR

Dừng ứng dụng trước để tránh tranh cổng. Chạy:

~~~bash
./mvnw clean package
jar tf target/initializer-lab-0.0.1-SNAPSHOT.jar
~~~

Windows PowerShell thay `./mvnw` bằng `./mvnw.cmd`. Tên file JAR ở ví dụ chỉ đúng nếu project dùng artifact `initializer-lab` và version `0.0.1-SNAPSHOT`; nếu khác hãy xem file JAR thực tế trong thư mục `target`.

Một Spring Boot executable JAR đúng sẽ chứa resource ở đường dẫn kiểu:

~~~text
BOOT-INF/classes/META-INF/spring.factories
BOOT-INF/classes/com/example/initializerlab/FactoriesInitializer.class
BOOT-INF/classes/com/example/initializerlab/ApiInitializer.class
~~~

`jar tf` chỉ liệt kê tên các entry, không tự in nội dung file. Trong project Maven, cũng có thể mở `target/classes/META-INF/spring.factories` sau build để so sánh nội dung resource đã được copy. Nếu không có file metadata trong JAR, lần chạy bằng `java -jar` sẽ không tìm được initializer từ cách đăng ký đó dù class Java vẫn có thể tồn tại.

Chạy file JAR:

~~~bash
java -jar target/initializer-lab-0.0.1-SNAPSHOT.jar
~~~

Gọi lại `GET /initializer-status` và đối chiếu log. Nếu chạy Maven plugin thành công nhưng JAR thất bại, kiểm tra việc resources có được đóng gói, classpath khi chạy executable JAR và thao tác shading/repackaging của dự án.

## 5. Ba thí nghiệm đối chứng: API-only, factories-only và cả hai

Mục tiêu là chứng minh hai đường đăng ký hoạt động độc lập thay vì chỉ thấy kết quả `true/true` và đoán.

### 5.1. Trường hợp A — Cả hai đường đăng ký đều có

Giữ nguyên `main()` có `application.addInitializers(new ApiInitializer())` và giữ file `META-INF/spring.factories`. Khi chạy, log có cả `LAB_API_INITIALIZER` và `LAB_FACTORIES_INITIALIZER`. HTTP body:

~~~json
{"api":"true","factories":"true"}
~~~

Kết luận: cùng một instance `SpringApplication` có thể nhận initializer từ nhiều nguồn và áp dụng chúng theo thứ tự được sắp xếp.

### 5.2. Trường hợp B — Chỉ dùng API

Trong **bản copy của project lab**, tạm loại file `src/main/resources/META-INF/spring.factories` khỏi nguồn build (không cần xóa class `FactoriesInitializer`), thực hiện clean build rồi chạy lại. Có thể đổi tên tạm resource thành một tên không phải `spring.factories`; cần xác minh file cũ không còn nằm trong `target/classes` sau `clean`.

Câu lệnh:

~~~bash
./mvnw clean package
java -jar target/initializer-lab-0.0.1-SNAPSHOT.jar
curl -i "http://localhost:8080/initializer-status"
~~~

Để chạy `curl` cần một terminal khác vì `java -jar` đang phục vụ. Log vẫn có `LAB_API_INITIALIZER` nhưng không có marker factories; HTTP body kỳ vọng:

~~~json
{"api":"true","factories":"false"}
~~~

Kết luận: class Java có mặt trên classpath **không đủ** để Spring Boot tự nhận nó làm initializer; cần đường đăng ký tương ứng.

### 5.3. Trường hợp C — Chỉ dùng spring.factories

Khôi phục file `META-INF/spring.factories`. Trong `main()`, bỏ riêng dòng `application.addInitializers(new ApiInitializer())`, giữ lại listener để quan sát và gọi `run`. Sau clean build, `spring.factories` vẫn làm Spring Boot nạp `FactoriesInitializer` mà không cần thêm code đăng ký qua API. HTTP body kỳ vọng:

~~~json
{"api":"false","factories":"true"}
~~~

Log chỉ có marker factories; event initialized sẽ in `api=false factories=true`. Sau thí nghiệm, khôi phục dòng `addInitializers` để project trở về trạng thái có cả hai đường.

### 5.4. Bảng bằng chứng cần lưu

| Lần chạy | `addInitializers` | `spring.factories` | Marker API | Marker factories | HTTP `api/factories` |
|---|---|---|---|---|---|
| A | Có | Có | Có | Có | `true / true` |
| B | Có | Không | Có | Không | `true / false` |
| C | Không | Có | Không | Có | `false / true` |

Đây là **kết quả kỳ vọng** của lab trong điều kiện không có các property override và không có dependency khác chứa chính initializer thử nghiệm. Khi làm thật, ghi log và response nhận được; nếu khác kỳ vọng, điều tra packaging và runtime classpath trước khi sửa các bean nghiệp vụ.

## 6. Thứ tự initializer: Ordered và @Order

Spring Boot sắp xếp tập initializer với cơ chế tương thích `Ordered`/`@Order`. Giá trị số **nhỏ hơn** có độ ưu tiên **cao hơn**. Trong lab:

~~~text
ApiInitializer       order = 0
FactoriesInitializer order = 10

Thứ tự giữa hai initializer: API -> FACTORIES
~~~

Có thể khai báo `@Order(5)` trên lớp khi muốn cung cấp metadata thứ tự thay vì implement `Ordered`. Không cần dùng cả hai cho một class đơn giản. Khi cùng số thứ tự hoặc không khai báo thứ tự, đừng dựa vào thứ tự không được hợp đồng bảo đảm; nếu initializer A cần dữ liệu do B tạo, hãy đặt thứ tự rõ ràng hoặc gộp logic vào một initializer.

**Quy tắc với PropertySource:** nhiều initializer gọi `addFirst(...)` trên cùng tên property có thể làm precedence cuối cùng khác với trực giác: initializer chạy sau có thể đưa nguồn mới lên đầu và override giá trị của initializer chạy trước. Trong lab mỗi initializer dùng tên source và property riêng biệt, đồng thời `addLast(...)`, nên không tạo xung đột. Ở sản phẩm thật, lưu rõ thứ tự, tên nguồn và chính sách override để dễ chẩn đoán.

Không giả định thứ tự initializer do chính bạn đăng ký được quyết định hoàn toàn bởi “API trước, factories sau”. `Ordered` mới là công cụ rõ ràng khi hai cơ chế cùng xuất hiện.

## 7. addInitializers, setInitializers và SpringApplicationBuilder

### 7.1. addInitializers(...) thêm vào tập có sẵn

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addInitializers(new MyInitializer());
app.run(args);
~~~

Đây là **snippet** giả định đã có `MyApplication` và `MyInitializer` trong project. `addInitializers(...)` bổ sung initializer cho `SpringApplication` hiện tại. Nếu muốn một initializer được áp dụng cho nhiều app, gọi phương thức khi tạo từng instance hoặc đóng gói theo cơ chế factories.

### 7.2. setInitializers(...) đặt lại tập initializer

`SpringApplication.setInitializers(Collection<? extends ApplicationContextInitializer<?>>)` đặt danh sách initializer trên instance. Nó có thể thay thế initializer được framework hoặc dependency cung cấp trước đó; dùng thiếu cân nhắc sẽ bỏ cấu hình quan trọng. Khi mục đích chỉ là bổ sung một initializer, **ưu tiên `addInitializers(...)`**.

`SpringApplication.getInitializers()` cho phép xem tập initializer đã đăng ký trên instance ở thời điểm quan sát. Nó hữu ích khi debug, nhưng một danh sách class có mặt không phải bằng chứng chắc chắn `initialize(...)` đã chạy thành công; cần marker hoặc hiệu ứng thực tế.

### 7.3. Cách dùng SpringApplicationBuilder

Nếu project vốn dùng builder, có thể đăng ký tương đương:

~~~java
new SpringApplicationBuilder(MyApplication.class)
        .initializers(new MyInitializer())
        .run(args);
~~~

Đây là ví dụ cú pháp đặt trong `main()` khi đã có các class và import cần thiết. Với `SpringApplicationBuilder`, initializer được thêm cho application do builder tạo. Không cần tạo một instance `SpringApplication` khác chỉ để dùng `addInitializers` song song, vì như vậy có thể vô tình chạy hai ứng dụng.

## 8. Đặt initializer trong một thư viện JAR tái sử dụng

Giả sử có một module `runtime-common` chứa `CommonContextInitializer` và resource:

~~~text
runtime-common/
  src/main/java/com/example/common/CommonContextInitializer.java
  src/main/resources/META-INF/spring.factories
~~~

Ví dụ `spring.factories` của thư viện:

~~~properties
org.springframework.context.ApplicationContextInitializer=com.example.common.CommonContextInitializer
~~~

Sau khi thư viện đóng gói, service A và B chỉ cần đưa JAR `runtime-common` vào **runtime classpath**. Spring Boot có thể thấy resource và tải initializer từ JAR mà không cần chỉnh từng `main()`. Đây là cơ chế hữu ích cho module infrastructure, nhưng cũng có tác dụng toàn cục trong phạm vi ứng dụng dùng thư viện.

**Quy tắc thiết kế thư viện:**

1. Initializer phải đủ độc lập để chạy trước khi các application beans tồn tại.
2. Constructor dùng cho factories nên đơn giản và có thể tạo từ cơ chế Spring factories loading; không phụ thuộc container injection vào constructor như một `@Component`.
3. Dùng `Ordered` nếu cần thứ tự ổn định tương đối với các initializer khác.
4. Hạn chế side effect: không tự tạo kết nối mạng dài, ghi file tùy ý, mở thread sống lâu hoặc in secrets.
5. Cung cấp công tắc bật/tắt thông qua nguồn cấu hình có sẵn nếu initializer có tác động đáng kể, nhưng hiểu rằng bản thân initializer đã được nạp trước khi nó quyết định có chạy logic hay không.
6. Đảm bảo JAR giữ `META-INF/spring.factories` khi shade/merge hoặc repackaging. Một số cấu hình build có thể ghi đè resource của dependency khác thay vì hợp nhất các factory entries.
7. Khi cần hỗ trợ nhiều bản Spring Boot, kiểm tra API và quá trình loading của từng bản; không giả định metadata dành cho auto-configuration giống metadata initializer.

**Không nhầm loại metadata:** Spring Boot 3.x dùng `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` cho đăng ký auto-configuration. `ApplicationContextInitializer` vẫn sử dụng `META-INF/spring.factories` theo hợp đồng được mô tả ở đây. Chuyển initializer sang `AutoConfiguration.imports` sẽ không đăng ký đúng loại điểm mở rộng này.

## 9. Tình huống khởi tạo context không thành công

Nếu `initialize(...)` ném exception, `SpringApplication` có thể kết thúc startup trước khi context refresh, và bạn sẽ không thấy marker ready. Ví dụ thay nội dung phương thức `initialize(...)` trong một bản thử riêng bằng đoạn:

~~~java
@Override
public void initialize(ConfigurableApplicationContext context) {
    System.out.println("LAB_INITIALIZER_BEFORE_FAILURE");
    throw new IllegalStateException("LAB_INTENTIONAL_INITIALIZER_FAILURE");
}
~~~

Đây là **snippet thay thế phương thức**, không phải file độc lập. Chạy bản thử trong môi trường lab, kiểm tra dòng `LAB_INTENTIONAL_INITIALIZER_FAILURE` trong stack trace. Startup thất bại do initializer **khác với** lỗi bean init (`@PostConstruct`) xảy ra trong refresh và cũng khác lỗi runner sau refresh.

Trong trường hợp lỗi sớm như thế, một `@EventListener` trong bean ứng dụng có thể chưa được tạo để nhận sự kiện lỗi. Nếu cần quan sát `ApplicationFailedEvent`, đăng ký `ApplicationListener` với `SpringApplication.addListeners(...)` trước khi `run(...)` và dùng một listener ít phụ thuộc.

**Không** giải quyết bằng cách bắt mọi exception và tiếp tục im lặng, vì lúc đó context có thể thiếu cấu hình quan trọng mà ứng dụng vẫn khởi động. Chỉ xử lý những lỗi thật sự có đường fallback được định nghĩa.

## 10. Chẩn đoán khi initializer không chạy

| Hiện tượng | Nguyên nhân thường gặp | Bước xác minh |
|---|---|---|
| Không thấy marker của initializer API | Quên gọi `addInitializers` trước `run` hoặc chạy nhầm main class | Tìm lời gọi trong main được chạy, so lệnh và log |
| Không thấy marker factories | Sai key `ApplicationContextInitializer` hoặc sai đường dẫn resource | Mở `src/main/resources/META-INF/spring.factories`, xem output build |
| Chạy qua Maven được nhưng JAR không có marker | Resource/class không nằm trong packaged JAR hoặc process chạy artifact cũ | `jar tf` để tìm `BOOT-INF/classes/META-INF/spring.factories`; clean build |
| `ClassNotFoundException` / lỗi tạo factory | FQCN sai, class không có ở runtime classpath, constructor không tương thích | So package/class, dependency scope, stack trace gốc |
| `ClassCastException` hoặc lỗi context type | Dùng generic initializer quá cụ thể cho context servlet/reactive/none khác thực tế | Xem `WebApplicationType`, context class và generic bound |
| Có marker nhưng property không thấy trong controller | PropertySource sai tên/key, thay đổi trên Environment khác, bị source ưu tiên cao override | In source names và đọc `Environment.getProperty(...)` |
| Hai initializer chạy trùng logic | Đăng ký cùng một hành vi qua cả API và factories | Kiểm tra `getInitializers()`, classpath, log và side effect |
| Initializer được tạo nhưng fail trước marker cuối | Exception trong constructor hoặc `initialize(...)` | Đọc `Caused by` và marker ngay trước lỗi |
| Gọi `getBean(...)` trong initializer báo context chưa active | BeanFactory/context chưa refresh | Chuyển code sang bean, post-processor, runner hoặc event phù hợp |
| Sửa `spring.config.location` trong initializer nhưng config không reload | Config data đã xử lý sớm hơn initializer | Dùng cơ chế môi trường sớm phù hợp |
| Thứ tự property override bất ngờ | `addFirst`, `addLast` hoặc `Ordered` khác suy nghĩ | Ghi precedence và thứ tự khởi tạo, dùng tên source riêng |
| Không thấy initializer khi chạy test hoặc non-web mode | Test bootstrap khác hoặc initializer chỉ tương thích web context | Kiểm tra cách tạo `SpringApplication`, test framework và context type |

Nếu bắt buộc đặt breakpoint, nên dừng ở `SpringApplication.applyInitializers(...)`, `ApiInitializer.initialize(...)` và `FactoriesInitializer.initialize(...)`; kiểm tra `ApplicationContext` chưa refresh và `Environment` có nguồn được thêm. Không cần dò toàn bộ bean runtime để xác nhận một initializer đã được gọi.

## 11. Phân biệt initializer với các điểm mở rộng lân cận

| Cơ chế | Thời điểm điển hình | Dùng cho | Không nên kỳ vọng |
|---|---|---|---|
| `ApplicationContextInitializer` | Context đã tạo, trước bean definitions chính và refresh | Sửa context/Environment, đăng ký hooks sớm | Truy cập service/repository đã init |
| `EnvironmentPostProcessor` | Trong giai đoạn chuẩn bị Environment | Bổ sung/điều chỉnh nguồn config sớm theo hợp đồng Boot | Truy cập ApplicationContext đầy đủ |
| `BeanFactoryPostProcessor` | Trong refresh, trước bean singleton thường được tạo | Điều chỉnh metadata bean definitions | Vận hành logic request |
| `BeanPostProcessor` | Khi từng bean instance được tạo/khởi tạo | Injection, init hooks, proxy, wrap bean | Được gọi trước khi tạo context |
| `ApplicationListener<ApplicationContextInitializedEvent>` | Sau khi tất cả initializer được áp dụng | Quan sát context initialized | Coi là ready cho HTTP |
| `ApplicationRunner` | Sau refresh, trước `ApplicationReadyEvent` | Công việc cấp ứng dụng cần hoàn tất trước ready | Can thiệp bước tạo context đã qua |
| `ApplicationReadyEvent` | Sau runners | Ghi nhận mốc cuối startup | Chạy công việc dài mà vẫn bảo đảm traffic bị chặn |

**Vì sao không thay tất cả bằng `@Component`?** Component scanning xảy ra trong quá trình xử lý cấu hình và refresh. Một class `@Component` có thể được tạo thành bean sau đó, nhưng điều này không tự đưa nó vào tập initializer mà `SpringApplication` đã dùng trước refresh. Nếu mục tiêu là can thiệp trước refresh, cần đăng ký đúng vào `SpringApplication`.

**Vì sao không thay `spring.factories` bằng `@AutoConfiguration`?** Auto-configuration cấu hình bean definitions trong refresh theo điều kiện. Initializer chạy trước để thay đổi context. Hai cơ chế giải quyết các pha khác nhau, dù cùng nằm trong thư viện Spring Boot.

## 12. Lưu ý vận hành và thiết kế đúng

- **Idempotency:** initializer nên chịu được việc nhiều context được tạo trong test, restart, parent/child context hoặc nhiều app trong một JVM. Nếu cần idempotent, kiểm tra tên `PropertySource` đã có trước khi thêm hoặc dùng guard phù hợp.
- **Đa context:** cùng initializer có thể áp dụng nhiều lần trên các instance context khác nhau; không dùng mutable static state làm bằng chứng chắc chắn toàn JVM chỉ khởi tạo một lần.
- **Phụ thuộc lớp:** factory được load theo tên lớp đầy đủ, nên thay package/class phải cập nhật metadata. Build vẫn có thể thành công nếu metadata trỏ tới một class không tồn tại, và lỗi chỉ lộ khi chạy.
- **Resource merging:** khi đóng gói fat JAR bằng công cụ khác Boot Maven plugin, giữ đầy đủ `spring.factories` của các dependency; mất metadata có thể làm hệ thống thay đổi dù không đổi source Java.
- **Property precedence:** source thêm vào `Environment` có vị trí ưu tiên. Ở ví dụ dùng `addLast` nhằm không override các source có trước; trong sản phẩm thật cần xác định nguồn dữ liệu nào là chủ sở hữu.
- **Thời gian startup:** không chạy database migrations, gọi HTTP chậm hoặc đợi vô hạn trong initializer vì nó chặn refresh. Các tác vụ hậu refresh có thể đặt trong runner với timeout và readiness đúng.
- **Bảo mật:** không in toàn bộ `Environment` hay các secrets ra log. Nếu cần marker, chỉ log tên source, boolean không nhạy cảm, context class và thời điểm.
- **Khả năng kiểm thử:** một initializer chạy đúng cần có bằng chứng đầu vào/đầu ra ổn định. Marker log và HTTP property ở lab giúp xác minh mà không phụ thuộc số lượng bean nội bộ của Spring.
- **Đổi phiên bản:** Spring Boot 3.3 dùng cơ chế như trên; sau khi nâng cấp nên đọc tài liệu phiên bản mới về factory loading, metadata, web context và thứ tự sự kiện.

## 13. Bài tập mở rộng kèm tiêu chí

### Bài tập 1: Thứ tự và ghi đè giá trị

Trong bản copy của project, cho `ApiInitializer` thêm property `lab.shared=api` và `FactoriesInitializer` thêm `lab.shared=factories`. Lần đầu cả hai dùng `addLast`; lần hai thay factories thành `addFirst`. Ghi lại giá trị hiệu lực của `lab.shared` ở controller và giải thích vai trò **thứ tự nguồn** so với **thứ tự initializer**. Không chỉ nhìn thứ tự console và đoán precedence.

### Bài tập 2: Một thư viện tự đăng ký

Tách `FactoriesInitializer` cùng `META-INF/spring.factories` sang module Maven JAR riêng. Thêm JAR làm dependency runtime của `initializer-lab`, bỏ initializer factory khỏi app để tránh hai bản class trùng nhau. Chạy lại JAR của app, đối chiếu `LAB_FACTORIES_INITIALIZER` và `/initializer-status`. Đây là cách kiểm thử một thư viện thực sự có auto-registration.

### Bài tập 3: Chứng minh thời điểm trước refresh

Giữ listener của `ApplicationContextInitializedEvent`, thêm một listener cho `ApplicationReadyEvent` như ví dụ. Ghi thứ tự các marker và giải thích tại sao trong `ApplicationContextInitializedEvent` chỉ cần kiểm chứng `Environment` và loại context mà không cố gọi controller bean. Kết luận được phép: initializer đã chạy trước khi bean nghiệp vụ sẵn sàng.

### Bài tập 4: Khởi động lỗi có chủ đích

Cho initializer ném `IllegalStateException` có marker duy nhất. Ghi stack trace gốc, các marker đã xuất hiện, xem ứng dụng có được đến `LAB_APPLICATION_READY` hay không. Khôi phục code rồi build lại. Giải thích tại sao lỗi xảy ra trước refresh khác với bean creation failure và HTTP 500.

### Mẫu bảng thực nghiệm

| Tình huống | Đầu vào/đăng ký | Log quan sát | HTTP output | Kết luận |
|---|---|---|---|---|
| Cả hai | API + factories | Cả hai marker, event initialized | `true / true` | Hai đường hoạt động |
| API-only | Bỏ factories metadata, clean build | Chỉ marker API | `true / false` | API độc lập |
| Factories-only | Bỏ dòng `addInitializers`, clean build | Chỉ marker factories | `false / true` | Metadata độc lập |
| Sai metadata | Đổi FQCN factories trong lab | Lỗi load/instantiate theo stack trace | Không đạt ready | Tên lớp phải đúng |
| Sai thứ tự | Đổi `Ordered` và nguồn cùng key | Marker/giá trị đổi theo cấu hình | Giá trị hiệu lực thực | Phân biệt order và precedence |

Khi làm bài, ghi lệnh build/chạy, phiên bản Spring Boot, nguồn `spring.factories` trong JAR, các marker và response HTTP thực tế. Không chỉ ghi “thành công” vì nhìn thấy một dòng log chung của Spring.

## 14. Checklist hoàn thành

- [ ] Giải thích được vì sao initializer chạy trước bean definitions chính và trước context refresh.
- [ ] Viết được class implement `ApplicationContextInitializer<ConfigurableApplicationContext>`.
- [ ] Đăng ký được một initializer bằng `SpringApplication.addInitializers(...)` trước `run`.
- [ ] Tạo đúng `src/main/resources/META-INF/spring.factories` với full key và full class name.
- [ ] Đóng gói project và tìm thấy `spring.factories` trong JAR.
- [ ] Chạy được Spring Boot 3.3.x / Java 17+ và quan sát cả hai marker.
- [ ] Gọi được `GET /initializer-status`, kiểm tra hai property do initializer thêm vào.
- [ ] Thực hiện được đối chứng API-only, factories-only và cả hai.
- [ ] Giải thích `Ordered` và ảnh hưởng của `addFirst`/`addLast` đến precedence.
- [ ] Phân biệt `ApplicationContextInitializer` với `EnvironmentPostProcessor`, bean post-processors và runner.
- [ ] Chẩn đoán được ít nhất một lỗi metadata/classpath và một lỗi dùng initializer quá muộn.
- [ ] Không gọi `refresh()` hoặc `getBean()` tùy tiện trong initializer.

## 15. Tài liệu chính thức

1. Spring Boot 3.3 — How-to, Customize the Environment or ApplicationContext Before It Starts: https://docs.spring.io/spring-boot/3.3/how-to/application.html
2. Spring Boot 3.3 — SpringApplication API (addInitializers, setInitializers, applyInitializers): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
3. Spring Boot 3.3 — SpringApplication Events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
4. Spring Framework — ApplicationContextInitializer API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ApplicationContextInitializer.html
5. Spring Framework — Ordered và property source precedence: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/Ordered.html

**Cách tự kiểm tra kiến thức:** với mỗi cơ chế đăng ký, ghi rõ nơi cấu hình, thời điểm nạp class, lúc `initialize(...)` chạy, thuộc tính hoặc context property được thay đổi, bằng chứng xuất hiện trước refresh và hiệu ứng có thể đọc sau ready. Khi các bằng chứng khớp, có thể kết luận initializer đã được áp dụng đúng vòng đời.