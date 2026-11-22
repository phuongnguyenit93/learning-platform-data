# Tách lựa chọn tính năng bằng @ConditionalOnProperty khỏi dữ liệu cấu hình

Spring Boot có hai nhu cầu cấu hình dễ bị trộn lẫn: **chọn một tính năng có được kích hoạt không**, và **cấp tham số để tính năng đó hoạt động**. Khi ứng dụng nhỏ, đôi khi cả hai được đặt trong một record `@ConfigurationProperties` với field `enabled`. Nhưng khi module có HTTP client, scheduler, listener hoặc database adapter, việc tạo bean không đúng thời điểm có thể gây tác dụng phụ dù logic nghiệp vụ sau đó kiểm tra `enabled=false`.

Trong Spring Boot 3.3.x, có thể tách hai nhiệm vụ rõ ràng:

- `@ConditionalOnProperty`: quyết định **đăng ký configuration/bean** dựa trên giá trị hiện có trong `Environment` ở thời điểm Spring xây dựng application context.
- `@ConfigurationProperties`: bind **dữ liệu có kiểu** như `URI`, `Duration`, `int` và hỗ trợ validation/default.

Ví dụ quy ước:

~~~yaml
features:
  delivery:
    enabled: false

app:
  delivery:
    endpoint: https://notify.example.org
    connect-timeout: 3s
    max-attempts: 3
~~~

`features.delivery.enabled` chỉ chọn chế độ hoạt động; các thuộc tính `app.delivery.*` chỉ mô tả dữ liệu của adapter. Bài học dùng Java 21, Spring Boot 3.3.x, Spring Test và JUnit Jupiter, kèm mã ứng dụng, các trường hợp bật/tắt, thứ tự ưu tiên cấu hình, kiểm thử và hướng dẫn refactor.

## 1. Vấn đề với một class chứa cả enabled và dữ liệu

Cách viết thường thấy:

~~~java
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        boolean enabled,
        URI endpoint,
        Duration connectTimeout,
        int maxAttempts) {
}
~~~

Service sẽ làm:

~~~java
if (properties.enabled()) {
    sendToRemoteService(properties.endpoint());
}
~~~

Có một số giới hạn:

1. Bean service hoặc client vẫn có thể được tạo trước khi `if` chạy.
2. Constructor có thể mở kết nối hoặc đăng ký background job dù tính năng tắt.
3. Record yêu cầu `endpoint` có thể bị validate trong startup ngay cả khi feature không dùng.
4. Nhiều service cần tự lặp lại điều kiện.
5. Khó thay thế một implementation bằng No-op hoặc adapter khác.
6. Test nhánh disabled phải can thiệp vào logic thay vì kiểm tra bean graph.
7. Việc có endpoint/credential dễ bị nhầm là điều kiện cho phép tính năng hoạt động.

Một hướng rõ ràng hơn:

~~~text
features.delivery.enabled
            |
            v
   @ConditionalOnProperty
            |
       +----+----+
       |         |
      true      false / missing
       |         |
       v         v
Configured    Noop
Delivery      Delivery
Sender        Sender
       |         |
       +----+----+
            |
            v
    DeliveryService

app.delivery.*
     |
     v
@ConfigurationProperties
     |
     v
Dữ liệu cho ConfiguredDeliverySender
(chỉ bind khi nhánh enabled được đăng ký)
~~~

Ý nghĩa của mô hình này không phải “mọi boolean đều phải dùng annotation”, mà là **quyết định cấu trúc bean** khác với **dữ liệu tham số**.

## 2. @ConditionalOnProperty hoạt động như thế nào?

Import:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
~~~

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "features.delivery",
        name = "enabled",
        havingValue = "true")
public class DeliveryEnabledConfiguration {
    // Bean definitions chỉ được xét khi flag phù hợp.
}
~~~

Địa chỉ property là `features.delivery.enabled`, ghép từ `prefix` và `name`. Khi Spring Boot xử lý configuration class, `OnPropertyCondition` đối chiếu giá trị trong `Environment`.

Các thuộc tính của annotation:

| Thuộc tính | Chức năng |
| --- | --- |
| `prefix` | Namespace, ví dụ `features.delivery` |
| `name` | Tên property hoặc mảng tên, ví dụ `enabled` |
| `value` | Alias của `name` |
| `havingValue` | Giá trị chuỗi mong đợi |
| `matchIfMissing` | Có match khi property không tồn tại không |

`@ConditionalOnProperty` có thể đặt trên một class `@Configuration` hoặc một method `@Bean`. Nó **không phải annotation validation cho boolean**, cũng không làm biến Environment thay đổi giá trị.

### Quy tắc matching mặc định

Không ghi `havingValue` thì property phải **tồn tại và không bằng `false`**:

| Giá trị property | `havingValue=""` | `havingValue="true"` | `havingValue="false"` |
| --- | --- | --- | --- |
| `true` | Khớp | Khớp | Không |
| `false` | Không | Không | Khớp |
| `hello` | Khớp | Không | Không |
| Chuỗi rỗng | Có thể khớp | Không | Không |
| Không tồn tại | Không, theo mặc định | Không | Không |

Đây là lý do **khuyến nghị ghi `havingValue="true"`** nếu ý nghĩa thực sự là một flag boolean. Việc chỉ đặt `name="enabled"` có thể khiến giá trị `hello` kích hoạt tính năng.

### matchIfMissing

Mặc định `matchIfMissing=false`. Nếu muốn **không khai báo flag đồng nghĩa tắt**, có thể tạo nhánh No-op với:

~~~java
@ConditionalOnProperty(
        prefix = "features.delivery",
        name = "enabled",
        havingValue = "false",
        matchIfMissing = true)
~~~

Ngược lại, đối với nhánh có hành vi gửi thật, nên yêu cầu flag có mặt với giá trị `true`, tránh vô tình bật.

## 3. Phân biệt feature switch và data property

Hai nhóm trong cùng file YAML nhưng khác trách nhiệm:

~~~yaml
features:
  delivery:
    enabled: true

