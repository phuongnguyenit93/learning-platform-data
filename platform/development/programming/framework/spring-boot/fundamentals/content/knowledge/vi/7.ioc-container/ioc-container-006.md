# Đăng ký định nghĩa, tạo đối tượng, tiêm phụ thuộc và khởi tạo

Trong một ứng dụng Spring Boot, lập trình viên có thể viết lớp `OrderService`, đánh dấu `@Service`, khai báo constructor nhận `OrderRepository` rồi dùng service ấy trong controller mà không phải tự viết hàng loạt lệnh `new`. Điều này diễn ra nhờ **Spring IoC container**: thành phần của Spring Framework chịu trách nhiệm quản lý các đối tượng được đăng ký, giải quyết quan hệ phụ thuộc và điều phối một phần vòng đời của chúng.

Tuy nhiên, có bốn công việc rất dễ bị nhầm là một:

1. **Đăng ký định nghĩa (registration):** cho container biết *có một bean cần được quản lý* và quy tắc tạo bean là gì.
2. **Tạo đối tượng (instantiation):** thực sự tạo một instance của class hoặc gọi factory method để có đối tượng.
3. **Tiêm phụ thuộc (dependency injection):** cung cấp những đối tượng mà bean cần cộng tác.
4. **Khởi tạo (initialization):** chạy các callback hoặc logic chuẩn bị sau khi bean đã có những dependency cần thiết.

Những giai đoạn này liên quan nhau nhưng không đồng nhất. **Có BeanDefinition không có nghĩa bean đã được tạo; constructor đã chạy không có nghĩa bean đã hoàn tất initialization; Spring Boot khởi động thành công không có nghĩa tất cả bean đều đã được tạo trong mọi cấu hình.**

Bài học mô tả các giai đoạn từ lúc Spring Boot khởi động đến khi một bean sẵn sàng phục vụ ứng dụng, minh họa bằng Java 21 và Spring Boot 3.x.

## 1. Các khái niệm nền tảng

### 1.1. IoC và Dependency Injection

**Inversion of Control (IoC)** là ý tưởng chuyển một phần quyền điều phối việc tạo và kết nối đối tượng sang một thành phần bên ngoài. Trong ứng dụng Spring, thành phần đó thường là **Spring container**.

**Dependency Injection (DI)** là cách một đối tượng nhận những thành phần mà nó cần từ bên ngoài, chẳng hạn qua constructor. DI là một cơ chế quan trọng mà Spring container sử dụng để thực hiện IoC.

Ví dụ Java thuần:

~~~java
public final class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
~~~

`OrderService` cần một `OrderRepository`, nhưng không tự quyết định implementation hay tự khởi tạo repository. Một nơi khác sẽ truyền đối tượng tương ứng khi tạo `OrderService`.

Trong Java thuần, nơi lắp ghép có thể là:

~~~java
OrderRepository repository = new InMemoryOrderRepository();
OrderService service = new OrderService(repository);
~~~

Các kiểu trong đoạn này là minh họa. Với Spring, container có thể thực hiện việc tạo và kết nối ấy dựa trên các **bean definition** đã được đăng ký.

### 1.2. Bean và BeanDefinition

**Bean** là đối tượng được Spring IoC container quản lý. Một đối tượng Java thông thường được gọi bằng `new` bên ngoài container không mặc nhiên trở thành Spring bean.

**BeanDefinition** là metadata cho container biết cách tạo, cấu hình và quản lý một bean. Tùy cách đăng ký, định nghĩa có thể mô tả:

- Class cần khởi tạo hoặc một factory method sẽ cung cấp đối tượng.
- Tên bean, phạm vi (scope) và trạng thái lazy/eager.
- Constructor arguments, các giá trị cấu hình và thông tin dependency.
- Các phương thức khởi tạo hoặc hủy, nếu được khai báo.
- Các điều kiện và metadata khác mà các bộ xử lý cấu hình sử dụng.

Hãy phân biệt:

| Khái niệm | Bản chất | Ví dụ |
| --- | --- | --- |
| Class | Kiểu Java được lập trình viên định nghĩa | `GreetingService.class` |
| BeanDefinition | Bản mô tả cách container quản lý/tạo bean | Định nghĩa bean tên `greetingService` |
| Bean instance | Đối tượng thực tế được tạo và quản lý | Instance `GreetingService` được inject vào controller |
| ApplicationContext | Container cung cấp bean và nhiều dịch vụ ứng dụng khác | Kết quả trả về từ `SpringApplication.run(...)` |

Một container có thể biết tên bean và kiểu bean **trước khi instance tương ứng tồn tại**. Điều này đặc biệt rõ ở bean khai báo lazy hoặc bean có scope `prototype`.

### 1.3. BeanFactory và ApplicationContext

`BeanFactory` là giao diện nền tảng cho việc truy xuất và quản lý bean. `ApplicationContext` mở rộng khả năng đó với nhiều dịch vụ của ứng dụng như event, resource, message resolution và các tích hợp quản lý cấu hình.

Trong ứng dụng Spring Boot thông thường, `SpringApplication.run(...)` tạo và refresh một `ApplicationContext` thích hợp với kiểu ứng dụng:

~~~java
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Spring Boot giúp chuẩn bị môi trường, lựa chọn loại context, nạp cấu hình và chạy ứng dụng thuận tiện hơn. **Các cơ chế BeanDefinition, Dependency Injection và bean lifecycle thuộc Spring Framework**, còn Boot xây dựng trải nghiệm khởi động và auto-configuration xung quanh chúng.

## 2. Nhìn toàn bộ chu trình trước khi đi vào chi tiết

Một dòng xử lý điển hình cho bean singleton thông thường trong lúc khởi động có thể được hình dung như sau:

~~~mermaid
flowchart TD
    A["SpringApplication.run(...)"] --> B["Chuẩn bị ApplicationContext"]
    B --> C["Đọc cấu hình, scan component, đăng ký BeanDefinition"]
    C --> D["Xử lý/chỉnh metadata và đăng ký BeanPostProcessor"]
    D --> E["BeanFactory chọn bean cần tạo"]
    E --> F["Giải quyết constructor dependencies và tạo instance"]
    F --> G["Tiêm thêm property/field/method dependencies nếu có"]
    G --> H["Callback trước initialization, ví dụ @PostConstruct"]
    H --> I["InitializingBean / custom init method"]
    I --> J["Callback sau initialization; có thể tạo proxy"]
    J --> K["Bean sẵn sàng để các thành phần khác sử dụng"]
    K --> L["Context hoàn tất refresh; Boot gọi runner thích hợp"]
~~~

Đây là **sơ đồ khái niệm**, không phải lời hứa rằng mọi bean hoặc mọi extension đều đi qua đúng cùng một danh sách callback. Một số bean được tạo sớm để phục vụ quá trình xử lý cấu hình; một số bean chỉ được tạo khi có yêu cầu; một số bean do factory hoặc framework-specific infrastructure khởi tạo theo đường riêng.

