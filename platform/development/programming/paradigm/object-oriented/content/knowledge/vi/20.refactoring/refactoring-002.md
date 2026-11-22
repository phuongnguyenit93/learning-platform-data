# Đổi tên để làm rõ ý định (Rename for Intent) trong Java OOP

## Vì sao một cái tên có thể làm code khó hiểu?

Xét một lời gọi trong chương trình bán hàng:

~~~java
long total = Calc.f(items, true);
~~~

Người đọc chưa biết `f` làm gì, `true` bật điều kiện nào, và `total` đã bao gồm những khoản tiền gì. Nếu muốn sửa code, họ phải mở phần cài đặt, lần theo các biến và tự suy luận nghiệp vụ.

Đổi tên để làm rõ ý định là một thao tác **refactoring**: thay tên class, method, field, biến hoặc hằng số bằng tên thể hiện chính xác vai trò của nó, trong khi **giữ nguyên hành vi quan sát được của chương trình**.

Ví dụ cùng ý tưởng với tên rõ ràng hơn:

~~~java
long payableAmountVnd =
        orderPriceCalculator.calculatePayableAmountVnd(
                orderLines, includeDeliveryFee);
~~~

Tên mới giúp trả lời ngay ba câu hỏi: giá trị là **số tiền phải trả**, đơn vị là **VND**, tham số boolean quyết định **có cộng phí giao hàng hay không**.

> Một tên tốt tiết lộ ý định; nó không chỉ mô tả kiểu dữ liệu. `orderLines` hữu ích hơn `list`, `remainingStock` hữu ích hơn `number`, và `isPaymentApproved` hữu ích hơn `flag`.

## Những tên nên thay đổi

| Vị trí trong OOP | Tên khó hiểu | Tên diễn đạt ý định | Vì sao rõ hơn? |
|---|---|---|---|
| Class | `DataManager` | `OrderRepository` | Chỉ rõ trách nhiệm lưu/truy xuất đơn hàng |
| Method | `process()` | `confirmOrder()` | Thể hiện thao tác nghiệp vụ |
| Method tính toán | `getTotal()` | `calculatePayableAmountVnd()` | Nêu hành động tính và ý nghĩa kết quả |
| Field | `n` | `quantity` | Chỉ rõ con số đại diện điều gì |
| Collection | `data` | `unpaidInvoices` | Nêu phần tử và tiêu chí của tập dữ liệu |
| Boolean | `flag` | `includeDeliveryFee` | Nêu ý nghĩa của `true` |
| Boolean trạng thái | `status` | `isOrderCancelled` | Đọc được như một điều kiện đúng/sai |
| Hằng số | `LIMIT` | `MAX_LOGIN_ATTEMPTS` | Nêu giới hạn áp dụng cho nghiệp vụ nào |
| Đơn vị | `timeout` | `connectionTimeoutMillis` | Tránh hiểu nhầm mili giây với giây |
| Thời điểm | `time` | `paymentExpiresAt` | Phân biệt mốc thời gian với khoảng thời gian |

Bảng là ví dụ có điều kiện: **tên đúng phải được suy ra từ hành vi thật**. Không thể đổi `DataManager` thành `OrderRepository` nếu class thực tế phụ trách nhiều loại dữ liệu. Cũng không nên đổi `getTotal()` thành `calculatePayableAmountVnd()` nếu method trả về số lượng sản phẩm thay vì tiền.

## Minh họa refactor có thể chạy: trước và sau đổi tên

Chương trình sau mô phỏng tính tổng tiền các dòng hàng, tùy chọn cộng phí giao hàng cố định 30.000 VND. Hai cách viết `Before` và `After` được giữ song song **chỉ để kiểm chứng trong bài học**; ở code thực tế, sau khi refactor ta giữ một triển khai và xóa tên cũ nếu không còn tương thích API cần duy trì.

Lưu đoạn sau thành **RenameForIntentDemo.java** (Java 11 trở lên):

~~~java
import java.util.List;

public final class RenameForIntentDemo {
    private static final long DELIVERY_FEE_VND = 30_000L;

    static final class OrderLine {
        private final long unitPriceVnd;
        private final int quantity;

        OrderLine(long unitPriceVnd, int quantity) {
            if (unitPriceVnd < 0 || quantity <= 0) {
                throw new IllegalArgumentException("Invalid order line");
            }
            this.unitPriceVnd = unitPriceVnd;
            this.quantity = quantity;
        }

        long calculateLineAmountVnd() {
            return Math.multiplyExact(unitPriceVnd, (long) quantity);
        }
    }

