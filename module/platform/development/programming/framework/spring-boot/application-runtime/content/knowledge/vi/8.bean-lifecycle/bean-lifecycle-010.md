# Giới hạn tự hủy đối với bean prototype và tài nguyên tạo ngoài container

## 1. Vì sao bean được Spring tạo vẫn có thể không được Spring tự hủy?

Spring quản lý vòng đời bean theo **scope** và theo việc đối tượng có thuộc quyền quản lý của container hay không. Hai câu hỏi cần tách riêng:

1. **Spring có tạo và khởi tạo đối tượng này không?** Điều đó quyết định cơ chế dependency injection, bean post-processor, `@PostConstruct` và những bước initialization.
2. **Ai có trách nhiệm kết thúc vòng đời và giải phóng tài nguyên?** Điều đó phụ thuộc vào scope, cách cấp phát, quan hệ sở hữu và cơ chế dọn dẹp.

Với bean `singleton` thông thường, Spring container giữ instance, theo dõi nó và gọi các destruction callback thích hợp khi context đóng bình thường. Với bean `prototype`, Spring thường **tạo, cấu hình, khởi tạo rồi trao instance cho nơi yêu cầu**; sau thời điểm đó container **không theo dõi đầy đủ** từng prototype để tự hủy khi context đóng.

Tương tự, một đối tượng do ứng dụng tự gọi `new` bên ngoài container thường **không phải bean**. Spring không tự biết đối tượng đó đang sở hữu file handle, socket, thread pool hay stream cần đóng.

Đây là quy tắc trung tâm của bài:

> **Có được Spring khởi tạo không đồng nghĩa được Spring tự hủy. Có annotation hủy không đồng nghĩa callback chắc chắn được gọi.**

Bài áp dụng cho Spring Framework 6.1.x và Spring Boot 3.3.x trên Java 17+. Mục tiêu là hiểu đúng giới hạn quản lý tài nguyên, chọn cơ chế cleanup và kiểm chứng bằng chương trình chạy thực tế.

## 2. Hai pha khác nhau: initialization và destruction

Vòng đời một bean nói chung có thể được hình dung như sau:

```text
Bean definition / yêu cầu lấy bean
    |
    v
Tạo instance (constructor hoặc factory method)
    |
    v
Tiêm dependency, áp dụng BeanPostProcessor
    |
    v
Initialization callbacks
    |  @PostConstruct, InitializingBean, initMethod thích hợp
    v
Bean được trao cho caller / sẵn sàng sử dụng
    |
    +----------------------+--------------------------+
    |                      |                          |
    v                      v                          v
singleton              prototype                 new ngoài Spring
Spring theo dõi        caller nhận instance      caller giữ instance
vòng đời instance      và sở hữu cleanup         và sở hữu cleanup
    |                      |                          |
    v                      v                          v
Context đóng           Caller chủ động            Caller chủ động
bình thường            close/destroy              close/shutdown
    |                      |                          |
    v                      v                          v
Destruction callbacks  Không tự gọi callback      Không có callback
cho singleton          hủy từ Spring              Spring mặc định
```

**Cần lưu ý:** `@PostConstruct` và `@PreDestroy` là hai phía của vòng đời **khi Spring thực sự quản lý các bước đó**. Đối với prototype, initialization callback được xử lý trong quá trình tạo bean; nhưng destruction callback được khai báo như `@PreDestroy` hay `DisposableBean.destroy()` **không tự chạy chỉ vì context đóng**.

“Destroy” trong Spring chủ yếu là gọi những callback dọn dẹp do người viết định nghĩa. JVM có thể thu hồi bộ nhớ qua GC ở thời điểm không xác định, nhưng GC **không phải cơ chế giải phóng đúng hạn** file descriptor, kết nối mạng, executor hoặc lock cần giải phóng theo hợp đồng ứng dụng.

## 3. So sánh phạm vi Spring quản lý tài nguyên

