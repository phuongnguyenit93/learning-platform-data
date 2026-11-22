# Builder và việc tạo đối tượng phức tạp trong Java

**Chủ đề:** Mẫu thiết kế (Design Patterns) — Builder.  
**Mục tiêu:** hiểu vì sao Builder hữu ích khi một đối tượng có nhiều thành phần và ràng buộc, tự viết fluent Builder bằng Java, bảo đảm đối tượng sau khi tạo hợp lệ và biết khi nào nên chọn cách tạo đối tượng đơn giản hơn.

## 1. Vì sao việc khởi tạo đối tượng có thể trở nên khó kiểm soát?

Khi một đối tượng chỉ có hai trường bắt buộc, constructor trực tiếp thường đủ rõ:

~~~java
record Point(int x, int y) {}

Point point = new Point(10, 20);
~~~

Nhưng hãy tưởng tượng yêu cầu tạo **đơn hàng** có các thông tin sau:

| Thành phần | Bắt buộc? | Ràng buộc |
| --- | --- | --- |
| Mã khách hàng | Có | Không được rỗng hoặc chỉ có khoảng trắng |
| Địa chỉ giao | Có | Không được rỗng |
| Danh sách mặt hàng | Có ít nhất một | Mỗi mặt hàng có SKU, số lượng dương và đơn giá không âm |
| Cách giao hàng | Không | Mặc định **STANDARD**, có thể chọn **EXPRESS** |
| Mã khuyến mãi | Không | Nếu cung cấp thì không được rỗng |
| Gói quà | Không | Mặc định **false** |
| Ghi chú giao hàng | Không | Mặc định chuỗi rỗng |

Nếu tất cả thành tham số constructor:

~~~java
// Khó nhận ra ý nghĩa của các giá trị ở giữa.
new Order("C01", "12 Nguyễn Huệ", items,
          ShippingMode.EXPRESS, "WELCOME",
          true, "Gọi trước khi giao");
~~~

Client phải nhớ thứ tự tham số, cách biểu diễn trường tùy chọn và các tổ hợp giá trị hợp lệ. Các kiểu cùng là **String** càng dễ bị truyền nhầm vị trí mà trình biên dịch không phát hiện. Nếu khắc phục bằng hàng loạt constructor quá tải (*telescoping constructors*) thì số lượng biến thể có thể tăng nhanh. Nếu thay bằng constructor rỗng rồi gọi setter, đối tượng có thể tồn tại ở trạng thái chưa hợp lệ trong lúc thiết lập:

~~~java
MutableOrder order = new MutableOrder();
order.setCustomerId("C01");
// Nếu bị sử dụng tại đây, order có thể chưa có địa chỉ và mặt hàng.
order.setShippingAddress("12 Nguyễn Huệ");
~~~

**Builder** cung cấp một cách tổ chức quá trình dựng đối tượng: gom các lựa chọn cấu hình vào một builder, đặt tên rõ cho mỗi thao tác, xác thực trước khi hoàn tất và tạo đối tượng kết quả.

## 2. Builder là gì?

Builder là mẫu thiết kế tạo đối tượng (*creational pattern*). Ý tưởng chung là **tách các bước xây dựng khỏi đối tượng cuối cùng**. Trong Java, biến thể rất phổ biến là **fluent Builder**: mỗi phương thức thiết lập thông tin trả về chính builder để có thể gọi nối tiếp.

~~~java
Order order = Order.builder("C01", "12 Nguyễn Huệ")
        .addItem("BOOK-01", 2, new BigDecimal("125000"))
        .addItem("PEN-05", 1, new BigDecimal("35000"))
        .shippingMode(ShippingMode.EXPRESS)
        .couponCode("WELCOME")
        .giftWrap(true)
        .build();
~~~

