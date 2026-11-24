# Discount reversal: hoàn tác giảm giá an toàn khi hủy hoặc hoàn đơn

## Mục tiêu và phạm vi

Discount reversal là quá trình điều chỉnh hoặc bù trừ ảnh hưởng của một khoản giảm giá khi giao dịch gốc bị hủy, trả hàng, hoàn tiền hoặc thay đổi theo chính sách đã công bố. Trong bảo mật logic nghiệp vụ, mục tiêu là giữ đúng quan hệ giữa tiền đã thu, hàng hóa được giữ lại, giảm giá đã hưởng và quyền sử dụng ưu đãi.

Một thao tác “hoàn tác giảm giá” có thể liên quan đến nhiều sổ theo dõi: phân bổ giảm giá của đơn hàng, khoản hoàn tiền, lượt sử dụng voucher, ngân sách chương trình và khoản tài trợ giữa các bên. Mỗi sổ có quy tắc riêng. Đổi trạng thái voucher không đồng nghĩa với hoàn tiền; hoàn tiền cũng không tự động đồng nghĩa với cấp lại voucher.

Bài học thuộc phạm vi bảo vệ quy tắc nghiệp vụ của ứng dụng: thiết kế bất biến, máy trạng thái, quyền theo đối tượng, transaction, idempotency và kiểm thử các đường đi mà người dùng có thể lạm dụng.

Sau bài này, bạn có thể:

- Phân biệt hủy một khoản giữ chỗ với bù trừ một ưu đãi đã ghi nhận.
- Tính giới hạn hoàn tiền từ giao dịch gốc và phân bổ giảm giá đã lưu.
- Thiết kế quy tắc cấp lại voucher mà không tạo thêm lượt sử dụng ngoài chính sách.
- Xử lý yêu cầu trùng, yêu cầu đồng thời và kết quả hoàn tiền chưa xác định.
- Xây dựng các tình huống kiểm thử tấn công logic cho luồng hoàn tác.

## 1. Làm rõ những gì đang được hoàn tác

### 1.1. Bốn thao tác thường bị gộp nhầm

| Thao tác | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Release reservation | Bỏ giữ chỗ khi ưu đãi chưa được tiêu dùng chính thức | Hết thời gian thanh toán, trả lại một suất voucher đang giữ |
| Reverse redemption | Ghi nhận việc sử dụng ưu đãi trước đó được bù trừ | Hủy toàn bộ đơn đã thanh toán theo chính sách cho phép phục hồi lượt |
| Refund payment | Hoàn một phần hoặc toàn bộ tiền đã thu | Khách trả món hàng có giá sau giảm là 80.000 đồng |
| Restore entitlement | Khôi phục hoặc cấp lại quyền sử dụng ưu đãi | Cấp một quyền thay thế có liên kết với lượt dùng đã bị đảo |

Còn có điều chỉnh ngân sách chiến dịch hoặc đối soát phần tài trợ của nhà bán hàng. Đây là các hiệu ứng bổ sung, không nên suy ra tự động từ tên API “reverse discount”.

Một API đổi `coupon.used = false` không đủ mô tả các trường hợp trên. Nếu voucher đang được chia sẻ toàn chương trình, cờ này còn có thể mở lại ưu đãi cho sai người hoặc xóa mất lịch sử dùng của nhiều đơn.

### 1.2. Hoàn tác nghiệp vụ khác rollback transaction

Rollback cơ sở dữ liệu có thể hủy các thay đổi chưa commit trong cùng transaction. Khi tiền đã được thu qua hệ thống thanh toán hoặc quyền ưu đãi đã được dùng ở một giao dịch khác, không thể coi việc đặt lại vài cột là quay toàn bộ thế giới về trạng thái cũ.

Lúc đó cần một hành động bù trừ có định danh, lý do và liên kết tới bản ghi gốc:

~~~text
Lượt dùng R1: voucher V1 được dùng cho đơn O1
Điều chỉnh A1: bù trừ một phần hoặc toàn bộ R1 vì hoàn đơn
Quyền E2: quyền thay thế được tạo từ A1, nếu chính sách cho phép
~~~

Lịch sử R1 vẫn tồn tại. Nhờ đó, hệ thống giải thích được ai đã hưởng lợi, vì sao có điều chỉnh và quyền mới bắt nguồn từ đâu.

## 2. Ví dụ nền tảng: tiền hoàn phải gắn với tiền thực thu

Xét đơn hàng chỉ có tiền hàng, chưa có thuế, phí vận chuyển hoặc phương thức thanh toán hỗn hợp:

~~~text
Giá trước giảm:       1.000.000 đồng
Giảm giá của đơn:       200.000 đồng
Tiền thực thu:         800.000 đồng
~~~

Nếu khách hủy toàn bộ đơn sau khi đã thu tiền, khoản hoàn tiền cho giao dịch này tối đa là 800.000 đồng, sau khi trừ các khoản đã hoàn hoặc đang được giữ cho yêu cầu hoàn khác. Không được hoàn 1.000.000 đồng rồi cấp lại voucher 200.000 đồng chỉ vì giao diện hiển thị “giá gốc”.

Nếu chính sách cho phép cấp lại ưu đãi, đó là một quyết định riêng. Việc cấp lại quyền có thể hợp lệ, nhưng không làm tăng số tiền được phép hoàn từ giao dịch gốc.

Khi đơn có thuế, phí, điểm, số dư ví hoặc thẻ quà tặng, phải tách thành phần. Tiền khách tự nạp vào ví có bản chất khác ưu đãi khuyến mại. Không đưa tất cả vào trường `discount` rồi dùng một công thức hoàn chung.

## 3. Chốt chính sách trước khi viết API

Không có một chính sách discount reversal đúng cho mọi mô hình kinh doanh. Bảo mật nằm ở việc hệ thống thực thi nhất quán chính sách đã được lựa chọn và công bố.

### 3.1. Ma trận quyết định tối thiểu

