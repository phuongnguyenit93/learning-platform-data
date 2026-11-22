# Can thiệp sớm bằng EnvironmentPostProcessor trong Spring Boot

## Mục tiêu

Spring Boot hỗ trợ cấu hình bên ngoài thông qua file application.properties/application.yml, biến môi trường, JVM system properties, command-line arguments, Config Data và những PropertySource do ứng dụng tự bổ sung. Trong phần lớn dự án, các nguồn cấu hình tiêu chuẩn đã đủ: nhóm giá trị được bind bằng **@ConfigurationProperties**, một giá trị riêng có thể đọc qua **@Value** hoặc **Environment**.

Nhưng một số nền tảng hoặc thư viện cần **thay đổi Environment trước khi ApplicationContext được refresh**: thêm mặc định của thư viện, nạp nguồn cấu hình riêng, hỗ trợ tên property legacy hoặc chuẩn bị nguồn thuộc tính để phần còn lại của ứng dụng có thể sử dụng. **EnvironmentPostProcessor** là extension point của Spring Boot dành cho việc đó.

Phương thức cốt lõi:

~~~java
void postProcessEnvironment(
        ConfigurableEnvironment environment,
        SpringApplication application);
~~~

Nó cho phép thao tác với danh sách PropertySource của Environment ở giai đoạn bootstrap. Ví dụ:

~~~java
environment.getPropertySources().addLast(
    new MapPropertySource("companyDefaults", Map.of(
        "company.http.connect-timeout", "2s",
        "company.http.max-connections", "20"
    ))
);
~~~

Đoạn code trên đưa hai giá trị mặc định vào Environment. Nếu được đặt ở cuối danh sách PropertySource, những nguồn ưu tiên cao hơn vẫn có thể ghi đè các giá trị này.

Sau bài học, người đọc có thể:

- Giải thích thời điểm EPP chạy trong lifecycle của Spring Boot.
- Đăng ký processor qua **META-INF/spring.factories** đúng với Spring Boot 3 hoặc Spring Boot 4.
- Dùng **ConfigurableEnvironment**, **MutablePropertySources** và **MapPropertySource** an toàn.
- Xác định thứ tự processor tương đối với **ConfigDataEnvironmentPostProcessor**.
- Phân biệt thứ tự gọi processor và thứ tự ưu tiên PropertySource.
- Viết processor để bổ sung default hoặc một file cấu hình.
- Chẩn đoán discovery, precedence, lỗi bind, thiếu file và vấn đề logging.
- Hiểu giới hạn về dependency injection, secret management và dynamic refresh.
- Viết test kiểm tra hành vi processor lẫn khả năng discovery bằng SpringApplication.
- Biết khi nào **spring.config.import** hoặc một hook khác phù hợp hơn EnvironmentPostProcessor.

## 1. Vì sao cần một hook ở giai đoạn sớm?

Giả sử ứng dụng có HTTP client cấu hình qua:

~~~yaml
company:
  client:
    connect-timeout: 5s
    read-timeout: 10s
~~~

Một bean có thể dùng:

~~~java
@ConfigurationProperties(prefix = "company.client")
public record ClientProperties(
        Duration connectTimeout,
        Duration readTimeout
) {}
~~~

Nếu chỉ có hai giá trị này, **không cần EPP**. Spring Boot đã biết cách nạp YAML và bind record.

Nhưng hãy tưởng tượng một thư viện platform dùng chung phải cung cấp default **company.client.connect-timeout=2s** cho mọi ứng dụng. Không muốn yêu cầu từng dự án chép cùng giá trị vào application.yml. Một EnvironmentPostProcessor được đóng gói cùng library có thể thêm một PropertySource chứa default vào Environment trước khi bean cấu hình được tạo.

Tương tự, hệ thống đang di trú tên key từ **legacy.client.timeout-ms** sang **company.client.read-timeout** có thể cần một lớp alias tạm thời trong giai đoạn nâng cấp. EPP cho phép thực thi quy tắc này rất sớm, miễn là chính sách ưu tiên và kiểm tra dữ liệu được định nghĩa rõ.

Điểm cốt lõi: **EnvironmentPostProcessor chỉnh dữ liệu mà các thành phần tạo sau sẽ đọc; nó không phải API để sửa những bean đã chạy.**

## 2. Vị trí trong quá trình khởi động

Một luồng khởi động giản lược:

~~~text
main()
   |
   v
SpringApplication.run(...)
   |
   v
Chuẩn bị Environment và những nguồn ban đầu
   |
   v
EnvironmentPostProcessor của Boot và ứng dụng
   |-- ConfigDataEnvironmentPostProcessor
   |-- Các processor khác, theo Ordered/@Order
   |-- Processor của platform, nếu được đăng ký
   |
   v
Environment tiếp tục được dùng khi tạo context
   |
   v
Tạo ApplicationContext và refresh
   |
   v
Tạo bean, bind @ConfigurationProperties, xử lý @Value
   |
   v
ApplicationRunner / CommandLineRunner
   |
   v
Ứng dụng chạy
~~~

Đây là sơ đồ để giải thích ý nghĩa thời điểm, không phải liệt kê chính xác mọi event và listener nội bộ của tất cả phiên bản. Các processor được gọi theo thứ tự đã được framework xác định; không phải luôn gọi processor ứng dụng sau toàn bộ processor nội bộ nếu người viết chọn order khác.

### 2.1. Những thứ chưa thể giả định đã tồn tại

Khi EPP chạy, ApplicationContext chưa được refresh, nên không được xem các thành phần sau là sẵn sàng:

- @Service, @Repository, controller và datasource bean.
- EntityManager, transaction manager và Spring Data repository.
- Bean @ConfigurationProperties được tạo bình thường bởi IoC container.
- Những đối tượng do auto-configuration chỉ tạo trong lúc refresh.
- Toàn bộ cấu hình logging/runtime đã hoàn tất.

EPP nhận **Environment** và **SpringApplication**, không phải một kho bean để gọi theo cách tùy ý.

### 2.2. Trường hợp can thiệp quá muộn

Nếu một bean đã bind readTimeout=5s, sau đó ứng dụng thêm một PropertySource có readTimeout=10s, bean đó không mặc nhiên được bind lại. Với EPP, mục tiêu là đưa giá trị vào sớm để tránh tình huống ấy.

Nhưng một số property ảnh hưởng rất sớm đến logging, Config Data location hoặc profile. Ngay cả một EPP chạy trước context refresh cũng có thể chạy **sau bước sử dụng** một property đặc biệt. Vì vậy thứ tự so với các processor khác vẫn quan trọng.

## 3. Khác biệt package giữa Spring Boot 3.x và 4.x

Đây là một thay đổi quan trọng khi dùng ví dụ trên Internet.

| Phiên bản | Interface | Khóa đăng ký spring.factories |
| --- | --- | --- |
| Spring Boot 2.x/3.x | org.springframework.boot.env.EnvironmentPostProcessor | org.springframework.boot.env.EnvironmentPostProcessor |
| Spring Boot 4.x | org.springframework.boot.EnvironmentPostProcessor | org.springframework.boot.EnvironmentPostProcessor |

Trong Spring Boot 4, interface chuyển sang package **org.springframework.boot**. Một số bản 4.x giữ interface cũ dạng deprecated phục vụ migration, nhưng code mới nên dùng package mới.

Import cho Boot 3.x:

~~~java
import org.springframework.boot.env.EnvironmentPostProcessor;
~~~

Import cho Boot 4.x:

~~~java
import org.springframework.boot.EnvironmentPostProcessor;
~~~

Phương thức callback về cơ bản vẫn có dạng:

~~~java
@Override
public void postProcessEnvironment(
        ConfigurableEnvironment environment,
        SpringApplication application) {
    // ...
}
~~~

**Khi nâng cấp Boot major version, phải sửa cả import lẫn key discovery trong spring.factories.** Một class Java compile được chưa đủ chứng minh factory của Boot sẽ tìm và gọi processor.

### 3.1. Không nhầm với AutoConfiguration.imports

Auto-configuration dùng cơ chế phát hiện riêng, thường dựa trên file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Còn **EnvironmentPostProcessor** phải được đăng ký qua **META-INF/spring.factories** theo hợp đồng API. Một thư viện có thể có cả hai loại extension, nhưng chúng giải quyết hai giai đoạn khác nhau.

## 4. Ví dụ hoàn chỉnh: default của thư viện, Spring Boot 3.x

Giả sử thư viện cung cấp ba mặc định:

~~~properties
company.http.connect-timeout=2s
company.http.max-connections=20
company.audit.enabled=false
~~~

Tạo class:

~~~text
src/main/java/com/example/platform/CompanyDefaultsEnvironmentPostProcessor.java
~~~

Code:

~~~java
package com.example.platform;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;

public final class CompanyDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    private static final String SOURCE_NAME =
            "company.platform.defaults";

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        MutablePropertySources sources =
                environment.getPropertySources();

        if (sources.contains(SOURCE_NAME)) {
            return;
        }

        Map<String, Object> defaults = Map.of(
                "company.http.connect-timeout", "2s",
                "company.http.max-connections", "20",
                "company.audit.enabled", "false"
        );

        sources.addLast(new MapPropertySource(
                SOURCE_NAME,
                defaults
        ));
    }
}
~~~

### 4.1. Giải thích từng bước

**MutablePropertySources** là danh sách có thứ tự các nguồn thuộc tính. **MapPropertySource** chuyển một Map key/value thành một PropertySource có tên.

**contains(SOURCE_NAME)** giúp processor idempotent trên cùng Environment: nếu đã thêm source, lần gọi tiếp theo không thêm trùng.

**addLast** đưa source vào cuối danh sách hiện có. Đây là lựa chọn phù hợp khi thư viện chỉ cung cấp fallback/default và muốn application.yml, environment variables hoặc CLI có quyền override.

**Map.of** tạo Map không thể thay đổi qua API. Các default ở ví dụ là giá trị không nhạy cảm, có thể giữ dưới dạng hằng nội bộ.

### 4.2. Vì sao không dùng @Component?

EnvironmentPostProcessor không được phát hiện bằng component scan thông thường. Khi nó cần chạy, quá trình tạo bean của ApplicationContext chưa hoàn tất.

Việc thêm @Component không thay thế bước đăng ký discovery. Nên để implementation là một Java class bình thường được Spring Boot tìm qua spring.factories.

## 5. Đăng ký trong META-INF/spring.factories

Tạo:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Với **Spring Boot 3.x**, nội dung:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=com.example.platform.CompanyDefaultsEnvironmentPostProcessor
~~~

Với **Spring Boot 4.x**, dùng:

~~~properties
org.springframework.boot.EnvironmentPostProcessor=com.example.platform.CompanyDefaultsEnvironmentPostProcessor
~~~

Ở Boot 4, source code class cũng cần import interface **org.springframework.boot.EnvironmentPostProcessor**.

### 5.1. Cấu trúc thư mục mẫu

~~~text
my-service/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/platform/
    │   │       └── CompanyDefaultsEnvironmentPostProcessor.java
    │   └── resources/
    │       ├── META-INF/
    │       │   └── spring.factories
    │       └── application.yml
    └── test/
        └── java/
            └── com/example/platform/
                └── CompanyDefaultsEnvironmentPostProcessorTest.java
~~~

Đối với thư viện JAR, resources và implementation phải được đóng gói vào runtime classpath của ứng dụng tiêu thụ.

### 5.2. Đóng gói executable JAR