| Cách có được đối tượng | Spring có biết bean definition/instance? | Initialization | Destruction khi context đóng bình thường | Ai phải dọn dẹp? |
| --- | --- | --- | --- | --- |
| `@Bean` mặc định `singleton` | Có; container giữ instance | Có | Thường có callback theo cấu hình | Spring thực hiện callback; callback phải giải phóng tài nguyên đúng cách |
| `@Component` singleton | Có; container giữ instance | Có | Thường có callback phù hợp | Spring thực hiện callback; lớp bean phải triển khai cleanup |
| `@Bean` hoặc `@Component` với `@Scope("prototype")` | Có definition và xử lý từng lần tạo; không giữ mọi instance để hủy tập trung | Có | **Không tự gọi destructor cho từng prototype** | Caller hoặc thành phần sở hữu prototype |
| `new SomeResource()` ngoài container | Không, trừ khi được đưa vào cơ chế quản lý khác | Chỉ constructor/logic tự gọi | Không | Mã tạo/nhận quyền sở hữu |
| `@Bean` trả về một đối tượng đã tạo bằng `new` | **Có**, khi factory method trả về đối tượng làm Spring bean | Có xử lý bean lifecycle | Phụ thuộc scope và destroy method | Xem hợp đồng sở hữu khi đăng ký bean |
| Tài nguyên được tạo trong trường của một singleton, không đăng ký riêng | Spring quản lý **owner bean**, không nhất thiết biết tài nguyên con | Phụ thuộc code owner | Chỉ tự dọn nếu owner thực hiện cleanup | Owner bean qua `@PreDestroy` hoặc destroy method |
| Đối tượng mượn từ thư viện khác hoặc shared pool | Không nhất thiết | Theo thư viện sở hữu | Không bảo đảm | Bên sở hữu thật theo hợp đồng; bên mượn không tùy tiện đóng |

Không nên nói mọi scope ngoài singleton đều có hành vi hủy giống prototype. `request`, `session` và custom scope có thể quản lý destruction callback ở cuối vòng đời scope theo cơ chế riêng. **Quy tắc prototype ở đây là quy tắc cụ thể của prototype scope mặc định.**

## 4. Chính xác Spring làm gì với một prototype bean?

Ví dụ định nghĩa:

```java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class FileTask {
    @PostConstruct
    public void init() {
        // Spring gọi khi instance này được khởi tạo.
    }

    @PreDestroy
    public void cleanup() {
        // Spring KHÔNG tự gọi khi context đóng đối với prototype.
    }
}
```

Đây là **đoạn minh họa**, cần các import Spring/Jakarta và đặt trong dự án Spring Boot hợp lệ. Sau khi có bean definition, mỗi lần caller yêu cầu prototype phù hợp, Spring tạo một instance mới:

```java
FileTask a = context.getBean(FileTask.class);
FileTask b = context.getBean(FileTask.class);
System.out.println(a == b); // false với bean prototype thông thường
```

### 4.1. Những callback nào vẫn chạy?

Khi Spring tạo prototype, các thao tác thích hợp vẫn diễn ra: constructor hoặc factory method, tiêm dependency, bean post-processor và initialization callback như `@PostConstruct`. Khi bean được giao cho caller, instance đó đã được tạo/khởi tạo theo cơ chế Spring.

Một prototype không nhất thiết được tạo ngay khi context refresh. Thông thường nó được tạo theo **mỗi lần yêu cầu bean**; nếu được inject vào singleton bằng constructor thì nó được tạo tại lúc singleton được khởi tạo.

### 4.2. Những callback nào không tự chạy?

Khi đóng `ApplicationContext`, Spring thường **không gọi** các callback destruction được khai báo cho từng prototype:

- `@PreDestroy`;
- `DisposableBean.destroy()`;
- `@Bean(destroyMethod = "close")` hoặc destroy method cấu hình khác của một bean prototype;
- Cơ chế suy luận `close`/`shutdown` cho `@Bean` prototype.

Các cơ chế trên có thể được thực thi **khi bạn chủ động chuyển instance vào quá trình hủy phù hợp**. Nhưng **đóng context một lần không tương đương hủy mọi prototype từng được phát ra**.

### 4.3. Vì sao Spring làm vậy?

Prototype thường được tạo nhiều lần, có thể sống độc lập và được truyền qua nhiều thành phần. Spring không giữ tập tham chiếu tới mọi instance prototype để quyết định thời điểm mỗi đối tượng hết được sử dụng. Nếu container cố giữ tất cả, việc giữ tham chiếu đến những đối tượng đã dùng xong còn có thể làm tăng bộ nhớ.

Vì vậy sau khi bàn giao instance, **caller phải biết thời điểm kết thúc công việc**. Với tài nguyên như stream, session hoặc handle, đây là nơi phải xác định ai sở hữu trách nhiệm `close()`.

## 5. Ví dụ Java 17+ / Spring Boot 3.3 chạy được

Thí nghiệm sau được cố ý viết bằng **tài nguyên mô phỏng**: không mở socket/file thật, để có thể quan sát chính xác những callback chạy và không chạy. Một prototype được đóng thủ công; một prototype thứ hai cố ý không đóng **chỉ để chứng minh Spring không tự dọn**. Không áp dụng phần bỏ đóng này cho tài nguyên thật trong production.

### 5.1. build.gradle và cấu hình

Dự án Gradle Groovy, Java 17, Spring Boot 3.3.13:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Tạo `settings.gradle`:

```groovy
rootProject.name = 'lifecycle-ownership-lab'
```

