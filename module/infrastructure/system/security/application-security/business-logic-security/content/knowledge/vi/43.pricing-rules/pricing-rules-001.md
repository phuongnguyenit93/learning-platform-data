# Price source authority

## 1. Ai được quyết định giá có hiệu lực?

**Price source authority** là quy tắc xác định nguồn nào được quyền cung cấp giá mà hệ thống dùng để tạo nghĩa vụ thanh toán, cấp quyền sử dụng hoặc thực hiện giao hàng.

Trong chương **Pricing Rules** của module **Business Logic Security**, câu hỏi không dừng ở “giá có phải số dương không?”. Hệ thống còn phải xác định:

- Giá này thuộc sản phẩm, biến thể, đơn vị bán và loại giao dịch nào?
- Ai được sử dụng bảng giá hoặc ưu đãi đó?
- Giá còn hiệu lực vào thời điểm nào?
- Khi nhiều nguồn cùng khớp, nguồn nào được ưu tiên?
- Giá đã hiển thị có được khóa hay phải tính lại trước khi đặt hàng?
- Có thể dùng lại báo giá để tạo nhiều đơn hoặc thanh toán thiếu không?

Một request đúng định dạng vẫn có thể gây lạm dụng nếu máy chủ tin nhầm giá do client gửi, cho phép chọn bảng giá ngoài quyền hoặc thực thi trên dữ liệu đã thay đổi.

Nguyên tắc tính lại các giá trị liên quan đến an toàn như giá và quyền ở phía máy chủ cũng được nêu trong [OWASP Business Logic Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Business_Logic_Security_Cheat_Sheet.html). Bài học cụ thể hóa nguyên tắc đó bằng mô hình bảng giá, báo giá và xác nhận checkout.

### 1.1. Phân biệt các loại “giá”

| Loại dữ liệu | Mục đích | Có tự tạo quyền thu tiền hoặc giao hàng không? |
| --- | --- | --- |
| Giá hiển thị trên trang sản phẩm | Giúp người dùng tham khảo | Chưa đủ |
| Giá niêm yết trong catalog | Một nguồn giá cơ sở | Chỉ khi được chọn đúng ngữ cảnh và còn hiệu lực |
| Giá trong hợp đồng | Điều kiện thương mại của đối tượng được hưởng | Cần xác minh hợp đồng và phạm vi |
| Giá khuyến mãi | Ưu đãi theo chương trình | Cần kiểm tra eligibility và điều kiện kết hợp |
| Giá trong giỏ hàng | Kết quả tính tại một phiên bản giỏ | Có thể cần tính lại hoặc phát hành quote |
| Giá trong quote đã khóa | Cam kết có điều kiện và thời hạn | Có thể dùng khi quote hợp lệ và được chấp nhận đúng cách |
| Giá trong đơn đã xác nhận | Snapshot nghĩa vụ đã được chấp thuận | Là căn cứ cho các bước thanh toán theo chính sách |
| Amount từ request hoặc HTML | Dữ liệu client cung cấp | Không phải nguồn có thẩm quyền |

Nguồn giá có thể là database, pricing service hoặc một báo giá thương mại đã được phê duyệt. Authority không đến từ việc dữ liệu mang tên “price”, nằm trong ứng dụng nội bộ hoặc có ID khó đoán.

### 1.2. Ba nhóm quyền cần tách biệt

1. **Quyền thiết lập và công bố giá:** ai được tạo bảng giá, duyệt giá và đưa giá vào sử dụng.
2. **Quyền hưởng giá:** khách hàng, hợp đồng hoặc kênh bán nào được áp dụng mức giá đó.
3. **Quyền chấp nhận và thực thi:** chủ thể nào được xác nhận nghĩa vụ, thanh toán hoặc cấp quyền sử dụng theo giá đã chốt.

Một nhân viên được nhập giá nháp chưa chắc được xuất bản. Một người biết mã giá doanh nghiệp chưa chắc thuộc doanh nghiệp đó. Một payment provider chấp nhận amount cũng chưa chứng minh người mua đã thanh toán đúng giá của sản phẩm.

## 2. Ví dụ: giá hợp lệ nhưng không có thẩm quyền

Giả sử một giấy phép phần mềm có SKU JAVA-PRO-LICENSE:

~~~text
Giá bán lẻ: 600.000 VND / giấy phép
Giá hợp đồng doanh nghiệp A: 450.000 VND / giấy phép
Điều kiện giá hợp đồng: ít nhất 10 giấy phép
~~~

Các giá trị trong bài chỉ dùng minh họa.

### 2.1. Tin unitPrice từ client

Request nguy hiểm nếu được backend tin trực tiếp:

~~~json
{
  "sku": "JAVA-PRO-LICENSE",
  "quantity": 2,
  "currency": "VND",
  "unitPriceMinor": "1000",
  "totalMinor": "2000"
}
~~~

Mẫu code sai:

~~~java
// Cố ý không an toàn.
long total = Math.multiplyExact(
    request.unitPriceMinor(),
    request.quantity()
);
paymentService.create(total, request.currency());
~~~

Kiểm tra quantity > 0, unitPrice > 0 và chống tràn số vẫn chưa sửa lỗi. Phép tính có thể hoàn toàn chính xác nhưng dùng một giá không được phép.

### 2.2. Tra giá bằng ID nhưng không kiểm tra phạm vi

Một backend khác không nhận amount, nhưng nhận price ID:

~~~json
{
  "sku": "JAVA-PRO-LICENSE",
  "quantity": 2,
  "priceId": "enterprise-a-450k"
}
~~~

Nếu server chỉ kiểm tra price ID tồn tại rồi lấy amount, người mua lẻ có thể dùng giá hợp đồng của A dù không thuộc A và không đạt số lượng tối thiểu.

Vì vậy:

~~~text
Giá tồn tại != giá được áp dụng cho yêu cầu này.
ID hợp lệ != quyền hưởng điều kiện thương mại.
~~~

### 2.3. Đúng sản phẩm nhưng sai đơn vị hoặc chu kỳ

Một price ID có thể thuộc cùng sản phẩm nhưng là:

- Giá một tháng thay vì một năm.
- Giá một giấy phép thay vì một gói mười giấy phép.
- Giá gia hạn thay vì đăng ký mới.
- Giá thử nghiệm giới hạn quyền thay vì gói đầy đủ.
- Giá cho biến thể hoặc thị trường khác.

Chỉ so product ID là chưa đủ. Phạm vi nguồn giá phải khớp toàn bộ điều kiện liên quan đến giá và quyền được cấp.

## 3. Mô hình nguồn giá có thẩm quyền

