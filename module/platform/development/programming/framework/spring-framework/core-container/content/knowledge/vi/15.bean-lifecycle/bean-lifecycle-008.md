# Callback @PreDestroy, DisposableBean và destroyMethod trong Spring Framework

## Mục tiêu

Spring IoC container không chỉ tạo và inject bean. Khi vòng đời của bean kết thúc, container còn có thể gọi các **destruction callbacks** để bean đóng tài nguyên đã sở hữu: kết nối mạng, file handle, thread pool, listener, buffer hoặc client bên ngoài. Ba cách cấu hình quan trọng là `@PreDestroy`, `org.springframework.beans.factory.DisposableBean` và **custom destroy method** trên bean definition, thường thấy dưới dạng `@Bean(destroyMethod = "close")`.

Bài học thuộc phần **Vòng đời bean** của Spring Framework Core Container. Sau khi học, bạn sẽ biết cách chọn callback, hiểu thứ tự chạy khi kết hợp, dùng đúng với các scope, cấu hình shutdown và tránh lỗi rò rỉ tài nguyên. Ví dụ chính sử dụng **Java 17 và Spring Framework 6**, có thể chạy với Maven và cho stdout xác định.

## 1. Destruction callback là gì?

Mỗi bean có một vòng đời do container và scope quyết định. Với một singleton thông thường:

~~~text
Đọc BeanDefinition
       ↓
Tạo instance, inject dependencies
       ↓
Initialization callbacks:
  @PostConstruct → InitializingBean.afterPropertiesSet()
                 → @Bean(initMethod="...") (nếu có)
       ↓
Bean phục vụ ứng dụng
       ↓
ApplicationContext đóng hoặc bean bị hủy
       ↓
Destruction callbacks:
  @PreDestroy → DisposableBean.destroy()
              → custom destroy method (nếu có)
       ↓
Giải phóng tài nguyên và ngừng dùng bean
~~~

Đây là sơ đồ khái quát cho lifecycle. Thực tế Spring còn dùng `BeanPostProcessor`, quản lý scope, proxy, dependency graph và startup/shutdown phases.

**Không đồng nhất destruction callback với Java garbage collection**: `@PreDestroy` không phải finalizer và không chạy mỗi khi một object hết tham chiếu. Chỉ khi Spring hoặc scope có trách nhiệm quản lý bean thực sự kích hoạt destruction lifecycle thì các callback thích hợp mới được gọi. Với object tự `new` bên ngoài container, Spring không có trách nhiệm lifecycle.

**Không đồng nhất destroy với rollback hay nghiệp vụ cuối cùng bắt buộc hoàn tất.** Khi JVM bị dừng cưỡng bức, process crash hoặc máy mất điện, callback không được bảo đảm chạy. Các yêu cầu bền vững dữ liệu cần commit/recovery độc lập với shutdown.

### Ví dụ về resource cần đóng

Một client dùng riêng cho bean có thể cần `client.close()`; một background poller cần dừng nhận việc, chờ các tác vụ còn chạy và giải phóng executor; một object đã đăng ký callback với thư viện khác cần unregister. Ngược lại, nếu resource thuộc quyền sở hữu của container khác hoặc là client dùng chung, việc tùy tiện đóng nó trong bean này có thể khiến các bean khác lỗi. Luôn xác định **resource ownership** trước khi viết callback.

## 2. So sánh ba cách khai báo

| Cơ chế | Cách sử dụng | Khi nào nên chọn? | Phụ thuộc của class vào Spring |
| --- | --- | --- | --- |
| `@PreDestroy` | Annotation trên instance method | Class ứng dụng cần cleanup và do Spring quản lý | Không phụ thuộc `DisposableBean`; dùng Jakarta annotation |
| `DisposableBean` | Implement interface, override `destroy()` | Infrastructure bean được thiết kế phụ thuộc Spring | Có, qua `org.springframework.beans.factory.DisposableBean` |
| Custom `destroyMethod` | Chỉ định method trong `@Bean` hoặc XML | Resource thuộc thư viện bên ngoài, không sửa được class | Không cần, vì metadata nằm ở configuration |
| Inferred method | Spring tự dò `close()/shutdown()` cho `@Bean` thích hợp | Bean từ thư viện có API close chuẩn | Không cần |

