# PayloadApplicationEvent và payload thực tế

## Mục tiêu

Sau bài này, bạn có thể giải thích vì sao Spring bọc một đối tượng thông thường thành PayloadApplicationEvent, phân biệt event wrapper với payload nghiệp vụ, chọn đúng kiểu tham số cho listener, đọc dữ liệu bằng getPayload(), và xử lý trường hợp payload có kiểu generic.

## 1. Payload và event wrapper là hai lớp ý nghĩa khác nhau

Khi phát một Application Event, ta cần phân biệt hai khái niệm:

- **Payload** là dữ liệu nghiệp vụ mà publisher muốn thông báo. Ví dụ: một đối tượng OrderPlaced chứa mã đơn hàng và tổng tiền.
- **Event wrapper** là đối tượng Spring dùng để đưa payload vào hệ thống Application Events. Wrapper chứa payload, nguồn phát và thông tin kiểu cần thiết cho việc phân phối.

Trong Spring Framework, lớp đảm nhiệm vai trò wrapper này là **PayloadApplicationEvent<T>**. Lớp nằm trong package org.springframework.context, kế thừa ApplicationEvent và triển khai ResolvableTypeProvider.

Tham số kiểu T mô tả kiểu dữ liệu bên trong wrapper. Ví dụ:

~~~java
PayloadApplicationEvent<OrderPlaced>
~~~

có nghĩa là event wrapper mang một payload kiểu OrderPlaced.

Không nên đồng nhất wrapper với payload. Wrapper là cấu trúc Spring dùng để phân phối; payload là nội dung mà listener thường quan tâm để thực hiện nghiệp vụ.

## 2. Spring tự bọc đối tượng thông thường khi publishEvent

ApplicationEventPublisher có phương thức:

~~~java
void publishEvent(Object event);
~~~

Khi đối tượng truyền vào đã là một ApplicationEvent, Spring phát chính event đó. Khi đối tượng truyền vào không phải ApplicationEvent, Spring bọc nó trong một PayloadApplicationEvent rồi mới phân phối đến các listener.

Ví dụ:

~~~java
OrderPlaced payload =
        new OrderPlaced("DH-2001", new BigDecimal("250000"));

eventPublisher.publishEvent(payload);
~~~

Publisher chỉ cần truyền đối tượng OrderPlaced. Không cần tự tạo PayloadApplicationEvent cho trường hợp thông thường.

Về mặt khái niệm, luồng xử lý tương đương với việc Spring tạo một wrapper mang payload đó:

~~~java
PayloadApplicationEvent<OrderPlaced> event =
        new PayloadApplicationEvent<>(source, payload);
~~~

Đây là cách minh họa cấu trúc dữ liệu, không phải lời gọi bắt buộc trong service. Khi dùng ApplicationEventPublisher.publishEvent(Object), Spring tự thực hiện bước bọc.

### Khi nào Spring không bọc?

Nếu đối tượng được phát đã kế thừa ApplicationEvent, Spring coi đó là một event hoàn chỉnh và phát chính đối tượng đó. Nó không bọc thêm một PayloadApplicationEvent bên ngoài.

Điều này tạo ra hai kiểu phổ biến:

| Đối tượng publisher truyền vào | Đối tượng được phân phối |
|---|---|
| Một record hoặc POJO thông thường | PayloadApplicationEvent<T> chứa đối tượng đó |
| Một lớp kế thừa ApplicationEvent | Chính đối tượng ApplicationEvent đó |

Vì vậy, khi thiết kế event, cần xác định rõ mình đang phát một event class hoàn chỉnh hay một payload thông thường.

## 3. Cấu trúc và dữ liệu của PayloadApplicationEvent

PayloadApplicationEvent<T> có ba phần cần quan tâm:

- **source**: đối tượng gắn với nguồn phát event. Khi ApplicationContext tự bọc payload qua publishEvent(Object), source thường là ApplicationContext đang phát event.
- **payload**: dữ liệu thực tế do publisher truyền vào.
- **payload type**: kiểu dữ liệu của payload, được biểu diễn thông qua ResolvableType để Spring có thể xác định listener phù hợp, kể cả trong một số trường hợp generic.