Luồng tư duy khi đọc đoạn mã: tạo đơn cho khách, thêm mặt hàng, chọn cách giao, đặt mã ưu đãi, yêu cầu gói quà rồi hoàn tất. Chữ ký phương thức thể hiện rõ ý nghĩa từng giá trị.

Builder không bắt buộc phải có chuỗi fluent, nested class hoặc các tên phương thức cố định. GoF Builder cổ điển có thể gồm **Builder**, **ConcreteBuilder**, **Director** và **Product**; một fluent Builder dùng trong Java có thể chỉ cần **Product** cùng **Builder**, không cần Director. Tên gọi là phương tiện tổ chức quá trình tạo, không phải yêu cầu triển khai tất cả vai trò cho mọi bài toán.

~~~mermaid
flowchart LR
    A["Client"] -->|"builder(required fields)"| B["Order.Builder"]
    B -->|"addItem / shippingMode / couponCode"| B
    B -->|"build(): kiểm tra bất biến"| C["Order (bất biến)"]
    C --> D["Client sử dụng Order hoàn chỉnh"]
~~~

### Những lợi ích cần nhận đúng

- **Dễ đọc:** mỗi bước cấu hình có tên, ít nhầm thứ tự tham số.
- **Kiểm tra tập trung:** Builder/constructor sản phẩm có thể xác nhận điều kiện xuyên nhiều trường trước khi trả về đối tượng.
- **Tùy chọn và mặc định:** khách hàng chỉ cung cấp các lựa chọn khác mặc định.
- **Đối tượng cuối cùng bất biến:** không cần public setter nếu giá trị đã hoàn chỉnh tại **build()**.
- **Tái sử dụng quy trình tạo:** builder có thể hỗ trợ thêm bước hoặc biến thể tùy nghiệp vụ.

**Không phải lợi ích tự động:** Builder không tự đảm bảo tính bất biến, đúng nghiệp vụ, thread-safe hoặc giảm mọi độ phức tạp. Những tính chất đó phụ thuộc vào code cụ thể.

## 3. Ví dụ Java 17+: tạo Order có ràng buộc rõ ràng

