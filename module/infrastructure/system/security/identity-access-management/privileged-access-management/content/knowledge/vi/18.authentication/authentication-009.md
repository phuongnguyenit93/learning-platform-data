# Authentication failure — Xử lý thất bại xác thực trong PAM

## 1. Thất bại xác thực có ý nghĩa gì?

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), **authentication failure** là tình huống một bước xác thực không tạo ra được bằng chứng danh tính hợp lệ theo yêu cầu của hệ thống.

Ví dụ:

- Người dùng nhập sai mật khẩu.
- Một yêu cầu MFA bị từ chối hoặc không hoàn tất.
- Chứng thư không đáp ứng chính sách.
- Token không hợp lệ hoặc không dành cho dịch vụ nhận.
- PAM không nhận được kết quả đáng tin cậy từ IdP trước khi hết thời gian chờ.
- Gateway dùng credential không còn đúng để xác thực với hệ thống đích.

Những trường hợp này không hoàn toàn giống nhau. Sai mật khẩu là một kết quả khác với dịch vụ xác thực không phản hồi. Một người xác thực thành công nhưng thiếu quyền cũng không phải thất bại xác thực.

Cách xử lý tốt phải đáp ứng ba mục tiêu:

1. Không cấp quyền đặc quyền khi chưa có bằng chứng xác thực bắt buộc.
2. Không làm một lỗi nhỏ trở thành khóa tài khoản hàng loạt hoặc gián đoạn kéo dài.
3. Giữ đủ bằng chứng để phân biệt lỗi người dùng, lỗi vận hành và hành vi đáng ngờ.

Một thông báo “đăng nhập thất bại” trên giao diện có thể cố ý đơn giản để hạn chế tiết lộ thông tin. Tuy nhiên, xử lý nội bộ không nên gộp mọi nguyên nhân thành một lỗi duy nhất rồi retry vô hạn.

## 2. Phân biệt xác thực, cấp quyền và trạng thái chưa xác định

### 2.1. Xác thực trả lời danh tính có được chứng minh hay không

Ví dụ, một IdP trả kết quả mật khẩu không hợp lệ hoặc chứng thư không qua kiểm tra. Hệ thống chưa có cơ sở xác nhận danh tính theo cơ chế yêu cầu.

Tên tài khoản mà client gửi lên chỉ là danh tính được khai báo. Trước khi xác thực thành công, không nên ghi nhận như thể đã biết chắc người có tên đó là người thực hiện lần thử.

### 2.2. Cấp quyền trả lời được làm gì

Một người có thể đã xác thực đúng nhưng:

- Không có role để mở phiên.
- Chưa được chủ hệ thống phê duyệt.
- Yêu cầu đã hết hạn.
- Thiết bị không đáp ứng điều kiện cấp quyền.
- Tài nguyên nằm ngoài phạm vi được duyệt.

Đây là từ chối cấp quyền hoặc không đạt điều kiện truy cập. Gọi tất cả là “sai mật khẩu” sẽ khiến người dùng thay bí mật không cần thiết và làm đội vận hành điều tra sai lớp.

### 2.3. Timeout không chứng minh credential sai

Nếu PAM không nhận được phản hồi từ IdP, kết quả là chưa xác định được việc xác thực trong thời hạn cho phép. Điều đó không tự chứng minh mật khẩu đúng hoặc sai.

Cần phân biệt:

| Kết quả nội bộ | Ý nghĩa | Hướng xử lý |
|---|---|---|
| Bằng chứng bị từ chối | Cơ chế xác minh trả kết quả không đạt | Không cấp quyền; xử lý theo nguyên nhân và chính sách |
| Chưa hoàn tất | Người dùng chưa hoàn thành bước cần thiết | Hết hạn challenge hoặc cho tiếp tục trong giới hạn đã định nghĩa |
| Phụ thuộc không khả dụng | Không xác minh được do lỗi dịch vụ hoặc kết nối | Không coi là thành công; xử lý lỗi phụ thuộc |
| Xác thực thành công, cấp quyền bị từ chối | Danh tính đã được chứng minh nhưng yêu cầu không được phép | Xử lý role, phê duyệt hoặc điều kiện liên quan |
| Kết quả truy cập chưa xác định | Một thao tác cấp quyền có thể đã xảy ra nhưng chưa nhận xác nhận | Đối soát trạng thái thực tế trước khi kết luận |

Các nhãn trên là mô hình phân loại, không phải mã lỗi bắt buộc của một sản phẩm.

Nếu hệ thống nguồn không cung cấp đủ chi tiết đáng tin cậy, nên giữ trạng thái “không xác định” phù hợp thay vì suy đoán một nguyên nhân cụ thể.

