# EnvironmentPostProcessor và quan hệ với giai đoạn chuẩn bị Environment trong Spring Boot

## 1. Environment là gì, và tại sao phải chuẩn bị nó sớm?

Trong ứng dụng Spring Boot, **Environment** là giao diện của Spring Framework để tra cứu cấu hình theo key và nhận diện các profile đang hoạt động. Thay vì mọi lớp tự đọc file cấu hình, bean có thể lấy dữ liệu qua **Environment**, **@Value** hoặc được bind bằng **@ConfigurationProperties**. Các giá trị xuất phát từ nhiều **PropertySource**, ví dụ:

- Tham số dòng lệnh như **--server.port=9090**.
- Java system properties như **-Ddemo.mode=production**.
- Biến môi trường hệ điều hành.
- **application.properties** hoặc **application.yml**, bao gồm cấu hình theo profile.
- Default properties của **SpringApplication**.
- Nguồn tùy biến mà ứng dụng hoặc thư viện thêm vào.

**ConfigurableEnvironment** cho phép sửa danh sách **MutablePropertySources**, cũng như thay đổi một số cấu hình profile theo đúng contract. Mỗi **PropertySource** có tên riêng và có thể cung cấp giá trị cho một tập key. Khi nhiều nguồn có cùng key, **thứ tự ưu tiên của các PropertySource** quyết định giá trị hiệu lực.

Một số thiết lập phải có **trước khi Spring tạo và refresh ApplicationContext**: cấu hình web application type, logging ban đầu, cách nạp config data, profile liên quan đến quá trình bootstrap và các tham số có tác động đến quyết định auto-configuration. Do đó Spring Boot có pha **prepare Environment** trước khi tạo các bean nghiệp vụ.

**EnvironmentPostProcessor** là điểm mở rộng dành cho pha sớm này. Nó cho phép can thiệp vào **Environment** mà Spring Boot đang chuẩn bị, khi ApplicationContext **chưa được refresh**.

## 2. EnvironmentPostProcessor là gì?

Trong Spring Boot 3.3, interface có tên đầy đủ:

**org.springframework.boot.env.EnvironmentPostProcessor**

Và khai báo phương thức cốt lõi:

~~~java
void postProcessEnvironment(
        ConfigurableEnvironment environment,
        SpringApplication application);
~~~

Ý nghĩa của hai tham số:

- **environment:** Environment đang được Boot chuẩn bị; có thể thêm, thay thế, sắp xếp hoặc kiểm tra PropertySource theo API **getPropertySources()**.
- **application:** đối tượng SpringApplication đang bootstrap; dùng khi cần thông tin/cấu hình bootstrap phù hợp, không phải một ApplicationContext đã refresh.

Ví dụ về những nhu cầu hợp lý: bổ sung default properties từ một nguồn riêng, chuẩn hóa một nhóm cấu hình tùy chỉnh, thêm PropertySource với mức ưu tiên được chọn, hoặc tích hợp cơ chế cấu hình sớm của một thư viện.

**EnvironmentPostProcessor không phải BeanPostProcessor.** Interface này xử lý **môi trường cấu hình** trước quá trình tạo bean thông thường. Nó cũng không phải một bean được lấy từ ApplicationContext để thực thi logic nghiệp vụ.

## 3. Nó nằm ở đâu trong quá trình khởi chạy?

Sơ đồ khái niệm theo Spring Boot 3.3:

~~~text
main(String[] args)
       |
       v
SpringApplication.run(args)
       |
       v
Tạo/chọn và cấu hình ConfigurableEnvironment
       |
       +--> Nạp nguồn ban đầu (system/CLI/defaults...)
       |
       v
ApplicationEnvironmentPreparedEvent được xử lý
       |
       +--> EnvironmentPostProcessorApplicationListener
       |         |
       |         +--> ConfigDataEnvironmentPostProcessor
       |         |       nạp application.properties/yml, profile config...
       |         |
       |         +--> Các EnvironmentPostProcessor khác
       |                 thêm/chỉnh PropertySources theo thứ tự
       |
       v
