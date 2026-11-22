# Một event một ý nghĩa nghiệp vụ trong thiết kế domain event

## 1. Nguyên tắc cốt lõi

Trong thiết kế domain event, **một event type nên diễn đạt một sự thật nghiệp vụ rõ ràng, có thể đặt tên, kiểm chứng và giải thích độc lập**. Sự thật ấy đã xảy ra trong domain; các consumer có thể phản ứng với nó, nhưng event không phải là lời yêu cầu consumer phải làm một việc nào đó.

Ví dụ trong hệ thống bán hàng:

- `OrderPlaced`: đơn hàng đã được tiếp nhận theo quy tắc của domain.
- `PaymentCaptured`: khoản tiền đã được thu thành công.
- `ShipmentDispatched`: kiện hàng đã được bàn giao để vận chuyển.

Ba mệnh đề này có **điều kiện đúng khác nhau** và có thể xảy ra ở ba thời điểm khác nhau. Việc một đơn đã được đặt **không** nhất thiết có nghĩa đã thu tiền; việc đã thu tiền **không** nhất thiết có nghĩa hàng đã được gửi đi.

Một event tốt cho phép người đọc hoàn thành câu: “**Điều gì đã xảy ra trong nghiệp vụ?**” mà không cần mở một chuỗi `if (action == ...)` hay giải mã một túi dữ liệu chung.

> **Một ý nghĩa không có nghĩa một listener, một field, một aggregate, một database row hoặc một event trên mỗi thao tác kỹ thuật.** Một `OrderPlaced` có thể được nhiều listener cùng xử lý. Một thao tác nghiệp vụ cũng có thể làm phát sinh nhiều sự thật, nếu các sự thật đó thật sự độc lập.

Nguyên tắc này tập trung vào **ngữ nghĩa** hơn là số lượng class Java. Mục tiêu là giúp event contract phản ánh đúng ngôn ngữ và bất biến nghiệp vụ, không tạo nhiều class cho đẹp.

## 2. Phân biệt event với command và CRUD notification

| Dạng thông điệp | Câu hỏi nó trả lời | Ví dụ | Bản chất |
| --- | --- | --- | --- |
| **Domain event** | Điều gì đã xảy ra và đã trở thành sự thật trong domain? | `PaymentCaptured` | Fact ở quá khứ |
| **Command** | Hệ thống cần cố gắng thực hiện việc gì? | `CapturePayment` | Ý định/yêu cầu; có thể bị từ chối |
| **Query** | Cần biết dữ liệu nào? | `FindOrderStatus` | Yêu cầu đọc thông tin |
| **CRUD/technical notification** | Dữ liệu/kỹ thuật vừa thay đổi thế nào? | `OrderRowUpdated`, `CacheInvalidated` | Sự kiện hạ tầng, chưa chắc là fact nghiệp vụ |

Không nên đặt tên `SendWelcomeEmailEvent` nếu thực chất thông điệp dùng để **ra lệnh gửi email**. Khi event diễn đạt `CustomerRegistered`, nhiều consumer độc lập có thể quyết định gửi email, cấp ưu đãi hoặc ghi audit theo quy tắc của riêng chúng.

Cũng không nên đồng nhất `OrderUpdated` với `OrderCancelled`. Cập nhật dữ liệu là khái niệm rộng; hủy đơn là một chuyển trạng thái nghiệp vụ có điều kiện và hậu quả đặc thù.

Một domain event được phép là event quan trọng về **trạng thái thất bại**. Chẳng hạn `PaymentDeclined` có thể là sự thật nếu domain lưu nhận quyết định từ chối thanh toán. Nhưng `PaymentCaptureRequested` và `PaymentCaptured` khác nhau: một cái nói yêu cầu đã được tiếp nhận, cái kia nói tiền đã thật sự được thu.

### Lời phát biểu trước khi đặt tên

Thử viết event dưới dạng một câu khẳng định:

- “Đơn `O-42` đã được chấp nhận vào lúc T” → `OrderPlaced`.
- “Thanh toán `P-7` của đơn `O-42` đã được thu 125.000 VND” → `PaymentCaptured`.
- “Hệ thống phải gửi hóa đơn” → **command/work item**, chưa phải sự thật hóa đơn đã phát hành.
- “Trạng thái bảng orders đổi từ X sang Y” → sự kiện kỹ thuật; cần hỏi liệu có mốc nghiệp vụ tương ứng hay không.

Nếu phải thêm câu “trừ khi `kind=...` thì ý nghĩa hoàn toàn khác”, rất có thể một event type đang gánh nhiều ý nghĩa.

## 3. Ví dụ phản thiết kế: một event chung cho mọi thay đổi

Một cách viết thường gặp:

```java
// Minh họa phản thiết kế, không phải chương trình chạy độc lập.
public record OrderEvent(
        String orderId,
        String action,
        Map<String, Object> payload) {
}

@EventListener
public void onOrderEvent(OrderEvent event) {
    if ("PLACED".equals(event.action())) {
        sendWelcomeMessage(event.orderId());
    } else if ("PAID".equals(event.action())) {
        updatePaymentLedger(event.payload());
    } else if ("CANCELLED".equals(event.action())) {
        releaseInventory(event.orderId());
    }
}
```

Vấn đề không phải cú pháp `record` hay `Map` tự thân có lỗi. Vấn đề là kiểu `OrderEvent` **không nói một sự thật cụ thể**; ý nghĩa nằm ở chuỗi `action` và cấu trúc `payload` thay đổi theo nhánh.

Hậu quả:

1. **Không kiểm tra được bằng kiểu dữ liệu**: nhánh `PAID` cần `paymentId` và `amount`, nhưng compiler không bắt buộc các field đó tồn tại.
2. **Người tiêu thụ phải hiểu mọi biến thể**: consumer chỉ quan tâm việc thu tiền vẫn phải biết một kiểu tổng quát và kiểm tra `action`.
3. **Khó đổi schema độc lập**: thay đổi payload của nhánh `CANCELLED` có thể ảnh hưởng code hoặc test dùng chung của `OrderEvent`.
4. **Tên event và log quá mơ hồ**: chỉ nhìn “OrderEvent received” không biết đã xảy ra chuyện gì.
5. **Dễ biến event thành command router**: một listener trung tâm điều khiển các hành động theo `action`, làm tăng coupling.
6. **Bộ kiểm tra hợp lệ phân tán**: mỗi nhánh phải tự hỏi field nào bắt buộc, trạng thái nào có thể xảy ra.

Một thiết kế tốt hơn nếu chúng là ba sự thật khác nhau:

```java
public record OrderPlaced(
        String orderId,
        Instant occurredAt) {}

public record PaymentCaptured(
        String orderId,
        String paymentId,
        long amountMinor,
        String currency,
        Instant occurredAt) {}

public record OrderCancelled(
        String orderId,
        String reasonCode,
        Instant occurredAt) {}
```

Đây là **các khai báo kiểu minh họa**; để biên dịch cần import `java.time.Instant`, và có thể bổ sung các quy tắc xác thực domain. Mỗi event có payload phù hợp với fact của riêng nó; không cần các nhánh dựa trên `action`.

**Không phải mọi thuộc tính biến đổi đều cần event riêng.** Nếu người dùng đổi độ rộng cột trong màn hình cá nhân, `UserPreferencesChanged` có thể đủ hoặc không cần domain event. Không nhất thiết tạo `UserTableColumnWidthChanged` trừ khi đó là một điều có giá trị nghiệp vụ cần nhận diện riêng.

## 4. “Một ý nghĩa” không có nghĩa “một event cho mỗi chi tiết”

Đây là điểm cân bằng quan trọng nhất.

### 4.1. Một event có thể có nhiều dữ liệu

`PaymentCaptured` có thể mang `paymentId`, `orderId`, số tiền, đơn vị tiền tệ, thời điểm và định danh event. Chúng là **dữ liệu mô tả cùng một sự thật**: khoản thanh toán được thu.

Không cần bẻ thành:

- `PaymentAmountRecorded`,
- `PaymentCurrencyRecorded`,
- `PaymentIdAssigned`,

nếu ba giá trị đó chỉ là các thuộc tính của **một kết quả nghiệp vụ nguyên vẹn**.

### 4.2. Một event có thể có nhiều consumer

`OrderPlaced` có thể được nhận bởi audit, analytics, recommendation và notification. Số consumer không quyết định số event types; việc chia thành `OrderPlacedForAudit` và `OrderPlacedForAnalytics` chỉ để phục vụ từng consumer thường làm méo ngôn ngữ domain và tạo dư thừa.

### 4.3. Một transaction có thể chứa nhiều fact

Nếu một workflow xác lập hai mốc nghiệp vụ khác nhau, nó có thể sinh hai event. Nhưng **không được phát hai fact chỉ vì code đang gọi hai repository**: phát event phải dựa trên business invariants thật sự đã đạt, không dựa trên số câu lệnh SQL.

### 4.4. Một event tổng hợp có thể hợp lệ

`CheckoutCompleted` có thể có một ý nghĩa riêng nếu domain quy định “checkout hoàn thành” là **một milestone được xác nhận duy nhất** sau khi mọi điều kiện cần thiết thỏa mãn. Event đó không nhất thiết sai chỉ vì có các bước đặt đơn, xử lý thanh toán và giữ hàng ở phía dưới.

Nhưng nếu `CheckoutCompleted` được phát ngay lúc bắt đầu checkout, hoặc payload chứa các cờ `paid/cancelled/shipped` với nhiều tổ hợp mâu thuẫn, đó là dấu hiệu ý nghĩa chưa được xác định rõ.

**Câu hỏi quyết định không phải “bao nhiêu field?” mà là “điều gì vừa trở thành đúng?”**

## 5. Tiêu chí quyết định tách event thành kiểu riêng

Một checklist để xem hai sự việc có nên là hai event types:

| Câu hỏi | Nếu câu trả lời “Có” | Hướng thiết kế |
| --- | --- | --- |
| Chúng có thể xảy ra **độc lập** không? | Đặt đơn thành công nhưng thu tiền chưa thành công | Tách `OrderPlaced` và `PaymentCaptured` |
| Chúng có **thời điểm** xảy ra khác nhau không? | Thanh toán xử lý sau khi nhận đơn | Tách để thời điểm event trung thực |
| Chúng có **điều kiện đúng/bất biến** khác nhau không? | “Đơn hợp lệ” khác “tiền đã thu” | Tách |
| Chúng có **payload bắt buộc** khác nhau không? | Thu tiền cần `paymentId/amount` | Thường tách |
| Chúng có **owner/bounded context** khác nhau không? | Ordering xác nhận đơn; Payments xác nhận capture | Dùng sự kiện phù hợp với ngữ cảnh; cân nhắc translation/integration event |
| Consumer cần **chính sách xử lý/lỗi** khác nhau không? | Audit của đặt đơn vs settlement của thanh toán | Đây là dấu hiệu hỗ trợ, không phải tiêu chí duy nhất |
| Chúng cần được **version và phát triển độc lập** không? | Thanh toán bổ sung provider metadata riêng | Tách nếu ngữ nghĩa cũng độc lập |
| Một type có nhiều giá trị `action/type/status` làm đổi hẳn fact không? | PLACED, CANCELLED, REFUNDED | Thường tách theo sự thật |
| Có một **milestone chung** được domain công nhận rõ không? | CheckoutCompleted có điều kiện hoàn tất xác định | Có thể giữ event milestone riêng |

