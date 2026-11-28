# Rate limit PAM API

## 1. Mục tiêu và phạm vi

Trong hệ thống Privileged Access Management (PAM), API thường phục vụ những thao tác có tác động lớn: tạo yêu cầu nâng quyền, phê duyệt truy cập, lấy credential từ vault, tạo phiên quản trị, luân chuyển mật khẩu và thu hồi quyền. Một automation gọi quá nhanh có thể làm chậm toàn bộ chuỗi kiểm soát đặc quyền, kể cả khi mọi request đều có token hợp lệ.

**Rate limit PAM API** là việc giới hạn tốc độ hoặc số lượng request được tiếp nhận trong một phạm vi xác định. Mục tiêu là giữ hệ thống ổn định, phân phối công bằng tài nguyên, giảm khả năng lạm dụng và bảo vệ những thao tác cần ưu tiên như thu hồi quyền. Đây là một lớp kiểm soát bổ sung cho xác thực, phân quyền, least privilege và kiểm toán; hạn mức còn dư không có nghĩa là caller được phép thực hiện thao tác.

Sau bài này, người học có thể:

- Phân biệt rate limit, quota, concurrency limit và timeout.
- Xác định caller, tài nguyên và loại thao tác cần áp dụng hạn mức.
- Chọn cơ chế giới hạn phù hợp với burst và tải liên tục.
- Thiết kế automation phản ứng đúng với HTTP 429 và tín hiệu chờ.
- Tránh cấp quyền hoặc luân chuyển credential hai lần do retry thiếu kiểm soát.
- Thiết lập quan sát, kiểm thử và quy trình điều chỉnh hạn mức dựa trên bằng chứng.

Các endpoint, tên header riêng, cấu hình và số liệu trong bài là ví dụ minh họa, không mô tả hợp đồng của một sản phẩm PAM cụ thể. Khi tích hợp một sản phẩm, cần dùng hợp đồng API và chính sách hạn mức của hệ thống đó.

## 2. Vì sao PAM cần giới hạn tốc độ riêng?

### 2.1. Một request có thể kích hoạt nhiều hệ thống

Một lệnh tạo phiên quản trị không chỉ là một lần ghi cơ sở dữ liệu. Nó có thể kéo theo kiểm tra MFA, kiểm tra policy, đánh giá approval, truy xuất secret, khởi tạo proxy, mở kết nối tới máy đích và bắt đầu ghi hình phiên. Một lệnh rotate có thể phải cập nhật credential ở máy đích, kiểm tra đăng nhập và lưu phiên bản mới vào vault.

Vì vậy, tải tính theo request/giây chưa phản ánh đầy đủ chi phí. Mười request đọc metadata có thể nhẹ hơn một request rotate tài khoản được nhiều ứng dụng sử dụng.

### 2.2. Automation hợp lệ vẫn có thể gây sự cố

Các tình huống thường gặp:

- Một pipeline bị lặp, liên tục tạo yêu cầu truy cập cho cùng một deployment.
- Nhiều replica đồng loạt gọi vault khi khởi động lại.
- Một job kiểm kê polling trạng thái từng tài khoản thay vì lấy theo trang hoặc dùng sự kiện.
- Sau khi PAM phục hồi, hàng nghìn client cùng retry ngay lập tức.
- Credential của automation bị lộ; kẻ tấn công dùng token hợp lệ để tăng tốc lấy secret hoặc tạo phiên.

Rate limit có thể giảm tốc độ và tác động của các tình huống này, nhưng không thay thế phát hiện xâm nhập. Một token bị lạm dụng chậm vẫn nguy hiểm. Cần kết hợp phân quyền hẹp, thời hạn credential phù hợp, kiểm tra hành vi và khả năng thu hồi.

### 2.3. Bảo vệ luồng kết thúc quyền

Nếu job đọc inventory dùng hết tài nguyên của PAM, người vận hành có thể không thu hồi được phiên đáng ngờ đúng lúc. Thiết kế tốt cần tách hoặc dành tài nguyên cho các luồng như:

- Thu hồi quyền JIT và hủy yêu cầu chưa thực hiện.
- Kết thúc phiên đặc quyền.
- Vô hiệu hóa credential hoặc token bị nghi lộ.
- Ghi nhận sự kiện kiểm toán và chuyển bằng chứng tới nơi lưu trữ.

Các luồng này vẫn phải được xác thực và phân quyền. Ưu tiên xử lý không đồng nghĩa với endpoint công khai không giới hạn.

## 3. Phân biệt các cơ chế kiểm soát tải

| Cơ chế | Câu hỏi được giải quyết | Ví dụ trong PAM |
|---|---|---|
| Rate limit | Trong một khoảng thời gian, cho phép tiếp nhận nhanh đến mức nào? | Automation được tạo tối đa một số yêu cầu truy cập mỗi giây. |
| Quota | Tổng ngân sách sử dụng trong một kỳ là bao nhiêu? | Giới hạn tổng số tác vụ kiểm kê theo ngày cho một tenant. |
| Concurrency limit | Có bao nhiêu thao tác đang chạy đồng thời? | Chỉ cho một số tác vụ rotate hoạt động cùng lúc trên một connector. |
| Timeout | Một lần gọi hoặc tác vụ được chờ trong bao lâu? | Dừng chờ phản hồi sau deadline đã đặt. |
| Queue limit | Có bao nhiêu công việc được xếp hàng? | Từ chối enqueue khi hàng đợi rotation đã đầy. |

