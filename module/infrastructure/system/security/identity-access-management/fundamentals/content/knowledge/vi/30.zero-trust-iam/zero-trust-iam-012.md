# Continuous access evaluation

## 1. Quyết định lúc đăng nhập không có giá trị mãi mãi

Một người dùng đăng nhập hợp lệ lúc đầu ngày, nhận token và mở ứng dụng. Sau đó, tài khoản bị khóa, một vai trò bị thu hồi hoặc thiết bị bị phát hiện không còn đáp ứng điều kiện truy cập. Nếu ứng dụng chỉ kiểm tra bằng chứng được cấp lúc đăng nhập, quyền truy cập có thể tiếp tục dù điều kiện cho phép đã thay đổi.

**Continuous access evaluation**, hay đánh giá truy cập liên tục, là cách thiết kế để quyền truy cập đang diễn ra được đánh giá lại khi có yêu cầu hoặc thay đổi liên quan. Quyết định được cập nhật dựa trên trạng thái danh tính, quyền, phiên, tài nguyên và ngữ cảnh có hiệu lực theo chính sách.

Trong bài này, thuật ngữ được dùng theo nghĩa kiến trúc IAM tổng quát, không mô tả một tính năng của riêng nhà cung cấp nào. Cách tích hợp, loại sự kiện, khả năng thu hồi và thời gian phản ứng phụ thuộc từng hệ thống.

“Liên tục” không có nghĩa mọi người phải nhập mật khẩu trước từng API call, cũng không có nghĩa mọi hệ thống luôn nhận thay đổi tức thì. Điều cần thiết là có cơ chế đánh giá lại, thời hạn hiệu lực rõ ràng và khả năng kiểm chứng việc thực thi.

## 2. Điều gì có thể làm thay đổi quyết định truy cập?

Một quyết định cho phép thường dựa trên nhiều điều kiện. Mỗi điều kiện có thể thay đổi sau khi phiên hoặc token đã được cấp.

| Nhóm trạng thái | Ví dụ thay đổi | Câu hỏi cần đánh giá lại |
| --- | --- | --- |
| Danh tính | Tài khoản bị vô hiệu hóa, quan hệ đối tác kết thúc | Chủ thể còn được phép hoạt động không? |
| Quyền | Xóa nhóm, đổi vai trò, kết thúc quyền tạm thời | Chủ thể còn được thực hiện hành động này không? |
| Phiên | Phát hiện chiếm phiên, phiên bị quản trị viên thu hồi | Bằng chứng phiên còn được chấp nhận không? |
| Thiết bị | Thiết bị không còn đáp ứng điều kiện quản trị | Điều kiện về môi trường sử dụng còn đúng không? |
| Mạng và rủi ro | Đổi đường kết nối, xuất hiện dấu hiệu cần điều tra | Chính sách hiện tại yêu cầu giới hạn hoặc xác minh thêm không? |
| Tài nguyên | Dữ liệu đổi mức nhạy cảm, tài nguyên bị khóa | Quyền cũ còn phù hợp với trạng thái tài nguyên không? |
| Chính sách | Thay điều kiện truy cập hoặc quy tắc phân quyền | Quyết định trước đó còn hợp lệ dưới chính sách mới không? |

Không phải mọi thay đổi đều phải khóa toàn bộ tài khoản. Xóa quyền phê duyệt có thể chỉ làm mất khả năng phê duyệt, trong khi quyền đọc dữ liệu vẫn còn. Một sự cố xác nhận chiếm phiên có thể yêu cầu thu hồi phiên đó và điều tra phạm vi rộng hơn.

Phản ứng cần gắn với ý nghĩa của thay đổi, thay vì dùng cùng một hành động cho mọi tín hiệu.

## 3. Phân biệt xác thực lại, đánh giá lại và thu hồi

Các khái niệm này liên quan nhưng không đồng nghĩa:

| Cơ chế | Mục đích | Điều không tự bảo đảm |
| --- | --- | --- |
| Xác thực lại | Yêu cầu chứng minh lại danh tính | Người dùng có thêm quyền nghiệp vụ |
| Step-up authentication | Đáp ứng mức xác thực cao hơn cho điều kiện cụ thể | Vai trò đã bị thu hồi được khôi phục |
| Đánh giá lại phân quyền | Kiểm tra quyền và điều kiện hiện tại cho hành động | Phiên phải luôn bị kết thúc |
| Thu hồi một quyền | Loại bỏ quyền hoặc quan hệ cấp quyền | Mọi bản sao, token và cache nhận thay đổi tức thì |
| Thu hồi phiên | Không tiếp tục chấp nhận phiên theo cơ chế quản lý của hệ thống | Mọi token đã phát hành từ phiên mất hiệu lực ở mọi tài nguyên |
| Từ chối gia hạn token | Ngăn lấy token mới theo đường gia hạn đó | Token hiện có lập tức không sử dụng được |

