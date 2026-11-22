# FlightRecorderApplicationStartup và kết hợp với Java Flight Recorder trong Spring Boot

## 1. Vấn đề cần giải quyết: ứng dụng khởi động chậm ở đâu?

Một ứng dụng Spring Boot có thể cần vài giây, hàng chục giây hoặc lâu hơn để đạt trạng thái sẵn sàng. Thời gian đó bao gồm nhiều công việc: nạp lớp Java, chuẩn bị cấu hình, quét package, phân tích @Configuration, đăng ký BeanDefinition, tạo singleton beans, thiết lập kết nối, khởi động embedded web server và thực thi startup runners.

Khi thời gian khởi động tăng, dòng log kiểu **Started Application in 8.4 seconds** chỉ cho biết kết quả tổng quát. Nó không trả lời được:

- Bao nhiêu thời gian được dùng để **Spring quét package**?
- Bean nào **khởi tạo chậm**?
- Có phải JVM đang bận **class loading, JIT compilation, garbage collection**?
- Spring đang thực thi code nghiệp vụ hay đang chờ **database, mạng, file I/O**?
- Một startup step chậm có phải vì chính nó tốn CPU, hay vì bị **GC pause**/blocked I/O trong lúc chạy?
- Nếu đã tối ưu một bean, startup toàn ứng dụng có thực sự nhanh lên không?

Spring Framework cung cấp **ApplicationStartup** và **StartupStep** để đánh dấu các bước trong container. Một implementation là **FlightRecorderApplicationStartup**, có nhiệm vụ phát những Spring startup steps thành **Java Flight Recorder (JFR) events**. Bằng cách ghi các event Spring **cùng phiên JFR** với các event của JVM, ta có thể đối chiếu **Spring làm gì** với **JVM đang trải qua điều gì**.

**Thông điệp chính:** FlightRecorderApplicationStartup mô tả các bước startup được instrument của Spring; Java Flight Recorder ghi thêm dấu vết JVM và runtime. Hai lớp dữ liệu bổ sung cho nhau trong một file **.jfr** để phục vụ phân tích thời gian khởi động.

Bài này dựa trên **Java 17+**, **Spring Boot 3.5.x** và **Spring Framework 6.2.x**. Các API trọng tâm thuộc Spring Framework, không phải một dependency bắt buộc của Spring Boot Actuator.

## 2. Phân biệt ba khái niệm gần nhau

| Thành phần | Thuộc về | Trách nhiệm |
| --- | --- | --- |
| **ApplicationStartup** | Spring Framework, package **org.springframework.core.metrics** | Abstraction để bắt đầu và kết thúc các bước startup |
| **StartupStep** | Spring Framework | Đối tượng ghi tên, id, parent id, tags và thời điểm kết thúc một bước |
| **FlightRecorderApplicationStartup** | Spring Framework, package **org.springframework.core.metrics.jfr** | Implementation của ApplicationStartup, xuất StartupStep dưới dạng JFR event |
| **Java Flight Recorder (JFR)** | JDK/JVM | Ghi event có timestamp/duration liên quan đến JVM, hệ thống và các custom events |
| **JDK Mission Control (JMC)** | Công cụ phân tích JFR, cài độc lập khi cần | Giao diện trực quan để mở file .jfr và xem timeline/profiling |
| **BufferingApplicationStartup** | Spring Boot | Lưu các StartupStep trong buffer, có thể làm nguồn dữ liệu cho Actuator startup endpoint |

**ApplicationStartup không phải JVM profiler.** Nó đo những bước được Spring hoặc code ứng dụng đánh dấu. **JFR không tự hiểu bean, @Configuration và context refresh** nếu không có Spring instrumentation hoặc một cơ chế event khác cung cấp ngữ nghĩa đó.

Theo mặc định, Spring Framework có implementation **ApplicationStartup.DEFAULT** kiểu no-op để tránh chi phí ghi startup steps khi không bật công cụ theo dõi cụ thể. Muốn có Spring startup events trong JFR, ta phải **cấu hình FlightRecorderApplicationStartup trước khi Spring khởi tạo context** và **bật một phiên ghi JFR đủ sớm**.

### Java Flight Recorder có cần một thư viện Maven riêng không?

**Không** cho JDK 17+ phổ biến có JFR. JFR được tích hợp vào JDK hỗ trợ. Trong Spring Boot 3.5, **spring-core** đã có trên classpath thông qua các starters thông thường, nên **FlightRecorderApplicationStartup không yêu cầu thêm một thư viện JFR bên ngoài**.

Điều cần phân biệt:

- **JVM/JDK** cung cấp flight recording.
- **Spring Framework** cung cấp FlightRecorderApplicationStartup.
- **JDK Mission Control** là công cụ riêng để xem và phân tích bản ghi, không nhất thiết đi kèm JDK.
- **Spring Boot Actuator** không cần thiết để ghi startup steps vào JFR.

## 3. StartupStep hoạt động ra sao?

Mỗi **StartupStep** đánh dấu một khoảng công việc:

~~~text
ApplicationStartup.start("demo.catalog.initialize")
                |
                +--> tạo StartupStep
                |    name, id, parentId
                |
                +--> tag("component", "catalog")
                |
                +--> thực hiện công việc
                |
                +--> step.end()
                       |
                       +--> kết thúc đo bước
                       +--> JFR event có thể được commit
~~~

Thông thường, tên bước theo namespace dạng chấm:

- **spring.context.refresh**
- **spring.beans.instantiate**
- **spring.context.config-classes.parse**
- **demo.catalog.initialize**
- **demo.runner.validate**

Tên bắt đầu bằng **spring.** được Spring Framework dành cho instrumentation nội bộ. Khi viết custom step, hãy chọn namespace riêng như **demo.**, **app.** hoặc tên module, không tự đặt custom step vào **spring.***.

Interface cơ bản:

~~~java
ApplicationStartup startup = /* một instance được cấu hình */;
StartupStep step = startup.start("demo.catalog.initialize");
step.tag("component", "catalog");
try {
    // Khởi tạo dữ liệu của ứng dụng.
} finally {
    step.end();
}
~~~

Đây là **mảnh code minh họa**, không phải file Java độc lập; cần import các interface, khai báo biến startup và logic ở giữa. Trong chương trình hoàn chỉnh ở mục 7, Spring inject đúng **ApplicationStartup** được cấu hình.

### Vì sao phải gọi end()?

Khi gọi **start(...)**, step bắt đầu được đo. Phương thức **end()** báo rằng công việc đã kết thúc và cho phép implementation ghi kết quả. Với FlightRecorderApplicationStartup, event JFR tương ứng được commit khi step hoàn tất theo cơ chế ghi.

**Không quên end() nếu có exception.** Dùng try/finally để tránh làm mất thông tin khi khởi tạo thất bại:

~~~java
StartupStep step = startup.start("demo.external-config.load");
try {
    loadConfig();
} finally {
    step.end();
}
~~~

