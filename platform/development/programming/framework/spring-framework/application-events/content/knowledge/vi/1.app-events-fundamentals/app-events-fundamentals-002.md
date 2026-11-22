# Giao tiếp giữa các bean trong cùng ApplicationContext bằng Application Events

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao các bean trong Spring cần giao tiếp qua application event.
- Tạo một event mang dữ liệu nghiệp vụ bằng Java record.
- Phát event bằng ApplicationEventPublisher.
- Đăng ký bean lắng nghe bằng @EventListener.
- Mô tả thứ tự xử lý mặc định, cách sắp xếp listener và trường hợp cần xử lý bất đồng bộ.
- Nhận biết khi nào nên dùng event và khi nào nên gọi trực tiếp một phương thức.

## 1. Application Events giải quyết vấn đề gì?

Giả sử PaymentService xác nhận một khoản thanh toán. Sau khi thanh toán thành công, hệ thống cần gửi biên nhận, ghi lịch sử kiểm toán và cập nhật thống kê.

Nếu PaymentService gọi trực tiếp ReceiptService, AuditService và StatisticsService, nó phải biết tên và phụ thuộc vào tất cả các bean đó. Khi thêm một tác vụ mới, bạn lại phải sửa PaymentService. Các thành phần vì thế bị liên kết chặt chẽ.

Application Events cung cấp cách giao tiếp theo mô hình phát hành và đăng ký nhận sự kiện:

- Bean phát sự kiện chỉ cần biết rằng một sự kiện đã xảy ra.
- Các bean quan tâm tự đăng ký listener để nhận sự kiện đó.
- Một sự kiện có thể được nhiều listener trong cùng ApplicationContext xử lý.
- Bean phát sự kiện không cần gọi trực tiếp từng listener.

Ví dụ, PaymentService phát PaymentCompletedEvent. ReceiptListener và AuditListener có thể cùng nhận event này mà PaymentService không cần biết hai listener tồn tại.

Cách làm này phù hợp khi một hành động cần thông báo cho nhiều phần khác của ứng dụng. Nếu cần gọi một thao tác cụ thể và nhận kết quả ngay, gọi phương thức trực tiếp thường dễ hiểu hơn.

## 2. Các thành phần chính

| Thành phần | Vai trò |
|---|---|
| Event | Đối tượng mô tả một sự việc đã xảy ra và mang dữ liệu cần thiết cho listener. |
| Publisher | Bean phát event thông qua ApplicationEventPublisher. |
| Listener | Bean Spring có phương thức được đánh dấu @EventListener để nhận event phù hợp. |
| ApplicationContext | Quản lý các bean và điều phối event đến những listener đã đăng ký trong context đó. |

ApplicationContext triển khai ApplicationEventPublisher. Khi inject ApplicationEventPublisher vào một bean, bạn đang dùng giao diện chuyên biệt để phát event mà không phải phụ thuộc trực tiếp vào lớp ApplicationContext cụ thể.

Event có thể là một đối tượng Java thông thường. Từ Spring Framework 4.2, bạn không cần kế thừa ApplicationEvent cho event tùy chỉnh mới. Dùng record là lựa chọn gọn và giúp dữ liệu event bất biến.

## 3. Luồng xử lý trong cùng ApplicationContext

1. Spring khởi tạo PaymentService và ReceiptListener như các bean được quản lý trong cùng ApplicationContext.
2. Spring inject ApplicationEventPublisher vào PaymentService.
3. Khi thanh toán hoàn tất, PaymentService tạo PaymentCompletedEvent và gọi publishEvent.
4. ApplicationContext chuyển event đến các listener có kiểu tham số phù hợp.
5. ReceiptListener nhận event, đọc dữ liệu và thực hiện gửi biên nhận.
6. Sau khi listener đồng bộ hoàn tất, lời gọi publishEvent trả quyền điều khiển về PaymentService.

