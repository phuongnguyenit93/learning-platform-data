# Dual control — Kiểm soát hai người trong truy cập break-glass

## 1. Dual control bảo vệ quyết định nào?

**Dual control** là cơ chế yêu cầu sự tham gia có thẩm quyền của ít nhất hai người độc lập tại một điểm kiểm soát được xác định, để một cá nhân không thể tự hoàn tất hành động nhạy cảm đó.

Trong truy cập khẩn cấp (break-glass), điểm kiểm soát có thể là:

- Chấp thuận kích hoạt quyền khẩn cấp.
- Mở khả năng sử dụng một credential.
- Cho phép một phiên quản trị đặc biệt.
- Kích hoạt một khóa hoặc phương tiện dự phòng.
- Chấp thuận mở rộng phạm vi hoặc gia hạn truy cập.

Điều quan trọng là phải nói rõ **hai người kiểm soát việc gì**. Có hai tên trong hồ sơ không chứng minh rằng hai người đã cùng kiểm soát việc cấp quyền.

Ví dụ:

~~~text
Người vận hành đề nghị truy cập khẩn cấp một hệ thống.
Một người độc lập có thẩm quyền kiểm tra phạm vi và chấp thuận.
Hệ thống chỉ cấp quyền khi đủ cả hai sự tham gia bắt buộc.
~~~

Đây có thể là một mô hình kiểm soát hai người nếu chính sách xác định rõ vai trò, tính độc lập và cổng thực thi. Nếu chính sách yêu cầu hai người phê duyệt độc lập ngoài người vận hành, tổng số cá nhân cần thiết sẽ là ít nhất ba.

Mục tiêu trong PAM là giảm khả năng tự ý sử dụng quyền khẩn cấp, tăng khả năng phát hiện sai phạm vi và tạo trách nhiệm rõ ràng. Dual control không tự loại bỏ thông đồng, không thay thế MFA và không thay thế việc thu hồi quyền sau sử dụng.

## 2. Phân biệt dual control với các cơ chế gần giống

| Cơ chế | Câu hỏi được giải quyết | Điều không tự bảo đảm |
|---|---|---|
| MFA | Chủ thể có cung cấp đủ yếu tố xác thực không? | Có hai người độc lập tham gia quyết định |
| Phê duyệt | Có quyết định có thẩm quyền cho yêu cầu không? | Điểm thực thi thực sự bắt buộc đủ người |
| Dual control | Một cá nhân có bị ngăn tự hoàn tất hành động nhạy cảm không? | Mọi lần sử dụng tiếp theo đều cần hai người nếu thiết kế không yêu cầu |
| Split knowledge | Mỗi người chỉ biết một phần bí mật hoặc thông tin cần thiết | Hệ thống đích đang xác thực bằng nhiều yếu tố |
| Quorum m-of-n | Có đủ m thành viên hợp lệ trong n thành viên không? | Các thành viên là các cá nhân khác nhau nếu không kiểm tra |
| Hậu kiểm | Hoạt động đã xảy ra có được xem xét không? | Có quyết định thứ hai trước lúc cấp quyền |

### 2.1. Hai yếu tố của một người không phải hai người

Một người dùng mật khẩu và security key vẫn là một người. Đó có thể là MFA, nhưng chưa phải dual control.

Ngược lại, hai người cùng đồng ý không có nghĩa tài khoản thực thi đã được xác thực an toàn. Mỗi người cần cơ chế xác thực phù hợp với vai trò của mình.

### 2.2. Hai tài khoản không nhất thiết là hai cá nhân

Một người có thể giữ hai tài khoản, hai vai trò hoặc hai thiết bị. Nếu chính sách yêu cầu người độc lập, không được tính hai lần cùng cá nhân chỉ vì họ đăng nhập bằng hai account.

Việc ánh xạ account sang cá nhân cần dựa trên nguồn quản trị danh tính có thẩm quyền. Không để người dùng tự khai rằng hai account thuộc hai người khác nhau.

### 2.3. Tách mật khẩu không tự tạo MFA

Chia mật khẩu thành hai phần và giao hai người giữ có thể hỗ trợ kiểm soát việc lấy bí mật. Khi ghép lại, hệ thống đích vẫn có thể chỉ xác thực bằng một mật khẩu.

Sau khi một người đã biết toàn bộ mật khẩu, lần sử dụng sau có thể không cần người còn lại. Vì vậy cần quản lý việc tiết lộ, thời hạn, thu hồi và thay credential theo thiết kế.

