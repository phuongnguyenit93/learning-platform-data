# Lỗi cấu hình bị dời sang lần sử dụng đầu tiên khi khởi tạo lười trong Spring Boot

## 1. Vấn đề: khởi động thành công nhưng tính năng hỏng ở lần gọi đầu

Trong Spring Boot, **lazy initialization** (khởi tạo lười) cho phép Spring trì hoãn việc tạo một bean cho đến lúc có thành phần thực sự yêu cầu bean đó. Cơ chế này có thể giảm công việc tại thời điểm startup, nhưng mang theo một hệ quả quan trọng: **lỗi cấu hình vốn được phát hiện khi tạo bean có thể không còn làm ứng dụng thất bại lúc khởi động; chúng chỉ lộ ra ở lần sử dụng đầu tiên**.

Ví dụ, một bean cần property bắt buộc **demo.remote.url** để được tạo. Nếu bean được tạo eager trong quá trình **ApplicationContext.refresh()**, việc thiếu property làm startup thất bại. Nếu bean được tạo lazy và chưa có thành phần khác yêu cầu nó, context có thể refresh xong, Spring Boot phát **ApplicationReadyEvent**, nhưng lần đầu gọi bean qua **getBean()** hoặc một dependency lazy mới gặp exception.

~~~text
EAGER (singleton thông thường)
    |
    +-- refresh()
          +-- tạo RemoteClient
                +-- demo.remote.url không có
                      +-- BeanCreationException
                            +-- startup FAIL
                            +-- không có ApplicationReadyEvent

LAZY (RemoteClient chưa được ai yêu cầu)
    |
    +-- refresh()
          +-- lưu BeanDefinition, chưa tạo RemoteClient
    +-- runners và ready event hoàn tất
          +-- startup nhìn như thành công
    +-- yêu cầu RemoteClient lần đầu
          +-- tạo bean
                +-- demo.remote.url không có
                      +-- BeanCreationException
                            +-- lỗi xuất hiện lúc sử dụng
~~~

**Điều cần hiểu đúng:** lazy initialization **không sửa được cấu hình sai**. Nó chỉ có thể **thay đổi thời điểm lỗi được phát hiện**. Khi lỗi xuất hiện muộn, sự cố có thể ảnh hưởng trực tiếp đến request của người dùng, message consumer hoặc một công việc nền thay vì bị phát hiện ở startup.

Bài học dùng ngữ cảnh **Spring Boot 3.3.x / Spring Framework 6.1, Java 17+**, và tập trung vào việc nhận diện, tái hiện, kiểm thử, giám sát và chủ động ngăn các lỗi cấu hình bị trì hoãn.

## 2. Khởi tạo eager và lazy khác nhau thế nào?

### 2.1. Singleton eager là mặc định

Trong Spring Framework, singleton bean thông thường sẽ được Spring tạo trong giai đoạn hoàn tất **refresh()**, trừ khi bean có cấu hình lazy hoặc có cơ chế vòng đời riêng. Khi khởi tạo, Spring phải:

1. Xác định BeanDefinition và phương thức tạo bean.
2. Resolve constructor/factory method parameters và dependency.
3. Khởi tạo đối tượng.
4. Inject properties, binding và các bước xử lý cần thiết.
5. Gọi BeanPostProcessor và initialization callbacks như **@PostConstruct** nếu có.
6. Lưu singleton đã tạo để các lần sử dụng tiếp theo nhận cùng đối tượng.

Nếu một property cần thiết bị thiếu trong factory method hoặc một dependency không thể resolve, lỗi có thể xuất hiện ngay trong chuỗi startup và ngăn context hoàn tất refresh.

### 2.2. Singleton lazy chỉ tạo khi có nhu cầu

Khi bean được đánh dấu lazy, BeanDefinition vẫn có mặt trong container, nhưng **instance của singleton không bị khởi tạo chỉ vì refresh đã đến pha tạo các singleton thông thường**.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    @Lazy
    RemoteClient remoteClient(Environment environment) {
        String url =
                environment.getRequiredProperty("demo.remote.url");
        return new RemoteClient(url);
    }
}
~~~

Đây là **snippet**, giả định đã có lớp **RemoteClient** và các import tương ứng. Khi context refresh mà **không có bean eager nào cần RemoteClient**, Spring có thể giữ bean chưa được tạo. Đến lúc một thành phần gọi:

~~~java
RemoteClient client = context.getBean(RemoteClient.class);
~~~

Spring mới thực thi factory method và đọc property bắt buộc. Nếu **demo.remote.url** không có, lỗi được phát hiện **ngay lần yêu cầu bean**, thay vì trong pha eager singleton creation.

**Không phải mọi lazy bean đều nhất định được tạo sau startup.** Nếu một singleton eager khác phụ thuộc trực tiếp vào nó, Spring vẫn phải tạo dependency khi khởi tạo bean eager. Lazy chỉ trì hoãn **khi chưa có nhu cầu thực sự**.

### 2.3. @Lazy, @Lazy(false) và lazy initialization toàn ứng dụng

Có hai cách cấu hình phổ biến:

- **@Lazy** trên một class component hoặc **@Bean** để áp dụng ở mức bean.
- Thuộc tính Spring Boot **spring.main.lazy-initialization=true** để bật lazy initialization trên diện rộng.

Ví dụ cấu hình Boot:

~~~properties
spring.main.lazy-initialization=true
~~~

Hoặc CLI:

~~~bash
java -jar app.jar --spring.main.lazy-initialization=true
~~~

Nếu muốn một bean **được khởi tạo eager dù ứng dụng bật global lazy**, Spring Boot hỗ trợ chỉ định:

~~~java
@Bean
@Lazy(false)
CriticalClient criticalClient(Environment environment) {
    return new CriticalClient(
            environment.getRequiredProperty("critical.endpoint"));
}
~~~

Đây là snippet giả định có **CriticalClient** và import **@Bean**, **@Lazy**, **Environment**. Ý nghĩa là **không trì hoãn** bean quan trọng: lỗi cấu hình liên quan được phát hiện trong startup khi singleton đó được khởi tạo theo vòng đời thông thường.

**Global lazy không có nghĩa 100% bean hạ tầng đều được trì hoãn.** Spring Boot có các phần tử cần được tạo sớm để hệ thống khởi động; một số bean có thể được tạo do processor, runner, lifecycle hoặc dependency khác yêu cầu. Luôn xét **dependency graph** và phiên bản Boot thực tế thay vì chỉ nhìn một property.

## 3. Loại lỗi nào có thể bị dời sang lần dùng đầu?

