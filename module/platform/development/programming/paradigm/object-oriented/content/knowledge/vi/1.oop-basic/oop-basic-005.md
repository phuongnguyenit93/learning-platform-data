# Đóng gói, trừu tượng, kế thừa và đa hình trong OOP

Bốn khái niệm **đóng gói (encapsulation), trừu tượng (abstraction), kế thừa (inheritance) và đa hình (polymorphism)** thường được gọi là “bốn tính chất của lập trình hướng đối tượng”. Nhưng nhớ tên và định nghĩa chưa đủ: điều quan trọng là hiểu **chúng giúp thiết kế phần mềm như thế nào, liên quan ra sao và khi nào nên dùng**.

Hãy lấy bài toán một cửa hàng: khách mua giỏ hàng trị giá 500.000 đồng. Cửa hàng có thể áp dụng **giảm 10%** hoặc **giảm cố định 80.000 đồng**. Hệ thống cần giữ cho giỏ hàng hợp lệ, tính đúng tổng tiền và cho phép bổ sung chính sách giảm giá sau này mà ít phải sửa mã thanh toán.

Bài học sẽ dùng bài toán này để giải thích cả bốn khái niệm. Không cần biết Spring Boot trước; phần code Java có thể chạy trực tiếp.

## 1. Bức tranh tổng quan: bốn khái niệm giải quyết bốn câu hỏi khác nhau

| Khái niệm | Câu hỏi nó giải quyết | Ví dụ trong cửa hàng |
| --- | --- | --- |
| **Đóng gói** | Ai được phép xem, sửa trạng thái, và sửa qua con đường nào để dữ liệu luôn hợp lệ? | Giỏ hàng tự kiểm tra số lượng và không cho bên ngoài sửa thẳng danh sách hàng. |
| **Trừu tượng** | Người sử dụng đối tượng cần biết *khả năng gì* và có thể bỏ qua *chi tiết nào*? | Thanh toán chỉ cần yêu cầu “tính số tiền giảm”, không phải biết thuật toán của từng ưu đãi. |
| **Kế thừa** | Kiểu chuyên biệt nào có thể dùng lại và mở rộng một kiểu cha theo quan hệ hợp lý? | Giảm phần trăm và giảm số tiền cố định đều là loại chính sách giảm giá. |
| **Đa hình** | Vì sao cùng một lời gọi có thể tạo ra hành vi khác nhau tùy đối tượng thực tế? | Gọi `discountFor(500000)` trả về 50.000 với chính sách 10%, nhưng 80.000 với chính sách cố định. |

Chúng **không phải bốn bước thực hiện theo thứ tự**, cũng không bắt buộc mọi lớp phải sử dụng cả bốn. Một lớp bất biến có thể thể hiện đóng gói rất tốt mà không hề kế thừa lớp nào. Một ứng dụng có thể dùng trừu tượng và đa hình qua interface mà gần như không cần hệ phân cấp lớp sâu.

## 2. Đóng gói (Encapsulation): đối tượng tự bảo vệ trạng thái

Giả sử viết một giỏ hàng như sau:

~~~java
class Cart {
    public List<String> items = new ArrayList<>();
}
~~~

Mọi nơi giữ tham chiếu đến `Cart` đều có thể sửa `items` trực tiếp. Nếu hệ thống cần quy tắc “không được thêm sản phẩm có số lượng âm”, lớp này không có điểm kiểm soát đáng tin cậy. Người gọi có thể vô tình phá hỏng dữ liệu dù không cố ý.

Thiết kế theo hướng đóng gói là **đặt dữ liệu và hành vi xử lý dữ liệu vào cùng một ranh giới chịu trách nhiệm**, rồi kiểm soát cách truy cập và thay đổi trạng thái.

~~~java
final class Cart {
    private final List<String> items = new ArrayList<>();

    public void addItem(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU must not be blank");
        }
        items.add(sku);
    }

    public List<String> viewItems() {
        return List.copyOf(items);
    }
}
~~~

Ở đây:

- `items` là chi tiết trạng thái được giữ trong `Cart`; bên ngoài không được tự ý thêm/xóa trực tiếp trên danh sách nội bộ.
- `addItem()` là **con đường thay đổi có kiểm soát**: kiểm tra đầu vào trước khi cập nhật.
- `viewItems()` trả về bản chụp danh sách không thể sửa bằng các thao tác như `add`/`clear`. Nhờ đó, người gọi không làm thay đổi danh sách gốc qua tham chiếu trả về.

**Đóng gói không đồng nghĩa đơn giản với việc thêm `private` rồi tạo getter/setter cho mọi trường.** Nếu viết `setQuantity(-5)` và setter vẫn chấp nhận giá trị sai, quy tắc nghiệp vụ chưa được bảo vệ. Nhiều khi hành vi `addItem()`, `removeItem()` hoặc `confirm()` có ý nghĩa hơn setter chung chung, vì nó diễn đạt một thao tác hợp lệ.

### Bảo vệ điều kiện luôn đúng (invariant)

Một giỏ hàng có thể đặt quy tắc:

- Mã sản phẩm không rỗng.
- Số lượng của mỗi dòng hàng lớn hơn 0.
- Đơn giá không âm.
- Tổng tiền được tính từ các dòng hàng hợp lệ.

Một thao tác tốt sẽ **kiểm tra điều kiện trước khi đổi trạng thái** và từ chối đầu vào sai mà không để giỏ hàng ở trạng thái dở dang.

Để ý `private final List` chỉ ngăn gán lại biến `items`; bản thân `ArrayList` vẫn thay đổi được qua `add()`. Vì vậy **`final` không có nghĩa là nội dung danh sách bất biến**, còn `private` không tự ngăn lỗi trong chính các phương thức của lớp. Muốn đóng gói đúng cần cả quyền truy cập, phương thức thao tác và kiểm tra quy tắc.

**Khi nào hữu ích?** Khi trạng thái có ràng buộc, thay đổi ở nhiều nơi sẽ gây sai lệch, hoặc bạn muốn bảo trì logic mà không sửa tất cả nơi sử dụng.

## 3. Trừu tượng (Abstraction): nói rõ khả năng, giấu phần chi tiết không cần thiết

Với bài toán giảm giá, mã thanh toán chỉ cần biết một chính sách có thể:

> Nhận tổng tiền trước giảm và trả về số tiền được giảm hợp lệ.

Nó không cần biết chính sách tính theo phần trăm, số tiền cố định hay một cách tính phức tạp hơn. Ta có thể mô tả **hợp đồng (contract)** bằng một interface:

~~~java
interface DiscountPolicy {
    BigDecimal discountFor(BigDecimal subtotal);
}
~~~

Hàm thanh toán có thể làm việc với `DiscountPolicy`:

~~~java
BigDecimal amountToPay(BigDecimal subtotal, DiscountPolicy policy) {
    return subtotal.subtract(policy.discountFor(subtotal));
}
~~~

Điểm chính là **tách “cần làm gì” khỏi “được thực hiện như thế nào”**. Người gọi biết tên hành vi, tham số, kiểu kết quả và quy tắc kỳ vọng; người gọi không cần nhìn vào thuật toán bên trong từng chính sách.

Trừu tượng còn xuất hiện khi ta dùng `Cart.addItem()` mà không cần quan tâm lớp này đang lưu dữ liệu bằng `ArrayList`, mảng hay cấu trúc khác. Vì vậy **trừu tượng là cách thiết kế và chọn thông tin cần công khai**, không chỉ là cú pháp `abstract class` hoặc `interface`.

**Đừng nhầm trừu tượng với đóng gói:**

| Góc nhìn | Đóng gói | Trừu tượng |
| --- | --- | --- |
| Trọng tâm | Kiểm soát truy cập và thay đổi trạng thái bên trong. | Chỉ đưa ra những khả năng/chi tiết cần thiết cho người sử dụng. |
| Câu hỏi | “Ai được quyền sửa dữ liệu và theo quy tắc nào?” | “Người gọi cần biết điều gì để dùng đối tượng?” |
| Ví dụ | `Cart` không lộ `items` mutable. | `CheckoutService` chỉ biết `DiscountPolicy.discountFor()`. |
| Công cụ Java thường thấy | `private`, phương thức nghiệp vụ, immutable view, validation. | Interface, abstract class, phương thức công khai có hợp đồng rõ ràng. |

