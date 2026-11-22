# Tác động của listener chậm lên request

Trong Spring Framework Application Events, khi một HTTP request gọi `ApplicationEventPublisher.publishEvent(...)`, listener **mặc định** được chạy đồng bộ trên chính luồng công bố event nếu ứng dụng dùng `SimpleApplicationEventMulticaster` với cấu hình mặc định. Vì vậy, một listener thực hiện công việc chậm (gửi email, gọi HTTP API, ghi file, đợi database hoặc `Thread.sleep`) có thể giữ request đang chờ cho đến khi listener hoàn tất. Đây là ảnh hưởng trực tiếp đến **response time, khả năng xử lý đồng thời và tính ổn định của endpoint**.

Bài học tập trung vào trường hợp xử lý đồng bộ: điều gì xảy ra trong request, vì sao hệ thống chậm dưới tải, tác động của lỗi listener và cách chọn phương án xử lý thích hợp. Việc chuyển sang bất đồng bộ được đề cập như một quyết định thiết kế, không phải hành vi mặc định của Spring Events.

## 1. Listener chậm nằm ở đâu trong vòng đời request?

Với ứng dụng Spring MVC dùng luồng request theo mô hình servlet thông thường, đường đi điển hình là:

~~~text
Client
  | POST /orders
  v
HTTP request thread
  -> Controller
     -> Service
        -> publisher.publishEvent(orderCreatedEvent)
           -> EventMulticaster
              -> Listener A (20 ms)
              -> Listener B (600 ms, gọi dịch vụ bên ngoài)
              -> Listener C (30 ms)
        <- publishEvent() hoàn thành
     <- Service trả về
  <- Controller tạo HTTP response
Client nhận response
~~~

Các con số trên chỉ là **tình huống giả định** để dễ hình dung, không phải thời gian được Spring bảo đảm. Khi tất cả listener được chạy tuần tự, riêng bước phát event đã chiếm khoảng `20 + 600 + 30 = 650 ms`, chưa tính thời gian controller, service, network hoặc chi phí khác.

Điểm then chốt: `publishEvent(...)` không mặc nhiên có nghĩa là “đưa vào một hàng đợi rồi trả về ngay”. Với cơ chế đồng bộ mặc định, Spring gọi các listener phù hợp trước khi lệnh này trả về. Vì thế, code đứng **sau** `publishEvent(...)` trong cùng call stack phải đợi listener đang chạy xong.

`ApplicationEventPublisher` chỉ định nghĩa việc công bố event; cách dispatch cụ thể do multicaster và cấu hình ứng dụng quyết định. Nếu đã bật executor riêng hoặc `@Async`, thời điểm và luồng thực thi có thể khác.

### Phân biệt “không thấy kết quả listener” và “không phải chờ listener”

Listener có thể trả về `void`, không cung cấp giá trị cho controller, nhưng nó vẫn chiếm thời gian của request trong chế độ đồng bộ. Không dùng kết quả trả về **không đồng nghĩa** với việc listener được chạy ở background.

Trong Spring mặc định, listener thường thực thi trên **cùng thread** với nơi gọi `publishEvent`, nên không cần chuyển thread để lọc hoặc gọi listener. Điều này cũng đồng nghĩa request phải gánh thời gian listener chậm.

## 2. Minh họa thời gian chờ và request latency

Giả sử request cần 40 ms để kiểm tra đầu vào và lưu dữ liệu, listener thực hiện I/O mất 600 ms, sau đó framework cần 10 ms để hoàn thiện response:

| Giai đoạn | Khoảng thời gian giả định | Request đang làm gì? |
| --- | ---: | --- |
| Controller và service trước event | 40 ms | Xử lý nghiệp vụ |
| Listener đồng bộ | 600 ms | Đợi listener hoàn tất trên cùng call stack |
| Hoàn thiện response | 10 ms | Tạo và gửi phản hồi |
| **Tổng thời gian phía server** | **650 ms** | Chưa cộng network giữa client và server |

