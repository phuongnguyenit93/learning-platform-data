# Thay giá trị khó hiểu bằng tên hoặc mô hình phù hợp

Khi đọc một dòng mã như `if (status == 2 && amount >= 500_000 && attempts < 3)`, lập trình viên thường hiểu phép so sánh nhưng chưa biết **tại sao** các giá trị `2`, `500_000` và `3` lại xuất hiện. Chúng có thể là mã trạng thái, ngưỡng nghiệp vụ và số lần thử tối đa. Nếu phải tìm ở nhiều tệp hoặc hỏi người viết trước mới hiểu ý nghĩa, mã nguồn đang bắt người đọc tự giải mã thông tin mà chương trình lẽ ra có thể diễn đạt.

Trong module `CODE_QUALITY_FUNDAMENTALS`, khả năng đọc là một yếu tố giúp mã **đáng tin cậy, dễ hiểu và dễ thay đổi**. Đặt tên cho những giá trị có ý nghĩa và chọn mô hình dữ liệu phù hợp giúp người bảo trì biết một giá trị đại diện cho điều gì, dùng ở đâu và được phép mang những trạng thái nào. Đồng thời, người viết tránh nhầm đơn vị, trạng thái hoặc ý nghĩa khi sửa quy tắc.

Bài học thuộc chương **Khả năng đọc** này tập trung vào lựa chọn giữa một giá trị thô, hằng có tên, enum, kiểu dữ liệu miền và những cấu trúc biểu đạt ý nghĩa khác. Mục tiêu không phải tạo thêm lớp ở mọi nơi mà là giảm lượng kiến thức ngầm người đọc phải giữ trong đầu.

Sau bài học, bạn có thể:

- Nhận diện *magic number*, *magic string*, cờ boolean và những giá trị đặc biệt khó suy luận từ ngữ cảnh.
- Thay các giá trị có ý nghĩa ổn định bằng tên mô tả rõ luật hoặc đơn vị.
- Biết khi nào nên sử dụng `enum`, `record`, value object, `Optional` hoặc trạng thái riêng thay cho dữ liệu nguyên thủy.
- Phân biệt dữ liệu cấu hình với hằng số và biết lúc nào cần giữ một giá trị đơn giản.
- Refactor dần mã hiện có mà vẫn giữ nguyên hành vi có thể quan sát.

## 1. Vấn đề nằm ở ý nghĩa bị giấu, không nằm ở chữ số

Xét đoạn Java sau:

```java
if (order.getStatus() == 2
        && order.getTotal() >= 500_000
        && order.getRetryCount() < 3) {
    approve(order);
}
```

Chỉ nhìn đoạn này, người đọc chưa trả lời chắc chắn được:

1. `2` là trạng thái nào? Có phải đã thanh toán hay đang chờ xác nhận?
2. `500_000` là đồng, xu, điểm thưởng hay một loại đơn vị khác?
3. So sánh `>=` có chủ ý bao gồm đúng ngưỡng hay không?
4. `3` là số lần thử lại, hay tổng số lần thực hiện bao gồm lần đầu?
5. Những giá trị ấy là chính sách áp dụng cho mọi đơn hay thay đổi theo khu vực và khách hàng?

Một chú thích như `// 2 = paid` có thể giải đáp một phần, nhưng vẫn buộc người đọc ghép mã và chú thích; khi một bên thay đổi, bên kia dễ bị bỏ quên. Nếu ý nghĩa có thể được **biểu diễn trực tiếp trong mã**, đó thường là lựa chọn rõ ràng hơn.

Tuy vậy, không phải mọi literal đều là giá trị khó hiểu. Những đoạn như `count + 1`, `items.isEmpty()` hoặc `String.join(", ", names)` thường đã có ngữ cảnh đầy đủ. Không cần biến mọi `0`, `1` hay dấu phẩy thành hằng số.

**Câu hỏi hữu ích:** Một người đọc hiểu bài toán nhưng chưa biết đoạn triển khai này có thể suy ra ý nghĩa của giá trị ngay tại điểm sử dụng hay không?

## 2. Bước nhỏ nhất: đặt tên cho quy tắc

Giả sử giá giao hàng tiêu chuẩn là 25.000 đồng, miễn phí khi giá trị đơn từ 500.000 đồng. Một cách viết khó hiểu:

```java
long shippingFee(long subtotal) {
    if (subtotal >= 500_000) {
        return 0;
    }
    return 25_000;
}
```

Để hiển thị ngay ý nghĩa, ta có thể viết:

```java
final class ShippingPolicy {
    private static final long FREE_SHIPPING_THRESHOLD_VND = 500_000L;
    private static final long STANDARD_SHIPPING_FEE_VND = 25_000L;

    long shippingFeeVnd(long subtotalVnd) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Subtotal must be non-negative");
        }

        if (subtotalVnd >= FREE_SHIPPING_THRESHOLD_VND) {
            return 0L;
        }

        return STANDARD_SHIPPING_FEE_VND;
    }
}
```

Những tên này giải thích được hai thông tin mà bản đầu giấu đi:

- **Quy tắc:** `FREE_SHIPPING_THRESHOLD_VND` là ngưỡng miễn phí, không chỉ một con số tình cờ.
- **Đơn vị:** hậu tố `VND` làm rõ 500.000 là đồng Việt Nam, đồng thời nhắc nơi gọi truyền giá trị cùng đơn vị.

So sánh `subtotalVnd >= FREE_SHIPPING_THRESHOLD_VND` diễn tả quy tắc rõ hơn `subtotal >= 500_000`. Người sửa mã sẽ biết cần tìm nơi khai báo ngưỡng khi thay đổi chính sách.

### Tên tốt nói được vai trò và phạm vi

So sánh các tên:

| Tên thiếu nghĩa | Tên rõ hơn | Vì sao |
| --- | --- | --- |
| `MAX` | `MAX_LOGIN_ATTEMPTS` | Nêu đối tượng bị giới hạn |
| `TIMEOUT = 3000` | `PAYMENT_TIMEOUT = Duration.ofSeconds(3)` | Nêu tác vụ và đơn vị |
| `RATE = 10` | `DISCOUNT_PERCENT = 10` | Phân biệt tỷ lệ phần trăm với số tiền |
| `STATUS = 2` | `PaymentStatus.PAID` | Diễn đạt trạng thái nghiệp vụ |
| `TYPE = "E"` | `DeliveryMode.EXPRESS` | Thể hiện loại giao hàng |
| `value == -1` | `result.isEmpty()` khi -1 chỉ “không tìm thấy” | Diễn đạt việc thiếu kết quả |

Cần chọn tên đúng ngữ nghĩa thực tế. Ví dụ `MAX_RETRIES = 3` thường có nghĩa **ba lần thử lại sau lần đầu**; còn `MAX_ATTEMPTS = 3` thường bao gồm cả lần đầu. Hai cách đặt tên này có thể dẫn đến hành vi khác nhau.

### Khi nào không nên tạo hằng?

Một số giá trị là phần hiển nhiên của phép toán: `index + 1`, `balance == 0`, `percentage / 100.0`. Nếu đặt tên chỉ để tránh chữ số, mã có thể trở nên khó đọc hơn:

```java
private static final int ONE = 1;
int nextIndex = index + ONE;
```

`ONE` không thêm ý nghĩa nào. Hằng có ích khi **tên nói lên khái niệm hoặc quy tắc**, không phải khi nó chỉ lặp lại cách đọc chữ số.

Đồng thời, nếu một ngưỡng thay đổi theo cửa hàng, thời gian hay cấu hình vận hành, đưa nó thành `static final` cố định có thể không đúng mô hình. Hãy dùng tên rõ ràng cho cấu hình hoặc thành phần chính sách:

```java
record ShippingSettings(long freeShippingThresholdVnd,
                        long standardShippingFeeVnd) {
    ShippingSettings {
        if (freeShippingThresholdVnd < 0 || standardShippingFeeVnd < 0) {
            throw new IllegalArgumentException("Negative shipping setting");
        }
    }
}
```

Tên có ý nghĩa vẫn cần thiết, nhưng **nguồn của giá trị** có thể là cấu hình được kiểm tra thay vì hằng biên dịch.

## 3. Magic string: chuỗi có thể là dữ liệu, cũng có thể là mã hóa trạng thái

Xét ví dụ:

```java
if ("P".equals(payment.getStatus())) {
    showPendingMessage();
} else if ("D".equals(payment.getStatus())) {
    showPaidMessage();
}
```

`"P"` và `"D"` là mã ở một giao diện nào đó, nhưng nếu chỉ xem phần sử dụng thì không thể biết chắc ý nghĩa. Gõ sai `"D"` thành `"d"` vẫn biên dịch, và sửa tên trạng thái phải tìm mọi nơi dùng chuỗi tương ứng.

Nếu tập trạng thái đã xác định và được ứng dụng quản lý, có thể biểu diễn bằng `enum`:

```java
enum PaymentStatus {
    PENDING,
    PAID,
    FAILED
}
```

Ở tầng nghiệp vụ:

```java
void showMessage(PaymentStatus status) {
    switch (status) {
        case PENDING -> showPendingMessage();
        case PAID -> showPaidMessage();
        case FAILED -> showFailedMessage();
    }
}
```

