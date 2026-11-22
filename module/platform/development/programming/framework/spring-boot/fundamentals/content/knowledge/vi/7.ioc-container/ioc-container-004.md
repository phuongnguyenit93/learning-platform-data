# BeanFactory và ApplicationContext

Trong Spring Boot, chúng ta thường viết `@Service`, `@Repository`, `@RestController`, `@Bean` hoặc constructor injection mà không trực tiếp tạo mọi đối tượng bằng `new`. Đằng sau cách làm đó là **IoC container** của Spring: thành phần biết những đối tượng nào cần tồn tại, cách tạo chúng, cách nối các phụ thuộc và cách quản lý vòng đời.

Hai tên thường gặp khi đọc tài liệu và source code của Spring là **`BeanFactory`** và **`ApplicationContext`**. Đây là hai interface có quan hệ kế thừa: `BeanFactory` xác định hợp đồng nền tảng của container; `ApplicationContext` mở rộng khả năng đó cho một ứng dụng thực tế. Spring Boot thường khởi tạo và sử dụng một **ApplicationContext** khi chạy ứng dụng.

Nắm rõ mối quan hệ này giúp bạn trả lời những câu hỏi như: vì sao bean được tạo khi startup, `getBean()` hoạt động thế nào, vì sao Spring có thể inject dependency theo constructor, và tại sao `ApplicationContext` còn dùng được để đọc cấu hình, tài nguyên hoặc phát sự kiện.

## 1. Từ `new` thủ công đến IoC container

Giả sử có hai class Java:

```java
public class MessageFormatter {
    public String format(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

```java
public class GreetingService {
    private final MessageFormatter formatter;

    public GreetingService(MessageFormatter formatter) {
        this.formatter = formatter;
    }

    public String greet(String name) {
        return formatter.format(name);
    }
}
```

Không dùng Spring, đoạn code gọi chúng có thể như sau:

```java
MessageFormatter formatter = new MessageFormatter();
GreetingService service = new GreetingService(formatter);
System.out.println(service.greet("Lan"));
```

Kết quả:

```text
Xin chào, Lan!
```

Code tự quyết định **khi nào tạo** `MessageFormatter`, **khi nào tạo** `GreetingService` và **đưa dependency nào vào constructor**.

Khi sử dụng IoC container, bạn khai báo *định nghĩa* của các đối tượng và mối quan hệ cần thiết. Container chịu trách nhiệm tạo và cung cấp đối tượng theo cấu hình:

```text
                   Định nghĩa bean
            @Component / @Bean / cấu hình
                         │
                         ▼
                   IoC container
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
       MessageFormatter       GreetingService
              └──────────┬──────────┘
                         ▼
             Constructor injection
                         │
                         ▼
                 Mã nghiệp vụ chạy
```

Đó là **Inversion of Control** (đảo ngược quyền điều khiển): phần code nghiệp vụ không cần tự điều phối toàn bộ quá trình dựng object graph. **Dependency Injection (DI)** là một cách IoC container cung cấp dependency vào constructor, field hoặc setter; constructor injection thường được ưu tiên vì dependency được biểu lộ rõ và có thể kiểm tra bằng Java thuần.

Một **Spring bean** là đối tượng được container tạo hoặc đăng ký và quản lý theo bean definition hoặc cơ chế đăng ký tương ứng. Không phải mọi object Java trong JVM đều là Spring bean.

## 2. `BeanFactory` là gì?

`BeanFactory` là interface nền tảng của Spring IoC container, nằm trong package:

```java
import org.springframework.beans.factory.BeanFactory;
```

Vai trò chính của nó là cung cấp quyền truy cập tới các bean được container quản lý. Những phương thức tiêu biểu:

```java
Object getBean(String name);

<T> T getBean(String name, Class<T> requiredType);

<T> T getBean(Class<T> requiredType);

boolean containsBean(String name);

boolean isSingleton(String name);

boolean isPrototype(String name);

Class<?> getType(String name);
```

Danh sách trên là các chữ ký minh họa thường gặp; interface còn có phương thức khác và overload tùy phiên bản Spring. Ý nghĩa chung:

- `getBean(...)` yêu cầu container trả về một bean theo tên hoặc kiểu.
- `containsBean(...)` giúp xác định có bean theo tên hay không.
- `isSingleton(...)` và `isPrototype(...)` truy vấn phạm vi bean.
- `getType(...)` tra cứu kiểu của bean khi container có thể xác định được.

Điểm quan trọng là **`BeanFactory` là interface, không phải tên của một object duy nhất đang chạy trong ứng dụng**. Spring có những implementation cung cấp khả năng lưu bean definitions, dựng bean, resolve dependency và phối hợp các bước xử lý khác.

### 2.1. Ví dụ sử dụng `BeanFactory` trực tiếp

Ta có lớp Java thuần:

```java
package com.example.ioc;