Những cơ chế này bổ sung cho nhau. Nếu PAM nhận hai tác vụ rotate mỗi giây và mỗi tác vụ kéo dài 30 giây, số tác vụ đồng thời có thể tiến gần 60 trong trạng thái ổn định. Hạn mức hai request/giây không tự bảo đảm connector chịu được 60 tác vụ đang chạy.

Một quan hệ ước lượng hữu ích khi hệ thống ở trạng thái ổn định là:

```text
số tác vụ đồng thời trung bình ≈ tốc độ tác vụ × thời gian xử lý trung bình
```

Quan hệ này dùng để lập kế hoạch ban đầu, không phải bảo đảm cho đỉnh tải hoặc thời gian xử lý bất thường. Với tác vụ bất đồng bộ, cần tính cả tác vụ còn chạy sau khi HTTP request tạo job đã kết thúc.

Timeout của client cũng không chứng minh server đã hủy thao tác. Client hết thời gian chờ có thể xảy ra sau khi server đã tạo phiên hoặc đã bắt đầu rotate.

## 4. Xác định đúng phạm vi hạn mức

### 4.1. Không chỉ giới hạn theo địa chỉ IP

IP có ích ở biên hệ thống để giảm lưu lượng chưa xác thực, nhưng không đủ làm danh tính nghiệp vụ:

- Nhiều automation có thể đi qua cùng một NAT.
- Một caller có thể đi qua nhiều egress IP.
- IP không cho biết tenant, service principal hoặc loại quyền đã được cấp.
- Hạn mức chỉ theo IP có thể làm một nhóm công việc ảnh hưởng nhóm khác không liên quan.

Sau xác thực, khóa hạn mức nên được suy ra từ ngữ cảnh đã được server xác minh, chẳng hạn tenant ID, service principal ID và nhóm thao tác. Không tin trực tiếp `X-Tenant`, `X-User` hoặc header tự khai báo từ bên ngoài. Nếu gateway chuyển danh tính xuống dịch vụ, kênh và header đó phải được bảo vệ khỏi giả mạo.

### 4.2. Áp dụng nhiều lớp hạn mức

Một request có thể cần đi qua các lớp sau:

```text
giới hạn lưu lượng ở biên
    → xác thực và xác định tenant/caller
    → kiểm tra quyền
    → hạn mức tenant và service principal
    → hạn mức nhóm thao tác hoặc tài nguyên
    → giới hạn tác vụ đồng thời và sức khỏe dependency
    → thực hiện thao tác, lưu kết quả và bằng chứng
```

Đây là thứ tự logic minh họa. Hệ thống thực có thể áp dụng thêm hạn mức trước phân quyền để bảo vệ dịch vụ policy, hoặc gộp một số bước. Các request không được phép không được phép vượt qua kiểm tra quyền chỉ vì đã qua limiter.

Những lớp hữu ích trong PAM gồm:

- **Toàn hệ thống hoặc cụm:** bảo vệ năng lực tổng thể.
- **Tenant:** tránh một tenant chiếm tài nguyên của tenant khác.
- **Service principal:** phân phối ngân sách giữa các automation trong tenant.
- **Nhóm thao tác:** tách đọc inventory, lấy secret, tạo phiên và rotate.
- **Tài nguyên đích:** tránh nhiều rotation hoặc thao tác xung đột trên cùng tài khoản.
- **Connector hoặc vùng:** bảo vệ thành phần có năng lực thấp hơn API frontend.

Một request có thể bị từ chối khi một trong các lớp hết ngân sách. Chính sách phản hồi cần giúp caller biết cách chờ mà không tiết lộ thông tin nhạy cảm về tenant khác.

### 4.3. Không dùng token làm khóa duy nhất

Nếu mỗi access token mới nhận một ngân sách mới, caller có thể tăng lưu lượng bằng cách liên tục đổi token. Khóa chính thường nên gắn với danh tính ổn định của workload và tenant. Token ID có thể là một chiều bổ sung để phát hiện hoặc khoanh vùng lạm dụng.

Tương tự, nếu chỉ áp dụng hạn mức theo client ID nhưng cho phép một nhóm tạo client ID không kiểm soát, ngân sách tổng của nhóm vẫn có thể bị nhân lên. Cần hạn mức ở cấp cha và quản trị vòng đời danh tính automation.

## 5. Các thuật toán thường dùng

### 5.1. Fixed window

Fixed window đếm request trong một cửa sổ cố định, ví dụ một phút lịch. Cách này dễ hiểu và lưu ít trạng thái.

Nhược điểm là hiệu ứng ranh giới: caller có thể gửi gần hết ngân sách vào cuối một cửa sổ và tiếp tục gửi gần hết ngân sách ở đầu cửa sổ tiếp theo. Hệ thống nhận một burst lớn dù từng cửa sổ riêng vẫn đúng hạn mức.

Fixed window phù hợp với một số ngân sách thô, nhưng không nên mặc định coi nó là cơ chế làm phẳng tải tức thời.

### 5.2. Sliding window

Sliding window đánh giá lưu lượng trong khoảng thời gian trượt so với hiện tại. Có thể lưu từng timestamp để đếm chính xác hoặc dùng các bộ đếm con để xấp xỉ.

Đổi lại việc giảm hiệu ứng ranh giới là chi phí lưu trữ, tính toán và đồng bộ. Khi dùng xấp xỉ, cần công bố sai số hoặc phần vượt có thể chấp nhận, nhất là với thao tác nhạy cảm.

### 5.3. Token bucket

Token bucket có dung lượng tối đa `B`, tốc độ nạp `r` và số token hiện tại `T`. Mỗi request tiêu thụ một lượng token theo chính sách. Khi bucket đầy, thời gian không sử dụng tiếp theo không làm token vượt `B`.

