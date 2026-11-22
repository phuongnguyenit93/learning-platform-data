# AutoCloseable và cơ chế suy luận phương thức hủy của @Bean trong Spring Boot

## 1. Vấn đề: tạo bean xong thì ai giải phóng tài nguyên?

Trong một ứng dụng Spring Boot, không phải mọi đối tượng chỉ chứa dữ liệu và được garbage collector xử lý. Một số đối tượng nắm giữ **tài nguyên cần đóng có chủ đích**, ví dụ connection pool, HTTP client, message producer, file handle, timer, thread pool hoặc một client SDK có phiên làm việc dài hạn.

Đối tượng Java có thể cung cấp phương thức **close()**, **shutdown()** hoặc **release()** để giải phóng tài nguyên. Khi đối tượng đó được trả về từ một method **@Bean**, Spring Framework cần biết có nên tự gọi phương thức hủy khi ApplicationContext đóng không.

Ví dụ tưởng tượng:

~~~java
@Bean
RemoteClient remoteClient() {
    return new RemoteClient();
}
~~~

Nếu **RemoteClient** có phương thức **public void close()**, Spring thường **tự nhận biết** phương thức này khi đăng ký destruction callback cho bean. Bạn **không bắt buộc** viết **@Bean(destroyMethod = "close")** cho trường hợp thông thường.

Cơ chế đó được gọi là **destroy method inference**: suy luận phương thức hủy. Nó gắn với vòng đời bean do container quản lý, không phải phép màu của garbage collector hay một thread tự động phát hiện leak.

Các câu hỏi quan trọng mà bài này trả lời:

1. **AutoCloseable** và **Closeable** đóng vai trò gì với tài nguyên Java?
2. Vì sao **@Bean** không khai báo destroyMethod vẫn có thể gọi **close()** hoặc **shutdown()**?
3. Khác biệt giữa **destroyMethod mặc định**, **destroyMethod = "cleanup"** và **destroyMethod = ""**?
4. Khi có đồng thời **@PreDestroy**, **DisposableBean** và phương thức hủy suy luận, thứ tự ra sao?
5. Có phải Spring đóng mọi instance, mọi scope và mọi tài nguyên được trả về qua @Bean không?
6. Khi nào nên **ngăn Spring tự đóng một tài nguyên do bên ngoài sở hữu**?

**Phạm vi ví dụ:** Spring Boot 3.5.x, Spring Framework 6.2.x và Java 17+. Đây là cơ chế của **Spring Framework bean lifecycle** được Spring Boot sử dụng khi quản lý ApplicationContext.

## 2. AutoCloseable là gì trong Java?

Interface có tên **java.lang.AutoCloseable**, được Java thiết kế cho tài nguyên cần đóng.

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

**AutoCloseable.close()** biểu diễn hành động giải phóng tài nguyên. Nó cho phép code Java dùng **try-with-resources** để tự gọi close ở cuối khối try, kể cả khi xảy ra exception.

Ví dụ Java tiêu chuẩn, độc lập với Spring:

~~~java
public class PlainAutoCloseDemo {

    static final class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("resource.close()");
        }

        void use() {
            System.out.println("resource.use()");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            resource.use();
        }

        System.out.println("after try");
    }
}
~~~

Lưu file **PlainAutoCloseDemo.java**, chạy:

~~~bash
javac PlainAutoCloseDemo.java
java PlainAutoCloseDemo
~~~

Output chính xác:

~~~text
resource.use()
resource.close()
after try
~~~

Ở ví dụ này **Java compiler và try-with-resources** làm việc gọi close. **Không có Spring ApplicationContext**.

### AutoCloseable và java.io.Closeable

**java.io.Closeable** cũng cung cấp **close()**, nhưng kế thừa **AutoCloseable**. Closeable phù hợp với I/O resources và có contract IOException cụ thể, trong khi AutoCloseable tổng quát hơn.

| API | Mục đích | Kiểu exception khai báo |
| --- | --- | --- |
| **AutoCloseable** | Tài nguyên bất kỳ cần cleanup | **Exception** |
| **Closeable** | Tài nguyên I/O và tương tự | **IOException** |
| **DisposableBean** | Callback hủy gắn trực tiếp với Spring | **Exception** |
| **@PreDestroy** | Lifecycle callback qua annotation Jakarta | Tùy chữ ký hợp lệ và Spring processor |
| **@Bean(destroyMethod)** | Chỉ định/suy luận method cleanup từ bean metadata | Theo method được chọn |

Nếu một bean do Spring **sở hữu vòng đời**, Spring có thể gọi close khi đóng context. Việc bean implements AutoCloseable **không** khiến JVM tự gọi close nếu bạn chỉ viết **new Resource()** và bỏ reference. Trách nhiệm giải phóng phụ thuộc vào **ai thực sự sở hữu resource**.

## 3. @Bean mặc định suy luận phương thức hủy như thế nào?

Annotation **org.springframework.context.annotation.Bean** có thuộc tính:

~~~java
String destroyMethod() default "(inferred)";
~~~

Đây là chữ ký rút gọn từ JavaDoc Spring Framework 6.2, không phải lời gọi method trong code ứng dụng. Giá trị mặc định đặc biệt **"(inferred)"** yêu cầu container tìm phương thức hủy thích hợp.

Trong Spring Framework 6.2, phạm vi suy luận theo JavaDoc gồm **các public methods không tham số mang tên close hoặc shutdown**, kể cả nếu method kế thừa từ superclass. Những bean implements **AutoCloseable** hoặc **Closeable** khớp rất tự nhiên vì có **close()**.

**Ví dụ 1 — bean implements AutoCloseable:**

