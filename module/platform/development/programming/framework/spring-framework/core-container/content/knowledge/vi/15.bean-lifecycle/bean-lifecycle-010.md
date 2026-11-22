# Giải phóng tài nguyên và giới hạn callback hủy với prototype trong Spring Framework

## 1. Vấn đề: tạo prototype rất dễ, nhưng ai đóng tài nguyên?

Trong Spring Core Container, một bean có scope `prototype` được tạo mới mỗi khi container nhận yêu cầu lấy bean đó. Spring thực hiện các bước tạo object, inject dependency và **initialization callbacks**. Nhưng **sau khi giao prototype instance cho phía yêu cầu, container không tự quản lý toàn bộ vòng đời hủy của instance ấy** như với singleton.

Đây là điều đặc biệt quan trọng khi bean nắm giữ tài nguyên cần giải phóng: file handle, socket, JDBC connection, streaming session, native buffer, thread hoặc subscription. Nếu chỉ trông chờ `@PreDestroy`, `DisposableBean.destroy()`, `@Bean(destroyMethod = "...")` hay `AutoCloseable.close()` được Spring tự gọi khi context đóng, prototype có thể bị giữ tài nguyên quá lâu.

> **Quy tắc:** Với một prototype do Spring cấp, **bên nhận và sử dụng instance phải thiết kế cách kết thúc vòng đời và cleanup của chính instance đó**. Spring không tự theo dõi mọi prototype đã cấp để gọi destruction callbacks khi `ApplicationContext.close()`.

Sau bài này, bạn có thể:

- Phân biệt rõ **initialization**, **destruction callbacks** và **phạm vi trách nhiệm** của Spring với prototype.
- Biết tại sao `@PreDestroy`, `DisposableBean`, custom `destroyMethod` không được tự động gọi cho prototype chỉ vì context đóng.
- Chọn cách đóng resource bằng `AutoCloseable`/try-with-resources, `finally` hoặc một factory/use-scope quản lý ownership.
- Biết khi nào có thể chủ động gọi `ConfigurableBeanFactory.destroyBean(beanName, instance)`, nó khác `close()` trực tiếp như thế nào.
- Xử lý được prototype được inject vào singleton, ngoại lệ giữa chừng, các luồng chạy đồng thời và trường hợp prototype thực ra không cần giữ resource.
- Thử bằng ví dụ hoàn chỉnh Java 17 + Spring Context 6.1, có output chính xác và kiểm chứng vòng đời.

## 2. So sánh trách nhiệm của Spring với từng scope

Một **bean definition** mô tả cách Spring tạo và quản lý bean. Scope quyết định container cấp instance theo ranh giới nào. Vòng đời hủy không được suy ra chỉ từ việc bean implement `AutoCloseable`.

| Scope | Khi Spring tạo bean | Initialization callback | Destruction callback tự động |
| --- | --- | --- | --- |
| `singleton` | Thông thường một instance cho một bean definition/container | Chạy khi instance được tạo | Spring thường gọi khi context đóng bình thường |
| `prototype` | Mỗi yêu cầu lấy target tạo instance mới | Chạy cho từng target mới | **Không được container tự gọi sau khi giao instance** |
| `request` | Theo HTTP request | Chạy khi target của request được tạo | Scope web có thể gọi khi request kết thúc |
| `session` | Theo HTTP session | Chạy khi target của session được tạo | Scope web có thể gọi lúc session hết hạn/bị hủy |
| `application` | Theo `ServletContext` | Chạy khi target được tạo | Theo vòng đời web application |
| Custom scope | Phụ thuộc implementation | Theo quá trình tạo bean | Chỉ khi scope hỗ trợ và kích hoạt destruction callback đúng |

Bảng phản ánh cách Spring Framework quản lý scope trong môi trường phù hợp. Với web scope hoặc custom scope, việc chạy destruction callback còn phụ thuộc lifecycle của scope và shutdown bình thường. Nó không bảo đảm cleanup khi JVM bị `kill -9`, máy mất điện hay process crash.

### “Prototype không bị Spring hủy” có nghĩa chính xác là gì?

Khi gọi `context.getBean(MyPrototype.class)`, Spring vẫn thực hiện những việc phía **creation/initialization**: instantiate, dependency injection, bean post-processing và init callback. Sau khi trả object cho caller, Spring không giữ danh sách tất cả prototype để tự gọi destroy callback tương ứng lúc context đóng. Người nhận chịu trách nhiệm cleanup.

Điều này **không có nghĩa** các destruction callback vô dụng cho prototype: bạn có thể kích hoạt xử lý hủy có chủ đích bằng cơ chế Spring như `ConfigurableBeanFactory.destroyBean(beanName, instance)`, hoặc gọi phương thức đóng resource do bean cung cấp. Cần chọn đúng contract.

### Một prototype có resource khác với một prototype chỉ mang dữ liệu

- Một `CalculationContext` chỉ chứa `List`, `Map`, số đếm và cấu trúc heap thông thường thường **không cần phương thức hủy riêng**. Java garbage collector thu hồi heap khi không còn reference.
- Một `FileSession` đang giữ `InputStream`, `RandomAccessFile`, socket hoặc native handle cần **đóng tài nguyên rõ ràng**; đợi GC có thể gây cạn file descriptor, pool slot hoặc bộ nhớ native.
- Một prototype tự tạo thread hoặc executor cần chính sách stop/shutdown phù hợp; không được giả định biến Java hết scope là thread tự ngừng.

