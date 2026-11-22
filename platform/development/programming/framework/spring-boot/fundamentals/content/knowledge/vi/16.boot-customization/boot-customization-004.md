# Phân biệt bean cùng type với bean cùng tên

Trong Spring Boot, một ứng dụng có thể có nhiều bean cùng thực hiện một interface, chẳng hạn nhiều implementation của `NotificationSender`, `PaymentGateway` hoặc `DataSource`. Điều đó hoàn toàn hợp lệ nếu mỗi bean có định danh riêng và ứng dụng biết cách chọn bean phù hợp khi cần.

Một tình huống khác cũng dễ gây nhầm lẫn là hai cấu hình cùng đăng ký bean với một tên. Khi đó, vấn đề không còn là có nhiều bean cùng type, mà là **xung đột định danh trong cùng một Spring container**. Spring quản lý bean definitions trong một registry; một tên bean chỉ có thể đại diện cho một definition tại một thời điểm.

Để tổ chức dependency đúng, cần phân biệt:

- **Type** cho biết bean có thể được sử dụng như kiểu Java nào.
- **Bean name** là định danh của bean trong container.
- **Alias** là tên bổ sung cùng trỏ tới một bean.
- **Qualifier** là metadata giúp lọc các ứng viên khi inject.
- **Primary** đánh dấu ứng viên được ưu tiên trong một số tình huống chọn một bean.

Bài học này giải thích các khái niệm đó, cách Spring chọn bean theo type hoặc name, các lỗi thường gặp khi có nhiều ứng viên hoặc trùng tên, và cách xử lý trong Java configuration của Spring Boot.

## 1. Bean type và bean name là hai thuộc tính khác nhau

Một bean trong Spring được container quản lý thông qua bean definition và instance. Khi sử dụng bean, ta thường có thể tìm nó bằng **type** hoặc bằng **name**.

Ví dụ:

```java
@Component("emailSender")
public class EmailNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        // Gửi email.
    }
}
```

Trong ví dụ:

- Type cụ thể là `EmailNotificationSender`.
- Bean cũng có thể được tìm qua interface `NotificationSender` vì class triển khai interface đó.
- Bean name được khai báo tường minh là `emailSender`.

Ta có thể yêu cầu bean theo hai cách:

```java
NotificationSender sender =
        applicationContext.getBean("emailSender", NotificationSender.class);

EmailNotificationSender implementation =
        applicationContext.getBean(EmailNotificationSender.class);
```

Cách đầu tiên tìm theo tên và kiểm tra kiểu tương thích. Cách thứ hai tìm bean theo type. Hai cách truy cập không có cùng quy tắc phân giải.

### 1.1. Type trả lời “bean này là loại gì?”

Type là kiểu Java mà bean có thể đáp ứng. Khi một class triển khai interface, instance của nó có thể được tìm qua interface hoặc các kiểu cha tương thích.

Ví dụ:

```java
public interface NotificationSender {
    void send(String recipient, String message);
}

@Component
class EmailNotificationSender implements NotificationSender {
    // ...
}

@Component
class SmsNotificationSender implements NotificationSender {
    // ...
}
```

Cả hai bean đều tương thích với type `NotificationSender`. Một truy vấn theo type interface có thể tìm thấy cả hai.

### 1.2. Name trả lời “bean này được định danh bằng gì?”

Bean name là tên dùng trong container để đăng ký và tra cứu một bean. Nếu dùng component scanning và không đặt tên tường minh, Spring thường tạo tên mặc định từ tên class với chữ cái đầu viết thường:

| Class | Bean name mặc định thường gặp |
| --- | --- |
| `EmailNotificationSender` | `emailNotificationSender` |
| `SmsNotificationSender` | `smsNotificationSender` |
| `URLFormatter` | `URLFormatter` theo quy tắc decapitalize của JavaBeans khi ký tự đầu và thứ hai đều viết hoa |

Tên mặc định là quy ước thuận tiện. Khi tên bean là một phần của hợp đồng cấu hình, nên đặt tên tường minh để người đọc không phải suy đoán.

### 1.3. Nhiều bean cùng type là bình thường

Một interface có thể có nhiều implementation. Mỗi implementation có thể được đăng ký thành một bean riêng với tên riêng:

```text
Bean name                  Bean type
------------------------------------------------
emailSender                NotificationSender
smsSender                  NotificationSender
consoleSender              NotificationSender
```

Điều này không phải lỗi. Nó chỉ trở thành vấn đề khi một điểm inject yêu cầu **một** `NotificationSender` nhưng Spring tìm thấy nhiều ứng viên mà không có quy tắc lựa chọn đủ rõ.

### 1.4. Một bean có thể có nhiều type

Một instance của `EmailNotificationSender` có thể được tìm theo type cụ thể, interface `NotificationSender`, hoặc một interface cha khác mà class triển khai. Do đó, “một bean” không đồng nghĩa “một type”.

Nói cách khác:

- Một type có thể khớp với nhiều bean.
- Một bean có thể khớp với nhiều type.
- Bean name xác định bean trong container; type xác định những góc nhìn kiểu dữ liệu mà bean đáp ứng.

## 2. Một class có thể tạo nhiều bean cùng type nhưng khác name

