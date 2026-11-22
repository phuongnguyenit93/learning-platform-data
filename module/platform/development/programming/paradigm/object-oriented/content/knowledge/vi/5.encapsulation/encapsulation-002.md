# Điều kiện bất biến của đối tượng trong Java OOP

Trong lập trình hướng đối tượng, một đối tượng có thể thay đổi trạng thái qua nhiều lời gọi phương thức. Tuy nhiên, **không phải mọi tổ hợp giá trị của các thuộc tính đều hợp lệ**. Ví dụ: số lượng hàng đã giữ để giao không thể âm hoặc lớn hơn tổng hàng hiện có. Những quy tắc phải luôn được bảo đảm tại các thời điểm đối tượng có thể được quan sát và sử dụng hợp lệ được gọi là **điều kiện bất biến của đối tượng** (*object invariants*).

Thiết kế lớp tốt không chỉ là khai báo `private` cho field; lớp cần **kiểm soát quá trình hình thành và thay đổi trạng thái** để các điều kiện bất biến luôn được duy trì.

## 1. Điều kiện bất biến là gì?

**Object invariant** là một tập điều kiện logic mô tả trạng thái hợp lệ của **một instance**, phải đúng sau khi khởi tạo thành công và sau mỗi thao tác công khai hoàn thành bình thường. Với các phương thức có thể thất bại, thiết kế vững chắc thường yêu cầu trạng thái vẫn hợp lệ và, khi phù hợp, không thay đổi nếu thao tác bị từ chối.

Ví dụ với sản phẩm trong kho:

- `sku` không được `null` hoặc rỗng.
- `unitPrice` phải lớn hơn 0.
- `onHand` (hàng vật lý còn trong kho) không âm.
- `reserved` (hàng đã giữ cho các đơn đang xử lý) không âm và **không vượt quá** `onHand`.
- `available` (hàng còn có thể đặt) luôn bằng `onHand - reserved`, nên phải không âm.

Diễn đạt toán học:

\[
\text{onHand} \ge 0,\quad 0 \le \text{reserved} \le \text{onHand}
\]

\[
\text{available} = \text{onHand} - \text{reserved} \ge 0
\]

Các điều kiện liên quan giữa **nhiều field** (như `reserved <= onHand`) thường là lý do quan trọng để **không cung cấp setter tùy ý cho từng field**.

### Phân biệt những khái niệm dễ nhầm

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| **Invariant** | Trạng thái nào của đối tượng là hợp lệ? | `0 <= reserved <= onHand` |
| **Precondition** (tiền điều kiện) | Điều gì phải đúng trước khi gọi thao tác? | `quantity > 0`, đủ hàng còn bán được |
| **Postcondition** (hậu điều kiện) | Sau thao tác thành công, kết quả phải thế nào? | Đặt giữ 2 sản phẩm làm `reserved` tăng 2 |
| **Immutability** (tính không thể thay đổi) | Trạng thái quan sát được có bị thay đổi sau khi tạo không? | `String`, `LocalDate`, value object bất biến |
| **Encapsulation** (đóng gói) | Ai được quyền đọc/sửa và bằng cách nào? | Field `private`, cập nhật qua `reserve()` |

**Invariant không đồng nghĩa với immutable.** Một đối tượng có thể *mutable* nhưng vẫn duy trì invariant qua mọi thao tác hợp lệ. Ngược lại, đối tượng immutable cũng cần được kiểm tra để **trạng thái ban đầu** của nó hợp lệ.

## 2. Vì sao setter độc lập có thể phá vỡ invariant?

Giả sử một lớp cung cấp hai setter:

~~~java
class BadStock {
    private int onHand;
    private int reserved;

    public void setOnHand(int onHand) {
        if (onHand < 0) {
            throw new IllegalArgumentException("Âm");
        }
        this.onHand = onHand;
    }

    public void setReserved(int reserved) {
        if (reserved < 0) {
            throw new IllegalArgumentException("Âm");
        }
        this.reserved = reserved;
    }
}
~~~

