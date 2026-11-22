# ContextClosedEvent trong vòng đời ApplicationContext của Spring Framework

## 1. Khái niệm và vai trò

**ContextClosedEvent** là sự kiện vòng đời mà Spring phát khi **ApplicationContext** được đóng theo quy trình shutdown của container. Lớp **org.springframework.context.event.ContextClosedEvent** kế thừa **ApplicationContextEvent**; listener có thể dùng **event.getApplicationContext()** để biết chính xác context đã phát sự kiện.

Sự kiện này trả lời câu hỏi **“Một Spring ApplicationContext đang bắt đầu đóng; các thành phần liên quan cần biết điều gì?”**. Nó hữu ích cho logging, telemetry, ngừng nhận tác vụ mới hoặc thông báo ngắn về việc shutdown. Tuy nhiên, tự nhận sự kiện **không đồng nghĩa** đã đóng tài nguyên, hoàn tất công việc bất đồng bộ hay bảo đảm cleanup khi JVM bị kill cưỡng bức.

Trong ứng dụng standalone, đường đóng quen thuộc là **ConfigurableApplicationContext.close()** hoặc **try-with-resources** trên **AnnotationConfigApplicationContext**. Trong ứng dụng web hoặc Spring Boot, framework thường nắm quyền điều phối vòng đời context và phát sự kiện này khi context thực sự đóng.

Đây là **event của container**, không phải sự kiện nghiệp vụ như **OrderCancelled** hoặc **UserLoggedOut**. Không nên phụ thuộc ContextClosedEvent để ghi nhận giao dịch nghiệp vụ quan trọng vào thời khắc cuối cùng, vì các lỗi tiến trình có thể khiến shutdown callback không chạy.

## 2. ContextClosedEvent xảy ra ở thời điểm nào?

Một vòng đời tiêu biểu:

~~~text
Tạo ApplicationContext
       |
       v
refresh()
  -> ContextRefreshedEvent
       |
       v
Context đang hoạt động, xử lý nghiệp vụ
  -> start() -> ContextStartedEvent (khi gọi API start)
  -> stop()  -> ContextStoppedEvent (khi gọi API stop)
       |
       v
close() hoặc shutdown hook đóng context
  -> ContextClosedEvent
  -> LifecycleProcessor.onClose(): dừng các Lifecycle/SmartLifecycle
  -> destroyBeans(): hủy singleton beans và gọi destroy callback
  -> đóng BeanFactory, làm sạch trạng thái context
       |
       v
Context đã đóng
~~~

Trong triển khai **AbstractApplicationContext.doClose()**, Spring phát **ContextClosedEvent** ở giai đoạn đầu của quy trình đóng, **trước khi** yêu cầu lifecycle processor dừng các bean lifecycle và trước khi hủy các singleton bean. Vì thế listener **đồng bộ** nhận ContextClosedEvent thường còn có thể thấy một số bean chưa bị hủy. Điều đó không bảo đảm mọi tài nguyên luôn sẵn sàng cho tác vụ dài hoặc hoạt động async đang chờ.

Điểm cần phân biệt:

- **Sự kiện đã được phát**: Spring đã thông báo context đang đóng.
- **Listener đồng bộ đã trả về**: phần xử lý thông báo của listener đó đã hoàn tất.
- **Container đã đóng xong**: các bước dừng lifecycle và destroy singleton đã được yêu cầu/thực hiện.
- **Ứng dụng đã thoát process**: còn phụ thuộc JVM, server/container và các thread khác.

Không được đồng nhất bốn mốc trên. **ContextClosedEvent** không có nghĩa toàn bộ bean đã bị destroy vào thời điểm listener vừa được gọi.

## 3. Những cách thông thường khiến sự kiện được phát

### 3.1. close() hoặc try-with-resources

~~~java
try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
    // Dùng các Spring-managed beans.
}
// Kết thúc khối try: AutoCloseable.close() được gọi.
~~~

Đây là **đoạn minh họa** cần có class **AppConfig** của ứng dụng. **AnnotationConfigApplicationContext** triển khai hợp đồng **ConfigurableApplicationContext** và có thể dùng trong try-with-resources. Khi rời khỏi khối try bình thường hoặc do exception, Java gọi **close()** để đóng context.