### 3.1. Một bản ghi giá cần mang ngữ nghĩa

Một nguồn giá nên xác định tối thiểu:

~~~text
tenant và bên bán
SKU / variant / đơn vị bán
loại giao dịch hoặc chu kỳ dịch vụ
currency và amount
đối tượng được hưởng hoặc hợp đồng
kênh bán và thị trường
điều kiện số lượng
khoảng hiệu lực
phiên bản dữ liệu và policy
trạng thái công bố
nguồn gốc và quyết định phê duyệt
~~~

Không bắt buộc mọi sản phẩm đều có mọi trường. Tuy nhiên, những yếu tố làm thay đổi giá phải nằm trong mô hình quyết định, không bị giấu trong một quy ước của giao diện.

### 3.2. Context phải được xây từ dữ liệu tin cậy

Một pricing context có thể gồm:

~~~text
tenant
buyer và tổ chức đang đại diện
seller
SKU / variant
quantity đã chuẩn hóa
currency được phép
contract assignment
customer segment đã xác minh
sales channel
market và loại địa chỉ liên quan
purchase type / billing interval
pricing effective time
~~~

Các nguồn đầu vào khác nhau cần mức tin cậy khác nhau:

| Thông tin | Cách xác định phù hợp |
| --- | --- |
| Tenant, principal | Ngữ cảnh xác thực và phân quyền |
| Tổ chức mua hàng | Liên kết thành viên và quyền đại diện |
| SKU, biến thể | Catalog và lựa chọn hợp lệ |
| Quantity | Request đã kiểm tra miền giá trị và đơn vị |
| Hợp đồng | Gán hợp đồng có thẩm quyền cho bên mua |
| Hạng khách hàng | Dữ liệu membership/segment phía server |
| Kênh bán | Ngữ cảnh ứng dụng hoặc integration đã xác thực |
| Currency | Lựa chọn trong phạm vi hỗ trợ và điều kiện bán |
| Thời gian hiệu lực | Đồng hồ phía server theo chính sách |
| Thị trường và điều kiện liên quan | Dữ liệu nghiệp vụ được kiểm tra cho đúng mục đích |

Không nhận `customerTier = VIP`, `channel = INTERNAL` hay `contractOwner = A` làm bằng chứng chỉ vì request đã đăng nhập.

Địa chỉ hoặc khu vực có thể do người dùng khai báo, nhưng mức độ xác minh và cách dùng phải phù hợp chính sách. Locale, ngôn ngữ trình duyệt hoặc một tín hiệu mạng đơn lẻ không tự cấp quyền dùng bảng giá khác.

### 3.3. Authority theo từng thành phần

| Thành phần | Nguồn quyết định |
| --- | --- |
| Đơn giá cơ sở | Catalog/price book được công bố hợp lệ |
| Giá thỏa thuận | Hợp đồng hoặc offer đã phê duyệt đúng phạm vi |
| Bậc số lượng | Quantity đã chuẩn hóa và quy tắc tier phía server |
| Discount | Promotion engine và eligibility đã kiểm tra |
| Phí giao hàng | Phương thức giao hàng và nguồn giá vận chuyển có thẩm quyền |
| Thuế hoặc phụ phí | Engine và policy được cấu hình cho nghiệp vụ |
| Quy đổi currency | Quote quy đổi có thẩm quyền nếu sản phẩm cần |
| Làm tròn | Rounding policy được quản lý phiên bản |
| Tổng phải trả | Kết quả tổng hợp của pricing decision |

Một client không được khai một thành phần thành 0 để loại nó khỏi tổng. Ngược lại, backend cũng không nên cộng lại khoản đã bao gồm trong đơn giá do không ghi rõ giá đã bao gồm thành phần nào.

## 4. Chọn nguồn giá: đúng điều kiện trước, ưu tiên sau

### 4.1. Không mặc định chọn giá thấp nhất

Giả sử có bốn nguồn:

~~~text
Retail: 600.000
Campaign: 520.000
Enterprise contract: 450.000
Verified student offer: 420.000
~~~

Không có quy tắc tổng quát rằng khách hàng luôn được lấy min của bốn giá. Người mua có thể không thuộc hợp đồng, không có tư cách sinh viên hoặc chương trình không áp dụng cho SKU đang chọn.

Một pipeline có thể là:

~~~text
1. Xây context có thẩm quyền.
2. Lọc theo tenant, seller, SKU và đơn vị.
3. Lọc currency, loại mua, chu kỳ và thời điểm.
4. Kiểm tra quyền hưởng hợp đồng/offer.
5. Kiểm tra quantity và các điều kiện nghiệp vụ.
6. Áp dụng thứ tự ưu tiên đã định nghĩa.
7. Đánh giá discount và quy tắc kết hợp.
8. Tính các thành phần còn lại.
9. Chốt kết quả và provenance.
~~~

### 4.2. Ví dụ precedence minh họa

Một sản phẩm có thể quy định:

~~~text
Approved negotiated offer
  > eligible enterprise contract
  > eligible campaign price
  > retail price
~~~

Đây là chính sách ví dụ, không phải thứ tự bắt buộc. Quan trọng là thứ tự được xác định rõ và áp dụng nhất quán.

Nếu có hai hợp đồng cùng khớp ở một mức ưu tiên, cần quy tắc phân giải đã phê duyệt hoặc báo xung đột. Không vô tình chọn bản ghi đầu tiên database trả về, bản ghi mới nhất hoặc mức rẻ nhất.

Không coi “không tìm thấy giá hợp đồng” và “dịch vụ hợp đồng không phản hồi” là cùng một kết quả. Một lỗi truy cập nguồn không được âm thầm biến thành kết luận không có điều kiện áp dụng.

### 4.3. Giá bậc thang phải định nghĩa cách tính

Với số lượng 10, hai mô hình có thể khác nhau:

- **All-units:** khi đạt bậc, toàn bộ số lượng dùng một đơn giá của bậc đó.
- **Graduated:** từng phần số lượng được tính theo bậc tương ứng.

Một trường `tierPrice` không đủ để mô tả cả hai. Server phải giữ thuật toán, khoảng số lượng và phiên bản rõ ràng.

Người dùng không được tự khai quantity tính giá khác quantity được cấp quyền sử dụng. Nếu có gộp quantity theo SKU, hợp đồng hoặc kỳ, việc chia một dòng thành nhiều dòng không được đổi phạm vi gộp ngoài chính sách.

### 4.4. Giá gốc và discount không được tính trùng

Giá hợp đồng có thể đã là giá cuối cho phần hàng hóa và không được cộng thêm campaign discount. Một ưu đãi khác có thể cho phép kết hợp.

