# Fractional amount handling

## 1. Phần lẻ của số tiền là một quy tắc nghiệp vụ

**Fractional amount handling** là cách hệ thống tiếp nhận, tính toán, lưu giữ, phân bổ và kết chuyển những phần tiền chưa biểu diễn được ở đơn vị thanh toán cuối cùng.

Trong chương **Rounding Rules** của module **Business Logic Security**, vấn đề này liên quan trực tiếp đến việc bảo vệ các bất biến tiền tệ. Một phần lẻ rất nhỏ có thể trở thành sai lệch lớn khi được lặp lại, hoặc thành đường lạm dụng nếu người dùng điều khiển được cách chia giao dịch, thứ tự xử lý và thời điểm làm tròn.

Ví dụ một hợp đồng tính phí sử dụng có mức phát sinh 0,004 đơn vị tiền cho mỗi sự kiện. Kênh thanh toán của ví dụ chỉ nhận hai chữ số thập phân:

~~~text
Làm tròn từng sự kiện đến 0,01:
  0,004 -> 0,00
  500 sự kiện -> thu 0,00

Cộng theo phạm vi hợp đồng trước khi chốt:
  500 * 0,004 = 2,000
  Số tiền chốt = 2,00
~~~

Chọn cách nào là một quyết định sản phẩm. Nếu hợp đồng quy định cộng theo kỳ mà API lại làm tròn theo từng request, người dùng có thể chia nhỏ yêu cầu để làm biến mất nghĩa vụ phí.

Các số tiền, độ chính xác và chính sách trong bài là giả định minh họa. Với phí, thuế hoặc hóa đơn thực tế, cần áp dụng quy tắc đã được xác định cho sản phẩm và phạm vi hoạt động, thay vì coi một chế độ làm tròn là chuẩn cho mọi trường hợp.

## 2. Phân biệt các lớp độ chính xác

| Lớp | Cần trả lời | Ví dụ của bài |
| --- | --- | --- |
| Độ chính xác đầu vào | API cho phép người dùng yêu cầu số tiền với bước nhỏ nhất nào? | Chuyển tiền chỉ nhận bội số 0,01 |
| Độ chính xác tính toán | Cần giữ bao nhiêu thông tin khi nhân đơn giá, tỷ lệ hoặc phân bổ? | Phí sử dụng được tính tới 0,000001 |
| Độ chính xác ghi nhận nội bộ | Sổ chi tiết có ghi được phần nhỏ hơn đơn vị thanh toán không? | Bucket tích lũy lưu số nguyên theo 0,000001 |
| Đơn vị ghi nợ/ghi có cuối cùng | Số tiền có hiệu lực đối với số dư được chốt theo bước nào? | Số dư thanh toán theo 0,01 |
| Đơn vị của kênh thanh toán | Nhà cung cấp hoặc kênh tiền mặt chấp nhận bước nào? | Có thể khác cách biểu diễn nội bộ |
| Độ chính xác hiển thị | Người dùng thấy bao nhiêu chữ số? | Trang tổng quan hiển thị 2 chữ số |

Không suy lớp này từ lớp khác. Một giao diện hiển thị 0,00 không chứng minh nghĩa vụ tích lũy là 0. Ngược lại, việc tính toán được 0,004 không tự tạo quyền chuyển hoặc rút 0,004 nếu sản phẩm chỉ cho thao tác theo 0,01.

### 2.1. Scale và quantum không hoàn toàn giống nhau

**Scale** là số chữ số thập phân trong một biểu diễn. **Quantum** là bước giá trị hợp lệ của thao tác.

Ví dụ, hai chữ số thập phân có thể biểu diễn 1,01, nhưng một kênh giả định chỉ chấp nhận bước 0,05 thì 1,01 vẫn không hợp lệ. Khi amount đã ở minor unit:

~~~text
amountMinor % quantumMinor == 0
~~~

Kiểm tra scale không thay thế kiểm tra quantum. Không dùng quy tắc của kênh tiền mặt để âm thầm sửa nghĩa vụ trên sổ điện tử nếu hai lớp có chính sách khác nhau.

### 2.2. Minor unit và đơn vị nội bộ phải được ghi rõ

Trong mô hình minh họa:

~~~text
1 major unit      = 100 payable minor units
1 major unit      = 1.000.000 internal units
1 payable minor   = 10.000 internal units
~~~

Cùng số nguyên 10.000 có thể nghĩa là 100,00 major units ở một trường, hoặc 0,010000 major unit ở trường khác. Do đó kiểu dữ liệu và schema cần gắn amount với currency, đơn vị, loại số tiền và phiên bản chính sách.

Không mặc định mọi currency có hai chữ số thập phân. Currency registry và quy tắc của từng thao tác phải đến từ cấu hình có thẩm quyền phía máy chủ.

## 3. Quyền quyết định phần lẻ thuộc về máy chủ

Client có thể gửi lượng sử dụng, yêu cầu chuyển tiền hoặc lựa chọn sản phẩm trong phạm vi được phép. Client không có quyền tự chọn:

- Scale ghi sổ.
- Chế độ làm tròn.
- Phạm vi cộng gộp trước khi làm tròn.
- Người nhận phần dư.
- Ngưỡng “bỏ qua sai số”.
- Cách tính lại phần lẻ của nghĩa vụ đã chốt.

Một request như sau không phải bằng chứng nghiệp vụ hợp lệ:

~~~json
{
  "amount": "0.004",
  "roundingMode": "DOWN",
  "roundingScale": 2,
  "discardResidual": true,
  "residualAccountId": "my-wallet"
}
~~~

Các trường ảnh hưởng tiền phải được suy từ chính sách đã phê duyệt. Nếu sản phẩm có nhiều lựa chọn được phép, máy chủ vẫn kiểm tra lựa chọn có đúng quyền, hợp đồng và trạng thái hiện tại hay không.

### 3.1. Phần dư có chủ sở hữu và phạm vi

Một bucket phần dư có thể được định danh theo:

~~~text
tenant
customer hoặc account
contract hoặc nghĩa vụ
currency
accrual type
billing period hoặc quy tắc carry-forward
policy version
~~~

Không gộp phần dư của hai khách hàng chỉ vì cùng currency. Không để client tạo bucket mới tùy ý sau mỗi request để reset phần lẻ.

Quyền đọc, kết chuyển, xóa nợ lẻ hoặc điều chỉnh bucket phải gắn với đúng đối tượng. ID khó đoán không thay thế kiểm tra tenant và quan hệ tài khoản.

