# Đăng ký bằng @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties

Spring Boot khuyến khích gom các giá trị cấu hình có liên quan vào một object có kiểu dữ liệu rõ ràng bằng **@ConfigurationProperties**. Thay vì đọc từng chuỗi cấu hình rải rác bằng @Value, ứng dụng có thể định nghĩa một class hoặc record chứa các trường như host, port, timeout và retry rồi để Spring Boot bind dữ liệu từ Environment vào object đó.

Tuy nhiên, **khai báo @ConfigurationProperties trên một kiểu không tự động bảo đảm kiểu đó đã trở thành bean trong ApplicationContext**. Spring Boot cần biết những kiểu cấu hình nào phải được đăng ký. Hai cơ chế phổ biến là:

- **@ConfigurationPropertiesScan**: quét các package được chỉ định để tìm các kiểu mang @ConfigurationProperties phù hợp rồi đăng ký chúng.
- **@EnableConfigurationProperties**: đăng ký tường minh một hoặc nhiều kiểu @ConfigurationProperties được liệt kê.

Cả hai đều hỗ trợ việc tạo bean cấu hình và binding, nhưng khác nhau về **cách lựa chọn kiểu, phạm vi ảnh hưởng và tình huống nên dùng**. Bài học này đi từ một ứng dụng nhỏ đến thư viện auto-configuration, bao gồm binding JavaBean/record, validation, kiểm thử và cách chẩn đoán những lỗi thường gặp.

## 1. Phân biệt ba việc: khai báo, đăng ký và binding

Trước khi chọn annotation đăng ký, cần tách ba khái niệm:

1. **Khai báo cấu trúc**: class có @ConfigurationProperties mô tả prefix và các field/constructor parameter cần nhận giá trị.
2. **Đăng ký bean**: Spring ApplicationContext phải có một bean của kiểu properties đó.
3. **Binding**: Spring Boot lấy các giá trị từ Environment để gán vào bean bằng JavaBean setters hoặc constructor binding thích hợp.

Ví dụ:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {
    private String host;

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }
}
~~~

Annotation này nói rằng MailProperties cần dữ liệu dưới prefix **app.mail**. Nhưng để inject được MailProperties:

~~~java
public MailService(MailProperties properties) {
    this.properties = properties;
}
~~~

thì Spring còn phải đăng ký một bean MailProperties bằng scan, enable, component scanning hoặc một factory method phù hợp.

Nếu không đăng ký, có thể gặp exception kiểu:

~~~text
No qualifying bean of type 'com.example.demo.config.MailProperties'
available
~~~

Lỗi này nói về **thiếu bean**, không nhất thiết nói rằng key cấu hình app.mail.host không tồn tại. Một lỗi binding và một lỗi bean registration là hai vấn đề khác nhau.

### 1.1. Luồng từ cấu hình đến consumer

~~~text
application.yml / environment variables / command line
                         │
                         ▼
                 Spring Environment
                         │
                         ▼
@ConfigurationProperties(prefix = "app.mail")
                         │
                         ▼
Đăng ký kiểu MailProperties thành bean
    ├── @ConfigurationPropertiesScan
    └── @EnableConfigurationProperties
                         │
                         ▼
      Spring Boot bind và chuyển đổi kiểu
                         │
                         ▼
    MailProperties được inject vào service
~~~

Spring Boot có nhiều property source và quy tắc ưu tiên giá trị. Hai annotation của bài học chủ yếu quyết định **kiểu properties nào được đăng ký**, không quyết định một file YAML cụ thể phải được dùng.

## 2. Ví dụ xuyên suốt: cấu hình kết nối mail

Ta xây một ứng dụng có cấu trúc:

~~~text
src/main/java/com/example/demo/
├── DemoApplication.java
├── config/
│   └── MailProperties.java
└── mail/
    ├── MailEndpoint.java
    └── MailConfiguration.java

src/main/resources/
└── application.yml
~~~

File application.yml:

~~~yaml
app:
  mail:
    host: smtp.example.internal
    port: 2525
    connect-timeout: 4s
~~~

Class properties dùng JavaBean binding:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    private String host;
    private int port = 25;
    private Duration connectTimeout = Duration.ofSeconds(3);

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public int getPort() {
        return port;
    }

    public void setPort(int port) {
        this.port = port;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }
}
~~~

Spring Boot có thể bind:

| Property | Trường Java | Kết quả |
|---|---|---|
| app.mail.host | host | smtp.example.internal |
| app.mail.port | port | 2525 |
| app.mail.connect-timeout | connectTimeout | Duration.ofSeconds(4) |

Nếu port không được khai báo, giá trị mặc định 25 trong object vẫn có thể được giữ lại. Nếu connect-timeout không được khai báo, ví dụ này mặc định 3 giây.

Điểm quan trọng: **@ConfigurationProperties không phải là annotation đánh dấu component để component scan thông thường tự phát hiện**. Ta sẽ chọn một trong hai cách đăng ký properties bean.

## 3. Cách 1: @ConfigurationPropertiesScan

**@ConfigurationPropertiesScan** nằm trong package:

~~~java
org.springframework.boot.context.properties.ConfigurationPropertiesScan
~~~

Annotation này yêu cầu Spring Boot tìm những kiểu @ConfigurationProperties phù hợp trong các package được quét và đăng ký chúng với ApplicationContext.

Ví dụ đặt trên main application class:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Khi không chỉ định package, scan bắt đầu từ **package của class có @ConfigurationPropertiesScan**. Trong ví dụ là com.example.demo, do đó nó bao gồm com.example.demo.config và các subpackage khác.

Spring Boot tìm thấy MailProperties có @ConfigurationProperties và đăng ký bean để binding.

### 3.1. @SpringBootApplication không mặc định thay thế @ConfigurationPropertiesScan

@SpringBootApplication bao gồm những cơ chế quan trọng như component scan và auto-configuration, nhưng **không có nghĩa mọi class chỉ mang @ConfigurationProperties sẽ tự động được quét và đăng ký**.

Với class MailProperties không có @Component và không được khai báo bằng @Bean, cần có một cơ chế đăng ký như @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties.

Nếu bạn chỉ thêm @ConfigurationProperties cho class rồi chờ @SpringBootApplication tự nhận mọi properties class, ứng dụng có thể thiếu bean MailProperties.

### 3.2. Chỉ định package bằng basePackages

Có thể cấu hình rõ package cần quét:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan(
        basePackages = "com.example.demo.config")
public class DemoApplication {
    // ...
}
~~~

Spring Boot sẽ tìm các kiểu properties trong package chỉ định và các subpackage liên quan, thay vì dựa vào package mặc định của class mang annotation.

Đây là cách hữu ích khi:

- Cấu hình được tập trung trong một package riêng.
- Main application class nằm ở package không bao phủ properties classes.
- Muốn giới hạn những kiểu configuration properties được tự động đăng ký.

Nhược điểm của chuỗi package là dễ bị sai khi refactor package hoặc đổi tên module mà quên cập nhật annotation.

### 3.3. Chỉ định package bằng basePackageClasses

Một cách bền vững hơn là tham chiếu class:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan(
        basePackageClasses = MailProperties.class)
public class DemoApplication {
    // ...
}
~~~

Spring Boot dùng **package chứa MailProperties** làm điểm bắt đầu scan, không chỉ quét duy nhất class đó.

Nếu muốn tách tên package khỏi một kiểu cấu hình cụ thể, có thể tạo marker class hoặc interface trong package mong muốn:

~~~java
package com.example.demo.config;

public interface ConfigurationPackageMarker {
}
~~~

Sau đó:

~~~java
@ConfigurationPropertiesScan(
        basePackageClasses = ConfigurationPackageMarker.class)
~~~

Việc này phù hợp khi muốn scan cả package với nhiều class properties mà không ràng buộc vào tên một class cụ thể.

### 3.4. Có thể khai báo nhiều package

Các thuộc tính basePackages và basePackageClasses hỗ trợ cấu hình nhiều vị trí tìm kiếm:

~~~java
@ConfigurationPropertiesScan(
        basePackages = {
                "com.example.shared.config",
                "com.example.demo.config"
        })
~~~

Hãy mở rộng phạm vi một cách có chủ đích. Một scan root quá rộng có thể đăng ký những configuration properties không cần thiết hoặc khó xác định lớp nào chịu trách nhiệm bật một nhóm cấu hình.

## 4. Cách 2: @EnableConfigurationProperties

**@EnableConfigurationProperties** nằm trong package:

~~~java
org.springframework.boot.context.properties.EnableConfigurationProperties
~~~

Annotation này cho phép liệt kê **tường minh** các kiểu @ConfigurationProperties cần đăng ký.

Ví dụ:

~~~java
package com.example.demo;

import com.example.demo.config.MailProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(MailProperties.class)
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Spring Boot đăng ký kiểu MailProperties được chỉ định và bind các giá trị có prefix app.mail.

Điểm khác với @ConfigurationPropertiesScan là **không cần Spring phải đi tìm MailProperties bằng package scan**. Kiểu đã được nêu rõ ngay trong annotation.

### 4.1. Đăng ký nhiều kiểu properties

~~~java
@EnableConfigurationProperties({
        MailProperties.class,
        StorageProperties.class,
        ReportProperties.class
})
~~~

Khi có ba nhóm cấu hình riêng, bạn có thể đăng ký cả ba trong cùng một configuration class.

Ưu điểm của cách này:

- Danh sách types được bật được thể hiện ngay trong source.
- Không phụ thuộc properties class nằm ở package nào.
- Dễ kiểm soát registration ở một module nhỏ hoặc một auto-configuration.
- Tác dụng ít bị thay đổi do vô tình bổ sung class mới vào package đang được scan.

Nhược điểm là khi thêm một properties class mới, người phát triển phải chủ động thêm type đó vào annotation thích hợp.

### 4.2. Đặt trên một @Configuration class

Không bắt buộc đặt @EnableConfigurationProperties trên main application class. Ví dụ:

~~~java
package com.example.demo.mail;

import com.example.demo.config.MailProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(MailProperties.class)
public class MailConfiguration {

    @Bean
    MailEndpoint mailEndpoint(MailProperties properties) {
        return new MailEndpoint(
                properties.getHost(),
                properties.getPort(),
                properties.getConnectTimeout());
    }
}
~~~

Và MailEndpoint là một immutable value object:

~~~java
package com.example.demo.mail;

import java.time.Duration;

public record MailEndpoint(
        String host,
        int port,
        Duration connectTimeout) {
}
~~~

Spring sẽ xử lý MailConfiguration nếu nó được component scan hoặc import vào context. Khi đó MailProperties được đăng ký và MailEndpoint có thể nhận object cấu hình thông qua tham số của @Bean method.

Lưu ý: **@EnableConfigurationProperties chỉ có hiệu lực khi class mang annotation thực sự được Spring xử lý**. Đặt nó trên một class cấu hình nằm ngoài component scan và không được import thì sẽ không tự kích hoạt class đó.

### 4.3. Không tham số có ý nghĩa gì?

Có thể thấy:

~~~java
@EnableConfigurationProperties
~~~

Việc sử dụng annotation không liệt kê types có thể bật các thành phần hạ tầng phục vụ configuration properties, nhưng **không có nghĩa nó tự quét và đăng ký mọi properties class trong ứng dụng**.

Khi cần đăng ký một kiểu cụ thể, hãy nêu kiểu đó:

~~~java
@EnableConfigurationProperties(MailProperties.class)
~~~

hoặc sử dụng @ConfigurationPropertiesScan với phạm vi scan thích hợp.

## 5. So sánh hai cách đăng ký

| Tiêu chí | @ConfigurationPropertiesScan | @EnableConfigurationProperties |
|---|---|---|
| Cách chọn kiểu | Tìm các kiểu @ConfigurationProperties trong package được quét | Liệt kê chính xác các kiểu cần đăng ký |
| Phạm vi | Theo package, có thể cấu hình basePackages/basePackageClasses | Theo danh sách Class trong annotation |
| Khi thêm properties class | Có thể được phát hiện tự động nếu nằm trong vùng scan | Phải được đăng ký tường minh |
| Khi đổi package | Có thể ảnh hưởng nếu scan root không còn bao phủ | Ít phụ thuộc vị trí package của kiểu đã chỉ định |
| Phù hợp | Ứng dụng có nhiều nhóm cấu hình nội bộ | Cấu hình riêng, module tích hợp, auto-configuration |
| Rủi ro chính | Scan quá rộng hoặc sai package | Bỏ quên type mới trong danh sách |
| Bean được tạo | Configuration properties bean do Boot đăng ký | Configuration properties bean do Boot đăng ký |
| Cơ chế binding | Spring Boot Configuration Properties Binder | Cùng cơ chế binding của Spring Boot |

Hai annotation khác nhau ở **registration strategy**, không phải ở bộ quy tắc parse YAML hay chuyển đổi kiểu dữ liệu.

### 5.1. Nên dùng một cách rõ ràng cho cùng một type

Về thiết kế, không cần cố đăng ký một properties class bằng cả hai cách.

Ví dụ không cần thiết:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
@EnableConfigurationProperties(MailProperties.class)
public class DemoApplication {
    // ...
}
~~~

