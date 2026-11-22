# Tách phương thức và tách lớp (Extract Method / Extract Class) trong Java OOP

## 1. Vì sao cần tách?

Khi một phương thức ngày càng dài, nó thường làm nhiều việc: kiểm tra dữ liệu, tính toán, cập nhật trạng thái, tạo thông báo, gọi dịch vụ ngoài. Khi một lớp chứa quá nhiều nhóm trách nhiệm khác nhau, chỉ một thay đổi nhỏ cũng buộc ta đọc, sửa và kiểm thử cả lớp.

**Tái cấu trúc (refactoring)** là cải thiện cấu trúc bên trong mà **giữ nguyên hành vi quan sát được**. Hai kỹ thuật cơ bản:

- **Extract Method (Tách phương thức):** chọn một nhóm câu lệnh có mục đích rõ ràng, đặt chúng vào phương thức có tên mô tả ý định, rồi thay nhóm câu lệnh cũ bằng lời gọi phương thức đó.
- **Extract Class (Tách lớp):** chuyển một nhóm dữ liệu và hành vi có trách nhiệm riêng sang lớp mới; lớp ban đầu giao việc cho lớp mới thông qua giao diện rõ ràng.

Hai kỹ thuật có thể kết hợp: đầu tiên tách các bước của một phương thức dài, sau đó phát hiện một số phương thức thuộc trách nhiệm của lớp khác và chuyển chúng sang lớp đó.

**Kết quả mong đợi:** code dễ đọc hơn, trách nhiệm rõ hơn, dễ tái sử dụng và kiểm thử; các giá trị trả về, exception, tác dụng phụ và quy tắc nghiệp vụ đã cam kết vẫn tương đương.

| Tiêu chí | Extract Method | Extract Class |
|---|---|---|
| Dấu hiệu | Một phương thức thực hiện nhiều bước độc lập về ý nghĩa | Một lớp chứa nhiều nhóm lý do phải thay đổi |
| Thao tác | Tách đoạn code sang method có tên rõ | Chuyển field/method liên quan sang object mới |
| Mức thay đổi | Chủ yếu tổ chức nội bộ của một lớp | Phân chia trách nhiệm giữa các đối tượng |
| Ví dụ | Tách calculateSubtotal, applyDiscount | Tách PricingPolicy và ReceiptFormatter khỏi CheckoutService |
| Lỗi hay gặp | Quá nhiều method một dòng, truyền quá nhiều tham số, đổi thứ tự side effect | Tạo lớp rỗng nghĩa, làm lộ dữ liệu, circular dependency, phân mảnh quá mức |

## 2. Dấu hiệu nên bắt đầu

Một số tín hiệu hữu ích (không phải quy tắc tuyệt đối):

1. Bạn phải đọc rất nhiều dòng mới hiểu một thao tác nghiệp vụ.
2. Trong cùng một hàm, các đoạn code có thể được mô tả bằng những tên mục đích khác nhau: *validate → calculate → format → persist*.
3. Một lớp đổi vì nhiều nguyên nhân không liên quan: thay quy tắc giá **hoặc** thay cách trình bày hóa đơn.
4. Nhiều phương thức cùng dùng một tập field và hầu như không cần phần còn lại của lớp; đó là một nhóm có độ gắn kết (cohesion) riêng.
5. Kiểm thử một quy tắc nhỏ buộc phải khởi tạo nhiều dependency không liên quan.

Độ dài chỉ là **tín hiệu**. Một method 40 dòng mô tả một thuật toán tuyến tính, rõ ràng có thể dễ bảo trì hơn 10 method vụn. Mục tiêu là tăng **cohesion**, giảm coupling, giữ ý nghĩa nghiệp vụ và đường dữ liệu rõ ràng.

## 3. Tách phương thức: cách làm từng bước

Giả sử hàm checkout đang chứa tất cả logic đơn hàng:

~~~java
// Phác thảo cấu trúc ban đầu:
CheckoutResult checkout(Order order) {
    // (1) Kiểm tra đơn hàng
    // (2) Cộng giá trị từng dòng
    // (3) Tính giảm giá VIP
    // (4) Tính phí vận chuyển
    // (5) Định dạng chuỗi biên nhận
    // (6) Trả kết quả
}
~~~