Đoạn mã này dùng cú pháp Java 17. Mỗi giá trị là một **trạng thái có tên**; trình biên dịch kiểm tra việc truyền đúng kiểu. `PaymentStatus.PAID` rõ nghĩa hơn một chuỗi bất kỳ.

### Chuyển mã từ hệ thống ngoài tại ranh giới

Giả sử API bên ngoài thật sự quy định `"P"` là chờ, `"D"` là đã thanh toán và `"F"` là thất bại. Không nên đổi giao thức bên ngoài chỉ để hợp với tên nội bộ. Thay vào đó, dịch mã một lần ở ranh giới:

```java
enum PaymentStatus {
    PENDING("P"),
    PAID("D"),
    FAILED("F");

    private final String externalCode;

    PaymentStatus(String externalCode) {
        this.externalCode = externalCode;
    }

    static PaymentStatus fromExternalCode(String code) {
        for (PaymentStatus status : values()) {
            if (status.externalCode.equals(code)) {
                return status;
            }
        }
        throw new IllegalArgumentException("Unknown payment status: " + code);
    }
}
```

Dịch ngay ở lớp adapter giúp phần còn lại của chương trình không phải nhớ các mã `"P"`, `"D"`, `"F"`. Khi API mở rộng thêm một trạng thái, ranh giới chuyển đổi là nơi rõ ràng để đánh giá có cần cập nhật mô hình và xử lý nghiệp vụ hay không.

Ví dụ trên chọn từ chối mã lạ. Trong ứng dụng thật, nếu API có thể bổ sung mã mới mà không báo trước, chính sách có thể là ghi nhận trạng thái `UNKNOWN` và trì hoãn xử lý. **Không nên mặc định ánh xạ mã lạ thành `PAID` hoặc `FAILED` nếu chưa có quy tắc nghiệp vụ tương ứng.**

### Trường hợp chuỗi thô vẫn hợp lý

Một chuỗi tự do như tên khách hàng, ghi chú đơn hàng hoặc nội dung tìm kiếm **không phải** magic string chỉ vì nó là `String`. Không cần tạo `enum` cho dữ liệu vốn không có danh sách giá trị cố định.

Các chuỗi theo giao thức chuẩn cũng có thể giữ nguyên ngay tại ranh giới kỹ thuật khi thư viện và bối cảnh đã làm rõ chúng. Mục tiêu là làm sáng tỏ khái niệm nghiệp vụ, không thay thế mọi chuỗi ký tự.

## 4. Giá trị boolean: rõ trong điều kiện, mơ hồ khi truyền đối số

Đoạn này có vẻ ngắn:

```java
orderService.create(order, true, false);
```

Không có tên tham số ngay tại điểm gọi, người đọc không biết `true` và `false` nghĩa là gì. Có thể là xác nhận tồn kho, gửi email hoặc bật chế độ thử nghiệm. Đảo vị trí hai giá trị vẫn hợp lệ về mặt kiểu.

**Cách đơn giản nhất** là đặt tên phương thức diễn tả trường hợp sử dụng nếu thật sự có hai hành vi khác nhau:

```java
orderService.createAndNotify(order);
orderService.createWithoutNotification(order);
```

Nếu có nhiều lựa chọn cùng loại và cần truyền qua các tầng, một `enum` có thể rõ hơn:

```java
enum NotificationMode {
    SEND,
    SKIP
}

void create(Order order, NotificationMode mode) {
    // ...
}
```

Điểm gọi khi đó:

```java
orderService.create(order, NotificationMode.SEND);
```

Đây chỉ là minh họa; không nhất thiết tạo enum khi tham số boolean đã có ý nghĩa rõ tại nơi dùng, ví dụ `if (isArchived)`. Nếu phương thức có hai hay ba cờ boolean độc lập, nên đánh giá lại giao diện thay vì tạo tên hằng `TRUE` và `FALSE`.

**Lưu ý:** Một cặp cờ có thể biểu diễn tổ hợp không hợp lệ. Ví dụ `isPaid` và `isRefunded` đều `true` gây khó hiểu nếu nghiệp vụ không cho phép. Với trạng thái loại trừ nhau, một enum `PaymentState` thường bảo vệ mô hình tốt hơn hai boolean.

## 5. Giá trị đặc biệt như -1, 0, null: làm rõ “không có”

Một giá trị như `-1` thường mang ý nghĩa ngầm “không tìm thấy” hoặc “chưa xử lý”:

```java
int customerLevel = findCustomerLevel(customerId);

if (customerLevel != -1) {
    applyBenefits(customerLevel);
}
```

Bài toán ở đây là phương thức trả về **hai loại thông tin** qua một số nguyên: hoặc cấp độ khách hàng, hoặc không có kết quả. Người đọc phải biết quy ước `-1` của phương thức.

