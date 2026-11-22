# Bổ sung profile bằng SpringApplication và ConfigurableEnvironment

Spring Profiles cho phép cùng một ứng dụng Spring Boot hoạt động với các bộ cấu hình khác nhau, ví dụ `dev`, `test` và `prod`. Thông thường, profile được chỉ định bằng thuộc tính `spring.profiles.active` trong cấu hình hoặc qua tham số khởi động. Tuy nhiên, cũng có những trường hợp **chương trình muốn chủ động bổ sung profile ngay trong mã Java**.

Spring Boot cung cấp `SpringApplication.setAdditionalProfiles(...)` cho nhu cầu đó. Spring Framework còn có API `ConfigurableEnvironment.addActiveProfile(...)` và `ConfigurableEnvironment.setActiveProfiles(...)` để quản lý tập profile trong một `Environment` cụ thể. Ba phương thức này liên quan nhau, nhưng **không hoàn toàn cùng ý nghĩa**.

Bài học giới thiệu hai cách bổ sung profile, thứ tự áp dụng, thời điểm phải gọi trước quá trình khởi tạo bean và cách quan sát cấu hình profile-specific trong Spring Boot 3.3.x (Java 21).

## 1. Profile ảnh hưởng đến những gì?

Một *profile* là một tên đại diện cho điều kiện hoặc môi trường chạy, chẳng hạn `dev`, `prod`, `mock-payment` hoặc `metrics`. Khi profile hoạt động, Spring có thể:

- Nạp các tệp cấu hình tương ứng, ví dụ `application-dev.yml` và `application-prod.properties`.
- Kích hoạt các bean hoặc lớp cấu hình được gắn `@Profile("dev")`, `@Profile("prod")`.
- Chọn các YAML document có điều kiện `spring.config.activate.on-profile`.
- Kết hợp với các profile khác, theo thứ tự và quy tắc ghi đè của Config Data.

Giả sử có ba tệp:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-metrics.yml
~~~

`application.yml` chứa giá trị chung:

~~~yaml
spring:
  application:
    name: profile-demo

app:
  message: "Ứng dụng mặc định"
  audit:
    enabled: false
~~~

`application-dev.yml`:

~~~yaml
app:
  message: "Ứng dụng dành cho phát triển"
~~~

`application-metrics.yml`:

~~~yaml
app:
  audit:
    enabled: true
~~~

Nếu chạy ứng dụng với cả `dev` và `metrics`, kết quả trong ví dụ là:

~~~text
app.message = Ứng dụng dành cho phát triển
app.audit.enabled = true
~~~

Điều này minh họa hai profile có thể cùng hoạt động và mỗi file chỉ cần ghi đè những khóa mà nó quản lý. Nếu nhiều file cùng chứa một khóa, Spring Boot sẽ quyết định giá trị hiệu lực theo thứ tự ưu tiên Config Data và thứ tự profile.

## 2. Cách trực tiếp: `SpringApplication.setAdditionalProfiles(...)`

Để bổ sung profile trước khi chạy ứng dụng, khởi tạo đối tượng `SpringApplication` thay vì gọi trực tiếp phương thức `SpringApplication.run(...)` dạng static.

~~~java
package com.example.profiledemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProfileDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ProfileDemoApplication.class);

        // Bổ sung một profile cho lần chạy này.
        application.setAdditionalProfiles("metrics");

        // Khởi động ứng dụng sau khi đã thiết lập profile.
        application.run(args);
    }
}
~~~

Ở đây, `metrics` là một **additional profile** của `SpringApplication`. Khi bắt đầu chạy, Spring Boot đưa profile này vào tập profile được sử dụng, cùng với những profile được kích hoạt hợp lệ từ các nguồn bên ngoài.

Ví dụ chạy từ JAR:

~~~bash
java -jar profile-demo.jar --spring.profiles.active=dev
~~~

Khi đó ứng dụng dùng cả `dev` từ CLI và `metrics` được bổ sung trong mã. Các giá trị ứng dụng trong phần trước có thể nhận từ `application-dev.yml` và `application-metrics.yml`.

### Vì sao dùng "Additional" thay vì đặt tên một profile bắt buộc?

`setAdditionalProfiles("metrics")` cho phép giữ lại các profile đã kích hoạt từ nguồn khác. Nếu môi trường triển khai chạy với `--spring.profiles.active=prod`, chương trình vẫn có thể thêm `metrics` mà không yêu cầu người vận hành nhớ truyền cả hai.

Ý định thường thấy:

~~~text
Profile do môi trường quyết định: dev / test / prod
Profile bổ sung theo ứng dụng:   metrics

Lần chạy dev:   dev + metrics
Lần chạy prod:  prod + metrics
~~~

Phương thức này phù hợp với profile mang ý nghĩa bổ sung tính năng hoặc nhóm cấu hình chung. Không nên tự động bật các profile có hành vi nguy hiểm hoặc không phù hợp mọi môi trường.

### Bổ sung nhiều profile

~~~java
SpringApplication application =
        new SpringApplication(ProfileDemoApplication.class);

application.setAdditionalProfiles("metrics", "observability");
application.run(args);
~~~

Đây là một lời gọi với hai tên profile. API chấp nhận tham số biến độ dài `String...`.

### Khi nào phải gọi?

Gọi **trước `application.run(args)`**. Nếu sử dụng:

~~~java
SpringApplication.run(ProfileDemoApplication.class, args);
~~~

ứng dụng đã bắt đầu vòng đời khởi động ngay tại dòng đó, nên bạn không còn cơ hội tùy chỉnh `SpringApplication` bằng `setAdditionalProfiles` trước khi tạo context. Hãy dùng dạng đối tượng khi cần cấu hình bootstrap.

## 3. `setAdditionalProfiles` khác gì với `spring.profiles.active`?

`spring.profiles.active` biểu thị danh sách profile hoạt động được xác định từ các nguồn thuộc tính. Thuộc tính này đi theo thứ tự ưu tiên thông thường: ví dụ một giá trị trong tham số CLI có thể ghi đè `spring.profiles.active` trong `application.yml`.

~~~yaml
# application.yml
spring:
  profiles:
    active: dev
~~~

Chạy:

~~~bash
java -jar profile-demo.jar --spring.profiles.active=prod
~~~

Trong tình huống đơn giản, profile từ CLI `prod` thay thế `dev` khai báo trong file; đây là hành vi của `spring.profiles.active`. Nhưng `metrics` được cấu hình bằng `SpringApplication.setAdditionalProfiles("metrics")` vẫn được bổ sung vào tập profile dùng khi khởi động.

So sánh:

| Cơ chế | Ý nghĩa |
| --- | --- |
| `spring.profiles.active=dev` | Chỉ định tập profile hoạt động qua property |
| `--spring.profiles.active=prod` | Chỉ định tập profile hoạt động từ CLI, có thể ghi đè property trong file |
| `application.setAdditionalProfiles("metrics")` | Bổ sung `metrics` cho lần chạy, bên cạnh các profile từ nguồn cấu hình khác |
| `spring.profiles.include=common` | Bổ sung profile thông qua cơ chế cấu hình của Spring Boot |
| `spring.profiles.group.prod=...` | Khi bật profile nhóm, kích hoạt thêm các profile thành viên |

Một điểm cần tránh: không coi `setAdditionalProfiles` như việc **ghi `spring.profiles.active` vào một file**. Đây là API của đối tượng bootstrap, tác động đến quá trình chạy hiện tại.

## 4. Quan sát profile hoạt động với `Environment`

Spring Framework cung cấp `Environment` để đọc thông tin profile và thuộc tính cấu hình. Dùng một `ApplicationRunner` để quan sát sau khi ứng dụng khởi động:

~~~java
package com.example.profiledemo;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ProfileDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ProfileDemoApplication.class);

        application.setAdditionalProfiles("metrics");
        application.run(args);
    }

    @Bean
    ApplicationRunner showProfiles(Environment environment) {
        return args -> {
            System.out.println(
                    "Active profiles: "
                            + Arrays.toString(environment.getActiveProfiles()));

            System.out.println(
                    "Default profiles: "
                            + Arrays.toString(environment.getDefaultProfiles()));

            System.out.println(
                    "app.message: " + environment.getProperty("app.message"));

            System.out.println(
                    "app.audit.enabled: "
                            + environment.getProperty("app.audit.enabled"));
        };
    }
}
~~~

Chạy:

~~~bash
java -jar profile-demo.jar --spring.profiles.active=dev
~~~

Kết quả có thể tương tự:

~~~text
Active profiles: [metrics, dev]
Default profiles: [default]
app.message: Ứng dụng dành cho phát triển
app.audit.enabled: true
~~~

Thứ tự các tên trong mảng `getActiveProfiles()` phụ thuộc cách chúng được tập hợp trong bootstrap; **không nên dựa vào một thứ tự in ra cố định nếu chương trình không quy định rõ việc đó**. Điểm quan trọng là cả hai profile đều hoạt động.

