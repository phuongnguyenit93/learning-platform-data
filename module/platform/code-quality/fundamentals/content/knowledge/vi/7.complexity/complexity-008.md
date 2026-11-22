# Đơn giản hóa điều kiện và loại bỏ trạng thái không cần thiết

> **Chương:** Độ phức tạp  
> **Học phần:** CODE_QUALITY_FUNDAMENTALS — Hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

Một phương thức có thể chỉ dài vài dòng nhưng vẫn khó hiểu nếu chứa nhiều nhánh phủ định, những điều kiện lặp lại hoặc các biến trạng thái phải luôn được cập nhật đồng bộ. Khi sửa một quy tắc nhỏ, người bảo trì phải tìm xem mọi nhánh và mọi cờ liên quan đã được sửa đúng chưa. Đây là một dạng **độ phức tạp không cần thiết**: mã buộc người đọc suy luận về nhiều trường hợp hơn số trường hợp nghiệp vụ thực sự có.

Hai cách cải thiện quan trọng là:

1. **Đơn giản hóa điều kiện** để các quyết định thể hiện trực tiếp ý định, không có nhánh hoặc phép so sánh dư thừa.
2. **Loại bỏ trạng thái không cần thiết** để tránh lưu nhiều biểu diễn của cùng một sự thật và giảm số tổ hợp trạng thái có thể xuất hiện.

Mục tiêu không phải số dòng ít nhất. Mục tiêu là khiến mã **dễ giải thích, khó rơi vào trạng thái mâu thuẫn và có thể thay đổi mà không làm sai hợp đồng**. Bài học tập trung vào Java, nhưng cách suy nghĩ áp dụng cho nhiều ngôn ngữ và mô hình ứng dụng.

## 1. Độ phức tạp đến từ quyết định và trạng thái

Xét hai phương thức trả cùng một điều kiện nghiệp vụ giả định: một tài khoản chỉ được thao tác khi đang hoạt động và không bị khóa.

```java
boolean canProceed(boolean active, boolean locked) {
    if (active == true) {
        if (locked == false) {
            return true;
        } else {
            return false;
        }
    } else {
        return false;
    }
}
```

```java
boolean canProceed(boolean active, boolean locked) {
    return active && !locked;
}
```

Với hai đầu vào Boolean thuần túy, hai phiên bản cho cùng kết quả. Phiên bản sau giúp người đọc nhận ra quy tắc ngay từ biểu thức thay vì lần qua nhiều đường `return`.

Nhưng số nhánh chỉ là một phần. Giả sử đối tượng còn lưu ba trường:

```java
boolean active;
boolean locked;
boolean canProceed; // Được cập nhật từ active và locked ở nơi khác.
```

Giá trị `canProceed` có thể được tính từ hai trường đầu. Nếu cả ba đều được ghi và sửa độc lập, ứng dụng có nguy cơ gặp trạng thái `active == false`, `locked == false`, `canProceed == true`. Vấn đề không nằm ở cú pháp `if` mà ở **hai nơi cùng tuyên bố một sự thật**.

| Nguồn độ phức tạp | Biểu hiện | Câu hỏi cần đặt ra |
| --- | --- | --- |
| Điều kiện lặp hoặc phủ định nhiều tầng | Khó biết khi nào một nhánh chạy | Có thể diễn đạt cùng quy tắc ngắn, rõ hơn không? |
| Nhánh không thể xảy ra | Mã chứa trường hợp bị bất biến loại trừ | Có thể thể hiện bất biến ở một ranh giới đáng tin cậy không? |
| Nhiều cờ biểu diễn một trạng thái | Có thể xuất hiện tổ hợp mâu thuẫn | Có nên dùng một kiểu trạng thái loại trừ nhau không? |
| Dữ liệu dẫn xuất được lưu riêng | Cần đồng bộ ở nhiều nơi | Có thể tính từ nguồn sự thật hiện có không? |
| Trạng thái thay đổi qua nhiều bước | Người đọc phải nhớ giá trị tạm thời | Có thể giảm phạm vi biến hoặc tạo giá trị bất biến không? |
| Điều kiện gắn với tác dụng phụ | Đổi thứ tự có thể đổi hành vi | Có thể tách phần tính quyết định khỏi phần thực hiện không? |

Hai hướng cải thiện có liên hệ: **điều kiện đơn giản hơn khi mô hình trạng thái biểu diễn đúng miền nghiệp vụ**, và mô hình trạng thái tốt giúp ít cần điều kiện phòng vệ trước những tổ hợp bất hợp lý.

