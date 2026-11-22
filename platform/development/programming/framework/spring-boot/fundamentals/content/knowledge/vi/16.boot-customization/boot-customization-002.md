# Cung cấp bean riêng để thay một mặc định có điều kiện

Spring Boot và các thư viện starter thường tự đăng ký những bean mặc định để ứng dụng có thể chạy với ít cấu hình nhất. Ví dụ, một starter có thể cung cấp implementation mặc định cho dịch vụ gửi thông báo, bộ chuyển đổi dữ liệu hoặc một client tích hợp. Khi ứng dụng cần hành vi riêng, lập trình viên có thể đăng ký một bean khác cùng contract.

Spring Boot hỗ trợ mô hình này bằng các condition, đặc biệt là **`@ConditionalOnMissingBean`**. Bean mặc định chỉ được đăng ký khi container chưa có bean phù hợp. Nếu ứng dụng đã cung cấp bean riêng, cấu hình mặc định sẽ tự động nhường chỗ.

Cách làm này khác với việc đăng ký cả hai bean rồi dùng `@Primary` để chọn một bean khi inject. Với `@ConditionalOnMissingBean`, bean mặc định có thể không được đăng ký ngay từ đầu; với `@Primary`, cả hai bean vẫn tồn tại trong context và một bean được ưu tiên cho injection một giá trị.

Bài học giải thích cách cung cấp bean mặc định có thể thay thế, cách ứng dụng ghi đè mặc định, điều kiện được đánh giá vào thời điểm nào, cách chọn điều kiện theo kiểu hoặc tên bean, quan hệ với các annotation lựa chọn khác và cách kiểm thử cấu hình.

## 1. Vì sao Spring Boot cần bean mặc định có thể thay thế?

Một starter thường muốn cung cấp chức năng sẵn dùng. Giả sử thư viện có contract:

~~~java
package com.example.greeting;

public interface GreetingService {
    String greet(String name);
}
~~~

Implementation mặc định:

~~~java
package com.example.greeting;

public class DefaultGreetingService implements GreetingService {

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Nếu starter luôn đăng ký implementation này mà không cho ứng dụng thay thế, consumer sẽ khó tùy biến cách chào hỏi. Nếu starter không cung cấp gì, mỗi ứng dụng phải tự viết cấu hình lặp lại.

Mô hình hữu ích là:

- Starter cung cấp một implementation mặc định.
- Ứng dụng có thể đăng ký implementation của riêng mình.
- Khi ứng dụng đã có bean phù hợp, cấu hình mặc định không đăng ký bean nữa.
- Service tiêu thụ vẫn phụ thuộc vào interface `GreetingService`.

Đây là cách Spring Boot cân bằng giữa **convention (quy ước mặc định)** và **customization (khả năng tùy biến)**.

~~~mermaid
flowchart TD
    A["Spring Boot khởi động"] --> B["Đăng ký cấu hình của ứng dụng"]
    B --> C["Xử lý auto-configuration"]
    C --> D{"Đã có GreetingService?"}
    D -->|Có| E["Bỏ qua bean mặc định"]
    D -->|Chưa có| F["Đăng ký DefaultGreetingService"]
    E --> G["Inject bean ứng dụng cung cấp"]
    F --> H["Inject bean mặc định"]
~~~

Ứng dụng sử dụng cùng một contract dù bean đến từ starter hay do chính ứng dụng đăng ký.

## 2. @ConditionalOnMissingBean là gì?

`@ConditionalOnMissingBean` là annotation của Spring Boot trong package:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
~~~

Nó yêu cầu Spring chỉ áp dụng cấu hình hoặc đăng ký bean được đánh dấu khi **không tìm thấy bean phù hợp** trong phạm vi kiểm tra.

Ví dụ đơn giản:

~~~java
@Configuration(proxyBeanMethods = false)
public class GreetingConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
~~~

Ý nghĩa:

- Nếu container đã có bean kiểu `GreetingService`, method `greetingService()` không được dùng để đăng ký bean mặc định.
- Nếu chưa có bean phù hợp, Spring gọi factory method khi cần tạo bean và quản lý object được trả về.
- Bean mặc định được đăng ký như một bean bình thường khi condition khớp.

`@ConditionalOnMissingBean` thường được dùng trong **auto-configuration** của Spring Boot. Auto-configuration cung cấp cấu hình mặc định cho ứng dụng, trong khi bean do người dùng khai báo có thể thay thế cấu hình ấy.

### 2.1. Condition quyết định đăng ký bean, không phải chọn implementation lúc gọi method

Khi điều kiện không khớp, bean definition từ method được đánh dấu sẽ không được đăng ký. Vì vậy không có chuyện Spring tạo bean mặc định rồi mỗi lần gọi service lại kiểm tra xem có bean tùy biến nào khác để chuyển sang.

Đây là quyết định trong quá trình xử lý cấu hình và đăng ký bean definition.

### 2.2. Đặt condition trên method hoặc class

Đặt trên một method:

~~~java
@Configuration(proxyBeanMethods = false)
public class GreetingConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }

    @Bean
    Clock greetingClock() {
        return Clock.systemUTC();
    }
}
~~~

