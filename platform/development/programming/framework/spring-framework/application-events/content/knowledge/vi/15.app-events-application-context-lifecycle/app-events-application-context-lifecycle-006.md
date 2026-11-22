# ApplicationContextEvent trong vòng đời Spring ApplicationContext

## 1. Vị trí của ApplicationContextEvent trong hệ thống sự kiện

`ApplicationContext` là vùng chứa (container) quản lý bean, dependency injection, cấu hình và vòng đời của các thành phần trong ứng dụng Spring. Khi một context được khởi tạo, nhận tín hiệu bắt đầu, dừng hoặc đóng, Spring có thể phát **sự kiện vòng đời context** để các bean quan sát và phản ứng.

`ApplicationContextEvent` là **lớp cơ sở trừu tượng** cho những sự kiện vòng đời này, nằm trong package `org.springframework.context.event`. Đây là một phần của Spring Framework, không phụ thuộc Spring Boot:

~~~text
java.util.EventObject
  └── org.springframework.context.ApplicationEvent
        └── org.springframework.context.event.ApplicationContextEvent
              ├── ContextRefreshedEvent
              ├── ContextStartedEvent
              ├── ContextStoppedEvent
              └── ContextClosedEvent
~~~

Có ba ý chính:

1. `ApplicationContextEvent` biểu diễn **một sự kiện xảy ra với chính ApplicationContext**. Nó không đại diện cho một nghiệp vụ như đặt hàng, thanh toán hay tạo tài khoản.
2. Lớp này là `abstract`. Thông thường ta đăng ký listener cho lớp cơ sở hoặc một lớp con cụ thể, thay vì cố tạo trực tiếp một `ApplicationContextEvent`.
3. Bốn lớp con trên được Spring Framework sử dụng khi thực hiện các thao tác vòng đời tương ứng. Listener nhận thông tin **context nào** đã phát sự kiện và có thể phân biệt sự kiện qua kiểu.

Chẳng hạn, một listener chỉ cần quan sát context đã sẵn sàng ở mức container thì nhận `ContextRefreshedEvent`; listener phục vụ việc thu hồi tài nguyên khi context đang đóng thì nhận `ContextClosedEvent`. Việc đặt logic nghiệp vụ bắt buộc vào listener vòng đời cần cân nhắc kỹ vì thời điểm chạy khác với use case của request.

## 2. API cốt lõi: constructor, nguồn sự kiện và thời gian

Khai báo khái niệm của lớp:

~~~java
public abstract class ApplicationContextEvent extends ApplicationEvent {
    public ApplicationContextEvent(ApplicationContext source) { /* ... */ }

    public final ApplicationContext getApplicationContext() { /* ... */ }
}
~~~

Đây là **chữ ký rút gọn minh họa**; phần triển khai nội bộ không được trình bày ở đây.

- `ApplicationContextEvent(ApplicationContext source)` nhận chính context gắn với sự kiện; source không được `null`.
- `event.getApplicationContext()` trả về đối tượng `ApplicationContext` có liên quan đến sự kiện, kiểu trả về cụ thể và thuận tiện hơn `getSource()`.
- `event.getSource()` kế thừa từ `EventObject` và trả về nguồn dưới kiểu `Object`. Với loại event này, nguồn chính là context.
- `event.getTimestamp()` kế thừa từ `ApplicationEvent`, cho biết thời điểm đối tượng event được tạo (millisecond epoch), **không phải** cam kết thời điểm toàn bộ ứng dụng đã sẵn sàng hoặc một transaction đã commit.
- `event.getClass()`/`instanceof` giúp phân biệt các lớp con khi một listener đăng ký nhận lớp cơ sở.

Ví dụ dùng nguồn sự kiện:

~~~java
@EventListener
public void onContextEvent(ApplicationContextEvent event) {
    ApplicationContext source = event.getApplicationContext();
    System.out.println(source.getId() + " -> "
        + event.getClass().getSimpleName());
}
~~~

