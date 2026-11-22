# Kiểm thử hàm khởi tạo và trạng thái không hợp lệ trong OOP

**Chủ đề:** OOP → Kiểm thử → **Kiểm thử hàm khởi tạo và trạng thái không hợp lệ**  
**Môi trường ví dụ:** Java 17+, JUnit Jupiter 5 (và `junit-jupiter-params` cho parameterized tests).

## 1. Vì sao cần kiểm thử constructor, khi nó “chỉ gán field”?

Xét một class biểu diễn hóa đơn. Để một hóa đơn có nghĩa, ta cần bảo đảm:

- Có **mã khách hàng không rỗng**.
- Có **ít nhất một dòng hàng**.
- Từng dòng có mã sản phẩm hợp lệ, đơn giá không âm và số lượng dương.
- **Tổng tiền hàng** được tính không tràn kiểu `long`.
- **Giảm giá** không âm và không vượt tổng tiền hàng.
- Sau khi tạo, người gọi không thể sửa danh sách đầu vào rồi làm thay đổi hóa đơn đã tạo.

Nếu constructor nhận mọi giá trị mà không kiểm tra, ta có thể tạo một object có `discountVnd > subtotalVnd`, danh sách hàng rỗng, thậm chí số tiền cuối cùng âm. Lỗi thường không xuất hiện ngay lúc `new`, mà lan tới bước lưu database, tính thuế hoặc hoàn tiền.

**Constructor là một ranh giới bảo vệ bất biến (invariant) của object.** Khi constructor trả về bình thường, caller có quyền tin object được tạo thỏa các bảo đảm đã công bố. Nếu dữ liệu không hợp lệ, constructor nên **từ chối tạo object** bằng một cơ chế lỗi rõ ràng.

Không phải constructor nào cũng phải làm nhiều việc: một value object có hai field đơn giản có thể cần rất ít validation. Nhưng một khi class công bố bất biến, **kiểm thử constructor chính là kiểm thử khả năng duy trì hợp đồng khi object bắt đầu tồn tại**.

### Ba câu hỏi cốt lõi

1. **Trường hợp hợp lệ:** tạo xong, các field đã đúng chưa; giá trị mặc định và chuẩn hóa có đúng không?
2. **Trường hợp không hợp lệ:** input nào phải bị từ chối; ngoại lệ thuộc loại nào; có tạo ra trạng thái quan sát được bị sai không?
3. **Sau khởi tạo:** object có tiếp tục hợp lệ khi input mutable hoặc reference được chia sẻ bị sửa không?

Một test chỉ kiểm tra `new Invoice(...)` “không ném exception” là chưa đủ nếu constructor còn có trách nhiệm tính tổng, chuẩn hóa hoặc chụp lại dữ liệu.

## 2. Phân biệt tiền điều kiện, hậu điều kiện và bất biến

| Khái niệm | Câu hỏi cần hỏi | Ví dụ |
| --- | --- | --- |
| **Precondition** | Đầu vào hợp lệ khi gọi constructor không? | `quantity > 0`; `customerId` không blank |
| **Postcondition** | Khi constructor thành công, object được thiết lập đúng chưa? | `total = subtotal - discount` |
| **Invariant** | Điều kiện nào phải luôn đúng khi object quan sát được? | `0 <= discount <= subtotal`, `total >= 0` |
| **Ownership/aliasing** | Object giữ một bản dữ liệu riêng hay dùng chung mutable reference? | Sửa `ArrayList` của caller không đổi hóa đơn |
| **Failure contract** | Khi vi phạm, constructor phản hồi thế nào? | `IllegalArgumentException` cho dữ liệu sai, `NullPointerException` cho tham chiếu bắt buộc null (nếu contract chọn vậy) |
| **Failure atomicity** | Nếu constructor thất bại, có side effect nào tồn tại không? | Không gửi email/ghi dữ liệu ngoài chỉ vì thử `new` |

Đặt ba tình huống cạnh nhau:

~~~text
Input hợp lệ:
  Invoice("CUS-01", [2 sách × 125000], discount=20000)
  → subtotal=250000, total=230000

Input không hợp lệ:
  Invoice("CUS-01", [2 sách × 125000], discount=300000)
  → ném IllegalArgumentException; không trả Invoice

Trạng thái bị phá sau tạo nếu thiết kế sai:
  Invoice giữ trực tiếp List mutable của caller
  → caller.clear() → hóa đơn trở thành rỗng
~~~

**“Không trả object” không đồng nghĩa Java tự rollback mọi side effect** đã xảy ra trong constructor. Nếu constructor đăng ký `this` với listener, phát event hoặc ghi DB trước khi validate xong, tác dụng phụ có thể còn tồn tại. Ta nên tránh làm như vậy và kiểm thử các ranh giới có side effect khi chúng thực sự cần thiết.

