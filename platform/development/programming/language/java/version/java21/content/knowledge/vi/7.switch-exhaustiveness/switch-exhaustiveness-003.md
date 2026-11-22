# Bao phủ sealed hierarchy mà không che mất biến thể chưa xử lý

Với Java 21, trình biên dịch có thể kiểm tra một pattern switch đã xử lý hết các kiểu có thể xuất hiện trong một sealed hierarchy hay chưa. Nếu liệt kê rõ các biến thể được phép, khi hierarchy bổ sung một biến thể mới, switch liên quan sẽ cần được cập nhật lúc biên dịch lại. Cơ chế này giúp thay đổi mô hình dữ liệu được phát hiện sớm.

Một nhánh **default** có thể làm mất lợi ích đó vì nó nhận mọi kiểu còn lại. Khi mục tiêu là buộc mã xử lý từng biến thể của một hierarchy đóng, hãy để compiler kiểm tra type coverage và liệt kê các nhánh cần thiết. Nếu một nhánh được thiết kế để mở rộng tự do, hãy thể hiện rõ bằng một kiểu **non-sealed** và pattern tương ứng.

## 1. Sealed hierarchy tạo ra tập kiểu có thể dự đoán

Một sealed class hoặc sealed interface giới hạn các kiểu được phép kế thừa hoặc triển khai trực tiếp thông qua danh sách **permits**. Mỗi kiểu con trực tiếp phải khai báo một trong ba trạng thái:

- **final**: không cho phép kiểu khác kế thừa tiếp.
- **sealed**: tiếp tục giới hạn các kiểu con trực tiếp của nó.
- **non-sealed**: mở nhánh đó để các kiểu khác có thể kế thừa hoặc triển khai.

Record là implicitly final, nên có thể là một permitted subtype mà không cần ghi từ khóa final.

~~~java
sealed interface Payment permits CashPayment, CardPayment {
}

record CashPayment(long amount) implements Payment {
}

record CardPayment(String lastFourDigits) implements Payment {
}
~~~

Trong ví dụ, Payment chỉ có hai kiểu triển khai trực tiếp là CashPayment và CardPayment. Cả hai record đều final ngầm định, vì vậy không thể có một lớp con khác của chúng. Khi selector của switch có kiểu Payment, compiler có đủ thông tin để xác định hai nhánh kiểu này bao phủ hierarchy hiện tại.

## 2. Liệt kê từng biến thể để switch exhaustive

Switch expression phải exhaustive: mọi giá trị không-null có thể có phải thuộc ít nhất một nhãn case. Mỗi nhánh của switch expression cũng phải tạo ra một giá trị hoặc kết thúc bằng việc ném exception. Pattern switch statement trong Java 21 cũng phải exhaustive khi dùng pattern label hoặc nhãn null.

~~~java
sealed interface Payment permits CashPayment, CardPayment {
}

record CashPayment(long amount) implements Payment {
}

record CardPayment(String lastFourDigits) implements Payment {
}

class PaymentDescription {
    static String describe(Payment payment) {
        return switch (payment) {
            case CashPayment cash ->
                    "Tiền mặt: " + cash.amount();
            case CardPayment card ->
                    "Thẻ: **** " + card.lastFourDigits();
            case null -> "Không có thông tin thanh toán";
        };
    }
}
~~~

Compiler xác định CashPayment và CardPayment là toàn bộ các kiểu triển khai hợp lệ của Payment, nên không cần một nhánh default. Mỗi pattern có thể truy cập component hoặc phương thức của kiểu cụ thể mà không cần ép kiểu.

Nhãn **case null** xử lý trường hợp selector là null. Null là trường hợp riêng: pattern kiểu như **case CashPayment cash** không khớp null. Nếu không khai báo case null, switch nhận null sẽ ném NullPointerException. Nhánh null không thay thế cho bất kỳ permitted subtype nào và cũng không làm một subtype bị bỏ sót trở nên exhaustive.

Pattern switch statement cũng có thể liệt kê đầy đủ các biến thể:

~~~java
class PaymentAudit {
    static void audit(Payment payment) {
        switch (payment) {
            case CashPayment cash ->
                    System.out.println("Đã nhận tiền mặt " + cash.amount());
            case CardPayment card ->
                    System.out.println("Đã nhận thẻ " + card.lastFourDigits());
            case null ->
                    System.out.println("Không có dữ liệu thanh toán");
        }
    }
}
~~~