Ví dụ, nhân viên đã mất vai trò `payment-approver` không thể lấy lại quyền phê duyệt bằng cách làm thêm MFA. Điều cần đánh giá là quyền nghiệp vụ còn tồn tại hay không, không chỉ mức chắc chắn của xác thực.

Tương tự, người dùng đăng xuất khỏi một ứng dụng không nhất thiết đã kết thúc phiên tại nhà cung cấp danh tính và tất cả ứng dụng SSO khác. Phạm vi của từng thao tác phải được hiểu rõ trong kiến trúc phiên.

## 4. Một kiến trúc đánh giá lại có những thành phần nào?

Luồng khái quát:

```text
Nguồn trạng thái và sự kiện
    tài khoản / quyền / phiên / thiết bị / tài nguyên
                         |
                         v
Xác minh, chuẩn hóa và cập nhật trạng thái có thẩm quyền
                         |
                         v
Thành phần đánh giá chính sách
                         |
                         v
Điểm thực thi tại API, ứng dụng hoặc kết nối
                         |
                         v
Cho phép / giới hạn / yêu cầu xác minh thêm / từ chối
                         |
                         v
Nhật ký quyết định, kết quả và độ trễ thực thi
```

**Nguồn trạng thái** cung cấp dữ liệu như tài khoản đang hoạt động, membership, phiên bị thu hồi hoặc thiết bị không đáp ứng điều kiện. Mỗi thuộc tính cần có nguồn chịu trách nhiệm rõ ràng.

**Thành phần đánh giá chính sách** kết hợp dữ liệu với chủ thể, hành động và tài nguyên để đưa ra quyết định. Nó có thể nằm trong cùng ứng dụng hoặc là một dịch vụ riêng.

**Điểm thực thi** là nơi thật sự chặn hoặc cho thao tác đi tiếp. Nếu nguồn trạng thái đã cập nhật nhưng API không sử dụng thông tin mới, thay đổi chưa có hiệu lực bảo vệ tại API đó.

**Lớp vận chuyển và đồng bộ** giúp các bên nhận thay đổi: sự kiện, truy vấn trực tiếp, kiểm tra định kỳ hoặc cơ chế kết hợp. Cần xử lý cả lỗi, chậm, trùng lặp và mất đồng bộ.

Thiết kế chỉ kết nối nhà cung cấp danh tính với một gateway có thể chưa bao phủ đường truy cập trực tiếp vào service, tác vụ nền hoặc kết nối đã mở trước đó. Phải xác định đầy đủ những điểm cần thực thi trong phạm vi tài nguyên.

## 5. Các cách nhận biết thay đổi

### 5.1. Kiểm tra trạng thái khi xử lý yêu cầu

API có thể tra trạng thái hiện tại hoặc một bản sao có kiểm soát trước khi cho phép hành động. Cách này giúp quyết định sử dụng dữ liệu mới hơn thông tin trong token, nhưng tạo thêm phụ thuộc về thời gian đáp ứng và khả năng sẵn sàng.

Không nhất thiết mỗi request đều phải truy vấn mọi nguồn từ đầu. Có thể sử dụng trạng thái tổng hợp hoặc cache nếu độ mới và cơ chế vô hiệu hóa đáp ứng yêu cầu của tài nguyên.

### 5.2. Nhận sự kiện thay đổi

Nguồn quyền phát sự kiện khi một membership bị xóa; nguồn quản lý phiên phát sự kiện khi một phiên bị thu hồi. Bên nhận cập nhật trạng thái và vô hiệu hóa các quyết định liên quan.

Sự kiện giúp phản ứng mà không phải chờ đến một chu kỳ kiểm tra dài. Tuy nhiên, khả năng gửi sự kiện không tự bảo đảm mọi bên nhận đã áp dụng thành công.

### 5.3. Kiểm tra định kỳ và đối soát

Một tác vụ định kỳ có thể phát hiện bản sao bị lệch hoặc phục hồi trạng thái sau gián đoạn. Độ trễ phụ thuộc chu kỳ và thời gian xử lý, nên không nên mô tả cơ chế này là thu hồi tức thì.

### 5.4. Kết hợp nhiều cơ chế

