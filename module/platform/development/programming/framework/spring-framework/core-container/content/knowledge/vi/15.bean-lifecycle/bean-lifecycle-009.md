# Suy luận `close()`, `shutdown()` và tắt suy luận bằng `destroyMethod = ""` trong Spring

## 1. Mục tiêu và vấn đề thực tế

Spring Core Container không chỉ tạo và inject bean. Khi container **thực sự sở hữu vòng đời** của bean, nó còn có thể gọi các callback hủy lúc bean được giải phóng. Với bean được khai báo bởi phương thức `@Bean`, Spring hỗ trợ một tiện ích quan trọng: **tự suy luận destroy method**. Nếu đối tượng có phương thức `close()` hoặc `shutdown()` phù hợp, container có thể đăng ký callback đó mà không cần developer ghi `@Bean(destroyMethod = "close")` hoặc `@Bean(destroyMethod = "shutdown")`.

Điều này giúp các bean quản lý tài nguyên như client, pool, executor, factory hoặc kết nối được đóng khi `ApplicationContext` kết thúc. Nhưng nó cũng có thể gây lỗi nghiêm trọng nếu bean trỏ tới **tài nguyên được chia sẻ hoặc do bên ngoài Spring sở hữu**: Spring vô tình đóng tài nguyên khiến ứng dụng/hệ thống khác đang sử dụng bị ảnh hưởng.

Để tránh tự suy luận, dùng:

```java
@Bean(destroyMethod = "")
ExternalClient externalClient() {
    return obtainExternallyManagedClient();
}
```

Đoạn mã chỉ minh họa cấu hình; `ExternalClient` và `obtainExternallyManagedClient()` giả định là API cụ thể của ứng dụng. Điều cốt lõi: **chuỗi rỗng `""` tắt inferred destroy-method của `@Bean`**, không có nghĩa nó xóa mọi lifecycle callback khác.

Bài học giải thích chính xác quy tắc suy luận, những trường hợp Spring gọi hủy, khác biệt giữa `""` và `"(inferred)"`, sự tương tác với `AutoCloseable`, `DisposableBean`, `@PreDestroy`, các scope và cách viết ví dụ quan sát được.

## 2. Giá trị mặc định của @Bean.destroyMethod

Trong Spring Framework 6.x, annotation `org.springframework.context.annotation.Bean` có thuộc tính:

```java
String destroyMethod() default "(inferred)";
```

Đây là **chữ ký rút gọn từ API**, không phải toàn bộ source code. Chuỗi đặc biệt `"(inferred)"` yêu cầu Spring tìm phương thức hủy trên **đối tượng bean** phù hợp quy tắc inference.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class ResourceConfig {
    @Bean
    ResourcePool pool() {
        return new ResourcePool();
    }
}
```

Đây là **mảnh minh họa**; giả định `ResourcePool` có method `public void close()`. Vì `@Bean` mặc định dùng `"(inferred)"`, khi singleton `pool` bị container hủy, Spring có thể gọi `pool.close()`.

Ba dạng cấu hình cần phân biệt:

| Khai báo | Ý nghĩa | Tác động |
| --- | --- | --- |
| `@Bean` | Sử dụng mặc định `destroyMethod = "(inferred)"` | Spring thử tìm callback `close`/`shutdown` hoặc hợp đồng close phù hợp |
| `@Bean(destroyMethod = "(inferred)")` | Yêu cầu suy luận một cách tường minh | Về ý nghĩa tương đương giá trị mặc định |
| `@Bean(destroyMethod = "close")` | Chỉ định tên phương thức | Spring gọi phương thức `close()` đã được cấu hình khi bean bị hủy |
| `@Bean(destroyMethod = "shutdown")` | Chỉ định tên phương thức | Spring gọi `shutdown()` theo cấu hình |
| `@Bean(destroyMethod = "cleanup")` | Chỉ định phương thức tùy chỉnh | Spring gọi `cleanup()` khi bean bị hủy |
| `@Bean(destroyMethod = "")` | Không cấu hình custom/inferred destroy method qua thuộc tính này | Không tự suy luận `close()`/`shutdown()`; các callback độc lập có thể vẫn hoạt động |

Giá trị `""` là **chuỗi rỗng thực sự**, không phải `null`, không phải một space `" "` và không phải tên method. Thông thường cũng không cần thiết đặt `initMethod = ""` để tắt suy luận hủy: `initMethod` và `destroyMethod` là hai thuộc tính với các quy tắc khác nhau.

## 3. Spring suy luận những phương thức nào?

Khi dùng chế độ mặc định `"(inferred)"`, Spring kiểm tra bean cho các phương thức hủy có signature phù hợp, đặc biệt:

- `public close()`, **không tham số**;
- `public shutdown()`, **không tham số**;
- `close()` trên các kiểu triển khai `java.io.Closeable` hoặc `java.lang.AutoCloseable`.

Hợp đồng của `AutoCloseable` yêu cầu `close()` công khai, không tham số và có thể khai báo checked exception. Bean không nhất thiết phải implements `AutoCloseable` mới được Spring gọi `close`: một phương thức công khai cùng tên và đúng signature cũng là ứng viên inference.

### 3.1. close() không cần implements AutoCloseable

```java
public class LegacyPool {
    public void close() {
        System.out.println("LegacyPool.close");
    }
}