Trong ví dụ này, condition chỉ điều khiển bean `greetingService`. Bean `greetingClock` vẫn được khai báo độc lập.

Đặt trên class:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnMissingBean(GreetingService.class)
public class GreetingConfiguration {

    @Bean
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }

    @Bean
    GreetingFormatter greetingFormatter() {
        return new GreetingFormatter();
    }
}
~~~

Nếu condition ở cấp class không khớp, toàn bộ cấu hình bị bỏ qua, bao gồm cả bean `greetingFormatter`.

Hãy chọn vị trí theo phạm vi mong muốn:

- **Method-level condition:** chỉ bean đó có điều kiện.
- **Class-level condition:** toàn bộ cấu hình chỉ được áp dụng khi điều kiện khớp.

Khi nhiều bean độc lập có các điều kiện khác nhau, đặt condition ở từng method thường giúp cấu hình dễ hiểu hơn.

## 3. Cung cấp bean riêng từ ứng dụng

Giả sử starter có auto-configuration đăng ký mặc định:

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService defaultGreetingService() {
        return new DefaultGreetingService();
    }
}
~~~

Ứng dụng muốn cách chào hỏi riêng:

~~~java
package com.example.application;

import com.example.greeting.GreetingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ApplicationGreetingConfiguration {

    @Bean
    public GreetingService customGreetingService() {
        return new VietnameseGreetingService();
    }
}
~~~

Implementation tùy biến:

~~~java
package com.example.application;

import com.example.greeting.GreetingService;

public class VietnameseGreetingService implements GreetingService {

    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Vì bean `customGreetingService` đã được khai báo từ cấu hình của ứng dụng trước khi auto-configuration mặc định được đánh giá, `@ConditionalOnMissingBean(GreetingService.class)` không khớp. Spring bỏ qua factory method `defaultGreetingService()`.

Kết quả:

- Context có bean tùy biến.
- Bean mặc định của starter không được đăng ký.
- Consumer inject `GreetingService` sẽ nhận implementation do ứng dụng cung cấp.
- Không cần sửa mã của starter hoặc service sử dụng contract.

Tên bean được đặt khác nhau trong ví dụ để làm rõ rằng việc thay thế diễn ra nhờ **condition theo kiểu**, không phải nhờ ghi đè tên bean.

## 4. Thứ tự xử lý cấu hình rất quan trọng

`@ConditionalOnMissingBean` chỉ có thể xét các bean definition mà container đã biết tại thời điểm condition được đánh giá. Vì thế thứ tự xử lý cấu hình có ý nghĩa.

Trong mô hình Spring Boot thông thường:

1. Cấu hình do ứng dụng khai báo được xử lý.
2. Các auto-configuration được nhập và xử lý theo cơ chế auto-configuration của Boot.
3. Condition của auto-configuration có thể nhìn thấy những bean definition phù hợp đã được đăng ký từ cấu hình ứng dụng.
4. Nếu ứng dụng đã cung cấp bean, auto-configuration mặc định nhường chỗ.

Đó là lý do `@ConditionalOnMissingBean` được thiết kế và sử dụng phổ biến trong auto-configuration.

### 4.1. Không dùng condition này tùy tiện giữa các cấu hình người dùng

Giả sử hai class cấu hình thông thường đều được scan:

~~~java
@Configuration
class DefaultConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService defaultGreetingService() {
        return new DefaultGreetingService();
    }
}

@Configuration
class CustomConfiguration {

    @Bean
    GreetingService customGreetingService() {
        return new VietnameseGreetingService();
    }
}
~~~

Nếu thứ tự xử lý khiến `DefaultConfiguration` được đánh giá trước khi bean tùy biến được đăng ký, condition có thể thấy chưa có bean và đăng ký mặc định. Sau đó bean tùy biến cũng được đăng ký, dẫn đến hai candidate.

Không nên dựa vào thứ tự component scan hoặc thứ tự file để tạo cơ chế override mặc định. Với ứng dụng thật, cấu hình mặc định nên được đặt trong auto-configuration và ứng dụng cung cấp bean riêng ở user configuration.

Nếu có nhiều auto-configuration phụ thuộc thứ tự của nhau, hãy sử dụng metadata ordering phù hợp như `before` hoặc `after` trong `@AutoConfiguration`, hay các annotation ordering tương ứng. Việc sắp xếp auto-configuration phải diễn đạt quan hệ cấu hình thực sự, không phải một cách chữa mọi xung đột bean.

### 4.2. Condition không chờ bean được tạo xong

