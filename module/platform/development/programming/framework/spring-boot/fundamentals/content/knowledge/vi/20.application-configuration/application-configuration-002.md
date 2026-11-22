# `application.properties`, `application.yml` và lựa chọn định dạng

Trong Spring Boot, **cấu hình ứng dụng** là những giá trị giúp cùng một chương trình hoạt động đúng ở nhiều môi trường: cổng HTTP, thông tin kết nối database, mức logging, timeout, giới hạn upload, hay các tính năng được bật hoặc tắt. Thay vì viết cố định những giá trị đó trong Java, bạn có thể đưa chúng vào các file cấu hình và để Spring Boot nạp thông qua `Environment`.

Hai định dạng thường gặp là **`application.properties`** và **`application.yml`**. Chúng phục vụ cùng mục đích nhưng khác cách biểu diễn:

- `application.properties` sử dụng các cặp **khóa–giá trị**, thường viết theo dạng `key=value`.
- `application.yml` sử dụng **YAML**, cho phép nhóm các giá trị thành cấu trúc lồng nhau thông qua thụt dòng.
- Spring Boot đọc cả hai dưới dạng **configuration properties**; phần lớn cơ chế binding và auto-configuration làm việc với giá trị đã được nạp, thay vì quan tâm file ban đầu là `.properties` hay `.yml`.

Chọn định dạng không quyết định ứng dụng “mạnh hơn” hay “nhanh hơn”. Điều quan trọng là **cấu hình dễ hiểu, ít gây nhầm lẫn và được nạp đúng từ các nguồn mà bạn dự định sử dụng**.

## 1. Tại sao cần tách cấu hình khỏi mã nguồn?

Giả sử một ứng dụng bán hàng chạy ở ba môi trường:

| Môi trường | Cổng HTTP | Database | Logging |
| --- | --- | --- | --- |
| Local | 8080 | Database phát triển | DEBUG ở package ứng dụng |
| Staging | 8081 | Database kiểm thử | INFO |
| Production | 8080 | Database production | WARN hoặc INFO |

Nếu mỗi lần đổi môi trường bạn phải sửa constructor, hằng số Java hoặc commit lại mật khẩu, chương trình sẽ khó triển khai và khó bảo trì.

Spring Boot hỗ trợ **externalized configuration**: cùng một artifact có thể nhận cấu hình từ file, profile, biến môi trường, Java system properties, command-line arguments và những nguồn khác.

```text
                Mã ứng dụng Java
                        |
                        v
               Spring Boot startup
                        |
         +--------------+--------------+
         |              |              |
         v              v              v
   application.*    Environment     Command-line
   và profile file    variables      arguments
         |              |              |
         +--------------+--------------+
                        |
                        v
                Spring Environment
                        |
                        v
             @ConfigurationProperties
                   / @Value
                        |
                        v
              Bean và auto-configuration
```

Ví dụ, application có thể chạy trên cổng 8080 ở local nhưng dùng cổng 9000 khi truyền `--server.port=9000`, mà không cần đổi mã Java.

## 2. Vị trí và tên file cấu hình

Trong dự án Maven hoặc Gradle thông thường, cấu hình nằm ở:

```text
src/
└── main/
    ├── java/
    │   └── com/example/shop/ShopApplication.java
    └── resources/
        ├── application.properties
        └── application.yml
```

Thông thường **chọn một trong hai** file trên làm cấu hình cơ bản. Không cần tạo đồng thời cả `application.properties` và `application.yml`.

Khi build, các file trong `src/main/resources` được đưa lên classpath. Spring Boot sử dụng cơ chế **Config Data** để tìm và nạp những file cấu hình có tên và vị trí được hỗ trợ.

Ngoài classpath, Spring Boot còn hỗ trợ các vị trí cấu hình bên ngoài artifact, ví dụ file nằm trong thư mục cấu hình khi chạy ứng dụng:

```text
shop-app.jar
config/
└── application.properties
```

Điều này cho phép thay giá trị cấu hình mà không đóng gói lại JAR.

### 2.1. Phần tên `application` có ý nghĩa gì?

`application` là tên cấu hình mặc định được Spring Boot tìm kiếm. Với profile, tên file có thể mang hậu tố:

```text
application.properties
application-dev.properties
application-prod.properties
```

hoặc:

```text
application.yml
application-dev.yml
application-prod.yml
```

Bạn có thể thay tên cấu hình mặc định bằng các tham số cấu hình phù hợp như `spring.config.name`, nhưng chỉ nên làm khi có yêu cầu rõ ràng.

### 2.2. `.yaml` hay `.yml`?

YAML có thể sử dụng phần mở rộng `.yaml` hoặc `.yml`; Spring Boot hỗ trợ cả hai trong các vị trí cấu hình phù hợp. Một nhóm nên chọn **một quy ước duy nhất** để tránh phân tán cấu hình.

Trong bài này, các ví dụ sử dụng `application.yml`.

## 3. Cú pháp cơ bản của `application.properties`

File `.properties` biểu diễn cấu hình theo từng dòng:

```properties
spring.application.name=shop-service
server.port=8081
logging.level.com.example.shop=DEBUG
app.catalog.currency=VND
app.catalog.page-size=20
app.catalog.enabled=true
```

Phần bên trái dấu `=` là key; phần bên phải là value. Dấu `:` cũng có thể được dùng làm dấu phân tách theo quy tắc Java properties, nhưng trong dự án nên thống nhất viết `=` để dễ đọc.

### 3.1. Key có dấu chấm biểu diễn nhóm logic

Ví dụ:

```properties
app.email.enabled=true
app.email.sender=no-reply@example.com
app.email.retry.max-attempts=3
app.email.retry.delay=5s
```

Bạn có thể hình dung các key này như cây:

```text
app
└── email
    ├── enabled
    ├── sender
    └── retry
        ├── max-attempts
        └── delay
```

Dấu chấm ở đây là một phần quy ước đặt tên configuration property. Bản thân file `.properties` vẫn là danh sách key–value phẳng.

### 3.2. Comment

Dùng `#` hoặc `!` ở đầu dòng để chú thích:

```properties
# Cổng dùng cho môi trường phát triển
server.port=8081

! Giới hạn số lần thử gửi email
app.email.retry.max-attempts=3
```

Không nên đặt dữ liệu cần sử dụng trong comment. Và tránh phụ thuộc vào “comment cuối dòng” như cú pháp chung cho `.properties`: dấu `#` phía sau giá trị có thể được xem là một phần của value, tùy cách đọc.

### 3.3. Chuỗi có khoảng trắng

Ví dụ:

```properties
app.company.display-name=Phuong Workspace
```

Không cần đặt chuỗi trong dấu ngoặc kép chỉ vì có dấu cách. Nếu viết:

```properties
app.company.display-name="Phuong Workspace"
```

