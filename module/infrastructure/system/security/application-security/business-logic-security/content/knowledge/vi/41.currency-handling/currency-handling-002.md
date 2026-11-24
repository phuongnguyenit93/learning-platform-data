# Currency conversion authority

## 1. Ai có quyền quyết định kết quả quy đổi?

**Currency conversion authority** là việc xác định thành phần nào được quyền chọn tỷ giá, chiều quy đổi, phí, quy tắc làm tròn và số tiền cuối cùng mà hệ thống sẽ ghi nhận hoặc thanh toán.

Trong chương **Currency Handling** của module **Business Logic Security**, vấn đề không chỉ là nhân đúng một con số. Hệ thống còn phải bảo vệ quyết định quy đổi khỏi các cách lạm dụng như:

- Thay tỷ giá hoặc số tiền trong request.
- Dùng báo giá thuộc khách hàng, tài khoản hoặc đơn hàng khác.
- Chọn lại thời điểm có lợi hoặc tái sử dụng báo giá đã hết hạn.
- Đổi currency nhưng giữ nguyên amount dạng số nguyên.
- Bỏ qua phê duyệt khi số tiền sau quy đổi vượt ngưỡng.
- Gửi lại yêu cầu để ghi nhận chuyển đổi, thanh toán hoặc hoàn tiền nhiều lần.

Nguyên tắc nền tảng: **client có thể yêu cầu cặp tiền và xác nhận lựa chọn, nhưng quyết định có hiệu lực phải đến từ phía máy chủ có thẩm quyền**. Kết quả đó cần được gắn với đúng chủ thể, mục đích, nghĩa vụ và thời hạn.

### 1.1. “Authority” bao gồm cả quyền tạo, dùng và thay đổi quyết định

Có ba loại quyền khác nhau:

1. **Cấp dữ liệu tỷ giá:** nguồn nào được phép cung cấp dữ liệu đầu vào.
2. **Phát hành báo giá thực thi:** dịch vụ nào được chọn tỷ giá áp dụng, phí và số tiền cam kết.
3. **Chấp thuận và thực hiện:** chủ thể nào được dùng báo giá đó cho tài khoản hoặc nghĩa vụ cụ thể.

Nhà cung cấp tỷ giá có thể được tin cậy để cung cấp dữ liệu tham khảo, nhưng không vì thế có quyền đổi phí bán hàng của hệ thống. Người dùng có quyền xem giá cũng chưa chắc có quyền chuyển tiền từ tài khoản doanh nghiệp.

Một chữ ký hợp lệ trên báo giá chứng minh tính toàn vẹn theo cơ chế ký. Nó không tự chứng minh người gọi có quyền sử dụng báo giá, báo giá còn hiệu lực hoặc chưa được dùng.

### 1.2. Phân biệt các loại currency trong một giao dịch

| Vai trò | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Currency của giá gốc | Đồng tiền dùng để định giá hàng hóa hoặc nghĩa vụ | Giá sản phẩm là 100 USD |
| Display currency | Đồng tiền dùng để hiển thị cho người dùng | Trang sản phẩm hiển thị giá tham khảo bằng VND |
| Charge/presentment currency | Đồng tiền thực sự dùng để yêu cầu thanh toán | Người dùng chấp thuận thanh toán 2.500.000 VND |
| Settlement currency | Đồng tiền nhà cung cấp thanh toán quyết toán về cho doanh nghiệp | Doanh nghiệp nhận khoản quyết toán bằng EUR |
| Accounting/reporting currency | Đồng tiền dùng cho báo cáo theo chính sách kế toán | Báo cáo quy đổi doanh thu sang VND |

Các phép quy đổi ở những lớp này có thể dùng nguồn và thời điểm khác nhau. Tỷ giá hiển thị không đương nhiên là tỷ giá thanh toán; số tiền quyết toán không đương nhiên là số tiền đã cam kết với người mua.