Một đối tượng tốt thường **vừa trừu tượng hóa điều người gọi cần, vừa đóng gói những chi tiết nội bộ phải bảo vệ**. Hai khái niệm bổ trợ nhưng không thay thế nhau.

### Hợp đồng không chỉ có tên method

Với `discountFor(subtotal)`, cần quy định: tổng tiền đầu vào không âm; số tiền giảm đầu ra không âm và không vượt tổng tiền; chính sách không tự ý sửa giỏ hàng. Interface về mặt cú pháp chưa thể tự bảo đảm các điều kiện này. Thiết kế phải thể hiện chúng qua code, kiểm tra, tài liệu hợp đồng và test thích hợp.

## 4. Kế thừa (Inheritance): xây dựng quan hệ cha – con hợp lý

Kế thừa cho phép một lớp con nhận thuộc tính/hành vi có thể truy cập từ lớp cha và bổ sung hoặc thay đổi một phần hành vi phù hợp với hợp đồng. Trong Java, dùng `extends` để kế thừa một lớp.

~~~java
abstract class DiscountPolicy {
    public abstract BigDecimal discountFor(BigDecimal subtotal);
}

final class PercentageDiscount extends DiscountPolicy {
    private final int percent;

    PercentageDiscount(int percent) {
        this.percent = percent;
    }

    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        return subtotal.multiply(BigDecimal.valueOf(percent))
                       .divide(BigDecimal.valueOf(100));
    }
}
~~~

`PercentageDiscount` là một dạng `DiscountPolicy`: mọi chỗ cần chính sách giảm giá đều có thể nhận một đối tượng `PercentageDiscount`, miễn nó tuân thủ quy tắc mà `DiscountPolicy` cam kết.

Kế thừa có hai tác dụng thường gặp:

1. **Quan hệ kiểu (subtyping):** `PercentageDiscount` có thể được dùng ở chỗ yêu cầu `DiscountPolicy`.
2. **Dùng chung triển khai:** lớp cha có thể cung cấp xử lý dùng chung, lớp con chỉ triển khai điểm khác biệt.

Không phải cứ thấy hai lớp có đoạn code giống nhau là nên dùng `extends`. Ví dụ `ReportService` và `EmailService` cùng có method `log()` chưa có nghĩa một lớp “là một dạng” của lớp kia. Trường hợp này có thể tách một đối tượng cộng tác để dùng chung chức năng.

### Một số quy tắc Java cần nhớ

| Cú pháp/khái niệm | Ý nghĩa |
| --- | --- |
| `class B extends A` | `B` kế thừa **một** lớp cha `A` (Java không hỗ trợ một lớp trực tiếp extends nhiều lớp). |
| `@Override` | Đánh dấu method của lớp con ghi đè method có thể override từ lớp cha; compiler giúp phát hiện sai chữ ký. |
| `super(...)` | Gọi constructor phù hợp của lớp cha từ constructor lớp con. |
| `super.method()` | Gọi triển khai của lớp cha khi cần, nếu method đó có thể truy cập. |
| `protected` | Cho phép truy cập trong cùng package và từ subclass theo quy tắc Java; dùng có cân nhắc vì mở rộng bề mặt phụ thuộc. |
| `final class` | Không cho phép lớp khác kế thừa lớp này. |
| `final method` | Không cho phép subclass override method đó. |

Java còn có **kế thừa interface**: `interface B extends A`; một class có thể `implements` nhiều interface. Việc **triển khai interface** không giống việc kế thừa phần trạng thái của một superclass, dù nó cũng tạo quan hệ kiểu và hỗ trợ đa hình.

### “Là một loại” chưa đủ: còn phải thay thế được

