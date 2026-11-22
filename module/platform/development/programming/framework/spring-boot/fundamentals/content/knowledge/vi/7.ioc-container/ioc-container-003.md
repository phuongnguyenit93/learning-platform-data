# Bean là đối tượng được container quản lý như thế nào?

Trong Java, bạn có thể tự tạo một đối tượng bằng `new` rồi gọi phương thức của nó. Trong Spring Boot, một cách phổ biến hơn là khai báo những thành phần cần thiết và để **Spring IoC container** tạo, lắp ghép, cấu hình và quản lý vòng đời của chúng. Một đối tượng được container quản lý như vậy gọi là **Spring bean**.

Câu “bean là đối tượng do Spring quản lý” chỉ có ý nghĩa khi hiểu được **Spring đang quản lý điều gì**: đăng ký định nghĩa bean, quyết định thời điểm tạo đối tượng, chọn dependency để truyền vào, kiểm soát phạm vi tồn tại, áp dụng các xử lý bổ sung như proxy và gọi callback vòng đời. Những việc này có hệ quả trực tiếp đến cách viết service, controller và cấu hình của một ứng dụng Spring Boot.

## 1. Bean vẫn là một đối tượng Java

Xét một lớp Java thuần:

```java
public class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name;
    }
}
```

Bạn hoàn toàn có thể tự tạo nó:

```java
GreetingService service = new GreetingService();
System.out.println(service.greet("An"));
```

Đây là **đối tượng Java bình thường**. Để dùng nó, mã gọi phải biết cách khởi tạo và tự quyết định ai giữ tham chiếu đến đối tượng. Bản thân câu lệnh `new GreetingService()` không đăng ký đối tượng với Spring.

Nếu đăng ký lớp thành bean:

```java
import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name;
    }
}
```

và lớp nằm trong phạm vi component scanning, Spring có thể tìm thấy định nghĩa này, tạo instance và cung cấp instance đó cho những bean khác cần `GreetingService`.

**Điểm phân biệt không nằm ở cú pháp của lớp.** Cùng một lớp `GreetingService` có thể có một instance do bạn tự tạo bằng `new` và một instance do Spring quản lý. Đối tượng tạo bằng `new` **không tự trở thành bean** chỉ vì trên lớp có annotation `@Service`.

| Câu hỏi | Đối tượng tự tạo bằng `new` | Spring bean |
|---|---|---|
| Ai quyết định khởi tạo? | Mã Java gọi constructor. | Spring container dựa trên bean definition và scope; bên trong factory method vẫn có thể dùng `new`. |
| Ai truyền dependency? | Chính mã gọi tự truyền. | Container giải quyết và inject dependency theo cấu hình. |
| Ai quyết định giữ/tái sử dụng instance? | Người viết chương trình. | Container và scope của bean. |
| Ai gọi callback vòng đời Spring? | Không tự có; người viết mã tự xử lý nếu muốn. | Container áp dụng cơ chế lifecycle đối với instance được quản lý. |
| Có thể được Spring AOP/proxy tự động áp dụng? | Không tự động chỉ nhờ `new`. | Có thể, khi bean thỏa điều kiện và cấu hình proxy phù hợp. |

Spring không “đổi bản chất” của Java object. Bean vẫn có field, method, constructor và chịu các quy tắc Java. Điểm khác là **container nắm quyền điều phối việc sử dụng đối tượng**.

## 2. IoC là đảo ngược quyền kiểm soát việc ghép đối tượng

**IoC** (*Inversion of Control*) diễn tả sự thay đổi nơi quyết định cách một đối tượng được tạo và kết nối với các đối tượng khác.

Nếu tự ghép đối tượng:

```java
public class OrderService {
    private final EmailNotifier notifier;

    public OrderService() {
        this.notifier = new EmailNotifier();
    }

    public void placeOrder() {
        // Thực hiện logic tạo đơn hàng...
        notifier.send("Đơn hàng đã được tạo");
    }
}
```

`OrderService` quyết định luôn implementation `EmailNotifier` và cách tạo nó. Điều này khiến lớp khó thay thế notifier khi test hoặc khi chuyển sang cách gửi thông báo khác.

Dùng dependency injection:

```java
public interface Notifier {
    void send(String message);
}

public class OrderService {
    private final Notifier notifier;

    public OrderService(Notifier notifier) {
        this.notifier = notifier;
    }

    public void placeOrder() {
        // Thực hiện logic tạo đơn hàng...
        notifier.send("Đơn hàng đã được tạo");
    }
}
```

`OrderService` chỉ nói rằng nó **cần một `Notifier`**, còn bên ngoài quyết định cung cấp implementation nào. Đây là **Dependency Injection (DI)**, một kỹ thuật phổ biến để thực hiện IoC.

Spring IoC container đóng vai trò “bên ngoài” ấy: nhìn vào các bean definition, chọn dependency phù hợp và gọi constructor hoặc factory method để lắp ghép. Spring cũng quản lý thêm lifecycle, scope, metadata và các phần mở rộng khác, nên **IoC container rộng hơn việc tự động truyền tham số constructor**.

Một hình dung về hướng điều phối:

```text
Không dùng container:

main() ── new EmailNotifier() ──> new OrderService(notifier)
   │                                     │
   └────────────── giữ tham chiếu ──────┘

Dùng Spring container:

Cấu hình/component scan ──> Bean definitions
                                   │
                                   ▼
                            Spring container
                             /           \
                  Notifier bean       OrderService bean
                             \           /
                              inject dependency
```

## 3. Container là gì: BeanFactory và ApplicationContext

Spring Framework định nghĩa hai khái niệm nền tảng:

