# Đăng ký bằng @ConfigurationPropertiesScan

Trong Spring Boot, annotation **`@ConfigurationProperties`** mô tả cách ánh xạ một nhóm key cấu hình thành đối tượng Java có kiểu, còn **`@ConfigurationPropertiesScan`** giúp Spring Boot **tìm và đăng ký các lớp cấu hình đó thành bean**. Hai annotation phục vụ hai bước khác nhau: *định nghĩa hợp đồng dữ liệu* và *đưa hợp đồng đó vào Spring ApplicationContext*.

Một lỗi phổ biến là tạo record có `@ConfigurationProperties(prefix = "app.client")`, viết `application.yml` đầy đủ, nhưng khi inject record vào service lại gặp lỗi **không tìm thấy bean**. Nguyên nhân thường không nằm ở cú pháp YAML, mà ở việc chưa bật scan, scan sai package hoặc dùng nhầm cơ chế đăng ký.

Bài này thực hành từ một ứng dụng nhỏ, giải thích đường đi từ `application.yml` đến bean, phạm vi quét package, constructor binding, cấu hình nhiều module, validation, so sánh với `@EnableConfigurationProperties` và cách xử lý những lỗi thường gặp. Ví dụ chủ yếu theo Spring Boot 3.x, sử dụng Java 17 trở lên.

## 1. Bức tranh tổng thể: định nghĩa khác đăng ký

~~~text
application.yml / application.properties
      |
      | app.client.base-url=https://api.example.test
      | app.client.connect-timeout=750ms
      | app.client.max-retries=3
      v
Spring Boot Environment
      |
      | các PropertySource và thứ tự ưu tiên
      v
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(...)
      ^
      |
@ConfigurationPropertiesScan
      |
      | tìm lớp @ConfigurationProperties trong package cần quét
      | đăng ký loại bean cấu hình với ApplicationContext
      v
Spring Boot Binder
      |
      | kết hợp key theo prefix
      | chuyển chuỗi sang URI, Duration, int...
      | áp dụng validation nếu cấu hình
      v
ClientProperties bean
      |
      v
RemoteClient constructor injection
~~~

Hãy tách ba trách nhiệm:

1. **Nguồn cấu hình** cung cấp key/value sau khi Spring Boot hợp nhất file, profile, biến môi trường và tham số khởi động.
2. **`@ConfigurationProperties`** chỉ ra prefix và mô hình Java đích.
3. **`@ConfigurationPropertiesScan`** tìm những mô hình được đánh dấu `@ConfigurationProperties` trong package cho phép, để framework đăng ký và bind chúng.

Chỉ có một file YAML không làm xuất hiện bean `ClientProperties`. Tương tự, chỉ có annotation `@ConfigurationProperties` trên record cũng không có nghĩa record chắc chắn đã được Spring đăng ký.

## 2. Ví dụ tối thiểu có thể áp dụng

Giả sử tạo ứng dụng Spring Boot với cấu trúc:

~~~text
order-service/
  build.gradle
  src/
    main/
      java/
        com/example/orders/
          OrderApplication.java
          config/
            ClientProperties.java
          service/
            RemoteClient.java
      resources/
        application.yml
~~~

