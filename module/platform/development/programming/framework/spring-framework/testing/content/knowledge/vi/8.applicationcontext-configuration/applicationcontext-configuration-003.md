# Nạp Groovy script trong các dự án dùng cấu hình Groovy

Spring Framework cho phép khai báo bean bằng Groovy script thông qua một DSL dành cho bean definition. Cách cấu hình này có thể được nạp vào `ApplicationContext` giống như cấu hình XML hoặc Java configuration. Trong một dự án dùng Groovy, ta có thể đặt các bean definition trong file `.groovy`, nạp file đó bằng `GenericGroovyApplicationContext` hoặc `GroovyBeanDefinitionReader`, rồi refresh context để Spring tạo và quản lý các bean.

Nạp Groovy script là một phần của quá trình xây dựng `ApplicationContext`: script được đọc và chuyển thành các `BeanDefinition`, các định nghĩa được đăng ký vào bean factory, sau đó context được refresh để hoàn tất quá trình khởi tạo. Hiểu rõ các bước này giúp tránh lỗi không tìm thấy bean, thiếu Groovy runtime, sai resource path hoặc gọi `refresh()` không đúng thời điểm.

## 1. Groovy bean-definition DSL trong Spring

Spring hỗ trợ một DSL viết bằng Groovy để khai báo bean. Thay vì mô tả bean bằng XML hoặc annotation, script dùng một khối `beans { ... }` để đăng ký tên bean, class, thuộc tính và quan hệ phụ thuộc.

Ví dụ file `src/main/resources/context/services.groovy`:

```groovy
import com.example.account.AccountRepository
import com.example.account.AccountRepositoryImpl
import com.example.account.AccountService

beans {
    accountRepository(AccountRepositoryImpl)

    accountService(AccountService) {
        repository = ref('accountRepository')
    }
}
```

Trong ví dụ:

- `accountRepository` là tên bean được đăng ký trong container.
- `AccountRepositoryImpl` là class được Spring khởi tạo cho bean đó.
- `accountService` là một bean khác.
- `repository = ref('accountRepository')` tạo tham chiếu đến bean có tên `accountRepository` và gán dependency đó cho thuộc tính `repository` của `AccountService`.

Các class Java minh họa có thể được viết như sau:

```java
public interface AccountRepository {
    String findDisplayName(long id);
}

public class AccountRepositoryImpl implements AccountRepository {
    @Override
    public String findDisplayName(long id) {
        return "Account-" + id;
    }
}

public class AccountService {

    private AccountRepository repository;

    public void setRepository(AccountRepository repository) {
        this.repository = repository;
    }

    public String displayName(long id) {
        return repository.findDisplayName(id);
    }
}
```

Groovy DSL sử dụng property syntax để gọi setter tương ứng. Trong ví dụ trên, `repository = ref(...)` tương đương với việc cấu hình property `repository` của bean definition; khi bean được khởi tạo, Spring gọi setter thích hợp.

### 1.1. Khai báo nhiều bean và tham chiếu giữa chúng

Một script có thể chứa nhiều bean definition. Thứ tự khai báo không nhất thiết phải trùng với thứ tự phụ thuộc vì Spring phân giải các bean reference khi khởi tạo bean.

```groovy
beans {
    notificationGateway(SmtpNotificationGateway) {
        host = 'localhost'
        port = 2525
    }

    registrationService(RegistrationService) {
        notificationGateway = ref('notificationGateway')
    }
}
```

`ref('notificationGateway')` biểu diễn dependency đến bean khác trong cùng bean factory. Đây là bean reference, không phải chuỗi tên được gán trực tiếp vào thuộc tính. Nếu gán chuỗi `'notificationGateway'`, Spring sẽ coi đó là giá trị String và không tự hiểu đó là bean cần inject.

Groovy DSL cũng hỗ trợ các khả năng định nghĩa bean như cấu hình scope, lazy initialization, constructor arguments, inner bean và các metadata khác. Khi sử dụng các tính năng nâng cao, nên giữ cấu hình dễ đọc và kiểm tra đúng kiểu dependency mà bean cần nhận.

### 1.2. Bean definition khác với việc tạo object