Không tách chỉ vì:

- Hai listener xử lý hai việc khác nhau.
- Một payload chứa nhiều thuộc tính.
- Team muốn ít điều kiện `if` mà chưa hiểu nghiệp vụ.
- Mỗi trường của entity vừa được chỉnh sửa.
- Một tên event dài hơn một giới hạn ký tự tùy ý.

### Ví dụ về sự thật và trạng thái

Các event `OrderPlaced`, `OrderCancelled` và `OrderShipped` phản ánh **chuyển mốc nghiệp vụ**. Một enum `OrderStatus` bên trong aggregate có thể mô tả trạng thái hiện tại, nhưng **không thay thế tự động** cho thông tin “điều gì đã xảy ra” và “khi nào”.

Ví dụ: trạng thái hiện tại là `SHIPPED` không đủ để suy ra đã thu tiền lúc nào, hay đã từng hủy rồi phục hồi hay không. Mô hình nghiệp vụ phải định nghĩa các điều đó; không suy ra event từ trạng thái cuối một cách tùy tiện.

## 6. Đặt tên event bằng ngôn ngữ nghiệp vụ

Tên nên giúp domain expert hiểu mà không phải biết tên bảng hay API Java. Một quy ước phổ biến là **danh từ nghiệp vụ + động từ ở dạng đã xảy ra**, chẳng hạn:

| Tên gợi ý | Câu khẳng định | Lưu ý |
| --- | --- | --- |
| `OrderPlaced` | Đơn đã được tiếp nhận | Cần định nghĩa “placed” cụ thể trong domain |
| `PaymentAuthorized` | Khoản tiền đã được cho phép giữ/ủy quyền | **Khác** với đã thực sự thu |
| `PaymentCaptured` | Khoản tiền đã được thu | Đừng dùng khi mới gửi yêu cầu thu |
| `PaymentDeclined` | Kết quả yêu cầu bị từ chối | Có ý nghĩa nếu domain lưu/quan tâm đến kết quả này |
| `ShipmentDispatched` | Hàng đã bàn giao cho vận chuyển | Khác với “đã giao đến người nhận” |
| `SubscriptionRenewed` | Kỳ đăng ký đã được gia hạn | Cần định nghĩa có bao gồm thành công thanh toán không |

Một số tên cần cảnh giác:

- `OrderChanged`: quá rộng nếu chứa nhiều nghiệp vụ khác nhau.
- `DoPayment`: command/động tác phải làm, chưa là fact.
- `SaveOrderCompleted`: mô tả bước lưu trữ, chưa chắc là ngôn ngữ domain.
- `EverythingDone`: không có điều kiện đúng cụ thể.
- `OrderPlacedAndEmailSent`: ghép hai việc độc lập trừ khi đó chính là milestone được domain định nghĩa.
- `EntityUpdatedEvent`: tiện về hạ tầng, khó dùng như business contract.

**Không có từ vựng chuẩn cho mọi tổ chức.** Ví dụ “order placed” có thể nghĩa là đơn đã nộp nhưng chưa được duyệt ở một domain, còn ở domain khác là đã chấp nhận và giữ hàng. Cần thống nhất trong ubiquitous language với domain experts; tên giống nhau không bảo đảm semantics giống nhau.

## 7. Payload: mang đủ dữ kiện để giải thích sự thật

Một event hữu dụng có thể chứa:

- **Event identity**: `eventId`, giúp chẩn đoán và chống xử lý lặp ở hệ thống phân phối có retry.
- **Business identity**: `orderId`, `paymentId` hoặc mã của aggregate liên quan.
- **Occurred time**: `occurredAt` là mốc nghiệp vụ, phân biệt với thời điểm consumer nhận event.
- **Dữ liệu cốt lõi của sự thật**: số tiền đã thu, mã currency, lý do hủy, trạng thái được xác nhận theo hợp đồng nghiệp vụ.
- **Causation/correlation** khi cần truy vết: action hoặc event nào dẫn đến sự kiện này, workflow nào liên kết các bước.
- **Version của contract** nếu event vượt ranh giới triển khai/lưu trữ và cần evolve schema có kiểm soát.

Không cần chép nguyên entity hoặc tất cả trường từ database vào event. Một snapshot lớn có thể vô tình lộ PII, làm consumer phụ thuộc model nội bộ và gây lỗi khi entity còn tiếp tục thay đổi.

Ví dụ một Java record bất biến về mặt cấu trúc:

```java
public record PaymentCaptured(
        UUID eventId,
        String paymentId,
        String orderId,
        long amountMinor,
        String currency,
        Instant occurredAt) {

    public PaymentCaptured {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(paymentId, "paymentId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(currency, "currency");
        Objects.requireNonNull(occurredAt, "occurredAt");
        if (amountMinor <= 0) {
            throw new IllegalArgumentException("amountMinor must be positive");
        }
    }
}
```