Các phương thức hữu ích:

| API | Ý nghĩa |
|---|---|
| getSource() | Lấy nguồn phát event, kế thừa từ EventObject |
| getPayload() | Lấy đối tượng payload bên trong |
| getResolvableType() | Lấy ResolvableType mô tả kiểu của event và payload |

Ví dụ đọc wrapper:

~~~java
void inspect(PayloadApplicationEvent<OrderPlaced> event) {
    Object source = event.getSource();
    OrderPlaced payload = event.getPayload();

    System.out.println(source.getClass().getSimpleName());
    System.out.println(payload.orderId());
}
~~~

getSource() và getPayload() phục vụ hai mục đích khác nhau. Không nên dùng source thay cho dữ liệu nghiệp vụ. Nếu listener cần mã đơn hàng, tổng tiền hoặc trạng thái đơn hàng, hãy đọc các trường từ payload.

PayloadApplicationEvent không tự sao chép sâu đối tượng payload. Wrapper giữ tham chiếu đến đối tượng được truyền vào. Nếu payload chứa collection hoặc đối tượng mutable, thay đổi dữ liệu sau khi phát event có thể làm listener nhìn thấy trạng thái đã thay đổi. Vì vậy, event payload nên được thiết kế bất biến hoặc không bị sửa sau khi publish.

## 4. Listener nhận payload trực tiếp hay nhận wrapper?

Spring hỗ trợ cả hai cách. Việc chọn kiểu tham số quyết định listener nhận dữ liệu nghiệp vụ hay nhận toàn bộ event wrapper.

### Cách 1: Nhận payload trực tiếp

Đây là cách phù hợp với phần lớn listener nghiệp vụ:

~~~java
@EventListener
public void handleOrderPlaced(OrderPlaced event) {
    System.out.println(event.orderId());
}
~~~

Mặc dù publisher đã truyền một đối tượng OrderPlaced và Spring đã bọc nó trong PayloadApplicationEvent, Spring có thể nhận diện kiểu payload để gọi phương thức listener bằng chính đối tượng OrderPlaced.

Listener không cần biết chi tiết wrapper. Điều này giúp mã xử lý tập trung vào dữ liệu nghiệp vụ.

### Cách 2: Nhận PayloadApplicationEvent

Nếu cần đọc source, kiểm tra wrapper hoặc làm việc với cấu trúc event ở cấp Spring, khai báo tham số theo kiểu wrapper:

~~~java
@EventListener
public void inspectOrderEvent(
        PayloadApplicationEvent<OrderPlaced> event) {

    OrderPlaced payload = event.getPayload();

    System.out.println(event.getClass().getSimpleName());
    System.out.println(event.getSource().getClass().getSimpleName());
    System.out.println(payload.orderId());
}
~~~

Trong cách này, listener nhận toàn bộ PayloadApplicationEvent<OrderPlaced>, không phải chỉ nhận OrderPlaced.

Spring xác định kiểu event thông qua ResolvableType và có thể đối chiếu kiểu payload với kiểu tham số listener. Vì vậy, listener nhận payload và listener nhận wrapper có thể cùng lắng nghe một lần publish.

### Chọn cách nào?

- Dùng tham số OrderPlaced khi listener chỉ cần xử lý dữ liệu nghiệp vụ.
- Dùng PayloadApplicationEvent<OrderPlaced> khi listener thực sự cần source, wrapper hoặc thông tin kiểu của event.
- Tránh nhận PayloadApplicationEvent<?> chỉ để rồi phải ép kiểu thủ công nếu listener chỉ xử lý một loại payload cụ thể.

Kiểu tham số cụ thể giúp Spring lọc event rõ ràng và giúp compiler kiểm tra kiểu dữ liệu tốt hơn.

## 5. ApplicationListener và forPayload()

Ngoài @EventListener, Spring còn hỗ trợ listener triển khai ApplicationListener.

ApplicationListener có tham số kiểu là một lớp con của ApplicationEvent. Với payload event, có thể khai báo:

~~~java
ApplicationListener<PayloadApplicationEvent<OrderPlaced>> listener =
        event -> {
            OrderPlaced payload = event.getPayload();
            System.out.println(payload.orderId());
        };
~~~

Listener này nhận wrapper và tự lấy payload bằng getPayload().

Từ Spring Framework 5.3, ApplicationListener cung cấp phương thức tĩnh forPayload(Consumer<T>). Phương thức này tạo một listener nhận PayloadApplicationEvent<T> nhưng chuyển tiếp riêng payload cho Consumer:

~~~java
ApplicationListener<PayloadApplicationEvent<OrderPlaced>> listener =
        ApplicationListener.forPayload(
                payload -> System.out.println(payload.orderId()));
~~~

Đăng ký listener với ApplicationContext:

~~~java
context.addApplicationListener(listener);
~~~

Điểm khác nhau:

- ApplicationListener<PayloadApplicationEvent<OrderPlaced>> cho phép xử lý wrapper và gọi getPayload().
- ApplicationListener.forPayload(...) giúp viết consumer chỉ quan tâm payload.
- @EventListener với tham số OrderPlaced là cách khai báo trực quan trong một Spring bean.

Chọn một cách theo nhu cầu của thành phần. Không cần tạo nhiều listener cùng thực hiện một phản ứng chỉ để minh họa các API khác nhau.

## 6. Ví dụ hoàn chỉnh với Java 17 và Spring Framework

Ví dụ sau phát một đối tượng OrderPlaced thông thường. Spring tự bọc nó thành PayloadApplicationEvent. Một listener nhận payload trực tiếp, listener còn lại nhận wrapper để đọc source và payload.

### Cấu trúc dự án

~~~text
payload-events-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── PayloadEventsDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>payload-events-demo</artifactId>
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
                    <mainClass>demo.PayloadEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### PayloadEventsDemo.java

~~~java
package demo;

import java.math.BigDecimal;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.PayloadApplicationEvent;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Configuration
@ComponentScan(basePackageClasses = PayloadEventsDemo.class)
public class PayloadEventsDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             PayloadEventsDemo.class)) {
            OrderPublisher publisher = context.getBean(OrderPublisher.class);
            publisher.publish(
                    new OrderPlaced("DH-2001", new BigDecimal("250000")));
        }
    }
}

record OrderPlaced(String orderId, BigDecimal total) {
}

@Component
class OrderPublisher {

    private final ApplicationEventPublisher eventPublisher;

    OrderPublisher(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    void publish(OrderPlaced payload) {
        eventPublisher.publishEvent(payload);
    }
}

@Component
class OrderEventListeners {

    @EventListener
    @Order(1)
    void receivePayload(OrderPlaced payload) {
        System.out.println(
                "Payload listener: " + payload.orderId()
                        + ", total=" + payload.total().toPlainString());
    }

