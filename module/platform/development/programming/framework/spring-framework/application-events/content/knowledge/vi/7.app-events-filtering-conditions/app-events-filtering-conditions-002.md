# SpEL truy cập event và payload trong Spring Framework

Spring hỗ trợ lọc event ngay tại listener bằng thuộc tính **condition** của annotation **@EventListener**. Giá trị của condition là một biểu thức Spring Expression Language (SpEL). Spring chỉ gọi phương thức listener khi biểu thức cho kết quả đúng.

Để viết điều kiện chính xác, cần hiểu SpEL đang nhìn thấy đối tượng nào. Evaluation context của event listener cung cấp event gốc, mảng tham số của phương thức và các biến đại diện cho từng tham số. Những biến thường dùng nhất là **#root.event**, **#root.args**, **#a0** và **#p0**.

Một điểm cần nhớ: khi publish một đối tượng Java thông thường không kế thừa ApplicationEvent, Spring bọc đối tượng đó trong **PayloadApplicationEvent**. Trong khi đó, tham số của phương thức listener vẫn có thể nhận trực tiếp payload ban đầu. Vì vậy, biểu thức truy cập event wrapper và biểu thức truy cập payload có thể khác nhau.

## 1. condition dùng để làm gì?

Nếu một bean có phương thức **@EventListener**, Spring đăng ký phương thức đó để nhận loại event tương ứng. Thuộc tính **condition** bổ sung một bộ lọc lúc chạy.

Ví dụ, chỉ xử lý đơn hàng có tổng tiền từ 1.000 trở lên:

```java
@EventListener(condition = "#a0.amount >= 1000")
public void handleLargeOrder(OrderPlacedEvent event) {
    System.out.println("Đơn hàng giá trị cao: " + event.getOrderId());
}
```

Spring vẫn nhận biết phương thức này là listener của OrderPlacedEvent. Trước khi gọi phương thức, Spring đánh giá condition. Nếu amount nhỏ hơn 1.000, phương thức không được gọi.

Nếu condition để trống, listener được gọi cho mọi event phù hợp với kiểu mà phương thức đăng ký. Condition phải trả về boolean true hoặc một trong các chuỗi được Spring chấp nhận là đúng: "true", "on", "yes" hoặc "1". Thông thường nên viết biểu thức boolean rõ ràng để người đọc dễ hiểu.

Condition thực hiện lọc ở thời điểm event được dispatch. Nó không thay đổi event, không biến listener thành một truy vấn database và không tự xử lý retry.

## 2. Evaluation context của event listener

Spring tạo một evaluation context riêng cho mỗi lần đánh giá điều kiện. Context cung cấp các dữ liệu sau:

| Cách truy cập | Ý nghĩa |
|---|---|
| **#root.event** hoặc **event** | ApplicationEvent thực tế được đưa vào cơ chế dispatch |
| **#root.args** hoặc **args** | Mảng tham số được dùng để gọi phương thức listener |
| **#root.args[0]** hoặc **args[0]** | Tham số đầu tiên của phương thức |
| **#a0** | Tham số đầu tiên theo chỉ số |
| **#p0** | Bí danh khác của tham số đầu tiên |
| **#a1**, **#p1** | Tham số thứ hai, nếu phương thức có tham số đó |
| **#tenThamSo** | Tham số theo tên, nếu tên tham số có trong bytecode |

Các chỉ số bắt đầu từ 0. Do đó, #a0 và #p0 đều chỉ tham số đầu tiên.

### #root.event

Đây là event gốc mà ApplicationEventMulticaster đang phân phối. Nếu ứng dụng publish một lớp tự định nghĩa kế thừa ApplicationEvent, #root.event chính là instance của lớp event đó.

Ví dụ:

```java
@EventListener(condition = "#root.event.amount >= 1000")
public void handleLargeOrder(OrderPlacedEvent event) {
    // ...
}
```

SpEL truy cập thuộc tính amount trên event thông qua getter tương ứng, chẳng hạn getAmount().

### #root.args và #a0 / #p0

Các biến này truy cập đối số mà Spring chuẩn bị để gọi phương thức listener. Với listener chỉ nhận một tham số, #root.args[0], #a0 và #p0 đều tham chiếu đến đối tượng tham số thứ nhất.

```java
@EventListener(condition = "#root.args[0].region == 'EU'")
public void handleEuropeanOrder(OrderPlacedEvent event) {
    // ...
}
```

Dùng chỉ số là cách ổn định khi không muốn phụ thuộc vào tên tham số được giữ trong bytecode. Nó cũng hữu ích khi đổi tên biến trong phương thức mà không muốn sửa biểu thức.

