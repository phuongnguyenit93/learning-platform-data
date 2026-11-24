# Các điều kiện khiến tài khoản không đủ điều kiện khôi phục

## 1. Xác định đúng câu hỏi về điều kiện khôi phục

**Tài khoản không đủ điều kiện — ineligible account — là tài khoản mà chính sách không cho phép thực hiện một thao tác khôi phục cụ thể trong ngữ cảnh và thời điểm đang xét.** Kết luận này cần gắn với mục đích, phương thức và thẩm quyền của luồng, thay vì chỉ là một cờ chung `canRecover=false`.

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, người dùng có thể mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Mục tiêu là giúp đúng người lấy lại quyền kiểm soát bằng một quy trình an toàn. Tuy nhiên, việc người dùng mất phương tiện không tự tạo quyền khôi phục nếu tài khoản đã kết thúc, bị ngăn bởi quyết định có thẩm quyền hoặc không thuộc phạm vi của luồng đang gọi.

Ví dụ:

- Một tài khoản đã xóa không được tự sống lại qua biểu mẫu quên mật khẩu.
- Một tài khoản đăng nhập hoàn toàn qua nhà cung cấp danh tính không nhất thiết được đặt mật khẩu cục bộ.
- Một tài khoản bị vô hiệu hóa bởi tổ chức không được tự mở lại chỉ vì người yêu cầu nhận được OTP.
- Một tài khoản đang hoạt động nhưng không còn bằng chứng phù hợp có thể cần quy trình khác, thay vì được kết luận là tài khoản bị cấm khôi phục vĩnh viễn.

Một quyết định có ý nghĩa cần trả lời:

```text
Tài khoản nào?
Khôi phục quyền gì?
Qua phương thức và kênh nào?
Theo chính sách nào?
Tại thời điểm nào?
Ai hoặc thành phần nào có quyền cho phép tiếp tục?
```

“Không đủ điều kiện cho luồng tự phục vụ đặt lại MFA” và “không có bất kỳ đường xử lý nào” là hai kết luận khác nhau. Hệ thống không nên đánh đồng chúng.

## 2. Phân biệt điều kiện tài khoản với bằng chứng và lỗi vận hành

### 2.1. Các loại kết quả cần tách riêng

| Kết quả nội bộ minh họa | Ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| `ELIGIBLE` | Tài khoản thuộc phạm vi được xem xét cho luồng này | Tiếp tục kiểm tra bằng chứng và các điều kiện còn lại |
| `INELIGIBLE` | Có một quy tắc có thẩm quyền ngăn thao tác được yêu cầu | Không phát hành hoặc sử dụng quyền để vượt quy tắc |
| `DEFERRED` | Chưa được thực hiện lúc này do hạn chế tạm thời | Nêu điều kiện đánh giá lại trong ngữ cảnh được phép |
| `ALTERNATE_FLOW_REQUIRED` | Luồng hiện tại không được phép hoặc không phù hợp, có luồng khác được định nghĩa | Chuyển đúng quy trình có kiểm soát |
| `EVIDENCE_REQUIRED` | Tài khoản có thể được khôi phục nhưng bằng chứng hiện có chưa đủ | Yêu cầu bằng chứng phù hợp, không tự cấp quyền |
| `UNDETERMINED` | Thiếu dữ liệu có thẩm quyền hoặc lỗi dịch vụ nên chưa thể kết luận | Không cho thao tác nhạy cảm đi qua; xử lý lỗi và đánh giá lại |

Các tên trên là quy ước học thuật để diễn đạt sự khác nhau, không bắt buộc triển khai đúng các enum này.

Đặc biệt, `ELIGIBLE` không có nghĩa đã xác minh đúng người. Nó chỉ nói tài khoản và thao tác không bị loại ở lớp điều kiện đang xét. Sau đó vẫn phải xác minh danh tính, hiệu lực token, giới hạn thử, chính sách rủi ro và các điều kiện cấp quyền.

### 2.2. Các trường hợp dễ bị phân loại sai

| Sự kiện | Có thể kết luận tài khoản không đủ điều kiện ngay không? | Lý do |
| --- | --- | --- |
| Người dùng nhập sai OTP | Không | Đây thường là thất bại bằng chứng hoặc tiêu hao ngân sách |
| Token đã hết hạn | Không | Token không còn dùng được, tài khoản có thể vẫn được tạo yêu cầu mới theo chính sách |
| Dịch vụ trạng thái tài khoản bị timeout | Không | Chưa biết điều kiện hiện tại; không nên ghi sai là tài khoản bị cấm |
| Một email không khớp tài khoản nào | Không nên coi là trạng thái của một tài khoản có thật | Đây là không xác định được chủ thể phù hợp |
| Tài khoản đã xóa, luồng là đặt lại mật khẩu thông thường | Có thể từ chối theo quy tắc vòng đời đã định nghĩa | Mục đích của luồng không bao gồm phục hồi tài khoản đã xóa |
| Chính sách yêu cầu kênh khác | Luồng hiện tại có thể không đủ điều kiện | Chưa chứng minh mọi luồng đều bị cấm |

