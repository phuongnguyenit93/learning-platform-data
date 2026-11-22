# Kiểm tra profile thực sự có hiệu lực và tránh nhầm môi trường

Một ứng dụng Spring Boot có thể dùng cùng một file JAR tại máy lập trình, môi trường kiểm thử, staging và production. Code gần như không đổi, nhưng database, endpoint, credential, logging và các bean tích hợp có thể khác nhau. **Spring Profiles** giúp chọn các nhóm cấu hình và bean theo môi trường.

Tuy nhiên, thấy chuỗi **prod** trong application.yml hoặc thấy file **application-prod.yml** trên đĩa **chưa đủ để kết luận process đang thực sự chạy với profile prod**. Ngược lại, ứng dụng báo profile prod đang active cũng chưa chứng minh rằng mọi URL, datasource và bean đều đến từ cấu hình production.

Muốn tránh nhầm môi trường, phải kiểm tra ba lớp:

1. **Active profiles:** Spring Environment thực sự coi những profile nào là đang hoạt động?
2. **Effective configuration:** giá trị cuối cùng của các property quan trọng là gì, và được lấy từ nguồn nào?
3. **Effective beans:** những bean được bảo vệ bởi @Profile hoặc các điều kiện khác thực tế có được đăng ký đúng không?

Bài này hướng dẫn cách xác minh cả ba lớp, giải thích default profile, nhiều profile đồng thời, profile groups, Config Data, kiểm thử và cách xử lý khi môi trường triển khai không khớp kỳ vọng.

## 1. Profile là tên logic, không tự chứng minh môi trường

Các tên phổ biến:

- **local**: máy cá nhân.
- **dev**: môi trường phát triển dùng chung.
- **test**: môi trường hoặc tình huống kiểm thử.
- **staging**: môi trường tiền production.
- **prod**: môi trường production.

Tên là do dự án đặt. Spring không tự coi **production**, **prod**, **live** và **release** là từ đồng nghĩa. Nếu @Profile("prod") thì chỉ profile tên prod phù hợp, trừ khi dự án chủ động thêm cơ chế liên kết như profile group.

Spring Profiles cho phép:

- Nạp những tài liệu cấu hình có điều kiện theo profile.
- Bật/tắt các bean hoặc configuration class có @Profile.
- Bổ sung profile bằng include hoặc group.
- Tách một số quyết định triển khai theo môi trường.

Profile không tự:

- Xác nhận database hoặc URL thuộc đúng môi trường.
- Chứng minh secret đã được nạp và hợp lệ.
- Ngăn một bean gọi nhầm API production.
- Thay thế authentication, authorization hoặc xác thực cấu hình.
- Tự động refresh bean khi người vận hành sửa file YAML.

Một process có active profile prod nhưng vẫn có thể nhận URL **localhost** từ một biến môi trường ưu tiên cao. Vì vậy active profile là một **dữ kiện cần kiểm tra**, không phải chứng nhận cuối cùng.

## 2. Ba cấp bằng chứng cần đối chiếu

Ví dụ ứng dụng gửi email:

~~~text
Process đang chạy
        │
        ├── Spring Environment
        │      Active profiles: [prod]
        │
        ├── Cấu hình hiệu lực
        │      app.mail.host = smtp.production.internal
        │      app.mail.enabled = true
        │
        └── Bean thực tế
               MailSender = SmtpMailSender
~~~

Nếu kết quả lại là:

~~~text
Active profiles: [prod]
app.mail.host = localhost
MailSender = LoggingMailSender
~~~

thì cần tìm **vì sao** giá trị và bean không theo dự kiến: cấu hình bị ghi đè, điều kiện @Profile sai, có @ConditionalOnProperty khác, hoặc ứng dụng đã tự đăng ký bean thay thế.

Hãy dựa vào **process thật trong môi trường đích**, không chỉ đọc những file nằm trong source repository.

## 3. Kích hoạt profile bằng spring.profiles.active

Trong application.properties:

~~~properties
spring.profiles.active=dev
~~~

Hoặc trong application.yml:

~~~yaml
spring:
  profiles:
    active: dev
~~~

Khi Boot sử dụng giá trị này, dev được kích hoạt và các cấu hình dành cho dev có thể được xét.

### 3.1. Qua command line

~~~bash
java -jar app.jar --spring.profiles.active=staging
~~~

Với property source mặc định của Spring Boot, option dòng lệnh thường có độ ưu tiên cao hơn giá trị trong application.yml, do đó có thể ghi đè profile đã đặt trong file.

Nhiều profile:

~~~bash
java -jar app.jar --spring.profiles.active=prod,metrics
~~~

Lệnh này không chỉ chọn prod: metrics cũng được kích hoạt.

### 3.2. Qua environment variable

Tên biến thường dùng:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

Ví dụ Linux shell:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
java -jar app.jar
~~~

Trong PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar app.jar
~~~

Trong container, biến có thể đến từ Docker, Kubernetes Deployment, ConfigMap hoặc pipeline. **Biến ở terminal của developer không chứng minh biến trong process đang chạy trên cluster có cùng giá trị.** Kiểm tra chính deployment/runtime process cần chẩn đoán.

### 3.3. Qua JVM system property

~~~bash
java -Dspring.profiles.active=prod -jar app.jar
~~~

Phân biệt hai dạng:

~~~text
java -Dspring.profiles.active=prod -jar app.jar
     └── JVM system property trước -jar

java -jar app.jar --spring.profiles.active=prod
                  └── Spring Boot application argument
~~~

Nếu đặt **-Dspring.profiles.active=prod** sau tên JAR, JVM không xử lý nó như system property theo cú pháp trên; nó trở thành application argument.

### 3.4. Qua SpringApplication API

~~~java
SpringApplication app =
        new SpringApplication(DemoApplication.class);
app.setAdditionalProfiles("diagnostics");
app.run(args);
~~~

**setAdditionalProfiles** bổ sung profile trước khi chạy, không có nghĩa xoá các profile đến từ mọi nguồn khác. Đây là một lý do không nên chỉ đọc chuỗi spring.profiles.active để kết luận tập profile đang dùng.

## 4. Cách chính xác để đọc active profiles của context

Spring cung cấp **Environment**:

~~~java
String[] active = environment.getActiveProfiles();
String[] defaults = environment.getDefaultProfiles();
~~~

Ví dụ log khi khởi động:

~~~java
package com.example.demo.diagnostics;

import java.util.Arrays;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ProfileStartupLogger implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(ProfileStartupLogger.class);

    private final Environment environment;

    public ProfileStartupLogger(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        log.info("Active profiles: {}",
                Arrays.toString(environment.getActiveProfiles()));
        log.info("Default profiles: {}",
                Arrays.toString(environment.getDefaultProfiles()));
    }
}
~~~