Không gọi mọi hình thức chia giữ bí mật là một cơ chế threshold mật mã. Nếu cần cơ chế mật mã, phải dùng giải pháp được thiết kế và quản trị phù hợp, không tự tạo thuật toán chia hoặc ghép bí mật.

## 3. Xác định cổng kiểm soát trước khi triển khai

### 3.1. Một quy trình có nhiều điểm nhạy cảm

Ví dụ vòng đời break-glass:

~~~text
Yêu cầu
    → chấp thuận
    → lấy hoặc mở quyền sử dụng credential
    → tạo phiên
    → thao tác
    → gia hạn hoặc mở rộng
    → thu hồi
    → hậu kiểm
~~~

Dual control có thể được đặt ở một hoặc nhiều bước, tùy rủi ro.

Nếu chỉ yêu cầu hai người để mở kho bí mật vào đầu ca trực, không nên tuyên bố mọi lần checkout sau đó đều có hai người phê duyệt.

Tương tự, quorum để mở khóa một vault hoặc kích hoạt một khóa không tự là phê duyệt cho từng yêu cầu truy cập ứng dụng.

### 3.2. Các mô hình minh họa

| Mô hình | Điểm được kiểm soát | Giới hạn cần nhận biết |
|---|---|---|
| Người vận hành và một người duyệt độc lập | Kích hoạt yêu cầu hoặc quyền cụ thể | Cần ràng buộc quyết định vào đúng phạm vi |
| Hai người duyệt ngoài người vận hành | Quyết định cấp quyền rủi ro cao | Cần ít nhất ba cá nhân nếu không cho chồng vai trò |
| Hai người giữ phương tiện | Lấy hoặc kích hoạt phương tiện dự phòng | Không tự kiểm soát mọi hành động sau khi phương tiện đã mở |
| Quorum cho từng lần release | Phát hành một lần quyền hoặc credential | Phải kiểm soát retry, phiên bản và sử dụng lại |
| Giám sát trực tiếp hai người | Theo dõi thao tác trong thời gian xác định | Không thay thế cổng kỹ thuật nếu người vận hành vẫn tự làm ngoài phạm vi |

Các mô hình có thể kết hợp. Chính sách phải ghi đúng mức bảo đảm thực tế, không dùng một tên chung để che các giới hạn.

### 3.3. Chọn mức kiểm soát theo tác động

Một credential có thể quản trị nền tảng danh tính hoặc thay đổi PAM có ảnh hưởng khác với một tác vụ restart giới hạn.

Cần cân nhắc:

- Phạm vi tài nguyên.
- Khả năng sửa quyền hoặc tạo đường truy cập mới.
- Credential có được tiết lộ hay không.
- Thời lượng và khả năng thu hồi.
- Khả năng quan sát trên đích.
- Hậu quả khi không khôi phục dịch vụ kịp thời.
- Khả năng đường thường đã bị xâm nhập thay vì chỉ bị lỗi.

Không có một số người hoặc một mô hình quorum phù hợp cho mọi tình huống.

## 4. Vai trò, thẩm quyền và tính độc lập

### 4.1. Phân công vai trò rõ ràng

Một mô hình có thể gồm:

- **Người vận hành:** cần quyền để xử lý sự cố.
- **Người có thẩm quyền quyết định:** xem xét lý do và phạm vi.
- **Người giữ phương tiện:** quản lý việc lấy khóa hoặc bí mật dự phòng.
- **Điều phối viên sự cố:** xác định tình trạng và phối hợp.
- **Người hậu kiểm:** đối chiếu sử dụng thực tế và điều kiện kết thúc.

Không nhất thiết mọi vai trò luôn là một người riêng. Tuy nhiên, các tổ hợp bị cấm phải được xác định và thực thi.

Ví dụ, nếu yêu cầu người duyệt độc lập với người vận hành, việc người vận hành đồng thời là chủ hệ thống không tự cho phép họ duyệt chính yêu cầu.

### 4.2. Kiểm tra thẩm quyền đối với đúng tài nguyên

Người duyệt cần có thẩm quyền với hệ thống, loại quyền và mức rủi ro liên quan.

Một chủ ứng dụng không tự được chấp thuận việc thay chính sách IdP. Người giữ chìa khóa vật lý cũng không tự có quyền quyết định mọi truy cập chỉ vì họ có thể lấy phương tiện.

Vai trò giữ phương tiện và vai trò chấp thuận rủi ro có thể khác nhau.

### 4.3. Ủy quyền không được làm mất tính độc lập

