# Chuẩn bị ApplicationArguments, Environment và profile trong chuỗi khởi động Spring Boot

## 1. Vai trò của ba thành phần ở thời điểm khởi động

Khi gọi `SpringApplication.run(...)`, Spring Boot phải biết **ứng dụng được chạy với những đối số nào**, **các thuộc tính cấu hình đến từ đâu và giá trị cuối cùng là gì**, đồng thời **profile nào đang hoạt động** trước khi quyết định tải cấu hình, kích hoạt bean và làm mới `ApplicationContext`.

Ba khái niệm liên kết với nhau nhưng khác trách nhiệm:

| Thành phần | Bản chất | Nhiệm vụ trong startup | Ví dụ |
| --- | --- | --- | --- |
| `ApplicationArguments` | Đối tượng biểu diễn các đối số được truyền vào `run(String... args)` | Giữ nguyên đối số nguồn; phân tích option và non-option để code truy cập một cách có cấu trúc | `--demo.user=Lan`, `--verbose`, `input.csv` |
| `Environment` | Nơi tập hợp `PropertySource` và thông tin profile của Spring | Cung cấp property hiệu lực sau khi hợp nhất nguồn và áp dụng thứ tự ưu tiên | `spring.application.name`, `demo.message`, `server.port` |
| Active/default profiles | Tập tên môi trường logic được `Environment` quản lý | Quyết định tệp config theo profile và các bean/configuration được điều kiện hóa bằng `@Profile` | `dev`, `test`, `prod`, `default` |

**Điểm chính:** `ApplicationArguments` trả lời “đối số nào đã được đưa cho ứng dụng?”, `Environment` trả lời “property đang có giá trị nào?”, còn profile trả lời “nhánh cấu hình và bean nào phù hợp môi trường?”. Tham số CLI có thể vừa là argument vừa được đưa vào `Environment`, nhưng hai API không đồng nhất.

Ví dụ:

~~~bash
java -jar startup-demo.jar --spring.profiles.active=dev --demo.user=Lan input.csv
~~~

- `ApplicationArguments` thấy hai option `spring.profiles.active`, `demo.user` và một non-option `input.csv`.
- Theo mặc định, `SpringApplication` đưa option CLI dạng `--key=value` vào một `CommandLinePropertySource` có độ ưu tiên cao.
- `Environment` có thể trả về `getProperty("spring.profiles.active")` là `dev` và `getProperty("demo.user")` là `Lan`.
- Profile `dev` khiến config data `application-dev.yaml` được xem xét và các bean `@Profile("dev")` đủ điều kiện được tạo.

Không phải mọi chuỗi trong `ApplicationArguments` là property. `input.csv` là non-option; Spring Boot không tự chuyển nó thành property `input.csv`. Cờ `--verbose` có thể hiện diện với **không có giá trị** trong `ApplicationArguments`; tránh giả định `getOptionValues("verbose").get(0)` luôn hợp lệ.

## 2. Vị trí của công đoạn này trong chuỗi khởi động

Dưới đây là **trình tự logic rút gọn** của một lần chạy Spring Boot thông thường. Một số thao tác nội bộ có thể khác nhau theo phiên bản và cấu hình, nhưng các mốc sự kiện chính là hợp đồng vòng đời được Spring Boot công bố.

~~~mermaid
flowchart TD
    A["main(String[] args)"] --> B["SpringApplication.run(args)"]
    B --> C["ApplicationStartingEvent"]
    C --> D["Khởi tạo ApplicationArguments từ args"]
    D --> E["Tạo và chuẩn bị Environment"]
    E --> F["Xử lý CLI, config data, profile và PropertySources"]
    F --> G["ApplicationEnvironmentPreparedEvent"]
    G --> H["Tạo ApplicationContext, áp dụng initializers"]
    H --> I["Nạp BeanDefinitions theo conditions và profiles"]
    I --> J["refresh(): khởi tạo singleton, web server nếu có"]
    J --> K["ApplicationStartedEvent"]
    K --> L["ApplicationRunner / CommandLineRunner"]
    L --> M["ApplicationReadyEvent"]
~~~

Sơ đồ chỉ biểu diễn luồng khái niệm: quá trình phát `ApplicationEnvironmentPreparedEvent` còn được các listener, trong đó có cơ chế xử lý config data, tham gia; không được hiểu rằng **mọi** listener nhìn thấy cấu hình hoàn toàn giống nhau ở mọi thứ tự listener. Spring Boot cũng có `ApplicationContextInitializedEvent` sau khi initializers chạy, `ApplicationPreparedEvent` trước refresh, `AvailabilityChangeEvent` tương ứng trạng thái liveness/readiness và `ApplicationFailedEvent` khi thất bại.