app:
  delivery:
    endpoint: https://sandbox.example.org
    connect-timeout: 2s
    max-attempts: 2
~~~

| Key | Loại | Ai sử dụng? |
| --- | --- | --- |
| `features.delivery.enabled` | Lựa chọn tính năng | `@ConditionalOnProperty` |
| `app.delivery.endpoint` | Tham số kết nối | `DeliveryClientProperties` |
| `app.delivery.connect-timeout` | Tham số thời gian | `DeliveryClientProperties` |
| `app.delivery.max-attempts` | Tham số retry | `DeliveryClientProperties` |
| `app.delivery.api-key` | Bí mật của adapter nếu có | Client configuration an toàn |

Tại sao không dùng sự có mặt của `app.delivery.endpoint` làm flag?

- Endpoint có thể được cấp sẵn ở mọi môi trường nhưng tính năng vẫn phải tắt.
- Endpoint có thể hợp lệ nhưng hoạt động bị cấm bởi rollout policy.
- Endpoint có thể thiếu vì deploy sai; không nên âm thầm coi đó là “tắt”.
- Credential có thể đã được mount nhưng không có nghĩa cho phép kết nối.
- Một ngày nào đó adapter có thể thay đổi phương thức kết nối trong khi ý nghĩa feature flag vẫn giữ nguyên.

Tách prefix là **quy ước kiến trúc**. Framework không bắt buộc tên `features.*` và `app.*`; dự án có thể dùng tên khác miễn ranh giới được tài liệu hóa.

## 4. Cấu trúc dự án minh họa

~~~text
delivery-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/delivery/
    │   │   ├── DeliveryDemoApplication.java
    │   │   ├── api/DeliverySender.java
    │   │   ├── impl/ConfiguredDeliverySender.java
    │   │   ├── impl/NoopDeliverySender.java
    │   │   ├── config/DeliveryClientProperties.java
    │   │   ├── config/DeliveryEnabledConfiguration.java
    │   │   ├── config/DeliveryDisabledConfiguration.java
    │   │   └── service/DeliveryWorkflow.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/delivery/
            └── DeliveryConfigurationTest.java
~~~

Các dependency Maven cơ bản:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Giả định dự án đã có Spring Boot parent/BOM 3.3.x, Java 21 và cấu hình build thông thường. `spring-boot-starter-validation` cung cấp Jakarta Bean Validation provider cần thiết cho các constraint trên typed properties.

## 5. Tạo interface nghiệp vụ

Tạo `DeliverySender.java`:

~~~java
package com.example.delivery.api;

public interface DeliverySender {
    void send(String message);
    String mode();
}
~~~

Tạo `DeliveryWorkflow.java`:

~~~java
package com.example.delivery.service;

import com.example.delivery.api.DeliverySender;
import org.springframework.stereotype.Service;

@Service
public final class DeliveryWorkflow {

    private final DeliverySender sender;

    public DeliveryWorkflow(DeliverySender sender) {
        this.sender = sender;
    }

    public void process(String message) {
        sender.send(message);
    }

    public String senderMode() {
        return sender.mode();
    }
}
~~~

Service này không cần inject `Environment` hoặc `DeliveryClientProperties` chỉ để kiểm tra flag. Nó phụ thuộc vào **hợp đồng nghiệp vụ `DeliverySender`**. Việc chọn implementation là trách nhiệm của configuration layer.

Lợi ích:

- Unit test `DeliveryWorkflow` bằng fake sender đơn giản.
- Có thể thay implementation mà không sửa service.
- Không phải thêm `if (enabled)` trước mọi lời gọi.
- Dễ chứng minh trong integration test rằng bean đã được chọn đúng.

## 6. Typed configuration chỉ chứa dữ liệu

Tạo `DeliveryClientProperties.java`:

~~~java
package com.example.delivery.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryClientProperties(
        @NotNull URI endpoint,
        @DefaultValue("3s") Duration connectTimeout,
        @Min(1) @DefaultValue("3") int maxAttempts) {
}
~~~

Tại đây:

- `endpoint` bắt buộc nếu class được bind và Bean Validation hoạt động.
- `connectTimeout` dùng `Duration`, mặc định ba giây.
- `maxAttempts` là số nguyên, có default ba và constraint tối thiểu một.
- Không có `enabled` vì record mô tả **dữ liệu**, không phải quyết định tạo bean.

Spring Boot Binder chuyển chuỗi như `3s` thành `Duration`. Validation chỉ kiểm tra giá trị sau khi binding. `URI` hợp lệ cú pháp không bảo đảm HTTPS, DNS hoặc endpoint thật sự truy cập được; nếu nghiệp vụ yêu cầu HTTPS, cần rule riêng.

### Dữ liệu có thể được cấp dù tính năng tắt

Bạn vẫn có thể giữ `app.delivery.endpoint` trong file cấu hình mặc định để phục vụ môi trường sẽ bật sau đó. Nhưng **sự có mặt của property không quyết định bean được tạo**. Việc chọn bean vẫn do `features.delivery.enabled`.

### Không đăng ký record vô điều kiện

Điểm quan trọng của ví dụ là record này được đăng ký trong một `@Configuration` có condition true ở phần sau. Nếu đặt `@ConfigurationPropertiesScan` ở application root và scan cả record, có thể Spring Boot vẫn tạo/bind bean này khi feature tắt.

Nếu mục tiêu là chỉ validate dữ liệu khi feature enabled, phải bảo đảm typed config không được đăng ký từ một đường vô điều kiện khác.

## 7. Adapter được dùng khi bật

Tạo `ConfiguredDeliverySender.java`:

~~~java
package com.example.delivery.impl;

import com.example.delivery.api.DeliverySender;
import com.example.delivery.config.DeliveryClientProperties;

public final class ConfiguredDeliverySender
        implements DeliverySender {

    private final DeliveryClientProperties properties;

    public ConfiguredDeliverySender(
            DeliveryClientProperties properties) {
        this.properties = properties;
    }

    @Override
    public void send(String message) {
        // Bản demo không gửi HTTP thật.
        // Không ghi nội dung message hoặc credential vào log.
        System.out.println(
                "Demo sender configured for "
                        + properties.endpoint());
    }

    @Override
    public String mode() {
        return "configured";
    }
}
~~~