@Configuration(proxyBeanMethods = false)
class PoolConfig {
    @Bean
    LegacyPool legacyPool() {
        return new LegacyPool();
    }
}
```

Đây là **mảnh mã minh họa**. `LegacyPool` không implements `AutoCloseable`, nhưng `close()` vẫn là ứng viên. Khi container đóng bean singleton trong điều kiện bình thường, Spring gọi `close()`.

### 3.2. shutdown() cũng là ứng viên

```java
public class BackgroundService {
    public void shutdown() {
        System.out.println("BackgroundService.shutdown");
    }
}

@Configuration(proxyBeanMethods = false)
class ServiceConfig {
    @Bean
    BackgroundService backgroundService() {
        return new BackgroundService();
    }
}
```

Đây là mảnh minh họa. Nếu không có phương thức `close()` được ưu tiên/khớp và bean đủ điều kiện suy luận, Spring nhận diện `shutdown()`. Không nên suy ra rằng method mang tên `stop()`, `terminate()`, `release()` hoặc `dispose()` cũng được tự đoán trong mọi trường hợp. Với các tên tùy chỉnh đó, hãy khai báo `destroyMethod` rõ ràng.

### 3.3. Signature phải phù hợp

```java
class InvalidInference {
    public void close(boolean force) {
        // Có tham số: không phải public no-arg close() cần tìm.
    }

    public void shutdown(String reason) {
        // Có tham số: không phải public no-arg shutdown().
    }

