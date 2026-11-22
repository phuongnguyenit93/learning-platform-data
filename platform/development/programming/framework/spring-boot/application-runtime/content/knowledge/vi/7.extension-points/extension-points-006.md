# Đăng ký SpringApplicationRunListener, yêu cầu constructor và thứ tự thực thi

## 1. SpringApplicationRunListener là điểm mở rộng nào?

**SpringApplicationRunListener** là một giao diện mở rộng ở tầng **SpringApplication.run(...)**. Nó cho phép một thư viện hoặc ứng dụng quan sát, và khi thật sự cần thiết can thiệp nhẹ vào, những mốc rất sớm của vòng đời khởi động Spring Boot: từ lúc bắt đầu chạy, chuẩn bị Environment, tạo ApplicationContext, refresh context, chạy startup runner, đến khi ứng dụng ready hoặc thất bại.

Đặc điểm quan trọng của RunListener:

- Một instance RunListener được tạo **cho mỗi lần gọi SpringApplication.run(...)**, qua cơ chế nạp factory của Spring.
- Nó được nạp **trước khi ApplicationContext hoàn chỉnh**, vì vậy không phải một Spring bean thông thường và không nhận dependency injection tự động như các bean trong context.
- Các phương thức của nó được SpringApplication gọi ở **những thời điểm xác định**, không phải một luồng công việc riêng, scheduler hay listener chạy sau khi service sẵn sàng.
- Trong Spring Boot 3.x, các phương thức của giao diện là **default methods**, vì vậy có thể chỉ override những callback thật sự cần thiết.

RunListener hữu ích khi cần tích hợp quan sát startup sớm, thu thập mốc thời gian khởi động, thêm hook ở tầng thư viện hạ tầng hoặc hiểu vì sao quá trình bootstrap không đi đến trạng thái ready. Với nghiệp vụ thông thường, hãy dùng **ApplicationRunner**, **CommandLineRunner**, **ApplicationListener** hoặc các bean/lifecycle hook thay vì mặc định tạo RunListener.

**Phân biệt hai từ gần nhau:** SpringApplicationRunListener nhận **lời gọi callback vòng đời của SpringApplication**. ApplicationListener nhận **application events** như ApplicationStartedEvent và ApplicationReadyEvent do cơ chế sự kiện của Spring phát hành. Spring Boot có một RunListener nội bộ tên **EventPublishingRunListener** làm cầu nối phát các sự kiện này, nhưng hai giao diện không phải một.

## 2. Cách đăng ký RunListener trong Spring Boot 3.x

Spring Boot dùng **SpringFactoriesLoader** để tìm và khởi tạo các implementation của SpringApplicationRunListener từ tài nguyên classpath:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Ví dụ nội dung tệp:

~~~properties
org.springframework.boot.SpringApplicationRunListener=example.TraceRunListener
~~~

Ở đây:

- Bên trái dấu bằng là **tên đầy đủ của giao diện**: org.springframework.boot.SpringApplicationRunListener.
- Bên phải là **tên lớp implementation đầy đủ package** (fully qualified class name), không phải tên bean, tên tệp Java hay tên method.
- Sau khi đóng gói, tài nguyên phải thực sự nằm tại **META-INF/spring.factories** trên classpath. Với project Gradle/Maven tiêu chuẩn, tệp đặt ở **src/main/resources/META-INF/spring.factories** sẽ được đưa vào output resources.
- Nếu cần nhiều implementation, có thể liệt kê bằng dấu phẩy, hoặc xuống dòng bằng cú pháp continuation hợp lệ của tệp properties. SpringFactoriesLoader nạp các factory được khai báo trên classpath rồi áp dụng thứ tự của chúng.

Ví dụ đăng ký hai listener:

~~~properties
org.springframework.boot.SpringApplicationRunListener=example.TraceRunListener,example.SecondRunListener
~~~

**Trong Spring Boot 3.x, RunListener vẫn được đăng ký bằng META-INF/spring.factories.** Đừng đặt khai báo trên vào **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**: đường dẫn này phục vụ việc đăng ký **auto-configuration classes**, không phải registry của SpringApplicationRunListener.