Tệp `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: order-service

app:
  client:
    base-url: https://api.example.test
    connect-timeout: 750ms
    max-retries: 3
    enabled: true
~~~

Record chứa dữ liệu cấu hình:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries,
    boolean enabled
) {}
~~~

Annotation `@ConfigurationProperties` thông báo rằng các thành phần của record cần nhận giá trị có prefix `app.client`. Ví dụ `base-url` ánh xạ sang `baseUrl`, còn `connect-timeout` thành `connectTimeout`.

Bây giờ đăng ký quét tại lớp khởi động:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Bean nghiệp vụ nhận cấu hình:

~~~java
package com.example.orders.service;

import com.example.orders.config.ClientProperties;
import org.springframework.stereotype.Service;

@Service
public class RemoteClient {
    private final ClientProperties properties;

    public RemoteClient(ClientProperties properties) {
        this.properties = properties;
    }

    public String endpointDescription() {
        return properties.baseUrl()
            + " (timeout=" + properties.connectTimeout()
            + ", retries=" + properties.maxRetries() + ")";
    }
}
~~~

Khi Spring Boot khởi động trong cấu trúc package này:

- `OrderApplication` ở `com.example.orders` là điểm bắt đầu quét.
- `@ConfigurationPropertiesScan` tìm `ClientProperties` trong package con `com.example.orders.config`.
- Framework đăng ký bean cấu hình và Binder chuyển value từ Environment sang record.
- Spring inject bean `ClientProperties` vào constructor của `RemoteClient`.

Đây là sự kết hợp cốt lõi: **`@ConfigurationProperties` trên kiểu dữ liệu, `@ConfigurationPropertiesScan` trên một lớp cấu hình hoặc lớp khởi động nằm ở package thích hợp.**

## 3. Vì sao phải có @ConfigurationPropertiesScan?

Trong một ứng dụng Spring, một class Java không tự trở thành bean chỉ vì nó tồn tại trên classpath. Spring cần một cơ chế đăng ký: component scan, `@Bean`, import, `@EnableConfigurationProperties` hoặc cơ chế khác.

Lớp:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    String baseUrl,
    int maxRetries
) {}
~~~

chỉ mô tả binding. Nếu không có bean definition tương ứng, Spring không có đối tượng nào để inject:

~~~java
public RemoteClient(ClientProperties properties) {
    this.properties = properties;
}
~~~

Một thông báo tương ứng có thể có dạng:

~~~text
Parameter 0 of constructor in com.example.orders.service.RemoteClient
required a bean of type 'com.example.orders.config.ClientProperties'
that could not be found.
~~~

Thêm `@ConfigurationPropertiesScan` với phạm vi đúng là một cách giải quyết được thiết kế cho việc này. Annotation thực hiện **scan riêng dành cho configuration properties classes**, chứ không phải “quét mọi class và biến chúng thành bean”.

### Khác với @SpringBootApplication như thế nào?

`@SpringBootApplication` đã bao gồm component scanning theo phạm vi package mặc định, nhưng component scan thường nhận những loại bean được đánh dấu như `@Component`, `@Service`, `@Repository` hoặc `@Controller`.

`@ConfigurationProperties` **không đồng nghĩa `@Component`**. Vì vậy, đừng suy luận rằng `@SpringBootApplication` tự động phát hiện mọi record `@ConfigurationProperties` theo cách component scan thông thường.

Khi thêm:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

bạn đang bổ sung bước quét các lớp cấu hình có kiểu vào cơ chế khởi tạo ứng dụng.

## 4. Quy tắc phạm vi package của @ConfigurationPropertiesScan

Khi không truyền thuộc tính nào:

~~~java
@ConfigurationPropertiesScan
~~~

Spring Boot dùng **package chứa lớp được annotate** làm gốc quét. Nó xét những class phù hợp trong package gốc và các package con.

Ví dụ:

~~~text
com.example.orders
  ├── OrderApplication                  @ConfigurationPropertiesScan
  ├── config
  │    ├── ClientProperties             @ConfigurationProperties
  │    └── CacheProperties              @ConfigurationProperties
  └── service
       └── RemoteClient                 @Service
~~~

Nếu annotation nằm trên `com.example.orders.OrderApplication`, lớp trong `com.example.orders.config` nằm trong phạm vi. Hai kiểu `ClientProperties` và `CacheProperties` có thể được phát hiện.

Ngược lại:

~~~text
com.example
  ├── orders
  │    └── OrderApplication             @ConfigurationPropertiesScan
  └── shared
       └── SecurityProperties           @ConfigurationProperties
~~~

`com.example.shared.SecurityProperties` **không nằm trong package con của `com.example.orders`**, nên không được quét chỉ bởi annotation mặc định trên `OrderApplication`.

### Cách giải quyết với basePackages

Khi cần chỉ định rõ các package, dùng thuộc tính `basePackages`:

~~~java
package com.example.orders;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan(basePackages = {
    "com.example.orders.config",
    "com.example.shared.config"
})
public class OrderApplication {}
~~~

Cách này hữu ích khi cấu hình được tách vào các module hoặc package nằm ngoài vùng quét mặc định. Tuy nhiên chuỗi package có thể bị lỗi nếu refactor đổi tên package mà không đổi annotation.

### Cách giải quyết với basePackageClasses

Một cách an toàn hơn khi có class mốc là `basePackageClasses`:

~~~java
package com.example.orders;

import com.example.orders.config.ClientProperties;
import com.example.shared.config.SecurityProperties;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan(basePackageClasses = {
    ClientProperties.class,
    SecurityProperties.class
})
public class OrderApplication {}
~~~

Spring Boot dùng **package của những class được chỉ định làm gốc quét**. Nó không đơn thuần chỉ đăng ký chính xác hai class nói trên: mọi loại `@ConfigurationProperties` phù hợp trong phạm vi các package đó cũng có thể được phát hiện.

Khi muốn quét chính xác một hoặc vài kiểu thay vì cả package, `@EnableConfigurationProperties(ClientProperties.class)` thường diễn đạt ý định rõ hơn.

### Package gốc nên đặt ở đâu?

Nếu phần lớn ứng dụng nằm trong `com.example.orders`, để main class và `@ConfigurationPropertiesScan` tại package này thường phù hợp. Không cần mở phạm vi quét tới toàn bộ `com.example` nếu project còn nhiều service và module không liên quan. Quét đúng phạm vi giúp tránh tạo bean cấu hình không được dự định sử dụng.

## 5. Phân biệt @ConfigurationPropertiesScan và @ComponentScan

Hai annotation mang tên “scan”, nhưng mục tiêu là khác nhau.

| Vấn đề | `@ComponentScan` | `@ConfigurationPropertiesScan` |
| --- | --- | --- |
| Mục đích | Phát hiện Spring component theo stereotype annotation | Phát hiện lớp `@ConfigurationProperties` phù hợp |
| Ví dụ class | `@Service`, `@Component` | `@ConfigurationProperties(prefix = "...")` |
| Vai trò bean | Service, repository, controller, configuration và các component | Đối tượng giữ cấu hình đã bind |
| Có nhất thiết tạo bean @ConfigurationProperties? | Không, nếu chỉ dùng annotation `@ConfigurationProperties` mà không có stereotype | Có, với các class phù hợp trong phạm vi quét |
| Có quét mọi @Service không? | Có thể, tùy phạm vi | Không |
| Constructor binding cho record bất biến | Không phải cơ chế mặc định dành cho kiểu cấu hình constructor-bound | Là một cơ chế đăng ký phù hợp |

Điểm dễ gây nhầm: tài liệu của Spring Boot nêu rằng **những lớp được đánh dấu `@Component` hoặc meta-annotated `@Component` không được chọn bởi `@ConfigurationPropertiesScan`**. Lớp dạng này có thể được đăng ký bằng component scan, nhưng đó là **một con đường đăng ký khác**.

Ví dụ:

~~~java
@Component
@ConfigurationProperties(prefix = "app.client")
public class MutableClientProperties {
    // Field + getter/setter...
}
~~~

Kiểu bean này có thể được component scan phát hiện rồi bind qua cơ chế hỗ trợ configuration properties thích hợp. Nhưng **không nên nói rằng `@ConfigurationPropertiesScan` tìm thấy nó**. Đặc biệt, constructor binding của `@ConfigurationProperties` không được dùng theo cùng cách cho bean do cơ chế tạo Spring bean thông thường như `@Component` hoặc `@Bean` tạo ra.

Với record bất biến, lựa chọn rõ ràng là:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(...) {}
~~~

và đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, **không thêm `@Component` chỉ để tránh lỗi không tìm thấy bean**.

## 6. Constructor binding khi dùng record hoặc lớp immutable

Spring Boot 3.x có khả năng bind configuration properties qua constructor cho đối tượng bất biến. Với record có một canonical constructor, ví dụ:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

khi lớp được đăng ký qua configuration properties scanning, Binder có thể lấy các property tương ứng rồi truyền vào constructor record.

Dữ liệu:

~~~properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=2s
app.client.max-retries=3
~~~

tạo record có ý nghĩa tương đương:

~~~java
new ClientProperties(
    URI.create("https://api.example.test"),
    Duration.ofSeconds(2),
    3
);
~~~

Đoạn `new ...` chỉ minh họa kết quả binding; trong ứng dụng thực tế, Spring Boot tạo đối tượng thông qua cơ chế Binder và inject bean đó cho consumer.

### Có phải luôn viết @ConstructorBinding?

Không. Trong Spring Boot 3.x, **một constructor có tham số thích hợp** thường được suy ra cho constructor binding; record với canonical constructor là trường hợp tiêu biểu. Với class có nhiều constructor hoặc cấu trúc phức tạp, có thể cần chỉ định constructor muốn dùng theo phiên bản Spring Boot thực tế.

Không sao chép đường dẫn import của `@ConstructorBinding` từ một phiên bản Spring Boot cũ sang phiên bản mới mà không kiểm tra phiên bản. Bài này dùng record đơn giản nên không cần thêm annotation đó.

### Vì sao @Component có thể gây vấn đề?

Spring Framework tạo bean `@Component` theo đường constructor injection cho dependency của nó. Trong khi đó constructor của `ClientProperties` chứa `URI`, `Duration` và `int` vốn là **dữ liệu cần Binder chuyển từ key/value** chứ không phải Spring bean cần inject.

Do đó đặt `@Component` lên record constructor-bound không phải cách thay thế tương đương cho configuration properties scan. Với typed configuration immutable, dùng dedicated registration mechanism để Spring Boot Binder chịu trách nhiệm khởi tạo.

## 7. Dùng JavaBean mutable khi cấu hình cần setter binding

Không phải configuration properties nào cũng phải là record. Một class có constructor mặc định, getter/setter vẫn có thể được Binder tạo và điền dữ liệu:

~~~java
package com.example.orders.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {
    private int concurrency = 4;
    private Duration pollInterval = Duration.ofSeconds(5);

    public int getConcurrency() {
        return concurrency;
    }

    public void setConcurrency(int concurrency) {
        this.concurrency = concurrency;
    }

    public Duration getPollInterval() {
        return pollInterval;
    }

    public void setPollInterval(Duration pollInterval) {
        this.pollInterval = pollInterval;
    }
}
~~~

Tệp cấu hình:

~~~yaml
app:
  worker:
    concurrency: 8
    poll-interval: 2s
~~~

Nếu `WorkerProperties` nằm trong phạm vi `@ConfigurationPropertiesScan`, nó được đăng ký và có thể được bind thành bean cấu hình. Các field có default phục vụ khi key không có trong nguồn hiệu lực.

Với record immutable, thiết kế default cần dựa vào constructor/binding phù hợp; không mặc định áp dụng cách field initializer của JavaBean lên record.

Một quyết định thiết kế:

- Dùng record nếu giá trị cấu hình nên cố định sau khi bind và muốn contract rõ ràng.
- Dùng JavaBean nếu cần kiểu setter binding, tương thích library cũ hoặc có yêu cầu đặc thù về mutable properties.
- Cả hai vẫn có thể được đăng ký qua `@ConfigurationPropertiesScan` nếu là loại `@ConfigurationProperties` phù hợp và nằm trong package được quét.

Không nhầm “mutable properties class” với “configuration tự cập nhật live”. Việc thay file YAML khi ứng dụng đang chạy không tự động khiến bean mutable được bind lại nếu không có cơ chế refresh/rebind riêng.

## 8. Mẫu dùng @ConfigurationPropertiesScan trong nhiều package

Một ứng dụng thực tế có nhiều nhóm cấu hình:

~~~text
com.example.orders
  ├── OrderApplication.java
  ├── config
  │    ├── ClientProperties.java
  │    ├── MailProperties.java
  │    └── CacheProperties.java
  ├── client
  │    └── RemoteOrderClient.java
  └── mail
       └── MailService.java
~~~

Các loại properties:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(URI baseUrl, Duration timeout) {}

@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(String host, int port) {}

@ConfigurationProperties(prefix = "app.cache")
public record CacheProperties(Duration ttl, int maximumSize) {}
~~~

Đây là ba ví dụ class/record riêng, đặt trong ba file Java theo quy tắc một public type/file khi triển khai.

Tại main class:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

Nếu main class ở `com.example.orders` và các kiểu properties nằm dưới `com.example.orders.config`, **một annotation scan đã đủ để phát hiện cả ba**. Không phải thêm `@Component` lên từng record.

### Tiêu chí tách properties class

Hãy tổ chức theo ranh giới chức năng: client, mail, cache, storage, export hoặc payment. Tránh tạo một class chứa hàng chục key không liên quan chỉ vì scanning có thể quét mọi thứ.

Consumer có thể inject đúng model:

~~~java
@Service
public class MailService {
    private final MailProperties mail;

    public MailService(MailProperties mail) {
        this.mail = mail;
    }
}
~~~

Cách này làm việc tái cấu trúc cấu hình và unit test đơn giản hơn so với rải `Environment.getProperty("app.mail.host")` ở nhiều vị trí.

## 9. So sánh với @EnableConfigurationProperties

Hai annotation đều có thể đưa `@ConfigurationProperties` vào ApplicationContext, nhưng khác cách chỉ định phạm vi.

### @ConfigurationPropertiesScan: tìm theo package

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

Phù hợp khi có **nhiều properties types** được tổ chức trong một hoặc một số package và muốn tự động phát hiện chúng.

### @EnableConfigurationProperties: đăng ký theo type

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
public class ClientConfiguration {}
~~~

Phù hợp khi muốn **nêu rõ chính xác kiểu properties cần đăng ký**, ví dụ một module auto-configuration muốn bật đúng `ClientProperties` hoặc một test chỉ cần một bean cụ thể.

Có thể đặt trực tiếp trên ứng dụng:

~~~java
@SpringBootApplication
@EnableConfigurationProperties({
    ClientProperties.class,
    MailProperties.class
})
public class OrderApplication {}
~~~

Cách này không yêu cầu các class được liệt kê nằm dưới package scan. Dĩ nhiên chúng phải có trên classpath.

| Câu hỏi | `@ConfigurationPropertiesScan` | `@EnableConfigurationProperties` |
| --- | --- | --- |
| Mô tả mục tiêu | Quét package tìm các loại properties | Đăng ký các loại properties cụ thể |
| Số lượng loại thường dùng | Thuận lợi khi có nhiều loại | Thuận lợi khi có ít loại biết trước |
| Phụ thuộc vị trí package | Có | Không bắt buộc quét package |
| Có cần liệt kê từng class? | Không | Có, khi khai báo danh sách type |
| Phù hợp ở main app | Có | Có |
| Phù hợp ở module cấu hình nhỏ | Có thể | Thường dễ kiểm soát nếu chỉ vài type |

**Không cần đăng ký cùng một class bằng cả hai cơ chế chỉ vì muốn chắc chắn.** Nếu một class xuất hiện qua nhiều con đường, bạn có thể gặp cấu hình khó đọc hoặc nhiều bean candidate tùy cách các cơ chế đăng ký được dùng. Hãy chọn mô hình đăng ký rõ ràng và nhất quán.

## 10. @Bean + @ConfigurationProperties: trường hợp cấu hình đối tượng bên thứ ba

`@ConfigurationPropertiesScan` dùng để tìm **lớp** được đánh dấu `@ConfigurationProperties`. Nhưng có khi bạn muốn bind key vào một đối tượng được tạo bởi một thư viện khác — một kiểu bạn không kiểm soát mã nguồn.

Trong trường hợp đó, `@ConfigurationProperties` có thể đặt trên **phương thức `@Bean`** để Spring bind các property phù hợp vào đối tượng bean sau khi phương thức tạo đối tượng.

Ví dụ một type mutable có setter, do thư viện nội bộ cung cấp:

~~~java
package com.example.orders.config;

import com.example.legacy.LegacyPoolSettings;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LegacyPoolConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "app.legacy-pool")
    LegacyPoolSettings legacyPoolSettings() {
        return new LegacyPoolSettings();
    }
}
~~~

Giả sử `LegacyPoolSettings` có getter/setter phù hợp, các key như `app.legacy-pool.maximum-size` có thể được bind vào bean.

Điểm quan trọng:

- Bean được đăng ký bởi **`@Bean`**, không phải do `@ConfigurationPropertiesScan` tìm class thứ ba.
- Cơ chế setter/property binding phụ thuộc khả năng của type đích.
- Khi dùng `@Bean` để tạo một type thư viện, constructor binding dành cho bean cấu hình immutable không hoạt động theo đúng đường đăng ký dedicated configuration properties.

Nếu bạn tự sở hữu type và muốn thiết kế immutable model, thường rõ ràng hơn khi định nghĩa record `@ConfigurationProperties` riêng rồi đăng ký bằng scan hoặc enable.

## 11. Spring Boot Binder xử lý tên và kiểu như thế nào?

Một trong những lợi ích chính của configuration properties là **relaxed binding**: tên key từ nguồn cấu hình có thể được ánh xạ theo quy tắc của Spring Boot sang tên thuộc tính Java.

Ví dụ:

~~~properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=1500ms
app.client.max-retries=4
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

Binder có thể chuyển các value:

| Key | Thành phần record | Kiểu Java | Kết quả |
| --- | --- | --- | --- |
| `app.client.base-url` | `baseUrl` | `URI` | URI của API |
| `app.client.connect-timeout` | `connectTimeout` | `Duration` | 1,5 giây |
| `app.client.max-retries` | `maxRetries` | `int` | 4 |

Tên key canonical nên ưu tiên dạng **lowercase kebab-case** trong file:

~~~properties
app.client.connect-timeout=1500ms
~~~

Trong môi trường triển khai, biến môi trường có thể dùng tên tương ứng với quy tắc chuyển đổi Spring Boot, ví dụ `APP_CLIENT_CONNECTTIMEOUT`. Binder đọc qua Environment và áp dụng relaxed binding thay vì yêu cầu mọi nguồn có đúng cùng kiểu tên chữ.

**Scanning không làm thay đổi thứ tự ưu tiên nguồn.** Nếu YAML đặt timeout 3 giây nhưng command-line có `--app.client.connect-timeout=500ms`, bean được bind theo giá trị hiệu lực của các nguồn cấu hình tại thời điểm binding thông thường, không ưu tiên YAML chỉ vì nó nằm trong project.

## 12. Nested properties, List và Map khi scanning

Scan chỉ quyết định **các root properties class nào được đăng ký thành bean**. Nó không yêu cầu từng nested type phải có `@ConfigurationProperties` riêng.

Ví dụ:

~~~yaml
app:
  outbound:
    endpoint: https://gateway.example.test
    retry:
      max-attempts: 3
      backoff: 250ms
    allowed-regions:
      - ap-southeast-1
      - eu-west-1
    headers:
      x-tenant: demo
      x-region: asia
~~~

Record:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.outbound")
public record OutboundProperties(
    URI endpoint,
    Retry retry,
    List<String> allowedRegions,
    Map<String, String> headers
) {
    public record Retry(
        int maxAttempts,
        Duration backoff
    ) {}
}
~~~

Chỉ cần scanner nhìn thấy root `OutboundProperties`. Nested `Retry` được Binder xử lý là một phần của mô hình dữ liệu, không cần khai báo `@ConfigurationPropertiesScan` hoặc `@Component` lên nested record.

Sử dụng:

~~~java
@Service
public class OutboundService {
    private final OutboundProperties properties;

    public OutboundService(OutboundProperties properties) {
        this.properties = properties;
    }

    public int retryLimit() {
        return properties.retry().maxAttempts();
    }
}
~~~

Tránh cố biến từng phần nested thành Spring bean độc lập nếu chúng chỉ có ý nghĩa bên trong một nhóm cấu hình.

### Khi nào tách thành bean riêng?

Nếu nhóm `app.retry.*` được nhiều module độc lập sử dụng như một contract riêng, có thể tạo `RetryProperties` với prefix riêng và đăng ký qua scan. Nhưng nếu retry chỉ là phần của một HTTP client, giữ nó là nested value giúp dependency rõ hơn.

## 13. Validation của bean configuration properties

Một bean được scan và bind vẫn có thể chứa giá trị không phù hợp nghiệp vụ. `@ConfigurationPropertiesScan` **không tự suy ra các ràng buộc như “port từ 1 đến 65535”**. Cần khai báo validation nếu muốn Spring Boot kiểm tra khi khởi tạo.

Ví dụ:

~~~java
package com.example.orders.config;

import java.time.Duration;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
    @NotBlank String host,
    @Min(1) @Max(65535) int port,
    @NotNull @Valid Timeout timeout
) {
    public record Timeout(
        @NotNull Duration connect,
        @NotNull Duration read
    ) {}
}
~~~

File cấu hình:

~~~yaml
app:
  mail:
    host: smtp.example.test
    port: 587
    timeout:
      connect: 2s
      read: 5s
~~~

Với Spring Boot 3.x và Jakarta Validation, project cần dependency validation phù hợp, ví dụ `spring-boot-starter-validation`. Khi bean được scan và bind, các ràng buộc có thể được kiểm tra. `@Valid` trên nested object giúp validation đi vào bên trong `Timeout`.

Nếu `app.mail.port=70000` hoặc host trống, lỗi validation có thể làm ứng dụng không khởi động được với thông báo nêu rõ properties có vấn đề. Đó thường là điều mong muốn đối với cấu hình thiết yếu: **fail fast** thay vì đợi đến khi request đầu tiên sử dụng giá trị sai.

### Scanning và validation khác nhau

- `@ConfigurationPropertiesScan`: phát hiện và đăng ký.
- `@ConfigurationProperties`: liên kết key với kiểu dữ liệu.
- `@Validated` và các constraint: kiểm tra điều kiện hợp lệ khi cơ chế validation được cấu hình.
- Bean nghiệp vụ: sử dụng dữ liệu sau binding.

Không được kết luận “đã thêm `@ConfigurationPropertiesScan` nên mọi field đều được validate”. Nếu cần thuộc tính bắt buộc, khai báo constraint có ý nghĩa với kiểu và đảm bảo validation provider có sẵn.

## 14. Giá trị mặc định và kiểu bị thiếu

Xét record:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    String baseUrl,
    int maxRetries,
    Duration timeout
) {}
~~~

Nếu trong file không có `app.client.timeout`, một cấu hình constructor-bound có thể nhận `null` ở thành phần `Duration` trừ khi bạn thiết kế default hoặc validation phù hợp. Nếu không có `max-retries`, primitive `int` có thể nhận giá trị mặc định như `0` trong quá trình bind.

Đừng hiểu “bean đã tạo thành công” là “mọi property cần thiết đều được cấp”.

### Default cho JavaBean mutable

Có thể dùng field initializer:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public class WorkerProperties {
    private int concurrency = 4;
    private Duration pollInterval = Duration.ofSeconds(5);

    // getter và setter tương ứng
}
~~~

### Default cho constructor-bound record

Spring Boot Binder có hỗ trợ annotation `@DefaultValue` trên parameter của constructor binding để biểu diễn fallback. Ví dụ theo phong cách record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
    @DefaultValue("4") int concurrency,
    @DefaultValue("5s") Duration pollInterval
) {}
~~~

Ví dụ này thuộc mô hình constructor binding của Spring Boot hiện đại. Với giá trị bắt buộc, không nên thêm default để che đi việc thiếu cấu hình; hãy dùng validation.

Nếu default cần tính toán từ những field khác hoặc có ngữ nghĩa phức tạp, cân nhắc thiết kế mô hình hoặc lớp nghiệp vụ xử lý rõ ràng thay vì nhét toàn bộ quy tắc vào constructor.

## 15. Vì sao scan không tìm thấy bean? Các tình huống phổ biến

### Trường hợp A — Chưa có @ConfigurationPropertiesScan

~~~java
@SpringBootApplication
public class OrderApplication {}
~~~

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(URI baseUrl) {}
~~~

Ở đây không có cơ chế dedicated registration nào được thể hiện. Nếu mã inject `ClientProperties`, có thể nhận lỗi thiếu bean.

**Sửa:** thêm `@ConfigurationPropertiesScan` ở main class hoặc dùng `@EnableConfigurationProperties(ClientProperties.class)`.

### Trường hợp B — Class nằm ngoài package được quét

~~~text
com.example.orders.OrderApplication
com.example.shared.config.ClientProperties
~~~

Nếu `@ConfigurationPropertiesScan` chỉ nằm tại `com.example.orders` mà không có tham số, scanner không bao phủ `com.example.shared.config`.

**Sửa:** dùng `basePackages` hoặc `basePackageClasses` phù hợp:

~~~java
@ConfigurationPropertiesScan(
    basePackageClasses = ClientProperties.class
)
~~~

Hoặc dùng `@EnableConfigurationProperties(ClientProperties.class)` khi chỉ cần một kiểu.

### Trường hợp C — Quên @ConfigurationProperties trên class

~~~java
public record ClientProperties(URI baseUrl, Duration timeout) {}
~~~

Nếu record không có `@ConfigurationProperties`, scanner không có dấu hiệu để biết nó là root configuration properties type.

**Sửa:** annotate với prefix đúng:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(URI baseUrl, Duration timeout) {}
~~~

### Trường hợp D — Gắn @Component rồi nghĩ scan đang hoạt động

~~~java
@Component
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    // ...
}
~~~

Class được đánh dấu component có thể được component scanning đăng ký nhưng **bị loại khỏi dedicated `@ConfigurationPropertiesScan`**. Với record constructor-bound, điều này có thể làm cơ chế tạo bean khác với mong đợi.

**Sửa:** nếu chủ đích là scanning configuration properties class, bỏ `@Component` và dùng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

### Trường hợp E — Prefix sai chính tả

File:

~~~properties
app.client.connect-timeout=750ms
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "app.clients")
public record ClientProperties(Duration connectTimeout) {}
~~~

Bean có thể được đăng ký thành công nhưng không bind được key mong đợi do `app.client` khác `app.clients`. Nếu field không bắt buộc, lỗi có thể không lộ rõ.

**Sửa:** thống nhất prefix và dùng validation cho những field phải có.

### Trường hợp F — Có bean nhưng lỗi bind kiểu

~~~properties
app.client.max-retries=several
~~~

Record:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(int maxRetries) {}
~~~

Scanner đã tìm thấy loại bean, nhưng Binder không chuyển `several` thành `int` như yêu cầu. Đây là lỗi **binding/conversion**, không phải lỗi scan package.

**Sửa:** cung cấp value đúng kiểu hoặc thay type đích phù hợp với thiết kế.

### Trường hợp G — Validation thất bại

~~~properties
app.mail.port=70000
~~~

Trong record có `@Max(65535) int port`. Nếu validation được kích hoạt, bean có thể không khởi tạo vì cấu hình sai. Đừng “sửa lỗi” bằng cách bỏ `@ConfigurationPropertiesScan`; phải sửa dữ liệu hoặc ràng buộc sai.

## 16. Lỗi không tìm thấy bean khác lỗi binding

Dựa vào thời điểm và thông điệp, có thể phân loại:

| Hiện tượng | Nguyên nhân nên kiểm tra trước |
| --- | --- |
| `NoSuchBeanDefinitionException` hoặc “required a bean ... could not be found” | Đăng ký bean, scan package, annotation trên class |
| Bean được tìm thấy nhưng field `null`/`0` | Prefix/key viết sai, cấu hình thiếu, default và kiểu primitive |
| Thông báo “Failed to bind properties under ...” | Chuyển kiểu, constructor, cấu trúc nested config, list/map |
| Thông báo vi phạm constraint Bean Validation | Value không đạt `@NotBlank`, `@Min`, `@NotNull` hoặc ràng buộc khác |
| Có hai bean cùng kiểu khi inject | Các đường đăng ký trùng lặp hoặc nhiều bean candidate |
| Bean có giá trị khác `application.yml` | Thứ tự property sources, profile, import, biến môi trường hoặc command-line |
| Đổi file config lúc chạy nhưng bean không đổi | Chưa có cơ chế refresh/rebind; scan không phải chức năng hot reload |

Một lần nữa: **`@ConfigurationPropertiesScan` không tự load lại file và không sửa key sai**. Nó giải quyết phần **phát hiện và đăng ký kiểu cấu hình**.

## 17. Ví dụ nhiều module: module chung + module chạy ứng dụng

Giả sử workspace có:

~~~text
order-platform/
  common-config/
    src/main/java/
      com/example/shared/config/
        SecurityProperties.java
        RetryProperties.java

  order-service/
    src/main/java/
      com/example/orders/
        OrderApplication.java
        service/OrderService.java
~~~

Module `order-service` có dependency tới `common-config`. Nếu `@ConfigurationPropertiesScan` đặt trên `com.example.orders.OrderApplication` mà không chỉ định base package bổ sung, các class trong `com.example.shared.config` nằm ngoài phạm vi.

Có thể khai báo:

~~~java
package com.example.orders;

import com.example.shared.config.RetryProperties;
import com.example.shared.config.SecurityProperties;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan(basePackageClasses = {
    RetryProperties.class,
    SecurityProperties.class
})
public class OrderApplication {}
~~~

Lúc này scanner quét các package chứa các type được chỉ định. Trong một package có nhiều `@ConfigurationProperties` khác, các type đó cũng có thể được đăng ký.

Nếu module chung chỉ cung cấp một properties type và muốn consumer quyết định chính xác bean cần bật, có thể dùng:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(SecurityProperties.class)
public class SecurityModuleConfiguration {}
~~~

Để module và starter dễ tái sử dụng, cần quản lý rõ **ai là người chịu trách nhiệm đăng ký properties bean**: ứng dụng tiêu thụ hay module cấu hình. Tránh vừa scan một package lớn vừa enable lặp lại không cần thiết.

## 18. Tích hợp với profile và override từ môi trường

`@ConfigurationPropertiesScan` hoạt động ở tầng bean registration. Việc profile và thứ tự nguồn được giải quyết ở tầng Config Data/Environment trước khi Binder dùng giá trị.

Giả sử file cơ sở:

~~~properties
# application.properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=3s
~~~

Tệp development:

~~~properties
# application-dev.properties
app.client.base-url=http://localhost:8090
app.client.connect-timeout=500ms
~~~

Chạy:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
~~~

Bean `ClientProperties` được scan có thể nhận các value từ `application-dev.properties` khi profile `dev` active và không có nguồn cao hơn ghi đè.

Nếu chạy:

~~~bash
java -jar order-service.jar \
  --spring.profiles.active=dev \
  --app.client.connect-timeout=250ms
~~~

thì giá trị timeout hiệu lực thường đến từ command-line argument `250ms`. Scanner không quyết định nguồn ưu tiên; nó chỉ bảo đảm có bean cấu hình để nhận kết quả binding.

Có thể dùng JVM system property:

~~~bash
java -Dapp.client.connect-timeout=2s -jar order-service.jar
~~~

hoặc biến môi trường theo quy tắc Spring Boot:

~~~bash
APP_CLIENT_CONNECTTIMEOUT=2s java -jar order-service.jar
~~~

Các nguồn này được Spring Boot xem xét khi xác định giá trị hiệu lực. Một record `ClientProperties` có thể giữ nguyên dù cách cấp cấu hình giữa local, staging và production khác nhau.

## 19. Annotation đặt trên class nào?

Một số cách bố trí hợp lệ:

**Trên main class:**

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

**Trên một lớp @Configuration:**

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConfigurationPropertiesScan(
    basePackages = "com.example.orders.config"
)
public class PropertiesScanConfiguration {}
~~~

Lớp `PropertiesScanConfiguration` phải thực sự được Spring đăng ký, ví dụ nằm trong component scan của ứng dụng hoặc được import từ một cấu hình khác. **Chỉ tạo file Java chứa `@ConfigurationPropertiesScan` mà không đưa lớp ấy vào ApplicationContext thì annotation không có cơ hội hoạt động.**

**Đặt trên một class thuần được import:**

~~~java
@ConfigurationPropertiesScan(
    basePackageClasses = ClientProperties.class
)
public class ScanDefinition {}
~~~

Nếu `ScanDefinition` được đưa vào context theo một cơ chế xử lý configuration class hợp lệ, scan có thể được kích hoạt. Thực tế, đặt trên main class hoặc một `@Configuration` được đăng ký tường minh thường rõ ràng hơn.

Điều quan trọng không phải tên class chứa annotation, mà là **class đó có được Spring xử lý như configuration source không** và **phạm vi package có bao phủ các properties class không**.

## 20. Viết test xác nhận scanning và binding

Một integration test đơn giản giúp xác nhận bean `ClientProperties` được đăng ký cùng với ứng dụng:

~~~java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import com.example.orders.config.ClientProperties;

@SpringBootTest(properties = {
    "app.client.base-url=https://api.example.test",
    "app.client.connect-timeout=900ms",
    "app.client.max-retries=4",
    "app.client.enabled=true"
})
class ClientPropertiesIntegrationTest {

    @Autowired
    ClientProperties properties;

    @Test
    void propertiesBeanIsScannedAndBound() {
        assertThat(properties.baseUrl().getHost())
            .isEqualTo("api.example.test");
        assertThat(properties.connectTimeout())
            .isEqualTo(Duration.ofMillis(900));
        assertThat(properties.maxRetries())
            .isEqualTo(4);
        assertThat(properties.enabled()).isTrue();
    }
}
~~~

Test này giả định `OrderApplication` nằm trong package mà Spring Boot test tự tìm được và có `@ConfigurationPropertiesScan` đúng phạm vi. Annotation `@SpringBootTest(properties = {...})` thêm giá trị cho môi trường test để xác minh binding mà không sửa file cấu hình production.

Nếu test báo bean không tồn tại, hãy kiểm tra scan trước; nếu có bean nhưng assertion giá trị sai, kiểm tra key, prefix, kiểu và thứ tự nguồn.

### Test nhỏ không cần full application

Khi muốn kiểm tra riêng việc scan trong một context nhỏ, có thể dùng `ApplicationContextRunner` thuộc Spring Boot Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class ScanOnlyTest {
    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfiguration.class)
            .withPropertyValues(
                "app.client.base-url=https://api.example.test",
                "app.client.connect-timeout=900ms",
                "app.client.max-retries=4",
                "app.client.enabled=true"
            );

    @Test
    void registersClientProperties() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(ClientProperties.class);
            assertThat(context.getBean(ClientProperties.class)
                .maxRetries()).isEqualTo(4);
        });
    }

    @Configuration(proxyBeanMethods = false)
    @ConfigurationPropertiesScan(
        basePackageClasses = ClientProperties.class
    )
    static class TestConfiguration {}
}
~~~

Trong ví dụ này, `ClientProperties` là record từ phần trước và cần import đúng package. Bài test `ApplicationContextRunner` minh họa cách kiểm tra cơ chế đăng ký trong context nhỏ; test đầy đủ của dự án vẫn phải có dependency Boot test và các điều kiện runtime phù hợp.

Cũng có thể unit test consumer mà không chạy Spring bằng cách tự tạo record:

~~~java
ClientProperties properties = new ClientProperties(
    URI.create("https://api.example.test"),
    Duration.ofMillis(900),
    4,
    true
);
RemoteClient client = new RemoteClient(properties);
~~~

Unit test kiểu này kiểm logic của `RemoteClient`, **không chứng minh scanning hoặc binding hoạt động**. Để kiểm scanning, cần một Spring context thực sự.

## 21. Cấu hình metadata cho IDE: không thay thế scanning

Trong một project lớn, bạn có thể thêm **Spring Boot Configuration Processor** để sinh metadata giúp IDE gợi ý key và cung cấp mô tả properties:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Với Maven, một ví dụ dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Những ví dụ trên giả định quản lý phiên bản dependency theo cách tương thích với Spring Boot project. Configuration Processor tạo metadata phục vụ công cụ phát triển; **nó không đăng ký bean `ClientProperties` ở runtime**. Nếu bỏ `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, việc IDE tự động gợi ý `app.client.connect-timeout` không chứng minh Spring ApplicationContext có bean tương ứng.