## 3. Xác định thất bại xảy ra ở đâu trong chuỗi PAM

Một luồng truy cập có thể đi qua nhiều ranh giới xác thực:

~~~text
Người vận hành
    → IdP hoặc bộ xác thực
    → PAM portal
    → API hoặc dịch vụ cấp quyền
    → gateway
    → hệ thống đích
~~~

Mỗi hop có danh tính, credential và vòng đời riêng.

### 3.1. Người dùng đăng nhập portal

Nguyên nhân có thể gồm mật khẩu, trạng thái tài khoản, MFA, phiên đăng nhập hoặc cơ chế federation. Nếu đăng nhập chưa thành công, không được tạo phiên có mức bảo đảm cao chỉ để người dùng “vào trước rồi xác thực sau”.

Một phiên giới hạn để hoàn tất đăng ký hoặc challenge, nếu có, phải được tách rõ khỏi phiên được phép thao tác đặc quyền.

### 3.2. Step-up cho hành động nhạy cảm

Người dùng có thể đang có phiên portal hợp lệ nhưng không hoàn tất được xác thực mới cho checkout credential hoặc thay đổi chính sách.

Trong trường hợp này:

- Không thực hiện hành động cần step-up.
- Không đánh dấu challenge thất bại là đã đáp ứng MFA.
- Không tự mở rộng mức quyền của phiên cũ.
- Quyết định có hủy cả phiên hay không phụ thuộc rủi ro và chính sách.

Một lần nhập nhầm OTP không nhất thiết phải chấm dứt mọi chức năng ít nhạy cảm của phiên. Ngược lại, tín hiệu tài khoản bị chiếm có thể yêu cầu thu hồi rộng hơn.

### 3.3. Portal xác minh bằng chứng từ IdP

Các lỗi có thể liên quan đến bên phát hành, đối tượng nhận, chữ ký, thời hạn, trạng thái luồng hoặc mức xác thực.

Không sửa bằng cách chấp nhận mọi issuer, bỏ kiểm tra audience hoặc tin một trường do trình duyệt gửi. Đây là các ranh giới xác minh danh tính, không phải chi tiết có thể tùy tiện bỏ qua để giảm lỗi.

Thời điểm portal tạo cookie không chứng minh rằng người dùng vừa thực hiện MFA. Khi yêu cầu độ mới xác thực, cần dùng bằng chứng phù hợp từ nguồn tin cậy.

### 3.4. Gateway xác thực với hệ thống đích

Người dùng có thể đã đăng nhập PAM và được duyệt, nhưng gateway vẫn thất bại khi dùng credential trên đích.

Các nguyên nhân có thể gồm:

- Credential trong vault không đồng bộ với hệ thống đích.
- Tài khoản đích bị khóa hoặc vô hiệu hóa.
- Chứng thư, khóa hoặc chính sách tin cậy không còn phù hợp.
- Cơ chế đăng nhập trên đích thay đổi.
- Kết nối chưa tới được bước xác thực.
- Hệ thống đích áp dụng điều kiện bổ sung.

Không nên yêu cầu người dùng đổi mật khẩu portal khi lỗi thực sự nằm ở tài khoản kỹ thuật trên đích.

### 3.5. Workload xác thực với vault hoặc API

Một workload có thể dùng token, chứng thư hoặc danh tính máy. Gia hạn credential lỗi có thể tạo vòng lặp retry, khóa tài khoản hoặc gây tải lớn.

Cần thiết kế hành vi khi không nhận được credential mới: giới hạn retry, tôn trọng hạn của credential hiện tại và không chuyển sang một bí mật quản trị dùng chung không được quản lý.

## 4. Phân loại nguyên nhân để xử lý đúng

| Nhóm nguyên nhân | Ví dụ | Việc cần kiểm tra |
|---|---|---|
| Dữ liệu xác thực không đạt | Mật khẩu sai, OTP không hợp lệ | Phản hồi đáng tin cậy từ bộ xác minh; không ghi lại bí mật |
| Trạng thái danh tính | Tài khoản khóa, bị vô hiệu hóa, không còn đủ điều kiện | Nguồn quản lý danh tính và lý do thay đổi |
| Vòng đời credential | Hết hạn, bị thu hồi, secret cũ | Phiên bản credential, lịch phát hành hoặc thay đổi |
| MFA chưa đạt | Challenge hết hạn, người dùng từ chối, phương thức không đủ mạnh | Kết quả và ngữ cảnh xác thực |
| Federation hoặc token | Sai đối tượng nhận, chữ ký không hợp lệ, phiên quá cũ | Cấu hình trust, khóa xác minh và điều kiện giao thức |
| Chứng thư | Chain không được tin cậy, sai profile, hết hạn | Trust store, thời gian và chính sách trạng thái |
| Hạ tầng | Timeout, DNS, kết nối, dịch vụ lỗi | Phạm vi ảnh hưởng và trạng thái phụ thuộc |
| Cấu hình hoặc triển khai | Thay đổi endpoint, mapping sai môi trường | Thay đổi gần nhất và khác biệt cấu hình |
| Hành vi đáng ngờ | Nhiều tài khoản bị thử, push bất ngờ | Mẫu sự kiện và dữ liệu điều tra liên quan |

