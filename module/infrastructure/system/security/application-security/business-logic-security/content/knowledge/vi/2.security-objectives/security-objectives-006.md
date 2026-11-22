# Correctness of financial outcomes — Tính đúng đắn của kết quả tài chính

## 1. Mục tiêu bảo mật là kết quả tiền tệ đúng

Trong chương **Security Objectives** của module **Business Logic Security** (`SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`), tính đúng đắn của kết quả tài chính là mục tiêu bảo vệ những gì hệ thống thực sự thu, chi, hoàn, ghi nhận hoặc cam kết về tiền.

Một giao dịch trả HTTP thành công chưa chứng minh mục tiêu này đã đạt. Ứng dụng vẫn có thể:

- Thu đúng người nhưng sai số tiền.
- Thu đúng số tiền nhưng bằng sai tiền tệ.
- Thu hai lần do retry hoặc xử lý sự kiện lặp.
- Hoàn nhiều hơn phần tiền được phép hoàn.
- Gửi tiền tới người nhận bị thay đổi sau khi phê duyệt.
- Hiển thị đã thanh toán khi mới nhận được thông báo từ client.
- Ghi sổ cân bằng nhưng gắn giao dịch với sai đơn hàng hoặc tenant.

Các lỗi trên có thể xảy ra mà không cần SQL injection, đánh cắp mật khẩu hay khai thác bộ nhớ. Người lạm dụng chỉ cần sửa một tham số, thay thứ tự gọi API hoặc gửi các yêu cầu cạnh tranh để làm sai kết quả nghiệp vụ.

**Bảo đảm cần hướng tới:** với mỗi nghiệp vụ tiền tệ được chấp nhận, số tiền, tiền tệ, đối tượng, thời điểm hiệu lực và số lần tác động phải phù hợp với chính sách và bằng chứng mà máy chủ tin cậy; trạng thái nội bộ phải giải thích được bằng các bản ghi có thể đối soát.

Bài này tập trung vào việc xác định mục tiêu, phát biểu bất biến và lựa chọn bằng chứng cần có. Các cơ chế như state machine, transaction, quyền theo đối tượng và idempotency là phương tiện để thực thi mục tiêu đó.

## 2. “Đúng” gồm nhiều chiều, không chỉ một con số

| Chiều của kết quả | Câu hỏi cần trả lời | Ví dụ vi phạm |
| --- | --- | --- |
| Số tiền | Giá trị được thu hoặc hoàn có đúng chính sách không? | Client sửa tổng từ 930.000 xuống 93.000 |
| Tiền tệ | Số tiền có được diễn giải trong đúng tiền tệ và đơn vị không? | Giá trị theo đơn vị nhỏ nhất bị hiểu thành đơn vị chính |
| Đối tượng | Tiền và bản ghi thuộc đúng khách hàng, người nhận, đơn và tenant không? | Callback của đơn A làm đơn B thành paid |
| Số lần | Cùng một nghĩa vụ có bị tạo tác động nhiều lần không? | Retry tạo hai lần thu tiền |
| Thứ tự và trạng thái | Tác động có diễn ra sau các bước bắt buộc không? | Chi tiền trước khi phê duyệt hoặc sau khi lệnh đã bị hủy |
| Hiệu lực | Báo giá, hạn mức hoặc ủy quyền có còn hiệu lực không? | Dùng lại báo giá cũ ngoài điều kiện cho phép |
| Tính nhất quán | Các bản ghi và hệ thống liên quan có phản ánh cùng một sự thật không? | Cổng thanh toán đã thu nhưng ứng dụng coi là chưa thu |
| Khả năng giải thích | Có tái dựng được cách tính và bằng chứng tạo tác động không? | Tổng cuối đúng ngẫu nhiên nhưng không biết giảm giá được áp dụng từ đâu |

Một hệ thống có thể đúng ở chiều này nhưng sai ở chiều khác. Chuyển chính xác 1.000.000 đơn vị tới sai tài khoản vẫn là một kết quả sai.

Vì vậy, phát biểu “thanh toán phải chính xác” cần được phân rã thành các cam kết cụ thể, có phạm vi và có cách kiểm chứng.

## 3. Phân biệt các khái niệm dễ bị đánh đồng

### 3.1. Yêu cầu được tiếp nhận khác với tiền đã được thu

Một yêu cầu tạo thanh toán có thể chỉ tạo một **ý định thanh toán**. Tùy hệ thống tích hợp, quá trình còn có thể gồm ủy quyền, thu tiền và quyết toán.

Không nên gộp tất cả thành một cờ `paid = true` mà không định nghĩa nó có nghĩa gì.

Ví dụ:

```text
PAYMENT_CREATED: đã tạo ý định
PAYMENT_PENDING: đang chờ kết quả
CAPTURE_CONFIRMED: có bằng chứng đã thu theo hợp đồng tích hợp
PAYMENT_UNKNOWN: chưa xác định được kết quả sau lỗi liên lạc
PAYMENT_FAILED: có kết quả thất bại đáng tin cậy
```

Tên trạng thái thực tế có thể khác. Điều quan trọng là mỗi tên phải đi kèm ý nghĩa và bằng chứng rõ ràng. Có bằng chứng thu tiền cũng không mặc nhiên có nghĩa khoản đó đã được quyết toán hoặc không thể bị điều chỉnh về sau.

### 3.2. Giá trị hiển thị khác với giá trị có thẩm quyền

Frontend có thể hiển thị tổng tạm tính để hỗ trợ người dùng. Máy chủ phải tự tính hoặc xác thực báo giá từ nguồn có thẩm quyền trước khi tạo nghĩa vụ tiền tệ.