Không nhất thiết phải có nhiều class implementation mới có nhiều bean cùng type. Một class có thể được dùng để tạo nhiều bean với cấu hình khác nhau.

Ví dụ một HTTP client có cấu hình timeout:

```java
public class PartnerClient {

    private final Duration timeout;

    public PartnerClient(Duration timeout) {
        this.timeout = timeout;
    }

    public Duration timeout() {
        return timeout;
    }
}
```

Java configuration:

```java
@Configuration(proxyBeanMethods = false)
public class PartnerClientConfiguration {

    @Bean("fastPartnerClient")
    PartnerClient fastPartnerClient() {
        return new PartnerClient(Duration.ofSeconds(2));
    }

    @Bean("slowPartnerClient")
    PartnerClient slowPartnerClient() {
        return new PartnerClient(Duration.ofSeconds(15));
    }
}
```

Context có hai bean:

| Bean name | Type | Giá trị cấu hình |
| --- | --- | --- |
| `fastPartnerClient` | `PartnerClient` | 2 giây |
| `slowPartnerClient` | `PartnerClient` | 15 giây |

Hai bean cùng type nhưng khác name. Khi muốn chọn client cụ thể, có thể dùng qualifier hoặc tra cứu theo name.

Điều này hữu ích khi cùng một implementation phục vụ hai vai trò khác nhau, ví dụ:

- Client gọi API nội bộ và client gọi API đối tác.
- Data source đọc và data source ghi.
- Serializer cho định dạng JSON và serializer cho định dạng CSV.
- Cache ngắn hạn và cache có thời gian lưu dài hơn.

Tuy nhiên, nếu hai bean chỉ khác một giá trị cấu hình nhưng không có lý do sử dụng riêng, hãy cân nhắc liệu có cần hai bean hay chỉ cần một bean nhận cấu hình phù hợp.

## 3. Tra cứu theo type

Spring có thể tìm bean theo kiểu:

```java
NotificationSender sender =
        applicationContext.getBean(NotificationSender.class);
```

Hoặc lấy tất cả bean phù hợp:

```java
Map<String, NotificationSender> senders =
        applicationContext.getBeansOfType(NotificationSender.class);
```

Hai thao tác có ý nghĩa khác nhau:

- `getBean(NotificationSender.class)` yêu cầu một ứng viên duy nhất có thể phân giải theo quy tắc của container.
- `getBeansOfType(NotificationSender.class)` trả về các bean phù hợp dưới dạng map theo bean name.

### 3.1. Không có bean phù hợp

Nếu không có bean nào tương thích với type yêu cầu, Spring có thể ném `NoSuchBeanDefinitionException`.

Ví dụ:

```java
PaymentGateway gateway =
        applicationContext.getBean(PaymentGateway.class);
```

Nếu context không có bean thực hiện `PaymentGateway`, yêu cầu này thất bại.

Nguyên nhân có thể là:

- Implementation chưa được đăng ký.
- Class nằm ngoài phạm vi component scan.
- Configuration tạo bean chưa được import.
- Bean bị loại bởi `@Profile` hoặc `@Conditional...`.
- Module cung cấp implementation không có trên runtime classpath.

### 3.2. Có nhiều bean cùng type

Nếu có hai bean cùng phù hợp với `NotificationSender` và không có tiêu chí lựa chọn, yêu cầu một bean đơn có thể thất bại với `NoUniqueBeanDefinitionException`.

Ví dụ:

```java
@Service
class RegistrationService {

    private final NotificationSender sender;

    RegistrationService(NotificationSender sender) {
        this.sender = sender;
    }
}
```

Nếu context có cả `emailSender` và `smsSender`, constructor trên không nói rõ service muốn dùng implementation nào.

Đây là lỗi **mơ hồ theo type**, không phải lỗi trùng bean name.

### 3.3. Lấy tất cả bean theo type

Nếu ứng dụng cần tất cả implementation, đừng yêu cầu một bean đơn. Hãy inject collection:

```java
@Service
class NotificationBroadcastService {

    private final List<NotificationSender> senders;

    NotificationBroadcastService(List<NotificationSender> senders) {
        this.senders = senders;
    }

    void broadcast(String recipient, String message) {
        senders.forEach(sender -> sender.send(recipient, message));
    }
}
```

Spring cung cấp các bean tương thích với `NotificationSender` vào collection. Cách này diễn đạt đúng ý định “dùng tất cả sender”.

Với `Map<String, NotificationSender>`, key thường là bean name và value là instance. Đây là lựa chọn hữu ích khi cần duyệt hoặc tra cứu nhiều implementation theo định danh.

## 4. Tra cứu theo bean name

Khi biết bean name, có thể yêu cầu container lấy bean theo tên:

```java
NotificationSender email =
        applicationContext.getBean("emailSender", NotificationSender.class);
```

Phương thức có cả tên và type giúp kiểm tra rằng bean mang tên đó có kiểu tương thích. Nếu chỉ dùng:

```java
Object bean = applicationContext.getBean("emailSender");
```

kết quả có kiểu khai báo `Object`, vì vậy code thường cần cast hoặc kiểm tra type.

### 4.1. Name lookup không có nghĩa type không quan trọng

