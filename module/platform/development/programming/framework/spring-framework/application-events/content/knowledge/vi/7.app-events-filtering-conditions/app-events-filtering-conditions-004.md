# Lọc theo trạng thái nghiệp vụ trong Spring Framework Application Events

## 1. Bài toán: cùng một loại sự kiện, nhiều trạng thái

Trong hệ thống đơn hàng, một đơn có thể chuyển qua các trạng thái như `NEW` (mới tạo), `CONFIRMED` (đã xác nhận), `PAID` (đã thanh toán), `SHIPPED` (đã giao cho đơn vị vận chuyển) và `CANCELLED` (đã hủy). Khi trạng thái thay đổi, hệ thống phát một sự kiện `OrderStatusChanged`; tuy nhiên, **không phải listener nào cũng cần xử lý mọi lần thay đổi**:

- Dịch vụ xuất hóa đơn chỉ quan tâm khi trạng thái mới là `PAID`.
- Dịch vụ thông báo vận chuyển chỉ quan tâm khi trạng thái mới là `SHIPPED`.
- Dịch vụ xử lý hủy chỉ quan tâm khi trạng thái mới là `CANCELLED`.
- Chuyển từ `NEW` sang `CONFIRMED` không kích hoạt ba tác vụ trên.

Đó là **lọc theo trạng thái nghiệp vụ**: chọn thực thi một listener dựa trên giá trị hoặc sự chuyển đổi trạng thái được đóng gói trong sự kiện. Cần phân biệt hai tầng lọc:

1. **Theo kiểu sự kiện**: phương thức nhận tham số `OrderStatusChanged` chỉ được chọn cho loại sự kiện phù hợp.
2. **Theo nội dung sự kiện**: điều kiện `status == PAID` (hoặc `oldStatus -> newStatus`) quyết định có gọi phương thức hay không.

Việc lọc bằng `@EventListener(condition = ...)` không làm sự kiện biến mất khỏi toàn bộ `ApplicationContext`: các listener khác vẫn có thể nhận chính sự kiện đó theo điều kiện của mình. Lọc listener cũng **không thay thế** kiểm tra tính hợp lệ của quy tắc chuyển trạng thái tại tầng nghiệp vụ.

## 2. Thiết kế sự kiện chứa thông tin đủ để lọc

Một sự kiện nên là dữ liệu mô tả điều đã xảy ra, thay vì chỉ chứa một tham chiếu đến entity có trạng thái còn tiếp tục thay đổi. Với Java 17+, có thể dùng `record`:

```java
public enum OrderStatus {
    NEW, CONFIRMED, PAID, SHIPPED, CANCELLED
}

public record OrderStatusChanged(
        String orderId,
        OrderStatus oldStatus,
        OrderStatus newStatus
) {}
```

Ý nghĩa của từng thuộc tính:

| Thuộc tính | Ý nghĩa | Tác dụng khi lọc |
| --- | --- | --- |
| `orderId` | Khóa nghiệp vụ của đơn | Xác định đối tượng cần tác động |
| `oldStatus` | Trạng thái trước khi thay đổi | Phân biệt các đường chuyển trạng thái |
| `newStatus` | Trạng thái mới sau thay đổi | Lọc listener theo trạng thái đích |

Ví dụ, `CONFIRMED -> PAID` và `NEW -> PAID` có cùng trạng thái đích nhưng có thể mang ý nghĩa khác nhau tùy quy tắc hệ thống. Nếu mục tiêu chỉ là "mọi đơn đã thanh toán", lọc `newStatus == PAID` là đủ; nếu chỉ chấp nhận một đường chuyển trạng thái, phải kiểm tra **cả hai** giá trị.

Trong hệ thống thực, nên bổ sung `eventId` và `occurredAt` khi cần theo dõi, kiểm toán hoặc chống xử lý trùng. Dữ liệu sự kiện nên bất biến; `record` hỗ trợ điều đó ở mức cấu trúc, nhưng nếu trường chứa một đối tượng có thể thay đổi thì vẫn cần sao chụp dữ liệu phù hợp.

## 3. Lọc trực tiếp bằng `@EventListener(condition)` và SpEL