Khi “không có” là trường hợp bình thường, một kiểu biểu đạt tùy chọn giúp lộ rõ điều đó:

```java
import java.util.OptionalInt;

OptionalInt customerLevel = findCustomerLevel(customerId);

if (customerLevel.isPresent()) {
    applyBenefits(customerLevel.getAsInt());
}
```

`OptionalInt` làm cho trạng thái thiếu kết quả hiện diện ngay ở chữ ký hàm. Trong đoạn ví dụ, `getAsInt()` được gọi sau `isPresent()`, nên không ném ngoại lệ do rỗng.

Có thể dùng `Optional<T>` cho đối tượng, hoặc kết quả nghiệp vụ rõ ràng hơn nếu cần phân biệt “không tìm thấy”, “bị từ chối”, “chưa đủ quyền” và “lỗi hệ thống”. Các trường hợp này không nên đồng nhất thành `Optional.empty()` nếu người gọi phải xử lý khác nhau.

Không phải mọi `-1` đều cần thay đổi. Chẳng hạn `String.indexOf` của Java dùng `-1` với hợp đồng chuẩn được tài liệu hóa; nếu dùng trực tiếp trong một điều kiện ngắn, người đọc Java thường hiểu ngay. Quyết định nên dựa trên **ngữ cảnh và mức độ kiến thức ngầm**, không phải quy tắc cấm một literal.

### Null khác với giá trị rỗng hoặc giá trị mặc định

`null` có thể nghĩa là chưa biết, chưa tải, không áp dụng hoặc dữ liệu lỗi. Đặt `""`, `0` hoặc `false` thay cho `null` mà không xác định ý nghĩa có thể chỉ chuyển sự mơ hồ sang dạng khác.

Ví dụ, số tiền giảm bằng `0` có thể là giảm 0 đồng hợp lệ; còn “chưa tính chiết khấu” là một trạng thái khác. Nếu hai trường hợp dẫn đến hai hành vi nghiệp vụ, cần mô hình khác nhau thay vì cùng dùng `0`.

## 6. Khi tên riêng chưa đủ: dùng kiểu biểu đạt miền nghiệp vụ

Đặt tên biến là `orderId`, `userId`, `totalVnd` giúp ích cho người đọc, nhưng nếu tất cả đều là `String` hoặc `long`, trình biên dịch không ngăn được việc truyền nhầm:

```java
void cancelOrder(String orderId, String userId) {
    // ...
}

// Vẫn biên dịch, dù truyền nhầm vị trí:
cancelOrder(userId, orderId);
```

Nếu lỗi nhầm lẫn này có rủi ro đáng kể và kiểu dữ liệu xuất hiện rộng trong hệ thống, có thể tạo **value object** (đối tượng giá trị) mang nghĩa rõ ràng.

### Mô hình hóa định danh bằng record

```java
record OrderId(String value) {
    OrderId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Order ID must not be blank");
        }
    }
}

record UserId(String value) {
    UserId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("User ID must not be blank");
        }
    }
}

final class OrderService {
    void cancelOrder(OrderId orderId, UserId userId) {
        // Kiểm tra quyền và hủy đơn theo nghiệp vụ.
    }
}
```

Lúc này, lệnh `cancelOrder(new UserId("u1"), new OrderId("o1"))` sẽ **không biên dịch**, vì thứ tự kiểu sai. `record` trong Java 17 tự sinh các phương thức truy cập, `equals`, `hashCode` và `toString` theo thành phần; phần constructor nhỏ ở trên thêm ràng buộc đầu vào.

Việc tạo kiểu riêng giúp:

- **Phát hiện nhầm lẫn khi biên dịch:** `OrderId` không phải `UserId`.
- **Tập trung bất biến:** ID không được rỗng được kiểm tra tại một nơi.
- **Làm rõ API:** chữ ký nói trực tiếp phương thức cần loại định danh nào.
- **Tái sử dụng biểu đạt:** những nơi làm việc với cùng ID có thể dùng một hợp đồng thống nhất.

Đổi lại là thêm kiểu và việc chuyển đổi ở ranh giới JSON, database, URL hoặc framework. Trong mã nhỏ, nơi không có nguy cơ nhầm lẫn, một tham số `String orderId` vẫn có thể đủ rõ.

### Mô hình hóa số tiền và đơn vị

Hai số nguyên giống nhau có thể đại diện cho đồng, xu, đô la, điểm thưởng, khối lượng hoặc thời gian. Nếu đơn vị có ảnh hưởng lớn tới tính đúng đắn, chỉ đặt tên biến có thể chưa đủ:

```java
record MoneyVnd(long amount) {
    MoneyVnd {
        if (amount < 0) {
            throw new IllegalArgumentException("Amount cannot be negative");
        }
    }

    MoneyVnd add(MoneyVnd other) {
        return new MoneyVnd(Math.addExact(amount, other.amount()));
    }
}
```

Hàm `add` nhận đúng kiểu `MoneyVnd` và dùng `Math.addExact` để phát hiện tràn số thay vì âm thầm cho ra kết quả sai. Giá trị âm bị từ chối bởi bất biến của loại dữ liệu này. **Đây là mô hình dành cho số tiền không âm**, không nên dùng nguyên xi cho các nghiệp vụ cần biểu diễn hoàn tiền, điều chỉnh âm hoặc đa tiền tệ; khi đó mô hình phải được thiết kế theo đúng nghiệp vụ.

Dù dùng `record`, một mô hình miền tốt vẫn cần giải thích những quy tắc như làm tròn, giá trị tối đa hoặc cách quy đổi. Kiểu mạnh không tự bảo đảm tất cả phép tính tiền đều đúng.

### Dùng kiểu có sẵn khi chúng đã thể hiện ý nghĩa

Không cần viết một kiểu `TimeoutMilliseconds` nếu thư viện có sẵn kiểu thích hợp:

```java
import java.time.Duration;

private static final Duration PAYMENT_TIMEOUT =
        Duration.ofSeconds(3);
```

`Duration` diễn đạt khoảng thời gian và có các phép toán phù hợp. Nó tránh nhầm `3000` mili giây với `3000` giây. Tương tự, khi phù hợp hãy cân nhắc `LocalDate` cho ngày, `Instant` cho mốc thời gian, `URI` cho địa chỉ tài nguyên hay `UUID` cho định danh dạng UUID. Chọn kiểu phải khớp ý nghĩa thực tế: `LocalDate` không mang múi giờ và `Instant` không tự biểu diễn lịch kinh doanh địa phương.

## 7. Khi nhiều trạng thái cần hành vi riêng

Giả sử hệ thống xử lý giao hàng:

```java
if (shippingType == 1) {
    fee = 25_000;
} else if (shippingType == 2) {
    fee = 45_000;
} else {
    fee = 0;
}
```

Nhánh `else` đang biến mọi loại không nhận biết thành phí 0, có thể khiến hệ thống bán hàng tính thiếu phí. Thay mã loại bằng enum giúp thể hiện các lựa chọn được hỗ trợ:

```java
enum DeliveryMode {
    STANDARD,
    EXPRESS
}

final class ShippingFeeCalculator {
    long calculateVnd(DeliveryMode mode) {
        if (mode == null) {
            throw new IllegalArgumentException("Delivery mode is required");
        }

        return switch (mode) {
            case STANDARD -> 25_000L;
            case EXPRESS -> 45_000L;
        };
    }
}
```

`switch` expression không có nhánh `default` trong ví dụ. Vì `DeliveryMode` hiện có hai phần tử, trình biên dịch Java 17 kiểm tra tính đầy đủ của các case. Nếu sau này thêm `SAME_DAY` vào enum, nơi sử dụng `switch` này cần được cập nhật để bao quát giá trị mới.

Không nên thêm `default -> 0` chỉ để “dễ chạy” khi chưa hiểu ý nghĩa trạng thái mới. Trong nghiệp vụ có thể làm phát sinh sai phí.

Tuy nhiên, **enum giải quyết vấn đề đặt tên và giới hạn tập lựa chọn**, chưa chắc giải quyết vấn đề tách thuật toán. Nếu các cách giao hàng có công thức dài, phụ thuộc riêng và thay đổi độc lập, cân nhắc tách chính sách tính phí ra các thành phần phù hợp. Tránh đưa hàng trăm dòng thuật toán vào enum chỉ vì có thể gắn phương thức cho mỗi phần tử.

## 8. Phân biệt biểu diễn, chính sách và cấu hình

Một giá trị thô thường mang một trong ba vai trò:

| Vai trò | Ví dụ | Cách biểu đạt nên cân nhắc |
| --- | --- | --- |
| Biểu diễn theo giao thức | API ngoài trả mã `"D"` | Chuyển sang `PaymentStatus.PAID` tại ranh giới |
| Quy tắc nghiệp vụ cố định trong phiên bản hiện tại | Ngưỡng miễn phí 500.000 VND | Hằng có tên rõ hoặc tham số chính sách |
| Cấu hình khác nhau theo môi trường/khách hàng | Timeout 3 giây tại môi trường A, 5 giây tại B | Cấu hình có tên, kiểu và kiểm tra hợp lệ |

