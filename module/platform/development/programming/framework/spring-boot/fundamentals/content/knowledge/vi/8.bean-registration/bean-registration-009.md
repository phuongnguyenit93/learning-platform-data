# Bean definition overriding và giới hạn của việc dùng nó để xử lý xung đột

Trong Spring Boot, một ứng dụng có thể khai báo bean bằng `@Component`, `@Service`, `@Configuration` kết hợp `@Bean`, hoặc nhận bean từ auto-configuration và các thư viện tích hợp. Khi những con đường này cùng sử dụng **một bean name**, Spring có thể gặp xung đột ngay tại bước **đăng ký bean definition**. Cơ chế **bean definition overriding** quyết định một định nghĩa đã tồn tại có được thay thế bằng định nghĩa đăng ký sau hay không.

Nhìn qua, bật overriding có vẻ là cách nhanh nhất để làm ứng dụng khởi động thành công. Nhưng nếu chưa xác định hai định nghĩa đến từ đâu, việc cho phép ghi đè dễ che giấu lỗi cấu hình, làm thay đổi implementation thực tế và khiến hành vi phụ thuộc vào thứ tự đăng ký. Bài học này giải thích rõ **overriding là gì, khi nào xảy ra, điều gì xảy ra nếu bật nó và giới hạn của cách xử lý này** trong một ứng dụng Spring Boot.

## 1. Nhắc lại: `BeanDefinition` và bean name

`BeanDefinition` là **metadata** Spring IoC container lưu để biết cách tạo và quản lý một bean. Metadata có thể chứa tên lớp, factory method, scope, trạng thái lazy, init/destroy callback và thông tin phục vụ dependency injection.

Ví dụ:

```java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class InvoiceService {
    public String createInvoice() {
        return "Created";
    }
}
```

Khi package của `InvoiceService` nằm trong phạm vi component scan, Spring có thể đăng ký một bean definition với tên mặc định là `invoiceService`. Sau đó container mới tạo instance khi cần.

Một cách khác:

```java
package com.example.demo.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean("appClock")
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

Ở đây `appClock` là **bean name**; `Clock` là **kiểu** của bean; `appClock()` là **factory method**. Ba thông tin này khác nhau. Có thể có nhiều bean cùng kiểu `Clock` nhưng tên khác nhau. Ngược lại, nếu có hai định nghĩa đăng ký trùng tên `appClock` trong cùng registry, Spring phải quyết định có chấp nhận thay thế định nghĩa cũ hay không.

### 1.1. Bean definition khác bean instance

```text
Khai báo @Bean / @Component
           |
           v
   BeanDefinition Registry
      "appClock" -> metadata
           |
           v
     BeanFactory tạo bean
           |
           v
   Object Clock được quản lý
```

**Overriding xảy ra ở cấp định nghĩa đăng ký**, không có nghĩa Java ghi đè phương thức bằng `@Override`, cũng không có nghĩa hai object tự động được hợp nhất. Nếu Spring đã từ chối định nghĩa trùng tên, ứng dụng có thể thất bại trước khi object tương ứng được khởi tạo.

### 1.2. Bean name thường đến từ đâu?

| Cách khai báo | Bean name điển hình |
| --- | --- |
| `@Service` trên `EmailService` | `emailService` nếu không đặt tên rõ ràng |
| `@Component("fastParser")` | `fastParser` |
| `@Bean` trên `Clock systemClock()` | `systemClock` nếu không chỉ định tên |
| `@Bean("appClock")` trên `Clock systemClock()` | `appClock` |
| Cấu hình framework/auto-configuration | Tên do cấu hình hoặc framework quy định |

Quy tắc đặt tên mặc định của component có những ngoại lệ theo quy tắc JavaBeans; khi phân tích sự cố, hãy xem **bean name thực tế** trong log thay vì chỉ đoán từ tên class.

## 2. Bean definition overriding là gì?

Trong Spring, registry của bean definitions ánh xạ **bean name** đến **bean definition**. Khi một tên đã có định nghĩa mà một định nghĩa khác cố đăng ký cùng tên, về mặt khái niệm có hai lựa chọn:

```text
Đăng ký bean definition A: name = "appClock"
                     |
                     v
          Registry["appClock"] = A
                     |
Đăng ký bean definition B: name = "appClock"
                     |
                     v
        Tên đã tồn tại trong registry?
                     |
          +----------+----------+
          |                     |
   Overriding = false    Overriding = true
          |                     |
          v                     v
      Báo xung đột       Thay định nghĩa A bằng B
      / thất bại         dưới cùng bean name
