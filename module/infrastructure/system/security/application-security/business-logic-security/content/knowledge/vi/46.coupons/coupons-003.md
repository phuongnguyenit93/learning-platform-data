# Coupon redemption count: đếm lượt dùng coupon an toàn

## Mục tiêu và phạm vi

Coupon redemption count là số lượt sử dụng mã ưu đãi được hệ thống ghi nhận theo một quy tắc nghiệp vụ cụ thể. Một “lượt” có thể là một đơn đã chấp nhận ưu đãi, một lần thanh toán hoàn tất hoặc một đơn vị sản phẩm đủ điều kiện. Phải chọn rõ ý nghĩa này trước khi viết bộ đếm.

Trong bảo mật logic nghiệp vụ, bộ đếm là cơ chế phân phối một quyền lợi hữu hạn. Nếu đếm sai, khách có thể dùng coupon nhiều lần hơn được phép, lấy lượt của người khác hoặc làm vượt giới hạn của chương trình. Lỗi thường xuất hiện khi kiểm tra và cập nhật ở hai thời điểm khác nhau, tin định danh do client gửi, bỏ qua lượt đang giữ hoặc tăng bộ đếm theo số lần nhận sự kiện.

Bài học tập trung vào các bất biến, máy trạng thái, quyền theo đối tượng, transaction, idempotency và kiểm thử tấn công logic. Mục tiêu là làm cho “mỗi khách một lần”, “tối đa 1.000 lượt” hoặc “mỗi đơn một mã trong nhóm” trở thành những quy tắc có thể thực thi, không chỉ là dòng mô tả trên giao diện.

Sau bài này, bạn có thể:

- Định nghĩa một lượt dùng và phạm vi giới hạn của từng bộ đếm.
- Phân biệt lượt đang giữ, lượt đã tiêu dùng, số dùng lũy kế và số dùng còn tính hạn mức.
- Cấp lượt nguyên tử khi nhiều yêu cầu tranh cùng phần còn lại.
- Chống phát lại ở cả tầng request và tầng nghiệp vụ.
- Xử lý hủy, hết hạn, hoàn đơn và kết quả thanh toán chưa rõ mà không tạo thêm lượt ngoài chính sách.
- Xây dựng kiểm thử đồng thời và đối soát bộ đếm từ lịch sử nghiệp vụ.

## 1. Định nghĩa “một lượt” trước khi đếm

### 1.1. Những sự kiện không tự động là redemption

Các hành động sau thường chưa phải sử dụng coupon thành công:

- Nhập mã vào ô tìm kiếm.
- Gọi API kiểm tra mã.
- Nhìn thấy một báo giá sau giảm.
- Thêm coupon vào giỏ nhưng chưa giữ quyền.
- Gửi yêu cầu thanh toán chưa có kết quả cuối.
- Nhận lại một callback hoặc message đã từng xử lý.

Nếu mỗi lần gọi API kiểm tra đều tăng số dùng, người khác có thể làm cạn lượt mà không mua hàng. Nếu chỉ đếm khi thanh toán thành công nhưng không giữ chỗ trước đó, nhiều đơn cùng chờ thanh toán có thể vượt giới hạn.

Cần tách ít nhất ba loại số liệu:

| Loại số liệu | Mục đích |
| --- | --- |
| Validation attempts | Thống kê và kiểm soát tần suất thử mã |
| Reserved usage | Lượt được giữ cho ý định mua hợp lệ nhưng chưa tiêu dùng cuối |
| Redeemed usage | Lượt đã được ghi nhận tiêu dùng theo mốc nghiệp vụ |

Bộ đếm chống thử mã không thay thế bộ đếm quyền sử dụng. Rate limit giới hạn tốc độ yêu cầu, không chứng minh tổng lượt hưởng ưu đãi còn hợp lệ.

### 1.2. Chọn đơn vị đếm

Ví dụ một đơn có ba sản phẩm và dùng một coupon giảm giá toàn đơn:

- Nếu giới hạn tính theo đơn: đơn đó tiêu dùng một lượt.
- Nếu coupon áp cho từng sản phẩm và giới hạn tính theo số đơn vị: đơn đó có thể tiêu dùng ba lượt.
- Nếu chỉ một sản phẩm được giảm: số lượng được tính phải theo các đơn vị đủ điều kiện, không theo toàn bộ giỏ.

Đơn vị phải được xác định riêng cho từng hạn mức. Không cộng số đơn và số sản phẩm vào cùng một bộ đếm.

Trong các ví dụ chính của bài, giả định **mỗi đơn đủ điều kiện tiêu dùng một lượt**. Khi cần đếm theo số lượng, máy chủ tính lượng tăng từ dữ liệu đơn đã kiểm tra; không nhận trực tiếp một trường `usageCount` có thẩm quyền từ client.

### 1.3. Chọn mốc tiêu dùng

Doanh nghiệp có thể ghi nhận redemption khi đơn được chấp nhận, khi thanh toán hoàn tất hoặc khi một dịch vụ được thực hiện. Mỗi lựa chọn cần quy tắc tương ứng cho trường hợp thất bại sau đó.

Với mô hình thanh toán trước, một luồng dễ hiểu là:

~~~text
Kiểm tra đủ điều kiện → giữ lượt → thanh toán → tiêu dùng lượt
                                     └─ thất bại xác định → giải phóng
~~~

Đơn có tổng thanh toán bằng 0 vẫn có thể tiêu dùng lượt ưu đãi. Không phụ thuộc duy nhất vào callback thanh toán để nhận biết redemption nếu loại đơn đó không có giao dịch thanh toán.

## 2. Một coupon có thể chịu nhiều giới hạn cùng lúc

### 2.1. Phạm vi đếm

| Phạm vi | Ví dụ quy tắc |
| --- | --- |
| Toàn chương trình | Tối đa 1.000 lượt cho cả chiến dịch |
| Một mã coupon chuẩn hóa | Mã SAVE10 có tối đa 300 lượt |
| Một quyền coupon được phát hành | Mỗi voucher cá nhân chỉ được dùng một lần |
| Khách hàng trong chương trình | Mỗi khách tối đa một lượt, kể cả dùng mã khác nhau |
| Khách hàng với một coupon | Mỗi khách tối đa hai lượt cho mã được chỉ định |
| Đơn hàng hoặc nhóm lợi ích | Mỗi đơn chỉ có một lợi ích trong nhóm không cộng dồn |
| Cửa hàng hoặc kênh | Tối đa một số lượt trong phạm vi được cấu hình |
| Một đợt | Giới hạn riêng cho từng đợt có định danh rõ |