### 3.2. Phê duyệt phải xét số tiền có thẩm quyền

Nếu phê duyệt được yêu cầu từ một ngưỡng tiền, chính sách phải chỉ rõ ngưỡng xét trên số tiền tính toán hay số tiền thanh toán đã chốt.

Không để endpoint A so số tiền trước làm tròn còn endpoint B so số tiền sau cắt phần lẻ mà không có lý do. Không cho client chia một nghĩa vụ thành nhiều mảnh dưới ngưỡng nếu chính sách xét tổng theo hợp đồng hoặc theo kỳ.

Quyết định phê duyệt nên liên kết với snapshot tính toán, tổng phải trả, phạm vi nghĩa vụ và phiên bản rounding policy. Khi một điều kiện quan trọng thay đổi, phải đánh giá lại quyền và phê duyệt.

## 4. Chọn rõ cách xử lý số tiền không biểu diễn được

Có bốn hướng thường gặp, mỗi hướng phục vụ một loại hành động:

| Hướng xử lý | Phù hợp khi | Điều kiện bảo vệ |
| --- | --- | --- |
| Từ chối | Người dùng yêu cầu chuyển một số tiền phải biểu diễn chính xác | Không âm thầm đổi ý định |
| Làm tròn tại điểm chốt | Phí, thuế hoặc tổng tiền được tính theo chính sách xác định | Có chế độ, phạm vi và phiên bản |
| Giữ phần dư để tích lũy | Phát sinh hợp lệ nhỏ hơn đơn vị thanh toán | Có chủ sở hữu, bảo toàn và chống lặp |
| Phân bổ số nguyên | Chia tổng đã chốt cho nhiều dòng hoặc người nhận | Tổng các phần bằng đúng tổng gốc |

Không áp dụng một quy tắc “cắt hết sau hai số” cho tất cả các hướng.

### 4.1. Đầu vào thanh toán: ưu tiên kiểm tra biểu diễn chính xác

Giả sử API chuyển tiền chỉ hỗ trợ bước 0,01:

~~~text
"1.23"   -> hợp lệ
"1.2300" -> có thể hợp lệ nếu hợp đồng cho phép số 0 dư
"1.234"  -> từ chối, không tự sửa thành 1.23
"0.004"  -> từ chối đối với thao tác chuyển tiền này
~~~

Nhưng 0,004 có thể hợp lệ trong sự kiện tích lũy phí có đơn vị nội bộ nhỏ hơn. Validation phải thuộc loại thao tác, không chỉ thuộc một hàm parse chung.

Một API có thể quy định chỉ nhận số nguyên minor unit dưới dạng chuỗi. Khi đó không có bước “làm tròn đầu vào”; chỉ cần kiểm tra định dạng, miền giá trị, currency và quantum.

### 4.2. Ví dụ Java nhận số tiền mà không làm mất phần lẻ

Đoạn sau minh họa một API nhận số thập phân dương, dùng scale do server cung cấp. Giới hạn scale 0..6 và kích thước input là giả định kỹ thuật của ví dụ.

~~~java
static long parsePositiveMinor(
        String raw,
        int payableScale,
        long maximumMinor) {

    if (payableScale < 0 || payableScale > 6 || maximumMinor <= 0) {
        throw new IllegalArgumentException("Invalid server policy");
    }
    if (raw == null || raw.length() > 24
            || !raw.matches("[0-9]{1,12}([.][0-9]{1,6})?")) {
        throw new IllegalArgumentException("Invalid decimal format");
    }

    try {
        BigDecimal exact = new BigDecimal(raw);
        BigDecimal normalized = exact.setScale(
            payableScale, RoundingMode.UNNECESSARY
        );
        long minor = normalized.movePointRight(payableScale)
            .longValueExact();

        if (minor <= 0 || minor > maximumMinor) {
            throw new IllegalArgumentException("Amount out of range");
        }
        return minor;
    } catch (ArithmeticException ex) {
        throw new IllegalArgumentException(
            "Amount cannot be represented exactly", ex
        );
    }
}
~~~

Với scale 2, hàm chấp nhận 1,2300 và trả 123; nó từ chối 1,234. Định dạng này không nhận dấu phẩy, số mũ, dấu âm hoặc khoảng trắng. Đó là hợp đồng của ví dụ; phần hiển thị theo locale cần xử lý riêng.

Không lấy scale hoặc maximumMinor trực tiếp từ request. Kiểm tra giới hạn chuỗi trước khi tạo số giúp tránh xử lý những biểu diễn quá lớn.

Các hành vi scale, số thập phân và chuyển đổi chính xác được mô tả trong [Java BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html). Dùng kiểu thập phân không tự quyết định quy tắc nghiệp vụ; chính sách vẫn phải được truyền từ nguồn có thẩm quyền.

## 5. Chế độ làm tròn không giải quyết toàn bộ bài toán

Ví dụ làm tròn đến hai chữ số:

| Chế độ | 1,005 | -1,005 |
| --- | --- | --- |
| DOWN | 1,00 | -1,00 |
| FLOOR | 1,00 | -1,01 |
| HALF_UP | 1,01 | -1,01 |
| HALF_EVEN | 1,00 | -1,00 |

DOWN hướng về 0; FLOOR hướng về phía âm. HALF_EVEN chọn giá trị gần nhất và chọn chữ số cuối chẵn ở điểm giữa. Đặc tả chi tiết có trong [Java RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html).

Không gọi tất cả các lựa chọn này là “làm tròn xuống”. Đặc biệt, dùng FLOOR cho số âm rồi dùng DOWN cho số dương có thể khiến debit và credit không đối xứng.

HALF_EVEN có thể giảm thiên lệch trong một số tập phép tính, nhưng không ngăn người dùng điều khiển số lần làm tròn hoặc cách chia nghĩa vụ. Bảo vệ business logic cần cả phạm vi tổng hợp và ràng buộc số lần thực thi.

### 5.1. Làm tròn hai lần có thể đổi kết quả

~~~text
Giá trị tính toán: 1,2449

HALF_UP đến 3 chữ số: 1,245
Sau đó HALF_UP đến 2 chữ số: 1,25

HALF_UP trực tiếp đến 2 chữ số: 1,24
~~~

Vì vậy cần phân biệt độ chính xác tính toán trung gian với điểm chốt tiền. Không dùng số đã format cho giao diện làm đầu vào ghi sổ.

