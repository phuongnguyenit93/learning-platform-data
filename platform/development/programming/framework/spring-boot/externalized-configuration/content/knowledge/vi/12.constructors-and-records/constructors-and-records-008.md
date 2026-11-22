# Giới hạn constructor binding với bean tạo qua @Component hoặc @Bean

Trong Spring Boot, `@ConfigurationProperties` cho phép ánh xạ các thuộc tính cấu hình bên ngoài thành đối tượng Java có kiểu. Khi kiểu đích là một **record** hoặc lớp bất biến, **constructor binding** đặc biệt phù hợp: thay vì tạo đối tượng rỗng rồi gọi setter, Spring Boot Binder đọc các giá trị từ `Environment`, chuyển kiểu và gọi constructor để tạo đối tượng hoàn chỉnh.

Tuy nhiên, có một giới hạn dễ gây lỗi: **constructor binding dành cho `@ConfigurationProperties` không áp dụng cho những bean được tạo bởi cơ chế tạo bean thông thường của Spring như `@Component`, phương thức `@Bean` hay `@Import`**. Lý do là những cơ chế đó có cách xử lý constructor và vòng đời bean riêng, không đồng nghĩa với việc Binder được quyền dùng các tham số constructor như các property cần bind.

Bài học này chỉ ra ranh giới giữa hai cách tạo đối tượng, nhận diện những đoạn mã sai, cách đăng ký đúng record bất biến, cách bind JavaBean có setter khi dùng `@Component` hoặc `@Bean`, cách xây bean nghiệp vụ cần cả cấu hình và dependency, cùng quy trình chẩn đoán lỗi.

## 1. Bản đồ tư duy: ai đang tạo bean?

~~~text
             Spring Boot Environment
             (Config Data, -D, env, CLI...)
                         |
                         v
               Các key app.client.*
                         |
          +--------------+-------------------+
          |                                  |
          v                                  v
 @ConfigurationProperties             @ConfigurationProperties
 class/record được đăng ký            trên @Component hoặc
 bằng @ConfigurationPropertiesScan     trên phương thức @Bean
 hoặc @EnableConfigurationProperties          |
          |                                  v
          v                          Spring tạo bean trước
 Spring Boot Binder quyết định               |
 constructor và cung cấp dữ liệu             v
          |                          Binder bind các property
          v                          qua cơ chế phù hợp với
 Record / immutable class             instance đã được tạo
 (constructor binding)                       |
          |                                  v
          v                          JavaBean / mutable settings
 Typed configuration bean                    |
          |                                  |
          +-------------+--------------------+
                        |
                        v
              Bean nghiệp vụ sử dụng
              cấu hình qua injection
~~~

Ở nhánh trái, đối tượng cấu hình được tạo theo cơ chế **đăng ký chuyên dụng cho configuration properties**. Ở nhánh phải, Spring đã dùng cơ chế bình thường để tạo đối tượng, sau đó hỗ trợ binding các property vào đối tượng phù hợp (thường là qua setter).

Hai con đường có thể cùng đọc một nguồn dữ liệu, nhưng **không thay thế cho nhau ở giai đoạn tạo object**.

### Câu nhớ nhanh

- `@ConfigurationProperties` khai báo prefix và hợp đồng binding.
- `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` đăng ký kiểu cấu hình cho Binder.
- **Constructor binding** tạo kiểu cấu hình bất biến từ các giá trị property.
- `@Component` và `@Bean` tạo Spring bean theo đường bình thường; việc gắn thêm `@ConfigurationProperties` không biến constructor injection của Spring thành constructor binding.
- Với đối tượng được tạo sẵn qua `@Bean` hoặc `@Component`, cân nhắc **JavaBean binding qua setter**.
- Với đối tượng bất biến cần constructor binding, đăng ký đúng kiểu qua cơ chế dedicated configuration properties.

## 2. Ví dụ chuẩn: một record bất biến được bind bằng constructor

Giả sử ứng dụng có cấu hình:

~~~yaml
# src/main/resources/application.yml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 750ms
    max-retries: 3
    enabled: true
~~~

Tạo record không có `@Component`:

~~~java
// src/main/java/com/example/orders/config/ClientProperties.java
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

Kích hoạt quét các kiểu cấu hình:

~~~java
// src/main/java/com/example/orders/OrderApplication.java
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

Consumer inject record:

~~~java
// src/main/java/com/example/orders/client/RemoteClient.java
package com.example.orders.client;

import com.example.orders.config.ClientProperties;
import org.springframework.stereotype.Service;

@Service
public class RemoteClient {
    private final ClientProperties config;

    public RemoteClient(ClientProperties config) {
        this.config = config;
    }

    public boolean canCallRemote() {
        return config.enabled();
    }
}
~~~

Với `@ConfigurationPropertiesScan` đặt trên `com.example.orders.OrderApplication`, package `com.example.orders.config` thuộc phạm vi quét. Binder có thể tạo `ClientProperties` từ các key hiệu lực:

| Property | Record component | Giá trị được bind |
| --- | --- | --- |
| `app.client.base-url` | `baseUrl: URI` | `https://api.example.test` |
| `app.client.connect-timeout` | `connectTimeout: Duration` | 750 mili giây |
| `app.client.max-retries` | `maxRetries: int` | 3 |
| `app.client.enabled` | `enabled: boolean` | `true` |

Ví dụ sử dụng record tương đương về mặt dữ liệu với một object đã được tạo bằng constructor Java thông thường:

~~~java
new ClientProperties(
    URI.create("https://api.example.test"),
    Duration.ofMillis(750),
    3,
    true
);
~~~

Đoạn `new` chỉ minh họa trạng thái sau binding; trong ứng dụng, Binder tạo đối tượng và Spring inject bean ấy cho `RemoteClient`.

**Điểm chính:** trong mô hình này, không có `@Component` hay `@Bean` tạo `ClientProperties` trước khi Binder xử lý. Nó được đăng ký bằng cơ chế `@ConfigurationPropertiesScan`, phù hợp với constructor binding.

## 3. Vì sao @Component + record bất biến thường là sai?

Xét cách viết sau:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

Trông có vẻ hợp lý: `@Component` để Spring tìm được bean, còn `@ConfigurationProperties` để Binder nhận giá trị. Nhưng đây **không phải** cách đăng ký record constructor-bound được khuyến nghị.

Với `@Component`, Spring đi theo cơ chế **component scanning và tạo bean thông thường**. Khi gặp constructor record, Spring có thể coi các tham số `URI`, `Duration` và `int` là những dependency hoặc argument cần cung cấp qua cơ chế tạo bean của Spring, chứ không tự coi chúng là các key `app.client.*` để Binder điền vào.

Lỗi có thể biểu hiện như:

~~~text
Parameter 0 of constructor in ...
required a bean of type 'java.net.URI'
that could not be found.
~~~

Hoặc một biến thể liên quan đến việc Spring không có cách cấp đủ constructor arguments phù hợp.

### Vì sao thêm @ConfigurationPropertiesScan chưa chắc sửa được?

Theo quy tắc Spring Boot, `@ConfigurationPropertiesScan` **không chọn những lớp được annotate `@Component` hoặc meta-annotated `@Component`** như các kiểu configuration properties để nó tạo theo dedicated binding. Vì vậy, nếu record vẫn có `@Component`, bạn đang khiến bean đi vào một đường đăng ký khác với mong đợi.

**Cách sửa:** bỏ `@Component` trên record, giữ `@ConfigurationProperties` và đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

### @Component không phải lúc nào cũng không thể đi cùng @ConfigurationProperties

Với **JavaBean mutable**, có constructor mặc định cùng setter, `@Component` cộng `@ConfigurationProperties` có thể là một con đường hợp lệ để Spring tạo bean rồi bind giá trị. Giới hạn ở đây là **constructor binding**, không phải việc dùng annotation `@ConfigurationProperties` với component bean trong mọi trường hợp.

Phân biệt rõ:

- **Sai mục đích:** thêm `@Component` vào record bất biến rồi mong Binder cung cấp constructor arguments bằng cơ chế constructor binding.
- **Có thể hợp lệ:** bean JavaBean được component scan tạo trước, có setter để Binder gán các thuộc tính sau đó.
- **Ưu tiên khi thiết kế mới:** các configuration properties types nên được đăng ký qua scan chuyên dụng hoặc enable tường minh để tách bạch loại bean.

## 4. @Bean tạo đối tượng trước: constructor binding không áp dụng

Một hiểu nhầm tương tự xảy ra với `@Bean`.

### Cách viết dễ hiểu nhầm

~~~java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "app.client")
    ClientProperties clientProperties() {
        return new ClientProperties(
            URI.create("https://fallback.example.test"),
            Duration.ofSeconds(3),
            1
        );
    }
}
~~~

Giả sử `ClientProperties` là record bất biến chỉ có ba component. Trong đoạn này, **phương thức `@Bean` tự gọi constructor**, nghĩa là bean đã được tạo trước khi Spring Boot làm việc với đối tượng return. Gắn `@ConfigurationProperties` lên phương thức không biến ba giá trị dùng trong `new ClientProperties(...)` thành những tham số Binder được phép thay thế bằng Config Data.

Các component của record không có setter. Vì thế, cơ chế bind vào instance đã tạo không thể dùng constructor binding để dựng lại record. Nếu giá trị bên ngoài không cập nhật được, đối tượng có thể giữ dữ liệu được cung cấp bởi mã Java (và hành vi lỗi/bind còn phụ thuộc cấu hình Binder). Đây không phải cách tạo immutable configuration properties bean từ YAML.

### Mẫu đúng 1 — Không tạo record trong @Bean

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

Spring Boot Binder được quyền tạo record theo constructor từ các key tương ứng.

### Mẫu đúng 2 — @Bean chỉ tạo bean nghiệp vụ, nhận typed config

`@Bean` rất phù hợp để dựng một **client hoặc service** dựa vào cấu hình đã được bind:

~~~java
package com.example.orders.config;

import com.example.orders.client.RemoteGateway;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GatewayConfiguration {

    @Bean
    RemoteGateway remoteGateway(ClientProperties properties) {
        return new RemoteGateway(
            properties.baseUrl(),
            properties.connectTimeout(),
            properties.maxRetries()
        );
    }
}
~~~

Ở đây `RemoteGateway` là ví dụ class nghiệp vụ do ứng dụng định nghĩa. `ClientProperties` vẫn được Binder tạo từ cấu hình bằng dedicated registration, còn `@Bean` có nhiệm vụ dựng gateway từ dữ liệu đã có.

Luồng trở nên rõ:

~~~text
YAML / properties / env
          |
          v
  ClientProperties
 (constructor binding)
          |
          v
@Bean remoteGateway(ClientProperties p)
          |
          v
  RemoteGateway bean
~~~

Mô hình này vừa giữ configuration model bất biến, vừa cho phép Spring inject thêm HTTP client, executor, metrics registry hoặc các dependency khác vào phương thức `@Bean` khi xây bean nghiệp vụ.

## 5. Mẫu hợp lệ: @Bean kết hợp JavaBean setter binding

`@ConfigurationProperties` trên phương thức `@Bean` có tác dụng khi muốn bind vào một **đối tượng đã được tạo**, đặc biệt một type thư viện bên ngoài có constructor mặc định và getter/setter.

Giả sử có kiểu mutable:

~~~java
package com.example.orders.legacy;

import java.time.Duration;

public class LegacyPoolSettings {
    private int maximumSize = 8;
    private Duration idleTimeout = Duration.ofSeconds(30);

    public int getMaximumSize() {
        return maximumSize;
    }

    public void setMaximumSize(int maximumSize) {
        this.maximumSize = maximumSize;
    }

    public Duration getIdleTimeout() {
        return idleTimeout;
    }

    public void setIdleTimeout(Duration idleTimeout) {
        this.idleTimeout = idleTimeout;
    }
}
~~~

Dùng `@Bean` để đăng ký và bind vào instance:

~~~java
package com.example.orders.config;

import com.example.orders.legacy.LegacyPoolSettings;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LegacyPoolConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "app.pool")
    LegacyPoolSettings legacyPoolSettings() {
        return new LegacyPoolSettings();
    }
}
~~~

Tệp cấu hình:

~~~properties
app.pool.maximum-size=24
app.pool.idle-timeout=10s
~~~

Khi bean được tạo từ phương thức, Binder có thể gọi các setter để thay default tương ứng theo nguồn cấu hình. Với các property không được cấp, default từ field initializer vẫn được giữ trong phương thức binding thông thường.

**Điểm cần chú ý:** `@Bean` là nơi tạo đối tượng, còn `@ConfigurationProperties` trên method yêu cầu binding vào đối tượng đó. Đây là **JavaBean-style binding**, không phải **constructor binding**. Nó phù hợp cho type có setter, không phù hợp khi muốn Binder tự gọi một constructor nhận toàn bộ giá trị.

### Vì sao ví dụ này quan trọng với thư viện bên thứ ba?

Bạn có thể không sửa được source code của một class trong thư viện để thêm `@ConfigurationProperties` hoặc constructor binding. Nhưng nếu class đó có các property ghi được (setter phù hợp), `@Bean` trả về instance cho phép Spring Boot bind các key theo prefix mà không cần viết từng lời gọi setter từ `Environment`.