Các hạn mức được áp dụng đồng thời nếu chính sách yêu cầu. Một mã còn lượt không đồng nghĩa chương trình còn lượt; chương trình còn lượt không đồng nghĩa khách chưa dùng hết phần của mình.

Ví dụ:

~~~text
Chương trình P: tối đa 1.000 lượt
Mã A thuộc P: tối đa 300 lượt
Mã B thuộc P: tối đa 700 lượt
Mỗi khách trong P: tối đa 1 lượt
Mỗi đơn trong nhóm G: tối đa 1 lợi ích
~~~

Khách đã dùng A không được dùng B để lấy thêm một lượt nếu giới hạn được đặt theo khách trong P. Kiểm tra riêng `(customer, coupon_code)` sẽ bỏ sót quy tắc này.

### 2.2. Cùng mã hiển thị không nhất thiết cùng một quyền

Mã công khai có thể được nhiều khách sử dụng. Voucher cá nhân có thể là một quyền riêng được phát cho một người. Hai loại này cần định danh và hạn mức phù hợp.

Nếu hệ thống cho phép nhiều cách viết mã tương đương, tất cả phải được phân giải về cùng `coupon_id` trước khi đếm. Không tạo bộ đếm riêng từ chuỗi người dùng nhập như SAVE10, save10 hoặc một alias được hệ thống công nhận.

Ngược lại, nếu phát hành một quyền mới có mã hiển thị được tái sử dụng theo chính sách, cần phân biệt bằng định danh phát hành. Không tự suy luận danh tính quyền từ duy nhất chuỗi mã.

Quy tắc phân biệt chữ hoa, chữ thường hoặc chuẩn hóa phải nhất quán giữa nơi tra mã, nơi áp ưu đãi và nơi đếm. Không tự thay đổi cách chuẩn hóa ở một endpoint rồi để endpoint khác hiểu một mã thành quyền khác.

### 2.3. Định danh khách phải lấy từ nguồn có thẩm quyền

Không dùng `customerId`, email hoặc số điện thoại trong body làm chủ thể đếm chỉ vì client khai báo như vậy. Với khách đã đăng nhập, máy chủ suy ra chủ thể từ phiên xác thực và các liên kết danh tính đã được kiểm tra.

Một tài khoản có thể thay email mà vẫn là cùng chủ thể. Nếu bộ đếm gắn với email có thể sửa, thay email có thể tạo ra “khách mới” ngoài ý muốn.

Cần phân biệt “mỗi tài khoản” với “mỗi người”. Một giới hạn theo account ID chỉ thực thi giới hạn theo tài khoản. Nếu doanh nghiệp yêu cầu theo một người hoặc một tổ chức, phải có chính sách liên kết chủ thể và mức xác minh phù hợp; bộ đếm không tự giải quyết được danh tính ngoài đời.

Đối với khách vãng lai, cần quyết định phạm vi có thể thực thi: phiên, đơn, danh tính đã xác minh hay không cho dùng chương trình đó. Không mô tả chắc chắn “mỗi người một lần” nếu thực tế chỉ dựa vào một cookie có thể xóa.

## 3. Mô hình đếm: giữ lượt, tiêu dùng và phục hồi

### 3.1. Ba đại lượng khác nhau

Với mỗi phạm vi giới hạn, đặt:

- `L`: giới hạn lượt theo chính sách.
- `H`: tổng lượt đang giữ, kể cả các lượt có kết quả bên ngoài chưa xác định.
- `C`: tổng lượt đã tiêu dùng còn được tính vào hạn mức.
- `E`: tổng lượt tiêu dùng lũy kế đã ghi nhận trong lịch sử.

Bất biến của một phạm vi có giới hạn cứng:

~~~text
L >= 0
H >= 0
C >= 0
E >= 0
C <= E
H + C <= L
~~~

Muốn chấp nhận một yêu cầu mới cần `d` lượt:

~~~text
d > 0
H + C + d <= L
~~~

Việc kiểm tra và tăng H phải là một thao tác nguyên tử. Lượt đang giữ chiếm dung lượng thực, không phải chỉ là thông tin tham khảo.

E không giảm khi hoàn đơn. C có giảm hay không phụ thuộc chính sách phục hồi. Với chương trình không phục hồi lượt đã tiêu dùng, C thường bằng E.

Mỗi phạm vi chỉ cộng các đóng góp của chính nó. Một redemption được tính một lượt cho chương trình và một lượt cho khách không có nghĩa chương trình tiêu dùng hai lượt; đó là hai phép kiểm tra độc lập.

### 3.2. Các phép chuyển cơ bản

| Hành động | Thay đổi H | Thay đổi C | Thay đổi E |
| --- | ---: | ---: | ---: |
| Giữ d lượt mới | +d | 0 | 0 |
| Tiêu dùng d lượt đã giữ | -d | +d | +d |
| Giải phóng d lượt chưa tiêu dùng | -d | 0 | 0 |
| Phục hồi d lượt đã tiêu dùng, nếu chính sách cho phép | 0 | -d | 0 |

Một lần tiêu dùng chuyển lượng đã giữ sang lượng đã dùng, không chiếm thêm dung lượng lần hai. Không tăng C mà quên giảm H.

Hết hạn lượt giữ cũng không được giảm C vì lượt đó chưa từng trở thành lượt dùng cuối. Hoàn đơn sau tiêu dùng không được giảm H vì phần giữ đã được kết chuyển.

Các phép chuyển phải gắn với redemption cụ thể và chỉ có hiệu lực một lần. Không cho một endpoint tùy ý cộng hoặc trừ trực tiếp tổng số mà không có nguồn nghiệp vụ.

### 3.3. Một ví dụ nhỏ

Chương trình có L = 3:

~~~text
Ban đầu:                    H=0, C=0, E=0
A được giữ 1 lượt:          H=1, C=0, E=0
B được giữ 1 lượt:          H=2, C=0, E=0
A thanh toán thành công:    H=1, C=1, E=1
B thất bại xác định:        H=0, C=1, E=1
~~~

Nếu A hoàn đơn và chính sách không phục hồi lượt, các số vẫn là H=0, C=1, E=1. Nếu chính sách cho phục hồi một lần sau khi đủ điều kiện, kết quả có thể là H=0, C=0, E=1.