Lưu đoạn mã sau vào **BuilderDemo.java** rồi chạy bằng JDK 17 trở lên. Ví dụ dùng **record** cho mặt hàng bất biến, **BigDecimal** để biểu diễn đơn giá chính xác, **List.copyOf** để chụp lại danh sách khi tạo đơn, và builder có các tham số bắt buộc ngay từ phương thức khởi đầu.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class BuilderDemo {

    enum ShippingMode {
        STANDARD, EXPRESS
    }

    // Value object: record tự sinh accessor, equals/hashCode và toString.
    // Các thành phần của record này đều là giá trị bất biến.
    public record LineItem(String sku, int quantity, BigDecimal unitPriceVnd) {
        public LineItem {
            sku = requiredText(sku, "sku");
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "Số lượng phải lớn hơn 0");
            }
            Objects.requireNonNull(unitPriceVnd, "unitPriceVnd");
            if (unitPriceVnd.signum() < 0) {
                throw new IllegalArgumentException(
                        "Đơn giá không được âm");
            }
        }

        public BigDecimal lineTotalVnd() {
            return unitPriceVnd.multiply(BigDecimal.valueOf(quantity));
        }
    }

    public static final class Order {
        private final String customerId;
        private final String shippingAddress;
        private final List<LineItem> items;
        private final ShippingMode shippingMode;
        private final String couponCode;
        private final boolean giftWrap;
        private final String note;

        private Order(Builder builder) {
            // Một lần nữa xác nhận bất biến tại ranh giới tạo đối tượng.
            this.customerId =
                    requiredText(builder.customerId, "customerId");
            this.shippingAddress =
                    requiredText(builder.shippingAddress, "shippingAddress");

            // Bản sao độc lập; không giữ danh sách mutable của Builder.
            this.items = List.copyOf(builder.items);
            if (items.isEmpty()) {
                throw new IllegalStateException(
                        "Đơn hàng cần ít nhất một mặt hàng");
            }

            this.shippingMode =
                    Objects.requireNonNull(builder.shippingMode);
            this.couponCode = builder.couponCode;
            this.giftWrap = builder.giftWrap;
            this.note = builder.note;
        }

        // Bắt buộc có khách hàng và địa chỉ ngay khi khởi tạo builder.
        public static Builder builder(
                String customerId, String shippingAddress) {
            return new Builder(customerId, shippingAddress);
        }

        public String customerId() {
            return customerId;
        }

        public String shippingAddress() {
            return shippingAddress;
        }

        public List<LineItem> items() {
            return items;
        }

        public ShippingMode shippingMode() {
            return shippingMode;
        }

        public String couponCode() {
            return couponCode;
        }

        public boolean giftWrap() {
            return giftWrap;
        }

        public String note() {
            return note;
        }

        public BigDecimal goodsTotalVnd() {
            return items.stream()
                    .map(LineItem::lineTotalVnd)
                    .reduce(BigDecimal.ZERO, BigDecimal::add);
        }

        public static final class Builder {
            private final String customerId;
            private final String shippingAddress;
            private final List<LineItem> items = new ArrayList<>();
            private ShippingMode shippingMode = ShippingMode.STANDARD;
            private String couponCode;
            private boolean giftWrap;
            private String note = "";

            private Builder(String customerId, String shippingAddress) {
                this.customerId = requiredText(customerId, "customerId");
                this.shippingAddress =
                        requiredText(shippingAddress, "shippingAddress");
            }

            public Builder addItem(
                    String sku, int quantity, BigDecimal unitPriceVnd) {
                items.add(new LineItem(sku, quantity, unitPriceVnd));
                return this;
            }

            public Builder shippingMode(ShippingMode mode) {
                this.shippingMode =
                        Objects.requireNonNull(mode, "shippingMode");
                return this;
            }

            public Builder couponCode(String code) {
                this.couponCode = requiredText(code, "couponCode");
                return this;
            }

            public Builder giftWrap(boolean enabled) {
                this.giftWrap = enabled;
                return this;
            }

            public Builder note(String value) {
                this.note = Objects.requireNonNull(value, "note");
                return this;
            }

            public Order build() {
                return new Order(this);
            }
        }
    }

    private static String requiredText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    field + " không được rỗng");
        }
        return value.trim();
    }

    public static void main(String[] args) {
        Order order = Order.builder("C01", "12 Nguyễn Huệ")
                .addItem("BOOK-01", 2, new BigDecimal("125000"))
                .addItem("PEN-05", 1, new BigDecimal("35000"))
                .shippingMode(ShippingMode.EXPRESS)
                .couponCode("WELCOME")
                .giftWrap(true)
                .note("Gọi trước khi giao")
                .build();

        System.out.println(
                order.customerId() + " | " +
                order.shippingMode() + " | " +
                order.goodsTotalVnd().toPlainString() + " VND");
        System.out.println("Số dòng mặt hàng: " + order.items().size());
    }
}
~~~

Chạy:

~~~bash
javac BuilderDemo.java
java BuilderDemo
~~~

Kết quả:

~~~text
C01 | EXPRESS | 285000 VND
Số dòng mặt hàng: 2
~~~

**Giải thích các điểm thiết kế:**

