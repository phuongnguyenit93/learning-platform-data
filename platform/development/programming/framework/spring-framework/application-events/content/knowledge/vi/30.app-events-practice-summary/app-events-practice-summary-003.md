# Lọc listener bằng điều kiện trong Spring Framework Application Events

## 1. Bối cảnh và mục tiêu

Trong nhóm **Thực hành và tổng kết** của **Spring Framework Application Events**, một câu hỏi rất thực tế là: ứng dụng cùng phát `OrderPlaced` cho mọi đơn hàng, nhưng chỉ muốn một số listener phản ứng khi **đơn giá trị cao**, khi **đơn đến từ kênh WEB**, hoặc khi **đơn đủ điều kiện gửi thông báo**. Có nhất thiết phải tạo một lớp event và một phương thức kiểm tra `if` riêng cho từng tình huống?

Spring hỗ trợ thuộc tính `condition` của `@EventListener` để viết một biểu thức **Spring Expression Language (SpEL)**. Biểu thức được đánh giá cho event phù hợp; chỉ khi điều kiện là `true` thì phương thức listener mới được gọi. Nhờ vậy, bạn có thể diễn đạt một bộ lọc nhỏ, tường minh ngay tại điểm đăng ký.

Ví dụ:

```java
@EventListener(condition = "#a0.totalCents() >= 100000")
public void onHighValueOrder(OrderPlaced event) {
    // Chỉ chạy khi đơn có tổng tiền từ 100.000 đơn vị nhỏ nhất trở lên.
}
```

Đây là **đoạn minh họa**, giả định `OrderPlaced` là record/class có phương thức `totalCents()`. Giá trị `100000` tính theo **đơn vị tiền nhỏ nhất** được quy ước trong hệ thống demo, không phải một tỷ giá cố định hay đơn vị tiền tệ mặc định.

Bài này hướng đến những năng lực:

1. Hiểu thứ tự **chọn listener theo kiểu event** rồi **đánh giá điều kiện SpEL**.
2. Sử dụng đúng `#a0`, `#p0`, `#root.args[0]` và tên tham số nếu có metadata.
3. Biết giới hạn của `condition` đối với bảo mật, độ tin cậy, transaction và async.
4. Phân biệt việc lọc bằng annotation với việc kiểm tra `if` bên trong handler, hoặc tạo event type riêng.
5. Chạy một ví dụ **Java 17+ / Spring Framework 6.1** và kiểm tra đúng listener nào thực thi.
6. Viết unit/integration tests cho nhánh true, false, giá trị biên, input không hợp lệ và tác động của cấu hình multicaster.
7. Tránh biểu thức SpEL tốn kém, phụ thuộc vào trạng thái mutable hoặc gây side effect.

**Quy tắc ngắn:** `@EventListener(condition = "...")` là **bộ lọc thực thi callback**, không phải ranh giới authorization và không phải bộ lọc tại database/message broker.

## 2. Cơ chế Spring chọn và gọi listener

Đường đi khái niệm:

```text
ApplicationEventPublisher.publishEvent(event)
                  |
                  v
       ApplicationEventMulticaster
                  |
        Lọc theo kiểu event
                  |
      Chọn các listener phù hợp
                  |
        Với @EventListener adapter:
                  |
          Đánh giá SpEL condition
              /             \
           true             false
            |                 |
   Gọi listener method     Bỏ qua method
            |
       Business logic
```

Giả sử ứng dụng có ba listener cho cùng kiểu `OrderPlaced`:
- `onEveryOrder`: không có `condition`.
- `onHighValueOrder`: điều kiện tổng tiền ≥ 100000.
- `onWebOrder`: điều kiện kênh đặt hàng bằng `"WEB"`.

Khi publish một đơn nhỏ từ WEB, Spring sẽ xác định cả ba adapter thuộc kiểu `OrderPlaced`. Sau đó, điều kiện của `onHighValueOrder` là false nên **method body không chạy**, nhưng điều kiện của `onWebOrder` true nên handler WEB chạy.

### Hai cấp lọc không giống nhau

| Cấp | Spring quyết định gì? | Thời điểm và chi phí |
| --- | --- | --- |
| **Event-type matching** | Listener có nhận loại event này không? | Do multicaster/adapter chọn ứng viên; có khả năng sử dụng cache theo event type/source |
| **Condition matching** | Event cụ thể này có thỏa biểu thức không? | Đánh giá ở runtime cho từng event ứng viên |
| **Business guard trong method** | Thao tác có nên thực hiện sau các kiểm tra domain không? | Khi method đã được gọi |
| **Authorization** | Người gọi có quyền thực thi thao tác không? | Phải cưỡng chế tại ranh giới service/consumer đáng tin |

Điều kiện SpEL không biến listener thành một subscription được broker lọc từ xa. Event vẫn được publish trong Spring context, các listener khác vẫn có thể nhận event. `condition=false` chỉ ngăn **callback đó** được thực thi.

### Event type không thay thế event state

Một listener `@EventListener(OrderPlaced.class)` lọc theo *loại* event. `condition="#a0.totalCents() >= 100000"` lọc theo *dữ liệu trong instance* đã nhận. Việc tách hai quyết định giúp code dễ đọc, nhưng nếu một trạng thái biểu diễn **fact nghiệp vụ khác hẳn**, tạo một event type riêng vẫn có thể phù hợp hơn.

## 3. Cú pháp @EventListener(condition)

Hình thức tổng quát:

```java
@EventListener(condition = "<SpEL expression returns boolean>")
public void handle(MyEvent event) {
    // ...
}
```

Đây là **mẫu cú pháp**, placeholder `<SpEL expression returns boolean>` giải thích vị trí biểu thức, không phải giá trị sử dụng trực tiếp trong dự án. Trong code chạy thực, hãy thay bằng biểu thức SpEL như các ví dụ dưới đây.

Một method `@EventListener` thông thường có **tối đa một tham số sự kiện**. Nếu muốn listener không có tham số, cần chỉ rõ event classes qua annotation; nhưng khi ấy biểu thức phụ thuộc `#a0` sẽ không có argument tại method và không phù hợp. Với nhu cầu lọc theo payload, **khai báo một tham số event có kiểu tường minh** là lựa chọn đơn giản nhất.

### 3.1. Dùng #a0 hoặc #p0 theo vị trí tham số

```java
@EventListener(condition = "#a0.totalCents() >= 100000")
public void handleHighValue(OrderPlaced event) {
    // ...
}

@EventListener(condition = "#p0.channel() == 'WEB'")
public void handleWeb(OrderPlaced event) {
    // ...
}
```

`#a0` và `#p0` đều tham chiếu **tham số thứ nhất** (index 0) của listener method. Chúng không phụ thuộc tên biến parameter được giữ lại ở bytecode hay chưa.

- `#a0.totalCents()`: gọi accessor `totalCents()` trên event.
- `>= 100000`: so sánh số.
- `#p0.channel() == 'WEB'`: so sánh chuỗi bằng toán tử SpEL.
- Chuỗi literal của SpEL dùng dấu nháy đơn `'WEB'`.
- Điều kiện nên trả về boolean (hoặc kết quả có thể chuyển đổi rõ ràng sang boolean), không dựa vào các kiểu mơ hồ.

**Khi Java là record**, hãy dùng lời gọi accessor rõ ràng `totalCents()` và `channel()`, tránh nhầm record accessor với getter kiểu JavaBean `getTotalCents()` nếu class không có getter đó.

### 3.2. Dùng #root.args[0]

Spring cung cấp root object của expression với các thông tin liên quan đến invocation:

```java
@EventListener(
    condition = "#root.args[0].channel() == 'WEB'"
)
public void onWebOrder(OrderPlaced event) {
    // ...
}
```

`#root.args` là các argument mà listener method nhận được. Với listener một tham số như ở đây, `#root.args[0]` là `OrderPlaced`.

Có thể gặp `#root.event` trong tài liệu về Spring event expressions. **Đừng luôn giả định `#root.event` chính là payload POJO**: khi code publish một object thường không extends `ApplicationEvent`, Spring có thể bọc nó bằng `PayloadApplicationEvent`. Vì vậy, `#a0` hoặc `#root.args[0]` rõ ràng và ổn định hơn khi muốn truy cập đúng tham số method đã khai báo.

### 3.3. Dùng tên tham số (khi có metadata)

```java
@EventListener(condition = "#event.channel() == 'WEB'")
public void onWebOrder(OrderPlaced event) {
    // ...
}
```

Đây là **đoạn tích hợp** phụ thuộc khả năng Spring biết tên tham số Java `event`, ví dụ thông qua biên dịch với cờ `-parameters` và môi trường tương ứng. Nếu tên tham số không khả dụng, expression có thể thất bại hoặc không lấy được biến. Để bài demo và thư viện độc lập hơn với build flags, dùng `#a0` hoặc `#p0`.

### 3.4. Boolean operators thường dùng

| Toán tử | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `==` / `eq` | `#a0.channel() == 'WEB'` | Bằng nhau |
| `!=` / `ne` | `#a0.channel() != 'POS'` | Khác nhau |
| `>=` / `ge` | `#a0.totalCents() >= 100000` | Lớn hơn hoặc bằng |
| `>`, `<`, `<=` | `#a0.totalCents() < 50000` | So sánh số |
| `and` | `#a0.totalCents() >= 100000 and #a0.channel() == 'WEB'` | Cả hai cùng đúng |
| `or` | `#a0.channel() == 'WEB' or #a0.channel() == 'APP'` | Một trong hai đúng |
| `!` / `not` | `!#a0.cancelled()` | Phủ định boolean |
| `?.` | `#a0.customer()?.tier() == 'GOLD'` | Null-safe property/method navigation trong SpEL |

**Lưu ý:** một vài biểu thức như `#a0.customer()?.tier()` là ví dụ tích hợp yêu cầu model thật có accessor như vậy. Không đưa expression vào bài demo nếu model không khớp.

Trong SpEL, `and`/`or` thực hiện short-circuit theo semantics boolean. Tuy vậy, tránh dựa vào những getter có side effect chỉ vì một nhánh hiện tại thường không được đánh giá.

### 3.5. Không cần dấu # cho literal hoặc toán tử

Sai:

```java
@EventListener(condition = "#a0.channel() == #WEB")
```

Vì `#WEB` được hiểu là một biến trong evaluation context, **không phải** chuỗi `"WEB"`. Đúng:

```java
@EventListener(condition = "#a0.channel() == 'WEB'")
```

Đây là các dòng minh họa, không phải file Java đầy đủ.

## 4. Ví dụ đơn hàng: nhiều điều kiện trên cùng một event

Giả sử event:

```java
public record OrderPlaced(
    String orderId,
    long totalCents,
    String channel
) {}
```

Và ba listener:

```java
@EventListener
public void everyOrder(OrderPlaced event) {
    // Luôn được gọi với OrderPlaced.
}

@EventListener(condition = "#a0.totalCents() >= 100000")
public void highValue(OrderPlaced event) {
    // Chỉ đơn >= 100000.
}

@EventListener(condition = "#a0.channel() == 'WEB'")
public void webOrder(OrderPlaced event) {
    // Chỉ đơn thuộc kênh WEB.
}
```

Đây là các đoạn tích hợp. Chúng chứng minh `condition` được đánh giá **độc lập** trên từng listener: một đơn có thể khớp cả điều kiện high-value và WEB, chỉ một trong hai, hoặc không khớp điều kiện nào nhưng vẫn được `everyOrder` xử lý.

### Bảng chân trị

| Event | totalCents | channel | everyOrder | highValue | webOrder |
| --- | ---: | --- | :---: | :---: | :---: |
| ORD-1 | 50000 | WEB | Có | Không | Có |
| ORD-2 | 150000 | POS | Có | Có | Không |
| ORD-3 | 200000 | WEB | Có | Có | Có |
| ORD-4 | 99999 | POS | Có | Không | Không |
| ORD-5 | 100000 | APP | Có | Có | Không |

Giá trị biên rất quan trọng: `100000` phải được nhận nếu biểu thức dùng `>= 100000`; `99999` thì không.

**Với dữ liệu tiền**, record ở ví dụ lưu số nguyên dạng đơn vị nhỏ nhất (`long totalCents`) để tránh bẫy làm tròn số chấm động trong điều kiện. Nếu production dùng `BigDecimal`, hãy chuẩn hóa đơn vị, so sánh đúng kiểu và kiểm tra ngữ nghĩa của tiền/thuế/giảm giá trước khi viết điều kiện.

## 5. Ví dụ Java 17+ chạy được với Spring Framework 6.1.21

Ta xây một ứng dụng Spring Context tối thiểu **không dùng Spring Boot, web server, database hoặc external broker**. Chương trình tạo `AnnotationConfigApplicationContext`, đăng ký một bean có ba handler, publish ba events, rồi in danh sách order IDs mà từng handler thực sự nhận.

### 5.1. Cấu trúc dự án

```text
conditional-event-listeners/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ConditionalEventListenersDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'conditional-event-listeners'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
}

application {
    mainClass = 'demo.ConditionalEventListenersDemo'
}
```

Yêu cầu **JDK 17+**, Gradle và khả năng tải dependency từ Maven Central.

### 5.2. File Java đầy đủ

`src/main/java/demo/ConditionalEventListenersDemo.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class ConditionalEventListenersDemo {

    public record OrderPlaced(
        String orderId,
        long totalCents,
        String channel
    ) {}

    public static final class OrderListeners {
        private final List<String> allOrders = new ArrayList<>();
        private final List<String> highValueOrders = new ArrayList<>();
        private final List<String> webOrders = new ArrayList<>();

        @EventListener
        public void onEveryOrder(OrderPlaced event) {
            allOrders.add(event.orderId());
        }

        @EventListener(
            condition = "#a0.totalCents() >= 100000"
        )
        public void onHighValueOrder(OrderPlaced event) {
            highValueOrders.add(event.orderId());
        }

        @EventListener(
            condition = "#a0.channel() == 'WEB'"
        )
        public void onWebOrder(OrderPlaced event) {
            webOrders.add(event.orderId());
        }

        public void printReport() {
            System.out.println("ALL=" + allOrders);
            System.out.println("HIGH=" + highValueOrders);
            System.out.println("WEB=" + webOrders);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public OrderListeners orderListeners() {
            return new OrderListeners();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            context.publishEvent(
                new OrderPlaced("ORD-1", 50000, "WEB")
            );
            context.publishEvent(
                new OrderPlaced("ORD-2", 150000, "POS")
            );
            context.publishEvent(
                new OrderPlaced("ORD-3", 200000, "WEB")
            );

            context.getBean(OrderListeners.class).printReport();
        }
    }
}
```

Chạy:

```bash
gradle run --quiet
```

**Stdout nghiệp vụ kỳ vọng**:

```text
ALL=[ORD-1, ORD-2, ORD-3]
HIGH=[ORD-2, ORD-3]
WEB=[ORD-1, ORD-3]
```

Kết quả này có thể đối chiếu bằng bảng chân trị ở mục 4.

### 5.3. Giải thích cơ chế

1. `@Configuration` và `@Bean` tạo `OrderListeners` dưới sự quản lý của Spring. Spring phát hiện ba method `@EventListener` và đăng ký adapter thích hợp.
2. `OrderPlaced` là Java record **không extends `ApplicationEvent`**. Spring hỗ trợ publish POJO event bằng cách bọc payload khi cần; adapter chuyển payload đúng kiểu vào method.
3. `onEveryOrder` nhận mọi `OrderPlaced` được publish.
4. `onHighValueOrder` chỉ chạy khi `totalCents() >= 100000`: ORD-2 và ORD-3. ORD-1 không đủ ngưỡng.
5. `onWebOrder` chỉ chạy với `channel() == 'WEB'`: ORD-1 và ORD-3. ORD-2 có `POS` nên không chạy.
6. `SimpleApplicationEventMulticaster` mặc định dispatch đồng bộ khi không cấu hình executor hay `@Async`. Vì vậy, sau khi ba `publishEvent(...)` trả về, các list đã có đủ giá trị.
7. Danh sách ở từng handler giữ thứ tự **các lần event được publish**; thứ tự **giữa các handler khác nhau** không cần xác định để đúng output, vì chương trình chỉ in báo cáo cuối cùng.
8. `ArrayList` phù hợp trong demo đồng bộ và một main thread; nếu chuyển sang async/multi-thread, collection cần được thay bằng loại thread-safe và test cần chờ handler hoàn tất.

