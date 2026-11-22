# Environment, PropertySource và thời điểm thuộc tính sẵn sàng cho điều kiện trong Spring Boot

## 1. Vấn đề cần hiểu

Auto-configuration không đưa ra quyết định trong khoảng trống. Các điều kiện như `@ConditionalOnProperty` tra cứu giá trị thuộc tính từ `Environment` ở **thời điểm điều kiện được đánh giá**. Muốn dự đoán bean nào sẽ được đăng ký, cần trả lời ba câu hỏi riêng biệt:

1. **Thuộc tính đến từ đâu?** Tệp `application.properties`/`application.yaml`, profile, biến môi trường hệ điều hành, JVM system property, tham số `--key=value`, nguồn tùy biến… đều có thể cung cấp giá trị.
2. **Nguồn nào được ưu tiên khi trùng khóa?** `Environment` đi qua các `PropertySource` theo thứ tự ưu tiên và lấy giá trị phù hợp đầu tiên; không cộng dồn hai giá trị cùng khóa thành một giá trị.
3. **Nguồn đã được thêm vào trước lúc xét điều kiện chưa?** Giá trị nhìn thấy trong `ApplicationRunner` sau khi ứng dụng khởi động chưa chắc là giá trị đã hiện diện khi một điều kiện chạy trước đó.

Ví dụ: một tính năng chỉ nên tạo bean khi `feature.mail.enabled=true`. Nếu khóa này có trong file cấu hình nhưng bị ghi đè bằng command-line thành `false`, bean thường không được đăng ký. Nếu một đoạn mã chỉ đưa khóa vào `Environment` sau khi điều kiện đã được đánh giá, việc thêm khóa đó không làm Spring tự đánh giá và đăng ký lại bean.

Mục tiêu của bài là hiểu chính xác các khái niệm, thứ tự ưu tiên, các mốc vòng đời và cách kiểm chứng bằng một ứng dụng Java 17+.

## 2. Environment là gì?

`org.springframework.core.env.Environment` là abstraction của Spring Framework để biểu diễn **properties** và **profiles** đang áp dụng cho ứng dụng.

Các API tiêu biểu:

| API | Ý nghĩa |
| --- | --- |
| `environment.getProperty("demo.message")` | Đọc giá trị chuỗi hoặc `null` nếu không tìm thấy. |
| `environment.getProperty("demo.port", Integer.class)` | Tra cứu rồi chuyển đổi kiểu, có thể báo lỗi nếu dữ liệu không chuyển được. |
| `environment.getProperty("demo.message", "fallback")` | Dùng giá trị dự phòng khi không tìm thấy thuộc tính. |
| `environment.containsProperty("demo.message")` | Kiểm tra xem thuộc tính có giá trị tra cứu được không. |
| `environment.getActiveProfiles()` | Lấy các profile hiện đang active. |
| `configurableEnvironment.getPropertySources()` | Xem hoặc quản lý chuỗi nguồn thuộc tính khi dùng `ConfigurableEnvironment`. |

`Environment` là **điểm tra cứu**; nó không nhất thiết giữ mọi giá trị trong một `Map` duy nhất. Một ứng dụng có thể có nhiều nguồn cùng mang khóa `demo.message`. Thứ tự các nguồn quyết định giá trị quan sát được.

`ConfigurableEnvironment` mở rộng khả năng đọc bằng cách cho phép cấu hình profiles và `MutablePropertySources`. Đối tượng này đặc biệt hữu ích ở các giai đoạn khởi tạo ứng dụng, chẳng hạn khi viết `EnvironmentPostProcessor`.

Phân biệt với một số khái niệm gần tên:

- **Environment**: giao diện truy vấn properties và profiles.
- **PropertySource**: một nguồn key-value cụ thể, chẳng hạn biến môi trường, system properties, một file được nạp hay một map tự tạo.
- **PropertySources**: tập các nguồn thuộc tính có **thứ tự**, được sử dụng để phân giải khóa.
- **ConfigData** của Spring Boot: cơ chế xử lý cấu hình ngoài như `application.properties`, YAML, profile-specific files và `spring.config.import` trong giai đoạn chuẩn bị môi trường.
- **`@ConfigurationProperties`**: bind các thuộc tính đã có vào một đối tượng cấu hình có cấu trúc; việc bind này không đồng nghĩa với lúc các giá trị lần đầu được đưa vào `Environment`.
- **`@ConditionalOnProperty`**: quyết định có đưa cấu hình/bean definition vào context hay không dựa trên property tra cứu được khi xét điều kiện.