Nên phân biệt:

- **Annotation processor**: hỗ trợ metadata lúc build.
- **`@ConfigurationPropertiesScan`**: hỗ trợ phát hiện và đăng ký tại startup.
- **Binder**: chuyển các nguồn cấu hình thành đối tượng Java.
- **Bean Validation**: kiểm ràng buộc dữ liệu nếu bật cơ chế phù hợp.

## 22. Chẩn đoán lỗi bean cấu hình trong ứng dụng đang chạy

Khi thấy một bean nghiệp vụ không inject được `ClientProperties`, có thể đọc lỗi theo trình tự:

1. **Class có `@ConfigurationProperties` chưa?** Đúng prefix chưa?
2. **Có cơ chế đăng ký chưa?** `@ConfigurationPropertiesScan` ở main/config được Spring xử lý, hay có `@EnableConfigurationProperties`?
3. **Package nằm trong vùng quét?** Nếu class ở module/shared package khác, thêm base package phù hợp hoặc enable trực tiếp.
4. **Class có `@Component` không?** Nếu muốn constructor binding qua dedicated scan, tránh trộn hai đường đăng ký.
5. **Class cấu hình chứa scan có thực sự là configuration source?** Một class không được component scan/import sẽ không tự kích hoạt annotation của nó.
6. **Bean thiếu hay bean đã có nhưng bind lỗi?** Phân biệt thông báo thiếu bean với conversion/validation error.
7. **Key có xuất hiện trong Environment không?** Xét profile, config import, tham số khởi động và các nguồn override.
8. **Kiểu Java đích có tương thích?** Ví dụ `2s` cho `Duration`, số nguyên cho `int`, URL hợp lệ cho `URI`.
9. **Có đăng ký trùng hoặc nhiều bean candidate?** Đối với injection theo type, xác minh các bean cùng kiểu nếu gặp lỗi ambiguity.
10. **Project test đang load context nào?** Một slice test không phải lúc nào cũng quét cùng package hoặc auto-configuration như ứng dụng chính.