Class này **không gắn `@Component`**. Nó chỉ được tạo từ một `@Bean` có điều kiện. Điều đó tránh bean được component scan tạo vô điều kiện.

Trong production, implementation có thể sử dụng `WebClient`, `RestClient` hoặc messaging SDK. HTTP client phải dùng timeout và retry phù hợp; không giả định ví dụ in thông báo đã thực hiện network request.

## 8. Adapter khi tắt

Tạo `NoopDeliverySender.java`:

~~~java
package com.example.delivery.impl;

import com.example.delivery.api.DeliverySender;

public final class NoopDeliverySender
        implements DeliverySender {

    @Override
    public void send(String message) {
        // Chủ ý không gửi khi tính năng đã tắt.
    }

    @Override
    public String mode() {
        return "disabled";
    }
}
~~~

No-op phù hợp khi “không gửi” là một hành vi nghiệp vụ chấp nhận được. Nó giúp `DeliveryWorkflow` vẫn được tạo và gọi qua interface không đổi.

**Không sử dụng No-op để che một tác vụ bắt buộc** như audit tuân thủ, mã hóa, kiểm tra quyền hay ghi giao dịch. Khi thao tác là bắt buộc, nên thiếu bean và fail fast thay vì âm thầm bỏ qua.

## 9. Configuration dành cho nhánh enabled

Tạo `DeliveryEnabledConfiguration.java`:

~~~java
package com.example.delivery.config;

import com.example.delivery.api.DeliverySender;
import com.example.delivery.impl.ConfiguredDeliverySender;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "features.delivery",
        name = "enabled",
        havingValue = "true")
@EnableConfigurationProperties(DeliveryClientProperties.class)
public class DeliveryEnabledConfiguration {

    @Bean
    DeliverySender configuredDeliverySender(
            DeliveryClientProperties properties) {
        return new ConfiguredDeliverySender(properties);
    }
}
~~~

Đây là ranh giới chính:

1. Condition kiểm tra `features.delivery.enabled`.
2. Nếu giá trị là `true`, configuration được xử lý.
3. `@EnableConfigurationProperties` đăng ký `DeliveryClientProperties`.
4. Spring Boot bind/validate `app.delivery.*`.
5. `ConfiguredDeliverySender` nhận object cấu hình đã có kiểu.

Nếu flag không khớp, configuration này không tạo sender thật. Vì `@EnableConfigurationProperties` nằm trong cấu hình có điều kiện, record không phải bean bắt buộc của nhánh disabled, miễn không có registration khác.

### Vì sao condition đặt ở class?

Nếu cả một nhóm bean như HTTP client, adapter, listener và configuration properties cùng thuộc feature enabled, đặt condition ở **class** giúp loại cả nhóm, giảm nguy cơ vô tình tạo một bean không mong muốn.

Nếu chỉ một method cần điều kiện còn các bean khác luôn cần, method-level condition có thể phù hợp hơn. Nhưng phải xét lại typed properties được đăng ký ở đâu.

## 10. Configuration dành cho nhánh disabled

Tạo `DeliveryDisabledConfiguration.java`:

~~~java
package com.example.delivery.config;

import com.example.delivery.api.DeliverySender;
import com.example.delivery.impl.NoopDeliverySender;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "features.delivery",
        name = "enabled",
        havingValue = "false",
        matchIfMissing = true)
public class DeliveryDisabledConfiguration {

    @Bean
    DeliverySender noopDeliverySender() {
        return new NoopDeliverySender();
    }
}
~~~

Với flag `false` hoặc thiếu, chỉ nhánh disabled match. Với flag true, nhánh disabled không match. Điều kiện có `havingValue="false"` và `matchIfMissing=true` biểu thị **mặc định tắt**.

### Kết quả cho các giá trị

| `features.delivery.enabled` | Bean được tạo theo ví dụ |
| --- | --- |
| Không khai báo | NoopDeliverySender |
| `false` | NoopDeliverySender |
| `true` | ConfiguredDeliverySender |
| `invalid` | Không nhánh nào match |
| Chuỗi rỗng | Không nhánh nào match |

Giá trị `invalid` không tự bị từ chối bởi annotation. Nếu `DeliveryWorkflow` là bean bắt buộc và cần `DeliverySender`, Spring có thể fail vì thiếu bean. Nếu không có consumer bắt buộc, context có thể vẫn khởi động với không sender. Nếu muốn mọi flag phải là boolean hợp lệ, cần cơ chế validate flag hoặc test cấu hình riêng.

## 11. Đăng ký cấu hình trong ứng dụng

Tạo `DeliveryDemoApplication.java`:

~~~java
package com.example.delivery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DeliveryDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DeliveryDemoApplication.class, args);
    }
}
~~~

Hai class configuration nằm trong package con `com.example.delivery.config`, nên component scan mặc định có thể nhận chúng.

**Không thêm `@ConfigurationPropertiesScan` ở root cho toàn bộ package trong ví dụ**, bởi như vậy có thể đăng ký `DeliveryClientProperties` khi feature tắt, phá yêu cầu chỉ validate khi enabled.

### Không gắn @Component vào các implementation

Với bean đã tạo bằng `@Bean`, không nên đồng thời đánh dấu `ConfiguredDeliverySender` hoặc `NoopDeliverySender` bằng `@Component` mà không có condition riêng. Nếu không, component scan có thể thêm bean thứ hai, tạo `NoUniqueBeanDefinitionException` hoặc khiến sender thật tồn tại dù flag false.

### Không nhầm với runtime service constructor

Một service nhận `DeliverySender` qua constructor được tạo sau khi Spring xử lý bean definitions. Nếu flag không hợp lệ và không có implementation nào, lỗi missing dependency là một biểu hiện của sai policy/flag, không phải lỗi conversion của `DeliveryClientProperties`.