Phải lưu được:

~~~text
selected source
base amount theo nguồn đã chọn
các điều chỉnh được áp dụng
các điều chỉnh bị loại và lý do
kết quả cuối
~~~

Không trừ ưu đãi lần nữa ở payment service chỉ vì service đó cũng nhận coupon code từ client.

## 5. Công bố và thay đổi giá là một workflow có quyền

### 5.1. Vòng đời một phiên bản giá

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT: Tạo hoặc nhập phiên bản
    DRAFT --> APPROVED: Kiểm tra và duyệt
    APPROVED --> PUBLISHED: Công bố theo quyền
    PUBLISHED --> RETIRED: Ngừng dùng cho quyết định mới
    RETIRED --> [*]
~~~

Mô hình thực tế có thể thêm SCHEDULED hoặc REJECTED. Cần bảo đảm bản nháp không được resolver dùng như giá đang bán.

Một phiên bản đã công bố nên có dữ liệu giá bất biến. Thay amount, currency hoặc eligibility bằng một phiên bản mới giúp truy vết và tránh việc một price ID lịch sử âm thầm đổi nghĩa.

### 5.2. Quyền chỉnh giá không đồng nghĩa quyền vượt mọi điều kiện

Những kiểm soát có thể cần:

- Người bán chỉ sửa giá của catalog thuộc quyền mình.
- Nhân viên hỗ trợ chỉ tạo điều chỉnh trong biên độ cho phép.
- Offer vượt ngưỡng cần người duyệt có thẩm quyền phù hợp.
- Khi chính sách yêu cầu, người tạo và người duyệt phải độc lập.
- Công bố theo lịch phải dùng thời gian phía server.
- Tài khoản dịch vụ import giá chỉ được cập nhật phạm vi được cấp.
- Thay precedence hoặc nguồn fallback cũng cần quyền vì ảnh hưởng tiền.

Một endpoint `PATCH product` nhận toàn bộ entity có thể tạo đường mass assignment tới `published`, `approvedBy` hoặc `unitPrice`. DTO cập nhật phải giới hạn các trường của đúng hành động, không map nguyên payload vào mô hình có quyền.

### 5.3. Giá 0 là một quyết định cần chứng minh

Sản phẩm miễn phí, quà tặng hoặc trial có thể có tổng bằng 0. Không nhất thiết phải cấm tất cả giá 0, nhưng cần nguồn hợp lệ và quyền lợi được xác định rõ.

Không được coi không tìm thấy giá, lỗi parse, timeout pricing service hoặc cache miss là giá 0. Quyền giao hàng miễn phí phải đến từ quyết định có thẩm quyền, không từ giá trị mặc định của biến.

## 6. Từ quyết định giá đến báo giá có thể chấp nhận

### 6.1. Lưu kết quả cùng nguồn gốc

Một pricing decision không nên chỉ trả về số 1.130.000. Nó cần giải thích được vì sao số tiền đó được áp dụng.

Ví dụ một đơn bán lẻ:

~~~text
2 giấy phép * 600.000 = 1.200.000
Discount hợp lệ       =   100.000
Phí giao hàng         =    30.000
Thuế trong ví dụ      =         0
Tổng phải trả         = 1.130.000 VND
~~~

Ví dụ không mô tả quy tắc thuế của một khu vực cụ thể. Các thành phần phải do engine và policy phù hợp xác định.

Một quote có thể lưu:

~~~json
{
  "quoteId": "pq-842",
  "tenantId": "tenant-a",
  "buyerId": "buyer-19",
  "checkoutIntentId": "checkout-301",
  "cartId": "cart-78",
  "cartVersion": 12,
  "purpose": "NEW_PURCHASE",
  "currency": "VND",
  "pricingDecisionId": "pd-917",
  "pricingReleaseId": "release-31",
  "pricingPolicyVersion": "pricing-policy-v7",
  "roundingPolicyVersion": "money-policy-v3",
  "lines": [
    {
      "lineId": "line-1",
      "sku": "JAVA-PRO-LICENSE",
      "unit": "LICENSE",
      "quantity": 2,
      "priceSourceKind": "RETAIL",
      "priceRecordId": "retail-java-pro",
      "priceVersion": 12,
      "unitPriceMinor": "600000",
      "subtotalMinor": "1200000"
    }
  ],
  "discountMinor": "100000",
  "shippingMinor": "30000",
  "taxMinor": "0",
  "payableMinor": "1130000",
  "createdAt": "2026-11-22T03:00:00Z",
  "expiresAt": "2026-11-22T03:05:00Z",
  "state": "ISSUED"
}
~~~

Các ID và thời điểm là minh họa. Amount dùng chuỗi số nguyên ở JSON này để tránh mất độ chính xác tại client có miền biểu diễn số hạn chế.

Quote thật còn cần tham chiếu discount allocation, lựa chọn giao hàng và các đầu vào ảnh hưởng giá. Có thể dùng phiên bản đối tượng hoặc digest chuẩn hóa thay vì công bố toàn bộ dữ liệu nhạy cảm.

### 6.2. Hai hợp đồng về thay đổi giá

Có hai cách thiết kế khác nhau:

**Tính lại khi xác nhận:** giá trên giỏ chỉ là ước tính. Khi confirm, server tính giá hiện tại; nếu điều kiện hoặc tổng thay đổi, client phải nhận kết quả mới và chấp thuận theo luồng sản phẩm.

**Khóa giá đến hết hạn quote:** server phát hành một cam kết có thời hạn. Confirm hợp lệ dùng đúng snapshot, không tính lại bằng giá mới chỉ vì catalog vừa cập nhật.

Bài học dùng mô hình thứ hai. Quote được cấp từ nguồn hợp lệ; expiry của ví dụ không vượt thời hạn nguồn cho phép dùng để phát hành cam kết. Khi xác nhận, hệ thống kiểm tra quyền mua hiện tại, binding, trạng thái, expiry và các điều kiện thu hồi đã định nghĩa.

Giá catalog mới xuất bản không tự đổi quote cũ. Ngược lại, nếu có thu hồi vì lỗi nghiêm trọng hoặc quyền hưởng hợp đồng bị hủy, phải có policy và trạng thái rõ ràng; không sửa amount của quote đã phát hành.

### 6.3. Quote là cam kết về giá, chưa chắc là giữ chỗ mọi tài nguyên

Một quote không tự chứng minh:

- Hàng còn tồn kho.
- Coupon còn lượt sử dụng.
- Hạn mức tín dụng còn đủ.
- Đơn đã được phê duyệt.
- Khoản thanh toán đã được thu.