Ủy quyền nên có phạm vi, thời gian và cơ sở rõ ràng. Người nhận ủy quyền vẫn phải đáp ứng điều kiện không xung đột với người vận hành.

Một người không được tính hai lần bằng vai trò gốc và vai trò được ủy quyền nếu yêu cầu là hai cá nhân.

Khi ghi bằng chứng, lưu người thực sự quyết định cùng liên kết ủy quyền. Không ghi như thể người ủy quyền đã trực tiếp tham gia.

### 4.4. Quản trị viên hệ thống cũng có thể tạo đường bỏ qua

Nếu một quản trị viên PAM có thể:

- Sửa số người cần duyệt.
- Tự đưa mình vào nhóm hợp lệ.
- Đọc trực tiếp mọi secret.
- Bỏ qua cổng release.
- Xóa hoặc sửa bằng chứng.

thì họ có thể làm mất hiệu lực của dual control.

Cần xem xét quyền cấu hình, truy cập lưu trữ, khóa mã hóa, backup, runner và đường trực tiếp tới đích. Việc hệ thống có một màn hình “hai người duyệt” chưa chứng minh một cá nhân không thể đi vòng.

## 5. Phạm vi quyết định phải cụ thể và có phiên bản

### 5.1. Hai người phải đồng ý với cùng một nội dung

Một quyết định nên gắn với:

- Request ID và phiên bản.
- Người vận hành.
- Tài nguyên và môi trường.
- Action hoặc role.
- Credential hoặc tập quyền được release.
- Phương thức truy cập.
- Khoảng thời gian.
- Điều kiện giám sát và xử lý sau sử dụng.
- Chính sách áp dụng.

Nếu người thứ nhất duyệt restart một dịch vụ, còn người thứ hai nhìn thấy yêu cầu full administrator trên cả cụm, không thể cộng hai quyết định đó thành đủ quorum cho một nội dung chung.

### 5.2. Thay đổi yêu cầu cần được xử lý

Ví dụ:

~~~text
Phiên bản 1:
    một hệ thống, một action, 20 phút

Phiên bản 2:
    thêm hệ thống, thêm quyền hoặc kéo dài thời gian
~~~

Quyết định của phiên bản 1 không tự áp dụng cho phiên bản 2.

Có thể dùng phiên bản yêu cầu và một biểu diễn chuẩn hóa để phát hiện thay đổi. Một bản băm nội dung có thể hỗ trợ đối chiếu, nhưng không thay thế xác thực người duyệt, thẩm quyền hoặc bảo vệ bản ghi.

Cách xử lý thay đổi thu hẹp phạm vi cũng cần được quy định. Không tự suy ra hai role khác tên có quan hệ ít quyền hơn.

### 5.3. Thông tin đủ để quyết định, không tiết lộ secret

Người duyệt cần thấy quyền và tác động, không nhất thiết cần thấy mật khẩu hoặc private key.

Một màn hình chỉ có nút “Approve emergency” không giúp đánh giá tốt. Hồ sơ nên thể hiện vì sao đường thường không dùng được, tài nguyên nào cần khôi phục và giới hạn kết thúc.

Không đặt secret vào comment để hai người cùng “xác nhận đúng mật khẩu”.

### 5.4. Phê duyệt muộn không tự kéo dài cửa sổ

Nếu cửa sổ được đề nghị kết thúc lúc 02:20 và người cuối cùng duyệt lúc 02:05, quyền chỉ còn trong phần thời gian hợp lệ, trừ khi có quyết định mới thay đổi cửa sổ.

Không tự cộng lại toàn bộ thời lượng từ lúc đạt quorum. Nếu đã hết khoảng hiệu lực, không kích hoạt theo yêu cầu cũ.

## 6. Luồng cấp quyền có kiểm soát hai người

~~~mermaid
flowchart TD
    A[Tạo yêu cầu khẩn cấp có phạm vi và phiên bản] --> B[Xác thực người vận hành và phân giải tuyến thẩm quyền]
    B --> C[Thu thập các quyết định độc lập bắt buộc]
    C --> D{Đủ người, đúng vai trò và cùng phiên bản?}
    D -- Chưa --> E[Giữ chờ, từ chối hoặc hết hạn theo chính sách]
    D -- Đủ --> F[Đánh giá lại trạng thái trước release]
    F --> G{Còn hợp lệ và đúng cửa sổ?}
    G -- Không --> E
    G -- Có --> H[Cấp phiên hoặc quyền khẩn cấp có giới hạn]
    H --> I[Giám sát thao tác và mọi thay đổi phạm vi]
    I --> J[Thu hồi và xác minh trên các điểm thực thi]
    J --> K[Hậu kiểm và khôi phục trạng thái sẵn sàng]
