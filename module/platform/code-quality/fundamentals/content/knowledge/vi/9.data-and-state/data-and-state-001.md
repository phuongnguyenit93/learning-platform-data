# Biểu diễn dữ liệu sao cho giảm trạng thái không hợp lệ

Một lỗi phần mềm đôi khi bắt đầu rất sớm, ngay từ cách thiết kế dữ liệu. Nếu một đơn thanh toán có ba cờ **đã thanh toán**, **đã hoàn tiền** và **đã hủy**, chương trình có thể biểu diễn trường hợp cả ba cờ đều đúng, dù quy trình nghiệp vụ không cho phép. Từ đó, mỗi phương thức phải kiểm tra thêm hàng loạt tổ hợp, và một nhánh bị bỏ sót có thể dẫn tới hoàn tiền sai, gửi thông báo sai hoặc lưu dữ liệu mâu thuẫn.

Trong chương **Dữ liệu và trạng thái** của module **CODE_QUALITY_FUNDAMENTALS**, việc lựa chọn cách biểu diễn dữ liệu là một phần quan trọng để mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Một thiết kế tốt giúp người đọc biết điều gì có thể xảy ra, ngăn tạo giá trị vô nghĩa ở những nơi có thể và tập trung kiểm tra các ràng buộc còn lại tại đúng ranh giới.

Nguyên tắc chủ đạo:

> Hãy thiết kế kiểu dữ liệu để những trạng thái không hợp lệ khó được tạo ra, dễ bị phát hiện hoặc, khi có thể, không thể biểu diễn bằng kiểu đó.

Đây là mục tiêu thiết kế, không phải lời hứa rằng hệ thống sẽ không bao giờ có dữ liệu sai. Tính đúng đắn còn phụ thuộc vào kiểm tra đầu vào, giao dịch, xử lý đồng thời, lưu trữ và các quy tắc thay đổi theo thời gian.

## 1. Trạng thái không hợp lệ là gì?

**Trạng thái** (*state*) là tập dữ kiện mô tả tình huống hiện tại của một đối tượng hoặc quy trình. **Trạng thái không hợp lệ** là tổ hợp dữ kiện vi phạm các quy tắc mà hệ thống đã cam kết duy trì.

Ví dụ:

| Đối tượng | Trạng thái hợp lệ | Trạng thái không hợp lệ |
| --- | --- | --- |
| Dòng hàng trong đơn | Mã hàng có giá trị, số lượng dương, đơn giá không âm | Số lượng -3 hoặc mã hàng rỗng |
| Thanh toán | Đang chờ; đã thanh toán với mã giao dịch; đã hoàn tiền với dữ kiện hoàn tiền | Đã hoàn tiền nhưng không có thông tin giao dịch gốc |
| Giao hàng | Giao tận nơi kèm địa chỉ; nhận tại cửa hàng kèm mã cửa hàng | Chọn nhận tại cửa hàng nhưng chỉ có địa chỉ giao tận nơi |
| Kho hàng | Số lượng đặt giữ không vượt số có thể bán, theo quy tắc kho | Hai yêu cầu đồng thời cùng giữ vượt tồn kho |
| Phiên làm việc | Đã xác thực có danh tính được xác minh | Cờ đã xác thực đúng nhưng không có danh tính |

Một số ràng buộc chỉ dựa vào **một giá trị**, như số lượng phải lớn hơn 0. Một số ràng buộc liên quan **nhiều trường**, như đơn đã thanh toán phải có mã giao dịch. Một số khác phụ thuộc **lịch sử hoặc dữ liệu bên ngoài**, như một ghế chưa bị người khác đặt.

Ba loại ràng buộc này cần các cách bảo vệ khác nhau; không nên kỳ vọng chỉ đổi kiểu Java là giải quyết được mọi vấn đề nghiệp vụ.

### 1.1. Bất biến dữ liệu

**Bất biến** (*invariant*) là điều kiện phải đúng tại những thời điểm được hợp đồng xác định. Với một đối tượng giá trị, bất biến thường phải đúng **ngay sau khi xây dựng** và trong suốt thời gian đối tượng tồn tại.

Ví dụ, nếu **OrderLine** đại diện cho một dòng hàng có số lượng bán, có thể yêu cầu:

- Mã sản phẩm không null và không chỉ chứa khoảng trắng.
- Số lượng lớn hơn 0.
- Đơn giá VND không âm.
- Phép nhân đơn giá với số lượng không tràn kiểu số.

Bất biến khác với một **yêu cầu tạm thời**. Chẳng hạn, “đơn hàng được hoàn tất trước 17 giờ” có thể là mục tiêu xử lý, còn “số lượng dòng hàng không âm” là ràng buộc của dữ liệu. Phải xác định đúng điều gì cần luôn đúng và điều gì chỉ cần đúng tại một bước cụ thể.

## 2. Cờ Boolean độc lập dễ tạo tổ hợp vô nghĩa

Giả sử quy trình thanh toán chỉ cho phép bốn trạng thái:

1. **PENDING:** chưa thanh toán.
2. **PAID:** đã thanh toán thành công.
3. **REFUNDED:** đã hoàn toàn tiền sau khi thanh toán.
4. **CANCELLED:** hủy khi còn chờ thanh toán.

Quy tắc trong ví dụ: thanh toán đã hủy không được chuyển thành đã trả tiền; chỉ thanh toán thành công mới có thể hoàn tiền. Quy trình hoàn tiền một phần không nằm trong phạm vi ví dụ này.

Một cách biểu diễn dễ gặp là:

~~~java
public final class PaymentFlags {
    public boolean paid;
    public boolean refunded;
    public boolean cancelled;
}
~~~

Ba cờ độc lập có thể tạo ra **2 × 2 × 2 = 8 tổ hợp**. Nhưng theo hợp đồng trên, chỉ bốn tổ hợp có ý nghĩa:

| paid | refunded | cancelled | Diễn giải |
| --- | --- | --- | --- |
| false | false | false | PENDING |
| true | false | false | PAID |
| true | true | false | REFUNDED |
| false | false | true | CANCELLED |
| false | true | false | Không thể hoàn tiền khi chưa thanh toán |
| false | true | true | Vừa hủy vừa hoàn tiền khi chưa thanh toán |
| true | false | true | Vừa thanh toán vừa hủy |
| true | true | true | Vừa thanh toán, hoàn tiền và hủy |

Ngoài các tổ hợp sai, trạng thái còn dễ bị **cập nhật một phần**:

~~~java
payment.paid = true;
payment.refunded = true;
// Nếu code dừng ở đây hoặc một luồng khác ghi thêm cancelled,
// mọi nơi đọc phải tự suy luận tổ hợp các cờ.
~~~

Việc thay đổi một cờ riêng lẻ không diễn đạt được *một chuyển trạng thái nghiệp vụ trọn vẹn*. Những phương thức khác nhau có thể hiểu các tổ hợp không nhất quán theo các cách khác nhau.

### 2.1. Khi enum là đủ

Nếu chỉ cần một nhãn trạng thái, **enum** loại bỏ các tổ hợp Boolean không hợp lệ:

~~~java
public enum PaymentStatus {
    PENDING,
    PAID,
    REFUNDED,
    CANCELLED
}
~~~

Khi đó, một thanh toán chỉ có **một** trong bốn trạng thái, thay vì ba cờ có thể mâu thuẫn. Enum cũng hỗ trợ **switch** rõ nghĩa.

Tuy nhiên, enum **chưa bảo đảm đầy đủ dữ liệu đi kèm từng trạng thái**. Một đối tượng có:

~~~java
PaymentStatus status;
String paymentId;
String refundId;
~~~

vẫn có thể mang **status = REFUNDED** nhưng **refundId = null** nếu không có ràng buộc bổ sung. Enum là bước đơn giản đầu tiên, không phải đáp án chung cho mọi trường hợp.

## 3. Biểu diễn lựa chọn bằng những biến thể có dữ liệu riêng

Khi mỗi trạng thái cần dữ liệu khác nhau, có thể dùng **kiểu tổng** (*sum type*): đối tượng thuộc **một trong các biến thể**, và mỗi biến thể chỉ mang những dữ liệu phù hợp.

Java 17 cung cấp **sealed interface** và **record** để biểu diễn trường hợp này tương đối trực tiếp:

~~~java
import java.time.Instant;
import java.util.Objects;

public sealed interface PaymentState
        permits PaymentState.Pending,
                PaymentState.Paid,
                PaymentState.Refunded,
                PaymentState.Cancelled {

    record Pending() implements PaymentState {}

    record Paid(String paymentId, Instant paidAt)
            implements PaymentState {
        public Paid {
            requireText(paymentId, "paymentId");
            Objects.requireNonNull(paidAt, "paidAt");
        }
    }

    record Refunded(String paymentId, String refundId,
                    Instant refundedAt) implements PaymentState {
        public Refunded {
            requireText(paymentId, "paymentId");
            requireText(refundId, "refundId");
            Objects.requireNonNull(refundedAt, "refundedAt");
        }
    }

    record Cancelled(String reason) implements PaymentState {
        public Cancelled {
            requireText(reason, "reason");
        }
    }

    private static void requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " is blank");
        }
    }
}
~~~

Trong ví dụ:

- **Pending** không có mã thanh toán vì chưa xảy ra thanh toán.
- **Paid** luôn mang mã thanh toán và thời điểm thanh toán hợp lệ theo kiểm tra xây dựng.
- **Refunded** mang mã giao dịch gốc, mã hoàn tiền và thời điểm hoàn tiền.
- **Cancelled** có lý do hủy; không chứa những trường của trạng thái đã thanh toán.
- **sealed** giới hạn những biến thể triển khai **PaymentState** tại vị trí định nghĩa kiểu.

Cách này giúp việc kiểm tra từng trường hợp trở nên rõ ràng hơn:

~~~java
public String describePayment(PaymentState state) {
    return switch (state) {
        case PaymentState.Pending ignored -> "Chưa thanh toán";
        case PaymentState.Paid paid ->
                "Đã thanh toán: " + paid.paymentId();
        case PaymentState.Refunded refunded ->
                "Đã hoàn tiền: " + refunded.refundId();
        case PaymentState.Cancelled cancelled ->
                "Đã hủy: " + cancelled.reason();
    };
}
~~~

Ví dụ **switch pattern matching** trên dùng cú pháp chính thức trong **Java 21**. Nếu dự án chạy Java 17, có thể xử lý các biến thể bằng **instanceof** hoặc cơ chế phù hợp khác; định nghĩa sealed interface và record bên trên vẫn là cấu trúc Java 17.

**Giới hạn quan trọng:** người gọi vẫn có thể tự tạo **new PaymentState.Refunded(...)** mà chưa từng tạo **Paid**, nếu constructor được công khai như trên. Kiểu dữ liệu giúp loại bỏ nhiều tổ hợp trường sai, nhưng **lịch sử chuyển trạng thái** cần được kiểm soát ở nơi quản lý nghiệp vụ. Ngoài ra, các định dạng lưu trữ hoặc thư viện serialization phải ánh xạ đúng từng biến thể và kiểm tra dữ liệu tại ranh giới nhập.

## 4. Chuyển trạng thái là một quy tắc riêng

Biểu diễn một trạng thái hợp lệ chưa đủ: cần bảo đảm **chuyển từ trạng thái cũ sang trạng thái mới** cũng hợp lệ.

Với hợp đồng thanh toán đang xét:

| Trạng thái hiện tại | Sự kiện | Trạng thái tiếp theo | Hợp lệ? |
| --- | --- | --- | --- |
| PENDING | Thanh toán thành công | PAID | Có |
| PENDING | Hủy | CANCELLED | Có |
| PAID | Hoàn tiền toàn bộ | REFUNDED | Có |
| PAID | Hủy như đơn chưa thanh toán | CANCELLED | Không |
| CANCELLED | Thanh toán thành công | PAID | Không |
| REFUNDED | Hoàn tiền lần nữa | REFUNDED | Không, theo hợp đồng ví dụ |

Ta có thể đặt các chuyển trạng thái trong một thành phần riêng:

~~~java
import java.time.Instant;
import java.util.Objects;

public final class PaymentTransitions {
    private PaymentTransitions() {}

    public static PaymentState markPaid(
            PaymentState current, String paymentId, Instant paidAt) {
        Objects.requireNonNull(current, "current");
        if (!(current instanceof PaymentState.Pending)) {
            throw new IllegalStateException(
                    "Only pending payments may be paid");
        }
        return new PaymentState.Paid(paymentId, paidAt);
    }

    public static PaymentState refund(
            PaymentState current, String refundId, Instant refundedAt) {
        Objects.requireNonNull(current, "current");
        if (!(current instanceof PaymentState.Paid paid)) {
            throw new IllegalStateException(
                    "Only paid payments may be refunded");
        }
        return new PaymentState.Refunded(
                paid.paymentId(), refundId, refundedAt);
    }

    public static PaymentState cancel(
            PaymentState current, String reason) {
        Objects.requireNonNull(current, "current");
        if (!(current instanceof PaymentState.Pending)) {
            throw new IllegalStateException(
                    "Only pending payments may be cancelled");
        }
        return new PaymentState.Cancelled(reason);
    }
}
~~~

Các phương thức trên tạo **trạng thái mới** thay vì sửa nhiều cờ trên cùng đối tượng. Trong phạm vi một phép tính thuần, nếu điều kiện không hợp lệ thì ném lỗi và không có trạng thái mới được trả về.

Khi đặt vào một hệ thống thực, vẫn cần giải quyết ít nhất hai vấn đề:

1. **Chuyển trạng thái cạnh tranh:** hai yêu cầu cùng đọc PENDING có thể cùng tạo ra PAID và CANCELLED. Cần giao dịch, khóa, phiên bản hoặc cập nhật có điều kiện khi ghi để chỉ một kết quả hợp lệ được cam kết.
2. **Tác dụng phụ bên ngoài:** gọi cổng thanh toán hoặc hoàn tiền là hành động có thể xảy ra trước/sau khi trạng thái DB được cập nhật. Cần cơ chế retry, đối soát, idempotency và quản lý trạng thái trung gian theo nghiệp vụ.

Một mô hình kiểu tốt làm cho quy tắc **dễ thấy và dễ kiểm thử**, nhưng không tự cung cấp tính nguyên tử cho toàn bộ hệ thống.

## 5. Value object ngăn giá trị vô nghĩa ngay khi xây dựng

Không phải mọi vấn đề đều cần sealed interface. Với ràng buộc thuộc **một giá trị hoặc một nhóm giá trị gắn bó**, một **value object** với constructor kiểm tra bất biến thường đơn giản và hiệu quả.

### 5.1. Ví dụ dòng hàng trong đơn