Nếu gộp tất cả vào “tài khoản không đủ điều kiện”, đội hỗ trợ sẽ khó hướng dẫn, số liệu bị lệch và cơ chế tự động có thể khóa nhầm người dùng sau một sự cố hạ tầng.

## 3. Các điều kiện loại trừ theo vòng đời và thẩm quyền

### 3.1. Tài khoản đã kết thúc hoặc không còn chủ thể hợp lệ

Tài khoản đã xóa về mặt nghiệp vụ thường không được phép dùng luồng khôi phục thông thường để nhận lại quyền truy cập. Việc còn một hàng dữ liệu, bản sao lưu hoặc phương tiện cũ không thay đổi quyết định vòng đời.

Nếu sản phẩm hỗ trợ phục hồi tài khoản đã xóa, đó phải là một thao tác riêng với phạm vi, thời hạn, bằng chứng và thẩm quyền rõ ràng. Không để token quên mật khẩu tự chuyển trạng thái tài khoản về hoạt động.

Cũng cần phân biệt tài khoản đã yêu cầu xóa với tài khoản đã xóa. Nếu có thời gian chờ và khả năng hủy, việc hủy phải theo luồng đã định nghĩa. Đăng nhập, đổi mật khẩu hay hoàn tất khôi phục không được âm thầm hủy ý định xóa.

Tài khoản đăng ký lại bằng cùng email cần có quan hệ định danh riêng theo thiết kế. Token hoặc quyết định khôi phục của tài khoản cũ không được áp vào tài khoản mới chỉ vì chuỗi email giống nhau.

### 3.2. Tài khoản bị vô hiệu hóa hoặc đình chỉ

Một nhãn như `DISABLED`, `SUSPENDED` hay `LOCKED` chưa đủ để suy ra mọi quyết định. Cần biết lý do, phạm vi và chủ thể có quyền gỡ.

Ví dụ:

| Tình trạng | Quyết định có thể phù hợp | Điều không được tự suy ra |
| --- | --- | --- |
| Khóa tạm do nhiều lần đăng nhập sai | Có thể cho khôi phục như một đường hợp lệ, tùy chính sách | Không phải mọi tài khoản khóa đều bị cấm khôi phục |
| Vô hiệu hóa bởi quản trị tổ chức | Có thể cấm tự phục vụ hoặc chuyển sang quản trị có thẩm quyền | OTP đúng không tự gỡ quyết định tổ chức |
| Hạn chế vì nghi chiếm đoạt | Có thể yêu cầu quy trình chứng minh mạnh hơn hoặc tạm ngừng thao tác | Một session cũ không đủ chứng minh hạn chế nên bị xóa |
| Đình chỉ toàn bộ quyền sử dụng | Có thể không cho khôi phục dẫn tới cấp quyền sử dụng | Đổi bí mật không mặc nhiên kích hoạt lại |
| Chỉ chặn một kênh bị nghi lộ | Có thể cấm kênh đó nhưng vẫn cho kênh khác đủ điều kiện | Không cần mặc định cấm toàn bộ tài khoản |

Đây là các lựa chọn cần được chính sách xác định, không phải các quy tắc giống nhau cho mọi dịch vụ.

Một thiết kế có thể cho phép thay một bí mật để giảm rủi ro trong khi tài khoản vẫn bị vô hiệu hóa. Khi đó, phạm vi quyền chỉ được phép thay bí mật; không được cấp session sử dụng hoặc xóa quyết định vô hiệu hóa như một tác dụng phụ.

### 3.3. Điều kiện do tổ chức hoặc hệ thống sở hữu tài khoản quyết định

Trong môi trường tổ chức, quyền khôi phục có thể chịu ràng buộc bởi đơn vị quản lý tài khoản, tenant hoặc nhà cung cấp danh tính. Cần xác định nguồn nào có thẩm quyền cho từng điều kiện.

Ví dụ, một người đã rời tổ chức vẫn có thể giữ điện thoại chứa passkey cũ. Bằng chứng sở hữu phương tiện không tự chứng minh họ còn quyền sử dụng tài khoản của tổ chức.

Ngược lại, một nhân viên hỗ trợ ứng dụng không nên có quyền gỡ mọi hạn chế do tổ chức đặt ra chỉ bằng thao tác “reset MFA”. Quyền xử lý sự cố, quyền thay phương tiện và quyền kích hoạt tài khoản phải được phân định.