Có thể hiểu gần đúng:

~~~text
Response time
 ≈ thời gian trước publish
 + thời gian dispatch và tất cả listener đồng bộ
 + thời gian sau publish
 + chi phí HTTP / I/O khác
~~~

Nếu một listener thỉnh thoảng mất 5 giây do timeout khi gọi hệ thống ngoài, request tương ứng có thể chậm bất thường dù các bước xử lý nghiệp vụ chính chỉ mất vài chục mili giây. Đây là nguyên nhân phổ biến của **độ trễ đuôi** (p95, p99) tăng mạnh.

Nếu có nhiều listener, mặc định `SimpleApplicationEventMulticaster` gọi chúng trong luồng công bố, theo thứ tự được Spring xác định; không nên dựa vào thứ tự ngẫu nhiên. Có thể sử dụng `@Order` khi thứ tự có ý nghĩa. Tuy nhiên, đổi thứ tự không loại bỏ tổng thời gian chờ nếu tất cả vẫn phải chạy đồng bộ.

## 3. Ví dụ Java 17+ chạy được với Spring Framework

Ví dụ này mô phỏng một luồng HTTP bằng thread có tên `http-request-demo`. Nó dùng **Spring Context thực**, `@EventListener` thực và multicaster đồng bộ mặc định; chương trình **không mở HTTP server**. Cách mô phỏng cho phép quan sát chính xác vị trí bị chặn mà không cần cấu hình Servlet container.

Tạo một dự án Gradle với cấu trúc:

~~~text
slow-listener-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/SlowListenerRequestDemo.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'slow-listener-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'demo.SlowListenerRequestDemo'
}
~~~

File `src/main/java/demo/SlowListenerRequestDemo.java`:

~~~java
package demo;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class SlowListenerRequestDemo {

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                 new AnnotationConfigApplicationContext(DemoConfig.class)) {

            // Mô phỏng một thread đang phục vụ HTTP request.
            Thread requestThread = new Thread(
                () -> context.getBean(RequestHandler.class).handleRequest(),
                "http-request-demo"
            );

            requestThread.start();
            requestThread.join();
        }
    }

    @Configuration
    static class DemoConfig {
        @Bean
        RequestHandler requestHandler(ApplicationEventPublisher publisher) {
            return new RequestHandler(publisher);
        }

        @Bean
        SlowListener slowListener() {
            return new SlowListener();
        }
    }

    static class OrderSubmittedEvent extends ApplicationEvent {
        OrderSubmittedEvent(Object source) {
            super(source);
        }
    }

    static class RequestHandler {
        private final ApplicationEventPublisher publisher;

        RequestHandler(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void handleRequest() {
            System.out.println(
                "request: trước publishEvent (" +
                Thread.currentThread().getName() + ")"
            );

            publisher.publishEvent(new OrderSubmittedEvent(this));

            System.out.println(
                "request: sau publishEvent (" +
                Thread.currentThread().getName() + ")"
            );
            System.out.println("request: có thể trả response");
        }
    }

    static class SlowListener {
        @EventListener
        public void onOrderSubmitted(OrderSubmittedEvent event) {
            System.out.println(
                "listener: bắt đầu (" +
                Thread.currentThread().getName() + ")"
            );

            try {
                Thread.sleep(600); // Chỉ để mô phỏng I/O chậm.
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                    "Listener bị ngắt", ex
                );
            }

            System.out.println(
                "listener: kết thúc (" +
                Thread.currentThread().getName() + ")"
            );
        }
    }
}
~~~

Với JDK 17+ và Gradle đã cài, chạy tại thư mục dự án:

~~~bash
gradle run --quiet
~~~

Nếu dự án đã có Gradle Wrapper, có thể thay bằng `./gradlew run --quiet` (macOS/Linux) hoặc `gradlew.bat run --quiet` (Windows).

**Các dòng stdout do chương trình in ra, theo đúng thứ tự** (bỏ qua log môi trường nếu có):