Khi script được đọc, Spring chủ yếu đăng ký metadata dưới dạng `BeanDefinition`. Việc đọc script không đồng nghĩa tất cả singleton đã được tạo ngay lập tức.

Quy trình cơ bản:

```text
Groovy script (.groovy)
        |
        v
GroovyBeanDefinitionReader
        |
        v
Đăng ký BeanDefinition vào BeanDefinitionRegistry
        |
        v
ApplicationContext.refresh()
        |
        v
Khởi tạo bean và xử lý lifecycle
        |
        v
ApplicationContext sẵn sàng phục vụ getBean()
```

Với singleton không lazy, Spring thường tạo bean trong quá trình refresh. Bean lazy hoặc bean có scope khác có thể chỉ được tạo khi được yêu cầu. Nếu một dependency không thể được phân giải, lỗi thường xuất hiện trong quá trình refresh hoặc khi bean tương ứng được khởi tạo.

## 2. Nạp script bằng GenericGroovyApplicationContext

`GenericGroovyApplicationContext` là một implementation của `ApplicationContext` dành cho việc nạp bean definition từ Groovy script. Đây là cách trực tiếp khi dự án muốn dùng Groovy làm nguồn cấu hình chính.

Giả sử file có cấu trúc:

```text
src/main/resources/
└── context/
    └── services.groovy
```

Có thể nạp file bằng Java:

```java
import org.springframework.context.support.GenericGroovyApplicationContext;

public class Application {

    public static void main(String[] args) {
        try (var context = new GenericGroovyApplicationContext()) {
            context.load("classpath:context/services.groovy");
            context.refresh();

            AccountService service = context.getBean(AccountService.class);
            System.out.println(service.displayName(42L));
        }
    }
}
```

Các bước có ý nghĩa riêng:

1. Tạo `GenericGroovyApplicationContext` bằng constructor không tham số.
2. Gọi `load(...)` để đọc một hoặc nhiều Groovy resource và đăng ký bean definition.
3. Gọi `refresh()` để hoàn tất việc tạo và cấu hình context.
4. Gọi `getBean(...)` để lấy bean đã được Spring quản lý.
5. Đóng context khi ứng dụng hoặc phạm vi sử dụng kết thúc để Spring gọi các callback hủy bean và giải phóng tài nguyên.

Ví dụ dùng constructor không tham số và gọi `load()`/`refresh()` tường minh giúp nhìn rõ lifecycle. Không gọi `refresh()` lần nữa sau khi context đã được refresh thành công. Với một context được dùng như container độc lập, nên quản lý vòng đời của nó rõ ràng bằng `try-with-resources` hoặc một cơ chế shutdown tương ứng.

### 2.1. Nạp nhiều Groovy resource

`load(...)` có thể nhận nhiều resource location:

```java
try (var context = new GenericGroovyApplicationContext()) {
    context.load(
            "classpath:context/infrastructure.groovy",
            "classpath:context/services.groovy",
            "classpath:context/web-support.groovy");
    context.refresh();

    // Sử dụng các bean đã đăng ký
}
```

Có thể chia script theo trách nhiệm để cấu hình dễ quản lý: hạ tầng, service, adapter hoặc các bean hỗ trợ. Khi chia file, cần tránh khai báo trùng bean name ngoài ý muốn. Nếu cùng một bean name được đăng ký nhiều lần, kết quả phụ thuộc vào chính sách bean definition overriding và cấu hình của container; không nên dựa vào thứ tự nạp ngầm để thay thế bean.

### 2.2. Nạp từ classpath và filesystem

Spring resource abstraction cho phép nạp Groovy script từ nhiều nguồn.

| Resource location | Ví dụ | Mục đích |
|---|---|---|
| Classpath | `classpath:context/services.groovy` | Script được đóng gói cùng ứng dụng hoặc nằm trên classpath |
| File system | `file:/opt/myapp/config/services.groovy` | Script cấu hình nằm ngoài artifact |
| Relative file path | `file:./config/services.groovy` | Script nằm tương đối với working directory của tiến trình |

Ví dụ:

```java
try (var context = new GenericGroovyApplicationContext()) {
    context.load("file:./config/application-context.groovy");
    context.refresh();
}
```