Khi hai cơ chế cùng phát hiện một kiểu configuration properties, Spring Boot có thể có cơ chế tránh trùng registration theo tên chuẩn, nhưng **đừng dựa vào sự kết hợp dư thừa đó làm mẫu thiết kế**. Một kiểu có một owner đăng ký rõ ràng sẽ dễ đọc, dễ kiểm thử và tránh nhầm lẫn về nguồn gốc bean hơn.

### 5.2. Quy tắc chọn nhanh

Nếu bạn đang viết **ứng dụng Spring Boot** và có nhiều class properties nội bộ dưới một package rõ ràng, @ConfigurationPropertiesScan thường thuận tiện.

Nếu bạn đang viết **một @Configuration hoặc @AutoConfiguration** cung cấp riêng một module/tính năng và biết chính xác các properties class cần dùng, @EnableConfigurationProperties thường hợp lý hơn.

Điều quan trọng là tránh đăng ký không chủ ý và làm rõ cấu hình nào sở hữu properties bean.

## 6. Vì sao @Component không phải lựa chọn tương đương?

Bạn có thể gặp class:

~~~java
@Component
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {
    // Các field và setters.
}
~~~

Nếu package của class này nằm trong component scan, Spring có thể đăng ký nó như bean thông thường; Spring Boot sẽ thực hiện properties binding phù hợp.

Vậy tại sao vẫn nên học hai annotation ở trên?

### 6.1. Component scanning và properties scanning khác nhau

Component scan tìm các component Spring mang stereotype như @Component. @ConfigurationPropertiesScan tìm các kiểu đánh dấu @ConfigurationProperties theo quy tắc riêng.

Đặc biệt, **@ConfigurationPropertiesScan không chọn các class được đánh dấu @Component hoặc meta-annotated @Component**. Vì vậy, nếu bạn thêm @Component vào MailProperties, bean có thể vẫn xuất hiện nhờ component scan, nhưng nó **không phải kết quả của @ConfigurationPropertiesScan**.

Từ đó dễ phát sinh nhầm lẫn: xóa @Component rồi ứng dụng đột nhiên thiếu bean nếu không có một cơ chế registration phù hợp; hoặc một class ở ngoài component scan không được đăng ký dù có @Component.

### 6.2. Constructor binding không dùng cùng mô hình với @Component

Một kiểu configuration properties immutable cần Spring Boot bind dữ liệu qua constructor. Với kiểu được đăng ký bằng @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties, Spring Boot có thể dùng constructor binding.

Nhưng một bean được tạo bằng component scanning theo @Component là bean do cơ chế regular Spring instantiation tạo ra; constructor của nó sẽ được xử lý theo dependency injection thông thường, **không phải mặc nhiên coi constructor parameters là cấu hình cần bind**.

Vì vậy, record properties hoặc immutable properties class không nên được đăng ký bằng @Component nếu bạn dựa vào constructor binding của Spring Boot.

### 6.3. Tách property holder khỏi component logic

Một class properties nên tập trung vào dữ liệu cấu hình, validation và các giá trị mặc định. Nó không cần tự thực hiện network call, khởi tạo client hay phối hợp workflow.

Thiết kế tách biệt:

~~~text
MailProperties  --(injected into)--> MailConfiguration
                                          │
                                          ▼
                                      MailEndpoint
                                          │
                                          ▼
                                     Business Service
~~~

Các thành phần nghiệp vụ được đăng ký riêng; properties class không phải service.

## 7. Binding object immutable bằng Java record

Trong Spring Boot 3, một record có một canonical constructor phù hợp có thể được dùng cho **constructor binding** mà không cần setters.

Ví dụ:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        String host,
        @DefaultValue("25") int port,
        @DefaultValue("3s") Duration connectTimeout) {
}
~~~

Khi Environment có:

~~~yaml
app:
  mail:
    host: smtp.example.internal
    connect-timeout: 5s
~~~

Boot có thể tạo MailProperties qua constructor, với host từ YAML, port mặc định 25 và connectTimeout bằng 5 giây.

Với record này, chọn **một trong hai** cách đăng ký:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
}
~~~

hoặc:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(MailProperties.class)
class MailPropertiesConfiguration {
}
~~~

Các trường record là final theo mô hình Java, nên cấu hình này không cần setters. Điều đó giúp giảm khả năng thay đổi cấu hình ngoài ý muốn sau khi bean đã được tạo.

### 7.1. @ConstructorBinding trong Spring Boot 3

Với một properties class chỉ có một constructor dùng để bind, Boot 3 có thể suy ra constructor binding. Khi có nhiều constructor và cần chỉ rõ constructor dùng để binding, có thể dùng **@ConstructorBinding** trên constructor thích hợp từ package:

~~~java
org.springframework.boot.context.properties.bind.ConstructorBinding
~~~

Trong Spring Boot 3, annotation này được dùng tại constructor, không phải như mẫu class-level @ConstructorBinding quen thuộc của một số phiên bản Boot 2.

Ví dụ minh họa:

~~~java
@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties {
    private final int limit;

    @ConstructorBinding
    public CacheProperties(int limit) {
        this.limit = limit;
    }

    public CacheProperties() {
        this(100);
    }

    public int getLimit() {
        return limit;
    }
}
~~~

Nếu chỉ có một constructor và không có tình huống ambiguous, thường không cần annotation tường minh.

### 7.2. Không gắn @Component cho record chỉ để Spring phát hiện

Sai lầm hay gặp:

~~~java
@Component
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(String host, int port) {
}
~~~

Khi regular component scanning tạo bean, Spring có thể cố giải quyết tham số constructor như những dependency kiểu String và int, thay vì bind từ app.mail.host và app.mail.port. Điều này dễ gây lỗi tạo bean.

Với record configuration properties, hãy dùng @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties.

## 8. Validation của @ConfigurationProperties

Registration bảo đảm bean được biết đến; binding đưa dữ liệu vào object. Nhưng ứng dụng còn cần biết dữ liệu **có hợp lệ không**.

Ví dụ, host không được rỗng, port phải từ 1 tới 65535, timeout cần có giá trị phù hợp.

Với JavaBean properties class:

~~~java
package com.example.demo.config;

import java.time.Duration;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    @NotBlank
    private String host;

    @Min(1)
    @Max(65535)
    private int port = 25;

    @NotNull
    private Duration connectTimeout = Duration.ofSeconds(3);

    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }

    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }

    public Duration getConnectTimeout() { return connectTimeout; }
    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }
}
~~~

Ứng dụng cần có Bean Validation provider thích hợp, thường được thêm qua:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Trong Spring Boot 3, các constraint annotation dùng namespace **jakarta.validation**. Nếu ứng dụng bind một host trống và @Validated được áp dụng, quá trình tạo/bind properties bean có thể thất bại với thông báo validation thay vì tiếp tục startup bằng cấu hình không hợp lệ.

### 8.1. Validation hoạt động với cả scan và enable