ApplicationRunner chạy sau khi ApplicationContext refresh xong và trước ApplicationReadyEvent. Đây là lúc thuận tiện để ghi nhận trạng thái của process đã khởi động theo luồng thông thường.

Nếu startup bị lỗi trước runner, log này có thể không xuất hiện. Khi đó phải xem startup logs, command line, property sources và cấu hình của container.

### 4.1. Không đồng nhất getProperty và getActiveProfiles

Hai API khác nhau:

~~~java
String declared = environment.getProperty("spring.profiles.active");
String[] actual = environment.getActiveProfiles();
~~~

**declared** là giá trị của một property được resolve; **actual** là tập active profiles mà Environment đang biết. Include, groups, additional profiles và những thay đổi hợp lệ trong giai đoạn chuẩn bị Environment có thể khiến tập actual rộng hơn một chuỗi property duy nhất.

**Ưu tiên getActiveProfiles() khi mục đích là kiểm tra những profile nào thật sự active.** Sau đó kiểm tra property sources để truy vết tại sao.

### 4.2. Không log toàn bộ Environment hoặc secret

Hãy log tên profile, tên bean và một số giá trị cấu hình **đã được chọn lọc**. Không in toàn bộ environment variables, datasource password, API token hay cấu hình nhạy cảm vào startup log.

Đặc biệt trong production, log chẩn đoán thường được tập trung ở hệ thống lưu trữ dài hạn. Một lần in secret trong log có thể tạo rủi ro bảo mật lớn hơn giá trị debug thu được.

## 5. Active profiles và default profiles không giống nhau

Spring có khái niệm **default profile** dùng khi không có active profile tường minh. Thông thường tên là **default**.

Nếu getActiveProfiles() trả mảng rỗng, Spring vẫn có thể áp dụng **@Profile("default")** vì default profile phù hợp.

| Active profiles | Default profiles | Profile phù hợp trong trường hợp thông thường |
|---|---|---|
| Không có | default | default |
| dev | default | dev |
| prod | default | prod |
| prod,metrics | default | prod và metrics |

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("default")
public class DefaultOnlyConfiguration {

    @Bean
    LocalMessageGateway localMessageGateway() {
        return new LocalMessageGateway();
    }
}
~~~

Bean này thuộc profile mặc định, không có nghĩa luôn được dùng nếu prod active.

### 5.1. Có thể thay default profile

~~~yaml
spring:
  profiles:
    default: local
~~~

Khi không có active profile, Spring có thể dùng local như default. Nếu prod active, local không tự trở thành active chỉ vì được khai báo default.

Spring Boot cũng hỗ trợ **spring.profiles.default=none** để không dùng một tên default profile cụ thể.

Trong hệ thống nhiều môi trường, nên thiết lập profile đích **tường minh từ deployment**, không dựa vào default profile mà các process khác nhau có thể cấu hình khác nhau.

### 5.2. Tránh suy luận “mảng active rỗng = không có cấu hình”

Sai:

~~~java
if (environment.getActiveProfiles().length == 0) {
    // Kết luận không có profile nào có hiệu lực.
}
~~~

Kết luận trên bỏ qua default profiles. Nếu cần hỏi một biểu thức profile có match không, có thể dùng:

~~~java
boolean localMatches =
        environment.acceptsProfiles(
                org.springframework.core.env.Profiles.of("local"));
~~~

Phương thức acceptsProfiles với Profiles expression xét các active profiles hoặc default profiles theo quy tắc Spring. Nó phù hợp để hỏi **một điều kiện** có thỏa hay không, không thay thế việc log cả active và default khi chẩn đoán.

## 6. Profile-specific configuration: file tồn tại chưa phải đã có hiệu lực

Một dự án có thể có:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
├── application-staging.yml
└── application-prod.yml
~~~

Ví dụ application.yml:

~~~yaml
app:
  gateway:
    url: https://gateway.default.internal
  audit:
    enabled: false
~~~

application-dev.yml:

~~~yaml
app:
  gateway:
    url: http://localhost:8090
~~~

application-prod.yml:

~~~yaml
app:
  gateway:
    url: https://gateway.production.internal
  audit:
    enabled: true
~~~

Khi prod active, Spring Boot có thể nạp application-prod.yml để ghi đè một số key từ application.yml theo quy tắc ưu tiên Config Data.

Phải phân biệt:

- File tồn tại không có nghĩa nó đã được nạp.
- File được nạp không có nghĩa mọi key của nó thắng các nguồn khác.
- Profile prod active không có nghĩa file application-prod.yml nhất định tồn tại.
- Một property có giá trị production không chứng minh bean đã dùng property đó.

Nếu application-prod.yml thiếu, profile prod vẫn có thể active và ứng dụng dùng giá trị từ nguồn khác. Do đó cần kiểm tra giá trị thực tế.

### 6.1. Profile-specific document trong YAML

Ngoài file riêng, có thể dùng nhiều document:

~~~yaml
app:
  gateway:
    url: https://gateway.default.internal

---
spring:
  config:
    activate:
      on-profile: dev
app:
  gateway:
    url: http://localhost:8090

---
spring:
  config:
    activate:
      on-profile: prod
app:
  gateway:
    url: https://gateway.production.internal
~~~

**spring.config.activate.on-profile** là điều kiện áp dụng một document. Nó **không kích hoạt** profile được ghi trong đó.

Ví dụ on-profile: prod có nghĩa “chỉ dùng document này nếu prod phù hợp”, khác với spring.profiles.active=prod có nghĩa “đặt profile prod là active”.

### 6.2. Không kích hoạt profile từ document chỉ dành cho profile

Không làm:

~~~yaml
spring:
  config:
    activate:
      on-profile: staging
  profiles:
    active: prod
~~~

Các property điều khiển kích hoạt profile như **spring.profiles.active**, **spring.profiles.default**, **spring.profiles.include** và **spring.profiles.group** cần được đặt ở vị trí hợp lệ **không phải** document profile-specific hay document đã phụ thuộc on-profile.

Không nên thiết kế một document chỉ nạp khi staging active rồi để nó tự bật prod; điều đó tạo vòng phụ thuộc và bị quy tắc cấu hình Spring Boot hạn chế.

## 7. Nhiều profile có thể cùng active

~~~bash
java -jar app.jar --spring.profiles.active=dev,prod
~~~

Trong trường hợp này:

- @Profile("dev") có thể match.
- @Profile("prod") có thể match.
- Cả cấu hình profile-specific của dev và prod đều có thể được xét.
- Nếu hai nguồn cùng định nghĩa một key, quy tắc ưu tiên config data quyết định giá trị cuối cùng.

Spring không tự coi dev và prod là hai lựa chọn loại trừ nhau.

### 7.1. Thứ tự profile có thể làm thay đổi giá trị

