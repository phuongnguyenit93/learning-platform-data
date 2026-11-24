# Danh sách tiền tệ được phép — Currency allowlist

## 1. Vì sao lựa chọn tiền tệ là một quy tắc bảo mật?

Trong chương **Currency Handling**, currency allowlist là tập tiền tệ mà hệ thống cho phép dùng cho **một thao tác trong một ngữ cảnh xác định**. Ví dụ, một cửa hàng có thể được nhận thanh toán VND qua một tuyến nhà cung cấp cụ thể, trong khi một cửa hàng khác được nhận USD. Quyền sử dụng một đồng tiền không tự truyền từ cửa hàng này sang cửa hàng khác.

Nếu API chỉ kiểm tra trường `currency` có ba ký tự hoặc được thư viện nhận diện, người dùng có thể chọn một đồng tiền mà sản phẩm, cửa hàng, tài khoản hay tuyến thanh toán chưa hỗ trợ. Lỗi còn nghiêm trọng hơn nếu hệ thống lấy số tiền từ đơn hàng nhưng lại lấy loại tiền từ request của người dùng.

```json
{
  "orderId": "order-123",
  "amountMinor": 100000,
  "currency": "USD"
}
```

Giả sử đơn hàng có giá gốc là `100000` đơn vị nhỏ nhất của VND. Thay mã tiền sang USD trong ví dụ không tạo ra phép đổi tiền hợp lệ: với cấu hình USD có hai chữ số thập phân, `100000` đơn vị nhỏ nhất biểu diễn 1.000 USD. Cặp **số tiền và loại tiền** đã mang ý nghĩa khác, dù số nguyên không đổi.

Một currency allowlist tốt giúp ngăn lựa chọn tiền tệ ngoài phạm vi, nhưng vẫn cần các bất biến liên quan:

- Tiền tệ được phép cho đúng tenant, cửa hàng, sản phẩm, thao tác và tuyến xử lý.
- Tiền tệ của thanh toán phải khớp đơn hàng hoặc báo giá có thẩm quyền.
- Sau điểm chốt nghiệp vụ, không được thay mã tiền mà giữ nguyên số tiền.
- Hoàn tiền phải gắn với giao dịch gốc và chính sách hoàn tiền riêng.
- Thay đổi cấu hình không làm diễn giải lại dữ liệu lịch sử.

Đây là vấn đề **business logic security**: request có thể hợp lệ về JSON và đến từ một tài khoản đã đăng nhập nhưng vẫn phá vỡ quy tắc tiền tệ của giao dịch.

## 2. Phân biệt đúng định dạng, được nhận diện và được phép

Các lớp kiểm tra sau giải quyết những câu hỏi khác nhau:

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Hợp đồng đầu vào | Trường có đúng kiểu, có mặt khi bắt buộc và không trùng lặp không? | `currency` phải là một chuỗi đơn |
| Cú pháp mã tiền | Chuỗi có đúng biểu diễn chuẩn mà API chấp nhận không? | Chính xác ba ký tự ASCII từ `A` đến `Z` |
| Danh mục tham chiếu | Hệ thống có metadata đã kiểm soát cho mã đó không? | Có mã, đơn vị tiền và cách ánh xạ tới nhà cung cấp |
| Allowlist nghiệp vụ | Mã đó có được dùng ở đây và cho thao tác này không? | Cửa hàng A được nhận VND qua route R |
| Nhất quán giao dịch | Mã có khớp đối tượng nguồn và trạng thái hiện tại không? | Thanh toán khớp currency của báo giá đã chốt |

Regex `[A-Z]{3}` chỉ kiểm tra cú pháp khi dùng phép khớp toàn bộ chuỗi. Nó không chứng minh mã tồn tại hoặc được doanh nghiệp hỗ trợ. Tương tự, một mã có trong danh mục tiền tệ không mặc nhiên được phép dùng để thu tiền.

Trong Java, `Currency.getInstance(code)` hỗ trợ tra cứu dữ liệu tiền tệ của runtime. `Currency.getAvailableCurrencies()` còn có thể bao gồm mã ISO 4217 đã lỗi thời. Vì thế không dùng toàn bộ tập do JDK trả về làm allowlist thanh toán. Xem [tài liệu Java SE 21 về Currency](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Currency.html).

Danh mục tham chiếu và cấu hình hỗ trợ cần có quy trình cập nhật được kiểm soát. Việc nâng cấp JDK hoặc đồng bộ metadata không nên tự mở thêm tiền tệ cho khách hàng.

OWASP phân biệt kiểm tra cú pháp với kiểm tra ý nghĩa nghiệp vụ và yêu cầu xác minh lựa chọn trong tập được phép ngay cả khi giá trị đến từ danh sách chọn trên giao diện. Currency allowlist cần áp dụng nguyên tắc đó ở server. Xem [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html).

### 2.1. Quy ước biểu diễn đầu vào

Một hợp đồng API đơn giản có thể yêu cầu mã chữ hoa ASCII chính xác:

| Đầu vào | Cách xử lý trong hợp đồng minh họa |
| --- | --- |
| `"VND"`, `"USD"` | Tiếp tục kiểm tra danh mục và chính sách |
| `"usd"` | Từ chối vì không đúng biểu diễn API đã công bố |
| `" USD"`, `"USD "` | Từ chối, không tự cắt khoảng trắng |
| `"ＵＳＤ"` | Từ chối; đây là ký tự fullwidth, không phải ASCII |
| `"US$"`, `"$"` | Từ chối; ký hiệu hiển thị không phải mã API |
| Chuỗi có ký tự vô hình hoặc ký tự nhìn giống chữ Latin | Từ chối theo hợp đồng ASCII |
| `null`, chuỗi rỗng hoặc trường bị thiếu khi bắt buộc | Từ chối, không tự chọn một đồng tiền khác |
| Mảng, object hoặc số | Từ chối vì sai kiểu |

Có thể thiết kế API chấp nhận chữ thường rồi chuẩn hóa về chữ hoa, nhưng phải công bố và thực hiện nhất quán trước khi so sánh, tạo fingerprint và lưu dữ liệu. Bài này dùng hợp đồng nghiêm ngặt để tránh cách hiểu khác nhau giữa các thành phần.

JSON có hai trường `currency` cần được parser hoặc lớp nhận request xử lý theo chính sách từ chối trùng key. Nếu gateway kiểm tra giá trị đầu còn service dùng giá trị cuối, một request có thể vượt qua lớp kiểm tra tiền tệ dù từng lớp đều tưởng mình đã kiểm tra đúng.

Không suy mã tiền thanh toán từ locale của trình duyệt, ký hiệu `$`, địa chỉ IP hoặc ngôn ngữ giao diện. Các dữ liệu này có thể hỗ trợ gợi ý hiển thị; quyết định giao dịch phải gắn với cấu hình và đối tượng nghiệp vụ có thẩm quyền.

## 3. Allowlist phải có phạm vi

Một cấu hình toàn cục như `supportedCurrencies = [VND, USD, JPY]` thường chưa đủ. Cần xác định các chiều có ảnh hưởng tới quyết định:

| Chiều ngữ cảnh | Quy tắc có thể phụ thuộc |
| --- | --- |
| Tenant và pháp nhân | Phạm vi kinh doanh và sổ tiền được cấu hình |
| Cửa hàng hoặc merchant | Hợp đồng xử lý tiền và tài khoản merchant |
| Sản phẩm | Bảng giá, hạn mức và đơn vị tiền đã hỗ trợ |
| Kênh | Checkout web, API đối tác, tác vụ vận hành |
| Thao tác | Thu tiền mới, hoàn tiền, chi trả, đổi tiền |
| Tuyến và tài khoản nhà cung cấp | Khả năng xử lý thực tế của đúng merchant account |
| Thời điểm và phiên bản chính sách | Quy tắc đang hiệu lực tại điểm quyết định |

Đối với một lần thu tiền, có thể mô hình hóa tập cho phép hiệu lực:

```text
AllowedCharge(context)
  = PlatformChargeCurrencies
  ∩ TenantChargeCurrencies
  ∩ StoreChargeCurrencies
  ∩ ProductChargeCurrencies
  ∩ RouteChargeCurrencies
```

Dấu giao có nghĩa là tiền tệ phải thỏa **mọi ràng buộc bắt buộc**. Dùng phép hợp sẽ làm yếu chính sách: một đồng tiền chỉ được sản phẩm biết đến cũng có thể lọt qua dù cửa hàng không được nhận nó.

Ví dụ cấu hình giả định:

```text
Nền tảng nhận:       {VND, USD, JPY}
Tenant A nhận:      {VND, USD}
Cửa hàng A1 nhận:   {VND}
Sản phẩm P nhận:    {VND, USD}
Route R nhận:       {VND, USD}

Kết quả cho A1/P/R: {VND}
```

Những tập trên chỉ minh họa thuật toán, không mô tả khả năng hiện tại của một nhà cung cấp cụ thể. Mỗi tập phải được tra theo đúng phạm vi; một giá trị cấu hình bị thiếu không được tự hiểu là “cho phép tất cả”. Nếu hệ thống hỗ trợ kế thừa, cần phân biệt rõ `INHERIT` với tập rỗng có nghĩa là không cho phép đồng tiền nào.

Route cũng phải do server lựa chọn trong các tuyến đã được cấp cho đối tượng đó. Không cho phép caller đưa một `merchantAccountId` của tenant khác chỉ vì tài khoản đó hỗ trợ đồng tiền họ muốn dùng. Nếu route được quyết định sau lựa chọn tiền tệ, thuật toán định tuyến chỉ được xét các route hợp lệ rồi kiểm tra quyết định cuối trước khi tạo hiệu ứng tiền.

### 3.1. Phân biệt các vai trò tiền tệ

| Vai trò | Ý nghĩa |
| --- | --- |
| Display currency | Đơn vị dùng để hiển thị giá hoặc ước tính |
| Charge currency | Đơn vị tiền khách thực sự bị thu |
| Settlement currency | Đơn vị tiền được quyết toán theo tuyến nhà cung cấp |
| Balance currency | Đơn vị của ví hoặc tài khoản số dư |
| Reporting currency | Đơn vị dùng trong báo cáo quy đổi |

Cho phép hiển thị USD không có nghĩa là được thu USD. Một tuyến có thể thu một loại tiền và quyết toán loại tiền khác theo chính sách chuyển đổi rõ ràng. Không bắt hai giá trị này bằng nhau một cách máy móc, cũng không dùng allowlist settlement để cấp quyền charge.