~~~

### 6.1. Phân biệt đã duyệt với đã có quyền

Một yêu cầu đạt đủ người duyệt chưa chứng minh quyền đã được cấp.

Cần phân biệt các trạng thái như:

| Trạng thái minh họa | Ý nghĩa |
|---|---|
| PENDING_CONTROL | Chưa đủ sự tham gia bắt buộc |
| READY_FOR_RELEASE | Đủ điều kiện quyết định, chưa khẳng định đã cấp quyền |
| ACTIVE | Quyền hoặc phiên đã được tạo và còn hiệu lực |
| RELEASE_OUTCOME_UNKNOWN | Chưa biết thao tác release đã hoàn tất hay chưa |
| REVOCATION_PENDING | Đã yêu cầu thu hồi nhưng chưa xác minh hoàn tất |
| ACCESS_ENDED | Quyền đã được kết thúc theo bằng chứng |
| REVIEW_PENDING | Còn hậu kiểm hoặc công việc quản trị sau sử dụng |
| CLOSED | Đạt điều kiện đóng hồ sơ |

Một triển khai có thể dùng tên hoặc mô hình trạng thái khác. Điều quan trọng là không gộp quyết định, cấp quyền, thu hồi và hậu kiểm thành một cờ thành công.

### 6.2. Kiểm tra lại trước release

Giữa lúc duyệt và lúc sử dụng có thể xảy ra:

- Tài khoản người vận hành bị khóa.
- Người duyệt hoặc ủy quyền không còn đáp ứng điều kiện theo chính sách.
- Yêu cầu bị hủy.
- Tài nguyên hoặc quyền thay đổi.
- Cửa sổ hết hạn.
- Chính sách khẩn cấp đổi.
- Có tín hiệu rủi ro mới.

Cần kiểm tra tính còn áp dụng của các quyết định trước khi cấp quyền. Bằng chứng cũ vẫn phải được giữ đúng lịch sử, ngay cả khi nó không còn đủ điều kiện cho lần kích hoạt hiện tại.

### 6.3. Xử lý đồng thời

Hai người có thể duyệt gần cùng lúc, hoặc một người duyệt khi yêu cầu vừa bị hủy.

Hệ thống cần cơ chế nhất quán như kiểm soát phiên bản hoặc giao dịch phù hợp để:

- Không tính hai lần cùng một quyết định.
- Không cộng quyết định của hai phiên bản khác nhau.
- Không cấp quyền từ yêu cầu đã hủy.
- Không tạo nhiều release ngoài ý định.
- Không để retry làm tăng số người được tính.

Quyết định phải được thực hiện phía máy chủ từ danh tính đã xác thực. Một trường approved=true do client gửi không phải bằng chứng.

### 6.4. Timeout khi release cần đối soát

Một dịch vụ có thể đã cấp quyền nhưng phản hồi bị mất. Không được mặc định “chưa cấp gì” rồi tạo thêm quyền.

Cần giữ định danh thao tác, đối soát trạng thái thực tế và dùng cơ chế chống thực hiện trùng phù hợp. Không lưu secret trong log hoặc bản ghi retry chỉ để thuận tiện phát lại.

Kết quả chưa xác định cần được theo dõi đến trạng thái rõ ràng.

## 7. Quorum và khả năng hoạt động khi có sự cố

### 7.1. Mô hình m-of-n

Ví dụ, chính sách có thể cho phép hai trong ba người được phân công tham gia. Cách này giúp duy trì khả năng vận hành khi một người vắng mặt.

Cần xác định:

- n là ai và thuộc vai trò nào.
- m áp dụng cho quyết định hoặc bước nào.
- Có yêu cầu các vai trò khác nhau không.
- Có yêu cầu tách với người vận hành không.
- Người dự phòng được thêm hoặc thu hồi thế nào.
- Quyết định từ chối ảnh hưởng ra sao.

Đủ số lượng không tự đủ thẩm quyền. Hai người giữ phương tiện không thay thế một chủ thể có trách nhiệm quyết định nếu chính sách yêu cầu vai trò đó.

### 7.2. Chuẩn bị người dự phòng thực tế

Danh sách dự phòng cần xét ca trực, thời gian liên lạc và khả năng sử dụng phương tiện.