Các trường như `unitPrice`, `discount`, `shippingFee`, `currency` và `grandTotal` trong request không tự trở thành sự thật chỉ vì request có chữ ký phiên đăng nhập hợp lệ.

### 3.3. Sổ cái cân bằng khác với giao dịch đúng nghiệp vụ

Một giao dịch có các bút toán cân bằng vẫn có thể:

- Dùng sai người nhận.
- Gắn sai đơn hàng.
- Sử dụng mức phí ngoài chính sách.
- Được ghi hai lần.
- Được tạo bởi actor không có quyền.

Cân bằng sổ là một bất biến cần thiết trong mô hình hạch toán phù hợp, nhưng không thay thế kiểm tra thẩm quyền và ý nghĩa nghiệp vụ.

## 4. Ví dụ xuyên suốt: đơn hàng và hoàn tiền một phần

### 4.1. Chính sách minh họa

Giả sử một đơn hàng dùng VND, biểu diễn số tiền bằng đồng nguyên, có:

| Thành phần | Phép tính | Giá trị |
| --- | --- | ---: |
| Mặt hàng A | 2 × 300.000 | 600.000 |
| Mặt hàng B | 1 × 400.000 | 400.000 |
| Tổng hàng | 600.000 + 400.000 | 1.000.000 |
| Giảm giá toàn đơn | Theo chương trình được máy chủ chấp nhận | 100.000 |
| Phí giao hàng | Theo báo giá đã được chấp nhận | 30.000 |
| Phải thanh toán | 1.000.000 − 100.000 + 30.000 | 930.000 |

Giá được chốt tại một phiên bản báo giá do máy chủ quản lý. Thay đổi giá danh mục sau đó không tự thay giá của đơn đã chốt.

Trong ví dụ này:

- Mỗi đơn chỉ có một lần thu thành công.
- Cho phép nhiều lần hoàn một phần.
- Phí giao hàng 30.000 không được hoàn theo chính sách đã thỏa thuận của ví dụ.
- Giảm giá toàn đơn được phân bổ theo tỷ lệ giá trị hàng: A nhận 60.000, B nhận 40.000.
- Luồng tranh chấp, đảo giao dịch và điều chỉnh sau đó nằm ngoài mô hình số dư đơn giản này; hệ thống có các luồng đó phải mở rộng mô hình tương ứng.

Phần tiền hàng sau giảm giá là 900.000. Nếu hoàn toàn bộ hai sản phẩm A, giá trị hoàn của hàng A là 540.000 theo phân bổ đã lưu, thay vì 600.000 theo giá trước giảm.

Đây là lý do mục tiêu tài chính cần bao gồm cả cách phân bổ, không chỉ tổng ban đầu.

### 4.2. Những thay đổi nào phải làm mất hiệu lực phê duyệt?

Nếu quy trình có phê duyệt, bằng chứng cần gắn với nội dung có ảnh hưởng đến tiền:

```text
orderId
contentRevision
line items và số lượng
giá đã chốt
giảm giá và phân bổ
phí
tiền tệ
người nhận hoặc tài khoản đích, nếu liên quan
tổng phải thanh toán
```

Sau khi đổi một trong những dữ liệu thuộc phạm vi quyết định, hệ thống cần xử lý theo chính sách: tính lại, tăng phiên bản, vô hiệu hóa quyết định cũ hoặc yêu cầu phê duyệt lại.

Giữ nguyên `approved = true` khi thay tài khoản nhận tiền làm mất ý nghĩa của phê duyệt, dù số tiền không đổi.

## 5. Chuyển mục tiêu thành các bất biến kiểm chứng được

### 5.1. Bất biến về tính tiền

```text
subtotal = Σ(quantity_i × acceptedUnitPrice_i)

payable = subtotal - acceptedDiscount + acceptedFees

payable >= 0

Mọi thành phần thuộc cùng một phép tổng hợp đều phải cùng tiền tệ,
hoặc được quy đổi bằng một quy trình đã xác định trước khi cộng.
```

“Giá được chấp nhận” cần được xác định bằng phiên bản báo giá hoặc snapshot đáng tin cậy, không phải một con số client tự chọn.

### 5.2. Bất biến về việc thu tiền

Trong mô hình một lần thu thành công cho mỗi đơn của bài:

```text
Một kết quả thu được gắn với đúng paymentIntent và order.

capturedCurrency = orderCurrency

capturedAmount = acceptedPayable

Số lần thu thành công được ghi nhận cho cùng nghĩa vụ ≤ 1.
```

Nếu hệ thống cho phép chia nhiều lần thu hoặc nhiều phương thức thanh toán, phải thay bất biến bằng quan hệ tổng phù hợp. Không được giữ giả định một lần thu trong code trong khi nghiệp vụ đã thay đổi.

### 5.3. Bất biến về hoàn tiền

Đặt:

- `capturedConfirmed`: số tiền đã thu có bằng chứng xác nhận.
- `refundableLimit`: tổng mức hoàn tối đa theo chính sách, đã được xác định từ giao dịch gốc.
- `refundedConfirmed`: tổng các lần hoàn thành công.
- `refundReserved`: tổng tiền đang được giữ chỗ cho các lệnh hoàn chưa có kết quả cuối.

Trong phạm vi mô hình đã nêu:

```text
0 <= refundableLimit <= capturedConfirmed

refundedConfirmed >= 0
refundReserved >= 0

refundedConfirmed + refundReserved <= refundableLimit
```

Với đơn ví dụ, `capturedConfirmed = 930.000` và `refundableLimit = 900.000`.