Mảnh code này giả định có startup và loadConfig; phần quan trọng là **finally**. Nếu một operation ném lỗi, step vẫn được kết thúc và JFR có cơ hội ghi duration. Tuy nhiên, **JFR file có được ghi xuống đĩa khi JVM exit/failure hay không** còn phụ thuộc cách bắt đầu recording, dumponexit, disk/quota và loại sự cố JVM.

### Tags và giới hạn của JFR

**StartupStep.tag(key, value)** thêm metadata có ích để phân loại: bean name, module, source hoặc loại thao tác. FlightRecorderApplicationStartup serialize những tags thành **một thuộc tính String** vì JFR event fields chỉ hỗ trợ các loại phù hợp với định dạng của nó.

Không nên nhét vào tag:

- Mật khẩu, token, chuỗi kết nối chứa secrets.
- Nội dung request hoặc dữ liệu cá nhân.
- Payload JSON lớn.
- ID với cardinality quá cao, không có giá trị phân tích.
- Bản dump toàn bộ Environment hoặc System Properties.

Tags chủ yếu dùng để nhận dạng **bước và ngữ cảnh**, không phải hệ thống lưu log nghiệp vụ hoặc tracing phân tán.

## 4. Những bước Spring có thể instrument

Spring Framework 6.2 có danh sách các startup steps của core container. Một số ví dụ thường gặp:

| Startup step | Ý nghĩa |
| --- | --- |
| **spring.context.refresh** | Giai đoạn làm mới ApplicationContext |
| **spring.context.base-packages.scan** | Quét những base packages |
| **spring.context.config-classes.parse** | Phân tích các configuration classes |
| **spring.context.config-classes.enhance** | CGLIB enhancement của @Configuration khi cần |
| **spring.context.beandef-registry.post-process** | Chạy BeanDefinitionRegistryPostProcessor |
| **spring.context.bean-factory.post-process** | Chạy BeanFactoryPostProcessor |
| **spring.context.beans.post-process** | Giai đoạn bean post processing |
| **spring.beans.instantiate** | Tạo bean và những dependency của bean |
| **spring.beans.smart-initialize** | SmartInitializingSingleton callbacks |

Đây là **ví dụ tên bước trong Spring Framework 6.2**, không phải cam kết mọi bản ghi có đủ tất cả bước ở mọi ứng dụng. Tên và tags của các startup steps nội bộ **không thuộc public API contract ổn định**; có thể thay đổi giữa patch/major versions.

**Một bean có thể xuất hiện nhiều lần trong các bước liên quan**, và các khoảng thời gian có thể lồng nhau. Không cộng tất cả durations theo tên rồi kết luận đó là tổng thời gian khởi động. Các bước cha có thể bao gồm thời gian của bước con.

Để xác định một bean chậm, hãy xem **beanName/beanType tags khi được ghi**, thứ tự/timeline, duration và dependency graph. Một bean trông chậm có thể đang chờ một bean khác hoặc remote service, nên cần dùng JFR JVM events và log bổ sung để xác minh.

## 5. Thứ tự khởi động: đặt instrumentation đúng thời điểm

Trong Spring Boot 3.5, một startup điển hình:

~~~text
main(String[] args)
      |
      +--> Tạo SpringApplication
      |
      +--> setApplicationStartup(
      |        new FlightRecorderApplicationStartup())
      |        PHẢI XẢY RA TRƯỚC run()
      |
      +--> SpringApplication.run(args)
      |        |
      |        +--> Environment / ConfigData preparation
      |        +--> Tạo và chuẩn bị ApplicationContext
      |        +--> Load bean definitions
      |        +--> Context refresh
      |        |      Bean factory, config parsing, singleton init,
      |        |      web server nếu là web app
      |        +--> ApplicationStartedEvent
      |        +--> ApplicationRunner/CommandLineRunner
      |        +--> ApplicationReadyEvent
      |
      +--> run() trả về nếu startup thành công
~~~

Bản thân **ApplicationStartup** không phải một application event. Nó là **instrumentation strategy** mà SpringApplication và ApplicationContext sử dụng để đánh dấu nhiều bước. Những event như **ApplicationStartedEvent**, **ApplicationReadyEvent** có ý nghĩa lifecycle riêng; chúng không tự động tương đương một StartupStep có cùng tên.

Đặt FlightRecorderApplicationStartup trong **@Bean** được tạo khi refresh thường là **quá muộn** để đo phần Environment, context preparation và những bước sớm nhất. Cách rõ ràng nhất:

~~~java
SpringApplication app =
        new SpringApplication(MyApplication.class);

app.setApplicationStartup(
        new FlightRecorderApplicationStartup());

app.run(args);
~~~

Đây là mảnh code minh họa; MyApplication là class ứng dụng của bạn, với imports cần thiết. **SpringApplication.run(MyApplication.class, args)** dạng static tiện lợi nhưng không cho ta chèn setApplicationStartup vào instance trước khi chạy; nên chuyển sang instance-based SpringApplication khi cần JFR startup tracking.

### Phân biệt thời gian startup và readiness

**ApplicationStartedEvent** xảy ra sau refresh, trước runners. **ApplicationReadyEvent** xảy ra sau khi runners hoàn tất. Vì vậy:

- Thời gian context refresh khác thời gian chuẩn bị để nhận traffic.
- Một bước custom trong ApplicationRunner có thể là phần quan trọng của startup.
- Một runner tạo background Future rồi return ngay **không bảo đảm** Spring Boot chờ Future trước Ready.
- Nếu tác vụ warm-up bắt buộc chưa xong, không nên gọi ứng dụng ready chỉ vì các bean đã được tạo.
- JFR có thể giúp chỉ ra chi phí runner nếu bạn đánh dấu custom StartupStep thích hợp; không nên giả định mọi xử lý trong runner đều có sẵn step chi tiết tương ứng.

## 6. Bắt đầu JFR đúng cách để không bỏ lỡ startup

### 6.1. Bật JFR khi khởi động JVM

Ví dụ Java 17+:

~~~bash
java -XX:StartFlightRecording=filename=startup.jfr,settings=profile,dumponexit=true \
  -jar target/jfr-startup-demo-0.0.1-SNAPSHOT.jar
~~~

**-XX:StartFlightRecording** là JVM option, vì vậy nó **phải đứng trước -jar**. Đặt option sau tên JAR sẽ khiến Spring Boot xem như application argument, không bật JFR theo ý định.

Giải thích các tham số:

| Tham số | Tác dụng |
| --- | --- |
| **filename=startup.jfr** | Đường dẫn file ghi kết quả, tương đối với working directory hiện hành |
| **settings=profile** | Dùng cấu hình JFR profiling, thường ghi nhiều sự kiện hơn default |
| **dumponexit=true** | Dump recording khi JVM thoát theo đường có thể chạy shutdown bình thường |
| **duration=15s** (tùy chọn) | Giới hạn khoảng thời gian ghi tối đa khoảng 15 giây nếu JVM tiếp tục chạy |
| **delay=...** (nếu dùng) | Hoãn bắt đầu recording; không phù hợp nếu muốn đo startup ngay từ đầu |