Một lỗi thiết kế phổ biến là trộn chúng với nhau. Ví dụ, mã `"D"` theo giao thức bên ngoài không nên được lặp trong mọi xử lý nội bộ. Ngược lại, giá trị `PAYMENT_TIMEOUT` dù có tên vẫn có thể cần lấy từ cấu hình theo môi trường.

Hãy hỏi:

1. Giá trị có **ý nghĩa gì** và đang được đo theo **đơn vị nào**?
2. Ai sở hữu định nghĩa: ứng dụng, bên ngoài hay người vận hành?
3. Nó có tập lựa chọn hữu hạn không?
4. Nó có bất biến hoặc phép toán riêng cần bảo vệ không?
5. Nếu thay đổi giá trị, bao nhiêu nơi cần sửa và cần kiểm thử lại điều gì?

Câu trả lời hướng tới giải pháp nhẹ nhất nhưng đủ diễn đạt ý nghĩa.

## 9. Dấu hiệu nên chọn từng mức biểu đạt

Có thể xem các lựa chọn như một dải mức độ:

```text
Literal có ngữ cảnh rõ
       |
       v
Biến/hằng có tên giải thích quy tắc và đơn vị
       |
       v
Enum cho tập trạng thái/loại hữu hạn
       |
       v
Value object/record cho khái niệm có bất biến riêng
       |
       v
Mô hình nghiệp vụ gồm nhiều trạng thái, chuyển đổi và hành vi
```

Đây **không phải lộ trình bắt buộc**. Nếu `Duration` sẵn có đã giải quyết được vấn đề, không cần tạo thêm record. Nếu trạng thái phụ thuộc hệ thống ngoài và biến động khó dự đoán, ép toàn bộ thành enum cố định cũng có thể làm việc tích hợp khó hơn.

Một ma trận đánh giá nhanh:

| Hiện tượng trong mã | Thay đổi thường phù hợp | Khi nào cần cân nhắc thêm |
| --- | --- | --- |
| `retryCount < 3`, 3 là giới hạn nghiệp vụ | `MAX_ATTEMPTS` hoặc `MAX_RETRIES` đúng nghĩa | Nếu số lần thay đổi theo môi trường, dùng cấu hình |
| `status.equals("P")` xuất hiện nhiều nơi | Enum/kiểu trạng thái, mapping tại ranh giới | Nếu đối tác có mã mở rộng, định nghĩa xử lý mã lạ |
| `send(order, true, false)` | Tên phương thức rõ hoặc enum cho mode | Nếu có nhiều cờ, thiết kế lại API |
| `amount == -1` nghĩa “chưa tính” | Kiểu tùy chọn hoặc trạng thái riêng | Nếu `-1` là giá trị hợp lệ, không dùng nó làm sentinel |
| Hai tham số `String` dễ truyền nhầm | Record như `UserId`, `OrderId` | Nếu API nhỏ và rủi ro thấp, tên tham số có thể đủ |
| `3000` có thể là ms hoặc giây | `Duration.ofSeconds(3)` | Đảm bảo thư viện nhận đúng đơn vị khi gọi |
| Enum chứa nhiều hành vi riêng rẽ dài | Tách chính sách hoặc thành phần nghiệp vụ | Không trừu tượng hóa khi biến thể vẫn ngắn, ổn định |

Nguyên tắc là **làm lộ ý nghĩa và ràng buộc trước, thêm cấu trúc khi nó giảm rủi ro hoặc chi phí thay đổi thực tế**.

## 10. Một lần refactor có kiểm soát

Giả sử mã cũ:

```java
boolean canRetry(String status, int count, long lastRequestTime) {
    return "T".equals(status)
            && count < 3
            && System.currentTimeMillis() - lastRequestTime > 1000;
}
```

Có ba kiến thức ngầm:

- `"T"` là trạng thái có thể thử lại.
- `3` là số lần thử tối đa (cần xác nhận có bao gồm lần đầu không).
- `1000` là khoảng chờ theo mili giây.

Bước đầu là xác nhận quy tắc nghiệp vụ và bảo vệ kết quả bằng test; sau đó biểu diễn đúng tên và đơn vị:

```java
import java.time.Duration;
import java.time.Instant;

enum RequestState {
    RETRYABLE,
    COMPLETED,
    REJECTED
}

final class RetryPolicy {
    private static final int MAX_ATTEMPTS = 3;
    private static final Duration MIN_RETRY_INTERVAL =
            Duration.ofSeconds(1);

    boolean canRetry(RequestState state, int attempts,
                     Instant lastAttempt, Instant now) {
        if (state == null || lastAttempt == null || now == null) {
            throw new IllegalArgumentException("Missing retry input");
        }
        if (attempts < 0) {
            throw new IllegalArgumentException("Invalid attempt count");
        }

        Duration elapsed = Duration.between(lastAttempt, now);
        return state == RequestState.RETRYABLE
                && attempts < MAX_ATTEMPTS
                && elapsed.compareTo(MIN_RETRY_INTERVAL) > 0;
    }
}
```

