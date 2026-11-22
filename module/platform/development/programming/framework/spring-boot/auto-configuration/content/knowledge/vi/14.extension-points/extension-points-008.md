# Quy định quyền sở hữu vòng đời và giải phóng tài nguyên của bean tạo tự động

> **Spring Boot Auto Configuration → Điểm mở rộng.** Bài học xác định ai chịu trách nhiệm tạo, sử dụng, dừng và giải phóng tài nguyên của bean do auto-configuration cung cấp. Nội dung tập trung vào quyền quản lý của Spring container, cách auto-configuration nhường cho bean do ứng dụng cung cấp, destruction callback, khác biệt giữa singleton/prototype và kiểm thử cleanup. Ví dụ sử dụng Java 17+ và Spring Boot 3.3.x.

## 1. Vì sao bean tạo được chưa có nghĩa là tài nguyên được quản lý đúng?

Một auto-configuration có thể cung cấp bean giữ tài nguyên bên ngoài:

- Connection pool, database client hoặc HTTP client.
- File handle, socket, channel và native handle.
- Executor, scheduler, worker thread.
- Message consumer hoặc listener container.
- Cache, SDK hoặc thư viện có phương thức `close()` / `shutdown()`.

Nếu bean chỉ được tạo mà không có chính sách giải phóng, ứng dụng có thể rò rỉ file descriptor, giữ thread khiến JVM không thoát, không trả kết nối về pool, giữ port hoặc tiếp tục xử lý công việc sau khi context đã đóng.

Với bean do Spring quản lý, hợp đồng nên là:

1. Auto-configuration quyết định bean có được đăng ký và cách tạo bean.
2. Spring container tạo instance, inject dependency và quản lý lifecycle trong scope của bean.
3. Bean tiêu thụ chỉ sử dụng dependency được inject; không tự ý đóng tài nguyên mà nó không sở hữu.
4. Khi scope kết thúc, container gọi destruction callback đã đăng ký.
5. Nếu ứng dụng cung cấp bean thay thế, cấu hình của ứng dụng chịu trách nhiệm khai báo lifecycle thích hợp cho bean đó.

**Auto-configuration cung cấp bean definition; Spring container quản lý vòng đời instance.** Thư viện phải công bố rõ cách đóng tài nguyên mà bean sở hữu, không bắt người dùng đoán thời điểm gọi `close()`.

## 2. Phân biệt quyền tạo, quyền sử dụng và quyền giải phóng

| Vai trò | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Bean definition owner | Quyết định bean có được đăng ký hay không, factory method, scope và callback hủy | Auto-configuration hoặc cấu hình do ứng dụng viết |
| Spring container | Tạo instance, inject dependency, gọi lifecycle callback và hủy bean theo scope | `ApplicationContext` / `BeanFactory` |
| Bean consumer | Sử dụng dependency trong thời gian bean còn hợp lệ | Service gọi `HttpClient` hoặc `WorkerResource` |

Ví dụ:

~~~text
WorkerAutoConfiguration
       |
       +-- đăng ký bean definition ManagedClient
       |          |
       |          +-- destroyMethod = close
       |
       v
Spring IoC Container
       |
       +-- tạo ManagedClient
       +-- inject ManagedClient vào FeatureService
       +-- quản lý dependency và scope
       |
       +-- khi context đóng:
                 hủy bean tiêu thụ trước
                 gọi ManagedClient.close()
~~~

Service tiêu thụ có thể giữ reference đến `ManagedClient`, nhưng điều đó **không biến service thành chủ sở hữu tài nguyên**. Nếu cả service và container cùng gọi `close()` trên một client singleton, cleanup có thể chạy hai lần hoặc đóng kết nối trong lúc bean khác vẫn đang sử dụng.

Một hợp đồng ownership tốt phải trả lời:
- Bean nào thực sự sở hữu tài nguyên?
- Ai tạo bean và đăng ký nó với container?
- Scope của bean là gì?
- Callback nào dừng hoặc giải phóng tài nguyên?
- Khi user cung cấp bean thay thế, ai khai báo callback hủy?
- Những bean nào cần dừng trước tài nguyên nền?

## 3. Vòng đời bean và thời điểm cleanup

Với singleton thông thường, vòng đời có thể mô tả:

~~~text
1. Đọc configuration / auto-configuration
                  |
                  v
2. Đăng ký BeanDefinition
                  |
                  v
3. Instantiate bean
                  |
                  v
4. Inject dependencies / xử lý Aware
                  |
                  v
5. BeanPostProcessor và initialization callbacks
                  |
                  v
6. Bean sẵn sàng cho ứng dụng sử dụng
                  |
                  v