dấu ngoặc kép có thể được hiểu là ký tự nằm trong giá trị ở tầng Java properties; đây là điểm khác biệt đáng chú ý so với YAML.

### 3.4. Các giá trị cơ bản đều bắt đầu từ text

Ví dụ:

```properties
app.feature.enabled=true
app.feature.limit=100
app.feature.timeout=15s
```

File properties lưu giá trị ở dạng chuỗi; khi bind vào Java, Spring Boot có thể chuyển đổi `true` thành `boolean`, `100` thành `int`, `15s` thành `Duration` nhờ hệ thống conversion.

Việc chuyển đổi thành công phụ thuộc kiểu Java đích và định dạng giá trị hợp lệ. Không nên giả định mọi chuỗi đều có thể được ép sang mọi kiểu.

## 4. Cú pháp cơ bản của `application.yml`

YAML biểu diễn cấu trúc thông qua **thụt dòng**, dấu `:` và danh sách:

```yaml
spring:
  application:
    name: shop-service

server:
  port: 8081

logging:
  level:
    com.example.shop: DEBUG

app:
  catalog:
    currency: VND
    page-size: 20
    enabled: true
```

Cấu hình trên có ý nghĩa tương đương các key phẳng:

```properties
spring.application.name=shop-service
server.port=8081
logging.level.com.example.shop=DEBUG
app.catalog.currency=VND
app.catalog.page-size=20
app.catalog.enabled=true
```

YAML giúp nhìn thấy quan hệ cha–con khi có nhiều property cùng prefix.

### 4.1. Thụt dòng quyết định cấu trúc

Đúng:

```yaml
app:
  notification:
    enabled: true
    max-retries: 3
```

Hai property là:

```text
app.notification.enabled
app.notification.max-retries
```

Sai ý định:

```yaml
app:
  notification:
  enabled: true
  max-retries: 3
```

Lúc này `enabled` và `max-retries` không còn là các phần tử con của `notification`. YAML có thể vẫn hợp lệ về cú pháp nhưng cấu trúc property không còn như mong muốn.

**Dùng dấu cách để thụt dòng, tránh tab.** Một quy ước phổ biến là hai dấu cách cho mỗi cấp. Không trộn nhiều kiểu indentation trong cùng file.

### 4.2. Comment trong YAML

```yaml
# Cấu hình chức năng gửi email
app:
  email:
    enabled: true # Bật email ở môi trường hiện tại
```

Dấu `#` mở comment khi xuất hiện ở ngữ cảnh comment hợp lệ của YAML. Nếu giá trị thực sự chứa ký tự `#`, dấu `:` hoặc những ký tự đặc biệt khác, dùng chuỗi được quote để giảm rủi ro diễn giải sai.

### 4.3. Khi nào cần quote chuỗi?

Ví dụ:

```yaml
app:
  message: "Ready: accepting requests"
  code: "00123"
  label: "true"
  template: "${APP_TEMPLATE:default}"
```

Trong YAML, các giá trị không có quote có thể được parser nhận là Boolean, số hoặc null thay vì text, tùy cú pháp và phiên bản YAML. Nếu bạn cần giữ nguyên mã có số 0 đầu, chuỗi `"true"` hoặc dữ liệu có ký tự đặc biệt, hãy quote.

Phân biệt:

```yaml
app:
  enabled: true
  enabled-label: "true"
  max-attempts: 3
  code: "0003"
```

`enabled` mang nghĩa Boolean, `max-attempts` mang nghĩa số, còn `enabled-label` và `code` được biểu diễn rõ ràng là chuỗi.

## 5. So sánh trực tiếp hai định dạng

Xét một cấu hình ứng dụng có HTTP server, client tích hợp và retry:

**`application.properties`:**

```properties
server.port=8081
app.client.base-url=https://api.example.com
app.client.connect-timeout=2s
app.client.read-timeout=10s
app.client.retry.enabled=true
app.client.retry.max-attempts=3
app.client.retry.backoff=500ms
```

**`application.yml`:**

```yaml
server:
  port: 8081

app:
  client:
    base-url: https://api.example.com
    connect-timeout: 2s
    read-timeout: 10s
    retry:
      enabled: true
      max-attempts: 3
      backoff: 500ms
```

| Tiêu chí | `application.properties` | `application.yml` |
| --- | --- | --- |
| Cấu trúc | Key–value phẳng | Phân cấp qua indentation |
| Dễ tìm một property bằng tên đầy đủ | Thường thuận tiện | Phải nhìn theo các cấp |
| Nhóm property chung prefix | Lặp prefix trên nhiều dòng | Nhóm tự nhiên |
| Danh sách/map phức tạp | Dùng chỉ số và key đầy đủ | Biểu diễn trực quan hơn |
| Rủi ro cú pháp | Escape, khoảng trắng, key trùng | Indentation, kiểu dữ liệu và key trùng |
| Dễ copy thành biến môi trường | Gần tên key phẳng | Cần chuyển đổi tên key |
| Phù hợp dự án nhỏ | Rất tốt | Cũng tốt |
| Phù hợp cấu hình phân cấp lớn | Được nhưng dài dòng | Thường dễ quan sát hơn |

Spring Boot có thể bind cả hai về cùng kiểu Java. Quyết định định dạng vì vậy chủ yếu liên quan đến **khả năng đọc, quy ước nhóm và quản lý thay đổi**.

## 6. Danh sách trong hai định dạng

Giả sử ứng dụng cần danh sách các địa chỉ email nhận cảnh báo.

### 6.1. Danh sách trong `.properties`

Bạn có thể sử dụng chỉ số:

```properties
app.alert.recipients[0]=ops@example.com
app.alert.recipients[1]=oncall@example.com
app.alert.recipients[2]=security@example.com
```

### 6.2. Danh sách trong YAML

```yaml
app:
  alert:
    recipients:
      - ops@example.com
      - oncall@example.com
      - security@example.com
```

YAML thường dễ nhìn hơn khi danh sách có nhiều phần tử.

### 6.3. Danh sách object

**Properties:**

```properties
app.integrations[0].name=billing
app.integrations[0].base-url=https://billing.example.com
app.integrations[0].timeout=3s
app.integrations[1].name=inventory
app.integrations[1].base-url=https://inventory.example.com
app.integrations[1].timeout=2s
```

**YAML:**

```yaml
app:
  integrations:
    - name: billing
      base-url: https://billing.example.com
      timeout: 3s
    - name: inventory
      base-url: https://inventory.example.com
      timeout: 2s
```

Với cấu trúc như `List<IntegrationProperties>`, YAML thường ít lặp lại hơn và giúp nhận biết từng phần tử.

### 6.4. Danh sách qua nhiều property source