Ứng dụng cũng có thể gọi trực tiếp **context.close()**. Đây là hành động đóng cả container, không phải API để tạm dừng một tác vụ nghiệp vụ đơn lẻ.

### 3.2. Shutdown hook

Với chương trình tự tạo context, có thể đăng ký:

~~~java
ConfigurableApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfig.class);
context.registerShutdownHook();
~~~

Đây là **đoạn minh họa**, cần **AppConfig** và import phù hợp. Spring đăng ký shutdown hook để gọi đóng context khi JVM thực hiện shutdown theo đường bình thường có chạy hooks. Spring Boot thường đã quản lý graceful shutdown/context closing theo cấu hình của framework; không nên tự nhân đôi hook nếu không có lý do.

**Giới hạn:** không có cam kết hook được chạy khi bị **SIGKILL/kill -9**, mất điện, crash nặng hoặc bị runtime dừng không cho đủ thời gian. Tác vụ “phải hoàn thành” cần durable state, retry và idempotency trong khi ứng dụng còn hoạt động.

### 3.3. Framework đóng web/child context

Trong servlet/web application, framework/runtime có thể đóng context khi ứng dụng dừng hoặc redeploy. Trong hệ thống có nhiều parent/child contexts, **mỗi context** có lifecycle riêng và có thể phát sự kiện đóng của chính mình.

Một event do child context publish có thể được truyền lên parent context. Vì thế parent listener có thể thấy **ContextClosedEvent của child**. Không phải cứ callback chạy trong parent là event phát bởi parent; dùng **event.getApplicationContext()** để phân biệt.

### 3.4. Tự tạo event có khiến context đóng không?

**Không.** Gọi **publisher.publishEvent(new ContextClosedEvent(context))** chỉ gửi một object event cho listeners; nó **không thay thế** **ConfigurableApplicationContext.close()**, không tự dừng lifecycle processor và không destroy bean factory. Điều này tạo tín hiệu sai cho hệ thống, nên cần dùng đúng API đóng context.

## 4. Lắng nghe bằng @EventListener

Một bean có thể nhận event:

~~~java
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class ShutdownObserver {
    @EventListener
    public void onClosed(ContextClosedEvent event) {
        System.out.println("Context closing: "
                + event.getApplicationContext().getId());
    }
}
~~~

Đây là **đoạn code trong ứng dụng có component scanning**, không phải chương trình độc lập. Spring tìm method **@EventListener**, tạo listener adapter và gọi nó khi event có type tương ứng được phân phối. **getId()** hỗ trợ phân biệt nhiều context; nó không nhất thiết là tên process hay hostname.

Có thể khai báo thứ tự khi có nhiều listener:

~~~java
@EventListener
@Order(10)
public void onClosed(ContextClosedEvent event) {
    // Phản ứng ngắn, đồng bộ nếu không dùng @Async.
}
~~~

Cần import **org.springframework.core.annotation.Order** và đặt method trong một Spring-managed bean. Số thứ tự thấp được ưu tiên trước trong multicaster hỗ trợ ordering. **@Order** sắp thứ tự dispatch, không đảm bảo thứ tự **hoàn thành** của các listener bất đồng bộ.

Đối với **SimpleApplicationEventMulticaster** mặc định, listener thông thường chạy đồng bộ khi được gọi. Nếu tự cấu hình executor cho multicaster hoặc dùng **@Async**, hành vi blocking và xử lý exception thay đổi; shutdown có thể tiếp tục trước khi tác vụ async hoàn tất.

## 5. Lắng nghe bằng ApplicationListener<ContextClosedEvent>

Cách khác là triển khai interface:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextClosedEvent;

public class ExplicitCloseListener
        implements ApplicationListener<ContextClosedEvent> {

    @Override
    public void onApplicationEvent(ContextClosedEvent event) {
        System.out.println("Closing: "
                + event.getApplicationContext().getId());
    }
}
~~~

Phải đăng ký object này làm bean hoặc đăng ký với context bằng API thích hợp. Chỉ khai báo class ngoài Spring không khiến listener được tự động gọi.

