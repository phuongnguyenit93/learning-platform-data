# proxyBeanMethods=true hoặc false và tác động tới instance được sử dụng

Trong Spring Boot, một class cấu hình thường khai báo nhiều bean bằng các phương thức có annotation `@Bean`. Một phương thức có thể tạo `Formatter`, phương thức khác tạo `GreetingService` và service lại cần formatter đó.

Câu hỏi quan trọng là: nếu phương thức `greetingService()` gọi trực tiếp `formatter()`, nó có nhận đúng bean `Formatter` mà Spring đang quản lý hay tạo thêm một object mới?

Câu trả lời phụ thuộc vào thuộc tính `proxyBeanMethods` của annotation `@Configuration`:

- `proxyBeanMethods = true`: Spring tăng cường class cấu hình bằng proxy CGLIB để điều phối lời gọi giữa các `@Bean` method. Khi một `@Bean` method gọi một `@Bean` method khác trên instance cấu hình được quản lý, lời gọi được chuyển qua container để trả về bean phù hợp với scope.
- `proxyBeanMethods = false`: Spring không tạo proxy cho class cấu hình chỉ để chặn các lời gọi `@Bean` method. Một lời gọi trực tiếp giữa các method là lời gọi Java thông thường; nó có thể tạo object mới ngoài bean instance mà container đang quản lý.

Mặc định của `@Configuration` là `proxyBeanMethods = true`. Chọn `false` không làm Spring ngừng quản lý bean và cũng không tắt Dependency Injection. Nó chỉ thay đổi cách xử lý **lời gọi trực tiếp giữa các phương thức `@Bean` trong class cấu hình**.

Bài học dùng một ví dụ nhỏ để nhìn thấy sự khác biệt về identity của object, sau đó giải thích cách viết cấu hình an toàn trong cả hai chế độ.

## 1. @Bean method là factory method của Spring

Xét cấu hình:

~~~java
@Configuration
public class AppConfig {

    @Bean
    public MessageFormatter messageFormatter() {
        return new MessageFormatter();
    }

    @Bean
    public GreetingService greetingService() {
        return new GreetingService(messageFormatter());
    }
}
~~~

Hai phương thức có nhiệm vụ:

- `messageFormatter()` cung cấp một bean kiểu `MessageFormatter`.
- `greetingService()` cung cấp một bean kiểu `GreetingService`.

Spring đăng ký các định nghĩa bean từ metadata của class cấu hình. Khi container tạo bean, nó gọi factory method tương ứng và quản lý object được trả về.

Tuy nhiên, trong `greetingService()` có lời gọi Java:

~~~java
messageFormatter()
~~~

Đây là điểm cần chú ý. Nếu lời gọi ấy được xử lý qua proxy cấu hình, Spring có thể trả về bean `messageFormatter` đã quản lý. Nếu không được intercept, Java chỉ thực thi thân method và tạo object theo câu lệnh `new` trong đó.

Do đó, cùng một đoạn code có thể dẫn đến hai kết quả khác nhau tùy `proxyBeanMethods`.

## 2. proxyBeanMethods=true: full configuration mode

`@Configuration` mặc định có `proxyBeanMethods = true`:

~~~java
@Configuration(proxyBeanMethods = true)
public class AppConfig {
    // Các @Bean method
}
~~~

Có thể viết ngắn hơn vì `true` là mặc định:

~~~java
@Configuration
public class AppConfig {
    // Các @Bean method
}
~~~

Ở chế độ này, Spring sử dụng cơ chế enhancement dựa trên CGLIB để tạo subclass proxy cho class cấu hình. Proxy intercept các lời gọi `@Bean` method phù hợp, đặc biệt là lời gọi giữa các bean method trong cùng một class cấu hình.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = true)
public class AppConfig {

    @Bean
    public MessageFormatter messageFormatter() {
        System.out.println("Create MessageFormatter");
        return new MessageFormatter();
    }

    @Bean
    public GreetingService greetingService() {
        System.out.println("Create GreetingService");
        return new GreetingService(messageFormatter());
    }
}
~~~

Khi Spring tạo `greetingService` và thực thi `messageFormatter()` trên configuration proxy, lời gọi được intercept. Container tra cứu bean `messageFormatter` và trả về instance đã quản lý theo scope của bean.

Với scope mặc định `singleton`:

~~~text
Spring container
      │
      ├── tạo bean messageFormatter
      │         │
      │         ▼
      │   MessageFormatter #1
      │
      └── tạo bean greetingService
                │
                └── gọi messageFormatter()
                       │
                       ▼
                Configuration proxy intercept
                       │
                       ▼
                Container trả MessageFormatter #1