Với một bean singleton thông thường không lazy, cần nhớ thứ tự mang tính bản chất:

~~~text
Định nghĩa được đăng ký
          ↓
Container quyết định tạo bean
          ↓
Tạo instance và giải quyết dependency
          ↓
Hoàn thành injection cần thiết
          ↓
Gọi initialization callbacks
          ↓
Bean có thể được sử dụng theo cấu hình của context
~~~

**Registration** và **instantiation** khác nhau. **Instantiation/injection** và **initialization** cũng khác nhau. Đây là điểm mấu chốt để hiểu những lỗi thường gặp của Spring.

## 3. Giai đoạn 1: Đăng ký BeanDefinition

### 3.1. Đăng ký bằng component scan

Cách dễ thấy nhất trong Spring Boot là dùng các annotation chỉ component:

~~~java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

`@Service` là một specialization của `@Component`. Khi package chứa lớp nằm trong phạm vi **component scan** của ứng dụng, Spring có thể phát hiện class và đăng ký định nghĩa bean tương ứng.

Các annotation thường gặp:

| Annotation | Mục đích diễn đạt |
| --- | --- |
| `@Component` | Component chung được quản lý bởi container |
| `@Service` | Component thuộc tầng dịch vụ hoặc xử lý nghiệp vụ |
| `@Repository` | Component thuộc tầng truy cập dữ liệu; còn có thể tham gia cơ chế dịch exception phù hợp |
| `@Controller` | Controller của mô hình web Spring MVC |
| `@RestController` | Controller hướng trả dữ liệu HTTP response body |
| `@Configuration` | Class khai báo cấu hình và các bean factory method |

Spring Boot thường dùng `@SpringBootApplication`, trong đó có cơ chế component scan mặc định bắt đầu ở package chứa class ứng dụng và các package con.

Ví dụ:

~~~text
com.example.demo
├── DemoApplication.java       ← @SpringBootApplication
├── GreetingService.java       ← @Service, thường được scan
└── web/
    └── GreetingController.java ← @RestController, thường được scan

com.example.other
└── ExternalService.java       ← nằm ngoài phạm vi scan mặc định
~~~

Nếu `ExternalService` không được nhập qua cơ chế cấu hình khác, chỉ đánh dấu `@Service` chưa chắc khiến nó được container phát hiện. Đây là một nguyên nhân phổ biến của lỗi thiếu bean.

Điều đáng chú ý: **component scan tạo ra bean definition trước; nó không nhất thiết tạo ngay mọi object tương ứng tại thời điểm quét class**.

### 3.2. Đăng ký bằng `@Bean` trong class cấu hình

Không phải class nào cũng có thể hoặc nên đánh dấu `@Component`. Chẳng hạn, thư viện bên thứ ba có thể không thuộc mã nguồn mà bạn sở hữu.

Bạn có thể khai báo factory method:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GreetingConfiguration {

    @Bean
    public MessageFormatter messageFormatter() {
        return new VietnameseMessageFormatter();
    }
}
~~~

Với:

~~~java
package com.example.demo;

public interface MessageFormatter {
    String format(String name);
}
~~~

Và implementation:

~~~java
package com.example.demo;

