# Phạm vi hỗ trợ trong ứng dụng Servlet, Reactive và không có web

## 1. Tách khả năng vận hành khỏi cách truy cập

Bạn có ba ứng dụng Spring Boot:

- Một API dùng Spring MVC để phục vụ yêu cầu HTTP.
- Một dịch vụ dùng Spring WebFlux.
- Một chương trình chạy tác vụ nhập dữ liệu rồi kết thúc.

Cả ba đều có thể cần số đo bộ nhớ, bộ đếm công việc hoặc phép kiểm tra tình trạng tài nguyên. Tuy nhiên, chỉ hai ứng dụng đầu có máy chủ web theo cấu hình đang xét.

**Actuator không bị giới hạn ở ứng dụng có HTTP.** Phạm vi thực tế cần được hiểu theo hai câu hỏi riêng:

1. Ứng dụng có những thành phần nào để tạo dữ liệu vận hành?
2. Dữ liệu đó được công bố hoặc xuất đi bằng cơ chế nào?

Ví dụ, một bộ đếm nghiệp vụ được cập nhật qua `MeterRegistry` không cần một yêu cầu HTTP mới có thể hoạt động. Ngược lại, muốn gọi `GET /actuator/health` thì cần hạ tầng web phù hợp cùng cấu hình endpoint.

Bài này dùng Spring Boot **3.3.13** và Java **21**. Các ví dụ được thiết kế để so sánh ba môi trường bằng cùng một phần mã nghiệp vụ rất nhỏ.

## 2. Ba kiểu ứng dụng được nói đến là gì?

### 2.1. Servlet

Ứng dụng Servlet sử dụng hạ tầng Servlet để nhận và xử lý yêu cầu web. Trong cách tạo dự án Boot thông thường, `spring-boot-starter-web` cung cấp Spring MVC và máy chủ nhúng mặc định thích hợp.

Ở đây, Servlet là kiểu hạ tầng phục vụ web. Nó không đồng nghĩa với một công nghệ đo lường riêng của Actuator.

### 2.2. Reactive

Ứng dụng Reactive trong phạm vi bài này là ứng dụng web dùng Spring WebFlux. Cách tạo dự án thông thường là dùng `spring-boot-starter-webflux`.

WebFlux dựa trên mô hình xử lý bất đồng bộ và Reactive Streams, không yêu cầu Servlet API như điều kiện nền tảng của chính framework. Dù Reactor Netty là lựa chọn mặc định thường gặp với starter, không nên định nghĩa “Reactive” đơn giản là “tên khác của Netty”. [Spring Boot: Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html).

### 2.3. Không có web

Trong Boot, `WebApplicationType.NONE` biểu thị ứng dụng không chạy như một ứng dụng web và không khởi động web server nhúng theo kiểu đó. Nó vẫn có thể có Spring ApplicationContext, các bean, tác vụ định kỳ, bộ nhận thông điệp hoặc công việc chạy từ dòng lệnh. [API WebApplicationType](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/WebApplicationType.html).

“Không có web” không có nghĩa “không dùng mạng”. Một chương trình nhập dữ liệu vẫn có thể gọi HTTP client hoặc kết nối cơ sở dữ liệu. Điều đang được nói tới là **không có hạ tầng máy chủ web của ứng dụng Boot trong chế độ NONE**.

Cũng không nên đánh đồng “không viết controller nghiệp vụ” với NONE. Một ứng dụng web có thể chỉ công bố endpoint quản trị và vẫn có web server.

## 3. Mô hình hỗ trợ: ba lớp cần kiểm tra

Có thể lần theo ba lớp sau:

~~~text
Thư viện và bean trong ứng dụng
    -> khả năng tạo hoặc cung cấp dữ liệu vận hành
    -> cơ chế công bố / xuất dữ liệu
~~~

Ví dụ:

~~~text
Bean HealthIndicator
    -> kết quả kiểm tra tình trạng
    -> health endpoint qua HTTP hoặc JMX phù hợp

