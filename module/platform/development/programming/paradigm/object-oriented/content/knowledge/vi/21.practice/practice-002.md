# Bài tập: Đóng gói quy tắc của đơn hàng bằng Java OOP

> **Bối cảnh:** Thực hành thiết kế một đối tượng `Order` (đơn hàng) có trách nhiệm tự bảo vệ trạng thái và các quy tắc nghiệp vụ. Mục tiêu không chỉ là giấu field bằng `private`, mà còn ngăn mọi đường sửa dữ liệu có thể tạo một đơn hàng sai.

## 1. Tình huống

Bạn tham gia xây dựng phần giỏ hàng/đặt hàng cho một cửa hàng trực tuyến. Thiết kế ban đầu có thể trông như sau:

~~~java
import java.util.ArrayList;
import java.util.List;

class OrderBad {
    public final List<OrderLineBad> lines = new ArrayList<>();
    public String status = "DRAFT";
}

class OrderLineBad {
    public String sku;
    public long priceCents;
    public int quantity;
}
~~~

Mã khác có thể làm tất cả những việc sau:

~~~java
OrderBad order = new OrderBad();
order.status = "PLACED";
order.lines.add(new OrderLineBad()); // sku null, quantity 0
order.lines.get(0).quantity = -5;
order.lines.clear();                 // xóa sau khi đã đặt hàng
~~~

Các lỗi này xảy ra vì **người sử dụng đối tượng có toàn quyền sửa trạng thái**, nên không ai bảo đảm bất biến nghiệp vụ. Việc đổi `public List` thành `private List` nhưng vẫn trả thẳng danh sách gốc từ getter cũng không giải quyết vấn đề.

**Nhiệm vụ:** thiết kế lại `Order` thành một *aggregate* đơn giản: `Order` sở hữu các dòng hàng, kiểm soát cập nhật, tự tính tổng tiền và quản lý vòng đời đơn hàng. Client chỉ gọi những hành vi được phép.

## 2. Đặc tả bắt buộc trước khi viết code

### Dữ liệu và quy tắc

Mỗi đơn hàng có một mã `orderId`, một trạng thái và tập các dòng hàng. Mỗi dòng hàng gồm mã sản phẩm `sku`, đơn giá `unitPriceCents` và số lượng `quantity`.

| Quy tắc | Hợp đồng cụ thể |
|---|---|
| Mã đơn hàng | Không `null`, không rỗng hoặc chỉ khoảng trắng; chuẩn hóa bằng `trim()` |
| Mã SKU | Không `null`/rỗng; sau `trim()` và chuyển chữ hoa, chỉ chấp nhận `A-Z`, `0-9`, dấu `-` |
| Trùng SKU | Mỗi SKU chuẩn hóa xuất hiện tối đa một dòng; `setLine` thay thế dòng đã có |
| Đơn giá | Đơn vị là **cent**, trong khoảng `1..1_000_000` |
| Số lượng | Mỗi dòng có `quantity` trong `1..100` |
| Tổng tiền hàng | `subtotal = Σ(unitPriceCents × quantity)`, không vượt `10_000_000` cent |
| Sửa số lượng | `changeQuantity(sku, 0)` xóa dòng; giá trị âm hoặc trên 100 là lỗi |
| Xóa SKU | `removeLine(sku)` trả `true` nếu có dòng được xóa; `false` nếu không tồn tại |
| Phí vận chuyển | Đơn rỗng: 0; đơn có `subtotal >= 100_000`: 0; còn lại: `15_000` cent |
| Giảm giá | Khi `subtotal >= 200_000`, giảm `5%` theo phép chia nguyên `subtotal / 20`; còn lại 0 |
| Phải trả | `payable = subtotal - discount + shipping` |
| Ngoại lệ | Đầu vào sai: `IllegalArgumentException`; SKU chưa tồn tại khi đổi số lượng: `NoSuchElementException`; trạng thái không cho phép thao tác: `IllegalStateException` |
| Hiệu ứng khi lỗi | Khi một thao tác bị từ chối, đơn hàng vẫn giữ trạng thái trước thao tác |

Quy tắc chính sách giá trên chỉ là giả định cho bài thực hành. Trong hệ thống thật, cần thống nhất rõ chính sách tiền, thuế, chiết khấu và làm tròn với bên nghiệp vụ.