- **`BeanFactory`**: giao diện lõi để truy cập và quản lý các bean.
- **`ApplicationContext`**: mở rộng `BeanFactory` với nhiều khả năng ứng dụng như event publication, xử lý resource, tích hợp environment và những tiện ích khác.

Trong Spring Boot, lập trình viên thường làm việc với **`ApplicationContext`**. Khi gọi `SpringApplication.run(...)`, Boot tạo hoặc chọn loại application context phù hợp, chuẩn bị environment, nạp bean definitions, làm mới context và khởi tạo những thành phần cần thiết.

Ví dụ điểm vào:

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

Đối tượng được quản lý không phải chỉ nằm trong một “danh sách Java object” đơn giản. Container còn giữ **metadata để biết tạo đối tượng nào, phụ thuộc ai, scope nào và phải áp dụng bước xử lý nào**.

Có thể diễn đạt ngắn gọn:

```text
ApplicationContext
├── Bean definitions (mô tả cách tạo và quản lý bean)
├── Dependency resolution (chọn và inject phụ thuộc)
├── Scope/lifecycle (lúc tạo, giữ lại, kết thúc)
├── BeanPostProcessor và các extension points
├── Environment, resources, events...
└── Các instance/proxy được tạo theo scope
```

Không nhất thiết mỗi bean definition luôn tương ứng với một instance đang tồn tại. Một bean singleton mặc định có thể được tạo khi context khởi động; bean `@Lazy` có thể được trì hoãn; bean prototype tạo mới theo từng lần container được yêu cầu; scoped bean web có vòng đời riêng.

## 4. Trước khi có bean phải có bean definition

Container cần biết **những gì được phép tạo**. Thông tin đăng ký này thường gọi là **bean definition**: tên, kiểu hoặc thông tin tạo đối tượng, scope, điều kiện khởi tạo, metadata autowiring và các thuộc tính vòng đời.

Các nguồn đăng ký phổ biến trong Spring Boot:

1. **Component scanning**: tìm lớp được đánh dấu bằng `@Component` hoặc stereotype tương ứng.
2. **Phương thức `@Bean`**: khai báo một đối tượng được tạo qua factory method.
3. **Import và configuration**: nạp thêm cấu hình/định nghĩa bean theo các cơ chế của Spring.
4. **Spring Boot auto-configuration**: đăng ký bean dựa trên những thư viện, bean và property đang có, nếu điều kiện phù hợp.
5. **Đăng ký lập trình**: hạ tầng có thể đăng ký definition hoặc singleton theo API container, thường gặp ở framework/library hơn ứng dụng cơ bản.

### Component scanning

Một service đơn giản:

```java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

`@Service` là annotation chuyên biệt hóa `@Component`. Nó làm rõ **vai trò nghiệp vụ** cho người đọc, đồng thời là ứng viên cho component scan.

Các stereotype quen thuộc:

| Annotation | Thông điệp chính | Có thể trở thành bean khi được scan? |
|---|---|---|
| `@Component` | Thành phần Spring tổng quát. | Có. |
| `@Service` | Thành phần chứa logic ứng dụng/nghiệp vụ. | Có. |
| `@Repository` | Thành phần tầng truy cập dữ liệu. | Có; còn có tích hợp xử lý exception khi được cấu hình phù hợp. |
| `@Controller` | Controller của web MVC. | Có. |
| `@RestController` | Controller web trả response body theo cơ chế REST/controller. | Có; kết hợp ý nghĩa của `@Controller` và `@ResponseBody`. |
| `@Configuration` | Lớp khai báo cấu hình, thường chứa phương thức `@Bean`. | Có, khi được nạp qua scanning/import phù hợp. |

**Annotation một mình chưa đảm bảo bean được đăng ký.** Spring phải thực sự quét hoặc import cấu hình chứa lớp đó. Một service đặt ngoài package scan mặc định có thể không được tìm thấy.

`@SpringBootApplication` bao gồm component scanning theo các quy ước của Boot. Mặc định, phạm vi quét bắt đầu từ package của lớp main/configuration và các package con. Chẳng hạn:

```text
com.example.demo/
├── DemoApplication.java       # @SpringBootApplication
├── controller/
│   └── GreetingController.java
└── service/
    └── GreetingService.java