Mỗi setter chỉ kiểm tra field của chính mình, nên vẫn cho phép:

~~~java
BadStock stock = new BadStock();
stock.setOnHand(2);
stock.setReserved(5); // Hai giá trị đều không âm, nhưng trạng thái sai!
~~~

Điều kiện `reserved <= onHand` bị phá vỡ. Chỉ thêm kiểm tra cho từng field là **chưa đủ**; những thay đổi có quan hệ phải được điều phối cùng nhau. Nếu kiểm tra `reserved <= onHand` bên trong từng setter, còn cần nghĩ về **thứ tự cập nhật** khi đổi từ một trạng thái hợp lệ sang trạng thái hợp lệ khác, đặc biệt trong chương trình đồng thời.

Hướng thiết kế tốt hơn là thể hiện các **hành vi nghiệp vụ** có ý nghĩa: `reserve`, `release`, `ship` và `restock`. Mỗi hành vi kiểm tra điều kiện phù hợp và cập nhật trạng thái một cách nhất quán.

## 3. Ví dụ Java hoàn chỉnh: đối tượng kho luôn hợp lệ

Ví dụ sau chạy với **Java 11+**. Tạo tệp `InvariantDemo.java`.

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public class InvariantDemo {

    static final class StockItem {
        private final String sku;
        private final BigDecimal unitPrice;
        private int onHand;
        private int reserved;

        public StockItem(String sku, BigDecimal unitPrice,
                         int initialOnHand) {
            String normalizedSku =
                    Objects.requireNonNull(sku, "sku").trim();
            Objects.requireNonNull(unitPrice, "unitPrice");

            if (normalizedSku.isEmpty()) {
                throw new IllegalArgumentException("SKU không được rỗng");
            }
            if (unitPrice.signum() <= 0) {
                throw new IllegalArgumentException("Giá phải lớn hơn 0");
            }
            if (initialOnHand < 0) {
                throw new IllegalArgumentException("Tồn kho không được âm");
            }

            this.sku = normalizedSku;
            this.unitPrice = unitPrice;
            this.onHand = initialOnHand;
            this.reserved = 0;
        }

        public String getSku() {
            return sku;
        }

        public BigDecimal getUnitPrice() {
            return unitPrice;
        }

        public int getOnHand() {
            return onHand;
        }

        public int getReserved() {
            return reserved;
        }

        // Dữ liệu dẫn xuất: không lưu một field available riêng.
        public int getAvailable() {
            return onHand - reserved;
        }

        public void reserve(int quantity) {
            requirePositive(quantity);
            if (quantity > getAvailable()) {
                throw new IllegalStateException("Không đủ hàng để giữ");
            }
            reserved += quantity;
        }

        public void release(int quantity) {
            requirePositive(quantity);
            if (quantity > reserved) {
                throw new IllegalStateException("Không thể trả quá số đã giữ");
            }
            reserved -= quantity;
        }

        public void ship(int quantity) {
            requirePositive(quantity);
            if (quantity > reserved) {
                throw new IllegalStateException("Chưa giữ đủ hàng để giao");
            }
            // Hàng được giao rời kho và hết trạng thái giữ chỗ.
            reserved -= quantity;
            onHand -= quantity;
        }

        public void restock(int quantity) {
            requirePositive(quantity);
            // Nếu overflow, Math.addExact ném ngoại lệ trước khi gán.
            int nextOnHand = Math.addExact(onHand, quantity);
            onHand = nextOnHand;
        }

        public String snapshot() {
            return "onHand=" + onHand
                    + ", reserved=" + reserved
                    + ", available=" + getAvailable();
        }

        private static void requirePositive(int quantity) {
            if (quantity <= 0) {
                throw new IllegalArgumentException("Số lượng phải dương");
            }
        }
    }

    public static void main(String[] args) {
        StockItem item = new StockItem(
                "BOOK-01", new BigDecimal("120000"), 10
        );

        System.out.println("Ban đầu: " + item.snapshot());

        item.reserve(4);
        System.out.println("Giữ 4: " + item.snapshot());

        try {
            item.reserve(7); // Còn bán được 6, thao tác thất bại.
        } catch (IllegalStateException ex) {
            System.out.println("Từ chối: " + ex.getMessage());
        }
        System.out.println("Sau lỗi: " + item.snapshot());

        item.ship(3);
        System.out.println("Giao 3: " + item.snapshot());

        item.release(1);
        System.out.println("Hủy giữ 1: " + item.snapshot());

        item.restock(5);
        System.out.println("Nhập 5: " + item.snapshot());
    }
}
~~~

