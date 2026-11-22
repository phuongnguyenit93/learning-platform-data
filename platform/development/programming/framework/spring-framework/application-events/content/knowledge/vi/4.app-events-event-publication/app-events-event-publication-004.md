# Phát event từ service và component trong Spring

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao một Spring bean có thể phát application event.
- Inject ApplicationEventPublisher vào bean mang stereotype @Service hoặc @Component.
- Phát event sau khi một hành động nghiệp vụ hoặc một tác vụ của component hoàn tất.
- Tạo event bằng Java record và để listener nhận event theo kiểu dữ liệu.
- Hiểu luồng xử lý mặc định khi gọi publishEvent.
- Chọn vị trí phát event phù hợp, tránh phát quá sớm hoặc phát trùng.
- Nhận biết giới hạn của application event trong cùng ApplicationContext.

## 1. Bean nào có thể phát event?

Trong Spring, phát application event không phải là chức năng riêng của controller hay service. Bất kỳ object nào được Spring quản lý như một bean đều có thể phát event nếu nó nhận được ApplicationEventPublisher.

Hai stereotype thường gặp là:

- @Service: biểu thị một bean chứa logic nghiệp vụ hoặc điều phối một thao tác nghiệp vụ.
- @Component: biểu thị một bean Spring có vai trò chung, chẳng hạn component điều phối import, theo dõi tác vụ hoặc tích hợp một phần kỹ thuật.

Cả hai đều là bean được component scan phát hiện. Spring có thể inject ApplicationEventPublisher vào constructor của chúng.

Một service thường phát event khi trạng thái nghiệp vụ đã thay đổi, ví dụ đơn hàng được tạo hoặc thanh toán hoàn tất. Một component có thể phát event khi một tác vụ mà nó phụ trách hoàn tất, ví dụ một batch import đã được xử lý.

Điểm quyết định không phải annotation nào được dùng, mà là bean có thuộc ApplicationContext đang quản lý listener hay không và event có biểu diễn đúng sự việc vừa xảy ra hay không.

## 2. ApplicationEventPublisher làm nhiệm vụ gì?

ApplicationEventPublisher là interface của Spring dùng để phát một application event:

~~~java
public interface ApplicationEventPublisher {
    void publishEvent(Object event);
}
~~~

Khi inject interface này, bean chỉ cần gọi publishEvent với một object event. Bean phát event không phải tìm listener, gọi từng listener hoặc biết những bean nào đang quan tâm.

Luồng tổng quát:

1. Spring khởi tạo publisher bean và inject ApplicationEventPublisher.
2. Publisher tạo event chứa thông tin về sự việc vừa xảy ra.
3. Publisher gọi publishEvent(event).
4. ApplicationContext dispatch event đến những listener phù hợp đã đăng ký trong context.
5. Các listener thực hiện công việc của mình.

Từ Spring Framework 4.2, event tùy chỉnh có thể là một object Java thông thường. Không bắt buộc phải kế thừa ApplicationEvent. Với Java 17, record thường là cách gọn để biểu diễn payload bất biến.

## 3. Phát event từ một service

Service thường phát event sau khi hoàn thành một bước nghiệp vụ. Ví dụ, OrderService tạo một đơn hàng rồi thông báo cho các thành phần quan tâm bằng OrderPlacedEvent.

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

    public void placeOrder(String orderId, String customerId) {
        // Thực hiện hoặc xác nhận bước tạo đơn hàng.
        System.out.println("1. OrderService: tạo đơn hàng " + orderId);

        eventPublisher.publishEvent(
                new OrderPlacedEvent(orderId, customerId)
        );
    }
}
~~~

OrderService chỉ phụ thuộc vào ApplicationEventPublisher. Nó không cần inject OrderNotificationListener, AuditListener hoặc bất kỳ listener cụ thể nào.

Khi cần thêm một listener mới, service vẫn có thể giữ nguyên. Listener mới chỉ cần được Spring quản lý và đăng ký nhận OrderPlacedEvent.

Trong ứng dụng thực tế, chỉ phát OrderPlacedEvent sau khi thao tác tạo đơn hàng đã đạt trạng thái mà tên event mô tả. Nếu việc lưu dữ liệu thất bại, không nên phát một event khẳng định đơn hàng đã được tạo thành công.

## 4. Phát event từ một component

Một bean có stereotype @Component cũng có thể nhận ApplicationEventPublisher và phát event. Ví dụ, ImportComponent phụ trách một batch import và thông báo khi batch hoàn tất.

