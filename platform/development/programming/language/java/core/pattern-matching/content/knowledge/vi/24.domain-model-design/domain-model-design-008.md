# Mở rộng type hierarchy có kiểm soát trong thiết kế domain model Java

## 1. Bài toán: thêm kiểu nghiệp vụ mà không làm mất tính nhất quán

Một domain model thường chứa **nhiều biến thể của cùng một khái niệm**: một đơn hàng có thể phát sinh sự kiện `Placed`, `Paid`, `Cancelled`; một kết quả thanh toán có thể là `Approved` hoặc `Rejected`; một biểu thức có thể là hằng số hoặc phép cộng.

Nếu chỉ dùng interface thông thường:

```java
interface OrderEvent {}
```

bất kỳ class nào có quyền truy cập interface đó đều có thể `implements OrderEvent`. Điều này hữu ích cho hệ thống plugin, nhưng đặt ra câu hỏi cho domain hữu hạn: **có những biến thể nào hợp lệ, và mã xử lý đã bao phủ hết chúng chưa?**

Từ Java 17, **sealed classes/interfaces** (JEP 409) cho phép chủ sở hữu khai báo **tập các subtype trực tiếp được phép tồn tại**. Từ Java 21, **pattern matching for `switch`** (JEP 441) và **record patterns** (JEP 440) phối hợp với sealed hierarchy để compiler phát hiện thiếu nhánh xử lý khi mở rộng domain.

**Mở rộng có kiểm soát** không có nghĩa hierarchy không bao giờ thay đổi. Nó có nghĩa mọi subtype mới cần được cân nhắc tại một vị trí sở hữu rõ ràng; các nơi tiêu thụ dữ liệu có cơ hội được compiler yêu cầu cập nhật; và các ràng buộc nghiệp vụ được giữ vững.

## 2. `sealed`, `permits`, `final` và `non-sealed`

Ví dụ một cây kiểu:

```java
sealed interface OrderEvent
        permits Placed, Paid, Cancelled {}

record Placed(String orderId) implements OrderEvent {}
record Paid(String orderId, long amountCents) implements OrderEvent {}
record Cancelled(String orderId, String reason) implements OrderEvent {}
```

- `sealed interface OrderEvent` nói rằng **không phải class/interface tùy ý** đều được phép trực tiếp `implements`/`extends` nó.
- `permits Placed, Paid, Cancelled` là **danh sách các subtype trực tiếp** được công nhận.
- Ba `record` là subtype trực tiếp; vì record mặc nhiên **`final`**, chúng không thể bị subclass tiếp.
- Không có subtype thứ tư nào được trực tiếp `implements OrderEvent` nếu không được cho phép trong `permits`.

Khi một class **trực tiếp** kế thừa sealed class hoặc implements sealed interface, Java yêu cầu nó chọn rõ một trong các hướng: `final`, `sealed`, `non-sealed` (record/enum có quy tắc ngầm tương ứng). Với **subinterface** trực tiếp, hai lựa chọn phù hợp là `sealed` hoặc `non-sealed` vì interface không thể là `final`.

| Cơ chế | Phạm vi mở rộng | Dùng khi |
| --- | --- | --- |
| `final class` / `record` | Không cho subclass bên dưới | Biến thể domain đã hoàn chỉnh |
| `sealed class/interface` | Chỉ cho subtype trực tiếp đã được cho phép; có thể kiểm soát tiếp các tầng sâu hơn | Danh mục biến thể ổn định, có chủ sở hữu |
| `non-sealed class/interface` | Mở lại quyền mở rộng từ nhánh đó | Cần nhánh extension có chủ đích |
| Class/interface thông thường | Mở rộng bình thường theo quyền truy cập của Java | Thiết kế plugin hoặc hệ thống mở không có tập subtype cố định |

**`permits` áp dụng cho subtype trực tiếp, không liệt kê mọi hậu duệ trong cả cây.** Ví dụ một subtype trực tiếp là `sealed` có thể sở hữu `permits` ở tầng tiếp theo; một subtype `non-sealed` cho phép phát triển tiếp bên dưới nhánh đó.

## 3. Ví dụ hoàn chỉnh: sealed hierarchy kết hợp pattern `switch`

Lưu mã trong `SealedOrderDemo.java`:

```java
public class SealedOrderDemo {
    sealed interface OrderEvent
            permits Placed, Paid, Cancelled {}

    record Placed(String orderId) implements OrderEvent {}
    record Paid(String orderId, long amountCents) implements OrderEvent {}
    record Cancelled(String orderId, String reason)
            implements OrderEvent {}

    static String describe(OrderEvent event) {
        return switch (event) {
            case Placed(var id) ->
                    "placed:" + id;

            case Paid(var id, var cents) ->
                    "paid:" + id + ":" + cents;

            case Cancelled(var id, var reason) ->
                    "cancelled:" + id + ":" + reason;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Placed("O-17")));
        System.out.println(describe(new Paid("O-17", 250)));
        System.out.println(describe(
                new Cancelled("O-17", "customer")));
    }
}
```

Chạy bằng **JDK 21 trở lên**:

```bash
javac --release 21 SealedOrderDemo.java
java SealedOrderDemo
```

Kết quả:

```text
placed:O-17
paid:O-17:250
cancelled:O-17:customer
```

Điểm quan trọng ở `describe` là `switch` **không có `default`**. Compiler có thể chứng minh biểu thức `switch` là *exhaustive*: mọi subtype có thể có của `OrderEvent` đều thuộc một trong ba kiểu record đã liệt kê. `case Placed(var id)` hay `case Paid(var id, var cents)` vừa chọn loại sự kiện, vừa giải cấu trúc các component theo record pattern.

Với đầu vào có kiểu tĩnh `OrderEvent`, đây là một lợi ích thiết kế lớn: khi danh mục sự kiện thay đổi, nhánh xử lý bị thiếu có thể lộ ra lúc **biên dịch**, thay vì nằm im đến khi hệ thống nhận được dữ liệu mới.

**Lưu ý `null`:** exhaustive theo tập subtype không có nghĩa selector `null` cũng tự khớp. Nếu gọi `describe(null)`, `switch` trong ví dụ sẽ ném `NullPointerException`. Có thể thêm `case null -> ...` nếu nghiệp vụ cho phép `null`, hoặc kiểm tra không-null ở ranh giới API.

## 4. Mở rộng hierarchy: thêm biến thể `Refunded`

Giả sử domain có thêm sự kiện **hoàn tiền**. Thay đổi không chỉ là tạo file/class mới:

```java
// Dạng thay đổi về ý tưởng:
sealed interface OrderEvent
        permits Placed, Paid, Cancelled, Refunded {}

record Refunded(String orderId, long amountCents)
        implements OrderEvent {}
```

Sau khi thêm `Refunded` vào `permits`, `switch` cũ chỉ có ba `case` **không còn exhaustive** khi biên dịch lại cùng hierarchy mới. Với biểu thức `switch` không có `default`, javac báo lỗi kiểu:

```text
the switch expression does not cover all possible input values
```

Lỗi này là **hàng rào kiểm soát thay đổi**: chủ sở hữu domain đã mở rộng tập subtype, còn nơi dùng `switch` vẫn đang giả định tập cũ. Thêm nhánh xử lý có ý nghĩa nghiệp vụ sẽ sửa được vấn đề:

```java
case Refunded(var id, var cents) ->
        "refunded:" + id + ":" + cents;
```

Đây là cập nhật cần xem xét, vì hoàn tiền có thể yêu cầu thêm kế toán, gửi thông báo hoặc ghi nhận trạng thái; Java chỉ biết subtype mới cần được xử lý, **không thể tự quyết định nghiệp vụ**.

### Ví dụ chạy được sau khi mở rộng

Lưu vào `EvolvedOrderDemo.java`:

```java
public class EvolvedOrderDemo {
    sealed interface OrderEvent
            permits Placed, Paid, Cancelled, Refunded {}

    record Placed(String orderId) implements OrderEvent {}
    record Paid(String orderId, long amountCents) implements OrderEvent {}
    record Cancelled(String orderId, String reason)
            implements OrderEvent {}
    record Refunded(String orderId, long amountCents)
            implements OrderEvent {}

    static String describe(OrderEvent event) {
        return switch (event) {
            case Placed(var id) ->
                    "placed:" + id;
            case Paid(var id, var cents) ->
                    "paid:" + id + ":" + cents;
            case Cancelled(var id, var reason) ->
                    "cancelled:" + id + ":" + reason;
            case Refunded(var id, var cents) ->
                    "refunded:" + id + ":" + cents;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(
                new Refunded("O-17", 100)));
    }
}
```