Spring cho phép điều kiện `condition` là một biểu thức Spring Expression Language (SpEL). Biểu thức được đánh giá **trước khi** gọi phương thức listener; phương thức chỉ chạy khi kết quả điều kiện hợp lệ là `true`.

```java
@EventListener(condition = "#p0.newStatus().name() == 'PAID'")
public void onPaid(OrderStatusChanged event) {
    // Chỉ chạy cho sự kiện có trạng thái mới PAID.
}
```

Ở đây:

- `#p0` là tham số đầu tiên của phương thức listener, tức đối tượng `OrderStatusChanged`. Có thể viết `#a0` hoặc `#root.args[0]` với ý nghĩa tương đương.
- `newStatus()` là accessor tự sinh của Java `record`; `name()` chuyển hằng enum thành tên chuỗi `PAID`.
- `'PAID'` dùng dấu nháy đơn theo cú pháp chuỗi của SpEL. Đổi tên hằng enum cần cập nhật biểu thức.
- `#event` theo *tên tham số Java* chỉ dùng được nếu tên tham số được giữ trong bytecode (ví dụ biên dịch với `-parameters`). Dùng `#p0` giúp ví dụ không phụ thuộc thiết lập đó.
- `#root.event` chỉ đến `ApplicationEvent` cơ sở; khi xuất bản một đối tượng Java thông thường, Spring có thể bọc nó trong `PayloadApplicationEvent`. Để truy cập trực tiếp các trường của payload tại listener, `#p0` thường rõ ràng hơn.

Có thể kết hợp nhiều điều kiện:

```java
// Chỉ xử lý chuyển từ CONFIRMED sang PAID:
@EventListener(condition =
        "#p0.oldStatus().name() == 'CONFIRMED' && " +
        "#p0.newStatus().name() == 'PAID'")
public void onConfirmedOrderPaid(OrderStatusChanged event) {
    // Xử lý nghiệp vụ phù hợp.
}
```

SpEL hỗ trợ các toán tử logic như `&&`, `||`, `!` (hoặc `and`, `or`, `not`) và so sánh như `==`, `!=`. Với giá trị có thể là `null`, kiểm tra `null` trước khi gọi phương thức, ví dụ `#p0.newStatus() != null && #p0.newStatus().name() == 'PAID'`. Tốt hơn, thiết kế event yêu cầu trạng thái không `null` để tránh phải lặp kiểm tra ở mọi listener.

## 4. Ví dụ đầy đủ chạy được với Java 17 và Spring Framework

Ví dụ sau chạy trong một `ApplicationContext` thuần, không cần ứng dụng web, cơ sở dữ liệu hay message broker. Ta chủ động xuất bản bốn sự kiện; chỉ ba sự kiện khớp các điều kiện sẽ in dòng kết quả.

**Cấu trúc tệp**

```text
status-event-demo/
├── pom.xml
└── src/main/java/example/BusinessStatusEventDemo.java
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>status-event-demo</artifactId>
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
                <configuration>
                    <mainClass>example.BusinessStatusEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Phiên bản `6.2.0` được cố định để ví dụ có thể tái lập; dự án thực tế nên dùng bản vá Spring được duy trì và cách quản lý phiên bản dependency của dự án.

**`src/main/java/example/BusinessStatusEventDemo.java`**

```java
package example;