7. ApplicationContext bắt đầu đóng
                  |
                  v
8. Dừng các bean có lifecycle phù hợp
                  |
                  v
9. Hủy singleton theo quan hệ phụ thuộc
                  |
                  v
10. Gọi destroy callbacks / close tài nguyên
~~~

Các điểm quan trọng:

- Auto-configuration được xử lý và bean definition được đăng ký trước khi bean instance được tạo.
- Dependency injection giúp Spring biết bean nào cần bean nào. Bean tiêu thụ thường được tạo sau dependency và được hủy trước dependency.
- Bean có thể khai báo initialization callback và destruction callback.
- Khi `ApplicationContext` đóng, Spring gọi callback hủy đã đăng ký cho các bean thuộc phạm vi được quản lý.
- Việc một bean được inject vào bean khác không chuyển quyền sở hữu lifecycle sang bean tiêu thụ.

Context có thể đóng qua `context.close()`, try-with-resources với context phù hợp, hoặc shutdown hook khi JVM kết thúc. Spring Boot đăng ký shutdown hook theo mặc định cho ứng dụng khởi chạy thông thường. Nếu tiến trình vẫn chạy, context vẫn còn mở và callback hủy singleton chưa được gọi.

### 3.1. Singleton

Singleton là scope mặc định: một instance trong mỗi container. Khi context đóng, container gọi destruction callback được đăng ký trong bean definition.

Đây là lựa chọn phổ biến cho connection pool, HTTP client dùng chung, scheduler hoặc dịch vụ nền do auto-configuration cung cấp.

Nếu singleton A được inject vào singleton B, Spring biết quan hệ dependency và có thể hủy B trước A. Nhờ vậy B có cơ hội dừng công việc trước khi A bị đóng.

### 3.2. Prototype

Với scope `prototype`, Spring tạo instance mới mỗi lần bean được yêu cầu, nhưng sau khi giao instance cho caller, container **không tự gọi destruction callback khi caller ngừng sử dụng**.

Do đó, không nên tạo resource-bearing prototype rồi kỳ vọng Spring tự đóng khi instance không còn reference. Caller hoặc một cơ chế quản lý riêng phải chịu trách nhiệm cleanup.

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
ManagedResource newManagedResource() {
    return new ManagedResource();
}
~~~

Đây là đoạn cấu hình minh họa. Nếu `ManagedResource` giữ file/socket/client, caller nhận instance phải biết và thực hiện cleanup. Với tài nguyên dùng chung toàn ứng dụng, singleton thường dễ quản lý hơn.

### 3.3. Custom scope

Request, session hoặc custom scope có thể gọi callback hủy khi scope kết thúc. Hành vi phụ thuộc implementation của scope. Không mặc định mọi scope đều đóng bean theo đúng thời điểm như singleton.

Khi thiết kế auto-configuration, chọn scope theo **thời gian sống của tài nguyên**. Connection pool dùng chung thường không nên là prototype; đối tượng không giữ tài nguyên ngoài có thể phù hợp với scope ngắn hơn.

## 4. Các destruction callback Spring hỗ trợ

| Cơ chế | Khai báo ở đâu | Khi phù hợp |
| --- | --- | --- |
| `@Bean(destroyMethod = "close")` | Factory method tạo bean | Thư viện muốn công khai rõ cách đóng resource |
| Inferred destroy method | `@Bean` trả về object có `close()` / `shutdown()` công khai phù hợp | Theo quy ước mặc định của Spring |
| `@PreDestroy` | Method trong class bean | Bean tự mô tả cleanup bằng annotation Jakarta |
| `DisposableBean.destroy()` | Bean implement interface Spring | Integration cần lifecycle API của Spring |
| `DestructionAwareBeanPostProcessor` | Hạ tầng extension | Chính sách cleanup đặc biệt áp dụng xuyên nhiều bean |
| `SmartLifecycle.stop(...)` | Bean có vòng đời start/stop | Worker, listener hoặc thành phần chạy nền cần dừng có phối hợp |

### 4.1. @Bean(destroyMethod = "close")

~~~java
@Bean(destroyMethod = "close")
ManagedClient managedClient() {
    return new ManagedClient();
}
~~~

Khi singleton bean bị hủy, Spring gọi method `close()` đã khai báo. Method phải tồn tại trên object trả về và có thể được gọi.

Spring cũng hỗ trợ suy luận một số destruction method công khai như `close` hoặc `shutdown` theo quy ước mặc định của `@Bean`. Với tài nguyên quan trọng, khai báo tường minh giúp hợp đồng dễ đọc và tránh việc người bảo trì không nhận ra cơ chế suy luận.

