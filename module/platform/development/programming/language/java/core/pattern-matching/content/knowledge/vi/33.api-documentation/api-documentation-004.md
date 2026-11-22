# Tài liệu hóa subtype được phép trong Java Pattern Matching

## 1. Vì sao danh sách subtype được phép là một phần quan trọng của API?

Khi xây dựng API Java bằng `sealed class` hoặc `sealed interface`, một quyết định thiết kế lớn là **những kiểu nào được phép kế thừa hoặc triển khai trực tiếp** kiểu gốc. Java cho phép biểu diễn quyết định này bằng mệnh đề `permits`:

```java
sealed interface OrderEvent permits Placed, Cancelled, FulfillmentEvent {
}
```

Mệnh đề trên là **ràng buộc của ngôn ngữ**, không chỉ là một đoạn comment: ngoài các kiểu `Placed`, `Cancelled` và `FulfillmentEvent` được phép trực tiếp, kiểu khác không thể trực tiếp `implements OrderEvent` trong chương trình hợp lệ.

Nhưng khi **tài liệu hóa API**, chỉ sao chép tên các lớp từ `permits` vẫn chưa đủ. Người sử dụng API cần hiểu:

- Danh sách này gồm **subtype trực tiếp**, không mặc nhiên là toàn bộ concrete subtype có thể xuất hiện ở runtime.
- Từng subtype được phép là **`final`**, **`sealed`** hay **`non-sealed`**, vì ba lựa chọn quyết định mức độ mở rộng của các nhánh.
- Những trường hợp nghiệp vụ có ý nghĩa gì, thành phần dữ liệu nào được bảo đảm và trường hợp nào cần xử lý như `null` hay dữ liệu không hợp lệ.
- Một `switch` với type/record patterns có thể coi các kiểu nào là **exhaustive**, và trường hợp nào nên có fallback.
- Khi thư viện thêm một subtype mới, mã client cần **recompile** hay bổ sung xử lý ra sao.
- Khả năng mở rộng là **cam kết lâu dài** hay chỉ phản ánh cấu trúc hiện tại của phiên bản API.

Trong Java, **sealed types** chính thức từ Java 17 (JEP 409). **Pattern matching for `switch`** và **record patterns** chính thức trong Java 21 (JEP 441 và JEP 440). Do đó, một sealed hierarchy có thể dùng trong thư viện target Java 17, còn cách xử lý bằng `switch` có pattern như bài này yêu cầu Java 21+.

**Mục tiêu bài học:** viết tài liệu vừa đúng với quy tắc `permits` của compiler, vừa hữu ích cho người đọc JavaDoc, người viết pattern switch, người bảo trì và người phát hành phiên bản thư viện.

## 2. Phân biệt subtype trực tiếp, gián tiếp và concrete implementation

Xem cây kế thừa:

```text
OrderEvent  (sealed interface)
├── Placed                 (record, implicitly final)
├── Cancelled              (record, implicitly final)
└── FulfillmentEvent       (non-sealed interface)
    ├── Packed             (record)
    ├── Shipped            (record)
    └── CustomerPickup     (record)
         ... còn có thể có subtype khác sau này
```

Danh sách `permits` của `OrderEvent` chỉ gồm:

```text
Placed, Cancelled, FulfillmentEvent
```

Nó **không** trực tiếp liệt kê `Packed`, `Shipped` hay `CustomerPickup`, vì những kiểu này triển khai **`FulfillmentEvent`**, không trực tiếp triển khai `OrderEvent`.

Có ba khái niệm cần ghi chính xác vào tài liệu:

| Khái niệm | Ý nghĩa | Trong ví dụ |
| --- | --- | --- |
| **Permitted direct subtype** | Kiểu được khai báo trong `permits` của sealed parent và trực tiếp extends/implements parent | `Placed`, `Cancelled`, `FulfillmentEvent` |
| **Indirect subtype** | Kiểu kế thừa parent qua một hoặc nhiều tầng | `Packed`, `Shipped`, `CustomerPickup` |
| **Concrete subtype** | Kiểu có thể tạo instance và sử dụng làm đối tượng thuộc parent | Ba record nói trên cùng `Placed`, `Cancelled` |

**Không đồng nhất “permitted” với “tất cả object thực tế có thể gặp”.** Một `non-sealed` nhánh cho phép các subtype khác mở rộng ở dưới nó. Do đó, tài liệu kiểu “chỉ có đúng ba loại sự kiện tại runtime” là sai nếu một trong ba nhánh được phép vẫn mở rộng.

Đối với hierarchy hoàn toàn đóng (mọi nhánh đều kết thúc ở `final` hoặc tiếp tục `sealed` mà cuối cùng đều kết thúc), có thể tài liệu hóa tập các concrete subtype hiện tại. Nhưng vẫn nên phân biệt tập **trực tiếp** của từng sealed node với tập **lá cuối** của cả cây.

## 3. Quy tắc compiler của `sealed`, `permits` và subtype được phép

### 3.1. Một subtype được phép phải kế thừa trực tiếp

```java
sealed interface Command permits Start, Stop {}

record Start(String id) implements Command {}
record Stop(String id) implements Command {}
```

Hai record triển khai trực tiếp `Command` nên được phép. Nhưng không thể chỉ thêm tên của một lớp **chỉ kế thừa gián tiếp** vào `permits` của `Command` để biến nó thành subtype trực tiếp. Parent phải liệt kê đúng direct children.

Ví dụ về đường kế thừa gián tiếp hợp lệ:

```java
sealed interface Command permits Task {}
non-sealed interface Task extends Command {}
record StartTask(String id) implements Task {}
```

Ở đây `Command` chỉ `permits Task`. `StartTask` là subtype gián tiếp qua `Task`, nên không cần và không nên ghi nó trong danh sách `permits` của `Command`.

### 3.2. Direct subtype phải quyết định có tiếp tục cho kế thừa hay không

Một lớp/interface trực tiếp kế thừa sealed type phải mang một trong các trạng thái hợp lệ:

- **`final`:** chấm dứt đường kế thừa tại lớp đó. Record class là `final` ngầm định.
- **`sealed`:** vẫn giới hạn những subtype trực tiếp của chính nó bằng `permits`.
- **`non-sealed`:** mở lại đường kế thừa ở nhánh đó, không còn danh sách `permits` cho chính nhánh `non-sealed`.

Ví dụ:

```java
sealed interface Result permits Success, Failure, Retryable {}

record Success(String data) implements Result {}

final class Failure implements Result {
    final String message;
    Failure(String message) { this.message = message; }
}

non-sealed interface Retryable extends Result {
    boolean shouldRetry();
}
```

Đây là đoạn mã Java 17+ hợp lệ khi các khai báo được đặt trong cùng compilation context phù hợp. `Success` là record (ngầm final), `Failure` explicit final, `Retryable` mở rộng tiếp được. **Tài liệu nên nói rõ nhánh nào mở**, không chỉ liệt kê `Success, Failure, Retryable`.