    @EventListener
    @Order(2)
    void inspectWrapper(PayloadApplicationEvent<OrderPlaced> event) {
        System.out.println(
                "Envelope listener: " + event.getClass().getSimpleName());
        System.out.println(
                "Source type: " + event.getSource().getClass().getSimpleName());
        System.out.println(
                "Payload type: " + event.getPayload().getClass().getSimpleName());
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
Payload listener: DH-2001, total=250000
Envelope listener: PayloadApplicationEvent
Source type: AnnotationConfigApplicationContext
Payload type: OrderPlaced
~~~

### Phân tích luồng chạy

1. Spring tạo ApplicationContext và đăng ký OrderPublisher cùng OrderEventListeners.
2. OrderPublisher nhận ApplicationEventPublisher qua constructor injection.
3. Phương thức publish truyền đối tượng OrderPlaced vào publishEvent.
4. OrderPlaced không kế thừa ApplicationEvent, nên Spring tạo PayloadApplicationEvent<OrderPlaced> để phân phối.
5. Listener receivePayload khai báo tham số OrderPlaced. Spring lấy payload bên trong wrapper và truyền vào phương thức.
6. Listener inspectWrapper khai báo tham số PayloadApplicationEvent<OrderPlaced>. Spring truyền wrapper để phương thức đọc source và payload.
7. @Order(1) và @Order(2) làm rõ thứ tự của hai listener trong ví dụ.

Điểm cần quan sát là publisher chỉ phát OrderPlaced. Publisher không tự tạo wrapper và cũng không cần biết listener nào nhận payload trực tiếp hay nhận wrapper.

## 7. Generic payload và ResolvableType

PayloadApplicationEvent<T> hỗ trợ kiểu generic. Thông tin kiểu này hữu ích khi listener chỉ muốn nhận payload thuộc một kiểu cụ thể.

Ví dụ:

~~~java
ApplicationListener<PayloadApplicationEvent<OrderPlaced>> listener =
        event -> System.out.println(event.getPayload().orderId());
~~~

PayloadApplicationEvent triển khai ResolvableTypeProvider để cung cấp thông tin kiểu cho cơ chế phân phối event. Spring có thể dùng thông tin đó khi đối chiếu listener theo kiểu generic.

### Giới hạn do type erasure

Java xóa phần lớn thông tin generic ở runtime. Với một payload đơn giản như OrderPlaced, Spring có thể suy ra kiểu từ instance. Nhưng nếu payload là một collection như List<OrderLine>, chỉ nhìn class runtime của collection thường không đủ để xác định chính xác kiểu phần tử OrderLine.

Ví dụ, hai giá trị sau có cùng class runtime là một kiểu List cụ thể:

~~~java
List<OrderLine> orderLines;
List<Customer> customers;
~~~

Nếu việc lọc listener phụ thuộc vào generic element type, không nên giả định Spring luôn suy ra được thông tin đó chỉ từ instance.

### Truyền kiểu payload rõ ràng

Constructor ba tham số của PayloadApplicationEvent có thể nhận ResolvableType mô tả payload. Cách này hữu ích khi cần giữ thông tin generic mà runtime không thể suy ra:

~~~java
import java.util.List;

import org.springframework.context.PayloadApplicationEvent;
import org.springframework.core.ResolvableType;

List<OrderLine> lines = List.of(
        new OrderLine("SP-01", 2),
        new OrderLine("SP-02", 1));

ResolvableType payloadType =
        ResolvableType.forClassWithGenerics(List.class, OrderLine.class);

PayloadApplicationEvent<List<OrderLine>> event =
        new PayloadApplicationEvent<>(this, lines, payloadType);

eventPublisher.publishEvent(event);
~~~

Listener có thể khai báo đúng kiểu wrapper:

~~~java
@EventListener
void handleOrderLines(
        PayloadApplicationEvent<List<OrderLine>> event) {

    List<OrderLine> lines = event.getPayload();
    System.out.println(lines.size());
}
~~~

Trong ví dụ trên, payloadType mô tả kiểu của payload là List<OrderLine>, không phải kiểu wrapper PayloadApplicationEvent<List<OrderLine>>.

Constructor có tham số ResolvableType được bổ sung từ Spring Framework 6.0. Với payload có kiểu cụ thể, không cần tạo wrapper thủ công; hãy dùng publishEvent(payload) để Spring tự bọc.

## 8. Payload object so với custom ApplicationEvent

Hai lựa chọn này đều hợp lệ, nhưng phục vụ nhu cầu khác nhau.

### Dùng payload object

~~~java
record OrderPlaced(String orderId, BigDecimal total) {
}

eventPublisher.publishEvent(
        new OrderPlaced("DH-2001", new BigDecimal("250000")));
~~~

Phù hợp khi:

- Event có thể biểu diễn bằng một đối tượng dữ liệu rõ ràng.
- Không cần kế thừa ApplicationEvent.
- Muốn listener nhận trực tiếp record hoặc POJO.
- Muốn giảm mã khởi tạo và giữ payload dễ kiểm thử.

### Dùng custom ApplicationEvent

~~~java
public final class OrderPlacedEvent extends ApplicationEvent {

    private final String orderId;

    public OrderPlacedEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

Khi publish:

~~~java
eventPublisher.publishEvent(
        new OrderPlacedEvent(this, "DH-2001"));
~~~

Spring phát trực tiếp OrderPlacedEvent vì đây đã là ApplicationEvent. Listener nhận đúng lớp event:

~~~java
@EventListener
void handleOrderPlaced(OrderPlacedEvent event) {
    System.out.println(event.getOrderId());
}
~~~

Custom ApplicationEvent phù hợp khi muốn định nghĩa rõ một event class kế thừa ApplicationEvent, cần dùng source/timestamp của lớp cha hoặc muốn kiểm soát cấu trúc event theo mô hình truyền thống.

Không cần kế thừa ApplicationEvent chỉ để Spring nhận diện một đối tượng là event. Từ Spring Framework 4.2, đối tượng thông thường đã có thể được publish và tự động bọc thành PayloadApplicationEvent.

## 9. Những lỗi thường gặp

### Nhầm source với payload

event.getSource() trả về nguồn phát, không phải dữ liệu nghiệp vụ. Với payload được ApplicationContext tự bọc, source thường là context. Muốn lấy OrderPlaced, hãy gọi event.getPayload().

### Listener nhận sai cấp dữ liệu

Nếu listener khai báo tham số PayloadApplicationEvent<OrderPlaced>, nó phải đọc dữ liệu qua getPayload(). Nếu listener chỉ cần OrderPlaced, hãy khai báo tham số OrderPlaced để Spring chuyển payload trực tiếp.

### Dùng kiểu quá rộng

Một listener nhận Object hoặc PayloadApplicationEvent<?> có thể phù hợp với quá nhiều event. Điều này làm luồng xử lý khó theo dõi và dễ vô tình xử lý payload ngoài dự kiến. Nên ưu tiên kiểu event cụ thể.

### Tự bọc payload không cần thiết

Với đối tượng thông thường, chỉ cần gọi publishEvent(payload). Việc tạo PayloadApplicationEvent thủ công thường không cần thiết, trừ khi có lý do cụ thể như truyền ResolvableType cho generic payload.

### Giả định payload được sao chép

Wrapper không đảm bảo tạo bản sao độc lập của payload. Nếu nhiều listener cùng đọc một đối tượng mutable, thay đổi trạng thái có thể gây ra kết quả khó dự đoán. Hãy ưu tiên record, immutable collection hoặc dữ liệu không bị sửa sau khi phát.

### Nhầm payload event với message broker

PayloadApplicationEvent là wrapper nội bộ của Spring Application Events. Nó không tự serialize, lưu bền vững, gửi sang tiến trình khác hoặc cung cấp retry. Nếu cần giao tiếp liên dịch vụ, cần tích hợp cơ chế messaging phù hợp.

## 10. Ghi nhớ

Khi publisher truyền một đối tượng không kế thừa ApplicationEvent vào publishEvent(Object), Spring tự bọc đối tượng đó trong PayloadApplicationEvent<T>. Payload là dữ liệu nghiệp vụ; wrapper là event Spring dùng để phân phối.

Listener có thể nhận payload trực tiếp bằng cách khai báo tham số theo kiểu payload, hoặc nhận toàn bộ wrapper bằng PayloadApplicationEvent<T> rồi đọc getPayload() và getSource(). ApplicationListener.forPayload() là một lựa chọn gọn khi dùng ApplicationListener nhưng chỉ cần Consumer nhận payload.

Với generic payload, ResolvableTypeProvider giúp Spring nhận diện kiểu. Khi type erasure khiến kiểu phần tử không thể suy ra từ instance, có thể truyền ResolvableType tường minh qua constructor ba tham số của PayloadApplicationEvent. Chọn payload bất biến, kiểu cụ thể và listener có phạm vi rõ ràng để event dễ hiểu và an toàn khi mở rộng.

## Tài liệu tham khảo chính thức

- [ApplicationEventPublisher — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [PayloadApplicationEvent — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/PayloadApplicationEvent.html)
- [ApplicationListener — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationListener.html)
- [ResolvableType — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/ResolvableType.html)