~~~java
public record OrderLine(
        String sku,
        long unitPriceVnd,
        int quantity) {

    public OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU is blank");
        }
        if (unitPriceVnd < 0) {
            throw new IllegalArgumentException("Negative price");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Invalid quantity");
        }

        // Kiểm tra tổng dòng hàng phải biểu diễn được bằng long.
        Math.multiplyExact(unitPriceVnd, quantity);
    }

    public long totalVnd() {
        return Math.multiplyExact(unitPriceVnd, quantity);
    }
}
~~~

Với cách này:

- Không thể tạo một **OrderLine** có quantity bằng 0 hoặc âm qua constructor được định nghĩa.
- Mã SKU rỗng bị từ chối ngay khi dữ liệu đi vào miền nghiệp vụ.
- Một tổ hợp giá và số lượng làm tràn kiểu **long** bị phát hiện sớm.
- Các trường của record là **final**, kiểu String và các kiểu nguyên thủy không cung cấp phương thức sửa giá trị tại chỗ.

Ngược lại, nếu dùng ba trường công khai có thể thay đổi, mỗi nơi dùng phải tự kiểm tra lại và một phương thức có thể làm quantity từ 1 thành -1 sau khi đối tượng được tạo.

Ở ví dụ này, đơn giá 0 được chấp nhận vì có thể có sản phẩm tặng kèm. Nếu chính sách thật yêu cầu đơn giá dương, ràng buộc constructor phải thay đổi tương ứng. **Dữ liệu hợp lệ phải xuất phát từ hợp đồng nghiệp vụ, không phải sở thích của lập trình viên.**

### 5.2. Bất biến của tập hợp và sao chép phòng vệ

Một record chứa **List** chưa chắc bất biến:

~~~java
public record UnsafeDraft(java.util.List<OrderLine> lines) {}
~~~

Đối tượng bên ngoài có thể sửa danh sách được truyền vào sau khi tạo record, khiến nội dung của **UnsafeDraft** thay đổi mà không đi qua bất kỳ kiểm tra nào.

Ví dụ thiết kế chặt chẽ hơn:

~~~java
import java.util.List;
import java.util.Objects;

public record OrderDraft(List<OrderLine> lines) {
    public OrderDraft {
        Objects.requireNonNull(lines, "lines");
        lines = List.copyOf(lines);
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("Empty order");
        }

        long total = 0L;
        for (OrderLine line : lines) {
            total = Math.addExact(total, line.totalVnd());
        }
    }

    public long totalVnd() {
        long total = 0L;
        for (OrderLine line : lines) {
            total = Math.addExact(total, line.totalVnd());
        }
        return total;
    }
}
~~~

**List.copyOf** tạo hoặc dùng lại một danh sách **không thể thay đổi bằng thao tác thêm/xóa/thay phần tử**, đồng thời từ chối phần tử null. Với **OrderLine** là giá trị bất biến như ví dụ, bản sao này giúp tránh thay đổi gián tiếp từ danh sách ban đầu. Constructor còn ngăn đơn rỗng và tổng vượt giới hạn biểu diễn của long.

Điều quan trọng là **bất biến sâu**: nếu phần tử trong List là một đối tượng mutable khác, **List.copyOf** không tự sao chép phần tử đó. Khi đó có thể cần giá trị bất biến, sao chép phòng vệ cho từng phần tử hoặc hợp đồng sở hữu rõ ràng.

## 6. Dữ liệu tùy chọn: không để những trường vô nghĩa xuất hiện cùng nhau

Giả sử ứng dụng hỗ trợ hai cách nhận hàng:

- **Giao tận nhà:** phải có địa chỉ giao hàng.
- **Nhận tại cửa hàng:** phải có mã cửa hàng.

Một cấu trúc như sau tạo ra nhiều tổ hợp sai:

~~~java
public record DeliveryRequest(
        boolean pickup,
        String storeId,
        String address) {}
~~~

Với **pickup = true**, cả địa chỉ lẫn mã cửa hàng có thể null; với **pickup = false**, cả hai lại có thể cùng hiện diện. Người đọc phải tự nhớ trường nào có ý nghĩa theo cờ.

Có thể biểu diễn thành hai biến thể:

~~~java
public sealed interface DeliveryMethod
        permits DeliveryMethod.HomeDelivery,
                DeliveryMethod.StorePickup {

    record HomeDelivery(ShippingAddress address)
            implements DeliveryMethod {
        public HomeDelivery {
            java.util.Objects.requireNonNull(address, "address");
        }
    }

    record StorePickup(String storeId)
            implements DeliveryMethod {
        public StorePickup {
            if (storeId == null || storeId.isBlank()) {
                throw new IllegalArgumentException("Store ID is blank");
            }
        }
    }
}

record ShippingAddress(String street, String city) {
    public ShippingAddress {
        if (street == null || street.isBlank()
                || city == null || city.isBlank()) {
            throw new IllegalArgumentException("Invalid shipping address");
        }
    }
}
~~~