Đoạn này cần được đặt trong một bean Spring đã đăng ký với context, cùng các import `ApplicationContext`, `ApplicationContextEvent`, `EventListener`. Listener nhận các loại con tương thích của `ApplicationContextEvent`, vì vậy tên class trong log có thể là `ContextRefreshedEvent`, `ContextStartedEvent`, `ContextStoppedEvent` hoặc `ContextClosedEvent`.

**Lưu ý:** context ID là dữ liệu mô tả; nếu nhiều context có ID giống nhau, dùng **so sánh đối tượng context** để lọc đúng nguồn thay vì chỉ dựa trên chuỗi ID.

## 3. Bốn sự kiện vòng đời chuẩn

| Sự kiện | Khi nào Spring phát | Cách dùng phù hợp |
| --- | --- | --- |
| `ContextRefreshedEvent` | Khi `ApplicationContext` hoàn tất khởi tạo hoặc thao tác `refresh()` thành công | Quan sát container đã khởi tạo, kiểm tra metadata/sẵn sàng ở mức context |
| `ContextStartedEvent` | Khi context nhận lời gọi `start()` | Quan sát tín hiệu start tường minh, phối hợp thành phần `Lifecycle` |
| `ContextStoppedEvent` | Khi context nhận lời gọi `stop()` | Quan sát tín hiệu stop tường minh, tạm dừng một phần hoạt động |
| `ContextClosedEvent` | Khi context đang đóng qua `close()` hoặc shutdown hook | Giải phóng/ghi nhận tình trạng đóng, kết thúc vòng đời |

Sơ đồ quan hệ điển hình:

~~~text
new AnnotationConfigApplicationContext()
         |
         | register(config), refresh()
         v
 ContextRefreshedEvent
         |
         | start()
         v
 ContextStartedEvent
         |
         | stop()
         v
 ContextStoppedEvent
         |
         | start() (có thể bắt đầu lại)
         v
 ContextStartedEvent
         |
         | close()
         v
 ContextClosedEvent
         |
         v
 Context đã đóng, không sử dụng lại
~~~

Không phải ứng dụng nào cũng gọi đủ bốn sự kiện theo sơ đồ. Chẳng hạn, context chỉ `refresh()` rồi `close()` thì có thể chỉ phát `ContextRefreshedEvent` và `ContextClosedEvent`. Một ứng dụng Spring Boot khởi động bình thường **không nhất thiết gọi `start()` tường minh để phát `ContextStartedEvent`**. Đừng kết luận không nhận `ContextStartedEvent` là lỗi khởi động.

### 3.1. ContextRefreshedEvent: khởi tạo hoặc refresh xong

Khi nhận `ContextRefreshedEvent`, những bước xây dựng container như xử lý cấu hình, đăng ký post-processor, tạo các singleton không lazy và hoàn tất refresh đã diễn ra theo vòng đời của context. Đây là một điểm hữu ích để quan sát việc khởi tạo bean hoàn thành.

Tuy nhiên:

- Không đồng nghĩa toàn bộ tác vụ hậu khởi động của **Spring Boot** đã kết thúc. Các `ApplicationRunner`/`CommandLineRunner` có thể chạy sau mốc refresh; `ApplicationReadyEvent` ở Spring Boot thể hiện mốc readiness khác.
- Không bảo đảm mọi hệ thống bên ngoài (database, message broker, ứng dụng khác) đều sẵn sàng.
- Không khẳng định sự kiện chỉ có **một lần duy nhất trong suốt đời ứng dụng**: một số loại context hỗ trợ refresh nhiều lần và cấu trúc context cha–con có thể dẫn tới nhiều sự kiện được quan sát.
- Không nên tự gọi `context.refresh()` lần thứ hai trên `AnnotationConfigApplicationContext`/`GenericApplicationContext` với giả định hỗ trợ hot refresh; các context loại này không được thiết kế để refresh nhiều lần.