Spring Boot Actuator có endpoint `configprops` cho phép quan sát thông tin configuration properties trong điều kiện được bật và bảo vệ truy cập phù hợp. Không mở công khai những endpoint có thể tiết lộ thông tin môi trường, và không đưa mật khẩu, token hoặc private key vào log chỉ để debug.

### Không nên dùng System.getProperty để kết luận bean chưa được bind

`System.getProperty("app.client.connect-timeout")` chỉ đọc JVM system properties. Nếu key được cấp từ YAML, kết quả Java thuần có thể là `null`, trong khi `Environment` và `ClientProperties` vẫn nhận đúng value.

Nếu cần xác định giá trị hiệu lực, đọc `Environment.getProperty("app.client.connect-timeout")` hoặc bean đã bind. Nếu cần xác định nguồn nào thắng, dùng công cụ chẩn đoán property sources/origin phù hợp với môi trường an toàn.

## 23. Những hiểu nhầm thường gặp

| Nhận định | Điều cần hiểu đúng |
| --- | --- |
| “Có `@ConfigurationProperties` là bean tự xuất hiện.” | Cần một cơ chế đăng ký bean như scan hoặc enable. |
| “`@SpringBootApplication` đã quét mọi `@ConfigurationProperties`.” | Component scan và configuration properties scan là hai cơ chế khác nhau. |
| “`@ConfigurationPropertiesScan` sẽ quét toàn bộ classpath.” | Mặc định quét package chứa class được annotate và các package con. |
| “`basePackageClasses` chỉ đăng ký đúng class được nêu.” | Nó lấy package của class làm gốc quét, không phải danh sách type chính xác. |
| “Cứ thêm `@Component` vào record là tương đương scan.” | Không; nó thay đổi cơ chế đăng ký và không thích hợp cho constructor binding kiểu dedicated. |
| “Scan tự sửa sai chính tả key trong YAML.” | Binder vẫn cần prefix và tên key phù hợp. |
| “Scan quyết định `application-dev.yml` thắng file cơ sở.” | Precedence và profile do hệ thống Config Data/Environment quyết định. |
| “Scan tự validate mọi field.” | Cần constraint và validation thích hợp. |
| “File cấu hình thay đổi thì scan lại bean tự động.” | Scan và binding thông thường là quá trình khởi động, không phải hot reload. |
| “Configuration processor thay thế scan.” | Metadata lúc build và bean registration ở runtime có vai trò khác nhau. |
| “Một nested record cũng cần `@ConfigurationPropertiesScan` riêng.” | Binder xử lý nested type như thành phần của root properties model. |