Ví dụ cho một web application chạy lâu:

~~~bash
java -XX:StartFlightRecording=filename=startup.jfr,settings=profile,duration=30s \
  -jar target/your-service.jar
~~~

Lệnh thứ hai là **mẫu**, cần thay your-service.jar bằng JAR thật. File được tạo khi bản ghi kết thúc theo duration, nếu JVM/recording ghi thành công. Dùng duration 30s chỉ khi 30 giây đủ bao trùm startup cần quan sát; với cold start lâu hơn, tăng duration hoặc dùng dumponexit/cơ chế dump chủ động.

**Lưu ý quan trọng:** nếu chạy JFR khi ứng dụng đã khởi động xong bằng jcmd, bạn **không thể ghi lại những event startup đã xảy ra trong quá khứ**. Muốn đo cold startup, phải bật recording từ lúc JVM bắt đầu hoặc trước những bước cần đo.

### 6.2. Vì sao dùng settings=profile?

JDK có các cấu hình ghi sẵn như **default** và **profile**:

- **default:** phù hợp các bản ghi liên tục với chi phí tương đối thấp.
- **profile:** thu thập thêm thông tin phục vụ profiling, hữu ích khi điều tra CPU, allocation, GC và thời gian chờ.

Độ phủ event thực tế phụ thuộc JDK version và .jfc settings. **Không phải mọi JVM event đều bật sẵn**; có thể cần bật event/threshold cụ thể bằng cấu hình JFR được thiết kế riêng.

Với các hệ thống nhạy về overhead và dung lượng, benchmark chi phí recording trước khi bật profile ở mọi replica. Dùng file rotation, giới hạn size/age và chính sách lưu trữ phù hợp.

### 6.3. Có cần JDK thay vì JRE?

JFR được triển khai trong runtime JDK hiện đại, nhưng các tiện ích CLI như **jfr**, **jcmd** và **jstack** thường có trong **JDK đầy đủ**. Một container image tối giản hoặc custom jlink image có thể không có các công cụ CLI.

Trong trường hợp đó, có thể ghi **startup.jfr** từ JVM trong container rồi **copy file sang máy có JDK đầy đủ** để chạy **jfr summary/print**, hoặc mở bằng JDK Mission Control.

## 7. Ví dụ Maven hoàn chỉnh: Spring Boot 3.5 + FlightRecorderApplicationStartup

Mục tiêu ví dụ:

1. Chạy trên **Java 17+**, không cần web server.
2. Cấu hình **FlightRecorderApplicationStartup trước SpringApplication.run**.
3. Có một @Bean tạo dữ liệu catalogue và đánh dấu **demo.catalog.initialize**.
4. Có một ApplicationRunner kiểm tra dữ liệu và đánh dấu **demo.runner.validate**.
5. Cho chương trình thoát bình thường để **dumponexit=true** có thể ghi file .jfr.
6. Dùng jfr summary/print để tìm các bước Spring và so sánh chúng với event JVM.

### 7.1. Cấu trúc project

~~~text
jfr-startup-demo/
  pom.xml
  src/
    main/
      java/
        com/example/demo/JfrStartupDemoApplication.java
      resources/
        application.properties
~~~

Nếu tạo qua Spring Initializr, project còn có **mvnw** và **mvnw.cmd**. Ví dụ dùng Maven cài sẵn, không cần database, Spring Web hay Actuator.

### 7.2. POM hoàn chỉnh

Tạo file **pom.xml**:

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
    <artifactId>jfr-startup-demo</artifactId>
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

**spring-boot-starter** đủ mang Spring Framework core, các Spring Boot bootstrap APIs và những dependencies cần thiết. Không cần một "JFR starter" riêng hoặc thêm dependency spring-boot-starter-actuator cho bài tập này.

Nếu sử dụng patch Boot 3.5.x khác, thay đúng phiên bản parent/BOM, không override ngẫu nhiên Spring Framework. Mẫu build đòi hỏi Maven repository có thể cung cấp dependencies và JDK 17 trở lên.

### 7.3. application.properties

Tạo **src/main/resources/application.properties**:

~~~properties
spring.application.name=jfr-startup-demo
spring.main.web-application-type=none

# Không cần HTTP server hoặc Actuator cho bản ghi JFR.
# Demo dùng StartupStep được instrument từ Java code.
~~~

**Không có property tiêu chuẩn spring.application-startup=flight-recorder** trong Spring Boot 3.5 để thay thế cấu hình programmatic ở bài này. Tránh tự đoán tên property rồi cho rằng instrumentation đã bật.

### 7.4. File Java hoàn chỉnh

Tạo **src/main/java/com/example/demo/JfrStartupDemoApplication.java**:

~~~java
package com.example.demo;

import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.metrics.ApplicationStartup;
import org.springframework.core.metrics.StartupStep;
import org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup;

@SpringBootApplication
public class JfrStartupDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(JfrStartupDemoApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);

        // Cài đặt instrumentation TRƯỚC khi tạo/refresh context.
        app.setApplicationStartup(
                new FlightRecorderApplicationStartup());

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("RUN_RETURNED active="
                    + context.isActive());
        }
    }

    @Bean
    Catalog catalog(ApplicationStartup applicationStartup) {
        StartupStep step =
                applicationStartup.start("demo.catalog.initialize");
        step.tag("component", "catalog");
        System.out.println("CATALOG_BEGIN");

        try {
            // Mô phỏng công việc initialization 300 ms.
            TimeUnit.MILLISECONDS.sleep(300);
            return new Catalog(3);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Catalog initialization interrupted", ex);
        } finally {
            step.end();
            System.out.println("CATALOG_END");
        }
    }

    @Bean
    ApplicationRunner warmupRunner(
            Catalog catalog, ApplicationStartup applicationStartup) {

        return args -> {
            StartupStep step =
                    applicationStartup.start("demo.runner.validate");
            step.tag("component", "runner");
            System.out.println("RUNNER_BEGIN items=" + catalog.items());

            try {
                // Mô phỏng validation cần làm trước ApplicationReadyEvent.
                TimeUnit.MILLISECONDS.sleep(120);
                System.out.println("RUNNER_DONE");
            } finally {
                step.end();
            }
        };
    }

    record Catalog(int items) {
    }
}
~~~

### 7.5. Kiểm tra khả năng biên dịch

- **package com.example.demo** khớp đường dẫn Java.
- **JfrStartupDemoApplication** là public class và tên file tương ứng.
- **record Catalog(int items)** thuộc Java 17, cho accessor **items()**.
- **FlightRecorderApplicationStartup** đúng package **org.springframework.core.metrics.jfr**.
- **ApplicationStartup** và **StartupStep** đúng package **org.springframework.core.metrics**.
- **SpringApplication.setApplicationStartup(...)** được Spring Boot 3.5 hỗ trợ.
- **ApplicationStartup** có thể được inject vào Spring-managed components theo Spring Framework Reference.
- **StartupStep.start(...), tag(...), end()** đúng contract JavaDoc.
- **TimeUnit.MILLISECONDS.sleep(...)** có thể ném InterruptedException; method tạo bean bắt và xử lý, còn **ApplicationRunner.run(ApplicationArguments)** có **throws Exception** nên lambda của runner có thể propagate InterruptedException.
- **try-with-resources** với ConfigurableApplicationContext hợp lệ vì nó implements Closeable.
- Chương trình không đòi hỏi cổng 8080, database, scheduler hay Actuator.