Mỗi vai trò cần tên trường và quy tắc riêng. Nếu có đổi tiền, phải có báo giá, tỷ giá, phí, hạn dùng và sự chấp nhận phù hợp; thay chuỗi `currency` không phải là chuyển đổi tiền.

## 4. Xác định nguồn dữ liệu có thẩm quyền

| Dữ liệu | Nguồn quyết định |
| --- | --- |
| Tenant của người gọi | Danh tính và quan hệ được server xác thực |
| Cửa hàng, sản phẩm, đơn hàng | Tra trong phạm vi chủ thể có quyền |
| Loại thao tác | Endpoint và state machine ở server |
| Tiền tệ được hỗ trợ | Chính sách đã phát hành và cấu hình route tương ứng |
| Tiền tệ và số tiền cần thu | Đơn hàng hoặc báo giá đã chốt |
| Tiền tệ được hoàn | Giao dịch gốc đã xác minh |
| Kết quả thanh toán bên ngoài | Thông điệp đã xác thực và được so khớp với payment intent |

Client có thể đề nghị một lựa chọn trong bước tạo báo giá. Server phải kiểm tra lựa chọn đó, tính giá đúng loại tiền và lưu kết quả. Khi xác nhận thanh toán, một API hẹp thường chỉ cần nhận `quoteId` hoặc `orderId` cùng khóa idempotency. Server lấy cặp tiền tệ/số tiền đã chốt từ đối tượng nguồn.

Nếu API xác nhận vẫn nhận `currency`, hãy coi đó là điều kiện kỳ vọng cần so khớp, không phải quyền thay đổi currency của đơn hàng. Một request có mã nằm trong allowlist nhưng khác mã đã chốt vẫn phải bị từ chối hoặc đi qua quy trình báo giá lại.

Các endpoint chỉnh sửa, import, API đối tác, job nền và callback cần cùng ranh giới nghiệp vụ. Chỉ kiểm tra ở controller checkout sẽ để lại đường đi vòng qua API quản trị hoặc tác vụ bulk update.

## 5. Gắn quyết định tiền tệ với state machine

Một state machine minh họa cho thanh toán:

```text
DRAFT
  → QUOTED
  → PAYMENT_PENDING
  → PAID

Đổi lựa chọn tiền ở DRAFT:
  Kiểm tra chính sách → tính lại giá → phát hành báo giá mới

Đổi lựa chọn tiền sau khi đã có payment intent:
  Không sửa tại chỗ
  Đi qua quy trình hủy/thay thế hợp lệ và kiểm tra kết quả cũ
```

Một báo giá nên gắn với tenant/cửa hàng/sản phẩm, cặp tiền tệ/số tiền, phiên bản định giá, phiên bản chính sách và hạn dùng. Không để `quoteId` có thể chuyển sang đơn hàng của tenant khác. Nếu cần đổi tiền tệ, server tạo báo giá mới; các phê duyệt dựa trên giá cũ cũng cần được đánh giá lại.

Luồng xác nhận có thể tổ chức như sau:

```text
Xác thực caller và chuẩn hóa command
BEGIN
  Claim khóa idempotency trong phạm vi phù hợp
  Nếu đã hoàn tất: kiểm tra quyền và trả kết quả đã lưu

  Khóa đơn hàng/báo giá cần xác nhận
  Kiểm tra sở hữu, trạng thái, phiên bản và hạn dùng
  Lấy money tuple đã chốt từ đối tượng nguồn

  Nạp chính sách cho đúng phạm vi và điểm hiệu lực
  Chọn route được cấp quyền và có khả năng xử lý
  Kiểm tra currency theo chính sách xác nhận hiện hành
  Kiểm tra currency/amount khớp dữ liệu đã chốt

  Tạo payment intent bất biến về money tuple
  Ghi quyết định chính sách, outbox và kết quả idempotency
COMMIT

Worker xử lý tương tác nhà cung cấp theo giao thức riêng
```

Transaction này bảo vệ các thay đổi cục bộ. Nó không làm lời gọi nhà cung cấp bên ngoài trở thành một phần của transaction SQL. Cần định nghĩa rõ worker sẽ áp chính sách nào trước khi gửi yêu cầu có hiệu ứng tiền và cách xử lý kết quả không chắc chắn.

Không cho client thay `policyVersion` để chọn lại phiên bản cũ còn cho phép tiền tệ đã bị tắt. Phiên bản chính sách được áp dụng phải do server quyết định và lưu làm bằng chứng.

## 6. Ví dụ Java: cổng kiểm tra allowlist theo thao tác

Ví dụ dưới dùng cú pháp Java 17. `PolicySnapshot` phải được service nạp từ nguồn tin cậy cho **đúng ngữ cảnh**, sau khi giao các tập ràng buộc bắt buộc. Người dùng không được gửi map quy tắc hoặc tự chọn snapshot này.

