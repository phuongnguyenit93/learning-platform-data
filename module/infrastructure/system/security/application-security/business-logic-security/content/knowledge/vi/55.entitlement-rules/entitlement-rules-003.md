# Entitlement expiration: thực thi thời hạn quyền sử dụng an toàn

## 1. Hết hạn là một điều kiện nghiệp vụ

Trong chương **Entitlement Rules**, entitlement là một quyền sử dụng được cấp cho một chủ thể trong một phạm vi cụ thể. Ví dụ: một thành viên được xuất báo cáo nâng cao đến hết kỳ thuê bao, một khách hàng có quyền dùng thử trong bảy ngày hoặc một đối tác được tải một bộ dữ liệu trong khoảng thời gian được phê duyệt.

Entitlement expiration là việc quyền đó không còn cho phép một hành động sau mốc thời gian đã xác định. Đây là điều kiện phải kiểm tra tại nơi thực thi hành động, không chỉ là một tác vụ định kỳ đổi trạng thái trong cơ sở dữ liệu.

Ví dụ xuyên suốt:

~~~text
Tenant: ACME
Chủ thể: thành viên An
Tính năng: REPORT_EXPORT
Phạm vi: dự án P1
Có hiệu lực từ: 2026-11-01T00:00:00Z
Hết hiệu lực tại: 2026-12-01T00:00:00Z
Nguồn cấp: quyền của kỳ thuê bao hiện tại
~~~

Vào đúng `2026-12-01T00:00:00Z`, An không còn được bắt đầu một lần xuất mới theo quyền này. Một worker dọn dữ liệu chưa chạy hoặc một cache vẫn chứa trạng thái `ACTIVE` không được kéo dài quyền.

Bài học tập trung vào:

- Bất biến thời gian, phạm vi và nguồn của quyền.
- Kiểm tra quyền theo đối tượng thay vì chỉ theo role.
- Phân biệt thời hạn nghiệp vụ với TTL của cache, token hoặc dữ liệu.
- Gia hạn và thu hồi khi có yêu cầu đồng thời hoặc sự kiện trùng.
- Chính sách cho transaction, tác vụ dài và nội dung đã tạo.
- Kiểm thử các cách khai thác khoảng trống tại ranh giới hết hạn.

## 2. Mô hình một quyền có thời hạn

### 2.1. Quyền luôn đi cùng chủ thể và phạm vi

Một grant, tức bản ghi cấp quyền, cần mô tả ít nhất:

| Thành phần | Ý nghĩa |
| --- | --- |
| Tenant | Ranh giới tổ chức sở hữu quyền |
| Subject | Người dùng, nhóm hoặc service được cấp |
| Feature/action | Hành động hoặc tính năng được phép |
| Resource scope | Một tài nguyên, một tập tài nguyên hoặc toàn tenant được định nghĩa rõ |
| Source | Nguồn cấp có thẩm quyền: thuê bao, hợp đồng, phê duyệt hoặc chương trình |
| Validity | Thời điểm bắt đầu, kết thúc hoặc chế độ không giới hạn thời gian được cho phép |
| State | Trạng thái cấp, hết hạn hoặc thu hồi |
| Revision | Phiên bản dùng phát hiện thay đổi |
| Issuance reference | Định danh nghiệp vụ của lần cấp |

Một quyền `REPORT_EXPORT` cho dự án P1 không tự cho phép xuất dự án P2. Một quyền còn hạn của tenant A không được dùng cho tài nguyên tenant B.

Role quản trị cũng không mặc nhiên kéo dài thời hạn entitlement. Quyền quản lý việc cấp và quyền sử dụng tính năng có thể là hai chính sách khác nhau.

### 2.2. Dùng khoảng thời gian nửa mở

Quy ước tham chiếu:

~~~text
valid_from <= t < expires_at
~~~

Điểm bắt đầu được bao gồm; điểm kết thúc bị loại trừ.

~~~text
t < valid_from              → chưa có hiệu lực
valid_from <= t < expires_at → có thể được sử dụng nếu đủ điều kiện khác
t >= expires_at             → hết hạn
~~~

Quy ước này tránh việc hai kỳ liền nhau cùng nhận quyền ở một thời điểm ranh giới. Nó cũng giúp kiểm thử chính xác tại mốc hết hạn.

Nếu giao diện ghi “dùng đến hết ngày 30”, server phải chuyển quy ước hiển thị đó thành một instant cụ thể theo múi giờ đã công bố. Không lưu một chuỗi ngày mơ hồ rồi để từng service tự diễn giải.

Ví dụ một chương trình kết thúc lúc bắt đầu ngày kế tiếp theo múi giờ kinh doanh phải được chuyển sang UTC bằng quy tắc múi giờ tương ứng. Đừng mặc định mọi ngày địa phương đều là cùng một khoảng 24 giờ.

### 2.3. Hết hạn không phải điều kiện duy nhất

Với một grant `g` và thời điểm quyết định `t`:

~~~text
grant_valid(g, t) =
    đúng tenant, subject, action và resource scope
    AND trạng thái cho phép
    AND valid_from <= t
    AND (grant được phép vô thời hạn OR t < expires_at)
    AND nguồn cấp còn đủ điều kiện
    AND không bị thu hồi
~~~

Quyết định cuối cùng còn cần quyền trên đối tượng, trạng thái thành viên và các giới hạn sử dụng:

~~~text
allow(action, resource, t) =
    actor được xác thực
    AND actor được phép thao tác resource
    AND không có điều kiện chặn áp dụng
    AND có grant hợp lệ hoặc tổ hợp grant hợp lệ theo chính sách
    AND còn hạn mức nếu hành động tiêu thụ hạn mức
~~~

Một tenant bị đình chỉ có thể bị chặn dù grant riêng còn hạn. Một người đã bị xóa khỏi dự án không được dùng grant cũ để tiếp tục truy cập dự án.

### 2.4. Nhiều nguồn cấp không được gộp tùy ý

Giả sử một người có hai grant độc lập cho cùng tính năng và phạm vi:

~~~text
Grant A: còn hiệu lực đến ngày 10
Grant B: còn hiệu lực đến ngày 20
~~~

Nếu chính sách cho phép **bất kỳ một grant độc lập hợp lệ**, hết hạn A không làm B mất hiệu lực. Không dùng một worker xử lý A để tắt một cờ chung `can_export=false` rồi vô hiệu hóa nhầm B.

Ngược lại, nếu hành động đòi hỏi đồng thời quyền tính năng và tư cách thành viên dự án, thời hạn khả dụng bị giới hạn bởi cả hai. Không lấy thời hạn lớn nhất để vượt qua một điều kiện bắt buộc đã hết.

Cần phân biệt rõ:

- Quan hệ thay thế: một trong các nguồn hợp lệ là đủ.
- Quan hệ phụ thuộc: mọi điều kiện bắt buộc đều phải đúng.
- Điều kiện phủ quyết: đình chỉ hoặc cấm truy cập có thể chặn các grant còn lại.

