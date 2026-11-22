# Modifier `final`, `sealed` và `non-sealed` của lớp con trực tiếp

Trong Java, một kiểu được khai báo bằng `sealed` kiểm soát những lớp hoặc interface nào được phép kế thừa hay triển khai trực tiếp nó. Mỗi kiểu con trực tiếp phải xác định chính sách kế thừa tiếp theo bằng `final`, `sealed` hoặc `non-sealed` (trừ những kiểu vốn đã ngầm `final`, chẳng hạn record).

Ba modifier này trả lời ba câu hỏi khác nhau: nhánh kế thừa có kết thúc ở đây không, có tiếp tục nhưng vẫn bị giới hạn không, hay được mở cho mã bên ngoài mở rộng tự do?

## 1. Bối cảnh: sealed type và các nhánh kế thừa

Sealed classes và sealed interfaces trở thành tính năng chính thức trong Java 17. Chúng hữu ích khi mô hình miền nghiệp vụ có một tập hợp kiểu con được kiểm soát, ví dụ các loại kết quả, hình học, thông điệp hoặc phương thức thanh toán.

Ví dụ, một interface `Payment` có thể cho phép đúng ba kiểu trực tiếp: `CardPayment`, `CashPayment` và `CustomPayment`. Java yêu cầu từng nhánh này khai báo cách nó tiếp tục được kế thừa.

- `final`: nhánh kết thúc tại kiểu này.
- `sealed`: nhánh tiếp tục, nhưng chỉ các kiểu được cho phép mới có thể kế thừa trực tiếp kiểu này.
- `non-sealed`: nhánh được mở lại; các lớp khác có thể kế thừa kiểu này mà không cần được liệt kê trong danh sách `permits` của tổ tiên sealed.

Các modifier trên áp dụng cho khai báo lớp hoặc interface. Chúng không phải modifier của phương thức và không tự quyết định một đối tượng có bất biến hay không.

## 2. Ba modifier khác nhau như thế nào?

| Modifier trên kiểu con trực tiếp | Ý nghĩa | Kế thừa tiếp theo |
| --- | --- | --- |
| `final` | Kiểu này là lá của nhánh kế thừa. | Không lớp nào được kế thừa lớp này; một interface `final` không hợp lệ. |
| `sealed` | Kiểu này tiếp tục giới hạn các kiểu con trực tiếp của chính nó. | Các kiểu con trực tiếp tiếp theo phải được khai báo trong `permits`, hoặc được trình biên dịch suy ra khi đủ điều kiện. |
| `non-sealed` | Kiểu này chủ động bỏ giới hạn sealed đối với nhánh của nó. | Các lớp có thể kế thừa kiểu này mà không cần nằm trong danh sách `permits` của kiểu sealed ban đầu. |

### `final`: đóng nhánh kế thừa

Khi một lớp trực tiếp kế thừa lớp sealed hoặc trực tiếp triển khai interface sealed và được khai báo `final`, không thể tạo lớp con từ lớp đó.

```java
sealed interface Payment permits CardPayment {}

final class CardPayment implements Payment {}
```

Trong ví dụ này, `CardPayment` là một kiểu được phép của `Payment`, và nhánh `CardPayment` kết thúc tại đây. Khai báo như `class PremiumCardPayment extends CardPayment {}` sẽ không biên dịch vì `CardPayment` là `final`.

Dùng `final` khi kiểu con đại diện cho một trường hợp cụ thể mà thiết kế không cho phép mở rộng thêm.

### `sealed`: tiếp tục giới hạn một nhánh

Một kiểu con có thể tự nó là sealed. Khi đó, nó trở thành một sealed type mới với danh sách kiểu con trực tiếp riêng.

```java
sealed interface Payment permits CashPayment {}

sealed class CashPayment implements Payment
        permits ExactCashPayment {}

final class ExactCashPayment extends CashPayment {}
```

`CashPayment` là kiểu được `Payment` cho phép, đồng thời giới hạn những lớp có thể kế thừa nó. Trong ví dụ, chỉ `ExactCashPayment` được phép kế thừa trực tiếp `CashPayment`. Một lớp khác tự khai báo `extends CashPayment` mà không được liệt kê sẽ bị từ chối khi biên dịch.