## 3. PropertySource hoạt động thế nào?

Một `PropertySource<T>` có tên và biết cách lấy một giá trị theo khóa từ đối tượng nguồn `T`. Ví dụ `MapPropertySource` lấy giá trị từ một `Map`. `SystemEnvironmentPropertySource` hỗ trợ các quy tắc tra cứu phù hợp với biến môi trường hệ điều hành.

Có thể tưởng tượng `Environment` như chuỗi tìm kiếm:

~~~text
getProperty("demo.message")
    |
    v
PropertySource ưu tiên cao nhất  ---> có giá trị? ---> trả về
    |
    | không có
    v
PropertySource ưu tiên kế tiếp ---> có giá trị? ---> trả về
    |
    | không có
    v
...
    |
    +-- không nguồn nào có giá trị ---> null / defaultValue
~~~

Điểm mấu chốt: khi cùng một khóa xuất hiện ở nhiều nguồn, **nguồn có độ ưu tiên cao nhất mà phân giải được khóa sẽ thắng**. Thêm một nguồn bằng `addFirst(...)` đặt nguồn đó lên đầu danh sách; `addLast(...)` đặt nó ở cuối. `addBefore(...)` và `addAfter(...)` cho phép sắp xếp tương đối với một nguồn đã biết. Phải phân biệt **thứ tự ưu tiên khi tra cứu** với **thời gian nguồn được nạp**: một nguồn được thêm sau vẫn có thể được xếp ở cuối, tức ưu tiên thấp.

Ví dụ minh họa bằng Spring Framework, không cần chạy ứng dụng Boot:

~~~java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

public class PropertySourceOrderDemo {
    public static void main(String[] args) {
        StandardEnvironment env = new StandardEnvironment();

        env.getPropertySources().addLast(
                new MapPropertySource("low", Map.of("demo.answer", "LOW"))
        );
        env.getPropertySources().addFirst(
                new MapPropertySource("high", Map.of("demo.answer", "HIGH"))
        );

        System.out.println(env.getProperty("demo.answer"));

        env.getPropertySources().remove("high");
        System.out.println(env.getProperty("demo.answer"));
    }
}
~~~

Với `spring-core` và các dependency của Spring Framework có sẵn trên classpath, lớp trên in:

~~~text
HIGH
LOW
~~~

Lưu ý: đoạn này minh họa **API và độ ưu tiên**. Đây không phải một tệp Java độc lập biên dịch chỉ với JDK, vì `StandardEnvironment` và `MapPropertySource` thuộc thư viện Spring. Ví dụ Maven đầy đủ ở phần 7 có thể chạy thành ứng dụng Spring Boot thực tế.

### Nguồn dữ liệu và thứ tự ưu tiên trong Spring Boot

Spring Boot có quy tắc riêng, được công bố trong tài liệu **Externalized Configuration**. Trong một ứng dụng Boot thông thường, có thể nhớ những điểm thực dụng sau:

- Tham số command-line dạng `--demo.message=CLI` thường **ưu tiên hơn** JVM `-Ddemo.message=JVM`, biến môi trường và file cấu hình, nếu ứng dụng không tắt command-line properties.
- JVM system properties thông thường **ưu tiên hơn** biến môi trường hệ điều hành; cả hai thường ưu tiên hơn config data từ `application.properties`.
- Config data từ file thường **ưu tiên hơn** `@PropertySource` trên lớp `@Configuration`; `SpringApplication.setDefaultProperties` cung cấp mức dự phòng thấp.
- Các nguồn khác như `SPRING_APPLICATION_JSON`, servlet/JNDI, test annotations, devtools và nguồn tùy biến có thứ tự riêng. Không nên xem danh sách rút gọn trên là toàn bộ thứ tự tuyệt đối cho mọi phiên bản và loại ứng dụng.