**GC không phải lifecycle callback.** Thu hồi memory và kết thúc tài nguyên hữu hạn là hai vấn đề khác nhau.

## 3. Các callback hủy: cơ chế và giới hạn

### 3.1. `@PreDestroy`

Một phương thức gắn `jakarta.annotation.PreDestroy` có thể được Spring gọi trong quá trình hủy **một bean mà lifecycle destruction thực sự được Spring xử lý**.

~~~java
import jakarta.annotation.PreDestroy;

public class ResourceOwner {
    @PreDestroy
    public void release() {
        System.out.println("release resources");
    }
}
~~~

Đây là class minh họa; muốn callback được Spring xử lý, phải đăng ký bean trong container có annotation processing. Trên Spring 6.x sử dụng `jakarta.annotation.PreDestroy`, không mặc định dùng import `javax.annotation.PreDestroy` của các ứng dụng cũ.

Nếu `ResourceOwner` là **singleton**, khi đóng context bình thường Spring có thể gọi callback. Nếu nó là **prototype đã được cấp cho caller**, đừng kỳ vọng context shutdown tự gọi callback cho instance đó.

### 3.2. `DisposableBean.destroy()`

Interface của Spring:

~~~java
import org.springframework.beans.factory.DisposableBean;

public class ResourceOwner implements DisposableBean {
    @Override
    public void destroy() {
        System.out.println("Spring destruction callback");
    }
}
~~~

Với singleton được container quản lý, Spring tự gọi `destroy()` trong pha hủy. Với prototype, việc `implements DisposableBean` **không thay đổi chính sách Spring không tự theo dõi prototype sau khi giao đi**.

Trade-off: class phụ thuộc trực tiếp vào Spring API. Với đối tượng tài nguyên có thể dùng độc lập, `AutoCloseable` thường là hợp đồng Java dễ tái sử dụng hơn.

### 3.3. Custom `@Bean(destroyMethod = "...")`

~~~java
@Configuration(proxyBeanMethods = false)
class ResourceConfiguration {
    @Bean(destroyMethod = "disconnect")
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}
~~~

Đây là đoạn cấu hình minh họa: `ExternalClient` phải có phương thức `disconnect()` không tham số, cùng các import Spring cần thiết. Tên `destroyMethod` được khai báo trên bean definition, nhưng **không làm Spring tự hủy prototype khi context đóng**.

Ưu điểm của custom destroy method: class `ExternalClient` không cần biết Spring, phù hợp với thư viện bên ngoài.

### 3.4. `AutoCloseable` và cơ chế suy luận destroy method

Với Java-config `@Bean`, Spring có thể suy luận một public no-arg `close()` hoặc `shutdown()` là destroy method khi `destroyMethod` không được chỉ định. Hành vi này hữu ích cho **singleton** do Spring toàn quyền quản lý:

~~~java
@Bean // Có thể suy luận close() cho singleton bean này.
ManagedChannel managedChannel() {
    return new ManagedChannel();
}
~~~

Nếu không muốn Spring gọi method suy luận của bean `@Bean`, có thể dùng `@Bean(destroyMethod = "")`; ví dụ khi tài nguyên thực sự do một owner bên ngoài quản lý. Tuy nhiên, điều này **không vô hiệu hóa mọi cơ chế callback khác** như `DisposableBean` nếu bean có triển khai interface đó.

Với **prototype**, dù bean được khai báo `@Bean(destroyMethod = "close")`, cơ chế suy luận hay cấu hình method chỉ quyết định **sẽ làm gì nếu destruction được chủ động kích hoạt**; nó không tạo bộ theo dõi tự hủy prototype.

## 4. Sơ đồ đầy đủ: nơi Spring dừng quản lý prototype

~~~text
Caller yêu cầu bean prototype
           |
           v
BeanFactory tạo object mới
           |
           v
Inject dependencies / properties
           |
           v
BeanPostProcessor + init callbacks
           |
           v
Trả prototype P1 cho caller
           |
           +---- Caller dùng P1 trong nghiệp vụ
           |               |
           |               v
           |        Caller chịu trách nhiệm cleanup
           |               |
           |               +-- P1.close()
           |               '-- beanFactory.destroyBean(name, P1)
           |
           '-- ApplicationContext.close()
                        |
                        +-- Hủy singleton thuộc container
                        '-- KHÔNG tự lần ra P1 để hủy
~~~

Phân biệt hai mốc:

- **Initialization boundary:** Spring tạo instance, chạy callback như `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, custom `initMethod`.
- **Ownership boundary:** Spring giao prototype cho code của caller; caller phải xác định kết thúc sử dụng và xử lý các tài nguyên của nó.

Nếu prototype được inject trực tiếp vào singleton, instance prototype có thể bị giữ trong field của singleton rất lâu. Dù singleton có vòng đời do Spring quản lý, **không có quy tắc tổng quát rằng Spring sẽ tự gọi destroy callback cho dependency prototype đó**. Chủ sở hữu singleton có thể phải chịu trách nhiệm dọn dẹp prototype mình giữ.

## 5. Ví dụ hoàn chỉnh: Spring Context 6.1, Java 17 và hai cách dọn dẹp

Chương trình sau cố tình tạo hai prototype. Prototype thứ nhất được hủy **chủ động qua BeanFactory**. Prototype thứ hai không bị Spring tự đóng khi context shutdown; caller sẽ tự gọi `close()` sau đó. Một singleton `AutoCloseable` minh họa hành vi khác biệt.

### 5.1. Cấu trúc dự án

~~~text
prototype-cleanup-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── cleanup/
                        └── PrototypeCleanupDemo.java
~~~

### 5.2. File `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>prototype-cleanup-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.13</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>com.example.cleanup.PrototypeCleanupDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.3. File `PrototypeCleanupDemo.java`