## 2. Đơn giản hóa logic Boolean mà vẫn giữ đúng nghĩa

### 2.1. Bỏ phép so sánh Boolean dư thừa

```java
// Dài hơn mức cần thiết:
if (hasPermission == true && isBlocked == false) {
    grantAccess();
}

// Cùng ý nghĩa với các biến boolean:
if (hasPermission && !isBlocked) {
    grantAccess();
}
```

Không nên áp dụng máy móc cho kiểu `Boolean` có thể chứa `null`: khi tự động unbox một `Boolean` bằng `if (flag)`, Java có thể ném `NullPointerException`. Hãy quyết định rõ `null` có hợp lệ hay không, rồi chuẩn hóa hoặc xử lý tại ranh giới thích hợp.

### 2.2. Dùng các quy tắc Boolean khi toán hạng thuần túy

| Biểu thức | Có thể viết lại | Điều kiện áp dụng |
| --- | --- | --- |
| `!!a` | `a` | `a` là giá trị Boolean đã xác định |
| `!(a && b)` | `!a || !b` | Tương đương về giá trị và cách đánh giá khi dùng các toán tử logic tương ứng |
| `!(a || b)` | `!a && !b` | Quy tắc De Morgan |
| `a && true` | `a` | Không cần kiểm tra hằng `true` |
| `a || false` | `a` | Không cần nhánh `false` |
| `a && !a` | `false` | `a` phải là một giá trị đã tính ổn định, không phải hai lần gọi hàm có tác dụng phụ |
| `a || !a` | `true` | Cùng điều kiện về giá trị ổn định |

Ví dụ, với hai biến kiểu nguyên thủy:

```java
boolean canAccess = !(expired || suspended);
boolean canAccessSimplified = !expired && !suspended;
```

Hai biểu thức cho cùng kết quả. Tuy nhiên, việc viết lại **không nhất thiết khiến mã dễ hiểu hơn**: chọn cách gần với ngôn ngữ nghiệp vụ nhất. Có những trường hợp tên `isEligibleForRefund()` diễn đạt tốt hơn cả một biểu thức lặp lại trong nhiều chỗ.

### 2.3. Tránh phép phủ định kép

```java
if (!account.isNotVerified()) {
    // ...
}
```

Nếu mô hình cho phép, một tên như `account.isVerified()` thường dễ hiểu hơn. Tuy nhiên, **“không phải chưa xác minh” không luôn đồng nghĩa “đã xác minh”** nếu miền nghiệp vụ còn trạng thái `PENDING` hoặc `UNKNOWN`. Trước khi đổi tên hoặc gộp điều kiện, cần xác định tập trạng thái thực tế.

### 2.4. Loại bỏ nhánh trùng nhau

```java
// Hai nhánh cùng thực hiện một kết quả:
if (priorityCustomer) {
    feeVnd = 0L;
} else if (promotionEligible) {
    feeVnd = 0L;
} else {
    feeVnd = STANDARD_FEE_VND;
}

// Nếu việc đánh giá hai điều kiện chỉ là đọc dữ liệu thuần:
feeVnd = (priorityCustomer || promotionEligible)
        ? 0L
        : STANDARD_FEE_VND;
```

Phiên bản sau nêu quy tắc “đủ một trong hai điều kiện thì được miễn phí” mà không lặp lệnh gán. Khi một nhánh còn ghi log, gửi sự kiện hoặc cần ghi nhận **lý do** miễn phí, hai nhánh có thể mang ý nghĩa khác nhau và không được tự ý gộp.

## 3. Trong Java, đổi thứ tự điều kiện có thể đổi hành vi

Với biến Boolean thuần túy, `a && b` và `b && a` có cùng bảng chân trị. Nhưng với biểu thức Java thực tế, toán tử `&&` và `||` đánh giá từ trái qua phải và **dừng sớm** (*short-circuit*). Vì vậy, thứ tự còn ảnh hưởng đến ngoại lệ và tác dụng phụ.

### 3.1. Kiểm tra `null` trước khi truy cập

```java
boolean canNotify(User user) {
    return user != null && user.isActive();
}
```

Phiên bản sau **không tương đương**:

```java
boolean canNotify(User user) {
    return user.isActive() && user != null; // Có thể ném NullPointerException.
}
```

Trong bản đầu, nếu `user == null`, Java không gọi `user.isActive()`. Ở bản sau, lời gọi diễn ra trước khi kiểm tra `null`.

### 3.2. Không di chuyển lời gọi có tác dụng phụ một cách tùy tiện

```java
if (isEligible(order) && reserveInventory(order)) {
    confirm(order);
}
```

