# Application Events là gì và giải quyết vấn đề nào?

## Mục tiêu

Sau bài này, bạn có thể giải thích Application Events trong Spring là gì, mô tả cách một sự kiện đi từ nơi phát đến các listener, nhận biết vấn đề phụ thuộc chặt chẽ mà cơ chế này giúp giảm bớt, và chọn đúng trường hợp dùng event thay cho lời gọi phương thức trực tiếp.

## 1. Application Events là gì?

**Application Event** là một thông báo cho biết một việc đã xảy ra bên trong ứng dụng. Thành phần phát sự kiện mô tả sự việc đó rồi gửi event qua cơ chế của Spring. Những thành phần quan tâm đăng ký listener để nhận và xử lý event.

Ví dụ, sau khi một đơn hàng được tạo thành công, ứng dụng có thể phát sự kiện **OrderPlaced**. Các thành phần khác có thể lắng nghe sự kiện này để gửi email xác nhận, ghi nhật ký kiểm toán hoặc cập nhật một màn hình thống kê.

Spring cung cấp cơ chế này ở cấp **ApplicationContext**. Có thể hình dung ApplicationContext như một bộ phân phối sự kiện trong phạm vi ứng dụng: publisher phát một event, Spring tìm các listener phù hợp và gọi chúng.

Một event thường biểu diễn **sự thật đã xảy ra**, chẳng hạn OrderPlaced, PaymentReceived hoặc UserRegistered. Nó không nên mang ý nghĩa yêu cầu một thành phần khác thực hiện lệnh. Tên event vì vậy thường dùng dạng quá khứ hoặc mô tả trạng thái đã hình thành.

### Các vai trò chính

- **Publisher**: thành phần phát event. Nó biết sự việc đã xảy ra và công bố dữ liệu cần thiết, nhưng không cần biết có bao nhiêu listener hoặc listener nằm ở đâu.
- **Event**: đối tượng mang thông tin về sự việc. Ví dụ, OrderPlaced có thể chứa mã đơn hàng và tổng tiền.
- **Listener**: thành phần đăng ký nhận một loại event và thực hiện phản ứng tương ứng.
- **ApplicationContext**: môi trường Spring quản lý việc phân phối event đến các listener đã đăng ký.

Publisher và listener có thể là các bean khác nhau trong cùng ứng dụng. Publisher không cần gọi trực tiếp từng listener.

## 2. Application Events giải quyết vấn đề nào?

Hãy xét một dịch vụ tạo đơn hàng. Sau khi lưu đơn hàng, hệ thống cần gửi email, ghi audit và cập nhật số liệu báo cáo.

Nếu gọi trực tiếp từng thành phần, dịch vụ tạo đơn hàng phải biết các lớp gửi email, audit và báo cáo. Khi thêm một tác vụ mới, chẳng hạn gửi thông báo cho bộ phận kho, ta lại phải sửa dịch vụ tạo đơn hàng và có thể phải thêm dependency mới. Thành phần nghiệp vụ dần biết quá nhiều chi tiết không thuộc trách nhiệm chính của nó.

Application Events giúp giảm sự phụ thuộc đó:

1. Dịch vụ tạo đơn hàng hoàn thành nghiệp vụ chính và phát OrderPlaced.
2. Spring phân phối event đến mọi listener phù hợp.
3. Listener email xử lý thông báo; listener audit ghi nhận lịch sử; listener báo cáo cập nhật dữ liệu của nó.
4. Khi cần thêm một phản ứng mới, ta có thể bổ sung listener mà không phải thêm lời gọi trực tiếp vào publisher.

Nhờ vậy, cơ chế event hỗ trợ:

- **Giảm phụ thuộc giữa các thành phần**: publisher chỉ phụ thuộc vào hợp đồng phát event, không phụ thuộc vào các lớp xử lý cụ thể.
- **Tách trách nhiệm**: dịch vụ nghiệp vụ tập trung vào việc tạo đơn hàng; mỗi listener phụ trách một phản ứng riêng.
- **Mở rộng dễ hơn**: có thể thêm hoặc bỏ listener mà không phải viết lại luồng phát event.
- **Cho phép nhiều bên cùng phản ứng**: một sự kiện có thể được nhiều listener xử lý độc lập theo trách nhiệm của chúng.