### Truy cập theo tên tham số

Nếu bytecode giữ tên tham số, có thể dùng tên đó làm biến SpEL:

```java
@EventListener(condition = "#orderEvent.amount >= 1000")
public void handleOrder(OrderPlacedEvent orderEvent) {
    // ...
}
```

Để bảo đảm Java compiler lưu tên tham số, có thể bật tùy chọn **-parameters**. Với Maven Compiler Plugin, cấu hình **parameters=true**. Nếu tên tham số không được giữ hoặc Spring không thể khám phá tên đó, hãy dùng #a0 hoặc #p0.

## 3. Phân biệt ApplicationEvent và payload object

Spring hỗ trợ hai kiểu đối tượng được publish:

1. Một lớp event kế thừa ApplicationEvent.
2. Một object Java thông thường, chẳng hạn POJO hoặc record, không cần kế thừa ApplicationEvent.

### Event kế thừa ApplicationEvent

Ví dụ:

```java
public class OrderPlacedEvent extends ApplicationEvent {
    private final String orderId;
    private final BigDecimal amount;

    public OrderPlacedEvent(
            Object source,
            String orderId,
            BigDecimal amount
    ) {
        super(source);
        this.orderId = orderId;
        this.amount = amount;
    }

    public String getOrderId() {
        return orderId;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
```

Khi publisher gọi publishEvent(new OrderPlacedEvent(...)), Spring dispatch chính instance này. Trong condition, #root.event.amount và #a0.amount đều có thể truy cập dữ liệu tương ứng: một biến nhìn từ event gốc, biến còn lại nhìn từ tham số listener.

### POJO hoặc record payload

Từ Spring Framework 4.2, publisher có thể phát một object bất kỳ:

```java
public class OrderPlacedPayload {
    private final String orderId;
    private final BigDecimal amount;

    public OrderPlacedPayload(String orderId, BigDecimal amount) {
        this.orderId = orderId;
        this.amount = amount;
    }

    public String getOrderId() {
        return orderId;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
```

Khi gọi publishEvent(payload), Spring bọc object này trong **PayloadApplicationEvent** để đưa vào hạ tầng event. Listener vẫn có thể khai báo tham số là OrderPlacedPayload:

```java
@EventListener(condition = "#root.args[0].amount >= 1000")
public void handlePayload(OrderPlacedPayload payload) {
    // payload là object được publish ban đầu.
}
```

Trong trường hợp payload, **#root.event** tham chiếu đến ApplicationEvent wrapper, còn **#root.args[0]** tham chiếu đến payload đã được Spring giải quyết thành tham số phương thức. Nếu cần truy cập payload thông qua wrapper, có thể dùng đường dẫn **#root.event.payload**. Trong hầu hết listener có kiểu tham số cụ thể, dùng #a0 hoặc #root.args[0] trực tiếp và dễ đọc hơn.

## 4. Các biểu thức SpEL thường dùng

Condition là một biểu thức SpEL, vì vậy có thể dùng các toán tử so sánh, logic và truy cập thuộc tính.

### So sánh số

```java
@EventListener(condition = "#a0.amount > 1000")
public void handlePremiumOrder(OrderPlacedEvent event) {
    // ...
}
```

Các toán tử thường dùng gồm >, >=, <, <=, == và !=. Với BigDecimal, Spring Expression Language hỗ trợ so sánh giá trị số; trong code nghiệp vụ cần tính toán tiền chính xác, vẫn nên dùng BigDecimal thay vì double.

### So sánh chuỗi

```java
@EventListener(condition = "#a0.region == 'EU'")
public void handleEuropeanOrder(OrderPlacedEvent event) {
    // ...
}
```

Chuỗi literal trong SpEL dùng dấu nháy đơn. Toán tử == thực hiện so sánh giá trị theo cơ chế của SpEL; không cần gọi equals() trong biểu thức đơn giản này.

### Kết hợp điều kiện AND và OR

```java
@EventListener(
    condition = "#a0.amount >= 1000 && #a0.region == 'EU'"
)
public void handleLargeEuropeanOrder(OrderPlacedEvent event) {
    // ...
}
```

Có thể dùng **&&** hoặc từ khóa **and** cho AND; dùng **||** hoặc **or** cho OR. Dùng ngoặc để làm rõ thứ tự ưu tiên khi biểu thức có nhiều nhánh.

### Phủ định

```java
@EventListener(condition = "#a0.cancelled == false")
public void handleActiveOrder(OrderPlacedEvent event) {
    // ...
}
```