~~~java
package com.example.events;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class ImportComponent {

    private final ApplicationEventPublisher eventPublisher;

    public ImportComponent(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void completeImport(String batchId, int importedRecords) {
        // Tại đây giả định quá trình import đã hoàn tất thành công.
        System.out.println(
                "3. ImportComponent: hoàn tất import batch " + batchId
        );

        eventPublisher.publishEvent(
                new ImportCompletedEvent(batchId, importedRecords)
        );
    }
}
~~~

ImportComponent không cần kế thừa lớp đặc biệt và cũng không cần truy cập trực tiếp ApplicationContext. Nó dùng cùng interface ApplicationEventPublisher như OrderService.

Việc phát event từ component phù hợp khi component sở hữu một sự kiện có ý nghĩa rõ ràng trong phạm vi công việc của nó. Nếu component chỉ là một helper nhỏ được gọi trong service, hãy cân nhắc để service phát event tại ranh giới nghiệp vụ thay vì phát event từ mọi lớp trung gian. Cách này giúp tránh phát trùng hoặc làm luồng nghiệp vụ khó theo dõi.

## 5. Định nghĩa event

Mỗi event nên mô tả một sự việc đã xảy ra và mang dữ liệu listener cần dùng.

File OrderPlacedEvent.java:

~~~java
package com.example.events;

public record OrderPlacedEvent(
        String orderId,
        String customerId
) {
}
~~~

File ImportCompletedEvent.java:

~~~java
package com.example.events;

public record ImportCompletedEvent(
        String batchId,
        int importedRecords
) {
}
~~~

Hai event là hai kiểu dữ liệu riêng. Nhờ kiểu tham số của listener, Spring có thể dispatch đúng event đến đúng phương thức xử lý.

Nên dùng tên event ở dạng quá khứ như OrderPlacedEvent hoặc ImportCompletedEvent khi sự việc đã xảy ra. Nếu object biểu diễn một yêu cầu cần thực hiện trong tương lai, hãy đặt tên thể hiện ý nghĩa yêu cầu, chẳng hạn ImportRequestedEvent.

Giữ payload vừa đủ cho listener. Không cần đưa toàn bộ service, repository hoặc ApplicationContext vào event. Nếu event cần mang collection hoặc object mutable, hãy tạo snapshot và bảo vệ dữ liệu trước khi publish.

## 6. Listener nhận event

Publisher và listener được kết nối qua kiểu event. Listener phải là bean Spring và đánh dấu phương thức bằng @EventListener.

~~~java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ApplicationEventListeners {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        System.out.println(
                "2. Listener: đơn hàng " + event.orderId()
                        + " được tạo cho " + event.customerId()
        );
    }

    @EventListener
    public void onImportCompleted(ImportCompletedEvent event) {
        System.out.println(
                "4. Listener: batch " + event.batchId()
                        + " hoàn tất, " + event.importedRecords()
                        + " bản ghi"
        );
    }
}
~~~

Spring chọn phương thức dựa trên kiểu tham số:

- onOrderPlaced nhận OrderPlacedEvent.
- onImportCompleted nhận ImportCompletedEvent.

Một bean listener có thể có nhiều phương thức @EventListener. Cũng có thể tách các listener thành nhiều bean nếu chúng thuộc các trách nhiệm khác nhau.

Publisher không cần gọi trực tiếp các phương thức trên. Điều này giúp service và component phát event không phụ thuộc vào danh sách listener đang tồn tại.

## 7. Ví dụ hoàn chỉnh có thể chạy

Ví dụ dưới đây dùng Java 17 và Spring Boot 3.5.0. OrderService phát event từ một bean @Service; ImportComponent phát event từ một bean @Component. Một listener nhận cả hai kiểu event.

### Cấu trúc thư mục

~~~text
spring-publish-from-beans/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── events/
                        ├── PublishFromBeansApplication.java
                        ├── OrderPlacedEvent.java
                        ├── ImportCompletedEvent.java
                        ├── OrderService.java
                        ├── ImportComponent.java
                        └── ApplicationEventListeners.java
~~~

### 7.1. Dependency

File pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-publish-from-beans</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

### 7.2. Hai event class

File OrderPlacedEvent.java:

~~~java
package com.example.events;

public record OrderPlacedEvent(
        String orderId,
        String customerId
) {
}
~~~

File ImportCompletedEvent.java:

~~~java
package com.example.events;

public record ImportCompletedEvent(
        String batchId,
        int importedRecords
) {
}
~~~

### 7.3. Publisher là service

File OrderService.java:

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

    public void placeOrder(String orderId, String customerId) {
        System.out.println("1. OrderService: tạo đơn hàng " + orderId);

        eventPublisher.publishEvent(
                new OrderPlacedEvent(orderId, customerId)
        );
    }
}
~~~

### 7.4. Publisher là component

File ImportComponent.java:

~~~java
package com.example.events;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class ImportComponent {

    private final ApplicationEventPublisher eventPublisher;

    public ImportComponent(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void completeImport(String batchId, int importedRecords) {
        System.out.println(
                "3. ImportComponent: hoàn tất import batch " + batchId
        );

        eventPublisher.publishEvent(
                new ImportCompletedEvent(batchId, importedRecords)
        );
    }
}
~~~

### 7.5. Listener

File ApplicationEventListeners.java:

~~~java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ApplicationEventListeners {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        System.out.println(
                "2. Listener: đơn hàng " + event.orderId()
                        + " được tạo cho " + event.customerId()
        );
    }

    @EventListener
    public void onImportCompleted(ImportCompletedEvent event) {
        System.out.println(
                "4. Listener: batch " + event.batchId()
                        + " hoàn tất, " + event.importedRecords()
                        + " bản ghi"
        );
    }
}
~~~

### 7.6. Điểm khởi chạy

File PublishFromBeansApplication.java:

~~~java
package com.example.events;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PublishFromBeansApplication implements CommandLineRunner {

    private final OrderService orderService;
    private final ImportComponent importComponent;

    public PublishFromBeansApplication(
            OrderService orderService,
            ImportComponent importComponent
    ) {
        this.orderService = orderService;
        this.importComponent = importComponent;
    }

    public static void main(String[] args) {
        SpringApplication.run(PublishFromBeansApplication.class, args);
    }

    @Override
    public void run(String... args) {
        orderService.placeOrder("ORD-1001", "CUS-01");

        importComponent.completeImport("BATCH-07", 120);
    }
}
~~~

Spring Boot quét package com.example.events và tạo các bean. Khi CommandLineRunner chạy, nó gọi service trước, sau đó gọi component.

Chạy ứng dụng từ thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Bỏ qua log khởi động của Spring Boot, output do ứng dụng in ra chính xác là:

~~~text
1. OrderService: tạo đơn hàng ORD-1001
2. Listener: đơn hàng ORD-1001 được tạo cho CUS-01
3. ImportComponent: hoàn tất import batch BATCH-07
4. Listener: batch BATCH-07 hoàn tất, 120 bản ghi
~~~

Các listener mặc định chạy đồng bộ nên output của listener xuất hiện ngay trong lời gọi publishEvent tương ứng. Sau khi listener xử lý xong, publisher tiếp tục thực thi.

## 8. Constructor injection là cách nên dùng

Có thể inject ApplicationEventPublisher bằng constructor:

~~~java
@Service
public class OrderService {

    private final ApplicationEventPublisher eventPublisher;

    public OrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }
}
~~~

Constructor injection có các lợi ích:

- Dependency được thể hiện rõ trong khai báo bean.
- Field có thể khai báo final.
- Dễ tạo unit test với publisher giả hoặc mock.
- Bean không thể được khởi tạo thiếu dependency cần thiết.

Không cần inject ApplicationContext chỉ để gọi publishEvent. ApplicationEventPublisher là abstraction hẹp hơn và thể hiện đúng ý định của bean.

Tránh dùng static ApplicationContext holder hoặc gọi ApplicationContextAware chỉ để lấy publisher toàn cục. Những cách đó làm dependency ẩn và khiến việc kiểm thử, thay đổi cấu hình khó hơn.

## 9. Đồng bộ, bất đồng bộ và lỗi listener

Mặc định, application event được dispatch đồng bộ. Listener chạy trên luồng phát event:

- Publisher chờ listener đồng bộ hoàn tất.
- Listener chạy lâu làm lời gọi publishEvent lâu hơn.
- Exception từ listener đồng bộ có thể truyền ngược về publisher và ảnh hưởng luồng đang gọi.

Nếu tác vụ không cần hoàn tất ngay, có thể dùng @Async trên listener và bật @EnableAsync:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

~~~java
@Component
public class ImportEventListener {

    @Async
    @EventListener
    public void processImportCompleted(ImportCompletedEvent event) {
        System.out.println(
                "Background processing for " + event.batchId()
        );
    }
}
~~~

Với listener bất đồng bộ, publisher không chờ tác vụ hoàn tất. Thứ tự hoàn thành không được bảo đảm và exception không truyền ngược về publisher theo cách của listener đồng bộ. Cần cấu hình executor, giám sát lỗi và tránh chia sẻ trạng thái mutable giữa các luồng.

Nếu nhiều listener cần chạy sau khi transaction commit, hãy cân nhắc @TransactionalEventListener với phase phù hợp. Ví dụ, AFTER_COMMIT chỉ xử lý sau khi transaction thành công; listener cần có transaction tương ứng. Application event thông thường không tự bảo đảm dữ liệu đã commit trước khi listener chạy.

## 10. Chọn nơi phát event