## 4. Tài khoản không thuộc phạm vi của luồng đang gọi

### 4.1. Tài khoản dùng nhà cung cấp danh tính bên ngoài

Nếu ứng dụng không quản lý mật khẩu cục bộ cho một tài khoản, endpoint đặt lại mật khẩu cục bộ không nên tự tạo mật khẩu để đáp ứng yêu cầu. Điều đó có thể mở một đường đăng nhập mới ngoài quyết định của tổ chức.

Hướng xử lý có thể là chuyển tới quy trình được phép của nhà cung cấp danh tính hoặc quản trị tổ chức. Đích chuyển tiếp cần do hệ thống xác định từ cấu hình có thẩm quyền, không lấy tùy ý từ dữ liệu client.

Không phải mọi tài khoản liên kết đều giống nhau. Một số sản phẩm cho phép cả đăng nhập cục bộ lẫn liên kết. Điều kiện cần dựa vào cấu hình thực tế của đúng tài khoản và thao tác, thay vì chỉ nhìn có một liên kết danh tính ngoài rồi cấm tất cả.

### 4.2. Tài khoản đặc quyền, tài khoản dịch vụ và chủ thể khác người dùng thông thường

Chính sách có thể yêu cầu một quy trình riêng cho quản trị viên đặc quyền hoặc tài khoản phục vụ vận hành. Khi đó, tài khoản không đủ điều kiện cho một biểu mẫu tự phục vụ phổ thông, nhưng vẫn có thể có đường xử lý được phê duyệt.

Tài khoản dịch vụ hay workload có thể không có khái niệm chủ hộp thư cá nhân giống người dùng. Không dùng việc một nhân viên nhận được email làm bằng chứng đủ để cấp lại khóa cho workload có quyền lớn.

Cần mô tả rõ loại chủ thể, người được phép yêu cầu và quyền có thể khôi phục. Không để một checkbox “đây là tài khoản của tôi” biến mọi loại chủ thể thành tài khoản cá nhân.

### 4.3. Tài khoản chưa hoàn tất đăng ký

Một bản ghi đang chờ xác minh email hoặc hoàn tất đăng ký chưa chắc đã có đầy đủ quan hệ tài khoản để thực hiện luồng khôi phục thông thường.

Nếu nhận email đủ để chuyển tài khoản từ chưa xác minh sang hoạt động, cần bảo đảm quy trình không vô tình giữ lại bí mật hoặc phương tiện do một người khác đã cài trước. Đây là vấn đề về ngữ nghĩa hoàn tất đăng ký và quyền sở hữu, không chỉ về việc gửi được một liên kết.

Sản phẩm cần chọn rõ: tiếp tục xác minh đăng ký, khởi động lại đăng ký có kiểm soát hay dùng một quy trình khác. Không coi “quên mật khẩu” là cách bỏ qua mọi điều kiện onboarding.

### 4.4. Không có phương tiện phù hợp với mục đích được yêu cầu

Một tài khoản chỉ có passkey không nhất thiết có mật khẩu để đặt lại. Tương tự, tài khoản không có đăng ký MFA tương ứng không nên được xử lý như thể đang thay thế một phương tiện đó.

Nếu sản phẩm cho phép thêm loại phương tiện mới sau một quy trình khôi phục, quyền thêm phải được phê duyệt rõ. Endpoint “đặt lại” không nên âm thầm biến thành “thêm một cách đăng nhập mới”.

## 5. Các hạn chế tạm thời và bằng chứng chưa đủ

### 5.1. Tạm dừng không đồng nghĩa cấm vĩnh viễn

Các tình huống có thể dẫn tới trì hoãn gồm:

- Một khoảng chờ có chủ đích sau thay đổi bảo mật.
- Yêu cầu khôi phục khác đang xử lý và có quy tắc xử lý xung đột.
- Ngân sách phát hành hoặc xác minh tạm thời đã hết.
- Một hạn chế an ninh có điều kiện đánh giá lại.
- Bước phê duyệt có thẩm quyền chưa hoàn tất.

Cần ghi rõ phạm vi bị trì hoãn và điều kiện xét lại. “Đợi thêm” không phải một quy tắc đủ nếu không biết đợi tới mốc nào hoặc sự kiện nào.

Khi hết thời gian chờ, phải đánh giá lại trạng thái và điều kiện còn lại. Không tự cho phép mọi thao tác chỉ vì đồng hồ đã qua hạn; tài khoản có thể đã bị xóa, bằng chứng có thể hết hiệu lực hoặc hạn chế khác vẫn còn.

### 5.2. Mất kênh không tự chứng minh quyền chọn kênh mới

Người dùng có thể không còn email, số điện thoại, mã dự phòng hay thiết bị cũ. Điều đó cho thấy luồng hiện tại có thể không hoàn tất được, không chứng minh rằng một địa chỉ mới do người yêu cầu nhập nên được tin ngay.

