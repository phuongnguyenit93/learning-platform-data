# DevTools: thay đổi mặc định khi phát triển và tác động đến đo thời gian trong Spring Boot

## 1. Vấn đề: nhanh khi restart chưa chắc nhanh khi triển khai thật

Spring Boot DevTools được thiết kế để rút ngắn vòng phản hồi khi lập trình. Nó tự điều chỉnh một số property phục vụ development, theo dõi thay đổi trên classpath và có thể restart ứng dụng trong cùng JVM. Những tiện ích đó khiến môi trường local **khác với môi trường production về caching, classloading, trạng thái JVM, logging và vòng đời tài nguyên**.

Điều quan trọng nhất khi đo hiệu năng:

- **Thời gian cold start**: khởi chạy một JVM/process mới, nạp framework và dựng application context.
- **Thời gian DevTools restart**: JVM đã hoạt động và base classloader vẫn còn; DevTools tạo restart classloader/context mới.
- **Thời gian từ Save tới thấy thay đổi**: bao gồm IDE/build compile, copy classpath, file watcher, context restart và browser refresh.
- **Thời gian từ ApplicationStartedEvent tới ApplicationReadyEvent**: phần startup sau context refresh, trong đó có ApplicationRunner/CommandLineRunner.
- **Thời gian request lần đầu và request đã warm**: phụ thuộc template cache, static resource cache, JIT, connection pool và lazy beans.

**Không so sánh những số đo có ranh giới khác nhau như cùng một đại lượng.** Một dòng Started ... in 0.8s sau DevTools restart không chứng minh một executable JAR trên JVM mới cũng ready sau 0.8s.

Bài lấy **Spring Boot 3.3.x, Java 17+**, ví dụ với Boot **3.3.13**. Danh sách default property dưới đây là của Boot **3.3**; phiên bản mới hơn có thể bổ sung hoặc đổi tên một số property.

## 2. DevTools được đưa vào ứng dụng như thế nào?

### Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

### Maven

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

Dùng **developmentOnly** (Gradle) hoặc **optional** (Maven) để dependency DevTools không tự lan truyền như dependency bình thường. Theo Spring Boot, DevTools **được loại khỏi repackaged executable JAR theo mặc định**. Khi chạy bằng **java -jar** ở chế độ packaged application thông thường, các chức năng DevTools sẽ được vô hiệu hóa.

Do đó, **bootRun/IDE với DevTools** và **java -jar không có DevTools** không giống nhau dù source code giống nhau. Không cố thêm remote DevTools hoặc bật cưỡng bức DevTools vào production, vì có rủi ro bảo mật và vận hành.

| Cách chạy | DevTools có thể hoạt động? | Mục đích |
| --- | --- | --- |
| IDE/Gradle bootRun với developmentOnly | Có | Vòng lặp phát triển |
| bootRun nhưng spring.devtools.add-properties=false | Có, nhưng không thêm nhóm defaults | Tách tác động development defaults |
| bootRun với restart tắt | Các tính năng khác vẫn có thể hoạt động | Chẩn đoán classloader/restart |
| bootJar + java -jar (mặc định) | DevTools không có trong artifact | Đo gần production hơn |
| Cố đưa DevTools vào packaged app | Có thể kích hoạt nếu ép | Không dùng trên production |

## 3. Development property defaults trong Spring Boot 3.3

Spring Boot 3.3 DevTools tự thêm nhóm cấu hình sau **khi DevTools active và spring.devtools.add-properties không bị tắt**:

| Property | Giá trị development | Ý nghĩa |
| --- | --- | --- |
| server.error.include-binding-errors | always | Chi tiết lỗi binding giúp debug |
| server.error.include-message | always | Trả thông điệp lỗi khi phù hợp |
| server.error.include-stacktrace | always | Có thể lộ stack trace trong error response |
| server.servlet.jsp.init-parameters.development | true | JSP development mode |
| server.servlet.session.persistent | true | Hỗ trợ duy trì session trong phát triển |
| spring.docker.compose.readiness.wait | only-if-started | Điều chỉnh chờ dịch vụ Compose do Boot khởi động |
| spring.freemarker.cache | false | Không cache FreeMarker template |
| spring.graphql.graphiql.enabled | true | Bật GraphiQL khi có GraphQL integration |
| spring.groovy.template.cache | false | Không cache Groovy templates |
| spring.h2.console.enabled | true | Bật H2 console khi có H2 |
| spring.mustache.servlet.cache | false | Không cache Mustache servlet template |
| spring.mvc.log-resolved-exception | true | Logging cho MVC exceptions đã resolve |
| spring.reactor.netty.shutdown-quiet-period | 0s | Giảm quiet period khi Reactor Netty shutdown |
| spring.template.provider.cache | false | Không cache phát hiện template provider |
| spring.thymeleaf.cache | false | Không cache Thymeleaf compiled templates |
| spring.web.resources.cache.period | 0 | Không đặt cache period dài cho static resources |
| spring.web.resources.chain.cache | false | Không cache resource chain |