Chạy:

~~~bash
javac InvariantDemo.java
java InvariantDemo
~~~

Kết quả:

~~~text
Ban đầu: onHand=10, reserved=0, available=10
Giữ 4: onHand=10, reserved=4, available=6
Từ chối: Không đủ hàng để giữ
Sau lỗi: onHand=10, reserved=4, available=6
Giao 3: onHand=7, reserved=1, available=6
Hủy giữ 1: onHand=7, reserved=0, available=7
Nhập 5: onHand=12, reserved=0, available=12
~~~

### Tại sao từng phương thức giữ được invariant?

| Hành vi | Điều kiện trước khi thay đổi | Công thức cập nhật | Vì sao vẫn hợp lệ? |
| --- | --- | --- | --- |
| Tạo đối tượng | `sku` hợp lệ, giá dương, hàng đầu kỳ ≥ 0 | `reserved = 0` | `0 <= 0 <= onHand` |
| `reserve(q)` | `q > 0` và `q <= onHand - reserved` | `reserved += q` | Giá trị mới của `reserved` không vượt `onHand` |
| `release(q)` | `q > 0` và `q <= reserved` | `reserved -= q` | `reserved` mới không âm |
| `ship(q)` | `q > 0` và `q <= reserved` | `reserved -= q; onHand -= q` | Cả hai giảm cùng lượng, `onHand` vẫn ≥ `reserved` |
| `restock(q)` | `q > 0` và tổng không tràn số nguyên | `onHand += q` | Chỉ tăng tổng hàng, không giảm số còn bán được |

Mỗi phép cập nhật đều **xuất phát từ một trạng thái hợp lệ**. Nếu `reserve(7)` bị từ chối khi còn 6 hàng có thể đặt, phương thức ném ngoại lệ **trước bất kỳ thay đổi nào** nên trạng thái cũ được giữ nguyên.

Đặc biệt, `Math.addExact` giúp tránh overflow khi thêm hàng vào `int`. Nếu cộng vượt `Integer.MAX_VALUE`, một phép cộng `int` thông thường có thể cho kết quả âm; `addExact` ném `ArithmeticException` trước khi field bị cập nhật. Đây cũng là bảo vệ invariant.

## 4. Nhìn invariant dưới dạng luồng kiểm tra

Đối với thao tác `reserve(q)`:

~~~mermaid
flowchart TD
    A["Gọi reserve(q)"] --> B{"q > 0?"}
    B -->|Không| E["IllegalArgumentException\nKhông đổi trạng thái"]
    B -->|Có| C{"q <= available?"}
    C -->|Không| F["IllegalStateException\nKhông đổi trạng thái"]
    C -->|Có| D["reserved = reserved + q"]
    D --> G["Trạng thái hợp lệ\n0 <= reserved <= onHand"]
~~~

Luồng lý tưởng là **kiểm tra → tính kết quả → cập nhật**. Khi một phương thức phải thay đổi nhiều field, hãy tránh để ngoại lệ có thể xảy ra *giữa các phép cập nhật* khiến đối tượng tồn tại ở trạng thái dở dang.