**Quan trọng:** phương thức @Bean và runner được chạy ở các mốc khác nhau. @Bean catalog được tạo trong context refresh, còn **ApplicationRunner** chỉ được gọi sau refresh. Các custom steps của demo phản ánh hai thời điểm thực sự khác nhau.

### 7.6. Build và ghi JFR

Từ thư mục project:

~~~bash
java -version
mvn -version
mvn clean package

java -XX:StartFlightRecording=filename=startup.jfr,settings=profile,dumponexit=true \
  -jar target/jfr-startup-demo-0.0.1-SNAPSHOT.jar
~~~

Windows PowerShell/cmd: viết lệnh **java** trên **một dòng** (không dùng backslash để nối dòng). Nếu có Maven Wrapper do Initializr cung cấp, dùng **./mvnw clean package** trên Linux/macOS hoặc **.\mvnw.cmd clean package** trên Windows.

Một số stdout quan trọng **do chính ứng dụng in**:

~~~text
CATALOG_BEGIN
CATALOG_END
RUNNER_BEGIN items=3
RUNNER_DONE
RUN_RETURNED active=true
~~~

Maven/Boot/JFR cũng có thể ghi các log khác xen kẽ. Đây chỉ là các marker của ứng dụng, không phải snapshot toàn console. Thời gian sleep 300 ms và 120 ms mang tính giả lập; thời gian event thực tế gồm overhead nhỏ và ảnh hưởng của scheduler/JVM.

**Vì sao chương trình tự đóng context?** Ứng dụng non-web không cần chạy dài hạn trong ví dụ. Khi SpringApplication.run trả về và rời **try-with-resources**, Java đóng ApplicationContext, main kết thúc; JFR với **dumponexit=true** có cơ hội dump recording ra **startup.jfr**.

**Điều kiện để có file:** runtime hỗ trợ JFR, JVM option được chấp nhận, thư mục đích cho phép ghi, JVM có thể dump recording trên exit, và process không bị cưỡng bức kill trước khi ghi. Không khẳng định file .jfr xuất hiện trong trường hợp SIGKILL hoặc hết dung lượng đĩa.

## 8. Phân tích file .jfr bằng công cụ có trong JDK

### 8.1. Kiểm tra recording có tồn tại và chứa dữ liệu

Sau khi chạy demo:

~~~bash
jfr summary startup.jfr
~~~

Lệnh JDK **jfr summary** liệt kê tổng quan recording, số event theo từng event type và kích thước ghi tương ứng. **Kết quả sẽ thay đổi theo JDK, máy, startup conditions và JFR configuration**, nên không đưa những con số cố định như số byte, GC count hay tổng startup duration.

Trong summary, tìm nhóm event của Spring, thường có tên:

~~~text
org.springframework.core.metrics.jfr.FlightRecorderStartupEvent
~~~

Cũng có thể thấy các event liên quan tới **jdk.Compilation**, **jdk.GarbageCollection**, **jdk.CPULoad**, **jdk.ClassLoad** hoặc nhiều loại khác, tùy cấu hình và điều kiện thực tế.

**Một JFR file có event type định nghĩa nhưng không có instance không chứng minh app không tạo step.** Cần kiểm tra recording có bắt đầu đủ sớm, event có bật trong settings, step có gọi end và có điều kiện lọc threshold không.

### 8.2. Lọc startup events chính xác

Tên event của implementation Spring Framework 6.2 là:

~~~text
org.springframework.core.metrics.jfr.FlightRecorderStartupEvent
~~~

Dùng tên fully qualified:

~~~bash
jfr print --events org.springframework.core.metrics.jfr.FlightRecorderStartupEvent startup.jfr
~~~

Để lấy JSON cho công cụ xử lý:

~~~bash
jfr print --json --events org.springframework.core.metrics.jfr.FlightRecorderStartupEvent startup.jfr
~~~

**Đừng dùng tên đoán mò như StartupEvent rồi kết luận không có dữ liệu**. Bộ lọc **--events** phải khớp tên event thật trong file, không phải tên interface ApplicationStartup hay tên Java class SpringApplication.

Khi nghi ngờ, dùng:

~~~bash
jfr metadata startup.jfr
~~~

để xem các event definitions thực có trong recording. Có thể dùng **jfr summary** và tìm tên Spring để tránh quét toàn bộ file bằng mắt.

**Chú ý phiên bản:** nếu dùng Spring Framework khác hoặc cơ chế JFR instrumentation khác, tên event có thể thay đổi. Hãy dựa vào metadata của bản ghi thực tế và code/version đang chạy thay vì hardcode tên từ một bài viết bất kỳ.

### 8.3. Nhận diện custom steps

Trong output của **jfr print**, tìm tên:

~~~text
demo.catalog.initialize
demo.runner.validate
~~~

Đây là hai tên do chính demo tự tạo, không phụ thuộc vào những bước nội bộ Spring nào được instrument. Với recording thành công và event settings phù hợp, chúng giúp xác nhận rằng cấu hình FlightRecorderApplicationStartup đã đi vào code ứng dụng.

**Không cố định JSON field names/value layout trong script nếu chưa kiểm tra jfr metadata của JDK và Spring version thực tế.** Tags có thể được serialize thành chuỗi, và output JFR có timestamp/duration cùng metadata theo định dạng của công cụ.

### 8.4. Xem JVM events để tìm nguyên nhân

Có thể lọc từng loại event nếu có trong file:

~~~bash
jfr print --events jdk.GarbageCollection startup.jfr
jfr print --events jdk.CPULoad startup.jfr
jfr print --events jdk.ClassLoad startup.jfr
~~~

Nếu loại event không được bật trong .jfc settings hoặc không xảy ra trong recording window, output có thể trống. **Không xem output trống là bằng chứng JVM hoàn toàn không có GC, CPU hoạt động hay class loading**.

Khi tìm nguyên nhân startup chậm:

1. Tìm StartupStep có duration cao.
2. Xác định nó có bao gồm các step con không.
3. Đặt interval của step đó lên timeline JVM.
4. Quan sát trong cùng khoảng có GC pause, compilation, class loading, allocation, socket I/O hoặc thread waiting không.
5. Xem stack trace/sampling event khi được cấu hình và có data.
6. Tái hiện nhiều lần để phân biệt vấn đề lặp lại với một lần cold-start bất thường.

**JFR correlation** mới là lợi ích chính: Spring nói **đang làm gì**, JVM giúp giải thích **vì sao thời gian trôi qua**.

## 9. Mở file bằng JDK Mission Control