1. **Constructor của Order là private.** Client không thể tạo **Order** bằng cách bỏ qua ranh giới xác thực.
2. **Order.builder(customerId, shippingAddress)** yêu cầu hai thông tin tối thiểu. Trình biên dịch buộc người gọi cung cấp tham số, còn kiểm tra null/rỗng được thực hiện lúc chạy.
3. **addItem(...)** tạo **LineItem** hợp lệ tại thời điểm thêm vào builder; **build()** kiểm tra điều kiện liên quan đến toàn bộ đơn hàng: phải có ít nhất một dòng.
4. **shippingMode** có giá trị mặc định. **couponCode == null** thể hiện không có mã ưu đãi, **giftWrap == false** thể hiện không gói quà, **note == ""** là không có ghi chú. Các ý nghĩa đó phải được xác định rõ trong API.
5. **Order** chỉ có trường **private final** và accessor. Không có setter thay đổi trạng thái sau khi tạo.
6. **List.copyOf** tạo danh sách không cho chỉnh sửa qua accessor và tách danh sách của đơn khỏi danh sách nội bộ của builder. Vì **LineItem** dùng **String**, **int** và **BigDecimal** (đều bất biến trong ví dụ), nội dung từng phần tử cũng không bị chỉnh sửa thông qua reference mutable.
7. **goodsTotalVnd()** là tổng tiền hàng trước phí vận chuyển và giảm giá. Builder không tự áp dụng coupon; quy tắc giảm giá thuộc xử lý nghiệp vụ riêng.

Mã sử dụng **BigDecimal** thay vì **double** cho tiền để tránh sai số nhị phân của phép tính dấu phẩy động. Trong dự án thật, hãy thống nhất quy tắc làm tròn, đơn vị tiền tệ, thuế và không dùng chuỗi coupon để ngầm coi đã áp dụng giảm giá.

## 4. Hai thời điểm kiểm tra điều kiện: cấu hình và hoàn tất

Đừng dồn một cách máy móc mọi kiểm tra vào **build()**, cũng đừng tin rằng việc từng setter riêng lẻ hợp lệ bảo đảm tổ hợp cuối cùng hợp lệ.

| Thời điểm | Nên kiểm tra gì? | Ví dụ |
| --- | --- | --- |
| Khi khởi tạo builder | Giá trị bắt buộc độc lập | Mã khách hàng/địa chỉ không rỗng |
| Khi gọi phương thức cấu hình | Tính hợp lệ của từng lựa chọn | Số lượng > 0, đơn giá không âm, chế độ giao không null |
| Khi gọi **build()** | Bất biến liên quan nhiều thành phần | Phải có ít nhất một mặt hàng; ngày giao sau ngày đặt nếu nghiệp vụ yêu cầu |
| Ở service nghiệp vụ | Quy tắc cần dữ liệu động hoặc hạ tầng | Tồn kho, hiệu lực mã ưu đãi, quyền đặt hàng, phí từ hãng vận chuyển |

Ví dụ với quy tắc tùy chọn: một đơn **EXPRESS** phải có số điện thoại liên hệ. Có thể thêm **contactPhone** vào builder và kiểm tra tổ hợp khi **build()**:

~~~java
// Minh họa đoạn điều kiện đặt trong constructor của Product:
if (builder.shippingMode == ShippingMode.EXPRESS
        && (builder.contactPhone == null
            || builder.contactPhone.isBlank())) {
    throw new IllegalStateException(
            "Giao EXPRESS yêu cầu số điện thoại liên hệ");
}
~~~

Đoạn này là **phần mở rộng minh họa**, không phải phần có thể copy nguyên xi vào **BuilderDemo.java** vì ví dụ hoàn chỉnh phía trên chưa khai báo **contactPhone**. Nếu triển khai, cần bổ sung field, method trong builder, field bất biến trong Order, accessor và test ràng buộc.

Lưu ý quan trọng: xác minh tồn kho hoặc tính phí vận chuyển bên ngoài không nên tự động gọi mạng trong **build()** của value object nếu điều đó làm quá trình tạo đối tượng khó dự đoán, khó test hoặc có side effect. Để service phối hợp các phụ thuộc thích hợp rồi tạo hoặc xác nhận đơn hàng.

## 5. Hiểu đúng tính bất biến và việc tái sử dụng Builder

**Builder thường mutable**, còn **Product có thể immutable**. Hai trạng thái đó không mâu thuẫn.