Nếu class thư viện bất biến và chỉ có constructor tham số, hãy tạo **typed properties bean riêng** rồi dùng nó trong phương thức `@Bean` để xây class thư viện; không cố dùng setter binding lên immutable instance.

## 6. @Component với JavaBean mutable: cơ chế khác constructor binding

Một ví dụ component có thể được tạo bởi Spring rồi bind:

~~~java
package com.example.orders.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "app.worker")
public class WorkerSettings {
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

Dữ liệu:

~~~yaml
app:
  worker:
    concurrency: 12
    poll-interval: 2s
~~~

Nếu component nằm trong phạm vi component scan của Spring, Spring tạo bean `WorkerSettings` bằng constructor không tham số phù hợp rồi hệ thống xử lý `@ConfigurationProperties` bind các value qua setter.

Bản chất vẫn là:

1. Spring tạo bean bằng cơ chế `@Component`.
2. Binding property được áp dụng lên instance đã tạo.
3. Consumer inject instance sau khi bean được khởi tạo.

Nó không đi qua đường mà Binder trực tiếp gọi constructor theo các key `app.worker.*` để tạo immutable object.

### Khi nào không nên dùng @Component cho settings?

Khi cần một record hoặc class bất biến, cần kiểm soát constructor binding, muốn phân biệt rõ bean cấu hình với bean nghiệp vụ, hoặc muốn khai báo default/validation theo contract typed config một cách tập trung, hãy dùng `@ConfigurationPropertiesScan` hay `@EnableConfigurationProperties`.

Dùng `@Component` với mutable settings có thể phù hợp trong mã cũ, nhưng không nên “thêm `@Component` để hết lỗi thiếu bean” một cách vô thức. Nó thay đổi đường khởi tạo bean và có thể che lấp lý do ban đầu vì sao scan không thấy class.

## 7. @Import và BeanDefinition tự đăng ký có giới hạn tương tự

Không chỉ `@Component` và `@Bean`, các bean được tạo thông qua các cơ chế Spring thông thường khác, ví dụ sử dụng `@Import` để đưa lớp cấu hình hay bean definition vào context, cũng không mặc nhiên nhận constructor binding của `@ConfigurationProperties`.

Hãy phân biệt hai trường hợp:

- **Dùng `@Import(SomeConfiguration.class)` để đăng ký một configuration class**, sau đó `@Bean` hoặc component scan tạo các bean mà class đó khai báo. Những bean đó tuân theo cơ chế tạo bean tương ứng.
- **Dùng `@EnableConfigurationProperties(MyProperties.class)` trong một configuration class**, dù configuration class có được đưa vào context thông qua `@Import`, thì `MyProperties` vẫn được đăng ký theo cơ chế dành cho configuration properties.

Như vậy, vấn đề không phải “`@Import` luôn sai”, mà là **constructor-bound properties instance được tạo bởi ai**. Nếu muốn Binder trực tiếp tạo đối tượng từ property values, hãy dùng registration mechanism chuyên dụng cho `@ConfigurationProperties`.

Không nên coi mọi class được đưa vào ApplicationContext bằng bất kỳ cách nào là tương đương một configuration properties bean được scan đúng cách.

## 8. Chọn @ConfigurationPropertiesScan hay @EnableConfigurationProperties?

Cả hai đều là con đường thích hợp để đăng ký các typed properties classes, bao gồm record immutable.

### Quét theo package

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

Nếu `OrderApplication` ở `com.example.orders`, scanner mặc định tìm các kiểu `@ConfigurationProperties` trong package đó và các package con. Đây là lựa chọn thuận tiện khi ứng dụng có nhiều nhóm cấu hình.

Cần quét package khác:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan(basePackages = {
    "com.example.orders.config",
    "com.example.shared.config"
})
public class OrderApplication {}
~~~

Hoặc khai báo theo package của class mốc:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan(basePackageClasses = ClientProperties.class)
public class OrderApplication {}
~~~

`basePackageClasses` chọn **package của type mốc**, không chỉ đăng ký đúng một type đó. Các lớp `@ConfigurationProperties` khác trong cùng phạm vi cũng có thể được tìm thấy.

### Đăng ký một kiểu cụ thể

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
public class ClientConfiguration {}
~~~

Với `@EnableConfigurationProperties`, bạn nêu rõ type cần đăng ký, không phụ thuộc việc scanner tìm type đó ở package nào.

### Bảng so sánh

| Nhu cầu | Lựa chọn |
| --- | --- |
| Ứng dụng có nhiều kiểu properties trong package rõ ràng | `@ConfigurationPropertiesScan` |
| Starter/config module cần đăng ký một type xác định | `@EnableConfigurationProperties(ThatType.class)` |
| Typed record immutable constructor-bound | Scan chuyên dụng hoặc enable tường minh |
| Bean nghiệp vụ cần typed config | Inject config bean vào `@Bean`/constructor nghiệp vụ |
| Class thư viện mutable có setter | `@Bean` + `@ConfigurationProperties` trên method |
| Component settings mutable được tạo sẵn | `@Component` + `@ConfigurationProperties` có thể bind bằng setter |

Không cần khai báo cùng một type qua cả scan và enable chỉ để “cho chắc”. Dự án nên chọn một chiến lược nhất quán và kiểm tra khi có lỗi bean candidate hoặc bean definition lặp.

## 9. Vì sao constructor injection và constructor binding không giống nhau?

Cả hai đều xuất hiện dưới dạng Java constructor, nhưng dữ liệu đầu vào đến từ hai hệ thống.

### Constructor injection của Spring

~~~java
@Service
public class OrderService {
    private final RemoteClient remoteClient;

    public OrderService(RemoteClient remoteClient) {
        this.remoteClient = remoteClient;
    }
}
~~~

Spring tìm một bean `RemoteClient` trong ApplicationContext để đưa vào constructor của `OrderService`. Đây là **dependency injection**: tham số constructor mô tả dependency là Spring bean.

### Constructor binding của Spring Boot

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

Spring Boot Binder lấy `app.client.base-url`, `app.client.connect-timeout` và `app.client.max-retries` từ nguồn cấu hình, chuyển kiểu rồi gọi constructor. Các tham số biểu diễn **giá trị cấu hình**, không phải Spring bean phải tìm trong container.

### Sự khác nhau làm phát sinh lỗi

Nếu đặt `@Component` trên `ClientProperties`, Spring có thể cố inject `URI` hoặc `Duration` như dependency. Nhưng bạn không định nghĩa bean `URI` hoặc `Duration`; bạn chỉ có value trong YAML. Vì vậy lỗi missing bean có thể xuất hiện dù file YAML hoàn toàn hợp lệ.

Giải pháp là cho hai trách nhiệm đi đúng đường:

~~~text
Binder -> ClientProperties(URI, Duration, int)
Spring DI -> RemoteClient(ClientProperties)
~~~

Đừng dùng một constructor của class `@Component` để mong nhận đồng thời property values theo Binder và những Spring bean khác theo DI như thể hai cơ chế tự hợp nhất.

## 10. Muốn vừa có config values vừa có dependency thì thiết kế sao?

Giả sử một HTTP gateway cần `WebClient.Builder` hoặc một client factory là Spring bean, và đồng thời cần base URL, timeout, retry từ cấu hình. Một hướng sạch là tách:

**Bước 1 — Configuration properties chỉ chứa dữ liệu:**

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.remote")
public record RemoteProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

**Bước 2 — Đăng ký typed properties:**

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

**Bước 3 — Bean nghiệp vụ dùng constructor injection cho cả config bean và dependency khác:**

~~~java
package com.example.orders.client;

import com.example.orders.config.RemoteProperties;
import org.springframework.stereotype.Service;

@Service
public class GatewayService {
    private final RemoteProperties settings;
    private final RequestSigner signer;

