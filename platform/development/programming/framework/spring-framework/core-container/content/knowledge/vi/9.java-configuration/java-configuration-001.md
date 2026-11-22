# Vai trò của @Configuration và phương thức @Bean trong Spring Core Container

## 1. Mục tiêu

**Java-based configuration** cho phép mô tả Spring IoC container bằng mã Java thay vì chỉ dùng XML hay để component scanning tự tìm toàn bộ class. Hai annotation trung tâm là:

- `@Configuration`: đánh dấu **class là nguồn khai báo bean definitions**. Class này thường tập hợp các phương thức `@Bean` và có thể được nạp bằng `AnnotationConfigApplicationContext`, `@Import` hoặc cơ chế quét cấu hình.
- `@Bean`: đánh dấu **phương thức factory** tạo, cấu hình và trả về một đối tượng để Spring đăng ký và quản lý dưới dạng bean.

Điều quan trọng là phân biệt **phương thức Java trả object** với **bean được container quản lý**. Spring đọc cấu hình để xây bean definitions, chọn dependency, áp dụng scope, lifecycle, bean post-processors và các quy tắc khác. Khi tự gọi phương thức factory bên ngoài cơ chế Spring, đối tượng được trả về **không tự động** trở thành bean được container quản lý.

Bài này tập trung vào hai annotation trên trong **Spring Framework Core Container**, gồm:

1. Vai trò riêng của class `@Configuration` và phương thức `@Bean`.
2. Khi nào nên dùng chúng thay cho `@Component`/`@Service`.
3. Cơ chế đặt tên bean, dependency injection, scope và lifecycle.
4. Sự khác nhau giữa **full `@Configuration`** và **lite `@Bean`**, đặc biệt `proxyBeanMethods`.
5. Ví dụ Java 17 + Spring Framework chạy độc lập, với lệnh Maven và stdout dự kiến.
6. Các lỗi thiết kế, cấu hình và kiểm thử thường gặp.

## 2. Đặt hai annotation vào bức tranh IoC

Spring quản lý đối tượng dựa trên **bean definitions**. Một bean definition có thể mô tả tên, kiểu bean, cách khởi tạo, dependency, scope và lifecycle. Java configuration là một **nguồn metadata** để container tạo các bean definitions đó.

Xét cấu hình ngắn:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AppConfig {

    @Bean
    public MessageService messageService() {
        return new MessageService();
    }
}
```

Đây là **đoạn minh họa**: `MessageService` là class do ứng dụng định nghĩa, không phải API sẵn của Spring; ví dụ runnable đầy đủ ở mục 6.

`@Configuration` áp dụng lên `AppConfig`, diễn đạt "class này định nghĩa cấu hình cho container". `@Bean` áp dụng lên `messageService()`, diễn đạt "giá trị trả về từ factory method này phải được Spring quản lý như một bean". Nếu dùng Spring để đăng ký `AppConfig` đúng cách, container có thể cung cấp bean `messageService` cho những consumer cần kiểu `MessageService`.

Luồng khái niệm:

```text
AppConfig.class
      |
      | đọc @Configuration và các @Bean method
      v
Bean definitions trong IoC container
      |
      | giải quyết dependency, scope và lifecycle
      v
Object instance được Spring quản lý
      |
      | getBean / constructor injection
      v