Điểm tốt hơn ở phiên bản mới:

- `RequestState.RETRYABLE` nói rõ trạng thái nào được phép thử lại.
- `MAX_ATTEMPTS` diễn đạt số lần thực hiện tính cả lần đầu, **nếu đó là quy tắc đã được xác nhận**.
- `Duration` và `Instant` thay cặp số mili giây thiếu ý nghĩa.
- `now` được truyền vào giúp kiểm thử thời gian ổn định, không phụ thuộc thời điểm chạy thực tế.
- Các đầu vào quan trọng được kiểm tra thay vì mặc nhiên chấp nhận `null` hoặc số lần âm.

Vẫn cần chú ý ranh giới: mã cũ chỉ cho phép thử lại khi đã qua **hơn** 1000 ms (`> 1000`). Nếu vô tình viết điều kiện sau trong phiên bản mới, chương trình sẽ cho phép thử lại ngay tại **đúng** một giây (`>= 1 giây`), làm thay đổi hành vi:

```java
boolean intervalElapsed = !now.isBefore(lastAttempt.plus(MIN_RETRY_INTERVAL));
```

Đó là lý do bản refactor ở trên dùng `elapsed.compareTo(MIN_RETRY_INTERVAL) > 0`. Đồng thời, chuyển từ `System.currentTimeMillis()` sang `Instant` cần xem xét nguồn thời gian, độ chính xác và cách lưu `lastAttempt`. Bài học từ sự khác biệt này là **đặt tên và mô hình tốt chưa đủ: phép so sánh, đơn vị và ranh giới phải được kiểm chứng bằng test**.

### Các bước refactor an toàn

1. **Ghi lại cách hiểu hiện tại:** `"T"` là gì, `3` đếm thế nào, `1000` có đơn vị nào, tình huống âm hoặc `null` xử lý ra sao.
2. **Viết test đặc tả:** kiểm tra trạng thái hợp lệ và không hợp lệ, ngưỡng 2/3 lần, thời điểm trước/đúng/sau một giây.
3. **Tạo tên hoặc mô hình nhỏ nhất:** hằng, enum, `Duration` hay value object theo đúng ý nghĩa.
4. **Chuyển đổi ở ranh giới:** mã ngoài tiếp tục được đọc vào nhưng quy tắc nội bộ dùng kiểu rõ nghĩa.
5. **Đổi điểm gọi và loại bỏ biểu diễn cũ:** tránh đồng thời dùng literal và hằng mới khiến quy tắc phân tán.
6. **Chạy lại test và rà soát hành vi:** nếu cần chủ ý đổi chính sách, đánh dấu đây là thay đổi chức năng riêng.

Bản refactor thường nên làm từng bước. Chỉ thay literal bằng hằng có tên đã có thể giảm đáng kể chi phí đọc mã, trước khi cân nhắc chuyển giao diện sang enum hoặc record.

## 11. Cạm bẫy khi “làm sạch” các giá trị khó hiểu

**Đặt tên không làm sáng ý nghĩa.** `VALUE_1`, `MAX_VALUE` hoặc `STATUS_A` chỉ che chữ số bằng chữ khác. Tên cần nói điều mà literal không thể tự nói.

**Biến mọi literal thành hằng.** `ZERO`, `ONE` hay `EMPTY_STRING` thường khiến mã phải nhảy tới nơi khai báo nhưng không được thêm thông tin. Chỉ đặt tên khi có khái niệm đằng sau.

**Thay giá trị cấu hình bằng hằng mã nguồn.** `static final` phù hợp với quy tắc cố định tại phiên bản đang chạy, không phù hợp nếu ngưỡng phải điều chỉnh độc lập theo khách hàng hoặc môi trường. Hãy phân biệt nguồn sở hữu của giá trị.

**Dùng enum mà bỏ qua mã không nhận biết.** Khi tích hợp với nguồn ngoài, mọi mã chưa biết cần có chính sách xử lý được xác định. Ép nó thành một trạng thái nghiệp vụ khác có thể làm sai hành vi.

**Tạo quá nhiều lớp bọc.** Một `OrderId` có ích nếu giảm khả năng truyền nhầm và tập trung validation. Nhưng một chuỗi kiểu `StringValue` → `TextValue` → `OrderIdValue` nhiều tầng có thể khiến người đọc khó theo dõi nếu không có bất biến riêng.