    // BEFORE: phải đọc phần thân mới đoán được tên và biến có ý nghĩa gì.
    static final class Before {
        static long f(List<OrderLine> x, boolean y) {
            long z = 0L;
            for (OrderLine i : x) {
                z = Math.addExact(z, i.calculateLineAmountVnd());
            }
            if (y) {
                z = Math.addExact(z, DELIVERY_FEE_VND);
            }
            return z;
        }
    }

    // AFTER: chỉ đổi các định danh; điều kiện, phép tính và thứ tự giữ nguyên.
    static final class After {
        static long calculatePayableAmountVnd(
                List<OrderLine> orderLines,
                boolean includeDeliveryFee) {

            long payableAmountVnd = 0L;
            for (OrderLine orderLine : orderLines) {
                payableAmountVnd = Math.addExact(
                        payableAmountVnd,
                        orderLine.calculateLineAmountVnd());
            }
            if (includeDeliveryFee) {
                payableAmountVnd = Math.addExact(
                        payableAmountVnd, DELIVERY_FEE_VND);
            }
            return payableAmountVnd;
        }
    }

    private static void assertEquals(long expected, long actual) {
        if (expected != actual) {
            throw new AssertionError(
                    "Expected " + expected + ", actual " + actual);
        }
    }

    public static void main(String[] args) {
        List<OrderLine> orderLines = List.of(
                new OrderLine(20_000L, 2),
                new OrderLine(55_000L, 1)
        );
        // Tiền hàng: 20.000 * 2 + 55.000 = 95.000 VND.

        long oldWithoutDelivery = Before.f(orderLines, false);
        long newWithoutDelivery =
                After.calculatePayableAmountVnd(orderLines, false);

        long oldWithDelivery = Before.f(orderLines, true);
        long newWithDelivery =
                After.calculatePayableAmountVnd(orderLines, true);

        assertEquals(95_000L, oldWithoutDelivery);
        assertEquals(oldWithoutDelivery, newWithoutDelivery);

        assertEquals(125_000L, oldWithDelivery);
        assertEquals(oldWithDelivery, newWithDelivery);

        // Kiểm tra một trường hợp biên: không có dòng hàng.
        assertEquals(Before.f(List.of(), false),
                After.calculatePayableAmountVnd(List.of(), false));

        System.out.println("Rename preserves behavior: PASS");
    }
}
~~~

Chạy:

~~~bash
javac RenameForIntentDemo.java
java RenameForIntentDemo
~~~

Kết quả:

~~~text
Rename preserves behavior: PASS
~~~

Các thay đổi chính trong thân phương thức:

| Trước | Sau | Vai trò |
|---|---|---|
| `f` | `calculatePayableAmountVnd` | Phép tính tiền phải trả |
| `x` | `orderLines` | Tập các dòng hàng |
| `y` | `includeDeliveryFee` | Có cộng phí giao hàng |
| `z` | `payableAmountVnd` | Giá trị tích lũy và kết quả |
| `i` | `orderLine` | Phần tử đang duyệt |

Bản `Before` và `After` đều dùng đúng một hằng phí giao hàng, cùng `Math.addExact` và `Math.multiplyExact`. Vì vậy sự khác nhau đang được khảo sát là **cách đặt tên**, không bị trộn với thay đổi công thức hay xử lý tràn số. Ví dụ kiểm tra một số trường hợp cụ thể; trong dự án thật cần chạy toàn bộ test và các trường hợp biên quan trọng.

## Đổi tên thế nào để thực sự phản ánh ý định?

### 1. Tên phương thức nên thể hiện hành động hoặc câu hỏi

~~~java
// Mơ hồ: tên không thể hiện kết quả.
void handle(Order order);

// Rõ hơn nếu nghiệp vụ thực sự là xác nhận đơn.
void confirmOrder(Order order);

// Boolean method có thể đọc như một câu hỏi.
boolean isEligibleForFreeShipping(Order order);
~~~

Một method có tên `validateOrder` cần có hợp đồng rõ: trả `boolean`, trả danh sách lỗi, hay ném exception? Nếu method **ném lỗi khi không hợp lệ**, `requireValidOrder` đôi khi diễn đạt hành vi chuẩn xác hơn; nếu nó trả `boolean`, `isOrderValid` có thể dễ hiểu hơn. Chọn theo hợp đồng có thật.

Với JavaBean, JPA, thư viện serialization hoặc framework dựa vào getter, các tiền tố `get`, `is`, `set` đôi khi là một phần của quy ước kỹ thuật. Đổi tên vẫn phải phù hợp hợp đồng/framework.

### 2. Tên dữ liệu nên thể hiện ý nghĩa nghiệp vụ và đơn vị

~~~java
long delay = 5_000;                 // 5.000 giây hay mili giây?
long retryDelayMillis = 5_000;      // Mili giây.