**JDK Mission Control (JMC)** là công cụ GUI để phân tích recordings. JMC thường được cài riêng; đừng giả định mọi image OpenJDK/JRE đều có sẵn chương trình này.

Quy trình:

1. Mở JDK Mission Control trên máy có môi trường GUI.
2. Mở file **startup.jfr** bằng chức năng mở Flight Recording.
3. Tìm các JFR events thuộc category **Spring Application**, nhãn liên quan đến **Startup Step**.
4. Lọc các event có tên bước **spring.context.refresh**, **spring.beans.instantiate**, **demo.catalog.initialize** và **demo.runner.validate**.
5. Quan sát **start time**, **duration**, **thread** và metadata (nếu có).
6. So sánh với những event JVM như **Garbage Collections**, **Threads**, **Class Loading** và **Method Profiling**, tùy bản JMC/JDK.
7. Ghi nhận giả thuyết, thay đổi đúng một nguyên nhân có khả năng ảnh hưởng rồi ghi recording mới để so sánh.

Tên tab/menu của JMC có thể thay đổi giữa các phiên bản. Điều cốt lõi là tìm event category/names của Spring và mở timeline JVM tương ứng, không phụ thuộc vào một ảnh giao diện cụ thể.

### Cách đọc một tình huống giả định

Giả sử recording cho thấy:

~~~text
demo.catalog.initialize       ~306 ms
demo.runner.validate          ~124 ms
spring.context.refresh        ~900 ms
jdk.GarbageCollection         ~120 ms trong cùng thời gian
~~~

**Đây là số liệu minh họa**, không phải output thực tế của ví dụ. Cần phân tích:

- **demo.catalog.initialize** giả lập sleep 300ms; thời gian lớn không chứng minh CPU bận.
- **demo.runner.validate** giả lập sleep 120ms; cũng chủ yếu là thời gian chờ.
- **spring.context.refresh** là bước rộng, có thể bao gồm nhiều bước con; **không cộng 900 + 306** rồi coi là tổng không trùng.
- GC 120ms nếu thực sự chồng lên startup step có thể đóng góp vào elapsed time; phải kiểm tra **timestamp và độ trùng**.
- Nếu muốn tối ưu, thay sleep giả lập bằng tracing thật của workload, sau đó đo lại với cùng cấu hình và tải.

### Vì sao không thể so sánh chỉ bằng giá trị Duration?

Duration là **wall-clock elapsed time** của khoảng step, không phải chỉ số CPU riêng của bean. Một bước 500 ms có thể tiêu:

- 500 ms CPU.
- 5 ms CPU + 495 ms đợi database.
- 350 ms chờ monitor/thread lock.
- Một phần thời gian bị GC pause.
- Thời gian đợi I/O hoặc tài nguyên bên ngoài.

Để kết luận bottleneck, cần event JVM bổ sung và/hoặc ứng dụng log/metrics theo đúng khoảng thời gian.

## 10. FlightRecorderApplicationStartup và BufferingApplicationStartup khác nhau

Đây là bẫy cấu hình đáng chú ý khi đọc tài liệu Spring Boot.

| Đặc điểm | FlightRecorderApplicationStartup | BufferingApplicationStartup |
| --- | --- | --- |
| Nơi cung cấp | **Spring Framework** | **Spring Boot** |
| Nơi lưu dữ liệu | JFR recording session/file | Buffer trong memory |
| Công dụng chính | Profile và correlate với JVM events | Quan sát startup steps qua buffer/endpoint |
| Cần JVM JFR recording? | **Có** để thu event ra file .jfr | Không |
| Cần Spring Boot Actuator? | Không | Chỉ cần Actuator nếu muốn HTTP startup endpoint |
| Kết quả | JFR events có timestamps/duration/tags | Dữ liệu steps có thể xuất JSON qua Actuator |
| Rủi ro chính | JFR start quá muộn, settings thiếu, file/overhead | Buffer capacity không đủ, thiếu endpoint/exposure |
| Phù hợp | Điều tra startup slow và JVM-level root causes | Theo dõi thứ tự/step data và tích hợp công cụ quan sát |

Cấu hình BufferingApplicationStartup trong Boot:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

SpringApplication app =
        new SpringApplication(MyApplication.class);

app.setApplicationStartup(
        new BufferingApplicationStartup(2048));

app.run(args);
~~~

Đây là **mảnh Java minh họa**, giả định MyApplication đã được định nghĩa. Buffer capacity 2048 chỉ là ví dụ; chọn theo số bước startup thực tế và tiêu thụ bộ nhớ.

### Actuator /actuator/startup có tự xuất file JFR không?

**Không.** Actuator startup endpoint là cách lấy startup data từ **BufferingApplicationStartup** theo cơ chế Boot hỗ trợ. Chỉ thêm dependency Actuator và bật endpoint không có nghĩa JVM đã ghi file .jfr hoặc FlightRecorderApplicationStartup đang hoạt động.

Ngược lại, khi cấu hình FlightRecorderApplicationStartup như bài này, dữ liệu được gửi vào **JFR**, không đồng nghĩa **/actuator/startup** tự có nội dung buffer tương đương.

SpringApplication nhận **một ApplicationStartup strategy tại một thời điểm**. Nếu muốn vừa có JFR vừa có buffer, cần thiết kế và kiểm chứng giải pháp composite/custom instrumentation thích hợp; không gán liên tiếp hai implementation rồi tưởng cả hai đều hoạt động. Lệnh setApplicationStartup sau cùng sẽ thay thế trước đó.

### Khi nào chọn cái nào?

- **Muốn xem JVM GC, class loading, CPU profiling trùng với Spring startup:** chọn **FlightRecorderApplicationStartup + JFR**.
- **Muốn startup steps dạng JSON và tích hợp Actuator:** cân nhắc **BufferingApplicationStartup** với endpoint startup phù hợp.
- **Chỉ cần biết tổng startup time:** có thể dùng log Spring Boot + ApplicationStarted/Ready metrics, không nhất thiết bật JFR.
- **Muốn phân tích liên tục trong production:** cân nhắc JFR default settings, giới hạn recording và chính sách bảo mật/retention riêng.

## 11. Ghi JFR bằng jcmd khi JVM đang chạy

JDK có công cụ **jcmd** để quản lý Flight Recording trên JVM đang chạy:

~~~bash
jcmd <PID> JFR.check
jcmd <PID> JFR.start name=investigate settings=profile
jcmd <PID> JFR.dump name=investigate filename=runtime.jfr
jcmd <PID> JFR.stop name=investigate
~~~

Các lệnh trên là **mẫu thao tác CLI**: thay **<PID>** bằng PID thật. Trong Markdown, dấu góc là placeholder cú pháp; khi chạy trong shell, cần gõ **số PID**, ví dụ 12345, không gõ dấu ngoặc nhọn/góc.

**Điểm giới hạn:** nếu jcmd được gọi **sau khi Spring Boot đã Ready**, bản ghi runtime mới **không chứa các StartupStep đã được phát trong startup trước đó**. Vì vậy để học bài **đo khởi động**, cách mặc định nên là JVM option **-XX:StartFlightRecording** ngay khi process launch.