Spring vẫn tạo và quản lý bean theo type, dependency và metadata. Tra cứu bằng name chỉ xác định **định danh nào** cần lấy. Khi dùng overload có type, container kiểm tra bean được tìm thấy có tương thích với type yêu cầu hay không.

Nếu tên không tồn tại, có thể gặp `NoSuchBeanDefinitionException`. Nếu tên tồn tại nhưng type không tương thích với type được yêu cầu, thao tác lấy bean có thể thất bại do type mismatch.

### 4.2. Tên bean có phạm vi trong container

Bean name được quản lý trong một registry/application context. Hai application context độc lập có thể cùng có bean tên `dataSource` mà không xung đột trong registry của nhau. Trong cấu trúc context cha-con, context con có thể có bean cùng tên và việc tra cứu trong context con có thể che khuất bean cùng tên từ context cha.

Trong một context duy nhất, nên coi bean name là định danh duy nhất. Đừng dựa vào việc có nhiều definition cùng tên để đại diện cho nhiều implementation.

## 5. Bean cùng tên là một tình huống khác

Trong một bean registry, một tên bean chỉ đại diện cho một bean definition tại một thời điểm. Nếu hai cấu hình cùng đăng ký một definition với tên `paymentGateway`, chúng đang tranh chấp cùng một định danh.

Ví dụ:

```java
@Configuration
class DefaultPaymentConfiguration {

    @Bean("paymentGateway")
    PaymentGateway paymentGateway() {
        return new DemoPaymentGateway();
    }
}
```

Một cấu hình khác:

```java
@Configuration
class PartnerPaymentConfiguration {

    @Bean("paymentGateway")
    PaymentGateway paymentGateway() {
        return new PartnerPaymentGateway();
    }
}
```

Hai phương thức cùng khai báo bean name `paymentGateway`. Trong cùng context, đây là xung đột tên bean.

### 5.1. Hành vi mặc định trong Spring Boot hiện đại

Trong các phiên bản Spring Boot hiện đại, bean definition overriding thường bị tắt theo mặc định. Nếu hai configuration đăng ký cùng một bean name, quá trình khởi tạo context có thể thất bại với `BeanDefinitionOverrideException`.

Điều này giúp phát hiện cấu hình trùng tên sớm thay vì âm thầm thay thế một định nghĩa bằng định nghĩa khác.

Spring Framework có cơ chế cho phép bean definition overriding tùy cấu hình của registry. Spring Boot cung cấp property:

```properties
spring.main.allow-bean-definition-overriding=true
```

để bật lại hành vi ghi đè bean definition trong những trường hợp cần thiết.

Không nên bật property này chỉ để làm lỗi biến mất. Nếu hai cấu hình vô tình dùng cùng tên, việc ghi đè có thể che giấu lỗi wiring và làm implementation được chọn phụ thuộc vào thứ tự đăng ký.

### 5.2. Khi overriding được bật

Nếu registry cho phép overriding, definition đăng ký sau có thể thay thế definition cùng tên đã tồn tại. Kết quả là container chỉ có một định nghĩa dưới tên đó; hai bean không tồn tại song song dưới cùng một tên.

Điều này khác với việc có hai bean cùng type nhưng khác name:

```text
Hai bean cùng type, khác name:
  emailSender -> EmailNotificationSender
  smsSender   -> SmsNotificationSender
  => Cả hai có thể tồn tại.

Hai definition cùng name:
  paymentGateway -> DemoPaymentGateway
  paymentGateway -> PartnerPaymentGateway
  => Xung đột hoặc một definition ghi đè definition kia,
     tùy cấu hình registry.
```

### 5.3. Trùng tên không được giải quyết bằng @Primary

`@Primary` chỉ ảnh hưởng lựa chọn giữa các bean ứng viên cùng type ở những điểm cần một bean. Nó không cho phép hai bean definition độc lập cùng chiếm một tên trong registry.

Nếu hai phương thức `@Bean` cùng tên, thêm `@Primary` vào một phương thức không giải quyết xung đột bean name. Cần đổi tên một bean, loại một cấu hình, dùng điều kiện phù hợp hoặc chủ động thiết kế cơ chế thay thế.

## 6. Alias: nhiều tên cùng trỏ tới một bean

Spring hỗ trợ alias để một bean có thể được tra cứu bằng nhiều tên. Alias không tạo thêm bean instance và không tạo thêm bean definition độc lập.

Ví dụ với `@Bean`:

```java
@Configuration(proxyBeanMethods = false)
class DataSourceConfiguration {

    @Bean(name = {"primaryDataSource", "dataSource"})
    DataSource primaryDataSource() {
        return createDataSource();
    }
}
```

Trong ví dụ, `primaryDataSource` là tên bean và `dataSource` là alias. Cả hai tên trỏ tới cùng một bean.

Có thể hình dung:

```text
primaryDataSource ─┐
                   ├──> cùng một DataSource instance
dataSource ────────┘
```

Alias hữu ích khi cần giữ tên cũ để tương thích với cấu hình hoặc code hiện có trong lúc đổi tên bean. Tuy nhiên, quá nhiều alias có thể khiến việc đọc cấu hình khó khăn; nên giữ một tên chính và chỉ thêm alias khi có nhu cầu thực tế.

### 6.1. Khai báo alias bằng @Bean

Thuộc tính `name` của `@Bean` có thể nhận nhiều tên:

```java
@Bean(name = {"mainClock", "systemClock"})
Clock clock() {
    return Clock.systemUTC();
}
```

Hai tên có thể dùng để tra cứu cùng bean:

```java
Clock first = context.getBean("mainClock", Clock.class);
Clock second = context.getBean("systemClock", Clock.class);
```

Với bean singleton, hai lần tra cứu qua tên chính và alias sẽ trả cùng instance. Với bean scope khác, quy tắc tạo instance của scope vẫn được áp dụng; alias không thay đổi scope.

### 6.2. Alias khác hai bean cùng type

Nếu có:

```java
@Bean("mainClock")
Clock mainClock() {
    return Clock.systemUTC();
}

@Bean("testClock")
Clock testClock() {
    return Clock.fixed(
            Instant.parse("2025-01-01T00:00:00Z"),
            ZoneOffset.UTC
    );
}
```

thì có hai bean definition khác nhau cùng type `Clock` và có hai instance singleton riêng. Nếu `testClock` chỉ là alias của `mainClock`, chúng mới cùng trỏ tới một bean definition và một instance.

## 7. Quy tắc lựa chọn khi inject theo type

Với constructor injection:

```java
@Service
class ReportService {

    private final ReportExporter exporter;

    ReportService(ReportExporter exporter) {
        this.exporter = exporter;
    }
}
```

Spring giải quyết dependency dựa trên type và các metadata lựa chọn. Ở mức khái quát:

1. Tìm các bean có type tương thích với `ReportExporter`.
2. Áp dụng các qualifier được yêu cầu tại điểm inject.
3. Nếu còn nhiều ứng viên, xét các tiêu chí ưu tiên như `@Primary` và các quy tắc lựa chọn liên quan.
4. Trong một số tình huống, tên tham số/field có thể giúp phân giải ứng viên khi tên khớp bean name và không có tiêu chí mạnh hơn.
5. Nếu vẫn không xác định được một bean duy nhất cho dependency đơn, Spring báo lỗi mơ hồ.

Đây là mô tả để hiểu cách chọn bean; thứ tự chi tiết còn phụ thuộc loại injection point và phiên bản Spring. Khi cần một lựa chọn ổn định, hãy khai báo qualifier rõ ràng thay vì dựa vào tên tham số.

### 7.1. @Primary: chọn bean mặc định

`@Primary` đánh dấu một bean là ứng viên ưu tiên khi có nhiều bean cùng type và điểm inject cần một bean đơn.

```java
@Component
@Primary
class CsvReportExporter implements ReportExporter {
    // ...
}

@Component
class PdfReportExporter implements ReportExporter {
    // ...
}
```

Một service nhận `ReportExporter` không cần qualifier có thể nhận bean primary nếu các tiêu chí khác không thay đổi kết quả.

`@Primary` không xóa các bean còn lại khỏi context. Chúng vẫn có thể được tra cứu theo tên, inject qua qualifier hoặc nhận trong collection.

### 7.2. @Qualifier: lọc ứng viên cụ thể

`@Qualifier` cho phép nói rõ điểm inject cần bean mang qualifier tương ứng:

```java
@Service
class PdfReportService {

    private final ReportExporter exporter;

    PdfReportService(
            @Qualifier("pdfReportExporter")
            ReportExporter exporter
    ) {
        this.exporter = exporter;
    }
}
```

Qualifier có thể dùng tên bean như tiêu chí fallback, nhưng bản chất của nó là metadata lọc ứng viên. Có thể tạo custom qualifier annotation để biểu diễn đặc tính như `@Regional("asia")` hoặc `@StorageType("durable")`.

### 7.3. @Primary và @Qualifier có vai trò khác nhau

| Cơ chế | Mục đích |
| --- | --- |
| `@Primary` | Đánh dấu bean mặc định được ưu tiên |
| `@Qualifier` | Chỉ định đặc tính/nhãn cần có tại điểm inject |
| Bean name | Định danh bean trong container |
| Alias | Tên bổ sung cho cùng bean |

Nếu một service luôn cần PDF, qualifier `pdf` diễn đạt ý định rõ hơn việc dựa vào bean primary toàn ứng dụng. Nếu phần lớn service cần CSV và chỉ một service đặc biệt cần PDF, có thể dùng primary cho CSV và qualifier cho PDF.

## 8. Inject theo name khác inject theo type

Trong Spring có nhiều cách khai báo dependency. Chúng có quy tắc phân giải khác nhau.

### 8.1. @Autowired thường giải quyết theo type

Ví dụ:

```java
@Autowired
private NotificationSender sender;
```

Spring tìm bean phù hợp với type `NotificationSender`. Nếu chỉ có một ứng viên, nó có thể inject trực tiếp. Nếu có nhiều, cần qualifier, primary hoặc một tiêu chí phân giải khác.

Với constructor injection:

```java
RegistrationService(NotificationSender sender) {
    this.sender = sender;
}
```

Spring cũng giải quyết dependency theo type. Nếu có nhiều bean cùng type, tên tham số có thể tham gia phân giải trong các điều kiện phù hợp, nhưng không nên dựa vào hành vi này thay cho qualifier tường minh.

### 8.2. @Resource thiên về name-based injection