Hai người ở cùng vị trí hoặc cùng phụ thuộc một thiết bị có thể không giúp trong một số sự cố. Tuy nhiên, phân bố nhân sự cũng phải đi cùng đào tạo và quản lý phương tiện; chỉ có tên trong danh sách không chứng minh có thể tham gia.

### 7.3. Không phụ thuộc toàn bộ vào thành phần đang cần cứu

Một tuyến break-glass cho sự cố IdP có thể không dùng được nếu cả hai người đều phải đăng nhập qua chính IdP đang lỗi.

Tương tự:

- Bản hướng dẫn chỉ nằm trong portal không truy cập được.
- Mọi phương tiện chỉ lấy được từ vault đang lỗi.
- Kênh thông báo cần cùng hệ thống danh tính bị ảnh hưởng.
- Người dự phòng không có thiết bị hoặc authenticator hợp lệ.

Cần phân tích phụ thuộc theo kịch bản và diễn tập. Không cần loại bỏ mọi phụ thuộc, nhưng phải biết tuyến bao phủ được sự cố nào.

### 7.4. Hết thời gian chờ không tự thành chấp thuận

SLA phản hồi có thể dẫn tới nhắc việc hoặc chuyển tới người dự phòng có thẩm quyền. Nó không tự biến một quyết định còn thiếu thành đủ quorum.

Nếu không thể đạt điều kiện trong tình huống đặc biệt, chỉ dùng tuyến ngoại lệ đã được tổ chức cho phép. Không tự hạ m từ hai xuống một để yêu cầu tiếp tục chạy.

## 8. Dual custody và phương tiện ngoại tuyến

### 8.1. Quy trình lấy phương tiện

Trong một số kịch bản, credential hoặc thiết bị dự phòng được giữ ngoài hệ thống trực tuyến.

Quy trình cần xác định:

- Ai được yêu cầu.
- Ai được giữ và bàn giao.
- Cách xác minh người nhận.
- Điều kiện cần có trước bàn giao.
- Phương tiện nào được lấy.
- Thời điểm, mục đích và người chứng kiến theo chính sách.
- Cách trả hoặc thay thế sau sử dụng.

Một niêm phong hoặc hộp giữ có thể hỗ trợ phát hiện và kiểm soát tiếp cận vật lý. Nó không tự ngăn sao chép sau khi đã mở.

### 8.2. Sau khi bí mật đã được tái tạo hoặc tiết lộ

Nếu một người đã biết đầy đủ credential, sự cần thiết của người thứ hai ở lần lấy trước không bảo đảm họ không thể dùng lại.

Cần thiết kế một hoặc nhiều biện pháp phù hợp:

- Credential dùng một lần nếu hệ thống hỗ trợ thực sự.
- Thời hạn được thực thi.
- Thay hoặc thu hồi bí mật sau sử dụng.
- Chặn đường truy cập không thuộc phạm vi.
- Quản lý phiên còn tồn tại.
- Xác minh bản dự phòng mới đã được cập nhật và dùng được.

Không chỉ yêu cầu người dùng xác nhận “đã quên mật khẩu”.

### 8.3. Kiểm soát mở khóa khác kiểm soát từng thao tác

Hai người có thể cùng kích hoạt một thiết bị hoặc kho, sau đó kho vẫn mở trong một khoảng thời gian.

Phải nói rõ ai có thể làm gì trong khoảng đó. Nếu các lần checkout không yêu cầu thêm quorum, không mô tả như mọi lần đều được hai người kiểm soát.

Điều này cũng áp dụng với khóa mật mã: quorum kích hoạt khóa không tự là phê duyệt nội dung của từng thao tác sử dụng khóa.

### 8.4. Bằng chứng ngoại tuyến

Nếu công cụ trung tâm không hoạt động, có thể dùng hồ sơ tạm được kiểm soát và đối chiếu sau khi phục hồi.

Cần giữ đúng thời điểm, người thực hiện, phương tiện và phạm vi. Hậu kiểm không được ghi lại như một phê duyệt đã có trước.

Nếu dùng tài khoản kỹ thuật chung, phải ghi giới hạn quy trách nhiệm: hồ sơ bàn giao có thể liên kết người sử dụng, nhưng hệ thống đích có thể chỉ xác thực tài khoản chung.

## 9. Ngoại lệ khẩn cấp và tình huống không đủ người

### 9.1. Chuẩn bị trước thay vì quyết định tùy tiện