Các cơ chế không loại trừ nhau. Cùng một bean có thể dùng cả ba, nhưng nếu chỉ cần một thao tác cleanup, thường chỉ nên chọn **một cơ chế rõ ràng** để giảm rủi ro gọi trùng và giúp maintenance dễ hơn.

## 3. @PreDestroy: khai báo trong class

Với Spring Framework 6+ và Spring Boot 3+, import:

~~~java
import jakarta.annotation.PreDestroy;
~~~

Ví dụ một bean ứng dụng:

~~~java
package demo;

import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class MetricsBuffer {
    private boolean closed;

    public void append(String event) {
        if (closed) {
            throw new IllegalStateException("Buffer is closed");
        }
        // Ghi event vào buffer thật của ứng dụng.
    }

    @PreDestroy
    public void cleanup() {
        if (!closed) {
            closed = true;
            // Flush rồi đóng buffer do bean này sở hữu.
        }
    }
}
~~~

Đây là **class minh họa**, chưa phải một ứng dụng độc lập; cần application context quét package `demo` để Spring đăng ký bean và xử lý annotation. Spring thường phát hiện `@PreDestroy` bằng `CommonAnnotationBeanPostProcessor` (thuộc nhóm destruction-aware processors được container sử dụng khi hủy).

### Method nên có hình thức nào?

- Dùng một method **instance**, **không tham số**, **trả về void**.
- Có thể là method không public nếu reflection access hợp lệ; với Java module system cần lưu ý mở package khi thích hợp.
- Không tạo thêm bean mới trong lúc container đang đóng.
- Không dùng callback để khởi chạy luồng xử lý nghiệp vụ mới.
- Nên idempotent nếu cùng resource còn được đóng từ đường khác.
- Cleanup nên chạy nhanh, có timeout cho network I/O và không block vô thời hạn.

Trên những dự án cũ dùng Spring Framework 5.x, annotation có thể được import từ `javax.annotation.PreDestroy`. Với Spring 6+, Jakarta là namespace đúng. Đừng trộn `javax.annotation` cũ với `jakarta.annotation` mới.

### @PreDestroy khác @PostConstruct ra sao?

`@PostConstruct` chạy **sau khi inject dependencies và trước khi bean được dùng bình thường**; `@PreDestroy` chạy trong quá trình container/scope hủy bean. Cả hai là callback ở những giai đoạn khác nhau. `@PreDestroy` không tự động được gọi khi bạn gọi trực tiếp một phương thức nghiệp vụ có tên `close()`.

## 4. DisposableBean.destroy(): interface chuyên biệt của Spring

Giao diện Spring có hợp đồng:

~~~java
package org.springframework.beans.factory;

public interface DisposableBean {
    void destroy() throws Exception;
}
~~~

Đây là chữ ký rút gọn của API để giải thích, không phải file cần tự tạo.

Ví dụ class implement interface:

~~~java
package demo;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.stereotype.Component;

@Component
public class BackgroundSession implements DisposableBean {
    private boolean disposed;

    @Override
    public void destroy() throws Exception {
        if (!disposed) {
            disposed = true;
            System.out.println("session disposed");
        }
    }
}
~~~

Khi bean được Spring hủy theo lifecycle phù hợp, container gọi `destroy()`. Phương thức được khai báo có thể `throws Exception`, nhưng người viết vẫn cần thiết kế error handling cho cleanup. Một exception trong shutdown không nhất thiết được propagate trở lại caller ở mọi kiểu scope/implementation; cần log có thông tin và đảm bảo các resource khác có cơ hội được giải phóng.

**Ưu điểm:** callback được diễn đạt thành contract rõ ràng; dễ nhận diện với code hạ tầng phụ thuộc Spring.

**Hạn chế:** domain class/utility class giờ phụ thuộc vào Spring API. Tài liệu Spring ưu tiên `@PreDestroy` hoặc custom method nếu muốn giảm coupling.

### DisposableBean không phải AutoCloseable

`DisposableBean.destroy()` được Spring gọi khi hủy một bean được quản lý. `AutoCloseable.close()` là Java interface, hỗ trợ `try-with-resources`. Spring có thể suy luận `close()` thành destruction method khi bean definition phù hợp, nhưng điều đó **không** biến mọi object implements `AutoCloseable` thành Spring-managed bean.

## 5. Custom destroy method thông qua bean definition

