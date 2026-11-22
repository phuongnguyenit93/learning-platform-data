# Trừu tượng hóa trong Java: là gì và giải quyết vấn đề nào?

## 1. Khái niệm cốt lõi

**Trừu tượng hóa (abstraction)** là cách mô tả một đối tượng hoặc một khả năng bằng những đặc điểm, hành vi **cần thiết đối với người sử dụng**, trong khi để các chi tiết thực hiện nằm ở lớp hiện thực phía sau. Khi gọi một hành vi, mã sử dụng cần biết **có thể yêu cầu điều gì** và **kết quả/hợp đồng là gì**; nó không nhất thiết phải biết thuật toán, dữ liệu nội bộ hoặc hệ thống bên ngoài được dùng để hoàn thành yêu cầu.

Ví dụ đời thường: người dùng nhấn nút “Thanh toán”, quan tâm số tiền, trạng thái thành công/thất bại và chứng từ; họ không cần biết giao dịch được chuyển qua ngân hàng hay ví điện tử, cách tạo yêu cầu mạng hoặc cách đối soát nội bộ.

Trong Java, có thể thể hiện ranh giới trừu tượng bằng **interface**, **abstract class**, và cả những lớp thông thường có API công khai rõ ràng. Trừu tượng hóa là **nguyên tắc thiết kế**; `interface` và `abstract` là **công cụ ngôn ngữ** hỗ trợ nguyên tắc ấy. Không phải cứ tạo interface là đã tạo ra một trừu tượng tốt.

Hãy nhớ ba câu hỏi:

- **Cái gì?** Người gọi có thể yêu cầu hành vi nào?
- **Cam kết nào?** Đầu vào hợp lệ, đầu ra, lỗi và tác dụng phụ được hiểu ra sao?
- **Như thế nào?** Ai thực hiện và bằng cơ chế gì? Đây là phần có thể ẩn sau ranh giới trừu tượng.

## 2. Vì sao cần trừu tượng hóa?

Giả sử một dịch vụ bán hàng thanh toán trực tiếp bằng một lớp chuyển khoản ngân hàng cụ thể:

```java
// Minh họa sự phụ thuộc trực tiếp; không phải chương trình độc lập.
final class CheckoutService {
    private final BankTransferGateway gateway = new BankTransferGateway();

    Receipt checkout(long totalVnd) {
        return gateway.pay(totalVnd);
    }
}
```

Đoạn này có thể đủ cho một bài toán nhỏ, nhưng khi nhu cầu mở rộng sẽ xuất hiện các vấn đề:

1. **Phụ thuộc chặt vào cách thực hiện:** `CheckoutService` tự quyết định dùng `BankTransferGateway`. Nếu đổi sang ví điện tử, có thể phải sửa lớp xử lý nghiệp vụ.
2. **Khó thay thế để kiểm thử:** kiểm tra quy tắc checkout có thể vô tình gọi tích hợp thanh toán thật hoặc phải dựng môi trường ngân hàng giả lập.
3. **Chi tiết kỹ thuật lan vào nghiệp vụ:** nếu dịch vụ biết tên endpoint, cách ký yêu cầu hay cấu trúc phản hồi của từng nhà cung cấp, logic nghiệp vụ ngày càng khó đọc và khó bảo trì.
4. **Thay đổi dây chuyền:** nhiều nơi cùng biết lớp cụ thể sẽ cùng bị tác động khi thư viện hoặc nhà cung cấp thay đổi.

Ý tưởng: cho mã nghiệp vụ phụ thuộc vào một **khả năng ổn định** mang tên `PaymentGateway`; từng nhà cung cấp triển khai khả năng đó. Khi ấy “thanh toán” là khái niệm nghiệp vụ được công bố, còn “gửi yêu cầu đến đâu và làm thế nào” là chi tiết phía sau.

Mối quan hệ được mong muốn:

```text
CheckoutService --> PaymentGateway (hợp đồng)
                         ^
                         |
             +-----------+-----------+
             |                       |
   BankTransferGateway          WalletGateway
   (cách làm thứ nhất)          (cách làm thứ hai)
```

Sơ đồ thể hiện hướng phụ thuộc về **kiểu dữ liệu** của mã sử dụng. Việc tạo và chọn một hiện thực vẫn cần xảy ra ở đâu đó, chẳng hạn tại `main` hoặc trong phần cấu hình ứng dụng.

## 3. Ví dụ hoàn chỉnh, chạy được với Java 17+

Tạo tệp **`AbstractionDemo.java`** với nội dung sau. Để tập trung vào abstraction, các gateway chỉ trả về chứng từ giả lập có giá trị xác định; ví dụ **không kết nối hay thực hiện giao dịch thanh toán thật**.

