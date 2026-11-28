# Adaptive authentication

Một người dùng đăng nhập từ thiết bị thường dùng để xem thông tin cá nhân không tạo ra cùng bối cảnh với một lần truy cập từ môi trường mới để thay đổi quyền quản trị. Adaptive authentication điều chỉnh yêu cầu xác thực dựa trên ngữ cảnh, thay vì áp dụng một chuỗi thao tác giống nhau cho mọi lần truy cập. Cách tiếp cận này còn được gọi là risk-based authentication. [OWASP: Adaptive or Risk Based Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#adaptive-or-risk-based-authentication).

Mục tiêu không phải hỏi MFA càng ít càng tốt hoặc chặn mọi hành vi lạ. Mục tiêu là đặt yêu cầu phù hợp với rủi ro và tác động của thao tác, trong khi vẫn duy trì mức bảo vệ tối thiểu của hệ thống. Một thiết kế tốt cần giải thích được vì sao nó cho tiếp tục, yêu cầu xác thực thêm hoặc từ chối một giao dịch.

## 1. Bài toán mà adaptive authentication giải quyết

Giả sử một dịch vụ SaaS có người dùng nghiệp vụ và quản trị viên theo tenant. Chính sách cố định ban đầu yêu cầu mật khẩu khi đăng nhập và giữ phiên trong một khoảng thời gian. Khi người dùng có session, hệ thống cho thực hiện mọi hành động mà role cho phép.

Thiết kế đó để lại một khoảng cách: cùng một session có thể được sử dụng trong những hoàn cảnh khác nhau. Người dùng có thể vừa khôi phục tài khoản, đổi thiết bị, có dấu hiệu phiên bị chiếm đoạt hoặc bắt đầu một hành động ảnh hưởng lớn hơn nhiều so với xem trang tổng quan.

Adaptive authentication thêm một lớp đánh giá ngữ cảnh tại những điểm cần thiết. Trong ví dụ của bài học, các điểm đó gồm đăng nhập, thêm authenticator, đổi phương thức khôi phục, xuất dữ liệu và thay đổi role quản trị.

Tuy nhiên, lớp này không sửa được mọi vấn đề khác. Nếu backend không kiểm tra tenant, một lần xác thực mạnh vẫn có thể đi kèm lỗi truy cập chéo tenant. Nếu dữ liệu quyền đã bị thu hồi nhưng API vẫn dùng cache cũ, điểm rủi ro thấp không làm quyền cũ trở nên hợp lệ.

## 2. Phân biệt rủi ro, bằng chứng xác thực và quyền truy cập

Ba câu hỏi cần được xử lý riêng:

| Khía cạnh | Câu hỏi | Ví dụ dữ liệu |
|---|---|---|
| Rủi ro | Tình huống này có dấu hiệu đáng ngờ nào? | Thiết bị mới, nguồn mạng bất thường, sự kiện bảo mật gần đây |
| Bằng chứng xác thực | Chủ thể đã thực hiện cơ chế xác thực nào và khi nào? | Phương thức đã xác minh, thời điểm xác thực, kết quả user verification nếu có |
| Phân quyền | Chủ thể có được làm hành động này trên tài nguyên này không? | Role, permission, tenant, trạng thái assignment |

Một địa chỉ IP quen thuộc là tín hiệu ngữ cảnh, không phải một yếu tố xác thực độc lập. NIST cũng phân biệt chỉ báo gian lận với authenticator: chỉ báo không thay thế yếu tố xác thực hoặc tự thay đổi mức bảo đảm của giao dịch. [NIST SP 800-63B: Authentication Assurance Levels](https://pages.nist.gov/800-63-4/sp800-63b.html#aal).

Từ đó, thiết kế của bài học giữ một nguyên tắc: ngữ cảnh thuận lợi không tạo ra danh tính đã xác thực. Người dùng vẫn phải có bằng chứng đăng nhập hợp lệ hoặc một session được chấp nhận trước khi đọc dữ liệu riêng tư.

Tương tự, `riskScore = 10` không có nghĩa người dùng “đã MFA”, và `riskScore = 90` không chứng minh chắc chắn người đó là kẻ tấn công. Score là đầu vào của quyết định, có ý nghĩa theo mô hình, dữ liệu và chính sách cụ thể.

## 3. Các tín hiệu đầu vào và giới hạn của chúng

Những nhóm tín hiệu thường được sử dụng gồm mạng, vị trí, thiết bị, thời điểm truy cập, hành vi và sự kiện bảo mật tài khoản. OWASP mô tả các nhóm tín hiệu này trong hướng dẫn về xác thực theo rủi ro. [OWASP: Adaptive or Risk-Based Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#adaptive-or-risk-based-authentication).

Đối với dịch vụ minh họa, có thể lập bảng đánh giá sau:

| Tín hiệu | Câu hỏi cần đặt | Hạn chế cần xử lý |
|---|---|---|
| Mạng truy cập | Nguồn mạng khác lịch sử hoặc có dấu hiệu lạm dụng không? | VPN, NAT và proxy làm nhiều người dùng chung hoặc thay đổi IP |
| Thiết bị hoặc trình duyệt | Có thay đổi đáng kể so với dữ liệu đã biết không? | Nhiều thuộc tính có thể bị sửa hoặc giống nhau giữa các máy |
| Vị trí ước lượng | Có mâu thuẫn với lịch sử gần đây không? | Định vị từ IP không phản ánh chính xác vị trí vật lý |
| Thời điểm | Lần truy cập có khác thói quen không? | Ca trực, đi công tác và đổi múi giờ tạo biến động hợp lệ |
| Sự kiện tài khoản | Có khôi phục, đổi mật khẩu hoặc thêm authenticator gần đây không? | Một sự kiện hợp lệ vẫn cần ngữ cảnh, không đồng nghĩa bị chiếm tài khoản |
| Hoạt động trong phiên | Có tốc độ hoặc chuỗi thao tác khác thường không? | Tác vụ hợp lệ, công cụ hỗ trợ và thay đổi công việc có thể làm mẫu thay đổi |
| Tác động hành động | Thao tác sắp làm có ảnh hưởng lớn không? | Đây là yêu cầu nghiệp vụ, không chỉ là dấu hiệu về người dùng |

Một nhãn “impossible travel” cần được diễn giải thận trọng. Hai lần định vị xa nhau có thể do proxy hoặc thay đổi đường mạng, chứ chưa chứng minh một người đã di chuyển với tốc độ phi thực tế. Trong thiết kế minh họa, tín hiệu này kích hoạt đánh giá bổ sung; nó không tự khóa vĩnh viễn tài khoản.

Tín hiệu có ích phải đi kèm nguồn, thời điểm quan sát và độ tin cậy. Nếu chỉ có một giá trị mà không biết nó được đo lúc nào hoặc do ai cung cấp, hệ thống khó dùng giá trị đó một cách an toàn.

## 4. Xác định ranh giới tin cậy của dữ liệu

Trình duyệt có thể gửi thông tin hệ điều hành hoặc một nhãn thiết bị, nhưng client không được tự quyết định rằng thiết bị đáng tin cậy. Tương tự, một header do người gọi tùy ý đặt không phải kết quả đánh giá mạng của hạ tầng.

Ví dụ request sau không được xem là bằng chứng để bỏ qua xác thực thêm:

```json
{
  "deviceTrusted": true,
  "riskScore": 0,
  "mfaCompleted": true
}
```

Backend phải xác định nguồn nào được phép phát biểu từng thuộc tính. Kết quả xác thực cần đến từ thành phần xác thực đáng tin cậy; trạng thái thiết bị cần đến từ cơ chế quản lý thiết bị nếu chính sách dựa vào nó; điểm rủi ro cần do thành phần đánh giá được kiểm soát cung cấp.

Trong môi trường có reverse proxy, địa chỉ client cũng cần được suy ra theo cấu hình proxy tin cậy. Tin mọi giá trị `X-Forwarded-For` từ Internet có thể cho phép người gọi tự khai một IP được ưu tiên.

Một mô hình tín hiệu khái niệm:

```text
Signal
  name
  value
  source
  observedAt
  receivedAt
  confidence
  integrityStatus
```

`observedAt` khác `receivedAt`: sự kiện có thể được chuyển tới muộn. Việc một thông báo vừa đến không làm cho nội dung của nó trở thành quan sát mới. Thiết kế cần đánh giá độ mới dựa trên ý nghĩa thực của từng trường.

## 5. Mức bảo vệ tối thiểu và yêu cầu theo ngữ cảnh

Trước khi thiết kế score, cần xác định mức bảo vệ tối thiểu cho mỗi nhóm hành động. Nếu role quản trị luôn phải dùng phương thức xác thực đáp ứng một tập thuộc tính nhất định, tín hiệu IP quen thuộc không được âm thầm gỡ yêu cầu đó.

Trong dịch vụ minh họa, chọn chính sách như sau:

| Nhóm hành động | Điều kiện tối thiểu | Điều chỉnh theo ngữ cảnh |
|---|---|---|
| Đọc thông tin nghiệp vụ thông thường | Session hợp lệ, tài khoản hoạt động, permission đúng scope | Yêu cầu xác thực lại khi có biến động đáng ngờ |
| Xuất tập dữ liệu nhạy cảm | Điều kiện trên và xác thực phù hợp còn đủ mới | Có thể giữ yêu cầu ở trạng thái chờ khi thiếu dữ liệu rủi ro quan trọng |
| Đổi role quản trị | Quyền quản trị đúng tenant và xác thực mạnh còn đủ mới | Từ chối khi có dấu hiệu phiên đã bị chiếm đoạt được xác nhận |
| Thêm authenticator hoặc đổi khôi phục | Xác minh tài khoản theo chính sách quản lý credential | Yêu cầu xem xét thêm khi vừa có sự kiện khôi phục hoặc nghi vấn |

Đây là chính sách giả định để học thiết kế, không phải một bảng chuẩn áp dụng cho mọi tổ chức. Điểm quan trọng là yêu cầu tối thiểu được mô tả độc lập và không bị score thuận lợi bù trừ.

Không nên gom mọi cơ chế vào một thang “mạnh hơn” chỉ bằng số lượng bước. Nếu yêu cầu là chống một kiểu phishing cụ thể, thêm một bước dễ chuyển tiếp chưa chắc đáp ứng thuộc tính cần thiết. Chính sách cần nêu điều kiện của bằng chứng, không chỉ ghi “thêm một MFA”.

## 6. Từ tín hiệu tới quyết định

Adaptive authentication có thể dùng rule, mô hình thống kê, machine learning hoặc kết hợp. Với hệ thống nhỏ, rule rõ ràng thường là điểm bắt đầu dễ giải thích hơn một mô hình phức tạp chưa có dữ liệu đánh giá.

Trong bài học, tách kết quả thành các loại:

| Quyết định | Ý nghĩa thực thi |
|---|---|
| `ALLOW_CURRENT_AUTH` | Bằng chứng hiện tại đủ cho yêu cầu xác thực của hành động này |
| `REQUIRE_STEP_UP` | Cần hoàn tất một giao dịch xác thực bổ sung phù hợp |
| `RESTRICT_AND_REVIEW` | Chặn hành động đang yêu cầu và chuyển xử lý theo chính sách |
| `DENY` | Từ chối; có thể kèm hành động bảo vệ tài khoản hoặc phiên |
| `RETRY_LATER` | Chưa thể quyết định an toàn do phụ thuộc cần thiết không sẵn sàng |

`ALLOW_CURRENT_AUTH` chỉ là kết quả của cổng xác thực. Nó không thay thế kiểm tra phân quyền. Tên quyết định cần làm rõ phạm vi này để thành phần nghiệp vụ không hiểu nhầm thành “cho làm mọi việc”.

Một thứ tự đánh giá khái niệm:

```text
nếu tài khoản bị chặn hoặc phiên bị thu hồi:
    DENY
nếu có điều kiện bảo vệ bắt buộc phải từ chối:
    DENY
nếu thiếu dữ liệu thiết yếu cho hành động nhạy cảm:
    RETRY_LATER hoặc RESTRICT_AND_REVIEW theo chính sách
xác định yêu cầu tối thiểu của hành động
bổ sung yêu cầu từ ngữ cảnh rủi ro
nếu bằng chứng hiện tại chưa đáp ứng:
    REQUIRE_STEP_UP
ngược lại:
    ALLOW_CURRENT_AUTH
```

Đừng cộng tất cả thành một tổng rồi để các tín hiệu thuận lợi xóa một điều kiện từ chối bắt buộc. Một cookie nhớ thiết bị không được bù cho việc session đã bị thu hồi.

## 7. Điểm rủi ro cần có ý nghĩa và phiên bản

Nếu dùng score, cần xác định nó là điểm ưu tiên, một mức phân loại hay xác suất đã được hiệu chỉnh. Thang 0–100 không tự mang nghĩa phần trăm tài khoản bị chiếm đoạt.

Ví dụ học tập có thể quy ước:

```text
0..29   → rủi ro thấp theo mô hình minh họa
30..69  → cần đánh giá yêu cầu step-up
70..100 → giữ hành động nhạy cảm và chuyển xem xét
```

Các ngưỡng này chỉ minh họa cách tổ chức chính sách, không phải giá trị đề xuất cho sản xuất. Hệ thống thực tế cần hiệu chỉnh theo dữ liệu, tác động và khả năng hỗ trợ. Cùng score nhưng hai hành động có thể cần kết quả khác nhau vì hậu quả nghiệp vụ khác nhau.

Mỗi assessment cần lưu phiên bản rule hoặc mô hình, các mã lý do, thời điểm đánh giá và thời điểm hết giá trị sử dụng. Khi mô hình thay đổi, nhóm vận hành phải biết vì sao hai lần đánh giá cùng một ngữ cảnh có thể cho kết quả khác nhau.

Độ rủi ro và độ chắc chắn của đánh giá cũng cần tách biệt. “Không thấy dấu hiệu xấu trong dữ liệu đầy đủ” khác với “không có dữ liệu vì nguồn đang lỗi”. Trường hợp thứ hai không nên được chuyển thành score thấp bằng cách gán mọi tín hiệu thiếu thành số 0.

## 8. Step-up là một giao dịch có trạng thái

Step-up là việc yêu cầu bằng chứng bổ sung khi bằng chứng hiện tại chưa đủ cho ngữ cảnh hoặc hành động. Nó không nhất thiết luôn là thêm đúng một yếu tố; có thể cần xác thực lại bằng phương thức đáp ứng thuộc tính cụ thể.

Một giao dịch step-up trong thiết kế minh họa cần gắn với:

```text
StepUpTransaction
  transactionId
  subjectId
  sessionId
  tenantId
  actionType
  actionContextDigest
  requiredAuthenticationProperties
  policyVersion
  createdAt
  expiresAt
  status
```

Khi người dùng hoàn tất, server cần kiểm tra đúng chủ thể, session, challenge, thời hạn và yêu cầu xác thực. Sau đó, hệ thống đánh giá lại các điều kiện liên quan trước khi cho hành động tiếp tục.

Ví dụ An xác thực lại để xuất báo cáo tại tenant A. Kết quả đó không được dùng cho session của Bình hoặc chuyển thành quyền đổi role tại tenant B. Nếu thiết kế chọn bằng chứng chỉ dùng cho một hành động, nó cần được tiêu thụ đúng một lần. Nếu chọn dùng lại trong một cửa sổ ngắn, phải mô tả rõ phạm vi và kiểm tra những điều kiện còn hiệu lực.

Không thực hiện tác dụng phụ trước rồi mới hiển thị màn hình xác thực. API xuất dữ liệu không được đưa job vào hàng đợi trước khi hoàn tất cổng kiểm soát. Sau xác thực lại, thao tác có thể cần kiểm tra quyền và phiên bản dữ liệu lần nữa để xử lý thay đổi phát sinh trong lúc người dùng tương tác.

MFA thành công cũng không tự xóa mọi nghi vấn. Nếu session đã được xác nhận bị chiếm đoạt hoặc authenticator bị thu hồi, một kết quả step-up không được dùng để âm thầm bỏ qua điều kiện bảo vệ đó.

## 9. Adaptive authentication trong vòng đời phiên

Đánh giá lúc đăng nhập chỉ phản ánh một thời điểm. NIST mô tả session monitoring là việc tiếp tục đánh giá đặc điểm phiên để nhận diện khả năng gian lận; phản ứng có thể gồm xác thực lại, chấm dứt phiên hoặc thông báo bộ phận phù hợp. [NIST SP 800-63B: Session Monitoring](https://pages.nist.gov/800-63-4/sp800-63b.html#session-monitoring).

Trong kiến trúc minh họa, đánh giá lại có thể xảy ra khi người dùng đổi nhóm hành động, khi có sự kiện bảo mật mới hoặc khi assessment cũ hết thời gian được sử dụng. Không cần hứa rằng mọi request đều chạy một mô hình nặng mới hoàn toàn; cần nêu rõ quyết định được cache bao lâu và sự kiện nào vô hiệu hóa nó.

Khi có thay đổi mức xác thực của phiên, việc quản lý session phải bảo vệ chống cố định phiên và sử dụng lại định danh không còn hợp lệ. OWASP hướng dẫn thay mới session ID khi mức đặc quyền thay đổi. [OWASP: Session ID Life Cycle](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#renew-the-session-id-after-any-privilege-level-change).

Điểm triển khai cần chú ý là phạm vi của bằng chứng sau step-up. Xác thực lại cho một thao tác không nhất thiết kéo dài toàn bộ vòng đời phiên hoặc nâng mọi quyền trong session. Chính sách phải xác định thời gian, loại hành động và tài khoản mà kết quả được dùng.

Nếu một token cũ vẫn được các API chấp nhận mà không biết sự kiện thu hồi, hệ thống chưa chặn được truy cập chỉ bằng cách cập nhật risk engine. Cần cơ chế thực thi tương ứng tại nơi dùng token và một giới hạn độ trễ được công bố.

## 10. Phối hợp với SSO và các dịch vụ khác

Trong SSO, ứng dụng có thể nhận bằng chứng từ IdP thay vì trực tiếp kiểm tra authenticator. Ứng dụng vẫn cần xác định sự kiện xác thực đó có đủ mới và đáp ứng yêu cầu của hành động hay không; một lần chuyển hướng thành công không tự chứng minh người dùng vừa thực hiện xác thực thêm.

NIST lưu ý session tại IdP và RP được quản lý độc lập; một assertion mới có thể dựa trên phiên IdP cũ. RP cần xác định yêu cầu xác thực lại của mình đã được đáp ứng chưa. [NIST SP 800-63B: Reauthentication](https://pages.nist.gov/800-63-4/sp800-63b.html#reauthentication).

Trong thiết kế của bài học, chỉ nhận thông tin thời điểm và phương thức từ assertion được xác minh qua quan hệ tin cậy phù hợp. Không lấy nhãn `mfa=true` từ query parameter do client bổ sung.

Hành động được thực hiện qua message queue hoặc dịch vụ nội bộ cũng phải giữ ngữ cảnh cần thiết. Một job được tạo sau kiểm tra hợp lệ không tự có quyền chạy mãi nếu quyền hoặc session đã thay đổi trước khi job thực hiện. Cần chọn thời điểm đánh giá lại phù hợp với rủi ro và đặc tính của tác vụ.

## 11. Xử lý thiếu tín hiệu và lỗi phụ thuộc

Risk engine là một phụ thuộc có thể chậm, trả dữ liệu cũ hoặc ngừng hoạt động. Không nên để toàn bộ chính sách chỉ có hai trạng thái ngầm: “có score” và “cho qua nếu không có score”.

Đối với dịch vụ minh họa, chọn chế độ suy giảm theo từng nhóm:

| Tình trạng | Hành vi được định nghĩa |
|---|---|
| Thiếu dữ liệu thiết yếu cho đổi role | Tạm dừng thao tác; trả kết quả để thử lại hoặc chuyển xử lý |
| Thiếu một tín hiệu bổ trợ cho tác vụ ít ảnh hưởng | Có thể dùng chính sách nền đã phê duyệt nếu mọi điều kiện bắt buộc vẫn kiểm tra được |
| Không xác minh được trạng thái thu hồi phiên | Không thực hiện hành động nhạy cảm dựa trên giả định phiên còn hợp lệ |
| Dữ liệu rủi ro quá cũ | Không tái sử dụng như một kết luận mới |
| Hệ thống liên tục yêu cầu step-up nhưng không hoàn tất được | Giới hạn vòng lặp và cung cấp đường hỗ trợ có kiểm soát |

Các hành vi này là lựa chọn thiết kế cần được chủ sở hữu chính sách chấp nhận trước. Không dùng một cấu hình “fail open” toàn cục để giải quyết mọi sự cố.

Cũng cần chống lạm dụng chính cơ chế bảo vệ. Kẻ tấn công có thể gửi nhiều lần đăng nhập để làm phiền nạn nhân bằng thông báo MFA hoặc cố tạo tín hiệu xấu để khóa tài khoản. Giới hạn tần suất, liên kết giao dịch và tiêu chí khóa cần được thiết kế cùng nhau.

## 12. Sai dương, sai âm và dữ liệu học

Sai dương xảy ra khi người dùng hợp lệ bị đánh giá đáng ngờ; sai âm xảy ra khi hành vi trái phép không bị phát hiện. Giảm số lần hỏi xác thực không đủ để kết luận mô hình tốt hơn nếu đồng thời bỏ lọt nhiều phiên bị chiếm đoạt.

Người đi công tác, người làm ca đêm, người dùng công cụ hỗ trợ hoặc người thường xuyên thay mạng có thể tạo lịch sử khác nhóm đông người. Việc hiệu chỉnh cần kiểm tra các nhóm này, tránh biến hành vi phổ biến nhất thành tiêu chuẩn duy nhất cho người hợp lệ.

Với tài khoản mới, chưa có baseline cá nhân để so sánh. Trong thiết kế minh họa, trạng thái “chưa có lịch sử” được giữ riêng; hệ thống dựa vào chính sách tối thiểu và tín hiệu khác thay vì gắn nhãn nguy hiểm hoặc an toàn một cách tuyệt đối.

Không dùng mọi lần vượt qua MFA làm nhãn chắc chắn là người thật. Kẻ tấn công có thể chuyển tiếp mã, gây nhầm phê duyệt hoặc kiểm soát authenticator. Nếu đưa các lần đó vào dữ liệu “hợp lệ”, mô hình có thể học theo hành vi của chính kẻ tấn công.

Mô hình cũng có thể bị thay đổi phân bố dữ liệu khi công ty đổi VPN, triển khai trình duyệt mới hoặc thay ca làm việc. Cần theo dõi ảnh hưởng sau thay đổi hạ tầng và có cơ chế quay lại phiên bản trước mà vẫn giữ chính sách xác thực nền.

## 13. Dữ liệu riêng tư và khả năng giải thích

Thu thập và xử lý đặc điểm phiên có tác động riêng tư. NIST yêu cầu đưa các tác động này vào đánh giá rủi ro riêng tư. [NIST SP 800-63B: Session Monitoring](https://pages.nist.gov/800-63-4/sp800-63b.html#session-monitoring).

Đối với bài thực hành, trước khi thêm một tín hiệu, cần viết mục đích sử dụng, mức chi tiết cần thiết, thời gian lưu và người được đọc. Không thu thập mọi dữ liệu có thể lấy chỉ vì sau này “có thể hữu ích”.

Hệ thống cần cung cấp hai mức giải thích. Với người dùng, thông báo nên nêu hành động cần làm bằng ngôn ngữ dễ hiểu. Với nhóm vận hành, cần mã lý do đủ cụ thể để điều tra, nhưng không tiết lộ toàn bộ ngưỡng và cơ chế phát hiện trong phản hồi công khai.

Một sự kiện quyết định minh họa:

```json
{
  "decisionId": "ad-702",
  "subjectId": "person-84",
  "tenantId": "tenant-a",
  "action": "report.export",
  "result": "REQUIRE_STEP_UP",
  "reasonCodes": ["ACTION_SENSITIVE", "AUTHENTICATION_TOO_OLD"],
  "policyVersion": "adaptive-v3",
  "assessmentId": "risk-128",
  "correlationId": "req-901"
}
```

Không ghi mật khẩu, mã OTP, session token hoặc mẫu sinh trắc vào bản ghi đó. Nếu cần liên kết phiên giữa các sự kiện, dùng tham chiếu nội bộ được bảo vệ, không đưa bearer token vào log.

## 14. Triển khai và đánh giá từng bước

Bắt đầu bằng một tập rule nhỏ cho vài hành động nhạy cảm sẽ giúp tìm lỗi chính sách và dữ liệu trước khi mở rộng. Cách triển khai minh họa:

1. Chốt điều kiện nền, ranh giới tenant và các yêu cầu không được bù trừ bằng score.
2. Xác định nguồn tín hiệu, độ mới và hành vi khi nguồn lỗi.
3. Chạy chính sách mới ở chế độ quan sát, ghi quyết định dự kiến nhưng giữ cơ chế bảo vệ hiện hành.
4. Đánh giá tác động qua các kịch bản có dữ liệu và kết quả mong đợi.
5. Áp dụng cho phạm vi nhỏ, theo dõi trải nghiệm và sự kiện bảo mật.
6. Mở rộng sau khi có cách xử lý hỗ trợ, ngoại lệ có thời hạn và khả năng quay lại phiên bản trước.

Chế độ quan sát không phải cho phép bỏ kiểm tra xác thực bắt buộc. Nó chỉ tách việc đánh giá tác động của chính sách bổ sung mới khỏi quyết định sản xuất hiện hành.

Các chỉ số nên theo dõi gồm tỷ lệ yêu cầu step-up, tỷ lệ hoàn tất, số lần từ chối bị khiếu nại hợp lệ, độ trễ đánh giá, lỗi nguồn tín hiệu và các sự cố bị bỏ lọt đã xác nhận. Cần tách theo nhóm hành động và bối cảnh để một tỷ lệ trung bình không che vấn đề của quản trị viên hoặc người dùng thường xuyên di chuyển.

Một danh sách ngoại lệ vô thời hạn cho người có quyền cao có thể phá mục tiêu của thiết kế. Nếu cần ngoại lệ vận hành, phải xác định phạm vi, người phê duyệt, thời hạn và biện pháp bù đắp cụ thể.

## 15. Bài tập và ca kiểm thử

Thiết kế adaptive authentication cho hai hành động: đọc hồ sơ của chính mình và cấp role quản trị trong tenant. Người dùng đã có session, nhưng các tín hiệu về thiết bị, sự kiện tài khoản và thời điểm xác thực có thể thay đổi.

Đầu ra cần có là danh mục tín hiệu, bảng quyết định, mô hình giao dịch step-up, chính sách phiên và hành vi suy giảm. Mỗi quyết định phải giải thích được bằng yêu cầu nền, ngữ cảnh và bằng chứng hiện có.

| Kịch bản | Kết quả cần kiểm chứng |
|---|---|
| Session hợp lệ, tác vụ ít ảnh hưởng, đủ điều kiện nền | Không yêu cầu lặp lại vô ích; vẫn kiểm tra permission |
| IP quen thuộc nhưng chưa có xác thực hợp lệ | Không cho đọc dữ liệu riêng tư chỉ nhờ tín hiệu mạng |
| Đổi role với bằng chứng xác thực đã quá cũ | Chặn tác dụng phụ và yêu cầu step-up phù hợp |
| Client tự gửi score thấp và cờ MFA | Không thay thế kết quả đánh giá hoặc xác thực phía server |
| Thiết bị mới nhưng người dùng hợp lệ | Xử lý theo chính sách, không kết luận tự động là tấn công |
| Session đã thu hồi nhưng score thấp | Từ chối theo điều kiện bắt buộc |
| Hoàn tất step-up bằng tài khoản khác | Không nâng mức xác thực cho session đang yêu cầu |
| Dùng lại giao dịch step-up một lần | Không được dùng vượt phạm vi hoặc số lần đã định nghĩa |
| Quyền bị thu hồi trong lúc step-up | Không tiếp tục thao tác chỉ vì xác thực vừa thành công |
| Nguồn risk engine lỗi khi cấp role | Thực hiện chế độ suy giảm đã chọn, không tự cho qua |
| Thông báo rủi ro đến muộn | Dùng thời điểm quan sát và xử lý phiên liên quan phù hợp |
| Session SSO nhận assertion mới từ lần xác thực cũ | Không mặc định coi là xác thực lại gần đây |
| Tín hiệu đổi mạng do VPN doanh nghiệp | Kiểm tra sai dương và khả năng hỗ trợ người dùng |
| Hai request đồng thời tiêu thụ một kết quả dùng một lần | Chỉ một thao tác được chấp nhận theo trạng thái giao dịch |

Nghiệm thu khi người học chỉ ra được dữ liệu nào là tín hiệu, dữ liệu nào là bằng chứng xác thực, và quyết định nào được backend thực thi trước tác dụng phụ. Các đường lỗi, khôi phục và ngoại lệ phải có hành vi xác định; không để trường hợp chưa biết trở thành cho phép mặc định.

Adaptive authentication hữu ích khi kết nối ngữ cảnh rủi ro với yêu cầu xác thực có thể kiểm chứng. Giá trị của nó nằm ở quyết định được thực thi đúng phạm vi và đúng thời điểm, cùng khả năng điều tra và hiệu chỉnh khi bối cảnh thay đổi.