    public GatewayService(
        RemoteProperties settings,
        RequestSigner signer
    ) {
        this.settings = settings;
        this.signer = signer;
    }

    public boolean isRetryConfigured() {
        return settings.maxRetries() > 0;
    }
}
~~~

`RequestSigner` là type nghiệp vụ minh họa, cần có một bean phù hợp được đăng ký. `GatewayService` là Spring component, constructor nhận **hai dependency là bean**. `RemoteProperties` là bean đã được Binder tạo, nên các giá trị bên trong không cần trở thành Spring bean riêng.

Nếu muốn dùng factory method thay vì `@Service`:

~~~java
@Configuration(proxyBeanMethods = false)
public class GatewayConfiguration {

    @Bean
    GatewayService gatewayService(
        RemoteProperties settings,
        RequestSigner signer
    ) {
        return new GatewayService(settings, signer);
    }
}
~~~

**Không cần** đánh dấu `GatewayService` bằng `@ConfigurationProperties`; nó là bean nghiệp vụ tiêu thụ cấu hình, không phải loại dữ liệu cần Binder sinh từ YAML.

## 11. @ConfigurationProperties trên @Bean method: cùng key nhưng khác vòng đời

Cùng có prefix `app.pool`, nhưng cách tạo đối tượng phụ thuộc registration path:

| Thiết kế | Ai tạo instance? | Cách bind điển hình | Phù hợp |
| --- | --- | --- | --- |
| `@ConfigurationProperties` trên record + scan | Spring Boot Binder | Constructor binding | Record/lớp immutable |
| `@ConfigurationProperties` trên JavaBean + scan | Dedicated configuration properties mechanism | Setter binding | Class mutable |
| `@Component` + `@ConfigurationProperties` | Component mechanism của Spring | Bind lên bean đã được tạo | Mutable bean có setter |
| `@Bean` + `@ConfigurationProperties` | Phương thức factory trả về instance | Bind lên instance đã tạo | Mutable type, third-party library |
| `@Bean` trả về object nghiệp vụ, nhận typed properties bean | Factory method Spring | Không bind object nghiệp vụ trực tiếp | Client/service cần giá trị config |

Với một class mutable, nhiều cách có thể thực hiện được chức năng, nhưng cách đăng ký chuyên dụng giữ vai trò rõ ràng hơn. Với record immutable, lựa chọn về đường đăng ký quan trọng hơn vì constructor binding không phải một bước tùy ý diễn ra sau khi instance tồn tại.

## 12. Khi record có nhiều constructor thì sao?

Trong Spring Boot hiện đại, một class/record có một constructor có tham số phù hợp có thể được suy ra để constructor binding. Nhưng khi loại dữ liệu có **nhiều constructor** hoặc thiết kế phức tạp hơn, Binder có thể cần chỉ định constructor muốn sử dụng theo phiên bản Spring Boot.

Ví dụ class immutable với một constructor nhận các giá trị cấu hình:

~~~java
package com.example.orders.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.retry")
public class RetryProperties {
    private final int maxAttempts;
    private final Duration backoff;

    public RetryProperties(int maxAttempts, Duration backoff) {
        this.maxAttempts = maxAttempts;
        this.backoff = backoff;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public Duration getBackoff() {
        return backoff;
    }
}
~~~

Đăng ký dedicated qua scan hoặc enable để Binder có thể gọi constructor từ các key `app.retry.max-attempts` và `app.retry.backoff`.

Nếu class có nhiều constructor và cần chọn một constructor binding, Spring Boot 3.x hỗ trợ annotation `@ConstructorBinding` trên constructor thích hợp (package của annotation trong các phiên bản mới khác các ví dụ cũ):

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;

@ConfigurationProperties(prefix = "app.retry")
public class RetryProperties {
    private final int maxAttempts;
    private final Duration backoff;

    @ConstructorBinding
    public RetryProperties(int maxAttempts, Duration backoff) {
        this.maxAttempts = maxAttempts;
        this.backoff = backoff;
    }

    // Ví dụ constructor phụ trợ cho việc sử dụng thuần Java
    public RetryProperties() {
        this(3, Duration.ofSeconds(1));
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public Duration getBackoff() {
        return backoff;
    }
}
~~~

Tùy phiên bản, cách phát hiện tên tham số constructor có thể cần metadata build như `-parameters`. Với project Boot hiện đại sử dụng plugin và cấu hình build chuẩn, nhiều trường hợp được hỗ trợ tự động; nếu binding báo không xác định được parameter name, hãy kiểm tra cấu hình compiler.

**Dù có `@ConstructorBinding`, không được kết luận nó khiến một `@Component` hoặc bean tạo bởi `@Bean` tự được bind qua constructor.** Annotation chỉ tham gia vào quy trình Binder dành cho kiểu được đăng ký đúng cơ chế.

## 13. Default values với constructor binding

Một constructor-bound record bất biến không có setter và không thể giữ default theo kiểu “constructor mặc định rồi set từng trường” như JavaBean. Spring Boot Binder có annotation `@DefaultValue` cho tham số constructor binding.

Ví dụ:

~~~java
package com.example.orders.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(
    @DefaultValue("3") int maxAttempts,
    @DefaultValue("200ms") Duration backoff
) {}
~~~

Khi `app.retry.max-attempts` hoặc `app.retry.backoff` không có trong nguồn cấu hình tương ứng, Binder có thể sử dụng những default này theo quy tắc của nó. Việc dùng default là lựa chọn có chủ đích, không nên che việc thiếu các key thiết yếu.

Với JavaBean mutable, default có thể đặt ở field initializer:

~~~java
@ConfigurationProperties(prefix = "app.retry")
public class RetrySettings {
    private int maxAttempts = 3;
    private Duration backoff = Duration.ofMillis(200);