**Phạm vi ví dụ:** chương trình không chứng minh transaction commit, bảo mật, retry, ordering giữa các thread hay delivery bền vững. Nó chỉ chứng minh tính đúng đắn của SpEL condition trong Spring Application Events. Các snippet về transaction, async và security bên dưới là **tích hợp minh họa**, không phải phần bắt buộc để chạy demo.

### 5.4. Vì sao không in trong từng listener?

Nếu mỗi listener tự in một dòng trong method, nhiều listener cùng nhận một event có thể khiến output phụ thuộc vào thứ tự invocation. Trong demo này, mỗi handler chỉ ghi một list riêng; main in báo cáo khi mọi callback đồng bộ đã kết thúc. Cách này khiến **stdout xác định mà không cần dựa vào `@Order`** hoặc scheduler.

Muốn kiểm soát thứ tự cho các handler đồng bộ, Spring có cơ chế ordering như `@Order`. Tuy nhiên, thứ tự đăng ký/call không phải bảo đảm **thứ tự hoàn tất** khi chuyển sang executor bất đồng bộ. Đừng dùng thứ tự listener để mô hình hóa một workflow có phụ thuộc bắt buộc; hãy sử dụng orchestration/service hoặc hàng đợi có contract rõ ràng.

## 6. Nhiều điều kiện với and/or và xử lý null

### 6.1. Kết hợp business criteria nhỏ

Ví dụ gửi cảnh báo đơn lớn trên WEB:

```java
@EventListener(
    condition = "#a0.totalCents() >= 100000 and #a0.channel() == 'WEB'"
)
public void onLargeWebOrder(OrderPlaced event) {
    // ...
}
```

Điều kiện true chỉ với ORD-3 theo bộ dữ liệu demo.

Một điều kiện cho WEB hoặc APP:

```java
@EventListener(
    condition = "#a0.channel() == 'WEB' or #a0.channel() == 'APP'"
)
public void onDigitalOrder(OrderPlaced event) {
    // ...
}
```

Các đoạn trên là **mẫu tích hợp**, không phải phần của file runnable.

### 6.2. Null ở dữ liệu tùy chọn

Nếu `customerTier` hoặc `channel` có thể null, một method invocation như `#a0.customerTier().equals('GOLD')` có thể ném exception. Đổi chiều so sánh hoặc dùng null-safe navigation:

```java
@EventListener(
    condition = "#a0.customerTier() == 'GOLD'"
)
public void onGoldCustomer(OrderPlacedWithTier event) {
    // ...
}
```

Ví dụ này giả định event type `OrderPlacedWithTier` có accessor `customerTier()`. SpEL equality so sánh null an toàn hơn việc gọi `equals` trên null. Dù vậy, điều kiện không phải validator: nếu kênh, mã tiền tệ hoặc tổng tiền không hợp lệ, ứng dụng cần kiểm tra đầu vào và domain invariants ở nơi có thẩm quyền.

Đặc biệt, đừng sử dụng `condition` để **âm thầm bỏ qua event vi phạm invariant quan trọng** rồi coi workflow hoàn tất. Khi dữ liệu không hợp lệ làm ảnh hưởng consistency/reliability, cần lỗi/alert hoặc đường xử lý rõ thay vì chỉ false và bỏ qua.

## 7. Lọc bằng condition hay if bên trong method?

Cả hai đều có chỗ đứng.

### 7.1. Condition ngắn, thuần, không gây side effect

Phù hợp khi điều kiện chỉ là một quy tắc nhẹ:

```java
@EventListener(condition = "#a0.channel() == 'WEB'")
public void onWeb(OrderPlaced event) {
    // Logic chỉ dành cho kênh WEB.
}
```

Ưu điểm:
- Nhìn annotation đã biết listener có nhận mọi `OrderPlaced` hay không.
- Handler body tập trung vào điều phải làm nếu condition đúng.
- Có thể tăng tính rõ ràng với những callback đơn giản, không cần tạo event subclass.

Nhược điểm:
- Biểu thức là một **string**, refactor có thể không được trình biên dịch phát hiện nếu đổi tên accessor.
- Runtime SpEL evaluation có overhead.
- Rule dài khó test/debug hơn code Java thông thường.
- Điều kiện có thể phụ thuộc trạng thái bên ngoài, làm mất tính deterministic.

### 7.2. Guard bằng Java

Một handler có guard:

```java
@EventListener
public void on(OrderPlaced event) {
    if (event.totalCents() < 100000) {
        return;
    }
    // Logic cho đơn lớn.
}
```

Ưu điểm:
- Java compiler kiểm tra kiểu và tên method.
- Dễ đặt breakpoint, viết unit test và dùng domain service.
- Phù hợp khi rule có nhiều bước, cần giải thích vì sao bị loại hoặc tạo metric theo decision.

Nhược điểm:
- Method vẫn được gọi với mọi event cùng type.
- Logic guard lặp ở nhiều handler có thể làm code rối nếu không trích thành policy đúng tầng.

### 7.3. Tạo một event type chuyên biệt

