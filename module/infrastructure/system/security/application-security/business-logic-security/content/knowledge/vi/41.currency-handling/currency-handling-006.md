# Nhất quán hiển thị tiền tệ — Currency display consistency

## 1. Hiển thị tiền là một phần của tính đúng đắn nghiệp vụ

Trong chương **Currency Handling**, currency display consistency là việc mọi nơi trình bày một khoản tiền đều giữ đúng **giá trị, loại tiền, đơn vị và ý nghĩa nghiệp vụ** của khoản tiền đó. Dấu phân cách, ngôn ngữ và vị trí ký hiệu có thể thay đổi theo locale; số tiền thực sự được xác nhận, thu hoặc hoàn phải nhất quán với dữ liệu có thẩm quyền.

Ví dụ, với cùng khoản tiền có giá trị 1.234,56 USD:

| Cách trình bày minh họa | Ý nghĩa |
| --- | --- |
| `1,234.56 USD` theo cách viết en-US | Một nghìn hai trăm ba mươi tư USD và 56 cent |
| `1.234,56 USD` theo cách viết vi-VN | Cùng giá trị và loại tiền |
| `1.234,56 VND` | Một loại tiền khác; không phải chỉ đổi locale |
| `123.456 USD` khi đọc nhầm dấu phân cách | Có thể bị hiểu thành một giá trị khác |

Các ví dụ trong bài ưu tiên mã ISO để làm rõ đơn vị. Chuỗi thực tế do thư viện định dạng sinh ra có thể có ký hiệu, khoảng trắng hoặc vị trí mã khác nhau tùy dữ liệu locale và phiên bản runtime.

Một lỗi hiển thị có thể dẫn tới hậu quả nghiệp vụ:

- Khách thấy tổng tiền bằng một loại tiền nhưng bị thu bằng loại tiền khác.
- Người duyệt tưởng một khoản chi nhỏ vì phần thập phân hoặc đơn vị bị che.
- API hoàn tiền phân tích lại chuỗi đã định dạng và hoàn sai số tiền.
- Một bản báo giá cũ còn trên màn hình trong khi request xác nhận dùng bản mới.
- Biên nhận hoặc báo cáo gắn số tiền của giao dịch này với ký hiệu của giao dịch khác.

Trong phạm vi bảo mật logic nghiệp vụ, mục tiêu là bảo vệ cặp tiền và đối tượng mà người dùng hoặc người duyệt xác nhận, đồng thời ngăn dữ liệu trình bày trở thành đường sửa số tiền, đổi tiền tệ hoặc vượt bước phê duyệt.

## 2. Bất biến cần giữ từ báo giá đến biên nhận

Một khoản tiền có thẩm quyền tối thiểu gồm:

```text
Money = (amountMinor, currency, unitScale)

Giá trị thập phân = amountMinor × 10^(-unitScale)

Ví dụ:
    (123456, USD, 2) → 1234.56 USD
    (123456, VND, 0) → 123456 VND
```

`unitScale` mô tả cách diễn giải đơn vị lưu trữ trong hợp đồng dữ liệu. Nó phải đến từ metadata hoặc snapshot do server kiểm soát, không phải lựa chọn tùy ý của client. Không mặc định mọi khoản tiền đều có hai chữ số thập phân.

Các bất biến quan trọng:

1. Số tiền và loại tiền của một thành phần hiển thị phải đến từ cùng một đối tượng và cùng phiên bản dữ liệu.
2. Đổi locale chỉ đổi cách trình bày, không đổi `amountMinor`, `currency` hoặc `unitScale`.
3. Tiền được xác nhận phải khớp snapshot có thẩm quyền mà thao tác xác nhận tham chiếu.
4. Thay đổi khoản thu, phí hoặc loại tiền có ý nghĩa với phê duyệt phải đi qua bước xác nhận/phê duyệt lại theo chính sách.
5. Dữ liệu thực tế gửi tới nhà cung cấp và kết quả được ghi nhận phải khớp payment intent đã chốt.
6. Biên nhận và lịch sử lấy từ giao dịch thực tế, không tính lại bằng giỏ hàng hay tỷ giá hiện tại.

“Nhất quán” không yêu cầu mọi màn hình có chuỗi giống hệt nhau. Một email tiếng Anh và màn hình tiếng Việt có thể dùng dấu phân cách khác nhau, nhưng phải giải thích cùng money tuple và cùng loại nghiệp vụ.

## 3. Tách dữ liệu tiền khỏi chuỗi trình bày

### 3.1. Hợp đồng dữ liệu có cấu trúc

Một response báo giá minh họa:

```json
{
  "quoteId": "quote-421",
  "version": 7,
  "charge": {
    "amountMinor": "1050",
    "currency": "USD",
    "unitScale": 2
  },
  "breakdown": {
    "subtotalMinor": "1000",
    "feeMinor": "50"
  },
  "pricingPolicyVersion": "pricing-v3",
  "moneyMetadataVersion": "money-metadata-v2"
}
```

Trong ví dụ, subtotal và fee cùng currency/scale với `charge` theo hợp đồng của response. Nếu các thành phần có loại tiền khác nhau, phải có đối tượng Money riêng và quy tắc chuyển đổi rõ ràng; không cộng các số nguyên khác đơn vị.