Tạo `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR
```

Không cần web starter vì nội dung đang kiểm tra bean lifecycle, không liên quan HTTP server. Ví dụ dùng **Gradle Wrapper** đã được tạo sẵn cho project.

### 5.2. Mã nguồn hoàn chỉnh

Tạo đúng file `src/main/java/com/example/lifecycle/LifecycleOwnershipApplication.java`:

```java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Scope;

@SpringBootApplication
public class LifecycleOwnershipApplication {

    private static final AtomicInteger NEXT_ID = new AtomicInteger();

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(LifecycleOwnershipApplication.class, args)) {

            try (PrototypeHandle first =
                    context.getBean(PrototypeHandle.class)) {
                System.out.println("use prototype #" + first.id());
            }

            PrototypeHandle second = context.getBean(PrototypeHandle.class);
            System.out.println("leave prototype #" + second.id()
                    + " unclosed (demo only)");

            try (ExternalHandle external = new ExternalHandle()) {
                System.out.println("use external");
            }
        }
        // Context đã đóng. Prototype #2 không được Spring tự close.
    }

    @Bean(destroyMethod = "close")
    SingletonHandle singletonHandle() {
        return new SingletonHandle();
    }

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    PrototypeHandle prototypeHandle() {
        return new PrototypeHandle(NEXT_ID.incrementAndGet());
    }

    static final class SingletonHandle implements AutoCloseable {
        SingletonHandle() {
            System.out.println("singleton created");
        }

        @Override
        public void close() {
            System.out.println("singleton close");
        }
    }

    static final class PrototypeHandle implements AutoCloseable {
        private final int id;

        PrototypeHandle(int id) {
            this.id = id;
        }

        int id() {
            return id;
        }

        @PostConstruct
        public void init() {
            System.out.println("prototype init #" + id);
        }

        @PreDestroy
        public void annotatedDestroy() {
            System.out.println("prototype @PreDestroy #" + id);
        }

        @Override
        public void close() {
            System.out.println("prototype close #" + id);
        }
    }

    static final class ExternalHandle implements AutoCloseable {
        ExternalHandle() {
            System.out.println("external created");
        }

        @PreDestroy
        public void annotatedDestroy() {
            System.out.println("external @PreDestroy");
        }

        @Override
        public void close() {
            System.out.println("external close");
        }
    }
}
```

Trong chương trình:

1. `SingletonHandle` được đăng ký qua `@Bean` singleton mặc định và Spring gọi `close` theo cấu hình `destroyMethod` khi context đóng.
2. `PrototypeHandle` được đăng ký bằng `@Bean` với scope prototype. Hai lần `getBean` tạo hai instance. Spring gọi `@PostConstruct` cho cả hai.
3. Instance `first` được đặt trong `try-with-resources` nên **mã Java gọi `AutoCloseable.close()`** khi rời khối. Hành động này **không đồng nghĩa** Spring đã gọi `@PreDestroy`.
4. Instance `second` được lấy ra nhưng không đóng, chỉ để minh họa. Khi đóng context, Spring không gọi cả `@PreDestroy` lẫn `close` cho instance prototype này.
5. `ExternalHandle` được tạo trực tiếp bằng `new` và được đóng nhờ `try-with-resources`. Annotation `@PreDestroy` trên class đó **không khiến Spring tự nhận quyền quản lý đối tượng**.

### 5.3. Cách chạy

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

macOS/Linux:

```bash
./gradlew bootRun
```

Các dòng **do mã ví dụ in ra**, theo đúng thứ tự với dự án như đã mô tả:

```text
singleton created
prototype init #1
use prototype #1
prototype close #1
prototype init #2
leave prototype #2 unclosed (demo only)
external created
use external
external close
singleton close
```

Gradle có thể in các dòng task/build khác. Các property đã tắt banner và startup INFO logging để kết quả dễ đọc.

**Ba dòng đáng chú ý không xuất hiện:**

```text
prototype @PreDestroy #1
prototype @PreDestroy #2
external @PreDestroy
```

Đây là **các dòng không được in**, được đưa ra để so sánh; chúng **không** là một phần của stdout dự kiến. Spring không tự hủy prototype khi context đóng và không quản lý instance được tạo bằng `new`. `first.close()` là lệnh Java do `try-with-resources` gọi trực tiếp; nó không tự kích hoạt toàn bộ chuỗi destruction callback của Spring.

### 5.4. Đổi thí nghiệm