`getDefaultProfiles()` trả về các profile dự phòng, thông thường gồm `default`; các profile này được dùng khi **không có active profile nào**. Việc chúng xuất hiện trong kết quả gọi API không có nghĩa profile `default` đang được sử dụng đồng thời với `dev`.

## 5. `ConfigurableEnvironment` là gì?

`Environment` là giao diện để truy vấn thuộc tính và profile. `ConfigurableEnvironment` mở rộng nó bằng các thao tác thay đổi cấu hình, trong đó có:

~~~java
void setActiveProfiles(String... profiles);
void addActiveProfile(String profile);
void setDefaultProfiles(String... profiles);
String[] getActiveProfiles();
String[] getDefaultProfiles();
~~~

`ConfigurableEnvironment` nằm ở package:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
~~~

Ba thao tác chính cần phân biệt:

- `addActiveProfile("metrics")`: **thêm** tên `metrics` vào tập profile đang hoạt động và giữ các tên hiện có.
- `setActiveProfiles("dev", "metrics")`: **thay toàn bộ** tập active profiles của đối tượng `Environment` bằng danh sách cung cấp.
- `setDefaultProfiles("local")`: thay tập **default profiles** được dùng khi không có active profile; nó không giống việc bổ sung vào active profiles.

Ví dụ với một `ConfigurableEnvironment` riêng:

~~~java
import java.util.Arrays;

import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.StandardEnvironment;

public class EnvironmentExample {

    public static void main(String[] args) {
        ConfigurableEnvironment environment = new StandardEnvironment();

        environment.setActiveProfiles("dev");
        environment.addActiveProfile("metrics");

        System.out.println(Arrays.toString(environment.getActiveProfiles()));
        // Bao gồm "dev" và "metrics".
    }
}
~~~

`StandardEnvironment` là một implementation của `ConfigurableEnvironment` trong Spring Framework. Trong ví dụ này nó là **một đối tượng độc lập**, chỉ để minh họa API. Tạo `new StandardEnvironment()` rồi chỉnh sửa nó **không tự động làm thay đổi Environment của một ứng dụng Spring Boot đang chạy**. Muốn ảnh hưởng đến ứng dụng, cần thao tác trên đúng Environment mà SpringApplication dùng.

## 6. Bổ sung profile bằng `ConfigurableEnvironment` trước khi chạy ứng dụng

Có thể chủ động cung cấp một `ConfigurableEnvironment` cho `SpringApplication`. Ví dụ dưới đây dành cho ứng dụng **không phải web** để dùng `StandardEnvironment` một cách rõ ràng:

~~~java
package com.example.profiledemo;

import java.util.Arrays;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.StandardEnvironment;

@SpringBootApplication
public class ProfileDemoApplication {

    public static void main(String[] args) {
        // Tạo Environment trước quá trình bootstrap.
        ConfigurableEnvironment environment = new StandardEnvironment();

        // Thêm profile vào Environment sẽ gắn với SpringApplication.
        environment.addActiveProfile("metrics");

        SpringApplication application =
                new SpringApplication(ProfileDemoApplication.class);

        // Ví dụ dùng trong một ứng dụng console/batch, không chạy web server.
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setEnvironment(environment);

        application.run(args);
    }
}
~~~

Khi môi trường ở trên được dùng để khởi động ứng dụng, profile `metrics` đã được thiết lập **trước thời điểm nạp config data và đăng ký bean**, nên Spring có thể xem xét `application-metrics.yml` và điều kiện `@Profile("metrics")`.

**Giới hạn của ví dụ:** Spring Boot có các loại `Environment` và `ApplicationContext` phù hợp với ứng dụng servlet, reactive hoặc non-web. Không tùy tiện dùng `StandardEnvironment` để thay thế môi trường trong ứng dụng web đang có nhu cầu servlet/reactive-specific property sources. Trong ứng dụng Spring Boot thông thường, nếu chỉ muốn thêm profile, `setAdditionalProfiles(...)` thường đơn giản và ít phụ thuộc loại môi trường hơn.

Một cách dùng `ConfigurableEnvironment` khác là trong quá trình chuẩn bị bootstrap có cung cấp đúng đối tượng Environment. Điều quan trọng không nằm ở nơi tạo biến `environment` mà ở **thời điểm thay đổi và việc đối tượng đó thực sự được SpringApplication sử dụng**.

## 7. `addActiveProfile` và `setActiveProfiles`: thêm hay thay?

Giả sử Environment hiện có active profiles:

~~~text
[dev]
~~~

Gọi:

~~~java
environment.addActiveProfile("metrics");
~~~

