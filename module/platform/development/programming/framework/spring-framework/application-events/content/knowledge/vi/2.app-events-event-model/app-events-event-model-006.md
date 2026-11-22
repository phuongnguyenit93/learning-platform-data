# Event đồng bộ mặc định trong Spring

## 1. Mục tiêu và bối cảnh

Spring Application Events cho phép một thành phần thông báo rằng một sự việc đã xảy ra để các thành phần khác phản ứng mà không cần publisher gọi trực tiếp từng listener. Ví dụ, dịch vụ tạo đơn hàng phát sự kiện OrderCreatedEvent; listener có thể gửi thông báo, ghi audit hoặc cập nhật một phần dữ liệu liên quan.

Trong cấu hình mặc định của Spring Framework, việc xử lý event là **đồng bộ**. Khi publisher gọi ApplicationEventPublisher.publishEvent(...), Spring gọi các listener phù hợp ngay trên thread đang phát event. Lệnh publishEvent chỉ trả về sau khi các listener đồng bộ đã chạy xong.

Đây là hành vi mặc định của ApplicationContext khi Spring sử dụng SimpleApplicationEventMulticaster mà không cấu hình TaskExecutor. Hành vi có thể thay đổi nếu ứng dụng thay thế multicaster hoặc chủ động dùng cơ chế bất đồng bộ. Vì vậy, cần phân biệt hợp đồng của publishEvent với cấu hình dispatch thực tế: API publishEvent chuyển event tới multicaster; chính multicaster quyết định cách gọi listener.

Sau bài học, bạn có thể:
- Mô tả luồng từ publisher đến listener và vai trò của ApplicationEventPublisher.
- Giải thích vì sao listener mặc định chạy trên cùng thread với publisher.
- Viết một ứng dụng Spring nhỏ để quan sát thứ tự thực thi.
- Nhận biết ảnh hưởng của listener chậm, exception và transaction.
- Biết những cách phổ biến để chuyển listener sang xử lý bất đồng bộ khi thật sự cần.

## 2. Các thành phần trong mô hình event

**Event** là đối tượng mô tả một sự việc đã xảy ra, thường mang dữ liệu cần thiết để listener xử lý. Nên đặt tên theo sự kiện, chẳng hạn OrderCreatedEvent, PaymentCompletedEvent hoặc UserRegisteredEvent. Dùng record hoặc lớp bất biến giúp dữ liệu event không bị thay đổi ngoài ý muốn sau khi phát.

**Publisher** là thành phần phát event thông qua ApplicationEventPublisher. Trong ứng dụng Spring, có thể inject interface này vào service thay vì tự tìm listener hoặc gọi từng listener.

**Listener** là thành phần nhận event. Cách thường dùng là đặt @EventListener trên một method của bean do Spring quản lý. Spring đăng ký method đó và gọi nó khi event phù hợp được phát.

**ApplicationEventMulticaster** là thành phần điều phối event tới các listener đã đăng ký. Nếu ứng dụng không cung cấp bean có tên applicationEventMulticaster, ApplicationContext tạo SimpleApplicationEventMulticaster mặc định. Khi không gắn TaskExecutor, multicaster gọi listener trực tiếp trong thread hiện tại.

Từ Spring Framework 4.2, publisher có thể phát một object Java thông thường; không bắt buộc event phải kế thừa ApplicationEvent. Ví dụ bên dưới dùng record OrderCreatedEvent.

## 3. Luồng thực thi đồng bộ

Giả sử một service thực hiện ba bước:

1. In ra thông báo trước khi phát event.
2. Gọi publishEvent(new OrderCreatedEvent(...)).
3. In ra thông báo sau khi publishEvent trả về.

Khi có listener phù hợp, thứ tự mặc định là:

~~~text
Publisher: trước publishEvent
Listener:  bắt đầu xử lý event
Listener:  xử lý xong event
Publisher: sau publishEvent
~~~

Listener chạy ngay trong lời gọi publishEvent. Nếu publisher đang chạy trên thread tên publisher-thread, listener đồng bộ cũng chạy trên publisher-thread. Không có thread mới hoặc hàng đợi trung gian được tạo chỉ vì ứng dụng dùng @EventListener.