### Vòng đời của đơn hàng

- **DRAFT:** thêm/thay thế dòng hàng, đổi số lượng và xóa dòng được phép.
- **PLACED:** đơn đã đặt; không được sửa dòng hàng hoặc đặt lại.
- **CANCELLED:** trạng thái kết thúc; không được thêm/sửa/xóa hoặc đặt hàng.
- `place()` chỉ đi từ `DRAFT` sang `PLACED` khi đơn có ít nhất một dòng.
- `cancel()` cho phép từ `DRAFT` hoặc `PLACED` sang `CANCELLED`; gọi lần hai bị từ chối.
- Việc hủy ở đây chỉ thay đổi trạng thái của ví dụ trong bộ nhớ; **không tự xử lý hoàn tiền hay gửi thông báo**.

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT : tạo Order
    DRAFT --> DRAFT : setLine / changeQuantity / removeLine
    DRAFT --> PLACED : place() khi có dòng
    DRAFT --> CANCELLED : cancel()
    PLACED --> CANCELLED : cancel()
    CANCELLED --> [*]
~~~

### API mong muốn

~~~java
Order order = new Order("ORD-001");

order.setLine(" book ", 90_000, 1);
order.setLine("PEN", 10_000, 2);
order.changeQuantity("BOOK", 2);

List<OrderLine> snapshot = order.lines();  // chỉ đọc, không sửa đơn được
OrderSummary result = order.summary();     // do Order tự tính
order.place();                             // khóa các thao tác chỉnh dòng
~~~

API này cung cấp **hành động có ý nghĩa**, thay vì `setStatus("PLACED")`, `setSubtotal(...)` hoặc `getMutableLines()`. Điều đó giúp đặt quy tắc đúng nơi chịu trách nhiệm.

## 3. Gợi ý tự làm trước khi xem lời giải

Thử tự triển khai theo các điểm sau:

1. Tạo `enum OrderStatus { DRAFT, PLACED, CANCELLED }` để loại bỏ các chuỗi trạng thái tùy tiện.
2. Sử dụng `record OrderLine(...)` để mỗi dòng hàng không có setter và kiểm tra dữ liệu ngay khi khởi tạo.
3. Giữ các field của `Order` là `private`; dùng `Map<String, OrderLine>` để quản lý một dòng trên mỗi SKU.
4. Đưa nghiệp vụ vào các method `setLine`, `changeQuantity`, `removeLine`, `place`, `cancel`, `summary`.
5. Tính giá trị **dự kiến** của một lần sửa trước khi cập nhật vào đơn. Nếu vượt giới hạn tổng tiền, báo lỗi mà không để lại dữ liệu nửa chừng.
6. Trả `List.copyOf(lines.values())` làm snapshot; vì `OrderLine` chứa các component immutable, người gọi không thể sửa cấu trúc hoặc phần tử để tác động giỏ hàng.
7. Tạo test cho giá trị biên và các thao tác bị cấm sau `place()`.

Một cách chia trách nhiệm hợp lý:

| Thành phần | Chịu trách nhiệm | Không nên làm |
|---|---|---|
| `Order` | Kiểm soát trạng thái, các dòng hàng, bất biến và quy tắc tiền của đơn | Trả Map nội bộ, cho caller gán tổng tiền |
| `OrderLine` | Biểu diễn một dòng hàng hợp lệ, bất biến | Có setter thay số lượng hoặc đơn giá |
| `OrderStatus` | Tập trạng thái hợp lệ | Dùng chuỗi tùy ý để chứa trạng thái |
| `OrderSummary` | Kết quả tính tiền bất biến | Là nơi lưu tổng tiền có thể được sửa tự do |
| Client/UI/API | Gọi hành vi, hiển thị snapshot | Tính lại quy tắc kinh doanh rồi tự sửa field |

## 4. Lời giải tham khảo Java 17 — chạy độc lập

Tạo tệp **`OrderExercise.java`**. Đoạn mã dưới đây sử dụng duy nhất Java Standard Library và có phương thức `main` để tự kiểm tra nghiệp vụ.

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.NoSuchElementException;

public class OrderExercise {
    static final long MAX_UNIT_PRICE = 1_000_000L;
    static final long MAX_SUBTOTAL = 10_000_000L;
    static final int MAX_QUANTITY = 100;