```

**Bean definition overriding** là việc cho phép đăng ký định nghĩa mới thay cho định nghĩa đã tồn tại **với cùng bean name trong cùng bean factory/registry**. Nếu cho phép, định nghĩa được đăng ký sau có thể thay thế định nghĩa trước đó.

Điều này có những hệ quả:

1. Hai định nghĩa không trở thành hai bean có tên khác nhau; registry giữ định nghĩa sau dưới cùng tên.
2. Đối tượng được sử dụng về sau phụ thuộc định nghĩa nào còn hiệu lực và quá trình tạo bean.
3. Thứ tự xử lý cấu hình, component scan và các thư viện tích hợp có thể ảnh hưởng định nghĩa nào được đăng ký sau.
4. Cho phép overriding không bảo đảm tất cả xung đột tên trong mọi cơ chế quét/đăng ký đều sẽ được xử lý êm thấm: có những kiểm tra riêng xảy ra trước hoặc ngoài thao tác thay thế trong registry.

### 2.1. Ví dụ cụ thể: hai `@Bean` cùng tên

Xét ứng dụng Spring Boot có cấu trúc:

```text
src/main/java/com/example/demo/
├── DemoApplication.java
└── config/
    ├── UtcClockConfiguration.java
    └── LocalClockConfiguration.java
```

Lớp khởi động:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Định nghĩa thứ nhất:

```java
package com.example.demo.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class UtcClockConfiguration {

    @Bean("appClock")
    public Clock utcClock() {
        return Clock.systemUTC();
    }
}
```

Định nghĩa thứ hai:

```java
package com.example.demo.config;

import java.time.Clock;
import java.time.ZoneId;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LocalClockConfiguration {

    @Bean("appClock")
    public Clock localClock() {
        return Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
    }
}
```

Hai class cấu hình đều nằm dưới package gốc `com.example.demo` nên có thể được Spring component scan phát hiện. Mỗi class khai báo một phương thức `@Bean`, nhưng **cả hai cùng chỉ định bean name `appClock`**.

Nếu bean definition overriding bị tắt, quá trình đăng ký có thể báo lỗi dạng:

```text
BeanDefinitionOverrideException:
Invalid bean definition with name 'appClock' ...
Cannot register bean definition ... since there is already ...
```

Thông điệp chi tiết và cách hiển thị tùy phiên bản Spring Boot/Spring Framework. Điểm quan trọng là **trùng bean name**; việc hai factory method tạo ra object đều thuộc kiểu `Clock` không giải quyết được xung đột.

## 3. Mặc định của Spring Boot và cách bật overriding

Trong các dòng Spring Boot hiện đại kể từ Spring Boot 2.1, **bean definition overriding mặc định bị tắt**. Spring Boot cố ý khiến xung đột tên được phát hiện sớm, thay vì âm thầm dùng một định nghĩa theo thứ tự đăng ký.

Để cho phép thay thế, có thể cấu hình trong `src/main/resources/application.properties`:

```properties
spring.main.allow-bean-definition-overriding=true
```

Hoặc trong `application.yml`:

```yaml
spring:
  main:
    allow-bean-definition-overriding: true
```

Chọn **một** định dạng cấu hình phù hợp với dự án; không cần chép cả hai. Thuộc tính này tác động đến cách Spring Boot thiết lập bean factory trong lúc khởi động.

### 3.1. Cấu hình bằng Java

Cũng có thể thiết lập trên `SpringApplication` trước khi chạy:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.setAllowBeanDefinitionOverriding(true);
        application.run(args);
    }
}
```

Ở cấp Spring Framework, `DefaultListableBeanFactory` cũng có cơ chế cấu hình quyền ghi đè bean definition. Với ứng dụng Spring Boot thông thường, cấu hình qua thuộc tính `spring.main...` hoặc qua `SpringApplication` dễ đọc hơn.

### 3.2. Điều gì xảy ra với ví dụ hai `Clock`?

Khi bật overriding, cả hai định nghĩa có thể được xử lý trong giai đoạn đăng ký, nhưng tên `appClock` chỉ còn ánh xạ tới định nghĩa được giữ lại sau cùng. Ví dụ:

```text
Trường hợp thứ tự 1:

1. UtcClockConfiguration đăng ký "appClock"
2. LocalClockConfiguration đăng ký "appClock"
3. Định nghĩa từ LocalClockConfiguration thay thế định nghĩa trước

Trường hợp thứ tự 2:

1. LocalClockConfiguration đăng ký "appClock"
2. UtcClockConfiguration đăng ký "appClock"
3. Định nghĩa từ UtcClockConfiguration thay thế định nghĩa trước
```

**Không nên giả định class nào luôn thắng** nếu dựa vào thứ tự quét hoặc thứ tự tìm thấy cấu hình. Trong một lần chạy cụ thể, kết quả có thể ổn định; nhưng thứ tự đăng ký không nên trở thành quy tắc nghiệp vụ không được viết rõ trong mã.

Ví dụ này cho thấy rủi ro dễ thấy: `Clock.systemUTC()` và `Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"))` có hành vi trả về giờ theo zone khác nhau khi được dùng với các API xử lý thời gian. Ứng dụng vẫn có thể khởi động nhưng sử dụng quy tắc thời gian sai so với mong đợi.