Một thiết kế thực tế có thể nhận sự kiện để cập nhật nhanh, đối soát định kỳ để sửa lệch và kiểm tra trực tiếp trước những hành động nhạy cảm. Sự kết hợp phải có ý nghĩa rõ ràng; không dùng một kiểm tra yếu hơn để tự bỏ qua kết quả thu hồi đã biết.

## 6. Ví dụ: thu hồi quyền phê duyệt trong một phiên đang hoạt động

Giả sử Minh có phiên hợp lệ và vai trò `payment-approver` tại đơn vị A. Sau khi chuyển công việc, quyền phê duyệt của Minh bị thu hồi.

Diễn biến mong muốn:

1. Kho quyền ghi nhận việc thu hồi và tạo phiên bản trạng thái mới cho quan hệ quyền đó.
2. Các điểm đánh giá nhận thay đổi qua cơ chế đồng bộ đã thiết kế.
3. Cache liên quan đến quyền phê duyệt của Minh trong đơn vị A bị cập nhật hoặc vô hiệu hóa.
4. Khi Minh gửi yêu cầu phê duyệt tiếp theo, API sử dụng trạng thái quyền đủ mới.
5. API từ chối phê duyệt, dù phiên đăng nhập hoặc access token vẫn còn hạn.
6. Những hành động khác chỉ được tiếp tục nếu Minh vẫn có đủ quyền và điều kiện tương ứng.

Mã giả minh họa một bước kiểm tra tại API:

```text
approvePayment(request):
    principal = authentication.requireValidApiPrincipal(request)
    payment = payments.loadWithinAuthorizedScope(request.paymentId)

    state = accessState.read(
        subject = principal.id,
        session = principal.sessionReference,
        scope = payment.organization
    )

    require state.isFreshEnoughFor("payment.approve")
    require state.subjectActive
    require not state.sessionRevoked
    require state.hasActivePermission("payment.approve")
    require payment.createdBy != principal.id
    require currentContextMeetsPolicy(principal, payment)

    payments.approveWithRequiredConcurrencyControls(payment)
    audit.recordOutcome(principal, payment)
```

Đây là mã giả về trách nhiệm kiểm tra, không phải một triển khai đầy đủ. Các hàm tải phạm vi, kiểm tra trạng thái và điều khiển đồng thời phải có cơ chế thực thi cụ thể trong hệ thống thực tế. Thuộc tính nhận từ request không tự trở thành trạng thái quyền đáng tin cậy.

Nếu trạng thái cho biết quyền đã bị thu hồi, không chuyển sang một bản sao cũ đang cho phép để hoàn thành yêu cầu. Nếu không đọc được trạng thái đủ mới, áp dụng chính sách thiếu dữ liệu đã được định nghĩa cho hành động đó.

## 7. Xử lý token và phiên một cách thực tế

### 7.1. Token còn hạn không đồng nghĩa quyền hiện tại còn nguyên

Một token có thể chứa vai trò hoặc scope tại thời điểm phát hành. Nếu ứng dụng chỉ kiểm tra chữ ký và thời hạn của token, thay đổi quyền ở hệ thống nguồn có thể chưa được phản ánh.

Token tự chứa và kiểm tra trạng thái hiện tại giải quyết các vấn đề khác nhau. Chữ ký giúp kiểm tra bằng chứng theo mô hình tin cậy; trạng thái mới giúp biết điều kiện hoặc quyền đã thay đổi hay chưa.

Các lựa chọn thiết kế có thể gồm token có thời hạn phù hợp, truy vấn trạng thái, danh sách thu hồi, phiên bản quyền hoặc cơ chế phản ứng theo sự kiện. Không phải nền tảng nào cũng hỗ trợ tất cả lựa chọn, và mỗi lựa chọn có chi phí vận hành riêng.

### 7.2. Gia hạn và sử dụng token là hai đường khác nhau

Từ chối refresh token có thể ngăn phát hành access token mới theo phiên đó. Nhưng một access token đang được resource server chấp nhận vẫn có thể sử dụng đến khi hết hạn hoặc đến khi resource server nhận và thực thi thông tin thu hồi.

Do đó, muốn đáp ứng yêu cầu chặn nhanh phải kiểm tra đường sử dụng tại tài nguyên, không chỉ đường phát hành token.

### 7.3. Không đồng nhất mọi định danh phiên

Phiên đăng nhập ở nhà cung cấp danh tính, phiên cục bộ của ứng dụng, access token và một kết nối dài có thể có các định danh và vòng đời khác nhau. Muốn thu hồi chính xác phải biết chúng liên kết như thế nào.