Giả sử application-dev.yml và application-prod.yml cùng có **app.gateway.url**. Trong nhóm config data profile-specific có cùng cấp ưu tiên, **profile liệt kê sau có thể thắng** khi ghi đè cùng key:

~~~text
spring.profiles.active=dev,prod
spring.profiles.active=prod,dev
~~~

Đảo thứ tự có thể đảo giá trị nhận được. Nhưng property source ưu tiên cao hơn, chẳng hạn command-line properties, vẫn có thể ghi đè chúng.

Vì vậy, một quy trình kiểm tra đúng phải quan sát **cả thứ tự profile lẫn giá trị property sau khi tất cả nguồn được hợp nhất**.

### 7.2. Tránh đặt profile tên gần giống

~~~text
prod
production
live
release
~~~

Đây là những tên khác nhau. Hãy thống nhất naming convention ở source code, manifest, CI/CD và tài liệu vận hành.

## 8. Include và profile groups

Spring Boot có thể bổ sung active profiles qua include hoặc groups. Tập profile thực tế có thể rộng hơn tên được nhập từ command line.

### 8.1. spring.profiles.include

Ví dụ khai báo trong cấu hình gốc:

~~~yaml
spring:
  profiles:
    include:
      - common-observability
      - region-south
~~~

Các profile được include được bổ sung vào tập active profiles theo cơ chế Spring Boot. Một process chọn prod có thể còn có common-observability và region-south.

Đây là lý do **environment.getActiveProfiles()** là dữ liệu quan trọng hơn việc chỉ xem spring.profiles.active.

### 8.2. Profile groups

~~~yaml
spring:
  profiles:
    group:
      production:
        - prod-datasource
        - prod-observability
        - prod-security
~~~

Khi profile production được kích hoạt, Spring Boot có thể kích hoạt thêm các member profiles của group.

Profile groups hữu ích khi một tên môi trường đại diện cho nhiều mảnh cấu hình. Nhưng khi sự cố xảy ra, cần kiểm tra từng member vì có thể một profile được thêm vào một cách gián tiếp.

### 8.3. Đặt include/group ở nơi hợp lệ

Các property trên điều khiển việc chọn profile nên được khai báo tại tài liệu cấu hình không bị điều kiện hóa bởi một profile. Không nên đặt chúng trong application-prod.yml hoặc một YAML document có spring.config.activate.on-profile rồi trông chờ chúng tự bổ sung profile theo chuỗi.

### 8.4. Mỗi profile không đồng nghĩa một môi trường riêng

Một profile có thể biểu thị một chiều cấu hình như:

- cloud.
- metrics.
- region-south.
- debug-sql.

Vì vậy một ứng dụng production hợp lệ có thể có nhiều profile. Điều cần tránh là **các profile mâu thuẫn**, chẳng hạn local-mock cùng prod-real, hoặc những profile dùng chung key với giá trị không tương thích.

## 9. Kiểm tra @Profile có chọn đúng bean không

Spring Profiles ảnh hưởng cả cấu hình lẫn việc đăng ký bean.

Ví dụ interface:

~~~java
public interface MessageGateway {
    void send(String message);
}
~~~

Hai implementations:

~~~java
public class LoggingMessageGateway implements MessageGateway {
    @Override
    public void send(String message) {
        System.out.println("LOCAL: " + message);
    }
}
~~~

~~~java
public class RemoteMessageGateway implements MessageGateway {
    @Override
    public void send(String message) {
        // Gửi thông điệp đến dịch vụ ngoài.
    }
}
~~~

Configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class MessageGatewayConfiguration {

    @Bean
    @Profile("local")
    MessageGateway localMessageGateway() {
        return new LoggingMessageGateway();
    }

    @Bean
    @Profile("prod")
    MessageGateway remoteMessageGateway() {
        return new RemoteMessageGateway();
    }
}
~~~

Nếu local phù hợp, bean localMessageGateway có thể xuất hiện. Nếu prod phù hợp, bean remoteMessageGateway có thể xuất hiện. Tuy nhiên:

- Nếu **không profile nào phù hợp**, có thể không có MessageGateway bean; consumer bắt buộc inject theo type sẽ thất bại.
- Nếu **cả local và prod active**, cả hai @Bean methods có thể match, tạo nhiều MessageGateway candidates và gây ambiguity khi inject.

Đừng coi tên profile là cơ chế bảo đảm chỉ một implementation được tạo. Cần xác định những tổ hợp profile được phép, cùng quy tắc chọn bean.

### 9.1. @Profile trên configuration class

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("prod")
public class ProductionMessagingConfiguration {

    @Bean
    MessageGateway remoteMessageGateway() {
        return new RemoteMessageGateway();
    }

    @Bean
    RemoteMetrics remoteMetrics() {
        return new RemoteMetrics();
    }
}
~~~

Nếu prod không phù hợp, configuration class này không được áp dụng nên các bean trong class không được đăng ký qua nhánh đó. Điều kiện ở cấp class có phạm vi rộng hơn điều kiện trên riêng một @Bean method.

### 9.2. Danh sách profile và biểu thức

~~~java
@Profile({"dev", "staging"})
~~~

Điều kiện trên match nếu **dev OR staging** phù hợp.

~~~java
@Profile("prod & cloud")
~~~

Biểu thức yêu cầu **prod AND cloud**.

~~~java
@Profile("!prod")
~~~

Biểu thức yêu cầu **prod không phù hợp**. Nhưng **!prod không đồng nghĩa dev**: nó có thể match ở staging, test hoặc một deployment chưa được gán profile chính xác.

Nếu bean mock có thể ảnh hưởng tới dữ liệu thật, đừng bảo vệ nó bằng điều kiện phủ định quá rộng. Hãy chọn các profile cho phép một cách tường minh và có ràng buộc an toàn bổ sung.

### 9.3. Đọc bean registry để xác minh

Một ApplicationRunner có thể quan sát bean names:

~~~java
import java.util.Map;
import org.springframework.beans.factory.ListableBeanFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class GatewayInspector implements ApplicationRunner {
    private final ListableBeanFactory factory;

    public GatewayInspector(ListableBeanFactory factory) {
        this.factory = factory;
    }

    @Override
    public void run(ApplicationArguments args) {
        Map<String, MessageGateway> gateways =
                factory.getBeansOfType(MessageGateway.class);
        System.out.println("Gateway beans: " + gateways.keySet());
    }
}
~~~

Trong production, ưu tiên logger có kiểm soát. In tên bean và kiểu implementation an toàn hơn in toàn bộ object nếu toString của client vô tình chứa credential.

Kết luận về môi trường phải dựa vào **bean thật đã đăng ký**, không chỉ dựa trên annotation bạn nhìn thấy trong source.

## 10. Active profile và giá trị property hiệu lực là hai câu hỏi

Giả sử application-prod.yml chứa:

~~~yaml
app:
  payment:
    endpoint: https://payments.production.internal