Đừng chỉ gắn **@Component** lên một lớp RunListener và trông chờ SpringApplication tìm được nó ở giai đoạn khởi động sớm. Component scanning diễn ra sau khi RunListener đã được nạp. Tương tự, **app.addListeners(...)** dùng để thêm **ApplicationListener** nhận event, không phải API đăng ký SpringApplicationRunListener.

## 3. Yêu cầu constructor chính xác

Với Spring Boot 3.3.x, lớp triển khai phải có **public constructor** nhận đúng hai tham số theo thứ tự và kiểu:

~~~java
public TraceRunListener(SpringApplication application, String[] args) {
    // Luu thong tin can thiet, khong phu thuoc vao Spring bean.
}
~~~

Đây là chữ ký dùng cho một lớp implementation thực sự. Import của SpringApplication là **org.springframework.boot.SpringApplication**.

**Tại sao constructor này quan trọng?** SpringApplication lấy tất cả RunListener được khai báo bằng SpringFactoriesLoader và truyền cho cơ chế tạo instance:

1. **SpringApplication** đang khởi động.
2. **String[]** là các đối số được truyền trực tiếp tới **SpringApplication.run(args)**.

Cơ chế này không tạo RunListener thông qua Spring BeanFactory, nên constructor không nên yêu cầu những bean như DataSource, Environment bean, Repository hoặc một service tự định nghĩa. Ở thời điểm tạo RunListener, ApplicationContext chưa được dựng đầy đủ.

Những lỗi hay gặp:

| Constructor hoặc thiết kế | Kết quả |
| --- | --- |
| public TraceRunListener(SpringApplication application, String[] args) | Chữ ký phù hợp |
| TraceRunListener(SpringApplication application, String[] args) không public | Không đáp ứng yêu cầu constructor public |
| public TraceRunListener() | Thiếu hai tham số SpringApplication và String[] |
| public TraceRunListener(String[] args, SpringApplication application) | Sai thứ tự tham số theo hợp đồng |
| public TraceRunListener(SpringApplication application, List<String> args) | Sai kiểu của tham số thứ hai |
| Constructor yêu cầu @Autowired MyService | Không có cơ chế constructor injection của bean ở giai đoạn này |
| Chỉ khai báo @Component mà thiếu spring.factories | Không được tự động nạp thành SpringApplicationRunListener |

Một lỗi class name, package, constructor hoặc dependency khởi tạo trong **spring.factories** có thể khiến **SpringFactoriesLoader** không tạo được RunListener và lần khởi động thất bại trước khi toàn bộ context được chuẩn bị. Hãy để constructor đơn giản: ghi nhận args/config được cấp, tránh I/O tốn thời gian và không mở những tài nguyên khó dọn.

**Mỗi lần run(...) có instance mới** không có nghĩa đây là singleton Spring. Đừng dùng state của instance để lưu dữ liệu xuyên các lần chạy ứng dụng, và đừng tự giả định luôn chỉ có một run(...) trong các ứng dụng có nhiều SpringApplication hoặc context hierarchy.

## 4. Thứ tự callback trong một lần khởi động thành công

Các callback theo chuỗi logic chuẩn:

| Thứ tự | Callback trong SpringApplicationRunListener | Trạng thái khi được gọi |
| --- | --- | --- |
| 1 | starting(ConfigurableBootstrapContext) | Ngay khi SpringApplication.run(...) bắt đầu, trước khi Environment được chuẩn bị đầy đủ |
| 2 | environmentPrepared(ConfigurableBootstrapContext, ConfigurableEnvironment) | Environment đã chuẩn bị, ApplicationContext chưa được tạo |
| 3 | contextPrepared(ConfigurableApplicationContext) | Context đã tạo, initializer đã áp dụng, chưa nạp application source/bean definitions đầy đủ |
| 4 | contextLoaded(ConfigurableApplicationContext) | Source/bean definitions đã được nạp; context chưa refresh |
| 5 | started(ConfigurableApplicationContext, Duration) | Context đã refresh, nhưng ApplicationRunner/CommandLineRunner chưa thực thi |
| 6 | ready(ConfigurableApplicationContext, Duration) | Runner đã hoàn tất, ứng dụng sắp kết thúc nhánh run(...) thành công |