| Tình huống | Xử lý tiền | Xử lý ưu đãi cần quy định |
| --- | --- | --- |
| Hết hạn đơn, chưa thu tiền | Không phát sinh hoàn tiền | Bỏ giữ chỗ nếu chưa tiêu dùng quyền |
| Đã ủy quyền thanh toán nhưng chưa thu tiền | Hủy ủy quyền theo trạng thái thanh toán | Giải phóng hoặc bù trừ theo thời điểm ghi nhận lượt dùng |
| Đã thu tiền, hủy toàn bộ đơn | Hoàn phần thực thu còn được phép hoàn | Có cấp lại quyền hay không; điều kiện và thời hạn |
| Trả một phần hàng | Tính từ các đơn vị hàng được chấp nhận trả | Giữ nguyên hay điều chỉnh lợi ích; thường chưa khôi phục toàn bộ lượt |
| Cửa hàng không giao được hàng | Hoàn theo phần không thực hiện được | Có chính sách cấp lại khác việc khách tự hủy hay không |
| Yêu cầu bị từ chối hoặc hoàn tiền thất bại xác định | Không ghi nhận thành công | Không mở quyền sớm; giải phóng phần giữ chỗ đúng điều kiện |
| Kết quả nhà cung cấp chưa rõ | Giữ trạng thái chờ xác minh | Không coi timeout là thất bại hoặc thành công |

Một chương trình “mỗi khách một lần” cần trả lời rõ: hủy đơn có phục hồi lần dùng đó không? Nếu có, giới hạn số chu kỳ phục hồi hoặc điều kiện chống lạm dụng là gì? Một chuỗi hủy và mua lại có thể tuân thủ giới hạn “chỉ một đơn hoạt động” nhưng vẫn vi phạm mục đích “chỉ trợ giá một lần”.

### 3.2. Điều kiện ngưỡng sau khi trả hàng

Giả sử ưu đãi giảm 100.000 đồng cho đơn từ 500.000 đồng. Khách mua 600.000 đồng rồi trả 400.000 đồng. Có ít nhất hai cách xử lý:

1. Giữ nguyên phân bổ giảm giá ban đầu: hoàn giá sau giảm của phần hàng trả.
2. Tính lại quyền hưởng ưu đãi trên phần hàng giữ lại theo chính sách hoàn trả đã công bố.

Cách thứ hai có thể làm khoản hoàn nhỏ hơn cách thứ nhất. Hệ thống phải lưu đủ phiên bản chính sách để giải thích kết quả; không âm thầm lấy cấu hình chương trình hiện tại áp vào đơn cũ.

Nếu khoản cần thu hồi lớn hơn số tiền có thể khấu trừ trong lần hoàn, không chuyển số tiền hoàn thành số âm rồi tự động thu thêm. Cần một quy trình riêng được chính sách và quyền hạn cho phép, hoặc chặn xử lý tự động để xem xét.

Trong các ví dụ tính tiền phía dưới, giả định chính sách giữ nguyên phân bổ ban đầu. Đây là giả định để minh họa, không phải quy tắc bắt buộc cho mọi dịch vụ.

## 4. Lưu dữ liệu đủ để bảo vệ quy tắc

### 4.1. Các thực thể và vai trò

| Thực thể | Dữ liệu quan trọng |
| --- | --- |
| Order pricing snapshot | Giá, số lượng, tiền tệ, phiên bản chính sách, thuế/phí và các khoản giảm tại lúc chốt đơn |
| Discount allocation | Phân bổ từng nguồn giảm cho dòng hàng hoặc đơn vị hàng |
| Redemption | Chủ thể hưởng ưu đãi, đơn gốc, phiên bản chương trình, số tiền hoặc lượt đã dùng |
| Return claim | Các đơn vị hàng được yêu cầu trả, đã chấp nhận và đã xử lý |
| Refund operation | Đơn, giao dịch thanh toán gốc, số tiền, trạng thái, lý do, khóa chống trùng |
| Reversal ledger | Các khoản bù trừ có dấu và liên kết tới allocation hoặc redemption gốc |
| Entitlement | Quyền dùng ưu đãi và nguồn gốc của quyền được phục hồi |
| Outbox / inbox | Công việc gửi ra ngoài và sự kiện đã nhận, phục vụ xử lý lại an toàn |

Không nhất thiết phải tạo đúng số bảng như trên. Điều quan trọng là dữ liệu mô tả được các trách nhiệm khác nhau và có khóa liên kết ổn định.

Chỉ một `reversed = true` trên đơn thường không đủ cho nhiều lần trả hàng một phần. Ngược lại, một cờ trên từng đơn vị hàng có thể hữu ích nếu chính sách chỉ cho xử lý đơn vị đó đúng một lần; nó vẫn cần liên kết đến khoản hoàn và trạng thái thực hiện.

### 4.2. Snapshot phải do máy chủ tạo

Tại thời điểm chốt đơn, máy chủ lưu dữ liệu giá đã được kiểm tra. Trong yêu cầu hoàn, khách chỉ gửi đối tượng cần trả và lý do. Các trường như sau không phải nguồn dữ liệu có thẩm quyền:

~~~json
{
  "orderId": "O1",
  "items": [{"orderItemId": "I1", "quantity": 1}],
  "claimedRefundAmount": 1000000,
  "claimedDiscountAmount": 200000,
  "restoreCoupon": true,
  "originalPrice": 1000000
}
~~~

Máy chủ có thể bỏ qua hoặc từ chối các trường tiền và quyền ưu đãi ngoài schema. Không dùng chúng để tính khoản hoàn, chọn chủ sở hữu quyền hay quyết định vượt qua phê duyệt.

Các định danh đơn và dòng hàng cũng phải được kiểm tra. Một `orderItemId` hợp lệ nhưng thuộc đơn khác không được chấp nhận chỉ vì tồn tại trong cơ sở dữ liệu.

## 5. Các bất biến cần luôn đúng