~~~

Nhưng process chạy:

~~~bash
java -jar app.jar --spring.profiles.active=prod --app.payment.endpoint=http://localhost:9000
~~~

Với property source mặc định, argument app.payment.endpoint có thể ghi đè giá trị trong file application-prod.yml. Profile vẫn là prod nhưng endpoint hiệu lực là localhost.

Do đó, log sau chưa đủ chứng minh kết nối production:

~~~text
The following 1 profile is active: "prod"
~~~

### 10.1. Đọc property đã được resolve

~~~java
String endpoint =
        environment.getProperty("app.payment.endpoint");
~~~

Hoặc kiểm tra object đã bind:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        String endpoint,
        boolean sandboxEnabled) {
}
~~~

Khi type được đăng ký bằng @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties, có thể inject bean:

~~~java
@Component
public class PaymentConfigurationInspector
        implements ApplicationRunner {

    private final PaymentProperties properties;

    public PaymentConfigurationInspector(
            PaymentProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Payment endpoint: "
                + properties.endpoint());
        System.out.println("Sandbox enabled: "
                + properties.sandboxEnabled());
    }
}
~~~

Kiểm tra properties bean giúp xác nhận kết quả relaxed binding và conversion mà code tiêu thụ. Nhưng vẫn cần đối chiếu service cụ thể có sử dụng bean đó hay sử dụng cấu hình khác.

### 10.2. Property có thể đến từ nhiều nguồn

- Giá trị mặc định trong code hoặc trong property definition.
- application.yml hoặc application.properties.
- Profile-specific files hoặc YAML documents.
- Config data được import qua spring.config.import.
- Environment variables.
- JVM system properties.
- Command-line arguments.
- Property sources do hạ tầng hoặc test bổ sung.

Spring Boot có quy tắc ưu tiên từng nguồn. Không thể suy luận từ việc một dòng xuất hiện trong application-prod.yml rằng nó chính là giá trị có hiệu lực.

**Kiểm tra property cuối cùng và nguồn thắng trong process.**

## 11. Truy vết PropertySource đang cung cấp giá trị

Với **ConfigurableEnvironment**, có thể duyệt các PropertySource:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public class PropertySourceInspector {

    public static void showCandidateSources(
            ConfigurableEnvironment env,
            String key) {

        System.out.println("Effective value: "
                + env.getProperty(key));

        for (PropertySource<?> source : env.getPropertySources()) {
            if (source.containsProperty(key)) {
                System.out.println("Candidate source: "
                        + source.getName());
            }
        }
    }
}
~~~

Ví dụ:

~~~java
PropertySourceInspector.showCandidateSources(
        environment, "app.payment.endpoint");
~~~

Trong trường hợp thông thường, PropertySource được duyệt theo thứ tự ưu tiên và nguồn đầu tiên cung cấp giá trị phù hợp sẽ quyết định kết quả. Nhưng code trên chỉ là **quan sát nguồn ứng viên**, không phải trình truy vết origin hoàn chỉnh cho mọi dạng relaxed binding, placeholders hoặc property source đặc biệt.

Ví dụ APP_PAYMENT_ENDPOINT trong environment có thể được Binder ánh xạ tới app.payment.endpoint theo quy tắc tên biến môi trường. Việc gọi containsProperty trên một nguồn riêng lẻ không tự chứng minh toàn bộ quá trình binding của Boot.

Nếu cần xác định origin chính xác, kết hợp Effective Environment, ConfigurationProperties bean, Actuator và logging của Config Data.

### 11.1. Phân biệt ba loại lỗi

| Hiện tượng | Hướng chẩn đoán |
|---|---|
| Profile không nằm trong getActiveProfiles() | Kiểm tra lệnh chạy, environment, include và groups. |
| Profile đúng nhưng property sai | Kiểm tra Config Data, property source ưu tiên cao hơn, import và prefix. |
| Property đúng nhưng bean sai | Kiểm tra @Profile, component scan, bean conditions, @Primary/@Qualifier và auto-configuration. |

### 11.2. Không log secret

Đối với các key như datasource password, API token hoặc private key, không dùng ví dụ debug để in giá trị ra log.

Có thể kiểm tra **sự tồn tại** một property ở mức không nhạy cảm:

~~~java
boolean configured =
        environment.containsProperty("app.payment.api-key");
~~~

Nhưng sự tồn tại không chứng minh credential còn hiệu lực. Nếu cần kiểm tra kết nối, dùng health check hoặc kiểm thử chức năng được thiết kế an toàn.

## 12. Dùng Spring Boot Actuator để quan sát

Khi có Actuator và endpoint đã được bật/expose, các endpoint sau hữu ích:

| Endpoint | Mục đích |
|---|---|
| **/actuator/env** | Quan sát active profiles và các property sources/origin được hỗ trợ. |
| **/actuator/configprops** | Quan sát configuration properties beans và dữ liệu binding theo cơ chế Actuator. |
| **/actuator/beans** | Xem bean đang có trong ApplicationContext. |
| **/actuator/conditions** | Xem Condition Evaluation Report của auto-configuration. |
| **/actuator/health** | Xem health theo các contributor đã cấu hình. |

Ví dụ minh họa cho **môi trường quản trị có kiểm soát truy cập**:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,env,configprops,beans,conditions
~~~

**Không nên expose các endpoint nhạy cảm này công khai trên production.** Cần cấu hình xác thực, phân quyền, redaction và mạng quản trị phù hợp. Ngay cả khi Actuator che một số giá trị, metadata cũng có thể tiết lộ cấu trúc hạ tầng.

### 12.1. /actuator/env

Dùng để xem tập active profiles và thông tin về giá trị/nguồn property khi được hỗ trợ. Nếu hai nguồn cùng định nghĩa một key, cần xác nhận **nguồn thực sự thắng**, không chỉ thấy key xuất hiện ở một source.

### 12.2. /actuator/configprops

Giúp quan sát việc binding của @ConfigurationProperties. Nếu YAML có key nhưng properties bean vẫn dùng default, cần kiểm tra prefix, tên field, conversion và registration.

### 12.3. /actuator/conditions và @Profile

Endpoint conditions hữu ích cho auto-configuration khi @ConditionalOnClass, @ConditionalOnBean hoặc @ConditionalOnProperty match/không match.

Tuy nhiên, **không giả định báo cáo này giải thích đầy đủ mọi điều kiện @Profile trong source**. Để biết một bean profile-specific có tồn tại không, đối chiếu active profiles với bean registry hoặc /actuator/beans.

## 13. Kiểm tra Config Data qua startup log

Spring Boot thường ghi profile đang active khi khởi động. Ví dụ:

~~~text
The following 1 profile is active: "prod"
~~~

Hoặc khi chỉ có default profile:

~~~text
No active profile set, falling back to 1 default profile: "default"
~~~