Cả @ConfigurationPropertiesScan và @EnableConfigurationProperties đều đưa type vào cùng hạ tầng configuration properties binding/validation của Spring Boot.

Không có chuyện scan tự validate còn enable không validate, hoặc ngược lại. Điều quyết định là:

- Properties bean được đăng ký và bind hay chưa.
- Annotation validation phù hợp có được khai báo không.
- Bean Validation provider có trên classpath không.
- Cấu trúc nested validation có được khai báo đúng không.

### 8.2. Nested properties và @Valid

Giả sử có nhóm credentials:

~~~yaml
app:
  mail:
    host: smtp.example.internal
    credentials:
      username: mailer
      password: example-secret
~~~

Có thể tổ chức JavaBean properties:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    @Valid
    private Credentials credentials = new Credentials();

    public Credentials getCredentials() {
        return credentials;
    }

    public void setCredentials(Credentials credentials) {
        this.credentials = credentials;
    }

    public static class Credentials {
        @NotBlank
        private String username;

        @NotBlank
        private String password;

        public String getUsername() { return username; }
        public void setUsername(String username) {
            this.username = username;
        }

        public String getPassword() { return password; }
        public void setPassword(String password) {
            this.password = password;
        }
    }
}
~~~

**@Valid** trên field nested giúp yêu cầu validation đi vào object con. Trong ví dụ cần import các annotation từ jakarta.validation và org.springframework.validation.annotation.Validated như đã minh họa ở phần trước.

Lưu ý: không log đầy đủ properties object nếu nó chứa password, token hoặc secret. Validation và debug không phải lý do để xuất secret ra log.

## 9. Relaxed binding không phụ thuộc vào cách đăng ký

Spring Boot hỗ trợ relaxed binding cho configuration properties. Chẳng hạn field Java:

~~~java
private Duration connectTimeout;
~~~

có thể nhận giá trị từ property canonical dạng kebab-case:

~~~yaml
app:
  mail:
    connect-timeout: 4s
~~~

Trong môi trường biến hệ điều hành, một tên tương ứng có thể được biểu diễn như:

~~~text
APP_MAIL_CONNECTTIMEOUT=4s
~~~

Spring Boot áp dụng quy tắc đặt tên và chuyển đổi kiểu theo nguồn property. Khi viết tài liệu và cấu hình chính thức, nên dùng canonical property names dạng kebab-case để tránh nhầm lẫn.

Các kiểu mà Binder có thể hỗ trợ gồm:

- String, boolean, số nguyên, số thực.
- Enum.
- Duration, ví dụ 250ms, 4s, 2m.
- DataSize, ví dụ 10MB hoặc 512KB.
- List, Set, Map với cấu trúc tương thích.
- Nested object.

Ví dụ:

~~~yaml
app:
  worker:
    enabled: true
    retry-count: 3
    timeout: 5s
    targets:
      - south
      - north
~~~

Các giá trị này có thể bind vào WorkerProperties nếu fields, getters/setters hoặc constructor parameters tương ứng được khai báo phù hợp.

**@ConfigurationPropertiesScan và @EnableConfigurationProperties không có hai cơ chế relaxed binding khác nhau.** Chúng chỉ chọn cách đăng ký type để Binder xử lý.

## 10. Package layout và phạm vi tìm kiếm

Một nguyên nhân thiếu bean phổ biến là đặt @ConfigurationPropertiesScan trên class nằm sai package.

Ví dụ:

~~~text
com.example.application
  └── DemoApplication.java

com.example.shared.config
  └── MailProperties.java
~~~

Nếu DemoApplication nằm ở com.example.application và chỉ khai báo:

~~~java
@ConfigurationPropertiesScan
~~~

scan mặc định không bao phủ com.example.shared.config. MailProperties sẽ không được tìm thấy bằng cơ chế này.

Có thể sửa bằng:

~~~java
@ConfigurationPropertiesScan(
        basePackageClasses = MailProperties.class)
~~~

hoặc đăng ký trực tiếp:

~~~java
@EnableConfigurationProperties(MailProperties.class)
~~~

### 10.1. Trong dự án nhiều module

Giả sử:

~~~text
modules/
├── app/
│   └── com.example.app.DemoApplication
└── shared-config/
    └── com.example.shared.config.MailProperties
~~~

Việc module app phụ thuộc shared-config làm class có mặt trên classpath nhưng **không tự mở rộng scan root** của @ConfigurationPropertiesScan.

Nếu muốn tự quét shared-config, hãy chỉ định package hoặc marker class. Nếu chỉ cần đúng MailProperties, @EnableConfigurationProperties(MailProperties.class) có thể rõ ràng hơn.

### 10.2. Quét quá rộng có thể gây tác dụng ngoài ý muốn

Một scan root rất rộng như com.example có thể bao gồm:

- Configuration properties của nhiều feature đang phát triển.
- Properties classes được thư viện khác sử dụng có điều kiện.
- Những class mà ứng dụng chưa muốn đăng ký.

Nếu các class đó có validation bắt buộc, chúng có thể gây lỗi startup ngay cả khi feature liên quan chưa được bật.

Khi các tính năng có vòng đời hoặc điều kiện kích hoạt riêng, registration tường minh trong @Configuration/@AutoConfiguration là một cách giảm coupling.

## 11. Dùng @EnableConfigurationProperties trong auto-configuration

Đây là một trong những trường hợp @EnableConfigurationProperties đặc biệt hữu ích. Giả sử bạn phát triển thư viện greeting có các property:

~~~java
package com.example.greeting;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "greeting")
public class GreetingProperties {

    private String prefix = "Xin chào";

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
~~~

Auto-configuration:

~~~java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingProperties;
import com.example.greeting.GreetingService;
import com.example.greeting.DefaultGreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(GreetingProperties.class)
@ConditionalOnProperty(
        prefix = "greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService(GreetingProperties properties) {
        return new DefaultGreetingService(properties.getPrefix());
    }
}
~~~

Trong ví dụ:

1. Auto-configuration được Spring Boot xử lý nếu được đăng ký qua cơ chế imports của thư viện.
2. @EnableConfigurationProperties đăng ký đúng kiểu GreetingProperties mà cấu hình này cần.
3. Property greeting.enabled điều khiển việc áp dụng cấu hình theo điều kiện.
4. @ConditionalOnMissingBean cho phép ứng dụng thay thế GreetingService mặc định.

### 11.1. Vì sao auto-configuration nên hạn chế scan package?

Thư viện có thể được thêm vào rất nhiều ứng dụng khác nhau. Nếu auto-configuration của nó quét quá rộng, nó có thể đăng ký các properties type không liên quan hoặc kích hoạt validation khi tính năng chưa được bật.

Registration tường minh bằng @EnableConfigurationProperties giúp auto-configuration làm rõ **những properties types thuộc trách nhiệm của nó**.