Environment đã được bổ sung/chuẩn bị
       |
       v
Bind những tùy chọn SpringApplication thích hợp
       |
       v
Tạo ApplicationContext tương ứng
       |
       v
Áp dụng ApplicationContextInitializer
       |
       v
Nạp bean definitions, refresh ApplicationContext
       |
       v
Tạo bean, dependency injection, lifecycle...
       |
       v
ApplicationRunner / CommandLineRunner
       |
       v
ApplicationReadyEvent
~~~

Sơ đồ lược bỏ những callback và listener khác; không khẳng định mỗi EnvironmentPostProcessor hoạt động trong một bước đồng nhất hoặc các listener khác luôn chạy sau nó. Điểm cần giữ là **EnvironmentPostProcessorApplicationListener kích hoạt các post-processor trong pha xử lý sự kiện Environment đã được chuẩn bị, trước refresh**.

### Điều gì đã có khi post-processor chạy?

Thông thường có:

- Một **ConfigurableEnvironment** đang được chuẩn bị và các PropertySource đã được bổ sung theo giai đoạn hiện tại.
- **SpringApplication**.
- Các cơ chế bootstrap đặc biệt được Spring Boot hỗ trợ.
- Classpath, system properties, environment variables và những dữ liệu ban đầu khác.

Không nên mặc định có:

- ApplicationContext đã được refresh.
- Bean của ứng dụng như **@Service**, **@Repository**, DataSource hoặc WebClient.Builder.
- Dependency injection thông thường qua **@Autowired** trong EnvironmentPostProcessor.
- Các kết quả từ **@ConfigurationProperties** bean đã được bind sau khi container hoạt động.

Vì vậy code trong EnvironmentPostProcessor nên hoạt động độc lập với các business bean và không dựa vào việc khởi tạo bean để lấy cấu hình.

## 4. Quan hệ với ConfigDataEnvironmentPostProcessor

Một thành phần rất quan trọng của Spring Boot là **ConfigDataEnvironmentPostProcessor**. Đây cũng là một EnvironmentPostProcessor, phụ trách nạp và áp dụng **ConfigData**, bao gồm cấu hình trong **application.properties**, **application.yml**, các file theo profile và các nguồn import được Boot hỗ trợ.

Điều này có nghĩa:

- Không phải tất cả EnvironmentPostProcessor đều nhìn thấy cùng một tập property ở mọi thời điểm.
- Một processor chạy **trước ConfigDataEnvironmentPostProcessor** có thể chưa thấy giá trị từ file application.yml vừa định nạp.
- Một processor chạy **sau ConfigDataEnvironmentPostProcessor** có thể đọc các giá trị đã được cấu hình từ ConfigData.
- Nếu muốn ảnh hưởng đến cơ chế chọn **spring.config.location**, **spring.config.name** hoặc việc tải các config location theo profile, thứ tự thực thi là một phần của thiết kế; thêm property **sau khi ConfigData đã được xử lý** không tự khiến Boot nạp lại các file theo tên/vị trí vừa thay đổi.

Đây là lý do Spring Boot hỗ trợ **Ordered** và **@Order** cho EnvironmentPostProcessor.

~~~java
public final class DemoProcessor
        implements EnvironmentPostProcessor, Ordered {

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {
        // Logic tùy biến Environment.
    }
}
~~~

Đoạn trên là **khung minh họa**, chưa phải file chạy độc lập (cần package và imports). Với **Ordered.LOWEST_PRECEDENCE**, ví dụ được thiết kế để chạy muộn, sau ConfigDataEnvironmentPostProcessor theo thứ tự mặc định. Không nên hardcode số thứ tự nội bộ của Boot nếu không cần; khi muốn so sánh tương đối, tham khảo **ConfigDataEnvironmentPostProcessor.ORDER** trong phiên bản được dùng.