Với phép chia vô hạn như 1/3, không thể giữ mọi chữ số bằng một số thập phân hữu hạn. Hệ thống phải chọn precision trung gian đủ theo chính sách hoặc lưu tỷ lệ bằng tử số/mẫu số khi cần tính chính xác. Không thêm một lệnh rounding tùy ý chỉ để tránh exception.

### 5.2. Không dùng epsilon để hợp thức hóa chênh lệch tiền

Điều kiện kiểu:

~~~java
// Không phù hợp cho amount đã chốt theo đơn vị tiền.
if (Math.abs(expected - actual) < 0.01) {
    accept();
}
~~~

có thể cho qua nhiều giao dịch lệch gần một minor unit. Khi đã chuẩn hóa về số nguyên đúng đơn vị, so đúng số nguyên.

Nếu đối soát có dung sai hợp lệ, cần chính sách riêng về currency, nguồn sai lệch, mức tổng và tài khoản điều chỉnh. Dung sai đó không tự cho phép thanh toán thiếu hoặc hoàn dư.

## 6. Các bất biến bảo toàn phần lẻ

### 6.1. Khi chốt một giá trị tính toán

Đặt:

~~~text
rawAmount = postedAmount + roundingDelta
~~~

Cả ba phải được hiểu trong cùng currency và một hệ đơn vị đủ chính xác. Delta có thể âm:

~~~text
raw = 0,006
posted = 0,01
delta = -0,004
~~~

Nếu đơn vị nội bộ chỉ có hai chữ số, không thể lưu chính xác delta này bằng cùng kiểu amount đó. Cần trường có độ chính xác thích hợp hoặc biểu diễn theo đơn vị nội bộ nhỏ hơn.

Delta không mặc định là tài sản có thể rút. Quyền sở hữu và cách xử lý phụ thuộc chính sách của loại nghĩa vụ.

### 6.2. Khi tích lũy các phát sinh không âm

Bài học dùng mô hình tích lũy bằng số nguyên:

~~~text
U = số internal units cho một payable minor
x = phát sinh mới, tính bằng internal units
r = phần dư đang giữ, tính bằng internal units

s = r + x
newPayableMinor = s div U
newResidualInternal = s mod U

r + x = newPayableMinor * U + newResidualInternal
0 <= newResidualInternal < U
~~~

Đây là phép chia lấy thương/phần dư cho số không âm. Nó khác với việc áp dụng HALF_EVEN riêng cho mỗi sự kiện.

Trong mô hình, tổng được kết chuyển vào khoản phải trả hoặc phải thu, chưa đồng nghĩa đã thu hoặc chi tiền qua ngân hàng. Nếu thanh toán thất bại, không được cộng lại phát sinh gốc như thể chưa từng kết chuyển.

### 6.3. Khi phân bổ tổng tiền

~~~text
sum(allocatedMinor[i]) = finalizedTotalMinor
allocatedMinor[i] >= 0
~~~

Tổng đã chốt là nguồn có thẩm quyền. Không chia mỗi phần bằng phép làm tròn độc lập rồi chấp nhận một tổng khác.

### 6.4. Khi hoàn tiền hoặc đảo nghiệp vụ

~~~text
successfulRefundMinor + pendingRefundMinor + requestedRefundMinor
    <= refundableOriginalMinor
~~~

Các giá trị phải cùng currency, đơn vị và giao dịch gốc. Phân bổ và phần dư của giao dịch gốc cần được dùng theo chính sách, thay vì tính lại mọi phần bằng dữ liệu hoặc chế độ làm tròn mới.

## 7. Giữ phần dư bằng bucket tích lũy

### 7.1. Ví dụ ba sự kiện nhỏ

Giả sử:

~~~text
Internal scale = 6
Payable scale = 2
U = 10.000 internal units / payable minor
Mỗi sự kiện hợp lệ phát sinh 0,004000 = 4.000 internal units
~~~

| Sự kiện | Phần dư trước | Phát sinh mới | Kết chuyển thêm, payable minor | Phần dư sau |
| --- | ---: | ---: | ---: | ---: |
| E1 | 0 | 4.000 | 0 | 4.000 |
| E2 | 4.000 | 4.000 | 0 | 8.000 |
| E3 | 8.000 | 4.000 | 1 | 2.000 |

Sau ba sự kiện:

~~~text
Tổng phát sinh = 0,012000
Đã kết chuyển = 0,01
Còn giữ phần dư = 0,002000
~~~

Sau 500 sự kiện, tổng phát sinh là 2,000000; đã kết chuyển 200 payable minor và phần dư bằng 0. Việc gửi lại một sự kiện không được làm tăng tổng phát sinh lần nữa.

### 7.2. Hàm tính bước tích lũy

Dùng số nguyên lớn giúp tránh tràn ở phép cộng trung gian trong ví dụ:

~~~java
record AccrualStep(
    BigInteger payableMinor,
    BigInteger residualInternal
) {}

static AccrualStep accrue(
        BigInteger oldResidual,
        BigInteger newAccrual,
        BigInteger unitsPerMinor) {

    if (oldResidual == null || newAccrual == null
            || unitsPerMinor == null
            || unitsPerMinor.signum() <= 0
            || oldResidual.signum() < 0
            || oldResidual.compareTo(unitsPerMinor) >= 0
            || newAccrual.signum() < 0) {
        throw new IllegalArgumentException("Invalid accrual state");
    }

    BigInteger[] qr = oldResidual.add(newAccrual)
        .divideAndRemainder(unitsPerMinor);

    return new AccrualStep(qr[0], qr[1]);
}
~~~

Hàm chỉ xử lý các phát sinh không âm theo mô hình. Điều chỉnh giảm, hủy sử dụng và sửa lỗi phải là operation riêng có bằng chứng và quyền, không đưa số âm vào hàm rồi kỳ vọng phép chia vẫn có cùng ý nghĩa.

BigInteger không loại bỏ giới hạn tài nguyên. Cần giới hạn miền số lượng sử dụng, đơn giá, số chữ số và số sự kiện theo hợp đồng trước khi tính.

### 7.3. Cập nhật bucket và khoản phải trả phải nguyên tử

Mẫu sai:

~~~text
Transaction A: cập nhật phần dư.
Transaction B: ghi thêm payable.
Transaction C: đánh dấu sự kiện đã xử lý.
~~~

Nếu hệ thống crash giữa các transaction, có thể mất tiền, tạo tiền hoặc cộng lại sự kiện.