Nếu một interface trực tiếp kế thừa sealed interface mà không ghi `sealed` hoặc `non-sealed`, compiler sẽ từ chối. Tương tự, một class trực tiếp kế thừa sealed class mà không phải `final`, `sealed` hoặc `non-sealed` theo quy định cũng không hợp lệ.

### 3.3. `non-sealed` không phải trạng thái mặc định của mọi interface

Từ khóa `non-sealed` chỉ dùng khi kiểu đó trực tiếp kế thừa một sealed type có liên quan. Không tùy tiện thêm `non-sealed` vào một interface bình thường không có sealed parent để “nói rằng mở rộng được”. Với interface thông thường, khả năng mở rộng là mặc định.

### 3.4. Phạm vi module/package là một phần của ràng buộc

Một subtype trực tiếp được phép phải thuộc phạm vi mã tương thích với sealed parent:

- Nếu sealed type nằm trong **named module**, direct permitted subtype phải nằm trong **cùng module**.
- Nếu sealed type thuộc **unnamed module**, direct permitted subtype phải nằm trong **cùng package** với sealed type.

Điều đó có nghĩa thư viện phát hành một sealed parent công khai không thể mời người dùng ở một module khác tùy ý viết thêm một **direct implementation** của parent. Muốn mở rộng cho phía client, thiết kế một nhánh `non-sealed` công khai trong phạm vi module của thư viện, rồi cho client triển khai nhánh đó.

Hãy ghi rõ **extension point** được hỗ trợ (nếu có). Đừng viết JavaDoc “client có thể implement `OrderEvent`” nếu sealed parent không cho phép điều ấy.

### 3.5. Có thể suy ra `permits` khi điều kiện biên dịch phù hợp

Trong một số trường hợp mọi direct subtype nằm cùng compilation unit với sealed parent, Java có thể suy ra tập permitted subclasses khi bỏ mệnh đề `permits`. Tuy nhiên, tài liệu API công khai nên làm rõ các subtype bằng một mô tả dễ kiểm chứng, và một mệnh đề `permits` tường minh thường giúp người đọc/reviewer nhận biết quyết định kiến trúc nhanh hơn.

**Không nên dựa vào JavaDoc chung chung để thay thế quy tắc compiler.** `permits` hoặc tập subtype được compiler suy ra là ràng buộc thực tế. JavaDoc bổ sung **ý nghĩa nghiệp vụ và chính sách phát triển API** mà cú pháp một mình chưa thể diễn đạt.

## 4. Cần tài liệu hóa những gì cho một sealed API?

Một tài liệu tốt có ít nhất bốn tầng:

### 4.1. Tầng ngữ nghĩa: sealed parent đại diện cho điều gì?

Ví dụ: “`OrderEvent` là một sự kiện bất biến mô tả biến đổi đáng chú ý trong vòng đời đơn hàng”. Tài liệu này trả lời *kiểu gốc tồn tại để làm gì*, không chỉ “đây là sealed interface”.

### 4.2. Tầng cấu trúc: các **direct permitted subtype** là gì?

Liệt kê tên và giải thích:

| Direct subtype | Cấu trúc | Ý nghĩa |
| --- | --- | --- |
| `Placed` | Record, final | Đơn hàng vừa được tạo |
| `Cancelled` | Record, final | Đơn hàng bị hủy |
| `FulfillmentEvent` | Non-sealed interface | Họ sự kiện thực hiện đơn hàng, mở cho các triển khai khác |

Một comment như “Possible event types: `Placed`, `Cancelled`, `FulfillmentEvent`” dễ bị hiểu sai thành “chỉ có ba concrete event”; nên thêm từ **direct** và ghi rõ nhánh thứ ba **open**.

### 4.3. Tầng hợp đồng: client cần xử lý thế nào?

Nêu cách phân nhánh được hỗ trợ, thuộc tính bắt buộc, chính sách `null` và ngoại lệ liên quan. Ví dụ, với client Java 21: “Một switch exhaustive trên `OrderEvent` có thể xử lý `Placed`, `Cancelled` và một `case FulfillmentEvent` tổng quát”. Nếu muốn phân biệt từng event fulfillment hiện tại, xử lý case cụ thể trước, nhưng vẫn cần case `FulfillmentEvent` để bao phủ các subtype mới của nhánh mở.

### 4.4. Tầng tiến hóa: API có ổn định hay không?

Nêu liệu thư viện có thể bổ sung subtype trong các bản cập nhật hay không và cách client nên phản ứng. Việc “sealed” **không tự là lời hứa danh sách subtype không bao giờ thay đổi giữa các phiên bản**; đó là quyết định versioning/phát hành do chủ API công bố.

Tài liệu nên phân biệt:
- Hạn chế **bởi compiler ở phiên bản hiện tại**.
- Cam kết **tương thích nguồn** khi nâng thư viện.
- Cam kết **tương thích nhị phân/runtime** cho client đã biên dịch.

Không nên khẳng định tuyệt đối “mọi client sẽ luôn hoạt động” chỉ vì kiểu gốc sealed.

## 5. Ví dụ Java 21 hoàn chỉnh có JavaDoc và phản xạ

Ví dụ sau trình bày API có một nhánh mở, việc dùng pattern switch và cách đọc **direct permitted subclasses** bằng reflection. Lưu nguyên văn thành **`PermittedSubtypeDocsDemo.java`**.

```java
import java.util.Arrays;
import java.util.stream.Collectors;

public class PermittedSubtypeDocsDemo {
    /**
     * Domain contract for an order event.
     *
     * <p>Direct permitted subtypes: Placed, Cancelled,
     * and FulfillmentEvent.
     *
     * @apiNote FulfillmentEvent is an open extension branch.
     *          Consumers should handle that branch as a whole
     *          unless their use case needs more detail.
     * @since 17
     */
    public sealed interface OrderEvent
            permits Placed, Cancelled, FulfillmentEvent {}

    /** An order was placed. */
    public record Placed(
            String orderId, String customerId) implements OrderEvent {}

    /** An order was cancelled. */
    public record Cancelled(
            String orderId, String reason) implements OrderEvent {}

    /**
     * Open family of events concerned with fulfillment.
     * Other implementations may be added without changing
     * the direct permitted subtype set of OrderEvent.
     */
    public non-sealed interface FulfillmentEvent extends OrderEvent {
        String orderId();
    }

    public record Packed(
            String orderId, int boxCount) implements FulfillmentEvent {}

    public record Shipped(
            String orderId, String destinationCity) implements FulfillmentEvent {}

    public record CustomerPickup(
            String orderId) implements FulfillmentEvent {}

    // Java 21: exhaustive because all three direct branches are covered.
    static String describe(OrderEvent event) {
        return switch (event) {
            case Placed(var orderId, var customerId) ->
                    "placed:" + orderId + ":" + customerId;
            case Cancelled(var orderId, var reason) ->
                    "cancelled:" + orderId + ":" + reason;
            case FulfillmentEvent fulfillment ->
                    "fulfillment:" + fulfillment.orderId();
        };
    }

    // Pattern chi tiet truoc, pattern cua nhanh mo sau.
    static String detail(OrderEvent event) {
        return switch (event) {
            case Placed(var orderId, var customerId) -> "placed";
            case Cancelled(var orderId, var reason) -> "cancelled";
            case Packed(var orderId, var boxCount) ->
                    "packed:" + boxCount;
            case Shipped(var orderId, var destinationCity) ->
                    "shipped:" + destinationCity;
            case FulfillmentEvent fulfillment ->
                    "other-fulfillment:" + fulfillment.orderId();
        };
    }

    // Reflection returns direct permitted subclasses only.
    static String permittedDirectNames(Class<?> sealedType) {
        Class<?>[] directTypes = sealedType.getPermittedSubclasses();
        if (directTypes == null) return "not-sealed";

        return Arrays.stream(directTypes)
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        System.out.println(
                "root.sealed=" + OrderEvent.class.isSealed());
        System.out.println(
                "root.permits=" + permittedDirectNames(OrderEvent.class));
        System.out.println(
                "fulfillment.sealed=" + FulfillmentEvent.class.isSealed());
        System.out.println(
                "fulfillment.permits="
                        + permittedDirectNames(FulfillmentEvent.class));

        System.out.println("event1="
                + describe(new Placed("O-1", "C-1")));
        System.out.println("event2="
                + describe(new Cancelled("O-2", "duplicate")));
        System.out.println("event3="
                + describe(new Packed("O-3", 2)));

        System.out.println("detail1="
                + detail(new Packed("O-3", 2)));
        System.out.println("detail2="
                + detail(new Shipped("O-4", "Hue")));
        System.out.println("detail3="
                + detail(new CustomerPickup("O-5")));
    }
}
```