thì tập profile trở thành:

~~~text
[dev, metrics]
~~~

Nhưng nếu gọi:

~~~java
environment.setActiveProfiles("metrics");
~~~

thì tập profile hiện có được thay thành:

~~~text
[metrics]
~~~

Với các ứng dụng đang có cấu hình theo môi trường, khác biệt này rất lớn: gọi `setActiveProfiles("metrics")` có thể khiến `dev` hoặc `prod` biến mất khỏi tập active profiles được quản lý bởi chính Environment đó.

Ví dụ tương phản:

~~~java
ConfigurableEnvironment environment = new StandardEnvironment();

environment.setActiveProfiles("dev");
environment.addActiveProfile("metrics");
// Tập active: dev, metrics.

environment.setActiveProfiles("prod");
// Tập active: prod. Hai profile dev, metrics không còn trong tập này.
~~~

Đây là minh họa trực tiếp API của Spring Framework. Trong một lần chạy Spring Boot, Config Data và các nguồn cấu hình khác cũng tham gia xác định profile; vì thế, để có kết quả dễ dự đoán, ưu tiên điều chỉnh profile bằng một cơ chế bootstrap đã được chọn rõ ràng.

### API nào phù hợp với yêu cầu "bổ sung"?

| Yêu cầu | API phù hợp |
| --- | --- |
| Bổ sung một profile khi tạo ứng dụng Spring Boot | `SpringApplication.setAdditionalProfiles(...)` |
| Đã có `ConfigurableEnvironment` đúng của bootstrap và muốn giữ profile hiện có | `ConfigurableEnvironment.addActiveProfile(...)` |
| Chủ ý xác định lại toàn bộ active profiles trong một Environment | `ConfigurableEnvironment.setActiveProfiles(...)` |
| Chỉ thay fallback khi không có profile hoạt động | `ConfigurableEnvironment.setDefaultProfiles(...)` |

Tên `setActiveProfiles` và `setAdditionalProfiles` nghe gần giống, nhưng một bên **thay tập active của Environment**, còn bên kia **đưa thêm profile vào SpringApplication**.

## 8. Vì sao thời điểm bổ sung profile quyết định kết quả?

Profile có thể ảnh hưởng đến hai việc quan trọng trong quá trình khởi động:

1. **Nạp Config Data:** đọc `application-dev.yml`, `application-prod.yml` hoặc các YAML document được kích hoạt bởi profile.
2. **Đăng ký bean:** đánh giá `@Profile` trên `@Configuration`, `@Component`, các bean factory method và một số định nghĩa cấu hình khác.

Quá trình diễn ra theo vòng đời khởi động, vì thế profile phải được xác lập sớm nếu bạn muốn cả việc **nạp file** và **chọn bean** cùng phản ánh profile đó.

Ví dụ **không phù hợp** để kích hoạt cấu hình theo profile của toàn bộ ứng dụng:

~~~java
@Component
class LateProfileChange implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    LateProfileChange(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        environment.addActiveProfile("metrics");
    }
}
~~~

Trong ví dụ này, `ApplicationRunner` chạy **sau khi ApplicationContext đã được refresh**. Lệnh `addActiveProfile` có thể thay đổi danh sách tên active trong đối tượng Environment tại thời điểm đó, nhưng **không làm Spring Boot tự quay lại nạp `application-metrics.yml`** và cũng **không tự đăng ký lại các bean `@Profile("metrics")` đã bỏ qua trước đó**.

Vì vậy, đọc lại `getActiveProfiles()` sau dòng này có thể thấy thêm `metrics`, nhưng kiểm tra bean hoặc cấu hình trong file metrics vẫn cho kết quả không như mong muốn. Đây là lỗi do **thay đổi quá muộn**, không phải lỗi cú pháp API.

Tương tự, không nên sử dụng `@PostConstruct` trong một bean thông thường để kích hoạt profile mà hệ thống cần từ đầu bootstrap.

Hãy đặt ý định bổ sung profile ở điểm khởi động, trước `run(args)`, hoặc ở một cơ chế bootstrap có bảo đảm về thứ tự xử lý. Với phần lớn trường hợp, `SpringApplication.setAdditionalProfiles` là lựa chọn trực tiếp.

## 9. Ví dụ dùng `@Profile` để bật bean tương ứng

Sau khi thiết lập profile từ một trong các cách hợp lệ trước khởi động, Spring có thể chọn bean theo điều kiện `@Profile`.

~~~java
package com.example.profiledemo;

public interface NotificationSender {
    String send(String message);
}
~~~