Nếu nghiệp vụ thực sự có fact **OrderFlaggedForManualReview** sau khi một policy service đã phân tích order, cân nhắc phát event chuyên biệt:

```java
public record OrderFlaggedForManualReview(
    String eventId, String orderId, String reasonCode
) {}
```

Đây là một fact khác với `OrderPlaced`. Consumer chỉ cần listen theo type, không tự đánh giá lại cùng business policy trong nhiều callback. Khi event có ý nghĩa domain mới, type chuyên biệt giúp phân quyền, audit, versioning và testing rõ ràng hơn.

**Không tạo hàng chục event classes chỉ để thay mỗi biểu thức so sánh một trường nhỏ** nếu điều đó không phản ánh sự kiện nghiệp vụ riêng.

### Bảng quyết định

| Trường hợp | Phương án nên cân nhắc |
| --- | --- |
| Kiểm tra field/enum/ngưỡng rất đơn giản | `@EventListener(condition=...)` |
| Rule phức tạp, cần unit test và lý do từ chối | Java guard / domain policy service |
| Event là một fact nghiệp vụ mới | Event type riêng |
| Lọc cả loại event rất rộng | Type-specific listener trước, condition chỉ là lớp sau |
| Điều kiện cần database/network hoặc external API | Không làm trong SpEL condition; đưa vào handler/service có transaction/error handling |
| Kiểm tra quyền người dùng, tenant, dữ liệu nhạy cảm | Authorization ở service/consumer boundary; condition không đủ |
| Lọc trong broker/SQL để giảm traffic | Cơ chế broker subscription/filter hoặc query ở tầng đó, không phải Spring condition |

## 8. @TransactionalEventListener có condition: cần hiểu thời điểm

Spring hỗ trợ condition cho listener gắn transaction:

```java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    condition = "#a0.totalCents() >= 100000"
)
public void onCommittedHighValueOrder(OrderPlaced event) {
    // Thực hiện side effect sau khi transaction commit.
}
```

Đây là **đoạn tích hợp** cần transaction manager, service thực sự publish event trong transaction và các import `@TransactionalEventListener`, `TransactionPhase`.

Hai khía cạnh độc lập:
- **Condition** xác định callback có phù hợp với event cụ thể không.
- **Transaction phase** xác định khi nào callback đủ điều kiện chạy dựa trên kết quả transaction.

Nếu transaction rollback, listener `AFTER_COMMIT` không chạy dù điều kiện trên payload là true. Nếu publish ngoài transaction và `fallbackExecution=false` mặc định, listener transaction-bound thường không chạy.

**Đừng đánh đồng condition true với “đã commit”.** Biểu thức dựa vào snapshot event, không thay thế transaction lifecycle. Và `AFTER_COMMIT` không biến event in-memory thành một queue bền vững: nếu process crash sau DB commit trước callback, side effect vẫn có thể mất.

### Condition không bảo đảm dữ liệu sau commit vẫn giống lúc publish

Một event mutable hoặc tham chiếu JPA managed entity có thể thay đổi trước khi callback chạy. Điều kiện đọc state mutable lúc đánh giá và body đọc state ở thời điểm khác dễ tạo **TOCTOU**. Hãy dùng immutable snapshot trong event hoặc truy vấn authoritative state trong handler theo contract, đặc biệt khi listener chạy sau commit/async.

Khi công việc quan trọng phải được giao lại nếu crash, lưu durable outbox/job trong cùng DB transaction thay vì chỉ dùng `@TransactionalEventListener(AFTER_COMMIT)`.

## 9. @Async và điều kiện: ranh giới thực thi

Một phương thức có thể kết hợp:

```java
@Async("eventExecutor")
@EventListener(condition = "#a0.channel() == 'WEB'")
public void onWebOrderAsync(OrderPlaced event) {
    // ...
}
```

Đây là **mẫu tích hợp** yêu cầu `@EnableAsync`, executor tên `eventExecutor`, listener Spring bean và method được gọi qua async proxy. Khi một method được Spring áp dụng async proxy, công việc body có thể chạy trên thread pool, trong khi multicaster dispatch theo cơ chế của nó. Không mặc định mọi đoạn SpEL và mọi body đều được thực thi trên cùng một thread nếu cấu hình thay đổi; chi phí dispatch/condition cần đo theo **đường chạy thực tế**.

Các điểm cần nhớ:
- `publishEvent()` có thể trả về trước khi handler async kết thúc.
- `condition=false` nghĩa callback body không được chạy, nhưng không tự tạo thông báo “đã bị lọc” để monitoring.
- Nếu một listener dùng executor riêng, cần cấu hình `TaskDecorator`/context propagation trên đúng executor.
- `SecurityContextHolder` và MDC mặc định thread-bound trong stack servlet, không tự đi theo task.
- Exception của `@Async void` không tự quay trở lại publisher; dùng `AsyncUncaughtExceptionHandler`, logging/metrics hoặc tín hiệu test.
- Không dùng `Thread.sleep(...)` rồi assert kết quả; dùng `CountDownLatch`, `CompletableFuture` hoặc Awaitility với timeout.

**Đặc biệt:** nếu condition thật sự phụ thuộc vào transaction/session/security context tại runtime, hãy thiết kế và test execution boundary, thay vì để biểu thức SpEL gọi vào những ThreadLocal có thể không còn tồn tại.

## 10. @Order, nhiều listener và tính độc lập

Hai listener có condition true trên cùng event **có thể đều chạy**:

```java
@EventListener(condition = "#a0.totalCents() >= 100000")
public void sendHighValueAlert(OrderPlaced event) {
    // ...
}

@EventListener(condition = "#a0.channel() == 'WEB'")
public void updateWebDashboard(OrderPlaced event) {
    // ...
}
```

Với ORD-3 trong demo, cả hai method đều được chọn, không phải `else if`. Spring multicast là fan-out: condition không có cơ chế “listener đầu tiên thắng”.

Nếu thực sự cần một trong hai nhánh độc quyền, mô hình hóa policy/dispatch ở một tầng duy nhất hoặc phân biệt event type; **đừng dựa vào thứ tự listener** và kỳ vọng cái sau không được chạy.

`@Order` có thể giúp Spring xác định thứ tự invocation cho listeners đồng bộ, nhưng không bảo đảm thứ tự **hoàn tất** khi listener chạy bất đồng bộ. Không dùng `@Order` thay cho một saga/workflow có dependency hoặc transaction atomicity.

### Trường hợp các listener trả về event khác

Spring `@EventListener` có thể sử dụng giá trị trả về từ method để phát tiếp event (theo contract hỗ trợ của Spring). Khi condition false, method không chạy nên không tạo event trả về; khi condition true, fan-out có thể bao gồm event phát tiếp. Với `@Async`, việc tự động publish event từ return value không được hỗ trợ như listener sync; thay bằng `ApplicationEventPublisher` tường minh nếu cần.

Chú ý vòng lặp event: một listener nhận event A rồi phát event A mới liên tục có thể tạo recursion/queue storm. Condition giúp chọn callback, **không tự bảo vệ khỏi vòng lặp**, duplicate hoặc retry vô hạn.

## 11. Hiệu năng: condition không miễn phí

Cần phân biệt `N` listener đăng ký, `K` listener **phù hợp theo type**, và `M` listener **qua condition**:

```text
N tổng listener beans/adapters
    |
    +-- Chọn theo event type/source --> K candidates
                                         |
                                         +-- SpEL condition true --> M handlers
                                         +-- SpEL condition false -> skipped methods
```

Khi ứng dụng publish rất nhiều event, chi phí có thể gồm:
- Spring tìm danh sách listeners phù hợp theo event type/source.
- Adapter đánh giá expression SpEL cho event phù hợp.
- Reflection/proxy/argument resolution.
- Executor submission (nếu async).
- Business handler, logging/tracing/metrics.
- I/O tới DB, API, cache và broker.

Ở Spring, kết quả tìm listener theo type có cơ chế cache trong `AbstractApplicationEventMulticaster` cho những trường hợp phù hợp. **Cache type-selection không có nghĩa condition result được cache theo từng event instance.** Giá trị `totalCents()` và `channel()` có thể khác ở mỗi event nên điều kiện cần được đánh giá theo event.

Ví dụ **điều kiện không nên dùng**:

```java
@EventListener(
    condition = "@orderRepository.isEligible(#a0.orderId())"
)
public void notifyEligibleOrder(OrderPlaced event) {
    // ...
}
```

Đây là **anti-pattern minh họa**, giả sử một bean repository tồn tại. SpEL cho phép bean reference và method invocation theo cấu hình evaluation context, nhưng gọi DB trong expression sẽ:
- Làm khó thấy I/O, timeout, retries và transaction scope;
- Có thể chạy cho rất nhiều event, kể cả khi handler method không chạy;
- Khi lỗi có thể chặn dispatch trong sync multicaster;
- Làm condition khó kiểm thử và phụ thuộc state ngoài;
- Che business authorization trong một chuỗi annotation khó audit.

Thay vào đó, cho handler gọi domain service/policy với error handling và transaction rõ; hoặc phát event fact chuyên biệt sau khi service đã kiểm tra điều kiện cần thiết.

### Đo hiệu năng đúng tầng

Có thể đo:
- `publishEvent` duration cho đường sync/handoff.
- `listener.execution.duration` cho method body.
- `event.condition.rejected.count` nếu thật sự cần biết số event bị lọc — phải instrument có chủ đích, vì Spring không tự tạo metric này cho mọi condition.
- Queue wait / executor rejection nếu có async.

Không dùng `eventId`, `orderId` hoặc `correlationId` làm metric tag vì cardinality lớn. Dùng tag hữu hạn như `eventType`, `listener`, `outcome`. Nếu muốn benchmark overhead SpEL, dùng JMH hoặc profiling có warmup với listener no-op; không đo một lần bằng `System.nanoTime()` rồi kết luận framework “chậm”.

## 12. Bảo mật và dữ liệu: condition không phải authorization

Một biểu thức như:

```java
@EventListener(condition = "#a0.tenantId() == 'tenant-A'")
public void exportCustomerData(CustomerExportRequested event) {
    // Đây KHÔNG phải kiểm tra quyền.
}
```

không xác nhận:
- Event có đến từ application service đã kiểm tra principal không;
- `tenantId` có bắt nguồn từ record đáng tin hay do client tự đặt;
- Người dùng có quyền xuất **đúng dữ liệu** đang được yêu cầu không;
- Quyền còn hiệu lực khi listener chạy sau đó không;
- Dữ liệu có được gửi tới recipient đã được kiểm tra không.

Một bean trong cùng context có thể tạo object event và publish trực tiếp; `@EventListener` là routing mechanism, **không phải security boundary**. Với tác vụ nhạy cảm, đặt authentication và object-level authorization tại service boundary, đồng thời listener/worker xác minh intent/aggregate/tenant phù hợp từ nguồn authoritative.