## 3. Sealed hierarchy lồng nhau được kiểm tra đệ quy

Một permitted subtype có thể tiếp tục là sealed interface hoặc sealed class. Khi đó, compiler có thể đi qua các nhánh sealed lồng nhau để xác định các kiểu cuối cùng cần được bao phủ.

~~~java
sealed interface Payment
        permits CashPayment, CardPayment, DigitalPayment {
}

record CashPayment(long amount) implements Payment {
}

record CardPayment(String lastFourDigits) implements Payment {
}

sealed interface DigitalPayment extends Payment
        permits WalletPayment, BankTransferPayment {
}

record WalletPayment(String accountId) implements DigitalPayment {
}

record BankTransferPayment(String reference) implements DigitalPayment {
}

class PaymentRouter {
    static String route(Payment payment) {
        return switch (payment) {
            case CashPayment cash -> "Quầy thu ngân";
            case CardPayment card -> "Cổng thanh toán thẻ";
            case WalletPayment wallet -> "Ví điện tử";
            case BankTransferPayment transfer -> "Chuyển khoản";
            case null -> "Không có giao dịch";
        };
    }
}
~~~

Payment có ba nhánh trực tiếp. Nhánh DigitalPayment lại chỉ cho phép WalletPayment và BankTransferPayment. Switch liệt kê hai kiểu cuối cùng của nhánh này cùng hai kiểu còn lại, nên toàn bộ hierarchy được bao phủ.

Không bắt buộc phải tách mọi sealed subtype thành các case con. Có thể dùng **case DigitalPayment digital** để xử lý toàn bộ nhánh đó theo cùng một chính sách. Tuy nhiên, pattern này cũng bao phủ mọi permitted subtype hiện tại và tương lai của DigitalPayment. Chỉ dùng cách gom nhánh khi các biến thể thực sự có cùng cách xử lý và không cần buộc switch cập nhật khi nhánh con thay đổi.

## 4. Vì sao default có thể che mất biến thể mới?

Nhãn **default** có type coverage cho mọi kiểu không-null còn lại. Vì vậy, khi dùng default trong switch trên sealed type, compiler không còn yêu cầu liệt kê từng permitted subtype chưa có case. Null vẫn là trường hợp riêng và cần nhãn null nếu muốn xử lý thay vì nhận NullPointerException.

Ví dụ sau vẫn biên dịch nếu hierarchy có thêm một kiểu thanh toán mới:

~~~java
sealed interface Payment permits CashPayment, CardPayment {
}

record CashPayment(long amount) implements Payment {
}

record CardPayment(String lastFourDigits) implements Payment {
}

class PaymentFallback {
    static String describeWithFallback(Payment payment) {
        return switch (payment) {
            case CashPayment cash -> "Tiền mặt";
            case null -> "Không có giao dịch";
            default -> "Phương thức khác";
        };
    }
}
~~~

Giả sử Payment được mở rộng:

~~~java
sealed interface Payment
        permits CashPayment, CardPayment, VoucherPayment {
}

record CashPayment(long amount) implements Payment {
}

record CardPayment(String lastFourDigits) implements Payment {
}

record VoucherPayment(String code) implements Payment {
}
~~~

Switch có default vẫn biên dịch và VoucherPayment đi vào nhánh "Phương thức khác". Nếu voucher cần xác minh mã, ghi nhận kế toán hoặc áp dụng chính sách riêng, thiếu sót này không được compiler chỉ ra. Default vẫn phù hợp khi selector thuộc một kiểu mở và fallback cho giá trị không nhận diện được là chính sách được chủ động lựa chọn.

Để compiler phát hiện thay đổi, bỏ default và liệt kê các biến thể cần xử lý:

~~~java
class PaymentDescription {
    static String describe(Payment payment) {
        return switch (payment) {
            case CashPayment cash -> "Tiền mặt";
            case CardPayment card -> "Thẻ";
            case VoucherPayment voucher -> "Phiếu thanh toán";
            case null -> "Không có giao dịch";
        };
    }
}
~~~

Khi hierarchy thêm một subtype khác, biên dịch lại lớp chứa switch sẽ báo switch không exhaustive cho đến khi có case phù hợp. Đây là tín hiệu hữu ích trong code xử lý nghiệp vụ, nơi một biến thể mới thường đòi hỏi logic riêng.

## 5. Phân biệt sealed branch và non-sealed branch