Đây là sự tách rời ở mức mã nguồn và cấu trúc bên trong ứng dụng. Bản thân Application Events không biến các bean thành những dịch vụ độc lập và cũng không tự tạo ra một hệ thống message broker phân tán.

## 3. Event được phát và xử lý như thế nào?

Luồng cơ bản diễn ra theo thứ tự sau:

1. Một bean thực hiện nghiệp vụ, ví dụ tạo đơn hàng.
2. Khi đã có sự kiện cần thông báo, bean gọi publishEvent và truyền đối tượng event.
3. ApplicationContext chuyển event đến cơ chế phân phối của Spring.
4. Spring xác định các listener có kiểu event tương thích.
5. Các listener được gọi để thực hiện phần việc của mình.

Trong cách cấu hình mặc định, Spring sử dụng bộ phân phối đồng bộ. Listener chạy ngay trong luồng gọi publishEvent. Vì vậy, lời gọi phát event thường chỉ hoàn tất sau khi các listener đồng bộ xử lý xong.

Điều này có một hệ quả quan trọng: Application Events giúp tách phụ thuộc giữa các bean, nhưng **không mặc nhiên tách thời gian thực thi**. Một listener chậm vẫn có thể làm chậm luồng nghiệp vụ đang phát event. Lỗi từ listener đồng bộ cũng có thể ảnh hưởng đến luồng phát event, tùy cách cấu hình xử lý lỗi.

Nếu cần chạy listener bất đồng bộ, có thể kết hợp @Async với @EnableAsync. Khi đó listener chạy trên executor và cần chú ý đến quản lý thread, thứ tự xử lý, lỗi và dữ liệu dùng chung. Không nên giả định rằng thêm @Async sẽ tự tạo ra cơ chế lưu trữ, retry hoặc bảo đảm giao nhận.

## 4. Những API Spring thường dùng

### ApplicationEventPublisher

ApplicationEventPublisher là hợp đồng để phát event. Có thể inject nó vào bean cần công bố sự kiện:

~~~java
private final ApplicationEventPublisher eventPublisher;

public OrderService(ApplicationEventPublisher eventPublisher) {
    this.eventPublisher = eventPublisher;
}
~~~

Sau khi nghiệp vụ tạo đơn hàng thành công, bean gọi:

~~~java
eventPublisher.publishEvent(new OrderPlaced(orderId, total));
~~~

ApplicationContext cũng triển khai ApplicationEventPublisher, nên trong ví dụ nhỏ có thể gọi context.publishEvent trực tiếp. Trong service, inject ApplicationEventPublisher thường thể hiện rõ hơn rằng service chỉ cần khả năng phát event, không cần phụ thuộc vào toàn bộ ApplicationContext.

### @EventListener

@EventListener đánh dấu một phương thức bean là listener. Kiểu tham số của phương thức cho Spring biết loại event mà phương thức muốn nhận:

~~~java
@EventListener
public void handle(OrderPlaced event) {
    // Xử lý đơn hàng vừa được tạo
}
~~~

Một bean có thể có nhiều phương thức listener. Nhiều bean cũng có thể lắng nghe cùng một loại event.

### ApplicationListener

ApplicationListener là cách đăng ký listener bằng interface:

~~~java
public class OrderAuditListener
        implements ApplicationListener<OrderPlacedEvent> {

    @Override
    public void onApplicationEvent(OrderPlacedEvent event) {
        // Ghi nhận sự kiện
    }
}
~~~

Cách này thường dùng với kiểu event kế thừa ApplicationEvent. Với event dạng đối tượng thông thường, @EventListener là cách khai báo gọn và trực quan.

### Event có bắt buộc kế thừa ApplicationEvent không?

Không. Trong Spring hiện đại, publishEvent nhận một Object. Ta có thể phát một đối tượng Java thông thường, chẳng hạn record OrderPlaced. Spring bọc payload đó trong PayloadApplicationEvent khi cần phân phối nội bộ; listener khai báo tham số theo kiểu payload vẫn có thể nhận trực tiếp đối tượng OrderPlaced.

Kế thừa ApplicationEvent vẫn là lựa chọn hợp lệ khi cần dùng kiểu event truyền thống hoặc cần mô hình kế thừa event rõ ràng. Với event nghiệp vụ mới, một record bất biến thường đơn giản và dễ đọc hơn.

## 5. Ví dụ chạy được với Java 17 và Spring Framework

