# Biểu diễn phụ thuộc tùy chọn bằng Optional trong Spring Core Container

## Mục tiêu

Một class có thể **cần** repository để hoàn thành nghiệp vụ chính, nhưng chỉ **muốn dùng** audit logger, bộ gửi thông báo hoặc adapter tích hợp bên ngoài khi các bean đó được đăng ký. Loại phụ thuộc thứ hai là *phụ thuộc tùy chọn* (*optional dependency*).

Trong Spring Core Container, `java.util.Optional<T>` là một cách khai báo rõ ràng rằng **bean `T` có thể vắng mặt**. Khi Spring giải quyết injection point có kiểu `Optional<T>`:

- Nếu tìm được một bean `T` thích hợp, Spring đưa vào `Optional.of(bean)` (về mặt ngữ nghĩa là giá trị **có mặt**).
- Nếu không có bean `T` thích hợp, Spring đưa vào `Optional.empty()` thay vì báo lỗi thiếu dependency.
- Nếu có nhiều bean `T` cạnh tranh mà Spring không thể chọn duy nhất một bean, `Optional` **không làm lỗi nhập nhằng biến mất**: vẫn phải giải quyết bằng qualifier, primary hoặc thiết kế lại kiểu phụ thuộc.
- Nếu bean ứng viên bị lỗi khi khởi tạo, `Optional` **không tự động nuốt lỗi đó**.

Sau bài này, bạn sẽ biết cách tiêm `Optional<T>` bằng constructor, phương thức `@Bean` và setter; đọc giá trị an toàn; phân biệt "vắng mặt" với "nhập nhằng"; chọn giải pháp phù hợp cho tính năng tùy chọn.

## 1. `Optional<T>` nói lên điều gì?

`Optional<T>` là một container Java biểu diễn một trong hai trạng thái:

| Trạng thái | Kiểm tra | Diễn giải trong dependency injection |
| --- | --- | --- |
| `Optional.empty()` | `isEmpty() == true` | Spring không tìm thấy bean `T` đáp ứng injection point đó |
| `Optional.of(value)` | `isPresent() == true` | Spring đã phân giải được bean `T` phù hợp |

Ví dụ ý tưởng:

```java
// Đoạn minh họa, bên trong class do Spring quản lý.
final class CheckoutService {
    private final Optional<AuditSink> auditSink;

    CheckoutService(Optional<AuditSink> auditSink) {
        this.auditSink = auditSink;
    }

    void checkout(String orderId) {
        auditSink.ifPresent(sink -> sink.record(orderId));
        // Các bước checkout bắt buộc vẫn được thực hiện.
    }
}
```

`AuditSink` trong ví dụ là interface ứng dụng tự định nghĩa, không phải API có sẵn của Spring. Với **constructor duy nhất**, Spring có thể tự dùng constructor đó mà không cần `@Autowired`. Khi không có bean `AuditSink`, trường `auditSink` nhận `Optional.empty()` và luồng checkout vẫn tiếp tục.

Điểm chính: `Optional<AuditSink>` biểu diễn **không bắt buộc có bean AuditSink**. Nó **không** có nghĩa là bean tùy chọn được tự sinh, khởi tạo trễ, có thể tồn tại nhiều bản sao, hay sẽ tự xuất hiện trong container về sau.

## 2. Spring phân giải `Optional<T>` như thế nào?

Giả sử Spring cần tạo một bean tiêu thụ, trong constructor có tham số `Optional<AuditSink>`:

1. Container đọc kiểu generic bên trong `Optional` để xác định dependency thực tế là `AuditSink`.
2. Spring tìm các bean có kiểu tương thích và thỏa điều kiện autowire tại injection point (ví dụ `@Qualifier`, generic, bean definition và metadata liên quan).
3. Nếu kết quả phân giải ra **một ứng viên hợp lệ**, Spring trao cho constructor một `Optional` chứa bean.
4. Nếu **không có ứng viên**, Spring trao cho constructor `Optional.empty()`; đây là tình huống được dự kiến trước.
5. Nếu **có nhiều ứng viên** mà cơ chế chọn bean vẫn không xác định được một bean duy nhất, quá trình tạo bean có thể thất bại vì nhập nhằng.