**Bảng không có nghĩa tất cả integration đã được cài.** spring.h2.console.enabled=true không tự thêm H2 dependency, tương tự spring.thymeleaf.cache=false không tự thêm Thymeleaf engine. Property chỉ có tác dụng khi technology tương ứng được dùng và auto-configured.

**Không sao chép mặc định từ Spring Boot 4.x sang Boot 3.3.** Ví dụ, key error mặc định trong Boot 3.3 dùng **server.error.include-...**; một số tài liệu version mới có key và default khác. Nếu benchmark là căn cứ triển khai, phải ghi chính xác phiên bản.

### Các cache bị tắt để làm gì?

Trong development, người lập trình muốn sửa HTML/CSS rồi thấy thay đổi sớm, không bị template cache che mất. DevTools ưu tiên trải nghiệm đó. Trong production, cache thường giảm chi phí parse template, resource lookups và HTTP transfer.

Hệ quả:

1. **Thymeleaf/FreeMarker/Mustache:** một view có thể phải resolve/parse lại nhiều lần, gây khác biệt first-request và warm-request.
2. **Static resources:** cache period 0 và resource chain cache=false thay đổi header/lookup, có thể làm browser gửi nhiều request hơn.
3. **CPU/GC:** tạo nhiều object hơn trong quá trình render hoặc resolve resources có thể đổi CPU/allocations.
4. **p95/p99:** đường xử lý template và browser cache khác làm các percentiles không tương đương production.
5. **Startup:** tác động không nhất thiết xuất hiện trong ApplicationReadyEvent; nhiều template chỉ được parse khi request đầu tiên tới **sau Ready**.

**Không kết luận spring.thymeleaf.cache=false luôn làm startup chậm hơn:** nếu không có bước render trước Ready, cache có thể chủ yếu ảnh hưởng request time, không phải bean initialization. Phải đo tách **startup, first request, warm requests**.

### Các default khác cũng ảnh hưởng kết quả đo

- **server.error.include-stacktrace=always** và **spring.mvc.log-resolved-exception=true:** error-path response/logging có thể chậm hơn và không đại diện production; stack trace còn có rủi ro lộ thông tin.
- **spring.reactor.netty.shutdown-quiet-period=0s:** thay đổi khoảng chờ khi shutdown, nên phép đo toàn chu kỳ restart của reactive server có thể khác.
- **spring.docker.compose.readiness.wait=only-if-started:** dependency readiness wait khác khi Compose đã chạy sẵn so với khi Boot vừa khởi động dịch vụ.
- **server.servlet.session.persistent=true:** session có thể sống qua restart ở cấu hình hỗ trợ, làm khác trạng thái giữa warm restart và cold process mới.
- **spring.h2.console.enabled và spring.graphql.graphiql.enabled:** tạo các bề mặt phát triển cần kiểm soát truy cập, không lấy làm benchmark production nếu không có chúng ở production.

**DevTools không mặc định bật mọi logger ở DEBUG.** Tài liệu gợi ý bật nhóm logging web DEBUG khi cần quan sát request. Nếu bạn thêm logging.level.web=DEBUG, hãy ghi rõ vì output/logging có thể tác động đo hiệu năng.

## 4. Tắt development defaults khác tắt restart

Tắt nhóm development defaults:

~~~properties
spring.devtools.add-properties=false
~~~

Điều này **không tắt DevTools restart**, không xóa dependency khỏi classpath, không tắt LiveReload và không tái tạo một JVM cold start.

Nếu chỉ muốn Thymeleaf có cache như môi trường bình thường, bạn có thể override:

~~~properties
spring.thymeleaf.cache=true
~~~

Property ứng dụng được cấu hình tường minh có thể override default của DevTools. Khi đó các development defaults còn lại, ví dụ static resource period 0 hoặc stacktrace always, vẫn có thể hoạt động.

### Phân biệt bốn cờ

| Cờ | Có tác dụng gì? | Không giải quyết gì? |
| --- | --- | --- |
| spring.devtools.add-properties=false | Không chèn development defaults | Không tắt restart |
| spring.devtools.restart.enabled=false trong application.properties | Ngừng watch và restart khi classpath đổi | Restart classloader vẫn có thể được khởi tạo |
| -Dspring.devtools.restart.enabled=false trước SpringApplication.run | Tắt toàn bộ restart support theo hướng dẫn Boot 3.3 | Không mặc nhiên gỡ nhóm development defaults |
| spring.devtools.livereload.enabled=false | Tắt LiveReload server | Không tắt restart hoặc defaults |

Theo tài liệu Boot 3.3, **chỉ đặt restart.enabled=false trong application.properties không loại hoàn toàn restart classloader**. Nếu muốn tắt hẳn, đặt **JVM System property** trước SpringApplication.run hoặc không có dependency DevTools trong classpath.

Đối với benchmark production thực sự, cách chắc chắn nhất là **dùng build không chứa DevTools** và kiểm soát quá trình JVM launch; đừng chỉ tin rằng một flag làm mọi thứ giống production.