Một builder có thể được sử dụng để tạo nhiều bản chụp đối tượng:

~~~java
var builder = BuilderDemo.Order
        .builder("C02", "45 Lê Lợi")
        .addItem("BOOK-01", 1, new java.math.BigDecimal("100000"));

var first = builder.build();           // 1 dòng
builder.addItem("PEN-05", 2,
        new java.math.BigDecimal("10000"));
var second = builder.build();          // 2 dòng

System.out.println(first.items().size());   // 1
System.out.println(second.items().size());  // 2
~~~

Điều này hoạt động vì mỗi lần **build()** sao chép danh sách. Nếu constructor của Product chỉ giữ **builder.items** trực tiếp, thay đổi builder sau khi build cũng làm thay đổi sản phẩm trước đó — phá vỡ kỳ vọng bất biến.

Tuy nhiên, **List.copyOf chỉ là sao chép nông các phần tử**. Nếu danh sách chứa đối tượng mutable như **MutableAddress**, **ArrayList** con hoặc đối tượng có setter, người giữ reference tới các phần tử có thể vẫn sửa nội dung bên trong. Khi cần bất biến sâu hơn, hãy dùng value object immutable, defensive copy từng phần tử, hoặc tránh lộ reference mutable.

**Builder mutable không mặc nhiên thread-safe.** Không chia sẻ một builder đang được cập nhật giữa các thread nếu không có giao thức đồng bộ/chống tranh chấp phù hợp. Cách đơn giản nhất là mỗi luồng/tác vụ dùng builder của riêng mình.

Các lỗi thường gặp:

- Public setter trên **Order** làm mất ý nghĩa “hoàn tất khi build”.
- **build()** trả về chính builder hoặc trả về product giữ reference mutable do builder sở hữu.
- Builder cho phép tạo product thiếu trường cần thiết mà không báo lỗi.
- Mặc định âm thầm thay đổi theo thời gian khiến hành vi cũ bị bất ngờ.
- Phép kiểm tra chỉ nằm ở một setter nhưng tổ hợp các bước cấu hình có thể vượt qua bất biến.
- Dùng exception cho trường hợp nghiệp vụ hợp lệ nhưng thất bại thường xuyên mà không có contract rõ ràng; ở ứng dụng lớn có thể dùng kiểu kết quả validation chuyên biệt.

## 6. Kiểm thử Builder bằng JUnit 5

Các test sau đặt trong **BuilderDemoTest.java** (có JUnit Jupiter trong classpath của dự án). Mục tiêu là xác nhận tính đúng đắn của đối tượng **đã xây dựng**, mặc định, bất biến và lỗi đầu vào.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class BuilderDemoTest {

    @Test
    void taoDonHangVoiMacDinh() {
        var order = BuilderDemo.Order.builder("C01", "12 Nguyễn Huệ")
                .addItem("BOOK-01", 2, new BigDecimal("125000"))
                .build();

        assertEquals(BuilderDemo.ShippingMode.STANDARD,
                order.shippingMode());
        assertFalse(order.giftWrap());
        assertNull(order.couponCode());
        assertEquals("", order.note());
        assertEquals(new BigDecimal("250000"), order.goodsTotalVnd());
    }

    @Test
    void khongChoTaoDonRong() {
        var builder = BuilderDemo.Order.builder("C01", "12 Nguyễn Huệ");

        assertThrows(IllegalStateException.class, builder::build);
    }

    @Test
    void chanSoLuongKhongHopLe() {
        var builder = BuilderDemo.Order.builder("C01", "12 Nguyễn Huệ");

        assertThrows(IllegalArgumentException.class, () ->
                builder.addItem("BOOK-01", 0,
                        new BigDecimal("125000")));
    }

    @Test
    void danhSachCuaOrderKhongTheSuaVaKhongBiAnhHuongKhiTaiSuDungBuilder() {
        var builder = BuilderDemo.Order.builder("C01", "12 Nguyễn Huệ")
                .addItem("BOOK-01", 1, new BigDecimal("100000"));
        var first = builder.build();

        assertThrows(UnsupportedOperationException.class, () ->
                first.items().clear());

        builder.addItem("PEN-05", 1, new BigDecimal("10000"));
        var second = builder.build();

        assertEquals(1, first.items().size());
        assertEquals(2, second.items().size());
    }

    @Test
    void batBuocCoMaKhachHangHopLe() {
        assertThrows(IllegalArgumentException.class, () ->
                BuilderDemo.Order.builder("   ", "12 Nguyễn Huệ"));
    }
}
~~~

