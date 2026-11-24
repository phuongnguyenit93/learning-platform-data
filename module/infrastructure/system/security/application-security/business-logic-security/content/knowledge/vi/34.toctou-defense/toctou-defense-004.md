# Price recheck

## 1. Kiểm tra lại giá phải bảo vệ được thời điểm chốt giá

Một người mua xem giỏ hàng với tổng 195.000 đồng rồi bấm đặt hàng. Trong lúc đó, giá sản phẩm thay đổi, mã giảm giá hết lượt hoặc một request khác sửa giỏ hàng. Nếu backend dùng tổng tiền cũ của client, đơn có thể bị bán sai giá. Nếu backend lấy giá mới rồi tự thu số tiền cao hơn, tác dụng lại không còn khớp mức người mua đã xác nhận.

**Price recheck** là việc xác minh giá và các thành phần tính tiền bằng dữ liệu tin cậy tại một điểm quyết định được xác định rõ, rồi ràng buộc kết quả với đơn hàng và lệnh thanh toán. Đây là một biện pháp phòng vệ TOCTOU: điều đúng khi hiển thị hoặc tạo báo giá chưa chắc còn đúng khi sử dụng để tạo tác dụng nghiệp vụ.

Mục tiêu không chỉ là gọi lại hàm `calculateTotal()`. Cần bảo đảm:

- Giá được áp dụng có căn cứ từ phía server và đúng chính sách bán hàng.
- Đúng sản phẩm, biến thể, số lượng, quyền hưởng giá, tiền tệ và điều kiện giao dịch được kiểm tra.
- Việc so sánh, tiêu thụ quyền ưu đãi và chốt đơn không để lại một khoảng trống cạnh tranh mới.
- Đơn và lệnh thanh toán sử dụng cùng kết quả đã chốt, không tự đọc lại giá thay đổi ở bước sau.
- Retry không tạo thêm đơn hoặc thêm khoản thu cho cùng ý định mua hàng.