Cần cộng cả phần đang chờ xử lý. Nếu chỉ trừ các lần hoàn đã thành công, hai yêu cầu đồng thời có thể cùng được gửi ra ngoài trước khi kết quả đầu tiên quay về.

### 5.4. Bất biến về thẩm quyền và đối tượng

```text
Mọi lệnh thu, hoàn hoặc chi được chấp nhận
phải được thực hiện trong đúng tenant,
trên đúng đối tượng,
bởi actor có quyền cho hành động đó,
với số tiền nằm trong phạm vi được phép.
```

Một nhân viên được hoàn tiền cho đơn của chi nhánh A không tự động được hoàn cho đơn chi nhánh B. Một callback hợp lệ về chữ ký cũng không tự động được áp dụng cho mọi orderId đi kèm nếu việc ánh xạ không được kiểm tra.

### 5.5. Ghi rõ ranh giới của từng bảo đảm

Bất biến cục bộ có thể được duy trì sau mỗi transaction commit. Sự khớp nhau giữa cơ sở dữ liệu nội bộ và dịch vụ ngoài thường cần quy trình xác nhận hoặc đối soát.

Không nên phát biểu rằng hai hệ thống độc lập “luôn đồng bộ tức thời” khi cơ chế thực tế sử dụng message và retry. Cam kết phù hợp hơn có thể là:

> Không tự kết luận thất bại khi kết quả chưa xác định; mọi tác động đã xác nhận được ghi nhận không trùng và các chênh lệch được đưa vào quy trình đối soát có theo dõi.

## 6. Biểu diễn và tính tiền mà không làm mất thông tin

### 6.1. Luôn mang theo tiền tệ và đơn vị

Con số `930000` tự nó không đủ nghĩa. Nó có thể là đồng, xu hoặc một đơn vị khác tùy hợp đồng.

Một kiểu tiền tối thiểu nên ràng buộc:

```text
Money = (currency, amountInDefinedUnit)
```

Không mặc định mọi tiền tệ đều có hai chữ số thập phân. Quy tắc về số chữ số và đơn vị tích hợp cần đến từ metadata và hợp đồng đáng tin cậy của hệ thống.

Hai cách biểu diễn thường dùng:

- Số nguyên theo đơn vị nhỏ nhất đã quy ước, có kiểm tra tràn số.
- Số thập phân chính xác với scale và quy tắc làm tròn được xác định.

Tránh dùng `float` hoặc `double` làm nguồn sự thật cho giá trị tiền cần chính xác theo đơn vị quy định. Vấn đề không chỉ ở hiển thị; sai khác nhỏ có thể ảnh hưởng kiểm tra bằng nhau, phân bổ hoặc mức hoàn còn lại.

### 6.2. Ví dụ Java với số nguyên có kiểm tra tràn

Ví dụ sau tính giá trị đơn trong cùng một tiền tệ. `Money` cho phép giá trị âm để hỗ trợ phép toán trung gian; quy tắc không âm được kiểm tra ở nơi sử dụng nghiệp vụ.

```java
import java.util.Currency;
import java.util.List;
import java.util.Objects;

record Money(Currency currency, long minor) {
    Money {
        Objects.requireNonNull(currency);
    }

    Money add(Money other) {
        requireSameCurrency(other);
        return new Money(currency, Math.addExact(minor, other.minor));
    }

    Money subtract(Money other) {
        requireSameCurrency(other);
        return new Money(currency, Math.subtractExact(minor, other.minor));
    }

    Money multiply(long quantity) {
        return new Money(currency, Math.multiplyExact(minor, quantity));
    }

    private void requireSameCurrency(Money other) {
        Objects.requireNonNull(other);
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("CURRENCY_MISMATCH");
        }
    }
}

record PricedLine(long quantity, Money acceptedUnitPrice) {
    PricedLine {
        Objects.requireNonNull(acceptedUnitPrice);
        if (quantity <= 0 || acceptedUnitPrice.minor() < 0) {
            throw new IllegalArgumentException("INVALID_LINE");
        }
    }
}

final class OrderPricing {
    static Money payable(
            List<PricedLine> lines,
            Money acceptedDiscount,
            Money acceptedFee) {
        Objects.requireNonNull(lines);
        Objects.requireNonNull(acceptedDiscount);
        Objects.requireNonNull(acceptedFee);

        if (lines.isEmpty()
                || acceptedDiscount.minor() < 0
                || acceptedFee.minor() < 0) {
            throw new IllegalArgumentException("INVALID_PRICING_INPUT");
        }

        Money subtotal = new Money(acceptedDiscount.currency(), 0);
        for (PricedLine line : lines) {
            subtotal = subtotal.add(
                    line.acceptedUnitPrice().multiply(line.quantity()));
        }

        Money discounted = subtotal.subtract(acceptedDiscount);
        if (discounted.minor() < 0) {
            throw new IllegalArgumentException("DISCOUNT_EXCEEDS_SUBTOTAL");
        }

        return discounted.add(acceptedFee);
    }
}
```

Các phép `Math.*Exact` báo lỗi khi kết quả vượt miền `long`, thay vì âm thầm cho một số sai. Tầng ứng dụng cần từ chối thao tác và rollback phần ghi liên quan khi lỗi xảy ra.

Mã này chỉ bảo vệ phép tính và tiền tệ. Nó không chứng minh giá, phí và giảm giá có thẩm quyền. Các giá trị `accepted...` phải được tạo từ báo giá và chính sách ở máy chủ, không phải đổi tên các trường lấy nguyên từ request.

Nếu nhận dữ liệu thập phân, phải kiểm tra scale trước khi đổi sang đơn vị nguyên. Không được cắt bỏ phần lẻ hoặc làm tròn ngầm chỉ để request đi qua.