MeterRegistry + meter
    -> số đo JVM / thư viện / nghiệp vụ
    -> truy vấn endpoint hoặc bộ xuất số liệu đã cấu hình
~~~

Vì vậy, câu “Actuator hỗ trợ môi trường X” không có nghĩa mọi endpoint, mọi số đo và mọi cách truy cập đều có mặt trong môi trường đó.

Một bảng định hướng:

| Khả năng | Servlet | Reactive | Không có web |
| --- | --- | --- | --- |
| Ghi bộ đếm, timer nghiệp vụ qua Micrometer | Có thể | Có thể | Có thể |
| Đóng góp thông tin tình trạng | Có thể | Có thể, có hợp đồng reactive | Có thể |
| Công bố endpoint quản trị qua HTTP | Qua hạ tầng web phù hợp | Qua hạ tầng WebFlux phù hợp | Không có HTTP server chỉ nhờ Actuator |
| Công bố endpoint tương thích qua JMX | Có thể khi cấu hình | Có thể khi cấu hình | Có thể khi cấu hình |
| Số đo yêu cầu HTTP phía server | Có khi được tích hợp | Có khi được tích hợp | Không có yêu cầu server để đo trong chế độ NONE |
| Số đo phụ thuộc một thư viện cụ thể | Cần thư viện/bean tương ứng | Cần thư viện/bean tương ứng | Cần thư viện/bean tương ứng |

“Có thể” trong bảng là phạm vi khả năng, không phải khẳng định mặc định đã bật tất cả. Phải xét thêm điều kiện tự cấu hình, danh sách công bố và quyền truy cập.

## 4. Boot chọn kiểu ứng dụng như thế nào?

Trong những tổ hợp starter thông thường đang xét:

| Thư viện phía server | Kiểu thường được Boot chọn |
| --- | --- |
| Spring MVC từ starter web | Servlet |
| WebFlux, không có Spring MVC | Reactive |
| Không có hạ tầng web phù hợp | Không có web |

Khi có cả Spring MVC và WebFlux, Boot mặc định ưu tiên kiểu Servlet. Vì vậy, thêm WebFlux để dùng `WebClient` không tự chuyển máy chủ hiện tại sang Reactive. [SpringApplication: Web Environment](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.web-environment).

Có thể chỉ định rõ kiểu:

~~~properties
spring.main.web-application-type=none
~~~

Hoặc truyền thuộc tính tương ứng khi chạy:

~~~powershell
java -jar app.jar --spring.main.web-application-type=none
~~~

Thuộc tính chọn kiểu không tải thêm thư viện. Nếu ép một kiểu web mà dự án thiếu thành phần cần thiết, ứng dụng có thể không khởi động được hoặc không có khả năng mà bạn đang mong đợi.

Điểm cần kiểm chứng là **kiểu ApplicationContext và các thành phần thực sự được tạo**, không chỉ là một dòng khai báo trong tệp cấu hình.

## 5. Phạm vi trong ứng dụng Servlet

### 5.1. HTTP management sử dụng hạ tầng web

Với ứng dụng Servlet thông thường, endpoint quản trị được gắn vào hạ tầng phục vụ HTTP. Người vận hành có thể đọc các đường dẫn như `/actuator/health` khi endpoint đã được công bố.