Cơ chế thứ ba cho phép class tài nguyên không cần chứa bất kỳ Spring annotation hay interface nào. Người cấu hình bean xác định method cần chạy khi hủy.

Ví dụ API client của thư viện ngoài có method `shutdown()`:

~~~java
@Configuration
public class ExternalClientConfig {
    @Bean(destroyMethod = "shutdown")
    public ExternalClient externalClient() {
        return new ExternalClient();
    }
}
~~~

Đây là **snippet minh họa**, giả định `ExternalClient` là class của thư viện có method `shutdown()`. Chèn trong một class `@Configuration` với import `org.springframework.context.annotation.Bean`, `Configuration` tương ứng.

Khi target bean được destroy, Spring gọi method `shutdown()` đã đăng ký. Nếu class của thư viện chỉ có method `close()` thì khai báo tương tự:

~~~java
@Bean(destroyMethod = "close")
public ExternalClient externalClient() {
    return new ExternalClient();
}
~~~

Trong cấu hình XML, metadata tương ứng:

~~~xml
<bean id="externalClient"
      class="example.ExternalClient"
      destroy-method="shutdown"/>
~~~

Đoạn XML là một phần của file cấu hình `<beans>`, không phải XML hoàn chỉnh. Các dự án dùng Java configuration hiện đại thường dùng `@Bean`.

### Vì sao đây là cách phù hợp cho thư viện bên thứ ba?

Với một thư viện mạng, bạn không thể sửa mã nguồn để thêm `@PreDestroy` hay `implements DisposableBean`. Nhưng bạn có thể cung cấp method factory và khai báo tên cleanup. Code thư viện vẫn giữ tính độc lập với Spring; ownership và thời điểm đóng nằm trong configuration.

## 6. Cơ chế inferred destroy method của @Bean

Với phương thức `@Bean`, giá trị mặc định `destroyMethod = "(inferred)"` cho phép Spring nhận diện một phương thức `public close()` hoặc `public shutdown()` không tham số trên bean instance khi thích hợp. Một bean implement `AutoCloseable`/`Closeable` cũng có `close()` để Spring nhận diện; việc này xảy ra khi container thực sự kiểm soát destruction lifecycle. Nó **không** có nghĩa Spring sẽ tự động đóng mọi object tạo bằng `new` hoặc mọi component có method `close()`.

Nếu resource được hệ thống khác sở hữu, có thể khai `@Bean(destroyMethod = "")` để tắt suy luận custom destroy method của bean definition đó. Cấu hình này **không tắt** `@PreDestroy` hoặc `DisposableBean.destroy()` độc lập. Nếu callback nào trực tiếp gọi `close()`, vẫn phải xem lại hợp đồng ownership.

Bài tiếp theo kiểm chứng riêng thứ tự nhận diện `close`/`shutdown`, hành vi khi tắt inference, method signatures và các ví dụ có thể chạy. Trong bài này, điều cần nhớ là **configured/inferred destroy method là một trong ba nhóm destruction hooks**, đứng sau `@PreDestroy` và `DisposableBean` khi mỗi hook là một phương thức khác nhau.

## 7. Thứ tự callbacks khi kết hợp

Khi một bean có ba callback riêng biệt, Spring thực thi theo thứ tự:

1. `@PreDestroy` method.
2. `DisposableBean.destroy()`.
3. Custom configured destroy method (ví dụ `@Bean(destroyMethod = "finish")`).

~~~text
Target được Spring quyết định hủy
       |
       v
BeanPostProcessor gọi method @PreDestroy
       |
       v
DisposableBean.destroy()
       |
       v
@Bean(destroyMethod = "finish")
       |
       v
Hoàn tất destruction lifecycle
~~~

**Đây là thứ tự của các callback bên trong cùng một bean.** Với nhiều beans, thứ tự hủy phụ thuộc quan hệ giữa bean, scope và context. Không có quy tắc rằng tất cả `@PreDestroy` của mọi beans phải chạy trước tất cả `DisposableBean.destroy()` của mọi beans.

Thứ tự trên cũng khác với các initialization callbacks (`@PostConstruct` → `InitializingBean.afterPropertiesSet()` → custom `initMethod`); đừng đảo lẫn startup và shutdown.

## 8. Ví dụ độc lập chạy với Java 17: cả ba callback trên một bean