```bash
javac --release 21 EvolvedOrderDemo.java
java EvolvedOrderDemo
```

Kết quả:

```text
refunded:O-17:100
```

Vậy quy trình nâng cấp không chỉ là sửa `permits`: **khai báo subtype mới → bổ sung quy tắc nghiệp vụ → tìm/cập nhật các consumer → biên dịch lại → kiểm thử từng variant**.

## 5. Tại sao không nên vội thêm `default`?

Khi xuất hiện lỗi thiếu nhánh sau khi thêm subtype, cách chữa nhanh là:

```java
static String describe(OrderEvent event) {
    return switch (event) {
        case Placed(var id) -> "placed:" + id;
        case Paid(var id, var cents) -> "paid:" + id;
        default -> "other";
    };
}
```

Đây là **đoạn minh họa trong ngữ cảnh đã khai báo `OrderEvent`, `Placed` và `Paid`**.

`default` khiến `switch` có nhánh dự phòng cho các trường hợp chưa liệt kê, nhưng **đồng thời che đi cảnh báo thiếu xử lý subtype mới**. Nếu nghiệp vụ thực sự cần logic riêng cho `Refunded`, `default -> "other"` sẽ khiến sự kiện hoàn tiền bị xử lý như “khác”.

Với hierarchy mà mỗi subtype có ý nghĩa nghiệp vụ riêng, thường nên **liệt kê từng case và bỏ `default`** để việc thêm subtype buộc các consumer rà soát. Với một API cần xử lý mọi biến thể theo một quy tắc chung, `default` có thể hợp lý, nhưng quyết định này phải có chủ đích.

Một quy tắc review hữu ích: hỏi **“consumer có cần phân biệt variant mới không?”** trước khi dùng `default` cho hết lỗi biên dịch.

## 6. `non-sealed`: mở đúng nhánh cần extension

Có khi domain cần cho phép plugin mở rộng, nhưng vẫn muốn bảo vệ những phần lõi. Khi ấy, tạo một nhánh **`non-sealed` có chủ đích** thường rõ ràng hơn việc bỏ `sealed` ở root.

Lưu vào `ControlledExtensionDemo.java`:

```java
public class ControlledExtensionDemo {
    sealed interface DomainAction
            permits Create, Remove, ExtensionAction {}

    record Create(String id) implements DomainAction {}
    record Remove(String id) implements DomainAction {}

    non-sealed interface ExtensionAction extends DomainAction {}

    record PluginAction(String key) implements ExtensionAction {}

    static String route(DomainAction action) {
        return switch (action) {
            case Create(var id) ->
                    "create:" + id;
            case Remove(var id) ->
                    "remove:" + id;
            case ExtensionAction other ->
                    "extension:" + other.getClass().getSimpleName();
        };
    }

    public static void main(String[] args) {
        System.out.println(route(new Create("a")));
        System.out.println(route(new Remove("b")));
        System.out.println(route(new PluginAction("x")));
    }
}
```

```bash
javac --release 21 ControlledExtensionDemo.java
java ControlledExtensionDemo
```

Kết quả:

```text
create:a
remove:b
extension:PluginAction
```

Giải thích:

- Root `DomainAction` chỉ cho ba subtype trực tiếp: `Create`, `Remove`, `ExtensionAction`.
- `Create`, `Remove` là record (`final`), nên biến thể lõi đóng.
- `ExtensionAction` là interface `non-sealed`: các class/record khác có thể `implements ExtensionAction` mà không cần thay đổi `permits` của `DomainAction`.
- `case ExtensionAction other` bao phủ **mọi subtype** ở nhánh mở, vì vậy `switch` vẫn exhaustive ở cấp `DomainAction`.

Điểm đánh đổi: compiler **không buộc viết case riêng** cho từng plugin dưới `ExtensionAction`. Nếu một plugin mới cần xử lý riêng, trách nhiệm định tuyến, xác thực hợp đồng và quản lý phiên bản thuộc phần kiến trúc extension. Một nhánh `non-sealed` chỉ nên xuất hiện khi thực sự có yêu cầu mở rộng độc lập.

Không nên dùng `non-sealed` như giải pháp mặc định để bỏ qua danh sách `permits`, vì làm mất khả năng kiểm soát tập subtype ở nhánh đó.

