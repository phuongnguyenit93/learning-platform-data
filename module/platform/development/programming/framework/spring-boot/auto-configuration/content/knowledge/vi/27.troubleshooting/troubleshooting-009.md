# Thuộc tính không có hiệu lực do sai khóa, sai nguồn hoặc sai thời điểm đọc

## 1. Nhìn đúng bản chất của lỗi

Trong Spring Boot, một property có thể được khai báo đúng cú pháp nhưng ứng dụng vẫn không dùng giá trị mong muốn. Thường lỗi thuộc một trong ba nhóm:

1. **Sai khóa hoặc sai cấu trúc binding:** tên property, prefix, đường dẫn lồng nhau hoặc kiểu dữ liệu không khớp với nơi đọc.
2. **Sai nguồn hoặc sai độ ưu tiên:** file không được nạp, profile không hoạt động, biến môi trường đặt sai tên, hoặc một nguồn ưu tiên cao hơn đã ghi đè giá trị.
3. **Sai thời điểm đọc:** property được đọc trước khi nguồn cấu hình được nạp, được đọc quá sớm trong vòng đời Spring, hoặc object đã giữ giá trị cũ sau khi Environment thay đổi.

Cách chẩn đoán hiệu quả là tách ba câu hỏi:

- Spring có nhìn thấy đúng key trong Environment không?
- Bean có bind hoặc inject đúng giá trị từ Environment không?
- Thành phần thực thi có đang dùng chính bean/giá trị đó tại thời điểm cần thiết không?

Nếu bỏ qua một trong ba câu hỏi, ta dễ sửa nhầm file hoặc thêm một property trùng tên mà không giải quyết nguyên nhân.

## 2. Spring Boot đọc property từ đâu?

Spring Boot hỗ trợ nhiều nguồn cấu hình: file .properties, YAML, biến môi trường, Java system properties, command-line arguments, JSON cấu hình, JNDI và các nguồn dành riêng cho kiểm thử.

Giá trị được hợp nhất vào Spring Environment dưới dạng các PropertySource. Nguồn xuất hiện sau trong thứ tự ưu tiên có thể ghi đè giá trị từ nguồn trước đó.

### 2.1. Thứ tự ưu tiên PropertySource trong Spring Boot 3.5

Danh sách dưới đây theo thứ tự từ ưu tiên thấp đến cao trong tài liệu Spring Boot 3.5:

| Thứ tự | Nguồn | Ghi chú |
| --- | --- | --- |
| 1 | Default properties | Ví dụ SpringApplication.setDefaultProperties(...) |
| 2 | @PropertySource | Được thêm khi context refresh; quá muộn cho một số thuộc tính khởi động |
| 3 | Config data | application.properties, YAML và file được import |
| 4 | RandomValuePropertySource | Chỉ cung cấp các key thuộc random.* |
| 5 | OS environment variables | Ví dụ APP_REMOTE_CONNECTTIMEOUT |
| 6 | Java system properties | Các giá trị truyền bằng -Dkey=value |
| 7 | JNDI attributes | java:comp/env |
| 8 | ServletContext init parameters | Chỉ có trong môi trường Servlet phù hợp |
| 9 | ServletConfig init parameters | Chỉ có trong môi trường Servlet phù hợp |
| 10 | SPRING_APPLICATION_JSON | JSON trong environment variable hoặc system property |
| 11 | Command-line arguments | Ví dụ --app.remote.connect-timeout=8s |
| 12 | properties trên test annotation | Ví dụ @SpringBootTest(properties = "...") |
| 13 | @DynamicPropertySource | Nguồn động trong test |
| 14 | @TestPropertySource | Property source của Spring Test |
| 15 | Devtools global settings | Chỉ khi Devtools được bật |

Ví dụ: file cấu hình đặt timeout là 3s, biến môi trường đặt 5s, system property đặt 6s, còn command line đặt 8s. Khi tất cả các nguồn này cùng được nạp, giá trị cuối cùng là 8s.

~~~properties
# application.properties
app.remote.connect-timeout=3s
~~~

~~~bash
# Linux/macOS
APP_REMOTE_CONNECTTIMEOUT=5s java -jar app.jar
~~~

~~~bash
# Java system property
java -Dapp.remote.connect-timeout=6s -jar app.jar
~~~

~~~bash
# Command-line argument có độ ưu tiên cao hơn các nguồn trên
java -jar app.jar --app.remote.connect-timeout=8s
~~~

Không nên cố ghi nhớ mọi nguồn cấu hình trong mọi môi trường. Khi có nhiều giá trị trùng key, hãy kiểm tra nguồn thắng thực tế bằng Actuator env hoặc bằng cách duyệt các PropertySource trong Environment.

### 2.2. Các vị trí Spring Boot tự tìm application.properties

Mặc định, Spring Boot tìm application.properties và application.yaml ở các vị trí phổ biến:

1. Gốc classpath, ví dụ src/main/resources/application.properties.
2. Thư mục config/ trên classpath.
3. Thư mục làm việc hiện tại khi chạy ứng dụng.
4. Thư mục config/ dưới thư mục làm việc hiện tại.
5. Các thư mục con trực tiếp của config/ ở thư mục làm việc hiện tại.