    enum OrderStatus {
        DRAFT, PLACED, CANCELLED
    }

    static String normalizeSku(String sku) {
        if (sku == null) {
            throw new IllegalArgumentException("sku must not be null");
        }
        String normalized = sku.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("[A-Z0-9-]+")) {
            throw new IllegalArgumentException("Invalid SKU: " + sku);
        }
        return normalized;
    }

    // Immutable value object. Bất biến được kiểm tra ngay khi khởi tạo.
    record OrderLine(String sku, long unitPriceCents, int quantity) {
        OrderLine {
            sku = normalizeSku(sku);
            if (unitPriceCents < 1 || unitPriceCents > MAX_UNIT_PRICE) {
                throw new IllegalArgumentException("Invalid unit price");
            }
            if (quantity < 1 || quantity > MAX_QUANTITY) {
                throw new IllegalArgumentException("Invalid quantity");
            }
        }

        long lineTotalCents() {
            return Math.multiplyExact(unitPriceCents, quantity);
        }
    }

    // Snapshot số tiền; caller chỉ đọc các component.
    record OrderSummary(
            long subtotalCents,
            long discountCents,
            long shippingCents,
            long payableCents) {
    }

    static final class Order {
        private final String orderId;
        private final Map<String, OrderLine> lines = new LinkedHashMap<>();
        private OrderStatus status = OrderStatus.DRAFT;

        Order(String orderId) {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("orderId is required");
            }
            this.orderId = orderId.trim();
        }

        String orderId() {
            return orderId;
        }

        OrderStatus status() {
            return status;
        }

        int lineCount() {
            return lines.size();
        }

        // Không trả Map hoặc collection mutable đang được giữ bên trong.
        List<OrderLine> lines() {
            return List.copyOf(lines.values());
        }

        private void ensureDraft() {
            if (status != OrderStatus.DRAFT) {
                throw new IllegalStateException(
                    "Order cannot be modified in state " + status
                );
            }
        }

        // Tính trước và từ chối ứng viên sai trước khi sửa state thật.
        private static long subtotalOf(Map<String, OrderLine> candidate) {
            long sum = 0;
            try {
                for (OrderLine line : candidate.values()) {
                    sum = Math.addExact(sum, line.lineTotalCents());
                }
            } catch (ArithmeticException overflow) {
                throw new IllegalArgumentException(
                    "Subtotal arithmetic overflow", overflow
                );
            }
            if (sum > MAX_SUBTOTAL) {
                throw new IllegalArgumentException(
                    "Subtotal exceeds " + MAX_SUBTOTAL
                );
            }
            return sum;
        }

        // Thêm SKU mới hoặc thay thế dòng của SKU đã có.
        void setLine(String sku, long unitPriceCents, int quantity) {
            ensureDraft();
            OrderLine newLine = new OrderLine(sku, unitPriceCents, quantity);

            Map<String, OrderLine> candidate = new LinkedHashMap<>(lines);
            candidate.put(newLine.sku(), newLine);
            subtotalOf(candidate);             // có thể ném lỗi

            lines.put(newLine.sku(), newLine); // commit sau validation
        }

        void changeQuantity(String sku, int newQuantity) {
            ensureDraft();
            String key = normalizeSku(sku);
            if (newQuantity < 0 || newQuantity > MAX_QUANTITY) {
                throw new IllegalArgumentException("Invalid quantity");
            }

            OrderLine current = lines.get(key);
            if (current == null) {
                throw new NoSuchElementException("Unknown SKU: " + key);
            }

            if (newQuantity == 0) {
                lines.remove(key);
                return;
            }

            // Giữ đơn giá cũ và kiểm tra tổng trước khi cập nhật.
            setLine(key, current.unitPriceCents(), newQuantity);
        }

        boolean removeLine(String sku) {
            ensureDraft();
            return lines.remove(normalizeSku(sku)) != null;
        }

        OrderSummary summary() {
            long subtotal = subtotalOf(lines);
            long discount = subtotal >= 200_000 ? subtotal / 20 : 0;
            long shipping = (lines.isEmpty() || subtotal >= 100_000)
                    ? 0 : 15_000;
            long payable = Math.addExact(
                Math.subtractExact(subtotal, discount), shipping);
            return new OrderSummary(
                subtotal, discount, shipping, payable
            );
        }

        void place() {
            ensureDraft();
            if (lines.isEmpty()) {
                throw new IllegalStateException("Cannot place empty order");
            }
            status = OrderStatus.PLACED;
        }

        void cancel() {
            if (status == OrderStatus.CANCELLED) {
                throw new IllegalStateException("Order already cancelled");
            }
            status = OrderStatus.CANCELLED;
        }
    }

    private static void require(boolean value, String message) {
        if (!value) {
            throw new AssertionError(message);
        }
    }

    // Mini assertion utility, không cần dependency ngoài JDK.
    private static void expectThrows(
            Class<? extends RuntimeException> type, Runnable action) {
        try {
            action.run();
        } catch (RuntimeException ex) {
            if (type.isInstance(ex)) {
                return;
            }
            throw new AssertionError(
                "Expected " + type.getSimpleName()
                    + " but caught " + ex.getClass().getSimpleName(),
                ex
            );
        }
        throw new AssertionError(
            "Expected exception " + type.getSimpleName()
        );
    }

    private static OrderLine findLine(List<OrderLine> snapshot, String sku) {
        return snapshot.stream()
            .filter(line -> line.sku().equals(sku))
            .findFirst()
            .orElseThrow();
    }

    public static void main(String[] args) {
        // 1) Chuẩn hóa SKU và tính tiền.
        Order order = new Order(" ORD-001 ");
        require(order.status() == OrderStatus.DRAFT, "initial status");
        require(order.summary().equals(
                new OrderSummary(0, 0, 0, 0)), "empty summary");

        order.setLine(" book ", 90_000, 1);
        order.setLine("PEN", 10_000, 2);
        require(order.lineCount() == 2, "two unique SKUs");
        require(order.summary().equals(
                new OrderSummary(110_000, 0, 0, 110_000)),
                "no discount, free shipping above 100000");

        // 2) Snapshot không thể sửa và không đổi theo update sau đó.
        List<OrderLine> before = order.lines();
        expectThrows(UnsupportedOperationException.class, before::clear);
        require(findLine(before, "BOOK").quantity() == 1,
                "old quantity");

        order.changeQuantity("BOOK", 2);
        require(order.summary().equals(
                new OrderSummary(200_000, 10_000, 0, 190_000)),
                "5% discount from 200000");

        require(findLine(before, "BOOK").quantity() == 1,
                "old snapshot remains unchanged");
        require(findLine(order.lines(), "BOOK").quantity() == 2,
                "new snapshot sees new state");

        // 3) Validation thất bại không làm hỏng đơn.
        OrderSummary goodState = order.summary();
        expectThrows(IllegalArgumentException.class,
            () -> order.setLine("BAD", -1, 1));
        expectThrows(IllegalArgumentException.class,
            () -> order.setLine("?", 100, 1));
        expectThrows(IllegalArgumentException.class,
            () -> order.changeQuantity("BOOK", -3));
        expectThrows(NoSuchElementException.class,
            () -> order.changeQuantity("UNKNOWN", 1));
        expectThrows(IllegalArgumentException.class,
            () -> order.setLine("EXPENSIVE", 1_000_000, 11));

        require(order.summary().equals(goodState),
                "failed mutations must not change totals");
        require(order.lineCount() == 2,
                "failed mutations must not add/remove lines");

        // 4) Kiểm thử cả hai phía của ngưỡng phí ship và giảm giá.
        Order boundaries = new Order("ORD-002");
        boundaries.setLine("A", 99_999, 1);
        require(boundaries.summary().equals(
                new OrderSummary(99_999, 0, 15_000, 114_999)),
                "shipping below threshold");

        boundaries.setLine("A", 100_000, 1);
        require(boundaries.summary().equals(
                new OrderSummary(100_000, 0, 0, 100_000)),
                "shipping free at threshold");

        boundaries.setLine("A", 199_999, 1);
        require(boundaries.summary().discountCents() == 0,
                "no discount below 200000");

        boundaries.setLine("A", 200_000, 1);
        require(boundaries.summary().equals(
                new OrderSummary(200_000, 10_000, 0, 190_000)),
                "discount at threshold");

        // 5) Trạng thái quản lý hành động được phép.
        expectThrows(IllegalStateException.class,
            () -> new Order("EMPTY").place());

        order.place();
        require(order.status() == OrderStatus.PLACED, "placed status");
        expectThrows(IllegalStateException.class,
            () -> order.setLine("NEW", 50, 1));
        expectThrows(IllegalStateException.class,
            () -> order.removeLine("BOOK"));
        expectThrows(IllegalStateException.class, order::place);

        order.cancel();
        require(order.status() == OrderStatus.CANCELLED, "cancelled status");
        expectThrows(IllegalStateException.class, order::cancel);
        expectThrows(IllegalStateException.class,
            () -> order.changeQuantity("BOOK", 1));

        System.out.println("PASS: SKU and business-rule validation");
        System.out.println("PASS: defensive snapshot and protected state");
        System.out.println("PASS: pricing thresholds and unchanged state on error");
        System.out.println("PASS: order lifecycle");
    }
}
~~~