Phân loại có thể thay đổi khi có thêm bằng chứng. Một chuỗi “credential rejected” có thể xuất phát từ script cũ sau khi thay mật khẩu, không nhất thiết là tấn công. Một lỗi được tưởng là người dùng gõ sai cũng có thể là dấu hiệu credential đã bị thay trái phép.

Không chẩn đoán chỉ dựa vào thông báo ở trình duyệt. Cần đối chiếu sự kiện ở thành phần thực hiện kiểm tra.

## 5. Nguyên tắc xử lý: không biến lỗi thành quyền

### 5.1. Không có bằng chứng bắt buộc thì không cấp quyền mới

Khi việc xác thực không đạt hoặc chưa xác minh được, luồng thường phải chặn:

- Tạo phiên đặc quyền mới.
- Nâng mức quyền.
- Checkout credential.
- Phê duyệt hoặc thay đổi chính sách yêu cầu xác thực tương ứng.
- Gia hạn quyền dựa trên một kết quả xác thực chưa có.

Một cờ trạng thái như mfa_failed không được chuyển thành mfa_completed chỉ để tiếp tục workflow.

### 5.2. Phiên hiện hữu cần chính sách riêng

Lỗi IdP không tự nói rằng mọi phiên đã tồn tại đều không hợp lệ. Nhưng cũng không cho phép giữ phiên vô thời hạn.

Cần định nghĩa:

- Phiên nào còn được hoạt động đến hạn đã xác định.
- Hành động nào yêu cầu xác thực mới và phải bị chặn.
- Khi nào lỗi hoặc tín hiệu rủi ro buộc thu hồi phiên.
- Cách xử lý token đã hết hạn hoặc bị vô hiệu hóa.
- Cách kết thúc phiên đích và quyền JIT liên quan.

Nếu một refresh thất bại, không tự gia hạn token cũ. Việc token hoặc phiên còn hiệu lực có thể tiếp tục được dùng hay không phải dựa vào trạng thái hiện hành và chính sách, không dựa vào mong muốn tránh gián đoạn.

### 5.3. Không tự hạ mức bảo đảm

Các phản ứng không phù hợp gồm:

- MFA lỗi thì chỉ dùng mật khẩu.
- Không kiểm tra được trạng thái chứng thư thì mặc định chưa thu hồi.
- Federation lỗi thì cho mọi người dùng tài khoản cục bộ toàn quyền.
- Vault không trả credential thì sử dụng một mật khẩu dự phòng được chép sẵn trong script.
- Timeout khi kiểm tra role thì tin dữ liệu cũ không có hạn.

Nếu cần break-glass, đó phải là một tuyến đã được chuẩn bị với danh tính, điều kiện kích hoạt, phạm vi, thời hạn và bằng chứng riêng. Một lỗi dịch vụ không tự tạo ra thẩm quyền dùng đường dự phòng.

## 6. Retry, giới hạn tốc độ và khóa tài khoản

### 6.1. Không phải lỗi nào cũng nên retry

| Loại kết quả | Cách tiếp cận |
|---|---|
| Mật khẩu bị từ chối rõ ràng | Không tự gửi lại cùng bí mật liên tục |
| OTP không hợp lệ hoặc challenge đã dùng | Không replay cùng bằng chứng như một phương án khôi phục |
| Tài khoản bị vô hiệu hóa | Không retry để mong vượt trạng thái tài khoản |
| Chứng thư hết hạn hoặc không được tin cậy | Sửa nguyên nhân, không retry vô hạn |
| Lỗi kết nối tạm thời | Có thể retry có giới hạn nếu thao tác và giao thức cho phép |
| Timeout sau thao tác có thể đã tạo trạng thái | Đối soát hoặc dùng cơ chế nhất quán phù hợp trước khi gửi lại |
| Dịch vụ phụ thuộc bị lỗi diện rộng | Giảm tải, áp dụng giới hạn và theo dõi phục hồi |

Retry ở tầng truyền tải cần phân biệt với một lần thử xác thực mới. Nếu không, một lần bấm đăng nhập có thể bị nhiều lớp tự retry và biến thành nhiều lần thử thất bại.

### 6.2. Backoff và jitter cho lỗi tạm thời