Câu chữ có thể khác theo phiên bản. Nếu startup thất bại trước runner, bạn có thể không thấy log tự viết của ApplicationRunner; hãy kiểm tra log của chính Spring Boot và runtime environment.

### 13.1. Trace quá trình load cấu hình

Khi cần tìm file nào được xử lý:

~~~properties
logging.level.org.springframework.boot.context.config=TRACE
~~~

Hoặc tạm kích hoạt lúc khởi động:

~~~bash
java -jar app.jar --logging.level.org.springframework.boot.context.config=TRACE
~~~

TRACE có thể tạo log rất dài, nên chỉ dùng khi chẩn đoán. Không giữ TRACE lâu dài trong production nếu không có nhu cầu và quản lý log phù hợp.

### 13.2. --debug không chứng minh mọi profile file đã thắng

~~~bash
java -jar app.jar --debug
~~~

Chế độ debug có thể hiển thị Condition Evaluation Report và thông tin startup. Nhưng nó không thay thế việc đọc giá trị property cuối và origin của key quan trọng.

## 14. Cấu hình ngoài JAR có thể thay đổi kết quả

Ứng dụng có thể nạp cấu hình từ:

- Những đường dẫn tìm kiếm mặc định.
- File profile-specific.
- spring.config.location hoặc spring.config.additional-location.
- spring.config.import.
- Biến môi trường, system properties và command line.

Ví dụ:

~~~bash
java -jar app.jar --spring.config.additional-location=file:/etc/my-app/
~~~

Nếu có file cấu hình dưới vị trí được bổ sung, Boot có thể sử dụng nó theo quy tắc Config Data. Đừng chỉ đọc application-prod.yml trong JAR khi deployment còn mount cấu hình bên ngoài.

### 14.1. location và additional-location khác nhau

Về ý định:

- **spring.config.location** lựa chọn những vị trí cấu hình theo cách thay thế các vị trí mặc định của Config Data.
- **spring.config.additional-location** thêm vị trí bên cạnh các vị trí mặc định.

Nhầm hai lựa chọn này có thể khiến một file trong JAR không còn được nạp như bạn kỳ vọng. Khi xử lý cần xem cả thứ tự vị trí, cách nhóm location và giá trị cuối.

### 14.2. Config import cũng cần được kiểm tra

~~~yaml
spring:
  config:
    import: optional:file:/etc/my-app/extra.yml
~~~

Đây là ví dụ import file cấu hình ngoài. Khi file tồn tại, nó có thể bổ sung hoặc ghi đè property theo quy tắc Config Data. **optional:** cho phép bỏ qua vị trí không có theo cơ chế hỗ trợ.

Nếu một property bất ngờ đổi giá trị, hãy kiểm tra config imports chứ không chỉ profile-specific files.

## 15. Xác minh đúng process trong container hoặc cluster

Khi ứng dụng chạy bằng Docker/Kubernetes, cấu hình mà developer nhìn trong repository có thể khác môi trường của process thật.

~~~text
Repository chứa application-prod.yml
                │
                ▼
Build image và triển khai
                │
                ▼
Deployment gắn env, ConfigMap, Secret, volume
                │
                ▼
JVM nhận args và system properties
                │
                ▼
Spring Boot tạo Environment
                │
                ▼
Active profiles / Effective values / Beans thực tế
~~~

Một file manifest trên Git chưa chứng minh deployment đã được rollout. Có thể có pod cũ, config mount khác, image digest khác hoặc nhiều replica đang chạy hai phiên bản.

Quy trình quan sát:

1. Xác định instance đang nhận request.
2. Kiểm tra version/image digest và lệnh startup của instance đó.
3. Xác nhận environment variables được truyền vào process, nhất là SPRING_PROFILES_ACTIVE.
4. Kiểm tra đường dẫn config volume và file không nhạy cảm được mount.
5. Đọc startup logs của đúng instance.
6. Truy vấn diagnostics nội bộ được bảo vệ để xác minh active profiles và effective values.
7. Nếu có nhiều replica, đối chiếu kết quả trên nhiều instance, không chỉ một pod.

Ví dụ lệnh tham khảo trong Kubernetes:

~~~bash
kubectl -n demo describe deployment demo-api
kubectl -n demo logs deployment/demo-api
~~~

Tên namespace và workload chỉ là minh họa. Không chia sẻ output chứa token, password hoặc giá trị Secret.

### 15.1. Lỗi chỉ xảy ra ở một số request

Có thể có:

~~~text
pod-a: active = [prod], payment endpoint = production
pod-b: active = [prod], payment endpoint = staging
pod-c: active = [prod], payment endpoint = production
~~~

Vấn đề không nằm ở tên profile, mà ở sự khác biệt cấu hình thực tế giữa các replica. Hãy kiểm tra rollout, cấu hình mount, thời điểm restart và những property sources của từng process.

## 16. Kiểm thử profile bằng @ActiveProfiles

Trong Spring Test, annotation **@ActiveProfiles** cho phép chỉ định profile cho test ApplicationContext.

Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class TestProfileIntegrationTests {

    @Autowired
    Environment environment;

    @Test
    void runsWithExpectedProfile() {
        assertThat(environment.getActiveProfiles())
                .contains("test");
    }
}
~~~

Ở test này, Spring Test chuẩn bị context với test profile. Nhưng test chỉ xác minh một phần: profile test được bật. Nó chưa chứng minh database test hay bean mock đã được chọn.

Nếu muốn chứng minh điều đó, cần kiểm tra **giá trị cấu hình và bean**:

~~~java
@SpringBootTest(properties = {
        "app.mail.host=smtp.test.internal"
})
@ActiveProfiles("test")
class MailEnvironmentIntegrationTests {

    @Autowired Environment environment;
    @Autowired MailSender sender;

    @Test
    void usesTestConfiguration() {
        assertThat(environment.getActiveProfiles())
                .contains("test");
        assertThat(environment.getProperty("app.mail.host"))
                .isEqualTo("smtp.test.internal");
        assertThat(sender).isInstanceOf(FakeMailSender.class);
    }
}
~~~

Trong ví dụ, MailSender/FakeMailSender là các kiểu minh họa được test application đăng ký. Nếu FakeMailSender không tồn tại trong context test, assertion sẽ fail. Kết quả như vậy hữu ích vì test kiểm tra **wiring thật**, không chỉ tên profile.

### 16.1. @ActiveProfiles không nhất thiết đại diện cho production

Một test có @ActiveProfiles("test") chỉ cho biết cách **test context** được tạo. Nó không chứng minh process production chạy với cùng profile hoặc cùng property sources.

Ngoài ra, @SpringBootTest có thể kích hoạt những auto-configuration, runner hoặc client ngoài không mong muốn. Hãy dùng mocks/stubs hoặc test configuration phù hợp để bảo đảm test không kết nối database hoặc gửi request tới production.