Một điểm cần chú ý của Spring Boot: khi **một list được cấu hình ở nhiều nguồn có độ ưu tiên khác nhau**, list ở nguồn ưu tiên cao thường **thay thế** list ở nguồn ưu tiên thấp; không nên mặc định các phần tử sẽ được nối lại.

Ví dụ, nếu file chung có ba recipients, còn file profile chỉ có một recipient ở cùng key, kết quả binding có thể chỉ có phần tử từ profile có độ ưu tiên cao hơn.

Nếu mong muốn hợp nhất nhiều nguồn, bạn cần thiết kế và kiểm thử riêng. Đừng dựa vào trực giác rằng `List` luôn được merge như một `Map`.

## 7. Map và các key đặc biệt

Ví dụ một map cấu hình giá theo mã:

**Properties:**

```properties
app.price-rules.standard=100
app.price-rules.premium=80
```

**YAML:**

```yaml
app:
  price-rules:
    standard: 100
    premium: 80
```

Cả hai có thể bind vào `Map<String, Integer>` khi khai báo `@ConfigurationProperties` phù hợp.

### 7.1. Map key có dấu chấm hoặc ký tự đặc biệt

Nếu key thực tế của map là `"region.hcm"` và bạn cần giữ nguyên dấu chấm như một phần của key, cấu hình có thể cần biểu diễn bằng bracket notation tùy kiểu value và cách binding.

Ví dụ:

```properties
app.labels.[region.hcm]=Southern region
```

Với YAML:

```yaml
app:
  labels:
    "[region.hcm]": "Southern region"
```

Spring Boot sử dụng bracket notation để giữ các ký tự không thuộc dạng tên property thông thường trong một số trường hợp bind `Map`. Nếu key chứa `/`, dấu chấm hoặc các ký tự đặc biệt, hãy tham khảo quy tắc map binding của phiên bản Spring Boot đang dùng và xác nhận kết quả thực tế.

## 8. `@ConfigurationProperties`: cùng một Java model cho hai file

Một ưu điểm của Spring Boot là bạn có thể gom các property liên quan thành một object Java có kiểu rõ ràng.

Ví dụ cấu hình client:

**`application.properties`:**

```properties
app.partner.base-url=https://partner.example.com
app.partner.timeout=5s
app.partner.max-attempts=3
app.partner.enabled=true
```

Hoặc **`application.yml`:**

```yaml
app:
  partner:
    base-url: https://partner.example.com
    timeout: 5s
    max-attempts: 3
    enabled: true
```

Với Spring Boot 3.x và Java có hỗ trợ records:

```java
package com.example.shop.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        URI baseUrl,
        Duration timeout,
        int maxAttempts,
        boolean enabled
) {
}
```

Spring Boot có thể bind `base-url` vào `baseUrl`, `max-attempts` vào `maxAttempts`, `"5s"` vào `Duration`, và URL thành `URI` thông qua cơ chế binding/conversion.

### 8.1. Đăng ký configuration properties class

Một cách phổ biến là dùng `@ConfigurationPropertiesScan`:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Khi record `PartnerProperties` ở package con được scan, Spring Boot đăng ký nó làm configuration properties bean.

Một cách khác là chỉ định rõ class:

```java
@Configuration
@EnableConfigurationProperties(PartnerProperties.class)
class PartnerConfiguration {
}
```

Không nhất thiết kết hợp cả hai cách nếu chúng cùng nhằm đăng ký một class.

### 8.2. Inject vào service

```java
package com.example.shop.service;

import com.example.shop.config.PartnerProperties;
import org.springframework.stereotype.Service;

@Service
public class PartnerService {

    private final PartnerProperties properties;

    public PartnerService(PartnerProperties properties) {
        this.properties = properties;
    }

    public void printConfiguration() {
        System.out.println(properties.baseUrl());
        System.out.println(properties.timeout());
        System.out.println(properties.maxAttempts());
    }
}
```

Service chỉ quan tâm tới một object đã được bind, không cần biết giá trị ban đầu đến từ YAML, properties, biến môi trường hay command line.

### 8.3. Validation của cấu hình

Bạn có thể kết hợp Jakarta Bean Validation với configuration properties để phát hiện giá trị sai ở startup:

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        @NotNull URI baseUrl,
        @NotNull Duration timeout,
        @Min(1) int maxAttempts,
        boolean enabled
) {
}
```

Ví dụ này giả định dự án có dependency validation tương thích, thường là starter validation của dòng Spring Boot đang dùng. Nếu cấu hình thiếu `base-url` hoặc `max-attempts` không hợp lệ, quá trình bind/validation có thể làm startup thất bại với thông tin property liên quan.

**Không nên coi validation là công cụ che lỗi runtime.** Nó giúp xác nhận cấu hình ban đầu đúng hợp đồng; dịch vụ bên ngoài vẫn có thể không phản hồi trong quá trình chạy.

## 9. `@Value` và khi nào nên dùng

Với một giá trị đơn giản, bạn có thể inject trực tiếp:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final String prefix;

    public GreetingService(
            @Value("${app.greeting.prefix:Hello}") String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        return prefix + ", " + name;
    }
}
```

Trong ví dụ trên, placeholder có giá trị mặc định `Hello` nếu property không được tìm thấy.

So sánh:

| Tình huống | Lựa chọn thường phù hợp |
| --- | --- |
| Một hoặc hai property đơn giản, rời nhau | `@Value` |
| Nhiều property chung prefix | `@ConfigurationProperties` |
| Cấu hình có list, map hoặc object lồng nhau | `@ConfigurationProperties` |
| Cần validation theo model | `@ConfigurationProperties` với validation |
| Muốn constructor injection rõ ràng và dễ test | Configuration properties object |

`@Value` hỗ trợ property placeholders và SpEL; còn `@ConfigurationProperties` được thiết kế cho binding cấu hình có kiểu và hỗ trợ relaxed binding. Không nên mặc định hai cơ chế có mọi quy tắc chuyển đổi/tên key hoàn toàn giống nhau.

## 10. Relaxed binding và quy ước đặt tên property

Spring Boot hỗ trợ **relaxed binding** để ánh xạ các cách viết tên cấu hình vào cùng một Java property.

Ví dụ Java:

```java
public record StorageProperties(long maxFileSize) {
}
```

Các cách biểu diễn phù hợp theo nguồn cấu hình có thể gồm:

```properties
app.storage.max-file-size=10485760
```

```yaml
app:
  storage:
    max-file-size: 10485760
```

hoặc một biến môi trường theo quy tắc chuyển tên:

```text
APP_STORAGE_MAXFILESIZE=10485760
```

Với environment variables trong cơ chế binding của Spring Boot, tên property chuẩn dạng kebab-case thường được chuyển bằng cách thay dấu `.` thành `_`, xóa dấu `-`, rồi chuyển thành chữ hoa. Vì vậy `app.storage.max-file-size` tương ứng với `APP_STORAGE_MAXFILESIZE` theo quy tắc đó.