~~~text
request: trước publishEvent (http-request-demo)
listener: bắt đầu (http-request-demo)
listener: kết thúc (http-request-demo)
request: sau publishEvent (http-request-demo)
request: có thể trả response
~~~

Vì `Thread.sleep(600)` được gọi bên trong listener đồng bộ, dòng “request: sau publishEvent” chỉ xuất hiện **sau** dòng “listener: kết thúc”. Cả request và listener hiển thị cùng tên thread: `http-request-demo`. Thời gian thực tế có thể chênh lệch do scheduling và khởi tạo môi trường, nhưng trình tự này cho thấy call stack bị chặn. `Thread.sleep` chỉ là công cụ minh họa; không dùng nó để “giả lập công việc nền” trong code sản xuất.

**Áp dụng vào Controller thật:** Trong Spring MVC, thread ở ví dụ tương ứng với thread đang xử lý lời gọi controller. Nếu controller hoặc service phát event rồi trả `ResponseEntity`, response thông thường chỉ được tạo sau khi listener đồng bộ hoàn tất hoặc lỗi được xử lý. Đặt event ở tầng service không làm nó tự động chạy bất đồng bộ.

## 4. Tác động dưới tải: request thread bị giữ lâu

Một request chậm gây trễ cho chính client đó. Nhiều request đồng thời lại có thể gây hiệu ứng dây chuyền:

1. **Giữ thread phục vụ request:** Spring MVC trên Servlet container thường dùng nhóm thread có giới hạn để tiếp nhận và xử lý request. Trong lúc listener chờ I/O, thread đó chưa phục vụ request mới.
2. **Giảm thông lượng hiệu dụng:** Khi nhu cầu tăng, thread bận và request đợi trong hàng nhận/phân phối tăng. Những endpoint không dùng event đó cũng có thể chịu ảnh hưởng nếu chia sẻ cùng tài nguyên.
3. **Tăng p95/p99:** Listener gọi API ngoài thường có thời gian đáp ứng dao động; vài lượt chậm có thể chi phối độ trễ đuôi.
4. **Dễ chạm timeout:** Client, reverse proxy, load balancer hoặc server có thể hết thời gian chờ. Timeout phía client **không mặc nhiên** dừng listener Java đang chạy; còn phụ thuộc thiết kế hủy công việc và từng thành phần.
5. **Tăng áp lực lên tài nguyên:** Nếu listener đồng thời giữ connection, khóa, bộ nhớ, CPU hoặc transaction, sự chậm trễ không còn giới hạn ở riêng request thread.

Một phép ước lượng hữu ích theo quan hệ giữa số request đến và thời gian phục vụ: giả sử có **50 request/giây**, mỗi request thêm **0,4 giây** chỉ để đợi listener, thì ở trạng thái ổn định hệ thống cần trung bình khoảng `50 × 0,4 = 20` request đồng thời **chỉ cho phần chờ phát sinh này**. Đây là ví dụ định lượng, không phải số đo của ứng dụng cụ thể; thực tế chịu ảnh hưởng bởi phân bố tải, giới hạn thread và cách triển khai.

Với Spring WebFlux, tác hại có thể còn nghiêm trọng hơn nếu listener blocking chạy ngay trên event-loop thread: một `Thread.sleep` hay I/O đồng bộ không phù hợp có thể chặn việc xử lý nhiều kết nối khác. Với luồng reactive, phải tôn trọng mô hình non-blocking và chiến lược chuyển tác vụ blocking ra scheduler thích hợp. Bài học ở đây lấy **Spring MVC đồng bộ** làm mô hình chính.

## 5. Listener chậm ở trong transaction có thể giữ tài nguyên lâu hơn

Xét tình huống điển hình:

~~~java
@Transactional
public void createOrder(CreateOrderCommand command) {
    Order order = repository.save(toOrder(command));
    publisher.publishEvent(new OrderCreatedEvent(this, order.getId()));
}
~~~