Hai chính sách cho số lượt khả dụng khác nhau. Không lấy E làm thống kê rồi vô tình dùng nó để thực thi một chính sách ròng, hoặc dùng C để tuyên bố rằng khách chưa từng hưởng ưu đãi.

## 4. Dữ liệu và khóa nghiệp vụ

### 4.1. Các bản ghi cần truy vết

| Bản ghi | Nội dung quan trọng |
| --- | --- |
| Coupon definition | Định danh mã chuẩn, chương trình, phạm vi, điều kiện, phiên bản chính sách |
| Issued entitlement | Quyền cá nhân, chủ sở hữu và nguồn phát hành, nếu coupon là quyền riêng |
| Redemption | Đơn, chủ thể, coupon, số lượt, trạng thái, mốc giữ và tiêu dùng |
| Redemption scope | Những phạm vi bị chiếm lượt, đơn vị đếm và lượng đóng góp vào từng phạm vi |
| Usage counter | H, C, E, giới hạn và phiên bản cập nhật cho một phạm vi |
| Usage ledger | Các hiệu ứng giữ, tiêu dùng, giải phóng, phục hồi liên kết tới redemption |
| Idempotency mapping | Phạm vi khóa, fingerprint và operation đã tạo |
| Outbox / inbox | Công việc đã commit và các sự kiện đã nhận cần xử lý lại an toàn |

Không nhất thiết phải tạo đúng số bảng như trên. Điều quan trọng là phân biệt được danh tính coupon, quyền được phát hành, một lần sử dụng và số tổng hợp.

Các phạm vi bị ảnh hưởng nên được chụp lại khi giữ lượt. Nếu cấu hình đổi sau đó, không suy ra lại các phạm vi từ chính sách hiện hành rồi giải phóng nhầm bộ đếm.

Ví dụ một redemption có thể ghi:

~~~text
redemption R1:
    tenant = T1
    coupon = A
    program = P
    subject = U1
    order = O1
    benefit_slot = G
    policy_revision = 7
    status = HELD

scope contributions:
    program P, metric ORDER_COUNT        : 1
    coupon A, metric ORDER_COUNT         : 1
    subject U1 in P, metric ORDER_COUNT  : 1
~~~

Thông tin revision giải thích quy tắc đã áp dụng, nhưng không nên tự trở thành cách mở một bộ đếm mới. Đổi tên chương trình hoặc publish revision 8 không mặc nhiên cấp lại lượt cho tất cả khách.

Nếu chính sách thật sự có đợt giới hạn mới, hãy dùng định danh đợt và mốc chuyển được công bố rõ. Không vô tình reset giới hạn chỉ vì sửa mô tả.

### 4.2. Các khóa cần tách biệt

**Khóa đối tượng:** `coupon_id`, `issued_entitlement_id`, `order_id`, `subject_id`.

**Khóa phạm vi đếm:** tenant, loại phạm vi, đối tượng của phạm vi và loại đơn vị đếm. Khóa này phải có tính duy nhất để hai request không tạo hai hàng bộ đếm cho cùng một khách trong một chương trình.

**Khóa idempotency:** tenant, chủ thể, loại thao tác và khóa request. Nó nhận diện việc gửi lại cùng một yêu cầu.

**Khóa ý định nghiệp vụ:** một đơn hoặc claim phía máy chủ cùng vị trí lợi ích được áp dụng. Nó ngăn tạo nhiều redemption cho cùng một ý định dù người gọi đổi khóa request.

Ví dụ hệ thống cho một lợi ích trong nhóm G trên mỗi đơn thì ràng buộc cần phản ánh `(tenant, order, benefit_slot_G)`, không chỉ `(order, coupon_id)`. Nếu chỉ chặn cùng mã trên cùng đơn, khách có thể đổi sang một mã khác thuộc cùng nhóm.

Không đưa một `orderVersion` có thể tăng sau mỗi lần sửa giỏ vào khóa chống dùng lặp rồi coi như đã bảo vệ “mỗi đơn một lần”. Phiên bản nội dung dùng để kiểm tra tính còn phù hợp của quyền; định danh ý định cần ổn định theo đúng chính sách.

Với hệ thống cho phép thử lại sau hủy hoặc hết hạn, phải có quy trình tạo lần thử mới có kiểm soát, kiểm tra lịch và hạn mức lại. Không hồi sinh redemption cũ hoặc để client tùy ý đổi một trường để tạo ý định mới.

### 4.3. Bộ đếm là dữ liệu tổng hợp, không phải toàn bộ lịch sử

Chỉ lưu `coupon.used_count = 123` không cho biết 123 lượt thuộc ai, đơn nào, lượt nào đang giữ hoặc vì sao số giảm.

Usage ledger giúp tái dựng số tổng hợp và giải thích chênh lệch. Mỗi hiệu ứng có định danh nguồn, loại hiệu ứng, phạm vi, lượng thay đổi và lý do.

Có thể đặt ràng buộc duy nhất trên hiệu ứng hợp lệ như `(redemption_id, scope_id, effect_kind)` khi mỗi loại chỉ được xuất hiện một lần. Nhưng ràng buộc đó không tự ngăn hai loại khác nhau, chẳng hạn EXPIRE và CANCEL, cùng trừ một phần giữ. Guard chuyển trạng thái vẫn phải bảo đảm chỉ một nhánh kết thúc có hiệu lực.

## 5. Máy trạng thái và thời điểm chiếm lượt

Một mô hình đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> HELD: Giữ lượt hợp lệ
    HELD --> PAYMENT_PENDING: Bắt đầu thanh toán
    HELD --> RELEASED: Hủy trước khi gửi thanh toán
    HELD --> EXPIRED: Hết hạn an toàn
    HELD --> REDEEMED: Đơn không cần thanh toán hoặc đã đủ điều kiện
    PAYMENT_PENDING --> REDEEMED: Xác nhận tiêu dùng
    PAYMENT_PENDING --> RELEASED: Xác nhận không còn hiệu ứng
    PAYMENT_PENDING --> RECONCILING: Chưa xác định kết quả
    RECONCILING --> REDEEMED: Đối soát thành công
    RECONCILING --> RELEASED: Đối soát thất bại dứt điểm
~~~

Đây là ví dụ cho mốc tiêu dùng gắn với chấp nhận đơn hoặc thanh toán. Một miền nghiệp vụ khác có thể cần trạng thái khác.

