# Đặt tên nhánh enum có ý nghĩa trong Java 21

Khi dùng `enum` cùng `switch`, **tên enum constant chính là từ vựng nghiệp vụ của các nhánh `case`**. Một nhánh tên `PAYMENT_PENDING` nói rõ đơn hàng đang **chờ thanh toán**; một nhánh `PAID` nói rõ thanh toán đã hoàn tất. Trái lại, `STATE_1`, `OK` hoặc `OTHER` buộc người đọc phải truy ngược tài liệu để biết mỗi giá trị đại diện cho điều gì.

Trong Java, ta không đặt một tên tùy ý cho `case` theo kiểu `case "đã thanh toán"` khi selector là enum. **`case` tham chiếu tới enum constant đã khai báo.** Do đó, muốn code xử lý rõ nghĩa, trước hết phải thiết kế **tên constant** tốt; sau đó tổ chức các nhánh và đặt tên cho method/kết quả xử lý tương ứng.

Bài này tập trung vào việc chọn tên, nhóm nhánh, diễn đạt vòng đời trạng thái, giữ tính exhaustive của `switch`, và tránh để tên hiển thị hoặc mã tích hợp ngoài hệ thống chi phối tên enum. Ví dụ dùng cú pháp Java 21, nhưng các nguyên tắc đặt tên có thể áp dụng từ những phiên bản Java cũ.

## 1. Tên enum phải mô tả *trạng thái*, không phải một số thứ tự

Giả sử ứng dụng quản lý đơn hàng có ba thời điểm: chờ thanh toán, đã thanh toán và đã giao. Thiết kế khó đọc:

```java
enum OrderStatus {
    S1, S2, S3
}
```

Người đọc đoạn sau không thể hiểu nhanh ý nghĩa:

```java
switch (status) {
    case S1 -> requestPayment();
    case S2 -> prepareShipment();
    case S3 -> closeOrder();
}
```

Hai đoạn chỉ minh họa cú pháp trong một chương trình có các method tương ứng; đây không phải file độc lập có thể chạy.

Thiết kế rõ nghĩa hơn:

```java
enum OrderStatus {
    PAYMENT_PENDING,
    PAID,
    DELIVERED
}
```

```java
switch (status) {
    case PAYMENT_PENDING -> requestPayment();
    case PAID -> prepareShipment();
    case DELIVERED -> closeOrder();
}
```

Giờ chính nhãn `case` giải thích **vì sao** một hành động được chọn. Nếu có yêu cầu sửa logic của đơn hàng “đã thanh toán nhưng chưa giao”, `case PAID` là nơi người bảo trì tìm tới ngay.

Một tên tốt cần trả lời: “Giá trị này biểu diễn **tình trạng hoặc biến thể nào của thực thể**?”. Một tên kém thường chỉ trả lời “Đây là nhánh số mấy?” hoặc “Đây là kết quả mà tôi muốn in ra lúc này?”.

## 2. Quy ước đặt tên enum constant trong Java

Thông thường, tên enum constant được viết bằng **UPPER_SNAKE_CASE**, gồm chữ cái in hoa và dấu gạch dưới giữa các từ:

```java
enum PaymentStatus {
    NOT_REQUESTED,
    PAYMENT_PENDING,
    PAID,
    FAILED,
    REFUNDED
}
```

Cách viết này nhất quán với quy ước constant của Java và dễ nhận diện trong `case`:

```java
case PAYMENT_PENDING -> "await payment";
case PAID -> "continue fulfillment";
```

Hãy lưu ý:

- **Ưu tiên thuật ngữ nghiệp vụ chính xác:** `AWAITING_APPROVAL` khác `APPROVED`; `CANCELED` khác `FAILED`.
- **Giữ cùng cấp độ khái niệm:** trong `OrderStatus`, các constant nên là *trạng thái đơn hàng*, không trộn `CREATE_ORDER` (một lệnh) với `PAID` (một trạng thái).
- **Không viết tắt khó đoán:** `PAYMENT_PENDING` thường rõ hơn `PYMT_PND`; viết tắt phổ biến như `HTTP` có thể phù hợp khi nhóm đã thống nhất.
- **Tránh tiền tố lặp không cần thiết:** `OrderStatus.PAID` thường gọn hơn `OrderStatus.ORDER_PAID`, vì tên kiểu đã cung cấp ngữ cảnh.
- **Tránh nhãn mơ hồ:** `DONE`, `ACTIVE`, `ERROR` chỉ nên dùng khi mô hình đã định nghĩa rõ chúng; nếu không, chọn `DELIVERED`, `PAYMENT_FAILED` hoặc `EXPIRED` cụ thể hơn.
- **Thống nhất cách chia động từ:** ví dụ dùng `CANCELED`, `DELIVERED` cho trạng thái đã xảy ra, và `PAYMENT_PENDING` cho trạng thái đang chờ, thay vì chuyển qua lại giữa tên lệnh và tên kết quả.