~~~

Kết quả: bean `GreetingService` sử dụng cùng instance `MessageFormatter` mà container cung cấp. Không có một formatter singleton thứ hai chỉ vì method cấu hình được gọi thêm lần nữa.

### 2.1. Vì sao cần proxy?

Nếu chỉ dùng Java thuần, gọi method:

~~~java
messageFormatter()
~~~

luôn thực thi thân method theo quy tắc Java. Với CGLIB-enhanced configuration class, Spring có thể thay đổi hành vi của lời gọi trên instance proxy để tra cứu bean trong container.

Cơ chế này bảo đảm các lời gọi giữa bean method tuân theo vòng đời và scope của bean do Spring quản lý.

Nói cách khác, `proxyBeanMethods=true` giúp các `@Bean` method có thể gọi lẫn nhau theo cách gần với việc tham chiếu đến bean đã được inject, ngay cả khi cú pháp trong method là lời gọi Java trực tiếp.

### 2.2. Điều kiện và giới hạn của proxy cấu hình

Vì Spring cần tạo subclass bằng CGLIB:

- Class cấu hình phải có khả năng được subclass; class `final` không phù hợp với full configuration proxy.
- Các instance `@Bean` method cần được override/intercept; không khai báo method đó là `private` hoặc `final` nếu cần interception.
- Một lời gọi trên object cấu hình tự tạo bằng `new AppConfig()` không đi qua proxy do Spring quản lý.
- Cơ chế proxy không biến mọi lời gọi Java đến bất kỳ method nào thành tra cứu bean; nó tập trung vào các `@Bean` method phù hợp.

Các giới hạn này là lý do một số cấu hình chọn `proxyBeanMethods=false` khi không cần inter-bean method call.

## 3. proxyBeanMethods=false: lite configuration mode

Khi khai báo:

~~~java
@Configuration(proxyBeanMethods = false)
public class AppConfig {
    // Các @Bean method
}
~~~

Spring không enhancement class cấu hình bằng CGLIB chỉ để intercept các lời gọi giữa `@Bean` method.

Spring vẫn:

- Phát hiện class cấu hình.
- Đăng ký bean definition cho các phương thức `@Bean`.
- Gọi factory method để tạo các bean tương ứng.
- Quản lý instance được trả về theo scope.
- Thực hiện dependency injection và các callback vòng đời cho những bean do container quản lý.

Điều thay đổi là lời gọi trực tiếp từ method này sang method khác trong class cấu hình trở thành **lời gọi Java thông thường**.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
public class AppConfig {

    @Bean
    public MessageFormatter messageFormatter() {
        System.out.println("Create MessageFormatter");
        return new MessageFormatter();
    }

    @Bean
    public GreetingService greetingService() {
        System.out.println("Create GreetingService");
        return new GreetingService(messageFormatter());
    }
}
~~~

Khi container tạo bean `messageFormatter`, nó gọi factory method và quản lý object trả về, gọi là `MessageFormatter #1`.

Khi container tạo `greetingService`, method `greetingService()` gọi trực tiếp `messageFormatter()` như một method Java bình thường. Câu lệnh `new MessageFormatter()` chạy lần nữa, tạo `MessageFormatter #2`.

`GreetingService` nhận `MessageFormatter #2`, còn bean `messageFormatter` mà container quản lý vẫn là `MessageFormatter #1`.

~~~text
Spring container
      │
      ├── gọi @Bean messageFormatter()
      │         │
      │         ▼
      │   MessageFormatter #1
      │   (bean được quản lý)
      │
      └── gọi @Bean greetingService()
                │
                └── gọi trực tiếp messageFormatter()
                       │
                       ▼
                 Java thực thi thân method
                       │
                       ▼
                MessageFormatter #2
                (object tạo trực tiếp)
                       │
                       ▼
                GreetingService sử dụng #2
~~~

Đây là khác biệt quan trọng nhất của `proxyBeanMethods=false`: **container vẫn quản lý bean được tạo bởi factory method, nhưng lời gọi trực tiếp giữa các factory method không tự động lấy lại bean từ container**.

## 4. Minh họa bằng identity của object

Để thấy rõ hai chế độ, ta định nghĩa hai class đơn giản.

`MessageFormatter.java`:

~~~java
public class MessageFormatter {
    public String format(String name) {
        return "Hello, " + name;
    }
}
~~~

`GreetingService.java`:

~~~java
public class GreetingService {
    private final MessageFormatter formatter;

    public GreetingService(MessageFormatter formatter) {
        this.formatter = formatter;
    }

    public MessageFormatter formatter() {
        return formatter;
    }