Một tổ chức có thể xác định các tình huống đặc biệt cần tuyến khác với dual control thông thường. Tuyến đó cần có cơ sở thẩm quyền, tiêu chí, phạm vi, thời hạn và biện pháp bổ sung.

Ví dụ, một chính sách khẩn cấp có thể cho một người được chỉ định kích hoạt một tác vụ khôi phục rất hẹp khi không liên lạc được người dự phòng, với cảnh báo và hậu kiểm bắt buộc.

Nếu chỉ có một người tham gia tại thời điểm cấp quyền, phải ghi đúng đó là ngoại lệ một người theo tuyến được cho phép. Không tính một người hậu kiểm sau đó như người thứ hai đã kiểm soát release trước đó.

### 9.2. Không có tuyến được phép thì không tự tạo

Tính cấp bách không tự trao quyền sửa quorum, tắt kiểm soát hoặc sử dụng credential ngoài chính sách.

Nếu thiếu người, cần chuyển tuyến điều phối hoặc thẩm quyền được xác định. Trạng thái chờ và lý do phải được thể hiện rõ, không che bằng một kết quả “approved” không đúng.

### 9.3. Ngoại lệ cần được kết thúc

Sau sử dụng, cần kiểm tra:

- Phạm vi và thời lượng thực tế.
- Credential đã tiết lộ.
- Phiên và quyền còn tồn tại.
- Các thay đổi cấu hình tạm thời.
- Bằng chứng còn thiếu.
- Trạng thái sẵn sàng của đường dự phòng.

Ngoại lệ dùng lặp lại có thể cho thấy thiếu nhân sự trực, quy trình quá khó hoặc thiết kế phụ thuộc chưa phù hợp. Cần sửa nguyên nhân, không biến ngoại lệ thành cách vận hành thường ngày.

## 10. Thu hồi và khôi phục trạng thái sẵn sàng

### 10.1. Hai người chấp thuận không làm quyền tự hết hạn

Dual control quản lý cổng quyết định hoặc sử dụng. PAM vẫn cần thực thi vòng đời:

- Chặn phiên mới khi hết hạn.
- Xử lý phiên đang hoạt động theo chính sách.
- Thu hồi entitlement.
- Xử lý token, certificate hoặc credential.
- Xác minh trên hệ thống đích.
- Theo dõi thất bại thu hồi.

Một trường end_at trong hồ sơ không tự đóng mọi phiên.

### 10.2. Đổi mật khẩu không thay thế xử lý phiên

Credential mới có thể ngăn lần xác thực mới bằng bí mật cũ, nhưng phiên đã mở có thể vẫn tồn tại.

Cần xác định các lớp còn hiệu lực và kết thúc chúng khi cần. Không đóng hồ sơ chỉ vì vault hiển thị “rotation succeeded”.

### 10.3. Vai trò người thứ hai sau sử dụng

Tùy chính sách, một người độc lập có thể xác nhận:

- Quyền đã được thu hồi.
- Credential dự phòng mới đã được quản lý.
- Phương tiện đã trả và còn dùng được.
- Không có thay đổi ngoài phạm vi.
- Bằng chứng đã được liên kết.

Đây là một kiểm soát kết thúc hoặc hậu kiểm. Nó bổ sung cho cổng trước sử dụng, không thay thế cổng đó.

### 10.4. Không quên sự cố tiếp theo

Sau khi đổi bí mật hoặc thay phương tiện, cần xác minh đường dự phòng còn hoạt động. Nếu cập nhật hệ thống đích nhưng quên bản dự phòng, lần khẩn cấp tiếp theo có thể thất bại.

Việc thử phải theo phạm vi được phép và không làm lộ bí mật trong log hoặc hồ sơ kiểm tra.

## 11. Chính sách và logic minh họa

Cấu hình dưới đây chỉ diễn tả ý định, không phải cú pháp của một sản phẩm PAM. Mô hình này yêu cầu hai người duyệt độc lập ngoài người vận hành:

~~~yaml
break_glass_dual_control:
  profile: "critical-system-recovery"

  participants:
    operator_must_be_eligible: true
    required_approvers: 2
    approvers_must_be_distinct_people: true
    approvers_must_differ_from_operator: true
    authority_scope_must_match: true

  decisions:
    bind_to_request_revision: true
    bind_to_target_action_and_window: true
    revalidate_before_release: true
    repeated_submission_does_not_add_a_vote: true

  release:
    no_release_before_required_control: true
    bounded_access_required: true
    uncertain_outcome_requires_reconciliation: true

  timeout:
    action: "escalate-to-authorized-alternate"
    automatic_quorum_reduction: false

  closure:
    verify_revocation: true
    manage_disclosed_secrets: true
    restore_emergency_readiness: true
    independent_review_required: true

  evidence:
    record_actual_people_and_authority: true
    record_secrets: false