Implementation dành cho phát triển:

~~~java
package com.example.profiledemo;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("dev")
public class ConsoleNotificationSender implements NotificationSender {

    @Override
    public String send(String message) {
        return "Console: " + message;
    }
}
~~~

Implementation dành cho production:

~~~java
package com.example.profiledemo;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("prod")
public class ProductionNotificationSender implements NotificationSender {

    @Override
    public String send(String message) {
        return "Production sender: " + message;
    }
}
~~~

Trong ví dụ tối giản này, phương thức `send` chỉ trả chuỗi để minh họa điều kiện chọn bean; nó không thực hiện gửi thông báo ra ngoài. Nếu ứng dụng inject duy nhất một `NotificationSender`, hãy bảo đảm tập profile đang hoạt động tạo đúng một implementation phù hợp. Nếu không có `dev` hay `prod`, có thể không có bean; nếu bật cả hai, có thể có nhiều bean cùng kiểu.

Ví dụ bean kiểm tra:

~~~java
package com.example.profiledemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean
    ApplicationRunner sendTestNotification(NotificationSender sender) {
        return args -> System.out.println(sender.send("Xin chào"));
    }
}
~~~

Chạy với `--spring.profiles.active=dev` và có additional profile `metrics` thì bean `ConsoleNotificationSender` được chọn. Chạy với `prod` thì bean `ProductionNotificationSender` được chọn. Việc có thêm `metrics` trong trường hợp này không tạo thêm implementation vì không có bean nào được gắn `@Profile("metrics")`.

**Không dùng `@Profile` để định nghĩa thứ tự ưu tiên của các file YAML.** `@Profile` quyết định bean có được đăng ký không; còn file `application-<profile>.yml` và thuộc tính bên trong thuộc cơ chế Config Data.

## 10. Kết hợp hai profile với hai loại cấu hình khác nhau

Một cách tổ chức hay gặp là một profile đại diện môi trường triển khai và một profile biểu thị một khả năng phụ trợ.

Ví dụ:

~~~text
Profile môi trường: dev hoặc prod
Profile phụ trợ:     metrics
~~~

Cấu trúc file:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
├── application-prod.yml
└── application-metrics.yml
~~~

`application.yml`:

~~~yaml
app:
  name: customer-service
  endpoint: https://api.example.org
  monitoring:
    enabled: false
~~~

`application-dev.yml`:

~~~yaml
app:
  endpoint: http://localhost:8080
~~~

`application-prod.yml`:

~~~yaml
app:
  endpoint: https://api.production.example.org
~~~

`application-metrics.yml`:

~~~yaml
app:
  monitoring:
    enabled: true
~~~

Đoạn bootstrap:

~~~java
SpringApplication application =
        new SpringApplication(ProfileDemoApplication.class);
application.setAdditionalProfiles("metrics");
application.run(args);
~~~

Khi chạy với `--spring.profiles.active=dev`, cấu hình cuối trong ví dụ:

~~~text
app.name = customer-service
app.endpoint = http://localhost:8080
app.monitoring.enabled = true
~~~

Khi chạy với `--spring.profiles.active=prod`:

~~~text
app.name = customer-service
app.endpoint = https://api.production.example.org
app.monitoring.enabled = true
~~~

Ví dụ không có trùng khóa giữa `application-dev.yml`/`application-prod.yml` và `application-metrics.yml`, nên việc quan sát kết quả không phụ thuộc thứ tự ghi đè giữa các profile này. Nếu nhiều file profile-specific cùng khai báo `app.endpoint`, kết quả phải được xác định theo thứ tự profile và thứ tự location group thực tế.

## 11. Bổ sung profile từ giá trị chương trình quyết định trước bootstrap

Đôi khi launcher nhận một tham số riêng, rồi quyết định bổ sung profile. Ví dụ một ứng dụng console nhận cờ `--enable-metrics` theo quy ước của chính launcher:

~~~java
package com.example.profiledemo;

import java.util.Arrays;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProfileDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ProfileDemoApplication.class);

        boolean metricsRequested = Arrays.asList(args)
                .contains("--enable-metrics");

        if (metricsRequested) {
            application.setAdditionalProfiles("metrics");
        }

        application.run(args);
    }
}
~~~

Ví dụ trên xử lý cờ theo cách đơn giản trước khi gọi `run`. Trong hệ thống thực tế, nên thiết kế tên tham số rõ ràng và cân nhắc dùng ngay cơ chế cấu hình Spring Boot thay vì tự xây dựng một bộ phân tích CLI phức tạp. Điều mấu chốt là quyết định bổ sung profile diễn ra **trước** quá trình khởi động.