Một bộ kiểm thử đầy đủ hơn nên bao phủ các biên: số lượng cực lớn, đơn giá âm, null, chuỗi trắng, các quy tắc liên trường, giá trị mặc định và cách xử lý khi builder được cấu hình lặp lại. Chọn mức độ test tương ứng với rủi ro nghiệp vụ; không cần viết test chỉ để chứng minh mỗi setter trả về builder nếu kết quả end-to-end đã bao phủ.

## 7. So sánh các cách tạo đối tượng trong Java

| Cách tạo | Hợp khi | Điểm cần cân nhắc |
| --- | --- | --- |
| Constructor thông thường | Ít trường, tất cả đều rõ ràng và bắt buộc | Có thể khó đọc khi quá nhiều tham số cùng kiểu |
| **record** | Value object nhỏ, thành phần rõ, cần equality theo giá trị | Không tự giải quyết tình trạng nhiều tùy chọn hay quy trình dựng nhiều bước |
| Static factory | Muốn tên nghiệp vụ rõ, chọn implementation hoặc quản lý cách khởi tạo | Nếu có hàng chục tùy chọn, số factory có thể phình to |
| Setter trên đối tượng mutable | Đối tượng thực sự cần thay đổi liên tục sau khởi tạo | Có thể lộ trạng thái trung gian không hợp lệ |
| **Builder** | Nhiều trường tùy chọn, quy trình tạo có bước, cần valid/immutable product | Thêm code, trạng thái trung gian và chi phí học API |
| Factory + Builder | Cần lựa chọn họ đối tượng/implementation rồi cấu hình nhiều tham số | Cân nhắc độ phức tạp tổng thể; hai mẫu không thay thế nhau |

**Factory trả lời chủ yếu “tạo loại đối tượng nào, bằng cơ chế nào?”; Builder trả lời “cung cấp thông tin và các bước để tạo đối tượng đó ra sao?”.** Có thể dùng cùng nhau nếu bài toán đòi hỏi, nhưng không cần kết hợp chỉ để tăng số mẫu thiết kế.

Đặc biệt, Java **record** thích hợp với dữ liệu nhỏ như **LineItem**. Builder mang lại giá trị rõ hơn với aggregate **Order** có nhiều tùy chọn, danh sách và ràng buộc liên trường.

## 8. Fluent Builder, staged Builder và Director

### Fluent Builder thông thường

Ví dụ **Order.Builder** ở trên cho phép gọi các bước tùy chọn theo thứ tự linh hoạt. Một số yêu cầu bắt buộc được ép thông qua **builder(customerId, shippingAddress)**, còn quy tắc “ít nhất một mặt hàng” được kiểm tra tại runtime khi **build()**.

### Staged Builder / Step Builder

Nếu một quy trình phức tạp cần ép người gọi thực hiện các bước theo thứ tự ở *thời điểm biên dịch*, có thể tách các interface từng giai đoạn:

~~~java
interface CustomerStep {
    AddressStep customer(String customerId);
}

interface AddressStep {
    BuildStep address(String shippingAddress);
}

interface BuildStep {
    BuildStep giftWrap(boolean enabled);
    Order build();
}
~~~