**Cẩn thận:** thứ tự gọi processor và thứ tự ưu tiên nguồn cấu hình là **hai trục khác nhau**. Một processor chạy cuối vẫn có thể thêm PropertySource ở đầu danh sách, khiến giá trị của nó thắng các nguồn khác. Đừng nhầm “chạy sau” với “property yếu hơn”.

## 5. Ví dụ đầy đủ Java 17+: thêm default properties khi chuẩn bị Environment

Mục tiêu của ví dụ:

1. Đăng ký một EnvironmentPostProcessor bằng cơ chế Spring Boot.
2. Thêm một PropertySource có giá trị mặc định.
3. Cho thấy **application.properties** ghi đè được default property.
4. Kiểm tra giá trị cuối cùng bằng ApplicationRunner khi Spring đã khởi chạy.

Ví dụ dành cho **Spring Boot 3.3.x và Java 17+**. Tạo dự án Maven bằng Spring Initializr, group **com.example**, artifact **demo**, package **com.example.demo**, dependency **Spring Boot Starter**. Không cần Spring Web vì đây là ứng dụng non-web.

### 5.1. File EnvironmentPostProcessor

Tạo **src/main/java/com/example/demo/bootstrap/LabEnvironmentPostProcessor.java**:

~~~java
package com.example.demo.bootstrap;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public final class LabEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    private static final String SOURCE_NAME = "labBootstrapDefaults";

    @Override
    public int getOrder() {
        // Chạy muộn, sau khi ConfigData thường đã được nạp.
        return Ordered.LOWEST_PRECEDENCE;
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        // Tránh thêm trùng tên PropertySource.
        if (environment.getPropertySources().contains(SOURCE_NAME)) {
            return;
        }

        Map<String, Object> defaults = Map.of(
                "demo.message", "hello-from-environment-post-processor",
                "demo.mode", "safe-default");

        // addLast: ưu tiên thấp; file config/CLI có thể ghi đè.
        environment.getPropertySources().addLast(
                new MapPropertySource(SOURCE_NAME, defaults));
    }
}
~~~

**Vì sao chọn MapPropertySource và addLast?**

**MapPropertySource** là một PropertySource giữ một map các key/value. **MutablePropertySources.addLast(...)** thêm nguồn này **ở vị trí ưu tiên thấp** so với những nguồn đã có. Đây là cách phù hợp khi post-processor chỉ cung cấp **fallback defaults**: người triển khai vẫn có thể đặt cấu hình trong application.properties, biến môi trường và tham số CLI.

Việc kiểm tra **contains(SOURCE_NAME)** làm ví dụ tránh thêm một nguồn có cùng tên nếu code được gọi lặp trong những tình huống kiểm thử/tích hợp. Logic vẫn không làm thay đổi bất kỳ business bean nào.

### 5.2. Đăng ký bằng spring.factories

Tạo file **src/main/resources/META-INF/spring.factories**:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=com.example.demo.bootstrap.LabEnvironmentPostProcessor
~~~

Đây là bước **bắt buộc** cho ví dụ với Spring Boot 3.3. Boot dùng cơ chế factories để tìm EnvironmentPostProcessor trong dependency/application classpath. Chỉ thêm **@Component** vào class hoặc chỉ để class trong package component scan **không đủ** cho callback chạy đúng pha Environment.

Đường dẫn và tên class phải khớp chính xác:

- **META-INF** là thư mục con trong **src/main/resources**.
- File phải có tên **spring.factories**.
- Key là tên đầy đủ của **EnvironmentPostProcessor** trong Spring Boot 3.3.
- Value là tên đầy đủ của class triển khai, kể cả package.

Khi build JAR bình thường, tài nguyên này phải nằm trên classpath. Nếu thư viện có nhiều processor, factories có thể liệt kê nhiều implementation theo cú pháp properties; thứ tự thực thi không nên phụ thuộc vào thứ tự liệt kê mà cần định nghĩa bằng Ordered hoặc @Order.

### 5.3. Ứng dụng đọc các giá trị sau startup

