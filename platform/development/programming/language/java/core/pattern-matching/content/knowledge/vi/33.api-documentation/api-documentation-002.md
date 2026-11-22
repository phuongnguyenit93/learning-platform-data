# Ghi rõ invariant giúp thiết kế exhaustive switch (Java 21+)

## 1. Hiểu đúng mối quan hệ giữa invariant và exhaustive switch

Khi dùng **pattern matching trong `switch`**, một thiết kế API tốt không chỉ có các nhánh `case` đầy đủ; người đọc còn phải hiểu **vì sao danh sách nhánh là đầy đủ** và **vì sao dữ liệu trong nhánh có thể sử dụng an toàn**.

Hai loại bảo đảm cần được phân biệt:

1. **Bảo đảm về tập kiểu:** một `sealed interface` hoặc `sealed class` xác định tập subtype được phép. Java 21 có thể dùng cấu trúc kiểu này để kiểm tra một `switch expression` có **exhaustive** hay không: mọi giá trị selector khác `null` thuộc những subtype được phép đều có một đường xử lý.
2. **Invariant dữ liệu của domain:** constructor/factory/validation bảo đảm trạng thái nội bộ của đối tượng hợp lệ. Ví dụ, “đối tượng `Shipped` luôn có `trackingCode` không null, không trắng”. Invariant này giúp nhánh đã chọn có thể gọi `trackingCode.toUpperCase(...)` mà không bị `NullPointerException` trong các đường tạo object hợp lệ.

**Điểm mấu chốt:** một invariant nghiệp vụ không tự làm compiler coi một `case ... when ...` là exhaustive. Compiler dựa vào **hệ thống kiểu và các quy tắc bao phủ của pattern**; nó không chứng minh các điều kiện nghiệp vụ tùy ý mà constructor đã kiểm tra.

Vì vậy, “ghi rõ invariant giúp exhaustive switch” nên hiểu chính xác là:

- **Ghi rõ tập variant đóng** để người đọc thấy cơ sở của kiểm tra exhaustive.
- **Ghi rõ invariant của từng variant** để các nhánh có thể dùng dữ liệu an toàn.
- **Ghi rõ chính sách `null` và guard** để không gán nhầm bảo đảm của compiler cho một quy tắc domain.
- **Ghi rõ cam kết tiến hóa API** vì thêm subtype mới có thể làm các `switch` của phía sử dụng không còn exhaustive.

Bài này trình bày cách thiết kế, ghi Javadoc, viết comment đúng chỗ, kiểm thử dương/âm và duy trì contract trên **Java 21+**.

## 2. Một mô hình ví dụ: trạng thái đơn hàng là tập variant đóng

Giả sử domain có bốn trạng thái đơn hàng:

| Variant | Payload riêng | Invariant cần bảo vệ |
| --- | --- | --- |
| `Draft` | `orderId` | Mã đơn hàng không null và không trắng |
| `Paid` | `orderId`, `amountCents` | Mã hợp lệ; tiền thanh toán dương |
| `Shipped` | `orderId`, `trackingCode` | Mã đơn hàng và mã vận đơn không null/không trắng |
| `Cancelled` | `orderId`, `reason` | Mã đơn hàng và lý do hủy không null/không trắng |

Một thiết kế cũ có thể đặt tất cả thông tin trong một record:

~~~java
enum Status { DRAFT, PAID, SHIPPED, CANCELLED }

record OrderData(
        Status status,
        String orderId,
        long amountCents,
        String trackingCode,
        String cancelReason) {}
~~~

Đây là **mô hình minh họa vấn đề**, không có validation. Nó cho phép tạo `OrderData(SHIPPED, "O1", 0, null, null)`, tức trạng thái đã gửi nhưng thiếu mã vận đơn; hoặc trạng thái `DRAFT` lại có lý do hủy. Rất nhiều tổ hợp field không có ý nghĩa domain.

Thay vào đó, mô hình hóa bốn variant riêng:

~~~java
sealed interface OrderState permits Draft, Paid, Shipped, Cancelled {}

record Draft(String orderId) implements OrderState {}
record Paid(String orderId, long amountCents) implements OrderState {}
record Shipped(String orderId, String trackingCode) implements OrderState {}
record Cancelled(String orderId, String reason) implements OrderState {}
~~~

Bốn record này chỉ là **khai báo kiểu minh họa**; phần tiếp theo bổ sung compact constructor để ngăn dữ liệu sai.

`sealed` mô tả **tập subtype trực tiếp được phép**. `record` là kiểu `final` theo mặc định, nên trong ví dụ này mỗi nhánh là một kiểu kết thúc; không có subclass mới được thêm tùy ý dưới các record đó.

Điều này giúp compiler đánh giá một `switch` có xử lý đủ bốn loại `OrderState`. Tuy nhiên, **`sealed` không tự kiểm tra giá trị các component**. Nó không chứng minh rằng `amountCents > 0` hoặc `trackingCode != null`. Hai tầng bảo đảm phải được diễn đạt riêng trong tài liệu API.