OWASP khuyến nghị kiểm tra chi tiết giỏ hàng và tính lại tổng phía server từ dữ liệu tin cậy trước khi tạo đơn. [OWASP: Secure Integration of Third-Party Payment Gateways](https://cheatsheetseries.owasp.org/cheatsheets/Third_Party_Payment_Gateway_Integration_Cheat_Sheet.html)

Các tên trạng thái, bảng và chính sách trong bài là mô hình minh họa. Những số tiền dùng đồng trong ví dụ, không phải một quy ước cho mọi tiền tệ hoặc mọi gateway.

## 2. Một ví dụ về khoảng trống giữa hiển thị và sử dụng giá

Giả sử giỏ hàng chứa hai sản phẩm cùng loại:

```text
Đơn giá tại thời điểm xem:        100.000 đồng
Số lượng:                                2
Tạm tính:                         200.000 đồng
Giảm giá:                          20.000 đồng
Phí giao hàng:                     15.000 đồng
Tổng được hiển thị:                195.000 đồng
```

Một lịch xen kẽ:

| Thời điểm | Checkout A | Thay đổi B |
|---|---|---|
| T1 | Nhận báo giá Q17: tổng 195.000 | |
| T2 | Người mua xác nhận Q17 | |
| T3 | | Đơn giá trong bảng giá đổi thành 110.000 |
| T4 | Tạo đơn từ dữ liệu chưa được ràng buộc | |
| T5 | Gửi lệnh thanh toán | |

Theo chính sách tính lại giá tại lúc nhận đơn, tổng hiện tại sẽ là 215.000 đồng nếu các thành phần khác giữ nguyên. Backend phải nhận diện sự khác biệt và yêu cầu xác nhận theo hợp đồng sản phẩm; không coi 195.000 client gửi là giá có thẩm quyền, cũng không âm thầm thay bằng 215.000 rồi tiếp tục thu tiền.

Theo một chính sách khác, Q17 có thể là báo giá được cam kết giữ đến một thời hạn nhất định. Nếu Q17 còn hiệu lực, đúng phạm vi và đủ các điều kiện đi kèm, việc chấp nhận 195.000 có thể hoàn toàn đúng dù bảng giá đã đổi. Vì vậy, “luôn lấy giá mới nhất” không phải định nghĩa đầy đủ của an toàn.

Nguy cơ còn xuất hiện khi tổng cuối không đổi. Ví dụ, một request thay sản phẩm bằng biến thể khác nhưng tổng vẫn là 195.000. Chỉ so sánh một con số không chứng minh người mua đã xác nhận đúng nội dung đơn hoặc có quyền mua biến thể mới với mức giá đó.

## 3. Chọn chính sách giá trước khi triển khai recheck

### 3.1. Tính lại tại thời điểm chấp nhận đơn

Với chính sách minh họa `REPRICE_AT_ORDER_ACCEPTANCE`, giá giỏ hàng trước đó là dữ liệu để trình bày và xác nhận, còn server đánh giá lại tại điểm chốt đơn. Nếu các điều kiện quan trọng khác mức đã xác nhận, server trả một báo giá mới và chưa tạo tác dụng thanh toán.

Luồng điển hình:

```text
xem giỏ -> nhận báo giá Q17 -> xác nhận Q17
    -> recheck thấy cần thay đổi
    -> trả báo giá Q18, chưa tạo đơn thanh toán
    -> người mua xác nhận Q18 bằng lệnh mới
    -> recheck và chốt đơn nếu điều kiện còn hợp lệ
```

Không để client bật một cờ `acceptAnyPrice=true` để bỏ qua bước cần thiết. Nếu sản phẩm có chế độ chấp nhận trong một giới hạn giá đã được người dùng cấp trước, giới hạn, phạm vi và hiệu lực phải là một phần của ý định được server quản lý.

### 3.2. Giữ báo giá đến thời hạn đã định

Với `HONOR_VALID_QUOTE`, một báo giá bất biến có thể chốt mức giá được quyền sử dụng đến thời hạn hoặc điều kiện xác định. Price recheck lúc này xác minh tính hợp lệ của báo giá: chủ thể/tenant, giỏ và phiên bản nội dung, tiền tệ, thời hạn, điều kiện ưu đãi, khả năng bị thu hồi theo chính sách và trạng thái đã sử dụng.

Không tự so sánh với bảng giá mới rồi bác mọi báo giá cũ nếu chính sách đã hứa giữ giá. Ngược lại, một dòng cache tổng tiền không tự trở thành một cam kết giữ giá. Server cần phân biệt báo giá ước tính với báo giá có hiệu lực chấp nhận đơn.

### 3.3. Không trộn hai chính sách ở các tầng

| Tình huống | Cách xử lý cần được xác định |
|---|---|
| Bảng giá đổi sau khi có quote | Tính lại hoặc giữ quote theo đúng loại chính sách |
| Quote hết hạn trước điểm chốt | Tạo quote mới hoặc từ chối theo hợp đồng, không tự sửa thời hạn |
| Coupon có số lượt giới hạn | Quote đã đặt chỗ lượt dùng hay chỉ nêu điều kiện để xét lại? |
| Người mua mất quyền hưởng giá nhóm | Quote có còn được giữ hay quyền đó phải tồn tại đến lúc chốt? |
| Giá mới thấp hơn | Có tự áp dụng giảm giá trong phạm vi đã được cấp hay cần xác nhận lại? |
| Phí giao hàng hoặc địa chỉ thay đổi | Phải đánh giá lại các dữ kiện ảnh hưởng giao dịch |
| Đơn đã được chốt, thanh toán đang chờ | Dùng giá đã chốt hoặc quy trình sửa đơn riêng, không tùy ý reprice |

Chính sách do server lựa chọn theo loại giao dịch, không lấy từ tham số không được kiểm chứng của client. Giao diện, order service và payment worker phải hiểu cùng một điểm chốt, tránh frontend nói giữ giá trong khi worker lại tự đọc bảng giá mới.

## 4. Viết bất biến về giá và nguồn dữ liệu

### 4.1. Các bất biến cần giữ

Một thiết kế checkout có thể dùng các bất biến sau:

1. Giá áp dụng là kết quả từ nguồn tin cậy theo chính sách, không phải tổng do client tự khai.
2. Quote được xác nhận gắn đúng người mua hoặc phạm vi được cấp, tenant, phiên bản giỏ và dữ liệu quan trọng của giao dịch.
3. Tổng chốt bằng tổng các thành phần sau khi áp dụng cùng quy tắc tính và làm tròn.
4. Quyền sử dụng ưu đãi hữu hạn không được tiêu thụ hoặc đặt chỗ vượt giới hạn.
5. Một checkout attempt không tạo nhiều đơn logic do retry hoặc thay idempotency key.
6. Payment attempt lấy số tiền, tiền tệ và order reference từ đơn đã chốt.
7. Một kết quả thanh toán chỉ hoàn tất đúng đơn và payment attempt phù hợp, có xử lý lặp và đối soát.

Nếu cần giữ chỗ tồn kho, đó là bất biến liên quan nhưng khác với giá. Price recheck đúng không chứng minh còn hàng; kiểm tra tồn kho đúng cũng không chứng minh giá đúng. Điểm chốt cần phối hợp các reservation bắt buộc theo hợp đồng.

### 4.2. Những dữ kiện phải được xem xét

| Dữ kiện | Nguồn có thẩm quyền và ràng buộc |
|---|---|
| SKU, biến thể, tùy chọn và số lượng | Giỏ do server quản lý hoặc đầu vào đã được kiểm tra, có phiên bản |
| Đơn giá, bảng giá và nhóm giá | Nguồn định giá đúng tenant, thị trường, khách hàng và điều kiện |
| Quyền hưởng giá nội bộ/đối tác | Quan hệ hoặc policy tin cậy, không nhận role tự khai |
| Coupon và quy tắc kết hợp | Chính sách phía server, trạng thái sử dụng và reservation khi cần |
| Địa chỉ, phương thức giao và phụ phí | Nội dung đã được chuẩn hóa, phiên bản và dịch vụ phí được tin cậy |
| Thuế và các khoản tính thêm | Bộ quy tắc/dịch vụ phù hợp với giao dịch, có căn cứ và phiên bản cần thiết |
| Tiền tệ, tỷ giá nếu có | Quy ước đơn vị rõ ràng, quote tỷ giá và thời hạn tương ứng |
| Merchant/payment account | Cấu hình server đúng tenant và tuyến thanh toán được cấp |

Không chỉ bỏ qua `total` của client rồi tin `unitPrice`, `discountPercent` hoặc `customerTier` trong cùng request. Client có thể gửi các giá trị đó để đối chiếu hiển thị, nhưng server phải tự xác định hoặc xác minh theo cơ chế có thẩm quyền.

### 4.3. Tính tiền theo một quy tắc xác định

Công thức khái quát có thể là:

```text
subtotal       = tổng thành tiền từng dòng
discountTotal  = tổng giảm giá được chấp nhận theo quy tắc
grandTotal     = subtotal - discountTotal
                 + shippingTotal + taxTotal + feeTotal
```

Hệ thống thực tế phải định nghĩa thứ tự áp dụng và phạm vi giảm giá: theo dòng, toàn giỏ, phí giao hàng hoặc thành phần khác. Không thay đổi thứ tự tùy tầng hoặc dùng một cách làm tròn ở quote rồi một cách khác khi tạo payment.

Dùng biểu diễn tiền chính xác: số nguyên trong đơn vị quy định hoặc kiểu decimal với scale và quy tắc làm tròn rõ. Không coi mọi tiền tệ đều có hai chữ số thập phân. Nếu dùng Java `long`, cần kiểm tra giới hạn và tràn số khi nhân đơn giá với số lượng, cộng dòng hoặc trừ giảm giá; các phép toán như `Math.multiplyExact` có thể giúp phát hiện tràn thay vì âm thầm tạo số sai.

Số lượng phải đúng kiểu và giới hạn. Đơn giá âm, số lượng âm, phần trăm vượt miền hoặc giảm giá tạo tổng trái chính sách phải bị xử lý theo quy tắc, không sửa bằng `max(total, 0)` rồi coi đơn miễn phí là hợp lệ. Giá bằng 0 chỉ được phép khi có căn cứ nghiệp vụ rõ ràng.

## 5. Thiết kế quote gắn với nội dung được xác nhận

### 5.1. Quote là một đối tượng nghiệp vụ

Một quote minh họa cho giỏ hàng ở trên:

```json
{
  "quoteId": "quote-17",
  "quoteVersion": 1,
  "tenantId": "tenant-17",
  "buyerId": "buyer-42",
  "cartId": "cart-90",
  "cartRevision": 6,
  "pricingPolicy": "REPRICE_AT_ORDER_ACCEPTANCE",
  "currency": "VND",
  "lines": [
    {
      "sku": "SKU-A",
      "variantId": "variant-standard",
      "quantity": 2,
      "unitAmount": 100000,
      "lineAmount": 200000
    }
  ],
  "totals": {
    "subtotal": 200000,
    "discountTotal": 20000,
    "shippingTotal": 15000,
    "taxTotal": 0,
    "feeTotal": 0,
    "grandTotal": 195000
  },
  "pricingRevision": "pricing-42",
  "promotionRef": "promotion-11",
  "deliverySelectionRevision": 3,
  "expiresAt": "2026-11-22T10:05:00Z",
  "state": "AVAILABLE"
}
```

Đây là dữ liệu giả lập; các khoản bằng 0 là giá trị của ví dụ, không phải khẳng định về thuế hoặc phí áp dụng cho loại giao dịch ngoài đời. Có thể cần thêm phân bổ giảm giá theo dòng để đối chiếu, hoàn tiền và xử lý từng phần.

Quote phải bất biến hoặc có version tăng đúng khi thay nội dung. Nếu dùng fingerprint của ý định mua, nó cần bao phủ các trường quan trọng như dòng hàng, số lượng, lựa chọn giao, tiền tệ và phạm vi người mua. Chỉ hash `grandTotal` không xác định được ý định đó.

### 5.2. Chữ ký không thay thế hiệu lực nghiệp vụ

Một quote có chữ ký hoặc MAC có thể giúp phát hiện payload bị sửa, nhưng không tự xác nhận người đang dùng có quyền, quote còn hiệu lực, chưa bị thu hồi hoặc chưa được tiêu thụ. Quote cũng cần được kiểm tra với đúng phạm vi tenant và khách hàng theo chính sách.

Nếu quote dùng một lần, việc kiểm tra chưa dùng và đánh dấu đã dùng phải được phối hợp nguyên tử với tạo đơn. Hai request cùng xác minh một chữ ký hợp lệ vẫn có thể tạo hai đơn nếu không có trạng thái hoặc ràng buộc chống lặp phù hợp.

### 5.3. Xác nhận lại khi dữ liệu quan trọng thay đổi

Thông báo phù hợp khi Q17 không còn được chấp nhận có thể là: “Giá hoặc điều kiện đơn hàng đã thay đổi. Tổng mới là 215.000 đồng; cần xác nhận lại.” Phản hồi nên có quote mới và breakdown để người mua hiểu điều gì thay đổi, còn backend chưa tạo lệnh thu tiền cho mức mới.

Số tiền, tiền tệ và các dữ liệu quan trọng phải được gắn với bước xác nhận tương ứng. OWASP nhấn mạnh việc người dùng nhận biết nội dung giao dịch và bảo vệ dữ liệu giao dịch khỏi bị thay sau authorization. [OWASP Transaction Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html)

Trong mô hình minh họa, một thay đổi cần xác nhận tạo quote/lệnh xác nhận mới. Không cho client gửi `confirmed=true` cùng bất kỳ total nào để biến nội dung tự khai thành một quote đã được server chấp nhận.
