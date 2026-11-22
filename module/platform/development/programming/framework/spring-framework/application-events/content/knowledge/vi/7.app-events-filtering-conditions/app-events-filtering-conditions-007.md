# Khi nào tách event thành kiểu riêng trong Spring Application Events?

Trong Spring Framework, một event nên diễn tả **điều đã xảy ra** hoặc **một yêu cầu nghiệp vụ rõ ràng**. Câu hỏi “có nên tách thành kiểu event riêng?” xuất hiện khi nhiều listener cùng nhận một event tổng quát, sau đó phải kiểm tra `type`, `action`, `status` hoặc hàng loạt điều kiện để quyết định xử lý.

Ví dụ, hệ thống đơn hàng phát `OrderChangedEvent` với `action = CREATED / PAID / CANCELLED`. Listener gửi hóa đơn chỉ quan tâm `PAID`; listener hoàn tiền chỉ quan tâm `CANCELLED`. Nếu các trạng thái biểu thị **những sự kiện nghiệp vụ khác nhau**, việc dùng `OrderPaid` và `OrderCancelled` thường rõ nghĩa và an toàn hơn. Ngược lại, listener thống kê chỉ cần nhận `OrderPlaced` khi `totalVnd >= 1_000_000` thì bộ lọc trên cùng một loại event có thể đã đủ.

Bài này giải thích ranh giới giữa **lọc một event** và **tạo một kiểu event mới**, đồng thời chỉ ra cách Spring định tuyến, cách viết listener, ví dụ chạy được và các giới hạn cần lưu ý.

## 1. Spring phân phối event dựa trên điều gì?

`ApplicationEventPublisher.publishEvent(Object)` cho phép công bố một đối tượng bất kỳ. Không bắt buộc lớp sự kiện phải kế thừa `ApplicationEvent`; một `record` Java hoặc POJO cũng dùng được. Với đối tượng thường, Spring bọc nó trong `PayloadApplicationEvent` ở tầng dispatch, còn listener khai báo đúng kiểu payload vẫn nhận được đối tượng gốc.

`@EventListener` dùng **kiểu tham số** để chọn những event mà phương thức xử lý được:

```java
record OrderPlaced(String orderId, long totalVnd) {}
record OrderCancelled(String orderId, String reason) {}

@EventListener
public void onPlaced(OrderPlaced event) {
    // Chỉ xử lý OrderPlaced.
}

@EventListener
public void onCancelled(OrderCancelled event) {
    // Chỉ xử lý OrderCancelled.
}
```

Đây là đoạn minh họa phương thức bên trong một Spring bean; ví dụ hoàn chỉnh có thể chạy nằm ở mục 4. Một listener có thể lọc tiếp các đối tượng **đã khớp kiểu** bằng `@EventListener(condition = "...")`. `condition` sử dụng Spring Expression Language (SpEL): biểu thức đúng thì Spring mới gọi phương thức.

Cần phân biệt:

- **Lọc theo kiểu:** “Đây có phải sự kiện yêu cầu rà soát đơn hàng không?” → một lớp `ReviewRequested` riêng làm rõ hợp đồng.
- **Lọc theo thuộc tính:** “Đơn vừa được đặt có tổng tiền từ một triệu đồng không?” → cùng `OrderPlaced`, thêm điều kiện trên dữ liệu.
- **Lọc theo cả hai:** listener nhận `OrderPlaced`, sau đó chỉ chọn đơn có giá trị cao. Cách này hoàn toàn hợp lệ nếu vẫn là cùng một sự kiện nghiệp vụ.

Một event **không mặc nhiên tồn tại** chỉ vì đã khai báo lớp hoặc listener. Mã nghiệp vụ phải thực sự gọi `publishEvent(...)` khi sự kiện xảy ra.

## 2. Những dấu hiệu nên tách thành kiểu event riêng