`@Resource` thuộc Jakarta Annotations và thường được dùng để yêu cầu dependency theo tên:

```java
@Resource(name = "emailSender")
private NotificationSender sender;
```

Ở ví dụ này, tên `emailSender` được chỉ định tường minh. Cơ chế resource injection tìm resource theo tên đó; nếu không thể phân giải theo quy tắc tương ứng, quá trình injection thất bại.

Nếu dùng `@Resource` không ghi name trên field hoặc property, tên mặc định thường được suy ra từ tên field/property. Cơ chế có thể dùng type làm bước fallback theo quy tắc của Spring/Jakarta. Vì vậy, khi cần lựa chọn chính xác theo name, nên ghi rõ thuộc tính `name`.

### 8.3. So sánh

| Cách khai báo | Ý nghĩa lựa chọn thường gặp |
| --- | --- |
| `@Autowired NotificationSender sender` | Type-based; có thể dùng qualifier/primary và các quy tắc phân giải bổ sung |
| `@Autowired @Qualifier("sms") NotificationSender sender` | Type-based rồi lọc theo qualifier |
| `@Resource(name = "emailSender")` | Yêu cầu resource theo tên |
| `context.getBean("emailSender")` | Tra cứu tường minh theo bean name |
| `context.getBean(NotificationSender.class)` | Tra cứu theo type; cần phân giải một ứng viên |
| `context.getBeansOfType(NotificationSender.class)` | Lấy tất cả bean phù hợp theo type |

Với ứng dụng Spring mới, constructor injection thường dễ kiểm thử và thể hiện dependency rõ ràng. Chọn type hay name dựa trên ý nghĩa của dependency, không chỉ dựa trên annotation nào có ít ký tự hơn.

## 9. Tên mặc định được tạo như thế nào?

### 9.1. Component scanning

Khi dùng:

```java
@Component
public class EmailNotificationSender {
}
```

Spring thường đặt bean name mặc định là `emailNotificationSender`.

Có thể đặt tên tường minh:

```java
@Component("emailSender")
public class EmailNotificationSender {
}
```

Tên tường minh hữu ích khi bean name được dùng trong cấu hình hoặc tại điểm inject. Với class được dùng trong nhiều context hoặc nhiều module, nên chọn tên ổn định và có ý nghĩa.

### 9.2. @Bean method

Với:

```java
@Configuration
class ClockConfiguration {

    @Bean
    Clock systemClock() {
        return Clock.systemUTC();
    }
}
```

Tên phương thức `systemClock` là bean name mặc định. Có thể đặt tên khác:

```java
@Bean("utcClock")
Clock systemClock() {
    return Clock.systemUTC();
}
```

Với nhiều tên:

```java
@Bean(name = {"utcClock", "systemClock"})
Clock clock() {
    return Clock.systemUTC();
}
```

Tên đầu tiên là bean name chính; các tên còn lại là alias.

### 9.3. Tên bean phân biệt chữ hoa/chữ thường

Hãy sử dụng bean name nhất quán và coi tên là chuỗi định danh chính xác. `emailSender` và `EmailSender` không nên được xem là hai cách viết thay thế nhau. Tránh thay đổi chữ hoa/chữ thường tùy tiện khi tên bean đã được tham chiếu trong qualifier, resource injection hoặc code tra cứu.

## 10. Bean name collision giữa các cấu hình

Một ứng dụng có thể import nhiều configuration class:

```java
@Configuration
class LocalCacheConfiguration {

    @Bean("cacheManager")
    CacheManager cacheManager() {
        return new LocalCacheManager();
    }
}

@Configuration
class RedisCacheConfiguration {

    @Bean("cacheManager")
    CacheManager cacheManager() {
        return new RedisCacheManager();
    }
}
```

Nếu cả hai cấu hình được xử lý trong cùng context, chúng cùng đăng ký tên `cacheManager`. Đây là xung đột bean name.

### 10.1. Cách xử lý 1: dùng tên khác nếu thực sự cần cả hai

```java
@Bean("localCacheManager")
CacheManager localCacheManager() {
    return new LocalCacheManager();
}

@Bean("redisCacheManager")
CacheManager redisCacheManager() {
    return new RedisCacheManager();
}
```

Sau đó chọn bean theo qualifier:

```java
CacheService(
        @Qualifier("redisCacheManager") CacheManager cacheManager
) {
    this.cacheManager = cacheManager;
}
```

### 10.2. Cách xử lý 2: chỉ kích hoạt một cấu hình

Nếu local cache chỉ dành cho môi trường dev và Redis dùng ở production, có thể dùng profile:

```java
@Configuration
@Profile("dev")
class LocalCacheConfiguration {
    // ...
}

@Configuration
@Profile("prod")
class RedisCacheConfiguration {
    // ...
}
```

Hai cấu hình không nên cùng được kích hoạt nếu mục tiêu là chỉ có một bean mặc định tên `cacheManager`. Profile mô tả môi trường kích hoạt; nó không phải cách đặt tên bean.

### 10.3. Cách xử lý 3: cấu hình mặc định và bean tùy chỉnh

Với auto-configuration, có thể cung cấp bean mặc định khi ứng dụng chưa có bean tương ứng:

```java
@AutoConfiguration
class CacheAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CacheManager.class)
    CacheManager cacheManager() {
        return new LocalCacheManager();
    }
}
```