Nếu có quy trình thay thế, cần định nghĩa bằng chứng và thẩm quyền tương ứng. Nếu không có bằng chứng được chấp nhận hoặc sản phẩm không hỗ trợ một đường phù hợp, hệ thống phải từ chối cấp quyền thay vì hạ yêu cầu xác minh chỉ để kết thúc yêu cầu.

Cũng không nên ghi một hạn chế vĩnh viễn vào tài khoản chỉ vì một người không xác thực nói rằng họ đã mất mọi phương tiện. Tác nhân có thể sử dụng lời khai đó để gây gián đoạn cho nạn nhân.

### 5.3. Không để cơ chế chống lạm dụng khóa nạn nhân tùy ý

Nếu một số request sai từ endpoint công khai đủ khiến tài khoản mất quyền khôi phục vĩnh viễn, người biết email có thể làm nạn nhân bị từ chối dịch vụ.

Giới hạn thử cần có phạm vi và thời gian phù hợp, kết hợp nhiều chiều và đường xử lý an toàn cho người dùng hợp lệ. Phân biệt tiêu hao lượt của một challenge với quyết định vô hiệu hóa tài khoản.

Việc chuyển luồng hoặc tạo request mới cũng không được đặt lại vô hạn ngân sách đoán. Bảo vệ khả năng khôi phục hợp lệ và chống bot phải được giải quyết cùng nhau.

### 5.4. Tín hiệu rủi ro không phải kết luận danh tính

IP lạ, thiết bị mới hoặc vị trí khác có thể làm tăng yêu cầu xác minh. Chúng không tự chứng minh người dùng là kẻ tấn công. Một người mất điện thoại thường phải dùng thiết bị khác để khôi phục.

Ngược lại, thiết bị quen thuộc không nên ghi đè một quyết định đã xóa hoặc vô hiệu hóa tài khoản. Tín hiệu rủi ro và điều kiện có thẩm quyền phải có cách kết hợp rõ ràng, không lấy một điểm số thuận lợi để bỏ qua điều kiện cấm.

## 6. Mô hình quyết định và thứ tự ưu tiên

### 6.1. Đầu vào cần có nguồn có thẩm quyền

Một lần đánh giá có thể cần các nhóm dữ liệu:

| Nhóm dữ liệu | Ví dụ | Nguồn không nên tin thay thế |
| --- | --- | --- |
| Danh tính tài khoản | ID nội bộ, tenant, loại chủ thể | Email hoặc ID tùy ý do client tự khẳng định |
| Vòng đời | Hoạt động, đang xóa, đã xóa | Cờ trạng thái trong trình duyệt |
| Hạn chế | Lý do, phạm vi, chủ thể ban hành, revision | Một boolean do trang hỗ trợ tự tính |
| Phương thức đăng nhập | Cục bộ, liên kết, phương tiện đã đăng ký | Tên nút mà người dùng bấm |
| Chính sách | Mục đích, nhóm tài khoản, quy tắc chuyển tiếp | Phiên bản client tự chọn |
| Trạng thái bảo mật hiện tại | Mốc thu hồi, thay đổi gần đây, yêu cầu đang xử lý | Ảnh chụp cũ không được kiểm tra độ mới |
| Bằng chứng | Loại, ràng buộc, kết quả và thời điểm xác minh | Lời khai “đã xác minh” từ client |

Nếu dữ liệu quan trọng không đọc được hoặc không còn đủ mới theo bảo đảm đã định nghĩa, không nên mặc định tài khoản đủ điều kiện. Cần trả một kết quả chưa xác định hoặc xử lý suy giảm đã được phê duyệt.

Sự thiếu dữ liệu cũng không được biến thành một lệnh đánh dấu tài khoản vĩnh viễn không đủ điều kiện. Khi dịch vụ phục hồi, yêu cầu có thể được đánh giá lại từ dữ liệu có thẩm quyền.

### 6.2. Kết hợp nhiều quy tắc mà không ghi đè hạn chế

Một tài khoản có thể đồng thời có khóa tạm đăng nhập, hạn chế quản trị và yêu cầu xóa. Việc xử lý xong một điều kiện không tự gỡ các điều kiện còn lại.

Ví dụ:

```text
Đã nhận OTP đúng
    không xóa quyết định vô hiệu hóa của tổ chức

Đã hết thời gian chờ
    không bỏ qua trạng thái đã xóa

Đã đổi sang thiết bị quen thuộc
    không khôi phục kênh đã bị thu hồi

Đã được nhân viên hỗ trợ xác nhận một bằng chứng
    không tự cho phép tạo loại phương tiện bị chính sách cấm
```