## 3. Lập ma trận kiểm thử trước khi viết test

Một ma trận tốt ghi rõ **điểm hợp lệ, điểm biên, trường hợp bị từ chối và kết quả sau lời gọi**:

| Nhóm | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Bình thường | ID hợp lệ, một/nhiều dòng hợp lệ | Tạo thành công, giữ đúng dữ liệu |
| Chuẩn hóa | ID `"  CUS-01  "` | Giá trị `customerId()` là `"CUS-01"` |
| ID sai | `null`, `""`, toàn khoảng trắng | `IllegalArgumentException` |
| Danh sách sai | `null` hoặc rỗng | Từ chối theo hợp đồng (ví dụ `NullPointerException`, `IllegalArgumentException`) |
| Phần tử sai | Danh sách có `null` | Từ chối; không tạo hóa đơn |
| Giá trị dòng hàng sai | Số lượng 0/âm, giá âm, SKU rỗng | `LineItem` từ chối |
| Giảm giá biên dưới | `discount = 0` | Hợp lệ |
| Giảm giá biên trên | `discount = subtotal` | Hợp lệ; tổng cuối = 0 |
| Giảm giá vượt biên | `discount = subtotal + 1` | `IllegalArgumentException` |
| Tính toán tràn số | `unitPrice × quantity` vượt `long` | `ArithmeticException` |
| Aliasing | Sửa danh sách nguồn sau tạo | Hóa đơn không thay đổi |
| Bảo vệ accessor | Gọi `invoice.lines().clear()` | `UnsupportedOperationException` |
| Trạng thái sau lỗi | Constructor thất bại hoặc operation bị từ chối | Không có object lỗi được trả về; state hiện có vẫn phù hợp hợp đồng |

**Chọn ngoại lệ theo hợp đồng**, không bắt buộc tất cả dữ liệu sai phải ném cùng một exception. Ví dụ `Objects.requireNonNull(...)` ném `NullPointerException`, còn số lượng âm thường được báo bằng `IllegalArgumentException`.

## 4. Ví dụ Java 17 hoàn chỉnh: constructor bảo vệ bất biến

Tạo file **ConstructorInvariantDemo.java**. Ví dụ dùng `record` cho một dòng hàng bất biến, một class `Invoice` có constructor kiểm soát các điều kiện liên trường, `Math.addExact/multiplyExact` để không tràn số âm thầm và `List.copyOf` để tách khỏi danh sách mutable của caller.

~~~java
import java.util.List;
import java.util.Objects;

public class ConstructorInvariantDemo {

    // Value object: không có setter; mỗi dòng được validate riêng.
    public record LineItem(
            String sku,
            long unitPriceVnd,
            int quantity) {

        public LineItem {
            sku = requiredText(sku, "sku");

            if (unitPriceVnd < 0) {
                throw new IllegalArgumentException(
                        "unitPriceVnd không được âm");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity phải dương");
            }
        }

        public long lineTotalVnd() {
            return Math.multiplyExact(unitPriceVnd, quantity);
        }
    }

    public static final class Invoice {
        private final String customerId;
        private final List<LineItem> lines;
        private final long subtotalVnd;
        private final long discountVnd;
        private final long totalVnd;

        public Invoice(
                String customerId,
                List<LineItem> lines,
                long discountVnd) {

            // Xác thực và tính toán trên biến cục bộ trước khi gán field.
            String normalizedId = requiredText(
                    customerId, "customerId");

            Objects.requireNonNull(lines, "lines");
            if (lines.isEmpty()) {
                throw new IllegalArgumentException(
                        "Hóa đơn cần ít nhất một dòng hàng");
            }

            // Tránh giữ tham chiếu tới ArrayList mutable của caller.
            // List.copyOf cũng từ chối phần tử null.
            List<LineItem> snapshot = List.copyOf(lines);

            long subtotal = 0;
            for (LineItem line : snapshot) {
                subtotal = Math.addExact(
                        subtotal, line.lineTotalVnd());
            }

            if (discountVnd < 0 || discountVnd > subtotal) {
                throw new IllegalArgumentException(
                        "Giảm giá phải nằm trong [0, subtotal]");
            }

            long total = Math.subtractExact(subtotal, discountVnd);

            // Chỉ thiết lập state sau khi toàn bộ điều kiện đã qua.
            this.customerId = normalizedId;
            this.lines = snapshot;
            this.subtotalVnd = subtotal;
            this.discountVnd = discountVnd;
            this.totalVnd = total;
        }

        public String customerId() {
            return customerId;
        }

        public List<LineItem> lines() {
            return lines;
        }

        public long subtotalVnd() {
            return subtotalVnd;
        }

        public long discountVnd() {
            return discountVnd;
        }