Các vị trí bên ngoài file JAR có thể ghi đè giá trị được đóng gói bên trong JAR. Vì vậy, một file application.properties trong thư mục chạy có thể làm giá trị trong src/main/resources không còn là giá trị cuối cùng.

Một lỗi triển khai thường gặp là kiểm tra đúng file trong IDE nhưng khi chạy JAR ở thư mục khác, Spring Boot nạp thêm cấu hình bên ngoài và thay thế giá trị.

### 2.3. spring.config.location và spring.config.additional-location

Hai thuộc tính này có ý nghĩa khác nhau:

- spring.config.location **thay thế** các vị trí tìm kiếm mặc định.
- spring.config.additional-location **bổ sung** vị trí mới bên cạnh các vị trí mặc định.

Ví dụ muốn bổ sung file cấu hình ngoài:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./deploy-config/
~~~

Ví dụ chỉ tìm trong các vị trí được chỉ định:

~~~bash
java -jar app.jar --spring.config.location=optional:file:./deploy-config/
~~~

Nếu vô tình dùng spring.config.location trong khi vẫn mong Spring Boot tự tìm mọi file mặc định, cấu hình đóng gói có thể không được nạp như dự kiến.

Các thuộc tính spring.config.name, spring.config.location và spring.config.additional-location được dùng rất sớm để quyết định file nào cần nạp. Hãy cung cấp chúng qua environment variable, system property hoặc command line; không đặt chúng trong application.properties rồi mong chúng điều khiển chính việc tìm file đó.

### 2.4. Profile-specific configuration

Nếu ứng dụng bật profile prod, Spring Boot sẽ xét các file như:

- application.properties
- application-prod.properties

File dành cho profile có thể ghi đè file không gắn profile. Nếu nhiều profile cùng hoạt động, profile được liệt kê sau có thể ghi đè giá trị của profile trước.

~~~properties
# application.properties
app.remote.connect-timeout=3s
~~~

~~~properties
# application-prod.properties
app.remote.connect-timeout=10s
~~~

Kích hoạt profile:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Nếu ứng dụng vẫn chạy profile default hoặc profile khác, file application-prod.properties không được áp dụng.

spring.profiles.active và spring.profiles.default cần được khai báo trong document không phải profile-specific; không đặt chúng bên trong document chỉ được kích hoạt bởi profile.

### 2.5. spring.config.import và nhiều document

Có thể import file cấu hình khác:

~~~properties
# application.properties
app.remote.connect-timeout=3s
spring.config.import=optional:file:./remote-overrides.properties
~~~

Nếu file được import chứa:

~~~properties
app.remote.connect-timeout=9s
~~~

giá trị từ file import có thể ghi đè giá trị trong document khai báo import. Một file có thể import thêm cấu hình profile-specific tương ứng.

Spring Boot cũng hỗ trợ YAML nhiều document:

~~~yaml
app:
  remote:
    connect-timeout: 3s
---
spring:
  config:
    activate:
      on-profile: prod
app:
  remote:
    connect-timeout: 10s
~~~

Document sau chỉ được áp dụng khi điều kiện kích hoạt khớp. Nếu dùng đồng thời .properties và YAML tại cùng một vị trí, file .properties có độ ưu tiên cao hơn; nên thống nhất một định dạng trong toàn ứng dụng.

## 3. Sai khóa: tên property và cấu trúc binding không khớp

### 3.1. Dùng một prefix nhất quán

Giả sử bean cấu hình khai báo:

~~~java
@ConfigurationProperties(prefix = "app.remote")
public class RemoteProperties {
    private Duration connectTimeout = Duration.ofSeconds(1);

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }
}
~~~

Key hợp lệ trong application.properties:

~~~properties
app.remote.connect-timeout=3s
~~~

Các lỗi thường gặp:

~~~properties
# Sai prefix
app.remtoe.connect-timeout=3s

# Sai tên trường
app.remote.connect-timout=3s

# Sai cấu trúc
app.remote.timeout.connect=3s
~~~

Spring không thể tự đoán rằng remtoe là remote hoặc connect-timout là connect-timeout. Nếu key sai không được tiêu thụ, field có thể giữ giá trị mặc định mà không gây lỗi rõ ràng.

Để giảm nhầm lẫn:

- Chọn prefix ngắn, ổn định và viết nhất quán.
- Dùng kebab-case chữ thường trong file cấu hình.
- Dùng đúng tên field Java theo camelCase.
- Tạo một lớp @ConfigurationProperties cho một nhóm cấu hình có liên quan.
- Đặt tên property có ngữ nghĩa rõ ràng, chẳng hạn connect-timeout thay vì một key mơ hồ như timeout.

### 3.2. Relaxed binding không có nghĩa mọi tên đều tương đương

Spring Boot hỗ trợ relaxed binding khi bind Environment vào @ConfigurationProperties. Ví dụ field Java firstName có thể nhận từ các key:

~~~properties
my.main-project.person.first-name=Lan
my.main-project.person.firstName=Lan
my.main-project.person.first_name=Lan
~~~

Prefix của @ConfigurationProperties nên viết theo canonical form: chữ thường và dấu gạch ngang, ví dụ my.main-project.person.