Không nên suy ra mọi biến môi trường tự đặt với dấu gạch dưới giữa từng từ sẽ luôn được hiểu như mong muốn. Để tránh nhầm, hãy dùng tên key canonical và xác nhận binding trong môi trường triển khai.

### 10.1. Nên dùng kebab-case làm key canonical

Quy ước dễ đọc:

```properties
app.email.max-attempts=3
app.storage.max-file-size=10MB
```

Tương đương trong YAML:

```yaml
app:
  email:
    max-attempts: 3
  storage:
    max-file-size: 10MB
```

Kebab-case giúp cấu hình nhất quán, rõ ràng trong tài liệu và thân thiện với `@ConfigurationProperties`.

## 11. Duration, DataSize và những kiểu dữ liệu tiện dụng

Spring Boot có hỗ trợ binding nhiều loại giá trị cấu hình sang các kiểu Java:

| Giá trị | Kiểu Java ví dụ | Ý nghĩa |
| --- | --- | --- |
| `true` | `boolean` | Cờ bật/tắt |
| `42` | `int`, `long` | Số |
| `5s` | `Duration` | Năm giây |
| `250ms` | `Duration` | 250 mili giây |
| `10MB` | `DataSize` | Kích thước dữ liệu |
| `https://example.com` | `URI` | Địa chỉ URI |
| `DEBUG` | `LogLevel` hoặc enum phù hợp | Mức log |

Ví dụ:

```properties
app.http.connect-timeout=2s
app.http.read-timeout=750ms
app.upload.max-file-size=10MB
```

Hoặc:

```yaml
app:
  http:
    connect-timeout: 2s
    read-timeout: 750ms
  upload:
    max-file-size: 10MB
```

Với custom configuration properties, có thể khai báo:

```java
@ConfigurationProperties(prefix = "app.http")
public record HttpClientProperties(
        Duration connectTimeout,
        Duration readTimeout
) {
}
```

Với kích thước file:

```java
@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(DataSize maxFileSize) {
}
```

`DataSize` nằm trong `org.springframework.util.unit.DataSize`. Nếu dùng Duration/DataSize không ghi đơn vị, Spring Boot có quy tắc đơn vị mặc định theo kiểu binding và annotation hỗ trợ. Khi cấu hình cần dễ đọc, hãy **ghi đơn vị tường minh** như `2s`, `750ms` hoặc `10MB`.

## 12. Profile-specific configuration

Spring Boot cho phép thay đổi cấu hình theo môi trường bằng profile.

Ví dụ dùng properties:

```text
src/main/resources/
├── application.properties
├── application-dev.properties
└── application-prod.properties
```

**`application.properties`:**

```properties
spring.application.name=shop-service
server.port=8080
app.mail.enabled=false
```

**`application-dev.properties`:**

```properties
server.port=8081
logging.level.com.example.shop=DEBUG
app.mail.enabled=true
```

**`application-prod.properties`:**

```properties
logging.level.root=INFO
app.mail.enabled=true
```

Khi profile `dev` được kích hoạt, các giá trị profile-specific có thể ghi đè giá trị chung từ nguồn có độ ưu tiên thấp hơn.

### 12.1. Profile trong YAML cũng tương tự

```text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
```

**`application.yml`:**

```yaml
spring:
  application:
    name: shop-service

server:
  port: 8080

app:
  mail:
    enabled: false
```

**`application-dev.yml`:**

```yaml
server:
  port: 8081

logging:
  level:
    com.example.shop: DEBUG

app:
  mail:
    enabled: true
```

### 12.2. Kích hoạt profile

Qua command line:

```bash
java -jar shop-service.jar --spring.profiles.active=dev
```

Qua biến môi trường:

```text
SPRING_PROFILES_ACTIVE=dev
```

Hoặc có thể đặt trong cấu hình không thuộc một profile-specific document:

```properties
spring.profiles.active=dev
```

Với hệ thống triển khai nhiều môi trường, thường đặt active profile bên ngoài artifact để giữ cùng bản build giữa dev, staging và production.

### 12.3. Không đặt `spring.profiles.active` sai chỗ

Trong Config Data của Spring Boot hiện đại, `spring.profiles.active` và `spring.profiles.default` chỉ nên được đặt trong **non-profile-specific documents**. Không đặt chúng trong `application-dev.yml` hoặc bên trong document đã được kích hoạt bằng `spring.config.activate.on-profile`.

Ví dụ không nên viết trong `application-dev.yml`:

```yaml
spring:
  profiles:
    active: prod
```

Vì đó là nguồn cấu hình chỉ được nạp khi profile dev đã được chọn, việc khai báo lại active profile ở đây không phù hợp với quy tắc Config Data hiện đại.

## 13. Nhiều YAML document trong một file

YAML cho phép phân tách document bằng dòng:

```yaml
---
```

Trong Spring Boot, bạn có thể dùng `spring.config.activate.on-profile` để chỉ định document nào áp dụng khi profile tương ứng active.

Ví dụ một `application.yml`:

```yaml
spring:
  application:
    name: shop-service

server:
  port: 8080

app:
  notification:
    enabled: false

---
spring:
  config:
    activate:
      on-profile: dev

server:
  port: 8081

app:
  notification:
    enabled: true

---
spring:
  config:
    activate:
      on-profile: prod

logging:
  level:
    root: INFO
```

Document đầu áp dụng chung. Document thứ hai chỉ active khi profile `dev` khớp; document thứ ba dành cho `prod`.

### 13.1. Khi nào dùng multi-document?

Multi-document YAML tiện khi:

- Chỉ có vài giá trị khác nhau giữa những profile.
- Muốn đọc nhiều biến thể ngay trong cùng file.
- Cấu hình không quá dài và ranh giới từng document rõ ràng.

Nếu mỗi môi trường có nhiều cấu hình riêng, các file `application-dev.yml`, `application-prod.yml` thường dễ quản lý hơn.

### 13.2. Không phải YAML mới có document activation

Spring Boot hiện đại cũng hỗ trợ multi-document `.properties` theo cú pháp phân tách riêng. Tuy nhiên, cấu hình nhiều document có thể khó theo dõi khi file lớn; chọn file profile riêng sẽ đơn giản hơn trong nhiều dự án.

Không nên sao chép nguyên dòng phân tách `---` của YAML vào `.properties` và mặc định nó hoạt động giống nhau. Cú pháp marker của hai định dạng khác nhau.

## 14. Thứ tự ưu tiên giữa các nguồn cấu hình

Một property có thể xuất hiện nhiều nơi:

```text
application.yml
application-prod.yml
Biến môi trường
Java system properties
Command-line arguments
```