Đường dẫn, cổng và tiền tố có thể được cấu hình. Actuator hỗ trợ HTTP với Spring MVC, Spring WebFlux và Jersey; không có yêu cầu phải tự viết controller cho từng endpoint chuẩn. [Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

Một ứng dụng có thể phục vụ cả API nghiệp vụ và endpoint quản trị. Nếu dùng cổng quản trị riêng, đó vẫn là một phần của thiết kế ứng dụng web, không phải bằng chứng rằng Actuator tự biến mọi chương trình NONE thành máy chủ.

### 5.2. Những gì gắn riêng với môi trường Servlet

Một số khả năng có điều kiện riêng. Chẳng hạn, endpoint `sessions` yêu cầu ứng dụng web dựa trên Servlet và Spring Session. Việc một tên endpoint xuất hiện trong tài liệu không đảm bảo nó tồn tại trong mọi dự án. [Điều kiện của các endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Tương tự, số đo của container phải được xem theo container và cấu hình đang dùng. Không nên lấy một tên số đo của Tomcat rồi mặc nhiên đòi hỏi nó có trong một ứng dụng chạy bằng công nghệ khác.

Khi thiết kế phần mở rộng, hãy tách rõ phần logic quản trị dùng chung khỏi mã phụ thuộc Servlet API. Một thao tác cần `HttpServletRequest` đã có ràng buộc công nghệ mà một thao tác đọc số liệu thông thường có thể không cần.

## 6. Phạm vi trong ứng dụng Reactive

### 6.1. Vẫn có HTTP endpoint và các khả năng dùng chung

Một ứng dụng WebFlux có thể công bố health, metrics và những endpoint tương thích qua HTTP. Người dùng đọc URL giống nhau không có nghĩa cơ chế bên trong là Spring MVC: loại hạ tầng web và lớp tích hợp endpoint mới quyết định cách xử lý.

Các meter nghiệp vụ vẫn dùng API Micrometer. Bạn không cần đổi một counter thành một loại “reactive counter” chỉ vì mã nghiệp vụ nằm trong một pipeline Reactor.

Tuy nhiên, thời điểm cập nhật số đo phải khớp hoạt động thực sự diễn ra. Việc tạo một publisher chưa chắc đã thực thi công việc; đo lúc tạo publisher có thể cho ý nghĩa khác với đo khi công việc hoàn tất.

### 6.2. Health có hợp đồng reactive

`ReactiveHealthIndicator` trả về `Mono<Health>` và được thiết kế cho hợp đồng kiểm tra không chặn trong ứng dụng reactive. Đây là hợp đồng khác với `HealthIndicator` truyền thống trả trực tiếp `Health`. [API ReactiveHealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/ReactiveHealthIndicator.html).

Boot có cơ chế thích nghi các health contributor truyền thống trong hệ thống reactive; tài liệu mô tả việc thực thi các contributor thông thường không dùng API reactive trên elastic scheduler. Điều này giúp tích hợp phép kiểm tra cũ, nhưng không biến mọi lời gọi chặn của toàn bộ ứng dụng thành không chặn. [Reactive Health Indicators](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.reactive).

Một cách suy nghĩ đúng là:

~~~text
Hợp đồng reactive
    -> mô tả khi nào có kết quả
    -> cần hiện thực phù hợp với cách thực thi

Bọc một lời gọi chặn bằng một kiểu trả về reactive
    -> chưa đủ chứng minh công việc không chặn
~~~

Ví dụ hoàn chỉnh trong bài dùng một indicator đồng bộ trả kết quả ngay để giữ phần so sánh gọn. Nó không thực hiện I/O nên không minh họa việc gọi một cơ sở dữ liệu chặn trong event loop.

### 6.3. Ngữ cảnh quan sát cần đi cùng pipeline

Nếu dùng observation hoặc tracing trong luồng reactive, ngữ cảnh hiện hành không nên được suy đoán chỉ từ một `ThreadLocal`. Công việc có thể tiếp tục ở các thời điểm hoặc luồng khác. Cần dùng cơ chế tích hợp và truyền ngữ cảnh phù hợp với phiên bản đang chạy. [Observability và context propagation](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

Điều này liên quan tới chất lượng tín hiệu, không phải lý do để coi Actuator là không được hỗ trợ trong Reactive.

## 7. Phạm vi trong ứng dụng không có web

### 7.1. Không có HTTP không làm mất mọi khả năng vận hành

Một tác vụ dòng lệnh vẫn có thể:

- Ghi bộ đếm số bản ghi đã xử lý.
- Đo thời gian một giai đoạn công việc.
- Đọc tình trạng một thành phần qua hợp đồng đã chọn.
- Công bố endpoint phù hợp qua JMX khi được cấu hình.
- Dùng bộ xuất số liệu thích hợp nếu có thư viện và cấu hình cần thiết.

Boot tích hợp Micrometer và tự cấu hình các registry dựa trên những thành phần tìm thấy. Việc ghi số đo vào registry không yêu cầu một controller nghiệp vụ. [Tài liệu Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Nhưng trong chế độ NONE, không có máy chủ web do Boot tạo theo kiểu đó để nhận `GET /actuator/health`. Chỉ thêm thuộc tính công bố web hoặc đặt `management.server.port` không thay thế điều kiện phải có hạ tầng ứng dụng web.

### 7.2. JMX là một đường quản trị độc lập với HTTP

Có thể bật hỗ trợ JMX của Spring bằng:

~~~yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    jmx:
      exposure:
        include: health,metrics
~~~

Theo cấu hình mặc định về domain và tên, health có thể được đăng ký dưới ObjectName:

~~~text
org.springframework.boot:type=Endpoint,name=Health
~~~

JMX của Spring Boot mặc định chưa được bật; vì vậy phải phân biệt “có khả năng hỗ trợ JMX” với “đã có MBean được đăng ký”. [Monitoring and Management over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

Ngoài ra, `spring.jmx.enabled=true` không tự đồng nghĩa với việc mở một cổng quản trị từ xa cho mọi máy truy cập. Đăng ký MBean, kết nối công cụ quản trị cục bộ và cấu hình connector từ xa là các vấn đề riêng. [JDK 21: JMX management](https://docs.oracle.com/en/java/javase/21/management/monitoring-and-management-using-jmx-technology.html).

### 7.3. Thời gian sống của tiến trình ảnh hưởng khả năng quan sát

Một chương trình chạy xong sau vài giây có thể đã kết thúc trước khi công cụ bên ngoài tới đọc dữ liệu. Bản demo bên dưới cố ý chụp thông tin trong `ApplicationRunner` rồi đóng context ở chế độ không có web.

Đối với một tác vụ ngắn, hãy chọn cách lưu kết quả và xuất dữ liệu phù hợp. Nếu một bộ xuất có chu kỳ gửi dài hơn thời gian chạy, cần xem quy tắc hoàn tất, gửi và đóng tài nguyên của chính bộ xuất đó. Đọc counter trong tiến trình không tự chứng minh dữ liệu đã được một hệ thống bên ngoài nhận.

Với một tiến trình nhận thông điệp chạy lâu dài, thời gian sống thường do công việc thực tế của nó quyết định. Không cần tạo API nghiệp vụ giả chỉ để có một counter hay một phép kiểm tra tình trạng.

## 8. Những khả năng không được coi là giống hệt ở cả ba môi trường

### 8.1. Endpoint dùng chung và endpoint phụ thuộc công nghệ

`@Endpoint` là hướng định nghĩa khả năng quản trị có thể được thích nghi với công nghệ công bố phù hợp. Ngược lại:

- `@WebEndpoint` giới hạn endpoint ở HTTP.
- `@JmxEndpoint` giới hạn endpoint ở JMX.

Do đó, không thể lấy một endpoint được định nghĩa chỉ cho web rồi kỳ vọng nó tự xuất hiện qua JMX trong chương trình NONE. [API WebEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/annotation/WebEndpoint.html), [API JmxEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/jmx/annotation/JmxEndpoint.html).

Các khả năng như đọc tệp log, lấy heap dump hoặc phục vụ định dạng Prometheus có cách công bố và điều kiện riêng. Không nên xem bảng tên endpoint như một danh sách luôn sẵn có bất kể web type và thư viện.

### 8.2. Công bố endpoint khác với xuất số liệu

Ba việc sau khác nhau:

~~~text
Ghi meter vào registry
Đọc registry qua metrics endpoint
Xuất số liệu bằng registry tích hợp hệ thống bên ngoài
~~~

Tương tự, công bố Actuator endpoint dưới dạng MBean không có nghĩa đã cấu hình Micrometer để đưa từng meter ra MBean riêng. Phải xem thành phần thực hiện việc đó.

Khi ứng dụng không có web, một thiết kế thu thập cần được chọn theo cách nó thực sự cung cấp dữ liệu. Một công cụ chỉ biết kéo dữ liệu qua URL HTTP sẽ không lấy được dữ liệu từ chương trình không có HTTP server chỉ vì chương trình đó đã tạo counter.

### 8.3. Bảo mật phải theo cơ chế truy cập đang dùng

Quy tắc truy cập HTTP của Servlet và Reactive thuộc các hạ tầng bảo mật tương ứng. Quy tắc trên HTTP cũng không tự trở thành quyền truy cập cho một kết nối JMX từ xa.

Trong bài thực hành, web server chỉ lắng nghe loopback và không thêm thư viện Spring Security. Khi đưa khả năng quản trị vào môi trường triển khai, cần gắn nó với cơ chế truy cập quản trị của môi trường đó.

## 9. Ví dụ hoàn chỉnh: cùng mã, thay bộ thư viện web

Ví dụ dùng một dự án độc lập với ba **Maven profile**:

- `nonweb`: chỉ dùng các phụ thuộc chung, không thêm web starter.
- `servlet`: thêm starter web.
- `reactive`: thêm starter WebFlux.

Đây là profile của công cụ build Maven, không phải Spring profile từ `spring.profiles.active`. Mỗi lượt thực hành chỉ chọn **một** Maven profile và build sạch để tránh dùng nhầm JAR của lượt trước.

Cấu trúc:

~~~text
actuator-scope/
├── pom.xml
└── src/main/
    ├── java/example/actuatorscope/ActuatorScopeApplication.java
    └── resources/application.yml
~~~

Bạn cần JDK 21, Maven và khả năng tải thư viện trong lần build đầu.

### 9.1. Tệp pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>actuator-scope</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
    <profiles>
        <profile>
            <id>nonweb</id>
        </profile>
        <profile>
            <id>servlet</id>
            <dependencies>
                <dependency>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-web</artifactId>
                </dependency>
            </dependencies>
        </profile>
        <profile>
            <id>reactive</id>
            <dependencies>
                <dependency>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-webflux</artifactId>
                </dependency>
            </dependencies>
        </profile>
    </profiles>
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

Phần mã chung không cần nhập kiểu dữ liệu của Servlet hoặc Reactor. Vì vậy, có thể biên dịch nó với cả ba tập thư viện.

### 9.2. Tệp Java

Tệp `src/main/java/example/actuatorscope/ActuatorScopeApplication.java`:

~~~java
package example.actuatorscope;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ActuatorScopeApplication {
    public static void main(String[] args) {
        ConfigurableApplicationContext context =
            SpringApplication.run(ActuatorScopeApplication.class, args);
        if (!(context instanceof WebServerApplicationContext)) {
            context.close();
        }
    }

    @Bean
    HealthIndicator demoHealthIndicator() {
        return () -> Health.up().build();
    }

    @Bean
    ApplicationRunner probe(ApplicationContext context,
                            MeterRegistry meters, MBeanServer mbeans) {
        return args -> {
            Counter work = meters.counter("demo.work.units", "source", "probe");
            work.increment();
            HealthIndicator demo =
                context.getBean("demoHealthIndicator", HealthIndicator.class);

            System.out.println("context=" + context.getClass().getSimpleName());
            System.out.println("web.server=" + (context instanceof WebServerApplicationContext));
            System.out.println("demo.health=" + demo.health().getStatus().getCode());
            System.out.println("work.units=" + (long) work.count());
            System.out.println("jmx.health=" + mbeans.isRegistered(
                new ObjectName("org.springframework.boot:type=Endpoint,name=Health")));
        };
    }
}
~~~

`demoHealthIndicator` luôn trả `UP` để minh họa một thành phần đóng góp tình trạng. Nó không kiểm tra tài nguyên bên ngoài và không phải phép kiểm tra đầy đủ cho hệ thống thật.

Runner tăng counter một lần, đọc indicator và kiểm tra xem MBean health đã được đăng ký chưa. Nó không phụ thuộc vào một yêu cầu HTTP để thực hiện những việc này.

Cuối `main`, chương trình đóng context khi không phải web application context. Ở hai chế độ web, context được giữ để bạn gọi HTTP trong terminal khác.

### 9.3. Tệp cấu hình

Tệp `src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    banner-mode: "off"
  jmx:
    enabled: true

logging:
  level:
    root: "OFF"

server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,metrics
    jmx:
      exposure:
        include: health,metrics
  endpoint:
    health:
      show-details: never
~~~

Cấu hình JMX được ghi rõ để cả ba lượt có thể kiểm tra MBean. Danh sách công bố HTTP chỉ có tác dụng khi có hạ tầng web phù hợp.

Logging và banner được tắt để đầu ra so sánh dễ đọc. Đây là lựa chọn của bài thực hành, không phải chỉ dẫn phải tắt nhật ký trong ứng dụng triển khai.

### 9.4. Lượt không có web

Tại thư mục chứa `pom.xml`:

~~~powershell
mvn -q -Pnonweb clean package
java -jar target/actuator-scope-1.0.0.jar --spring.main.web-application-type=none
~~~

Đầu ra của chương trình:

~~~text
context=AnnotationConfigApplicationContext
web.server=false
demo.health=UP
work.units=1
jmx.health=true
~~~

Chương trình kết thúc sau khi in và đóng context. Không có web server của ví dụ để nhận yêu cầu HTTP.

Đầu ra chứng minh ba điều trong cùng thời điểm chạy: indicator có thể được gọi, meter có thể được cập nhật và health MBean có thể được đăng ký khi không có web server.

Không thể mở JConsole sau khi tiến trình đã kết thúc rồi kỳ vọng vẫn quản lý được các MBean của tiến trình đó. `jmx.health=true` là phép kiểm tra đăng ký được thực hiện **khi context còn hoạt động**.

### 9.5. Lượt Servlet

~~~powershell
mvn -q -Pservlet clean package
java -jar target/actuator-scope-1.0.0.jar
~~~

Đầu ra:

~~~text
context=AnnotationConfigServletWebServerApplicationContext
web.server=true
demo.health=UP
work.units=1
jmx.health=true
~~~

Giữ terminal này chạy, mở terminal thứ hai rồi gọi:

~~~powershell
curl.exe --silent http://127.0.0.1:8080/actuator/health
~~~

Trong môi trường mà các phép kiểm tra health mặc định đều đạt, nội dung phản hồi là:

~~~json
{"status":"UP"}
~~~

Để kiểm tra counter đã tăng từ runner:

~~~powershell
$metric = Invoke-RestMethod -Uri "http://127.0.0.1:8080/actuator/metrics/demo.work.units"
$count = $metric.measurements | Where-Object { $_.statistic -eq "COUNT" }
[int]$count.value
~~~

Kết quả:

~~~text
1
~~~

Việc đọc counter không tăng counter `demo.work.units`. Mã tăng bộ đếm nằm trong runner, chạy một lần trong mỗi lần khởi động mẫu.

Dừng ứng dụng bằng `Ctrl+C` trước khi chuyển sang lượt tiếp theo để giải phóng cổng và tệp JAR đang được dùng.

### 9.6. Lượt Reactive

~~~powershell
mvn -q -Preactive clean package
java -jar target/actuator-scope-1.0.0.jar
~~~

Đầu ra:

~~~text
context=AnnotationConfigReactiveWebServerApplicationContext
web.server=true
demo.health=UP
work.units=1
jmx.health=true
~~~

Dùng lại hai phép kiểm tra HTTP ở lượt Servlet. Với cùng điều kiện health, bạn nhận health `UP` và counter có giá trị `1`.

API HTTP quản trị có cùng đường dẫn trong cấu hình mẫu. Khác biệt quan trọng là context và hạ tầng server đang chạy thuộc ứng dụng Reactive.

`curl.exe` là cách gọi chương trình cURL trên Windows để tránh alias của một số bản PowerShell. Trên Linux hoặc macOS, có thể dùng `curl`. Đoạn dùng `Invoke-RestMethod` được viết cho PowerShell.

### 9.7. Tại sao không dùng javac trực tiếp trên một tệp?

Tệp Java cần Spring Boot, Actuator, Micrometer và những phụ thuộc liên quan của từng Maven profile. Một lệnh `javac` không có classpath tương ứng sẽ không biên dịch được.

Trong ví dụ, `mvn clean package` giải quyết phụ thuộc, biên dịch bằng JDK đã cấu hình và đóng gói JAR thực thi. `java -jar` sau đó chạy đúng sản phẩm của từng lượt build.

Nếu cổng `8080` đã được dùng, có thể đổi `server.port` hoặc truyền `--server.port=<cổng phù hợp>` khi chạy hai bản web, rồi điều chỉnh URL kiểm tra.

## 10. Đọc bằng chứng theo đúng phạm vi

| Quan sát trong ví dụ | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- |
| NONE vẫn in `work.units=1` | Counter hoạt động không cần yêu cầu HTTP | Hệ thống bên ngoài đã lưu số đo |
| NONE in `jmx.health=true` | MBean health đã được đăng ký trong lúc chạy | Đã mở một connector JMX từ xa |
| Servlet và Reactive đều đọc được health qua HTTP | Hai hạ tầng hỗ trợ công bố endpoint này trong cấu hình mẫu | Mọi endpoint đều có ở cả hai |
| Ba lượt đều in `demo.health=UP` | Indicator minh họa trả kết quả theo định nghĩa của nó | Mọi tài nguyên bên ngoài đều hoạt động |
| Hai bản web có cùng URL | Cách nhìn từ bên gọi nhất quán trong cấu hình này | Cùng framework hoặc cùng cách thực thi nội bộ |

Chính việc tách các kết luận này giúp bạn tránh thêm web starter chỉ để giải quyết một nhu cầu đo lường vốn không đòi hỏi HTTP.

## 11. Những nhầm lẫn thường gặp và cách chẩn đoán

### “Thêm starter Actuator sẽ tự mở cổng 8080”

Hãy kiểm tra tập phụ thuộc phía server và kiểu ứng dụng. Starter Actuator không thay thế web starter. Lượt `nonweb` trong ví dụ là một cách kiểm chứng trực tiếp.

### “Tôi khai báo web exposure nên chương trình NONE phải có URL”

Danh sách exposure chọn endpoint cho cơ chế công bố đã có điều kiện hoạt động. Nó không tự tạo máy chủ trong một ứng dụng đang chạy kiểu NONE.

Khi không có máy chủ lắng nghe, lỗi kết nối không phải là cùng một tình huống với mã `404` do một máy chủ đã nhận yêu cầu trả về.

### “Có WebFlux trong dependencies thì chắc chắn server Reactive”

Hãy kiểm tra có Spring MVC trong classpath hay không, có thuộc tính ép web type hay không và context thực tế được tạo. Có thể ứng dụng chỉ cần WebFlux để dùng HTTP client trong khi máy chủ vẫn là Servlet.

### “Đặt cổng quản trị là -1 tương đương NONE”

`management.server.port=-1` dùng để tắt công bố HTTP quản trị theo cấu hình đó. Nó không phải cách tuyên bố toàn bộ ứng dụng không có web: API nghiệp vụ của ứng dụng Servlet/Reactive vẫn là vấn đề riêng. [Tắt HTTP management](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.disabling-http-endpoints).

### “Hỗ trợ Reactive có nghĩa mọi phép kiểm tra đều không chặn”

Cần xem hợp đồng và hiện thực của từng phép kiểm tra. Một phương thức trả kiểu reactive nhưng thực hiện I/O chặn ngay trước khi trả về vẫn cần được xem xét đúng cách.

### “Không có MBean nghĩa là Actuator không hỗ trợ ứng dụng này”

Kiểm tra `spring.jmx.enabled`, danh sách JMX exposure, endpoint có được bật và điều kiện tạo bean. Không nên suy ra giới hạn kiến trúc từ một cấu hình chưa bật cơ chế công bố.

### “Số liệu của tác vụ ngắn chắc chắn sẽ được thu tự động”

Kiểm tra thời gian sống của tiến trình, bộ xuất và nơi nhận. Với công việc đã kết thúc, phải có chiến lược lưu/xuất phù hợp thay vì trông chờ một yêu cầu HTTP tới một tiến trình không còn chạy.

## 12. Chọn cách áp dụng và tự kiểm tra

Một cách ra quyết định theo nhu cầu:

| Ứng dụng | Nhu cầu thực tế | Hướng thiết kế |
| --- | --- | --- |
| API Spring MVC hiện có | Đọc tình trạng và số đo qua HTTP | Dùng tích hợp Actuator cho hạ tầng Servlet đang có |
| Dịch vụ WebFlux | Công bố quản trị và giữ cách kiểm tra phù hợp reactive | Dùng tích hợp WebFlux, xem xét hợp đồng health và ngữ cảnh |
| Tác vụ nhập dữ liệu chạy ngắn | Biết số lượng xử lý và kết quả sau khi hoàn tất | Ghi số đo/kết quả, chọn cách lưu hoặc xuất theo vòng đời |
| Bộ nhận thông điệp chạy lâu dài, không cần HTTP | Theo dõi hoạt động và tài nguyên | Chọn JMX hoặc cơ chế xuất số liệu phù hợp; chỉ thêm HTTP khi đó là yêu cầu vận hành cụ thể |

**Bài tập 1:** Trong bản build `servlet`, chạy thêm tham số `--spring.main.web-application-type=none`. Dự đoán `web.server` và khả năng gọi HTTP.

Điểm cần giải thích: thư viện web vẫn có trong JAR, nhưng thuộc tính chọn kiểu NONE làm ứng dụng không khởi động như một web application. Sự hiện diện của một thư viện và việc sử dụng hạ tầng đó là hai điều khác nhau.

**Bài tập 2:** Tắt `spring.jmx.enabled` trong ví dụ rồi xem điều gì xảy ra.

Mã mẫu đang yêu cầu một bean `MBeanServer` trong runner. Vì vậy, việc tắt JMX có thể làm ví dụ không thỏa điều kiện tiêm phụ thuộc, thay vì đơn giản chỉ in `false`. Đây là một ràng buộc của mã kiểm chứng, không chứng minh rằng counter bắt buộc cần JMX. Hãy tách phần kiểm tra JMX trước khi dùng bài mẫu để thử riêng meter.

**Bài tập 3:** Một ứng dụng WebFlux đọc được `/actuator/health` nhưng không tìm thấy một số đo tên bắt đầu bằng `tomcat.`. Bạn cần kiểm tra gì?

Cần xác định server thực tế và điều kiện tạo số đo đó. Việc cùng hỗ trợ HTTP Actuator không tạo ra cùng một tập số đo đặc thù cho mọi server.

**Bài tập 4:** Một chương trình NONE có counter tăng đúng nhưng công cụ thu thập chỉ đọc URL HTTP không lấy được số liệu. Điều cần thay đổi là gì?

Cần quyết định lại cơ chế cung cấp dữ liệu cho công cụ đó hoặc chọn cách thu thập khác. Không được bỏ qua ranh giới giữa ghi số đo trong tiến trình và công bố số đo qua một giao thức cụ thể.

Sau bài này, khi đánh giá một khả năng Actuator, hãy xác định **web type thực tế, điều kiện của thành phần và cơ chế công bố**. Ba thông tin đó mới đủ để nói một khả năng có thể dùng như thế nào trong ứng dụng của bạn.