Ví dụ dưới đây mô phỏng một đơn hàng được tạo. Hai listener độc lập cùng nhận OrderPlaced: một listener gửi xác nhận và một listener ghi audit.

### Cấu trúc tối thiểu

Tạo dự án Maven với hai tệp:

- pom.xml
- src/main/java/demo/ApplicationEventsDemo.java

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-events-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ApplicationEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### ApplicationEventsDemo.java

~~~java
package demo;

import java.math.BigDecimal;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Configuration
@ComponentScan(basePackageClasses = ApplicationEventsDemo.class)
public class ApplicationEventsDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             ApplicationEventsDemo.class)) {
            context.publishEvent(
                    new OrderPlaced("DH-1001", new BigDecimal("125000")));
        }
    }
}

record OrderPlaced(String orderId, BigDecimal total) {
}

@Component
class EmailConfirmationListener {

    @EventListener
    @Order(1)
    void sendConfirmation(OrderPlaced event) {
        System.out.println("Gửi xác nhận cho đơn " + event.orderId());
    }
}

@Component
class AuditListener {

    @EventListener
    @Order(2)
    void writeAudit(OrderPlaced event) {
        System.out.println(
                "Ghi audit cho đơn " + event.orderId()
                        + ", tổng tiền " + event.total().toPlainString());
    }
}
~~~

### Chạy chương trình

Tại thư mục chứa pom.xml, chạy:

~~~bash
mvn -q compile exec:java
~~~

Kết quả:

~~~text
Gửi xác nhận cho đơn DH-1001
Ghi audit cho đơn DH-1001, tổng tiền 125000
~~~

### Đọc ví dụ

- OrderPlaced là event dạng record. Các thành phần của record là final, nên dữ liệu event không bị thay đổi sau khi tạo theo cách thông thường.
- main tạo ApplicationContext và phát OrderPlaced bằng publishEvent.
- EmailConfirmationListener và AuditListener là hai bean độc lập. Cả hai đều khai báo @EventListener với tham số OrderPlaced.
- @Order(1) và @Order(2) chỉ định thứ tự listener để kết quả minh họa ổn định và dễ đối chiếu.
- Publisher không gọi trực tiếp hai listener. Nếu thêm một listener mới cho OrderPlaced, publisher không cần biết tên hoặc lớp của listener đó.

Ví dụ dùng ApplicationContext trực tiếp để tập trung vào cơ chế phát event. Trong ứng dụng thực tế, service thường nhận ApplicationEventPublisher qua constructor injection rồi gọi publishEvent sau khi nghiệp vụ tương ứng hoàn tất.

## 6. Khi nào nên dùng Application Events?

Nên cân nhắc Application Events khi:

- Một nghiệp vụ vừa xảy ra và nhiều thành phần có thể cần phản ứng với nó.
- Publisher không cần nhận kết quả trả về từ listener.
- Các phản ứng có trách nhiệm riêng, có thể bổ sung hoặc thay đổi tương đối độc lập.
- Muốn giữ cho service nghiệp vụ không phải biết danh sách các thành phần phụ trợ.

Ví dụ phù hợp gồm gửi thông báo sau khi người dùng đăng ký, ghi audit sau khi hồ sơ thay đổi, cập nhật chỉ số nội bộ sau khi đơn hàng được tạo, hoặc làm mới cache sau khi dữ liệu được cập nhật.

## 7. Khi nào không nên dùng event?

Không nên dùng event chỉ để thay thế mọi lời gọi phương thức.

Hãy gọi phương thức trực tiếp khi:

- Thành phần gọi cần kết quả trả về ngay.
- Công việc của thành phần được gọi là bước bắt buộc để hoàn tất nghiệp vụ.
- Luồng xử lý cần thể hiện rõ thứ tự và cách xử lý lỗi giữa các bước.
- Một lời gọi trực tiếp giúp mã nguồn dễ đọc hơn và không tạo phụ thuộc gây vấn đề.

Ví dụ, khi OrderService cần gọi PaymentService và phải biết thanh toán thành công hay thất bại trước khi xác nhận đơn, một API phương thức trả về kết quả thường phù hợp hơn một event thông báo chung.

Cũng cần phân biệt **event** với **command**. OrderPlaced nói rằng đơn hàng đã được tạo; PlaceOrder là yêu cầu tạo đơn hàng. Listener nên phản ứng với sự kiện đã xảy ra, thay vì biến event thành một lệnh ẩn khiến người đọc khó biết ai chịu trách nhiệm thực hiện nghiệp vụ.

