# Đóng gói hành vi thay vì chỉ bao bọc dữ liệu trong Java OOP

**Đóng gói (encapsulation)** không dừng ở việc đặt các field thành `private` rồi tạo đủ getter/setter. Giá trị lớn hơn của đóng gói là để **đối tượng chịu trách nhiệm thực hiện những thao tác hợp lệ trên chính trạng thái của nó**. Code bên ngoài đưa ra một *ý định* như “xác nhận đơn hàng” hoặc “thêm sản phẩm”; đối tượng tự quyết định thao tác đó có được phép hay không và cập nhật những thuộc tính liên quan một cách nhất quán.

Ví dụ, thay vì yêu cầu bên gọi tự kiểm tra các điều kiện rồi `order.setStatus(CONFIRMED)`, hãy cho `Order` phương thức `confirm()`. Khi quy tắc xác nhận thay đổi, ta sửa tại nơi chịu trách nhiệm về đơn hàng.

## 1. Vì sao chỉ bao bọc dữ liệu là chưa đủ?

Xét một lớp đơn hàng đơn giản:

~~~java
import java.math.BigDecimal;

public class OrderData {
    private String status;
    private BigDecimal total;

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }
}
~~~

Dù các field đều `private`, lớp này vẫn cho phép:

~~~java
OrderData order = new OrderData();

order.setStatus("CONFIRMED");
order.setTotal(new BigDecimal("-90000"));
~~~

Không có gì ngăn đơn hàng được xác nhận dù chưa có sản phẩm hoặc có tổng tiền âm. Toàn bộ hiểu biết về trạng thái hợp lệ có thể bị đẩy ra ngoài:

~~~java
// Mỗi đoạn code gọi tới OrderData có nguy cơ phải kiểm tra lại:
if (order.getTotal() != null &&
        order.getTotal().signum() > 0 &&
        !"CANCELLED".equals(order.getStatus())) {
    order.setStatus("CONFIRMED");
}
~~~

Nếu hệ thống có thêm quy tắc như “không thể thêm sản phẩm sau khi xác nhận”, “đơn hủy không thể xác nhận lại”, nhiều nơi sẽ phải tự nhớ và tự áp dụng. Cách thiết kế này thường được gọi là **anemic domain model** (mô hình miền chủ yếu chứa dữ liệu, ít hành vi nghiệp vụ).

Vấn đề không nằm ở bản thân getter/setter. Chúng hoàn toàn phù hợp với nhiều kiểu dữ liệu truyền tải hoặc cấu hình đơn giản. Vấn đề xuất hiện khi **trạng thái mang quy tắc nghiệp vụ** nhưng mọi nơi đều được phép điều khiển nó thông qua các setter không có ràng buộc.

| Câu hỏi | Lớp chỉ bao bọc dữ liệu | Đối tượng đóng gói hành vi |
| --- | --- | --- |
| Ai quyết định trạng thái hợp lệ? | Thường là code gọi bên ngoài | Đối tượng sở hữu trạng thái |
| Bên ngoài yêu cầu thay đổi thế nào? | `setStatus(...)`, `setTotal(...)` | `confirm()`, `addLine(...)`, `cancel()` |
| Quy tắc nằm ở đâu? | Dễ bị lặp ở controller/service/UI | Tập trung quanh hành vi cần bảo vệ |
| Khi có thêm quy tắc? | Phải tìm nhiều chỗ gán field | Cập nhật các phương thức liên quan |
| Nguy cơ trạng thái sai? | Cao nếu quên kiểm tra | Giảm nếu mọi đường thay đổi được kiểm soát |

Một tên phương thức mô tả **hành động nghiệp vụ** thường truyền đạt ý định tốt hơn tên setter mô tả cách lưu dữ liệu.

## 2. Ví dụ Java hoàn chỉnh: để Order tự quản lý vòng đời

Giả sử có các quy tắc sau:

- Đơn hàng mới ở trạng thái `DRAFT`.
- Khi còn `DRAFT`, có thể thêm sản phẩm với SKU không rỗng, đơn giá dương và số lượng dương.
- Chỉ xác nhận được một đơn `DRAFT` có ít nhất một dòng hàng.
- Sau khi xác nhận, không thể thêm dòng hàng.
- Chỉ đơn `CONFIRMED` mới có thể bị hủy; sau khi hủy, không thể xác nhận lại.
- Tổng tiền được **tính từ các dòng hàng**, không cho code bên ngoài tự gán.

Đây là một mô hình minh họa độc lập, chưa tích hợp thanh toán, vận chuyển hoặc cơ sở dữ liệu. Chạy trên **Java 11+**; lưu toàn bộ vào tệp `EncapsulatedOrderDemo.java`.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class EncapsulatedOrderDemo {

    enum Status {
        DRAFT, CONFIRMED, CANCELLED
    }

    // Dòng hàng là một value object: không có setter.
    static final class OrderLine {
        private final String sku;
        private final BigDecimal unitPrice;
        private final int quantity;

        OrderLine(String sku, BigDecimal unitPrice, int quantity) {
            String checkedSku =
                    Objects.requireNonNull(sku, "sku").trim();
            Objects.requireNonNull(unitPrice, "unitPrice");

            if (checkedSku.isEmpty()) {
                throw new IllegalArgumentException("SKU không được rỗng");
            }
            if (unitPrice.signum() <= 0) {
                throw new IllegalArgumentException("Giá phải dương");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("Số lượng phải dương");
            }

            this.sku = checkedSku;
            this.unitPrice = unitPrice;
            this.quantity = quantity;
        }

        String getSku() {
            return sku;
        }

        BigDecimal subtotal() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    static final class Order {
        private final String id;
        private final List<OrderLine> lines = new ArrayList<>();
        private Status status = Status.DRAFT;

        Order(String id) {
            String checkedId =
                    Objects.requireNonNull(id, "id").trim();
            if (checkedId.isEmpty()) {
                throw new IllegalArgumentException("Mã đơn không được rỗng");
            }
            this.id = checkedId;
        }

        public String getId() {
            return id;
        }

        public Status getStatus() {
            return status;
        }

        public List<OrderLine> getLines() {
            // Bản sao không thể sửa cấu trúc; OrderLine cũng bất biến.
            return List.copyOf(lines);
        }

        public BigDecimal getTotal() {
            BigDecimal total = BigDecimal.ZERO;
            for (OrderLine line : lines) {
                total = total.add(line.subtotal());
            }
            return total;
        }

        public void addLine(String sku, BigDecimal price, int quantity) {
            requireDraft();
            // Kiểm tra xong trước khi cập nhật danh sách.
            OrderLine candidate = new OrderLine(sku, price, quantity);
            lines.add(candidate);
        }

        public void confirm() {
            requireDraft();
            if (lines.isEmpty()) {
                throw new IllegalStateException(
                        "Không thể xác nhận đơn hàng rỗng"
                );
            }
            status = Status.CONFIRMED;
        }

        public void cancel() {
            if (status != Status.CONFIRMED) {
                throw new IllegalStateException(
                        "Chỉ đơn đã xác nhận mới được hủy"
                );
            }
            status = Status.CANCELLED;
        }

        private void requireDraft() {
            if (status != Status.DRAFT) {
                throw new IllegalStateException(
                        "Chỉ được sửa đơn ở trạng thái DRAFT"
                );
            }
        }
    }

    public static void main(String[] args) {
        Order order = new Order("ORD-101");

        try {
            order.confirm();
        } catch (IllegalStateException ex) {
            System.out.println("Từ chối: " + ex.getMessage());
        }

        order.addLine("BOOK-01", new BigDecimal("80000"), 2);
        order.addLine("PEN-01", new BigDecimal("50000"), 1);

        System.out.println("Tổng tiền: "
                + order.getTotal().toPlainString());

        order.confirm();
        System.out.println("Trạng thái: " + order.getStatus());

        try {
            order.addLine("BOOK-02", new BigDecimal("90000"), 1);
        } catch (IllegalStateException ex) {
            System.out.println("Từ chối: " + ex.getMessage());
        }

        order.cancel();
        System.out.println("Sau hủy: " + order.getStatus());
        System.out.println("Số dòng hàng: " + order.getLines().size());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac EncapsulatedOrderDemo.java
java EncapsulatedOrderDemo
~~~

Kết quả:

~~~text
Từ chối: Không thể xác nhận đơn hàng rỗng
Tổng tiền: 210000
Trạng thái: CONFIRMED
Từ chối: Chỉ được sửa đơn ở trạng thái DRAFT
Sau hủy: CANCELLED
Số dòng hàng: 2
~~~

Điểm đáng chú ý: `Order` tự thực thi quy tắc ở đúng nơi thay đổi trạng thái. Code gọi **không cần biết** cần gán field `status` ra sao hoặc nên cập nhật `total` cùng lúc với `lines` như thế nào.

### Vì sao thiết kế này an toàn hơn?

**Không có `setStatus()`.** Người gọi chỉ thể hiện ý định `confirm()` hoặc `cancel()`; các trạng thái chuyển tiếp được kiểm tra.

**Không có `setTotal()`.** `getTotal()` tính từ dữ liệu nguồn, nên không có tình huống tổng đã được gán nhưng danh sách sản phẩm chưa thay đổi tương ứng.

**Không trả ra danh sách mutable nội bộ.** `getLines()` cung cấp snapshot cấu trúc dưới dạng `List.copyOf(lines)`. Nếu trả thẳng `lines`, code bên ngoài có thể gọi `clear()` để xóa sản phẩm khỏi một đơn đã xác nhận, vượt qua `requireDraft()`. Trong ví dụ, `OrderLine` cũng bất biến nên không thể lách quy tắc bằng cách sửa phần tử.

**Kiểm tra trước khi ghi.** `addLine()` tạo và kiểm tra `OrderLine` trước khi thêm vào danh sách; `confirm()` và `cancel()` chỉ gán `status` sau khi các điều kiện được thỏa mãn. Khi bị từ chối, thao tác không để lại cập nhật dở dang.

## 3. Theo dõi trạng thái bằng sơ đồ và bảng

Các bước chuyển trạng thái hợp lệ của `Order`:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT : new Order(...)
    DRAFT --> DRAFT : addLine(...)
    DRAFT --> CONFIRMED : confirm() khi có dòng hàng
    CONFIRMED --> CANCELLED : cancel()
~~~

Những chuyển trạng thái **không có mũi tên** (như `CANCELLED → CONFIRMED` hoặc `CONFIRMED → DRAFT`) không được API trong ví dụ cho phép.

| Trạng thái hiện tại | Lệnh gọi | Kết quả |
| --- | --- | --- |
| `DRAFT`, chưa có dòng hàng | `confirm()` | Ném `IllegalStateException`; vẫn `DRAFT` |
| `DRAFT`, có sản phẩm hợp lệ | `addLine(...)` | Thêm dòng hàng, vẫn `DRAFT` |
| `DRAFT`, có sản phẩm | `confirm()` | Chuyển `CONFIRMED` |
| `CONFIRMED` | `addLine(...)` | Bị từ chối; không thêm sản phẩm |
| `CONFIRMED` | `cancel()` | Chuyển `CANCELLED` |
| `CANCELLED` | `confirm()` hoặc `cancel()` | Bị từ chối |

**Invariant** (điều kiện cần luôn đúng với đối tượng ở trạng thái quan sát hợp lệ) của mô hình này bao gồm: mã đơn không rỗng; mọi `OrderLine` có SKU hợp lệ, giá và số lượng dương; danh sách không thể bị sửa trực tiếp từ code ngoài; trạng thái thuộc một trong ba giá trị enum; khi trạng thái là `CONFIRMED` hoặc `CANCELLED` thì đơn đã trải qua bước xác nhận với ít nhất một dòng hàng.

Một phương thức có hành vi tốt nên giữ invariant trước và sau mỗi thao tác thành công. Với thao tác thất bại, nên từ chối **trước khi thay đổi trạng thái** khi điều đó khả thi.

## 4. “Tell, Don't Ask”: yêu cầu đối tượng làm việc thay vì lấy dữ liệu để tự làm

Nguyên tắc **Tell, Don't Ask** khuyến khích gửi một yêu cầu nghiệp vụ tới đối tượng đang sở hữu dữ liệu, thay vì liên tục đọc trạng thái của nó rồi thao tác từ bên ngoài.

**Cách dễ phân tán quy tắc:**

~~~java
// Chỉ minh họa phong cách code: một kiểu Order khác có các setter này.
if (order.getStatus() == Status.DRAFT
        && !order.getLines().isEmpty()) {
    order.setStatus(Status.CONFIRMED);
}
~~~

**Cách thể hiện ý định:**

~~~java
order.confirm();
~~~

Phương thức `confirm()` chính là nơi định nghĩa các điều kiện và chuyển trạng thái. Khi quy tắc mới xuất hiện, ví dụ cần kiểm tra địa chỉ giao hàng trước khi xác nhận, hành vi xác nhận hoặc đối tượng cộng tác phù hợp có thể được mở rộng mà không phải tìm các lệnh `setStatus` trên khắp ứng dụng.

Điều này **không có nghĩa getter là xấu**. Getter rất hữu ích khi hiển thị, ghi log hoặc lập báo cáo:

~~~java
System.out.println(order.getStatus());
System.out.println(order.getTotal());
~~~

Khác biệt nằm ở **mục đích**: *đọc để trình bày* là hợp lý; *đọc toàn bộ trạng thái để quyết định rồi tự gán các field mang nghiệp vụ* thường là tín hiệu cần xem lại trách nhiệm.

## 5. Giao diện hành vi tốt nên giấu cái gì?

Một API của đối tượng nên bộc lộ **những thao tác có nghĩa với miền nghiệp vụ**, đồng thời che giấu các chi tiết có thể thay đổi.

| Thông tin / thao tác | Nên công khai? | Lý do |
| --- | --- | --- |
| `getStatus()` | Có thể | Người dùng giao diện cần biết trạng thái |
| `getTotal()` | Có thể | Hiển thị tổng tiền và đối soát |
| `addLine(...)` | Có | Nói rõ hành động thêm sản phẩm, cho phép kiểm soát |
| `confirm()`, `cancel()` | Có | Biểu đạt chuyển trạng thái theo nghiệp vụ |
| `setStatus(Status)` | Không trong ví dụ | Cho phép bỏ qua quy trình xác nhận/hủy |
| `setTotal(BigDecimal)` | Không | Có thể làm tổng tiền lệch khỏi dòng hàng |
| `getMutableLines()` trả `ArrayList` nội bộ | Không | Caller có thể sửa danh sách mà không qua quy tắc |
| Hàm trợ giúp `requireDraft()` | `private` | Là chi tiết thực thi quy tắc nội bộ |

Cũng cần tránh một thiết kế ngược lại: tạo phương thức như `setDataWithValidation()` chỉ đổi tên setter, trong khi bên ngoài vẫn quyết định toàn bộ luồng và trạng thái. Hãy đặt câu hỏi: **“Thao tác này đại diện cho hành động thực tế nào của đối tượng?”**

Với đối tượng phức tạp, không nhất thiết mỗi câu lệnh đều trở thành một phương thức công khai. Chỉ bộc lộ các hành vi có ích đối với bên sử dụng và giữ chi tiết nội bộ ở mức `private` thích hợp.

## 6. Phân định trách nhiệm giữa Entity và Service

Đóng gói hành vi **không có nghĩa nhồi mọi logic của ứng dụng vào một entity**. Cần phân biệt:

- **Entity / domain object**: bảo vệ trạng thái và quy tắc liên quan trực tiếp đến nó, ví dụ `Order.confirm()`, `Order.addLine()`, `Order.cancel()`.
- **Application service**: điều phối một use case, kết hợp repository, cổng thanh toán, dịch vụ vận chuyển hoặc gửi thông báo.
- **Infrastructure adapter**: thực hiện kết nối HTTP, database, message broker, v.v.

Ví dụ một luồng xác nhận đơn hàng **chỉ ở mức minh họa kiến trúc**:

~~~java
// Pseudocode: minh họa trách nhiệm, không phải đoạn chạy độc lập.
public void confirmOrder(String orderId) {
    Order order = repository.findById(orderId);

    order.confirm();            // Quy tắc của chính Order
    repository.save(order);     // Lưu trữ qua repository
    eventPublisher.publishOrderConfirmed(order.getId());
}
~~~

`Order` không cần biết cách kết nối database hay gửi email. `OrderService` (hoặc use-case service) không cần tự cài lại điều kiện “đơn hàng không rỗng và đang DRAFT” bằng cách đọc nhiều field của `Order`.

**Lưu ý về tính nhất quán:** đoạn pseudo trên chỉ để minh họa phân chia trách nhiệm. Trong hệ thống thực, lưu đơn và phát sự kiện có thể thất bại ở các thời điểm khác nhau; có thể cần transaction, transactional outbox, retry hoặc cơ chế thích hợp. Chuyển quy tắc vào entity **không tự giải quyết** toàn bộ vấn đề giao dịch và hệ thống phân tán.

Một dấu hiệu rõ ràng về vị trí logic:

| Logic cần đặt | Nơi thường phù hợp |
| --- | --- |
| “Chỉ đơn nháp mới được thêm hàng” | `Order` |
| “Không xác nhận đơn rỗng” | `Order` |
| “Số tiền một dòng = giá × số lượng” | `OrderLine` |
| “Tìm đơn trong database” | Repository |
| “Gọi ngân hàng để thu tiền” | Payment gateway / service |
| “Phối hợp xác nhận, lưu, phát sự kiện” | Application service |
| “Quy tắc liên quan nhiều entity, không thuộc riêng entity nào” | Domain service hoặc quy trình nghiệp vụ thích hợp |

Ranh giới này phụ thuộc miền nghiệp vụ; không phải một công thức bắt buộc cho mọi ứng dụng.

## 7. Tại sao dữ liệu cần được bảo vệ cả khi trả về?

Chỉ `private List<OrderLine> lines` **không đủ** nếu getter trả thẳng danh sách đó:

~~~java
class UnsafeOrder {
    private final List<String> skus = new ArrayList<>();

    List<String> getSkus() {
        return skus; // Trả về danh sách mutable bên trong
    }
}
~~~

Đoạn gọi có thể sửa trạng thái đối tượng mà không thông qua hành vi đã thiết kế:

~~~java
UnsafeOrder order = new UnsafeOrder();
order.getSkus().add("ITEM-001");
~~~

Các lựa chọn thường dùng:

| Cách cung cấp dữ liệu | Tác động |
| --- | --- |
| `return lines;` | Lộ collection mutable nếu `lines` là mutable |
| `return Collections.unmodifiableList(lines);` | View không thể sửa qua getter nhưng sẽ phản ánh các thay đổi sau đó của danh sách nội bộ |
| `return List.copyOf(lines);` | Snapshot cấu trúc không thể sửa, nhưng **không deep copy** phần tử |
| Trả DTO/value object bất biến | Có thể bảo vệ cả trạng thái phần tử tùy thiết kế |

Trong `EncapsulatedOrderDemo`, `OrderLine` có field `private final` chứa `String`, `BigDecimal`, `int` (đều không có nội dung mutable có thể bị lộ) và không có setter. Do đó, kết hợp với `List.copyOf(lines)` là đủ cho yêu cầu bảo vệ danh sách trong ví dụ. Nếu phần tử chứa `List` hay `Date` mutable, cần tiếp tục xét defensive copy ở cấp sâu hơn.

## 8. Kiểm thử hành vi thay vì chỉ kiểm tra getter/setter

Một bài test tốt nên diễn đạt **luật nghiệp vụ**, bao gồm kết quả khi thao tác bị từ chối.

Ví dụ sử dụng **JUnit 5**, đặt test ở cùng package với `EncapsulatedOrderDemo`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderBehaviorTest {

    @Test
    void cannotConfirmEmptyOrder() {
        EncapsulatedOrderDemo.Order order =
                new EncapsulatedOrderDemo.Order("ORD-101");

        assertThrows(IllegalStateException.class, order::confirm);
        assertEquals(EncapsulatedOrderDemo.Status.DRAFT,
                order.getStatus());
    }

    @Test
    void confirmedOrderCannotBeEdited() {
        EncapsulatedOrderDemo.Order order =
                new EncapsulatedOrderDemo.Order("ORD-102");

        order.addLine("BOOK", new BigDecimal("100000"), 2);
        order.confirm();

        assertThrows(IllegalStateException.class,
                () -> order.addLine("PEN", BigDecimal.TEN, 1));

        assertEquals(new BigDecimal("200000"), order.getTotal());
        assertEquals(1, order.getLines().size());
    }

    @Test
    void callerCannotModifyInternalLines() {
        EncapsulatedOrderDemo.Order order =
                new EncapsulatedOrderDemo.Order("ORD-103");
        order.addLine("BOOK", BigDecimal.TEN, 1);

        assertThrows(UnsupportedOperationException.class,
                () -> order.getLines().clear());
        assertEquals(1, order.getLines().size());
    }

    @Test
    void cannotConfirmAgainAfterCancellation() {
        EncapsulatedOrderDemo.Order order =
                new EncapsulatedOrderDemo.Order("ORD-104");

        order.addLine("BOOK", BigDecimal.TEN, 1);
        order.confirm();
        order.cancel();

        assertThrows(IllegalStateException.class, order::confirm);
        assertEquals(EncapsulatedOrderDemo.Status.CANCELLED,
                order.getStatus());
    }
}
~~~

Ví dụ test cần dependency và test runner JUnit Jupiter phù hợp; chương trình `EncapsulatedOrderDemo.java` ở phần 2 **chạy độc lập** với thư viện chuẩn Java.

Các test này không cố chứng minh setter hoạt động; chúng bảo đảm rằng **đối tượng từ chối những hành vi không hợp lệ** và vẫn giữ trạng thái đúng sau khi từ chối. Đây chính là giá trị cần bảo vệ khi refactor.

## 9. Khi nào mô hình giàu hành vi là lựa chọn tốt?

Ưu tiên đưa hành vi về đối tượng khi:

- Một trường dữ liệu có **quy tắc chuyển trạng thái** hoặc ràng buộc kết hợp với các trường khác.
- Nhiều nơi đang lặp lại cùng chuỗi `get... → if... → set...`.
- Việc cập nhật sai có thể tạo dữ liệu nghiệp vụ không hợp lệ.
- Đối tượng có các hành động tự nhiên như `approve`, `reserve`, `withdraw`, `activate`, `close`.
- Bạn muốn kiểm thử nghiệp vụ qua API rõ ràng, không phụ thuộc trực tiếp cấu trúc field.

Không nhất thiết làm như vậy cho mọi đối tượng:

- **DTO/request/response** chủ yếu dùng để truyền hoặc hiển thị dữ liệu có thể chỉ cần constructor, getter, mapping/validation ở ranh giới.
- **Value object bất biến** có thể tập trung vào việc kiểm tra ở constructor và những phép biến đổi trả về object mới.
- **Tác vụ tích hợp hoặc quy trình xuyên nhiều đối tượng** thường cần service để điều phối.
- Những kiểu dữ liệu chỉ có cấu hình đơn giản và không có invariant phức tạp không cần bị ép thành state machine.

Một ví dụ tốt về thay đổi từ thiết kế hướng dữ liệu sang hướng hành vi là:

| Cách suy nghĩ thiên về field | Cách suy nghĩ thiên về hành động |
| --- | --- |
| “Cho phép sửa `status`” | “Cho phép xác nhận/hủy trong điều kiện nào?” |
| “Cần setter để sửa `balance`” | “Cho phép nạp, rút, chuyển tiền bằng luật gì?” |
| “Thay `reserved` từ 2 thành 5” | “Yêu cầu giữ thêm 3 đơn vị có hợp lệ không?” |
| “Sửa `isActive`” | “Ai được kích hoạt hoặc vô hiệu hóa và khi nào?” |
| “Tổng tiền là số được lưu” | “Tổng tiền được hình thành từ dữ liệu nguồn nào?” |

## 10. Các lỗi dễ mắc khi chuyển sang đóng gói hành vi

**1. Chỉ đổi tên setter.** `updateStatus(CONFIRMED)` vẫn cho caller quyết định trạng thái trực tiếp. Hãy thiết kế `confirm()` mang điều kiện cụ thể.

**2. Kiểm tra ở controller nhưng entity vẫn cho sửa tùy ý.** Một API khác, batch job hoặc test có thể bỏ qua controller. Quy tắc cốt lõi của entity cần nằm tại API thay đổi trạng thái của entity (trừ khi có lý do kiến trúc rõ ràng).

**3. Phơi bày collection mutable.** Getter trả tham chiếu tới collection nội bộ tạo một con đường thay đổi không qua các hành vi.

**4. Cập nhật một nửa rồi mới ném lỗi.** Validate tất cả điều kiện và dữ liệu cần thiết trước khi gán nếu có thể; đối với giao dịch nhiều đối tượng cần phương án nhất quán phù hợp.

**5. Dồn mọi logic vào một lớp cực lớn.** Chia trách nhiệm theo dữ liệu mà đối tượng thực sự sở hữu và để service điều phối tương tác bên ngoài.

**6. Cho rằng đóng gói tự bảo đảm an toàn đồng thời.** Nếu nhiều thread đồng thời gọi `addLine()` hoặc `confirm()` trên cùng một `Order`, bản mẫu dùng `ArrayList` và field thường ở đây **không thread-safe**. Cần phân định ranh giới request/aggregate và dùng synchronization, transaction, optimistic locking hoặc cơ chế tương ứng trong hệ thống thực.

## 11. Tự luyện tập

**Bài 1.** Một lớp `BankAccount` có `getBalance()` và `setBalance(BigDecimal)`. Hãy đề xuất API biểu đạt nghiệp vụ tốt hơn.

**Gợi ý:** `deposit(amount)`, `withdraw(amount)`, có thể `transferTo(target, amount)` nếu thiết kế bảo vệ được cả hai tài khoản. Đặt quy tắc số tiền dương, đủ số dư, hạn mức và tính nhất quán ở các phương thức thích hợp; chuyển giữa hai tài khoản có thể cần transaction/locking.

**Bài 2.** Khi thêm chức năng “không hủy đơn đã giao”, nên kiểm tra ở đâu?

**Gợi ý:** Hành vi hủy trên đối tượng `Order` (hoặc mô hình vòng đời/phân quyền liên quan) phải biết trạng thái vận chuyển cần thiết. Tránh chỉ kiểm tra ở màn hình rồi vẫn để `setStatus(CANCELLED)` từ nơi khác.

**Bài 3.** Có nên xóa mọi getter trên `Order` để tuân theo Tell, Don't Ask?

**Đáp án:** Không. Đọc thông tin để hiển thị, truy vấn, báo cáo là nhu cầu hợp lý. Cảnh báo chỉ xuất hiện khi bên ngoài liên tục đọc trạng thái để **ra quyết định thay đối tượng** rồi trực tiếp thay nhiều field.

**Bài 4.** Nếu `Order.getLines()` trả `List.copyOf(lines)` nhưng từng `OrderLine` lại có `setPrice()`, đối tượng có được bảo vệ hoàn toàn chưa?

**Đáp án:** Chưa. Collection không thể sửa cấu trúc, nhưng từng phần tử mutable vẫn có thể bị người gọi cập nhật qua tham chiếu. Cần thiết kế `OrderLine` bất biến, defensive copy phù hợp hoặc chỉ trả dữ liệu quan sát an toàn.

**Bài 5.** Khi xác nhận đơn hàng cần thanh toán qua API và lưu vào database, có nên gọi HTTP trực tiếp bên trong `Order.confirm()`?

**Gợi ý:** Thường không. Hãy để `Order` quyết định tính hợp lệ của chuyển trạng thái; application service điều phối cổng thanh toán, lưu dữ liệu và phát sự kiện. Thiết kế phải xét trạng thái khi một phần thao tác ngoài hệ thống thất bại.

Điểm cần nhớ khi thiết kế lớp: **“Đối tượng này chịu trách nhiệm bảo vệ điều gì, và người dùng cần yêu cầu nó thực hiện những hành động nào?”** Khi API mô tả được hành động thay vì chỉ phơi ra dữ liệu, lớp thường dễ dùng đúng hơn, khó bị sửa sai hơn và dễ kiểm thử quy tắc nghiệp vụ hơn.