## 3. Ghi contract ở nơi khai báo invariant

Nếu định để các nhánh pattern dựa trên invariant, trước tiên **phải thực thi invariant**, không chỉ viết comment khẳng định nó luôn đúng.

~~~java
static String requireText(String text, String field) {
    if (text == null || text.isBlank()) {
        throw new IllegalArgumentException(field);
    }
    return text;
}

record Draft(String orderId) implements OrderState {
    Draft {
        requireText(orderId, "orderId");
    }
}

record Paid(String orderId, long amountCents) implements OrderState {
    Paid {
        requireText(orderId, "orderId");
        if (amountCents <= 0) {
            throw new IllegalArgumentException("amountCents");
        }
    }
}

record Shipped(String orderId, String trackingCode) implements OrderState {
    Shipped {
        requireText(orderId, "orderId");
        requireText(trackingCode, "trackingCode");
    }
}

record Cancelled(String orderId, String reason) implements OrderState {
    Cancelled {
        requireText(orderId, "orderId");
        requireText(reason, "reason");
    }
}
~~~

Đây là **các thành phần minh họa cùng một phạm vi khai báo**, chưa phải một tệp độc lập: chúng cần `OrderState` và `requireText` đặt chung đúng vị trí. Mục 9 có toàn bộ chương trình chạy được.

Các compact constructor kiểm tra tham số trước khi các component được gán. Nếu input vi phạm quy tắc, constructor ném `IllegalArgumentException` ngay tại điểm tạo object.

Ví dụ:

~~~java
new Paid("O1", 1500);             // Hợp lệ
new Shipped("O1", "trk-9");       // Hợp lệ

new Paid("O1", 0);                // IllegalArgumentException
new Shipped("O1", null);         // IllegalArgumentException
new Cancelled("O1", "  ");        // IllegalArgumentException
~~~

**Bản thân Java record không có kiểu non-null mặc định.** `String trackingCode` vẫn cho phép null nếu không có validation. Vì vậy comment hoặc Javadoc về invariant phải trỏ tới **mã thực thi bảo đảm nó**.

Nếu record chứa `List`, mảng hay một đối tượng mutable, record chỉ bất biến **nông** (*shallow immutability*). Một invariant về nội dung collection cần defensive copy hoặc thiết kế immutable phù hợp. Ví dụ bài học dùng `String` và kiểu nguyên thủy, không có mutable component.

## 4. Exhaustive switch: tính đầy đủ xuất phát từ tập subtype

Với `OrderState` đã được khai báo là sealed và bốn subtype kết thúc, một `switch expression` có thể xử lý toàn bộ chúng:

~~~java
static String summary(OrderState state) {
    java.util.Objects.requireNonNull(state, "state");

    return switch (state) {
        case Draft(var id) -> "draft:" + id;
        case Paid(var id, var cents) -> "paid:" + id + ":" + cents;

        // Invariant: trackingCode trong Shipped khác null và không trắng.
        // Được kiểm tra bởi compact constructor của Shipped.
        case Shipped(var id, var tracking) ->
                "shipped:" + id + ":"
                + tracking.toUpperCase(java.util.Locale.ROOT);

        case Cancelled(var id, var reason) ->
                "cancelled:" + id + ":" + reason;
    };
}
~~~

Đây là **phương thức minh họa**, nằm trong lớp có các record ở mục 3. Có bản hoàn chỉnh tại mục 9.

Không có `default`, nhưng compiler vẫn chấp nhận vì các nhánh bao phủ mọi subtype được phép của `OrderState` trong cấu trúc ví dụ.

Lưu ý hai lớp bảo đảm trong mã:

- **Exhaustiveness:** compiler suy luận từ `OrderState permits Draft, Paid, Shipped, Cancelled`, các subtype và các pattern tương ứng.
- **An toàn dữ liệu:** lời gọi `tracking.toUpperCase(...)` dựa vào contract “`Shipped.trackingCode` không null” mà constructor thực thi. Compiler **không tự biết** rằng mọi chuỗi `tracking` trong nhánh này đã được validate.

Vì `case Shipped(var id, var tracking)` dùng các component pattern không có guard, nó bao phủ các instance `Shipped` theo quy tắc bao phủ của record pattern. Việc không có `default` giúp phát hiện khi tập subtype thay đổi lúc biên dịch lại.

**Không nên viết một comment như “exhaustive nhờ trackingCode luôn hợp lệ”.** Nhận định đó nhầm lẫn hai lý do. Comment đúng hơn:

> `switch` exhaustive vì `OrderState` là sealed với bốn subtype được phép; nhánh `Shipped` an toàn khi sử dụng `trackingCode` nhờ validation trong constructor.

## 5. Guard không tự trở thành exhaustive nhờ invariant

Đây là điểm quan trọng nhất khi tài liệu nói tới invariant và `switch`.