Relaxed binding có quy tắc theo từng PropertySource. Nó hỗ trợ các cách viết camelCase, kebab-case và underscore trong file properties/YAML, còn environment variable dùng chữ hoa và dấu gạch dưới theo quy tắc riêng.

Đừng dựa vào việc một cách viết tình cờ hoạt động trong file properties để suy ra rằng cùng chuỗi đó sẽ hoạt động như environment variable.

### 3.3. Quy tắc đổi tên thành environment variable

Để chuyển một property canonical thành environment variable:

1. Thay dấu chấm . bằng _.
2. Bỏ dấu gạch ngang -.
3. Chuyển toàn bộ thành chữ hoa.

Ví dụ:

| Property canonical | Environment variable |
| --- | --- |
| app.remote.connect-timeout | APP_REMOTE_CONNECTTIMEOUT |
| spring.main.log-startup-info | SPRING_MAIN_LOGSTARTUPINFO |
| my.service[0].other | MY_SERVICE_0_OTHER |

Với property app.remote.connect-timeout, biến APP_REMOTE_CONNECT_TIMEOUT không phải tên chuyển đổi tương ứng theo quy tắc trên; dấu gạch ngang bị bỏ, không được đổi thành một dấu gạch dưới mới.

Ví dụ PowerShell:

~~~powershell
$env:APP_REMOTE_CONNECTTIMEOUT = "8s"
java -jar .\target\config-diagnostics-1.0.0-SNAPSHOT.jar
Remove-Item Env:APP_REMOTE_CONNECTTIMEOUT
~~~

Ví dụ Linux/macOS:

~~~bash
APP_REMOTE_CONNECTTIMEOUT=8s java -jar target/config-diagnostics-1.0.0-SNAPSHOT.jar
~~~

Giá trị của environment variable được giữ nguyên; Spring chỉ chuyển đổi tên key. Ví dụ MY_PROPS_VALUES_KEY=VALUE vẫn bind value là VALUE, không tự đổi thành chữ thường.

### 3.4. @ConfigurationProperties và @Value có mức hỗ trợ khác nhau

@ConfigurationProperties phù hợp với một nhóm cấu hình có cấu trúc:

~~~java
@ConfigurationProperties(prefix = "app.remote")
public class RemoteProperties {
    // endpoint, connectTimeout, enabled...
}
~~~

Nó hỗ trợ relaxed binding, metadata cho IDE, chuyển đổi kiểu dữ liệu và validation khi được cấu hình phù hợp.

@Value là tính năng của Spring Core, hữu ích cho một giá trị đơn:

~~~java
@Value("${app.remote.connect-timeout:1s}")
private Duration connectTimeout;
~~~

@Value không hỗ trợ relaxed binding đầy đủ như @ConfigurationProperties. Khi dùng placeholder, hãy viết tên key ở canonical form, ví dụ:

~~~java
@Value("${demo.item-price}")
private BigDecimal itemPrice;
~~~

Dùng ${demo.itemPrice} có thể không nhận được dạng kebab-case demo.item-price từ file properties. Nếu cấu hình có nhiều field, nested object hoặc collection, ưu tiên @ConfigurationProperties.

### 3.5. Kiểm tra bean cấu hình đã được đăng ký chưa

Chỉ gắn @ConfigurationProperties lên class không có nghĩa bean chắc chắn tồn tại. Cần đăng ký class bằng một trong các cách:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class Application {
}
~~~

Hoặc:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(RemoteProperties.class)
public class RemoteConfiguration {
}
~~~

Hoặc bind trực tiếp bean bên thứ ba:

~~~java
@Configuration(proxyBeanMethods = false)
public class ThirdPartyConfiguration {

    @Bean
    @ConfigurationProperties("another")
    AnotherComponent anotherComponent() {
        return new AnotherComponent();
    }
}
~~~

Nếu không có scan, @EnableConfigurationProperties hoặc bean method phù hợp, class có thể không được đăng ký để binder xử lý. Khi đó service không thể inject bean hoặc bạn có thể đang đọc một instance được tự tạo bằng new và chưa từng được Spring bind.

### 3.6. Sai kiểu dữ liệu hoặc cấu trúc lồng nhau

Property tồn tại vẫn có thể không bind như mong muốn nếu kiểu dữ liệu không hợp lệ hoặc cấu trúc không đúng.

Ví dụ:

~~~properties
app.remote.connect-timeout=3s
app.remote.enabled=true
~~~

Duration có thể nhận giá trị có đơn vị như 3s, 500ms, 2m. Nếu dùng chuỗi không hợp lệ, quá trình bind có thể thất bại với lỗi chuyển đổi.

Với YAML, chú ý thụt lề:

~~~yaml
app:
  remote:
    connect-timeout: 3s
    enabled: true
~~~

Nếu connect-timeout bị đặt lệch cấp, key sinh ra có thể không còn là app.remote.connect-timeout.

Khi bind collection, map hoặc list, chú ý cú pháp index. Khi bind key map có ký tự đặc biệt, có thể cần bracket notation để giữ nguyên key:

~~~properties
my.map[/key1]=value1
~~~