```java
import java.util.Map;
import java.util.Objects;
import java.util.regex.Pattern;

final class CurrencyAllowlist {
    private static final Pattern CODE = Pattern.compile("[A-Z]{3}");

    enum Operation {
        NEW_PAYMENT,
        REFUND
    }

    record CurrencyRule(
        int minorUnit,
        boolean newPaymentAllowed,
        boolean historicalRefundAllowed
    ) {
        CurrencyRule {
            // Giới hạn 0..9 là giới hạn của sản phẩm minh họa.
            if (minorUnit < 0 || minorUnit > 9) {
                throw new IllegalArgumentException("INVALID_CURRENCY_METADATA");
            }
        }
    }

    record PolicySnapshot(
        String version,
        Map<String, CurrencyRule> effectiveRules
    ) {
        PolicySnapshot {
            Objects.requireNonNull(version);
            if (version.isBlank()) {
                throw new IllegalArgumentException("MISSING_POLICY_VERSION");
            }
            effectiveRules = Map.copyOf(effectiveRules);
        }
    }

    record AllowedCurrency(
        String code,
        int minorUnit,
        String policyVersion
    ) {}

    static AllowedCurrency requireAllowed(
        String requestedCurrency,
        Operation operation,
        PolicySnapshot policy,
        String originalPaymentCurrency
    ) {
        Objects.requireNonNull(operation);
        Objects.requireNonNull(policy);

        if (requestedCurrency == null
                || requestedCurrency.length() != 3
                || !CODE.matcher(requestedCurrency).matches()) {
            throw new IllegalArgumentException("INVALID_CURRENCY_FORMAT");
        }

        CurrencyRule rule = policy.effectiveRules().get(requestedCurrency);
        if (rule == null) {
            throw new IllegalArgumentException("CURRENCY_NOT_ALLOWED");
        }

        switch (operation) {
            case NEW_PAYMENT -> {
                if (!rule.newPaymentAllowed()) {
                    throw new IllegalArgumentException("CURRENCY_NOT_ALLOWED");
                }
            }
            case REFUND -> {
                if (!rule.historicalRefundAllowed()) {
                    throw new IllegalArgumentException("CURRENCY_NOT_ALLOWED");
                }
                if (originalPaymentCurrency == null
                        || !requestedCurrency.equals(originalPaymentCurrency)) {
                    throw new IllegalArgumentException("CURRENCY_MISMATCH");
                }
            }
        }

        return new AllowedCurrency(
            requestedCurrency,
            rule.minorUnit(),
            policy.version()
        );
    }
}
```

Các điều kiện sử dụng quan trọng:

- `Operation` được xác định từ luồng nghiệp vụ ở server. Không cho request thanh toán tự khai là `REFUND` để dùng chính sách thoáng hơn.
- `originalPaymentCurrency` được đọc từ giao dịch gốc đã xác minh và kiểm tra quyền, không lấy từ request.
- `effectiveRules` là kết quả đã xét đúng tenant, cửa hàng, sản phẩm và route; map toàn cục không đáp ứng tiền điều kiện này.
- Metadata và key trong snapshot được kiểm tra ở quy trình phát hành cấu hình. `Map.copyOf` giúp snapshot không bị thay đổi ngoài ý muốn, không chứng minh cấu hình có thẩm quyền.
- Hàm chỉ kiểm tra allowlist và currency của khoản hoàn. Nó chưa kiểm tra số tiền, trạng thái, hạn mức hoàn, quyền đối tượng hoặc cơ chế transaction.
- Kết quả kiểm tra cần được dùng cho cùng quyết định đã nạp chính sách. Không kiểm tra bằng snapshot này rồi gửi thanh toán qua một route khác chưa được xét.

Ví dụ một snapshot giả định cho một phạm vi cụ thể:

```java
var policy = new CurrencyAllowlist.PolicySnapshot(
    "currency-policy-v12",
    Map.of(
        "VND", new CurrencyAllowlist.CurrencyRule(0, true, true),
        "USD", new CurrencyAllowlist.CurrencyRule(2, false, true)
    )
);
```

Trong snapshot này, USD đã ngừng cho thanh toán mới nhưng vẫn có thể qua cổng kiểm tra hoàn lịch sử nếu đúng currency của payment gốc. Quyết định hoàn cuối cùng còn phụ thuộc điều kiện nguồn và khả năng xử lý của tuyến hoàn tiền.

### 6.1. Tiền tệ đã được phép vẫn cần kiểm tra đơn vị tiền

Sau khi xác định mã tiền và metadata, server mới diễn giải số tiền theo quy tắc tương ứng. Ví dụ chuyển một chuỗi thập phân sang số nguyên đơn vị nhỏ nhất:

```java
BigInteger toMinorUnits(String decimalAmount, int minorUnit) {
    BigDecimal exact = new BigDecimal(decimalAmount)
        .setScale(minorUnit, RoundingMode.UNNECESSARY);
    return exact.movePointRight(minorUnit).toBigIntegerExact();
}
```

Đoạn này cần các import từ `java.math`; nó chỉ minh họa chuyển đổi chính xác. Lớp nhận request còn phải giới hạn kích thước chuỗi, miền số, yêu cầu giá trị dương theo thao tác và giới hạn lưu trữ. Không dùng `double` rồi mới chuyển sang `BigDecimal` để xử lý tiền cần chính xác.

Nếu dữ liệu đã là `amountMinor` dạng số nguyên, không nhân thêm theo scale lần nữa. Adapter nhà cung cấp phải có hợp đồng đơn vị riêng và ánh xạ được kiểm chứng; không suy rằng mọi nhà cung cấp dùng cùng một cách biểu diễn cho mọi đồng tiền.