public class GreetingService {

    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Một chương trình có thể tự tạo implementation container và đăng ký bean definition:

```java
package com.example.ioc;

import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.beans.factory.support.RootBeanDefinition;

public class BeanFactoryExample {

    public static void main(String[] args) {
        DefaultListableBeanFactory registry =
                new DefaultListableBeanFactory();

        registry.registerBeanDefinition(
                "greetingService",
                new RootBeanDefinition(GreetingService.class)
        );

        BeanFactory factory = registry;

        GreetingService service =
                factory.getBean("greetingService", GreetingService.class);

        System.out.println(service.greet("Lan"));
    }
}
```

Ở ví dụ này:

1. `DefaultListableBeanFactory` là implementation có khả năng đăng ký và quản lý bean definitions.
2. `RootBeanDefinition` mô tả cách tạo bean `GreetingService`.
3. `BeanFactory` là kiểu interface được dùng để truy cập bean.
4. `getBean(...)` yêu cầu container cung cấp instance.

Không có `@SpringBootApplication`, web server hay Spring Boot auto-configuration trong ví dụ. Nó minh họa cơ chế IoC cơ bản của Spring Framework.

Chúng ta không cần gọi `new GreetingService()` ở nơi sử dụng bean; container thực hiện quá trình tạo theo bean definition. Tuy nhiên, bản thân việc **lập trình cấu hình bean** vẫn phải được thực hiện, ở đây là lệnh `registerBeanDefinition(...)`.

### 2.2. `BeanFactory` không tự quét toàn bộ classpath

Một quan niệm sai là chỉ cần tạo `new DefaultListableBeanFactory()` thì mọi lớp có `@Service` hoặc `@Component` đều được tìm thấy.

Thực tế, container cần **bean definitions**. Khi dùng trực tiếp một `BeanFactory` cơ bản, bạn phải đăng ký chúng hoặc thiết lập rõ các bộ xử lý cần thiết để nạp định nghĩa bean từ annotation, XML hay nguồn khác.

`@Component` là metadata trên class. Sự tồn tại của annotation trong bytecode **không đồng nghĩa** class đã trở thành bean trong một container bất kỳ.

### 2.3. Bean definitions và bean instances khác nhau

**Bean definition** là mô tả cách tạo bean: kiểu, tên, scope, dependency, init method, v.v. **Bean instance** là đối tượng cụ thể được tạo theo định nghĩa đó.

```text
BeanDefinition
    name: greetingService
    class: GreetingService
    scope: singleton
              │
              ▼
       Tạo bean instance
              │
              ▼
       GreetingService@...
```

Với một `DefaultListableBeanFactory` mới được tạo bằng cách thủ công và chưa gọi các bước pre-instantiation, nhiều singleton sẽ chỉ được tạo khi được yêu cầu lần đầu bằng `getBean()`. Điều này thường được gọi là mô hình *lazy retrieval* trong ví dụ dùng BeanFactory trực tiếp.

Tuy nhiên, **không nên biến điều đó thành quy tắc tuyệt đối rằng mọi BeanFactory luôn lazy**. Việc bean được tạo khi nào còn phụ thuộc implementation, cách container được khởi tạo và các bước quản lý lifecycle đã được gọi.

## 3. `ApplicationContext` là gì?

`ApplicationContext` là một interface thuộc Spring Framework:

```java
import org.springframework.context.ApplicationContext;
```

Nó **mở rộng các hợp đồng quản lý bean** và thêm những khả năng phục vụ ứng dụng thực tế: đọc metadata môi trường, tìm resource, cung cấp thông điệp đa ngôn ngữ, phát sự kiện ứng dụng, tổ chức context theo quan hệ cha/con và quản lý quá trình khởi tạo container theo các implementation tương ứng.

Một sơ đồ interface rút gọn:

```text
                        BeanFactory
                             ▲
                ┌────────────┴────────────┐
                │                         │
        HierarchicalBeanFactory    ListableBeanFactory
                ▲                         ▲
                └────────────┬────────────┘
                             │
                     ApplicationContext
                      /     |       \
             Environment  Events    Resources
               & i18n       &       loading
                         lifecycle*
```

Sơ đồ là cách nhìn chức năng, không phải toàn bộ cây kế thừa chính xác của mọi interface. Cụ thể, `ApplicationContext` mở rộng `ListableBeanFactory`, `HierarchicalBeanFactory`, `MessageSource`, `ApplicationEventPublisher`, `ResourcePatternResolver` và `EnvironmentCapable`. Các implementation cấu hình được, chẳng hạn `ConfigurableApplicationContext`, cung cấp thêm hợp đồng `refresh()`, `close()` và lifecycle.

Vì `ApplicationContext` cũng là một `BeanFactory` theo quan hệ interface kế thừa, nên những thao tác như `getBean(...)` vẫn có thể thực hiện trên `ApplicationContext`.

### 3.1. `ApplicationContext` không phải container thứ hai nằm ngoài `BeanFactory`

Trong nhiều implementation Spring, một `ApplicationContext` sử dụng một `BeanFactory` bên trong để thực hiện các nhiệm vụ tạo, tìm và quản lý bean.

Có thể hình dung:

```text
Ứng dụng Spring Boot
        │
        ▼
  ApplicationContext
   ├── Hợp đồng BeanFactory / truy cập bean
   ├── BeanFactory triển khai cơ chế bean bên dưới
   ├── Environment / configuration
   ├── Resource loading
   ├── Events / MessageSource
   └── Startup và shutdown lifecycle
```

Do đó, không nên nói “Spring Boot dùng ApplicationContext nên không dùng BeanFactory”. **ApplicationContext được xây dựng trên các khả năng BeanFactory**. Hai khái niệm mô tả những tầng API liên quan, không nhất thiết là hai danh sách bean độc lập.

### 3.2. Các implementation `ApplicationContext`

Trong mã Spring Framework, bạn có thể gặp:

- `AnnotationConfigApplicationContext`: tạo context từ configuration class và component metadata, phù hợp ví dụ Java độc lập hoặc ứng dụng không phải web.
- `ClassPathXmlApplicationContext`: khởi tạo từ cấu hình XML trên classpath, thường thấy trong tài liệu hoặc hệ thống kế thừa.
- Các loại context cho ứng dụng web: tích hợp với môi trường servlet hoặc reactive.
- Các implementation của Spring Boot phù hợp với kiểu ứng dụng và cấu hình bootstrap.

Bạn thường làm việc với **interface `ApplicationContext`** thay vì phụ thuộc chặt vào implementation cụ thể.

## 4. Ví dụ `ApplicationContext` với Java configuration

Lần này chúng ta không đăng ký bean definition bằng tay như `BeanFactoryExample`. Thay vào đó, dùng `@Configuration` và `@Bean`.

### 4.1. Lớp nghiệp vụ

`src/main/java/com/example/ioc/GreetingService.java`:

```java
package com.example.ioc;

public class GreetingService {

    private final String prefix;

    public GreetingService(String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        return prefix + ", " + name + "!";
    }
}
```

### 4.2. Lớp cấu hình

`src/main/java/com/example/ioc/AppConfig.java`:

```java
package com.example.ioc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AppConfig {

    @Bean
    public GreetingService greetingService() {
        return new GreetingService("Xin chào");
    }
}
```

`@Configuration` đánh dấu lớp là nguồn cấu hình. `@Bean` khai báo một bean tên `greetingService` theo tên phương thức (nếu không chỉ định tên khác).

### 4.3. Khởi tạo và dùng context

`src/main/java/com/example/ioc/ApplicationContextExample.java`:

```java
package com.example.ioc;

import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class ApplicationContextExample {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            ApplicationContext applicationContext = context;

            GreetingService service =
                    applicationContext.getBean(GreetingService.class);

            System.out.println(service.greet("Lan"));
        }
    }
}
```

Kết quả:

```text
Xin chào, Lan!
```

Ở đây:

- `AnnotationConfigApplicationContext` đọc `AppConfig` làm cấu hình.
- `@Bean` được xử lý thành bean definition, rồi bean được tạo và đăng ký theo quy tắc của container.
- `ApplicationContext#getBean(...)` trả bean cần dùng.
- `try-with-resources` đóng context sau khi sử dụng, giúp gọi các bước shutdown phù hợp với bean do context quản lý.

Ví dụ này dùng **Spring Framework** và không bắt buộc có Spring Boot, bởi `ApplicationContext` là khái niệm nền tảng của Spring.

## 5. So sánh `BeanFactory` và `ApplicationContext`

| Tiêu chí | `BeanFactory` | `ApplicationContext` |
|---|---|---|
| Vai trò chính | Giao diện lõi cho IoC/bean management | Giao diện container cấp ứng dụng |
| Quan hệ | Interface nền tảng | Kế thừa các giao diện bean lookup và mở rộng chức năng |
| Lấy bean theo tên/kiểu | Có | Có |
| Container cần bean definitions | Có | Có |
| Tự động quét component | Không được bảo đảm chỉ bởi interface; cần cấu hình hạ tầng | Thường được cấu hình thuận tiện qua các implementation dùng annotation |
| Bean post-processors | Có thể hỗ trợ nếu được đăng ký | Các implementation thông dụng xử lý và đăng ký hạ tầng liên quan trong quá trình refresh |
| Khởi tạo singleton | Với BeanFactory tự tạo, thường tạo khi được yêu cầu nếu chưa pre-instantiate | Thường tạo các non-lazy singleton khi refresh/startup |
| Truy cập môi trường `Environment` | Không phải hợp đồng của `BeanFactory` | Có |
| Tải resource `ResourcePatternResolver` | Không phải hợp đồng của `BeanFactory` | Có |
| Application events | Không phải hợp đồng của `BeanFactory` | Có |
| Internationalization `MessageSource` | Không phải hợp đồng của `BeanFactory` | Có |
| Context hierarchy | Không phải hợp đồng của interface cơ bản | Có khả năng nhận diện context cha; phụ thuộc implementation |
| Dùng trực tiếp trong ứng dụng Spring Boot thông thường | Ít cần | Phổ biến, được Spring Boot tạo khi startup |

Cột “thường” mô tả các implementation được dùng trong thực tế; không nên suy ra **mọi cách triển khai của interface** bắt buộc có cùng lịch tạo bean hoặc hạ tầng annotation.

### 5.1. Phân biệt tính năng lõi và tính năng tiện ích

`BeanFactory` cung cấp những thao tác để làm việc với bean. `ApplicationContext` cho phép sử dụng các thao tác ấy trong một môi trường ứng dụng đã được khởi tạo với nhiều dịch vụ bổ sung.

Ví dụ cùng một API lấy bean có thể xuất hiện ở cả hai:

```java
BeanFactory beanFactory = /* một BeanFactory đã cấu hình */;
GreetingService one = beanFactory.getBean(GreetingService.class);
```

```java
ApplicationContext context = /* một ApplicationContext đã khởi tạo */;
GreetingService two = context.getBean(GreetingService.class);
```

Hai đoạn này minh họa API, **không giả định** `one` và `two` là cùng một instance vì có thể thuộc hai container khác nhau. Nếu cùng một `ApplicationContext` được nhìn qua interface `BeanFactory` và `ApplicationContext`, các lệnh truy cập cùng hệ bean của context ấy.

### 5.2. Khi nào cần biết về `BeanFactory`?

Người viết ứng dụng nghiệp vụ thường không tạo `BeanFactory` thủ công. Khái niệm này hữu ích khi:

- Đọc kiến trúc IoC hoặc source code Spring.
- Hiểu quá trình bean lookup, scopes và bean definitions.
- Làm việc với framework integration cần tùy biến cách đăng ký hoặc khởi tạo bean.
- Phân biệt container infrastructure với dependency injection trong business code.

Khi xây dựng ứng dụng Spring Boot bình thường, thường không cần truy cập `BeanFactory` trực tiếp; chỉ cần khai báo dependency qua constructor và để ApplicationContext cung cấp bean.

## 6. Thời điểm tạo bean: lazy và eager phải hiểu đúng

Giả sử có một bean singleton:

```java
public class StartupProbe {

    public StartupProbe() {
        System.out.println("StartupProbe được tạo");
    }
}
```

### 6.1. BeanFactory thủ công

```java
DefaultListableBeanFactory factory = new DefaultListableBeanFactory();

factory.registerBeanDefinition(
        "startupProbe",
        new RootBeanDefinition(StartupProbe.class)
);

System.out.println("Đã đăng ký định nghĩa");

// Lần đầu yêu cầu bean:
factory.getBean("startupProbe");
```

Trong thiết lập cơ bản này, `StartupProbe` thường được tạo khi gọi `getBean` lần đầu. Container đã biết bean definition nhưng không cần tạo instance ngay lúc đăng ký.

Điều này không có nghĩa `BeanFactory` **không thể** pre-instantiate singleton. Những API và quá trình khởi tạo nâng cao có thể yêu cầu tạo chúng trước.

### 6.2. ApplicationContext khởi tạo qua `refresh()`

```java
@Configuration
public class ProbeConfig {

    @Bean
    public StartupProbe startupProbe() {
        return new StartupProbe();
    }
}
```

```java
try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext(ProbeConfig.class)) {

    System.out.println("Context đã sẵn sàng");
}
```

Trong cấu hình thông thường, constructor `AnnotationConfigApplicationContext(ProbeConfig.class)` đăng ký configuration và refresh context. Các singleton **không đánh dấu lazy** thường được khởi tạo trong refresh, trước khi chương trình in “Context đã sẵn sàng”.

Đây là một lợi ích thực tế: nhiều lỗi tạo bean hoặc thiếu dependency có thể bộc lộ **ngay lúc khởi động**, thay vì đến khi một chức năng được gọi lần đầu.

### 6.3. `@Lazy` thay đổi thời điểm tạo

```java
@Configuration
public class ProbeConfig {

    @Bean
    @Lazy
    public StartupProbe startupProbe() {
        return new StartupProbe();
    }
}
```

Với bean này, container có thể trì hoãn tạo instance cho đến khi bean thực sự được yêu cầu.

Cần lưu ý:

- `@Lazy` không bảo đảm bean không bao giờ được tạo lúc startup; một singleton eager khác có thể yêu cầu bean đó qua dependency.
- Bean scope `prototype` vốn được tạo khi yêu cầu instance, khác với eager singleton.
- Spring Boot còn có những tùy chọn cấu hình lazy initialization ở mức ứng dụng; đừng đánh đồng chúng với chính định nghĩa `BeanFactory` hoặc `ApplicationContext`.

**Sự khác biệt về eager/lazy chủ yếu đến từ cách container khởi tạo và cấu hình bean**, không phải vì hai interface tuyên bố hai quy tắc tuyệt đối đối lập.

## 7. Các khả năng bổ sung của `ApplicationContext`

Các tính năng dưới đây giải thích vì sao Spring Boot thường làm việc với `ApplicationContext` hơn là một `BeanFactory` được tạo thủ công.

### 7.1. `Environment`: đọc thuộc tính cấu hình và profile

`ApplicationContext` cung cấp `getEnvironment()`:

```java
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;

public class ConfigurationReader {

    public static void printPort(ApplicationContext context) {
        Environment environment = context.getEnvironment();

        String port = environment.getProperty(
                "server.port",
                "8080"
        );

        System.out.println("Configured server.port = " + port);
    }
}
```

Trong Spring Boot, `Environment` có thể nhận giá trị từ `application.yml`, profile-specific files, biến môi trường, system properties, command-line arguments và các PropertySources khác theo quy tắc ưu tiên.

Giá trị `8080` trong ví dụ là fallback của **lệnh đọc property**, không phải cách bảo đảm port HTTP thực tế luôn là 8080. Khi web server dùng cổng ngẫu nhiên, cấu hình chuyên biệt hoặc không phải ứng dụng web, port được sử dụng có thể khác.

Với mã nghiệp vụ, thường tốt hơn khi inject cấu hình qua `@ConfigurationProperties` hoặc `@Value`, tránh gọi `context.getEnvironment()` ở khắp nơi.

### 7.2. `Resource`: tìm tài nguyên trên classpath và nơi khác

`ApplicationContext` hỗ trợ đọc resource:

```java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.context.ApplicationContext;
import org.springframework.core.io.Resource;

public class MessageReader {

    public static String read(ApplicationContext context)
            throws Exception {

        Resource resource =
                context.getResource("classpath:messages/welcome.txt");

        try (InputStream input = resource.getInputStream()) {
            return new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            );
        }
    }
}
```

Tệp có thể nằm ở:

```text
src/main/resources/messages/welcome.txt
```

và sau khi đóng gói Spring Boot JAR, nó thường nằm tại:

```text
BOOT-INF/classes/messages/welcome.txt
```

Code dùng `classpath:messages/welcome.txt` vẫn hoạt động vì nó tìm resource qua classpath loader, không yêu cầu một file vật lý trong source tree.

`ApplicationContext` còn hỗ trợ tìm nhiều resource theo pattern thông qua hợp đồng `ResourcePatternResolver` khi cần. Đây là khả năng cấp ứng dụng ngoài các thao tác lookup bean cơ bản.

### 7.3. `ApplicationEventPublisher`: phát sự kiện nội bộ

Context cho phép thành phần ứng dụng phát sự kiện để các listener nhận và xử lý.

Ví dụ một event Java:

```java
package com.example.demo.events;

public record CustomerRegisteredEvent(String customerId) {
}
```

Một service dùng `ApplicationEventPublisher`:

```java
package com.example.demo.service;

import com.example.demo.events.CustomerRegisteredEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class RegistrationService {

    private final ApplicationEventPublisher events;

    public RegistrationService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void register(String customerId) {
        // Ví dụ tối giản: thao tác nghiệp vụ đăng ký được lược bớt.
        events.publishEvent(new CustomerRegisteredEvent(customerId));
    }
}
```

Listener:

```java
package com.example.demo.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class RegistrationListener {

    @EventListener
    public void onRegistered(CustomerRegisteredEvent event) {
        System.out.println(
                "Đã đăng ký khách hàng: " + event.customerId()
        );
    }
}
```

Trong một ứng dụng Spring Boot đã khởi tạo context phù hợp, `@EventListener` được hạ tầng của Spring xử lý và listener nhận event khi event được publish. Event có thể là object Java bình thường, không bắt buộc kế thừa `ApplicationEvent` trong Spring hiện đại.

**Lưu ý:** cơ chế phát sự kiện Spring mặc định thường gọi listener **đồng bộ** theo cấu hình multicaster thông thường. Nó không tự biến event thành message queue, không bảo đảm lưu bền vững qua restart và không cung cấp transaction boundary chỉ vì gọi `publishEvent()`. Muốn asynchronous hoặc durable messaging phải thiết kế và cấu hình riêng.

`BeanFactory` cơ bản không có `publishEvent(...)` trong hợp đồng interface của nó.

### 7.4. `MessageSource`: thông điệp theo ngôn ngữ

Một ứng dụng cần đa ngôn ngữ có thể dùng `MessageSource`, cũng là một hợp đồng mà `ApplicationContext` mở rộng.

Ví dụ:

```java
import java.util.Locale;
import org.springframework.context.ApplicationContext;

public class MessageExample {

    public static String greeting(ApplicationContext context) {
        return context.getMessage(
                "greeting.hello",
                null,
                "Xin chào",
                Locale.forLanguageTag("vi-VN")
        );
    }
}
```

Nếu ứng dụng cấu hình một MessageSource với key `greeting.hello`, Spring lấy thông điệp phù hợp với locale. Nếu không tìm thấy, ví dụ trên sử dụng default message `Xin chào`. Cơ chế cấu hình source và file messages tùy cách dựng context; Spring Boot thường hỗ trợ auto-configuration message bundle theo quy ước khi có nguồn message thích hợp.

Khả năng này không phải nhiệm vụ lookup bean cơ bản của `BeanFactory`.

### 7.5. Context hierarchy

Một số hệ thống có context cha và context con:

```text
Parent ApplicationContext
    ├── sharedService
    └── infrastructureBean
             │
             ▼
Child ApplicationContext
    ├── webController
    └── requestHandler
```

Context con có thể truy cập bean từ context cha theo quy tắc tìm bean và quan hệ hierarchy, trong khi context cha không mặc nhiên nhìn thấy bean chỉ tồn tại ở con.

Đây là cơ chế hữu ích trong một số môi trường web hoặc kiến trúc tích hợp nhiều context. Một ứng dụng Spring Boot đơn giản thường không cần tự tạo hierarchy.

Tránh suy luận “mọi `@SpringBootApplication` tạo nhiều context”. Tùy cách bootstrap, thường chỉ cần một context ứng dụng chính.

## 8. Lifecycle: từ bean definition tới hủy context

Vòng đời tiêu biểu của một `ApplicationContext` dùng annotation configuration có thể hình dung như sau:

```text
Chọn nguồn cấu hình
  (@SpringBootApplication, @Configuration, ...)
                     │
                     ▼
Đăng ký / phân tích bean definitions
                     │
                     ▼
Xử lý các BeanFactoryPostProcessor
  và hạ tầng annotation có liên quan
                     │
                     ▼
Đăng ký BeanPostProcessor
                     │
                     ▼
Tạo các singleton non-lazy và inject dependency
                     │
                     ▼
Khởi tạo bean, callbacks, các hook liên quan
                     │
                     ▼
ApplicationContext sẵn sàng
                     │
                     ▼
Ứng dụng sử dụng bean
                     │
                     ▼
Đóng context
  -> hủy những bean được quản lý phù hợp
```

Thứ tự này là mô hình học tập. Lifecycle thực tế có nhiều bước hơn: đăng ký BeanDefinitionRegistryPostProcessor, thiết lập event multicaster, khởi tạo MessageSource, lifecycle processors, publish context events, server startup và callbacks sau refresh tùy loại context.

### 8.1. `BeanFactoryPostProcessor` và `BeanPostProcessor`

Hai tên gần giống nhưng tác động lên những thứ khác nhau:

| Thành phần | Chủ yếu can thiệp vào | Thời điểm ý tưởng |
|---|---|---|
| `BeanFactoryPostProcessor` | Metadata/bean definitions trước khi các singleton thông thường được tạo | Giai đoạn chuẩn bị container |
| `BeanPostProcessor` | Bean instance trước/sau các bước initialization | Giai đoạn tạo bean |

Ví dụ, Spring sử dụng hạ tầng post-processing để hỗ trợ annotation, proxy và nhiều khả năng tích hợp khác. Khi chỉ tự tạo `DefaultListableBeanFactory`, **không thể giả định** toàn bộ post-processors đã được tìm, đăng ký và chạy tự động.

`ApplicationContext` implementations có quá trình refresh thực hiện nhiều bước hạ tầng này giúp annotation configuration hoạt động như mong đợi.

### 8.2. Hook khởi tạo và hủy bean

Ví dụ dùng `@PostConstruct` và `@PreDestroy` theo Jakarta Annotations trong Spring Boot 3.x:

```java
package com.example.demo.service;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Service;

@Service
public class CacheService {

    @PostConstruct
    public void initialize() {
        System.out.println("CacheService initialized");
    }

    @PreDestroy
    public void shutdown() {
        System.out.println("CacheService shutting down");
    }
}
```

Khi bean được tạo và hạ tầng annotation lifecycle thích hợp được đăng ký, `@PostConstruct` được gọi theo quy trình khởi tạo. Khi context đóng bình thường, Spring có thể gọi callback hủy cho singleton được quản lý.

Trong Spring Boot 3.x, package phổ biến là `jakarta.annotation`; code Spring Boot cũ hơn có thể gặp `javax.annotation`. Hành vi phụ thuộc phiên bản framework/dependencies.

Cần biết thêm:

- Context đóng đúng quy trình là điều kiện quan trọng để các callback hủy có cơ hội chạy.
- Spring không mặc nhiên theo dõi và gọi destruction callback cho từng instance `prototype` sau khi giao cho client.
- Một `BeanFactory` trực tiếp có thể được cấu hình hỗ trợ lifecycle, nhưng cần setup đúng hạ tầng. Không suy ra việc dùng interface `BeanFactory` là “không bao giờ có lifecycle”.

### 8.3. Eager singleton giúp phát hiện lỗi sớm

Nếu bean `PaymentService` yêu cầu `PaymentGateway` nhưng không có bean phù hợp, application context khởi tạo non-lazy singleton thường thất bại ở startup:

```text
UnsatisfiedDependencyException:
No qualifying bean of type '...PaymentGateway' available
```

Vì thế, một ứng dụng có thể **biên dịch thành công** nhưng không khởi động được. Vấn đề là container không dựng được object graph theo bean definitions, khác với lỗi Java compiler không tìm thấy tên class trong mã nguồn.

## 9. Spring Boot sử dụng `ApplicationContext` như thế nào?

Lớp main Spring Boot thường được viết:

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

`SpringApplication.run(...)` xây dựng môi trường chạy, xác định loại context phù hợp, nạp các nguồn cấu hình, áp dụng quá trình khởi tạo Spring Boot và trả về một `ConfigurableApplicationContext` khi thành công.

Có thể lưu lại context được trả về:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(DemoApplication.class, args);