Nếu cố ý không muốn Spring suy luận destruction method, `@Bean(destroyMethod = "")` có thể tắt suy luận mặc định. Chỉ dùng khi đã xác định một cơ chế cleanup khác; không tắt callback rồi để resource rò rỉ.

### 4.2. AutoCloseable và Closeable

Java cung cấp `AutoCloseable`:

~~~java
public final class ManagedClient implements AutoCloseable {

    @Override
    public void close() {
        // release resources
    }
}
~~~

`Closeable` kế thừa `AutoCloseable` và thường được dùng cho I/O. Implement interface thể hiện rõ object có thể được đóng.

Với bean singleton do Spring quản lý, có thể kết hợp:

~~~java
@Bean(destroyMethod = "close")
ManagedClient managedClient() {
    return new ManagedClient();
}
~~~

Không nhầm `AutoCloseable` với try-with-resources trong bean consumer. Nếu container sở hữu bean, container gọi callback khi lifecycle kết thúc; consumer không nên tự đóng reference được inject sau mỗi lần dùng.

### 4.3. @PreDestroy

Trong Spring Boot 3 / Spring Framework 6, annotation thuộc Jakarta:

~~~java
import jakarta.annotation.PreDestroy;

public class ManagedClient {

    @PreDestroy
    public void release() {
        // release resources
    }
}
~~~

`@PreDestroy` phù hợp khi class tự khai báo hành động dọn dẹp mà không cần implement interface Spring. Bean phải được Spring quản lý và hạ tầng annotation lifecycle phải được cấu hình.

Nếu dùng `@PreDestroy` cùng với `@Bean(destroyMethod = "close")`, `DisposableBean` hoặc callback khác mà tất cả đều gọi cùng thao tác, cần tránh cleanup lặp. Hãy chọn một cơ chế chính hoặc làm cleanup idempotent.

### 4.4. DisposableBean

~~~java
import org.springframework.beans.factory.DisposableBean;

public class ManagedClient implements DisposableBean {

    @Override
    public void destroy() {
        // release resources
    }
}
~~~

Đây là API gắn trực tiếp với Spring. Nó hữu ích trong một số integration nhưng làm class phụ thuộc Spring. Với thư viện muốn giữ resource class độc lập framework, `AutoCloseable` cộng với `@Bean(destroyMethod = "close")` thường tạo ranh giới rõ hơn.

### 4.5. Làm cleanup an toàn

Không nên đồng thời:
- Gọi `close()` trong `@PreDestroy`;
- Implement `DisposableBean.destroy()` cũng gọi `close()`;
- Khai báo `@Bean(destroyMethod = "close")`;
- Yêu cầu consumer gọi `close()` thủ công.

Các callback có thể cùng tham gia lifecycle, gây double-close. Nếu close không idempotent, lần thứ hai có thể ném exception hoặc thao tác lên resource đã giải phóng.

Một method `close()` tốt nên:
- Có thể gọi lặp an toàn nếu hợp đồng yêu cầu idempotency;
- Đánh dấu trạng thái đóng và ngăn thao tác mới;
- Dừng hoặc chờ công việc đang chạy trong giới hạn thời gian;
- Đóng resource theo thứ tự hợp lý;
- Không nuốt exception cleanup quan trọng;
- Dọn các resource còn lại kể cả khi một bước đóng thất bại, thường bằng `try/finally` hoặc suppressed exceptions.

## 5. Thiết kế auto-configuration có trách nhiệm lifecycle

Một auto-configuration cung cấp bean dùng tài nguyên cần xác định:

1. **Điều kiện xuất hiện:** property, classpath hoặc bean nào phải tồn tại?
2. **Bean owner:** auto-configuration tạo bean mặc định hay nhường cho ứng dụng?
3. **Scope:** singleton, prototype hay scope khác?
4. **Resource owner:** bean nào thực sự giữ và giải phóng resource?
5. **Destroy callback:** `close`, `shutdown`, `@PreDestroy` hay lifecycle protocol?
6. **Dependency order:** worker/listener nào phải dừng trước client/pool?
7. **Override contract:** nếu user cung cấp bean riêng, user phải thực hiện cleanup thế nào?

Ví dụ:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
    prefix = "demo.worker",
    name = "enabled",
    havingValue = "true"
)
public class WorkerAutoConfiguration {

    @Bean(destroyMethod = "close")
    @ConditionalOnMissingBean(ManagedWorkerResource.class)
    ManagedWorkerResource managedWorkerResource() throws IOException {
        return new ManagedWorkerResource();
    }
}
~~~