    public String greet(String name) {
        return formatter.format(name);
    }
}
~~~

Configuration:

~~~java
@Configuration(proxyBeanMethods = true) // Thử đổi thành false
public class AppConfig {

    @Bean
    public MessageFormatter messageFormatter() {
        return new MessageFormatter();
    }

    @Bean
    public GreetingService greetingService() {
        return new GreetingService(messageFormatter());
    }
}
~~~

Kiểm tra trong context:

~~~java
try (var context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {

    MessageFormatter beanFormatter =
            context.getBean(MessageFormatter.class);

    GreetingService service =
            context.getBean(GreetingService.class);

    System.out.println(
            beanFormatter == service.formatter()
    );
}
~~~

Kết quả dự kiến:

| Cấu hình | Kết quả so sánh | Ý nghĩa |
| --- | --- | --- |
| `proxyBeanMethods = true` | `true` | Service nhận cùng instance bean formatter |
| `proxyBeanMethods = false` | `false` | Lời gọi trực tiếp tạo formatter khác với bean trong context |

`==` so sánh identity của hai reference, không so sánh nội dung object. Hai object có cùng dữ liệu vẫn có thể là hai instance khác nhau.

Đây là một minh họa cho cấu hình đơn giản với scope mặc định singleton và method gọi trực tiếp như trên. Khi có scope khác, factory method khác hoặc proxy khác, cần phân tích thêm quy tắc tương ứng.

## 5. Cách viết an toàn: truyền dependency qua tham số @Bean method

Nếu muốn dùng `proxyBeanMethods=false` mà vẫn bảo đảm các bean nhận dependency do container quản lý, hãy khai báo dependency trong tham số của factory method.

~~~java
@Configuration(proxyBeanMethods = false)
public class AppConfig {

    @Bean
    public MessageFormatter messageFormatter() {
        return new MessageFormatter();
    }

    @Bean
    public GreetingService greetingService(
            MessageFormatter messageFormatter) {
        return new GreetingService(messageFormatter);
    }
}
~~~

Spring thấy tham số `MessageFormatter messageFormatter` và giải quyết dependency qua container. Nó truyền bean `messageFormatter` đã quản lý vào factory method.

Luồng:

~~~text
Spring tạo bean messageFormatter
              │
              ▼
      MessageFormatter #1
              │
              │ container resolve tham số
              ▼
Spring gọi greetingService(messageFormatter)
              │
              ▼
GreetingService nhận #1
~~~

Với cách này:

- Không cần gọi trực tiếp `messageFormatter()`.
- Không cần proxy cấu hình để chia sẻ dependency.
- Bean được quản lý theo scope của container.
- Cấu hình hoạt động đúng cả khi `proxyBeanMethods=true` lẫn `false`.
- Quan hệ dependency được thể hiện rõ trong chữ ký factory method.

Đây là cách viết nên ưu tiên khi một `@Bean` method cần một bean khác.

### 5.1. Tham số @Bean method hỗ trợ qualifier

Nếu có nhiều bean cùng kiểu, có thể dùng `@Qualifier` trên tham số:

~~~java
@Bean
public GreetingService greetingService(
        @Qualifier("vietnameseFormatter")
        MessageFormatter formatter) {
    return new GreetingService(formatter);
}
~~~

Container chọn bean có qualifier phù hợp. Cách này không phụ thuộc vào việc configuration class có được proxy hay không.

### 5.2. Có thể truyền nhiều dependency

~~~java
@Bean
public GreetingService greetingService(
        MessageFormatter formatter,
        GreetingRepository repository,
        Clock clock) {
    return new GreetingService(formatter, repository, clock);
}
~~~

`GreetingRepository` và `Clock` là các kiểu giả định cần được đăng ký phù hợp. Spring resolve từng tham số như dependency của bean đang tạo.

Cách này giúp factory method đóng vai trò composition point: nó nhận những dependency do container quản lý rồi tạo object mới với chúng.

## 6. So sánh hai chế độ trong cùng một bảng

| Nội dung | `proxyBeanMethods=true` | `proxyBeanMethods=false` |
| --- | --- | --- |
| Giá trị mặc định của `@Configuration` | Có | Không |
| Class cấu hình được CGLIB enhance để intercept bean method calls | Có | Không |
| Lời gọi trực tiếp `otherBean()` từ một `@Bean` method | Được intercept và tra cứu bean phù hợp | Là lời gọi Java bình thường |
| Có thể nhận cùng singleton khi gọi chéo bean method | Có, theo scope của bean | Không bảo đảm; thường tạo object mới nếu thân method có `new` |
| Bean do container gọi factory method | Được quản lý | Được quản lý |
| Constructor/parameter injection | Có | Có |
| Dependency qua tham số `@Bean` | Có | Có |
| Phù hợp với cấu hình không gọi chéo bean method | Có thể dùng | Rất phù hợp |
| Cần enhancement configuration class | Có | Không cần cho mục đích inter-bean method interception |

Điều quan trọng không phải chế độ nào “quản lý bean tốt hơn”. Cả hai đều cho phép container quản lý bean definition và instance. Khác biệt nằm ở **lời gọi method trong class cấu hình**.

## 7. @Component có @Bean method thường ở lite mode

`@Bean` method không chỉ xuất hiện trong class `@Configuration`. Spring cũng cho phép khai báo nó trong các component thông thường.

Ví dụ:

~~~java
@Component
public class FormatterFactory {

    @Bean
    public MessageFormatter messageFormatter() {
        return new MessageFormatter();
    }
}
~~~

Class `FormatterFactory` không phải full `@Configuration` class. Các `@Bean` method bên trong nó được xử lý theo lite configuration semantics; không có configuration class proxy để intercept lời gọi giữa các bean method.

Nếu viết:

~~~java
@Component
public class FormatterFactory {

    @Bean
    public MessageFormatter messageFormatter() {
        return new MessageFormatter();
    }

    @Bean
    public GreetingService greetingService() {
        return new GreetingService(messageFormatter());
    }
}
~~~

lời gọi `messageFormatter()` trong `greetingService()` là lời gọi Java thông thường. Nó có thể tạo object khác với bean `messageFormatter` trong context.

Có thể viết lại:

~~~java
@Component
public class FormatterFactory {

    @Bean
    public MessageFormatter messageFormatter() {
        return new MessageFormatter();
    }

    @Bean
    public GreetingService greetingService(
            MessageFormatter messageFormatter) {
        return new GreetingService(messageFormatter);
    }
}
~~~

Khi đó container resolve tham số và cung cấp đúng bean.

Lưu ý: `proxyBeanMethods` là thuộc tính của `@Configuration`. Không thể đặt thuộc tính đó lên `@Component` thông thường để yêu cầu Spring intercept bean method. Nếu class chỉ là component chứa factory method, hãy dùng tham số method để diễn đạt dependency.

## 8. Ảnh hưởng của scope bean

Ví dụ trước dùng scope mặc định `singleton`. Nhưng Spring còn hỗ trợ các scope khác như `prototype` và web scopes.

Trong full configuration mode, khi một `@Bean` method được gọi thông qua configuration proxy, lời gọi được chuyển qua container. Vì vậy container có thể áp dụng scope tương ứng thay vì chạy trực tiếp thân method.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = true)
public class PrototypeConfiguration {

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    public TaskContext taskContext() {
        return new TaskContext();
    }