        System.out.println("Beans: " +
                context.getBeanDefinitionCount());
    }
}
```

Đoạn này minh họa cách lấy context sau khi startup. `getBeanDefinitionCount()` thuộc khả năng liệt kê bean definitions của context triển khai; con số phụ thuộc dependencies, auto-configuration, profiles và các bean của ứng dụng.

Trong ứng dụng web thông thường, **không đóng context ngay sau `run(...)`** nếu bạn còn muốn web server tiếp tục phục vụ request. Lúc cần shutdown đúng cách, Spring Boot và môi trường triển khai thường có cơ chế lifecycle/shutdown phù hợp.

### 9.1. Tại sao Spring Boot không cần tự gọi `getBean()` ở mọi nơi?

Vì Spring Boot xây dựng một `ApplicationContext` và xử lý các bean definitions, bạn có thể khai báo constructor injection:

```java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

```java
package com.example.demo.web;

import com.example.demo.service.GreetingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greet")
    public String greet(
            @RequestParam(defaultValue = "Spring") String name
    ) {
        return greetingService.greet(name);
    }
}
```

`@SpringBootApplication` thường kích hoạt component scanning từ package của lớp main và các package con. Nếu hai lớp trên thuộc nhánh package được quét, Spring đăng ký bean definitions tương ứng và tạo `GreetingController` với `GreetingService` được inject.