Đây là **khai báo minh họa**; cần import `java.util.UUID`, `java.util.Objects` và `java.time.Instant`. `amountMinor` là số đơn vị nhỏ nhất của tiền tệ theo hợp đồng ứng dụng (ví dụ cents nếu dùng USD). Với VND, cần định nghĩa rõ hệ thống dùng đơn vị gì. Không chuyển tùy tiện số thập phân tiền tệ thành `double` để tránh sai số.

Record giúp giảm nguy cơ sửa field sau khi tạo nhưng **không tự làm cho mọi object tham chiếu trong record bất biến**. Nếu payload có `List`, `Map` hoặc đối tượng mutable, cần copy bất biến và kiểm soát schema. Không đưa thông tin nhạy cảm vào `toString()` rồi log toàn bộ event.

### Dữ liệu tối thiểu hay đầy đủ?

Có hai chiến lược phổ biến:

1. **Notification-style**: chỉ mang định danh và mốc; consumer truy vấn dữ liệu cần thiết. Đơn giản, nhưng coupling vào query API, nguy cơ đọc trạng thái **mới hơn** sự thật lúc event phát và khó xử lý offline.
2. **Event-carried state**: mang dữ liệu cần thiết để consumer xử lý fact mà không truy vấn đồng bộ. Tăng độ tự chủ nhưng cần thiết kế schema, phân quyền và version cẩn thận.

Lựa chọn phụ thuộc boundary và nhu cầu consumer. Dù dùng chiến lược nào, ý nghĩa của event vẫn phải được giữ nguyên.

## 8. Ví dụ Spring Framework 6.2 với Java 17: hai ý nghĩa, nhiều listener

Ví dụ chạy độc lập sau minh họa:

- `OrderPlaced` và `PaymentCaptured` là hai event types diễn đạt hai sự thật khác nhau.
- Một event `OrderPlaced` có **hai listener** (audit và notification) nhưng vẫn chỉ là **một ý nghĩa**.
- `PaymentCaptured` có listener riêng nhận đúng dữ liệu thanh toán.
- Không dùng chuỗi `action`, không dùng `Map<String, Object>` và không để consumer phải đoán event subtype.

Dự án dùng **Java 17+**, **Spring Framework 6.2.12** và Maven.

Cấu trúc:

```text
domain-event-meaning/
├── pom.xml
└── src/main/java/demo/DomainEventsDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>domain-event-meaning</artifactId>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.DomainEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/DomainEventsDemo.java`:

```java
package demo;

import java.time.Instant;
import java.util.UUID;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class DomainEventsDemo {

    public record OrderPlaced(
            UUID eventId,
            String orderId,
            Instant occurredAt) {
    }

    public record PaymentCaptured(
            UUID eventId,
            String paymentId,
            String orderId,
            long amountMinor,
            String currency,
            Instant occurredAt) {
    }

    public static class OrderHandlers {

        @EventListener
        @Order(1)
        public void writeAudit(OrderPlaced event) {
            System.out.println("AUDIT order " + event.orderId());
        }

        @EventListener
        @Order(2)
        public void notifyCustomer(OrderPlaced event) {
            System.out.println("NOTIFY order " + event.orderId());
        }
    }

    public static class PaymentHandlers {

        @EventListener
        public void writeLedger(PaymentCaptured event) {
            System.out.println(
                    "LEDGER payment " + event.paymentId()
                    + " amount=" + event.amountMinor()
                    + " " + event.currency());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public OrderHandlers orderHandlers() {
            return new OrderHandlers();
        }

        @Bean
        public PaymentHandlers paymentHandlers() {
            return new PaymentHandlers();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            var orderPlaced = new OrderPlaced(
                    UUID.fromString(
                            "00000000-0000-0000-0000-000000000001"),
                    "O-100",
                    Instant.parse("2026-01-01T10:00:00Z"));

            var paymentCaptured = new PaymentCaptured(
                    UUID.fromString(
                            "00000000-0000-0000-0000-000000000002"),
                    "P-200",
                    "O-100",
                    125000L,
                    "VND",
                    Instant.parse("2026-01-01T10:02:00Z"));

            context.publishEvent(orderPlaced);
            context.publishEvent(paymentCaptured);
        }
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

Các dòng **do chương trình in**, không tính log phụ thuộc môi trường:

```text
AUDIT order O-100
NOTIFY order O-100
LEDGER payment P-200 amount=125000 VND
```

Giải thích:

1. `AnnotationConfigApplicationContext` tạo và refresh context, đăng ký các phương thức `@EventListener` của `OrderHandlers` và `PaymentHandlers`.
2. `publishEvent(orderPlaced)` gửi một object Java thông thường (record). Spring Framework hỗ trợ cả object không kế thừa `ApplicationEvent`; listener được chọn theo kiểu event.
3. Hai phương thức `writeAudit` và `notifyCustomer` đều nghe **cùng `OrderPlaced`**, không buộc tách thành hai event types. `@Order` mô tả thứ tự gọi listener trong ví dụ **đồng bộ**.
4. `PaymentHandlers.writeLedger` chỉ nhận `PaymentCaptured`, không cần nhánh phân tích chuỗi `action`. Số tiền và currency thuộc hợp đồng sự thật này.
5. Các event được publish tuần tự trên multicaster mặc định. Nếu cấu hình executor bất đồng bộ, **không thể lấy thứ tự hoàn tất listener** như ví dụ làm bảo đảm hệ thống.

Trong ví dụ, hai event được tạo cố định để dễ quan sát. Hệ thống thật **không nên phát `PaymentCaptured` chỉ vì một callback được gọi**: phải chắc chắn sự kiện thu tiền thành công theo nguồn có thẩm quyền của domain.

### Không cần mỗi event kế thừa ApplicationEvent

Từ Spring Framework 4.2, `ApplicationEventPublisher.publishEvent(Object)` hỗ trợ object thường. Bạn có thể dùng record như trên. Chỉ dùng subclass `ApplicationEvent` nếu thực sự có nhu cầu tương thích API hoặc thiết kế riêng, không bắt buộc thêm một superclass chỉ để nhận `@EventListener`.

### Event type không phải nơi thực hiện công việc

`PaymentCaptured` là **thông tin đã thu tiền**, không phải object có phương thức `capturePayment()`. Logic quyết định có thể thu tiền hay không phải nằm ở application/domain service phù hợp; consumer lắng nghe event xử lý hậu quả theo trách nhiệm đã định.

## 9. Vị trí phát event: sau khi bất biến nghiệp vụ được thỏa mãn

Một nguyên tắc thiết kế quan trọng: **không phát một fact trước khi nó thật sự đúng**.

Mô hình ứng dụng minh họa:

```java
// Code minh họa trong application service, không độc lập.
// Đã có orderRepository, eventPublisher và transaction boundary phù hợp.
@Transactional
public void placeOrder(PlaceOrderCommand command) {
    Order order = Order.place(command);
    orderRepository.save(order);

    eventPublisher.publishEvent(new OrderPlaced(
            UUID.randomUUID(),
            order.getId(),
            Instant.now()));
}
```

Ở đoạn này, `OrderPlaced` được phát **sau thao tác save trong luồng ứng dụng**, nhưng vẫn có một ranh giới quan trọng: nếu method đang trong transaction chưa commit, event Spring đồng bộ có thể đến listener **trước commit** và transaction vẫn có thể rollback sau đó.

Vì thế, nếu contract `OrderPlaced` nghĩa là “đơn **đã commit bền vững**”, việc publish trực tiếp bên trong transaction chưa đủ. Bạn cần xác định ranh giới sự thật:

- Nếu event là domain event nội bộ gắn với thay đổi đang được xét trong transaction, những listener đồng bộ có thể tham gia cùng transaction tùy cách gọi và cấu hình.
- Nếu consumer chỉ được phản ứng **sau commit thành công**, có thể dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` cho listener trong cùng tiến trình (với giới hạn ở phần 10).
- Nếu event phải được phát **đáng tin cậy qua tiến trình khác** sau commit, cân nhắc **transactional outbox** hoặc cơ chế có bảo đảm nhận và gửi được kiểm chứng.