Từ đây, người đọc biết:

- **HomeDelivery** luôn mang **ShippingAddress** đã qua kiểm tra.
- **StorePickup** luôn mang một mã cửa hàng không rỗng.
- Không còn trường **address** vô nghĩa trên biến thể nhận tại cửa hàng.

Nếu **StorePickup** phải dùng một cửa hàng thực sự đang hoạt động, kiểm tra này cần thông tin từ kho dữ liệu. Kiểu **String không rỗng** chỉ bảo đảm tính hợp lệ cú pháp, chưa chứng minh mã cửa hàng tồn tại.

### 6.1. Khi nào dùng Optional, nullable hoặc kiểu biến thể?

| Trường hợp | Cách biểu diễn thường phù hợp | Lưu ý |
| --- | --- | --- |
| Một truy vấn có thể không tìm thấy đối tượng | **Optional&lt;T&gt;** ở kết quả API, nếu phù hợp quy ước | Bên gọi phải xử lý trường hợp vắng mặt |
| Một trường có thể vắng mặt độc lập, thực sự hợp lệ | Kiểu nullable/Optional với hợp đồng rõ hoặc một giá trị đại diện có ý nghĩa | Tránh gán ý nghĩa mơ hồ cho null |
| Hai lựa chọn yêu cầu những trường khác nhau | **sealed interface** và các record biến thể | Giảm tổ hợp trường không liên quan |
| Một tập giá trị nhỏ, không có dữ liệu khác nhau | **enum** | Đơn giản hơn dựng một hệ kiểu lớn |
| Dữ liệu chưa được xác thực từ JSON hoặc form | DTO đầu vào với kiểm tra/mapping | Không coi DTO chưa kiểm tra là domain object hợp lệ |

Không nên biến mọi trường nullable thành một hierarchy phức tạp. Mục tiêu là **loại bỏ những trạng thái sai có ý nghĩa nghiệp vụ**, trong khi giữ thiết kế đủ dễ sử dụng và bảo trì.

## 7. Từ dữ liệu bên ngoài đến đối tượng hợp lệ

Dữ liệu từ HTTP, JSON, cơ sở dữ liệu, file CSV hoặc message broker có thể thiếu trường, sai kiểu, lỗi thời hoặc mâu thuẫn. Vì vậy thường cần một **ranh giới kiểm tra** trước khi đưa dữ liệu vào phần xử lý nghiệp vụ.

~~~text
JSON / Form / DB row
       |
       v
Đọc và giải mã dữ liệu
       |
       v
Kiểm tra và ánh xạ
       |
       v
Domain object đã giữ các bất biến cục bộ
       |
       v
Tính toán / chuyển trạng thái / điều phối
       |
       v
Ghi trạng thái với ràng buộc và cơ chế đồng thời
~~~

Ví dụ, một DTO có thể chứa các giá trị chưa được kiểm tra:

~~~java
public record OrderLineRequest(
        String sku,
        Long unitPriceVnd,
        Integer quantity) {}

public final class OrderLineMapper {
    public OrderLine toDomain(OrderLineRequest request) {
        if (request == null
                || request.unitPriceVnd() == null
                || request.quantity() == null) {
            throw new IllegalArgumentException("Missing order line data");
        }

        return new OrderLine(
                request.sku(),
                request.unitPriceVnd(),
                request.quantity());
    }
}
~~~

DTO dùng kiểu hộp **Long/Integer** để thể hiện trường có thể thiếu trong dữ liệu vào. Sau khi chuyển đổi, **OrderLine** kiểm tra các bất biến của miền nghiệp vụ. Việc ánh xạ cũng nên chuyển lỗi thành phản hồi API thích hợp ở tầng giao tiếp, thay vì lộ thông tin nội bộ không cần thiết.

**Không chỉ API mới là ranh giới:** khi đọc bản ghi DB từ phiên bản phần mềm cũ, lấy dữ liệu từ cache hoặc nhận sự kiện, vẫn cần lưu ý bất biến và tính tương thích của dữ liệu.

### 7.1. Đừng phụ thuộc vào đúng một lớp kiểm tra

Một constructor kiểm tra tốt không thay thế tất cả cơ chế:

- **Kiểu dữ liệu và constructor** bảo vệ một đối tượng trong bộ nhớ.
- **Validation ở ranh giới** giúp báo lỗi đầu vào dễ hiểu và từ chối dữ liệu không phù hợp.
- **Constraint của cơ sở dữ liệu** giúp ngăn một số bản ghi sai kể cả khi có nhiều ứng dụng cùng ghi, ví dụ NOT NULL, CHECK, UNIQUE và khóa ngoại nếu được hệ quản trị hỗ trợ.
- **Giao dịch và kiểm soát đồng thời** bảo vệ ràng buộc giữa nhiều bản ghi hoặc các chuyển trạng thái cạnh tranh.
- **Kiểm tra nghiệp vụ liên hệ hệ thống khác** xác nhận những điều mà kiểu dữ liệu cục bộ không thể biết, ví dụ khả năng thu tiền hoặc tình trạng tồn kho thực.