`Optional<T>` chỉ thay đổi cách xử lý **thiếu dependency**, không thay thế cơ chế lựa chọn bean. Chẳng hạn, nếu có hai bean cùng triển khai `AuditSink`, Spring có thể chọn một bean được đánh dấu `@Primary`, hoặc bạn có thể dùng `@Qualifier("stdoutAuditSink")` tại tham số `Optional<AuditSink>`. Nếu không có quy tắc phân giải, Spring không tự cho rằng đó là `Optional.empty()`.

**Quan hệ với `null`:** Khi Spring thực hiện injection đúng cách, thứ bạn nhận là **một đối tượng `Optional`**, không phải `null` đại diện cho thiếu dependency. Nếu tự gọi constructor bằng `new CheckoutService(null)` ngoài Spring, bạn đã vi phạm hợp đồng của class; `Optional` không ngăn mã người gọi truyền `null` vào.

## 3. Ví dụ hoàn chỉnh: tính năng audit và email có thể bật/tắt bằng sự hiện diện của bean

Ta xây dựng một ứng dụng Spring Framework thuần (không dùng Spring Boot), chạy hai container riêng:

- Container thứ nhất chỉ chứa cấu hình chung: có `smsNotifier`, nhưng **không** có `AuditSink` và không có `Notifier` mang qualifier `email`.
- Container thứ hai chứa cấu hình chung **và** cấu hình tích hợp: đăng ký thêm bean audit và bean email.

Nhờ đó, ta thấy một `Optional<T>` rỗng khi thiếu bean, và có giá trị khi bean phù hợp xuất hiện. Tình huống email cũng chứng minh rằng **có bean đúng kiểu vẫn chưa đủ** nếu injection point có qualifier khác.

### 3.1. Tạo dự án

Cấu trúc:

```text
spring-optional-di/
├── pom.xml
└── src/main/java/demo/OptionalInjectionDemo.java
```

`pom.xml` (Java 17+, Spring Framework 6.2.19):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-optional-di</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <version>3.13.0</version>
                <artifactId>maven-compiler-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 3.2. Mã Java chạy độc lập

`src/main/java/demo/OptionalInjectionDemo.java`:

```java
package demo;

import java.util.Optional;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class OptionalInjectionDemo {

    interface AuditSink {
        void record(String event);
    }

    interface Notifier {
        String channel();
    }

    static final class CheckoutService {
        private final Optional<AuditSink> auditSink;
        private final Optional<Notifier> emailNotifier;

        CheckoutService(Optional<AuditSink> auditSink,
                        Optional<Notifier> emailNotifier) {
            this.auditSink = auditSink;
            this.emailNotifier = emailNotifier;
        }

        void checkout() {
            System.out.println("audit=" +
                    (auditSink.isPresent() ? "present" : "absent"));

            auditSink.ifPresent(sink -> sink.record("order-42"));

            String selectedChannel = emailNotifier
                    .map(Notifier::channel)
                    .orElse("disabled");
            System.out.println("email=" + selectedChannel);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CommonConfig {

        @Bean
        Notifier smsNotifier() {
            return () -> "sms";
        }

        @Bean
        CheckoutService checkoutService(
                Optional<AuditSink> auditSink,
                @Qualifier("email") Optional<Notifier> emailNotifier) {
            return new CheckoutService(auditSink, emailNotifier);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class EnabledConfig {

        @Bean
        AuditSink stdoutAuditSink() {
            return event -> System.out.println("AUDIT: " + event);
        }

        @Bean
        @Qualifier("email")
        Notifier emailNotifier() {
            return () -> "email";
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(CommonConfig.class)) {
            System.out.println("without optional beans:");
            context.getBean(CheckoutService.class).checkout();
        }

        try (var context = new AnnotationConfigApplicationContext(
                CommonConfig.class, EnabledConfig.class)) {
            System.out.println("with optional beans:");
            context.getBean(CheckoutService.class).checkout();
        }
    }
}
```