Spring Boot kết hợp các `PropertySource` theo một **thứ tự ưu tiên**. Nguồn có độ ưu tiên cao hơn sẽ quyết định giá trị được dùng nếu cùng một key xuất hiện ở nhiều nguồn.

Ví dụ:

**`application.properties`:**

```properties
server.port=8080
```

**Biến môi trường:**

```text
SERVER_PORT=8082
```

**Command line:**

```bash
java -jar shop-service.jar --server.port=9090
```

Trong thiết lập mặc định của Spring Boot, command-line property thường ưu tiên hơn giá trị từ biến môi trường và file cấu hình, nên server sẽ cố dùng cổng 9090.

### 14.1. Thứ tự tổng quát thường gặp

Ở mức khái niệm, từ những nguồn phổ biến có độ ưu tiên thấp đến cao:

```text
Default properties
       |
       v
Config Data: application.*, profile files
       |
       v
Một số nguồn hệ điều hành / Java system properties
       |
       v
Command-line arguments
```

Danh sách đầy đủ có thêm test properties, JSON application properties, `RandomValuePropertySource` và những nguồn khác. Một số nguồn có thứ tự riêng rất cụ thể trong Spring Boot; khi có lỗi precedence hãy tham khảo thứ tự property source của phiên bản đang chạy, thay vì xem sơ đồ rút gọn là đặc tả đầy đủ.

### 14.2. Profile-specific files có thể ghi đè file chung

Ví dụ:

```properties
# application.properties
app.feature.enabled=false
```

```properties
# application-dev.properties
app.feature.enabled=true
```

Nếu profile `dev` active và không có nguồn ưu tiên cao hơn ghi đè, giá trị được sử dụng là `true`.

### 14.3. Nếu cùng vị trí có cả `.properties` và YAML?

Spring Boot có quy tắc ưu tiên khi cả `application.properties` và file YAML cùng tên logic nằm tại **cùng một vị trí cấu hình**: `.properties` có độ ưu tiên cao hơn YAML trong trường hợp đó.

Ví dụ:

```text
src/main/resources/
├── application.properties  # app.mode=SAFE
└── application.yml         # app.mode: FAST
```

Không nên dựa vào việc trộn hai file này để quản lý hai phiên bản cấu hình. Hãy chọn một định dạng chủ đạo và chuyển các key trùng nhau vào cùng một nơi để tránh khó tìm nguồn của giá trị thực tế.

### 14.4. Cách kiểm tra giá trị thực tế

Bạn có thể đọc `Environment`:

```java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationReporter {

    private final Environment environment;

    public ConfigurationReporter(Environment environment) {
        this.environment = environment;
    }

    public int configuredPort() {
        return environment.getProperty(
                "server.port",
                Integer.class,
                8080
        );
    }
}
```

Đoạn code trả về giá trị cấu hình được resolve theo các property sources. Nó không chứng minh cổng HTTP đã được bind thành công và server đang lắng nghe: để xác nhận điều đó, cần xem log web server hoặc gửi HTTP request thực tế.

## 15. Property placeholder và default value

Spring Boot hỗ trợ placeholder tham chiếu tới property khác:

**Properties:**

```properties
app.base-url=https://example.com
app.callback-url=${app.base-url}/callback
```

**YAML:**

```yaml
app:
  base-url: https://example.com
  callback-url: "${app.base-url}/callback"
```

Sau khi resolve, `app.callback-url` sử dụng giá trị của `app.base-url`.

### 15.1. Giá trị fallback

```properties
app.greeting=${GREETING_TEXT:Hello}
```

Tương đương:

```yaml
app:
  greeting: "${GREETING_TEXT:Hello}"
```

Nếu biến/property `GREETING_TEXT` có sẵn, placeholder dùng giá trị đó. Nếu không, nó dùng `Hello` theo cú pháp fallback.

### 15.2. Secret từ môi trường triển khai

Không nên commit mật khẩu trực tiếp:

```properties
# Tránh lưu mật khẩu production vào Git
spring.datasource.password=production-secret-value
```

Thay vào đó:

```properties
spring.datasource.password=${DB_PASSWORD}
```

Hoặc:

```yaml
spring:
  datasource:
    password: "${DB_PASSWORD}"
```

Biến `DB_PASSWORD` được cung cấp bởi môi trường triển khai hoặc hệ thống quản lý secret. Nếu thiếu mà không có giá trị fallback, startup có thể báo lỗi khi property cần thiết được resolve/bind; đây thường là hành vi tốt cho một secret bắt buộc.

**Đừng đưa secret vào log, endpoint chẩn đoán hoặc ví dụ kết nối thực tế.** Việc sử dụng placeholder không tự bảo vệ secret nếu mã ứng dụng cố tình in giá trị đó.

## 16. `spring.config.import` và cấu hình ngoài artifact

Đôi khi bạn muốn cấu hình local hoặc cấu hình chung được tách ra khỏi `application.yml`.

Spring Boot hỗ trợ `spring.config.import` để nhập một nguồn Config Data khác.

Ví dụ:

```properties
spring.config.import=optional:file:./config/local.properties
```

Hoặc YAML:

```yaml
spring:
  config:
    import: "optional:file:./config/local.yml"
```

`optional:` cho biết việc thiếu file có thể được chấp nhận. Nếu bỏ `optional:` và nguồn không tồn tại, Spring Boot có thể thất bại khi khởi động với lỗi liên quan đến Config Data location.

### 16.1. Khi nào dùng import?

Các trường hợp thường gặp:

- Tách cấu hình máy local khỏi file commit vào Git.
- Nhập một file cấu hình vận hành bên ngoài JAR.
- Tổ chức cấu hình cho module hoặc môi trường theo hợp đồng rõ ràng.
- Đọc dữ liệu từ nguồn Config Data được framework hỗ trợ.

`spring.config.import` là một cơ chế cấu hình startup. Không nên hiểu nó như một cách runtime tự theo dõi file và cập nhật bean ngay khi file bị sửa.

### 16.2. Phân biệt `spring.config.import`, `location` và `additional-location`

| Thuộc tính | Ý nghĩa khái quát |
| --- | --- |
| `spring.config.import` | Nhập một nguồn Config Data từ cấu hình đang được xử lý |
| `spring.config.location` | Chỉ định các vị trí cấu hình cần xét, có thể thay thế những vị trí mặc định |
| `spring.config.additional-location` | Bổ sung vị trí vào danh sách tìm kiếm mặc định |
| `spring.config.name` | Thay tên logic mặc định `application` |

Những thuộc tính điều khiển việc **tìm file cấu hình** thường phải được cung cấp đủ sớm, như biến môi trường, Java system property hoặc command-line argument. Nếu đặt chúng trong một file chỉ được tìm thấy sau khi quá trình tìm kiếm đã xảy ra, có thể không đạt mục đích.