Nếu cần dump recording đang chạy mà đã được bật từ đầu:

~~~bash
jcmd 12345 JFR.check
jcmd 12345 JFR.dump filename=checkpoint.jfr
~~~

**12345** là PID giả định để minh họa cú pháp. jcmd có thể bị hạn chế bởi permission, container namespace, attach mechanism hoặc JDK/runtime distribution. Không cần jcmd cho bài demo non-web vì chương trình tự thoát và **dumponexit=true**.

### JVM thoát bất thường thì sao?

- **Process exit có shutdown hook/dump bình thường:** thường có cơ hội ghi file nếu configured.
- **SIGKILL, OOM-killer, container bị force-kill:** không bảo đảm dumponexit chạy.
- **Filesystem read-only hoặc quota đầy:** có thể không ghi được file.
- **JFR bị tắt hoặc runtime không hỗ trợ:** không có event file theo kỳ vọng.

Trong môi trường nghi ngờ startup crash, có thể thiết kế ghi JFR ra disk sớm và cơ chế thu thập phù hợp, nhưng không phụ thuộc hoàn toàn vào dumponexit để bảo tồn dữ liệu sau kill cưỡng bức.

## 12. Tối ưu hóa sau khi tìm bottleneck

JFR giúp **đặt giả thuyết có dữ liệu**, nhưng điều chỉnh phải đi theo nguyên nhân được xác nhận.

### 12.1. Chậm do classpath và configuration scanning

Nếu bước quét package hoặc phân tích configuration classes lớn:

- Hạn chế **@ComponentScan** quét phạm vi không cần thiết.
- Kiểm tra starter/autoconfiguration không còn dùng.
- Đo class loading/JIT và context parse phases.
- Tránh loại bỏ auto-configuration bừa bãi chỉ vì thấy nhiều bean; xác minh lợi ích và ảnh hưởng tính năng.

### 12.2. Chậm do bean initialization

Nếu **spring.beans.instantiate** hoặc custom bean step chậm:

- Xác định beanName và dependency chain.
- Kiểm tra constructor/@PostConstruct có I/O blocking hay không.
- Đánh giá việc tải remote config, DB validation, warm-up dữ liệu.
- Tách tác vụ thật sự cần trước ready và tác vụ best-effort.
- Có timeout cho I/O, không dùng sleep/retry vô hạn.
- Không chỉ bật lazy initialization để giấu lỗi và chuyển chi phí sang request đầu.

### 12.3. Chậm do JVM/JDK

Nếu timeline cho thấy nhiều GC, class loading, JIT:

- Kiểm tra heap size, CPU quota, container memory và filesystem performance.
- So sánh warm vs cold start, page cache, JDK version và GC configuration.
- Xem JFR JVM events và profiling settings đúng bản Java.
- Không kết luận chỉ từ một lần chạy vì JIT/classloading/OS scheduling khác nhau theo máy.

### 12.4. Chậm do ApplicationRunner

Nếu context refresh nhanh nhưng Ready chậm:

- Đo runner và các tác vụ seed, cache warm-up, check dependencies.
- Với công việc bắt buộc, sử dụng bounded retries và deadline.
- Với công việc có thể hoãn, cân nhắc background tasks với fallback và readiness policy phù hợp.
- Tránh runner submit CompletableFuture rồi return trước khi công việc bắt buộc kết thúc: Boot có thể công bố Ready sớm.

### 12.5. Chậm do network

Nếu custom step có duration cao mà CPU thấp:

- Kiểm tra DNS, TLS handshake, connect timeout, JDBC pool acquisition và remote latency.
- Đối chiếu socket events của JFR khi settings hỗ trợ.
- Thêm application-level instrumentation ở đúng nơi gọi network.
- Đừng chỉ tăng thread count: số kết nối downstream hoặc rate limit có thể mới là bottleneck.

## 13. Đo startup có thể gây sai lệch nếu thiết kế thí nghiệm không nhất quán

Một recording hữu ích không chỉ là file xuất hiện thành công. Trước khi so sánh A/B:

1. Dùng **cùng JDK version**, Spring Boot patch, classpath và ứng dụng.
2. Giữ **CPU, RAM, container limits**, loại máy và storage tương đồng.
3. Ghi rõ **cold/warm start**, file cache và trạng thái remote dependencies.
4. Giữ giống **JFR settings** ở hai nhóm; profile recording có thể có overhead khác default.
5. Thu nhiều lần chạy; xem median/p95 hoặc phân phối, không chọn một số đẹp.
6. Phân biệt **Spring startup step duration** với **tổng thời gian đến Ready**.
7. Không cộng durations của các nested steps khi báo cáo tổng.
8. Gắn thời gian JFR với timestamps của startup log và readiness transition.
9. Tránh để logging DEBUG gây overhead lớn chỉ ở một nhóm.
10. Đo cả side effects: cache warm-up thiếu có thể làm startup nhanh hơn nhưng request đầu chậm hoặc lỗi.
11. Đảm bảo file recording không bị truncate khi container exit.
12. Không so sánh một developer laptop với một Kubernetes pod chịu CPU throttling rồi quy toàn bộ chênh lệch cho Spring.

**Bài toán đo khởi động nên có định nghĩa mục tiêu:** "từ JVM launch đến ApplicationReadyEvent", "thời gian refresh", "thời gian một custom bean" hay "thời gian Pod Ready". Các mốc không đồng nhất và có thể bị ảnh hưởng bởi network/probe scheduling.

### Ví dụ bảng đánh giá A/B

| Thước đo | Baseline | Sau thay đổi | Cách đọc |
| --- | --- | --- | --- |
| Thời gian refresh | Đo từ startup steps | Đo tương tự | Có giảm công việc trong context? |
| Ready latency | Đo từ log/event | Đo tương tự | Runners có làm thay đổi kết quả? |
| Tổng CPU trong startup | JFR CPU/profile | Cùng settings | CPU work có giảm? |
| GC pause trong startup | JFR GC events | Cùng settings | Có bớt allocation/GC stalls? |
| First-request latency | Load test bổ sung | Cùng workload | Có chỉ đẩy chi phí sang request đầu? |
| Correctness | Integration tests | Không suy giảm | Không đánh đổi tính đúng lấy tốc độ? |

Không gán con số tự nghĩ vào bảng vì chúng phụ thuộc ứng dụng thật. Bảng này là **khuôn đánh giá**, không phải dữ liệu đo.