~~~java
final class FileLikeClient implements AutoCloseable {
    @Override
    public void close() {
        System.out.println("FileLikeClient.close()");
    }
}

@Bean
FileLikeClient fileLikeClient() {
    return new FileLikeClient();
}
~~~

Đây là hai mảnh code minh họa được đặt trong những lớp phù hợp, không phải một file chạy độc lập. Vì method **@Bean** dùng destroyMethod mặc định, container có thể tự đăng ký callback **close()**.

**Ví dụ 2 — bean không implements AutoCloseable nhưng có shutdown():**

~~~java
final class BackgroundClient {
    public void shutdown() {
        System.out.println("BackgroundClient.shutdown()");
    }
}

@Bean
BackgroundClient backgroundClient() {
    return new BackgroundClient();
}
~~~

Phương thức **shutdown()** công khai, không tham số có thể được suy luận làm destroy method dù class không implements AutoCloseable.

**Ví dụ 3 — có method cleanup() tùy ý:**

~~~java
final class LegacyClient {
    public void release() {
        System.out.println("LegacyClient.release()");
    }
}

@Bean(destroyMethod = "release")
LegacyClient legacyClient() {
    return new LegacyClient();
}
~~~

Vì method được đặt tên **release**, Spring **không tự suy luận theo tên này**; cần khai báo rõ **destroyMethod = "release"**.

**Giới hạn suy luận:** đừng nghĩ Spring thử mọi method kiểu **dispose, clear, delete, terminate**. Với @Bean mặc định, các tên suy luận được tài liệu công bố chỉ là **close** hoặc **shutdown** công khai, không tham số. Khi muốn method khác, phải chỉ định rõ.

### Spring xét class trả về hay instance thật?

Một chi tiết trong JavaDoc: detection có thể kiểm tra phản chiếu trên **class của bean instance được tạo**, không nhất thiết chỉ giới hạn ở kiểu khai báo trả về của method @Bean.

Ví dụ:

~~~java
interface Client {
    void request();
}

final class RealClient implements Client, AutoCloseable {
    @Override
    public void request() {
    }

    @Override
    public void close() {
        System.out.println("RealClient.close()");
    }
}

@Bean
Client client() {
    return new RealClient();
}
~~~

Đây là mảnh minh họa, cần đặt vào project với các lớp/import hợp lệ. Dù method **@Bean** trả kiểu interface **Client** không khai báo close, instance thật là **RealClient** có close công khai và implements AutoCloseable. Theo JavaDoc @Bean 6.2, suy luận có thể tìm method của instance đó.

Tuy nhiên không nên xây thiết kế cleanup phụ thuộc vào loại proxy, factory hoặc runtime class không được kiểm soát. Với API được sở hữu rõ ràng, **implements AutoCloseable** hoặc **destroyMethod khai báo tường minh** giúp contract dễ hiểu hơn.

## 4. Khi nào cơ chế hủy chạy?

Với bean **singleton thuộc quyền quản lý đầy đủ của ApplicationContext**, destruction callbacks thường chạy trong quá trình context **close()**, bao gồm khi Spring Boot thực hiện shutdown bình thường.

Dòng thời gian đơn giản:

~~~text
SpringApplication.run(args)
        |
        v
Tạo ApplicationContext
        |
        v
Register/parse BeanDefinitions, refresh
        |
        v
Tạo singleton bean instance
        |
        +--> @PostConstruct / init callbacks
        |
        v
Ứng dụng hoạt động
        |
        v
ApplicationContext.close()
        |
        +--> Dừng Lifecycle / SmartLifecycle components
        |
        +--> Hủy singleton beans theo dependency/lifecycle
        |      @PreDestroy
        |      DisposableBean.destroy() (nếu có)
        |      inferred/explicit custom destroy method
        |
        v
Context đóng, các tài nguyên được giải phóng
~~~

Một bean đã khởi tạo **không tự được hủy sau khi @Bean factory method trả về**. Việc hủy gắn với thời điểm scope kết thúc và contract của container.

### Trường hợp Spring Boot web application

Trong ứng dụng Spring Boot chạy lâu dài, SpringApplication thường đăng ký JVM shutdown hook để đóng context khi JVM shutdown bình thường. Vì thế **không cần tự gọi close() cho từng bean singleton** nếu chúng thuộc quyền sở hữu của context và các callbacks được cấu hình đúng.

Nhưng **không có bảo đảm tuyệt đối** nếu process bị **SIGKILL**, máy mất nguồn, JVM crash hoặc container bị force-kill trước khi hết termination grace. Thiết kế dữ liệu nghiệp vụ và xử lý side effects phải chịu được trường hợp cleanup không xảy ra.

### Khác với garbage collection

Garbage collector quản lý bộ nhớ heap, không thay thế đầy đủ việc đóng socket, file descriptor, connection pool hoặc khả năng flush/ack message. **AutoCloseable không phải finalizer** và inferred destroy method không chạy vì một object "không còn được tham chiếu". Nó là callback từ **Spring BeanFactory khi bean bị destroy đúng quy trình**.

## 5. Ba cách cấu hình destroyMethod

| Cách khai báo | Ý nghĩa | Ví dụ ứng dụng |
| --- | --- | --- |
| **@Bean** | Dùng mặc định **"(inferred)"** để tìm public no-arg close/shutdown | Client/pool do Spring sở hữu |
| **@Bean(destroyMethod = "close")** | Chỉ định rõ close làm method hủy | Muốn contract tường minh |
| **@Bean(destroyMethod = "shutdown")** | Chỉ định rõ shutdown | Scheduler/service có shutdown |
| **@Bean(destroyMethod = "release")** | Chỉ định method khác do class cung cấp | Legacy SDK có release |
| **@Bean(destroyMethod = "")** | Tắt việc suy luận custom close/shutdown cho bean này | Tài nguyên được owner bên ngoài quản lý |