| Dấu hiệu | Vì sao cần cân nhắc tách | Ví dụ |
| --- | --- | --- |
| Hành vi/ngữ nghĩa nghiệp vụ khác nhau | Người đọc tên lớp hiểu ngay sự kiện nào đã xảy ra | `PaymentSucceeded` khác `PaymentFailed` |
| Listener liên tục `switch`/`if` trên `action` | Cùng một event đang chứa nhiều hợp đồng khác nhau | `OrderChanged(action)` bị kiểm tra tại mọi listener |
| Các trường bắt buộc không giống nhau | Một kiểu chung phải chứa nhiều trường `null` hoặc dữ liệu không liên quan | Thanh toán thành công có `transactionId`; thất bại có `failureCode` |
| Quy trình sau sự kiện khác về trách nhiệm | Event riêng là tín hiệu nghiệp vụ cho một workflow mới | `ReviewRequested` mở quy trình duyệt, thay vì chỉ tăng số liệu |
| Chính sách bảo mật/quyền truy cập khác | Giảm nguy cơ phát tán dữ liệu không cần thiết đến mọi listener | Event kiểm soát gian lận chỉ mang dữ liệu cần thiết |
| Vòng đời, phiên bản và consumer khác nhau | Có thể tiến hóa từng hợp đồng rõ ràng hơn | `RefundApproved` tách khỏi `RefundRejected` |
| Nhiều nhóm phát/nhận cùng hiểu một ý nghĩa ổn định | Tên event đóng vai trò ngôn ngữ chung giữa các module | `AccountLocked` |
| Điều kiện bắt đầu quyết định *loại* công việc, thay vì chỉ chọn dữ liệu | Điều kiện là quy tắc tạo một sự kiện mới, nên nằm ở miền nghiệp vụ | “Đã phát sinh yêu cầu rà soát” là sự kiện mới |

**Không nên tách chỉ vì mỗi listener có một tiêu chí lọc nhỏ.** Ví dụ, một bên thống kê các đơn trên một triệu, một bên thống kê đơn trên năm triệu, nhưng cả hai đều quan sát sự kiện “đơn đã được đặt”. Nếu tạo `OrderAboveOneMillion` và `OrderAboveFiveMillion` chỉ để phục vụ hai báo cáo, số kiểu event sẽ tăng theo từng consumer và các ngưỡng thay đổi liên tục.

## 3. Quy tắc quyết định: filter hay event mới?

Hãy trả lời lần lượt bốn câu:

1. **Tên event có mô tả một sự thật hoặc yêu cầu nghiệp vụ độc lập không?** Nếu có, ưu tiên kiểu riêng, ví dụ `InventoryReservationFailed`.
2. **Nếu bỏ một listener đi, sự kiện ấy vẫn có ý nghĩa không?** Nếu chỉ được đặt tên theo một bộ lọc của listener, có thể nó chưa cần thành loại mới.
3. **Người phát event có trách nhiệm xác nhận điều kiện nghiệp vụ không?** Nếu việc “phải rà soát” là kết quả của chính sách tại nguồn, nguồn có thể phát `ReviewRequested` sau khi quyết định; đừng để mỗi consumer tự diễn giải quy tắc khác nhau.
4. **Các dữ liệu và bất biến có khác nhau thực chất không?** Khi kiểu riêng giúp loại bỏ các trạng thái bất hợp lệ như “thất bại nhưng vẫn có mã giao dịch thành công”, lợi ích vượt xa việc rút gọn `if`.

Một cách phân nhóm thực tế:

| Tình huống | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Chỉ xử lý `OrderPlaced` nếu giá trị ≥ 1 triệu | `@EventListener(condition=...)` hoặc `if` trong listener | Vẫn là sự kiện đặt hàng |
| Đơn được duyệt thủ công, bắt đầu quy trình kiểm soát | `OrderReviewRequested` | Ý nghĩa nghiệp vụ mới |
| Cần phân biệt đơn được tạo và đơn bị hủy | `OrderPlaced` và `OrderCancelled` | Hai chuyển trạng thái khác nhau |
| Một notification listener chỉ chạy cho `region = "VN"` | Lọc trong listener | Tiêu chí của consumer, chưa tạo sự kiện mới |
| Email, SMS, audit đều nhận `OrderPaid` | Một event, nhiều listener | Không tạo loại event theo kênh xử lý |
| Cùng một event với 30 trạng thái cùng bộ dữ liệu, nhưng yêu cầu xử lý khác hẳn | Xem xét mô hình hóa các chuyển trạng thái thực sự quan trọng | Tránh biến tất cả thành một event đa dụng |