        public long totalVnd() {
            return totalVnd;
        }
    }

    private static String requiredText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    field + " không được null/rỗng");
        }
        return value.trim();
    }

    public static void main(String[] args) {
        var invoice = new Invoice(
                "  CUS-01  ",
                List.of(
                        new LineItem("BOOK-1", 125_000L, 2),
                        new LineItem("PEN-1", 35_000L, 1)
                ),
                20_000L
        );

        System.out.println(invoice.customerId());
        System.out.println(invoice.subtotalVnd());
        System.out.println(invoice.totalVnd());
        System.out.println(invoice.lines().size());
    }
}
~~~

Chạy:

~~~bash
javac ConstructorInvariantDemo.java
java ConstructorInvariantDemo
~~~

Kết quả:

~~~text
CUS-01
285000
265000
2
~~~

### Vì sao đặt validation trước các phép gán field?

Trong `Invoice`, mã khách hàng được chuẩn hóa; danh sách được kiểm tra và sao chép; tổng tiền được tính; sau đó mới gán các field `final`. Nếu thiếu một dòng hàng hoặc giảm giá vượt tổng, không có `Invoice` được trả ra cho client.

Java không bắt buộc constructor phải gán field `final` đúng thứ tự minh họa, nhưng cách **tính và kiểm tra trên biến cục bộ trước khi publish object** giúp người đọc dễ kiểm chứng invariants và giảm nguy cơ để `this` thoát ra giữa quá trình khởi tạo. Không nên gọi virtual method overrideable, đăng ký listener hoặc chuyển `this` sang thread khác trong constructor.

Đối với các data structure mutable, `List.copyOf` tạo một danh sách không thể sửa qua reference được trả về và không giữ kết nối tới `ArrayList` mutable ban đầu. Đây là **bản sao nông về phần tử**: nếu `LineItem` chứa một object mutable, người gọi vẫn có thể sửa trạng thái phần tử đó qua reference khác. Trong ví dụ, `LineItem` dùng `String`, `long`, `int` nên không có vấn đề mutable element.

### Tại sao không chỉ dùng setter để hoàn tất?

Mẫu sau cho phép trạng thái trung gian sai:

~~~java
// Chỉ minh họa anti-pattern: không có validation tại ranh giới tạo.
Invoice invoice = new Invoice();
invoice.setCustomerId("CUS-01");
invoice.setDiscountVnd(500_000L);
// Ở đây chưa chắc tồn tại dòng hàng nào!
~~~

Lớp `Invoice` trong ví dụ hoàn chỉnh **không có constructor rỗng hay setter**; caller chỉ có thể nhận object khi đã đủ dữ liệu hợp lệ. Những object UI form hoặc entity do framework quản lý có thể cần lifecycle khác, nhưng khi đó trạng thái **chưa hoàn chỉnh** cần được tách khỏi trạng thái domain **đã hợp lệ**, không bị xem là tương đương.

## 5. JUnit 5: kiểm thử đường hợp lệ và giá trị biên

Tạo file **ConstructorInvariantDemoTest.java** (cùng package với class trên). Các test sử dụng JUnit Jupiter và module `junit-jupiter-params`.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

class ConstructorInvariantDemoTest {

    private static ConstructorInvariantDemo.LineItem item(
            long price, int quantity) {
        return new ConstructorInvariantDemo.LineItem(
                "BOOK-1", price, quantity);
    }

    private static ConstructorInvariantDemo.Invoice invoice(
            String customerId, List<ConstructorInvariantDemo.LineItem> lines,
            long discount) {
        return new ConstructorInvariantDemo.Invoice(
                customerId, lines, discount);
    }

    @Test
    void validInvoiceComputesTotalsAndNormalizesId() {
        var result = invoice(
                "  CUS-01 ",
                List.of(item(125_000L, 2), item(35_000L, 1)),
                20_000L);

        assertAll(
                () -> assertEquals("CUS-01", result.customerId()),
                () -> assertEquals(285_000L, result.subtotalVnd()),
                () -> assertEquals(20_000L, result.discountVnd()),
                () -> assertEquals(265_000L, result.totalVnd()),
                () -> assertEquals(2, result.lines().size())
        );
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {" ", "   ", "\t"})
    void invalidCustomerIdIsRejected(String invalidId) {
        assertThrows(IllegalArgumentException.class, () ->
                invoice(invalidId, List.of(item(100L, 1)), 0L));
    }