### 5.1. Trạng thái nào còn chiếm lượt?

Trong mô hình này:

| Trạng thái | Đóng góp vào H | Đóng góp vào C |
| --- | ---: | ---: |
| HELD | Có | Không |
| PAYMENT_PENDING | Có | Không |
| RECONCILING | Có | Không |
| REDEEMED | Không | Có, theo chính sách tính hạn mức |
| RELEASED | Không | Không |
| EXPIRED | Không | Không |

Phục hồi sau REDEEMED cần một hành động bù trừ riêng có điều kiện. Có thể theo dõi bằng bản ghi restoration hoặc trạng thái bổ sung, không xóa lịch sử redemption.

Phục hồi cũng có thể khác nhau theo phạm vi: chương trình cho trả lại sức chứa toàn cục sau hoàn đơn nhưng vẫn tính khách đó đã dùng ưu đãi chào mừng một lần trong đời. Khi ấy C của chương trình có thể giảm, trong khi C của phạm vi khách không giảm.

### 5.2. Hết TTL không luôn có nghĩa được trả lượt

Nếu chưa gửi thao tác thanh toán ra ngoài, worker có thể chuyển HELD sang EXPIRED và trừ H trong cùng transaction, sau khi kiểm tra quyền chưa được tiêu dùng.

Nếu đã gửi thanh toán và kết quả chưa rõ, timeout không chứng minh giao dịch thất bại. Giải phóng H lúc này có thể cấp lượt cho khách khác, rồi giao dịch cũ thành công muộn làm vượt giới hạn.

Cần giữ phần đang chiếm trong PAYMENT_PENDING hoặc RECONCILING cho tới khi có bằng chứng đủ chắc chắn. Nếu một công việc đã được đọc bởi worker, xóa message hoặc đặt cờ hủy cũng chưa chứng minh nó không thể thực hiện muộn; việc giải phóng phải phối hợp với vòng đời công việc đó.

### 5.3. Tiêu dùng và giải phóng phải loại trừ nhau

Giả sử callback thành công và worker hết hạn cùng xử lý R1. Cả hai không được cùng đọc HELD rồi:

~~~text
Worker A: H -= 1, C += 1, E += 1
Worker B: H -= 1
~~~

Kết quả có thể làm H âm hoặc trả lại sức chứa đã tiêu dùng. Cần khóa redemption hoặc chuyển trạng thái có điều kiện; bên thắng ghi cả trạng thái lẫn hiệu ứng bộ đếm trong cùng transaction. Bên còn lại đọc kết quả mới và không ghi hiệu ứng lần nữa.

Đừng chỉ chặn trùng bằng event ID. Callback và worker hết hạn vốn là hai sự kiện khác nhau nhưng cùng cạnh tranh một quyền.

## 6. Ngăn vượt giới hạn do yêu cầu đồng thời

### 6.1. Mẫu kiểm tra rồi ghi dễ lỗi

Chương trình có L=100, C=99 và H=0. Hai request khác nhau cùng thực hiện:

~~~text
A đọc 99, kết luận còn 1 lượt
B đọc 99, kết luận còn 1 lượt
A tạo redemption và tăng tổng lên 100
B tạo redemption và tăng tổng lên 101
~~~

Mỗi request đều có thể dùng idempotency key đúng và không bị phát lại. Lỗi ở đây là hai ý định hợp lệ riêng rẽ cùng chiếm một phần dung lượng.

Cũng có lỗi ở hạn mức theo khách: hai đơn khác nhau của cùng khách cùng đọc “chưa từng dùng”. Khóa riêng từng đơn không bảo vệ tài nguyên dùng chung là hạn mức của khách trong chương trình.

### 6.2. Kiểm tra và giữ nguyên tử

Một mẫu SQL minh họa cho một hàng bộ đếm đã tồn tại:

~~~sql
UPDATE coupon_usage_counter
SET held_count = held_count + :delta,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND scope_id = :scope_id
  AND :delta > 0
  AND :delta <= limit_count - counted_count - held_count;
~~~

Máy chủ tính delta từ dữ liệu nghiệp vụ. Thao tác chỉ được chấp nhận khi đúng một hàng được cập nhật. Nếu không đủ lượt thì không tăng H.

Ví dụ này giả định các số đếm không âm, giới hạn có giá trị phù hợp và kiểu số đủ chứa phép tính. Cần kiểm tra phạm vi số đầu vào, không dùng số âm, giá trị thập phân hoặc số quá lớn để tạo thêm dung lượng hoặc gây tràn số.

Có thể dùng khóa hàng rồi kiểm tra và cập nhật thay câu lệnh có điều kiện. Điều bắt buộc là phép kiểm tra dung lượng và ghi phần giữ được bảo vệ chung.

### 6.3. Nhiều phạm vi phải cùng thành công hoặc cùng thất bại

Một redemption có thể giữ lượt cho chương trình, mã và khách. Nếu giữ được chương trình nhưng thất bại ở hạn mức khách, phải rollback cả phần đã giữ của chương trình.

~~~text
begin transaction
    giữ 1 lượt ở chương trình
    giữ 1 lượt ở mã coupon
    giữ 1 lượt ở phạm vi khách
    tạo redemption và các đóng góp
commit
~~~

Nếu bất kỳ bước nào thất bại thì không commit các bước còn lại. Không để lại phần giữ mồ côi do cập nhật lần lượt ở các transaction độc lập.

Khi cần khóa nhiều hàng, dùng thứ tự ổn định theo khóa phạm vi. Việc tạo hàng bộ đếm đầu tiên cho một khách cũng cần khóa duy nhất và xử lý cạnh tranh. Không dùng mẫu “không thấy hàng thì tự insert” mà thiếu ràng buộc, vì hai hàng cùng đại diện một khách có thể chia nhỏ hạn mức ngoài ý muốn.

Nếu insert hàng mới bị xung đột, đọc hoặc thử lại theo cơ chế của cơ sở dữ liệu. Không coi lỗi tạo hàng là bằng chứng khách có một hạn mức mới.

## 7. Luồng giữ và tiêu dùng lượt

### 7.1. Tạo redemption có giữ lượt

Đoạn giả mã sau minh họa ranh giới transaction. Tên hàm thể hiện trách nhiệm cần triển khai, không phải API của một thư viện.