| Phong cách | Phù hợp khi | Lưu ý |
| --- | --- | --- |
| **@EventListener** | Muốn method ngắn gọn, một bean xử lý nhiều loại event | Bean phải được Spring quản lý; method signature hợp lệ |
| **ApplicationListener<ContextClosedEvent>** | Muốn listener thể hiện rõ bằng interface, dễ đăng ký tường minh | Phải đăng ký instance; loại event được định nghĩa ở generic type |

Dùng cả hai trên cùng một logic có thể khiến xử lý shutdown bị lặp. Chọn một cách và kiểm tra số lần được gọi trong thực tế.

## 6. Ví dụ Java 17+ biên dịch/chạy được: stop khác close, event trước destroy

Ví dụ sử dụng **Spring Framework 6.2.9**, **Java 17+**, **Gradle 8.x**. Không cần Spring Boot hay máy chủ bên ngoài.

Cấu trúc thư mục:

~~~text
context-close-demo/
  build.gradle
  src/main/java/demo/ContextCloseDemo.java
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

application {
    mainClass = 'demo.ContextCloseDemo'
}
~~~

**src/main/java/demo/ContextCloseDemo.java**:

~~~java
package demo;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextStoppedEvent;
import org.springframework.context.event.EventListener;

public class ContextCloseDemo {

    public static class EventObserver {
        @EventListener
        public void onStopped(ContextStoppedEvent event) {
            System.out.println("event: stopped");
        }

        @EventListener
        public void onClosed(ContextClosedEvent event) {
            System.out.println("event: closed");
        }
    }

