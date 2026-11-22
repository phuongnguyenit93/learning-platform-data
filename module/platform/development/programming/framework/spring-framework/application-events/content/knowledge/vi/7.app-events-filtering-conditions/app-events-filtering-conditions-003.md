# Lọc theo thuộc tính của event

## Mục tiêu

Sau bài này, bạn có thể phân biệt lọc event theo kiểu với lọc event theo dữ liệu bên trong, viết điều kiện SpEL bằng @EventListener(condition = "..."), truy cập payload và metadata của event, xử lý thuộc tính lồng nhau hoặc giá trị null an toàn, và kiểm chứng listener chỉ chạy khi event thỏa điều kiện.

## 1. Lọc event theo thuộc tính là gì?

Spring Application Events cho phép một publisher phát event và nhiều listener cùng quan tâm đến event đó. Thông thường, Spring chọn listener dựa trên kiểu event. Tuy nhiên, đôi khi nhiều event cùng kiểu nhưng listener chỉ cần xử lý một số event thỏa điều kiện nghiệp vụ.

Ví dụ, ứng dụng phát OrderPlaced cho mọi đơn hàng. Các listener có thể chỉ muốn nhận:

- Đơn hàng đến từ kênh WEB.
- Đơn hàng có tổng tiền từ 50.000 trở lên.
- Đơn hàng của khách VIP.
- Đơn hàng sử dụng mã khuyến mãi SPRING.
- Đơn hàng có nhãn priority.

Đây là **lọc theo thuộc tính của event**. Spring vẫn nhận event và xác định listener phù hợp theo kiểu trước. Sau đó, điều kiện runtime quyết định phương thức listener có được gọi hay không.

Với annotation-based listener, cách trực tiếp nhất là dùng thuộc tính condition của @EventListener. Giá trị condition là một biểu thức Spring Expression Language (SpEL).

~~~java
@EventListener(condition = "#a0.channel() == 'WEB'")
public void handleWebOrder(OrderPlaced event) {
    System.out.println("Web order: " + event.orderId());
}
~~~

Trong ví dụ này, listener chỉ chạy khi thuộc tính channel của payload có giá trị WEB.

## 2. Phân biệt lọc theo kiểu và lọc theo thuộc tính

Hai bước lọc giải quyết hai câu hỏi khác nhau:

| Cơ chế | Câu hỏi | Ví dụ |
|---|---|---|
| Kiểu event | Listener có nhận loại event này không? | Chỉ nhận OrderPlaced |
| Thuộc tính event | Event cụ thể này có thỏa điều kiện không? | Chỉ nhận OrderPlaced có channel = WEB |

Kiểu event thường được suy ra từ tham số phương thức:

~~~java
@EventListener
public void handleOrder(OrderPlaced event) {
    // Nhận OrderPlaced phù hợp
}
~~~

Nếu cần một listener xử lý nhiều kiểu event, có thể khai báo classes:

~~~java
@EventListener(classes = {
        OrderPlaced.class,
        OrderCancelled.class
})
public void handleOrderLifecycle() {
    System.out.println("Order lifecycle event");
}
~~~

Với nhiều kiểu event, nếu phương thức có tham số thì kiểu tham số phải là kiểu chung tương thích với các event được khai báo. Thuộc tính condition bổ sung bước lọc theo dữ liệu runtime sau khi kiểu event đã phù hợp.

Không nên dùng một biểu thức condition để thay thế việc khai báo đúng kiểu event. Chọn kiểu event rõ ràng giúp Spring loại các listener không liên quan ngay từ bước phân phối.

## 3. SpEL có thể truy cập những dữ liệu nào?

Spring đánh giá condition trong một evaluation context dành riêng cho event listener. Các biến quan trọng gồm:

| Biến | Ý nghĩa | Ví dụ |
|---|---|---|
| #root.event hoặc event | ApplicationEvent thực tế được đưa vào listener | #root.event |
| #root.args hoặc args | Mảng các tham số truyền vào phương thức listener | #root.args[0] |
| #a0, #p0 | Tham số thứ nhất, đánh số từ 0 | #a0.channel() |
| #a1, #p1 | Tham số thứ hai | #a1 |
| #tenThamSo | Tham số theo tên nếu tên được giữ trong bytecode | #order.channel() |

Với phương thức nhận một payload:

~~~java
@EventListener(condition = "#a0.channel() == 'WEB'")
public void handle(OrderPlaced order) {
    // ...
}
~~~

#a0 tham chiếu đối tượng OrderPlaced được truyền vào phương thức. Cách dùng chỉ số #a0 không phụ thuộc vào việc compiler có giữ tên tham số hay không.

Nếu muốn dùng tên như #order, hãy bật tùy chọn compiler -parameters để tên tham số có trong bytecode. Nếu không, Spring có thể không phân giải được tên đó.

### Phân biệt #a0 với #root.event

Khi publisher phát một object thông thường, Spring có thể bọc object đó trong PayloadApplicationEvent. Trong trường hợp này:

- #a0 tham chiếu payload mà phương thức listener nhận.
- #root.event tham chiếu ApplicationEvent thực tế, có thể là PayloadApplicationEvent chứa payload.

Nếu listener nhận một lớp tự định nghĩa kế thừa ApplicationEvent, #a0 thường là chính instance event đó. Dùng #a0 khi mục tiêu là đọc thuộc tính của tham số listener; dùng #root.event khi cần truy cập metadata của ApplicationEvent.

## 4. Viết điều kiện trên thuộc tính đơn giản

SpEL hỗ trợ các phép so sánh và toán tử logic thông dụng. Ví dụ:

~~~java
@EventListener(condition = "#a0.channel() == 'WEB'")
public void handleWeb(OrderPlaced event) {
}

@EventListener(condition = "#a0.total() >= 50000")
public void handleHighValue(OrderPlaced event) {
}

@EventListener(condition = "#a0.vip() == true")
public void handleVip(OrderPlaced event) {
}
~~~

Một số dạng điều kiện thường dùng:

~~~java
// So sánh bằng
@EventListener(condition = "#a0.channel() == 'WEB'")

// So sánh khác
@EventListener(condition = "#a0.channel() != 'STORE'")

// So sánh số
@EventListener(condition = "#a0.total() > 100000")

// Kết hợp AND
@EventListener(condition =
        "#a0.channel() == 'WEB' and #a0.total() >= 50000")

// Kết hợp OR
@EventListener(condition =
        "#a0.channel() == 'WEB' or #a0.vip()")
~~~

Nên ưu tiên biểu thức trả về boolean rõ ràng. Theo API Spring, listener được gọi khi biểu thức trả về true hoặc một trong các chuỗi "true", "on", "yes", "1". Condition mặc định là chuỗi rỗng, nghĩa là không lọc thêm và listener được xử lý mỗi khi kiểu event phù hợp.

## 5. Lọc thuộc tính lồng nhau, collection và giá trị null

Event thường chứa object lồng nhau hoặc collection. SpEL có thể truy cập các thành phần này qua accessor hoặc method của object.

### Thuộc tính lồng nhau

Ví dụ payload có thông tin khách hàng:

~~~java
record Customer(boolean vip) {
}

record OrderPlaced(String orderId, Customer customer) {
}
~~~

Có thể lọc đơn hàng của khách VIP:

~~~java
@EventListener(condition = "#a0.customer() != null and #a0.customer().vip()")
public void handleVipOrder(OrderPlaced event) {
    System.out.println("VIP: " + event.orderId());
}
~~~

Biểu thức kiểm tra customer khác null trước rồi mới đọc vip. Toán tử and của SpEL đánh giá có điều kiện, vì vậy vế sau không cần được đánh giá khi vế đầu là false.

### Collection

Nếu event chứa danh sách nhãn:

~~~java
record OrderPlaced(String orderId, Set<String> tags) {
}
~~~

Có thể lọc event có nhãn priority:

~~~java
@EventListener(condition =
        "#a0.tags() != null and #a0.tags().contains('priority')")
public void handlePriorityOrder(OrderPlaced event) {
    System.out.println("Priority: " + event.orderId());
}
~~~

### Giá trị có thể null

Luôn kiểm tra null trước khi truy cập thuộc tính hoặc gọi method trên một giá trị tùy chọn:

~~~java
@EventListener(condition =
        "#a0.couponCode() != null and #a0.couponCode() == 'SPRING'")
public void handleSpringCoupon(OrderPlaced event) {
    // ...
}
~~~