## 5. DevTools restart và hai classloader

~~~text
JVM process dang song
       |
       +-- Base classloader
       |     Thu vien/JAR it thay doi
       |
       +-- Restart classloader #1
       |     Application classes
       |     ApplicationContext #1
       |
IDE build/copy thay doi classpath
       |
       +-- Dong context #1
       +-- Bo restart classloader #1
       +-- Tao restart classloader #2
       +-- Tao ApplicationContext #2
       |
       +-- Base classloader va JVM tiep tuc ton tai
~~~

Với **cold start**, JVM, classloading, runtime caches/JIT và context đều bắt đầu từ trạng thái process mới. Với **DevTools restart**, JVM/base classloader đã hiện hữu, vì thế restart thường nhanh hơn cold start.

Không đồng nhất restart với JVM process exit/relaunch, cũng không hiểu restart là thay bytecode in-place cho mọi class. Các class trong thư viện ngoài thường được giữ trong base classloader, còn class đang phát triển vào restart classloader.

### Một thao tác Save có nhiều khoảng thời gian

~~~text
Save source
  -> IDE/Gradle compile, copy classpath
  -> FileSystemWatcher poll/quiet period
  -> DevTools phat hien change
  -> Context cu shutdown
  -> Restart classloader/context moi
  -> ApplicationStartedEvent
  -> Runner
  -> ApplicationReadyEvent
  -> Browser LiveReload
~~~

Khoảng **Save tới browser đổi nội dung** bao gồm cả thời gian IDE build, watcher và browser. **ApplicationReadyEvent.getTimeTaken() không đo các đoạn đó trước khi SpringApplication bắt đầu**.

DevTools theo dõi thay đổi **đầu ra trên classpath**, không đơn giản đọc file .java ngay khi bạn bấm Save. Với IntelliJ, Build Project/copy output có thể cần thiết; IDE auto-compile có thể tạo thêm delay.

Một số thư mục như templates, static, public và META-INF/resources thường không gây **full context restart** theo mặc định, nhưng có thể kích hoạt LiveReload. Sửa CSS mà browser refresh không phải bằng chứng startup vừa chạy lại.

### Thời gian file watcher

Có thể cấu hình:

~~~properties
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
~~~

Các giá trị này quyết định tốc độ phát hiện thay đổi và chờ file ổn định. Chúng **không phải** thời gian tạo Spring bean hoặc thời gian ApplicationContext.refresh. Khi đo phản hồi developer, phải ghi watcher delay; khi đo runtime startup, phải loại watcher delay khỏi metric.

## 6. Các đồng hồ phải dùng đúng ranh giới

| Đại lượng | Phạm vi |
| --- | --- |
| ApplicationStartedEvent.getTimeTaken() | Spring Boot tới started, sau context refresh, trước runner |
| ApplicationReadyEvent.getTimeTaken() | Spring Boot tới ready, sau các runner |
| application.started.time | Micrometer metric tổng thời gian tới started |
| application.ready.time | Micrometer metric tổng thời gian tới ready |
| RuntimeMXBean.getUptime() | Uptime của JVM process; vẫn tăng qua DevTools restart |
| save-to-reload elapsed | IDE compile + watcher + old shutdown + new startup + browser |
| first HTTP response | Network + routing + lazy init + template parse/cache và response |
| warm HTTP requests | Steady-state latency, phụ thuộc JIT/caches và workload |

Hai event có phương thức getTimeTaken() trả **Duration**, cũng có thể là null nếu không xác định. Mã thực hành xử lý null thay vì gán duration=0 tùy tiện.

**Ví dụ logic:** sau khi sửa source 10 lần, JVM process đã hoạt động 30 phút, nhưng Ready duration của một DevTools restart là vài trăm ms. Cả hai số có thể đúng vì đo hai khoảng khác nhau. Không lấy process uptime trừ từ 0 rồi xem là startup duration.

Không dùng lệnh đo wall time của một web server sống mãi đến khi shutdown để suy ra startup. Nếu process phục vụ request 10 phút, khoảng wall time bao gồm cả 10 phút phục vụ, không chỉ Spring initialization.


## 7. Project runnable Spring Boot 3.3/Java 17: quan sát property và thời gian thật

Ví dụ này dùng Gradle, embedded Tomcat, Thymeleaf và Actuator. Nó:

- Đưa DevTools vào developmentOnly, không đưa vào executable JAR mặc định.
- Kiểm tra giá trị raw Environment và **ThymeleafProperties.isCache()** cuối cùng.
- In event Started, Ready và duration tính bằng ms, có xử lý null.
- In JVM uptime để phân biệt JVM cũ với context restart.
- Có template và static resource giúp kiểm tra first/warm request.
- Cho phép tắt restart support bằng System property đặt trước SpringApplication.run.

### 7.1. Cấu trúc project

~~~text
devtools-timing-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          DevtoolsTimingDemo.java
      resources/
        application.properties
        templates/
          home.html
        static/
          demo.txt
~~~

**settings.gradle**:

~~~groovy
rootProject.name = 'devtools-timing-demo'
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