Trong YAML, bracket key cần đặt trong dấu nháy:

~~~yaml
my:
  map:
    "[/key1]": "value1"
~~~

## 4. Sai nguồn: key đúng nhưng nguồn không được nạp hoặc bị ghi đè

### 4.1. File không nằm ở vị trí Spring Boot tìm kiếm

Kiểm tra các câu hỏi:

- File có nằm trong src/main/resources không?
- File có được đóng gói vào JAR không?
- Khi chạy JAR, thư mục làm việc hiện tại là thư mục nào?
- Có file application.properties bên ngoài JAR đang ghi đè không?
- Có spring.config.location thay thế danh sách vị trí mặc định không?
- File custom có được import bằng spring.config.import không?

Có thể kiểm tra nội dung JAR:

~~~bash
jar tf target/app.jar
~~~

Tìm BOOT-INF/classes/application.properties hoặc file cấu hình tương ứng. Lưu ý lệnh này chỉ kiểm tra file có được đóng gói; nó không cho biết giá trị cuối cùng sau khi hợp nhất các nguồn.

### 4.2. Profile không được kích hoạt

Nếu property chỉ có trong application-prod.properties, hãy xác nhận profile prod thực sự hoạt động:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Có thể in profile hiện tại:

~~~java
@Component
public class ProfileReporter {

    public ProfileReporter(Environment environment) {
        System.out.println(
                "activeProfiles="
                        + Arrays.toString(environment.getActiveProfiles())
        );
    }
}
~~~

Đoạn này chỉ dùng để chẩn đoán cục bộ. Không nên in thông tin nhạy cảm trong log production.

### 4.3. Một nguồn khác đang ghi đè

Giả sử application-prod.properties đặt 3s, nhưng môi trường triển khai có APP_REMOTE_CONNECTTIMEOUT=10s. Giá trị environment variable có độ ưu tiên cao hơn config data, nên bean nhận 10s.

Tình huống này không phải binder bị lỗi. Binder đang nhận giá trị cuối cùng mà Environment cung cấp.

Đừng thêm một key thứ hai vào application.properties để cố sửa giá trị bị ghi đè từ environment hoặc command line. Hãy xác định nguồn nào đang thắng và sửa ở đúng nơi quản lý nguồn đó.

### 4.4. @PropertySource không phù hợp với mọi loại cấu hình

Ví dụ:

~~~java
@Configuration
@PropertySource("classpath:custom.properties")
public class CustomPropertiesConfiguration {
}
~~~

@PropertySource được thêm vào Environment khi ApplicationContext đang refresh. Vì vậy, nó quá muộn để cấu hình một số thuộc tính Spring Boot đọc trước khi refresh, chẳng hạn:

- logging.*
- spring.main.*

Với các thuộc tính điều khiển cách Spring Boot khởi động, hãy đặt chúng trong Config Data, system property, environment variable hoặc command-line argument thích hợp.

Ngoài ra, @PropertySource không tự nạp YAML và không hỗ trợ multi-document properties/YAML như Config Data. Nếu cần nạp YAML trực tiếp, cần dùng cơ chế loader phù hợp hoặc chuyển cấu hình về Config Data chuẩn.

## 5. Sai thời điểm đọc: property đúng nhưng code giữ giá trị cũ

### 5.1. Đọc property trước khi SpringApplication chạy

Đoạn code sau đọc system property trước khi Spring Boot nạp cấu hình:

~~~java
public class Application {

    private static final String ENDPOINT =
            System.getProperty("app.remote.endpoint");

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

System.getProperty(...) chỉ đọc Java system properties tại thời điểm class được khởi tạo. Nó không tự đọc application.properties, YAML hoặc toàn bộ Spring Environment.

Cách phù hợp hơn là inject Environment hoặc RemoteProperties vào bean do Spring quản lý:

~~~java
@Component
public class RemoteService {

    private final RemoteProperties properties;

    public RemoteService(RemoteProperties properties) {
        this.properties = properties;
    }
}
~~~

Không lưu kết quả đọc property vào static field trước khi SpringApplication.run(...) khởi tạo Environment.

### 5.2. Phân biệt thời điểm đọc của các cơ chế

| Cơ chế | Thời điểm sử dụng giá trị | Lưu ý |
| --- | --- | --- |
| SpringApplication properties | Giai đoạn chuẩn bị và khởi tạo ứng dụng | Một số key cần có trước context refresh |
| @PropertySource | Khi cấu hình được xử lý trong context refresh | Quá muộn cho một số spring.main.* và logging.* |
| @Value | Khi bean được tạo và placeholder được resolve | Field trong singleton không tự cập nhật khi Environment đổi |
| @ConfigurationProperties | Khi bean cấu hình được bind | Cần đăng ký bean và cấu trúc field phù hợp |
| Environment.getProperty(...) | Tại thời điểm gọi method | Trả về giá trị thắng trong các PropertySource hiện có |
| Static initializer / new thủ công | Khi class/object được tạo ngoài lifecycle Spring | Dễ đọc quá sớm hoặc bỏ qua Spring binding |

### 5.3. Singleton không tự cập nhật khi file hoặc Environment thay đổi

Ví dụ bean:

~~~java
@Component
public class RemoteService {