    @Bean
    public TaskRunner taskRunner() {
        return new TaskRunner(taskContext());
    }
}
~~~

Trong ví dụ, `taskContext()` được intercept và container giải quyết bean theo scope prototype. Mỗi lần container cần lấy bean prototype, nó có thể tạo instance mới.

Nhưng nếu chuyển thành `proxyBeanMethods=false` mà vẫn gọi trực tiếp `taskContext()` trong `taskRunner()`, Java thực thi method như bình thường. Object được tạo trực tiếp không đi qua scope resolution của container như một lần `getBean`.

Điều này không chỉ liên quan singleton hay prototype. Một lời gọi trực tiếp trong lite mode cũng không tự chạy toàn bộ quá trình bean creation, dependency injection, BeanPostProcessor và lifecycle callback cho object được tạo ngoài container.

### 8.1. Prototype được inject vào singleton cần chú ý riêng

Ngay cả khi dùng constructor injection:

~~~java
@Bean
public TaskRunner taskRunner(TaskContext taskContext) {
    return new TaskRunner(taskContext);
}
~~~

nếu `TaskRunner` là singleton và `TaskContext` là prototype, container thường giải quyết `TaskContext` một lần khi tạo singleton `TaskRunner`. Nó không tự lấy prototype mới cho mỗi lần gọi method của runner.

Nếu cần instance mới mỗi lần, cân nhắc `ObjectProvider<TaskContext>`:

~~~java
@Bean
public TaskRunner taskRunner(ObjectProvider<TaskContext> taskContexts) {
    return new TaskRunner(taskContexts);
}
~~~

Sau đó `TaskRunner` gọi `taskContexts.getObject()` khi cần object mới. `ObjectProvider` là API của Spring để truy xuất dependency theo yêu cầu.

Đây là một vấn đề scope/prototype injection, không phải lý do để dựa vào lời gọi chéo `@Bean` method.