Điểm quan trọng là publisher chỉ phát event. Listener quyết định phải làm gì khi nhận event. Event nên biểu diễn một sự việc đã xảy ra, thường được đặt tên ở dạng quá khứ như PaymentCompletedEvent, OrderCreatedEvent hoặc UserRegisteredEvent.

## 4. Ví dụ hoàn chỉnh với Java 17 và Spring Boot

Ví dụ tạo một ứng dụng nhỏ: PaymentService xác nhận thanh toán và phát event; ReceiptListener nhận event rồi in thông tin biên nhận. Cả hai bean được Spring quản lý trong cùng ApplicationContext.

### Cấu trúc thư mục

~~~text
application-events-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── events/
                        ├── ApplicationEventsDemoApplication.java
                        ├── PaymentCompletedEvent.java
                        ├── PaymentService.java
                        └── ReceiptListener.java
~~~

### 4.1. Khai báo dependency

Tạo file pom.xml tại thư mục gốc:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>application-events-demo</artifactId>
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

### 4.2. Tạo lớp event

File PaymentCompletedEvent.java:

~~~java
package com.example.events;

import java.math.BigDecimal;

public record PaymentCompletedEvent(
        String paymentId,
        BigDecimal amount
) {
}
~~~

Record này mang mã thanh toán và số tiền đã thanh toán. Vì record có các thành phần dữ liệu bất biến, listener có thể đọc thông tin mà không cần lo một bean khác sửa trực tiếp các trường của event.

### 4.3. Phát event từ PaymentService

File PaymentService.java:

~~~java
package com.example.events;

import java.math.BigDecimal;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final ApplicationEventPublisher eventPublisher;

    public PaymentService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void completePayment(String paymentId, BigDecimal amount) {
        System.out.println(
                "1. PaymentService: xác nhận thanh toán " + paymentId
        );

        eventPublisher.publishEvent(
                new PaymentCompletedEvent(paymentId, amount)
        );

        System.out.println(
                "3. PaymentService: tiếp tục sau khi phát event"
        );
    }
}
~~~

PaymentService chỉ phụ thuộc vào ApplicationEventPublisher. Nó không inject ReceiptListener và không cần biết listener nào sẽ xử lý event.

Lời gọi publishEvent nhận một đối tượng event. Trong ví dụ này, đối tượng được tạo từ record PaymentCompletedEvent.

### 4.4. Nhận event bằng @EventListener

File ReceiptListener.java:

~~~java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReceiptListener {

    @EventListener
    public void onPaymentCompleted(PaymentCompletedEvent event) {
        System.out.println(
                "2. ReceiptListener: gửi biên nhận cho "
                        + event.paymentId()
                        + ", số tiền "
                        + event.amount()
        );
    }
}
~~~

Spring nhận biết phương thức onPaymentCompleted là listener nhờ @EventListener. Kiểu tham số PaymentCompletedEvent cho Spring biết phương thức này quan tâm đến event nào.

ReceiptListener phải là bean được Spring quản lý và phải được đăng ký trong ApplicationContext đang nhận event. Đặt @EventListener trên một đối tượng được tạo thủ công bằng từ khóa new sẽ không tự đăng ký đối tượng đó với Spring.

### 4.5. Khởi chạy ứng dụng

File ApplicationEventsDemoApplication.java:

~~~java
package com.example.events;