Phạm vi thu hồi cũng cần rõ: một phiên, mọi phiên của một chủ thể, một quyền, một thiết bị hay một workload. Không dùng email hoặc tên hiển thị làm căn cứ duy nhất để suy ra tất cả đối tượng cần xử lý.

## 8. Sự kiện cần đáng tin, có phiên bản và xử lý được lỗi

Một sự kiện minh họa:

```json
{
  "eventId": "event-4007",
  "source": "authorization-store",
  "type": "permission-assignment.revoked",
  "subjectId": "principal-1042",
  "scopeId": "organization-A",
  "assignmentId": "assignment-208",
  "assignmentVersion": 18,
  "occurredAt": "2030-01-01T09:00:00Z"
}
```

Tên trường và thời điểm trên chỉ minh họa cấu trúc dữ liệu. Đây không phải schema của một giao thức cụ thể.

Các yêu cầu thiết kế quan trọng:

- **Xác minh nguồn:** bên nhận chỉ chấp nhận sự kiện từ nguồn được phép, qua cơ chế xác thực và bảo vệ tính toàn vẹn phù hợp.
- **Định danh đúng đối tượng:** nguồn danh tính, tenant hoặc phạm vi cần được diễn giải cùng định danh chủ thể và quan hệ quyền.
- **Chống xử lý trùng:** nhận lại cùng sự kiện không tạo trạng thái sai hoặc tác dụng phụ lặp ngoài dự kiến.
- **Xử lý sai thứ tự:** một sự kiện cũ không được ghi đè trạng thái mới hơn của cùng đối tượng. Phiên bản cần có quy tắc so sánh rõ ràng trong phạm vi đối tượng đó.
- **Phục hồi gián đoạn:** có cơ chế thử lại, theo dõi tồn đọng và đối soát với nguồn có thẩm quyền.
- **Theo dõi hiệu lực:** phân biệt đã gửi, đã nhận, đã cập nhật trạng thái và đã có hiệu lực tại điểm thực thi.

Không dùng một bộ đếm của quan hệ quyền để so sánh với phiên bản thiết bị hoặc phiên khác. Nếu các nguồn không cung cấp thứ tự chung, cần thiết kế cách hợp nhất hoặc truy vấn lại nguồn; timestamp đơn lẻ có thể chịu ảnh hưởng sai lệch đồng hồ và độ trễ.

Sự kiện không nên mang token bí mật để làm khóa tra cứu. Có thể dùng định danh hoặc tham chiếu phù hợp với mô hình của hệ thống, đồng thời bảo vệ quyền đọc và phát sự kiện.

## 9. Kết nối dài, tác vụ nền và yêu cầu đang chạy

Một API kiểm tra quyền trước mỗi request tương đối dễ xác định điểm đánh giá lại. Với luồng tải dữ liệu, kết nối liên tục hoặc job chạy lâu, ranh giới này cần thiết kế thêm.

### 9.1. Kết nối dài

Một kết nối được mở khi quyền còn hợp lệ không nên mặc nhiên truyền dữ liệu nhạy cảm vô thời hạn sau khi quyền bị thu hồi. Hệ thống có thể kiểm tra lại tại các mốc phù hợp, nhận tín hiệu kết thúc hoặc giới hạn thời gian phiên kết nối.

Cơ chế phải hoạt động tại nơi đang giữ kết nối. Chỉ cập nhật một kho quyền mà không có đường tác động đến kết nối chưa đủ để kết thúc việc truyền dữ liệu.

### 9.2. Tác vụ nền

Một job cần biết danh tính workload thực thi, chủ thể yêu cầu nếu có, phạm vi tài nguyên và chính sách áp dụng. Cần xác định quyền được kiểm tra khi xếp hàng, khi chạy hoặc trong các giai đoạn xử lý nào.

Khi quyền người yêu cầu đã bị thu hồi trước lúc job chạy, hệ thống phải có quy tắc rõ ràng. Không mặc định một quyết định cho phép tại thời điểm xếp hàng có hiệu lực mãi mãi.

### 9.3. Yêu cầu đã bắt đầu thực hiện

Đánh giá lại không thể tự động hoàn tác những tác dụng đã xảy ra. Dữ liệu đã được tải xuống không thể được thu hồi chỉ bằng khóa phiên; một thay đổi đã commit cũng cần quy trình nghiệp vụ nếu phải bù trừ.

Với hành động nhạy cảm, cần xác định thời điểm chấp nhận quyền, điều kiện phải đúng tại thời điểm ghi và cách xử lý thay đổi đồng thời. Một số hệ thống có thể kiểm tra lại gần điểm thực thi; một số cần cơ chế giao dịch, phiên bản hoặc hủy hợp tác. Không nên hứa việc thu hồi sẽ dừng an toàn mọi tác vụ đang chạy nếu chưa có thiết kế đó.