### 8.1. Thư mục

~~~text
destroy-callback-demo/
├── pom.xml
└── src/main/java/demo/
    └── DestroyCallbackDemo.java
~~~

### 8.2. pom.xml

Ví dụ dùng Spring Framework 6.2.9 và Jakarta Annotations 2.1.1:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>destroy-callback-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>jakarta.annotation</groupId>
            <artifactId>jakarta.annotation-api</artifactId>
            <version>2.1.1</version>
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
~~~

### 8.3. src/main/java/demo/DestroyCallbackDemo.java

~~~java
package demo;

import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class DestroyCallbackDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            ManagedResource resource = context.getBean(ManagedResource.class);
            resource.use();
        }

        System.out.println("context closed");
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean(destroyMethod = "finish")
        public ManagedResource managedResource() {
            return new ManagedResource();
        }
    }

    public static class ManagedResource implements DisposableBean {
        private boolean closed;

        public ManagedResource() {
            System.out.println("resource created");
        }

        public void use() {
            if (closed) {
                throw new IllegalStateException("Already closed");
            }
            System.out.println("resource in use");
        }

        @PreDestroy
        public void beforeDestroy() {
            System.out.println("1. @PreDestroy");
        }

        @Override
        public void destroy() {
            System.out.println("2. DisposableBean.destroy()");
        }

        public void finish() {
            if (!closed) {
                closed = true;
                System.out.println("3. @Bean(destroyMethod=finish)");
            }
        }
    }
}
~~~

### 8.4. Chạy

Từ thư mục `destroy-callback-demo`:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=demo.DestroyCallbackDemo
~~~

**Stdout của chương trình** (không bao gồm thông báo của Maven nếu có):

~~~text
resource created
resource in use
1. @PreDestroy
2. DisposableBean.destroy()
3. @Bean(destroyMethod=finish)
context closed
~~~

**Giải thích kết quả:**

- `AnnotationConfigApplicationContext` đọc `AppConfig`, tạo `ManagedResource` dưới dạng singleton và đăng ký destruction metadata.
- Constructor in `resource created`. `resource.use()` in `resource in use`.
- Kết thúc khối `try` khiến `context.close()` chạy, ngay cả khi thân `try` ném exception.
- Spring gọi `beforeDestroy()` do `@PreDestroy`, tiếp theo `destroy()` qua interface `DisposableBean`, cuối cùng `finish()` từ `@Bean(destroyMethod = "finish")`.
- Chương trình in `context closed` **sau** khi `close()` hoàn tất.

Ví dụ không dùng Spring Boot hoặc HTTP server, nên stdout độc lập với request. Các method có tên khác nhau nhằm chứng minh thứ tự callback chính xác. Đoạn code đã bao gồm package, imports, tên file, nested configuration và main phù hợp Java 17+.

### 8.5. Thí nghiệm tự làm

1. Bỏ `@PreDestroy` trên `beforeDestroy()` rồi chạy lại: chỉ còn interface callback và custom method.
2. Bỏ `implements DisposableBean` và method `destroy()`: method custom vẫn được gọi khi Spring đóng singleton.
3. Thay `destroyMethod = "finish"` bằng `destroyMethod = ""`: Spring không còn gọi custom `finish()` thông qua bean definition; hai callback còn lại không bị tắt.
4. Thử dùng một class khác chỉ có public `close()` trong `@Bean` mà không ghi destroy method: quan sát tính năng inferred method.
5. Thay đoạn `try-with-resources` bằng một context được tạo nhưng không đóng: đừng kỳ vọng callback tự chạy ngay sau khi `main` hoàn tất nếu không có shutdown hook.
6. Tạo hai beans có dependency thật để quan sát thứ tự hủy giữa dependent và dependency, không chỉ thứ tự ba callback bên trong một bean.

## 9. Khi nào Spring thực sự chạy callback?

### 9.1. Singleton

Với một singleton do `ApplicationContext` tạo và quản lý, container chịu trách nhiệm destruction. Trong chương trình Java thuần, dùng:

~~~java
try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext(AppConfig.class)) {
    // Sử dụng beans.
} // context.close() được gọi tự động.
~~~

Đây là **snippet trong một method**, dựa vào `AppConfig` của ví dụ trên. Có thể gọi `context.close()` thủ công; bản thân `ConfigurableApplicationContext` còn cung cấp `registerShutdownHook()` để JVM có cơ hội đóng container khi shutdown thông thường.