Đây là **đoạn minh họa đặt trong service đã có** (các kiểu `Order`, `CreateOrderCommand`, `OrderCreatedEvent`, `repository` và `toOrder` thuộc nghiệp vụ ứng dụng, không phải chương trình độc lập).

Nếu listener là `@EventListener` đồng bộ, nó chạy **ngay tại thời điểm publish**, thường **trước khi phương thức transaction kết thúc và commit**. Listener chậm có thể kéo dài khoảng thời gian transaction còn mở, đồng thời tăng thời gian giữ connection hoặc lock liên quan đến transaction. Điều đó còn có thể ảnh hưởng tới các request khác đang chờ cùng dữ liệu.

Lưu ý các khác biệt:

- Listener `@EventListener` đồng bộ có thể thực thi trong transaction hiện tại khi được gọi ở cùng thread và transaction đang hoạt động.
- `@TransactionalEventListener` mặc định gắn vào pha `AFTER_COMMIT`, cho phép chạy khi transaction đã commit thành công; nó **không mặc nhiên chuyển listener sang thread nền**. Trong mô hình transaction gắn với thread, callback có thể vẫn chạy khi kết thúc transaction trên request thread, vì vậy request vẫn có thể phải chờ.
- Mặc định, nếu không có transaction phù hợp, `@TransactionalEventListener` **không thực thi**; có thể đổi với `fallbackExecution = true` nếu nghiệp vụ thực sự cần.
- Dời xử lý sang sau commit giúp phân tách thời điểm xử lý so với transaction, nhưng **không đồng nghĩa giảm latency** nếu callback vẫn đồng bộ.

Nếu công việc phải xảy ra **sau khi dữ liệu lưu thành công**, cần xét thời điểm commit và độ bền của cơ chế xử lý, thay vì chỉ thêm một annotation để giảm thời gian chờ.

## 6. Lỗi listener cũng có thể trở thành lỗi request

Giả sử một listener đồng bộ gọi dịch vụ thông báo và ném `RuntimeException`. Với `SimpleApplicationEventMulticaster` mặc định và không cấu hình xử lý lỗi riêng, exception đó có thể truyền ngược lên `publishEvent(...)`. Khi đó:

- Các dòng code sau `publishEvent(...)` trong service/controller có thể không được thực thi.
- HTTP request có thể trả lỗi nếu exception không được xử lý ở tầng ứng dụng.
- Nếu exception xuyên qua ranh giới phương thức `@Transactional`, transaction có thể bị rollback theo quy tắc rollback của transaction manager.
- Những listener phía sau có thể không được gọi nếu dispatch bị ngắt do lỗi; không nên xây nghiệp vụ dựa vào giả định “mọi listener luôn chạy đủ” khi một listener thất bại.

Điều này có mặt tích cực khi listener là **một phần không thể thiếu của nghiệp vụ đồng bộ**: caller biết rằng toàn bộ bước bắt buộc phải thành công trước khi trả kết quả. Nhưng với email hoặc thông báo phụ, việc một API ngoài gặp sự cố làm endpoint đặt hàng thất bại có thể là ràng buộc không mong muốn.

Nếu cần bắt lỗi tại listener, hãy xác định rõ cơ chế retry, ghi nhận thất bại và trạng thái nghiệp vụ. “Nuốt exception” để request trả thành công có thể che giấu mất việc và không làm hệ thống đáng tin cậy hơn.

## 7. Chọn giải pháp theo yêu cầu nghiệp vụ