Đường dẫn tương đối được phân giải theo working directory của tiến trình, không nhất thiết là thư mục chứa file JAR. Trong môi trường triển khai, nên dùng đường dẫn cấu hình rõ ràng và kiểm tra file tồn tại, quyền đọc cũng như cách đóng gói. Không nên giả định đường dẫn tương đối giống nhau giữa IDE, Gradle/Maven và service chạy trong container.

### 2.3. Nạp script bằng Resource object

Nếu ứng dụng đã có `Resource` hoặc muốn tự quyết định cách phân giải resource, có thể truyền resource vào reader thông qua `GenericGroovyApplicationContext` hoặc `GroovyBeanDefinitionReader`.

Ví dụ với classpath resource:

```java
import org.springframework.core.io.ClassPathResource;
import org.springframework.context.support.GenericGroovyApplicationContext;

try (var context = new GenericGroovyApplicationContext()) {
    context.load(new ClassPathResource("context/services.groovy"));
    context.refresh();
}
```

Cách này hữu ích khi resource được tạo bởi code hoặc được truyền vào từ một thành phần cấu hình khác. `ClassPathResource` dùng đường dẫn tương đối với classpath; không cần thêm tiền tố `classpath:` khi đã tạo object resource cụ thể.

## 3. Nạp script bằng GroovyBeanDefinitionReader

`GroovyBeanDefinitionReader` là reader chuyên đọc Groovy script và đăng ký bean definition vào một `BeanDefinitionRegistry`. Nó hữu ích khi cần kết hợp Groovy script với một loại cấu hình khác trong cùng một context.

Ví dụ:

```java
import org.springframework.beans.factory.groovy.GroovyBeanDefinitionReader;
import org.springframework.context.support.GenericApplicationContext;

GenericApplicationContext context = new GenericApplicationContext();
GroovyBeanDefinitionReader reader = new GroovyBeanDefinitionReader(context);

reader.loadBeanDefinitions("classpath:context/services.groovy");
context.refresh();

try {
    AccountService service = context.getBean(AccountService.class);
    System.out.println(service.displayName(42L));
} finally {
    context.close();
}
```

Reader không thay thế `ApplicationContext`. Nó chỉ đảm nhiệm việc đọc nguồn Groovy và đăng ký definition vào registry được truyền vào. Chính context vẫn quản lý lifecycle, dependency injection, event, resource và việc đóng bean.

### 3.1. Khi nào chọn GenericGroovyApplicationContext?

Dùng `GenericGroovyApplicationContext` khi:

- Phần lớn hoặc toàn bộ bean definition đến từ Groovy script.
- Muốn API `load()` và lifecycle của context nằm trong một đối tượng.
- Không cần tự điều phối nhiều loại reader.

Dùng `GroovyBeanDefinitionReader` khi:

- Đã có `GenericApplicationContext` và muốn nạp thêm Groovy bean definition.
- Muốn kết hợp Java annotation configuration, XML hoặc các nguồn bean definition khác.
- Cần kiểm soát cụ thể reader nào đăng ký bean vào registry.

Hai cách đều sử dụng cơ chế bean definition của Spring. Khác biệt chủ yếu nằm ở cách tổ chức việc nạp cấu hình.

## 4. Kết hợp Groovy script với Java configuration

Một dự án không bắt buộc phải chọn duy nhất Groovy hoặc Java configuration. `GenericApplicationContext` có thể nhận bean definition từ nhiều reader trước khi refresh.

Ví dụ lớp Java configuration:

```java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InfrastructureConfig {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Groovy script có thể khai báo bean cần sử dụng một dependency khác hoặc tham chiếu bean Java đã đăng ký:

```groovy
import com.example.account.AccountService
import com.example.account.AccountRepositoryImpl

beans {
    accountRepository(AccountRepositoryImpl)

    accountService(AccountService) {
        repository = ref('accountRepository')
    }
}
```

Đăng ký cả hai nguồn trước khi refresh:

```java
import org.springframework.beans.factory.annotation.AnnotatedBeanDefinitionReader;
import org.springframework.beans.factory.groovy.GroovyBeanDefinitionReader;
import org.springframework.context.support.GenericApplicationContext;