- Đổi `@Scope(PROTOTYPE)` thành singleton: hai lần `getBean` thường trả cùng instance, và `@PreDestroy` của bean đó có thể được Spring gọi lúc context đóng. **Không chạy lại nguyên xi phần `try-with-resources` đóng singleton ngay giữa chương trình** như một ví dụ production, vì sẽ phá ranh giới sở hữu của container.
- Bỏ `try-with-resources` khỏi `first`: sẽ không có dòng `prototype close #1`; context đóng vẫn không cứu được việc thiếu cleanup.
- Bỏ `@PreDestroy` trên prototype: output không đổi, vì callback ấy vốn không được Spring tự gọi khi đóng context.
- Đổi `ExternalHandle` thành một bean singleton được Spring đăng ký với destroy method thích hợp: lúc đó quyền quản lý vòng đời đã thay đổi, dù constructor có thể vẫn dùng `new` bên trong factory method.

## 6. Đối tượng được tạo bằng new: khi nào vẫn là Spring bean?

Câu “đối tượng tạo bằng `new` không được Spring quản lý” cần hiểu **đúng ranh giới đăng ký**. Cách gọi constructor không tự quyết định lifecycle.

### 6.1. new trong mã ứng dụng bình thường

```java
ClientSession session = new ClientSession();
session.doWork();
```

Đây là **đoạn minh họa**, với `ClientSession` là class ứng dụng giả định. Nếu không đăng ký `session` với một container/scope phù hợp, Spring không biết instance đó và không tự gọi `@PostConstruct`, `@PreDestroy` hay `close()` cho nó. Người tạo hoặc người nhận quyền sở hữu phải đóng theo contract của class.

Thêm annotation `@Component` vào **định nghĩa class** cũng không biến mọi instance được tự `new` thành Spring bean. Container chỉ quản lý những instance nó được cấu hình để tạo/quản lý.

### 6.2. new bên trong @Bean

```java
@Configuration
class ClientConfig {
    @Bean(destroyMethod = "close")
    ClientSession clientSession() {
        return new ClientSession();
    }
}
```

Đây là **đoạn cấu hình minh họa**, cần class `ClientSession` có phương thức `close()` và các import thích hợp.

**Kết quả khác hoàn toàn:** instance được trả về từ phương thức `@Bean` được đăng ký thành bean. Với singleton mặc định, Spring theo dõi lifecycle bean đó và có thể gọi `close()` khi context đóng.

Nếu phương thức `@Bean` có `@Scope("prototype")`, Spring tạo một bean khi có yêu cầu nhưng **không tự chạy destruction callback cho mỗi instance lúc context đóng**. Vì vậy **“do `@Bean` tạo” cũng chưa đủ** để kết luận có auto-cleanup; phải xem scope.

### 6.3. Tài nguyên được tạo *bên trong* một bean nhưng không là bean

Ví dụ một singleton sở hữu executor:

```java
@Component
class TaskOwner {
    private final ExecutorService executor =
            Executors.newFixedThreadPool(2);

    @PreDestroy
    void stop() {
        executor.shutdown();
    }
}
```

Đây là **đoạn mã minh họa**, cần import `java.util.concurrent.ExecutorService`, `Executors`, `org.springframework.stereotype.Component` và `jakarta.annotation.PreDestroy`.

Trong trường hợp này, Spring quản lý bean `TaskOwner` và gọi method `stop()` khi destroy singleton bình thường. Nó **không tự nhận `executor` là một bean** chỉ vì executor nằm trong field của bean. Cleanup có hiệu lực vì **owner bean chủ động gọi `shutdown()`**. Với task dài, `shutdown()` chỉ ngừng nhận task mới; có thể còn cần `awaitTermination(...)` với timeout và chiến lược xử lý task đang chạy.

Tài nguyên tương tự gồm `InputStream`, `Socket`, `Connection`, message consumer, file watcher, thread pool và native handle. Phải hiểu phương thức đóng phù hợp cho từng API.

## 7. Chọn một chủ sở hữu để dọn dẹp tài nguyên

Trong thiết kế, hãy xác định ba thông tin cùng nhau:

1. **Ai tạo hoặc thuê tài nguyên?** Bean factory, service, method xử lý request, thư viện khác hay container bên ngoài?
2. **Ai được quyền đóng?** Owner thực sự, không nhất thiết là nơi đang có một tham chiếu tới resource.
3. **Khi nào nên đóng?** Hết một request/job, kết thúc một scope, lúc singleton đóng hoặc lúc ứng dụng shutdown.

Ví dụ lựa chọn:

| Tài nguyên | Vòng đời mong muốn | Ownership khuyến nghị |
| --- | --- | --- |
| Stream cho một lần đọc file | Một khối đọc ngắn | Phương thức mở stream dùng `try-with-resources` |
| Prototype xử lý một công việc | Một job/request nghiệp vụ | Caller lấy prototype và tự `close` trong `finally`/`try-with-resources` |
| Kết nối theo transaction | Một transaction | Dùng cơ chế transaction/connection pool; trả connection đúng hợp đồng, không đóng pool chung |
| Shared HTTP client hoặc connection pool | Suốt vòng đời ứng dụng | Bean singleton/owner quản lý và đóng một lần khi shutdown |
| Thread pool sở hữu bởi một bean | Suốt vòng đời owner | Owner gọi `shutdown`, chờ task theo chính sách |
| Client được mượn từ một thư viện/host bên ngoài | Theo vòng đời host | Bên mượn không tự đóng tài nguyên chung nếu hợp đồng không trao ownership |
| Prototype do singleton giữ trong field | Có thể kéo dài theo singleton | Singleton/owner phải thiết kế cleanup cho instance đã nhận; không dựa vào prototype destruction tự động |

Từ bảng này, lựa chọn dễ kiểm tra nhất thường là **ràng buộc acquisition và release trong cùng một scope code**. Ví dụ:

```java
try (ResourceHandle handle = openResource()) {
    handle.execute();
}
```

Đây là **pseudocode Java** với class/method giả định. Khi có exception trong khối, `try-with-resources` vẫn gọi `close()`. Resource cần triển khai `AutoCloseable` hoặc `Closeable`. Tự gọi `@PreDestroy` hoặc dựa vào GC không thay thế được hợp đồng `close` của tài nguyên.

### 7.1. Cần prototype mới cho từng lần xử lý: dùng ObjectProvider

Một singleton tiêm thẳng prototype bằng constructor:

```java
@Service
class ReportService {
    private final ReportSession session;

    ReportService(ReportSession session) {
        this.session = session;
    }
}
```

Nếu `ReportSession` là prototype, instance được giải quyết **khi singleton `ReportService` được tạo**, không tự thay mới mỗi lời gọi method. Singleton có thể giữ prototype quá lâu và dễ quên hủy đúng thời điểm.

Để lấy một instance prototype cho **mỗi lần xử lý**, có thể inject `ObjectProvider<ReportSession>`:

```java
@Service
class ReportService {
    private final ObjectProvider<ReportSession> sessions;

    ReportService(ObjectProvider<ReportSession> sessions) {
        this.sessions = sessions;
    }

    void runReport() {
        try (ReportSession session = sessions.getObject()) {
            session.generate();
        }
    }
}
```

Hai đoạn trên là **minh họa cấu trúc**, không phải file chạy độc lập: cần khai báo `ReportSession` là bean prototype triển khai `AutoCloseable`, định nghĩa `generate()` và import `ObjectProvider`, `@Service`. `ObjectProvider` giúp **lấy instance mới đúng lúc**, nhưng nó **không tự dọn dẹp instance** sau khi trả về. Trách nhiệm cleanup ở đây thuộc `try-with-resources` của caller.

Nếu đối tượng prototype chỉ chứa dữ liệu tạm không giữ tài nguyên cần đóng, không nhất thiết phải bắt nó thực thi `AutoCloseable`. Việc thiết kế cleanup phải tương xứng loại tài nguyên thực tế, không thêm thao tác close không có ý nghĩa.

## 8. @PreDestroy, DisposableBean, AutoCloseable và @Bean destroyMethod

Các cơ chế này khác nhau về **ai kích hoạt** và **khi nào áp dụng**.

| Cơ chế | Ai gọi trong tình huống thích hợp? | Lưu ý |
| --- | --- | --- |
| `@PreDestroy` | Spring destruction processing cho bean thuộc diện được hủy | Không tự gọi với prototype chỉ vì context đóng |
| `DisposableBean.destroy()` | Spring khi bean được destroy đúng lifecycle | Gắn mã nguồn với API Spring |
| `@Bean(destroyMethod = "cleanup")` | Spring khi destroy bean được định nghĩa bằng `@Bean` và có callback phù hợp | Chỉ hoạt động khi lifecycle destruction thực sự được thực thi |
| `@Bean(destroyMethod = "close")` | Spring gọi method `close` khi bean cần destroy | Rõ ràng cho bean singleton sở hữu resource |
| `@Bean` mặc định, đối tượng có `close()` hoặc `shutdown()` public | Spring có thể suy luận destruction method | Có cơ chế inference mặc định; không đồng nghĩa mọi instance ngoài container được đóng |
| `AutoCloseable.close()` | Java `try-with-resources` hoặc mã gọi trực tiếp; Spring có thể dùng khi cấu hình bean | Bản thân interface không tạo lịch tự hủy cho prototype |
| `finally { resource.close(); }` | Code ứng dụng | Phù hợp khi quản lý lifecycle theo phạm vi riêng |

### 8.1. @Bean tự suy luận close/shutdown: điều cần tránh