Trong Spring Boot, context và shutdown hook được framework quản lý theo runtime. Khi nhận tín hiệu dừng bình thường và có đủ thời gian, Spring điều phối stop/close và destruction. Nhưng process bị dừng cưỡng bức hoặc crash không bảo đảm callback chạy. Không sử dụng destruction callbacks làm nơi duy nhất lưu dữ liệu quan trọng.

### 9.2. Prototype: không tự động destroy sau khi trả instance

Với `@Scope("prototype")`, Spring tạo và khởi tạo bean theo mỗi lần container được yêu cầu, nhưng **không giữ danh sách tất cả prototype instances đã giao cho caller để auto destroy khi ApplicationContext đóng**.

Ví dụ ý tưởng:

~~~java
@Bean(destroyMethod = "close")
@Scope("prototype")
public TempHandle tempHandle() {
    return new TempHandle();
}
~~~

Đây là snippet yêu cầu một class `TempHandle` có `close()`, import `@Scope` và Spring configuration thích hợp. Dù có metadata destroy method, **caller vẫn phải chủ động xử lý vòng đời resource của từng prototype instance**. Có thể gọi `close()` nếu caller sở hữu resource, hoặc dùng API destruction tường minh của bean factory khi muốn áp dụng Spring lifecycle hooks.

Điều này cũng đúng khi prototype được inject vào singleton: nếu chỉ inject một instance trong constructor, singleton giữ tham chiếu tới instance đó, không tự lấy prototype mới ở mỗi lời gọi. Khi cần lookup động, dùng `ObjectProvider<T>` hoặc thiết kế scoped proxy phù hợp; cleanup của target vẫn phải được quyết định.

### 9.3. Request, session và application

Trong một `WebApplicationContext` hỗ trợ web scopes, Spring lưu target request/session theo HTTP request/session. Destruction callbacks được scope phối hợp vào thời điểm target hết đời, chẳng hạn request kết thúc hoặc session bị invalidate/expire.

| Scope | Phạm vi target | Điểm kết thúc điển hình |
| --- | --- | --- |
| `request` | Một HTTP request | Spring hoàn tất vòng đời request |
| `session` | Một HTTP session | Session invalidate hoặc expire |
| `application` | Một ServletContext | Kết thúc lifecycle application/ServletContext |
| Custom scope | Do ứng dụng định nghĩa | Scope implementation quyết định |

Một scoped proxy có thể được inject vào singleton, nhưng **proxy không đồng nghĩa target**. Target request có thể được tạo và hủy trong một request trong khi singleton/proxy vẫn sống; callback áp dụng cho target theo scope, không phải mọi lần gọi method trên proxy.

### 9.4. Custom scope và destruction callbacks

Một implementation của `org.springframework.beans.factory.config.Scope` cần hỗ trợ:

~~~java
void registerDestructionCallback(String name, Runnable callback);
~~~

Spring gửi destruction callback vào scope khi bean có metadata cần dọn dẹp. Scope implementation phải lưu và **gọi callback khi target/scope kết thúc**, nếu không bean có thể bị bỏ khỏi storage nhưng resource chưa được đóng.

`Scope.remove(String name)` thường có nhiệm vụ bỏ target/callback khỏi registry và trả target về để caller có thể hủy theo trách nhiệm riêng. Nó không phải lời hứa rằng callback luôn được gọi tại `remove`. Một API custom `end()`/`closeConversation()` cần điều phối cleanup các target còn lại, bảo đảm gọi đúng một lần và giải phóng storage.

## 10. Thứ tự hủy giữa nhiều bean

Thứ tự ba callbacks là quy luật **bên trong một bean**. Giữa các bean, Spring cố gắng tôn trọng dependency: bean phụ thuộc có cơ hội cleanup **trước** bean mà nó phụ thuộc khi container hủy singleton.

Ví dụ `InvoiceService` dùng `RemoteClient`:

~~~text
Khi khởi tạo:
RemoteClient → InvoiceService

Khi đóng context:
InvoiceService cleanup
       ↓
RemoteClient cleanup
~~~