Chạy:

~~~bash
java -jar profile-demo.jar --spring.profiles.active=dev --enable-metrics
~~~

Trong cách minh họa này, `--enable-metrics` là cờ do code launcher kiểm tra. Nếu mục tiêu chỉ là bật tính năng có điều kiện, một thuộc tính boolean như `app.metrics.enabled` có thể đơn giản hơn so với tạo profile mới.

## 12. Phân biệt `spring.profiles.include`, profile group và API Java

Không phải trường hợp bổ sung profile nào cũng cần sửa mã Java.

### 12.1. `spring.profiles.include`

Trong `application.yml` chung:

~~~yaml
spring:
  profiles:
    include:
      - common
      - metrics
~~~

Các profile `common` và `metrics` được bổ sung ngoài danh sách từ `spring.profiles.active`. Theo tài liệu Spring Boot, included profiles được thêm trước các profile được kích hoạt qua `spring.profiles.active`.

Cơ chế này phù hợp khi nhóm profile phụ trợ là quyết định cấu hình, có thể kiểm soát bằng file.

### 12.2. Profile group

~~~yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
~~~

Khi bật `production`, Spring Boot kích hoạt thêm `proddb` và `prodmq` theo group. Cách này giúp người vận hành chọn một profile đại diện thay vì phải nhớ nhiều tên.

### 12.3. `setAdditionalProfiles(...)`

~~~java
application.setAdditionalProfiles("metrics");
~~~

Là quyết định được đặt ngay tại bootstrap trong Java. Phù hợp khi launcher, thư viện tích hợp hoặc một lựa chọn ở mức ứng dụng cần quyết định profile phải luôn được bổ sung cho lần chạy.

Ba cơ chế có thể cùng tham gia vào tập active profiles. Không nên giả định thứ tự giữa các cơ chế khác nhau chỉ dựa vào tên profile; cần hiểu các điều kiện profile và thứ tự nạp cấu hình cụ thể.

**Quy tắc đối với file profile-specific:** `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include` và các khai báo profile group chỉ được đặt ở document không gắn điều kiện profile. Không đặt các thuộc tính đó vào document có `spring.config.activate.on-profile` hay file `application-prod.yml` để tự kích hoạt thêm profile một cách vòng tròn.

## 13. So sánh `setDefaultProfiles` với `setAdditionalProfiles`

Tên “default profile” có thể dẫn tới nhầm lẫn với “additional profile”.

Giả sử chưa có active profile:

~~~java
ConfigurableEnvironment environment = new StandardEnvironment();

environment.setDefaultProfiles("local");
System.out.println(Arrays.toString(environment.getDefaultProfiles()));
// [local]
~~~

Với Environment này, khi không có active profile, cấu hình dùng profile mặc định có thể áp dụng theo chính sách Spring. Nhưng nếu sau đó bật `prod`:

~~~java
environment.addActiveProfile("prod");
~~~

`local` không còn đóng vai trò active profile dự phòng trong lần xử lý điều kiện profile. Nó vẫn thuộc danh sách *default profiles* của đối tượng, nhưng chỉ dùng khi không có profile hoạt động.

Ngược lại, `setAdditionalProfiles("metrics")` bổ sung một active profile qua quá trình bootstrap `SpringApplication`, ngay cả khi môi trường đã có `dev` hoặc `prod`.

| API | Áp dụng khi nào? | Thay hay thêm? |
| --- | --- | --- |
| `setDefaultProfiles("local")` | Thiết lập tập fallback của Environment | Thay default set |
| `setActiveProfiles("prod")` | Xác định tập active của Environment | Thay active set |
| `addActiveProfile("metrics")` | Bổ sung vào Environment | Thêm active |
| `SpringApplication.setAdditionalProfiles("metrics")` | Bổ sung trước khi Spring Boot chạy | Thêm profile vào ứng dụng |

## 14. Kiểm tra active profile và cấu hình cuối cùng

Trong môi trường học tập hoặc chẩn đoán, nên in tập active profiles và các thuộc tính liên quan:

~~~java
@Bean
ApplicationRunner inspectEnvironment(Environment environment) {
    return args -> {
        System.out.println("Active profiles: "
                + Arrays.toString(environment.getActiveProfiles()));

        System.out.println("app.message: "
                + environment.getProperty("app.message"));

        System.out.println("app.monitoring.enabled: "
                + environment.getProperty("app.monitoring.enabled", Boolean.class));
    };
}
~~~