Không có một phép `MAX(expires_at)` phù hợp cho mọi mô hình entitlement.

## 3. Business invariants cần bảo vệ

### 3.1. Không dùng quyền ngoài khoảng hiệu lực

Với chính sách kiểm tra tại thời điểm bắt đầu hành động:

~~~text
Một hành động mới được chấp nhận
  ⇒ Có bằng chứng quyền hợp lệ tại thời điểm quyết định.
~~~

Cụ thể, grant có hạn không được cho phép hành động khi `decision_time >= effective_end`.

`effective_end` là giới hạn sau khi xét mọi điều kiện thời gian bắt buộc. Với các điều kiện cùng phải đúng, nó có thể là:

~~~text
effective_end = min(
    grant.expires_at,
    source.allowed_until,
    membership.allowed_until,
    approval.allowed_until
)
~~~

Chỉ lấy các giới hạn thực sự áp dụng; một thành phần không có thời hạn không được diễn giải thành ngày 0 hoặc làm toàn bộ phép tính thành “vô thời hạn”.

Nguồn có thời gian gia hạn ân hạn phải cung cấp `allowed_until` theo chính sách ân hạn đã được duyệt. Không cộng tùy ý vài phút vào kết quả của mỗi service.

### 3.2. Không biến dữ liệu thiếu thành quyền vĩnh viễn

Trường `expires_at = null` chỉ được phép nếu bản ghi tuyên bố rõ chế độ `PERPETUAL` và nguồn cấp có thẩm quyền được phép cấp quyền đó.

Các trường hợp sau phải bị từ chối hoặc đưa vào trạng thái xử lý lỗi:

- Grant có chế độ hữu hạn nhưng thiếu ngày hết hạn.
- Ngày hết hạn không sau ngày bắt đầu.
- Không tìm được nguồn cấp bắt buộc.
- Không xác định được tenant hoặc phạm vi.
- Không đọc được phiên bản chính sách cần thiết.

Không dùng quy tắc “không parse được ngày thì bỏ qua kiểm tra”. Không coi một sự cố đọc nguồn dữ liệu là bằng chứng rằng nguồn còn hiệu lực.

Nếu sản phẩm hỗ trợ sử dụng ngoại tuyến, quyền ngoại tuyến phải được định nghĩa trước bằng phạm vi và thời hạn cụ thể, không phát sinh bằng nhánh xử lý lỗi tùy tiện.

### 3.3. Gia hạn không được nhân bản theo số lần retry

Một sự kiện gia hạn chỉ tạo một hiệu ứng. Ví dụ cùng hóa đơn hoặc phê duyệt kỳ mới được gửi lại không được kéo dài thời hạn thêm lần nữa.

Sai:

~~~text
Mỗi lần nhận event:
  expires_at = thời gian hiện tại + 30 ngày
~~~

Cùng event được phát lại ở ngày khác sẽ tạo hạn mới khác. Một kẻ có khả năng gọi lại luồng có thể biến quyền hữu hạn thành quyền trượt vô hạn.

Đúng hơn là dùng kỳ hoặc khoảng đã được nguồn có thẩm quyền xác định, cùng định danh nghiệp vụ duy nhất của lần gia hạn. Nếu cần cộng thời lượng, chỉ thực hiện một lần theo command ID bền vững, với mốc neo được quy định rõ.

### 3.4. Hết hạn không xóa bằng chứng đã nhận quyền lợi

Nếu trial chỉ được cấp một lần, hết hạn trial không được xóa luôn dấu đã sử dụng để người dùng đăng ký lại cùng quyền lợi.

Dữ liệu phục vụ kiểm tra hiệu lực, lịch sử kiểm toán và bằng chứng chống cấp lặp có vòng đời khác nhau. Một bản ghi không còn cho phép sử dụng vẫn có thể cần được giữ để ngăn phát lại sự kiện cấp quyền.

Xóa grant không phải một cách chung để thực hiện expiration.

## 4. Phân biệt thời hạn nghiệp vụ và TTL

### 4.1. Bốn loại thời gian thường bị nhầm

| Loại thời gian | Câu hỏi nó trả lời | Không tự bảo đảm |
| --- | --- | --- |
| Thời hạn entitlement | Chủ thể được bắt đầu hoặc tiếp tục hành động đến lúc nào? | Dữ liệu sẽ bị xóa đúng lúc |
| TTL cache | Bản sao được giữ hoặc dùng lại bao lâu? | Quyền còn hiệu lực trong toàn TTL |
| Thời hạn token | Token được chấp nhận trong khoảng nào? | Grant phía sau chưa bị thu hồi |
| TTL lưu trữ/dọn dữ liệu | Khi nào dữ liệu đủ điều kiện bị xóa? | Mọi request sau đó đều bị chặn |

Một cache còn bản ghi grant không có nghĩa grant còn quyền. Một token chưa hết hạn không có nghĩa gói thuê bao phía sau vẫn đang hoạt động.

TTL của cơ chế lưu trữ thường không nên được dùng làm đồng hồ quyết định nghiệp vụ. Handler cần so sánh thời gian với điều kiện có hiệu lực đã lưu.

### 4.2. Sliding cache không được kéo dài grant

Giả sử grant hết lúc 12:00, cache TTL là 10 phút:

~~~text
11:58: Cache kết quả allow.
12:03: Request mới đọc lại cache allow.
~~~

Nếu cache chỉ lưu boolean và tin TTL, request lúc 12:03 có thể được cấp quyền sai.

Một bản cache cho quyết định dương nên mang ít nhất:

~~~text
tenant + subject + action + resource scope
grant/source revision
evaluated_at
effective_end
policy version cần thiết
~~~

Khi dùng lại cache, vẫn phải kiểm tra `now < effective_end`. Tuổi cache tối đa không được vượt thời hạn quyền còn lại:

~~~text
cache_lifetime <= min(
    cache_policy_limit,
    effective_end - decision_time
)
~~~

Nếu thời gian còn lại không dương, từ chối quyền và không biến TTL bằng 0 thành một cách lưu vô thời hạn theo quy ước của thư viện.

Cache dạng sliding, được gia hạn mỗi lần truy cập, chỉ thay đổi tuổi bản sao; nó không được sửa `effective_end` của entitlement.

### 4.3. Thời hạn token phải nằm trong quyền được ủy nhiệm

Nếu token mang một quyền có hạn:

~~~text
token.expires_at <= effective_end của quyền đã được ủy nhiệm
~~~

Token còn phải bị giới hạn bởi subject, tenant, audience và phạm vi tài nguyên thích hợp. Nếu token biểu diễn thời gian ở độ phân giải thấp hơn, cách làm tròn không được đẩy hạn quyền sang sau mốc kết thúc nghiệp vụ.