### 6.3. Làm tròn và phân bổ là một phần của chính sách

Giả sử cần phân bổ khoản giảm 100 đơn vị nguyên cho ba dòng có trọng số bằng nhau. Không thể cho mỗi dòng đúng một phần ba đơn vị cuối cùng trong mô hình số nguyên.

Một cách xác định là:

```text
Phần nguyên ban đầu: 33, 33, 33
Phần còn lại: 1
Phân bổ phần còn lại theo thứ tự ổn định: 34, 33, 33

Tổng phân bổ = 100
```

Cần xác định:

- Làm tròn ở cấp dòng hay cấp đơn.
- Quy tắc làm tròn.
- Cách phân phối phần dư.
- Thứ tự ổn định khi các dòng có cùng phần dư.
- Cách giữ nguyên phân bổ khi hoàn tiền một phần.

Với tỷ lệ khác nhau, có thể phân bổ phần nguyên rồi phân phối phần dư theo phần lẻ lớn nhất và một quy tắc hòa ổn định. Phép nhân hoặc chia dùng để tính tỷ lệ cũng cần tránh tràn và sai số.

Không nên tính lại tiền hoàn từ giá danh mục hoặc chương trình giảm giá hiện hành. Cần dùng giao dịch gốc, phân bổ đã chấp nhận và chính sách hoàn tương ứng.

### 6.4. Đổi tiền cần một giao dịch có ngữ cảnh

Không được cộng trực tiếp 100 USD với 100 VND. Nếu có quy đổi, bản ghi cần thể hiện ít nhất tiền tệ nguồn và đích, tỷ giá hoặc phiên bản báo giá, thời điểm hiệu lực, quy tắc làm tròn và phí liên quan.

Lưu cả dữ liệu gốc lẫn kết quả được chấp nhận để tái dựng. Một con số đã quy đổi nhưng không có ngữ cảnh khiến đối soát và xử lý hoàn trở nên mơ hồ.

## 7. Bảo vệ nguồn sự thật và quyết định phê duyệt

### 7.1. Máy chủ quyết định dữ liệu có thẩm quyền

Một request checkout có thể chỉ cần gửi:

```text
productId
quantity
couponCode
quoteId hoặc expectedPricingRevision
định danh phương thức thanh toán được phép
idempotencyKey
```

Máy chủ tải dữ liệu phù hợp, kiểm tra báo giá và tính lại tổng. Nếu client gửi tổng dự kiến để phát hiện thay đổi giá, trường đó chỉ là kỳ vọng cần so sánh, không phải lệnh đặt số tiền thực thu.

Giá thương lượng hoặc báo giá đã ký cũng phải được kiểm tra scope, đối tượng, tiền tệ, thời hạn và khả năng sử dụng lại theo chính sách. Một chữ ký hợp lệ không mặc nhiên cho phép dùng báo giá của khách hàng khác.

### 7.2. Kiểm tra quyền trên đúng nghiệp vụ tiền tệ

Quyền “xem đơn” không đồng nghĩa “hoàn tiền”. Quyền “hoàn tối đa 100.000” không đồng nghĩa “hoàn toàn bộ”.

Một quyết định có thể cần:

```text
canRefund(actor, order, refundRequest)
=
    đúng tenant
    ∧ có quyền hoàn trên đơn cụ thể
    ∧ đủ hạn mức
    ∧ đúng trạng thái cho phép
    ∧ lý do và phần hàng hoàn đáp ứng chính sách
    ∧ không vi phạm tách người tạo và người duyệt nếu áp dụng
```

Khi phê duyệt dựa trên một mức tiền, việc sửa mức tiền sau duyệt phải làm mất hiệu lực quyết định cũ. Nếu phê duyệt xét cả người nhận, thay người nhận cũng phải được xử lý tương tự.

### 7.3. Ràng buộc số tiền với ý định thanh toán

Không chỉ so sánh tổng số. Bản ghi ý định cần liên kết đúng:

```text
tenantId
orderId
pricingRevision
amount
currency
người trả hoặc phạm vi thanh toán theo chính sách
providerAccount hoặc cấu hình tích hợp tương ứng
providerReference
```

Nhờ đó, một kết quả hợp lệ từ nhà cung cấp không bị áp dụng nhầm sang đơn khác hoặc sang cấu hình tài khoản khác.

Khi số tiền đơn thay đổi, cần một quy trình rõ để vô hiệu hóa, thay thế hoặc đối soát ý định cũ. Không được chỉ sửa tổng đơn trong cơ sở dữ liệu rồi tiếp tục nhận mọi kết quả trả về từ ý định ban đầu như thể chúng vẫn khớp.

## 8. Duy trì hạn mức hoàn trước thao tác đồng thời

### 8.1. Vì sao kiểm tra rồi gửi lệnh chưa đủ?

Giả sử chưa hoàn đồng nào và hạn mức còn 900.000:

| Thời điểm | Request A | Request B |
| --- | --- | --- |
| 1 | Đọc còn 900.000 | |
| 2 | | Đọc còn 900.000 |
| 3 | Kiểm tra hoàn 500.000, đạt | |
| 4 | | Kiểm tra hoàn 500.000, đạt |
| 5 | Gửi lệnh hoàn | Gửi lệnh hoàn |

Hai lệnh cộng lại thành 1.000.000. Mỗi request riêng lẻ đúng với dữ liệu nó đọc, nhưng kết quả chung sai.

### 8.2. Giữ chỗ trong transaction cục bộ

Cần biến “còn đủ để hoàn” thành một quyết định có chiếm dụng hạn mức.

