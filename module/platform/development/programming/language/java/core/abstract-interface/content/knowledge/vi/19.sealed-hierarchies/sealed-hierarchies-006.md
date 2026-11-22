# Interface con `sealed` và `non-sealed` trong Java

Từ Java 17, sealed classes và sealed interfaces là tính năng chính thức để giới hạn những kiểu nào được phép kế thừa hoặc triển khai trực tiếp một kiểu cha. Với interface, cơ chế này giúp mô hình hóa một tập hợp nhánh đã biết, đồng thời cho phép mở rộng có chủ đích ở những nhánh cần linh hoạt.

Điểm cần phân biệt: `sealed` giới hạn các kiểu con trực tiếp; `non-sealed` mở rộng một nhánh của hệ phân cấp để những kiểu khác tiếp tục triển khai hoặc kế thừa nhánh đó.

## 1. Vì sao interface con không thể là `final`?

Một sealed interface có thể cho phép cả class trực tiếp triển khai và interface con trực tiếp mở rộng. Một **class** được phép cần có chính sách `final`, `sealed` hoặc `non-sealed` (record vốn final). Một **interface con** chỉ được chọn `sealed` hoặc `non-sealed`: Java không cho phép khai báo `final interface`.

`sealed interface` con đóng danh sách nhánh trực tiếp ở tầng mới; `non-sealed interface` con là hợp đồng mở cho những class hay interface tiếp theo. Vì vậy, dùng `non-sealed` trên interface con là quyết định về quyền mở rộng API, không chỉ là cách tránh lỗi biên dịch.

## 2. Cách khai báo `sealed interface`

Dùng mệnh đề `permits` để liệt kê các kiểu con trực tiếp:

~~~java
sealed interface PaymentMethod
        permits CardPayment, CashPayment, FlexiblePaymentMethod {
    String description();
}
~~~

Trong ví dụ, chỉ `CardPayment`, `CashPayment` và `FlexiblePaymentMethod` được phép trực tiếp triển khai hoặc mở rộng `PaymentMethod`. Danh sách này không liệt kê mọi kiểu nằm sâu hơn trong hệ phân cấp.

Mỗi kiểu được liệt kê phải thật sự là kiểu con trực tiếp của sealed type. Nếu `CardPayment` là một class `sealed`, nó phải có danh sách `permits` của riêng mình. Nếu `FlexiblePaymentMethod` là `non-sealed`, các kiểu như `GiftCardPayment` có thể triển khai interface đó mà không cần xuất hiện trong danh sách của `PaymentMethod`.

Nếu bỏ mệnh đề `permits`, các kiểu con trực tiếp được cho phép phải được khai báo cùng compilation unit với sealed type. Khai báo tường minh thường dễ đọc hơn khi cần thể hiện rõ phạm vi được phép.

## 3. Các quy tắc của Java

- Sealed classes và sealed interfaces được hoàn thiện trong Java 17. Khi biên dịch, hãy dùng source level tương thích, chẳng hạn `javac --release 17`.
- Các kiểu được nêu trong `permits` phải là kiểu con trực tiếp của sealed class/interface đó.
- Trong named module, sealed type và các kiểu con trực tiếp được phép phải thuộc cùng module. Trong unnamed module, chúng phải thuộc cùng package.
- Mỗi kiểu con trực tiếp phải xác định nhánh bằng `final`, `sealed` hoặc `non-sealed`; record và enum vốn final theo quy tắc của ngôn ngữ.
- `non-sealed` chỉ hợp lệ khi kiểu đó trực tiếp kế thừa hoặc triển khai một sealed type. Viết đúng dấu gạch nối: `non-sealed`.
- Quy tắc sealed kiểm soát quan hệ kế thừa trực tiếp. Một kiểu ở sâu hơn có thể không nằm trong `permits` của interface gốc, miễn là nó đi qua một nhánh đã được mở bằng `non-sealed`.

## 4. Ví dụ hoàn chỉnh chạy được trên Java 17

Lưu nội dung sau vào file `SealedInterfaceDemo.java`. Tất cả các kiểu đều ở cùng file và cùng unnamed package để ví dụ đơn giản, có thể biên dịch trực tiếp.