int count = 3;                      // Đếm cái gì?
int failedLoginAttempts = 3;        // Số lần đăng nhập thất bại.
~~~

Trong code mới, kiểu miền giúp tránh nhầm hơn nữa, ví dụ `Duration.ofSeconds(5)`. Tuy nhiên, **đổi từ `long` sang `Duration` là thay đổi kiểu dữ liệu**, không còn là thao tác chỉ đổi tên; cần tách thành bước refactor khác và có kiểm thử tương ứng.

### 3. Tên boolean phải tránh hai cách hiểu

~~~java
boolean active;              // Ai đang hoạt động?
boolean userAccountActive;   // Tài khoản người dùng đang hoạt động.

boolean send;                // Gửi thứ gì, lúc nào?
boolean sendConfirmationEmail;
~~~

Đừng dùng các tên phủ định kép như `isNotDisabled` nếu có thể diễn đạt trực tiếp bằng `isEnabled`. Tuy nhiên, **đảo nghĩa một cờ** (`disabled` sang `enabled` rồi đảo giá trị) không phải rename đơn thuần, bởi `true` đã mang nghĩa khác; phải thay toàn bộ logic sử dụng và kiểm thử thật kỹ.

### 4. Cân bằng giữa độ ngắn và đủ ngữ cảnh

`customerId` tốt hơn `c`, nhưng `customerIdOfTheCustomerCurrentlyBeingProcessed` lại quá dài. Trong vòng lặp nhỏ, `index` hoặc `item` có thể đủ; ở một method xử lý cả `orders`, `invoices` và `receipts`, tên `currentOrder` rõ hơn `item`.

Phạm vi càng rộng (public class, public API, field sống lâu), tên càng cần tự giải thích. Trong biểu thức rất cục bộ, một tên ngắn nhưng rõ ngữ cảnh vẫn chấp nhận được.

## Quy trình đổi tên an toàn trong dự án Java

~~~mermaid
flowchart TD
    A["Hiểu mục đích và hợp đồng hiện tại"] --> B["Chọn tên diễn đạt nghiệp vụ đúng"]
    B --> C["Dùng IDE Rename Symbol để cập nhật tham chiếu"]
    C --> D["Xem diff: chỉ các định danh mong muốn thay đổi?"]
    D --> E["Compile và chạy unit tests"]
    E --> F{"Có API / dữ liệu / cấu hình phụ thuộc tên?"}
    F -- "Có" --> G["Kiểm tra consumer, reflection, serialization, migration"]
    F -- "Không" --> H["Hoàn tất refactor"]
    G --> H
~~~

1. **Đọc chính method/class được đổi tên:** xác định ý nghĩa, điều kiện, kết quả và side effect. Không đoán qua tên cũ.
2. **Chọn tên mới:** thể hiện đúng hành động/đối tượng/đơn vị/trạng thái, giữ nhất quán với ngôn ngữ miền của dự án.
3. **Dùng refactor Rename của IDE:** IntelliJ IDEA thường dùng **Shift+F6**, VS Code với Java tooling thường dùng **F2**. Tính năng này tìm các tham chiếu theo symbol, an toàn hơn thao tác tìm-thay-chuỗi toàn file.
4. **Kiểm tra diff và các nơi gọi:** constructor, method reference, override/implements, test, annotation, cấu hình và tài liệu liên quan. Xem cả phạm vi nhiều module nếu symbol được dùng chéo module.
5. **Chạy compile và kiểm thử:** so sánh hành vi trước/sau. Với API public hoặc storage, kiểm chứng các consumer và dữ liệu thực tế.
6. **Giữ thay đổi nhỏ:** commit refactor đổi tên riêng với sửa logic nghiệp vụ sẽ dễ review, truy lỗi và revert hơn (chỉ thực hiện commit khi quy trình dự án yêu cầu).

Nếu chỉ đổi tên biến cục bộ bằng công cụ hỗ trợ, rủi ro thường thấp. Đổi tên method public, property hoặc tên lớp dùng bên ngoài có thể cần kế hoạch tương thích/migration.

## Ranh giới quan trọng: tên trong source chưa chắc là tên trong runtime