import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class BusinessStatusEventDemo {

    public enum OrderStatus {
        NEW, CONFIRMED, PAID, SHIPPED, CANCELLED
    }

    public record OrderStatusChanged(
            String orderId,
            OrderStatus oldStatus,
            OrderStatus newStatus
    ) {
        public OrderStatusChanged {
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(oldStatus, "oldStatus");
            Objects.requireNonNull(newStatus, "newStatus");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DemoConfig {
        @Bean
        public OrderListeners orderListeners() {
            return new OrderListeners();
        }
    }

    public static class OrderListeners {
        @EventListener(condition = "#p0.newStatus().name() == 'PAID'")
        public void whenPaid(OrderStatusChanged event) {
            System.out.println("PAID: " + event.orderId());
        }

        @EventListener(condition = "#p0.newStatus().name() == 'SHIPPED'")
        public void whenShipped(OrderStatusChanged event) {
            System.out.println("SHIPPED: " + event.orderId());
        }

        @EventListener(condition = "#p0.newStatus().name() == 'CANCELLED'")
        public void whenCancelled(OrderStatusChanged event) {
            System.out.println("CANCELLED: " + event.orderId());
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(DemoConfig.class)) {
            context.publishEvent(new OrderStatusChanged(
                    "O-101", OrderStatus.NEW, OrderStatus.CONFIRMED));
            context.publishEvent(new OrderStatusChanged(
                    "O-101", OrderStatus.CONFIRMED, OrderStatus.PAID));
            context.publishEvent(new OrderStatusChanged(
                    "O-101", OrderStatus.PAID, OrderStatus.SHIPPED));
            context.publishEvent(new OrderStatusChanged(
                    "O-102", OrderStatus.NEW, OrderStatus.CANCELLED));
        }
    }
}
```

**Chạy** từ thư mục chứa `pom.xml`, với JDK 17+ và Maven đã cài:

```bash
mvn -q compile exec:java
```

Các dòng `System.out` mà chương trình tạo ra, theo đúng thứ tự:

```text
PAID: O-101
SHIPPED: O-101
CANCELLED: O-102
```

Sự kiện `NEW -> CONFIRMED` vẫn được phát thành công nhưng không có listener nào trong ví dụ khớp điều kiện, vì vậy không in dòng nào. Mỗi lần phát sự kiện còn lại chỉ kích hoạt listener có trạng thái đích tương ứng. Những dòng log của thư viện hoặc công cụ chạy, nếu được cấu hình, không thuộc ba dòng kết quả nghiệp vụ trên.

**Vì sao ví dụ hoạt động?** `AnnotationConfigApplicationContext` đăng ký `DemoConfig` và bean `OrderListeners`; Spring phát hiện các phương thức có `@EventListener`. Khi `publishEvent(...)` nhận một `OrderStatusChanged`, Spring đối chiếu kiểu tham số và đánh giá từng biểu thức `condition` với chính payload đó. Mặc định các listener chạy đồng bộ trên luồng xuất bản, nên thứ tự phát ở `main` cũng là thứ tự các dòng in của ví dụ.

## 5. Chọn kỹ thuật lọc theo mức độ phức tạp

| Tình huống | Cách phù hợp | Lý do |
| --- | --- | --- |
| Một trạng thái hoặc điều kiện đơn giản, thuần dữ liệu | `@EventListener(condition = "...")` | Ngắn, listener không bị gọi nếu không khớp |
| Cần cả trạng thái cũ và mới | Điều kiện SpEL trên `oldStatus` và `newStatus` | Phân biệt chính xác chuyển đổi |
| Quy tắc phức tạp, cần gọi service, cấu hình hoặc truy vấn dữ liệu | `@EventListener` rồi kiểm tra bằng Java hoặc policy service | Dễ đọc, kiểm thử và xử lý lỗi hơn SpEL dài |
| Chỉ xử lý sau khi transaction ghi dữ liệu thành công | `@TransactionalEventListener(phase = AFTER_COMMIT, condition = "...")` | Tránh tác dụng phụ khi transaction bị rollback |
| Một mốc nghiệp vụ có ngữ nghĩa độc lập và ổn định | Phát loại sự kiện chuyên biệt như `OrderPaidEvent` | Mô hình rõ ràng, giảm điều kiện lặp lại ở nhiều listener |

Khi nghiệp vụ cần kiểm tra quyền, gọi API hoặc đọc trạng thái hiện tại từ cơ sở dữ liệu, không nên nhồi logic này vào `condition`. Thay vào đó, để biểu thức đơn giản và kiểm tra trong Java:

```java
// Minh họa tích hợp: notificationPolicy và notificationService
// là các dependency nghiệp vụ cần cung cấp trong ứng dụng thực.
@EventListener(condition = "#p0.newStatus().name() == 'PAID'")
public void notifyEligibleOrder(OrderStatusChanged event) {
    if (!notificationPolicy.canNotify(event.orderId())) {
        return;
    }
    notificationService.sendPaymentConfirmation(event.orderId());
}
```

Đoạn trên là minh họa tích hợp, **không phải lớp độc lập có thể biên dịch** khi chưa định nghĩa các dependency. Nó cho thấy ranh giới: SpEL lọc điều kiện đơn giản; Java xử lý quy tắc thay đổi theo nghiệp vụ.

## 6. Lọc trạng thái ở listener không thay thế việc quản lý chuyển trạng thái

Một listener chỉ biết sự kiện được phát ra; nó không tự chứng minh rằng chuyển trạng thái là hợp lệ hay đã được lưu bền vững. Tại service thay đổi đơn hàng, cần thực hiện đúng trình tự:

1. Đọc và khóa/cập nhật đơn theo cơ chế đồng thời thích hợp.
2. So sánh trạng thái cũ và trạng thái yêu cầu; nếu không đổi, thường **không phát** sự kiện trạng thái thay đổi.
3. Kiểm tra quy tắc chuyển trạng thái (ví dụ không cho `SHIPPED -> NEW`).
4. Lưu trạng thái mới và phát `OrderStatusChanged` chứa **snapshot trạng thái cũ/mới**.
5. Chọn cơ chế listener phù hợp với thời điểm commit và độ tin cậy cần thiết.

Ví dụ mã service mang tính tích hợp (phụ thuộc `OrderRepository`, entity `Order` và quy tắc nghiệp vụ thực tế):

```java
@Transactional
public void updateStatus(String orderId, OrderStatus target) {
    Order order = repository.findByIdForUpdate(orderId)
            .orElseThrow();
    OrderStatus previous = order.getStatus();

    if (previous == target) {
        return;
    }

    validateTransition(previous, target);
    order.setStatus(target);
    repository.save(order);

    publisher.publishEvent(
            new OrderStatusChanged(orderId, previous, target));
}
```

Trong ví dụ tích hợp, `@Transactional` được áp dụng thông qua Spring transaction management; `findByIdForUpdate` và `validateTransition` là hợp đồng minh họa do dự án tự định nghĩa. Nếu repository dùng cơ chế optimistic locking hoặc một loại transaction khác, triển khai đồng thời phải thay đổi tương ứng.

**Lưu ý về thời điểm:** `@EventListener` đồng bộ mặc định chạy ngay tại `publishEvent`, có thể trước khi transaction bao ngoài commit. Nếu listener gửi email hoặc gọi dịch vụ ngoài, tác dụng phụ đó có thể đã xảy ra dù transaction sau đó rollback.

Với tác dụng phụ phải đợi ghi dữ liệu thành công, có thể chuyển sang listener giao dịch:

```java
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

// Phương thức bên trong một Spring bean; cần spring-tx và
// transaction manager đang quản lý transaction thực tế.
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        condition = "#p0.newStatus().name() == 'PAID'")
public void afterOrderPaid(OrderStatusChanged event) {
    // Ví dụ: gửi tín hiệu bắt đầu phát hành hóa đơn.
}
```

Các điểm cần nhớ:

- `AFTER_COMMIT` là phase mặc định của `@TransactionalEventListener`; có thể chọn `BEFORE_COMMIT`, `AFTER_ROLLBACK` hoặc `AFTER_COMPLETION` cho mục đích khác.
- Mặc định `fallbackExecution = false`: nếu không có transaction đang hoạt động tại lúc phát, listener giao dịch **không chạy**. Ví dụ `main` thuần ở mục 4 vì thế dùng `@EventListener`.
- `AFTER_COMMIT` cho biết transaction đã commit; không đồng nghĩa callback tự động có transaction ghi dữ liệu mới. Nếu cần ghi DB trong listener hậu commit, thiết kế transaction mới phù hợp (thường `REQUIRES_NEW` trong một service được Spring quản lý).
- Transaction-bound event **không phải hàng đợi bền vững**. Với yêu cầu không được mất thông báo khi process chết hoặc cần retry đáng tin cậy, cân nhắc transactional outbox kết hợp worker/broker và cơ chế idempotency.

## 7. Kiểm thử các điều kiện theo trạng thái

Tách việc kiểm tra thành hai lớp: **lọc listener** và **chính sách chuyển trạng thái**. Với ví dụ mục 4, ma trận mong đợi:

| Sự kiện được phát | `whenPaid` | `whenShipped` | `whenCancelled` |
| --- | --- | --- | --- |
| `NEW -> CONFIRMED` | Không | Không | Không |
| `CONFIRMED -> PAID` | Có | Không | Không |
| `PAID -> SHIPPED` | Không | Có | Không |
| `NEW -> CANCELLED` | Không | Không | Có |

Nên kiểm thử thêm:

- Sự kiện cho hai `orderId` khác nhau không bị trộn dữ liệu.
- Listener không tạo tác dụng phụ khi trạng thái không khớp; kiểm tra **số lần gọi**, không chỉ nội dung log.
- Trường hợp cùng trạng thái cũ/mới được service bỏ qua; chuyển trạng thái bất hợp lệ bị từ chối **trước khi phát** sự kiện.
- Nếu dùng `@TransactionalEventListener`, kiểm thử riêng trường hợp **commit**, **rollback** và **không có transaction**. Không dùng ví dụ chỉ có `publishEvent` ngoài transaction để kết luận rằng callback `AFTER_COMMIT` lỗi.
- Khi chuyển sang `@Async`, xác nhận hành vi đồng thời, lỗi và retry; không còn dựa vào thứ tự in hoặc sự hoàn thành đồng bộ. Listener bất đồng bộ thường không truyền exception về luồng phát.

## 8. Những sai lầm thường gặp

1. **Dùng trạng thái hiện tại của entity thay vì trạng thái tại thời điểm phát.** Entity có thể được cập nhật tiếp trước khi listener bất đồng bộ chạy. Hãy đưa `oldStatus` và `newStatus` bất biến vào event.
2. **So sánh mỗi `newStatus` trong khi nghiệp vụ cần phân biệt nguồn chuyển.** Ví dụ, hoàn tiền khi `PAID -> CANCELLED` khác với hủy trước thanh toán `NEW -> CANCELLED`; điều kiện cần xét cả hai.
3. **Phụ thuộc `#event` như tên biến mà không biên dịch giữ tên tham số.** Dùng `#p0` hoặc `#a0` để ổn định giữa các cấu hình build.
4. **Viết SpEL quá dài hoặc phụ thuộc service phức tạp.** Khó kiểm thử và debug; đưa các quy tắc nhiều nhánh vào phương thức Java/policy.
5. **Quên phân biệt `@EventListener` và `@TransactionalEventListener`.** Một cái lọc theo nội dung khi sự kiện được chuyển đến; cái còn lại ràng buộc thêm việc xử lý theo phase transaction.
6. **Xem listener là công cụ đảm bảo chỉ xử lý một lần.** Trường hợp phát trùng, retry hoặc ứng dụng khởi chạy lại cần `eventId`/khóa idempotency và cơ chế lưu trạng thái xử lý nếu nghiệp vụ yêu cầu.
7. **Giả định mọi listener luôn chạy cùng luồng.** Mặc định là đồng bộ, nhưng cấu hình `ApplicationEventMulticaster` tùy chỉnh hoặc `@Async` có thể thay đổi. Không dựa vào thứ tự bất định giữa nhiều listener cho cùng một event.

## 9. Checklist áp dụng vào dự án

- Event có chứa trạng thái cũ, mới và định danh đối tượng, ở dạng snapshot.
- Publisher phát event **sau khi chấp nhận một thay đổi hợp lệ**, không phát cho no-op.
- Điều kiện `@EventListener(condition = ...)` phản ánh đúng trạng thái đích hoặc cặp trạng thái cần quan sát.
- Điều kiện đơn giản nằm trong SpEL; logic nghiệp vụ phức tạp nằm trong code Java có thể kiểm thử.
- Tác vụ phụ thuộc commit dùng `@TransactionalEventListener` và được kiểm thử với transaction thật.
- Tác dụng phụ quan trọng có chính sách lỗi, retry/idempotency, và độ bền phù hợp.

**Tài liệu chính thức để đối chiếu:**

- [Spring Framework — ApplicationContext Events và `@EventListener`](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