### 11.2. Phân biệt đăng ký properties với tạo service

@EnableConfigurationProperties đăng ký GreetingProperties, nhưng **không tự tạo GreetingService**. Service vẫn được đăng ký bằng @Bean, @Component hoặc auto-configuration thích hợp.

~~~text
@EnableConfigurationProperties(GreetingProperties.class)
                         │
                         ▼
                 GreetingProperties bean
                         │
                         ▼
@Bean GreetingService greetingService(GreetingProperties)
                         │
                         ▼
                  GreetingService bean
~~~

Đây là sự tách trách nhiệm giữa **configuration data** và **application component**.

## 12. @Bean kết hợp @ConfigurationProperties: cách đăng ký thứ ba

Đôi khi bạn cần bind configuration trực tiếp vào object của thư viện bên thứ ba, không thể sửa class để thêm @ConfigurationProperties.

Khi đó có thể đặt @ConfigurationProperties lên phương thức @Bean:

~~~java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "app.client")
    VendorClientOptions vendorClientOptions() {
        return new VendorClientOptions();
    }
}
~~~

Spring tạo bean qua factory method rồi bind các property tương thích vào object đó. Mẫu này phù hợp với object bên thứ ba có setters hoặc cơ chế binding thích hợp.

Đây là **phương pháp khác với đăng ký một @ConfigurationProperties class bằng scan/enable**:

- @ConfigurationPropertiesScan tìm các class mang annotation.
- @EnableConfigurationProperties đăng ký một danh sách classes.
- @Bean + @ConfigurationProperties khai báo một bean cụ thể và yêu cầu bind dữ liệu vào bean đó.

Nếu muốn constructor binding cho một record bất biến, hãy dùng cơ chế scan/enable tương ứng thay vì giả định @Bean factory method luôn hỗ trợ cách bind constructor giống như Boot tạo properties bean.

## 13. Tên bean khi đăng ký bằng scan hoặc enable

Khi Spring Boot đăng ký một configuration properties class thông qua @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties, nó thường dùng tên bean theo quy ước:

~~~text
<prefix>-<fully-qualified-class-name>
~~~

Ví dụ:

~~~text
app.mail-com.example.demo.config.MailProperties
~~~

Đây là tên bean quy ước được Boot dùng cho dạng registration này. Nếu không có prefix, quy ước tên có thể chỉ gồm tên class đầy đủ.

Trong code nghiệp vụ, cách inject nên ưu tiên **theo kiểu**:

~~~java
public MailService(MailProperties properties) {
    this.properties = properties;
}
~~~

Không nên hard-code bean name có tên package vào phần lớn consumer, vì việc đổi package hoặc thay cơ chế registration có thể ảnh hưởng tên.

### 13.1. Có thể có nhiều bean cùng kiểu không?

Thông thường, một properties type được đăng ký một lần là đủ. Nếu bạn chủ động tạo nhiều bean cùng kiểu bằng @Bean hoặc nhiều cơ chế khác nhau, consumer inject theo kiểu có thể gặp ambiguity.

Lúc đó cần:

- Xác định có thực sự cần nhiều instance không.
- Đặt bean names và @Qualifier rõ ràng.
- Tránh đăng ký trùng do @Component, @Bean và scan/enable chồng chéo.
- Nếu cần nhiều cấu hình cùng cấu trúc nhưng khác prefix, cân nhắc tạo các type riêng hoặc @Bean methods với tên/qualifier riêng.

### 13.2. Không dùng @Primary để che lỗi đăng ký chồng chéo

@Primary giúp chọn một bean cho dependency đơn, nhưng không sửa nguyên nhân vì sao có nhiều properties beans cùng vai trò.

Nếu vô tình đăng ký một MailProperties qua @Component và thêm một MailProperties qua @EnableConfigurationProperties, hãy chọn một phương thức đăng ký đúng thay vì dùng @Primary để “giải quyết cho xong”.

## 14. Kiểm thử cách đăng ký bằng ApplicationContextRunner

Khi học configuration properties, nên tách việc kiểm thử registration/binding khỏi toàn bộ ứng dụng web. Spring Boot cung cấp **ApplicationContextRunner** để dựng một ApplicationContext nhỏ với những configuration classes và property values do test lựa chọn.

Các ví dụ sử dụng JUnit 5, AssertJ và spring-boot-test. Trong Gradle thường có:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

### 14.1. Kiểm thử @EnableConfigurationProperties

Giả sử MailProperties đã được khai báo ở mục 2. Ta tạo test configuration chỉ đăng ký một type:

~~~java
package com.example.demo.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(MailProperties.class)
class ExplicitMailPropertiesConfiguration {
}
~~~

Test:

~~~java
package com.example.demo.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class ExplicitPropertiesRegistrationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            ExplicitMailPropertiesConfiguration.class);

    @Test
    void registersAndBindsPropertiesExplicitly() {
        runner.withPropertyValues(
                        "app.mail.host=smtp.testing.internal",
                        "app.mail.port=587",
                        "app.mail.connect-timeout=7s")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(MailProperties.class);

                    MailProperties props =
                            context.getBean(MailProperties.class);

                    assertThat(props.getHost())
                            .isEqualTo("smtp.testing.internal");
                    assertThat(props.getPort()).isEqualTo(587);
                    assertThat(props.getConnectTimeout())
                            .isEqualTo(Duration.ofSeconds(7));
                });
    }
}
~~~

Test này kiểm tra riêng hai điều quan trọng:

1. Explicit registration tạo một MailProperties bean.
2. Bean nhận giá trị property và chuyển đổi được kiểu Duration.

Nó không cần mở HTTP port hay khởi động toàn bộ chức năng nghiệp vụ.

### 14.2. Kiểm thử @ConfigurationPropertiesScan

Với phương án scan, cấu hình test là:

~~~java
package com.example.demo.config;

import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConfigurationPropertiesScan(
        basePackageClasses = MailProperties.class)
class ScannedMailPropertiesConfiguration {
}
~~~

Test:

~~~java
@Test
void registersPropertiesFoundByScan() {
    new ApplicationContextRunner()
            .withUserConfiguration(ScannedMailPropertiesConfiguration.class)
            .withPropertyValues(
                    "app.mail.host=smtp.scan.internal",
                    "app.mail.port=2526")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(MailProperties.class);

                MailProperties props =
                        context.getBean(MailProperties.class);
                assertThat(props.getHost())
                        .isEqualTo("smtp.scan.internal");
                assertThat(props.getPort()).isEqualTo(2526);
            });
}
~~~

Ví dụ này chỉ có ý nghĩa khi MailProperties thực sự nằm trong package mà cấu hình test quét, và không được đăng ký bằng một cơ chế khác ngoài phạm vi test.