Chạy trong thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.OptionalInjectionDemo
```

**Standard output do chương trình in** (không tính thông báo riêng của Maven/hệ thống logging):

```text
without optional beans:
audit=absent
email=disabled
with optional beans:
audit=present
AUDIT: order-42
email=email
```

Giải thích:

- Khi chỉ dùng `CommonConfig`, Spring vẫn tạo `CheckoutService` mặc dù thiếu `AuditSink` và thiếu bean `Notifier` có qualifier `email`. Cả hai tham số `Optional` đều rỗng.
- `smsNotifier` là bean `Notifier` thật, nhưng **không thỏa qualifier `email`**. Nó không bị chọn làm email và việc thiếu email không gây lỗi.
- Khi thêm `EnabledConfig`, `stdoutAuditSink` và `emailNotifier` được đăng ký; hai tham số nhận `Optional` có giá trị.
- `checkout()` sử dụng `ifPresent` cho audit, `map(...).orElse(...)` cho email. Luồng chính không cần kiểm tra `null` và không gọi `get()` khi Optional rỗng.
- Mỗi `AnnotationConfigApplicationContext` là một container riêng. Việc đăng ký thêm bean ở ví dụ thứ hai là **khởi tạo container khác**, không phải thay đổi động một container đang chạy.

### 3.3. Đặt `Optional<T>` trên constructor component

Ở dự án dùng component scan, bạn có thể giữ hợp đồng trực tiếp trong constructor:

```java
// Minh họa: interface AuditSink thuộc ứng dụng;
// class phải nằm trong phạm vi component scan.
import java.util.Optional;
import org.springframework.stereotype.Component;

@Component
class PurchaseProcessor {
    private final Optional<AuditSink> auditSink;

    PurchaseProcessor(Optional<AuditSink> auditSink) {
        this.auditSink = auditSink;
    }

    void handle(String event) {
        auditSink.ifPresent(sink -> sink.record(event));
    }
}
```

Đây là **đoạn minh họa cần đặt vào dự án có AuditSink**, không phải chương trình độc lập. Constructor injection giúp field là `final`, dependency rõ ràng, và dễ tạo instance giả lập trong unit test bằng `Optional.empty()` hay `Optional.of(fake)`.

Không cần đặt `@Autowired` nếu class chỉ có một constructor. Khi class có nhiều constructor, Spring có các quy tắc chọn constructor riêng; `Optional<T>` không tự quyết định Spring sẽ chọn constructor nào.

## 4. Những vị trí tiêm `Optional<T>` thường dùng

### Constructor — ưu tiên cho hợp đồng của class

```java
// Đoạn minh họa trong class Spring-managed:
private final Optional<AuditSink> auditSink;

public MyService(Optional<AuditSink> auditSink) {
    this.auditSink = auditSink;
}
```

Hãy coi đây là một **quyết định thiết kế**: class chấp nhận vận hành khi không có `AuditSink`. Nếu không có dependency đó thì chức năng chính vẫn hoạt động, khai báo `Optional` là hợp lý. Nếu thiếu dependency làm chức năng chính sai, hãy để `AuditSink` là tham số bắt buộc kiểu `AuditSink` thay vì che giấu lỗi cấu hình.

### Tham số của phương thức `@Bean`

```java
@Configuration(proxyBeanMethods = false)
class ServiceConfig {
    @Bean
    MyService myService(Optional<AuditSink> auditSink) {
        return new MyService(auditSink);
    }
}
```

Đoạn này là minh họa cấu hình trong dự án đã định nghĩa `MyService` và `AuditSink`. Spring tự phân giải tham số phương thức factory theo quy tắc dependency injection, nên đây cũng là cách thuận tiện khi bạn không muốn đặt annotation của Spring trong class nghiệp vụ.

### Setter hoặc field dùng `@Autowired`

```java
// Đoạn minh họa trong Spring-managed bean:
private Optional<AuditSink> auditSink = Optional.empty();