## 9. @Bean method có thể gọi bean khác theo cách nào?

Có ba kiểu viết thường gặp:

### Cách A: Gọi trực tiếp method

~~~java
@Bean
GreetingService greetingService() {
    return new GreetingService(messageFormatter());
}
~~~

- Với `proxyBeanMethods=true` trong full configuration class: lời gọi được intercept.
- Với `proxyBeanMethods=false` hoặc lite configuration: lời gọi là Java trực tiếp.

Cách này dễ gây hiểu nhầm khi chuyển chế độ.

### Cách B: Inject qua tham số factory method

~~~java
@Bean
GreetingService greetingService(MessageFormatter formatter) {
    return new GreetingService(formatter);
}
~~~

Container giải quyết dependency và truyền bean phù hợp. Cách này hoạt động nhất quán ở cả hai chế độ.

### Cách C: Inject qua constructor của component

~~~java
@Service
public class GreetingService {
    private final MessageFormatter formatter;

    public GreetingService(MessageFormatter formatter) {
        this.formatter = formatter;
    }
}
~~~

Spring tạo bean service và inject formatter qua constructor. Đây thường là lựa chọn rõ ràng cho service/controller/component thông thường.

**Ưu tiên B hoặc C khi có dependency giữa các bean.** Cách A vẫn có thể hợp lệ trong full configuration mode khi bạn chủ động cần inter-bean method call, nhưng nó tạo sự phụ thuộc vào proxy configuration.

## 10. @Configuration(proxyBeanMethods=false) có nghĩa là Spring không còn DI?

Không. Đây là một hiểu nhầm phổ biến.

Với:

~~~java
@Configuration(proxyBeanMethods = false)
public class AppConfig {

    @Bean
    public MessageFormatter messageFormatter() {
        return new MessageFormatter();
    }

    @Bean
    public GreetingService greetingService(
            MessageFormatter formatter) {
        return new GreetingService(formatter);
    }
}
~~~

Spring vẫn:

1. Phát hiện class cấu hình.
2. Đăng ký bean definition cho `messageFormatter` và `greetingService`.
3. Tạo object qua factory method.
4. Resolve tham số `formatter` từ container.
5. Inject dependency và quản lý bean theo scope.
6. Thực hiện lifecycle processing tương ứng.

Chỉ không có CGLIB enhancement để biến lời gọi `messageFormatter()` trong thân một method khác thành lookup bean.

Ngoài ra, `proxyBeanMethods=false` không tắt AOP proxy cho service, không tắt transaction proxy và không thay đổi việc inject bean vào controller. Các cơ chế đó thuộc các phần khác của Spring.

## 11. @Configuration(proxyBeanMethods=false) có phải lúc nào cũng nhanh hơn?

Không nên quyết định chỉ dựa trên tốc độ.

`false` tránh việc enhancement class cấu hình để intercept inter-bean method calls. Điều đó có thể giảm một phần overhead và cho phép cấu hình đơn giản hơn, nhưng chênh lệch hiệu năng thường không phải yếu tố lớn nhất trong ứng dụng thông thường.

Yếu tố quan trọng hơn là semantics:

- Nếu các `@Bean` method gọi trực tiếp lẫn nhau và bạn muốn container trả đúng bean theo scope, `true` phù hợp.
- Nếu dependency được truyền qua tham số method hoặc constructor, `false` thường đơn giản và rõ ràng.
- Nếu không cần inter-bean method call, không cần bật proxy chỉ vì nghĩ rằng Spring sẽ không quản lý bean nếu thiếu nó.

Nhiều auto-configuration của Spring Boot sử dụng cấu hình không proxy khi các dependency đã được biểu diễn qua tham số method. Đây là một cách giảm phụ thuộc vào interception và giúp cấu hình dễ hiểu.

## 12. Giới hạn khi dùng full configuration proxy

### 12.1. Class cấu hình final

CGLIB cần subclass class cấu hình. Một class `final` không thể được subclass:

~~~java
@Configuration
public final class AppConfig {
    // Không phù hợp với full configuration proxy.
}
~~~

Nếu class không cần inter-bean method interception, có thể cân nhắc:

~~~java
@Configuration(proxyBeanMethods = false)
public final class AppConfig {
    // Lite configuration semantics.
}
~~~

Tuy nhiên, việc thay chế độ chỉ an toàn khi không dựa vào lời gọi chéo `@Bean` method để lấy bean container-managed.

### 12.2. @Bean method private hoặc final

Trong full configuration mode, Spring cần intercept lời gọi `@Bean` method thông qua override. Method `private` hoặc `final` không thể được override như cách CGLIB cần.