Điều này cho phép `InvoiceService` flush dữ liệu thông qua client trước khi `RemoteClient` đóng socket. Nếu mối quan hệ không được thể hiện bằng injection, có thể cần metadata phụ thuộc như `@DependsOn` (khi thật sự phù hợp), nhưng đừng lạm dụng để chỉ định thứ tự tùy ý.

Khi context đang đóng, callback không nên gọi `context.getBean()` để tạo thêm singleton mới. Các dependency có thể đang được hủy; tạo bean mới trong shutdown là thiết kế không ổn định.

### SmartLifecycle khác destruction callback

Với thành phần có background threads hoặc worker queue, việc “ngừng nhận job” có thể cần xảy ra trước khi “đóng socket”. Spring có `Lifecycle` và `SmartLifecycle` để tham gia startup/shutdown phases; shutdown thông thường sẽ xử lý stop rồi đến general bean destruction.

`SmartLifecycle.stop(Runnable)` hữu ích khi cần điều phối graceful stop có thời hạn. Sau đó `@PreDestroy` hoặc custom destroy method đóng tài nguyên còn lại. Tuy nhiên trong một số tình huống bất thường, destroy có thể được gọi mà không nhận stop callback đầy đủ; cleanup vẫn phải an toàn.

## 11. Những nguyên tắc viết cleanup đáng tin

### 11.1. Resource ownership

Chỉ đóng tài nguyên mà bean thực sự sở hữu. Nếu bean nhận từ Spring-managed singleton khác, bean cung cấp resource mới là owner điển hình; nếu object tham chiếu tới connection pool chung, đừng đóng toàn pool từ một request-scoped bean.

### 11.2. Idempotency

Một resource có thể bị đóng trực tiếp bởi ứng dụng và lại được Spring đóng khi context shutdown. Thiết kế close chịu được lời gọi lặp là an toàn hơn, khi hợp đồng resource cho phép.

~~~java
package demo;

import java.util.concurrent.atomic.AtomicBoolean;

public class SafeResource implements AutoCloseable {
    private final AtomicBoolean closed = new AtomicBoolean();

    @Override
    public void close() {
        if (!closed.compareAndSet(false, true)) {
            return;
        }
        System.out.println("closed once");
    }

    public static void main(String[] args) {
        SafeResource resource = new SafeResource();
        resource.close();
        resource.close();
    }
}
~~~

Chạy độc lập với Java 17:

~~~bash
javac -d . SafeResource.java
java demo.SafeResource
~~~

Kết quả stdout:

~~~text
closed once
~~~

File nguồn trên cần đặt tên `SafeResource.java` (dù chứa package `demo`, lệnh `javac -d .` sẽ tạo output đúng package). `AtomicBoolean` ngăn việc thực thi cleanup body lặp lại trong các lời gọi đồng thời. Nó không tự quản lý các nhiệm vụ đang sử dụng resource; với tài nguyên có in-flight requests cần cơ chế đồng bộ và quiescence thích hợp.

### 11.3. Lỗi khi dọn tài nguyên

Cleanup có thể ném exception do network hoặc I/O. Thiết kế nên có logging đủ thông tin, giới hạn thời gian và cố gắng giải phóng các resource còn lại. Không nên giả định exception trong `@PreDestroy` sẽ được ném ra caller `context.close()` theo cùng cách ở mọi Spring version/processor/scope. Trách nhiệm chính là shutdown có thể tiếp tục và lỗi được quan sát.

Ví dụ một method đóng hai resource:

~~~java
public void closeBoth(AutoCloseable first, AutoCloseable second)
        throws Exception {
    Exception failure = null;
    try {
        first.close();
    } catch (Exception ex) {
        failure = ex;
    }
    try {
        second.close();
    } catch (Exception ex) {
        if (failure == null) {
            failure = ex;
        } else {
            failure.addSuppressed(ex);
        }
    }
    if (failure != null) {
        throw failure;
    }
}
~~~

Đây là **method minh họa**, không phải class độc lập. Mục tiêu là không bỏ qua resource thứ hai chỉ vì việc đóng resource thứ nhất lỗi. Trong bean thật, cần bảo đảm thứ tự đóng và quyền sở hữu của cả hai.

### 11.4. Tránh block vô hạn