### destroyMethod="" thực sự vô hiệu hóa điều gì?

Theo JavaDoc @Bean 6.2, đặt:

~~~java
@Bean(destroyMethod = "")
ExternalClient externalClient() {
    return externallyManagedClient;
}
~~~

làm Spring **không tự suy luận gọi close hoặc shutdown** trên bean này chỉ vì nó có method tương ứng. Tuy nhiên nó **không có nghĩa vô hiệu hóa mọi cơ chế destroy**.

Đặc biệt:

- Nếu bean implements **DisposableBean**, callback **destroy()** vẫn có thể được Spring phát hiện và gọi.
- Nếu bean có method **@PreDestroy**, lifecycle processing tương ứng vẫn có thể gọi nó.
- Nếu bean implements **SmartLifecycle**, giai đoạn **stop** là một contract khác và có thể chạy trước destroy callbacks.
- Nếu scope hoặc custom scope có cơ chế destruction riêng, phải xem contract của scope/BeanFactory.

Vì vậy **@Bean(destroyMethod = "")** là công cụ để **vô hiệu hóa inferred custom close/shutdown**, không phải một "nút tắt mọi cleanup".

### Khi nào nên tắt suy luận?

Ví dụ ứng dụng được cấp một HTTP client chia sẻ bởi framework khác:

~~~java
@Bean(destroyMethod = "")
SharedHttpClient sharedHttpClient() {
    return externalClientRegistry.getSharedClient();
}
~~~

Đây là mảnh minh họa, cần các type và registry thật. Nếu Spring chỉ **mượn** client còn hệ thống khác vẫn sử dụng sau khi context đóng, Spring không nên tự close client đó. **Owner bên ngoài** chịu trách nhiệm đóng đúng thời điểm.

Ngược lại, nếu Spring **tạo client mới** từ factory method và là owner của client đó, dùng **@Bean** mặc định để đóng auto resource thường đơn giản và an toàn hơn.

**Đừng dùng destroyMethod="" để che lỗi cleanup chậm hoặc exception.** Nếu Spring thật sự sở hữu resource, việc vô hiệu hóa close có thể để lại socket, worker thread hoặc connection pool chưa giải phóng.

## 6. Ví dụ runnable Java 17+: kiểm tra inference và quyền sở hữu resource

Ví dụ này tạo một Spring Boot application **non-web** với hai bean:

1. **TrackedResource** do Spring tạo, implements **AutoCloseable** và có **@PreDestroy**. Không ghi destroyMethod; Spring tự suy luận close khi context đóng.
2. **BorrowedChannel** được tạo bởi bên sở hữu ngoài BeanFactory, Spring chỉ mượn để đăng ký làm bean. Method @Bean đặt **destroyMethod = ""** để tránh Spring tự close; chính owner đóng nó sau khi context đóng.

Mục tiêu là quan sát thứ tự callbacks **một cách xác định**, không phụ thuộc vào thứ tự hủy của hàng chục bean khác.

### 6.1. Tạo project

Dùng **Spring Initializr**, chọn:

- **Maven**, **Java 17+**.
- **Spring Boot 3.5.x**.
- Group **com.example**, artifact **bean-cleanup-demo**, package **com.example.demo**.
- Dependency **Spring Boot Starter**.

Không cần Spring Web. Giữ POM và Maven Wrapper do Initializr sinh. Java 17+ phù hợp với Spring Framework 6.2 và package **jakarta.annotation.PreDestroy**.

### 6.2. File Java hoàn chỉnh

Tạo **src/main/java/com/example/demo/BeanCleanupDemoApplication.java**:

~~~java
package com.example.demo;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BeanCleanupDemoApplication {

    // Demo: main là owner; Spring chỉ mượn instance này.
    private static final BorrowedChannel EXTERNAL_CHANNEL =
            new BorrowedChannel();

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(BeanCleanupDemoApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);

        System.out.println("01 | before run");

        try (ConfigurableApplicationContext context = app.run(args)) {
            // Singleton thông thường đã được tạo khi refresh.
            context.getBean(TrackedResource.class);
            System.out.println("03 | context active="
                    + context.isActive());
        }

        System.out.println("06 | context closed");

        // Chỉ owner bên ngoài BeanFactory mới close resource mượn.
        EXTERNAL_CHANNEL.close();
        System.out.println("08 | external owner finished");
    }

    @Bean
    TrackedResource trackedResource() {
        return new TrackedResource();
    }

    @Bean(destroyMethod = "")
    BorrowedChannel borrowedChannel() {
        return EXTERNAL_CHANNEL;
    }

    static final class TrackedResource implements AutoCloseable {

        TrackedResource() {
            System.out.println("02 | TrackedResource created");
        }

        @PreDestroy
        void beforeDestroy() {
            System.out.println("04 | @PreDestroy");
        }

        @Override
        public void close() {
            System.out.println("05 | inferred close()");
        }
    }

    static final class BorrowedChannel implements AutoCloseable {

        private boolean closed;

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("07 | owner closes BorrowedChannel");
            }
        }
    }
}
~~~

**Tại sao ví dụ này có thể biên dịch?**