**failed(ConfigurableApplicationContext, Throwable)** là callback của **nhánh lỗi**, không phải bước thứ bảy luôn xảy ra sau ready. Nếu lỗi xuất hiện trước khi context được tạo, tham số context có thể là **null**.

Dễ nhớ:

~~~text
RunListener được tạo
       |
       v
starting
       |
environmentPrepared     -- Environment đã có
       |
contextPrepared         -- Context đã tạo, đã áp dụng initializer
       |
contextLoaded           -- Đã load sources, chưa refresh
       |
refresh ApplicationContext
       |
started                 -- Refresh xong
       |
ApplicationRunner / CommandLineRunner
       |
ready                   -- Runner xong, run(...) sắp trả về
~~~

Nếu một lỗi khiến nhánh khởi động thất bại, các callback phía sau điểm lỗi thường không chạy. **failed(...)** có thể được gọi trong cơ chế failure handling, nhưng không được coi nó là callback bảo đảm bắt được mọi lỗi kể cả lỗi xảy ra trong lúc **nạp hoặc tạo chính RunListener**. Vị trí exception rất quan trọng: Boot 3.3 lấy và tạo RunListener trước khi bước xử lý startup chính đi vào khối bắt lỗi của run(...).

**Tương quan với event Spring Boot:** RunListener **started(...)** ở giai đoạn sau refresh và trước runner, tương ứng với mốc **ApplicationStartedEvent** được hệ thống phát hành. RunListener **ready(...)** xuất hiện sau các runner, liên quan mốc **ApplicationReadyEvent**. Không suy ra chúng là cùng một object hay callback đến từ cùng một interface; EventPublishingRunListener là thành phần nội bộ chuyển mốc vòng đời thành application events.

## 5. Hai kiểu thứ tự rất dễ bị nhầm

### 5.1. Thứ tự các giai đoạn của SpringApplication

Các callback **starting → environmentPrepared → contextPrepared → contextLoaded → started → ready** là thứ tự theo vòng đời. Bạn **không thể** dùng annotation @Order để chuyển **ready(...)** lên trước **contextPrepared(...)** hoặc để cho started chạy trước refresh.

### 5.2. Thứ tự giữa nhiều RunListener

Nếu classpath có nhiều SpringApplicationRunListener, **SpringFactoriesLoader** tải chúng và sắp xếp implementation bằng **AnnotationAwareOrderComparator**. Có thể đặt **@Order(n)** trên class hoặc dùng giao diện **Ordered**.

Ví dụ:

~~~java
@Order(100)
public final class TraceRunListener implements SpringApplicationRunListener {
    // ...
}
~~~

~~~java
@Order(200)
public final class SecondRunListener implements SpringApplicationRunListener {
    // ...
}
~~~

Giữa **hai listener đó**, số thấp hơn có độ ưu tiên cao hơn: listener **100 chạy trước 200 ở cùng một giai đoạn**.

Ví dụ, SpringApplication sẽ gọi starting(...) cho từng listener theo thứ tự được sắp xếp, sau đó mới chuyển toàn bộ chuỗi sang environmentPrepared(...). Không phải chạy đủ cả sáu callback của TraceRunListener rồi mới chạy sáu callback của SecondRunListener.

Chỉ số @Order của hai listener tùy chỉnh **không quyết định tuyệt đối** vị trí tương đối với mọi listener khác trên classpath, bởi Spring Boot và thư viện có thể đăng ký các RunListener riêng với độ ưu tiên khác. Nếu hai listener có cùng order, đừng dựa vào thứ tự ghi tên trong tệp properties như một hợp đồng nghiệp vụ bền vững.

## 6. Ví dụ chạy được: hai RunListener, một startup runner

Tạo một dự án Gradle Spring Boot 3.3.x dùng **JDK 17+**, dependency **spring-boot-starter** và plugin Spring Boot. Ví dụ dùng Java 17 và mã dưới đây không cần web server.

Cấu trúc thư mục:

~~~text
run-listener-demo/
  build.gradle
  settings.gradle
  src/
    main/
      java/
        example/
          RunListenerDemo.java
          TraceRunListener.java
          SecondRunListener.java
      resources/
        META-INF/
          spring.factories
~~~

### 6.1. Cấu hình Gradle

Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'run-listener-demo'
~~~