Yêu cầu JDK 17+, Gradle phù hợp, quyền tải plugin/dependencies hoặc đã có chúng trong cache.

**src/main/resources/application.properties**:

~~~properties
spring.application.name=devtools-timing-demo
server.port=8080
spring.main.banner-mode=off
management.endpoints.web.exposure.include=health,metrics
~~~

Chủ động **không khai báo** spring.thymeleaf.cache, spring.web.resources.cache.period và server.error.include-stacktrace; nếu chúng có giá trị trong Environment khi bootRun, có thể là development defaults do DevTools thêm.

### 7.2. Source Java

Tệp **src/main/java/demo/DevtoolsTimingDemo.java**:

~~~java
package demo;

import java.lang.management.ManagementFactory;
import java.time.Duration;
import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.thymeleaf.ThymeleafProperties;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@SpringBootApplication
public class DevtoolsTimingDemo {

    public static void main(String[] args) {
        if (Arrays.asList(args).contains("--demo.disable-restart")) {
            System.setProperty("spring.devtools.restart.enabled", "false");
        }
        SpringApplication.run(DevtoolsTimingDemo.class, args);
    }

    @Bean
    ApplicationRunner reportProperties(
            Environment environment, ThymeleafProperties thymeleaf) {
        return args -> {
            System.out.println("RUNNER_BEGIN");
            System.out.println("ENV_THYMELEAF_CACHE="
                    + environment.getProperty(
                            "spring.thymeleaf.cache", "<unset>"));
            System.out.println("EFFECTIVE_THYMELEAF_CACHE="
                    + thymeleaf.isCache());
            System.out.println("ENV_STATIC_CACHE_PERIOD="
                    + environment.getProperty(
                            "spring.web.resources.cache.period",
                            "<unset>"));
            System.out.println("ENV_ERROR_STACKTRACE="
                    + environment.getProperty(
                            "server.error.include-stacktrace",
                            "<unset>"));
            System.out.println("RUNNER_END");
        };
    }
}

@Component
class StartupTimingEvents {

    @EventListener
    public void started(ApplicationStartedEvent event) {
        System.out.println("EVENT_STARTED");
        printDuration("STARTED_MS", event.getTimeTaken());
    }

    @EventListener
    public void ready(ApplicationReadyEvent event) {
        System.out.println("EVENT_READY");
        printDuration("READY_MS", event.getTimeTaken());
        System.out.println("JVM_UPTIME_MS="
                + ManagementFactory.getRuntimeMXBean().getUptime());
    }

    private static void printDuration(String key, Duration value) {
        if (value == null) {
            System.out.println(key + "=unknown");
        } else {
            System.out.println(key + "=" + value.toMillis());
        }
    }
}

@Controller
class HomePageController {
    @GetMapping("/")
    public String home(Model model) {
        model.addAttribute("title", "DevTools Timing Demo");
        return "home";
    }
}
~~~

**Cú pháp runnable:**

- Chỉ DevtoolsTimingDemo là public class; tên tệp đúng. Hai class còn lại package-private cùng package demo.
- Spring Boot 3.3 cung cấp getTimeTaken() trên Started/Ready events; null được xử lý an toàn.
- Khi có thymeleaf starter, Boot auto-configures ThymeleafProperties; method isCache() phản ánh giá trị cuối.
- @Bean ApplicationRunner chạy **sau** ApplicationStartedEvent và **trước** ApplicationReadyEvent.
- System property tắt restart được đặt **trước run** khi dùng arg demo.disable-restart.
- Thời gian READY_MS và JVM_UPTIME_MS luôn biến đổi, không assert một con số cố định.

**src/main/resources/templates/home.html**:

~~~html
<!doctype html>
<html xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Demo</title></head>
<body>
    <h1 th:text="'DevTools Timing Demo'">Fallback</h1>
</body>
</html>
~~~

**src/main/resources/static/demo.txt**:

~~~text
DevTools static resource
~~~

Vì template có Thymeleaf attribute, việc render thực sự đi qua template engine. Cùng một template có thể dùng để thử cache=true/false, nhưng số liệu latency cần đo thực tế, không suy từ nội dung HTML.

## 8. Năm chế độ chạy tách tác động

### Chế độ A: bootRun và DevTools defaults

Chạy nếu có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu không có wrapper nhưng đã cài Gradle phù hợp:

~~~bash
gradle bootRun
~~~

Với Spring Boot 3.3.13, DevTools developmentOnly active và không bị config override, các dòng do code in xuất hiện theo thứ tự tương đối:

~~~text
EVENT_STARTED
RUNNER_BEGIN
ENV_THYMELEAF_CACHE=false
EFFECTIVE_THYMELEAF_CACHE=false
ENV_STATIC_CACHE_PERIOD=0
ENV_ERROR_STACKTRACE=always
RUNNER_END
EVENT_READY
~~~

Log Boot/Gradle và các dòng **STARTED_MS=...**, **READY_MS=...**, **JVM_UPTIME_MS=...** sẽ xen vào, giá trị thời gian tùy từng máy. Đừng assert console chỉ có những dòng ở trên.