- Public class **BeanCleanupDemoApplication** khớp filename.
- **@SpringBootApplication** và **@Bean** thuộc Spring Boot/Framework dependencies do starter cung cấp.
- **@PreDestroy** là annotation Jakarta; không dùng package **javax.annotation** từ Java 8 thời cũ.
- Hai lớp con là **static nested classes** nên @Bean factory methods tạo được mà không cần outer instance cho từng resource.
- **TrackedResource.close()** là public theo contract AutoCloseable, được Spring suy luận.
- **BorrowedChannel** cũng có public close, nhưng bean definition của nó đã đặt **destroyMethod = ""** để ngăn suy luận.
- Main dùng **try-with-resources** với **ConfigurableApplicationContext**; khi rời khối, Java gọi context.close(), còn Spring gọi destruction callbacks của bean nó sở hữu.
- Không tạo resource bằng **new** rồi bỏ quên cleanup; resource mượn được owner close tường minh sau khi context đóng.

**Lưu ý quan trọng:** ví dụ giả định TrackedResource là singleton không lazy như mặc định. Nếu đổi scope sang prototype hoặc đặt lazy không bao giờ tạo, kết quả callback khác; mục 10 phân tích trường hợp này.

### 6.3. Chạy thử

Từ thư mục Maven:

~~~bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell/cmd:
# .\mvnw.cmd spring-boot:run
~~~

Các dòng **do chương trình chủ động in**, theo thứ tự:

~~~text
01 | before run
02 | TrackedResource created
03 | context active=true
04 | @PreDestroy
05 | inferred close()
06 | context closed
07 | owner closes BorrowedChannel
08 | external owner finished
~~~

Spring Boot/Maven có thể in thêm log; đây là các dòng của demo được lọc lại. Vì không có bean khác in các dòng số thứ tự tương tự và close được gọi đồng bộ, thứ tự những dòng này là xác định trong một startup/shutdown thành công.

**Diễn giải:**

- **01:** main trước SpringApplication.run.
- **02:** Spring khởi tạo TrackedResource trong refresh.
- **03:** SpringApplication.run đã trả về; context vẫn active.
- **04:** Khi đóng context, Spring xử lý @PreDestroy của TrackedResource.
- **05:** Inferred destroy method gọi close() trên TrackedResource sau @PreDestroy.
- **06:** context.close đã hoàn thành.
- **07:** Owner ở ngoài container chủ động đóng BorrowedChannel; đây **không phải** callback do Spring tạo.
- **08:** main kết thúc.

Dòng **07** chỉ xảy ra vì main **tự gọi** EXTERNAL_CHANNEL.close(). Nếu bỏ lời gọi đó, Spring **không tự close BorrowedChannel** vì destroyMethod đã bị tắt; owner phải có chính sách quản lý riêng.

### 6.4. Biến thể để tự kiểm chứng destroyMethod

**Biến thể A — bật inference cho BorrowedChannel.** Đổi:

~~~java
@Bean(destroyMethod = "")
BorrowedChannel borrowedChannel() {
    return EXTERNAL_CHANNEL;
}
~~~

thành:

~~~java
@Bean
BorrowedChannel borrowedChannel() {
    return EXTERNAL_CHANNEL;
}
~~~

Khi context đóng, Spring sẽ có thể gọi **BorrowedChannel.close()**; nếu main vẫn đóng nó sau đó thì method có thể bị gọi hai lần. Class trong demo có guard **closed** nên chỉ in dòng 07 một lần, **nhưng điều đó không chứng minh close chỉ được gọi một lần**. Đây là lý do không chuyển ownership tùy tiện: một HTTP client thật có thể phản ứng khác khi bị close trùng.

**Biến thể B — tắt inference cho TrackedResource.** Đổi:

~~~java
@Bean
TrackedResource trackedResource() {
    return new TrackedResource();
}
~~~

thành:

~~~java
@Bean(destroyMethod = "")
TrackedResource trackedResource() {
    return new TrackedResource();
}
~~~

Khi close context, **@PreDestroy vẫn chạy** nhưng **inferred close() không còn được gọi theo mặc định**. Đây là ví dụ quan trọng: **destroyMethod = "" không vô hiệu hóa @PreDestroy**, nhưng nó có thể khiến tài nguyên thật không được close nếu không có owner khác.

Không áp dụng hai biến thể cùng lúc mà vẫn kỳ vọng stdout của ví dụ gốc còn chính xác.

## 7. @Bean(destroyMethod = "shutdown") và suy luận shutdown()

Nếu class không implements AutoCloseable mà có public no-argument **shutdown()**, Spring vẫn có thể suy luận nó ở mode mặc định.

~~~java
public final class MessageClient {
    private boolean running = true;

    public void send(String value) {
        if (!running) {
            throw new IllegalStateException("already shut down");
        }
        System.out.println("send: " + value);
    }

    public void shutdown() {
        if (running) {
            running = false;
            System.out.println("MessageClient.shutdown()");
        }
    }
}
~~~

Đây là class Java độc lập về mặt cú pháp, nhưng để dùng như Spring bean, khai báo trong một configuration class:

~~~java
@Bean
MessageClient messageClient() {
    return new MessageClient();
}
~~~

Hoặc nếu muốn rõ ràng:

~~~java
@Bean(destroyMethod = "shutdown")
MessageClient messageClient() {
    return new MessageClient();
}
~~~

**Hai @Bean snippets là hai lựa chọn thay thế nhau**, không khai báo cả hai với cùng tên trong một cấu hình. Khi ApplicationContext đóng và sở hữu singleton này, Spring có thể gọi shutdown().

### Khi method cleanup không phải close/shutdown

Một SDK có thể dùng **disconnect()** hoặc **release()**. Spring không tự suy luận những tên đó; chọn:

~~~java
@Bean(destroyMethod = "disconnect")
LegacyConnection legacyConnection() {
    return new LegacyConnection();
}
~~~