Tệp **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Gradle cần có phiên bản được Spring Boot 3.3 hỗ trợ và có thể tải plugin/dependency từ internet hoặc cache cục bộ. Dùng Gradle wrapper của dự án nếu đã có; cấu hình trên dùng **Spring Boot 3.3.13** để cố định phiên bản cho ví dụ.

### 6.2. Ứng dụng chính

Tệp **src/main/java/example/RunListenerDemo.java**:

~~~java
package example;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class RunListenerDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(RunListenerDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("main.afterRun");
        }
    }

    @Bean
    ApplicationRunner demoRunner() {
        return args -> {
            System.out.println("runner");
            if (args.containsOption("demo.fail")) {
                throw new IllegalStateException("demo runner failure");
            }
        };
    }
}
~~~

**Giải thích:** WebApplicationType.NONE giúp demo kết thúc rõ ràng mà không mở server HTTP. **ApplicationRunner** là bean và chỉ được chạy **sau** callback started(...), **trước** callback ready(...). Tham số **--demo.fail** được dùng để tạo lỗi ở runner khi cần kiểm tra nhánh thất bại. Mã chính đóng context sau khi **app.run(...)** thành công.

### 6.3. RunListener quan sát mọi mốc chính

Tệp **src/main/java/example/TraceRunListener.java**:

~~~java
package example;

import java.time.Duration;

import org.springframework.boot.ConfigurableBootstrapContext;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringApplicationRunListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.annotation.Order;
import org.springframework.core.env.ConfigurableEnvironment;

@Order(100)
public final class TraceRunListener implements SpringApplicationRunListener {

    public TraceRunListener(SpringApplication application, String[] args) {
        System.out.println("trace.constructor args=" + args.length);
    }

    @Override
    public void starting(ConfigurableBootstrapContext bootstrapContext) {
        System.out.println("trace.starting");
    }

    @Override
    public void environmentPrepared(
            ConfigurableBootstrapContext bootstrapContext,
            ConfigurableEnvironment environment) {
        System.out.println("trace.environmentPrepared");
    }

    @Override
    public void contextPrepared(ConfigurableApplicationContext context) {
        System.out.println("trace.contextPrepared");
    }

    @Override
    public void contextLoaded(ConfigurableApplicationContext context) {
        System.out.println("trace.contextLoaded");
    }

    @Override
    public void started(
            ConfigurableApplicationContext context, Duration timeTaken) {
        System.out.println("trace.started");
    }

    @Override
    public void ready(
            ConfigurableApplicationContext context, Duration timeTaken) {
        System.out.println("trace.ready");
    }

    @Override
    public void failed(
            ConfigurableApplicationContext context, Throwable exception) {
        System.out.println("trace.failed");
    }
}
~~~

Điểm cần chú ý: cả **starting** và **environmentPrepared** nhận một **ConfigurableBootstrapContext**; environmentPrepared còn nhận **ConfigurableEnvironment**. Hai callback **started/ready** nhận thêm **java.time.Duration**. **failed** nhận Throwable và một context có thể null. Đây là chữ ký cho Spring Boot **3.3.x**, không nên sao chép phương thức từ ví dụ viết cho phiên bản rất cũ nếu signature đã đổi.

### 6.4. RunListener thứ hai để kiểm tra @Order

Tệp **src/main/java/example/SecondRunListener.java**:

~~~java
package example;

import java.time.Duration;

import org.springframework.boot.ConfigurableBootstrapContext;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringApplicationRunListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.annotation.Order;

@Order(200)
public final class SecondRunListener implements SpringApplicationRunListener {

    public SecondRunListener(SpringApplication application, String[] args) {
    }

    @Override
    public void starting(ConfigurableBootstrapContext bootstrapContext) {
        System.out.println("second.starting");
    }

    @Override
    public void ready(
            ConfigurableApplicationContext context, Duration timeTaken) {
        System.out.println("second.ready");
    }
}
~~~

SecondRunListener không override các mốc khác, vì giao diện cung cấp default method rỗng. Chữ ký constructor vẫn phải đúng. **@Order(100)** và **@Order(200)** tạo thứ tự quan sát được ở hai mốc starting/ready mà cả hai listener đều override.