## 10. Thiết kế giới hạn độ trễ và trạng thái thiếu dữ liệu

Để đánh giá hiệu quả, cần xác định mốc đo cụ thể. Ví dụ:

```text
t0: nguồn quyền có thẩm quyền hoàn tất ghi việc thu hồi
t1: sự kiện được phát hoặc thay đổi được quan sát
t2: bên nhận cập nhật trạng thái và cache liên quan
t3: điểm thực thi bắt đầu từ chối truy cập thuộc phạm vi thu hồi

Độ trễ có hiệu lực tại điểm thực thi = t3 - t0
```

Nếu đo từ lúc quản trị viên bấm nút nhưng nguồn chưa ghi thành công, hoặc chỉ đo đến lúc hàng đợi nhận sự kiện, kết quả không phản ánh đầy đủ thời gian truy cập thực tế còn được chấp nhận.

Yêu cầu độ trễ cần gắn với tài nguyên và đường truy cập. Có thể đặt mục tiêu khác nhau cho thay đổi đặc quyền, truy cập đọc thông thường và tác vụ xử lý hàng loạt. Mục tiêu không được coi là bảo đảm cho đến khi kiểm chứng cả lỗi và các đường thực thi liên quan.

Khi dữ liệu quá cũ hoặc nguồn không sẵn sàng, cần chính sách đã định nghĩa. Đối với thao tác yêu cầu trạng thái đủ mới, không xác minh được điều kiện phải dẫn đến xử lý phù hợp như từ chối hoặc hoãn. Một phạm vi suy giảm được cho phép trước cần có giới hạn, thời hạn và quan sát; không âm thầm chuyển mọi request sang cho phép.

Không coi “chưa nhận sự kiện thu hồi” là bằng chứng rằng quyền chắc chắn chưa bị thu hồi. Muốn sử dụng trạng thái đã biết trong một khoảng thời gian, phải định nghĩa rõ khoảng hiệu lực và mức rủi ro chấp nhận được.

## 11. Nhật ký và tình huống kiểm chứng

Nhật ký nên liên kết được sự thay đổi với quyết định thực tế: nguồn thay đổi, đối tượng ảnh hưởng, phiên bản trạng thái, thời điểm áp dụng, API hoặc kết nối thực thi và kết quả.

Không cần ghi toàn bộ nội dung nhạy cảm của yêu cầu hoặc token để có khả năng truy vết. Định danh tương quan, mã lý do và phiên bản chính sách có thể hỗ trợ điều tra với phạm vi dữ liệu phù hợp.

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Thu hồi vai trò trong khi access token còn hạn | Hành động tương ứng bị chặn theo cơ chế và độ trễ đã thiết kế |
| Người dùng làm thêm MFA sau khi mất quyền | Quyền không tự được khôi phục |
| Từ chối gia hạn token nhưng token cũ còn được gửi | Đường sử dụng token cũ được kiểm soát theo yêu cầu thu hồi |
| Sự kiện đến hai lần | Trạng thái và tác dụng phụ vẫn đúng |
| Sự kiện cũ đến sau sự kiện mới | Không làm trạng thái quay lại phiên bản cũ |
| Một bên nhận bị gián đoạn | Có thể phục hồi, đối soát và quan sát khoảng chậm cập nhật |
| Cache giữ quyết định cho phép cũ | Cơ chế vô hiệu hóa hoặc hết hạn đáp ứng yêu cầu |
| API có đường vào bỏ qua gateway | Quyền vẫn được thực thi ở mọi đường được hỗ trợ |
| Kết nối dài đang truyền dữ liệu khi phiên bị thu hồi | Phản ứng tại nơi giữ kết nối đúng thiết kế |
| Job chạy sau khi người yêu cầu mất quyền | Quyền được đánh giá theo chính sách vòng đời job |
| Một chủ thể có cùng tên ở hai tenant | Chỉ đúng đối tượng và phạm vi bị tác động |
| Nguồn trạng thái không trả lời | Áp dụng chính sách thiếu dữ liệu, không cấp quyền ngoài thiết kế |

Continuous access evaluation có giá trị khi một thay đổi liên quan thực sự làm thay đổi cách tài nguyên chấp nhận truy cập. Để đạt điều đó, cần liên kết vòng đời danh tính, quyền, phiên và tín hiệu ngữ cảnh với cơ chế đồng bộ, cache cùng các điểm thực thi có thể kiểm chứng.