Thời hạn token ngắn không tự giải quyết thu hồi tức thời. Nếu cần thu hồi trước hạn, phải có kiểm tra trạng thái hoặc revision hiện hành, cơ chế vô hiệu hóa hoặc một mô hình ủy nhiệm được thiết kế cho yêu cầu đó.

Một khoảng cho phép lệch đồng hồ khi kiểm tra token cũng không nên âm thầm biến thành ân hạn của entitlement. Chính sách phải nói rõ chấp nhận điều gì ở lớp xác thực và điều gì ở lớp quyền nghiệp vụ.

## 5. Chọn thời điểm kiểm tra quyền

### 5.1. Ba chính sách khác nhau

| Chính sách | Quy tắc | Ví dụ |
| --- | --- | --- |
| Admission | Phải còn quyền khi hành động được chấp nhận | Nhận một tác vụ xử lý đã cam kết |
| Execution/delivery | Phải còn quyền khi tác vụ bắt đầu hoặc kết quả được giao | Xuất và tải báo cáo nhạy cảm |
| Continuous | Cần quyền tại các điểm kiểm tra trong quá trình sử dụng | Phiên truyền nội dung hoặc tác vụ chạy dài |

Không được chỉ ghi “kiểm tra hết hạn” mà không chọn điểm kiểm tra. Cùng một job có thể được nhận trước hạn nhưng thực thi sau hạn; đúng hay sai phụ thuộc chính sách đã công bố.

Trong ví dụ của bài:

- Tạo một lệnh xuất cần quyền hợp lệ tại thời điểm quyết định chấp nhận.
- Worker phải kiểm tra lại khi bắt đầu xử lý.
- Tải kết quả là một hành động mới, cần kiểm tra quyền đọc tài nguyên và chính sách truy cập kết quả hiện tại.
- Một lần retry không được tạo một job mới sau hạn chỉ vì job trước được tiếp nhận hợp lệ.

Đây là chính sách tham chiếu. Nếu sản phẩm cho phép hoàn tất job đã được tiếp nhận trước hạn, hãy lưu rõ cam kết đó thay vì để worker tự suy diễn.

### 5.2. Không hứa điều kiện mà transaction không bảo đảm

Một transaction có thể kiểm tra quyền lúc 11:59:59.900 và commit lúc 12:00:00.100. Kiểm tra dưới khóa không biến điều đó thành “commit trước hạn”.

Nếu chính sách là admission, thời điểm quyết định được ghi nhận trước hạn có thể đủ. Nếu yêu cầu là hoàn tất một hành động trước một deadline, phải thiết kế một giao thức và giới hạn thực thi đáp ứng yêu cầu đó; một câu `if (now < expiresAt)` trước khi làm việc không tự chứng minh thời điểm hoàn tất.

Cũng cần xác định quan hệ với thu hồi: một hành động đã được chấp nhận trước khi lệnh thu hồi thắng khóa có thể được phép tiếp tục theo chính sách admission. Nếu muốn chặn cả hành động chưa hoàn tất, phải có cơ chế hủy hoặc kiểm tra lại phù hợp.

### 5.3. Tác vụ dài không được dùng quyền của worker để bỏ qua người yêu cầu

Job nên lưu:

- Tenant, subject và resource ban đầu.
- Action được yêu cầu.
- Grant hoặc quyết định quyền liên quan.
- Revision và thời điểm được chấp nhận.
- Chính sách thực thi và deadline nếu có.
- Định danh nghiệp vụ chống lặp.

Worker có service identity để vận hành hàng đợi, nhưng không mặc nhiên có quyền sử dụng thay mọi người. Nó cần đánh giá đúng quyền được ủy nhiệm hoặc cam kết nghiệp vụ của job.

Nếu job chờ hàng đợi đến sau thời hạn và chính sách execution không còn cho phép, worker phải từ chối hoặc kết thúc theo trạng thái phù hợp. Không tự gia hạn để “giúp job hoàn thành”.

### 5.4. Kết quả đã tạo và link tải là một lớp quyền riêng

Một file được tạo trước hạn không mặc nhiên được công khai mãi sau đó. Cần quy định:

- Ai được xem hoặc tải.
- Quyền tải phụ thuộc entitlement hiện tại hay quyền lưu trữ kết quả đã được mua.
- Link tải hết hạn lúc nào.
- Có thể thu hồi link trước hạn hay không.
- Điều kiện trên tenant và tài nguyên có tiếp tục được kiểm tra không.

Nếu dùng link ký sẵn không gọi lại hệ thống quyền khi tải, thời hạn link phải nằm trong quyền ủy nhiệm phù hợp. Nếu yêu cầu thu hồi tức thời mà cơ chế link không hỗ trợ, cần đổi cách giao nội dung; giảm TTL chỉ làm nhỏ cửa sổ, không tạo khả năng thu hồi ngay.

Không thể lấy lại những byte người dùng đã nhận hợp lệ trước đó bằng cách cho grant hết hạn. Expiration kiểm soát các hành động và lần truy cập tiếp theo theo chính sách.

## 6. Trạng thái, nguồn cấp và gia hạn

### 6.1. Trạng thái vật chất hóa không thay phép so thời gian

Một mô hình đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE: Cấp quyền có nguồn hợp lệ
    ACTIVE --> EXPIRED: Đến hạn và được ghi nhận
    ACTIVE --> REVOKED: Thu hồi trước hạn
    EXPIRED --> [*]
    REVOKED --> [*]
~~~

Trạng thái `ACTIVE` chỉ cho biết grant chưa được vật chất hóa thành trạng thái kết thúc. Predicate thời gian vẫn có thể nói “chưa bắt đầu” hoặc “đã hết hạn”.

Nếu cần giao diện tách rõ chưa hiệu lực, có thể thêm trạng thái hoặc suy nhãn từ `valid_from`. Không để một worker kích hoạt chạy trễ là điều kiện duy nhất làm quyền bắt đầu.

Trong mô hình tham chiếu:

- Có thể gia hạn một grant còn hiệu lực bằng cập nhật có kiểm soát và tăng revision.
- Grant đã kết thúc không tự sống lại vì sự kiện cũ.
- Cấp cho kỳ mới sau khi grant đã hết hạn nên có grant/term identity mới.
- Grant đã thu hồi không được khôi phục chỉ vì một thông báo gia hạn; muốn cấp lại phải qua quyết định mới có thẩm quyền.

Một sản phẩm có thể chọn giữ cùng ID qua các kỳ, nhưng khi đó cần term/generation riêng để phân biệt quyền mới với bằng chứng và sự kiện của kỳ cũ.

### 6.2. Gia hạn chỉ từ nguồn có thẩm quyền

Client có thể gửi yêu cầu gia hạn nhưng không được tự xác nhận:

~~~json
{
  "expiresAt": "2099-01-01T00:00:00Z",
  "paid": true,
  "sourceStatus": "ACTIVE",
  "skipApproval": true
}
~~~