Không phải mọi lỗi đều được trì hoãn. Những lỗi phải **tạo instance hoặc sử dụng dependency** mới phát hiện thường là ứng viên.

### 3.1. Thiếu property bắt buộc khi factory method chạy

Ví dụ:

~~~java
@Bean
RemoteClient remoteClient(Environment environment) {
    String url =
            environment.getRequiredProperty("demo.remote.url");
    return new RemoteClient(url);
}
~~~

Nếu **demo.remote.url** thiếu, **getRequiredProperty(...)** ném exception khi method chạy. Khi bean lazy, việc chạy method bị dời đến khi container tạo bean lần đầu.

Cũng có thể xảy ra với injection qua **@Value**: placeholder bắt buộc không resolve được trong quá trình tạo bean có thể khiến **BeanCreationException** hoặc exception lồng bên trong xuất hiện tại thời điểm instantiation.

### 3.2. Giá trị có nhưng sai định dạng hoặc không hợp lệ

Ví dụ một bean parse URL, số cổng, timeout hoặc một enum khi được tạo:

~~~java
@Bean
RemoteClient remoteClient(Environment environment) {
    String endpoint =
            environment.getRequiredProperty("demo.remote.url");

    if (!endpoint.startsWith("https://")) {
        throw new IllegalArgumentException(
                "demo.remote.url must start with https://");
    }

    return new RemoteClient(endpoint);
}
~~~

Nếu bean lazy và chưa được yêu cầu, validation trong factory method **chưa chạy**. Cấu hình **demo.remote.url=http://insecure.example** có thể chưa tạo lỗi cho đến lúc bean đầu tiên được yêu cầu.

**Phân biệt:** validation của **@ConfigurationProperties** có thể được thực hiện khi bean đó được bind/khởi tạo, nhưng kết quả cụ thể phụ thuộc bean có bị yêu cầu sớm không và cách Boot cấu hình binding. Không nên tuyên bố mọi lỗi cấu hình đều bị hoãn theo cùng một cách.

### 3.3. Unsatisfied dependency chỉ được kiểm tra khi tạo bean

Một bean lazy có constructor yêu cầu bean khác:

~~~java
@Component
@Lazy
class ReportService {

    private final MissingFormatter formatter;

    ReportService(MissingFormatter formatter) {
        this.formatter = formatter;
    }
}
~~~

Đây là snippet giả định **MissingFormatter** là một type mà context không đăng ký bean. Nếu ReportService không được tạo trong refresh, lỗi thiếu dependency có thể chỉ xuất hiện khi container cố tạo ReportService.

Tuy nhiên, nếu một eager bean inject ReportService trực tiếp, dependency graph có thể ép Spring tạo ReportService ngay khi refresh; lỗi quay lại giai đoạn startup.

### 3.4. Lỗi từ @PostConstruct hoặc initialization callback

Ví dụ:

~~~java
@Component
@Lazy
class RemoteIndex {

    @PostConstruct
    void initialize() {
        // Nếu ở đây validate cấu hình hoặc gọi remote API,
        // lỗi có thể xuất hiện khi bean được tạo lần đầu.
    }
}
~~~

Đây là snippet cần import **@Component**, **@Lazy**, **@PostConstruct**; với Spring Boot 3 dùng **jakarta.annotation.PostConstruct**, không phải **javax.annotation.PostConstruct** của các API cũ.

Callback **@PostConstruct**, **InitializingBean.afterPropertiesSet()** và custom init method chạy trong quá trình bean initialization. Nếu bean lazy, các callback ấy cũng thường bị trì hoãn theo quá trình tạo bean.

**Cảnh báo:** không nên thực hiện I/O không có timeout trong @PostConstruct chỉ vì muốn fail-fast. Hãy tách validation cấu hình thuần khỏi kiểm tra kết nối mạng, quyết định rõ việc nào là điều kiện startup và việc nào được xử lý bằng retry ở runtime.

### 3.5. Lỗi khi lần đầu thực hiện thao tác nghiệp vụ

Ngay cả khi bean đã được tạo thành công, một lỗi có thể chỉ xuất hiện lúc method đầu tiên gọi backend: DNS sai, access token hết hạn, database không truy cập được hoặc một operation không được hỗ trợ.

Đó **không nhất thiết là lỗi lazy bean initialization**. Cần phân biệt:

- **Lỗi tạo bean:** xảy ra trong constructor, factory method, dependency injection, binding hoặc init callback.
- **Lỗi vận hành:** xảy ra sau khi bean đã tạo, khi một method thật sự kết nối hoặc thực hiện công việc.

Bật eager initialization có thể giúp phát hiện **lỗi tạo bean sớm hơn**, nhưng **không bảo đảm** mọi lỗi vận hành được phát hiện nếu không có hành động kiểm tra có chủ đích.

## 4. Những lỗi vẫn có thể xuất hiện trong startup dù bật lazy

Lazy initialization **không tắt** quá trình SpringApplication chuẩn bị Environment, phân tích cấu hình, đăng ký BeanDefinition, auto-configuration hay refresh context.

Một số lỗi có thể xảy ra trước khi bean lazy được khởi tạo:

| Loại lỗi | Vì sao vẫn có thể fail lúc startup? |
| --- | --- |
| **application.yaml** sai cú pháp nghiêm trọng | Config Data được parse ở pha chuẩn bị Environment |
| **spring.config.import** trỏ tới nguồn bắt buộc không tồn tại | Lỗi có thể xảy ra trong cơ chế nạp Config Data |
| Lỗi xử lý **@Configuration**, **@Import**, class path hoặc BeanDefinition | Các bước đăng ký/kiểm tra cấu hình xảy ra trong refresh |
| Trùng tên bean khi overriding bị cấm | Vấn đề registry được phát hiện khi đăng ký definition |
| Lỗi từ **BeanDefinitionRegistryPostProcessor** hoặc **BeanFactoryPostProcessor** | Processor cần chạy trong refresh trước singleton thông thường |
| Lỗi từ bean hạ tầng cần cho web server hoặc application context | Hạ tầng cần được khởi tạo để context hoạt động |
| Lỗi trong một **ApplicationRunner** được Boot gọi | Runner vẫn được gọi trước ApplicationReadyEvent |
| Lazy bean bị một eager bean phụ thuộc | Nhu cầu dependency ép lazy bean tạo sớm |

**Kết luận:** thuộc tính **spring.main.lazy-initialization=true** không phải một cách bỏ qua validation. Nó thay đổi chính sách tạo nhiều bean, trong khi phần còn lại của bootstrap vẫn thực thi.

## 5. Ví dụ Java 17+ chạy được: cấu hình thiếu, eager fail và lazy fail