Quy ước viết hoa giúp thống nhất mã nguồn, nhưng **không thay thế việc đặt tên đúng nghĩa**: `STATE_ONE` có đúng hình thức mà vẫn không cho người đọc biết trạng thái thực tế.

## 3. Tên enum constant khác với tên hành động của nhánh

Xét vòng đời:

```text
DRAFT -> PAYMENT_PENDING -> PAID -> PACKING -> SHIPPED -> DELIVERED
                                \-> CANCELED
                                \-> REFUNDED (theo quy tắc nghiệp vụ riêng)
```

Sơ đồ trên mô tả ví dụ đơn giản; **không phải** mọi hệ thống đều cho phép chuyển thẳng từ `PAID` sang `REFUNDED` hoặc từ trạng thái nào cũng sang `CANCELED`. Quy tắc chuyển trạng thái cần được thiết kế độc lập.

Trong `enum OrderStatus`, các tên `DRAFT`, `PAYMENT_PENDING`, `PAID`, `PACKING`, `SHIPPED`, `DELIVERED`, `CANCELED`, `REFUNDED` diễn đạt **trạng thái hiện tại**.

Trong `switch`, phần thân nhánh mới diễn đạt **hành động tiếp theo**:

```java
static String nextAction(OrderStatus status) {
    return switch (status) {
        case DRAFT -> "submit-order";
        case PAYMENT_PENDING -> "request-payment";
        case PAID -> "start-packing";
        case PACKING -> "ship-package";
        case SHIPPED -> "track-delivery";
        case DELIVERED -> "archive-order";
        case CANCELED, REFUNDED -> "stop-fulfillment";
        case null -> "manual-review";
    };
}
```

Đây là method minh họa với `OrderStatus` được định nghĩa trước. Một tên `case PAID` không có nghĩa “hãy đánh dấu đơn hàng là đã thanh toán”; nó có nghĩa “khi trạng thái **đang là PAID**, thực thi hành động dành cho trạng thái đó”. Tránh nhầm lẫn giữa **điều kiện chọn nhánh** và **lệnh mà nhánh thực hiện**.

Nếu domain cần rõ hơn, hãy trả về một `enum NextAction` riêng thay vì chuỗi, ví dụ `START_PACKING`, `SHIP_PACKAGE`, `MANUAL_REVIEW`. Hai enum lúc đó có hai nhiệm vụ khác nhau: một enum biểu diễn trạng thái, enum kia biểu diễn hành động.

## 4. Khi nào nên gộp nhiều enum constant trong một case?

Java hỗ trợ nhiều hằng enum dùng chung một rule:

```java
return switch (status) {
    case DRAFT, PAYMENT_PENDING -> "pre-payment";
    case PAID, PACKING, SHIPPED -> "fulfillment";
    case DELIVERED -> "delivered";
    case CANCELED, REFUNDED -> "closed";
    case null -> "unknown";
};
```

Đây là method body minh họa cho `OrderStatus status`. Dấu phẩy biểu thị **nhiều enum constant chọn cùng một kết quả**. Chỉ gộp khi các trạng thái thật sự có **cùng hành vi trong ngữ cảnh cụ thể**.

Ví dụ `CANCELED` và `REFUNDED` có thể cùng trả `"closed"` cho **mục đích hiển thị nhóm trạng thái**; chúng **không vì thế mà đồng nghĩa**. Hoàn tiền có thể cần báo cáo kế toán, còn hủy đơn có thể phát sinh trước khi thu tiền. Nếu đang xử lý thanh toán, hai nhánh này nên được tách riêng.