| Cách triển khai | Request có phải chờ? | Trường hợp phù hợp | Điều cần quan tâm |
| --- | --- | --- | --- |
| `@EventListener` đồng bộ mặc định | Có, tới khi listener hoàn tất | Validation, kiểm tra quy tắc bắt buộc, xử lý cần trả lỗi cùng request | Latency, transaction, exception, giới hạn thời gian |
| `@Async` trên `@EventListener` và bật async support | Thường không đợi **phần xử lý đã giao cho executor**, nhưng vẫn tốn thời gian giao tác vụ | Tác vụ phụ, chấp nhận xử lý sau response | Executor giới hạn, queue, rejection, lỗi nền và mất việc khi tiến trình chết |
| Multicaster với `TaskExecutor` | Tùy loại listener và khả năng xử lý async | Muốn điều khiển chiến lược dispatch tập trung | Listener không hỗ trợ async vẫn có thể chạy đồng bộ, cần cấu hình rõ |
| `@TransactionalEventListener(phase = AFTER_COMMIT)` | Vẫn có thể chờ | Chỉ xử lý sau commit thành công | **Không tự động async**, transaction callback có ngữ nghĩa riêng |
| Queue/broker kèm outbox | Request chờ đến bước ghi nhận công việc bền vững, không phải đợi worker xử lý | Email, tích hợp hệ thống, các tác vụ phải chạy bền vững sau commit | Retry, idempotency, giám sát, eventual consistency |

### Khi dùng `@Async`: phải có cấu hình executor và xử lý lỗi

Spring hỗ trợ đặt `@Async` cùng `@EventListener`, nhưng phải bật async support, chẳng hạn bằng `@EnableAsync`. Ví dụ cấu hình executor có giới hạn cho **một ứng dụng Spring đã có** (đây là phần tích hợp, không phải chương trình chạy độc lập):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class EventExecutorConfig {

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("app-event-");
        executor.initialize();
        return executor;
    }
}
~~~

Khi listener được Spring quản lý như một bean, phương thức của listener có thể khai báo:

~~~java
@Async("eventExecutor")
@EventListener
public void onOrderSubmitted(OrderSubmittedEvent event) {
    processNotification(event);
}
~~~

Đoạn phương thức trên **minh họa điểm gắn annotation trong listener nghiệp vụ đã có**; `OrderSubmittedEvent` và `processNotification(...)` là thành phần của chính ứng dụng, nên không phải ví dụ Java độc lập. Nếu muốn thử với demo ở mục 3, có thể chuyển lớp listener thành bean async, dùng `Thread.sleep(600)` trong thân phương thức và quan sát thứ tự log không còn bảo đảm như trước.

Tính chất cần nắm khi chuyển sang bất đồng bộ:

- Khi tác vụ đã được executor nhận, listener thường chạy trên thread khác và request không cần đợi toàn bộ I/O bên trong listener.
- **Executor không vô hạn.** Khi pool và queue đều đầy, việc submit có thể bị từ chối; nếu dùng chính sách `CallerRunsPolicy`, công việc có thể chạy lại trên request thread và gây chậm request. Đặt chính sách quá tải phù hợp thay vì mặc định rằng mọi publish đều nhanh.
- Exception xảy ra **bên trong listener void chạy async** không tự truyền ngược tới request đã trả về; cần logger, `AsyncUncaughtExceptionHandler`, retry hoặc cơ chế theo dõi thất bại.
- Transaction, SecurityContext, MDC/trace context hay giá trị dựa trên `ThreadLocal` **không mặc nhiên** được sao chép sang thread nền. Nếu cần, dùng cơ chế context propagation phù hợp và truyền dữ liệu bất biến/ID cần thiết trong event.
- Không đưa entity JPA lazy hoặc đối tượng gắn với request/transaction sang thread khác rồi mặc định cho rằng tài nguyên vẫn còn hiệu lực. Ưu tiên gửi ID hoặc bản dữ liệu bất biến và truy vấn lại khi cần.
- `@Async` dùng thread pool trong cùng tiến trình **không đảm bảo độ bền công việc** nếu tiến trình dừng ngay sau khi nhận event. Tác vụ quan trọng cần cơ chế lưu bền và retry.

### Khi cần tác vụ chắc chắn được xử lý sau commit