Nguyên tắc cốt lõi: **tách theo khác biệt về sự kiện nghiệp vụ và hợp đồng dữ liệu; lọc theo điều kiện lựa chọn bên trong cùng sự kiện**.

## 4. Ví dụ hoàn chỉnh: một điều kiện lọc, một event riêng

Giả sử hệ thống vừa ghi nhận đơn hàng vừa có thể phát sinh yêu cầu rà soát. Listener audit cần thấy mọi `OrderPlaced`; listener theo dõi đơn lớn chỉ quan tâm giá trị từ một triệu đồng. Tuy nhiên, `ReviewRequested` là một yêu cầu công việc có lý do riêng, đáng được biểu diễn bằng kiểu độc lập.

Ví dụ sau chạy với **Java 17+, Maven và Spring Framework 6.2.x**; dùng Spring context thuần, không cần Spring Boot hay cơ sở dữ liệu.

Tạo cấu trúc:

```text
spring-event-design/
├── pom.xml
└── src/main/java/demo/EventDesignDemo.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-event-design</artifactId>
    <version>1.0-SNAPSHOT</version>

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
                    <mainClass>demo.EventDesignDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Nội dung `src/main/java/demo/EventDesignDemo.java`:

```java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class EventDesignDemo {

    public record OrderPlaced(String orderId, long totalVnd) {}

    public record ReviewRequested(String orderId, String reason) {}

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Handlers handlers() {
            return new Handlers();
        }
    }

    public static class Handlers {
        @EventListener
        @Order(1)
        public void audit(OrderPlaced event) {
            System.out.println("AUDIT " + event.orderId());
        }

        @EventListener(condition = "#root.args[0].totalVnd() >= 1000000")
        @Order(2)
        public void watchLargeOrder(OrderPlaced event) {
            System.out.println("LARGE " + event.orderId());
        }

        @EventListener
        public void startReview(ReviewRequested event) {
            System.out.println(
                    "REVIEW " + event.orderId() + ": " + event.reason());
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            ApplicationEventPublisher publisher = context;

            publisher.publishEvent(new OrderPlaced("A1", 500_000L));
            publisher.publishEvent(new OrderPlaced("B2", 1_500_000L));

            // Nghiệp vụ đã quyết định cần rà soát đơn B2.
            publisher.publishEvent(
                    new ReviewRequested("B2", "manual risk review"));
        }
    }
}
```

Ở thư mục có `pom.xml`, chạy:

```bash
mvn -q compile exec:java
```

Kết quả của các lệnh `System.out.println` (không tính thông báo tùy môi trường của Maven/logging):

```text
AUDIT A1
AUDIT B2
LARGE B2
REVIEW B2: manual risk review
```

Giải thích theo trình tự:

1. `OrderPlaced("A1", 500_000)` khớp phương thức `audit`; điều kiện `watchLargeOrder` sai nên chỉ in `AUDIT A1`.
2. `OrderPlaced("B2", 1_500_000)` khớp cả hai phương thức. `@Order(1)` và `@Order(2)` đảm bảo thứ tự của hai listener tương ứng trong ví dụ đồng bộ.
3. `ReviewRequested("B2", ...)` là **một lần publish độc lập**, nên listener `startReview` nhận đúng kiểu đó. `@EventListener` không tự suy ra hay tạo `ReviewRequested` từ một `OrderPlaced` có giá trị cao.
4. `#root.args[0]` trong điều kiện SpEL là tham số `OrderPlaced` của listener. Gọi `totalVnd()` phù hợp với accessor của Java `record`, không phụ thuộc tên tham số được biên dịch vào bytecode.
5. Hai event không buộc phải kế thừa `ApplicationEvent`; Spring xử lý chúng như payload events.

Trong hệ thống thật, nơi đặt lệnh `publishEvent(new ReviewRequested(...))` phải là thành phần **chịu trách nhiệm quyết định nghiệp vụ** (chẳng hạn application service sau khi áp dụng chính sách rủi ro). `main` trong ví dụ chỉ thay cho thành phần đó để có chương trình chạy độc lập.