## 8. Các giới hạn cần hiểu đúng

### Event trong ApplicationContext là event nội bộ

Application Events chủ yếu phục vụ giao tiếp giữa các bean trong cùng ứng dụng Spring. Cơ chế này không tự gửi event sang tiến trình khác, không cung cấp hàng đợi bền vững, không có lịch sử để phát lại và không tự retry khi listener thất bại.

Nếu cần giao tiếp giữa các dịch vụ hoặc cần lưu trữ và giao nhận thông điệp bền vững, hãy xem xét message broker như RabbitMQ hoặc Kafka cùng cơ chế tích hợp phù hợp.

### Event không mặc nhiên đợi transaction commit

Với listener đồng bộ thông thường, listener được gọi tại thời điểm publisher phát event. Nếu publisher nằm trong một transaction, listener có thể chạy trước khi transaction commit. Vì vậy, listener không nên mặc định rằng dữ liệu đã được commit và có thể đọc từ một transaction khác.

Khi chỉ muốn xử lý sau một giai đoạn transaction cụ thể, Spring cung cấp @TransactionalEventListener. Mặc định, listener này chạy ở phase AFTER_COMMIT. Nếu không có transaction đang hoạt động, listener không được gọi theo mặc định; chỉ bật fallbackExecution khi hành vi đó thực sự phù hợp.

Nếu cần bảo đảm event được lưu cùng dữ liệu nghiệp vụ và có thể gửi lại sau sự cố, cần thiết kế cơ chế bền vững như transactional outbox hoặc giải pháp tương đương. Chỉ gọi publishEvent không tạo ra bảo đảm đó.

### Listener đồng bộ ảnh hưởng đến thời gian và lỗi

Vì listener mặc định chạy trong luồng publisher, listener xử lý lâu sẽ làm tăng thời gian của lời gọi phát event. Exception từ listener cũng có thể truyền ngược và ảnh hưởng đến luồng phát event tùy cấu hình ErrorHandler.

Có thể cấu hình xử lý bất đồng bộ hoặc ErrorHandler theo nhu cầu, nhưng phải quyết định rõ cách quan sát lỗi, retry, thứ tự và tính nhất quán dữ liệu.

## 9. Thực hành tốt

- Đặt tên event theo sự việc đã xảy ra, ví dụ OrderPlaced hoặc PaymentReceived.
- Dùng payload nhỏ, rõ nghĩa và ưu tiên bất biến. Chỉ đưa dữ liệu listener thực sự cần, thường là định danh và các thông tin nghiệp vụ liên quan.
- Phát event tại thời điểm nghiệp vụ đã đạt trạng thái mà tên event khẳng định. Không phát OrderPlaced trước khi đơn hàng thực sự được tạo thành công.
- Giữ listener tập trung vào một trách nhiệm để dễ kiểm thử và thay đổi.
- Chỉ quy định thứ tự bằng @Order khi thứ tự có ý nghĩa thực sự; không nên để các listener phụ thuộc ngầm vào nhau.
- Với listener có tác dụng phụ, cân nhắc tính idempotent để việc xử lý lặp không tạo ra kết quả sai.
- Không đưa toàn bộ entity đang được quản lý hoặc đối tượng mutable dùng chung vào event nếu listener có thể vô tình thay đổi trạng thái của publisher.
- Không tạo chuỗi event vòng lặp khó theo dõi. Nếu một luồng nghiệp vụ có nhiều bước bắt buộc và cần điều phối rõ ràng, hãy thể hiện nó bằng service hoặc một cơ chế điều phối phù hợp.

## 10. Ghi nhớ

Application Events là cơ chế thông báo nội bộ của Spring. Publisher công bố một sự việc; listener đăng ký loại sự việc quan tâm và xử lý độc lập. Cách làm này giảm phụ thuộc trực tiếp, tách trách nhiệm và giúp thêm phản ứng mới dễ dàng hơn.

Mặc định, listener chạy đồng bộ trong luồng phát event. Application Events cũng không tự cung cấp lưu trữ bền vững, retry, giao tiếp liên tiến trình hoặc bảo đảm xử lý sau transaction commit. Hiểu các giới hạn này giúp chọn event đúng chỗ và tránh dùng nó thay cho lời gọi trực tiếp hay message broker.