Có thể dùng **!** hoặc **not** để phủ định một biểu thức boolean. Với thuộc tính boolean, biểu thức trực tiếp như #a0.cancelled == false thường dễ đọc hơn.

### Truy cập thuộc tính có thể null

Nếu một nhánh dữ liệu có thể null, toán tử safe navigation **?.** giúp tránh truy cập thuộc tính trên tham chiếu null:

```java
@EventListener(condition = "#a0.customer?.vip == true")
public void handleVipCustomerOrder(OrderPlacedEvent event) {
    // ...
}
```

Cần kiểm tra đường dẫn thuộc tính và kiểu dữ liệu thực tế. Safe navigation chỉ bảo vệ phần truy cập được viết với ?.; nó không tự bảo vệ mọi thuộc tính khác trong biểu thức.

## 5. Ví dụ hoàn chỉnh với Java 17 và Spring Framework

Ví dụ dùng Spring Context thuần để minh họa ba cách truy cập:

- Listener thứ nhất đọc custom ApplicationEvent qua #root.event.
- Listener thứ hai đọc tham số listener qua #a0.
- Listener thứ ba nhận POJO payload và đọc tham số qua #root.args[0].

Một đơn hàng chỉ được xử lý bởi listener có condition phù hợp. Ví dụ không cần Spring Boot.

### 5.1. Cấu trúc dự án

```text
spring-event-spel/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── example/
                    └── spel/
                        └── Application.java
```

### 5.2. Dependency Maven

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>spring-event-spel</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.example.spel.Application</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. Mã nguồn

Tạo file src/main/java/dev/example/spel/Application.java:

```java
package dev.example.spel;

import java.math.BigDecimal;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class Application {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService service = context.getBean(OrderService.class);

            service.placeOrder(
                    "ORD-1001",
                    new BigDecimal("1500.00"),
                    "EU"
            );

            service.placeOrder(
                    "ORD-1002",
                    new BigDecimal("80.00"),
                    "US"
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        public LargeOrderListener largeOrderListener() {
            return new LargeOrderListener();
        }

        @Bean
        public EuropeanOrderListener europeanOrderListener() {
            return new EuropeanOrderListener();
        }

        @Bean
        public PayloadOrderListener payloadOrderListener() {
            return new PayloadOrderListener();
        }
    }

    public static class OrderPlacedEvent extends ApplicationEvent {
        private final String orderId;
        private final BigDecimal amount;
        private final String region;

        public OrderPlacedEvent(
                Object source,
                String orderId,
                BigDecimal amount,
                String region
        ) {
            super(source);
            this.orderId = orderId;
            this.amount = amount;
            this.region = region;
        }

        public String getOrderId() {
            return orderId;
        }

        public BigDecimal getAmount() {
            return amount;
        }

        public String getRegion() {
            return region;
        }
    }

    // POJO payload không cần kế thừa ApplicationEvent.
    public static class OrderPlacedPayload {
        private final String orderId;
        private final BigDecimal amount;
        private final String region;

        public OrderPlacedPayload(
                String orderId,
                BigDecimal amount,
                String region
        ) {
            this.orderId = orderId;
            this.amount = amount;
            this.region = region;
        }

        public String getOrderId() {
            return orderId;
        }

        public BigDecimal getAmount() {
            return amount;
        }

        public String getRegion() {
            return region;
        }
    }

    public static class OrderService {
        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void placeOrder(
                String orderId,
                BigDecimal amount,
                String region
        ) {
            // Publish custom ApplicationEvent.
            publisher.publishEvent(
                    new OrderPlacedEvent(this, orderId, amount, region)
            );

            // Publish POJO payload; Spring bọc nó trong PayloadApplicationEvent.
            publisher.publishEvent(
                    new OrderPlacedPayload(orderId, amount, region)
            );
        }
    }

    public static class LargeOrderListener {

        @EventListener(condition = "#root.event.amount >= 1000")
        public void onLargeOrder(OrderPlacedEvent event) {
            System.out.printf(
                    "Large order: %s, amount=%s%n",
                    event.getOrderId(),
                    event.getAmount()
            );
        }
    }

    public static class EuropeanOrderListener {

        @EventListener(condition = "#a0.region == 'EU'")
        public void onEuropeanOrder(OrderPlacedEvent event) {
            System.out.printf(
                    "EU order: %s, region=%s%n",
                    event.getOrderId(),
                    event.getRegion()
            );
        }
    }

    public static class PayloadOrderListener {

        @EventListener(
                condition = "#root.args[0].amount >= 1000 && "
                        + "#root.args[0].region == 'EU'"
        )
        public void onLargeEuropeanPayload(OrderPlacedPayload payload) {
            System.out.printf(
                    "Large EU payload: %s%n",
                    payload.getOrderId()
            );
        }
    }
}
```