try (var context = new GenericApplicationContext()) {
    var annotationReader = new AnnotatedBeanDefinitionReader(context);
    annotationReader.register(InfrastructureConfig.class);

    var groovyReader = new GroovyBeanDefinitionReader(context);
    groovyReader.loadBeanDefinitions("classpath:context/services.groovy");

    context.refresh();

    Clock clock = context.getBean(Clock.class);
    AccountService service = context.getBean(AccountService.class);
}
```

Các reader cùng đăng ký bean definition vào một registry. Do đó, bean được khai báo bằng Java có thể được tham chiếu từ Groovy và ngược lại, miễn là tên bean, kiểu dependency và thứ tự đăng ký đáp ứng yêu cầu của cấu hình. Đăng ký tất cả nguồn trước `refresh()` giúp context có đầy đủ thông tin khi khởi tạo singleton.

Nếu cần cấu hình nhiều nguồn có thứ tự phức tạp, hãy thể hiện thứ tự đó rõ ràng trong code bootstrap. Tránh gọi `refresh()` giữa chừng rồi tiếp tục nạp thêm definition vào context đã hoạt động.

## 5. Groovy runtime và dependency cần thiết

Spring có hỗ trợ Groovy bean-definition reader, nhưng để thực thi Groovy script, ứng dụng cần Groovy runtime tương thích trên classpath. Chỉ có `spring-context` mà thiếu Groovy runtime có thể khiến việc nạp script thất bại khi Spring cần biên dịch hoặc đánh giá script.

Ví dụ Gradle với Groovy 4:

```groovy
dependencies {
    implementation("org.springframework:spring-context")
    runtimeOnly("org.apache.groovy:groovy")
}
```

Nếu code Java trực tiếp import `GenericGroovyApplicationContext` hoặc `GroovyBeanDefinitionReader`, compiler cũng cần thấy các kiểu Groovy liên quan mà API đó tham chiếu. Trong trường hợp đó, cấu hình Groovy dependency ở compile classpath thay vì chỉ runtime classpath, tùy phiên bản Spring/Groovy và cách dependency được khai báo.

Với Maven, dependency Groovy có thể được khai báo như sau khi dự án dùng Groovy 4:

```xml
<dependency>
    <groupId>org.apache.groovy</groupId>
    <artifactId>groovy</artifactId>
</dependency>
```

Phiên bản Groovy cần được quản lý rõ ràng bằng dependency management hoặc BOM phù hợp. Các dòng Groovy trước đây có thể dùng group id khác; hãy chọn tọa độ artifact đúng với phiên bản Groovy và baseline Spring của dự án. Không trộn tùy tiện các phiên bản Groovy khác nhau trên classpath.

Nếu ứng dụng chỉ dùng Java configuration và không nạp Groovy script, không cần thêm Groovy runtime chỉ vì Spring có hỗ trợ tính năng này.

## 6. Resource path và cách tổ chức file cấu hình

Một cấu trúc phổ biến cho ứng dụng dùng Groovy configuration:

```text
src/main/resources/
└── context/
    ├── infrastructure.groovy
    ├── persistence.groovy
    ├── services.groovy
    └── application.groovy
```

Có thể tạo một script tổng hợp để nạp các file con:

```groovy
beans {
    // Khai báo các bean thuộc cấu hình này.
}
```

Trong Java bootstrap, nạp từng resource location theo thứ tự rõ ràng:

```java
context.load(
        "classpath:context/infrastructure.groovy",
        "classpath:context/persistence.groovy",
        "classpath:context/services.groovy");
context.refresh();
```

Thứ tự nạp có thể ảnh hưởng khi nhiều script khai báo cùng tên bean hoặc khi có cấu hình phụ thuộc cách ghi đè definition. Tốt nhất là dùng tên bean duy nhất và thể hiện rõ các tham chiếu. Không nên dùng cùng một tên bean ở nhiều file với kỳ vọng file nạp sau luôn thay thế file trước, vì hành vi overriding còn phụ thuộc cấu hình bean factory và phiên bản framework.

### 6.1. Nạp cấu hình ngoài artifact

Trong một số hệ thống, file Groovy nằm ngoài JAR/WAR để có thể thay đổi cấu hình theo môi trường. Khi đó, nên truyền đường dẫn qua tham số khởi động hoặc biến môi trường, sau đó tạo resource location `file:` phù hợp.

Ví dụ minh họa:

```java
String configPath = System.getProperty("app.context.script");
if (configPath == null || configPath.isBlank()) {
    throw new IllegalStateException("Missing app.context.script");
}