Đối với lỗi có thể retry, có thể dùng:

- Số lần thử tối đa.
- Tổng thời gian chờ tối đa.
- Khoảng chờ tăng dần.
- Jitter để các client không thử lại cùng một thời điểm.
- Ngân sách retry theo dịch vụ hoặc nhóm tác vụ.
- Circuit breaker khi phụ thuộc không ổn định.

Circuit breaker giúp bảo vệ hệ thống khỏi tải vô ích; nó không xác nhận danh tính thay cho IdP. Khi mạch đang chặn, kết quả không được chuyển thành cho phép.

Không dùng retry để né điều kiện bị từ chối. Một cơ chế xác thực yêu cầu challenge mới phải tuân thủ vòng đời challenge, không phát lại bằng chứng cũ tùy tiện.

### 6.3. Giới hạn tốc độ cần nhiều chiều

Chỉ giới hạn theo IP có thể làm cả văn phòng dùng NAT bị ảnh hưởng, trong khi nguồn phân tán vẫn thử được nhiều lần. Chỉ giới hạn theo tài khoản có thể bị lợi dụng để khóa người quản trị hợp lệ.

Có thể kết hợp tín hiệu theo:

- Danh tính được khai báo.
- Nguồn kết nối đã được xác định qua ranh giới tin cậy.
- Thiết bị hoặc phiên nếu có.
- Loại challenge.
- Dịch vụ và tập tài khoản.
- Mẫu thất bại trên toàn hệ thống.

Các ngưỡng cần được lựa chọn theo rủi ro và hành vi thực tế. Không có một con số khóa tài khoản phù hợp cho mọi PAM.

### 6.4. Khóa tài khoản cũng có thể gây từ chối dịch vụ

Một kẻ không biết mật khẩu vẫn có thể gây khóa nếu hệ thống cho phép thử liên tục vào một tài khoản quan trọng. Vì vậy cần cân bằng chống dò với khả năng vận hành.

Các lựa chọn có thể gồm trì hoãn, hạn chế theo rủi ro, yêu cầu cơ chế xác thực phù hợp hơn hoặc khóa có điều kiện. Mỗi lựa chọn cần có đường khôi phục được kiểm soát.

Không tự mở khóa chỉ vì có cuộc gọi tự xưng là người quản trị. Cần xác minh danh tính, xem nguyên nhân và kiểm tra dấu hiệu chiếm đoạt trước khi khôi phục quyền.

### 6.5. Tài khoản kỹ thuật dùng chung có phạm vi ảnh hưởng lớn

Nếu nhiều phiên PAM sử dụng cùng một tài khoản đích, một script retry sai có thể khóa đường truy cập của nhiều người.

Cần có phối hợp retry, theo dõi trạng thái tài khoản và khả năng dừng nguồn lỗi. Trong dài hạn, danh tính riêng và credential ngắn hạn có thể giúp giảm phạm vi tác động nếu hệ thống hỗ trợ.

## 7. Thiết kế thông báo và trải nghiệm khôi phục

### 7.1. Thông báo bên ngoài và lý do nội bộ

Một thông báo công khai không nên trở thành công cụ dò tài khoản. Ví dụ, không cần trả hai thông báo khác nhau để xác nhận tài khoản có tồn tại hay không.

Tuy nhiên, người dùng vẫn cần biết bước tiếp theo an toàn:

~~~text
Không thể hoàn tất xác thực.
Hãy kiểm tra phương thức đang sử dụng hoặc liên hệ bộ phận hỗ trợ.
Mã tham chiếu: AUTH-REF-2841
~~~

Nếu đã có ngữ cảnh đáng tin cậy, có thể hiển thị hướng dẫn cụ thể hơn theo chính sách. Không để yêu cầu hạn chế tiết lộ biến thành một giao diện không có cách khắc phục.

Mã tham chiếu không nên chứa mật khẩu, token hoặc dữ liệu tài khoản nhạy cảm.

### 7.2. Không yêu cầu bí mật để chẩn đoán

Bộ phận hỗ trợ không nên yêu cầu người dùng:

- Gửi mật khẩu.
- Đọc OTP đang có hiệu lực.
- Chụp recovery code.
- Gửi private key.
- Chuyển tiếp cookie hoặc token đăng nhập.
- Chấp thuận một push không do họ khởi tạo.

Có thể yêu cầu thời điểm, mã tham chiếu, phương thức sử dụng và mô tả hiện tượng. Dữ liệu chẩn đoán cần được giới hạn, kiểm soát truy cập và loại bỏ bí mật.

### 7.3. Khôi phục authenticator là một quy trình riêng

Nếu người dùng mất phương tiện, cần xác minh danh tính bằng tuyến được phê duyệt. Đăng ký yếu tố mới là một thay đổi có thể tạo quyền truy cập lâu dài.