Mảnh minh họa này yêu cầu class **LegacyConnection** thật sự có method **disconnect()** phù hợp. Nếu đặt tên method không tồn tại, Spring có thể báo lỗi lifecycle/bean creation hoặc destroy callback configuration tùy API và phase; đừng coi đây là tùy chọn không có tác dụng.

### Có cần ghi destroyMethod = "(inferred)" tường minh?

Thông thường **không**: @Bean mặc định đã có giá trị **"(inferred)"**. Ghi lại giá trị này có thể hữu ích khi muốn truyền đạt intent, nhưng không làm cơ chế phát hiện mạnh hơn.

## 8. Thứ tự @PreDestroy, DisposableBean và custom destroy method

Một bean có thể tham gia nhiều cơ chế hủy:

1. Method đánh dấu **@PreDestroy**.
2. **DisposableBean.destroy()** của Spring (nếu implement).
3. Custom destroy method được cấu hình hoặc suy luận, ví dụ **close()**.

Spring Framework Reference mô tả thứ tự trên khi các cơ chế được cấu hình bằng **những method khác nhau**.

~~~text
ApplicationContext.close()
    |
    +--> @PreDestroy
    |
    +--> DisposableBean.destroy()
    |
    +--> custom/inferred destroy method
         close() / shutdown() / release()
~~~

Ví dụ minh họa các chữ ký:

~~~java
class CombinedResource implements DisposableBean, AutoCloseable {

    @PreDestroy
    public void beforeDestroy() {
        System.out.println("@PreDestroy");
    }

    @Override
    public void destroy() {
        System.out.println("DisposableBean.destroy()");
    }

    @Override
    public void close() {
        System.out.println("AutoCloseable.close()");
    }
}
~~~

Đây **không phải file Java độc lập**: phải import **jakarta.annotation.PreDestroy** và **org.springframework.beans.factory.DisposableBean**, đồng thời đăng ký bean với context. Trong các trường hợp bean implements DisposableBean, Spring có cơ chế tránh đăng ký/trùng callback khi suy luận destroy methods; **không được lấy đoạn này làm cam kết Spring luôn gọi cả destroy() lẫn close()**. Muốn cleanup cụ thể, chọn một contract rõ ràng thay vì chồng nhiều phương thức rồi đoán thứ tự.

**Quy tắc thực hành:** đừng để hai callbacks khác nhau cùng giải phóng một resource không idempotent. Nếu bắt buộc dùng nhiều callbacks, chúng phải có nhiệm vụ rõ ràng, hoặc method cleanup phải an toàn khi gọi lặp lại.

### Một method được khai báo qua nhiều cơ chế

Spring có logic tránh gọi lặp cùng method trong những trường hợp callback trùng nhau. Nhưng đừng dựa vào thứ tự phản chiếu, AOP proxies hoặc một giả định "luôn gọi close đúng hai lần". Hãy kiểm thử thực tế khi bean implements nhiều interface lifecycle đồng thời.

### @PreDestroy không tự suy luận tên close

Nếu bạn có:

~~~java
@PreDestroy
public void cleanUpBeforeShutdown() {
    // ...
}
~~~

thì callback này được đăng ký qua Jakarta annotation processing. Nó **khác** với inferred destroy method tìm theo tên close/shutdown. Cả hai có thể cùng tồn tại và thực hiện **những công việc riêng**.

## 9. Sự khác nhau giữa stop và destroy

Một số tài nguyên không chỉ cần đóng socket mà còn có luồng chạy nền cần dừng có kiểm soát. Spring cung cấp **Lifecycle** và **SmartLifecycle** để quản lý thứ tự start/stop, trong khi destroy method xử lý bước giải phóng cuối.

Ví dụ:

~~~text
Context đang hoạt động
     |
     v
Yêu cầu đóng ApplicationContext
     |
     +--> SmartLifecycle.stop(Runnable)
     |    Ngừng nhận việc, đợi in-flight tasks
     |    callback.run() khi đã stop
     |
     +--> @PreDestroy / DisposableBean.destroy
     |
     +--> Inferred close() hoặc explicit shutdown()
     |    Đóng kết nối, giải phóng tài nguyên cuối
     |
     v
Context đóng
~~~

**SmartLifecycle.stop(Runnable)** có contract callback và ordering theo phase; việc suy luận **close()/shutdown()** không thay thế cơ chế đó. Nếu bean có luồng xử lý background, nên phân biệt:

- **Quiesce:** ngừng nhận việc mới.
- **Drain:** đợi việc đang chạy với deadline thích hợp.
- **Dispose:** đóng tài nguyên.
- **Confirm:** báo hoàn tất và ghi metrics.

Không giả định chỉ cần AutoCloseable.close() là Spring sẽ tự đợi mọi Future hoàn tất. Method close phải tự thực thi contract thích hợp hoặc phối hợp lifecycle phase.

**Một rủi ro thường gặp:** một bean closes HTTP client trong @PreDestroy hoặc inferred close trong khi một consumer ở phase khác vẫn cần client để flush. Cần sắp xếp dependencies/SmartLifecycle phases và graceful shutdown budget phù hợp.

## 10. Bean scope quyết định container có hủy instance hay không

### Singleton (mặc định)

Với bean singleton thông thường do ApplicationContext quản lý, container giữ reference và đăng ký destruction callback. Khi context đóng bình thường, Spring gọi callback phù hợp. Đó là trường hợp demo ở mục 6.

Nếu bean singleton có **@Lazy**, nó có thể chỉ được khởi tạo khi lần đầu được truy cập. Khi chưa hề tạo instance, đương nhiên không có instance cụ thể để close; không nên khẳng định mọi @Bean definition đều dẫn đến một lần close.

### Prototype