Ví dụ, ràng buộc **quantity > 0** có thể xuất hiện cả trong constructor **OrderLine** và một CHECK constraint trên cột lưu trữ. Đây là hai lớp bảo vệ cho những ranh giới khác nhau, không phải cùng một phép kiểm tra bị lặp vô ích.

## 8. Mô hình trạng thái tốt không thay thế tính nhất quán khi cập nhật

Giả sử hai tác vụ cùng đọc một bản ghi với trạng thái **PENDING**:

~~~text
Task A: đọc PENDING ----> tạo Paid ----> ghi Paid
Task B: đọc PENDING ----> tạo Cancelled -> ghi Cancelled
~~~

Cả **Paid** và **Cancelled** đều là các giá trị riêng lẻ hợp lệ. Nhưng nếu cả hai tác vụ đồng thời thực hiện tác dụng phụ rồi một bên ghi đè trạng thái của bên còn lại, kết quả có thể vi phạm lịch sử nghiệp vụ.

Một chiến lược là **cập nhật có điều kiện** theo trạng thái và phiên bản:

~~~sql
UPDATE payments
SET status = 'PAID',
    version = version + 1
WHERE id = :payment_id
  AND status = 'PENDING'
  AND version = :expected_version;
~~~

Nếu **số dòng được cập nhật bằng 0**, cần xử lý xung đột hoặc trạng thái đã thay đổi; không được mặc định thành công. Câu lệnh này chỉ minh họa điều kiện cập nhật: hệ thống thực còn cần cập nhật dữ liệu thanh toán đi kèm, chọn ranh giới giao dịch, chỉ mục, thứ tự tác dụng phụ và cách phục hồi khi kết quả ngoài DB không rõ ràng.

Với dữ liệu mà nhiều tiến trình có thể sửa, việc sở hữu một đối tượng record bất biến trong Java **không tự ngăn ghi đè** ở cơ sở dữ liệu. Cần kết hợp mô hình dữ liệu với hợp đồng cập nhật nhất quán.

## 9. Kiểm thử bất biến và chuyển trạng thái

Khi kiểu dữ liệu được thiết kế để giảm trạng thái sai, bài kiểm thử nên chứng minh hai nhóm hành vi:

1. **Giá trị hợp lệ có thể được tạo và sử dụng đúng**.
2. **Giá trị hoặc chuyển trạng thái không hợp lệ bị từ chối ở ranh giới đã định**.

Ví dụ với JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class DataModelTest {
    @Test
    void acceptsValidOrderLine() {
        OrderLine line = new OrderLine("BOOK-1", 50_000L, 2);
        assertEquals(100_000L, line.totalVnd());
    }

    @Test
    void rejectsInvalidQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> new OrderLine("BOOK-1", 50_000L, 0));
    }

    @Test
    void rejectsArithmeticOverflow() {
        assertThrows(ArithmeticException.class,
                () -> new OrderLine("BOOK-1", Long.MAX_VALUE, 2));
    }

    @Test
    void copiedLinesCannotBeChangedViaOriginalList() {
        List<OrderLine> mutable = new ArrayList<>();
        mutable.add(new OrderLine("BOOK-1", 50_000L, 2));
        OrderDraft draft = new OrderDraft(mutable);

        mutable.clear();

        assertEquals(1, draft.lines().size());
        assertThrows(UnsupportedOperationException.class,
                () -> draft.lines().clear());
    }

    @Test
    void onlyPendingPaymentCanBePaid() {
        Instant now = Instant.parse("2026-01-01T00:00:00Z");
        PaymentState paid = PaymentTransitions.markPaid(
                new PaymentState.Pending(), "PAY-1", now);

        assertInstanceOf(PaymentState.Paid.class, paid);
        assertThrows(IllegalStateException.class,
                () -> PaymentTransitions.markPaid(paid, "PAY-2", now));
    }

    @Test
    void refundCarriesOriginalPaymentId() {
        Instant now = Instant.parse("2026-01-01T00:00:00Z");
        PaymentState paid =
                new PaymentState.Paid("PAY-1", now);

        PaymentState refunded =
                PaymentTransitions.refund(paid, "REF-1", now);

        PaymentState.Refunded result =
                assertInstanceOf(PaymentState.Refunded.class, refunded);
        assertEquals("PAY-1", result.paymentId());
        assertEquals("REF-1", result.refundId());
    }
}
~~~

Các bài kiểm thử này kiểm tra giá trị, tính bất biến của danh sách và quy tắc chuyển trạng thái trong bộ nhớ. Chúng **không kiểm chứng được** rằng thanh toán thực tế chỉ xảy ra một lần, ghi DB không bị race condition hoặc sự kiện được gửi đúng một lần. Các hành vi ấy cần kiểm thử tích hợp và thiết kế nhất quán ở các ranh giới bên ngoài.

### 9.1. Kiểm thử theo thuộc tính