Các công thức sau áp dụng cho một giao dịch thu tiền, cùng tiền tệ, chưa xét tranh chấp thanh toán. Nếu có chargeback hoặc điều chỉnh bên ngoài, phải đưa các nghĩa vụ đó vào mô hình đối soát thay vì tiếp tục coi toàn bộ tiền là còn hoàn được.

### 5.1. Bất biến tiền hoàn

Đặt:

- `C`: số tiền đã thu thành công và được phép hoàn của giao dịch gốc.
- `F`: tổng số tiền hoàn đã xác nhận thành công.
- `P`: tổng số tiền đang giữ cho các yêu cầu hoàn còn hiệu lực, gồm cả yêu cầu có kết quả chưa rõ.
- `x`: khoản hoàn mới định chấp nhận.

~~~text
C >= 0
F >= 0
P >= 0
F + P <= C

Chỉ giữ chỗ cho x khi:
x > 0 và F + P + x <= C
~~~

Kiểm tra này phải được thực thi cùng thao tác giữ chỗ trong transaction hoặc một cơ chế nguyên tử tương đương. Đọc số dư, kiểm tra trong mã ứng dụng rồi ghi ở transaction khác tạo ra khoảng trống cho hai yêu cầu cùng vượt giới hạn.

Giới hạn cấp giao dịch chưa đủ. Từng đơn vị hàng hoặc claim cũng cần giới hạn riêng để không thể hoàn cùng món hai lần nhưng vẫn nằm dưới tổng tiền của đơn.

### 5.2. Bất biến phân bổ giảm giá

Với chính sách giữ nguyên phân bổ:

~~~text
Tổng giảm phân bổ cho các đơn vị = giảm giá gốc của phạm vi tương ứng
0 <= giảm của một đơn vị <= giá đủ điều kiện của đơn vị đó
Giá sau giảm của đơn vị = giá trước giảm - giảm phân bổ
~~~

Nếu có nhiều lớp giảm, phải lưu thứ tự áp dụng và phần đóng góp của từng lớp. Không cộng lại các phần trăm một cách tùy ý. Tổng khoản bù trừ của một allocation không được vượt phần đã ghi nhận, kể cả khi có nhiều lần hoàn một phần.

Phần thuế và phí cần chính sách phân bổ riêng. Không suy ra nghĩa vụ thuế chỉ bằng cách trừ giảm giá khỏi giá niêm yết.

### 5.3. Bất biến quyền và ngân sách

- Một quyền được cấp lại phải có chủ sở hữu được suy ra từ giao dịch gốc, không lấy từ body yêu cầu.
- Mỗi điều kiện phục hồi chỉ tạo số quyền tối đa mà chính sách cho phép.
- Phục hồi cùng nguồn nhiều lần phải trả về kết quả đã có hoặc bị từ chối.
- Không đánh dấu lượt gốc là “chưa từng dùng”; lịch sử vẫn phải truy vết được.
- Nếu ngân sách được hoàn lại theo chính sách, tổng hoàn ngân sách không vượt phần đã tiêu dùng của nguồn tương ứng.
- Giải phóng chỗ giữ và hoàn ngân sách đã tiêu dùng là hai phép chuyển khác nhau; không cộng cả hai cho cùng một phần sử dụng.

Nên đặt ràng buộc duy nhất cho khóa nghiệp vụ như `(source_redemption_id, restoration_kind)` khi mỗi lượt chỉ được phục hồi một lần theo loại đó. Với phục hồi nhiều phần, cần khóa cho phần nguồn và giới hạn tổng; một ràng buộc duy nhất đơn giản không tự bảo vệ được tổng số tiền.

## 6. Tính hoàn một phần từ phân bổ đã chốt

### 6.1. Ví dụ hai dòng hàng

Đơn hàng có hai dòng đủ điều kiện:

| Dòng | Giá trước giảm | Giảm được phân bổ | Giá sau giảm |
| --- | ---: | ---: | ---: |
| A | 700.000 | 140.000 | 560.000 |
| B | 300.000 | 60.000 | 240.000 |
| Tổng | 1.000.000 | 200.000 | 800.000 |

Khách trả A thì tiền hàng được hoàn là 560.000 đồng, trước các thành phần khác được quy định riêng. Khách giữ B với lợi ích đã phân bổ là 60.000 đồng.

Nếu lần trả A làm hệ thống cấp lại ngay một voucher đầy đủ 200.000 đồng, khách vừa giữ lợi ích trên B vừa nhận toàn bộ quyền mới. Điều này có thể là lỗ hổng nếu chính sách chỉ cho phục hồi sau khi toàn bộ giao dịch gốc đã được đảo.

Bù trừ 140.000 đồng trong sổ giảm giá cũng không có nghĩa khách nhận thêm 140.000 đồng tiền mặt. Đây là phần điều chỉnh lợi ích của món hàng đã trả; khoản hoàn tiền hàng đã phản ánh giá sau giảm.

### 6.2. Làm tròn phải cố định tới đơn vị có thể trả

Ba món giống nhau, mỗi món 100.000 đồng, cùng hưởng giảm tổng 100.001 đồng. Một phân bổ hợp lệ bằng số nguyên là:

| Đơn vị | Giảm giá | Giá sau giảm |
| --- | ---: | ---: |
| U1 | 33.334 | 66.666 |
| U2 | 33.334 | 66.666 |
| U3 | 33.333 | 66.667 |
| Tổng | 100.001 | 199.999 |

Một cách phân bổ xác định:

1. Tính phần chia theo trọng số giá đủ điều kiện bằng số học chính xác.
2. Lấy phần nguyên theo đơn vị tiền nhỏ nhất của tiền tệ.
3. Phân phối phần dư theo quy tắc ổn định, chẳng hạn phần thập phân lớn nhất rồi đến định danh đơn vị.
4. Lưu kết quả; các lần trả sau đọc lại kết quả đó.

Không chia đều rồi làm tròn độc lập mỗi lần hoàn. Cũng không cho client chọn tùy ý phần dư. Nếu không định danh từng đơn vị, máy chủ phải có cách lấy và đánh dấu các phần phân bổ theo số lượng một cách xác định, có khóa khi cập nhật.