Một mẫu cập nhật có điều kiện:

```sql
UPDATE payment_position
SET refund_reserved_minor = refund_reserved_minor + :amount_minor,
    row_version = row_version + 1
WHERE tenant_id = :tenant_id
  AND payment_id = :payment_id
  AND currency = :currency
  AND capture_status = 'CAPTURE_CONFIRMED'
  AND :amount_minor > 0
  AND :amount_minor <= (
      refundable_limit_minor
      - refunded_confirmed_minor
      - refund_reserved_minor
  );
```

Ứng dụng chỉ tạo lệnh hoàn mới khi cập nhật đúng một dòng. Việc giữ chỗ, tạo bản ghi refund và ghi outbox cần nằm trong cùng transaction nếu chúng là các ghi cục bộ của cùng quyết định.

Mẫu này giả định các cột không null, không âm, giá trị nằm trong miền biểu diễn và mọi đường cập nhật số dư tuân theo cùng cơ chế nhất quán. Constraint có thể bảo vệ thêm:

```text
refundableLimit <= capturedConfirmed
refundReserved <= refundableLimit
refundedConfirmed <= refundableLimit - refundReserved
```

Cơ chế cạnh tranh cụ thể cần phù hợp với cơ sở dữ liệu và mức cô lập đang dùng. Khóa bản ghi vị thế thanh toán rồi đọc, kiểm tra, cập nhật trong cùng transaction cũng là một cách triển khai.

Giới hạn tổng chưa thay thế kiểm tra chi tiết: số lượng hàng đã hoàn, giá trị từng dòng và quyền của actor vẫn phải đúng. Nếu các giới hạn đó nằm ở bản ghi khác, chúng cũng cần được bảo vệ nhất quán.

### 8.3. Kết thúc hoặc giữ nguyên khoản giữ chỗ

Giả sử một refund đã giữ 500.000:

| Kết quả được xác nhận | Thay đổi cục bộ |
| --- | --- |
| Hoàn thành công | Giảm reserved 500.000, tăng refundedConfirmed 500.000 trong cùng transaction |
| Thất bại cuối cùng, chắc chắn không có tác động | Giải phóng reserved theo trạng thái hợp lệ |
| Timeout hoặc kết quả chưa xác định | Giữ trạng thái chờ xác minh; không giải phóng chỉ vì chưa nhận phản hồi |

Nếu giải phóng ngay khi timeout nhưng bên ngoài đã hoàn thành công, một lệnh mới có thể sử dụng lại hạn mức và làm vượt trần.

Việc chuyển từ pending sang succeeded phải có điều kiện trạng thái hoặc version, để hai thông báo thành công không chuyển khoản giữ chỗ thành tiền đã hoàn hai lần.

## 9. Ngăn tác động trùng bằng nhiều lớp bảo vệ

### 9.1. Định danh command và định danh nghiệp vụ

Khóa idempotency nhận diện các lần gửi lại của cùng command logic. Định danh nghiệp vụ xác định nghĩa vụ hoặc tác động cần bảo vệ.

Ví dụ:

| Định danh | Vai trò |
| --- | --- |
| `orderId` | Đơn hàng |
| `paymentIntentId` | Ý định thanh toán cho một nội dung và mức tiền xác định |
| `refundId` | Một yêu cầu hoàn cụ thể |
| `idempotencyKey` | Liên kết các lần gửi lại của cùng command |
| `providerReference` | Liên kết với tác động tại nhà cung cấp |
| `eventId` | Nhận diện sự kiện nhận hoặc phát, theo scope đã định nghĩa |

Không nên dùng một khóa ngẫu nhiên từ client làm bảo vệ duy nhất. Người lạm dụng có thể đổi khóa. Mô hình một lần thu còn cần tính duy nhất theo nghĩa vụ; mô hình nhiều lần hoàn cần hạn mức tổng, giới hạn theo hàng và trạng thái từng refund.

### 9.2. Xử lý idempotency nhất quán

Một luồng cục bộ có thể:

1. Xác thực actor, tenant và phạm vi thao tác.
2. Giành quyền xử lý khóa bằng cơ chế có tính duy nhất.
3. So sánh dấu vân tay command, gồm đối tượng, số tiền hoặc nội dung nguồn dùng để tính tiền, tiền tệ và các tham số quan trọng.
4. Nếu đã có kết quả commit của cùng command, kiểm tra quyền xem kết quả và trả lại theo hợp đồng.
5. Nếu là command mới, đánh giá guard trên dữ liệu được bảo vệ, thực hiện tác động và lưu kết quả nhất quán.

Hai request cùng đến cần được phối hợp; chỉ đọc “chưa tồn tại khóa” rồi thực hiện không đủ. Phạm vi khóa và thời gian lưu phải rõ ràng.

Khi retry gọi nhà cung cấp, dùng lại định danh ổn định phù hợp với hợp đồng idempotency của họ. Không tạo một khóa bên ngoài mới cho mỗi lần thử mạng của cùng một refund.

### 9.3. Không hứa “đúng một lần” chỉ nhờ một thành phần

- Idempotency tại API không tự khử trùng consumer.
- Outbox không tự ngăn tác động lặp tại nhà cung cấp.
- Khóa duy nhất cho event không ngăn hai event khác nhau cùng mô tả một giao dịch.
- Một trạng thái `SUCCEEDED` không đủ nếu handler vẫn ghi thêm bút toán mỗi lần nhận thông báo.

Cần nối các lớp theo cùng định danh nghiệp vụ. Ví dụ, consumer chỉ được chuyển refund từ pending sang succeeded một lần; việc ghi nhận sự kiện đã xử lý và tác động cục bộ phải nhất quán.