## 12. application.yml cho mặc định an toàn

Ví dụ `src/main/resources/application.yml`:

~~~yaml
features:
  delivery:
    enabled: false

app:
  delivery:
    connect-timeout: 3s
    max-attempts: 3
~~~

Chưa có endpoint. Khi flag false, nhánh enabled không đăng ký typed properties nên không yêu cầu endpoint trong mô hình này.

Nếu muốn bật trong dev:

~~~yaml
# application-dev.yml
features:
  delivery:
    enabled: true

app:
  delivery:
    endpoint: https://sandbox.example.org
    connect-timeout: 1s
    max-attempts: 2
~~~

Nếu muốn bật trong prod:

~~~yaml
# application-prod.yml
features:
  delivery:
    enabled: true

app:
  delivery:
    endpoint: https://notify.example.org
    connect-timeout: 3s
    max-attempts: 4
~~~

Địa chỉ trên chỉ là ví dụ, không phải endpoint thật.

### Hành vi khi bật mà thiếu data

Nếu `features.delivery.enabled=true` nhưng không có `app.delivery.endpoint`, bean typed properties vẫn được bind và validation `@NotNull` có thể làm startup fail khi Bean Validation được cấu hình đúng. Đây là điều mong muốn cho một feature cần endpoint.

### Hành vi khi tắt mà data sai

Nếu flag false nhưng `app.delivery.max-attempts=abc`, việc bind vào record không phải bước bắt buộc của mô hình này. Tuy nhiên, **file YAML vẫn phải đúng cú pháp**, vì Config Data được parse trước khi Spring xét condition. Condition không che lỗi YAML hỏng.

## 13. Ghi đè từ Environment và CLI

Spring Boot chọn giá trị hiệu lực theo thứ tự ưu tiên PropertySource.

Ví dụ file chung:

~~~yaml
features:
  delivery:
    enabled: false
~~~

Có thể bật từ CLI:

~~~bash
java -jar delivery-demo.jar   --features.delivery.enabled=true   --app.delivery.endpoint=https://sandbox.example.org
~~~

Trong thứ tự cấu hình thông thường, CLI có thể có ưu tiên cao hơn file YAML, vì vậy nhánh enabled được chọn.

Với Linux shell:

~~~bash
export FEATURES_DELIVERY_ENABLED=true
export APP_DELIVERY_ENDPOINT=https://sandbox.example.org
export APP_DELIVERY_CONNECTTIMEOUT=2s
java -jar delivery-demo.jar
~~~

Quy tắc tên biến môi trường:

~~~text
features.delivery.enabled  -> FEATURES_DELIVERY_ENABLED
app.delivery.endpoint      -> APP_DELIVERY_ENDPOINT
app.delivery.connect-timeout -> APP_DELIVERY_CONNECTTIMEOUT
~~~

Dấu chấm thành gạch dưới, dấu gạch ngang bị bỏ khi chuyển sang tên env variable, tên được viết hoa theo quy tắc relaxed binding của Spring Boot.

**Lưu ý:** thay environment variable bên ngoài một process Java đang chạy không làm thay đổi các bean đã đăng ký. Cách dùng `@ConditionalOnProperty` ở đây là **startup-time switch**.

## 14. Tách feature flag khỏi Bean Validation

Có ba tầng cần phân biệt:

- **Condition:** Có đăng ký cấu hình enabled không?
- **Conversion:** `3s` có được chuyển thành `Duration` không?
- **Validation:** `maxAttempts=0` có vi phạm `@Min(1)` không?

Ví dụ:

~~~text
features.delivery.enabled=false
app.delivery.max-attempts=0
~~~

Nhánh disabled không nhất thiết bind `DeliveryClientProperties`, vì vậy validation của record không tự áp dụng.

Ngược lại:

~~~text
features.delivery.enabled=true
app.delivery.max-attempts=0
~~~

lúc đó typed config được đăng ký; sau conversion thành `int`, Bean Validation có thể chặn giá trị 0.

Nếu một công ty yêu cầu kiểm tra **tất cả cấu hình kể cả module tắt** ở bước CI, có thể xây một validator cấu hình độc lập trước deployment. Đó là chính sách khác với việc chỉ validate bean đang được sử dụng lúc startup.

## 15. Tại sao @DefaultValue không thay thế matchIfMissing?

Trên data record:

~~~java
@DefaultValue("3s") Duration connectTimeout
~~~

có nghĩa: nếu property `app.delivery.connect-timeout` thiếu trong lần bind, Binder có thể dùng giá trị mặc định ba giây.

Trên condition:

~~~java
@ConditionalOnProperty(
    name = "features.delivery.enabled",
    havingValue = "false",
    matchIfMissing = true)
~~~

có nghĩa: condition match khi `features.delivery.enabled` thiếu. Nó **không thêm `features.delivery.enabled=false` vào Environment**.

Hai default có nhiệm vụ khác nhau. Với thiết kế này, thiếu flag chọn No-op; còn thiếu timeout khi enabled có thể dùng 3s.

## 16. Đặt condition trên class hay @Bean method?

Class-level:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "features.report",
    name = "enabled",
    havingValue = "true")
class ReportConfiguration {

    @Bean
    ReportExporter reportExporter(ReportProperties properties) {
        return new ReportExporter(properties);
    }
}
~~~

Method-level:

~~~java
@Configuration(proxyBeanMethods = false)
class ReportConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "features.report",
        name = "enabled",
        havingValue = "true")
    ReportExporter reportExporter(ReportProperties properties) {
        return new ReportExporter(properties);
    }
}
~~~

Nếu chỉ method có condition mà class mang `@EnableConfigurationProperties(ReportProperties.class)` vô điều kiện, record có thể vẫn được bind khi feature tắt. Do đó, **điều kiện hóa cả vùng registration** nếu muốn cô lập dữ liệu của module.

### Ví dụ đặt @Bean condition nhưng bind không mong muốn

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ReportProperties.class)
class ReportsConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "features.report",
        name = "enabled",
        havingValue = "true")
    ReportExporter reportExporter(ReportProperties props) {
        return new ReportExporter(props);
    }
}
~~~