public final class VietnameseMessageFormatter implements MessageFormatter {
    @Override
    public String format(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Trong cấu hình trên:

- `@Configuration` đánh dấu class cấu hình Spring.
- `@Bean` yêu cầu Spring quản lý đối tượng được factory method trả về.
- Tên bean mặc định thường lấy từ tên method, ở đây là `messageFormatter`.
- `VietnameseMessageFormatter` không cần đánh dấu `@Component` vì bean được tạo thông qua factory method.

Khi xử lý class cấu hình, Spring đăng ký **định nghĩa** cho bean `messageFormatter`. Đến lúc bean cần được tạo, container có thể gọi method `messageFormatter()` để lấy instance thực tế.

Điều này giải thích vì sao không thể đồng nhất “Spring nhìn thấy `@Bean`” với “Spring đã chạy method `@Bean` ngay lúc quét”.

### 3.3. Injection ngay trong tham số factory method

Một factory method có thể nhận các dependency đã được container quản lý:

~~~java
@Configuration
public class ClientConfiguration {

    @Bean
    public ReportClient reportClient(HttpClient httpClient) {
        return new ReportClient(httpClient);
    }
}
~~~

Trong đoạn minh họa, `HttpClient` và `ReportClient` là những kiểu giả định cần được định nghĩa/đăng ký riêng. Spring sẽ giải quyết bean phù hợp với tham số `httpClient` khi tạo `ReportClient`.

Lợi ích là class cấu hình vẫn thể hiện **đồ thị phụ thuộc** một cách rõ ràng; ta không buộc phải gọi `applicationContext.getBean(...)` thủ công trong method cấu hình.

### 3.4. Spring Boot auto-configuration cũng đăng ký định nghĩa

Ngoài component do bạn viết, Spring Boot có **auto-configuration**. Dựa trên classpath, các bean hiện có, thuộc tính cấu hình và các điều kiện tương ứng, nó có thể cung cấp các bean hạ tầng thông dụng.

Ví dụ khi ứng dụng có web starter và cấu hình phù hợp, những thành phần phục vụ Spring MVC và embedded server có thể được thiết lập tự động.

Các annotation điều kiện trong cơ chế này thường gồm:

~~~java
@ConditionalOnClass(...)
@ConditionalOnMissingBean(...)
@ConditionalOnProperty(...)
~~~

Đây là các **ví dụ annotation điều kiện**, không phải đoạn code hoàn chỉnh để biên dịch độc lập.

`@ConditionalOnMissingBean` thường giúp auto-configuration nhường chỗ khi người dùng đã cung cấp một bean phù hợp. Tuy nhiên, hành vi cụ thể phụ thuộc vào điều kiện, thứ tự xử lý cấu hình và kiểu bean đang xét.

**Auto-configuration không đồng nghĩa Spring Boot luôn tạo tất cả bean có thể có.** Nó lựa chọn những định nghĩa thích hợp theo điều kiện thực tế của ứng dụng.

### 3.5. Đăng ký programmatically

Ngoài annotation, Spring Framework còn hỗ trợ đăng ký định nghĩa qua API như `BeanDefinitionRegistry` hoặc những phương thức đăng ký bean có sẵn trên context phù hợp.

Cách này thường dành cho framework, starter hoặc cấu hình động. Trong bài nhập môn, `@Component` và `@Bean` là hai đường đăng ký dễ đọc và dễ bảo trì nhất.

## 4. Giai đoạn 2: Container quyết định khi nào cần tạo bean

Sau khi có các định nghĩa, container phải xác định **bean nào cần được tạo ngay**, bean nào chỉ cần tạo khi được yêu cầu.

### 4.1. Singleton thường được tạo trong quá trình khởi động

Scope mặc định của Spring bean là **singleton trong phạm vi một Spring container**. Với một singleton không lazy, `ApplicationContext` thường tạo instance của bean đó khi refresh context.

Ví dụ:

~~~java
@Service
public class GreetingService {
    public GreetingService() {
        System.out.println("GreetingService constructor");
    }
}
~~~

Nếu lớp nằm trong phạm vi scan và không có điều kiện ngăn đăng ký/tạo bean, constructor thường được gọi khi ứng dụng khởi động.

Nhưng đây là quy tắc cho **singleton không lazy trong một luồng khởi tạo thông thường**. Không nên hiểu thành “cứ thấy định nghĩa của bean là constructor đã chạy”.

### 4.2. Lazy bean có thể chỉ tạo khi được yêu cầu

~~~java
@Lazy
@Service
public class HeavyReportService {
    public HeavyReportService() {
        System.out.println("HeavyReportService created");
    }
}
~~~

`@Lazy` có thể trì hoãn khởi tạo bean cho tới khi bean được yêu cầu. Tuy nhiên, có một điểm dễ nhầm: nếu một singleton không lazy khác cần `HeavyReportService` như dependency bắt buộc, việc giải quyết dependency có thể vẫn khiến bean ấy được tạo trong lúc khởi động.

Nếu muốn injection point sử dụng cơ chế tham chiếu lazy, Spring cũng hỗ trợ `@Lazy` tại injection point trong những tình huống thích hợp. Khi thiết kế, cần phân biệt **lazy bean definition** và **lazy resolution của dependency**.

Spring Boot cũng có thuộc tính cấu hình:

~~~properties
spring.main.lazy-initialization=true
~~~

Thuộc tính này thay đổi chiến lược khởi tạo mặc định của nhiều bean. Nó có thể rút ngắn thời gian startup trong một số tình huống, đồng thời khiến lỗi cấu hình/khởi tạo lộ ra muộn hơn khi bean lần đầu được dùng.

### 4.3. Scope prototype tạo instance theo yêu cầu

~~~java
@Component
@Scope("prototype")
public class TaskContext {
    public TaskContext() {
        System.out.println("New TaskContext");
    }
}
~~~

Với scope `prototype`, container tạo một instance mới khi có yêu cầu lấy bean tương ứng. Không giống singleton, prototype không được tạo sẵn hàng loạt chỉ vì có định nghĩa.

Nếu một prototype được inject trực tiếp vào **một singleton** qua constructor, dependency đó thường chỉ được giải quyết một lần khi singleton được tạo. Mỗi lần gọi method trên singleton **không tự động nhận prototype mới**. Khi cần lấy instance mới ở mỗi lần sử dụng, có thể thiết kế qua `ObjectProvider<T>` hoặc cơ chế tương đương phù hợp.

Spring cũng có giới hạn quản lý vòng đời prototype: container tạo, cấu hình và khởi tạo prototype, nhưng không tự quản lý toàn bộ bước hủy cho từng instance prototype như với singleton.

### 4.4. Singleton không đồng nghĩa “một object trong cả JVM”

Nếu có hai application context khác nhau, mỗi context có thể sở hữu singleton riêng của cùng một bean definition. Ngoài ra, mã Java bên ngoài vẫn có thể tự tạo các instance khác bằng `new`.

Ý nghĩa của Spring singleton là **một instance theo định nghĩa bean trong phạm vi container**, không phải một ràng buộc toàn cục của ngôn ngữ Java.

## 5. Giai đoạn 3: Tạo object và giải quyết constructor

Với bean được đăng ký qua class, Spring chọn phương thức tạo phù hợp, thường là constructor. Với bean từ `@Bean`, container gọi factory method và sử dụng object được trả về.

### 5.1. Constructor injection

Ví dụ:

~~~java
@Service
public class GreetingService {
    private final MessageFormatter formatter;

    public GreetingService(MessageFormatter formatter) {
        this.formatter = formatter;
    }

    public String greet(String name) {
        return formatter.format(name);
    }
}
~~~

Để tạo `GreetingService`, Spring cần một bean phù hợp với kiểu `MessageFormatter`.

Diễn giải khái niệm:

~~~text
Yêu cầu tạo GreetingService
             │
             ▼
Đọc constructor cần MessageFormatter
             │
             ▼
Tìm BeanDefinition/bean phù hợp
             │
             ▼
Tạo hoặc lấy MessageFormatter instance
             │
             ▼
Gọi new GreetingService(formatter)
             │
             ▼
Có GreetingService instance
~~~

Câu “Spring tạo bean” thường bao gồm cả việc **đi theo các dependency trước khi gọi constructor**. Vì thế log từ constructor của dependency có thể xuất hiện trước log constructor của bean sử dụng nó.

Nếu một class chỉ có **một constructor**, Spring có thể dùng constructor đó để injection mà không cần ghi `@Autowired`. Đây là cách viết phổ biến vì dễ nhận biết những dependency bắt buộc.

### 5.2. Container tìm bean phù hợp dựa vào đâu?

Spring thực hiện dependency resolution dựa trên các thông tin như kiểu bean, qualifier, primary candidate, tên bean trong những trường hợp thích hợp và các quy tắc dành cho từng loại injection point.

Nếu chỉ có một bean `MessageFormatter`, constructor trên thường được giải quyết thuận lợi.

Nếu có **hai bean cùng triển khai**:

~~~java
@Component
class VietnameseFormatter implements MessageFormatter {
    public String format(String name) {
        return "Xin chào, " + name;
    }
}

@Component
class EnglishFormatter implements MessageFormatter {
    public String format(String name) {
        return "Hello, " + name;
    }
}
~~~

thì một constructor yêu cầu duy nhất `MessageFormatter` có thể trở nên nhập nhằng. Ví dụ này là **một tình huống thay thế**, không phải phần thêm vào cùng ví dụ `@Bean messageFormatter` ở trên; thêm tất cả implementation đồng thời sẽ tạo nhiều candidate hơn nữa.

Có thể chỉ định một bean:

~~~java
public GreetingService(
        @Qualifier("vietnameseFormatter") MessageFormatter formatter) {
    this.formatter = formatter;
}
~~~

Hoặc đánh dấu một implementation là lựa chọn ưu tiên bằng `@Primary` theo thiết kế thực tế. Với nhiều dependency bắt buộc dùng chung một kiểu, không nên tự chọn đại một bean cho hết lỗi khởi động.

### 5.3. Constructor có thể chưa được gọi vì thiếu dependency

Ví dụ:

~~~java
@Service
public class OrderService {
    public OrderService(OrderRepository repository) {
        // ...
    }
}
~~~

Nếu không có bean phù hợp với `OrderRepository`, Spring không thể cung cấp tham số bắt buộc và thường báo lỗi tạo bean như `UnsatisfiedDependencyException` hoặc nguyên nhân `NoSuchBeanDefinitionException`.

Điều này xảy ra **trong quá trình giải quyết dependency để tạo bean**, trước khi service sẵn sàng sử dụng. Đổi thành constructor không tham số để che giấu dependency thường không giải quyết được nhu cầu thiết kế thực sự.

### 5.4. Tạo đối tượng qua `@Bean`

Với factory method:

~~~java
@Bean
MessageFormatter messageFormatter() {
    return new VietnameseMessageFormatter();
}
~~~

Spring không cần tự gọi constructor của `VietnameseMessageFormatter` thông qua component scan. Nó gọi factory method được đăng ký rồi quản lý đối tượng được trả về.

Nếu một class vừa được scan như `@Component`, vừa được một `@Bean` method tự tạo instance khác, bạn có thể vô tình đăng ký hai bean có vai trò tương tự. Phải hiểu mình muốn container tạo bean qua **con đường nào**.

## 6. Giai đoạn 4: Tiêm phụ thuộc và cấu hình thuộc tính

Ở constructor injection, dependency được cung cấp **ngay khi tạo đối tượng**. Với field injection hoặc setter/method injection, Spring còn có bước gán dependency **sau khi constructor đã chạy**.

### 6.1. Constructor injection

~~~java
@Service
public class EmailService {
    private final MailClient mailClient;

    public EmailService(MailClient mailClient) {
        this.mailClient = mailClient;
    }
}
~~~

`MailClient` ở đây là interface/class minh họa cần có bean tương ứng trong context.

Ưu điểm:

- Dependency bắt buộc hiện rõ ở constructor.
- Có thể dùng `final` để giữ tham chiếu ổn định.
- Dễ tạo đối tượng trong unit test bằng Java thuần.
- Tránh tình huống đối tượng được tạo hợp lệ nhưng chưa có dependency bắt buộc.

Đây thường là lựa chọn nên ưu tiên cho các cộng tác viên bắt buộc của service, controller và những thành phần tương tự.

### 6.2. Setter injection

~~~java
@Component
public class ReportPrinter {
    private AuditLogger auditLogger;

    @Autowired
    public void setAuditLogger(AuditLogger auditLogger) {
        this.auditLogger = auditLogger;
    }
}
~~~

Trong đoạn minh họa này, Spring có thể tạo `ReportPrinter` trước rồi gọi setter để inject `AuditLogger`.

Cách này có thể dùng cho dependency tùy chọn hoặc có chủ đích thay đổi, nhưng cần bảo đảm mã xử lý đúng khi dependency chưa được cung cấp theo hợp đồng thiết kế.

### 6.3. Field injection

~~~java
@Component
public class ReportPrinter {
    @Autowired
    private AuditLogger auditLogger;
}
~~~

Field injection được Spring hỗ trợ, nhưng tạo dependency “ẩn” trong lớp: muốn khởi tạo bằng Java thuần, bạn không thể truyền dependency qua constructor. Trạng thái field cũng chưa được điền ngay trong constructor.

Nếu constructor gọi phương thức cần field được inject, field đó có thể vẫn là `null`. Vì thế các hoạt động cần dependency sau field injection nên được thực hiện ở giai đoạn initialization phù hợp, không trong constructor.

### 6.4. Injection khác với gọi method nghiệp vụ

Khi một controller có:

~~~java
public GreetingController(GreetingService greetingService) {
    this.greetingService = greetingService;
}
~~~

việc container cung cấp `GreetingService` là **injection**. Khi client gửi HTTP request khiến controller gọi `greetingService.greet(...)`, đó là **thực thi nghiệp vụ sau khi đối tượng đã được kết nối**.

Không nên nhầm một lần injection lúc khởi tạo singleton với một lần gọi service cho từng HTTP request.

## 7. Giai đoạn 5: Initialization callbacks

Sau khi instance được tạo và dependency cần thiết đã được gán, Spring có thể thực hiện những callback khởi tạo được khai báo. Giai đoạn này phù hợp để một bean **kiểm tra cấu hình đã được cấp, thiết lập trạng thái nội bộ cần thiết hoặc chuẩn bị tài nguyên thuộc vòng đời của chính bean**.

### 7.1. `@PostConstruct`

Trong Spring Boot 3.x, annotation dùng package Jakarta:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    private final MessageFormatter formatter;

    public GreetingService(MessageFormatter formatter) {
        this.formatter = formatter;
    }

    @PostConstruct
    public void initialize() {
        System.out.println("GreetingService dependencies are ready");
    }

    public String greet(String name) {
        return formatter.format(name);
    }
}
~~~

`@PostConstruct` chạy sau khi Spring đã thực hiện việc injection thông thường cho bean, trong quá trình initialization. Annotation này được xử lý bởi cơ chế bean post-processing phù hợp trong Spring.

Cần phân biệt thời điểm:

~~~text
constructor                       : tạo instance
constructor injection             : dependency có ngay khi constructor chạy
field/setter injection (nếu có)   : thực hiện sau khi tạo instance
@PostConstruct                     : callback initialization sau injection
~~~

Đừng dùng `@PostConstruct` để giả định **mọi bean trong cả application context** đều đã hoàn thành startup. Nó chỉ nằm trong vòng đời khởi tạo của **bean hiện tại** và những dependency đã được giải quyết để tạo bean đó.

### 7.2. `InitializingBean.afterPropertiesSet()`

Spring Framework cung cấp giao diện:

~~~java
import org.springframework.beans.factory.InitializingBean;

public class ConfiguredClient implements InitializingBean {
    @Override
    public void afterPropertiesSet() {
        System.out.println("ConfiguredClient initialized");
    }
}
~~~

Nếu bean do Spring quản lý và triển khai `InitializingBean`, container gọi `afterPropertiesSet()` trong giai đoạn initialization.

Đây là một cơ chế có liên hệ trực tiếp đến Spring API. `@PostConstruct` thường giúp mã ứng dụng biểu đạt callback dễ đọc hơn, còn `InitializingBean` vẫn xuất hiện trong framework hoặc các tích hợp có chủ đích.

### 7.3. Custom init method của `@Bean`

Có thể khai báo tên method khởi tạo:

~~~java
public class ConnectionHolder {
    public void warmUp() {
        System.out.println("ConnectionHolder warm-up");
    }