Dùng số nguyên theo đơn vị tiền nhỏ nhất hoặc kiểu số thập phân có thang đo rõ ràng. Tránh số thực nhị phân cho phép cộng tiền và kiểm tra giới hạn.

## 7. Dùng các máy trạng thái riêng nhưng có điều kiện liên kết

Đừng dùng một trường trạng thái để đại diện cả trả hàng, hoàn tiền và voucher. Một yêu cầu trả hàng có thể đã được chấp thuận trong khi cổng thanh toán vẫn đang xử lý; lúc đó tiền và quyền ưu đãi chưa chắc đã được phép chuyển sang trạng thái cuối.

Ví dụ trạng thái khoản hoàn:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Chấp nhận và giữ hạn mức
    PENDING --> SUCCEEDED: Xác nhận hoàn thành công
    PENDING --> UNKNOWN: Chưa xác định kết quả
    PENDING --> FAILED_CONFIRMED: Xác nhận không hoàn
    UNKNOWN --> SUCCEEDED: Đối soát thành công
    UNKNOWN --> FAILED_CONFIRMED: Đối soát thất bại dứt điểm
~~~

`PENDING` bao gồm công việc đã ghi nhận nhưng chưa có kết quả cuối. `UNKNOWN` cho biết không đủ bằng chứng xác định hiệu ứng bên ngoài. Cả hai đều giữ phần `P` trong giới hạn tiền hoàn.

### 7.1. Điều kiện chuyển trạng thái

| Chuyển đổi | Điều kiện và hiệu ứng |
| --- | --- |
| Tạo PENDING | Claim hợp lệ, đúng quyền, đủ hạn mức; giữ tiền hoàn và các đơn vị hàng tương ứng |
| PENDING → UNKNOWN | Timeout, mất kết nối hoặc kết quả không đủ chắc chắn; tiếp tục giữ hạn mức |
| PENDING/UNKNOWN → SUCCEEDED | Có bằng chứng đáng tin cậy cho đúng refund operation; chuyển tiền đang giữ sang đã hoàn |
| PENDING/UNKNOWN → FAILED_CONFIRMED | Có bằng chứng thao tác không tạo khoản hoàn và không còn khả năng thực thi muộn; giải phóng phần đang giữ |
| SUCCEEDED → SUCCEEDED | Đọc lại kết quả, không tạo hiệu ứng thêm |
| Trạng thái cuối → trạng thái trước | Không cho phép chỉ vì sự kiện đến trễ hoặc được phát lại |

Một mã lỗi HTTP hoặc timeout không tự chứng minh tiền chưa được hoàn. Ngay cả khi cần mở lại thao tác cho nhân viên, việc mở lại cũng phải gắn với cùng operation và tình trạng bên ngoài đã được xác minh.

Nếu hỗ trợ hủy trước khi gửi, hệ thống phải bảo đảm công việc thực sự chưa được phát đi và không còn worker nào có thể gửi nó sau khi phần giữ được giải phóng. Xóa một dòng outbox trong khi worker đã đọc dòng đó không cung cấp bảo đảm này.

### 7.2. Trạng thái quyền ưu đãi

Một mô hình đơn giản có thể dùng:

~~~text
RESERVED → CONSUMED
RESERVED → RELEASED
CONSUMED → PARTIALLY_REVERSED → FULLY_REVERSED
~~~

Đây là trạng thái của việc sử dụng ưu đãi, không phải trạng thái thanh toán. Không phải nghiệp vụ nào cũng cần đủ các trạng thái này.

Nếu chỉ cho phục hồi sau khi hủy toàn bộ đã hoàn tất, điều kiện cấp quyền có thể là:

~~~text
Tất cả đơn vị đủ điều kiện đã được chấp nhận trả hoặc hủy
AND các khoản hoàn cần thiết đã được xác nhận thành công
AND không còn nghĩa vụ liên quan đang chờ xử lý
AND chính sách của lượt dùng gốc cho phép phục hồi
AND chưa có quyền phục hồi cho điều kiện này
~~~

Cửa hàng có thể chọn cấp lại sớm trong một số trường hợp. Khi đó phải mô hình hóa rõ quyền cấp trước, điều kiện sử dụng và cách xử lý nếu luồng hoàn thất bại. Không chỉ chuyển điều kiện từ “đã hoàn” thành “đã nhận yêu cầu”.

## 8. Luồng xử lý an toàn từ API tới hệ thống thanh toán

### 8.1. Xác thực và phân quyền trên đối tượng

Một yêu cầu có đăng nhập vẫn có thể truy cập sai đơn. Máy chủ cần kiểm tra:

- Đơn thuộc đúng tenant hoặc cửa hàng mà chủ thể được phép thao tác.
- Khách được gửi yêu cầu cho đơn của mình; nhân viên cần quyền phù hợp với loại hoàn và phạm vi cửa hàng.
- Các dòng hàng thuộc đúng đơn, đúng người bán nếu đơn nhiều bên, đúng số lượng còn có thể trả.
- Trạng thái giao hàng, cửa sổ trả hàng và bước phê duyệt đáp ứng chính sách.
- Quyền “phê duyệt hoàn tiền”, “thực thi hoàn tiền” và “cấp lại ưu đãi” được kiểm tra tại nơi có hiệu ứng tương ứng.

Giấu nút trên giao diện không bảo vệ API. Nếu quy trình yêu cầu phê duyệt, endpoint thực thi phải kiểm tra bản ghi phê duyệt có hiệu lực, đúng đối tượng và đúng số tiền. Đổi số tiền hoặc phạm vi hàng trả sau phê duyệt phải làm mất hiệu lực phê duyệt cũ hoặc tạo một phiên bản cần duyệt lại.

Ngay cả khi trả lại kết quả của một idempotency key cũ, phải kiểm tra quyền đọc operation đó. Khóa chống trùng không phải bằng chứng sở hữu.