    public static class ManagedResource implements DisposableBean {
        @Override
        public void destroy() {
            System.out.println("resource: destroyed");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        EventObserver eventObserver() {
            return new EventObserver();
        }

        @Bean
        ManagedResource managedResource() {
            return new ManagedResource();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            System.out.println("context: running");

            context.stop();
            System.out.println("after: stop");

            context.start();
            System.out.println("after: start");

            System.out.println("before: close");
        }

        System.out.println("after: close");
    }
}
~~~

Tại thư mục **context-close-demo**, chạy bằng JDK 17+ và Gradle 8.x:

~~~bash
gradle --console=plain -q run
~~~

**Các dòng do chương trình in ra** (bỏ qua các log khác nếu môi trường tự thêm):

~~~text
context: running
event: stopped
after: stop
after: start
before: close
event: closed
resource: destroyed
after: close
~~~

Phân tích:

1. Constructor **AnnotationConfigApplicationContext(Config.class)** tạo và refresh context, đăng ký các bean **EventObserver**, **ManagedResource**.
2. **context.stop()** gọi cơ chế stop lifecycle rồi publish **ContextStoppedEvent**; listener **onStopped(...)** in **event: stopped**. Nó **không** publish ContextClosedEvent, nên context vẫn có thể **start()** trở lại.
3. **context.start()** yêu cầu các lifecycle beans khởi động và publish **ContextStartedEvent**. Chương trình không đăng ký listener in log cho loại event này.
4. Khi rời try-with-resources, **close()** được gọi. Spring publish **ContextClosedEvent**, do đó in **event: closed**.
5. Sau đó, bean **ManagedResource** bị destroy và **DisposableBean.destroy()** in **resource: destroyed**. **after: close** chỉ được in khi call **close()** đã trả về.

Demo cố ý dùng **DisposableBean** để quan sát destroy callback mà không cần thêm dependency Jakarta annotations. **@PreDestroy**, **destroyMethod** hoặc **SmartLifecycle** cũng có thể dùng trong ứng dụng thật.

Đây không phải minh họa cho transaction, xử lý network hoặc guarantee khi JVM bị kill. Chỉ có một bean resource; trong ứng dụng thực, thứ tự destroy của nhiều bean còn chịu ảnh hưởng bởi quan hệ phụ thuộc và cấu hình container.

## 7. Phân biệt các event và hook vòng đời

| Sự kiện hoặc hook | Thời điểm | Ngữ nghĩa |
| --- | --- | --- |
| **ContextRefreshedEvent** | Sau khi context được init/refresh thành công | Container đã được làm mới |
| **ContextStartedEvent** | Khi gọi **start()** | Phát tín hiệu start của lifecycle context |
| **ContextStoppedEvent** | Khi gọi **stop()** | Dừng lifecycle beans; có thể start lại nếu context còn mở |
| **ContextClosedEvent** | Khi context bắt đầu quy trình đóng | Thông báo container đang shutdown |
| **@PreDestroy / DisposableBean.destroy()** | Khi bean bị destroy | Dọn tài nguyên mà bean quản lý |
| **SmartLifecycle.stop(Runnable)** | Khi lifecycle processor dừng bean | Điều phối việc ngừng nhận tác vụ và hoàn tất shutdown |
| **ApplicationReadyEvent** *(Spring Boot)* | Khi ứng dụng Boot startup xong | Event riêng của Boot; không phải event đóng context |

**stop() khác close():** stop thường hướng đến ngừng các lifecycle components trong một context vẫn tồn tại. Close hướng đến hủy context và singleton beans. Nếu cần tạm ngừng một scheduler/worker, nên dùng API stop hoặc điều khiển riêng của worker, không đóng cả context.

**Event listener khác destroy callback:** ContextClosedEvent thông báo một thay đổi vòng đời; destroy callback là nơi trực tiếp đóng tài nguyên do bean sở hữu. Một bean có thể nhận event đóng và vẫn có destroy callback sau đó, nhưng hai hook có mục đích khác nhau.

## 8. Chọn cách cleanup cho đúng trách nhiệm

### 8.1. Dùng ContextClosedEvent khi cần biết context đóng

Các việc phù hợp:

- Ghi metric hoặc audit ngắn về thời điểm bắt đầu shutdown, nếu hệ thống ghi nhận còn khả dụng.
- Chuyển trạng thái nội bộ sang “shutting down” để từ chối yêu cầu công việc mới.
- Phát tín hiệu ngắn cho bộ phận điều phối nội bộ khi context đóng.
- Kiểm tra và log context ID để debug trong hệ thống có nhiều context.

Không nên dùng một listener để chờ hàng loạt nhiệm vụ kéo dài, tạo job mới không có điểm dừng hoặc gửi network request không có timeout.

### 8.2. Dùng @PreDestroy / DisposableBean cho tài nguyên thuộc bean

Nếu bean mở file handle, thread pool riêng, socket hoặc connection, bean đó nên sở hữu cách đóng của tài nguyên. Spring hỗ trợ **@PreDestroy**, **DisposableBean.destroy()**, destroy method cấu hình trên bean hoặc các API close tương thích. Khi singleton bị hủy, Spring gọi callback theo lifecycle quản lý của bean.

Với tài nguyên do một bean tạo, cleanup đặt trong bean sở hữu tài nguyên có thể test độc lập và tránh phụ thuộc vào việc event có được observer bên ngoài nhận hay không.

### 8.3. Dùng SmartLifecycle để dừng có thứ tự

**SmartLifecycle** hợp với các thành phần làm việc nền cần dừng nhận việc, drain tác vụ hiện hữu, rồi báo đã dừng. Nó hỗ trợ **start()**, **stop(Runnable callback)**, **isAutoStartup()**, **getPhase()** và **isRunning()**.

Trong shutdown, lifecycle processor có thể sử dụng phase và dependency để quyết định thứ tự dừng; thông thường bean có phase cao hơn dừng trước bean phase thấp hơn. **stop(Runnable callback)** nên gọi callback khi thực sự kết thúc dừng, để container có thể điều phối bước sau. Cần timeout và giới hạn thời gian cho draining; không chờ vô hạn.

| Nhu cầu | Ưu tiên |
| --- | --- |
| Thông báo ngắn rằng context đang đóng | **ContextClosedEvent** |
| Đóng tài nguyên cụ thể do bean sở hữu | **@PreDestroy**, **DisposableBean** hoặc destroy method |
| Stop nhiều worker có thứ tự và chờ hoàn tất | **SmartLifecycle** |
| Ghi công việc không được phép mất khi process chết | Persistent queue/outbox/checkpoint **trước** shutdown |
| Tạm dừng hoạt động rồi khởi động lại | **Lifecycle/SmartLifecycle** hoặc cơ chế riêng, không dùng close |

## 9. Các rủi ro khi xử lý đóng context

### 9.1. Executor và @Async đang shutdown

Nếu listener **ContextClosedEvent** dùng **@Async**, lời gọi đến executor có thể được xếp hàng, chạy sau hoặc bị từ chối trong giai đoạn dừng; tài nguyên phục vụ tác vụ có thể sớm bị hủy. Vì vậy không được coi “đã dispatch async” là “đã hoàn tất cleanup”.

Với listener đồng bộ chạy lâu, **close()** có thể bị chặn cho tới khi listener trả về, gây quá thời gian graceful shutdown. Giải pháp là giữ listener ngắn, đặt timeout hợp lý, và chuyển công việc dừng có điều phối sang lifecycle component.

### 9.2. Spring không bảo đảm event khi process chết cưỡng bức

Khi bị **kill -9**, mất điện hoặc container bị cắt thời gian, **ContextClosedEvent** có thể không xảy ra. Muốn không mất dữ liệu, phải lưu bền vững trước lúc shutdown, thiết kế retry/idempotency sau restart, hoặc có cơ chế health/readiness để giảm tải trước khi ngừng dịch vụ.

### 9.3. Exception ở listener không phải cách hủy shutdown

Một listener có thể ném exception trong quá trình đóng. **AbstractApplicationContext** cố gắng tiếp tục cleanup ngay cả khi phát sự kiện đóng gặp lỗi; exception không phải rollback hay cơ chế đảm bảo ứng dụng sẽ còn chạy. Log lỗi cần đủ thông tin để tìm nguyên nhân; tránh nuốt mọi **Throwable** rồi coi cleanup đã thành công.

### 9.4. Transaction không tự có ở ContextClosedEvent

Đóng ApplicationContext không mặc định diễn ra trong transaction nghiệp vụ. Method **@TransactionalEventListener(ContextClosedEvent)** có thể không được gọi nếu không có transaction tương thích. Để quan sát shutdown, dùng **@EventListener** thông thường. Nếu cần ghi DB trong quá trình shutdown, phải tính tới transaction manager và data source có thể đã/đang shutdown, thời gian đóng và idempotency.

Không nên xử lý một nghiệp vụ tài chính bắt buộc ở **ContextClosedEvent**. Dữ liệu quan trọng cần được commit và/hoặc đưa vào outbox trong các giao dịch nghiệp vụ thông thường.

### 9.5. Có parent/child ApplicationContext

Event publish ở child có thể lan tới parent. Một listener trong parent có thể thấy event đóng của child. Nếu chỉ muốn phản ứng với context sở hữu bean, lọc theo object identity:

~~~java
@Component
class LocalContextObserver {
    private final ApplicationContext own;