Khi ứng dụng tự khai báo một bean phù hợp, auto-configuration có thể back off thay vì đăng ký một definition trùng tên. Đây là mẫu phổ biến để thư viện cung cấp mặc định nhưng cho phép ứng dụng tùy biến.

## 11. Không nhầm bean name collision với nhiều bean cùng type

Hai lỗi này có triệu chứng và cách sửa khác nhau:

| Tình huống | Ví dụ | Lỗi có thể gặp | Cách xử lý |
| --- | --- | --- | --- |
| Nhiều bean cùng type, khác name | `emailSender`, `smsSender` cùng implement `NotificationSender` | `NoUniqueBeanDefinitionException` khi cần một bean đơn | `@Qualifier`, `@Primary`, inject collection |
| Hai definition cùng name trong một registry | Hai cấu hình cùng khai báo `paymentGateway` | `BeanDefinitionOverrideException` nếu overriding bị tắt | Đổi tên, bỏ cấu hình thừa, dùng condition/profile |
| Không có bean theo type | Chưa đăng ký `PaymentGateway` | `NoSuchBeanDefinitionException` hoặc `UnsatisfiedDependencyException` | Kiểm tra scan/import/dependency/condition |
| Alias trùng tên không hợp lệ | Tên alias đã được dùng cho bean khác | Lỗi đăng ký alias/definition | Chọn alias không xung đột |
| Một bean có nhiều alias | `utcClock`, `systemClock` cùng trỏ tới một bean | Không phải xung đột nếu alias được đăng ký hợp lệ | Giữ tên chính và alias cần thiết |

Khi đọc exception, hãy xác định nó nói về **số lượng ứng viên theo type** hay **định danh bean trong registry**. Thêm `@Primary` không sửa được xung đột tên; đổi bean name không tự giải quyết mọi mơ hồ theo type nếu vẫn còn nhiều ứng viên.

## 12. Type matching và kiểu trả về của @Bean

Spring dự đoán type bean từ class hoặc metadata factory method. Vì vậy, kiểu trả về của phương thức `@Bean` có ảnh hưởng tới những type mà container có thể nhận diện trước khi tạo instance.

Ví dụ:

```java
@Bean
NotificationSender notificationSender() {
    return new EmailNotificationSender();
}
```

Definition thể hiện type khai báo là `NotificationSender`. Đây là type hợp đồng phù hợp nếu consumer chỉ cần interface.

Nếu một consumer yêu cầu `EmailNotificationSender` cụ thể, Spring có thể không xác định được type cụ thể từ metadata của factory method trong một số giai đoạn xử lý sớm, nhất là khi method chỉ khai báo kiểu trả về interface. Vì vậy, hãy khai báo kiểu trả về đủ cụ thể khi ứng dụng thật sự cần truy vấn theo implementation class:

```java
@Bean
EmailNotificationSender emailNotificationSender() {
    return new EmailNotificationSender();
}
```

Tuy nhiên, **không nên khai báo concrete type chỉ để làm consumer phụ thuộc vào implementation** nếu interface đã diễn đạt đủ hợp đồng. Hãy ưu tiên inject interface và dùng concrete type chỉ khi đó thực sự là yêu cầu.

Với factory bean, proxy hoặc bean được tạo theo cơ chế đặc biệt, type prediction có thể phức tạp hơn. Khi truy vấn theo type không cho kết quả như mong đợi, kiểm tra bean definition, factory method return type và API type introspection phù hợp.

## 13. Bean name và bean type khi có proxy

Spring AOP có thể bọc một bean bằng proxy. Proxy có thể triển khai interface hoặc là subclass của target class tùy chiến lược proxy.

Ví dụ:

```java
@Service
public class BillingService implements BillingOperations {

    @Transactional
    public void charge() {
        // ...
    }
}
```

Khi có proxy, bean name vẫn là định danh của bean trong context, nhưng object được consumer nhận có thể là proxy. Type mà proxy expose phụ thuộc chiến lược tạo proxy.

Vì vậy:

- Tra cứu theo bean name vẫn tìm bean đã được đăng ký dưới tên đó.
- Tra cứu theo interface mà proxy triển khai thường phù hợp.
- Tra cứu theo concrete class có thể thất bại nếu proxy là JDK dynamic proxy.
- Không nên suy luận rằng object nhận được luôn có đúng runtime class của implementation ban đầu.

Đây là một lý do khác để thiết kế dependency theo interface khi phù hợp.

## 14. Context cha-con và bean cùng tên

Spring có thể tổ chức nhiều application context theo quan hệ parent-child. Mỗi context có registry riêng.

Ví dụ khái niệm:

```text
Parent ApplicationContext
  bean: dataSource -> SharedDataSource
        |
        v
Child WebApplicationContext
  bean: dataSource -> TenantDataSource
```

Hai context có thể cùng có bean name `dataSource` mà không phải hai definition trùng tên trong cùng registry. Khi tra cứu từ context con, bean cùng tên ở child có thể được ưu tiên và che khuất bean từ context cha.

Đây là trường hợp khác với hai configuration cùng đăng ký `dataSource` vào một registry duy nhất.