Nếu cần full mode, hãy để bean methods có thể override. Nếu muốn method private/final hoặc class cấu hình final, hãy đánh giá lite mode và dùng tham số dependency.

### 12.3. Tự tạo configuration bằng new

Ví dụ:

~~~java
AppConfig config = new AppConfig();
MessageFormatter formatter = config.messageFormatter();
~~~

Đây là Java object được tạo thủ công, không phải instance configuration proxy mà Spring quản lý. Lời gọi method chỉ thực thi thân method; không thể mong đợi container intercept và trả bean singleton.

Nếu cần bean do Spring quản lý, hãy lấy từ context hoặc inject vào consumer. Không tự tạo class cấu hình để truy cập bean method.

## 13. Phân biệt configuration proxy với AOP proxy

Cả hai đều có thể dùng proxy, nhưng mục đích khác nhau.

| Cơ chế | Mục tiêu |
| --- | --- |
| `@Configuration(proxyBeanMethods=true)` | Intercept lời gọi giữa các `@Bean` method để trả bean theo container/scope |
| Spring AOP proxy | Bọc lời gọi method của bean để áp dụng advice như transaction, security hoặc logging |
| `@Lazy` proxy | Trì hoãn việc resolve/khởi tạo dependency trong những tình huống phù hợp |

Không nên nhầm `proxyBeanMethods=false` với việc tắt AOP hoặc tắt mọi proxy trong ứng dụng. Nó chỉ điều khiển proxy enhancement của configuration class.

Ví dụ một service vẫn có thể dùng `@Transactional` trong ứng dụng có `@Configuration(proxyBeanMethods=false)`. Hai cơ chế không phụ thuộc nhau theo nghĩa bật/tắt trực tiếp.

## 14. Kiểm thử sự khác biệt giữa true và false

Có thể dùng Spring Test hoặc `AnnotationConfigApplicationContext` để xác nhận object identity.

### 14.1. Cấu hình dùng true

~~~java
@Configuration(proxyBeanMethods = true)
static class SharedConfiguration {

    @Bean
    MessageFormatter formatter() {
        return new MessageFormatter();
    }

    @Bean
    GreetingService greetingService() {
        return new GreetingService(formatter());
    }
}
~~~

Test:

~~~java
@Test
void fullConfigurationUsesContainerManagedSingleton() {
    try (var context =
            new AnnotationConfigApplicationContext(
                    SharedConfiguration.class)) {

        MessageFormatter formatter =
                context.getBean(MessageFormatter.class);

        GreetingService service =
                context.getBean(GreetingService.class);

        assertSame(formatter, service.formatter());
    }
}
~~~

`assertSame` xác nhận hai tham chiếu trỏ tới cùng object.

### 14.2. Cấu hình dùng false nhưng vẫn gọi trực tiếp

~~~java
@Configuration(proxyBeanMethods = false)
static class LiteConfiguration {

    @Bean
    MessageFormatter formatter() {
        return new MessageFormatter();
    }

    @Bean
    GreetingService greetingService() {
        return new GreetingService(formatter());
    }
}
~~~

Test:

~~~java
@Test
void liteConfigurationDirectCallCreatesDifferentObject() {
    try (var context =
            new AnnotationConfigApplicationContext(
                    LiteConfiguration.class)) {

        MessageFormatter formatter =
                context.getBean(MessageFormatter.class);

        GreetingService service =
                context.getBean(GreetingService.class);

        assertNotSame(formatter, service.formatter());
    }
}
~~~

`assertNotSame` xác nhận instance trong service khác bean formatter trong context. Đây là hệ quả của lời gọi method Java trực tiếp trong lite mode.

### 14.3. Cấu hình dùng false và parameter injection

~~~java
@Configuration(proxyBeanMethods = false)
static class ParameterInjectionConfiguration {

    @Bean
    MessageFormatter formatter() {
        return new MessageFormatter();
    }

    @Bean
    GreetingService greetingService(MessageFormatter formatter) {
        return new GreetingService(formatter);
    }
}
~~~

Test:

~~~java
@Test
void liteConfigurationInjectsManagedDependencyThroughParameter() {
    try (var context =
            new AnnotationConfigApplicationContext(
                    ParameterInjectionConfiguration.class)) {

        MessageFormatter formatter =
                context.getBean(MessageFormatter.class);

        GreetingService service =
                context.getBean(GreetingService.class);

        assertSame(formatter, service.formatter());
    }
}
~~~

Đây là cách thể hiện dependency rõ ràng mà không cần proxy inter-bean method.