`amountMinor` được truyền dưới dạng chuỗi số nguyên để các tầng không vô tình làm mất độ chính xác khi dùng kiểu số có giới hạn. Client phải dùng cách biểu diễn số chính xác tương ứng, không chuyển chuỗi sang số dấu phẩy động rồi mặc định giá trị vẫn nguyên vẹn. Dữ liệu có cấu trúc vẫn phải được kiểm tra kiểu, miền giá trị và kích thước khi tiếp nhận.

Có thể bổ sung chuỗi trình bày do server tạo, nhưng chuỗi đó phải đi cùng đúng snapshot và locale. Nó không thay thế các trường Money trong giao thức máy và không được dùng làm số tiền có thẩm quyền cho API thanh toán.

### 3.2. Không phân tích ngược chuỗi hiển thị để tạo giao dịch

Những luồng sau dễ gây lỗi:

```text
"1.234,56 USD"
    → bỏ dấu chấm/phẩy theo giả định
    → parseDouble
    → gửi amount lên API hoàn tiền

"$100.00"
    → đoán USD từ ký hiệu $
    → tạo payment
```

Các dấu phân cách thay đổi theo locale; ký hiệu có thể dùng cho nhiều tiền tệ; khoảng trắng Unicode và cách biểu diễn số âm cũng khác nhau. Chuỗi dùng cho con người không phải hợp đồng lưu trữ tiền.

API hoàn tiền nên nhận danh tính payment và số tiền trong biểu diễn được quy định rõ, hoặc một lệnh hoàn toàn bộ có phạm vi hẹp. Server lấy currency từ payment gốc, kiểm tra quyền, trạng thái, phần còn được hoàn và tính nguyên tử của thao tác.

Nếu sản phẩm cần cho người dùng nhập tiền, đó là một luồng **nhập liệu** riêng: công bố locale/quy ước, phân tích nghiêm ngặt, kiểm tra miền giá trị và hiển thị lại kết quả chuẩn hóa trước xác nhận khi cần. Không dùng một bộ parse đoán nhiều locale cho chuỗi được copy từ bất kỳ màn hình nào.

## 4. Locale, mã tiền và vai trò tiền tệ

### 4.1. Locale không cấp quyền đổi loại tiền

Locale quyết định những chi tiết như dấu phân cách, chữ số, vị trí ký hiệu và cách biểu diễn âm. Currency xác định đơn vị tiền. Hai tham số phải được truyền riêng cho bộ định dạng.

Một người dùng xem ứng dụng bằng tiếng Việt vẫn có thể đang thanh toán USD. Không dùng `Locale.getDefault()` hoặc ngôn ngữ trình duyệt để suy lại currency của đơn hàng. Danh sách locale giao diện cũng không phải allowlist tiền tệ được phép thanh toán.

### 4.2. Ký hiệu cần đủ rõ tại điểm quyết định

Chỉ ghi `$` có thể mơ hồ trong hệ thống hỗ trợ nhiều loại dollar. Tại màn hình xác nhận, phê duyệt, hoàn tiền hoặc biên nhận, nên có mã tiền tệ rõ ràng như `USD`, `CAD` hoặc tên đầy đủ phù hợp ngữ cảnh. Mã phải gắn với khoản tiền, không nằm ở một góc trang dễ bị bỏ qua.