### 3.3. Không nên nhầm property với `@Primary`

```properties
spring.main.allow-bean-definition-overriding=true
```

không có nghĩa Spring tự đánh dấu một bean là primary. Thuộc tính này xử lý **đăng ký trùng tên**. `@Primary`, `@Qualifier` và cơ chế chọn bean xử lý bài toán **chọn một bean trong nhiều bean phù hợp theo kiểu** khi dependency injection.

## 4. Hai loại xung đột cần phân biệt trước khi sửa

Một lỗi dependency injection và một lỗi bean definition overriding có thể xuất hiện trong cùng chủ đề “trùng bean”, nhưng nguyên nhân và cách giải quyết khác hẳn.

### 4.1. Xung đột **cùng tên**: bean definition overriding

```java
@Configuration
class FirstConfig {
    @Bean("clock")
    Clock firstClock() {
        return Clock.systemUTC();
    }
}

@Configuration
class SecondConfig {
    @Bean("clock")
    Clock secondClock() {
        return Clock.systemDefaultZone();
    }
}
```

Hai định nghĩa có cùng name `clock`. Nếu overriding không được cho phép, việc đăng ký có thể thất bại **ngay cả khi chưa có service nào yêu cầu inject `Clock`**. Lỗi nằm ở **registry**, trước bước quyết định injection của một service cụ thể.

### 4.2. Xung đột **cùng kiểu nhưng khác tên**: dependency injection ambiguity

```java
@Configuration
class ClockConfiguration {
    @Bean("utcClock")
    Clock utcClock() {
        return Clock.systemUTC();
    }

    @Bean("localClock")
    Clock localClock() {
        return Clock.systemDefaultZone();
    }
}
```

Ở đây có **hai bean name hợp lệ**. Không có xung đột ghi đè bean definition. Nhưng khi inject:

```java
@Service
class ReportService {
    ReportService(Clock clock) {
        // Spring cần xác định Clock nào được dùng
    }
}
```

Spring có thể gặp lỗi dạng:

```text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2:
utcClock, localClock
```

Trong những trường hợp có thể dựa trên qualifier, tên tham số hoặc các quy tắc chọn ứng viên khác, Spring đôi khi resolve được một ứng viên; đừng dựa vào việc trùng tên tham số như hợp đồng cấu hình duy nhất. Để code rõ ràng, hãy chỉ định bean cần sử dụng bằng `@Qualifier` hoặc đặt mặc định bằng `@Primary`.

**Bật bean definition overriding không giải quyết xung đột này**, vì không có hai bean definition nào cùng tên để ghi đè.

### 4.3. Bảng phân biệt lỗi

| Tình huống | Vấn đề chính | Hướng xử lý đúng |
| --- | --- | --- |
| Hai `@Bean("appClock")` trong cùng context | Trùng bean name lúc đăng ký | Đổi tên, bỏ định nghĩa thừa, hoặc tổ chức điều kiện rõ ràng |
| Hai `Clock` tên `utcClock` và `localClock` cùng được inject theo kiểu | Nhiều ứng viên cùng kiểu | `@Qualifier`, `@Primary` hoặc điều chỉnh thiết kế |
| Bean cần inject không tồn tại | Không có ứng viên phù hợp | Xem package scan, profile, condition, dependency và cấu hình |
| Bean bị thay bằng implementation khác sau khi bật overriding | Định nghĩa sau ghi đè định nghĩa trước | Tìm nơi đăng ký cùng tên và xác định owner chính thức |
| Hai component cùng tên mặc định ở hai package khác nhau | Xung đột tên do naming/scanning | Đặt tên riêng, giới hạn scan hoặc chọn component cần đăng ký |

Một số xung đột phát sinh trong **component scanning** có thể bị scanner từ chối bằng kiểm tra tính tương thích của bean definitions trước khi thao tác ghi đè thông thường diễn ra. Vì vậy `allow-bean-definition-overriding=true` không phải công tắc bảo đảm giải quyết được mọi lỗi trùng tên.

## 5. Tại sao sử dụng overriding để “chữa” xung đột có giới hạn?

### 5.1. Che giấu lỗi đặt tên hoặc cấu hình trùng

Giả sử hai thư viện nội bộ đều đăng ký bean tên `tokenProvider`, mỗi bean thực hiện một cách cấp token khác nhau. Nếu bật overriding, ứng dụng có thể chỉ giữ một định nghĩa mà không làm rõ bên nào sở hữu tên này. Về sau, thay đổi dependency hoặc thứ tự cấu hình có thể làm behavior đổi mà không có thay đổi rõ ràng tại điểm inject.

Giải pháp tốt hơn là **đặt tên có chủ đích** như `internalTokenProvider`, `partnerTokenProvider`, rồi inject đúng loại qua qualifier hoặc sử dụng interface thích hợp.

### 5.2. Phụ thuộc thứ tự đăng ký

Việc định nghĩa được đăng ký sau có thể phụ thuộc vào:

- Thứ tự xử lý configuration classes.
- Phạm vi component scan và danh sách class tìm thấy.
- Các điều kiện hoặc profile đang active.
- Một số cơ chế đăng ký do thư viện và auto-configuration cung cấp.
- Cách khởi động ứng dụng trong các môi trường khác nhau.

Không nên sử dụng “class nào được scan sau sẽ thắng” làm chiến lược chọn implementation. Nếu cần lựa chọn có điều kiện, hãy biểu đạt điều kiện đó bằng cấu hình rõ ràng.

### 5.3. Có thể thay sai kiểu hoặc sai đặc tính bean

Hai bean definitions trùng tên không nhất thiết có cùng kiểu hoặc cùng scope. Ví dụ tên `cacheClient` có thể bị thay từ implementation dùng Redis sang implementation bộ nhớ cục bộ. Code không phụ thuộc vào implementation có thể vẫn chạy; code dựa trên tính chất phân tán của Redis sẽ hoạt động sai.

Nếu hai định nghĩa có kiểu không tương thích, dependency injection có thể chỉ chuyển lỗi từ “trùng bean name” thành “không có bean đúng kiểu” hoặc lỗi khi tạo bean. Bật overriding **không kiểm chứng tính tương đương nghiệp vụ** của hai bean definitions.

### 5.4. `@Primary` và `@Qualifier` không sửa được trùng bean name

`@Primary` giúp lựa chọn giữa **nhiều bean còn tồn tại** cùng kiểu. Nếu hai định nghĩa cùng dùng tên `appClock` và registry không cho phép overriding, lỗi xảy ra trước khi có thể xét `@Primary`.

`@Qualifier` tương tự: nó xác định bean mong muốn khi inject, nhưng **không tự sửa tên của các bean definitions trùng nhau**.

### 5.5. Không tạo ra hai phiên bản cùng tên để dùng đồng thời

Khi một định nghĩa ghi đè định nghĩa khác, bạn không tự nhiên có cả hai implementation để lựa chọn. Nếu ứng dụng cần cả hai, phải đăng ký chúng bằng **tên khác nhau** hoặc thiết kế một tập hợp bean có định danh rõ ràng.

### 5.6. Không thay thế xử lý conflict ở những tầng khác

Overriding không tự giải quyết:

- `NoUniqueBeanDefinitionException` vì nhiều bean cùng kiểu.
- `NoSuchBeanDefinitionException` vì thiếu bean cần inject.
- `BeanCurrentlyInCreationException` do circular dependency.
- Lỗi classpath như `ClassNotFoundException` hay `NoSuchMethodError`.
- Khác biệt package scanning, profile hoặc conditional configuration.
- Lỗi trùng route HTTP, trùng mapping hay những xung đột hạ tầng không thuộc bean definition registry.

Thực hiện đúng bước xác định nguyên nhân sẽ tránh việc bật một property không liên quan đến lỗi.

## 6. Cách sửa xung đột bằng thiết kế rõ ràng

### 6.1. Đặt tên bean khác nhau

Thay ví dụ ở mục 2 thành:

```java
package com.example.demo.config;

import java.time.Clock;
import java.time.ZoneId;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClockConfiguration {

    @Bean("utcClock")
    public Clock utcClock() {
        return Clock.systemUTC();
    }

    @Bean("businessClock")
    public Clock businessClock() {
        return Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
    }
}
```

Bây giờ cả hai definitions được đăng ký hợp lệ vì có tên riêng. Một service sử dụng clock cho nghiệp vụ có thể chọn:

```java
package com.example.demo.service;

import java.time.Clock;
import java.time.LocalDate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class BillingService {
    private final Clock clock;

    public BillingService(@Qualifier("businessClock") Clock clock) {
        this.clock = clock;
    }

    public LocalDate today() {
        return LocalDate.now(clock);
    }
}
```

`@Qualifier("businessClock")` giúp người đọc biết bean nào được sử dụng. Nếu có nhiều implementation với vai trò khác nhau, một tên riêng là lựa chọn rõ ràng.

### 6.2. Dùng `@Primary` nếu cần một lựa chọn mặc định

Trong cùng cấu hình:

```java
@Configuration(proxyBeanMethods = false)
public class ClockConfiguration {
    @Bean("utcClock")
    public Clock utcClock() {
        return Clock.systemUTC();
    }

    @Bean("businessClock")
    @Primary
    public Clock businessClock() {
        return Clock.systemDefaultZone();
    }
}
```

Khi inject `Clock` mà không ghi qualifier, `businessClock` là ứng viên ưu tiên nếu không có quy tắc chọn ứng viên khác xung đột. Nếu muốn `utcClock`, hãy dùng `@Qualifier("utcClock")`.

Ví dụ này minh họa cách **chọn giữa hai bean có tên khác nhau**. `@Primary` không phải cơ chế bean definition overriding.