## 7. Kiểm soát cả tầng trung gian của hierarchy

Mô hình nhiều tầng có thể hữu ích khi biến thể domain có nhóm lớn nhỏ:

```java
sealed interface PaymentEvent
        permits Settled, Adjustment {}

record Settled(String paymentId) implements PaymentEvent {}

sealed interface Adjustment extends PaymentEvent
        permits Refund, Chargeback {}

record Refund(String paymentId) implements Adjustment {}
record Chargeback(String paymentId) implements Adjustment {}
```

Đây là **ví dụ khai báo kiểu** có thể đặt cùng một compilation unit (một file không chứa public type). Mọi subtype trực tiếp của `PaymentEvent` phải là `Settled` hoặc `Adjustment`. Nhánh `Adjustment` lại có danh sách con cố định là `Refund` và `Chargeback`.

Khi compiler phân tích exhaustive `switch` trên `PaymentEvent`, nó có thể sử dụng thông tin đóng của các nhánh đã `sealed`. Tuy nhiên, nếu thay `Adjustment` bằng `non-sealed`, danh sách hậu duệ của nhánh ấy mở, nên một `switch` xử lý riêng `Refund` và `Chargeback` **chưa chắc exhaustive** đối với `PaymentEvent`. Khi cần bao phủ nhánh mở, một `case Adjustment adjustment -> ...` có thể là lựa chọn đúng.

Cần phân biệt **subtype trực tiếp** (được `permits` ở tầng cha) với **subtype gián tiếp** (đi qua nhánh đã được phép). Không đưa mọi lớp con của `Adjustment` vào `PaymentEvent permits` nếu chúng không trực tiếp `implements PaymentEvent`.

## 8. Quy tắc đóng gói: module và package

Danh sách `permits` không cho phép tạo subtype ở bất kỳ đâu. Java đặt giới hạn quan trọng:

- Nếu sealed type thuộc một **named module**, các subtype trực tiếp được cho phép phải thuộc **cùng module**. Chúng có thể ở package khác trong module đó khi tuân thủ các quy tắc truy cập.
- Nếu sealed type thuộc **unnamed module**, các subtype trực tiếp được phép phải ở **cùng package** với sealed type.
- Mỗi subtype trong `permits` phải thực sự là **subtype trực tiếp** của sealed type.
- Nếu không ghi `permits`, Java có thể suy luận danh sách khi các subtype trực tiếp có tên chuẩn được khai báo **trong cùng compilation unit**. Với hệ thống lớn, `permits` tường minh thường dễ review hơn khi chủ đích là kiểm soát mở rộng.

Ví dụ, thêm `com.partner.ExternalEvent implements OrderEvent` từ một module hoàn toàn khác vào hierarchy `sealed` đã định nghĩa ở module hiện tại **không phải cách tạo plugin hợp lệ** chỉ bằng cách cập nhật `permits`. Nếu cần extension xuyên module, nên thiết kế ranh giới bằng một API mở, SPI, adapter, hoặc nhánh `non-sealed` phù hợp.

Do đó, quyết định `sealed` có liên hệ trực tiếp với **quyền sở hữu domain model**: ai được sửa tập biến thể, nhóm nào cần đồng bộ và subtype nằm ở module/package nào.

## 9. Sealed hierarchy không thay thế bất biến nghiệp vụ

`sealed` kiểm soát **loại đối tượng** được chấp nhận ở cấp type hierarchy. Nó **không bảo đảm dữ liệu bên trong một subtype hợp lệ**. Ví dụ, `Paid` là subtype hợp lệ vẫn có thể mang `orderId` rỗng hoặc số tiền âm nếu không được kiểm tra.

Dùng validation tại nơi khởi tạo dữ liệu, như compact constructor của record:

```java
record Approved(String paymentId, long cents) {
    Approved {
        if (paymentId == null || paymentId.isBlank()
                || cents <= 0) {
            throw new IllegalArgumentException(
                    "invalid approved payment");
        }
    }
}
```

Đây là **khai báo record minh họa**. Trong domain thực tế, có thể dùng `Objects.requireNonNull`, value object riêng (`PaymentId`, `Money`) và các rule rõ ràng.

Ví dụ độc lập `CheckedResultDemo.java`:

```java
public class CheckedResultDemo {
    sealed interface PaymentResult
            permits Approved, Rejected {}

    record Approved(String paymentId, long cents)
            implements PaymentResult {
        Approved {
            if (paymentId == null || paymentId.isBlank()
                    || cents <= 0) {
                throw new IllegalArgumentException(
                        "invalid approved payment");
            }
        }
    }

    record Rejected(String paymentId, String reason)
            implements PaymentResult {}

    static String display(PaymentResult result) {
        return switch (result) {
            case Approved(var id, var cents) ->
                    "ok:" + id + ":" + cents;
            case Rejected(var id, var reason) ->
                    "rejected:" + id + ":" + reason;
        };
    }

    public static void main(String[] args) {
        System.out.println(display(new Approved("P-1", 350)));

        try {
            new Approved("", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

```bash
javac --release 21 CheckedResultDemo.java
java CheckedResultDemo
```

Kết quả:

```text
ok:P-1:350
invalid approved payment
```

Ở đây:

- `sealed` bảo vệ tập kết quả là `Approved`/`Rejected`.
- `record` cung cấp data carrier bất biến ở mức component tham chiếu và accessor.
- Compact constructor bảo đảm giá trị cho `Approved` hợp lệ.
- `switch` exhaustive bảo đảm nhánh hiển thị phân biệt từng kết quả.

Tuy nhiên, **trạng thái tiến trình** như “đã hoàn tiền chỉ sau khi thanh toán” còn cần quy tắc chuyển trạng thái hoặc nghiệp vụ riêng; riêng `sealed` không kiểm tra được lịch sử sự kiện.

## 10. Khi mở rộng public API: source compatibility và runtime

Việc thêm một permitted subtype có hai tác động khác nhau cần phân biệt:

**Khi biên dịch lại source consumer:** một `switch` exhaustive trước đây có thể báo **lỗi biên dịch** vì thiếu case cho subtype mới. Điều này hữu ích để buộc cập nhật logic. Mã có `default` có thể tiếp tục biên dịch nhưng cũng dễ bỏ sót nghiệp vụ mới.

**Với binary consumer đã biên dịch từ phiên bản cũ:** theo JLS, việc **thêm permitted direct subtype** nhìn chung là **binary compatible**, nghĩa là không nhất thiết gây lỗi liên kết chỉ vì danh sách subtype mở rộng. Tuy vậy, nếu binary cũ chứa một `switch` từng exhaustive và sau nâng cấp nhận đối tượng thuộc subtype mới mà nó không biết, thực thi có thể ném **`MatchException`**. Đó là rủi ro tương thích khi triển khai/migration, dù class file cũ vẫn liên kết được.

Ví dụ tình huống vận hành:

1. Thư viện domain **v1** khai báo `OrderEvent permits Placed, Paid, Cancelled`; một dịch vụ client biên dịch `switch` đủ ba loại.
2. Thư viện **v2** thêm `Refunded`.
3. Nếu client được **biên dịch lại**, compiler yêu cầu cập nhật `switch` exhaustive.
4. Nếu chỉ cập nhật thư viện ở runtime mà vẫn chạy **client cũ**, client có thể xử lý ba loại cũ bình thường, nhưng khi nhận `Refunded`, `switch` cũ có thể thất bại bằng `MatchException`.

Vì vậy, kiểm soát hierarchy còn bao gồm **versioning, cập nhật consumer, test tích hợp và kế hoạch deploy**. Đừng đồng nhất “binary compatible” với “mọi hành vi runtime vẫn tương thích”.

## 11. Phân biệt mở rộng bên trong domain với dữ liệu ngoài hệ thống

Một domain hierarchy có thể đóng, nhưng dữ liệu đầu vào từ JSON/API/message queue thường không đóng: có thể có `eventType` lạ, payload sai schema hoặc phiên bản mới chưa được hỗ trợ. `sealed` không tự ánh xạ hoặc xác thực JSON.

Nên tách các lớp trách nhiệm:

1. **Adapter/decoder** đọc dữ liệu bên ngoài, kiểm tra schema, version và quyền truy cập.
2. **Validation/domain factory** tạo một subtype hợp lệ hoặc trả lỗi đầu vào rõ ràng.
3. **Domain model sealed** giữ tập biến thể đã được hệ thống chấp nhận.
4. **Pattern `switch` ở application logic** xử lý toàn bộ subtype domain đã cho phép.

Nếu một hệ thống phải giữ lại sự kiện tương lai chưa hiểu, có thể cân nhắc mô hình riêng như `UnknownEvent(type, rawPayload)`, nhưng điều đó là **quyết định nghiệp vụ và chính sách tương thích dữ liệu**, không phải giải pháp mặc định cho mọi thiếu case. Cần đặt giới hạn kích thước, định dạng và cách sử dụng dữ liệu lạ nếu mô hình có payload bên ngoài.

Một `default` ở `switch` hoặc một subtype `UnknownEvent` không tự khiến hệ thống hiểu được giao dịch tương lai; chúng chỉ tạo chỗ rõ ràng để xử lý hoặc từ chối.

## 12. Chọn `enum`, `sealed interface` hay interface mở?

| Đặc điểm | `enum` | `sealed interface` + records | Interface mở |
| --- | --- | --- | --- |
| Tập biến thể | Hữu hạn theo các hằng | Các subtype trực tiếp được kiểm soát | Có thể được mở rộng bởi bên ngoài |
| Dữ liệu khác nhau theo biến thể | Có thể, nhưng dễ cồng kềnh khi payload khác cấu trúc | Mỗi record mang component riêng rõ nghĩa | Tùy implementation |
| `switch` exhaustive | Compiler có thể dựa trên các hằng enum | Compiler có thể dựa trên sealed hierarchy | Thường cần nhánh tổng quát |
| Chỗ mở rộng | Thêm enum constant | Thêm subtype `permits` hoặc nhánh `non-sealed` | Implement thêm type |
| Phù hợp | Trạng thái/giá trị đơn giản, ít payload | Algebraic data type, sự kiện/kết quả có payload khác nhau | SPI, plugin, polymorphism mở |

Ví dụ đơn hàng chỉ có `NEW`, `PAID`, `CANCELLED` và không mang dữ liệu khác nhau thì `enum` có thể đủ. Khi mỗi biến thể mang payload riêng (`Paid.amountCents`, `Cancelled.reason`), `sealed interface` kết hợp `record` thường giúp model biểu đạt điều gì hợp lệ rõ hơn.

Đừng chọn sealed hierarchy chỉ vì cú pháp pattern matching đẹp. Hãy chọn khi **tập biến thể có chủ sở hữu và cần kiểm soát**, nhất là khi nhiều consumer phải được cập nhật mỗi khi có subtype mới.

## 13. Quy trình thêm subtype trong dự án thực tế

Một thay đổi có kiểm soát thường theo thứ tự:

1. **Xác định biến thể mới có thật sự là subtype của domain hiện tại hay không.** Ví dụ `Refunded` là `OrderEvent` hay là một kết quả nằm ở bounded context `Payment`?
2. **Xác định ai sở hữu sealed root và package/module.** Type mới phải đáp ứng quy tắc `permits` và biên giới module.
3. **Định nghĩa subtype và invariant.** Nếu dùng record, cân nhắc component, nullability, value object, validation.
4. **Cập nhật `permits` của sealed root** hoặc mở rộng nhánh đã thiết kế cho việc đó; tránh mở cả hierarchy bằng `non-sealed` nếu chỉ cần một biến thể cụ thể.
5. **Biên dịch lại các consumer.** Xử lý các lỗi `switch` exhaustive; review cả những consumer dùng `default`, vì chúng có thể tiếp tục biên dịch nhưng sai kỳ vọng nghiệp vụ.
6. **Kiểm tra tích hợp và serialization.** API, mapping JSON, persistence, message schema, telemetry và dữ liệu cũ/mới phải tuân thủ contract.
7. **Lập kế hoạch triển khai đồng bộ khi cần.** Đặc biệt với nhiều service đang chia sẻ domain JAR hoặc event schema.
8. **Cập nhật tài liệu domain và ví dụ.** Mô tả mục đích, dữ liệu, luồng xử lý và cách mở rộng tiếp.

Những bước trên không thay thế code review; chúng giúp review tập trung đúng nơi mà compiler hoặc domain model không thể tự quyết định.

## 14. Ví dụ kiểm tra tiêu cực: subtype không được cho phép

Cho đoạn:

```java
sealed interface Action permits Start, Stop {}