**Không có quy tắc “chỉ cần có `@Transactional` là event được gửi sau commit”**. Thời điểm publish và thời điểm listener xử lý là hai yếu tố khác nhau.

### Logic quyết định nên ở đâu?

Ví dụ `CapturePayment` là một command. Payment service phải trao đổi với hệ thống thanh toán và nhận kết quả hợp lệ trước khi công bố `PaymentCaptured`. Không được phát `PaymentCaptured` để yêu cầu consumer khác đi thu tiền rồi coi fact đã có.

Quy trình đúng về ý nghĩa:

```text
CapturePayment command
        |
        v
Kiểm tra quy tắc / gọi payment provider
        |
        +--> Thu thành công, trạng thái được xác nhận
        |        |
        |        v
        |    PaymentCaptured event
        |
        +--> Thu thất bại
                 |
                 v
          Không phát PaymentCaptured
          (có thể phát PaymentDeclined nếu đó là fact domain)
```

Một tên event phải có **truth condition** mà domain có thể kiểm chứng. Nếu truth condition không rõ, event đó sẽ khó dùng đúng dù Java class thiết kế sạch.

## 10. Chọn ranh giới bounded context và tích hợp

Trong Domain-Driven Design, `OrderPlaced` do Ordering phát có thể là **domain event nội bộ** của Ordering. Payments có thể không cần phụ thuộc trực tiếp vào mọi class domain của Ordering. Khi dữ kiện đi qua ranh giới bounded context hoặc service, nên cân nhắc contract **integration event** phù hợp:

```text
Ordering Domain
     |
     +--> Domain event: OrderPlaced
                 |
                 v
        Outbox / translation / publication
                 |
                 v
        Integration event: OrderAcceptedV1
                 |
                 v
            Other services
```

Tên integration event không nhất thiết phải khác tên domain event, nhưng khi semantics và audience khác nhau thì một contract riêng có lợi. Có thể cần loại bỏ dữ liệu nội bộ, chuẩn hóa định danh, thêm schema version và xác định chính sách compatibility.

Quan trọng:

- **Một domain event một ý nghĩa** không có nghĩa mọi bounded context phải cùng dùng một class Java.
- Hai context có thể dùng cùng một từ nhưng định nghĩa khác nhau. Ví dụ “order accepted” trong Order Management và trong Fulfillment có thể là hai mốc khác nhau.
- Integration event là **hợp đồng công bố**, thường tồn tại lâu hơn code nội bộ và cần thay đổi có version.
- Không nên xuất toàn bộ domain entity object ra message broker rồi kỳ vọng consumer có thể deserialize mọi phiên bản của model.
- Nếu chuyển tiếp sự thật đã xảy ra, hệ thống ngoài phải biết chính xác nó có nghĩa gì, bao gồm idempotency, ordering scope và thời điểm có hiệu lực.

Một fact nội bộ cũng có thể tạo thành nhiều bản chiếu hoặc message cho các consumer khác nhau. Điều đó không làm thay đổi fact gốc; sự khác biệt nằm ở ranh giới triển khai và contract tiêu thụ.

## 11. Spring Application Events không tự biến fact thành thông điệp bền vững