    @Value("${app.remote.connect-timeout}")
    private Duration connectTimeout;
}
~~~

Giá trị được resolve khi bean được tạo. Nếu sau đó file cấu hình trên đĩa thay đổi hoặc một PropertySource bị sửa, field của singleton không tự động bind lại.

Tương tự, một @ConfigurationProperties bean không tự refresh chỉ vì bạn sửa application.properties trong khi ứng dụng đang chạy.

Nếu yêu cầu cập nhật cấu hình không cần restart, cần dùng cơ chế refresh/rebind được thiết kế cho môi trường đó, ví dụ giải pháp Spring Cloud phù hợp hoặc một cơ chế cập nhật có kiểm soát của ứng dụng. Spring Boot core không tự theo dõi mọi file và cập nhật mọi singleton.

### 5.4. Đọc Environment và đọc bean cấu hình có thể cho hai kết quả khác nhau

Nếu Environment.getProperty("app.remote.connect-timeout") trả về đúng nhưng bean đang dùng giá trị khác, hãy kiểm tra:

- Bean có đúng là bean @ConfigurationProperties do Spring quản lý không?
- Prefix và field name có khớp không?
- Có setter/constructor binding phù hợp không?
- Có instance nào được tạo bằng new RemoteProperties() thay vì inject bean không?
- Service có giữ giá trị cũ trong field hoặc cache không?
- Có @Value khác đang đọc một key khác không?
- Bean có được tạo trước khi custom PropertySource được thêm vào không?

Đây là dấu hiệu lỗi nằm ở binding hoặc lifecycle, không còn là lỗi nạp file đơn thuần.

## 6. Ví dụ chạy được: chẩn đoán key, nguồn và binding

Ví dụ dùng Java 17 và Spring Boot 3.5.0. Ứng dụng bind nhóm app.remote vào RemoteProperties, rồi in giá trị đã bind cùng giá trị đang có trong Environment.

### 6.1. Cấu trúc project

~~~text
config-diagnostics/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── example/
    │   │       ├── ConfigDiagnosticsApplication.java
    │   │       └── RemoteProperties.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/
            └── example/
                └── RemotePropertiesBindingTests.java
~~~

### 6.2. Tệp pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>example</groupId>
    <artifactId>config-diagnostics</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

### 6.3. Tệp src/main/resources/application.properties

~~~properties
app.remote.endpoint=https://api.example.test
app.remote.connect-timeout=3s
app.remote.enabled=true
~~~

Đây là cấu hình mặc định được đóng gói trong ứng dụng. Giá trị có thể được ghi đè bởi profile, file bên ngoài, environment variable, system property hoặc command-line argument theo thứ tự ưu tiên.

### 6.4. Tệp RemoteProperties.java

~~~java
package example;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.remote")
public class RemoteProperties {

    private URI endpoint = URI.create("https://fallback.example.test");

    private Duration connectTimeout = Duration.ofSeconds(1);

    private boolean enabled;

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

Giá trị khởi tạo trong Java là fallback của object. Khi Config Data có property tương ứng, binder sẽ ghi đè giá trị đó. Prefix được viết theo kebab-case chữ thường.

### 6.5. Tệp ConfigDiagnosticsApplication.java

~~~java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDiagnosticsApplication.class, args);
    }

    @Bean
    CommandLineRunner reportEffectiveConfiguration(
            RemoteProperties properties,
            Environment environment) {

        return args -> {
            System.out.println("app.remote.endpoint="
                    + properties.getEndpoint());

            System.out.println("app.remote.connect-timeout="
                    + properties.getConnectTimeout());

            System.out.println("environment.app.remote.connect-timeout="
                    + environment.getProperty(
                            "app.remote.connect-timeout"
                    ));

            System.out.println("app.remote.enabled="
                    + properties.isEnabled());
        };
    }
}
~~~

@ConfigurationPropertiesScan đăng ký RemoteProperties làm bean để Spring Boot bind. CommandLineRunner chạy sau khi context được tạo, nên có thể so sánh object đã bind với giá trị thắng trong Environment.

Không in password, token hoặc secret trong ứng dụng production. Ví dụ chỉ in endpoint giả lập và timeout để minh họa.

### 6.6. Tệp RemotePropertiesBindingTests.java