```java
import java.util.Objects;

interface PaymentGateway {
    Receipt pay(long amountVnd);
}

record Receipt(String provider, long amountVnd, String reference) {
}

final class BankTransferGateway implements PaymentGateway {
    @Override
    public Receipt pay(long amountVnd) {
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("amountVnd must be positive");
        }
        return new Receipt("BankTransfer", amountVnd, "BANK-001");
    }
}

final class WalletGateway implements PaymentGateway {
    @Override
    public Receipt pay(long amountVnd) {
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("amountVnd must be positive");
        }
        return new Receipt("Wallet", amountVnd, "WALLET-001");
    }
}

final class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
    }

    Receipt checkout(long totalVnd) {
        if (totalVnd <= 0) {
            throw new IllegalArgumentException("totalVnd must be positive");
        }
        return gateway.pay(totalVnd);
    }
}

public class AbstractionDemo {
    public static void main(String[] args) {
        CheckoutService bankCheckout =
                new CheckoutService(new BankTransferGateway());
        CheckoutService walletCheckout =
                new CheckoutService(new WalletGateway());

        System.out.println(bankCheckout.checkout(120_000));
        System.out.println(walletCheckout.checkout(120_000));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac AbstractionDemo.java
java AbstractionDemo
```

Kết quả chính xác:

```text
Receipt[provider=BankTransfer, amountVnd=120000, reference=BANK-001]
Receipt[provider=Wallet, amountVnd=120000, reference=WALLET-001]
```

**Phân tích từng vai trò:**

- `PaymentGateway` nêu ra **khả năng thanh toán** qua phương thức `pay(long)`. Người sử dụng làm việc qua tên kiểu và phương thức này.
- `BankTransferGateway` và `WalletGateway` là **hai hiện thực thay thế được** của cùng hợp đồng. Cả hai phải cung cấp `pay(long)`.
- `Receipt` là dữ liệu kết quả chung, giúp mã gọi không phải hiểu hai cấu trúc phản hồi khác nhau.
- `CheckoutService` giữ một trường thuộc kiểu `PaymentGateway`, nhận hiện thực qua constructor và chỉ gọi phương thức hợp đồng. Đây là **dependency injection bằng constructor** ở mức Java thuần.
- `main` chọn hiện thực cụ thể khi ghép các đối tượng. Việc lựa chọn được đặt ở nơi tạo ứng dụng, tách khỏi logic `checkout`.
- Khi gọi `gateway.pay(totalVnd)`, Java chọn phương thức của đối tượng thực tế đang được tham chiếu (đa hình lúc chạy). **Trừu tượng hóa** xác định giao diện chung; **đa hình** giúp nhiều hiện thực đáp ứng lời gọi qua giao diện đó.

Điểm quan trọng: thay `new BankTransferGateway()` bằng `new WalletGateway()` ở nơi khởi tạo là có thể đổi cách thanh toán mà không sửa mã nguồn của `CheckoutService`. Điều này hữu ích khi nghiệp vụ thật sự cần nhiều hiện thực hoặc cần thay thế thành phần trong kiểm thử.

## 4. “Ẩn chi tiết” nghĩa là gì, và không có nghĩa là gì?

Trừu tượng hóa **không nhất thiết giấu mọi thứ**. Một hợp đồng tốt phải công bố đủ thông tin để người gọi dùng đúng: đơn vị tiền tệ, điều kiện số tiền dương, kiểu dữ liệu trả về, điều kiện lỗi, tính đồng bộ/bất đồng bộ, tác dụng phụ và các bảo đảm có ý nghĩa. Trong ví dụ, `amountVnd` cho thấy giá trị được tính bằng VND, `long` thể hiện số nguyên, `Receipt` thống nhất đầu ra và `IllegalArgumentException` được dùng cho số tiền không hợp lệ.

Điều được che khỏi `CheckoutService` là các quyết định **không cần thiết đối với nghiệp vụ checkout**: giao thức gọi API, cách xác thực với nhà cung cấp, phương thức ký số, retry, hoặc chuyển đổi JSON thành đối tượng Java. Khi triển khai thật, những chi tiết này phải được hiện thực và kiểm thử riêng.

Một interface quá mơ hồ như `execute(Object value)` không phải là trừu tượng tốt chỉ vì nó tổng quát. Người dùng khó biết loại dữ liệu nào hợp lệ và kết quả ra sao. Ngược lại, tên `pay(long amountVnd)` cùng một hợp đồng rõ ràng truyền đạt đúng khả năng của thành phần.

## 5. Interface, abstract class và lớp thường