    @Test
    void emptyAndNullLinesAreRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                invoice("CUS", List.of(), 0L));

        assertThrows(NullPointerException.class, () ->
                invoice("CUS", null, 0L));
    }

    @Test
    void nullElementIsRejected() {
        var source =
                new ArrayList<ConstructorInvariantDemo.LineItem>();
        source.add(item(10L, 1));
        source.add(null);

        assertThrows(NullPointerException.class, () ->
                invoice("CUS", source, 0L));
    }

    @Test
    void discountBoundariesAreClear() {
        var goods = List.of(item(100L, 2)); // subtotal = 200

        assertEquals(200L,
                invoice("CUS", goods, 0L).totalVnd());
        assertEquals(0L,
                invoice("CUS", goods, 200L).totalVnd());

        assertThrows(IllegalArgumentException.class, () ->
                invoice("CUS", goods, -1L));
        assertThrows(IllegalArgumentException.class, () ->
                invoice("CUS", goods, 201L));
    }

    @Test
    void invalidLineItemIsRejectedAtConstruction() {
        assertThrows(IllegalArgumentException.class, () ->
                item(-1L, 1));
        assertThrows(IllegalArgumentException.class, () ->
                item(100L, 0));
        assertThrows(IllegalArgumentException.class, () ->
                new ConstructorInvariantDemo.LineItem(
                        "  ", 100L, 1));
    }

    @Test
    void overflowIsRejectedInsteadOfWrapping() {
        assertThrows(ArithmeticException.class, () ->
                invoice("CUS", List.of(
                        item(Long.MAX_VALUE, 2)), 0L));

        assertThrows(ArithmeticException.class, () ->
                invoice("CUS", List.of(
                        item(Long.MAX_VALUE, 1),
                        item(1L, 1)), 0L));
    }

    @Test
    void sourceListMutationCannotChangeInvoice() {
        var source =
                new ArrayList<ConstructorInvariantDemo.LineItem>();
        source.add(item(100L, 1));
        var result = invoice("CUS", source, 0L);

        source.clear();
        assertEquals(1, result.lines().size());
        assertEquals(100L, result.totalVnd());

        assertThrows(UnsupportedOperationException.class, () ->
                result.lines().add(item(1L, 1)));
    }
}
~~~

Các test được đặt tên theo **hành vi**, không theo tên field nội bộ. Ví dụ `discountBoundariesAreClear` giúp nhận ra ngay quy tắc “0 và subtotal hợp lệ, ngoài khoảng thì từ chối”, thay vì chỉ là `testConstructor3`.

### Giải thích vì sao từng kiểu test quan trọng

- **Happy path:** kiểm tra output và chuẩn hóa, không chỉ “không ném”.
- **Null/empty/blank:** phân biệt null reference, chuỗi rỗng và chỉ có whitespace.
- **Boundary:** test chính xác ranh giới `0`, `subtotal`, `-1`, `subtotal + 1`, vì lỗi `<`/`<=` dễ xảy ra.
- **Nested invalid input:** một `Invoice` chỉ hợp lệ nếu `LineItem` hợp lệ. Validate ở từng lớp tạo nên một chuỗi hợp đồng.
- **Overflow:** `Math.multiplyExact` hoặc `Math.addExact` làm rõ điều mà phép số học `long` thông thường không bảo đảm.
- **Aliasing:** chứng minh object không bị thay đổi khi caller sửa danh sách nguồn.
- **Accessor:** chứng minh reference trả về không cho caller phá bất biến bằng thao tác trên list.

**Lưu ý:** unit test cho ví dụ chỉ cần JUnit Jupiter. JUnit không được JDK cung cấp mặc định, nên cần dependency test của dự án. Các file demo và test có thể đặt trong cùng package; nếu dùng package khác, cần điều chỉnh visibility/import.

## 6. Kiểm thử trạng thái không hợp lệ *sau* khi constructor thành công

Không chỉ constructor: nhiều object hợp lệ lúc đầu nhưng có thể bị sửa sai qua một method. Nếu object mutable, các phép cập nhật cũng phải giữ invariant.

Ví dụ lớp quản lý hạn mức đã có thể được tạo với số dư hợp lệ, nhưng một lệnh trừ quá hạn mức phải bị từ chối mà **không làm thay đổi số dư**:

~~~java
public final class Wallet {
    private long balanceVnd;

    public Wallet(long initialBalanceVnd) {
        if (initialBalanceVnd < 0) {
            throw new IllegalArgumentException(
                    "Số dư ban đầu không được âm");
        }
        this.balanceVnd = initialBalanceVnd;
    }

    public long balanceVnd() {
        return balanceVnd;
    }

    public void debit(long amountVnd) {
        if (amountVnd <= 0) {
            throw new IllegalArgumentException(
                    "Số tiền phải dương");
        }
        if (amountVnd > balanceVnd) {
            throw new IllegalStateException(
                    "Không đủ số dư");
        }

        balanceVnd = Math.subtractExact(balanceVnd, amountVnd);
    }
}
~~~

Đây là một class riêng, lưu trong **Wallet.java** nếu chạy độc lập. Để minh họa kiểm thử:

~~~java
@Test
void failedDebitMustPreserveValidState() {
    Wallet wallet = new Wallet(100L);

    assertThrows(IllegalStateException.class, () ->
            wallet.debit(101L));

    assertEquals(100L, wallet.balanceVnd());
}

@Test
void constructorRejectsNegativeInitialBalance() {
    assertThrows(IllegalArgumentException.class, () ->
            new Wallet(-1L));
}
~~~

Hai test trên là method đặt trong một JUnit test class có `import static org.junit.jupiter.api.Assertions.*;` và `import org.junit.jupiter.api.Test;`.

**Ý nghĩa:** thay vì ép một `Wallet` hợp lệ thành trạng thái âm bằng reflection rồi kiểm tra method khác, ta test **đường sử dụng công khai có khả năng tạo ra lỗi**. Nếu bất biến được bảo vệ đúng, không có public API nào tạo ra trạng thái âm.

Ví dụ Wallet chưa thread-safe; hai thao tác đồng thời có thể cạnh tranh trên `balanceVnd`. Đối với hệ thống tiền thật, phải có thêm cơ chế transaction, idempotency và quyền truy cập phù hợp. “Constructor test PASS” không chứng minh cả vòng đời object an toàn trước concurrency.

## 7. Không kiểm thử bằng cách phá bất biến một cách tùy tiện

Đôi khi ta muốn “tạo một object invalid rồi đưa vào service” để kiểm tra service có xử lý không. Nhưng nếu constructor từ chối object invalid, điều này là **thiết kế đúng**.

Ví dụ không nên làm trong unit test business thông thường:

~~~java
// Không nên dùng reflection chỉ để vượt constructor:
// Field f = Invoice.class.getDeclaredField("discountVnd");
// f.setAccessible(true);
// f.setLong(invoice, -99L);
~~~

Cách đó buộc test phụ thuộc cấu trúc private và làm hỏng chính bất biến mà class hứa bảo vệ. Sau refactor đổi tên field, test có thể gãy dù hành vi công khai không đổi.

**Thay vào đó, đặt lỗi tại đúng ranh giới:**

- Nếu người dùng gửi JSON sai, test bộ **request validation/deserialization**.
- Nếu database chứa dữ liệu cũ sai, test **persistence mapping/migration** hoặc adapter phục hồi trạng thái.
- Nếu service nhận một dependency có thể lỗi, dùng fake hoặc mock trả lỗi từ dependency theo contract.
- Nếu cần test logic khôi phục từ snapshot cũ, tạo **test fixture ở API nội bộ có kiểm soát** thay vì khai mở setter public trên domain object.

Điều quan trọng là **test đúng vị trí xuất hiện lỗi**, không phải cố tạo trạng thái mà API đã cấm.

## 8. Constructor có nhiều bước: bảo đảm lỗi không để lại tác dụng phụ

Một constructor nguy hiểm có thể làm việc ngoài phạm vi thiết lập state:

~~~java
// Anti-pattern minh họa: side effect trước khi validate xong.
class BadRegistration {
    BadRegistration(EventBus bus, String email) {
        bus.publish("RegistrationStarted");
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email sai");
        }
    }
}
~~~

Nếu email sai, caller không nhận được `BadRegistration` hợp lệ, **nhưng event có thể đã phát**. Một listener có thể đã ghi dữ liệu, gửi mail hoặc tạo log nghiệp vụ sai.

Hướng thiết kế rõ hơn:

1. Constructor/factory tạo một value object **hợp lệ** và hạn chế side effect.
2. Application service phối hợp transaction, persistence, event/outbox theo nhu cầu.
3. Nếu thất bại ở bất cứ bước nào, thiết kế cách xử lý/rollback/compensation riêng.
4. Test side effect qua fake để xác nhận trường hợp input sai **không gọi collaborator**.

Ví dụ một service tạo yêu cầu đăng ký:

~~~java
record RegistrationRequest(String email) {
    RegistrationRequest {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email sai");
        }
        email = email.trim();
    }
}

interface RegistrationGateway {
    void submit(RegistrationRequest request);
}

final class RegistrationService {
    private final RegistrationGateway gateway;

    RegistrationService(RegistrationGateway gateway) {
        this.gateway = java.util.Objects.requireNonNull(gateway);
    }

    void register(String email) {
        RegistrationRequest request = new RegistrationRequest(email);
        gateway.submit(request);
    }
}
~~~

Bây giờ `RegistrationRequest` từ chối đầu vào trước khi `submit()` chạy. Kiểm thử có thể dùng fake đếm số lần gateway được gọi để bảo đảm input sai không tạo side effect. Tuy nhiên, code còn cần xử lý lỗi gateway và retry theo hợp đồng; việc chỉ validate trước chưa tự tạo transaction xuyên mạng.