~~~text
reserveCoupon(actor, orderId, couponText, command, idempotencyKey):
    validateAllowedRequestFields(command)

    begin transaction
        order = lockOrder(orderId)
        authorizeOrderAccess(actor, order)

        coupon = resolveCanonicalCoupon(order.tenantId, couponText)
        requireCouponInAllowedScope(coupon, order)
        subject = resolveTrustedSubject(actor, order)

        fingerprint = canonicalFingerprint(orderId, coupon.id, command)
        previous = findIdempotency(
            tenant = order.tenantId,
            subject = subject.id,
            action = "RESERVE_COUPON",
            key = idempotencyKey
        )

        if previous exists:
            requireSameFingerprint(previous, fingerprint)
            authorizeReadOfOperation(actor, previous)
            commit
            return currentResult(previous)

        existing = findClaimForSameOrderBenefitSlot(order, coupon)
        if existing exists:
            authorizeReadOfOperation(actor, existing)
            saveIdempotencyMapping(idempotencyKey, fingerprint, existing)
            commit
            return currentResult(existing)

        policy = lockApplicableCouponPolicy(coupon)
        requireExpectedOrderVersion(command, order)
        requireEntitlementOwnerIfPersonalCoupon(coupon, subject)

        scopes = deriveStableCounterScopes(policy, subject, order)
        counters = createOrLockCountersInStableOrder(scopes)

        t = authoritativeNow()
        requireCouponStateAndScheduleAllowNewUse(coupon, policy, t)
        requireProductsAndAudienceEligible(order, subject, policy)

        deltas = calculateUsageDeltasOnServer(order, policy, scopes)
        requireAllDeltasValidAndWithinLimits(counters, deltas)

        redemption = insertRedemption(
            subject = subject,
            order = order,
            coupon = coupon,
            policySnapshot = policy,
            scopeContributions = deltas,
            acceptedAt = t,
            expiresAt = calculateBoundedHoldExpiry(t, policy),
            status = HELD
        )

        incrementHeldCounts(counters, deltas)
        appendUsageLedger("HOLD", redemption, deltas)
        saveIdempotencyMapping(idempotencyKey, fingerprint, redemption)
        insertOutbox("COUPON_HELD", redemption.id)
        appendAudit("COUPON_HOLD_ACCEPTED", actor, redemption)

    commit

    return redemption
~~~

Những yêu cầu quan trọng:

- Chính sách và giới hạn không được thay đổi dưới chân transaction mà không bị phát hiện.
- Mỗi phạm vi có lượng đóng góp do máy chủ tính; không giả định mọi phạm vi dùng chung một đơn vị.
- Ràng buộc khóa nghiệp vụ và idempotency phải được thực thi ở tầng lưu trữ, không chỉ bằng một lần đọc trước.
- Nếu hai request cùng khóa hoặc cùng claim cạnh tranh, request thua không được để lại phần giữ khi transaction rollback.
- Kết quả trả lại cho một yêu cầu cũ là trạng thái của operation đó; đọc lại kết quả không đồng nghĩa gia hạn hoặc cấp lại quyền.
- Không gọi cổng thanh toán trong lúc giữ khóa cơ sở dữ liệu. Ghi ý định hoặc outbox trước, rồi xử lý bên ngoài với định danh ổn định.

### 7.2. Chuyển từ giữ sang tiêu dùng

Khi có đủ bằng chứng theo chính sách:

~~~text
begin transaction
    khóa redemption và các bộ đếm nguồn theo kỷ luật khóa thống nhất
    xác minh sự kiện, đối tượng và giao dịch liên quan

    nếu redemption đã REDEEMED:
        trả kết quả hiện có; không đổi bộ đếm

    nếu trạng thái cho phép tiêu dùng và các điều kiện còn phù hợp:
        với mỗi đóng góp d đã lưu:
            H -= d
            C += d
            E += d
        ghi trạng thái REDEEMED
        ghi ledger và audit
commit
~~~

Lượng chuyển lấy từ đóng góp đã lưu, không tính lại bằng giỏ hàng hiện tại. Nếu đơn bị sửa sau khi giữ coupon, cần kiểm tra phiên bản và xử lý thay đổi bằng quy trình được cho phép.

Không chỉ tăng một `used_count` sau callback rồi để phần giữ tồn tại. Cũng không cho phép callback tạo redemption mới từ một order ID bất kỳ nếu chưa có quyền hợp lệ.

Nếu callback đến sau hạn, áp dụng chính sách đã định nghĩa cho thanh toán muộn hoặc đang đối soát. Sự kiện có xác thực vẫn cần được đối chiếu đúng giao dịch, số tiền, đơn và redemption; chữ ký hợp lệ không tự chứng minh sự kiện thuộc đối tượng đang xử lý.

### 7.3. Hủy hoặc hết hạn trước tiêu dùng

Một chuyển từ HELD sang RELEASED hoặc EXPIRED trừ H đúng lượng đã giữ và ghi lý do. Không thay đổi C hoặc E.

Thao tác phải kiểm tra trạng thái hiện hành và vòng đời công việc bên ngoài. Hai lý do giải phóng khác nhau vẫn chỉ được trừ phần giữ một lần.

Nếu sử dụng một quyền cá nhân, giải phóng lượt cũng không tự đổi chủ sở hữu hoặc làm quyền hết hạn trở thành còn hạn. Sức chứa, quyền sở hữu và điều kiện thời gian là các ràng buộc riêng.

## 8. Idempotency không thay thế giới hạn nghiệp vụ

### 8.1. Hai tầng chống lặp

| Tầng | Ngăn điều gì? | Ví dụ |
| --- | --- | --- |
| Request idempotency | Một yêu cầu được gửi lại tạo nhiều operation | Khách bấm hai lần cùng khóa |
| Business uniqueness và hạn mức | Các request khác nhau tạo lợi ích trùng hoặc vượt quyền | Đổi khóa, đổi thiết bị, dùng API quản trị |

Một khách có thể tạo hai idempotency key khác nhau. Nếu giới hạn là mỗi khách một lượt, bộ đếm theo chủ thể vẫn phải chặn lần thứ hai.

Một sự kiện có thể được nhà cung cấp phát lại với ID khác. Nếu cùng thể hiện một giao dịch đã tiêu dùng, guard của redemption vẫn phải ngăn tăng E lần nữa.

### 8.2. Quy ước xử lý request thử lại