Nếu cam kết giá phụ thuộc các tài nguyên này, cần quy định khi nào giữ chỗ và cách giải phóng. Nếu chưa giữ, confirm phải kiểm tra hoặc reserve nguyên tử theo policy và có thể từ chối khi điều kiện không còn.

Không hứa giá đã được khóa vô điều kiện trong UI nếu backend vẫn có thể loại một ưu đãi mà không yêu cầu chấp thuận lại số tiền.

### 6.4. Quote ID và chữ ký không thay thế quyền

Client có thể gửi quote ID hoặc một payload có chữ ký của pricing service. Trong cả hai trường hợp vẫn cần:

~~~text
đúng issuer / nguồn có thẩm quyền
đúng tenant và buyer
đúng checkout intent và phiên bản giỏ
đúng purpose, quantity, currency và đầu vào quan trọng
đúng thời hạn và trạng thái
chưa được chấp nhận cho một đơn khác
~~~

Token có chữ ký giúp bảo vệ tính toàn vẹn, nhưng không ngăn replay hoặc dùng sai đối tượng nếu hệ thống không kiểm tra các điều kiện trên.

Không nhận JSON của pricing response do client gửi lại rồi mặc định nó có cùng authority như response được backend lấy trực tiếp từ dịch vụ có xác thực.

## 7. Các bất biến của luồng định giá

Với mô hình đơn giản, discount chỉ trừ vào tiền hàng:

~~~text
subtotalMinor = tổng tiền hàng từ các dòng đã tính hợp lệ

0 <= discountMinor <= subtotalMinor
shippingMinor >= 0
taxMinor >= 0

payableMinor =
    subtotalMinor - discountMinor + shippingMinor + taxMinor

payableMinor >= 0
~~~

Sản phẩm có discount cho vận chuyển, giá bao gồm thuế hoặc nhiều bước tính khác phải mô hình hóa tương ứng. Không áp dụng công thức ví dụ vào mọi trường hợp.

Các bất biến về authority:

1. Mọi dòng đều có nguồn giá hợp lệ cho đúng context.
2. Các thành phần trong tổng có cùng currency và quy ước đơn vị.
3. Quantity tính tiền khớp quantity giao hàng hoặc quyền lợi được cấp.
4. Quote gắn đúng intent, giỏ và phiên bản.
5. Người xác nhận có quyền trên bên mua và đối tượng liên quan.
6. Order snapshot bằng quote đã được chấp thuận, không bằng amount tùy ý từ request.
7. Một checkout intent chỉ tạo một đơn trong mô hình bài.
8. Một quote chỉ được chấp nhận cho một đơn.
9. Một giỏ đã được tiêu thụ không được xác nhận lần nữa bằng intent mới.
10. Yêu cầu thanh toán được dựng từ order snapshot và đối chiếu đúng khi xác nhận kết quả.
11. Chỉ commit đầy đủ mới được trả thành công.

Điểm 7 đến 9 ngăn việc chống lặp chỉ dựa vào HTTP key. Tạo một giỏ mới cho một lần mua thực sự mới là hành động khác, cần qua quy trình bình thường.

## 8. Vòng đời quote và xác nhận checkout

~~~mermaid
stateDiagram-v2
    [*] --> ISSUED: Phát hành từ nguồn hợp lệ
    ISSUED --> ACCEPTED: Tạo đơn và tiêu thụ intent
    ISSUED --> EXPIRED: Hết hạn
    ISSUED --> SUPERSEDED: Chọn quote mới
    ISSUED --> REVOKED: Thu hồi theo policy
    ACCEPTED --> [*]
    EXPIRED --> [*]
    SUPERSEDED --> [*]
    REVOKED --> [*]
~~~

ACCEPTED nghĩa là giá đã được chấp nhận vào một đơn. Nó không có nghĩa đơn đã PAID.

### 8.1. Khi giỏ thay đổi

Các thay đổi có thể ảnh hưởng quote gồm:

- SKU, variant, đơn vị bán hoặc quantity.
- Bên mua đang đại diện, hợp đồng hoặc địa chỉ liên quan.
- Phương thức giao hàng.
- Coupon hoặc điều kiện ưu đãi.
- Loại mua, chu kỳ dịch vụ hoặc currency.

Server phải tăng version thích hợp hoặc thay snapshot binding. Không chỉ so quote với cart ID rồi bỏ qua các nội dung đã đổi.

Nếu cấp quote mới, việc thay quote được chọn cho intent và đánh dấu quote cũ SUPERSEDED phải nhất quán. Người dùng không được tùy ý dùng quote cũ có điều kiện thuận lợi hơn sau khi giỏ đã đổi.

### 8.2. Hết hạn cần kiểm tra lúc chấp nhận

Điều kiện là:

~~~text
quote.state == ISSUED
serverDecisionTime < quote.expiresAt
~~~

Job cập nhật EXPIRED chưa chạy không kéo dài hiệu lực. Nếu transaction chờ khóa lâu, phải lấy thời điểm kiểm tra mới trước khi claim, thay vì dùng timestamp từ đầu request.

Mô hình bài xem thời điểm claim quote trong transaction ngắn là điểm chấp nhận. Không đặt lời gọi mạng chậm giữa lúc kiểm tra và ghi quyết định.

## 9. Ví dụ API và Java service

### 9.1. Client gửi lựa chọn và điều kiện đối chiếu

~~~http
POST /checkout-intents/checkout-301/confirm
Idempotency-Key: 2aa5029e-895f-4a8e-bba5-afbb7dc0487a
Content-Type: application/json

{
  "quoteId": "pq-842",
  "expectedCartVersion": 12,
  "expectedCurrency": "VND",
  "expectedPayableMinor": "1130000"
}
~~~

Expected amount là điều kiện để phát hiện client đang xác nhận dữ liệu khác với quote. Nó không trở thành nguồn giá.

Nếu quote hiện tại khác số tiền người dùng vừa nhìn thấy, server không được tự coi `expectedPayableMinor` là amount cần thu, cũng không âm thầm tăng số tiền mà người dùng chưa chấp thuận.

### 9.2. Phác thảo transaction xác nhận

Mã giả dưới đây giả định intent, giỏ, quote và reservation cần thiết ở cùng database. Các repository và policy biểu diễn hợp đồng phải triển khai, không phải một ứng dụng có thể biên dịch ngay.