```

Hai lớp trong `controller` và `service` nằm trong package con của `com.example.demo` nên thường được scan. Một lớp ở `com.other.service` không tự lọt vào phạm vi đó.

### Bean definition có thể bị điều kiện chặn

Spring Boot auto-configuration thường dùng các điều kiện như:

- Có hoặc không có một class cụ thể trên classpath.
- Có hoặc chưa có một bean với kiểu/tên phù hợp.
- Property cấu hình có giá trị được yêu cầu.
- Loại ứng dụng hoặc môi trường runtime phù hợp.

Ví dụ, Boot có thể tự khai báo thành phần mặc định **chỉ khi ứng dụng chưa cung cấp bean thay thế**. Vì vậy, câu “có starter là có bean X” luôn cần xét điều kiện thực tế.

## 5. Hai cách khai báo bean thường gặp

### Cách A — đánh dấu lớp của ứng dụng bằng stereotype

```java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class PriceService {
    public long calculate(long unitPrice, int quantity) {
        return unitPrice * quantity;
    }
}
```

Khi component scan tìm thấy lớp này, Spring đăng ký bean definition và dùng constructor phù hợp để tạo instance. Đây thường là cách tự nhiên cho service/controller/repository của ứng dụng.

### Cách B — dùng factory method `@Bean`

Đôi khi bạn không sở hữu mã nguồn của class, hoặc cần điều khiển rõ cách khởi tạo. Ví dụ đăng ký `java.time.Clock`:

```java
package com.example.demo.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {

    @Bean
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

Lớp `Clock` thuộc JDK và không có `@Component`. Phương thức `appClock()` nói với container cách tạo đối tượng. Kết quả là **`Clock` được quản lý như bean** khi cấu hình này được nạp.

Ở cả hai cách, dữ liệu runtime cuối cùng có thể là đối tượng Java thông thường hoặc **proxy** do hạ tầng tạo ra; điểm chung là container quản lý việc cấp phát/truy cập theo bean definition.

| Trường hợp | Thường chọn |
|---|---|
| Class do bạn viết và có vai trò service/controller/repository | `@Service`, `@Controller`, `@Repository`... |
| Class thuộc thư viện/JDK không sửa được annotation | `@Bean` trong lớp cấu hình. |
| Cần constructor tùy chỉnh, chọn implementation theo cấu hình | `@Bean` có tham số hoặc logic factory thích hợp. |
| Cần đưa một object đã được thư viện tạo ra vào container | Đăng ký bean thông qua cấu hình/hạ tầng tương ứng. |

## 6. Một ví dụ Spring Boot đầy đủ: container lắp ghép các bean

Giả sử dự án có package gốc `com.example.demo` và starter web MVC tương ứng với dòng Boot đang dùng. Mục tiêu là tạo endpoint trả về thời gian hiện tại theo UTC.

**File 1: `DemoApplication.java`**

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

**File 2: `config/TimeConfiguration.java`**

```java
package com.example.demo.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {
    @Bean
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

**File 3: `service/TimeService.java`**

```java
package com.example.demo.service;

import java.time.Clock;
import java.time.Instant;
import org.springframework.stereotype.Service;

@Service
public class TimeService {
    private final Clock clock;

    public TimeService(Clock clock) {
        this.clock = clock;
    }

    public Instant now() {
        return Instant.now(clock);
    }
}
```

**File 4: `controller/TimeController.java`**

```java
package com.example.demo.controller;

import com.example.demo.service.TimeService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TimeController {
    private final TimeService timeService;

    public TimeController(TimeService timeService) {
        this.timeService = timeService;
    }

    @GetMapping("/time")
    public String currentTime() {
        return timeService.now().toString();
    }
}
```

Spring xử lý các quan hệ theo ý tưởng:

```text
Bean definition TimeConfiguration
           │ @Bean
           ▼
        Clock bean
           │ constructor dependency
           ▼
     TimeService bean
           │ constructor dependency
           ▼
    TimeController bean
           │ Spring MVC mapping
           ▼
       GET /time
```

Người viết code không cần có đoạn `new TimeController(new TimeService(Clock.systemUTC()))` trong `main()`. Container biết cách tạo và liên kết dựa trên các bean definition. Với ứng dụng Spring MVC đang chạy, HTTP request `GET /time` được chuyển đến controller.

**Tính test được cải thiện:** vì `TimeService` nhận một `Clock` qua constructor, test thuần Java có thể tạo `Clock.fixed(...)` và kiểm tra kết quả thời gian cố định mà không cần chạy toàn bộ Spring Boot context.

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixed = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneOffset.UTC
);
TimeService service = new TimeService(fixed);
System.out.println(service.now()); // 2026-01-01T00:00:00Z
```

Đoạn minh họa này nằm trong context có thể truy cập `TimeService`; khi đặt ở file Java riêng, cần thêm import package tương ứng. **Một đối tượng được phép dùng ngoài Spring trong unit test** dù tại runtime ứng dụng nó được khai báo thành bean.

## 7. Spring tìm dependency bằng cách nào?

Khi khởi tạo `TimeService`, Spring thấy constructor cần một `Clock`. Container tra cứu bean có thể đáp ứng dependency đó. Nếu tìm được ứng viên phù hợp, Spring truyền instance tương ứng vào constructor.

Đây là **constructor injection**, thường được ưu tiên vì dependency hiển thị rõ ràng, dễ test và có thể giữ ở field `final`.

### Có cần `@Autowired` cho constructor?

Với lớp chỉ có **một constructor**, Spring hiện đại có thể dùng constructor đó để inject dependency mà **không cần** `@Autowired`.

```java
@Service
public class AuditService {
    private final EventPublisher publisher;

    public AuditService(EventPublisher publisher) {
        this.publisher = publisher;
    }
}
```

Đoạn này giả định `EventPublisher` là một kiểu đã khai báo và container có bean tương ứng. Nếu có nhiều constructor hoặc cần chỉ định điểm injection đặc biệt, quy tắc chọn constructor phải được xét cụ thể; `@Autowired` có thể cần thiết.

Spring cũng hỗ trợ injection qua setter và field, nhưng field injection làm dependency ít rõ ràng khi tạo đối tượng trong unit test và khó thiết lập tính bất biến. Trong code nghiệp vụ mới, constructor injection thường dễ hiểu và bảo trì hơn.

### Nếu có hai bean cùng một interface?

Ví dụ:

```java
public interface MessageSender {
    void send(String text);
}
```

Hai implementation:

```java
import org.springframework.stereotype.Component;

@Component("emailSender")
public class EmailSender implements MessageSender {
    @Override
    public void send(String text) {
        // Gửi email...
    }
}

@Component("smsSender")
public class SmsSender implements MessageSender {
    @Override
    public void send(String text) {
        // Gửi SMS...
    }
}
```

Nếu một constructor chỉ yêu cầu `MessageSender` mà không có thông tin phân giải, Spring có thể báo **nhiều bean phù hợp**. Có thể chọn rõ bằng `@Qualifier`:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    private final MessageSender sender;

    public NotificationService(
            @Qualifier("emailSender") MessageSender sender) {
        this.sender = sender;
    }
}
```

`@Primary` là lựa chọn khác: chỉ định một bean làm ứng viên mặc định khi có nhiều bean phù hợp. Quy tắc lựa chọn còn có thể liên quan tên tham số, generic, qualifier hoặc metadata khác, nên tốt nhất nêu rõ ý định khi có nhiều implementation.

**Tên bean** và **kiểu bean** là hai thuộc tính khác nhau. Trong ví dụ, bean có tên `emailSender` và kiểu có thể gán cho `EmailSender`/**`MessageSender`**. Không nên nhầm tên Java class với tên bean; Spring có quy tắc đặt tên mặc định nhưng vẫn cho phép ghi đè tên qua cấu hình.

## 8. Scope quyết định bean tồn tại và được tái sử dụng ra sao

**Scope** trả lời câu hỏi: container trả cùng một instance hay tạo/định vị instance khác khi bean được yêu cầu?

| Scope | Hành vi cơ bản | Tình huống thường gặp |
|---|---|---|
| **singleton** (mặc định) | Một instance được container quản lý cho mỗi bean definition trong một Spring container. | Service stateless, configuration/service infrastructure. |
| **prototype** | Container tạo instance mới cho mỗi lần yêu cầu bean từ container. | Đối tượng có trạng thái cần tạo theo lần yêu cầu đặc biệt. |
| **request** | Một instance gắn với một HTTP request trong web-aware context. | Dữ liệu sống đúng vòng đời request. |
| **session** | Một instance gắn với một HTTP session. | Trạng thái riêng cho phiên người dùng trong ứng dụng web. |
| **application** | Bean gắn với `ServletContext` trong ứng dụng web phù hợp. | Trạng thái ứng dụng ở phạm vi servlet application. |
| **websocket** | Phạm vi theo WebSocket session trong hạ tầng hỗ trợ. | Trạng thái cho một kết nối WebSocket. |

Các scope web cần môi trường web phù hợp. Không thể mặc định bean `request` hoạt động trong một chương trình command-line không có request đang active.

### Singleton của Spring không phải singleton của cả JVM

Khái niệm **singleton trong Spring** áp dụng trong phạm vi **một bean definition thuộc một container**. Nó không tương đương với Java/GoF Singleton pattern phải đảm bảo chỉ có một đối tượng cho toàn bộ tiến trình JVM.

Giả sử hai `ApplicationContext` độc lập đều đăng ký bean `PriceService` dạng singleton. Mỗi context có thể giữ một instance riêng. Tương tự, hai bean definition khác nhau của cùng một Java class có thể tạo ra hai instance.

Trong một context thông thường:

```java
PriceService first = context.getBean(PriceService.class);
PriceService second = context.getBean(PriceService.class);