### 16.2. Nếu test có nhiều profile

~~~java
@ActiveProfiles({"test", "cloud"})
~~~

Test sử dụng cả test và cloud. Các bean có điều kiện trên cloud cũng có thể được đăng ký. Không nên nghĩ rằng chỉ vì tên test xuất hiện thì tất cả cấu hình khác đều bị tắt.

Nếu muốn tránh thừa hưởng profile từ test class cha hoặc context khác, cần hiểu quy tắc kế thừa của Spring Test và cấu hình @ActiveProfiles phù hợp với cấu trúc test class.

## 17. Kiểm thử chọn bean bằng ApplicationContextRunner

Với phần lớn cấu hình có @Profile, không cần khởi động web server hoặc toàn bộ ứng dụng. **ApplicationContextRunner** có thể tạo một context nhỏ, chủ động thiết lập active profiles và kiểm tra bean registry.

Giả sử configuration class từ mục 9 có hai MessageGateway beans cho local và prod. Có thể kiểm thử:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class MessageGatewayProfileTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            MessageGatewayConfiguration.class);

    @Test
    void selectsLocalGateway() {
        runner.withInitializer(context ->
                    context.getEnvironment()
                            .setActiveProfiles("local"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasBean("localMessageGateway");
                    assertThat(context)
                            .doesNotHaveBean("remoteMessageGateway");
                });
    }

    @Test
    void selectsProductionGateway() {
        runner.withInitializer(context ->
                    context.getEnvironment()
                            .setActiveProfiles("prod"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasBean("remoteMessageGateway");
                    assertThat(context)
                            .doesNotHaveBean("localMessageGateway");
                });
    }
}
~~~

Đây là ví dụ minh họa cách chủ động đặt active profiles **trước khi configuration được xử lý** trong context runner.

Không cần chạy service thật hoặc kết nối API ngoài để kiểm tra điều kiện đăng ký bean. Nếu bean có side effect khi khởi tạo, nên thay nó bằng implementation test hoặc thiết kế test configuration tách biệt.

### 17.1. Test tình huống không active profile

Với hai bean chỉ dành cho local và prod, một context không có các profile này có thể không có MessageGateway nào.

~~~java
@Test
void registersNoGatewayWithoutMatchingProfile() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    MessageGatewayConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context)
                        .doesNotHaveBean(MessageGateway.class);
            });
}
~~~

Test này có ích để xác định bạn muốn **fail-fast**, tạo fallback hay yêu cầu người vận hành chọn một profile. Nó không có nghĩa thiếu MessageGateway luôn là thiết kế tốt; ứng dụng thực tế có thể cần service này và nên thất bại rõ ràng khi cấu hình sai.

### 17.2. Test sự kết hợp profile mâu thuẫn

Nếu cho phép local và prod cùng active:

~~~java
@Test
void revealsConflictingGatewayCandidates() {
    runner.withInitializer(context ->
                    context.getEnvironment()
                            .setActiveProfiles("local", "prod"))
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context.getBeansOfType(
                        MessageGateway.class)).hasSize(2);
            });
}
~~~

Test trên chỉ minh họa việc **hai definitions cùng phù hợp** trong một context không có consumer bắt buộc chỉ một instance. Trong ứng dụng thật, một consumer inject MessageGateway không có qualifier có thể khiến context thất bại.

Từ phát hiện này, nhóm có thể thiết kế rule từ chối một tổ hợp profile không hợp lệ hoặc chuyển sang lựa chọn bean theo property/qualifier rõ ràng.

## 18. Đừng nhầm Spring Profile với build profile

Spring profile được quyết định bởi Spring Environment khi ứng dụng chạy. Một số công cụ build cũng có khái niệm profile hoặc project properties, nhưng **chúng không tự tương đương** với Spring active profiles.

### 18.1. Maven build profile

Ví dụ:

~~~bash
mvn -Pproduction package
~~~

Maven profile có thể tác động tới dependency, plugin hoặc quá trình build. Nhưng nếu build không được cấu hình đặc biệt để truyền một giá trị vào runtime, **lệnh này không chứng minh Spring Boot sẽ khởi động với spring.profiles.active=prod**.

Khi ứng dụng đã build xong, muốn chạy profile prod vẫn nên khai báo tường minh:

~~~bash
java -jar target/app.jar --spring.profiles.active=prod
~~~

### 18.2. Gradle project property

Ví dụ:

~~~bash
./gradlew build -Penv=prod
~~~

Trong Gradle, -Penv=prod là project property của build. Nó không tự biến thành SPRING_PROFILES_ACTIVE hoặc một application argument của Spring Boot.

Nếu build task được cấu hình để chuyển giá trị đó, hãy kiểm tra cụ thể cách chuyển và kết quả process. Nếu không có cấu hình tương ứng, đừng suy ra Spring active profile từ Gradle property.

### 18.3. IDE run configuration

IDE có thể chạy ứng dụng với:

- Program arguments.
- JVM options.
- Environment variables.
- Một ô lựa chọn profile trong giao diện.

Đây là **cấu hình của từng run configuration**, không nhất thiết trùng với lệnh chạy của service trên server, Docker hoặc pipeline.

Khi debug khác biệt giữa máy local và production, hãy so sánh cách IDE truyền profile với cách process production nhận profile.

## 19. Phòng tránh nhầm môi trường bằng fail-fast

Trong một ứng dụng quan trọng, phát hiện cấu hình sai ngay khi khởi động thường an toàn hơn là để process báo ready rồi gọi nhầm hệ thống ngoài.

Ví dụ ứng dụng có property biểu diễn môi trường triển khai do hạ tầng cung cấp:

~~~yaml
app:
  deployment-environment: staging
~~~

Nếu deployment pipeline cung cấp một marker độc lập và đáng tin cậy, có thể đối chiếu nó với profile hiện tại.

### 19.1. Ví dụ kiểm tra marker và active profile

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.stereotype.Component;

@Component
public class EnvironmentSafetyGuard
        implements ApplicationRunner {

    private final Environment environment;

    public EnvironmentSafetyGuard(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String target = environment.getProperty(
                "app.deployment-environment", "unknown");

        boolean isProductionDeployment =
                "production".equalsIgnoreCase(target);

        boolean isProdProfile =
                environment.acceptsProfiles(Profiles.of("prod"));

        if (isProductionDeployment != isProdProfile) {
            throw new IllegalStateException(
                    "Deployment environment và Spring profile "
                    + "không nhất quán");
        }
    }
}
~~~

Ví dụ này minh họa một **invariant**, không phải một cơ chế xác minh production hoàn chỉnh. Marker chỉ có giá trị khi được cấp phát qua nguồn tin cậy và không thể dễ dàng bị ghi đè cùng lúc với Spring profile. Nếu cả hai cùng đến từ một nguồn cấu hình sai, chúng có thể sai giống nhau và phép đối chiếu vẫn pass.