Nếu bỏ qua điều kiện null, biểu thức có thể phát sinh lỗi khi event không có couponCode. Với dữ liệu lồng nhau, hãy kiểm tra từng cấp có thể null trước khi truy cập cấp tiếp theo.

## 6. Điều kiện SpEL nên đơn giản và dễ kiểm tra

Condition được đánh giá trong lúc Spring quyết định có gọi listener hay không. Vì vậy, nên giữ biểu thức ngắn, xác định và ít tốn chi phí.

Nên dùng condition cho:

- So sánh giá trị của event.
- Kiểm tra trạng thái hoặc loại nghiệp vụ.
- Kết hợp một vài điều kiện boolean.
- Kiểm tra sự tồn tại của phần dữ liệu tùy chọn.
- Kiểm tra một nhãn hoặc giá trị trong collection nhỏ.

Tránh đưa vào condition:

- Gọi HTTP hoặc truy vấn database.
- Thay đổi trạng thái của object.
- Thực hiện nghiệp vụ có side effect.
- Duyệt collection lớn hoặc thực hiện phép tính tốn kém.
- Phụ thuộc vào thời gian hoặc trạng thái bên ngoài thay đổi liên tục.

Nếu điều kiện phức tạp, có nhiều nhánh hoặc cần truy vấn dữ liệu, hãy cân nhắc tính toán một thuộc tính rõ ràng trước khi publish event, hoặc dùng một listener nhận event rồi gọi service để xử lý nghiệp vụ. Điều này giúp điều kiện dễ đọc và dễ kiểm thử.

Event payload nên bất biến sau khi publish. Nếu publisher thay đổi object trong khi các listener đang xử lý, kết quả lọc có thể khó dự đoán, đặc biệt khi listener chạy bất đồng bộ.

## 7. Lọc trong @EventListener và tự lọc trong listener khác nhau thế nào?

Có thể tự viết điều kiện trong thân phương thức:

~~~java
@EventListener
public void handle(OrderPlaced event) {
    if (!"WEB".equals(event.channel())) {
        return;
    }

    System.out.println("Web order: " + event.orderId());
}
~~~

Cách này vẫn đúng. Tuy nhiên, listener được gọi cho mọi event cùng kiểu rồi mới tự kiểm tra điều kiện.

Dùng condition:

~~~java
@EventListener(condition = "#a0.channel() == 'WEB'")
public void handle(OrderPlaced event) {
    System.out.println("Web order: " + event.orderId());
}
~~~

Với condition, Spring quyết định có gọi phương thức hay không ngay trong cơ chế xử lý event. Phương thức chỉ chứa logic dành cho event đã thỏa điều kiện.

| Tiêu chí | condition | if trong method |
|---|---|---|
| Thời điểm lọc | Trước khi gọi method listener | Sau khi method đã được gọi |
| Khai báo | SpEL trong annotation | Java code |
| Phù hợp | Điều kiện ngắn, đọc được ngay trên listener | Logic nhiều bước hoặc cần gọi service |
| Debug | Cần kiểm tra biểu thức SpEL | Có thể đặt breakpoint trong Java |
| Kiểm thử | Kiểm tra điều kiện và việc method có được gọi | Kiểm tra nhánh xử lý trong method |

Với ApplicationListener triển khai interface, có thể dùng if trong onApplicationEvent(). Annotation condition là lựa chọn thuận tiện cho phương thức @EventListener.

## 8. Ví dụ hoàn chỉnh với Java 17 và Spring Framework 6.2.12

Ví dụ phát hai event OrderPlaced có cùng kiểu nhưng dữ liệu khác nhau. Event thứ nhất là đơn hàng WEB giá trị cao của khách VIP, có mã SPRING và nhãn priority. Event thứ hai là đơn hàng tại cửa hàng với giá trị thấp.

Năm listener dùng condition để lọc từng thuộc tính. Event thứ hai vẫn được publish, nhưng không listener nào trong ví dụ được gọi cho nó.

### Cấu trúc dự án

~~~text
event-property-filter-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── EventPropertyFilterDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>event-property-filter-demo</artifactId>
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
                    <mainClass>demo.EventPropertyFilterDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### EventPropertyFilterDemo.java

~~~java
package demo;