~~~java
@Transactional
public CheckoutResult confirm(
        Principal principal,
        ConfirmCheckoutCommand cmd) {

    CheckoutRef ref = intents.findAccessibleRef(
        principal, cmd.checkoutIntentId()
    );
    permissions.requireCheckoutAccess(principal, ref);

    String fingerprint = fingerprints.forConfirm(
        principal.tenantId(), principal.clientId(),
        cmd.checkoutIntentId(), cmd.quoteId(),
        cmd.expectedCartVersion(),
        cmd.expectedCurrency(), cmd.expectedPayableMinor()
    );

    OperationClaim op = operations.claimOrLoad(
        principal.tenantId(), principal.clientId(),
        "CONFIRM_CHECKOUT", cmd.idempotencyKey(), fingerprint
    );

    if (op.completed()) {
        return op.savedResult();
    }

    CheckoutIntent intent = intents.lock(
        principal.tenantId(), cmd.checkoutIntentId()
    );
    Cart cart = carts.lock(principal.tenantId(), intent.cartId());
    PriceQuote quote = quotes.lock(principal.tenantId(), cmd.quoteId());

    intent.requireUnconfirmedAndSelectedQuote(quote.id());
    cart.requireNotConsumed();
    cart.requireVersion(cmd.expectedCartVersion());
    quote.requireBoundTo(principal, intent, cart);
    quote.requireExpectedTotal(
        cmd.expectedCurrency(), cmd.expectedPayableMinor()
    );

    permissions.requireCurrentBuyingRights(principal, cart, quote);
    pricingPolicies.requireAuthoritativeAndNotRevoked(quote);
    approvals.requireValidFor(cart, quote);

    // Chỉ thao tác nội bộ có thể rollback cùng transaction.
    benefits.reserveIfRequired(quote, intent.id());
    fulfillmentPolicies.requireOrderCanBeAccepted(cart, quote);

    Instant decisionTime = time.authoritativeNowAfterLocks();
    quote.requireIssuedAndUnexpiredAt(decisionTime);

    Order order = orders.insertUniqueForIntent(
        intent, cart, quote.immutableSnapshot()
    );
    quote.markAccepted(order.id(), decisionTime);
    intent.markConfirmed(order.id());
    cart.markConsumed(order.id());

    if (order.payableMinor() > 0) {
        outbox.appendPaymentRequested(order);
    } else {
        pricingPolicies.requireAuthorizedZeroPrice(order);
        outbox.appendNoPaymentRequiredOrder(order);
    }

    return operations.complete(op, order);
}
~~~

Các điểm quan trọng:

- Không lấy unitPrice hay total từ request để dựng order.
- Không yêu cầu quote bằng phiên bản catalog mới nhất nếu policy đã khóa giá hợp lệ.
- Mọi quyền hưởng giá đặc biệt cần kiểm tra theo điều kiện của quote và policy, không chỉ quyền xem giỏ.
- Claim idempotency, reservation, tạo đơn, consume quote/intent/cart và outbox phải commit cùng nhau.
- Lỗi sau reservation phải rollback toàn bộ; cấu hình rollback phải bao phủ loại exception thực tế.
- Retry cùng key không được chạy lại việc reserve hoặc tạo đơn.
- Quyền xem kết quả cần được kiểm tra trước khi trả kết quả đã lưu.

Nếu fulfillment hoặc payment là dịch vụ bên ngoài, ghi một yêu cầu vào outbox thay vì gọi mạng trong transaction này. Trạng thái chờ và cơ chế xử lý bù phải được mô hình hóa cho các tài nguyên bên ngoài.

### 9.3. Ràng buộc database hỗ trợ chống lặp

Ví dụ PostgreSQL tối giản:

~~~sql
CREATE TABLE checkout_order (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    checkout_intent_id UUID NOT NULL,
    cart_id UUID NOT NULL,
    quote_id UUID NOT NULL,
    currency VARCHAR(3) NOT NULL,
    subtotal_minor NUMERIC(20, 0) NOT NULL CHECK (subtotal_minor >= 0),
    discount_minor NUMERIC(20, 0) NOT NULL CHECK (discount_minor >= 0),
    shipping_minor NUMERIC(20, 0) NOT NULL CHECK (shipping_minor >= 0),
    tax_minor NUMERIC(20, 0) NOT NULL CHECK (tax_minor >= 0),
    payable_minor NUMERIC(20, 0) NOT NULL CHECK (payable_minor >= 0),
    PRIMARY KEY (tenant_id, order_id),
    UNIQUE (tenant_id, checkout_intent_id),
    UNIQUE (tenant_id, cart_id),
    UNIQUE (tenant_id, quote_id),
    CHECK (discount_minor <= subtotal_minor),
    CHECK (
        payable_minor
        = subtotal_minor - discount_minor + shipping_minor + tax_minor
    )
);
~~~

Unique theo cart là lựa chọn của mô hình một giỏ chỉ xác nhận một lần. Ứng dụng có thể dùng mô hình khác, nhưng phải giữ một định danh nghiệp vụ ổn định cho cùng lần checkout.

Schema đầy đủ cần khóa ngoại có tenant tới intent, cart và quote, cùng order lines có provenance. Các CHECK trên không tự chứng minh tổng dòng bằng subtotal hoặc nguồn giá có quyền; cần bảo vệ ở transaction và lớp nghiệp vụ.

Luồng refresh quote, cancel và confirm phải tuân thủ thứ tự khóa tương thích. Nếu dùng optimistic locking, conflict phải rollback và retry toàn thao tác, không ghi đè snapshot mới bằng dữ liệu cũ.

## 10. Cache, replica và lỗi dịch vụ giá

### 10.1. Cache không tự trở thành authority

Cache có thể phục vụ giá hiển thị hoặc giữ một snapshot có phiên bản. Tuy nhiên, cần biết cache đang đại diện cho:

- Giá tham khảo.
- Bản sao giá công bố với một hợp đồng freshness.
- Quote đã được pricing authority phát hành và còn hiệu lực.

Một dòng trong session hoặc localStorage không đủ làm nguồn quyết định. Một bản sao server cũng cần version, context và quy tắc hiệu lực rõ ràng.

Cache key phải bao phủ những yếu tố làm kết quả khác nhau, chẳng hạn tenant, SKU/variant, đơn vị, currency, loại mua, quantity tier, kênh, hợp đồng/nhóm đủ điều kiện và policy/release version.

Không dùng chung kết quả giá hợp đồng riêng tư cho người mua lẻ. Với giá công khai thực sự không phụ thuộc khách hàng, có thể cache theo phạm vi công khai đã được xác định, thay vì thêm dữ liệu cá nhân không cần thiết.

### 10.2. Một quyết định cần nguồn dữ liệu nhất quán

Đọc giá dòng A ở release cũ và dòng B ở release mới có thể tạo một tổ hợp không được chính sách nào công bố.