| Công cụ Java | Vai trò thường gặp trong trừu tượng hóa | Điều cần hiểu |
| --- | --- | --- |
| `interface` | Định nghĩa **khả năng/hợp đồng** chung cho những hiện thực có thể khác nhau. | Một lớp có thể `implements` nhiều interface; interface cũng có thể khai báo phương thức `default` và `static`. |
| `abstract class` | Định nghĩa một **loại cơ sở** có thể giữ trạng thái, constructor, hành vi dùng chung và phương thức abstract để lớp con hoàn thiện. | Không thể `new` trực tiếp abstract class; một lớp Java chỉ `extends` một lớp cha. |
| Lớp thường với API công khai | Đưa ra các thao tác dễ dùng và giấu chi tiết trong phương thức/private fields. | Không cần tạo interface riêng nếu chưa có lý do thay thế hoặc ranh giới phụ thuộc hữu ích. |

Ví dụ ngắn về `abstract class` (đoạn minh họa thành phần, không chứa `main`):

```java
abstract class Shape {
    private final String color;

    protected Shape(String color) {
        this.color = color;
    }

    public String color() {
        return color;
    }

    public abstract double area();
}

final class Circle extends Shape {
    private final double radius;

    Circle(String color, double radius) {
        super(color);
        this.radius = radius;
    }

    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
}
```

Kiểu `Shape` công bố “mọi hình có màu và tính được diện tích”, đồng thời chia sẻ trạng thái `color`. Lớp `Circle` quyết định công thức cụ thể. Trong bài toán gateway, `interface` phù hợp vì ta chủ yếu cần một khả năng chung; không nhất thiết có trạng thái hay cấu trúc kế thừa chung giữa các nhà cung cấp.

**Cần phân biệt:** `abstract class` và `interface` không đồng nghĩa với toàn bộ khái niệm “abstraction”. Chúng giúp khai báo ranh giới; chất lượng của ranh giới vẫn phụ thuộc vào bài toán và hợp đồng được thiết kế.

## 6. Trừu tượng hóa khác gì đóng gói và đa hình?

Ba khái niệm liên quan nhưng trả lời các câu hỏi khác nhau:

- **Trừu tượng hóa (abstraction):** người sử dụng **cần biết và có thể yêu cầu điều gì?** Ví dụ `PaymentGateway.pay` là khả năng chung.
- **Đóng gói (encapsulation):** **ai được phép truy cập hoặc thay đổi trạng thái/chi tiết nội bộ?** Ví dụ dùng trường `private`, cung cấp phương thức công khai phù hợp, giữ bất biến của đối tượng.
- **Đa hình (polymorphism):** **cùng một lời gọi có thể được thực hiện bởi những kiểu đối tượng nào?** Ví dụ `PaymentGateway gateway` có thể trỏ đến gateway ngân hàng hoặc ví.

Một lớp với các trường `private` có thể đóng gói tốt nhưng API công khai vẫn kém trừu tượng nếu buộc mã gọi phải biết quá nhiều chi tiết kỹ thuật. Ngược lại, việc khai báo interface cũng không tự bảo đảm dữ liệu bên trong các hiện thực được đóng gói đúng.

## 7. Kiểm thử trở nên đơn giản hơn thế nào?

Một trong các lợi ích rõ nhất là dùng **test double**: cung cấp một hiện thực thay thế có kiểm soát để kiểm tra riêng logic `CheckoutService`. Vì `PaymentGateway` chỉ có một phương thức abstract, có thể viết một lambda như sau trong chương trình Java có các kiểu ở ví dụ trên:

```java
PaymentGateway fakeGateway =
        amount -> new Receipt("Fake", amount, "TEST-001");
CheckoutService service = new CheckoutService(fakeGateway);

Receipt receipt = service.checkout(500);
System.out.println(receipt.provider()); // Fake
```

Đây là **đoạn minh họa**, không phải tệp độc lập: đặt bên trong một phương thức khi các khai báo `PaymentGateway`, `Receipt` và `CheckoutService` đã tồn tại. Mục tiêu là kiểm tra luồng checkout mà không cần giao tiếp với hệ thống thanh toán bên ngoài. Lưu ý rằng fake này không thay thế được các kiểm thử tích hợp nhằm xác minh gateway thật hoạt động đúng.

Khi nhiều hiện thực cùng dựa vào một hợp đồng, nên kiểm tra những hành vi chung của chúng: xử lý số tiền không hợp lệ, đơn vị và ý nghĩa của số tiền, tính nhất quán của dữ liệu kết quả và quy tắc lỗi. Nếu hai gateway trả về giá trị trái ngược với hợp đồng, tính thay thế sẽ mất dù chúng đều biên dịch thành công.

## 8. Khi nào nên tạo trừu tượng? Khi nào chưa cần?

