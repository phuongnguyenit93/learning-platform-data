# ApplicationContext cung cấp gì ngoài BeanFactory trong Spring Boot?

## 1. Bức tranh tổng thể: từ quản lý bean đến ngữ cảnh ứng dụng

Khi bắt đầu học Spring, ta thường nghe rằng Spring là một **IoC container**: nó tạo đối tượng, lắp ghép dependency, quản lý scope và vòng đời bean. Nền tảng của khả năng đó là `BeanFactory`. Tuy nhiên khi một ứng dụng Spring Boot khởi động bằng `SpringApplication.run(...)`, thứ chương trình nhận được là một `ConfigurableApplicationContext`, tức một đối tượng **`ApplicationContext` có khả năng quản lý vòng đời**.

Vì sao Spring cần lớp trừu tượng rộng hơn?

Một chương trình có nhiều bean thường còn cần:

- Đọc cấu hình theo môi trường và profile đang hoạt động.
- Nạp tài nguyên từ classpath, file hoặc mẫu đường dẫn.
- Tra cứu thông điệp theo ngôn ngữ.
- Phát sự kiện để các thành phần phối hợp với nhau.
- Biết ngữ cảnh cha/con nếu ứng dụng có phân tầng container.
- Kích hoạt các bước chuẩn bị bean, listener và vòng đời khởi động/đóng.

`ApplicationContext` tập hợp những dịch vụ này trên nền tảng `BeanFactory`. Hiểu đúng khác biệt giúp ta đặt chức năng vào đúng nơi và biết tại sao một ứng dụng tạo bean bằng tay chưa có những hành vi tự động giống Spring Boot.

**Hình dung nhanh:**

```text
SpringApplication.run(...)
           |
           v
  ConfigurableApplicationContext
           |
           +-- BeanFactory: định nghĩa, tạo, tra cứu, quản lý bean
           |
           +-- Environment: properties và profiles
           +-- MessageSource: thông điệp đa ngôn ngữ
           +-- ResourcePatternResolver: tài nguyên và mẫu đường dẫn
           +-- ApplicationEventPublisher: phát sự kiện
           +-- HierarchicalBeanFactory: context cha/con
           +-- Refresh / close / lifecycle: vận hành context
           |
           v
Ứng dụng đã được cấu hình để bắt đầu thực thi
```

Đây là sơ đồ các **khả năng** chứ không có nghĩa `ApplicationContext` sở hữu một đối tượng tách biệt cho mỗi dòng. Một số khả năng được kế thừa qua interface, một số được triển khai bởi các thành phần bên trong context.

## 2. Quan hệ interface chính xác

Trong Spring Framework 6.1 (cùng thế hệ với Spring Boot 3.3), khai báo của `ApplicationContext` về bản chất là:

```java
public interface ApplicationContext extends
        EnvironmentCapable,
        ListableBeanFactory,
        HierarchicalBeanFactory,
        MessageSource,
        ApplicationEventPublisher,
        ResourcePatternResolver {
    // Các phương thức bổ sung về định danh, parent và bean factory.
}
```

Đoạn này **rút gọn danh sách phương thức** để học quan hệ kiểu; không phải file cần sao chép vào dự án để khai báo lại interface thư viện.

Lưu ý: `ListableBeanFactory` và `HierarchicalBeanFactory` đều thuộc nhánh `BeanFactory`. Vì vậy một `ApplicationContext` cũng là một `BeanFactory` và có thể gọi `getBean(...)`, `containsBean(...)`, `getBeanProvider(...)` hoặc liệt kê bean qua `getBeansOfType(...)`.

| Khả năng | `BeanFactory` cơ bản | `ApplicationContext` |
| --- | --- | --- |
| Tra cứu bean theo tên/kiểu | Có, qua `getBean` và API liên quan | Có, được kế thừa |
| Quản lý scope và vòng đời bean | Có ở mức bean factory/implementation | Có, dựa vào bean factory nội bộ |
| Liệt kê bean definition | Phụ thuộc interface/triển khai, ví dụ `ListableBeanFactory` | Có qua `ListableBeanFactory` |
| Đọc `Environment`/active profiles | Không phải hợp đồng của interface `BeanFactory` | Có qua `EnvironmentCapable` |
| Tra cứu thông điệp đa ngôn ngữ | Không phải hợp đồng của `BeanFactory` | Có qua `MessageSource` |
| Phát sự kiện ứng dụng | Không phải hợp đồng của `BeanFactory` | Có qua `ApplicationEventPublisher` |
| Đọc tài nguyên từ location hoặc pattern | Không phải hợp đồng của `BeanFactory` | Có qua `ResourcePatternResolver` |
| Quan hệ cha/con | Không phải hợp đồng cơ bản; có `HierarchicalBeanFactory` | Có qua `HierarchicalBeanFactory` và `getParent()` |
| Phát hiện/đăng ký tự động các bean hạ tầng | Có thể làm thủ công tùy implementation | Các triển khai context chuẩn thực hiện khi `refresh()` |
| Điều khiển refresh, đóng và lifecycle của context | Không nằm trong interface cơ bản | Qua `ConfigurableApplicationContext` |