Ví dụ với phép chuyển số tiền giữa hai ví, không nên trừ ví A trước rồi mới kiểm tra có thể cộng vào ví B hay không. Với xử lý đơn luồng trong bộ nhớ, có thể **kiểm tra cả hai điều kiện**, tính trước số dư mới, rồi mới gán. Với cập nhật qua database, nhiều service hoặc xử lý đồng thời, cần transaction/locking hoặc cơ chế phù hợp để bảo đảm cập nhật nhóm.

## 5. Invariant, constructor và vòng đời đối tượng

Một invariant không tự nhiên đúng chỉ vì các field được khai báo `private`. Lớp phải chủ động thiết lập nó khi khởi tạo.

~~~java
public final class TemperatureRange {
    private final int min;
    private final int max;

    public TemperatureRange(int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min phải <= max");
        }
        this.min = min;
        this.max = max;
    }

    public int getMin() { return min; }
    public int getMax() { return max; }
}
~~~

Ở đây invariant là `min <= max`. Constructor kiểm tra trước khi cung cấp một đối tượng được khởi tạo thành công. Việc hai field đều `final` **không tự động kiểm chứng** mối quan hệ giữa chúng.

Nếu constructor nhận những collection hay đối tượng mutable, nó cũng phải tránh để bên ngoài thay đổi “lén” trạng thái sau khi xây dựng.

~~~java
import java.util.List;
import java.util.Objects;

public final class StudyPlan {
    private final List<String> topics;

    public StudyPlan(List<String> topics) {
        Objects.requireNonNull(topics, "topics");
        if (topics.isEmpty()) {
            throw new IllegalArgumentException("Phải có ít nhất một chủ đề");
        }
        for (String topic : topics) {
            if (topic == null || topic.isBlank()) {
                throw new IllegalArgumentException("Chủ đề không hợp lệ");
            }
        }
        this.topics = List.copyOf(topics);
    }

    public List<String> getTopics() {
        return topics;
    }
}
~~~

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> external = new ArrayList<>(List.of("OOP"));
StudyPlan plan = new StudyPlan(external);

external.clear();                    // Không làm rỗng plan
System.out.println(plan.getTopics()); // [OOP]

// Ném UnsupportedOperationException:
plan.getTopics().clear();
~~~

Invariant của `StudyPlan`: danh sách chủ đề không rỗng và mỗi phần tử là chuỗi hợp lệ. `List.copyOf` tạo danh sách không thể sửa, tách khỏi những thay đổi sau đó của collection nguồn. Vì các phần tử là `String` bất biến, đây là lựa chọn an toàn cho ví dụ. Với danh sách chứa **phần tử mutable**, `List.copyOf` chỉ sao chép **tham chiếu đến phần tử**, không bảo vệ toàn bộ object graph; cần bản sao sâu phù hợp hoặc các value object bất biến.

**Tránh làm lộ `this` trong constructor**, ví dụ đăng ký đối tượng đang xây dựng vào một listener toàn cục trước khi mọi field/invariant được thiết lập. Thành phần khác có thể quan sát instance chưa hoàn tất, đặc biệt trong chương trình nhiều luồng.

## 6. Khi đối tượng thay đổi, điều kiện vẫn phải đúng

Trở lại `StockItem`, xét hai trạng thái:

- Trước `reserve(4)`: `onHand=10`, `reserved=0`, `available=10`.
- Sau `reserve(4)`: `onHand=10`, `reserved=4`, `available=6`.

**Cả hai trạng thái đều hợp lệ.** Đây là điểm phân biệt rõ với immutable object: giá trị của field thay đổi nhưng invariant được bảo toàn.

Một setter đặt số hàng đã giữ một cách tùy ý sẽ phá vỡ ranh giới này. Thay vì:

~~~java
// Thiết kế dễ bị dùng sai:
public void setReserved(int newReserved) {
    reserved = newReserved;
}
~~~

hãy cho phép thao tác theo ý nghĩa của miền nghiệp vụ:

~~~java
item.reserve(4);
item.release(1);
item.ship(3);
~~~

