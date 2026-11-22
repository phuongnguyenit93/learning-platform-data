# Bài tập thực hành: Tái cấu trúc mã thủ tục thành mô hình đối tượng (Java)

**Chủ đề:** OOP → Thực hành → Bài tập tái cấu trúc đoạn mã thủ tục thành mô hình đối tượng  
**Mức độ:** Trung cấp | **Yêu cầu:** Java 17 trở lên, JDK, terminal; không cần thư viện ngoài.

## 1. Bối cảnh và yêu cầu

Một ứng dụng bán hàng có hàm tính tiền đơn hàng. Phiên bản ban đầu dồn dữ liệu, kiểm tra loại khách hàng, tính giảm giá và phí giao hàng vào cùng một hàm thủ tục. Khi chính sách đổi hoặc cần tái sử dụng từng quy tắc, hàm khó kiểm thử và dễ phát sinh lỗi.

**Luật nghiệp vụ cần giữ nguyên đối với dữ liệu hợp lệ:**

1. Tạm tính = đơn giá × số lượng; mọi khoản tiền được biểu diễn bằng số nguyên VND.
2. Khách VIP được giảm **10% tạm tính**, phần lẻ VND bị bỏ (chia nguyên); khách REGULAR không giảm.
3. Sau khi giảm giá, nếu số tiền đạt **1.000.000 VND trở lên**, miễn phí giao hàng.
4. Nếu chưa đủ ngưỡng miễn phí: giao NORMAL = 20.000 VND, EXPRESS = 50.000 VND.
5. Tổng thanh toán = tạm tính − giảm giá + phí giao hàng.

**Kết quả mong đợi:** Tổ chức lại mô hình thành các đối tượng có trách nhiệm rõ ràng, giấu trạng thái nội bộ, thay chuỗi phân loại bằng kiểu an toàn, tách chính sách chiết khấu khỏi luồng thanh toán và chứng minh các kết quả tính tiền không đổi.

## 2. Đoạn mã thủ tục xuất phát

Giả sử mọi đầu vào đang hợp lệ và đây là logic ban đầu cần bảo toàn:

~~~java
public static long calculateTotal(
        String customerType, long unitPriceVnd,
        int quantity, String shippingMode) {

    long subtotal = Math.multiplyExact(unitPriceVnd, quantity);

    long discount = "VIP".equals(customerType)
            ? subtotal / 10 : 0;

    long afterDiscount = subtotal - discount;

    long shippingFee;
    if (afterDiscount >= 1_000_000L) {
        shippingFee = 0L;
    } else if ("EXPRESS".equals(shippingMode)) {
        shippingFee = 50_000L;
    } else {
        shippingFee = 20_000L;
    }

    return Math.addExact(afterDiscount, shippingFee);
}
~~~

**Nhận xét về thiết kế, không chỉ về cú pháp:**

- Hàm vừa nhận dữ liệu, vừa hiểu loại khách, vừa định giá, vừa chọn phí giao hàng; nhiều lý do có thể khiến nó thay đổi.
- Giá trị chuỗi dễ bị nhập sai: ví dụ "vip" sẽ bị xử lý như REGULAR; "EXPREES" sẽ bị xử lý như NORMAL mà không báo lỗi.
- Chính sách giảm giá bị gắn cứng vào hàm, nên thêm loại khách hàng sẽ phải sửa logic điều phối.
- Kết quả chỉ là một số tổng; màn hình hóa đơn không biết phần tiền giảm hoặc phí giao hàng riêng.
- Chưa có ranh giới rõ ràng cho dữ liệu không hợp lệ (đơn giá âm, số lượng bằng 0).

**Lưu ý:** Bài này cải thiện thiết kế và bổ sung kiểm tra hợp lệ. Việc từ chối đầu vào sai là thay đổi hành vi có chủ đích; chỉ kết quả cho đầu vào hợp lệ được yêu cầu giữ nguyên.

## 3. Nhiệm vụ tự thực hiện

Làm từng bước trước khi xem lời giải:

1. **Đóng gói dữ liệu:** tạo lớp Order giữ đơn giá, số lượng, loại khách, hình thức giao; không cho sửa tùy tiện sau khi tạo. Đưa việc tính tạm tính vào Order.
2. **Thay magic string:** dùng enum CustomerType { REGULAR, VIP } và ShippingMode { NORMAL, EXPRESS }.
3. **Tách chính sách:** khai báo DiscountPolicy và hai triển khai NoDiscount, VipDiscount. Mỗi chính sách chỉ trả về tiền giảm, không tự tính phí giao.
4. **Tách dịch vụ:** ShippingPolicy tính phí giao; CheckoutService phối hợp các đối tượng và trả về Receipt chứa từng khoản.
5. **Kiểm thử hồi quy:** so sánh kết quả của các ca REGULAR/VIP, NORMAL/EXPRESS, có/không miễn phí giao và ca sát ngưỡng 1.000.000 VND.
6. **Kiểm soát lỗi:** từ chối đơn giá âm, số lượng không dương, đối tượng bắt buộc bị null; không cho chính sách trả mức giảm âm hoặc vượt tạm tính.

Đừng tạo đối tượng chỉ để thay tên hàm. Hãy tự trả lời: mỗi đối tượng sở hữu dữ liệu/quy tắc gì, ai được quyền thay đổi nó và test nào xác nhận đúng trách nhiệm đó?

## 4. Phân chia trách nhiệm theo OOP

| Thành phần | Trách nhiệm duy nhất nổi bật | Điều cần tránh |
|---|---|---|
| Order | Nắm giữ dữ liệu đơn hàng hợp lệ, tính tạm tính | Biết cách tính giảm giá hoặc in hóa đơn |
| CustomerType, ShippingMode | Biểu diễn các lựa chọn nghiệp vụ hợp lệ | Truyền chuỗi tùy ý khắp hệ thống |
| DiscountPolicy | Hợp đồng tính tiền giảm trên tạm tính | Phụ thuộc trực tiếp vào giao hàng |
| NoDiscount, VipDiscount | Hiện thực hai quy tắc chiết khấu | Chèn if-else phân loại khách vào chính từng chính sách |
| ShippingPolicy | Tính phí từ số tiền sau giảm và hình thức giao | Tính lại tạm tính hoặc chiết khấu |
| CheckoutService | Điều phối, bảo vệ bất biến và tạo Receipt | Chứa chi tiết mọi chính sách |
| Receipt | Kết quả tính tiền có thể quan sát và kiểm thử | Âm thầm sửa số tiền trong lúc hiển thị |

~~~mermaid
classDiagram
    class Order {
      -CustomerType customerType
      -ShippingMode shippingMode
      -long unitPriceVnd
      -int quantity
      +subtotalVnd() long
    }
    class DiscountPolicy {
      <<interface>>
      +discountVnd(long) long
    }
    class NoDiscount
    class VipDiscount
    class ShippingPolicy {
      +feeVnd(long, ShippingMode) long
    }
    class CheckoutService {
      +checkout(Order) Receipt
    }
    class Receipt
    DiscountPolicy <|.. NoDiscount
    DiscountPolicy <|.. VipDiscount
    CheckoutService --> Order
    CheckoutService --> DiscountPolicy
    CheckoutService --> ShippingPolicy
    CheckoutService --> Receipt
~~~

**Ý đồ thiết kế:** Order bảo vệ trạng thái và cung cấp hành vi gắn với dữ liệu; DiscountPolicy dùng **đa hình** để chọn thuật toán tính giảm giá; CheckoutService dùng **composition** để phối hợp. ShippingPolicy hiện mới có một cách tính nên chưa cần tạo interface riêng.

## 5. Lời giải tham khảo hoàn chỉnh, chạy độc lập

Tạo một tệp **RefactorCheckout.java** và dán toàn bộ mã dưới đây. Các lớp lồng nhau chỉ giúp ví dụ nằm trong một tệp để chạy nhanh; trong dự án thực tế có thể tách thành các tệp cùng package.

~~~java
import java.util.Map;
import java.util.Objects;

public class RefactorCheckout {