Ví dụ sau chứng minh hai thời điểm thất bại bằng **cùng một mã nguồn** và **cùng một property bắt buộc**. Không cần dịch vụ HTTP thật, bởi mục tiêu là quan sát thời điểm factory method chạy.

### 5.1. Cấu trúc dự án

Sử dụng **Java 17+**, **Spring Boot 3.3.13**, Maven 3.9+:

~~~text
lazy-config-demo/
  pom.xml
  src/main/java/com/example/lazy/LazyFailureApplication.java
~~~

**pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>lazy-config-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

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

### 5.2. Mã ứng dụng hoàn chỉnh

**src/main/java/com/example/lazy/LazyFailureApplication.java**:

~~~java
package com.example.lazy;

import org.springframework.beans.BeansException;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class LazyFailureApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(LazyFailureApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("STARTUP | run returned");

            try {
                RemoteClient client = context.getBean(RemoteClient.class);
                client.call();
                System.out.println("FIRST_USE | success");
            } catch (BeansException ex) {
                System.out.println("FIRST_USE | bean creation failed");
                // Trong ứng dụng thật: ghi log lỗi đã che secrets,
                // phân loại nguyên nhân rồi quyết định fail-fast/retry.
            }
        }
    }

    @Bean
    RemoteClient remoteClient(Environment environment) {
        String url =
                environment.getRequiredProperty("demo.remote.url");

        if (!url.startsWith("https://")) {
            throw new IllegalArgumentException(
                    "demo.remote.url must start with https://");
        }

        System.out.println("BEAN | remoteClient created");
        return new RemoteClient(url);
    }

    public record RemoteClient(String url) {
        public void call() {
            // Ví dụ không thực sự kết nối mạng.
            System.out.println("USE | endpoint=" + url);
        }
    }
}
~~~

Giải thích các lựa chọn:

- **@Bean remoteClient** không có **@Lazy**. Như vậy cấu hình mặc định là eager và biến thể lazy được điều khiển bằng **spring.main.lazy-initialization=true**.
- **Environment.getRequiredProperty(...)** kiểm tra property khi factory method được gọi. Nếu property không có, nó ném exception; Spring có thể bọc trong một **BeanCreationException**.
- Validation **https://** được viết ngay trong factory method để minh họa lỗi giá trị không hợp lệ.
- **RemoteClient.call()** chỉ in chuỗi, không làm network I/O. Ví dụ do đó minh họa rõ lỗi **bean creation**, tránh trộn thêm lỗi mạng.
- **SpringApplication.run(...)** hoàn tất mới in **STARTUP**. Sau đó lệnh **getBean(RemoteClient.class)** chủ động yêu cầu bean.
- Catch **BeansException** ở ví dụ giúp nhìn thấy mốc thất bại mà không phụ thuộc tên exception con cụ thể. **Trong hệ thống production, không nên bắt exception rồi giả vờ thao tác đã thành công**.
- **WebApplicationType.NONE** và **try-with-resources** phù hợp cho ứng dụng CLI ngắn trong bài học. Không đóng context ngay sau run trong ứng dụng web cần phục vụ request liên tục.

### 5.3. Build và chạy không có property bắt buộc — lazy bật

Từ thư mục dự án:

~~~bash
mvn -q -DskipTests package
java -jar target/lazy-config-demo-1.0.0.jar --spring.main.lazy-initialization=true
~~~

**Các dòng do chính chương trình in:**

~~~text
STARTUP | run returned
FIRST_USE | bean creation failed
~~~

Spring Boot có thể in thêm log của framework. Không có dòng **BEAN | remoteClient created** vì factory method thất bại trước khi hoàn tất validation.

Ở lần chạy này, **SpringApplication.run(...) đã trả về context thành công**. Chỉ khi main gọi **context.getBean(RemoteClient.class)**, Spring mới cố tạo bean và phát hiện **demo.remote.url** thiếu. Đây chính là lỗi cấu hình bị dời sang lần sử dụng đầu tiên.

### 5.4. Chạy không có property — lazy tắt

~~~bash
java -jar target/lazy-config-demo-1.0.0.jar --spring.main.lazy-initialization=false
~~~

Trong cấu hình eager mặc định, Spring cố tạo **remoteClient** khi hoàn tất refresh. Factory method ném lỗi vì thiếu **demo.remote.url**. **SpringApplication.run(...) không trả về bình thường**, nên bạn **không thấy** dòng:

~~~text
STARTUP | run returned
~~~

Quá trình báo lỗi startup qua log/stack trace và ứng dụng thất bại. **Không cố khẳng định một stack trace nguyên văn**: tên exception lồng nhau và cách trình bày log phụ thuộc phiên bản/framework và logger. Quan hệ thời điểm quan trọng là **failure trước STARTUP**.

### 5.5. Property đúng — đối chiếu thứ tự tạo bean

Chạy lazy:

~~~bash
java -jar target/lazy-config-demo-1.0.0.jar \
  --spring.main.lazy-initialization=true \
  --demo.remote.url=https://example.invalid
~~~

**Các dòng do chương trình in:**

~~~text
STARTUP | run returned
BEAN | remoteClient created
USE | endpoint=https://example.invalid
FIRST_USE | success
~~~

Bean được tạo **sau** khi run trả về, ngay lúc main gọi getBean.

Chạy eager:

~~~bash
java -jar target/lazy-config-demo-1.0.0.jar \
  --spring.main.lazy-initialization=false \
  --demo.remote.url=https://example.invalid
~~~

**Các dòng do chương trình in:**

~~~text
BEAN | remoteClient created
STARTUP | run returned
USE | endpoint=https://example.invalid
FIRST_USE | success
~~~

Trong lần này, bean được tạo **trong startup**. Main chỉ tra cứu instance đã tồn tại.

### 5.6. Property sai định dạng — không phải chỉ lỗi thiếu key

Chạy:

~~~bash
java -jar target/lazy-config-demo-1.0.0.jar \
  --spring.main.lazy-initialization=true \
  --demo.remote.url=http://insecure.example
~~~

Context có thể hoàn tất startup, nhưng **context.getBean(RemoteClient.class)** làm factory method chạy, ném **IllegalArgumentException** từ validation, và main in:

~~~text
STARTUP | run returned
FIRST_USE | bean creation failed
~~~

Khi chuyển sang eager, validation thất bại trong refresh. Như vậy **lỗi thiếu property** và **giá trị không hợp lệ** đều có thể bị dời tới lần tạo bean đầu tiên.

## 6. Vì sao lazy bean đôi khi vẫn khiến startup thất bại?