Nếu `reserveInventory(order)` thay đổi tồn kho, hoán đổi hai điều kiện sẽ khiến thao tác giữ hàng xảy ra **trước khi** xác minh điều kiện đủ. Gộp, tách hoặc di chuyển điều kiện chỉ an toàn khi đã hiểu các lời gọi và hợp đồng của chúng.

Việc tách thành các bước có thể làm rõ ý định:

```java
if (!isEligible(order)) {
    return;
}

boolean inventoryReserved = reserveInventory(order);
if (!inventoryReserved) {
    return;
}

confirm(order);
```

Hai phiên bản tương đương về **thứ tự gọi các phương thức đã nêu** khi `return` được phép theo hợp đồng của phương thức bao quanh và không có công việc cần chạy ở phía sau. Với mã thực tế, còn phải kiểm tra tác dụng phụ, cleanup, ngoại lệ và giá trị trả về.

### 3.3. Không đồng nhất `&&` với `&`

Với toán hạng kiểu `boolean`, `&` cũng tính toán phép AND nhưng **đánh giá cả hai vế**; `&&` có thể bỏ qua vế phải. Tương tự, `|` khác `||` về việc đánh giá đầy đủ. Nếu vế phải có khả năng ném lỗi hoặc thay đổi trạng thái, thay toán tử có thể đổi hành vi.

### 3.4. So sánh “số lượng ít nhất” ở giá trị biên

```java
if (quantity >= MINIMUM_QUANTITY) {
    // Hợp lệ ngay tại ngưỡng.
}
```

Viết lại thành `quantity > MINIMUM_QUANTITY` tuy ngắn tương đương về hình thức nhưng khác quy tắc ở đúng ngưỡng. Khi đơn giản hóa điều kiện, **trường hợp biên** phải được xác nhận bằng đặc tả và kiểm thử.

## 4. Giảm số cờ để loại bỏ trạng thái không hợp lệ

Giả sử một hồ sơ chỉ được ở đúng một trong ba trạng thái: **đang chờ**, **đã duyệt** hoặc **bị từ chối**.

Một thiết kế dễ gây mâu thuẫn:

```java
class ReviewRequest {
    boolean pending;
    boolean approved;
    boolean rejected;
}
```

Ba cờ độc lập cho phép tới `2^3 = 8` tổ hợp, trong khi đặc tả chỉ cho phép **ba trạng thái**. Năm tổ hợp còn lại không có nghĩa hoặc mâu thuẫn, ví dụ `approved == true` đồng thời `rejected == true`, hoặc cả ba cùng `false`.

| `pending` | `approved` | `rejected` | Theo đặc tả |
| :---: | :---: | :---: | --- |
| `true` | `false` | `false` | Đang chờ — hợp lệ |
| `false` | `true` | `false` | Đã duyệt — hợp lệ |
| `false` | `false` | `true` | Bị từ chối — hợp lệ |
| `false` | `false` | `false` | Không xác định — không hợp lệ |
| `true` | `true` | `false` | Hai trạng thái cùng lúc — không hợp lệ |
| `true` | `false` | `true` | Hai trạng thái cùng lúc — không hợp lệ |
| `false` | `true` | `true` | Hai trạng thái cùng lúc — không hợp lệ |
| `true` | `true` | `true` | Ba trạng thái cùng lúc — không hợp lệ |

Nếu các trạng thái thực sự loại trừ nhau, một `enum` diễn đạt miền giá trị chính xác hơn:

```java
enum ReviewStatus {
    PENDING,
    APPROVED,
    REJECTED
}

final class ReviewRequest {
    private ReviewStatus status = ReviewStatus.PENDING;

    boolean isApproved() {
        return status == ReviewStatus.APPROVED;
    }

    void approve() {
        if (status != ReviewStatus.PENDING) {
            throw new IllegalStateException("Only pending requests can be approved");
        }
        status = ReviewStatus.APPROVED;
    }
}
```

Giờ `isApproved()` được **suy ra** từ `status`, không được lưu như một cờ thứ hai. Phương thức `approve()` kiểm tra điều kiện chuyển trạng thái, tránh âm thầm duyệt lại một hồ sơ đã xử lý.

Lưu ý hai ranh giới:

- Trường tham chiếu `ReviewStatus` vẫn có thể là `null` nếu nhà phát triển cho phép gán `null` qua một API hoặc khi ánh xạ dữ liệu bên ngoài. Ví dụ trên chỉ giữ trường ở trạng thái hợp lệ thông qua các thao tác được trình bày; dữ liệu đầu vào/khôi phục cần kiểm tra riêng.
- Không nên thay nhiều cờ bằng một `enum` nếu chúng đại diện cho **những chiều độc lập**. Ví dụ “đã thanh toán” và “đã giao” có thể cần kết hợp với “đã hoàn tiền”; gom tất cả vào một enum sẽ tạo quá nhiều tổ hợp tên trạng thái hoặc làm mất thông tin.

### Tại sao ít trạng thái hơn giúp đơn giản hóa điều kiện?

Với ba cờ, trước khi xét `approved`, người đọc còn phải tự hỏi có thể có `approved && rejected` hay không. Với một giá trị `status` được kiểm soát, điều kiện `status == ReviewStatus.APPROVED` đã diễn đạt trọn vẹn quyết định. Ta giảm cả số điều kiện phòng vệ lẫn số kịch bản cần cân nhắc.

## 5. Không lưu riêng dữ liệu có thể suy ra an toàn

Một dạng dư thừa khác là lưu **kết quả tính toán** đồng thời với nguồn đầu vào:

```java
class PriceSummary {
    long subtotalVnd;
    long discountVnd;
    long payableVnd;    // Có thể không khớp với hai trường trên.
    boolean hasDiscount; // Có thể không khớp với discountVnd.
}
```

Nếu chỉ có một quy tắc `payableVnd = subtotalVnd - discountVnd`, hai trường cuối là dữ liệu dẫn xuất. Cập nhật `discountVnd` mà quên cập nhật `payableVnd` hoặc `hasDiscount` sẽ tạo ra trạng thái không nhất quán.

Một mô hình gọn hơn:

```java
public final class PriceSummary {
    private final long subtotalVnd;
    private final long discountVnd;

    public PriceSummary(long subtotalVnd, long discountVnd) {
        if (subtotalVnd < 0L || discountVnd < 0L
                || discountVnd > subtotalVnd) {
            throw new IllegalArgumentException("Invalid monetary values");
        }
        this.subtotalVnd = subtotalVnd;
        this.discountVnd = discountVnd;
    }

    public boolean hasDiscount() {
        return discountVnd > 0L;
    }

    public long payableVnd() {
        return subtotalVnd - discountVnd;
    }
}
```

Hợp đồng đầu vào cho phép tính tiền không âm và không tràn số tại phép trừ. Cả hai kết quả `hasDiscount()` và `payableVnd()` đều được suy ra từ một nguồn dữ liệu ổn định. Không có đường cập nhật riêng khiến chúng lệch nhau.

**Nhưng không phải lúc nào cũng nên tính lại.** Giá trị dẫn xuất có thể được lưu có chủ đích khi:

- Việc tính rất tốn kém và có bằng chứng hiệu năng cần cache.
- Cần một **ảnh chụp lịch sử**: giá trị hóa đơn tại thời điểm giao dịch phải được giữ nguyên dù quy tắc thuế hoặc bảng giá sau này thay đổi.
- Cần lưu một giá trị đã được hệ thống bên ngoài xác nhận độc lập, không chỉ là phép tính từ các trường hiện tại.
- Cần một cột tổng hợp phục vụ truy vấn nhưng có cơ chế đồng bộ, tái tạo và đối soát rõ.

Khi đó, giá trị lưu thêm không còn là “thừa” theo nghĩa thiết kế; nó có một **hợp đồng riêng**. Cần chỉ rõ nguồn sự thật, thời điểm cập nhật, quy tắc làm mới, và xử lý khi dữ liệu không khớp.

## 6. Ví dụ Java tổng hợp: chính sách cho phép xuất kho

Giả sử quy trình đơn hàng đơn giản của một ứng dụng bán hàng có các giai đoạn loại trừ nhau:

```text
CREATED -> PAID -> PACKED -> SHIPPED
          \            /
           -> CANCELLED
```

Sơ đồ chỉ mang tính gợi ý; chính sách hủy thực tế phải nói rõ giai đoạn nào được hủy và các tác động hoàn tiền. Với bài học này, **đơn chỉ được gửi đi khi ở trạng thái `PACKED`, địa chỉ đã được xác minh và tồn kho đã được giữ**. Quy trình giả định bảo đảm `PACKED` chỉ đạt được sau khi thanh toán thành công.

### 6.1. Thiết kế dùng nhiều cờ và điều kiện lặp

```java
boolean canShip(
        boolean paid,
        boolean packed,
        boolean shipped,
        boolean cancelled,
        boolean addressVerified,
        boolean inventoryReserved) {

    return paid && packed
            && !shipped && !cancelled
            && addressVerified && inventoryReserved;
}
```