### 8.2. Transaction tạo khoản hoàn

Đoạn giả mã sau thể hiện ranh giới kiểm tra và ghi dữ liệu. Tên hàm biểu thị trách nhiệm cần triển khai, không phải API của một framework cụ thể.

~~~text
requestRefund(actor, orderId, command, idempotencyKey):
    requireValidShape(command)
    fingerprint = canonicalFingerprint(orderId, command)

    begin transaction

        order = lockOrder(orderId)
        authorizeRefundRequest(actor, order)

        previous = findIdempotency(
            tenant = order.tenantId,
            actor = actor.id,
            operation = "REQUEST_REFUND",
            key = idempotencyKey
        )

        if previous exists:
            requireSameFingerprint(previous, fingerprint)
            commit
            return authorizedResult(previous)

        claim = lockApprovedReturnClaim(command.claimId)
        requireClaimBelongsToOrder(claim, order)
        requireApprovalMatchesCurrentClaim(claim)
        requireClaimIsNotAlreadyBoundToAnotherRefund(claim)

        source = lockOriginalPayment(order, command.paymentReference)
        requireSourceBelongsToOrder(source, order)

        units = lockReturnableUnits(claim)
        amount = calculateFromStoredAllocations(units, order.policySnapshot)
        requireMoneyCurrencyMatches(amount, source)
        requireUnitsNotAlreadyReservedOrRefunded(units)
        requireWithinPaymentLimit(source, amount)
        requireReversalWithinOriginalAllocations(units)

        operation = insertRefund(
            sourcePayment = source.id,
            claim = claim.id,
            amount = amount,
            status = PENDING
        )

        reserveRefundCapacity(source, operation)
        reserveUnitsAndReversalAllocations(units, operation)
        bindClaimToRefund(claim, operation)

        insertIdempotencyMapping(idempotencyKey, fingerprint, operation)
        insertOutbox("SUBMIT_REFUND", operation.id)
        appendAudit("REFUND_ACCEPTED", actor, operation)

    commit

    return operation
~~~

Các yêu cầu quan trọng của ví dụ:

- Mọi đường ghi liên quan, kể cả công cụ quản trị, tuân thủ cùng kỷ luật khóa và bất biến.
- Khóa đơn giúp tuần tự hóa thao tác trên đơn trong mô hình này; các tài nguyên chia sẻ giữa nhiều đơn vẫn cần cơ chế bảo vệ riêng.
- Khóa hoặc cập nhật có điều kiện phải bao phủ cả số tiền lẫn số lượng hàng đã giữ.
- Ràng buộc cơ sở dữ liệu ngăn một claim sinh hai khoản hoàn dù client đổi idempotency key.
- Nếu thứ tự khóa gồm nhiều tài nguyên, dùng thứ tự thống nhất để giảm deadlock; khi thử lại transaction phải giữ định danh nghiệp vụ.
- Với đơn trả qua nhiều giao dịch thanh toán, chia khoản hoàn theo nguồn và kiểm tra hạn mức từng nguồn. Giới hạn tổng cấp đơn không thay thế được giới hạn này.

Có thể dùng cập nhật có điều kiện hoặc optimistic locking thay khóa bi quan, miễn kiểm tra giới hạn và ghi hiệu ứng là nguyên tử. Một phép đọc trước transaction không đáp ứng yêu cầu đó.

### 8.3. Gọi dịch vụ bên ngoài qua outbox

Không nên giữ khóa cơ sở dữ liệu trong suốt thời gian chờ mạng. Transaction cục bộ ghi operation, phần giữ và outbox trước; worker xử lý công việc sau commit.

~~~text
Transaction cục bộ
    └─ Refund PENDING + giữ hạn mức + outbox

Worker
    └─ Gửi yêu cầu hoàn với định danh ổn định của operation

Phản hồi / callback / đối soát
    └─ Transaction chốt kết quả + sổ bù trừ + điều kiện phục hồi quyền
~~~

Nếu worker bị dừng sau khi dịch vụ thanh toán nhận yêu cầu nhưng trước khi lưu phản hồi, lần xử lý lại phải sử dụng cùng định danh hoàn bên ngoài. Cần dựa trên khả năng chống trùng và truy vấn kết quả mà nhà cung cấp thực sự hỗ trợ, kể cả thời gian lưu khóa.

Outbox không tự tạo bảo đảm “thực thi đúng một lần” ở nhà cung cấp. Nó giúp không bỏ sót ý định đã commit; chống trùng ở đích, truy vấn trạng thái và đối soát mới xử lý được hiệu ứng bên ngoài.

Nếu nhà cung cấp không hỗ trợ chống trùng đáng tin cậy, không tự động tạo một khoản hoàn mới chỉ vì lần cũ không có phản hồi. Giữ trạng thái chưa rõ và chuyển sang xác minh trước khi quyết định bước tiếp theo.

### 8.4. Chốt kết quả và ghi bù trừ

Khi có xác nhận thành công:

~~~text
begin transaction
    xác thực và đối chiếu sự kiện với nhà cung cấp, tài khoản và operation
    khóa operation và các bản ghi liên quan
    nếu operation đã SUCCEEDED:
        ghi nhận sự kiện đã thấy nếu cần; không tạo hiệu ứng thêm
    nếu chuyển trạng thái hợp lệ:
        chuyển phần tiền giữ từ P sang F
        chuyển đơn vị hàng sang đã hoàn
        ghi bù trừ theo đúng allocation gốc
        đánh giá điều kiện phục hồi quyền và ngân sách
        ghi các hiệu ứng cục bộ và audit
commit
~~~

Nếu quyền ưu đãi nằm cùng cơ sở dữ liệu, có thể tạo quyền bằng ràng buộc duy nhất trong transaction này. Nếu do dịch vụ khác quản lý, ghi thêm outbox với khóa nghiệp vụ ổn định; bên nhận phải chống trùng và kiểm tra nguồn. Khi chưa hoàn tất, theo dõi trạng thái phục hồi đang chờ riêng.