## 14. Các lỗi thường gặp khi dùng FlightRecorderApplicationStartup

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không thấy Spring startup events | Chưa gọi setApplicationStartup trước run | Cấu hình đúng trong main |
| Có JFR events của JVM nhưng không có custom Spring steps | Dùng ApplicationStartup.DEFAULT/no-op | Đổi sang FlightRecorderApplicationStartup |
| Có Spring steps trong code nhưng .jfr không xuất hiện | Không bật JFR, không có quyền ghi, dump fail | Kiểm tra -XX:StartFlightRecording và output JVM |
| JFR ghi muộn, thiếu phase Environment | Dùng jcmd sau startup hoặc delay quá dài | Bật recording tại JVM launch |
| jfr print --events StartupEvent không thấy gì | Sai event name | Dùng tên fully qualified từ jfr metadata |
| Không thấy demo.catalog.initialize | Custom step chưa được gọi/end | Kiểm tra bean có tạo và finally có step.end |
| StartupStep duration rất lớn nhưng CPU thấp | Bị block I/O/sleep/GC pause | Correlate với JVM events và application metrics |
| Tính tổng durations lớn hơn startup time | Nested/overlapping steps | Dùng timeline, không cộng thô |
| Boot actuator /startup không hiển thị JFR steps | Endpoint đòi dữ liệu buffering phù hợp | Dùng BufferingApplicationStartup hoặc phân tích .jfr |
| Chỉ thấy GC event mà không thấy ClassLoad | Recording settings/threshold khác nhau | Xem JFR event configuration |
| JFR file bị ghi đè giữa nhiều lần thử | Dùng cùng filename | Đặt tên riêng theo run/PID/timestamp |
| Không có jfr CLI trong container | Runtime image tối giản | Copy .jfr sang máy có JDK đầy đủ |
| Không đọc được file sau container restart | File ghi trong ephemeral filesystem | Dùng volume/artifact collection phù hợp |
| Gắn dữ liệu nhạy cảm vào StartupStep.tag | Tags được ghi trong recording | Loại bỏ secrets/PII, giới hạn quyền truy cập |
| Thay application startup strategy hai lần | Set lần sau ghi đè lần trước | Chọn một strategy rõ ràng |
| Chỉ tối ưu phần refresh nhưng Ready không nhanh | Runner/dependency bên ngoài vẫn chậm | Đo cả thời gian từ Started đến Ready |
| Dùng CPU profile để suy ra mọi IO waiting | CPU sampling không đo hết waiting | Kết hợp socket/thread/park events và custom steps |

### Lỗi phân tích cần tránh

Một JFR trace không có **jdk.GarbageCollection** không đủ kết luận GC chưa bao giờ xảy ra. Event có thể bị tắt, threshold có thể khác hoặc recording window không phủ đúng thời điểm. Tương tự, không thấy Spring step có thể do instrumentation chưa được cài, event chưa bật hoặc file ghi sau khi step kết thúc.

**Luôn xác minh recording window, event type và settings trước khi rút ra kết luận.**

## 15. Quan sát trong production: hiệu năng, bảo mật và vận hành

JFR có thể có chi phí ghi thấp với cấu hình phù hợp, nhưng **không hoàn toàn miễn phí**. Trong production:

- Dùng **settings=default** hoặc policy riêng cho recording định kỳ, và **settings=profile** khi điều tra có chủ đích.
- Giới hạn **maxsize/maxage/duration**; tránh file recording chiếm đĩa không kiểm soát.
- Chỉ lưu recording trong thư mục có quyền truy cập phù hợp.
- Tags/custom events không chứa secrets hoặc dữ liệu nhạy cảm.
- Có chính sách retention/xóa dữ liệu.
- Với nhiều replicas, hạn chế bật toàn bộ đồng thời khi chưa đo resource impact.
- Ghi metadata: service version, JDK version, image digest, Pod/container ID và thời điểm recording, theo nguyên tắc bảo mật.
- Chỉ tạo file khi cần, hoặc sử dụng hạ tầng thu thập JFR có kiểm soát.
- Nếu production dùng JVM image tối giản, lên kế hoạch thu file và phân tích ở môi trường khác.
- Khi dùng JMC, cần tránh tải file ghi chứa dữ liệu production lên dịch vụ ngoài không được phê duyệt.
- Không dùng JFR thay thế metrics hạ tầng, distributed tracing hay health/readiness probes.

**Đừng gắn bản ghi dài hạn chỉ để đo startup một lần.** Khi mục tiêu là cold startup, một recording ngắn bật từ JVM launch thường dễ phân tích và ít tốn tài nguyên hơn.

## 16. Kiểm thử chủ động sự khác biệt giữa JFR và startup buffer

### Thí nghiệm A — FlightRecorderApplicationStartup

Chạy ví dụ chính với:

~~~bash
java -XX:StartFlightRecording=filename=flight-a.jfr,settings=profile,dumponexit=true \
  -jar target/jfr-startup-demo-0.0.1-SNAPSHOT.jar
~~~

Kỳ vọng về bản chất:

- Có file **flight-a.jfr** nếu recording được dump thành công.
- Có những Spring startup events, gồm custom steps của demo.
- Có thể xem thêm JVM events trong cùng file.
- Không cần HTTP Actuator endpoint.

### Thí nghiệm B — Không cài ApplicationStartup

Trong bản sao local của dự án, bỏ lời gọi:

~~~java
app.setApplicationStartup(
        new FlightRecorderApplicationStartup());
~~~

Đây là thao tác thay đổi mã nguồn **chỉ trong bản sao thí nghiệm**, không phải thao tác nên làm đối với code production. Nếu code demo vẫn inject **ApplicationStartup**, Spring có thể cung cấp default no-op strategy; phương thức custom step vẫn chạy nhưng không được export thành event JFR.

Bật JFR như cũ. JVM events vẫn có thể được ghi, nhưng **không kỳ vọng có FlightRecorderStartupEvent của Spring** chỉ vì JFR đang chạy. Điều này giúp chứng minh **bật JFR** và **bật Spring instrumentation** là hai bước riêng biệt.

### Thí nghiệm C — Tăng thời gian giả lập

Đổi sleep của **demo.catalog.initialize** từ 300ms thành 700ms, build và chạy lại với filename khác. Nếu không có yếu tố bất thường, duration của custom step tương ứng có xu hướng tăng. **Không đòi delta chính xác 400ms** vì JVM scheduling, build/run variance và event overhead.

So sánh trong timeline rằng phần catalog tăng có thể kéo dài **spring.context.refresh** và thời điểm Ready, nhưng đừng cộng custom step vào parent step như hai phần độc lập.

### Thí nghiệm D — Chuyển công việc sang runner

Nếu chuyển một tác vụ bắt buộc từ @Bean initialization sang ApplicationRunner (đúng dependency và readiness policy):

- **context refresh** có thể ngắn hơn.
- **thời gian đến ApplicationReadyEvent** có thể không giảm, vì runner vẫn phải làm việc.
- JFR cho phép đối chiếu nơi chi phí đã dịch chuyển.
- Nếu runner return sớm bằng asynchronous task, startup có thể nhanh "ảo" nhưng ứng dụng nhận traffic khi tài nguyên chưa sẵn.

Mục tiêu không phải chỉ tối ưu một con số, mà là **giảm thời gian sẵn sàng thực tế mà vẫn bảo đảm đúng chức năng**.

## 17. Câu hỏi luyện tập