Với **@Scope("prototype")**, Spring tạo và initialize mỗi instance được yêu cầu, nhưng **không quản lý đầy đủ quá trình destruction** của các prototype sau khi trả chúng cho caller.

~~~java
@Bean
@Scope("prototype")
ResourceSession resourceSession() {
    return new ResourceSession();
}
~~~

Đây là mảnh configuration minh họa, cần class ResourceSession và import Scope. Nếu mỗi lần getBean tạo ResourceSession mới implements AutoCloseable, **caller phải tự chịu trách nhiệm đóng instance đó**.

Ví dụ phương thức sử dụng:

~~~java
try (ResourceSession resource =
        context.getBean(ResourceSession.class)) {
    resource.perform();
}
~~~

Đây là mảnh minh họa, cần biến context, class ResourceSession implements AutoCloseable và method perform. Không suy luận rằng Spring sẽ tự close mọi prototype khi ApplicationContext đóng.

### Request/session/custom scopes

Các scope như request/session có lifecycle và destruction callback gắn với việc kết thúc scope, không đơn thuần là ApplicationContext.close. Một custom scope phải quản lý việc đăng ký/invoke destruction callback theo contract của nó. Cần đánh giá đúng loại scope và lifetime trong ứng dụng; đừng thay singleton/prototype bằng scope khác mà vẫn giữ nguyên giả định cleanup.

### Bean không do Spring tạo

Nếu code làm:

~~~java
ResourceSession resource = new ResourceSession();
~~~

mà không đưa object đó vào bean container, Spring không tự biết object để gọi destroy method. **AutoCloseable** chỉ là hợp đồng Java; Java code tạo ra object phải dùng try-with-resources hoặc close ở nơi thích hợp.

## 11. Quyền sở hữu tài nguyên quan trọng hơn việc có phương thức close

Một câu hỏi kiến trúc hữu ích hơn "class này có close hay không" là **"ai sở hữu quyền kết thúc vòng đời của tài nguyên?"**

| Nguồn tài nguyên | Ai nên đóng? | Cấu hình thường phù hợp |
| --- | --- | --- |
| Singleton được tạo mới trong @Bean, dùng riêng trong context | Spring ApplicationContext | @Bean mặc định suy luận close/shutdown |
| Singleton SDK client được Spring tạo và cần cleanup không tên chuẩn | Spring ApplicationContext | @Bean(destroyMethod = "release") |
| Instance do host/plugin container khác sở hữu, Spring chỉ mượn | Host/plugin container | @Bean(destroyMethod = "") nếu chỉ muốn tắt inferred close |
| Prototype tạo mỗi lần phục vụ tác vụ | Caller nhận instance | try-with-resources / close thủ công |
| Resource tạo trong method local không đăng ký bean | Method/caller tạo | try-with-resources |
| Client/pool được dùng chung qua nhiều ApplicationContexts | Owner thống nhất được chỉ định rõ | Tránh mỗi context đều tự close một shared instance |
| Tài nguyên được quản lý bởi thư viện có lifecycle riêng | Xem contract thư viện | Không gọi close hai lần theo giả định |

### Tình huống nguy hiểm: nhiều context cùng trả về một instance

Giả sử context A và context B đều đăng ký cùng object **sharedClient** từ các @Bean methods mặc định. Nếu một context đóng trước, nó có thể gọi **sharedClient.close()** dù context còn lại vẫn cần client.

Đây là vấn đề **ownership**, không phải bug của suy luận. Muốn chia sẻ tài nguyên giữa nhiều context, cần một owner rõ ràng, reference counting hoặc lifetime tập trung; có thể đặt **destroyMethod=""** ở các context chỉ mượn, nhưng owner thật vẫn phải close cuối cùng.

### Tình huống nguy hiểm: close tự động làm mất dữ liệu đang xử lý

Một message sender có method **shutdown()**, Spring suy luận tự động là hợp lý nếu sender chỉ được sở hữu bởi context. Tuy nhiên **shutdown()** của thư viện có thể không flush hết in-flight messages hoặc có timeout riêng. Việc Spring gọi method đúng lúc **không thay thế** chính sách graceful shutdown và đảm bảo delivery. Bạn vẫn phải đọc contract SDK, thiết kế drain/flush và kiểm thử khi có SIGTERM.

## 12. Vì sao không nên tạo tài nguyên "mượn" mà không tắt inference?

Mẫu dễ gặp:

~~~java
@Bean
AutoCloseable externalResource() {
    return ExternalRegistry.getSharedResource();
}
~~~

Nếu object thực có **public close()**, @Bean mặc định có thể suy luận close. Khi context đóng, Spring sẽ đóng object dù nó là shared resource của host bên ngoài.

Mẫu chủ động hơn:

~~~java
@Bean(destroyMethod = "")
AutoCloseable externalResource() {
    return ExternalRegistry.getSharedResource();
}
~~~

Hai snippets là **mẫu thiết kế minh họa**, cần ExternalRegistry và bean contract thật. Lựa chọn thứ hai ngăn inferred close. Nhưng nếu chính object còn implements **DisposableBean** hoặc có **@PreDestroy**, cần kiểm tra những callback khác; destroyMethod="" **không phải cơ chế hủy toàn diện**.

### Tránh dùng @Bean(destroyMethod="") vì sợ lỗi

Đừng tự tắt cleanup vì thấy lỗi "Connection closed" trong shutdown logs mà chưa xác định nguyên nhân. Lỗi đó có thể do:

- Dependency stop order sai.
- Client bị close bởi hai owners khác nhau.
- Một thread tiếp tục sử dụng client sau khi shutdown đã bắt đầu.
- Code gọi close quá sớm.
- Thời gian shutdown không đủ.
- Thư viện không xử lý close idempotent.