`ReportProperties` có thể được tạo/bind dù method `reportExporter` bị loại, vì annotation đăng ký properties nằm ngoài condition.

Đây là lỗi thiết kế dễ bỏ sót khi chuyển dần từ `@ConfigurationProperties` sang `@ConditionalOnProperty`.

## 17. @Profile khác @ConditionalOnProperty

`@Profile` chọn bean theo **tên môi trường/profile**:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("dev")
class LocalTestAdapterConfiguration {
}
~~~

`@ConditionalOnProperty` chọn theo **property cụ thể**:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "features.delivery",
        name = "enabled",
        havingValue = "true")
class DeliveryEnabledConfiguration {
}
~~~

Có thể kết hợp hai điều kiện:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("!prod")
@ConditionalOnProperty(
        prefix = "features.debug",
        name = "enabled",
        havingValue = "true")
class DebugConfiguration {
}
~~~

Class chỉ được sử dụng khi cả profile expression và property condition đều phù hợp.

Không nên tạo mỗi tính năng một profile riêng nếu vấn đề chỉ là lựa chọn bật/tắt độc lập. Profile mô tả **tập cấu hình theo môi trường**, còn flag thể hiện **lựa chọn tính năng**. Chúng có thể phối hợp nhưng không thay thế nhau.

## 18. @ConditionalOnProperty không phải toggle động

Spring đánh giá `@ConditionalOnProperty` trong giai đoạn xử lý bean definitions. Nếu file YAML hoặc ConfigMap thay đổi sau khi ứng dụng đã chạy, bean graph không tự động được xây lại chỉ vì annotation này tồn tại.

Ví dụ:

~~~text
Startup: features.delivery.enabled=false
    -> NoopDeliverySender được đăng ký.

Sau 10 phút: file cấu hình đổi thành true
    -> Không tự tạo ConfiguredDeliverySender.
~~~

Nếu cần bật/tắt theo từng request, tenant, user hoặc campaign, có thể xây một **runtime feature decision service**:

~~~java
public interface FeatureDecisions {
    boolean isDeliveryEnabled(String tenantId);
}
~~~

Service thực hiện kiểm tra tại thời điểm xử lý, với cache/TTL, audit và cơ chế rollback được thiết kế riêng. Hai chiến lược khác nhau:

| Nhu cầu | Lựa chọn |
| --- | --- |
| Bật/tắt qua deploy/restart | `@ConditionalOnProperty` |
| Bật/tắt theo request/tenant | Runtime feature flag provider |
| Thay tham số của bean khi restart | `@ConfigurationProperties` |
| Refresh động khi process chạy | Cơ chế refresh riêng, kiểm tra tính tương thích |

Nếu dự án có hệ thống refresh chuyên dụng, không tự suy luận mọi bean với `@ConditionalOnProperty` đều được đăng ký lại hoàn toàn an toàn. Phải kiểm chứng hành vi của stack đó.

## 19. Điều kiện có thể kết hợp nhiều names nhưng không phải OR

Ví dụ:

~~~java
@ConditionalOnProperty(
        prefix = "features.delivery",
        name = {"enabled", "licensed"},
        havingValue = "true")
~~~

Nếu khai báo nhiều `name` thì **tất cả** phải phù hợp. Đó là quan hệ AND.

~~~properties
features.delivery.enabled=true
features.delivery.licensed=false
~~~

→ Condition không match.

Nếu muốn một trong hai key đúng, cần một chiến lược điều kiện khác hoặc policy kiểm tra riêng, không thể chỉ liệt kê names rồi kỳ vọng OR.

Tương tự, `@ConditionalOnProperty` **không đáng tin cậy để match collection properties**. Một nguồn có `app.regions[0]` nhưng không có key `app.regions` có thể không khiến điều kiện kiểm tra parent key match. Khi cần logic dựa trên danh sách, dùng converter/config object hoặc custom Condition thích hợp.

## 20. Không dùng credential hoặc endpoint như một feature flag

Ví dụ không nên dùng:

~~~java
@ConditionalOnProperty(
        prefix = "app.payment",
        name = "api-key")
~~~

để quyết định có đăng ký payment client hay không.

Lý do:

- Credential có thể được mount sẵn nhưng tính năng vẫn chưa được cho phép.
- Credential hết hạn vẫn là một chuỗi có mặt.
- Một người điền test token có thể vô tình kích hoạt chức năng thật.
- Không có ý định bật/tắt được thể hiện tường minh.
- Điều kiện mặc định chỉ kiểm tra có mặt và khác false.

Tốt hơn:

~~~properties
features.payment.enabled=false
app.payment.api-key=...
app.payment.endpoint=...
~~~

Khi bật, validate dữ liệu phù hợp và khởi tạo adapter thực. Khi tắt, không tạo client hoặc chỉ tạo No-op nếu nghiệp vụ cho phép. Không log token, không lưu secret trong metadata và không dùng flag để thay thế cơ chế phân quyền.

## 21. No-op hay không đăng ký bean nào?

Mẫu delivery sử dụng No-op để một `DeliveryWorkflow` vẫn hoạt động. Nhưng với một số chức năng, cách tốt hơn là **không có bean** khi disabled.

Ví dụ scheduler:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "features.cleanup",
        name = "enabled",
        havingValue = "true")
class CleanupScheduleConfiguration {

    @Bean
    CleanupScheduler cleanupScheduler(CleanupProperties props) {
        return new CleanupScheduler(props);
    }
}
~~~

Nếu flag false, không cần tạo scheduler. Không có nhánh No-op nếu không có consumer yêu cầu một interface ổn định.

Nếu service tùy chọn sử dụng bean, có thể inject `ObjectProvider<CleanupScheduler>`; nếu service bắt buộc yêu cầu scheduler, việc thiếu bean nên là lỗi khởi động. Không tạo No-op chỉ để che một dependency bắt buộc.

## 22. Khi muốn nhiều chế độ hơn true/false