Ví dụ gửi thông báo khi đơn hàng tạo thành công và không muốn mất thông báo nếu dịch vụ khởi động lại: có thể ghi đơn hàng và **outbox record** trong cùng transaction, sau đó worker đọc outbox để gửi thông báo. Worker phải xử lý retry, đánh dấu trạng thái và chống gửi trùng (idempotency). Queue/broker giúp chuyển việc ra khỏi request, nhưng yêu cầu “đã xử lý thành công” phải được phản ánh bằng cơ chế xác nhận thực tế, không chỉ dựa vào việc gọi `publishEvent`.

## 8. Kiểm tra hiệu năng và hành vi thực tế

Đừng suy đoán từ annotation hoặc chỉ nhìn log của controller; nên đo đúng các ranh giới:

1. Đặt timer quanh `publishEvent(...)` để biết thời gian dành cho dispatch và listener đồng bộ. So sánh với tổng thời gian controller/server và thời gian request phía client.
2. Ghi tên thread trong publisher và listener khi debug để xác nhận cùng thread hay khác thread. Với async, thứ tự log không còn là bằng chứng đáng tin về thành công/thất bại.
3. Thử listener nhanh, listener chậm khoảng 600 ms và listener ném exception, sau đó xác nhận thứ tự log, mã HTTP và rollback theo đúng thiết kế nghiệp vụ.
4. Load test với mức concurrency có kiểm soát; quan sát p50/p95/p99, thread đang bận, queue, connection pool và số lần timeout. Một request chậm không đủ để chứng minh throughput toàn hệ thống bị giới hạn.
5. Nếu dùng executor, theo dõi active threads, queue depth, rejected tasks, độ trễ từ submit đến execute và tỷ lệ lỗi; cần chính sách backpressure rõ ràng.
6. Với I/O bên ngoài, cấu hình connect/read timeout, retry có giới hạn và circuit breaker khi phù hợp. Nếu thiếu timeout, listener có thể chặn request quá lâu.

Spring Framework không mặc định tạo observation riêng cho từng lời gọi `@EventListener` để tự động tách chi phí của listener khỏi request. Nếu cần số đo chính xác, hãy instrument vùng listener bằng metric/trace riêng hoặc dùng profiler.

## 9. Những nhầm lẫn thường gặp

- **“Dùng event là tách biệt request.”** Event giúp tách publisher khỏi listener về mặt phụ thuộc mã nguồn; dispatch vẫn có thể đồng bộ.
- **“Listener trả `void` nên không chặn.”** Phương thức `void` vẫn chạy và tốn thời gian; caller đợi nó hoàn thành trong chế độ đồng bộ.
- **“Thêm `@TransactionalEventListener` là request trả ngay.”** Annotation này định thời điểm theo transaction, không tự tạo thread nền.
- **“Bật `@Async` là không thể mất event.”** Task trong memory có thể mất khi ứng dụng dừng; executor có thể quá tải.
- **“Client timeout thì listener tự động dừng.”** Việc hủy xử lý phụ thuộc công nghệ, ngữ cảnh và cách viết listener; không có bảo đảm chung.
- **“Cache danh sách listener giúp bỏ qua listener chậm.”** Cache chỉ giảm công đoạn chọn listener phù hợp. Mỗi event vẫn gọi listener, và công việc chậm vẫn chậm.

**Nguyên tắc áp dụng:** Nếu kết quả của listener là điều kiện bắt buộc để xác nhận request thành công, cân nhắc xử lý đồng bộ có timeout và giám sát. Nếu đó là hậu xử lý độc lập (email, audit bất đồng bộ, đồng bộ hệ thống ngoài), cân nhắc `@Async` hoặc queue/outbox theo mức độ tin cậy cần có. Quyết định dựa trên ranh giới transaction, độ bền công việc và mục tiêu latency thực tế.

### Tài liệu tham khảo

- [Spring Framework — Application Events, synchronous và asynchronous listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Observability for Application Events](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Framework — Task Execution and `@Async`](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Maven Central — org.springframework:spring-context](https://central.sonatype.com/artifact/org.springframework/spring-context/6.2.19)