**Có cơ sở tốt để tạo trừu tượng** khi một khả năng có từ hai cách thực hiện hợp lý; phần nghiệp vụ cần tách khỏi thư viện, nhà cung cấp hoặc hạ tầng; cần thay thế phụ thuộc khi kiểm thử; hoặc có một hợp đồng ổn định được nhiều thành phần sử dụng. Một interface tại ranh giới “thanh toán”, “gửi thông báo” hay “đọc dữ liệu” thường dễ giải thích vì nó gắn với khả năng rõ ràng.

**Chưa chắc cần tạo interface** nếu chương trình rất nhỏ, chỉ có một hiện thực, chưa có nhu cầu tách phụ thuộc hoặc tên hợp đồng chỉ lặp nguyên tên lớp cụ thể mà không tạo ra ý nghĩa mới. Tạo hàng chục interface chỉ để mỗi lớp có một `I...Service` tương ứng có thể tăng số tệp, số bước tra cứu và chi phí bảo trì.

Tránh những lỗi thường gặp:

1. **Trừu tượng quá sớm:** đoán trước nhiều biến thể chưa tồn tại, thiết kế phương thức chung quá tổng quát rồi phải sửa liên tục.
2. **Lộ chi tiết nhà cung cấp:** interface trả về đối tượng SDK cụ thể, buộc mọi caller vẫn phụ thuộc vào SDK đó.
3. **Hợp đồng mơ hồ:** không nói rõ đơn vị dữ liệu, giá trị hợp lệ, lỗi, `null`, tác dụng phụ hoặc điều kiện tiền/hậu.
4. **Ép các hiện thực không tương thích vào cùng interface:** mỗi lớp hiểu `pay` theo cách khác nhau khiến caller phải dùng `instanceof` hoặc `if` để phân biệt.
5. **Hiểu nhầm thay thế được là giống hệt nhau:** các hiện thực có thể khác cách làm và hiệu năng, nhưng vẫn phải tôn trọng những cam kết chung có thể quan sát từ phía caller.
6. **Nhầm abstraction với bảo mật:** ẩn chi tiết API hoặc dùng `private` không thay thế kiểm soát quyền, xác thực, mã hóa và quản lý bí mật.

Một phép thử thiết kế hữu ích: **nếu thay hiện thực A bằng B, phần gọi có tiếp tục đúng mà không cần biết B là ai không?** Nếu câu trả lời là “có” trong phạm vi các cam kết đã công bố, ranh giới trừu tượng đang có ích.

## 9. Quy trình áp dụng vào bài toán thực tế

1. **Xác định nghiệp vụ cần làm gì.** Ví dụ checkout cần yêu cầu một khoản thanh toán và nhận kết quả thống nhất.
2. **Viết hợp đồng nhỏ, rõ và ổn định.** Xác định tên phương thức, tham số, đơn vị, giá trị trả về, lỗi và các bảo đảm cần thiết; không bê nguyên giao diện của SDK.
3. **Để mã sử dụng phụ thuộc vào hợp đồng.** Nhận `PaymentGateway` qua constructor, thay vì tự tạo gateway bên trong nghiệp vụ.
4. **Cài đặt hiện thực cụ thể.** Mỗi gateway ánh xạ hợp đồng vào công nghệ hoặc nhà cung cấp tương ứng và tôn trọng cam kết chung.
5. **Ghép đối tượng tại điểm cấu hình.** Ở Java thuần có thể dùng `new` tại `main`; một framework DI có thể tự quản lý việc tạo/lắp ghép này khi cần.
6. **Thử khả năng thay thế.** Chạy cùng logic với hai hiện thực, test double và các trường hợp đầu vào/lỗi đã định nghĩa.

**Tự kiểm tra hiểu bài:**

- Nếu `CheckoutService` vẫn phải kiểm tra `if (gateway instanceof WalletGateway)` để quyết định luồng xử lý, ranh giới trừu tượng có thể đang thiếu hoặc sai điều gì?
- Nếu một hệ thống chỉ cần lưu một chuỗi cố định, việc tạo `StringProvider`, `DefaultStringProvider` và factory riêng mang lại giá trị thực tế nào?
- Nếu API `PaymentGateway` trả về `BankSdkResponse`, phần nghiệp vụ đã thực sự tách khỏi nhà cung cấp chưa?

**Kết luận:** trừu tượng hóa cho phép lập trình theo **khả năng và hợp đồng cần thiết**, để mỗi bên có thể thay đổi chi tiết thực hiện trong phạm vi cam kết của mình. Mục tiêu không phải thêm nhiều lớp/interface, mà là tạo ra một ranh giới khiến phần mã sử dụng dễ hiểu, dễ kiểm thử và ít phải thay đổi khi cách thực hiện thay đổi.