    enum CustomerType { REGULAR, VIP }
    enum ShippingMode { NORMAL, EXPRESS }

    static final class Order {
        private final CustomerType customerType;
        private final ShippingMode shippingMode;
        private final long unitPriceVnd;
        private final int quantity;

        Order(CustomerType customerType, ShippingMode shippingMode,
              long unitPriceVnd, int quantity) {
            this.customerType =
                    Objects.requireNonNull(customerType, "customerType");
            this.shippingMode =
                    Objects.requireNonNull(shippingMode, "shippingMode");
            if (unitPriceVnd < 0) {
                throw new IllegalArgumentException("Unit price must be >= 0");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("Quantity must be > 0");
            }
            this.unitPriceVnd = unitPriceVnd;
            this.quantity = quantity;
        }

        CustomerType customerType() {
            return customerType;
        }

        ShippingMode shippingMode() {
            return shippingMode;
        }

        long subtotalVnd() {
            return Math.multiplyExact(unitPriceVnd, quantity);
        }
    }

    interface DiscountPolicy {
        long discountVnd(long subtotalVnd);
    }

    static final class NoDiscount implements DiscountPolicy {
        @Override
        public long discountVnd(long subtotalVnd) {
            return 0L;
        }
    }

    static final class VipDiscount implements DiscountPolicy {
        @Override
        public long discountVnd(long subtotalVnd) {
            return subtotalVnd / 10L;  // 10%, làm tròn xuống 1 VND
        }
    }

    static final class ShippingPolicy {
        long feeVnd(long afterDiscountVnd, ShippingMode mode) {
            Objects.requireNonNull(mode, "mode");
            if (afterDiscountVnd >= 1_000_000L) {
                return 0L;
            }
            return mode == ShippingMode.EXPRESS ? 50_000L : 20_000L;
        }
    }

    record Receipt(long subtotalVnd, long discountVnd,
                   long shippingVnd, long totalVnd) { }

    static final class CheckoutService {
        private final Map<CustomerType, DiscountPolicy> discountPolicies;
        private final ShippingPolicy shippingPolicy;

        CheckoutService(
                Map<CustomerType, DiscountPolicy> discountPolicies,
                ShippingPolicy shippingPolicy) {
            this.discountPolicies =
                    Map.copyOf(Objects.requireNonNull(discountPolicies));
            this.shippingPolicy =
                    Objects.requireNonNull(shippingPolicy);
        }

        Receipt checkout(Order order) {
            Objects.requireNonNull(order, "order");

            long subtotal = order.subtotalVnd();
            DiscountPolicy policy =
                    discountPolicies.get(order.customerType());

            if (policy == null) {
                throw new IllegalStateException(
                        "Missing policy for " + order.customerType());
            }

            long discount = policy.discountVnd(subtotal);
            if (discount < 0 || discount > subtotal) {
                throw new IllegalStateException("Invalid discount");
            }

            long afterDiscount = Math.subtractExact(subtotal, discount);
            long shipping =
                    shippingPolicy.feeVnd(afterDiscount, order.shippingMode());
            if (shipping < 0) {
                throw new IllegalStateException("Invalid shipping fee");
            }

            long total = Math.addExact(afterDiscount, shipping);
            return new Receipt(subtotal, discount, shipping, total);
        }
    }