Nếu client thực sự do Spring sở hữu, giải pháp là **sửa ownership và shutdown order**; tắt inference vô điều kiện có thể khiến resource leak.

## 13. Lỗi phổ biến với inferred destruction

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Bean tự gọi close dù không viết destroyMethod | @Bean có default "(inferred)" | Kiểm tra public no-arg close/shutdown trên class thật |
| Muốn gọi release() nhưng không chạy | Không nằm trong tên được suy luận | Khai báo @Bean(destroyMethod = "release") |
| @Bean(destroyMethod = "") nhưng @PreDestroy vẫn chạy | Khác lifecycle mechanism | Kiểm tra và thiết kế từng callback riêng |
| @Bean(destroyMethod = "") nhưng DisposableBean.destroy vẫn chạy | Interface callback không bị tắt bởi attribute đó | Tránh giao resource này cho bean nếu không muốn callback |
| Prototype AutoCloseable không tự close khi context đóng | Prototype không được container theo dõi destruction đầy đủ | Caller tự close hoặc custom scope |
| Lazy bean chưa từng tạo nên không thấy close | Không có instance cụ thể | Tránh test giả định tất cả definitions đều instantiated |
| Class có private cleanup() nhưng Spring không suy luận | Chỉ tìm public no-arg close/shutdown | Chọn method/visibility và khai báo rõ |
| Class có public shutdown(int) nhưng không chạy | Có tham số, không phù hợp inference | Đổi contract hoặc explicit adapter |
| getBean trả về interface không có close, vẫn được close | Inference xét bean instance thực | Xem JavaDoc, đừng chỉ xét return type |
| Resource bị close hai lần | Nhiều owners hoặc callback bị lặp không được kiểm soát | Dùng một owner và idempotent close |
| Không có cleanup khi process bị SIGKILL | Không thực hiện orderly shutdown | Thiết kế recovery/idempotency, không dựa tuyệt đối vào @PreDestroy |
| @Component có close nhưng không thấy như @Bean | Khác nguồn đăng ký/bean definition metadata và interfaces | Kiểm tra cơ chế lifecycle thực tế; không suy luận tất cả beans giống hệt nhau |
| Shutdown mất nhiều giây hơn mong đợi | Close/blocking I/O không có deadline | Thiết kế client timeout, SmartLifecycle và graceful budget |
| Spring tự đóng client shared quá sớm | @Bean mặc định được giao tài nguyên mượn | Chuyển ownership hoặc tắt inferred close có chủ đích |

### Ghi log và kiểm tra cleanup

Khi cần điều tra một bean có bị close hay không, có thể log:

- Tên bean và thời điểm context close.
- Method hủy thực tế được gọi.
- Còn bao nhiêu tác vụ đang chạy.
- Trạng thái resource trước/sau close.
- Exception/elapsedMillis khi cleanup.
- Dependency chain và phase nếu dùng SmartLifecycle.

Không log secrets, credentials, payloads hoặc những object.toString() có thể lộ dữ liệu nhạy cảm.

## 14. Kiểm thử thực tế

### 14.1. Test suy luận close

Tạo một @Bean singleton với public close và dùng context close bình thường. Có thể dùng **AtomicBoolean** để ghi nhận close:

~~~java
final class CloseProbe implements AutoCloseable {

    private final AtomicBoolean closed = new AtomicBoolean();

    @Override
    public void close() {
        closed.set(true);
    }

    boolean isClosed() {
        return closed.get();
    }
}
~~~

Đây là mảnh Java minh họa cần import **java.util.concurrent.atomic.AtomicBoolean**. Test kỳ vọng:

~~~text
Trước context.close(): closed=false
Sau context.close():  closed=true
~~~

Để test chính xác, giữ reference tới bean trước khi đóng context và kiểm tra sau close. Không gọi getBean trên context đã đóng.

### 14.2. Test destroyMethod="" với borrowed resource

Cấp một resource mượn cho @Bean(destroyMethod=""), đóng context và xác minh **closed vẫn false**. Sau đó owner gọi close và kiểm tra true. Chỉ dùng resource không có callback khác (không implements DisposableBean, không @PreDestroy) nếu mục tiêu test là **riêng cơ chế inferred close**.

### 14.3. Test thứ tự callbacks

Với bean vừa có @PreDestroy vừa AutoCloseable.close và không có DisposableBean, Spring Framework Reference cho thứ tự:

~~~text
@PreDestroy
close() suy luận từ @Bean
~~~

Test cần tránh phụ thuộc vào thứ tự hủy **giữa các beans độc lập**, vì dependency graph và bean registration order có thể khác theo môi trường. Hãy khẳng định thứ tự callback **trong cùng bean** khi đúng contract.

### 14.4. Test failure path

Mô phỏng close() ném exception có kiểm soát. Ứng dụng nên log được bean/method lỗi và tiếp tục các bước shutdown theo behavior của container. Không đặt kỳ vọng cleanup chắc chắn hoàn tất nếu một callback bị chặn vô hạn hoặc JVM nhận SIGKILL.

### 14.5. Test resource ownership

Cùng một client được trả về cho hai contexts: cố ý đóng context A trước, sau đó thử dùng client từ context B. Nếu resource tự bị close gây lỗi, architecture đã có ownership conflict. Giải pháp không phải tăng shutdown timeout mà là đặt owner rõ ràng và tránh auto-close ở borrower context.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao một class implements AutoCloseable không có nghĩa JVM tự gọi close khi GC thu hồi đối tượng?