Server phải xác minh nguồn, kỳ, khoản thanh toán hoặc phê duyệt tương ứng theo mô hình sản phẩm. Nội dung được duyệt phải khớp subject, feature, resource scope và khoảng thời gian được cấp.

Với sự kiện từ hệ thống ngoài, xác thực nguồn là điều kiện cần. Còn phải đối chiếu event với đối tượng, tenant, kỳ và trạng thái có thẩm quyền. Một event thật của kỳ trước không chứng minh kỳ tiếp theo đã được thanh toán.

### 6.3. Chống sự kiện đến sai thứ tự

Ví dụ:

~~~text
Grant revision 4 hết hạn lúc T1.
Gia hạn hợp lệ tạo revision 5, hết hạn lúc T2 > T1.
Worker cũ vẫn cầm công việc "expire revision 4 tại T1".
~~~

Worker cũ không được đánh dấu revision 5 hết hạn theo công việc đó. Cần kiểm tra revision và mốc kết thúc kỳ vọng.

Tương tự, một event gia hạn cũ không được ghi đè mốc kết thúc mới hoặc khôi phục grant đã bị thu hồi. Nếu nguồn có revision/sequence có nghĩa, dùng nó theo đúng phạm vi. Không lấy thời gian nhận webhook làm thứ tự nghiệp vụ.

Nếu nguồn không cung cấp thứ tự đáng tin, có thể cần truy vấn lại trạng thái có thẩm quyền và đối soát, thay vì đoán theo event nào đến sau.

### 6.4. Ân hạn phải là quyền được mô hình hóa

Nếu sản phẩm có grace period, hãy định nghĩa:

- Trạng thái nào được hưởng.
- Tính năng nào vẫn được dùng.
- Thời hạn tối đa và mốc neo.
- Ai có quyền gia hạn hoặc kết thúc.
- Quan hệ với đình chỉ, gian lận và thu hồi.
- Có được nhận lại ân hạn nhiều lần qua retry hoặc thay gói không.

Không triển khai “nếu kiểm tra thất bại thì cho thêm 24 giờ kể từ bây giờ”. Mỗi lần gọi sẽ tạo một deadline mới và có thể giữ quyền vô hạn.

## 7. Mô hình dữ liệu tối thiểu

Lược đồ PostgreSQL dưới đây minh họa một grant cho một subject. Nó chưa bao gồm bảng thành viên, nguồn cấp, chính sách, lịch sử gia hạn hoặc audit:

~~~sql
CREATE TABLE entitlement_grant (
    tenant_id UUID NOT NULL,
    grant_id UUID NOT NULL,
    subject_id UUID NOT NULL,
    feature_code TEXT NOT NULL,
    scope_kind TEXT NOT NULL
        CHECK (scope_kind IN ('TENANT', 'RESOURCE')),
    resource_id UUID,
    source_id UUID NOT NULL,
    issuance_ref UUID NOT NULL,
    validity_kind TEXT NOT NULL
        CHECK (validity_kind IN ('BOUNDED', 'PERPETUAL')),
    valid_from TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    state TEXT NOT NULL
        CHECK (state IN ('ACTIVE', 'EXPIRED', 'REVOKED')),
    revision BIGINT NOT NULL CHECK (revision > 0),
    PRIMARY KEY (tenant_id, grant_id),
    UNIQUE (tenant_id, issuance_ref),
    CHECK (
        (scope_kind = 'TENANT' AND resource_id IS NULL)
        OR
        (scope_kind = 'RESOURCE' AND resource_id IS NOT NULL)
    ),
    CHECK (
        (validity_kind = 'BOUNDED'
            AND expires_at IS NOT NULL
            AND expires_at > valid_from)
        OR
        (validity_kind = 'PERPETUAL' AND expires_at IS NULL)
    )
);

CREATE INDEX entitlement_expiry_candidates
ON entitlement_grant (expires_at, tenant_id, grant_id)
WHERE state = 'ACTIVE' AND validity_kind = 'BOUNDED';
~~~

`issuance_ref` ở đây định danh một lần cấp cho một grant. Nếu một quyết định cấp nhiều dòng, mỗi dòng cần identity riêng hoặc một khóa ghép tương ứng.

Khóa ngoại ghép trong lược đồ đầy đủ phải giữ subject, source và resource trong phạm vi tenant phù hợp. Không coi việc bản ghi chứa cùng một `tenant_id` do client gửi là bằng chứng quan hệ đó đúng.

Constraint bảo vệ miền dữ liệu trên hàng, nhưng không tự chứng minh nguồn được phép cấp quyền vô thời hạn hoặc actor được gia hạn. Các điều kiện đó thuộc lệnh nghiệp vụ và dữ liệu có thẩm quyền.

## 8. Kiểm tra quyền tại nơi tạo hiệu ứng

### 8.1. Kiểm tra ở controller chưa đủ

Luồng không an toàn:

~~~text
Controller thấy grant còn hạn.
Request chờ một khóa hoặc chờ hàng đợi.
Grant hết hạn hoặc bị thu hồi.
Service vẫn tạo hiệu ứng theo kết quả kiểm tra cũ.
~~~

Kết quả kiểm tra phải gắn với điểm quyết định nghiệp vụ. Với một hành động cục bộ cần transaction, quyền và dữ liệu mà hành động dựa vào phải được đọc dưới cơ chế đồng bộ phù hợp.

Một cách triển khai dùng:

1. Kiểm tra xác thực và tenant trước transaction.
2. Khóa các trạng thái nền như tenant, thành viên và nguồn cấp theo giao thức chung.
3. Khóa hoặc kiểm tra revision của các grant liên quan.
4. Khóa tài nguyên hoặc bộ đếm hạn mức sắp thay đổi.
5. Lấy thời điểm quyết định sau khi chờ các khóa cần thiết.
6. Đánh giá quyền và thực hiện thay đổi trong cùng transaction.
7. Ghi bằng chứng quyết định cùng hiệu ứng rồi commit.

Thứ tự khóa cần ổn định và được dùng bởi cả cấp quyền, gia hạn, thu hồi, thay đổi nguồn và thực thi tài nguyên. Chỉ khóa grant không ngăn một transaction khác đình chỉ nguồn ở bảng khác nếu hai luồng không có điểm đồng bộ tương thích.

Đối với điều kiện phủ quyết như đình chỉ tenant, cần đọc và bảo vệ bản ghi có thẩm quyền tương ứng; không chỉ khóa những grant dương tìm được.

### 8.2. Lấy thời gian sau khi chờ khóa

Trong PostgreSQL, `CURRENT_TIMESTAMP` gắn với thời điểm bắt đầu transaction. Nếu transaction đã chờ khóa lâu, nó có thể không đại diện cho thời điểm ra quyết định sau khi lấy được khóa.