Giả sử constructor của `Shipped` bảo đảm mã vận đơn **luôn bắt đầu bằng chữ `"X"`**. Một người có thể nghĩ nhánh sau đã bao phủ toàn bộ `Shipped`:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH nếu không còn case Shipped khác hoặc default.
return switch (state) {
    case Shipped(var tracking) when tracking.startsWith("X") -> "shipping";
    case Closed c -> "closed";
};
~~~

Để ví dụ rõ và tránh nhầm số component, đây là **kiểu mô hình giả định khác với `OrderState`**:

~~~java
sealed interface State permits Shipped, Closed {}

record Shipped(String tracking) implements State {
    Shipped {
        if (tracking == null || !tracking.startsWith("X")) {
            throw new IllegalArgumentException("tracking");
        }
    }
}

record Closed() implements State {}
~~~

Khi đặt đoạn `return switch (state) {...}` vào một phương thức nhận `State state` của cùng mô hình, Java 21 **báo không exhaustive**. Lý do: compiler không coi điều kiện `when tracking.startsWith("X")` là phép bao phủ vô điều kiện, kể cả khi constructor đã kiểm tra tiền tố `"X"`.

**Cách sửa để compiler có thể xác nhận đầy đủ:**

~~~java
static String label(State state) {
    return switch (state) {
        case Shipped(var tracking) when tracking.startsWith("X") ->
                "shipping-priority";
        case Shipped(var tracking) -> "shipping-other";
        case Closed c -> "closed";
    };
}
~~~

Đây là đoạn minh họa cùng mô hình `State` ở trên; **không** phải một phần của chương trình chính ở mục 9. Nhánh `Shipped` thứ hai không có guard nên bao phủ phần còn lại của subtype, kể cả trường hợp mà guard trước không thỏa. Nếu invariant đúng trong các đường tạo object hợp lệ, nhánh dự phòng ấy có thể ít khi được chạy, nhưng nó **vẫn cần thiết cho bảo đảm exhaustive trong source code**.

Đừng khắc phục bằng cách thêm `default` một cách máy móc chỉ để hết lỗi. `default` có thể làm compiler không còn nhắc bạn cập nhật xử lý khi thêm subtype mới.

### Vì sao điều này có ích cho tài liệu API?

Javadoc nên mô tả cả hai điều:

1. **Invariant của `Shipped`:** constructor chỉ chấp nhận mã hợp lệ.
2. **Giới hạn của kiểm tra compiler:** những điều kiện runtime trong `when` không được suy ra từ Javadoc hoặc implementation của constructor.

Tài liệu giúp lập trình viên **không suy luận sai** về exhaustiveness và biết khi nào phải dùng nhánh không guarded hoặc tổ chức lại mô hình kiểu.

## 6. Thiết kế guard kết hợp nhánh dự phòng trên mô hình thật

Một cách xử lý có guard là phân loại phương thức vận chuyển theo tiền tố tracking code:

~~~java
static String carrier(OrderState state) {
    java.util.Objects.requireNonNull(state, "state");

    return switch (state) {
        case Shipped(var id, var tracking)
                when tracking.startsWith("X") -> "priority-shipping";

        case Shipped(var id, var tracking) -> "standard-shipping";

        case Draft d -> "not-shipped";
        case Paid p -> "not-shipped";
        case Cancelled c -> "not-shipped";
    };
}
~~~

Đây là phương thức minh họa cùng mô hình `OrderState`, được đưa nguyên vẹn vào lớp ở mục 9.

Nhánh guarded `Shipped ... when tracking.startsWith("X")` chỉ áp dụng cho một **tập con** của `Shipped`. Nhánh `Shipped(...)` không guard ở sau bảo đảm các `Shipped` còn lại có đường xử lý.

Thứ tự quan trọng: nếu chuyển nhánh `Shipped(...)` rộng hơn lên trước, nhánh có `when` phía sau có thể bị compiler từ chối do **dominated**. Khi viết tài liệu bảo trì, cần nêu rõ vì sao phải giữ nhánh cụ thể trước, tổng quát sau.

Trong ví dụ, `trackingCode` chỉ được yêu cầu không trắng chứ **không** bắt buộc một tiền tố nhất định. Do đó cả hai nhánh `Shipped` thật sự có thể xảy ra:

- `Shipped("O1", "X-7")` → `"priority-shipping"`.
- `Shipped("O2", "trk-9")` → `"standard-shipping"`.

Điều này khác với mô hình `State` ở mục 5, nơi constructor giả định chỉ cho phép mã bắt đầu bằng `"X"`. Hai mô hình cố ý có invariant khác nhau, không được trộn kết luận của chúng.

## 7. Ghi rõ chính sách null: exhaustive không có nghĩa bắt mọi null

Một `switch` exhaustive trên `sealed interface` có thể bao phủ **toàn bộ các subtype hợp lệ khác null** mà vẫn không xử lý selector `null` theo ý nghĩa nghiệp vụ.

Phương thức `summary` ở mục 4 dùng:

~~~java
java.util.Objects.requireNonNull(state, "state");
~~~

Nghĩa là API **từ chối null tường minh**, ném `NullPointerException` tại biên của phương thức. Đây là một hợp đồng có chủ đích.