Một cách thiết kế là dùng pricing release bất biến: resolver chọn một release và các phiên bản liên quan rồi lưu release ID trong quyết định. Các giá hợp đồng, promotion và thành phần khác cũng cần version/provenance phù hợp.

Nếu pricing service ở xa, có thể yêu cầu nó phát hành quote có thẩm quyền, ràng buộc với request context và phiên bản giỏ. Order service xác minh nguồn, binding và hiệu lực trước khi lưu. Không cần giữ khóa database của giỏ trong suốt cuộc gọi mạng.

Khi giỏ hoặc context đổi trong lúc chờ pricing response, response cũ không được gắn vào phiên bản mới. Cần phát hiện và yêu cầu tính lại.

### 10.3. Fallback phải được phê duyệt trước

Khi nguồn lỗi, có thể:

- Tạm dừng phát hành quote mới.
- Dùng một bản snapshot còn trong điều kiện cho phép.
- Chuyển sang nguồn dự phòng được định nghĩa.
- Tiếp tục hiển thị tham khảo nhưng chưa cho xác nhận.

Không fallback về amount client, giá 0, giá từ một tenant khác hoặc dữ liệu cũ vô thời hạn. Nếu fallback làm thay đổi giá hoặc mất ưu đãi, cần hiển thị và chấp thuận lại theo hợp đồng sản phẩm.

Read replica có thể phù hợp cho hiển thị, nhưng không được dùng một trạng thái cũ để bỏ qua thu hồi quote, quyền khách hàng hoặc việc intent đã được xác nhận. Các quyết định đó cần dữ liệu có thẩm quyền theo mô hình nhất quán đã chọn.

## 11. Tích hợp thanh toán không được tạo một nguồn giá tùy ý khác