    private static void expectTotal(
            CheckoutService checkout, Order order, long expected) {
        Receipt receipt = checkout.checkout(order);
        if (receipt.totalVnd() != expected) {
            throw new AssertionError(
                    "Expected " + expected + ", actual " + receipt);
        }
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            // Đầu vào sai đã bị từ chối đúng dự kiến.
        }
    }

    public static void main(String[] args) {
        CheckoutService checkout = new CheckoutService(
                Map.of(
                        CustomerType.REGULAR, new NoDiscount(),
                        CustomerType.VIP, new VipDiscount()),
                new ShippingPolicy());

        // VIP: 1.200.000 - 120.000 = 1.080.000, miễn phí giao.
        expectTotal(checkout,
                new Order(CustomerType.VIP, ShippingMode.EXPRESS,
                        400_000L, 3),
                1_080_000L);

        // REGULAR: 400.000 + 20.000 phí giao thường.
        expectTotal(checkout,
                new Order(CustomerType.REGULAR, ShippingMode.NORMAL,
                        400_000L, 1),
                420_000L);

        // VIP: 400.000 - 40.000 + 50.000 giao nhanh.
        expectTotal(checkout,
                new Order(CustomerType.VIP, ShippingMode.EXPRESS,
                        400_000L, 1),
                410_000L);

        // Tính ngưỡng miễn phí theo giá SAU giảm: 990.000 < 1.000.000.
        expectTotal(checkout,
                new Order(CustomerType.VIP, ShippingMode.NORMAL,
                        1_100_000L, 1),
                1_010_000L);

        // Đúng ngưỡng: 1.000.000, giao thường miễn phí.
        expectTotal(checkout,
                new Order(CustomerType.REGULAR, ShippingMode.NORMAL,
                        1_000_000L, 1),
                1_000_000L);

        expectInvalid(() -> new Order(
                CustomerType.REGULAR, ShippingMode.NORMAL, -1L, 1));
        expectInvalid(() -> new Order(
                CustomerType.VIP, ShippingMode.EXPRESS, 10_000L, 0));

        Receipt receipt = checkout.checkout(
                new Order(CustomerType.VIP, ShippingMode.EXPRESS,
                        400_000L, 1));
        System.out.println(receipt);
        System.out.println("PASS: 5 business cases + 2 invalid inputs");
    }
}
~~~

Chạy bằng:

~~~bash
javac RefactorCheckout.java
java RefactorCheckout
~~~

Kết quả mẫu:

~~~text
Receipt[subtotalVnd=400000, discountVnd=40000, shippingVnd=50000, totalVnd=410000]
PASS: 5 business cases + 2 invalid inputs
~~~

Trong chương trình thực tế, mỗi loại chính sách có thể nằm ở một lớp riêng. Map cấu hình chính sách được đưa vào qua constructor, nên CheckoutService không phải biết triển khai cụ thể nào tương ứng với từng loại khách. Nếu sau này thêm loại khách hàng, đăng ký chính sách mới tại điểm cấu hình sau khi cập nhật enum; không cần sửa thuật toán checkout.

## 6. Bộ ca kiểm thử bắt buộc

| Khách | Đơn giá × SL | Giao | Giảm giá | Phí giao | Tổng kỳ vọng |
|---|---:|---|---:|---:|---:|
| REGULAR | 400.000 × 1 | NORMAL | 0 | 20.000 | **420.000** |
| VIP | 400.000 × 1 | EXPRESS | 40.000 | 50.000 | **410.000** |
| VIP | 400.000 × 3 | EXPRESS | 120.000 | 0 | **1.080.000** |
| VIP | 1.100.000 × 1 | NORMAL | 110.000 | 20.000 | **1.010.000** |
| REGULAR | 1.000.000 × 1 | NORMAL | 0 | 0 | **1.000.000** |

Làm thêm bảng đối chiếu kết quả **trước/sau refactor** cho từng đầu vào hợp lệ. Hai bên phải có cùng tổng. Test sát ngưỡng miễn phí đặc biệt quan trọng: nếu vô tình xét tạm tính 1.100.000 trước giảm, ca VIP ở hàng thứ tư sẽ miễn phí sai.

**Kiểm thử lỗi nên có:** null CustomerType/ShippingMode, số lượng 0 hoặc âm, giá âm, thiếu DiscountPolicy cho một loại khách, chính sách trả giá trị âm hoặc lớn hơn tạm tính, và phép nhân/cộng vượt giới hạn long. Đoạn mẫu dùng Math.multiplyExact/Math.addExact để báo ArithmeticException khi tràn số thay vì âm thầm trả kết quả sai. Không cần dùng double cho tiền VND; nếu xử lý tiền có phần thập phân hoặc nhiều đơn vị tiền tệ, cân nhắc BigDecimal kèm quy tắc làm tròn rõ ràng.