```text
T_mới = min(B, T_cũ + r × thời_gian_đã_trôi)

nếu T_mới ≥ chi_phí_request:
    trừ token và cho phép
ngược lại:
    từ chối hoặc yêu cầu chờ
```

Ví dụ `B = 20`, `r = 5 token/giây`, mỗi request tốn một token. Caller có thể gửi một burst tối đa 20 request khi bucket đầy, sau đó duy trì khoảng 5 request/giây nếu không có giới hạn khác. Đây không phải cam kết rằng mọi cửa sổ một giây đều chỉ có năm request.

Nếu còn hai token, request cần năm token và tốc độ nạp là năm token/giây, thời gian chờ lý thuyết ít nhất là:

```text
(5 − 2) / 5 = 0,6 giây
```

Trong thực tế, các request khác có thể tiêu thụ token trong khi caller chờ. Vì vậy thời gian chờ không bảo đảm lần gọi tiếp theo chắc chắn thành công.

### 5.4. Leaky bucket và hàng đợi

Leaky bucket thường được dùng để điều tiết đầu ra theo nhịp tương đối đều. Nếu triển khai bằng hàng đợi, phải giới hạn cả số phần tử lẫn thời gian chờ.

Với PAM, một yêu cầu cấp quyền nằm trong hàng đợi quá lâu có thể không còn hợp lệ: ticket đã đóng, approval hết hiệu lực, ca trực đã kết thúc hoặc deadline JIT đã qua. Trước khi thực thi, server phải kiểm tra lại những điều kiện có thể thay đổi. Không coi việc đã enqueue là phê duyệt vĩnh viễn.

Tên thuật toán chưa đủ để hiểu hành vi. Cần xác nhận cụ thể hệ thống sẽ từ chối ngay, trì hoãn, xếp hàng hay phân phối theo thứ tự ưu tiên.

## 6. Thiết kế ngân sách theo mức độ tác động

### 6.1. Tách nhóm thao tác

Bảng dưới đây là cấu hình giả định để thảo luận thiết kế, không phải mức khuyến nghị dùng trực tiếp:

| Nhóm thao tác | Hạn mức tốc độ minh họa | Kiểm soát bổ sung |
|---|---|---|
| Đọc metadata inventory | 5 request/giây/caller, burst 20 | Phân trang có giới hạn, kiểm soát truy vấn đắt. |
| Tạo access request | 1 request/giây/caller, burst 3 | Idempotency, giới hạn yêu cầu đang chờ. |
| Lấy secret | Ngân sách riêng theo workload và policy | Quyền theo secret, audit, kiểm soát bất thường. |
| Tạo phiên quản trị | Ngân sách riêng theo tenant | Giới hạn phiên đồng thời và năng lực proxy. |
| Rotate credential | Giới hạn enqueue và số job đang chạy | Khóa hoặc cơ chế tuần tự hóa theo tài khoản đích. |
| Thu hồi quyền, kết thúc phiên | Tài nguyên dự phòng được kiểm soát | Phân quyền chặt, chống lặp, audit và cảnh báo. |

Không gộp lấy secret với đọc metadata chỉ vì cả hai có thể dùng phương thức GET. GET vẫn có thể trả về dữ liệu rất nhạy cảm và có chi phí lớn.

### 6.2. Tính chi phí có trọng số

Trong một số thiết kế, mỗi request tiêu thụ số token khác nhau:

```text
đọc một trang inventory nhỏ:     1 đơn vị
tạo access request:             3 đơn vị
khởi tạo phiên đặc quyền:       5 đơn vị
enqueue một rotation:           8 đơn vị
```

Các trọng số phải được hiệu chỉnh bằng dữ liệu vận hành và có lý do rõ ràng. Một bucket có trọng số không thay thế giới hạn độc lập của nhóm quan trọng. Nếu inventory và revoke cùng chia một bucket, inventory vẫn có thể làm revoke bị đói tài nguyên.

Nếu chi phí lớn hơn dung lượng bucket, request sẽ không bao giờ được chấp nhận. Đây là lỗi cấu hình cần phát hiện trước khi triển khai.

### 6.3. Cân bằng công bằng và năng lực sử dụng

Ngân sách theo tenant ngăn một tenant dùng hết cụm, nhưng chưa bảo đảm các ứng dụng trong tenant được phục vụ công bằng. Cần cân nhắc thêm ngân sách theo caller, ưu tiên theo loại tác vụ và giới hạn hàng đợi.

Một số môi trường cho phép mượn phần năng lực đang rảnh; một số môi trường yêu cầu cách ly cứng. Lựa chọn phụ thuộc khả năng chịu tải, cam kết dịch vụ và rủi ro của từng nhóm thao tác. Mọi cơ chế mượn ngân sách phải giữ giới hạn tổng, có thể quan sát và có thể thu hồi.

## 7. Thực thi hạn mức trong hệ thống phân tán

### 7.1. Bộ đếm cục bộ có thể làm nhân hạn mức

Giả sử mỗi API instance cho một caller 100 request/phút. Nếu có bốn instance và không chia sẻ trạng thái, caller phân tán lưu lượng có thể được tiếp nhận gần 400 request/phút. Việc cấu hình cùng một con số trên mọi instance không tạo ra một hạn mức toàn cụm.

Các lựa chọn thường gặp:

- Dùng kho trạng thái chung với thao tác kiểm tra và trừ ngân sách nguyên tử.
- Cấp phát trước một phần ngân sách toàn cục cho từng instance.
- Dùng limiter cục bộ để bảo vệ nhanh, kết hợp limiter tổng ở cấp cao hơn.
- Phân chia quyền xử lý theo khóa để một khóa có nơi quản lý nhất quán.

Mỗi lựa chọn có đánh đổi về độ trễ, tính sẵn sàng, chi phí đồng bộ và mức vượt giới hạn có thể xảy ra.

### 7.2. Kiểm tra và trừ ngân sách phải nhất quán

Mẫu thao tác sau không an toàn khi nhiều request chạy đồng thời:

```text
đọc bộ đếm
nếu bộ đếm chưa hết:
    cho phép request
    ghi bộ đếm mới
```

Hai request có thể cùng thấy một ngân sách còn lại và cùng được chấp nhận. Cần thao tác nguyên tử, transaction hoặc cơ chế tương đương phù hợp với kho trạng thái.

Khi có nhiều bucket, phải định nghĩa rõ cách tiêu thụ ngân sách: tiêu thụ tất cả khi tiếp nhận hay một số bộ đếm vẫn tính cả request bị từ chối. Chính sách tính request bị từ chối có thể hữu ích để chống lạm dụng, nhưng không nên xuất hiện ngẫu nhiên do cập nhật nhiều khóa dở dang.

### 7.3. Đồng hồ, TTL và nhiều vùng

Đối với limiter cục bộ, đồng hồ đơn điệu giúp đo khoảng thời gian mà không bị ảnh hưởng bởi việc chỉnh giờ hệ thống. Với trạng thái chia sẻ, cần nguồn thời gian và cách tính thống nhất tại nơi thực thi.

TTL giúp dọn những khóa không còn hoạt động, nhưng không được đặt quá ngắn khiến bucket bị reset liên tục. Đồng thời phải giới hạn số lượng khóa để caller không tạo ra lượng lớn trạng thái bằng danh tính hoặc tài nguyên đầu vào tùy ý.

Trong mô hình nhiều vùng, đồng bộ trễ có thể làm tổng lượng request được chấp nhận vượt giới hạn mong muốn. Cần xác định rõ hạn mức là theo vùng hay toàn cục, mức vượt cho phép và cách xử lý khi chia cắt mạng. Không quảng bá một giới hạn toàn cục cứng nếu cách triển khai chỉ bảo đảm giới hạn gần đúng.

### 7.4. Khi dịch vụ limiter gặp lỗi

Phải quyết định hành vi theo nhóm thao tác:

- Cấp quyền mới hoặc lấy secret có thể cần từ chối có kiểm soát khi không xác định được ngân sách, tùy mô hình rủi ro.
- Một số thao tác đọc ít nhạy cảm có thể dùng ngân sách cục bộ dự phòng đã được giới hạn.
- Thu hồi quyền cần đường xử lý đã được thiết kế trước, có tài nguyên dự phòng và các kiểm soát quyền tương ứng.

Không biến lỗi limiter thành cơ chế bỏ qua xác thực, approval hay audit. Nếu hạ tầng hạn mức không hoạt động, phản hồi nên thể hiện lỗi dịch vụ phù hợp; không nhất thiết dùng 429 vì caller có thể chưa hề vượt hạn mức.

## 8. Hợp đồng phản hồi khi bị giới hạn

### 8.1. HTTP 429 nói lên điều gì?

HTTP 429 thường được dùng khi server từ chối request vì caller hoặc phạm vi liên quan đã vượt chính sách giới hạn. Nó khác với:

- `401`: caller chưa cung cấp thông tin xác thực hợp lệ theo hợp đồng API.
- `403`: caller không được phép thực hiện thao tác.
- `503`: dịch vụ tạm thời không thể phục vụ, ví dụ quá tải chung hoặc dependency lỗi.

Không thay mọi lỗi thành 429. Client cần phân biệt chờ ngân sách với sửa credential, xin quyền hoặc xử lý sự cố dịch vụ.

### 8.2. Trả tín hiệu có thể dùng để chờ

Ví dụ phản hồi minh họa:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Cache-Control: no-store
Retry-After: 3
X-Request-ID: req-example-714