    private void close() {
        // Private: không phải public candidate thông thường.
    }
}
```

Đoạn trên là **anti-example** để minh họa, không phải class dùng trong chương trình chạy ở mục 6. Phương thức `close` overloaded hoặc private không làm đúng hợp đồng public no-arg inference. Nếu API chỉ cung cấp cleanup có tham số, cần viết một method adapter không tham số rồi cấu hình tường minh hoặc tổ chức bean thành wrapper quản lý lifecycle.

Khi một class có **cả** `close()` và `shutdown()`, đừng xây business logic dựa trên việc Spring sẽ gọi cả hai. Chọn một API hủy làm hợp đồng chính thức, khai báo `destroyMethod` tường minh nếu cần kiểm soát. Inference không có nghĩa “gọi tất cả method mang tên cleanup”.

## 4. Khi nào callback hủy thực sự chạy?

Việc Spring phát hiện được `close()`/`shutdown()` chưa đủ. Bean phải đang nằm trong vòng đời mà container có quyền quản lý destruction.

### 4.1. Singleton được quản lý bởi context

Ví dụ:

```java
try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext(PoolConfig.class)) {
    LegacyPool pool = context.getBean(LegacyPool.class);
    // Dùng bean.
}
// context.close() chạy do try-with-resources;
// Spring thực thi callbacks của các singleton được quản lý.
```

Đây là mảnh minh họa; phụ thuộc vào các định nghĩa `PoolConfig` và `LegacyPool` ở mục 3, đồng thời cần import `AnnotationConfigApplicationContext`. Khi `close()` trên context thực thi, Spring hủy các singleton thích hợp và phát callback.

Trong ứng dụng thực tế, `ConfigurableApplicationContext.close()`, `registerShutdownHook()` hoặc cơ chế quản lý lifecycle của môi trường chạy sẽ quyết định thời điểm close của context. **Không nên kỳ vọng Spring tự chạy callback chỉ vì chương trình đi qua cuối một hàm Java hoặc đối tượng hết reference.**

### 4.2. Prototype

Với `@Scope("prototype")`, Spring tạo và khởi tạo một bean mới mỗi lần bean được yêu cầu. Nhưng sau khi trả prototype cho caller, container **không chủ động theo dõi toàn bộ destruction lifecycle của từng prototype**.

```java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
LegacyPool temporaryPool() {
    return new LegacyPool();
}
```

Mảnh này cần import `Scope` và `ConfigurableBeanFactory`. Dù `LegacyPool` có public `close()` và method `@Bean` dùng mặc định `"(inferred)"`, caller **không được mặc định kỳ vọng Spring tự close từng prototype khi context shutdown**. Caller cần chủ động đóng tài nguyên.

### 4.3. Request/session/custom scope

Ở các scope khác, cleanup phụ thuộc vòng đời và khả năng thực thi destruction callbacks của **scope implementation**. Một custom scope có thể không hỗ trợ callback hủy; vì vậy `@Bean(destroyMethod = "close")` không tạo được phép màu nếu scope không có điểm teardown.

### 4.4. Bean được dùng chung bên ngoài

Nếu một đối tượng là shared resource do JNDI, ứng dụng khác hoặc hạ tầng bên ngoài nắm quyền sở hữu, điều kiện “Spring có thể nhìn thấy method `close()`” **không đồng nghĩa** “Spring có quyền đóng resource đó”. Đây là trường hợp điển hình cần `destroyMethod = ""`.

## 5. destroyMethod="" tác động chính xác tới những gì?

`@Bean(destroyMethod = "")` vô hiệu hóa suy luận qua thuộc tính `@Bean.destroyMethod`, kể cả trường hợp lớp triển khai `AutoCloseable`/`Closeable`. Tuy nhiên:

- `@PreDestroy` là một lifecycle callback được annotation processor xử lý độc lập.
- `DisposableBean.destroy()` là hợp đồng callback hủy của Spring, cũng được xử lý độc lập.
- Custom bean post-processors hoặc cơ chế quản lý scope/container bên ngoài có thể có cleanup riêng.
- Việc một đối tượng **tự được đóng bởi code khác** không bị chặn bởi giá trị của annotation.

Bảng minh họa:

| Bean thực tế có | `@Bean` mặc định | `@Bean(destroyMethod = "")` |
| --- | --- | --- |
| Chỉ `public close()` | Có thể gọi `close()` lúc destroy | Không tự suy luận gọi `close()` |
| Chỉ `public shutdown()` | Có thể gọi `shutdown()` lúc destroy | Không tự suy luận gọi `shutdown()` |
| Implements `AutoCloseable`, chỉ có `close()` | `close()` được nhận diện | Không tự suy luận gọi `close()` |
| Có `@PreDestroy void cleanup()` | Callback `@PreDestroy` được xử lý | `@PreDestroy` vẫn được xử lý |
| Implements `DisposableBean` | Spring gọi `destroy()` theo giao diện | Spring vẫn gọi `destroy()` |
| Có method `cleanup()` không annotate | Không được suy luận từ tên tùy ý | Không được suy luận từ tên tùy ý |
| Prototype giữ tài nguyên | Init chạy khi tạo; destroy thường do caller quản lý | Caller vẫn phải quản lý destroy |

Điểm quan trọng nhất: **“Tắt inference” không phải “tắt toàn bộ destruction”.** Nếu mục đích là giữ tài nguyên external không bị đóng, bạn phải kiểm tra cả `@PreDestroy`, `DisposableBean`, các hooks khác và logic đóng thủ công.

## 6. Ví dụ Java 17+ hoàn chỉnh: so sánh sáu cơ chế

Chương trình dưới đây chứng minh bằng **kết quả quan sát được**:

1. Bean có `close()` được suy luận mặc định.
2. Bean có `shutdown()` được suy luận mặc định.
3. Bean có `close()` nhưng `destroyMethod = ""` thì không bị Spring tự close.
4. Custom destroy method khác tên được gọi khi cấu hình tường minh.
5. `DisposableBean.destroy()` **vẫn chạy** dù `destroyMethod = ""`.
6. `@PreDestroy` **vẫn chạy** dù `destroyMethod = ""`.
7. Prototype đã được lấy từ container không tự được destroy khi context đóng.

Dự án tối thiểu:

```text
destroy-inference-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/DestroyInferenceDemo.java
```

### settings.gradle

```groovy
rootProject.name = 'destroy-inference-demo'
```

### build.gradle

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
    implementation 'jakarta.annotation:jakarta.annotation-api:2.1.1'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'DestroyInferenceDemo'
}
```

### src/main/java/DestroyInferenceDemo.java