### Chế độ B: tắt defaults nhưng giữ khả năng restart

~~~bash
./gradlew bootRun --args="--spring.devtools.add-properties=false"
~~~

Vì project không khai báo các property raw trong application.properties, các giá trị quan sát dự kiến:

~~~text
ENV_THYMELEAF_CACHE=<unset>
EFFECTIVE_THYMELEAF_CACHE=true
ENV_STATIC_CACHE_PERIOD=<unset>
ENV_ERROR_STACKTRACE=<unset>
~~~

**Environment raw khác default của binder.** Mặc định thông thường của ThymeleafProperties.cache trong Boot 3.3 là true, nên ngay cả khi Environment trả chuỗi <unset>, giá trị cuối vẫn là true. Đừng suy rằng thuộc tính không có thì tự động false.

DevTools vẫn có thể auto restart khi classpath thay đổi; cờ này **chỉ tắt nhóm development defaults**.

### Chế độ C: tắt hẳn restart support và tắt defaults

~~~bash
./gradlew bootRun --args="--demo.disable-restart --spring.devtools.add-properties=false"
~~~

Main đặt System property restart=false **trước SpringApplication.run**; đây là cách được tài liệu Boot 3.3 hướng dẫn khi muốn tắt hẳn restart classloader. Cùng lúc add-properties=false khiến defaults không được thêm. Tuy vậy DevTools dependency vẫn có thể nằm trên development classpath; đây **không phải** một runtime hoàn toàn giống packaged production.

### Chế độ D: executable JAR không có DevTools

~~~bash
./gradlew bootJar
java -jar build/libs/devtools-timing-demo-1.0.0.jar
~~~

Theo cách khai báo developmentOnly và packaging mặc định, DevTools không có trong repackaged JAR. Kết quả raw/effective Thymeleaf có thể giống B/C, nhưng đây là **đường JVM process/launcher/classpath khác** bootRun. Không đổ toàn bộ chênh lệch thời gian A với D cho DevTools.

### Chế độ E: chỉ override Thymeleaf cache

~~~bash
./gradlew bootRun --args="--spring.thymeleaf.cache=true"
~~~

Hai dòng property dự kiến:

~~~text
ENV_THYMELEAF_CACHE=true
EFFECTIVE_THYMELEAF_CACHE=true
~~~

Những defaults DevTools khác có thể còn hiệu lực. Đây là cách kiểm tra gần hơn tác động riêng của Thymeleaf template caching mà không đổi toàn bộ nhóm development defaults.

## 9. Đo startup khác first-request và warm-request

Bắt đầu process, chờ Ready rồi dùng:

~~~bash
curl -s http://localhost:8080/
curl -i http://localhost:8080/demo.txt
curl -s http://localhost:8080/actuator/metrics/application.ready.time
~~~

Actuator endpoint cuối chỉ truy cập được khi actuator đã thêm và metrics được expose, như trong project. application.ready.time là một meter tổng hợp, không phải profiler chi tiết bean.

Có thể đo độ trễ HTTP từ client bằng curl:

~~~bash
curl -s -o /dev/null -w "total=%{time_total}s\n" http://localhost:8080/
~~~

Lặp lại với cùng process, cùng content và cùng cache state, báo median/p95 từ nhiều mẫu. Curl total time bao gồm overhead HTTP/network; không phải riêng thời gian render Thymeleaf.

**Tách ba loại phép đo:**

1. **Ready duration:** từ Spring Boot event/meter.
2. **First GET sau Ready:** có thể trả giá do lazy beans, template parsing, JSP/engine init, connection warmup.
3. **Warm GET:** phản ánh caching/JIT đã hoạt động; production thường có chính sách cache khác DevTools.

Nếu spring.thymeleaf.cache=false, những request lặp có thể phải parse template nhiều lần. Nếu true, warm requests có thể hưởng cache. Nhưng không hứa chênh lệch latency bằng số ms cố định khi chưa thực hiện đo thật.

## 10. Những cách đo sai và cách sửa

### Sai: dùng restart warm như cold start

~~~text
DevTools warm restart: 0.9 s
Fresh JVM java -jar: 3.1 s
~~~

Đây là **số giả định để minh họa lỗi tư duy**, không phải benchmark đã chạy. Chênh lệch không thể dùng để kết luận production “chậm gấp hơn ba” do có nhiều biến cùng đổi.

**Cách sửa:** Mỗi mẫu cold start phải dùng **JVM/process mới**, cùng JDK, profile, tài nguyên, dependency readiness và launch mode. Ghi riêng warm restarts nếu đang đo developer loop.

### Sai: dùng JVM uptime làm Ready duration

JVM có thể tồn tại hàng giờ qua nhiều lần DevTools restart. Uptime không reset cùng ApplicationContext. Dùng Started/Ready event Duration cho **mỗi startup**, còn uptime để xác định trạng thái process warm.

### Sai: dùng thời gian bấm Save tới browser thấy CSS làm startup time