Trong danh sách thứ tự *tăng dần độ ưu tiên* mà tài liệu Boot công bố, **nguồn xuất hiện sau có thể ghi đè nguồn xuất hiện trước**. Còn khi duyệt `MutablePropertySources` trong mã, **nguồn đứng trước trong danh sách là nguồn được tra cứu trước**. Hai cách mô tả không mâu thuẫn; chúng nhìn từ hai hướng khác nhau.

Ví dụ với cùng khóa `demo.message`:

| Nguồn | Giá trị |
| --- | --- |
| `application.properties` | `FILE` |
| Biến môi trường `DEMO_MESSAGE` | `ENV` |
| Tham số JVM `-Ddemo.message=JVM` | `JVM` |
| Tham số ứng dụng `--demo.message=CLI` | `CLI` |

Khi tất cả nguồn trên hiện diện theo cấu hình Boot mặc định, giá trị tra cứu thường là `CLI`. Bỏ tham số `--demo.message` thì `JVM` thắng; bỏ cả `-D` thì biến môi trường có thể thắng; bỏ tiếp biến môi trường thì nhận `FILE`. Đây là ví dụ về **override**, không phải bốn bean hay bốn bản cấu hình được tạo cùng lúc.

### Profiles, file và import

Spring Boot hỗ trợ `application-{profile}.properties`, `application-{profile}.yaml` và `spring.config.import`. Việc file nào được nạp còn phụ thuộc active profiles, vị trí file, thứ tự config data và nhóm vị trí. Chẳng hạn `application-dev.properties` chỉ có tác dụng khi profile `dev` được kích hoạt hoặc có cơ chế import tương ứng.

Khi cần chẩn đoán giá trị cuối, đừng chỉ nhìn `src/main/resources/application.properties`. Hãy kiểm tra profile đang hoạt động, file bên ngoài JAR, file import và các giá trị khởi động. Các giá trị có thể thay đổi giữa IDE, test, lệnh chạy local và container.

## 4. Thời điểm thuộc tính sẵn sàng trong vòng đời khởi động

“Có trong file” không đồng nghĩa với “đã xuất hiện trong `Environment` ngay từ đầu”. Sơ đồ dưới đây là các **mốc khái quát**; chi tiết về các callback có thể thay đổi giữa phiên bản Boot:

~~~text
SpringApplication.run(...)
    |
    v
Tạo / chuẩn bị Environment
- đọc tham số ứng dụng, system properties, biến môi trường
- xử lý config data: application.*, profiles, spring.config.import
- chạy EnvironmentPostProcessor theo thứ tự được cấu hình
    |
    v
Tạo ApplicationContext và chuẩn bị context
    |
    v
Refresh context: phân tích @Configuration,
đăng ký bean definitions, xử lý auto-configuration
và đánh giá @ConditionalOnProperty / các @Conditional
    |
    v
Khởi tạo những singleton bean cần thiết,
bind @ConfigurationProperties, inject dependencies
    |
    v
ApplicationRunner / CommandLineRunner
    |
    v
Ứng dụng sẵn sàng phục vụ
~~~

Thời điểm quan trọng:

**Trước khi refresh context:** các nguồn cấu hình do Boot chuẩn bị qua ConfigData và `EnvironmentPostProcessor` đã có thể hiện diện cho việc tra cứu trong quá trình xử lý configuration classes/auto-configuration. Nếu cần bổ sung nguồn cho các quyết định rất sớm, thường dùng ConfigData hoặc cơ chế chuẩn bị `Environment`.

**Khi refresh / phân tích cấu hình:** `@ConditionalOnProperty` thường được đánh giá để quyết định có đăng ký cấu hình hoặc `@Bean`. Nó dùng giá trị `Environment` **ở thời điểm đánh giá**, với thứ tự ưu tiên hiện tại. Một điều kiện trên lớp và một điều kiện trên phương thức có thể được xử lý ở các bước khác nhau trong quá trình phân tích/đăng ký bean definition.

**Sau khi bean đã được đăng ký và khởi tạo:** `@Value` hay `@ConfigurationProperties` có thể đọc/bind properties trong quá trình tạo bean. Đây không phải bằng chứng rằng chúng đã tồn tại ở một thời điểm trước đó. Nếu bạn thay `Environment` trong `ApplicationRunner`, `Environment.getProperty(...)` có thể đọc giá trị mới, nhưng Spring Boot **không tự tính lại toàn bộ các điều kiện đã được xét**, không tự tháo hoặc thêm bean theo giá trị mới.