Với chính sách kiểm tra ở thời điểm hiện tại sau khi chờ, có thể lấy một giá trị từ `clock_timestamp()` rồi dùng nhất quán cho quyết định đó:

~~~sql
-- Các khóa nghiệp vụ liên quan đã được lấy theo giao thức chung.
SELECT clock_timestamp() AS decision_time;
~~~

Thời gian này do server/cơ sở dữ liệu xác định, không phải tham số `clientNow` được client tự khai báo.

Mọi service cần một chính sách đồng hồ nhất quán và kiểm soát sai lệch. Không thể bảo đảm ranh giới chính xác giữa nhiều máy bằng cách để mỗi máy tự cộng một khoảng đệm tùy ý.

### 8.3. Predicate thời gian phải xuất hiện trong đường thực thi

Ví dụ truy vấn một grant đã được lựa chọn và bảo vệ phù hợp:

~~~sql
SELECT grant_id, revision, expires_at
FROM entitlement_grant
WHERE tenant_id = :tenant_id
  AND grant_id = :grant_id
  AND subject_id = :subject_id
  AND feature_code = :feature_code
  AND (
      scope_kind = 'TENANT'
      OR (scope_kind = 'RESOURCE' AND resource_id = :resource_id)
  )
  AND state = 'ACTIVE'
  AND valid_from <= :decision_time
  AND (
      validity_kind = 'PERPETUAL'
      OR (
          validity_kind = 'BOUNDED'
          AND expires_at > :decision_time
      )
  );
~~~

`decision_time` là giá trị tin cậy vừa lấy, không phải dữ liệu request. Truy vấn này chỉ thể hiện điều kiện cục bộ của grant; các điều kiện nguồn, tư cách thành viên, quyền trên đối tượng và phủ quyết vẫn phải được kiểm tra.

Nếu có nhiều nguồn thay thế, đánh giá tập grant theo chính sách đã định. Một grant thất bại không tự phủ quyết các grant độc lập khác; một grant thành công cũng không xóa bỏ điều kiện cấm ở tenant.

### 8.4. Phác thảo predicate Java

~~~java
boolean timeAndStateAllow(EntitlementGrant grant, Instant decisionTime) {
    if (grant.state() != GrantState.ACTIVE) {
        return false;
    }
    if (decisionTime.isBefore(grant.validFrom())) {
        return false;
    }

    return switch (grant.validityKind()) {
        case BOUNDED ->
            grant.expiresAt() != null
                && decisionTime.isBefore(grant.expiresAt());
        case PERPETUAL ->
            grant.expiresAt() == null;
    };
}
~~~

Đây là helper kiểm tra trạng thái và thời gian, không phải hàm phân quyền hoàn chỉnh. Caller còn phải kiểm tra nguồn được phép cấp chế độ tương ứng, phạm vi, đối tượng và các điều kiện khác.

Không để utility tự gọi nhiều đồng hồ khác nhau trong cùng quyết định. Truyền một `Instant` tin cậy giúp kiểm thử ranh giới rõ ràng; ở production, caller vẫn phải lấy nó tại đúng điểm quyết định.

### 8.5. Lưu bằng chứng của quyết định

Một receipt hoặc audit record có thể lưu:

~~~text
operation_id
tenant, subject, action, resource
authorization_decision_time
grant_id, grant_revision
source/policy revision liên quan
effective_end đã dùng
operation_policy: ADMISSION / EXECUTION / CONTINUOUS
~~~

Bằng chứng này giúp giải thích vì sao hành động được phép. Nó không mặc nhiên là một token có thể phát lại vô hạn cho những hành động mới.

Nếu transaction tiếp nhận tạo outbox để làm việc sau, consumer phải tuân thủ chính sách job đã chọn. Việc sự kiện được commit trước hạn không đủ cho một hành động yêu cầu kiểm tra tại execution hoặc delivery.

## 9. Gia hạn, thu hồi và tranh chấp đồng thời

### 9.1. Gia hạn là lệnh nhạy cảm

Một transaction gia hạn nên:

1. Xác thực và kiểm tra quyền quản lý grant cụ thể.
2. Nhận quyền xử lý idempotency của lệnh.
3. Khóa nguồn và grant theo giao thức chung.
4. Xác minh kỳ hoặc phê duyệt gia hạn có thẩm quyền.
5. Kiểm tra trạng thái, revision và mốc hiệu lực hiện tại.
6. Ghi hiệu ứng gia hạn một lần theo định danh nghiệp vụ.
7. Cập nhật thời hạn, tăng revision, ghi audit và outbox.
8. Hoàn tất kết quả idempotency trong cùng transaction.

Nguồn xác nhận “được dùng đến ngày X” phải dẫn tới một mốc X đã được kiểm chứng. Không kéo dài thêm một khoảng mới chỉ vì handler nhận lại cùng thông báo.

### 9.2. Cập nhật có điều kiện cho gia hạn trước khi hết hạn

Đoạn SQL minh họa cho nguồn có giới hạn hữu hạn:

~~~sql
UPDATE entitlement_grant
SET expires_at = :new_expires_at,
    revision = revision + 1
WHERE tenant_id = :tenant_id
  AND grant_id = :grant_id
  AND revision = :expected_revision
  AND state = 'ACTIVE'
  AND validity_kind = 'BOUNDED'
  AND :decision_time < expires_at
  AND :new_expires_at > expires_at
  AND :new_expires_at <= :source_allowed_until
RETURNING revision, expires_at;
~~~

Các tham số thời hạn và giới hạn nguồn được server xác minh; không lấy nguyên từ payload rồi xem đây là kiểm tra đủ.

Phải có đúng một hàng cập nhật. Nếu trả 0 hàng, có thể grant đã hết hạn, bị thu hồi, đã đổi revision hoặc yêu cầu không còn phù hợp. Đọc lại và xử lý theo nghiệp vụ; không bỏ các điều kiện để “retry cho thành công”.

Với grant đã hết hạn, luồng cấp kỳ mới có identity mới theo mô hình tham chiếu. Không dùng câu SQL gia hạn trước hạn để tự khôi phục quyền cũ.

Nếu cần rút ngắn thời hạn vì điều chỉnh nguồn, đó là một lệnh riêng có quyền và bằng chứng tương ứng. Dùng `GREATEST(old_end, incoming_end)` cho mọi event có thể che mất một quyết định rút ngắn hợp lệ.

### 9.3. Idempotency và định danh gia hạn

Idempotency key HTTP bảo vệ retry của một lệnh client. Nó không đủ để chống cùng một kỳ gia hạn bị xử lý qua hai key hoặc hai consumer.

Cần có ràng buộc bền vững như:

~~~text
UNIQUE(tenant, grant_or_term, renewal_business_reference)
~~~

Tham chiếu có thể là dòng quyết định phê duyệt, kỳ quyền đã được cấp hoặc một định danh nguồn khác phù hợp. Một event ID kỹ thuật không phải lúc nào cũng đồng nhất với một quyền lợi nghiệp vụ.