Biên dịch và chạy bằng JDK 21 hoặc mới hơn:

```bash
javac --release 21 -encoding UTF-8 PermittedSubtypeDocsDemo.java
java PermittedSubtypeDocsDemo
```

**Đầu ra chính xác:**

```text
root.sealed=true
root.permits=Cancelled,FulfillmentEvent,Placed
fulfillment.sealed=false
fulfillment.permits=not-sealed
event1=placed:O-1:C-1
event2=cancelled:O-2:duplicate
event3=fulfillment:O-3
detail1=packed:2
detail2=shipped:Hue
detail3=other-fulfillment:O-5
```

### Giải thích kết quả

- `OrderEvent.class.isSealed()` là `true`: hierarchy gốc bị giới hạn direct children.
- `getPermittedSubclasses()` trả **`Cancelled`, `FulfillmentEvent`, `Placed`** sau khi sắp xếp theo tên. **Không có `Packed` hoặc `Shipped`** vì đó là implementation gián tiếp của `OrderEvent`.
- `FulfillmentEvent.class.isSealed()` là `false` và `getPermittedSubclasses()` trả `null` với một interface không sealed; phương thức minh họa chuyển thành `"not-sealed"`.
- `describe` có ba case bao phủ ba **direct permitted branches** nên exhaustive mà không cần `default` cho các instance khác `null`.
- `detail` có các case cụ thể `Packed`, `Shipped` đặt trước case rộng `FulfillmentEvent`. `CustomerPickup` mới vẫn đi đến fallback của nhánh mở, tạo `other-fulfillment:O-5`.
- Dù ví dụ đã định nghĩa ba loại fulfillment, tài liệu của `FulfillmentEvent` không nên cam kết rằng “chỉ có ba loại”. Bất kỳ implementation hợp lệ nào của interface mở cũng thuộc họ `FulfillmentEvent`.

Ví dụ đã được kiểm chứng ở chế độ ngôn ngữ Java 21. Việc sắp xếp tên bằng `sorted()` có chủ đích: thứ tự tự nhiên của mảng trả về từ reflection **không nên coi là một hợp đồng thứ tự của API**.

## 6. Reflection giúp kiểm tra tài liệu, nhưng chỉ cho thấy một lớp thông tin

Từ Java 17, `java.lang.Class` cung cấp hai phương thức liên quan:

```java
boolean isSealed();
Class<?>[] getPermittedSubclasses();
```

Đối với một sealed class/interface:
- `isSealed()` là `true`.
- `getPermittedSubclasses()` trả danh sách các class/interface **được phép kế thừa trực tiếp**. Những class/interface này được mô tả bằng đối tượng `Class<?>`.

Đối với kiểu không sealed:
- `isSealed()` là `false`.
- `getPermittedSubclasses()` trả `null`, **không phải** một danh sách tự động chứa tất cả subtype có thể tồn tại.

Vì thế, đoạn sau là **cách kiểm tra sai**:

```java
// SAI về ý tưởng: getPermittedSubclasses() không phải
// một hàm liệt kê mọi subtype ở mọi mức trong cây.
var descendants = OrderEvent.class.getPermittedSubclasses();
// Không suy ra được ở đây rằng Packed là loại không được hỗ trợ.
```

Muốn hiểu toàn bộ cây, cần lần lượt xem từng direct permitted type:
- Nếu subtype là `final`, không còn nhánh kế thừa phía dưới kiểu ấy.
- Nếu subtype là `sealed`, xem tiếp danh sách permitted direct subtypes của nó.
- Nếu subtype là `non-sealed`, cây mở tại nhánh đó; không thể suy ra toàn bộ descendant từ `permits` của sealed root.

Một công cụ sinh tài liệu/validation dùng reflection có thể tạo danh sách **trực tiếp** cho từng sealed node. Nhưng một API có plugin implementations hoặc class được nạp động không nên tuyên bố đã thống kê đầy đủ các subtype của nhánh mở chỉ qua một lần reflection.

### Một test đơn vị để bảo vệ danh sách direct subtype

Đoạn JUnit 5 sau dựa trên lớp `PermittedSubtypeDocsDemo` và có thể đặt trong cùng package (có JUnit 5 trong test classpath):

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

class PermitsContractTest {
    @Test
    void permittedDirectTypesAreDocumented() {
        Class<?>[] permitted =
                PermittedSubtypeDocsDemo.OrderEvent.class
                        .getPermittedSubclasses();

        assertNotNull(permitted);
        Set<Class<?>> actual = Arrays.stream(permitted)
                .collect(Collectors.toSet());

        assertEquals(Set.of(
                PermittedSubtypeDocsDemo.Placed.class,
                PermittedSubtypeDocsDemo.Cancelled.class,
                PermittedSubtypeDocsDemo.FulfillmentEvent.class),
                actual);
    }