Condition chủ yếu làm việc với bean definition và metadata. Nó không cần đợi tất cả singleton được khởi tạo mới quyết định có đăng ký bean mặc định hay không.

Vì vậy, kiểu trả về của factory method tùy biến cần công bố đúng contract:

~~~java
@Bean
GreetingService customGreetingService() {
    return new VietnameseGreetingService();
}
~~~

Spring có thể nhận diện bean theo kiểu `GreetingService` từ metadata của method. Nếu khai báo return type quá chung như `Object`, type prediction có thể không nhận ra bean đó đáp ứng contract trước khi auto-configuration đánh giá điều kiện.

Không nên viết:

~~~java
@Bean
Object customGreetingService() {
    return new VietnameseGreetingService();
}
~~~

nếu mục đích là cung cấp bean thay thế cho `GreetingService`. Hãy khai báo kiểu trả về là interface hoặc implementation cụ thể có thể nhận diện.

## 5. Điều kiện theo kiểu, tên và các thuộc tính khác

`@ConditionalOnMissingBean` có nhiều thuộc tính để xác định thế nào là một bean “đã tồn tại”.

### 5.1. Kiểm tra theo kiểu

~~~java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService defaultGreetingService() {
    return new DefaultGreetingService();
}
~~~

Đây là cách phổ biến nhất: nếu đã có bean phù hợp với `GreetingService` thì không đăng ký mặc định.

Có thể dùng thuộc tính tường minh:

~~~java
@Bean
@ConditionalOnMissingBean(value = GreetingService.class)
GreetingService defaultGreetingService() {
    return new DefaultGreetingService();
}
~~~

### 5.2. Kiểm tra theo tên bean

~~~java
@Bean
@ConditionalOnMissingBean(name = "customGreetingService")
GreetingService defaultGreetingService() {
    return new DefaultGreetingService();
}
~~~

Trong ví dụ, điều kiện kiểm tra sự vắng mặt của bean có tên `customGreetingService`. Cách này hữu ích khi một contract có nhiều bean và mục tiêu là tránh đăng ký trùng một định danh cụ thể.

Tuy nhiên, nếu mục tiêu là cho phép ứng dụng cung cấp bất kỳ implementation nào của contract, kiểm tra theo kiểu thường phù hợp hơn kiểm tra theo tên.

### 5.3. Kiểm tra theo annotation

Condition cũng có thể xét bean mang annotation cụ thể:

~~~java
@Bean
@ConditionalOnMissingBean(annotation = CustomGreetingMarker.class)
GreetingService defaultGreetingService() {
    return new DefaultGreetingService();
}
~~~

`CustomGreetingMarker` là annotation tùy chỉnh do ứng dụng hoặc thư viện định nghĩa. Cách này hữu ích khi contract không đủ để diễn đạt nhóm bean mà cấu hình muốn nhận diện.

### 5.4. Bỏ qua một số kiểu khi xét candidate

Trong những trường hợp đặc biệt, các thuộc tính như `ignored` hoặc `ignoredType` có thể loại một số kiểu khỏi việc xét điều kiện. Các tùy chọn này thường phục vụ cấu hình thư viện hoặc auto-configuration phức tạp.

Không nên thêm chúng nếu chưa có nhu cầu rõ ràng. Mục tiêu của condition nên dễ đọc: “nếu người dùng đã cung cấp bean đáp ứng contract này, hãy nhường chỗ”.

## 6. Phân biệt @ConditionalOnMissingBean với @Primary

Hai annotation này thường bị nhầm là hai cách tương đương để thay bean mặc định. Thực tế chúng giải quyết hai giai đoạn khác nhau.

### 6.1. @ConditionalOnMissingBean: không đăng ký bean mặc định

~~~java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService defaultGreetingService() {
    return new DefaultGreetingService();
}
~~~

Nếu ứng dụng có bean `GreetingService` phù hợp, method mặc định không được đăng ký. Context chỉ có bean ứng dụng cung cấp cho contract này, trừ khi còn những bean khác được đăng ký từ nơi khác.

### 6.2. @Primary: đăng ký cả hai, ưu tiên một bean

~~~java
@Bean
GreetingService defaultGreetingService() {
    return new DefaultGreetingService();
}

@Bean
@Primary
GreetingService customGreetingService() {
    return new VietnameseGreetingService();
}
~~~

Ở đây cả hai bean đều tồn tại. Khi một consumer yêu cầu một `GreetingService` duy nhất, bean được đánh dấu `@Primary` được ưu tiên.

Nhưng bean mặc định vẫn được đăng ký và vẫn có thể xuất hiện khi inject collection hoặc truy vấn theo tên.