Dùng `sealed` khi muốn phân cấp có nhiều tầng nhưng mỗi tầng vẫn phải tuân theo một danh sách kiểu con được kiểm soát.

### `non-sealed`: mở lại một nhánh

`non-sealed` cho phép một kiểu con trực tiếp của sealed type trở thành điểm mở rộng thông thường.

```java
sealed interface Payment permits CustomPayment {}

non-sealed class CustomPayment implements Payment {}

class BrandedPayment extends CustomPayment {}
class PartnerPayment extends CustomPayment {}
```

`CustomPayment` vẫn phải được liệt kê trong `permits` của `Payment`, vì nó là kiểu triển khai trực tiếp. Sau đó, `BrandedPayment` và `PartnerPayment` có thể kế thừa `CustomPayment` mà không cần được thêm vào `permits` của `Payment`.

Dùng `non-sealed` khi muốn kiểm soát các loại trực tiếp của một abstraction, nhưng vẫn muốn cho thư viện, plugin hoặc mã ứng dụng mở rộng một nhánh cụ thể.

Lưu ý rằng `non-sealed` không có nghĩa là kiểu đó có thể được thêm tùy ý vào danh sách trực tiếp của sealed type. Bản thân kiểu `non-sealed` vẫn phải là một kiểu con trực tiếp được cho phép.

## 3. Ví dụ Java 17+ có thể biên dịch và chạy

Lưu nội dung sau vào tệp `SealedHierarchyDemo.java`. Tất cả các kiểu đều nằm trong cùng compilation unit và package mặc định để ví dụ tập trung vào modifier.

```java
public class SealedHierarchyDemo {
    public static void main(String[] args) {
        Payment[] payments = {
            new CardPayment(),
            new ExactCashPayment(),
            new CustomPayment(),
            new BrandedPayment()
        };

        for (Payment payment : payments) {
            System.out.println(payment.label());
        }
    }
}

sealed interface Payment
        permits CardPayment, CashPayment, CustomPayment {
    String label();
}

final class CardPayment implements Payment {
    @Override
    public String label() {
        return "card";
    }
}

sealed class CashPayment implements Payment
        permits ExactCashPayment {
    @Override
    public String label() {
        return "cash";
    }
}

final class ExactCashPayment extends CashPayment {}

non-sealed class CustomPayment implements Payment {
    @Override
    public String label() {
        return "custom";
    }
}

final class BrandedPayment extends CustomPayment {
    @Override
    public String label() {
        return "branded";
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```text
javac --release 17 SealedHierarchyDemo.java
java SealedHierarchyDemo
```

Kết quả chuẩn (stdout):

```text
card
cash
custom
branded
```

Ví dụ cho thấy modifier không thay thế tính đa hình. Mảng có kiểu phần tử là `Payment`, nhưng mỗi đối tượng vẫn thực thi phiên bản `label()` của lớp thực tế. Các modifier kiểm soát cấu trúc kế thừa tại thời điểm biên dịch.

## 4. Đọc cấu trúc phân cấp trong ví dụ

```text
Payment (sealed)
├── CardPayment (final)
├── CashPayment (sealed)
│   └── ExactCashPayment (final)
└── CustomPayment (non-sealed)
    └── BrandedPayment (final)