Ta có thể đặt tên cụ thể cho các bước thuần tính toán:

~~~java
// Phác thảo sau Extract Method:
CheckoutResult checkout(Order order) {
    long subtotal = calculateSubtotal(order);
    long discount = calculateDiscount(subtotal, order.vip);
    long payable = Math.subtractExact(subtotal, discount);
    long shipping = calculateShipping(payable);
    long total = Math.addExact(payable, shipping);
    String receipt = formatReceipt(subtotal, discount, shipping, total);
    return new CheckoutResult(
            subtotal, discount, shipping, total, receipt);
}
~~~

Các method như calculateDiscount hoặc calculateShipping có thể là private và có đầu vào/đầu ra rõ ràng. Nếu một đoạn cần dùng hoặc sửa quá nhiều biến cục bộ, hãy xác định chính xác dữ liệu cần truyền/giá trị cần trả về, thay vì biến chúng thành field chung để có thể truy cập từ mọi nơi.

Quy trình Extract Method an toàn:

1. Chạy test hoặc xác định một bộ trường hợp đầu vào/đầu ra hiện tại để làm mốc.
2. Chọn khối lệnh có mục đích độc lập; đặt tên theo **việc nó làm**, không chỉ theo thao tác kỹ thuật.
3. Phân tích biến được đọc, biến được cập nhật, giá trị trả về, exception và side effect.
4. Tạo method; chuyển chính xác khối lệnh, truyền dependency cần thiết bằng tham số; thay code cũ bằng lời gọi.
5. Biên dịch và chạy lại test ngay sau mỗi bước nhỏ.
6. Tiếp tục tách nếu mục đích mới rõ hơn, dừng nếu việc tách chỉ làm code khó lần theo.

Ví dụ: tên **calculateShipping** diễn đạt mục đích tốt hơn **processStep4**. Tránh truyền nguyên đối tượng lớn chỉ để dùng một field, nếu truyền một giá trị cụ thể khiến hợp đồng dễ hiểu hơn; nhưng cũng tránh danh sách 10 tham số bằng cách chọn một parameter object thật sự có ý nghĩa.

## 4. Tách lớp: phân biệt trách nhiệm

Sau khi tách các method, giả sử CheckoutService có hai nhóm:

- **Định giá:** subtotal, giảm giá VIP, phí vận chuyển, tổng tiền.
- **Trình bày:** định dạng biên nhận để hiển thị.

Chúng thay đổi vì các lý do khác nhau. Ta chuyển nhóm thứ nhất sang **PricingPolicy**, nhóm thứ hai sang **ReceiptFormatter**, giữ **CheckoutService** làm lớp điều phối.

~~~mermaid
flowchart TB
    subgraph BEFORE["Trước"]
        A["CheckoutService: kiểm tra + tính giá + định dạng"]
    end
    subgraph AFTER["Sau"]
        B["CheckoutService: điều phối"] --> C["PricingPolicy: quy tắc tiền"]
        B --> D["ReceiptFormatter: trình bày"]
    end
~~~

Đây là ứng dụng của **Single Responsibility Principle (SRP)**: mỗi lớp nên có một nhóm lý do thay đổi rõ ràng. SRP không có nghĩa mỗi lớp chỉ có đúng một method. Việc tách cũng khuyến khích phụ thuộc vào abstraction khi có nhu cầu thay thế implementation, nhưng không bắt buộc tạo interface cho mọi lớp.

## 5. Chương trình Java hoàn chỉnh: so sánh trước/sau refactor

Ví dụ giữ cùng yêu cầu nghiệp vụ cho cả hai phiên bản:

- Một đơn hàng có ít nhất một dòng. SKU không rỗng, số lượng dương, đơn giá không âm.
- **subtotal** là tổng của đơn giá nhân số lượng; dùng số nguyên VND để tránh sai lệch do float/double.
- Nếu khách VIP và subtotal từ **500.000 VND**, giảm **10% subtotal**, làm tròn xuống theo chia số nguyên.
- Phí vận chuyển là **0 VND** nếu số tiền sau giảm giá từ **700.000 VND**, ngược lại **30.000 VND**.
- **total = subtotal − discount + shipping**.
- Biên nhận có định dạng chuỗi cố định như ví dụ.
- Các phép toán dùng Math.addExact, multiplyExact, subtractExact để lỗi tràn số không âm thầm thay đổi kết quả.