System.out.println(first == second); // true nếu bean singleton được trả trực tiếp
```

Đoạn trên giả định context chỉ có **một** bean phù hợp với `PriceService`. Nếu Spring trả proxy singleton, hai lần lookup thường vẫn trả cùng proxy theo scope; **không** nên kết luận hai lần gọi method tương ứng với chỉ một đối tượng nghiệp vụ phía sau mọi dạng scoped proxy.

### Bean singleton có tự động thread-safe?

**Không.** Container quản lý số lượng instance, nhưng không biến mọi field mutable thành an toàn cho truy cập đồng thời.

Ví dụ service có trạng thái dùng chung không phù hợp cho nhiều HTTP request:

```java
@Service
public class CounterService {
    private int count;

    public int next() {
        return ++count; // Có data race khi nhiều thread cùng gọi
    }
}
```

Với singleton web service, nhiều request có thể gọi `next()` đồng thời. Nếu thực sự cần counter trong một JVM, có thể dùng `AtomicInteger`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class CounterService {
    private final AtomicInteger count = new AtomicInteger();

    public int next() {
        return count.incrementAndGet();
    }
}
```

Đây chỉ đảm bảo đếm an toàn trong phạm vi instance JVM tương ứng; không tạo counter dùng chung giữa nhiều instance Spring Boot trên các máy khác nhau. Với trạng thái ứng dụng phân tán cần kho lưu trữ/dịch vụ điều phối phù hợp.

**Thực hành phổ biến:** viết singleton service theo hướng stateless, giữ state nghiệp vụ trong database/cache hoặc trong biến cục bộ của lời gọi, và sử dụng đồng bộ hóa đúng chỗ khi cần shared mutable state.

## 9. Scope prototype: tạo mới không có nghĩa thay đổi ở mọi nơi

Ví dụ bean prototype:

```java
import java.util.UUID;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class ReportDraft {
    private final UUID id = UUID.randomUUID();

    public UUID id() {
        return id;
    }
}
```

Mỗi lần container được yêu cầu cấp một `ReportDraft` prototype, nó thường tạo một instance mới:

```java
ReportDraft a = context.getBean(ReportDraft.class);
ReportDraft b = context.getBean(ReportDraft.class);
// a != b
```

Tuy nhiên, nếu bạn **inject một prototype trực tiếp vào constructor của một singleton**, container sẽ lấy prototype khi tạo singleton. Singleton giữ tham chiếu đến instance đó; **không có prototype mới tự động cho mỗi lần gọi method**.

Muốn lấy instance mới theo nhu cầu, có thể dùng `ObjectProvider<T>`:

```java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ObjectProvider<ReportDraft> drafts;

    public ReportService(ObjectProvider<ReportDraft> drafts) {
        this.drafts = drafts;
    }

    public String newDraftId() {
        return drafts.getObject().id().toString();
    }
}
```