Điều này có nghĩa là thời gian xử lý listener nằm trong thời gian thực thi của publisher. Nếu listener mất 800 ms, publisher phải chờ phần xử lý đó hoàn tất trước khi đi tiếp, trừ khi listener hoặc multicaster được cấu hình bất đồng bộ.

## 4. Ví dụ chạy được với Java 17+

Ví dụ dùng Spring Framework 6.2.0, Maven và Java 17. Tạo cấu trúc dự án:

~~~text
spring-sync-events/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── events/
                        ├── EventDemo.java
                        ├── OrderCreatedEvent.java
                        ├── OrderService.java
                        └── OrderCreatedListener.java
~~~

### 4.1. Khai báo dependency

Tệp pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-sync-events</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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

### 4.2. Tạo event

Tệp src/main/java/com/example/events/OrderCreatedEvent.java:

~~~java
package com.example.events;

public record OrderCreatedEvent(String orderId) {
}
~~~

Record lưu mã đơn hàng và cung cấp accessor orderId(). Đây là một event object thông thường; không cần kế thừa ApplicationEvent.

### 4.3. Tạo publisher

Tệp src/main/java/com/example/events/OrderService.java:

~~~java
package com.example.events;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher eventPublisher;

    public OrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void create(String orderId) {
        System.out.println("1. Trước publish: "
                + Thread.currentThread().getName());

        eventPublisher.publishEvent(new OrderCreatedEvent(orderId));

        System.out.println("3. Sau publish: "
                + Thread.currentThread().getName());
    }
}
~~~

OrderService chỉ phụ thuộc vào ApplicationEventPublisher. Service không cần biết có bao nhiêu listener, listener nằm ở đâu hoặc listener sẽ thực hiện công việc gì.

### 4.4. Tạo listener

Tệp src/main/java/com/example/events/OrderCreatedListener.java:

~~~java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @EventListener
    public void handle(OrderCreatedEvent event) {
        System.out.println("2. Listener: "
                + Thread.currentThread().getName()
                + " xử lý " + event.orderId());
    }
}
~~~

Spring phát hiện method có @EventListener trong bean được quản lý và đăng ký method đó làm listener cho OrderCreatedEvent. Tham số method xác định kiểu event mà listener nhận.

### 4.5. Khởi tạo ApplicationContext và chạy thử

Tệp src/main/java/com/example/events/EventDemo.java:

~~~java
package com.example.events;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan
public class EventDemo {

    public static void main(String[] args) {
        Thread.currentThread().setName("publisher-thread");

        try (var context =
                     new AnnotationConfigApplicationContext(EventDemo.class)) {
            context.getBean(OrderService.class).create("ORD-1001");
        }
    }
}
~~~

@ComponentScan không chỉ định package nên Spring quét package của EventDemo và các package con. Các class OrderService và OrderCreatedListener cùng package được đăng ký thành bean.

Chạy từ thư mục có pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=com.example.events.EventDemo
~~~

Kết quả phần chương trình in ra:

~~~text
1. Trước publish: publisher-thread
2. Listener: publisher-thread xử lý ORD-1001
3. Sau publish: publisher-thread
~~~

Dòng listener xuất hiện giữa hai dòng của publisher. Cả ba dòng đều hiển thị publisher-thread, chứng minh listener chạy trên thread đang gọi publishEvent. Nếu listener chạy bất đồng bộ, publisher có thể in dòng số 3 trước khi listener hoàn tất và thread của listener có thể khác.

## 5. Điều gì xảy ra khi có nhiều listener?

Một event có thể được nhiều listener cùng quan tâm. Khi event được phát, multicaster tìm các listener có thể xử lý kiểu event đó và gọi chúng theo cấu hình dispatch.

Nếu cần xác định thứ tự giữa các listener, có thể dùng @Order trên method hoặc bean. Giá trị order nhỏ hơn có độ ưu tiên cao hơn. Ví dụ:

~~~java
@Order(1)
@EventListener
public void updateInventory(OrderCreatedEvent event) {
    // Cập nhật tồn kho
}

@Order(2)
@EventListener
public void sendNotification(OrderCreatedEvent event) {
    // Gửi thông báo
}
~~~