```java
import java.util.ArrayList;
import java.util.List;

import jakarta.annotation.PreDestroy;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

public class DestroyInferenceDemo {

    private static final List<String> EVENTS = new ArrayList<>();

    public static final class CloseResource implements AutoCloseable {
        private final String name;

        public CloseResource(String name) {
            this.name = name;
        }

        @Override
        public void close() {
            EVENTS.add("close:" + name);
        }
    }

    public static final class ShutdownResource {
        private final String name;

        public ShutdownResource(String name) {
            this.name = name;
        }

        public void shutdown() {
            EVENTS.add("shutdown:" + name);
        }
    }

    public static final class CustomResource {
        public void release() {
            EVENTS.add("release:explicit");
        }
    }

    public static final class DisposableResource
            implements DisposableBean, AutoCloseable {

        @Override
        public void destroy() {
            EVENTS.add("destroy:contract");
        }

        @Override
        public void close() {
            EVENTS.add("close:disposable");
        }
    }

    public static final class AnnotatedResource implements AutoCloseable {
        @PreDestroy
        public void beforeDestroy() {
            EVENTS.add("preDestroy:annotation");
        }

        @Override
        public void close() {
            EVENTS.add("close:annotated");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public CloseResource inferredClose() {
            return new CloseResource("inferred");
        }

        @Bean
        public ShutdownResource inferredShutdown() {
            return new ShutdownResource("inferred");
        }

        @Bean(destroyMethod = "")
        public CloseResource externalOwned() {
            return new CloseResource("external");
        }

        @Bean(destroyMethod = "release")
        public CustomResource explicitRelease() {
            return new CustomResource();
        }

        @Bean(destroyMethod = "")
        public DisposableResource contractStillRuns() {
            return new DisposableResource();
        }

        @Bean(destroyMethod = "")
        public AnnotatedResource annotationStillRuns() {
            return new AnnotatedResource();
        }

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public CloseResource prototypeResource() {
            return new CloseResource("prototype");
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            // Tạo ít nhất một prototype; caller chưa tự close nó.
            context.getBean("prototypeResource", CloseResource.class);

            System.out.println("eventsBeforeClose=" + EVENTS.size());
        } // Context tự đóng, chạy destruction callbacks của singletons.

        EVENTS.stream().sorted().forEach(System.out::println);
    }
}
```

Chạy (Gradle 8+, JDK 17+):

```bash
gradle run --quiet
# Hoặc ./gradlew run --quiet nếu dự án đã tạo wrapper.
```

**Các dòng chương trình in từ `System.out`**:

```text
eventsBeforeClose=0
close:inferred
destroy:contract
preDestroy:annotation
release:explicit
shutdown:inferred
```

Thứ tự các dòng **sau `eventsBeforeClose=0` đã được sắp xếp** bằng `stream().sorted()` để output không phụ thuộc thứ tự phá hủy nhiều bean singleton không có quan hệ dependency với nhau. Đó là một kỹ thuật quan trọng khi xây ví dụ hoặc test: thứ tự các bean bị hủy **khác** với thứ tự callback bên trong **một bean**.

Giải thích từng trường hợp:

- `inferredClose`: Spring nhìn thấy `CloseResource implements AutoCloseable` có `close()`; log `close:inferred`.
- `inferredShutdown`: Spring nhận diện `public shutdown()`; log `shutdown:inferred`.
- `externalOwned`: dù cùng `CloseResource`, bean này ghi `destroyMethod = ""`; **không có** log `close:external`.
- `explicitRelease`: method `release()` không phải tên được tự suy luận; cấu hình `destroyMethod = "release"` khiến log `release:explicit` xuất hiện.
- `contractStillRuns`: `DisposableResource implements DisposableBean`; log `destroy:contract` vẫn xuất hiện, nhưng **không có** `close:disposable` vì đã tắt inferred close.
- `annotationStillRuns`: phương thức `@PreDestroy` vẫn được gọi; log `preDestroy:annotation`, nhưng **không có** `close:annotated`.
- `prototypeResource`: đã được lấy từ container nhưng không tự được Spring destroy; **không có** `close:prototype`.

Nếu bỏ cấu hình `destroyMethod = ""` trên `externalOwned`, bean đó sẽ xuất hiện trong danh sách destruction callbacks và được `close()`. Nếu thay bằng `@Bean(destroyMethod = "close")` thì Spring cũng dùng explicit close hook.

## 7. Khi một bean kết hợp nhiều callback hủy

Spring cho phép một bean có đồng thời:

- `@PreDestroy`;
- `DisposableBean.destroy()`;
- Một custom destroy method cấu hình tại bean definition (bao gồm method inferred).

Với **các phương thức khác nhau** và container thực thi destruction của bean, thứ tự tổng quát trong cùng bean là:

```text
@PreDestroy
   ↓
DisposableBean.destroy()
   ↓
custom destroy-method (ví dụ close, shutdown, cleanup)
```

Đây là thứ tự quy định cho **các lifecycle callbacks trong cùng một bean**. Đừng nhầm với thứ tự bean A và bean B được hủy: chuyện đó phụ thuộc dependency graph, container implementation và các quan hệ lifecycle khác.

Nếu cùng một method được Spring phát hiện qua nhiều cơ chế, container có logic tránh gọi lifecycle method trùng một cách máy móc. Dù vậy, không nên trộn `DisposableBean.destroy()` với một custom method khác cũng gọi lại `destroy()` bên trong vì ứng dụng tự gọi chồng hoàn toàn có thể gây side effect hai lần.

Khi bean implement `DisposableBean`, Spring nhận diện hợp đồng `destroy()` độc lập với `@Bean.destroyMethod`. Việc vô hiệu inference **không xóa method `destroy()` do giao diện Spring yêu cầu**. Tương tự, `@PreDestroy` được hỗ trợ bởi `DestructionAwareBeanPostProcessor`; callback đó không biến mất do một thuộc tính của `@Bean`.

### Khi @PreDestroy lại chủ động gọi close()

```java
@PreDestroy
void cleanup() {
    close();
}
```

Mảnh này minh họa một class có method `close()` tự định nghĩa. Dù bean có `@Bean(destroyMethod = "")`, phương thức `cleanup()` vẫn chạy và **code của chính bạn vẫn gọi `close()`**. Nếu có external ownership, cần rà soát cả method body chứ không chỉ annotation.

## 8. Phân biệt initMethod và destroyMethod

`@Bean` có cả `initMethod` và `destroyMethod`. Tuy cùng nhận tên method nhưng **thời điểm và default khác nhau**:

| Thuộc tính | Default thông dụng | Khi nào gọi? | Có tự suy luận close/shutdown? |
| --- | --- | --- | --- |
| `initMethod` | `""` | Lúc bean được khởi tạo sau bước dependency injection và các init callbacks trước đó | Không |
| `destroyMethod` | `"(inferred)"` | Lúc container quản lý hủy bean | Có, khi phù hợp |

Ví dụ:

```java
@Bean(initMethod = "connect", destroyMethod = "close")
Client client() {
    return new Client();
}
```

Đây là mảnh minh họa; class `Client` cần có phương thức `connect()` và `close()` phù hợp. Mục tiêu:

- `connect()` chạy khi Spring hoàn tất init của bean theo lifecycle.
- `close()` chạy khi Spring hủy bean singleton/container-owned đúng thời điểm.
- Không được suy ra `connect()` tự bị gọi nếu bỏ `initMethod = "connect"` chỉ vì method tên là `connect`.

Nếu mục tiêu là tắt inferred destroy, cần **chính xác**:

```java
@Bean(destroyMethod = "")
Client externalClient() {
    return externalClientFromRegistry();
}
```

Mảnh ví dụ trên giả định client lấy từ một registry có lifecycle bên ngoài.

## 9. Phân biệt @Bean và các cách đăng ký bean khác

### 9.1. @Bean methods

`@Bean` có default `destroyMethod = "(inferred)"`. Đây là cơ chế được bài học nhấn mạnh, áp dụng ở Java configuration.

### 9.2. Component scanning

Một bean đăng ký bởi `@Component` có thể được container xử lý destruction qua `@PreDestroy` hoặc `DisposableBean` và những hợp đồng đặc biệt khác. Nhưng **không nên sao chép máy móc mệnh đề “mọi component scan bean đều có @Bean(destroyMethod='(inferred)')”**, vì `@Component` không có thuộc tính `destroyMethod`.

Nếu yêu cầu cụ thể “không cho container gọi close theo suy luận”, hãy kiểm tra **loại bean definition và ownership thực sự** thay vì đặt `@Bean(destroyMethod = "")` lên một method không tạo bean đó. Với bean trả về bởi `@Bean`, dùng annotation ở factory method là cách trực tiếp.

### 9.3. XML configuration