Một API có ý nghĩa thường khiến **trạng thái không hợp lệ khó biểu diễn và khó đạt tới hơn**. Cách đặt tên phương thức cũng giúp đọc code rõ hơn: “giao 3 đơn vị đã giữ” chính xác hơn “đặt reserved thành 1 và onHand thành 7”.

### Có nên gọi `checkInvariant()` sau mọi phương thức?

Có thể dùng một hàm nội bộ để phát hiện sai sót trong quá trình phát triển:

~~~java
private void checkInvariant() {
    if (onHand < 0 || reserved < 0 || reserved > onHand) {
        throw new IllegalStateException("Vi phạm invariant của kho");
    }
}
~~~

Nhưng hàm kiểm tra **không thay thế** thiết kế đúng. Nếu code đã ghi một phần trạng thái sai rồi mới ném ngoại lệ, kiểm tra ở cuối phương thức sẽ phát hiện vi phạm nhưng **không tự khôi phục** dữ liệu. Ưu tiên kiểm tra điều kiện và tính giá trị mới **trước khi ghi**.

Lệnh `assert` của Java cũng không nên là cơ chế duy nhất xác thực dữ liệu nghiệp vụ: các assertion thường bị tắt nếu chương trình không chạy với tùy chọn `-ea`. Dữ liệu đầu vào sai nên bị từ chối qua logic kiểm tra rõ ràng, thường với `IllegalArgumentException` hoặc ngoại lệ miền nghiệp vụ phù hợp.

## 7. Ngoại lệ, thay đổi từng phần và tính nguyên tử

Một phương thức tốt thường hướng tới nguyên tắc: **thành công thì chuyển sang trạng thái hợp lệ mới; thất bại thì đối tượng vẫn hợp lệ**. Đối với nhiều thao tác, ta còn mong **thất bại không làm thay đổi trạng thái** (*strong exception guarantee*), nhưng không phải API nào cũng bảo đảm mức này.

Ví dụ sai:

~~~java
public void unsafeReserve(int quantity) {
    reserved += quantity; // Đã thay đổi!
    if (reserved > onHand) {
        throw new IllegalStateException("Không đủ hàng");
    }
}
~~~

Nếu ban đầu `onHand=10, reserved=4`, gọi `unsafeReserve(7)` khiến `reserved=11`, rồi ném ngoại lệ; invariant đã bị phá vỡ.

Cách đúng:

~~~java
public void safeReserve(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("Số lượng phải dương");
    }
    if (quantity > onHand - reserved) {
        throw new IllegalStateException("Không đủ hàng");
    }
    reserved += quantity;
}
~~~

Tại thời điểm từ chối, chưa field nào bị sửa. Điều này rất quan trọng với service có nhiều bước, bởi **ném exception không tự động hoàn tác những phép gán Java đã thực hiện**.

Cần phân biệt ba phạm vi:

| Phạm vi | Biện pháp thường dùng | Điều cần nhớ |
| --- | --- | --- |
| Một đối tượng trong một luồng | Guard condition, tính trước, gán hợp lệ | Có thể chứng minh invariant theo từng phương thức |
| Nhiều luồng cùng dùng một đối tượng | Khóa/synchronization, cấu trúc dữ liệu đồng thời hoặc mô hình immutable | Kiểm tra và cập nhật phải được phối hợp như một thao tác |
| Nhiều bảng/bản ghi hoặc hệ thống | Transaction, constraint, versioning/locking, idempotency, xử lý bù trừ | Kiểm tra riêng trong Java không đủ bảo đảm trạng thái dữ liệu chung |

## 8. Invariant và vấn đề đồng thời

Đoạn `StockItem` chính phía trên cố ý minh họa logic OOP trong **môi trường đơn luồng**. Nếu nhiều thread cùng gọi `reserve`, chúng có thể đồng thời nhìn thấy cùng số `available`, khiến điều kiện được kiểm tra trên trạng thái cũ rồi đều cập nhật.