## 24. Bài tập áp dụng

### Bài 1 — package mặc định

Cho:

~~~text
com.example.orders.OrderApplication   @ConfigurationPropertiesScan
com.example.orders.config.ClientProperties  @ConfigurationProperties
~~~

**Câu hỏi:** Scanner mặc định có tìm thấy `ClientProperties` không?

**Đáp án:** có, vì `com.example.orders.config` là package con của `com.example.orders`.

### Bài 2 — package ngang hàng

Cho:

~~~text
com.example.orders.OrderApplication
com.example.shared.config.ClientProperties
~~~

**Câu hỏi:** Nếu chỉ đặt `@ConfigurationPropertiesScan` mặc định trên `OrderApplication` thì bean có chắc chắn được tìm thấy không?

**Đáp án:** không. Package `com.example.shared.config` không nằm trong cây package `com.example.orders`. Dùng `basePackages`, `basePackageClasses` hoặc `@EnableConfigurationProperties(ClientProperties.class)`.

### Bài 3 — thiếu annotation trên record

~~~java
public record ClientProperties(String baseUrl) {}
~~~

**Câu hỏi:** Có `@ConfigurationPropertiesScan` trên main class thì record này có được tự nhận là root config bean không?

**Đáp án:** không, vì thiếu `@ConfigurationProperties` mô tả root và prefix.