Save tới reload bao gồm IDE compilation, file watcher poll/quiet, LiveReload, network/browser. Nhiều thay đổi static/template không trigger full context restart. Phải xem có thêm ApplicationStartedEvent/ReadyEvent mới hay không, rồi đo các khoảng riêng.

### Sai: bật DEBUG log rồi so với production INFO

Log output, condition evaluation delta và IDE console I/O có overhead. So sánh phải dùng cùng logging policy hoặc ghi rõ đây là phép đo end-to-end development experience chứ không phải pure startup.

### Sai: đo bằng shell time khi web app chạy lâu

Một web app chạy 10 phút rồi mới được stop sẽ cho wall time bao gồm 10 phút phục vụ. Không gọi đó là startup duration. Thay bằng ApplicationReadyEvent timeTaken hoặc cơ chế polling readiness với mốc rõ ràng, cùng điều kiện cold start.


## 11. Ma trận đo có kiểm soát

| Run | Launch | Dev defaults | Restart classloader | Mục tiêu |
| --- | --- | --- | --- | --- |
| A | bootRun | Bật | Bật | Trải nghiệm development hiện tại |
| B | bootRun, add-properties=false | Tắt | Bật | Tác động cả nhóm development defaults |
| C | bootRun, disable-restart sớm + add-properties=false | Tắt | Tắt | Giảm tác động restart support trong dev runtime |
| D | bootJar rồi fresh java -jar | Không có DevTools | Tắt | Cold startup gần production |
| E | bootRun + Thymeleaf cache=true | Chỉ cache template bị override | Bật | Tác động cache của một engine |

**So sánh A–B** xem khác biệt khi nhóm property defaults đổi, nhưng không chỉ ra property nào gây ra khác biệt. **A–E** tương đối phù hợp hơn để kiểm tra Thymeleaf cache. **B–C** cho biết restart support có thể ảnh hưởng gì trong development classpath. **C–D** thay đổi launcher/classpath nên không được coi là chỉ đổi đúng một biến.

Mỗi lượt đo ghi:

| Trường | Vì sao phải lưu? |
| --- | --- |
| JDK, Boot, Gradle, OS | Classloading/GC/runtime khác nhau |
| App version, commit, profile | Cùng một code và cùng feature flags |
| JVM fresh hay reused | Cold khác warm restart |
| DevTools classpath, defaults, restart flags | Biến chính của bài |
| Template/static cache effective values | Chứng minh cấu hình thực |
| CPU quota, heap, GC | Tài nguyên ảnh hưởng mọi duration |
| DB/broker readiness và external I/O | Startup có thể chờ dependency |
| Started/Ready ms | Mốc SpringApplication |
| JVM uptime ms | Phát hiện process đã warm |
| First HTTP và warm p95 | Phản ánh caching/lazy/render |
| Watcher/compile delay | Chỉ cho đo developer feedback loop |

Chạy nhiều mẫu độc lập cho mỗi cấu hình, có warmup chuẩn khi đo HTTP, tính median/phân bố thay vì chỉ giữ lần tốt nhất. **Không bịa thời gian benchmark**: các con số ví dụ không thay cho kết quả từ máy của bạn.

## 12. Khi cần đo sâu hơn ở cấp bean

Có thể instrument startup bằng BufferingApplicationStartup:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setApplicationStartup(new BufferingApplicationStartup(2048));
app.run(args);
~~~

**Đây là đoạn minh họa**: cần import BufferingApplicationStartup và class MyApplication thực. setApplicationStartup cần được gọi trước run để thu những bước Spring đã instrument từ lúc đầu.

Nếu có Actuator và expose startup endpoint, **GET /actuator/startup** trả snapshot, **POST /actuator/startup** lấy rồi drain buffer. Timeline có thể giúp nhận biết bean instantiation hoặc context phase chậm; nhưng không coi timeline của warm DevTools restart tương đương cold JVM. Đừng cộng tất cả nested step durations để suy ra tổng startup vì có thể đếm trùng.

Nếu muốn hiểu JVM classloading, allocation, JIT và GC bên cạnh Spring startup, dùng **Java Flight Recorder (JFR)**. Nếu chỉ cần tổng thời gian qua nhiều deployments, dùng **application.started.time và application.ready.time** từ Micrometer/Actuator.

**READY_TIME - STARTED_TIME** có thể phản ánh khoảng giữa hai mốc trong cùng lần startup, thường chứa runners, nhưng không tự là CPU time của runner và không nên tính khi một trong hai Duration null.

## 13. Những yếu tố DevTools khác có thể làm lệch phép đo

### Log condition evaluation delta

Mỗi DevTools restart có thể in báo cáo chênh lệch condition evaluation. Nếu không muốn log này:

~~~properties
spring.devtools.restart.log-condition-evaluation-delta=false
~~~

Nó chỉ ngừng log delta, **không tắt restart**. Khối lượng log lớn trên IDE console có thể tạo thêm I/O/CPU overhead, đặc biệt khi đang đo end-to-end developer cycle.