`ApplicationEventPublisher` là cơ chế publish application events trong tiến trình/context. Mặc định `SimpleApplicationEventMulticaster` gọi listener **đồng bộ**. Khi bạn cấu hình `TaskExecutor`, một số listener có thể chạy bất đồng bộ.

Những hành vi cần hiểu:

| Khía cạnh | Spring Application Events nội bộ |
| --- | --- |
| Phân phối | Những listener phù hợp trong phạm vi application context; có thể truyền trong context hierarchy |
| Đồng bộ mặc định | Có, nếu dùng multicaster mặc định |
| Async | Có thể thông qua executor multicaster hoặc `@Async` theo thiết kế |
| Persistence | **Không tự lưu event một cách bền vững** |
| Retry sau crash | **Không có bảo đảm tự động** |
| Exactly-once | **Không được bảo đảm** |
| Thứ tự xử lý | Có thể điều khiển thứ tự gọi đồng bộ bằng `@Order`; không bảo đảm thứ tự hoàn tất async |
| Exception | Listener đồng bộ ném lỗi có thể làm lỗi đi ngược về publisher, tùy ErrorHandler/cấu hình |
| Transaction | Publish không đồng nghĩa commit; cần thiết kế phase và boundary riêng |

Do đó, chọn event type có semantics tốt là **cần thiết nhưng chưa đủ** để tạo hệ thống chịu lỗi. Nếu `PaymentCaptured` phải dẫn đến một công việc chắc chắn không được mất, hãy chọn cơ chế gửi nhận bền vững và idempotent consumer thay vì chỉ hy vọng một `@EventListener` sẽ chạy được.

### TransactionalEventListener là cơ chế thời điểm, không phải lưu bền vững

```java
// Minh họa trong một Spring bean với transaction manager.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onPaymentCaptured(PaymentCaptured event) {
    updateReadModel(event);
}
```

Phương thức trên giả định `PaymentCaptured` và `updateReadModel(...)` đã có, và có import cho `TransactionalEventListener`/`TransactionPhase`. Nếu không có transaction đang hoạt động, mặc định listener transactional không chạy, trừ khi cấu hình `fallbackExecution = true`.

Một callback `AFTER_COMMIT` không tự tạo atomic delivery đến broker, không có retry qua process crash, và không nên mặc nhiên dựa vào transaction cũ để ghi dữ liệu mới trong listener. Nếu cần viết dữ liệu sau commit qua transaction mới, cần biên giao dịch riêng được thiết kế rõ.

## 12. Event versioning: giữ nguyên ý nghĩa khi schema tiến hóa

Nếu sự thật vẫn giữ nguyên nhưng payload được làm giàu, bạn **không cần tạo một event nghiệp vụ mới chỉ vì thêm field**. Ví dụ `PaymentCaptured` thêm `paymentMethodCode` thì ý nghĩa “tiền đã thu” không đổi, dù contract tích hợp có thể cần version để tương thích.

Ngược lại, nếu semantics đổi từ “provider đã chấp nhận yêu cầu capture” sang “tiền đã chắc chắn được settle”, đó là **hai sự thật khác nhau**, không thể chỉ đổi phiên bản schema và tiếp tục gọi chung `PaymentCaptured` mà không cập nhật contract.

| Thay đổi | Thường nên làm |
| --- | --- |
| Thêm field tùy chọn không đổi nghĩa | Evolve schema tương thích nếu hạ tầng cho phép |
| Đổi cách biểu diễn số tiền | Version và migration rõ ràng; không đoán quy ước |
| Đổi truth condition của event | Tên/type/contract mới hoặc migration semantics có kiểm soát |
| Consumer mới quan tâm cùng fact | Thêm listener; **không** tạo event type mới chỉ vì consumer |
| Cần công bố qua service boundary | Contract integration riêng khi có lợi |
| Bỏ dữ liệu PII | Thiết kế schema, migration và chính sách retention |

Đừng dùng tên kiểu `PaymentCapturedV2` như một cách che việc event V2 thật ra nói một sự thật khác. Hãy giải thích trong tài liệu “V2 đổi gì, không đổi gì”.

### Tính bất biến của fact sau khi phát

Một khi đã công bố rằng `PaymentCaptured` xảy ra, đừng sửa event object cũ để biến nó thành `PaymentRefunded`. Nếu tiền đã hoàn, đó là một **sự thật nghiệp vụ mới**, thường có event riêng như `PaymentRefunded` và liên kết tới giao dịch gốc.

Cùng logic này, trạng thái nghiệp vụ hiện tại có thể thay đổi, nhưng lịch sử sự thật đã xảy ra không thể được viết lại tùy tiện. Tuy nhiên, domain event **không mặc nhiên** đồng nghĩa event sourcing; event-sourced system cần storage và quy tắc replay riêng.

## 13. Correlation, causation, ordering và idempotency

Mỗi event phải mô tả đúng một fact, nhưng các fact vẫn có thể liên quan tới cùng một workflow.

Ví dụ:

```text
correlationId = checkout-123

OrderPlaced(
    eventId=e1, orderId=O-100, occurredAt=t1)
     |
     | causationId=e1
     v
PaymentCaptured(
    eventId=e2, orderId=O-100, paymentId=P-200, occurredAt=t2)
     |
     | causationId=e2
     v
ShipmentRequested / fulfillment command
```

Sơ đồ là mẫu quan hệ, **không phải** quy tắc bắt buộc rằng mọi order đều được thanh toán trước khi vận chuyển. `correlationId` tập hợp các bước của cùng giao dịch logic; `causationId` chỉ ra thông điệp/hành động dẫn đến event nếu ứng dụng có cơ chế ghi nhận.