Như vậy bạn **không cần viết**:

```java
GreetingService service = context.getBean(GreetingService.class);
```

bên trong controller. Container đã cung cấp dependency qua constructor.

### 9.2. Interface `ApplicationContext` và kiểu context cụ thể

Spring Boot có thể tạo context phù hợp với loại ứng dụng:

- Ứng dụng không phải web: một context dựa trên annotation configuration.
- Ứng dụng servlet: context phù hợp với hạ tầng Servlet và web server.
- Ứng dụng reactive: context phù hợp với stack reactive.

Loại cụ thể còn phụ thuộc version Spring Boot và cấu hình. Code nghiệp vụ thường không cần phụ thuộc vào implementation class. Tiêm các interface như `ApplicationContext`, `Environment`, `ApplicationEventPublisher` hoặc tốt hơn là trực tiếp dependency nghiệp vụ, giúp hạn chế ràng buộc không cần thiết.

### 9.3. Auto-configuration tạo thêm bean trong context

`@SpringBootApplication` kết hợp:

- Cấu hình gốc của ứng dụng.
- Component scanning.
- Spring Boot auto-configuration.

Auto-configuration có thể đăng ký thêm bean definitions khi các điều kiện được đáp ứng: classpath có library tương ứng, property được bật hoặc một bean của người dùng chưa tồn tại.