Chạy:

~~~bash
javac OrderExercise.java
java OrderExercise
~~~

Kết quả kỳ vọng:

~~~text
PASS: SKU and business-rule validation
PASS: defensive snapshot and protected state
PASS: pricing thresholds and unchanged state on error
PASS: order lifecycle
~~~

**Giải thích thiết kế:** `Order` không có `setStatus` hay `setTotal`. Mã gọi `place()` hoặc `cancel()` theo quy tắc chuyển trạng thái; `summary()` luôn tính từ các dòng hiện hành. Phương thức `setLine()` tạo map ứng viên và kiểm tra giới hạn **trước** khi cập nhật map thật. Nhờ vậy, một thao tác vượt giới hạn tổng tiền không bỏ lại dòng hàng sai.

Mã ví dụ dùng `LinkedHashMap` để thuận tiện theo dõi dữ liệu, nhưng client không phụ thuộc trực tiếp loại map này. `OrderLine` là record chỉ chứa `String` và primitive nên snapshot không lộ mutable element; nếu record chứa `Date`, `List` hoặc mảng, chỉ dùng `record` thôi chưa bảo đảm bất biến sâu.

## 5. Các nguyên tắc OOP được thực hành

### Encapsulation: chủ thể sở hữu trạng thái

~~~mermaid
classDiagram
    class Order {
        -String orderId
        -Map~String,OrderLine~ lines
        -OrderStatus status
        +setLine(String,long,int)
        +changeQuantity(String,int)
        +removeLine(String) boolean
        +lines() List~OrderLine~
        +summary() OrderSummary
        +place()
        +cancel()
    }
    class OrderLine {
        <<record>>
        +sku() String
        +unitPriceCents() long
        +quantity() int
    }
    class OrderSummary {
        <<record>>
        +subtotalCents() long
        +discountCents() long
        +shippingCents() long
        +payableCents() long
    }
    class OrderStatus {
        <<enumeration>>
        DRAFT
        PLACED
        CANCELLED
    }
    Order "1" o-- "*" OrderLine : sở hữu
    Order --> OrderStatus : trạng thái
    Order --> OrderSummary : tạo bản đọc