    LocalContextObserver(ApplicationContext own) {
        this.own = own;
    }

    @EventListener
    public void onClose(ContextClosedEvent event) {
        if (event.getApplicationContext() != own) {
            return;
        }
        // Chính context sở hữu bean này đang đóng.
    }
}
~~~

Đây là **đoạn minh họa**; cần import các Spring type tương ứng và dùng trong ứng dụng có component scanning. Trong hệ thống đa context, nên kiểm thử riêng thứ tự đóng và trường hợp parent nhận lại sự kiện của child để tránh xử lý trùng.

## 10. Kiểm thử đúng lifecycle thay vì chỉ gọi method listener

Để kiểm tra một listener **ContextClosedEvent**, phải chạy qua **ApplicationContext** thật:

1. Tạo context với listener và bean resource.
2. Gọi **context.stop()**, xác nhận nhận **ContextStoppedEvent**, chưa nhận ContextClosedEvent.
3. Gọi **context.start()**, xác nhận context còn hoạt động và start event không bị nhầm với close.
4. Gọi **context.close()**, xác nhận listener nhận một ContextClosedEvent của context mong muốn.
5. Đối chiếu thứ tự log/danh sách sự kiện: **ContextClosedEvent** trước **destroy()** của resource trong luồng đóng mặc định.
6. Với hierarchy, xác nhận **event.getApplicationContext()** là child hay parent đúng mong đợi.
7. Với listener lỗi hoặc executor, xác nhận policy log, timeout, stop và cleanup phù hợp.

Có thể lưu dấu bằng **List<String>** đồng bộ hoặc **AtomicInteger** trong integration test, tránh dùng **Thread.sleep(...)** tùy ý để kết luận callback đã hoàn tất. Unit test gọi trực tiếp **onClosed(new ContextClosedEvent(...))** chỉ kiểm tra nội dung method, **không chứng minh** Spring đã phát event đúng pha.

## 11. Sai lầm phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đợi ContextClosedEvent sau khi chỉ gọi **stop()** | Listener đóng không chạy | Phân biệt ContextStoppedEvent với ContextClosedEvent |
| Tưởng ContextClosedEvent xảy ra sau mọi **@PreDestroy** | Sai mốc quan sát và suy luận tài nguyên | Nhớ Spring publish close event trước giai đoạn destroy singleton |
| Dùng event đóng để cleanup tất cả resources | Ownership không rõ, dễ sai thứ tự và thiếu timeout | Cleanup ở resource owner hoặc SmartLifecycle |
| Dùng **@Async** cho cleanup bắt buộc | Executor có thể dừng trước khi tác vụ hoàn tất | Sử dụng lifecycle hook có điều phối và timeout |
| Tự publish **new ContextClosedEvent(...)** để tắt ứng dụng | Chỉ phát thông báo; context vẫn chưa được đóng | Gọi **ConfigurableApplicationContext.close()** |
| Không lọc event trong parent/child contexts | Parent xử lý event đóng của child ngoài ý muốn | Kiểm tra **getApplicationContext()** |
| Dùng **@TransactionalEventListener** mặc định cho shutdown event | Thường không có transaction để đăng ký | Dùng **@EventListener** thường |
| Chờ shutdown hook chạy trong mọi trường hợp | Mất công việc khi bị kill hoặc crash | Lưu state bền vững trước shutdown, retry khi phục hồi |
| Listener block network không timeout | Graceful shutdown treo hoặc bị cắt ngang | Timeout, metrics và làm tối thiểu trong listener |
| Bắt exception rồi tuyên bố đã hoàn tất cleanup | Che khuất lỗi và rò rỉ resource | Log/alert, phân quyền dọn dẹp rõ, test lỗi thực |

## 12. Checklist thiết kế listener ContextClosedEvent

Trước khi thêm listener đóng context, hãy xác nhận:

- **Mục tiêu là quan sát sự kiện đóng hay dọn resource?** Chọn đúng callback theo ownership.
- **Listener thuộc context nào?** Dùng **event.getApplicationContext()** khi có parent/child.
- **Có phụ thuộc executor, DB, HTTP không?** Đánh giá availability khi container đang shutdown.
- **Listener có thể chạy nhanh, timeout rõ ràng không?** Tránh kéo dài close().
- **Có bắt buộc hoàn thành dù JVM chết không?** Nếu có, chuyển sang cơ chế bền vững trước shutdown.
- **Đã test stop/close/destroy với ApplicationContext thực chưa?** Không kết luận từ test gọi method trực tiếp.
- **Một bean có nhiều hook cleanup gây chạy lặp không?** Chỉ rõ nơi chịu trách nhiệm đóng tài nguyên.

**Quy tắc nhớ:** **ContextClosedEvent** là thông báo Spring **bắt đầu đóng ApplicationContext**. Trong đường đóng thông thường của **AbstractApplicationContext**, sự kiện được publish **trước** bước dừng lifecycle components và destroy singleton beans. Hãy dùng nó để biết context đang đóng; dùng **SmartLifecycle** và destroy callbacks để dọn tài nguyên có thứ tự và trách nhiệm rõ ràng.

### Tài liệu tham khảo chính thức

- Spring Framework Reference, *Standard and Custom Events*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Javadoc, *ContextClosedEvent*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/ContextClosedEvent.html
- Spring Framework Javadoc, *AbstractApplicationContext*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Framework Javadoc, *ConfigurableApplicationContext*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html
- Spring Framework Reference, *Lifecycle Callbacks*: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework Javadoc, *SmartLifecycle*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/SmartLifecycle.html