~~~java
package example;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class RemotePropertiesBindingTests {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(RemoteProperties.class)
    static class PropertiesConfiguration {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(PropertiesConfiguration.class);

    @Test
    void javaDefaultRemainsWhenPropertyIsAbsent() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(RemoteProperties.class);

            RemoteProperties properties =
                    context.getBean(RemoteProperties.class);

            assertThat(properties.getConnectTimeout())
                    .isEqualTo(Duration.ofSeconds(1));
        });
    }

    @Test
    void canonicalPropertyOverridesTheJavaDefault() {
        runner.withPropertyValues(
                        "app.remote.connect-timeout=7s"
                )
                .run(context -> {
                    RemoteProperties properties =
                            context.getBean(RemoteProperties.class);

                    assertThat(properties.getConnectTimeout())
                            .isEqualTo(Duration.ofSeconds(7));
                });
    }

    @Test
    void misspelledPropertyDoesNotOverrideTheExpectedField() {
        runner.withPropertyValues(
                        "app.remote.connect-timout=9s"
                )
                .run(context -> {
                    RemoteProperties properties =
                            context.getBean(RemoteProperties.class);

                    assertThat(properties.getConnectTimeout())
                            .isEqualTo(Duration.ofSeconds(1));
                });
    }

    @Test
    void environmentAndBoundObjectSeeTheSameCanonicalValue() {
        runner.withPropertyValues(
                        "app.remote.connect-timeout=5s"
                )
                .run(context -> {
                    RemoteProperties properties =
                            context.getBean(RemoteProperties.class);

                    assertThat(context.getEnvironment().getProperty(
                            "app.remote.connect-timeout"
                    )).isEqualTo("5s");

                    assertThat(properties.getConnectTimeout())
                            .isEqualTo(Duration.ofSeconds(5));
                });
    }
}

@SpringBootTest(properties = "app.remote.connect-timeout=9s")
class TestPropertyOverrideTests {

    @org.springframework.beans.factory.annotation.Autowired
    RemoteProperties properties;

    @Test
    void testPropertyOverridesThePackagedApplicationProperties() {
        assertThat(properties.getConnectTimeout())
                .isEqualTo(Duration.ofSeconds(9));
    }
}
~~~

Các test dùng ApplicationContextRunner để kiểm tra binder trong context nhỏ. Test @SpringBootTest cuối cùng kiểm tra property của test có thể ghi đè giá trị 3s trong src/main/resources/application.properties.

### 6.7. Chạy chương trình và kiểm tra kết quả

Dùng JDK 17+ và Maven:

~~~bash
java -version
mvn -version
mvn test
mvn package
java -jar target/config-diagnostics-1.0.0-SNAPSHOT.jar
~~~

Với file cấu hình mẫu, output nghiệp vụ chính xác là:

~~~text
app.remote.endpoint=https://api.example.test
app.remote.connect-timeout=PT3S
environment.app.remote.connect-timeout=3s
app.remote.enabled=true
~~~

Duration.toString() biểu diễn ba giây là PT3S, trong khi Environment giữ chuỗi property gốc 3s.

Thử ghi đè bằng command line:

~~~bash
java -jar target/config-diagnostics-1.0.0-SNAPSHOT.jar --app.remote.connect-timeout=8s
~~~

Các dòng liên quan sẽ là:

~~~text
app.remote.connect-timeout=PT8S
environment.app.remote.connect-timeout=8s
~~~

Thử biến môi trường:

~~~powershell
$env:APP_REMOTE_CONNECTTIMEOUT = "6s"
java -jar .\target\config-diagnostics-1.0.0-SNAPSHOT.jar
Remove-Item Env:APP_REMOTE_CONNECTTIMEOUT
~~~

Kết quả timeout là PT6S. Nếu đặt nhầm APP_REMOTE_CONNECT_TIMEOUT, key đó không ánh xạ tới property canonical app.remote.connect-timeout theo quy tắc đổi tên environment variable.

**Phân biệt rõ hai loại test trong ví dụ:** các assertion cho ApplicationContextRunner kiểm tra binding và default trong context test riêng; @SpringBootTest kiểm tra nguồn Config Data thật cùng test property. Các lệnh Maven ở trên là cách xác nhận toàn bộ ví dụ trên máy có JDK và Maven.

## 7. Quy trình chẩn đoán khi property không có hiệu lực

Thực hiện theo thứ tự để tìm đúng tầng gây lỗi.

### Bước 1: Xác định key canonical mà code thực sự đọc

Tìm nơi sử dụng property:

- @ConfigurationProperties(prefix = "...")
- @Value("${...}")
- Environment.getProperty("...")
- Binder
- @ConditionalOnProperty

Ghi lại tên đầy đủ, ví dụ app.remote.connect-timeout. Đừng chỉ nhìn tên field Java connectTimeout rồi tự suy ra key.

Nếu dùng @ConditionalOnProperty, kiểm tra cả prefix, name, havingValue và matchIfMissing. Property có thể tồn tại nhưng condition không khớp do giá trị không đúng.

### Bước 2: Kiểm tra Environment có nhìn thấy key không

Có thể kiểm tra nhanh trong bean:

~~~java
@Component
public class PropertyProbe {

    public PropertyProbe(Environment environment) {
        String key = "app.remote.connect-timeout";

        System.out.println("present=" + environment.containsProperty(key));
        System.out.println("value=" + environment.getProperty(key));
    }
}
~~~

Nếu containsProperty là false, hãy kiểm tra key, nguồn file, profile, biến môi trường và vị trí cấu hình.

Nếu giá trị có mặt nhưng khác dự kiến, nghi ngờ nguồn ưu tiên cao hơn đã ghi đè.

### Bước 3: Xem nguồn nào đang cung cấp giá trị

Trong môi trường kiểm thử cục bộ, có thể duyệt các PropertySource:

~~~java
for (PropertySource<?> source : environment.getPropertySources()) {
    if (source.containsProperty("app.remote.connect-timeout")) {
        System.out.println(
                source.getName() + " -> "
                        + source.getProperty("app.remote.connect-timeout")
        );
    }
}
~~~