Với Java configuration trong Spring Framework 6.1, `@Bean` có destroy method mặc định dạng **inferred**. Container có thể phát hiện phương thức `close()` hoặc `shutdown()` public, không tham số trên bean thực tế và gọi khi destroy bean do container quản lý.

```java
@Bean
ExternalClient client() {
    return new ExternalClient(); // giả định có public close()
}
```

Trong tình huống bean singleton được container sở hữu, Spring có thể tự gọi `close()` lúc context đóng dù bạn không ghi `destroyMethod="close"`. Đó là hành vi có ích cho client/pool được ứng dụng sở hữu, nhưng cũng có thể là **lỗi ownership** nếu client thực tế là một tài nguyên chung **được mượn** từ hệ thống khác.

Nếu chỉ muốn **tắt suy luận close/shutdown** cho bean do `@Bean` tạo:

```java
@Bean(destroyMethod = "")
ExternalClient borrowedClient() {
    return externallyManagedClient;
}
```

Đây là đoạn minh họa; `externallyManagedClient` là biến/object được bên ngoài cung cấp. **Cẩn thận:** `destroyMethod=""` chỉ tắt custom destroy-method inference; nó không nhất thiết loại bỏ mọi destruction callback, ví dụ `DisposableBean` hoặc `@PreDestroy` vẫn có thể được xử lý. Nếu object thuộc sở hữu bên khác, cần xem hợp đồng và tránh đăng ký nhầm các callback gây đóng tài nguyên chung.

### 8.2. Không “gọi annotation” bằng tay

`@PreDestroy` chỉ là metadata. Khi bạn trực tiếp gọi `resource.close()`, Java không tự thực thi phương thức mang `@PreDestroy` nếu đó là hai method khác nhau. Ngược lại, Spring gọi `@PreDestroy` không có nghĩa tự động gọi mọi resource con: chính method callback phải đóng resource hoặc bean cần có destroy callback phù hợp.

Tránh tạo hai đường cleanup cùng đóng một tài nguyên một cách không kiểm soát. Thiết kế idempotent khi cần, và chọn một ownership path rõ ràng.

## 9. Khi cần Spring hỗ trợ hủy một prototype cụ thể

Spring Framework có API hủy bean theo yêu cầu, ví dụ `ConfigurableBeanFactory.destroyBean(String beanName, Object beanInstance)`, để áp dụng quy tắc hủy theo bean definition cho một instance, thường là prototype. Đây là **hành động rõ ràng của caller**, khác với việc container tự dọn tất cả prototype lúc shutdown.

Ví dụ minh họa ý tưởng:

```java
ConfigurableBeanFactory factory = context.getBeanFactory();
MyPrototype instance = context.getBean(MyPrototype.class);

try {
    instance.doWork();
} finally {
    factory.destroyBean("myPrototype", instance);
}
```

Đây là **đoạn minh họa**, không phải file độc lập: `context` cần là `ConfigurableApplicationContext`, `MyPrototype` cần được đăng ký dưới bean name tương ứng, và các import phải có. API `destroyBean` có thể kích hoạt callback Spring phù hợp trên instance, bao gồm những callback khác với một lệnh `close()` trực tiếp. Hãy hiểu method/scope và chỉ dùng **một cơ chế ownership** để tránh dọn hai lần. Với ứng dụng đơn giản, tài nguyên triển khai `AutoCloseable` và caller dùng `try-with-resources` thường dễ bảo trì hơn.

Một số ứng dụng chuyên biệt có thể viết custom scope hoặc bean post-processor theo dõi prototype cần hủy. Việc lưu mọi prototype vào danh sách toàn cục để đóng khi shutdown cần xét **giữ tham chiếu gây tăng bộ nhớ, đồng bộ giữa các thread, thời điểm resource thực sự hết hạn và nguy cơ double-close**.

Không nên giải quyết vấn đề bằng cách đơn giản đổi toàn bộ prototype thành singleton: singleton dùng chung có thể sai về trạng thái, thread safety và cách ly dữ liệu.

## 10. Shutdown bình thường và shutdown đột ngột

Ngay cả với singleton, câu “Spring tự đóng” cũng có điều kiện: ứng dụng phải có cơ hội thực hiện shutdown lifecycle.