~~~

Nếu tổ chức chọn người vận hành cộng một người duyệt độc lập, cần mô tả đúng mô hình đó thay vì sao chép con số trên.

Mã giả:

~~~text
evaluate_release(request_id, expected_revision):
    request = load_current_request(request_id)
    require(request.revision == expected_revision)
    require(request.is_active)
    require(request.operator_is_eligible)
    require(request.access_window_is_valid_now)

    decisions = load_decisions_for_same_request_revision(request)
    valid = validate_authority_scope_freshness_and_delegation(decisions)

    people = resolve_distinct_authoritative_people(valid)
    require(people.meet_required_roles)
    require(people.meet_required_count)
    require(people.satisfy_separation_from_operator)

    require(request.scope_and_control_profile_have_not_changed)
    require(current_risk_and_authentication_conditions_are_met)

    reserve_release_consistently_for_this_request()
    release_bounded_access_or_record_uncertain_outcome()
    track_access_until_revocation_is_verified()
~~~

Việc kiểm tra và reserve cần xử lý đồng thời phù hợp với kiến trúc. Không tự viết một vòng đếm số bản ghi rồi cấp quyền nếu bản ghi có thể trùng, bị thay đổi hoặc thuộc account của cùng một người.

## 12. Bằng chứng và giám sát

### 12.1. Chứng minh ai đã tham gia và vào lúc nào

Một hồ sơ tốt nên liên kết được:

| Nhóm | Dữ liệu hữu ích |
|---|---|
| Yêu cầu | ID, phiên bản, người vận hành, lý do và sự cố |
| Phạm vi | Tài nguyên, action hoặc role, phương thức và cửa sổ |
| Thẩm quyền | Vai trò, nguồn phân công, ủy quyền và điều kiện áp dụng |
| Quyết định | Người thực sự tham gia, thời điểm, nội dung và kết quả |
| Kiểm soát | Profile, số người cần, kết quả kiểm tra độc lập |
| Release | Thời điểm, operation ID, entitlement, lease hoặc phiên liên quan |
| Sử dụng | Tham chiếu log hoặc bản ghi phù hợp |
| Kết thúc | Thu hồi, xử lý credential, ngoại lệ và hậu kiểm |

Không lưu mật khẩu, OTP, PIN, private key hoặc token dùng lại trong hồ sơ. Người duyệt cần nội dung quyết định chứ không cần secret.

### 12.2. Không sửa lịch sử để khớp trạng thái hiện tại

Nếu người duyệt đổi vai trò, bản ghi cũ vẫn cần thể hiện người đã quyết định và cơ sở thẩm quyền tại thời điểm đó.

Nếu quyết định không còn được tính cho kích hoạt mới theo chính sách, giữ cả sự kiện đánh giá lại. Không ghi đè tên người cũ bằng người dự phòng.

### 12.3. Tín hiệu cần điều tra

- Cùng một cá nhân được tính nhiều lần.
- Người vận hành tham gia vai trò bị cấm.
- Thay quorum hoặc nhóm duyệt ngay trước release.
- Release trước khi đủ điều kiện.
- Nhiều yêu cầu khác nội dung dùng lại quyết định cũ.
- Phiên hoặc credential được sử dụng ngoài cửa sổ.
- Sử dụng đường trực tiếp bỏ qua cổng release.
- Ngoại lệ một người lặp lại.
- Có release nhưng thiếu bằng chứng sử dụng hoặc thu hồi.
- Có quyền trên đích nhưng control plane ghi thất bại.

Không nên chỉ đo tốc độ phê duyệt. Cần theo dõi cả chất lượng phạm vi, số lần chặn sai thẩm quyền, độ trễ thu hồi và các khoảng trống bằng chứng.

## 13. Tình huống: khôi phục một dịch vụ bằng quyền khẩn cấp

Một dịch vụ quan trọng gặp lỗi. Đường phê duyệt thường không đáp ứng được thời gian xử lý, nhưng tuyến break-glass đã được chuẩn bị.

Chính sách trong tình huống này yêu cầu người vận hành và một người duyệt độc lập có thẩm quyền.

### 13.1. Yêu cầu ban đầu

Người vận hành tạo yêu cầu:

~~~text
Sự cố: INC-5271
Tài nguyên: service-instance-02
Quyền: tác vụ khôi phục đã định nghĩa
Cửa sổ: 02:00–02:20
Người vận hành: engineer-17
Profile khẩn cấp: service-recovery
~~~

Người duyệt thấy lý do đường thường không dùng được, phạm vi tác vụ và điều kiện kết thúc. Họ xác thực và quyết định trên đúng phiên bản.

Nếu người duyệt hoàn tất lúc 02:05, yêu cầu chỉ còn phần cửa sổ hợp lệ đến 02:20. Hệ thống không tự dời hết hạn tới 02:25.

### 13.2. Thay đổi phạm vi

Trong lúc làm việc, người vận hành phát hiện cần thêm một máy chủ và quyền sửa cấu hình.

Đây không còn là nội dung ban đầu. Cần cập nhật hoặc tạo yêu cầu theo chính sách, lấy quyết định đúng phạm vi và kiểm tra lại trước khi cấp thêm quyền.

Một câu “đã duyệt khẩn cấp rồi” không bao phủ mọi hành động phát sinh.

### 13.3. Kết thúc

Khi xử lý xong:

1. Phiên và quyền tạm thời được kết thúc.
2. Credential đã tiết lộ được xử lý nếu có.
3. Kết quả trên đích được xác minh.
4. Các thao tác được đối chiếu với yêu cầu.
5. Người độc lập thực hiện bước kiểm tra kết thúc theo chính sách.
6. Hồ sơ được đóng khi đạt đủ điều kiện, không chỉ khi dịch vụ đã chạy lại.

Nếu thu hồi thất bại, trạng thái phải thể hiện còn việc cần xử lý. Dịch vụ hoạt động trở lại không tự chứng minh quyền khẩn cấp đã hết.

## 14. Diễn tập và tiêu chí kiểm chứng

Diễn tập nên bao phủ cả khả năng sử dụng khi có sự cố và khả năng chặn một người tự làm mọi việc. Thực hiện trong phạm vi được cho phép và có kế hoạch khôi phục.

| Ca kiểm thử | Kết quả cần đạt |
|---|---|
| Chỉ có một quyết định khi cần hai | Không release |
| Một người dùng hai account | Không được tính như hai cá nhân |
| Người vận hành tự duyệt trong mô hình cấm | Bị chặn |
| Người duyệt không có thẩm quyền với đích | Quyết định không được tính |
| Người được ủy quyền đã hết hạn | Không dùng ủy quyền cũ |
| Hai quyết định thuộc hai phiên bản | Không ghép thành đủ quorum |
| Request đổi quyền hoặc tài nguyên sau phê duyệt | Không dùng lại quyết định ngoài phạm vi |
| Một người gửi cùng quyết định nhiều lần | Không tạo thêm phiếu hoặc release |
| Duyệt và hủy xảy ra gần đồng thời | Không cấp quyền từ trạng thái đã mất hiệu lực |
| Quorum đạt sau khi cửa sổ hết | Không kích hoạt yêu cầu cũ |
| Timeout khi release | Có đối soát và không tạo quyền trùng ngoài ý định |
| Người quản trị sửa quorum hoặc nhóm duyệt | Có kiểm soát thẩm quyền, lịch sử và giám sát |
| Vault hoặc IdP chính lỗi | Tuyến dự phòng hoạt động đúng kịch bản đã thiết kế |
| Không đủ người trong SLA | Chuyển tuyến hợp lệ, không tự hạ quorum |
| Bí mật ngoại tuyến đã được mở | Có quản lý sử dụng lại, thay hoặc thu hồi theo chính sách |
| Chỉ có quorum mở kho | Không báo sai rằng mọi checkout đều có dual control |
| Hết hạn khi phiên còn mở | Quyền và phiên được xử lý đúng cơ chế công bố |
| Thu hồi thất bại | Không đóng hồ sơ như đã hoàn tất |
| Kết thúc diễn tập | Phương tiện và tuyến dự phòng sẵn sàng cho lần tiếp theo |
| Kiểm tra bằng chứng | Đúng người, đúng thời điểm, đúng phạm vi và không lộ secret |

Dual control có hiệu lực khi một cá nhân thực sự không thể tự vượt cổng nhạy cảm đã xác định. Trong break-glass, điều đó cần đi cùng thẩm quyền rõ, quyết định gắn với cùng phạm vi, khả năng hoạt động trong sự cố và quy trình thu hồi được kiểm chứng sau khi quyền đã được sử dụng.