Ví dụ: `@ConditionalOnProperty(name = "demo.enabled", havingValue = "true")` đã loại một bean vì giá trị là `false`. Sau đó thêm `demo.enabled=true` từ `ApplicationRunner` không làm bean xuất hiện trong cùng một context. Muốn thay đổi cấu trúc bean theo điều kiện khởi động, thông thường phải cấu hình đúng **trước khi** refresh và khởi động một context mới.

### Vì sao @PropertySource cần được dùng đúng lúc?

`@PropertySource("classpath:extra.properties")` được Spring Framework xử lý khi lớp `@Configuration` được phân tích trong quá trình **refresh context**. Spring Boot lưu ý rằng thời điểm này **quá muộn** cho một số thuộc tính đã được dùng trước khi refresh bắt đầu, như `logging.*` và `spring.main.*`.

Không nên suy rộng thành “`@PropertySource` luôn vô dụng cho mọi điều kiện”: điều kiện nào được đánh giá khi nào, lớp cấu hình được phân tích theo thứ tự nào và nguồn đã được thêm hay chưa mới quyết định nó có kịp hay không. Tuy vậy, nếu một auto-configuration cần một giá trị đáng tin cậy **từ giai đoạn chuẩn bị môi trường**, hãy đưa giá trị qua ConfigData hoặc `EnvironmentPostProcessor`, thay vì phụ thuộc vào thứ tự tình cờ của các lớp `@Configuration`.

`@PropertySource` mặc định phù hợp với file Java `.properties`. Đừng giả định `@PropertySource("classpath:extra.yaml")` tự có hỗ trợ YAML giống cơ chế ConfigData của Boot; muốn nạp YAML bằng annotation này cần `PropertySourceFactory` thích hợp hoặc chọn cơ chế chuẩn của Boot.

### EnvironmentPostProcessor và thứ tự chạy

`EnvironmentPostProcessor` là điểm mở rộng của Spring Boot để chỉnh `ConfigurableEnvironment` **trước khi refresh**. Một implementation được đăng ký trong `META-INF/spring.factories`; có thể dùng `Ordered` hoặc `@Order` để điều khiển trình tự. Boot cũng sử dụng một `ConfigDataEnvironmentPostProcessor` để xử lý config data. Một processor tùy chỉnh cần cân nhắc thứ tự tương đối với processor này nếu phụ thuộc vào các thuộc tính trong file cấu hình.

Trong ví dụ ở phần tiếp theo, processor tùy chỉnh chọn `Ordered.LOWEST_PRECEDENCE` và thêm `MapPropertySource` bằng `addLast`. Điều đó nhằm làm nguồn dự phòng: property từ command-line hay file được nạp theo cấu hình Boot sẽ có thể ghi đè nó. Với chương trình đơn giản này, processor tạo ra default trước khi điều kiện được đánh giá, nên điều kiện có thể sử dụng nó.

## 5. @ConditionalOnProperty đọc Environment như thế nào?

Ví dụ:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "demo",
        name = "feature-enabled",
        havingValue = "true",
        matchIfMissing = false
)
FeatureService featureService() {
    return () -> "ENABLED";
}
~~~

Đây là **đoạn minh họa bên trong một lớp `@Configuration` / `@SpringBootApplication`**, không phải chương trình độc lập. Điều kiện kiểm tra khóa `demo.feature-enabled` trong `Environment`.

Các trường hợp:

| `demo.feature-enabled` được phân giải thành | Kết quả với `havingValue="true", matchIfMissing=false` |
| --- | --- |
| `true` | Điều kiện khớp. |
| `false` | Không khớp. |
| Khóa vắng mặt | Không khớp. |
| Một chuỗi khác như `other` | Không khớp. |

Nếu bỏ `havingValue`, quy tắc mặc định của `@ConditionalOnProperty` rộng hơn: property phải có mặt và giá trị **không bằng `false`** theo logic của annotation. Nếu bật `matchIfMissing=true`, điều kiện có thể khớp ngay khi khóa vắng mặt. Vì vậy, đừng lẫn lộn “khóa tồn tại” với “giá trị boolean đúng”, và hãy viết `havingValue` rõ ràng khi muốn ràng buộc cụ thể.