@Autowired
void setAuditSink(Optional<AuditSink> auditSink) {
    this.auditSink = auditSink;
}
```

Với injection point kiểu `Optional<T>`, sự thiếu bean `T` **không** khiến setter bắt buộc bị lỗi: Spring có thể truyền `Optional.empty()`. Đây là khác biệt quan trọng với một setter chỉ nhận `AuditSink` và dùng `@Autowired(required = false)`: Spring có thể **bỏ qua hẳn lời gọi setter** nếu không phân giải được dependency của setter đó.

Field injection `@Autowired private Optional<AuditSink> auditSink;` cũng được hỗ trợ, nhưng constructor injection thường dễ bảo trì và dễ test hơn.

## 5. Đọc `Optional` an toàn

Bản thân `Optional` đã đưa ra các phương thức để xử lý đủ hai trường hợp:

| API Java | Khi có giá trị | Khi không có giá trị |
| --- | --- | --- |
| `isPresent()` / `isEmpty()` | Kiểm tra trạng thái | Kiểm tra trạng thái |
| `ifPresent(action)` | Gọi `action` với bean | Không làm gì |
| `ifPresentOrElse(action, emptyAction)` | Gọi `action` | Chạy `emptyAction` |
| `map(transform)` | Biến đổi giá trị và bọc vào Optional mới | Trả `Optional.empty()` |
| `orElse(fallback)` | Trả giá trị có sẵn | Trả fallback |
| `orElseGet(supplier)` | Trả giá trị có sẵn | Mới gọi supplier |
| `orElseThrow(...)` | Trả giá trị có sẵn | Ném exception do ứng dụng quyết định |

Một số mẫu thường dùng:

```java
// Đoạn minh họa bên trong class đã có field auditSink:
// 1. Tác vụ chỉ thực hiện nếu tích hợp có mặt.
auditSink.ifPresent(sink -> sink.record("PAYMENT_SUCCESS"));

// 2. Đường xử lý thay thế nếu thiếu bean.
auditSink.ifPresentOrElse(
        sink -> sink.record("PAYMENT_SUCCESS"),
        () -> System.out.println("Audit adapter not installed")
);

// 3. Trích một giá trị với fallback thuần Java.
String status = auditSink
        .map(sink -> "audit-enabled")
        .orElse("audit-disabled");
```

**Phân biệt `orElse` và `orElseGet`.** `orElse(expensiveFallback())` vẫn tính biểu thức đối số khi gọi phương thức, kể cả Optional đã có giá trị. `orElseGet(() -> expensiveFallback())` chỉ gọi supplier khi Optional rỗng. Nhưng nếu bạn muốn **thực hiện side effect** khi không có bean, `ifPresentOrElse` hoặc `if (optional.isEmpty())` thường diễn đạt ý định rõ hơn.

Tránh `optional.get()` mà không kiểm tra: nếu Optional rỗng, Java ném `NoSuchElementException`. Cũng không dùng `optional.orElse(null)` rồi làm toàn bộ chỗ gọi trở lại kiểu kiểm tra `null` nếu có thể xử lý ngay qua `map`, `ifPresent` hoặc fallback có ý nghĩa.

**Không nên lưu `Optional` trong một field chỉ vì muốn thay thế mọi trường nullable.** Với Spring DI, dùng `Optional<T>` ở **ranh giới tiêm dependency** là cách giao tiếp hợp đồng rõ ràng. Bên trong class, tùy nhu cầu bạn có thể giữ nguyên Optional, hoặc ánh xạ nó sang một chiến lược fallback hợp lệ để giảm phân nhánh; quyết định này không đổi cách Spring chọn bean.

## 6. Kết hợp `Optional<T>` với `@Qualifier` và `@Primary`

### `@Qualifier`: một loại bean nhưng nhiều mục đích

Nếu ứng dụng có nhiều `Notifier` nhưng chỉ một cái phục vụ email:

```java
// Trong một cấu hình Spring; đây là các đoạn minh họa.
@Bean
@Qualifier("email")
Notifier smtpNotifier() {
    return () -> "smtp";
}

@Bean
@Qualifier("sms")
Notifier smsNotifier() {
    return () -> "sms";
}

// Tại injection point (constructor hoặc @Bean factory method):
MyService(@Qualifier("email") Optional<Notifier> notifier) {
    // ...
}
```

`@Qualifier("email")` chỉ **lọc** trong các bean `Notifier`. Khi không có bean thỏa điều kiện, `Optional.empty()`; khi có một bean thỏa điều kiện, Optional chứa bean đó. Nếu có nhiều bean **cùng thỏa qualifier** và không có quy tắc nào xác định được ứng viên duy nhất, lỗi nhập nhằng vẫn có thể xảy ra. Một qualifier không đảm bảo rằng cuối cùng chỉ còn đúng một bean.

### `@Primary`: chọn khi có nhiều bean tương thích

```java
// Minh họa trong @Configuration:
@Bean
@Primary
AuditSink preferredAuditSink() {
    return event -> { /* gửi sang hệ thống audit chính */ };
}