import java.math.BigDecimal;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApplicationEventsDemoApplication
        implements CommandLineRunner {

    private final PaymentService paymentService;

    public ApplicationEventsDemoApplication(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    public static void main(String[] args) {
        SpringApplication.run(
                ApplicationEventsDemoApplication.class,
                args
        );
    }

    @Override
    public void run(String... args) {
        paymentService.completePayment(
                "PAY-001",
                new BigDecimal("250000")
        );
    }
}
~~~

Chạy ứng dụng từ thư mục có pom.xml:

~~~bash
mvn spring-boot:run
~~~

Các dòng do ứng dụng in ra, bỏ qua log khởi động của Spring Boot:

~~~text
1. PaymentService: xác nhận thanh toán PAY-001
2. ReceiptListener: gửi biên nhận cho PAY-001, số tiền 250000
3. PaymentService: tiếp tục sau khi phát event
~~~

Dòng số 2 xuất hiện trước dòng số 3 vì listener mặc định chạy đồng bộ. Khi publishEvent được gọi, Spring gọi listener trên luồng đang phát event. Lời gọi publishEvent chỉ tiếp tục sau khi listener đồng bộ xử lý xong.

## 5. Một event có thể có nhiều listener

Nhiều bean có thể lắng nghe cùng một kiểu event. Ví dụ, sau khi thanh toán hoàn tất, ngoài ReceiptListener còn có AuditListener để ghi lịch sử:

~~~java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
public class AuditListener {

    @EventListener
    @Order(1)
    public void recordPayment(PaymentCompletedEvent event) {
        System.out.println(
                "Audit: đã ghi nhận thanh toán " + event.paymentId()
        );
    }
}
~~~

Khi PaymentCompletedEvent được phát, cả ReceiptListener và AuditListener đều có thể nhận event. Publisher không phải thêm lời gọi mới khi có listener mới.

Nếu cần xác định thứ tự giữa nhiều listener cùng xử lý một event, dùng @Order. Giá trị order nhỏ hơn được ưu tiên chạy trước. Nếu không khai báo thứ tự, không nên dựa vào thứ tự đăng ký bean để quyết định nghiệp vụ.

## 6. Đồng bộ và bất đồng bộ

### Mặc định: đồng bộ

Với cấu hình mặc định, listener chạy trên luồng phát event. Điều này có nghĩa:

- Publisher chờ listener xử lý xong rồi mới tiếp tục.
- Listener có thể đọc dữ liệu trong cùng luồng thực thi.
- Listener chạy lâu sẽ làm chậm thao tác phát event.
- Lỗi phát sinh từ listener đồng bộ có thể truyền ngược về nơi gọi publishEvent.

Cách này phù hợp với tác vụ ngắn, cần hoàn tất ngay trong luồng xử lý hiện tại.

### Khi cần bất đồng bộ

Có thể đánh dấu listener bằng @Async và bật xử lý bất đồng bộ bằng @EnableAsync:

~~~java
package com.example.events;

import org.springframework.scheduling.annotation.Async;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class AsyncAuditListener {

    @Async
    @EventListener
    public void recordPayment(PaymentCompletedEvent event) {
        System.out.println(
                "Xử lý audit bất đồng bộ cho " + event.paymentId()
        );
    }
}
~~~

Thêm @EnableAsync vào lớp cấu hình hoặc lớp ứng dụng có @SpringBootApplication:

~~~java
@EnableAsync
@SpringBootApplication
public class ApplicationEventsDemoApplication {
    // Phần khởi chạy ứng dụng
}
~~~

Khi listener chạy bất đồng bộ, publisher không chờ listener hoàn tất. Thứ tự hoàn thành giữa các listener bất đồng bộ không được bảo đảm. Cần chú ý quản lý thread pool, dữ liệu dùng chung và xử lý ngoại lệ trong tác vụ nền.

Không nên bật bất đồng bộ chỉ để làm cho event có vẻ nhanh hơn. Hãy dùng khi nghiệp vụ cho phép listener hoàn tất sau và publisher không cần kết quả ngay.

## 7. Chọn Application Event hay gọi phương thức trực tiếp?

| Nhu cầu | Cách phù hợp |
|---|---|
| Một bean cần gọi một thao tác cụ thể và dùng kết quả trả về | Gọi phương thức trực tiếp qua dependency injection. |
| Một hành động cần thông báo cho nhiều bean độc lập | Phát application event. |
| Publisher cần biết listener đã xử lý thành công hay trả về dữ liệu | Dùng lời gọi trực tiếp hoặc một API có kết quả rõ ràng. |
| Xử lý tác vụ nền trong cùng ứng dụng | Có thể kết hợp event với @Async nếu chấp nhận xử lý bất đồng bộ. |
| Gửi thông điệp sang service hoặc tiến trình khác | Dùng cơ chế messaging phù hợp như message broker; application event trong context không tự trở thành thông điệp liên tiến trình. |

Application Events là cơ chế giao tiếp trong bộ nhớ của ứng dụng Spring. Event không tự được lưu bền vững và không tự được gửi sang một JVM hay service khác. Nếu ứng dụng dừng trước khi listener xử lý xong, cơ chế này không cung cấp hàng đợi để phát lại event.

## 8. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Listener không chạy | Listener chưa được đăng ký thành bean hoặc nằm ngoài phạm vi component scan. | Đảm bảo listener có @Component hoặc được khai báo bằng @Bean trong đúng ApplicationContext. |
| Listener không nhận event | Kiểu tham số listener không phù hợp với kiểu event được phát. | Kiểm tra lớp event trong publishEvent và kiểu tham số của phương thức @EventListener. |
| Publisher không phát hiện listener | Tự tạo publisher hoặc listener bằng new thay vì để Spring quản lý. | Dùng constructor injection và để Spring tạo các bean. |
| Phương thức publishEvent chạy lâu | Listener đồng bộ thực hiện I/O hoặc công việc nặng. | Tối ưu listener hoặc cân nhắc @Async khi nghiệp vụ cho phép. |
| Lỗi trong listener làm thao tác phát event thất bại | Listener đồng bộ ném exception và lỗi truyền về publisher. | Xác định chính sách xử lý lỗi, ghi log và xử lý ngoại lệ phù hợp với nghiệp vụ. |
| Kết quả xử lý bất đồng bộ không theo thứ tự mong muốn | Các listener chạy trên những luồng khác nhau. | Không phụ thuộc thứ tự hoàn thành; dùng cơ chế tuần tự hóa hoặc điều phối riêng nếu nghiệp vụ bắt buộc. |

## 9. Nguyên tắc thiết kế event

- Đặt tên event theo sự việc đã xảy ra, ví dụ PaymentCompletedEvent.
- Chỉ đưa dữ liệu listener thực sự cần vào event; thường ưu tiên mã định danh và một bản dữ liệu bất biến.
- Dùng record hoặc lớp chỉ có getter để hạn chế thay đổi dữ liệu sau khi phát.
- Giữ publisher độc lập với các listener; không biến event thành cách gọi hàm vòng vo.
- Không dùng application event thay cho API request-response khi publisher cần kết quả ngay.
- Với listener cần chạy sau khi transaction commit, cân nhắc @TransactionalEventListener và chọn phase phù hợp. Listener này cần ngữ cảnh transaction tương ứng; nó không thay thế việc hiểu rõ vòng đời transaction.
- Nếu cần giao tiếp đáng tin cậy giữa nhiều tiến trình, hãy chọn message broker hoặc cơ chế lưu trữ và truyền thông điệp có độ bền phù hợp.

## 10. Tự kiểm tra

1. Vì sao PaymentService chỉ inject ApplicationEventPublisher thay vì inject ReceiptListener?
2. Nếu có thêm AuditListener nhận PaymentCompletedEvent, PaymentService có cần thay đổi không? Vì sao?
3. Vì sao dòng log của ReceiptListener xuất hiện trước dòng log số 3 trong ví dụ đồng bộ?
4. Khi nào @Async hữu ích và điều gì thay đổi về thứ tự hoàn thành?
5. Vì sao application event trong cùng ApplicationContext không phù hợp để gửi thông điệp sang một service chạy ở tiến trình khác?

**Kết quả cần nắm:** Bean phát event mô tả một sự việc bằng một đối tượng event và gửi qua ApplicationEventPublisher. Các bean listener trong cùng ApplicationContext nhận event bằng @EventListener. Cơ chế mặc định là đồng bộ; có thể mở rộng sang bất đồng bộ khi nghiệp vụ cho phép.