`@ConditionalOnProperty` kiểm tra các thuộc tính trên `Environment`; nó không đọc trực tiếp một file xác định. Thứ tự nguồn và thời điểm đã nạp nguồn quyết định kết quả. Tình trạng bean được đăng ký còn tùy các điều kiện khác cùng áp dụng (classpath, bean hiện diện, môi trường web, v.v.).

Với những cấu trúc như `demo.targets[0]` hoặc collection, không nên mặc định `@ConditionalOnProperty` sẽ kiểm tra đầy đủ sự tồn tại của phần tử lồng nhau. Tài liệu Boot khuyến nghị dùng điều kiện tùy biến nếu kiểm tra collection phức tạp.

## 6. Ví dụ đầy đủ: nguồn dự phòng, file, command-line và điều kiện

Dự án Maven dưới đây dùng **Java 17 và Spring Boot 3.5.0**, đủ để quan sát ba điều:
- Một `EnvironmentPostProcessor` đưa thuộc tính dự phòng vào `Environment` trước khi các bean điều kiện được xét.
- `application.properties` có thể ghi đè một thuộc tính trong nguồn dự phòng.
- Command-line có thể ghi đè cả file lẫn nguồn dự phòng, từ đó thay đổi việc đăng ký bean.

Cấu trúc:

~~~text
environment-condition-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/demo/
    │   ├── DemoApplication.java
    │   ├── FeatureService.java
    │   └── EarlyDefaultsPostProcessor.java
    └── resources/
        ├── application.properties
        └── META-INF/spring.factories
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>environment-condition-demo</artifactId>
    <version>1.0.0</version>
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

### FeatureService.java

Tệp `src/main/java/com/example/demo/FeatureService.java`:

~~~java
package com.example.demo;

public interface FeatureService {
    String message();
}
~~~

### EarlyDefaultsPostProcessor.java

Tệp `src/main/java/com/example/demo/EarlyDefaultsPostProcessor.java`:

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public final class EarlyDefaultsPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        MapPropertySource defaults = new MapPropertySource(
                "demoFallback",
                Map.of(
                        "demo.feature-enabled", "true",
                        "demo.message", "FALLBACK_MESSAGE"
                )
        );

        environment.getPropertySources().addLast(defaults);
    }
}
~~~

Lớp này **không phải Spring bean** và không cần `@Component`; nó được Spring Boot gọi như một extension ở giai đoạn chuẩn bị `Environment`. Tên nguồn `demoFallback` có thể thấy khi duyệt `getPropertySources()`. `addLast` cho phép các nguồn ưu tiên cao hơn lấn át giá trị dự phòng.

### META-INF/spring.factories

Nội dung chính xác của `src/main/resources/META-INF/spring.factories`:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.demo.EarlyDefaultsPostProcessor
~~~

Đường dẫn và key rất quan trọng: nếu đăng ký sai, processor không chạy và `demo.feature-enabled` có thể vắng mặt. Ví dụ này dùng API và đường dẫn đăng ký của **Spring Boot 3.5.x**. Không đổi tùy tiện sang tên package hoặc cơ chế đăng ký của phiên bản Boot khác.

### application.properties

Nội dung `src/main/resources/application.properties`:

~~~properties
spring.main.banner-mode=off
logging.level.root=ERROR
demo.message=FILE_MESSAGE
~~~

Ta **không** khai báo `demo.feature-enabled` trong file. Nếu không có nguồn ưu tiên cao hơn, processor sẽ cung cấp `true` cho khóa này. Đồng thời, `demo.message=FILE_MESSAGE` ở config data sẽ ưu tiên hơn `FALLBACK_MESSAGE` trong `demoFallback`.

### DemoApplication.java