Vì vậy, danh sách bean trong `ApplicationContext` có thể bao gồm **bean của bạn** và **bean hạ tầng do Spring Boot tự cấu hình**. Chúng đều thuộc hệ quản lý của context.

`ApplicationContext` **không tự đồng nghĩa với auto-configuration**. Một `AnnotationConfigApplicationContext` của Spring Framework có thể hoạt động mà không có Spring Boot. Auto-configuration đến từ cơ chế của Spring Boot được kích hoạt và xử lý trên container đó.

## 10. Ba cách làm việc với bean và nên chọn cách nào

### 10.1. Cách thường dùng: constructor injection

```java
@Service
public class InvoiceService {

    private final TaxCalculator taxCalculator;

    public InvoiceService(TaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
    }
}
```

Spring tạo bean và inject `TaxCalculator` phù hợp. Đây là hướng thường nên ưu tiên cho code nghiệp vụ: dependency rõ ràng, dễ kiểm thử bằng Java thuần và tránh lệ thuộc trực tiếp vào API container.

### 10.2. `@Bean` cho đối tượng cần tạo bằng factory method

```java
@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    public java.time.Clock applicationClock() {
        return java.time.Clock.systemUTC();
    }
}
```

Dùng khi object cần cấu hình một lần hoặc class đến từ thư viện không thể đánh dấu `@Component` trực tiếp.