Một subclass tốt phải giữ được kỳ vọng của code sử dụng kiểu cha. Nếu lớp cha hứa trả tiền giảm trong đoạn từ 0 đến tổng tiền, lớp con không nên tự trả giá trị âm hay lớn hơn tổng tiền. Đây là trực giác của **nguyên tắc thay thế Liskov (LSP)**: không làm hỏng hợp đồng khi thay kiểu cha bằng kiểu con.

Vì vậy, kế thừa nên được cân nhắc khi **quan hệ kiểu thực sự có nghĩa và hành vi của lớp con phù hợp với hợp đồng của lớp cha**. Nếu chỉ muốn ghép chức năng, **composition** (chứa và ủy quyền cho đối tượng khác) thường linh hoạt hơn.

## 5. Đa hình (Polymorphism): cùng lời gọi, cách xử lý khác nhau

Xét hai chính sách cùng nhận tổng tiền 500.000 đồng:

- `PercentageDiscount(10)`: giảm 50.000, khách trả **450.000 đồng**.
- `FixedDiscount(80000)`: giảm 80.000, khách trả **420.000 đồng**.

Đoạn mã thanh toán không cần một chuỗi `if/else` để hỏi “đây là loại giảm giá gì?”. Nó chỉ yêu cầu đối tượng chính sách thực hiện hành vi của mình.

~~~java
DiscountPolicy policy = new PercentageDiscount(10);
BigDecimal first = policy.discountFor(new BigDecimal("500000"));

policy = new FixedDiscount(new BigDecimal("80000"));
BigDecimal second = policy.discountFor(new BigDecimal("500000"));
~~~

Đây là **đa hình lúc chạy (runtime polymorphism)** dựa trên **ghi đè phương thức (overriding)**: cùng một cách gọi qua kiểu `DiscountPolicy` nhưng Java chọn triển khai phù hợp với kiểu đối tượng thực tế.

Trong Java còn có **nạp chồng phương thức (overloading)**: cùng tên method, khác danh sách tham số.

~~~java
void print(String text) { /* ... */ }
void print(int value) { /* ... */ }
~~~

Overloading được chọn chủ yếu theo **kiểu khai báo của biểu thức và chữ ký có thể áp dụng tại lúc biên dịch**; không phải cơ chế chọn override dựa trên đối tượng runtime. Phân biệt hai cơ chế giúp tránh ngộ nhận rằng cứ trùng tên method là ví dụ của cùng một loại đa hình.

**Một giới hạn quan trọng:** phương thức `static` không được override theo cơ chế dynamic dispatch của instance method; nếu subclass khai báo static method cùng tên/chữ ký, đó là *method hiding*. Các `private` method cũng không được subclass override như phương thức instance có thể truy cập.

### Đa hình giúp mở rộng ở đâu?

Khi xuất hiện `SeasonalDiscount` mới, chương trình có thể bổ sung một lớp/triển khai mới mà `CheckoutService` vẫn gọi `discountFor()`. Điều này giúp giảm mã phụ thuộc vào từng loại cụ thể. Tuy nhiên, nếu mỗi lần bổ sung chính sách lại buộc sửa chuỗi if/else trong service, lợi ích này bị hạn chế.

## 6. Ví dụ Java hoàn chỉnh: bốn khái niệm phối hợp

Để thấy đầy đủ, ta dùng một lớp cha trừu tượng `DiscountPolicy` với **phần kiểm tra điều kiện dùng chung**, hai lớp con cung cấp thuật toán riêng, và một `Cart` tự giữ danh sách hàng hợp lệ. Code sau chạy được với **Java 17+** trong một file `Main.java`; chỉ có một public class.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

// Một dòng hàng bất biến (record, Java 16+).
record CartLine(String sku, int quantity, BigDecimal unitPrice) {
    CartLine {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (sku.isBlank() || quantity <= 0 || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid cart line");
        }
    }

    BigDecimal total() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}

// ENCAPSULATION: Cart quản lý cách thay đổi dữ liệu của mình.
final class Cart {
    private final List<CartLine> lines = new ArrayList<>();