```

- `CardPayment` đóng nhánh của nó bằng `final`.
- `CashPayment` tạo thêm một tầng được kiểm soát bằng `sealed`; danh sách cho phép của tầng này chỉ gồm `ExactCashPayment`.
- `CustomPayment` là một nhánh mở. Vì thế `BrandedPayment` có thể kế thừa nó dù không xuất hiện trong `permits` của `Payment`.
- `BrandedPayment` lại được khai báo `final`, nên nhánh này kết thúc tại lớp đó.

Các modifier được xét theo quan hệ kế thừa trực tiếp. Một lớp nằm sâu trong nhánh `non-sealed` không cần khai báo `final`, `sealed` hoặc `non-sealed` chỉ vì tổ tiên xa của nó là sealed. Những quy tắc này áp dụng khi lớp đó trực tiếp kế thừa hoặc triển khai một sealed type.

## 5. Đọc `permits` theo từng nhánh

Trong ví dụ chính, `Payment` liệt kê các kiểu triển khai trực tiếp `CardPayment`, `CashPayment`, `CustomPayment`; `CashPayment` tự cho phép `ExactCashPayment`. `BrandedPayment` chỉ mở rộng `CustomPayment`, vì vậy không xuất hiện trong `permits` của `Payment`. Muốn thêm một biến thể trực tiếp, phải chủ động sửa danh sách ở đúng tầng.

Có thể bỏ `permits` nếu toàn bộ kiểu con trực tiếp của một sealed type được khai báo cùng compilation unit để trình biên dịch tự suy ra; nó không tìm kiểu ở tệp khác. Kiểu con được phép phải cùng named module với kiểu sealed, hoặc cùng package nếu thuộc unnamed module. Đồng thời, quan hệ `extends` / `implements` phải đúng; tên xuất hiện trong `permits` không tự tạo quan hệ kế thừa.

## 6. Những lỗi biên dịch thường gặp

Các đoạn dưới đây được cố ý viết sai để minh họa quy tắc; không thêm chúng vào chương trình mẫu đang chạy.

**Kế thừa một lớp `final`:**

```java
class AnotherCardPayment extends CardPayment {}
```

Lỗi: không thể kế thừa `CardPayment` vì lớp này là `final`.

**Kế thừa một sealed class nhưng không được cho phép:**

```java
class OtherCashPayment extends CashPayment {}
```

Lỗi: `CashPayment` chỉ cho phép `ExactCashPayment` làm kiểu con trực tiếp. Muốn có kiểu con trực tiếp mới, phải thay đổi khai báo sealed có thẩm quyền đối với nhánh đó.

**Triển khai sealed interface nhưng không nằm trong danh sách cho phép:**

```java
class UnknownPayment implements Payment {}
```

Lỗi: `UnknownPayment` không được liệt kê trong `permits` của `Payment`. Khai báo `implements Payment` không tự động đăng ký kiểu mới.

**Dùng `non-sealed` mà kiểu cha trực tiếp không phải sealed:**

```java
non-sealed class OrdinaryExtension {}
```

Lỗi: `non-sealed` chỉ hợp lệ với kiểu con trực tiếp của một sealed class hoặc kiểu triển khai trực tiếp của sealed interface. Nó không phải cách khai báo chung cho một lớp mở thông thường.

**Nhầm `sealed` với `final`:**

Một kiểu không thể đồng thời là `sealed` và `final`: `sealed` cho phép một tập kiểu con, còn `final` cấm mọi lớp con. Tương tự, `final` và `abstract` không thể cùng áp dụng cho một lớp vì ý nghĩa của chúng xung đột.

**Quên chính sách của sealed subclass:**

Nếu một kiểu con trực tiếp không tự đóng bằng `final`, nó phải tiếp tục kiểm soát phân cấp bằng `sealed` hoặc chủ động mở bằng `non-sealed`. Một sealed subclass còn cần danh sách kiểu con được phép riêng, trừ khi danh sách có thể được suy ra hợp lệ từ cùng compilation unit.

## 7. Các trường hợp đặc biệt cần nhớ

- **Lớp trừu tượng vẫn có thể sealed.** Ví dụ `abstract sealed class Node permits Leaf, Branch {}` có thể mô hình hóa một nhánh mà bản thân `Node` không được khởi tạo trực tiếp. Các kiểu con vẫn phải tuân theo quy tắc của sealed type.
- **Record vốn đã final.** Một record có thể là kiểu được phép triển khai sealed interface mà không cần viết thêm modifier `final`, vì record không thể được kế thừa như một lớp thông thường.
- **Interface cũng có thể sealed.** Các kiểu trực tiếp được liệt kê có thể là lớp triển khai hoặc subinterface. Một subinterface sealed có thể giới hạn nhánh tiếp theo; subinterface `non-sealed` mở nhánh cho các interface khác mở rộng.
- **`non-sealed` không xóa chính sách của tổ tiên.** Nó chỉ mở rộng từ kiểu được khai báo `non-sealed` trở xuống. Tập kiểu trực tiếp của sealed type gốc vẫn là tập được khai báo trong `permits`.
- **Sealed không làm đối tượng bất biến.** Trạng thái mutable, quyền truy cập thành viên, khả năng ghi đè phương thức và quy tắc khởi tạo vẫn tuân theo các quy tắc Java tương ứng.
- **Sealed hữu ích cho kiểm tra tính đầy đủ.** Các phiên bản Java mới hơn có thể dùng sealed hierarchy cùng pattern matching trong `switch` để kiểm tra các trường hợp đã được xử lý. Cú pháp pattern switch có phiên bản và yêu cầu ngôn ngữ riêng; không cần nó để biên dịch ví dụ Java 17 ở trên.

## 8. Cách chọn modifier

Chọn modifier theo chính sách mà API muốn công bố:

1. Dùng `final` khi kiểu đại diện cho một trường hợp cụ thể và không được mở rộng.
2. Dùng `sealed` khi nhánh có các biến thể đã biết, nhưng vẫn cần một tầng phân loại tiếp theo có kiểm soát.
3. Dùng `non-sealed` khi muốn giữ một điểm mở rộng cho bên sử dụng API hoặc cho mã của module khác, trong khi các kiểu trực tiếp của abstraction gốc vẫn được kiểm soát.

Ví dụ, một thư viện có thể cho phép các kiểu thanh toán lõi như `CardPayment` và `CashPayment`, nhưng đồng thời cung cấp `CustomPayment` như điểm mở rộng. Nhờ vậy, thư viện giữ được một ranh giới rõ ràng giữa các trường hợp lõi và các triển khai do bên sử dụng cung cấp.

Đừng chọn `non-sealed` chỉ để làm biến mất lỗi biên dịch. Hãy xác định xem việc mở rộng tùy ý có phải là một phần của hợp đồng API hay không. Việc mở nhánh ảnh hưởng đến những kiểu mà ứng dụng có thể định nghĩa về sau và đến khả năng phân tích đầy đủ các trường hợp trong mã sử dụng hierarchy.

## 9. Bảng xử lý nhanh

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Lớp không thể kế thừa một kiểu con | Kiểu cha là `final`. | Kế thừa một nhánh được thiết kế để mở rộng; chỉ đổi modifier nếu chính sách thiết kế cho phép. |
| Lớp mới không thể trực tiếp triển khai sealed interface | Lớp chưa được liệt kê trong `permits`. | Bổ sung vào danh sách được kiểm soát nếu đó là thay đổi API có chủ đích. |
| Sealed subclass báo lỗi về kiểu con | Danh sách `permits` của tầng đó thiếu hoặc không hợp lệ. | Kiểm tra quan hệ trực tiếp và khai báo danh sách cho phép của chính sealed subclass. |
| `non-sealed` bị từ chối | Kiểu cha trực tiếp không phải sealed type. | Chỉ dùng `non-sealed` ở một nhánh trực tiếp của sealed class/interface. |
| Kiểu được cho phép nhưng vẫn không biên dịch | Sai quan hệ `extends`/`implements`, khác module/package theo quy tắc, hoặc khai báo modifier không hợp lệ. | Kiểm tra đầy đủ quan hệ kế thừa, vị trí package/module và modifier của kiểu con. |

## 10. Checklist khi đọc hoặc thiết kế hierarchy

- Xác định sealed class hoặc sealed interface gốc.
- Đọc `permits` để biết các kiểu con trực tiếp được phép; nếu không có, kiểm tra xem có thể suy luận từ cùng compilation unit không.
- Với từng kiểu con trực tiếp, xác định nó là `final`, `sealed` hay `non-sealed` (hoặc một kiểu ngầm `final` như record).
- Nếu kiểu con là sealed, tiếp tục đọc danh sách `permits` của chính nó.
- Nếu kiểu con là `non-sealed`, xem đó là ranh giới mà nhánh bắt đầu mở rộng tự do.
- Kiểm tra quy tắc package/module và chạy trình biên dịch để xác nhận khai báo thực tế.
- Giữ ví dụ tối thiểu, có tên tệp đúng, lệnh biên dịch rõ ràng và kết quả đầu ra có thể kiểm tra được.

Khi đọc một sealed hierarchy, hãy theo từng cạnh trực tiếp của cây kế thừa. `final` kết thúc nhánh, `sealed` tạo một tầng được kiểm soát khác, còn `non-sealed` mở rộng nhánh đó cho các kiểu con mới.