Luồng đúng cần một transaction cho sự kiện nội bộ:

~~~text
1. Xác thực nguồn sự kiện và kiểm tra tenant/contract.
2. Claim định danh sự kiện nghiệp vụ, phát hiện payload xung đột.
3. Khóa bucket thuộc phạm vi do server xác định.
4. Kiểm tra trạng thái, policy và kỳ.
5. Tính x từ lượng sử dụng và đơn giá có thẩm quyền.
6. Tính payable tăng thêm và residual mới bằng phép chia số nguyên.
7. Cập nhật tổng phát sinh, tổng kết chuyển và residual.
8. Nếu payable tăng thêm > 0, ghi nghĩa vụ và bút toán tương ứng.
9. Ghi kết quả sự kiện cùng outbox rồi commit.
~~~

Nếu payable tăng thêm bằng 0, sự kiện vẫn có hiệu lực tích lũy và phải được deduplicate. Không trả kết quả “không phát sinh gì” rồi bỏ luôn phần dư.

Phản hồi có thể phân biệt:

~~~json
{
  "eventApplied": true,
  "newPayableMinor": "0",
  "residualRecorded": true
}
~~~

Không cần công bố toàn bộ dữ liệu phần dư cho mọi client. Người dùng được xem dữ liệu nào còn tùy quyền và hợp đồng, nhưng hệ thống phải giữ đủ dữ liệu để giải thích kết quả.

### 7.4. Hai request đồng thời không được ghi đè phần dư

Giả sử residual đang là 8.000, hai sự kiện mỗi sự kiện thêm 4.000:

~~~text
Kết quả đúng:
  Tổng = 8.000 + 4.000 + 4.000 = 16.000
  Kết chuyển thêm = 1 minor
  Residual cuối = 6.000
~~~

Nếu cả hai cùng đọc 8.000 rồi cùng ghi residual = 2.000, hệ thống có thể kết chuyển 2 minor hoặc làm mất một phát sinh.

Cần khóa dòng bucket, optimistic locking với version và retry toàn transaction, hoặc một cơ chế cập nhật nguyên tử tương đương. Mọi instance và mọi endpoint điều chỉnh bucket phải dùng cùng cơ chế.

Idempotency chỉ ngăn cùng sự kiện bị áp dụng lại; hai sự kiện khác nhau vẫn cần kiểm soát đồng thời trên bucket chung.

## 8. Mô hình dữ liệu và vòng đời bucket

### 8.1. Phác thảo ràng buộc PostgreSQL

~~~sql
CREATE TABLE fractional_bucket (
    tenant_id UUID NOT NULL,
    bucket_id UUID NOT NULL,
    owner_id UUID NOT NULL,
    contract_id UUID NOT NULL,
    currency VARCHAR(3) NOT NULL,
    accrual_type VARCHAR(40) NOT NULL,
    period_key VARCHAR(40) NOT NULL,
    policy_version VARCHAR(80) NOT NULL,
    state VARCHAR(20) NOT NULL
        CHECK (state IN ('OPEN', 'CLOSING', 'CLOSED')),
    units_per_minor NUMERIC(24, 0) NOT NULL
        CHECK (units_per_minor > 0),
    accrued_internal NUMERIC(30, 0) NOT NULL
        CHECK (accrued_internal >= 0),
    adjustment_internal NUMERIC(30, 0) NOT NULL DEFAULT 0,
    posted_minor NUMERIC(30, 0) NOT NULL
        CHECK (posted_minor >= 0),
    residual_internal NUMERIC(30, 0) NOT NULL
        CHECK (residual_internal >= 0),
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, bucket_id),
    UNIQUE (
        tenant_id, owner_id, contract_id,
        currency, accrual_type, period_key
    ),
    CHECK (residual_internal < units_per_minor),
    CHECK (
        accrued_internal + adjustment_internal
        = posted_minor * units_per_minor + residual_internal
    )
);
~~~

`adjustment_internal` tách các điều chỉnh đã phê duyệt khỏi phát sinh gốc. Ở luồng tích lũy thông thường, trường này bằng 0. Mỗi lần điều chỉnh cần bản ghi riêng với lý do, chủ thể, căn cứ và liên kết bút toán; không chỉ sửa con số tổng hợp.

Một bảng ghi nhận sự kiện nên có khóa duy nhất theo:

~~~text
(tenant_id, producer_id, source_event_id)
~~~

Producer phải được xác thực; ID sự kiện phải ổn định từ nguồn nghiệp vụ. Nếu client có thể tạo ID mới cho cùng một sự kiện sử dụng, unique key này chưa đủ. Cần liên kết nguồn đo hoặc nghĩa vụ gốc để chống khai lại.

Bản ghi sự kiện giữ bucket ID, fingerprint nội dung có ảnh hưởng và kết quả đã commit. Cùng ID nhưng payload khác phải bị từ chối hoặc đưa vào luồng điều chỉnh chuyên biệt.

Schema đầy đủ cần khóa ngoại có tenant tới owner, contract, event và các nghĩa vụ. CHECK bảo toàn trên một dòng không tự chứng minh tổng các bút toán chi tiết khớp bucket; trách nhiệm đó cần transaction và đối soát.

### 8.2. State machine khi chốt kỳ

~~~mermaid
stateDiagram-v2
    [*] --> OPEN: Mở kỳ theo chính sách
    OPEN --> CLOSING: Khóa nhận phát sinh thông thường
    CLOSING --> CLOSED: Kết chuyển hoặc xử lý phần dư có audit
    CLOSED --> [*]
~~~

Đóng kỳ phải phối hợp với ingest sự kiện. Ví dụ, cần watermark hoặc quy tắc cắt kỳ để xác định nguồn đã gửi đủ dữ liệu.

Sự kiện đến muộn không được âm thầm bỏ qua. Chính sách có thể yêu cầu điều chỉnh kỳ cũ hoặc ghi vào kỳ sau với tham chiếu kỳ gốc. Không tự mở lại bucket CLOSED chỉ vì có một request mới.

Sửa chính sách không được reset residual về 0. Có thể giữ phiên bản chính sách cố định trong vòng đời bucket, rồi chuyển sang phiên bản mới bằng một operation migration hoặc kỳ mới có bảo toàn.

### 8.3. Cuối kỳ, phần dư đi đâu?

Các lựa chọn cần được xác định trước:

- **Carry-forward:** chuyển phần dư sang bucket kỳ sau của cùng chủ sở hữu và loại nghĩa vụ.
- **Chốt thêm theo rounding policy:** tính một khoản điều chỉnh rõ ràng rồi kết chuyển.
- **Write-off được phép:** ghi nhận bỏ phần nghĩa vụ lẻ bằng một điều chỉnh có audit.
- **Giữ chờ xử lý:** chưa đóng hoàn toàn nếu chưa có điều kiện quyết định.

Ví dụ residual = 6.000, U = 10.000, policy cho phép chốt thành 1 minor:

~~~text
Adjustment thêm = +4.000 internal units
Posted tăng = 1 minor
Residual mới = 0

6.000 + 4.000 = 1 * 10.000
~~~

Nếu write-off residual = 2.000, adjustment là -2.000 và residual mới là 0. Không sửa giảm tổng phát sinh lịch sử để che khoản điều chỉnh.

Carry-forward cần một operation duy nhất liên kết bucket nguồn và đích. Giảm phần dư nguồn, ghi biến động chuyển và tăng giá trị nhận ở đích phải nhất quán; không vừa giữ residual ở nguồn vừa cộng ở đích.

Bucket đích cần ghi nhận phần carry-in có thể truy vết. Khi mở rộng schema, phương trình bảo toàn phải có thành phần carry-in/carry-out tương ứng hoặc coi chúng là các điều chỉnh chuyển có định danh, không giả làm phát sinh sử dụng mới.

## 9. Phân bổ tổng tiền đã chốt mà không mất minor unit

### 9.1. Vì sao chia đều rồi làm tròn không đủ?

Một tổng 1,00 cần phân cho ba dòng bằng nhau:

~~~text
Tính độc lập:
  0,333... -> 0,33
  0,333... -> 0,33
  0,333... -> 0,33
  Tổng = 0,99

Phân bổ đúng tổng:
  A = 0,34
  B = 0,33
  C = 0,33
  Tổng = 1,00
~~~

Phần 0,01 phải đi đâu là một quy tắc, không phải một chênh lệch được phép bỏ.

### 9.2. Phương pháp phần dư lớn nhất cho tổng không âm

Gọi T là tổng minor unit, w_i là trọng số không âm và W là tổng trọng số, W > 0:

~~~text
numerator_i = T * w_i
base_i = numerator_i div W
remainder_i = numerator_i mod W

K = T - sum(base_i)

Cộng thêm 1 minor cho K dòng có remainder lớn nhất.
Nếu remainder bằng nhau, dùng thứ tự khóa nghiệp vụ ổn định do server xác định.
~~~

Dùng phép nhân số nguyên đủ lớn để tránh tràn. Không chuyển sang double rồi sắp xếp theo phần thập phân gần đúng.

Ví dụ Java sau minh họa phép phân bổ, với tối đa 1.000 dòng:

~~~java
record WeightedLine(String stableId, long weight) {}
record Quota(String stableId, long base, BigInteger remainder) {}

static Map<String, Long> allocate(
        long totalMinor,
        List<WeightedLine> lines) {

    if (totalMinor < 0 || lines == null
            || lines.isEmpty() || lines.size() > 1_000) {
        throw new IllegalArgumentException("Invalid allocation");
    }

    Set<String> ids = new HashSet<>();
    BigInteger totalWeight = BigInteger.ZERO;
    for (WeightedLine line : lines) {
        if (line == null || line.stableId() == null
                || line.stableId().isBlank()
                || !ids.add(line.stableId()) || line.weight() < 0) {
            throw new IllegalArgumentException("Invalid line");
        }
        totalWeight = totalWeight.add(BigInteger.valueOf(line.weight()));
    }
    if (totalWeight.signum() == 0) {
        throw new IllegalArgumentException("Total weight must be positive");
    }

    List<Quota> quotas = new ArrayList<>();
    long baseSum = 0;
    for (WeightedLine line : lines) {
        BigInteger numerator = BigInteger.valueOf(totalMinor)
            .multiply(BigInteger.valueOf(line.weight()));
        BigInteger[] qr = numerator.divideAndRemainder(totalWeight);
        long base = qr[0].longValueExact();
        baseSum = Math.addExact(baseSum, base);
        quotas.add(new Quota(line.stableId(), base, qr[1]));
    }

    quotas.sort(
        Comparator.comparing(Quota::remainder).reversed()
            .thenComparing(Quota::stableId)
    );
    int extraCount = Math.toIntExact(
        Math.subtractExact(totalMinor, baseSum)
    );

    Map<String, Long> result = new LinkedHashMap<>();
    for (int i = 0; i < quotas.size(); i++) {
        Quota quota = quotas.get(i);
        long value = Math.addExact(
            quota.base(), i < extraCount ? 1L : 0L
        );
        result.put(quota.stableId(), value);
    }
    return result;
}
~~~

Các đoạn Java trong bài cần import tương ứng từ java.math và java.util, cùng một lớp bao ngoài nếu muốn chạy thành chương trình.

Hàm không kiểm tra quyền nhận tiền, giới hạn discount từng dòng hoặc độ dài ID theo hợp đồng API. Các điều kiện miền đó phải được xác minh trước khi phân bổ.

### 9.3. Bảo toàn tổng chưa đồng nghĩa chống chia nhỏ

Phương pháp trên bảo toàn T, nhưng một người có thể cố chia một dòng thành nhiều dòng để tăng cơ hội nhận phần dư. Vì vậy:

- Phạm vi và trọng số phải lấy từ dữ liệu có thẩm quyền.
- Các dòng thuộc cùng đối tượng kinh tế cần được gộp theo policy trước khi phân bổ nếu có yêu cầu.
- Khóa phá hòa phải ổn định và không do client tùy ý chọn chỉ để thắng phần lẻ.
- Snapshot phân bổ phải được lưu khi chốt.
- Retry hoặc đảo thứ tự JSON không được tính ra một người nhận khác.

Nếu phân bổ discount, còn cần ràng buộc discount của mỗi dòng không vượt số tiền đủ điều kiện. Nếu gặp giới hạn từng dòng, phải có thuật toán phân bổ lại đã định nghĩa, không đẩy phần còn lại cho bất kỳ dòng nào còn trống.

## 10. Capture một phần, hoàn tiền và điều chỉnh

Một giao dịch 1,00 đã phân bổ:

~~~text
A = 34 minor
B = 33 minor
C = 33 minor
~~~

Nếu hoàn lại dòng A, căn cứ là phần đã ghi nhận cho A và các khoản hoàn trước đó, không mặc định tính lại 100/3 rồi làm tròn thành 33.