    void addItem(String sku, int quantity, BigDecimal unitPrice) {
        // Validation chạy trước khi List bị thay đổi.
        lines.add(new CartLine(sku, quantity, unitPrice));
    }

    List<CartLine> viewItems() {
        return List.copyOf(lines);
    }

    BigDecimal subtotal() {
        return lines.stream()
                .map(CartLine::total)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }
}

// ABSTRACTION: một hợp đồng cho mọi chính sách giảm giá.
// INHERITANCE: có thể dùng lại bước validation chung.
abstract class DiscountPolicy {
    // final: mọi subclass đều phải đi qua bước kiểm tra này.
    final BigDecimal discountFor(BigDecimal subtotal) {
        Objects.requireNonNull(subtotal, "subtotal");
        if (subtotal.signum() < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        BigDecimal discount = calculateDiscount(subtotal);

        if (discount == null || discount.signum() < 0
                || discount.compareTo(subtotal) > 0) {
            throw new IllegalStateException("Invalid discount");
        }
        return discount;
    }

    // Phần khác nhau để lớp con triển khai.
    protected abstract BigDecimal calculateDiscount(BigDecimal subtotal);
}

// INHERITANCE: chính sách phần trăm là một DiscountPolicy.
final class PercentageDiscount extends DiscountPolicy {
    private final int percent;

    PercentageDiscount(int percent) {
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException("Percent must be 0..100");
        }
        this.percent = percent;
    }

    @Override
    protected BigDecimal calculateDiscount(BigDecimal subtotal) {
        return subtotal.multiply(BigDecimal.valueOf(percent))
                .divide(BigDecimal.valueOf(100));
    }
}

// INHERITANCE: chính sách giảm số tiền cố định.
final class FixedDiscount extends DiscountPolicy {
    private final BigDecimal amount;

    FixedDiscount(BigDecimal amount) {
        Objects.requireNonNull(amount, "amount");
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Negative discount amount");
        }
        this.amount = amount;
    }

    @Override
    protected BigDecimal calculateDiscount(BigDecimal subtotal) {
        // Không cho phép giảm vượt tổng tiền.
        return amount.min(subtotal);
    }
}

// POLYMORPHISM: service làm việc với kiểu cha thay vì loại cụ thể.
final class CheckoutService {
    BigDecimal amountToPay(Cart cart, DiscountPolicy policy) {
        Objects.requireNonNull(cart, "cart");
        Objects.requireNonNull(policy, "policy");

        BigDecimal subtotal = cart.subtotal();
        return subtotal.subtract(policy.discountFor(subtotal));
    }
}

public class Main {
    public static void main(String[] args) {
        Cart cart = new Cart();
        cart.addItem("BOOK", 2, new BigDecimal("200000"));
        cart.addItem("PEN", 1, new BigDecimal("100000"));
        System.out.println(cart.subtotal()); // 500000

        CheckoutService checkout = new CheckoutService();

        // Cùng lời gọi service, khác đối tượng chính sách thực tế.
        DiscountPolicy policy = new PercentageDiscount(10);
        System.out.println(checkout.amountToPay(cart, policy)); // 450000

        policy = new FixedDiscount(new BigDecimal("80000"));
        System.out.println(checkout.amountToPay(cart, policy)); // 420000

        // Trường hợp dữ liệu sai: từ chối, không thêm hàng.
        try {
            cart.addItem("ERROR", 0, new BigDecimal("1000"));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected invalid quantity");
        }
        System.out.println(cart.subtotal()); // Vẫn 500000

        // Danh sách trả về không thể sửa trực tiếp.
        try {
            cart.viewItems().clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("Cannot modify cart through view");
        }
        System.out.println(cart.subtotal()); // Vẫn 500000

        // Giảm cố định lớn hơn subtotal vẫn cho số phải trả là 0.
        DiscountPolicy huge = new FixedDiscount(new BigDecimal("900000"));
        System.out.println(checkout.amountToPay(cart, huge)); // 0
    }
}
~~~

Chạy trong thư mục chứa `Main.java`:

~~~bash
javac Main.java
java Main
~~~

Kết quả chính, theo thứ tự:

~~~text
500000
450000
420000
Rejected invalid quantity
500000
Cannot modify cart through view
500000
0
~~~

### Đọc chương trình theo bốn khái niệm

| Khái niệm | Đoạn thể hiện trong code | Vì sao |
| --- | --- | --- |
| **Đóng gói** | `Cart.lines` là `private`; `addItem()` kiểm tra qua `CartLine`; `viewItems()` dùng `List.copyOf`. | Mã bên ngoài không trực tiếp thay đổi trạng thái danh sách, dữ liệu không hợp lệ bị từ chối trước khi thêm. |
| **Trừu tượng** | `CheckoutService` nhận tham số kiểu `DiscountPolicy` với hành vi `discountFor()`. | Service chỉ cần hợp đồng tính giảm giá, không biết chi tiết công thức. |
| **Kế thừa** | `PercentageDiscount extends DiscountPolicy` và `FixedDiscount extends DiscountPolicy`. | Hai lớp con thuộc cùng kiểu chính sách, dùng chung bước kiểm tra và tự cài công thức riêng. |
| **Đa hình** | `policy.discountFor(subtotal)` gọi `calculateDiscount()` của lớp con tương ứng. | Cùng luồng checkout nhưng phần tính tiền giảm thay đổi theo đối tượng thực tế. |

### Chính xác chuyện gì xảy ra khi gọi method?

Giả sử biến `policy` được gán `new PercentageDiscount(10)`:

1. `CheckoutService.amountToPay()` tính `subtotal = 500000`.
2. Nó gọi `policy.discountFor(subtotal)`.
3. Java chạy method `discountFor()` dùng chung từ lớp cha `DiscountPolicy` và kiểm tra subtotal không âm.
4. Bên trong method cha, lời gọi `calculateDiscount(subtotal)` được **dispatch động** đến phiên bản ghi đè trong `PercentageDiscount`.
5. Kết quả giảm là `50000`; lớp cha kiểm tra giá trị hợp lệ và trả lại.
6. Service tính `500000 - 50000 = 450000`.

Nếu `policy` tham chiếu đến `new FixedDiscount(80000)` thì các bước chung không thay đổi, chỉ **bước 4** dùng công thức của `FixedDiscount`. Kết quả phải trả là `420000`.

~~~mermaid
sequenceDiagram
    participant Main
    participant C as CheckoutService
    participant P as DiscountPolicy
    participant I as Chính sách thực tế
    Main->>C: amountToPay(cart, policy)
    C->>C: subtotal() = 500000
    C->>P: discountFor(500000)
    P->>P: Kiểm tra subtotal
    P->>I: calculateDiscount(500000)
    Note over I: Runtime chọn PercentageDiscount hoặc FixedDiscount
    I-->>P: 50000 hoặc 80000
    P->>P: Kiểm tra mức giảm hợp lệ
    P-->>C: Mức giảm
    C-->>Main: 450000 hoặc 420000
~~~

Sơ đồ trên biểu diễn luồng logic. `DiscountPolicy` trong code là **lớp cha của chính đối tượng runtime**, không phải một đối tượng thứ hai được tạo ra chỉ để chuyển lời gọi. Dispatch của Java chọn method override ngay trên đối tượng hiện tại.

## 7. Vì sao dùng abstract class trong ví dụ? Khi nào dùng interface?

Ta đã xem ví dụ interface đơn giản trước đó, còn chương trình hoàn chỉnh dùng `abstract class` vì muốn giữ **quy tắc kiểm tra dùng chung**: mọi loại giảm giá phải kiểm tra đầu vào và kết quả. Điều này được thể hiện bằng **Template Method**: method `discountFor()` là `final`, chỉ phần `calculateDiscount()` được override.