    @Test
    void fulfillmentBranchIsOpen() {
        assertFalse(
                PermittedSubtypeDocsDemo.FulfillmentEvent.class.isSealed());
        assertNull(
                PermittedSubtypeDocsDemo.FulfillmentEvent.class
                        .getPermittedSubclasses());
    }
}
```

Test đầu bảo vệ **tập subtype trực tiếp được công bố**, test thứ hai bảo vệ **chính sách nhánh mở**. Một thay đổi như bổ sung một direct subtype vào `OrderEvent` sẽ làm test đầu thất bại, nhắc người duy trì xem lại JavaDoc, switch client và chính sách versioning.

**Không phải lúc nào cũng nên khóa cứng danh sách bằng test.** Nếu API được thiết kế để thêm direct subtype ở phiên bản tương lai, test có thể là một *change detection gate* yêu cầu review/chỉnh tài liệu, không nên khiến người ta mặc định việc thêm subtype luôn sai.

## 7. Tài liệu hóa nhánh đóng, nhánh sealed tiếp và nhánh mở

Ba cách khai báo thể hiện ba chính sách khác nhau.

### 7.1. Nhánh đóng bằng record hoặc `final`

```java
sealed interface PaymentResult permits Paid, Rejected {}
record Paid(String receiptId) implements PaymentResult {}
record Rejected(String errorCode) implements PaymentResult {}
```

Cả `Paid` và `Rejected` là record, ngầm `final`. Với phiên bản này, tập concrete subtype được mô hình hóa trực tiếp là đóng, và pattern switch có thể bao phủ hai case.

Tài liệu thích hợp: “PaymentResult biểu diễn kết quả thanh toán; hai trường hợp hiện tại là `Paid` và `Rejected`. Khi thêm một trường hợp mới trong phiên bản API, client xử lý exhaustive cần được xem lại.”

### 7.2. Nhánh tiếp tục `sealed` qua nhiều tầng

```java
sealed interface Operation permits ReadOp, WriteOp {}
record ReadOp(String key) implements Operation {}

sealed interface WriteOp extends Operation permits PutOp, DeleteOp {}
record PutOp(String key, String value) implements WriteOp {}
record DeleteOp(String key) implements WriteOp {}
```

`Operation` có hai direct permitted subtypes: `ReadOp` và `WriteOp`. `WriteOp` lại có hai direct permitted subtypes: `PutOp` và `DeleteOp`.

Tài liệu nên dùng sơ đồ hoặc bảng **hai tầng**, không đưa `PutOp` thành direct permitted subtype của `Operation`.

```text
Operation (sealed)
├── ReadOp (final record)
└── WriteOp (sealed)
    ├── PutOp (final record)
    └── DeleteOp (final record)
```

### 7.3. Nhánh mở bằng `non-sealed`

```java
sealed interface Message permits TextMessage, ExtensionMessage {}
record TextMessage(String text) implements Message {}

non-sealed interface ExtensionMessage extends Message {
    String extensionId();
}
```

Tài liệu phù hợp: “`Message` chỉ cho phép hai direct subtypes; `ExtensionMessage` là **extension point** có thể có nhiều implementation khác nhau, kể cả implementation từ client nếu được API export/hiển thị hợp lệ.”

**Không được viết** “Message chỉ nhận TextMessage và ExtensionMessage như hai class có thể tạo instance”. `ExtensionMessage` là một interface và còn cho phép những kiểu con bên dưới. Khi nói “hai” phải chỉ rõ “hai **direct permitted branches**”.

## 8. Tài liệu hóa cách viết pattern switch exhaustive

Một trong những lợi ích lớn của sealed hierarchy là compiler có thể chứng minh một `switch` với pattern đã bao phủ mọi direct branch cần thiết, **không cần `default` mù**.

Dựa vào `OrderEvent` của chương trình đầy đủ:

```java
static String category(
        PermittedSubtypeDocsDemo.OrderEvent event) {
    return switch (event) {
        case PermittedSubtypeDocsDemo.Placed placed -> "placed";
        case PermittedSubtypeDocsDemo.Cancelled cancelled -> "cancelled";
        case PermittedSubtypeDocsDemo.FulfillmentEvent fulfillment ->
                "fulfillment";
    };
}
```

Đây là **đoạn minh họa** cần đặt trong một lớp Java 21 hợp lệ. Nó thể hiện ý định rõ ràng: mỗi direct permitted branch có một case.

Đối với sealed root có nhánh `non-sealed`, **không thể chỉ liệt kê những concrete implementation hiện biết** của nhánh mở rồi giả định đã exhaustive. Ví dụ:

```java
// CỐ Ý KHÔNG EXHAUSTIVE với FulfillmentEvent non-sealed.
return switch (event) {
    case Placed placed -> "placed";
    case Cancelled cancelled -> "cancelled";
    case Packed packed -> "packed";
    case Shipped shipped -> "shipped";
};
```

Mã minh họa này thiếu đường xử lý cho các implementation khác của `FulfillmentEvent`. Với switch expression Java 21, nếu compiler không chứng minh được bao phủ kiểu selector, nó báo lỗi tương tự `the switch expression does not cover all possible input values`.

Một cách phù hợp hơn:

```java
return switch (event) {
    case Placed placed -> "placed";
    case Cancelled cancelled -> "cancelled";
    case Packed packed -> "packed";
    case Shipped shipped -> "shipped";
    case FulfillmentEvent other -> "other-fulfillment";
};
```

Trong ví dụ trên, các tên `Placed`, `Cancelled`, `Packed`, `Shipped`, `FulfillmentEvent` được hiểu là các kiểu đã khai báo ở cùng lớp/đã import. **Mẫu cụ thể phải đứng trước mẫu rộng**; nếu đặt `FulfillmentEvent` lên trước `Packed` hoặc `Shipped`, các case cụ thể có thể bị che phủ (*dominated case*) và bị compiler từ chối.

**Tài liệu API nên đưa ra hướng dẫn rõ:** nếu có nhánh mở, client phải có chiến lược xử lý mọi subtype của nhánh đó, ngay cả subtype chưa tồn tại ở phiên bản thư viện hiện tại.

## 9. Đừng nhầm exhaustive với xử lý `null`

Khi dùng pattern switch Java 21:

```java
static String describe(OrderEvent event) {
    return switch (event) {
        case Placed placed -> "placed";
        case Cancelled cancelled -> "cancelled";
        case FulfillmentEvent fulfillment -> "fulfillment";
    };
}
```

Switch có thể exhaustive đối với các **instance khác null** của `OrderEvent`. Nhưng gọi `describe(null)` thông thường ném **`NullPointerException`** vì không có `case null` phù hợp.

Nếu hợp đồng API **cho phép** giá trị null:

```java
return switch (event) {
    case null -> "missing";
    case Placed placed -> "placed";
    case Cancelled cancelled -> "cancelled";
    case FulfillmentEvent fulfillment -> "fulfillment";
};
```

Đây là đoạn minh họa trong phương thức có biến `event` phù hợp. Nếu hợp đồng API cấm null, không nhất thiết thêm `case null`: có thể ghi rõ điều kiện đầu vào và dùng `Objects.requireNonNull` trong tầng thích hợp.

Với record subtype, **component null** và **selector null** là hai vấn đề khác nhau. Ví dụ `new Placed("O-1", null)` vẫn là một instance `Placed`; type pattern `case Placed p` khớp. Nhưng component có giá trị null có thể ảnh hưởng guard hoặc logic xử lý sau đó. Danh sách `permits` không tự bảo đảm tính hợp lệ của component.

Trong JavaDoc nên phân biệt:
- Những subtype nào thuộc mô hình API.
- Những điều kiện dữ liệu của subtype là hợp lệ.
- Null selector có bị từ chối hay được xử lý.
- Trường hợp giá trị thành phần không hợp lệ được kiểm tra ở constructor, accessor hay service.

Đó là các hợp đồng khác nhau, không nên trộn trong một câu “sealed nên đã an toàn”.

## 10. Viết JavaDoc có giá trị hơn một bản sao `permits`

Một JavaDoc tốt nên mô tả **semantics và extension policy**, không chỉ lặp cấu trúc compiler.

Ví dụ mẫu:

```java
/**
 * A domain event emitted for an order.
 *
 * <p>Direct permitted types:
 * {@link Placed}, {@link Cancelled}, and {@link FulfillmentEvent}.
 *
 * <p>{@code Placed} and {@code Cancelled} are final record
 * variants. {@code FulfillmentEvent} is a non-sealed extension
 * branch: clients should not assume its current concrete
 * implementations form an exhaustive set.
 *
 * @apiNote A pattern switch may handle each final record variant
 *          and include a single FulfillmentEvent branch.
 *          New concrete fulfillment variants may appear without
 *          changing this sealed parent's direct permitted set.
 * @since 17
 */