### 5.4. Chạy chương trình

Tại thư mục chứa pom.xml, chạy:

```bash
mvn -q compile exec:java
```

Stdout mong đợi:

```text
Large order: ORD-1001, amount=1500.00
EU order: ORD-1001, region=EU
Large EU payload: ORD-1001
```

Đơn ORD-1001 có amount bằng 1.500 và region là EU nên thỏa cả ba điều kiện. Đơn ORD-1002 có amount bằng 80 và region là US nên không listener nào trong ví dụ được gọi.

Kết quả minh họa:

- **#root.event.amount:** đọc amount từ custom ApplicationEvent.
- **#a0.region:** đọc region từ tham số thứ nhất của phương thức listener.
- **#root.args[0].amount:** đọc amount từ tham số payload mà listener nhận trực tiếp, dù event bên trong hạ tầng Spring là PayloadApplicationEvent.

## 6. Lọc theo kiểu event và lọc bằng condition

Kiểu tham số của phương thức listener xác định loại event mà listener có thể nhận. Condition bổ sung điều kiện dữ liệu ở thời điểm dispatch.

Ví dụ:

```java
@EventListener(condition = "#a0.amount >= 1000")
public void onOrder(OrderPlacedEvent event) {
    // ...
}
```

Có hai bước logic:

1. Spring xác định event có phù hợp với kiểu OrderPlacedEvent của phương thức không.
2. Nếu kiểu phù hợp, Spring đánh giá SpEL condition. Chỉ khi điều kiện đúng, phương thức mới được gọi.

Do đó, condition không thay thế việc khai báo đúng kiểu event. Nếu một listener phải nhận nhiều kiểu event khác nhau, hãy thiết kế chữ ký hoặc thuộc tính classes phù hợp rồi viết điều kiện tương ứng. Khi annotation khai báo nhiều event class, phương thức không được khai báo tham số; trong trường hợp đó có thể truy cập event thông qua evaluation context.

Không nên dùng một condition phức tạp để thay thế thiết kế event type rõ ràng. Kiểu event nên lọc theo loại sự kiện; condition nên lọc theo dữ liệu hoặc trạng thái đơn giản của event.

## 7. Tham số theo tên và tùy chọn -parameters

Một số biểu thức dễ đọc hơn khi dùng tên tham số:

```java
@EventListener(condition = "#orderEvent.amount >= 1000")
public void handle(OrderPlacedEvent orderEvent) {
    // ...
}
```

Để cách truy cập này hoạt động ổn định, cần bảo đảm tên tham số có thể được khám phá từ bytecode. Với Maven Compiler Plugin, bật:

```xml
<configuration>
    <release>17</release>
    <parameters>true</parameters>
</configuration>
```

Nếu không thể bảo đảm parameter names, dùng #a0, #p0 hoặc #root.args[0]. Các cách theo chỉ số không phụ thuộc vào tên biến trong source code.

Một nguyên tắc hữu ích là dùng #a0 cho biểu thức ngắn, dùng tên tham số khi dự án đã thống nhất biên dịch với -parameters và biểu thức có nhiều trường cần đọc. Không đổi tên biến tham số mà quên cập nhật condition nếu đang tham chiếu theo tên.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Listener không chạy dù event đúng loại | Condition trả về false | Kiểm tra giá trị thực tế của các trường và toán tử so sánh |
| SpEL báo không tìm thấy biến tên tham số | Bytecode không giữ tên tham số | Dùng #a0/#p0 hoặc bật -parameters |
| Không truy cập được thuộc tính trên #root.event | Event là PayloadApplicationEvent wrapper hoặc đường dẫn thuộc tính sai | Dùng #root.args[0] để đọc tham số payload; nếu cần wrapper, kiểm tra #root.event.payload |
| Không truy cập được thuộc tính payload | Getter không tồn tại hoặc tên property sai | Dùng getter JavaBean như getAmount() và kiểm tra chính tả property |
| Condition lỗi khi dữ liệu null | Biểu thức truy cập thuộc tính trên giá trị null | Dùng safe navigation ?. và kiểm tra null rõ ràng |
| Listener nhận event nhưng không xử lý một số payload | Payload không tương thích với kiểu tham số hoặc condition không thỏa | Kiểm tra loại payload, kiểu listener và condition |
| Condition trở nên khó bảo trì | Biểu thức chứa nhiều nhánh nghiệp vụ hoặc nhiều truy cập lồng nhau | Tách logic nghiệp vụ vào service/listener, giữ condition đơn giản |