Một annotation hoặc thuộc tính lazy không phải cơ chế ngăn bean được tạo trong mọi trường hợp. Spring luôn phải đáp ứng những dependency mà các bean khác yêu cầu.

### 6.1. Bean eager phụ thuộc trực tiếp vào bean lazy

Giả sử:

~~~java
@Component
class EagerReportRunner {

    private final LazyRemoteClient remoteClient;

    EagerReportRunner(LazyRemoteClient remoteClient) {
        this.remoteClient = remoteClient;
    }
}
~~~

và:

~~~java
@Component
@Lazy
class LazyRemoteClient {

    LazyRemoteClient(Environment environment) {
        environment.getRequiredProperty("demo.remote.url");
    }
}
~~~

Đây là snippets, cần import **@Component**, **@Lazy**, **Environment**. **EagerReportRunner** theo mặc định là một singleton eager. Khi tạo EagerReportRunner, Spring cần cung cấp **LazyRemoteClient** cho constructor. Vì vậy target lazy có thể bị tạo ngay trong startup để đáp ứng dependency.

**Kết luận:** cần nhìn **đồ thị phụ thuộc**, không chỉ nhãn lazy trên một class. Nếu startup vẫn fail dù đã thêm @Lazy, có thể một bean eager đang đòi dùng nó.

### 6.2. @Lazy trên injection point và lazy target bean là hai điều khác nhau

Spring hỗ trợ **@Lazy trên injection point** để cung cấp proxy trì hoãn việc resolve dependency thực sự:

~~~java
@Component
class ReportCoordinator {

    private final RemoteClient remoteClient;

    ReportCoordinator(@Lazy RemoteClient remoteClient) {
        this.remoteClient = remoteClient;
    }

    void execute() {
        remoteClient.call();
    }
}
~~~

Đây là **snippet minh họa**, yêu cầu RemoteClient là kiểu có thể proxy theo cấu hình Spring. Nếu RemoteClient là một **record/final class** như ví dụ hoàn chỉnh ở mục 5, không được mặc định rằng Spring có thể tạo proxy subclass cho nó. Khi cần trì hoãn dependency vào một kiểu final hoặc muốn biểu diễn thời điểm lookup minh bạch, **ObjectProvider** là lựa chọn tốt hơn.

Proxy lazy injection có thể khiến dependency chỉ được resolve lúc gọi method trên proxy, nhưng việc gọi method sớm vẫn có thể kích hoạt lỗi ngay startup.

### 6.3. ObjectProvider giúp trì hoãn lookup, không sửa cấu hình

Ví dụ:

~~~java
@Component
class ReportCoordinator {

    private final ObjectProvider<RemoteClient> clientProvider;

    ReportCoordinator(ObjectProvider<RemoteClient> clientProvider) {
        this.clientProvider = clientProvider;
    }

    void execute() {
        RemoteClient client = clientProvider.getObject();
        client.call();
    }
}
~~~

Đây là snippet có các import **@Component** và **ObjectProvider**. Constructor của ReportCoordinator chỉ nhận provider. Khi **execute()** gọi **getObject()**, container mới phải resolve target bean nếu chưa có.

**Điểm mấu chốt:** nếu constructor hoặc **@PostConstruct** của ReportCoordinator **gọi execute() ngay**, lỗi vẫn có thể xuất hiện trong startup. ObjectProvider chỉ trì hoãn lookup **cho tới lúc lập trình viên thực sự yêu cầu**.

### 6.4. Runner, lifecycle và hạ tầng có thể đòi bean sớm

Một **ApplicationRunner** có thể được Spring Boot gọi sau refresh nhưng **trước ApplicationReadyEvent**. Nếu runner nhận hoặc gọi một lazy bean, lỗi có thể xảy ra trong giai đoạn startup sau refresh và làm lần chạy thất bại trước readiness.

Tương tự, BeanFactoryPostProcessor, BeanPostProcessor, listener/lifecycle hạ tầng hoặc web server có thể gây khởi tạo sớm theo nhu cầu framework. Không nên coi mọi bean lazy là “chỉ tạo sau khi application ready”.

## 7. Readiness, health checks và độ trễ của request đầu

### 7.1. Ready không có nghĩa mọi lazy bean đã hợp lệ

Trong Spring Boot, **ApplicationReadyEvent** báo chuỗi startup thông thường đã hoàn thành. Nó **không ngụ ý tất cả bean lazy đã được tạo** hay mọi external dependency đều đã kết nối thành công.

Ví dụ một ứng dụng web có controller/service lazy không được yêu cầu khi startup. Health/readiness endpoint có thể báo trạng thái chấp nhận traffic, rồi request đầu vào endpoint đặc biệt mới kích hoạt service và gặp lỗi cấu hình. Việc Actuator có phát hiện lỗi hay không phụ thuộc health indicators nào được bật, chúng kiểm tra những gì và các bean nào đã được khởi tạo.

**Không đánh đồng “HTTP port đã mở”, “Spring Boot ready” và “mọi tính năng đều hoạt động”.** Đây là ba mức bảo đảm khác nhau.

### 7.2. First-hit latency và đồng thời

Ngay cả khi cấu hình đúng, lần gọi đầu tiên có thể chậm hơn vì cần:

- Tạo bean cùng toàn bộ dependency còn thiếu.
- Bind configuration properties và validate.
- Xây proxy hoặc khởi tạo cache liên quan.
- Mở kết nối tới nguồn dữ liệu (nếu logic khởi tạo yêu cầu).
- Thực hiện @PostConstruct hoặc custom initialization.

Nếu nhiều request tới cùng một singleton lazy gần như cùng lúc, Spring phải phối hợp việc tạo singleton đó; các request có thể cùng chịu chậm hoặc nhận lỗi theo kết quả khởi tạo. Không thiết kế SLA cho request đầu giống request đã warm-up mà không đo lường.

### 7.3. Một lỗi bị dời từ startup sang production traffic

Tình huống:

~~~text
Deploy phiên bản mới
       |
       +-- lazy initialization = true
       +-- optionalFeature bean có URL sai
       +-- startup và readiness thành công
       |
       +-- traffic đầu tiên tới optionalFeature
                |
                +-- tạo bean -> validation lỗi
                +-- request thất bại
                +-- monitoring mới phát hiện
~~~

Điều này có thể **nguy hiểm hơn fail-fast** với các chức năng quan trọng. Khi bean bắt buộc để phục vụ nghiệp vụ chính, việc trả lỗi ngay lúc startup thường giúp rollout thất bại sớm và tránh chuyển traffic sang phiên bản chưa sẵn sàng.