public sealed interface OrderEvent
        permits Placed, Cancelled, FulfillmentEvent {}
```

Đây là đoạn JavaDoc minh họa để đặt trong cùng mô hình type đã khai báo, không phải tệp chạy độc lập. Nó làm rõ:

1. **Mục đích domain:** sự kiện đơn hàng.
2. **Direct permitted subtypes:** tên, không nhầm với lớp con gián tiếp.
3. **Đặc điểm từng nhánh:** record final hay interface non-sealed.
4. **Hệ quả cho pattern switch:** nhánh mở cần xử lý rộng.
5. **Chính sách tiến hóa:** implementation mới có thể xuất hiện phía dưới nhánh mở.
6. **Phiên bản xuất hiện API:** `@since` là thông tin tài liệu, không phải compiler-enforced Java compatibility.

Thêm `@param` vào JavaDoc của record components khi cần giải thích ý nghĩa, đơn vị hoặc ràng buộc:

```java
/**
 * Event created when an order is packed.
 *
 * @param orderId stable identifier of the associated order
 * @param boxCount number of packed boxes, non-negative
 */
public record Packed(String orderId, int boxCount)
        implements FulfillmentEvent {}
```

Nếu ghi “non-negative” trong tài liệu, **nên có validation thực sự** hoặc mô tả rõ đây là tiền điều kiện của caller. Java không tự cấm `new Packed("O-1", -1)` chỉ vì JavaDoc nói số phải không âm.

### Các câu mô tả cần tránh

| Mô tả yếu hoặc sai | Mô tả nên dùng |
| --- | --- |
| “OrderEvent có đúng ba implementation.” | “OrderEvent cho phép ba **direct subtype**: ...” |
| “FulfillmentEvent chỉ gồm Packed và Shipped.” | “FulfillmentEvent là nhánh `non-sealed`; Packed và Shipped là các implementation hiện tại.” |
| “Mọi client phải có case cho từng lớp con.” | “Client có thể phân nhóm qua `case FulfillmentEvent`; nếu cần xử lý chi tiết, dùng case cụ thể trước nhánh tổng quát.” |
| “JavaDoc @since 17 làm code chạy trên Java 17.” | “@since 17 mô tả thời điểm API xuất hiện; compile với `--release 17` và test JVM17 để xác minh tương thích.” |
| “Đã exhaustive nên null cũng an toàn.” | “Exhaustive theo kiểu không thay thế chính sách xử lý selector `null`.” |
| “Cứ thêm subtype mới là không ảnh hưởng client.” | “Thay đổi subtype cần đánh giá lại source, binary và runtime behavior của client.” |

## 11. Kiểm tra tài liệu khi thêm, đổi hoặc loại subtype

Đối với API công khai, việc thay danh sách `permits` là thay đổi cấu trúc kiểu. Một checklist review nên đặt câu hỏi:

1. Kiểu mới là **direct subtype** của sealed parent hay **indirect subtype** của một nhánh khác?
2. Kiểu mới `final`, `sealed` hay `non-sealed`? Nếu mở nhánh, có cần công bố extension point mới không?
3. JavaDoc cho sealed parent có cập nhật đúng direct permitted set và mô tả không?
4. Các bảng/sơ đồ API có nhầm direct/indirect hoặc concrete/abstract không?
5. Các switch exhaustive của client có cần thêm case khi recompile không?
6. Có cần giữ fallback để xử lý các implementation trong nhánh non-sealed không?
7. Tập JSON/event names/serialization types có thay đổi không?
8. Có nhánh mã hoặc rule nghiệp vụ nào dựa vào giả định “chỉ có các kiểu hiện biết” không?
9. Bản phát hành này thay đổi hợp đồng source, binary hay runtime ở mức nào?
10. Đã chạy regression tests với loại mới và ít nhất một loại cũ chưa?

**Không được đánh đồng** “chỉ sửa `permits` một dòng” với “không ảnh hưởng công khai”. Một subtype mới có thể thay đổi hành vi của xử lý exhaustiveness, serializer, dispatch, persistence mapping và schema mà người dùng API phụ thuộc.

### Ví dụ: thêm một direct subtype mới

Ban đầu:

```java
sealed interface Status permits Ready, Failed {}
record Ready() implements Status {}
record Failed(String reason) implements Status {}
```

Client Java 21 có switch expression exhaustive:

```java
static String label(Status status) {
    return switch (status) {
        case Ready r -> "ready";
        case Failed f -> "failed";
    };
}
```

Sau khi API thêm `TimedOut` vào danh sách direct permitted subtypes, **mã nguồn client khi được biên dịch lại** có thể bị yêu cầu bổ sung đường xử lý, vì tập sealed đã đổi. Đây thường là cảnh báo compiler hữu ích để bắt code chưa cập nhật.

Nếu có **separate compilation** (client cũ chưa biên dịch lại nhưng runtime dùng thư viện mới), một switch đã được biên dịch dựa trên tập subtype cũ có thể gặp giá trị mới chưa được xử lý và ném **`MatchException`** ở runtime trong Java 21. Đây là tình huống phụ thuộc phiên bản/đường nạp class; không nên khẳng định mọi trường hợp nâng thư viện đều ném đúng exception này, nhưng là rủi ro phải có trong chiến lược kiểm thử.

**Tài liệu versioning nên nói rõ** liệu việc thêm direct subtype được coi là breaking change đối với client exhaustive, hoặc API có chính sách buộc client dành một fallback thích hợp.

### Ngược lại: thêm subtype dưới nhánh non-sealed

Với `OrderEvent` và `FulfillmentEvent` trong ví dụ chính, thêm `CustomerPickup` dưới `FulfillmentEvent` **không cần thêm tên vào `OrderEvent permits`**. Client có case `FulfillmentEvent fulfillment` vẫn xử lý được instance mới theo nhánh tổng quát.

Nhưng vẫn phải kiểm thử:
- Nếu client cần phân biệt `CustomerPickup`, họ phải thêm case cụ thể trước case tổng quát.
- Serialization/deserialization có thể cần mapping tên loại mới.
- Tài liệu enum-like “Supported fulfillment events” phải ghi rõ đó là danh sách ví dụ hay chính sách API giới hạn.
- Nếu client xử lý mọi `FulfillmentEvent` bằng logic giả định chỉ có `Packed` và `Shipped`, có thể phát sinh lỗi nghiệp vụ dù Java compiler vẫn cho phép.

Một nhánh mở là **cam kết về khả năng mở rộng kiểu**, không phải bảo đảm mọi client sẽ tự xử lý chính xác semantics của biến thể mới.

## 12. Public API, Java version và mô tả mức hỗ trợ

Các sealed constructs được Java 17 hỗ trợ chính thức:

```java
public class SealedPermitJava17 {
    public sealed interface Signal permits Started, Stopped {}
    public record Started(String id) implements Signal {}
    public record Stopped(String id) implements Signal {}