Nếu hoàn toàn bộ ba dòng, tổng phải theo đúng quyền hoàn của giao dịch gốc. Không cho mỗi request tự làm tròn lên để tổng hoàn vượt khoản đã thu.

Các yêu cầu:

1. Refund hoặc capture từng phần phải tham chiếu nghĩa vụ và phần phân bổ gốc.
2. Cộng cả khoản đang chờ vào số tiền đã chiếm quyền hoàn/capture.
3. Phân bổ cho các phần phải dùng snapshot và policy đã xác định.
4. Mỗi thao tác có định danh nghiệp vụ chống lặp.
5. Số tiền, phần dư, trạng thái và bút toán phải thay đổi nguyên tử.

Điều chỉnh số âm cần chính sách riêng. Với phân bổ số âm, có thể phân bổ độ lớn không âm rồi đảo dấu theo hợp đồng đã định nghĩa; không đưa số âm vào thuật toán dành cho T >= 0 và mong rounding tự làm đúng.

Khi hủy một sự kiện tích lũy đã góp phần tạo payable, không chỉ trừ nó khỏi residual hiện tại. Số tiền đó có thể đã được kết chuyển. Cần operation đảo hoặc điều chỉnh theo provenance, đồng thời xét payable đã thu/chi và quyền hoàn.

## 11. Các đường lạm dụng do xử lý phần lẻ không nhất quán

### 11.1. Chia nhỏ để phí luôn thành 0

Nếu một nghĩa vụ phí được phép cộng theo hợp đồng nhưng endpoint làm tròn xuống mỗi request, nhiều request nhỏ có thể cùng tạo phí thanh toán bằng 0.

Điểm chặn là xác định phạm vi tính phí theo dữ liệu nghiệp vụ và giữ phần dư ở đúng phạm vi. Rate limit chỉ giảm tốc độ khai thác; nó không sửa được công thức hoặc phạm vi sai.

Phí tối thiểu, nếu có, phải là chính sách được công bố và chấp thuận. Không tự thêm phí tối thiểu vào mọi giao dịch để che một lỗi làm tròn.

### 11.2. Ghi nợ và ghi có từ hai cách tính khác nhau

Ví dụ không an toàn:

~~~text
Client yêu cầu 0,004.
Debit bị cắt về 0,00.
Credit hoặc điểm nhận được vẫn tính theo 0,004.
~~~

Khi hai vế dùng hai biểu diễn khác nhau, người dùng có thể nhận giá trị mà không chịu nghĩa vụ tương ứng.

Cách bảo vệ là chốt một monetary plan có thẩm quyền và sinh cả debit/credit từ plan đó. Nếu một vế nằm trong sổ có độ chính xác khác, cần phép quy đổi đơn vị rõ ràng cùng phần dư hoặc tài khoản điều chỉnh, không để sự khác biệt bị mất.

### 11.3. Dùng hiển thị 0,00 làm bằng chứng miễn phí

Một amount dương nhưng nhỏ có thể hiển thị thành 0,00. UI không được dùng chuỗi hiển thị đó để quyết định:

- Bỏ qua authorization.
- Giao hàng miễn phí.
- Đánh dấu đã thanh toán.
- Bỏ kiểm tra hạn mức.
- Xóa nghĩa vụ hoặc residual.

Nếu hệ thống cho phép miễn hoặc write-off khoản nhỏ, đó là một quyết định có thẩm quyền, tách khỏi thao tác format.

### 11.4. Lợi dụng chuyển đổi policy hoặc kết thúc tài khoản

Nếu mở lại tài khoản, đổi gói hoặc sang kỳ mới làm residual về 0, người dùng có thể chủ động reset nhiều lần để tránh nghĩa vụ.

Quy tắc xử lý phần dư phải gắn với chủ sở hữu và hợp đồng, có chuyển tiếp khi cần. Đóng tài khoản, chuyển quyền sở hữu hoặc gộp tài khoản cần một quy trình riêng, không cho phép kéo phần dư của người khác sang tài khoản đang thao tác.

### 11.5. Đổi thứ tự dòng để nhận phần dư

Khi thuật toán đưa minor unit cuối cho “dòng đầu tiên”, client có thể đảo danh sách để đổi người hưởng.

Khóa phá hòa phải do server xác định từ dữ liệu ổn định, và kết quả phân bổ được lưu. Không dùng thứ tự trong JSON, thời điểm thread chạy hoặc thứ tự trả về không được cam kết của database làm quyết định tiền.

## 12. Chuẩn hóa API, lưu trữ và định danh chống lặp

### 12.1. Hợp đồng dữ liệu phải nhất quán giữa các lớp

Một luồng cần kiểm tra xuyên suốt:

~~~text
HTTP input
  -> parse và kiểm tra miền giá trị
  -> kiểu dữ liệu tiền/đơn vị
  -> tính toán theo policy
  -> snapshot đã chốt
  -> database
  -> event/outbox
  -> adapter nhà cung cấp
  -> hiển thị
~~~

Lỗi thường gặp là server giữ 6 chữ số nhưng cột database chỉ giữ 2, hoặc event chuyển sang số thực rồi bên nhận parse lại. Mỗi ranh giới phải quy định đơn vị, scale và việc có được làm tròn hay không.

Không dựa vào việc database tự ép scale để thực thi rounding policy. Nếu amount không biểu diễn được theo schema, cần phát hiện trước và xử lý theo hợp đồng, thay vì để thao tác lưu quyết định số tiền.

Nếu event có số nguyên lớn, có thể dùng chuỗi số nguyên để tránh mất độ chính xác ở client không biểu diễn được toàn bộ miền. Định dạng và giới hạn phải được mô tả thống nhất.

### 12.2. Idempotency không chỉ là hash chuỗi amount

Nếu API cho phép 1,23 và 1,2300 cùng đại diện một ý định, fingerprint nghiệp vụ nên dùng biểu diễn chuẩn có thẩm quyền:

~~~text
currency
normalized minor hoặc internal units
quantum/scale policy
đối tượng và phiên bản nghĩa vụ
loại hành động
các tham số ảnh hưởng kết quả
~~~

Không biến amount thành double để chuẩn hóa. Nếu hợp đồng coi một khác biệt biểu diễn là khác payload, phải quy định rõ cách xử lý; không để các endpoint tự quyết trái nhau.