Dedupe theo `provider_event_id` hữu ích nhưng chưa đủ: nhà cung cấp có thể gửi nhiều sự kiện khác ID cho cùng một khoản hoàn. Guard chuyển trạng thái và khóa nghiệp vụ của operation vẫn phải ngăn ghi bù trừ hai lần.

Sự kiện đến trễ không được đưa `SUCCEEDED` về `PENDING` hoặc giải phóng hạn mức như một khoản thất bại. Nếu dữ liệu cuối có mâu thuẫn, cần ghi nhận và đối soát thay vì tự suy đoán theo thứ tự nhận sự kiện.

## 9. Idempotency có hai tầng

### 9.1. Tầng yêu cầu

Một khóa thường được gắn với phạm vi như tenant, chủ thể, loại thao tác và khóa do client gửi. Cần lưu:

~~~text
scope
idempotency_key
request_fingerprint
refund_operation_id
created_at
~~~

Fingerprint được tính từ các trường nghiệp vụ đã chuẩn hóa, chẳng hạn đơn, claim, phiên bản claim và phạm vi yêu cầu. Máy chủ vẫn tự tính tiền. Không để thứ tự thuộc tính JSON hoặc dữ liệu không liên quan làm biến đổi ý nghĩa khóa.

Quy ước phản hồi nên rõ ràng:

| Lần gọi sau | Kết quả |
| --- | --- |
| Cùng khóa, cùng nội dung | Trả cùng operation và trạng thái hiện tại |
| Cùng khóa, nội dung khác | Từ chối xung đột, chẳng hạn HTTP 409 |
| Khóa mới, cùng claim đã ràng buộc | Trả operation đã có theo hợp đồng hoặc từ chối; không tạo khoản hoàn khác |
| Khác chủ thể nhưng đoán được khóa | Vẫn phải qua xác thực và quyền theo đối tượng |

Sau thời gian lưu cache idempotency, bất biến claim, hàng và hạn mức vẫn phải giữ được. Không dựa vào TTL của khóa để bảo vệ một giao dịch có thể được phát lại sau nhiều ngày.

### 9.2. Tầng hiệu ứng nghiệp vụ

Khách có thể cố ý thay khóa mỗi lần gọi; nhân viên có thể thao tác trên kênh quản trị khác. Vì thế cần các khóa và giới hạn độc lập với yêu cầu:

- Claim đã được gắn với khoản hoàn nào.
- Đơn vị hàng nào đang giữ hoặc đã hoàn.
- Phần allocation gốc còn được bù trừ bao nhiêu.
- Nguồn redemption đã tạo quyền phục hồi nào.
- Giao dịch thanh toán còn bao nhiêu hạn mức hoàn.

Idempotency ngăn phát lại một ý định thành nhiều hiệu ứng. Nó không tự quyết định một ý định mới có hợp lệ hay không.

## 10. Những đường lạm dụng cần chủ động chặn

### 10.1. Hoàn giá gốc, giữ lợi ích giảm giá

**Chuỗi thao tác:** mua hàng có voucher, gọi hoàn bằng giá niêm yết hoặc sửa trường số tiền trong request.

**Điểm sai:** tin dữ liệu client hoặc dùng giá hiện tại thay snapshot đã chốt.

**Chốt chặn:** tính lại ở máy chủ từ phân bổ đã lưu, kiểm tra hạn mức tiền và phần hàng. Chỉ chặn vượt tổng đơn vẫn có thể hoàn quá nhiều cho một món rồi thiếu tiền để hoàn món còn lại.

### 10.2. Phục hồi voucher ngay khi gửi yêu cầu

**Chuỗi thao tác:** gửi yêu cầu trả hàng, nhận voucher được phục hồi, dùng voucher cho đơn khác, rồi hủy yêu cầu trả.

**Điểm sai:** coi ý định trả hàng là bằng chứng giao dịch gốc đã được đảo.

**Chốt chặn:** gắn việc cấp quyền với mốc nghiệp vụ được quy định rõ; nếu chọn cấp sớm, phải mô hình hóa và giới hạn rủi ro cấp trước.

### 10.3. Chia nhỏ lần hoàn để tăng số quyền

**Chuỗi thao tác:** trả từng món trong đơn nhiều món; mỗi callback lại mở một voucher toàn phần.

**Điểm sai:** coi mỗi lần hoàn là một lý do độc lập để phục hồi toàn bộ lượt dùng.

**Chốt chặn:** tổng hợp phần đã bù trừ ở redemption gốc; khóa nguồn phục hồi và kiểm tra điều kiện toàn phần hoặc định lượng theo chính sách.

### 10.4. Hai yêu cầu đồng thời cùng đọc hạn mức cũ

Giả sử còn được hoàn 100.000 đồng. Hai yêu cầu khác nhau, mỗi yêu cầu 70.000 đồng, cùng đọc số dư trước khi ghi. Nếu chỉ kiểm tra trong bộ nhớ, cả hai có thể được chấp nhận, tổng là 140.000 đồng.

**Chốt chặn:** kiểm tra và giữ hạn mức nguyên tử. Nếu một yêu cầu đã giữ 70.000 đồng thì yêu cầu sau chỉ thấy 30.000 đồng khả dụng, kể cả khi khoản hoàn đầu chưa hoàn tất ở cổng thanh toán.

### 10.5. Lợi dụng timeout để thực hiện hoàn lần hai

**Chuỗi thao tác:** nhà cung cấp đã nhận khoản hoàn, API timeout, hệ thống giải phóng hạn mức và tạo operation mới khi người dùng thử lại.

**Điểm sai:** đánh đồng “chưa biết” với “không có hiệu ứng”.

**Chốt chặn:** giữ trạng thái `UNKNOWN`, tra cứu cùng operation và cùng định danh bên ngoài, giữ hạn mức tới khi có kết luận đủ chắc chắn.

### 10.6. Mua đủ ngưỡng rồi trả phần lớn