Không nên dựa vào thứ tự ngẫu nhiên hoặc thứ tự đăng ký tình cờ khi nghiệp vụ yêu cầu một listener phải chạy trước listener khác. Nếu các bước phụ thuộc chặt chẽ vào nhau, một service điều phối tuần tự thường dễ hiểu và dễ kiểm soát hơn việc chia chúng thành nhiều listener độc lập.

## 6. Hệ quả của xử lý đồng bộ

### 6.1. Listener chậm làm publisher chậm

Publisher phải chờ listener đồng bộ hoàn tất. Một listener gọi dịch vụ bên ngoài, truy vấn cơ sở dữ liệu chậm hoặc thực hiện tác vụ nặng có thể làm tăng thời gian phản hồi của luồng gọi publishEvent.

Vì vậy, listener mặc định phù hợp với công việc ngắn, cần thực hiện ngay trong cùng luồng xử lý. Không nên đưa tác vụ kéo dài vào listener nếu publisher không cần chờ tác vụ đó.

### 6.2. Exception có thể truyền ngược về publisher

Với SimpleApplicationEventMulticaster mặc định không cấu hình ErrorHandler, exception phát sinh khi gọi listener có thể truyền ngược qua publishEvent tới publisher. Lỗi trong một listener cũng có thể làm lượt multicast hiện tại dừng trước khi các listener tiếp theo được gọi.

Do đó, cần quyết định rõ cách xử lý lỗi trong listener. Có thể bắt và xử lý lỗi tại listener khi lỗi đó có thể được khắc phục tại chỗ; nếu lỗi cần làm thao tác phát event thất bại, hãy để nó truyền lên theo thiết kế nghiệp vụ. Không nên nuốt mọi exception vì như vậy publisher có thể tưởng rằng toàn bộ xử lý đã thành công.

### 6.3. Event trong Spring không phải message queue

Application Events là cơ chế giao tiếp trong cùng ApplicationContext/process. Bản thân nó không cung cấp lưu trữ bền vững, retry sau khi ứng dụng dừng, xác nhận đã nhận, phân phối tới ứng dụng khác hoặc bảo đảm giao hàng đúng một lần.

Nếu cần giao tiếp giữa nhiều service, retry, lưu trữ event hoặc xử lý sau khi process khởi động lại, hãy cân nhắc message broker và transactional outbox. Không nên xem publishEvent như một lệnh gửi message tới hệ thống bên ngoài.

## 7. Khi nào cần bất đồng bộ?

Nếu publisher không cần chờ công việc của listener, có thể chủ động cấu hình bất đồng bộ. Một cách phổ biến là bật async processing và đánh dấu listener bằng @Async:

~~~java
package com.example.events;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
@ComponentScan
public class AsyncEventConfiguration {
}
~~~

~~~java
package com.example.events;

import org.springframework.scheduling.annotation.Async;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @Async
    @EventListener
    public void handle(OrderCreatedEvent event) {
        // Công việc này được thực hiện qua executor của @Async.
    }
}
~~~

Trong ứng dụng thực tế, nên cấu hình executor phù hợp với tải công việc thay vì để số lượng tác vụ không được kiểm soát.

Một cách khác là khai báo bean SimpleApplicationEventMulticaster có tên applicationEventMulticaster và gắn TaskExecutor cho nó. Cách này thay đổi cơ chế dispatch ở cấp ApplicationContext nên cần đánh giá ảnh hưởng tới tất cả listener liên quan.

Khi chuyển sang bất đồng bộ, cần lưu ý:

- Publisher có thể tiếp tục trước khi listener xử lý xong.
- Listener có thể chạy trên thread khác; không thể dựa vào ThreadLocal hoặc ngữ cảnh thread của publisher nếu chưa truyền hoặc thiết lập lại ngữ cảnh cần thiết.
- Exception của listener bất đồng bộ không truyền ngược về lời gọi publishEvent ban đầu. Với method trả về void, cần cấu hình cách ghi nhận và xử lý lỗi async.
- Phải cân nhắc giới hạn thread, hàng đợi, timeout và khả năng quá tải của executor.
- Với @Async trên method @EventListener, không nên dựa vào giá trị trả về của method để phát event tiếp theo; xử lý bất đồng bộ không dùng cơ chế trả về event như listener đồng bộ.