Với những miền giá trị lớn, ngoài ca điển hình còn có thể nghĩ theo **thuộc tính luôn phải đúng**:

- Mọi **OrderLine** được tạo thành công đều có **quantity > 0** và **unitPriceVnd >= 0**.
- Tổng của **OrderDraft** bằng tổng các **OrderLine.totalVnd()** nếu constructor thành công và không có tràn số.
- Sau khi gọi chuyển từ **Pending** sang **Paid**, trạng thái nhận được luôn mang mã thanh toán hợp lệ.
- Từ trạng thái **Cancelled**, mọi lời gọi **markPaid** theo chính sách hiện tại phải bị từ chối.
- Sau khi tạo **OrderDraft**, việc sửa danh sách nguồn không thay đổi các dòng trong bản nháp.

Có thể dùng kiểm thử sinh dữ liệu (*property-based testing*) để thử nhiều tổ hợp và kiểm tra các thuộc tính này, nhưng vẫn cần các ca biên có chủ đích và hiểu đúng hợp đồng.

## 10. Những đánh đổi cần cân nhắc

| Cách làm | Lợi ích | Chi phí hoặc giới hạn |
| --- | --- | --- |
| Thay nhiều cờ bằng enum | Dễ hiểu, ít tổ hợp mâu thuẫn | Không mang dữ liệu riêng cho từng trạng thái |
| Dùng sealed type và record | Diễn đạt biến thể và trường bắt buộc | Tăng số kiểu, cần cách serialize/deserialize phù hợp |
| Kiểm tra trong constructor | Lỗi được phát hiện ngay khi tạo đối tượng | Phải xử lý dữ liệu từ nguồn cũ, có thể tốn công ánh xạ |
| Dùng giá trị bất biến | Tránh sửa trạng thái sau khi đã kiểm tra | Có thể cần tạo bản sao khi thay đổi |
| Sao chép phòng vệ | Tránh sửa gián tiếp qua collection | Có chi phí bộ nhớ và sao chép; không tự tạo bất biến sâu |
| Ràng buộc DB và version | Bảo vệ dữ liệu trước các tác vụ ghi đồng thời | Thêm xử lý xung đột, migration và thiết kế giao dịch |

Không nên tạo hệ kiểu phức tạp cho một công việc có hai giá trị đơn giản, cũng không nên gom nhiều trạng thái nghiệp vụ khác nhau vào một kiểu chứa hàng loạt trường tùy chọn chỉ để giảm số lượng lớp.

**Ngưỡng phân tách phù hợp** được xác định bởi số trường hợp sai có thể phát sinh, mức độ nghiêm trọng nếu xảy ra, tần suất thay đổi của quy tắc và khả năng đọc/kiểm thử của đội ngũ.

## 11. Các hiểu nhầm phổ biến

**“Có enum thì mọi trạng thái đều hợp lệ.”** Enum ngăn giá trị trạng thái ngoài tập khai báo, nhưng không tự xác nhận dữ liệu đi kèm hoặc tính hợp lệ của chuyển trạng thái.

**“Record luôn bất biến.”** Trường của record là final nhưng phần tử được tham chiếu có thể là đối tượng mutable. List hoặc mảng trong record cần xem xét vấn đề chia sẻ tham chiếu.

**“Constructor đã kiểm tra nên không cần constraint trong DB.”** Nhiều đường ghi dữ liệu, nhiều tiến trình hoặc dữ liệu cũ có thể không đi qua cùng constructor. DB constraint bảo vệ ranh giới lưu trữ.

**“Giá trị hiện tại hợp lệ thì lịch sử chắc chắn hợp lệ.”** Một đối tượng Refunded có đủ mã vẫn có thể được tạo trực tiếp mà không có thanh toán trước đó. Kiểm soát chuyển trạng thái và lưu trữ mới xử lý lịch sử.

**“Đưa null vào Optional là giải quyết xong.”** Optional làm rõ khả năng vắng mặt ở một số API, nhưng nếu ý nghĩa các trường phụ thuộc lẫn nhau, vẫn có thể tồn tại tổ hợp sai. Khi đó cần mô hình các biến thể.

**“Từ chối càng nhiều giá trị càng tốt.”** Ràng buộc sai có thể làm hệ thống từ chối nghiệp vụ hợp lệ. Ví dụ hàng tặng kèm có giá 0 vẫn có thể hợp lệ; không nên tự ý yêu cầu đơn giá lớn hơn 0.

**“Bất biến trong bộ nhớ tự bảo đảm cập nhật đồng thời.”** Hai tiến trình có thể tính hai trạng thái hợp lệ từ cùng dữ liệu cũ; cơ sở dữ liệu phải phối hợp cập nhật và xử lý xung đột theo hợp đồng.

## 12. Quy trình thiết kế dữ liệu để giảm trạng thái sai

Khi thiết kế một đối tượng mới hoặc cải tiến cấu trúc cũ, có thể làm theo các bước:

1. **Liệt kê trường hợp hợp lệ:** Thảo luận với người hiểu nghiệp vụ về những trạng thái thực sự có thể xảy ra, kể cả trạng thái trung gian.
2. **Viết bất biến:** Trường nào phải có, giới hạn số nào hợp lệ, điều kiện nào liên quan hai hay nhiều trường.
3. **Tìm tổ hợp sai có thể biểu diễn:** Các cờ độc lập, trường nullable, các giá trị mặc định và dữ liệu dư thừa có tạo trạng thái vô nghĩa không?
4. **Chọn cấu trúc nhỏ nhất đủ rõ:** Kiểu nguyên thủy kèm validation, value object, enum hoặc sealed variant tùy quy tắc.
5. **Tạo đối tượng qua ranh giới kiểm tra:** Constructor, factory, mapper và validation từ DTO hoặc dữ liệu lưu trữ.
6. **Bảo vệ việc chia sẻ trạng thái:** Cân nhắc bất biến, sao chép phòng vệ, sở hữu collection và dữ liệu mutable.
7. **Định nghĩa các chuyển trạng thái:** Ai được thay đổi, từ đâu sang đâu, và điều gì xảy ra khi yêu cầu không hợp lệ.
8. **Bảo vệ trạng thái lưu trữ:** Dùng constraint, giao dịch, kiểm soát đồng thời và xử lý lỗi theo nhu cầu.
9. **Kiểm thử giá trị sai và giá trị biên:** Không chỉ xác nhận đường thành công, mà còn chứng minh đối tượng từ chối trạng thái vô nghĩa.
10. **Đánh giá chi phí sử dụng:** Kiểu dữ liệu có làm người đọc hiểu nhanh hơn và sửa quy tắc ít rủi ro hơn không?

Mục tiêu sau cùng là **chuyển một phần công việc kiểm tra từ mọi nơi sử dụng về nơi dữ liệu được tạo ra**, đồng thời vẫn giữ những kiểm tra phụ thuộc ngữ cảnh tại ranh giới phù hợp.

## 13. Tình huống luyện tập

Một hệ thống quản lý đăng ký khóa học có đối tượng:

~~~java
public class Enrollment {
    public boolean approved;
    public boolean cancelled;
    public String approvalCode;
    public String cancellationReason;
}
~~~

Quy tắc nghiệp vụ:

- Đăng ký mới ở trạng thái **đang chờ**.
- Đăng ký **được duyệt** cần mã xác nhận duyệt không rỗng.
- Đăng ký **bị hủy** cần lý do hủy không rỗng.
- Không thể vừa duyệt vừa hủy; chỉ các đăng ký đang chờ mới được duyệt hoặc hủy.

Hãy tự trả lời:

1. Kiểu hiện tại có thể biểu diễn những tổ hợp sai nào?
2. Chỉ thay hai cờ bằng một enum có giải quyết được vấn đề thiếu mã duyệt hoặc lý do hủy không?
3. Hãy đề xuất các biến thể dữ liệu và những trường bắt buộc cho mỗi biến thể.
4. Nên đặt quy tắc “chỉ từ đang chờ mới được duyệt hoặc hủy” ở đâu?
5. Nếu hai nhân viên duyệt và hủy cùng một đăng ký tại cùng thời điểm, cần cơ chế gì ngoài cấu trúc Java?

**Gợi ý đối chiếu:** Có thể thiết kế **Pending**, **Approved(approvalCode)** và **Cancelled(reason)**, kiểm tra chuỗi không rỗng khi tạo từng biến thể. Một hàm chuyển trạng thái chỉ chấp nhận **Pending** cho thao tác duyệt hoặc hủy. Nếu dữ liệu được lưu trong DB, cần cập nhật có điều kiện hoặc kiểm soát phiên bản/giao dịch để ngăn hai quyết định cạnh tranh cùng được xác nhận. Khi đổi cấu trúc, cũng phải kiểm tra cách chuyển đổi dữ liệu cũ và các trường hợp API đầu vào thiếu dữ liệu.

## 14. Ghi nhớ

- **Trạng thái không hợp lệ** là dữ liệu hoặc tổ hợp dữ liệu vi phạm quy tắc nghiệp vụ; cách biểu diễn có thể làm số trường hợp sai tăng hoặc giảm đáng kể.
- **Enum** phù hợp với một tập trạng thái đơn giản; **sealed interface và record** hữu ích khi mỗi trạng thái cần dữ liệu riêng.
- **Value object với validation** và **dữ liệu bất biến** giúp giữ bất biến từ lúc tạo đối tượng, tránh nhiều kiểm tra lặp lại ở nơi sử dụng.
- **Trạng thái hợp lệ** và **chuyển trạng thái hợp lệ** là hai điều khác nhau; lịch sử, đồng thời và các tác dụng phụ vẫn cần cơ chế kiểm soát tương ứng.
- Mô hình tốt kết hợp **kiểu dữ liệu, ranh giới kiểm tra, ràng buộc lưu trữ và kiểm thử**, để mã nguồn dễ hiểu và khó rơi vào tình huống sai khi mở rộng.