Ba annotation có ba trách nhiệm:
- `@ConditionalOnProperty` chỉ bật auto-configuration khi property cho phép.
- `@ConditionalOnMissingBean` cho phép ứng dụng cung cấp bean thay thế.
- `@Bean(destroyMethod = "close")` đăng ký callback giải phóng resource cho bean do factory method tạo.

### 5.1. Khi user override bean, ai chịu trách nhiệm cleanup?

~~~java
@Configuration(proxyBeanMethods = false)
class UserWorkerConfiguration {

    @Bean(destroyMethod = "close")
    ManagedWorkerResource managedWorkerResource() throws IOException {
        return new ManagedWorkerResource();
    }
}
~~~

Nếu bean này được đăng ký trước khi auto-configuration đánh giá `@ConditionalOnMissingBean`, cấu hình mặc định nhường. **Bean thay thế vẫn được Spring container quản lý** vì nó cũng được đăng ký qua Spring; nhưng cấu hình do ứng dụng sở hữu phải khai báo lifecycle contract thích hợp.

Auto-configuration không nên tìm rồi tự đóng bean do user cung cấp. Thư viện chỉ sở hữu tài nguyên bên trong bean mặc định mà nó tạo. Khi người dùng override, người dùng chịu trách nhiệm bảo đảm bean của họ có cleanup phù hợp.

### 5.2. Không đóng dependency được inject như thể mình sở hữu nó

~~~java
@Bean
FeatureService featureService(ManagedWorkerResource resource) {
    return new FeatureService(resource);
}
~~~

`FeatureService` sử dụng `resource`; Spring biết dependency này. Nếu `FeatureService` có destruction callback, callback đó nên dừng công việc của chính service, không tự ý gọi `resource.close()` nếu resource thuộc bean singleton khác.

Container quản lý quan hệ dependency và hủy bean phụ thuộc trước dependency. Service có thể dừng nhận công việc, hoàn tất hoặc hủy tác vụ đang chạy, rồi resource nền mới được đóng.

### 5.3. Không dùng @DependsOn thay cho dependency injection

`@DependsOn` có thể ép một bean được khởi tạo trước bean khác và singleton phụ thuộc được hủy trước bean mà nó phụ thuộc. Tuy nhiên, nếu bean A được inject trực tiếp vào bean B, Spring đã biết quan hệ dependency.

Chỉ dùng `@DependsOn` khi cần ràng buộc khởi tạo/hủy không thể hiện qua dependency trực tiếp. Nó không thay thế `@Bean(destroyMethod=...)`, không đăng ký bean còn thiếu và không biến consumer thành owner của tài nguyên.

## 6. Ví dụ chạy được: auto-configuration tạo resource và Spring tự đóng

Lab tạo một file tạm làm tài nguyên đại diện. Bean `ManagedWorkerResource` mở file, ghi dữ liệu, rồi đóng stream và xóa file khi Spring context kết thúc.

Ta cần quan sát:
- Khi `demo.worker.enabled=true`, bean được auto-configuration tạo.
- Khi feature tắt hoặc không khai báo, auto-configuration không tạo bean.
- Khi context đóng, callback `close()` được gọi và file tạm bị xóa.
- ApplicationRunner chỉ sử dụng bean, không gọi `close()`.

Yêu cầu: JDK 17+, Maven và khả năng tải dependency. Phiên bản ví dụ: Spring Boot 3.3.13.

### 6.1. Cấu trúc dự án

~~~text
lifecycle-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── demo/
    │   │       ├── app/
    │   │       │   └── LifecycleDemoApplication.java
    │   │       └── worker/
    │   │           ├── ManagedWorkerResource.java
    │   │           └── autoconfigure/
    │   │               └── WorkerAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/
    │           └── spring/
    │               └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/
            └── demo/
                └── worker/
                    └── WorkerAutoConfigurationTest.java
~~~

Application nằm trong `demo.app`, auto-configuration trong `demo.worker.autoconfigure`. Component scan của application không tự quét lớp auto-configuration; Boot tìm nó qua tệp `AutoConfiguration.imports`.

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

### 6.3. ManagedWorkerResource.java

Tệp `src/main/java/demo/worker/ManagedWorkerResource.java`:

~~~java
package demo.worker;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class ManagedWorkerResource implements AutoCloseable {

    private final Path file;
    private final OutputStream output;
    private boolean closed;

    public ManagedWorkerResource() throws IOException {
        Path created = Files.createTempFile("managed-worker-", ".txt");
        OutputStream opened;

        try {
            opened = Files.newOutputStream(
                    created,
                    StandardOpenOption.WRITE
            );
        } catch (IOException openFailure) {
            try {
                Files.deleteIfExists(created);
            } catch (IOException cleanupFailure) {
                openFailure.addSuppressed(cleanupFailure);
            }
            throw openFailure;
        }

        this.file = created;
        this.output = opened;
        System.out.println("resource opened");
    }

    public synchronized void write(String message) throws IOException {
        if (closed) {
            throw new IllegalStateException("Resource is already closed");
        }
        output.write(message.getBytes(StandardCharsets.UTF_8));
        output.flush();
    }

    @Override
    public synchronized void close() throws IOException {
        if (closed) {
            return;
        }

        IOException failure = null;

        try {
            output.close();
        } catch (IOException closeFailure) {
            failure = closeFailure;
        }

        try {
            Files.deleteIfExists(file);
        } catch (IOException deleteFailure) {
            if (failure == null) {
                failure = deleteFailure;
            } else {
                failure.addSuppressed(deleteFailure);
            }
        }

        if (failure != null) {
            throw failure;
        }

        closed = true;
        System.out.println("resource closed");
    }

    Path filePath() {
        return file;
    }
}
~~~

Giải thích:
- Constructor tạo file tạm và mở `OutputStream`. Nếu mở stream thất bại, nó cố gắng xóa file đã tạo; lỗi cleanup được giữ dưới dạng suppressed exception.
- `write()` kiểm tra trạng thái rồi ghi UTF-8.
- `close()` đóng stream, sau đó xóa file kể cả khi đóng stream gặp lỗi.
- Nếu một bước cleanup thất bại, method báo exception thay vì âm thầm coi là thành công.
- Cờ `closed` giúp thao tác close thành công có tính idempotent; lần gọi sau không lặp thao tác lên tài nguyên đã giải phóng.

Đây là resource thật của lab nhưng không đại diện cho một client database/network hoàn chỉnh. Mục tiêu là quan sát file được tạo và xóa theo lifecycle của bean.

### 6.4. WorkerAutoConfiguration.java

Tệp `src/main/java/demo/worker/autoconfigure/WorkerAutoConfiguration.java`:

~~~java
package demo.worker.autoconfigure;

import java.io.IOException;

import demo.worker.ManagedWorkerResource;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.worker",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class WorkerAutoConfiguration {

    @Bean(destroyMethod = "close")
    @ConditionalOnMissingBean(ManagedWorkerResource.class)
    ManagedWorkerResource managedWorkerResource() throws IOException {
        return new ManagedWorkerResource();
    }
}
~~~

Ba annotation có ba trách nhiệm:
1. `@ConditionalOnProperty` chỉ bật auto-configuration khi property cho phép.
2. `@ConditionalOnMissingBean` cho phép ứng dụng cung cấp bean thay thế.
3. `@Bean(destroyMethod = "close")` đăng ký callback giải phóng resource cho bean do factory method tạo.

### 6.5. Tệp AutoConfiguration.imports

Tạo file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung đúng một dòng:

~~~text
demo.worker.autoconfigure.WorkerAutoConfiguration
~~~

Tên class phải khớp package và tên lớp. Nếu tệp thiếu hoặc sai, Boot không tìm thấy auto-configuration theo cơ chế đăng ký của starter; đặt property `demo.worker.enabled=true` một mình không làm bean xuất hiện.

### 6.6. LifecycleDemoApplication.java

Tệp `src/main/java/demo/app/LifecycleDemoApplication.java`:

~~~java
package demo.app;

import demo.worker.ManagedWorkerResource;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LifecycleDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LifecycleDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner useWorkerResource(
            ObjectProvider<ManagedWorkerResource> resources) {

        return args -> {
            ManagedWorkerResource resource = resources.getIfAvailable();

            System.out.println(
                    "worker resource present: " + (resource != null)
            );

            if (resource != null) {
                resource.write("sample payload");
                System.out.println("resource used");
            }
        };
    }
}
~~~

`ObjectProvider` cho phép ứng dụng sử dụng bean theo cách tùy chọn. Nếu feature bị tắt, runner vẫn chạy và không ném lỗi vì thiếu dependency. Khi bean tồn tại, runner sử dụng nó nhưng **không gọi `close()`**.

### 6.7. Đóng gói và chạy

Từ thư mục `lifecycle-demo`:

~~~bash
mvn -q -DskipTests package
~~~

**Trường hợp A — bật feature:**

~~~bash
java -jar target/lifecycle-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.worker.enabled=true
~~~

Các dòng stdout do chương trình in:

~~~text
resource opened
worker resource present: true
resource used
resource closed
~~~