Nếu API phải chấp nhận null như một giá trị “chưa có trạng thái”, có thể viết:

~~~java
static String nullableSummary(OrderState state) {
    return switch (state) {
        case null -> "missing-state";
        case Draft d -> summary(d);
        case Paid p -> summary(p);
        case Shipped s -> summary(s);
        case Cancelled c -> summary(c);
    };
}
~~~

`case null` xử lý selector null. Các nhánh còn lại bao phủ bốn subtype đóng. `default` trong pattern switch Java 21 **không tự đại diện cho null**, nên cần thiết kế riêng.

Tài liệu API nên trả lời:

- `null` là **lỗi gọi API** hay một trạng thái nghiệp vụ hợp lệ?
- Nếu từ chối, ném ngoại lệ nào và ở đâu?
- Nếu chấp nhận, `case null` mang ý nghĩa gì đối với người dùng?

Không nên viết “mọi trường hợp đã được cover” mà bỏ qua hợp đồng null. **Exhaustive về kiểu** và **xử lý null** là hai câu hỏi khác nhau.

### Cảnh báo về null trong record component

Một biến record component như `var tracking` có thể nhận `null` nếu constructor không bảo vệ. Ngay cả mẫu con kiểu `String tracking`, khi là **unconditional** đối với component tĩnh `String`, vẫn có thể khớp giá trị null ở Java 21.

Vì vậy, record pattern **không thay thế validation**. Để gọi `tracking.toUpperCase(...)` an toàn, mã cần một invariant đã được thực thi hoặc guard kiểm tra null tại chỗ.

## 8. Javadoc và comment: ghi gì ở đâu?

### 8.1. Javadoc ở sealed interface: công bố danh sách biến thể

Một mô tả hữu ích:

~~~java
/**
 * Trạng thái đơn hàng hợp lệ được mô hình bằng tập subtype đóng:
 * Draft, Paid, Shipped và Cancelled.
 *
 * Các phương thức xử lý OrderState nên dùng exhaustive switch
 * không có default khi cần được compiler nhắc cập nhật lúc thêm variant.
 *
 * Selector null không phải một OrderState hợp lệ;
 * mỗi API quyết định rõ sẽ từ chối hay xử lý null.
 */
sealed interface OrderState permits Draft, Paid, Shipped, Cancelled {}
~~~

Đây là **minh họa về kiểu tài liệu API**. Nơi khai báo thật phải kết hợp với các record cùng package/module đúng quy tắc của `sealed`.

Việc liệt kê các variant ở Javadoc giúp người dùng API hiểu **tập trạng thái**. Tuy nhiên, Javadoc là tài liệu; danh sách kiểu được compiler kiểm tra nằm ở **`permits` và định nghĩa subtype**. Nếu chỉ sửa Javadoc mà không sửa `permits`, tập kiểu không thay đổi.

### 8.2. Javadoc ở record: phát biểu invariant như hợp đồng

Ví dụ:

~~~java
/**
 * Đơn hàng đã được giao cho bên vận chuyển.
 *
 * @param orderId mã đơn hàng, khác null và không trắng
 * @param trackingCode mã vận đơn, khác null và không trắng
 * @throws IllegalArgumentException nếu thành phần không hợp lệ
 */
record Shipped(String orderId, String trackingCode) implements OrderState {
    Shipped {
        requireText(orderId, "orderId");
        requireText(trackingCode, "trackingCode");
    }
}
~~~

Đây là đoạn minh họa; `requireText` cần được khai báo trong phạm vi chứa record. Khi thiết kế API công khai, mô tả kiểu giá trị được phép và ngoại lệ cần được gắn với API constructor/thành phần phù hợp theo cách Javadoc dự án sử dụng.

Ghi chú ngắn ở nơi xử lý:

~~~java
// Shipped constructor bảo đảm trackingCode != null và !isBlank().
case Shipped(var id, var tracking) ->
        tracking.toUpperCase(java.util.Locale.ROOT);
~~~

Nó giải thích một **giả định không hiển nhiên**: vì sao dereference `tracking` không cần guard thêm.

### 8.3. Tránh những comment gây hiểu nhầm

**Comment yếu:**

~~~java
// Đoạn này switch đầy đủ vì dữ liệu luôn đúng.
~~~

Sai về nguyên nhân: dữ liệu đúng không làm một nhánh `when` trở thành exhaustive.

**Comment chính xác hơn:**

~~~java
// Exhaustive: OrderState là sealed, bốn record final đều có case.
// Safe dereference: Shipped constructor từ chối trackingCode null/trắng.
// Nếu sửa permits hoặc constructor, phải kiểm tra lại switch và test.
~~~

Ở nơi người đọc dễ thấy, comment nên giải thích **mối phụ thuộc giữa mô hình và đường xử lý**, không lặp lại cú pháp mà compiler đã thể hiện rõ.

### 8.4. Khi nào không cần comment?

Nếu một hàm nhỏ đã dùng `Objects.requireNonNull` và mọi nhánh đơn giản, không có giả định nghiệp vụ ẩn, thêm comment ở mỗi `case` có thể làm rối. Ưu tiên:

- Hợp đồng đầy đủ ở **khai báo API/Javadoc**.
- Comment ngắn tại **điểm phụ thuộc vào invariant liên field hoặc điều kiện ngầm**.
- Test xác nhận điều kiện được thực thi; không xem comment là cơ chế bảo vệ.

## 9. Chương trình Java 21 hoàn chỉnh với 21 ca kiểm thử

Tạo tệp **`ExhaustiveInvariantDemo.java`** và chép đúng toàn bộ chương trình:

~~~java
public class ExhaustiveInvariantDemo {
    sealed interface OrderState permits Draft, Paid, Shipped, Cancelled {}

    record Draft(String orderId) implements OrderState {
        Draft { requireText(orderId, "orderId"); }
    }

    record Paid(String orderId, long amountCents) implements OrderState {
        Paid {
            requireText(orderId, "orderId");
            if (amountCents <= 0) {
                throw new IllegalArgumentException("amountCents");
            }
        }
    }

    record Shipped(String orderId, String trackingCode) implements OrderState {
        Shipped {
            requireText(orderId, "orderId");
            requireText(trackingCode, "trackingCode");
        }
    }

    record Cancelled(String orderId, String reason) implements OrderState {
        Cancelled {
            requireText(orderId, "orderId");
            requireText(reason, "reason");
        }
    }