## 5. Trước và sau khi tách kiểu

### Trước: một event mang nhiều ý nghĩa

```java
record OrderChanged(String orderId, String action, String reason) {}

// Bên trong một Spring bean:
@EventListener
public void handle(OrderChanged event) {
    if ("PAID".equals(event.action())) {
        issueReceipt(event.orderId());
    } else if ("CANCELLED".equals(event.action())) {
        releaseInventory(event.orderId());
    }
}
```

Đây là **đoạn minh họa**, các phương thức `issueReceipt` và `releaseInventory` thuộc dịch vụ ứng dụng và chưa được định nghĩa. Những rủi ro của mô hình này gồm giá trị `action` không hợp lệ, `reason` bị bỏ trống khi hủy và việc mọi consumer phải lặp lại logic rẽ nhánh.

### Sau: hai hợp đồng có ý nghĩa rõ ràng

```java
record OrderPaid(String orderId, String paymentId) {}
record OrderCancelled(String orderId, String reason) {}

// Bên trong một Spring bean:
@EventListener
public void onPaid(OrderPaid event) {
    issueReceipt(event.orderId());
}

@EventListener
public void onCancelled(OrderCancelled event) {
    releaseInventory(event.orderId());
}
```

Khi `OrderPaid` xuất hiện, `paymentId` thuộc hợp đồng của loại đó; khi `OrderCancelled` xuất hiện, `reason` có vai trò rõ ràng. Constructor của `record` **chưa tự kiểm tra null/blank**, nên nếu yêu cầu bất biến mạnh hơn, hãy thêm kiểm tra trong compact constructor hoặc tại lớp nghiệp vụ tạo event.

Không phải mọi giá trị của enum trạng thái đều cần lớp event riêng. Chỉ tách những chuyển trạng thái có ý nghĩa và người tiêu thụ rõ ràng; tránh tạo vô số `StatusChangedToX` nếu tất cả thực sự cùng một hợp đồng.

## 6. Dùng `condition` đúng chỗ

Ví dụ ngắn cho một listener lựa chọn theo thuộc tính:

```java
@EventListener(condition = "#root.args[0].totalVnd() >= 1000000")
public void trackLargeOrder(OrderPlaced event) {
    // Chạy khi có OrderPlaced đủ ngưỡng.
}
```

Các quy tắc quan trọng:

- **Điều kiện luôn nằm sau bước chọn kiểu phù hợp**: SpEL không biến một `OrderPlaced` thành `ReviewRequested`.
- **Ưu tiên điều kiện thuần, nhẹ và có thể dự đoán**: so sánh giá trị, trạng thái, cờ đơn giản; tránh truy vấn mạng hoặc database trong SpEL.
- **Phân biệt quy tắc nghiệp vụ với bộ lọc consumer**: nếu một điều kiện quyết định việc mở quy trình, hãy tính ở service chịu trách nhiệm rồi phát event thích hợp; nếu chỉ quyết định có cập nhật biểu đồ thống kê hay không, giữ trong listener.
- **Kiểm tra null và dữ liệu hợp lệ**: SpEL có thể lỗi khi gọi accessor trên đối tượng lồng nhau null; thiết kế payload và biểu thức cho đúng hợp đồng.
- **Tránh phụ thuộc tên tham số mơ hồ**: `#root.args[0]` hoặc `#a0` hoạt động theo chỉ số. Dùng `#orderEvent` theo tên chỉ khi cấu hình biên dịch cung cấp tên tham số.
- **Không dùng chuỗi nhãn kỹ thuật làm hợp đồng ngầm**: nếu `event.kind()` có nhiều giá trị độc lập và consumer đều rẽ nhánh theo nó, hãy xem lại việc tách kiểu.

Khi điều kiện dài hoặc có nhiều phép kiểm tra, phương thức listener gọi một service/policy riêng có thể dễ đọc, dễ kiểm thử hơn. Tuy nhiên, nếu cùng một chính sách quyết định **event nào được phát**, chính sách đó phải được áp dụng ở phía phát event để các listener không đưa ra kết luận trái nhau.

## 7. Thiết kế event riêng sao cho bền vững