**Chuỗi thao tác:** thêm hàng để vượt ngưỡng voucher, sau đó trả những món thêm vào.

**Điểm sai:** hệ thống không có chính sách rõ cho điều kiện ngưỡng sau hoàn, hoặc mỗi endpoint áp một quy tắc khác.

**Chốt chặn:** định nghĩa chính sách và lưu phiên bản; tính khoản hoàn theo cùng quy tắc trên API khách, quản trị và tác vụ nền. Nếu doanh nghiệp cho giữ lợi ích đã phân bổ, đây là hành vi được chấp nhận theo thiết kế, không tự động là một cuộc tấn công.

### 10.7. Vòng lặp dùng và hủy ưu đãi một lần

**Chuỗi thao tác:** dùng ưu đãi giới hạn theo khách, hủy đơn để phục hồi, lặp lại nhằm giữ suất khuyến mại hoặc khai thác quà tặng phát sinh.

**Điểm sai:** phục hồi lượt dùng nhưng không xét các lợi ích phụ và ý nghĩa của giới hạn chương trình.

**Chốt chặn:** áp dụng điều kiện số chu kỳ, mốc thực hiện và quyền hưởng theo chính sách. Kiểm tra cả quà, điểm thưởng hoặc trợ giá đi kèm nếu chúng có thể còn lại sau hủy. Rate limit chỉ giảm tốc độ, không thay thế quy tắc này.

## 11. Những trường hợp biên cần thiết kế riêng

### 11.1. Đơn được giảm về 0 đồng

Đơn miễn phí vẫn có thể tiêu dùng lượt ưu đãi, hàng tồn hoặc ngân sách. Hủy đơn như vậy có thể cần bù trừ và phục hồi quyền dù không có khoản tiền để hoàn.

Điều kiện `x > 0` trong phần bất biến áp dụng khi tạo một khoản hoàn tiền. Không dùng nó để chặn mọi luồng trả hàng hoặc hủy đơn có giá trị thanh toán bằng 0. Xử lý việc hủy, bù trừ và quyền ưu đãi theo nghiệp vụ; không tạo một giao dịch hoàn tiền giả chỉ để kích hoạt callback.

### 11.2. Voucher đã hết hạn

Quyền được phục hồi có thể giữ ngày hết hạn gốc, có thời hạn mới theo chính sách hoặc không được phục hồi. Quyết định này phải được ghi lại và giải thích được.

Không đặt lại voucher gốc thành hoạt động vô thời hạn. Nếu chương trình đã dừng, một quyền thay thế cũng không được tự vượt qua các giới hạn chương trình trừ khi có chính sách cho phép.

### 11.3. Đơn nhiều người bán hoặc nhiều nguồn trợ giá

Một khoản giảm có thể do sàn, cửa hàng hoặc đối tác tài trợ. Khi trả hàng, phần bù trừ cần đi theo allocation và nguồn tài trợ gốc, không lấy tổng giảm của đơn trả về một ngân sách bất kỳ.

Tương tự, nhân viên của cửa hàng A không được hoàn hàng hoặc phục hồi quyền cho phần của cửa hàng B chỉ vì hai phần cùng thuộc một mã đơn tổng.

### 11.4. Sửa giá hoặc ưu đãi sau khi đơn đã chốt

Mọi thay đổi sau chốt đơn cần một điều chỉnh có định danh và quy tắc ưu tiên rõ ràng. Nếu một hoàn tiền đã giữ chỗ trên snapshot cũ, việc sửa giá không được làm cơ sở tính tiền thay đổi âm thầm bên dưới operation đó.

Có thể khóa phiên bản tính giá cho từng operation hoặc yêu cầu tính và phê duyệt lại trước khi gửi. Không sửa lịch sử để khiến các khoản đã hoàn trước đây trông như được tính theo giá mới.

## 12. Kiểm thử tình huống tấn công logic

Kiểm thử cần đi qua đường xử lý nghiệp vụ và kiểm tra dữ liệu sau cùng. Chỉ xác nhận HTTP 200 hoặc 409 chưa cho biết có phát sinh khoản hoàn, quyền mới hay ngân sách bị tăng ngoài ý muốn hay không.

### 12.1. Ma trận tình huống

| Tình huống | Kết quả cần quan sát |
| --- | --- |
| Hủy trước khi thu tiền | Giải phóng đúng phần giữ, không gọi hoàn tiền |
| Hủy toàn bộ đơn 1.000.000 đồng, giảm 200.000 đồng | Tổng tiền hoàn không vượt 800.000 đồng; quyền theo đúng chính sách |
| Trả A trong ví dụ hai dòng | Tiền hàng hoàn 560.000 đồng; không cấp quyền toàn phần nếu chưa đủ điều kiện |
| Trả các đơn vị theo nhiều thứ tự | Tổng khoản hoàn đúng các allocation cố định; không tăng do làm tròn lại |
| Sửa số tiền và cờ phục hồi trong body | Không thay đổi giá trị do máy chủ tính hoặc vượt quyền |
| Dùng dòng hàng thuộc đơn khác | Bị từ chối; không đổi trạng thái hoặc số dư |
| Khách hoặc nhân viên truy cập sai tenant | Không đọc hoặc thực hiện được operation ngoài phạm vi |
| Bỏ qua bước phê duyệt | Không tạo lệnh hoàn hoặc quyền phục hồi |
| Đổi claim sau phê duyệt | Phê duyệt cũ không cho thực thi nội dung mới |
| Cùng khóa, cùng nội dung | Cùng operation; một khoản hoàn và một tập hiệu ứng |
| Cùng khóa, khác nội dung | Xung đột; không ghi thêm phần giữ |
| Khóa khác, cùng claim | Không tạo khoản hoàn thứ hai |
| Hai claim hợp lệ tranh cùng hạn mức | Chỉ tổng tiền trong giới hạn được giữ |
| Hai yêu cầu cùng trả một đơn vị | Chỉ một yêu cầu giữ hoặc hoàn được đơn vị đó |
| Callback phát lại hoặc khác event ID nhưng cùng khoản hoàn | Không tăng tiền hoàn, bù trừ hoặc quyền lần hai |
| Worker dừng sau khi nhà cung cấp nhận lệnh | Xử lý lại cùng operation, không tạo khoản hoàn độc lập |
| Timeout rồi trả lời thành công muộn | Giữ hạn mức trong thời gian chưa rõ; chốt thành công một lần |
| Sự kiện cũ đến sau SUCCEEDED | Không hạ trạng thái hoặc giải phóng tiền lần nữa |
| Hoàn một phần rồi hoàn phần còn lại | Tổng bù trừ bằng phần gốc; phục hồi đúng mốc và tối đa số quyền cho phép |
| Hoàn thất bại được xác nhận dứt điểm | Giải phóng đúng phần giữ; không ghi thành công hoặc cấp quyền sai điều kiện |
| Đơn 0 đồng | Xử lý hủy và quyền mà không tạo hoàn tiền giả |
| Phục hồi voucher đã hết hạn | Tuân thủ thời hạn và phiên bản chính sách đã chọn |
| Gọi lại sau khi khóa idempotency hết hạn lưu | Bất biến claim và allocation vẫn ngăn hiệu ứng lặp |
| Đổi cấu hình chiến dịch sau ngày mua | Đơn cũ dùng đúng snapshot hoặc điều chỉnh đã được ghi nhận |