try (var context = new GenericGroovyApplicationContext()) {
    context.load("file:" + configPath);
    context.refresh();
    // Chạy ứng dụng với context
}
```

Trong ứng dụng thực tế, cần chuẩn hóa đường dẫn thành URI hợp lệ thay vì nối chuỗi tùy tiện, đặc biệt khi path có khoảng trắng hoặc ký tự đặc biệt. Có thể tạo `FileSystemResource` từ `Path` nếu muốn tránh tự ghép prefix.

Groovy script là mã được thực thi khi nạp. Vì vậy, chỉ nên nạp script từ nguồn cấu hình mà ứng dụng tin cậy và có quyền kiểm soát. Một file cấu hình bị thay thế có thể thực hiện logic Groovy tùy ý trong tiến trình ứng dụng; nó có mức ảnh hưởng lớn hơn một file dữ liệu thuần.

## 7. Lifecycle của ApplicationContext khi nạp Groovy

Lifecycle cần được quản lý theo đúng thứ tự.

### 7.1. Tạo context

Khởi tạo context để có một bean definition registry và bean factory. Với `GenericGroovyApplicationContext`, Groovy reader được tích hợp sẵn để nạp script.

### 7.2. Nạp bean definition

Gọi `load(...)` hoặc dùng `GroovyBeanDefinitionReader` để đọc script. Ở giai đoạn này, Spring phân tích script và đăng ký definition. Nếu script sai cú pháp, không tìm thấy class được import hoặc khai báo bean không hợp lệ, lỗi sẽ phát sinh khi nạp.

### 7.3. Refresh context

`refresh()` kích hoạt quá trình hoàn thiện context: chuẩn bị bean factory, xử lý các bean factory post-processor, đăng ký bean post-processor, tạo singleton eager, xử lý lifecycle và phát sự kiện refresh.

Một số lỗi chỉ xuất hiện tại đây, ví dụ:

- Không tìm thấy bean được tham chiếu.
- Không có constructor hoặc setter phù hợp.
- Không thể resolve placeholder hoặc dependency.
- Bean post-processor hoặc factory method thất bại.
- Bean khởi tạo ném exception.

### 7.4. Sử dụng và đóng context

Sau khi refresh thành công, ứng dụng có thể lấy bean, publish event và sử dụng các dịch vụ trong context. Khi ứng dụng kết thúc, đóng context để Spring gọi các callback destroy và giải phóng tài nguyên do bean quản lý.

Không nên tạo và refresh một `ApplicationContext` mới cho từng request. Context thường được tạo một lần trong vòng đời ứng dụng hoặc một lần trong phạm vi test cần cô lập.

## 8. Kiểm thử việc nạp Groovy script

Việc nạp Groovy configuration nên được kiểm tra bằng một test nhỏ sử dụng resource test riêng. Test có thể xác minh script được tìm thấy, bean được đăng ký, dependency được inject và hành vi bean đúng như cấu hình.

### 8.1. Tạo Groovy script trong test resources

Ví dụ file `src/test/resources/context/test-services.groovy`:

```groovy
import com.example.greeting.GreetingService

beans {
    greetingService(GreetingService) {
        prefix = 'Hello'
    }
}
```

Class Java:

```java
package com.example.greeting;

public class GreetingService {