Trong ứng dụng Spring Boot thông thường, phần lớn người học chỉ làm việc với một application context. Tuy nhiên, khi tích hợp nhiều web context, management context hoặc module có context riêng, cần nhớ phạm vi của bean name là **mỗi container/registry**, không phải một tên toàn cục cho cả JVM.

## 15. Thực hành: xây dựng ứng dụng có nhiều sender

Ta sẽ tạo ba sender với ba tên khác nhau:

```java
public interface NotificationSender {
    void send(String recipient, String message);
}

@Component("emailSender")
class EmailSender implements NotificationSender {
    public void send(String recipient, String message) {
        System.out.println("EMAIL: " + recipient + " - " + message);
    }
}

@Component("smsSender")
class SmsSender implements NotificationSender {
    public void send(String recipient, String message) {
        System.out.println("SMS: " + recipient + " - " + message);
    }
}

@Component("consoleSender")
class ConsoleSender implements NotificationSender {
    public void send(String recipient, String message) {
        System.out.println("CONSOLE: " + recipient + " - " + message);
    }
}
```

### 15.1. Service cần email

```java
@Service
class WelcomeService {

    private final NotificationSender sender;

    WelcomeService(@Qualifier("emailSender") NotificationSender sender) {
        this.sender = sender;
    }

    void welcome(String email) {
        sender.send(email, "Welcome!");
    }
}
```

### 15.2. Service cần SMS

```java
@Service
class SecurityAlertService {

    private final NotificationSender sender;

    SecurityAlertService(@Qualifier("smsSender") NotificationSender sender) {
        this.sender = sender;
    }

    void alert(String phoneNumber) {
        sender.send(phoneNumber, "Security alert");
    }
}
```

Hai service cùng phụ thuộc vào `NotificationSender` nhưng nhận implementation khác nhau nhờ qualifier.

### 15.3. Service cần tất cả sender

```java
@Service
class BroadcastService {

    private final Map<String, NotificationSender> senders;

    BroadcastService(Map<String, NotificationSender> senders) {
        this.senders = senders;
    }

    void broadcast(String recipient, String message) {
        senders.values().forEach(
                sender -> sender.send(recipient, message)
        );
    }
}
```

Map được inject có key là các bean name, còn value là instance tương ứng. Service có thể duyệt tất cả sender mà không cần yêu cầu Spring chọn một bean đơn.

Nếu muốn chỉ lấy sender thuộc một nhóm, có thể gắn custom qualifier lên các bean rồi inject collection với qualifier tại điểm inject.

### 15.4. Đọc kết quả bằng ApplicationContext

Trong một runner phục vụ minh họa:

```java
@Bean
CommandLineRunner inspectSenders(ApplicationContext context) {
    return args -> {
        Map<String, NotificationSender> senders =
                context.getBeansOfType(NotificationSender.class);

        senders.forEach((name, sender) ->
                System.out.println(name + " -> " + sender.getClass().getName())
        );
    };
}
```

Output có thể hiển thị ba tên bean cùng type interface. Nếu có AOP proxy hoặc decorator, class runtime hiển thị có thể là proxy thay vì class implementation ban đầu.

## 16. Cách xử lý khi Spring báo lỗi

### 16.1. NoUniqueBeanDefinitionException

Thông báo cho biết có nhiều bean cùng type phù hợp với một dependency đơn.

Các bước:

1. Đọc type đang được yêu cầu.
2. Liệt kê các bean name cùng type bằng report hoặc `getBeansOfType`.
3. Xác định service cần một implementation cụ thể, bean mặc định hay toàn bộ nhóm.
4. Dùng `@Qualifier`, `@Primary` hoặc collection injection tương ứng.

Không nên xóa implementation chỉ để làm hết lỗi nếu ứng dụng thực sự cần nhiều bean.

### 16.2. BeanDefinitionOverrideException

Thông báo cho biết một bean definition đang được đăng ký dưới tên đã có trong registry và việc overriding không được cho phép.

Các bước:

1. Xác định bean name bị trùng.
2. Tìm các configuration class hoặc component cùng đăng ký tên đó.
3. Xác định có cần cả hai bean hay chỉ một implementation.
4. Nếu cần cả hai, đổi tên và inject rõ ràng.
5. Nếu chỉ cần một, loại cấu hình thừa bằng profile/condition hoặc sửa nguồn đăng ký.

Không nên bật overriding toàn cục như giải pháp đầu tiên.

### 16.3. NoSuchBeanDefinitionException

Không có bean phù hợp theo name hoặc type yêu cầu. Kiểm tra:

- Bean đã được đăng ký chưa?
- Tên hoặc type yêu cầu có đúng không?
- Configuration có được scan/import không?
- Profile và condition có cho phép bean tồn tại không?
- Dependency chứa implementation có trên classpath không?

### 16.4. Bean được tìm theo name nhưng type không đúng

Nếu dùng:

```java
context.getBean("emailSender", PaymentGateway.class);
```

trong khi bean `emailSender` chỉ thực hiện `NotificationSender`, yêu cầu type không tương thích. Hãy kiểm tra cả tên và type thay vì giả định tên bean đủ để bảo đảm kiểu.

## 17. Checklist chọn theo type hay name

Khi khai báo dependency, hãy tự hỏi:

1. **Service cần một vai trò hay một implementation cụ thể?** Nếu chỉ cần vai trò, inject interface theo type.
2. **Có nhiều bean cùng type không?** Nếu có, xác định service cần một bean hay cả nhóm.
3. **Bean nào là mặc định?** Có thể dùng `@Primary` nếu một implementation phù hợp cho phần lớn điểm inject.
4. **Service có yêu cầu đặc tính cụ thể không?** Dùng `@Qualifier` hoặc custom qualifier.
5. **Code cần tra cứu bean theo định danh không?** Dùng name lookup ở code hạ tầng/registry có lý do rõ ràng.
6. **Hai cấu hình cùng đăng ký một tên không?** Kiểm tra bean definition collision, alias và cấu hình overriding.
7. **Nhiều tên có thực ra chỉ là alias của cùng bean không?** Phân biệt alias với hai definition riêng.
8. **Có đang dùng nhiều context không?** Xác định registry nào sở hữu bean name.

Một thiết kế tốt thường để service phụ thuộc vào type/contract, còn tên bean và cấu hình lựa chọn nằm ở composition root hoặc tầng wiring. Khi tên là một phần của API tích hợp, hãy đặt tên tường minh và ổn định.

## 18. Bài tập thực hành

### Bài tập 1 – Phân biệt cùng type và cùng name

Tạo hai class `EmailSender` và `SmsSender` cùng triển khai `NotificationSender`. Đăng ký chúng với bean name `emailSender` và `smsSender`.

Trả lời:

- Có bao nhiêu bean definition?
- Có bao nhiêu type implementation?
- `getBeansOfType(NotificationSender.class)` trả về bao nhiêu entry?
- Vì sao đây không phải lỗi bean name collision?

### Bài tập 2 – Một class, hai bean

Tạo class `PartnerClient` có thuộc tính timeout. Đăng ký hai bean `fastClient` và `slowClient` bằng hai phương thức `@Bean` trả về cùng class.

Kiểm tra hai bean có cùng type nhưng khác instance và khác bean name.

### Bài tập 3 – Tạo bean name collision

Tạo hai configuration cùng khai báo `@Bean("paymentGateway")`. Quan sát lỗi khi dùng cấu hình Spring Boot mặc định. Sau đó đổi tên thành `demoPaymentGateway` và `partnerPaymentGateway`, inject từng bean qua qualifier.

### Bài tập 4 – Alias hay bean thứ hai?

Khai báo:

```java
@Bean(name = {"mainClock", "systemClock"})
Clock clock() {
    return Clock.systemUTC();
}
```

Tra cứu bằng cả hai tên và so sánh object identity. Sau đó khai báo hai phương thức `@Bean` riêng để tạo hai `Clock` khác nhau, rồi giải thích sự khác biệt.

### Bài tập 5 – Chọn một bean hoặc cả nhóm

Tạo ba implementation `ReportExporter`: CSV, PDF và JSON.

- Dùng `@Primary` để chọn CSV mặc định.
- Dùng `@Qualifier("pdf")` cho service xuất PDF.
- Inject `List<ReportExporter>` cho service xuất theo nhiều định dạng.

Giải thích vì sao `@Primary` không loại PDF và JSON khỏi collection.

### Bài tập 6 – Phân biệt @Autowired và @Resource

Tạo hai bean cùng type có tên `emailSender` và `smsSender`. Thử inject bằng `@Autowired` không qualifier, `@Autowired @Qualifier("smsSender")` và `@Resource(name = "emailSender")`. Ghi lại cách lựa chọn và lỗi nếu bean name không tồn tại.

## 19. Những điều cần nhớ

**Bean cùng type và bean cùng tên là hai vấn đề khác nhau.**

- Nhiều bean cùng type nhưng khác name có thể cùng tồn tại. Spring chỉ cần thêm tiêu chí khi một điểm inject yêu cầu một bean duy nhất.
- Một bean có thể khớp nhiều type thông qua class, interface và kiểu cha.
- Một class có thể tạo nhiều bean instance với tên khác nhau qua nhiều phương thức `@Bean`.
- Bean name định danh bean trong một registry; alias là tên khác cùng trỏ tới một bean, không tạo instance mới.
- Hai bean definition khác nhau cùng tên trong một registry gây xung đột hoặc ghi đè tùy chính sách; Spring Boot hiện đại mặc định không khuyến khích overriding.
- `@Primary` chọn ứng viên mặc định; `@Qualifier` lọc ứng viên theo nhãn/metadata; collection injection nhận nhiều bean cùng type.
- `@Autowired` thường giải quyết theo type, trong khi `@Resource(name = "...")` thể hiện lựa chọn theo tên.
- Bean name collision không được giải quyết bằng `@Primary`; mơ hồ theo type không được giải quyết chỉ bằng cách bật bean overriding.
- Khi có proxy, object runtime được inject có thể khác class implementation ban đầu; dependency theo interface thường bền vững hơn.

Khi tổ chức Java configuration, hãy dùng **type để diễn đạt hợp đồng mà service cần**, dùng **name để định danh bean**, và dùng **qualifier/primary để giải quyết lựa chọn**. Chỉ khi tách rõ ba trách nhiệm này, ứng dụng mới có thể chứa nhiều implementation cùng type mà vẫn tránh xung đột tên và giữ wiring dễ hiểu.