Một payment provider có thể nhận price ID hoặc dữ liệu giá được backend gửi khi tạo phiên thanh toán. Chẳng hạn, [Stripe Create a Checkout Session](https://docs.stripe.com/api/checkout/sessions/create) có line items tham chiếu Price và quantity.

Ứng dụng phải quyết định các tham chiếu đó từ dữ liệu có thẩm quyền. Việc provider chấp nhận một Price ID không chứng minh Price đó thuộc đúng SKU, tenant, chu kỳ hoặc quyền hưởng giá của khách hàng.

### 11.1. Hai kiểu ánh xạ cần bảo vệ

**Dùng provider Price ID có sẵn:**

~~~text
internal offer/version
  -> mapping được quản lý
  -> provider account + provider Price ID
  -> currency, đơn vị, chu kỳ và các điều kiện khớp
~~~

Client có thể chọn một offer trong danh sách được phép, nhưng server phải phân giải và kiểm tra mapping. Không chuyển tiếp bất kỳ provider Price ID nào client gửi.

**Dùng amount do backend dựng:**

~~~text
accepted order snapshot
  -> adapter amount/currency
  -> request thanh toán
~~~

Không lấy amount từ browser ở bước này. Adapter phải bảo toàn đơn vị và currency, không tính lại từ giá catalog hiện tại.

### 11.2. Xác định ai chốt các thành phần cuối cùng

Nếu hệ thống đã khóa toàn bộ payable, cấu hình phiên thanh toán phải phù hợp với số tiền đó.

Nếu provider được giao tính một thành phần cuối như thuế hoặc vận chuyển, quote trước đó phải thể hiện đúng phần chưa chốt. Cần một luồng nhận kết quả cuối, kiểm tra và ghi nhận sự chấp thuận tương ứng. Không đồng thời coi một tổng cũ là bất biến và cho provider tự cộng thêm khoản chưa được mô hình hóa.

### 11.3. Đối chiếu kết quả trước khi giao quyền lợi

Khi xác nhận thanh toán, cần kiểm tra:

- Provider account và đối tượng giao dịch được liên kết đúng order/payment attempt.
- Amount và currency thực tế khớp nghĩa vụ được phép thanh toán.
- Trạng thái đáp ứng điều kiện ghi nhận thành công.
- Event hoặc operation chưa được áp dụng.
- Quyền lợi được cấp khớp sản phẩm, quantity và chu kỳ đã mua.

Một redirect về success URL không phải bằng chứng trả đủ tiền. Webhook cũng cần xác minh nguồn và ngữ cảnh; không chỉ nhận một cờ `paid = true` từ payload không được xác thực.

Nếu amount thấp hơn order total, không tự đánh dấu PAID chỉ vì provider nói giao dịch đó thành công. Giao dịch thành công có thể là một khoản tiền không đúng nghĩa vụ.

### 11.4. Timeout không làm giá đã chốt trở thành giá mới

Giả sử payment request đã được gửi nhưng response bị mất. Client không nên tạo đơn mới từ catalog hiện tại để “thử lại”.

Cần giữ order và payment attempt, tra cứu hoặc retry theo hợp đồng idempotency của provider. Không kết luận tiền chưa bị thu chỉ dựa vào lỗi mạng. Kết quả đến muộn phải được gắn về đúng order snapshot ban đầu.

## 12. Idempotency và chống dùng lại báo giá

### 12.1. Mỗi key đại diện một ý định xác nhận

Một idempotency scope có thể là:

~~~text
(tenant_id, client_id, operation_type, idempotency_key)
~~~

Fingerprint gồm intent ID, quote ID và các điều kiện đối chiếu ảnh hưởng hành động. Amount cần chuẩn hóa theo quy ước đã công bố, không hash một số thực gần đúng.

| Tình huống | Hành vi mong muốn |
| --- | --- |
| Cùng key, cùng payload, đã commit | Trả lại cùng order nếu người gọi được xem |
| Cùng key, payload khác | Xung đột |
| Cùng key, hai request đồng thời | Một request được thực hiện; request còn lại chờ hoặc retry theo hợp đồng |
| Khác key, cùng intent | Không tạo order thứ hai |
| Khác intent nhưng dùng giỏ đã tiêu thụ | Không xác nhận lại cùng giỏ |
| Quote đã được chấp nhận cho order khác | Không sử dụng lại |
| Mất response sau commit | Tra cứu hoặc retry để nhận lại order đã tạo |
| Key hết thời gian lưu | Ràng buộc intent/cart/quote vẫn bảo vệ khỏi lặp |

TTL của idempotency store không phải TTL của nghĩa vụ nghiệp vụ. Một order đã tồn tại không biến mất chỉ vì cache key cũ hết hạn.

### 12.2. Refresh quote không được né trạng thái hoàn tất

Khi intent đã CONFIRMED, endpoint refresh không được:

- Cấp lại quote như thể chưa có order.
- Reset giỏ về chưa tiêu thụ.
- Tạo payment attempt mới không liên kết với order cũ.
- Thay snapshot của order bằng catalog hiện tại.

Nếu người dùng muốn đặt lại một đơn tương tự, tạo một ý định mua mới theo quy trình. Đổi ID không được dùng như cách lách kiểm tra của cùng lần checkout đang thực hiện.

### 12.3. Tác động ngoài database cần định danh ổn định

Outbox có thể được phát lại sau crash. Consumer tạo payment session, cấp license hoặc giao hàng cần định danh operation ổn định và cơ chế ghi nhận đã áp dụng.

Một lần xác nhận giá không tự đảm bảo chỉ một license được cấp nếu dịch vụ fulfillment xử lý lặp không an toàn. Cần liên kết benefit grant với order/line/fulfillment obligation, không chỉ với delivery ID của message.

## 13. Hoàn tiền và sửa đơn phải tôn trọng nguồn giá gốc

Giả sử đơn đã thanh toán 600.000 VND cho một giấy phép. Sau đó retail price giảm xuống 500.000 hoặc tăng lên 700.000.

Khoản hoàn theo giao dịch gốc không mặc định dùng giá catalog hiện tại. Căn cứ là amount đã thu, phần discount/fee được phân bổ, điều kiện hoàn và các khoản đã hoặc đang hoàn.

Các bất biến thường cần:

~~~text
Tổng refund thành công và đang chờ
    <= phần được hoàn của capture gốc

Mỗi refund obligation
    -> đúng order/capture/currency
    -> đúng policy và approval cần thiết
~~~

Với đổi gói, đổi hàng hoặc tính tiền theo thời gian, có thể cần pricing decision mới. Phải phân biệt phần điều chỉnh giao dịch cũ với phần mua mới; không sửa âm thầm nguồn giá lịch sử.

Một nhân viên hỗ trợ được quyền tạo refund không đương nhiên có quyền thay order price hoặc mở lại quote để cấp thêm quyền lợi. Các hành động đó có authority khác nhau và cần audit riêng.

## 14. Các đường lạm dụng và nơi chặn

| Đường lạm dụng | Điểm yếu | Kiểm soát phù hợp |
| --- | --- | --- |
| Sửa unitPrice/total trong request | Client là nguồn giá | Tính từ nguồn có thẩm quyền và quote |
| Chọn giá hợp đồng của tổ chức khác | Chỉ kiểm tra ID tồn tại | Kiểm tra quyền hưởng giá và binding |
| Dùng giá monthly cho annual entitlement | Mapping thiếu loại mua/chu kỳ | Xác minh toàn bộ offer và quyền lợi |
| Đổi quantity sau khi được báo giá | Quote chỉ gắn cart ID | Version và snapshot đầu vào quan trọng |
| Chia dòng để đạt tier hoặc kết hợp ưu đãi sai | Phạm vi gộp không được bảo vệ | Normalize và áp dụng policy phía server |
| Sử dụng bản giá nháp hoặc chưa duyệt | Resolver bỏ trạng thái công bố | Workflow và quyền publish |
| Gửi trường approved hoặc published khi sửa entity | Mass assignment | DTO theo hành động và kiểm tra quyền |
| Cache giá doanh nghiệp cho người mua lẻ | Cache key thiếu context | Scope và key đúng chính sách |
| Nguồn lỗi rồi mặc định giá 0 | Fallback không có authority | Chính sách lỗi rõ ràng, không tự tạo giá |
| Dùng quote cũ sau thay đổi giỏ | Thiếu supersede/version check | Quote được chọn và state machine |
| Gửi nhiều key để xác nhận cùng lần mua | Chỉ dựa vào idempotency cache | Unique theo intent/cart/quote |
| Trả một amount nhỏ nhưng khai mua gói lớn | Payment success không đối chiếu order | Kiểm tra amount/currency/benefit binding |
| Nhân viên tự nhập offer rồi tự duyệt vượt quyền | Tách quyền không đầy đủ | Approval đúng ngưỡng và chủ thể |
| Hoàn theo giá hiện tại có lợi hơn giá đã thu | Không giữ provenance của order | Refund dựa giao dịch và policy gốc |

Giới hạn tần suất và phát hiện bất thường hữu ích, nhưng không thay cho quyền theo đối tượng hoặc bất biến giá. Một request duy nhất cũng có thể mua sai giá nếu nguồn quyết định không được bảo vệ.

## 15. Kiểm thử theo quyết định giá và chuỗi hành động

Các kịch bản sau dành cho môi trường thử nghiệm được kiểm soát. Khi triển khai, cần kiểm tra trạng thái dữ liệu, order snapshot và các tác động, không chỉ mã HTTP.

### 15.1. Ma trận kiểm thử

| Nhóm | Tình huống | Kết quả cần chứng minh |
| --- | --- | --- |
| Authority | Client sửa unitPrice hoặc total | Không thay đổi giá có hiệu lực |
| Authority | Client gửi price ID hợp lệ nhưng của buyer khác | Từ chối hoặc không chọn nguồn đó theo hợp đồng API |
| Context | Đổi tenant, seller hoặc hợp đồng | Không dùng bảng giá ngoài phạm vi |
| Context | Product đúng nhưng variant, đơn vị hoặc chu kỳ sai | Không cấp quyền lợi sai giá |
| Eligibility | Khai VIP/student/enterprise trong request | Server dùng tư cách đã xác minh |
| Precedence | Nhiều nguồn cùng đủ điều kiện | Chọn theo policy, không theo thứ tự query |
| Ambiguity | Hai nguồn cùng ưu tiên mà không có quy tắc phân giải | Báo xung đột thay vì chọn ngẫu nhiên |
| Quantity | Đạt/chưa đạt mốc tier; all-units và graduated | Kết quả đúng mô hình đã công bố |
| Combining | Giá hợp đồng không được stack campaign | Không trừ thêm ưu đãi ngoài policy |
| Publication | Giá DRAFT hoặc APPROVED chưa PUBLISHED | Không dùng cho quote mới |
| Time | now đúng validUntil hoặc expiresAt | Áp dụng ranh giới hiệu lực đã định nghĩa |
| Zero price | Nguồn miễn phí hợp lệ và lỗi tra giá | Chỉ trường hợp có authority được tạo order 0 |
| Quote | Thay quantity, địa chỉ liên quan hoặc currency | Quote cũ không được dùng cho context mới |
| Price lock | Catalog đổi sau khi phát hành quote còn hiệu lực | Giữ đúng cam kết theo policy khóa giá |
| Revocation | Quote bị thu hồi hoặc quyền mua bị hủy | Không xác nhận ngoài điều kiện đã định |
| Consent | Expected total khác quote | Không âm thầm thu theo một trong hai giá trị |
| Cache | Giá hợp đồng đã cache rồi user khác truy cập | Không lộ hoặc áp dụng giá riêng tư |
| Failure | Pricing service timeout hoặc replica trả dữ liệu cũ | Không fallback thành client price/0 hay bỏ trạng thái hoàn tất |
| Retry | Cùng key và payload sau mất response | Cùng order, không reserve hoặc tạo lại |
| Conflict | Cùng key nhưng đổi quote/intent | Xung đột, không trả kết quả sai phạm vi |
| Concurrency | Hai key cùng intent hoặc cùng giỏ | Tối đa một order |
| Concurrency | Refresh quote và confirm cùng lúc | Chỉ một kết quả hợp lệ theo state/version |
| Atomicity | Lỗi sau reserve trước tạo order | Rollback mọi thay đổi trong transaction |
| Atomicity | Commit xong nhưng outbox chưa được phát | Order tồn tại nhất quán, worker có thể tiếp tục |
| Provider | Thanh toán thành công nhưng amount/currency sai | Không đánh dấu đúng nghĩa vụ đã trả đủ |
| Provider | Timeout rồi webhook thành công đến muộn | Gắn đúng attempt/order, không tạo đơn mới |
| Refund | Giá catalog đổi trước khi refund | Quyền hoàn theo giao dịch và policy gốc |

Kiểm thử cạnh tranh cần nhiều transaction/kết nối database và đồng bộ điểm bắt đầu. Mock một resolver hoặc repository không chứng minh được unique constraint, khóa hoặc hành vi commit.

### 15.2. Các khẳng định sau mỗi kịch bản

~~~text
Mỗi order có pricing decision và quote được phép.
Mỗi line có source/version và context phù hợp.
Order amount/currency khớp snapshot đã chấp nhận.
Tổng các thành phần khớp payable theo policy.
Quantity được cấp quyền lợi khớp quantity đã mua.
Mỗi intent/cart/quote tạo tối đa một order trong mô hình bài.
Không có reservation hoặc benefit grant bị áp dụng lặp.
Không có dữ liệu tenant khác bị đọc hoặc thay đổi ngoài quyền.
Order chỉ chuyển sang trạng thái thanh toán hợp lệ khi bằng chứng khớp.
~~~

Với các phép tính tiền, dùng số nguyên minor unit hoặc số thập phân chính xác theo policy, kiểm tra tràn và điểm làm tròn. Không dùng một epsilon tùy ý để che việc tổng server khác amount đã chốt.

### 15.3. Kiểm thử chuỗi thay vì từng endpoint độc lập

Những chuỗi cần chú ý:

~~~text
Tạo giỏ -> nhận quote -> sửa quantity -> confirm quote cũ
Nhận quote hợp đồng -> thu hồi quyền tổ chức -> confirm
Nhận quote -> catalog xuất bản giá mới -> confirm trong thời hạn
Confirm -> mất response -> retry key mới -> refresh quote
Tạo payment -> timeout -> nhận webhook -> retry consumer
Thanh toán -> đổi catalog -> refund một phần -> retry refund
~~~

Sau từng bước, kiểm tra state, provenance, số order, reservation và benefit grant. Thay đổi thứ tự request có thể bộc lộ lỗi mà test đường đi thuận không phát hiện.

## 16. Audit và vận hành nguồn giá

Một order cần có thể truy vết theo chuỗi:

~~~text
Buyer và context đủ điều kiện
  -> nguồn giá và phiên bản được chọn
  -> policy ưu tiên/kết hợp
  -> pricing decision
  -> quote và sự chấp thuận
  -> order snapshot
  -> payment và fulfillment liên quan
~~~

Dữ liệu nên lưu gồm source kind/ID/version, contract hoặc offer reference, quantity, currency, các thành phần tiền, policy/release version, quote expiry, principal, approval reference và idempotency operation.

Không cần ghi toàn bộ dữ liệu cá nhân vào log để chứng minh nguồn giá. Dùng tham chiếu và kiểm soát quyền xem dữ liệu thương mại riêng tư; không ghi token thanh toán hoặc bí mật xác thực.

Theo dõi các dấu hiệu:

- Nhiều lần yêu cầu price ID ngoài quyền.
- Expected total liên tục thấp hơn quote.
- Quote conflict, replay hoặc refresh sau confirm tăng.
- Giá 0, override hoặc fallback tăng bất thường.
- Cache trả sai phân khúc hoặc quyết định thiếu source/version.
- Price publish, precedence hoặc contract assignment thay đổi bất thường.
- Order total không khớp payment amount hoặc benefit grant.
- Reservation treo và payment attempt chưa xác minh quá lâu.

Các job đối soát có thể phát hiện quyết định thiếu provenance, tổng tiền lệch hoặc fulfillment trùng. Chúng không thay thế việc bảo vệ transaction đúng từ đầu.

Nếu phát hiện giá sai đã được sử dụng, cần quy trình thu hồi hoặc điều chỉnh có căn cứ và quyền. Không sửa trực tiếp giá lịch sử của order chỉ để báo cáo khớp catalog hiện tại.

## 17. Tiêu chí hoàn thành thiết kế

Một thiết kế price source authority cần trả lời rõ:

1. Nguồn nào được phát hành giá và ai có quyền công bố hoặc override?
2. Buyer được hưởng nguồn giá đó dựa vào dữ liệu nào?
3. Các trục SKU, biến thể, đơn vị, quantity, currency và chu kỳ có được kiểm tra đầy đủ không?
4. Precedence và quy tắc kết hợp được xác định thế nào khi nhiều nguồn cùng khớp?
5. Giá hiển thị là tham khảo hay cam kết; thời điểm nào cần chấp thuận lại?
6. Quote gắn với intent và phiên bản context bằng cách nào?
7. Nguồn bị lỗi, cache cũ hoặc quyền bị thu hồi sẽ được xử lý ra sao?
8. Transaction và unique constraint nào ngăn xác nhận lặp?
9. Payment và fulfillment có thực thi đúng snapshot đã chấp nhận không?
10. Có thể giải thích từng amount trong order bằng nguồn, policy và approval không?

Giá an toàn về nghiệp vụ là giá được chọn từ đúng nguồn cho đúng đối tượng và điều kiện, rồi thực thi theo một quyết định có thể truy vết. Kiểm tra định dạng của amount hoặc sự tồn tại của price ID chỉ là một phần nhỏ của việc bảo vệ đó.