Bản ghi chống lặp, thay đổi thời hạn và audit phải commit cùng nhau. Nếu bản ghi chống lặp được commit nhưng cập nhật grant thất bại ở transaction khác, lần retry có thể bị bỏ qua dù chưa được gia hạn.

### 9.4. Thu hồi không chờ đến ngày hết hạn

Thu hồi có thể xảy ra khi thành viên rời tổ chức, nguồn bị đình chỉ hoặc quyền bị cấp sai.

Thu hồi cần:

- Đúng actor và phạm vi quản lý.
- Chuyển trạng thái có điều kiện.
- Tăng revision.
- Ghi lý do và bằng chứng.
- Thực hiện cơ chế vô hiệu hóa quyền dẫn xuất theo yêu cầu của chính sách.

Một request đã chờ khóa phải đánh giá lại sau khi lệnh thu hồi thắng khóa. Nếu chính sách cho phép tiếp tục hành động được admission trước thu hồi, điều đó phải được ghi nhận, không suy từ một cache allow cũ.

### 9.5. Tranh chấp gia hạn và thu hồi

Giả sử hai lệnh cùng thao tác grant revision 8:

~~~text
Lệnh A: gia hạn đến kỳ mới.
Lệnh B: thu hồi vì thành viên không còn đủ điều kiện.
~~~

Khóa hoặc kiểm tra revision phải khiến chúng có thứ tự rõ ràng. Sau khi thu hồi có hiệu lực, gia hạn dựa trên revision cũ không được khôi phục grant. Nếu gia hạn thắng trước, lệnh thu hồi vẫn cần đánh giá trạng thái hiện tại và có thể thu hồi revision mới theo thẩm quyền.

Đừng xem một event “đã gia hạn” là lệnh ghi đè mọi trạng thái. Quyền bắt nguồn từ việc còn đủ điều kiện, không chỉ từ việc từng có một giao dịch gia hạn.

## 10. Worker hết hạn và sự kiện dẫn xuất

### 10.1. Worker phục vụ vật chất hóa, không quyết định mọi quyền

Worker hết hạn hữu ích để:

- Cập nhật trạng thái cho truy vấn quản trị.
- Phát thông báo.
- Đóng tài nguyên hoặc phiên theo chính sách.
- Làm sạch bản sao và hỗ trợ đối soát.
- Ghi nhận lịch sử hoàn tất vòng đời.

Nếu worker ngừng một giờ, quyền hết hạn trong giờ đó vẫn phải bị chặn bởi predicate thời gian trên đường thực thi. Đây là bất biến quan trọng nhất của expiration.

### 10.2. Công việc phải mang revision kỳ vọng

Một worker có thể lấy danh sách ứng viên bằng index rồi xử lý từng grant trong transaction. Sau khi lấy các khóa cần thiết, nó kiểm tra lại:

~~~sql
UPDATE entitlement_grant
SET state = 'EXPIRED',
    revision = revision + 1
WHERE tenant_id = :tenant_id
  AND grant_id = :grant_id
  AND revision = :expected_revision
  AND state = 'ACTIVE'
  AND validity_kind = 'BOUNDED'
  AND expires_at = :expected_expires_at
  AND expires_at <= :decision_time
RETURNING revision;
~~~

Ứng viên có thể đã được gia hạn sau lần quét. Nếu cập nhật 0 hàng, worker không được phát sự kiện “grant hiện tại đã hết hạn” từ dữ liệu cũ. Nó có thể bỏ công việc cũ hoặc đưa đối tượng về luồng đánh giá lại.

Nếu cập nhật thành công, ghi audit và outbox cùng transaction. Một khóa sự kiện theo grant, revision kết quả và loại chuyển trạng thái giúp chống phát hiệu ứng trùng.

### 10.3. Consumer phải hiểu phạm vi của sự kiện

Sự kiện `GrantExpired` nói về một grant hoặc term cụ thể. Nó không nhất thiết có nghĩa subject mất toàn bộ tính năng.

Consumer cập nhật quyền tổng hợp phải:

- Đối chiếu revision hoặc generation.
- Xét các grant thay thế còn hiệu lực.
- Không áp dụng event cũ lên một grant mới.
- Xử lý trùng một cách an toàn.
- Truy vấn lại nguồn có thẩm quyền khi không xác định được trạng thái phù hợp.

Ví dụ grant trial hết hạn nhưng grant thuê bao trả phí đã có hiệu lực. Consumer không được tắt tính năng chỉ vì nhận event trial hết hạn sau event thuê bao.

### 10.4. TTL dữ liệu và lưu lịch sử

Tác vụ dọn dữ liệu không được xóa trước khi các bằng chứng cần thiết được giữ theo chính sách lưu trữ. Có thể chuyển lịch sử sang kho riêng, nhưng vẫn cần duy trì bằng chứng ngăn cùng quyền lợi được cấp lại nếu nó còn liên quan.

Không dùng “bản ghi không còn tồn tại” làm cách phân biệt duy nhất giữa chưa từng được cấp, đã hết hạn và đã bị thu hồi. Ba trường hợp đó có hậu quả nghiệp vụ khác nhau.

## 11. API, cache và khả năng quan sát

### 11.1. Hiển thị thời hạn mà không giao quyền quyết định cho client

API đọc có thể trả:

~~~json
{
  "feature": "REPORT_EXPORT",
  "scope": {
    "kind": "RESOURCE",
    "resourceId": "project-p1"
  },
  "effective": false,
  "reason": "ENTITLEMENT_EXPIRED",
  "validFrom": "2026-11-01T00:00:00Z",
  "effectiveEnd": "2026-12-01T00:00:00Z",
  "evaluatedAt": "2026-12-01T00:00:00Z",
  "revision": 12
}
~~~

`effective` là kết quả đánh giá tại thời điểm và phạm vi được trả, không phải một cam kết vô thời hạn cho mọi request sau.

Đồng hồ đếm ngược trên giao diện chỉ phục vụ trải nghiệm. Endpoint thực thi phải tự kiểm tra lại; người dùng sửa giờ máy hoặc giữ tab cũ không được làm quyền sống lâu hơn.

### 11.2. Phân biệt hết hạn với ngoài quyền và lỗi hệ thống

Một số mã lỗi nghiệp vụ minh họa:

| Mã | Ý nghĩa |
| --- | --- |
| `ENTITLEMENT_NOT_YET_VALID` | Chưa đến thời điểm bắt đầu |
| `ENTITLEMENT_EXPIRED` | Không còn grant phù hợp do thời hạn |
| `ENTITLEMENT_REVOKED` | Grant liên quan đã bị thu hồi |
| `ENTITLEMENT_SCOPE_MISMATCH` | Không áp dụng cho đối tượng đang thao tác |
| `ENTITLEMENT_SOURCE_INACTIVE` | Nguồn không còn đủ điều kiện |
| `ENTITLEMENT_REVISION_CHANGED` | Trạng thái đã thay đổi, cần đọc lại |
| `AUTHORIZATION_STATE_UNAVAILABLE` | Chưa thể xác định trạng thái có thẩm quyền |