    public void shutDown() {
        System.out.println("ConnectionHolder shutdown");
    }
}
~~~

Đăng ký:

~~~java
@Configuration
class ConnectionConfiguration {

    @Bean(initMethod = "warmUp", destroyMethod = "shutDown")
    ConnectionHolder connectionHolder() {
        return new ConnectionHolder();
    }
}
~~~

Trong ví dụ này, Spring quản lý bean `connectionHolder`, gọi `warmUp` trong initialization và gọi `shutDown` ở giai đoạn hủy singleton phù hợp khi context đóng bình thường. Khả năng hủy cụ thể còn phụ thuộc scope và lifecycle của bean.

Bạn vẫn cần tự viết logic mở/đóng tài nguyên thực sự bên trong các method. Annotation không tự biến một đối tượng bất kỳ thành kết nối database.

### 7.4. Thứ tự của các callback thông dụng

Với bean thông thường có đủ các callback và được xử lý qua các cơ chế chuẩn, thứ tự khái quát thường là:

1. Instance được tạo; dependency được giải quyết và inject.
2. Một số callback về container như `BeanNameAware` hoặc `BeanFactoryAware` được thực hiện nếu bean triển khai.
3. `BeanPostProcessor.postProcessBeforeInitialization(...)` được gọi; cơ chế xử lý `@PostConstruct` thường diễn ra ở giai đoạn này.
4. `InitializingBean.afterPropertiesSet()` được gọi nếu có.
5. Custom init method được khai báo được gọi nếu có.
6. `BeanPostProcessor.postProcessAfterInitialization(...)` được gọi; một số cơ chế có thể bọc bean trong proxy.
7. Bean tiếp tục được sử dụng theo lifecycle của context.

Cần lưu ý có nhiều loại BeanPostProcessor và logic framework khác nhau. Sơ đồ này giải thích **quy trình phổ biến**, không phải toàn bộ mọi đường tạo bean đặc biệt.

Một bean có thể dùng hơn một kiểu callback, nhưng tránh phân tán initialization cho cùng một mục đích ở nhiều cơ chế vì khó dự đoán và bảo trì.

## 8. Ví dụ Spring Boot hoàn chỉnh: quan sát từng giai đoạn

Ta xây một ứng dụng nhỏ có endpoint lời chào. Ứng dụng dùng:

- `MessageFormatter` là hợp đồng tạo lời chào.
- `VietnameseMessageFormatter` là implementation.
- `GreetingConfiguration` đăng ký implementation qua `@Bean`.
- `GreetingService` được component scan phát hiện và nhận formatter bằng constructor.
- `GreetingController` nhận service bằng constructor.
- `CommandLineRunner` kiểm tra service sau khi context khởi động.

Ví dụ dùng Java 21, Maven và Spring Boot `3.3.5` làm baseline minh họa.

### 8.1. Cấu trúc file

~~~text
ioc-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/ioc/
                ├── IocDemoApplication.java
                ├── MessageFormatter.java
                ├── VietnameseMessageFormatter.java
                ├── GreetingConfiguration.java
                ├── GreetingService.java
                └── GreetingController.java
~~~

### 8.2. File `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>ioc-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.3. File `MessageFormatter.java`

~~~java
package com.example.ioc;

public interface MessageFormatter {
    String format(String name);
}
~~~

Interface diễn tả khả năng tạo lời chào mà service cần, không buộc service biết class triển khai cụ thể.

### 8.4. File `VietnameseMessageFormatter.java`

~~~java
package com.example.ioc;

public final class VietnameseMessageFormatter implements MessageFormatter {
    @Override
    public String format(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Class này cố ý **không có** `@Component`; nó sẽ được tạo bằng factory method trong file cấu hình.

### 8.5. File `GreetingConfiguration.java`

~~~java
package com.example.ioc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GreetingConfiguration {

    @Bean
    public MessageFormatter messageFormatter() {
        System.out.println("[factory] Creating MessageFormatter");
        return new VietnameseMessageFormatter();
    }
}
~~~

Khi cấu hình được xử lý, Spring có định nghĩa bean tên `messageFormatter`. Khi cần tạo bean đó, container gọi factory method.

### 8.6. File `GreetingService.java`

~~~java
package com.example.ioc;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    private final MessageFormatter formatter;

    public GreetingService(MessageFormatter formatter) {
        this.formatter = formatter;
        System.out.println("[constructor] GreetingService created");
    }

    @PostConstruct
    public void initialize() {
        System.out.println("[init] GreetingService initialized");
    }

    public String greet(String name) {
        return formatter.format(name);
    }
}
~~~

`@Service` tạo cơ sở cho component scan đăng ký định nghĩa của `GreetingService`. Constructor bắt buộc cần một `MessageFormatter`. `@PostConstruct` làm xuất hiện dấu mốc trong giai đoạn initialization của service.

### 8.7. File `GreetingController.java`

~~~java
package com.example.ioc;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/api/greeting")
    public GreetingResponse greet(
            @RequestParam(defaultValue = "Bạn") String name) {
        return new GreetingResponse(greetingService.greet(name));
    }