Ví dụ: còn 1 sản phẩm, hai luồng đều muốn giữ 1. Nếu mỗi luồng độc lập đọc `available=1` trước khi ghi, quyết định “đủ hàng” có thể được đưa ra hai lần. `private` hoặc `final` **không tự tạo tính an toàn luồng**.

Trong một đối tượng Java dùng chung, có thể bảo vệ toàn bộ thao tác đọc/ghi với cùng một khóa, chẳng hạn:

~~~java
public synchronized void reserve(int quantity) {
    requirePositive(quantity);
    if (quantity > getAvailable()) {
        throw new IllegalStateException("Không đủ hàng");
    }
    reserved += quantity;
}

public synchronized int getAvailable() {
    return onHand - reserved;
}
~~~

Đây chỉ là hai phương thức **minh họa** của cùng lớp `StockItem`. Để thread-safe hoàn chỉnh, **mọi đường đọc/ghi trạng thái chia sẻ** (bao gồm `release`, `ship`, `restock`, `getOnHand`, `getReserved` và snapshot có nhiều field) cũng phải tuân thủ chiến lược đồng bộ nhất quán. Với truy cập qua database hoặc nhiều instance server, `synchronized` trong một JVM không đủ; cần cơ chế điều phối tại nguồn dữ liệu.

Một invariant có thể đúng ở đầu và cuối phương thức nhưng tạm thời không đúng giữa các câu lệnh. Nếu code khác có thể quan sát trạng thái trung gian, đó vẫn là lỗi thiết kế. Tránh làm lộ trạng thái trung gian, gọi callback ra bên ngoài trong lúc đang cập nhật, hoặc nhả khóa giữa chừng mà chưa khôi phục invariant.

## 9. Kiểm thử invariant theo biên và sau thất bại

Không chỉ kiểm thử nhánh thành công: các ca vượt giới hạn, giá trị âm, bằng 0, và cập nhật bị từ chối thường là nơi lộ bug. Ví dụ với **JUnit 5** (lớp `StockItem` của chương trình phía trên):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class StockItemTest {

    @Test
    void reserveCannotExceedAvailableAndKeepsStateOnFailure() {
        InvariantDemo.StockItem item =
                new InvariantDemo.StockItem(
                        "BOOK-01", new BigDecimal("120000"), 5
                );
        item.reserve(3);

        assertThrows(IllegalStateException.class, () -> item.reserve(3));

        assertEquals(5, item.getOnHand());
        assertEquals(3, item.getReserved());
        assertEquals(2, item.getAvailable());
    }

    @Test
    void shipNeverMakesStockNegative() {
        InvariantDemo.StockItem item =
                new InvariantDemo.StockItem(
                        "BOOK-01", new BigDecimal("120000"), 2
                );
        item.reserve(2);
        item.ship(2);

        assertEquals(0, item.getOnHand());
        assertEquals(0, item.getReserved());
        assertEquals(0, item.getAvailable());

        assertThrows(IllegalStateException.class, () -> item.ship(1));
    }

    @Test
    void constructorRejectsInvalidInitialState() {
        assertThrows(IllegalArgumentException.class, () ->
                new InvariantDemo.StockItem(
                        "BOOK-01", BigDecimal.ONE, -1
                ));
        assertThrows(IllegalArgumentException.class, () ->
                new InvariantDemo.StockItem(
                        "   ", BigDecimal.ONE, 1
                ));
    }

    @Test
    void overflowDoesNotCorruptState() {
        InvariantDemo.StockItem item =
                new InvariantDemo.StockItem(
                        "BOOK-01", BigDecimal.ONE, Integer.MAX_VALUE
                );
        assertThrows(ArithmeticException.class, () -> item.restock(1));
        assertEquals(Integer.MAX_VALUE, item.getOnHand());
        assertEquals(0, item.getReserved());
    }
}
~~~