`minorUnit` dùng để hiểu khoản tiền đã lưu phải gắn với metadata hoặc snapshot của giao dịch. Đối với hoàn lịch sử, kiểm tra currency theo chính sách hoàn hiện hành nhưng tính số tiền từ dữ liệu và đơn vị của giao dịch gốc. Không dùng metadata vừa thay đổi để diễn giải lại một số nguyên lịch sử.

## 7. Ngừng hỗ trợ tiền tệ mà vẫn giữ đúng lịch sử

Một cờ `enabled` dùng chung cho mọi thao tác dễ tạo lỗi: tắt đồng tiền để ngừng bán hàng có thể vô tình làm tất cả khoản hoàn cũ thất bại. Cần mô tả chính sách theo thao tác và phạm vi.

| Trạng thái chính sách minh họa | Thanh toán mới | Đọc lịch sử | Hoàn tiền của payment cũ |
| --- | --- | --- | --- |
| Đang hỗ trợ | Theo allowlist ngữ cảnh | Được nếu có quyền | Theo chính sách hoàn |
| Chỉ phục vụ lịch sử | Không | Được nếu có quyền | Có thể cho phép nếu đúng payment gốc và route còn xử lý được |
| Chặn thao tác tiền | Không | Vẫn bảo toàn dữ liệu và quyền đọc thích hợp | Cần quy trình được định nghĩa rõ; không tự chuyển currency |

“Chỉ phục vụ lịch sử” không có nghĩa là mọi người được tạo một request mang nhãn hoàn tiền. Phải có payment gốc thuộc đối tượng được phép truy cập, còn hạn mức hoàn, đúng trạng thái và đúng tuyến phù hợp.

Các quy tắc cần thống nhất khi gỡ một đồng tiền khỏi luồng mới:

1. Không xóa mã tiền khỏi danh mục mà dữ liệu lịch sử đang tham chiếu.
2. Không đổi currency của đơn hàng, ledger hoặc payment đã hoàn tất.
3. Phân biệt ngừng tạo mới với xử lý kết quả của thao tác đã bắt đầu.
4. Định nghĩa cách xử lý báo giá chưa hết hạn, payment đang chờ và khoản hoàn chưa gửi.
5. Lưu phiên bản, thời điểm hiệu lực, người phê duyệt và phạm vi ảnh hưởng.

Một callback báo thanh toán cũ thành công vẫn cần được xác thực, lưu và đối soát dù đồng tiền đã ngừng cho giao dịch mới. Nếu dữ liệu callback mâu thuẫn với payment intent, giữ bằng chứng và đưa vào luồng xử lý ngoại lệ; không đánh dấu thành công tự động, cũng không bỏ mất dấu vết tiền thực tế chỉ vì allowlist hiện tại đã thay đổi.

Nếu route cũ không còn hỗ trợ hoàn, không thay mã tiền trong refund rồi gửi lại cùng số nguyên. Cần quy trình xử lý ngoại lệ được cấp quyền, có tính toán tiền và bằng chứng riêng nếu thật sự phải chi trả bằng một phương thức hoặc đơn vị khác.

## 8. Thay đổi chính sách, cache và cạnh tranh

### 8.1. Quyết định tại thời điểm nào?

Giả sử hai việc xảy ra đồng thời:

```text
+----------------------+-------------------------------+
| Luồng thanh toán     | Luồng quản trị                |
+----------------------+-------------------------------+
| Đọc USD đang bật     |                               |
|                      | Tắt USD, phát hành v13         |
| Ghi payment theo v12 |                               |
+----------------------+-------------------------------+
```

Không thể đánh giá kết quả chỉ bằng câu “đã đọc allowlist trước khi ghi”. Phải định nghĩa điểm quyết định và chính sách cho công việc đang thực hiện.

Hai lựa chọn nghiệp vụ có thể có là yêu cầu mọi xác nhận mới theo chính sách hiện hành hoặc cho báo giá đủ điều kiện tiếp tục trong một thời hạn được kiểm soát. Lựa chọn nào cũng phải được server áp dụng rõ ràng; client không được tự chọn phiên bản cũ.

Nếu yêu cầu là sau khi thao tác tắt tiền tệ commit thì không có quyết định xác nhận mới được commit theo chính sách cũ, cần đồng bộ hai luồng ở ranh giới đó. Ví dụ, khi cấu hình và payment cùng DB:

- Luồng xác nhận giữ khóa chia sẻ trên dòng phiên bản chính sách cho phạm vi liên quan, đọc bộ quy tắc và ghi quyết định trong cùng transaction.
- Luồng thay đổi cấu hình phải lấy khóa xung đột trên chính dòng đó, cập nhật quy tắc và tăng phiên bản trong cùng transaction.
- Mọi đường thay đổi hoặc sử dụng quy tắc đều tuân thủ giao thức khóa; chỉ ghi thêm `policy_version` vào payment không tự tạo sự đồng bộ.

Đây là mô hình giao thức; cần chọn kiểu khóa và thứ tự khóa phù hợp DB thực tế. Nếu chính sách thuộc dịch vụ khác, phải có giao thức xác nhận phiên bản hoặc cấp phép tương ứng. Một lần đọc cache từ xa không tạo transaction chung với DB thanh toán.

Điểm cho phép tạo payment intent và điểm thực sự gửi lệnh tới nhà cung cấp có thể khác nhau. Một cơ chế chặn khẩn cấp muốn dừng cả việc gửi lệnh đang nằm trong outbox cần được kiểm tra tại worker, với chính sách cho thao tác đã được gửi nhưng chưa rõ kết quả. Tắt cấu hình không tự hoàn tác yêu cầu bên ngoài đã thực hiện.