Một boolean không đủ khi có:

~~~text
OFF
SIMULATION
REAL
~~~

Có thể dùng một mode flag:

~~~properties
features.delivery.mode=simulation
~~~

và các cấu hình điều kiện:

~~~java
@ConditionalOnProperty(
        prefix = "features.delivery",
        name = "mode",
        havingValue = "simulation")
~~~

hoặc:

~~~java
@ConditionalOnProperty(
        prefix = "features.delivery",
        name = "mode",
        havingValue = "real")
~~~

Khi đó cần quy định giá trị mặc định và hành vi với mode lạ. Với các lựa chọn phức tạp, một enum typed config hoặc strategy factory có thể dễ bảo trì hơn nhiều boolean có thể xung đột như `enabled`, `simulate`, `real`.

Nếu mode quyết định toàn bộ bean graph, condition phù hợp; nếu mode cần thay đổi trong runtime, cân nhắc strategy runtime.

## 23. @ConditionalOnMissingBean có giống flag không?

Không. `@ConditionalOnMissingBean` kiểm tra có bean phù hợp đã được đăng ký hay chưa, không trực tiếp đọc cờ `features.delivery.enabled`.

Ví dụ:

~~~java
@Bean
@ConditionalOnMissingBean(DeliverySender.class)
DeliverySender fallbackSender() {
    return new NoopDeliverySender();
}
~~~

Điều này phù hợp trong auto-configuration khi cần cho người dùng tự cung cấp bean. Nhưng kết quả có thể phụ thuộc thứ tự bean definitions được xử lý, nên Spring Boot khuyến nghị thận trọng và thường sử dụng loại điều kiện này trong auto-configuration.

Đối với bài toán “flag false tạo No-op, flag true tạo configured”, hai `@ConditionalOnProperty` minh bạch hơn và ít phụ thuộc thứ tự hơn.

Nếu một starter cần vừa cho phép override bean vừa dùng feature switch, có thể kết hợp các condition nhưng nên tách trách nhiệm rõ: **feature enabled?** và **bean đã tồn tại?**.

## 24. Kiểm thử bằng ApplicationContextRunner

`ApplicationContextRunner` giúp tạo context nhỏ với những property khác nhau, rất phù hợp để test condition.

Tạo `DeliveryConfigurationTest.java`:

~~~java
package com.example.delivery;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.delivery.api.DeliverySender;
import com.example.delivery.config.DeliveryEnabledConfiguration;
import com.example.delivery.config.DeliveryDisabledConfiguration;
import com.example.delivery.impl.ConfiguredDeliverySender;
import com.example.delivery.impl.NoopDeliverySender;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class DeliveryConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(
                    DeliveryEnabledConfiguration.class,
                    DeliveryDisabledConfiguration.class);

    @Test
    void missingFlagUsesNoop() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(DeliverySender.class);
            assertThat(context.getBean(DeliverySender.class))
                    .isInstanceOf(NoopDeliverySender.class);
        });
    }

    @Test
    void falseFlagUsesNoop() {
        runner.withPropertyValues(
                "features.delivery.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context.getBean(DeliverySender.class))
                    .isInstanceOf(NoopDeliverySender.class);
            });
    }

    @Test
    void trueFlagUsesConfiguredSender() {
        runner.withPropertyValues(
                "features.delivery.enabled=true",
                "app.delivery.endpoint=https://sandbox.example.org",
                "app.delivery.connect-timeout=2s",
                "app.delivery.max-attempts=2")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(DeliverySender.class);
                assertThat(context.getBean(DeliverySender.class))
                    .isInstanceOf(ConfiguredDeliverySender.class);
            });
    }

    @Test
    void unexpectedFlagMatchesNeither() {
        runner.withPropertyValues(
                "features.delivery.enabled=unexpected")
            .run(context -> {
                assertThat(context)
                    .doesNotHaveBean(DeliverySender.class);
            });
    }
}
~~~

Giả định `spring-boot-starter-test` cung cấp JUnit Jupiter và AssertJ. Test không khởi tạo một ứng dụng web hoặc kết nối remote.

### Kiểm tra thiếu endpoint

Với Bean Validation được cấu hình đầy đủ, nếu flag true nhưng `app.delivery.endpoint` thiếu, record mang `@NotNull` sẽ vi phạm constraint. Trong một test context tối giản, phải bảo đảm validation infrastructure thực sự được cung cấp trước khi khẳng định lỗi cụ thể.

`ApplicationContextRunner` cho phép test rất chính xác từng configuration; nó không tự thay thế integration test kiểm chứng component scan và toàn bộ bootstrap.

## 25. Test nhánh disabled không cần tham số

Một test hữu ích:

~~~java
@Test
void disabledDoesNotBindUnusedClientData() {
    runner.withPropertyValues(
            "features.delivery.enabled=false",
            "app.delivery.max-attempts=not-a-number")
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context.getBean(DeliverySender.class))
                .isInstanceOf(NoopDeliverySender.class);
        });
}
~~~

Kết quả mong đợi của mô hình ví dụ là disabled branch không bind `DeliveryClientProperties`, nên dữ liệu của module không được sử dụng không trở thành bắt buộc.

Nếu case trên fail, kiểm tra:

1. `@ConfigurationPropertiesScan` đang tự đăng ký record không?
2. Có `@EnableConfigurationProperties` trên class vô điều kiện khác không?
3. Một bean nào đó có inject record kể cả khi disabled không?
4. Implementation có vô tình mang `@Component` không?
5. Có một auto-configuration khác dùng key đó không?

Không nên bỏ mọi validation của các module chỉ để test này pass. Mục tiêu là đảm bảo đúng ranh giới đã chọn: dữ liệu chỉ phải hợp lệ khi được sử dụng.

### Cú pháp YAML vẫn cần hợp lệ

Nếu YAML bị lỗi format, Spring Boot có thể thất bại trong Config Data parsing trước khi xét condition. `@ConditionalOnProperty` không làm Spring bỏ qua việc đọc/parse toàn bộ file chứa dữ liệu sai.