    public record GreetingResponse(String message) {
    }
}
~~~

Spring đăng ký controller làm bean và inject `GreetingService` vào constructor. Khi HTTP request đến, controller gọi service đã được container tạo và kết nối trước đó.

### 8.8. File `IocDemoApplication.java`

~~~java
package com.example.ioc;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class IocDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(IocDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner afterStartup(GreetingService greetingService) {
        return args -> System.out.println(
                "[runner] " + greetingService.greet("Lan"));
    }
}
~~~

`CommandLineRunner` là callback Spring Boot gọi sau khi application context đã được refresh theo quy trình khởi động. Nó **khác** với `@PostConstruct`: runner là logic ở mức ứng dụng sau context startup; `@PostConstruct` thuộc vòng đời khởi tạo một bean.

Method `afterStartup(...)` cũng là một `@Bean` factory method. Spring giải quyết tham số `GreetingService` khi tạo bean runner.

### 8.9. Chạy và đọc kết quả

Ở thư mục chứa `pom.xml`, với JDK 21 và Maven phù hợp:

~~~bash
mvn spring-boot:run
~~~

Trong các dòng log khởi động, bạn có thể thấy những dấu mốc do ví dụ tự in:

~~~text
[factory] Creating MessageFormatter
[constructor] GreetingService created
[init] GreetingService initialized
[runner] Xin chào, Lan!
~~~

Đây là **các dòng cần quan sát theo quan hệ phụ thuộc**, không nhất thiết liền kề trong stdout; Spring Boot còn ghi nhiều log của framework. Với ví dụ và điều kiện khởi động thông thường, factory của formatter phải cung cấp object trước khi constructor của service có thể nhận dependency, initialization của service diễn ra sau khi service được tạo, và runner chỉ được gọi ở giai đoạn sau refresh.

Mở terminal khác và gửi HTTP request:

~~~bash
curl -i "http://localhost:8080/api/greeting?name=Minh"
~~~

Body mong đợi:

~~~json
{"message":"Xin chào, Minh!"}
~~~

Cần có ứng dụng đang chạy trên cổng `8080`, hoặc thay URL theo cổng đã cấu hình thực tế. Response cho thấy controller có thể sử dụng service đã được container inject và formatter đã được đăng ký.

### 8.10. Đọc đường đi của bean trong ví dụ

~~~mermaid
flowchart TD
    A["Component scan và xử lý @Configuration"] --> B["BeanDefinition: messageFormatter"]
    A --> C["BeanDefinition: greetingService"]
    A --> D["BeanDefinition: greetingController"]
    A --> E["BeanDefinition: afterStartup"]
    B --> F["Gọi @Bean factory method"]
    F --> G["VietnameseMessageFormatter instance"]
    G --> H["Inject vào GreetingService constructor"]
    C --> H
    H --> I["GreetingService instance"]
    I --> J["@PostConstruct"]
    J --> K["Inject vào GreetingController"]
    D --> K
    I --> L["Inject vào CommandLineRunner factory method"]
    E --> L
    L --> M["Runner gọi greet sau context refresh"]
~~~

Sơ đồ không cố định thứ tự tạo những bean không phụ thuộc nhau. Nó thể hiện **các ràng buộc về thứ tự do dependency tạo ra**. Chẳng hạn, service không thể được tạo đúng theo constructor của ví dụ nếu formatter chưa được cung cấp.

## 9. BeanPostProcessor xử lý gì trong chu trình?

Spring có một extension point quan trọng là `BeanPostProcessor`. Nó có thể can thiệp vào bean **trước và sau initialization**.

Giao diện chính khai báo hai method tiêu biểu:

~~~java
Object postProcessBeforeInitialization(Object bean, String beanName);

Object postProcessAfterInitialization(Object bean, String beanName);
~~~

Đây là chữ ký rút gọn để minh họa, bỏ qua annotation và những chi tiết khác của giao diện/API thực tế.

Các processor có thể:

- Thực hiện xử lý annotation lifecycle như `@PostConstruct`.
- Áp dụng logic tùy biến cho những bean phù hợp.
- Trong một số tích hợp Spring, tham gia việc tạo proxy hoặc bổ sung hành vi xung quanh bean.

Với AOP hoặc `@Transactional`, đối tượng mà nơi khác nhận được có thể là **proxy** thay vì chính instance implementation ban đầu. Điều này giúp Spring bổ sung hành vi như quản lý transaction, nhưng cũng khiến việc quan sát constructor, method interception và kiểu runtime cần được hiểu đúng.

Không nên mặc định rằng tất cả bean đều được proxy hóa; chỉ những bean phù hợp với cấu hình/điều kiện tương ứng mới đi qua các cơ chế proxy cần thiết.

### 9.1. BeanFactoryPostProcessor khác BeanPostProcessor

Hai tên gần giống nhưng thao tác ở hai tầng khác nhau.

| Cơ chế | Tác động chủ yếu | Thời điểm khái quát |
| --- | --- | --- |
| `BeanFactoryPostProcessor` | Metadata/configuration của bean factory, đặc biệt là bean definitions | Trước giai đoạn tạo các singleton ứng dụng thông thường |
| `BeanDefinitionRegistryPostProcessor` | Có thể bổ sung/chỉnh sửa đăng ký BeanDefinition | Khi registry đang được chuẩn bị |
| `BeanPostProcessor` | Các bean instance đang được tạo/khởi tạo | Quanh giai đoạn initialization của từng instance |

Ví dụ một `BeanFactoryPostProcessor` có thể điều chỉnh một số thuộc tính của định nghĩa bean; nó không phải callback thông thường để “sử dụng bean đã hoàn tất”.

Trong một ứng dụng nhập môn, bạn thường **không cần tự viết** các processor này. Hiểu chúng giúp giải thích vì sao Spring không chỉ đơn giản là tìm annotation rồi gọi `new`.

## 10. Initialization và application startup là hai thời điểm khác nhau

Trong một ứng dụng có nhiều bean, cần tách biệt hai mức:

- **Bean initialization:** một bean cụ thể đã được tạo, inject và gọi callback khởi tạo tương ứng.
- **Application startup:** application context đã được refresh và Spring Boot tiếp tục những callback ở mức ứng dụng như `ApplicationRunner` hoặc `CommandLineRunner`.

Ví dụ:

~~~java
@Component
class StartupTask implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Application startup task");
    }
}
~~~