Quy trình nên quản lý:

- Người có thẩm quyền xác minh và quyết định.
- Yếu tố cũ cần vô hiệu hóa.
- Phiên hoặc token cần thu hồi.
- Phạm vi và hạn của ngoại lệ tạm thời.
- Thông báo và bằng chứng sau thay đổi.

Một phiên SSO cũ hoặc một email tự khai không tự là cơ sở đủ để bỏ mọi kiểm soát khôi phục.

## 8. Quan sát và ghi bằng chứng mà không lộ bí mật

### 8.1. Tách sự kiện từ từng hop

Một sự kiện có thể chứa:

| Trường | Mục đích |
|---|---|
| Event ID và correlation ID | Liên kết luồng giữa portal, IdP, gateway và đích |
| Thành phần, giai đoạn | Biết ai đang xác minh ai |
| Thời điểm đáng tin cậy | Xác định thứ tự, cửa sổ và độ trễ |
| Danh tính được khai báo | Hỗ trợ đối chiếu, ghi rõ chưa được xác thực nếu thích hợp |
| Principal đã xác thực nếu có | Phân biệt với chuỗi do client tự gửi |
| Loại phương thức | Mật khẩu, chứng thư, federation hoặc cơ chế khác |
| Kết quả và nhóm lý do | Từ chối, chưa hoàn tất, phụ thuộc lỗi hoặc chưa xác định |
| Chính sách hoặc cấu hình liên quan | Hỗ trợ đối chiếu thay đổi |
| Trạng thái giới hạn hoặc khóa | Giải thích tác động của kiểm soát |
| Kết quả xử lý tiếp theo | Retry, chặn, chuyển hỗ trợ hoặc thu hồi |

Nguồn IP chỉ đáng tin theo chuỗi proxy được cấu hình. Không tin một header nguồn do client có thể tự đặt.

Dữ liệu do người dùng gửi cần được xử lý để tránh chèn dòng hoặc làm sai cấu trúc log. Giới hạn độ dài và không coi tên tài khoản tự khai là bằng chứng danh tính.

### 8.2. Ví dụ sự kiện đã lược bỏ bí mật

~~~json
{
  "event": "authentication_attempt",
  "reference": "AUTH-REF-2841",
  "correlation_id": "corr-example-481",
  "component": "pam-gateway",
  "stage": "target-authentication",
  "claimed_target_account_ref": "managed-account-72",
  "authenticated_operator_ref": "engineer-17",
  "target_ref": "application-host-02",
  "outcome": "rejected",
  "reason_class": "credential-not-accepted",
  "credential_version_ref": "version-18",
  "automatic_retry": false
}
~~~

Ví dụ không nói mật khẩu sai nếu hệ thống đích chỉ cho biết credential không được chấp nhận. Nguyên nhân cụ thể cần được xác định bằng bằng chứng bổ sung.

Các định danh có thể vẫn là dữ liệu nhạy cảm. Việc dùng mã tham chiếu không tự làm dữ liệu vô danh; cần quyền đọc và chính sách lưu phù hợp.

### 8.3. Tránh log ở lớp chẩn đoán làm lộ bí mật

Bí mật có thể xuất hiện trong:

- Request body.
- Authorization header.
- URL.
- Stack trace hoặc thông báo exception.
- Kết quả debug của giao thức.
- File hỗ trợ hoặc ảnh chụp màn hình.

Không chỉ bảo vệ log ứng dụng chính mà bỏ qua log proxy, agent và công cụ thu thập lỗi. Cần kiểm tra việc che hoặc loại bỏ dữ liệu trên toàn đường đi liên quan.

## 9. Runbook chẩn đoán theo phạm vi ảnh hưởng

### 9.1. Bước 1: xác định hop và thời điểm

Thu thập mã tham chiếu, thời điểm, hệ thống và hành động. Xác định lần thất bại nằm ở đăng nhập portal, step-up, cấp credential hay xác thực trên đích.

Đối chiếu các sự kiện có cùng correlation ID nếu có. Không tự kết luận mọi lỗi xuất hiện sau nút “Connect” đều là lỗi mật khẩu.

### 9.2. Bước 2: đánh giá phạm vi

Các câu hỏi hữu ích:

- Một người bị lỗi hay nhiều người?
- Một phương thức lỗi hay tất cả?
- Một hệ thống đích lỗi hay nhiều hệ thống?
- Chỉ production lỗi hay cả môi trường khác?
- Lỗi bắt đầu sau một thay đổi nào?
- Có tăng retry, khóa tài khoản hoặc timeout không?