Trong một codebase lớn, có thể chọn package thử nghiệm riêng để tránh scan thêm nhiều properties class không liên quan. Mục đích test là xác nhận **registration theo package**, không phải tình cờ tìm thấy bean do @Component hoặc một auto-configuration khác.

### 14.3. Xác nhận chỉ khai báo annotation chưa đăng ký bean

Một test không thêm registration:

~~~java
@Test
void annotationAloneDoesNotRegisterProperties() {
    new ApplicationContextRunner()
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(MailProperties.class);
            });
}
~~~

Test này minh họa rằng một type trong source code, dù có @ConfigurationProperties, không tự đi vào một context test trống nếu không được quét, import hoặc đăng ký.

### 14.4. Kiểm thử giá trị mặc định

Với MailProperties có port mặc định 25 và timeout mặc định 3 giây:

~~~java
@Test
void retainsDefaultsForMissingProperties() {
    new ApplicationContextRunner()
            .withUserConfiguration(ExplicitMailPropertiesConfiguration.class)
            .withPropertyValues("app.mail.host=smtp.defaults.internal")
            .run(context -> {
                assertThat(context).hasNotFailed();
                MailProperties props =
                        context.getBean(MailProperties.class);

                assertThat(props.getPort()).isEqualTo(25);
                assertThat(props.getConnectTimeout())
                        .isEqualTo(Duration.ofSeconds(3));
            });
}
~~~

Giá trị mặc định do Java class hoặc record constructor cung cấp. Đây không phải hành vi đặc biệt chỉ thuộc scan hay chỉ thuộc enable.

## 15. Kiểm thử validation và cấu hình sai

Nếu MailProperties mang @Validated và @NotBlank trên host, hãy kiểm tra ứng dụng không chấp nhận cấu hình thiếu host.

~~~java
@Test
void failsWhenRequiredHostIsMissing() {
    new ApplicationContextRunner()
            .withUserConfiguration(ExplicitMailPropertiesConfiguration.class)
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure()).isNotNull();
            });
}
~~~

Test yêu cầu có Bean Validation provider và class properties đã khai báo validation constraints như mục 8. Nếu chưa bật validation, việc thiếu host có thể không gây lỗi ngay tại binding, vì String host mặc định null.

### 15.1. Đọc lỗi binding đúng tầng

Khi port là chuỗi không thể chuyển thành int:

~~~yaml
app:
  mail:
    host: smtp.example.internal
    port: not-a-number
~~~

Bean có thể thất bại khi binding với thông tin liên quan đến property path và conversion. Lỗi ngoài cùng có thể được bọc trong BeanCreationException hoặc exception liên quan đến binding, tùy cách tạo bean và phiên bản Boot.

Khi đọc startup log, hãy phân biệt:

- **Không có MailProperties bean**: registration chưa xảy ra.
- **Có definition nhưng bind thất bại**: property value không hợp lệ hoặc không chuyển được kiểu.
- **Bind thành công nhưng validation thất bại**: cấu trúc có giá trị nhưng vi phạm constraint.
- **Bind thành công nhưng service không tạo được**: bean nghiệp vụ cần dependency khác hoặc lỗi khi khởi tạo.

Không nên sửa một lỗi binding bằng cách thêm @Primary hoặc @Qualifier. Hai annotation đó không giải quyết việc chuyển chuỗi thành Duration hay validate port.

### 15.2. Test với nhiều profile hoặc property source

Trong ứng dụng thực tế, property có thể đến từ application.yml, application-dev.yml, environment variables hoặc command-line arguments.

Nếu muốn kiểm tra một profile:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(ExplicitMailPropertiesConfiguration.class)
        .withPropertyValues(
                "spring.profiles.active=dev",
                "app.mail.host=smtp.dev.internal")
        .run(context -> {
            // Đọc và kiểm tra properties bean.
        });
~~~

Ở ApplicationContextRunner, chỉ đặt spring.profiles.active không tự bảo đảm runner đã tải đầy đủ các file cấu hình giống một SpringApplication thực tế. Hãy cung cấp property values cụ thể hoặc dùng test tích hợp có configuration loading phù hợp khi cần kiểm tra cơ chế nạp file profile.

Mục tiêu của context runner là kiểm thử registration và binding trong một môi trường nhỏ, được kiểm soát.

## 16. Dùng @SpringBootTest khi cần kiểm tra ứng dụng thực tế

ApplicationContextRunner phù hợp để kiểm tra cấu hình cô lập. Nếu muốn xác nhận cả package scanning, main application configuration, auto-configuration và dependency injection trong một ứng dụng, có thể dùng @SpringBootTest.

Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "app.mail.host=smtp.integration.internal",
        "app.mail.port=1025"
})
class MailPropertiesIntegrationTest {

    @Autowired
    MailProperties mailProperties;

    @Test
    void applicationRegistersBoundMailProperties() {
        assertThat(mailProperties.getHost())
                .isEqualTo("smtp.integration.internal");
        assertThat(mailProperties.getPort()).isEqualTo(1025);
    }
}
~~~

Test chỉ thành công nếu ứng dụng thực sự có một cách đăng ký MailProperties. Với cấu trúc ví dụ, đó có thể là @ConfigurationPropertiesScan trên DemoApplication hoặc @EnableConfigurationProperties trong MailConfiguration đã được scan/import.

Vì @SpringBootTest có thể khởi tạo nhiều bean, web context và kết nối ngoài, hãy dùng ApplicationContextRunner cho test đơn giản; chỉ dùng @SpringBootTest khi cần chứng minh wiring toàn hệ thống.

## 17. Cấu hình theo điều kiện và thời điểm đăng ký

Trong một auto-configuration, properties bean có thể chỉ được đăng ký khi điều kiện trên configuration class thỏa.

Ví dụ:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.MailClient")
@ConditionalOnProperty(
        prefix = "feature.mail",
        name = "enabled",
        havingValue = "true")
@EnableConfigurationProperties(MailProperties.class)
public class MailFeatureAutoConfiguration {
    // Bean methods phụ thuộc thư viện vendor.
}
~~~

Nếu class vendor vắng mặt hoặc property feature.mail.enabled không phải true, auto-configuration này bị bỏ qua theo điều kiện của nó. Registration MailProperties gắn với nhánh cấu hình đó cũng không phải một hoạt động scan độc lập do main application class kích hoạt.

Ngược lại, nếu ứng dụng đặt:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
}
~~~

thì MailProperties trong vùng scan có thể được đăng ký ngay cả khi feature sử dụng nó bị tắt bởi một condition ở một auto-configuration khác. Nếu MailProperties có validation bắt buộc, điều đó có thể khiến ứng dụng yêu cầu cấu hình cho một tính năng chưa bật.