`ApplicationRunner` và `ApplicationArguments` thuộc Spring Boot; chúng không phải lifecycle callback của riêng một bean service giống `@PostConstruct`.

Nếu cần một tác vụ chỉ chạy **sau khi application context đã sẵn sàng theo vòng đời Boot**, runner có thể phù hợp hơn là ép việc ấy vào `@PostConstruct` của một service tùy ý.

Tuy nhiên, runner vẫn chạy trong quá trình startup và exception từ nó có thể làm startup thất bại. Các công việc chậm, lặp định kỳ, cần retry hoặc cần đảm bảo giao dịch thường phải có thiết kế riêng thay vì đặt mặc định trong mọi callback.

### 10.1. Đừng nhầm `ApplicationReadyEvent` với `@PostConstruct`

Spring Boot còn phát sự kiện vòng đời ứng dụng như `ApplicationReadyEvent` gần cuối quá trình khởi động thành công, sau khi các runner liên quan đã hoàn tất. Listener cho sự kiện này phù hợp với một số nhu cầu thông báo hoặc điều phối ở mức ứng dụng.

Tính khả dụng của server, bean và tài nguyên phụ thuộc vào cấu hình thực tế. Không nên hiểu rằng mọi tài nguyên bên ngoài như database, message broker hay dịch vụ HTTP khác đã khỏe mạnh chỉ vì sự kiện ready được phát.

## 11. Quản lý thứ tự khởi tạo giữa các bean

Nếu bean A cần bean B qua constructor, Spring phải cung cấp B trước khi có thể hoàn thành A:

~~~java
@Service
class OrderService {
    OrderService(OrderRepository repository) {
        // repository cần có trước khi OrderService tạo xong
    }
}
~~~

Nhưng nếu hai bean **không có dependency với nhau**, đừng viết logic phụ thuộc vào thứ tự ngẫu nhiên mà chúng xuất hiện trong log.

Nếu thực sự cần khai báo quan hệ khởi tạo nhưng không thể biểu diễn bằng constructor, Spring có annotation `@DependsOn`:

~~~java
@Component
@DependsOn("schemaInitializer")
class ReportScheduler {
    // ...
}
~~~

Đoạn trên chỉ minh họa quan hệ; bean tên `schemaInitializer` phải được đăng ký. `@DependsOn` điều khiển một số quan hệ thứ tự tạo bean, **không tự inject** một object vào constructor hoặc bảo đảm hệ thống bên ngoài đã hoàn tất mọi công việc.

Trong phần lớn mã ứng dụng, quan hệ dependency được khai báo rõ qua constructor là dễ hiểu hơn. Nếu hai bean cần thứ tự initialization mà không có quan hệ cộng tác thực sự, hãy xác định đó có phải trách nhiệm của một thành phần orchestration hoặc lifecycle ở mức ứng dụng hay không.

## 12. Khi nào bean được hủy?

Bài học tập trung vào registration → instantiation → injection → initialization, nhưng bean lifecycle còn có giai đoạn **destruction**.

Với singleton phù hợp, khi Spring context đóng bình thường, container có thể gọi:

- Method mang `@PreDestroy` (Jakarta).
- `DisposableBean.destroy()` nếu bean triển khai interface này.
- Custom destroy method nếu được khai báo.
- Một số cơ chế suy luận destroy method phù hợp đối với bean được tạo qua `@Bean`.

Ví dụ:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

@Component
public class ManagedWorker {

    @PostConstruct
    public void start() {
        System.out.println("Worker initialized");
    }

    @PreDestroy
    public void stop() {
        System.out.println("Worker stopping");
    }
}
~~~