Điều kiện về mặt Boolean không quá dài, nhưng bộ đầu vào cho phép những trạng thái vô nghĩa: vừa hủy vừa đã giao, đã đóng gói mà chưa trả tiền, hoặc đã giao nhưng chưa đóng gói. Muốn đảm bảo đúng, các nơi cập nhật cả sáu cờ phải phối hợp với nhau.

### 6.2. Thể hiện một giai đoạn nghiệp vụ bằng một giá trị

```java
import java.util.Objects;

public final class ShippingEligibility {
    public enum OrderStatus {
        CREATED,
        PAID,
        PACKED,
        SHIPPED,
        CANCELLED
    }

    public static final class OrderSnapshot {
        private final OrderStatus status;
        private final boolean addressVerified;
        private final boolean inventoryReserved;

        public OrderSnapshot(
                OrderStatus status,
                boolean addressVerified,
                boolean inventoryReserved) {
            this.status = Objects.requireNonNull(status, "status");
            this.addressVerified = addressVerified;
            this.inventoryReserved = inventoryReserved;
        }

        public OrderStatus status() {
            return status;
        }

        public boolean addressVerified() {
            return addressVerified;
        }

        public boolean inventoryReserved() {
            return inventoryReserved;
        }
    }

    public static boolean canShip(OrderSnapshot order) {
        Objects.requireNonNull(order, "order");
        return order.status() == OrderStatus.PACKED
                && order.addressVerified()
                && order.inventoryReserved();
    }
}
```

Đoạn mã trên vẫn giữ hai cờ `addressVerified` và `inventoryReserved` vì chúng mô tả **hai sự thật độc lập** với giai đoạn của đơn. Chúng có thể thay đổi theo quy tắc riêng và chưa chắc được suy ra chỉ từ `PACKED`. Ngược lại, những cờ `paid`, `packed`, `shipped`, `cancelled` cùng mô tả **một giai đoạn độc quyền** theo đặc tả đơn giản nên được thay bằng `OrderStatus`.

**Đây là một thay đổi mô hình dữ liệu, không chỉ đổi cú pháp.** Hai phiên bản chỉ được xem tương đương trên những trạng thái đầu vào hợp lệ đã được đặc tả. Khi chuyển từ mô hình cờ sang enum trong dự án thật, cần xác định:

1. Những tổ hợp cờ nào đang tồn tại trong dữ liệu cũ; xử lý giá trị mâu thuẫn hoặc thiếu thế nào?
2. Những luồng nào chuyển trạng thái, và ai được phép thực hiện chúng?
3. Những đặc điểm nào thực sự là các chiều độc lập, chẳng hạn hoàn tiền, giữ kho hoặc xác minh địa chỉ?
4. Cần chuyển đổi dữ liệu lưu trữ, giao diện API hoặc sự kiện tích hợp ra sao?

Không thể kết luận an toàn chỉ vì phương thức `canShip(...)` của phiên bản mới ngắn hơn.

### 6.3. Kiểm thử quy tắc và các giới hạn