**Nguyên tắc:** gộp ở nơi hành vi giống nhau, nhưng **không nhập hai giá trị enum** chỉ vì một màn hình hiện tại xử lý chúng giống nhau.

Ví dụ tốt:

```java
case DRAFT, PAYMENT_PENDING -> "needs-customer-action";
```

Ví dụ đáng nghi nếu không có yêu cầu nghiệp vụ chứng minh:

```java
case PAID, REFUNDED -> "payment-complete";
```

`PAID` và `REFUNDED` có thể dẫn đến hậu quả tài chính khác nhau. Nếu nhãn kết quả khiến người đọc hiểu nhầm, cần đặt lại tên nhóm, tách rule hoặc định nghĩa một kiểu kết quả rõ nghĩa hơn.

## 5. Cùng hành vi hôm nay không có nghĩa cùng ý nghĩa mãi mãi

Giả sử hệ thống đang hiển thị một nút “Không thao tác” cho `CANCELED` và `REFUNDED`. Viết:

```java
case CANCELED, REFUNDED -> "no-fulfillment";
```

là hợp lý **nếu cả hai đều không được tiếp tục giao hàng**. Nhưng khi chuyển sang tác vụ gửi thông báo:

```java
case CANCELED -> "send-cancellation-notice";
case REFUNDED -> "send-refund-confirmation";
```

nên dùng các nhánh riêng vì hành động khác nhau.

Đừng tạo một enum constant `STOPPED` để thay cả `CANCELED` lẫn `REFUNDED` nếu doanh nghiệp vẫn phải biết sự khác biệt. Cách nhóm **ở kết quả xử lý** giữ thông tin nguồn; cách nhập các trạng thái thành một constant có thể làm mất thông tin.

Ngược lại, cũng không nên tách các case thành nhiều đoạn mã copy-paste dài nếu chúng chỉ gọi cùng một nghiệp vụ. Khi đó, gộp case hoặc gọi chung helper method sẽ giúp giảm lỗi sửa một nhánh nhưng quên nhánh còn lại.

## 6. `switch expression` không có default giúp tên enum phát huy giá trị

Nếu tất cả enum constant đều được liệt kê, `switch expression` trong Java 21 có thể exhaustive **mà không cần `default`**:

```java
static String display(OrderStatus status) {
    return switch (status) {
        case DRAFT -> "Draft";
        case PAYMENT_PENDING -> "Awaiting payment";
        case PAID -> "Paid";
        case PACKING -> "Packing";
        case SHIPPED -> "Shipped";
        case DELIVERED -> "Delivered";
        case CANCELED -> "Canceled";
        case REFUNDED -> "Refunded";
    };
}
```

Nếu thêm một enum constant mới, chẳng hạn `RETURNED`, rồi **biên dịch lại mã nguồn**, compiler có thể yêu cầu cập nhật `switch expression` vì nó chưa exhaustive. Điều này có giá trị khi mỗi trạng thái mới phải được xem xét về cách xử lý.

Với **traditional switch statement** chỉ chứa nhãn hằng và không có `case null`/pattern, Java có thể cho phép không có `default` và chưa đủ mọi enum constant. Vì vậy, đừng suy rằng **mọi switch statement** đều buộc exhaustive như switch expression. Nếu muốn kiểm tra đầy đủ trạng thái, sử dụng switch expression hoặc quy tắc kiểm tra code phù hợp.

Cần phân biệt thêm trường hợp runtime: nếu class chứa switch cũ được biên dịch với enum v1 nhưng runtime nhận một constant chỉ có trong enum v2, một switch vốn được compiler coi exhaustive có thể gặp `MatchException` (Java 21). Rebuild các module phụ thuộc là bước cần thiết khi thay đổi enum đã được dùng rộng rãi.

## 7. `default` có thể che giấu enum mới

Cách viết này rất phổ biến:

```java
return switch (status) {
    case PAID -> "paid";
    case SHIPPED -> "shipped";
    default -> "other";
};
```

Nó hợp lệ, nhưng có hai rủi ro với một domain enum đóng:

1. Những trạng thái hiện tại khác `PAID` và `SHIPPED` đều rơi vào `"other"`, có thể làm mất ý nghĩa nghiệp vụ.
2. Khi thêm `REFUNDED` hoặc `RETURNED`, compiler không nhất thiết nhắc cập nhật rule vì đã có `default`.