Đừng chờ `Thread.join()` vô hạn hoặc một HTTP response không có timeout từ callback hủy. Khi stop, ngừng nhận công việc, signal các threads, chờ có giới hạn; nếu có thời hạn shutdown của nền tảng triển khai, phối hợp các phase phù hợp. Callback có thể chạy trên thread đóng context, nên block sẽ kéo dài quá trình tắt ứng dụng.

### 11.5. Không dùng destructor làm nơi ghi nghiệp vụ không thể mất

Destruction callbacks không được bảo đảm chạy trong mọi cách process kết thúc. Transaction commit, outbox, durable queue và recovery phải diễn ra trong luồng nghiệp vụ hoặc hạ tầng persistence thích hợp. Callback chỉ nên đảm nhiệm cleanup và graceful shutdown.

## 12. Kiểm thử vòng đời

Một test tốt cần khiến Spring **thực sự hủy bean**, rồi kiểm tra tác dụng. Chỉ gọi trực tiếp `bean.cleanup()` không chứng minh Spring đã nhận diện annotation.

Các ca nên thử:

1. Singleton được tạo trong `AnnotationConfigApplicationContext`; callback chưa chạy trước khi đóng context và chạy sau `close()`.
2. Cùng một bean có đủ ba callbacks khác tên; xác nhận thứ tự `@PreDestroy` → `DisposableBean.destroy()` → custom method.
3. Bean `@Bean` có public `close()` và không chỉ định destroy method: xác nhận inference khi bean phù hợp.
4. `@Bean(destroyMethod = "")`: xác nhận chỉ phần inferred method bị tắt, không mất callback annotation/interface khác.
5. Prototype đã được cấp cho caller: xác nhận context close **không** tự hủy tất cả prototype targets; cleanup thuộc trách nhiệm caller.
6. Request-scoped target: trong HTTP integration test, xác nhận callback xảy ra theo request lifecycle chứ không phải vòng đời singleton proxy.
7. Error path: bean resource close thất bại; logging và cleanup các resource khác vẫn được thiết kế hợp lý.
8. Two-bean dependency: dependent cleanup trước dependency trong singleton shutdown bình thường.
9. Idempotency: đóng resource lặp không gây phá dữ liệu hoặc exception vô lý.
10. Không để context test rò rỉ; dùng try-with-resources/finally cho test tạo container riêng.

Nếu dùng Spring TestContext caching, context có thể còn sống qua nhiều test methods. Destruction của singleton **không nhất thiết chạy sau từng test method**, mà khi context thật sự bị đóng hoặc bị evict khỏi cache. Kiểm tra startup/shutdown bằng một context tường minh để giảm nhầm lẫn.

## 13. Lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân khả dĩ | Cách sửa |
| --- | --- | --- |
| `@PreDestroy` không được gọi | Object được tạo bằng `new` ngoài Spring | Giao lifecycle cho container hoặc chủ động cleanup từ owner |
| Annotation không nhận diện | Sai namespace `javax`/`jakarta`, thiếu xử lý annotation | Dùng `jakarta.annotation.PreDestroy` với Spring 6+ và context hỗ trợ |
| Không thấy callback khi main kết thúc | Context Java thuần chưa được close, không có hook | Dùng `try-with-resources` hoặc đăng ký shutdown hook |
| `@Bean` gọi `close()` dù không khai báo | Inferred destroy method mặc định | Kiểm tra ownership; dùng `destroyMethod = ""` khi có lý do hợp lệ |
| Tắt inference nhưng vẫn thấy callback | Còn `@PreDestroy` hoặc `DisposableBean` | Xem toàn bộ destruction metadata |
| Prototype không được cleanup ở context close | Spring không tự quản lý destruction cho prototype đã trả | Caller đóng tài nguyên hoặc dùng bean destruction API phù hợp |
| Method `shutdown` không chạy | Sai tên/signature, bean chưa tạo hoặc scope chưa đóng | Kiểm tra metadata, target, scope và log |
| Vẫn còn thread/socket sau khi shutdown | Cleanup chưa thực thi, không xử lý triệt để hoặc close chờ lỗi | Theo dõi resource ownership và shutdown path |
| Callback bị gọi nhiều lần qua code ứng dụng | Resource đóng cả thủ công lẫn bởi container | Idempotency và quy ước một owner |
| Thứ tự hủy resource không đúng | Không khai báo dependency thật giữa beans | Dùng injection và metadata phụ thuộc chính xác |
| Shutdown treo | Callback block, đợi thread/network vô hạn | Stop phase phù hợp, timeout và cancellation |
| Callback phụ thuộc request context rồi lỗi khi app đóng | Không có HTTP request active trong singleton shutdown | Tách dữ liệu nghiệp vụ khỏi request-bound context |
| Test không thấy destructor | Test context còn được cache | Đóng context riêng để kiểm chứng lifecycle |
| Callback không chạy khi process bị SIGKILL | OS kết thúc cưỡng bức, Spring không được chạy | Có cơ chế recovery, đừng dựa vào callback cho dữ liệu quan trọng |