    // Getter và setter tương ứng
}
~~~

Nếu class này được tạo qua `@Component` hoặc `@Bean` rồi bind qua setter, các giá trị default còn lại khi key không được cung cấp. **Đừng sao chép nguyên cách default của record sang một class mutable và nghĩ rằng mọi cơ chế tạo bean hoạt động giống nhau.**

### Vắng key không đồng nghĩa value rỗng hoặc sai kiểu

Một key thiếu có thể dùng default; một key tồn tại nhưng chứa giá trị không thể chuyển sang `Duration` vẫn có thể làm binding thất bại. `@DefaultValue` không phải công cụ bỏ qua các giá trị cấu hình sai cú pháp.

Ví dụ:

~~~properties
# Giá trị không chuyển được thành Duration hợp lệ
app.retry.backoff=tomorrow
~~~

Khi bind `Duration`, lỗi là vấn đề chuyển kiểu. Cần sửa dữ liệu, không chỉ gắn `@DefaultValue("200ms")`.

## 14. Validation: đăng ký đúng vẫn chưa đủ

Constructor binding giúp tạo object có kiểu, nhưng **không tự áp dụng mọi ràng buộc nghiệp vụ**. Nếu cần một URL bắt buộc, số retry không âm hoặc timeout có mặt, có thể dùng Jakarta Bean Validation khi project đã cấu hình provider phù hợp.

Ví dụ:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    @NotNull URI baseUrl,
    @NotNull Duration connectTimeout,
    @Min(0) int maxRetries
) {}
~~~

Dependency thường dùng trong Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Khi bean được đăng ký qua scan hoặc enable, Binder tạo instance và cơ chế validation có thể kiểm tra các constraint. Nếu `base-url` bị thiếu hoặc `max-retries=-1`, quá trình khởi tạo có thể thất bại với lỗi liên quan đến binding/validation, giúp phát hiện cấu hình sai sớm.

Cần phân biệt ba loại lỗi:

- **Thiếu bean:** scanner/enable không đăng ký kiểu cấu hình.
- **Không tạo được object:** đường khởi tạo sai, constructor binding không phù hợp với `@Component`/`@Bean`, thiếu type hoặc converter.
- **Giá trị không hợp lệ:** property thiếu, sai kiểu hoặc vi phạm constraint sau binding.

Sửa đúng lớp nguyên nhân giúp tránh những giải pháp sai như thêm `@Component` vào record chỉ để “hết lỗi bean không tồn tại”.

## 15. @NestedConfigurationProperty và đối tượng lồng nhau

Một record bất biến có thể chứa cấu hình lồng nhau:

~~~yaml
app:
  outbound:
    base-url: https://gateway.example.test
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.outbound")
public record OutboundProperties(
    URI baseUrl,
    Retry retry
) {
    public record Retry(
        int maxAttempts,
        Duration backoff
    ) {}
}
~~~

Nếu `OutboundProperties` được đăng ký theo dedicated configuration properties mechanism, Binder xử lý nested `Retry` theo cấu trúc dữ liệu. Không cần biến `Retry` thành `@Component` hoặc Spring bean riêng chỉ vì nó là một record có constructor.

Nếu một nested object cần validation riêng, có thể dùng `@Valid` trên thành phần chứa nested object và các constraint trong nested type, khi bean validation hoạt động đúng.

**Đừng nhầm nested record với dependency injection:** `Retry` là dữ liệu lồng trong một configuration object; nó không phải dependency mà Spring phải tìm bằng type trong ApplicationContext.

## 16. Binding không phụ thuộc việc giá trị đến từ YAML hay -D

Một `ClientProperties` được tạo bằng Binder vẫn đọc giá trị hiệu lực của Spring Boot `Environment`. Ví dụ:

~~~properties
# application.properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=3s
app.client.max-retries=2
~~~

Chạy:

~~~bash
java -Dapp.client.connect-timeout=800ms -jar order-service.jar
~~~

JVM system property có thể ghi đè file cho key `app.client.connect-timeout`, khi không có nguồn ưu tiên cao hơn. Record được bind thành đối tượng với timeout 800 ms.

Hoặc:

~~~bash
java -jar order-service.jar --app.client.max-retries=5
~~~

Command-line property có thể ghi đè số retry thành 5. Dù đường cung cấp khác nhau, record vẫn dùng cùng prefix và kiểu.

Một biến môi trường theo quy ước Spring Boot thường được dùng như:

~~~bash
APP_CLIENT_CONNECTTIMEOUT=1s java -jar order-service.jar
~~~

Các nguồn cần tên key tương thích với cơ chế relaxed binding. Ví dụ `app.client.connect-timeout` trong file ánh xạ sang `connectTimeout` trong Java.

**Nguồn cấu hình có được ưu tiên hay không là câu chuyện của `Environment` và Config Data**, không phải vì bean được tạo qua scan hay enable. Giới hạn của constructor binding nằm ở **cơ chế tạo bean**, không phải ở cách khai báo giá trị trong file.

## 17. Lỗi thực tế và dấu hiệu phân biệt

### Lỗi A — record vừa @Component vừa @ConfigurationProperties

~~~java
@Component
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(URI baseUrl, Duration timeout) {}
~~~

**Triệu chứng:** thiếu bean dependency như `URI` hoặc constructor không được Spring giải quyết.

**Nguyên nhân:** Spring đang đi theo component construction thay vì Binder constructor binding.

**Cách sửa:** bỏ `@Component`, thêm dedicated registration bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(ClientProperties.class)`.

### Lỗi B — @Bean trả về record mới với default hardcoded

~~~java
@Bean
@ConfigurationProperties(prefix = "app.client")
ClientProperties clientProperties() {
    return new ClientProperties(
        URI.create("https://fallback.example.test"),
        Duration.ofSeconds(3)
    );
}
~~~

**Triệu chứng:** YAML có giá trị nhưng object không nhận đúng các field như kỳ vọng; có thể có lỗi binding tùy kiểu.

**Nguyên nhân:** method đã tạo instance bất biến, Binder không có setter và constructor binding không phải cách hoạt động của `@Bean` method.

**Cách sửa:** để Binder tạo record từ nguồn cấu hình qua scan/enable; hoặc dùng method `@Bean` để tạo **bean nghiệp vụ** từ một typed properties bean đã có.

### Lỗi C — JavaBean @Bean có setter nhưng vẫn không bind

~~~java
@Bean
@ConfigurationProperties(prefix = "app.pool")
LegacyPoolSettings pool() {
    return new LegacyPoolSettings();
}
~~~

**Triệu chứng:** các field giữ default.

**Nên kiểm tra:** class có setter đúng tên và public accessibility hay không; prefix `app.pool` có khớp với key như `app.pool.maximum-size` hay không; cấu hình có thật sự được nạp và không bị nguồn khác ghi đè hay không.

Không kết luận lỗi này do “`@Bean` không bao giờ hoạt động với `@ConfigurationProperties`”: `@Bean` hỗ trợ binding vào instance phù hợp, chỉ **không sử dụng constructor binding**.

### Lỗi D — record đúng nhưng không có bean

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(URI baseUrl) {}
~~~

**Triệu chứng:** thông báo `required a bean of type ClientProperties that could not be found`.

**Nguyên nhân có thể:** chưa đặt `@ConfigurationPropertiesScan` hoặc chưa `@EnableConfigurationProperties`; đặt scan ở package không bao gồm record.

**Cách sửa:** đăng ký đúng, không thêm `@Component` vào record.

### Lỗi E — record được scan nhưng bind không đủ values

~~~properties
app.client.max-retries=many
~~~

Record cần `int maxRetries`.

**Triệu chứng:** `Failed to bind properties under ...` hoặc lỗi conversion.

**Nguyên nhân:** dữ liệu không chuyển được sang `int`, không phải do `@Component` hay `@Bean`. Sửa dữ liệu thành số hợp lệ.

### Lỗi F — constructor của component vừa nhận dependency vừa nhận @Value

~~~java
@Component
public class SomeService {
    public SomeService(
        OtherService other,
        @Value("${app.worker.concurrency:4}") int concurrency
    ) {
        // ...
    }
}
~~~

**Có phải constructor binding của `@ConfigurationProperties`?** Không. Đây là **constructor injection thông thường của Spring** với một đối số được giải qua `@Value` và một đối số là Spring bean. Mẫu này có thể hợp lệ cho component nghiệp vụ, nhưng không biến `SomeService` thành immutable configuration properties object.

Nếu có nhiều property thuộc cùng nhóm, tách một typed `WorkerProperties` bean rồi inject nó vào service sẽ rõ ràng hơn.

## 18. Khi nào một @Bean method có thể nhận constructor-bound properties?

Một factory method có thể nhận một **configuration properties bean đã được bind** như tham số:

~~~java
@Configuration(proxyBeanMethods = false)
public class ClientFactoryConfiguration {

    @Bean
    RemoteClient remoteClient(
        ClientProperties clientProperties,
        ClientMetrics clientMetrics
    ) {
        return new RemoteClient(
            clientProperties.baseUrl(),
            clientProperties.connectTimeout(),
            clientMetrics
        );
    }
}
~~~

`RemoteClient` và `ClientMetrics` là các type minh họa, cần có định nghĩa và bean thích hợp trong ứng dụng. Quan hệ là:

- `ClientProperties`: được tạo thông qua dedicated configuration properties registration, áp dụng constructor binding.
- `ClientMetrics`: là dependency khác được Spring tạo.
- `RemoteClient`: được factory method tạo từ cả hai.

Không có giới hạn cấm `@Bean` **tiêu thụ** đối tượng constructor-bound. Giới hạn chỉ là không dùng `@Bean` làm cơ chế **tạo chính đối tượng properties cần Binder constructor binding**.

Đây là mẫu thiết kế thường được dùng khi cấu hình cho client thư viện bên thứ ba vốn không thể annotate `@ConfigurationProperties`.

## 19. Những tình huống chọn cách triển khai

| Tình huống | Cách làm phù hợp |
| --- | --- |
| Cần record bất biến với URI, Duration, int | `@ConfigurationProperties` + scan/enable |
| Class immutable chỉ có constructor nhận property values | Dedicated registration cho Binder |
| Một component service cần timeout và bean repository | Inject typed properties bean và repository qua constructor |
| Thư viện có object settings mutable, nhiều setter | `@Bean` + `@ConfigurationProperties` trên method |
| Dự án cũ có mutable `@Component` properties bean | Có thể giữ setter binding nếu cần tương thích |
| Muốn chuyển từ mutable bean sang record | Bỏ `@Component`/factory tạo record, thêm scan/enable |
| Một package có nhiều cấu hình typed | `@ConfigurationPropertiesScan` |
| Starter chỉ muốn đăng ký một type | `@EnableConfigurationProperties(TheType.class)` |
| Object nested chỉ là dữ liệu con của config | Để Binder xử lý nested object |
| Cần default cho record constructor-bound | `@DefaultValue` và validation phù hợp |
| Cần fail fast khi thiếu key | `@Validated` + Bean Validation |
| Key bị nguồn khác override | Kiểm tra property source precedence, không đổi cơ chế bean |
| Muốn cấu hình thay đổi khi file được sửa | Thiết kế refresh/rebind riêng; constructor binding không tự hot reload |

## 20. Thiết kế migration từ @Component mutable sang record

Giả sử mã cũ:

~~~java
@Component
@ConfigurationProperties(prefix = "app.export")
public class ExportSettings {
    private String directory;
    private int batchSize = 100;

    public String getDirectory() {
        return directory;
    }

    public void setDirectory(String directory) {
        this.directory = directory;
    }

    public int getBatchSize() {
        return batchSize;
    }

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }
}
~~~

Khi muốn chuyển sang bất biến, có thể dùng record:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.export")
public record ExportProperties(
    String directory,
    @DefaultValue("100") int batchSize
) {}
~~~

Thay cách đăng ký:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

Thay cách tiêu thụ:

~~~java
@Service
public class ExportService {
    private final ExportProperties properties;

    public ExportService(ExportProperties properties) {
        this.properties = properties;
    }

    public int batchSize() {
        return properties.batchSize();
    }
}
~~~

Hãy hiểu thứ tự thay đổi:

1. Tạo model properties bất biến biểu diễn cùng tên key.
2. Đưa default đang có từ field initializer sang cơ chế default dành cho constructor-bound type.
3. Không thêm `@Component` vào record.
4. Đăng ký record qua scan hoặc enable.
5. Đổi consumer để inject record và gọi accessor của record.
6. Nếu hệ thống có hai types với cùng prefix trong giai đoạn chuyển đổi, cần quản lý rõ bean nào đang thực sự được sử dụng; tránh giữ hai con đường registration mơ hồ.

Nếu cần kiểm tra directory không trống hoặc batchSize dương, có thể bổ sung validation. Với ứng dụng nhiều module, cần xác định package của record nằm trong phạm vi scan.

## 21. Cách viết test phân biệt registration và binding

Test tích hợp có thể chứng minh rằng record được scan/enable và nhận value từ môi trường:

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
    "app.client.max-retries=5",
    "app.client.enabled=true"
})
class ClientPropertiesTest {

    @Autowired
    ClientProperties config;

    @Test
    void constructorBoundRecordHasValues() {
        assertThat(config.baseUrl().getHost())
            .isEqualTo("api.example.test");
        assertThat(config.connectTimeout())
            .isEqualTo(Duration.ofMillis(900));
        assertThat(config.maxRetries()).isEqualTo(5);
        assertThat(config.enabled()).isTrue();
    }
}
~~~

Test giả định main class có `@ConfigurationPropertiesScan` đúng package hoặc `@EnableConfigurationProperties`, và dự án có Spring Boot Test dependencies. Nếu test báo không inject được bean, kiểm tra **đường đăng ký**. Nếu bean có nhưng không đúng value, kiểm tra **binding/precedence**.

### Test class thư viện mutable được tạo qua @Bean

Giả sử có `LegacyPoolSettings` với setter như phần trước. Có thể tạo test context và xác nhận bean nhận `app.pool.maximum-size=24`. Mục đích của test này khác test record: nó chứng minh **setter binding trên một bean đã được tạo**, không chứng minh Binder gọi constructor của type thư viện.

Nếu muốn unit test consumer mà không chạy Spring, tự tạo typed properties record:

~~~java
ClientProperties props = new ClientProperties(
    URI.create("https://api.example.test"),
    Duration.ofMillis(900),
    5,
    true
);

RemoteClient client = new RemoteClient(props);
~~~

Đoạn trên là minh họa khi constructor `RemoteClient(ClientProperties)` được định nghĩa tương ứng. Test thuần Java chứng minh consumer dùng dữ liệu đúng, nhưng **không chứng minh scanning hoặc binding**. Để kiểm cơ chế đăng ký, phải có Spring context thực tế.

## 22. Có phải mọi class bất biến đều dùng được constructor binding?

Không mặc nhiên. Spring Boot Binder cần có cách xác định constructor, tên property, kiểu đích và conversion phù hợp. Hãy xem xét:

- Class có annotation `@ConfigurationProperties(prefix = "...")` và được đăng ký đúng cơ chế?
- Constructor có tham số tương ứng với key cấu hình?
- Các parameter name có thể được Binder xác định từ metadata build hoặc annotation phù hợp?
- Các kiểu như `Duration`, `URI`, enum, nested object có converter/binder thích hợp?
- Với nhiều constructor, đã chỉ định đúng constructor binding nếu phiên bản yêu cầu?
- Có các property bắt buộc bị thiếu hoặc sai kiểu?
- Class có đồng thời `@Component` hoặc được tạo qua `@Bean` không?

Một lớp bất biến có logic constructor quá phức tạp, sử dụng các dependency Spring bean hoặc thực hiện network call không phải ứng viên tốt cho typed configuration model. **Đối tượng configuration properties nên mô tả dữ liệu**, còn công việc tạo client hoặc mở kết nối nên ở bean nghiệp vụ riêng.

### Không lẫn lộn validation với constructor injection

Một constructor có câu lệnh:

~~~java
if (maxRetries < 0) {
    throw new IllegalArgumentException("maxRetries must be nonnegative");
}
~~~

có thể tự kiểm tra đầu vào; nhưng nếu mã này nằm trong constructor của bean `@Component`, nó không tự biến đối tượng thành constructor-bound `@ConfigurationProperties`. Muốn hệ thống bind key/value theo cấu trúc, vẫn phải dùng dedicated registration.

## 23. Đọc lỗi startup theo nhóm nguyên nhân

| Lỗi quan sát | Khả năng cao | Hướng xử lý |
| --- | --- | --- |
| Spring đòi bean `URI`, `Duration` cho record `@Component` | Đang dùng constructor injection của Spring, không phải Binder constructor binding | Bỏ `@Component`, scan/enable record |
| `required a bean of type ClientProperties ... could not be found` | Chưa đăng ký hoặc scan sai package | Kiểm `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties` |
| `Failed to bind properties under 'app.client'` | Binder đã đi vào binding nhưng value/constructor/type không hợp | Kiểm key, value, constructor, converter, default |
| `No qualifying bean ... expected single matching bean but found ...` | Có nhiều bean cùng type hoặc đường đăng ký chồng chéo | Kiểm bean names, qualifiers và chiến lược registration |
| Bean `@Bean` mutable vẫn giữ default | Setter/prefix/file/precedence không đúng | Kiểm getter/setter, nguồn value, prefix |
| Record `@Bean` không đổi khi YAML đổi | Instance bất biến được tạo bằng Java factory; không có constructor binding | Tạo record qua dedicated Binder, chuyển factory sang tiêu thụ record |
| `@NotNull`/`@Min` thất bại | Dữ liệu thiếu hoặc sai constraint | Sửa source/validation, không sửa scan |
| Chỉnh file cấu hình lúc runtime nhưng object không đổi | Không có refresh/rebind riêng | Thiết kế cơ chế reload, không dựa vào scan |

### Quy trình tìm lỗi ngắn

1. Xác định đối tượng gây lỗi là **configuration properties bean** hay **bean nghiệp vụ**.
2. Kiểm cách đối tượng được **đăng ký**: scan/enable, component, factory method, import.
3. Nếu muốn constructor binding, xác nhận **không tạo instance qua `@Component` hay `@Bean`**.
4. Kiểm constructor/record component và prefix tương ứng.
5. Kiểm giá trị hiệu lực trong Environment, bao gồm profile, import, biến môi trường, `-D` và command-line arguments.
6. Kiểm conversion và validation.
7. Khi cần test, tách một integration test xác nhận bean được tạo/bind khỏi unit test nghiệp vụ.

Không dùng việc “Spring Boot đã đọc YAML” làm bằng chứng rằng một record đã được đăng ký đúng đường; hai bước là riêng biệt.

## 24. Những hiểu nhầm nên loại bỏ

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Có `@ConfigurationProperties` là constructor tự bind.” | Còn phải đăng ký type đúng cơ chế và có constructor phù hợp. |
| “`@Component` trên record sẽ giúp Binder tự tìm giá trị cho tham số.” | Component constructor injection không phải dedicated constructor binding. |
| “`@Bean` cộng `@ConfigurationProperties` luôn bị cấm.” | `@Bean` hỗ trợ bind vào instance mutable phù hợp; giới hạn là constructor binding. |
| “`@Bean` trả về record rồi Binder sẽ gọi lại constructor với giá trị YAML.” | Factory đã tạo instance; không có bước constructor binding để thay instance đó. |
| “`@ConfigurationPropertiesScan` bắt mọi `@Component` properties class.” | Component types bị loại khỏi dedicated properties scan. |
| “`@EnableConfigurationProperties` chỉ dùng cho class mutable.” | Nó đăng ký cả immutable type phù hợp cho Binder constructor binding. |
| “Constructor của Spring bean có tham số giống key nên Binder tự hiểu.” | Tham số constructor của Spring DI là dependencies, không mặc định là property values. |
| “@Bean không thể dùng record config làm tham số.” | Có thể inject một properties bean đã được Binder tạo vào factory method. |
| “Một nested record phải có `@Component` riêng.” | Binder xử lý nested value như phần của root configuration model. |
| “Đã tạo được config bean thì chắc mọi value đúng.” | Vẫn cần kiểm kiểu, default và validation. |
| “Thay file YAML lúc chạy tự tạo lại bean bất biến.” | Cần cơ chế refresh/rebind riêng. |
| “Nếu có lỗi, cứ thêm `@Component` để Spring thấy class.” | Thêm component có thể chuyển sang đường tạo bean không phù hợp. |

## 25. Bài tập xác định cơ chế tạo đối tượng

### Bài 1 — record được đăng ký bằng dedicated scanning

~~~java
@ConfigurationProperties(prefix = "app.cache")
public record CacheProperties(Duration ttl, int maximumSize) {}
~~~

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class App {}
~~~

**Câu hỏi:** nếu record nằm trong package được quét, đây có phải ứng viên constructor binding không?

**Đáp án:** có. Record được đăng ký qua `@ConfigurationPropertiesScan`, phù hợp với dedicated constructor binding của Spring Boot khi các key/kiểu thỏa điều kiện.

### Bài 2 — record có thêm @Component

~~~java
@Component
@ConfigurationProperties(prefix = "app.cache")
public record CacheProperties(Duration ttl, int maximumSize) {}
~~~

**Câu hỏi:** đây có tương đương với bài 1?

**Đáp án:** không. Spring component mechanism tạo bean theo constructor injection. Dedicated scanner không chọn component class như cách đăng ký constructor-bound properties. Cần bỏ `@Component` và đăng ký qua scan/enable.

### Bài 3 — bean mutable từ @Bean method

~~~java
@Bean
@ConfigurationProperties(prefix = "app.pool")
LegacyPoolSettings settings() {
    return new LegacyPoolSettings();
}
~~~

`LegacyPoolSettings` có constructor mặc định và setter `setMaximumSize`.

**Câu hỏi:** có thể nhận `app.pool.maximum-size=16` không?

**Đáp án:** có thể, thông qua binding vào instance mutable sau khi method tạo bean; đây không phải constructor binding.

### Bài 4 — record immutable được new trong @Bean

~~~java
@Bean
@ConfigurationProperties(prefix = "app.client")
ClientProperties client() {
    return new ClientProperties(
        URI.create("https://fallback.example.test"),
        Duration.ofSeconds(5),
        1
    );
}
~~~

**Câu hỏi:** Binder có tự thay ba tham số `new` bằng YAML?

**Đáp án:** không có constructor binding trên bean đã được factory method tạo. Chọn scan/enable để Binder tạo record, còn `@Bean` chỉ nên nhận record đã bind nếu cần xây bean nghiệp vụ.

### Bài 5 — một service cần config và dependency

~~~java
@Service
public class ExportService {
    ExportService(
        ExportProperties properties,
        StorageClient storageClient
    ) {
        // ...
    }
}
~~~

**Câu hỏi:** constructor này dùng cơ chế gì?

**Đáp án:** constructor injection của Spring cho hai bean `ExportProperties` và `StorageClient`. `ExportProperties` có thể đã được tạo trước bằng Binder constructor binding, nhưng constructor của `ExportService` không phải Binder constructor binding.

### Bài 6 — @EnableConfigurationProperties

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
class ClientConfiguration {}
~~~

**Câu hỏi:** `ClientProperties` có nhất thiết phải nằm trong package được `@ConfigurationPropertiesScan` quét không?

**Đáp án:** không. Enable đăng ký tường minh type; class cần có trên classpath và configuration class đó phải được Spring xử lý.

### Bài 7 — chuyển từ mutable sang record

Trước đây `@Component @ConfigurationProperties(prefix = "app.worker")` có setter `setConcurrency`; giờ chuyển sang:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(int concurrency) {}
~~~

**Câu hỏi:** cần thay gì?

**Đáp án:** bỏ cơ chế `@Component`, thêm scan/enable, đổi consumer nếu cần và chuyển default/validation sang mô hình constructor-bound thích hợp. Không chỉ xóa setter rồi giữ nguyên cách tạo bean.

### Bài 8 — sai kiểu không phải do registration

~~~properties
app.worker.concurrency=many
~~~

Record dùng `int concurrency`, đã được scan đúng.

**Câu hỏi:** sửa bằng cách thêm `@Component` có đúng không?

**Đáp án:** không. Lỗi là `many` không chuyển được sang `int`; phải sửa dữ liệu hoặc thay type hợp lý.

## 26. Bảng quyết định cuối bài

| Muốn làm gì? | Cơ chế đúng |
| --- | --- |
| Bind key vào constructor của immutable record | `@ConfigurationProperties` + `@ConfigurationPropertiesScan` |
| Bind key vào constructor của class immutable | Dedicated scan/enable, constructor hợp lệ |
| Đăng ký chính xác một kiểu properties | `@EnableConfigurationProperties(Type.class)` |
| Spring tự tạo component thông thường | `@Component`/`@Service` + constructor injection dependency |
| Bind property lên component mutable có setter | `@Component` + `@ConfigurationProperties` có thể dùng |
| Tạo object settings của thư viện rồi set property | `@Bean` + `@ConfigurationProperties` trên method |
| Tạo client từ config bất biến và dependency khác | `@Bean Client(ImmutableProperties, OtherBean)` |
| Dùng default cho constructor-bound record | `@DefaultValue` hoặc thiết kế constructor hợp lệ |
| Kiểm cấu hình quan trọng khi startup | `@Validated` và Bean Validation |
| Biết vì sao có lỗi thiếu bean | Kiểm registration, scan package và các stereotype annotation |
| Biết vì sao có lỗi binder | Kiểm prefix, key, conversion, constructor và validation |

**Kết luận cốt lõi:** constructor binding của `@ConfigurationProperties` chỉ phù hợp khi Spring Boot Binder được dùng theo **đường đăng ký configuration properties chuyên dụng**. Bean được Spring tạo qua `@Component` hay `@Bean` vẫn có thể nhận cấu hình theo cơ chế bind lên instance mutable, nhưng **không sử dụng constructor binding theo cùng cách**. Với record hoặc class bất biến, hãy để Binder tạo typed config bean; với service hoặc client nghiệp vụ, hãy inject typed config bean ấy vào constructor Spring thông thường hoặc factory method `@Bean`. Phân ranh giới này giúp tránh lỗi khởi tạo, giữ cấu hình có kiểu rõ ràng và làm dự án dễ kiểm thử hơn.