Với token hoặc thông điệp có chữ ký, xác minh đúng biểu diễn theo giao thức trước khi dùng nội dung. Không tự thay đổi payload ký rồi cho rằng chữ ký cũ vẫn có cùng ý nghĩa.

### 12.3. Hai lớp chống lặp bổ sung nhau

- **Idempotency key của request:** xử lý retry cùng ý định HTTP.
- **Định danh sự kiện hoặc nghĩa vụ:** ngăn cùng tác động nghiệp vụ bị khai lại bằng key mới.

Ví dụ sự kiện sử dụng E1 đã làm tăng bucket. Client retry E1 bằng key K2 vẫn không được cộng thêm. Ngược lại, E2 là sự kiện thực sự mới cần được áp dụng dù amount bằng E1.

Cùng event ID nhưng nội dung khác phải được phát hiện. Sửa một lần đo sai cần tạo adjustment liên kết E1, không sửa âm thầm bản ghi đã áp dụng.

Kết quả idempotency và thay đổi phần dư phải commit cùng nhau. Trước khi trả kết quả đã lưu, vẫn kiểm tra quyền xem đối tượng theo ngữ cảnh hiện tại.

### 12.4. Snapshot đã chốt không được tính lại khi replay

Ví dụ snapshot hóa đơn có:

~~~text
raw total
finalized total minor
rounding delta
allocation từng dòng
policy version
nguồn đầu vào và phiên bản
~~~

Sau khi snapshot có hiệu lực, retry, capture và refund phải dựa vào nó theo chính sách tương ứng. Không chạy lại với rounding mode mới rồi thay kết quả lịch sử.

Một quy trình sửa hóa đơn hoặc điều chỉnh có thể tạo phiên bản mới, nhưng cần quyền, lý do, trạng thái và bút toán liên kết. Nó không phải retry của phiên bản cũ.

## 13. Thanh toán bên ngoài và lỗi giữa các bước

Khi tổng payable đã được kết chuyển, việc gửi yêu cầu thanh toán là một bước tiếp theo. Không gộp “đã tính phí”, “đã lập nghĩa vụ” và “đã thu tiền” thành một trạng thái duy nhất.

Có thể có các trạng thái riêng cho nghĩa vụ thanh toán:

~~~text
PAYABLE -> PAYMENT_PENDING -> PAID
                      \-> UNKNOWN -> xác minh kết quả
                      \-> FAILED  -> retry theo cùng nghĩa vụ
~~~

Nếu request thu 2,00 đã tới nhà cung cấp rồi response bị mất:

- Không cộng lại 500 sự kiện vào bucket.
- Không tạo hóa đơn thứ hai cho cùng payable.
- Không kết luận khoản thu thất bại chỉ dựa vào timeout.
- Giữ định danh payment attempt và tra cứu hoặc retry theo hợp đồng nhà cung cấp.

Outbox giúp phát yêu cầu sau commit, nhưng có thể phát lại. Consumer phải deduplicate theo nghĩa vụ và operation, không chỉ dựa vào một event delivery ID.

Nếu adapter phát hiện amount payable nhỏ hơn mức tối thiểu của kênh, cần chính sách như giữ nghĩa vụ chờ gộp hoặc chọn kênh khác được phép. Không gửi amount = 0 rồi đánh dấu nghĩa vụ đã trả xong.

Gộp nhiều payable để thanh toán cần một payment group có liên kết tới các nghĩa vụ thành phần, bảo toàn tổng và xử lý thất bại nhất quán. Không đánh dấu tất cả đã thu khi mới tạo group.

## 14. Kiểm thử các bất biến và chuỗi thao tác

Các ví dụ sau dành cho môi trường thử nghiệm được kiểm soát. Chúng mô tả các kiểm tra cần có khi triển khai hệ thống, không yêu cầu chạy tấn công trên dịch vụ thật.

### 14.1. Ma trận kiểm thử

| Nhóm | Tình huống | Kết quả cần chứng minh |
| --- | --- | --- |
| Input | Chuyển 1,234 khi scale thanh toán là 2 | Từ chối, không tự giảm xuống 1,23 |
| Input | Gửi 1,2300 theo hợp đồng cho phép số 0 dư | Cùng giá trị có thẩm quyền với 1,23 |
| Input | 0,004 cho chuyển tiền, rồi cho sự kiện tích lũy hợp lệ | Validation khác nhau đúng loại thao tác |
| Input | Chuỗi quá dài, số mũ ngoài hợp đồng, sai currency | Từ chối có kiểm soát trước tính toán lớn |
| Quantum | Scale 2 nhưng amount không là bội số của quantum được phép | Từ chối thao tác không biểu diễn được |
| Rounding | 1,005 và -1,005 với các mode được hỗ trợ | Kết quả khớp policy, không nhầm DOWN và FLOOR |
| Rounding | 1,2449 qua nhiều lớp | Không vô tình chốt hai lần |
| Tích lũy | Ba sự kiện 4.000, U = 10.000 | Posted tăng tổng 1, residual = 2.000 |
| Tích lũy | 500 sự kiện 4.000 | Posted = 200, residual = 0 |
| Chia nhỏ | Một phát sinh và nhiều sự kiện con tương đương trong cùng phạm vi | Bảo toàn giá trị theo chính sách tổng hợp |
| Đồng thời | Residual 8.000, hai sự kiện 4.000 khác nhau | Posted tăng 1, residual cuối 6.000 |
| Retry | Cùng event nhiều lần, có thể khác HTTP key | Áp dụng đúng một lần |
| Conflict | Cùng event ID nhưng thay lượng sử dụng hoặc đơn giá | Không áp dụng payload mới âm thầm |
| Crash | Lỗi sau đổi residual, trước ghi payable | Rollback toàn bộ |
| Crash | Commit xong nhưng mất response | Retry trả kết quả đã ghi, không kết chuyển lần nữa |
| Phân bổ | T = 100, ba trọng số bằng nhau | 34/33/33 theo phá hòa ổn định, tổng 100 |
| Phân bổ | Đảo thứ tự input nhưng giữ nguyên dòng nghiệp vụ | Cùng kết quả theo stable ID |
| Phân bổ | T lớn, trọng số lớn | Không tràn số ở phép nhân hoặc cộng |
| Đóng kỳ | Sự kiện đến đồng thời CLOSING | Chỉ được áp dụng theo một nhánh policy, không mất sự kiện |
| Carry | Retry chuyển dư sang kỳ sau | Nguồn giảm và đích tăng đúng một lần |
| Hoàn tiền | Hoàn từng phần, có hai request đồng thời | Tổng thành công và pending không vượt quyền hoàn |
| Quyền | Client chọn bucket tenant khác hoặc residual account khác | Từ chối trước thay đổi dữ liệu |
| Policy | Đổi policy khi bucket đang hoạt động | Không reset residual hoặc sửa snapshot đã chốt |
| Provider | Timeout thu tiền rồi nhận kết quả thành công muộn | Không tính lại accrual hoặc thu lần hai |