Với chức năng tùy chọn ít sử dụng, lazy initialization vẫn có thể hữu ích, nhưng phải có telemetry và chiến lược lỗi rõ ràng.

## 8. Cách phát hiện lỗi quan trọng sớm mà không mất toàn bộ lợi ích lazy

### 8.1. Đánh dấu những bean quan trọng là eager

Nếu bật global lazy, có thể dùng **@Lazy(false)** cho bean bắt buộc:

~~~java
@Configuration(proxyBeanMethods = false)
class CriticalConfiguration {

    @Bean
    @Lazy(false)
    CriticalService criticalService(Environment environment) {
        String endpoint =
                environment.getRequiredProperty("critical.endpoint");
        return new CriticalService(endpoint);
    }
}
~~~

Snippet giả định class **CriticalService** đã khai báo; cần import **Configuration**, **Bean**, **Lazy**, **Environment**. Bean phải được Spring quản lý như một singleton bình thường. Khi cấu hình hợp lệ, service sẽ được tạo trong startup; khi thiếu property, nó có thể khiến startup thất bại đúng thời điểm mong muốn.

**Dùng có chọn lọc.** Nếu đánh dấu tất cả bean đều eager thì mất lợi ích của global lazy. Định nghĩa rõ bean nào thật sự cần thiết cho readiness, bean nào chỉ cần khi một tính năng phụ được gọi.

### 8.2. Validate cấu hình độc lập với việc tạo service

Không nhất thiết phải khởi tạo toàn bộ client hoặc mở network connection chỉ để kiểm tra định dạng một property. Có thể tạo một **startup validator** gọn kiểm tra các điều kiện bắt buộc:

~~~java
@Component
class CriticalConfigValidator implements ApplicationRunner {

    private final Environment environment;

    CriticalConfigValidator(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String url =
                environment.getRequiredProperty("critical.endpoint");

        if (!url.startsWith("https://")) {
            throw new IllegalArgumentException(
                    "critical.endpoint must start with https://");
        }
    }
}
~~~

Đây là snippet cần import **@Component**, **ApplicationRunner**, **ApplicationArguments**, **Environment**. Boot gọi runner trước **ApplicationReadyEvent**. Vì vậy nếu validator được đăng ký và được chạy bình thường, cấu hình không hợp lệ làm startup thất bại **trước ready**, ngay cả khi client sử dụng property ấy còn lazy.

Ưu điểm: validation nhẹ, không phải tạo client hoặc kết nối mạng. Nhược điểm: có thể bị **lặp validation** ở nhiều nơi; nên tách quy tắc vào class nhỏ dùng chung cho startup validator và lúc xây client để tránh hai chính sách khác nhau.

### 8.3. Prewarm một vài dependency thiết yếu

Nếu điều kiện sẵn sàng yêu cầu một số lazy bean phải được tạo và thực hiện initialization, runner có thể yêu cầu chúng một cách có chủ đích:

~~~java
@Component
class CriticalBeanWarmup implements ApplicationRunner {

    private final ObjectProvider<CriticalClient> clientProvider;

    CriticalBeanWarmup(
            ObjectProvider<CriticalClient> clientProvider) {
        this.clientProvider = clientProvider;
    }

    @Override
    public void run(ApplicationArguments args) {
        clientProvider.getObject();
        // Nếu cần, gọi một thao tác kiểm tra rất cụ thể.
    }
}
~~~

Đây là snippet giả định có **CriticalClient**, import **ObjectProvider** và API runner. **getObject()** kích hoạt tạo target nếu chưa tồn tại; lỗi tạo bean làm runner thất bại và chặn mốc ready của lần khởi động.

Không prewarm tất cả bean một cách mù quáng. Nếu cần kiểm tra external service, phải đặt **timeout**, giới hạn retry, xác định ứng dụng có thật sự cần backend đó để nhận traffic không và tránh gây tải lớn trong rollout.

### 8.4. Chọn mức kiểm tra health/readiness thích hợp

Với Actuator/Kubernetes, nên phân biệt:

- **Liveness:** tiến trình còn hoạt động hay bị kẹt, không nên phụ thuộc quá nhiều vào dịch vụ ngoài.
- **Readiness:** ứng dụng có thể phục vụ workload hiện tại không.
- **Validation lúc startup:** cấu hình tĩnh bắt buộc có hợp lệ không.
- **Runtime monitoring:** tác vụ lazy, optional feature và các dependency phát sinh lỗi sau khi ready.

Một readiness indicator custom có thể kiểm tra thành phần thiết yếu, nhưng không nên làm readiness phụ thuộc mọi feature tùy chọn hoặc mạng tạm thời mất kết nối, vì điều đó có thể làm rollout/cluster bất ổn. Health check phải có mục tiêu và giới hạn chi phí.

## 9. Thực hành về @ConfigurationProperties và validation

### 9.1. Rủi ro khi validation gắn vào bean bị tạo lười

Nếu một bean cấu hình được tạo bằng **@ConfigurationProperties** và có validation (ví dụ **@Validated** cùng **@NotBlank**), việc bind/validate thường gắn với **quá trình tạo bean cấu hình đó**. Nếu bean ấy thật sự lazy và chưa ai yêu cầu, lỗi có thể bị dời tới lúc tạo.

Ví dụ conceptual:

~~~java
@ConfigurationProperties(prefix = "demo.remote")
@Validated
public class RemoteProperties {

    @NotBlank
    private String url;

    public String getUrl() {
        return url;
    }

    public void setUrl(String url) {
        this.url = url;
    }
}
~~~

Đây là snippet, cần import **ConfigurationProperties**, **Validated**, **NotBlank**, và dự án cần dependency validation phù hợp (chẳng hạn **spring-boot-starter-validation**). Bean phải được đăng ký qua **@EnableConfigurationProperties**, configuration properties scanning hoặc cơ chế tương ứng.

**Không khẳng định rằng mọi @ConfigurationProperties bean luôn được khởi tạo lazy.** Auto-configuration, binding hoặc eager consumer có thể tạo chúng sớm; những điều kiện ở pha metadata vẫn được đánh giá trong refresh. Điều cần kiểm tra là **thời điểm binding/validation thực tế của bean cấu hình cụ thể**.

### 9.2. Fail-fast với thuộc tính bắt buộc

Nếu **demo.remote.url** là cấu hình không thể thiếu để ứng dụng xử lý request cốt lõi:

1. Xác định schema/config contract rõ ràng.
2. Validate format, độ dài, bắt buộc nhập hoặc tập giá trị hợp lệ trong bước startup.
3. Tách validation thuần khỏi network I/O khi có thể.
4. Chỉ công bố readiness thành công sau khi các điều kiện tối thiểu được đáp ứng.
5. Có test cho property thiếu/sai định dạng và cho cấu hình hợp lệ.