| Yêu cầu sau | Kết quả |
| --- | --- |
| Cùng khóa, cùng nội dung chuẩn hóa | Cùng operation, trạng thái hiện tại |
| Cùng khóa, nội dung khác | Xung đột; không đổi quyền đã có |
| Khóa mới, cùng ý định nghiệp vụ | Trả operation đã gắn hoặc từ chối theo hợp đồng; không cấp thêm |
| Khóa mới, đơn khác của cùng khách đã hết lượt | Từ chối theo hạn mức khách |
| Khóa đoán được nhưng người gọi không có quyền | Không được đọc hoặc thao tác trên operation |
| Gọi lại sau thời gian lưu khóa request | Khóa nghiệp vụ và hạn mức vẫn ngăn hiệu ứng sai |

Fingerprint cần dựa trên các trường nghiệp vụ được chuẩn hóa. Việc đổi thứ tự thuộc tính JSON không nên tạo ra ý nghĩa mới; việc đổi đơn, nội dung hoặc coupon thực sự thì phải được phát hiện.

Không tự đặt lại hạn giữ bằng `now + TTL` mỗi lần retry. Một quyền giữ có thể bị chiếm vô thời hạn nếu mỗi lần đọc hoặc thử lại đều gia hạn.

### 8.3. Không đếm theo số message đã nhận

Các lựa chọn sau dễ sai:

~~~text
Mỗi callback thanh toán → used_count += 1
Mỗi lần đọc message ORDER_PAID → used_count += 1
Mỗi lần chạy lại job đối soát → used_count += 1
~~~

Cần đếm theo một chuyển trạng thái nghiệp vụ có định danh. Inbox chống trùng message hỗ trợ xử lý, nhưng không thay thế liên kết giữa giao dịch thanh toán và redemption.

Nếu phía thanh toán thử lại một lệnh do mất phản hồi, dùng định danh nghiệp vụ ổn định và cơ chế chống trùng của bên nhận. Bộ đếm coupon phải gắn với cùng redemption, không tạo thêm lượt chỉ vì có thêm một lần thử thanh toán.

## 9. Hủy, hoàn đơn và phục hồi số lượt

### 9.1. Đừng mặc định “hoàn tiền thì giảm used_count”

Các chính sách có thể khác nhau:

| Chính sách | Sau khi hoàn đủ điều kiện |
| --- | --- |
| Một lần trong đời của chủ thể | Vẫn tính đã dùng trong hạn mức chủ thể |
| Một lần cho giao dịch hoàn tất còn hiệu lực | Có thể phục hồi theo điều kiện đã công bố |
| Phục hồi sức chứa chương trình nhưng không phục hồi quyền chào mừng | Chỉ giảm C ở các phạm vi được cho phép |
| Chỉ phục hồi khi toàn bộ đơn được hủy | Hoàn một phần chưa đủ điều kiện trả một lượt |

Đặt lại mọi bộ đếm về 0 sau refund có thể mở quyền cho sai chủ thể hoặc giải phóng quá nhiều dung lượng. Phải bù trừ đúng lượng, đúng phạm vi và đúng redemption gốc.

### 9.2. Giới hạn phục hồi theo nguồn

Một restoration cần chỉ rõ:

~~~text
source_redemption_id
source_scope_id
quantity_restored
policy_snapshot / restoration_reason
qualifying_business_event
unique_restoration_key
~~~

Tổng phục hồi của một đóng góp không được vượt lượng đã tiêu dùng được phép phục hồi. Nhiều callback hoàn tiền hoặc nhiều nhân viên xử lý không được tạo thêm quyền từ cùng một nguồn.

Nếu đơn tiêu dùng một lượt tính theo đơn, trả một trong ba món không mặc nhiên tương đương phục hồi 1/3 lượt. Với đơn vị đếm là sản phẩm, phục hồi bao nhiêu phải theo các đơn vị đủ điều kiện và chưa được phục hồi trước đó.

E vẫn giữ lịch sử đã dùng. Khách có thể được cấp một quyền mới hợp lệ theo chính sách, nhưng không được biến giao dịch cũ thành “chưa từng xảy ra”.

### 9.3. Ngăn vòng lặp giữ, dùng và hủy

Một chương trình chào mừng có thể bị lạm dụng nếu mỗi lần hủy lại mở quyền dùng không giới hạn. Cần xác định doanh nghiệp giới hạn điều gì: số giao dịch đang hiệu lực, tổng số lần đã hưởng hay số chu kỳ cấp lại.

Giới hạn tốc độ chỉ làm chậm vòng lặp. Muốn ngăn hành vi vượt chính sách phải có quy tắc phục hồi, định danh nguồn và kiểm tra các lợi ích phụ có thể còn lại sau hủy, chẳng hạn quà tặng hoặc điểm thưởng.

Các yêu cầu giữ chỗ cũng có thể làm cạn lượt tạm thời. Có thể giới hạn số quyền giữ đang hoạt động của một chủ thể, ràng buộc với đơn hợp lệ và đặt thời hạn phù hợp. Không chữa tình trạng cạn lượt bằng cách giải phóng sớm các thanh toán còn có khả năng thành công.

## 10. Nguồn có thẩm quyền, cache và thay đổi hạn mức

### 10.1. Chọn nơi quyết định cấp lượt

Nếu mỗi dịch vụ giữ một bản đếm riêng rồi đồng bộ sau, hai nơi có thể cùng cấp lượt cuối. Với giới hạn cứng dùng chung, phải có một cơ chế phân xử chung đủ mạnh cho các phạm vi liên quan.

Một phương án là dịch vụ coupon quản lý việc giữ, tiêu dùng và giải phóng, trả về một quyền có định danh cho checkout. Các kênh bán và công cụ quản trị đều phải đi qua cùng quy tắc.

Cache có thể hiển thị “còn lượt” hoặc giảm tải tra cứu, nhưng quyết định giữ quyền cần xác nhận tại nguồn có thẩm quyền. Một số thống kê cập nhật chậm không được dùng thay hạn mức chính xác.

Khóa phân tán không tự giải quyết mọi vấn đề: cần biết điều gì xảy ra khi hết thời gian giữ khóa, chuyển máy chủ hoặc tiến trình cũ tiếp tục ghi. Cơ chế được chọn phải bảo vệ cả trạng thái redemption lẫn các hiệu ứng bộ đếm, không chỉ một đoạn mã trong một tiến trình.