Ví dụ JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class ShippingEligibilityTest {
    private static ShippingEligibility.OrderSnapshot snapshot(
            ShippingEligibility.OrderStatus status,
            boolean addressVerified,
            boolean inventoryReserved) {
        return new ShippingEligibility.OrderSnapshot(
                status, addressVerified, inventoryReserved);
    }

    @Test
    void packedOrderWithBothRequirementsMayShip() {
        assertTrue(ShippingEligibility.canShip(snapshot(
                ShippingEligibility.OrderStatus.PACKED, true, true)));
    }

    @Test
    void incompleteRequirementsPreventShipping() {
        assertFalse(ShippingEligibility.canShip(snapshot(
                ShippingEligibility.OrderStatus.PACKED, false, true)));
        assertFalse(ShippingEligibility.canShip(snapshot(
                ShippingEligibility.OrderStatus.PACKED, true, false)));
    }

    @Test
    void otherStagesCannotShip() {
        for (ShippingEligibility.OrderStatus status
                : ShippingEligibility.OrderStatus.values()) {
            if (status != ShippingEligibility.OrderStatus.PACKED) {
                assertFalse(ShippingEligibility.canShip(
                        snapshot(status, true, true)));
            }
        }
    }
}
```

Các kiểm thử xác minh **quy tắc quyết định**, không tự bảo đảm quy trình cập nhật trạng thái ở cơ sở dữ liệu là đúng. Nếu nghiệp vụ còn cần chống gửi trùng, kiểm soát đồng thời hoặc xử lý lỗi dịch vụ vận chuyển, phải kiểm thử thêm ở lớp thực hiện tác dụng phụ.

## 7. Đặt tên điều kiện giúp giảm tải nhận thức

Một biểu thức đơn giản về mặt toán học vẫn có thể khó hiểu khi chứa nhiều khái niệm nghiệp vụ:

```java
if (user != null && user.isActive()
        && (user.hasPremiumPlan() || user.isInTrial())
        && !user.isSuspended()) {
    showReport();
}
```

Khi quy tắc được dùng ở nhiều nơi hoặc cần được giải thích với nghiệp vụ, một hàm có tên rõ có thể hữu ích:

```java
boolean canViewReport(User user) {
    return user != null
            && user.isActive()
            && !user.isSuspended()
            && (user.hasPremiumPlan() || user.isInTrial());
}
```

Tên `canViewReport` diễn đạt ý định, còn phần cài đặt giữ các điều kiện ở cùng một chỗ. Tuy nhiên, khi chuyển từ biểu thức đầu sang hàm, phải xem các lời gọi `isActive()`, `hasPremiumPlan()`, `isInTrial()`, `isSuspended()` có thuần túy và ổn định hay không: thứ tự hai điều kiện cuối đã thay đổi. Nếu chúng có tác dụng phụ, có thể ném ngoại lệ hoặc đọc trạng thái đang biến động, nên giữ thứ tự ban đầu hoặc phân tích hợp đồng trước khi hoán đổi.

Đặt tên không có nghĩa phải tạo hàm mới cho mỗi phép so sánh. Một điều kiện như `quantity > 0` có thể dễ đọc ngay tại nơi dùng. Nên trích thành tên riêng khi người đọc được hưởng lợi từ **một khái niệm nghiệp vụ thực sự**, không chỉ để giấu cú pháp.

## 8. Giảm trạng thái thay đổi bên trong phương thức

Không chỉ các trường dữ liệu lâu dài mới gây phức tạp. Một biến cục bộ bị gán lại qua nhiều nhánh cũng buộc người đọc theo dõi lịch sử giá trị:

```java
long shippingFeeVnd = 30_000L;
if (express) {
    shippingFeeVnd = 50_000L;
}
if (!express && payableVnd >= 500_000L) {
    shippingFeeVnd = 0L;
}
```

Nếu hai nhánh là những lựa chọn loại trừ nhau theo đặc tả, có thể viết:

```java
final long shippingFeeVnd;
if (express) {
    shippingFeeVnd = 50_000L;
} else if (payableVnd >= 500_000L) {
    shippingFeeVnd = 0L;
} else {
    shippingFeeVnd = 30_000L;
}
```

Giờ mỗi đường đi chỉ gán `shippingFeeVnd` một lần. Từ khóa `final` ngăn gán lại biến sau khi đã khởi tạo; nó không tự làm đối tượng được tham chiếu trở nên bất biến.

Khi quy tắc này được sử dụng nhiều lần, việc đưa vào `calculateShippingFeeVnd(payableVnd, express)` còn giúp tập trung chính sách và kiểm thử riêng. Cần tránh tạo state tạm chỉ để truyền tiếp giữa nhiều phương thức nếu một kết quả trực tiếp là đủ.

### State machine hay hàm thuần?

Nếu phương thức chỉ quyết định một giá trị từ đầu vào, **hàm thuần** thường là lựa chọn đơn giản: không cần cờ nội bộ, ít tác dụng phụ và dễ kiểm thử. Nếu nghiệp vụ thực sự có vòng đời hoặc chuyển trạng thái, **state machine** với các chuyển đổi hợp lệ rõ ràng có thể tốt hơn nhiều cờ độc lập.

Đừng ép mọi nghiệp vụ vào một hàm thuần, cũng đừng tạo state machine cho phép tính không có vòng đời. Chọn mô hình bám sát các sự thật mà hệ thống cần lưu và các quyết định mà hệ thống phải thực hiện.

## 9. Phân biệt đơn giản hóa hợp lệ với thay đổi hành vi

Khi refactor, cần kiểm tra ít nhất bốn lớp hành vi:

| Phần cần giữ | Sai lầm dễ gặp |
| --- | --- |
| **Giá trị trả về** | Đổi ngưỡng `>=` thành `>`, gộp sai nhóm điều kiện |
| **Ngoại lệ** | Đổi thứ tự kiểm tra khiến `NullPointerException` xuất hiện trước lỗi nghiệp vụ |
| **Tác dụng phụ** | Hoán đổi hai lời gọi, đổi số lần hoặc điều kiện gọi dịch vụ |
| **Trạng thái quan sát được** | Bỏ cờ được hệ thống khác đọc, làm lệch dữ liệu lưu hoặc thay đổi chuyển trạng thái hợp lệ |

Một biểu thức Boolean tương đương không bảo đảm cả phương thức tương đương nếu hai vế gọi những hàm có tác dụng phụ. Một mô hình ít trường hơn không bảo đảm tương thích với dữ liệu, API và sự kiện hiện tại. Hãy phân biệt **refactor giữ hành vi** với **thay đổi nghiệp vụ hoặc chuyển đổi mô hình dữ liệu** để thiết kế kiểm tra phù hợp.

### Những kiểm tra thực dụng

1. Viết lại quy tắc bằng lời, xác định đầu vào hợp lệ và bất biến.
2. Xác định điều kiện nào là Boolean thuần, điều kiện nào đọc dữ liệu biến động hoặc có thể ném ngoại lệ.
3. Tạo bảng trường hợp quan trọng, gồm ngưỡng biên, `null`, trạng thái loại trừ và dữ liệu bất thường.
4. Đối chiếu kết quả, ngoại lệ, thứ tự/số lần tác dụng phụ trước và sau thay đổi.
5. Với thay đổi mô hình trạng thái, kiểm tra đường chuyển đổi dữ liệu cũ và cách ngăn tổ hợp không hợp lệ về sau.
6. Chỉ kết luận cải thiện khi **mã dễ giải thích hơn và bằng chứng xác nhận hành vi cần giữ**.

Nếu cần một bảng chân trị cho ba biến Boolean, tối đa tám tổ hợp vẫn có thể kiểm tra bằng tay. Với nhiều biến hơn, nên ưu tiên kiểm thử các tổ hợp có ý nghĩa, ranh giới và bất biến, kết hợp các kỹ thuật kiểm thử phù hợp thay vì dựa hoàn toàn vào việc liệt kê mọi tổ hợp.

## 10. Những ngộ nhận thường gặp

### “Ít `if` hơn nghĩa là ít phức tạp hơn”

Một biểu thức ba ngôi dài hoặc chuỗi toán tử lồng nhau có thể khó đọc hơn vài nhánh có tên rõ. Ít nhánh có thể giúp giảm một phần độ phức tạp luồng điều khiển, nhưng **độ khó hiểu** còn đến từ trạng thái, tác dụng phụ, tên gọi và số giả định cần nhớ.

### “Gộp mọi điều kiện thành một dòng là tối ưu”

Độ dài không phải mục tiêu. Biểu thức cần thể hiện đúng các quy tắc; với nhiều điều kiện độc lập, dùng biến có tên hoặc phương thức nghiệp vụ có thể giảm tải nhận thức tốt hơn.

### “Một `enum` luôn thay thế được nhiều cờ”

Chỉ nên gộp các trạng thái **loại trừ nhau**. Nếu các cờ là những chiều độc lập, một enum tổ hợp có thể làm mô hình phình to và che mất ý nghĩa.

### “Giá trị tính được thì không bao giờ nên lưu”

Một ảnh chụp giá trị tại thời điểm giao dịch hoặc một cache được quản lý có thể là dữ liệu cần thiết. Câu hỏi là liệu giá trị đó có hợp đồng riêng và cơ chế nhất quán đáng tin hay không.

### “Biểu thức Boolean tương đương thì cách viết luôn tương đương”

Trong Java, thứ tự đánh giá, short-circuit, unboxing, ngoại lệ và tác dụng phụ đều có thể tạo khác biệt. Chứng minh Boolean là một phần, không thay thế đánh giá hành vi chương trình.

### “Trạng thái không hợp lệ sẽ không bao giờ xuất hiện”

Khi dữ liệu đến từ API, cơ sở dữ liệu hoặc sự kiện ngoài hệ thống, phải xác minh điều kiện vào. Sử dụng enum hoặc constructor kiểm tra dữ liệu giúp giảm lỗi, nhưng không tự sửa được dữ liệu lịch sử, lỗi tích hợp hay những đường cập nhật bỏ qua bất biến.

## 11. Checklist dành cho người review

| Câu hỏi | Dấu hiệu cần xem lại |
| --- | --- |
| Điều kiện có thể phát biểu thành một câu nghiệp vụ không? | Nhiều phủ định và giá trị “ma thuật” |
| Có so sánh `boolean == true/false` hoặc nhánh trả cùng kết quả không? | Phép so sánh hoặc nhánh có thể dư thừa |
| Có đổi thứ tự những lời gọi có thể ném lỗi hoặc tạo tác dụng phụ không? | Refactor có thể làm đổi hành vi |
| Có kiểm tra `null` trước khi truy cập dữ liệu không? | Có nguy cơ `NullPointerException` |
| Nhiều cờ có đang biểu diễn một trạng thái loại trừ nhau không? | Tổ hợp không hợp lệ có thể tồn tại |
| Có trường nào chỉ là kết quả tính từ các trường khác không? | Phải đồng bộ cùng một sự thật ở nhiều nơi |
| Nếu lưu giá trị dẫn xuất, hợp đồng và cách cập nhật của nó đã rõ chưa? | Cache hoặc ảnh chụp có thể sai lệch |
| Các biến cục bộ có bị gán lại qua nhiều nhánh khó theo dõi không? | Người đọc phải nhớ lịch sử trạng thái |
| Khi dữ liệu cũ hoặc đầu vào bất thường xuất hiện, mô hình mới xử lý ra sao? | Tích hợp và migration có thể hỏng |
| Đã kiểm tra trường hợp biên, ngoại lệ và tác dụng phụ chưa? | Bài kiểm thử chỉ bao phủ kết quả “đẹp” |

## 12. Bài tập áp dụng

Một tài khoản có các trường:

```java
class Account {
    boolean pending;
    boolean active;
    boolean suspended;
    boolean canTransfer;
    long balanceVnd;
}
```

Quy tắc giả định: tài khoản chỉ ở một trong ba trạng thái **đang chờ**, **hoạt động**, **bị đình chỉ**. Chỉ tài khoản đang hoạt động mới được chuyển tiền, và mỗi giao dịch chuyển cần được kiểm tra thêm điều kiện số dư đủ tại thời điểm thực hiện.

Hãy giải quyết:

1. Liệt kê những tổ hợp ba cờ trạng thái không hợp lệ. Có bao nhiêu tổ hợp có thể biểu diễn, và bao nhiêu tổ hợp nghiệp vụ chấp nhận?
2. Đề xuất `AccountStatus` và thay ba cờ loại trừ nhau bằng một trường `status`. Khi đó, `canTransfer` có nên lưu độc lập không? Điều gì xảy ra nếu quyền chuyển tiền còn phụ thuộc một cờ tuân thủ khác ngoài `status`?
3. Viết phương thức trả về điều kiện **được phép bắt đầu kiểm tra chuyển tiền**, sau đó tách riêng bước xác minh số dư. Tránh hiểu nhầm kết quả “được phép” với “giao dịch đã thành công”.
4. Viết ca kiểm thử khi tài khoản ở `PENDING`, `ACTIVE`, `SUSPENDED` và số dư ngay dưới/đúng bằng số tiền cần chuyển.
5. Giả sử hệ thống cũ đã lưu hai cờ `active == true` và `suspended == true`. Mô tả cách phát hiện và xử lý dữ liệu mâu thuẫn khi chuyển đổi mô hình; không âm thầm chọn một trạng thái nếu chưa có quy tắc nghiệp vụ.
6. Giải thích vì sao việc đọc số dư rồi chuyển tiền qua hai thao tác độc lập vẫn có thể gặp lỗi đồng thời. Cần thêm biện pháp gì để bảo đảm tiền không bị trừ vượt số dư?

**Gợi ý:** sự chuyển đổi từ nhiều cờ sang một trạng thái có ý nghĩa làm giảm số tổ hợp vô lý, nhưng giao dịch tiền còn phụ thuộc vào kiểm tra quyền, dữ liệu hiện tại và cập nhật nguyên tử. Giảm độ phức tạp mô hình là điều kiện giúp suy luận rõ hơn; nó không tự cung cấp an toàn giao dịch.

## Ghi nhớ

Đơn giản hóa điều kiện giúp người đọc nhìn thấy **quy tắc thực sự**, còn loại bỏ trạng thái không cần thiết giúp giảm những **tổ hợp phải duy trì và kiểm thử**. Hãy gộp các điều kiện tương đương khi giữ nguyên ngữ nghĩa Java; dùng một kiểu trạng thái cho những tình huống thật sự loại trừ nhau; tính từ nguồn sự thật khi không cần lưu kết quả dẫn xuất; và bảo toàn hành vi, ngoại lệ, tác dụng phụ khi refactor. Một thiết kế tốt không chỉ ngắn hơn mà còn làm cho trạng thái sai khó biểu diễn và quyết định đúng dễ kiểm chứng.