~~~java
package com.example.cleanup;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

public class PrototypeCleanupDemo {

    public static void main(String[] args) {
        PrototypeLease second;

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            PrototypeLease first = context.getBean(PrototypeLease.class);
            second = context.getBean(PrototypeLease.class);

            System.out.println("Different prototypes: " + (first != second));

            // Chủ động kích hoạt Spring destruction callbacks cho first.
            context.getBeanFactory()
                .destroyBean("prototypeLease", first);
            System.out.println("First closed: " + first.isClosed());

            System.out.println("Closing ApplicationContext");
        }

        // Context đã đóng singleton, nhưng không tự đóng prototype second.
        System.out.println("Second closed after context: " + second.isClosed());

        // Caller giải phóng second bằng Java contract trực tiếp.
        second.close();
        System.out.println("Second closed manually: " + second.isClosed());
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        SingletonLease singletonLease() {
            return new SingletonLease();
        }

        @Bean(destroyMethod = "close")
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        PrototypeLease prototypeLease() {
            return new PrototypeLease();
        }
    }

    public static class SingletonLease implements AutoCloseable {
        public SingletonLease() {
            System.out.println("Singleton created");
        }

        @Override
        public void close() {
            System.out.println("Singleton closed by Spring");
        }
    }

    public static class PrototypeLease implements AutoCloseable {
        private static final AtomicInteger SEQUENCE = new AtomicInteger();

        private final int number = SEQUENCE.incrementAndGet();
        private final AtomicBoolean closed = new AtomicBoolean();

        public PrototypeLease() {
            System.out.println("Prototype created #" + number);
        }

        @PostConstruct
        public void initialize() {
            System.out.println("Prototype initialized #" + number);
        }

        @PreDestroy
        public void beforeDestroy() {
            System.out.println("Prototype @PreDestroy #" + number);
        }

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                System.out.println("Prototype closed #" + number);
            }
        }

        public boolean isClosed() {
            return closed.get();
        }
    }
}
~~~

Các class được khai báo `public static` bên trong một file Java để tiện học. Chúng được đăng ký qua phương thức `@Bean`; `AnnotationConfigApplicationContext(Config.class)` nhận dạng và xử lý `@Configuration`. `jakarta.annotation-api` cung cấp `@PostConstruct` và `@PreDestroy` theo namespace tương ứng với Spring Framework 6.x.

Trong ví dụ:

- `SingletonLease` là singleton vì `@Bean` không chỉ định scope khác. Spring có thể suy luận `close()` làm destroy callback.
- `PrototypeLease` là prototype. Spring chạy `@PostConstruct` cho mỗi instance mới.
- `destroyBean("prototypeLease", first)` cố ý yêu cầu Spring thực thi **đường hủy** cho `first`: `@PreDestroy`, sau đó custom `close()` theo cấu hình.
- `second` vẫn mở sau khi context đóng. Cuối cùng caller tự đóng nó qua `AutoCloseable`; hành động đóng trực tiếp **không tự gọi method `@PreDestroy`**.

### 5.4. Chạy chương trình

Yêu cầu JDK 17+ và Maven 3.9.x. Chạy tại thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Các dòng stdout chủ động từ chương trình, theo đúng thứ tự:

~~~text
Singleton created
Prototype created #1
Prototype initialized #1
Prototype created #2
Prototype initialized #2
Different prototypes: true
Prototype @PreDestroy #1
Prototype closed #1
First closed: true
Closing ApplicationContext
Singleton closed by Spring
Second closed after context: false
Prototype closed #2
Second closed manually: true
~~~

Maven hoặc logging framework có thể in thông tin khác tùy môi trường; bảng trên chỉ phản ánh những lệnh `System.out.println` trong mã.

**Điểm cần quan sát:** Không có dòng `Prototype @PreDestroy #2` khi đóng context. Prototype thứ hai vẫn mở cho đến khi caller gọi `second.close()`. Điều này không phải bug của Spring: prototype **không nằm trong danh sách destruction callbacks tự động của container** sau khi instance được giao đi.

### 5.5. Khác nhau giữa `destroyBean` và `close()`

| Gọi | Ai thực hiện? | Callback kỳ vọng cho ví dụ |
| --- | --- | --- |
| `context.getBean(PrototypeLease.class)` | Spring tạo target | Constructor, dependency injection, `@PostConstruct` |
| `beanFactory.destroyBean("prototypeLease", first)` | Caller đề nghị Spring xử lý hủy cho một instance cụ thể | `@PreDestroy`, `close()` vì bean definition có `destroyMethod = "close"` |
| `second.close()` | Caller gọi contract Java | Chỉ method `close()` do class định nghĩa |
| `context.close()` | Spring hủy bean/container do nó quản lý | Singleton `close()`; **không tự đóng prototype `second`** |

Khi gọi `destroyBean`, sử dụng đúng **bean name của definition** và đúng **instance đã lấy từ factory**. API này là phần của `ConfigurableBeanFactory`, tức API cấu hình/hạ tầng Spring. Nếu ứng dụng chỉ cần đóng tài nguyên Java bình thường, `AutoCloseable.close()` thường đơn giản hơn, giảm phụ thuộc tới bean factory.