### 3.2. ContextStartedEvent: start tường minh

`ContextStartedEvent` gắn với thao tác `ConfigurableApplicationContext.start()`. Lời gọi này cũng liên quan đến `LifecycleProcessor` và các bean triển khai `Lifecycle`. Tùy cấu hình, `SmartLifecycle` có thể được khởi động tự động trong giai đoạn refresh; điều đó **không có nghĩa** event `ContextStartedEvent` sẽ tự xuất hiện chỉ vì một bean `SmartLifecycle` đã start.

Do đó, cần phân biệt:

- Context vừa được `refresh()` → `ContextRefreshedEvent`.
- Người gọi tường minh `context.start()` → `ContextStartedEvent`.
- Bean `Lifecycle` được bắt đầu theo policy container → sự kiện trên **không phải** một event riêng cho từng bean.

### 3.3. ContextStoppedEvent: dừng có thể phục hồi

`ContextStoppedEvent` gắn với `context.stop()`. `LifecycleProcessor` gửi tín hiệu stop đến những bean thuộc cơ chế lifecycle; context có thể nhận `start()` về sau để tiếp tục. `stop()` **không đồng nghĩa `close()`**: singleton beans chưa mặc nhiên bị destroy và context chưa kết thúc vĩnh viễn.

Một yêu cầu HTTP đang chạy, message queue listener hoặc tác vụ background có được dừng an toàn hay không còn phụ thuộc bean triển khai `Lifecycle`/`SmartLifecycle` và quy tắc shutdown. Nhận `ContextStoppedEvent` không chứng minh mọi tác vụ ngoài container đã quiesce.

### 3.4. ContextClosedEvent: đang trong quá trình đóng

`ContextClosedEvent` được Spring phát khi tiến hành đóng context. Trong `AbstractApplicationContext`, sự kiện được phát ở quá trình `doClose()` trước một số bước dừng lifecycle processor và hủy singleton; vậy nên khi callback xử lý sự kiện, **không thể phát biểu rằng mọi bean đã bị hủy xong**.

Sau khi `close()` hoàn thành, context đi đến cuối vòng đời: không dùng lại để refresh/start theo cách thông thường. Đối với cleanup, listener `ContextClosedEvent` có thể ghi log, đánh dấu trạng thái, hoặc phối hợp dừng tác vụ; còn tài nguyên thuộc sở hữu một bean nên ưu tiên callback hủy bean như `@PreDestroy` hoặc `DisposableBean`/`destroyMethod`, và dùng `SmartLifecycle.stop(...)` khi cần điều phối thứ tự dừng.

Nếu listener xử lý đóng quá lâu hoặc ném lỗi, shutdown có thể bị chậm hoặc phức tạp. Tránh dựa vào các bean đã bị destroy hoặc công việc async chưa chắc kịp hoàn tất.

## 4. Lắng nghe bằng @EventListener và ApplicationListener

### 4.1. Lọc đúng một loại event

~~~java
@Component
public class RefreshObserver {
    @EventListener
    public void afterRefresh(ContextRefreshedEvent event) {
        System.out.println(event.getApplicationContext().getId());
    }
}
~~~

Đây là đoạn mã minh họa trong dự án đã cấu hình component scanning. Cần import `Component`, `EventListener`, `ContextRefreshedEvent`. Khi phương thức nhận `ContextRefreshedEvent`, Spring suy ra kiểu event từ tham số và không gọi nó chỉ vì gặp `ContextStoppedEvent`.

### 4.2. Một listener xử lý nhiều subtype

~~~java
@Component
public class ContextAudit {
    @EventListener
    public void onAnyContextEvent(ApplicationContextEvent event) {
        if (event instanceof ContextClosedEvent) {
            System.out.println("CLOSING");
        } else if (event instanceof ContextRefreshedEvent) {
            System.out.println("REFRESHED");
        }
    }
}
~~~