### Trình tự chẩn đoán

Kiểm tra: **(1)** object có thật sự là Spring bean không; **(2)** target đã được tạo chưa; **(3)** scope nào sở hữu target; **(4)** điểm kết thúc lifecycle đã xảy ra chưa; **(5)** bean có callback metadata gì; **(6)** callback có lỗi hoặc bị timeout không; **(7)** còn ai tham chiếu hoặc sử dụng tài nguyên đã đóng không. Đừng đổi ba cơ chế một cách thử-sai mà chưa xác định nguyên nhân.

## 14. Câu hỏi tự kiểm tra

**Hỏi 1: Có thể chỉ thêm `@PreDestroy` lên một object tạo bằng `new` rồi kỳ vọng Spring tự đóng không?**  
**Đáp:** Không. Object cần thuộc Spring-managed lifecycle, hoặc caller phải tự cleanup.

**Hỏi 2: Một singleton có `@PreDestroy`, `DisposableBean.destroy()` và `@Bean(destroyMethod="finish")`. Với ba method khác tên, thứ tự là gì?**  
**Đáp:** `@PreDestroy` trước, `DisposableBean.destroy()` tiếp theo, custom `finish()` cuối cùng.

**Hỏi 3: Đặt `@Bean(destroyMethod = "")` có làm mất `@PreDestroy` không?**  
**Đáp:** Không. Nó chỉ tắt inferred custom destroy method, không vô hiệu hóa các lifecycle mechanisms khác.

**Hỏi 4: Vì sao BeanFactory không tự destroy tất cả prototype instances?**  
**Đáp:** Sau khi tạo và trả prototype target cho caller, container không tiếp tục theo dõi từng instance để dọn khi đóng context; caller có trách nhiệm cleanup.

**Hỏi 5: Có cần khai báo `destroyMethod = "close"` cho mọi `@Bean` trả về AutoCloseable không?**  
**Đáp:** Không nhất thiết. Spring `@Bean` mặc định hỗ trợ inferred close/shutdown trên bean thích hợp. Khai báo rõ có thể giúp thể hiện ownership, nhưng phải hiểu inference và không đóng resource dùng chung sai owner.

**Hỏi 6: Shutdown hook đảm bảo cleanup ngay cả khi JVM bị kill cưỡng bức chứ?**  
**Đáp:** Không. Hook có cơ hội chạy khi JVM shutdown bình thường; crash/SIGKILL không bảo đảm.

**Hỏi 7: Một request-scoped bean được inject qua proxy vào singleton. Callback target chạy khi singleton đóng hay khi request kết thúc?**  
**Đáp:** Theo lifecycle của target trong request scope; proxy singleton là đối tượng khác, không kéo dài target qua mọi request.

**Hỏi 8: Tại sao `SmartLifecycle.stop()` và `@PreDestroy` không nên bị đồng nhất?**  
**Đáp:** Stop tham gia quá trình ngừng hoạt động có điều phối của context, còn destruction callbacks chủ yếu dọn tài nguyên của bean; khi shutdown bất thường có thể không có mọi stop signal như mong đợi.

## Tài liệu tham khảo chính thức

- [Spring Framework Reference — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html), phần *Destruction Callbacks* và *Combining Lifecycle Mechanisms*.
- [Spring Framework Reference — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html), phần lifecycle theo scope.
- [Spring Framework Reference — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html), phần inferred destroy method và `destroyMethod`.
- [Spring Framework Javadoc — DisposableBean](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/DisposableBean.html).
- [Spring Framework Javadoc — Bean](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/annotation/Bean.html).
- [Jakarta Annotations — PreDestroy](https://jakarta.ee/specifications/annotations/2.1/apidocs/jakarta.annotation/jakarta/annotation/PreDestroy.html).