## 6. Cách khuyến nghị: try-with-resources

Khi một prototype đại diện cho **một phiên làm việc có điểm bắt đầu/kết thúc rõ ràng**, hãy thiết kế class implements `AutoCloseable` và lấy nó tại đầu một đơn vị công việc.

~~~java
import java.io.IOException;
import org.springframework.beans.factory.ObjectProvider;

public final class ExportService {
    private final ObjectProvider<ExportSession> sessions;

    public ExportService(ObjectProvider<ExportSession> sessions) {
        this.sessions = sessions;
    }

    public void export() throws IOException {
        try (ExportSession session = sessions.getObject()) {
            session.writeHeader();
            session.writeBody();
        } // close() tự gọi kể cả khi writeBody() ném exception.
    }
}
~~~

Đây là class minh họa, không tự chạy độc lập; `ExportSession` cần được triển khai như `AutoCloseable` với `writeHeader()`, `writeBody()` và `close()`. Trong ứng dụng Spring, đăng ký `ExportSession` là prototype và đăng ký `ExportService` làm bean nếu muốn inject `ObjectProvider`.

Một implementation ý tưởng:

~~~java
public final class ExportSession implements AutoCloseable {
    private final java.io.ByteArrayOutputStream buffer =
        new java.io.ByteArrayOutputStream();

    public void writeHeader() throws java.io.IOException {
        buffer.write("HEADER\n".getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }

    public void writeBody() throws java.io.IOException {
        buffer.write("BODY\n".getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }

    @Override
    public void close() throws java.io.IOException {
        buffer.close();
    }
}
~~~

Lưu ý: `ByteArrayOutputStream.close()` không có hiệu ứng đóng tài nguyên bên ngoài; đoạn này chỉ thể hiện đúng kiểu Java và cú pháp try-with-resources. Trong mã thực tế, `ExportSession` có thể giữ `FileOutputStream`, `InputStream`, socket hoặc resource khác cần giải phóng thật. Khi đó phải xử lý ownership và khả năng ném `IOException` đúng thiết kế.

**Tránh hiểu sai:** `ObjectProvider.getObject()` không tự đóng prototype; chính try-with-resources kích hoạt `close()`. Đồng thời, `close()` Java trực tiếp không tự kích hoạt `@PreDestroy` hoặc `DisposableBean.destroy()` trừ khi chính code `close()` của bạn gọi logic ấy.

### Trường hợp muốn cả lifecycle callback của Spring

Nếu cleanup logic chỉ đặt trong `@PreDestroy` và `DisposableBean.destroy()` mà `close()` không làm thay, có thể tạo một **owner/factory wrapper** gọi `beanFactory.destroyBean(beanName, instance)` trong `close()` của wrapper:

~~~java
import org.springframework.beans.factory.config.ConfigurableBeanFactory;

public final class SpringOwnedHandle<T> implements AutoCloseable {
    private final ConfigurableBeanFactory factory;
    private final String beanName;
    private final T instance;
    private boolean closed;

    public SpringOwnedHandle(
            ConfigurableBeanFactory factory,
            String beanName,
            T instance) {
        this.factory = factory;
        this.beanName = beanName;
        this.instance = instance;
    }

    public T get() {
        return instance;
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            factory.destroyBean(beanName, instance);
        }
    }
}
~~~

Đây là một **class Java hoàn chỉnh về hình thức**, nhưng để dùng trong ứng dụng cần code tạo handle từ một bean factory còn hoạt động, bean name đúng và instance phù hợp; không giả định đa luồng an toàn vì `closed` không được đồng bộ. Nếu nhiều thread có thể gọi `close()` cùng lúc, dùng `AtomicBoolean.compareAndSet(false, true)`.

Cách này tạo một lớp phụ thuộc Spring infrastructure. Chỉ dùng khi cần thực thi đúng chain destruction callbacks của Spring; với resource thông thường, đóng trực tiếp qua `AutoCloseable` thường dễ bảo trì hơn.

## 7. Tại sao inject prototype trực tiếp vào singleton có thể làm tình hình tệ hơn?

Xét:

~~~java
@Component
@Scope("prototype")
class TemporaryWriter implements AutoCloseable {
    @Override
    public void close() {
        // Đóng tài nguyên.
    }
}

@Service
class BatchService {
    private final TemporaryWriter writer;

    BatchService(TemporaryWriter writer) {
        this.writer = writer;
    }

    void process() {
        // Mỗi lần gọi method vẫn dùng cùng writer đã inject.
    }
}
~~~

Đây là mã minh họa cần import `Component`, `Scope` và `Service`. Khi Spring tạo một instance singleton `BatchService`, nó resolve constructor dependency một lần và inject một `TemporaryWriter` prototype. Singleton sau đó giữ tham chiếu này trong field.

Hệ quả:

1. Prototype đó **không mới cho mỗi lần gọi `process()`**.
2. Nó có thể sống lâu bằng singleton nếu field không được thay thế.
3. Spring không tự đăng ký callback hủy riêng cho prototype chỉ vì nó được inject vào singleton.
4. Nếu writer không thread-safe, nhiều request gọi singleton có thể truy cập cùng writer.
5. Nếu service không chủ động cleanup, tài nguyên bị giữ đến khi caller giải phóng hoặc process kết thúc.

Giải pháp phù hợp thường là inject `ObjectProvider<TemporaryWriter>` vào singleton, lấy một writer **trong mỗi lần `process()`** và đóng trong `try-with-resources`:

~~~java
@Service
class BatchService {
    private final ObjectProvider<TemporaryWriter> writers;