Consumer sử dụng bean
```

Không nên hiểu `@Bean` là lời gọi `new` tự xảy ra ngay khi JVM đọc annotation. Tạo instance là bước của container, có thể khác nhau tùy scope, lazy initialization và thời điểm giải quyết dependency.

### So với cấu hình XML

Cấu hình:

```java
@Configuration
class Config {
    @Bean
    public MessageService messageService() {
        return new MessageService();
    }
}
```

về mục đích đăng ký bean tương tự định nghĩa XML:

```xml
<bean id="messageService" class="demo.MessageService"/>
```

XML trên chỉ minh họa cấu trúc; `demo.MessageService` phải thực sự tồn tại nếu sử dụng. Java config có thêm lợi ích compiler kiểm tra trực tiếp lời gọi constructor và kiểu dữ liệu.

## 3. Vai trò của @Configuration

`@Configuration` thuộc package:

```java
import org.springframework.context.annotation.Configuration;
```

Nó đánh dấu một **class** là cấu hình. Về mặt stereotype, `@Configuration` cũng được meta-annotate bằng `@Component`, nên có thể được tìm thấy khi component scanning phù hợp. Tuy nhiên, nếu bạn chỉ khởi tạo một class cấu hình bằng `new AppConfig()` thì Spring **không** tự nạp các bean definitions. Class cấu hình cần được **đăng ký** vào container.

### 3.1. Đăng ký class cấu hình

Một cách cơ bản:

```java
// Đoạn minh họa, giả định AppConfig đã tồn tại.
try (var context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {
    MessageService service = context.getBean(MessageService.class);
    service.send("Hello");
}
```

Import `org.springframework.context.annotation.AnnotationConfigApplicationContext`. Constructor nhận `AppConfig.class` đăng ký cấu hình vào ApplicationContext và refresh context. Bean có thể được tra cứu theo kiểu/tên; khi thoát `try-with-resources`, context được đóng và lifecycle callback thích hợp được gọi.

Các cách khác:

- `@Import(OtherConfig.class)` để một cấu hình khai báo import cấu hình khác.
- Component scanning tìm class `@Configuration` trong vùng quét.
- Dùng `AnnotationConfigApplicationContext` rồi gọi `register(Config.class)` và `refresh()`.
- Trong ứng dụng Spring Boot, cơ chế bootstrap xử lý configuration classes thông qua các annotation của Boot; nhưng không cần Boot để hiểu `@Configuration` trong Core Container.

### 3.2. Class cấu hình chứa những gì?

Một class cấu hình có thể chứa:

- Phương thức `@Bean` trả về bean cần container quản lý.
- `@Import` để chia cấu hình thành module.
- `@ComponentScan` để chỉ định package chứa component ứng viên.
- `@PropertySource`, `@Profile`, `@Conditional` hoặc những annotation điều khiển đăng ký phù hợp, khi ứng dụng có nhu cầu.
- Constructor và các dependency của chính class cấu hình, nhưng cần cân nhắc thời điểm khởi tạo và tránh vòng phụ thuộc.

Không nhất thiết mỗi class cấu hình phải chứa nhiều phương thức `@Bean`. Có thể chia file theo feature như `PersistenceConfig`, `WebConfig`, `MessagingConfig` khi chúng thực sự quản lý những nhóm bean khác nhau. Tách theo **trách nhiệm cấu hình** tốt hơn một file khổng lồ chứa tất cả bean toàn hệ thống.

### 3.3. @Configuration là metadata, không phải service nghiệp vụ

Class `@Configuration` nên tập trung vào **wiring**: chọn implementation, xây đối tượng và khai báo dependency. Logic xử lý đơn hàng, tính giá và ghi dữ liệu nên nằm ở service/repository, không nằm trong method cấu hình.

Phản ví dụ:

```java
@Configuration
class PoorDesignConfig {

    @Bean
    PaymentService paymentService() {
        // Không nên tính toàn bộ nghiệp vụ thanh toán tại đây.
        // Chỉ nên xây dựng đối tượng và các collaborator.
        return new PaymentService();
    }
}
```

Đây là ví dụ phác thảo thiết kế, không phải ứng dụng độc lập. Method `paymentService()` là factory bean, không phải endpoint gọi để thanh toán từng đơn hàng.

## 4. Vai trò của @Bean

`@Bean` thuộc package:

```java
import org.springframework.context.annotation.Bean;
```

Annotation này được đặt trên **method**; Spring sử dụng phương thức như một factory để tạo đối tượng bean.

```java
@Configuration
class AppConfig {
    @Bean
    PaymentGateway paymentGateway() {
        return new InMemoryPaymentGateway();
    }
}
```

Trong đoạn minh họa, `PaymentGateway` là interface ứng dụng và `InMemoryPaymentGateway` là implementation. Spring đăng ký bean theo **return type được khai báo** và những metadata có thể phân giải khi chạy. Nếu container yêu cầu tạo bean này, nó gọi factory method trong ngữ cảnh phù hợp rồi quản lý instance trả về.

### 4.1. Tên bean mặc định

Thông thường, bean name mặc định từ phương thức `@Bean` là **tên phương thức**:

```java
@Bean
PaymentGateway paymentGateway() {
    return new InMemoryPaymentGateway();
}
```

Tên bean là `paymentGateway`. Có thể tra cứu:

```java
// Minh họa khi context đã được tạo.
PaymentGateway gateway =
        context.getBean("paymentGateway", PaymentGateway.class);
```

Ngoài tên, Spring vẫn hỗ trợ tiêm bean **theo kiểu** nếu có một ứng viên phù hợp và các quy tắc lựa chọn được thỏa. Tên bean và tên biến Java trong consumer không nhất thiết phải giống nhau để việc constructor injection hoạt động.

### 4.2. Đặt tên và alias tường minh

`@Bean` hỗ trợ `name` hoặc alias `value`:

```java
@Bean(name = {"defaultGateway", "primaryPaymentAdapter"})
PaymentGateway paymentGateway() {
    return new InMemoryPaymentGateway();
}
```

Ở đây `defaultGateway` là tên chính; `primaryPaymentAdapter` là **alias cho cùng bean**, không tạo hai instance riêng. Đây là alias bean name của container, **khác** annotation `@AliasFor` dùng để mô tả alias giữa các thuộc tính annotation.

Khi có nhiều bean cùng interface:

```java
@Bean("fastGateway")
PaymentGateway fastGateway() {
    return new FastGateway();
}

@Bean("safeGateway")
PaymentGateway safeGateway() {
    return new SafeGateway();
}
```

consumer nhận `PaymentGateway` đơn lẻ có thể cần `@Qualifier("safeGateway")` hoặc `@Primary`/quy tắc chọn ứng viên khác. `@Bean` không tự chọn "bean đầu tiên" khi kiểu có nhiều implementation. Hai phương thức trên là ví dụ minh họa yêu cầu các class tương ứng.

### 4.3. Kiểu trả về của factory method

Có thể khai báo kiểu interface:

```java
@Bean
Storage storage() {
    return new FileStorage();
}
```

hoặc class cụ thể:

```java
@Bean
FileStorage fileStorage() {
    return new FileStorage();
}
```

Cả hai đều hợp lệ nếu class tồn tại. Tuy nhiên, **metadata type để Spring dự đoán bean trước khi tạo instance** chịu ảnh hưởng bởi return type được khai báo. Nếu nơi khác muốn inject theo kiểu `FileStorage` nhưng factory chỉ khai báo `Storage`, Spring có thể chưa nhìn thấy implementation type ở một số thời điểm.

Nguyên tắc: khai báo kiểu trả về **đủ cụ thể cho injection points cần thiết**, nhưng không buộc tầng nghiệp vụ phụ thuộc implementation nếu không cần. Với API dựa trên interface, `Storage` thường là hợp đồng đúng; với các cơ chế xử lý đặc thù dựa trên implementation, cần cân nhắc metadata kiểu.

### 4.4. @Bean không chỉ tạo đối tượng mới bằng new

Factory method có thể:

- Trả về đối tượng được xây bằng constructor Java.
- Gọi builder/factory của thư viện.
- Tạo adapter bao quanh tài nguyên bên ngoài.
- Đăng ký đối tượng của thư viện bên thứ ba mà bạn **không sở hữu source** để gắn `@Component`.

```java
@Bean
ExternalClient externalClient(ClientProperties properties) {
    return ExternalClient.builder()
            .endpoint(properties.endpoint())
            .build();
}
```

Đây là đoạn minh họa; `ExternalClient` và `ClientProperties` là các kiểu giả định của ứng dụng/thư viện. Lợi ích ở đây là có thể quản lý bean của class không chứa Spring stereotype và vẫn cấu hình collaborator, scope và lifecycle.

## 5. Dependency injection qua tham số phương thức @Bean

Đây là cách wiring đáng ưu tiên vì rõ ràng và hoạt động với cả full lẫn lite configuration.

```java
@Configuration(proxyBeanMethods = false)
class AppConfig {

    @Bean
    PaymentGateway paymentGateway() {
        return new InMemoryPaymentGateway();
    }

    @Bean
    CheckoutService checkoutService(PaymentGateway paymentGateway) {
        return new CheckoutService(paymentGateway);
    }
}
```

Spring giải quyết tham số `PaymentGateway paymentGateway` tương tự constructor injection rồi truyền bean phù hợp vào `checkoutService(...)`. Bạn **không cần gọi** `paymentGateway()` thủ công bên trong `checkoutService()`.

Lợi ích:

1. Dependency được khai báo **công khai ngay trên chữ ký** phương thức.
2. Container quyết định candidate theo kiểu, qualifier, primary và metadata cần thiết.
3. Cách viết không phụ thuộc vào việc `@Configuration` có bật proxy bean methods hay không.
4. Khi thiếu bean bắt buộc, Spring báo lỗi khi tạo consumer thay vì âm thầm tạo đối tượng ngoài container.
5. Dễ chia cấu hình thành nhiều class bằng `@Import` hoặc component scan.

### 5.1. Phụ thuộc tới bean ở class cấu hình khác

```java
@Configuration(proxyBeanMethods = false)
class RepositoryConfig {

    @Bean
    AccountRepository accountRepository() {
        return new InMemoryAccountRepository();
    }
}

@Configuration(proxyBeanMethods = false)
@Import(RepositoryConfig.class)
class ServiceConfig {

    @Bean
    AccountService accountService(AccountRepository repository) {
        return new AccountService(repository);
    }
}
```

Đây là đoạn minh họa cấu trúc; các interface/implementation do ứng dụng cung cấp. `@Import` nhập cấu hình; method `accountService` nhận dependency do Spring phân giải. Không cần để `ServiceConfig` tự khởi tạo `RepositoryConfig` bằng `new` rồi gọi factory method.

### 5.2. Phân giải nhiều bean

Nếu có hai `PaymentGateway`, method nhận một `PaymentGateway` không luôn xác định được ứng viên. Có thể dùng:

```java
@Bean
CheckoutService checkoutService(
        @Qualifier("safeGateway") PaymentGateway gateway) {
    return new CheckoutService(gateway);
}
```

Nhớ import `org.springframework.beans.factory.annotation.Qualifier`. Nếu thật sự muốn nhận toàn bộ plugin, dùng `List<Plugin>`, `Map<String, Plugin>` hoặc `ObjectProvider<Plugin>` ở injection point thích hợp. Đừng dùng collection chỉ để né lỗi nhập nhằng khi service thật sự cần một bean duy nhất.

### 5.3. Phụ thuộc tùy chọn

Một method `@Bean` cũng có thể khai báo `Optional<AuditSink>` khi audit là tùy chọn hợp lệ:

```java
@Bean
CheckoutService checkoutService(
        PaymentGateway gateway,
        java.util.Optional<AuditSink> auditSink) {
    return new CheckoutService(gateway, auditSink);
}
```

Đây là minh họa, constructor của `CheckoutService` trong dự án cần phù hợp. Phụ thuộc cốt lõi `PaymentGateway` vẫn bắt buộc; `AuditSink` được phép vắng mặt. Không nên chuyển mọi tham số thành `Optional` hoặc `ObjectProvider` chỉ để ứng dụng khởi động khi cấu hình thiếu.

## 6. Ví dụ Java 17 + Spring Framework chạy độc lập

Ví dụ dùng **Spring Framework thuần** (không cần Spring Boot), Java 17 và Maven. Nó cho thấy:

- `@Configuration(proxyBeanMethods = false)` là nguồn các bean definitions.
- `@Bean` tạo gateway và service.
- Method `checkoutService(PaymentGateway gateway)` nhận dependency do Spring tiêm.
- `@Bean(name = {"auditClient", "auditAlias"})` tạo tên chính và alias.
- `initMethod`/`destroyMethod` khiến Spring quản lý vòng đời của object.
- Tra cứu theo kiểu và tên trả cùng singleton trong phạm vi một context.

### 6.1. Cấu trúc

```text
java-config-demo/
├── pom.xml
└── src/main/java/demo/JavaConfigDemo.java
```

### 6.2. POM

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>java-config-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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

### 6.3. Chương trình

Tạo `src/main/java/demo/JavaConfigDemo.java`:

```java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class JavaConfigDemo {

    interface PaymentGateway {
        String charge(String orderId);
    }

    static final class DemoGateway implements PaymentGateway {
        @Override
        public String charge(String orderId) {
            return "receipt-" + orderId;
        }
    }

    static final class CheckoutService {
        private final PaymentGateway gateway;

        CheckoutService(PaymentGateway gateway) {
            this.gateway = gateway;
        }

        String checkout(String orderId) {
            return gateway.charge(orderId);
        }
    }

    static final class AuditClient {
        private boolean ready;

        void initialize() {
            ready = true;
            System.out.println("audit.init");
        }

        void shutdown() {
            ready = false;
            System.out.println("audit.shutdown");
        }

        boolean isReady() {
            return ready;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {

        @Bean
        PaymentGateway paymentGateway() {
            return new DemoGateway();
        }

        @Bean
        CheckoutService checkoutService(PaymentGateway paymentGateway) {
            return new CheckoutService(paymentGateway);
        }

        @Bean(
                name = {"auditClient", "auditAlias"},
                initMethod = "initialize",
                destroyMethod = "shutdown"
        )
        AuditClient auditClient() {
            return new AuditClient();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            CheckoutService first =
                    context.getBean(CheckoutService.class);
            CheckoutService second =
                    context.getBean("checkoutService", CheckoutService.class);

            System.out.println("receipt=" + first.checkout("42"));
            System.out.println("sameService=" + (first == second));
            System.out.println("alias=" +
                    (context.getBean("auditClient") ==
                     context.getBean("auditAlias")));
            System.out.println("auditReady=" +
                    context.getBean(AuditClient.class).isReady());
        }
    }
}
```

### 6.4. Chạy và quan sát

Từ thư mục chứa `pom.xml`, cài JDK 17+ và Maven rồi chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.JavaConfigDemo
```

Các dòng **do ứng dụng in ra** (không tính log Maven hoặc môi trường):

```text
audit.init
receipt=receipt-42
sameService=true
alias=true
auditReady=true
audit.shutdown
```

Tại sao output này đáng tin?

1. `AnnotationConfigApplicationContext(AppConfig.class)` tạo/refresh context với ba bean definitions từ ba method `@Bean`. Những singleton thông thường được khởi tạo trong giai đoạn startup; `auditClient` có callback `initialize()` nên in `audit.init` trước khi code trong `main` in receipt.
2. `CheckoutService` nhận cùng `PaymentGateway` mà container đã phân giải theo kiểu. Method factory không gọi thủ công `paymentGateway()`.
3. `checkoutService` mặc định là singleton: hai lời gọi `getBean` theo kiểu và theo tên tham chiếu cùng instance nên `sameService=true`.
4. `auditClient` và `auditAlias` là **hai tên cho cùng một bean**, không phải hai bean riêng, nên `alias=true`.
5. `initMethod = "initialize"` được gọi trước khi bean sẵn sàng cho consumer; `isReady()` trả `true`.
6. Khi thoát `try-with-resources`, context đóng và Spring gọi `shutdown()` trên singleton `AuditClient`, in `audit.shutdown`.

**Điều kiện cần nhớ:** Với singleton non-lazy, bean lifecycle của Spring diễn ra ở startup/close như trong ví dụ. Với prototype hoặc scoped bean, lifecycle destruction không có cùng bảo đảm như singleton; không suy rộng output này sang mọi scope. Chương trình cố ý giữ class đơn giản, không dùng logging framework.

### 6.5. Bài thử nhỏ

Thay:

```java
@Bean
CheckoutService checkoutService(PaymentGateway paymentGateway) {
    return new CheckoutService(paymentGateway);
}
```

bằng:

```java
@Bean("primaryCheckout")
CheckoutService checkoutService(PaymentGateway paymentGateway) {
    return new CheckoutService(paymentGateway);
}
```

Khi đó bean name chính đổi từ `checkoutService` sang `primaryCheckout`. Nếu `main` vẫn gọi `getBean("checkoutService", CheckoutService.class)`, nó sẽ không còn tìm được bean theo tên cũ, trừ khi có alias hoặc định nghĩa bean khác. Lấy theo kiểu `CheckoutService.class` vẫn có thể hoạt động nếu chỉ có một bean phù hợp.

## 7. Full `@Configuration` và cơ chế `proxyBeanMethods`

`@Configuration` mặc định dùng `proxyBeanMethods=true`: Spring tăng cường class cấu hình bằng CGLIB để các lời gọi **instance `@Bean` method** phù hợp trên cấu hình do container quản lý có thể đi qua `BeanFactory`. Với `proxyBeanMethods=false`, lời gọi Java trực tiếp giữ nguyên nghĩa Java. **Cả hai chế độ đều đăng ký bean definitions, hỗ trợ DI và lifecycle.**

### 7.1. Full configuration mặc định

```java
@Configuration
class FullConfig {
    @Bean Repository repository() { return new Repository(); }
    @Bean Service service() { return new Service(repository()); }
}
```

Đoạn này minh họa hai kiểu `Repository` và `Service` đã được định nghĩa. Khi container gọi `service()` trên **enhanced `FullConfig`**, lời gọi `repository()` có thể được chặn để lấy bean theo scope. Với singleton mặc định, service nhận cùng managed reference như `context.getBean(Repository.class)`. Tự `new FullConfig()` ngoài container không có interception.

### 7.2. Lite mode và hướng sửa an toàn

Nếu đổi annotation thành `@Configuration(proxyBeanMethods=false)` mà vẫn gọi `repository()` trong `service()`, Java chạy factory method trực tiếp và có thể tạo **một `Repository` bên ngoài managed bean**. Đây không phải bean `prototype` và cũng không có nghĩa `@Bean` mất hiệu lực.

Cách nên ưu tiên trong cả hai chế độ:

```java
@Configuration(proxyBeanMethods = false)
class ParameterConfig {
    @Bean Repository repository() { return new Repository(); }
    @Bean Service service(Repository repository) {
        return new Service(repository);
    }
}
```

Tham số `Repository` được Spring resolve từ BeanFactory theo type/qualifier/scope, nên không cần gọi một phương thức factory khác để lấy bean.

### 7.3. Bảng đối chiếu

| Điều kiện | Full (mặc định) | Lite (`proxyBeanMethods=false`) |
| --- | --- | --- |
| Container đăng ký và quản lý `@Bean` | Có | Có |
| Direct inter-bean instance call | Có thể được chặn qua enhanced config | Lời gọi Java thông thường |
| Dependency bằng tham số `@Bean` | Có | Có |
| Subclass CGLIB cho method interception | Có | Không cần |

Chỉ chuyển sang lite khi không còn inter-bean calls cần semantics của container; kiểm tra và thay chúng bằng dependency parameters nếu phù hợp.

### 7.4. Giới hạn của subclassing

Full configuration cần class có thể kế thừa và instance `@Bean` methods có thể override: class `final`, method `private`/`final` không phù hợp; `static @Bean` được hỗ trợ nhưng lời gọi static không có interception. Bài về full mode và bài giới hạn `final`/`private`/`static` sẽ phân tích sâu lý do.

## 8. @Bean có thể nằm trong @Component không?

Có. Spring cho phép phương thức `@Bean` trong class `@Component` thông thường. Nhưng đó là **lite @Bean mode**, không phải full configuration processing chỉ vì có bean method.

```java
@Component
class HelperFactory {

    @Bean
    Worker worker() {
        return new Worker();
    }
}
```

Đây là đoạn minh họa (cần `Worker` và `@Component` import). Nếu `HelperFactory` được Spring phát hiện, `worker()` có thể đóng góp bean definition. Tuy nhiên, gọi `worker()` trực tiếp từ phương thức khác trên `HelperFactory` **không** được Spring intercept giống full `@Configuration`.

Hãy phân biệt:

- **Component scanning:** tìm class `@Component` hoặc stereotype meta-present.
- **Cấu hình bean definitions:** nhận diện `@Bean` methods để đăng ký factory definitions.
- **Full configuration enhancement:** hành vi proxy method calls chỉ có khi cấu hình full đúng điều kiện.

Vì mục tiêu của một class là định nghĩa nhiều bean, `@Configuration` thường diễn đạt ý định rõ hơn `@Component`. Nếu không cần interception, `@Configuration(proxyBeanMethods=false)` là cách khai báo minh bạch.

## 9. Scope và thời điểm khởi tạo bean

`@Bean` mặc định tạo **singleton trong mỗi Spring IoC container**, nếu không khai báo scope khác.

```java
@Bean
CacheClient cacheClient() {
    return new CacheClient();
}
```

Một ApplicationContext lấy bean `cacheClient` nhiều lần thường nhận **cùng instance**, nhưng mỗi ApplicationContext độc lập có singleton riêng.

### Prototype scope

```java
@Bean
@Scope("prototype")
TaskWorker taskWorker() {
    return new TaskWorker();
}
```

Đoạn minh họa cần các class/import tương ứng. Spring trả một instance mới theo yêu cầu phân giải prototype bean. Tuy nhiên, nếu `TaskWorker` prototype được **inject trực tiếp một lần** vào constructor của một singleton, singleton đó thường giữ instance đã nhận; việc gọi phương thức trên singleton không tự làm Spring inject prototype mới.

Khi singleton cần **lấy một prototype mới theo từng tác vụ**, có thể dùng `ObjectProvider<TaskWorker>` hoặc factory chuyên dụng; không thay đổi scope hoặc lạm dụng lời gọi trực tiếp `taskWorker()` khi `proxyBeanMethods=false`.

### Lazy bean

```java
@Bean
@Lazy
LargeClient largeClient() {
    return new LargeClient();
}
```

`@Lazy` thay đổi thời điểm khởi tạo trong những điều kiện phù hợp; không có nghĩa bean bị loại khỏi container hay có thể thiếu. Với singleton non-lazy, Spring thường tạo trong quá trình context refresh. Với lazy bean, việc khởi tạo có thể bị trì hoãn đến khi có yêu cầu; nếu một singleton eager khác cần nó ngay, dependency đó vẫn có thể khiến bean được tạo sớm.

**Không nhầm `@Bean` với `@Scope`:** Factory method định nghĩa bean; scope định nghĩa chính sách quản lý số lượng/lifetime instance.

## 10. Vòng đời bean và @Bean(initMethod, destroyMethod)

Vì `@Bean` trả đối tượng được Spring quản lý, Spring có thể áp dụng:

- Dependency injection và callback theo lifecycle.
- BeanPostProcessor và các cơ chế proxy/phụ trợ được bật trong context.
- `@PostConstruct` và `@PreDestroy` nếu các annotation và hỗ trợ liên quan có mặt.
- `InitializingBean` / `DisposableBean`.
- `initMethod` / `destroyMethod` khai báo ngay trong `@Bean`.

Ví dụ:

```java
@Bean(initMethod = "connect", destroyMethod = "close")
ConnectionClient connectionClient() {
    return new ConnectionClient();
}
```

Đây là ví dụ minh họa cần `ConnectionClient.connect()` và `ConnectionClient.close()`. Spring gọi init callback theo lifecycle sau khi tạo và thiết lập bean; destroy callback diễn ra khi container đóng đối với singleton phù hợp.

### Khi bean có close/shutdown method

Spring có cơ chế **suy luận destruction callback** cho một số method như `close` hoặc `shutdown` trên đối tượng phù hợp. Nếu resource **không thuộc quyền sở hữu lifecycle** của context (ví dụ tài nguyên JNDI/managed resource do hạ tầng khác quản lý), có thể cần:

```java
@Bean(destroyMethod = "")
ExternalManagedResource externalResource() {
    return lookupExternalResource();
}
```

Đây là minh họa; `ExternalManagedResource` và `lookupExternalResource` phải được định nghĩa trong ứng dụng. Dùng `destroyMethod=""` để vô hiệu hóa inferred destroy callback khi Spring không nên tự đóng tài nguyên bên ngoài.

Không đóng một resource do Spring quản lý thủ công tại nhiều nơi rồi lại kỳ vọng destroy callback sẽ không gọi nữa, trừ khi implementation thật sự idempotent và lifecycle được thiết kế có chủ đích.

### Prototype destruction

Spring xử lý **khởi tạo** prototype, nhưng thường không quản lý việc **hủy prototype** giống singleton sau khi trả object cho client. Nếu bean prototype giữ connection/file/resource, phía sử dụng phải có chính sách cleanup phù hợp. Không lấy ví dụ `AuditClient` singleton ở mục 6 làm bảo đảm rằng mọi prototype sẽ tự gọi `destroyMethod` khi context đóng.

## 11. Nạp và kết hợp Java configuration

Ở ứng dụng nhiều module, có thể chia cấu hình:

```java
@Configuration(proxyBeanMethods = false)
class AdapterConfig {

    @Bean
    Adapter adapter() {
        return new Adapter();
    }
}

@Configuration(proxyBeanMethods = false)
@Import(AdapterConfig.class)
class BusinessConfig {

    @Bean
    BusinessService businessService(Adapter adapter) {
        return new BusinessService(adapter);
    }
}
```

Đây là các class minh họa, cần import `Configuration`, `Bean`, `Import` và các class ứng dụng. Đăng ký `BusinessConfig` vào context sẽ kéo theo `AdapterConfig`, và `BusinessService` nhận `Adapter` do Spring phân giải. Không cần gọi trực tiếp `new AdapterConfig().adapter()`.

Nếu muốn kết hợp với component scanning:

```java
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackages = "com.example.application")
class ApplicationConfig {
}
```

Các class mang stereotype trong `com.example.application` và package con có thể được quét. Đồng thời, các method `@Bean` trong `ApplicationConfig` cũng đăng ký các bean factory definitions. Hai cách **bổ sung cho nhau**, không nhất thiết phải chọn chỉ một.

### Đăng ký cấu hình qua context

Có thể dùng:

```java
var context = new AnnotationConfigApplicationContext();
context.register(BusinessConfig.class);
context.refresh();
try {
    // lấy bean và chạy tác vụ
} finally {
    context.close();
}
```

Đây là đoạn minh họa, cần `BusinessConfig` hợp lệ. Phải gọi `refresh()` sau khi `register()` khi dùng constructor rỗng để hoàn tất khởi tạo context. Khi dùng constructor nhận class cấu hình như ví dụ mục 6, Spring thực hiện refresh trong constructor.

## 12. @Configuration và @Bean so với @Component / @Service

| Tiêu chí | `@Component` / `@Service` | `@Configuration` + `@Bean` |
| --- | --- | --- |
| Nơi gắn annotation chính | Trên class ứng viên | `@Configuration` trên class cấu hình, `@Bean` trên factory method |
| Bean được tạo từ đâu | Scanner phát hiện class stereotype và container quản lý quá trình khởi tạo | Container gọi factory method được khai báo |
| Phù hợp | Class ứng dụng tự kiểm soát source, dependency qua constructor | Third-party client, adapter cần builder/cấu hình phức tạp, nhóm wiring |
| Cần component scan? | Thường có, hoặc được đăng ký qua cơ chế khác | Không bắt buộc nếu config được đăng ký trực tiếp |
| Đặt tên bean | Thường dựa class name hoặc stereotype value | Thường tên factory method, có thể dùng `@Bean(name=...)` |
| Xử lý vòng đời | Bean managed bình thường | Bean managed bình thường |
| Cần proxy method calls? | Không phải mục tiêu của stereotype | Chỉ khi `@Configuration` full và có nhu cầu gọi bean method khác |

Không phải cứ có `@Bean` thì Spring tạo ra object "cao cấp" hơn `@Component`. **Cùng vào container thì cả hai đều là bean** và chịu các quy tắc scope/lifecycle phù hợp. Khác biệt chủ yếu là **cách khai báo factory và mức độ kiểm soát cách khởi tạo**.

### Khi nên dùng @Bean?

- Cần đăng ký bean của thư viện bên thứ ba, không thể sửa source để gắn `@Component`.
- Cần truyền config values vào builder/constructor có nhiều tùy chọn.
- Muốn cung cấp nhiều bean cùng class nhưng cấu hình khác nhau.
- Muốn định nghĩa rõ alias, scope, init/destroy callback tại factory boundary.
- Muốn module hóa wiring và thay implementation theo môi trường.

### Khi nên dùng @Component/@Service?

- Class thuộc ứng dụng, có constructor dependency rõ ràng.
- Không cần logic factory phức tạp.
- Component scanning đã được thiết lập có chủ đích.
- Muốn cấu trúc ít boilerplate, tránh liệt kê hàng trăm factory methods đơn giản.

Tránh vừa gắn `@Component` lên một implementation vừa khai báo `@Bean` tạo cùng implementation một cách vô thức. Điều đó có thể tạo **hai bean khác nhau cùng kiểu**, dẫn tới nhập nhằng khi tiêm một dependency đơn lẻ. Nếu thực sự cần nhiều instance cấu hình khác nhau, đặt tên/qualifier và test số ứng viên rõ ràng.

## 13. Những hiểu lầm phổ biến

### "Có @Configuration thì mọi method bên trong tự trở thành bean"

**Sai.** Chỉ những method được Spring nhận diện là `@Bean` (hoặc các cơ chế đăng ký khác) đóng góp bean definitions. Một helper method bình thường không tự trở thành factory bean.

```java
@Configuration
class Config {
    @Bean
    Client client() {
        return createClient();
    }

    private Client createClient() {
        return new Client();
    }
}
```

Đây là minh họa, `Client` là class ứng dụng. `createClient()` chỉ là helper, không đăng ký thêm bean riêng; nó được gọi trong `client()` để tạo bean `client`.

### "Cứ gọi appConfig.beanMethod() là lấy bean Spring"

**Sai nếu không xét ngữ cảnh.** Với class cấu hình tạo bằng `new` bên ngoài context, đây là lời gọi Java bình thường. Trong full `@Configuration` object đã được Spring enhance, inter-bean calls có interception. Trong lite mode, lời gọi trực tiếp vẫn bình thường. Để chắc chắn lấy bean được quản lý, hãy tiêm dependency qua method parameter hoặc tra cứu theo context trong tầng wiring/thử nghiệm khi cần.

### "Đổi @Configuration(proxyBeanMethods=false) chỉ là tối ưu, không đổi hành vi"

**Không luôn đúng.** Nếu cấu hình cũ gọi trực tiếp một phương thức `@Bean` từ phương thức `@Bean` khác, khi tắt proxy, lời gọi không được Spring intercept; có thể tạo thêm object ngoài bean identity/scope đúng dự kiến. Nên thay bằng parameter-based dependency injection trước khi tắt proxy.

### "@Bean luôn tạo singleton mới mỗi lần được gọi"

**Sai.** Singleton/prototype là **scope của bean resolution trong container**. Một factory method có thể được gọi một lần khi container tạo singleton; cũng có thể được gọi mỗi lần Spring phân giải prototype. Nhưng một lời gọi trực tiếp qua Java trên lite config là chuyện khác và không bảo đảm cùng instance với bean.

### "Có @Bean thì không cần đưa config vào context"

**Sai.** Class cấu hình phải được đăng ký/import/scanned đúng cơ chế Spring. Một file Java có annotation nhưng không nằm trong ApplicationContext không tự tạo bean definitions.

### "Bean của thư viện bất kỳ đều nên gắn @Component bằng cách chỉnh source"

**Không cần.** `@Bean` cho phép tạo và quản lý instance thư viện mà không yêu cầu chỉnh sửa class đó. Đây là tình huống dùng Java config rất phù hợp.

### "@Bean(name = {a, b}) tạo hai singleton"

**Sai.** Mảng tên của một bean definition chỉ ra tên chính và alias, không phải hai bean instance riêng. Nếu cần hai instance, viết hai factory methods hoặc đăng ký hai bean definitions riêng, kèm qualifier nếu cần.

### "@Bean được dùng như endpoint nghiệp vụ"

**Sai.** Factory method dùng để **định nghĩa/tạo bean**, không nên được gọi mỗi lần cần xử lý một request thanh toán hoặc thực thi job. Nghiệp vụ thuộc methods của bean đã được tạo, không thuộc phương thức `@Bean`.

## 14. Vấn đề kỹ thuật nâng cao cần nhận biết

### 14.1. @Bean và BeanFactoryPostProcessor

Một số bean thuộc hạ tầng như `BeanFactoryPostProcessor` hoặc `BeanPostProcessor` tham gia vào giai đoạn **rất sớm** của container. Spring tài liệu khuyên các phương thức `@Bean` cho một số post-processor như `BeanFactoryPostProcessor` thường nên là `static` để tránh phải tạo instance class cấu hình quá sớm, ảnh hưởng injection/callback trên chính class cấu hình.

```java
@Configuration
class InfrastructureConfig {

    @Bean
    static MyBeanFactoryPostProcessor myPostProcessor() {
        return new MyBeanFactoryPostProcessor();
    }
}
```

Đây là minh họa; `MyBeanFactoryPostProcessor` là implementation cần định nghĩa riêng. Không chuyển mọi `@Bean` thành `static` một cách máy móc: cần dựa vào vai trò bean và các yêu cầu lifecycle.

### 14.2. @Bean method có tham số phụ thuộc vào scope

Nếu một factory method singleton nhận một dependency prototype qua tham số, prototype có thể được tạo **khi singleton được xây**. Sau đó singleton giữ reference đó, không tự lấy prototype mới cho mỗi method invocation. Muốn lookup theo lượt, nên dùng provider/factory chuyên dụng và hiểu scope.

### 14.3. Chú ý vòng phụ thuộc và @PostConstruct của config

Class cấu hình cũng là bean đặc biệt và được xử lý sớm. Không nên gọi những `@Bean` methods trong `@PostConstruct` của chính configuration class để "ép" tạo các bean khác. Điều này có thể gây early initialization hoặc circular reference phức tạp. Đưa dependency vào method parameters và để Spring quản lý trình tự tạo bean.

### 14.4. Return type và bean prediction

Spring phải suy ra nhiều thông tin về ứng viên trước khi tạo bean. Nếu một method trả interface rộng, Spring có thể không biết mọi interface/concrete type thực của object trong giai đoạn bean type matching. Với các injection points cần implementation-specific type, hãy khai báo return type đủ cụ thể hoặc sửa injection point để phụ thuộc interface ổn định.

### 14.5. Trùng bean name và override

Hai phương thức hoặc hai configuration classes đăng ký cùng tên bean có thể dẫn tới lỗi, hoặc override một definition tùy cấu hình container và chính sách framework. **Không giả định** Spring sẽ luôn chọn method khai báo sau. Chọn tên bean rõ ràng, hạn chế đăng ký trùng và kiểm thử kết quả trong đúng kiểu ApplicationContext/Boot configuration của ứng dụng.

## 15. Chẩn đoán lỗi theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` khi lấy bean | Class cấu hình chưa được đăng ký/import, factory method không có `@Bean`, qualifier/type không khớp | Kiểm tra metadata, phạm vi config và tên/kiểu bean |
| `UnsatisfiedDependencyException` | Tham số factory method hoặc constructor thiếu bean bắt buộc | Đọc dependency nào thiếu rồi đăng ký/định danh đúng implementation |
| `NoUniqueBeanDefinitionException` | Nhiều bean cùng kiểu, không chọn được duy nhất | Dùng `@Qualifier`, `@Primary` hoặc thiết kế collection đúng nhu cầu |
| `BeanCreationException` trong method factory | Constructor/builder của thư viện ném lỗi; config không hợp lệ | Xem root cause trong stack trace, sửa factory/config values |
| Có hai instance dù định nghĩa singleton | Gọi trực tiếp phương thức `@Bean` trong lite config; tự gọi `new AppConfig()` | Tiêm bean qua factory method parameters; để Spring quản lý |
| Lỗi không enhance được `@Configuration` | Full config hoặc bean methods bị `final`/`private` không phù hợp | Chuyển sang mode lite với wiring đúng hoặc bỏ final/private cần interception |
| Bean name khác dự kiến | Dùng `@Bean(name=...)` hoặc custom naming strategy | Kiểm tra tên khai báo và tra cứu theo type khi phù hợp |
| `destroyMethod` không chạy với prototype | Prototype không được container hủy tự động như singleton | Thiết kế cleanup do consumer sở hữu |
| `initMethod` không chạy như mong đợi | Object được tạo bằng `new` ngoài context hoặc callback chỉ áp dụng instance khác | Xác nhận bạn dùng bean được Spring quản lý |
| Bean được tạo sớm dù có provider | Non-lazy singleton đã được pre-instantiated | Kiểm tra bean scope và lazy configuration |
| Thêm `@Component` và `@Bean` cho cùng class gây ambiguous | Hai bean definitions trùng kiểu | Chọn một cách đăng ký hoặc qualifier rõ |
| Gọi `register()` nhưng vẫn chưa lấy được bean | Context tạo qua constructor rỗng chưa `refresh()` | Gọi `refresh()` rồi tra cứu; nhớ đóng context |

Quy trình debug:

1. Đảm bảo class cấu hình có trong ApplicationContext (truyền class vào constructor, `register`, `@Import` hoặc scan).
2. Đảm bảo factory method mang đúng `@Bean` và return type hợp lệ.
3. Xem bean name mặc định có đổi do `name`/`value` không.
4. Xem mỗi parameter của `@Bean` có bao nhiêu ứng viên và qualifier nào áp dụng.
5. Kiểm tra scope/lazy/lifecycle; phân biệt object do container tạo với object được gọi bằng `new` trực tiếp.
6. Nếu có gọi giữa `@Bean` methods, kiểm tra `proxyBeanMethods`.
7. Đọc exception nguyên nhân gốc, không chỉ exception wrapper ngoài cùng.

## 16. Bài tập và đáp án định hướng

### Bài 1 — Vai trò hai annotation

`@Configuration` và `@Bean` khác nhau ở đâu?

**Đáp án:** `@Configuration` đánh dấu class cấu hình làm nguồn bean definitions; `@Bean` đánh dấu factory method đóng góp một bean definition và trả object container quản lý. Không phải mọi method của class `@Configuration` đều tự biến thành bean.

### Bài 2 — Lấy bean bằng tên

Với `@Bean CheckoutService checkoutService(...)`, tên bean mặc định là gì? Nếu dùng `@Bean(name={"checkoutA","checkoutAlias"})` thì có mấy bean được định nghĩa?

**Đáp án:** Mặc định tên là `checkoutService`. Mảng tên tạo **một bean definition** với tên chính `checkoutA` và alias `checkoutAlias`.

### Bài 3 — Full và lite

Cho đoạn sau:

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    Repository repository() { return new Repository(); }

    @Bean
    Service service() { return new Service(repository()); }
}
```

Nếu `service()` gọi `repository()` trực tiếp, `Service` có chắc nhận đúng singleton bean `repository` mà container đang quản lý không?

**Đáp án:** Không. Trong lite mode, `repository()` là lời gọi Java bình thường, có thể tạo instance riêng. Sửa thành `Service service(Repository repository)` để Spring inject dependency.

### Bài 4 — Bean của thư viện

Bạn cần đăng ký `HttpClient` từ JDK hoặc một client của thư viện thứ ba nhưng không thể sửa source class đó. Nên chọn component scan trực tiếp trên client class hay `@Bean`?

**Đáp án:** `@Bean` phù hợp. Factory method có thể xây client bằng builder/constructor và đưa instance vào container. Nếu client giữ tài nguyên, cần cân nhắc lifecycle/ownership.

### Bài 5 — Hai implementation

Có hai bean `MailSender` cùng kiểu. Một service phải dùng chính xác sender cho giao dịch. Nếu parameter `MailSender mailSender` bị nhập nhằng, nên làm gì?

**Đáp án:** Dùng `@Qualifier` tại parameter hoặc `@Primary` khi có một ứng viên mặc định đúng. Không tự chọn theo thứ tự đăng ký và không thay tất cả bằng collection nếu nghiệp vụ cần một sender cụ thể.

### Bài 6 — Vòng đời

Một `@Bean(initMethod="start", destroyMethod="stop")` là singleton. Khi nào callback có thể chạy?

**Đáp án:** `start` chạy theo lifecycle initialization khi bean được tạo/xử lý; `stop` thường chạy khi singleton được container hủy hoặc context đóng. Với prototype, Spring không tự đảm bảo destroy callback khi context đóng như singleton.

### Bài 7 — Viết cấu hình rõ ràng

Cho `Repository` và `ReportService` có constructor nhận `Repository`. Hãy viết hai `@Bean` trong một `@Configuration(proxyBeanMethods=false)` sao cho `ReportService` dùng bean `Repository` do Spring quản lý.

**Đáp án định hướng:**

```java
@Configuration(proxyBeanMethods = false)
class ReportConfig {
    @Bean
    Repository repository() {
        return new Repository();
    }

    @Bean
    ReportService reportService(Repository repository) {
        return new ReportService(repository);
    }
}
```

Đây là mẫu cấu hình; cần thêm các class `Repository` và `ReportService` tương ứng. Điểm chính là `Repository` được đưa vào **tham số factory method**, không gọi `repository()` trực tiếp.

## 17. Checklist áp dụng trong dự án

Trước khi kết luận Java configuration hoạt động đúng, kiểm tra:

- Đã đưa `@Configuration` vào đúng ApplicationContext.
- Mỗi bean cần đăng ký bằng factory method đều có `@Bean`.
- `@Bean` method trả kiểu hữu ích cho các injection points.
- Bean names/aliases không vô tình xung đột.
- Dependency bắt buộc được khai báo bằng constructor hoặc parameter method rõ ràng.
- Nếu tắt `proxyBeanMethods`, không dựa vào inter-bean direct calls để lấy container-managed instance.
- Scope/lazy semantics phù hợp cách sử dụng singleton, prototype hoặc tài nguyên ngoài.
- Init/destroy callback đúng với chủ sở hữu lifecycle của bean.
- Không đăng ký trùng cùng implementation một cách vô tình giữa component scanning và `@Bean`.
- Có smoke test bằng `AnnotationConfigApplicationContext` hoặc integration test xác nhận bean có mặt, đúng identity và lifecycle.

## Tổng kết

**`@Configuration` mô tả nơi chứa cấu hình; `@Bean` mô tả phương thức tạo bean.** Spring dùng chúng để xây bean definitions và quản lý dependency, scope, lifecycle, callback cùng các cơ chế container khác. Khi xây Java config mới, **tiêm dependency qua tham số phương thức `@Bean`** thường rõ ràng và an toàn với cả full lẫn lite mode.

Chỉ dựa vào lời gọi giữa `@Bean` methods nếu bạn hiểu full `@Configuration` và `proxyBeanMethods=true`. Với `proxyBeanMethods=false`, lời gọi đó là Java bình thường, có thể tạo object ngoài managed singleton identity. Khi muốn biểu diễn wiring mà không sửa source của thư viện, `@Bean` là công cụ tự nhiên; khi class ứng dụng chỉ cần được scanner phát hiện, `@Component`/`@Service` có thể đơn giản hơn.

## Tài liệu Spring chính thức

- [Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java.html) — tổng quan Java configuration.
- [Basic Concepts: @Bean and @Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html) — định nghĩa hai annotation và full/lite mode.
- [Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html) — bean name, method parameters, lifecycle và return type.
- [Using the @Configuration Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html) — inter-bean dependencies và enhancement.
- [Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html) — `@Import` và wiring giữa các configuration classes.
- [Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html) — singleton, prototype và scope semantics.