Đoạn này đặt trong lớp `@Configuration` hoặc `@SpringBootApplication`, với imports:

~~~java
import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
~~~

Nếu muốn kiểm tra profile theo điều kiện logic, Spring Framework có thể sử dụng `Profiles`:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

boolean metricsEnabled = environment.acceptsProfiles(Profiles.of("metrics"));
boolean devWithMetrics =
        environment.acceptsProfiles(Profiles.of("dev & metrics"));
~~~

Kết quả kiểm tra dựa trên tập active profiles hiện có. Đây là cách đọc điều kiện, không phải thao tác kích hoạt thêm profile.

### Lưu ý về log startup

Spring Boot thường hiển thị thông tin active profiles trong thông điệp khởi động. Có thể dùng log này để kiểm tra nhanh, nhưng không nên phụ thuộc vào định dạng log hoặc thứ tự chuỗi profile làm hợp đồng nghiệp vụ. Đối với logic ứng dụng, hãy dùng `Environment` và cấu hình đã bind.

### Cấu hình theo profile chỉ có hiệu lực khi đã được nạp

Nếu profile bổ sung là `metrics` và có file `application-metrics.yml`, file này được xét trong Config Data khi profile có hiệu lực **ở giai đoạn nạp cấu hình**. Nếu chỉ thay đổi active profile bằng mã Java sau khởi động, thông tin `getActiveProfiles()` có thể đổi nhưng những file đã bỏ qua không tự được tải lại.

## 15. Các lỗi thường gặp

### 15.1. Dùng `SpringApplication.run(...)` quá sớm

Không có đối tượng `SpringApplication` để tùy chỉnh trước khi gọi static `run`:

~~~java
// Khi dòng này đã chạy, quá trình khởi động đã diễn ra.
SpringApplication.run(ProfileDemoApplication.class, args);
~~~

Để thêm profile:

~~~java
SpringApplication application =
        new SpringApplication(ProfileDemoApplication.class);
application.setAdditionalProfiles("metrics");
application.run(args);
~~~

### 15.2. Thay profile đang có do nhầm `setActiveProfiles`

~~~java
environment.setActiveProfiles("metrics");
~~~

Lệnh này thay danh sách active của **chính Environment đó**. Nếu muốn giữ `dev` hay `prod` đang có, dùng:

~~~java
environment.addActiveProfile("metrics");
~~~

Hoặc, với Spring Boot, dùng `SpringApplication.setAdditionalProfiles("metrics")` trước khi chạy.

### 15.3. Sửa một Environment không thuộc ứng dụng

~~~java
ConfigurableEnvironment independent = new StandardEnvironment();
independent.addActiveProfile("metrics");

// Dòng này tạo và chỉnh một object riêng.
// Nó chưa thay đổi Environment của một SpringApplication khác.
~~~

Chỉ một Environment được dùng thật sự trong quá trình bootstrap mới ảnh hưởng đến bean và Config Data của ứng dụng đó. Nếu muốn cấp custom Environment, cần gắn nó bằng `SpringApplication.setEnvironment(...)` trước khi `run` và lựa chọn loại Environment phù hợp.

### 15.4. Bổ sung profile sau khi context đã tạo

Gọi `environment.addActiveProfile(...)` từ `ApplicationRunner` hoặc một bean đã khởi tạo **không tự kích hoạt lại** bean `@Profile` và không nạp lại YAML. Chọn thời điểm trước bootstrap.

### 15.5. Sai tên profile so với tên file

~~~text
Profile đang hoạt động: production
Tên file hiện có:        application-prod.yml
~~~

`production` và `prod` là hai tên khác nhau. Nếu muốn dùng `application-prod.yml`, cần kích hoạt đúng `prod` hoặc đổi file thành `application-production.yml`.

### 15.6. Cấu hình giá trị không khớp do ưu tiên nguồn

Một file `application-dev.yml` có thể chứa `app.message=local`, nhưng CLI `--app.message=remote` thường có ưu tiên cao hơn. Khi đó profile vẫn hoạt động đúng, chỉ là **giá trị cuối cùng** đến từ nguồn khác.

Đừng dùng mỗi nội dung của một file để kết luận rằng profile chưa được kích hoạt. Hãy kiểm tra `getActiveProfiles()` trước rồi kiểm tra các nguồn thuộc tính liên quan.

### 15.7. Có nhiều bean cùng kiểu khi bật nhiều profile