Những callback này liên quan đến đối tượng **do Spring quản lý** và vòng đời context. Không nên giả định `@PreDestroy` luôn chạy khi JVM bị tắt cưỡng bức, crash hoặc bị kill không có cơ hội shutdown bình thường.

Đối với prototype, container thường không theo dõi việc hủy mọi instance sau khi cấp phát. Với tài nguyên cần giải phóng, người sử dụng hoặc cơ chế quản lý scope tương ứng phải có chiến lược rõ ràng.

## 13. Những lỗi thường gặp gắn với từng giai đoạn

Nhìn vào giai đoạn đang thất bại giúp khoanh vùng lỗi nhanh hơn.

| Dấu hiệu | Giai đoạn liên quan | Hướng kiểm tra |
| --- | --- | --- |
| Không tìm thấy bean `OrderRepository` | Đăng ký/giải quyết dependency | Package scan, annotation, `@Bean`, điều kiện cấu hình |
| Có hai bean cùng kiểu, Spring không chọn được | Dependency resolution | `@Qualifier`, `@Primary` hoặc thiết kế nhiều implementation |
| Constructor ném exception | Instantiation | Nguyên nhân thực tế trong constructor và dependency đầu vào |
| Field `@Autowired` chưa có trong constructor | Instantiation trước field injection | Chuyển dependency bắt buộc sang constructor |
| Method `@PostConstruct` ném exception | Initialization | Logic chuẩn bị, cấu hình, tài nguyên cần thiết |
| Bean không xuất hiện lúc startup nhưng tạo khi gọi endpoint | Có thể liên quan lazy/scope | `@Lazy`, `spring.main.lazy-initialization`, scope, đường dependency |
| Runtime dùng bean proxy, kiểu hoặc call path khác dự kiến | Post-processing/AOP | Cấu hình AOP, transaction, proxy và cách gọi method |

### 13.1. Không có bean phù hợp

Ví dụ:

~~~text
No qualifying bean of type '...OrderRepository' available
~~~

Các nguyên nhân có thể:

1. Implementation chưa được đánh dấu hoặc chưa được đăng ký qua `@Bean`.
2. Package không nằm trong phạm vi component scan.
3. Auto-configuration liên quan không được kích hoạt vì thiếu dependency/điều kiện.
4. Bean bị vô hiệu hóa bởi profile hoặc condition.
5. Kiểu mà constructor yêu cầu không tương thích với các bean hiện có.

Không nên giải quyết bằng cách thêm `@ComponentScan` bao phủ toàn bộ project một cách tùy tiện. Trước tiên cần hiểu module/package nào thực sự sở hữu bean.

### 13.2. Nhiều bean cùng hợp đồng

Nếu cần một `PaymentGateway` nhưng có hai implementation `CardGateway` và `MockGateway` đều được đăng ký, container cần một cách chọn hợp lệ. Trong ứng dụng thật, mock implementation không nên mặc nhiên xuất hiện ở production chỉ để phục vụ test.

Có thể dùng profile, condition, qualifier hoặc cấu hình bean để diễn đạt rõ implementation nào được sử dụng trong hoàn cảnh nào.

### 13.3. Circular dependency

Ví dụ:

~~~text
ServiceA ──constructor──► ServiceB
ServiceB ──constructor──► ServiceA
~~~

Để tạo A cần B; để tạo B lại cần A. Đây là **circular dependency**. Với constructor injection bắt buộc ở cả hai phía, container không thể hoàn tất chuỗi tạo object theo cách thông thường.

Spring Boot 3.x mặc định không khuyến khích các vòng phụ thuộc kiểu này và thường báo lỗi khi không giải quyết được. Cách sửa tốt là xem lại trách nhiệm:

- Có logic nào đáng lẽ thuộc một service thứ ba không?
- Hai service có đang ôm quá nhiều trách nhiệm không?
- Có một luồng điều phối cấp cao đang bị đặt nhầm vào service thấp hơn không?

Dùng lazy reference hoặc setter để lách lỗi có thể che giấu vấn đề thiết kế. Chỉ sử dụng khi thực sự hiểu rõ dependency và vòng đời.

### 13.4. Constructor chạy nhưng `@PostConstruct` không chạy

Các khả năng đáng xem xét:

- Đối tượng được tạo bằng `new` ngoài container, nên Spring không xử lý lifecycle.
- Bean không được Spring đăng ký hoặc không đi qua cơ chế xử lý annotation thích hợp.
- Đoạn mã thực tế đang dùng một instance khác với instance mà bạn đang quan sát.
- Quá trình tạo bean đã thất bại trước khi đến initialization.

Đừng vội cho rằng annotation sai. Hãy xác định **đối tượng được tạo bởi ai** và Spring có đang quản lý instance đó không.

### 13.5. Initialization thất bại làm ứng dụng không khởi động

Ví dụ một `@PostConstruct` cố kết nối database và ném exception. Nếu đây là bean cần tạo trong quá trình startup, lỗi initialization có thể khiến toàn bộ refresh context thất bại.

Thông báo bên ngoài thường mang dạng `BeanCreationException`. Cần đọc **cause** sâu trong stack trace để biết logic nào thực sự gây lỗi, thay vì chỉ thấy tên bean rồi sửa annotation.

Đôi khi một kết nối bên ngoài cần chiến lược retry, health check hoặc initialization ở giai đoạn khác. Điều đó phải được thiết kế theo nghiệp vụ và đặc điểm hệ thống, thay vì mặc định đặt mọi I/O trong `@PostConstruct`.

## 14. Quan sát vòng đời bean bằng công cụ phù hợp

### 14.1. Log constructor và callback

Trong môi trường học tập, việc thêm log tại constructor và `@PostConstruct` giúp phân biệt creation và initialization:

~~~java
@Service
class InventoryService {
    InventoryService() {
        System.out.println("[constructor] InventoryService");
    }

    @PostConstruct
    void initialize() {
        System.out.println("[init] InventoryService");
    }
}
~~~

Log minh họa trật tự trong phạm vi bean này. Không suy ra thứ tự của mọi bean khác trong toàn ứng dụng từ vài dòng log, vì nhiều định nghĩa được xử lý qua các cơ chế khác nhau.

Trong ứng dụng thực tế, nên dùng logger có cấu hình thay vì in dữ liệu nhạy cảm ra stdout.

### 14.2. Xác định bean nào đã được đăng ký

`ApplicationContext` cho phép truy vấn danh sách bean definition names:

~~~java
@Bean
CommandLineRunner showBeanName(ApplicationContext context) {
    return args -> {
        for (String name : context.getBeanDefinitionNames()) {
            if (name.toLowerCase().contains("greeting")) {
                System.out.println("Bean definition: " + name);
            }
        }
    };
}
~~~

Đoạn trên dùng `ApplicationContext` và `CommandLineRunner`, với import cần thiết trong một class cấu hình Spring Boot. Nó có thể giúp quan sát các tên bean đã được đăng ký.