Tạo **src/main/java/com/example/demo/EnvironmentDemoApplication.java**:

~~~java
package com.example.demo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class EnvironmentDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(EnvironmentDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner printEnvironment(Environment environment) {
        return args -> {
            System.out.println("demo.message="
                    + environment.getProperty("demo.message"));
            System.out.println("demo.mode="
                    + environment.getProperty("demo.mode"));
        };
    }
}
~~~

**ApplicationRunner** thực thi sau khi context đã refresh, là nơi thuận tiện để **quan sát** cấu hình có hiệu lực. Trong khi đó **LabEnvironmentPostProcessor** được gọi sớm hơn, lúc Spring Boot chuẩn bị Environment.

### 5.4. File cấu hình ứng dụng

Tạo **src/main/resources/application.properties**:

~~~properties
demo.mode=from-application-properties
~~~

Không khai báo **demo.message** trong file này. Như vậy:

- **demo.message** chỉ xuất hiện trong default PropertySource của processor, nên đọc được giá trị fallback.
- **demo.mode** có mặt ở cả PropertySource của processor lẫn application.properties; file cấu hình có độ ưu tiên cao hơn nguồn addLast nên giá trị hiệu lực lấy từ file.

### 5.5. Chạy chương trình và kết quả

Từ thư mục gốc dự án Maven do Initializr sinh:

~~~bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell/cmd:
# .\mvnw.cmd spring-boot:run
~~~

Các dòng do ApplicationRunner tự in:

~~~text
demo.message=hello-from-environment-post-processor
demo.mode=from-application-properties
~~~

Đây là **hai dòng kết quả mong đợi của chương trình**, không phải toàn bộ stdout. Spring Boot và Maven có thể in log/banner khác. Kết quả giả định không có biến môi trường, JVM system property hoặc CLI argument khác ghi đè hai key này.

Nếu ứng dụng báo không có giá trị **demo.message**, kiểm tra trước hết file **META-INF/spring.factories** đã được đóng gói đúng, package/class name trong value chính xác và class processor có mặt trên runtime classpath.

### 5.6. Thử ghi đè bằng command-line argument

Nếu Initializr dùng artifact **demo**, version **0.0.1-SNAPSHOT**, build JAR:

~~~bash
./mvnw package
~~~

Và chạy:

~~~bash
java -jar target/demo-0.0.1-SNAPSHOT.jar --demo.message=from-command-line
~~~

Nếu artifact/version khác, thay đúng tên JAR ở thư mục target. Theo thứ tự ưu tiên mặc định của Spring Boot, command-line property thắng cả giá trị default được thêm bằng **addLast**. Những dòng chương trình in:

~~~text
demo.message=from-command-line
demo.mode=from-application-properties
~~~

Ba lần truy cập **demo.message** ở các pha khác nhau minh họa đúng nhiệm vụ: EnvironmentPostProcessor đặt nguồn giá trị sớm; Environment quyết định giá trị cuối cùng dựa trên thứ tự nguồn; bean dùng **Environment** sau refresh đọc được kết quả hiệu lực.

## 6. addFirst, addLast và thứ tự ưu tiên của PropertySource

Cùng một processor có thể tạo hành vi rất khác nhau chỉ bằng cách chọn vị trí:

~~~java
// Default, thường cho phép nguồn khác ghi đè:
environment.getPropertySources().addLast(
        new MapPropertySource("lowPriorityDefaults", defaults));

// Override mạnh (cần cân nhắc trước khi dùng):
environment.getPropertySources().addFirst(
        new MapPropertySource("highPriorityOverrides", overrides));
~~~

Đây là **đoạn minh họa**: giả định hai biến **defaults** và **overrides** đã là các map phù hợp.