### 8.2. Cache cần đầy đủ ngữ cảnh

Khóa cache chính sách cần chứa những chiều thực sự ảnh hưởng quyết định, chẳng hạn tenant, cửa hàng, sản phẩm, loại thao tác, route/merchant account và phiên bản. Cache chỉ theo `currency` có thể làm cấu hình của tenant này được dùng cho tenant khác.

Cần quy định rõ cách hết hạn, vô hiệu hóa và phát hành phiên bản. Nếu không thể xác định một chính sách đủ tin cậy cho giao dịch tiền mới, trả lỗi tạm thời hoặc từ chối theo thiết kế; không tự mở toàn bộ tiền tệ để duy trì lưu lượng.

Một cache phục vụ giao diện có thể chỉ giúp hiển thị lựa chọn. Quyết định có hiệu ứng tiền vẫn cần hàng rào server tại thời điểm được định nghĩa. Nếu UI và server khác phiên bản, server có thể yêu cầu tải lại lựa chọn hoặc lấy báo giá mới.

### 8.3. Quản trị allowlist là một thao tác đặc quyền

Thêm tiền tệ có thể mở thêm khả năng thu tiền, chi trả hoặc chuyển đổi. API cấu hình cần kiểm tra người sửa có quyền trên đúng tenant/pháp nhân, phạm vi được sửa và route liên quan. Vai trò chỉ được quản trị cửa hàng không mặc nhiên được sửa allowlist toàn nền tảng.

Có thể yêu cầu phê duyệt cho thay đổi có ảnh hưởng lớn. Phê duyệt cần gắn với nội dung hoặc phiên bản cấu hình cụ thể; sửa tập currency hoặc route sau khi đã duyệt phải dẫn đến đánh giá lại. Ghi audit trước/sau, người thực hiện, người duyệt, lý do và thời điểm hiệu lực.

## 9. Idempotency phải ràng buộc cả loại tiền

Một request fingerprint cho thao tác có đề nghị tiền tệ cần bao gồm currency đã chuẩn hóa cùng các trường tiền và đối tượng có ý nghĩa. Với API xác nhận chỉ dùng `quoteId`, phiên bản báo giá và money tuple được ràng buộc bởi báo giá bất biến phía server.

```text
+ Cùng key, cùng command đã hoàn tất:
+   Trả kết quả cũ sau khi kiểm tra quyền; không tạo hiệu ứng mới.
+
+ Cùng key nhưng currency hoặc nguồn tiền khác:
+   Từ chối vì command đã thay đổi.
+
+ Key mới nhưng cùng sự kiện thanh toán đã xử lý:
+   Ràng buộc nghiệp vụ vẫn phải ngăn thu/ghi nhận trùng.
+```

Trả lại biên nhận của một thao tác đã hoàn tất không phải là cấp quyền tạo giao dịch mới bằng tiền tệ đã bị tắt. Tuy nhiên, nếu lần trước mới dừng ở trạng thái chờ và chưa gửi yêu cầu tiền, việc có được tiếp tục gửi hay không phải theo chính sách dành cho thao tác đang chờ.

Khi nhà cung cấp trả timeout và chưa rõ có thu tiền hay chưa, không chuyển ngay sang route hoặc currency khác rồi gọi lại. Trước hết cần truy vấn/đối soát kết quả theo danh tính thao tác ban đầu và giao thức idempotency của tuyến đó. Nếu không, một cơ chế fallback có thể thu tiền hai lần hoặc tạo hai khoản không tương đương.

## 10. Lưu dữ liệu để không làm mất nghĩa của khoản tiền

Mô hình lưu trữ cần tách danh mục tiền tệ, chính sách thao tác và dữ liệu giao dịch:

| Nhóm dữ liệu | Nội dung nên lưu | Điều cần tránh |
| --- | --- | --- |
| Danh mục tham chiếu | Mã chuẩn, metadata có phiên bản, ánh xạ cần thiết | Tự động cho phép mọi mã vừa được đồng bộ |
| Chính sách hỗ trợ | Phạm vi, thao tác, route, thời điểm hiệu lực, phiên bản | Một cờ toàn cục dùng cho cả bán mới và xử lý lịch sử |
| Báo giá/đơn hàng | Currency, số tiền, đơn vị lưu trữ, phiên bản và hạn dùng | Lấy currency từ request khác với nguồn của amount |
| Payment intent | Money tuple đã chốt, nguồn, merchant/route, quyết định chính sách | Đổi currency tại chỗ sau khi bắt đầu xử lý |
| Refund | Liên kết payment gốc, money tuple, hạn mức và trạng thái | Tự đổi loại tiền để vượt một lỗi không hỗ trợ |
| Audit | Bằng chứng cấu hình và quyết định áp dụng | Chỉ lưu “đã validate” mà không biết chính sách nào |

Khóa ngoại từ giao dịch tới danh mục giúp ngăn mã không có dữ liệu tham chiếu. Nó không tự kiểm tra một mã còn được phép cho thanh toán mới. Ngược lại, nếu cho giao dịch lịch sử tham chiếu trực tiếp một dòng allowlist sẽ bị xóa khi ngừng hỗ trợ, việc xóa có thể phá vỡ lịch sử hoặc bị chặn ngoài ý muốn.