Giải thích:
1. Runner yêu cầu bean; Spring tạo `ManagedWorkerResource`, constructor mở file.
2. Runner ghi dữ liệu và hoàn tất sử dụng reference.
3. Khi tiến trình Java kết thúc, shutdown hook của Spring Boot đóng `ApplicationContext`.
4. Container gọi `destroyMethod="close"` và resource được giải phóng.

**Trường hợp B — tắt feature:**

~~~bash
java -jar target/lifecycle-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.worker.enabled=false
~~~

Stdout:

~~~text
worker resource present: false
~~~

Không có file nào được tạo vì bean mặc định không xuất hiện.

**Trường hợp C — không khai báo property:**

~~~bash
java -jar target/lifecycle-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Stdout cũng là:

~~~text
worker resource present: false
~~~

Điều này đúng vì `matchIfMissing=false` là mặc định. Các kết quả trên mô tả dòng do chương trình `System.out.println` in; log nội bộ có thể khác tùy môi trường và cấu hình.

Trong PowerShell/CMD có thể chạy từng lệnh Java một dòng như trên. Nếu chạy trong IDE mà JVM vẫn còn hoạt động, context chỉ được đóng khi ứng dụng dừng hoặc code chủ động đóng context.

## 7. Kiểm thử rằng context đóng thì resource thực sự được giải phóng

Chỉ xác nhận bean tồn tại là chưa đủ. Với resource-bearing bean, cần xác nhận **sau khi context kết thúc, tài nguyên đã được đóng**.

Tệp `src/test/java/demo/worker/WorkerAutoConfigurationTest.java`:

~~~java
package demo.worker;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class WorkerAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            WorkerAutoConfiguration.class
                    ));

    @Test
    void missingPropertyDoesNotCreateResource() {
        runner.run(context ->
                assertThat(context)
                        .doesNotHaveBean(ManagedWorkerResource.class)
        );
    }

    @Test
    void falsePropertyDoesNotCreateResource() {
        runner.withPropertyValues("demo.worker.enabled=false")
                .run(context ->
                        assertThat(context)
                                .doesNotHaveBean(ManagedWorkerResource.class)
                );
    }

    @Test
    void closingContextReleasesAutoConfiguredResource() {
        AtomicReference<Path> resourcePath = new AtomicReference<>();

        runner.withPropertyValues("demo.worker.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(ManagedWorkerResource.class);

                    ManagedWorkerResource resource =
                            context.getBean(ManagedWorkerResource.class);

                    Path path = resource.filePath();
                    resourcePath.set(path);

                    assertThat(Files.exists(path)).isTrue();
                });

        // ApplicationContextRunner closes the context after the callback.
        assertThat(resourcePath.get()).isNotNull();
        assertThat(Files.exists(resourcePath.get())).isFalse();
    }
}
~~~

Test nằm cùng package `demo.worker` để gọi method `filePath()` package-private; method này phục vụ quan sát trong lab, không phải API công khai của thư viện.

Chạy:

~~~bash
mvn test
~~~

Kỳ vọng **3 test PASS**:
- Không cấu hình → không tạo resource.
- `enabled=false` → không tạo resource.
- `enabled=true` → có resource trong context; sau khi callback test kết thúc và context đóng, file không còn tồn tại.

Đây là kiểm thử lifecycle có bằng chứng trực tiếp: file được tạo trong thời gian bean sống và bị xóa sau khi container hủy bean.

## 8. Khi bean có công việc nền: stop trước, close sau

Một bean chỉ giữ file hoặc client đơn giản có thể chỉ cần `close()`. Nhưng worker, message listener hoặc scheduler còn có hoạt động đang chạy. Khi ứng dụng dừng, cần ngừng nhận công việc, chờ hoặc hủy công việc đang chạy, rồi mới giải phóng tài nguyên dùng chung.

`Lifecycle` / `SmartLifecycle` dành cho thành phần cần quy trình start/stop có phối hợp:

- `Lifecycle.start()` bắt đầu hoạt động.
- `Lifecycle.stop()` dừng hoạt động.
- `SmartLifecycle` bổ sung `isAutoStartup()`, `getPhase()` và callback `stop(Runnable callback)`.
- `phase` giúp xác định thứ tự start/stop giữa các lifecycle bean; khi shutdown, thành phần có phase cao hơn được dừng trước thành phần có phase thấp hơn.
- Callback trong `stop(Runnable)` phải được gọi khi thành phần đã hoàn tất dừng.

Đoạn mã thành phần minh họa:

~~~java
public final class BackgroundWorker implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        // start accepting work
    }

    @Override
    public void stop() {
        running = false;
        // stop accepting work and release running tasks
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
~~~

Đây là ví dụ minh họa contract; implementation thực tế cần thread-safe, dừng tác vụ đang chạy và có timeout phù hợp. Nếu bean còn giữ socket/file/client, có thể cung cấp destruction callback để **đóng tài nguyên sau khi đã stop**.

Không coi `stop()` và `close()` là hai tên đồng nghĩa:
- `stop()` dừng hoạt động do lifecycle quản lý.
- `close()` / destroy callback giải phóng tài nguyên mà bean sở hữu.

### 8.1. Graceful shutdown của ứng dụng web

Với ứng dụng Spring Boot web, graceful shutdown cho server là cơ chế riêng để ngừng nhận request mới và cho request hiện tại thời gian hoàn tất. Có thể cấu hình:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Timeout phải phù hợp SLA và thời gian dừng thực tế. Graceful shutdown không thay thế callback đóng database pool hoặc client do bean sở hữu; hai phần cần phối hợp để request đang xử lý không bị mất resource quá sớm.

## 9. Thứ tự hủy và quan hệ phụ thuộc

Giả sử:

~~~text
FeatureService
     |
     v
WorkerClient
     |
     v
ConnectionPool
~~~

`FeatureService` sử dụng `WorkerClient`; `WorkerClient` sử dụng `ConnectionPool`. Khi Spring biết các dependency qua injection, container có thể hủy theo thứ tự ngược dependency:
1. Dừng/hủy `FeatureService`.
2. Hủy `WorkerClient` sau khi consumer không còn dùng.
3. Cuối cùng đóng `ConnectionPool`.

Không nên đóng pool trong `FeatureService.destroy()` nếu pool thuộc `WorkerClient` hoặc auto-configuration khác. Khi nhiều bean cùng giữ reference đến một pool singleton, pool phải sống cho đến khi các consumer được dừng.

Nếu quan hệ shutdown không thể hiện qua injection, có thể xem xét `@DependsOn`, `SmartLifecycle` phase hoặc một coordinator chuyên trách. Tránh ràng buộc thứ tự bằng side effect trong constructor hoặc dựa vào thứ tự dòng trong source code.

## 10. Lỗi phổ biến khi quản lý resource của auto-configured bean

1. **Tạo resource nhưng không khai báo destruction callback.** Bean có thể tồn tại suốt đời ứng dụng; file handle, thread hoặc connection không được đóng đúng lúc.
2. **Consumer tự gọi `close()` trên bean được inject.** Có thể làm hỏng các consumer khác đang dùng chung singleton.
3. **Đóng cùng resource ở nhiều callback.** `@PreDestroy`, `DisposableBean`, `destroyMethod` và lệnh thủ công có thể khiến cleanup chạy lặp.
4. **Nghĩ prototype tự được Spring đóng.** Container không tự gọi destruction callback cho prototype sau khi giao instance cho caller.
5. **Dùng `@DependsOn` thay cho inject dependency.** Làm thứ tự khởi tạo có vẻ đúng nhưng che giấu dependency thực và không thay callback giải phóng.
6. **Đóng pool trước khi dừng worker.** Tác vụ đang chạy có thể dùng resource đã đóng; hãy dừng consumer trước.
7. **Nuốt exception trong `close()`.** Ứng dụng báo shutdown thành công trong khi file hoặc kết nối chưa được giải phóng.
8. **Chờ vô hạn khi shutdown.** Worker bị kẹt có thể làm JVM dừng rất chậm; cần timeout và chính sách interrupt/force-stop.
9. **Auto-config đóng bean do người dùng cung cấp.** Vi phạm ranh giới ownership; hãy để bean definition của user quản lý callback của bean user.
10. **Cho rằng `@ConditionalOnMissingBean` giải phóng bean cũ.** Annotation chỉ quyết định có đăng ký bean mặc định hay không; không phải cơ chế thay thế/hủy object đang tồn tại.
11. **Dùng `@Bean(destroyMethod = "")` mà không có owner khác.** Vô hiệu hóa callback suy luận nhưng không tạo ra cơ chế cleanup mới.
12. **Tạo thread hoặc executor trong constructor mà không quản lý shutdown.** Thread có thể giữ JVM sống hoặc tiếp tục truy cập dependency đã đóng.
13. **Đặt mọi cleanup vào một bean điều phối.** Khi đó thứ tự và trách nhiệm phụ thuộc khó nhìn; mỗi bean nên tự giải phóng resource nó sở hữu.
14. **Không test sau khi context đóng.** Test chỉ xác nhận bean có mặt sẽ không phát hiện resource bị rò rỉ.
15. **Nhầm shutdown hook với cleanup tức thì.** Callback chỉ chạy khi context đóng; sửa property hoặc kết thúc request không tự đóng singleton.

## 11. Checklist thiết kế trước khi phát hành starter

- [ ] Xác định bean nào thật sự sở hữu mỗi tài nguyên.
- [ ] Dùng Spring container quản lý bean có vòng đời dài; tránh tự tạo object bên ngoài container nếu không có owner rõ ràng.
- [ ] Chọn scope đúng với thời gian sống của resource.
- [ ] Khai báo `destroyMethod="close"` / `"shutdown"` hoặc destruction callback thích hợp.
- [ ] Cleanup idempotent nếu có thể; không giải phóng hai lần ngoài ý muốn.
- [ ] Đảm bảo bean consumer dừng trước resource nền.
- [ ] Dùng `SmartLifecycle` cho worker/listener cần start-stop có phối hợp.
- [ ] Khi có `@ConditionalOnMissingBean`, ghi rõ contract cho bean user thay thế và để user quản lý lifecycle bean đó.
- [ ] Không để consumer đóng dependency singleton mà nó chỉ sử dụng.
- [ ] Đặt timeout cho tác vụ shutdown có thể chờ.
- [ ] Test cả điều kiện bean có/không có và trạng thái resource sau khi context đóng.
- [ ] Kiểm tra ứng dụng dừng qua JVM shutdown hook, `context.close()` hoặc lifecycle quản lý tương ứng.
- [ ] Ghi rõ trong tài liệu bean nào được tạo tự động, khi nào được đóng, và user override phải khai báo gì.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Auto-configuration tạo singleton `HttpClient` bằng `@Bean`. Ai gọi cleanup khi Spring context đóng?  
**Đáp án:** Spring container gọi destruction callback đã đăng ký trong bean definition; auto-configuration phải khai báo callback phù hợp.

**Câu 2.** Một service được inject singleton `HttpClient`. Service có nên gọi `httpClient.close()` trong `@PreDestroy` không?  
**Đáp án:** Không nếu service chỉ là consumer. Client thuộc lifecycle của bean definition sở hữu nó; container điều phối hủy dependency.

**Câu 3.** User tự cung cấp bean thay cho bean mặc định qua `@ConditionalOnMissingBean`. Auto-configuration có phải đóng bean user không?  
**Đáp án:** Không. User configuration sở hữu cách tạo và phải khai báo lifecycle callback phù hợp; Spring container vẫn quản lý bean đó.

**Câu 4.** Một prototype bean implement `AutoCloseable`. Spring có tự gọi `close()` khi caller bỏ reference không?  
**Đáp án:** Không. Caller hoặc cơ chế quản lý riêng chịu trách nhiệm cleanup prototype.

**Câu 5.** `@DependsOn` có thay thế `@Bean(destroyMethod="close")` không?  
**Đáp án:** Không. `@DependsOn` quy định quan hệ thứ tự khởi tạo/hủy giữa bean; nó không chỉ định cách giải phóng resource.

**Câu 6.** `SmartLifecycle.stop()` có đồng nghĩa với việc đã đóng mọi file/socket/client không?  
**Đáp án:** Không. `stop()` dừng hoạt động theo lifecycle; destruction callback vẫn cần đóng tài nguyên mà bean sở hữu.

**Câu 7.** Làm thế nào chứng minh resource đã được giải phóng?  
**Đáp án:** Tạo resource trong context, quan sát nó tồn tại khi context mở, đóng context rồi kiểm tra file/connection/handle không còn tồn tại hoặc không còn hoạt động.

## 13. Kết luận và tài liệu tham khảo

Quyền sở hữu lifecycle phải rõ ngay từ lúc thiết kế auto-configuration. Bean do thư viện tạo cần có destruction contract mà Spring container thực thi; bean consumer chỉ sử dụng dependency; bean user tự cung cấp có lifecycle do cấu hình của user quyết định. Với resource có công việc nền, cần phối hợp **stop trước, destroy/close sau**. Với scope prototype, caller phải tự quản lý cleanup.

Ba nguyên tắc:
1. Tạo bean có resource thì phải xác định ai đóng resource và callback nào được container gọi.
2. Dependency được inject không đồng nghĩa với quyền sở hữu; không đóng tài nguyên của bean khác chỉ vì đang giữ reference.
3. Kiểm thử sau khi context đóng để chứng minh resource thực sự được giải phóng.

Tài liệu chính thức:
- [Spring Framework — Bean Lifecycle and Initialization/Destruction Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html).
- [Spring Framework — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html#beans-factory-lifecycle).
- [Spring Framework — Bean Scopes, including Prototype](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html).
- [Spring Framework Javadoc — SmartLifecycle](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html).
- [Spring Boot Reference — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html).
- [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)