### 10.2. Nhiều vùng hoặc nhiều kho dữ liệu

Nếu cần cấp lượt ở nhiều vùng, có thể dùng một nơi phân xử chung hoặc chia hạn ngạch theo vùng. Với cách chia hạn ngạch, tổng phần được cấp không vượt giới hạn chung; việc chuyển hoặc thu hồi phần được cấp cũng phải chống trùng và không tạo hai bản quyền sử dụng cùng một phần.

Đọc số dùng theo mô hình nhất quán cuối cùng rồi tăng tại mỗi vùng không đủ để cam kết không vượt giới hạn toàn cục.

Nếu các phạm vi nằm ở các dịch vụ khác nhau, không được tuyên bố một transaction cục bộ đã làm tất cả nguyên tử. Cần thiết kế giao thức giữ từng phần, điều kiện chấp nhận cuối và bù trừ khi thất bại, hoặc đưa phần phân xử vào một nơi có thể bảo vệ chung. Trong bài này, các ví dụ transaction giả định những bộ đếm cần cập nhật có thể được bảo vệ trong cùng ranh giới nhất quán.

### 10.3. Quản trị số lượt cũng là thao tác bảo mật

Việc tăng hạn mức, reset bộ đếm hoặc phục hồi lượt có thể cấp thêm lợi ích, nên phải kiểm tra quyền và ghi audit.

Một số quy tắc hữu ích:

- Không cho nhân viên tenant A sửa giới hạn hoặc số dùng của tenant B.
- Không cho API đổi metadata coupon ngầm đặt H, C hoặc E về 0.
- Sửa chính sách không tạo bộ đếm khách mới nếu phạm vi hạn mức không đổi.
- Mặc định từ chối giảm L xuống dưới H+C; nếu nghiệp vụ cần trường hợp khác, phải mô hình hóa rõ quyền đã cấp và cơ chế dừng lượt mới.
- Đổi hạn mức và cấp lượt mới phải phối hợp bằng khóa hoặc kiểm tra phiên bản để không dựa trên cấu hình lỗi thời.
- Sửa tay dữ liệu để chữa lệch phải có nguồn nghiệp vụ hoặc quy trình điều chỉnh, không ghi đè một tổng số trong khi các transaction vẫn cập nhật.

## 11. Kiểm thử tình huống tấn công logic

### 11.1. Ma trận tình huống

| Tình huống | Kết quả cần quan sát |
| --- | --- |
| Gọi kiểm tra mã nhiều lần | Không tăng H, C hoặc E chỉ vì validation |
| Một đơn có ba sản phẩm, chính sách đếm theo đơn | Tiêu dùng một lượt, không phải ba |
| Chính sách đếm theo đơn vị sản phẩm | Lượng giữ do máy chủ tính từ các đơn vị đủ điều kiện |
| Client gửi usageCount bằng 0, âm hoặc quá lớn | Không thao túng được bộ đếm; trường ngoài hợp đồng bị từ chối hoặc không có thẩm quyền |
| Giới hạn L=0 | Không cấp lượt; không coi 0 là không giới hạn ngoài chính sách |
| Mã còn lượt nhưng chương trình hết lượt | Từ chối; không để phần giữ ở phạm vi khác |
| Khách đã dùng mã A, chuyển sang B trong cùng chương trình | Bị chặn nếu giới hạn khách tính theo chương trình |
| Các cách viết mã được cấu hình tương đương | Cùng coupon chuẩn và bộ đếm |
| Sửa customerId trong body | Không đổi chủ thể được tính lượt |
| Đổi email của tài khoản | Không reset giới hạn gắn với chủ thể ổn định |
| Dùng quyền cá nhân của người khác | Bị từ chối trước khi cấp hoặc tiêu dùng lượt |
| Hai khách tranh lượt cuối toàn cục | Chỉ một lượng trong hạn mức được giữ |
| Một khách dùng hai đơn đồng thời | Hạn mức theo khách vẫn được bảo vệ |
| Hai request cùng tạo hàng đếm đầu tiên | Chỉ một hàng đại diện đúng phạm vi |
| Hai request cùng khóa idempotency | Một operation và một tập hiệu ứng |
| Cùng khóa nhưng đổi nội dung | Xung đột, không chuyển quyền sang đơn khác |
| Khóa mới nhưng cùng vị trí lợi ích trên đơn | Không tạo thêm redemption |
| Hai mã trong cùng nhóm không cộng dồn | Không tạo hai lợi ích cho cùng vị trí được giới hạn |
| Callback giống nhau hoặc khác ID nhưng cùng redemption | Chỉ một lần chuyển H sang C và tăng E |
| Worker tiêu dùng và worker hết hạn chạy đồng thời | Một nhánh hợp lệ, không giảm H hai lần |
| Thanh toán timeout nhưng sau đó thành công | Lượt vẫn được giữ khi chưa rõ; không cấp vượt do giải phóng sớm |
| Hủy trước tiêu dùng được gửi lại nhiều lần | H chỉ giảm đúng một lần, C và E không đổi |
| Hoàn một phần với chính sách tính theo đơn | Không tự phục hồi phần lẻ của một lượt |
| Hoàn toàn bộ, chính sách không phục hồi | C và E vẫn phản ánh lượt đã dùng |
| Phục hồi theo chính sách được phát lại | Mỗi phạm vi chỉ được bù trừ tối đa phần cho phép |
| Retry sau khi idempotency cache hết hạn | Khóa nghiệp vụ và bộ đếm vẫn bảo vệ giới hạn |
| Cache thống kê còn báo số cũ | Đường giữ quyền vẫn dùng dữ liệu có thẩm quyền |
| Sửa phiên bản hoặc tên chương trình | Không mở bộ đếm mới ngoài chính sách |
| Giảm giới hạn khi đang có lượt giữ | Không phá quyền và bất biến bằng cập nhật thiếu kiểm tra |
| Đơn miễn phí không có callback thanh toán | Tiêu dùng đúng một lần tại mốc nghiệp vụ được chọn |
| API quản trị cố bỏ qua bước giữ hoặc quyền đối tượng | Không được tạo redemption ngoài quy tắc |

### 11.2. Kiểm thử đồng thời có kiểm soát

Đặt trạng thái ban đầu L=100, C=99, H=0. Cho hai tiến trình khác nhau tranh cùng lượt còn lại, mỗi tiến trình có idempotency key riêng.