**Che mất thông tin về đơn vị.** `amount`, `distance` hay `time` là tên còn thiếu. Dùng tên và kiểu phù hợp; khi giao tiếp với thư viện nhận số nguyên, phải chuyển đúng đơn vị.

**Thay đổi nghiệp vụ ngoài ý muốn khi refactor.** Sự khác nhau giữa `<` và `<=`, giữa “lần thử lại” và “tổng số lần”, giữa null và giá trị 0 có thể gây lỗi ở ranh giới. Kiểm thử phải bảo vệ những ranh giới này.

**Dùng giá trị mặc định để nuốt dữ liệu sai.** Một phương thức `parseStatus` trả `PAID` khi mã không hợp lệ trông có vẻ tiện nhưng tạo nguy cơ nghiêm trọng. Giá trị mặc định cần có cơ sở nghiệp vụ, không phải chỉ để tránh ngoại lệ.

## 12. Tình huống vận dụng

### Tình huống A: chính sách chiết khấu

Hệ thống có câu lệnh:

```java
if (total >= 1_000_000) {
    discount = total * 15 / 100;
}
```

Hãy xác định: ngưỡng và tỷ lệ do ai quản lý? Đơn vị của `total` và `discount` là gì? Phép chia số nguyên có chủ đích làm tròn xuống không? Bạn có thể đặt `DISCOUNT_THRESHOLD_VND` và `DISCOUNT_PERCENT`, hoặc tạo chính sách chiết khấu khi có nhiều phân khúc khách hàng. Đừng thay đổi phép làm tròn chỉ vì đổi tên.

### Tình huống B: quyền người dùng

API trả chuỗi quyền `"A"`, `"E"`, `"V"`, còn nội bộ dùng nhiều điều kiện so sánh chuỗi. Cần tìm nơi ánh xạ mã ngoài sang những vai trò có tên và nơi kiểm tra quyền nghiệp vụ. Nếu quyền là tổ hợp nhiều khả năng độc lập, một enum vai trò duy nhất có thể không đủ; có thể cần tập quyền hoặc mô hình phân quyền phù hợp.

### Tình huống C: gửi thông báo

Một hàm gọi `send(message, true, false, true)`. Hãy phân tích từng cờ quyết định điều gì. Nếu có những tổ hợp không hợp lệ, đề xuất API theo trường hợp sử dụng hoặc một đối tượng tùy chọn có validation; nếu chỉ có hai hành vi ngắn, tên phương thức rõ ràng có thể là đủ.

### Tình huống D: “không có dữ liệu”

Hàm `lookupPrice(productId)` trả `-1` nếu chưa có giá, `0` nếu hàng tặng kèm và số dương nếu có giá. Hãy chọn cách biểu diễn để người gọi phân biệt ba trường hợp. `OptionalLong` có thể biểu diễn “không có giá” và vẫn giữ `0` hợp lệ; nếu giá còn ở trạng thái “đang xác minh”, cần kiểu trạng thái rõ hơn.

Với mỗi tình huống, thử mô phỏng một lần thay đổi yêu cầu: bổ sung một trạng thái, đổi đơn vị, điều chỉnh ngưỡng hoặc thêm kênh gửi. Quan sát lựa chọn tên và kiểu dữ liệu có giúp tìm đúng điểm sửa, giảm tác động và kiểm thử dễ dàng hơn không.

## 13. Ghi nhớ

Thay giá trị khó hiểu là chuyển **ý nghĩa đang nằm trong đầu người viết** thành **ý nghĩa có thể nhìn thấy và được kiểm tra trong mã nguồn**:

- Dùng literal trực tiếp khi ngữ cảnh đã diễn đạt đầy đủ và không có quy tắc ẩn.
- Dùng biến hoặc hằng có tên khi giá trị đại diện cho ngưỡng, giới hạn hay luật nghiệp vụ.
- Dùng enum khi có tập lựa chọn hữu hạn cần phân biệt rõ, kèm chính sách xử lý mã ngoài.
- Dùng kiểu thư viện như `Duration` hoặc value object khi đơn vị, bất biến hay nguy cơ truyền nhầm đáng để bảo vệ bằng kiểu.
- Phân biệt giá trị cố định với cấu hình và phân biệt “không có”, “chưa biết”, “không hợp lệ” với các giá trị hợp lệ.
- Kiểm thử ranh giới, đơn vị và tính tương đương hành vi khi chuyển sang cách biểu đạt mới.

Mã dễ đọc giúp người bảo trì hiểu **vì sao giá trị đó có mặt, nó có nghĩa gì và thay đổi nó sẽ ảnh hưởng điều gì**. Một tên đúng hoặc mô hình nhỏ, phù hợp với bối cảnh có thể ngăn lỗi hiệu quả hơn nhiều lớp trừu tượng không mang thêm thông tin.