~~~java
public class SealedInterfaceDemo {
    public static void main(String[] args) {
        PaymentMethod[] methods = {
            new CashPayment(),
            new CardPayment("4242"),
            new InternationalCardPayment("7777", "VN"),
            new GiftCardPayment("GC-01")
        };

        for (PaymentMethod method : methods) {
            System.out.println(method.description());
        }
    }
}

sealed interface PaymentMethod
        permits CardPayment, CashPayment, FlexiblePaymentMethod {
    String description();
}

sealed class CardPayment implements PaymentMethod
        permits InternationalCardPayment {
    private final String lastFour;

    CardPayment(String lastFour) {
        this.lastFour = lastFour;
    }

    @Override
    public String description() {
        return "Card ****" + lastFour;
    }
}

final class InternationalCardPayment extends CardPayment {
    private final String country;

    InternationalCardPayment(String lastFour, String country) {
        super(lastFour);
        this.country = country;
    }

    @Override
    public String description() {
        return "International " + super.description() + " (" + country + ")";
    }
}

record CashPayment() implements PaymentMethod {
    @Override
    public String description() {
        return "Cash";
    }
}

non-sealed interface FlexiblePaymentMethod extends PaymentMethod {
}

final class GiftCardPayment implements FlexiblePaymentMethod {
    private final String code;

    GiftCardPayment(String code) {
        this.code = code;
    }