    BatchService(ObjectProvider<TemporaryWriter> writers) {
        this.writers = writers;
    }

    void process() {
        try (TemporaryWriter writer = writers.getObject()) {
            // Thực hiện công việc với đúng writer này.
        } catch (Exception ex) {
            throw new IllegalStateException("Processing failed", ex);
        }
    }
}
~~~

Đây là phiên bản **thay thế** của `BatchService` ở trên, không định nghĩa hai class trùng tên trong một package. Nếu `TemporaryWriter.close()` không khai báo checked exception, có thể bỏ việc catch chung; đặt exception handling theo logic nghiệp vụ và đảm bảo không che mất lỗi chính.

## 8. Khi muốn Spring quản lý hủy toàn bộ prototype bằng BeanPostProcessor

Tài liệu Spring nêu khả năng dùng custom `BeanPostProcessor` giữ tham chiếu đến những prototype cần dọn dẹp rồi tự xử lý tài nguyên sau đó. Đây là lựa chọn **nâng cao**:

- Một registry phải theo dõi instance nào đã tạo, thuộc owner nào và khi nào thực sự hết sử dụng.
- Nếu chỉ thêm mọi prototype vào `List` toàn cục rồi chờ context close, registry có thể giữ các object và tài nguyên quá lâu, tạo rò memory.
- Phải tránh cleanup khi prototype còn đang được request/job khác sử dụng.
- Phải bảo đảm registry thread-safe khi nhiều worker tạo/hủy prototype song song.
- Nếu cleanup bằng Spring destruction callbacks, phải tránh double-destroy cho một instance.

Do đó, chỉ chọn cách này khi hệ thống có **ownership/lifecycle manager được thiết kế rõ ràng**. Nó không phải phương án mặc định cho mỗi prototype chỉ giữ một file hoặc socket. Thường tốt hơn là thiết kế `AutoCloseable` và giữ object trong lexical scope của `try-with-resources`.

## 9. Tại sao `@PreDestroy` không đồng nghĩa với `close()`?

Có ba dạng “dọn dẹp” cần phân biệt:

| Cơ chế | Người kích hoạt | Chạy khi nào |
| --- | --- | --- |
| `@PreDestroy` | Spring destruction lifecycle (hoặc framework có hỗ trợ annotation) | Khi destruction callback thực sự được dispatch |
| `DisposableBean.destroy()` | Spring destruction lifecycle | Khi Spring dispatch callback cho bean |
| `AutoCloseable.close()` | Code Java như `try-with-resources` hoặc Spring nếu được cấu hình/suy luận làm destroy method | Khi caller hoặc Spring thật sự gọi `close()` |

Một method `@PreDestroy` không nhất thiết là method `close()`. Gọi `close()` không tự động quét annotation để gọi tất cả lifecycle callback. Ngược lại, nếu `@PreDestroy` method và inferred `close()` cùng tồn tại trên bean singleton, Spring có thể kích hoạt cả hai; cần thiết kế để **không cleanup cùng tài nguyên hai lần theo cách nguy hiểm**.

Một số người viết cả:

~~~java
@PreDestroy
public void stop() {
    close();
}

@Override
public void close() {
    // release
}
~~~

Nếu bean cũng có custom/inferred `destroyMethod = "close"`, Spring có thể gọi `stop()` rồi `close()` thêm lần nữa. Đừng dựa vào suy đoán về cơ chế bỏ trùng callback cho thiết kế. Hãy lựa chọn một owner và một điểm cleanup, hoặc bảo đảm `close()` idempotent.

### Idempotency là gì?

Một method đóng **idempotent** có thể được gọi nhiều lần mà không tạo tác dụng xấu hay cố giải phóng cùng handle nhiều lần. Ví dụ:

~~~java
private final AtomicBoolean closed = new AtomicBoolean();

@Override
public void close() {
    if (closed.compareAndSet(false, true)) {
        // Đóng resource thật đúng một lần.
    }
}
~~~

Mã trên là đoạn bên trong một class implement `AutoCloseable`, cần `import java.util.concurrent.atomic.AtomicBoolean;`. Cần quyết định rõ hành vi nếu cleanup ném exception: atomic flag được set trước thao tác đóng có nghĩa caller không tự retry bằng cùng method; đôi khi phải dùng state machine hoặc xử lý retry ở resource manager.

## 10. Destruction callback có đảm bảo chạy khi process bị tắt đột ngột?

Không. Ngay cả singleton được Spring quản lý cũng không thể dựa vào callback hủy trong mọi sự cố.

| Tình huống | Có thể chạy cleanup? | Ghi chú |
| --- | --- | --- |
| `AnnotationConfigApplicationContext.close()` bình thường | Có, với singleton được container quản lý | Trừ khi lỗi hoặc lifecycle đặc biệt |
| Spring Boot shutdown hợp lệ với shutdown hook | Có thể | Phụ thuộc quá trình shutdown và hệ thống |
| `System.exit(...)` và shutdown hooks được chạy | Có thể | Không bảo đảm nếu hook lỗi/hết thời gian |
| JVM crash, `kill -9`, mất điện | Không thể bảo đảm | Callback Java không có cơ hội chạy |
| Prototype đã giao ra và sau đó context đóng | **Không tự động** | Caller vẫn chịu trách nhiệm |
| Prototype trong `try-with-resources` | Java cố gọi `close()` khi rời block | Phụ thuộc đường thực thi và việc JVM còn hoạt động |

Với tài nguyên quan trọng, cần cơ chế bền vững ở cấp hệ thống: transaction boundary, timeout, lease, server-side expiration, connection pool hoặc recovery sau crash. Lifecycle callback là cơ chế cleanup hợp lệ trong luồng chạy bình thường, **không phải bảo đảm chống mọi sự cố**.

## 11. Đặc biệt với connection pool, JDBC và HTTP client

Không phải cứ có resource là tự viết prototype:

- **Connection pool / HTTP client thread-safe** thường nên được quản lý dài hạn, hay là singleton `@Bean` với destroy method thích hợp. Tạo cả một pool mới cho từng prototype request là rất tốn kém và có thể làm cạn kết nối.
- **Connection hoặc stream mượn từ pool** nên được lấy và trả trong phạm vi giao dịch/công việc, thường qua `try-with-resources` hoặc infrastructure quản lý resource. “Đóng” một pooled connection thường mang nghĩa trả lại pool.
- **Spring transaction management** có thể bind connection vào transaction hiện hành. Không tự ý đóng resource đã được framework quản lý thay cho transaction manager.
- **File handle, socket, archive writer** do prototype **thật sự sở hữu** nên có contract đóng rõ ràng, thường là `AutoCloseable`.

Cần xác định **ai sở hữu resource**, không chỉ nhìn thấy method `close()`. Nếu bean chỉ tham chiếu một resource chung do singleton sở hữu, prototype không nên đóng resource chung khi nó kết thúc.

## 12. Thiết kế ownership rõ ràng

Một prototype có thể có những quan hệ:

~~~text
Singleton ResourceManager
      |
      | mở/cho mượn
      v
Prototype WorkSession  <-- một lần công việc sở hữu
      |
      | sử dụng resource được mượn
      v
Close / release vào cuối công việc
      |
      v
ResourceManager tiếp tục tồn tại
~~~

**Các câu hỏi cần trả lời trong code review:**

1. Ai gọi Spring để lấy prototype?
2. Ai quyết định instance không được dùng nữa?
3. Ai gọi `close()` hoặc `destroyBean(...)` và ở nhánh thành công/thất bại nào?
4. Prototype có giữ resource riêng hay chỉ mượn resource chung?
5. `close()` có thể bị gọi đồng thời hoặc hai lần không?
6. Nếu initialization thất bại giữa chừng, resource nào đã mở và cách rollback?
7. Nếu tác vụ async kéo dài, ai bảo đảm cleanup ở thời điểm tác vụ thật sự kết thúc?
8. Bean proxy có khiến bạn đang đóng **proxy** thay vì **target resource** không?

Với những bean chỉ giữ dữ liệu tính toán thuần Java, có thể không cần callback hủy. Với bean giữ tài nguyên, trách nhiệm cleanup phải hiển thị trong API thay vì kỳ vọng GC hoặc Spring context sẽ đoán giúp.

## 13. Cleanup khi exception xảy ra giữa công việc

### 13.1. `try-with-resources` bao phủ cả đường lỗi

~~~java
try (WorkSession session = sessions.getObject()) {
    session.stepOne();
    session.stepTwo();  // Nếu ném exception, close() vẫn được gọi.
}
~~~

Đây là mã minh họa; `sessions` là `ObjectProvider<WorkSession>`, `WorkSession` implements `AutoCloseable`. Compiler sinh block `finally` để gọi `close()`, và nếu cả phần body lẫn `close()` đều throw, lỗi `close()` thường được lưu là *suppressed exception* của lỗi chính.

### 13.2. Nếu factory đã mở tài nguyên nhưng constructor/init thất bại?

Không thể dựa vào một prototype **chưa được tạo hoàn chỉnh và chưa giao cho caller** để caller cleanup. Với resource mở ngay trong constructor hoặc init method, nên áp dụng exception safety:

~~~java
public ResourceSession(Path path) throws IOException {
    this.stream = Files.newOutputStream(path);
    try {
        validateConfiguration();
    } catch (RuntimeException | Error ex) {
        try {
            stream.close();
        } catch (IOException cleanupFailure) {
            ex.addSuppressed(cleanupFailure);
        }
        throw ex;
    }
}
~~~

Đây là đoạn constructor minh họa bên trong `ResourceSession`; class cần field `OutputStream stream`, method `validateConfiguration()`, các import `Path`, `Files`, `IOException`. Nó thể hiện cách cleanup tài nguyên đã mở khi khởi tạo thất bại. Trong thiết kế tốt hơn, có thể trì hoãn việc mở tài nguyên đến một factory có khả năng cleanup rõ ràng hoặc dùng `try-with-resources` ngay tại chỗ acquire.

### 13.3. Nếu `close()` thất bại?

Không nên nuốt mọi lỗi đóng tài nguyên. Tùy ngữ cảnh, log có correlation ID, gắn suppressed exception hoặc truyền exception ra ngoài theo contract của API. Với pool/network, đôi khi đóng tài nguyên có thể thất bại vì state đã hỏng; cần có chính sách phục hồi thay vì retry vô hạn.

## 14. Prototype, scoped proxy và giới hạn của `try-with-resources`

Giả sử bean prototype được khai báo với proxy:

~~~java
@Component
@Scope(
    value = "prototype",
    proxyMode = ScopedProxyMode.TARGET_CLASS
)
public class ProxiedWorker implements AutoCloseable {
    public void work() {
        // ...
    }