Chỉ chuyển sang async khi yêu cầu nghiệp vụ cho phép publisher không chờ kết quả và hệ thống đã có cách theo dõi lỗi cũng như giới hạn tài nguyên.

## 8. Event có liên quan đến transaction

Listener @EventListener thông thường chạy ngay khi event được phát. Nếu publisher phát event bên trong một phương thức có @Transactional, listener đồng bộ thường được gọi trong luồng xử lý transaction đó, trước khi phương thức transaction hoàn tất.

Điều này có thể gây vấn đề nếu listener thực hiện hành động bên ngoài trước khi transaction commit. Ví dụ, listener gửi email thành công nhưng transaction lưu đơn hàng sau đó rollback; hệ thống đã gửi thông báo cho một đơn hàng không được lưu.

Nếu cần xử lý theo vòng đời transaction, dùng @TransactionalEventListener:

~~~java
package com.example.events;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderCreatedTransactionalListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderCreatedEvent event) {
        // Chỉ xử lý sau khi transaction phát event đã commit.
    }
}
~~~

Để biên dịch và sử dụng listener transaction, thêm dependency spring-tx cùng phiên bản Spring Framework vào pom.xml và cấu hình PlatformTransactionManager phù hợp. Publisher cũng phải phát event trong một transaction đang hoạt động, thường thông qua phương thức có @Transactional và transaction management được bật. Ví dụ chạy ở mục 4 chỉ minh họa xử lý đồng bộ, chưa cấu hình transaction manager.

Mặc định, phase của @TransactionalEventListener là AFTER_COMMIT. Nếu không có transaction, listener không được gọi, trừ khi bật fallbackExecution = true. Annotation này điều khiển thời điểm theo transaction, tự nó không có nghĩa là xử lý bất đồng bộ.

Nếu công việc sau commit phải được bảo đảm không thất lạc khi process dừng đột ngột, chỉ dùng callback trong ApplicationContext là chưa đủ; cần thiết kế lưu bền vững như transactional outbox hoặc cơ chế message phù hợp.

## 9. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc xử lý |
|---|---|---|
| Listener không được gọi | Bean listener không nằm trong ApplicationContext, package scan không bao phủ bean hoặc kiểu tham số không khớp event | Kiểm tra component scan, bean registration và kiểu event |
| Publisher bị chậm | Listener đồng bộ thực hiện công việc lâu | Đo thời gian từng listener; chuyển công việc phù hợp sang async |
| Exception xuất hiện tại publishEvent | Listener đồng bộ phát sinh exception | Kiểm tra stack trace của listener và chính sách ErrorHandler |
| Listener chạy trên thread khác | Có @Async hoặc multicaster dùng TaskExecutor | Kiểm tra cấu hình async và tên thread |
| Listener transaction không chạy | Event không được phát trong transaction và fallbackExecution không bật | Kiểm tra ranh giới @Transactional và phase |
| Gửi thông báo dù transaction rollback | Dùng @EventListener thông thường để thực hiện hành động trước commit | Cân nhắc @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT) hoặc outbox |

Khi debug, hãy kiểm tra lần lượt: publisher có thật sự gọi publishEvent không; event được tạo có đúng kiểu không; listener có phải bean Spring không; method có @EventListener không; và ApplicationContext có dùng multicaster mặc định hay đã bị cấu hình thay thế.

## 10. Ghi nhớ

Trong cấu hình Spring mặc định, ApplicationContext dùng SimpleApplicationEventMulticaster không có TaskExecutor. Vì vậy, listener phù hợp được gọi trực tiếp trên thread phát event và publisher chờ listener hoàn tất trước khi publishEvent trả về. Cách này đơn giản, dễ quan sát và phù hợp với xử lý ngắn trong cùng ứng dụng.

Khi cần giảm thời gian chờ, có thể chủ động dùng @Async hoặc cấu hình executor cho multicaster. Khi cần gắn xử lý với thời điểm commit, dùng @TransactionalEventListener. Khi cần độ bền, retry hoặc giao tiếp giữa các process, chọn cơ chế messaging có lưu trữ phù hợp với yêu cầu hệ thống.