## 9. Nguyên tắc thiết kế condition

- Chỉ dùng condition cho bộ lọc đơn giản, dễ đọc và có thể đánh giá từ dữ liệu event.
- Ưu tiên truy cập tham số bằng #a0 hoặc #root.args[0] nếu không chắc chắn tên tham số được giữ trong bytecode.
- Dùng #root.event khi cần truy cập ApplicationEvent thực tế.
- Với POJO payload, nhớ rằng Spring bọc payload trong PayloadApplicationEvent; tham số phương thức vẫn có thể là payload gốc.
- Bảo đảm tên property tương ứng với getter hoặc property accessor có thể truy cập.
- Dùng toán tử safe navigation khi thuộc tính trung gian có thể null.
- Không đặt truy vấn database, gọi dịch vụ bên ngoài hoặc logic có side effect trong SpEL condition.
- Không ghép biểu thức SpEL trực tiếp từ dữ liệu người dùng hoặc cấu hình không đáng tin cậy.
- Giữ điều kiện ngắn; nếu nghiệp vụ cần nhiều bước, chuyển phần đánh giá vào code Java có kiểm thử.

Condition chỉ quyết định listener có được gọi hay không. Các quy tắc nghiệp vụ quan trọng như quyền truy cập, hạn mức, trạng thái giao dịch và tính hợp lệ của dữ liệu vẫn cần được xác thực trong service nghiệp vụ.

## 10. Condition khi listener chạy bất đồng bộ

Có thể kết hợp @EventListener với @Async để xử lý listener trên executor riêng:

```java
@Async
@EventListener(condition = "#a0.amount >= 1000")
public void handleLargeOrder(OrderPlacedEvent event) {
    // Xử lý bất đồng bộ.
}
```

Cần bật async bằng @EnableAsync và bảo đảm listener là bean do Spring quản lý. Condition vẫn là bộ lọc của event listener; việc bật async không biến điều kiện SpEL thành một cơ chế retry hoặc bảo đảm thứ tự hoàn thành.

Với listener bất đồng bộ, exception không được truyền ngược về nơi gọi publishEvent như listener đồng bộ thông thường. Nếu cần xử lý lỗi, hãy cấu hình AsyncUncaughtExceptionHandler hoặc cơ chế quan sát và retry phù hợp. Một listener bất đồng bộ cũng không thể dùng giá trị trả về để tự publish event tiếp theo; nếu cần phát event khác, hãy inject ApplicationEventPublisher và gọi publishEvent rõ ràng.

Không nên dùng @Async chỉ để làm condition chạy nhanh hơn. Điều kiện nên là biểu thức nhỏ và không thực hiện I/O.

## 11. Checklist khi viết SpEL cho event

- Listener đã khai báo đúng event type hoặc payload type.
- Đã xác định #root.event là event gốc nào.
- Đã xác định #root.args[0] là đối tượng nào mà listener thực sự nhận.
- Dùng #a0/#p0 khi muốn tránh phụ thuộc tên tham số.
- Nếu dùng #tenThamSo, bytecode phải giữ tên tham số, ví dụ bật -parameters.
- Property trong SpEL có getter hoặc accessor hợp lệ.
- Các nhánh có thể null được bảo vệ bằng safe navigation hoặc điều kiện kiểm tra.
- Condition trả về boolean rõ ràng.
- Điều kiện không chứa truy vấn, I/O hoặc side effect.
- Đã kiểm tra trường hợp event khớp và không khớp condition.
- Nếu listener async, đã có cách theo dõi exception và không dựa vào giá trị trả về để phát event tiếp theo.

## 12. Tài liệu tham khảo

- Spring Framework 6.2 Reference: Additional Capabilities of the ApplicationContext, phần Annotation-based Event Listeners.
- Spring Framework 6.2 Javadoc: EventListener, thuộc tính condition và metadata được cung cấp trong SpEL evaluation context.

Khi nắm rõ sự khác nhau giữa event gốc và tham số payload, bạn có thể viết condition ngắn gọn, an toàn và dễ kiểm tra. Hãy dùng #root.event cho ApplicationEvent, #root.args hoặc #a0/#p0 cho tham số listener, và nhớ rằng POJO payload được Spring bọc trong PayloadApplicationEvent trước khi đi qua event multicaster.