Kiểm thử đồng thời cần transaction và kết nối database thực tế. Test chỉ gọi tuần tự hoặc mock một repository sẽ không chứng minh được các ràng buộc khóa và commit.

### 14.2. Thuộc tính cần kiểm tra cho mọi bước tích lũy

~~~text
oldResidual + newAccrual
    = newPayableMinor * U + newResidual

0 <= newResidual < U

Mỗi sự kiện được áp dụng tối đa một lần.
Tổng các payable tăng thêm khớp biến động bucket.
Không có dữ liệu của tenant khác bị thay đổi.
~~~

Với toàn bucket có điều chỉnh:

~~~text
accruedInternal + adjustmentInternal
    = postedMinor * U + residualInternal
~~~

Khi có carry-in/carry-out, mở rộng phương trình theo mô hình dữ liệu đã chọn và kiểm tra cả hai đầu.

### 14.3. Thuộc tính của phân bổ

~~~text
Tất cả phần phân bổ đều là số nguyên minor.
Tất cả phần đều không âm trong mô hình không âm.
Tổng các phần bằng T.
Cùng snapshot và policy cho cùng kết quả.
Nếu W > 0, từng phần là floor(quota) hoặc ceil(quota).
~~~

Nếu hợp đồng cho phép thay đổi thứ tự nhận phần dư theo từng kỳ để chia công bằng, lịch đó cũng phải được xác định và lưu. Không dùng sự ngẫu nhiên không truy vết khi replay một snapshot.

### 14.4. Kiểm thử sinh chuỗi hành động

Có thể sinh các chuỗi:

~~~text
accrue -> retry -> accrue -> close -> carry -> retry carry
allocate -> capture một phần -> retry -> refund một phần
policy change -> accrue -> adjustment -> close
payment timeout -> lookup -> webhook -> retry
~~~

Sau mỗi bước, kiểm tra bất biến và quyền theo đối tượng. Chú ý điểm ngay trước/sau commit, vì đây là nơi các lỗi lặp và mất phần dư dễ xuất hiện.

Nếu đọc nhiều bảng để đối soát, dùng snapshot nhất quán hoặc chờ các thao tác liên quan ổn định. Đọc số tổng hợp trước commit rồi đọc journal sau commit có thể tạo báo động giả.

## 15. Audit, đối soát và vận hành

Một kết quả tiền cần truy được về:

~~~text
Nguồn sử dụng hoặc nghĩa vụ
  -> giá trị tính toán và đơn vị
  -> phạm vi tổng hợp
  -> policy version
  -> phần payable và phần dư
  -> allocation hoặc adjustment
  -> bút toán
  -> payment/refund liên quan
~~~

Nên lưu các dữ liệu đủ để giải thích: tenant, chủ thể/dịch vụ, hợp đồng, bucket, source event ID, raw amount hoặc internal units, U, residual trước/sau, payable tăng thêm, snapshot phân bổ và lý do điều chỉnh.

Không ghi bí mật xác thực hoặc dữ liệu thanh toán nhạy cảm vào log. Dữ liệu audit tài chính cần quyền xem thích hợp; log ứng dụng chung không thay thế sổ biến động có thể đối soát.

Theo dõi các dấu hiệu:

- Nhiều giao dịch nằm ngay dưới bước làm tròn hoặc ngưỡng miễn phí.
- Tăng số bucket hoặc lần mở/đóng hợp đồng của cùng chủ thể.
- Residual âm, residual >= U hoặc sai phương trình bảo toàn.
- Khoản điều chỉnh rounding tăng bất thường theo khách hàng hoặc nhân viên.
- Tăng conflict event/idempotency hoặc nhiều key cho cùng nghĩa vụ.
- Phân bổ không khớp tổng, payable không có nguồn hoặc nguồn bị áp dụng lặp.
- Payment UNKNOWN kéo dài hoặc nhiều payable bị đánh dấu hoàn tất bằng amount 0.

Không tự cộng/trừ số dư để “làm cho bảng khớp” dựa trên một lần đọc. Điều chỉnh phải xác định nguồn có thẩm quyền, nguyên nhân, quyền và bút toán liên kết.

Thay đổi rounding mode, quantum, scale, phạm vi gộp hoặc cách xử lý cuối kỳ đều có thể ảnh hưởng tiền. Cần quản lý phiên bản, thời điểm hiệu lực và quy trình phê duyệt phù hợp; không coi đó chỉ là thay đổi định dạng giao diện.

## 16. Tiêu chí hoàn thành thiết kế

Trước khi cho một luồng xử lý fractional amount có hiệu lực, cần trả lời rõ:

1. Đầu vào nào phải biểu diễn chính xác và đầu vào nào được phép có phần lẻ nội bộ?
2. Currency, quantum, scale và đơn vị của từng trường được xác định ở đâu?
3. Phạm vi cộng gộp là dòng, hóa đơn, hợp đồng hay kỳ; người dùng có điều khiển được không?
4. Điểm làm tròn và mode nào có thẩm quyền?
5. Phần dư thuộc về ai, được lưu ở đâu và xử lý thế nào khi đóng kỳ hoặc đổi hợp đồng?
6. Transaction nào bảo vệ residual, payable, event và bút toán khỏi lặp hoặc mất cập nhật?
7. Cách nào ngăn cùng tác động được thực hiện bằng event ID hoặc idempotency key mới?
8. Allocation có bảo toàn tổng, phá hòa ổn định và được lưu làm snapshot không?
9. Capture/refund từng phần có giới hạn theo quyền gốc và tính cả phần đang chờ không?
10. Có thể đối soát từ từng minor unit đã kết chuyển về nguồn phát sinh và phần dư còn giữ không?

Phần tiền chưa đủ một đơn vị thanh toán vẫn cần một quy tắc có thể giải thích. Khi đơn vị, chủ sở hữu, phạm vi tổng hợp và số lần thực thi đều được bảo vệ, hệ thống mới ngăn được việc biến những chênh lệch nhỏ thành lạm dụng nghiệp vụ.