Một sealed hierarchy có thể chứa nhánh non-sealed. Nhánh đó là điểm mở rộng có chủ đích: compiler không thể liệt kê mọi lớp con trong tương lai, nhưng có thể yêu cầu một pattern bao phủ kiểu non-sealed đã được khai báo.

~~~java
sealed interface Payment
        permits CashPayment, CardPayment, ExternalPayment {
}

record CashPayment(long amount) implements Payment {
}

record CardPayment(String lastFourDigits) implements Payment {
}

non-sealed interface ExternalPayment extends Payment {
}

record PartnerWallet(String partnerId) implements ExternalPayment {
}

class PaymentRouter {
    static String route(Payment payment) {
        return switch (payment) {
            case CashPayment cash -> "Quầy thu ngân";
            case CardPayment card -> "Cổng thanh toán thẻ";
            case ExternalPayment external -> "Bộ xử lý đối tác";
            case null -> "Không có giao dịch";
        };
    }
}
~~~

**case ExternalPayment external** bao phủ PartnerWallet và mọi implementation khác của ExternalPayment. Đây là một nhánh mở được đặt tên rõ trong mô hình. Nếu thêm một permitted subtype trực tiếp khác vào Payment, compiler vẫn yêu cầu switch có case mới; nếu thêm một implementation của ExternalPayment, case hiện tại đã bao phủ nó.

Điều này hữu ích khi ứng dụng có một số biến thể nội bộ cần xử lý riêng, đồng thời có một điểm mở rộng cho plugin hoặc adapter bên ngoài. Nếu cần xử lý riêng từng implementation đối tác, hãy giữ nhánh đó sealed và liệt kê các subtype cụ thể.

## 6. Guarded pattern không tự bao phủ toàn bộ kiểu

Một pattern có **when** chỉ khớp khi cả type pattern và điều kiện guard đều đúng. Vì điều kiện có thể sai, guarded pattern không chứng minh rằng toàn bộ subtype đã được xử lý.

Ví dụ chỉ có nhánh tiền mặt giá trị lớn sẽ không bao phủ mọi CashPayment:

Các ví dụ dưới đây dùng lại Payment, CashPayment và CardPayment đã khai báo ở phần 2.

~~~java
class GuardedPaymentDescription {
    static String describe(Payment payment) {
        return switch (payment) {
            case CashPayment cash when cash.amount() >= 100_000 ->
                    "Giao dịch tiền mặt giá trị lớn";
            case CardPayment card ->
                    "Thanh toán bằng thẻ";
            case null -> "Không có giao dịch";
        };
    }
}
~~~

Switch trên không exhaustive vì CashPayment có amount nhỏ hơn 100.000 không khớp case guarded. Hãy thêm một pattern không guard cho phần còn lại:

~~~java
class GuardedPaymentDescription {
    static String describe(Payment payment) {
        return switch (payment) {
            case CashPayment cash when cash.amount() >= 100_000 ->
                    "Giao dịch tiền mặt giá trị lớn";
            case CashPayment cash ->
                    "Giao dịch tiền mặt thông thường";
            case CardPayment card ->
                    "Thanh toán bằng thẻ";
            case null -> "Không có giao dịch";
        };
    }
}
~~~

Case không guard cho CashPayment bao phủ các giá trị không thỏa guard trước đó. Tương tự, nếu dùng nhiều guard cho cùng một permitted subtype, hãy có một nhánh không guard cuối cùng hoặc một cách bao phủ toàn bộ phần còn lại.

## 7. Tránh pattern rộng che khuất pattern cụ thể

Pattern switch kiểm tra thứ tự nhãn và báo lỗi nếu một nhãn không thể được khớp vì nhãn trước đã bao phủ nó. Ví dụ, pattern cho kiểu cha Payment đặt trước CashPayment sẽ làm case CashPayment phía sau bị dominated:

~~~java
sealed interface Payment permits CashPayment, CardPayment {
}

record CashPayment(long amount) implements Payment {
}

record CardPayment(String lastFourDigits) implements Payment {
}

class InvalidPaymentOrder {
    // Không hợp lệ: Payment bao phủ mọi CashPayment.
    static String invalidOrder(Payment payment) {
        return switch (payment) {
            case Payment any -> "Một loại thanh toán";
            case CashPayment cash -> "Tiền mặt";
        };
    }
}
~~~