Các test trên giả định `MessageFormatter` và `GreetingService` là class đã định nghĩa ở phần trước, có constructor và getter tương ứng. Test dùng JUnit 5 và Spring Context trên test classpath.

## 15. Khi nào chọn true, khi nào chọn false?

Có thể dùng bảng quyết định sau:

| Tình huống | Lựa chọn phù hợp |
| --- | --- |
| Một `@Bean` method gọi trực tiếp một `@Bean` method khác và cần bean theo container | `true` |
| Cấu hình có class/method cần CGLIB intercept | `true`, với điều kiện class/method có thể proxy |
| Tất cả dependency giữa bean được truyền qua tham số `@Bean` | `false` thường phù hợp |
| Class cấu hình chỉ gom factory method độc lập | `false` thường phù hợp |
| Muốn tránh enhancement class cấu hình | `false` |
| Dùng `@Component` chứa `@Bean` method | Lite semantics; dùng parameter injection |
| Không chắc có lời gọi chéo `@Bean` method hay không | Kiểm tra cấu hình trước khi đổi từ true sang false |

Một cách lựa chọn dễ nhớ:

- **Chọn true** khi cần semantics full configuration và có lời gọi trực tiếp giữa các `@Bean` method.
- **Chọn false** khi cấu hình được viết theo kiểu độc lập hoặc truyền dependency qua tham số.
- **Ưu tiên parameter injection** vì nó diễn đạt dependency tường minh và không phụ thuộc chế độ proxy.

Không nên đổi hàng loạt từ true sang false mà không kiểm tra các lời gọi chéo trong class cấu hình. Một thay đổi thuộc tính có thể làm object được tạo thêm ngoài container, gây khác biệt về state, lifecycle và scope.

## 16. Những lỗi và triệu chứng thường gặp

### 16.1. Service dùng instance khác với bean lấy từ context

**Triệu chứng:** Khi so sánh identity, `context.getBean(MessageFormatter.class)` và `service.formatter()` không giống nhau.

**Nguyên nhân thường gặp:** `proxyBeanMethods=false` hoặc lite configuration, trong khi một `@Bean` method gọi trực tiếp method khác và tạo object bằng `new`.

**Cách xử lý:** Chuyển dependency thành tham số của factory method hoặc bật full configuration nếu thật sự cần lời gọi trực tiếp.

### 16.2. Có nhiều instance và state không đồng bộ

**Triệu chứng:** Bean được lấy trực tiếp từ context giữ một state, nhưng service lại sử dụng một object khác với state khác.

**Nguyên nhân:** Object thứ hai được tạo bởi lời gọi Java trực tiếp và không phải bean singleton container-managed.

**Cách xử lý:** Không gọi trực tiếp factory method để lấy dependency trong lite mode. Hãy inject bean.

### 16.3. Configuration class final không khởi động ở full mode

**Triệu chứng:** Spring báo không thể enhance/proxy configuration class.

**Nguyên nhân:** CGLIB không thể subclass class final.

**Cách xử lý:** Bỏ final nếu cần full proxy, hoặc chuyển sang `proxyBeanMethods=false` và loại bỏ inter-bean direct calls.

### 16.4. Thay true thành false làm lỗi chỉ xuất hiện ở một số cấu hình

**Triệu chứng:** Một bean vẫn được tạo, nhưng dependency hoặc object state thay đổi.

**Nguyên nhân:** Có những `@Bean` method gọi lẫn nhau mà trước đó được proxy intercept.

**Cách xử lý:** Tìm các lời gọi method cấu hình bên trong factory method, chuyển sang tham số injection và kiểm tra scope/identity sau khi đổi.

### 16.5. Nghĩ rằng false làm mất @Bean

**Triệu chứng:** Người phát triển bỏ `@Bean` hoặc tự tạo mọi object bằng `new` sau khi tắt proxy.

**Giải thích:** Không cần làm vậy. Spring vẫn đăng ký và quản lý bean được khai báo bằng `@Bean`; chỉ có inter-bean method call không còn được intercept.

### 16.6. Dùng proxyBeanMethods để sửa lỗi dependency injection

Nếu thiếu bean, có nhiều bean cùng kiểu hoặc dependency vòng, thay đổi `proxyBeanMethods` không phải giải pháp chung. Hãy xác định đúng lỗi candidate, package scan, condition, qualifier hoặc dependency graph.

## 17. Bài thực hành

### Bài A: So sánh instance

Tạo hai `@Bean` method:

~~~java
@Bean
MessageFormatter formatter() {
    return new MessageFormatter();
}

@Bean
GreetingService greetingService() {
    return new GreetingService(formatter());
}
~~~