Response cụ thể phải theo chính sách tiết lộ thông tin. Đối với đối tượng ngoài tenant, không trả chi tiết ngày hết hạn hoặc nguồn cấp của người khác.

Lỗi đọc hệ thống quyền không nhất thiết là lỗi hết hạn. Có thể trả lỗi tạm thời để client retry, đồng thời không cho phép tạo hiệu ứng mới khi chưa có căn cứ quyền.

### 11.3. Retry sau hạn không được trở thành hành động mới

Một lệnh đã thành công trước hạn có thể được retry cùng idempotency key để tìm kết quả. Server cần phân biệt:

- Tra cứu receipt hoặc kết quả của hành động đã thực hiện.
- Tạo một lần thực thi mới.
- Tạo token hoặc link tải mới.
- Đọc nội dung nhạy cảm của kết quả.

Retry không tạo thêm job, không đặt lại deadline và không cấp một capability mới chỉ vì receipt cũ tồn tại. Quyền đọc lịch sử hoặc tải kết quả phải theo chính sách hiện tại của các hành động đó.

Nếu receipt được phép đọc sau khi mất entitlement sử dụng tính năng, hãy mô hình hóa quyền đọc lịch sử riêng. Không coi việc trả lại toàn bộ response có chứa dữ liệu bí mật là luôn an toàn.

### 11.4. Theo dõi các vi phạm bất biến

Các chỉ báo đáng theo dõi gồm:

- Quyết định allow có `decision_time >= effective_end`.
- Job bắt đầu sau hạn trái với execution policy.
- Grant hữu hạn thiếu ngày kết thúc.
- Event gia hạn trùng tạo thay đổi revision hoặc thời hạn nhiều lần.
- Worker cũ ghi đè revision mới.
- Cache trả quyền vượt thời hạn.
- Grant bị thu hồi lại được khôi phục bởi event cũ.
- Grant đã hết hạn vẫn còn `ACTIVE` quá lâu trong dữ liệu quản trị.
- Một chương trình trial được cấp lại sau khi lịch sử cũ bị xóa.

Trạng thái quản trị cập nhật trễ là vấn đề vận hành; quyết định allow quá hạn là vấn đề thực thi quyền. Hai chỉ báo cần được phân biệt để ưu tiên xử lý đúng.

Audit nên chứa tenant, subject, grant/term, revision, resource, action, thời gian quyết định, nguồn và lý do. Không đưa token hoặc bí mật xác thực vào log.

## 12. Kiểm thử các tình huống tấn công logic

### 12.1. Kiểm thử chính xác ranh giới thời gian

Dùng đồng hồ có thể điều khiển trong kiểm thử thay vì chờ thời gian thực:

~~~text
valid_from = S
effective_end = E

S - một đơn vị độ phân giải → từ chối: chưa hiệu lực
S                         → có thể cho phép
E - một đơn vị độ phân giải → có thể cho phép
E                         → từ chối: hết hạn
E + một đơn vị độ phân giải → từ chối: hết hạn
~~~

Chọn đơn vị độ phân giải phù hợp với dữ liệu thực tế, chẳng hạn microsecond của timestamp trong môi trường đang dùng; đừng giả định mọi lớp lưu và so sánh đều giữ cùng độ chính xác.

Lặp lại khi worker không chạy và trạng thái hàng vẫn là `ACTIVE`. Kết quả ở E phải không đổi.

### 12.2. Cache, token và đồng hồ client

| Ca kiểm thử | Hành vi | Kết quả cần chứng minh |
| --- | --- | --- |
| Cache allow trước hạn | Tạo cache ở E−2 phút, gọi lại sau E | Bị chặn dù cache TTL chưa hết |
| Sliding cache | Truy cập liên tục quanh deadline | Không đẩy effective end ra sau |
| Sửa giờ máy | Client gửi thời gian quá khứ | Server không dùng làm thời gian quyết định |
| Token dài hơn grant | Token còn hạn nhưng grant hết | Không tạo hành động ngoài quyền |
| Token/link cũ sau thu hồi | Phát lại capability đã cấp | Hành vi đúng mô hình thu hồi đã chọn |
| Thiếu ngày kết thúc | Grant BOUNDED có dữ liệu lỗi | Không suy thành vô thời hạn |
| Lệch độ phân giải | Chuyển giữa timestamp và token dạng giây | Không làm tròn kéo dài quyền |
| Mất nguồn dữ liệu quyền | Mô phỏng lỗi đọc nguồn bắt buộc | Không tự cho phép bằng nhánh lỗi |

### 12.3. Quyền theo đối tượng và nhiều nguồn

- Subject có grant của tenant A nhưng gọi tài nguyên tenant B: không được phép.
- Grant cho dự án P1 bị dùng cho P2: bị từ chối.
- Grant A hết hạn, grant B độc lập còn hạn: kết quả theo chính sách thay thế, không bị tắt nhầm.
- Grant còn hạn nhưng thành viên đã bị loại khỏi dự án: không vượt qua điều kiện tư cách thành viên.
- Grant vô thời hạn nhưng tenant bị đình chỉ: điều kiện phủ quyết vẫn có hiệu lực.
- Quyền tính năng còn hạn nhưng phê duyệt tài nguyên đã hết: không lấy thời hạn lớn nhất để cho phép.

### 12.4. Tranh chấp gia hạn, hết hạn và thu hồi

**Ca A — Worker cũ sau gia hạn**

~~~text
Ban đầu:
  Grant revision 4, expires_at = E1.
  Worker giữ ứng viên revision 4/E1.

Gia hạn hợp lệ:
  Grant trở thành revision 5, expires_at = E2 > E1.

Worker cũ chạy:
  Không cập nhật revision 5 thành EXPIRED theo E1.
  Không phát hiệu ứng tắt quyền tổng hợp dựa trên ứng viên cũ.
~~~

**Ca B — Gia hạn trùng**

Gửi cùng tham chiếu gia hạn với nhiều request hoặc event, có thể dùng các HTTP key khác nhau. Chỉ có một hiệu ứng theo danh tính nghiệp vụ; hạn cuối không tăng theo số lần retry.

**Ca C — Thu hồi tranh chấp gia hạn**

Điều khiển hai transaction cùng đến điểm khóa. Nếu thu hồi đã thắng, gia hạn theo revision cũ không được khôi phục. Nếu gia hạn thắng trước, quyết định thu hồi sau đó vẫn có thể chặn trạng thái hiện hành theo quyền.

**Ca D — Request chờ khóa qua mốc hết hạn**

~~~text
Transaction bắt đầu trước E.
Request bị chặn tại khóa.
Sau E, request mới lấy được đủ khóa.