Đây là một lý do **@EnableConfigurationProperties đặt trên đúng configuration class có điều kiện** phù hợp với các thư viện hoặc tính năng tùy chọn.

### 17.1. Registration không tự bảo đảm điều kiện nghiệp vụ

Ngay cả khi MailProperties được đăng ký, một MailClient không tự được tạo nếu không có @Bean, @Component hoặc auto-configuration tương ứng.

Tách rõ:

~~~text
Điều kiện tính năng hợp lệ
           │
           ▼
Đăng ký MailProperties (config holder)
           │
           ▼
Bind + validate configuration data
           │
           ▼
Đăng ký MailClient (nếu bean condition phù hợp)
           │
           ▼
MailService sử dụng client
~~~

Các giai đoạn có thể thất bại vì những nguyên nhân khác nhau; không nên gọi tất cả là “scan không hoạt động”.

## 18. Các lỗi thường gặp và cách xử lý

### 18.1. Chỉ thêm @ConfigurationProperties nhưng inject không được

**Dấu hiệu:** NoSuchBeanDefinitionException hoặc UnsatisfiedDependencyException cho MailProperties.

**Nguyên nhân:** type chưa được đăng ký thành bean; annotation chỉ mô tả cách binding.

**Cách sửa:** dùng @ConfigurationPropertiesScan cho package chứa type hoặc @EnableConfigurationProperties(MailProperties.class) trong một configuration class được Spring xử lý.

### 18.2. Scan đặt ở package không bao phủ properties class

**Dấu hiệu:** class có annotation đúng nhưng không thấy MailProperties bean khi khởi động.

**Nguyên nhân:** @ConfigurationPropertiesScan không có basePackages sẽ quét từ package của class mang annotation, không phải toàn classpath.

**Cách sửa:** chuyển scan root tới package phù hợp, cấu hình basePackageClasses hoặc đăng ký explicit bằng @EnableConfigurationProperties.

### 18.3. @EnableConfigurationProperties nằm trong class chưa được load

**Dấu hiệu:** code khai báo @EnableConfigurationProperties(MailProperties.class) nhưng context không có MailProperties.

**Nguyên nhân:** class chứa annotation không được component scan, không được import và cũng không nằm trong auto-configuration được Boot xử lý.

**Cách sửa:** xác nhận class cấu hình thực sự được Spring đăng ký. Bản thân @EnableConfigurationProperties không tự làm class chứa nó được phát hiện.

### 18.4. Gắn @Component vào record properties

**Dấu hiệu:** Spring báo không tìm được bean String, int hoặc kiểu tham số constructor.

**Nguyên nhân:** regular component creation cố inject các tham số constructor như dependency, thay vì constructor binding từ Environment.

**Cách sửa:** bỏ @Component và dùng @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties cho record.

### 18.5. Đăng ký cùng type qua nhiều cơ chế

**Dấu hiệu:** context có nhiều MailProperties beans, injection bị mơ hồ hoặc có cấu hình bị bind hai lần theo những đường khác nhau.

**Nguyên nhân:** phối hợp @Component, @Bean, scan, enable mà không thống nhất ownership.

**Cách sửa:** xác định một nơi đăng ký cho mỗi properties type; nếu có chủ đích tạo nhiều bean, dùng bean names và qualifiers rõ ràng.

### 18.6. Sai prefix hoặc sai property name

**Dấu hiệu:** bean tồn tại nhưng fields giữ giá trị mặc định hoặc null.

**Nguyên nhân:** class dùng prefix app.mail nhưng YAML lại đặt mail.app hoặc một tên key khác không thuộc cùng prefix.

**Cách sửa:** so sánh prefix trong annotation với cấu trúc property thực tế và quy tắc relaxed binding.

### 18.7. Property có giá trị nhưng không bind được

**Dấu hiệu:** BeanCreationException với cause liên quan đến conversion, ví dụ cannot convert String thành Duration hoặc int.

**Nguyên nhân:** sai kiểu dữ liệu, sai định dạng hoặc thiếu converter phù hợp.

**Cách sửa:** dùng giá trị có đơn vị rõ như 5s, 200ms; kiểm tra type và conversion; bổ sung converter khi có kiểu custom.

### 18.8. Validation không chạy

**Dấu hiệu:** host rỗng vẫn được chấp nhận.

**Nguyên nhân:** class thiếu @Validated, constraint chưa được khai báo, không có validation provider phù hợp hoặc nested validation chưa được thiết lập.

**Cách sửa:** kiểm tra jakarta.validation constraints, @Validated và dependency Bean Validation.

### 18.9. Scan thêm properties của một tính năng bị tắt

**Dấu hiệu:** ứng dụng báo thiếu property hoặc validation lỗi cho một module không sử dụng.

**Nguyên nhân:** @ConfigurationPropertiesScan quét toàn package và đăng ký một properties type không gắn với điều kiện bật/tắt feature.

**Cách sửa:** thu hẹp scan root hoặc chuyển registration của type đó sang @EnableConfigurationProperties trên configuration class có condition thích hợp.

### 18.10. Nhầm với @ConfigurationProperty hoặc @PropertySource

**Dấu hiệu:** thêm một annotation đọc file rồi kỳ vọng properties bean tự được tạo.

**Nguyên nhân:** trộn việc nạp nguồn property với đăng ký và binding object.

**Cách sửa:** xác định rõ bước nào đang thiếu: property source có được nạp không, properties type có được đăng ký không và dữ liệu có bind đúng không.

### 18.11. Thay đổi giá trị cấu hình ở runtime nhưng bean không tự cập nhật

**Dấu hiệu:** cập nhật một file YAML sau khi process chạy nhưng MailProperties vẫn giữ giá trị cũ.

**Nguyên nhân:** configuration properties thường được bind theo lifecycle tạo bean/context. Chỉnh file không tự phát sinh cơ chế refresh động.

**Cách sửa:** áp dụng phương án restart/redeploy hoặc một cơ chế dynamic refresh được thiết kế riêng nếu hệ thống thực sự cần cập nhật runtime. Không coi @ConfigurationPropertiesScan là tính năng theo dõi file.

### 18.12. Hiểu nhầm explicit registration là tạo nhiều instance

**Dấu hiệu:** đặt @EnableConfigurationProperties ở hai nơi rồi cho rằng mỗi nơi chắc chắn tạo một instance riêng.

**Nguyên nhân:** annotation dùng để đăng ký configuration properties type theo cơ chế Boot, không phải constructor/factory method tùy ý mỗi lần xuất hiện.

**Cách sửa:** xem bean definitions thực tế và thống nhất owner đăng ký. Nếu cần hai object cùng kiểu với hai prefix khác nhau, thiết kế hai registration tường minh phù hợp thay vì trông đợi hai @Enable tạo hai bản sao khác cấu hình.

## 19. Hướng dẫn chọn trong các tình huống thực tế