Điều phối để chúng thật sự cạnh tranh ở nơi kiểm tra và giữ lượt. Sau khi cả hai kết thúc, xác nhận:

~~~text
H + C <= 100
Chỉ một redemption mới chiếm lượt thành công
Không có phần giữ mồ côi ở bộ đếm mã hoặc khách
Không có hai hiệu ứng HOLD cho cùng claim
~~~

Tiếp theo chạy trường hợp chương trình còn nhiều lượt nhưng cùng khách chỉ được một lượt, với hai đơn khác nhau. Bài kiểm thử này phát hiện việc chỉ khóa đơn mà quên khóa phạm vi khách.

Không chỉ dựa vào một khoảng ngủ ngẫu nhiên hoặc chạy tuần tự hai lời gọi rồi kết luận đã chống race. Cần tạo ra cạnh tranh thực và kiểm tra dữ liệu sau cùng.

### 11.3. Kiểm thử theo chuỗi trạng thái

Một chuỗi có giá trị:

~~~text
giữ lượt → bắt đầu thanh toán → mất phản hồi
→ retry → nhận callback thành công → nhận callback trùng
→ hoàn một phần → hoàn phần còn lại → retry phục hồi
~~~

Sau mỗi bước, kiểm tra số đếm, trạng thái, lượng đóng góp và khóa nguồn. Một assertion chỉ nhìn số dùng cuối có thể bỏ sót giai đoạn hệ thống từng trả lượt sớm để người khác lấy.

## 12. Ví dụ kết hợp nhiều phạm vi

Giả sử:

~~~text
Chương trình P: tối đa 2 lượt
Hai mã A và B cùng thuộc P, còn đủ hạn mức riêng
Mỗi khách trong P: tối đa 1 lượt
Mỗi đơn: một vị trí lợi ích
Mỗi đơn đủ điều kiện: 1 lượt
Không phục hồi lượt đã tiêu dùng sau hoàn đơn
~~~

| Bước | Hành động | H toàn chương trình | C toàn chương trình | E toàn chương trình |
| --- | --- | ---: | ---: | ---: |
| 1 | U1 giữ A cho O1 | 1 | 0 | 0 |
| 2 | U1 thử giữ B cho O2, bị chặn theo khách | 1 | 0 | 0 |
| 3 | U2 giữ B cho O3 | 2 | 0 | 0 |
| 4 | U3 thử giữ A, bị chặn theo chương trình | 2 | 0 | 0 |
| 5 | O1 tiêu dùng thành công | 1 | 1 | 1 |
| 6 | Callback O1 được gửi lại | 1 | 1 | 1 |
| 7 | O3 thất bại xác định, giải phóng | 0 | 1 | 1 |
| 8 | U3 gửi yêu cầu hợp lệ mới và được giữ lượt | 1 | 1 | 1 |
| 9 | O1 được hoàn theo chính sách không phục hồi | 1 | 1 | 1 |

Ở bước 2, kể cả hệ thống đã tạm cập nhật một hàng bộ đếm trước khi phát hiện hết lượt khách, toàn transaction phải rollback. Bảng thể hiện trạng thái đã commit, không có phần giữ thừa.

U1 không dùng B sau bước 9 để nhận lượt mới. Việc mã B còn khả dụng không xóa lần dùng của U1 trong chương trình P.

Nếu thay chính sách phục hồi, kết quả cần thay đổi theo từng phạm vi được cho phép. Không sửa bảng ví dụ bằng cách giảm mọi số về 0, vì E là lịch sử lũy kế và quyền khách có thể chịu quy tắc khác sức chứa chương trình.

## 13. Đối soát và điều tra số đếm

Một ledger đầy đủ cho từng phạm vi có thể hỗ trợ tái dựng:

~~~text
H = tổng HOLD - tổng CONSUME - tổng RELEASE
C = tổng CONSUME - tổng RESTORE được phép của phạm vi
E = tổng CONSUME
~~~

Trong mô hình này, hủy và hết hạn đều tạo một hiệu ứng RELEASE đúng một lần. Nếu dùng tên hiệu ứng khác, công thức phải phản ánh cùng ý nghĩa và không trừ hai lần.

Đối soát phải đọc dữ liệu ở một mốc nhất quán. So một bộ đếm vừa thay đổi với ledger đọc trước đó có thể tạo cảnh báo giả. Cần truy vết được từ chênh lệch về redemption và transaction nguồn.

Các dấu hiệu đáng điều tra:

- H âm hoặc tồn tại lâu hơn vòng đời được phép.
- C vượt E hoặc tổng phục hồi vượt phần tiêu dùng gốc.
- H+C vượt giới hạn không có một thay đổi nghiệp vụ được mô hình hóa.
- Hai quyền hoạt động cho cùng ý định hoặc quyền cá nhân.
- Operation đã kết thúc nhưng vẫn còn phần giữ không có lý do.
- Callback có hiệu ứng nhưng không có nguồn redemption phù hợp.
- Một lần sửa chính sách làm số khách đủ điều kiện tăng bất thường.

Khi sửa lệch, xác minh trạng thái nghiệp vụ và hệ thống thanh toán trước, rồi điều chỉnh có khóa hoặc kiểm tra phiên bản, định danh và audit. Không lấy tổng trong báo cáo cập nhật chậm ghi đè lên bộ đếm đang dùng để cấp quyền.

## 14. Câu hỏi tự đánh giá

1. Một lượt được đo theo đơn, sản phẩm hay đơn vị nào, và được tiêu dùng tại mốc nào?
2. Những phạm vi nào cùng giới hạn một redemption?
3. Chủ thể đếm lấy từ đâu, có ổn định khi đổi hồ sơ hoặc nhập mã khác không?
4. Lượt đang giữ và kết quả thanh toán chưa rõ có chiếm hạn mức không?
5. Kiểm tra và giữ ở mọi phạm vi có cùng thành công hoặc cùng rollback không?
6. Đổi idempotency key có vượt được khóa nghiệp vụ hoặc hạn mức khách không?
7. Callback trùng và cạnh tranh tiêu dùng với hết hạn có tạo thêm hoặc trả thừa lượt không?
8. Hoàn đơn phục hồi những phạm vi nào, vào lúc nào và tối đa bao nhiêu?
9. Thay đổi policy hoặc hạn mức có vô tình reset lịch sử không?
10. Có thể giải thích và tái dựng H, C, E của một phạm vi từ các bản ghi nguồn không?