### Bài 4 — một record được scan, file properties có value

~~~properties
app.retry.max-attempts=5
app.retry.backoff=200ms
~~~

~~~java
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(
    int maxAttempts,
    Duration backoff
) {}
~~~

**Câu hỏi:** Khi scan đúng và bind thành công, hai field nhận gì?

**Đáp án:** `maxAttempts=5` và `backoff=Duration.ofMillis(200)`.

### Bài 5 — chỉ muốn đăng ký chính xác một loại

**Bối cảnh:** Một module chỉ cần `StorageProperties`; các properties class khác trong cùng package không liên quan.

**Câu hỏi:** Dùng annotation nào diễn đạt việc đăng ký một type rõ nhất?

**Đáp án:** `@EnableConfigurationProperties(StorageProperties.class)`. `@ConfigurationPropertiesScan(basePackageClasses = StorageProperties.class)` quét package, có thể phát hiện thêm các loại khác.

### Bài 6 — Bean không được tìm thấy dù IDE gợi ý key

Project đã thêm `spring-boot-configuration-processor`, IDE tự hoàn thành `app.client.base-url`, nhưng Spring báo thiếu bean `ClientProperties`.

**Đáp án:** annotation processor tạo metadata lúc build, không tự đăng ký bean. Cần scan/enable và package phù hợp.