Trong XML, có cơ chế `destroy-method` của từng `<bean>` và `default-destroy-method` trên `<beans>`. Giá trị đặc biệt `(inferred)` cũng có thể dùng để bật inference.

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="pool"
          class="example.ResourcePool"
          destroy-method="(inferred)"/>

</beans>
```

Đây là XML minh họa, cần class `example.ResourcePool` thật. Không giả định mọi khai báo XML không có `destroy-method` đều có cùng default như `@Bean`. Muốn inference trong XML thì cấu hình rõ ràng theo cơ chế XML áp dụng.

### 9.4. Programmatic bean definitions

Đăng ký `RootBeanDefinition` hoặc bean factory bằng code cũng có thể khai báo destroy method hoặc inferred mode. Nhưng cách thiết lập phụ thuộc API bean definition cụ thể, khác với annotation `@Bean`. Để giữ bài học sát mục tiêu, chỉ cần nhớ rằng **inference xuất phát từ metadata của bean definition**, không phải một special method Java luôn tự gọi khi garbage collector hoạt động.

## 10. Tắt inference khi bean không thuộc sở hữu của context

Tình huống sử dụng `destroyMethod = ""` rõ ràng nhất là **borrowed resource**:

- Client/pool được lấy từ JNDI do application server sở hữu.
- Shared executor được quản lý bởi hạ tầng khác.
- Đối tượng singleton đến từ global registry của một thư viện, được nhiều container dùng chung.
- Resource wrapper trả về từ nhà cung cấp có lifecycle riêng.
- Bean façade chỉ cung cấp reference tới external service/client đã được khởi tạo và quản lý bên ngoài.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class ExternalResources {
    @Bean(destroyMethod = "")
    SharedConnectionPool sharedPool(ExternalPoolRegistry registry) {
        return registry.getSharedPool();
    }
}
```

Mảnh này cần import `Configuration`/`Bean` và các kiểu `SharedConnectionPool`/`ExternalPoolRegistry` do ứng dụng định nghĩa. Nếu `SharedConnectionPool` có `close()`, không nên để container bất ngờ gọi method đó vào lúc một trong nhiều context bị đóng, trong khi các bên còn lại vẫn đang dùng chung pool.

**Quy tắc ownership:**

- **Spring sở hữu tài nguyên** và là nơi tạo/quyết định teardown: để inferred callback hoạt động hoặc dùng explicit destroy method.
- **Ứng dụng nhận resource mượn từ bên ngoài**: cân nhắc `destroyMethod = ""` và kiểm tra tất cả callback khác.
- **Caller tạo prototype và nhận quyền sở hữu:** caller phải tự close.
- **Có nhiều owner tiềm năng:** xác định rõ một owner chịu trách nhiệm close; tránh đóng nhiều lần hoặc quá sớm.

Không dùng `destroyMethod = ""` chỉ để loại bỏ thông báo lỗi ở shutdown nếu thực tế pool/socket/executor đang cần cleanup. Điều đó có thể biến một lỗi cấu hình thành resource leak khó phát hiện.

## 11. So sánh tắt inference với tự đóng bằng AutoCloseable

Một bean implements `AutoCloseable` không có nghĩa Spring có quyền đóng đối tượng đó ở mọi trường hợp. `AutoCloseable` chỉ xác định **API đóng**, còn lifecycle ownership tùy thiết kế.

### Tài nguyên do Spring sở hữu

```java
@Bean
MySocketClient ownedClient() {
    return new MySocketClient();
}
```

Giả định `MySocketClient implements AutoCloseable`. Mặc định inference giúp context thực thi cleanup khi hủy singleton. Nên để Spring đóng nếu bean chỉ tồn tại trong context và không còn ai dùng sau shutdown.

### Tài nguyên được mượn

```java
@Bean(destroyMethod = "")
MySocketClient borrowedClient(ResourceRegistry registry) {
    return registry.borrowSharedClient();
}
```

Container chỉ quản lý **bean reference**, không nên quyết định close cho client được mượn. Tuy nhiên, nếu bean có `@PreDestroy` hoặc `DisposableBean` tự đóng client, vẫn cần sửa mã/hợp đồng ownership tương ứng.

### Prototype dùng try-with-resources

```java
try (MySocketClient oneTaskClient = context.getBean(MySocketClient.class)) {
    oneTaskClient.send();
}
```

Mảnh này giả định bean phù hợp được cấu hình prototype và implements `AutoCloseable`. Caller chủ động đóng đúng ranh giới công việc. Tránh đặt cùng reference vào một singleton chia sẻ rồi đóng từ nhiều caller nếu lifecycle không được thiết kế để dùng chung.