## 9. Một ví dụ fake để kiểm tra “không gọi dependency khi input sai”

Các type ở phần trên có thể đặt chung package. JUnit test minh họa:

~~~java
@Test
void invalidRegistrationDoesNotCallGateway() {
    class RecordingGateway implements RegistrationGateway {
        int calls;

        @Override
        public void submit(RegistrationRequest request) {
            calls++;
        }
    }

    RecordingGateway fake = new RecordingGateway();
    RegistrationService service = new RegistrationService(fake);

    assertThrows(IllegalArgumentException.class, () ->
            service.register("  "));

    assertEquals(0, fake.calls);
}
~~~

Đoạn này nằm trong class test có JUnit import tương ứng. Nó đo **hành vi bên ngoài** (không gửi lệnh khi input sai), không test một field private chỉ vì field đó tồn tại.

## 10. Record, Builder và inheritance: không chỉ constructor thông thường

### 10.1. Compact constructor của record

Java `record` tự tạo canonical constructor, có thể thêm kiểm tra trong **compact constructor**:

~~~java
record Age(int years) {
    Age {
        if (years < 0 || years > 150) {
            throw new IllegalArgumentException("Tuổi không hợp lệ");
        }
    }
}
~~~

Test cần bao gồm `0`, `150` là hợp lệ; `-1`, `151` bị từ chối. Record **không tự validation** nếu không có code kiểm tra. Record cũng chỉ **shallowly immutable**: component chứa một `List` hoặc mảng mutable có thể làm biến đổi trạng thái quan sát được nếu không phòng vệ.

### 10.2. Builder không được bỏ qua invariant của Product

~~~java
Invoice invoice = Invoice.builder()
        .customerId("CUS-01")
        .addLine(...)
        .discountVnd(200_000L)
        .build();
~~~

Đây là **minh họa API Builder giả định**, không phải API hiện có của `ConstructorInvariantDemo.Invoice`. Nếu Builder tạo object, điều kiện `discount <= subtotal` vẫn phải được thực thi ở `build()` hoặc constructor/factory của Product. Test cả việc thiếu field, áp dụng default và các tổ hợp không hợp lệ; đừng tin Builder hợp lệ chỉ vì mỗi setter riêng lẻ hợp lệ.

### 10.3. Kế thừa và lời gọi phương thức có thể override

Gọi một method có thể override trong constructor có thể dẫn tới việc thực thi method của subclass **trước khi field riêng của subclass được khởi tạo đầy đủ**:

~~~java
class Base {
    Base() {
        initialize(); // Nguy cơ dispatch tới override.
    }

    void initialize() {}
}

class Child extends Base {
    private String name = "ready";

    @Override
    void initialize() {
        // Ở thời điểm Base() gọi, name chưa được gán "ready".
        System.out.println(name); // null
    }
}
~~~

Vì vậy, không nên thiết kế constructor dựa vào override của subclass để hoàn thiện invariant. Test object subclass có thể bắt lỗi đó, nhưng **giải pháp thiết kế tốt hơn** là giữ logic khởi tạo trong constructor/factory không cần virtual dispatch, rồi thực hiện các bước phụ thuộc subtype khi trạng thái đã hoàn chỉnh.

Đừng tạo object trong constructor rồi đăng ký `this` vào callback hoặc một thread: đối tượng có thể bị quan sát quá sớm, trước khi các field được thiết lập an toàn.

## 11. Kiểm thử tổ hợp trạng thái không hợp lệ

Một object có thể có từng field hợp lệ nhưng **tổ hợp** không hợp lệ. Ví dụ lịch hẹn:

- `start` và `end` khác null;
- `end` phải sau `start`;
- nếu chọn `REMOTE`, phải có liên kết họp;
- nếu chọn `ONSITE`, phải có địa điểm.

Một ma trận nhỏ:

| Hình thức | Link họp | Địa điểm | Kết quả |
| --- | --- | --- | --- |
| REMOTE | Có | Không | Hợp lệ |
| REMOTE | Không | Không | Sai: thiếu link |
| ONSITE | Không | Có | Hợp lệ |
| ONSITE | Không | Không | Sai: thiếu địa điểm |
| Bất kỳ | Có | Có | Tùy hợp đồng: có cho phép dữ liệu dư không? |
| Bất kỳ | Ngày kết thúc trước bắt đầu | Bất kỳ | Sai |

**Kiểm thử theo từng field đơn lẻ sẽ không phát hiện mọi vi phạm liên trường.** Đây là nơi nên phân loại equivalence classes và dùng parameterized tests hoặc test table-driven để giảm lặp, bảo đảm mọi tổ hợp quan trọng được thử.