Quy tắc cấm có thẩm quyền phải được thực thi trong phạm vi mà nó chi phối. Một điều kiện cho phép ở phạm vi hẹp không được ghi đè lệnh cấm rộng hơn chỉ vì được chạy sau trong mã nguồn.

Ngược lại, lệnh cấm một kênh không nên tự mở rộng thành cấm mọi mục đích nếu chính sách không quy định như vậy. Cần giữ nguyên phạm vi để tránh vừa mở quyền sai vừa chặn nhầm.

### 6.3. Mã giả minh họa

```text
evaluateEligibility(accountReference, purpose, flow, context):
    account = resolveAuthoritativeAccount(accountReference)

    nếu không xác định được tài khoản phù hợp:
        trả kết quả nội bộ không tìm thấy chủ thể
        ánh xạ sang phản hồi công khai không tiết lộ tài khoản

    policy = selectServerControlledPolicy(account, purpose, flow)
    facts = loadRequiredCurrentFacts(account, policy)

    nếu không đủ dữ liệu bắt buộc để đánh giá:
        trả UNDETERMINED, không cấp quyền

    nếu có quy tắc cấm mục đích đang yêu cầu:
        trả INELIGIBLE với phạm vi và lý do nội bộ

    nếu có hạn chế tạm thời liên quan:
        trả DEFERRED với điều kiện đánh giá lại

    nếu flow hiện tại không được phép:
        nếu có luồng thay thế được chính sách cho phép:
            trả ALTERNATE_FLOW_REQUIRED
        nếu không:
            trả INELIGIBLE cho flow và mục đích đang xét

    nếu bằng chứng hiện tại chưa đủ:
        trả EVIDENCE_REQUIRED

    trả ELIGIBLE cho đúng tài khoản, mục đích và ngữ cảnh đã đánh giá
```

Thứ tự này là ví dụ của một chính sách, không phải thuật toán phổ quát. Hệ thống thực cần định nghĩa cách xử lý khi nhiều điều kiện cùng đúng và lý do nào được chọn để hiển thị cho từng đối tượng.

Một kết quả `ELIGIBLE` tại đây vẫn không phải quyền truy cập. Nó cần được kết hợp với quyết định xác minh và cấp quyền ở điểm thực hiện thao tác.

### 6.4. Kết quả có phạm vi và thời điểm

Thay vì chỉ lưu một boolean, có thể mô tả kết quả bằng:

```text
decision_id
account_id
tenant_id
recovery_purpose
flow_id
policy_id
account_revision
restriction_revision
evaluated_at
decision
reason_code
permitted_next_step
reevaluation_condition
```

Đây là mô hình dữ liệu khái niệm. Không nhất thiết mọi trường phải thành cột riêng, nhưng ý nghĩa tương ứng cần có trong thiết kế.

Không nên trao kết quả này cho client rồi tin vô thời hạn. Nếu cần một quyết định có thể dùng lại, phải ràng buộc đúng đối tượng, mục đích, thời hạn, tính toàn vẹn và điều kiện kiểm tra lại. Thời điểm vừa đánh giá không bảo đảm tài khoản sẽ không thay đổi ngay sau đó.

## 7. Thực thi điều kiện ở mọi điểm tạo quyền

### 7.1. Không chỉ kiểm tra ở biểu mẫu đầu tiên

Các điểm sau có thể cần đánh giá hoặc xác nhận lại điều kiện liên quan:

1. Khi tiếp nhận và lựa chọn luồng có thể dùng.
2. Trước khi phát hành bằng chứng hoặc token cho một tài khoản.
3. Khi chấp nhận bằng chứng khôi phục.
4. Khi cấp quyền thiết lập phương tiện.
5. Khi thực hiện thay đổi cuối.
6. Khi cấp session hoặc quyền sử dụng sau khôi phục.

Mức kiểm tra tại từng điểm phụ thuộc kiến trúc và tác động của thao tác. Điều không được phép là chỉ kiểm tra một lần ở giao diện rồi cho mọi endpoint sau tin ảnh chụp đó.

Nếu người dùng đi qua API di động, công cụ hỗ trợ hoặc một luồng khác, các quyết định có thẩm quyền vẫn phải được áp dụng. Một đường ít được dùng không nên trở thành nơi bỏ qua điều kiện tài khoản.

### 7.2. Token đúng nhưng tài khoản đã không còn đủ điều kiện

Giả sử request được tạo khi tài khoản hoạt động. Token còn thời hạn, chưa dùng và đúng mục đích. Trước khi token được sử dụng, quản trị có thẩm quyền vô hiệu hóa tài khoản.

Nếu chính sách hiện tại cấm thao tác đó cho tài khoản bị vô hiệu hóa, token phải bị từ chối hoặc chuyển sang quy trình tương ứng. Thời hạn token chỉ là một điều kiện, không phải cam kết rằng mọi quyền khôi phục sẽ giữ nguyên tới lúc hết hạn.