Tệp `src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "feature-enabled",
            havingValue = "true"
    )
    FeatureService featureService(Environment environment) {
        return () -> environment.getProperty(
                "demo.message", "MISSING_MESSAGE");
    }

    @Bean
    ApplicationRunner showResult(
            Environment environment,
            ObjectProvider<FeatureService> serviceProvider) {

        return args -> {
            FeatureService service = serviceProvider.getIfAvailable();

            System.out.println("enabled="
                    + environment.getProperty("demo.feature-enabled"));
            System.out.println("message="
                    + environment.getProperty("demo.message"));
            System.out.println("service="
                    + (service == null ? "ABSENT" : service.message()));
        };
    }
}
~~~

`@ConditionalOnProperty` quyết định đăng ký `FeatureService` từ property có sẵn khi xử lý cấu hình. `ApplicationRunner` chạy sau khi context đã khởi tạo, chỉ quan sát trạng thái cuối. `ObjectProvider` tránh lỗi tiêm bắt buộc khi bean không tồn tại.

### Chạy và đối chiếu

Cần cài JDK 17+ và Maven. Từ thư mục `environment-condition-demo`:

~~~bash
mvn -q -DskipTests package
java -jar target/environment-condition-demo-1.0.0.jar
~~~

Bỏ qua những dòng log môi trường (nếu có). Ba dòng do chương trình in ra:

~~~text
enabled=true
message=FILE_MESSAGE
service=FILE_MESSAGE
~~~

Giải thích: `demo.feature-enabled` đến từ `demoFallback`; `demo.message` đến từ file. Điều kiện khớp và `FeatureService` được đăng ký.

Ghi đè qua command-line:

~~~bash
java -jar target/environment-condition-demo-1.0.0.jar --demo.feature-enabled=false --demo.message=CLI_MESSAGE
~~~

Ba dòng của chương trình:

~~~text
enabled=false
message=CLI_MESSAGE
service=ABSENT
~~~

Giải thích: nguồn command-line được tra cứu trước file và map dự phòng. `@ConditionalOnProperty(havingValue="true")` không khớp, nên `FeatureService` không được đăng ký; runner vẫn chạy nhờ `ObjectProvider`.

Ghi đè chỉ bằng JVM system property:

~~~bash
java -Ddemo.feature-enabled=false -jar target/environment-condition-demo-1.0.0.jar
~~~

Ba dòng của chương trình:

~~~text
enabled=false
message=FILE_MESSAGE
service=ABSENT
~~~

Giải thích: `-Ddemo.feature-enabled=false` ưu tiên hơn giá trị trong map dự phòng. Giá trị `demo.message` vẫn lấy từ file vì ví dụ không khai báo một nguồn ưu tiên cao hơn cho khóa này.

Có thể thử tiếp:

~~~bash
java -jar target/environment-condition-demo-1.0.0.jar --demo.feature-enabled=true --demo.message=CLI_MESSAGE
~~~

Kết quả ba dòng:

~~~text
enabled=true
message=CLI_MESSAGE
service=CLI_MESSAGE
~~~

Bốn tình huống minh họa rằng điều kiện đọc **giá trị đã phân giải từ Environment**, không gắn cố định vào file hay vào giá trị trong `EnvironmentPostProcessor`.

### Nếu bỏ đăng ký processor thì sao?

Nếu bỏ dòng đăng ký trong `spring.factories` và chạy theo cấu hình file hiện tại, `demo.feature-enabled` không được cung cấp bởi nguồn nào trong ví dụ. Điều kiện `havingValue="true"` với `matchIfMissing=false` mặc định không khớp, nên `FeatureService` vắng mặt. Điều này minh họa hai điều kiện độc lập: implementation đúng vẫn phải **được đăng ký và chạy đúng giai đoạn**, và property phải được **phân giải đúng giá trị**.

## 7. Quan sát nguồn thắng và thời điểm chạy

Khi debug, chỉ gọi `environment.getProperty(key)` thường chưa đủ, vì nó cho biết **giá trị cuối cùng** mà không nói nguồn nào cung cấp nó. Có thể thêm đoạn chẩn đoán sau vào bên trong phương thức `showResult` của ví dụ:

~~~java
// Đoạn minh họa đặt bên trong showResult(...).
// Biến environment ở đây có kiểu Environment.
if (environment instanceof
        org.springframework.core.env.ConfigurableEnvironment configurable) {
    for (org.springframework.core.env.PropertySource<?> source
            : configurable.getPropertySources()) {
        Object value = source.getProperty("demo.feature-enabled");
        if (value != null) {
            System.out.println("source=" + source.getName()
                    + "; value=" + value);
            break;
        }
    }
}
~~~

Đoạn trên **không là một class độc lập**. Nó duyệt theo thứ tự `MutablePropertySources` và dừng ở nguồn đầu tiên trả về giá trị khác `null` cho khóa minh họa. Một số nguồn, đặc biệt những nguồn liên quan environment variables và property naming, có cách phân giải tên linh hoạt; nếu cần đối chiếu khóa nào thắng, hãy tra cứu cùng dạng khóa đang dùng trong condition và cẩn trọng với tên chuẩn hóa.

Trong dự án có Actuator, endpoint `/actuator/env` (nếu được cung cấp và expose có kiểm soát) có thể hỗ trợ xem giá trị/property source; endpoint `/actuator/conditions` (khi được bật/expose) cho thấy lý do điều kiện khớp hoặc không khớp. Các endpoint này không nhất thiết public hay bật sẵn. Tránh đưa secrets vào log và không expose thông tin cấu hình nhạy cảm một cách tùy tiện.

Một công cụ khác là chạy:

~~~bash
java -jar target/environment-condition-demo-1.0.0.jar --debug
~~~

Spring Boot sẽ đưa ra **Condition Evaluation Report** trong log chẩn đoán nếu logging cho phép hiển thị. Lưu ý ví dụ đặt `logging.level.root=ERROR`; để nhìn thấy report ở mức phù hợp, hãy bỏ cấu hình giảm log hoặc ghi đè mức log khi chạy, chẳng hạn:

~~~bash
java -jar target/environment-condition-demo-1.0.0.jar --debug --logging.level.root=INFO
~~~

Tìm `DemoApplication#featureService` và lý do `@ConditionalOnProperty` match/mismatch. Đừng nhầm `Positive matches` của một cấu hình với việc mọi bean liên quan đều đã được khởi tạo thành công.