~~~

Trong phạm vi bài tập, **`Order` là nơi duy nhất được cập nhật collection và trạng thái**. Client gọi API của `Order`, không chỉnh `Map` hay enum field trực tiếp.

### Invariant: kiểm tra ở mọi đường thay đổi

Không đủ nếu constructor kiểm tra đơn giá và số lượng nhưng một setter khác vẫn cho sửa chúng. Các quy tắc cần giữ đúng qua **mọi public mutation**, bao gồm:

- Thêm/thay thế một dòng.
- Đổi số lượng, nhất là `0` hoặc giá trị âm.
- Xóa dòng và xác nhận/đặt hàng.
- Thao tác thất bại do trạng thái hoặc giới hạn tổng tiền.

### Information hiding: giấu quyết định lưu trữ

Sử dụng `Map<String,OrderLine>` là một quyết định nội bộ; về sau có thể đổi sang một cấu trúc khác mà các thao tác nghiệp vụ công khai vẫn giữ nguyên. `Order.lines()` trả snapshot để UI hiển thị, không cho UI quản lý cách các dòng được lưu.

### Cohesion: logic nào thuộc trách nhiệm của Order?

Ví dụ này đưa **tổng tiền, trạng thái và quy tắc dòng hàng** vào `Order` vì chúng phụ thuộc trực tiếp đến một đơn. Nhưng `Order` không cần tự mở kết nối database, tự gửi email hay thực hiện yêu cầu thanh toán tới cổng ngoài. Các công việc có side effect này nên được điều phối ở tầng ứng dụng bằng service/port phù hợp.