Client chỉ thấy phương thức hợp lệ ở giai đoạn hiện tại. Cách này có thể giảm nguy cơ thiếu trường bắt buộc, nhưng tạo thêm nhiều interface, generic hoặc type phức tạp. Thường không đáng dùng cho object cấu hình bình thường. Ví dụ trên chỉ mô tả hình dạng các **stage interfaces**; cần một implementation tương ứng và kiểu **Order** thực tế trước khi sử dụng.

### Director trong GoF Builder

**Director** là đối tượng biết một trình tự xây dựng tiêu chuẩn. Nó gọi builder để tạo biến thể như “đơn quà tặng”, “báo cáo chi tiết”, “cấu hình mặc định cho môi trường test”:

~~~java
static BuilderDemo.Order createGiftOrder(
        String customerId, String address) {
    return BuilderDemo.Order.builder(customerId, address)
            .addItem("GIFT-01", 1, new java.math.BigDecimal("200000"))
            .giftWrap(true)
            .build();
}
~~~

Ở đây một static factory đủ diễn đạt “recipe” và không cần tạo class **Director** riêng. Nếu có nhiều loại builder cho những sản phẩm khác nhau nhưng cùng quy trình dựng, một Director độc lập mới có thể có ích.

## 9. Builder khi kết hợp với Lombok, Spring hoặc thư viện khác

Trong codebase dùng Lombok, **@Builder** có thể tạo API builder và giảm boilerplate:

~~~java
// Ví dụ ý tưởng, cần dependency Lombok và cấu hình annotation processing:
@lombok.Builder
record ExportOptions(
        String format,
        boolean includeImages,
        int maxRows
) {}
~~~

Đây không phải thay thế trực tiếp cho các kiểm tra ở ví dụ **Order**. Annotation sinh builder và cơ chế dựng, nhưng các bất biến nghiệp vụ, defensive copy của dữ liệu mutable, lựa chọn mặc định và điều kiện liên trường vẫn cần được thiết kế/chứng minh. Cũng cần hiểu tương tác giữa **@Builder**, record/constructor, **@Builder.Default** (trong các trường hợp được hỗ trợ) và code được sinh khi review.

Với Spring Boot, một lớp cấu hình có thể được bind từ YAML/properties qua constructor/record và có cơ chế validation của framework. Không nên thêm Builder cho mọi **@ConfigurationProperties** nếu constructor binding hoặc record đã đủ rõ; Builder phù hợp hơn khi client thực sự tạo đối tượng từng bước hoặc có nhiều cấu hình tùy chọn do code quyết định.

**Lưu ý hiệu năng:** tạo thêm builder là thêm một object ngắn hạn và các bước gọi phương thức. Thông thường ưu tiên tính đúng, độ rõ và khả năng bảo trì. Chỉ tối ưu allocation khi profiling chứng minh đây là điểm nghẽn thực tế.

## 10. Thiết kế API Builder dễ dùng và dễ bảo trì

Một số quyết định nhỏ nhưng có ảnh hưởng lớn:

| Quyết định | Gợi ý | Lý do |
| --- | --- | --- |
| Trường bắt buộc | Đưa vào static factory **builder(required...)** hoặc dùng staged steps khi cần | Giảm khả năng quên và làm rõ entry point |
| Giá trị mặc định | Định nghĩa minh bạch, nhất quán trong builder | Client không phải truyền lại giá trị phổ biến |
| Danh sách/map | Tích lũy trong builder, sao chép phòng vệ khi build | Không lộ mutable state qua product |
| Giá trị có kiểu | Ưu tiên **enum**, value object thay vì chuỗi không kiểm soát | Giảm trạng thái không hợp lệ |
| Trường cùng tên | Dùng tên phương thức đúng ngôn ngữ nghiệp vụ | Tránh mơ hồ như **setFlag(true)** |
| Exception | Báo lỗi gắn với trường hoặc bất biến vi phạm | Người gọi dễ sửa dữ liệu đầu vào |
| Build nhiều lần | Quy định rõ có hỗ trợ hay không; nếu có, trả object độc lập | Tránh mutation vô tình |
| Đồng thời | Builder thuộc phạm vi một tác vụ/thread, trừ khi có thiết kế đồng bộ rõ | Hạn chế data race |
| Sao chép/biến thể | Cân nhắc **toBuilder()** chỉ khi có nhu cầu | Tránh copy bằng setter trên immutable product |