Cần giữ định danh và metadata cần thiết để đọc lại khoản tiền. Việc gỡ hỗ trợ được thể hiện bằng chính sách có hiệu lực, không bằng cách xóa dữ liệu mà lịch sử cần dùng. Thay đổi cấu hình không được làm `amountMinor=100000` của một payment cũ mang nghĩa khác.

Ở tầng domain, nên biểu diễn tiền bằng một kiểu có cả amount và currency, ví dụ `Money(amountMinor, currency)`. Phép cộng hoặc so sánh tiền khác currency phải bị từ chối trừ khi đi qua một thao tác chuyển đổi có định nghĩa. Điều này giúp giảm nguy cơ một service truyền số nguyên đi mà đánh mất đơn vị.

## 11. Lỗi, audit và khả năng quan sát

### 11.1. Phân biệt nguyên nhân xử lý

| Lỗi nội bộ minh họa | Ý nghĩa | Cách xử lý phù hợp |
| --- | --- | --- |
| `INVALID_CURRENCY_FORMAT` | Sai kiểu hoặc biểu diễn mã | Sửa request theo hợp đồng |
| `CURRENCY_NOT_ALLOWED` | Không nằm trong tập hiệu lực cho thao tác | Chọn phương án được phép hoặc dừng thao tác |
| `CURRENCY_MISMATCH` | Không khớp báo giá/payment nguồn | Tải lại dữ liệu hoặc đi qua quy trình báo giá lại |
| `CURRENCY_POLICY_UNAVAILABLE` | Chưa có quyết định chính sách đáng tin cậy | Lỗi tạm thời; không mở rộng quyền để fallback |
| `QUOTE_EXPIRED` hoặc `ORDER_VERSION_CONFLICT` | Dữ liệu nguồn không còn dùng được | Lấy báo giá/phiên bản mới theo state machine |

Không phải mọi mã lỗi nội bộ đều cần được trả nguyên văn cho caller. Trước khi trả chi tiết, kiểm tra quyền đối tượng; lỗi không nên giúp một người không có quyền suy ra currency, route hoặc cấu hình riêng của tenant khác.

Phản hồi cho người dùng có thể đề nghị chọn lại loại tiền nếu họ đang ở bước lựa chọn hợp lệ. Với khoản tiền đã chốt hoặc thao tác đang không rõ kết quả, không gợi ý “đổi currency rồi thử lại” như một cách khắc phục chung.

### 11.2. Bằng chứng quyết định

Với quyết định cho phép hoặc từ chối có ảnh hưởng tiền, nên truy được:

- Loại thao tác và định danh command/idempotency trong phạm vi phù hợp.
- Tenant, cửa hàng, đối tượng nguồn và route thực tế được dùng.
- Currency yêu cầu và currency có thẩm quyền của nguồn.
- Phiên bản chính sách, thời điểm quyết định và kết quả kiểm tra.
- Actor hoặc service principal và mã lý do.

Dữ liệu log phải có giới hạn độ dài, được mã hóa phù hợp định dạng và tránh chứa bí mật hay toàn bộ payload thanh toán. Đầu vào sai có thể chứa ký tự điều khiển; không ghi thẳng nó thành dòng log có thể giả mạo.

Các chỉ báo hữu ích gồm số lần từ chối do currency theo phạm vi, xung đột với báo giá, request dùng chính sách cũ và sai lệch giữa currency của payment intent với sự kiện nhà cung cấp. Một loạt yêu cầu thử nhiều mã tiền hoặc nhiều merchant account có thể cho thấy hành vi dò giới hạn nghiệp vụ.

## 12. Kiểm thử tình huống lạm dụng