Tuy nhiên, đừng cố kiểm thử mọi tích Descartes của 20 field nếu không có cơ sở rủi ro. Ưu tiên những tổ hợp ảnh hưởng invariant thật; dùng property-based testing khi miền giá trị lớn và có công cụ phù hợp.

## 12. Kiểm thử lỗi như một phần hợp đồng, không phụ thuộc câu chữ

Ví dụ:

~~~java
IllegalArgumentException failure =
        assertThrows(IllegalArgumentException.class,
                () -> new ConstructorInvariantDemo.LineItem(
                        "SKU", -1L, 1));
~~~

Test có thể kiểm tra `failure.getMessage()` nếu thông điệp là **hợp đồng công khai được thống nhất**, nhưng đừng đóng băng mọi câu chữ nội bộ chỉ để tăng assertion. Thay đổi ngôn ngữ, thêm ngữ cảnh hoặc chỉnh cách diễn đạt thường không phải lỗi domain.

Nếu caller phải phân biệt lỗi “giảm giá vượt tổng” với “mã khách hàng thiếu”, nên có **error code**, result type hoặc exception có ngữ nghĩa cụ thể. Không nên để caller parse chuỗi message để ra quyết định.

### `assertThrows` và `assertDoesNotThrow`

- `assertThrows(Expected.class, executable)` chấp nhận exception thuộc class mong đợi **hoặc subclass**. Nếu hợp đồng đòi **đúng loại** exception, có thể dùng `assertThrowsExactly` trong JUnit 5 hỗ trợ.
- `assertDoesNotThrow` hữu ích để chứng minh giá trị biên hợp lệ, nhưng thường nên **kiểm tra kết quả** của object được tạo, thay vì chỉ khẳng định không lỗi.
- `assertAll` gom một số khẳng định về cùng một object để người học nhìn rõ các postcondition; không dùng nó để che một phép khởi tạo thất bại.

Ví dụ:

~~~java
var invoice = assertDoesNotThrow(() ->
        new ConstructorInvariantDemo.Invoice(
                "CUS",
                List.of(new ConstructorInvariantDemo.LineItem(
                        "BOOK", 100L, 1)),
                100L));

assertEquals(0L, invoice.totalVnd());
~~~

## 13. Đối tượng bất biến và trạng thái không hợp lệ dưới tải đồng thời

Một object có field `private final`, thành phần immutable và không escape khỏi constructor thường dễ dùng an toàn hơn khi chia sẻ giữa thread. Nhưng **`final` không biến mọi object tham chiếu thành bất biến** và không thay thế được thiết kế đồng bộ cho mutable state.

Ví dụ `Wallet` trong phần trước không thread-safe. Hai thread cùng kiểm tra số dư 100 rồi mỗi thread trừ 80 có thể dẫn tới kết quả mất cập nhật hoặc khác mong muốn, tùy cách interleave. Constructor test không kiểm tra hiện tượng này.

Với entity lưu database, còn cần **transaction/locking/version** để tránh hai request đồng thời ghi đè nhau. Nhiều class có invariant hợp lệ trong RAM vẫn có thể sai khi persistence mapper bỏ qua constructor, hoặc dữ liệu DB chứa giá trị từ phiên bản cũ.

Phân tách trách nhiệm kiểm thử:

| Ranh giới | Nên chứng minh gì? |
| --- | --- |
| Constructor/record/builder | Input hợp lệ sinh object hợp lệ; invalid input bị từ chối |
| Public mutator | Thao tác sai không phá invariant; phép cập nhật đúng giữ hậu điều kiện |
| Serialization/deserialization | Dữ liệu từ JSON được xác thực/khôi phục đúng theo contract |
| Persistence mapper/ORM | Dữ liệu lưu và tải lại bảo toàn invariant, xử lý dữ liệu cũ sai |
| Application service | Trước lỗi không gửi side effect ngoài ý muốn, có phân quyền và state đúng |
| Concurrent/transaction boundary | Nhiều lệnh đồng thời không phá điều kiện bảo toàn ở nguồn dữ liệu thật |

Không cần chạy các integration test đắt cho từng điều kiện nhỏ đã được unit test; nhưng cũng không được dùng chỉ một unit test constructor để tuyên bố an toàn toàn hệ thống.

## 14. Những lỗi thường gặp khi viết test constructor