### 16.3. Khi cần cấu hình ngoài JAR

Một cách đơn giản:

```text
deploy/
├── shop-service.jar
└── config/
    └── application-prod.yml
```

Khi chạy tại thư mục phù hợp và kích hoạt profile `prod`, Spring Boot có thể tìm cấu hình bên ngoài theo các default location được hỗ trợ. Nếu vị trí khác thông thường, truyền `spring.config.additional-location` hoặc `spring.config.import` theo thiết kế của ứng dụng.

## 17. Các lỗi thường gặp của YAML

YAML gọn khi cấu trúc lồng nhau, nhưng dễ gặp những lỗi khó thấy.

### 17.1. Sai indentation

Sai:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
   username: shop_user
```

`username` không cùng mức indentation với `url`, có thể gây YAML parse error.

Đúng:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: shop_user
```

### 17.2. Dùng tab

YAML sử dụng khoảng trắng để thể hiện thụt dòng. Tab trong indentation có thể khiến parser báo lỗi.

Nên cấu hình editor dùng spaces và bật hiển thị whitespace nếu thường xuyên chỉnh YAML.

### 17.3. Trùng key

Ví dụ:

```yaml
server:
  port: 8080

server:
  port: 8081
```

Key `server` bị khai báo lặp trong cùng mapping. Tùy parser và cấu hình, trùng key có thể bị từ chối hoặc dẫn đến giá trị ngoài mong đợi.

Trong Spring Boot, tốt nhất **không tạo trùng key trong cùng YAML document**. Nếu cần override theo môi trường, dùng profile-specific documents/files.

### 17.4. Biểu diễn sai kiểu

Ví dụ mã đối tác:

```yaml
app:
  partner-code: 0007
```

Nếu cần giữ `"0007"` đúng như text, nên viết:

```yaml
app:
  partner-code: "0007"
```

Tương tự, một giá trị trông như Boolean hoặc null nhưng có nghĩa là nhãn chuỗi cũng nên được quote.

### 17.5. Chuỗi chứa dấu `:` và `#`

Để giảm nhầm lẫn parser:

```yaml
app:
  message: "Status: ready"
  display-label: "Plan #1"
```

Chuỗi được quote thích hợp hơn khi chứa ký tự có ý nghĩa cú pháp.

### 17.6. Nhầm YAML list với map

List:

```yaml
app:
  servers:
    - host: api-1.example.com
      port: 8080
    - host: api-2.example.com
      port: 8080
```

Map:

```yaml
app:
  servers:
    primary:
      host: api-1.example.com
      port: 8080
    fallback:
      host: api-2.example.com
      port: 8080
```

List phù hợp khi có thứ tự và nhiều phần tử cùng vai trò; map phù hợp khi cần truy cập bằng key như `primary`, `fallback`.

## 18. Các lỗi thường gặp của `.properties`

### 18.1. Lặp key

```properties
server.port=8080
server.port=8081
```

Khi hai key giống nhau xuất hiện trong cùng một file, một giá trị có thể bị thay thế trong quá trình đọc. Thay vì dựa vào quy tắc ghi đè trong file, hãy giữ **một key duy nhất** hoặc chuyển cấu hình biến thể vào profile.

### 18.2. Hiểu sai dấu ngoặc kép

Không nên viết:

```properties
app.title="My Shop"
```

nếu kỳ vọng Java properties tự loại dấu ngoặc kép. Dùng:

```properties
app.title=My Shop
```

YAML có quy tắc quote riêng; không sao chép nguyên cách biểu diễn chuỗi giữa hai định dạng mà không kiểm tra.

### 18.3. Ký tự escape

Java `.properties` có quy tắc escape dấu gạch chéo ngược, khoảng trắng và một số ký tự. Ví dụ đường dẫn Windows:

```properties
app.storage.directory=C:\\data\\shop
```

Trong YAML, nếu dùng single-quoted string:

```yaml
app:
  storage:
    directory: 'C:\data\shop'
```

Single quotes của YAML không diễn giải backslash như escape theo cách double-quoted YAML làm, nên thường dễ dùng cho đường dẫn Windows. Nếu sử dụng double quotes, phải xử lý các escape theo YAML.

### 18.4. Danh sách dài khó đọc

Khi `.properties` có hàng chục key với chỉ số như `[0]`, `[1]`, `[2]`, cấu hình vẫn hợp lệ nhưng dễ khó sửa và khó review. Đây là một lý do thực tế để cân nhắc YAML cho danh sách object nhiều cấp.

## 19. Cấu hình logging trong hai định dạng

**Properties:**

```properties
logging.level.root=INFO
logging.level.com.example.shop=DEBUG
logging.file.name=logs/shop-service.log
```

**YAML:**

```yaml
logging:
  level:
    root: INFO
    com.example.shop: DEBUG
  file:
    name: logs/shop-service.log
```

Cả hai đều cung cấp các property mà Spring Boot logging system có thể đọc.

### 19.1. Một lưu ý riêng với YAML và logging

Log levels cấu hình theo package name, ví dụ `com.example.shop`, không phải một class Java cụ thể. YAML cho phép giữ `com.example.shop` như một key đơn trong mapping dưới `logging.level`, nên bạn thường không cần tách tên package thành nhiều cấp YAML.

### 19.2. Không ghi thông tin nhạy cảm vào log

Khi chẩn đoán cấu hình, bạn có thể muốn in toàn bộ `Environment` hoặc `@ConfigurationProperties`. Nhưng những object đó có thể chứa password, token hoặc endpoint nội bộ.

Nên dùng logging có chọn lọc và cơ chế masking của hệ thống quan sát thay vì in mọi property value.

## 20. Cấu hình datasource và môi trường chạy

Ví dụ `application.properties`:

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/shop
spring.datasource.username=shop_user
spring.datasource.password=${DB_PASSWORD}
spring.datasource.hikari.maximum-pool-size=10
```

YAML tương đương:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: shop_user
    password: "${DB_PASSWORD}"
    hikari:
      maximum-pool-size: 10
```

Đây là cấu hình ví dụ cho ứng dụng có JDBC driver và dependency datasource phù hợp. **Không phải cứ thêm property thì Spring Boot sẽ tự cung cấp driver hoặc tạo database**.

Nếu ứng dụng thiếu JDBC driver, server database không chạy hoặc thông tin xác thực sai, startup hoặc thao tác truy cập database vẫn có thể thất bại.

### 20.1. Tách môi trường

Ví dụ:

```text
application.yml
application-dev.yml
application-prod.yml
```

File chung chứa cấu hình không nhạy cảm và giống nhau giữa các môi trường. File profile chỉ chứa những giá trị khác biệt. Secret nên được cung cấp từ hệ thống quản lý cấu hình/secret của môi trường triển khai.