Vì vậy, khi mức độ rủi ro cao, cần đối chiếu thêm:

- Database host và database/schema identity.
- Endpoint của hệ thống thanh toán, email hoặc messaging.
- ID của cloud account/project/namespace được cấp từ hạ tầng.
- Feature flags quan trọng.
- Certificate hoặc cơ chế authentication phù hợp.

Không in secret vào exception hoặc log để minh chứng.

### 19.2. Fail-fast cho cấu hình bắt buộc

Một kiểu @ConfigurationProperties có thể khai báo validation:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.payment")
public record PaymentSettings(
        @NotBlank String endpoint,
        @NotBlank String merchantId) {
}
~~~

Khi được đăng ký và có validation provider phù hợp, việc thiếu một giá trị bắt buộc có thể khiến startup thất bại thay vì chạy với cấu hình rỗng.

Validation không chứng minh endpoint thuộc đúng môi trường, nhưng nó loại bỏ một lớp lỗi cấu hình cơ bản.

### 19.3. Không dùng profile như cơ chế bảo mật duy nhất

Đừng tin rằng một endpoint destructive, truy cập debug hoặc thao tác dữ liệu sẽ an toàn chỉ vì được gắn @Profile("dev") hoặc @Profile("!prod").

Một deployment cấu hình sai có thể bật profile đó ở môi trường không mong muốn. Những hành động nguy hiểm vẫn cần:

- Authentication/authorization.
- Quyền hạn hạn chế ở database/cloud account.
- Cấu hình feature flag có chính sách rõ ràng.
- Điều kiện vận hành, audit và các giới hạn bổ sung.

Profile là công cụ **chọn cấu hình**, không phải ranh giới an ninh đủ mạnh.

## 20. Khi nào nên dùng profile, khi nào dùng property?

| Nhu cầu | Cách thường phù hợp |
|---|---|
| Dùng các nhóm cấu hình ổn định khác nhau giữa dev và prod | Spring Profiles. |
| Chọn giữa bean mock local và client thật | @Profile nếu có danh sách môi trường rõ ràng, kết hợp kiểm tra an toàn. |
| Bật hoặc tắt một tính năng độc lập với môi trường | @ConditionalOnProperty hoặc feature flag phù hợp. |
| Điều chỉnh timeout, batch size, endpoint | @ConfigurationProperties hoặc Environment, từ property sources phù hợp. |
| Có nhiều provider trên cùng một môi trường | Điều kiện bean/property, qualifier và cấu hình lựa chọn provider tường minh. |
| Muốn thay đổi tính năng khi ứng dụng đang chạy | Cơ chế dynamic config/feature flag có quản lý; profile thông thường không tự reload context. |

Ví dụ **không nên** tạo profile riêng cho mọi tính năng:

~~~text
prod,feature-a-on,feature-b-off,feature-c-on,debug-metrics
~~~

Tổ hợp profile có thể tăng nhanh và khó dự đoán. Nếu một tính năng có thể bật/tắt ở mọi môi trường, property riêng như app.feature-a.enabled rõ nghĩa hơn.

### 20.1. Đổi profile khi process đang chạy

Việc thay spring.profiles.active trong một file YAML sau khi ApplicationContext đã refresh **không tự động** làm Spring unregister bean cũ, đăng ký bean mới và bind lại toàn bộ cấu hình.

Thông thường cần restart/redeploy hoặc một cơ chế refresh riêng được thiết kế cẩn trọng. Đừng xây điều kiện nghiệp vụ dựa trên giả định rằng đổi file đồng nghĩa đổi active profile tức thời.

## 21. Quy trình điều tra khi nghi ứng dụng chạy nhầm môi trường

Một quy trình có thể áp dụng cho sự cố thực tế:

**Bước 1 — Xác định instance đang phục vụ:** ghi nhận deployment, namespace, pod, image version, thời điểm khởi động. Không dùng nhầm log của máy developer.

**Bước 2 — Đọc active/default profiles:** dùng Environment.getActiveProfiles(), getDefaultProfiles() hoặc endpoint quản trị được bảo vệ. Ghi nhận **toàn bộ** danh sách.

**Bước 3 — Truy vết nguồn kích hoạt:** kiểm tra command line, -D, SPRING_PROFILES_ACTIVE, application.yml, include/groups và cơ chế startup do code bổ sung.

**Bước 4 — Xác minh Config Data:** xem file profile-specific, YAML documents có on-profile, config imports, locations và file được mount.

**Bước 5 — Đọc effective properties:** kiểm tra endpoint, database host/schema, chế độ sandbox, feature flags và các thông số thật sự quyết định hành vi.

**Bước 6 — Kiểm tra bean registry:** xác nhận bean mock/real, các implementations cùng kiểu, @Profile và auto-configuration conditions.

**Bước 7 — Xác minh tài nguyên bên ngoài:** ở mức an toàn, kiểm tra kết nối và danh tính của hệ thống đích, không chỉ DNS hostname trong config.

**Bước 8 — So sánh các replica:** đặc biệt khi lỗi không ổn định hoặc chỉ xảy ra với một phần traffic.

**Bước 9 — Thiết lập phòng ngừa:** thêm validation, fail-fast, test profile matrix, startup diagnostics không lộ secret và quy trình rollout nhất quán.

Các bước này không yêu cầu thay source code ngay từ đầu. Phần lớn sự cố nhầm profile có thể được thu hẹp bằng quan sát **đúng process và đúng giá trị hiệu lực**.

## 22. Ví dụ điều tra: prod profile nhưng gửi tới staging

Giả sử một dịch vụ thanh toán có cấu hình dự định:

~~~yaml
# application-prod.yml
app:
  payment:
    endpoint: https://payments.production.internal
    sandbox-enabled: false
~~~

Nhóm vận hành thấy log:

~~~text
Active profiles: [prod]
~~~

Nhưng request lại đi tới staging.

Không nên kết luận “@Profile hoạt động sai” ngay. Hãy kiểm tra:

1. Effective app.payment.endpoint trong process có phải endpoint production không?
2. Có environment variable APP_PAYMENT_ENDPOINT ghi đè không?
3. Lệnh startup có --app.payment.endpoint từ pipeline không?
4. Có config import hoặc additional location ngoài JAR không?
5. Payment client có được tạo từ đúng @ConfigurationProperties bean không?
6. Có một PaymentClient bean custom nhường chỗ auto-configuration mặc định không?
7. Có proxy, service discovery hoặc network routing chuyển request sang một nơi khác không?

Nếu Environment trả endpoint staging, lỗi nằm ở **config resolution**. Nếu Environment trả production nhưng client lại dùng staging, cần kiểm tra **bean construction hoặc implementation**. Nếu client dùng endpoint production nhưng request tới staging, cần kiểm tra **network/routing và dịch vụ đích**.