### LiveReload

~~~properties
spring.devtools.livereload.enabled=false
~~~

Chỉ tắt LiveReload server; không làm mất restart classloader hoặc development property defaults. Không dùng việc browser tự refresh như bằng chứng context đã restart. Nếu có nhiều app DevTools cùng chạy, chỉ một LiveReload server có thể chiếm port mặc định.

### Global DevTools settings

DevTools có thể đọc file spring-boot-devtools.properties, yaml hoặc yml tại thư mục **HOME/.config/spring-boot**, hoặc vị trí tương thích cũ. Hai máy cùng source code nhưng có global settings khác có thể cho kết quả khác. Kiểm tra global configs và SPRING_DEVTOOLS_HOME hoặc spring.devtools.home khi điều tra.

### Thời gian shutdown context cũ

DevTools restart dựa vào shutdown hook của Spring context. Nếu code tắt đăng ký shutdown hook, tài liệu Boot 3.3 cảnh báo restart có thể hoạt động không đúng. Chi phí drain HTTP, SmartLifecycle.stop, executor cleanup và đóng database pool thuộc **vòng shutdown cũ**, không phải Duration của lần SpringApplication mới. Khi đo toàn chu trình Save→Ready, cần tính cả hai giai đoạn.

### Rò rỉ classloader qua restart

Một số thư viện giữ static references, ThreadLocal, thread nền hoặc deserialization cache tới class của restart classloader cũ. Điều này có thể tạo memory leak hoặc lỗi classloading chỉ thấy khi restart liên tục. Khi gặp tình huống này, thử disable restart sớm, xem quy tắc **META-INF/spring-devtools.properties** và thiết kế cleanup; đừng dùng một lần warm restart để kết luận heap production ổn định.

## 14. Chẩn đoán nhanh theo triệu chứng

| Triệu chứng | Diễn giải khả dĩ | Hành động |
| --- | --- | --- |
| bootRun có cache=false nhưng JAR lại cache=true | DevTools defaults tắt cache trong dev | Đọc Environment và ThymeleafProperties |
| spring.devtools.add-properties=false mà app vẫn restart | Cờ chỉ tắt defaults | Xem restart.enabled |
| restart.enabled=false trong properties nhưng vẫn có restart classloader | Theo tài liệu classloader có thể vẫn khởi tạo | Đặt System property trước run |
| Started in X rất nhỏ sau sửa file | JVM và base classloader đã warm | So với cold process mới |
| JVM uptime lớn mà Ready duration nhỏ | Warm restart trong cùng JVM | Phân biệt runtime và context duration |
| Sửa template không có Started event mới | Template chỉ LiveReload, không full restart | Xem resource exclusions |
| Save rồi chờ vài giây mới bắt đầu restart | IDE compile + watcher poll/quiet | Đo trước SpringApplication |
| Request template chậm trong dev | Thymeleaf cache=false, JIT/cold state | Thử cache=true trong cùng launch |
| Error response lộ stack trace | DevTools server.error.include-stacktrace=always | Không expose dev config ở production |
| WebFlux shutdown khác nhau | Reactor Netty quiet period dev=0s | Tách shutdown timing |
| Restart tăng dần RAM | Classloader/reference/resource leak có thể xảy ra | Heap dump, dừng restart để đối chiếu |
| Metrics endpoint 404 | Chưa có Actuator/exposure hoặc security khác | Kiểm tra dependency/management config |

## 15. Các hiểu nhầm thường gặp

**“Thêm DevTools làm production nhanh hơn.”** Sai: DevTools là công cụ phát triển; artifact production không nên chứa nó.

**“DevTools luôn làm mỗi ứng dụng khởi động chậm.”** Không có quy tắc tuyệt đối: defaults, classloader, caches và workload có thể làm các mốc nhanh/chậm khác nhau.

**“DevTools tự bật mọi DEBUG log.”** Sai: tài liệu gợi ý web DEBUG; mức log thực phải kiểm tra.

**“Tắt development property defaults đồng nghĩa tắt restart.”** Sai: add-properties và restart độc lập.

**“Tắt restart trong application.properties loại hoàn toàn classloader.”** Không theo mô tả Boot 3.3; muốn vô hiệu hoàn toàn thì đặt System property trước run.

**“Sau restart DevTools có JVM mới.”** Sai: base classloader/JVM vẫn có thể được dùng lại.

**“Một dòng Started in 0.7 s là thời gian bấm Save tới browser.”** Sai: IDE compile, watcher và LiveReload ở ngoài mốc đó.

**“JVM_UPTIME_MS bằng READY_MS.”** Sai: uptime process không reset qua restart.

**“Một request đầu tiên đại diện steady-state.”** Không: cache, JIT, lazy init và connection warmup có thể làm khác.

**“Cache templates tắt ở dev nhưng không ảnh hưởng benchmark.”** Có thể ảnh hưởng đáng kể đường render view; phải thử có kiểm soát.

**“Static resource change luôn restart app.”** Sai: nhiều resource bị loại khỏi restart trigger.