| Tình huống | Nơi phát event phù hợp |
|---|---|
| Đơn hàng được tạo sau khi service hoàn tất nghiệp vụ | Service phát OrderPlacedEvent. |
| Thanh toán được xác nhận trong nghiệp vụ | PaymentService phát PaymentCompletedEvent. |
| Component import hoàn tất batch và sở hữu thông tin batch | Component phát ImportCompletedEvent. |
| Helper chỉ thực hiện một bước nhỏ trong service | Thường để service phát event sau khi hoàn tất hành động tổng thể. |
| Cần thông báo cho ứng dụng hoặc service khác | Dùng message broker hoặc cơ chế messaging liên tiến trình. |

Nên phát event tại nơi biết rõ sự việc đã xảy ra và có đủ dữ liệu để mô tả sự việc. Không nên để nhiều lớp cùng phát một event cho cùng một hành động, vì listener có thể xử lý trùng.

Event nên có ý nghĩa nghiệp vụ hoặc kỹ thuật rõ ràng. Tránh phát event quá chung chung như SomethingChangedEvent nếu listener không thể hiểu chính xác điều gì đã thay đổi.

## 11. Giới hạn của application event

Application event được dispatch trong cơ chế event của Spring ApplicationContext. Nó hữu ích để giảm phụ thuộc giữa các bean trong cùng ứng dụng, nhưng không thay thế message broker.

Cần lưu ý:

- Event không tự được lưu bền vững để phát lại khi ứng dụng khởi động lại.
- Event không tự gửi sang một JVM hoặc service khác.
- Publisher không tự nhận được kết quả nghiệp vụ từ listener.
- Listener đồng bộ có thể ảnh hưởng trực tiếp đến thời gian và kết quả lời gọi publisher.
- Listener bất đồng bộ cần chính sách quản lý thread và lỗi riêng.

Nếu cần truyền thông điệp đáng tin cậy giữa nhiều service, hãy dùng giải pháp messaging phù hợp. Nếu cần bảo đảm event được gửi khi transaction dữ liệu commit, hãy tìm hiểu transactional outbox hoặc cơ chế tương đương thay vì giả định publishEvent là durable.

## 12. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không inject được publisher | Bean không do Spring quản lý hoặc constructor khai báo sai dependency. | Đảm bảo bean có @Service/@Component hoặc được khai báo bằng @Bean. |
| Listener không nhận event | Listener chưa được đăng ký hoặc kiểu tham số không phù hợp. | Kiểm tra component scan và kiểu event trong phương thức @EventListener. |
| Phát event từ component nhưng không có listener | Component và listener không nằm trong cùng phạm vi ApplicationContext phù hợp hoặc listener chưa được đăng ký. | Kiểm tra cấu hình context và bean registration. |
| Listener chạy trước khi nghiệp vụ hoàn tất | Publisher phát event quá sớm. | Phát event sau bước nghiệp vụ cần thiết hoặc dùng @TransactionalEventListener. |
| Listener xử lý trùng | Nhiều nơi phát cùng event cho một hành động. | Chọn một điểm phát event rõ ràng và kiểm soát idempotency khi cần. |
| Publisher bị chậm | Listener đồng bộ thực hiện tác vụ dài. | Tối ưu listener hoặc cân nhắc @Async nếu nghiệp vụ cho phép. |
| Mong event được gửi sang service khác | Nhầm application event với message broker. | Dùng cơ chế messaging liên tiến trình. |
| Dữ liệu listener đọc không ổn định | Payload chứa collection hoặc object mutable bị sửa sau khi publish. | Dùng record và defensive copy để tạo snapshot bất biến. |

## 13. Tự kiểm tra

1. Vì sao cả @Service và @Component đều có thể inject ApplicationEventPublisher?
2. Khi phát OrderPlacedEvent, vì sao OrderService không cần biết ApplicationEventListeners?
3. Nếu một component không được Spring quản lý mà tự tạo bằng new, nó có thể được inject publisher tự động không?
4. Vì sao nên phát event sau khi hành động nghiệp vụ đã hoàn tất?
5. publishEvent mặc định có chờ listener xử lý xong không?
6. Khi nào nên dùng @TransactionalEventListener?
7. ApplicationEventPublisher có thể thay thế message broker để gửi event sang service khác không?
8. Vì sao chỉ nên chọn một điểm phát event cho một sự việc cụ thể?

**Kết quả cần nắm:** Bất kỳ bean Spring nào, bao gồm @Service và @Component, đều có thể inject ApplicationEventPublisher và phát event. Bean chỉ mô tả sự việc bằng event object; Spring dispatch đến listener phù hợp trong ApplicationContext. Hãy phát event tại đúng ranh giới nghiệp vụ, dùng constructor injection và chọn đồng bộ, bất đồng bộ hoặc transactional listener theo yêu cầu thực tế.