Nếu muốn xử lý các subtype khác, bổ sung các nhánh `instanceof`. Sử dụng type base thuận tiện cho log và observability, nhưng **không nên mặc định mọi event đều có ý nghĩa nghiệp vụ như nhau**.

### 4.3. Dùng giao diện ApplicationListener

~~~java
@Component
public class CloseObserver
        implements ApplicationListener<ContextClosedEvent> {
    @Override
    public void onApplicationEvent(ContextClosedEvent event) {
        System.out.println("Closing: "
            + event.getApplicationContext().getId());
    }
}
~~~

`ApplicationListener<E>` là cơ chế listener có kiểu tường minh, hữu ích khi muốn biểu diễn hợp đồng nghe sự kiện ngay trong interface. `@EventListener` lại phù hợp khi một bean có nhiều phương thức nghe nhiều loại event. Hai cách đều cần được Spring đăng ký; không nên vô tình gắn đồng thời cả hai cơ chế cho cùng logic rồi gây xử lý trùng.

Với `@EventListener({ContextStartedEvent.class, ContextStoppedEvent.class})`, ta có thể khai báo một phương thức **không có tham số** để chạy cho nhiều kiểu. Nếu cần đọc kiểu event tại runtime, dùng tham số có kiểu chung phù hợp như `ApplicationContextEvent` thay vì phương thức không tham số.

## 5. Ví dụ hoàn chỉnh: quan sát refresh, start, stop và close

Ví dụ dùng **Java 17+** và **Spring Framework 6.2.8**. Chỉ cần `spring-context`, không yêu cầu Spring Boot. Ta tạo một context bằng tay, đặt ID cố định, đăng ký bean listener trước refresh, rồi gọi các thao tác vòng đời để quan sát thứ tự.

### 5.1. Cấu trúc dự án

~~~text
context-event-demo/
├── pom.xml
└── src/main/java/ContextLifecycleDemo.java
~~~

### 5.2. Tệp pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>context-event-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
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
                    <mainClass>ContextLifecycleDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.3. Tệp ContextLifecycleDemo.java

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationContextEvent;
import org.springframework.context.event.EventListener;

public final class ContextLifecycleDemo {