Sự phân biệt presentment và settlement cũng được mô tả trong [Stripe: Supported currencies](https://docs.stripe.com/currencies). Bài học dùng các ví dụ thiết kế tổng quát, không giả định nhà cung cấp nào hỗ trợ mọi cặp tiền hoặc mọi phương thức thanh toán.

## 2. Ví dụ: server đúng công thức nhưng sai nguồn quyết định

Một đơn hàng có giá 100 USD. Máy chủ quy định báo giá áp dụng là:

~~~text
1 USD = 25.000 VND
Số tiền thanh toán = 2.500.000 VND
~~~

Các con số tỷ giá trong bài chỉ dùng minh họa, không phải báo giá thị trường.

Nếu backend nhận request như sau rồi tin toàn bộ dữ liệu:

~~~json
{
  "orderId": "ord-842",
  "fromCurrency": "USD",
  "toCurrency": "VND",
  "sourceAmount": "100.00",
  "exchangeRate": "100.00",
  "targetAmount": "10000"
}
~~~

người dùng có thể khiến hệ thống thu 10.000 VND cho đơn 100 USD. Phép nhân vẫn đúng với tỷ giá client gửi; lỗi là để client quyết định tỷ giá có hiệu lực.

Một cách sửa vẫn thiếu là server tự tính lại:

~~~java
// Cố ý không an toàn: rate và currency vẫn do client quyết định.
BigDecimal target = request.sourceAmount()
    .multiply(request.exchangeRate());
~~~

Validation “rate > 0” chỉ loại bỏ một số đầu vào sai. Nó không chứng minh rate là tỷ giá được phép áp dụng cho đơn này.

Một ví dụ khác: server đã lưu báo giá Q cho đơn A, nhưng endpoint thanh toán chỉ kiểm tra Q tồn tại. Người gọi có thể gắn Q vào đơn B có giá trị lớn hơn. Do đó, quyền sử dụng báo giá và liên kết với nghĩa vụ quan trọng ngang với công thức quy đổi.

## 3. Ma trận quyền quyết định

Một thiết kế có thể phân định như sau:

| Dữ liệu hoặc hành động | Nguồn có thẩm quyền | Client được làm gì? |
| --- | --- | --- |
| Giá gốc và số tiền nghĩa vụ | Order/pricing service với phiên bản xác định | Chọn sản phẩm, số lượng trong phạm vi được phép |
| Các cặp tiền được hỗ trợ | Cấu hình nghiệp vụ phía máy chủ | Chọn trong danh sách được hỗ trợ |
| Tỷ giá tham chiếu | Feed hoặc rate service được cấu hình | Xem thông tin được công bố |
| Chiều mua/bán, spread, phí | Chính sách phía máy chủ đã được phê duyệt | Xem và chấp thuận điều kiện |
| Amount cuối cùng và expiry | Quote service có thẩm quyền | Xác nhận một quote cụ thể |
| Tài khoản bị ghi nợ/ghi có | Liên kết nghiệp vụ và quyền theo đối tượng | Chọn tài khoản mà mình được phép dùng |
| Sử dụng báo giá | Conversion/payment service | Gửi yêu cầu thực hiện và idempotency key |
| Thay đổi hoặc override tỷ giá | Vai trò vận hành chuyên biệt, theo quy trình | Không tự gửi cờ để bỏ qua quy trình |
| Kết quả nhà cung cấp bên ngoài | Phản hồi đã xác minh, tra cứu và đối soát | Tra trạng thái; không tự khai thành công |

Rate service và quote service có thể nằm trong cùng ứng dụng. Điểm quan trọng là hợp đồng quyền hạn và dữ liệu, không phải tách thành nhiều microservice.

Dịch vụ nội bộ cũng cần được xác thực và giới hạn quyền. Tên endpoint “internal” hoặc header tự khai không tạo ra authority.

## 4. Money, đơn vị và chiều tỷ giá phải rõ ràng

### 4.1. Amount luôn đi cùng currency và đơn vị

~~~text
Money = amount + currency + quy ước đơn vị
~~~

Trong ví dụ:

~~~text
100 USD = 10.000 USD minor units
2.500.000 VND = 2.500.000 VND units
~~~

Không được hiểu số nguyên 10.000 giống nhau cho mọi currency. Cũng không nên có một trường số tiền trần rồi suy currency từ locale của trình duyệt.

Số chữ số thập phân trong mô hình miền và cách mã hóa amount của API nhà cung cấp cần được quản lý riêng. Một số nhà cung cấp có ngoại lệ theo currency hoặc theo loại thao tác charge/payout; cần adapter theo hợp đồng của họ, thay vì dùng một công thức nhân 100 cho tất cả. Xem [quy tắc amount và các trường hợp đặc biệt của Stripe](https://docs.stripe.com/currencies).

### 4.2. Ghi rõ đơn vị của tỷ giá

Nếu:

~~~text
rate = số đơn vị tiền đích trên một đơn vị tiền nguồn
~~~

thì:

~~~text
targetMajor = sourceMajor * rate
targetMinor = round(targetMajor * 10^targetExponent)
sourceMajor = sourceMinor / 10^sourceExponent
~~~

Ví dụ:

~~~text
sourceCurrency = USD
targetCurrency = VND
sourceExponent = 2
targetExponent = 0
sourceMinor = 10000
rate = 25000 VND/USD

sourceMajor = 10000 / 100 = 100 USD
targetMinor = round(100 * 25000 * 1) = 2500000
~~~

Nếu nhân trực tiếp sourceMinor với rate rồi coi kết quả là VND, số tiền sẽ sai 100 lần.

Tránh tên trường mơ hồ như `rate: 25000` mà thiếu base/quote currency và đơn vị. Nên diễn đạt như `targetUnitsPerSourceUnit` hoặc hợp đồng tương đương có định nghĩa rõ.

### 4.3. Chiều ngược không chỉ là lấy nghịch đảo

Tỷ giá người mua USD bằng VND có thể khác tỷ giá bán USD lấy VND vì spread và phí. Cặp tỷ giá thực thi cũng có thể chịu hạn mức và điều kiện khác nhau.

Do đó:

- Không lấy báo giá USD → VND rồi dùng nó làm báo giá VND → USD.
- Không suy một báo giá thực thi mới chỉ bằng cách lấy 1/rate.
- Nếu dùng cross-rate qua đồng trung gian, phải lưu được nguồn, chiều, thời điểm và quy tắc tính.
- Không hứa rằng chuyển qua rồi chuyển lại sẽ thu được đúng số tiền ban đầu.

Một tỷ giá phù hợp để báo cáo không nhất thiết là tỷ giá có thể giao dịch. Authority cần phân biệt dữ liệu tham khảo với cam kết thực thi.

## 5. Từ feed tỷ giá đến một báo giá có hiệu lực

### 5.1. Kiểm soát nguồn và chất lượng dữ liệu

Rate service cần quy định:

- Nguồn nào được phép cung cấp cặp tiền nào.
- Timestamp của tỷ giá, thời điểm nhận và thời điểm phát hành quote.
- Tuổi tối đa của dữ liệu cho từng mục đích.
- Giới hạn miền giá trị và mức biến động cần kiểm tra.
- Cách xử lý thiếu dữ liệu, nguồn chậm hoặc cặp tiền không được hỗ trợ.
- Quyền thay đổi nguồn, margin và quy tắc fallback.

Không cho client gửi URL nguồn tỷ giá tùy ý để máy chủ tải về. Ngoài việc chọn sai dữ liệu có lợi, cơ chế đó còn có thể tạo đường truy cập mạng ngoài ý muốn.

Cache phải phân biệt cặp tiền và chiều quy đổi, nguồn, sản phẩm, phân khúc phí hoặc các điều kiện có ảnh hưởng. Hai tenant có chính sách spread khác nhau không được dùng chung một kết quả quote chỉ vì cùng cặp tiền.

### 5.2. Không dùng fallback bí mật làm thay đổi cam kết

Nếu feed lỗi, các lựa chọn phải do chính sách định nghĩa, chẳng hạn:

- Tạm dừng phát hành quote thực thi mới.
- Dùng nguồn dự phòng đã được phê duyệt và ghi lại nguồn.
- Dùng dữ liệu còn trong ngưỡng tuổi được phép cho mục đích đó.
- Chỉ hiển thị giá tham khảo và thông báo chưa thể xác nhận thanh toán.

Không mặc định rate = 1, lấy giá client, hoặc dùng tỷ giá cũ vô thời hạn để “giữ luồng chạy được”.

Với một quote cố định đã được phát hành hợp lệ, thị trường đổi không tự làm quote biến thành giá mới. Quote đó được sử dụng theo điều kiện và thời hạn đã công bố, trừ quy trình thu hồi đặc biệt đã được định nghĩa rõ. Nếu sản phẩm không cam kết giá cố định, phải thể hiện đúng loại quote và yêu cầu chấp thuận số tiền thực thi cuối cùng.

### 5.3. Phí, spread và làm tròn là một phần của quyết định

Hai chính sách sau cho kết quả khác nhau:

~~~text
Chính sách A:
  Trừ phí bằng tiền nguồn trước.
  Quy đổi phần nguồn còn lại.
  Làm tròn tiền đích.

Chính sách B:
  Quy đổi toàn bộ tiền nguồn.
  Trừ phí bằng tiền đích.
  Làm tròn theo thứ tự đã định.
~~~

Không được đổi từ A sang B sau khi người dùng đã chấp thuận quote.

Trong các phần triển khai bên dưới, ví dụ chọn:

~~~text
sourceDebit = tổng tiền nguồn bị trừ
sourceFee   = phí bằng tiền nguồn
sourceNet   = sourceDebit - sourceFee
targetCredit = round(sourceNet * effectiveRate theo đơn vị tiền đích)

0 <= sourceFee < sourceDebit
targetCredit > 0
~~~

`effectiveRate` là tỷ giá thực thi sau spread nếu có; spread không được tính thêm một lần nữa như một khoản phí ẩn. Phiên bản chính sách quyết định chính xác những thành phần này.

## 6. Báo giá phải ràng buộc với đúng giao dịch

Một quote có thể lưu:

~~~json
{
  "quoteId": "fxq-842",
  "tenantId": "tenant-a",
  "customerId": "customer-19",
  "sourceAccountId": "wallet-usd-19",
  "targetAccountId": "wallet-vnd-19",
  "purpose": "WALLET_CONVERSION",
  "obligationId": "conversion-intent-301",
  "sourceCurrency": "USD",
  "sourceExponent": 2,
  "sourceDebitMinor": "10000",
  "sourceFeeMinor": "0",
  "targetCurrency": "VND",
  "targetExponent": 0,
  "targetCreditMinor": "2500000",
  "targetUnitsPerSourceUnit": "25000",
  "rateSnapshotId": "rate-snapshot-917",
  "pricingPolicyVersion": "fx-policy-v7",
  "roundingPolicyVersion": "fx-rounding-v3",
  "createdAt": "2026-11-22T03:00:00Z",
  "expiresAt": "2026-11-22T03:00:30Z",
  "state": "QUOTED"
}
~~~

Các ID và thời điểm trên là dữ liệu minh họa. Amount được biểu diễn bằng chuỗi số nguyên trong JSON này để tránh mất độ chính xác ở client dùng kiểu số có giới hạn; API thực tế cần quy định định dạng thống nhất.

Quote cho thanh toán đơn hàng phải ràng buộc thêm order ID và order version. Quote cho chuyển ví phải ràng buộc tài khoản nguồn/đích. Trường purpose ngăn một báo giá dùng để hiển thị giá bị dùng cho rút tiền hoặc hoàn tiền.

Client không cần được nhận mọi metadata nội bộ. Các trường được công bố phải đủ để người dùng hiểu tiền nào bị trừ, tiền nào được nhận, phí và thời hạn, đồng thời server giữ bản có thẩm quyền.

### 6.1. Báo giá lưu server và báo giá có chữ ký

**Báo giá lưu server:** client gửi quote ID; server tải dữ liệu đã lưu trong phạm vi được phép và kiểm tra trạng thái.

**Báo giá có chữ ký:** server có thể xác minh payload chưa bị sửa, issuer, audience, thời hạn và phiên bản khóa theo thiết kế. Tuy nhiên, hệ thống vẫn cần trạng thái dùng một lần hoặc một bản ghi execution duy nhất để chống replay.

Không để client chọn thuật toán xác minh theo ý muốn hoặc chấp nhận payload không được xác minh vì parse thành công. Quản lý quyền khóa ký và quyền sửa dữ liệu quote là một phần của authority.

Đổi nguồn dữ liệu từ database sang token có chữ ký không loại bỏ kiểm tra quyền, hạn mức, số dư, trạng thái nghĩa vụ và chống thực hiện lặp.

### 6.2. Phê duyệt phải gắn với nội dung thực thi

Nếu chuyển đổi trên một ngưỡng cần quản lý duyệt, approval phải ràng buộc ít nhất với chủ thể, nghĩa vụ, tài khoản, cặp tiền, số tiền và điều kiện giá được chấp thuận.

Khi quote hết hạn và phải cấp quote mới, cần quyết định rõ approval cũ có còn áp dụng trong giới hạn nào. Nếu cho phép khoảng trượt giá, khoảng đó phải được phê duyệt và kiểm tra phía máy chủ, không nhận một trường `maxSlippage` bất kỳ làm quyền tự mở rộng số tiền.

Việc gắn authorization với dữ liệu giao dịch và kiểm tra trước khi thực thi phù hợp với [OWASP Transaction Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html). Các trường quote và policy trong bài là mô hình thiết kế minh họa.

## 7. Các bất biến cần bảo vệ

Bài học dùng một mô hình chính: **chuyển đổi giữa hai ví nội bộ của cùng khách hàng**, với quote cố định, sử dụng một lần, toàn bộ ghi sổ nằm trong một database transaction.

Tài khoản đối ứng ngoại tệ và tài khoản phí thuộc hệ thống, được chọn từ cấu hình phía máy chủ. Mô hình này minh họa tính nhất quán dữ liệu; không giả định hệ thống đã mua bán ngoại tệ trên thị trường chỉ vì đã cập nhật hai ví.

Các bất biến:

1. Quote, nghĩa vụ, khách hàng và hai ví thuộc đúng tenant và có quan hệ được phép.
2. Currency của ví nguồn/đích khớp chính xác với cặp tiền trong quote.
3. Người thực hiện có quyền chuyển đổi từ ví nguồn đến ví đích cho mục đích đó.
4. Quote chưa bị hủy, thay thế, hết hạn hoặc thực thi.
5. Quote đang là báo giá được chọn cho nghĩa vụ; nghĩa vụ chưa hoàn tất.
6. Số tiền ghi nợ, ghi có và phí bằng các giá trị đã chốt trong quote.
7. Số dư khả dụng nguồn đủ chi trả; thanh khoản tài khoản đối ứng đích cũng đủ theo chính sách.
8. Mỗi quote và mỗi nghĩa vụ chỉ tạo tối đa một execution có hiệu lực.
9. Các bút toán cân bằng riêng theo từng currency, không cộng trực tiếp hai đồng tiền.
10. Bản ghi execution, biến động số dư, journal, trạng thái quote/nghĩa vụ và outbox commit cùng nhau.

Nếu hệ thống còn có khoản giữ, số dư khả dụng phải trừ cả phần đang giữ. Quote có hiệu lực không tự đồng nghĩa tiền nguồn hoặc thanh khoản đích đã được giữ chỗ. Muốn cam kết cả hai, cần một reservation riêng, có thời hạn và quy tắc giải phóng.

### 7.1. Cân bằng theo currency

Giả sử quote không có phí và chuyển 100 USD thành 2.500.000 VND:

~~~text
USD:
  Ví khách hàng USD           -10.000 minor units
  Tài khoản đối ứng FX USD    +10.000 minor units
  Tổng USD                         0

VND:
  Tài khoản đối ứng FX VND    -2.500.000 units
  Ví khách hàng VND           +2.500.000 units
  Tổng VND                            0
~~~

Đây là cách biểu diễn biến động có dấu để minh họa, chưa phải toàn bộ hệ thống tài khoản kế toán.

Nếu có phí bằng tiền nguồn:

~~~text
-sourceDebit + sourceNet + sourceFee = 0 trong currency nguồn
-targetCredit + targetCredit = 0 trong currency đích
~~~

Không viết bất biến kiểu “USD bị trừ bằng VND được cộng” bằng cách so hai số thô. Chênh lệch tỷ giá, doanh thu phí và quy tắc định giá lại cần tài khoản và chính sách tương ứng.

### 7.2. Ngưỡng phê duyệt và hạn mức không được do client quy đổi

Giả sử giới hạn thao tác được quản lý theo USD nhưng giao dịch bằng EUR. Máy chủ phải chọn nguồn quy đổi và thời điểm đánh giá rủi ro theo policy.

Giá trị quy đổi dùng cho hạn mức có thể khác số tiền giao dịch đã cam kết. Cần lưu được cả hai căn cứ; không dùng một tỷ giá do client gửi để khiến giao dịch lớn trông như nhỏ hơn ngưỡng.

Nếu chính sách giới hạn tổng theo ngày hoặc nhóm nghĩa vụ, việc kiểm tra và cập nhật bộ đếm phải cùng cơ chế bảo vệ đồng thời. Tách thành nhiều yêu cầu nhỏ không được làm mất phạm vi tổng hợp mà chính sách đã quy định.

## 8. State machine của báo giá và thực thi

### 8.1. Luồng nội bộ nguyên tử

~~~mermaid
stateDiagram-v2
    [*] --> QUOTED: Phát hành báo giá
    QUOTED --> EXECUTED: Kiểm tra hợp lệ và ghi sổ nguyên tử
    QUOTED --> EXPIRED: Hết hạn
    QUOTED --> CANCELLED: Hủy theo quyền
    QUOTED --> SUPERSEDED: Chọn báo giá mới cho nghĩa vụ
    EXECUTED --> [*]
    EXPIRED --> [*]
    CANCELLED --> [*]
    SUPERSEDED --> [*]
~~~

Trong mô hình này, cấp một quote mới cho cùng nghĩa vụ sẽ thay thế quote được chọn trước đó bằng cách cập nhật liên kết `active_quote_id` dưới khóa nghĩa vụ. Đây là chính sách minh họa để tránh việc tùy ý chọn giữa nhiều quote; sản phẩm khác có thể định nghĩa cách chọn khác nhưng phải kiểm soát rõ.

Các điều kiện sử dụng:

~~~text
quote.state == QUOTED
obligation.active_quote_id == quote.id
obligation chưa có execution
authoritativeNow < quote.expires_at
phê duyệt và quyền hiện tại hợp lệ
~~~

Thời điểm kiểm tra expiry cần được lấy sau khi đã có các khóa cần thiết, tránh dùng timestamp cũ từ đầu request khi phải chờ lâu. Ranh giới quyết định phải được định nghĩa thống nhất; bài này coi việc claim quote trong transaction là thời điểm chấp nhận, transaction ngắn và không chứa lời gọi mạng.

Job đổi trạng thái EXPIRED có thể chạy chậm. Điều đó không cho phép dùng một quote đã quá hạn.

### 8.2. Hai loại cạnh tranh khác nhau

**Hai request cùng một quote:** chỉ một request được thực thi; request còn lại trả kết quả phù hợp hoặc thông báo đã được dùng.

**Hai quote khác nhau cho cùng một nghĩa vụ:** khóa nghĩa vụ và unique constraint trên execution ngăn thực hiện hai lần. Unique theo quote ID đơn thuần không bảo vệ trường hợp này.

Với hai nghĩa vụ độc lập cùng tiêu một ví nguồn, cần khóa hoặc cập nhật có điều kiện trên số dư dùng chung. Chống dùng lại quote không thay thế kiểm soát số dư.

## 9. Luồng API và transaction

### 9.1. Yêu cầu tạo quote

~~~http
POST /conversion-intents/intent-301/quotes
Content-Type: application/json

{
  "targetCurrency": "VND",
  "expectedIntentVersion": 4
}
~~~

Đối với chuyển ví, số tiền nguồn và tài khoản được xác nhận trong conversion intent đã qua kiểm tra. Đối với thanh toán đơn hàng, máy chủ lấy số tiền từ phiên bản đơn và dịch vụ giá có thẩm quyền.

Rate snapshot có thể được lấy trước transaction ngắn, sau đó kiểm tra tuổi, phiên bản nghĩa vụ và điều kiện liên quan khi phát hành quote. Không đọc đơn ở phiên bản 4, đợi nguồn tỷ giá rồi phát hành quote như thể đơn vẫn là phiên bản 4 nếu nó đã đổi.

Response công bố các giá trị người dùng cần xác nhận: source debit, target credit, phí, cặp tiền, thời hạn và quote ID.

### 9.2. Yêu cầu thực hiện

~~~http
POST /conversion-intents/intent-301/executions
Idempotency-Key: 1d975342-7db9-46c2-af74-51f385d06301
Content-Type: application/json

{
  "quoteId": "fxq-842",
  "expectedIntentVersion": 4
}
~~~

Request không cần gửi lại rate có thẩm quyền. Nếu có gửi số tiền người dùng nhìn thấy để đối chiếu, nó chỉ là điều kiện phát hiện bất đồng; server vẫn dùng snapshot đã lưu.

Có thể áp dụng trình tự sau:

~~~text
1. Xác thực principal và kiểm tra quyền truy cập nghĩa vụ/quote.
2. Claim idempotency operation theo tenant, client và loại thao tác.
3. Khóa nghĩa vụ; kiểm tra quote đang được chọn.
4. Khóa quote; kiểm tra liên kết và trạng thái.
5. Khóa các tài khoản liên quan theo thứ tự ổn định.
6. Kiểm tra quyền thực thi, số dư, thanh khoản, approval, hạn mức và thời hạn ngay trước claim.
7. Tạo execution duy nhất theo nghĩa vụ và quote.
8. Ghi journal và cập nhật số dư theo amount đã chốt.
9. Đổi quote sang EXECUTED, hoàn tất nghĩa vụ và ghi outbox.
10. Lưu kết quả idempotency rồi commit.
~~~

Mọi luồng có khóa nhiều đối tượng, gồm cấp lại quote, hủy, expire và điều chỉnh, cần tuân thủ thứ tự khóa tương thích. Với các tài khoản, sắp xếp theo định danh ổn định thay vì một luồng khóa nguồn trước còn luồng ngược khóa đích trước.

### 9.3. Phác thảo Java service

Đây là mã giả mô tả hợp đồng nghiệp vụ; repository, policy và cơ chế giao dịch cần được triển khai phù hợp với ứng dụng.

~~~java
@Transactional
public ConversionResult execute(Principal principal, ExecuteCommand cmd) {
    ConversionRef ref = intents.findAccessibleRef(principal, cmd.intentId());
    permissions.requireConversionAccess(principal, ref);

    String fingerprint = fingerprints.forExecution(
        principal.tenantId(), principal.clientId(),
        cmd.intentId(), cmd.quoteId(), cmd.expectedIntentVersion()
    );

    OperationClaim op = operations.claimOrLoad(
        principal.tenantId(), principal.clientId(),
        "EXECUTE_FX", cmd.idempotencyKey(), fingerprint
    );

    if (op.completed()) {
        return op.savedResult();
    }

    ConversionIntent intent = intents.lock(
        principal.tenantId(), cmd.intentId()
    );
    FxQuote quote = quotes.lock(principal.tenantId(), cmd.quoteId());

    policies.requireMatchingIntentAndSelectedQuote(intent, quote);
    intent.requireVersion(cmd.expectedIntentVersion());
    intent.requireNotExecuted();

    // Bao gồm ví nguồn, ví đích, tài khoản FX và tài khoản phí cần thiết.
    LockedAccounts locked = accounts.lockAllInStableOrder(
        policies.accountIdsFor(quote)
    );

    permissions.requireExecution(principal, intent, quote, locked);
    policies.requireMatchingCurrenciesAndOwnership(quote, locked);
    approvals.requireValidFor(intent, quote);
    limits.checkAndConsumeAtomically(principal, quote);
    locked.requireSourceFundsAndTargetLiquidity(quote);

    Instant decisionTime = time.authoritativeNowAfterLocks();
    quote.requireUsableAt(decisionTime);

    FxExecution execution = executions.insertUnique(intent, quote);
    Journal journal = journals.buildBalancedFxPostings(execution, quote);
    balances.applyExactly(locked, journal);
    journals.insert(journal);

    quote.markExecuted(execution.id());
    intent.markExecuted(execution.id());
    outbox.appendConversionExecuted(execution);
    return operations.complete(op, execution);
}
~~~

Không tính lại target amount bằng tỷ giá thị trường mới ở giữa bước thực thi. Quote cố định là căn cứ chốt số tiền; rate mới chỉ dùng để phát hành quote mới theo quy trình.

Nếu bất kỳ bước ghi nào thất bại, transaction phải rollback cả hạn mức, số dư, journal và trạng thái. Cấu hình rollback phải bao phủ loại exception thực tế. Phản hồi thành công chỉ được gửi sau commit, không phát trực tiếp thông báo ra ngoài trước khi commit.

### 9.4. Ràng buộc ở database

Ví dụ PostgreSQL tối giản cho execution:

~~~sql
CREATE TABLE fx_execution (
    tenant_id UUID NOT NULL,
    execution_id UUID NOT NULL,
    obligation_id UUID NOT NULL,
    quote_id UUID NOT NULL,
    source_currency VARCHAR(3) NOT NULL,
    source_debit_minor NUMERIC(20, 0) NOT NULL
        CHECK (source_debit_minor > 0),
    source_fee_minor NUMERIC(20, 0) NOT NULL
        CHECK (source_fee_minor >= 0),
    target_currency VARCHAR(3) NOT NULL,
    target_credit_minor NUMERIC(20, 0) NOT NULL
        CHECK (target_credit_minor > 0),
    executed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, execution_id),
    UNIQUE (tenant_id, obligation_id),
    UNIQUE (tenant_id, quote_id),
    CHECK (source_currency <> target_currency),
    CHECK (source_fee_minor < source_debit_minor)
);
~~~

Schema đầy đủ cần khóa ngoại có tenant tới quote, nghĩa vụ và journal. Currency/account binding và amount khớp quote phải được bảo vệ trong thiết kế ghi dữ liệu, không chỉ kiểm tra bằng các `CHECK` ở trên.

Có thể claim quote bằng cập nhật có điều kiện, trong cùng transaction:

~~~sql
UPDATE fx_quote
SET state = 'EXECUTED',
    execution_id = :execution_id,
    used_at = :decision_time
WHERE tenant_id = :tenant_id
  AND quote_id = :quote_id
  AND obligation_id = :obligation_id
  AND state = 'QUOTED'
  AND expires_at > :decision_time
RETURNING quote_id;
~~~

Không trả dòng nào nghĩa là chưa claim được. Nếu các ghi khác đã thực hiện trong transaction này, phải rollback thay vì bỏ qua lỗi và vẫn commit bút toán.

Câu UPDATE trên không tự chứng minh người dùng có quyền, quote là báo giá đang được chọn hoặc ví còn đủ tiền. Nó là một phần của toàn bộ kiểm tra có bảo vệ.

Nếu khóa đã bảo vệ quote và nghĩa vụ, có thể cập nhật thông qua repository trong cùng transaction. Điều quan trọng là trạng thái không bị quyết định trên bản đọc cũ rồi ghi đè vô điều kiện.

## 10. Tính toán chính xác và chính sách làm tròn

Không dùng `double` cho amount hoặc rate có thẩm quyền. Không biến chuỗi tỷ giá thành số thực nhị phân rồi mới đưa trở lại kiểu thập phân.

Ví dụ hàm tính tiền đích cho mô hình trừ phí nguồn trước:

~~~java
static long targetMinor(
        long sourceDebitMinor,
        long sourceFeeMinor,
        int sourceExponent,
        int targetExponent,
        BigDecimal targetUnitsPerSourceUnit,
        RoundingMode roundingMode) {

    // Ví dụ chỉ hỗ trợ exponent 0..6; lấy từ registry phía server.
    if (sourceExponent < 0 || sourceExponent > 6
            || targetExponent < 0 || targetExponent > 6) {
        throw new IllegalArgumentException("Unsupported exponent");
    }
    if (sourceDebitMinor <= 0 || sourceFeeMinor < 0
            || sourceFeeMinor >= sourceDebitMinor) {
        throw new IllegalArgumentException("Invalid source amounts");
    }
    if (targetUnitsPerSourceUnit == null
            || targetUnitsPerSourceUnit.signum() <= 0
            || targetUnitsPerSourceUnit.precision() > 24
            || targetUnitsPerSourceUnit.scale() < 0
            || targetUnitsPerSourceUnit.scale() > 12
            || roundingMode == null) {
        throw new IllegalArgumentException("Invalid rate or rounding");
    }

    long sourceNetMinor = Math.subtractExact(
        sourceDebitMinor, sourceFeeMinor
    );
    BigDecimal sourceMajor = BigDecimal.valueOf(
        sourceNetMinor, sourceExponent
    );
    BigDecimal rawTargetMinor = sourceMajor
        .multiply(targetUnitsPerSourceUnit)
        .movePointRight(targetExponent);

    long result = rawTargetMinor
        .setScale(0, roundingMode)
        .longValueExact();

    if (result <= 0) {
        throw new IllegalArgumentException("Target amount too small");
    }
    return result;
}
~~~

Đây là hàm minh họa cho currency và miền giá trị được hỗ trợ; không thay thế validation cặp tiền, ngưỡng số tiền và tỷ giá theo sản phẩm. Input rate phải được parse có giới hạn độ dài trước khi gọi hàm, rồi kiểm tra miền giá trị hợp lệ cho đúng cặp tiền.

Ví dụ gọi với rate được tạo từ chuỗi:

~~~java
long target = targetMinor(
    10_000L, 0L, 2, 0,
    new BigDecimal("25000"),
    RoundingMode.HALF_EVEN
);
// target = 2_500_000 VND
~~~

`HALF_EVEN` chỉ là lựa chọn của ví dụ. Policy phải quy định rõ chế độ và điểm làm tròn. Đặc tả [Java BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html) giải thích các phép toán thập phân và kiểm soát rounding.

### 10.1. Không làm tròn ở nhiều điểm ngoài chính sách

Ví dụ cùng rate 1,6 đơn vị tiền đích trên một đơn vị tiền nguồn:

~~~text
Hai khoản nguồn, mỗi khoản 1 đơn vị:

Làm tròn từng khoản đến số nguyên:
  round(1,6) + round(1,6) = 2 + 2 = 4

Cộng trước rồi làm tròn:
  round(1,6 + 1,6) = round(3,2) = 3
~~~

Cả hai có thể phù hợp trong các hợp đồng khác nhau, nhưng hệ thống phải chọn nhất quán. Nếu client được tùy ý chia nhỏ nghĩa vụ rồi ghép số tiền đích, chênh lệch làm tròn có thể trở thành đường lạm dụng.

Nếu chia một tổng tiền đã chốt cho nhiều dòng, dùng quy tắc phân bổ phần dư có thứ tự ổn định để tổng các dòng bằng tổng đã cam kết. Không tính mỗi phần bằng các rate mới rồi coi tổng đó là quote gốc.

### 10.2. Không dùng sai số tùy ý để bỏ qua lệch giá

Điều kiện kiểu:

~~~text
abs(clientAmount - serverAmount) < 1000
~~~

không phù hợp nếu currency và đơn vị không được xét rõ. Một dung sai lớn có thể trở thành giảm giá lặp lại.

Ở thời điểm thực thi quote cố định, nên so đúng các giá trị đã chốt theo minor unit. Nếu có dung sai cho đối soát hoặc slippage, phải có phạm vi, lý do và chính sách riêng; không dùng nó để âm thầm thay số tiền người dùng đã chấp thuận.

## 11. Idempotency, replay và thực hiện lặp

### 11.1. Idempotency xử lý retry của cùng một yêu cầu

Một bảng thao tác có thể có unique key theo:

~~~text
(tenant_id, client_id, operation_type, idempotency_key)
~~~

Fingerprint gồm ít nhất intent ID, quote ID và phiên bản nghĩa vụ có ảnh hưởng đến hành động. Bản ghi cần liên kết với execution và kết quả đã commit.

| Tình huống | Hành vi cần có |
| --- | --- |
| Cùng key, cùng payload, đã thành công | Trả lại kết quả được phép xem; không tạo execution mới |
| Cùng key, payload khác | Trả lỗi xung đột |
| Cùng key đến đồng thời | Chỉ một thao tác được thực hiện; thao tác còn lại chờ hoặc retry theo hợp đồng |
| Khác key, cùng quote | Quote và unique execution chặn thực hiện lần hai |
| Khác key, khác quote, cùng nghĩa vụ | Khóa nghĩa vụ và unique theo obligation chặn thực hiện lần hai |
| Key cũ đã hết thời gian lưu | Nghĩa vụ hoàn tất vẫn không được thực hiện lại |
| Timeout không rõ kết quả | Tra cứu hoặc retry cùng key trước khi tạo ý định mới |

Xác thực và kiểm tra quyền xem đối tượng phải diễn ra trước khi trả lại kết quả cũ. Key không được trở thành cách đọc kết quả của tenant khác hoặc sau khi quyền đã bị thu hồi.

Không lưu idempotency key vào một cache riêng rồi ghi sổ độc lập mà thiếu cơ chế bảo đảm nhất quán. Crash giữa hai bước có thể làm mất bằng chứng chống lặp hoặc đánh dấu thành công khi chưa có execution.

### 11.2. Quote dùng một lần và nghĩa vụ dùng một lần giải quyết hai vấn đề

Một người dùng có thể yêu cầu nhiều quote trước khi chọn. Nếu mỗi quote chỉ dùng một lần nhưng một nghĩa vụ được thanh toán qua hai quote khác nhau, hệ thống vẫn ghi nhận trùng.

Vì vậy cần cả:

~~~text
Mỗi quote: tối đa một execution.
Mỗi nghĩa vụ trong mô hình bài: tối đa một execution có hiệu lực.
Mỗi execution: một tập bút toán được áp dụng đúng một lần.
~~~

Việc phát hành quote mới không tạo ra quyền thực thi lại một nghĩa vụ đã hoàn tất. Muốn chuyển đổi thêm tiền, người dùng phải tạo một intent mới qua quyền, số dư và hạn mức tương ứng.

### 11.3. Không “làm mới thời hạn” bằng thao tác đọc

Một endpoint GET quote không được tự gia hạn expiry. Việc đổi ngày hết hạn của quote cũ làm mất khả năng giải thích cam kết ban đầu.

Nếu muốn refresh:

1. Kiểm tra nghĩa vụ chưa thực hiện hoặc đang chờ một execution chưa xác minh.
2. Lấy dữ liệu tỷ giá đủ điều kiện và tạo quote mới.
3. Kiểm tra phiên bản nghĩa vụ, chính sách và phê duyệt.
4. Thay quote được chọn một cách nguyên tử.
5. Yêu cầu người dùng chấp thuận số tiền và điều kiện mới khi cần.

Không tạo quote thay thế trong lúc execution bên ngoài còn UNKNOWN rồi dùng nó để thực hiện nghĩa vụ lần nữa.

## 12. Khi nhà cung cấp thực hiện chuyển đổi bên ngoài

State machine QUOTED → EXECUTED ở trên chỉ phù hợp khi toàn bộ tác động có thể commit trong cùng database. Lời gọi HTTP đến nhà cung cấp không nằm trong transaction nội bộ.

Một mô hình tích hợp cần thêm trạng thái cho execution:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Chấp nhận quote và giữ tiền
    PENDING --> SUCCEEDED: Xác nhận thực thi và ghi sổ
    PENDING --> FAILED: Xác nhận không thực thi và giải phóng
    PENDING --> UNKNOWN: Timeout hoặc phản hồi không rõ
    UNKNOWN --> SUCCEEDED: Tra cứu xác nhận thành công
    UNKNOWN --> FAILED: Tra cứu xác nhận không có tác động
    SUCCEEDED --> [*]
    FAILED --> [*]
~~~

Đây là mô hình mở rộng, không dùng đồng thời một cách máy móc với schema execution tối giản của phần trước. Ở mô hình này, bản ghi execution tồn tại từ lúc PENDING và đã chiếm quyền thực hiện duy nhất của nghĩa vụ.

Luồng tham khảo:

1. Kiểm tra quote còn hợp lệ tại điểm chấp nhận, quyền và phê duyệt.
2. Trong transaction nội bộ, tạo execution PENDING, đánh dấu quote đã được nhận thực hiện, giữ tiền nguồn và ghi outbox.
3. Worker gửi yêu cầu bằng định danh operation ổn định của execution.
4. Nếu timeout, giữ trạng thái UNKNOWN và không coi tiền là được giải phóng.
5. Tra cứu hoặc retry theo hợp đồng idempotency của nhà cung cấp.
6. Khi có bằng chứng thành công, chuyển khoản giữ thành ghi nợ/ghi có hoặc ghi nhận khoản phải thu/phải trả thích hợp.
7. Chỉ giải phóng khi có cơ sở xác định không có tác động bên ngoài hoặc có quy trình xử lý bù trừ được kiểm soát.

Một quote đã được chấp nhận hợp lệ trước expiry cần được xử lý theo cam kết dành cho execution đó. Không tự đổi số tiền khách hàng sau timeout vì tỷ giá thị trường đã thay đổi. Nếu nhà cung cấp không bảo đảm cùng cam kết, sản phẩm phải có chính sách về rủi ro giá, thất bại và chấp thuận lại.

Không chuyển sang nhà cung cấp B chỉ vì A timeout mà chưa xác minh A chưa thực hiện. Nếu cả hai thành công, idempotency key riêng của từng nhà cung cấp không ngăn được giao dịch kép.

Webhook phải được xác minh nguồn và liên kết đúng provider object, execution, cặp tiền và số tiền. Cần deduplicate event và bảo vệ trạng thái thực thi vì nhiều event khác ID có thể cùng mô tả một operation. Không cho event cũ đảo ngược một quyết định cuối cùng.

Outbox và cơ chế retry có thể phát lại sự kiện. Bên nhận phải ghi nhận theo execution/event nghiệp vụ để không cộng tiền thêm lần nữa.

## 13. Thanh toán, capture và hoàn tiền không được tự chọn lại tỷ giá

### 13.1. Khóa cả amount lẫn currency của yêu cầu thanh toán

Nếu đơn 100 USD đã được chấp thuận thanh toán bằng 2.500.000 VND, request tới payment provider phải mang đúng amount và currency theo quy ước adapter.

Không chỉ khóa rate rồi để amount nguồn hoặc currency đích thay đổi. Cũng không dùng currency hiển thị hiện tại của trình duyệt để dựng lại request thanh toán.

Khi provider tự thực hiện chuyển đổi cho khách hàng, không đồng thời áp dụng thêm một phép chuyển đổi của merchant như thể đó là cùng một dịch vụ. Cần xác định bên nào chịu trách nhiệm về giá, phí và cam kết được trình bày cho người trả tiền.

### 13.2. Đơn hàng thay đổi làm thay đổi quyết định

Thay số lượng, khuyến mãi, phí vận chuyển, tài khoản nguồn hoặc người nhận có thể làm quote không còn đúng phạm vi.

Với thay đổi cần tính giá lại, phải tạo phiên bản nghĩa vụ và quote thích hợp, đánh giá phê duyệt và xử lý khoản giữ cũ theo quy trình. Không chỉnh amount trong quote đã ký hoặc đã được chấp thuận.

Nếu có capture một phần, phải định nghĩa quan hệ giữa số tiền từng phần và tổng đã được chấp thuận. Không được lấy tỷ giá mới cho mỗi phần rồi coi tổng tiền đó vẫn là giao dịch đã chốt.

### 13.3. Hoàn tiền là một nghĩa vụ có kiểm soát riêng

Ví dụ người mua bị thu 2.500.000 VND. Chính sách hoàn lại đúng khoản thanh toán gốc phải xét số tiền đã thu bằng VND và các khoản hoàn trước đó.

Không mặc định lấy 100 USD nhân với rate mới để quyết định khoản hoàn. Cách đó có thể hoàn vượt khoản thu hoặc tạo cơ hội nhận chênh lệch không thuộc chính sách.

Một bất biến phù hợp khi hoàn bằng currency của capture gốc:

~~~text
refundedMinor + pendingRefundMinor + newRefundMinor
    <= refundableCapturedMinor
~~~

Mọi amount trong bất biến này cùng currency và cùng quy ước đơn vị. Các khoản hoàn đang chờ cũng phải chiếm phần được hoàn, để hai request đồng thời không cùng vượt qua kiểm tra.

Nếu sản phẩm hỗ trợ hoàn sang currency khác, cần chính sách rõ về bên chịu chênh lệch, tỷ giá, phí, báo giá hoàn tiền và sự chấp thuận cần thiết. Một giao dịch chuyển đổi mới không được ngụy trang thành thao tác đảo ngược đơn giản.

Với hoàn một phần, cần phân bổ phần dư làm tròn và phí sao cho tổng các phần không vượt quyền hoàn của giao dịch gốc. Mỗi refund obligation phải có định danh chống lặp riêng và liên kết được với capture ban đầu.

## 14. Các đường lạm dụng và điểm chặn

| Hành vi | Lỗi thiết kế bị khai thác | Kiểm soát |
| --- | --- | --- |
| Sửa rate hoặc target amount trong JSON | Client là nguồn quyết định giá | Quote do server phát hành; thực thi amount đã lưu |
| Đổi USD thành JPY nhưng giữ amount integer | Không gắn currency và đơn vị | Money type, registry và adapter rõ ràng |
| Dùng quote khách hàng khác | Chỉ kiểm tra quote ID tồn tại | Quyền theo đối tượng và tenant/customer binding |
| Dùng quote đơn A cho đơn B | Thiếu liên kết nghĩa vụ và version | Quote gắn order/intent và phiên bản |
| Dùng quote hiển thị cho rút tiền | Không ràng buộc mục đích | Purpose và quyền theo loại thao tác |
| Gửi cặp tiền đảo chiều | Chỉ có một con số rate mơ hồ | Cặp có hướng và rate áp dụng đúng chiều |
| Dùng quote hết hạn khi job chưa chạy | Tin trạng thái lưu mà bỏ timestamp | Kiểm tra expiry tại điểm chấp nhận |
| Gửi nhiều key cho cùng quote | Chỉ có cache idempotency | Quote và execution được bảo vệ ở database |
| Gửi hai quote cho cùng nghĩa vụ | Chỉ unique theo quote | Khóa và unique theo obligation |
| Chia nhỏ để ăn chênh lệch làm tròn | Client chọn phạm vi cộng/làm tròn | Quy tắc tổng hợp, phân bổ và hạn mức theo phạm vi |
| Giữ nhiều quote rồi chọn rate có lợi quá hạn | Gia hạn hoặc chọn quote tùy tiện | Expiry, quote được chọn và quy tắc thay thế |
| Sửa tỷ giá để né ngưỡng duyệt | Risk amount do client tính | Đánh giá ngưỡng phía server theo policy |
| Nhân viên tự override rate rồi tự duyệt | Quyền vận hành quá rộng | Tách quyền, giới hạn override và audit |
| Timeout rồi thực hiện lại ở provider khác | Coi lỗi mạng là thất bại nghiệp vụ | UNKNOWN, tra cứu, đối soát và giữ định danh |
| Hoàn tiền theo rate hiện tại không kiểm soát | Không ràng buộc capture gốc | Hạn mức hoàn, currency gốc và policy riêng |

Rate limit và kiểm tra bất thường giúp giảm khai thác ở tần suất lớn. Chúng không thay thế việc kiểm soát số tiền và trạng thái: chỉ hai request hợp lệ về tốc độ cũng có thể gây ghi sổ kép.

## 15. Kiểm thử tình huống tấn công logic

Kiểm thử cần xem toàn bộ chuỗi tạo quote, phê duyệt, thực thi, retry và hoàn tiền trong môi trường kiểm soát. Không chỉ kiểm tra HTTP 200 hay chữ ký hợp lệ.

### 15.1. Ma trận tình huống

| Nhóm | Tình huống | Kết quả cần chứng minh |
| --- | --- | --- |
| Nguồn quyết định | Sửa rate, fee hoặc target amount phía client | Server dùng quote có thẩm quyền hoặc từ chối bất đồng |
| Đơn vị | USD exponent 2 sang currency exponent 0 | Không sai hệ số 100 |
| Adapter | Currency có quy ước provider đặc biệt | Payload provider đúng hợp đồng thao tác |
| Chiều | Gửi quote USD → VND cho yêu cầu VND → USD | Từ chối |
| Quyền | Tenant A dùng quote/intent/ví tenant B | Không đọc hoặc thay đổi dữ liệu ngoài quyền |
| Phạm vi | Quote hợp lệ nhưng sai tài khoản, purpose hoặc order version | Từ chối, không ghi tiền |
| Phê duyệt | Quote mới làm thay đổi amount vượt quyền đã duyệt | Đánh giá lại hoặc yêu cầu phê duyệt mới |
| Hiệu lực | now bằng expiresAt | Không chấp nhận quote |
| Hiệu lực | Request chờ khóa đến khi quote hết hạn | Kiểm tra thời gian mới trước claim |
| Thay thế | Quote cũ còn timestamp hợp lệ nhưng đã SUPERSEDED | Không thực thi quote cũ |
| Retry | Cùng key và payload sau khi mất response | Cùng execution, không ghi sổ thêm |
| Key conflict | Cùng key nhưng đổi quote hoặc intent | Xung đột, không lộ kết quả sai phạm vi |
| Replay | Hai key cùng quote | Tối đa một execution |
| Replay | Hai quote cùng nghĩa vụ | Tối đa một execution |
| Số dư | Hai nghĩa vụ cùng tiêu một ví không đủ cho cả hai | Không âm số dư, chỉ phần hợp lệ được thực hiện |
| Thanh khoản | Ví nguồn đủ nhưng tài khoản FX đích không đủ | Không chỉ trừ ví nguồn rồi bỏ dở |
| Nguyên tử | Lỗi sau ghi nợ trước ghi có | Rollback toàn bộ |
| Nguyên tử | Lỗi trước khi lưu kết quả idempotency | Không có trạng thái thành công tách rời execution |
| Feed | Rate quá cũ, âm, 0, sai cặp hoặc ngoài biên policy | Không phát hành quote thực thi sai |
| Precision | Amount/rate có quá nhiều ký tự hoặc scale quá lớn | Từ chối có kiểm soát |
| Làm tròn | Chia một tổng thành nhiều phần | Tổng phân bổ khớp cam kết, không tạo lợi ích ngoài policy |
| Provider | Timeout rồi webhook thành công đến trễ | Không giải phóng hoặc ghi tiền hai lần |
| Hoàn tiền | Hai refund cùng tranh phần còn được hoàn | Tổng thành công và pending không vượt giới hạn |
| Vận hành | Người sửa rate tự duyệt vượt thẩm quyền | Quy trình chặn và có audit |

Các test đồng thời cần nhiều transaction/kết nối database thật và cơ chế đồng bộ điểm bắt đầu. Mock repository không chứng minh được hiệu lực của khóa hoặc unique constraint.

### 15.2. Các khẳng định sau mỗi kịch bản

~~~text
Không có ví bị âm ngoài chính sách đã định.
Mỗi nghĩa vụ có tối đa một execution hiệu lực.
Mỗi quote chỉ liên kết tối đa một execution.
Amount và currency execution khớp quote đã chấp thuận.
Tổng biến động bằng 0 riêng theo từng currency của journal.
Không có journal hoặc biến động số dư bị áp dụng lặp.
Không có execution thành công mà thiếu tập bút toán tương ứng.
Quote/intent hoàn tất liên kết đúng execution đã commit.
Các trạng thái bên ngoài chưa biết không bị giải phóng tiền tùy tiện.
Tổng refund thành công và đang chờ không vượt phần được hoàn.
~~~

Khi đối chiếu các bảng, đọc trong snapshot nhất quán hoặc sau khi thao tác đã ổn định để tránh báo sai do đọc hai thời điểm khác nhau.

Có thể bổ sung sinh chuỗi thao tác ngẫu nhiên: tạo quote, thay quote, chấp thuận, retry, expire và thực hiện. Sau mỗi bước, kiểm tra bất biến để tìm đường đi mà các test từng endpoint riêng lẻ bỏ sót.

## 16. Audit và kiểm soát vận hành

Một execution cần giải thích được bằng chuỗi dữ liệu:

~~~text
nghĩa vụ và phiên bản
  -> rate snapshot và nguồn
  -> policy phí/spread/rounding
  -> quote được phát hành
  -> principal và phê duyệt
  -> execution
  -> journal, số dư và provider reference
~~~

Các dữ liệu nên lưu gồm tenant, principal/service identity, tài khoản liên quan, source/target currency, debit/fee/credit, rate snapshot, thời điểm feed và quote, expiry, policy version, idempotency operation, lý do quyết định và kết quả.

Không đưa khóa ký, token provider, OTP hoặc bí mật xác thực vào log. Giới hạn quyền xem log chứa thông tin tài chính và thông tin khách hàng.

Những thay đổi có thể ảnh hưởng tiền cần kiểm soát quyền: thêm nguồn feed, đổi spread, tăng tuổi tối đa của rate, thay rounding, mở cặp tiền, sửa mapping tài khoản đối ứng hoặc cho phép override. Với thay đổi cần phê duyệt độc lập, phải kiểm tra người tạo và người duyệt có thẩm quyền khác nhau theo chính sách.

Override không nên sửa âm thầm quote cũ. Cần tạo một quyết định mới có phạm vi, thời hạn, lý do và dấu vết, rồi yêu cầu lại phê duyệt hoặc chấp thuận khi điều kiện giao dịch thay đổi.

Theo dõi các dấu hiệu vận hành:

- Quote bị từ chối vì expiry, superseded hoặc sai binding.
- Tăng đột biến số quote cho một nghĩa vụ hoặc số request conflict.
- Feed chậm, rate ngoài biên, fallback tăng hoặc policy thay đổi bất thường.
- Execution UNKNOWN kéo dài, webhook không liên kết được hoặc amount/currency không khớp.
- Journal không cân bằng theo currency, số dư lệch với sổ hoặc khoản giữ mồ côi.
- Hoàn tiền lặp và chuỗi giao dịch nhỏ tạo chênh lệch làm tròn đáng kể.

Đối soát phát hiện sai lệch chứ không cấp quyền sửa số dư tùy ý. Điều chỉnh cần có căn cứ, quyền, liên kết giao dịch gốc và audit.

## 17. Tiêu chí hoàn thành thiết kế

Một thiết kế currency conversion authority cần trả lời rõ:

1. Ai được cấp rate, ai phát hành quote và ai được thực thi?
2. Quote nào là tham khảo, quote nào là cam kết thực thi?
3. Số tiền thực tế, currency, đơn vị, chiều rate và phí được chốt ở đâu?
4. Quote ràng buộc với tenant, chủ thể, tài khoản, purpose và nghĩa vụ nào?
5. Phiên bản giá, phê duyệt và expiry được kiểm tra tại thời điểm nào?
6. Cách nào ngăn hai key hoặc hai quote thực hiện cùng nghĩa vụ?
7. Cách nào giữ số dư và journal nhất quán khi có cạnh tranh hoặc crash?
8. Nếu provider timeout, hệ thống giữ tiền và xác minh kết quả ra sao?
9. Capture một phần và hoàn tiền dùng quy tắc amount/rounding nào?
10. Có thể truy từ từng bút toán về rate snapshot và quyết định đã chấp thuận không?

Một phép tính quy đổi chỉ an toàn về nghiệp vụ khi nguồn quyết định, phạm vi sử dụng và số lần thực thi đều được bảo vệ. Client không thể biến lựa chọn hiển thị, dữ liệu tỷ giá hoặc một quote hợp lệ thành quyền thay đổi số tiền ngoài cam kết.