**Đặt tên theo sự kiện đã xảy ra hoặc ý định nghiệp vụ.** `PaymentCaptured`, `AccountLocked`, `ReviewRequested` truyền đạt ý nghĩa tốt hơn `PaymentEvent2`, `SpecialEvent` hoặc `NotifyEmailEvent`. Không dùng tên consumer làm tên event nếu bản thân nghiệp vụ không có sự kiện đó.

**Ưu tiên payload nhỏ, bất biến.** `record` phù hợp với dữ liệu đơn giản: mã định danh, thời điểm, giá trị cần thiết, lý do, correlation ID. Không gửi cả entity JPA đang quản lý chỉ để listener đọc vài trường: entity có thể thay đổi, lazy-loading có thể phụ thuộc transaction và dễ lộ dữ liệu thừa. Với dữ liệu mutable, cân nhắc snapshot bất biến.

**Xác định chính xác thời điểm phát event.** `OrderPlaced` phải được công bố tại một điểm nghiệp vụ nhất quán. Nếu event mang nghĩa “giao dịch đã commit”, đừng phát nó như một cam kết sau commit khi transaction còn có thể rollback.

**Đừng dùng inheritance như một cách lách điều kiện.** Một cây lớp `OrderEvent` với hàng chục subclass chỉ hữu ích khi quan hệ “is-a” và cách dispatch thực sự phù hợp. Tránh listener nhận lớp cha rồi lại dùng `instanceof` liên tục, và cẩn thận listener theo lớp cha có thể nhận cả event lớp con.

**Tính đến khả năng tiến hóa hợp đồng.** Thêm trường mới, thay đổi ý nghĩa hoặc tách event đều tác động đến người phát/người nhận. Trong một ứng dụng nội bộ, có thể refactor đồng thời; ở ranh giới module độc lập hoặc có hàng đợi bền vững, cần kế hoạch tương thích và versioning riêng.

**Không tách theo mỗi nhu cầu báo cáo.** Khi số lượng event tăng theo từng nhóm thống kê, cân nhắc giữ một event nghiệp vụ cốt lõi và cho consumer xây dựng các projection khác nhau.

## 8. Event trong Spring không đồng nghĩa message broker

Spring Application Events mặc định dùng `SimpleApplicationEventMulticaster` và phát **đồng bộ trên luồng của bên publish**, trừ khi được cấu hình khác hoặc listener dùng cơ chế bất đồng bộ. Điều này có các hệ quả:

- Listener đồng bộ có thể làm thời gian thực thi `publishEvent(...)` tăng lên; lỗi runtime trong listener có thể lan tới phía publish.
- `@Async` cho listener cần bật hỗ trợ async và cấu hình executor phù hợp. Khi chạy async, không nên giả định listener hoàn tất trước khi `publishEvent(...)` trả về, thứ tự xử lý cố định hoặc cùng transaction/thread context.
- `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` dùng khi một listener cần chạy theo phase của transaction, nhưng mặc định **không chạy nếu không có transaction đang hoạt động** (trừ khi chọn `fallbackExecution = true`). Cần hiểu rõ thời điểm commit, exception và giới hạn của các thao tác dữ liệu trong callback.
- Event nội bộ Spring không tự cung cấp lưu bền vững, retry bảo đảm, phân phối qua nhiều instance hay exactly-once delivery. Khi bắt buộc gửi event ra hệ thống ngoài sau commit, hãy cân nhắc transactional outbox và message broker theo yêu cầu hệ thống.

Quyết định tách event thành kiểu riêng và quyết định **vận chuyển event bằng cơ chế nào** là hai bài toán khác nhau. Một kiểu event rõ nghĩa không tự bảo đảm độ tin cậy phân phối.

## 9. Kiểm thử quyết định tách event và điều kiện lọc

Với ví dụ ở mục 4, tối thiểu cần bao phủ:

| Trường hợp | Event công bố | Kết quả cần kiểm tra |
| --- | --- | --- |
| Đơn dưới ngưỡng | `OrderPlaced("A1", 500_000)` | Audit chạy, bộ lọc đơn lớn không chạy |
| Đơn đúng ngưỡng | `OrderPlaced("C3", 1_000_000)` | Audit và bộ lọc đơn lớn đều chạy |
| Đơn trên ngưỡng | `OrderPlaced("B2", 1_500_000)` | Audit và bộ lọc đơn lớn đều chạy |
| Yêu cầu rà soát | `ReviewRequested("B2", "manual risk review")` | Chỉ listener cho loại yêu cầu rà soát được kích hoạt |
| Chỉ phát đơn lớn, không phát yêu cầu rà soát | `OrderPlaced("B2", 1_500_000)` | Không có `ReviewRequested` tự sinh |
| Đổi chính sách phân loại | Cùng event đầu vào, policy mới | Test policy phát hay không phát loại event độc lập với listener |

Trong kiểm thử tích hợp, có thể khởi tạo `AnnotationConfigApplicationContext` với các bean ghi lại event đã nhận và dùng assertion trên danh sách đó. Nếu project có Spring Boot Test, có thể dùng công cụ kiểm thử event phù hợp, nhưng không phải điều kiện tiên quyết để hiểu cơ chế. Với async hoặc transaction phase, viết test có executor/transaction đúng cấu hình thay vì dựa vào thứ tự in ra console.

## 10. Lỗi thiết kế thường gặp

1. **Tách event theo tên listener**: `SendEmailEvent`, `UpdateDashboardEvent` thường phản ánh tác vụ consumer; event nghiệp vụ như `OrderPaid` có thể phục vụ nhiều consumer hơn.
2. **Giữ một event “đa năng” mãi mãi**: hàng loạt `action`/`status` và trường nullable khiến hợp đồng khó kiểm tra, mỗi listener hiểu một kiểu.
3. **Phát nhiều loại event mang cùng một sự thật mà không có quy ước**: dễ xử lý trùng hoặc để các consumer cập nhật dữ liệu hai lần. Xác định quan hệ giữa event gốc và event được suy ra.
4. **Đẩy quy tắc nghiệp vụ vào SpEL của từng listener**: cùng một chính sách bị sao chép và cho kết quả khác nhau theo thời gian.
5. **Nhầm lọc và tạo event**: `condition` chỉ quyết định có gọi listener hay không; muốn có event mới phải phát nó.
6. **Giả định mọi listener luôn xử lý bất đồng bộ hoặc sau commit**: mặc định dispatch đồng bộ; cơ chế transaction/async cần cấu hình rõ ràng.
7. **Sửa tên hoặc payload event đã có nhiều consumer mà không kiểm tra tương thích**: lớp mới có thể tốt hơn về thiết kế nhưng vẫn là thay đổi hợp đồng.
8. **Kỳ vọng Spring Application Events thay thế hệ thống messaging bền vững**: yêu cầu retry, replay, giao hàng liên dịch vụ cần cơ chế chuyên biệt.

## 11. Checklist trước khi tạo kiểu event mới

- Có thể mô tả event bằng một câu nghiệp vụ cụ thể, độc lập với tên listener không?
- Một listener mới chỉ cần lọc thuộc tính, hay đang phải diễn giải `action` để biết **sự kiện nào** đã xảy ra?
- Payload của hai tình huống có bất biến và trường bắt buộc khác nhau không?
- Ai có thẩm quyền quyết định và phát event; khi nào quyết định ấy được xem là có hiệu lực?
- Tách kiểu có giảm nhiều rẽ nhánh, trùng lặp và trạng thái sai không?
- Event sẽ được xử lý đồng bộ, sau transaction hay cần vận chuyển bền vững?
- Những listener hiện có sẽ bị ảnh hưởng ra sao khi thêm/tách/đổi hợp đồng?

Nếu câu trả lời chủ yếu là “cùng một sự kiện, chỉ khác tiêu chí chọn dữ liệu”, giữ loại event hiện có và lọc ở listener. Nếu câu trả lời là “hai sự kiện/nghĩa vụ nghiệp vụ khác nhau với hợp đồng riêng”, tạo các kiểu riêng và để nguồn nghiệp vụ phát chúng một cách có chủ ý.

**Tài liệu tham khảo:** [Spring Framework Reference — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html), các phần *Annotation-based Event Listeners*, *Asynchronous Listeners* và *Ordering Listeners*.