Mỗi lần gọi `getObject()`, provider yêu cầu container cấp bean theo scope đã khai báo. Đây là một cách dùng lookup theo nhu cầu mà không phải đưa trực tiếp `ApplicationContext` vào service.

**Lưu ý vòng đời:** Spring khởi tạo prototype và thực hiện các callback khởi tạo khi tạo bean, nhưng container thường **không tự gọi callback hủy cho từng prototype** sau khi đã trao instance cho bên sử dụng. Nếu prototype sở hữu tài nguyên cần đóng, mã sử dụng phải quản lý việc giải phóng theo thiết kế.

## 10. Bean request và session: lúc nào cần proxy?

Bean gắn với HTTP request không nên được giữ trực tiếp như một instance cố định suốt đời một singleton service. Có thể dùng **scoped proxy** hoặc provider để container tìm đúng đối tượng theo request hiện hành.

Ví dụ với Spring MVC, một request-scoped bean:

```java
package com.example.demo.web;

import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestTrace {
    private final String traceId = UUID.randomUUID().toString();

    public String traceId() {
        return traceId;
    }
}
```

`@RequestScope` là annotation chuyên dụng cho request scope, mặc định dùng scoped proxy theo cơ chế của Spring. Singleton service có thể nhận một proxy của `RequestTrace`, còn đối tượng thực tế phía sau proxy được tra theo request hiện tại.

```text
Singleton service
       │ giữ tham chiếu
       ▼
RequestTrace scoped proxy
       │ lời gọi trong request A
       ├──> RequestTrace instance A
       │ lời gọi trong request B
       └──> RequestTrace instance B
```

Nếu gọi method cần request scope khi **không có HTTP request đang active** (chẳng hạn từ một thread nền không có request context), container có thể báo lỗi scope không active. Request-scoped bean không phải cơ chế truyền trạng thái tùy ý sang thread mới.

WebFlux và các mô hình reactive có ngữ cảnh thực thi khác servlet thread-local, nên khi dùng reactive stack phải chọn cơ chế truyền context phù hợp; không áp nguyên mẫu request scope của servlet cho mọi loại ứng dụng.

## 11. Vòng đời của một bean: từ định nghĩa đến kết thúc

Với một bean singleton thông thường được tạo khi application context khởi động, có thể hình dung thứ tự rút gọn:

```text
1. Đăng ký bean definition
         │
2. Quyết định cần tạo bean (eager/lazy/scope)
         │
3. Khởi tạo instance (constructor/factory method)
         │
4. Gắn dependency, inject các property cần thiết
         │
5. Gọi các aware callbacks và BeanPostProcessor trước init
         │
6. Callback khởi tạo (@PostConstruct, afterPropertiesSet, initMethod...)
         │
7. BeanPostProcessor sau init; có thể trả về proxy
         │
8. Bean sẵn sàng được các thành phần khác sử dụng
         │
9. Context đóng → callback hủy cho bean có lifecycle phù hợp
```

Đây là **mô hình đơn giản hóa**. Các extension point như bean factory post-processing, bean post-processing, circular reference handling và cơ chế tạo proxy có thể khiến trình tự quan sát thực tế phức tạp hơn. Không nên dùng sơ đồ này để dự đoán chính xác mọi thứ tự log giữa hàng trăm bean.

### Ví dụ lifecycle callback

Trong Spring Boot 3+ dùng Jakarta annotations:

```java
package com.example.demo.service;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class ResourceMonitor {

    @PostConstruct
    public void start() {
        System.out.println("ResourceMonitor: initialized");
    }

    @PreDestroy
    public void stop() {
        System.out.println("ResourceMonitor: destroying");
    }
}
```

- `@PostConstruct` được gọi trong giai đoạn khởi tạo bean, sau khi container đã inject dependency liên quan.
- `@PreDestroy` thường được gọi khi container hủy bean singleton lúc context shutdown bình thường, nếu lifecycle tương ứng được hỗ trợ.
- Nếu ứng dụng bị hệ điều hành cưỡng bức dừng, ví dụ kill không cho shutdown hoặc crash, **không thể đảm bảo callback hủy chạy**.

Không nên đặt toàn bộ công việc chạy nền hoặc xử lý lâu trong `@PostConstruct`. Lúc đó application context có thể chưa hoàn tất mọi bước startup; một số cơ chế proxy/event/listener chưa ở trạng thái mà bạn dự kiến. Với công việc cần chạy sau application startup, tìm hiểu `ApplicationRunner`, `CommandLineRunner` và application events tương ứng.

### Còn `InitializingBean` và `DisposableBean`?

Spring cũng hỗ trợ callback qua interface `InitializingBean`/`DisposableBean` và `initMethod`/`destroyMethod` trong cấu hình `@Bean`. Đây là những lựa chọn khác nhau cho việc khởi tạo và dọn tài nguyên; không cần kết hợp tất cả chỉ để một bean hoạt động.

Ví dụ đăng ký một đối tượng Java có method đóng tài nguyên:

```java
@Configuration
public class ClientConfiguration {

    @Bean(destroyMethod = "close")
    public MyClient myClient() {
        return new MyClient();
    }
}
```

Ví dụ trên **giả định** bạn có lớp `MyClient` và method `close()` phù hợp; nó chỉ minh họa ý nghĩa của `destroyMethod`. Phần lớn resource integration đã có starter/configuration chuẩn, nên hãy dùng cơ chế có sẵn trước khi tự tạo bean quản lý kết nối phức tạp.

## 12. Bean được quản lý không có nghĩa mọi lời gọi đều đi qua Spring