### 6.5. Đăng ký hai listener

Tệp **src/main/resources/META-INF/spring.factories**:

~~~properties
org.springframework.boot.SpringApplicationRunListener=example.TraceRunListener,example.SecondRunListener
~~~

Phải dùng đúng key nêu trên, đúng package **example**, đúng chữ hoa/chữ thường và đặt tệp vào classpath. Không cần thêm @Component cho hai listener.

### 6.6. Chạy và đối chiếu thứ tự

Nếu dự án có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu chưa có wrapper nhưng có Gradle tương thích đã cài, có thể dùng **gradle bootRun**.

Với lần chạy **không truyền đối số**, các dòng **do mã ví dụ tự in** xuất hiện theo thứ tự:

~~~text
trace.constructor args=0
trace.starting
second.starting
trace.environmentPrepared
trace.contextPrepared
trace.contextLoaded
trace.started
runner
trace.ready
second.ready
main.afterRun
~~~

Log nội bộ của Spring Boot/Gradle tùy môi trường có thể xen giữa những dòng này; ở đây chỉ liệt kê thông báo do code trong ví dụ in ra.

Quan sát cho thấy:

1. **Constructor** của RunListener được gọi trước các callback; nó nhận SpringApplication và mảng arguments.
2. Ở mốc **starting**, TraceRunListener có order **100** in trước SecondRunListener order **200**.
3. Các mốc **environmentPrepared → contextPrepared → contextLoaded → started** xảy ra trước runner.
4. **runner** in sau started, trước ready.
5. Ở mốc **ready**, TraceRunListener vẫn in trước SecondRunListener.
6. **main.afterRun** xuất hiện sau khi **SpringApplication.run(args)** trả về thành công.

Không gán ý nghĩa cho việc người dùng khai báo listener nào trước trong spring.factories nếu đã có @Order: chính độ ưu tiên mới là công cụ rõ ràng để xác định thứ tự giữa các implementation.

## 7. Thử nhánh thất bại và giới hạn của callback failed(...)

Chạy lại demo với đối số gây lỗi trong runner:

~~~bash
./gradlew bootRun --args="--demo.fail"
~~~

Khi đó, các mốc **constructor → starting → environmentPrepared → contextPrepared → contextLoaded → started** vẫn xuất hiện, rồi đến dòng **runner**. Runner ném exception, SpringApplication chuyển sang đường startup failure, và TraceRunListener có thể in:

~~~text
trace.failed
~~~

Trong trường hợp lỗi runner theo ví dụ này, **trace.ready**, **second.ready** và **main.afterRun** sẽ không xuất hiện. Spring Boot/Gradle cũng có thể ghi stack trace và thông báo build thất bại. **failed(context, exception)** cần phòng trường hợp context bằng null nếu lỗi xảy ra trước khi context được tạo.

Đối với lỗi xảy ra ngay lúc **SpringFactoriesLoader tạo RunListener**, hoặc ngoại lệ bị ném ở hook cực sớm như **starting(...)**, đừng dựa vào chính RunListener đó để bắt lỗi của nó. Trong luồng Spring Boot 3.3, việc lấy/tạo RunListener và gọi starting diễn ra trước khối try/catch chính quản lý phần startup. Cần kiểm tra console/log của caller và tránh ném exception trong RunListener trừ khi có yêu cầu rõ ràng buộc phải từ chối startup.

Không sử dụng RunListener để mở connection pool hay tạo thread nền rồi tin rằng **failed(...) luôn được gọi và sẽ giải phóng tài nguyên**. Nếu một hook phải cấp phát resource, cần có try/finally, lifecycle owner rõ ràng, timeout và cleanup riêng.

## 8. RunListener khác các điểm mở rộng gần nó thế nào?