## 12. Lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân khả dĩ | Cách kiểm tra/sửa |
| --- | --- | --- |
| `close()` được gọi dù không ghi `destroyMethod` | `@Bean` mặc định `"(inferred)"` và class có public no-arg `close` hoặc `AutoCloseable` | Đối chiếu bean definition; nếu resource bên ngoài sở hữu, dùng `destroyMethod = ""` |
| `shutdown()` chạy khi context đóng | Bean có public no-arg `shutdown()` và inference đang bật | Nếu Spring là owner, hành vi có thể đúng; nếu không, tắt inference |
| `close(boolean)` không được Spring gọi | Method có tham số, không khớp no-arg signature | Tạo adapter no-arg hoặc explicit lifecycle logic |
| `release()` không được gọi | Tên `release` không phải ứng viên inference tiêu chuẩn | `@Bean(destroyMethod = "release")` |
| Đã ghi `destroyMethod = ""` nhưng `destroy()` vẫn chạy | Bean implements `DisposableBean` | Đây là callback độc lập; sửa hợp đồng ownership/lifecycle |
| Đã ghi `destroyMethod = ""` nhưng `@PreDestroy` vẫn chạy | Annotation lifecycle độc lập | Rà soát `@PreDestroy` và phương thức nó gọi |
| Inferred cleanup không chạy trên prototype | Container không tự theo dõi destruction của từng prototype được cấp cho caller | Caller chủ động cleanup |
| Context không đóng nhưng bean vẫn sống | Không có lifecycle termination của container | Đóng context đúng cách, dùng shutdown hook/môi trường quản lý |
| Bean external bị đóng khiến dịch vụ khác lỗi | Chia sẻ resource nhưng không tắt callback Spring | Xác định một owner duy nhất; đặt `destroyMethod = ""` và rà soát callback độc lập |
| Method hủy ném exception | Cleanup thực thi thất bại; có thể ảnh hưởng quá trình shutdown và để lại tài nguyên chưa release | Xem root cause, ghi log hữu ích, thiết kế cleanup an toàn và idempotent |
| Hai callback hủy đều gọi `close()` | Code user tự chồng `@PreDestroy` với explicit/inferred close | Phân phối trách nhiệm rõ ràng, tránh gọi lại cùng thao tác |
| Test không thấy callback của Spring | Test khởi tạo đối tượng qua `new` hoặc không đóng context | Khởi tạo qua Spring và gọi `context.close()`/try-with-resources |
| Tắt inference trên nhầm bean | Cấu hình `@Bean` không phải bean definition thực sự đang được dùng | Kiểm tra bean name, class, context, qualifier và nguồn registration |

## 13. Kiểm thử lifecycle mà không phụ thuộc thứ tự bean bị hủy

Khi viết test, nên kiểm tra **sự xuất hiện/vắng mặt của sự kiện** chứ không khẳng định thứ tự toàn bộ singleton được destroy nếu không có dependency order rõ ràng.

Ví dụ ý tưởng JUnit 5:

```java
assertTrue(events.contains("close:inferred"));
assertTrue(events.contains("shutdown:inferred"));
assertTrue(events.contains("destroy:contract"));
assertTrue(events.contains("preDestroy:annotation"));

assertFalse(events.contains("close:external"));
assertFalse(events.contains("close:disposable"));
assertFalse(events.contains("close:annotated"));
assertFalse(events.contains("close:prototype"));
```

Đây là **mảnh assertion minh họa**, giả định biến `events` và các static import của JUnit đã có. Không phải lớp test đầy đủ.

Đối với nhiều callback trên **cùng bean**, có thể ghi log thành danh sách theo thứ tự và assert `@PreDestroy` xảy ra trước `DisposableBean.destroy`, rồi tới method được cấu hình. Trong ví dụ mục 6, các callback nằm ở các bean khác nhau, nên `sorted()` chỉ giúp output xác định khi trình bày.

Các kịch bản hữu ích để kiểm thử:

1. Một bean chỉ có public `close()`, không implements interface.
2. Một bean chỉ có public `shutdown()`.
3. Một bean `AutoCloseable` dùng inferred/default.
4. Cùng bean đó chuyển thành `@Bean(destroyMethod = "")`.
5. Một bean vừa implements `DisposableBean` vừa có `close()`.
6. Một bean có `@PreDestroy`.
7. Bean bị lấy từ prototype scope rồi đóng context.
8. Bean lấy từ external registry đã bị đóng ở context nào khác hay chưa.
9. Cleanup bị lỗi hoặc gọi nhiều lần: resource có trạng thái idempotent không?