Một cách triển khai rất hay gặp là **Builder nằm trong lớp Product**, nhưng không phải giới hạn của mẫu thiết kế. Builder bên ngoài phù hợp khi không sở hữu mã nguồn Product, cần nhiều chiến lược dựng, hoặc muốn giữ API Product gọn.

## 11. Khi nào không nên dùng Builder?

Builder có chi phí viết và bảo trì. Hãy giữ cách tạo đơn giản khi:

- Một object có 2–3 tham số rõ ràng, không có nhiều tùy chọn hoặc trạng thái trung gian.
- Dữ liệu chủ yếu là bản ghi bất biến nhỏ; **record** hoặc constructor là đủ.
- Object là entity do framework ORM quản lý, có ràng buộc lifecycle/proxy khác với value object. Cần xem lại yêu cầu của framework thay vì áp Builder máy móc.
- Mọi thay đổi là trạng thái hợp lệ trong quá trình sống của object; khi đó API mutation có kiểm soát, command hoặc aggregate method có thể là mô hình đúng hơn.
- Tạo builder chỉ vì “dự án phải có Design Pattern”, trong khi người đọc cần thêm lớp để hiểu một phép gán.

Một nguyên tắc thực dụng: **chọn Builder khi nó làm rõ một quá trình tạo phức tạp, bảo vệ bất biến, hoặc làm API gọi dễ hiểu hơn đáng kể so với constructor/factory**. Không đo chất lượng thiết kế bằng số lớp hoặc số pattern xuất hiện.

## 12. Bài tập thực hành

Thiết kế **ReportConfig** cho chức năng xuất báo cáo doanh thu:

- **reportName**, **fromDate**, **toDate** là bắt buộc.
- **format** mặc định **CSV**, có thể chọn **PDF**.
- **includeCharts** mặc định false; PDF được phép có biểu đồ, CSV thì không.
- Danh sách các phòng ban cần lọc có thể rỗng (nghĩa là tất cả), nhưng không chứa mã phòng ban null/rỗng.
- Ngày bắt đầu không được sau ngày kết thúc.

Hãy viết **ReportConfig.builder(reportName, fromDate, toDate)**, thêm **format(...)**, **includeCharts(...)**, **addDepartment(...)** và **build()**. Dùng **LocalDate**, **enum Format**, **List.copyOf** và các field **final** nếu phù hợp. Kiểm thử tối thiểu: mặc định CSV, khoảng ngày đảo ngược bị từ chối, CSV kèm biểu đồ bị từ chối, danh sách phòng ban trên Product không thay đổi được, và việc dùng lại builder không sửa ReportConfig đã tạo.

Tự đánh giá bằng ba câu hỏi: (1) người đọc lời gọi có hiểu từng lựa chọn không; (2) có cách nào tạo ReportConfig vi phạm bất biến không; (3) khi thêm tùy chọn mới, có cần sửa mọi vị trí constructor trong hệ thống không?

**Kết luận:** Builder hữu ích nhất khi biến quá trình tạo đối tượng nhiều tham số thành các bước có ý nghĩa, cô lập xác thực và tạo sản phẩm hoàn chỉnh. Hãy đảm bảo ranh giới giữa Builder mutable và Product immutable được thiết kế thực sự đúng, và chỉ chấp nhận độ phức tạp của mẫu khi lợi ích bảo trì rõ ràng.