import java.util.Set;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class EventPropertyFilterDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            context.publishEvent(new OrderPlaced(
                    "DH-7701",
                    "WEB",
                    75_000,
                    new Customer(true),
                    "SPRING",
                    Set.of("priority", "gift")));

            context.publishEvent(new OrderPlaced(
                    "DH-7702",
                    "STORE",
                    20_000,
                    new Customer(false),
                    null,
                    Set.of("standard")));
        }
    }

    record Customer(boolean vip) {
    }

    record OrderPlaced(
            String orderId,
            String channel,
            long total,
            Customer customer,
            String couponCode,
            Set<String> tags) {
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {

        @Bean
        EventListeners eventListeners() {
            return new EventListeners();
        }
    }

    static class EventListeners {

        @EventListener(condition = "#a0.channel() == 'WEB'")
        @Order(1)
        public void handleWebOrder(OrderPlaced event) {
            System.out.println("WEB order: " + event.orderId());
        }

        @EventListener(
                condition = "#a0.channel() == 'WEB' and #a0.total() >= 50000")
        @Order(2)
        public void handleHighValueWebOrder(OrderPlaced event) {
            System.out.println("High-value web order: " + event.orderId());
        }

        @EventListener(
                condition = "#a0.customer() != null and #a0.customer().vip()")
        @Order(3)
        public void handleVipOrder(OrderPlaced event) {
            System.out.println("VIP order: " + event.orderId());
        }

        @EventListener(
                condition = "#a0.couponCode() != null and #a0.couponCode() == 'SPRING'")
        @Order(4)
        public void handleSpringCoupon(OrderPlaced event) {
            System.out.println("Spring coupon order: " + event.orderId());
        }

        @EventListener(
                condition = "#a0.tags() != null and #a0.tags().contains('priority')")
        @Order(5)
        public void handlePriorityOrder(OrderPlaced event) {
            System.out.println("Priority order: " + event.orderId());
        }
    }
}
~~~

### Chạy chương trình

Tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java
~~~

Kết quả:

~~~text
WEB order: DH-7701
High-value web order: DH-7701
VIP order: DH-7701
Spring coupon order: DH-7701
Priority order: DH-7701
~~~

Không có dòng nào được in cho DH-7702 vì event này có channel STORE, tổng tiền thấp, khách không phải VIP, coupon null và không có nhãn priority.

### Phân tích luồng chạy

1. AnnotationConfigApplicationContext khởi tạo AppConfig và đăng ký EventListeners thành bean.
2. EventListenerMethodProcessor phát hiện năm phương thức được đánh dấu @EventListener.
3. Publisher phát OrderPlaced có orderId DH-7701.
4. Spring xác định các listener nhận được kiểu OrderPlaced rồi đánh giá condition của từng listener.
5. Cả năm điều kiện đều trả về true cho DH-7701, nên năm phương thức được gọi theo thứ tự @Order.
6. Publisher phát DH-7702. Các condition tương ứng trả về false, nên những phương thức listener này không được gọi.
7. Context được đóng sau khi hai event đã được xử lý.

Điểm cần nhớ: condition không hủy event và cũng không ngăn listener khác xử lý event đó. Nó chỉ quyết định phương thức listener đang xét có được gọi hay không.

## 9. Kiểm thử bộ lọc event như thế nào?

Một bài kiểm thử tốt nên có ít nhất hai trường hợp:

- Event thỏa điều kiện và listener phải được gọi.
- Event không thỏa điều kiện và listener không được gọi.

Có thể kiểm thử bằng cách inject một listener recorder có bộ đếm hoặc danh sách event đã nhận. Sau đó publish từng event và kiểm tra kết quả.

Ví dụ kiểm tra bằng bộ đếm:

~~~java
AtomicInteger webOrderCount = new AtomicInteger();

@EventListener(condition = "#a0.channel() == 'WEB'")
public void handleWebOrder(OrderPlaced event) {
    webOrderCount.incrementAndGet();
}
~~~

Sau khi publish một event WEB và một event STORE, kết quả mong đợi là:

~~~java
assertEquals(1, webOrderCount.get());
~~~

Nên bổ sung các trường hợp biên:

- Thuộc tính tùy chọn là null.
- Số tiền đúng bằng ngưỡng.
- Collection rỗng hoặc null.
- Giá trị chuỗi viết hoa/thường khác nhau.
- Event có thuộc tính lồng nhau bị thiếu.
- Nhiều listener có condition độc lập cùng nhận một event.