### 12.2. Cách tạo bài kiểm thử đồng thời có ý nghĩa

Để kiểm tra giới hạn 100.000 đồng với hai yêu cầu 70.000 đồng, điều phối hai tiến trình tới gần điểm kiểm tra và giữ hạn mức rồi cho chúng cạnh tranh. Sau khi cả hai kết thúc, truy vấn các số dư và operation.

Kết quả cần chứng minh:

~~~text
Tổng phần giữ + tổng phần đã hoàn <= tiền đã thu
Không có cùng đơn vị hàng thuộc hai khoản hoàn còn hiệu lực
Không có hai quyền phục hồi cho cùng điều kiện nguồn
Không có phần bù trừ vượt allocation gốc
~~~

Không dựa vào việc thêm một khoảng ngủ ngẫu nhiên rồi kỳ vọng race xuất hiện. Bài kiểm thử nên kiểm soát được điểm đồng bộ hoặc ít nhất chạy có điều phối để đường cạnh tranh thực sự xảy ra.

### 12.3. Kiểm thử theo chuỗi trạng thái

Ngoài các ca riêng lẻ, có thể tạo chuỗi:

~~~text
mua → giảm giá → thanh toán → yêu cầu trả một phần
→ nhận callback trùng → thử lại yêu cầu → trả phần còn lại
→ đối soát → thử dùng quyền phục hồi
~~~

Sau mỗi bước, kiểm tra bất biến thay vì chỉ kiểm tra cuối chuỗi. Với chính sách giữ phân bổ, các cách chia một tập hàng thành nhiều lần hoàn phải cho cùng tổng tiền của tập đó. Nếu chương trình có phí theo lần trả hoặc chính sách khác phụ thuộc thứ tự, cần mô hình hóa kỳ vọng ấy rõ ràng thay vì áp dụng tính chất này máy móc.

Các bài kiểm thử này còn giúp phát hiện đường quản trị hoặc tác vụ nền bỏ qua logic mà API khách đã thực hiện đúng.

## 13. Audit và đối soát để tìm hiệu ứng bị thiếu

Mỗi operation nên truy vết được tới đơn, claim, giao dịch thu tiền, redemption và allocation gốc. Audit ghi chủ thể thực hiện, hành động, lý do, phiên bản chính sách, trạng thái trước/sau và định danh nhà cung cấp nếu có.

Các câu hỏi cần trả lời được từ dữ liệu:

- Vì sao khách nhận đúng số tiền này?
- Đơn vị hàng nào đã được hoàn, đơn vị nào đang giữ?
- Voucher được cấp lại do điều kiện nào và đã được dùng vào đâu?
- Phần tài trợ nào được hoàn ngân sách?
- Operation nào đã có hiệu ứng bên ngoài nhưng chưa chốt ở nội bộ?
- Có khoản hoàn nội bộ nào không khớp nhà cung cấp hoặc bù trừ quyền còn đang chờ?

Đối soát định kỳ tìm operation chờ quá lâu, trạng thái không khớp, phần giữ mồ côi và quyền phục hồi chưa hoàn tất. Việc sửa lệch phải đi qua hành động nghiệp vụ có định danh, chống trùng và audit. Không cập nhật thẳng số dư hoặc bật lại voucher chỉ để làm các con số trông khớp.

## 14. Tự đánh giá thiết kế

Trước khi coi luồng discount reversal đã đủ rõ để triển khai, hãy tự trả lời:

1. Hệ thống đang bỏ giữ chỗ, bù trừ lượt dùng, hoàn tiền hay cấp lại quyền ở từng bước?
2. Nguồn dữ liệu nào quyết định số tiền và ai được phép phê duyệt?
3. Giá, phân bổ và chính sách của đơn gốc có được lưu đủ để xử lý một phần không?
4. Những bất biến nào được bảo vệ nguyên tử bằng transaction và ràng buộc dữ liệu?
5. Thay idempotency key có tạo thêm hiệu ứng cho cùng claim không?
6. Khi nhà cung cấp đã thực hiện nhưng phản hồi bị mất, hệ thống giữ giới hạn và xác minh thế nào?
7. Mốc phục hồi quyền có thể bị khai thác trước khi việc hủy hoặc trả hoàn tất không?
8. Sau nhiều lần hoàn một phần, có giải thích được tổng tiền, tổng bù trừ và số quyền được tạo không?

Một thiết kế tốt cho phép lần theo mọi hiệu ứng từ giao dịch gốc tới bản ghi bù trừ, giữ được giới hạn khi thao tác trùng hoặc đồng thời và có đường xử lý rõ ràng cho kết quả chưa xác định.