Một nhầm lẫn quan trọng: Spring quản lý bean không có nghĩa container can thiệp vào **từng dòng mã Java**.

Với service:

```java
@Service
public class ProductService {
    public String formatName(String input) {
        return input.trim();
    }
}
```

Khi có một instance/proxy của `ProductService`, lời gọi method bình thường vẫn vận hành theo cơ chế Java. Spring chỉ thêm hành vi nếu có cơ chế tương ứng, chẳng hạn proxy AOP dùng cho transaction, caching, async hoặc method security.

### Proxy và đối tượng đích

Một proxy có thể đứng giữa bean tham chiếu từ caller và đối tượng đích:

```text
Caller → Spring-managed proxy → target object → method
            │
            ├─ trước/sau method theo advice
            └─ transaction, caching, security... khi có cấu hình
```

Điều này giúp Spring áp dụng cross-cutting concerns mà không cần viết lời gọi xử lý transaction ở mọi controller.

Tuy nhiên, **không phải mọi bean đều bị proxy** và cũng không phải mọi lời gọi đều qua proxy. Tùy extension point và công nghệ, Spring có thể chọn JDK dynamic proxy hoặc class-based proxy.

### Self-invocation: gọi method nội bộ có thể bỏ qua advice

Ví dụ ý tưởng:

```java
@Service
public class PaymentService {

    public void pay() {
        savePayment(); // lời gọi nội bộ qua this
    }

    @Transactional
    public void savePayment() {
        // lưu dữ liệu...
    }
}
```

Giả sử `@Transactional` được cấu hình hoạt động theo **proxy-based transaction management**. Khi gọi `pay()` trên bean proxy, lời gọi `this.savePayment()` bên trong target có thể **không đi qua proxy lần nữa**, nên transaction advice ở `savePayment()` có thể không chạy theo kỳ vọng.

Để đạt behavior mong muốn, thường tách method transactional sang một bean khác rồi inject vào caller, hoặc đặt transaction boundary ở method được gọi từ bên ngoài proxy. Cần phân biệt chi tiết này với trường hợp chạy bằng AspectJ weaving; không thể khẳng định mọi kiểu AOP của Spring đều giống proxy self-invocation.

### Không nên tự `new` service có advice

Nếu bạn tự gọi `new PaymentService()` trong controller, instance đó không tự qua Spring lifecycle, dependency injection, transaction proxy, security hoặc caching. Đây là lý do phổ biến khiến annotation “có trên class nhưng không có tác dụng” trong runtime.

## 13. `@Configuration` và `@Bean`: lời gọi Java hay tham chiếu bean?

Trong lớp `@Configuration` thông thường, Spring có thể xử lý các lời gọi giữa những phương thức `@Bean` để trả bean được quản lý theo scope thay vì chỉ chạy method body như Java thông thường.

Ví dụ:

```java
@Configuration
public class OrderConfiguration {

    @Bean
    public Notifier notifier() {
        return new EmailNotifier();
    }

    @Bean
    public OrderService orderService() {
        return new OrderService(notifier());
    }
}
```

Với **full `@Configuration`** (cơ chế intercept phương thức `@Bean` khi `proxyBeanMethods=true`, là mặc định của `@Configuration`), Spring có thể đảm bảo lời gọi `notifier()` được giải quyết thành bean `Notifier` do container quản lý, phù hợp với scope của definition.

Tuy nhiên, với `@Configuration(proxyBeanMethods = false)` hoặc phương thức `@Bean` nằm trong kiểu cấu hình lite, gọi trực tiếp `notifier()` là **gọi phương thức Java thông thường** và có thể tạo object mới ngoài luồng container mong muốn.

Cách rõ ràng, ít phụ thuộc hành vi interception hơn là **inject qua tham số factory method**:

```java
@Configuration(proxyBeanMethods = false)
public class OrderConfiguration {

    @Bean
    public Notifier notifier() {
        return new EmailNotifier();
    }

    @Bean
    public OrderService orderService(Notifier notifier) {
        return new OrderService(notifier);
    }
}
```

Spring giải quyết tham số `Notifier` trước khi gọi `orderService(...)`. Hãy coi cấu hình `@Bean` là cách **khai báo quan hệ giữa bean definitions**, không phải nơi thủ công tạo lại mọi object ở mỗi method.

## 14. Lazy initialization và thời điểm bean thật sự được tạo

Singleton mặc định thường được khởi tạo khi context refresh, nhưng có thể thay đổi bằng `@Lazy`:

```java
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Service;

@Lazy
@Service
public class HeavyReportService {
    public HeavyReportService() {
        System.out.println("Constructing HeavyReportService");
    }
}
```

Ý nghĩa: container có thể hoãn việc tạo bean này đến khi cần. Tuy nhiên, nếu một singleton khác **eagerly** cần `HeavyReportService` trong constructor, việc đó có thể khiến bean được khởi tạo sớm; muốn trì hoãn dependency có thể cần proxy/lazy injection hoặc provider phù hợp.

Một số hệ thống bật lazy initialization rộng hơn qua cấu hình Boot. Điều này có thể giảm công việc khởi tạo ban đầu nhưng làm lỗi thiếu dependency/configuration xuất hiện **muộn**, khi tính năng lần đầu được truy cập. Vì vậy, eager và lazy là lựa chọn về lifecycle và thời điểm phát hiện lỗi, không phải một quy tắc tối ưu chung.

## 15. Bean có thể thay đổi theo profile hoặc điều kiện cấu hình

Spring Boot cho phép các bean chỉ xuất hiện khi môi trường phù hợp, ví dụ:

```java
public interface StorageClient {
    String where();
}
```

```java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("local")
public class LocalStorageClient implements StorageClient {
    @Override
    public String where() {
        return "local";
    }
}
```

```java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("prod")
public class ProductionStorageClient implements StorageClient {
    @Override
    public String where() {
        return "remote";
    }
}
```

Khi profile `local` active, Spring có thể đăng ký `LocalStorageClient`; với `prod`, ứng viên tương ứng là `ProductionStorageClient`. Nếu không profile nào phù hợp và có một service yêu cầu `StorageClient`, việc khởi tạo có thể thất bại vì không có bean. Nếu cả hai profile cùng active, có thể xuất hiện nhiều ứng viên và cần cấu hình cách chọn bean.

Profile là một trong nhiều điều kiện đăng ký bean. Auto-configuration của Boot thường dùng các annotation điều kiện phong phú hơn như `@ConditionalOnClass` hoặc `@ConditionalOnMissingBean` để chỉ cung cấp bean mặc định khi phù hợp.

**Không nên kiểm tra profile bằng cách tạo object thủ công ở nhiều nơi** nếu quan hệ phụ thuộc đã có thể được khai báo rõ bằng bean và configuration.

## 16. Những lỗi bean thường gặp và ý nghĩa

| Triệu chứng / lỗi thường thấy | Ý nghĩa có thể xảy ra | Cách kiểm tra |
|---|---|---|
| `NoSuchBeanDefinitionException` | Container không tìm thấy bean phù hợp với dependency/lookup. | Kiểm tra package scan, annotation, cấu hình `@Bean`, profile, điều kiện và dependency. |
| `NoUniqueBeanDefinitionException` | Có nhiều bean phù hợp nhưng không chọn được duy nhất. | Xem ứng viên, `@Qualifier`, `@Primary` và cấu hình test/profile. |
| `BeanCreationException` | Quá trình tạo hoặc khởi tạo một bean thất bại. | Đọc nguyên nhân sâu nhất trong stack trace: constructor, config, tài nguyên, callback, dependency. |
| `UnsatisfiedDependencyException` | Một dependency bắt buộc của bean chưa được đáp ứng. | Xác định parameter/field nào, kiểm tra thiếu bean, sai type hoặc có nhiều ứng viên. |
| `BeanCurrentlyInCreationException` | Có thể có vòng phụ thuộc hoặc vấn đề trong quá trình tạo bean. | Kiểm tra dependency graph và thiết kế constructor; tránh vòng A → B → A. |
| `ScopeNotActiveException` | Bean thuộc scope không hoạt động trong ngữ cảnh hiện tại. | Kiểm tra request/session đang active và cách dùng scoped proxy/provider. |
| `@Transactional`/`@Async` không phát huy tác dụng | Đối tượng không được container quản lý hoặc lời gọi bỏ qua proxy/cấu hình advice. | Kiểm tra cách lấy bean, việc gọi nội bộ, cấu hình AOP và phạm vi proxy. |

Một số lỗi được Spring bọc nhiều tầng exception. Dòng cuối cùng hữu ích nhưng không đủ; hãy đọc chuỗi `Caused by` để tìm nguyên nhân ban đầu.

### Vòng phụ thuộc constructor

Ví dụ:

```java
@Service
public class ServiceA {
    public ServiceA(ServiceB b) { }
}

@Service
public class ServiceB {
    public ServiceB(ServiceA a) { }
}
```

Để tạo `ServiceA`, container cần `ServiceB`; để tạo `ServiceB`, nó lại cần `ServiceA`. Với constructor injection, quan hệ vòng này không thể được giải quyết như một đồ thị khởi tạo tuyến tính thông thường.

Thay vì bật các cờ cho phép circular reference làm giải pháp mặc định, hãy xem lại thiết kế: tách trách nhiệm chung, đảo chiều dependency hoặc dùng event/callback khi hai component thực sự cần phối hợp mà không cần giữ tham chiếu hai chiều.

## 17. Nhìn thấy container đang quản lý bean nào

Trong ứng dụng phát triển/debug, bạn có thể inspect `ApplicationContext`:

```java
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BeanInspectorConfiguration {

    @Bean
    CommandLineRunner showTimeBeans(ApplicationContext context) {
        return args -> {
            for (String name : context.getBeanNamesForType(
                    com.example.demo.service.TimeService.class)) {
                System.out.println("TimeService bean: " + name);
            }
        };
    }
}
```

Ví dụ này dựa trên `TimeService` của phần 6 và giả định lớp config ở package được scan. Khi ứng dụng khởi động, runner in các bean name thuộc kiểu `TimeService`. Trong dự án thực tế, nên dùng logger, tránh log toàn bộ bean nếu có dữ liệu nhạy cảm hoặc quá nhiều nội dung.

Bạn có thể kiểm tra instance singleton bằng một test Spring Boot:

```java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.assertSame;

import com.example.demo.service.TimeService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

@SpringBootTest
class BeanIdentityTest {

    @Autowired
    ApplicationContext context;

    @Test
    void sameSingletonBeanIsReturned() {
        TimeService first = context.getBean(TimeService.class);
        TimeService second = context.getBean(TimeService.class);
        assertSame(first, second);
    }
}
```

Test giả định một bean `TimeService` singleton duy nhất và test starter phù hợp đã được thêm. **Đây là bài thực hành quan sát scope**, không phải bằng chứng rằng mọi bean hay mọi scope đều trả cùng instance.