| Tiêu chí | `@ConditionalOnMissingBean` | `@Primary` |
| --- | --- | --- |
| Quyết định chính | Có đăng ký bean mặc định không? | Chọn bean nào cho injection một giá trị? |
| Bean mặc định khi ứng dụng có bean riêng | Có thể không được đăng ký | Vẫn được đăng ký |
| Nhiều bean trong collection | Chỉ các bean đã được đăng ký mới xuất hiện | Cả hai vẫn xuất hiện |
| Thường dùng ở đâu | Auto-configuration | Cấu hình bean của ứng dụng hoặc thư viện |
| Mục đích | Cho phép người dùng thay mặc định | Đặt một lựa chọn ưu tiên |

Nếu mục tiêu là thay thế hẳn mặc định của starter, `@ConditionalOnMissingBean` thường diễn đạt đúng hơn. Nếu muốn giữ nhiều implementation nhưng có một lựa chọn mặc định khi inject đơn, `@Primary` phù hợp hơn.

## 7. Phân biệt với @Qualifier và @Fallback

### 7.1. @Qualifier chọn candidate cho một consumer

Nếu có hai bean:

~~~java
@Bean
@Qualifier("default")
GreetingService defaultGreetingService() {
    return new DefaultGreetingService();
}

@Bean
@Qualifier("vietnamese")
GreetingService vietnameseGreetingService() {
    return new VietnameseGreetingService();
}
~~~

Consumer có thể chọn cụ thể:

~~~java
@Service
public class WelcomeControllerService {
    private final GreetingService greetingService;

    public WelcomeControllerService(
            @Qualifier("vietnamese") GreetingService greetingService) {
        this.greetingService = greetingService;
    }
}
~~~

`@Qualifier` không tự ngăn bean mặc định được đăng ký. Nó giúp injection point chọn đúng candidate.

### 7.2. @Fallback đánh dấu một bean dự phòng

Từ Spring Framework 6.2, `@Fallback` có thể đánh dấu một bean là candidate dự phòng khi có nhiều bean phù hợp cho injection một giá trị.

~~~java
@Bean
@Fallback
GreetingService defaultGreetingService() {
    return new DefaultGreetingService();
}

@Bean
GreetingService customGreetingService() {
    return new VietnameseGreetingService();
}
~~~

Trong trường hợp này cả hai bean vẫn được đăng ký. Bean thông thường được ưu tiên khi inject một `GreetingService`; bean fallback vẫn tồn tại và vẫn xuất hiện trong collection injection.

### 7.3. Bảng phân biệt

| Annotation | Ý nghĩa |
| --- | --- |
| `@ConditionalOnMissingBean` | Chỉ đăng ký bean khi chưa có bean phù hợp |
| `@Primary` | Ưu tiên bean này khi injection một giá trị |
| `@Qualifier` | Chọn candidate theo qualifier cụ thể |
| `@Fallback` | Đánh dấu bean có mức ưu tiên dự phòng |

`@Fallback` thuộc Spring Framework 6.2 trở lên. Nó không phải điều kiện để đăng ký bean và không thay thế `@ConditionalOnMissingBean` trong auto-configuration.

## 8. Ví dụ hoàn chỉnh về auto-configuration trong một starter

Giả sử bạn đang xây một thư viện `greeting-spring-boot-starter`. Starter muốn cung cấp `GreetingService` mặc định, nhưng ứng dụng tiêu thụ có thể thay thế.

### 8.1. Contract và implementation

`GreetingService.java`:

~~~java
package com.example.greeting;

public interface GreetingService {
    String greet(String name);
}
~~~

`DefaultGreetingService.java`:

~~~java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingService;

public class DefaultGreetingService implements GreetingService {

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

### 8.2. Auto-configuration

`GreetingAutoConfiguration.java`:

~~~java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
~~~

Khi auto-configuration được áp dụng, Spring Boot đăng ký bean mặc định nếu chưa có bean phù hợp.

### 8.3. Đăng ký auto-configuration để Boot phát hiện

Với Spring Boot 3.x, thư viện auto-configuration khai báo tên class trong file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
~~~

File này cho Spring Boot biết auto-configuration nào cần được xem xét khi ứng dụng sử dụng starter.

Trong một dự án thực tế, module auto-configuration thường tách khỏi module starter metadata; cấu trúc module cụ thể tùy cách đóng gói thư viện. Điều quan trọng là class auto-configuration được đưa vào cơ chế imports mà Boot sử dụng.

### 8.4. Ứng dụng cung cấp bean tùy biến

Trong ứng dụng tiêu thụ starter:

~~~java
package com.example.application;

import com.example.greeting.GreetingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomGreetingConfiguration {

    @Bean
    public GreetingService customGreetingService() {
        return new GreetingService() {
            @Override
            public String greet(String name) {
                return "Xin chào, " + name + "!";
            }
        };
    }
}
~~~

Khi Spring Boot xử lý `GreetingAutoConfiguration`, bean `customGreetingService` đã được đăng ký. Condition trên `greetingService()` không khớp và bean mặc định không được tạo.

Consumer:

~~~java
@Service
public class WelcomeService {
    private final GreetingService greetingService;