**“Có devtools default GraphiQL/H2 nghĩa là mọi app đã có H2/GraphQL.”** Sai: vẫn cần các integration tương ứng.

**“Bật error stacktrace luôn an toàn vì chỉ là log.”** Sai: nó có thể xuất hiện trong HTTP error response, không nên đưa ra public.

**“Đo startup bằng wall time của một web server sống 20 phút.”** Sai: đó là thời gian tồn tại tiến trình, không phải thời gian tới Ready.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** DevTools 3.3 đặt spring.thymeleaf.cache thành gì?  
**Đáp án:** false khi development defaults active.

**Câu 2.** ThymeleafProperties.cache mặc định bình thường nếu không có override?  
**Đáp án:** true trong Boot 3.3.

**Câu 3.** spring.devtools.add-properties=false có tắt restart không?  
**Đáp án:** Không, chỉ tắt nhóm defaults.

**Câu 4.** DevTools restart có tạo JVM process mới không?  
**Đáp án:** Thông thường không; JVM/base classloader được giữ lại.

**Câu 5.** Muốn tắt hẳn restart classloader phải làm gì?  
**Đáp án:** Đặt System property restart.enabled=false trước SpringApplication.run, hoặc không dùng DevTools dependency.

**Câu 6.** Ứng dụng có Ready time nhỏ nhưng process uptime một giờ có mâu thuẫn?  
**Đáp án:** Không. Một bên duration context startup, một bên tuổi JVM.

**Câu 7.** ApplicationReadyEvent.getTimeTaken có bao gồm IDE compile không?  
**Đáp án:** Không.

**Câu 8.** Vì sao không so sánh first request khi cache=false với warm request cache=true?  
**Đáp án:** Workload/caching/JIT/lazy state khác nhau.

**Câu 9.** LiveReload có đồng nghĩa context restart không?  
**Đáp án:** Không.

**Câu 10.** Khi nào DevTools error-stacktrace default gây rủi ro?  
**Đáp án:** Khi error response tiết lộ stack trace, đặc biệt nếu cấu hình dev lọt ra môi trường public.

**Câu 11.** Muốn tìm bean nào startup chậm thì dùng gì?  
**Đáp án:** ApplicationStartup/BufferingApplicationStartup, kết hợp metrics hoặc JFR.

**Câu 12.** Muốn đo cold start công bằng phải làm gì?  
**Đáp án:** Tạo JVM mới mỗi run, cùng JDK, launcher, profiles, resources và downstream conditions.

**Câu 13.** Thay property Spring Boot mà không ghi vào báo cáo benchmark có vấn đề gì?  
**Đáp án:** Kết quả khó tái lập và không thể quy nguyên nhân đúng.

**Câu 14.** Đo developer Save-to-Ready phải tính thêm gì ngoài SpringApplication?  
**Đáp án:** IDE compile, watcher, context cũ shutdown và browser reload khi có.

## 17. Checklist trước khi đưa ra kết luận hiệu năng

- [ ] Ghi đúng Boot 3.3.x, JDK, launcher và build/profile.
- [ ] Xác nhận DevTools chỉ nằm trong developmentOnly hoặc Maven optional.
- [ ] Kiểm tra default properties do DevTools thêm có thực sự active không.
- [ ] Tách add-properties, restart.enabled, livereload.enabled.
- [ ] Kiểm tra **effective configuration** chứ không chỉ raw Environment key.
- [ ] Đo StartedEvent/ReadyEvent Duration, ghi rõ nullable.
- [ ] Đọc JVM uptime chỉ để biết process warm, không gọi nó là startup time.
- [ ] Không so sánh warm DevTools restart với cold JVM production như một phép đo tương đương.
- [ ] Đo first/warm request riêng, với template/static cache policy rõ.
- [ ] Điều khiển JIT, GC, CPU/RAM, connection pool và readiness dependency.
- [ ] Phân biệt thời gian build/IDE watcher với thời gian chạy SpringApplication.
- [ ] Lặp thí nghiệm, báo median/percentile và lưu metadata.
- [ ] Khi cần, dùng ApplicationStartup, Actuator metrics hoặc JFR để lý giải.
- [ ] Không bật remote DevTools và thông tin debug/stacktrace trên production.

**Kết luận:** DevTools thay đổi **property defaults để dễ lập trình**, tách **base/restart classloader** để khởi động lại nhanh và có **LiveReload** phục vụ trình duyệt. Những thay đổi này ảnh hưởng cache, logs, lifecycle, classloading và cách định nghĩa timing. Trong Spring Boot 3.3, **spring.devtools.add-properties=false** chỉ tắt development defaults; để tắt hẳn restart classloader cần System property trước run hoặc loại module DevTools. Muốn benchmark chính xác phải so sánh cùng ranh giới **Started/Ready, cold/warm process, cache state và launch mode**; không dùng một lần restart nhanh để kết luận về production cold start.

### Tài liệu tham khảo

- [Spring Boot 3.3 — Developer Tools](https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html)
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — Startup Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