Khi ứng dụng đủ điều kiện bật Spring Boot Actuator, endpoint `beans` có thể giúp quan sát bean definitions và dependency trong môi trường kiểm soát. Cần cấu hình exposure và bảo vệ endpoint quản trị thích hợp; không mặc định mọi endpoint Actuator đều được công khai.

## 18. Những hiểu lầm dễ gặp

**“Có `@Service` nghĩa là mỗi lần gọi method Spring tạo một object mới.”** Sai với scope singleton mặc định. Method gọi nhiều lần trên cùng bean có thể dùng cùng instance qua nhiều request.

**“Spring singleton là một instance duy nhất trên mọi máy.”** Sai. Scope singleton gắn với một bean definition trong một container. Hai tiến trình Spring Boot không chia sẻ heap Java với nhau.

**“Đã inject dependency thì có thể tự tạo service bằng `new` ở nơi khác mà không sao.”** Bạn có thể tạo đối tượng Java bình thường, nhưng instance đó không tự mang dependency, lifecycle và proxy do container quản lý. Hãy chọn đúng cơ chế theo mục đích.

**“`@Autowired` là cách duy nhất để inject.”** Constructor đơn của một Spring-managed class có thể được dùng mà không cần ghi annotation. Quan trọng hơn là định nghĩa rõ dependency cần thiết.

**“Prototype là một object mới cho mọi HTTP request.”** Không nhất thiết. Prototype là mới theo **mỗi lần container cấp bean**, không tự đồng bộ với request. Request scope mới mô tả lifecycle gắn với HTTP request.

**“Có bean là tự động thread-safe.”** Không. Shared mutable state phải được bảo vệ đúng cách hoặc tránh lưu trên singleton service.

**“Một starter tạo mọi bean cho mọi trường hợp.”** Không. Starter đưa dependency vào classpath; auto-configuration còn phụ thuộc điều kiện và cấu hình.

**“`@PostConstruct` chứng tỏ toàn bộ ứng dụng đã sẵn sàng.”** Không. Nó liên quan giai đoạn khởi tạo **một bean**, không cam kết toàn bộ startup đã hoàn thành.

**“Một method có `@Transactional` luôn chạy trong transaction.”** Không phải trong mọi cách gọi. Với proxy-based interception, direct self-invocation có thể bỏ qua advice.

## 19. Bài tập thực hành về bean và IoC container

### Bài tập A: So sánh `new` với bean

Tạo `GreetingService` như phần 1, thử gọi bằng `new` trong một unit test. Sau đó thêm `@Service` và inject nó vào một controller. Giải thích trách nhiệm của người gọi và Spring container ở mỗi cách.

### Bài tập B: Dùng constructor injection và bean `Clock`

Tạo `TimeConfiguration`, `TimeService`, `TimeController` như phần 6. Truy cập `GET /time`. Sau đó unit test `TimeService` bằng `Clock.fixed`. Quan sát vì sao cùng một lớp service có thể dùng được bên trong lẫn bên ngoài Spring.

### Bài tập C: Tạo hai implementation của cùng interface

Đăng ký `emailSender` và `smsSender`, rồi inject `MessageSender` vào service. Quan sát exception khi không thể chọn duy nhất; dùng `@Qualifier` để nêu rõ bean cần nhận.

### Bài tập D: Quan sát singleton và prototype

Tạo `ReportDraft` prototype, dùng `context.getBean(ReportDraft.class)` hai lần rồi so sánh identity. Thử inject trực tiếp nó vào một singleton và gọi method nhiều lần. Sau đó dùng `ObjectProvider<ReportDraft>` để nhận instance mới theo nhu cầu.

### Bài tập E: Kiểm tra lifecycle

Thêm `@PostConstruct` và `@PreDestroy` vào một bean đơn giản. Khởi chạy rồi tắt ứng dụng bình thường; quan sát callback. Giải thích vì sao không nên phụ thuộc hoàn toàn vào callback hủy để đảm bảo một giao dịch nghiệp vụ quan trọng luôn được hoàn thành.

### Bài tập F: Quan sát auto-configuration

Thêm một Spring Boot starter phù hợp với dòng Boot của dự án, chạy ứng dụng với chế độ debug và tìm conditions evaluation report. Tìm một auto-configuration được áp dụng và một cái không được áp dụng. Giải thích điều kiện classpath/bean/property thay vì chỉ dựa vào tên starter.

## 20. Kết luận về trách nhiệm của container

Một **Spring bean** là đối tượng được container nhận diện thông qua bean definition và quản lý theo cấu hình. Container biết **cách tạo**, **cách chọn và inject dependency**, **khi nào tái sử dụng hay tạo instance mới**, **callback lifecycle nào được áp dụng**, và **có cơ chế mở rộng nào bao quanh bean**. Từ đó, ứng dụng có thể tách rõ logic nghiệp vụ khỏi việc tự lắp ghép đối tượng.

Khi viết code Spring Boot, hãy hình dung đường đi:

```text
@Component / @Service / @Repository / @Controller
@Bean / @Configuration / auto-configuration
                    │
                    ▼
             Bean definitions
                    │
                    ▼
              IoC container
       ┌────────────┼────────────┐
  Khởi tạo       Inject DI       Scope/lifecycle
       └────────────┼────────────┘
                    ▼
       Bean (instance hoặc proxy)
                    │
                    ▼
       Controller, service, repository,
          ứng dụng và các caller
```

Cách hiểu này giải thích phần lớn lỗi thiếu bean, có quá nhiều bean, circular dependency, sai scope, lifecycle và annotation proxy không hoạt động. Thay vì chỉ thêm annotation theo thói quen, bạn có thể xác định **container đã đăng ký bean chưa, đang tạo bean nào, chọn dependency nào và thực sự trả instance gì**.