    public WelcomeService(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    public String welcome(String name) {
        return greetingService.greet(name);
    }
}
~~~

`WelcomeService` không cần biết implementation đến từ starter hay ứng dụng.

## 9. Kết hợp với các điều kiện khác

Trong auto-configuration, việc có hay không bean cùng kiểu chỉ là một phần của quyết định. Có thể cần kiểm tra class trên classpath, property hoặc loại ứng dụng.

Ví dụ cấu hình tích hợp client tùy chọn:

~~~java
@AutoConfiguration
@ConditionalOnClass(ExternalGreetingClient.class)
@ConditionalOnProperty(
        prefix = "greeting.external",
        name = "enabled",
        havingValue = "true"
)
public class ExternalGreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService externalGreetingService(
            ExternalGreetingClient client) {
        return new ExternalGreetingService(client);
    }
}
~~~

Các điều kiện có ý nghĩa:

- `@ConditionalOnClass`: thư viện cung cấp `ExternalGreetingClient` phải có trên classpath.
- `@ConditionalOnProperty`: ứng dụng phải bật tính năng tích hợp.
- `@ConditionalOnMissingBean`: chỉ cung cấp implementation mặc định nếu ứng dụng chưa tự cung cấp `GreetingService`.

`ExternalGreetingClient` và `ExternalGreetingService` là các kiểu minh họa. Client cần được cấu hình hoặc tạo bởi một bean khác phù hợp.

Các condition đặt trên cùng cấu hình/method thường kết hợp theo logic AND: tất cả điều kiện liên quan phải khớp để bean được đăng ký.

### 9.1. Thứ tự giữa các auto-configuration

Nếu một auto-configuration cần kiểm tra bean được cung cấp bởi auto-configuration khác, hãy khai báo thứ tự phù hợp.

Ví dụ:

~~~java
@AutoConfiguration(after = ClientAutoConfiguration.class)
public class ExternalGreetingAutoConfiguration {
    // ...
}
~~~

`ClientAutoConfiguration` là class auto-configuration giả định. `after` giúp Boot xử lý cấu hình này sau cấu hình client được nêu, trong phạm vi ordering của auto-configuration.

Ordering không thay thế việc thiết kế condition đúng. Nếu cấu hình phụ thuộc vào bean mà một auto-configuration khác đăng ký, cần xác định rõ mối quan hệ và bảo đảm điều kiện được đánh giá sau khi định nghĩa liên quan đã được xử lý.

Không dùng thứ tự để che một bean bị thiếu thực sự hoặc để dựa vào thứ tự khởi tạo singleton.

## 10. Cung cấp bean riêng cho một số loại cấu hình mặc định phổ biến

Cùng một mô hình được sử dụng trong nhiều tích hợp Spring Boot.

### 10.1. Tùy biến ObjectMapper

Spring Boot có thể cung cấp bean `ObjectMapper` dựa trên cấu hình Jackson. Nếu ứng dụng tự khai báo một bean `ObjectMapper`, một số auto-configuration mặc định liên quan có thể nhường chỗ theo điều kiện thiếu bean.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
public class JsonConfiguration {

    @Bean
    public ObjectMapper objectMapper() {
        return JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .build();
    }
}
~~~

Đoạn này cần các dependency Jackson phù hợp và import các class tương ứng.

Tuy nhiên, nếu chỉ muốn **tùy chỉnh một vài hành vi** của ObjectMapper do Boot quản lý, thường nên cân nhắc extension point như `Jackson2ObjectMapperBuilderCustomizer` thay vì thay toàn bộ `ObjectMapper`. Tự tạo bean hoàn chỉnh có thể làm bạn phải chịu trách nhiệm cho những module, feature và quy ước mà Boot vốn đã cấu hình.

Bài học ở đây: cung cấp bean riêng có thể thay một mặc định, nhưng hãy chọn mức tùy biến nhỏ nhất đáp ứng nhu cầu.

### 10.2. Tự cung cấp DataSource

Khi ứng dụng khai báo bean `DataSource` phù hợp, auto-configuration datasource mặc định có thể back off.

~~~java
@Configuration(proxyBeanMethods = false)
public class DatabaseConfiguration {