@Bean
AuditSink secondaryAuditSink() {
    return event -> { /* gửi sang hệ thống khác */ };
}
```

Với injection point `Optional<AuditSink>` không có qualifier, `@Primary` giúp Spring chọn một bean ưu tiên trong tình huống nhiều ứng viên phù hợp. Nếu có **hai primary cùng cạnh tranh** hoặc cấu hình khác tạo ra ứng viên không thể phân biệt, Spring vẫn có thể báo lỗi. Không phải cứ bọc kiểu `T` bằng `Optional<T>` là có quyền lấy "bất kỳ một bean" từ tập ứng viên.

### Generic vẫn phải được khai báo đúng

Kiểu generic bên trong `Optional<T>` là thông tin quan trọng. Khi có `Repository<Customer>` và `Repository<Order>`, injection point `Optional<Repository<Customer>>` có thể dùng generic làm điều kiện phân biệt nếu bean definitions giữ được metadata kiểu này. Tránh raw `Optional` hoặc kiểu khai báo quá rộng khiến Spring không biết chính xác `T` mà bạn muốn.

## 7. `Optional<T>` khác `@Autowired(required=false)`, `@Nullable` và `ObjectProvider<T>`

Các công cụ này cùng giải quyết bài toán thiếu dependency nhưng có hợp đồng khác nhau:

| Cách khai báo | Nếu không có bean `T` | Đặc tính |
| --- | --- | --- |
| `Optional<T>` tại injection point | Nhận `Optional.empty()` | Thể hiện rõ cả trạng thái có và không có giá trị; phù hợp dependency tùy chọn đơn lẻ |
| `@Autowired(required=false)` trên field `T` | Spring không gán field; giữ mặc định | Dễ cần `null`/giá trị mặc định; thuộc tính `required` áp dụng ở cấp injection point |
| `@Autowired(required=false)` trên setter `setT(T)` | Setter có thể bị bỏ qua hoàn toàn | Không gọi setter trong trường hợp không thể phân giải |
| `@Nullable T` ở tham số được Spring hỗ trợ | Nhận `null` khi thiếu bean | Giao tiếp bằng nullable; phải xử lý null an toàn |
| `ObjectProvider<T>` | Nhận provider; gọi `getIfAvailable()` có thể trả null | Truy vấn bean có chủ đích tại thời điểm sử dụng, phù hợp lazy/dynamic lookup |
| `T` bắt buộc (không Optional) | Thường lỗi thiếu dependency khi tạo bean | Đúng cho thành phần không thể hoạt động nếu vắng `T` |

`@Nullable` ở đây là annotation mà Spring nhận biết trên **tham số**, ví dụ `@Nullable AuditSink auditSink`. Trong Spring Framework 6.2, hỗ trợ annotation nullable trên type-use có giới hạn; dùng tham số với annotation được hỗ trợ nếu chọn cách này. `Optional` giữ mô hình Java nhất quán hơn vì bạn không cần xử lý tham số `null`.

### Ví dụ đối chiếu `@Autowired(required=false)`

```java
// Đoạn minh họa trong một Spring-managed bean:
private AuditSink auditSink; // mặc định null

@Autowired(required = false)
void setAuditSink(AuditSink auditSink) {
    this.auditSink = auditSink;
}
```

Khi `AuditSink` không tồn tại, setter có thể **không được gọi**. Nếu class cần một mặc định khác `null`, bạn phải thiết kế giá trị ban đầu hoặc một implementation dự phòng. Với `Optional<AuditSink>`, khi Spring inject, caller nhận một đối tượng để hỏi trực tiếp `isPresent()` hoặc `ifPresent()`.

Đừng đặt `@Autowired(required=false)` lên một constructor một cách máy móc và nghĩ từng tham số của constructor đó sẽ thành tùy chọn giống `Optional<T>`. Quy tắc chọn constructor trong Spring khác với field/setter; cách diễn đạt rõ ý định cho một tham số không bắt buộc là khai báo `Optional<T>` ngay tại tham số.

### Khi nào chọn `ObjectProvider<T>`?

`Optional<T>` được phân giải **khi dependency được tiêm** vào bean tiêu thụ. Nó không đảm bảo tạo bean `T` trễ và không tự truy vấn lại khi registry thay đổi.

`ObjectProvider<T>` cho phép truy vấn lúc cần:

```java
// Đoạn minh họa trong Spring-managed bean:
import org.springframework.beans.factory.ObjectProvider;