| Sai lầm | Vấn đề | Thay bằng |
| --- | --- | --- |
| Chỉ kiểm tra `assertNotNull(new Object(...))` | Không chứng minh giá trị, invariant hay failure | Assert các postcondition có ý nghĩa |
| Chỉ test happy path | Không phát hiện giá trị biên/không hợp lệ | Bảng valid, invalid và boundary |
| Mong mọi null đều trả cùng exception tùy ý | Không bám hợp đồng thực | Quy định rõ null policy và assert đúng |
| Tạo object invalid bằng reflection | Test bám implementation private | Test qua public constructor/mutator và boundary dữ liệu ngoài |
| Dùng `assertThrows(Exception.class, ...)` | Quá rộng, sai exception vẫn PASS | Kiểm tra loại exception dự kiến |
| Assert nguyên văn mọi message | Test dễ gãy vì wording | Chỉ assert message khi là API contract |
| Tin `final List` là immutable | Caller vẫn có thể sửa nội dung list | Defensive copy và test aliasing |
| Không kiểm tra `total` khi discount sát biên | Lỗi off-by-one dễ lọt | Test `0`, `subtotal`, `subtotal+1` |
| Để constructor làm I/O không cần thiết | Side effect khó rollback khi validation fail | Validate trước, phối hợp I/O tại service |
| Test riêng các setter nhưng không test tổ hợp | Các field đơn lẻ hợp lệ nhưng cùng nhau sai | Test invariant liên trường |
| Chỉ test một thread cho object mutable chia sẻ | Không bắt race/mất cập nhật | Test concurrency và bảo vệ ở đúng boundary nếu cần |

## 15. Checklist khi review một constructor

Dùng checklist này trước khi chốt test:

- [ ] Các tham số bắt buộc có được kiểm tra null/blank/range không?
- [ ] Các giới hạn **đúng biên** được test chưa (0, 1, max, max+1)?
- [ ] Có quy tắc **liên quan nhiều field** phải được xác nhận cùng nhau không?
- [ ] Có phép tính tràn số hoặc mất độ chính xác cần kiểm soát không?
- [ ] Khi thành công, các field được chuẩn hóa và derived values đúng chưa?
- [ ] Collection và các reference mutable có được sao chép hoặc bảo vệ phù hợp không?
- [ ] Có đường nào caller sửa object vượt qua validation không?
- [ ] Constructor có gọi code overrideable, publish `this` hoặc tạo side effect sớm không?
- [ ] Kiểu exception/result có rõ nghĩa với người dùng API không?
- [ ] ORM, serializer hay framework có thể xây dựng object bằng đường khác không?
- [ ] Với mutable object, các thao tác bị từ chối có giữ nguyên state hợp lệ không?

Checklist không thay thế suy luận về domain: test tốt nhất phải được rút từ những invariant thật, không phải từ một template chung.

## 16. Bài tập: tạo lịch hẹn an toàn

Thiết kế class `Appointment` trong Java với các trường:

- `appointmentId`: không được blank.
- `start` và `end`: kiểu `LocalDateTime`, không null và `end.isAfter(start)`.
- `channel`: enum `ONLINE` hoặc `OFFLINE`.
- `meetingLink`: bắt buộc khi `ONLINE`.
- `location`: bắt buộc khi `OFFLINE`.
- `participants`: danh sách mã người tham gia, phải có ít nhất một phần tử, không phần tử nào null/blank, không có mã trùng sau khi chuẩn hóa.
- Khi tạo thành công, đối tượng được dùng như một cấu hình bất biến.

**Yêu cầu thực hành:**

1. Thiết kế constructor (hoặc static factory) không cho tạo trạng thái sai.
2. Vẽ bảng các tổ hợp hợp lệ/không hợp lệ của `channel`, `meetingLink`, `location`.
3. Viết JUnit 5 parameterized tests cho null/blank ID; giá trị biên của `start/end`; thiếu trường theo loại `channel`.
4. Kiểm thử cả `participants` rỗng, có null, blank, trùng sau trim.
5. Kiểm thử sửa danh sách nguồn sau khi tạo không làm object thay đổi; accessor không trả danh sách mutable nội bộ.
6. Nếu app nhận dữ liệu từ JSON, giải thích boundary validation nào xảy ra trước khi gọi domain constructor.
7. Nếu lịch hẹn có phương thức `reschedule(newStart, newEnd)`, nên trả một object mới bất biến hay dùng mutation có kiểm soát? Chứng minh rằng input sai không để lại trạng thái bị phá.

**Tiêu chí đạt:** mọi đường xây dựng object đều bảo vệ invariant; test khẳng định cả kết quả hợp lệ và cách từ chối không hợp lệ; khi một tham số/tổ hợp bị lỗi, không có object sai được công bố; dữ liệu mutable bên ngoài không phá được đối tượng đã tạo.

---

**Ghi nhớ:** constructor không chỉ “đổ dữ liệu vào field” khi object mang bất biến nghiệp vụ. Kiểm thử constructor là kiểm thử lời hứa rằng **một object được tạo thành công đã ở trạng thái hợp lệ**; kiểm thử trạng thái không hợp lệ là chứng minh các con đường tạo hoặc sửa object **không thể âm thầm phá lời hứa đó**.