Nếu mục đích là **buộc người bảo trì xét từng trạng thái**, hãy liệt kê enum constant hoặc nhóm các hằng có cùng hành vi, **không dùng `default` chỉ để tiết kiệm vài dòng**.

`default` vẫn hữu ích khi yêu cầu thật sự là “các trạng thái khác nhau đều được xử lý chung” và ứng dụng phải tương thích với giá trị enum tương lai. Khi đó, cần diễn đạt rõ hợp đồng: `"other"` là một nhóm nghiệp vụ được chấp nhận, hay chỉ là một cách giấu lỗi?

Đặc biệt, **`default` không mặc nhiên xử lý selector `null`** trong pattern switch Java 21. Nếu dữ liệu có thể `null`, xử lý tường minh hoặc kiểm tra trước khi switch.

## 8. Đặt tên đúng giúp đọc nhánh khi review và debug

So sánh hai đoạn:

```java
switch (order.status()) {
    case S1 -> sendEmail();
    case S2 -> chargeCard();
    case S3 -> preparePackage();
    default -> {}
}
```

và:

```java
switch (order.status()) {
    case DRAFT -> sendDraftReminder();
    case PAYMENT_PENDING -> requestPayment();
    case PAID -> startPacking();
    case PACKING, SHIPPED, DELIVERED, CANCELED, REFUNDED -> {
        // Không gửi yêu cầu thanh toán tại các trạng thái này.
    }
}
```

Cả hai là đoạn **minh họa trong method** có đối tượng và helper phù hợp. Đoạn hai làm rõ **mối quan hệ giữa trạng thái và hành vi** ngay trên các nhánh; từ đó code review có thể đặt câu hỏi đúng: “Ở `DRAFT`, gửi nhắc bản nháp có phù hợp không?” và “`PAYMENT_PENDING` đã được bảo vệ khỏi thu tiền hai lần chưa?”.

Một tên nhánh tự giải thích không thay cho validation và kiểm thử, nhưng làm những điểm cần kiểm thử dễ nhận ra hơn.

Khi có quá nhiều case, có thể trích phần xử lý ra method theo nghiệp vụ:

```java
case PAYMENT_PENDING -> handlePendingPayment(order);
case PAID -> handlePaidOrder(order);
```

Cách này vừa giữ `switch` dễ quét mắt, vừa đặt tên method rõ nhiệm vụ. Đừng đặt tên chung chung như `doStuff()` hoặc `process2()` rồi buộc người đọc mở sâu nhiều tầng để hiểu tác động của từng nhánh.

## 9. Đặt tên đồng bộ giữa enum, log và sự kiện

Trong hệ thống nhiều tầng, tên enum xuất hiện ở nhiều nơi:

- Code Java: `OrderStatus.PAYMENT_PENDING`.
- Log: có thể ghi `status=PAYMENT_PENDING`.
- Payload API: có thể dùng chuỗi như `"payment_pending"`.
- Database: có thể lưu một mã ổn định.
- UI: có thể hiển thị **“Chờ thanh toán”** cho người dùng Việt Nam.

Các cách biểu diễn này **không nhất thiết có cùng văn bản**. Chẳng hạn `PAYMENT_PENDING` là tên code hữu ích, còn UI dùng “Chờ thanh toán” để người dùng hiểu. Không nên đặt enum constant thành một câu tiếng Việt có dấu chỉ vì UI hiển thị tiếng Việt; dùng mapping/lớp trình bày phù hợp.

Khi cần mã giao tiếp ngoài hệ thống ổn định, có thể khai báo riêng:

```java
enum PaymentStatus {
    PAYMENT_PENDING("payment_pending"),
    PAID("paid"),
    REFUNDED("refunded");

    private final String externalCode;

    PaymentStatus(String externalCode) {
        this.externalCode = externalCode;
    }

    String externalCode() {
        return externalCode;
    }
}
```

Đây là **một enum minh họa riêng**, không cùng `OrderStatus` của chương trình đầy đủ phía sau. Nó cho phép thay đổi nhãn hiển thị mà không tự động thay đổi mã trao đổi, với điều kiện các bên thống nhất hợp đồng.