## 6. Vì sao không nên dùng setter hoặc getter collection trực tiếp?

Một phương án thường gặp:

~~~java
class Order {
    private List<OrderLine> lines;
    private long totalCents;
    private String status;

    public void setLines(List<OrderLine> lines) {
        this.lines = lines;
    }
    public void setTotalCents(long totalCents) {
        this.totalCents = totalCents;
    }
    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

Nó có thể tạo trạng thái trái hợp đồng như `status="PLACED"` với danh sách rỗng, tổng tiền không bằng tổng dòng hoặc dòng hàng thay đổi mà `totalCents` không được cập nhật. Để tránh:

- Cho phép **đặt hàng** bằng `place()`, không qua gán trạng thái tùy ý.
- Cho phép **đổi số lượng** bằng `changeQuantity()` để xử lý riêng trường hợp `0`.
- Cho phép **đọc tổng** qua `summary()`, không qua field tổng tiền mà client có thể gán.
- Cho phép **xem dòng hàng** qua snapshot chứa immutable value object, không trả tham chiếu mutable nội bộ.

Không có nghĩa mọi đối tượng đều phải tránh setter. DTO hoặc dữ liệu truyền qua API có thể dùng JavaBean/setter. Bài tập này nhắm tới **đối tượng miền có quy tắc cần được bảo vệ**.

## 7. Ma trận kiểm thử nghiệm thu

| Mã | Hành động | Kết quả đúng |
|---|---|---|
| TC01 | Tạo đơn mới | Trạng thái DRAFT, 0 dòng, tổng 0 |
| TC02 | Thêm `" book "` rồi `"BOOK"` | Chỉ một SKU chuẩn hóa; lần sau thay dòng trước |
| TC03 | Giá bằng 0, số âm, hơn 1.000.000 | Ném `IllegalArgumentException` |
| TC04 | Số lượng 0 tại `setLine`, số lượng 101 | Ném `IllegalArgumentException` |
| TC05 | `changeQuantity("BOOK", 0)` | Xóa BOOK nếu có; không giữ dòng quantity 0 |
| TC06 | Đổi số lượng SKU chưa tồn tại | Ném `NoSuchElementException` |
| TC07 | Tổng sau cập nhật vượt 10.000.000 | Từ chối; tổng và dòng cũ không đổi |
| TC08 | Lấy `lines()` rồi `clear()` | Bị từ chối bằng `UnsupportedOperationException` |
| TC09 | Lấy snapshot A rồi cập nhật đơn | A vẫn chứa dữ liệu cũ, snapshot B có dữ liệu mới |
| TC10 | Tổng 99.999 cent | Phí ship 15.000 |
| TC11 | Tổng đúng 100.000 cent | Miễn phí ship |
| TC12 | Tổng đúng 200.000 cent | Giảm 10.000 cent |
| TC13 | `place()` khi đơn rỗng | Ném `IllegalStateException`; vẫn DRAFT |
| TC14 | `place()` với đơn có dòng | Thành PLACED; cấm sửa dòng |
| TC15 | `cancel()`, rồi cố sửa/đặt/hủy lại | Ném `IllegalStateException` |
| TC16 | Mọi đầu vào không hợp lệ | Không để lại state thay đổi một phần |

Bạn có thể viết các test đó trước khi xem lời giải rồi dùng chúng làm tiêu chí tự chấm. Nếu thay đổi cách lưu collection, các test hành vi vẫn phải đúng.

### Một số kiểm thử JUnit 5

Với dự án đã có `JUnit Jupiter`, đặt tệp `OrderExerciseTest.java` **cùng package** với `OrderExercise`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class OrderExerciseTest {
    @Test
    void duplicateSkuIsReplacedAfterNormalization() {
        var order = new OrderExercise.Order("ORD-1");
        order.setLine("book", 100, 2);
        order.setLine(" BOOK ", 150, 3);

        assertEquals(1, order.lineCount());
        assertEquals("BOOK", order.lines().get(0).sku());
        assertEquals(450, order.summary().subtotalCents());
    }

    @Test
    void invalidUpdateLeavesOrderUnchanged() {
        var order = new OrderExercise.Order("ORD-2");
        order.setLine("BOOK", 100, 2);
        var before = order.summary();

        assertThrows(IllegalArgumentException.class,
            () -> order.setLine("EXPENSIVE", 1_000_000, 11));

        assertEquals(before, order.summary());
        assertEquals(1, order.lineCount());
    }

    @Test
    void returnedLinesCannotBypassRules() {
        var order = new OrderExercise.Order("ORD-3");
        order.setLine("BOOK", 100, 2);
        var snapshot = order.lines();

        assertThrows(UnsupportedOperationException.class, snapshot::clear);

        order.changeQuantity("BOOK", 3);
        assertEquals(2, snapshot.get(0).quantity());
        assertEquals(3, order.lines().get(0).quantity());
    }

    @Test
    void placingFreezesMutations() {
        var order = new OrderExercise.Order("ORD-4");
        order.setLine("PEN", 99_999, 1);

        assertEquals(15_000, order.summary().shippingCents());
        order.place();

        assertThrows(IllegalStateException.class,
            () -> order.setLine("NEW", 10, 1));
        assertThrows(IllegalStateException.class,
            () -> order.removeLine("PEN"));
        assertEquals(OrderExercise.OrderStatus.PLACED, order.status());
    }
}
~~~

Trong ứng dụng thực tế, hãy tổ chức các type thành class/record ở các tệp phù hợp, chọn `public`/package-private theo ranh giới API; phần code trên chọn nested types để ví dụ có thể chạy bằng một tệp.

## 8. Thảo luận: các quyết định thiết kế và giới hạn của lời giải

**Vì sao dùng Map?** SKU là khóa duy nhất; map giúp biểu diễn trực tiếp bất biến không trùng SKU. Nhưng map không được trả trực tiếp; client không cần biết cấu trúc lưu trữ. `LinkedHashMap` giữ thứ tự chèn để dễ quan sát, nhưng nếu thứ tự giao diện là **hợp đồng**, cần viết rõ và kiểm thử riêng.

**Vì sao dùng cent và long?** Tránh biểu diễn tiền bằng `double` dễ có lỗi sai số nhị phân. Với tiền tệ có nhiều quy tắc precision/rounding, có thể dùng `BigDecimal` với scale, currency, rounding mode được đặc tả. `long` theo đơn vị nhỏ nhất chỉ phù hợp nếu hệ thống định nghĩa thống nhất đơn vị và giới hạn.

**Vì sao dùng record?** `OrderLine` và `OrderSummary` là những giá trị bất biến, không có danh tính độc lập trong ví dụ. Bản thân record **không tự bảo đảm deep immutability** nếu các component chứa mutable object; ở đây chúng dùng `String` và primitive nên an toàn theo ranh giới đã chọn.

**Vì sao kiểm tra tổng trước khi commit?** Nếu thêm dòng rồi mới tính tổng và phát hiện vượt giới hạn, map thật có thể chứa dữ liệu sai. Dựng candidate trước và kiểm tra trên candidate giúp thao tác thất bại không gây thay đổi một phần.

**Vì sao không đặt cờ `isPlaced` public?** Vì client có thể tự đánh dấu đã đặt mà không kiểm tra điều kiện đơn không rỗng. Enum trạng thái cùng các method chuyển trạng thái giúp biểu đạt quy tắc một cách tập trung.

**Vì sao không kết nối database trong Order?** Quy tắc miền và side effect hạ tầng có mức trách nhiệm khác nhau. Một application service có thể tải `Order` từ repository, gọi `order.place()` rồi lưu lại trong transaction, trong khi `Order` chỉ chịu trách nhiệm tính hợp lệ của thao tác.

### Giới hạn cần bổ sung khi đưa vào production

- **Đồng thời:** `LinkedHashMap` và `Order` hiện không thread-safe. Nếu nhiều request có thể chỉnh cùng đơn, sử dụng transaction, optimistic locking/version và chiến lược xử lý xung đột. Snapshot đọc an toàn không tự khiến cập nhật đồng thời trở nên an toàn.
- **Phí vận chuyển và chiết khấu:** Giá trị có thể phụ thuộc mã giảm giá, địa chỉ, phí từ bên giao hàng, ngày khuyến mãi; không nên nhét mọi phụ thuộc hạ tầng vào entity. Có thể đưa chính sách được cung cấp từ ngoài vào thao tác domain khi yêu cầu phát triển.
- **Tồn kho và thanh toán:** `place()` trong bài tập chỉ đổi trạng thái. Trừ kho, gọi payment gateway, gửi email và phát sự kiện phải được điều phối có kiểm soát; không kết luận tất cả những việc đó đã được hoàn tất sau `place()`.
- **Tính lịch sử:** Hệ thống thật có thể cần chốt snapshot tên sản phẩm/đơn giá tại thời điểm đặt, lịch sử chuyển trạng thái và tính tiền theo chính sách được phiên bản hóa.
- **Hủy sau thanh toán:** Bài tập cho phép `PLACED → CANCELLED` nhưng chưa có điều kiện thời gian giao hàng hay hoàn tiền. Khi nghiệp vụ thực tế có các trạng thái `PAID`, `SHIPPED`, cần thiết kế state machine và luật hủy chính xác.
- **API compatibility:** Khi thay entity kiểu anemic với getter/setter công khai bằng aggregate, mã bên ngoài có thể không biên dịch; cần cập nhật client, DTO mapping và các ràng buộc ORM/JPA tương ứng.

## 9. Bài tập mở rộng theo mức độ

**Mức 1 — Đóng gói chắc chắn:** Viết thêm các ca test về SKU rỗng, ký tự không hợp lệ, số lượng 101, thay dòng trùng SKU và `removeLine` không tồn tại. Chứng minh rằng mỗi lần lỗi không thay đổi `OrderSummary`, `lineCount` và `status`.

**Mức 2 — Bảo vệ quy tắc tiền:** Thử tổng tiền sát `10_000_000`; thay một dòng sao cho vượt giới hạn, xác nhận thao tác bị từ chối nhưng dòng cũ còn nguyên. Điều chỉnh giả định giới hạn và kiểm thử lại các ranh giới miễn phí ship/giảm giá.

**Mức 3 — Chính sách có biến thể:** Thêm khách VIP được miễn phí giao hàng. Cân nhắc nên lưu `CustomerType` trong `Order` hay truyền một chính sách giá có hợp đồng rõ. Nêu lý do chọn cách thiết kế dựa trên yêu cầu thật, tránh sinh interface chỉ để tăng số lớp.

**Mức 4 — Bảo vệ trạng thái:** Bổ sung `PAID` hoặc `SHIPPED` và quy tắc chuyển trạng thái tương ứng. Viết bảng chuyển trạng thái trước, sau đó code và test mọi chuyển trạng thái bị cấm.

**Mức 5 — Ứng dụng thực tế:** Viết `PlaceOrderUseCase` để lấy đơn từ repository, gọi `order.place()` rồi lưu. Dùng fake repository trong unit test; viết integration test để xác nhận transaction/optimistic locking khi hai yêu cầu cùng sửa một đơn.

### Rubric tự đánh giá (10 điểm)

| Tiêu chí | Điểm |
|---|---:|
| Trạng thái và dòng hàng được giấu, client không sửa trực tiếp | 2 |
| Input validation, SKU duy nhất, giới hạn số lượng và đơn giá | 2 |
| Quy tắc subtotal/discount/shipping/payable chính xác tại biên | 2 |
| Chuyển trạng thái DRAFT/PLACED/CANCELLED đúng | 2 |
| Test chống representation exposure và thao tác thất bại không làm hỏng state | 2 |

**Hoàn thành bài tập** khi tất cả test nghiệm thu phù hợp đặc tả đều PASS và một client chỉ dùng API công khai không thể tự ý tạo dòng hàng âm, vượt giới hạn, thay đổi đơn đã đặt hoặc sửa cấu trúc nội bộ để bỏ qua quy tắc. Đó là ý nghĩa thực hành của việc **đóng gói quy tắc của đơn hàng** trong OOP.