final class AuditService {
    private final ObjectProvider<AuditSink> auditProvider;

    AuditService(ObjectProvider<AuditSink> auditProvider) {
        this.auditProvider = auditProvider;
    }

    void record(String event) {
        AuditSink sink = auditProvider.getIfAvailable();
        if (sink != null) {
            sink.record(event);
        }
    }
}
```

`getIfAvailable()` có thể trả `null` khi thiếu bean, nhưng **không** có nghĩa mọi lỗi đều được bỏ qua; việc khởi tạo bean hoặc chọn giữa nhiều ứng viên vẫn phải hợp lệ. Provider cũng có `ifAvailable(Consumer<T>)` để bỏ phần kiểm tra null, `getIfUnique()` cho trường hợp chỉ muốn giá trị khi chọn được ứng viên duy nhất theo ngữ nghĩa API, và `stream()`/`orderedStream()` cho nhu cầu lấy nhiều bean. Đặc biệt với scope `prototype`, gọi provider nhiều lần có thể lấy instance khác nhau, tùy cách đăng ký/scope của bean.

Chọn `ObjectProvider<T>` khi cần truy vấn lặp lại, lazy access, bean theo scope hoặc tích hợp nhiều ứng viên. Chọn `Optional<T>` khi tại thời điểm tạo consumer, bạn chỉ cần biết **có hay không một dependency**.

## 8. Phụ thuộc tùy chọn khác tính năng tùy chọn

Không phải mọi tính năng bật/tắt đều nên được thiết kế bằng sự vắng mặt của bean:

- **Phụ thuộc tùy chọn:** `CheckoutService` vận hành bình thường khi không có `AuditSink`; đây là ví dụ tốt cho `Optional<AuditSink>`.
- **Feature flag:** cấu hình có thể nói `audit.enabled=false` dù bean `AuditSink` vẫn tồn tại. Lúc này trạng thái tính năng và sự hiện diện của bean là **hai khái niệm riêng**.
- **Tích hợp theo điều kiện:** nếu configuration quyết định có tạo `AuditSink` hay không, `Optional<AuditSink>` trở thành cách consumer ứng xử khi bean không được đăng ký. Trong Spring Framework thuần có `@Conditional` và cơ chế đăng ký bean có điều kiện; Spring Boot còn cung cấp nhiều `@ConditionalOn...` như `@ConditionalOnProperty`. Các annotation `@ConditionalOn...` là tính năng của **Spring Boot**, không phải API lõi `spring-context` dùng trong ví dụ Maven ở trên.

Nếu hành vi chính **không được phép hoạt động** khi thiếu bean, tránh khai báo Optional chỉ để application khởi động được. Ví dụ, không nên biến `PaymentGateway` bắt buộc thành `Optional<PaymentGateway>` rồi lặng lẽ bỏ qua thanh toán. Khi đó lỗi thiếu cấu hình nên được phát hiện sớm.

Nếu thiếu tích hợp thì cần fallback, hãy xác định rõ fallback đó:

```java
// Minh họa ý tưởng: có thể chọn implementation fallback thuần Java.
AuditSink selected = auditSink.orElseGet(() -> event -> {
    // Không ghi audit sang hệ thống ngoài; chính sách fallback chủ đích.
});
selected.record("order-42");
```

Trong dự án thực, một `NoOpAuditSink` cũng có thể được đăng ký làm bean có điều kiện nếu muốn các consumer luôn nhận dependency không tùy chọn. Đừng để cả fallback bean và bean thực cùng khớp mà không xác định luật lựa chọn.

## 9. Những hiểu lầm phổ biến

### "`Optional<T>` giúp che mọi lỗi bean"

**Sai.** Nó chỉ biểu diễn sự **vắng mặt hợp lệ của dependency**. Một bean `T` có cấu hình sai, vòng phụ thuộc không được hỗ trợ, constructor ném exception hoặc hai ứng viên không thể phân biệt vẫn có thể làm context khởi động thất bại.

### "Có hai bean `T` thì Spring sẽ trả `Optional.empty()`"

**Sai.** Hai bean khác nhau không có nghĩa là thiếu bean. Spring phải chọn một ứng viên theo cơ chế type matching, qualifier, `@Primary` và metadata tương ứng; nếu không chọn được, lỗi ambiguity là điều cần sửa.

### "`Optional<T>` sẽ tự cập nhật nếu có bean mới"

**Sai.** Giá trị `Optional` nhận qua constructor là kết quả phân giải tại thời điểm tiêm. Nếu nghiệp vụ cần lookup động, `ObjectProvider<T>` hoặc các API container phù hợp diễn đạt đúng ý hơn.

### "`Optional<T>` sẽ tự phát hiện config property của kiểu `T`"

**Sai.** Tìm bean và đọc property là hai cơ chế khác nhau. `Optional<AuditSink>` xem container có bean `AuditSink` phù hợp hay không. `application.properties`/`application.yml` không tự tạo bean `AuditSink` chỉ nhờ có một khóa trong file.

### "Nên dùng `Optional` cho tất cả dependency"

Không hợp lý. Dùng `Optional` khi **thiếu dependency là trường hợp hợp lệ được thiết kế trước**. Dependency bắt buộc nên giữ kiểu `T` trực tiếp để ứng dụng thất bại rõ ràng nếu cấu hình thiếu.

### "`Optional<List<T>>` và `List<T>` là một"

Chúng biểu thị hợp đồng khác nhau. `Optional<List<T>>` nói **cả giá trị danh sách có thể vắng mặt**; `List<T>` nói consumer nhận một danh sách phần tử. Với multi-bean collection injection, Spring có các quy tắc riêng cho tập ứng viên và một số trường hợp cho collection rỗng (đặc biệt ở constructor duy nhất). Không tự bọc collection bằng Optional để giả định Spring luôn lấy được một danh sách các bean hay luôn trả empty khi không có phần tử. Hãy chọn `List<T>` khi cần 0..n implementation và xem xét `ObjectProvider<T>.stream()` nếu cần truy vấn động.

## 10. Chẩn đoán lỗi theo tình huống

| Hiện tượng | Kiểm tra | Cách khắc phục |
| --- | --- | --- |
| `Optional.isEmpty()` dù đã viết implementation | Class đã đăng ký thành bean chưa, component scan có đúng package, điều kiện registration có bật không | Đăng ký bean hoặc chỉnh phạm vi scan/cấu hình điều kiện |
| Có bean đúng interface nhưng Optional vẫn rỗng | Qualifier, generic và trạng thái autowire candidate có khớp không | Sửa qualifier, kiểu generic hoặc metadata đăng ký |
| Context lỗi `NoUniqueBeanDefinitionException` | Có nhiều ứng viên `T` hợp lệ nhưng chưa chọn được một cái | Dùng `@Qualifier` hoặc `@Primary`; cân nhắc multi-bean injection nếu cần nhiều bean |
| Context lỗi `BeanCreationException` | Factory/constructor của bean được chọn đã thất bại | Sửa lỗi tạo bean; `Optional` không phải cơ chế bắt lỗi khởi tạo |
| `NullPointerException` ở biến Optional | Đối tượng được tạo bằng `new` ngoài Spring, hoặc người gọi đã truyền `null` | Đảm bảo consumer do Spring quản lý, test truyền `Optional.empty()` |
| `NoSuchElementException` khi gọi `get()` | Optional rỗng nhưng code không kiểm tra | Dùng `ifPresent`, `map`, `orElseGet` hoặc `orElseThrow` có ý nghĩa |
| `@Autowired(required=false)` setter không chạy | Setter có dependency không phân giải được | Cân nhắc tham số `Optional<T>` hoặc thiết kế mặc định rõ ràng |
| Tưởng Optional cho lazy bean nhưng bean vẫn khởi tạo sớm | `Optional<T>` được resolve lúc inject | Dùng `ObjectProvider<T>` cho lazy lookup có chủ đích |

Cách gỡ lỗi có trình tự: (1) xác định bean `T` có được đăng ký không; (2) kiểm tra kiểu thực tế, generic và component scan; (3) đọc các qualifier và `@Primary`; (4) phân biệt **không có ứng viên** với **có quá nhiều ứng viên**; (5) nếu có ứng viên mà vẫn thất bại, kiểm tra exception gốc trong quá trình tạo bean.

Khi kiểm thử, có thể xây hai context như ví dụ: một không đăng ký optional beans và một có đăng ký. Điều này kiểm chứng cả **đường fallback** và **đường có dependency**. Với consumer tự tạo trong unit test, truyền thẳng `Optional.empty()` hoặc `Optional.of(fake)`; không cần dựng toàn bộ context cho các phép kiểm tra nghiệp vụ thuần Java.

## 11. Bài tập và đáp án định hướng

**Bài 1.** Trong ví dụ chạy độc lập, xóa `@Qualifier("email")` khỏi tham số `Optional<Notifier>` của `checkoutService`. Với `CommonConfig`, điều gì xảy ra?

*Đáp án:* Vì chỉ có bean `smsNotifier` thuộc kiểu `Notifier`, tham số Optional bây giờ có thể chứa `smsNotifier`, và chương trình sẽ in `email=sms`. Điều này cho thấy một dependency "tùy chọn" vẫn phải được **lọc đúng ngữ nghĩa**; bỏ qualifier có thể chọn tích hợp không mong muốn.

**Bài 2.** Giữ thay đổi của Bài 1, nhưng thêm cả `EnabledConfig`. Với hai bean `Notifier` (`smsNotifier` và `emailNotifier`) và không có `@Primary`, hãy dự đoán.

*Đáp án:* Spring cần chọn một `Notifier` cho injection point kiểu `Optional<Notifier>`. Nếu không có thêm quy tắc phân biệt hợp lệ, context có thể thất bại vì nhiều ứng viên. Bọc bằng `Optional` không chuyển tình huống này thành empty.

**Bài 3.** Chuyển `AuditSink` từ tính năng phụ sang **điều kiện bắt buộc** để hoàn tất thanh toán. Nên sửa kiểu constructor thế nào?

*Đáp án:* Nhận trực tiếp `AuditSink` thay vì `Optional<AuditSink>`. Khi không đăng ký bean, Spring báo lỗi khởi tạo consumer, giúp phát hiện việc thiếu dependency bắt buộc.

**Bài 4.** Consumer muốn truy cập một `AuditSink` có scope `prototype` mới ở mỗi lần xử lý. Giữ `Optional<AuditSink>` trên constructor có bảo đảm điều đó không?

*Đáp án:* Không. Optional được phân giải khi inject. Cân nhắc `ObjectProvider<AuditSink>` rồi gọi `getObject()`/`ifAvailable(...)` lúc cần; hiểu rõ chính sách scope và hành vi khi thiếu bean.

**Bài 5.** Viết lại cách lấy channel email mà không gọi `get()` và không tạo fallback tốn kém khi Optional có giá trị.

*Đáp án:*

```java
String channel = emailNotifier
        .map(Notifier::channel)
        .orElseGet(() -> computeFallbackChannel());