Một lỗi trên nhiều người và nhiều tài nguyên cùng lúc thường cần kiểm tra phụ thuộc chung. Một lỗi chỉ trên một tài khoản có thể cần kiểm tra vòng đời danh tính hoặc credential, nhưng vẫn phải xác minh bằng chứng.

### 9.3. Bước 3: kiểm tra nguồn xác minh có thẩm quyền

Đối chiếu trạng thái tài khoản, lịch thay đổi, kết quả MFA, profile chứng thư hoặc log IdP theo đúng lớp.

Nếu giao thức chỉ trả lý do tổng quát, không suy diễn chi tiết. Có thể cần người vận hành hệ thống đích hỗ trợ xác minh.

Không thử liên tục trên tài khoản production chỉ để “xem lần này có được không”, nhất là khi có giới hạn khóa.

### 9.4. Bước 4: dừng tác nhân làm lỗi lan rộng

Nếu một job hoặc agent đang dùng credential cũ, cần hạn chế hoặc dừng vòng retry theo quy trình vận hành. Nếu có nhiều lớp retry, xác định lớp điều phối thay vì chỉ tăng timeout.

Nếu phụ thuộc bị lỗi diện rộng, áp dụng cơ chế giảm tải đã chuẩn bị. Không chuyển toàn bộ người dùng sang tài khoản dự phòng chung.

### 9.5. Bước 5: khôi phục theo nguyên nhân

Ví dụ:

- Sai hoặc cũ credential: đồng bộ qua cơ chế quản lý credential, xác minh kết quả.
- Tài khoản khóa: xác minh nguyên nhân và danh tính trước khi mở lại.
- MFA mất phương tiện: dùng tuyến khôi phục có kiểm soát.
- Chứng thư lỗi: xử lý thời gian, chain, profile hoặc vòng đời tương ứng.
- Federation lỗi: khôi phục cấu hình tin cậy đúng.
- Phụ thuộc không hoạt động: sửa dịch vụ hoặc dùng tuyến khẩn cấp đúng thẩm quyền.

Không “sửa” bằng cách bỏ kiểm tra bảo mật vốn tạo ra kết quả từ chối hợp lệ.

### 9.6. Bước 6: xác minh và đóng

Sau xử lý, cần xác nhận:

- Luồng hợp lệ hoạt động trong phạm vi dự kiến.
- Trường hợp không hợp lệ vẫn bị chặn.
- Không còn retry storm hoặc khóa lặp lại.
- Ngoại lệ tạm thời đã hết.
- Không có quyền hoặc phiên thừa do thao tác khắc phục.
- Bằng chứng và nguyên nhân đã được ghi nhận.

Một lần đăng nhập thành công không đủ để kết luận đã hết vấn đề nếu nguồn dùng credential cũ vẫn tiếp tục chạy.

## 10. Ba tình huống thực tế

### 10.1. Credential trong vault không đồng bộ với hệ thống đích

Một lần thay mật khẩu trên đích đã hoàn tất nhưng trạng thái trong vault chưa phản ánh đúng. Người dùng đăng nhập PAM và được duyệt bình thường, sau đó gateway không xác thực được.

Cách xử lý:

1. Xác định lỗi ở hop gateway tới đích.
2. Ngăn retry lặp lại gây khóa tài khoản.
3. Đối chiếu sự kiện thay credential và phiên bản được sử dụng.
4. Dùng quy trình reconcile hoặc khôi phục credential có thẩm quyền.
5. Xác minh bằng phương thức được kiểm soát, không in mật khẩu ra log.
6. Kiểm tra các tiến trình khác vẫn dùng phiên bản cũ.
7. Xác nhận hoạt động và giữ bằng chứng.

Không sửa bằng cách yêu cầu mọi người dùng tài khoản quản trị khác ngoài PAM. Nếu cần đường khẩn cấp, phải dùng tuyến được chuẩn bị.

### 10.2. Dịch vụ MFA không phản hồi

Nhiều người cùng gặp timeout ở step-up. Portal vẫn hoạt động nhưng không có bằng chứng MFA mới cho các thao tác nhạy cảm.

Cách xử lý:

- Giữ các hành động cần MFA mới ở trạng thái chưa được thực hiện.
- Phân biệt timeout với người dùng từ chối MFA.
- Giảm retry đồng bộ để tránh tạo thêm tải.
- Kiểm tra phụ thuộc và kênh giám sát.
- Xử lý phiên hiện hữu theo chính sách đã định nghĩa.
- Chỉ dùng break-glass cho trường hợp đủ điều kiện, không cho mọi người đăng nhập bằng mật khẩu đơn.

Khi dịch vụ phục hồi, cần kiểm tra challenge cũ, ngoại lệ và các yêu cầu chưa hoàn tất. Không tự phát lại mọi hành động nhạy cảm từng bị treo nếu chưa kiểm tra tính còn hợp lệ.