**Danh sách BeanDefinition không phải danh sách bằng chứng rằng mọi instance đều đã được tạo**. Phương thức `getBeanDefinitionNames()` nói về đăng ký; phương thức `getBean(...)` có thể kích hoạt tạo bean lazy khi được gọi.

### 14.3. Debug auto-configuration

Spring Boot có thể in báo cáo đánh giá các điều kiện auto-configuration khi bật debug:

~~~bash
java -jar app.jar --debug
~~~

Thông tin này hữu ích khi bạn muốn biết vì sao một auto-configuration được áp dụng hoặc không. Tên file JAR `app.jar` chỉ là ví dụ, cần thay bằng artifact thực tế.

Báo cáo điều kiện không thể tự giải thích mọi lỗi DI. Kết hợp với exception stack trace, package scan, danh sách bean và dependency graph để tìm nguyên nhân chính xác.

## 15. Bài thực hành: đoán lúc nào bean được tạo

### Bài A. BeanDefinition có phải instance?

Cho:

~~~java
@Lazy
@Component
class ExportService {
    ExportService() {
        System.out.println("ExportService constructor");
    }
}
~~~

Câu hỏi: nếu ứng dụng scan được `ExportService`, có chắc dòng log constructor xuất hiện ngay khi khởi động không?

**Gợi ý:** Không. Spring có thể đăng ký định nghĩa nhưng trì hoãn việc tạo instance do lazy. Nếu một bean eager cần trực tiếp `ExportService`, việc giải quyết dependency có thể làm nó được tạo sớm hơn bạn dự đoán.

### Bài B. Đọc thứ tự callback

Cho:

~~~java
@Component
class SampleService {
    SampleService() {
        System.out.println("A: constructor");
    }

    @PostConstruct
    void init() {
        System.out.println("B: @PostConstruct");
    }
}
~~~

Câu hỏi: trong quá trình tạo một instance do container quản lý theo cơ chế thông thường, log nào xuất hiện trước?

**Gợi ý:** `A` xuất hiện khi constructor chạy; `B` là initialization callback nên xuất hiện sau khi instance được tạo và phần injection cần thiết hoàn thành.

### Bài C. Constructor và field injection

Cho:

~~~java
@Component
class AuditService {
    @Autowired
    private AuditClient client;

    AuditService() {
        System.out.println(client);
    }
}
~~~

Câu hỏi: vì sao constructor có thể in `null`?

**Gợi ý:** Field injection diễn ra **sau khi constructor chạy**. `AuditClient` là kiểu giả định cần có bean tương ứng; cách tránh phụ thuộc chưa khởi tạo là yêu cầu `AuditClient` qua constructor.

### Bài D. Phân biệt component scan và `@Bean`

Cho:

~~~java
@Configuration
class ToolsConfiguration {
    @Bean
    Formatter formatter() {
        return new JsonFormatter();
    }
}
~~~

Trong ví dụ, `Formatter` và `JsonFormatter` là các kiểu minh họa.

Câu hỏi: `JsonFormatter` có nhất thiết cần `@Component` không?

**Gợi ý:** Không. Container có định nghĩa bean qua `@Bean` factory method. Class implementation không phải được component scan trực tiếp để tạo bean từ phương pháp này.

### Bài E. Nhiều implementation

Cho:

~~~java
interface Notifier {
    void notify(String text);
}

@Component
class MailNotifier implements Notifier {
    public void notify(String text) {
        System.out.println("MAIL " + text);
    }
}

@Component
class SmsNotifier implements Notifier {
    public void notify(String text) {
        System.out.println("SMS " + text);
    }
}
~~~

Và:

~~~java
@Service
class AlertService {
    AlertService(Notifier notifier) {
        // ...
    }
}
~~~

Câu hỏi: Spring có đủ thông tin để chắc chắn chọn một bean `Notifier` chưa? Có thể sửa bằng những cách nào?

**Gợi ý:** Khi có hai candidate hợp lệ mà không có quy tắc ưu tiên phù hợp, injection có thể thất bại. Có thể dùng `@Qualifier`, `@Primary` hoặc đăng ký chỉ implementation thật sự cần.

### Bài F. Tìm dependency graph

Cho:

~~~text
OrderController → OrderService → OrderRepository → DataSource
~~~

Hãy giải thích:

1. Những loại bean definition nào cần xuất hiện để container có thể tạo đầy đủ các đối tượng?
2. Nếu `OrderRepository` bị thiếu, việc tạo `OrderService` sẽ ra sao?
3. `OrderController` có nên tự `new OrderRepository(...)` không?
4. Nếu constructor `DataSource` hoặc factory tạo datasource thất bại, vì sao lỗi có thể xuất hiện ở quá trình startup của một service cấp cao?

**Gợi ý:** Spring phải giải quyết dependency để tạo bean theo đồ thị; lỗi ở bean thấp có thể lan lên bean yêu cầu nó. DI giúp tách quyết định tạo dependency khỏi logic sử dụng.

## 16. Những nguyên tắc cần giữ khi viết ứng dụng Spring Boot

Khi thiết kế class và bean, hãy tự hỏi:

- **Bean có được đăng ký chưa?** Kiểm tra annotation, cấu hình `@Bean`, package scan và các condition.
- **Bean được tạo khi nào?** Kiểm tra scope, lazy và dependency từ các singleton eager.
- **Ai cung cấp các cộng tác viên?** Ưu tiên constructor injection cho dependency bắt buộc.
- **Bean đang nhận implementation nào?** Nếu có nhiều candidate, sử dụng quy tắc lựa chọn rõ ràng.
- **Initialization đặt ở đâu?** Callback nên xử lý việc chuẩn bị của bean, không tùy tiện làm thay toàn bộ application startup orchestration.
- **Có phụ thuộc vào thứ tự ngẫu nhiên không?** Dùng dependency rõ ràng hoặc cơ chế lifecycle thích hợp thay vì dựa trên log.
- **Ai quản lý lifecycle?** Đối tượng được tạo bằng `new` bên ngoài container không tự hưởng mọi callback và cơ chế bean của Spring.

Hiểu được sự phân biệt giữa **BeanDefinition**, **bean instance**, **dependency resolution** và **initialization callback** giúp đọc được phần lớn các lỗi startup thường gặp: thiếu bean, nhiều bean cùng kiểu, vòng phụ thuộc, constructor ném lỗi hoặc khởi tạo tài nguyên thất bại.

Spring Boot giúp khởi động context và cung cấp nhiều định nghĩa hạ tầng mặc định; Spring Framework thực hiện phần lớn việc quản lý bean. Trong luồng thông thường, container **đăng ký cách tạo bean**, **quyết định thời điểm tạo**, **giải quyết dependency để tạo object**, **inject các thành phần cần thiết**, rồi **chạy initialization callback** trước khi bean được sử dụng theo thiết kế. Nắm được từng bước này là nền tảng để học tiếp bean scopes, auto-configuration, AOP, transaction và lifecycle của ứng dụng Spring Boot.