Các kiểm thử cần quan sát hiệu ứng đã lưu và lời gọi ra nhà cung cấp, không chỉ thông báo trên giao diện. Với request bị từ chối trước khi thực hiện tiền, phải xác nhận không có payment intent mới được chấp nhận, không có tác vụ gửi tiền và không có bút toán phát sinh do request đó.

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Gửi `usd`, `USD `, fullwidth hoặc ký tự vô hình theo hợp đồng nghiêm ngặt | Bị từ chối trước xử lý nghiệp vụ |
| Thiếu/null/sai kiểu trường currency khi bắt buộc | Không tự rơi về tiền tệ mặc định |
| Gửi một mã đúng ba chữ nhưng không có quy tắc | Bị từ chối; regex không đủ cấp phép |
| Gửi mã được JDK nhận diện nhưng sản phẩm chưa hỗ trợ | Không được tạo giao dịch |
| Cùng USD, tenant A cho phép nhưng tenant B không cho phép | Mỗi tenant nhận đúng quyết định; không dùng nhầm cache |
| Gửi store hoặc merchant account của tenant khác | Bị từ chối theo quyền đối tượng |
| Sản phẩm cho phép nhưng cửa hàng hoặc route không cho phép | Bị từ chối theo phép giao ràng buộc |
| Route đầu hỗ trợ, route fallback không hỗ trợ | Không gửi yêu cầu không hợp lệ qua route fallback |
| Currency nằm trong allowlist nhưng khác báo giá | Không sửa money tuple hoặc tạo payment sai |
| Sửa currency qua PATCH, import hoặc API quản trị | Các đường ghi đều giữ cùng invariant |
| Đổi currency sau khi đã tạo payment intent | Không thay tại chỗ; theo đúng quy trình hủy/thay thế |
| Gửi request có hai key `currency` mâu thuẫn | Parser/hợp đồng từ chối; gateway và service không dùng hai giá trị khác nhau |
| Tắt đồng tiền sau khi tạo báo giá, trước xác nhận | Kết quả đúng chính sách chuyển tiếp đã định nghĩa |
| Thay đổi chính sách đồng thời với xác nhận | Không commit quyết định vượt ranh giới hiệu lực đã cam kết |
| Cache cũ hoặc không nạp được chính sách | Không tự mở rộng tập tiền tệ |
| Caller gửi `policyVersion` cũ | Không dùng nó để vượt chính sách server |
| Cùng key, đổi currency hoặc nguồn tiền | Xung đột idempotency; không tạo thêm hiệu ứng |
| Retry thao tác đã hoàn tất sau khi currency bị tắt | Trả lại kết quả cũ nếu có quyền; không thu lại tiền |
| Hoàn payment USD cũ khi USD chỉ còn phục vụ lịch sử | Được đánh giá theo chính sách hoàn và dữ liệu gốc |
| Gắn nhãn refund nhưng không có payment gốc hợp lệ | Không vượt qua cổng bằng chính sách hoàn tiền |
| Hoàn bằng currency khác payment gốc | Bị từ chối hoặc đi qua nghiệp vụ ngoại lệ riêng đã cấp quyền |
| Callback muộn có currency khớp payment cũ | Được lưu/xử lý theo luồng lịch sử, không mất bằng chứng |
| Callback có chữ ký hợp lệ nhưng currency khác payment intent | Không tự đánh dấu paid; giữ bằng chứng để xử lý xung đột |
| Hai currency có đơn vị nhỏ nhất khác nhau | Không tái dùng cùng số nguyên với ý nghĩa tiền khác |
| Sửa allowlist mà không có quyền hoặc sửa sau phê duyệt | Bị từ chối hoặc phải phê duyệt lại đúng phiên bản |

Các kiểm thử cạnh tranh cần có điểm đồng bộ để điều khiển thứ tự đọc chính sách, phát hành phiên bản và commit xác nhận. Hai request chạy nối tiếp chỉ kiểm tra luồng tuần tự.

Với hàm tính allowlist hiệu lực, có thể kiểm tra các tính chất:

```text
+ Kết quả là tập con của mọi tập ràng buộc bắt buộc.
+ Thu hẹp một tập ràng buộc không làm kết quả rộng hơn.
+ Một tập bắt buộc rỗng làm kết quả rỗng.
+ Quy tắc NEW_PAYMENT không tự cấp quyền REFUND hoặc PAYOUT.
+ Ngữ cảnh tenant/store/route khác không dùng chung quyết định sai phạm vi.
```

Không cần sao chép toàn bộ danh mục tiền tệ vào từng test. Các trường hợp đại diện cần phân biệt mã hợp cú pháp nhưng không được hỗ trợ, mã chỉ được dùng trong lịch sử, ngữ cảnh khác quyền và đơn vị tiền khác nhau.

## 13. Các lỗi thiết kế thường gặp

| Thiết kế | Vì sao nguy hiểm? | Hướng xử lý |
| --- | --- | --- |
| “JDK biết mã này nên nhận thanh toán” | Metadata runtime không thể hiện quyền nghiệp vụ | Allowlist được phát hành theo phạm vi và thao tác |
| Chỉ kiểm tra dropdown ở frontend | Caller có thể gọi API trực tiếp | Kiểm tra server tại ranh giới quyết định |
| Denylist vài mã chưa hỗ trợ | Mã khác hoặc mã mới có thể tự lọt qua | Mặc định không cho phép ngoài tập đã cấu hình |
| Lấy amount từ order, currency từ request | Ghép hai nguồn tạo khoản tiền sai nghĩa | Dùng money tuple có thẩm quyền |
| Tự đổi currency khi tuyến xử lý lỗi | Thay đơn vị không chuyển đổi số tiền | Chọn route hợp lệ hoặc tạo nghiệp vụ đổi tiền rõ ràng |
| Xóa mã khỏi toàn bộ hệ thống khi ngừng bán | Làm hỏng đọc lịch sử và xử lý khoản cũ | Giữ danh mục, thay chính sách cho từng thao tác |
| Cho client chọn tenant, route và policy version để validate | Caller có thể tìm ngữ cảnh ít ràng buộc hơn | Server xác định phạm vi từ quan hệ và quyền |
| Dùng một cấu hình cho display, charge và settlement | Quyền hiển thị trở thành quyền xử lý tiền | Tách vai trò và quy tắc theo loại tiền |
| Cho phép cả payment/refund chỉ bằng cờ `enabled` | Khó ngừng bán mà vẫn xử lý lịch sử an toàn | Quy tắc theo operation và nguồn giao dịch |

Một quyết định currency đạt yêu cầu khi hệ thống trả lời được: **đồng tiền này được phép cho ai, ở đâu, cho thao tác nào, qua tuyến nào, tại thời điểm nào và phải khớp với khoản tiền nguồn nào**. Câu trả lời cần được giữ nguyên từ bước kiểm tra đến lúc tạo hiệu ứng tiền, cùng bằng chứng đủ để truy vết về sau.