Một ứng dụng fail-fast đáng tin thường có tín hiệu triển khai tốt hơn việc khởi động thành công rồi trả lỗi trên request đầu.

## 10. Kiểm thử sự khác nhau giữa refresh và lần tạo bean đầu

Không cần chạy web server để xác minh nguyên lý. Trong Spring Framework, **@Lazy** trên một **@Bean** có thể được kiểm tra trực tiếp qua **AnnotationConfigApplicationContext**. Đây là test về semantics của **bean-level lazy**, còn global setting **spring.main.lazy-initialization** thuộc Spring Boot và nên được kiểm tra bổ sung bằng SpringApplication thật.

### 10.1. Thêm JUnit

Trong dự án Maven ở mục 5, bổ sung dependency test vào pom.xml:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

### 10.2. Unit/context test cho @Lazy bean

Tạo file **src/test/java/com/example/lazy/LazyBeanBehaviorTest.java**:

~~~java
package com.example.lazy;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.BeansException;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LazyBeanBehaviorTest {

    @Configuration(proxyBeanMethods = false)
    static class TestConfiguration {

        @Bean
        @Lazy
        LazyFailureApplication.RemoteClient remoteClient(
                Environment environment) {
            String url =
                    environment.getRequiredProperty("demo.remote.url");
            return new LazyFailureApplication.RemoteClient(url);
        }
    }

    @Test
    void missingPropertyFailsOnFirstLookupNotRefresh() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.register(TestConfiguration.class);
            context.refresh();

            assertTrue(context.isActive());
            assertFalse(
                    context.getBeanFactory()
                           .containsSingleton("remoteClient"));

            assertThrows(
                    BeansException.class,
                    () -> context.getBean(
                            LazyFailureApplication.RemoteClient.class));
        }
    }

    @Test
    void validPropertyCreatesBeanOnlyWhenRequested() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource(
                            "test",
                            Map.of("demo.remote.url",
                                   "https://example.invalid")));

            context.register(TestConfiguration.class);
            context.refresh();

            assertFalse(
                    context.getBeanFactory()
                           .containsSingleton("remoteClient"));

            var client = context.getBean(
                    LazyFailureApplication.RemoteClient.class);

            assertEquals("https://example.invalid", client.url());
            assertTrue(
                    context.getBeanFactory()
                           .containsSingleton("remoteClient"));
        }
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Lý do test có ý nghĩa:**

- Method **remoteClient(...)** trong TestConfiguration có **@Lazy**; context refresh không tự khởi tạo singleton ấy.
- **containsSingleton("remoteClient")** trước lookup trả false trong cấu hình test này, dù definition đã được đăng ký.
- Nếu thiếu property, **getBean(...)** kích hoạt factory method, tạo lỗi thuộc nhóm **BeansException**.
- Nếu property hợp lệ, getBean tạo instance rồi **containsSingleton** trả true.
- Test không cần database hoặc HTTP server vì lỗi được thiết kế ở tầng configuration validation.

**Giới hạn:** test này chứng minh **Spring Framework @Lazy** ở mức bean, chứ không trực tiếp chứng minh toàn bộ cơ chế global **spring.main.lazy-initialization=true** của Spring Boot. Để kiểm chứng global property, hãy chạy chương trình mẫu ở mục 5 qua hai lệnh CLI hoặc viết startup integration test dùng SpringApplication thật.

### 10.3. Test bootstrap toàn ứng dụng

Một kiểm thử tích hợp nên bao phủ tối thiểu:

| Tình huống | Kỳ vọng |
| --- | --- |
| Global lazy **false**, thiếu demo.remote.url | **run(...) thất bại**, không tới đoạn MAIN sau run |
| Global lazy **true**, thiếu demo.remote.url, chưa lookup | **run(...) hoàn tất** |
| Global lazy **true**, thiếu demo.remote.url, gọi getBean | **Lỗi tại first lookup** |
| Global lazy **true**, endpoint hợp lệ, gọi getBean | **Bean được tạo thành công ở lookup** |
| Global lazy **false**, endpoint hợp lệ | **Bean được tạo trong refresh** |
| Bean có **@Lazy(false)** dù global lazy true | **Bean được tạo eager**, lỗi tĩnh có thể fail startup |
| Lazy bean bị eager bean inject trực tiếp | **Có thể bị tạo ngay trong startup** |

Trong CI, khi test startup có failure dự kiến, test nên **assert exception từ run**, thay vì để process thất bại khiến cả pipeline bị báo lỗi không có ngữ cảnh.

Đối với ứng dụng web, có thể thêm một test request đầu tiên tới endpoint phụ thuộc bean lazy để đo **first-hit latency** và bảo đảm lỗi được trả theo error handling phù hợp. Không nên dùng một phép đo thời gian đơn lẻ để đưa ra kết luận hiệu năng cho production.

## 11. Xử lý lỗi thực tế mà không che giấu misconfiguration

### 11.1. Không bắt exception rồi trả thành công giả

Trong ví dụ giáo dục, main bắt BeansException để in mốc thất bại. Trong production, cách sau có thể nguy hiểm:

~~~java
try {
    criticalService.execute();
} catch (BeansException ex) {
    return "OK";
}
~~~

Đây là snippet minh họa anti-pattern. Nó biến lỗi cấu hình thành **thành công giả**, gây khó phát hiện và có thể làm sai nghiệp vụ. Với tính năng quan trọng, hãy fail startup hoặc fail request rõ ràng, log lỗi an toàn và báo metric/alert phù hợp.

### 11.2. Chẩn đoán exception chain

Một lỗi lazy thường biểu hiện qua chuỗi exception:

~~~text
BeanCreationException / UnsatisfiedDependencyException
    |
    +-- bean name hoặc dependency liên quan
            |
            +-- factory method / constructor / binding
                    |
                    +-- IllegalStateException
                        (required property demo.remote.url not found)
~~~

Đây là sơ đồ điển hình, **không phải stack trace bắt buộc**. Tên exception con, vị trí message và số lớp wrapper phụ thuộc cách bean được khai báo và phiên bản framework. Khi debug cần đọc **root cause**, bean name và thời điểm lỗi xảy ra.

Phân loại:

- **Thiếu property:** kiểm tra Environment và PropertySources theo precedence, nhưng không ghi secrets.
- **Sai định dạng:** thêm validation rõ ràng và thông báo lỗi có tên key.
- **Thiếu bean dependency:** xem component scan, auto-configuration, điều kiện và injection graph.
- **Init callback hỏng:** xem logic @PostConstruct/afterPropertiesSet và side effect thực hiện trong đó.
- **External resource unavailable:** phân biệt lỗi cấu hình tĩnh với lỗi mạng tạm thời; dùng timeout và chính sách retry/circuit breaker phù hợp.

### 11.3. Log và metrics đúng ngữ cảnh

Nên ghi hoặc quan sát:

- **Bean name** và class bị lỗi (không đưa cả object chứa secret vào log).
- **Lifecycle phase**: refresh, runner, first lookup, first HTTP request hay background job.
- **Feature/endpoint** liên quan.
- Mức độ ảnh hưởng: critical/optional.
- **Số lần lỗi** và **thời điểm phát hiện sau deploy**.
- Nếu đo first-hit latency: đo riêng khởi tạo bean và tổng thời gian request khi có thể.

Không in toàn bộ Environment, command line hay cấu hình bí mật vào log chỉ để giải thích lỗi. Với Actuator, những endpoint tiết lộ cấu hình phải được bảo vệ và che thông tin nhạy cảm.

## 12. Trade-off hiệu năng, vận hành và thiết kế

### 12.1. Lợi ích thật của lazy initialization

Một ứng dụng có nhiều bean nhưng chỉ một phần chức năng được sử dụng ở mỗi lần chạy có thể tiết kiệm thời gian startup và tài nguyên ban đầu nhờ lazy initialization. Điều này đáng cân nhắc cho:

- Ứng dụng có nhiều feature tùy chọn.
- Công cụ CLI mà mỗi lần chỉ chạy một nhóm chức năng.
- Môi trường development, test hoặc một số workload mà thời gian khởi động quan trọng.
- Tính năng chỉ cần tải module lớn khi thực sự được gọi.

Nhưng lợi ích thực tế phụ thuộc lượng bean được tránh khởi tạo, dependency graph và workload. Không nên hứa lazy luôn làm ứng dụng nhanh hơn về tổng thể.

### 12.2. Chi phí có thể chuyển sang thời điểm nhạy cảm hơn

Lazy có thể làm tăng:

- **Độ trễ request đầu tiên**.
- **Độ biến thiên latency** giữa request đầu và request sau.
- **Rủi ro lỗi runtime sau ready**.
- Độ khó phân tích startup, dependency và health.
- Những đợt tải tăng bất ngờ khi một nhóm người dùng cùng kích hoạt feature chưa được warm-up.

Nếu ứng dụng phục vụ traffic lớn với SLA nghiêm ngặt, hãy benchmark các đường đi quan trọng và prewarm đúng chỗ. Không dùng lazy như giải pháp duy nhất cho startup chậm mà không tìm nguyên nhân.

### 12.3. Chiến lược cân bằng

Một chính sách thực tế:

| Loại thành phần | Gợi ý |
| --- | --- |
| Service cốt lõi và dependency bắt buộc để nhận traffic | **Eager** hoặc validate/prewarm trước ready |
| Feature tùy chọn hiếm dùng | Có thể **lazy**, có quan sát first-use failure |
| Bean cấu hình chỉ chứa metadata nhưng bắt buộc hợp lệ | Validate vào startup, không phụ thuộc việc consumer tạo bean |
| Client kết nối backend có thể tạm thời unavailable | Tách config validation khỏi runtime connectivity; timeout/retry rõ |
| Bean rất nặng nhưng dùng thường xuyên | Cân nhắc prewarm sau khi đo chi phí và readiness |
| Startup nhanh ở môi trường dev/test | Có thể bật lazy theo profile, vẫn test eager path trước production |

Không có một cờ bật lazy đúng cho mọi hệ thống. Quyết định nên dựa trên **yêu cầu readiness, tác động khi lỗi muộn và chi phí tạo bean thực tế**.

## 13. Các lỗi hiểu nhầm thường gặp

### 13.1. “spring.main.lazy-initialization=true làm ứng dụng luôn startup được”

Sai. Config Data, cấu hình hạ tầng, BeanFactoryPostProcessor và những dependency cần thiết vẫn có thể thất bại trước khi context hoàn tất.

### 13.2. “Có @Lazy thì bean chắc chắn chưa tạo trong startup”

Sai. Một eager bean hoặc runner có thể yêu cầu nó trước ready. Lazy thay đổi **mặc định tạo bean**, không tạo ra một ranh giới thời gian bất khả xâm phạm.

### 13.3. “@Lazy trên injection point và @Lazy trên target bean tương đương”

Không hoàn toàn. Annotation trên bean điều khiển BeanDefinition; annotation trên injection point thường cung cấp **proxy trì hoãn resolve target**. Khi target là final class hoặc record, proxy bằng subclass có thể không khả thi; **ObjectProvider** thường rõ hơn cho lookup có chủ đích.

### 13.4. “Nếu startup ready thì tất cả @ConfigurationProperties đã validate xong”

Không nhất thiết. Việc bind/validate gắn với tạo bean cấu hình có thể bị trì hoãn, trừ khi bean đã được yêu cầu hoặc có cơ chế startup validation riêng.

### 13.5. “Bật eager sẽ tự kiểm tra kết nối remote”

Không tự động. Eager chỉ buộc quá trình tạo bean chạy. Nếu constructor không thực hiện network I/O và client chỉ kết nối khi gọi method, backend vẫn có thể lỗi ở lần request đầu.

### 13.6. “Lỗi xảy ra sau ready chắc chắn do @Lazy”

Không đủ căn cứ. Có thể là lỗi runtime, dữ liệu đầu vào, timeout mạng, cache chưa warm, credential hết hạn hoặc một vấn đề concurrency. Phải xác định **bean có đang được tạo tại lần gọi đó hay không** và đọc root cause.

### 13.7. “Chỉ cần gọi getBean cho mọi bean trong startup”

Không nên. Cách này có thể tạo hàng loạt resource không cần thiết, tăng latency startup và làm mất lợi ích của lazy. Chỉ validate/prewarm những dependency thực sự bắt buộc.

### 13.8. “Catch exception first use là đủ, readiness vẫn có thể xanh”

Với tính năng bắt buộc, readiness xanh trong khi functionality hỏng là tín hiệu vận hành sai. Cần điều chỉnh startup validation hoặc readiness policy thay vì chỉ che exception.

### 13.9. “Dùng @PostConstruct để gọi external API không cần timeout”

Không an toàn. Nếu bean lazy, network failure chỉ xuất hiện ở request đầu. Nếu eager, network failure có thể kéo dài hoặc chặn startup. Dù ở pha nào, I/O cần timeout, retry policy và tiêu chí fail-open/fail-closed rõ.