    public static class LifecycleLogger {
        @EventListener
        public void onContextEvent(ApplicationContextEvent event) {
            System.out.println(
                event.getClass().getSimpleName()
                    + " | " + event.getApplicationContext().getId()
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        LifecycleLogger lifecycleLogger() {
            return new LifecycleLogger();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

            context.setId("demo-context");
            context.register(Config.class);
            context.refresh();
            context.start();
            context.stop();
            context.start();
        }
        // close() từ try-with-resources gọi khi ra khỏi khối.
    }
}
~~~

Chạy tại thư mục `context-event-demo/`, với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java
~~~

Các dòng chính mà chương trình tự in ra, theo thứ tự:

~~~text
ContextRefreshedEvent | demo-context
ContextStartedEvent | demo-context
ContextStoppedEvent | demo-context
ContextStartedEvent | demo-context
ContextClosedEvent | demo-context
~~~

**Giải thích:**

1. `context.register(Config.class)` đăng ký định nghĩa cấu hình; chưa làm toàn bộ context được khởi tạo. `context.refresh()` xây dựng context, tạo `LifecycleLogger` và đăng ký phương thức `@EventListener`; sau đó phát `ContextRefreshedEvent`.
2. `context.start()` gửi tín hiệu start và phát `ContextStartedEvent`. Ví dụ không có bean `Lifecycle` riêng, nhưng event đánh dấu lời gọi start của context.
3. `context.stop()` phát `ContextStoppedEvent`. Context vẫn có thể tiếp tục hoạt động sau `start()` tiếp theo.
4. Lần `start()` thứ hai làm xuất hiện thêm `ContextStartedEvent`. Ví dụ chứng minh **không nên mặc định mỗi loại lifecycle event chỉ xuất hiện đúng một lần**.
5. Khi ra khỏi `try-with-resources`, `AnnotationConfigApplicationContext.close()` được gọi và phát `ContextClosedEvent`.

Việc giữ `LifecycleLogger` là bean **không lazy** giúp listener có mặt trước sự kiện refresh đầu tiên. Nếu chỉ tạo listener bằng `new LifecycleLogger()` ở code khác mà không đăng ký với Spring, annotation `@EventListener` tự nó không khiến phương thức được gọi.

Lưu ý chương trình không gọi lại `refresh()` lần thứ hai: `AnnotationConfigApplicationContext` thuộc họ `GenericApplicationContext` không hỗ trợ kiểu hot refresh lặp tùy ý. Ví dụ cũng không dùng thread executor, nên output không bị xáo trộn bởi listener async.

## 6. Vòng đời bean và vòng đời ApplicationContext khác nhau

Lỗi thường gặp là nghe `ContextRefreshedEvent` rồi coi đó là lúc **mỗi bean** được khởi tạo, hoặc nghe `ContextClosedEvent` rồi cho rằng mọi bean đã được destroy. Đây là sự nhầm lẫn phạm vi.

| Cơ chế | Đối tượng/ý nghĩa |
| --- | --- |
| Constructor, dependency injection và `@PostConstruct` | Khởi tạo **một bean** |
| `InitializingBean.afterPropertiesSet()`/custom init method | Hook khởi tạo của bean |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | Hook sau giai đoạn khởi tạo các singleton thông thường |
| `SmartLifecycle.start()/stop(...)` | Quản lý hoạt động của **bean có lifecycle** theo phase và chính sách tự khởi động |
| `ContextRefreshedEvent` | Sự kiện sau một lần **refresh context** |
| `ContextClosedEvent` | Sự kiện phát trong **quá trình đóng context** |
| `@PreDestroy`/`DisposableBean.destroy()` | Hook hủy **bean** khi container dọn dẹp |

Một bean `prototype` có vòng đời khác singleton; không nên dựa vào lifecycle event để giải phóng tất cả các đối tượng prototype mà người dùng đã lấy ra. Tương tự, `ContextClosedEvent` không thay thế phương thức đóng của resource cụ thể như connection pool, executor hoặc client.

### Vì sao ContextStartedEvent không phải SmartLifecycle startup?

`SmartLifecycle` có thể tự start trong lúc context refresh, tùy `isAutoStartup()` và phase. Khi gọi `context.start()` tường minh, lifecycle processor cũng có thể gửi tín hiệu start. Nhưng `ContextStartedEvent` gắn với thao tác của **context**, không phải event riêng phát mỗi lần một bean `SmartLifecycle` thực thi `start()`.

Nếu cần quản lý chính xác vòng đời một consumer, server adapter hoặc scheduler, triển khai `SmartLifecycle`/`Lifecycle` với phase, trạng thái và shutdown đúng cách; chỉ dùng lifecycle event để quan sát hoặc phối hợp cấp context.

## 7. Context cha–con: tại sao có thể nhận nhiều event?

Một ứng dụng có thể có **nhiều ApplicationContext**, chẳng hạn context gốc và context con cho các thành phần web. Khi một context con publish event, cơ chế Spring `AbstractApplicationContext` thường **truyền event lên context cha**. Vì vậy một listener nằm trong context cha có thể nhìn thấy cả:

- Event của chính context cha.
- Event được publish từ context con rồi lan lên cha.

Chiều phát event thông thường là từ **con lên cha**, không mặc nhiên từ cha xuống mọi context con. Nhờ `event.getApplicationContext()`, listener vẫn biết context ban đầu liên quan tới event là context nào.

Ví dụ minh họa cho một bean trong context cha:

~~~java
@Component
public class RootOnlyRefreshListener
        implements ApplicationContextAware {

    private ApplicationContext owner;

    @Override
    public void setApplicationContext(ApplicationContext context) {
        this.owner = context;
    }

    @EventListener
    public void handle(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != owner) {
            return;  // Bỏ qua event của context con.
        }
        System.out.println("Root context refreshed");
    }
}
~~~

Đây là đoạn mã phụ thuộc một ứng dụng có cấu hình context cha–con và component scanning, không phải chương trình độc lập. Cần import `Component`, `ApplicationContextAware`, `ApplicationContext`, `EventListener` và `ContextRefreshedEvent`. So sánh `!=` giữa hai tham chiếu xác nhận **đúng đối tượng context**, tránh false positive khi ID của các context bị cấu hình trùng.

Đừng viết listener chỉ dựa vào `ContextRefreshedEvent` rồi tự tăng một bộ đếm “ứng dụng khởi động xong một lần” mà không xét số context và số lần refresh. Đặc biệt với Spring Boot, tài liệu cũng nhắc đến hiện tượng listener nhận nhiều sự kiện cùng loại khi có hierarchy.

### Lọc event bằng condition

Một số trường hợp có thể dùng `@EventListener(condition = "...")` với Spring Expression Language (SpEL). Tuy nhiên logic so sánh source/owner thường rõ hơn ở thân listener hoặc trong service chuyên trách. Khi dùng condition, cần hiểu biến SpEL và khả năng truy cập bean tương ứng; tránh biểu thức dài hoặc gọi dịch vụ bên ngoài trong đường phát event.

## 8. Đối chiếu với các sự kiện Spring Boot

Spring Framework có `ContextStartedEvent`, còn Spring Boot có `ApplicationStartedEvent`. **Hai tên gần nhau nhưng khác loại và khác mốc thời gian**.

| Sự kiện | Thuộc | Ý nghĩa |
| --- | --- | --- |
| `ContextRefreshedEvent` | Spring Framework | Container đã refresh |
| `ContextStartedEvent` | Spring Framework | Gọi `ConfigurableApplicationContext.start()` tường minh |
| `ContextClosedEvent` | Spring Framework | Context đang đóng |
| `ApplicationStartedEvent` | Spring Boot | Spring Boot đã refresh context nhưng trước khi chạy `ApplicationRunner`/`CommandLineRunner` |
| `ApplicationReadyEvent` | Spring Boot | Sau khi các runner hoàn tất, mốc ứng dụng sẵn sàng phục vụ request theo lifecycle Boot |
| `ApplicationFailedEvent` | Spring Boot | Có lỗi trong quá trình Spring Boot khởi động |

Các `SpringApplicationEvent` của Boot **không phải** bốn lớp con chuẩn của `ApplicationContextEvent` nêu ở đầu bài; một listener chỉ đăng ký `ApplicationContextEvent` không nên được kỳ vọng bắt mọi sự kiện của Boot. Ngược lại, một listener `ApplicationEvent` chung có thể thấy nhiều sự kiện khác trong context nếu cách đăng ký cho phép.

Nếu mục tiêu là **readiness để nhận traffic** ở Spring Boot, tìm hiểu `ApplicationReadyEvent` và cơ chế application availability/readiness; đừng dùng `ContextRefreshedEvent` để kết luận toàn bộ bootstrap đã xong. Nếu mục tiêu là bật một dịch vụ có start/stop cụ thể, xem `SmartLifecycle` thay vì giả lập trạng thái bằng event.

## 9. Lỗi trong listener vòng đời và xử lý bất đồng bộ

Mặc định, `SimpleApplicationEventMulticaster` xử lý event đồng bộ trên luồng phát. Vì thế một listener `ContextRefreshedEvent` làm việc quá lâu có thể làm kéo dài thời gian refresh; exception chưa được xử lý có thể ảnh hưởng quá trình khởi động. Listener `ContextClosedEvent` chờ tác vụ mạng vô hạn có thể trì hoãn shutdown.

Nếu đánh dấu listener `@Async` hoặc thay multicaster bằng executor, có thể giảm chặn luồng phát, nhưng cần hiểu:

- Công việc listener có thể chạy khi context đang thay đổi trạng thái; khi đóng context, executor hay dependency có thể đã dừng hoặc đang dừng.
- Exception của listener bất đồng bộ không tự truyền về lời gọi gốc như listener đồng bộ.
- Việc nhận event không đồng nghĩa một công việc async chắc chắn hoàn tất trước khi tiến trình kết thúc.
- Không dùng async lifecycle listener để thay thế quản lý shutdown có thứ tự hoặc bảo đảm flush dữ liệu trước khi ứng dụng dừng.

Với cleanup bắt buộc, quản lý **resource trong chính bean** với callback hủy/`SmartLifecycle`, có timeout và khả năng xử lý lỗi. Với công việc cần giao hàng tin cậy, dùng hàng đợi/outbox/cơ chế retry phù hợp; Spring event nội bộ không tự cung cấp durable delivery.

## 10. Kiểm thử và quan sát đúng vòng đời

Một ca kiểm thử trực tiếp với `AnnotationConfigApplicationContext` có thể thực hiện trình tự:

1. Tạo context chưa refresh, đăng ký config và listener.
2. Gọi `refresh()`, kiểm tra nhận `ContextRefreshedEvent` đúng một lần **trong lần chạy cụ thể này**.
3. Gọi `start()`, kiểm tra `ContextStartedEvent`.
4. Gọi `stop()`, kiểm tra `ContextStoppedEvent`.
5. Gọi `start()` lần nữa, kiểm tra có thêm `ContextStartedEvent`.
6. Gọi `close()`, kiểm tra `ContextClosedEvent` và tài nguyên được dọn đúng cách.

Đoạn code ở mục 5 cung cấp một phép thử quan sát có đầu ra ổn định. Với integration test có context hierarchy, nên thêm ca nhận event con tại listener cha và ca lọc bằng `event.getApplicationContext() == ownContext`.

Các điểm cần kiểm tra khi listener không chạy:

- Bean listener có thực sự được Spring quản lý không? Có `@Bean` hoặc `@Component` được scan hay chưa?
- Phương thức có `@EventListener` đúng kiểu tham số không? Có lẫn `ContextStartedEvent` với `ContextRefreshedEvent` không?
- Listener có được đăng ký **trước khi** event cần quan sát phát ra không? Event rất sớm có thể đòi hỏi cách đăng ký khác với bean tạo sau.
- Ứng dụng đã gọi `context.start()`/`context.stop()` thật chưa? Không nên tự động chờ hai event này sau mọi lần `refresh()`.
- Có nhiều context không? Event có đến từ context con không?
- Listener có chạy async, bị lỗi hoặc bị executor từ chối không? Có log/monitor không?
- Có tùy chỉnh `ApplicationEventMulticaster`, `ErrorHandler` hoặc cơ chế filter khác không?

**Không nên xác minh “refresh một lần” bằng cách gọi `refresh()` lần thứ hai trên `AnnotationConfigApplicationContext`**; ví dụ chọn đúng loại context và đúng lifecycle được hỗ trợ.

## 11. Những nhầm lẫn và sai lầm thường gặp

1. **Tưởng ApplicationContextEvent là mọi event trong Spring.** Đây là lớp cơ sở cho nhóm sự kiện vòng đời context; business event có thể là POJO hoặc loại `ApplicationEvent` khác.
2. **Tưởng ApplicationContextEvent có thể new trực tiếp.** Nó là abstract; đăng ký listener cho base hoặc lớp con.
3. **Tưởng ContextStartedEvent phát ngay sau context refresh.** `start()` là thao tác tường minh; refresh hoàn tất phát `ContextRefreshedEvent`.
4. **Tưởng ContextStoppedEvent đã destroy toàn bộ bean.** Stop và close khác nhau; context dừng có thể start lại.
5. **Tưởng ContextClosedEvent chỉ đến sau khi tất cả singleton đã bị hủy.** Event được phát **trong quá trình đóng**, trước nhiều bước hủy bean.
6. **Tưởng ContextRefreshedEvent đồng nghĩa Spring Boot đã ready nhận traffic.** Runner và readiness có thể xảy ra sau refresh.
7. **Đếm event mà bỏ qua context hierarchy.** Parent listener có thể thấy event từ child; dùng `getApplicationContext()` để phân biệt.
8. **Tưởng refresh lặp luôn được hỗ trợ.** `GenericApplicationContext`/`AnnotationConfigApplicationContext` không phải context hot-refresh tùy ý.
9. **Dùng lifecycle event thay hook của bean.** Với tài nguyên thuộc bean, dùng `@PreDestroy`/`DisposableBean`/`SmartLifecycle` phù hợp.
10. **Nhét công việc nặng vào listener đồng bộ lúc refresh/close.** Có thể tăng thời gian startup hoặc cản shutdown.
11. **Tự publish một ContextRefreshedEvent để giả lập refresh thật.** Việc gửi một object event không thực thi quy trình container refresh, không tạo hay tái cấu hình bean.
12. **Đưa business transaction vào ContextClosedEvent.** Context đang dừng, phụ thuộc có thể không còn sẵn sàng; nên xử lý use case theo ranh giới riêng và shutdown có kiểm soát.

## 12. Câu hỏi thực hành

1. `ApplicationContextEvent` khác `ApplicationEvent` và một POJO event ở điểm nào? Nó có thể được tạo trực tiếp không?
2. Trong ví dụ, vì sao có hai `ContextStartedEvent` nhưng chỉ có một `ContextRefreshedEvent`?
3. Nếu bạn chỉ gọi `refresh()` rồi `close()` thì có chắc chắn nhận `ContextStartedEvent`/`ContextStoppedEvent` không?
4. Vì sao một listener `ContextClosedEvent` không nên khẳng định rằng mọi singleton đã được destroy tại thời điểm nhận event?
5. Trong hierarchy `root → child`, tại sao listener ở root có thể nhận `ContextRefreshedEvent` của child? Làm sao lọc chỉ root?
6. `ContextRefreshedEvent` có phải sự kiện tương đương `ApplicationReadyEvent` của Spring Boot không?
7. Một consumer cần tự start và stop đúng phase, có graceful shutdown. Nên bắt event nào hay triển khai `SmartLifecycle`?
8. Vì sao không thể gọi `context.publishEvent(new ContextRefreshedEvent(context))` để thay thế `context.refresh()`?
9. Listener close dùng `@Async` có thể gặp những rủi ro nào khi context/executor đang dừng?

**Gợi ý đối chiếu:** (1) abstract base của nhóm context lifecycle, kế thừa `ApplicationEvent`; (2) đã gọi `start()` hai lần; (3) không, cần thao tác tường minh; (4) close event được phát trong quy trình đóng; (5) event truyền lên cha, so sánh đối tượng qua `getApplicationContext()`; (6) không, Boot readiness muộn hơn; (7) `SmartLifecycle`; (8) publish không chạy pipeline refresh; (9) task có thể không hoàn tất hoặc dependency/executor dừng.

## Tài liệu tham khảo

- Spring Framework Reference, *Standard and Custom Events / ApplicationContext*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework 6.2 API, *ApplicationContextEvent*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/ApplicationContextEvent.html
- Spring Framework 6.2 API, *ContextRefreshedEvent*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/ContextRefreshedEvent.html
- Spring Framework 6.2 API, *AbstractApplicationContext*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Framework Reference, *Lifecycle Callbacks*: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Boot Reference, *SpringApplication and Application Events*: https://docs.spring.io/spring-boot/3.4/reference/features/spring-application.html