### 10.3. Nhiều lần thất bại rồi xuất hiện thành công

Một tài khoản có chuỗi thất bại, sau đó có đăng nhập thành công và checkout credential.

Đây là tín hiệu cần xem xét, không phải kết luận chắc chắn tài khoản bị chiếm. Cần kiểm tra:

- Người dùng có xác nhận các lần thử không.
- Có thay đổi nguồn, thiết bị hoặc phương thức không.
- Có push không do người dùng khởi tạo không.
- Có khôi phục hoặc thêm authenticator ngay trước đó không.
- Hành động sau đăng nhập có phù hợp yêu cầu đã duyệt không.
- Có credential hoặc phiên cần thu hồi để hạn chế rủi ro không.

Nếu có dấu hiệu chiếm đoạt, đổi mật khẩu riêng lẻ có thể chưa đủ. Cần đánh giá phiên, token, yếu tố xác thực và quyền trên đích.

## 11. Trạng thái không xác định trong hệ thống phân tán

Một lỗi kết nối có thể xảy ra sau khi phía nhận đã thực hiện một thao tác nhưng trước khi phía gửi nhận được phản hồi.

Ví dụ, dịch vụ cấp quyền đã tạo entitlement tạm thời, nhưng gateway bị timeout khi chờ kết quả. Nếu portal báo “không có quyền nào được cấp” rồi tạo lại yêu cầu, có thể phát sinh quyền trùng hoặc quyền không được theo dõi.

Cần phân biệt:

~~~text
AUTHENTICATION_REJECTED
    Bằng chứng xác thực bị từ chối theo kết quả đáng tin cậy.

AUTHENTICATION_UNAVAILABLE
    Không có kết quả xác minh cần thiết trong thời hạn.

ACCESS_OUTCOME_UNKNOWN
    Chưa biết thao tác cấp hoặc mở quyền đã hoàn tất hay chưa.
~~~

Đối với kết quả chưa xác định:

- Giữ định danh yêu cầu xuyên suốt.
- Dùng idempotency hoặc cơ chế chống thực hiện trùng phù hợp cho thao tác có trạng thái.
- Đối soát trạng thái thực tế trên hệ thống nhận.
- Không đánh dấu đã thu hồi nếu chưa có kết quả xác minh.
- Không cho retry tạo thêm quyền ngoài yêu cầu.
- Theo dõi đến khi có trạng thái rõ ràng.

Idempotency không có nghĩa một OTP có thể được dùng lại cho nhiều phiên hoặc nhiều hành động. Vòng đời bằng chứng xác thực và tính nhất quán của thao tác nghiệp vụ là hai vấn đề cần thiết kế riêng.

## 12. Chính sách và logic minh họa

Cấu hình sau chỉ là mô hình trao đổi thiết kế, không phải cú pháp của một sản phẩm:

~~~yaml
authentication_failure_handling:
  normal_access:
    grant_on_rejected_evidence: false
    grant_on_unknown_authentication_result: false
    downgrade_required_assurance_on_error: false

  retries:
    rejected_evidence: "no-automatic-replay"
    transient_dependency_errors: "bounded-with-backoff-and-jitter"
    uncertain_stateful_outcome: "reconcile-before-repeat"

  protection:
    rate_limit_multiple_dimensions: true
    monitor_account_lockout_side_effects: true
    coordinate_shared_target_account_retries: true

  sessions:
    failed_step_up_does_not_elevate: true
    enforce_existing_expiry: true
    risk_based_revocation: true

  evidence:
    distinguish_claimed_and_verified_identity: true
    correlate_authentication_hops: true
    exclude_reusable_secrets: true

  emergency:
    route: "separately-authorized-break-glass"
    automatic_password_only_fallback: false
~~~

Mã giả:

~~~text
handle_authentication_result(result, operation):
    record_sanitized_result(result, operation.reference)

    if result.is_verified_success:
        return evaluate_authorization_and_current_conditions(operation)

    if result.is_rejected:
        update_attempt_controls_using_trusted_context()
        do_not_execute_privileged_operation()
        return generic_failure_with_reference()

    if result.is_incomplete:
        keep_only_the_permitted_challenge_state()
        do_not_execute_privileged_operation()
        return continuation_or_expiry_according_to_policy()

    if result.is_dependency_error:
        apply_bounded_retry_only_if_safe_and_allowed()
        do_not_treat_error_as_success()
        return unavailable_with_reference()

    preserve_unknown_outcome_for_reconciliation()
    do_not_assume_access_was_never_created()
    return controlled_pending_or_failure_state()
~~~