Nếu hệ thống xử lý lại cùng dữ liệu sau phục hồi hoặc đối soát, đường xử lý đó cũng phải giữ những ràng buộc tương đương.

## 10. Xác nhận sự thật từ hệ thống bên ngoài

### 10.1. Không dùng kết quả do client tự khai làm bằng chứng

Trình duyệt quay về trang `payment-success` hoặc gửi `status = SUCCESS` chỉ cho biết một luồng phía client đã diễn ra. Nó không đủ để xác nhận tiền đã được thu.

Bằng chứng cần đến từ kênh máy chủ tin cậy, chẳng hạn thông báo đã được xác thực hoặc truy vấn trạng thái tới hệ thống tích hợp theo hợp đồng.

### 10.2. Kiểm tra thông điệp theo nhiều chiều

Một thông điệp hợp lệ cần được kiểm tra phù hợp với giao thức:

- Nguồn gốc và tính toàn vẹn, ví dụ chữ ký và thông tin xác thực cần thiết.
- Scope tài khoản tích hợp và môi trường.
- Định danh giao dịch và ánh xạ tới đối tượng nội bộ.
- Loại tác động: tạo ý định, ủy quyền, thu, hoàn hoặc điều chỉnh.
- Số tiền và tiền tệ so với bản ghi có thẩm quyền.
- Khả năng lặp, thứ tự và trạng thái hiện hành.

Chữ ký hợp lệ chứng minh điều mà cơ chế xác thực được thiết kế để chứng minh. Nó không thay thế việc đối chiếu amount, currency và đối tượng.

Ví dụ một thông báo xác thực được về khoản thu 93.000 VND không được dùng để đánh dấu đơn 930.000 VND là đã thanh toán đủ. Cần ghi nhận chênh lệch và đưa vào quy trình xử lý phù hợp; không sửa dữ liệu gốc cho khớp một cách âm thầm.

### 10.3. Sự kiện đến muộn hoặc sai thứ tự

Giả sử:

```text
1. Nhận capture succeeded.
2. Đơn được ghi nhận đã thu.
3. Nhận lại một thông báo pending cũ.
```

Handler không được đơn giản gán trạng thái theo thông báo cuối nhận được. “Đến sau” không đồng nghĩa “xảy ra sau”.

Nên dùng state machine và ngữ nghĩa của từng sự kiện. Một sự kiện pending cũ không làm lùi trạng thái đã thu. Một sự kiện hoàn, đảo giao dịch hoặc tranh chấp hợp lệ là nghiệp vụ khác, cần trạng thái và bút toán riêng theo mô hình.

Timestamp đơn lẻ thường không đủ để giải quyết mọi thứ tự, đặc biệt khi các hệ thống dùng đồng hồ khác nhau. Cần dựa vào quan hệ định danh, loại sự kiện, phiên bản hoặc cách truy vấn trạng thái có thẩm quyền mà giao thức cung cấp.

### 10.4. Kết quả chưa xác định là một trạng thái cần quản lý

Khi gọi thu hoặc hoàn bị timeout:

```text
Không có phản hồi
⇒ chưa biết kết quả

Không có phản hồi
⇏ chắc chắn thất bại
```

Cần lưu định danh, giữ các ràng buộc đang áp dụng và tra cứu hoặc thử lại theo hợp đồng. Nếu có giới hạn thời gian xử lý, cần theo dõi tuổi của trạng thái chưa xác định và đưa vào xử lý sự cố khi vượt ngưỡng đã thiết kế.

Không đánh dấu thất bại chỉ để cho phép tạo một tác động mới. Cách đó có thể biến lỗi liên lạc thành thu hoặc hoàn trùng.

## 11. Sổ cái và khả năng tái dựng kết quả

### 11.1. Lưu sự kiện tiền tệ có ý nghĩa

Một trường `balance` được cập nhật trực tiếp không giải thích được vì sao số dư có giá trị hiện tại.

Các bản ghi về tác động nên liên kết tới nghiệp vụ gốc, ví dụ:

```text
businessOperationId
tenantId
orderId hoặc paymentId
loại tác động
amount và currency
trạng thái và bằng chứng xác nhận
providerReference nếu có
thời điểm liên quan
quan hệ với tác động gốc nếu là hoàn hoặc điều chỉnh
```

Khi dùng sổ cái bút toán kép, tổng debit phải bằng tổng credit cho từng tiền tệ trong một giao dịch đã ghi sổ theo mô hình tài khoản được chọn. Không cộng những tiền tệ khác nhau để tạo ra một phép cân bằng vô nghĩa.

Trong một mô hình chuyển số dư ví nội bộ đơn giản, không phí và cùng tiền tệ:

```text
Trước: ví A = 1.000, ví B = 200
Chuyển: 100 từ A sang B
Sau:   ví A =   900, ví B = 300

Tổng số dư trước = tổng số dư sau = 1.200
```

Đây là minh họa bảo toàn trong một hệ đóng đã nêu giả định. Khi có nạp, rút, phí hoặc tương tác bên ngoài, các luồng đó phải được mô hình hóa bằng tài khoản hoặc bút toán tương ứng; không thể áp dụng công thức bảo toàn trên hai ví mà bỏ qua phần còn lại.

### 11.2. Ghi trạng thái và bằng chứng nhất quán

Nếu trạng thái payment, bản ghi tác động và bút toán nằm trong cùng cơ sở dữ liệu và cùng quyết định, transaction cần ngăn các trường hợp:

- Trạng thái đã thu nhưng thiếu bản ghi thu.
- Có bút toán nhưng command bị coi là chưa thực hiện và được chạy lại.
- Hoàn thành công nhưng số dư reserved chưa giảm.
- Bút toán ghi hai lần khi cùng sự kiện được nhận lại.

Nếu sổ cái nằm ở một dịch vụ khác, cần mô hình hóa khoảng trễ và dùng cơ chế phát tin bền vững, khử trùng và đối soát. Không giả định transaction nội bộ bao phủ cơ sở dữ liệu của dịch vụ khác.

### 11.3. Điều chỉnh bằng tác động có dấu vết

Khi một khoản đã được ghi nhận cần sửa, việc xóa lịch sử hoặc sửa trực tiếp giá trị cũ có thể làm mất khả năng giải thích.

Một thiết kế có thể giữ bản ghi gốc và tạo giao dịch đảo hoặc điều chỉnh có liên kết, có quyền phê duyệt và lý do phù hợp. Cách tổ chức cụ thể phụ thuộc mô hình sổ cái và nghiệp vụ, nhưng quan hệ giữa sự kiện gốc và điều chỉnh cần được giữ.

Chỉ gọi bảng là “append-only” chưa làm dữ liệu không thể bị sửa. Cần quyền ghi phù hợp, đường điều chỉnh được kiểm soát và bằng chứng phục vụ đối soát.

## 12. Đối soát là một phần của mục tiêu bảo mật

### 12.1. Vì sao giao dịch đúng tại API vẫn cần đối soát?

Các ranh giới hệ thống có thể gặp lỗi sau một phần công việc:

```text
Nhà cung cấp đã thu thành công
→ phản hồi bị mất
→ ứng dụng còn pending

Ứng dụng ghi nhận ý định hoàn
→ nhà cung cấp xử lý
→ callback chưa tới
```

Đối soát so sánh những nguồn có thẩm quyền để phát hiện và xử lý các trạng thái chưa khớp. Đây là cơ chế hoàn thiện tính đúng đắn khi không có một transaction bao trùm mọi bên.

### 12.2. So sánh đủ chiều, không chỉ tổng ròng

Với mô hình thu và hoàn đơn giản:

```text
netCollected = confirmedCaptures - confirmedRefunds
```

Tuy nhiên, tổng ròng khớp không đủ. Một lần thu thừa 100 và hoàn thừa 100 có thể làm tổng ròng không đổi nhưng vẫn vi phạm.

Đối soát nên so sánh theo định danh giao dịch và tiền tệ, đồng thời tách:

- Khoản thu và khoản hoàn.
- Tổng tiền gốc và phí liên quan.
- Giao dịch thành công, thất bại và chưa xác định.
- Dữ liệu giao dịch và dữ liệu quyết toán nếu hệ thống có cả hai.

Không so trực tiếp số tiền nhà cung cấp chuyển ròng sau phí với tổng tiền khách trả mà bỏ qua cấu trúc phí. Sai khác có thể có lời giải thích hợp lệ, nhưng lời giải thích phải được mô hình hóa.

### 12.3. Cách xử lý chênh lệch

| Chênh lệch | Hướng xử lý cần có |
| --- | --- |
| Bên ngoài thành công, nội bộ pending | Xác minh đối tượng và cập nhật qua đường xử lý có khử trùng |
| Nội bộ paid, không tìm thấy bằng chứng tương ứng | Điều tra nguồn chuyển trạng thái và dữ liệu tích hợp |
| Số tiền hoặc tiền tệ không khớp | Cô lập trường hợp sai lệch, tránh cấp thêm quyền lợi như thể đã thanh toán đủ |
| Cùng tác động được ghi nhận nhiều lần | Xác định bản ghi gốc, chặn tái áp dụng và điều chỉnh có dấu vết |
| Pending quá lâu | Tra cứu, thử lại an toàn hoặc chuyển xử lý sự cố theo thiết kế |

Một tiến trình đối soát cũng có thể chạy lại hoặc nhận dữ liệu trùng. Nó phải dùng cùng các bất biến và định danh nghiệp vụ, không được “sửa số dư” vô điều kiện cho hai bên nhìn có vẻ bằng nhau.

## 13. Kiểm thử các kết quả sai mà kẻ lạm dụng muốn tạo ra

### 13.1. Ma trận tình huống

| Mục tiêu bị tấn công | Tình huống cần thử | Kết quả cần chứng minh |
| --- | --- | --- |
| Đúng số tiền | Sửa giá, tổng hoặc phí trong request | Máy chủ từ chối hoặc tính theo dữ liệu có thẩm quyền |
| Đúng giảm giá | Dùng coupon ngoài scope, hết hiệu lực hoặc vượt số lần dùng | Không tạo mức phải trả ngoài chính sách |
| Đúng tiền tệ | Tráo currency hoặc sai đơn vị tích hợp | Không áp dụng giao dịch sai nghĩa tiền tệ |
| Đúng miền biểu diễn | Số lượng và giá lớn gây tràn phép nhân hoặc cộng | Từ chối, không commit số tiền sai |
| Đúng phân bổ | Chia giảm giá có phần dư rồi hoàn từng phần | Tổng phân bổ khớp; tổng hoàn theo dòng không vượt phần được phép |
| Đúng người nhận | Đổi tài khoản đích sau phê duyệt | Không sử dụng lại quyết định cũ cho người nhận mới |
| Đúng quyền | Actor có role nhưng sai tenant, sai đơn hoặc vượt hạn mức | Không tạo tác động tiền tệ ngoài quyền |
| Không thu trùng | Mất phản hồi sau thu rồi retry | Cùng nghĩa vụ không bị thu thêm |
| Không hoàn vượt trần | Hai yêu cầu hoàn 500.000 cùng chạy khi hạn mức 900.000 | Không chấp nhận tổng reserved và confirmed vượt 900.000 |
| Không hoàn trùng theo dòng | Tạo hai command khác khóa cho cùng phần hàng | Giới hạn số lượng và giá trị hoàn theo dòng vẫn giữ |
| Bằng chứng đúng | Client tự báo thành công | Không chuyển sang đã thu chỉ từ dữ liệu client |
| Ánh xạ đúng | Callback xác thực được nhưng sai amount, currency hoặc order | Không gắn sai kết quả; có bản ghi xử lý chênh lệch |
| Chịu được sự kiện lặp | Gửi lại cùng callback hoặc hai event cho cùng tác động | Không ghi nhận hai lần tiền hay bút toán |
| Chịu được sai thứ tự | Event pending cũ tới sau succeeded | Không làm lùi trạng thái hoặc tạo lại tác động |
| Không mất hạn mức khi chưa biết kết quả | Timeout sau khi bên ngoài đã nhận lệnh hoàn | Không giải phóng reserved chỉ vì timeout |
| Nhất quán cục bộ | Gây lỗi sau một phần ghi nhưng trước commit | Không để lại trạng thái, số dư và outbox dở dang |
| Phục hồi đúng | Chạy đối soát nhiều lần trên cùng dữ liệu | Không tạo thêm tác động sau lần đã áp dụng |