Nếu `@Profile("dev")` và `@Profile("prod")` cùng tạo bean `NotificationSender`, bật cả `dev` lẫn `prod` có thể dẫn tới nhiều ứng viên injection. Cần quy định tập profile triển khai, hoặc có cơ chế chọn bean như `@Primary`/`@Qualifier` khi thực sự phù hợp.

### 15.8. Dùng profile để biểu diễn mọi cấu hình tính năng

Profile có ích cho điều kiện bean và nhóm cấu hình. Nhưng những cờ có thể đổi độc lập như `app.feature.enabled` hoặc hạn mức `app.retry-count` thường đơn giản hơn nếu biểu diễn bằng thuộc tính cấu hình có kiểu thay vì thêm hàng chục profile tên khác nhau.

## 16. Bài thực hành

### Bài 1 — Bổ sung profile qua SpringApplication

Chuẩn bị `application.yml` và `application-metrics.yml` với:

~~~yaml
# application.yml
app:
  monitoring:
    enabled: false
~~~

~~~yaml
# application-metrics.yml
app:
  monitoring:
    enabled: true
~~~

Thêm:

~~~java
SpringApplication application =
        new SpringApplication(ProfileDemoApplication.class);
application.setAdditionalProfiles("metrics");
application.run(args);
~~~

Dùng `Environment` đọc `app.monitoring.enabled`. Giá trị mong đợi là `true`, giả định không nguồn ưu tiên cao hơn ghi đè.

### Bài 2 — Kiểm tra profile từ CLI cùng với additional profile

Chạy JAR với:

~~~bash
java -jar profile-demo.jar --spring.profiles.active=dev
~~~

Trong mã luôn có `setAdditionalProfiles("metrics")`. Hãy in `getActiveProfiles()` và giải thích vì sao `dev`, `metrics` đều xuất hiện, mặc dù lệnh CLI chỉ nêu `dev`.

### Bài 3 — Thêm và thay bằng ConfigurableEnvironment

~~~java
ConfigurableEnvironment environment = new StandardEnvironment();
environment.setActiveProfiles("dev");
environment.addActiveProfile("metrics");
// Dự đoán getActiveProfiles().

environment.setActiveProfiles("prod");
// Dự đoán getActiveProfiles() lần nữa.
~~~

Đáp án: lần đầu tập gồm `dev` và `metrics`; lần sau chỉ còn `prod`.

### Bài 4 — Điều tra thêm profile quá muộn

Thử gọi `environment.addActiveProfile("metrics")` trong một `ApplicationRunner` mà không thêm profile từ bootstrap. Sau khi gọi, đọc `getActiveProfiles()` và `app.monitoring.enabled`. Giải thích vì sao danh sách tên profile có thể đã đổi nhưng giá trị từ `application-metrics.yml` không tự được tải lại.

### Bài 5 — Kiểm tra cấu hình và bean theo profile

Tạo hai bean cùng interface với `@Profile("dev")` và `@Profile("prod")`. Chạy riêng từng profile; sau đó bật cả hai để quan sát sự khác biệt khi Spring cần inject một bean duy nhất.

### Bài 6 — Tập default profile

Với `ConfigurableEnvironment` độc lập, gọi `setDefaultProfiles("local")` rồi `getDefaultProfiles()`. Tiếp tục gọi `addActiveProfile("prod")`. Giải thích khi nào default profile được dùng.

## 17. Ghi nhớ

- `SpringApplication.setAdditionalProfiles(...)` là cách trực tiếp để **bổ sung profile bằng Java trước khi Spring Boot khởi động**.
- `ConfigurableEnvironment.addActiveProfile(...)` thêm một active profile trên đúng đối tượng Environment; `setActiveProfiles(...)` thay tập active profiles của Environment.
- `setDefaultProfiles(...)` điều khiển tập dự phòng khi không có active profile, khác với việc bổ sung profile hoạt động.
- Thời điểm kích hoạt profile phải đủ sớm để ảnh hưởng đến nạp `application-<profile>.yml`, YAML document theo profile và đánh giá `@Profile` cho bean.
- Thay đổi active profiles sau khi context đã khởi tạo không tự làm lại quá trình Config Data hay đăng ký bean.
- CLI, environment variables, config data và additional profiles có thể cùng tác động. Kiểm tra `Environment.getActiveProfiles()` để biết profile thực tế; đọc giá trị hiệu lực để hiểu ghi đè.
- Khi chỉ cần bổ sung profile cho ứng dụng Spring Boot thông thường, ưu tiên `SpringApplication.setAdditionalProfiles(...)` vì API thể hiện rõ ý định và không cần tự thay thế loại Environment.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html)
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Framework 6.1 — ConfigurableEnvironment API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html)