Lưu ý: file test yêu cầu dependency JUnit Jupiter/Test runner tương ứng. Mã `InvariantDemo.java` ở phần 3 **không phụ thuộc JUnit** và chạy độc lập bằng `javac`/`java`. Trong dự án thực tế, có thể dùng **property-based testing** để sinh nhiều chuỗi thao tác `reserve → release → ship → restock` và khẳng định sau mỗi thao tác hợp lệ rằng `0 <= reserved <= onHand`.

## 10. Các lỗi thiết kế phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ kiểm tra từng field riêng lẻ | Bỏ sót quan hệ giữa các field | Viết invariant của **toàn bộ đối tượng** trước khi thiết kế API |
| Cho setter công khai không ràng buộc | Caller tạo trạng thái sai | Dùng thao tác có ý nghĩa nghiệp vụ với guard |
| Kiểm tra sau khi đã ghi field | Ngoại lệ để lại trạng thái hỏng | Validate và tính trước, sau đó mới cập nhật |
| Xem `final` đồng nghĩa “mọi thứ hợp lệ” | Quan hệ logic ban đầu vẫn có thể sai | Constructor phải xác thực |
| Trả mutable collection nội bộ | Caller vượt qua quy tắc của lớp | Defensive copy, immutable view/value object khi phù hợp |
| Dùng `assert` thay kiểm tra input | Kiểm tra có thể không chạy | Dùng exception/validation trong runtime bình thường |
| Chỉ kiểm thử ca hợp lệ | Không phát hiện lỗi tại giới hạn | Kiểm thử biên, ngoại lệ, trạng thái sau thất bại |
| Bỏ qua chia sẻ giữa các thread | Race condition phá invariant | Đồng bộ trọn thao tác hoặc dùng transaction đúng phạm vi |

## 11. Câu hỏi luyện tập

**1.** Với `onHand=8, reserved=5`, `reserve(3)` có được phép không? Sau thành công, các giá trị là gì?

**Đáp án:** Có vì `available = 8 - 5 = 3`. Sau đó `onHand=8, reserved=8, available=0`: invariant vẫn đúng tại biên.

**2.** Nếu đang `onHand=8, reserved=5`, gọi `ship(6)` nên xảy ra điều gì?

**Đáp án:** Bị từ chối vì chỉ 5 đơn vị đang được giữ. Trạng thái nên không đổi, không trừ `onHand` trước.

**3.** `private final List<OrderLine> lines` có bảo đảm đối tượng chứa danh sách bất biến không?

**Đáp án:** Không. `final` chỉ ngăn gán lại tham chiếu field. Danh sách và từng `OrderLine` có thể mutable; cần kiểm soát mọi đường sửa hoặc dùng bản sao/vật chứa/phần tử bất biến.

**4.** Vì sao một đối tượng mutable vẫn có thể duy trì invariant?

**Đáp án:** Invariant ràng buộc **tập trạng thái được phép**, chứ không cấm chuyển trạng thái. Phương thức được thiết kế để mọi lần chuyển trạng thái thành công đều kết thúc ở một trạng thái hợp lệ.

**5.** Có cần khóa nếu hệ thống dùng nhiều luồng cùng đặt một món hàng không?

**Đáp án:** Cần một chiến lược phối hợp các thao tác kiểm tra/cập nhật: khóa, xử lý tuần tự, atomic/transaction hoặc cơ chế nhất quán tương ứng với nơi lưu trạng thái. Nếu trạng thái được lưu trong database có nhiều instance ứng dụng, chỉ khóa một object trong một JVM là không đủ.

Khi đọc hoặc viết một lớp Java, hãy tự hỏi: **“Điều kiện nào phải đúng đối với mọi instance hợp lệ? Constructor bảo đảm nó ra sao? Mỗi phương thức giữ được điều kiện ấy như thế nào, kể cả khi gặp lỗi?”** Ba câu hỏi này giúp biến nguyên tắc đóng gói thành những quy tắc thiết kế và kiểm thử cụ thể.