Điều tương tự áp dụng khi tài khoản bị xóa, phương tiện bị thu hồi hoặc có quyết định bảo mật mới. Token không nên chứa một bản sao `eligible=true` rồi được dùng để bỏ qua nguồn trạng thái hiện hành.

### 7.3. Tránh lỗi kiểm tra xong rồi trạng thái đổi

Một kịch bản chạy đua:

```text
T1: Recovery đọc tài khoản đang hoạt động
T2: Quản trị ghi hạn chế cấm khôi phục
T3: Recovery thay MFA theo ảnh chụp ở T1
```

Nếu yêu cầu là hạn chế tại T2 phải ngăn thay đổi tại T3, lần ghi cuối cần kiểm tra điều kiện có thẩm quyền tương ứng. Có thể dùng revision trạng thái, mốc bảo mật, cập nhật có điều kiện hoặc cơ chế phối hợp phù hợp.

Một giao dịch cục bộ không tự làm dữ liệu ở hệ thống quản trị bên ngoài trở nên nhất quán. Với cache, thông điệp đồng bộ hoặc nhiều dịch vụ, cần nêu độ trễ và bảo đảm thực tế. Nếu không thể xác nhận điều kiện bắt buộc còn phù hợp, không tự cho thao tác nhạy cảm đi qua.

Khi bị xung đột, đánh giá lại hoặc từ chối theo chính sách. Không sửa trạng thái tài khoản về `ACTIVE` để làm cho giao dịch khôi phục thành công.

### 7.4. Thu hồi quyền đã cấp và xử lý phần còn lại

Khi tài khoản trở thành không đủ điều kiện, cần xác định các token, quyền thiết lập và request đang chạy bị ảnh hưởng. Cơ chế vô hiệu hóa có thể dựa vào trạng thái lưu, mốc thu hồi hoặc điều kiện kiểm tra tại điểm sử dụng.

Một quyền đã phát hành nhưng chưa dùng không nên tiếp tục cấp thay đổi chỉ vì không có tác vụ nền nào kịp xóa nó. Điểm sử dụng phải tôn trọng cơ chế thu hồi đã thiết kế.

Nếu thay đổi đã hoàn tất trước hạn chế, xử lý session, phương tiện và hậu quả là một quyết định riêng theo thẩm quyền hiện tại. Không coi việc ghi một lý do từ chối mới là tự động đảo ngược mọi thao tác trước đó.

## 8. Phản hồi an toàn và đường xử lý tiếp theo

### 8.1. Tách lý do nội bộ khỏi thông điệp công khai

Một endpoint công khai không nên cho biết ngay rằng email thuộc tài khoản đã xóa, bị đình chỉ hay đang thuộc một tenant cụ thể.

Ví dụ thông điệp tiếp nhận:

> Nếu thông tin phù hợp với một phương thức được hỗ trợ, hướng dẫn tiếp theo sẽ được gửi qua kênh tương ứng.

Câu chữ cụ thể cần phù hợp sản phẩm và trạng thái thực. Không được hứa sẽ gửi nếu hệ thống không có ý định gửi; một thông điệp điều kiện phải phản ánh đúng ý nghĩa điều kiện đó.

Tính riêng tư cần xét cả mã HTTP, cấu trúc phản hồi, thời gian xử lý, hành vi giới hạn và các endpoint truy vấn trạng thái. Chỉ dùng cùng một câu trên giao diện chưa đủ nếu API trả một mã lý do riêng cho từng trạng thái tài khoản.

Ở backend vẫn cần lý do cụ thể để điều tra. Ẩn thông tin với người không có quyền không có nghĩa xóa khả năng giải thích quyết định.

### 8.2. Thông tin chi tiết theo đúng quyền được biết

Trong một ngữ cảnh đã được xác minh phù hợp, có thể cần hướng dẫn cụ thể hơn:

| Kết quả | Nội dung có thể phù hợp trong ngữ cảnh được phép |
| --- | --- |
| Luồng cục bộ không hỗ trợ tài khoản | Chỉ tới quy trình đăng nhập hoặc quản trị có thẩm quyền |
| Cần bổ sung bằng chứng | Nêu bước tiếp theo và giới hạn của quyền hiện tại |
| Đang chờ điều kiện thời gian | Nêu mốc hoặc điều kiện đánh giá lại mà hệ thống thực thi |
| Có hạn chế quản trị | Hướng tới chủ thể có quyền xem và xử lý hạn chế |
| Không còn đường được hỗ trợ | Nêu giới hạn rõ, không hứa có thể lấy lại bằng mọi cách |
| Chưa xác định do lỗi vận hành | Thông báo chưa thể xử lý và hướng kiểm tra lại an toàn |