| Cơ chế | Cách đăng ký thông dụng | Giai đoạn chính | Khi nào dùng |
| --- | --- | --- | --- |
| SpringApplicationRunListener | META-INF/spring.factories với key org.springframework.boot.SpringApplicationRunListener | Rất sớm; nhiều callback trải suốt SpringApplication.run | Hook hạ tầng/quan sát trình tự bootstrap |
| ApplicationListener | app.addListeners(...), @Bean khi context sẵn sàng, hoặc spring.factories với key ApplicationListener | Khi sự kiện Spring được phát | Quan sát/xử lý application events |
| ApplicationContextInitializer | app.addInitializers(...) hoặc factory registration tương ứng | Sau khi tạo context, trước refresh | Tinh chỉnh context trước khi bean được khởi tạo |
| EnvironmentPostProcessor | Factory registration qua spring.factories | Chuẩn bị Environment/config | Bổ sung/chỉnh property sources sớm |
| ApplicationRunner | Spring bean | Sau refresh, trước ready | Thực hiện tác vụ khởi tạo có thể dùng DI |
| CommandLineRunner | Spring bean | Sau refresh, trước ready | Tác vụ khởi động cần mảng String[] args |

Nếu cần **DataSource**, **Repository** hoặc một bean khác để chạy nghiệp vụ, thông thường **ApplicationRunner** phù hợp hơn vì context đã khởi tạo. Nếu cần đọc/điều chỉnh config trước khi tạo bean, đánh giá **EnvironmentPostProcessor**. Nếu chỉ muốn nhận sự kiện, cân nhắc **ApplicationListener** thay vì triển khai một SPI thấp hơn.

**Thứ tự của ApplicationRunner/CommandLineRunner** có thể được sắp xếp bằng @Order/Ordered cho các runner bean; đó là một hệ thống sắp xếp riêng với thứ tự của SpringApplicationRunListener. Dù order bằng số thấp nhất, một runner vẫn không được chạy trước mốc RunListener started(...) trong đường startup bình thường.

## 9. Những lỗi thường gặp khi triển khai

**Không được gọi vì đặt sai tệp.** Kiểm tra đường dẫn thực trong build output: **META-INF/spring.factories** phải nằm trên classpath. Tệp ở thư mục mã Java hoặc một thư mục META-INF khác sẽ không được phát hiện.

**Dùng key sai.** Key phải đúng là **org.springframework.boot.SpringApplicationRunListener**, không phải ApplicationListener, tên lớp implementation hoặc một property tùy ý.

**Constructor không công khai hoặc tham số sai.** Dù lớp implements SpringApplicationRunListener, SpringFactoriesLoader cần tạo instance bằng public constructor với **SpringApplication, String[]**. Không dùng constructor no-args để thay thế.

**Chờ Spring tự inject bean vào constructor.** RunListener được tạo trước khi container bean hoạt động đầy đủ. Không chèn repository/service bean tùy ý vào constructor; đổi sang runner hoặc lifecycle hook khi cần DI.

**Dùng @Component thay cho factory registration.** Component scanning không thay thế cơ chế nạp RunListener qua spring.factories.

**Đăng ký qua AutoConfiguration.imports.** Đây là cơ chế đăng ký auto-configuration, không phải RunListener. Lưu ý Spring Boot 3.x vẫn hỗ trợ spring.factories cho nhiều extension SPI như RunListener.

**Nhầm callback started với ready.** started(...) xảy ra sau refresh nhưng **trước** các runner; ready(...) xảy ra sau khi các runner kết thúc thành công.

**Nhầm thứ tự @Order với thứ tự giai đoạn.** @Order chỉ điều khiển thứ tự giữa những listener tại cùng điểm gọi; nó không sắp xếp lại toàn bộ vòng đời khởi động.

**Ghi log hoặc thực hiện I/O quá nặng trong callback.** Callback thường chạy đồng bộ trong thread khởi động và có thể làm startup chậm. Tránh gọi dịch vụ mạng thiếu timeout, làm việc bất đồng bộ không được quản lý hoặc blocking vô hạn.

**Đọc bean ở contextPrepared/contextLoaded.** Đây là các giai đoạn trước refresh, nên bean chưa chắc được tạo/không an toàn để dùng. Đợi đến started hoặc runner khi cần bean đã khởi tạo.

**Không xử lý lỗi trong listener.** Nếu listener ném exception, nó có thể làm startup gián đoạn và che nguyên nhân quan trọng. Với chẩn đoán/telemetry, ghi log an toàn và bảo đảm không phụ thuộc vào dịch vụ đang gặp sự cố.