    @Override
    public void close() {
        // ...
    }
}
~~~

Đây là class minh họa, cần import `Component`, `Scope` và `ScopedProxyMode`.

Một **prototype scoped proxy** có thể resolve target khác nhau cho **mỗi method invocation**. Nếu caller có reference đến proxy và viết:

~~~java
try (ProxiedWorker worker = injectedWorkerProxy) {
    worker.work();
}
~~~

Không nên mặc định `work()` và `close()` chạy trên cùng target. Target của lời gọi `work()` có thể khác target của `close()`; khi đó công việc thực tế không được đóng đúng tài nguyên. Đây là một lý do quan trọng để **không coi prototype scoped proxy là resource handle ổn định**.

Với resource cần nhiều lời gọi trên **cùng instance**, lấy target prototype trực tiếp từ `ObjectProvider.getObject()` và lưu trong biến cục bộ của một công việc. Khi bean không bật scoped proxy, provider trả target prototype để `try-with-resources` đóng đúng object.

## 15. Tình huống bất đồng bộ, nhiều thread và đóng quá sớm

Một method singleton có thể giao prototype cho thread khác:

~~~java
WorkSession session = sessions.getObject();
executor.submit(() -> session.process());
session.close(); // Nguy cơ đóng trước khi background task dùng xong.
~~~

Đây là đoạn minh họa; `executor` là một `ExecutorService`. Không thể đóng session ở thread gọi ngay sau khi submit rồi kỳ vọng worker đã xong. Cần đặt cleanup vào đúng đường hoàn thành của task:

~~~java
executor.submit(() -> {
    try (WorkSession session = sessions.getObject()) {
        session.process();
    }
});
~~~

Nếu `sessions.getObject()` không được phép gọi ở worker thread vì dependency gắn request scope, phải truyền snapshot dữ liệu cần thiết thay vì truyền scoped proxy. Với prototype thông thường, có thể lấy trong worker nếu container còn sống.

Nhiều thread dùng chung một prototype vẫn phải tự đồng bộ mutable state. Scope prototype **không bảo đảm thread-safety**. Với task hủy/chạy đồng thời, thiết kế ownership và synchronization sao cho `close()` không xảy ra trong khi `process()` vẫn đang sử dụng resource.

## 16. Kiểm thử chính sách cleanup của prototype

Bài test tốt phải kiểm tra cả **được đóng** và **không được Spring tự đóng** theo hợp đồng:

1. Tạo context từ `@Configuration`.
2. Lấy hai prototype và kiểm tra chúng không trùng object identity.
3. Xác nhận initialization callback đã chạy trên cả hai.
4. Gọi `beanFactory.destroyBean(name, first)`, kiểm tra `first` đã đóng.
5. Đóng context và xác nhận `second` chưa đóng.
6. Gọi `second.close()`, kiểm tra `second` đã đóng.
7. Kiểm tra singleton có destroy callback được Spring gọi.

Ví dụ main ở mục 5 đã kiểm chứng tuần tự đủ các bước này qua stdout. Trong test automation, ưu tiên assert `boolean`/counter/state thay vì chỉ so khớp text log, vì framework có thể in thêm thông tin.

Nếu kiểm thử có prototype mở tài nguyên thật, luôn cleanup trong `finally` hoặc try-with-resources **ngay cả khi assertion thất bại**. Test không nên rò file handle vì một nhánh `assertThat(...)` ném exception.

## 17. Lỗi phổ biến và cách xử lý

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@PreDestroy` không chạy khi đóng context | Instance là prototype đã giao cho caller | Cleanup chủ động; dùng `close()` hoặc `destroyBean(...)` theo contract |
| `DisposableBean.destroy()` không được tự gọi | Prototype không được Spring theo dõi để hủy tự động | Thiết kế owner, không phụ thuộc context shutdown |
| Có `destroyMethod = "close"` mà prototype vẫn mở | Khai báo callback không đồng nghĩa tự kích hoạt | Caller gọi `close()` hoặc kích hoạt destruction có chủ đích |
| Bean singleton đóng nhưng prototype không | Singleton thuộc danh sách hủy của container, prototype không | Đúng hành vi; xử lý riêng prototype |
| Resource bị đóng hai lần | `@PreDestroy` và inferred `close()` cùng đóng, hoặc hai owner gọi | Một nơi sở hữu cleanup, `close()` idempotent khi phù hợp |
| Resource đóng rồi mà job vẫn chạy | Cleanup xảy ra trước khi async task hoàn tất | Gắn ownership theo vòng đời thực của job |
| File/socket bị rò khi exception | Không dùng `try/finally` hoặc `try-with-resources` | Bao mọi đường kết thúc trong cleanup |
| Prototype bị giữ lâu trong singleton field | Direct injection chỉ resolve một lần | Provider/factory per operation; cleanup từng instance |
| Shutdown context không giải phóng resource | Nhầm JVM shutdown với cleanup prototype | Thiết kế hủy chủ động và timeout/recovery |
| `close()` trên proxy không đóng đúng target | Prototype proxy có thể chọn target khác cho mỗi lời gọi | Lấy target thật bằng provider và giữ biến cục bộ |
| Cleanup sai tài nguyên chung | Prototype chỉ mượn resource do singleton khác sở hữu | Chỉ trả/giải phóng lease, không đóng resource manager |
| Container context đóng trong khi worker còn chạy | Worker giữ prototype/context ngoài lifetime hợp lệ | Chốt lifecycle job, ngừng nhận task, đợi/cancel và cleanup có tổ chức |

## 18. Hướng dẫn chọn chiến lược

**Đối tượng chỉ mang dữ liệu:** Không cần tạo resource cleanup giả. Prototype mới hoặc object Java `new` bình thường có thể để GC quản lý.

**Đối tượng giữ resource riêng trong một method:** Dùng `AutoCloseable` và `try-with-resources`. Inject `ObjectProvider<T>` vào singleton để tạo prototype ở đầu method, rồi dùng một instance xuyên suốt công việc.

**Đối tượng phải chạy chính xác lifecycle callbacks của Spring:** Cân nhắc `ConfigurableBeanFactory.destroyBean(beanName, instance)` từ lớp owner có kiểm soát. Hãy nêu rõ vì sao gọi framework API thay vì `close()` Java.

**Thư viện có `close()` hoặc `shutdown()`:** Khai báo một singleton `@Bean` nếu thư viện là client/pool dùng chung; Spring thường tự suy luận destroy method cho `@Bean`. Đặt `destroyMethod` rõ ràng khi có yêu cầu đặc biệt.

**Nhiều tác vụ bất đồng bộ:** Gắn việc tạo và giải phóng prototype vào **mỗi task**, không vào thread submit hoặc shutdown context. Khi cần giới hạn tài nguyên, dùng pool/semaphore/lease phù hợp.

**Muốn “Spring tự đóng mọi prototype khi context close”:** Đây không phải hành vi mặc định. Nếu thật sự cần một registry lifecycle, phải có owner rõ ràng, quy tắc kết thúc sử dụng, synchronization và kiểm tra memory retention. Thông thường quản lý trực tiếp bằng scope của công việc đơn giản hơn.

## 19. Câu hỏi tự kiểm tra

**Câu 1:** Một `@Bean` prototype có `@PreDestroy` và `destroyMethod = "close"`. Sau khi gọi `getBean()`, nếu chỉ `context.close()` thì hai callback có tự chạy không?

**Đáp án:** Không tự động cho prototype đã giao cho caller. Container không theo dõi toàn bộ prototype instance để destroy vào lúc close. Cần cleanup chủ động.

**Câu 2:** `context.getBeanFactory().destroyBean("prototypeLease", lease)` có khác `lease.close()` không?

**Đáp án:** Có. `destroyBean` dùng bean definition để thực hiện Spring destruction lifecycle (chẳng hạn `@PreDestroy`, `DisposableBean`, custom destroy method). `close()` gọi trực tiếp một method Java. Cả hai phải được gọi ở thời điểm resource thực sự hết sử dụng.

**Câu 3:** Vì sao `@Bean(destroyMethod = "")` không phải cách “tắt mọi destroy callback”?

**Đáp án:** Nó vô hiệu hóa custom destroy-method inference/name theo bean definition; các cơ chế như `DisposableBean.destroy()` vẫn có contract riêng. Với prototype, vấn đề chính là không tự trigger destruction chứ không phải chỉ thiếu cấu hình method.

**Câu 4:** Một singleton inject trực tiếp một prototype `FileWriter`. Tại sao nhiều lần gọi singleton không tạo writer mới và writer có thể bị giữ lâu?

**Đáp án:** Dependency prototype được resolve khi singleton tạo, một object được lưu trong field. Các method calls không tự yêu cầu Spring tạo prototype mới. Cần provider/factory per operation và cleanup theo lifecycle.

**Câu 5:** Nếu prototype scope proxy implements `AutoCloseable`, có thể bảo đảm `proxy.work()` và `proxy.close()` tác động cùng target không?

**Đáp án:** Không. Prototype scoped proxy có thể lấy target mới cho từng lời gọi. Hãy giữ tham chiếu trực tiếp tới một target prototype lấy từ provider khi công việc cần state/resource ổn định.

**Câu 6:** Có cần `@PreDestroy` cho prototype chỉ giữ `List<String>` không?

**Đáp án:** Thường không. Nếu không giữ tài nguyên ngoài heap hay cần hoàn nguyên side effect, Java GC xử lý memory khi object không còn reachable. Không thêm callback hủy chỉ để “cho đủ lifecycle”.

## 20. Tài liệu chính thức

- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): hợp đồng prototype, initialization callback, giới hạn destruction callback và việc caller cần cleanup.
- [Spring Framework — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `@PreDestroy`, `DisposableBean`, custom destroy method, thứ tự callback.
- [Spring Framework — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): `destroyMethod`, suy luận `close()`/`shutdown()`, `destroyMethod = ""`.
- [ConfigurableBeanFactory Javadoc — `destroyBean(String, Object)`](https://docs.spring.io/spring-framework/docs/6.1.6/javadoc-api/org/springframework/beans/factory/config/ConfigurableBeanFactory.html): API kích hoạt destruction theo bean definition cho một bean instance cụ thể.
- [Spring Framework — Method Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-method-injection.html): cách lấy prototype mới khi một singleton cần dependency theo từng lần xử lý.