Kỳ vọng:
  Thời gian quyết định được lấy sau lúc chờ.
  Không dùng thời điểm bắt đầu transaction để cho phép một admission mới.
~~~

**Ca E — Quyết định trước hạn, commit sau hạn**

Cho hành động được admission trước E nhưng commit sau E. Kiểm tra đúng chính sách đã chọn và audit ghi đúng thời điểm quyết định. Không viết assertion “commit luôn trước E” nếu thiết kế không bảo đảm điều đó.

Các ca đồng thời nên dùng barrier/latch và cơ sở dữ liệu có hành vi khóa tương ứng môi trường triển khai. Chỉ gọi tuần tự hoặc thêm sleep ngẫu nhiên không chứng minh giao thức đúng.

### 12.5. Hàng đợi và hành động dài

| Tình huống | Kết quả theo chính sách tham chiếu |
| --- | --- |
| Job được tiếp nhận trước hạn, worker bắt đầu sau hạn | Worker không bắt đầu nếu execution check không còn hợp lệ |
| Worker có role hệ thống mạnh | Không dùng role đó để thay quyền subject vô điều kiện |
| Retry job sau hạn | Không tạo job mới hoặc tự gia hạn deadline |
| File tạo trước hạn, tải sau hạn | Đánh giá riêng quyền tải và tài nguyên |
| Phiên dài đến checkpoint sau hạn | Dừng hoặc giới hạn theo continuous policy đã định |
| Consumer nhận event hết hạn của term cũ | Không vô hiệu hóa term mới |
| Thu hồi giữa hai checkpoint | Hành vi nằm trong giới hạn thu hồi đã được thiết kế |

Với mô hình continuous, phải kiểm tra cả thời gian tối đa giữa các checkpoint và hành động đang diễn ra. Kiểm tra định kỳ không tự bảo đảm dừng đúng từng mili giây; nếu cần ranh giới chặt hơn, cơ chế thực thi tài nguyên phải đáp ứng yêu cầu đó.

### 12.6. Chèn lỗi và kiểm tra bất biến

Chèn lỗi sau khi ghi bằng chứng gia hạn nhưng trước cập nhật grant, sau cập nhật grant nhưng trước audit/outbox, và sau commit nhưng trước response.

Kỳ vọng:

- Lỗi trước commit không để lại hiệu ứng một phần.
- Retry sau commit tìm đúng kết quả đã có.
- Không cộng thêm thời hạn hoặc phát lại quyền lợi.
- Consumer nhận lại outbox không tạo thêm hiệu ứng.

Có thể sinh chuỗi:

~~~text
Cấp → sử dụng → gia hạn → retry → thu hồi
→ event gia hạn cũ → worker hết hạn cũ
→ cấp term mới hợp lệ → event hết hạn term cũ
~~~

Sau mỗi bước, kiểm tra:

- Quyền theo đúng tenant, subject và resource scope.
- Không allow ngoài khoảng hợp lệ tại điểm kiểm tra đã chọn.
- Revision không bị ghi đè bởi quyết định cũ.
- Không có grant bị thu hồi tự sống lại.
- Quyền lợi chỉ được cấp đúng số lần theo chương trình.
- Trạng thái tổng hợp khớp các nguồn hiện hành.

Với một tập grant và chính sách không thay đổi, khi thời gian đi qua điểm kết thúc cuối cùng thì quyền không thể tự xuất hiện lại. Thuộc tính này giúp phát hiện deadline trượt, xử lý null sai và nhánh cache kéo dài quyền.

## 13. Các lỗi thiết kế cần nhận ra khi review

| Thiết kế có vấn đề | Rủi ro | Hướng sửa |
| --- | --- | --- |
| Chỉ kiểm tra `state = ACTIVE` | Worker chậm làm quyền sống quá hạn | So thời gian ngay trên đường thực thi |
| Xóa grant bằng TTL để thu hồi quyền | Xóa trễ hoặc bản sao còn giữ quyền | Predicate thời gian và trạng thái có thẩm quyền |
| Cache một boolean allow | Không biết quyền kết thúc lúc nào | Mang effective end, scope và revision |
| Gia hạn từ `now + duration` mỗi event | Retry kéo dài quyền vô hạn | Mốc nguồn xác định và danh tính gia hạn duy nhất |
| Event hết hạn chỉ chứa subject/feature | Tắt nhầm grant hoặc term mới | Mang grant/term identity và revision |
| Dùng `MAX(expires_at)` cho mọi nguồn | Bỏ qua phụ thuộc bắt buộc | Mô hình quan hệ thay thế, phụ thuộc và phủ quyết |
| Quyền vô thời hạn biểu diễn bằng ngày bị thiếu | Dữ liệu lỗi trở thành quyền vĩnh viễn | Validity kind rõ và constraint |
| Worker dùng toàn quyền service để xử lý job | Vượt qua hết hạn của người yêu cầu | Kiểm tra quyền ủy nhiệm và execution policy |
| Retry trả token hoặc link mới vô điều kiện | Receipt cũ biến thành quyền mới | Tách đọc lịch sử, tạo capability và thực thi |
| Chỉ dùng token expiry để thu hồi ngay | Token cũ còn được chấp nhận | Kiểm tra phiên bản hoặc cơ chế thu hồi thích hợp |
| Xóa lịch sử trial khi hết hạn | Có thể nhận lại cùng quyền lợi | Giữ bằng chứng chống cấp lặp theo vòng đời nghiệp vụ |

## 14. Tiêu chí hoàn thành thiết kế

Một cơ chế entitlement expiration cần trả lời được:

- Khoảng hiệu lực được biểu diễn và so sánh theo quy ước nào?
- Đồng hồ nào có thẩm quyền, thời gian được lấy tại đâu?
- Quyền bị giới hạn bởi những nguồn và quan hệ đối tượng nào?
- Một grant hết hạn có ảnh hưởng ra sao khi còn grant thay thế?
- Kiểm tra diễn ra lúc admission, execution, delivery hay liên tục?
- Cache, token và link tải có thể tồn tại đến lúc nào?
- Gia hạn, thu hồi và worker cũ tranh chấp theo giao thức nào?
- Một sự kiện hoặc yêu cầu gia hạn được chống lặp theo identity nào?
- Worker ngừng hoạt động thì các hành động sau hạn có bị chặn không?
- Bằng chứng lịch sử nào phải tồn tại để ngăn cấp lại quyền lợi?

Hết hạn được thực thi an toàn khi **thời gian là một phần của quyết định quyền tại đúng điểm tạo hiệu ứng**, gắn với chủ thể, tài nguyên và nguồn cấp hiện hành. Worker hỗ trợ vòng đời dữ liệu; transaction bảo vệ tranh chấp; revision và idempotency ngăn sự kiện cũ hoặc yêu cầu trùng làm quyền kéo dài ngoài chính sách.