## 7. Cách refactor an toàn trên codebase thật

~~~mermaid
flowchart TD
    A[Chốt đầu vào và luật hiện hữu] --> B[Viết characterization tests]
    B --> C[Đưa dữ liệu vào Order]
    C --> D[Thay chuỗi phân loại bằng enum]
    D --> E[Tách DiscountPolicy và ShippingPolicy]
    E --> F[Đưa luồng điều phối vào CheckoutService]
    F --> G[So sánh đầu ra trước và sau]
    G --> H{Các ca đều khớp?}
    H -- Không --> I[Định vị khác biệt và sửa]
    I --> G
    H -- Có --> J[Xóa đường xử lý cũ, giữ test]
~~~

Đề xuất mỗi lần chỉ thực hiện một thay đổi có thể kiểm chứng: **Extract Class → Encapsulate Field → Extract Method → Introduce Strategy → Move Method**. Chạy test sau từng bước. Nếu hệ thống cũ cho phép giá âm hoặc tên loại khách tùy ý, ghi rõ quyết định siết validation thành thay đổi nghiệp vụ riêng và bổ sung test cho nó; không nhầm lỗi do refactor với hành vi mới.

### Dấu hiệu đã làm tốt

- Mỗi lớp có mục đích giải thích được trong một câu; các trường của Order là private final.
- Thêm một cách tính chiết khấu mới chủ yếu là thêm triển khai DiscountPolicy và đăng ký nó tại điểm cấu hình.
- Không có nhánh so sánh "VIP" hoặc "EXPRESS" rải rác trong CheckoutService.
- Đơn giá, số lượng và kiểu giao không bị người gọi chỉnh sửa trực tiếp sau khi tạo Order.
- Receipt cung cấp đầy đủ tạm tính, giảm, giao và tổng để xuất hóa đơn và kiểm thử.
- Test kiểm tra các kết quả nghiệp vụ, không chỉ kiểm tra tên lớp hoặc getter.

### Những lỗi thiết kế dễ gặp

- **God object:** chuyển nguyên hàm cũ vào Order rồi cho Order làm cả giảm giá, phí giao, in hóa đơn.
- **Anemic model cực đoan:** Order chỉ còn getter/setter công khai, toàn bộ hành vi liên quan dữ liệu lại nằm ở tiện ích static.
- **Đa hình hình thức:** tạo interface cho mọi lớp dù chỉ có một quy tắc ổn định; hãy thêm trừu tượng tại nơi có biến thể thật.
- **Dùng double cho tiền:** dễ có sai số biểu diễn số thực; bài này dùng long VND.
- **Chỉ kiểm thử happy path:** bỏ sót ngưỡng giao hàng và đầu vào không hợp lệ.
- **Đổi hành vi ngoài ý muốn:** tính ngưỡng trên tạm tính thay vì số tiền sau giảm, hoặc làm tròn 10% khác phiên bản cũ.

## 8. Bài tập mở rộng và tiêu chí nộp bài

**Bài A — Bronze:** Bỏ chuỗi loại khách/giao hàng; tách Order, CheckoutService và Receipt; giữ nguyên 5 kết quả trong bảng.

**Bài B — Silver:** Hoàn thiện DiscountPolicy, cho phép test CheckoutService với một chính sách giả trả tiền giảm tùy ý; kiểm tra chính sách trả tiền giảm sai.

**Bài C — Gold:** Thêm chính sách chiết khấu PREMIUM = 15% vào enum và cấu hình, không sửa phương thức CheckoutService.checkout. Viết test khẳng định giá sau giảm được dùng để xét miễn phí giao. Nếu thay đổi quy tắc làm tròn, mô tả rõ thay đổi và test giá trị lẻ.

**Nộp:** mã chạy được trên Java 17+, bảng các ca kiểm thử trước/sau có cùng kết quả, sơ đồ lớp hoặc bảng trách nhiệm và giải thích ngắn về encapsulation, composition, polymorphism. Hoàn thành khi mã cũ được thay thế an toàn, không còn logic trùng lặp và mọi ca hồi quy đều PASS.