    private String prefix;

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        return prefix + ", " + name;
    }
}
```

### 8.2. JUnit test nạp context

```java
import org.junit.jupiter.api.Test;
import org.springframework.context.support.GenericGroovyApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class GroovyApplicationContextTest {

    @Test
    void loadsBeanDefinitionsFromGroovyScript() {
        try (var context = new GenericGroovyApplicationContext()) {
            context.load("classpath:context/test-services.groovy");
            context.refresh();

            GreetingService service = context.getBean(GreetingService.class);

            assertNotNull(service);
            assertEquals("Hello, Spring", service.greet("Spring"));
        }
    }
}
```

Test này kiểm tra cả việc tìm resource, phân tích DSL, đăng ký bean definition, khởi tạo bean và inject property. Dùng `try-with-resources` đảm bảo context được đóng ngay cả khi assertion thất bại.

### 8.3. Kiểm tra bean reference giữa các definition

Script test có thể khai báo hai bean và tham chiếu lẫn nhau:

```groovy
beans {
    greetingFormatter(GreetingFormatter) {
        prefix = 'Welcome'
    }

    greetingService(GreetingService) {
        formatter = ref('greetingFormatter')
    }
}
```

Test nên lấy `GreetingService`, gọi hành vi công khai và xác minh kết quả sử dụng formatter. Nếu cần xác minh identity của dependency, có thể kiểm tra bean được inject là cùng bean có tên `greetingFormatter`, nhưng nên ưu tiên kiểm tra hành vi nếu identity không phải hợp đồng của ứng dụng.

### 8.4. Kiểm tra lỗi nạp script

Các trường hợp lỗi hữu ích để kiểm tra ở phạm vi cấu hình:

- Resource location không tồn tại.
- Script sai cú pháp Groovy.
- Bean class không có trên classpath.
- Bean reference trỏ đến tên không tồn tại.
- Property không thể gán hoặc constructor không tương thích.
- Dependency cycle không được container xử lý theo cấu hình hiện tại.

Tùy lỗi, exception có thể xuất hiện trong `load()` hoặc `refresh()`. Test nên kiểm tra loại lỗi ở mức phù hợp và thông tin nguyên nhân, tránh khóa quá chặt vào toàn bộ message nội bộ có thể thay đổi giữa phiên bản Spring/Groovy.

## 9. Dùng Groovy script trong kiểm thử Spring TestContext

Spring TestContext có thể nạp Groovy bean-definition script thông qua `@ContextConfiguration`. Khi Groovy runtime có trên classpath và resource được chỉ định là file `.groovy`, loader mặc định của Spring TestContext có thể chọn cơ chế đọc Groovy phù hợp.

Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(locations = "classpath:context/test-services.groovy")
class GreetingServiceGroovyContextTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void loadsBeanFromGroovyContextConfiguration() {
        assertEquals("Hello, Spring", greetingService.greet("Spring"));
    }
}
```

Ở đây Spring TestContext quản lý cache và lifecycle của context cho test class. Script phải nằm trên test classpath, và Groovy runtime phải có mặt để Spring đọc script. Có thể dùng `@SpringJUnitConfig` khi muốn kết hợp đăng ký `SpringExtension` với cấu hình context theo cách rút gọn; `@ContextConfiguration` vẫn là nơi chỉ định resource location.

Khi cần nạp script bằng code, kiểm soát thứ tự nhiều reader hoặc kiểm tra riêng quá trình bootstrap, dùng `GenericGroovyApplicationContext` trong test như ví dụ trước. Khi muốn tận dụng TestContext caching, dependency injection vào test instance và các listener/callback của Spring Test, khai báo Groovy resource qua `@ContextConfiguration` là cách phù hợp.

Không nhầm `@TestPropertySource` với Groovy bean-definition script. `@TestPropertySource` cung cấp property values cho Environment; nó không đọc một Groovy `beans {}` script để đăng ký bean definition.

## 10. So sánh Groovy configuration với XML và Java configuration

| Cách cấu hình | Đặc điểm | Trường hợp phù hợp |
|---|---|---|
| XML | Khai báo bean bằng phần tử và thuộc tính XML; dễ dùng với hệ thống legacy | Ứng dụng có cấu hình XML sẵn hoặc cần tương thích cấu hình cũ |
| Java configuration | Dùng `@Configuration`, `@Bean`, component scanning và type-safe Java | Ứng dụng Java hiện đại cần compiler hỗ trợ và refactor an toàn |
| Groovy bean DSL | Dùng Groovy script và `beans {}` để khai báo bean | Dự án có Groovy runtime, cần cấu hình linh hoạt hoặc đang sử dụng Groovy DSL |

Groovy DSL ngắn gọn và biểu đạt tốt các cấu hình có nhiều property/reference. Tuy nhiên, script vẫn là mã có thể thực thi và không có cùng mức kiểm tra kiểu tĩnh như Java configuration trong mọi trường hợp. Cần cân nhắc khả năng bảo trì, debugging, dependency Groovy runtime và kỹ năng của đội ngũ.

