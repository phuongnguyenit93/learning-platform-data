# Tiêm ApplicationEventPublisher vào bean

## 1. Vì sao cần tiêm ApplicationEventPublisher?

`ApplicationEventPublisher` là interface Spring cung cấp để một thành phần phát thông báo về sự kiện đã xảy ra. Một service có thể gọi `publishEvent(event)` mà không cần biết listener nào sẽ nhận hoặc cách listener được triển khai.

Trong ứng dụng Spring, `ApplicationContext` triển khai `ApplicationEventPublisher`. Vì vậy, Spring có thể cung cấp publisher của context hiện tại cho bean thông qua dependency injection. Bạn chỉ cần khai báo `ApplicationEventPublisher` là dependency của bean; không cần tự tìm `ApplicationContext` toàn cục hoặc gọi listener trực tiếp.

Ví dụ, `RegistrationService` cần phát `UserRegistered` sau khi tạo tài khoản. Service nhận publisher qua constructor rồi gọi `publisher.publishEvent(new UserRegistered(...))`. Các listener đã đăng ký trong context sẽ được Spring thông báo theo cơ chế Application Events.

## 2. Tiêm qua constructor

Constructor injection là cách nên ưu tiên khi bean cần publisher trong suốt vòng đời hoạt động:

```java
public class RegistrationService {
    private final ApplicationEventPublisher publisher;

    public RegistrationService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void register(String userId) {
        publisher.publishEvent(new UserRegistered(userId));
    }
}
```

Dependency được khai báo rõ trong constructor và lưu ở field `final`. Khi tạo `RegistrationService`, Spring phải cung cấp một đối tượng phù hợp với kiểu `ApplicationEventPublisher`. Nếu class chỉ có một constructor, Spring tự sử dụng constructor đó để tiêm dependency; không cần thêm `@Autowired` trong trường hợp thông thường.

Constructor injection giúp bean không thể được tạo ở trạng thái thiếu publisher. Nó cũng giúp unit test dễ dàng truyền một publisher giả hoặc publisher kiểm thử thay thế khi cần.

## 3. Khai báo bean và để Spring cung cấp publisher

Với cấu hình Java, có thể nhận `ApplicationEventPublisher` làm tham số của phương thức `@Bean`, rồi truyền nó vào constructor của service:

```java
@Configuration
public class AppConfig {

    @Bean
    RegistrationService registrationService(ApplicationEventPublisher publisher) {
        return new RegistrationService(publisher);
    }

    @Bean
    UserRegisteredListener userRegisteredListener() {
        return new UserRegisteredListener();
    }
}
```

Spring phân giải tham số `publisher` theo kiểu dependency và cung cấp publisher gắn với `ApplicationContext` đang tạo bean. `RegistrationService` không cần biết implementation cụ thể của context.

Trong ứng dụng dùng component scanning, cách khai báo tương đương là đánh dấu service bằng `@Service` và khai báo constructor:

```java
@Service
public class RegistrationService {
    private final ApplicationEventPublisher publisher;

    public RegistrationService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }
}
```

Listener cũng phải là bean do Spring quản lý, ví dụ dùng `@Component` và `@EventListener`. Chỉ tiêm publisher vào service chưa tự tạo listener; hai phía phải được đăng ký trong `ApplicationContext` phù hợp.

## 4. Ví dụ hoàn chỉnh chạy với Java 17

Ví dụ sau dùng Spring Context thuần để thấy rõ publisher được Spring tiêm vào service. Khi service phát event, listener nhận payload và in thông báo.

### Cấu trúc thư mục

```text
publisher-injection/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── App.java
```

### pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>publisher-injection</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>6.2.0</spring-framework.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring-framework.version}</version>
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
                <configuration>
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### src/main/java/demo/App.java

```java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class App {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.getBean(RegistrationService.class).register("user-46");
        }
    }

    @Configuration
    static class AppConfig {

        @Bean
        RegistrationService registrationService(ApplicationEventPublisher publisher) {
            return new RegistrationService(publisher);
        }

        @Bean
        UserRegisteredListener userRegisteredListener() {
            return new UserRegisteredListener();
        }
    }

    static class RegistrationService {
        private final ApplicationEventPublisher publisher;

        RegistrationService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void register(String userId) {
            publisher.publishEvent(new UserRegistered(userId));
            System.out.println("Registration completed for user=" + userId);
        }
    }

    static class UserRegisteredListener {

        @EventListener
        public void welcome(UserRegistered event) {
            System.out.println("Welcome event received for user=" + event.userId());
        }
    }

    public record UserRegistered(String userId) {
    }
}
```

### Chạy chương trình

Đứng tại thư mục chứa `pom.xml` và chạy:

```bash
mvn -q compile exec:java
```

Output:

```text
Welcome event received for user=user-46
Registration completed for user=user-46
```

Listener in thông báo trước dòng `Registration completed` vì cấu hình mặc định xử lý event đồng bộ. Khi `publishEvent` trả về, listener đồng bộ đã hoàn tất.

Trong ví dụ:

- `ApplicationEventPublisher` được Spring truyền vào phương thức `@Bean` `registrationService`.
- Phương thức factory truyền publisher vào constructor của `RegistrationService`.
- Service chỉ phụ thuộc vào interface publisher và phát một `UserRegistered` payload.
- `UserRegisteredListener` là bean trong cùng context và nhận payload bằng `@EventListener`.