Nếu dùng @Async, cần đợi listener hoàn tất trước khi kiểm tra bộ đếm. Với listener đồng bộ mặc định, có thể kiểm tra ngay sau khi publishEvent trả về.

## 10. Lỗi thường gặp

### Dùng tên tham số nhưng compiler không giữ parameter name

Condition #event.channel() có thể không phân giải được nếu tên tham số không có trong bytecode. Dùng #a0.channel() hoặc #p0.channel(), hoặc cấu hình compiler với -parameters.

### Nhầm #root.event với payload

Khi publisher phát một object thông thường, Spring có thể bọc nó trong PayloadApplicationEvent. #root.event tham chiếu ApplicationEvent wrapper, còn #a0 tham chiếu tham số payload mà method nhận. Chọn đúng đối tượng trước khi truy cập thuộc tính.

### Bỏ qua kiểm tra null

Truy cập #a0.couponCode().length() khi couponCode null có thể làm biểu thức lỗi. Kiểm tra null trước rồi mới truy cập hoặc gọi method.

### Viết condition quá phức tạp

Một biểu thức dài với nhiều phép gọi và nhánh làm listener khó đọc và khó debug. Tách nghiệp vụ phức tạp sang service hoặc tính toán thuộc tính cần lọc trước khi publish event.

### Nghĩ condition chặn toàn bộ event

Condition false chỉ ngăn phương thức listener tương ứng được gọi. Event vẫn được publish và các listener khác vẫn có thể xử lý nó.

### Dùng condition để thực hiện side effect

Condition nên chỉ trả lời event có phù hợp hay không. Không cập nhật database, gửi HTTP hoặc thay đổi dữ liệu trong biểu thức SpEL.

### Mong đợi listener async hoàn tất trước khi publishEvent trả về

Với listener dùng @Async, publisher không chờ công việc nền hoàn tất. Hãy thiết kế cách đồng bộ hóa và kiểm thử riêng cho xử lý async.

### Dùng condition thay cho kiểm soát bảo mật

Condition là bộ lọc xử lý event trong ứng dụng. Không dùng nó làm ranh giới bảo mật hoặc thay thế authorization ở tầng service/API.

## 11. Thực hành tốt

- Dùng kiểu event để chọn nhóm listener, rồi dùng condition để lọc thuộc tính runtime.
- Ưu tiên #a0 hoặc #p0 khi muốn tránh phụ thuộc tên tham số trong bytecode.
- Viết điều kiện trả về boolean rõ ràng.
- Kiểm tra null trước khi đọc thuộc tính lồng nhau hoặc gọi method.
- Giữ payload bất biến và chứa dữ liệu cần thiết cho listener.
- Giữ condition ngắn, nhanh và không có side effect.
- Dùng @Order nếu thứ tự gọi listener có ý nghĩa rõ ràng.
- Kiểm thử cả trường hợp khớp, không khớp và dữ liệu biên.
- Nếu điều kiện cần truy vấn database hoặc gọi hệ thống ngoài, chuyển phần đó sang service.
- Nếu cần lọc ở mức publisher để tránh tạo event không cần thiết, quyết định publish trong logic nghiệp vụ trước khi gọi publishEvent.

## 12. Ghi nhớ

Lọc theo thuộc tính của event là bước kiểm tra runtime bổ sung sau khi Spring đã xác định listener phù hợp theo kiểu event. Với @EventListener, thuộc tính condition nhận một biểu thức SpEL và chỉ gọi phương thức khi biểu thức trả về giá trị đúng.

Dùng #a0 hoặc #p0 để truy cập tham số đầu tiên, #root.args để truy cập mảng tham số và #root.event để truy cập ApplicationEvent. Có thể lọc theo chuỗi, số, thuộc tính lồng nhau, giá trị null và collection. Giữ biểu thức đơn giản, kiểm thử cả event khớp lẫn không khớp, và đặt nghiệp vụ phức tạp trong service để listener dễ hiểu.

## Tài liệu tham khảo chính thức

- [EventListener — Spring Framework 6.2.12 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html)
- [Additional Capabilities of the ApplicationContext — Spring Framework 6.2](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Expression Language (SpEL) — Spring Framework 6.2](https://docs.spring.io/spring-framework/reference/6.2/core/expressions.html)
- [EventListenerMethodProcessor — Spring Framework 6.2.12 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListenerMethodProcessor.html)