### Các ranh giới cần nhớ

1. **Trước khi có `ApplicationContext`:** không thể dựa vào `@Bean` thông thường để bắt những sự kiện rất sớm như `ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent`. Nếu cần quan sát mốc này, phải đăng ký listener phù hợp từ `SpringApplication.addListeners(...)` hoặc cơ chế listener do Boot hỗ trợ.
2. **Trong giai đoạn Environment được chuẩn bị:** Boot kết hợp CLI, JVM system properties, OS environment variables, config data và các nguồn khác; profile được xác định đủ sớm để tải tài liệu theo profile và phục vụ điều kiện đăng ký bean.
3. **Trước `refresh()`:** context đã có phần metadata/bean definitions; `@Profile` và các điều kiện liên quan được đánh giá khi xử lý cấu hình. `ApplicationArguments` có thể được inject như một bean sau khi context được chuẩn bị cho việc tạo bean.
4. **Sau `refresh()`:** các singleton thông thường đã được tạo. `ApplicationStartedEvent` được phát trước runners; `ApplicationReadyEvent` được phát sau runners. Nếu runner ném exception thì lần chạy có thể thất bại và không đi đến ready.
5. **Không đồng nhất “Environment prepared” với “ứng dụng ready”:** lúc này chưa chắc đã có `@RestController`, connection pool, embedded web server hoặc các bean nghiệp vụ đã sẵn sàng.

### Quan hệ phụ thuộc thực tế

~~~text
args nguồn
  ├─> ApplicationArguments (phân loại option/non-option)
  └─> CLI PropertySource (mặc định)
          │
          v
    Environment <--- config data / OS env / JVM -D / default properties
          │
          ├─> active/default profiles
          ├─> application-{profile}.yaml
          └─> @Profile / @Conditional / @ConfigurationProperties / @Value
                           │
                           v
                     BeanDefinitions → Bean instances
~~~

Đây là luồng dữ liệu chứ không phải mọi công đoạn đều chạy nối tiếp không chồng lấp. Chọn profile, nạp config data và thiết lập property source tương tác nhau trong giai đoạn cấu hình sớm.

## 3. ApplicationArguments được tạo và được sử dụng thế nào?

`SpringApplication` dùng đối số truyền từ `main`, tạo một bản triển khai của `ApplicationArguments` (thông thường `DefaultApplicationArguments`) để cung cấp cả dữ liệu thô và kết quả phân tích.

~~~java
public static void main(String[] args) {
    SpringApplication.run(StartupDemoApplication.class, args);
}
~~~

Nếu launcher tùy biến, cũng có thể tạo `SpringApplication` rồi gọi `run(args)`; điều thiết yếu là **truyền đúng `args`** nếu muốn Boot thấy đối số từ process.

### API cần phân biệt

| Phương thức | Trả về | Ý nghĩa |
| --- | --- | --- |
| `getSourceArgs()` | `String[]` | Đối số gốc theo thứ tự được truyền cho `SpringApplication` |
| `getOptionNames()` | `Set<String>` | Các key của option bắt đầu bằng `--` |
| `containsOption("debug")` | `boolean` | Có option `--debug` hay không, dù không có giá trị |
| `getOptionValues("region")` | `List<String>` hoặc `null` | Tất cả giá trị của option đó; `null` khi option không xuất hiện, danh sách rỗng khi option có mặt nhưng không kèm giá trị |
| `getNonOptionArgs()` | `List<String>` | Các chuỗi positional, không bắt đầu như option CLI được nhận dạng |

Ví dụ dữ liệu:

~~~bash
java -jar app.jar --region=vn --region=sg --dry-run invoices.csv
~~~

Các kết quả quan trọng:
- `containsOption("region")` là `true`; `getOptionValues("region")` là `[vn, sg]`.
- `containsOption("dry-run")` là `true`; `getOptionValues("dry-run")` là danh sách rỗng.
- `getOptionValues("missing")` là `null`; phải kiểm tra null trước khi truy cập.
- `getNonOptionArgs()` là `[invoices.csv]`.
- `getSourceArgs()` giữ cả năm chuỗi sau tên JAR theo đúng thứ tự được đưa vào chương trình.

Không nên dùng `System.getProperty("region")` để lấy tùy tiện đối số CLI dạng `--region=vn`: Java system property dùng cú pháp JVM `-Dregion=vn` và được xử lý bằng nguồn khác. `--region=vn` thường trở thành Spring property trong `Environment`, còn `-Dregion=vn` phải đặt trước `-jar` để JVM nhận.

### ApplicationRunner và CommandLineRunner khác nhau

Sau khi context được refresh, Boot gọi những bean thuộc `ApplicationRunner` và `CommandLineRunner`. Chúng có cùng vai trò chạy công việc khởi tạo một lần, nhưng khác kiểu đối số đầu vào:

~~~java
@Bean
ApplicationRunner parsedRunner() {
    return args -> System.out.println(args.getNonOptionArgs());
}
~~~

~~~java
@Bean
CommandLineRunner rawRunner() {
    return args -> System.out.println(java.util.Arrays.toString(args));
}
~~~

Đặt những method `@Bean` trên trong một class `@Configuration` có import thích hợp, hoặc trong class có `@SpringBootApplication`; đây là các snippet riêng minh họa chữ ký API. Khi có nhiều runner, đừng dựa vào thứ tự ngẫu nhiên; dùng `@Order` hoặc `Ordered` nếu công việc thực sự cần thứ tự. Trong production, thao tác chậm ở runner sẽ trì hoãn thời điểm `ApplicationReadyEvent` và trạng thái readiness của Boot.

Có thể inject `ApplicationArguments` trực tiếp vào constructor của bean, không cần tự tạo lại từ `System.getenv` hay biến global. Tuy vậy, dùng `ApplicationRunner` thường rõ ràng hơn nếu công việc cần đợi các bean phụ thuộc hoàn tất.

### Khi vô hiệu hóa CLI property injection

~~~java
SpringApplication app = new SpringApplication(StartupDemoApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
~~~

Lúc này `ApplicationArguments` **vẫn chứa** các option và positional arguments, nhưng option CLI không tự được thêm vào `Environment` bằng cơ chế mặc định. Nếu truyền `--spring.profiles.active=dev` và đồng thời tắt CLI property injection, **đừng mặc định profile dev sẽ được chọn bởi chính option ấy**. Có thể cấu hình profile từ nguồn khác hoặc qua API Java. Đây là ví dụ rõ nhất cho thấy `ApplicationArguments` khác `Environment`.

## 4. Environment: tổng hợp nguồn và phân giải giá trị cuối cùng

Spring Framework định nghĩa `Environment` là điểm truy cập các property và thông tin profile. Spring Boot thêm nhiều nguồn cấu hình và cơ chế xử lý config data.

Các phương thức thường dùng:

~~~java
String name = environment.getProperty("spring.application.name", "unknown");
String mode = environment.getProperty("demo.mode");
boolean enabled = environment.getProperty("demo.enabled", Boolean.class, false);

String[] active = environment.getActiveProfiles();
String[] defaults = environment.getDefaultProfiles();
boolean isDev = environment.acceptsProfiles(
    org.springframework.core.env.Profiles.of("dev"));
~~~

- `getProperty(...)` giải quyết theo thứ tự `PropertySource` và có thể trả về `null` khi không tìm thấy nếu không có giá trị dự phòng.
- Bản typed `getProperty(key, Boolean.class, defaultValue)` hỗ trợ chuyển kiểu; cấu hình không hợp lệ có thể gây lỗi chuyển đổi.
- `getActiveProfiles()` chỉ phản ánh những profile được active tường minh/chương trình/cấu hình.
- `getDefaultProfiles()` cho biết profile fallback khi không có active profile; đừng suy ra `getActiveProfiles()` phải chứa `default`.
- `acceptsProfiles(Profiles.of("dev"))` kiểm tra điều kiện profile của Environment, có tính đến cơ chế default profile của Spring.

### Thứ tự ưu tiên phổ biến

Trong chương trình Spring Boot thông thường, từ thấp đến cao (chỉ trích những nguồn cần thiết nhất):

1. Default properties được đặt bởi `SpringApplication.setDefaultProperties(...)`.
2. Config data như `application.yaml`, `application-dev.yaml` và file ngoài JAR.
3. Biến môi trường của hệ điều hành, chẳng hạn `DEMO_MESSAGE`.
4. Java system properties từ `-Ddemo.message=...`.
5. Option dòng lệnh `--demo.message=...`, nếu CLI property injection được bật.

Thứ tự đầy đủ còn bao gồm `@PropertySource`, `SPRING_APPLICATION_JSON`, JNDI, servlet parameters, test properties, DevTools và các cơ chế mở rộng. Hãy tra đúng phiên bản Boot khi các nguồn đặc biệt cùng đặt một key. Không được kết luận “YAML luôn có ưu tiên thấp hơn một file ngoài JAR” nếu chưa xét vị trí config data, nhóm location, profile và nguồn cao hơn.

**Lưu ý thời điểm:** `@PropertySource` trên `@Configuration` được thêm khi context đang refresh, quá muộn đối với một số property đọc rất sớm như `logging.*` và `spring.main.*`. Vì vậy không dùng nó như cách đáng tin để thay đổi quá trình bootstrap ban đầu.

### Khác biệt giữa CLI, JVM và OS env

~~~bash
# Đối số ứng dụng: SpringApplication nhận --demo.message=CLI
java -jar app.jar --demo.message=CLI

# JVM system property: JVM nhận -D trước -jar
java -Ddemo.message=JVM -jar app.jar

# Trên shell hỗ trợ env trước lệnh, biến môi trường có thể là:
DEMO_MESSAGE=ENV java -jar app.jar
~~~

Ví dụ thứ ba dành cho shell Unix/Linux; trên PowerShell đặt `$env:DEMO_MESSAGE = 'ENV'` trước khi chạy. Phần lớn hệ điều hành không cho dấu chấm trong tên biến môi trường, nên relaxed binding hỗ trợ các dạng underscore tương ứng. Tuy nhiên việc map dấu gạch ngang/underscore trong **key do ứng dụng định nghĩa** cần tuân theo quy tắc đặt tên property canonical. Với nhiều property cùng nhóm, `@ConfigurationProperties` phù hợp hơn hàng loạt `@Value`.

## 5. Nạp config data và chọn profile

Boot tìm `application.properties`/`application.yaml` và các file cấu hình ở classpath, thư mục làm việc, thư mục `config/` bên ngoài, các location được khai báo thêm và các nguồn import nếu có. Tệp dành cho profile thường đặt tên như `application-dev.yaml` hoặc `application-prod.properties`. **Một file profile-specific chỉ được áp dụng khi profile tương ứng đang hoạt động**, ngoại trừ những tình huống được config/import xử lý có chủ đích.

Ví dụ:

**`src/main/resources/application.yaml`**

~~~yaml
spring:
  application:
    name: startup-demo

demo:
  message: "Xin chào mặc định"
~~~

**`src/main/resources/application-dev.yaml`**

~~~yaml
demo:
  message: "Xin chào từ dev"
~~~

Khi không có profile `dev`, `demo.message` từ file chung là `Xin chào mặc định`. Khi chạy với `--spring.profiles.active=dev`, file profile-specific được dùng để override key tương ứng, nên giá trị hiệu lực trong ví dụ là `Xin chào từ dev`. Nếu CLI bổ sung `--demo.message=CLI`, giá trị này lại ghi đè giá trị config data.

### Active profile và default profile

- `spring.profiles.active=dev` đặt profile `dev` đang hoạt động.
- Khi không có active profile, Spring sử dụng default profile, tên mặc định là `default`; có thể thay danh sách mặc định bằng `spring.profiles.default`.
- `application-default.yaml` có thể được áp dụng khi không có active profile.
- Giá trị `spring.profiles.default=none` là cách Boot hỗ trợ vô hiệu hóa fallback profile `default`.
- `@Profile("dev")` đánh dấu bean hoặc cấu hình chỉ nên có khi biểu thức profile phù hợp. `@Profile("!prod")` là điều kiện phủ định, không phải cách xác định tất cả môi trường đều tương đương.

**Ranh giới quan trọng:** `Environment.getActiveProfiles()` có thể trả về mảng rỗng dù Spring đang dùng default profile. Câu log “No active profile set, falling back to ... default” không có nghĩa `getActiveProfiles()` phải trả `["default"]`.

### Kết hợp profile bằng những cơ chế nào?

Có ba cơ chế thường gặp:

1. `spring.profiles.active`: chọn một hoặc nhiều profile, ví dụ `dev,metrics`.
2. `spring.profiles.include`: bổ sung profile lên danh sách active; nó không chỉ đơn giản là một giá trị thay thế của `active`.
3. `spring.profiles.group.production`: gắn một tên profile logic với các profile thành phần, ví dụ `production` kích hoạt thêm `proddb`, `prodmq`.

~~~yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
~~~

Khi `production` active, Boot có thể kích hoạt thêm hai profile `proddb` và `prodmq` để nạp các nhánh cấu hình tương ứng. Đừng nhầm tên nhóm profile với một profile tự tạo bằng Java: nhóm là cấu hình được Boot xử lý trong config data.

**Quy tắc đặt vị trí:** `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include` và `spring.profiles.group` phải nằm ở tài liệu cấu hình **không phụ thuộc profile**. Không đặt các key điều khiển profile này vào `application-dev.yaml` hoặc tài liệu YAML được kích hoạt bằng `spring.config.activate.on-profile`. Làm vậy có thể gây `InvalidConfigDataPropertyException` hoặc lỗi cấu hình liên quan.

### Nhiều profile cùng hoạt động

~~~bash
java -jar app.jar --spring.profiles.active=dev,metrics
~~~

Tệp `application-dev.yaml` và `application-metrics.yaml` có thể cùng được xét. Nếu chúng định nghĩa cùng property, thông thường profile đứng sau trong chuỗi có thể ghi đè profile trước **trong cùng nhóm config location**. Với nhiều thư mục hoặc cấu hình location groups phức tạp, độ ưu tiên thực còn phụ thuộc cách nạp; không suy ra kết quả chỉ từ thứ tự chữ trong tên file. Tương tự, `@Profile({"dev", "metrics"})` trên một bean thể hiện điều kiện **OR** giữa hai tên, không phải AND; nếu cần điều kiện phức hợp có thể dùng biểu thức profile hỗ trợ như `@Profile("dev & metrics")`.

## 6. Cách truyền cấu hình profile từ API SpringApplication

Có thể chọn bổ sung profile trước `run(...)`:

~~~java
package com.example.startup;

import org.springframework.boot.SpringApplication;

public final class AdditionalProfileLauncher {
    public static void main(String[] args) {
        SpringApplication app =
            new SpringApplication(StartupDemoApplication.class);
        app.setAdditionalProfiles("audit");
        app.run(args);
    }
}
~~~

Đây là một **launcher thay thế** dùng với class `StartupDemoApplication` ở ví dụ hoàn chỉnh bên dưới. `setAdditionalProfiles("audit")` thêm profile `audit` vào những profile đã chọn bằng cấu hình/CLI; không có nghĩa xóa các profile từ `spring.profiles.active`.

Với cấu hình mặc định ứng dụng:

~~~java
SpringApplication app = new SpringApplication(StartupDemoApplication.class);
app.setDefaultProperties(java.util.Map.of(
    "spring.application.name", "startup-demo",
    "demo.message", "Xin chào từ Java mặc định"));
app.run(args);
~~~

Default properties có độ ưu tiên thấp. Nếu `application.yaml` chứa `demo.message` thì giá trị YAML thông thường thắng; nếu CLI cung cấp `--demo.message=...` thì CLI thắng cả hai. Những snippet trên là lựa chọn khởi động riêng; khi triển khai hãy chọn **một** main launcher phù hợp.

### Khi nào cần can thiệp Environment sớm?

Nếu phải cung cấp một `PropertySource` bổ sung **trước lúc tạo bean**, Spring Boot có hook `EnvironmentPostProcessor` hoặc các cơ chế bootstrap/config data được hỗ trợ. Việc thêm property vào Environment trong constructor một `@Service`, `@PostConstruct` hay `ApplicationRunner` là **quá muộn** để chắc chắn ảnh hưởng tới:
- profile dùng để nạp config data ban đầu;
- điều kiện `@Profile` hoặc `@ConditionalOnProperty` đã được đánh giá;
- cấu hình sớm của logging, `spring.main.*` và khởi tạo ứng dụng.

`ApplicationContextInitializer` được gọi trước việc nạp bean definitions, nên có thể tùy biến context sớm, nhưng vẫn khác với cơ chế chọn profile và nạp config data ở pha Environment. Cần chọn hook theo **thời điểm dữ liệu phải xuất hiện**, tránh giả định cứ đặt property vào Environment lúc nào cũng có thể tái đánh giá toàn bộ cấu hình.

## 7. Ví dụ chạy được: xem cả ba thành phần trên cùng một ứng dụng

Tạo project Maven bằng Spring Initializr với Java 17+, nhóm `com.example`, artifact `startup-demo`, package `com.example.startup` và dependency **Spring Boot Starter** (starter nền tảng, không bắt buộc Web hay Actuator). Sử dụng phiên bản Spring Boot tương thích với Java trên máy, ví dụ dòng 3.5.x. Bốn file sau tạo một ứng dụng dòng lệnh hiển thị argument đã phân tích, property hiệu lực, profile active và sự có mặt của bean theo profile.

**`src/main/java/com/example/startup/StartupDemoApplication.java`**

~~~java
package com.example.startup;

import java.util.Arrays;
import java.util.List;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class StartupDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(StartupDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectStartup(
            Environment environment,
            ObjectProvider<DevOnlyMarker> devMarker) {
        return args -> {
            List<String> names = args.getOptionValues("demo.user");
            String user = (names == null || names.isEmpty())
                    ? "unknown" : names.get(0);

            System.out.println("user=" + user);
            System.out.println("inputFiles=" + args.getNonOptionArgs());
            System.out.println("activeProfiles="
                    + Arrays.toString(environment.getActiveProfiles()));
            System.out.println("message="
                    + environment.getProperty("demo.message", "missing"));
            System.out.println("devBeanPresent="
                    + (devMarker.getIfAvailable() != null));
            System.out.println("verboseFlag="
                    + args.containsOption("demo.verbose"));
        };
    }
}
~~~

**`src/main/java/com/example/startup/DevOnlyMarker.java`**

~~~java
package com.example.startup;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("dev")
public class DevOnlyMarker {
}
~~~

**`src/main/resources/application.yaml`**

~~~yaml
spring:
  application:
    name: startup-demo

demo:
  message: "Xin chào mặc định"
~~~

**`src/main/resources/application-dev.yaml`**

~~~yaml
demo:
  message: "Xin chào từ dev"
~~~

Giải thích: `ApplicationRunner` được gọi sau refresh và nhận `ApplicationArguments` ngay trong tham số lambda. `ObjectProvider<DevOnlyMarker>` cho phép kiểm tra bean tùy chọn mà không bắt buộc phải có bean ở các profile khác. Vì bean được chú thích `@Profile("dev")`, nó chỉ được tạo khi profile `dev` thỏa điều kiện. `Environment` cung cấp property cuối cùng và danh sách active profiles.

### Biên dịch và chạy

Trong thư mục Maven chứa `pom.xml` do Spring Initializr tạo:

~~~bash
mvn -q -DskipTests package
java -jar target/startup-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev \
  --demo.user=Lan \
  --demo.verbose \
  input.csv
~~~

Dấu `\` nối dòng là cú pháp shell Unix/Linux; có thể gõ toàn bộ lệnh `java -jar ...` trên **một dòng** ở PowerShell/cmd. Tên JAR minh họa phiên bản artifact mặc định; nếu đã sửa `version` hoặc tên artifact trong `pom.xml`, sử dụng tên JAR thực tế.

Khi các nguồn cấu hình chỉ gồm bốn file trên và đối số đúng như lệnh, các dòng do `inspectStartup` in ra là:

~~~text
user=Lan
inputFiles=[input.csv]
activeProfiles=[dev]
message=Xin chào từ dev
devBeanPresent=true
verboseFlag=true
~~~

Boot còn in những dòng log khởi động khác; bảng output trên chỉ trích **những dòng của runner**, không khẳng định toàn bộ stdout chỉ có sáu dòng này.

Giờ chạy mà không active dev:

~~~bash
java -jar target/startup-demo-0.0.1-SNAPSHOT.jar \
  --demo.user=Minh \
  report.csv
~~~

Những dòng của runner:

~~~text
user=Minh
inputFiles=[report.csv]
activeProfiles=[]
message=Xin chào mặc định
devBeanPresent=false
verboseFlag=false
~~~

**Giải thích giá trị rỗng:** `activeProfiles=[]` cho biết không có active profile tường minh; nếu không cấu hình khác thì default profile `default` vẫn được áp dụng theo cơ chế fallback. File `application-dev.yaml` và bean `DevOnlyMarker` vì thế không được kích hoạt.

Để chứng minh thứ tự ưu tiên, chạy thêm:

~~~bash
java -jar target/startup-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev \
  --demo.user=Lan \
  --demo.message="Ưu tiên CLI" \
  input.csv
~~~

Lần này dòng `message=...` của runner thành:

~~~text
message=Ưu tiên CLI
~~~

Mặc dù `application-dev.yaml` vẫn được xét, CLI property có ưu tiên cao hơn config data cho key này trong cấu hình Boot mặc định.

## 8. Thêm ví dụ về khác biệt thời điểm: event sớm và runner muộn

Khi cần quan sát một sự kiện sớm, bạn có thể tự đăng ký listener vào `SpringApplication` trước khi chạy. Đoạn sau là launcher độc lập sử dụng lại ứng dụng ở mục 7:

~~~java
package com.example.startup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;

public final class EventLauncher {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(StartupDemoApplication.class);

        app.addListeners(event -> {
            if (event instanceof ApplicationEnvironmentPreparedEvent) {
                System.out.println("EVENT=environment-prepared");
            }
        });

        app.run(args);
    }
}
~~~

`ApplicationEnvironmentPreparedEvent` được phát trước khi tạo `ApplicationContext`. Ví dụ chỉ in mốc sự kiện để tránh phụ thuộc thứ tự các listener nội bộ; không nên lấy giá trị profile tại listener bất kỳ rồi coi đó là snapshot cuối cùng của **toàn bộ** quá trình xử lý config data. Với `ApplicationRunner` trong ví dụ trước, ngược lại, config đã được xử lý và context đã refresh; đây là thời điểm thích hợp hơn để đọc property hiệu lực phục vụ công việc khi chạy.

Đây cũng là lý do không thể tạo một `@Component` lắng nghe sự kiện `ApplicationStartingEvent` rồi mặc định kỳ vọng Spring Boot gọi được nó từ trước khi context tồn tại. Nếu cần event cực sớm, đăng ký listener theo cơ chế `SpringApplication` hoặc metadata của Boot.

## 9. Các lỗi thường gặp và cách chẩn đoán

### “Đã truyền --spring.profiles.active=dev nhưng bean @Profile("dev") không có”

Kiểm tra argument **có thực sự đi vào `run(args)` không**. Một launcher gọi `SpringApplication.run(MyApp.class)` mà bỏ `args` sẽ làm mất các đối số dòng lệnh. Xem có gọi `setAddCommandLineProperties(false)` không, vì khi đó `ApplicationArguments` vẫn có option nhưng `Environment` không nhất thiết nhận property CLI. Sau đó kiểm tra giá trị profile cuối cùng từ những nguồn cao hơn, điều kiện package scan và nơi khai báo `@Profile`.

### “getActiveProfiles() trả mảng rỗng, vậy profile default có hoạt động không?”

Có thể **có**. Khi không có active profile, `Environment` sử dụng default profile. Hãy xem `getDefaultProfiles()` hoặc điều kiện `acceptsProfiles(Profiles.of("default"))` thay vì coi `getActiveProfiles()` là toàn bộ cơ chế profile.

### “getOptionValues(...) ném NullPointerException”

Phương thức trả về `null` nếu tên option không có. Nếu option chỉ là một flag `--dry-run`, kết quả là danh sách **rỗng**. Kiểm tra cả hai trường hợp trước khi gọi `get(0)`. Đừng giả định option không có và option không có giá trị là cùng trạng thái.

### “application-dev.yaml không được tải”

Kiểm tra tên profile, tên file, classpath/location, cấu hình `spring.config.name` hoặc `spring.config.location` và việc profile có active đúng thời điểm nạp config data hay không. `spring.config.location` **thay thế** các location mặc định, còn `spring.config.additional-location` **bổ sung** location; cả hai cần được cung cấp đủ sớm, thường từ CLI, system property hoặc OS env. Có thể dùng `optional:` nếu một location được phép không tồn tại; nếu không, Boot có thể dừng với `ConfigDataLocationNotFoundException`.

### “Đặt spring.profiles.active trong application-prod.yaml nhưng bị lỗi”

`spring.profiles.active` và các key điều khiển profile tương tự phải nằm trong tài liệu **không đặc thù profile**. Di chuyển chúng vào `application.yaml` hoặc chỉ định qua environment/CLI, rồi đặt các property riêng cho prod trong `application-prod.yaml`. Đừng kích hoạt profile trong chính document vốn chỉ được đọc khi profile đó đã active.

### “Thêm @PropertySource nhưng logging.* hoặc spring.main.* không đổi”

`@PropertySource` thường được xử lý khi refresh context, **muộn hơn** thời điểm Boot đọc một số thiết lập bootstrap. Đưa key cần sớm vào config data hoặc nguồn Environment thích hợp trước run. Đây là lỗi về **thời điểm** chứ không đơn thuần về tên property.

### “Chạy tại máy khác, cùng JAR nhưng property khác”

Kiểm tra biến môi trường, Java `-D`, CLI options, profile active, file bên ngoài JAR, thư mục làm việc và import config data. Boot cố ý hỗ trợ externalized configuration: cùng artifact có thể hoạt động khác nhau theo môi trường mà không phải lỗi.

### “Runner chạy trước khi app sẵn sàng”

Đúng: `ApplicationRunner`/`CommandLineRunner` chạy **sau `ApplicationStartedEvent` nhưng trước `ApplicationReadyEvent`**. Nếu runner thực hiện tác vụ khởi tạo lâu, readiness sẽ bị trì hoãn. Không chuyển công việc nặng vào listener chuẩn bị Environment vì mục đích đó; chọn thời điểm và cơ chế chạy nền/khởi tạo riêng phù hợp.

### “Mật khẩu hoặc token bị lộ khi log arguments”

`ApplicationArguments.getSourceArgs()` có thể chứa bí mật nếu operator truyền trên CLI. Không in toàn bộ `args`, `Environment` hay `PropertySources` vào production log. Sử dụng cơ chế secrets phù hợp và giới hạn xuất thông tin cấu hình/Actuator; thông điệp debug chỉ nên chứa những trường không nhạy cảm.

## 10. Bảng đối chiếu: thay đổi đầu vào tác động lên giai đoạn nào?

| Thao tác | ApplicationArguments | Environment / profiles | Tác động ở bước sau |
| --- | --- | --- | --- |
| Truyền `--demo.user=Lan` | Có option `demo.user` | CLI property được thêm theo mặc định | Bean có thể đọc `demo.user` khi tạo |
| Truyền `file.csv` | Có non-option `file.csv` | Không tự có property `file.csv` | Runner có thể xử lý đường dẫn |
| Đặt OS env `DEMO_MESSAGE=...` | Không xuất hiện nếu không có CLI option tương ứng | PropertySource từ OS environment | Giá trị cấu hình có thể bị override |
| Truyền `-Ddemo.message=JVM` | Không thuộc `ApplicationArguments` | Java system property | Ghi đè config data theo ưu tiên |
| Chạy `--spring.profiles.active=dev` | Có option CLI | Thường kích hoạt dev (nếu CLI property bật) | Nạp config dev và tạo `@Profile("dev")` bean |
| Dùng `setAdditionalProfiles("audit")` | Không thêm đối số nguồn | Bổ sung profile bằng Java API | Có thể nạp config/bean cho audit |
| Đặt `spring.profiles.group.production` | Không tự tạo option | Nhóm profile xử lý ở config data | Active thêm profile thành phần |
| Thêm property tại `ApplicationRunner` | Dữ liệu argument không đổi | Có thể thêm property runtime | Quá muộn để chắc chắn tái xét bean/profile đã chọn |
| Đặt `setAddCommandLineProperties(false)` | Vẫn có raw/parsed args | Không tự thêm CLI PropertySource | `--spring.profiles.active` không còn tự chi phối Environment theo cách mặc định |

## 11. Checklist triển khai

1. **Giữ nguyên `args`** khi gọi `SpringApplication.run(...)` nếu muốn chuyển CLI options vào ứng dụng.
2. **Chọn đúng API:** dùng `ApplicationArguments` cho raw/parsed startup args, `Environment` hoặc `@ConfigurationProperties` cho config hiệu lực; dùng `ApplicationRunner` khi cần xử lý sau refresh.
3. **Xác định profile sớm:** dùng `spring.profiles.active` qua config hợp lệ, CLI/OS env hoặc `SpringApplication.setAdditionalProfiles(...)` trước run.
4. **Đặt profile key đúng file:** không khai báo `spring.profiles.active`/`default`/`include`/`group` trong tài liệu chỉ dành cho profile.
5. **Nắm rõ thứ tự ưu tiên** và các nguồn override thực tế trước khi kết luận property không hoạt động.
6. **Chọn hook theo thời điểm:** bootstrap/config data cần nguồn sớm; `@PropertySource`, `@PostConstruct` và runner không thay thế được giai đoạn nạp config data.
7. **Chẩn đoán qua bằng chứng:** in có chọn lọc active/default profiles và những property không nhạy cảm, xem log config data khi cần; không dump secret.
8. **Kiểm thử hai chiều:** ít nhất chạy một lượt không có profile active và một lượt với `dev` để thấy khác biệt của file profile và bean `@Profile`.

### Câu hỏi tự kiểm tra

**1.** Truyền `--mode=fast report.csv` thì `getNonOptionArgs()` chứa gì? → `[report.csv]`, còn `mode` là option.

**2.** `--dry-run` khác `--dry-run=true` ra sao trong `getOptionValues("dry-run")`? → Trường hợp thứ nhất có list rỗng, trường hợp thứ hai có list chứa `"true"`.

**3.** Vì sao `getActiveProfiles()=[]` không chứng minh rằng profile mặc định không có hiệu lực? → Spring dùng `getDefaultProfiles()` để fallback khi không có active profile.

**4.** Cùng một key nằm trong YAML và CLI, nguồn nào thắng khi không tùy biến thứ tự? → CLI option property thường thắng YAML.

**5.** Có nên sửa profile từ `ApplicationRunner` để thay đổi những bean `@Profile` đã đăng ký? → Không; runner chạy sau refresh, quá muộn để tái thực hiện lựa chọn bean theo profile ban đầu.

**6.** Đâu là khác biệt giữa `ApplicationEnvironmentPreparedEvent` và `ApplicationReadyEvent`? → Sự kiện đầu ở pha thiết lập Environment trước context; sự kiện sau khi context đã refresh và runners hoàn tất thành công.

## 12. Tài liệu chính thức để đối chiếu theo phiên bản

- [Spring Boot — SpringApplication, Application Events, Application Arguments và Runners](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html)
- [Spring Boot — ApplicationArguments API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ApplicationArguments.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html)
- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/3.5/reference/features/profiles.html)
- [Spring Boot — Properties and Configuration](https://docs.spring.io/spring-boot/3.5/how-to/properties-and-configuration.html)
- [Spring Framework — Environment and Profiles](https://docs.spring.io/spring-framework/reference/core/beans/environment.html)

Tài liệu phiên bản khác có thể thay đổi thứ tự nội bộ, tên API bổ sung hoặc chính sách profile. Khi bảo trì ứng dụng, đối chiếu theo chính phiên bản Spring Boot và Spring Framework trong dependency tree của dự án.