    @Override
    public String description() {
        return "Gift card " + code;
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 SealedInterfaceDemo.java
java SealedInterfaceDemo
~~~

Kết quả stdout chính xác:

~~~text
Cash
Card ****4242
International Card ****7777 (VN)
Gift card GC-01
~~~

## 5. Đọc ví dụ theo từng nhánh

- `PaymentMethod` là sealed interface gốc. Mệnh đề `permits` cho phép đúng ba kiểu con trực tiếp.
- `CardPayment` là sealed class, nên nó tạo một tầng giới hạn tiếp theo. Nó chỉ cho phép `InternationalCardPayment` kế thừa trực tiếp.
- `InternationalCardPayment` khai báo `final`, vì vậy nhánh thẻ quốc tế dừng ở class này.
- `CashPayment` là record. Record tự động final và đáp ứng yêu cầu của một kiểu con trực tiếp.
- `FlexiblePaymentMethod` khai báo `non-sealed`. Nó vẫn phải nằm trong danh sách `permits` của `PaymentMethod`, nhưng nhánh của nó được mở. `GiftCardPayment` chỉ cần triển khai `FlexiblePaymentMethod`; không cần được thêm vào `permits` của `PaymentMethod`.
- Vòng lặp gọi cùng một phương thức `description()` thông qua kiểu tham chiếu `PaymentMethod`. Tính đa hình vẫn hoạt động bình thường; sealed không thay thế hay loại bỏ cơ chế đa hình của Java.

Có thể hình dung hệ phân cấp như sau:

~~~text
PaymentMethod (sealed)
├── CardPayment (sealed)
│   └── InternationalCardPayment (final)
├── CashPayment (record, implicitly final)
└── FlexiblePaymentMethod (non-sealed)
    └── GiftCardPayment (final trong ví dụ)
~~~

Sơ đồ cho thấy `permits` quản lý những cạnh trực tiếp từ một sealed type. `PaymentMethod` không cần liệt kê `InternationalCardPayment` hay `GiftCardPayment`, vì chúng không trực tiếp kế thừa hoặc triển khai `PaymentMethod`.

## 6. Khi nào nên dùng `sealed` và `non-sealed`?

Dùng `sealed` khi miền dữ liệu có các biến thể được xác định rõ, chẳng hạn trạng thái giao dịch, loại kết quả hoặc các loại thông báo trong một thư viện. Danh sách kiểu con trực tiếp giúp người đọc và trình biên dịch hiểu những nhánh hợp lệ.

Dùng `non-sealed` khi muốn giữ một nhánh mở cho phần mở rộng, ví dụ cho phép ứng dụng thêm nhiều loại phương thức thanh toán riêng. Hãy mở đúng nhánh cần mở; nếu mọi nhánh đều `non-sealed`, lợi ích giới hạn của sealed type sẽ giảm đáng kể.

Dùng `final` cho class con khi muốn khóa nhánh tại đó. Nếu cần thêm một tầng kiểm soát, dùng `sealed` và khai báo danh sách con của tầng đó. Các lựa chọn này diễn đạt chính sách mở rộng ngay trong mã nguồn, giúp API rõ ràng hơn.

## 7. Liên hệ với pattern matching và `switch`

Một sealed hierarchy cho trình biên dịch biết các nhánh trực tiếp có thể xuất hiện. Điều này có thể hỗ trợ kiểm tra tính đầy đủ khi dùng pattern matching trong `switch`. Ví dụ với Java 21 trở lên, có thể xử lý các nhánh của `PaymentMethod` bằng các type pattern tương ứng với `CardPayment`, `CashPayment` và `FlexiblePaymentMethod`; pattern `CardPayment` cũng bao phủ các kiểu con của nó.

Pattern matching for `switch` đã được hoàn thiện trong Java 21. Trong Java 17, tính năng này vẫn ở giai đoạn preview và cần tùy chọn preview tương ứng. Ví dụ chạy được ở phần trên không dùng pattern matching for `switch`, vì vậy chỉ cần Java 17 thông thường.

Sealed không tự làm một chuỗi `if/else` trở nên exhaustive và cũng không tự đảm bảo mọi nhánh nghiệp vụ đã được xử lý. Lợi ích kiểm tra tính đầy đủ phụ thuộc vào cấu trúc biểu thức và phiên bản Java đang dùng.

## 8. Lỗi thường gặp

**Quên modifier ở kiểu con trực tiếp.** Một class thông thường triển khai sealed interface mà không khai báo `final`, `sealed` hoặc `non-sealed` sẽ không biên dịch được. Hãy chọn chính sách mở rộng rõ ràng.

**Dùng `final` cho interface.** Interface không dùng modifier `final`; chọn `sealed` nếu muốn tiếp tục giới hạn các interface con hoặc `non-sealed` nếu muốn mở nhánh.

**Liệt kê nhầm kiểu con gián tiếp trong `permits`.** `permits` chỉ chứa kiểu kế thừa/triển khai trực tiếp. Hãy thêm kiểu trung gian vào danh sách và quản lý nhánh sâu hơn tại kiểu trung gian đó.

**Mở nhánh nhưng vẫn kỳ vọng giới hạn toàn bộ cây.** Một kiểu `non-sealed` chủ động cho phép phần mở rộng phía dưới. Nếu cần kiểm soát toàn bộ các kiểu con ở nhánh đó, cân nhắc `sealed` thay vì `non-sealed`.

**Đặt các kiểu con trực tiếp sai package/module.** Kiểm tra ranh giới package khi dùng unnamed module hoặc ranh giới module khi dùng named module.

**Biên dịch bằng phiên bản Java cũ.** Sealed type yêu cầu Java 17 để dùng như tính năng chính thức. Kiểm tra JDK và tùy chọn `--release` của dự án.

## 9. Checklist thiết kế

- Xác định rõ những kiểu nào được phép kế thừa/triển khai trực tiếp interface gốc.
- Với từng kiểu con trực tiếp, chọn `final`, `sealed` hay `non-sealed` theo chính sách mở rộng mong muốn.
- Nếu chọn `sealed` ở tầng giữa, khai báo `permits` cho tầng đó.
- Chỉ mở nhánh bằng `non-sealed` khi thực sự cần cho phép mở rộng bên ngoài.
- Giữ các kiểu con trực tiếp trong cùng module hoặc package theo quy tắc của Java.
- Biên dịch ví dụ với đúng phiên bản Java mục tiêu và kiểm tra cả lỗi biên dịch lẫn kết quả chạy.

Thiết kế tốt thường dùng sealed để mô tả các biến thể hợp lệ ở ranh giới API, rồi chỉ mở những nhánh có nhu cầu mở rộng thực tế. Cách này cân bằng giữa kiểm soát hệ phân cấp và tính linh hoạt của ứng dụng.