Groovy bean DSL cũng không đồng nghĩa với việc viết một class Groovy có annotation `@Configuration`. Một Groovy class dùng annotation có thể được xử lý theo cơ chế Java annotation configuration; còn script `beans {}` được đọc bởi `GroovyBeanDefinitionReader`. Hai cách có thể cùng xuất hiện nhưng là hai hình thức cấu hình khác nhau.

## 11. Lỗi thường gặp khi nạp Groovy script

**Thiếu Groovy runtime.** Spring tìm được class reader nhưng không thể thực thi script vì Groovy runtime không có trên classpath hoặc không tương thích. Kiểm tra dependency tree và phiên bản Groovy.

**Sai resource path.** Script nằm trong `src/main/resources` nhưng đường dẫn không đúng với classpath sau khi build. Dùng `classpath:context/services.groovy` và xác nhận file được đóng gói vào output resources.

**Quên gọi `refresh()`.** Bean definition đã được đăng ký nhưng context chưa được kích hoạt. Gọi `refresh()` sau khi nạp tất cả nguồn cấu hình.

**Gọi `refresh()` quá sớm.** Nếu refresh trước khi nạp hết script hoặc Java configuration, các bean eager có thể được tạo khi registry chưa đầy đủ. Nạp toàn bộ nguồn trước rồi mới refresh.

**Dùng chuỗi thay cho bean reference.** `repository = 'accountRepository'` gán một String; dùng `repository = ref('accountRepository')` để tham chiếu bean.

**Khai báo trùng bean name.** Nhiều script đăng ký cùng một tên bean gây xung đột hoặc phụ thuộc chính sách overriding. Dùng tên rõ ràng và kiểm soát thứ tự nạp.

**Không tìm thấy class trong script.** Class cần import phải có trên classpath khi Groovy script được biên dịch/thực thi. Kiểm tra package, tên class và dependency.

**Đóng context không đúng.** Không đóng context có thể để lại thread, connection pool hoặc tài nguyên bean. Dùng `close()` hoặc `try-with-resources` trong code sở hữu context.

**Cho rằng Groovy script là file dữ liệu an toàn.** Script được thực thi trong tiến trình. Chỉ nạp file từ nguồn được tin cậy và kiểm soát quyền ghi.

## 12. Quy trình nạp Groovy script trong ứng dụng

Khi thiết lập một `ApplicationContext` dùng Groovy bean definition, có thể đi theo trình tự:

1. Xác định Groovy script là nguồn cấu hình chính hay chỉ là một phần bổ sung.
2. Đặt script trong classpath resources hoặc chọn rõ filesystem resource location.
3. Bảo đảm Groovy runtime tương thích có trên compile/runtime classpath theo API đang dùng.
4. Khai báo bean trong `beans {}` với tên, class, property và bean reference rõ ràng.
5. Tạo `GenericGroovyApplicationContext` hoặc một `GenericApplicationContext` phù hợp.
6. Nạp toàn bộ Groovy resource trước khi refresh; nếu trộn Java configuration, đăng ký tất cả reader vào cùng registry.
7. Gọi `refresh()` đúng một lần sau khi hoàn tất đăng ký definition.
8. Lấy bean qua `getBean()` và sử dụng các interface/hành vi công khai.
9. Đóng context đúng vòng đời để hủy bean và giải phóng tài nguyên.
10. Viết test nạp script từ `src/test/resources` để bảo vệ resource path, bean definition và dependency wiring.

Khi tổ chức đúng các bước này, Groovy script trở thành một nguồn bean definition được Spring quản lý đầy đủ. `GenericGroovyApplicationContext` là lựa chọn thuận tiện cho ứng dụng dùng Groovy configuration; `GroovyBeanDefinitionReader` phù hợp khi cần kết hợp Groovy với các nguồn cấu hình khác. Cả hai đều đưa bean definition vào cùng cơ chế lifecycle của `ApplicationContext`, vì vậy việc nạp resource, refresh và đóng context cần được quản lý như một phần của bootstrap ứng dụng.