| Tình huống | Độ tin cậy của Spring cleanup |
| --- | --- |
| Đóng context bằng `ConfigurableApplicationContext.close()` | Spring thực hiện quy trình shutdown/destroy cho bean đủ điều kiện |
| `try (ConfigurableApplicationContext ctx = ...)` | Gọi `close()` khi rời khối, kể cả lúc ném exception thông thường |
| SIGTERM với shutdown hook hoạt động bình thường | Có cơ hội chạy graceful shutdown và bean destruction theo cấu hình |
| `kill -9` / SIGKILL hoặc crash nặng | **Không** có cơ hội bảo đảm chạy callback Java/Spring |
| Mất điện, máy bị kill cưỡng bức, hết tài nguyên nghiêm trọng | Không thể bảo đảm callback được thực thi đầy đủ |
| Object prototype không có caller cleanup | Context shutdown **không tự khắc phục** việc thiếu cleanup |

Vì vậy những tài nguyên bên ngoài cần thiết kế chịu được crash: database transaction/lease timeout, idempotency, retry, broker redelivery hoặc timeout của connection. Shutdown callback hữu ích cho quá trình dừng bình thường; nó không phải cơ chế duy nhất bảo đảm tính đúng đắn dữ liệu.

**Đóng JVM và GC:** hệ điều hành sẽ thu hồi nhiều loại tài nguyên của tiến trình khi tiến trình thực sự kết thúc, nhưng điều đó không thay thế việc release đúng hạn trong một tiến trình còn chạy và không bảo đảm hoàn tất protocol/application-level cleanup. Java GC cũng không hứa hẹn gọi `close` hoặc `@PreDestroy` đúng lúc.

## 11. Các lỗi thường gặp

| Dấu hiệu hoặc phát biểu | Sai ở đâu? | Hướng xử lý |
| --- | --- | --- |
| “Bean prototype có `@PreDestroy` thì Spring sẽ gọi khi dừng app” | Prototype không được container theo dõi để hủy tập trung | Caller quản lý cleanup hoặc gọi API destroy rõ ràng |
| “Có `@PostConstruct` nghĩa là sẽ có `@PreDestroy`” | Init và destroy là hai pha có contract khác nhau | Xem scope và ownership |
| “Chỉ cần `AutoCloseable` là đóng context sẽ tự đóng mọi instance” | Interface không tạo quyền sở hữu hay tracking cho mọi prototype | Dùng `try-with-resources` hoặc owner tương ứng |
| “Mọi object `new` trong bean được Spring quản lý riêng” | Chỉ owner bean được đăng ký; field/resource con không tự là bean | Đóng resource trong lifecycle callback của owner |
| “`new` trong `@Bean` chắc chắn nằm ngoài Spring” | Instance được trả về từ `@Bean` có thể là bean được quản lý | Xem scope, bean definition và destroy method |
| “`@Bean(destroyMethod="")` tắt mọi cleanup” | Chỉ tắt destroy-method inference/custom method đó, các callback khác vẫn có thể hoạt động | Kiểm tra `@PreDestroy`, `DisposableBean` và ownership |
| “Prototype inject vào singleton sẽ luôn tạo mới mỗi lần gọi” | Dependency thường resolve một lần khi dựng singleton | Dùng `ObjectProvider` khi cần instance mới cho mỗi tác vụ |
| “Có Spring context thì không cần close InputStream” | Stream theo tác vụ không tự thuộc lifecycle context | Dùng `try-with-resources` tại điểm sở hữu |
| “Đóng resource ngay sau getBean là luôn an toàn” | Resource có thể được mượn/chia sẻ cho caller khác | Xác định owner; tránh close tài nguyên chung quá sớm |
| “Đóng prototype rồi chắc chắn `@PreDestroy` đã chạy” | `close()` Java khác callback Spring | Chọn cơ chế cụ thể và kiểm chứng log |
| “Spring chắc chắn chạy cleanup sau SIGKILL” | Process không có cơ hội chạy hook | Thiết kế timeout và phục hồi sau crash |
| “Cứ giữ tất cả prototype trong list để đóng khi JVM tắt” | Có thể giữ tham chiếu lâu quá mức và dọn sai thời điểm | Thiết kế lifetime theo scope tác vụ |

### 11.1. Checklist điều tra rò rỉ tài nguyên

1. Xác định đối tượng đó **thực sự là bean** hay chỉ được tạo bằng `new`.
2. Xem **scope** và nơi gọi `getBean`; đối với prototype, tìm caller nhận instance.
3. Xem đối tượng sở hữu gì: file/socket, thread, session, pool hay chỉ dữ liệu thuần.
4. Tìm lệnh release tương ứng như `close`, `shutdown`, `dispose` và kiểm tra nó có chạy trong cả luồng thành công lẫn exception.
5. Nếu Spring phải destroy singleton, xác nhận lifecycle shutdown bình thường và annotation/`destroyMethod` hợp lệ.
6. Nếu bean được trả từ `@Bean`, xem destroy-method inference và tránh vô tình đóng object mượn.
7. Với prototype trong singleton, xem có cần `ObjectProvider`/lookup và thời điểm dọn từng instance.
8. Khi điều tra bằng log, ghi **ID resource và mốc acquired/released**; không in secret, connection string chứa credential hoặc dữ liệu nhạy cảm.