{
  "code": "PAM_RATE_LIMITED",
  "requestId": "req-example-714",
  "retryable": true,
  "message": "Request not admitted; retry after the indicated delay."
}
```

Trong hợp đồng ví dụ này, server xác nhận request chưa được tiếp nhận để thực thi. Hệ thống thật phải định nghĩa rõ điều đó; chỉ nhìn mã trạng thái không đủ để suy ra mọi chi tiết xử lý nội bộ.

`Retry-After` có thể biểu diễn số giây chờ hoặc một thời điểm dạng HTTP-date. Client cần hiểu các dạng được API hỗ trợ. Khi header có giá trị hợp lệ, không retry sớm hơn mốc chờ; có thể thêm jitter để nhiều caller không thức dậy cùng lúc. Với dạng thời điểm tuyệt đối, sai lệch đồng hồ có thể ảnh hưởng kết quả tính toán.

Header báo ngân sách còn lại hoặc thời điểm reset, nếu có, là tín hiệu quan sát theo hợp đồng cụ thể. Không xem ngân sách vừa đọc như chỗ đã được giữ cho request sau, vì caller khác có thể sử dụng nó ngay lập tức.

Nếu ngân sách chỉ phục hồi vào kỳ sau hoặc cần thay đổi hợp đồng sử dụng, client không nên retry liên tục. API cần phân biệt tình huống này bằng tài liệu và mã lỗi có nghĩa rõ ràng.

### 8.3. Không tiết lộ dữ liệu nhạy cảm trong lỗi

Phản hồi nên có mã lỗi ổn định và correlation ID, nhưng tránh chứa token, secret, tên tài khoản đặc quyền không cần thiết hoặc chi tiết sử dụng của tenant khác. Với API trả secret, cả lỗi và thành công cần chính sách lưu đệm phù hợp với dữ liệu nhạy cảm.

## 9. Xây dựng client automation biết tự điều tiết

### 9.1. Giới hạn trước khi gửi

Một client tốt nên có:

1. Ngân sách tốc độ cục bộ để hạn chế request ngay tại nguồn.
2. Giới hạn số request hoặc job đang chạy đồng thời.
3. Hàng đợi có kích thước và deadline rõ ràng.
4. Backoff và jitter khi bị từ chối tạm thời.
5. Số lần thử tối đa và tổng thời gian chờ tối đa.
6. Cơ chế báo lỗi hoặc chuyển xử lý khi đã hết ngân sách retry.

Hạn mức server là lớp bảo vệ cuối cùng, không nên là cách duy nhất để client khám phá tốc độ phù hợp bằng cách gửi thật nhiều rồi nhận 429.

Nếu một automation có nhiều replica, mỗi replica giữ nguyên cùng một ngân sách cục bộ có thể làm tổng tốc độ tăng theo số replica. Cần bộ điều phối chung, chia ngân sách hoặc cách phân vùng công việc được xác định rõ.

### 9.2. Exponential backoff và jitter

Một công thức backoff đơn giản cho lần chờ thứ `k`, bắt đầu từ `k = 0`, là:

```text
trần_backoff(k) = min(trần_tối_đa, độ_trễ_gốc × 2^k)
jitter_ngẫu_nhiên = random(0, trần_backoff(k))
```

Nếu có `Retry-After` hợp lệ, có thể chọn:

```text
thời_gian_chờ = Retry-After + jitter_ngẫu_nhiên
```

Đây là một chính sách minh họa: caller chờ ít nhất thời gian server yêu cầu rồi thêm độ lệch để tránh đồng bộ. Khi không có tín hiệu chờ, dùng backoff theo chính sách đã đặt. Không coi header bị thiếu hoặc hỏng là lý do retry ngay lập tức.

Phải giới hạn cả số lần thử lẫn tổng deadline. Nếu server yêu cầu chờ lâu hơn thời gian còn lại, dừng hoặc đưa công việc về scheduler; không cắt thời gian chờ xuống thấp hơn yêu cầu rồi tiếp tục gọi.

### 9.3. Mã giả cho một logical operation

Đoạn dưới là mã giả về điều khiển luồng, không phải SDK của nhà cung cấp. Nó giả định API có hợp đồng idempotency phù hợp và phản hồi 429 xác nhận thao tác chưa được tiếp nhận:

```text
thực_hiện_thao_tác(operation, deadline):
    key = operation.idempotency_key_đã_lưu
    payload = operation.payload_cố_định

    cho attempt từ 1 đến MAX_ATTEMPTS:
        nếu thời_gian_hiện_tại >= deadline:
            trả DEADLINE_EXCEEDED

        chờ bộ_giới_hạn_cục_bộ, nhưng không vượt deadline
        lấy slot đồng_thời, nhưng không vượt deadline

        thử:
            response = gửi_request(
                payload = payload,
                idempotency_key = key,
                timeout = min(TIMEOUT_MỖI_LẦN, deadline_còn_lại)
            )
        cuối_cùng:
            trả slot đồng_thời

        nếu nhận được response thành_công:
            lưu operation_id hoặc kết_quả
            trả SUCCESS

        nếu timeout hoặc mất_kết_nối hoặc lỗi có_kết_quả_không_rõ:
            lưu trạng_thái UNKNOWN
            đối_soát theo key hoặc operation_id bằng API được hỗ trợ
            trả kết_quả_đối_soát hoặc NEEDS_RECONCILIATION

        nếu response không phải 429:
            trả lỗi cho nhánh xử_lý tương_ứng

        nếu attempt == MAX_ATTEMPTS:
            trả RETRY_BUDGET_EXHAUSTED

        delay = phân_tích_Retry_After(response)
        nếu delay thiếu hoặc không_hợp_lệ:
            delay = backoff_có_jitter(attempt)
        ngược_lại:
            delay = delay + jitter_bổ_sung(attempt)

        nếu delay >= deadline_còn_lại:
            trả DEFER_UNTIL_LATER

        chờ delay mà không giữ slot đồng_thời

    trả RETRY_BUDGET_EXHAUSTED
```

Các điểm cần giữ khi triển khai:

- Idempotency key thuộc về một logical operation, không tạo key mới cho mỗi retry.
- Payload được giữ ổn định theo hợp đồng idempotency; thay đổi yêu cầu cần operation mới.
- Không giữ slot đồng thời trong thời gian backoff nếu slot đó chỉ dùng để đo request đang bay.
- Deadline cần được kiểm tra lại sau mọi lần chờ và trước khi gửi.
- Không tự retry vô hạn 401 hoặc 403. Việc làm mới token, nếu được hỗ trợ, cũng phải có giới hạn.
- Lỗi 5xx hoặc timeout của thao tác thay đổi trạng thái cần nhánh đối soát; ví dụ trên không coi chúng mặc nhiên an toàn để gửi lại.
- Tác vụ polling phục vụ đối soát cũng phải có hạn mức và backoff riêng.

Trong triển khai thực, cần giải phóng response body và kết nối theo thư viện HTTP, xử lý hủy công việc, kiểm tra TLS và tránh chuyển thông tin xác thực qua redirect không được tin cậy. Không ghi access token, secret hoặc payload nhạy cảm vào log khi debug retry.

## 10. Rate limit không thay thế idempotency

### 10.1. Cấp quyền hai lần do timeout

Xét chuỗi sự kiện:

```text
client gửi yêu cầu cấp quyền
    → server tạo access request thành công
    → phản hồi bị mất trên mạng
    → client timeout
    → client gửi lại với key mới
    → server có thể tạo thêm một access request