**Không hiểu nhầm:** `BeanFactory` không đồng nghĩa với một container “không biết lifecycle”. Các triển khai như `DefaultListableBeanFactory` hỗ trợ scope, đăng ký `BeanPostProcessor`, destroy singleton và nhiều tính năng nâng cao. Khác biệt chính là những dịch vụ ứng dụng được tích hợp và quy trình khởi tạo chúng của các triển khai `ApplicationContext` chuẩn.

## 3. BeanFactory vẫn là lõi của IoC

Một `BeanFactory` biết cách trả về bean:

```java
Object bean = beanFactory.getBean("taskService");
```

Nó có thể quản lý bean singleton, prototype, dependency và các callback vòng đời. Bean thường được tạo theo nhu cầu trong cách sử dụng một `BeanFactory` thuần, tùy cơ chế đăng ký và lệnh khởi tạo được gọi.

`ApplicationContext` **không thay thế** các hoạt động đó bằng một hệ thống bean độc lập. Nó tiếp tục sử dụng một bean factory bên trong. Với `ConfigurableApplicationContext`, có thể lấy bean factory phục vụ các nhu cầu hạ tầng đặc biệt:

```java
ConfigurableListableBeanFactory factory = context.getBeanFactory();
```

Đoạn này yêu cầu biến `context` có kiểu `ConfigurableApplicationContext` và đã ở trạng thái phù hợp; đây là API hạ tầng, không phải mã cần có trong mọi service.

Hầu hết code ứng dụng nên ưu tiên **constructor injection**:

```java
@Service
public class InvoiceService {
    private final PaymentGateway paymentGateway;

    public InvoiceService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

Đoạn trên minh họa một class có dependency; `PaymentGateway` cần được định nghĩa và đăng ký thành bean ở dự án thực tế. Injection qua constructor làm rõ dependency và dễ kiểm thử hơn việc rải `applicationContext.getBean(...)` trong nghiệp vụ.

## 4. Environment và profile: hiểu ứng dụng đang chạy với cấu hình nào

`ApplicationContext` kế thừa `EnvironmentCapable`, nên cung cấp `getEnvironment()` để đọc thuộc tính cấu hình và danh sách profile:

```java
Environment env = context.getEnvironment();

String name = env.getProperty("spring.application.name", "unknown");
boolean production = env.acceptsProfiles(Profiles.of("prod"));
String[] active = env.getActiveProfiles();
```

Cần import `org.springframework.core.env.Environment` và `org.springframework.core.env.Profiles`. Ví dụ dùng biến `context` đã được cung cấp ở một phương thức trong ứng dụng.

Điều này hữu ích khi mã phải quan sát cấu hình đã được nạp từ các nguồn như `application.properties`, YAML, biến môi trường, system properties hoặc tham số dòng lệnh. Trong Spring Boot, thứ tự ưu tiên nguồn cấu hình là một chủ đề riêng; không được suy luận rằng mọi giá trị đều đến từ một file cụ thể.

Một `BeanFactory` thuần **không bắt buộc** có `Environment` như một phần hợp đồng. Bạn có thể tự tạo và gắn cơ chế cấu hình cho nó, nhưng `ApplicationContext` đã thống nhất đường truy cập thông dụng.

**Phân biệt đọc với điều khiển:**

- `Environment#getProperty(...)` lấy một giá trị tại thời điểm gọi.
- `@Value` và `@ConfigurationProperties` hỗ trợ đưa cấu hình vào bean.
- `@Profile` và các điều kiện quyết định bean được đăng ký trong quá trình dựng context.
- Đổi biến môi trường sau khi ứng dụng đã khởi động **không có nghĩa** mọi bean tự được tạo lại hoặc mọi `@ConfigurationProperties` tự cập nhật ngay.

Một service chỉ cần một property cụ thể nên nhận giá trị qua cấu hình/injection phù hợp, thay vì luôn cần toàn bộ `ApplicationContext`.

## 5. MessageSource: thông điệp theo ngôn ngữ

`ApplicationContext` kế thừa `MessageSource`. Nó cung cấp cơ chế lấy chuỗi hiển thị dựa trên **mã thông điệp (message code)** và `Locale`. Đây là nền tảng của quốc tế hóa (i18n).

Ví dụ trong dự án Spring Boot:

`src/main/resources/messages.properties`:

```properties
welcome=Hello, {0}!
```

`src/main/resources/messages_vi.properties`:

```properties
welcome=Xin chào, {0}!
```

`src/main/resources/messages_en.properties`:

```properties
welcome=Hello, {0}!
```

Đoạn Java:

```java
String message = context.getMessage(
        "welcome",
        new Object[] {"Lan"},
        Locale.forLanguageTag("vi"));

System.out.println(message);
```

Kết quả:

```text
Xin chào, Lan!
```

Import `java.util.Locale`; giả định `context` là một `ApplicationContext` trong ứng dụng đang chạy. Phương thức `getMessage(...)` không cần truy vấn database; nó sử dụng bộ nguồn thông điệp đã được cấu hình.

Spring Boot thường tự cấu hình `MessageSource` từ các resource bundle thích hợp khi có file mặc định tương ứng, ví dụ `messages.properties`. Trong Spring Framework thuần, có thể khai báo một bean tên `messageSource` (chẳng hạn `ResourceBundleMessageSource`). Nếu không có nguồn thông điệp phù hợp, không nên mong `getMessage` luôn tìm ra mã tùy ý.

Hai chữ ký thường dùng:

```java
// Có nguồn thông điệp và mã tồn tại:
String value = context.getMessage("welcome", args, locale);

// Có văn bản dự phòng nếu không tìm thấy mã:
String safe = context.getMessage(
        "missing.key", args, "Không có thông điệp", locale);
```

`args` và `locale` ở đây là các biến đã có. Bản dùng `defaultMessage` hữu ích khi nội dung dự phòng được phép; bản không có fallback có thể ném `NoSuchMessageException` nếu không tìm thấy mã.

**Lưu ý:** `MessageSource` là cơ chế i18n cho thông điệp, không phải nơi lưu các cấu hình nghiệp vụ như `server.port`. Dùng `Environment` và hệ thống cấu hình khi làm việc với property vận hành.

## 6. ResourceLoader và ResourcePatternResolver: tải tài nguyên thống nhất

`ApplicationContext` kế thừa `ResourcePatternResolver`, và interface này kế thừa `ResourceLoader`. Do đó context có thể giải quyết một **vị trí tài nguyên** thành `Resource`:

```java
Resource resource = context.getResource("classpath:demo/notice.txt");

try (InputStream in = resource.getInputStream()) {
    String value = new String(in.readAllBytes(), StandardCharsets.UTF_8);
    System.out.println(value.trim());
}
```

Các import cần có: `org.springframework.core.io.Resource`, `java.io.InputStream` và `java.nio.charset.StandardCharsets`; phương thức gọi cần xử lý hoặc khai báo `IOException`.

Với Spring Boot executable JAR, `classpath:demo/notice.txt` có thể trỏ tới tài nguyên trong `BOOT-INF/classes/demo/notice.txt`. Vì vậy dùng `getInputStream()` thay vì ép `Resource` thành `File` trên filesystem.

Khi cần tra cứu nhiều resource theo pattern:

```java
Resource[] files = context.getResources("classpath*:demo/*.txt");

System.out.println("resources=" + files.length);
```

`getResources(...)` được cung cấp bởi `ResourcePatternResolver`; phương thức này có thể ném `IOException`. Prefix `classpath*:` được dùng khi muốn tìm qua nhiều mục classpath, còn `classpath:` thường giải quyết một tài nguyên cụ thể. Không giả định số kết quả là cố định nếu dependency cũng cung cấp những tài nguyên trùng pattern.

Bảng lựa chọn:

| Nhu cầu | Vị trí ví dụ | Ghi chú |
| --- | --- | --- |
| Đọc file đóng gói | `classpath:demo/notice.txt` | Ổn định khi classpath đầy đủ |
| Đọc file ngoài JAR | `file:/opt/app/config/data.txt` | Cần tồn tại, có quyền đọc |
| Đọc file tương đối từ working directory | `file:./config/data.txt` | Nhạy cảm với cwd của tiến trình |
| Tìm nhiều file classpath | `classpath*:demo/*.txt` | Có thể trả về nhiều `Resource` |
| Đọc URL | `https://example.org/file.txt` | Có thể cần I/O mạng; cần kiểm soát URL |

Dù `BeanFactory` cũng quản lý bean thuộc loại `ResourceLoader` nếu bạn tự đăng ký, nó **không tự cung cấp phương thức `getResource/getResources` qua interface `BeanFactory`**. Đây là khác biệt về hợp đồng API.

**Lỗi phổ biến:** chuỗi `src/main/resources/demo/notice.txt` là đường dẫn tới thư mục mã nguồn, không phải tên classpath tại runtime. Khi chạy JAR từ thư mục khác, hãy dùng `classpath:demo/notice.txt`.

## 7. ApplicationEventPublisher: các thành phần thông báo sự kiện

`ApplicationContext` là một `ApplicationEventPublisher`, nên có thể gọi:

```java
context.publishEvent(new OrderAccepted("ORDER-101"));
```

Giả định lớp `OrderAccepted` đã được định nghĩa. Từ Spring Framework 4.2 trở lên, payload event có thể là **bất kỳ đối tượng**; không bắt buộc subclass `ApplicationEvent`. Có thể dùng record Java 17+:

```java
public record OrderAccepted(String orderId) { }
```

Ở một bean do Spring quản lý, listener:

```java
@Component
class OrderListener {

    @EventListener
    public void onOrderAccepted(OrderAccepted event) {
        System.out.println("Accepted: " + event.orderId());
    }
}
```

Các import lần lượt là `org.springframework.stereotype.Component` và `org.springframework.context.event.EventListener`. Listener được phát hiện qua cơ chế xử lý annotation của Spring context khi cấu hình tương ứng đã sẵn sàng.

Với event `new OrderAccepted("ORDER-101")`, nếu listener trên đã đăng ký và publisher hoạt động đồng bộ, dòng tự chương trình in ra là:

```text
Accepted: ORDER-101
```

**Điểm quan trọng:** sự kiện ứng dụng Spring là cơ chế trong **cùng ApplicationContext/JVM** theo thiết lập mặc định. Nó không tự động là Kafka, RabbitMQ, HTTP webhook hay một hàng đợi lưu trữ bền vững.

Các hành vi cần hiểu:

- `SimpleApplicationEventMulticaster` thường gọi listener **đồng bộ trên thread phát sự kiện** theo cấu hình mặc định. Nếu listener xử lý lâu, caller có thể phải đợi.
- Có thể cấu hình thực thi bất đồng bộ theo cơ chế được hỗ trợ, nhưng không nên mặc định mọi listener chạy song song.
- Một listener ném exception có thể ảnh hưởng đến publisher trong chế độ đồng bộ, tùy cách multicaster xử lý lỗi.
- Với giao dịch database, thời điểm phát sự kiện và thời điểm transaction commit là hai thời điểm khác nhau. Nếu cần xử lý sau commit, tìm hiểu `@TransactionalEventListener(phase = AFTER_COMMIT)` với điều kiện có transaction phù hợp.
- Sự kiện `ContextRefreshedEvent` hay `ContextClosedEvent` là **sự kiện vòng đời context**; chúng khác event nghiệp vụ như `OrderAccepted`.

Một service chỉ có nhiệm vụ phát sự kiện nên **inject `ApplicationEventPublisher`** thay vì ôm cả context:

```java
@Service
class OrderService {

    private final ApplicationEventPublisher publisher;

    OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    void accept(String orderId) {
        // Giả định xử lý nghiệp vụ hợp lệ đã diễn ra.
        publisher.publishEvent(new OrderAccepted(orderId));
    }
}
```

Đây là đoạn minh họa, cần import `Service` và `ApplicationEventPublisher` và có định nghĩa `OrderAccepted`. Cách inject interface nhỏ giúp mã ít phụ thuộc hạ tầng hơn.

## 8. Context cha/con: phạm vi nhìn thấy bean

`ApplicationContext` kế thừa `HierarchicalBeanFactory` và có thêm `getParent()`. Khi hệ thống sử dụng **context hierarchy**, child có thể nhìn thấy bean từ parent nếu không có bean cùng tên che khuất.

```text
Parent ApplicationContext
  |- bean: sharedService
  |- bean: appClock
  |
  +-- Child A
  |     |- bean: featureAController
  |     |- có thể tra cứu sharedService từ parent
  |
  +-- Child B
        |- bean: featureBController
        |- có thể tra cứu sharedService từ parent
```

Các nguyên tắc:

- **Tra cứu từ child lên parent**: nếu không tìm được bean trong child theo cơ chế tra cứu phù hợp, parent có thể là nơi cung cấp bean.
- **Định nghĩa cùng tên** ở child có thể che tên bean ở parent trong tra cứu từ child.
- Parent **không tự nhìn thấy** các bean định nghĩa riêng của child; hai child không tự chia sẻ bean của nhau.
- `context.getParent()` có thể trả về `null` nếu không có parent.
- `containsLocalBean(name)` hỏi bean ở context hiện tại, còn `containsBean(name)` có thể xét theo chuỗi parent.
- Các event được publish trong child có thể truyền lên parent; không nên mặc định event phát ở parent sẽ tự gửi xuống mọi child.

Ví dụ kiểm tra quan hệ:

```java
ApplicationContext parent = context.getParent();
System.out.println("hasParent=" + (parent != null));
System.out.println("localService=" +
        context.containsLocalBean("sharedService"));
```

Đây là mã chèn vào phương thức đã có biến `context`. Ứng dụng Spring Boot thông thường có thể chỉ dùng **một root context**; không có yêu cầu bắt buộc phải dựng hierarchy. Việc tạo hierarchy cần mục đích rõ ràng, chẳng hạn tách tầng web trong một thiết kế cụ thể hoặc dùng `SpringApplicationBuilder` nâng cao.

## 9. ApplicationContext không chỉ gom API: còn chuẩn hóa khởi tạo

Một khác biệt rất thực tế nằm ở quá trình **`refresh()`**.

`AbstractApplicationContext` (nền tảng chung của nhiều context) chủ động tìm và đăng ký các bean hạ tầng, gọi các bộ xử lý bean, chuẩn bị thông điệp, sự kiện và hoàn thành khởi tạo singleton không lazy.

Các thành phần quan trọng:

- **`BeanFactoryPostProcessor`**: có thể thay đổi hoặc bổ sung metadata/bean definitions **trước khi bean thường được tạo**. `BeanDefinitionRegistryPostProcessor` có vai trò mở rộng việc đăng ký bean definition.
- **`BeanPostProcessor`**: can thiệp vào quá trình khởi tạo từng bean, cho phép các cơ chế như một số dạng proxy và xử lý annotation vận hành.
- **`MessageSource`**: context tìm bean có tên `messageSource` hoặc dùng cơ chế phù hợp để phân giải thông điệp, có thể nhờ parent.
- **`ApplicationEventMulticaster`**: quản lý việc phân phối event tới listener.
- **`LifecycleProcessor`**: điều phối lifecycle của các bean `Lifecycle` / `SmartLifecycle`.
- **`ApplicationListener` và các listener từ annotation**: được phát hiện/đăng ký thông qua hạ tầng liên quan.
- **Pre-instantiation của non-lazy singleton**: các bean singleton không được đánh dấu lazy thường được tạo trước khi refresh hoàn tất.

Với `DefaultListableBeanFactory` dùng độc lập, các khả năng thấp tầng vẫn tồn tại, nhưng người dùng phải **tự thiết lập các post-processor và gọi những giai đoạn cần thiết**. Trong context chuẩn, `refresh()` thực hiện phần điều phối.

Sơ đồ rút gọn, không thay thế toàn bộ source code framework:

```text
ApplicationContext.refresh()
  |
  +-- Chuẩn bị context và BeanFactory
  +-- Xử lý BeanFactoryPostProcessor / bean definitions
  +-- Đăng ký BeanPostProcessor
  +-- Khởi tạo MessageSource
  +-- Khởi tạo ApplicationEventMulticaster
  +-- Đăng ký ApplicationListener
  +-- Hoàn thành khởi tạo các singleton không lazy
  +-- Hoàn tất refresh, kích hoạt LifecycleProcessor
  +-- Phát ContextRefreshedEvent
```

Các triển khai context khác nhau có thể bổ sung các bước riêng; một web context còn chuẩn bị web server qua các hook phù hợp. Đây là **quy trình dựng ứng dụng**, không chỉ một hàm “làm mới lại giá trị property”.

### Lazy loading và một ngộ nhận

Một `BeanFactory` thuần có thể tạo bean khi `getBean(...)` được gọi. Với các context chuẩn, `refresh()` thường khởi tạo những singleton không lazy trước. Tuy nhiên:

- `@Lazy` có thể trì hoãn khởi tạo bean.
- Bean prototype thường không được pre-instantiate hàng loạt.
- Một bean lazy vẫn có thể được tạo sớm nếu một bean không lazy cần nó như dependency thực tế.
- Tùy cấu hình, một số bean hạ tầng cần được tạo sớm để làm nhiệm vụ khởi động.

Không có quy luật “mọi bean trong ApplicationContext đều eager” hoặc “mọi bean trong BeanFactory đều lazy”.

## 10. ConfigurableApplicationContext, refresh và vòng đời

`ApplicationContext` là giao diện **cung cấp khả năng sử dụng** context. Để điều khiển giai đoạn khởi tạo/đóng, Spring dùng `ConfigurableApplicationContext` và các triển khai cụ thể.

Ví dụ:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(ContextFeaturesApplication.class, args);
```

`SpringApplication.run(...)` đã thực hiện việc chuẩn bị và refresh context trước khi trả về thành công. Vì vậy thông thường **không gọi thêm `context.refresh()` sau khi `run` trả về**.

Các phương thức liên quan:

| Phương thức / sự kiện | Ý nghĩa |
| --- | --- |
| `refresh()` | Thực hiện các bước dựng/khởi tạo context theo implementation |
| `start()` / `stop()` | Gửi tín hiệu lifecycle tới các bean hỗ trợ lifecycle; không tương đương đóng context |
| `close()` | Đóng context và hủy các singleton được quản lý khi phù hợp |
| `isActive()` | Quan sát context còn trong trạng thái hoạt động hay không |
| `ContextRefreshedEvent` | Được phát sau khi refresh hoàn tất |
| `ContextClosedEvent` | Được phát khi quá trình đóng context diễn ra |
| `ApplicationReadyEvent` | Sự kiện riêng của Spring Boot ở cuối quá trình khởi động thành công, sau runner phù hợp |

**Có thể refresh nhiều lần không?** Phụ thuộc implementation. Ví dụ `GenericApplicationContext` (nền tảng của `AnnotationConfigApplicationContext`) chỉ hỗ trợ refresh một lần. Một số context có khả năng refresh lặp lại, nhưng **không nên coi Spring Boot application mặc định có cơ chế reload mọi bean theo ý muốn**.

**Config thay đổi có tự cập nhật?** Việc sửa file `application.properties` trên đĩa hoặc thay biến môi trường không có nghĩa `refresh()` phải đọc lại đúng dữ liệu hay mọi bean sẽ được tạo lại an toàn. Cơ chế refresh cấu hình động của các sản phẩm khác (nếu có) cần được thiết kế riêng, có điều kiện và không đồng nhất với `ConfigurableApplicationContext.refresh()`.

**Context close không có nghĩa hệ điều hành dừng ngay ở mọi thiết kế**. Có thể còn thread không do context quản lý; ngược lại, JVM có thể thoát khi không còn thread hoạt động. Khi chạy lệnh CLI/batch nên kiểm soát kết quả, đóng resource và mã thoát rõ ràng.

## 11. Ví dụ Spring Boot 3.3 hoàn chỉnh: cấu hình, message, resource, event

Ví dụ sau sử dụng **Java 17 trở lên**, Spring Boot 3.3 và dependency `spring-boot-starter`. Không cần web server vì mục đích là quan sát năng lực của `ApplicationContext`.

### 11.1. Cấu trúc file

```text
context-features-demo/
  src/main/java/demo/context/ContextFeaturesApplication.java
  src/main/resources/application.properties
  src/main/resources/messages.properties
  src/main/resources/messages_vi.properties
  src/main/resources/demo/notice.txt
```

`src/main/resources/application.properties`:

```properties
spring.application.name=context-features-demo
spring.main.web-application-type=none
```

`src/main/resources/messages.properties`:

```properties
hello=Hello, {0}!
```

`src/main/resources/messages_vi.properties`:

```properties
hello=Xin chào, {0}!
```

`src/main/resources/demo/notice.txt`:

```text
Noi dung tu classpath
```

### 11.2. Java code

Đặt các class dưới đây trong **một file** có tên `ContextFeaturesApplication.java`; một class là `public`, các type còn lại là package-private, hợp lệ trong Java 17+.

```java
package demo.context;