Unicode CLDR mô tả định dạng tiền theo locale và cách kết hợp ký hiệu với mã ISO để xử lý sự mơ hồ. Việc thêm mã rõ ràng có thể giữ nguyên cách viết số bản địa. Xem [Unicode TR35: Numbers — Currency Formats](https://www.unicode.org/reports/tr35/tr35-numbers.html).

Ví dụ bố cục xác nhận:

```text
Hàng hóa:                10,00 USD
Phí người mua trả:        0,50 USD
Tổng tiền sẽ thu:        10,50 USD

[Xác nhận thanh toán 10,50 USD]
```

Các giá trị trên đến từ cùng một snapshot. Tên nút, phần tổng tiền, nội dung hỗ trợ tiếp cận và request xác nhận phải cùng tham chiếu snapshot đó.

### 4.3. Phân biệt tiền thu, tiền ước tính và tiền quyết toán

| Loại thông tin | Cần nói rõ điều gì? |
| --- | --- |
| Charge currency | Khách thực sự được yêu cầu thanh toán bằng loại tiền nào |
| Display conversion | Khoản quy đổi hiển thị là ước tính hay báo giá được cam kết |
| Settlement currency | Đơn vị quyết toán với merchant hoặc nhà cung cấp |
| Reporting currency | Đơn vị quy đổi dùng cho báo cáo |

Ví dụ với tỷ giá **giả định chỉ để minh họa** là 25.000 VND/USD:

```text
Tổng tiền sẽ thu:       10,50 USD
Ước tính quy đổi:      262.500 VND
Tỷ giá minh họa:       25.000 VND cho 1 USD
```

Khoản ước tính phải được gắn nhãn là ước tính và đứng riêng với khoản thu thực tế. Nếu sản phẩm thật sự chuyển sang thu VND, cần một báo giá VND có thẩm quyền, chính sách phí, hạn dùng và xác nhận tương ứng. Không thay nhãn USD bằng VND trên cùng số tiền rồi coi là đã đổi tiền.

Không hiển thị số tiền merchant nhận sau phí như thể đó là tổng tiền khách phải trả. Cùng một giao dịch có thể có nhiều khoản tiền hợp lệ; mỗi khoản cần nhãn về vai trò và đối tượng chịu phí.

## 5. Làm tròn và độ chính xác phải có chủ sở hữu

### 5.1. Formatter không quyết định giá thanh toán

Bộ định dạng có thể làm tròn theo số chữ số được cấu hình. Nếu màn hình làm tròn tổng 10,49 USD thành 10 USD còn server thu 10,49 USD, chuỗi hiển thị đã không phản ánh đủ khoản được xác nhận.

Tại điểm xác nhận hoặc phê duyệt, hiển thị đầy đủ độ chính xác mà nghiệp vụ thực sự thu/chi. Cách viết gọn như `1,2 triệu` hoặc `1.2K` chỉ phù hợp khi ngữ cảnh cho phép ước lượng; cần có giá trị đầy đủ tại nơi ra quyết định.

ECMA-402 định nghĩa các tham số định dạng và số chữ số tiền tệ của `Intl.NumberFormat`. Giá trị mặc định của một formatter không phải chính sách định giá của ứng dụng. Khi triển khai trên trình duyệt, phải cấu hình định dạng theo hợp đồng tiền và kiểm chứng trên các runtime được hỗ trợ. Xem [ECMA-402: NumberFormat Objects](https://tc39.es/ecma402/2026/#numberformat-objects).

### 5.2. Các dòng tiền và tổng tiền cần khớp

Giá sản phẩm nội bộ, thuế hoặc tỷ giá có thể có độ chính xác cao hơn khoản thu cuối. Chính sách định giá cần quyết định làm tròn ở từng dòng hay sau khi cộng, rồi xuất breakdown có thẩm quyền.

Không để frontend tự làm tròn từng dòng trong khi backend làm tròn tổng theo cách khác. Một màn hình có các dòng trông cộng thành 10,50 USD nhưng tổng ghi 10,51 USD cần được giải thích bằng quy tắc và khoản điều chỉnh hợp lệ, không bằng dòng “bù chênh lệch” tùy ý.

Luồng an toàn hơn là server tính giá và phí theo chính sách có phiên bản, tạo snapshot các dòng cùng tổng, rồi các kênh chỉ định dạng dữ liệu đó. Nếu có làm tròn tiền mặt theo phương thức thanh toán, phải phân biệt khoản điều chỉnh ấy với lỗi định dạng và đưa nó vào tổng được xác nhận.

### 5.3. Dữ liệu lịch sử giữ nguyên đơn vị

Không đọc số nguyên của một payment cũ rồi áp đơn vị lưu trữ mới từ cấu hình toàn cục. Lưu metadata cần thiết hoặc tham chiếu phiên bản bất biến để đọc đúng khoản tiền lịch sử.

Thay đổi bản dịch, dấu phân cách hoặc cách đặt ký hiệu có thể chỉ thay hình thức. Thay scale, currency hoặc quy tắc định giá làm thay ý nghĩa tiền và phải được quản lý ở tầng nghiệp vụ.

## 6. Ví dụ Java: định dạng từ Money snapshot

Ví dụ Java 17 dưới đây nhận số nguyên đơn vị nhỏ nhất và scale từ snapshot. Hàm định dạng chỉ làm nhiệm vụ trình bày; việc chọn currency, tính giá và kiểm tra quyền đã thuộc luồng nghiệp vụ trước đó.

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;
import java.util.Objects;

final class MoneyDisplay {
    record MoneySnapshot(
        BigInteger amountMinor,
        String currency,
        int unitScale
    ) {
        MoneySnapshot {
            Objects.requireNonNull(amountMinor);
            Objects.requireNonNull(currency);

            if (!currency.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException("INVALID_CURRENCY_CODE");
            }
            // Miền giá trị của sản phẩm minh họa, không phải mọi hệ thống.
            if (unitScale < 0 || unitScale > 9
                    || amountMinor.abs().toString().length() > 30) {
                throw new IllegalArgumentException("INVALID_MONEY_RANGE");
            }
        }
    }

    static String formatExact(MoneySnapshot money, Locale displayLocale) {
        Objects.requireNonNull(money);
        Objects.requireNonNull(displayLocale);

        BigDecimal value = new BigDecimal(
            money.amountMinor(), money.unitScale()
        );

        NumberFormat candidate = NumberFormat.getCurrencyInstance(displayLocale);
        if (!(candidate instanceof DecimalFormat format)) {
            throw new IllegalStateException("UNSUPPORTED_FORMAT_PROVIDER");
        }

        format.setCurrency(Currency.getInstance(money.currency()));
        format.setMinimumFractionDigits(money.unitScale());
        format.setMaximumFractionDigits(money.unitScale());
        format.setMaximumIntegerDigits(30);
        format.setRoundingMode(RoundingMode.UNNECESSARY);
        format.setGroupingUsed(true);

        return format.format(value) + " [" + money.currency() + "]";
    }
}
```

Cách gọi minh họa:

```java
var money = new MoneyDisplay.MoneySnapshot(
    new BigInteger("123456"), "USD", 2
);

String vi = MoneyDisplay.formatExact(money, Locale.forLanguageTag("vi-VN"));
String en = MoneyDisplay.formatExact(money, Locale.US);
```

Hai chuỗi có thể khác ký hiệu và dấu phân cách, nhưng cùng biểu diễn 1.234,56 USD. Mã ISO được thêm vào để không phụ thuộc riêng vào ký hiệu mà locale lựa chọn. Cách kết hợp mã và ký hiệu trong giao diện thực tế có thể được thiết kế phù hợp bố cục và thư viện locale.

Những điểm cần giữ khi áp dụng:

- Tạo `BigDecimal` trực tiếp từ số nguyên và scale; không đi qua `double`.
- Đặt currency và số chữ số thập phân một cách tường minh từ snapshot đã được kiểm soát.
- Tạo formatter cho từng lần gọi để không chia sẻ trạng thái mutable giữa các request.
- Dùng `DecimalFormat` để định dạng trực tiếp `BigDecimal`; ví dụ từ chối provider khác thay vì giả định mọi `NumberFormat` đều có cùng khả năng.
- `UNNECESSARY` giúp phát hiện trường hợp cần làm tròn ngoài hợp đồng của hàm này; nó không thay thế chính sách làm tròn của bước định giá.
- Giới hạn 30 chữ số và scale 0..9 là lựa chọn cho ví dụ; production phải thống nhất với hợp đồng dữ liệu và giới hạn sản phẩm.

Trong Java, `setCurrency` không tự cập nhật giới hạn chữ số phần thập phân. `NumberFormat` cũng không được bảo đảm dùng đồng thời an toàn khi chia sẻ mà không đồng bộ. Xem [tài liệu Java SE 21 về NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html).

Hàm không chứng minh currency được phép thanh toán hoặc scale đúng nghiệp vụ: caller phải cung cấp snapshot có thẩm quyền. Nếu mã tiền lịch sử không được runtime định dạng hỗ trợ, cần đường hiển thị đã kiểm chứng giữ số thập phân chính xác và mã gốc, hoặc thông báo không thể định dạng. Không thay sang một currency khác cho thuận tiện.

Đối với frontend, cần kiểm chứng thư viện có thể nhận và giữ chính xác biểu diễn số mà API cung cấp. Không chuyển một số nguyên rất lớn sang kiểu số không đủ chính xác chỉ để gọi formatter. Một bộ định dạng chạy được không có nghĩa là dữ liệu đầu vào đã được giữ nguyên.

## 7. Bảo vệ phiên bản mà người dùng xác nhận

### 7.1. Một phiên bản cho một lần xác nhận

Giả sử màn hình đã hiển thị báo giá `quote-421/version=7` với tổng 10,50 USD. Sau đó phí được cập nhật và server tạo phiên bản 8 với tổng 11,00 USD. Nếu nút xác nhận vẫn hiển thị 10,50 nhưng request lấy phiên bản mới nhất ngầm định, người dùng sẽ xác nhận và bị thu hai khoản khác nhau.

Một API xác nhận hẹp có thể nhận:

```http
POST /orders/order-123/confirm-payment
Idempotency-Key: confirmation-key
Content-Type: application/json

{
  "quoteId": "quote-421",
  "expectedQuoteVersion": 7
}
```

Server cần tra quote trong phạm vi caller được phép, kiểm tra liên kết với đơn hàng, hạn dùng, trạng thái và phiên bản hiện hành. Nếu phiên bản 7 không còn được chấp nhận, trả xung đột/yêu cầu lấy báo giá mới theo hợp đồng, để giao diện trình bày lại và yêu cầu xác nhận.

Không tự thay sang phiên bản 8 rồi vẫn dùng lần bấm của phiên bản 7 làm sự chấp thuận cho số tiền mới. Nếu chính sách cho phép giữ giá cũ trong thời hạn, phiên bản 7 phải vẫn là một snapshot có hiệu lực được server xác nhận, không phải dữ liệu do client tự gửi lại.

### 7.2. Luồng transaction minh họa

```text
+ Nhận quoteId + expectedVersion + idempotency key
+ Xác thực caller và xác định tenant từ nguồn tin cậy
+
+ BEGIN
+   Claim khóa idempotency trong phạm vi thao tác
+   Nếu đã có kết quả: kiểm tra quyền, trả đúng kết quả cũ
+
+   Khóa/kiểm soát phiên bản đối tượng báo giá và đơn hàng
+   Kiểm tra sở hữu, trạng thái, hạn dùng, phê duyệt
+   Kiểm tra expectedVersion theo chính sách xác nhận
+
+   Lấy amount/currency/scale và breakdown từ snapshot
+   Kiểm tra chính sách tiền tệ và route tại điểm hiệu lực
+   Tạo payment intent gắn với snapshot bất biến
+   Ghi outbox và kết quả idempotency
+ COMMIT
+
+ Worker gửi khoản tiền của payment intent tới nhà cung cấp
```

Transaction bảo vệ thay đổi cục bộ; lời gọi nhà cung cấp cần cơ chế idempotency và xử lý kết quả riêng. Một thay đổi UI sau commit không được làm worker đọc lại giá mới từ giỏ hàng để thay khoản thu.

Fingerprint cho xác nhận cần ràng buộc command với đúng quote, phiên bản, đơn hàng và đối tượng liên quan. Nếu API nhận money tuple thì tuple đã chuẩn hóa cũng phải được ràng buộc và so khớp nguồn có thẩm quyền. Không băm riêng chuỗi `10,50 USD` làm danh tính khoản tiền: đổi locale có thể đổi chuỗi dù giá trị không đổi.

### 7.3. Chấp thuận và bằng chứng

Có thể lưu quote ID/phiên bản, money tuple, breakdown có ý nghĩa, người xác nhận, người duyệt khi cần, thời điểm và phiên bản chính sách. Bằng chứng này giúp giải thích quyết định đã được chấp nhận.

Server không thể chỉ từ một request khẳng định người dùng thật sự đã đọc đúng mọi pixel trên trình duyệt. Mục tiêu kỹ thuật là ràng buộc hành động với dữ liệu có thẩm quyền và thiết kế giao diện đáng tin cậy trên các client được hỗ trợ. Ảnh chụp màn hình hoặc trường `displayedTotal` do client tự khai không thay thế kiểm tra đó.

Nếu dùng báo giá có chữ ký, server vẫn phải kiểm tra phạm vi chủ thể, hạn dùng, trạng thái và chính sách chống dùng lại. Chữ ký không tự ngăn một quote hợp lệ được dùng sai đơn hàng hoặc được xác nhận nhiều lần.

## 8. Nhất quán giữa các kênh và các thời điểm

| Điểm trình bày | Nguồn dữ liệu nên dùng | Điều phải làm rõ |
| --- | --- | --- |
| Danh sách sản phẩm | Giá niêm yết hoặc dữ liệu giá có phiên bản | Giá cơ bản hay giá đã gồm phí/thuế |
| Giỏ hàng | Snapshot tính giá hiện hành | Có phải giá tạm tính, còn có thể thay đổi không |
| Màn hình xác nhận | Báo giá có hiệu lực được xác nhận | Tổng tiền thực thu, currency và phí |
| Màn hình phê duyệt | Nội dung cần phê duyệt có phiên bản | Đối tượng, khoản tiền và quyền quyết định |
| Payment intent/nhà cung cấp | Money tuple đã chốt | Tuyến và đơn vị tiền của adapter |
| Biên nhận | Payment thực tế được ghi nhận | Thu/hoàn bao nhiêu, bằng currency nào |
| Báo cáo | Dữ liệu giao dịch và quy tắc báo cáo | Tiền giao dịch hay tiền quy đổi, mốc tỷ giá |

Không bắt giá ở danh sách sản phẩm luôn bằng tổng xác nhận nếu có thêm phí hoặc thay đổi cấu hình hợp lệ. Cần trình bày rõ bước chuyển và yêu cầu xác nhận ở điểm có đầy đủ thông tin. Bất biến bị vi phạm khi thông tin có ý nghĩa thay đổi ngầm mà hành động cũ vẫn được dùng cho khoản tiền mới.

### 8.1. Đối chiếu với nhà cung cấp

Trước khi gửi yêu cầu, adapter phải ánh xạ money tuple sang đúng currency và đơn vị mà tuyến nhà cung cấp yêu cầu. Lỗi nhân/chia scale không được giải quyết bằng cách sửa chuỗi hiển thị để giống số đã gửi sai.

Khi nhận callback hoặc tra cứu kết quả, cần xác thực nguồn rồi đối chiếu payment ID, merchant, amount và currency với payment intent tương ứng. Một callback có chữ ký nhưng sai currency không được tự biến payment thành `PAID`.

Nếu kết quả không khớp, lưu bằng chứng và đưa vào luồng xử lý ngoại lệ/đối soát. Không bỏ qua khoản tiền bên ngoài có thể đã phát sinh, cũng không tự sửa currency của payment intent cho khớp callback.

### 8.2. Biên nhận và hoàn tiền

Biên nhận lấy số tiền đã thu hoặc hoàn từ dữ liệu giao dịch, không dựng lại từ giá hiện tại của sản phẩm. Đổi ngôn ngữ có thể định dạng lại khoản tiền lịch sử, nhưng không tính lại tỷ giá hoặc phí để thay giá trị gốc.

Một khoản hoàn cần nhãn rõ, ví dụ `Số tiền hoàn: 10,50 USD`. Nếu màn hình dùng số có dấu, cần quy ước nhất quán với loại thông tin đang xem: dòng biến động số dư khác cách biểu diễn một lệnh hoàn với amount dương. Không bỏ dấu âm bằng `abs()` chỉ để giao diện trông đồng đều.

Refund giữ currency của payment gốc theo hợp đồng nghiệp vụ. Nếu sản phẩm có một nghiệp vụ chi trả khác currency, phải thể hiện riêng với quy tắc chuyển đổi và phê duyệt tương ứng, không ghi như một khoản hoàn nguyên trạng.

## 9. Frontend, cache và trạng thái dùng chung

### 9.1. Tránh trộn dữ liệu từ hai response

Một race trên giao diện có thể xảy ra khi người dùng đổi tiền tệ hoặc số lượng nhanh:

```text
+ Gửi request A lấy quote USD phiên bản cũ
+ Gửi request B lấy quote VND phiên bản mới
+ B trả trước: cập nhật nhãn VND và tổng tiền mới
+ A trả sau: ghi đè riêng phần số tiền bằng giá USD cũ
+ Màn hình hiện số tiền từ A kèm currency từ B
```

Giao diện nên coi quote là một đối tượng bất biến và cập nhật đồng thời tổng tiền, currency, breakdown, phiên bản cùng trạng thái nút xác nhận. Bỏ qua response không còn thuộc lựa chọn hiện hành; có thể hủy request cũ để giảm công việc nhưng vẫn cần kiểm tra response/version.

Nếu chưa có một quote nhất quán, không bật nút xác nhận với dữ liệu chắp vá. Server vẫn phải kiểm tra phiên bản vì mọi kiểm soát frontend đều có thể bị bỏ qua hoặc gặp client cũ.

### 9.2. Cache không được làm lẫn khoản tiền hoặc người xem

Khóa cache chuỗi hiển thị cần gắn với dữ liệu nguồn và cấu hình thực sự ảnh hưởng, ví dụ tenant/phạm vi dữ liệu, quote hoặc payment ID, phiên bản, locale và phiên bản trình bày. Nếu cache theo giá trị thay vì ID, phải có đầy đủ amount, currency và scale.

Không cache riêng chuỗi số rồi ghép với currency lấy từ trạng thái khác. Không dùng cache chỉ theo `productId` nếu sản phẩm có nhiều bảng giá hoặc loại tiền theo cửa hàng.

Cache hoặc CDN chứa giá trị riêng tư cần tuân thủ quyền truy cập tương ứng. Một chuỗi tiền đúng về định dạng vẫn là lộ dữ liệu nếu được trả nhầm cho người không có quyền xem đơn hàng.

### 9.3. Không chia sẻ formatter mutable tùy ý

Một singleton formatter bị request A đặt currency là USD, request B đặt VND rồi request A gọi format có thể sinh nhãn sai. Các thuộc tính số chữ số và rounding cũng có thể bị lẫn.

Tạo formatter theo request/lần gọi hoặc dùng cơ chế lưu trữ/đồng bộ phù hợp đã được kiểm chứng. Một thiết kế cache formatter cần bảo đảm đối tượng không bị caller sửa và khóa cache có đủ tham số, không chỉ locale.

### 9.4. Không lấy tiền có thẩm quyền từ DOM hoặc storage của trình duyệt

Giá trị nằm trong text node, hidden input hoặc `localStorage` đều có thể bị thay đổi. API cần tham chiếu dữ liệu server và kiểm tra nhất quán, không nhận `totalFormatted` như một bằng chứng số tiền.

Render chuỗi tiền và nhãn bằng cơ chế text/escaping phù hợp. Metadata hiển thị do merchant cung cấp không được phép chèn HTML để che đơn vị, chèn số khác hoặc sửa cấu trúc màn hình xác nhận. Tên tiền và mã chuẩn dùng tại điểm quyết định nên lấy từ nguồn đã kiểm soát.

## 10. Bố cục, khả năng tiếp cận và dấu của khoản tiền

### 10.1. Không làm mất đơn vị ở màn hình nhỏ

Trên mobile, zoom lớn hoặc bảng có cột hẹp, currency và dấu âm có thể bị cắt trong khi phần số vẫn còn. Tại điểm xác nhận, không dùng ellipsis khiến `10,50 USD` chỉ còn `10,50`, hoặc khiến khoản âm trông như khoản dương.

Nên giữ số tiền và đơn vị như một nhóm thông tin, cho xuống dòng có chủ ý khi cần và kiểm tra cả giá trị dài. Tooltip có thể bổ sung chi tiết nhưng không nên là nơi duy nhất thể hiện currency hoặc phần thập phân của khoản được xác nhận.

Màu xanh/đỏ không đủ diễn tả thu, chi hoặc hoàn. Cần nhãn và cách biểu diễn dấu rõ ràng. Nếu dùng dạng kế toán có ngoặc cho số âm, phải bảo đảm ngữ cảnh và cách đọc hỗ trợ tiếp cận không làm mất ý nghĩa đó.

### 10.2. Nội dung nhìn thấy và nội dung được đọc phải cùng khoản tiền

Một nút có chữ `Thanh toán 10,50 USD` nhưng `aria-label` vẫn ghi `Thanh toán 10 USD` tạo hai cách hiểu. Nội dung cho screen reader, phần tổng tiền và nhãn nút nên được tạo từ cùng snapshot, cùng quy tắc định dạng/ngữ nghĩa.

Có thể dùng tên tiền đầy đủ để người nghe hiểu rõ, nhưng không để tên ấy mâu thuẫn với mã hiển thị. Khi báo giá đổi, thông báo cập nhật cần mô tả khoản tiền mới và trạng thái cần xác nhận lại.

### 10.3. Văn bản hai chiều và khoảng trắng Unicode

Một số locale dùng hướng viết phải sang trái hoặc ký tự định hướng trong chuỗi định dạng. Không xóa tùy tiện mọi ký tự Unicode không nhìn thấy rồi cho rằng chuỗi sẽ đúng hơn. Bố cục cần cô lập đoạn tiền theo cơ chế bidi phù hợp, kiểm thử thứ tự số, dấu âm và currency trên các locale được hỗ trợ.

Ngược lại, không chấp nhận ký tự điều khiển do người dùng tự đưa vào mã currency chuẩn. Đầu vào máy và đầu ra bản địa hóa có hợp đồng khác nhau: mã API có thể yêu cầu ASCII chặt chẽ, còn formatter hợp lệ có thể tạo khoảng trắng không ngắt dòng.

Các kiểm thử chuỗi cần biết khi nào khoảng trắng là khác biệt trình bày được phép. Không dùng một bước “xóa mọi dấu và khoảng trắng” để kết luận hai khoản tiền là tương đương, vì bước đó cũng có thể xóa dấu âm hoặc dấu thập phân có ý nghĩa.

## 11. Audit và đối soát tính nhất quán

Dữ liệu phục vụ truy vết một xác nhận hoặc phê duyệt nên đủ để nối các bước:

```text
+ quote_id / quote_version
+ order_id / payment_intent_id
+ amount_minor / currency / unit_scale
+ breakdown và phiên bản định giá có ý nghĩa
+ actor / approver / thời điểm quyết định
+ idempotency scope và liên kết thao tác
+ provider transaction ID / kết quả thực tế
```

Có thể lưu thêm locale, phiên bản trình bày và mẫu thông báo để hỗ trợ điều tra. Chúng giải thích cách thông tin được dựng, không thay thế dữ liệu tiền chuẩn và không cần trở thành thành phần định danh nghiệp vụ khi chỉ thay đổi hình thức.

Không ghi token thanh toán, khóa bí mật hoặc toàn bộ dữ liệu nhạy cảm chỉ để phục vụ debug hiển thị. Với dữ liệu không tin cậy, giới hạn và escape theo định dạng log; một chuỗi nhãn bị chèn ký tự điều khiển không nên giả thành dòng audit mới.

Các phép đối chiếu hữu ích:

| Đối chiếu | Sai lệch cần phát hiện |
| --- | --- |
| Quote đã xác nhận với payment intent | Sai phiên bản, amount, currency hoặc scale |
| Payment intent với lệnh gửi nhà cung cấp | Lỗi ánh xạ currency/đơn vị hoặc dùng nhầm route |
| Kết quả nhà cung cấp với giao dịch ghi nhận | Thu thực tế khác khoản dự kiến |
| Payment/refund với biên nhận | Biên nhận dùng giá hiện tại hoặc nhầm loại giao dịch |
| Dữ liệu tiền chuẩn với các kênh hiển thị | Kênh dùng sai locale, làm tròn ngoài hợp đồng hoặc thiếu đơn vị |

Các khoản phí, chuyển đổi và quyết toán khác currency cần quy tắc đối chiếu theo vai trò; không so hai con số khác đơn vị rồi coi phần chênh là lỗi. Với dữ liệu cập nhật bất đồng bộ, đối chiếu theo cùng trạng thái hoặc mốc cắt phù hợp để phân biệt độ trễ với sai lệch thật.

Nếu đã thu sai tiền, việc sửa template chỉ khắc phục đầu ra về sau. Phải xác định giao dịch bị ảnh hưởng, giữ lịch sử và xử lý điều chỉnh theo quy trình có quyền, hạn mức và bằng chứng. Không sửa payment cũ để làm nó giống số từng hiển thị.

## 12. Kiểm thử tình huống tấn công logic và lỗi trình bày

### 12.1. Ma trận tình huống

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Đổi locale vi-VN sang en-US | Money tuple và khoản gửi nhà cung cấp không đổi |
| Có nhiều loại dollar trong một bảng hoặc luồng | Currency đủ rõ, không dựa riêng vào `$` |
| VND/JPY scale 0 và USD scale 2 theo cấu hình thử nghiệm | Số nguyên được diễn giải đúng đơn vị; không mặc định hai số lẻ |
| Số tiền lớn vượt miền nguyên chính xác của kiểu số frontend đang dùng | Không bị mất chữ số qua API và formatter |
| Tổng tiền có phần lẻ, màn hình dùng kiểu viết gọn | Điểm xác nhận vẫn có giá trị đầy đủ và đúng currency |
| Dòng phí/thuế cần làm tròn | Breakdown và tổng theo cùng chính sách đã chốt |
| Currency trong request khác quote nhưng đều được hỗ trợ | Không tạo payment bằng cặp tiền ghép sai nguồn |
| Sửa `totalFormatted`, DOM hoặc hidden field | Không sửa khoản tiền có thẩm quyền |
| Caller dùng quote của tenant khác | Bị từ chối; không lộ số tiền hoặc biên nhận |
| Dùng phiên bản báo giá cũ khi giá/phí đã đổi | Server xử lý đúng chính sách phiên bản và yêu cầu xác nhận lại khi cần |
| Hai response báo giá trả về ngược thứ tự | Không trộn amount/currency/version giữa hai response |
| Cache cùng product nhưng khác tenant/currency | Không trả nhầm khoản tiền hoặc dữ liệu riêng tư |
| Hai request dùng formatter chung với currency khác nhau | Không xuất hiện ký hiệu, scale hoặc dấu từ request khác |
| Cùng idempotency key nhưng đổi quote hoặc money tuple | Xung đột command; không tạo hiệu ứng mới |
| Retry sau khi payment đã commit nhưng mất response | Trả kết quả cũ theo quyền; không thu thêm tiền |
| Adapter nhà cung cấp dùng sai scale | Bị phát hiện bằng kiểm tra hợp đồng và đối chiếu; không sửa nhãn để che lỗi |
| Callback hợp lệ về chữ ký nhưng sai amount/currency | Không tự đánh dấu thành công; giữ bằng chứng ngoại lệ |
| Giá sản phẩm thay đổi sau thanh toán | Biên nhận vẫn phản ánh giao dịch đã thực hiện |
| Hoàn một payment lịch sử bằng locale mới | Số tiền/currency nguồn giữ nguyên, chỉ định dạng thay đổi |
| Khoản âm, dạng kế toán hoặc refund có nhãn riêng | Không mất hoặc đảo nghĩa dấu và chiều nghiệp vụ |
| Mobile, zoom lớn, bảng hẹp | Dấu, currency và phần thập phân không bị che ở điểm quyết định |
| Screen reader và nội dung nhìn thấy | Cùng diễn tả tổng tiền, currency và hành động |
| Locale phải sang trái hoặc khoảng trắng Unicode | Thứ tự và liên kết số/currency rõ, không dùng bộ lọc phá nghĩa |
| Tên/nhãn do merchant cung cấp chứa markup hoặc ký tự điều khiển | Không chèn nội dung để đổi cách hiểu khoản tiền |
| Báo cáo dùng tiền quy đổi | Có nhãn, mốc tỷ giá và liên kết tới tiền giao dịch gốc |

Với kiểm thử lỗi phiên bản hoặc response về ngược thứ tự, cần điểm đồng bộ để tạo đúng thứ tự cạnh tranh. Với formatter dùng chung, kiểm thử tuần tự không đủ chứng minh không có race condition.

Kiểm thử API nên kiểm tra cả dữ liệu đã lưu và số lần/giá trị gọi tới nhà cung cấp giả lập. Kiểm thử UI cần kiểm tra bố cục thực tế và nội dung hỗ trợ tiếp cận; chỉ assert rằng một chuỗi có chứa `USD` chưa chứng minh currency không bị cắt khỏi màn hình.

### 12.2. Các tính chất nên giữ

```text
+ Cùng Money snapshot, đổi locale không đổi khoản tiền nghiệp vụ.
+ Cùng quote/version, các thành phần trên màn hình dùng cùng dữ liệu nguồn.
+ Đổi currency không được thực hiện chỉ bằng thay ký hiệu hiển thị.
+ Confirmation chỉ tạo hiệu ứng theo snapshot được server chấp nhận.
+ Replay cùng thao tác không làm tăng số lần thu/hoàn.
+ Biên nhận không thay giá trị khi bảng giá hoặc tỷ giá hiện tại đổi.
```

Không cần định nghĩa tính đúng đắn bằng cách parse lại chuỗi để so số, vì chính bộ parse có thể che lỗi locale hoặc ký hiệu. Kiểm tra giá trị chuẩn ở tầng domain; kiểm tra kết quả định dạng với trường hợp chuẩn và cấu trúc/ngữ nghĩa hiển thị; kiểm tra khoản được gửi thực tế ở biên tích hợp.

Một số chuỗi có thể thay đổi khi nâng runtime hoặc dữ liệu locale, như ký hiệu và khoảng trắng. Tách các kiểm tra bất biến tiền khỏi kiểm tra hình thức có phiên bản, rồi xem xét thay đổi đầu ra tại những màn hình có ý nghĩa quyết định. Không cập nhật toàn bộ snapshot test một cách máy móc khi có khác biệt.

## 13. Những thiết kế dễ tạo sai lệch

| Dấu hiệu | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Tự chọn currency từ locale | Đổi ngôn ngữ làm đổi nghĩa khoản tiền | Lấy currency từ đối tượng nguồn, locale chỉ để định dạng |
| Chỉ hiện ký hiệu mơ hồ | Người dùng hoặc người duyệt hiểu nhầm đơn vị | Hiện mã hoặc tên tiền rõ tại điểm quyết định |
| Format bằng số dấu phẩy động sau khi API đã gửi số chính xác | Mất độ chính xác trước cả khi render | Giữ biểu diễn chính xác xuyên suốt |
| Gửi chuỗi tiền đã định dạng để server parse lại | Nhầm dấu phân cách, ký hiệu và scale | Dùng hợp đồng Money có cấu trúc |
| Frontend tự tính tổng và phí riêng | Hiển thị khác khoản server thu | Dùng snapshot định giá có thẩm quyền |
| Amount và currency ở hai state/cache khác nhau | Ghép nhãn và giá từ hai phiên bản | Cập nhật nguyên khối theo quote snapshot |
| Request xác nhận chỉ ghi “dùng giá mới nhất” | Lần bấm cũ có thể chấp nhận số tiền mới ngầm định | Ràng buộc quote/version và chính sách hết hiệu lực |
| Formatter singleton bị sửa theo từng request | Lẫn currency, scale hoặc rounding giữa người dùng | Tránh chia sẻ mutable hoặc đồng bộ đúng |
| Biên nhận tính lại từ giỏ hàng hiện tại | Lịch sử giao dịch bị diễn giải sai | Đọc payment/refund đã ghi nhận |
| Sửa nhãn để khớp khoản đã gửi sai nhà cung cấp | Che lỗi tích hợp, giữ sai lệch tiền thực | Giữ bằng chứng và xử lý giao dịch bị ảnh hưởng |

Một luồng hiển thị đạt yêu cầu khi có thể nối rõ **khoản tiền đã tính, thông tin được dùng để xác nhận, payment intent, yêu cầu gửi nhà cung cấp và biên nhận**. Mỗi bước có thể trình bày khác theo ngôn ngữ, nhưng số tiền, loại tiền, phiên bản và ý nghĩa nghiệp vụ phải được giữ đúng qua mọi ranh giới.