Trong hierarchy đóng, hãy đặt các case cụ thể theo từng permitted subtype và chỉ dùng pattern cho kiểu cha khi chủ đích là gom toàn bộ nhánh. Không dùng một pattern rộng để vô tình làm mất cơ hội phát hiện biến thể cần xử lý riêng.

## 8. Generic sealed hierarchy và type coverage

Compiler xét cả type argument của kiểu selector. Vì vậy, một permitted subtype có thể không phù hợp với kiểu tham số hóa cụ thể đang được switch xử lý và không cần một case cho subtype đó.

~~~java
sealed interface Message<T> permits TextMessage, ValueMessage {
}

final class TextMessage implements Message<String> {
}

final class ValueMessage<T> implements Message<T> {
}

class MessageHandler {
    static int handle(Message<Integer> message) {
        return switch (message) {
            case ValueMessage<Integer> value -> 1;
        };
    }
}
~~~

TextMessage chỉ triển khai Message<String>, nên không thể là giá trị của selector có kiểu Message<Integer>. ValueMessage<Integer> là nhánh có thể xuất hiện và đủ để bao phủ kiểu selector này. Ví dụ cho thấy compiler không chỉ đếm tên trong permits; nó còn xét khả năng tương thích generic.

Không nên tự bỏ một case chỉ dựa trên suy luận nghiệp vụ. Hãy để compiler xác nhận type coverage từ khai báo sealed và generic thực tế. Khi thay đổi type parameter hoặc quan hệ implements, tập kiểu có thể xuất hiện trong switch cũng thay đổi.

## 9. Thay đổi sealed hierarchy và MatchException

Tính exhaustive được xác định lúc biên dịch. Nếu sealed hierarchy được thay đổi và biên dịch lại nhưng lớp chứa switch exhaustive không được biên dịch lại, chương trình có thể nhận một subtype mới mà bytecode switch cũ chưa có nhánh xử lý.

Trong Java 21, nếu một permitted subtype mới xuất hiện lúc chạy nhưng không có trong tập kiểu mà switch đã bao phủ lúc biên dịch, pattern switch có thể ném **java.lang.MatchException**. Đây là tình huống có thể xuất hiện khi các phần của hierarchy được biên dịch riêng ở những thời điểm khác nhau. Selector null không được xử lý bằng case null vẫn ném NullPointerException; đó là trường hợp riêng.

Quy trình an toàn khi thay đổi danh sách permitted subtype:

1. Cập nhật sealed root và khai báo subtype mới.
2. Tìm các switch xử lý kiểu sealed root hoặc các sealed subtype liên quan.
3. Thêm logic cho biến thể mới ở các switch cần xử lý riêng.
4. Biên dịch lại các module chứa hierarchy và switch phụ thuộc trong cùng một lần build nhất quán.
5. Chạy test cho subtype mới và các nhánh cũ.

Không thêm default chỉ để làm build xanh khi hierarchy thay đổi. Hãy xác định biến thể mới có cùng chính sách với một nhánh hiện có hay cần logic riêng, sau đó thể hiện quyết định đó bằng case cụ thể hoặc pattern cho một nhánh non-sealed có chủ đích.

## 10. Checklist thiết kế switch cho sealed hierarchy

- [ ] Sealed root khai báo rõ các permitted subtype.
- [ ] Mỗi subtype trực tiếp được khai báo **final**, **sealed** hoặc **non-sealed**.
- [ ] Các nhánh sealed lồng nhau được bao phủ tới mức cần xử lý nghiệp vụ.
- [ ] Không dùng **default** nếu muốn compiler phát hiện permitted subtype mới chưa có xử lý.
- [ ] Chỉ gom một sealed branch vào pattern kiểu cha khi mọi biến thể trong nhánh thực sự có chung cách xử lý.
- [ ] Với nhánh non-sealed, dùng pattern cho kiểu non-sealed đó để biểu thị điểm mở rộng có chủ đích.
- [ ] Guarded pattern có nhánh không guard bao phủ các giá trị còn lại.
- [ ] Xử lý null riêng nếu selector có thể null.
- [ ] Tránh pattern kiểu cha đặt trước pattern kiểu con gây dominance.
- [ ] Biên dịch lại các switch phụ thuộc khi danh sách permitted subtype thay đổi.

## Tài liệu tham khảo

- [Java SE 21: Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java SE 21: Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html)
- [Java SE 21: Sealed Classes](https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html)
- [Java SE 21 API: MatchException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html)
- [JEP 441: Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 409: Sealed Classes](https://openjdk.org/jeps/409)