    static String label(Signal signal) {
        if (signal instanceof Started started) {
            return "started:" + started.id();
        }
        if (signal instanceof Stopped stopped) {
            return "stopped:" + stopped.id();
        }
        return "other";
    }

    public static void main(String[] args) {
        System.out.println(label(new Started("S-17")));
    }
}
```

Chạy bằng JDK có hỗ trợ target 17:

```bash
javac --release 17 -encoding UTF-8 SealedPermitJava17.java
java SealedPermitJava17
```

Đầu ra:

```text
started:S-17
```

Ở mức Java 17, client có thể dùng `instanceof` type patterns và sealed hierarchy. Khi mục tiêu sử dụng là **pattern switch exhaustive với record deconstruction**, yêu cầu ngôn ngữ Java 21 (dù hierarchy sealed có thể đã tồn tại trong artifact Java 17).

Vì vậy JavaDoc nên phân biệt:
- API sealed ra mắt từ Java 17 (`@since` có thể ghi release của thư viện).
- Các ví dụ xử lý bằng `switch` với type/record patterns cần Java 21+.
- Tập subtype được phép là ràng buộc API; cú pháp để consume API phụ thuộc phiên bản Java mà client biên dịch.

Không nên đưa một ví dụ `case Placed(var id, var customer)` vào hướng dẫn “Java 17 compatible” mà không đánh dấu đó là cú pháp Java 21.

## 13. Trường hợp lỗi compile giúp kiểm tra ràng buộc thật

### 13.1. Thiếu `sealed`/`non-sealed` ở direct subtype

Đoạn sau **cố ý không biên dịch**:

```java
sealed interface Root permits Open {}
interface Open extends Root {}
```

Compiler Java 21 có thể báo dạng:

```text
sealed or non-sealed modifiers expected
```

Lý do: `Open` là direct subtype của `Root` nhưng không xác định một trong hai trạng thái `sealed`/`non-sealed` (interface không thể `final`). Sửa thành:

```java
sealed interface Root permits Open {}
non-sealed interface Open extends Root {}
```

Khi tài liệu nói “Open là nhánh mở” nhưng mã quên `non-sealed`, compiler phát hiện. Ngược lại, khi code có `non-sealed` mà JavaDoc lại khẳng định “toàn bộ subtype đã được liệt kê”, tài liệu sai dù code biên dịch.

### 13.2. Liệt kê indirect subtype trong `permits`

Đoạn sau **cố ý không biên dịch**:

```java
sealed interface Root permits Direct, Indirect {}
non-sealed interface Direct extends Root {}
final class Indirect implements Direct {}
```

`Indirect` không trực tiếp `implements Root`, nên không thể là direct permitted subtype của `Root`. Bản đúng chỉ liệt kê `Direct`:

```java
sealed interface Root permits Direct {}
non-sealed interface Direct extends Root {}
final class Indirect implements Direct {}
```

Hãy dùng **compiler check** để phát hiện cấu trúc sai; không giải quyết bằng cách thêm tên vào JavaDoc mà bỏ qua lỗi kiểu.

### 13.3. Cố thêm class mới implement sealed parent

Nếu `OrderEvent` chỉ permits `Placed, Cancelled, FulfillmentEvent`, một class mới:

```java
// SAI: không nằm trong danh sách direct permitted types của OrderEvent.
final class ExtraOrderEvent implements OrderEvent {}
```

không được phép trực tiếp triển khai `OrderEvent`. Nếu đây là sự kiện thuộc họ fulfillment, implement `FulfillmentEvent` (khi hợp đồng và các phương thức yêu cầu phù hợp) là con đường mở rộng đã được thiết kế. Nếu là một nhóm sự kiện mới, chủ API phải xem xét bổ sung direct permitted subtype, công bố tác động và cập nhật tài liệu.

## 14. Sinh tài liệu và hướng dẫn tiêu thụ API

Với tài liệu public API, nên cung cấp kết hợp:

**Mô tả tự nhiên:** vì sao kiểu sealed tồn tại, giới hạn ở direct subtypes nào, nhánh nào mở, ý nghĩa nghiệp vụ của từng nhánh.

**Sơ đồ hoặc bảng:** dễ đọc hơn một `permits` dài có nhiều tầng, thể hiện rõ sealed/non-sealed/final và quan hệ trực tiếp/gián tiếp.

**JavaDoc liên kết:** dùng `{@link TypeName}`, `@apiNote`, `@since` và `@param` cho record components khi phù hợp. Đừng sao chép danh sách bằng các link sai package hoặc một trang docs không được cập nhật khi thêm subtype.

**Ví dụ xử lý hợp lệ:** nếu công bố các case dùng cho Java 21, có một switch exhaustive theo direct branches; nếu hỗ trợ Java 17, có thêm ví dụ dựa trên `instanceof`. Phải ghi rõ baseline.

**Hướng dẫn mở rộng:** nếu có non-sealed extension point, nêu phương thức tối thiểu cần implement, quy tắc ổn định, validation và vùng mở rộng được hỗ trợ. Không gợi ý người dùng trực tiếp implement sealed parent từ module ngoài.

**Quy tắc versioning:** khi nào thêm subtype là thay đổi đáng chú ý, client cần làm gì khi nâng cấp, test nào phát hiện hierarchy mới.

**Thông tin runtime:** `getPermittedSubclasses()` chỉ cho thấy direct permitted subtypes, không phải discovery mechanism hoàn chỉnh cho mọi provider/implementation của một open branch.

Một bản JavaDoc tốt không nhất thiết dài. Mục tiêu là người dùng API hiểu **được phép tạo kiểu gì, compiler chứng minh gì, và đâu là điều API vẫn có thể thay đổi**.

## 15. Đề xuất test cho API đóng và nhánh mở

Bên cạnh reflection test ở mục 6, có thể dùng behavior tests để xác minh cách client xử lý từng nhánh.

### Test các direct branches

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class OrderEventContractTest {
    @Test
    void sealedBranchesHaveExpectedBehavior() {
        assertAll(
                () -> assertEquals("placed:O-1:C-1",
                        PermittedSubtypeDocsDemo.describe(
                                new PermittedSubtypeDocsDemo.Placed("O-1", "C-1"))),
                () -> assertEquals("cancelled:O-2:duplicate",
                        PermittedSubtypeDocsDemo.describe(
                                new PermittedSubtypeDocsDemo.Cancelled(
                                        "O-2", "duplicate"))),
                () -> assertEquals("fulfillment:O-3",
                        PermittedSubtypeDocsDemo.describe(
                                new PermittedSubtypeDocsDemo.Packed("O-3", 2)))
        );
    }

    @Test
    void openBranchHasGenericFallback() {
        assertEquals("other-fulfillment:O-5",
                PermittedSubtypeDocsDemo.detail(
                        new PermittedSubtypeDocsDemo.CustomerPickup("O-5")));
    }
}
```