## 12. Tự kiểm tra

**Câu 1.** Một bean prototype có `@PostConstruct` và `@PreDestroy`. Khi context đóng, callback nào chắc chắn không được container tự gọi theo quy tắc prototype?

**Đáp:** Destruction callback `@PreDestroy` không được tự gọi cho từng prototype lúc context đóng. `@PostConstruct` đã chạy khi từng instance được Spring khởi tạo.

**Câu 2.** Hai lần `context.getBean(MyPrototype.class)` thường trả mấy instance?

**Đáp:** Hai instance với bean prototype thông thường. Mỗi instance cần được quản lý theo thời gian sử dụng thực tế nếu giữ tài nguyên.

**Câu 3.** Dùng `try (MyPrototype p = provider.getObject())` có tự kích hoạt `@PreDestroy` không?

**Đáp:** Không. Java gọi `AutoCloseable.close()` trên `p`; `@PreDestroy` là callback khác do Spring xử lý khi có destruction processing.

**Câu 4.** Vì sao một object được tạo bằng `new` bên trong phương thức `@Bean` có thể được Spring đóng?

**Đáp:** Vì instance được **trả về và đăng ký thành bean**. Với singleton và destroy method thích hợp, Spring có quyền thực hiện lifecycle callback. Constructor dùng `new` không phải ranh giới duy nhất.

**Câu 5.** Một singleton tự tạo `ExecutorService` trong field. Spring có tự gọi `shutdown()` cho field đó không?

**Đáp:** Không, trừ khi executor được đăng ký/quản lý riêng hoặc owner bean chủ động gọi `shutdown()` trong callback hủy của chính nó.

**Câu 6.** `@Bean(destroyMethod="")` giúp làm gì, và chưa làm gì?

**Đáp:** Nó tắt cơ chế suy luận destroy method dạng `close/shutdown` cho `@Bean` đó; nó không bảo đảm vô hiệu hóa `@PreDestroy` hay `DisposableBean`.

**Câu 7.** Vì sao singleton inject một prototype không có nghĩa mỗi request có một instance?

**Đáp:** Dependency được giải quyết khi singleton được tạo; singleton có thể giữ cùng prototype. Muốn một instance cho từng tác vụ, dùng provider/lookup và cleanup theo tác vụ.

**Câu 8.** Khi JVM bị SIGKILL, có thể dựa vào `@PreDestroy` để gửi thông điệp kết thúc transaction không?

**Đáp:** Không. Cần thiết kế cơ chế nhất quán/timeout/phục hồi cho lỗi đột ngột; callback chỉ là một phần shutdown bình thường.

## 13. Ghi nhớ và tài liệu tham khảo

- **Singleton được container sở hữu:** Spring có thể chạy destruction callback khi context đóng bình thường.
- **Prototype:** Spring làm initialization, bàn giao instance rồi **không tự gọi destruction callback cho từng instance** khi context đóng. Caller phải xử lý cleanup nếu có tài nguyên cần release.
- **Object ngoài container:** `new` ngoài cơ chế đăng ký bean không mang lifecycle Spring; `@PreDestroy` trên class không tự có tác dụng.
- **@Bean và ownership:** một object tạo bằng `new` nhưng trả về từ `@Bean` vẫn có thể do Spring quản lý; kiểm tra scope và destroy method.
- **AutoCloseable và @PreDestroy khác nhau:** `try-with-resources` gọi `close`; Spring destruction processing mới kích hoạt callback Spring tương ứng.
- **Resource lifetime theo người sở hữu:** acquisition và cleanup cần được ghép trong cùng một vòng đời hợp lý, không tùy tiện dựa vào GC hoặc JVM shutdown.

Tài liệu chính thức:

- [Spring Framework — Bean Scopes: Prototype Scope](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html) — xác nhận prototype init nhưng container không tự gọi destruction callback.
- [Spring Framework — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html) — `@Bean(destroyMethod=...)` và suy luận `close/shutdown`.
- [Spring Framework 6.1 — Bean Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Bean.html) — contract về destroy-method inference và `destroyMethod=""`.
- [Spring Framework 6.1 — ConfigurableBeanFactory](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/config/ConfigurableBeanFactory.html) — `destroyBean(beanName, instance)` khi cần explicit destruction.

Để chẩn đoán đúng, luôn hỏi: **Spring đang quản lý bean definition, instance, scope hay chỉ một object được tham chiếu từ bean khác?** Và quan trọng hơn: **ai là chủ sở hữu có trách nhiệm release tài nguyên ở thời điểm nào?**