**Cảnh báo khi đổi tên:** `Enum.name()` trả đúng tên constant trong source. Nếu serialization, API hoặc database đang dựa vào `name()`, đổi tên constant có thể làm dữ liệu cũ không còn parse được bằng `Enum.valueOf(...)`. Ngược lại, `ordinal()` dựa theo **thứ tự khai báo** nên rất dễ thay đổi khi chèn/sắp xếp constant; không nên dùng `ordinal()` làm mã lưu trữ lâu dài.

## 10. `case` enum là tên hằng, không phải nhãn chuỗi tùy ý

Một enum selector dùng nhãn hằng của **chính enum đó**, thường viết không kèm tên type:

```java
OrderStatus status = OrderStatus.PAID;

String result = switch (status) {
    case PAID -> "paid";
    case DRAFT, PAYMENT_PENDING, PACKING, SHIPPED,
         DELIVERED, CANCELED, REFUNDED -> "not paid";
};
```

Trong Java 21, đoạn trên hợp lệ khi các constant đã khai báo như các phần trước. Đây là `switch expression`; mỗi `case` chọn theo **constant**, không khai báo pattern variable.

**Không hợp lệ với selector `OrderStatus`:**

```java
// KHÔNG BIÊN DỊCH:
String result = switch (status) {
    case "PAID" -> "paid"; // String, không phải hằng OrderStatus.
    default -> "other";
};
```

Nếu nguồn đầu vào là chuỗi `"PAID"`, hãy **parse/validate** chuỗi ở ranh giới hệ thống trước, rồi xử lý theo `OrderStatus`. `OrderStatus.valueOf(raw)` phân biệt chữ hoa và có thể ném `IllegalArgumentException` khi không có constant tương ứng; nếu `raw` bằng `null`, lời gọi cũng không an toàn. Đừng rải việc parse chuỗi vào nhiều nhánh nghiệp vụ.

Một lỗi khác là cố dùng cú pháp `when` sau nhãn hằng:

```java
// KHÔNG BIÊN DỊCH ở Java 21:
// case PAID when customer.isVerified() -> "ready";
```

`when` gắn với **case pattern**, không phải một danh sách enum constant. Nếu cùng trạng thái `PAID` cần hai hành vi theo một điều kiện phụ, xử lý điều kiện **bên trong rule**:

```java
case PAID -> customer.isVerified() ? "start-packing" : "verify-customer";
```

Dòng trên là cú pháp minh họa **trong switch expression** có `customer` phù hợp, không phải chương trình độc lập.

## 11. Tên enum rõ nghĩa giúp tránh trộn trạng thái với kết quả lỗi

Một enum trạng thái dễ bị “phình” nếu mọi lỗi kỹ thuật đều trở thành một constant mới:

```java
enum OrderStatus {
    DRAFT,
    PAYMENT_PENDING,
    PAID,
    PACKING,
    SHIPPED,
    DELIVERED,
    CANCELED,
    REFUNDED,
    NETWORK_ERROR,
    TIMEOUT
}
```

`NETWORK_ERROR` và `TIMEOUT` đôi khi là **kết quả tạm thời của việc gọi service**, chứ không phải trạng thái bền vững của đơn hàng. Nếu chúng không thuộc cùng domain lifecycle, tốt hơn là mô hình riêng:

```java
enum OrderStatus {
    DRAFT, PAYMENT_PENDING, PAID, PACKING,
    SHIPPED, DELIVERED, CANCELED, REFUNDED
}

enum RemoteCallResult {
    SUCCESS, NETWORK_ERROR, TIMEOUT
}
```

Tách như vậy giúp các nhánh `switch(order.status())` chỉ nói về vòng đời đơn hàng, không trộn với lỗi vận chuyển hoặc hạ tầng. Tuy nhiên, nếu nghiệp vụ thực sự lưu một trạng thái “giao hàng thất bại” như một phần vòng đời, hãy dùng tên cụ thể `DELIVERY_FAILED` trong enum trạng thái phù hợp.

Nguyên tắc là đặt tên theo **ranh giới domain**, không tùy tiện đưa mọi tín hiệu kỹ thuật vào cùng enum chỉ vì đều có thể xảy ra trong một workflow.

## 12. Ví dụ hoàn chỉnh chạy được trên JDK 21