    @Bean
    public DataSource dataSource() {
        HikariDataSource dataSource = new HikariDataSource();
        dataSource.setJdbcUrl("jdbc:postgresql://localhost:5432/shop");
        dataSource.setUsername("shop_user");
        dataSource.setPassword("read-from-secure-configuration");
        return dataSource;
    }
}
~~~

Ví dụ minh họa cách tạo bean; trong ứng dụng thực tế, không hard-code mật khẩu trong source code. Nên bind properties từ cấu hình bên ngoài và quản lý secret an toàn. Ngoài ra, custom DataSource phải có driver, pool, transaction manager và các cấu hình liên quan phù hợp.

Nếu chỉ cần thay một số thuộc tính datasource, cấu hình property của Boot thường đơn giản hơn tự thay cả bean.

### 10.3. Custom bean cho integration client

Một starter có thể cung cấp client mặc định nếu ứng dụng chưa đăng ký client riêng. Ứng dụng có thể cung cấp implementation phù hợp với proxy, timeout, authentication hoặc endpoint riêng.

Điều quan trọng là bean tùy biến phải đáp ứng contract mà các service khác cần, và auto-configuration mặc định phải kiểm tra đúng kiểu/định danh để nhường chỗ.

## 11. Phân biệt thay thế bean với tùy biến bean có sẵn

Có hai cách tiếp cận:

**Thay thế bean:** ứng dụng đăng ký bean khác và auto-configuration bỏ qua bean mặc định nhờ `@ConditionalOnMissingBean`.

**Tùy biến bean:** ứng dụng giữ bean mặc định nhưng cung cấp một extension point như customizer, builder, converter, callback hoặc properties để điều chỉnh hành vi.

Ví dụ với ObjectMapper, nếu chỉ muốn thêm một module hoặc đổi một feature, customizer thường ít xâm lấn hơn việc tự tạo ObjectMapper mới.

Hãy hỏi:

- Có cần thay hoàn toàn implementation không?
- Hay chỉ cần thay một vài tham số?
- Starter có extension point được thiết kế sẵn không?
- Tự tạo bean có làm mất những cấu hình mặc định khác không?

Thay bean là một quyết định rộng hơn so với tùy chỉnh thuộc tính của bean hiện có.

## 12. Kiểm thử auto-configuration có thể nhường chỗ

Một auto-configuration nên được kiểm thử ít nhất hai trường hợp:

1. Không có bean do người dùng cung cấp: bean mặc định được tạo.
2. Có bean do người dùng cung cấp: bean mặc định không được đăng ký và bean tùy biến được sử dụng.

Spring Boot cung cấp `ApplicationContextRunner` để kiểm thử auto-configuration trong một context nhỏ.

Ví dụ test:

~~~java
import com.example.greeting.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(GreetingAutoConfiguration.class)
                    );

    @Test
    void createsDefaultWhenUserBeanIsMissing() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context.getBean(GreetingService.class))
                    .isInstanceOf(DefaultGreetingService.class);
        });
    }

    @Test
    void backsOffWhenUserBeanIsPresent() {
        contextRunner
                .withUserConfiguration(CustomGreetingConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context.getBean(GreetingService.class))
                            .isInstanceOf(CustomGreetingService.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomGreetingConfiguration {

        @Bean
        GreetingService customGreetingService() {
            return new CustomGreetingService();
        }
    }
}
~~~

`DefaultGreetingService` và `CustomGreetingService` là các implementation trong ví dụ. Test cần dependency `spring-boot-test` cùng các thư viện test phù hợp, thường được cung cấp khi dùng `spring-boot-starter-test`.

### 12.1. Kiểm tra số lượng bean

`hasSingleBean(GreetingService.class)` xác nhận context có đúng một bean phù hợp với contract trong hai kịch bản trên.

Nếu chỉ kiểm tra `context.getBean(GreetingService.class)` mà không kiểm tra số lượng, một cấu hình có thể vô tình đăng ký cả bean mặc định và bean tùy biến nhưng test vẫn nhận được một bean do primary hoặc qualifier. Với mục tiêu kiểm tra backoff, số lượng bean cũng quan trọng.

### 12.2. Kiểm tra hành vi, không chỉ kiểu

Có thể gọi method của bean để xác nhận implementation được chọn thực hiện đúng hành vi:

~~~java
assertThat(context.getBean(GreetingService.class).greet("Lan"))
        .isEqualTo("Xin chào, Lan!");
~~~

Kiểm thử cả hai nhánh condition giúp tránh tình trạng starter hoạt động khi không có customization nhưng thất bại khi ứng dụng đăng ký bean riêng.

## 13. Những lỗi thường gặp

### 13.1. Bean mặc định vẫn được đăng ký dù ứng dụng đã có bean riêng

Nguyên nhân có thể:

- Auto-configuration được xử lý trước cấu hình cung cấp bean riêng.
- Bean riêng không được đăng ký do package scan, profile hoặc condition khác.
- Kiểu trả về của factory method quá chung, khiến Spring không nhận diện được contract trước khi condition được đánh giá.
- Condition kiểm tra sai kiểu hoặc sai tên bean.

Cách xử lý:

1. Xác nhận bean tùy biến thực sự được đăng ký.
2. Khai báo return type rõ ràng, ví dụ `GreetingService`.
3. Đặt bean mặc định trong auto-configuration phù hợp.
4. Kiểm tra ordering nếu condition phụ thuộc bean từ auto-configuration khác.

### 13.2. Có hai bean cùng kiểu và injection bị nhập nhằng

Có thể bean mặc định không dùng condition hoặc condition không khớp như mong đợi. Spring đăng ký cả hai bean và constructor yêu cầu một bean duy nhất có thể thất bại với `NoUniqueBeanDefinitionException`.

Hãy kiểm tra bean definition names, condition report và cấu hình đăng ký. Đừng mặc định thêm `@Primary` là giải pháp thay thế cho việc sửa condition nếu mục tiêu thật sự là bean mặc định phải nhường chỗ.

### 13.3. Bean tùy biến được khai báo nhưng không được nhìn thấy

Một class có `@Configuration` hoặc `@Component` chỉ được xử lý nếu nằm trong phạm vi scan hoặc được import đúng cách. Kiểm tra package chứa `@SpringBootApplication` và vị trí cấu hình.

Nếu cấu hình thuộc module khác, có thể cần `@Import` hoặc cơ chế cấu hình tương ứng.

### 13.4. Dùng @ConditionalOnMissingBean trên cấu hình ứng dụng theo thứ tự không rõ

Condition được đánh giá dựa trên những definition đã xử lý tại thời điểm đó. Đặt condition vào cấu hình user thông thường có thể khiến kết quả phụ thuộc ordering.

Nếu mục đích là cung cấp mặc định cho người dùng starter, đặt nó trong auto-configuration là mô hình rõ ràng hơn.

### 13.5. Consumer yêu cầu implementation cụ thể thay vì contract

Nếu auto-configuration đăng ký bean qua interface `GreetingService` nhưng consumer yêu cầu class `DefaultGreetingService`, khi ứng dụng thay bean mặc định bằng implementation khác, consumer đó sẽ không còn được đáp ứng.

Service nên phụ thuộc interface nếu nó chỉ cần contract. Việc inject class cụ thể sẽ làm giảm khả năng thay thế bean.

### 13.6. Dùng @ConditionalOnMissingBean nhưng muốn thay đổi bean sau startup

Condition được đánh giá trong quá trình cấu hình context. Nó không theo dõi bean mới được đăng ký hoặc tự thay bean đang chạy khi property/file thay đổi.

Nếu cần thay đổi implementation động, phải thiết kế một cơ chế routing hoặc strategy ở runtime thay vì dùng condition startup.

### 13.7. Thay toàn bộ bean mặc định để chỉnh một thuộc tính nhỏ

Tự cung cấp bean có thể khiến auto-configuration không còn áp dụng một phần thiết lập khác. Trước khi thay, hãy xem có customizer hoặc properties extension point nào phù hợp hơn không.

## 14. Quy trình lựa chọn và thay bean mặc định

Khi muốn tùy biến một bean do starter cung cấp, hãy thực hiện theo thứ tự:

1. **Xác định contract:** bean mặc định có kiểu nào, service nào đang phụ thuộc vào nó?
2. **Tìm cách cấu hình chính thức:** starter có properties hoặc customizer cho nhu cầu của bạn không?
3. **Quyết định mức thay đổi:** tùy biến bean hiện có hay cung cấp implementation thay thế?
4. **Đăng ký bean đúng kiểu:** dùng `@Bean` hoặc component scan; khai báo kiểu trả về đủ cụ thể.
5. **Kiểm tra condition:** auto-configuration có dùng `@ConditionalOnMissingBean` theo contract đó không?
6. **Kiểm tra ordering:** cấu hình ứng dụng có được đăng ký trước auto-configuration cần nhường chỗ không?
7. **Kiểm thử cả hai trường hợp:** không có bean tùy biến và có bean tùy biến.
8. **Kiểm tra consumer:** service nhận interface/contract phù hợp và không phụ thuộc implementation mặc định.

Nếu không có `@ConditionalOnMissingBean` ở auto-configuration, hãy xem tài liệu của starter và cách nó thiết kế customization. Không nên tự giả định mọi bean Boot cung cấp đều được phép thay thế bằng cách đăng ký một bean cùng kiểu.

## 15. Bài thực hành

### Bài A: Cung cấp bean mặc định

Tạo interface:

~~~java
public interface CurrencyFormatter {
    String format(long amount);
}
~~~

Tạo implementation mặc định `DefaultCurrencyFormatter` và một auto-configuration:

~~~java
@Bean
@ConditionalOnMissingBean(CurrencyFormatter.class)
CurrencyFormatter currencyFormatter() {
    return new DefaultCurrencyFormatter();
}
~~~

Chạy context mà không có bean tùy biến và xác nhận implementation mặc định được tạo.

### Bài B: Thay mặc định từ ứng dụng

Tạo `VietnameseCurrencyFormatter implements CurrencyFormatter` và đăng ký bằng `@Bean` trong cấu hình ứng dụng.

Khởi động context cùng auto-configuration. Xác nhận bean mặc định không được đăng ký và service nhận implementation tiếng Việt.

### Bài C: Phân biệt với @Primary

Bỏ `@ConditionalOnMissingBean` khỏi bean mặc định, sau đó đăng ký cả default và custom formatter. Đánh dấu custom bean là `@Primary`.

Quan sát rằng:

- Cả hai bean vẫn tồn tại.
- Injection một `CurrencyFormatter` ưu tiên bean primary.
- Collection injection vẫn chứa cả hai.

Giải thích vì sao đây không phải backoff.

### Bài D: Condition theo tên bean

Thay điều kiện theo kiểu bằng điều kiện theo tên. Đổi tên factory method của ứng dụng và quan sát sự khác biệt.

Giải thích khi nào kiểm tra theo tên phù hợp hơn kiểm tra theo contract.

### Bài E: Kiểm thử auto-configuration

Dùng `ApplicationContextRunner` để viết hai test:

- Không có bean tùy biến: chỉ có default.
- Có bean tùy biến: chỉ có custom.

Xác nhận cả số lượng lẫn kiểu runtime của bean được chọn.

### Bài F: Tùy biến một phần thay vì thay bean

Chọn một bean mặc định có extension point (ví dụ builder customizer). Thử chỉnh một thuộc tính qua customizer, sau đó so sánh với việc tự tạo bean mới.

Ghi nhận cấu hình mặc định nào được giữ lại và cấu hình nào bạn phải tự chịu trách nhiệm.

## 16. Câu hỏi tự kiểm tra

**1. `@ConditionalOnMissingBean` dùng để làm gì?**

Nó cho phép chỉ đăng ký bean mặc định khi chưa có bean phù hợp trong phạm vi condition kiểm tra.

**2. Tại sao annotation này thường xuất hiện trong auto-configuration?**

Vì auto-configuration cung cấp mặc định sau khi cấu hình ứng dụng đã được xử lý, nhờ đó có thể phát hiện bean do người dùng đăng ký và nhường chỗ.

**3. Nếu ứng dụng có bean cùng kiểu, chuyện gì xảy ra?**

Condition không khớp và bean mặc định được đánh dấu không được đăng ký từ method đó.

**4. `@ConditionalOnMissingBean` khác `@Primary` thế nào?**

Condition điều khiển việc đăng ký bean; primary chỉ ưu tiên một bean trong số các candidate đã đăng ký cho injection một giá trị.

**5. Kiểu trả về của `@Bean` tùy biến có quan trọng không?**

Có. Spring cần metadata đủ cụ thể để nhận diện bean đáp ứng contract trước khi condition được đánh giá.

**6. Có thể dùng condition này trên một cấu hình người dùng thông thường không?**

Có thể, nhưng cần kiểm soát thứ tự xử lý. Mô hình phổ biến và rõ ràng nhất để cung cấp mặc định có thể thay thế là đặt condition trong auto-configuration.

**7. Nếu bean mặc định không được đăng ký, bean tùy biến có cần cùng tên không?**

Không. Khi kiểm tra theo kiểu, bean tùy biến chỉ cần đáp ứng contract phù hợp. Tên bean có thể khác.

**8. Condition có tự thay implementation khi ứng dụng đang chạy không?**

Không. Nó được đánh giá trong quá trình xử lý cấu hình của context, không phải cơ chế thay bean động ở runtime.

## 17. Kết luận

Cung cấp bean riêng để thay một mặc định có điều kiện là một trong những cơ chế tùy biến quan trọng của Spring Boot. Auto-configuration có thể đăng ký implementation mặc định bằng `@Bean` kết hợp `@ConditionalOnMissingBean`. Khi ứng dụng đã cung cấp bean phù hợp, condition không khớp và cấu hình mặc định nhường chỗ.

Hãy phân biệt cơ chế này với `@Primary`, `@Qualifier` và `@Fallback`: chúng điều khiển cách chọn candidate trong những tình huống khác nhau, còn `@ConditionalOnMissingBean` quyết định có đăng ký bean mặc định hay không. Thứ tự xử lý cấu hình và kiểu trả về của factory method cũng quan trọng vì condition dựa trên bean definition đã được nhận diện tại thời điểm đánh giá.

Khi viết starter hoặc tùy biến ứng dụng, hãy cung cấp một contract rõ ràng, đăng ký bean riêng đúng kiểu và kiểm thử cả hai nhánh có/không có bean tùy biến. Cách làm này giữ service độc lập với implementation mặc định, cho phép ứng dụng thay đổi hành vi ở ranh giới cấu hình và vẫn tận dụng được quy ước mà Spring Boot cung cấp.