## 5. Tiêm publisher trong Spring Boot

Trong ứng dụng Spring Boot, cách dùng vẫn giống hệt. Bạn có thể dùng constructor của `@Service`:

```java
@Service
public class AccountService {
    private final ApplicationEventPublisher publisher;

    public AccountService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void openAccount(String accountId) {
        // Lưu tài khoản bằng repository trước hoặc theo luồng nghiệp vụ phù hợp.
        publisher.publishEvent(new AccountOpened(accountId));
    }
}
```

Spring Boot tạo và quản lý `ApplicationContext`, nên publisher được phân giải tự động. Không cần tự khai báo một bean `ApplicationEventPublisher` riêng trong cấu hình thông thường.

## 6. Các cách tiêm khác và lựa chọn phù hợp

Spring cũng hỗ trợ field injection và setter injection, nhưng constructor injection thường rõ ràng hơn:

```java
// Field injection
@Autowired
private ApplicationEventPublisher publisher;

// Setter injection
@Autowired
public void setPublisher(ApplicationEventPublisher publisher) {
    this.publisher = publisher;
}
```

Field injection che giấu dependency trong thân class và khó tạo instance trong unit test thuần. Setter injection phù hợp hơn khi dependency thực sự là tùy chọn hoặc cần thay đổi sau khi tạo bean. Publisher thường là dependency bắt buộc của service phát event, vì vậy constructor injection là lựa chọn dễ kiểm soát.

Không nên dùng `ApplicationContext` chỉ để gọi `publishEvent` nếu bean chỉ cần chức năng phát event. Khai báo interface `ApplicationEventPublisher` giúp thể hiện đúng nhu cầu và giảm phụ thuộc vào API rộng hơn của context.

Spring còn có `ApplicationEventPublisherAware` cho bean muốn nhận publisher thông qua callback của container. Cơ chế này hữu ích trong một số thành phần hạ tầng cần callback aware, nhưng service nghiệp vụ thông thường nên dùng constructor injection để dependency xuất hiện rõ ngay tại điểm tạo bean.

## 7. Phạm vi và thời điểm xử lý

Publisher được tiêm gắn với context quản lý bean. Event được gửi qua cơ chế Application Events của Spring trong phạm vi ứng dụng/context và được chuyển tới listener tương thích. Khi có quan hệ parent/child context, cần hiểu cách event được chuyển giữa các context; đừng mặc định mọi context độc lập đều chia sẻ toàn bộ listener.

Việc tiêm `ApplicationEventPublisher` không làm event tự động bất đồng bộ, không tạo hàng đợi bền vững và không bảo đảm listener chạy sau khi transaction commit. Mặc định listener đồng bộ chạy trên luồng phát event. Nếu muốn listener chạy bất đồng bộ, có thể dùng `@Async` cùng `@EnableAsync` và cấu hình executor.

Nếu listener chỉ nên chạy sau khi transaction commit, hãy tìm hiểu `@TransactionalEventListener` và các phase như `AFTER_COMMIT`. Điều kiện này liên quan đến transaction lifecycle; bản thân việc inject publisher không thay đổi thời điểm commit.

## 8. Lỗi thường gặp

| Hiện tượng | Nguyên nhân và cách xử lý |
|---|---|
| Spring không inject được publisher | Bean được tạo ngoài container hoặc context chưa khởi tạo đúng. Hãy để Spring tạo bean bằng component scanning hoặc `@Bean`. |
| Constructor báo thiếu dependency | Kiểm tra cấu hình tạo bean và kiểu tham số. Với bean do Spring quản lý, `ApplicationEventPublisher` được cung cấp bởi context. |
| Tự tạo `new RegistrationService(...)` rồi mong có dependency | Object tạo bằng `new` ngoài container không được Spring tự tiêm. Lấy bean từ context hoặc để container quản lý toàn bộ vòng đời. |
| Listener không nhận event | Kiểm tra listener là bean, có `@EventListener`, nằm trong context phù hợp và nhận kiểu payload tương thích. |
| Nghĩ publisher mặc định chạy nền | Event mặc định được xử lý đồng bộ. Dùng `@Async` nếu cần chạy trên executor và đã chuẩn bị xử lý lỗi. |
| Inject cả `ApplicationContext` chỉ để phát event | Dùng `ApplicationEventPublisher` để phụ thuộc đúng interface cần thiết. |

## 9. Ghi nhớ

- `ApplicationContext` cung cấp chức năng `ApplicationEventPublisher` cho các bean trong context.
- Khai báo `ApplicationEventPublisher` trong constructor hoặc tham số phương thức `@Bean` để Spring tiêm dependency.
- Service phát event bằng `publisher.publishEvent(event)` và không cần gọi trực tiếp listener.
- Listener phải là bean Spring và đăng ký xử lý bằng `@EventListener` hoặc cơ chế listener phù hợp.
- Constructor injection giúp dependency rõ ràng, bắt buộc và dễ kiểm thử.
- Tiêm publisher không tự tạo xử lý bất đồng bộ, message broker hay transaction-after-commit.