    static String requireText(String text, String field) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException(field);
        }
        return text;
    }

    static String summary(OrderState state) {
        java.util.Objects.requireNonNull(state, "state");
        return switch (state) {
            case Draft(var id) -> "draft:" + id;
            case Paid(var id, var cents) -> "paid:" + id + ":" + cents;
            // Invariant: Shipped.trackingCode is non-null and non-blank.
            // Enforced in Shipped's compact constructor.
            case Shipped(var id, var tracking) ->
                    "shipped:" + id + ":"
                    + tracking.toUpperCase(java.util.Locale.ROOT);
            case Cancelled(var id, var reason) ->
                    "cancelled:" + id + ":" + reason;
        };
    }

    static String carrier(OrderState state) {
        java.util.Objects.requireNonNull(state, "state");
        return switch (state) {
            case Shipped(var id, var tracking)
                    when tracking.startsWith("X") -> "priority-shipping";
            case Shipped(var id, var tracking) -> "standard-shipping";
            case Draft d -> "not-shipped";
            case Paid p -> "not-shipped";
            case Cancelled c -> "not-shipped";
        };
    }

    static String nullableSummary(OrderState state) {
        return switch (state) {
            case null -> "missing-state";
            case Draft d -> summary(d);
            case Paid p -> summary(p);
            case Shipped s -> summary(s);
            case Cancelled c -> summary(c);
        };
    }

    private static int passed = 0;

    static void check(String name, String got, String expected) {
        if (!java.util.Objects.equals(got, expected)) {
            throw new AssertionError(
                    name + ": expected " + expected + ", got " + got);
        }
        ++passed;
        System.out.println("PASS " + name + " -> " + got);
    }

    static void expectInvalid(String name, Runnable attempt) {
        try {
            attempt.run();
            throw new AssertionError(
                    "Expected IllegalArgumentException: " + name);
        } catch (IllegalArgumentException expected) {
            ++passed;
            System.out.println("PASS " + name);
        }
    }

    static void expectNull(String name, Runnable attempt) {
        try {
            attempt.run();
            throw new AssertionError(
                    "Expected NullPointerException: " + name);
        } catch (NullPointerException expected) {
            ++passed;
            System.out.println("PASS " + name);
        }
    }

    public static void main(String[] args) {
        OrderState draft = new Draft("O1");
        OrderState paid = new Paid("O1", 1500);
        OrderState shippedX = new Shipped("O1", "X-7");
        OrderState shippedStd = new Shipped("O2", "trk-9");
        OrderState cancelled = new Cancelled("O3", "customer");

        check("draft", summary(draft), "draft:O1");
        check("paid", summary(paid), "paid:O1:1500");
        check("shipped", summary(shippedStd), "shipped:O2:TRK-9");
        check("cancelled", summary(cancelled), "cancelled:O3:customer");
        check("priority", carrier(shippedX), "priority-shipping");
        check("standard", carrier(shippedStd), "standard-shipping");
        check("carrier-draft", carrier(draft), "not-shipped");
        check("carrier-paid", carrier(paid), "not-shipped");
        check("carrier-cancelled", carrier(cancelled), "not-shipped");
        check("nullable-null", nullableSummary(null), "missing-state");
        check("nullable-shipped",
                nullableSummary(shippedX), "shipped:O1:X-7");

        expectInvalid("draft-blank-id", () -> new Draft("  "));
        expectInvalid("paid-null-id", () -> new Paid(null, 100));
        expectInvalid("paid-zero", () -> new Paid("O1", 0));
        expectInvalid("paid-negative", () -> new Paid("O1", -5));
        expectInvalid("shipped-null-id",
                () -> new Shipped(null, "T-1"));
        expectInvalid("shipped-null-tracking",
                () -> new Shipped("O1", null));
        expectInvalid("shipped-blank-tracking",
                () -> new Shipped("O1", " "));
        expectInvalid("cancelled-blank-reason",
                () -> new Cancelled("O1", ""));
        expectInvalid("cancelled-null-reason",
                () -> new Cancelled("O1", null));
        expectNull("summary-null", () -> summary(null));

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

Biên dịch bằng **JDK 21 trở lên** rồi chạy:

~~~bash
javac --release 21 ExhaustiveInvariantDemo.java
java ExhaustiveInvariantDemo
~~~

**Output xác định:**

~~~text
PASS draft -> draft:O1
PASS paid -> paid:O1:1500
PASS shipped -> shipped:O2:TRK-9
PASS cancelled -> cancelled:O3:customer
PASS priority -> priority-shipping
PASS standard -> standard-shipping
PASS carrier-draft -> not-shipped
PASS carrier-paid -> not-shipped
PASS carrier-cancelled -> not-shipped
PASS nullable-null -> missing-state
PASS nullable-shipped -> shipped:O1:X-7
PASS draft-blank-id
PASS paid-null-id
PASS paid-zero
PASS paid-negative
PASS shipped-null-id
PASS shipped-null-tracking
PASS shipped-blank-tracking
PASS cancelled-blank-reason
PASS cancelled-null-reason
PASS summary-null
ALL PASSED: 21
~~~

### Những gì kiểm thử khẳng định

- Bốn ca `draft`, `paid`, `shipped`, `cancelled` xác nhận `summary` xử lý đủ bốn subtype.
- Hai ca `priority` và `standard` chứng minh nhánh có `when` và nhánh dự phòng cho `Shipped` đều có thể chạy trong mô hình của bài.
- Ba ca `carrier-*` chứng minh mọi subtype còn lại đều có đường xử lý trong `carrier`.
- `nullable-null` cho thấy `case null` có thể mã hóa chính sách xử lý selector null; `summary-null` xác nhận một API khác lựa chọn từ chối null tường minh.
- Chín ca `expectInvalid`? Không: chương trình có **chín** lời gọi `expectInvalid`, từ mã đơn hàng trắng đến lý do hủy null. Chúng chứng minh constructor bảo vệ invariant trước khi switch sử dụng dữ liệu.
- Mỗi phép `check` hoặc test ngoại lệ không đúng kỳ vọng đều ném `AssertionError`; dòng `ALL PASSED: 21` chỉ được in sau khi tất cả phép kiểm tra đạt.

**Cần phân biệt:** 21 ca ở đây xác minh hành vi khi chạy, gồm cả dữ liệu không hợp lệ được constructor từ chối. **Tính exhaustive** của `summary` và `carrier` được trình biên dịch xác nhận khi biên dịch mã, không phải do chạy đủ 21 case. Hai loại kiểm tra bổ sung cho nhau.

## 10. Negative compile test: chứng minh giới hạn của compiler

Một kiểm thử runtime không thể chứng minh compiler sẽ từ chối một `switch` thiếu nhánh. Với mục đích đó, tạo một **tệp riêng** `GuardOnlyCompileError.java` như sau:

~~~java
public class GuardOnlyCompileError {
    sealed interface State permits Shipped, Closed {}

    record Shipped(String tracking) implements State {
        Shipped {
            if (tracking == null || !tracking.startsWith("X")) {
                throw new IllegalArgumentException("tracking");
            }
        }
    }

    record Closed() implements State {}

    static String label(State state) {
        return switch (state) {
            case Shipped(var tracking)
                    when tracking.startsWith("X") -> "shipping";
            case Closed c -> "closed";
        };
    }
}
~~~

Dùng lệnh:

~~~bash
javac --release 21 GuardOnlyCompileError.java
~~~

**Kỳ vọng:** trình biên dịch từ chối vì `switch expression` **không bao phủ mọi input có thể có**. Dù constructor của `Shipped` yêu cầu tracking code bắt đầu bằng `"X"`, nhánh `case Shipped(...) when ...` vẫn là nhánh có guard nên **không được compiler coi là bao phủ toàn bộ `Shipped`**.

Đây là tệp **cố ý không biên dịch**, không được chép vào cùng chương trình chính ở mục 9. Một bài test biên dịch âm (*negative compile test*) nên kiểm tra rằng lệnh `javac` thất bại **vì thiếu exhaustiveness**, chứ không coi mọi lỗi cú pháp hoặc thiếu class là PASS.

Cách sửa cùng với việc giữ điều kiện nghiệp vụ là thêm nhánh không có guard cho `Shipped` phía sau nhánh guarded. Khi thử các tình huống tương tự, nên xem diagnostic của compiler bản JDK thực tế vì câu chữ thông báo có thể thay đổi.

## 11. Khi thêm subtype: invariant về tập kiểu cũng là hợp đồng API

Giả sử dự án cần bổ sung trạng thái `Returned`. Để làm điều đó, nhà phát triển phải:

1. Định nghĩa subtype `Returned` có payload/invariant riêng.
2. Bổ sung `Returned` vào `permits` của `OrderState`.
3. Biên dịch lại các consumer có exhaustive `switch expression`. Những `switch` không có nhánh `Returned` và không có fallback phù hợp có thể bị từ chối khi biên dịch.
4. Thêm logic xử lý và kiểm thử cho variant mới.
5. Cập nhật **Javadoc về danh sách trạng thái, ràng buộc và quy tắc chuyển trạng thái**.

Một subtype minh họa, **không nằm trong chương trình mục 9**:

~~~java
record Returned(String orderId, String returnReason)
        implements OrderState {
    Returned {
        requireText(orderId, "orderId");
        requireText(returnReason, "returnReason");
    }
}
~~~

Đoạn trên còn cần cập nhật `permits` và các `switch`; nó không thể chỉ được dán vào chương trình chính rồi kỳ vọng tự chạy. Đây chính là giá trị của exhaustive switch: khi tập variant thay đổi, compiler có thể chỉ ra điểm code chưa được cập nhật.

### Lưu ý với thư viện công khai

Tập subtype của `sealed` là **một phần hợp đồng mở rộng API**:

- Consumer có thể viết `switch` không có `default` và dựa vào danh sách subtype đóng tại thời điểm biên dịch.
- Bổ sung subtype vào bản phát hành mới có thể gây lỗi **tương thích nguồn** với các exhaustive switch của consumer khi họ biên dịch lại.
- Việc nâng thư viện nhưng giữ binary consumer cũ cũng cần kiểm thử tương thích và xử lý cập nhật runtime; không được giả định một cách tự động rằng mọi mã đã biên dịch cũ đều an toàn với subtype mới.
- Nếu API được thiết kế cho plugin bên ngoài tự tạo nhiều subtype, một interface mở hoặc mô hình đăng ký handler có thể phù hợp hơn. Dùng `sealed` khi **tập biến thể đóng** thực sự là đặc trưng domain mà bạn muốn công bố.

**Không thêm `default` một cách vô thức chỉ để tránh việc compiler nhắc cập nhật.** Với domain đóng, việc phải xử lý variant mới thường là điều mong muốn. Ngược lại, một API có chiến lược “unknown future variant” rõ ràng có thể chủ động dùng fallback, nhưng nên ghi contract và kiểm thử hậu quả đó.

## 12. Quy tắc ghi tài liệu cho những invariant khác nhau

| Loại bảo đảm | Ai thực thi? | Ghi ở đâu? | Điều không nên ngộ nhận |
| --- | --- | --- | --- |
| Danh sách subtype đóng | Compiler dựa vào `sealed`/`permits` và subtype | Javadoc ở interface + khai báo kiểu | Không phải do comment tự làm exhaustive |
| Payload không null/không trắng | Constructor, factory, validation | Javadoc ở record/constructor và test âm | `record`/`String` không tự đồng nghĩa non-null |
| Quan hệ giữa các field | Code validation nghiệp vụ | Contract và test của model | Compiler không tự chứng minh mọi invariant liên field |
| Điều kiện `when` | Logic runtime ở guard | Ghi quy tắc khi không hiển nhiên | Guarded case không tự bao phủ toàn bộ subtype |
| Selector `null` | API contract, `requireNonNull` hoặc `case null` | Javadoc của phương thức | Exhaustive trên sealed subtype không thay thế null policy |
| Thêm subtype sau này | Quy trình thay đổi API + compiler khi biên dịch lại | Versioning/changelog/Javadoc | Không coi mọi thay đổi tập subtype là tương thích |
| Dữ liệu đầu vào chưa xác thực | Boundary parser/validator | Contract ở DTO/domain mapper | Pattern matching không thay thế validation |

Khi viết tài liệu API, hãy ưu tiên phát biểu **cụ thể và có thể kiểm thử**: “`trackingCode` phải khác `null` và không trắng; constructor ném `IllegalArgumentException` nếu sai” có giá trị hơn “trạng thái luôn hợp lệ”.

Nếu contract chưa được thực thi, không nên viết comment bảo đảm nó đã đúng. Hãy bổ sung code kiểm tra, test hoặc thiết kế lại kiểu trước.

## 13. Những nhầm lẫn thường gặp

**Nhầm 1 — “Invariant của constructor làm nhánh `when` exhaustive”.** Không. Compiler không chứng minh các biểu thức điều kiện nghiệp vụ trong guard từ constructor. Cần nhánh bao phủ không guard hoặc cách tổ chức kiểu thích hợp.

**Nhầm 2 — “`sealed` bảo vệ mọi dữ liệu trong record”.** `sealed` giới hạn subtype trực tiếp. Nó không bảo đảm chuỗi không null, số tiền dương hoặc quan hệ giữa nhiều trường.

**Nhầm 3 — “Có bốn nhánh case, vậy chắc chắn exhaustive”.** Phải xem kiểu selector, kiểu pattern và guard. Bốn nhánh có thể không bao phủ đủ tập kiểu hoặc có pattern bị compiler từ chối.

**Nhầm 4 — “`default` là cách xử lý mọi trường hợp”.** Trong pattern switch Java 21, `default` không tự xử lý selector null. Đồng thời, `default` quá rộng có thể che việc quên cập nhật một subtype mới.

**Nhầm 5 — “Biến `var tracking` luôn không null vì Java biết là String”.** Kiểu tĩnh `String` không tương đương ràng buộc non-null. Component pattern có thể nhận null; cần constructor/guard đáng tin cậy.

**Nhầm 6 — “Comment đúng thì không cần test”.** Comment có thể lỗi thời khi constructor đổi. Kiểm thử dữ liệu hợp lệ và không hợp lệ bảo vệ các invariant đang được branch phụ thuộc.

**Nhầm 7 — “Exhaustiveness đảm bảo mọi thao tác nghiệp vụ đều thành công”.** Nó chỉ giúp kiểm tra bao phủ cấu trúc kiểu/nhánh. Đường xử lý vẫn có thể ném exception, gọi hạ tầng thất bại hoặc vi phạm quy tắc domain khác.

**Nhầm 8 — “Thêm một subtype là thay đổi nội bộ”.** Với một `sealed API` công khai, consumer có thể dựa vào danh sách variant. Bổ sung subtype cần kế hoạch versioning và kiểm tra tương thích.

**Nhầm 9 — “Record bất biến tuyệt đối”.** Record là immutable nông với các component final. Nếu giữ đối tượng mutable, invariant về nội dung có thể bị phá sau khi constructor kiểm tra.

**Nhầm 10 — “Có thể dùng runtime test thay compiler check”.** Test chỉ xác minh những input đã chạy; tính exhaustive cần sự bảo đảm của compiler. Ngược lại, compiler không thay cho test validation nội dung.

## 14. Checklist review và bài tập

### Checklist

1. Interface/class có được đánh dấu `sealed` đúng mục đích domain không? Các subtype trực tiếp có đúng danh sách `permits`?
2. Có subtype `non-sealed` làm mở rộng tập giá trị cần xử lý không? Nếu có, mô tả rõ ảnh hưởng tới cách phân loại.
3. Từng subtype có contract payload và constructor/factory validation không?
4. Với `switch expression`, các nhánh **không guard** có bao phủ tất cả subtype cần thiết không?
5. Các nhánh có `when` được đặt trước nhánh tổng quát của cùng subtype chưa?
6. Null selector được từ chối tường minh hay xử lý bằng `case null`?
7. Nơi dereference biến pattern có invariant đáng tin cậy hoặc guard bảo vệ không?
8. Javadoc có phân biệt lý do exhaustive do **kiểu** với an toàn dữ liệu do **invariant** không?
9. Có test runtime cho từng subtype và trường hợp dữ liệu không hợp lệ?
10. Khi thêm subtype mới, có kiểm tra biên dịch lại consumer và cập nhật tài liệu API?
11. Có tránh `default` rộng che lỗi khi tập subtype vốn được thiết kế đóng?
12. Có test biên dịch âm chứng minh guard-only không tạo bảo đảm exhaustive không?

### Bài tập

- Thêm subtype `Returned` vào `OrderState`, cập nhật `permits` rồi thử biên dịch `summary`. Quan sát các vị trí cần cập nhật và bổ sung test.
- Trong mô hình `State` của mục 5, bỏ nhánh `case Shipped(...)` không guard. Quan sát compiler từ chối `switch` dù constructor chỉ cho phép tracking bắt đầu bằng `"X"`.
- Tạm bỏ kiểm tra null của `Shipped.trackingCode` trong constructor rồi tạo `new Shipped("O1", null)`. Tìm vị trí `summary` dựa vào invariant cũ và giải thích vì sao comment có thể gây hiểu lầm.
- Đổi `summary` từ `Objects.requireNonNull` sang `case null`; cập nhật contract và test `summary-null` cho phù hợp.
- Viết Javadoc cho `Paid`: mã đơn không trắng, `amountCents > 0`, và tài liệu hóa ngoại lệ khi vi phạm. Đối chiếu với kiểm thử `paid-zero` và `paid-negative`.
- Thảo luận một API plugin có subtype mở: nên dùng `sealed`, `non-sealed` hay interface thường? Nêu đánh đổi giữa khả năng mở rộng và compiler exhaustiveness.

**Ghi nhớ:** **`sealed` và kiểu subtype** tạo cơ sở để compiler kiểm tra exhaustive `switch`; **constructor/factory invariant** tạo cơ sở để sử dụng dữ liệu trong từng nhánh an toàn; **`when`** là điều kiện runtime và không được xem là bao phủ toàn bộ subtype chỉ vì Javadoc khẳng định điều kiện ấy luôn đúng. Ghi rõ từng bảo đảm, xử lý null có chủ đích và bảo vệ chúng bằng test sẽ làm API pattern matching dễ hiểu, an toàn và có thể tiến hóa hơn.