Không nên copy nguyên `application-prod.yml` chứa mật khẩu thật vào repository để phục vụ chạy local.

## 21. Nên chọn `application.properties` hay `application.yml`?

Không có một định dạng luôn đúng cho mọi dự án. Có thể cân nhắc theo các tiêu chí sau.

### 21.1. Chọn `.properties` khi

- Cấu hình ít, phần lớn là scalar key–value.
- Nhóm quen với tên property đầy đủ dạng `spring.datasource.url`.
- Cần sửa nhanh một key hoặc so sánh trực tiếp với tài liệu của framework.
- Muốn tránh rủi ro indentation.
- Dự án đang dùng `.properties` ổn định và không có lý do chuyển đổi.

Ví dụ:

```properties
spring.application.name=order-service
server.port=8080
management.endpoints.web.exposure.include=health,info
```

### 21.2. Chọn YAML khi

- Cấu hình phân cấp nhiều mức.
- Có nhiều list hoặc list of objects.
- Muốn gom cấu hình của từng module vào một cấu trúc dễ nhìn.
- Nhóm có công cụ editor/lint YAML tốt và đã quen indentation.
- Sử dụng profile documents hoặc cấu hình phức tạp cần biểu diễn rõ.

Ví dụ:

```yaml
app:
  payment:
    retries:
      enabled: true
      max-attempts: 3
      backoff: 500ms
    providers:
      - name: bank
        timeout: 3s
      - name: wallet
        timeout: 2s
```

### 21.3. Bảng quyết định

| Đặc điểm dự án | Định dạng dễ phù hợp hơn |
| --- | --- |
| 10–20 scalar properties | `.properties` |
| Nhiều key cùng prefix | YAML |
| Nhiều list of objects | YAML |
| Muốn giảm indentation errors | `.properties` |
| Nhóm đã thống nhất một định dạng | Giữ định dạng hiện tại |
| Cần triển khai qua environment variables | Cả hai đều phù hợp |
| Cần `@ConfigurationProperties` và validation | Cả hai đều phù hợp |
| Cần profile-specific files | Cả hai đều phù hợp |

**Tính nhất quán trong cùng codebase thường quan trọng hơn lợi ích nhỏ của việc đổi định dạng.** Khi hai định dạng đều diễn đạt được cấu hình, chọn định dạng mà nhóm có thể review và debug dễ nhất.

## 22. Có nên chuyển đổi giữa hai định dạng?

Bạn có thể chuyển từ `.properties` sang YAML khi cấu hình lớn dần. Nhưng chuyển đổi không chỉ đơn giản là thay extension.

Ví dụ ban đầu:

```properties
app.queue.max-attempts=5
app.queue.retry-delay=2s
app.queue.consumers[0].name=orders
app.queue.consumers[0].enabled=true
app.queue.consumers[1].name=payments
app.queue.consumers[1].enabled=false
```

Sau chuyển đổi:

```yaml
app:
  queue:
    max-attempts: 5
    retry-delay: 2s
    consumers:
      - name: orders
        enabled: true
      - name: payments
        enabled: false
```

Khi chuyển đổi, cần giữ **ý nghĩa cấu hình**:

1. Tên property sau khi flatten vẫn tương ứng.
2. Giá trị string đặc biệt như `"0012"` không bị đổi kiểu.
3. List giữ đúng thứ tự và số phần tử.
4. Placeholder `${...}` vẫn resolve đúng.
5. Profile activation vẫn áp dụng đúng môi trường.
6. Không còn file cũ chứa key trùng vô tình ghi đè file mới.

Đây là những điều cần kiểm chứng trong một bước chuyển đổi cấu hình thực tế. Việc kiểm thử chuyển đổi không làm thay đổi bản chất: Spring Boot nhận property values từ `Environment`.

## 23. Kiểm tra cấu hình đã nạp đúng

### 23.1. Kiểm tra bằng `Environment`

Ví dụ một startup reporter:

```java
package com.example.shop;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class SettingsReporter implements ApplicationRunner {

    private final Environment environment;

    public SettingsReporter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Application: " +
                environment.getProperty("spring.application.name")
        );
        System.out.println(
                "Catalog size: " +
                environment.getProperty("app.catalog.page-size")
        );
    }
}
```

Đoạn code dùng để quan sát những property không nhạy cảm sau khi context đã refresh. Không in password hoặc token.

### 23.2. Kiểm tra bằng `@ConfigurationProperties`

Ví dụ với `PartnerProperties`, có thể viết test:

```java
@SpringBootTest(properties = {
    "app.partner.base-url=https://test.example.com",
    "app.partner.timeout=3s",
    "app.partner.max-attempts=2",
    "app.partner.enabled=true"
})
class PartnerPropertiesTest {

    @Autowired
    PartnerProperties properties;

    @Test
    void bindsPartnerProperties() {
        assertThat(properties.baseUrl())
                .isEqualTo(URI.create("https://test.example.com"));
        assertThat(properties.timeout())
                .isEqualTo(Duration.ofSeconds(3));
        assertThat(properties.maxAttempts()).isEqualTo(2);
    }
}
```

Ví dụ giả định dự án có Spring Boot Test, JUnit 5, AssertJ và đã đăng ký `PartnerProperties` trong test context. Test này kiểm tra binding từ property values sang Java model, không phụ thuộc bản gốc giá trị đến từ `.properties` hay YAML.

### 23.3. Dùng Actuator trong môi trường phù hợp

Spring Boot Actuator có endpoint `/actuator/env` và `/actuator/configprops` khi được thêm dependency, bật và expose phù hợp.

Chúng hữu ích để kiểm tra:

- Property source nào được nạp.
- Property nào đã được bind vào configuration properties bean.
- Vì sao một giá trị có thể khác với giá trị trong file dự kiến.

Những endpoint này có thể chứa metadata nhạy cảm. Cần cấu hình bảo mật và cơ chế che/masking dữ liệu phù hợp; không tự expose chúng ra Internet công khai để debug.

### 23.4. Đọc thông báo lỗi binding

Nếu Spring Boot không bind được:

```properties
app.partner.max-attempts=abc
```

vào `int maxAttempts`, startup có thể báo lỗi binding với tên property, value, kiểu đích và vị trí nguồn cấu hình.

Khi gặp lỗi, hãy kiểm tra **key, value, profile, kiểu Java và vị trí file đã nạp**, thay vì sửa Java model vội vàng.

## 24. Ví dụ thực hành đầy đủ: một ứng dụng, hai định dạng

Giả sử ứng dụng cần cấu hình vận hành một API đối tác.

### 24.1. Cấu hình ở dạng properties

```properties
spring.application.name=partner-gateway
server.port=8081

app.partner.enabled=true
app.partner.base-url=https://partner.example.com
app.partner.timeout=5s
app.partner.max-attempts=3

logging.level.com.example.gateway=INFO
```