```

Đây là đoạn minh họa giả định `computeFallbackChannel()` có sẵn trong class; supplier chỉ chạy khi Optional rỗng.

## Tóm lược kiến thức cần ghi nhớ

- `Optional<T>` là **hợp đồng thiếu bean `T` có thể chấp nhận được**.
- Có ứng viên duy nhất/phân giải được → `Optional` có giá trị; không có ứng viên → `Optional.empty()`.
- Nhiều ứng viên không phân giải được, lỗi khởi tạo bean và cấu hình sai **vẫn là lỗi**.
- Dùng constructor injection để khai báo rõ optional dependency; dùng `@Qualifier` khi cần đúng loại implementation.
- Dùng `ifPresent`, `map`, `orElseGet` thay vì `get()` thiếu kiểm tra hoặc tạo `null` không cần thiết.
- Chọn `ObjectProvider<T>` khi cần tra cứu linh hoạt theo thời điểm/scope; dùng dependency kiểu `T` trực tiếp cho chức năng bắt buộc.

## Tài liệu tham khảo chính thức

- Spring Framework, [Using `@Autowired`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html) — Optional, `required=false`, constructor và factory method injection.
- Spring Framework, [Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html) — cách qualifier thu hẹp ứng viên.
- Spring Framework, [Using `@Primary`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-primary.html) — chọn ứng viên ưu tiên.
- Spring Framework, [`ObjectProvider<T>` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/ObjectProvider.html) — truy vấn phụ thuộc linh hoạt.
- Java SE 17, [`Optional<T>` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html) — `ifPresent`, `map`, `orElse`, `orElseGet`.