### 10.3. Gọi `getBean()` trực tiếp khi có lý do cụ thể

```java
ApplicationContext context = /* context đã khởi tạo */;
Clock clock = context.getBean(Clock.class);
```

`getBean()` có giá trị trong integration code, diagnostic tools, plugins hoặc nơi việc tìm bean động là một yêu cầu thực sự. Tuy nhiên, nếu một `@Service` liên tục gọi `ApplicationContext#getBean()` để tự tìm các dependency mà nó biết trước, code trở nên khó thấy hợp đồng phụ thuộc.

Khi cần nhiều implementation được lựa chọn động, có thể xem các cơ chế phù hợp như inject `Map<String, Strategy>`, `ObjectProvider<T>` hoặc dùng qualifier; không mặc định phải tự “đi tìm” bean bằng một global context.

### 10.4. Vì sao tránh biến `ApplicationContext` thành global service locator?

Ví dụ nên cân nhắc:

```java
public class OrderService {

    public void createOrder() {
        PaymentGateway gateway =
                GlobalContext.getBean(PaymentGateway.class);
        gateway.charge();
    }
}
```

Ở đoạn này, dependency của `OrderService` không nằm trên constructor; test hoặc người đọc phải biết tới `GlobalContext`. Hướng rõ ràng hơn:

```java
@Service
public class OrderService {

    private final PaymentGateway paymentGateway;

    public OrderService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    public void createOrder() {
        paymentGateway.charge();
    }
}
```

Nhờ constructor injection, Spring vẫn là nơi cấp bean, nhưng code nghiệp vụ ít phụ thuộc API container hơn.

## 11. Bean scopes: container quản lý những gì?

Trong Spring, bean có thể được khai báo theo scope. Hai scope nền tảng là:

- **`singleton`**: theo mặc định, một bean instance cho mỗi bean definition trong một Spring IoC container. Đây không phải *một singleton duy nhất trên toàn JVM* khi có nhiều context.
- **`prototype`**: tạo một instance mới cho mỗi yêu cầu bean tương ứng tới container.

Ví dụ:

```java
@Configuration
public class ScopeConfig {

    @Bean
    public CounterService singletonCounter() {
        return new CounterService();
    }

    @Bean
    @Scope("prototype")
    public CounterService prototypeCounter() {
        return new CounterService();
    }
}
```

Với một context được cấu hình bằng `ScopeConfig`:

```java
CounterService one = context.getBean("singletonCounter", CounterService.class);
CounterService two = context.getBean("singletonCounter", CounterService.class);

System.out.println(one == two); // true trong cùng context
```

```java
CounterService first = context.getBean("prototypeCounter", CounterService.class);
CounterService second = context.getBean("prototypeCounter", CounterService.class);

System.out.println(first == second); // false, hai lần yêu cầu
```

Ví dụ giả định `CounterService` là một class có constructor không tham số hợp lệ. Import `@Configuration`, `@Bean` và `@Scope` từ package tương ứng của Spring.

### 11.1. Prototype inject vào singleton

Một điểm dễ nhầm: nếu một singleton nhận prototype trực tiếp qua constructor, container resolve dependency khi tạo singleton, nên singleton thường giữ **chính instance prototype đã nhận**; không tự tạo instance mới mỗi lần singleton gọi phương thức.

Khi thật sự cần instance prototype mới theo từng lần sử dụng, cân nhắc inject `ObjectProvider<CounterService>` hoặc một factory tương ứng để yêu cầu bean khi cần.

### 11.2. Scope web

Spring Web còn có các scope gắn với HTTP request, session hoặc application tùy môi trường và cấu hình. Một `BeanFactory` cơ bản mới tạo thủ công không mặc nhiên có những request/session scope vì các scope này cần hạ tầng web context.

Với Spring Boot web application, context phù hợp tích hợp với các khả năng của môi trường servlet hoặc reactive. Điều đó giải thích vì sao cùng khái niệm IoC container nhưng số scope và bean infrastructure có thể khác nhau.

## 12. Lỗi thường gặp liên quan đến container

| Triệu chứng | Nguyên nhân cần xét | Hướng xử lý |
|---|---|---|
| `NoSuchBeanDefinitionException` | Không có bean phù hợp với tên/kiểu cần tìm | Kiểm tra component scan, `@Bean`, `@Import`, profile, conditional config |
| `NoUniqueBeanDefinitionException` | Có nhiều bean phù hợp khi chỉ yêu cầu một | Chọn `@Qualifier`, `@Primary` hoặc inject collection phù hợp |
| `UnsatisfiedDependencyException` | Container không giải quyết được dependency khi tạo bean | Xem nguyên nhân `Caused by`: thiếu bean, nhiều bean hoặc bean tạo lỗi |
| `BeanCreationException` | Bean thất bại trong quá trình tạo hoặc initialization | Xem constructor, factory method, init callback và nguyên nhân sâu nhất |
| `BeanCurrentlyInCreationException` | Có thể liên quan vòng phụ thuộc khi container đang tạo bean | Đọc chuỗi dependency, thiết kế lại quan hệ để tránh vòng |
| `NoSuchBeanDefinitionException` khi dùng BeanFactory thủ công | Chưa đăng ký bean definition | Đăng ký class/definition hoặc hạ tầng scan đúng cách |
| `@Autowired` không hoạt động trong object tạo bằng `new` | Object không được Spring quản lý | Để container tạo bean hoặc truyền dependency bằng tay |
| Context khởi động được nhưng controller không xuất hiện | Sai vùng component scan hoặc chưa đăng ký bean | Kiểm tra vị trí lớp main, package và annotation |
| Bean không có khi profile khác | Bean có điều kiện profile hoặc configuration | Kiểm tra active profiles và điều kiện đăng ký |

### 12.1. Đọc lỗi từ container đúng cách

Ví dụ log:

```text
Parameter 0 of constructor in com.example.demo.OrderService
required a bean of type 'com.example.demo.PaymentGateway'
that could not be found.
```

Lỗi này có nghĩa Spring **không có bean `PaymentGateway` phù hợp** để dựng `OrderService`. Nó không có nghĩa Java compiler không tìm thấy class `PaymentGateway`. Nếu không biết type này, Java đã có thể thất bại ở giai đoạn biên dịch.

Cần kiểm tra:

1. `PaymentGateway` là interface hay class?
2. Có implementation được đánh dấu `@Component`/`@Service` hoặc phương thức `@Bean` cung cấp nó không?
3. Lớp cấu hình/implementation có nằm trong vùng scan hoặc đã được import không?
4. Có `@Profile` hoặc `@Conditional` khiến bean không được đăng ký không?
5. Có nhiều context và bean nằm ở context khác không?

Thêm `@Autowired` vào một field không thể thay thế bước đăng ký bean còn thiếu.

### 12.2. Lỗi xuất hiện trong startup hay khi gọi lần đầu?

Với các singleton non-lazy, một `ApplicationContext` thông dụng sẽ dựng chúng khi refresh, nên lỗi phụ thuộc có thể bộc lộ trong startup.