| Nhu cầu | Interface thường phù hợp | Abstract class thường phù hợp |
| --- | --- | --- |
| Khai báo năng lực/hợp đồng chung | Rất phù hợp; nhiều class độc lập có thể implement. | Có thể dùng, nhưng buộc lớp con tham gia một hệ phân cấp lớp. |
| Dùng chung trạng thái instance và constructor | Không dành cho instance fields/constructors của lớp triển khai. | Có thể định nghĩa state, constructor và logic chung. |
| Dùng chung code | Có `default`/`static` method khi cần, nhưng giới hạn. | Có method thường, `protected` helper và template. |
| Một class cần nhiều vai trò | Một class có thể implements nhiều interface. | Một class chỉ extends trực tiếp một class. |
| Bảo đảm không subclass nào bỏ qua bước validation | Chỉ khai báo contract thường chưa đủ để ép luồng xử lý chung. | Có thể dùng method `final` gọi hook `protected abstract` như ví dụ. |

**Một lựa chọn khác:** giữ `DiscountPolicy` là interface và dùng **composition** để tách đối tượng kiểm tra quy tắc hoặc phần công thức. Interface không phải lúc nào cũng tốt hơn, abstract class cũng không mặc nhiên là thiết kế “OOP hơn”. Hãy chọn theo hợp đồng, mức độ dùng chung và giới hạn mở rộng thực sự cần có.

## 8. Những nhầm lẫn khiến thiết kế OOP khó hiểu

| Nhầm lẫn | Điều cần hiểu |
| --- | --- |
| “Đóng gói = biến private + đầy đủ getter/setter.” | Đóng gói nhằm bảo vệ quy tắc và giới hạn các con đường làm thay đổi trạng thái; getter/setter vô điều kiện có thể phá mục tiêu này. |
| “Trừu tượng = dùng abstract class.” | Trừu tượng là cách chọn hợp đồng/chi tiết cần cho người dùng; class thường cũng cung cấp một mức trừu tượng. |
| “Kế thừa giúp tái sử dụng, nên cứ thấy code trùng là extends.” | Kế thừa còn là cam kết quan hệ kiểu và khả năng thay thế. Dùng composition khi chỉ muốn ghép chức năng. |
| “Đa hình = bất kỳ hai method có cùng tên.” | Đa hình runtime dựa trên override và kiểu đối tượng thực tế; overload có quy tắc chọn khác. |
| “Có inheritance mới dùng được polymorphism.” | Implement interface cũng có thể tạo đa hình, không cần extends một lớp nghiệp vụ chung. |
| “Con gọi method cha nào cũng tự động override được.” | Không override được `final`/`private`; `static` cùng chữ ký là hiding, không phải override instance. |
| “Một abstract class luôn ẩn toàn bộ cách cài đặt.” | Abstract class có thể chứa nhiều chi tiết dùng chung; mức trừu tượng phụ thuộc hợp đồng mà nó công khai. |
| “Cứ dùng bốn tính chất thì chương trình sẽ tự an toàn.” | Vẫn cần xét transaction, đồng thời, input validation, lỗi mạng và ranh giới dữ liệu trong hệ thống thực tế. |

### Một phản ví dụ về kế thừa vì tiện tay

Giả sử có `Printer` và `InvoiceService` cùng cần ghi log. Thiết kế `InvoiceService extends Printer` chỉ để dùng lại `log()` là không hợp lý: dịch vụ hóa đơn **không phải một loại máy in**. Hợp lý hơn là cho `InvoiceService` **nhận một đối tượng `Logger`** rồi gọi phương thức của nó khi cần.

~~~java
interface Logger {
    void info(String message);
}

final class InvoiceService {
    private final Logger logger;

    InvoiceService(Logger logger) {
        this.logger = logger;
    }

    void createInvoice() {
        logger.info("Invoice created");
    }
}
~~~

Đây là **composition và dependency injection** ở mức cơ bản. Nó cũng sử dụng **trừu tượng** qua `Logger` và cho phép **đa hình** nếu có nhiều cách ghi log, nhưng không cần kế thừa một lớp cha nghiệp vụ.

## 9. Tự kiểm tra bằng tình huống ngắn

**Câu 1.** Một lớp có `private int balance` nhưng `setBalance(-100)` vẫn chạy được. Đã đóng gói tốt chưa?