### 13.10. “Tắt lazy ở production là đủ, không cần test”

Vẫn cần test cấu hình thiếu, binding, profile, conditions và behavior của external dependencies. Eager giúp phát hiện một nhóm lỗi sớm hơn, nhưng không tự bảo đảm tính đúng của mọi chức năng.

## 14. Checklist kiểm tra trước khi bật lazy initialization

- [ ] Biết chính xác bean nào được đánh dấu lazy và bean nào vẫn eager.
- [ ] Đã xem xét dependency graph: có singleton eager nào ép tạo target lazy sớm?
- [ ] Những property bắt buộc cho tính năng cốt lõi đã được validate trước ready.
- [ ] Phân biệt lỗi tạo bean với lỗi khi gọi method/network.
- [ ] Có test cho property thiếu, giá trị sai và trường hợp hợp lệ.
- [ ] Có test cho cả **spring.main.lazy-initialization=true** và **false** khi behavior quan trọng.
- [ ] Không giả định @ConfigurationProperties luôn bind/validate trước ready.
- [ ] Có chiến lược @Lazy(false) hoặc prewarm chọn lọc đối với dependency quan trọng.
- [ ] First-hit latency đã được đo trên tuyến request thật.
- [ ] Readiness/liveness có mục tiêu và không kiểm tra tràn lan external dependencies.
- [ ] Có log/metrics theo bean, feature và pha lỗi, không lộ secrets.
- [ ] Runner không bị block vô hạn bởi validation hoặc kết nối mạng.
- [ ] Không dùng catch-all để báo thành công giả khi critical bean hỏng.
- [ ] Đã xem xét behavior với nhiều context, background jobs và consumer ít hoạt động.
- [ ] Có tài liệu vận hành giải thích vì sao một số lỗi có thể xuất hiện sau deploy.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Một singleton lazy cần property bắt buộc, nhưng chưa có bean khác yêu cầu. Spring Boot có chắc chắn phát hiện property bị thiếu trong refresh không?

**Đáp án:** Không. Nếu việc kiểm tra chỉ xảy ra khi tạo bean và chưa có ai yêu cầu bean, lỗi có thể bị trì hoãn đến lúc bean được tạo lần đầu.

**Câu 2.** Tại sao cùng một cấu hình thiếu property, eager có thể fail startup còn lazy có thể fail ở request đầu tiên?

**Đáp án:** Eager chạy factory method/constructor/init callback trong giai đoạn tạo singleton của refresh. Lazy hoãn những bước ấy tới lần cần instance, nên validation gắn với chúng cũng bị hoãn.

**Câu 3.** Một bean có **@Lazy** nhưng bị singleton eager inject qua constructor. Có bảo đảm bean lazy chỉ tạo sau ready không?

**Đáp án:** Không. Dependency của singleton eager có thể buộc Spring tạo bean lazy ngay trong startup.

**Câu 4.** Bật lazy có ngăn lỗi do file YAML sai cú pháp được phát hiện lúc SpringApplication chuẩn bị Environment không?

**Đáp án:** Không. Phân tích Config Data thuộc bootstrap và vẫn có thể thất bại trước khi container tạo singleton ứng dụng.

**Câu 5.** **@Lazy(false)** dùng trong trường hợp nào?

**Đáp án:** Khi muốn một bean quan trọng được khởi tạo eager, kể cả lúc ứng dụng bật lazy initialization trên diện rộng, để phát hiện lỗi liên quan sớm hơn.

**Câu 6.** **ObjectProvider.getObject()** giúp sửa một URL cấu hình sai không?

**Đáp án:** Không. Nó chỉ trì hoãn lookup đến lúc getObject được gọi; nếu factory method cần URL và URL vẫn sai, lỗi vẫn xảy ra ở lần lookup.

**Câu 7.** Khi bean đã tạo eager thành công, có chắc DNS/backend luôn hoạt động không?

**Đáp án:** Không. Nếu bean chưa thử kết nối thực, lỗi kết nối có thể xảy ra trong một method ở runtime. Đó là lỗi vận hành khác với validation/creation.

**Câu 8.** Tại sao readiness endpoint có thể báo healthy nhưng một tính năng lazy vẫn lỗi?

**Đáp án:** Readiness không tự tạo và validate mọi bean lazy. Nếu health indicators không kiểm tra tính năng ấy và chưa có request kích hoạt bean, lỗi chưa lộ ra.

**Câu 9.** Muốn bắt buộc một property hợp lệ trước ready nhưng vẫn giữ client lazy, có giải pháp nào?

**Đáp án:** Tách validation cấu hình vào một bước startup gọn (chẳng hạn ApplicationRunner), hoặc một bean validator eager; không nhất thiết tạo client/network connection đầy đủ.

**Câu 10.** Unit test dùng **AnnotationConfigApplicationContext** với @Bean @Lazy đã chứng minh cờ Spring Boot global lazy hoạt động đúng chưa?

**Đáp án:** Chưa. Nó chứng minh semantics lazy ở mức Spring bean. Cần chạy SpringApplication với global property để xác minh phần tùy biến của Boot.

## 16. Tổng kết và tài liệu chính thức

**Lazy initialization thay đổi thời điểm tạo bean, nên cũng có thể dời thời điểm phát hiện lỗi cấu hình gắn với việc tạo bean.** Với singleton eager, missing property, dependency không resolve hoặc lỗi initialization có thể khiến startup thất bại. Với singleton lazy chưa được yêu cầu, context vẫn có thể ready, và lỗi chỉ lộ ra ở lần đầu tạo instance.

Tuy nhiên, **lazy không trì hoãn tất cả các lỗi**: Config Data, registry, post-processors, infrastructure và những dependency bị yêu cầu sớm vẫn có thể fail trong refresh. Chọn **@Lazy(false)**, validation startup, prewarm có chọn lọc và readiness policy đúng cho những thành phần quan trọng; dùng unit/context test và chạy cả hai biến thể eager/lazy để biết lỗi sẽ xuất hiện khi nào. Đừng hy sinh độ tin cậy production chỉ để startup nhanh hơn mà không đo first-hit latency và mức độ ảnh hưởng của lỗi muộn.

Tài liệu chính thức:

- Spring Boot — Lazy Initialization: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Framework — Lazy-initialized Beans: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html
- Spring Framework — @Lazy API: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/context/annotation/Lazy.html
- Spring Framework — ObjectProvider API: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/ObjectProvider.html
- Spring Boot — Configuration Properties and Validation: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot — Application Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Framework — BeanCreationException API: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/BeanCreationException.html