Danh sách này giúp nhìn thấy nhiều nguồn cùng chứa một key. Environment.getProperty(...) trả về giá trị thắng theo thứ tự ưu tiên.

Đoạn probe trên chỉ dành cho key không nhạy cảm. Không in toàn bộ Environment hoặc secrets vào log production.

### Bước 4: Kiểm tra file Config Data thực sự được nạp

Bật log chi tiết cho quá trình nạp cấu hình:

~~~properties
logging.level.org.springframework.boot.context.config=TRACE
~~~

Log này giúp thấy Spring Boot đang tìm và nạp file nào, profile nào được xét và import nào được xử lý.

Nếu dùng spring.config.location, kiểm tra nó có thay thế các vị trí mặc định hay không. Nếu muốn thêm file, cân nhắc spring.config.additional-location.

### Bước 5: So sánh giá trị Environment với bean đã bind

Nếu Environment trả đúng 5s nhưng RemoteProperties vẫn giữ 1s, kiểm tra:

- Bean cấu hình có được đăng ký không?
- Prefix có chính xác không?
- Field/getter/setter hoặc constructor binding có hợp lệ không?
- Có tạo instance thủ công bằng new không?
- Kiểu dữ liệu có chuyển đổi được không?
- Bean có được tạo trước khi nguồn cấu hình tùy chỉnh xuất hiện không?

Nếu cả Environment và bean đều đúng nhưng chức năng vẫn dùng giá trị cũ, tìm field cache, static field, instance khác hoặc code đọc property ở một nơi khác.

### Bước 6: Kiểm tra nguồn ghi đè

Kiểm tra theo thứ tự vận hành thực tế:

- Command line có --app.remote... không?
- Có SPRING_APPLICATION_JSON không?
- Java có tham số -Dapp.remote... không?
- Container/Kubernetes có environment variable không?
- Có file profile-specific không?
- Có file cấu hình ngoài JAR không?
- Test có properties, @DynamicPropertySource hoặc @TestPropertySource không?

Không giả định giá trị trong file luôn là giá trị cuối cùng.

### Bước 7: Dùng Actuator khi cần chẩn đoán production

Nếu ứng dụng đã có Actuator và expose endpoint phù hợp:

- /actuator/env hoặc /actuator/env/{property.name} giúp xem property sources và giá trị theo Environment.
- /actuator/configprops giúp xem các bean @ConfigurationProperties đã bind.

Hai endpoint trả lời hai câu hỏi khác nhau: env cho biết giá trị đến từ đâu; configprops cho biết object cấu hình đã nhận giá trị nào.

Các endpoint này có thể tiết lộ tên property, cấu trúc cấu hình hoặc thông tin nhạy cảm. Chỉ expose khi cần, giới hạn quyền truy cập và bảo vệ endpoint theo chính sách bảo mật của hệ thống.

## 8. Những lỗi thường gặp

1. **Sai prefix hoặc typo trong key.** Ví dụ app.remtoe hoặc connect-timout; field giữ giá trị mặc định.
2. **Dùng environment variable sai quy tắc.** Dấu gạch ngang bị bỏ, không đổi thành dấu gạch dưới bổ sung.
3. **Cho rằng mọi nguồn có cùng độ ưu tiên.** Environment, system property và command line có thể ghi đè Config Data.
4. **Đặt file ngoài JAR nhưng chạy từ thư mục khác.** Spring Boot có thể không tìm thấy file dự kiến hoặc tìm thấy một file khác.
5. **Dùng spring.config.location khi chỉ muốn thêm file.** Thuộc tính này thay thế vị trí mặc định; dùng spring.config.additional-location khi muốn bổ sung.
6. **Profile không hoạt động.** application-prod.properties không được dùng nếu profile prod không active.
7. **Đặt spring.config.location trong application.properties.** Thuộc tính này cần được cung cấp sớm qua environment, system property hoặc command line.
8. **Dùng @PropertySource cho logging.* hoặc spring.main.*.** Nguồn được thêm quá muộn cho một số thuộc tính khởi động.
9. **Dùng @Value với tên placeholder không canonical.** @Value không có relaxed binding đầy đủ như @ConfigurationProperties.
10. **Quên đăng ký @ConfigurationProperties.** Class không được scan/enable hoặc không được tạo thành bean.
11. **Tạo object bằng new.** Instance tự tạo không đi qua Spring binder và dependency injection.
12. **Nhầm giá trị Environment với giá trị đã bind.** Kiểm tra cả hai để biết lỗi ở nguồn hay binder.
13. **Mong singleton tự cập nhật khi file đổi.** @Value và @ConfigurationProperties không tự refresh chỉ vì file trên đĩa thay đổi.
14. **Đọc property trong static initializer.** Class có thể được khởi tạo trước khi Spring Environment sẵn sàng.
15. **Sai kiểu hoặc cú pháp YAML.** Binder có thể lỗi chuyển đổi hoặc nhận một cấu trúc key khác dự kiến.
16. **Không kiểm tra giá trị test override.** @SpringBootTest(properties=...), @DynamicPropertySource và @TestPropertySource có thứ tự ưu tiên riêng.
17. **Dùng đồng thời .properties và YAML ở cùng vị trí.** .properties được ưu tiên; hai file có thể tạo cảm giác cấu hình bị bỏ qua.
18. **Không kiểm tra origin của property.** Chỉ xem giá trị cuối cùng có thể chưa đủ để biết file hoặc nguồn nào đã thắng.