Chạy test với `proxyBeanMethods=true` rồi `false`. Dùng `assertSame` và `assertNotSame` để xác nhận object identity.

Hãy giải thích vì sao bean formatter trong context vẫn tồn tại ở cả hai trường hợp.

### Bài B: Chuyển sang parameter injection

Sửa method:

~~~java
@Bean
GreetingService greetingService(MessageFormatter formatter) {
    return new GreetingService(formatter);
}
~~~

Đặt `proxyBeanMethods=false` và chạy lại test. Xác nhận service nhận đúng bean formatter của context.

### Bài C: Thêm dependency thứ hai

Tạo `GreetingRepository` và cho `GreetingService` nhận cả `MessageFormatter` lẫn `GreetingRepository`.

Viết factory method:

~~~java
@Bean
GreetingService greetingService(
        MessageFormatter formatter,
        GreetingRepository repository) {
    return new GreetingService(formatter, repository);
}
~~~

Hãy xác định dependency nào được container resolve và object nào được tạo trực tiếp trong method.

### Bài D: Quan sát scope prototype

Đăng ký một bean `TaskContext` với scope prototype. So sánh:

- Lấy `TaskContext` nhiều lần từ `ObjectProvider`.
- Gọi trực tiếp `taskContext()` từ một `@Bean` method khi proxy false.
- Gọi `taskContext()` từ một `@Bean` method khi proxy true.

Hãy giải thích trường hợp nào đi qua scope resolution của container.

### Bài E: Phân biệt configuration proxy và AOP proxy

Tạo một service có `@Transactional` trong dự án có `@Configuration(proxyBeanMethods=false)`. Quan sát rằng transaction proxy vẫn có thể hoạt động nếu dependency và cấu hình transaction phù hợp.

Giải thích vì sao thuộc tính `proxyBeanMethods` không điều khiển proxy transaction.

## 18. Câu hỏi tự kiểm tra

**1. Giá trị mặc định của `proxyBeanMethods` là gì?**

`true`. `@Configuration` mặc định sử dụng full configuration semantics và enhancement để intercept lời gọi giữa các `@Bean` method phù hợp.

**2. Khi `proxyBeanMethods=true`, lời gọi `formatter()` từ `greetingService()` có gì đặc biệt?**

Lời gọi đi qua configuration proxy và được chuyển đến container để lấy bean theo scope thay vì luôn thực thi thân method như Java thông thường.

**3. Khi `proxyBeanMethods=false`, Spring còn quản lý bean không?**

Có. Bean definition vẫn được đăng ký, factory method vẫn được container gọi và object trả về vẫn được quản lý. Chỉ inter-bean method call không được proxy intercept.

**4. Tại sao service có thể nhận một formatter khác với bean formatter trong context khi dùng false?**

Vì lời gọi trực tiếp `formatter()` thực thi `new MessageFormatter()` một lần nữa và tạo object ngoài container.

**5. Cách nào hoạt động nhất quán ở cả true và false?**

Truyền dependency qua tham số của `@Bean` method hoặc constructor injection của component.

**6. `proxyBeanMethods=false` có tắt AOP/transaction proxy không?**

Không. Nó chỉ tắt enhancement của configuration class cho mục đích inter-bean method interception.

**7. Khi nào nên dùng false?**

Khi không cần gọi trực tiếp các `@Bean` method lẫn nhau, đặc biệt khi dependency được thể hiện qua tham số method. Đây thường là cấu hình đơn giản và rõ ràng.

## 19. Kết luận

`proxyBeanMethods` quyết định cách Spring xử lý lời gọi trực tiếp giữa các `@Bean` method trong class cấu hình. Với `true`, Spring dùng CGLIB enhancement để lời gọi chéo đi qua container, giúp bean nhận instance phù hợp với scope. Với `false`, lời gọi method là Java thông thường và có thể tạo object mới ngoài container, dù các bean do factory method trực tiếp cung cấp vẫn được Spring quản lý.

Nếu cấu hình cần chia sẻ dependency, cách ổn định là **khai báo dependency trong tham số của `@Bean` method** hoặc dùng constructor injection. Điều đó giúp dependency được container resolve rõ ràng, không phụ thuộc configuration proxy và dễ kiểm thử hơn.

Hãy nhớ: `proxyBeanMethods=false` không tắt Spring IoC, không bỏ đăng ký bean và không tắt AOP. Nó chỉ bỏ interception của các lời gọi `@Bean` method giữa các phương thức cấu hình. Hiểu đúng sự khác biệt này giúp tránh vô tình tạo nhiều instance, tránh state không đồng bộ và chọn chế độ cấu hình phù hợp với cách tổ chức bean của ứng dụng.