| Trường hợp | Điều có thể hỏng | Hướng xử lý |
|---|---|---|
| Đổi method trong interface công khai | Dự án khác biên dịch lỗi; client nhị phân có thể lỗi khi liên kết | Cập nhật các consumer, version API hoặc duy trì adapter/deprecated method theo chính sách |
| Đổi field trong JSON payload | Contract của API đổi, client đọc field cũ thất bại | Giữ tên wire bằng annotation phù hợp (ví dụ `@JsonProperty`) hoặc làm migration có version |
| Đổi tên property của JPA entity | Có thể tác động mapping, query theo property, hoặc schema nếu đang dựa quy ước đặt tên | Kiểm tra `@Column`, derived queries, JPQL, migrations và integration test |
| Đổi tên `@Bean`, `@Qualifier` hoặc component | Dependency injection dựa tên có thể không tìm đúng bean | Kiểm tra cấu hình bean và khởi động context test |
| Tên method/field được dùng trong reflection | String literal cũ không tự cập nhật khi Rename Symbol | Tìm tất cả lời gọi reflection, tên trong config/test, cập nhật và chạy thử |
| Đổi tên file/class/package public | Build, import, resource/config hoặc caller có thể lệch | Refactor bằng IDE, xem cả test, build scripts và external references |

Ví dụ rename tên field Java nhưng vẫn bảo vệ contract JSON công khai (khi dự án có Jackson):

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public final class PaymentResponse {
    private long payableAmountVnd;

    @JsonProperty("total")
    public long getPayableAmountVnd() {
        return payableAmountVnd;
    }
}
~~~

Trong ví dụ này, tên JSON `"total"` được gắn **trên getter** để bảo vệ tên field khi serialize. Đoạn trích chỉ minh họa chiều đọc ra; muốn deserialize đúng contract cần constructor/setter hoặc cấu hình creator phù hợp. Đây chỉ là minh họa mapping: nếu ứng dụng thực tế có setter, constructor, record, chiến lược serialization hoặc visibility rule khác, hãy kiểm chứng JSON input/output thực tế bằng test. Import Jackson ở đoạn này thuộc dự án có dependency tương ứng, **không nằm trong file Java chạy độc lập phía trên**.

Với Java, đổi tên method được `@Override` còn phải đồng bộ với hợp đồng của interface/superclass; nếu interface thuộc thư viện bên ngoài, không thể tùy tiện đổi signature mà vẫn bảo đảm implement đúng.

## Khi nào tên mới chưa đủ?

Có lúc vấn đề lớn hơn tên gọi. Ví dụ:

~~~java
void processOrder(Order order);
~~~

Nếu method vừa kiểm tra tồn kho, thanh toán, cập nhật đơn và gửi email, đổi thành `processValidatedOrderAndChargeAndSendEmail` vẫn không làm trách nhiệm rõ ràng. Khi đó nên cân nhắc **Extract Method**, **Extract Class** hoặc thiết kế collaborator theo trách nhiệm, mỗi bước có tên riêng. Đó là những refactoring khác, cần được đánh giá và kiểm thử độc lập.

Tương tự, `calculatePayableAmountVnd(orderLines, true)` vẫn khiến người đọc tại **call site** phải tự nhớ ý nghĩa của `true`. Đặt tên tham số tốt giúp phần khai báo, nhưng Java không hỗ trợ named argument. Nếu bài toán phức tạp, có thể cân nhắc method tường minh hơn hoặc enum cho lựa chọn nghiệp vụ. Đổi chữ ký/enum là bước thay đổi API riêng, không nên ngụy trang thành rename.

## Bài tập tự kiểm tra

**Bài 1 — Tìm tên ý định:** đề xuất tên đúng cho các đoạn sau, sau khi xác minh logic thật:

~~~java
boolean a = invoice.getDueDate().isBefore(today) && !invoice.isPaid();
int n = cart.getItems().size();
long t = priceCents * quantity;
~~~

Gợi ý: `isInvoiceOverdue` (nếu business rule cho rằng quá hạn và chưa thanh toán), `cartItemCount`, `lineAmountCents`.

**Bài 2 — Giữ nguyên hành vi:** trong file `RenameForIntentDemo.java`, đổi method `After.calculatePayableAmountVnd` thành `calculateOrderPayableAmountVnd` bằng Rename Symbol, kiểm tra lời gọi tại `main` được cập nhật, rồi chạy lại chương trình. Console vẫn cần báo `PASS`.

**Bài 3 — Nhận diện rủi ro:** có API trả JSON với field `"total"`. Đề xuất cách đổi tên Java field thành `payableAmountVnd` mà client hiện tại vẫn nhận `"total"`, và viết bài test serialization nếu dự án có Jackson.

**Tự đánh giá:** giải thích vì sao đổi `flag` thành `includeDeliveryFee` là rename, còn đổi `boolean includeDeliveryFee` thành `ShippingMethod shippingMethod` là thiết kế lại hợp đồng; nêu bài test nào chứng minh không thay đổi tổng tiền.

Đổi tên đạt chất lượng khi người đọc hiểu **đối tượng làm gì, dữ liệu có nghĩa gì, điều kiện đại diện cho điều gì** ngay tại vị trí sử dụng; mã vẫn chạy cùng hành vi mong đợi, và các hợp đồng ngoài source được xem xét đầy đủ.