Lưu toàn bộ vào **OrderRefactoringDemo.java**. Đây là chương trình tự chạy với **Java 11+**, không cần dependency ngoài. Phiên bản LegacyCheckout gom nghiệp vụ trong một method; phiên bản sau refactor chia thành PricingPolicy, ReceiptFormatter và CheckoutService.

~~~java
import java.util.List;
import java.util.Objects;

public class OrderRefactoringDemo {
    static final long VIP_MIN_SUBTOTAL = 500_000L;
    static final long FREE_SHIPPING_MIN = 700_000L;
    static final long SHIPPING_FEE = 30_000L;

    static final class Item {
        final String sku;
        final long unitPriceVnd;
        final int quantity;

        Item(String sku, long unitPriceVnd, int quantity) {
            this.sku = sku;
            this.unitPriceVnd = unitPriceVnd;
            this.quantity = quantity;
        }
    }

    static final class Order {
        final List<Item> items;
        final boolean vip;

        Order(List<Item> items, boolean vip) {
            this.items = items;
            this.vip = vip;
        }
    }

    static final class CheckoutResult {
        final long subtotal;
        final long discount;
        final long shipping;
        final long total;
        final String receipt;

        CheckoutResult(long subtotal, long discount, long shipping,
                       long total, String receipt) {
            this.subtotal = subtotal;
            this.discount = discount;
            this.shipping = shipping;
            this.total = total;
            this.receipt = receipt;
        }
    }

    // TRƯỚC: một phương thức phải xử lý nhiều trách nhiệm.
    static final class LegacyCheckout {
        CheckoutResult checkout(Order order) {
            if (order == null || order.items == null
                    || order.items.isEmpty()) {
                throw new IllegalArgumentException("Empty order");
            }

            long subtotal = 0L;
            for (Item item : order.items) {
                if (item == null || item.sku == null
                        || item.sku.isBlank()
                        || item.unitPriceVnd < 0 || item.quantity <= 0) {
                    throw new IllegalArgumentException("Invalid item");
                }

                long lineTotal = Math.multiplyExact(
                        item.unitPriceVnd, (long) item.quantity);
                subtotal = Math.addExact(subtotal, lineTotal);
            }

            long discount = order.vip && subtotal >= VIP_MIN_SUBTOTAL
                    ? subtotal / 10 : 0L;
            long payable = Math.subtractExact(subtotal, discount);
            long shipping = payable >= FREE_SHIPPING_MIN
                    ? 0L : SHIPPING_FEE;
            long total = Math.addExact(payable, shipping);

            String receipt = "subtotal=" + subtotal
                    + ",discount=" + discount
                    + ",shipping=" + shipping
                    + ",total=" + total;

            return new CheckoutResult(
                    subtotal, discount, shipping, total, receipt);
        }
    }

    // KẾT QUẢ TÍNH TOÁN: dữ liệu cho lớp trình bày.
    static final class Pricing {
        final long subtotal;
        final long discount;
        final long shipping;
        final long total;

        Pricing(long subtotal, long discount, long shipping, long total) {
            this.subtotal = subtotal;
            this.discount = discount;
            this.shipping = shipping;
            this.total = total;
        }
    }

    // Extract Class: gom các quy tắc định giá liên quan.
    static final class PricingPolicy {
        Pricing calculate(Order order) {
            long subtotal = calculateSubtotal(order);
            long discount = calculateDiscount(subtotal, order.vip);
            long payable = Math.subtractExact(subtotal, discount);
            long shipping = calculateShipping(payable);
            long total = Math.addExact(payable, shipping);

            return new Pricing(subtotal, discount, shipping, total);
        }