- **addLast:** nguồn thêm vào đứng phía sau, có ưu tiên thấp hơn nguồn phía trước.
- **addFirst:** nguồn thêm vào đứng đầu, ưu tiên cao nhất tại thời điểm thêm; nó có thể ghi đè config file, system properties hoặc CLI arguments đang có trong danh sách.
- **addBefore(name, source)** và **addAfter(name, source)**: chèn tương đối với một nguồn cụ thể; cần biết chính xác tên nguồn đang tồn tại.
- **replace(name, source):** thay hẳn nguồn có tên đã biết; phải hiểu tác động lên những key đang được cung cấp.

**Không chọn addFirst theo phản xạ** chỉ để chắc chắn code “có tác dụng”. Việc này có thể làm người vận hành không còn điều chỉnh cấu hình được bằng biến môi trường hay CLI, hoặc vô tình thay thế giá trị cấu hình cần được kiểm soát.

### Trường hợp nhiều key trùng nhau

Giả sử đã có:

~~~text
application.properties       demo.mode=prod
systemEnvironment            DEMO_MODE=staging
labBootstrapDefaults         demo.mode=safe-default
~~~

Giá trị hiệu lực phụ thuộc vị trí PropertySource và cơ chế xử lý tên key của nguồn tương ứng. Với thứ tự thông thường và không có nguồn ưu tiên cao hơn, **systemEnvironment** có thể ghi đè config file, còn **labBootstrapDefaults** ở cuối chỉ đóng vai trò fallback. Ví dụ này minh họa nguyên tắc ưu tiên; không nên coi danh sách rút gọn trên là toàn bộ thứ tự các PropertySource trong mọi ứng dụng.

### Thứ tự xử lý của processor khác với precedence của property

Hai câu hỏi độc lập:

1. Processor nào **chạy trước**? Quyết định qua **Ordered/@Order**.
2. Sau khi tất cả processor chạy, PropertySource nào **thắng khi cùng key**? Quyết định bởi **vị trí** trong MutablePropertySources, cùng quy tắc tra cứu/relaxed binding phù hợp.

Một processor chạy sau ConfigData nhưng gọi **addFirst** có thể ghi đè cả giá trị từ ConfigData. Một processor chạy trước ConfigData nhưng thêm nguồn fallback có thể bị ConfigData ghi đè sau đó. Hãy thiết kế cả hai trục rõ ràng.

## 7. Tại sao cần chạy trước refresh thay vì dùng @Bean?

Một số điểm mở rộng có thời điểm và mục tiêu rất khác:

| Cơ chế | Mốc hoạt động | Đối tượng chính được thay đổi |
| --- | --- | --- |
| **EnvironmentPostProcessor** | Pha chuẩn bị Environment, trước refresh | PropertySources, profile và dữ liệu cấu hình sớm |
| **ApplicationContextInitializer** | Sau khi context được tạo nhưng trước refresh | ApplicationContext chưa refresh, môi trường và cấu trúc ban đầu |
| **BeanDefinitionRegistryPostProcessor** | Trong pha refresh, trước khởi tạo bean ứng dụng | Registry/BeanDefinition |
| **BeanFactoryPostProcessor** | Trong refresh, trước singleton application initialization | BeanFactory và metadata bean |
| **BeanPostProcessor** | Khi mỗi bean được khởi tạo | Bean instance, wrapper/proxy và lifecycle |
| **@Bean / @Component** | Định nghĩa được xử lý trong context startup; instance theo scope/lazy | Thành phần ứng dụng |
| **ApplicationRunner** | Sau khi context refresh thành công | Tác vụ sau startup; quan sát/khởi tạo nghiệp vụ tùy nhu cầu |

Ví dụ: nếu thiết lập **logging.\*** hoặc **spring.main.\*** cần được Spring Boot đọc trước khi context refresh, việc thêm PropertySource qua **@PropertySource** trên **@Configuration** có thể quá muộn. Spring Boot Reference nêu rõ các PropertySource từ @PropertySource chỉ được thêm trong pha refresh, khi một số thuộc tính sớm đã được đọc.

EnvironmentPostProcessor tồn tại để can thiệp vào Environment ở mốc sớm hơn. Dù vậy không nên giả định nó có thể thay đổi **mọi thiết lập từ giây đầu tiên**; những giá trị mà Boot hoặc listener khác đã tiêu thụ trước callback của processor không thể được “quay ngược” tự động.