Phân loại như vậy giúp tránh sửa sai tầng và hạn chế rủi ro khi thao tác trên production.

## 23. Những lỗi thường gặp

### 23.1. Có application-prod.yml nên tưởng prod đã active

**Vấn đề:** file được đóng gói nhưng process không được kích hoạt prod.

**Xử lý:** xác minh getActiveProfiles() và nguồn kích hoạt profile; file tồn tại không phải bằng chứng.

### 23.2. SPRING_PROFILES_ACTIVE đúng ở local nhưng sai trong container

**Vấn đề:** environment variables được truyền theo từng process; terminal local không đại diện cho pod.

**Xử lý:** đọc cấu hình workload và log của process đích, không dựa vào terminal developer.

### 23.3. Active profile đúng nhưng endpoint vẫn là local

**Vấn đề:** property source khác ghi đè, import config hoặc giá trị mặc định của bean.

**Xử lý:** xem effective value và origin; đối chiếu object @ConfigurationProperties đã bind.

### 23.4. @Profile("prod") không match khi deployment dùng production

**Vấn đề:** prod và production là hai tên khác nhau.

**Xử lý:** thống nhất naming convention hoặc định nghĩa profile group rõ ràng.

### 23.5. @Profile("!prod") vô tình bật mock ở staging

**Vấn đề:** phủ định prod không có nghĩa chỉ dành cho dev.

**Xử lý:** dùng danh sách profile cho phép, hạn chế quyền thực thi và xác minh loại bean khi startup.

### 23.6. Cả dev và prod cùng active

**Vấn đề:** cả file và bean theo hai profile đều có thể tham gia; xảy ra ghi đè cấu hình hoặc nhiều bean candidate.

**Xử lý:** kiểm tra include/group, runtime args, thứ tự profile, quy định tổ hợp hợp lệ và fail-fast nếu mâu thuẫn.

### 23.7. Chỉ có default profile nhưng nghĩ không profile nào hoạt động

**Vấn đề:** getActiveProfiles() rỗng nhưng getDefaultProfiles() vẫn có default hoặc một tên khác.

**Xử lý:** quan sát cả active và default; dùng acceptsProfiles nếu cần kiểm tra biểu thức cụ thể.

### 23.8. Đặt spring.profiles.active trong YAML document có on-profile

**Vấn đề:** nhầm điều kiện áp dụng document với kích hoạt profile; Spring Boot giới hạn cấu hình profile activation trong các document profile-specific.

**Xử lý:** đưa profile activation về cấu hình gốc hoặc deployment.

### 23.9. Lẫn Maven/Gradle profile với Spring profile

**Vấn đề:** -P của build tool không tự trở thành spring.profiles.active trong process chạy.

**Xử lý:** xác nhận lệnh runtime và Environment thực tế.

### 23.10. Test dùng @ActiveProfiles("test") nhưng gọi nhầm production

**Vấn đề:** profile test có thể active nhưng một endpoint bị ghi đè từ nguồn khác hoặc service dùng client custom.

**Xử lý:** kiểm tra effective URL, bean implementation và quyền truy cập mạng; không chỉ assert tên profile.

### 23.11. Đổi config file nhưng profile trong process không đổi

**Vấn đề:** Config Data và các bean đã được xử lý lúc startup; sửa file không tự rebuild context.

**Xử lý:** restart/redeploy có kiểm soát hoặc dùng cơ chế refresh chuyên biệt khi thật sự cần.

### 23.12. Tất cả pod báo prod nhưng chỉ một pod sai

**Vấn đề:** pod có config source, image version hoặc thời điểm rollout khác.

**Xử lý:** đối chiếu version, effective settings và bean của từng replica.

## 24. Những hiểu nhầm cần tránh

**“Có file application-prod.yml là Spring đang chạy prod.”**  
Không. File có thể chưa được nạp.

**“getProperty('spring.profiles.active') là danh sách đầy đủ mọi active profile.”**  
Không nhất thiết. Include, groups và programmatic additional profiles có thể bổ sung profile; dùng getActiveProfiles().

**“getActiveProfiles() rỗng nghĩa không có profile nào phù hợp.”**  
Không. Default profiles vẫn có thể được dùng.

**“@Profile({"dev", "staging"}) yêu cầu cả hai profile.”**  
Không. Danh sách mang ý nghĩa OR.

**“@Profile("!prod") chỉ chạy ở môi trường phát triển.”**  
Không. Nó match bất kỳ tình huống nào mà prod không phù hợp.

**“Profile prod tự loại trừ profile dev.”**  
Không. Hai profile có thể cùng active.

**“spring.config.activate.on-profile: prod sẽ tự bật prod.”**  
Không. Nó chỉ điều kiện hóa document khi prod đã phù hợp.

**“Kích hoạt prod bảo đảm mọi property lấy từ application-prod.yml.”**  
Không. Nguồn ưu tiên cao hơn hoặc import có thể ghi đè.

**“Bean mang @Profile đúng nghĩa bean đó chắc chắn tồn tại.”**  
Không. Configuration class có thể chưa được scan/import, hoặc còn condition và dependency khác.

**“Maven -Pproduction hoặc Gradle -Penv=prod tự bật Spring prod.”**  
Không. Đây là các thiết lập build; runtime Spring Profile phải được truyền/thiết lập phù hợp.

**“Actuator /conditions luôn giải thích mọi @Profile.”**  
Không. Cần kết hợp Environment và bean registry.

**“Profile là lớp bảo vệ đủ mạnh cho thao tác nguy hiểm.”**  
Không. Cần thêm quyền truy cập, validation và quy trình vận hành an toàn.

## Ghi nhớ cốt lõi

Để biết Spring Boot thực sự đang dùng profile nào, hãy đọc **Environment.getActiveProfiles()** và **getDefaultProfiles()** từ process cần kiểm tra. Đừng chỉ xem file application-prod.yml hoặc chuỗi spring.profiles.active vì include, groups, additional profiles và các nguồn cấu hình khác có thể làm kết quả khác dự kiến.

Sau khi xác minh active profiles, kiểm tra **giá trị property cuối cùng** từ Environment hoặc @ConfigurationProperties, và đối chiếu **các bean thực tế được đăng ký**. Một profile có thể đúng nhưng database, endpoint hoặc bean vẫn sai vì property override, condition khác hoặc phiên bản triển khai khác. Kiểm thử bằng @ActiveProfiles và ApplicationContextRunner, bổ sung startup diagnostics không lộ secret, kiểm tra các replica và dùng fail-fast cho cấu hình không an toàn. Mục tiêu không chỉ là thấy chữ prod trong log, mà là chứng minh ứng dụng đang sử dụng **đúng cấu hình, đúng bean và đúng tài nguyên** của môi trường dự kiến.