### Event ID

`eventId` giúp:

- Tìm một fact trong logs và traces.
- Dedupe consumer có thể nhận lại cùng thông điệp.
- Ghi nhận lần xử lý và kết quả ở các hệ thống tích hợp.
- Phân biệt nhiều lần xảy ra của cùng event type cho cùng một aggregate.

Một consumer có thể lưu `processedEventId` trong cùng transaction với cập nhật mà nó thực hiện, để có chính sách idempotency. Nhưng **có ID không tự tạo bảo đảm exactly-once**: transaction, retry và broker delivery semantics vẫn quan trọng.

### Ordering

Các event cùng một aggregate có thể có thứ tự nghiệp vụ cần bảo vệ. Nếu `OrderCancelled` tới trước `OrderPlaced` ở consumer remote, consumer cần chính sách cho thứ tự trễ hoặc out-of-order. Có thể dùng `aggregateVersion`, sequence number, partition key hoặc state machine, tùy kiến trúc.

Đừng suy luận rằng chỉ vì hai `publishEvent(...)` được gọi tuần tự trong một thread thì mọi consumer async hoặc remote sẽ xử lý đúng thứ tự đó.

## 14. Kiểm thử một event có thực sự “một ý nghĩa” không

Kiểm thử không chỉ xem listener có nhận class đúng, mà còn kiểm chứng **trạng thái nghiệp vụ trước/sau**:

| Trường hợp | Mục tiêu kiểm thử |
| --- | --- |
| Đặt đơn hợp lệ | Phát đúng một `OrderPlaced` với `orderId` và thời điểm phù hợp |
| Đặt đơn bị từ chối | Không phát `OrderPlaced` nếu điều kiện nghiệp vụ chưa đạt |
| Đơn đã đặt nhưng chưa thu tiền | Không phát sớm `PaymentCaptured` |
| Provider cho phép authorization nhưng chưa capture | Không gọi authorization là capture |
| Thu tiền thành công | Phát `PaymentCaptured` với `paymentId`, amount và currency đúng |
| Retry cùng lệnh | Không nhân đôi fact ngoài ý muốn; xác định idempotency |
| Nhiều listener cho OrderPlaced | Cùng nghe một event, không cần nhân bản event cho từng consumer |
| Transaction rollback | Hành vi listener/đưa event ra ngoài phù hợp với contract |
| Event gửi qua broker nhiều lần | Consumer nhận diện cùng `eventId` và không nhân đôi side effect |
| Schema đổi version | Consumer cũ/mới được kiểm tra tính tương thích |

### Đoạn test gợi ý

Với code application service, có thể dùng một `ApplicationEventPublisher` giả để ghi lại object đã được phát. Ví dụ helper:

```java
import java.util.ArrayList;
import java.util.List;
import org.springframework.context.ApplicationEventPublisher;

public final class RecordingEventPublisher implements ApplicationEventPublisher {
    private final List<Object> published = new ArrayList<>();

    @Override
    public void publishEvent(Object event) {
        published.add(event);
    }

    public List<Object> events() {
        return List.copyOf(published);
    }
}
```

Đây là class hỗ trợ test độc lập về cú pháp (với `spring-context` trên classpath). Nó chưa kiểm tra transaction của Spring, chỉ ghi các lần method `publishEvent(Object)` được gọi. Để test listener thực, dùng `AnnotationConfigApplicationContext`/integration test như ở mục 8.

Các assertion minh họa cho một test service:

```java
// Giả định placeOrder thành công và dùng RecordingEventPublisher.
assertEquals(1, publisher.events().size());
assertInstanceOf(OrderPlaced.class, publisher.events().get(0));
```

Đây là **đoạn minh họa JUnit**, không thuộc chương trình chạy độc lập ở mục 8. Nếu cần test các bản ghi/transaction, nên có integration test với database thật hoặc test container phù hợp.

### Review event contract bằng câu hỏi nghiệp vụ

Trong code review, hãy yêu cầu người thiết kế trả lời:

1. Tên fact này được domain expert hiểu như thế nào?
2. Điều kiện nào khiến fact đúng, và được kiểm chứng ở nơi nào?
3. Nếu nghiệp vụ thất bại, event nào **không** được phát?
4. Fact có thể xảy ra nhiều lần cho cùng aggregate không?
5. Cần gì để phân biệt các lần xảy ra: `eventId`, version, timestamp?
6. Consumer nào cần nó, và sự tồn tại consumer có khiến ta đặt tên event thiên lệch không?
7. Có đang ghép hai fact độc lập hoặc tách nhiều field của cùng fact không?
8. Nếu tiến trình crash ngay sau commit, cơ chế nào bảo đảm event vẫn có thể được xử lý?

## 15. Những lỗi phổ biến và cách khắc phục