Tạo file **`MeaningfulEnumBranchesDemo.java`**:

```java
public class MeaningfulEnumBranchesDemo {
    enum OrderStatus {
        DRAFT,
        PAYMENT_PENDING,
        PAID,
        PACKING,
        SHIPPED,
        DELIVERED,
        CANCELED,
        REFUNDED
    }

    static String nextAction(OrderStatus status) {
        return switch (status) {
            case null -> "manual-review";
            case DRAFT -> "submit-order";
            case PAYMENT_PENDING -> "request-payment";
            case PAID -> "start-packing";
            case PACKING -> "ship-package";
            case SHIPPED -> "track-delivery";
            case DELIVERED -> "archive-order";
            case CANCELED, REFUNDED -> "stop-fulfillment";
        };
    }

    static String phase(OrderStatus status) {
        return switch (status) {
            case null -> "unknown";
            case DRAFT, PAYMENT_PENDING -> "pre-payment";
            case PAID, PACKING, SHIPPED -> "fulfillment";
            case DELIVERED -> "delivered";
            case CANCELED, REFUNDED -> "closed";
        };
    }

    static boolean canStartPacking(OrderStatus status) {
        return status == OrderStatus.PAID;
    }

    public static void main(String[] args) {
        for (OrderStatus status : OrderStatus.values()) {
            System.out.println(
                    status + " -> " + nextAction(status)
                            + " | " + phase(status));
        }

        System.out.println("null -> " + nextAction(null));
        System.out.println("canStartPacking(PAID)="
                + canStartPacking(OrderStatus.PAID));
        System.out.println("canStartPacking(CANCELED)="
                + canStartPacking(OrderStatus.CANCELED));
    }
}
```

Biên dịch và chạy bằng **JDK 21**:

```bash
javac --release 21 MeaningfulEnumBranchesDemo.java
java MeaningfulEnumBranchesDemo
```

**Stdout dự kiến, theo thứ tự khai báo enum:**

```text
DRAFT -> submit-order | pre-payment
PAYMENT_PENDING -> request-payment | pre-payment
PAID -> start-packing | fulfillment
PACKING -> ship-package | fulfillment
SHIPPED -> track-delivery | fulfillment
DELIVERED -> archive-order | delivered
CANCELED -> stop-fulfillment | closed
REFUNDED -> stop-fulfillment | closed
null -> manual-review
canStartPacking(PAID)=true
canStartPacking(CANCELED)=false
```

Giải thích các điểm quan trọng:

1. **Tên constant mang ý nghĩa:** `PAYMENT_PENDING` không bị nhầm với `PAID`; `SHIPPED` không đồng nghĩa `DELIVERED`.
2. **Cùng enum, hai cách phân loại:** `nextAction` ánh xạ từng trạng thái sang hành động, còn `phase` nhóm trạng thái thành giai đoạn. Hai cách gom khác nhau vì **mục tiêu xử lý khác nhau**.
3. **Gộp case có chủ đích:** `CANCELED` và `REFUNDED` cùng trả `stop-fulfillment` trong `nextAction`, nhưng vẫn là hai trạng thái độc lập. Nếu nghiệp vụ hoàn tiền cần tác vụ riêng, phải tách case.
4. **Không cần default:** cả hai switch expression liệt kê đủ tám trạng thái, đồng thời có `case null`. Compiler có thể buộc cập nhật code nếu enum được mở rộng và source được biên dịch lại.
5. **Tránh ép mọi điều kiện qua switch:** `canStartPacking` đơn giản là phép so sánh `status == OrderStatus.PAID`. So sánh enum với `==` là đúng về định danh constant; khi `status == null`, phép so sánh trả `false` mà không ném `NullPointerException`.
6. **Thứ tự `values()`** phản ánh thứ tự khai báo constant, nên chương trình in theo thứ tự đã viết trong enum; không suy từ đó rằng `ordinal()` là một mã nghiệp vụ ổn định.

Không cần `--enable-preview` cho các case constant và `case null` của Java 21.

## 13. Bài tập thiết kế tên nhánh

**Bài tập 1 — Thay nhãn mơ hồ.** Một enum `TicketStatus` có `S1, S2, S3, S4`; tài liệu mô tả lần lượt là mới tạo, đang xử lý, đã giải quyết, đã đóng. Hãy đặt lại tên:

```java
enum TicketStatus {
    NEW,
    IN_PROGRESS,
    RESOLVED,
    CLOSED
}
```

Không dùng `DONE` thay cả `RESOLVED` và `CLOSED` nếu hệ thống phân biệt “đã có giải pháp” với “đã hoàn tất quy trình đóng ticket”.

**Bài tập 2 — Chỉ gộp theo mục tiêu.** Với `TicketStatus`, một màn hình có thể hiển thị `RESOLVED` và `CLOSED` cùng nhãn nhóm `"finished"`. Nhưng một chức năng gửi khảo sát sau giải quyết có thể chỉ chạy ở `RESOLVED`. Hãy viết **hai switch** theo hai yêu cầu thay vì gộp enum constant.

**Bài tập 3 — Thêm trạng thái mới.** Thêm `REOPENED` vào `TicketStatus`, rồi biên dịch lại switch expression đã liệt kê đủ bốn trạng thái cũ mà không có `default`. Hãy quan sát compiler yêu cầu xử lý giá trị mới. Nếu một `default` che lấp yêu cầu cập nhật, cân nhắc bỏ default để được cảnh báo compile-time.

**Bài tập 4 — Mã bên ngoài.** Nếu API đã phát giá trị `"in_progress"`, việc đổi tên Java constant `IN_PROGRESS` sang `PROCESSING` có thể ảnh hưởng đến consumer nào? Hãy xác định điểm parse và serialize, đồng thời tách external code khỏi `Enum.name()` khi hợp đồng yêu cầu ổn định.

Các bài tập hướng vào một kỹ năng: **đọc tên nhánh để hiểu chính xác dữ liệu và hành vi**, thay vì chỉ làm cho code biên dịch.

## 14. Checklist khi review enum switch

1. **Tên enum type** có nói rõ domain, chẳng hạn `OrderStatus`, `PaymentStatus`, `TicketStatus`, hay chỉ là `State` không ngữ cảnh?
2. **Tên constant** có mô tả biến thể/trạng thái cụ thể? Có dùng `S1`, `TYPE_A`, `OTHERS`, `MISC` khó hiểu?
3. **Các constant cùng loại khái niệm** hay trộn lẫn trạng thái, thao tác, lỗi kỹ thuật, nhãn UI?
4. **Tên nhánh và hành động** có phân biệt rõ? `case PAID` không có nghĩa “thực hiện thu tiền lại”.
5. **Các case gộp bằng dấu phẩy** có thật sự có cùng hành vi **ở method này**? Có mất sự khác biệt nghiệp vụ ở method khác?
6. **Mọi enum constant đã được xét** trong switch expression chưa? `default` có vô tình che việc thêm trạng thái mới không?
7. **Đã quyết định chính sách cho null** chưa? Có cần `case null`, kiểm tra trước hoặc từ chối đầu vào?
8. **Nhãn hiển thị cho người dùng** có được tách khỏi `name()` và mã trao đổi ổn định nếu cần?
9. **Có phụ thuộc `ordinal()` để lưu dữ liệu** hoặc phân biệt trạng thái không? Nếu có, cần xem lại khả năng thay đổi thứ tự.
10. **Khi thay tên constant**, API, JSON, database, log và dữ liệu cũ có cần migration/compatibility không?

**Kết luận:** “Đặt tên nhánh enum có ý nghĩa” thực chất là thiết kế **từ vựng trạng thái rõ ràng** cho từng enum constant, rồi tổ chức `case` theo đúng hành vi nghiệp vụ. Java 21 hỗ trợ `switch expression` exhaustive, gộp nhiều hằng và xử lý `null`, nhưng compiler không thể thay người lập trình quyết định `PAID`, `REFUNDED` hay `DELIVERED` có ý nghĩa gì. Tên tốt làm nhánh dễ hiểu; tính exhaustive và kiểm thử giúp giữ chúng đúng khi domain phát triển.

### Tài liệu tham khảo

- [Oracle Java 21 — Enum Classes](https://docs.oracle.com/en/java/javase/21/language/enum-classes.html)
- [Oracle Java 21 — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html)
- [Java Language Specification 21 — §8.9 Enum Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.9)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