Trong một Spring Boot executable JAR, file classes/resources của ứng dụng có thể được đặt trong **BOOT-INF/classes/**. Với thư viện, chúng có thể nằm trong JAR ở **BOOT-INF/lib/**. Điều kiện thực sự là SpringFactoriesLoader tìm được entry **META-INF/spring.factories** trên runtime classpath.

Nếu build sử dụng shade/merge tùy chỉnh, cần bảo đảm nhiều file spring.factories từ các dependency được kết hợp đúng, không bị ghi đè chỉ còn một file.

### 5.3. Sai tên file là lỗi discovery, không phải lỗi Binder

Các lỗi thường gặp:

- Viết **spring.factory** thay vì **spring.factories**.
- Đặt file ngoài thư mục **META-INF**.
- Key không đúng package interface.
- Giá trị là tên class không đủ package.
- Class implementation không có trong runtime classpath.
- Constructor không khớp những loại tham số factory hỗ trợ.

Một lỗi discovery có thể khiến ứng dụng vẫn khởi động bình thường, nhưng default hoặc source custom không được thêm.

## 6. Đọc kết quả bằng Environment và @ConfigurationProperties

Record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "company.http")
public record HttpProperties(
        Duration connectTimeout,
        int maxConnections
) {}
~~~

Sau khi đăng ký bằng @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties, bean có thể nhận giá trị từ source EPP.

Nếu không có override:

~~~text
connectTimeout = 2s
maxConnections = 20
~~~

Với application.yml:

~~~yaml
company:
  http:
    connect-timeout: 5s
~~~

thì connectTimeout có thể nhận 5s từ Config Data, trong khi maxConnections vẫn dùng default 20 của thư viện.

Với command-line:

~~~bash
java -jar demo.jar --company.http.max-connections=60
~~~

thì 60 có thể thắng default 20.

### 6.1. Canonical naming

Nên dùng key canonical:

~~~text
company.http.connect-timeout
company.http.max-connections
company.audit.enabled
~~~

Biến môi trường tương ứng:

~~~text
COMPANY_HTTP_CONNECTTIMEOUT
COMPANY_HTTP_MAXCONNECTIONS
COMPANY_AUDIT_ENABLED
~~~

EnvironmentPostProcessor không thay đổi quy tắc relaxed binding của @ConfigurationProperties. Việc viết một MapPropertySource không tạo ra cú pháp đặc biệt riêng cho Java field.

### 6.2. Không dùng EPP để tự bind tất cả bean

EPP chỉ cần thêm PropertySource. Những component chuẩn của Spring Boot sau đó có thể đọc/bind giá trị.

Không nên viết code trong EPP để tạo thủ công toàn bộ HTTP client, service và repository từ các giá trị vừa thêm. Đó là trách nhiệm của context và auto-configuration/bean factory phù hợp.

## 7. Thứ tự ưu tiên của MutablePropertySources

Các thao tác thường dùng:

| Phương thức | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| addFirst(source) | Đặt nguồn ở đầu danh sách | Có thể che CLI/env và nguồn khác |
| addLast(source) | Đặt nguồn ở cuối danh sách | Thích hợp cho default ưu tiên thấp |
| addBefore(name, source) | Thêm trước một nguồn có tên | Cần nguồn được tham chiếu tồn tại |
| addAfter(name, source) | Thêm sau một nguồn có tên | Cần nguồn được tham chiếu tồn tại |
| replace(name, source) | Thay nguồn theo tên | Chỉ khi chắc chắn sở hữu/chủ đích |
| remove(name) | Gỡ nguồn | Có thể làm mất hàng loạt key |
| contains(name) | Kiểm tra nguồn đã có | Hữu ích cho idempotency |
| get(name) | Lấy nguồn theo tên | Hữu ích cho chẩn đoán có giới hạn |

### 7.1. addFirst không phải cách tăng độ chắc chắn

Đặt default lên đầu có thể khiến những giá trị do người vận hành truyền qua CLI hoặc biến môi trường bị che mất. Ví dụ library mặc định maxConnections=20, operator truyền 60, nhưng EPP addFirst đặt 20 ở vị trí ưu tiên cao hơn.

Nếu đây chỉ là default, hành vi ấy không phù hợp. Thêm source ở cuối giúp bảo vệ khả năng override.

### 7.2. addBefore và addAfter

Ví dụ:

~~~java
var sources = environment.getPropertySources();

if (sources.contains("systemEnvironment")) {
    sources.addAfter(
            "systemEnvironment",
            new MapPropertySource("platformOverrides", values)
    );
} else {
    sources.addLast(
            new MapPropertySource("platformOverrides", values)
    );
}
~~~

Đây chỉ là minh họa cơ chế. Trên một Environment tùy biến, tên source có thể khác, vì vậy phải kiểm tra tồn tại.

Không nên chọn vị trí chỉ dựa vào tên nguồn nội bộ mà không có test xác minh kết quả precedence thực tế.

### 7.3. replace có thể làm mất dữ liệu

Nếu replace nguyên nguồn **systemEnvironment** bằng Map chỉ có vài key, ứng dụng có thể mất hàng loạt biến môi trường. Tránh replace/remove những nguồn mà processor không sở hữu.

Đối với một nguồn mới, nên tạo tên riêng với namespace, chẳng hạn **company.platform.defaults** hoặc **company.platform.legacy-aliases**.

## 8. Thứ tự gọi EPP khác thứ tự PropertySource

Có hai loại thứ tự:

**Thứ tự của processor:** processor nào được Spring Boot gọi trước/sau, chịu ảnh hưởng Ordered hoặc @Order.

**Thứ tự PropertySource:** khi tìm một key, nguồn nào được Environment ưu tiên.

Ví dụ một EPP có thể chạy sau Config Data nhưng vẫn gọi **addFirst**, đưa nguồn nó tạo ra lên đầu để thắng Config Data.

Ngược lại, một EPP chạy sớm nhưng gọi **addLast** có thể tạo nguồn ưu tiên thấp; các processor chạy sau còn có thể thay đổi thứ tự danh sách.

Vì thế, câu nói **“processor chạy cuối thì giá trị của nó thắng”** không đúng trong mọi trường hợp. Phải xét đồng thời thứ tự callback và vị trí PropertySource.

## 9. Ordered và ConfigDataEnvironmentPostProcessor

Spring Boot dùng **ConfigDataEnvironmentPostProcessor** để nạp và áp dụng Config Data. Nếu EPP của bạn cần đọc key từ application.yml, nó thường phải chạy **sau khi Config Data được nạp**.

Một cách diễn đạt thứ tự tương đối:

~~~java
import org.springframework.boot.context.config.ConfigDataEnvironmentPostProcessor;
import org.springframework.core.Ordered;

public final class CompanyDefaultsEnvironmentPostProcessor
        implements EnvironmentPostProcessor, Ordered {

    @Override
    public int getOrder() {
        return ConfigDataEnvironmentPostProcessor.ORDER + 1;
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {
        // ...
    }
}
~~~

Như ví dụ, **Ordered** cung cấp giá trị order; giá trị nhỏ hơn được gọi trước theo hợp đồng Ordered thông thường.

### 9.1. Vì sao không chọn một số bất kỳ?

Nếu viết:

~~~java
@Override
public int getOrder() {
    return 100;
}
~~~

ta chỉ biết một con số, không biết nó nằm trước hay sau Config Data tại phiên bản đang dùng. Khi yêu cầu thật là **sau Config Data**, nên thể hiện quan hệ với constant thích hợp.

### 9.2. ORDER + 1 có phải chạy sau mọi thứ?

Không. Nó chỉ thể hiện thứ tự tương đối với ConfigDataEnvironmentPostProcessor. Các processor khác có thể có order nhỏ, lớn hoặc bằng nhau. Nếu nhiều extension cùng thay đổi một key, cần test để tránh phụ thuộc một thứ tự ngẫu nhiên.

### 9.3. Đọc YAML quá sớm

Một processor được đặt trước Config Data có thể chưa thấy:

~~~yaml
company:
  deployment:
    mode: production
~~~

Nếu phương thức cố đọc **company.deployment.mode** từ Environment tại thời điểm ấy, nó có thể nhận null hoặc giá trị từ nguồn khác.

Cách khắc phục là chạy sau Config Data nếu mục tiêu là đọc property đã khai báo trong application.yml.

## 10. Không đổi spring.config.* quá muộn

Một số property ảnh hưởng trực tiếp quá trình nạp file cấu hình:

~~~text
spring.config.name
spring.config.location
spring.config.additional-location
spring.config.import
spring.profiles.active
~~~

Nếu processor chạy sau khi Config Data đã được xử lý, việc thêm một giá trị **spring.config.location** vào Environment **không đảm bảo** Boot tự quay lại nạp file ở location mới.

Tương tự, thêm spring.profiles.active muộn không tương đương việc bật profile ngay từ đầu.

Để quyết định config location/profile, thường nên dùng một nguồn được Boot đọc đủ sớm:

~~~bash
java -jar demo.jar   --spring.config.additional-location=optional:file:./extra/
~~~

Hoặc env:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar demo.jar
~~~

Hoặc JVM system property:

~~~bash
java -Dspring.config.name=company -jar demo.jar
~~~

### 10.1. Nếu thật sự phải chạy trước Config Data

Đây là trường hợp nâng cao và cần tìm hiểu thứ tự nội bộ. Processor có thể chỉ nhìn thấy system properties, env vars và các nguồn bootstrap ban đầu. Nó không nên phụ thuộc application.yml chưa được nạp.

Nếu nhiệm vụ chỉ là thêm default cho bean, **không cần chạy sớm hơn Config Data**. Một lựa chọn order sau Config Data đơn giản và dễ kiểm thử hơn.

## 11. So sánh EPP với @PropertySource

Ví dụ Spring Framework:

~~~java
@Configuration
@PropertySource("classpath:extra.properties")
class ExtraConfiguration {}
~~~

Cơ chế @PropertySource trên @Configuration class được xử lý trong quá trình context refresh. Điều này có thể quá muộn cho một số thuộc tính cần cấu hình sớm, chẳng hạn **logging.*** hoặc **spring.main.*** đã được đọc trước refresh.

Trong khi đó, EPP nhận Environment ở giai đoạn chuẩn bị và có thể bổ sung nguồn trước khi đa số bean được tạo.

### 11.1. Bảng quyết định

| Nhu cầu | Cách nên xem xét |
| --- | --- |
| Cấu hình chuẩn từ application.yml | Config Data |
| Nạp thêm một file YAML/properties thông thường | spring.config.import |
| Thêm PropertySource rất sớm và có thứ tự riêng | EnvironmentPostProcessor |
| Thêm file chỉ phục vụ bean thông thường | @PropertySource khi phù hợp |
| Tùy biến context trước refresh | ApplicationContextInitializer |
| Tạo bean theo feature flag | @ConditionalOnProperty |
| Bind nhóm cấu hình vào object | @ConfigurationProperties |
| Đọc một giá trị đơn | @Value / Environment |
| Cần chạy công việc sau startup | ApplicationRunner |

**Chọn hook đơn giản nhất đáp ứng yêu cầu**, không chọn hook sớm nhất chỉ vì nó có vẻ linh hoạt.

## 12. So sánh với spring.config.import

Nếu muốn nạp một file ngoài ở thời điểm khởi động:

~~~yaml
spring:
  config:
    import: "optional:file:./config/platform-extra.yml"
~~~

Thường không cần EPP. Config Data có cơ chế nạp file, profile-specific variants, import order, optional location và các thông báo lỗi tương ứng.

Khi tự đọc file trong EPP, bạn phải quản lý:

- Quy tắc đường dẫn và resource lookup.
- Định dạng properties/YAML.
- File có được phép vắng mặt không.
- Lỗi I/O và permission.
- Ưu tiên nguồn khi trùng key.
- Profile activation và multi-document YAML nếu có.
- Origin metadata nếu cần chẩn đoán.
- Thời điểm xử lý và tác động lên startup.

Nếu chỉ cần import thêm file, **Config Data** thường ít code và dễ vận hành hơn.

### 12.1. EPP không phải bản thay thế Config Data

EPP có thể thêm source từ một file mà code tự đọc, nhưng nó không tự chạy lại mọi quy tắc của subsystem Config Data.

Một loader YAML được gọi trực tiếp không đồng nghĩa Boot sẽ tự xử lý profile activation, location groups và import của file ấy giống khi nạp qua spring.config.import.

## 13. Ví dụ đọc file .properties bổ sung

Giả sử một thư viện có:

~~~text
src/main/resources/company-defaults.properties
~~~

Với nội dung:

~~~properties
company.worker.pool-size=12
company.worker.idle-timeout=30s
company.feature.enabled=false
~~~

Processor có thể đọc file và thêm MapPropertySource:

~~~java
package com.example.platform;

import java.io.IOException;
import java.io.InputStream;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Properties;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.io.ClassPathResource;

public final class CompanyFileEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    private static final String SOURCE = "companyFileDefaults";

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application) {

        var sources = environment.getPropertySources();

        if (sources.contains(SOURCE)) {
            return;
        }

        var resource = new ClassPathResource(
                "company-defaults.properties"
        );

        if (!resource.exists()) {
            // Ví dụ: file được phép vắng mặt.
            return;
        }

        Properties properties = new Properties();

        try (InputStream input = resource.getInputStream()) {
            properties.load(input);
        } catch (IOException e) {
            throw new IllegalStateException(
                    "Cannot load company-defaults.properties",
                    e
            );
        }

        Map<String, Object> values = new LinkedHashMap<>();
        for (String key : properties.stringPropertyNames()) {
            values.put(key, properties.getProperty(key));
        }

        sources.addLast(new MapPropertySource(SOURCE, values));
    }
}
~~~

Mã này dùng import EPP của **Spring Boot 3.x**; với Boot 4 cần thay package interface và spring.factories.

### 13.1. Chính sách file optional

Trong ví dụ, nếu file không tồn tại thì phương thức return. Đây là một **quyết định nghiệp vụ**, không phải hành vi mà mọi resource bắt buộc phải có.

Nếu ứng dụng bắt buộc phải có file:

~~~java
if (!resource.exists()) {
    throw new IllegalStateException(
            "Missing required company-defaults.properties"
    );
}
~~~

Nếu file có nhưng không đọc được, throw với cause giúp xác định lỗi. Không nên catch mọi exception rồi im lặng bỏ qua, vì có thể che sai quyền hoặc file hỏng.

### 13.2. Dùng loader phù hợp

Java Properties.load(InputStream) theo các quy tắc encoding/escape của Java properties truyền thống. Với dữ liệu Unicode phức tạp hoặc nguồn cần hỗ trợ metadata, có thể sử dụng loader của Spring Boot hoặc Config Data.

**Đừng tự viết parser đơn giản** rồi giả định nó luôn tương đương parser của Boot. Với YAML nhiều cấp, lists và nhiều document, parser riêng dễ gây khác biệt về đường dẫn property.

## 14. Ví dụ nạp YAML với YamlPropertySourceLoader

Spring Boot cung cấp **YamlPropertySourceLoader**. Một ví dụ chỉ chấp nhận **một YAML document**:

~~~java
import java.io.IOException;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.boot.env.YamlPropertySourceLoader;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

public final class ExtraYamlEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    private final YamlPropertySourceLoader loader =
            new YamlPropertySourceLoader();

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment env,
            SpringApplication app) {

        Resource resource =
                new ClassPathResource("company-extra.yml");

        if (!resource.exists()) {
            return;
        }

        List<PropertySource<?>> loaded;

        try {
            loaded = loader.load("companyExtra", resource);
        } catch (IOException e) {
            throw new IllegalStateException(
                    "Cannot load company-extra.yml", e
            );
        }

        if (loaded.size() != 1) {
            throw new IllegalStateException(
                    "This example requires exactly one YAML document"
            );
        }

        String sourceName = loaded.get(0).getName();
        if (!env.getPropertySources().contains(sourceName)) {
            env.getPropertySources().addLast(loaded.get(0));
        }
    }
}
~~~

Đây vẫn là ví dụ cho Boot 3.x. **Không dùng code này rồi mong nó hỗ trợ toàn bộ trường hợp multi-document YAML**. Nếu muốn nhiều document, phải xác định thứ tự precedence và thêm đầy đủ các PropertySource được loader trả về.

### 14.1. Khi nào nên dùng Config Data thay YAML loader?

Nếu file có:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
~~~

hoặc dùng spring.config.import, việc gọi YamlPropertySourceLoader thủ công không tự mang lại toàn bộ cách xử lý Config Data của Spring Boot.

**Khi mục tiêu là semantics Config Data**, hãy nạp file bằng cơ chế Config Data, không mô phỏng nó chỉ bằng YamlPropertySourceLoader.

## 15. Migration alias: chuyển property cũ sang mới

Một trường hợp thực tế là hỗ trợ deployment cũ khi library đổi tên key.

Tên cũ:

~~~text
legacy.timeout-ms
~~~

Tên mới:

~~~text
company.http.timeout
~~~

Chính sách minh họa: tên mới **luôn thắng** nếu đã được khai báo ở bất kỳ nguồn nào; tên cũ chỉ dùng khi tên mới hoàn toàn vắng mặt.

~~~java
@Override
public void postProcessEnvironment(
        ConfigurableEnvironment environment,
        SpringApplication application) {

    var sources = environment.getPropertySources();
    String aliasSource = "company.legacy.timeout-alias";

    if (sources.contains(aliasSource)) {
        return;
    }

    String targetKey = "company.http.timeout";
    String legacyKey = "legacy.timeout-ms";

    if (environment.containsProperty(targetKey)) {
        return;
    }

    String millis = environment.getProperty(legacyKey);
    if (millis == null) {
        return;
    }

    // Ví dụ: legacy luôn là số milliseconds.
    long parsed = Long.parseLong(millis);

    if (parsed <= 0) {
        throw new IllegalArgumentException(
                "legacy.timeout-ms must be positive"
        );
    }

    sources.addLast(new MapPropertySource(
            aliasSource,
            Map.of(targetKey, parsed + "ms")
    ));
}
~~~

### 15.1. Chính sách ưu tiên phải được công bố

Ví dụ trên ưu tiên tên mới ngay cả khi tên cũ nằm ở một PropertySource có precedence cao hơn. Đây là một chính sách chủ động, **không phải mô phỏng hoàn toàn thứ tự PropertySource**.

Nếu yêu cầu là giữ precedence giữa các tên ở từng nguồn, implementation phải kiểm tra từng PropertySource và có logic phức tạp hơn. Khi đó cần test kỹ những tổ hợp như CLI cũ + file mới, env cũ + CLI mới.

### 15.2. Alias không thay thế kế hoạch migration

Tài liệu vận hành nên công bố:

- Tên canonical mới.
- Các tên cũ được hỗ trợ.
- Quy tắc chuyển đổi đơn vị và kiểu dữ liệu.
- Hành vi nếu cả tên cũ và mới được khai báo.
- Cách báo lỗi khi legacy value không hợp lệ.
- Phiên bản dự kiến bỏ alias.

Nếu không có giới hạn, EPP có thể trở thành một lớp chuyển đổi tên khó duy trì.

## 16. Có thể làm gì bằng ConfigurableEnvironment?

Ở giai đoạn EPP, environment cho phép:

~~~java
String appName =
        environment.getProperty("spring.application.name");

String mode =
        environment.getProperty("company.deployment.mode", "local");

boolean exists =
        environment.containsProperty("company.feature.enabled");
~~~

Và quản lý PropertySource:

~~~java
var sources = environment.getPropertySources();

if (!sources.contains("company.platform.defaults")) {
    sources.addLast(customSource);
}
~~~

Tuy nhiên, **Environment.getProperty** chỉ cho thấy kết quả tra cứu từ những nguồn đã được đăng ký tại thời điểm đó. Nếu Config Data chưa nạp, nó không thể đọc một property chỉ nằm trong application.yml chưa được xử lý.

### 16.1. Đừng biến EPP thành service đọc config theo request

Nếu Controller cần chọn cấu hình theo tenant mỗi request, EnvironmentPostProcessor không phải hook đó. Nó được thiết kế cho giai đoạn khởi động, không phải một service runtime đa tenant.

Có thể dùng Binder API, một registry immutable hoặc một hệ thống config service phù hợp tùy dữ liệu, quyền truy cập và vòng đời.

## 17. Logging và DeferredLogFactory

Logging của Spring Boot được chuẩn bị rất sớm; nhiều giá trị logging có thể đã được đọc trước khi một EPP custom chạy.

Vì vậy:

- Không mặc định rằng thêm **logging.level.root** vào source ở EPP chạy sau Config Data sẽ điều chỉnh toàn bộ pha logging ban đầu.
- Với property logging cần được đọc sớm, ưu tiên env var, JVM system property hoặc CLI, trừ khi đã xác định chính xác thứ tự bootstrap.
- Tránh dùng logger thông thường trong processor mà không xét trạng thái logging system.

Một số phiên bản Boot hỗ trợ cung cấp **DeferredLogFactory** trong constructor của EPP, để trì hoãn output logging đến thời điểm phù hợp.

Ví dụ ý tưởng:

~~~java
import org.apache.commons.logging.Log;
import org.springframework.boot.logging.DeferredLogFactory;

public final class DiagnosticEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    private final Log log;

    public DiagnosticEnvironmentPostProcessor(
            DeferredLogFactory factory) {
        this.log = factory.getLog(getClass());
    }

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment env,
            SpringApplication app) {
        log.info("Installing company environment defaults");
    }
}
~~~

Các package Boot nâng cao cần được đối chiếu với phiên bản đang chạy. **Không cần DeferredLogFactory** cho processor chỉ thêm một Map và không phát log.

### 17.1. Không log secret

Deferred logging chỉ điều chỉnh thời điểm phát log. Nó không tự che token, password hay key. Không in toàn bộ Environment, MapPropertySource hoặc exception message chứa thông tin nhạy cảm.

## 18. Bootstrap context không phải ApplicationContext

Trong các phiên bản Boot có API thích hợp, factory tạo EPP có thể cung cấp **ConfigurableBootstrapContext** qua constructor, bên cạnh **DeferredLogFactory**.

Ý tưởng:

~~~java
public SomeEnvironmentPostProcessor(
        DeferredLogFactory logFactory,
        ConfigurableBootstrapContext bootstrapContext) {
    // Lưu hoặc tái sử dụng một tài nguyên bootstrap khi cần.
}
~~~

Bootstrap context hữu ích cho tài nguyên khởi tạo đặc biệt cần chia sẻ ở giai đoạn sớm. Nó **không phải** Spring ApplicationContext hoàn chỉnh, không phải nơi inject repository hoặc service bình thường.

### 18.1. Lưu ý nâng cấp Spring Boot 4

Không chỉ EPP đổi package. Một số API liên quan BootstrapRegistry/BootstrapContext cũng có thay đổi package. Khi di trú, xem migration guide và API tương ứng, tránh copy import Boot 3 sang Boot 4.

### 18.2. Khi nào không cần?

Nếu chỉ tạo:

~~~java
new MapPropertySource("companyDefaults", Map.of(...))
~~~

thì không cần thêm bootstrap context. Giữ extension nhỏ giúp ít điểm lỗi hơn.

## 19. Không @Autowired bean ứng dụng trong EPP

Ví dụ sai về kiến trúc:

~~~java
@Component
public class BadProcessor implements EnvironmentPostProcessor {

    @Autowired
    private CustomerRepository repository;

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment env,
            SpringApplication app) {
        // Không thể dựa vào repository như bean đã sẵn sàng.
    }
}
~~~

Vì EPP chạy trước context refresh và được discover bằng factory, repository chưa sẵn sàng theo vòng đời thông thường.

Không nên dùng static ApplicationContext holder để “lấy trộm” bean từ một context trước đó: điều này có thể thất bại trong test hoặc khi nhiều ApplicationContext tồn tại.

Nếu thật sự cần dữ liệu từ database hoặc remote service khi bootstrap, cần một integration được thiết kế riêng với authentication, timeout, failure policy và lifecycle phù hợp.

## 20. Idempotency và tên nguồn

Một EPP có thể được gọi lại trên cùng Environment trong test hoặc một flow bootstrap đặc biệt. Do đó tên source nên ổn định và processor không nên thêm duplicate source vô điều kiện.

Ví dụ:

~~~java
String sourceName = "company.platform.defaults";

if (!environment.getPropertySources().contains(sourceName)) {
    environment.getPropertySources().addLast(
            new MapPropertySource(sourceName, defaults)
    );
}
~~~

### 20.1. Nếu source đã tồn tại thì sao?

Có vài lựa chọn:

- Bỏ qua vì processor idempotent.
- So sánh với dữ liệu dự kiến và báo lỗi nếu trùng tên bất thường.
- Replace nếu nguồn do chính processor sở hữu và đây là chính sách đã thiết kế.

**Không replace mù.** Một source trùng tên có thể thuộc thư viện khác. Tên dạng namespace giúp giảm va chạm.

### 20.2. Không sửa mutable global state

Không nên lưu Environment trong static field. Cũng không nên dùng System.setProperty như một cách truyền giá trị tùy tiện giữa các lần test hoặc nhiều ứng dụng cùng JVM. Giữ thay đổi nằm trong Environment đang được truyền vào.

## 21. File tùy chọn và file bắt buộc

Với nguồn config bổ sung, cần có hợp đồng rõ:

| Tình huống | Nguồn tùy chọn | Nguồn bắt buộc |
| --- | --- | --- |
| File không tồn tại | Có thể bỏ qua | Fail-fast |
| File tồn tại nhưng không đọc được | Thường báo lỗi | Báo lỗi |
| File sai định dạng | Báo lỗi trừ khi có chính sách khác | Báo lỗi |
| Giá trị sai kiểu | Không nên âm thầm bỏ qua | Báo lỗi |
| Remote service không phản hồi | Có timeout/fallback theo thiết kế | Timeout rồi fail-fast |
| Giá trị nhạy cảm | Không log raw value | Không log raw value |

Không nên viết một catch(Exception) rồi return đối với mọi lỗi. Việc ấy có thể biến một lỗi deployment nghiêm trọng thành giá trị fallback khó phát hiện.

### 21.1. Có thể dùng optional của Config Data

Nếu yêu cầu chỉ là thêm file có thể thiếu:

~~~yaml
spring:
  config:
    import: "optional:file:./extra/application.yml"
~~~

thường dễ hiểu hơn một EPP tự implement logic kiểm tra file.

## 22. Chi phí I/O trong bootstrap

EnvironmentPostProcessor nằm trên đường khởi động, nên thao tác nặng có thể kéo dài thời gian toàn bộ ứng dụng sẵn sàng.

Những việc cần tránh:

- Gọi network không có timeout.
- Retry vô hạn khi secret/config service không phản hồi.
- Quét filesystem hoặc classpath không giới hạn.
- Truy vấn database bằng kết nối phụ thuộc auto-configuration chưa sẵn sàng.
- Tải toàn bộ cấu hình của hàng nghìn tenant dù ứng dụng chỉ cần một nhóm.
- Gọi các chức năng nghiệp vụ có side effect.

Nếu I/O là bắt buộc:

1. Đặt timeout và giới hạn retry.
2. Xác định chính sách nếu nguồn không sẵn sàng.
3. Không đọc secret vượt phạm vi cần thiết.
4. Làm cho thao tác idempotent khi có thể.
5. Giữ thông báo lỗi đủ xác định nguyên nhân.
6. Viết test cho thiếu file, permission denied và timeout.
7. Tránh giả định có bean để hỗ trợ request.

**EPP nên làm ít việc nhưng đúng thời điểm.**

## 23. Bảo mật và quản lý secret

Spring Boot cho phép tùy biến Environment nhưng điều đó không đồng nghĩa nên tự viết một hệ thống giải mã secret trong EPP.

Khi giá trị là token, password hoặc private key:

- Không hardcode key giải mã vào JAR.
- Dùng secret store/integration chuyên dụng khi phù hợp.
- Kiểm soát identity và permission của tiến trình.
- Không log toàn bộ PropertySource hoặc record config có secret.
- Không đưa secret vào exception message.
- Xác định rotation/reload riêng nếu cần thay đổi runtime.
- Không phơi bày config qua endpoint công khai.
- Chỉ nạp đúng secret mà module cần.

Nếu dùng EPP như một phần của tích hợp secret, ranh giới trách nhiệm và chính sách an toàn cần được thiết kế rõ. Một MapPropertySource không tự mang lại caching an toàn, token rotation hoặc audit logging.

## 24. Unit test logic thêm PropertySource

Một EPP đơn giản có thể test trực tiếp mà không tạo ApplicationContext.

Ví dụ với JUnit Jupiter và AssertJ:

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class CompanyDefaultsEnvironmentPostProcessorTest {

    private final CompanyDefaultsEnvironmentPostProcessor processor =
            new CompanyDefaultsEnvironmentPostProcessor();

    @Test
    void addsExpectedDefaults() {
        StandardEnvironment environment = new StandardEnvironment();

        processor.postProcessEnvironment(
                environment,
                new SpringApplication(Object.class)
        );

        assertThat(environment.getProperty(
                "company.http.connect-timeout")).isEqualTo("2s");
        assertThat(environment.getProperty(
                "company.http.max-connections")).isEqualTo("20");
    }

    @Test
    void doesNotOverrideHigherPriorityValue() {
        StandardEnvironment environment = new StandardEnvironment();

        environment.getPropertySources().addFirst(
            new MapPropertySource("testOverride", Map.of(
                "company.http.max-connections", "70"
            ))
        );

        processor.postProcessEnvironment(
                environment,
                new SpringApplication(Object.class)
        );

        assertThat(environment.getProperty(
                "company.http.max-connections")).isEqualTo("70");
    }

    @Test
    void canRunTwiceOnSameEnvironment() {
        StandardEnvironment environment = new StandardEnvironment();
        SpringApplication application = new SpringApplication(Object.class);

        processor.postProcessEnvironment(environment, application);
        processor.postProcessEnvironment(environment, application);

        assertThat(environment.getPropertySources()
                .contains("company.platform.defaults")).isTrue();
    }
}
~~~

Test xác nhận:

- Processor có thêm source và giá trị đúng.
- addLast không che một nguồn ưu tiên cao hơn.
- Code không bị lỗi khi gọi lại trên cùng Environment.

**Test này không xác nhận spring.factories được discover**, vì nó gọi phương thức trực tiếp.

## 25. Integration test discovery qua SpringApplication

Để kiểm tra Spring Boot thực sự tìm được EPP trong META-INF/spring.factories, cần test khởi động SpringApplication.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.Environment;

import static org.assertj.core.api.Assertions.assertThat;

class EnvironmentProcessorDiscoveryTest {

    @Test
    void registersCustomPropertySourceAtStartup() {
        SpringApplication application =
                new SpringApplication(TestApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context =
                application.run()) {

            Environment env = context.getEnvironment();

            assertThat(env.getProperty(
                "company.http.connect-timeout")).isEqualTo("2s");
        }
    }

    @org.springframework.boot.SpringBootConfiguration
    @org.springframework.boot.autoconfigure.EnableAutoConfiguration
    static class TestApplication {}
}
~~~

Bài test có ý nghĩa khi:

- spring.factories nằm trong runtime classpath test.
- Không có nguồn ưu tiên cao hơn vô tình override giá trị đang assert.
- TestApplication đủ tối thiểu để khởi động context.
- Class processor được đóng gói và load đúng.

Một unit test trực tiếp có thể pass trong khi integration test fail vì key spring.factories sai; do đó cần phân biệt hai loại test.

### 25.1. Test trong thư viện đóng gói riêng

Nếu processor thuộc một library JAR, có thể tạo ứng dụng test tiêu thụ library như dependency thật. Cách này giúp phát hiện resource file bị bỏ qua hoặc sai khi đóng gói.

## 26. Kiểm thử thứ tự so với Config Data

Nếu processor cần đọc:

~~~java
String mode =
        environment.getProperty("company.deployment.mode");
~~~

mà mode nằm trong application.yml, một unit test tự tạo MapPropertySource với key đó chưa chứng minh **order** chính xác.

Cần integration test SpringApplication nạp YAML thực tế rồi xác nhận processor nhìn thấy giá trị.

Ví dụ:

~~~yaml
company:
  deployment:
    mode: production
~~~

Với processor chạy sau ConfigDataEnvironmentPostProcessor, mode có thể là production. Nếu chạy trước, nó có thể chưa có mặt.

Nên kiểm thử các nguồn đúng với cách deploy: file nền, profile-specific file, environment variable, system property hoặc CLI.

## 27. Precedence với file, env và CLI

Giả sử:

~~~yaml
company:
  http:
    max-connections: 30
~~~

Môi trường:

~~~bash
COMPANY_HTTP_MAXCONNECTIONS=40 java -jar demo.jar   --company.http.max-connections=50
~~~

EPP thêm default 20 bằng addLast.

Giá trị cuối thông thường là **50** vì command-line có ưu tiên cao hơn những nguồn còn lại.

| Nguồn | Giá trị |
| --- | ---: |
| EPP default addLast | 20 |
| application.yml | 30 |
| OS environment | 40 |
| Command-line | 50 |

Nếu EPP addFirst source default, kết quả có thể khác và làm operator mất quyền override. Do đó nên có integration test xác nhận precedence thay vì chỉ test rằng default tồn tại.

### 27.1. Không nhầm naming với precedence

Nếu biến môi trường đặt sai tên:

~~~text
COMPANY_HTTP_MAX_CONNECTIONS
~~~

thay vì cách chuyển canonical:

~~~text
COMPANY_HTTP_MAXCONNECTIONS
~~~

ứng dụng có thể không dùng override mong muốn. Khi debug, hãy phân biệt **tên key không bind được** và **một nguồn ưu tiên cao hơn thắng**.

## 28. Vì sao không nên dùng ApplicationRunner để thêm source?

ApplicationRunner chạy sau khi context được refresh và nhiều bean đã được tạo. Nếu một bean @ConfigurationProperties đã bind timeout=5s, rồi runner thêm source timeout=10s, bean đó không tự đổi thành 10s.

EnvironmentPostProcessor được thiết kế chính cho việc chỉnh Environment sớm hơn.

Tuy nhiên, nếu mục tiêu chỉ là chạy một tác vụ khi ứng dụng sẵn sàng, ApplicationRunner lại là hook đúng hơn. Không nên chuyển một tác vụ nghiệp vụ vào EPP chỉ vì muốn nó chạy sớm.

## 29. Vì sao không nên dùng EPP cho dynamic refresh?

Một số người nghĩ:

~~~java
Map<String, Object> values = new HashMap<>();
sources.addFirst(new MapPropertySource("dynamic", values));
~~~

rồi sau startup sửa values sẽ khiến mọi bean nhận giá trị mới.

Điều này không được bảo đảm. @Value và @ConfigurationProperties thường được xử lý khi bean được tạo; chỉnh một MapPropertySource đang tồn tại không tự rebind mọi object.

Nếu cần cấu hình thay đổi nóng:

- Xác định nguồn nào thật sự có khả năng được nạp lại.
- Có cơ chế đồng bộ/atomic snapshot.
- Có validation trước khi đưa giá trị mới vào sử dụng.
- Có quy tắc rollback khi cấu hình mới sai.
- Có phương thức reconfigure các client/bean phụ thuộc.
- Có giới hạn quyền truy cập và bảo mật secret.

EPP chỉ cung cấp một hook startup. Nó không tự xây dựng hệ thống runtime refresh.

## 30. Không dùng EPP làm service đa tenant

Giả sử một hệ thống có hàng nghìn tenant và mỗi tenant có cấu hình thay đổi theo request. Không nên cố nạp toàn bộ vào Environment lúc startup rồi dùng EPP làm cơ chế quản lý tenant.

Các vấn đề sẽ xuất hiện:

- Memory và thời gian startup.
- Quyền truy cập giữa tenant.
- Config thay đổi nhưng object bind cũ không refresh.
- Secret bị lưu trong Environment lâu hơn cần thiết.
- Khó phân biệt lỗi theo tenant.

Nếu cấu hình tenant thật sự là dữ liệu runtime, cần một service và storage/registry có vòng đời riêng. Nếu tập tenant nhỏ và cố định lúc startup, một Map qua @ConfigurationProperties có thể đủ.

## 31. Lỗi thường gặp: processor không chạy

Các nguyên nhân phổ biến:

| Dấu hiệu | Nguyên nhân cần xem |
| --- | --- |
| Không có source custom | spring.factories sai path hoặc key |
| Source không có trong executable JAR | Resources bị loại khi build |
| Lỗi ClassNotFound | Tên class hoặc dependency sai |
| Lỗi tạo instance | Constructor không được factory hỗ trợ |
| Chạy Boot 4 nhưng dùng import/key Boot 3 | Package migration chưa hoàn tất |
| Không thấy property từ YAML | Processor chạy trước Config Data |
| Source có nhưng giá trị không thắng | PropertySource precedence |
| Processor skip silently | File optional không tồn tại hoặc điều kiện return |
| Bean lỗi bind | Property có mặt nhưng conversion/validation fail |

Trước khi thay addLast thành addFirst để “chữa lỗi”, hãy xác định processor có thực sự chạy và source có xuất hiện không.

### 31.1. In tên nguồn một cách an toàn

Trong môi trường test có thể liệt kê:

~~~java
for (PropertySource<?> source
        : environment.getPropertySources()) {
    System.out.println(source.getName());
}
~~~

Đoạn này yêu cầu environment có kiểu ConfigurableEnvironment và import PropertySource phù hợp.

Không in toàn bộ dữ liệu cấu hình vì có thể chứa password, token và thông tin nhạy cảm.

## 32. Lỗi thường gặp: cấu hình sai kiểu

Nếu EPP thêm:

~~~properties
company.http.max-connections=not-a-number
~~~

và bean đích có:

~~~java
@ConfigurationProperties(prefix = "company.http")
public record HttpProperties(int maxConnections) {}
~~~

Binder có thể báo lỗi conversion. Đây không phải bằng chứng EPP không hoạt động; ngược lại, nó có thể đã đưa key vào Environment chính xác nhưng giá trị không hợp lệ.

Nếu giá trị là 0 và có **@Min(1)** thì đó là lỗi validation, không phải conversion.

Để chẩn đoán, lần theo:

~~~text
Source được thêm?
       |
       v
Property name đúng?
       |
       v
Source precedence?
       |
       v
Giá trị raw?
       |
       v
Chuyển sang kiểu Java?
       |
       v
Validation?
~~~

Không được dùng default ưu tiên cao để che một giá trị production sai. Cần sửa dữ liệu hoặc chính sách triển khai.

## 33. Lỗi thường gặp: đặt tên source trùng

Hai thư viện đều thêm source **customDefaults**. Khi đó có thể xảy ra xung đột tên và một thư viện không hoạt động như mong muốn.

Chọn tên rõ namespace:

~~~text
company.gateway.defaults
company.billing.legacy-aliases
company.shared.extra-properties
~~~

Với một nguồn đã tồn tại:

~~~java
if (sources.contains(sourceName)) {
    return;
}
~~~

là một lựa chọn idempotent, nhưng nếu tên đó bất thường và khác nội dung, có thể cần báo lỗi. Không nên tự động replace nguồn chưa rõ thuộc về ai.

## 34. Lỗi thường gặp: thay đổi logging quá muộn

Một processor chạy sau Config Data có thể được gọi trước context refresh, nhưng không có nghĩa nó chạy trước mọi lần logging system đọc cấu hình.

Nếu cần:

~~~text
logging.level.root=DEBUG
logging.config=classpath:logback-custom.xml
~~~

nên cung cấp bằng nguồn Boot hỗ trợ đủ sớm, hoặc xác minh cực kỳ rõ lifecycle/order của extension. Không nên chỉ thêm property bằng addLast rồi kết luận log level chắc chắn thay đổi từ thời điểm JVM vừa chạy.

## 35. Lỗi thường gặp: nuốt lỗi I/O

Code kém:

~~~java
try {
    loadFileAndAddProperties();
} catch (Exception ignored) {
    // Bỏ qua mọi lỗi.
}
~~~

Nếu file là nguồn bắt buộc, việc nuốt lỗi sẽ khiến ứng dụng khởi động bằng cấu hình thiếu.

Cách tốt hơn:

~~~java
try {
    loadFileAndAddProperties();
} catch (IOException e) {
    throw new IllegalStateException(
            "Failed to initialize company configuration source",
            e
    );
}
~~~

Nếu nguồn được phép vắng mặt, chỉ bỏ qua trường hợp vắng mặt theo quy tắc rõ. File tồn tại nhưng không đọc được vẫn nên báo lỗi.

## 36. Lỗi thường gặp: nghĩ @Autowired hoạt động

Một EPP không phải bean của application context thông thường. Vì vậy không thể trông đợi:

~~~java
@Autowired
private SecretService secretService;
~~~

được inject theo cách của @Service đã khởi tạo. Dùng API bootstrap mà Boot hỗ trợ, và hạn chế phụ thuộc vào service graph.

Nếu bạn thật sự cần Spring bean để xử lý một việc sau đó, có thể EPP không phải hook phù hợp.

## 37. Tình huống platform defaults hoàn chỉnh

Một thư viện cung cấp:

~~~text
company.http.connect-timeout
company.http.read-timeout
company.http.max-connections
company.audit.enabled
~~~

EPP thêm low-priority defaults:

~~~java
Map<String, Object> defaults = Map.of(
        "company.http.connect-timeout", "2s",
        "company.http.read-timeout", "5s",
        "company.http.max-connections", "20",
        "company.audit.enabled", "false"
);

sources.addLast(
        new MapPropertySource(
                "company.platform.defaults",
                defaults
        )
);
~~~

Ứng dụng khai báo:

~~~yaml
company:
  http:
    read-timeout: 12s
    max-connections: 40
  audit:
    enabled: true
~~~

Với thứ tự bình thường, bean HttpProperties nhận **connectTimeout=2s** từ default, **readTimeout=12s** và **maxConnections=40** từ YAML.

Khi chạy:

~~~bash
COMPANY_HTTP_MAXCONNECTIONS=80 java -jar demo.jar
~~~

giá trị maxConnections có thể thành 80 từ environment variable.

Thiết kế này đáp ứng mục tiêu: **thư viện cung cấp mặc định, ứng dụng và operator giữ quyền override**.

## 38. Khi nào không nên viết EnvironmentPostProcessor?

Không nên dùng nếu:

1. Chỉ cần bind một nhóm property: dùng @ConfigurationProperties.
2. Chỉ cần một scalar: dùng Environment hoặc @Value.
3. Chỉ muốn import thêm file YAML/properties: dùng spring.config.import.
4. Cần tạo bean có điều kiện: dùng @ConditionalOnProperty hoặc auto-configuration.
5. Cần thực hiện tác vụ sau startup: dùng ApplicationRunner.
6. Cần tùy biến bean definition/context: xem ApplicationContextInitializer hoặc hook context phù hợp.
7. Cần truy vấn secret/config từ một hệ thống riêng: ưu tiên integration chuẩn của hệ thống ấy.
8. Cần refresh config giữa lúc chạy: dùng cơ chế refresh có validation và synchronization.
9. Cần chọn prefix khi xử lý runtime: xem Binder API hoặc registry thay vì startup EPP.
10. Chỉ muốn override CLI/env ngoài ý muốn: nên xem lại chính sách precedence.

**EPP có giá trị khi yêu cầu cần một PropertySource hoặc biến đổi Environment ở giai đoạn bootstrap**, không phải như phương pháp mặc định cho mọi cấu hình.

## 39. Checklist phát hành thư viện có EPP

- [ ] Đã chọn phiên bản Spring Boot đích.
- [ ] Interface và spring.factories key đúng với Boot 3 hoặc 4.
- [ ] File META-INF/spring.factories nằm trên runtime classpath.
- [ ] Class processor có thể được SpringFactoriesLoader tạo.
- [ ] Không dùng @Autowired các bean nghiệp vụ.
- [ ] Order được xác định rõ nếu phụ thuộc Config Data.
- [ ] Tên PropertySource có namespace và không trùng.
- [ ] addFirst/addLast đúng chính sách override.
- [ ] Không xóa/replace source mà processor không sở hữu.
- [ ] File optional và required có hành vi riêng.
- [ ] I/O được giới hạn và có timeout nếu cần.
- [ ] Không log secret hoặc toàn bộ Environment.
- [ ] Default không che giá trị cấu hình production sai.
- [ ] Có unit test kiểm tra dữ liệu và idempotency.
- [ ] Có integration test kiểm tra discovery bằng SpringApplication.
- [ ] Có test priority với YAML, env, JVM system properties hoặc CLI.
- [ ] Có test nâng cấp Boot 3 → 4 nếu thư viện hỗ trợ cả hai.
- [ ] Có tài liệu cho người vận hành về key, default và override.

## 40. Tài liệu chính thức

Đối chiếu các hướng dẫn theo phiên bản ứng dụng:

- Spring Boot — Customize the Environment or ApplicationContext Before It Starts: https://docs.spring.io/spring-boot/how-to/application.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot 3.5 — EnvironmentPostProcessor: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html
- Spring Boot 4.x — EnvironmentPostProcessor: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/EnvironmentPostProcessor.html
- Spring Boot — ConfigDataEnvironmentPostProcessor: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/config/ConfigDataEnvironmentPostProcessor.html

Những hướng dẫn cũ có thể vẫn dùng package org.springframework.boot.env.EnvironmentPostProcessor. Khi học hoặc nâng cấp, cần kiểm tra đúng dòng Spring Boot để tránh một đoạn code hợp lệ về ý tưởng nhưng sai import hoặc key discovery.

## 41. Tổng kết

**EnvironmentPostProcessor** là hook Spring Boot để **chỉnh Environment trước ApplicationContext refresh**. Nó đặc biệt phù hợp khi muốn thêm nguồn mặc định, chuyển đổi một nhóm property legacy hoặc nạp một nguồn cấu hình đặc thù có kiểm soát ngay trong bootstrap.

Các điểm cần nhớ:

- Boot 2/3 dùng **org.springframework.boot.env.EnvironmentPostProcessor**; Boot 4 dùng **org.springframework.boot.EnvironmentPostProcessor**.
- Đăng ký implementation bằng **META-INF/spring.factories**, đúng key của phiên bản.
- **addLast** thường phù hợp default; **addFirst** tạo source ưu tiên cao và cần lý do rõ.
- **Order của processor** và **precedence của PropertySource** là hai khái niệm khác nhau.
- Khi cần property từ application.yml, hãy xem thứ tự tương đối với ConfigDataEnvironmentPostProcessor.
- Không kỳ vọng EPP được @Autowired bean nghiệp vụ hoặc ApplicationContext đã sẵn sàng.
- Không thêm spring.config.location/profiles.active quá muộn rồi nghĩ Config Data tự nạp lại.
- Không dùng EPP như một hệ dynamic refresh hoặc secret manager tự chế.
- Kiểm thử **logic**, **discovery**, **precedence** và **failure policy** riêng biệt.
- Nếu **spring.config.import** hoặc @ConfigurationProperties giải quyết được yêu cầu, nên chọn cách đơn giản hơn.

Câu hỏi quyết định là: **“Thuộc tính này có cần được đưa vào Environment trước context refresh, và cách nạp Config Data thông thường đã đủ chưa?”**. Nếu thực sự cần can thiệp sớm, EnvironmentPostProcessor là công cụ hiệu quả khi áp dụng đúng lifecycle, thứ tự nguồn và chính sách xử lý lỗi.