`eventId`, `actorId`, `correlationId` và `tenantId` là metadata, không phải credentials. Không đưa access token hoặc full Spring Security `Authentication` vào event để dùng sau khi request kết thúc. Chỉ truyền dữ liệu tối thiểu, bảo vệ PII trong event/outbox/log/trace, và định nghĩa retention.

Một cách xem condition an toàn: nó là **tối ưu chọn callback nhỏ**, còn logic tin cậy và security vẫn ở service/consumer có trách nhiệm.

## 13. Error handling khi biểu thức hoặc handler lỗi

Điều kiện có thể fail vì:
- Viết sai tên accessor: `#a0.totalCent()` thay vì `totalCents()`.
- Mẫu biểu thức sai cú pháp hoặc nháy chuỗi không hợp lệ.
- Giá trị null nhưng gọi method trên null.
- Sai event type hoặc kỳ vọng `#root.event` là payload.
- Method/bean được gọi từ expression ném exception.
- Điều kiện dựa vào context không tồn tại ở thread hiện tại.

Khi SpEL đánh giá lỗi, đó là **lỗi runtime** của đường xử lý event, không có nghĩa “condition=false” và bỏ qua an toàn trong mọi trường hợp. Với multicast đồng bộ và không có error handler suppress, exception có thể propagate về publisher. Với async, lỗi có thể đến cơ chế `ErrorHandler`/executor/async uncaught exception handling. Phải test thực tế theo cấu hình.

Nếu một listener khác đã xử lý event trước khi listener lỗi, retry cả `publishEvent(event)` có thể khiến handler trước bị gọi lại. Với side effect quan trọng, dùng stable event ID, idempotency và durable work theo yêu cầu. Không coi condition false/error là acknowledgment thành công của một workflow.

### Sai condition có thể làm mất dữ liệu quan trọng

Nếu `condition` viết `> 100000` thay vì `>= 100000`, các đơn đúng ngưỡng sẽ không được handler xử lý. Đây là lỗi nghiệp vụ có thể **âm thầm bị bỏ qua**. Vì thế, test cả boundary, null, enum/chuỗi và dữ liệu không hợp lệ thay vì chỉ test một giá trị hiển nhiên.

Với handler thực hiện nghiệp vụ bắt buộc, nên có kiểm soát bền vững/reconciliation, không dựa duy nhất vào một expression annotation khó quan sát.

## 14. Kiểm thử listener có condition

### 14.1. Test happy path theo bảng chân trị

Với demo mục 5:
1. Publish `ORD-1(50000, WEB)` → all + web; không high.
2. Publish `ORD-2(150000, POS)` → all + high; không web.
3. Publish `ORD-3(200000, WEB)` → all + high + web.
4. Assert `ALL=[ORD-1, ORD-2, ORD-3]`, `HIGH=[ORD-2, ORD-3]`, `WEB=[ORD-1, ORD-3]`.

Nếu test gọi thẳng `listeners.onHighValueOrder(event)` bằng Java, bạn đang **bypass Spring event adapter**: method body sẽ chạy bất kể `condition`! Muốn kiểm tra annotation condition, phải publish event qua `ApplicationEventPublisher` trong một Spring context có listener được đăng ký.

### 14.2. Test giá trị biên

Thêm:
- Tổng tiền `99999`: condition high-value false.
- Tổng tiền `100000`: condition high-value true.
- Tổng tiền `100001`: true.
- Channel `WEB` đúng chữ hoa: true.
- Channel `web` chữ thường: false với expression equality hiện tại.
- Channel `null`: equality với `'WEB'` false, nhưng cần chính sách validation nếu channel bắt buộc.

Tránh chọn test chỉ có `200000` rồi bỏ quên chính ngưỡng `100000`.

### 14.3. Test failure của expression

Tạo một listener test riêng với condition cố tình truy cập accessor không tồn tại, publish event qua Spring context và xác minh error behavior trong **cấu hình đã chọn**. Không đưa listener lỗi đó vào cùng context với test chạy bình thường rồi làm toàn bộ suite fail không rõ nguyên nhân.

Nếu handler được chuyển sang async, đừng dùng `assertThrows` quanh publisher rồi kết luận không có lỗi. Hãy chờ `ErrorHandler`/`AsyncUncaughtExceptionHandler` hoặc test signal phù hợp.

### 14.4. Test condition và transaction

Với `@TransactionalEventListener(AFTER_COMMIT, condition=...)`:
- Publish event đúng condition **trong transaction thật**, commit, rồi assert handler được gọi.
- Publish event đúng condition nhưng rollback, assert handler AFTER_COMMIT không được gọi.
- Publish event false condition và commit, assert handler không được gọi.
- Publish event ngoài transaction với fallback mặc định, assert không được gọi.

Đừng chỉ dùng `@Transactional` ở Spring Test rồi mong AFTER_COMMIT chạy, vì nhiều integration tests tự rollback cuối method. Dùng `TransactionTemplate`/`TestTransaction` để chủ động commit theo contract.

### 14.5. Test async không flaky

Khi multicaster/`@Async` dùng executor:
- Publish event với ID riêng.
- Dùng `CountDownLatch` hoặc `CompletableFuture` đặt theo `eventId` để chờ đúng handler.
- Với condition true, chờ completion signal rồi assert kết quả.
- Với condition false, để kiểm thử “không được gọi”, cần mốc đảm bảo mọi work liên quan đã qua dispatcher/queue hoặc thiết kế harness có sentinel; không khẳng định không gọi chỉ vì đợi 100 ms.
- Dọn executor và context sau test; không để worker test trước rò sang test sau.