Với bean đánh dấu `@Lazy` hoặc `prototype`, có những lỗi chỉ xảy ra **khi bean thực sự được yêu cầu**. Điều này giải thích vì sao ứng dụng có thể in log “Started ...” nhưng một chức năng vẫn thất bại khi chạm tới bean chưa được khởi tạo trước đó.

## 13. Phân biệt `BeanFactory` và `FactoryBean`

Hai tên này gần giống nhau nhưng nói về hai thứ khác nhau:

- **`BeanFactory`** là interface đại diện cho container cung cấp bean.
- **`FactoryBean<T>`** là một interface mà một **bean chuyên biệt** có thể triển khai để Spring biết cách tạo một object khác.

Ví dụ trong Spring, các factory bean có thể được dùng khi việc tạo object phức tạp và cần tích hợp chặt với bean lifecycle.

Với bean tên `sampleFactory` là một `FactoryBean`, tra cứu theo tên thông thường có thể trả về **sản phẩm** do factory tạo; tiền tố `&` trong tên bean có thể được dùng để yêu cầu chính **factory object**:

```java
Object product = context.getBean("sampleFactory");
Object factoryObject = context.getBean("&sampleFactory");
```

Đây là tính năng nâng cao của Spring container. Bạn không cần triển khai `FactoryBean` khi chỉ muốn dùng một phương thức `@Bean` thông thường. Việc phân biệt tên giúp tránh nhầm rằng `BeanFactory` và `FactoryBean` là hai cách viết của một interface.

## 14. Thực hành trong Spring Boot Fundamentals

Các bài tập dưới đây giúp quan sát trực tiếp sự khác nhau mà không cần hệ thống phức tạp.

### Bài 1: Dùng `BeanFactory` độc lập

Tạo `GreetingService` không có annotation Spring và có constructor không tham số. Tạo `DefaultListableBeanFactory`, đăng ký `RootBeanDefinition`, rồi lấy bean qua interface `BeanFactory`.

Quan sát rằng bạn **tự chọn** cách đăng ký bean definition; container không cần scan toàn bộ project.

### Bài 2: Chuyển sang `ApplicationContext`

Tạo `@Configuration` với `@Bean GreetingService`, khởi tạo `AnnotationConfigApplicationContext` và lấy bean. Dùng `try-with-resources` để đóng context.

Giải thích tại sao bạn không cần tự gọi `registerBeanDefinition(...)` cho mỗi `@Bean`: hạ tầng annotation configuration của context đã xử lý metadata.

### Bài 3: Quan sát eager và lazy

Tạo bean in một dòng trong constructor, khởi tạo `AnnotationConfigApplicationContext` và xem thời điểm dòng được in. Sau đó thêm `@Lazy` vào bean và so sánh.

Chú ý bảo đảm bean không bị một eager singleton khác yêu cầu ngay khi startup; nếu có dependency như vậy thì `@Lazy` có thể không tạo ra khác biệt thời điểm bạn dự kiến.

### Bài 4: Quan sát constructor injection

Tạo hai lớp `MessageFormatter` và `GreetingService`, để `GreetingService` yêu cầu `MessageFormatter` qua constructor. Đăng ký chúng thành bean bằng `@Component`/`@Service` hoặc `@Bean`, rồi để Spring Boot tạo controller cần `GreetingService`.

Sau đó thử tạo một object nghiệp vụ bằng `new` ở ngoài container và so sánh trách nhiệm phải tự cung cấp dependency.

### Bài 5: Đọc `Environment` và resource

Đặt một property trong `application.yml` và tệp `messages/welcome.txt` trong `src/main/resources`. Inject `ApplicationContext` vào một `CommandLineRunner` hoặc sử dụng `Environment`/`Resource` trực tiếp, rồi đọc property và resource khi startup.

Giải thích tại sao đây là những dịch vụ mở rộng của `ApplicationContext`, ngoài nhu cầu tạo một `GreetingService`.

### Bài 6: Phát sự kiện nội bộ

Tạo một `CustomerRegisteredEvent`, một listener với `@EventListener` và gọi `publishEvent(...)` từ service được Spring quản lý. Quan sát listener được gọi trong context đã khởi tạo.

Thử phân biệt việc phát event trong một ứng dụng đang chạy với việc gửi message vào một hàng đợi bền vững: event nội bộ không tự cung cấp các bảo đảm lưu trữ hoặc xử lý lại.

## 15. Những điểm cần ghi nhớ khi đọc source Spring Boot

Để không bị nhầm giữa hai interface, hãy nhìn chúng theo tầng trách nhiệm:

```text
Business code
    │
    ├── Constructor injection
    ├── @Service / @Repository / @Controller
    └── @Bean / @Configuration
                │
                ▼
        ApplicationContext
    ├── Giao diện truy cập bean
    ├── Xử lý cấu hình và lifecycle
    ├── Environment / resources
    ├── Events / MessageSource
    └── Hạ tầng Spring Boot bổ sung
                │
                ▼
        BeanFactory implementation
    ├── Bean definitions
    ├── Tạo và tìm bean
    ├── Resolve dependencies
    └── Scope và phần lõi bean lifecycle
```

**`BeanFactory`** là nền tảng để container cung cấp bean. **`ApplicationContext`** là giao diện container cấp ứng dụng, kế thừa khả năng đó và mở rộng bằng những dịch vụ mà một ứng dụng Spring thường cần. Spring Boot dùng một `ApplicationContext` phù hợp khi khởi chạy, nhưng các hoạt động tạo và quản lý bean vẫn dựa trên cơ chế BeanFactory.

Khi viết mã nghiệp vụ, hãy ưu tiên **constructor injection** và định nghĩa bean rõ ràng. Khi đọc tài liệu hoặc chẩn đoán lỗi khởi động, hãy nhớ rằng `ApplicationContext` chịu trách nhiệm phối hợp nhiều giai đoạn cấu hình và lifecycle; bản thân bean lookup chỉ là một phần trong toàn bộ hoạt động của IoC container.