        // Extract Method: đọc và kiểm tra dữ liệu, rồi cộng tiền.
        private long calculateSubtotal(Order order) {
            if (order == null || order.items == null
                    || order.items.isEmpty()) {
                throw new IllegalArgumentException("Empty order");
            }

            long subtotal = 0L;
            for (Item item : order.items) {
                if (item == null || item.sku == null
                        || item.sku.isBlank()
                        || item.unitPriceVnd < 0 || item.quantity <= 0) {
                    throw new IllegalArgumentException("Invalid item");
                }

                long lineTotal = Math.multiplyExact(
                        item.unitPriceVnd, (long) item.quantity);
                subtotal = Math.addExact(subtotal, lineTotal);
            }
            return subtotal;
        }

        private long calculateDiscount(long subtotal, boolean vip) {
            return vip && subtotal >= VIP_MIN_SUBTOTAL
                    ? subtotal / 10 : 0L;
        }

        private long calculateShipping(long payable) {
            return payable >= FREE_SHIPPING_MIN ? 0L : SHIPPING_FEE;
        }
    }

    // Extract Class: cách trình bày thay đổi độc lập với quy tắc giá.
    static final class ReceiptFormatter {
        String format(Pricing pricing) {
            return "subtotal=" + pricing.subtotal
                    + ",discount=" + pricing.discount
                    + ",shipping=" + pricing.shipping
                    + ",total=" + pricing.total;
        }
    }

    // SUT sau refactor: đọc như một quy trình điều phối.
    static final class CheckoutService {
        private final PricingPolicy pricingPolicy;
        private final ReceiptFormatter formatter;

        CheckoutService(PricingPolicy pricingPolicy,
                        ReceiptFormatter formatter) {
            this.pricingPolicy = Objects.requireNonNull(pricingPolicy);
            this.formatter = Objects.requireNonNull(formatter);
        }

