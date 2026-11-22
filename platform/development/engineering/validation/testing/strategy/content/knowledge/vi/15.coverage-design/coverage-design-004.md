# Thiết kế bao phủ: Chọn bảng quyết định hoặc mô hình trạng thái cho quy tắc nghiệp vụ

## 1. Vì sao cần chọn đúng cách mô hình hóa quy tắc?

Quy tắc nghiệp vụ thường không chỉ là một điều kiện đơn lẻ. Kết quả có thể phụ thuộc vào nhiều yếu tố như vai trò người dùng, loại giao dịch, thời điểm, số dư, trạng thái hiện tại, quyền hạn và lịch sử xử lý. Nếu chỉ viết một vài ca kiểm thử theo ví dụ thuận tiện, nhóm dễ bỏ sót tổ hợp điều kiện hoặc chuyển trạng thái bất hợp lệ.

Hai kỹ thuật hữu ích để làm rõ và thiết kế độ bao phủ là **bảng quyết định (decision table)** và **mô hình trạng thái (state model/state machine)**:

- Bảng quyết định mô tả cách kết hợp các điều kiện đầu vào để chọn hành động hoặc kết quả nghiệp vụ.
- Mô hình trạng thái mô tả vòng đời của một đối tượng, những sự kiện có thể làm thay đổi trạng thái và điều kiện để chuyển tiếp.

Trong **VALIDATION_TESTING_STRATEGY**, lựa chọn đúng kỹ thuật giúp nhóm chuyển quy tắc thành tập kiểm thử có cấu trúc, phát hiện trường hợp thiếu hoặc mâu thuẫn và giải thích rõ phần hành vi đã được bao phủ.

Không nên chọn kỹ thuật theo thói quen hoặc theo công cụ đang có. Hãy xem điều gì quyết định kết quả của quy tắc:

- Nếu câu hỏi chính là “với tổ hợp điều kiện này, hệ thống phải làm gì?”, bảng quyết định thường phù hợp.
- Nếu câu hỏi chính là “đối tượng đang ở trạng thái nào và sự kiện nào được phép đưa nó sang trạng thái khác?”, mô hình trạng thái thường phù hợp.
- Nếu nghiệp vụ vừa có nhiều điều kiện quyết định vừa có vòng đời nhiều bước, có thể dùng cả hai và liên kết chúng.

## 2. Bảng quyết định là gì?

Bảng quyết định trình bày các điều kiện, tổ hợp giá trị điều kiện và hành động tương ứng. Mỗi cột quy tắc (rule) biểu diễn một trường hợp hoặc một nhóm trường hợp mà kết quả phải nhất quán.

Một bảng cơ bản gồm:

| Phần | Nội dung |
| --- | --- |
| Điều kiện (conditions) | Các yếu tố ảnh hưởng đến quyết định, ví dụ vai trò, thời hạn, số dư hoặc trạng thái |
| Giá trị điều kiện | Giá trị hoặc miền giá trị có thể nhận, ví dụ Có/Không, Đúng/Sai, trong hạn/quá hạn |
| Quy tắc (rules) | Mỗi cột hoặc hàng xác định một tổ hợp điều kiện cần xử lý |
| Hành động (actions) | Kết quả nghiệp vụ phải thực hiện hoặc từ chối |
| Ghi chú/ưu tiên | Giải thích quy tắc, thứ tự ưu tiên hoặc nguồn yêu cầu khi cần |

Trong cách trình bày phổ biến, điều kiện và hành động nằm ở các hàng, còn mỗi cột là một quy tắc. Một số nhóm dùng bảng theo hàng, mỗi hàng là một quy tắc; cả hai cách đều được nếu cấu trúc nhất quán và dễ truy vết.

### 2.1. Khi nào nên dùng bảng quyết định?

Bảng quyết định phù hợp khi:

- Kết quả phụ thuộc vào nhiều điều kiện kết hợp.
- Có quy tắc tính phí, chiết khấu, hạn mức, quyền, phân loại hoặc phê duyệt.
- Nhiều điều kiện có thể dẫn đến cùng một hành động.
- Cần phát hiện tổ hợp chưa được định nghĩa hoặc quy tắc mâu thuẫn.
- Người dùng nghiệp vụ cần rà soát logic theo cách trực quan.
- Nhóm cần tạo tập kiểm thử bao phủ các quy tắc đã xác định.

Ví dụ: mức phí hủy lịch phụ thuộc vào thời gian còn lại trước giờ hẹn, trạng thái thanh toán và trạng thái của lịch. Đây là quyết định dựa trên tổ hợp điều kiện; bảng quyết định giúp nhìn rõ trường hợp nào được hủy, trường hợp nào được hoàn tiền và trường hợp nào phải từ chối.

### 2.2. Xác định điều kiện đúng mức

Điều kiện cần độc lập về ý nghĩa và đủ rõ để phân biệt kết quả. Tránh đưa nhiều khái niệm vào một điều kiện mơ hồ như “khách hàng hợp lệ”. Hãy tách thành các yếu tố có thể xác định:

- Tài khoản đang hoạt động?
- Người dùng có quyền thực hiện hành động?
- Giao dịch có thuộc phạm vi khách hàng?
- Dữ liệu bắt buộc đã đầy đủ?

Không phải mọi tổ hợp toán học đều hợp lệ trong nghiệp vụ. Ví dụ, một lịch đã hủy không thể đồng thời ở trạng thái đang chờ xác nhận. Hãy xác định tổ hợp không thể xảy ra và ghi rõ lý do, thay vì âm thầm bỏ qua.

### 2.3. Dùng giá trị “không quan trọng” có kiểm soát

Ký hiệu “–” hoặc “không quan trọng” (don't care) có thể dùng khi giá trị của một điều kiện không ảnh hưởng đến hành động trong quy tắc đó.

Ví dụ, nếu lịch đã hủy thì hệ thống không xử lý yêu cầu hủy lần nữa; trạng thái thanh toán và thời gian còn lại không thay đổi kết quả. Khi đó, hai điều kiện này có thể được đánh dấu “–” trong quy tắc lịch đã không còn hoạt động.

Chỉ dùng don't care khi có căn cứ nghiệp vụ. Không dùng nó để bỏ qua một điều kiện chưa được làm rõ.

## 3. Quy trình xây dựng bảng quyết định

### 3.1. Bước 1 — Xác định quyết định cần kiểm thử

Viết rõ câu hỏi mà hệ thống phải trả lời. Ví dụ:

> Khi người dùng yêu cầu hủy lịch, hệ thống có cho phép hủy và cần thực hiện hành động hoàn tiền nào?

Phạm vi của bảng nên tập trung vào một quyết định cụ thể. Nếu bảng cố mô tả toàn bộ quy trình đặt lịch, thanh toán, thông báo và đối soát cùng lúc, số điều kiện sẽ tăng nhanh và khó đọc.

### 3.2. Bước 2 — Liệt kê điều kiện và miền giá trị

Với quyết định hủy lịch, các điều kiện có thể là:

- Lịch còn hoạt động hay đã kết thúc/hủy.
- Thời điểm yêu cầu có nằm trong cửa sổ được phép hủy không.
- Thanh toán đã được ghi nhận hay chưa.

Điều kiện phải dựa trên quy tắc đã được chủ sở hữu nghiệp vụ xác nhận. Nếu chính sách hủy khác nhau theo loại dịch vụ, nhóm khách hàng hoặc kênh đặt, cần đưa yếu tố đó vào bảng hoặc tách bảng theo phạm vi.

### 3.3. Bước 3 — Liệt kê quy tắc và hành động

Ví dụ dưới đây dùng chính sách minh họa:

- Chỉ lịch còn hoạt động mới có thể được hủy.
- Lịch được hủy nếu yêu cầu đến trước hoặc đúng thời điểm chốt hủy.
- Nếu đã thanh toán, hệ thống khởi tạo hoàn tiền đầy đủ.
- Nếu chưa thanh toán, hệ thống hủy lịch mà không tạo hoàn tiền.
- Nếu quá thời điểm chốt hủy, yêu cầu bị từ chối.
- Yêu cầu lặp trên lịch đã hủy không tạo tác dụng phụ lần thứ hai.

| Điều kiện / Quy tắc | R1 | R2 | R3 | R4 | R5 |
| --- |:---:|:---:|:---:|:---:|:---:|
| Lịch còn hoạt động? | Không | Có | Có | Có | Có |
| Còn trong thời hạn được hủy? | – | Có | Có | Không | Không |
| Đã thanh toán? | – | Có | Không | Có | Không |
| **Hành động** | | | | | |
| Chấp nhận yêu cầu hủy | Không | Có | Có | Không | Không |
| Chuyển lịch sang đã hủy | Không đổi | Có | Có | Không đổi | Không đổi |
| Khởi tạo hoàn tiền | Không | Có | Không | Không | Không |
| Giữ nguyên trạng thái hiện tại | Có | Không | Không | Có | Có |

R1 thể hiện lịch không còn hoạt động; các điều kiện còn lại không ảnh hưởng đến kết quả. R2 và R3 phân biệt hành động hoàn tiền. R4 và R5 thể hiện yêu cầu quá thời hạn bị từ chối, dù trạng thái thanh toán khác nhau.

Đây là ví dụ minh họa, không phải chính sách hủy mặc định. Trong sản phẩm thực tế, cần xác định thời điểm chốt, múi giờ, mức hoàn tiền, phí hủy, trạng thái đang xử lý và các ngoại lệ với chủ sở hữu nghiệp vụ.

### 3.4. Bước 4 — Kiểm tra tính đầy đủ và nhất quán

Sau khi lập bảng, kiểm tra:

- Các điều kiện quan trọng đã được đưa vào chưa?
- Miền giá trị có bao phủ các trường hợp hợp lệ và biên không?
- Mỗi tổ hợp hợp lệ có quy tắc xử lý không?
- Có hai quy tắc cùng khớp một đầu vào nhưng đưa ra hành động mâu thuẫn không?
- Có hành động nào không được định nghĩa trong một trường hợp cần xử lý không?
- Các tổ hợp không thể xảy ra đã được ghi rõ chưa?
- Quy tắc mặc định khi không khớp điều kiện là gì?

Nếu dùng điều kiện nhiều giá trị, số tổ hợp lý thuyết có thể tăng theo tích số giá trị của từng điều kiện. Không cần tạo một cột cho mọi tổ hợp nếu có thể chứng minh một số điều kiện không ảnh hưởng hoặc các trường hợp có cùng hành động theo quy tắc nghiệp vụ. Việc rút gọn phải giữ nguyên ý nghĩa và có thể giải thích.

### 3.5. Bước 5 — Chuyển quy tắc thành kiểm thử

Một cách cơ bản là tạo ít nhất một ca kiểm thử cho mỗi quy tắc có thể xảy ra. Với mỗi ca, xác định:

1. Dữ liệu và trạng thái ban đầu.
2. Giá trị của từng điều kiện.
3. Hành động kích hoạt quyết định.
4. Kết quả mong đợi.
5. Bằng chứng và oracle dùng để xác nhận.

Với quy tắc có ngưỡng, bổ sung kiểm thử sát biên. Ví dụ, nếu được hủy đến đúng 24 giờ trước giờ hẹn, cần kiểm tra 24 giờ + một đơn vị thời gian nhỏ, đúng 24 giờ và 24 giờ - một đơn vị thời gian nhỏ theo độ chính xác mà hệ thống hỗ trợ.

## 4. Các mức bao phủ cho bảng quyết định

Không có một mức bao phủ duy nhất phù hợp cho mọi bảng. Chọn mức theo rủi ro và số lượng điều kiện.

| Mức bao phủ | Ý nghĩa | Khi phù hợp |
| --- | --- | --- |
| Rule coverage | Mỗi quy tắc có ít nhất một ca kiểm thử | Bảng nhỏ, quy tắc quan trọng và tổ hợp đã được xác định |
| Condition coverage | Mỗi điều kiện nhận từng giá trị liên quan ít nhất một lần | Cần xác nhận từng yếu tố điều kiện được xử lý |
| Condition combination coverage | Các tổ hợp giá trị điều kiện được kiểm tra theo mức đã chọn | Quy tắc có tương tác giữa nhiều điều kiện |
| Boundary coverage | Giá trị sát ngưỡng và tại ngưỡng được kiểm tra | Phí, thời gian, hạn mức, số lượng hoặc điểm số |
| Invalid combination coverage | Tổ hợp không hợp lệ hoặc mâu thuẫn được kiểm tra để bảo đảm xử lý an toàn | Đầu vào có thể bị thao túng hoặc dữ liệu có thể không nhất quán |

Rule coverage không đảm bảo condition coverage. Ví dụ, một quy tắc dùng điều kiện “người dùng có quyền” có thể được kiểm thử ở nhánh có quyền nhưng chưa kiểm tra trường hợp không có quyền.

Condition coverage cũng không đảm bảo mọi tổ hợp điều kiện đã được thử. Với rủi ro cao, cần xem xét kiểm thử tổ hợp, pairwise hoặc các kỹ thuật bao phủ mạnh hơn. Nếu yêu cầu an toàn hoặc quy định đòi hỏi mức bao phủ cụ thể, phải tuân theo yêu cầu đó.

### 4.1. Kiểm soát số lượng tổ hợp

Khi có nhiều điều kiện, số tổ hợp có thể tăng nhanh. Có thể giảm tập kiểm thử bằng cách:

- Nhóm các điều kiện có cùng hành động khi giá trị khác nhau không làm thay đổi quyết định.
- Dùng don't care khi điều kiện thực sự không ảnh hưởng.
- Chia bảng lớn thành các quyết định nhỏ có ranh giới rõ.
- Dùng pairwise hoặc combinatorial testing cho tương tác giữa nhiều yếu tố khi phù hợp.
- Ưu tiên tổ hợp có rủi ro cao, lịch sử lỗi hoặc tác động lớn.

Không rút gọn các tổ hợp có thể tạo ra hậu quả nghiêm trọng chỉ vì chúng hiếm gặp. Cần ghi rõ lý do khi một tổ hợp bị loại khỏi phạm vi kiểm thử.

## 5. Mô hình trạng thái là gì?

Mô hình trạng thái mô tả vòng đời của một đối tượng hoặc quy trình. Nó xác định:

- **Trạng thái (state):** tình trạng hiện tại của đối tượng, ví dụ DRAFT, PENDING, CONFIRMED, CANCELLED.
- **Sự kiện (event):** điều xảy ra và có thể kích hoạt chuyển trạng thái, ví dụ Submit, PaymentSucceeded, Expire hoặc Cancel.
- **Điều kiện bảo vệ (guard):** điều kiện phải đúng để chuyển tiếp được phép.
- **Chuyển trạng thái (transition):** thay đổi từ trạng thái hiện tại sang trạng thái tiếp theo.
- **Hành động (action):** tác động được thực hiện khi chuyển tiếp xảy ra, ví dụ ghi thời điểm, phát event hoặc tạo yêu cầu hoàn tiền.

Một state machine hữu ích phải phân biệt rõ trạng thái hiện tại với sự kiện đến. Cùng một sự kiện có thể có kết quả khác nhau tùy trạng thái và guard.

### 5.1. Khi nào nên dùng mô hình trạng thái?

Mô hình trạng thái phù hợp khi:

- Một đối tượng có vòng đời gồm nhiều giai đoạn.
- Hành động được phép phụ thuộc trạng thái hiện tại.
- Có chuyển trạng thái hợp lệ và không hợp lệ cần xác nhận.
- Sự kiện có thể đến trễ, lặp hoặc sai thứ tự.
- Cần kiểm tra trạng thái kết thúc, timeout, retry hoặc phục hồi.
- Một lỗi có thể làm đối tượng mắc kẹt hoặc chuyển sang trạng thái không thể quay lại.

Ví dụ thường gặp: đơn hàng, giao dịch thanh toán, yêu cầu phê duyệt, tài khoản, đăng ký dịch vụ, hồ sơ hỗ trợ và lịch hẹn.

### 5.2. Xác định trạng thái có ý nghĩa

Trạng thái nên mô tả những khác biệt ảnh hưởng đến hành vi. Nếu hai giá trị không làm thay đổi hành động, quyền hoặc kết quả nghiệp vụ, có thể chúng không cần là hai trạng thái riêng.

Ví dụ, một đơn hàng có thể có:

- CREATED: đã tạo nhưng chưa gửi xử lý.
- PAYMENT_PENDING: đang chờ kết quả thanh toán.
- CONFIRMED: đã xác nhận.
- CANCELLED: đã hủy.
- EXPIRED: hết hạn mà chưa hoàn tất.

Tránh tạo quá nhiều trạng thái chỉ để phản ánh từng bước kỹ thuật nội bộ. Ngược lại, không gộp hai trạng thái nếu chúng có quyền, tác động dữ liệu hoặc hành động tiếp theo khác nhau.

### 5.3. Định nghĩa sự kiện và guard

Sự kiện cần có tên và ý nghĩa rõ. Ví dụ:

- SubmitOrder: người dùng gửi đơn.
- PaymentSucceeded: provider xác nhận thanh toán thành công.
- PaymentFailed: provider xác nhận thất bại cuối.
- PaymentTimedOut: hết thời gian chờ phản hồi đồng bộ.
- CancelRequested: người dùng yêu cầu hủy.
- ExpirationReached: thời hạn giữ tài nguyên kết thúc.

Guard xác định khi nào sự kiện được chấp nhận. Ví dụ, CancelRequested chỉ hợp lệ khi đơn đang ở trạng thái CONFIRMED và thời điểm yêu cầu còn trong cửa sổ hủy.

Không nên gộp timeout với thất bại cuối nếu hệ thống chưa có bằng chứng rằng giao dịch đã thất bại. Timeout có thể chỉ có nghĩa là chưa nhận được phản hồi trong thời hạn.

## 6. Quy trình xây dựng mô hình trạng thái

### 6.1. Bước 1 — Chọn đối tượng và ranh giới vòng đời

Xác định đối tượng nào có trạng thái cần quản lý: đơn hàng, lịch hẹn, thanh toán hay yêu cầu hoàn tiền. Không trộn nhiều vòng đời độc lập vào một state machine nếu chúng có quy tắc và chủ sở hữu khác nhau.

Ví dụ, trạng thái đặt lịch và trạng thái hoàn tiền có thể liên quan nhưng không nhất thiết là cùng một biến trạng thái. Một lịch có thể đã hủy trong khi yêu cầu hoàn tiền vẫn đang chờ xử lý.

### 6.2. Bước 2 — Liệt kê trạng thái và trạng thái kết thúc

Với mỗi trạng thái, ghi:

- Ý nghĩa nghiệp vụ.
- Điều kiện để vào trạng thái.
- Hành động được phép.
- Hành động bị cấm.
- Điều kiện rời trạng thái.
- Có thể quay lại hay không.

Trạng thái kết thúc (terminal state) là trạng thái mà vòng đời hiện tại không có chuyển tiếp nghiệp vụ thông thường nào khác. Nếu có quy trình mở lại hoặc khôi phục, hãy mô tả rõ sự kiện và quyền cho phép.

### 6.3. Bước 3 — Liệt kê sự kiện và chuyển tiếp

Mỗi chuyển tiếp cần xác định trạng thái nguồn, sự kiện, guard, trạng thái đích và hành động đi kèm.

| Trạng thái hiện tại | Sự kiện | Guard | Trạng thái tiếp theo | Hành động |
| --- | --- | --- | --- | --- |
| CREATED | SubmitOrder | Dữ liệu hợp lệ và tài nguyên còn khả dụng | PAYMENT_PENDING | Tạo yêu cầu thanh toán |
| PAYMENT_PENDING | PaymentSucceeded | Mã giao dịch khớp và xác nhận hợp lệ | CONFIRMED | Ghi nhận giao dịch và xác nhận đơn |
| PAYMENT_PENDING | PaymentFailed | Provider xác nhận thất bại cuối | CANCELLED | Giải phóng tài nguyên theo quy tắc |
| PAYMENT_PENDING | ExpirationReached | Hết thời hạn và chưa có xác nhận thành công | EXPIRED | Đóng yêu cầu và giải phóng giữ chỗ |
| CONFIRMED | CancelRequested | Còn trong cửa sổ hủy và người dùng có quyền | CANCELLED | Khởi tạo quy trình hoàn tiền nếu cần |
| CANCELLED | CancelRequested | Đơn đã ở trạng thái hủy | CANCELLED | Trả kết quả idempotent, không lặp tác dụng phụ |
| EXPIRED | PaymentSucceeded | Không có quy trình khôi phục được cho phép | EXPIRED hoặc trạng thái xử lý ngoại lệ đã định nghĩa | Đưa vào đối soát; không tự xác nhận đơn |

Bảng này chỉ là mô hình minh họa. Trạng thái và hành động cụ thể phải được xác nhận theo chính sách sản phẩm, đặc biệt với trường hợp callback đến trễ sau khi đơn đã hết hạn.

### 6.4. Bước 4 — Kiểm tra tính đầy đủ và nhất quán

Hãy kiểm tra:

- Mọi trạng thái có ý nghĩa đều được định nghĩa.
- Mọi sự kiện quan trọng đều có kết quả ở từng trạng thái liên quan.
- Không có chuyển tiếp không thể xảy ra hoặc không có chủ sở hữu.
- Guard không mâu thuẫn với quy tắc nghiệp vụ.
- Trạng thái kết thúc được xác định rõ.
- Timeout, retry, event lặp và event sai thứ tự được xử lý.
- Hành động có tác dụng phụ có cơ chế idempotency hoặc kiểm soát trùng.
- Không có đường đi khiến đối tượng bị mắc kẹt vô thời hạn mà không có cảnh báo hoặc quy trình xử lý.

### 6.5. Bước 5 — Chuyển tiếp thành ca kiểm thử

Với mỗi chuyển tiếp quan trọng, tạo ca kiểm thử gồm:

1. Đặt đối tượng vào trạng thái nguồn.
2. Gửi sự kiện tương ứng.
3. Thiết lập guard đúng hoặc sai.
4. Kiểm tra trạng thái đích.
5. Kiểm tra hành động và tác dụng phụ.
6. Kiểm tra sự kiện lặp hoặc không hợp lệ nếu có.

Ngoài chuyển tiếp hợp lệ, cần kiểm tra chuyển tiếp bị từ chối. Ví dụ, một đơn CANCELLED không được chuyển trở lại CONFIRMED chỉ vì callback thanh toán cũ đến muộn, trừ khi nghiệp vụ có quy trình khôi phục được định nghĩa.

## 7. Các mức bao phủ cho mô hình trạng thái

| Mức bao phủ | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| State coverage | Mỗi trạng thái được thăm ít nhất một lần | Không chứng minh các chuyển tiếp đã được kiểm tra |
| Transition coverage | Mỗi chuyển tiếp được thực hiện ít nhất một lần | Không nhất thiết bao phủ mọi chuỗi nhiều bước |
| Transition-pair coverage | Mỗi cặp chuyển tiếp liên tiếp hợp lệ được kiểm tra | Có thể bỏ sót lỗi chỉ xuất hiện trong chuỗi dài hơn |
| Transition-path coverage | Kiểm tra các đường đi qua nhiều trạng thái theo phạm vi đã chọn | Số đường đi có thể tăng rất lớn hoặc vô hạn nếu có vòng lặp |
| Invalid-transition coverage | Kiểm tra sự kiện không được phép ở trạng thái hiện tại | Cần xác định rõ phản hồi và tác dụng phụ phải bị ngăn |

State coverage đơn thuần thường quá yếu. Một test có thể thăm tất cả trạng thái nhưng không kiểm tra đường chuyển quan trọng hoặc guard sai. Với rủi ro cao, nên ưu tiên transition coverage và kiểm thử chuyển tiếp không hợp lệ.

### 7.1. Kiểm tra guard ở cả hai phía

Với mỗi guard, cần có ca mà điều kiện đúng và ca mà điều kiện sai. Nếu guard phụ thuộc một ngưỡng, hãy kiểm tra:

- Ngay dưới ngưỡng.
- Đúng tại ngưỡng.
- Ngay trên ngưỡng.

Ví dụ, nếu lịch được hủy đến 24 giờ trước giờ hẹn, hãy xác định chính xác múi giờ, độ chính xác thời gian và cách xử lý thời điểm đúng 24 giờ. Không để các môi trường khác nhau diễn giải ngưỡng theo cách khác nhau.

### 7.2. Kiểm thử chuỗi sự kiện

Một số lỗi chỉ xuất hiện khi sự kiện đến theo thứ tự khác dự kiến:

- PaymentSucceeded đến sau ExpirationReached.
- CancelRequested đến hai lần.
- PaymentFailed đến sau PaymentSucceeded.
- Event được xử lý lại sau khi worker restart.
- Callback đến trước khi consumer đã lưu trạng thái ban đầu.

Hãy xác định thứ tự nào hợp lệ, thứ tự nào có thể xảy ra trong thực tế và hệ thống phải xử lý ra sao. Với event lặp, kiểm tra idempotency và bảo đảm tác dụng phụ không được thực hiện nhiều lần ngoài quy tắc.

## 8. Khi nào dùng bảng quyết định, khi nào dùng mô hình trạng thái?

| Tiêu chí | Bảng quyết định | Mô hình trạng thái |
| --- | --- | --- |
| Trọng tâm | Tổ hợp điều kiện dẫn đến hành động | Vòng đời và chuyển tiếp của đối tượng |
| Câu hỏi chính | “Với các điều kiện này, quyết định là gì?” | “Ở trạng thái này, sự kiện nào được phép và dẫn đến đâu?” |
| Dữ liệu đầu vào | Giá trị điều kiện tại thời điểm ra quyết định | Trạng thái hiện tại, sự kiện và guard |
| Đầu ra | Hành động, kết quả, mức phí, quyền hoặc quyết định | Trạng thái tiếp theo và hành động khi chuyển tiếp |
| Dạng lỗi thường phát hiện | Thiếu tổ hợp, quy tắc mâu thuẫn, điều kiện không được xét | Chuyển trạng thái sai, trạng thái không thể đạt, sự kiện lặp hoặc sai thứ tự |
| Phù hợp với | Phê duyệt, tính phí, phân loại, điều kiện quyền | Đơn hàng, giao dịch, lịch hẹn, yêu cầu và quy trình nhiều bước |

### 8.1. Dùng cả hai khi nghiệp vụ có cả quyết định và vòng đời

Ví dụ hủy lịch:

- Mô hình trạng thái xác định lịch hiện tại có đang hoạt động và sự kiện hủy có được phép ở giai đoạn này không.
- Bảng quyết định xác định yêu cầu hủy có được chấp nhận dựa trên thời hạn, trạng thái thanh toán và loại dịch vụ; nếu được chấp nhận thì mức hoàn tiền hoặc phí hủy là bao nhiêu.

Luồng xử lý có thể là:

1. Đọc trạng thái hiện tại của lịch.
2. Kiểm tra sự kiện hủy có hợp lệ theo state model không.
3. Nếu hợp lệ, đánh giá điều kiện bằng decision table.
4. Thực hiện hành động và chuyển trạng thái.
5. Xác nhận trạng thái cuối cùng và các tác dụng phụ.

~~~mermaid
flowchart TD
    START["Nhận yêu cầu hủy"] --> STATE["Đọc trạng thái lịch"]
    STATE --> VALID{"Trạng thái cho phép<br/>xử lý hủy?"}
    VALID -->|"Không"| REJECT["Từ chối hoặc trả kết quả idempotent"]
    VALID -->|"Có"| TABLE["Đánh giá bảng quyết định"]
    TABLE --> ALLOW{"Quy tắc cho phép hủy?"}
    ALLOW -->|"Không"| KEEP["Giữ nguyên trạng thái"]
    ALLOW -->|"Có"| ACTION["Thực hiện hủy và hành động liên quan"]
    ACTION --> VERIFY["Kiểm tra trạng thái cuối<br/>và tác dụng phụ"]
~~~

Tách hai mô hình giúp tránh một bảng quyết định phải chứa toàn bộ lịch sử trạng thái hoặc một state machine phải mã hóa mọi tổ hợp điều kiện chi tiết.

## 9. Ví dụ hoàn chỉnh: đặt lịch và thanh toán

### 9.1. Mô hình trạng thái của khung giờ

Một khung giờ có thể có các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> AVAILABLE
    AVAILABLE --> HELD: HoldRequested / còn khả dụng
    HELD --> BOOKED: BookingConfirmed
    HELD --> AVAILABLE: HoldExpired
    HELD --> AVAILABLE: PaymentFailed
    BOOKED --> CANCELLED: CancelAccepted
    CANCELLED --> [*]
~~~

Mô hình này cho thấy một khung giờ được giữ tạm thời trước khi xác nhận. Nếu thời hạn giữ hết hoặc thanh toán thất bại cuối, khung giờ được giải phóng. Khi lịch đã được xác nhận, việc hủy cần đi qua quy tắc nghiệp vụ tương ứng.

### 9.2. Bảng quyết định cho yêu cầu hủy

Giả sử chính sách minh họa:

- Chỉ lịch đã xác nhận mới được yêu cầu hủy.
- Hủy trong thời hạn cho phép được chấp nhận.
- Nếu đã thanh toán, hệ thống tạo yêu cầu hoàn tiền.
- Nếu quá thời hạn, hệ thống từ chối và giữ lịch.

| Điều kiện / Quy tắc | R1 | R2 | R3 | R4 |
| --- |:---:|:---:|:---:|:---:|
| Lịch đang CONFIRMED? | Không | Có | Có | Có |
| Trong thời hạn hủy? | – | Có | Có | Không |
| Đã thanh toán? | – | Có | Không | – |
| **Hành động** | | | | |
| Chấp nhận hủy | Không | Có | Có | Không |
| Chuyển lịch sang CANCELLED | Không đổi | Có | Có | Không đổi |
| Tạo yêu cầu hoàn tiền | Không | Có | Không | Không |

Trong hệ thống thực tế, cần bổ sung các trạng thái hoàn tiền, yêu cầu hủy đang xử lý, chính sách phí và callback đến trễ nếu chúng ảnh hưởng đến quyết định. Bảng và state model cần cùng tham chiếu một định nghĩa thời hạn và trạng thái nghiệp vụ.

### 9.3. Tập kiểm thử đại diện

| ID | Trạng thái ban đầu | Điều kiện/sự kiện | Kết quả mong đợi |
| --- | --- | --- | --- |
| T1 | Lịch CONFIRMED | Hủy trong hạn, đã thanh toán | Lịch chuyển CANCELLED; tạo đúng một yêu cầu hoàn tiền |
| T2 | Lịch CONFIRMED | Hủy trong hạn, chưa thanh toán | Lịch chuyển CANCELLED; không tạo yêu cầu hoàn tiền |
| T3 | Lịch CONFIRMED | Hủy quá hạn | Yêu cầu bị từ chối; lịch vẫn CONFIRMED |
| T4 | Lịch CANCELLED | Gửi yêu cầu hủy lần nữa | Không lặp tác dụng phụ; phản hồi theo hợp đồng idempotency |
| T5 | Lịch HELD | Hết thời hạn giữ | Khung giờ trở lại AVAILABLE |
| T6 | Lịch HELD | PaymentSucceeded đến sau khi hold đã hết hạn | Không xác nhận lịch sai; chuyển sang quy trình đối soát/ngoại lệ đã định nghĩa |
| T7 | Lịch CONFIRMED | Hai yêu cầu hủy đến đồng thời | Chỉ một lần chuyển trạng thái và một tác dụng phụ theo quy tắc |

Tập kiểm thử này kết hợp rule coverage cho bảng quyết định với transition và invalid-transition coverage cho state model. Với T6 và T7, cần thu thập correlation ID, trạng thái cuối và bằng chứng đối soát để xác nhận tính nhất quán.

## 10. Tổ chức dữ liệu và oracle cho kiểm thử mô hình

### 10.1. Dữ liệu phải phản ánh điều kiện của quy tắc

Với decision table, tạo dữ liệu sao cho mỗi điều kiện có thể nhận giá trị cần kiểm tra. Với state model, chuẩn bị đối tượng ở đúng trạng thái nguồn trước khi gửi sự kiện.

Có thể sử dụng:

- Fixture hoặc factory tạo dữ liệu có trạng thái xác định.
- API hỗ trợ kiểm thử để tạo đối tượng.
- Event fixture theo schema được công bố.
- Clock giả lập hoặc cơ chế điều khiển thời gian trong môi trường test.
- Sandbox cho dịch vụ ngoài.

Nếu setup trực tiếp database, cần ghi rõ nó chỉ chuẩn bị trạng thái và không bỏ qua hành vi đang được xác nhận. Ví dụ, không thể dùng việc ghi trực tiếp trạng thái BOOKED làm bằng chứng rằng luồng xác nhận booking hoạt động đúng.

### 10.2. Oracle cho bảng quyết định

Oracle có thể là:

- Hành động được phép hoặc bị từ chối.
- Mức phí, mức hoàn tiền hoặc hạn mức mong đợi.
- Mã lỗi hoặc phản hồi theo hợp đồng.
- Trạng thái dữ liệu và các bất biến liên quan.
- Tác dụng phụ được tạo đúng số lần.

### 10.3. Oracle cho mô hình trạng thái

Oracle cần kiểm tra:

- Trạng thái trước và sau sự kiện.
- Guard đúng/sai.
- Hành động khi chuyển tiếp.
- Tác dụng phụ và event được phát.
- Trạng thái không thay đổi khi chuyển tiếp bị từ chối.
- Không xuất hiện trạng thái không hợp lệ hoặc đường đi bị mắc kẹt.

Với hệ thống bất đồng bộ, cần chờ theo điều kiện có timeout, không dựa vào sleep cố định. Nếu trạng thái cuối không đạt, giữ lại chuỗi sự kiện và trace để phân tích.

## 11. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng bảng quyết định cho toàn bộ vòng đời dài | Bảng phình to, khó thể hiện thứ tự và lịch sử | Tách vòng đời thành state model; dùng decision table cho từng quyết định |
| Dùng state machine cho mọi tổ hợp điều kiện | Số trạng thái tăng không cần thiết | Đưa điều kiện quyết định vào bảng hoặc guard có cấu trúc |
| Bỏ qua tổ hợp không hợp lệ | Đầu vào mâu thuẫn có thể gây hành vi không xác định | Định nghĩa cách từ chối và kiểm thử invalid combination |
| Dùng don't care tùy tiện | Bỏ qua điều kiện thực sự ảnh hưởng | Chỉ rút gọn khi có căn cứ nghiệp vụ |
| Chỉ kiểm tra state coverage | Có thể bỏ sót chuyển tiếp quan trọng | Bổ sung transition và invalid-transition coverage |
| Không kiểm tra event lặp hoặc đến trễ | Có thể ghi trùng hoặc chuyển trạng thái sai | Kiểm thử idempotency, thứ tự và đối soát |
| Không xác định trạng thái kết thúc | Đối tượng có thể mắc kẹt vô thời hạn | Định nghĩa timeout, terminal state và quy trình xử lý ngoại lệ |
| Kiểm tra hành động nhưng không kiểm tra trạng thái cuối | Test pass dù dữ liệu nghiệp vụ sai | Dùng oracle kiểm tra state và tác dụng phụ |
| Mô hình và code không được đồng bộ | Test xác nhận mô hình cũ | Rà soát mô hình khi quy tắc hoặc kiến trúc thay đổi |

## 12. Quản lý thay đổi quy tắc và mô hình

Quy tắc nghiệp vụ thay đổi khi chính sách, sản phẩm hoặc phụ thuộc thay đổi. Khi có thay đổi, nhóm nên:

1. Ghi nguồn và phiên bản thay đổi.
2. Xác định điều kiện, hành động, trạng thái hoặc chuyển tiếp bị ảnh hưởng.
3. Kiểm tra các rule mới có mâu thuẫn với rule hiện tại không.
4. Kiểm tra state mới có đường vào, đường ra và trạng thái kết thúc rõ ràng không.
5. Cập nhật ca kiểm thử, dữ liệu và oracle liên quan.
6. Phân tích tác động tới API, event, báo cáo và người dùng.
7. Lưu bằng chứng và người xác nhận quy tắc.

Không nên chỉ sửa test expected để khớp với code hiện tại khi chưa có xác nhận nghiệp vụ. Nếu mô hình thay đổi, cần có dấu vết về lý do và người phê duyệt.

## 13. Mẫu ghi nhận bảng quyết định và mô hình trạng thái

### 13.1. Mẫu bảng quyết định

~~~text
Tên quyết định:
Mục tiêu nghiệp vụ:
Phạm vi / đối tượng:
Nguồn quy tắc và người xác nhận:

Điều kiện:
- C1:
- C2:
- C3:

Miền giá trị:
Các quy tắc:
Hành động tương ứng:
Tổ hợp không hợp lệ:
Quy tắc mặc định:
Ngưỡng / trường hợp biên:

Mức bao phủ được chọn:
Ca kiểm thử và dữ liệu:
Oracle / bằng chứng:
Giả định và ngoại lệ:
~~~

### 13.2. Mẫu mô hình trạng thái

~~~text
Tên đối tượng / vòng đời:
Mục tiêu nghiệp vụ:
Chủ sở hữu:

Các trạng thái:
- Tên:
- Ý nghĩa:
- Terminal hay không:

Các sự kiện:
Các guard:
Các chuyển tiếp:
- Trạng thái nguồn:
- Sự kiện:
- Guard:
- Trạng thái đích:
- Hành động:

Sự kiện lặp / trễ / sai thứ tự:
Timeout và retry:
Bất biến:
Mức bao phủ state/transition/path:
Ca kiểm thử và oracle:
~~~

## 14. Checklist chọn và áp dụng kỹ thuật

- [ ] Đã xác định câu hỏi nghiệp vụ cần mô hình hóa.
- [ ] Đã chọn bảng quyết định cho tổ hợp điều kiện và mô hình trạng thái cho vòng đời phù hợp.
- [ ] Các điều kiện có ý nghĩa rõ và miền giá trị được xác định.
- [ ] Don't care chỉ được dùng khi điều kiện thực sự không ảnh hưởng đến quyết định.
- [ ] Mỗi tổ hợp hợp lệ có quy tắc hoặc có lý do được loại trừ.
- [ ] Không có rule mâu thuẫn hoặc hành động chưa xác định.
- [ ] Trạng thái, sự kiện, guard, chuyển tiếp và terminal state được định nghĩa.
- [ ] Chuyển tiếp không hợp lệ, event lặp, trễ và sai thứ tự được xem xét.
- [ ] Mức bao phủ được chọn dựa trên rủi ro và yêu cầu.
- [ ] Dữ liệu kiểm thử có thể đưa đối tượng vào trạng thái cần thiết một cách tái lập.
- [ ] Oracle kiểm tra cả quyết định, trạng thái cuối và tác dụng phụ quan trọng.
- [ ] Mô hình được liên kết với yêu cầu, người xác nhận và bộ kiểm thử.
- [ ] Thay đổi quy tắc có quy trình cập nhật mô hình và đánh giá hồi quy.

Bảng quyết định làm rõ cách điều kiện dẫn đến hành động; mô hình trạng thái làm rõ cách sự kiện thay đổi vòng đời của đối tượng. Khi chọn đúng kỹ thuật, kiểm tra tính đầy đủ và chuyển mô hình thành ca kiểm thử có oracle, nhóm có thể bao phủ quy tắc nghiệp vụ một cách có hệ thống và giải thích được phần hành vi đã được xác nhận.