### 24.2. Cấu hình tương đương dạng YAML

```yaml
spring:
  application:
    name: partner-gateway

server:
  port: 8081

app:
  partner:
    enabled: true
    base-url: https://partner.example.com
    timeout: 5s
    max-attempts: 3

logging:
  level:
    com.example.gateway: INFO
```

### 24.3. Bind vào Java

```java
package com.example.gateway.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        boolean enabled,
        URI baseUrl,
        Duration timeout,
        int maxAttempts
) {
}
```

Lớp khởi động:

```java
package com.example.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class GatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
```

Service:

```java
package com.example.gateway.service;

import com.example.gateway.config.PartnerProperties;
import org.springframework.stereotype.Service;

@Service
public class PartnerGateway {

    private final PartnerProperties properties;

    public PartnerGateway(PartnerProperties properties) {
        this.properties = properties;
    }

    public boolean isEnabled() {
        return properties.enabled();
    }

    public String targetHost() {
        return properties.baseUrl().getHost();
    }
}
```

Nếu dùng đúng một trong hai file và cùng các nguồn cấu hình khác, service nhận những giá trị tương đương. Đây là minh họa quan trọng rằng **định dạng file là cách biểu diễn đầu vào; model binding và logic Java không cần thay theo định dạng**.

### 24.4. Thử ghi đè bằng command line

Giả sử file đặt:

```properties
server.port=8081
```

Chạy:

```bash
java -jar partner-gateway.jar --server.port=9090
```

Nếu không có cấu hình ưu tiên cao hơn hoặc ràng buộc khác, Spring Boot sẽ dùng cổng 9090 cho web server. Cùng một nguyên tắc áp dụng khi nguồn file ban đầu là YAML.

## 25. Bài tập thực hành

### Bài 1 — Viết hai file tương đương

Tạo cấu hình cho một ứng dụng đặt vé gồm:

- `spring.application.name=booking-service`.
- `server.port=8085`.
- `app.booking.max-seats=8`.
- `app.booking.confirmation-timeout=30s`.
- `app.booking.enabled=true`.

Viết một bản bằng `.properties`, một bản bằng YAML và giải thích đường dẫn key tương ứng. Chỉ giữ một bản active khi chạy để tránh key trùng.

### Bài 2 — Danh sách và map

Cấu hình ba payment providers có `name`, `base-url` và `timeout`. Viết bằng properties với `[0]`, `[1]`, `[2]`, sau đó viết lại dưới dạng YAML list.

Tiếp theo, tạo map `app.currency.decimals` với các key `VND`, `USD`, `JPY`. Đề xuất Java model thích hợp cho từng cấu trúc.

### Bài 3 — Binding kiểu dữ liệu

Tạo record:

```java
@ConfigurationProperties(prefix = "app.upload")
public record UploadProperties(
        boolean enabled,
        DataSize maxFileSize,
        Duration timeout
) {
}
```

Cấu hình `max-file-size=20MB` và `timeout=45s`. Inject record vào một service và in những giá trị không nhạy cảm.

Giải thích cách Spring Boot chuyển text thành `DataSize` và `Duration`.

### Bài 4 — Profile dev và prod

Tạo `application.yml`, `application-dev.yml`, `application-prod.yml`.

- Cấu hình chung: application name và cờ feature mặc định.
- Dev: port 8081, log DEBUG cho package ứng dụng.
- Prod: port 8080, log INFO.

Chạy hai lần với `--spring.profiles.active=dev` và `--spring.profiles.active=prod`. Xác nhận giá trị được nạp.

### Bài 5 — YAML multi-document

Chuyển Bài 4 thành một file `application.yml` có ba documents: chung, dev và prod. Dùng `spring.config.activate.on-profile`.

Giải thích vì sao không đặt `spring.profiles.active` trong document đã được kích hoạt bởi `on-profile`.

### Bài 6 — Tìm lỗi YAML

Cho cấu hình:

```yaml
app:
  email:
    enabled: true
   retry:
      max-attempts: 3
```

Xác định lỗi indentation, sửa và cho biết các key được tạo sau khi flatten.

### Bài 7 — Tìm nguồn override

Giả sử:

```properties
# application.properties
server.port=8080
```

```properties
# application-dev.properties
server.port=8081
```

Môi trường chạy có `SERVER_PORT=8082`, còn command line có `--server.port=9090`.

Dự đoán cổng được dùng khi profile dev active theo thiết lập mặc định, rồi kiểm chứng qua log và request HTTP.

### Bài 8 — Thay placeholder bằng môi trường

Đặt:

```properties
app.partner.api-key=${PARTNER_API_KEY}
```

Truyền secret từ biến môi trường của máy local hoặc secret manager dùng trong bài tập. Xác nhận ứng dụng có thể bind property mà không in secret ra console.

Giải thích tại sao không nên commit API key thật vào repository.

### Bài 9 — Đổi định dạng có kiểm soát

Chọn một file `.properties` đang có list/map, chuyển hoàn toàn sang YAML. Xóa hoặc di chuyển file cũ khỏi các vị trí Spring Boot tự nạp, sau đó xác nhận:

- Những scalar property chính giữ giá trị.
- List còn đúng số phần tử và thứ tự.
- `@ConfigurationProperties` bind thành công.
- Profile có cùng ý nghĩa như trước.
- Không còn property trùng ở hai file cùng vị trí.

### Bài 10 — Chọn định dạng cho một nhóm

Một nhóm có 15 property đơn giản, còn nhóm khác có hàng chục integration objects và nhiều profile. Đề xuất định dạng cho mỗi nhóm, giải thích tiêu chí và đưa ra quy ước đặt tên/indentation để cả nhóm có thể duy trì lâu dài.

## 26. Ghi nhớ

`application.properties` và `application.yml` đều là **cách khai báo configuration properties cho Spring Boot**. `.properties` đơn giản, phẳng và dễ tìm key theo tên đầy đủ. YAML thể hiện cấu trúc lồng nhau, list và map trực quan hơn nhưng yêu cầu indentation và quoting cẩn thận.

Spring Boot nạp cấu hình vào `Environment`, kết hợp các property sources theo thứ tự ưu tiên và bind giá trị vào Java thông qua `@ConfigurationProperties` hoặc `@Value`. Cả hai định dạng hỗ trợ profile-specific configuration, property placeholders và cấu hình được ghi đè từ môi trường triển khai.

Khi chọn định dạng, hãy ưu tiên **tính nhất quán, khả năng review và độ dễ chẩn đoán**. Sử dụng một định dạng chính trong cùng dự án, giữ key canonical dạng kebab-case, dùng `@ConfigurationProperties` cho cấu hình có cấu trúc, không lưu secret trong source code và kiểm chứng giá trị thực tế sau khi Spring Boot khởi động.