Ngay cả ở đây, không cần tiết lộ toàn bộ dữ liệu điều tra hay mọi quy tắc chống gian lận. Quyền nhận thông tin phải tách khỏi quyền thay đổi tài khoản.

### 8.3. Hỗ trợ thủ công không phải quyền ghi đè mọi điều kiện

Một quy trình hỗ trợ cần biết:

- Nhân viên được xem lý do nào.
- Bằng chứng nào được thu thập và chấp nhận.
- Ai có quyền gỡ từng loại hạn chế.
- Quyết định nào cần phê duyệt khác.
- Quyền nào được cấp sau khi xử lý.

Nếu tổ chức chưa kích hoạt lại tài khoản, việc hỗ trợ xác minh đúng người không tự khôi phục tư cách thành viên. Nếu tài khoản đã xóa và không có quy trình phục hồi được phép, không nên dùng nút reset mật khẩu để mở đường quay lại.

Không yêu cầu người dùng gửi mật khẩu, OTP đang dùng hoặc mã dự phòng cho nhân viên như cách chứng minh mặc định. Quy trình chứng minh cần được thiết kế riêng, giảm thu thập bí mật và có khả năng kiểm tra.

## 9. Các tình huống minh họa

### 9.1. Mất MFA nhưng tài khoản bị vô hiệu hóa bởi tổ chức

Bình mất điện thoại chứa MFA và vẫn kiểm soát email. Tổ chức đã vô hiệu hóa tài khoản trước đó vì Bình không còn quyền sử dụng hệ thống.

Bình nhận được mã email không làm thay đổi quyền sử dụng. Nếu chính sách cấm tự phục vụ trong tình trạng đó, backend không cấp quyền thay MFA dẫn tới đăng nhập. Quy trình tổ chức, nếu có, phải quyết định việc kích hoạt và quyền được cấp.

Ở đây, vấn đề không chỉ là “MFA có được đặt lại không”. Cần ngăn việc đặt lại phương tiện âm thầm khôi phục quyền thành viên hoặc session.

### 9.2. Tài khoản hoạt động nhưng luồng đặt mật khẩu cục bộ không được phép

Chi đăng nhập qua nhà cung cấp danh tính do tổ chức quản lý. Ứng dụng không cho tài khoản này có mật khẩu cục bộ.

Khi Chi dùng biểu mẫu quên mật khẩu của ứng dụng, kết quả cho luồng cục bộ là không phù hợp hoặc cần luồng khác. Backend không tạo một mật khẩu mới chỉ vì Chi kiểm soát email.

Nếu định tuyến tới nhà cung cấp danh tính, ứng dụng chọn đích từ cấu hình đáng tin cậy. Người yêu cầu không được chèn một URL khác để biến hướng dẫn khôi phục thành chuyển hướng phishing.

### 9.3. Token hợp lệ nhưng tài khoản đã bị xóa

Dũng được cấp token khi tài khoản còn hoạt động. Sau đó một quyết định xóa có hiệu lực. Dũng hoặc người giữ token mở liên kết trước hạn hết token.

Token không được phép đặt lại mật khẩu rồi ghi tài khoản về hoạt động. Nếu có một quy trình phục hồi tài khoản đã xóa, người yêu cầu phải đi qua đúng quy trình đó, với điều kiện và thẩm quyền riêng.

Nếu sau này một tài khoản mới dùng cùng email được tạo, token của tài khoản cũ không được áp vào tài khoản mới.

### 9.4. Lỗi đọc trạng thái không phải tài khoản bị cấm

Hà đủ bằng chứng nhưng dịch vụ quản lý hạn chế đang lỗi. Backend chưa xác nhận được tài khoản có bị một quyết định chặn hiện hành hay không.

Không tự cho phép vì bằng chứng đã tốt. Đồng thời, không ghi `account_permanently_ineligible=true` chỉ để kết thúc request. Kết quả phù hợp là chưa xác định, ngăn thao tác nhạy cảm theo chính sách và đánh giá lại khi có dữ liệu.

### 9.5. Bot cố tiêu hao khả năng khôi phục

Một bot biết email của Mai, tạo request rồi nhập sai liên tục. Nếu hệ thống gắn mọi sai OTP thành lệnh cấm tài khoản vĩnh viễn, bot đã đạt mục tiêu mà không cần đoán đúng.

Thiết kế cần giới hạn lượt thử có kiểm soát, giữ lịch sử lạm dụng cần thiết qua request mới và có hướng xử lý an toàn cho Mai. Không nới vô hạn lượt đoán, cũng không dùng lời khai từ nguồn công khai để tước quyền khôi phục lâu dài của nạn nhân.