## 8. Lỗi phổ biến liên quan timing và cách xử lý

### “Trong runner tôi thấy true nhưng bean không có”

Có thể giá trị đã được thêm/sửa **sau khi** cấu hình được xử lý. In giá trị ở cuối startup không tái hiện lịch sử của nó. Kiểm tra callback nào thêm property, thứ tự `EnvironmentPostProcessor`, event listener, profile và thời điểm condition được xét. Nếu cần property quyết định cấu trúc context, hãy cung cấp sớm hơn, qua config data hoặc hook khởi tạo thích hợp.

### “Thêm @PropertySource rồi mà logging.* không đổi”

`@PropertySource` được xử lý khi refresh; cấu hình logging có thể đã đọc giá trị trước đó. Dùng `application.properties`, command-line, system/environment properties hay một cơ chế cấu hình sớm phù hợp.

### “Tôi thấy cùng khóa ở hai file nên tưởng có hai giá trị”

`Environment.getProperty` trả về một giá trị được phân giải theo precedence. Hãy tìm nguồn ưu tiên cao nhất và xem profile/file import; nếu key là cấu trúc nhiều phần tử, cơ chế binding có quy tắc riêng, đừng suy ra “merge” từ việc hai file đều tồn tại.

### “Thêm PropertySource trong @Bean rồi đợi @ConditionalOnProperty đổi kết quả”

Lúc gọi phương thức `@Bean`, định nghĩa bean có điều kiện có thể đã được quyết định. Việc sửa `Environment` bên trong một bean thường quá muộn để tác động tới quyết định đăng ký bean trước đó. Chuyển logic bổ sung property sang giai đoạn chuẩn bị `Environment`.

### “Tên biến môi trường có dấu gạch dưới mà condition không nhận”

Spring Boot có quy tắc biểu diễn tên biến môi trường cho externalized configuration, ví dụ `DEMO_FEATURE_ENABLED` tương ứng với khóa cấu hình dạng canonical phù hợp. Nên dùng dạng tên property nhất quán, kiểm tra quy tắc relaxed binding và nguồn cụ thể thay vì đoán từ phép thay ký tự. Tên có nhiều dấu gạch ngang, dấu chấm hay chỉ số collection cần đặc biệt cẩn trọng.