### Tình huống A: Ứng dụng web có nhiều class properties nội bộ

Có UserProperties, EmailProperties, ReportProperties ở com.example.app.config. Main application class ở com.example.app.

**Lựa chọn phù hợp:** đặt @ConfigurationPropertiesScan trên main class. Spring tự tìm các properties classes trong phạm vi quét.

### Tình huống B: Một @Configuration chỉ cần đúng một type

MailConfiguration chỉ cần MailProperties; main application class nằm ở package khác.

**Lựa chọn phù hợp:** @EnableConfigurationProperties(MailProperties.class) trên MailConfiguration. Không cần mở rộng scan root của toàn ứng dụng.

### Tình huống C: Viết một Spring Boot starter

GreetingAutoConfiguration cần GreetingProperties và có @ConditionalOnClass hoặc @ConditionalOnProperty.

**Lựa chọn phù hợp:** @EnableConfigurationProperties(GreetingProperties.class) trên auto-configuration để registration gắn với chính tính năng đó.

### Tình huống D: Nhiều class properties ở shared module

Shared module nằm ở package khác, có nhiều properties classes mà ứng dụng muốn dùng.

**Lựa chọn phù hợp:** @ConfigurationPropertiesScan(basePackageClasses = SharedConfigMarker.class), nếu chủ đích bật cả nhóm. Nếu chỉ dùng một hoặc hai type, @EnableConfigurationProperties tường minh giúp kiểm soát hơn.

### Tình huống E: Properties immutable dùng record

Class properties là record có canonical constructor, không có setters.

**Lựa chọn phù hợp:** scan/enable để Spring Boot constructor-bind. Tránh thêm @Component chỉ để bean được phát hiện.

### Tình huống F: Cần bind vào một class bên thứ ba

Class từ vendor không có @ConfigurationProperties và không thể sửa source.

**Lựa chọn phù hợp:** một @Bean method mang @ConfigurationProperties để bind theo cơ chế thích hợp của object đó, thường là JavaBean setters.

## 20. Những hiểu nhầm thường gặp

**“@ConfigurationProperties là đủ để class được inject.”**  
Không. Cần registration qua scan, enable, @Bean hoặc cơ chế component phù hợp.

**“@SpringBootApplication luôn tự scan tất cả @ConfigurationProperties classes.”**  
Không. Component scanning không đồng nghĩa configuration properties scanning.

**“@ConfigurationPropertiesScan quét toàn classpath.”**  
Không. Nó quét từ package mặc định của class mang annotation hoặc từ các package được chỉ định.

**“@EnableConfigurationProperties không phụ thuộc class cấu hình có được xử lý hay không.”**  
Không. Annotation chỉ có hiệu lực khi class chứa nó được Spring đưa vào quá trình cấu hình.

**“@EnableConfigurationProperties không có arguments sẽ tự tìm mọi properties class.”**  
Không. Nếu muốn explicit registration, phải liệt kê các types; nếu muốn package scan, dùng @ConfigurationPropertiesScan.

**“Dùng @Component và @ConfigurationPropertiesScan cho cùng class sẽ chắc chắn hoạt động theo scan.”**  
Không. Các class được đánh dấu @Component không thuộc đối tượng mà @ConfigurationPropertiesScan chọn; nếu bean xuất hiện, nó có thể đến từ component scanning.

**“Record properties nên thêm @Component để khởi tạo được.”**  
Không. Constructor binding của configuration properties và constructor injection của component là hai cơ chế khác nhau.

**“@ConfigurationPropertiesScan có Binder và validation riêng mạnh hơn @EnableConfigurationProperties.”**  
Không. Cả hai đăng ký properties types để dùng cùng hạ tầng binding/validation của Boot.

**“Dùng basePackageClasses là chỉ đăng ký duy nhất class được truyền vào.”**  
Không. Thuộc tính đó xác định các package cần scan. Nếu cần một type duy nhất, dùng @EnableConfigurationProperties(Type.class).

**“Có MailProperties bean nghĩa mọi property đều hợp lệ.”**  
Không. Cần xác định giá trị mặc định, conversion, constraints và validation policy rõ ràng.

**“@ConfigurationPropertiesScan giúp ứng dụng đọc lại YAML mỗi khi file thay đổi.”**  
Không. Đó là cơ chế registration; dynamic configuration refresh là chủ đề riêng.

**“Nếu đã có @ConfigurationPropertiesScan, auto-configuration không bao giờ cần @EnableConfigurationProperties.”**  
Không. Một thư viện không nên giả định consumer đang quét package nội bộ của thư viện. Auto-configuration nên tự đăng ký các properties types nó cần khi điều kiện phù hợp.

## 21. Sơ đồ tổng kết: quyết định đăng ký thế nào?

~~~text
Bạn có một class @ConfigurationProperties
                   │
                   ▼
Class này thuộc nhóm properties nội bộ
của ứng dụng và muốn tự phát hiện theo package?
             │                  │
            Có                Không
             │                  │
             ▼                  ▼
@ConfigurationPropertiesScan    Class được dùng bởi một
chọn package phù hợp            configuration/auto-configuration
                                       │
                                       ▼
                          @EnableConfigurationProperties
                          liệt kê type cụ thể
                                       │
                                       ▼
                          Spring Boot đăng ký properties bean
                                       │
                                       ▼
                          Bind / convert / validate
                                       │
                                       ▼
                          Inject vào service hoặc @Bean method
~~~

Nếu object thuộc thư viện bên thứ ba và không có annotation trên class, cân nhắc factory method @Bean với @ConfigurationProperties thay vì cố sửa class vendor.

## Ghi nhớ cốt lõi

**@ConfigurationProperties** mô tả cách bind dữ liệu vào một kiểu Java; nó không tự bảo đảm kiểu đó đã được Spring đăng ký thành bean. **@ConfigurationPropertiesScan** tìm những kiểu properties theo phạm vi package, thích hợp cho nhiều nhóm cấu hình nội bộ của một ứng dụng. **@EnableConfigurationProperties** đăng ký tường minh những kiểu được liệt kê, phù hợp với configuration class, tính năng riêng và auto-configuration có điều kiện.

Cả hai cơ chế dùng cùng hạ tầng binding, chuyển đổi kiểu và validation. Với Java record hoặc immutable properties, scan/enable là lựa chọn phù hợp để Spring Boot constructor-bind, thay vì gắn @Component và trông chờ regular dependency injection. Khi properties bean không xuất hiện, hãy kiểm tra registration và phạm vi package trước; khi bean tồn tại nhưng giá trị sai, kiểm tra prefix, property sources, conversion và validation. Chọn đúng cơ chế đăng ký sẽ giúp cấu hình Spring Boot dễ hiểu, an toàn khi mở rộng và dễ kiểm thử hơn.