**Tách kiểm thử unit và integration**: unit test có thể gọi `close()` trực tiếp để kiểm tra nội bộ class, nhưng muốn kiểm thử Spring có **suy luận và gọi method** thì cần dựng/đóng ApplicationContext thật.

## 14. Lưu ý khi áp dụng cho executor, connection pool và dịch vụ nền

Với executor hoặc thread pool, `shutdown()` có thể là bước bắt đầu ngừng nhận công việc mới, trong khi chờ các task hoàn thành có thể cần thêm `awaitTermination` hoặc cơ chế stop có kiểm soát. Inference chọn một method `shutdown()` **không bảo đảm mọi task đã dừng, mọi thread đã join hoặc mọi request đang xử lý đã hoàn tất**.

Tương tự:

- `close()` của database pool có thể đóng kết nối; cần đảm bảo traffic đã ngừng và giao dịch đang xử lý được phối hợp.
- `close()` của HTTP client có thể giải phóng sockets; không đóng trước khi background job hoàn thành.
- `shutdown()` của message consumer có thể yêu cầu ack/flush; cần phân biệt đóng tài nguyên với drain workload.
- `SmartLifecycle.stop()` và `phase` thuộc orchestration của lifecycle; có thể thực thi ở giai đoạn stop trước việc hủy singleton, nhưng không làm mất vai trò của inferred destroy callback cuối vòng đời.

Nếu ứng dụng cần graceful shutdown phức tạp, chỉ một callback inferred có thể **không đủ**. Thiết kế rõ các bước stop accepting → finish/drain tasks → close resources, kiểm thử startup/shutdown thực tế và chọn `Lifecycle`/`SmartLifecycle` khi thích hợp. Dùng `destroyMethod = "shutdown"` nếu tên API đích rõ ràng; đừng dựa trên inference trong hệ thống mà thứ tự shutdown có ảnh hưởng độ tin cậy.

## 15. Checklist trước khi bật hoặc tắt inference

- Bean thật sự được tạo bởi phương thức `@Bean` hay một registration mechanism khác?
- Giá trị `@Bean.destroyMethod` đang là mặc định `"(inferred)"`, explicit name hay `""`?
- Class runtime có `public close()`, `public shutdown()` hoặc implements `Closeable`/`AutoCloseable` không?
- Bean được quản lý bởi scope nào? Với prototype, ai chịu trách nhiệm close?
- Tài nguyên được Spring tạo và sở hữu hoàn toàn, hay mượn từ JNDI, shared registry, pool ngoài?
- Có `@PreDestroy` hoặc `DisposableBean.destroy()` vẫn được kích hoạt dù `destroyMethod = ""` không?
- Có logic custom callback tự gọi `close()`/`shutdown()` hoặc đóng resource từ nơi khác không?
- Context có được đóng đúng cách không? Có shutdown hook/môi trường quản lý tương ứng không?
- Cleanup có thực hiện đúng thứ tự với workload đang chạy không?
- Đã kiểm thử cả trường hợp callback chạy **một lần**, không chạy khi external-owned, và shutdown thất bại chưa?

## 16. Nguồn đọc thêm chính thức

1. [Spring Framework Reference — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): mặc định phát hiện `close`/`shutdown`, cơ chế vô hiệu `destroyMethod = ""` và ví dụ tài nguyên được quản lý từ bên ngoài.
2. [Spring Framework Reference — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): hủy singleton, `DisposableBean`, inferred destroy method, XML `(inferred)` và `AutoCloseable`.
3. [Spring Framework 6.2 Javadoc — @Bean](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/Bean.html): default `destroyMethod = "(inferred)"`, method signatures, điều kiện lifecycle của bean.
4. [Spring Framework Reference — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): vì sao prototype không có destruction lifecycle do container tự quản lý sau khi bàn giao bean.
5. [Maven Central — spring-context 6.2.18](https://central.sonatype.com/artifact/org.springframework/spring-context/6.2.18): dependency Spring Framework dùng trong ví dụ.

Quy tắc sử dụng: **để inferred destruction hoạt động khi Spring sở hữu tài nguyên; cấu hình `@Bean(destroyMethod = "")` khi Spring chỉ mượn tài nguyên có phương thức đóng; đồng thời kiểm tra riêng `@PreDestroy` và `DisposableBean` vì hai callback này không bị tắt bởi chuỗi rỗng.**