### 6.3. Chỉ tạo bean khi điều kiện cấu hình phù hợp

Nếu một ứng dụng chỉ cần **một implementation theo môi trường**, dùng `@Profile` hoặc điều kiện cấu hình để tránh đăng ký đồng thời các bean.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
public class ClockConfiguration {

    @Bean("appClock")
    @Profile("dev")
    Clock devClock() {
        return Clock.systemDefaultZone();
    }

    @Bean("appClock")
    @Profile("prod")
    Clock prodClock() {
        return Clock.systemUTC();
    }
}
```

Với đúng một trong hai profile `dev` hoặc `prod` được active, chỉ định nghĩa phù hợp được đăng ký. **Nếu cả hai profile cùng active**, hai bean definitions cùng tên có thể tiếp tục xung đột; nếu không profile nào active, có thể thiếu bean `appClock`. Đó là lý do điều kiện phải được thiết kế bao phủ đúng các trạng thái ứng dụng cần hỗ trợ.

Kích hoạt profile qua cấu hình:

```properties
spring.profiles.active=dev
```

Trong hệ thống chạy nhiều môi trường, thường đặt active profile qua biến môi trường hoặc tham số khi triển khai, thay vì ghi cố định profile production vào mã nguồn.

Một cách khác là `@ConditionalOnProperty`, ví dụ:

```java
@Configuration(proxyBeanMethods = false)
public class AuditConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "audit",
        name = "enabled",
        havingValue = "true"
    )
    AuditWriter auditWriter() {
        return new ConsoleAuditWriter();
    }
}
```

Đoạn minh họa giả định `AuditWriter` và `ConsoleAuditWriter` đã được định nghĩa trong dự án, cùng dependency Spring Boot hỗ trợ `@ConditionalOnProperty`. Đây là điều kiện để **đăng ký hoặc không đăng ký** bean theo thuộc tính `audit.enabled`, chứ không phải cho phép ghi đè bean trùng tên.

### 6.4. Loại bỏ định nghĩa dư thừa hoặc giới hạn scan

Nếu cùng một component bị đăng ký qua hai con đường độc lập, hãy xem có thể bỏ một con đường hay không. Ví dụ:

```java
@Component
public class MetricsPublisher {
}
```

và đồng thời:

```java
@Configuration
public class MetricsConfiguration {
    @Bean("metricsPublisher")
    public MetricsPublisher metricsPublisher() {
        return new MetricsPublisher();
    }
}
```

Cả hai cùng dự định đăng ký bean tên `metricsPublisher`. Nếu không có lý do giữ hai cấu hình, hãy chọn **một cách đăng ký**. Khi bạn cần constructor hoặc factory method đặc biệt, giữ `@Bean`; khi chỉ cần Spring tạo component thông thường qua scanning, `@Component` có thể đủ.

Nếu một component thuộc module không nên chạy trong ứng dụng hiện tại, điều chỉnh phạm vi scan, profile hoặc cấu hình import phù hợp cũng có thể giải quyết nguyên nhân, thay vì bật overriding cho toàn ứng dụng.

## 7. `@ConditionalOnMissingBean`: cách auto-configuration nhường quyền

Một trong những cơ chế khiến Spring Boot linh hoạt là **auto-configuration có thể “back off” khi ứng dụng đã tự khai báo bean phù hợp**.

Ví dụ một cấu hình mặc định dành cho thư viện:

```java
import java.time.Clock;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClockDefaultsConfiguration {

    @Bean("appClock")
    @ConditionalOnMissingBean(Clock.class)
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

Ứng dụng có thể tự cung cấp:

```java
@Configuration(proxyBeanMethods = false)
public class ApplicationClockConfiguration {

    @Bean("appClock")
    public Clock appClock() {
        return Clock.systemDefaultZone();
    }
}
```

Trong một quy trình **auto-configuration được sắp xếp đúng thứ tự**, Spring Boot xử lý bean do ứng dụng khai báo trước rồi mới xét điều kiện của auto-configuration. Nếu đã có bean `Clock` phù hợp, default `appClock` có thể không được đăng ký. Như vậy ứng dụng tùy biến hành vi bằng cách cung cấp bean, **không cần bật overriding**.

Tuy nhiên, có hai điểm phải hiểu:

1. `@ConditionalOnMissingBean` đánh giá những bean definitions **đã được xử lý tại thời điểm điều kiện được xét**. Nếu đặt tùy tiện trên hai cấu hình người dùng không được sắp xếp thứ tự, không thể giả định nó luôn nhìn thấy định nghĩa sắp đăng ký sau.
2. `@ConditionalOnMissingBean(Clock.class)` kiểm tra **kiểu**; `@ConditionalOnMissingBean(name = "appClock")` kiểm tra **tên**. Hai điều kiện không tương đương, nhất là khi ứng dụng có nhiều bean cùng kiểu với tên khác nhau.

Đối với thư viện hoặc starter, hãy dùng cơ chế auto-configuration được hỗ trợ ở phiên bản Spring Boot của mình và thiết kế điều kiện đúng ý nghĩa. Với ứng dụng bình thường, nên ưu tiên **một nơi chịu trách nhiệm** khai báo bean nghiệp vụ.

### 7.1. `@ConditionalOnMissingBean` không phải “chống trùng tuyệt đối”

Nếu bean A được đăng ký khi điều kiện còn đúng, rồi một cấu hình khác xuất hiện sau với cùng tên, vẫn có khả năng phát sinh xung đột. Điều kiện chỉ biết registry tại thời điểm được đánh giá. Nó không hủy ngược quyết định trước đó khi biết có bean mới.

Trong auto-configuration của Spring Boot, việc sắp xếp thứ tự, điều kiện và phạm vi quét được thiết kế phối hợp để tránh trường hợp này; khi tự viết cấu hình, cần cân nhắc tương tự.

## 8. Khi nào overriding có thể được dùng có chủ đích?

Mặc dù không nên bật để “che” mọi lỗi, overriding là một cơ chế có trường hợp sử dụng cụ thể:

- Một hệ thống cũ đã có **hợp đồng thay thế bean theo tên** được thiết kế rõ và cần duy trì tạm thời trong quá trình chuyển đổi.
- Một integration framework có quy tắc đăng ký bean rất cụ thể, đã xác định definition nào cần thay thế và ai chịu trách nhiệm.
- Một môi trường thử nghiệm hoặc migration có cấu hình kiểm soát chặt, nơi có thể xác minh định nghĩa cuối cùng theo tên.

Khi cân nhắc dùng, phải biết **bean name nào bị thay, nguồn của hai định nghĩa, lý do cần thay và thứ tự đăng ký được đảm bảo bằng cơ chế nào**. Nếu không trả lời được, nên giải quyết bằng đổi tên, điều kiện, cấu hình chọn bean hoặc loại bỏ định nghĩa thừa.

### 8.1. Vì sao cách này đặc biệt rủi ro ở production?

Bật overriding bằng property thường cho phép hành vi ở cấp ứng dụng, **không chỉ cho riêng một bean xung đột**. Một thay đổi khác trong project hoặc dependency có thể vô tình tạo thêm collision và bị ghi đè thay vì báo lỗi sớm.

Điều này khiến lỗi khó phát hiện ở review, có thể chỉ bộc lộ khi môi trường khác có profile khác hoặc khi version dependency thay đổi. Ở production, cơ chế fail-fast do Spring Boot mặc định chọn thường giúp phát hiện cấu hình trùng tên sớm hơn.

### 8.2. Cách test có nên dựa vào overriding?

Một test cần thay bean thật bằng fake/mock không nhất thiết phải bật global overriding. Có thể:

- Sử dụng công cụ **bean mocking/bean overriding dành cho test** phù hợp phiên bản Spring Test hoặc Spring Boot của dự án.
- Cung cấp một bean `@Primary` dành cho test khi có hai bean với tên khác nhau và loại test phù hợp.
- Dùng `@Profile("test")` cùng cấu hình để chỉ một implementation được đăng ký.
- Giới hạn context của test đến những configuration cần thiết.

Các cơ chế hỗ trợ mock bean trong Spring Test/Boot thay đổi theo phiên bản; khi dùng chúng, nên làm theo API của chính phiên bản dự án. Không lấy việc test chạy được khi bật `spring.main.allow-bean-definition-overriding=true` làm bằng chứng rằng kiến trúc bean của ứng dụng đã đúng.

## 9. Phân biệt “ghi đè” ở các tầng khác của Spring

Từ *override* xuất hiện ở nhiều nơi nhưng không chỉ cùng một cơ chế:

| Hiện tượng | Bản chất | Có dùng `spring.main.allow-bean-definition-overriding`? |
| --- | --- | --- |
| Java `@Override` | Phương thức lớp con triển khai/ghi đè phương thức kế thừa | Không |
| Hai bean definitions cùng tên trong một registry | Đăng ký tên trùng | Có thể liên quan trực tiếp |
| `@Primary` | Chọn ứng viên ưu tiên khi inject theo kiểu | Không |
| `@Qualifier` | Thu hẹp hoặc chỉ định ứng viên injection | Không |
| `@ConditionalOnMissingBean` | Cấu hình chỉ có hiệu lực khi điều kiện thiếu bean phù hợp | Không phải cơ chế ghi đè |
| Child `ApplicationContext` có bean cùng tên với parent context | Bean ở context con có thể che (shadow) bean cùng tên ở context cha khi lookup | Không giống ghi đè cùng registry |
| Spring property từ CLI ghi đè `application.properties` | Thứ tự ưu tiên nguồn cấu hình | Không |
| Test replacement/mocking | Cơ chế thay bean trong ngữ cảnh test | Phụ thuộc API test, không đồng nhất với global overriding |

Ví dụ, nếu một child context có bean tên `clock` và parent context cũng có bean tên `clock`, việc child lookup thấy bean của mình không đồng nghĩa định nghĩa trong parent bị xóa hay bị thay bằng định nghĩa khác. Hai context có registry riêng.

## 10. Chẩn đoán lỗi bean definition overriding

Khi ứng dụng không khởi động và log có `BeanDefinitionOverrideException`, thay vì bật property ngay, hãy xác định **hai định nghĩa đang tranh cùng bean name**.

### 10.1. Đọc bean name và hai nguồn đăng ký trong lỗi

Thông điệp thường cung cấp:

```text
Bean name: appClock
New definition: ... LocalClockConfiguration ...
Existing definition: ... UtcClockConfiguration ...
```

Tên class, nguồn tài nguyên hoặc factory method có thể xuất hiện theo format khác nhau. Hãy tìm những dòng chứa `Cannot register bean definition`, `already` hoặc phần phân tích khởi động thất bại để biết **định nghĩa nào xuất hiện trước và sau** trong lần chạy đó.

### 10.2. Tìm khai báo có cùng tên

Trong IDE, tìm toàn dự án với những dạng khai báo như:

```java
@Bean("appClock")
@Bean(name = "appClock")
@Component("appClock")
@Service("appClock")
```

Đừng chỉ tìm chuỗi tên bean trong source Java: một định nghĩa có thể đến từ XML, auto-configuration hoặc thư viện khác. Với bean tên mặc định, cần kiểm tra **tên phương thức `@Bean`** và **tên component sinh từ tên class**.

### 10.3. Xem phạm vi quét và cấu hình được import

Kiểm tra:

1. Lớp `@SpringBootApplication` nằm ở package nào và đã bật `scanBasePackages` chưa.
2. Một lớp `@Configuration` có bị quét lặp hoặc import từ nhiều nguồn không.
3. Có profile, condition hoặc cấu hình module nào cùng đăng ký tên bean hay không.
4. Các dependency/starter mới có thêm cấu hình mặc định hay không.

Không có nghĩa cùng một class được nhìn thấy qua nhiều cơ chế **luôn** tạo hai definitions: Spring có nhiều cơ chế nhận diện và loại bỏ đăng ký trùng thích hợp. Khi có lỗi thật, dùng chi tiết nguồn trong exception để lần tới từng con đường tạo định nghĩa.

### 10.4. Quan sát definition khi ứng dụng khởi động được

Trong một context đang chạy, bạn có thể xem metadata:

```java
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.context.ConfigurableApplicationContext;

ConfigurableApplicationContext context =
        SpringApplication.run(DemoApplication.class, args);

ConfigurableListableBeanFactory factory = context.getBeanFactory();
BeanDefinition definition = factory.getBeanDefinition("appClock");

System.out.println("Bean class: " + definition.getBeanClassName());
System.out.println("Factory method: " + definition.getFactoryMethodName());
System.out.println("Resource: " + definition.getResourceDescription());
System.out.println("Bean type: " + context.getBean("appClock").getClass().getName());
```

Đây là đoạn minh họa để đặt trong `main()` hoặc một nơi chẩn đoán phù hợp, giả định `DemoApplication` là lớp khởi động và bean `appClock` tồn tại. Với bean đến từ `@Bean`, `getBeanClassName()` có thể là `null` vì định nghĩa sử dụng **factory method** thay vì khai báo trực tiếp bean class. `getResourceDescription()` cũng không phải lúc nào cũng có giá trị.

Nếu ứng dụng thất bại trước khi tạo context, đoạn `getBeanDefinition(...)` này không chạy được. Khi đó dựa vào exception lúc startup, thông tin nguồn cấu hình và log.

### 10.5. Dùng báo cáo điều kiện khi liên quan auto-configuration

Khi nghi ngờ Spring Boot auto-configuration, có thể khởi động với tham số:

```text
--debug
```

hoặc cấu hình:

```properties
debug=true
```

Spring Boot có thể in **Conditions Evaluation Report**, cho biết nhiều auto-configuration được áp dụng hoặc bị bỏ qua do điều kiện nào. Báo cáo này hỗ trợ phân tích các điều kiện như `@ConditionalOnMissingBean` nhưng không thay thế việc đọc exception chứa bean name xung đột.

### 10.6. Hướng giải quyết theo nguyên nhân

| Nguyên nhân đã xác định | Cách xử lý nên cân nhắc |
| --- | --- |
| Hai `@Bean` cùng name do copy cấu hình | Đổi tên hoặc bỏ definition dư |
| Một `@Component` và một `@Bean` cùng name | Chọn một cách đăng ký hoặc đặt tên tách biệt |
| Hai implementation khác vai trò | Đặt tên riêng, dùng qualifier tại nơi inject |
| Cần một implementation mặc định | Hai tên riêng + `@Primary` khi phù hợp |
| Cần một implementation theo môi trường | `@Profile`, `@ConditionalOnProperty` hoặc cấu hình điều kiện rõ |
| Auto-configuration cần nhường bean người dùng | Thiết kế `@ConditionalOnMissingBean` và thứ tự auto-configuration đúng |
| Component không nên có mặt trong ứng dụng | Chỉnh component scan, import hoặc điều kiện cấu hình |
| Cần thay bean trong test | Sử dụng cơ chế cấu hình/mocking test phù hợp phiên bản |

## 11. Bài thực hành

### Bài 1 — Tạo lỗi ghi đè và quan sát thông điệp

Tạo một Spring Boot project cơ bản với `DemoApplication` ở `com.example.demo`. Thêm hai configuration class cùng có `@Bean("appClock")` như mục 2.

Khởi động ứng dụng với cấu hình mặc định. Xác định:

1. Tên bean bị tranh chấp.
2. Tên hai configuration class và factory methods.
3. Lỗi xảy ra ở giai đoạn đăng ký định nghĩa hay khi một controller sử dụng `Clock`.

Không cần web starter để quan sát lỗi đăng ký bean trong ví dụ này.

### Bài 2 — Bật overriding và giải thích kết quả

Thêm vào `application.properties`:

```properties
spring.main.allow-bean-definition-overriding=true
```

Khởi động lại và xem runtime bean `appClock` có kiểu, zone và nguồn metadata nào. Giải thích vì sao kết quả của lần chạy hiện tại **không phải hợp đồng ổn định để lựa chọn timezone theo nghiệp vụ**.

Sau thực hành, bỏ property này khỏi cấu hình để tiếp tục bài với cơ chế phát hiện lỗi trùng tên.

### Bài 3 — Sửa đúng bằng tên riêng và qualifier

Đổi hai bean definitions thành `utcClock` và `businessClock`. Inject:

```java
public BillingService(@Qualifier("businessClock") Clock clock) {
    this.clock = clock;
}
```

Giải thích vì sao hai definitions cùng kiểu `Clock` có thể đồng thời tồn tại khi tên khác nhau. Tiếp tục thử inject không có qualifier để quan sát cách Spring chọn ứng viên hoặc báo mơ hồ tùy cấu hình.

### Bài 4 — Chọn bean bằng `@Primary`

Đánh dấu bean `businessClock` bằng `@Primary` rồi inject `Clock` không có qualifier. Quan sát implementation nào được chọn. Sau đó chuyển `@Primary` sang `utcClock` và so sánh. Vì sao bài này không cần bean definition overriding?

### Bài 5 — Profile bị bật đồng thời

Định nghĩa hai `@Bean("appClock")` với `@Profile("dev")` và `@Profile("prod")`. Khởi động lần lượt với:

```properties
spring.profiles.active=dev
```

và:

```properties
spring.profiles.active=dev,prod
```

Dự đoán điều gì xảy ra khi cả hai profiles active trong lúc overriding bị tắt. Sửa thiết kế để các profile không thể tạo hai định nghĩa cùng tên ngoài ý muốn.

### Bài 6 — Phân loại lỗi

Cho ba tình huống:

```text
A. Hai @Bean("emailSender") khác nhau cùng đăng ký.
B. Có emailSenderA và emailSenderB cùng kiểu Sender; constructor chỉ cần Sender.
C. Constructor cần Sender, nhưng không có Sender bean được đăng ký.
```

Phân loại:

- Xung đột bean definition name.
- Nhiều ứng viên theo kiểu.
- Thiếu ứng viên.

Đề xuất cách sửa phù hợp cho mỗi tình huống và giải thích tại sao chỉ bật overriding không xử lý được cả ba.

## 12. Ghi nhớ khi thiết kế bean

**Bean definition overriding xử lý việc đăng ký trùng *bean name* trong một registry.** Nếu bị tắt, Spring Boot thường báo lỗi sớm để bạn thấy hai định nghĩa xung đột. Nếu bật, định nghĩa đăng ký sau có thể thay thế định nghĩa trước, nhưng điều đó không xác định rõ implementation nên được sử dụng theo nghiệp vụ.

Trong phần lớn ứng dụng, hướng xử lý dễ bảo trì hơn là **đặt tên bean rõ ràng, giới hạn nguồn đăng ký, dùng `@Qualifier`/`@Primary` để chọn giữa những bean khác tên, và dùng điều kiện cấu hình khi chỉ một implementation nên tồn tại**. Với auto-configuration, ưu tiên cơ chế điều kiện để nhường quyền cho bean do ứng dụng tự định nghĩa.

Khi gặp lỗi liên quan bean, hãy hỏi theo đúng thứ tự: *Có hai definitions trùng tên không? Nếu không, có nhiều ứng viên cùng kiểu không? Hay không có ứng viên nào?* Trả lời được câu hỏi này sẽ giúp bạn sửa nguyên nhân thay vì sử dụng `allow-bean-definition-overriding` như một cách bỏ qua mọi xung đột.