**Câu 1.** FlightRecorderApplicationStartup nằm trong Spring Boot hay Spring Framework? Package đầy đủ là gì?

**Câu 2.** Vì sao chạy JVM với -XX:StartFlightRecording chưa chắc tạo Spring StartupStep events?

**Câu 3.** Tại sao nên gọi setApplicationStartup trước SpringApplication.run thay vì khai báo nó như một @Bean trong configuration class?

**Câu 4.** StartupStep.start, tag và end có vai trò gì? Vì sao phải gọi end ở finally?

**Câu 5.** Khi xem spring.context.refresh duration 800ms và một step con 300ms, có thể cộng thành 1100ms không?

**Câu 6.** Khi Spring bean chờ network 600ms, có thể kết luận bean tiêu 600ms CPU không?

**Câu 7.** Dùng jcmd JFR.start sau ApplicationReadyEvent có tái tạo được những startup events đã xảy ra trước đó không?

**Câu 8.** Phân biệt FlightRecorderApplicationStartup và BufferingApplicationStartup về nơi lưu dữ liệu và công cụ phân tích.

**Câu 9.** Vì sao /actuator/startup không tự thay thế file .jfr?

**Câu 10.** Tại sao không nên dùng custom tag chứa mật khẩu/JDBC URL có credentials?

**Câu 11.** Nếu JFR summary không có ClassLoad events, có thể kết luận JVM đã không load class nào khi startup không?

**Câu 12.** Một ứng dụng startup nhanh hơn sau khi bật lazy initialization nhưng request đầu chậm rõ rệt. Có nên coi đây là chiến thắng không?

**Câu 13.** Trong chương trình demo, custom step nào được gọi trong refresh và step nào trong runner?

**Câu 14.** Một bản ghi profile dài 10 phút trên hàng trăm replicas có thể có vấn đề gì?

### Gợi ý đáp án

1. Thuộc Spring Framework; **org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup**.
2. Vì phải gắn ApplicationStartup implementation vào Spring trước startup, đồng thời JFR recording phải ghi đúng event.
3. @Bean được tạo trong refresh, quá muộn cho những bước sớm.
4. start mở bước, tag thêm ngữ cảnh, end kết thúc ghi; finally bảo đảm end khi có exception.
5. Không; parent có thể bao gồm child.
6. Không; duration có thể là wall-clock waiting.
7. Không; recording bắt đầu muộn không khôi phục lịch sử quá khứ.
8. FlightRecorder phát JFR events; Buffering lưu steps trong bộ nhớ và có thể xuất qua Actuator.
9. Actuator startup endpoint không phải JVM Flight Recorder và không chứa đầy đủ JVM profiling events.
10. File JFR có thể được tải, chia sẻ, lưu trữ; tags có thể lộ thông tin nhạy cảm.
11. Không; kiểm tra event settings, recording window và version.
12. Chưa chắc; phải đo readiness và end-to-end first-request behavior.
13. **demo.catalog.initialize** trong @Bean; **demo.runner.validate** trong ApplicationRunner.
14. Dung lượng file, overhead, security/retention và vận hành thu thập có thể quá lớn.

## 18. Checklist trước khi chốt một kết luận startup

- [ ] Xác nhận Spring Boot/JDK version thực tế, không dùng tài liệu một version khác?
- [ ] Có **FlightRecorderApplicationStartup** đúng package?
- [ ] Đã cài ApplicationStartup **trước run()**?
- [ ] JVM đã bật JFR từ khi khởi động, **không có delay bỏ lỡ phase đầu**?
- [ ] Đường dẫn file và filesystem permissions phù hợp?
- [ ] Có cờ **dumponexit=true** hoặc duration/dump policy bảo đảm tạo recording?
- [ ] Dùng **jfr summary** để kiểm tra bản ghi?
- [ ] Dùng đúng event name qua **jfr metadata** và filter?
- [ ] Thấy ít nhất một custom step đáng tin, có **step.end()**?
- [ ] Không cộng durations của các steps lồng nhau?
- [ ] Có correlation với GC, CPU, I/O, class loading hoặc thread events?
- [ ] Đã tách thời gian refresh, runners và Ready?
- [ ] Đã đo baseline và nhiều lần chạy với cấu hình nhất quán?
- [ ] Có test correctness/first-request latency sau khi tối ưu?
- [ ] Không đưa secrets/PII vào tags/recording?
- [ ] Không nhầm BufferingApplicationStartup /actuator/startup với JFR?
- [ ] Có retention, maxsize, access control phù hợp production?

## 19. Kết luận

**FlightRecorderApplicationStartup** là cầu nối để đưa các **Spring StartupStep** vào **Java Flight Recorder**. Nó cần được cấu hình bằng **SpringApplication.setApplicationStartup(...)** trước khi **run()** bắt đầu. Đồng thời JVM phải bật **JFR recording từ lúc launch** nếu muốn nhìn thấy toàn bộ giai đoạn khởi động.

Sau đó:

~~~text
Spring startup steps
  (refresh, bean creation, custom steps)
             |
             v
FlightRecorderApplicationStartup
             |
             v
Spring-specific JFR events
             |
             +------------------------+
             |                        |
       JVM GC/CPU/ClassLoad      App custom steps
             |                        |
             +------------+-----------+
                          |
                    startup.jfr
                          |
                 jfr summary/print
                          |
               JDK Mission Control
                          |
              Giả thuyết bottleneck
                          |
             Tối ưu và đo lại A/B
~~~

Điều quan trọng nhất không phải "có file JFR", mà là **đưa ra kết luận có thể kiểm chứng**: một startup step cụ thể đang tiêu thời gian, nguyên nhân của thời gian đó nằm ở Spring/bean, JVM hay dependency, và thay đổi đã làm thời gian **ready thực tế** cải thiện mà không giảm tính đúng đắn.

### Tài liệu tham khảo chính thức

1. Spring Boot 3.5 Reference — SpringApplication, Application Startup tracking: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
2. Spring Framework 6.2 JavaDoc — FlightRecorderApplicationStartup: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/metrics/jfr/FlightRecorderApplicationStartup.html
3. Spring Framework 6.2 Reference — Application startup steps và cách instrumentation: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
4. Spring Framework 6.2 Appendix — Các Spring Application Startup Steps: https://docs.spring.io/spring-framework/reference/6.2/core/appendix/application-startup-steps.html
5. Spring Framework 6.2 JavaDoc — ApplicationStartup và StartupStep: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/metrics/ApplicationStartup.html
6. Oracle Java 21 — java command và -XX:StartFlightRecording: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
7. Oracle Java 21 — jfr command summary, print, metadata: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
8. Oracle Java 21 — jcmd JFR.start/JFR.dump/JFR.stop: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html

**Phạm vi:** ví dụ là ứng dụng non-web Spring Boot 3.5.x, Java 17+, dùng JDK có JFR và Maven. Với Boot 4.x, Framework 7.x hoặc JDK/JMC khác, cần đối chiếu lại API, event names, event settings và công cụ của đúng phiên bản trước khi tự động hóa phân tích .jfr.