**Câu 2.** Bean được tạo từ @Bean không chỉ định destroyMethod, class thật có public shutdown() nhưng không implements AutoCloseable. Spring có thể gọi shutdown khi context đóng không?

**Câu 3.** Vì sao public release() không được suy luận như public close() hoặc public shutdown()?

**Câu 4.** Khi viết @Bean(destroyMethod = ""), điều này có tắt @PreDestroy và DisposableBean.destroy không?

**Câu 5.** Vì sao không thể coi "bean singleton được quản lý" và "prototype được cấp cho caller" là có cùng chính sách destruction?

**Câu 6.** Một service từ bên ngoài được chia sẻ cho hai contexts, hai @Bean methods dùng inference mặc định. Rủi ro gì khi context đầu tiên đóng?

**Câu 7.** @Bean factory method trả kiểu interface không có close, nhưng instance thực implements AutoCloseable. Có phải inference chắc chắn không nhìn thấy close vì return type không khai báo nó?

**Câu 8.** Trong demo, tại sao dòng **07** không phải là callback của Spring?

**Câu 9.** Một client vừa implements SmartLifecycle vừa AutoCloseable. Tại sao stop và close nên có trách nhiệm khác nhau?

**Câu 10.** Nếu JVM bị kill ngay, có thể bảo đảm @PreDestroy hoặc inferred close chạy không?

### Đáp án gợi ý

1. AutoCloseable là contract API; close được gọi bởi owner như try-with-resources hoặc bean lifecycle chứ không phải tự động từ GC.
2. Có, nếu là public no-arg shutdown và bean thuộc scope/destruction contract thích hợp.
3. Tên release không nằm trong danh sách được suy luận; phải khai báo destroyMethod tường minh.
4. Không; chỉ tắt inferred custom close/shutdown, các callback khác vẫn có semantics riêng.
5. Container theo dõi singleton destruction, còn prototype thường do caller tự close.
6. Context A có thể close resource mà context B vẫn sử dụng.
7. Không; JavaDoc @Bean nêu detection dựa trên instance thực.
8. Main là owner của BorrowedChannel và gọi EXTERNAL_CHANNEL.close() sau context đã đóng.
9. stop phù hợp ngừng nhận/drain task theo phase; close phù hợp dispose resource cuối.
10. Không; SIGKILL và crash có thể bỏ qua orderly shutdown.

## 16. Checklist thiết kế trước khi dùng @Bean

- [ ] Resource có phải do Spring ApplicationContext **thực sự sở hữu**?
- [ ] Bean scope là singleton, prototype hay một custom scope?
- [ ] Nếu implements AutoCloseable/Closeable, close có public no-arg contract đúng?
- [ ] Nếu chỉ có shutdown(), method có public và không tham số?
- [ ] Nếu cleanup method tên khác, đã khai báo destroyMethod tường minh?
- [ ] Nếu bean trả tài nguyên bên ngoài, có cần destroyMethod=""?
- [ ] Đã kiểm tra @PreDestroy/DisposableBean/SmartLifecycle callbacks khác chưa?
- [ ] Close/destroy có idempotent và xử lý partial initialization an toàn không?
- [ ] Các dependencies cần thiết có sống đủ lâu để cleanup?
- [ ] Có bounded network timeouts và termination grace tương ứng?
- [ ] Đã kiểm chứng trên Spring Framework/Boot version thực tế?
- [ ] Đã viết test đóng context, không chỉ test tạo bean thành công?
- [ ] Đã kiểm tra production shutdown với SIGTERM và trường hợp force-kill?
- [ ] Không phụ thuộc vào thứ tự hủy giữa các singleton không có dependency?

## 17. Tóm tắt và tài liệu tham khảo

**AutoCloseable** định nghĩa cách một object giải phóng tài nguyên, còn **@Bean** quy định object đó tham gia vòng đời Spring ra sao. Spring Framework mặc định dùng **destroyMethod = "(inferred)"** cho @Bean và có thể tự gọi public no-arg **close()** hoặc **shutdown()** khi container hủy bean mà nó quản lý.

- **@Bean**: thuận tiện khi Spring sở hữu resource và class có close/shutdown.
- **@Bean(destroyMethod = "release")**: dùng method khác được nêu tường minh.
- **@Bean(destroyMethod = "")**: tắt inferred close/shutdown, phù hợp khi Spring chỉ mượn resource; không tắt mọi callback lifecycle.
- **Singleton**: thường được container quản lý destruction khi context đóng bình thường.
- **Prototype**: caller chịu trách nhiệm cleanup; Spring không tự close mọi instance khi context đóng.
- **@PreDestroy**, **DisposableBean** và **SmartLifecycle** là cơ chế riêng, cần phối hợp đúng.
- **SIGKILL/crash** có thể bỏ qua cleanup; đừng lấy destruction callback làm bảo đảm duy nhất về an toàn dữ liệu.

Nguồn chính thức, tham chiếu theo Spring Framework 6.2 / Spring Boot 3.5:

1. Spring Framework 6.2 JavaDoc — @Bean.destroyMethod và default "(inferred)": https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Bean.html
2. Spring Framework Reference — Using the @Bean Annotation: https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html
3. Spring Framework Reference — Customizing the Nature of a Bean: https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html
4. Spring Framework Reference — Bean Scopes và prototype destruction: https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html
5. Oracle Java 17 — AutoCloseable: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html
6. Spring Boot 3.5 — SpringApplication startup/shutdown: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html

Ví dụ runnable dùng **Java 17+**, **Spring Boot 3.5.x** và **Spring Framework 6.2.x**. Khi dùng các phiên bản hoặc client SDK khác, cần đối chiếu đúng JavaDoc và contract thực của resource trước khi quyết định ai gọi close().