**ApplicationContextInitializer** khác EnvironmentPostProcessor ở chỗ initializer đã có tham chiếu context để cấu hình, nhưng vẫn chưa refresh. Nếu nhu cầu là thay đổi cấu trúc context thay vì chỉ PropertySources, initializer có thể phù hợp hơn.

## 8. Cơ chế đăng ký và khởi tạo processor

Ở Spring Boot 3.3, **EnvironmentPostProcessorApplicationListener** là listener chịu trách nhiệm kích hoạt các EnvironmentPostProcessor được đăng ký qua **spring.factories**. Điều này giải thích tại sao interface có tên “PostProcessor” nhưng cách kích hoạt **khác** cơ chế phát hiện bean sau component scan.

### Không dùng constructor injection kiểu bean thông thường

Processor được Boot tạo trong giai đoạn bootstrap. Vì Spring ApplicationContext chưa sẵn sàng, không nên viết constructor yêu cầu **@Service** hoặc **@Repository**.

Spring Boot 2.4+ hỗ trợ những tham số constructor đặc biệt cho EnvironmentPostProcessor, trong đó có:

- **DeferredLogFactory:** tạo logger có thể trì hoãn log cho đến khi cấu hình logging được chuẩn bị đầy đủ.
- **ConfigurableBootstrapContext** (và một số kiểu bootstrap context liên quan): chia sẻ các đối tượng bootstrap giữa những bước khởi chạy mà không cần ApplicationContext đã refresh.

Ví dụ minh họa constructor chuyên biệt:

~~~java
public SampleProcessor(DeferredLogFactory logFactory) {
    this.log = logFactory.getLog(getClass());
}
~~~

Đây là **mảnh code minh họa** cho processor có field **log** và imports tương ứng, không phải một class hoàn chỉnh. Dùng logger defer hữu ích vì logging system có thể chưa áp dụng đầy đủ các cấu hình log lúc callback chạy. Không nên dùng **System.out** để in secret hoặc dữ liệu nhạy cảm chỉ vì đang chạy ở pha sớm.

### Sai vị trí spring.factories

Nếu file đặt tại **src/main/java/META-INF** hoặc chỉ có trong thư mục test, runtime JAR có thể không chứa nó. Thư mục đúng khi dùng layout Maven tiêu chuẩn là **src/main/resources/META-INF**. Một class implement interface mà không được đăng ký vào factories sẽ không tự được gọi chỉ vì compile thành công.

## 9. Quan hệ với profile và config loading

Active profiles ảnh hưởng tới các file cấu hình như **application-dev.properties** và những bean được điều kiện hóa theo profile. Vì ConfigDataEnvironmentPostProcessor xử lý ConfigData trong pha Environment, cần phân biệt hai nhu cầu:

**A. Muốn đọc cấu hình đã được nạp rồi mới thêm default/chuẩn hóa một nhóm key.** Chạy processor **sau ConfigData** thường hợp lý; ví dụ dùng **Ordered.LOWEST_PRECEDENCE**.

**B. Muốn thay đổi các lựa chọn quyết định file cấu hình được nạp hoặc profile nào được xét trong quá trình ConfigData.** Phải thiết kế thành phần can thiệp **đủ sớm**, đúng thứ tự so với ConfigData. Chỉ thêm **spring.profiles.active** hoặc **spring.config.location** sau khi ConfigData đã chạy thường **không làm Boot nạp lại** các config file theo lựa chọn mới. Với cấu hình chọn file/profile, ưu tiên những nguồn được Boot hỗ trợ sớm như CLI, environment variable hoặc system property; nếu nhu cầu là custom config location resolver, hãy cân nhắc extension point ConfigData phù hợp thay vì thao tác muộn ở post-processor.

Một processor có thể đọc:

~~~java
String[] activeProfiles = environment.getActiveProfiles();
String value = environment.getProperty("demo.mode");
~~~

Nhưng dữ liệu quan sát phụ thuộc **thời điểm** processor chạy trong chuỗi. Trước ConfigData, nhiều giá trị profile-specific chưa được nạp; sau ConfigData, giá trị thường đã hiện diện nhưng việc bổ sung profile có thể quá muộn để tác động vào lần nạp đã hoàn tất.

## 10. Khi nào nên dùng EnvironmentPostProcessor?

**Nên cân nhắc khi:**

- Xây dựng thư viện hoặc starter phải thêm một nguồn cấu hình **trước khi bean application được tạo**.
- Cần bổ sung một nhóm fallback properties có độ ưu tiên được định nghĩa rõ.
- Cần xử lý hoặc chuyển đổi giá trị bootstrap sớm trên Environment.
- Cần tích hợp cơ chế nạp cấu hình có tính chất bootstrap mà file application.yml thông thường không đủ diễn đạt.

**Thường không cần khi:**

- Chỉ muốn khai báo **server.port**, URL datasource, timeout hoặc profile; dùng application.properties/yml hay biến môi trường sẽ đơn giản hơn.
- Muốn map một nhóm cấu hình kiểu dữ liệu vào bean; **@ConfigurationProperties** phù hợp hơn.
- Muốn chạy logic sau khi startup hoàn thành; dùng **ApplicationRunner**, **CommandLineRunner** hoặc các lifecycle event thích hợp.
- Muốn sửa định nghĩa hoặc quá trình khởi tạo bean; xem **BeanDefinitionRegistryPostProcessor**, **BeanFactoryPostProcessor** hoặc **BeanPostProcessor**.
- Muốn tự động tải lại config khi file thay đổi trong lúc ứng dụng chạy; EPP **không phải file watcher**, không mặc nhiên chạy lại sau startup.

Tránh thực hiện thao tác mạng chậm, blocking không kiểm soát hoặc side effect khó đảo ngược trong processor: callback nằm trên đường khởi động quan trọng của ứng dụng. Nếu phải đọc nguồn ngoài, cần có timeout, chính sách lỗi và hiểu rõ bảo mật của thông tin cấu hình.

## 11. Những lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Processor không được gọi | Thiếu hoặc sai **META-INF/spring.factories** | Kiểm tra path trong resources, key và fully qualified class |
| Dùng **@Component** nhưng callback không chạy sớm | Component scan chưa phải cơ chế đăng ký EPP | Đăng ký đúng factories |
| Trong processor lấy **@Autowired MyService** nhưng thiếu bean | ApplicationContext chưa refresh | Không phụ thuộc vào business beans ở pha sớm |
| Không đọc thấy property từ application.yml | Processor chạy trước ConfigData | Xem thứ tự Ordered và bản Boot đang dùng |
| Thêm **spring.config.location** nhưng file không nạp lại | Đã qua pha ConfigData | Cấu hình lựa chọn file từ nguồn đủ sớm |
| File cấu hình không ghi đè được default | Processor đã gọi **addFirst** hoặc chèn nguồn quá cao | Chọn **addLast** cho fallback defaults |
| Giá trị lấy ra khác dự tính | Nhiều PropertySource cùng key | Kiểm tra thứ tự, nguồn CLI/system/env và key binding |
| Processor chạy trong test nhưng production không chạy | Class hoặc spring.factories chỉ có ở test classpath | Đọc cấu trúc JAR và vị trí resources |
| Startup quá chậm | Processor làm I/O/mạng tốn thời gian | Đặt timeout, giảm I/O hoặc chuyển việc khỏi startup |
| Log trong processor không theo mức log cấu hình | Logging chưa được chuẩn bị đầy đủ | Xem DeferredLogFactory và thứ tự startup |
| Thêm property rồi mong bean hiện tại tự nhận giá trị mới | Nhiều bean/config đã bind khi startup | Thiết kế cơ chế refresh động riêng hoặc restart |