1. **Event chung có `action`/`type` quyết định toàn bộ semantics**: tách khi các nhánh thật sự nói các sự thật khác nhau, dùng kiểu cụ thể.
2. **Đặt tên event theo consumer**: `OrderPlacedForEmail` dễ tạo dư thừa; dùng `OrderPlaced` và để consumer quyết định việc gửi.
3. **Đặt tên command dưới dạng event**: `CapturePaymentEvent` có thể chỉ yêu cầu capture; dùng command `CapturePayment`, event `PaymentCaptured` sau kết quả.
4. **Phát event khi mới bắt đầu thao tác**: gọi `OrderShipped` khi vừa tạo shipping label, trong khi hàng chưa bàn giao.
5. **Một class chứa nhiều trạng thái mâu thuẫn**: `OrderEvent(status, isPaid, isRefunded, isShipped)` tạo nhiều combinations khó hiểu; xác định lại những mốc business quan trọng.
6. **Event quá vụn cho mỗi cột database**: sinh hàng trăm event không ai có lý do nghiệp vụ để nghe; tập trung vào fact.
7. **Phát sự thật chưa commit nhưng đặt tên như đã durable**: xác định transaction boundary và quy tắc publish.
8. **Nhầm `@TransactionalEventListener` với delivery guarantee**: after commit chỉ là thời điểm xử lý nội bộ, không phải outbox.
9. **Lộ PII hoặc toàn bộ entity**: giới hạn payload vào dữ liệu cần thiết, có chính sách schema/privacy.
10. **Tin rằng cùng type nghĩa cùng semantics ở mọi bounded context**: đồng bộ ngôn ngữ hoặc translation contract.
11. **Dùng `@Order` làm orchestration nghiệp vụ đa bước**: với async hoặc remote, thứ tự completion không được bảo đảm; workflow cần state machine/saga phù hợp.
12. **Đổi semantics dưới cùng event name**: consumer cũ có thể hiểu nhầm dữ kiện; version và tài liệu hóa rõ.
13. **Cho rằng event type = event instance**: một class `OrderPlaced` có thể được tạo nhiều lần cho những order khác nhau hoặc các nỗ lực nghiệp vụ khác nhau.
14. **Không tính đến idempotency và delivery duplicate**: consumer có side effect dễ ghi đôi khi message broker retry.
15. **Dùng event nội bộ thay cho API giao dịch bắt buộc**: code thành công hay thất bại phụ thuộc kết quả trực tiếp của hành động thiết yếu thì không nên biến nó thành side effect tùy chọn.
16. **Coi domain event là event sourcing**: publish sự kiện trong application context không tạo được event log có thể replay.

## 16. Quy trình thiết kế thực tế

Khi cần mô hình hóa một chức năng mới, có thể đi theo thứ tự:

**Bước 1 — Viết câu chuyện nghiệp vụ.** Dùng lời người dùng/domain expert: “Khách đặt đơn; đơn được chấp nhận; payment provider thu tiền; đơn được chuyển kho”.

**Bước 2 — Khoanh những fact ở thì quá khứ.** Ví dụ `OrderPlaced`, `PaymentCaptured`, `FulfillmentStarted`. Không biến lệnh như “gửi email” thành fact đã gửi.

**Bước 3 — Ghi rõ truth condition.** `PaymentCaptured` chỉ phát sau khi provider xác nhận đã thu theo định nghĩa domain, không phát khi request đang pending.

**Bước 4 — Xác định boundary/owner.** Domain nào biết chắc fact đúng? Ai chịu trách nhiệm đổi trạng thái và phát event?

**Bước 5 — Chọn dữ liệu tối thiểu đủ cho consumer.** Định nghĩa identity, occurredAt, dữ liệu cần thiết, bảo mật, schema evolution.

**Bước 6 — Tách/gộp dựa trên semantics.** Nếu hai tên có thể xảy ra và evolve độc lập, tách. Nếu nhiều field cùng chứng minh một fact, giữ chung.

**Bước 7 — Thiết kế phát/nhận đúng tính tin cậy.** Internal Spring event, transactional listener, outbox hay broker tương ứng với nhu cầu latency, rollback và durability.

**Bước 8 — Kiểm thử tình huống đối chứng.** Không chỉ test happy path; test lệnh bị từ chối, payment pending, rollback, duplicate, out-of-order và consumer lỗi.

### Checklist cuối cùng

- [ ] Mỗi event type trả lời một câu “điều gì **đã xảy ra**?” rõ ràng.
- [ ] Không có `action` chuỗi buộc consumer phân nhánh sang các business facts không liên quan.
- [ ] Tên event nằm trong ubiquitous language của bounded context.
- [ ] Event được phát khi truth condition đã đạt; boundary transaction được ghi rõ.
- [ ] Payload mô tả fact, không lộ thừa dữ liệu entity hoặc secrets.
- [ ] Một event có thể có nhiều listener; không tạo một event type cho mỗi consumer.
- [ ] Không tách sự kiện theo từng field nếu chúng cùng một kết quả nghiệp vụ.
- [ ] Correlation, identity, idempotency và schema version được cân nhắc khi vượt boundary.
- [ ] Không nhầm Spring Application Events với persistent message broker.
- [ ] Test có cả tình huống **không được** phát event khi fact chưa xảy ra.

**Kết luận:** “Một event một ý nghĩa nghiệp vụ” là nguyên tắc thiết kế hợp đồng về **sự thật đã xảy ra**, không phải chỉ dẫn tăng số lượng Java record. Chia event theo mốc nghiệp vụ có điều kiện đúng độc lập; giữ mọi dữ liệu mô tả cùng fact trong một contract rõ ràng; để nhiều consumer nghe cùng event khi cần. Khi ý nghĩa của event chính xác, ứng dụng dễ kiểm thử, dễ tiến hóa và ít lệ thuộc vào chuỗi điều kiện kỹ thuật hơn.

## Tài liệu tham khảo

- [Spring Framework Reference — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [EventListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/EventListener.html)
- [Martin Fowler — Domain Event](https://martinfowler.com/eaaDev/DomainEvent.html)
- [Martin Fowler — What do you mean by "Event-Driven"?](https://martinfowler.com/articles/201701-event-driven.html)