Đây là logic khái niệm. Việc ánh xạ giao thức, quản lý phiên, kiểm tra bằng chứng và xử lý đồng thời cần được thực hiện bằng thành phần phù hợp. Không đặt một đoạn catch-all trả “success” khi thư viện xác thực ném lỗi.

## 13. Phát hiện và chỉ số vận hành

Các mẫu đáng điều tra gồm:

- Nhiều lần thử trên một tài khoản từ nhiều nguồn.
- Một nguồn thử nhiều tài khoản.
- Tăng đột biến timeout trên cùng một phụ thuộc.
- Nhiều tài khoản đích bị khóa sau thay credential.
- Phương thức MFA bị từ chối lặp lại.
- Thất bại kéo dài rồi có hành động đặc quyền bất thường.
- Đăng nhập qua đường dự phòng ngay sau lỗi luồng thường.
- Lỗi xác thực giảm đột ngột sau một thay đổi làm yếu kiểm tra.

Nên theo dõi riêng:

| Chỉ số | Điều giúp quan sát |
|---|---|
| Tỷ lệ bị từ chối theo phương thức và hop | Phát hiện cấu hình hoặc credential lỗi |
| Tỷ lệ timeout và lỗi phụ thuộc | Phân biệt khả dụng với sai credential |
| Số tài khoản khóa và số người bị ảnh hưởng | Đánh giá tác dụng phụ của kiểm soát |
| Retry trên mỗi thao tác | Phát hiện khuếch đại tải |
| Thời gian khôi phục và lỗi lặp lại | Đánh giá chất lượng xử lý |
| Quyền có kết quả chưa xác định | Phát hiện khoảng trống đối soát |
| Sử dụng break-glass liên quan đến lỗi xác thực | Kiểm tra nhu cầu và khả năng lạm dụng |
| Sự kiện thiếu bằng chứng hoặc chứa dữ liệu nhạy cảm | Đánh giá chất lượng quan sát |

Không đặt mục tiêu “giảm mọi thất bại về không” bằng cách làm yếu xác thực. Các lần từ chối đúng là một phần của cơ chế bảo vệ. Cần giảm lỗi không cần thiết trong khi giữ khả năng chặn truy cập không hợp lệ.

## 14. Kiểm chứng trước khi vận hành

Kiểm thử nên dùng danh tính, tài nguyên và phạm vi được phép, đồng thời kiểm tra khả năng phục hồi sau mỗi bài thử.

| Ca kiểm thử | Kết quả cần đạt |
|---|---|
| Mật khẩu sai | Không cấp quyền; thông báo không lộ thông tin quá mức |
| Tài khoản không tồn tại | Không trở thành cách dò danh tính qua phản hồi không cần thiết |
| Tài khoản bị vô hiệu hóa | Không được cấp mới qua đường khác ngoài chính sách |
| OTP sai, hết hạn hoặc đã dùng | Không thỏa điều kiện MFA |
| Người dùng từ chối push | Hành động yêu cầu MFA không được thực hiện |
| Step-up thất bại trong phiên portal | Không nâng quyền; phiên được xử lý đúng chính sách |
| IdP hoặc dịch vụ MFA timeout | Không tự hạ mức xác thực |
| Chứng thư hoặc token không hợp lệ | Không bị bỏ qua kiểm tra để tiếp tục |
| Gateway dùng credential cũ | Retry được giới hạn và có thể xác định đúng hop |
| Nhiều client retry đồng thời | Không tạo vòng lặp tải không giới hạn |
| Một nguồn cố gây khóa tài khoản | Có kiểm soát và đường xử lý theo chính sách |
| Thao tác cấp quyền timeout sau khi phía nhận đã xử lý | Có đối soát, không tạo quyền trùng |
| Header hoặc trạng thái client giả mạo kết quả xác thực | Không được tin như bằng chứng phía máy chủ |
| Lỗi phát sinh trong thư viện xác thực | Không rơi vào nhánh cho phép mặc định |
| Đường API, CLI hoặc đăng nhập cục bộ | Không trở thành lối bỏ qua kiểm soát tương đương |
| Mất log trung tâm | Có hành vi thu thập và xử lý giới hạn theo thiết kế |
| Khôi phục xong sau sự cố | Ngoại lệ hết, quyền và phiên thừa được xử lý |
| Kiểm tra dữ liệu chẩn đoán | Không có mật khẩu, OTP, private key hoặc token dùng lại |

Xử lý authentication failure trong PAM không chỉ là hiển thị một thông báo lỗi. Hệ thống cần giữ đúng ranh giới tin cậy, phân loại kết quả theo bằng chứng, ngăn retry và khóa tài khoản gây tác động lan rộng, đồng thời theo dõi mọi quyền có thể đã phát sinh đến một trạng thái xác định.