Để chẩn đoán, Spring Boot Actuator (khi được cài đặt và bảo vệ thích hợp) có thể cung cấp endpoint **env** và **configprops**. Chúng có thể giúp xác định nguồn cấu hình và giá trị bind nhưng cần tránh làm lộ secret. Không bật công khai những endpoint nhạy cảm chỉ để debug.

## 12. Bài tập kiểm tra hiểu biết

**Câu 1.** Một class implements EnvironmentPostProcessor được đánh dấu **@Component** nhưng không khai báo trong spring.factories. Trong Boot 3.3 có nên kỳ vọng nó tự chạy ở pha chuẩn bị Environment không?

**Câu 2.** Với processor dùng **addLast** để đưa **demo.mode=safe-default**, còn application.properties có **demo.mode=from-file**, sau startup Environment trả giá trị nào?

**Câu 3.** Vì sao dùng **Ordered.LOWEST_PRECEDENCE** hữu ích khi processor muốn đọc những property đã được ConfigData nạp?

**Câu 4.** Giả sử processor chạy sau ConfigData rồi mới đặt **spring.config.location**. Có thể khẳng định Boot sẽ nạp lại những file theo location mới không?

**Câu 5.** Tại sao **@PropertySource** trong configuration class có thể quá muộn nếu nhu cầu là tác động đến một số giá trị logging hoặc spring.main.*?

**Câu 6.** Muốn thêm giá trị mặc định nhưng cho phép tham số dòng lệnh ghi đè, nên dùng **addFirst** hay **addLast**? Việc thay đổi thứ tự processor có đồng nghĩa thay đổi property precedence không?

**Đáp án gợi ý:** (1) không, phải đăng ký đúng mechanism của EPP; (2) from-file vì nguồn file ưu tiên hơn nguồn fallback; (3) ConfigData processor có cơ hội chạy trước; (4) không, phải có quyết định trước giai đoạn nạp file; (5) vì @PropertySource chỉ được đưa vào khi context refresh, sau khi một số giá trị sớm được đọc; (6) addLast, còn execution order và PropertySource precedence là hai cơ chế khác nhau.

## 13. Ghi nhớ

- **EnvironmentPostProcessor** là hook của Spring Boot để chỉnh **ConfigurableEnvironment trước ApplicationContext.refresh()**.
- **EnvironmentPostProcessorApplicationListener** kích hoạt những implementation đăng ký qua **META-INF/spring.factories** trong luồng bootstrap của Boot 3.3.
- **ConfigDataEnvironmentPostProcessor** cũng là EPP. Nếu muốn quan sát file application.properties/yml đã được nạp, cần hiểu thứ tự chạy; nếu muốn quyết định config location hay profile sớm, không thể tùy tiện chạy sau ConfigData.
- **Ordered/@Order** quyết định **processor chạy lúc nào**; **addFirst/addLast** quyết định **nguồn property đứng ở đâu**. Hai điều này độc lập.
- **EPP không phải một Spring bean thông thường**, không dùng để inject business services, chạy logic nghiệp vụ hay tự refresh cấu hình động.
- Với bài toán mặc định đơn giản, dùng **addLast** giúp giữ quyền ghi đè của file cấu hình, biến môi trường và CLI.

### Tài liệu chính thức (Spring Boot 3.3)

1. EnvironmentPostProcessor JavaDoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html
2. EnvironmentPostProcessorApplicationListener JavaDoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessorApplicationListener.html
3. ConfigDataEnvironmentPostProcessor JavaDoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataEnvironmentPostProcessor.html
4. Externalized Configuration, thứ tự PropertySource và @PropertySource: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
5. SpringApplication và startup lifecycle: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html

Các ví dụ Java trong bài được viết cho **Java 17+ / Spring Boot 3.3.x**. Với Spring Boot 4.x và các major phiên bản khác, hãy đối chiếu lại JavaDoc và cơ chế đăng ký extension của phiên bản đó trước khi tái sử dụng nguyên mã nguồn.