## 10. Dấu vết quyết định và quan sát vận hành

### 10.1. Ghi lý do có cấu trúc

Có thể dùng mã lý do nội bộ như:

```text
ACCOUNT_LIFECYCLE_BLOCKS_PURPOSE
ADMINISTRATIVE_RESTRICTION_ACTIVE
LOCAL_RECOVERY_NOT_SUPPORTED
ACCOUNT_TYPE_REQUIRES_DEDICATED_FLOW
TEMPORARY_RECOVERY_HOLD
REQUIRED_EVIDENCE_NOT_AVAILABLE
AUTHORITATIVE_STATE_UNAVAILABLE
```

Đây là các tên minh họa cho mã lý do trong hệ thống khôi phục. Mã lý do cần đi kèm phạm vi và kết quả để tránh hiểu mọi lý do đều là `INELIGIBLE`.

Dấu vết nên đủ cho việc xác định tài khoản nội bộ, mục đích, luồng, phiên bản chính sách, trạng thái hoặc revision liên quan, thời điểm và quyết định. Không ghi OTP, token, mật khẩu hay bằng chứng nhạy cảm không cần thiết.

Nếu có nhiều hạn chế, cần lưu đủ để giải thích vì sao gỡ một hạn chế vẫn chưa cho phép tiếp tục. Việc chọn một lý do hiển thị chính không nên làm mất các điều kiện còn hiệu lực.

### 10.2. Tách số liệu từ chối và chưa xác định

Các nhóm đáng theo dõi gồm:

- Bị loại bởi vòng đời hoặc hạn chế có thẩm quyền.
- Chuyển sang quy trình khác.
- Thiếu bằng chứng.
- Tạm hoãn do ngân sách hoặc điều kiện thời gian.
- Chưa xác định vì lỗi đọc trạng thái hoặc chính sách.
- Bị từ chối tại điểm cuối do điều kiện đã thay đổi.

Nếu số `UNDETERMINED` tăng sau một lỗi hạ tầng, không nên báo rằng người dùng đột nhiên vi phạm điều kiện khôi phục nhiều hơn. Nếu số từ chối ở API cũ thấp bất thường, cần xét khả năng đường đó bỏ qua quy tắc, thay vì vội coi là trải nghiệm tốt hơn.

Theo dõi theo nhóm và loại luồng trong phạm vi dữ liệu được phép. Không xuất chi tiết trạng thái tài khoản ra dashboard công khai hoặc phản hồi ẩn danh.

## 11. Các thuộc tính cần giữ trong đặc tả

| Tình huống | Thuộc tính cần bảo đảm |
| --- | --- |
| Tài khoản đủ điều kiện nhưng người yêu cầu chưa có bằng chứng | Không cấp quyền chỉ dựa vào kết quả eligibility |
| Tài khoản bị một quyết định cấm thao tác có thẩm quyền | Token đúng hoặc thiết bị quen thuộc không bỏ qua quyết định |
| Tài khoản chỉ bị cấm một kênh | Không tự suy cấm mọi luồng, cũng không tự cho phép kênh khác chưa được phê duyệt |
| Tài khoản liên kết không có đường mật khẩu cục bộ được phép | Không tạo thêm cách đăng nhập bằng endpoint reset |
| Tài khoản đang đăng ký dở | Không dùng recovery để bỏ qua ngữ nghĩa xác minh và sở hữu tài khoản |
| Thời gian chờ kết thúc | Đánh giá lại các điều kiện còn lại trước khi cấp quyền |
| Dữ liệu có thẩm quyền không đọc được | Không mặc định cho phép và không gắn lệnh cấm vĩnh viễn sai |
| Trạng thái đổi sau lần đánh giá đầu | Điểm cấp quyền hoặc ghi thay đổi thực thi điều kiện hiện hành theo bảo đảm đã định |
| Hỗ trợ thủ công tham gia | Chỉ chủ thể đúng thẩm quyền mới gỡ được hạn chế tương ứng |
| Bot gửi sai bằng chứng hàng loạt | Không dễ biến lỗi công khai thành mất quyền khôi phục vĩnh viễn của nạn nhân |
| Tài khoản cũ đã xóa, email được dùng lại | Không áp token hoặc quyết định của tài khoản cũ vào chủ thể mới |
| Người không xác thực dò trạng thái | Không nhận được lý do nội bộ hoặc thông tin tài khoản ngoài quyền được biết |

Điều kiện không đủ khôi phục cần được mô hình hóa thành một quyết định có phạm vi, lý do và nguồn thẩm quyền. Khi đó, hệ thống mới có thể từ chối đúng thao tác, hướng người dùng tới đường phù hợp và ngăn một token hợp lệ trở thành cách vượt qua vòng đời hay hạn chế của tài khoản.