record Start() implements Action {}
record Stop() implements Action {}
```

Nếu thêm:

```java
// Đoạn này không hợp lệ khi chưa sửa permits:
record Pause() implements Action {}
```

`Pause` đang cố trực tiếp implements `Action` nhưng chưa được liệt kê. Compiler sẽ từ chối. Chỉ khi chủ sở hữu `Action` thêm `Pause` vào `permits` và các điều kiện liên quan được đáp ứng thì đây mới là subtype trực tiếp hợp lệ.

Tương tự, nếu sửa `permits` để thêm `Pause` nhưng `switch` hiện tại chỉ xét `Start` và `Stop`, expression switch exhaustive không còn hoàn chỉnh và sẽ bị compiler phát hiện khi biên dịch lại.

Đây là **hai lớp kiểm soát khác nhau**: (1) ai được phép trở thành biến thể của root; (2) những consumer nào cần cập nhật khi danh mục biến thể thay đổi.

## 15. Những hiểu nhầm thường gặp

1. **“`sealed` cấm mọi thay đổi trong tương lai.”** Không đúng. Chủ sở hữu có thể sửa danh sách `permits`, nhưng thay đổi đó kéo theo nghĩa vụ nâng cấp consumer.
2. **“Mọi class implement một sealed interface ở bất kỳ module nào cũng được nếu liệt kê `permits`.”** Không đúng. Type phải tuân thủ hạn chế same named module hoặc same package trong unnamed module.
3. **“`permits` chứa tất cả subtype ở mọi tầng.”** Không đúng. Nó chỉ quản lý subtype **trực tiếp**; mỗi nhánh `sealed` quản lý tầng con của chính nó.
4. **“Record cần ghi `final` để hợp lệ với sealed interface.”** Không cần. Record ngầm là `final`.
5. **“`non-sealed` vẫn giữ danh sách subtype con cố định.”** Không đúng. Nó mở lại quyền mở rộng dưới nhánh đó.
6. **“Có `default` là thiết kế luôn an toàn.”** Không chắc. `default` có thể che thiếu logic cho biến thể nghiệp vụ mới.
7. **“Đã exhaustive thì `switch` tự xử lý `null`.”** Không đúng. Hãy định nghĩa chính sách `null` rõ ràng.
8. **“Thêm subtype là binary incompatible trong mọi trường hợp.”** Không đúng theo quy tắc tương thích nhị phân của Java; rủi ro nằm cả ở **mã consumer chưa nâng cấp** và `MatchException` khi gặp subtype mới.
9. **“Sealed đảm bảo mọi record instance đều hợp lệ.”** Không đúng. Nullability, số tiền dương, độ dài chuỗi và trạng thái nghiệp vụ cần validation riêng.
10. **“Mọi hierarchy đều nên `sealed`.”** Không đúng. Extension point thực sự mở có thể dùng interface thông thường hoặc một nhánh `non-sealed` được thiết kế có chủ đích.

## 16. Checklist thiết kế

Khi tạo hoặc thay đổi domain type hierarchy, hãy tự trả lời:

- Tập biến thể là **đóng** hay **mở** theo nhu cầu sản phẩm?
- Ai sở hữu root type và ai có quyền thêm subtype?
- Những nhánh nào nên là `final`/record, `sealed` tiếp, hoặc `non-sealed`?
- `permits` đã đúng **subtype trực tiếp** và đúng biên giới module/package chưa?
- Các `switch` đang dựa vào exhaustiveness có cần `case` mới không? Có `default` nào đang che thiếu xử lý không?
- Có bảo vệ **invariant của dữ liệu** bằng constructor/factory/validation không?
- `null`, dữ liệu lạ và phiên bản schema mới được xử lý ở đâu?
- Khi nâng cấp thư viện/domain JAR, các consumer có được biên dịch và deploy đồng bộ không?

**Ghi nhớ:** sử dụng `sealed` để kiểm soát **những loại giá trị domain có thể tồn tại**; sử dụng pattern matching với `switch` để kiểm soát **những nhánh xử lý cần có**; sử dụng constructor, validation và quy trình triển khai để giữ **giá trị và hành vi nghiệp vụ** đúng khi mở rộng type hierarchy.

## Tài liệu tham khảo chính thức

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Java SE 21 JLS §8.1.1.2 — sealed và final Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2)
- [Java SE 21 JLS §9.1.1.4 — sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.1.1.4)
- [Java SE 21 JLS §14.11 — switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 JLS §13.4 và §13.5 — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html)