## 15. Checklist thực hành

- [ ] Phân biệt rõ type selection, condition SpEL và business guard trong method.
- [ ] Listener method có parameter type đúng event dự kiến.
- [ ] Dùng `#a0`/`#p0`/`#root.args[0]` khi muốn độc lập tên parameter.
- [ ] Biểu thức trả boolean, dùng đúng nháy chuỗi và toán tử SpEL.
- [ ] Test giới hạn `>=` / `>` và case-sensitive channel.
- [ ] Condition ngắn, thuần, không gọi DB/network hoặc thay đổi state.
- [ ] Không dùng SpEL condition làm nơi chứa authorization hay domain invariant phức tạp.
- [ ] Không tin `#root.event` luôn là POJO payload với mọi loại event.
- [ ] Không dùng condition để âm thầm bỏ qua event lỗi nghiêm trọng.
- [ ] Với nhiều listener, hiểu điều kiện độc lập, có thể đồng thời true.
- [ ] Khi dùng async, biết executor, error handler và completion signal.
- [ ] Khi dùng transactional listener, kiểm tra commit/rollback thật.
- [ ] Event payload bất biến, không chứa managed entity/trạng thái ThreadLocal mutable.
- [ ] Có metrics/logging cho outcome của handler quan trọng, không dùng high-cardinality tags.
- [ ] Test condition qua `publishEvent` trong Spring context, không chỉ gọi trực tiếp method.
- [ ] Nếu side effect không được phép mất, thiết kế outbox/job/retry/idempotency thay cho chỉ condition.

## 16. Bài tập tổng kết

**Bài tập 1 — điều kiện kép.** Từ demo, thêm một method `onHighValueWebOrder` có condition:

```java
@EventListener(
    condition = "#a0.totalCents() >= 100000 and #a0.channel() == 'WEB'"
)
```

Kỳ vọng chỉ ORD-3 được thêm vào danh sách của listener mới. Test thêm ORD-5 có giá trị đúng ngưỡng, channel APP để chứng minh điều kiện phải thỏa **cả hai nhánh**.

**Bài tập 2 — giới hạn.** Dùng cùng listener high-value nhưng publish `99999`, `100000`, `100001`, assert chỉ hai giá trị cuối được xử lý.

**Bài tập 3 — refactor.** Giả sử một điều kiện SpEL phải gọi DB để xác định khách hàng thuộc nhóm VIP. Chuyển rule sang policy service trong handler hoặc ứng dụng phát một fact chuyên biệt sau khi tính điều kiện. Viết unit test cho policy và integration test cho listener registration.

**Bài tập 4 — transaction.** Thêm `@TransactionalEventListener(AFTER_COMMIT)` với condition đơn lớn. Test bốn nhánh: commit-true, commit-false, rollback-true, no-transaction. Đảm bảo không nhầm điều kiện với phase.

**Bài tập 5 — async.** Chuyển demo sang `ThreadPoolTaskExecutor` có queue hữu hạn. Thay `ArrayList` bằng concurrent structures, dùng `CountDownLatch` để chờ, kiểm tra stdout cuối không phụ thuộc timing, test error handler và shutdown.

**Bài tập 6 — security.** Một người dùng gửi payload `tenantId=tenant-B` từ tenant-A. Hãy giải thích vì sao `condition="#a0.tenantId() == 'tenant-B'"` không phải check quyền; thay vào đó, thêm authorization tại application service và tenant-scoped query.

### Câu hỏi tự kiểm tra

1. `condition=false` có ngăn `publishEvent` phát event cho **mọi** listener không? **Không.** Nó chỉ ngăn callback tương ứng.
2. `#a0` chỉ tới đâu? **Tham số đầu tiên** của listener method.
3. `@EventListener(condition=...)` có thay type matching không? **Không.** Nó là lớp lọc sau khi listener đã phù hợp kiểu.
4. Trong async multicaster, `publishEvent` trả về có nghĩa listener đã xong không? **Không nhất thiết.**
5. `@TransactionalEventListener(AFTER_COMMIT, condition=true)` có chạy khi transaction rollback không? **Không.**
6. Condition SpEL có được xem là authorization boundary không? **Không.**
7. Làm thế nào để chứng minh annotation condition hoạt động? **Publish qua Spring ApplicationContext** và assert listener được/không được gọi đúng dữ liệu.
8. Cache listener type-selection có cache cả kết quả condition cho mọi event không? **Không nên giả định; condition phụ thuộc dữ liệu mỗi event.**

**Kết luận:** `@EventListener(condition = "...")` là công cụ gọn cho việc **lọc callback theo dữ liệu event** khi rule nhỏ, rõ, thuần và dễ kiểm thử. Nó kết hợp với type selection của Spring nhưng không thay thế authorization, transaction, reliability hay business policy. Với hệ thống quan trọng, hãy dùng domain event đúng ngữ nghĩa, payload bất biến, error handling, idempotency và integration tests cho các nhánh điều kiện/transaction/async.

## Tài liệu tham khảo

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.1.21 — EventListener annotation API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework — SpEL Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
- [Spring Framework 6.1.21 — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.1.21 — AbstractApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/AbstractApplicationEventMulticaster.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework 6.1.21 — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