### 13.2. Kiểm tra số dư và bản ghi, không chỉ mã phản hồi

Một API trả lỗi vẫn có thể đã commit trước khi kết nối bị ngắt. Một API trả thành công cũng có thể bỏ qua việc câu lệnh cập nhật không tác động dòng nào.

Sau thử nghiệm, cần đọc lại các dữ liệu phù hợp:

```text
Giá và phân bổ đã chấp nhận
Trạng thái đơn và phiên bản nội dung
Ý định thanh toán và kết quả đã xác nhận
refundedConfirmed và refundReserved
Số refund theo nghiệp vụ và theo nhà cung cấp
Bút toán, idempotency record và outbox liên quan
```

Kiểm thử cạnh tranh cần dùng cơ sở dữ liệu phù hợp và điều khiển lịch bằng cơ chế đồng bộ, thay vì chỉ dựa vào sleep. Có thể chấp nhận các thứ tự thắng khác nhau, nhưng mọi kết quả commit đều phải giữ bất biến.

Đối với tích hợp ngoài, dùng mô phỏng có kiểm soát để tạo trường hợp “đã thực hiện nhưng mất phản hồi”, sự kiện lặp và sai thứ tự. Unit test phép tính không chứng minh được những thuộc tính này.

### 13.3. Đo điều gì trong vận hành?

Các tín hiệu hữu ích có thể gồm:

- Số trường hợp amount, currency hoặc đối tượng không khớp.
- Số giao dịch pending hoặc unknown vượt thời gian xử lý đã định.
- Vi phạm constraint và các lần từ chối vượt hạn mức.
- Chênh lệch thu, hoàn và bút toán trong đối soát.
- Số tác động bên ngoài có bằng chứng nhưng chưa được ghi nhận nội bộ.

Số request thành công cao hoặc độ trễ thấp không chứng minh kết quả tài chính đúng. Không phát hiện chênh lệch cũng chưa đủ nếu quy trình đối soát bị ngừng hoặc phạm vi kiểm tra không bao phủ các luồng quan trọng.

## 14. Đặc tả một mục tiêu có thể nghiệm thu

Với ví dụ trong bài, có thể viết mục tiêu như sau:

> Mỗi đơn có giá trị phải trả 930.000 VND theo báo giá được chấp nhận chỉ được ghi nhận thanh toán đủ khi có bằng chứng đúng đối tượng, đúng tiền tệ và đúng số tiền. Trong mô hình một lần thu, cùng nghĩa vụ không được tạo thêm lần thu thành công. Tổng hoàn đã xác nhận cộng tiền giữ chỗ cho hoàn không vượt hạn mức 900.000 VND theo chính sách của đơn.

Kèm theo đó là các điều kiện thực thi:

| Thành phần | Nội dung cần chốt |
| --- | --- |
| Phạm vi | Một tenant, đơn, ý định thanh toán và các refund liên quan |
| Nguồn sự thật | Snapshot giá và phân bổ ở máy chủ; bằng chứng tác động từ kênh tích hợp tin cậy |
| Quyền | Quyền theo đối tượng, hạn mức và phê duyệt cho đúng nội dung |
| Tính nguyên tử cục bộ | Guard, giữ chỗ, thay đổi trạng thái và các ghi liên quan trong ranh giới nhất quán đã chọn |
| Chống lặp | Idempotency theo command, tính duy nhất nghiệp vụ và chuyển trạng thái có điều kiện |
| Ngoài hệ thống | Định danh ổn định, quản lý unknown, khử trùng và đối soát |
| Bằng chứng | Kết quả kiểm thử giá trị, quyền, cạnh tranh, lỗi giữa chừng và đối soát |

Nếu thêm thanh toán nhiều phần, phí có thể hoàn, tranh chấp hoặc quy đổi tiền tệ, phải sửa mục tiêu và mô hình trước khi mở rộng handler. Những giả định không còn đúng không nên tiếp tục tồn tại dưới dạng điều kiện rải rác trong code.

Tính đúng đắn của kết quả tài chính được đánh giá ở sự thật cuối cùng mà hệ thống có thể chứng minh: tiền nào đã được tính, ai cho phép, tác động nào đã xảy ra, xảy ra bao nhiêu lần và các bản ghi giải thích chúng ra sao.