**Giải thích:** Chưa. Che trường khỏi truy cập trực tiếp chưa đủ; public method vẫn có thể phá invariant “số dư không âm” nếu không kiểm soát thao tác.

**Câu 2.** `CheckoutService` chỉ nhận `DiscountPolicy`, không import `PercentageDiscount`. Đây là biểu hiện của gì?

**Giải thích:** Trừu tượng. Service dựa vào hợp đồng và ít phụ thuộc chi tiết. Khi có nhiều implementation, cách sử dụng ấy cũng tạo điều kiện cho đa hình.

**Câu 3.** `PercentageDiscount` kế thừa `DiscountPolicy` nhưng trả về mức giảm 700.000 cho tổng 500.000. Có vấn đề gì?

**Giải thích:** Nó vi phạm hợp đồng “giảm không vượt tổng”; chương trình hoàn chỉnh đặt kiểm tra ở method `final` của lớp cha để phát hiện.

**Câu 4.** Biến `DiscountPolicy p` lần lượt trỏ đến đối tượng giảm phần trăm và giảm cố định, còn câu lệnh gọi vẫn là `p.discountFor(subtotal)`. Đây là gì?

**Giải thích:** Đa hình. Lời gọi bên ngoài thống nhất; method được ghi đè bên trong sẽ chạy theo loại đối tượng thực tế.

**Câu 5.** Hai lớp có chung method `formatMoney()`. Có bắt buộc tạo base class để kế thừa không?

**Giải thích:** Không. Có thể dùng helper, service hoặc đối tượng cộng tác. Chỉ tạo quan hệ kế thừa khi lớp con thực sự thỏa hợp đồng của lớp cha.

**Câu 6.** Vì sao `viewItems()` của `Cart` trả về `List.copyOf(lines)`?

**Giải thích:** Để không lộ danh sách mutable bên trong qua kết quả trả về. Lưu ý nếu phần tử của danh sách là các object mutable thì vẫn phải đánh giá nguy cơ sửa trạng thái qua từng phần tử; ở đây `CartLine` là record với các thành phần bất biến.

**Câu 7.** Nếu phải thêm một chính sách mới “giảm 15% tối đa 100.000 đồng”, phần nào cần thay đổi?

**Giải thích:** Có thể tạo `CappedPercentageDiscount extends DiscountPolicy`, override `calculateDiscount()` và giữ nguyên `CheckoutService`. Cần tiếp tục bảo đảm mức giảm hợp lệ và kiểm thử đầu vào biên. Trong hệ thống lớn, việc cấp phát/chọn chính sách phù hợp ở nơi cấu hình vẫn có thể cần cập nhật.

## 10. Khi tự thiết kế một đối tượng, hãy hỏi gì?

- **Trạng thái và quy tắc:** dữ liệu nào thuộc quyền quản lý của đối tượng? Làm sao bảo đảm không bị sửa sai? → nghĩ đến **đóng gói**.
- **Hợp đồng:** người dùng đối tượng cần yêu cầu những hành vi gì mà không phải biết thuật toán nội bộ? → nghĩ đến **trừu tượng**.
- **Quan hệ kiểu:** các triển khai có quan hệ “là một dạng” thực sự, tuân thủ cùng một hợp đồng và có phần triển khai dùng chung không? → cân nhắc **kế thừa**.
- **Biến thể hành vi:** nhiều đối tượng cần đáp ứng cùng một lời gọi với cách xử lý khác nhau không? → nghĩ đến **đa hình**.

Trong ví dụ cửa hàng, `Cart` bảo vệ dữ liệu; `DiscountPolicy` xác định khả năng mà checkout cần; các lớp giảm giá chuyên biệt kế thừa quy tắc chung; và checkout gọi cùng một hợp đồng để nhận kết quả khác nhau theo chính sách. Bốn khái niệm trở nên hữu ích khi mỗi khái niệm giải quyết **một vấn đề thiết kế cụ thể**, chứ không phải khi cố đưa đủ bốn tên gọi vào mọi class.