**Không phân biệt nhiều SpringApplication.** Với context hierarchy hoặc kiểm thử khởi động nhiều lần trong cùng JVM, RunListener mới có thể được tạo mỗi lần; không giả định chỉ một instance hoặc một lần gọi mọi callback trên toàn tiến trình.

## 10. Kiểm tra kết quả và chẩn đoán

Khi RunListener không hoạt động như dự kiến, làm theo trình tự:

1. Xác nhận **Spring Boot 3.x và Java version** thực tế. Nếu sao chép mã từ phiên bản cũ, đối chiếu signature callback theo API đúng phiên bản.
2. Xem build output hoặc JAR để chắc **META-INF/spring.factories** đã được đóng gói.
3. Kiểm tra key và tên lớp fully qualified trong spring.factories, đặc biệt lỗi chính tả và dấu phẩy.
4. Xác nhận implementation là class truy cập được với **public constructor (SpringApplication, String[])**.
5. Dùng log ngắn ở constructor và **starting(...)** để phân biệt **không nạp được implementation** với **đã nạp nhưng callback lỗi**.
6. Nếu thứ tự giữa nhiều implementation không mong muốn, kiểm tra **@Order/Ordered** trên toàn bộ RunListener, không dựa vào danh sách trong tệp properties.
7. Nếu chỉ thiếu **ready(...)**, xem startup runner có ném exception hay ứng dụng đã gặp lỗi trước khi ready.
8. Nếu cần quan sát lỗi rất sớm, đọc stack trace từ entrypoint; đừng mặc định **failed(...)** sẽ được gọi nếu chính phần tạo/khởi chạy listener bị lỗi.

Kiểm thử đáng tin nên xác nhận **thứ tự những dòng do code của ứng dụng tự in**, chấp nhận các dòng log framework có thể xen giữa. Với test tự động, thay System.out bằng bộ thu sự kiện thread-safe phục vụ test, tránh gắn yêu cầu test vào cách format log nội bộ.

## 11. Câu hỏi tự kiểm tra

1. **Đặt một class implements SpringApplicationRunListener thành @Component có đủ không?** Không. Cần đăng ký implementation đúng key trong META-INF/spring.factories.
2. **Constructor bắt buộc có signature nào?** Public constructor nhận **SpringApplication** và **String[]** theo thứ tự đó.
3. **Muốn chạy tác vụ cần Repository bean sau khi Spring khởi tạo xong, nên dùng gì?** ApplicationRunner/CommandLineRunner thường phù hợp hơn.
4. **Giữa listener order 100 và order 200, listener nào được gọi trước ở cùng callback?** Order 100.
5. **Một listener order 1 có làm ready(...) chạy trước contextLoaded(...) không?** Không. @Order chỉ sắp xếp các listener tại một giai đoạn, không thay đổi chuỗi khởi động.
6. **RunListener.started(...) có nghĩa tất cả runner đã hoàn tất?** Không. Các runner được gọi sau started, trước ready.
7. **Lỗi ở runner có phát ready(...) không?** Không theo đường startup thành công; failure handling xử lý lỗi.
8. **Có chắc failed(...) chạy nếu constructor RunListener ném exception?** Không. Việc khởi tạo RunListener có thể thất bại trước cơ chế bắt lỗi startup chính.
9. **Dùng AutoConfiguration.imports để đăng ký RunListener có đúng không?** Không. RunListener sử dụng cơ chế spring.factories.
10. **Tại sao không dùng RunListener để mở DataSource bằng @Autowired trong constructor?** Vì RunListener được tạo trước khi Spring context/bean injection sẵn sàng.

**Ghi nhớ:** RunListener là SPI cấp SpringApplication, phải được nạp qua **META-INF/spring.factories** với **public constructor(SpringApplication, String[])**. Các callback chạy theo **thứ tự giai đoạn khởi động**; khi có nhiều RunListener, thứ tự giữa chúng tại mỗi giai đoạn được điều khiển bằng **@Order/Ordered**, không thay đổi thứ tự của chính các giai đoạn.

### Tài liệu tham khảo

- [Spring Boot 3.3 — SpringApplicationRunListener API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplicationRunListener.html)
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Framework 6.1 — SpringFactoriesLoader API](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/core/io/support/SpringFactoriesLoader.html)
- [Spring Boot — Application Events and Listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