## 9. Checklist review cấu hình

- [ ] Đã xác định đúng key canonical mà code đang đọc.
- [ ] Prefix @ConfigurationProperties dùng kebab-case chữ thường.
- [ ] Tên field và cấu trúc YAML/properties khớp nhau.
- [ ] Environment variable được đổi tên theo quy tắc dots → underscores, bỏ dashes, uppercase.
- [ ] @ConfigurationProperties bean đã được scan hoặc enable.
- [ ] Đã kiểm tra giá trị qua Environment.getProperty(...).
- [ ] Đã kiểm tra nguồn nào đang thắng khi có nhiều PropertySource.
- [ ] File cấu hình nằm ở vị trí Spring Boot thực sự tìm kiếm hoặc được import rõ ràng.
- [ ] Profile cần thiết đang active.
- [ ] Đã phân biệt spring.config.location với spring.config.additional-location.
- [ ] Không dùng @PropertySource để cấu hình thuộc tính cần đọc trước context refresh.
- [ ] Không đọc property qua static initializer hoặc trước SpringApplication.run.
- [ ] Không kỳ vọng singleton tự cập nhật khi Environment/file thay đổi.
- [ ] Đã so sánh Environment với bean cấu hình đã bind.
- [ ] Có test cho default, override đúng key và typo/wrong key.
- [ ] Actuator env/configprops chỉ được expose và bảo vệ khi thực sự cần.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao property có trong application.properties nhưng bean vẫn nhận giá trị khác?  
**Đáp án:** Một PropertySource có độ ưu tiên cao hơn, chẳng hạn environment variable hoặc command line, có thể ghi đè giá trị trong file.

**Câu 2.** app.remote.connect-timeout được đổi thành environment variable nào?  
**Đáp án:** APP_REMOTE_CONNECTTIMEOUT; dấu chấm thành dấu gạch dưới, dấu gạch ngang bị bỏ, rồi chuyển thành chữ hoa.

**Câu 3.** spring.config.location khác spring.config.additional-location thế nào?  
**Đáp án:** location thay thế vị trí tìm kiếm mặc định; additional-location bổ sung vị trí mới.

**Câu 4.** Vì sao @PropertySource không phù hợp để cấu hình spring.main.*?  
**Đáp án:** PropertySource của nó được thêm khi context refresh, trong khi một số thuộc tính spring.main.* đã được đọc trước thời điểm đó.

**Câu 5.** Khi nào nên dùng @ConfigurationProperties thay @Value?  
**Đáp án:** Khi có một nhóm cấu hình có cấu trúc, nhiều field, nested object, collection, relaxed binding hoặc validation.

**Câu 6.** Environment trả đúng giá trị nhưng bean cấu hình sai thì nên kiểm tra gì?  
**Đáp án:** Đăng ký bean, prefix, field/getter/setter, kiểu dữ liệu, instance tự tạo bằng new và thời điểm bean được khởi tạo.

**Câu 7.** Sửa application.properties khi ứng dụng đang chạy có tự cập nhật field @Value không?  
**Đáp án:** Không. Giá trị đã resolve trong singleton không tự cập nhật; cần cơ chế refresh/rebind có chủ đích hoặc restart ứng dụng.

**Câu 8.** Endpoint Actuator nào giúp xem giá trị đến từ đâu và bean đã bind gì?  
**Đáp án:** env giúp kiểm tra Environment/property sources; configprops giúp kiểm tra các bean @ConfigurationProperties.

## Tài liệu tham khảo chính thức

- Spring Boot 3.5 Reference — Externalized Configuration, thứ tự PropertySource, Config Data, profile, import, placeholder và relaxed binding: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot 3.5 How-to — Properties and Configuration: https://docs.spring.io/spring-boot/3.5/how-to/properties-and-configuration.html
- Spring Boot 3.5 Reference — Profiles: https://docs.spring.io/spring-boot/3.5/reference/features/profiles.html
- Spring Boot 3.5 Reference — Type-safe Configuration Properties và validation: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot 3.5 Actuator API — Environment endpoint: https://docs.spring.io/spring-boot/3.5/api/rest/actuator/env.html
- Spring Boot 3.5 Actuator API — Configuration Properties endpoint: https://docs.spring.io/spring-boot/3.5/api/rest/actuator/configprops.html

**Ghi nhớ:** Khi một property không có hiệu lực, hãy kiểm tra theo ba lớp: key và binding có đúng không, nguồn nào đang thắng, và property được đọc vào thời điểm nào. So sánh Environment với bean @ConfigurationProperties, xác định PropertySource đang cung cấp giá trị, rồi kiểm tra lifecycle của bean. Cách này giúp phân biệt lỗi cấu hình với lỗi binding và lỗi sử dụng giá trị cũ.