import java.io.InputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class ContextFeaturesApplication {

    public static void main(String[] args) throws IOException {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(ContextFeaturesApplication.class, args)) {

            String appName = context.getEnvironment().getProperty(
                    "spring.application.name", "unknown");
            System.out.println("app=" + appName);

            String viMessage = context.getMessage(
                    "hello", new Object[] {"Lan"},
                    Locale.forLanguageTag("vi"));
            System.out.println("message=" + viMessage);

            Resource resource = context.getResource(
                    "classpath:demo/notice.txt");
            try (InputStream in = resource.getInputStream()) {
                String content = new String(
                        in.readAllBytes(), StandardCharsets.UTF_8);
                System.out.println("resource=" + content.trim());
            }

            Resource[] matches = context.getResources(
                    "classpath*:demo/*.txt");
            System.out.println("resourcesFound=" + matches.length);

            context.publishEvent(new TicketIssued("T-101"));
        }
    }
}

record TicketIssued(String id) { }

@Component
class TicketListener {

    @EventListener
    public void whenIssued(TicketIssued event) {
        System.out.println("event=" + event.id());
    }
}
```

Cần có Spring Boot Gradle plugin hoặc Maven plugin/cấu hình dependency tương ứng. Nếu dùng Gradle, ví dụ khai báo dependency chính:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Lệnh chạy khi dự án có Gradle wrapper và Spring Boot plugin:

```bash
./gradlew bootRun
```

Các dòng do **mã ví dụ** in ra theo thứ tự thông thường, khi chỉ có một `demo/*.txt` khớp:

```text
app=context-features-demo
message=Xin chào, Lan!
resource=Noi dung tu classpath
resourcesFound=1
event=T-101
```

Spring Boot có thể in thêm banner và log. Con số `resourcesFound` trong ứng dụng lớn phụ thuộc toàn bộ classpath, nên không nên cố định nó khi kiểm thử các dependency có thể mang cùng tên tài nguyên.

**Vì sao ví dụ hoạt động?**

1. `SpringApplication.run(...)` tạo và refresh context, đăng ký `TicketListener` qua component scanning.
2. `Environment` trả về `spring.application.name` từ cấu hình.
3. `MessageSource` phân giải `hello` với `Locale("vi")` từ bundle tiếng Việt.
4. `ResourceLoader` đọc `demo/notice.txt` từ classpath; `ResourcePatternResolver` tìm tập tài nguyên theo pattern.
5. `ApplicationEventPublisher` phát `TicketIssued`, listener đã đăng ký nhận được payload.
6. `try-with-resources` đóng `ConfigurableApplicationContext` sau phép thử, tránh để demo non-web tồn tại lâu không cần thiết.

Nếu xóa `messages.properties` và chỉ để `messages_vi.properties`, đừng mặc định Spring Boot vẫn tự cấu hình message source như mong đợi. Giữ file gốc `messages.properties` làm bundle nền, rồi bổ sung file locale.

### 11.3. Biến thể dùng interface hẹp trong service

Ví dụ trên dùng `ApplicationContext` trực tiếp để **chứng minh tập khả năng**. Trong mã nghiệp vụ nên inject đúng interface cần thiết:

```java
@Service
public class GreetingService {

    private final MessageSource messageSource;

    public GreetingService(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    public String greet(String person, Locale locale) {
        return messageSource.getMessage(
                "hello", new Object[] {person}, locale);
    }
}
```

Đoạn này thuộc file `GreetingService.java` riêng trong package phù hợp, cần import `org.springframework.stereotype.Service`, `org.springframework.context.MessageSource` và `java.util.Locale`. Tên bean và cấu hình bundle phải tồn tại. Cách này giúp service có dependency chính xác và dễ mock trong unit test.

Cùng nguyên tắc: inject `ResourceLoader` nếu chỉ nạp file; `ApplicationEventPublisher` nếu chỉ phát sự kiện; `Environment` nếu cần quan sát property; inject bean nghiệp vụ qua constructor nếu chỉ cần gọi nghiệp vụ.

## 12. Vì sao ApplicationContext có ý nghĩa khi khởi chạy Spring Boot?

Spring Boot là một tầng cung cấp cấu hình và tự động hóa quanh Spring Framework. Khi gọi `SpringApplication.run(...)`, Boot chịu trách nhiệm lựa chọn context, chuẩn bị `Environment`, xây dựng nguồn cấu hình, chạy refresh và thực hiện các giai đoạn tiếp theo.

Tùy `WebApplicationType`, context mặc định của Spring Boot 3.3 thường là:

| Kiểu | Context thường gặp |
| --- | --- |
| `NONE` | `AnnotationConfigApplicationContext` |
| `SERVLET` | `AnnotationConfigServletWebServerApplicationContext` |
| `REACTIVE` | `AnnotationConfigReactiveWebServerApplicationContext` |

Những lớp trên đều là những triển khai của hệ thống `ApplicationContext`, nên đều có các khả năng chung ở bài này. Context web mở rộng thêm phần liên quan web server, request routing và cấu hình tương ứng. **Không đánh đồng `ApplicationContext` với một HTTP server:** ứng dụng `NONE` vẫn có `Environment`, `MessageSource`, resources và event.

**Khác biệt giữa việc khởi chạy Spring Framework thuần và Spring Boot:** interface `ApplicationContext` là của Spring Framework. Sự suy luận loại web app, tự cấu hình `MessageSource` từ resource bundle, tự phát các sự kiện đặc trưng của Boot và hỗ trợ starter là phần hành vi được thêm bởi Spring Boot. Đừng gán mọi tính năng mặc định của Boot cho riêng hợp đồng interface.

## 13. So sánh refresh context với Boot events

Có nhiều sự kiện xuất hiện trong quá trình startup. Chúng giúp quan sát thời điểm nào các dịch vụ đã sẵn sàng.

Một chuỗi rút gọn:

```text
Tạo SpringApplication
  -> chuẩn bị Environment và các nguồn property
  -> tạo ApplicationContext phù hợp
  -> nạp bean definitions và refresh ApplicationContext
  -> ContextRefreshedEvent
  -> ApplicationStartedEvent (Spring Boot)
  -> ApplicationRunner / CommandLineRunner
  -> ApplicationReadyEvent (Spring Boot)
```

Chuỗi trên lược bỏ các sự kiện sớm, các callback và bước đặc thù. Không nên suy luận rằng `ContextRefreshedEvent` chứng minh tất cả runner đã chạy thành công. Trong Spring Boot, `ApplicationReadyEvent` có ý nghĩa gần thời điểm hoàn tất startup hơn.

Một số listener có thể đăng ký từ rất sớm qua `SpringApplication.addListeners(...)` hoặc cơ chế bootstrap vì tại giai đoạn trước khi context được tạo, các bean listener thông thường chưa tồn tại. Đây cũng là lý do không nên tin rằng một `@EventListener` trong bean đã hoạt động tại **mọi** thời điểm của startup.

Thực tế hữu ích:

- Dùng `ApplicationRunner` khi muốn chạy logic sau khi context đã được khởi tạo.
- Dùng `ApplicationReadyEvent` khi cần phản ứng sau khi quá trình khởi động Boot đã hoàn tất.
- Dùng `ContextClosedEvent` hoặc callback destruction để thu dọn tài nguyên khi đóng context.
- Không tự gọi `refresh()` lặp đi lặp lại để giả lập một lần restart của Spring Boot.

## 14. Phân biệt lifecycle của bean với lifecycle của context

Hai vòng đời liên quan nhưng khác nhau:

**Vòng đời bean** có thể gồm: tạo instance, inject dependencies, chạy post-processor, callback `@PostConstruct`, sử dụng và callback `@PreDestroy` khi bị quản lý/hủy theo scope tương ứng.

**Vòng đời context** gồm: tạo context, đăng ký nguồn bean, refresh, hoạt động, có thể nhận start/stop, rồi đóng. Khi đóng, context thường phá hủy singleton do nó quản lý.

Điều kiện quan trọng:

- Bean `prototype` thường không được container tự gọi callback hủy khi context đóng; bên sử dụng bean cần quản lý phần kết thúc.
- Không mặc định mọi bean đều được tạo trước khi `ApplicationReadyEvent`, bởi cấu hình lazy loading có thể làm một số bean chưa được tạo.
- `@PostConstruct` của một singleton không đồng nghĩa toàn bộ context đã ready.
- Nếu một bean cần nhận sự kiện lifecycle, có thể dùng `ApplicationListener`/`@EventListener`, nhưng phải hiểu thời điểm đăng ký và thứ tự sự kiện.

Mục đích của `ApplicationContext` là gom những quy tắc này thành một đơn vị vận hành có ranh giới rõ ràng cho ứng dụng.

## 15. Các nhầm lẫn và lỗi chẩn đoán

| Hiện tượng / suy luận sai | Điều cần kiểm tra | Cách hiểu hoặc khắc phục |
| --- | --- | --- |
| “`ApplicationContext` là thứ thay thế `BeanFactory`” | Quan hệ interface | `ApplicationContext` kế thừa các khả năng bean factory và bổ sung dịch vụ ứng dụng |
| “Có `BeanFactory` thì tự nhận event `@EventListener`” | Cơ chế đăng ký hạ tầng xử lý annotation | Container thuần có thể cần tự cấu hình post-processors/listeners |
| “`getBean` tìm được bean tức ứng dụng ready” | Trạng thái refresh, runner, health | Dùng cơ chế readiness phù hợp, không chỉ kiểm tra bean |
| “Mọi singleton đều chỉ khởi tạo khi `getBean`” | Non-lazy singleton lúc refresh | Context chuẩn có thể tạo non-lazy singleton khi refresh |
| “`refresh` nghĩa là đọc lại YAML sau khi file đổi” | Loại context và cơ chế config reload | Không được suy diễn hot reload cấu hình từ `refresh()` |
| “`getResource` luôn trả về `java.io.File`” | Resource có thể nằm trong JAR | Dùng `getInputStream()` để đọc |
| “`getResources` luôn có một kết quả” | Pattern và classpath | Kiểm tra số resource và xử lý trường hợp 0 hoặc nhiều |
| “Không có `messages_vi.properties` mà vẫn có bản dịch” | MessageSource và fallback bundle | Khai báo message bundle/locale đúng |
| “Event mặc định chạy ở thread riêng” | Event multicaster và executor | Mặc định thường đồng bộ; không dựa vào giả định async |
| “Event Spring tự truyền sang microservice khác” | Phạm vi JVM/context | Muốn giao tiếp liên dịch vụ cần hạ tầng messaging/HTTP riêng |
| “Parent có thể lấy mọi bean của child” | Hướng tra cứu hierarchy | Child nhìn lên parent; parent không tự nhìn xuống child |
| “Đóng context không ảnh hưởng bean” | Lifecycle, destruction callback | Bean singleton do context quản lý được dọn dẹp khi đóng đúng cách |

Một quy trình chẩn đoán thực tế khi Spring Boot có vấn đề lúc khởi chạy:

1. Xác nhận context có tạo/refresh thành công không; xem exception gốc trong log startup.
2. Nếu thiếu bean, kiểm tra component scanning, `@Configuration`, điều kiện `@Profile` và auto-configuration.
3. Nếu sai property, in hoặc log an toàn giá trị cần thiết từ `Environment` và kiểm tra nguồn ưu tiên.
4. Nếu thiếu message, kiểm tra `messages.properties`, bundle locale, mã message và `MessageSource`.
5. Nếu thiếu tài nguyên, kiểm tra classpath/JAR, prefix `classpath:` hoặc `file:` và working directory.
6. Nếu listener không được gọi, kiểm tra nó có là bean, annotation đã được xử lý, event type có khớp và thời điểm publish hợp lý không.
7. Nếu startup treo, kiểm tra những bean non-lazy, post-processor, listener đồng bộ và thao tác I/O trong giai đoạn refresh.
8. Nếu bean không được hủy khi thoát, kiểm tra scope, ai sở hữu bean và việc đóng context đúng cách.

## 16. Bài tập thực hành

### Bài A: xác nhận các khả năng được kế thừa

Dựa trên code trong mục 11, tìm trong IDE các method:

- `getBeanDefinitionCount()` và `getBean(...)` từ `ListableBeanFactory` / `BeanFactory`.
- `getEnvironment()` từ `EnvironmentCapable`.
- `getMessage(...)` từ `MessageSource`.
- `getResource(...)` và `getResources(...)` từ `ResourceLoader` / `ResourcePatternResolver`.
- `publishEvent(...)` từ `ApplicationEventPublisher`.
- `getParent()` từ `ApplicationContext`.

Với mỗi method, ghi rõ bạn dùng **hợp đồng interface** nào và phụ thuộc nào cần có trong lúc runtime. Điều này giúp hiểu tại sao một `ApplicationContext` có thể làm nhiều việc, nhưng code nghiệp vụ vẫn nên inject interface nhỏ hơn.

### Bài B: chứng minh event mặc định có thể đồng bộ

Tạo listener in tên thread bằng `Thread.currentThread().getName()` và publisher in tên thread ngay trước/sau `publishEvent(...)`. Trong cấu hình mặc định, quan sát sự kiện được xử lý theo luồng gọi. Thử thêm một listener xử lý chậm có kiểm soát, rồi giải thích vì sao publisher có thể phải đợi. Không thử sleep lâu trong ứng dụng production.

### Bài C: kiểm tra tài nguyên sau khi đóng JAR

Đóng gói bằng Gradle `bootJar`, kiểm tra file `demo/notice.txt` có dưới `BOOT-INF/classes` rồi chạy bằng `java -jar` từ một thư mục khác. So sánh:

```java
context.getResource("classpath:demo/notice.txt");
context.getResource("file:./demo/notice.txt");
```

Đoạn trên là code minh họa trong một phương thức có `context`. Hai location có vòng đời và gốc tra cứu khác nhau, nên không thể luôn cho cùng kết quả.

### Bài D: phân biệt context và bean readiness

Đăng ký listener cho `ContextRefreshedEvent` và `ApplicationReadyEvent`; đồng thời tạo một `ApplicationRunner` có dòng log riêng. Chạy và quan sát thứ tự. Nêu vì sao một listener ở `ContextRefreshedEvent` không nên báo toàn hệ thống đã hoàn thành mọi công việc startup.

## 17. Những nguyên tắc cần ghi nhớ

1. **`BeanFactory` là lõi IoC; `ApplicationContext` là ngữ cảnh ứng dụng xây trên lõi đó.**
2. Các khả năng thêm rõ nhất là **`Environment`, `MessageSource`, tải resource/pattern, phát sự kiện và context hierarchy**.
3. Với các triển khai context chuẩn, **`refresh()` điều phối hạ tầng bean, listener, message source, singleton và lifecycle**, giúp ứng dụng có trạng thái hoạt động nhất quán.
4. `ApplicationContext` không tự bảo đảm hot reload mọi cấu hình, event bất đồng bộ hay HTTP server; những tính năng đó phụ thuộc implementation và cấu hình.
5. Trong ứng dụng Spring Boot, để framework dựng và refresh context qua `SpringApplication.run(...)`; trong service, ưu tiên **constructor injection** và interface hẹp theo nhu cầu thực tế.

### Tài liệu chính thức

- [Spring Framework 6.1 — ApplicationContext API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/context/ApplicationContext.html): danh sách interface kế thừa, phương thức và chức năng.
- [Spring Framework — Additional Capabilities of ApplicationContext](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): i18n, resources, events và hierarchy.
- [Spring Framework 6.1 — AbstractApplicationContext API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html): các giai đoạn `refresh()` và hạ tầng nội bộ.
- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): mối liên hệ giữa SpringApplication và context lúc startup.