Đây là **lớp JUnit 5 minh họa**, cần JUnit test classpath và đặt cùng package hoặc điều chỉnh accessibility. Không phải một phần của chương trình standalone `PermittedSubtypeDocsDemo.java`.

Các test này kiểm chứng:
- Những subtype trực tiếp `Placed`/`Cancelled` có hành vi đúng.
- Nhánh `FulfillmentEvent` xử lý được implementation của nó.
- Case cụ thể và fallback mở được phân biệt bằng `detail`.

### Test thay đổi API bằng compile checks

Ngoài test runtime, kiểm tra những điều sau trong CI:
1. Mã thư viện tự nó **biên dịch thành công** với `--release` đã công bố.
2. Direct subtype mới phải được cấp quyền bởi sealed parent; subtype sai cấu trúc bị compiler từ chối.
3. Các ví dụ trong JavaDoc/guides (nếu có code executable) được compile/test với Java release tương ứng.
4. Client mẫu dùng exhaustive `switch` được biên dịch lại khi cập nhật phiên bản API để lộ nhánh mới cần xử lý.
5. Các regression tests với phiên bản cũ và phiên bản mới phân biệt binary loading, runtime behavior và serialization compatibility.

Một bài test chỉ assert số lượng `getPermittedSubclasses().length == 3` chưa chắc đủ: đổi một subtype thành kiểu khác nhưng giữ nguyên số lượng vẫn khiến test xanh. So sánh **tập kiểu thực tế**, không chỉ độ dài mảng.

## 16. Checklist tài liệu hóa trước khi phát hành

| Câu hỏi cần trả lời | Dấu hiệu tài liệu tốt |
| --- | --- |
| Sealed parent biểu diễn domain nào? | Có mục đích nghiệp vụ, không chỉ liệt kê class |
| Direct permitted subtypes là gì? | Danh sách/bảng chính xác với `permits` |
| Có nhánh `non-sealed` không? | Được mô tả rõ là extension point |
| Có nhánh `sealed` nhiều tầng không? | Có sơ đồ tầng, không nhầm direct với indirect |
| Có record hoặc final class không? | Ghi rõ đó là nhánh kết thúc kế thừa |
| Client có quyền tự implement ở đâu? | Chỉ đúng interface/class mở và visibility/module hợp lệ |
| Với Java 21, switch exhaustive thế nào? | Có ví dụ bao phủ direct branches, nhánh mở có case rộng |
| Với Java 17, hướng dẫn tiêu thụ là gì? | Dùng `instanceof` type patterns/accessors, không lẫn record patterns |
| Null selector và dữ liệu thành phần xử lý ra sao? | Nêu hợp đồng null riêng |
| Thêm subtype mới có breaking change không? | Có chính sách versioning và hướng dẫn migrate |
| Reflection trả thông tin gì? | Nêu rõ chỉ direct permitted subtypes |
| JavaDoc có liên kết, phiên bản và component contract? | Có `{@link}`, `@since`, `@param` khi cần |
| Test nào bảo vệ hợp đồng? | Reflection set + behavior cases + compile/runtime tests |
| Tài liệu đã khớp mã bản phát hành? | Có bước review/check tự động thích hợp |

Nếu chỉ có thời gian sửa một điểm tài liệu, ưu tiên một câu chính xác: **“Các kiểu trong `permits` là những direct subtype được phép; bất kỳ nhánh `non-sealed` nào vẫn có thể được mở rộng.”** Đây là điểm làm nhiều API sealed bị mô tả sai nhất.

## 17. Những lỗi phổ biến

### 17.1. Gọi toàn bộ descendant là “permitted”

`Packed` có thể là `OrderEvent` theo quan hệ kiểu, nhưng không phải direct permitted subtype của `OrderEvent` trong mô hình trên. Tài liệu nên dùng “indirect implementation” hoặc “concrete variant of the fulfillment branch”.

### 17.2. Mặc định `non-sealed` nghĩa là chỉ có các implementation hiện biết

`non-sealed` cho phép mở rộng tiếp. Nếu khách hàng xây logic dựa trên danh sách hiện tại mà không có fallback, họ có thể gặp subtype mới về sau.

### 17.3. Thêm `default` để che mọi thay đổi API

Một switch exhaustive trên sealed hierarchy đóng, viết case tường minh thường giúp compiler nhắc khi có subtype mới. `default` có thể che tín hiệu ấy. Với nhánh non-sealed, case cho chính nhánh rộng thường có ý nghĩa hơn một `default` vô danh vì vẫn thể hiện nhóm nghiệp vụ được nhận diện.

### 17.4. Giả định sealed parent không bao giờ đổi

Sealed là luật kế thừa **của artifact hiện tại**, không phải lời cam kết không tiến hóa. Thêm direct subtype, đổi modifier hay đóng nhánh mở cần chính sách phát hành và kiểm thử tương thích.

### 17.5. Nhầm API contract với runtime enumeration

`getPermittedSubclasses()` là reflection cho direct permitted set; nó không quét classpath tìm mọi implementation bên dưới một nhánh non-sealed. Muốn discovery provider, cần một cơ chế riêng (cấu hình, ServiceLoader, registry...) nếu nghiệp vụ đòi hỏi.

### 17.6. JavaDoc chỉ lặp cú pháp

“`OrderEvent permits A, B, C`” không giải thích vì sao mỗi biến thể tồn tại, client xử lý thế nào, null ra sao, nhánh nào mở và versioning có ảnh hưởng gì. Bổ sung đúng những ý nghĩa chưa được compiler biểu diễn.

### 17.7. Công bố ví dụ Java 21 như mã hỗ trợ Java 17

Sealed hierarchy tồn tại từ Java 17, nhưng pattern switch và record patterns chính thức từ Java 21. Ghi rõ mức Java của từng ví dụ và chạy `javac --release` tương ứng.

### 17.8. Đổi trực tiếp subtype mà không đánh giá external client