        CheckoutResult checkout(Order order) {
            Pricing pricing = pricingPolicy.calculate(order);
            return new CheckoutResult(
                    pricing.subtotal,
                    pricing.discount,
                    pricing.shipping,
                    pricing.total,
                    formatter.format(pricing));
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private static void checkEquivalent(
            LegacyCheckout oldVersion,
            CheckoutService newVersion,
            Order input,
            long expectedTotal) {
        CheckoutResult oldResult = oldVersion.checkout(input);
        CheckoutResult newResult = newVersion.checkout(input);

        check(oldResult.subtotal == newResult.subtotal, "subtotal changed");
        check(oldResult.discount == newResult.discount, "discount changed");
        check(oldResult.shipping == newResult.shipping, "shipping changed");
        check(oldResult.total == newResult.total, "total changed");
        check(oldResult.receipt.equals(newResult.receipt),
                "receipt changed");
        check(newResult.total == expectedTotal, "incorrect total");
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Expected IllegalArgumentException");
    }

    public static void main(String[] args) {
        LegacyCheckout oldVersion = new LegacyCheckout();
        CheckoutService newVersion =
                new CheckoutService(new PricingPolicy(),
                                    new ReceiptFormatter());

        // subtotal = 600.000; VIP giảm 60.000;
        // sau giảm 540.000; phí 30.000 => 570.000.
        Order vipOrder = new Order(List.of(
                new Item("BOOK", 250_000L, 2),
                new Item("PEN", 100_000L, 1)), true);
        checkEquivalent(oldVersion, newVersion, vipOrder, 570_000L);

        // Không VIP: 100.000 + phí 30.000 = 130.000.
        Order normalOrder = new Order(
                List.of(new Item("PEN", 100_000L, 1)), false);
        checkEquivalent(oldVersion, newVersion, normalOrder, 130_000L);

        // VIP: subtotal 800.000, giảm 80.000,
        // sau giảm 720.000, miễn phí vận chuyển.
        Order freeShippingOrder = new Order(
                List.of(new Item("BOOK", 400_000L, 2)), true);
        checkEquivalent(oldVersion, newVersion,
                freeShippingOrder, 720_000L);

        // Cả hai phiên bản từ chối quantity không hợp lệ.
        Order invalid = new Order(
                List.of(new Item("BOOK", 100_000L, 0)), false);
        expectInvalid(() -> oldVersion.checkout(invalid));
        expectInvalid(() -> newVersion.checkout(invalid));

        System.out.println("3 equivalent cases + invalid input: PASS");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac OrderRefactoringDemo.java
java OrderRefactoringDemo
~~~

Đầu ra kỳ vọng:

~~~text
3 equivalent cases + invalid input: PASS
~~~

Ví dụ này **không chỉ so sánh tổng tiền**: nó so sánh subtotal, discount, shipping, total và cả chuỗi receipt; đồng thời xác minh hai phiên bản đều từ chối cùng một loại input sai. Khi refactor có tác dụng phụ hoặc làm việc với hệ thống ngoài, cần bổ sung kiểm thử những hiệu ứng quan sát được ở ranh giới tương ứng.

**Giới hạn ví dụ:** Chương trình mô phỏng việc tính giá thuần trong bộ nhớ, chưa có repository, transaction, gửi email hay số lượng lớn. Trong ứng dụng thật, kiểm thử thêm trạng thái database, thứ tự side effect có ý nghĩa, tính an toàn luồng và lỗi tích hợp trước khi kết luận hành vi được giữ nguyên.

## 6. Nhận diện trách nhiệm sau khi tách

| Thành phần | Trách nhiệm hiện tại | Lý do có thể thay đổi |
|---|---|---|
| Order / Item | Dữ liệu đơn hàng và dòng hàng | Hợp đồng dữ liệu |
| PricingPolicy | Kiểm tra đầu vào và tính giá, giảm giá, phí | Chính sách bán hàng |
| Pricing | Kết quả tính toán đã xác định | Cấu trúc dữ liệu giá |
| ReceiptFormatter | Chuyển kết quả định giá thành chuỗi | Yêu cầu hiển thị |
| CheckoutService | Gọi PricingPolicy rồi ReceiptFormatter | Luồng nghiệp vụ phối hợp |

Việc truyền PricingPolicy và ReceiptFormatter qua constructor là **dependency injection** đơn giản. Không bắt buộc phải dùng Spring. Khi cần nhiều biến thể giá/định dạng, có thể cân nhắc interface tương ứng; với một implementation duy nhất, class cụ thể đã đủ rõ.

**Khi nào giữ một method trong lớp cũ?** Nếu nó sử dụng phần lớn trạng thái và nằm sát trách nhiệm cốt lõi của lớp. Extract Class nên chuyển cả nhóm hành vi và dữ liệu thật sự gắn nhau, thay vì chỉ tạo một lớp "Utils" chứa nhiều static method không liên quan.

## 7. Những rủi ro cần kiểm tra trước khi gọi là refactor thành công

### Đổi thứ tự xử lý hoặc hiệu ứng ngoài

Trong ví dụ thuần tính toán, chuyển method có ít rủi ro. Nhưng đổi thứ tự *thanh toán → trừ kho → ghi log/gửi email* có thể làm thay đổi business rule. Nếu refactor dính transaction, lock, retry hoặc event, phải giữ nguyên các bất biến và ranh giới transaction đã cam kết.

### Đổi thời điểm ném exception

Khi chuyển validation sang lớp khác, lỗi có thể xuất hiện sớm hoặc muộn hơn. Ví dụ nếu dòng đầu gây tràn số và dòng sau không hợp lệ, đưa validation toàn giỏ hàng lên đầu sẽ đổi exception quan sát được. Với hệ thống có contract về exception hoặc side effect, giữ đúng thứ tự và viết test thích hợp trước khi di chuyển logic.

### Làm lộ chi tiết dữ liệu

Tránh biến toàn bộ field private thành public chỉ để lớp mới truy cập. Có thể dùng đối tượng giá trị bất biến, method truy vấn có ý nghĩa, hoặc chuyển ownership của trạng thái sang lớp chuyên trách.

### Tạo phụ thuộc vòng tròn

CheckoutService phụ thuộc PricingPolicy là hợp lý; nếu PricingPolicy lại phải gọi ngược CheckoutService, trách nhiệm đang bị chia thiếu rõ ràng. Thiết kế hướng phụ thuộc một chiều, tránh để các lớp nắm tham chiếu lẫn nhau chỉ để truy cập helper.

### Tách quá nhỏ

Một lớp có đúng một dòng chuyển tiếp sang lớp khác chưa chắc hữu ích. Nếu mỗi phép cộng là một lớp hoặc một method thì độ phân mảnh sẽ tăng. Tách theo ý nghĩa nghiệp vụ, cohesion và lý do thay đổi, không theo mục tiêu tối đa số file.

### Vô tình thay đổi hiệu năng hoặc luồng dữ liệu

Di chuyển method có thể tạo copy bộ sưu tập, cache khác vòng đời hoặc gọi dependency nhiều hơn. Nếu hiệu năng, identity, thứ tự, khả năng song song hoặc idempotency là phần hợp đồng, hãy có phép kiểm tra tương ứng. Chú ý khác biệt Java reference, đối tượng mutable và data race khi chuyển state sang lớp dùng chung.

## 8. Test trước và sau khi refactor

Một trình tự thực tế:

1. **Characterization tests:** ghi lại hành vi hiện tại của code cũ trong các kịch bản quan trọng, đặc biệt khi chưa có test.
2. **Extract Method nhỏ:** chuyển một khối lệnh và chạy lại các test liên quan.
3. **Extract Class theo trách nhiệm:** di chuyển phương thức/field, cập nhật dependency trong constructor và caller.
4. **Kiểm tra tương đương:** kết quả, exception, trạng thái và các side effect có ý nghĩa.
5. **Chạy unit + integration test:** những đường nối với database, API, transaction phải được kiểm chứng thật khi cần.
6. **Review phạm vi diff:** những thay đổi chính sách nghiệp vụ nên được tách khỏi refactor để dễ phát hiện regression.

Đối với code gốc có lỗi đã biết, đừng vô tình đổi hành vi khi tuyên bố "refactor thuần". Có thể tạo một thay đổi riêng để sửa lỗi với test mô tả hành vi mong đợi mới.

Ví dụ, nếu chính sách giá phải đổi từ giảm 10% thành 15%, hãy thực hiện việc đó **sau** một lần refactor bảo toàn hành vi, có test độc lập. Khi một commit vừa tách lớp vừa thay quy tắc, nếu test đỏ khó xác định nguyên nhân.

## 9. Bài tập thực hành

**Bài 1 — Extract Method:** Trong LegacyCheckout, tách riêng tính subtotal, giảm giá, phí vận chuyển và định dạng. Sau mỗi bước chạy lại cùng bộ test; giải thích đầu vào/đầu ra của từng method.

**Bài 2 — Extract Class:** Chuyển riêng trách nhiệm ReceiptFormatter và kiểm tra việc đổi định dạng không đòi sửa PricingPolicy. Phân tích vì sao đây là sự cải thiện cohesion.

**Bài 3 — Ca biên:** Bổ sung test subtotal đúng 500.000 cho VIP, payable đúng 700.000, đơn rỗng, giá âm, số lượng 0 và số tiền vượt giới hạn long. Chạy cả hai phiên bản để kiểm tra tương đương.

**Bài 4 — Phát hiện thay đổi hành vi:** Cố tình tính phí vận chuyển trên subtotal trước giảm giá thay vì payable sau giảm giá. Viết một input làm hai kết quả khác nhau để test bắt regression.

**Bài 5 — Thiết kế lại:** Nếu có chính sách giảm giá cho nhiều quốc gia hoặc nhiều loại khách, cân nhắc interface DiscountPolicy. Giải thích khi nào chiến lược thay thế (Strategy) tốt hơn việc tiếp tục thêm nhiều nhánh if trong PricingPolicy, và khi nào interface là quá sớm.

## 10. Kết luận

**Extract Method** đặt tên cho các bước có mục đích rõ ràng để method chính dễ đọc hơn. **Extract Class** gom dữ liệu và hành vi theo trách nhiệm, để mỗi phần thay đổi độc lập hơn. Cả hai là tái cấu trúc chỉ khi **hợp đồng quan sát được vẫn giữ nguyên**. Tách từng bước nhỏ, đặt tên theo nghiệp vụ, kiểm tra trước/sau và dừng khi sự phân chia giúp người đọc hiểu hệ thống tốt hơn.