```

Rate limit chỉ giảm tần suất xảy ra, không làm thao tác tự trở nên idempotent. Thiết kế cần một định danh logical operation được lưu bền ở client và cơ chế deduplication theo hợp đồng server.

Server cần xác định phạm vi key, thời gian lưu kết quả, cách xử lý cùng key nhưng khác payload và cách phản hồi khi operation vẫn đang chạy. Key phải được ràng buộc với tenant và caller phù hợp để tránh truy cập kết quả của bên khác.

Không gắn nhãn “exactly once” chỉ vì có một header idempotency. Cần kiểm tra hành vi khi tiến trình chết giữa lúc thực hiện tác động ở hệ thống đích và lúc lưu kết quả.

### 10.2. Rotation có tác động bên ngoài PAM

Nếu mật khẩu đã đổi trên máy đích nhưng phản hồi về PAM bị mất, gửi lại một lệnh rotate mới có thể gây lệch trạng thái hoặc gián đoạn ứng dụng. Khi kết quả không rõ:

1. Dùng operation ID hoặc key đã lưu để truy vấn trạng thái theo API hỗ trợ.
2. Nếu chưa xác định được, đưa vào luồng reconciliation đã được phê duyệt.
3. Giữ bằng chứng liên quan tới tài khoản, connector và lần thực hiện.
4. Chỉ tạo thao tác mới khi đã biết cách xử lý trạng thái trước đó.

Khóa theo tài khoản giúp tránh rotation đồng thời, nhưng không tự khôi phục trạng thái khi hệ thống đích đã thay đổi một phần. Cần quy trình phục hồi riêng.

## 11. Tổ chức automation để giảm số lần gọi PAM

### 11.1. Kiểm kê và polling

- Dùng phân trang với kích thước hợp lý, thay vì yêu cầu tải toàn bộ inventory trong một lần.
- Dùng cơ chế lấy thay đổi theo mốc, webhook hoặc sự kiện nếu API hỗ trợ.
- Tăng khoảng polling khi trạng thái chưa thay đổi và có deadline tổng.
- Tránh nhiều worker cùng polling một operation; dùng một bộ theo dõi rồi phân phối kết quả nội bộ.
- Dàn lịch các job định kỳ để không đồng loạt khởi chạy đầu giờ.

Batch endpoint cũng phải giới hạn số phần tử và chi phí mỗi batch. Không để một request chứa hàng chục nghìn thao tác trở thành cách vượt hạn mức request.

### 11.2. Lấy secret và cache

Không thêm cache secret chỉ để tránh 429 mà bỏ qua policy. Cache có thể kéo dài thời gian credential còn tồn tại ngoài vault và làm chậm hiệu lực thu hồi.

Nếu cơ chế lease, TTL hoặc cache được cho phép, cần xác định rõ thời hạn, lưu trữ được bảo vệ, khả năng vô hiệu hóa và hành vi khi lease hết hạn. Không gia hạn TTL cục bộ vượt policy khi PAM bị giới hạn hoặc mất kết nối.

Ưu tiên credential ngắn hạn hoặc tích hợp danh tính workload khi kiến trúc hỗ trợ và phù hợp yêu cầu. Dù dùng cơ chế nào, khả năng làm mới và thu hồi vẫn cần được tính trong kế hoạch tải.

### 11.3. Thu hồi và break-glass

Không tạo bypass limiter bằng một header như `X-Emergency: true` mà caller tùy ý đặt. Luồng khẩn cấp cần danh tính, quyền, điều kiện kích hoạt và bằng chứng riêng đã được thiết kế trước.

Ngân sách dự phòng cho revoke hoặc break-glass phải có giới hạn và khả năng quan sát. Nếu mọi caller đều có thể chọn độ ưu tiên cao, cơ chế ưu tiên sẽ mất ý nghĩa. Sau sự kiện khẩn cấp, phải rà soát truy cập, kết thúc phiên và rotate credential khi policy yêu cầu.

## 12. Quan sát và bằng chứng kiểm toán

### 12.1. Metric nên thu thập

| Metric | Câu hỏi cần trả lời |
|---|---|
| Request được tiếp nhận và bị giới hạn theo nhóm thao tác | Hạn mức đang tác động tới luồng nào? |
| Tỷ lệ 429 và khoảng thời gian kéo dài | Đây là burst ngắn hay client đang liên tục vượt ngân sách? |
| Thời gian chờ ở client và hàng đợi server | Độ trễ đến từ xử lý hay chờ ngân sách? |
| Số tác vụ đang chạy theo connector | Hạn mức request có thực sự bảo vệ downstream? |
| Lỗi, độ trễ và chế độ dự phòng của limiter | Quyết định hạn mức có còn đáng tin cậy? |
| Retry amplification | Một logical operation tạo ra bao nhiêu lần gọi HTTP? |
| Thời gian thu hồi quyền và tỷ lệ thành công | Luồng bảo vệ có đáp ứng khi hệ thống bận? |

Không gắn token, secret hay mọi resource ID tùy ý làm nhãn metric. Điều đó vừa có thể làm lộ dữ liệu vừa tạo lượng time series quá lớn. Dùng nhãn có tập giá trị được kiểm soát; chi tiết phục vụ điều tra có thể đặt trong log bảo vệ phù hợp.

### 12.2. Phân biệt request log và audit của thao tác

Request bị chặn trước admission chưa chắc tạo ra một thao tác PAM. Log kỹ thuật nên ghi được quyết định limiter và correlation ID; audit nghiệp vụ ghi sự kiện tạo quyền, mở phiên, rotate hoặc revoke thực sự diễn ra.

Các trường hữu ích có thể gồm:

- Thời điểm, request ID, operation ID nếu có.
- Tenant và caller đã được xác thực theo quy tắc bảo vệ dữ liệu.
- Nhóm thao tác, policy limiter và phiên bản cấu hình.
- Quyết định cho phép hoặc từ chối; phạm vi ngân sách gây giới hạn.
- Số lần retry và trạng thái kết thúc của logical operation.

Idempotency key có thể cần được che hoặc băm theo policy; không mặc định đưa nguyên giá trị vào mọi log. Với lưu lượng lạm dụng lớn, phải bảo vệ năng lực ghi log, có bộ đếm và cảnh báo tương ứng. Không âm thầm loại bỏ các bằng chứng nghiệp vụ bắt buộc để giảm tải.

## 13. Chọn và điều chỉnh hạn mức

Không có một con số request/giây phù hợp cho mọi PAM. Có thể xây dựng chính sách theo quy trình sau:

1. **Liệt kê luồng nghiệp vụ:** kiểm kê, tạo yêu cầu, approval, lấy credential, tạo phiên, rotate và thu hồi.
2. **Đo chi phí thực:** độ trễ, CPU, truy vấn, tải connector, số phiên và dung lượng audit.
3. **Xác định đỉnh hợp lệ:** deployment đồng loạt, thay ca, rotation định kỳ, phục hồi sau gián đoạn.
4. **Giữ dự phòng:** dành năng lực cho biến động và các luồng bảo vệ đã xác định.
5. **Đặt nhiều giới hạn:** tốc độ, burst, số việc đồng thời, số việc chờ và deadline.
6. **Kiểm thử với phân bố tải thực tế:** nhiều tenant, nhiều replica, chênh lệch thời gian xử lý.
7. **Triển khai dần:** quan sát tác động, điều chỉnh có ghi nhận và có phương án quay lại.

Chế độ chỉ quan sát giúp ước lượng số request có thể bị từ chối, nhưng bản thân nó không bảo vệ được hệ thống. Cần giữ lớp kiểm soát tải hiện hữu trong giai đoạn đánh giá.

Nếu một nhóm liên tục chạm hạn mức, trước hết phân biệt nhu cầu hợp lệ với lỗi vòng lặp, polling dư thừa hoặc credential bị lạm dụng. Tăng hạn mức chỉ hợp lý khi năng lực downstream và mô hình quyền vẫn đáp ứng.

## 14. Kịch bản thực hành trong môi trường thử nghiệm

### 14.1. Bối cảnh

Một nền tảng nội bộ có ba automation:

- `inventory-bot`: đọc danh sách tài khoản đặc quyền.
- `deployment-bot`: tạo access request JIT cho pipeline.
- `incident-bot`: kết thúc phiên và thu hồi quyền trong sự cố.

Ba bot dùng danh tính riêng, quyền riêng và chạy trên cùng hạ tầng egress. Mục tiêu là kiểm tra inventory không làm nghẽn cấp quyền và revoke, đồng thời retry của deployment không tạo yêu cầu trùng.

Chỉ thực hành trên môi trường được giao quyền với dữ liệu và tài khoản thử. Không kiểm thử tải bằng tài khoản quản trị hoặc secret production.

### 14.2. Chuẩn bị

- Đặt cấu hình minh họa cho inventory: token bucket `B = 20`, `r = 5/giây` theo caller và tenant.
- Đặt giới hạn nhỏ cho số access request đang chờ và số request đồng thời.
- Tạo đường xử lý revoke có tài nguyên dự phòng, vẫn kiểm tra quyền của `incident-bot`.
- Bật metric, request ID và audit ở mức cần thiết.
- Chuẩn bị operation ID, ticket giả lập và idempotency key cho từng logical operation.

### 14.3. Các phép thử và kết quả cần quan sát

| Phép thử | Kết quả cần kiểm tra |
|---|---|
| Gửi một burst vượt dung lượng bucket | Request dư bị giới hạn theo chính sách; không làm tràn hàng đợi. |
| Duy trì tải cao sau burst | Tốc độ được tiếp nhận tiến về ngân sách nạp; client giảm tốc. |
| Hai caller sau cùng NAT | Có thể phân biệt ngân sách caller; lớp biên vẫn hoạt động theo thiết kế. |
| Một caller đổi access token | Ngân sách danh tính ổn định không bị reset ngoài ý muốn. |
| Scale từ một lên nhiều API instance | Hạn mức tổng giữ đúng cam kết hoặc đúng sai số đã công bố. |
| Nhiều replica retry sau 429 | Không hình thành làn sóng retry đồng bộ; mọi replica tuân thủ deadline. |
| Timeout sau khi server tạo access request | Đối soát được yêu cầu cũ; không tự tạo thêm yêu cầu bằng key mới. |
| Inventory liên tục chạm hạn mức | Revoke vẫn được phục vụ trong mục tiêu đã đặt. |
| Limiter hoặc connector lỗi | Hành vi dự phòng đúng policy; không bỏ qua kiểm tra quyền. |
| Một batch rất lớn | Bị chặn bởi giới hạn kích thước hoặc chi phí, không vượt qua bằng một request. |

Để kiểm thử thời gian, cần chấp nhận biên đo và sai số của cơ chế đã chọn. Không khẳng định thất bại chỉ vì một cửa sổ một giây có hơn năm request khi đang dùng token bucket cho phép burst.

### 14.4. Bằng chứng cần lưu

Lưu cấu hình limiter và phiên bản, mô tả tải thử, thời điểm bắt đầu/kết thúc, số logical operation, số HTTP attempt, tỷ lệ 429, độ trễ, số tác vụ đồng thời và kết quả revoke. Liên kết các lần thử của cùng operation bằng ID phù hợp, không đưa token hoặc secret vào báo cáo.

Kết thúc thử nghiệm bằng việc thu hồi quyền thử, kết thúc phiên còn mở và dọn credential theo policy của môi trường.

## 15. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ giới hạn theo IP | Caller sau NAT ảnh hưởng nhau, danh tính phân tán dễ vượt hạn mức. | Kết hợp lớp biên với tenant/caller đã xác minh. |
| Cùng hạn mức trên mỗi instance nhưng gọi là toàn cục | Scale-out làm tăng lượng request được phép. | Dùng ngân sách chia sẻ hoặc cơ chế phân bổ có giới hạn tổng. |
| Retry ngay khi nhận 429 | Tăng tải, kéo dài thời gian bị giới hạn. | Tôn trọng tín hiệu chờ, thêm jitter và giới hạn tổng retry. |
| Giữ slot trong lúc backoff | Hàng đợi client bị chiếm bởi công việc đang ngủ. | Trả slot request sau mỗi lần gọi, điều phối lại khi thử tiếp. |
| Tạo idempotency key mới mỗi lần thử | Một logical operation có thể tạo nhiều tác động. | Lưu và tái sử dụng key theo hợp đồng API. |
| Chỉ giới hạn HTTP request tạo job | Tác vụ dài làm quá tải connector. | Giới hạn cả job đang chạy và hàng đợi. |
| Chia chung ngân sách inventory và revoke | Tải đọc làm chậm ứng phó sự cố. | Tách nhóm và dành tài nguyên bảo vệ đã kiểm thử. |
| Tăng TTL cache secret khi bị giới hạn | Credential tồn tại ngoài policy và chậm thu hồi. | Tuân thủ lease/TTL và xử lý hết hạn rõ ràng. |
| Tin header tenant hoặc emergency từ client | Caller tự đổi khóa hạn mức hoặc ưu tiên. | Suy danh tính và quyền từ ngữ cảnh được xác minh. |
| Limiter lỗi thì cho qua mọi thứ | Mất kiểm soát đúng lúc hệ thống suy giảm. | Định nghĩa chế độ lỗi cho từng nhóm thao tác. |

## 16. Tự kiểm tra kiến thức

**Câu 1. Vì sao hạn mức 10 request/giây chưa bảo vệ được hệ thống rotation?**

Vì một request có thể tạo job chạy lâu. Cần kiểm soát số job đang chạy, hàng đợi, tài nguyên đích và năng lực connector, ngoài tốc độ tiếp nhận.

**Câu 2. Token bucket có tốc độ nạp 5 token/giây và dung lượng 20 có cho phép 20 request gần như cùng lúc không?**

Có thể, khi bucket đầy và mỗi request tốn một token, nếu không có giới hạn khác. Tốc độ nạp mô tả năng lực duy trì; dung lượng bucket mô tả burst được tích lũy.

**Câu 3. Client còn deadline hai giây nhưng server yêu cầu chờ năm giây. Có nên chờ hai giây rồi retry không?**

Không. Client nên kết thúc lần thực hiện hoặc chuyển công việc về scheduler theo policy. Deadline ngắn không cho phép retry sớm hơn tín hiệu chờ hợp lệ của server.

**Câu 4. Tại sao timeout của POST tạo phiên cần đối soát?**

Vì phiên có thể đã được tạo dù client không nhận phản hồi. Cần operation ID, idempotency key hoặc cơ chế tra cứu được API hỗ trợ để xác định kết quả, tránh tạo phiên trùng.

**Câu 5. Vì sao phải kiểm thử revoke khi inventory đang bị giới hạn?**

Để xác minh luồng ứng phó sự cố có tài nguyên và đường xử lý đáp ứng mục tiêu trong điều kiện tải cao, thay vì chỉ hoạt động khi hệ thống rảnh.

**Câu 6. Một request được limiter chấp nhận có đủ điều kiện lấy secret không?**

Không. Request vẫn phải đáp ứng xác thực, phân quyền, điều kiện policy và các yêu cầu audit tương ứng.

## 17. Điểm cần ghi nhớ

Rate limit PAM API cần gắn với danh tính đã xác minh, loại thao tác và năng lực của cả chuỗi xử lý. Kết hợp tốc độ, burst, concurrency, hàng đợi và deadline giúp kiểm soát tải thực tế hơn một con số request/giây duy nhất.

Automation phải tự điều tiết, hiểu 429, chờ theo hợp đồng API và giữ ngân sách retry hữu hạn. Với thao tác cấp quyền, tạo phiên hoặc rotate, idempotency và đối soát kết quả là điều kiện để retry không tạo thêm rủi ro.

Chất lượng của chính sách được chứng minh bằng khả năng hoạt động dưới tải: các tenant được phục vụ theo cam kết, connector không bị quá tải, quyền có thể thu hồi đúng lúc và bằng chứng kiểm toán vẫn được bảo vệ.