## 26. Test toàn bộ wiring bằng @SpringBootTest

Ví dụ disabled:

~~~java
package com.example.delivery;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.delivery.service.DeliveryWorkflow;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "features.delivery.enabled=false"
})
class DeliveryDisabledIntegrationTest {

    @Autowired
    DeliveryWorkflow workflow;

    @Test
    void usesNoopSender() {
        assertThat(workflow.senderMode()).isEqualTo("disabled");
    }
}
~~~

Ví dụ enabled:

~~~java
@SpringBootTest(properties = {
        "features.delivery.enabled=true",
        "app.delivery.endpoint=https://sandbox.example.org"
})
class DeliveryEnabledIntegrationTest {

    @Autowired
    DeliveryWorkflow workflow;

    @Test
    void usesConfiguredSender() {
        assertThat(workflow.senderMode()).isEqualTo("configured");
    }
}
~~~

Các annotation và import phù hợp cần có trong file test thứ hai tương tự test đầu. `@SpringBootTest` xác nhận app component scan, conditional configurations và dependency injection chạy cùng nhau.

Khi ứng dụng có thêm database, queue hoặc service client khác, integration test có thể cần fake/embedded infrastructure. Nếu chỉ cần kiểm tra condition, `ApplicationContextRunner` nhỏ và dễ lặp hơn.

## 27. Chẩn đoán lỗi thiếu bean khi bật/tắt

Nếu gặp:

~~~text
No qualifying bean of type 'DeliverySender'
~~~

hãy kiểm tra:

1. Tên đầy đủ property thực sự là `features.delivery.enabled` hay bị viết thiếu `s`?
2. Value là `true`, `false`, missing hay một chuỗi không mong muốn?
3. Có `havingValue="true"`/`havingValue="false"` chính xác không?
4. Nhánh disabled có `matchIfMissing=true` không?
5. Class configuration có được scan hoặc import không?
6. Có dependency mới đòi hỏi sender khi cả hai branch không match không?
7. Source ưu tiên cao hơn (env/CLI) có đang thay flag không?
8. `@ConfigurationPropertiesScan` hoặc `@Component` khác có tạo trùng bean không?

Có thể chạy với:

~~~bash
java -jar delivery-demo.jar --debug
~~~

để Spring Boot cung cấp condition evaluation report. Trong báo cáo, tìm tên configuration, condition matched/unmatched và các thông tin liên quan.

Nếu dùng Spring Boot Actuator, endpoint conditions có thể giúp quan sát các condition khi được cấu hình và bảo vệ quyền truy cập thích hợp. Không công khai thông tin chẩn đoán nội bộ hoặc secrets.

## 28. Vì sao condition matched nhưng bean vẫn lỗi?

Condition true chỉ cho phép Spring **thử tạo bean**. Nó không chứng minh bean đã tạo thành công.

Một số nguyên nhân:

- `app.delivery.endpoint` vắng mặt và `@NotNull` fail.
- `app.delivery.connect-timeout=abc` không bind thành `Duration`.
- `app.delivery.max-attempts=0` vi phạm `@Min(1)`.
- Constructor HTTP client ném exception.
- Một dependency như connection factory chưa được tạo.
- Sai cấu hình TLS/credentials.
- Bean khác cùng type tạo ambiguous injection.

Đây là những lỗi **binding, validation hoặc bean creation**, khác lỗi condition không match.

Phân biệt ba câu hỏi:

~~~text
Condition có match không?
    |
    v
Configuration/Bean definition có được đăng ký không?
    |
    v
Bean có được tạo và khởi tạo thành công không?
~~~

Nếu chưa biết lỗi thuộc tầng nào, không nên tự thêm `matchIfMissing=true` để “sửa” mọi tình huống.

## 29. @ConditionalOnProperty không đánh giá từ record đã bind

Sai nhận thức:

~~~java
@ConditionalOnProperty(
        name = "features.delivery.enabled",
        havingValue = "true")
~~~

không có nghĩa Spring tự gọi:

~~~java
deliveryFeatureProperties.enabled()
~~~

trên một bean record rồi mới chọn condition. Spring kiểm tra **Environment property**.

Điều đó có nghĩa:

- Chỉ cần property nằm trong nguồn cấu hình được xét đúng thời điểm.
- Không cần tạo một `@ConfigurationProperties` class chỉ để đọc một flag.
- Một validator đặt trên record chứa `enabled` không tự được gọi trước condition.
- Sự sai lệch giữa tên property trong Environment và tên bean record không được “sửa” bởi relaxed binding tùy ý.

Nếu cần feature policy có logic phức tạp hơn so sánh chuỗi, thiết kế một custom condition hoặc feature-selection layer rõ ràng.

## 30. Feature flags và security

Không coi `features.delivery.enabled=true` là một cơ chế cấp quyền bảo mật.

Flag chỉ điều khiển **đăng ký bean**. Nó không xác thực người dùng, kiểm tra quyền gọi API hoặc bảo vệ secrets. Khi tạo adapter thật, cần:

- Credential phù hợp môi trường.
- Quyền kết nối tối thiểu.
- TLS/HTTPS khi yêu cầu.
- Timeout và retry có giới hạn.
- Không log payload hoặc token.
- Test để chứng minh endpoint production không được dùng trong môi trường test.
- Quy trình kiểm soát rollout/restart.

Nếu một feature liên quan giao dịch quan trọng, nên có guardrail CI/deployment để tránh accidental enable.

## 31. Migration từ thiết kế cũ

Giả sử một module trước đó dùng:

~~~properties
app.delivery.enabled=true
app.delivery.endpoint=https://sandbox.example.org
~~~

và record:

~~~java
@ConfigurationProperties(prefix = "app.delivery")
record DeliveryProperties(boolean enabled, URI endpoint) {}
~~~

Một lộ trình nâng cấp:

1. Xác định rõ **chính sách default** của enabled; thường chọn default false cho feature có tác dụng ngoài.
2. Đặt một canonical flag mới, ví dụ `features.delivery.enabled`.
3. Tạo record data chỉ chứa endpoint/timeout/retry.
4. Tách sender interface khỏi service.
5. Đặt bean registration cho sender thật và typed config trong enabled configuration.
6. Quyết định disabled tạo No-op hay không tạo bean.
7. Cập nhật Config Data, env vars, Helm chart, Docker Compose, CI.
8. Viết test cho missing/false/true/invalid flag và dữ liệu thiếu khi enabled.
9. Xem lại component scan/`@ConfigurationPropertiesScan` để tránh bind data lúc disabled.
10. Có kế hoạch deprecation cho `app.delivery.enabled` trước khi bỏ.

Nếu cả key cũ và mới cùng tồn tại, không mặc định hiểu chúng là alias. Cần quy định key nào thắng, có cảnh báo hay không, và lúc nào ngừng hỗ trợ key cũ. Hai `@ConditionalOnProperty` trên cùng class không tự tạo phép OR theo ý định.

## 32. Docker Compose và Kubernetes

Docker Compose:

~~~yaml
services:
  app:
    image: delivery-demo:latest
    environment:
      FEATURES_DELIVERY_ENABLED: "true"
      APP_DELIVERY_ENDPOINT: "https://sandbox.example.org"
      APP_DELIVERY_CONNECTTIMEOUT: "2s"
~~~

Trong Kubernetes Deployment:

~~~yaml
env:
  - name: FEATURES_DELIVERY_ENABLED
    value: "false"
~~~

Nếu flag false, không cần cung cấp endpoint/credential chỉ dùng cho sender thật. Nếu flag true, phải cung cấp typed config đầy đủ từ ConfigMap, Secret hoặc nguồn phù hợp.

Đổi ConfigMap không tự làm một process Spring Boot tiêu chuẩn tạo lại bean graph. Thường cần rollout/restart hoặc một cơ chế refresh được thiết kế và kiểm thử riêng.

## 33. Bài tập thực hành

### Bài 1 — Tách dữ liệu khỏi lựa chọn

Một record có `enabled`, `directory` và `batchSize`. Hãy tạo flag `features.export.enabled` và record `ExportProperties(directory, batchSize)` riêng.

### Bài 2 — Mặc định tắt

Tạo hai nhánh conditional configuration với `havingValue="true"` và `havingValue="false", matchIfMissing=true`. Thiếu key phải chọn No-op.

### Bài 3 — Kiểm tra giá trị lạ

Đặt `features.export.enabled=maybe`. Vì sao hai condition không match, trong khi annotation không ghi `havingValue` có thể match? **Đáp án:** condition mặc định chỉ yêu cầu property tồn tại và khác false.

### Bài 4 — Validation có điều kiện

Feature false nhưng endpoint thiếu; feature true nhưng endpoint thiếu. Đặt `@EnableConfigurationProperties` ở đâu để chỉ case thứ hai bị validation chặn?

### Bài 5 — Config Data precedence

File chung đặt enabled=false; CLI đặt `--features.delivery.enabled=true`. Đoán nhánh được chọn khi không có nguồn mạnh hơn.

### Bài 6 — Multiple names

`name={"enabled","licensed"}` với `havingValue="true"` yêu cầu bao nhiêu key phù hợp? **Đáp án:** cả hai.

### Bài 7 — Không dùng endpoint làm flag

Vì sao sự có mặt của API key hoặc endpoint không chứng minh chức năng được phép hoạt động?

### Bài 8 — Unit test

Dùng `ApplicationContextRunner` cho bốn trường hợp missing, false, true, invalid và xác nhận bean type/absence.

### Bài 9 — Runtime toggle

Nếu muốn quyết định theo user và đổi trạng thái ngay lập tức, tại sao `@ConditionalOnProperty` không đủ? Thiết kế một interface `FeatureDecisions` chạy trong request flow.

### Bài 10 — Tránh tạo bean trùng

Nếu ConfiguredDeliverySender có `@Component` và cũng được tạo từ `@Bean` conditional, có rủi ro gì? Hãy sửa bằng một đường đăng ký duy nhất.

### Bài 11 — Chẩn đoán

Condition true nhưng startup fail do `app.delivery.max-attempts=0`. Lỗi thuộc condition, conversion hay validation? **Đáp án:** conversion sang int có thể thành công; giá trị bị Bean Validation từ chối.

### Bài 12 — Rollout

Hãy đề xuất cách triển khai feature mới sao cho production mặc định tắt, test bật với sandbox, không log secrets, và có kiểm thử rollback.

## 34. Tổng kết

- **`@ConditionalOnProperty`** quyết định cấu hình hoặc bean nào được đăng ký dựa trên giá trị Environment trong quá trình khởi tạo Spring context.
- **`@ConfigurationProperties`** mô tả dữ liệu có kiểu, hỗ trợ conversion, default và validation.
- Tách `features.delivery.enabled` khỏi `app.delivery.endpoint`, `connect-timeout` và `max-attempts` để giảm phụ thuộc.
- Dùng `havingValue="true"` cho boolean switch nghiêm ngặt; nếu không ghi, mọi value có mặt khác false có thể match.
- `matchIfMissing` là default của **condition**, không phải default property được ghi vào Environment.
- Muốn dữ liệu của tính năng tắt không bị bind/validate, đăng ký record trong configuration có điều kiện enabled; tránh scan/register record ở nơi khác vô điều kiện.
- No-op phù hợp với tính năng tùy chọn; đối với tác vụ bắt buộc, nên fail fast thay vì bỏ qua.
- Condition không tự làm hot reload khi environment hoặc file thay đổi.
- Dùng `ApplicationContextRunner` để kiểm tra nhánh bật/tắt, và `@SpringBootTest` để kiểm tra toàn bộ wiring.
- Khi debug, kiểm tra property hiệu lực, condition report, component scan, typed config registration và lỗi bean creation riêng.
- Feature flag không thay thế security, Bean Validation hoặc cơ chế quyết định runtime theo người dùng.

## Tài liệu tham khảo

- [Spring Boot 3.3 — ConditionalOnProperty API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