### Bài 7 — lỗi bind chứ không phải lỗi scan

~~~properties
app.client.max-retries=many
~~~

Record có `int maxRetries`, scanner đã phát hiện class.

**Đáp án:** Binder không chuyển được `many` thành số nguyên. Sửa value hoặc kiểu đích; việc mở rộng package scan không giải quyết lỗi này.

### Bài 8 — @Component trên immutable record

~~~java
@Component
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(URI baseUrl) {}
~~~

**Câu hỏi:** Đây có phải cách khuyến nghị để dùng constructor-bound configuration properties với scanning?

**Đáp án:** không. `@Component` thay đổi cơ chế tạo bean và dedicated `@ConfigurationPropertiesScan` không nhận những component classes. Bỏ `@Component` và dùng scan hoặc enable.

### Bài 9 — cấu hình khi chạy khác file mặc định

~~~properties
app.client.connect-timeout=3s
~~~

Chạy:

~~~bash
java -jar order-service.jar --app.client.connect-timeout=500ms
~~~

**Câu hỏi:** Bean được scan có timeout nào?

**Đáp án:** thông thường `500ms` khi command-line có ưu tiên cao hơn file và binding thành công. `@ConfigurationPropertiesScan` không ngăn override.

## 25. Bảng ghi nhớ cuối bài