Khi thêm direct subtype, người duy trì có thể làm client exhaustive thiếu case khi recompile, hoặc gặp giá trị bất ngờ lúc runtime riêng phiên bản. Cần kiểm thử và thông báo thay đổi, không chỉ sửa Javadoc.

### 17.9. Nói “client có thể implement sealed parent” sai module

Với named module, direct permitted implementation phải ở cùng module với sealed parent. Client ngoài module không thể tự nhiên trở thành direct subtype; hãy chỉ đúng nhánh `non-sealed` công khai nếu muốn hỗ trợ extension.

### 17.10. Tên subtype không phản ánh domain

`Status1`, `Status2` hoặc `EventX` khiến pattern switch khó đọc dù compiler exhaustive. Đặt tên `Placed`, `Cancelled`, `FulfillmentEvent` theo nghiệp vụ, và mô tả rõ trạng thái/ý nghĩa cho người đọc API.

## 18. Bài tập và đáp án

**Bài 1 — Direct hay indirect?** Cho `sealed interface Root permits A, Open`, `record A() implements Root`, `non-sealed interface Open extends Root`, `record B() implements Open`. Những kiểu nào nằm trong direct permitted set của `Root`?

**Đáp án:** `A` và `Open`. `B` là indirect subtype qua `Open`; không nằm trong `Root.permits`.

**Bài 2 — Nhánh mở có hết subtype không?** Nếu hiện có `B` và `C` implements `Open`, có thể tài liệu hóa “`Open` chỉ có B và C” như invariant không?

**Đáp án:** không, trừ khi có ràng buộc ngoài ngôn ngữ bảo đảm điều đó và tài liệu nói rõ. `Open` là non-sealed, cho phép thêm implementation.

**Bài 3 — Modifier.** Một interface trực tiếp extends sealed interface nhưng chỉ viết `interface Child extends Parent` có hợp lệ không?

**Đáp án:** không trong trường hợp Child là direct permitted interface; phải khai báo `sealed` hoặc `non-sealed` theo quy tắc ngôn ngữ. Record direct subtype là final ngầm định.

**Bài 4 — Exhaustive switch.** Có các direct permitted branches `Placed`, `Cancelled`, `FulfillmentEvent` (non-sealed). Liệt kê `Placed`, `Cancelled`, `Packed` và `Shipped` có đủ exhaustive không?

**Đáp án:** không; `FulfillmentEvent` có thể còn implementation khác. Cần case rộng `FulfillmentEvent` hoặc một đường bao phủ hợp lệ khác.

**Bài 5 — Reflection.** Vì sao `OrderEvent.class.getPermittedSubclasses()` không trả `Packed` trong chương trình mẫu?

**Đáp án:** vì `Packed` chỉ trực tiếp implements `FulfillmentEvent`. Reflection trên `OrderEvent` trả direct permitted types, không phải mọi descendant.

**Bài 6 — Named module.** Một plugin trong module khác có thể direct implements `OrderEvent` sealed từ module thư viện không?

**Đáp án:** không, nếu không phải direct permitted subtype cùng module. Nếu API có nhánh công khai `non-sealed FulfillmentEvent`, plugin có thể triển khai nhánh đó khi đáp ứng visibility/hợp đồng.

**Bài 7 — API evolution.** Vì sao thêm direct subtype mới có thể làm client Java 21 fail khi recompile?

**Đáp án:** switch expression previously exhaustive theo tập cũ có thể không còn bao phủ toàn bộ direct branches. Compiler yêu cầu case mới hoặc fallback phù hợp.

**Bài 8 — Binary/runtime.** Một client cũ đã biên dịch trên sealed hierarchy cũ, sau đó dùng thư viện có subtype mới. Có chắc luôn chạy đúng không?

**Đáp án:** không. Với separate compilation, switch đã được biên dịch exhaustive có thể gặp subtype mới chưa xử lý và ném `MatchException` khi được thực thi. Cần kiểm thử tương thích, không chỉ dựa vào compile pass của thư viện mới.

**Bài 9 — Null.** Switch exhaustive trên `OrderEvent` gồm `Placed`, `Cancelled`, `FulfillmentEvent` nhưng không có `case null`. `describe(null)` có tự vào nhánh nào không?

**Đáp án:** thường ném `NullPointerException`. Tập subtype cho phép không tự định nghĩa chính sách null.

**Bài 10 — Viết JavaDoc.** Viết một câu đúng để mô tả hierarchy `OrderEvent` có nhánh mở.

**Đáp án tham khảo:** “OrderEvent là sealed interface cho phép trực tiếp Placed, Cancelled và FulfillmentEvent; FulfillmentEvent là non-sealed extension point, vì vậy tập concrete fulfillment events có thể mở rộng.”

**Bài 11 — Java version.** Sealed hierarchy trên dùng được từ Java nào? Còn `case Packed(var id, var count)` với record pattern?

**Đáp án:** sealed types chính thức từ Java 17; record pattern kết hợp pattern switch chính thức Java 21. Client cần chọn `--release` phù hợp và test trên runtime hỗ trợ.

**Bài 12 — Review thay đổi.** Khi một developer thêm `Returned` implements `FulfillmentEvent`, cần sửa `OrderEvent permits` không?

**Đáp án:** không, vì `FulfillmentEvent` là nhánh non-sealed được phép. Nhưng cần đánh giá tài liệu liệt kê các fulfillment variants, serialization, domain behavior và regression tests cho sự kiện mới.

## 19. Ghi nhớ

- Danh sách `permits` của sealed type xác định **direct permitted subtypes**, không tự liệt kê mọi indirect/concrete subtype.
- Direct subtype phải kết thúc bằng `final` (record là final ngầm định), tiếp tục kiểm soát bằng `sealed` hoặc mở rộng bằng `non-sealed`.
- Với **named module**, direct permitted subtypes phải cùng module; với **unnamed module**, cùng package.
- **JavaDoc phải nêu ý nghĩa nghiệp vụ, mức đóng/mở của từng nhánh và chính sách tiến hóa**, không chỉ chép lại cú pháp.
- **`non-sealed`** là extension point thực sự; khi dùng pattern switch, hãy bao phủ cả nhánh mở thay vì chỉ các concrete implementation hiện biết.
- `Class.isSealed()` và `Class.getPermittedSubclasses()` giúp xác minh **direct permitted set**; phương thức thứ hai không phải công cụ quét mọi subtype.
- **Sealed API từ Java 17; pattern switch/record patterns chính thức từ Java 21.** Ghi rõ baseline Java của ví dụ.
- Một switch exhaustive vẫn phải có hợp đồng riêng cho **selector null** và các giá trị thành phần không hợp lệ.
- Khi thay đổi direct permitted set, đánh giá **source recompilation**, **runtime với separate compilation**, serialization và migration cho client.
- Kiểm thử tốt gồm **reflection set**, behavior của các branch, compile tests và regression tests cho biến thể mới.

**Tham khảo chính thức:**
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java SE 21 API — Class.getPermittedSubclasses()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses())
- [Java Language Specification 21 — Classes (`8)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html)
- [Java Language Specification 21 — Interfaces (`9)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html)