### “Tôi thay property lúc runtime nhưng bean không được thêm/xóa”

Các condition dạng `@ConditionalOnProperty` thường là **điều kiện khởi tạo context**, không phải hệ thống phản ứng theo từng thay đổi property. Muốn cập nhật hành vi runtime, có thể thiết kế service đọc giá trị động, cơ chế refresh chuyên dụng hoặc tái khởi tạo context tùy yêu cầu. Không dựa vào auto-configuration để tự đổi bean graph trong context đang chạy.

### “Tôi chỉ debug file application.properties”

Một giá trị từ command-line, JVM system properties, OS env, external config hoặc profile có thể ghi đè file trong JAR. Hãy kiểm tra trực tiếp `Environment` và thứ tự `PropertySource`.

## 9. Quy trình chẩn đoán ngắn gọn

Khi một conditional bean không có mặt:

1. **Xác nhận key, value, annotation.** Đọc `prefix`, `name`, `havingValue`, `matchIfMissing` và các điều kiện khác đang áp dụng; tránh đoán từ tên bean.
2. **Xác nhận property sources.** Tìm nguồn đầu tiên cung cấp khóa, kiểm tra thứ tự và giá trị trả về; đối chiếu CLI, `-D`, env, config data, profile và import.
3. **Xác nhận timing.** Nguồn được thêm trước khi refresh hay trong/sau refresh? `@PropertySource` được xử lý ở cấu hình nào? `EnvironmentPostProcessor` có được đăng ký và chạy đúng thứ tự?
4. **Đọc condition report.** Phân biệt “điều kiện không khớp nên không đăng ký bean” với “điều kiện khớp nhưng quá trình khởi tạo bean thất bại”.
5. **Thử trường hợp tối thiểu.** Dùng hai lệnh chạy khác nhau ở phần 6 để kiểm tra xem thay đổi nguồn ưu tiên cao có thay đổi quyết định tạo bean hay không.
6. **Sửa đúng giai đoạn.** Giá trị cần cho condition phải sẵn sàng ở giai đoạn đánh giá condition; giá trị chỉ dành cho logic bên trong bean có thể được đọc/bind sau đó theo lifecycle của bean.

## 10. Câu hỏi tự kiểm tra

**1. Environment có phải là một file cấu hình không?** Không. Đây là abstraction truy vấn nhiều `PropertySource` và thông tin profile.

**2. Vì sao một khóa xuất hiện ở application.properties nhưng getProperty lại trả về giá trị khác?** Vì nguồn ưu tiên cao hơn (chẳng hạn command-line) cũng cung cấp khóa đó.

**3. addFirst và addLast khác gì?** `addFirst` làm nguồn được tra cứu trước; `addLast` đưa nguồn xuống mức ưu tiên thấp hơn trong danh sách hiện tại.

**4. Một thuộc tính mới thêm trong ApplicationRunner có làm @ConditionalOnProperty của bean đã xét chạy lại không?** Không. Các điều kiện đăng ký bean không tự được đánh giá lại chỉ vì thay đổi `Environment` sau startup.

**5. Vì sao @PropertySource không nên dùng để điều khiển logging.*?** Vì annotation được xử lý trong refresh, còn logging có thể được cấu hình trước đó.

**6. Nếu demo.feature-enabled vắng mặt, havingValue="true" có khớp không?** Mặc định `matchIfMissing=false` nên không khớp.

**7. Nếu property có giá trị false trong file nhưng true từ command-line thì điều kiện nhìn thấy gì?** Theo precedence mặc định, điều kiện đọc `true` từ nguồn command-line tại thời điểm đánh giá, nên có thể khớp.

## Tài liệu chính thức

- Spring Framework — Environment Abstraction: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Creating Your Own Auto-configuration (conditions): https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot — EnvironmentPostProcessor API (chọn đúng phiên bản sử dụng): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html

**Kết luận để áp dụng:** Muốn giải thích một conditional bean, hãy kiểm tra **giá trị Environment đã phân giải, PropertySource thắng theo precedence và thời điểm property sẵn sàng khi condition được xét**. Đọc giá trị ở cuối startup chỉ xác nhận trạng thái hiện tại; không thay thế việc hiểu vòng đời khởi tạo.