| Mục tiêu | Cách làm |
| --- | --- |
| Biểu diễn nhóm key có kiểu | `@ConfigurationProperties(prefix = "app.client")` trên class/record |
| Tự tìm các properties type trong package | `@ConfigurationPropertiesScan` trên main/config class được xử lý |
| Quét đúng package bằng chuỗi | `@ConfigurationPropertiesScan(basePackages = "...")` |
| Quét package dựa trên mốc kiểu | `@ConfigurationPropertiesScan(basePackageClasses = ClientProperties.class)` |
| Đăng ký tường minh một class | `@EnableConfigurationProperties(ClientProperties.class)` |
| Đăng ký nhiều types qua enable | `@EnableConfigurationProperties({A.class, B.class})` |
| Bind vào type thư viện có setter | `@Bean` kết hợp `@ConfigurationProperties` trên phương thức |
| Tạo immutable record | Dedicated scan/enable để Binder tạo bean qua constructor |
| Cần ràng buộc giá trị | `@Validated` và Jakarta Bean Validation constraints |
| Cần hỗ trợ autocomplete key | `spring-boot-configuration-processor` |
| Kiểm tra bean scan và bind | `@SpringBootTest` hoặc `ApplicationContextRunner` |
| Sửa “could not be found” | Kiểm tra registration và package trước |
| Sửa “Failed to bind” | Kiểm tra prefix, key, kiểu, constructor và validation |
| Sửa giá trị khác dự kiến | Kiểm tra profile và precedence trong `Environment` |

Hãy nhớ theo thứ tự: **`@ConfigurationProperties` nói “dữ liệu nào thuộc đối tượng này”; `@ConfigurationPropertiesScan` nói “hãy tìm và đăng ký các đối tượng cấu hình trong những package này”; Spring Boot Binder nói “hãy biến key/value hiệu lực thành giá trị Java có kiểu”.** Khi tách được ba bước, bạn sẽ biết khi nào nên quét package, khi nào nên đăng ký type tường minh, và kiểm tra đúng nguyên nhân khi một bean cấu hình không xuất hiện hoặc không nhận dữ liệu mong đợi.
