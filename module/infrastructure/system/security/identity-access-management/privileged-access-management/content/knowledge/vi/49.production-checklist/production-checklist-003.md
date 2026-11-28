# Đã bật MFA

## 1. “Đã bật” phải có nghĩa là đã thực thi

Trong checklist production của hệ thống quản lý truy cập đặc quyền (PAM), “đã bật MFA” không chỉ có nghĩa là người quản trị nhìn thấy tùy chọn xác thực nhiều yếu tố trong màn hình cấu hình. Điều phải chứng minh là **một người không thể nhận hoặc sử dụng quyền đặc biệt qua các đường truy cập thuộc phạm vi triển khai nếu chưa đáp ứng chính sách xác thực tương ứng**.

Phạm vi này có thể gồm đăng nhập cổng PAM, quản trị vault, lấy credential, mở phiên SSH/RDP qua broker, kích hoạt quyền JIT/JEA, phê duyệt yêu cầu và thay đổi cấu hình bảo mật. Tùy kiến trúc, một lần xác thực đủ mạnh có thể được dùng lại trong một khoảng thời gian có kiểm soát; không nhất thiết yêu cầu nhập mã MFA ở mọi lần bấm. Tuy nhiên, hành động nhạy cảm phải kiểm tra được người dùng, ngữ cảnh và độ mới của lần xác thực đáp ứng chính sách.

Ví dụ, một tổ chức đã bắt buộc MFA ở cổng SSO nhưng vẫn cho phép tài khoản quản trị cục bộ đăng nhập trực tiếp vào vault bằng mật khẩu. Tổ chức đó mới bảo vệ được một đường vào. Không thể đánh dấu toàn bộ mục MFA là đạt chỉ vì màn hình SSO đã có bước xác thực thứ hai.

Sau bài học, người học cần làm được bốn việc:

- Xác định những danh tính và đường truy cập phải chịu chính sách MFA.
- Phân biệt MFA thông thường với xác thực có khả năng chống phishing.
- Thực hiện kiểm thử tích cực và kiểm thử từ chối cho các thao tác đặc quyền.
- Lưu bộ bằng chứng đủ để người khác kiểm tra lại quyết định cho phép đưa hệ thống vào production.

Bài này tập trung vào danh tính con người thực hiện thao tác đặc quyền. Tài khoản dịch vụ, workload và tác vụ tự động được kiểm soát theo cơ chế dành cho danh tính máy, được phân biệt rõ ở phần sau.

## 2. Hiểu đúng yếu tố xác thực

MFA kết hợp các loại yếu tố độc lập để xác minh danh tính. Các loại thường gặp là thông tin người dùng biết, vật hoặc thiết bị người dùng sở hữu, và đặc điểm sinh trắc học của người dùng.

| Tổ hợp hoặc phương thức | Cách hiểu đúng | Điểm cần kiểm tra khi dùng cho PAM |
| --- | --- | --- |
| Mật khẩu và câu hỏi bí mật | Đều là yếu tố “biết”; không tạo thành MFA chỉ vì có hai câu hỏi | Không tính đây là bằng chứng đáp ứng nhiều yếu tố |
| Mật khẩu và mã TOTP từ ứng dụng | Kết hợp yếu tố biết và sở hữu nếu triển khai đúng | Mã vẫn có thể bị nhập vào trang phishing và chuyển tiếp |
| Mật khẩu và thông báo push | Có thể tạo thành MFA | Phải kiểm soát yêu cầu bất thường, push liên tiếp và việc người dùng phê duyệt nhầm |
| Khóa bảo mật hoặc passkey dựa trên FIDO | Có thể cung cấp xác thực chống phishing nhờ ràng buộc với bên nhận xác thực | Xác minh có yêu cầu user verification, loại authenticator và chính sách đăng ký phù hợp |
| Mã gửi qua SMS | Có thể được dùng như yếu tố sở hữu trong một số triển khai | Có rủi ro liên quan số điện thoại, khôi phục và chuyển quyền kiểm soát SIM |
| Recovery code | Phương tiện khôi phục hoặc thay thế theo thiết kế | Không mặc định tương đương với phương thức MFA chính; phải quản lý như bí mật nhạy cảm |

Hai màn hình đăng nhập không chứng minh có hai yếu tố. Hai mật khẩu khác nhau vẫn cùng loại yếu tố. Cũng không thể suy từ tên thương mại của một phương thức để kết luận mức bảo đảm: cần kiểm tra cấu hình, cách xác minh người dùng và đường khôi phục thực tế.

Với passkey hoặc khóa bảo mật, sinh trắc học có thể được dùng để mở khóa authenticator ngay trên thiết bị. Trong mô hình phổ biến, dịch vụ nhận bằng chứng xác thực bằng mật mã, không nhận mẫu vân tay hay khuôn mặt để tự đối chiếu. Không viết log hoặc yêu cầu người dùng đưa dữ liệu sinh trắc học vào hồ sơ kiểm toán.

### Chống phishing khác với chỉ có thêm một bước

Một trang giả có thể yêu cầu người dùng nhập cả mật khẩu lẫn mã TOTP. Kẻ tấn công có thể chuyển tiếp mã còn hiệu lực sang trang thật. Vì vậy, TOTP không tự động trở thành phương thức chống phishing.

Xác thực FIDO/WebAuthn được thiết kế để ràng buộc phản hồi xác thực với bên nhận xác thực. Điều này giúp chống kiểu đánh cắp và chuyển tiếp thông tin xác thực qua tên miền giả, nhưng không làm cho toàn bộ máy trạm hay phiên làm việc trở nên an toàn. Máy trạm bị kiểm soát, phiên bị chiếm dụng sau đăng nhập hoặc kênh khôi phục yếu vẫn là những vấn đề phải xử lý.

Đối với người quản trị PAM, vault hoặc hạ tầng trọng yếu, checklist cần ghi rõ tổ chức yêu cầu phương thức nào. Không chỉ ghi “MFA bất kỳ” nếu thiết kế bảo mật đã yêu cầu khả năng chống phishing.

## 3. Lập phạm vi theo danh tính và đường truy cập

Bắt đầu bằng câu hỏi: **ai có thể làm gì, qua đường nào, với mức quyền nào?** Danh sách người dùng đã đăng ký MFA chỉ là một phần của câu trả lời.

Các nhóm con người cần xem xét gồm quản trị viên nền tảng PAM, quản trị vault, người vận hành có quyền lấy credential, người mở phiên đặc quyền, người phê duyệt JIT, người quản trị IdP, nhân sự hỗ trợ và nhà cung cấp được cấp quyền tạm thời. Một người có thể giữ nhiều tài khoản; phải kiểm tra cả tài khoản làm việc hằng ngày và tài khoản quản trị tách biệt của họ.

Lập bảng các đường truy cập trước khi kết luận:

| Đường truy cập | Ví dụ thao tác | Câu hỏi kiểm tra MFA |
| --- | --- | --- |
| Cổng web PAM qua SSO | Yêu cầu phiên, xem tài sản được cấp | PAM có thực sự yêu cầu và kiểm tra ngữ cảnh xác thực từ IdP không? |
| Giao diện quản trị vault | Thêm secret, đổi chính sách, cấp quyền | Có yêu cầu xác thực đủ mạnh cho vai trò quản trị không? |
| Đăng nhập cục bộ vào PAM | Tài khoản local trong giao diện quản trị | Có đường mật khẩu đơn lẻ còn hoạt động không? |
| Credential checkout hoặc reveal | Lấy mật khẩu quản trị để dùng ngoài broker | Lần xác thực có đáp ứng chính sách cho việc tiết lộ bí mật không? |
| Session broker | Mở SSH/RDP hoặc ứng dụng quản trị | Quyết định mở phiên có gắn với đúng người và lần xác thực hợp lệ không? |
| CLI hoặc API do con người sử dụng | Lấy credential bằng công cụ dòng lệnh | Token được cấp từ luồng nào, có thể bỏ qua chính sách qua luồng khác không? |
| Truy cập trực tiếp hệ thống đích | SSH thẳng vào máy chủ, console cloud | Đường này đã bị chặn, giới hạn hay có kiểm soát xác thực riêng tương xứng? |
| Quản trị chính IdP | Thay policy, reset phương thức MFA | Người có thể làm yếu MFA có chịu kiểm soát đủ mạnh không? |
| Nhà cung cấp bên ngoài | Truy cập qua federation hoặc tài khoản khách | Bằng chứng MFA từ bên ngoài có được tin cậy theo hợp đồng kỹ thuật cụ thể không? |
| Đường khẩn cấp | Truy cập khi IdP không sẵn sàng | Ngoại lệ được nhận diện, bảo vệ, cảnh báo và kiểm tra lại như thế nào? |

Nếu bảng còn một đường chưa rõ cơ chế, trạng thái của đường đó là **chưa xác minh**, không phải “đạt mặc định”. Một đường truy cập trực tiếp có thể nằm ngoài chức năng kỹ thuật của PAM nhưng vẫn nằm trong rủi ro cần kiểm soát trước khi đưa PAM vào vận hành.

Tài khoản dùng chung làm suy yếu khả năng quy trách nhiệm. Nếu hệ thống đích buộc phải dùng một tài khoản quản trị dùng chung, PAM vẫn cần xác thực từng cá nhân trước khi cấp hoặc sử dụng credential đó, đồng thời liên kết được người, yêu cầu, phiên và tài khoản đích.

## 4. Phân biệt đăng ký MFA với bắt buộc MFA

Đăng ký authenticator chỉ chứng minh tài khoản có phương tiện xác thực. Cấu hình chính sách và kiểm thử thực thi mới cho biết tài khoản có bắt buộc dùng phương tiện đó hay không.

Một rollout có thể ở các trạng thái khác nhau:

1. Người dùng được phép tự đăng ký MFA.
2. Người dùng đã đăng ký ít nhất một phương thức.
3. Chính sách đã cấu hình nhưng chỉ ở chế độ quan sát.
4. Chính sách đang thực thi nhưng chỉ áp dụng cho một phần nhóm quản trị.
5. Chính sách thực thi trên các đường thuộc phạm vi và đã vượt qua kiểm thử từ chối.

Chỉ trạng thái cuối cùng mới đủ làm nền cho quyết định “đã bật MFA” đối với phạm vi đã xác định. Ngay cả khi tỷ lệ đăng ký là 100%, một tài khoản nằm trong nhóm loại trừ rộng vẫn có thể vào bằng mật khẩu.

Cần đọc kết quả chính sách hiệu lực đối với tài khoản mẫu, thay vì chỉ đọc tên policy. Các yếu tố có thể làm thay đổi kết quả gồm nhóm người dùng, vai trò, ứng dụng, nguồn kết nối, thiết bị, luồng đăng nhập, thứ tự xử lý policy và thời gian chuyển tiếp rollout.

Một cấu hình minh họa, độc lập với sản phẩm:

```yaml
# Mô hình chính sách minh họa, không phải cấu hình để nạp vào một sản phẩm.
human_privileged_access:
  scope:
    applications:
      - pam-portal
      - vault-administration
    roles:
      - pam-administrator
      - privileged-operator
      - privileged-approver
  enforcement: enabled
  authentication:
    required_strength: phishing_resistant_with_user_verification
    freshness: defined_by_action_risk_policy
  sensitive_actions:
    - reveal_credential
    - activate_privilege
    - change_security_policy
    - reset_authenticator
  exceptions:
    source: approved_emergency_access_register
    require_owner: true
    require_review_date: true
    alert_on_use: true
```

Mục đích của ví dụ là làm rõ phạm vi, trạng thái thực thi, mức xác thực và ngoại lệ. Các giá trị phải được ánh xạ sang khả năng có thật của IdP và PAM đang triển khai; không sao chép ví dụ rồi coi đó là bằng chứng hệ thống đã được bảo vệ.

## 5. Ràng buộc MFA với hành động đặc quyền

MFA ở thời điểm đăng nhập và MFA đủ mới cho hành động đặc quyền là hai câu hỏi khác nhau.

Ví dụ, người dùng đăng nhập SSO buổi sáng để đọc tài liệu. Đến cuối ngày, họ yêu cầu tiết lộ credential quản trị database. Tổ chức có thể yêu cầu xác thực bổ sung vì mức rủi ro của hành động tăng lên hoặc lần xác thực trước đã quá cũ theo chính sách. Đây là step-up authentication.

Không cần đặt một thời hạn giống nhau cho mọi hành động. Cần có quyết định được phê duyệt về độ mới xác thực, thời gian sống của phiên và điều kiện phải xác thực lại. Các giá trị phải phù hợp mức nhạy cảm và khả năng hỗ trợ của hệ thống.

### Khi PAM dùng SSO

IdP thực hiện xác thực; PAM là bên tiêu thụ kết quả và ra quyết định cho phép hành động. Phải kiểm tra cả hai phía.

PAM hoặc thư viện xác thực được hỗ trợ cần xác minh token hoặc assertion theo giao thức đang dùng, bao gồm tính toàn vẹn, bên phát hành, bên nhận, thời hạn và các ràng buộc giao thức tương ứng. Không tự viết bộ xử lý token từ một đoạn ví dụ trong tài liệu học.

Trong OIDC, các claim như `acr`, `amr` và `auth_time` có thể hỗ trợ biểu diễn mức, phương thức và thời điểm xác thực. Ý nghĩa và việc có mặt của chúng phụ thuộc IdP, cấu hình và hợp đồng tích hợp. Với SAML, cần xem ngữ cảnh xác thực và những ràng buộc tương ứng mà sản phẩm hỗ trợ.

Không kết luận token “đã MFA” chỉ từ một chuỗi ký tự trong claim mà chưa xác minh nguồn phát hành và quy ước ý nghĩa. Cũng không mặc định một giá trị `amr` bất kỳ chứng minh xác thực chống phishing.

Quyết định minh họa cho một hành động:

```text
Khi nhận yêu cầu reveal_credential:
  1. Xác minh phiên và danh tính bằng cơ chế giao thức được hỗ trợ.
  2. Kiểm tra người dùng được cấp quyền đối với credential đích.
  3. Kiểm tra yêu cầu và phê duyệt cần thiết còn hợp lệ.
  4. Đọc ngữ cảnh xác thực đã được xác minh.
  5. Nếu chưa đủ mức hoặc chưa đủ mới:
       yêu cầu step-up bằng luồng được hỗ trợ;
       chưa tiết lộ credential.
  6. Nếu step-up thành công và gắn đúng phiên/yêu cầu:
       cho phép hành động;
       ghi sự kiện kiểm toán.
  7. Nếu step-up thất bại, bị hủy hoặc không xác minh được:
       từ chối hành động;
       ghi lý do phù hợp, không ghi bí mật.
```

MFA không thay thế phân quyền, phê duyệt hay giới hạn thời gian JIT. Một người xác thực rất mạnh vẫn có thể không được quyền lấy credential hoặc mở phiên trên một tài sản cụ thể.

### Tránh khoảng trống sau khi đã mở phiên

Chính sách cần xác định điều gì xảy ra khi người dùng bị vô hiệu hóa, phiên IdP bị thu hồi hoặc vai trò bị gỡ trong lúc phiên đặc quyền còn mở. Không mặc định mọi hệ thống tự đóng tất cả phiên ngay tức thì.

Kiểm tra khả năng thực tế của broker và ứng dụng đích: có đóng phiên chủ động không, khi nào đánh giá lại quyền, ai nhận cảnh báo và ai có thể chấm dứt phiên. Đối với credential đã được tiết lộ, thu hồi token đăng nhập không làm mật khẩu đã lộ biến mất; cần cơ chế rotate hoặc thu hồi quyền đích phù hợp.

## 6. Kiểm tra vòng đời authenticator

Chính sách mạnh ở bước đăng nhập có thể bị vô hiệu hóa nếu đăng ký và khôi phục quá yếu. Người có thể đăng ký authenticator mới hoặc reset MFA có khả năng thay đổi người kiểm soát tài khoản.

### Đăng ký ban đầu

Trước khi cấp authenticator cho tài khoản quản trị, cần xác minh đúng người nhận bằng quy trình đã phê duyệt. Không chỉ dựa vào một email yêu cầu “thêm thiết bị mới” hoặc một cuộc gọi tự xưng là quản trị viên.

Ghi nhận phương thức được phép, người thực hiện đăng ký và thời điểm đăng ký. Nếu tổ chức yêu cầu thiết bị được quản lý hoặc authenticator được tổ chức cấp, phải kiểm tra điều kiện này ở hệ thống thực thi, không chỉ ghi trong hướng dẫn.

Với tài khoản đặc quyền quan trọng, có thể cấp phương tiện dự phòng theo chính sách để tránh phụ thuộc duy nhất một thiết bị. Phương tiện dự phòng phải được bảo quản và kiểm kê phù hợp; không biến nó thành một bản sao bí mật được lưu chung với mật khẩu.

### Thay thiết bị, mất thiết bị và khôi phục

Quy trình cần trả lời rõ:

- Ai được yêu cầu khôi phục và cần chứng minh danh tính như thế nào?
- Ai được phê duyệt, ai thực hiện và khi nào cần tách người phê duyệt khỏi người thao tác?
- Authenticator bị mất được thu hồi ở đâu?
- Có cần thu hồi phiên, token hoặc quyền tạm đang hoạt động không?
- Phương thức tạm có thời hạn và được loại bỏ sau khi khôi phục không?
- Chủ tài khoản và đội giám sát có nhận thông báo về thay đổi không?

Không để helpdesk vô hiệu hóa MFA vô thời hạn chỉ vì người gọi biết một vài thông tin cá nhân. Một đường khôi phục yếu có thể trở thành đường đăng nhập chính của kẻ tấn công.

Đối với recovery code, không ghi giá trị code vào ticket hoặc ảnh chụp bằng chứng. Lưu bằng chứng đã cấp, đã dùng hoặc đã thu hồi theo khả năng của hệ thống; bí mật thực tế nằm trong nơi lưu trữ được phép.

### Nghỉ việc và chuyển vai trò

Thu hồi tài khoản hoặc quyền quản trị phải kéo theo xử lý authenticator và phiên liên quan theo quy trình. Thiết bị được trả lại không tự động chứng minh tài khoản đã mất quyền; xóa tài khoản trong một hệ thống cũng không tự động thu hồi mọi token ở hệ thống khác.

Trong checklist, cần có kiểm thử cho người bị gỡ khỏi nhóm quản trị: họ không còn mở được phiên đặc quyền hoặc lấy credential mới bằng một phiên đăng nhập cũ ngoài giới hạn mà chính sách cho phép.

## 7. Quản lý ngoại lệ và đường khẩn cấp

Một tài khoản khẩn cấp có thể được thiết kế để dùng khi IdP hoặc hạ tầng MFA gặp sự cố. Nếu cơ chế truy cập này phụ thuộc hoàn toàn vào chính thành phần đang hỏng, nó không đáp ứng mục tiêu phục hồi.

Tuy nhiên, ngoại lệ không được trở thành nhóm “bỏ MFA” chứa nhiều người dùng hoạt động hằng ngày. Mỗi đường khẩn cấp phải có mục đích, người sở hữu, phương thức bảo vệ, điều kiện sử dụng, giám sát và quy trình kiểm tra sau sử dụng.

Nếu sản phẩm và kiến trúc hỗ trợ, có thể dùng authenticator độc lập với dịch vụ đang được phục hồi. Nếu đường khẩn cấp được chấp thuận không dùng MFA, hồ sơ phải ghi rõ điều đó cùng các kiểm soát bù. Không báo cáo đường đó là “đã MFA” để làm đẹp tỷ lệ bao phủ.

Bảng ngoại lệ tối thiểu:

| Trường | Nội dung cần ghi |
| --- | --- |
| Định danh | Tài khoản hoặc đường truy cập cụ thể, tránh nhóm không xác định |
| Mục đích | Sự cố nào cần dùng và vì sao đường bình thường không đủ |
| Người sở hữu | Người chịu trách nhiệm duy trì, kiểm tra và thu hồi |
| Phương thức bảo vệ | MFA độc lập hoặc các kiểm soát bù đã chấp thuận |
| Giới hạn | Tài sản, quyền, thời gian và người được phép kích hoạt |
| Giám sát | Sự kiện cảnh báo, nơi nhận và người trực tiếp phản hồi |
| Rà soát | Ngày xem lại, thời hạn ngoại lệ hoặc lịch kiểm thử khẩn cấp |
| Sau sử dụng | Thu hồi phiên, rotate credential khi cần, điều tra và đóng hồ sơ |

Kiểm thử đường khẩn cấp có kế hoạch, trong cửa sổ được cho phép. Không thử bằng cách tắt MFA trên diện rộng hoặc cắt IdP production chỉ để xem hệ thống có hoạt động hay không.

## 8. Tài khoản dịch vụ không phải người nhập mã MFA

Tài khoản dịch vụ, pipeline CI/CD và workload thường không có con người hiện diện để nhập mã. Việc đặt một ứng dụng TOTP trong cùng script với mật khẩu không tạo ra sự độc lập có ý nghĩa giữa các yếu tố khi cả hai cùng bị lấy từ một nơi.

Không tự ý bắt mọi service account phải dùng một luồng MFA tương tác. Thay vào đó, cần phân loại rõ danh tính máy và áp dụng cơ chế phù hợp, chẳng hạn danh tính workload, chứng thư, federation hoặc credential ngắn hạn, kết hợp quyền tối thiểu, giới hạn tài nguyên và khả năng thu hồi.

Có hai tình huống phải tách:

- **Workload tự động chạy theo lịch:** xác thực bằng danh tính máy, được giới hạn quyền và ghi log theo danh tính workload.
- **Con người dùng CLI để thao tác đặc quyền:** cần luồng cấp quyền cho con người đáp ứng chính sách MFA; không lấy cớ “đang gọi API” để chuyển sang một token tĩnh được miễn kiểm soát.

Khi một người sử dụng credential của service account để đăng nhập tương tác, phải xử lý đó là một đường truy cập của con người chưa được kiểm soát đúng mục đích. Các biện pháp có thể gồm cấm đăng nhập tương tác khi nền tảng hỗ trợ, giới hạn nguồn sử dụng, môi giới qua PAM và điều tra cách credential được phân phối.

MFA cũng không bảo vệ một API token tĩnh chỉ vì người tạo token từng đăng nhập bằng MFA. Token bị sao chép có thể được sử dụng theo quyền và thời hạn riêng của nó. Vì vậy, checklist phải kiểm tra các đường token có thể thay thế đăng nhập tương tác.

## 9. Bộ kiểm thử trước production

Thực hiện với tài khoản, tài sản và cửa sổ kiểm thử đã được cho phép. Dùng credential thử nghiệm và bằng chứng đã che dữ liệu nhạy cảm. Không thu thập mã OTP, khóa riêng hoặc cookie thật vào báo cáo.

“Đăng nhập thành công” chỉ là kiểm thử tích cực. Bằng chứng thực thi cần có tình huống mà hệ thống phải từ chối.

| Mã | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| MFA-01 | Người quản trị dùng phương thức được phép, đủ điều kiện | Đăng nhập hoặc step-up thành công, có sự kiện gắn với đúng người |
| MFA-02 | Có mật khẩu đúng nhưng chưa hoàn tất yếu tố cần thiết | Không cấp phiên hoặc hành động đặc quyền tương ứng |
| MFA-03 | Người dùng hủy, từ chối hoặc làm thất bại bước MFA | Hành động bị từ chối, không để lại credential hoặc phiên đã được cấp trước |
| MFA-04 | Tài khoản quản trị chưa đăng ký phương thức hợp lệ | Không dùng được quyền đặc biệt qua đường đang kiểm thử; luồng onboarding không cho vượt quyền |
| MFA-05 | Thử phương thức yếu hơn mức chính sách yêu cầu | Bị từ chối hoặc yêu cầu chuyển sang phương thức đủ mạnh |
| MFA-06 | Phiên đăng nhập cũ được dùng cho hành động cần xác thực mới | Yêu cầu step-up trước khi thực hiện hành động |
| MFA-07 | Truy cập local, CLI, API hoặc đường legacy bằng mật khẩu đơn lẻ | Bị chặn hoặc chịu cơ chế đã được thiết kế và xác minh riêng |
| MFA-08 | Người đã bị gỡ quyền cố dùng phiên cũ để xin quyền mới | Không cấp thêm quyền ngoài thời gian và điều kiện đã được phê duyệt |
| MFA-09 | Yêu cầu reset hoặc thêm authenticator cho tài khoản quản trị | Áp dụng đúng xác minh danh tính, phê duyệt và thông báo |
| MFA-10 | Sự cố IdP/MFA được mô phỏng trong môi trường phù hợp | Đường bình thường có hành vi từ chối đã định nghĩa; không tự chuyển sang mật khẩu |
| MFA-11 | Sử dụng đường khẩn cấp theo kịch bản được duyệt | Truy cập đúng giới hạn, cảnh báo đến nơi nhận và có bằng chứng sau sử dụng |
| MFA-12 | Kiểm tra sự kiện thay đổi chính sách hoặc thêm người vào ngoại lệ | Có log và cảnh báo theo thiết kế, xác định được người thay đổi |
| MFA-13 | Nhà cung cấp đăng nhập qua federation | Mức xác thực được đánh giá theo quy ước tin cậy; bằng chứng thiếu không bị tự coi là đạt |
| MFA-14 | Workload hoặc pipeline lấy secret | Dùng đúng danh tính máy, đúng quyền và thời hạn; không dùng tài khoản người để né MFA |

Bảng này là bộ khung. Phải mở rộng theo những đường có thật trong inventory, không đánh dấu một ca “không áp dụng” chỉ vì chưa biết cách kiểm tra.

Với mỗi ca, lưu điều kiện ban đầu, tài khoản/vai trò mẫu, phiên bản chính sách, bước thực hiện, kết quả mong đợi, kết quả quan sát, thời điểm và người kiểm tra. Nếu kiểm thử thất bại, ghi issue và retest sau khi sửa; giữ cả bằng chứng lần đầu và lần xác minh lại.

### Ví dụ kiểm thử đường bypass

Giả sử vận hành bình thường dùng SSO vào PAM rồi mở RDP qua broker. Hệ thống vẫn còn cổng quản trị cục bộ dành cho bảo trì.

Kịch bản kiểm tra:

1. Dùng tài khoản local thử nghiệm được phép để truy cập đúng cổng quản trị đó.
2. Kiểm tra mật khẩu đơn lẻ có tạo được phiên quản trị hay không.
3. Nếu tạo được, ghi rõ tài khoản, đường vào và quyền quan sát được; dừng trước thao tác thay đổi.
4. Đối chiếu đây có phải ngoại lệ được duyệt hay là lỗ hổng triển khai.
5. Sau khi cấu hình lại, kiểm thử từ chối cùng đường vào và kiểm tra log.
6. Kiểm tra đường bảo trì hoặc khẩn cấp hợp lệ vẫn đáp ứng mục tiêu phục hồi.

Không sửa kết quả thành “PASS vì chỉ mạng nội bộ truy cập được”. Giới hạn mạng là một kiểm soát khác; nó không biến đăng nhập bằng mật khẩu thành MFA.

## 10. Ghi log và lưu bằng chứng đúng mức

Bằng chứng nên cho thấy sự liên kết giữa cấu hình, thực thi và kết quả. Chỉ chụp màn hình công tắc “Enable MFA” không đủ để kiểm tra một hành động đặc quyền cụ thể đã được bảo vệ.

Bộ hồ sơ nên gồm:

- Inventory người và đường truy cập thuộc phạm vi, kèm đường đã chặn hoặc loại trừ.
- Bản trích chính sách hiệu lực, phiên bản, thời điểm và nhóm/vai trò áp dụng.
- Bằng chứng đăng ký phương thức phù hợp của tập tài khoản cần bảo vệ.
- Kết quả kiểm thử thành công, từ chối, step-up, khôi phục và đường khẩn cấp.
- Log xác thực liên kết được với yêu cầu hoặc phiên đặc quyền.
- Danh sách ngoại lệ và quyết định xử lý các ca chưa đạt.
- Người chịu trách nhiệm và người phê duyệt kết quả triển khai.

Một sự kiện minh họa đã lược bỏ bí mật:

```json
{
  "event": "privileged_action_authentication",
  "timestamp": "2026-01-15T08:30:00Z",
  "subject_id": "admin-example-17",
  "application": "pam-portal",
  "action": "reveal_credential",
  "target_reference": "database-prod-example",
  "request_id": "request-example-428",
  "policy_id": "pam-sensitive-action",
  "policy_version": "example-v3",
  "authentication_context": {
    "mapped_strength": "phishing_resistant",
    "user_verification": true,
    "authentication_time": "2026-01-15T08:29:42Z"
  },
  "decision": "allow",
  "evidence_origin": "validated_identity_provider_context"
}
```

Đây là schema minh họa cho hồ sơ kiểm tra, không phải bộ claim chuẩn hoặc bằng chứng do mọi sản phẩm tự phát ra. Trường ánh xạ mức xác thực phải đến từ dữ liệu đã được xác minh và quy ước tích hợp rõ ràng.

Không ghi mật khẩu, TOTP seed, mã OTP, recovery code, private key, access token đầy đủ hoặc session cookie vào log. Ngay cả log không có secret vẫn chứa thông tin người dùng và tài sản nhạy cảm, nên cần phân quyền đọc, bảo vệ tính toàn vẹn và thời hạn lưu theo chính sách.

Đồng bộ thời gian giúp liên kết sự kiện IdP, PAM và hệ thống đích. Nếu đồng hồ lệch đáng kể, việc kết luận hành động được thực hiện sau lần MFA nào có thể sai.

## 11. Đo độ bao phủ bằng nhiều góc nhìn

Không dùng một tỷ lệ duy nhất để che các khoảng trống.

**Độ bao phủ đăng ký** cho biết bao nhiêu tài khoản con người thuộc phạm vi đã có phương thức hợp lệ. Chỉ số này hữu ích cho rollout, nhưng chưa chứng minh thực thi.

**Độ bao phủ thực thi** cho biết bao nhiêu đường truy cập thuộc phạm vi đang thực sự áp dụng yêu cầu xác thực được phê duyệt.

**Độ bao phủ kiểm thử** cho biết bao nhiêu trường hợp cần kiểm tra đã có bằng chứng đạt, đặc biệt các ca từ chối và các đường ít sử dụng.

Ví dụ minh họa:

```text
Tài khoản con người thuộc phạm vi: 25
Đã đăng ký phương thức đạt yêu cầu: 25
Đường truy cập được kiểm kê: 8
Đường áp dụng yêu cầu xác thực thông thường: 6
Đường khẩn cấp được duyệt riêng: 1
Đường chưa kiểm chứng: 1
```

Kết luận đúng là đăng ký đạt 25/25; sáu đường đã áp dụng yêu cầu thông thường; một đường khẩn cấp cần trình bày riêng; một đường chưa đủ bằng chứng. Không thể kết luận “MFA đạt 100%” cho toàn bộ phạm vi.

Mẫu số phải có nguồn và thời điểm chốt. Nếu chỉ tính những tài khoản đã tự đăng ký hoặc những ứng dụng đã kết nối SSO, tỷ lệ có thể đẹp nhưng bỏ sót đúng phần rủi ro cần tìm.

## 12. Quyết định cho phép vận hành

Một mục checklist có ích phải giúp người quyết định biết còn điều gì ngăn hệ thống vận hành an toàn.

Có thể dùng các trạng thái sau:

| Trạng thái | Khi dùng |
| --- | --- |
| Đạt | Các đường thuộc phạm vi đáp ứng chính sách đã phê duyệt, có kiểm thử và bằng chứng |
| Chưa đạt | Có đường hoặc hành động cần MFA nhưng vẫn thực hiện được mà không đáp ứng yêu cầu |
| Chưa xác minh | Thiếu kiểm thử hoặc chưa xác định được hành vi thực tế |
| Ngoại lệ được chấp thuận | Đường cụ thể có quyết định nhận rủi ro và kiểm soát bù; không đồng nghĩa đường đó đã MFA |
| Không áp dụng | Có giải thích kỹ thuật và phạm vi rõ ràng, ví dụ danh tính workload dùng cơ chế riêng |

Một đường quản trị production có thể dùng mật khẩu đơn lẻ ngoài thiết kế, một quy trình reset cho phép chiếm tài khoản hoặc một policy còn ở chế độ quan sát là những lý do cần chặn triển khai trong phạm vi liên quan.

Nếu tổ chức chấp thuận vận hành có ngoại lệ, hồ sơ phải nêu đúng trạng thái của từng đường và đúng người có thẩm quyền nhận rủi ro. Không đổi tên ngoại lệ thành “đạt MFA” và không để người triển khai tự hợp thức hóa kết quả kiểm thử thất bại.

Mẫu kết luận minh họa:

> Phạm vi gồm cổng PAM, quản trị vault, mở phiên broker và tiết lộ credential. Chính sách MFA đã thực thi cho các vai trò quản trị và vận hành được liệt kê trong inventory. Các ca từ chối và step-up đã đạt. Đường khẩn cấp có hồ sơ riêng và cảnh báo đã được thử. Đường CLI cũ chưa đáp ứng chính sách nên bị vô hiệu hóa trước khi mở production. Bộ bằng chứng gắn với phiên bản chính sách đã được người có trách nhiệm phê duyệt.

Kết luận cần gắn với cấu hình thực tế tại thời điểm kiểm tra. Khi cấu hình đổi, bằng chứng trước đó có thể không còn chứng minh trạng thái hiện hành.

## 13. Duy trì sau khi go-live

MFA không phải một lần cấu hình rồi bỏ quên. Những thay đổi sau có thể làm xuất hiện đường truy cập mới hoặc làm giảm mức bảo đảm:

- Thêm ứng dụng, connector, phiên bản API hoặc cổng quản trị.
- Thêm nhóm quản trị, tài khoản nhà cung cấp hoặc phương thức đăng nhập.
- Đổi IdP, federation, mapping claim hoặc chính sách session.
- Cho phép thêm phương thức fallback, reset hoặc khôi phục.
- Thay đổi thời gian sống token hoặc cách cấp credential cho CLI.
- Sửa cấu hình để xử lý sự cố rồi quên khôi phục.

Cần theo dõi thay đổi chính sách, thêm tài khoản vào nhóm ngoại lệ, đăng ký authenticator mới cho người quản trị, reset MFA và sử dụng đường khẩn cấp. Cảnh báo phải có người nhận và quy trình phản hồi đã thử, không chỉ tồn tại trong danh sách rule.

Thực hiện lại kiểm thử liên quan sau thay đổi có ảnh hưởng và theo lịch rà soát của tổ chức. Khi phát hiện đường bypass mới, cập nhật inventory, khoanh vùng quyền bị ảnh hưởng, xử lý cấu hình và lưu retest. Không chỉ tăng số lượng người dùng đã đăng ký MFA.

## 14. Bài thực hành: rà soát một đợt triển khai PAM

Một nhóm sắp đưa PAM vào production có cấu hình sau:

- Người vận hành vào cổng web qua SSO có TOTP.
- Người quản trị vault được yêu cầu khóa bảo mật với user verification.
- CLI cũ dùng personal access token có thời hạn dài.
- Helpdesk được reset MFA cho quản trị viên theo một cuộc gọi xác nhận tên và email.
- Có tài khoản local khẩn cấp nhưng chưa thử cảnh báo khi sử dụng.
- Dashboard hiển thị 100% người dùng quản trị đã đăng ký MFA.

Hãy lập kết luận cho từng thành phần trước khi quyết định toàn phạm vi.

Một hướng phân tích:

1. **Cổng web:** cần đối chiếu TOTP với mức xác thực được phê duyệt cho vai trò và hành động. Phải kiểm tra thực thi, fallback và độ mới; tỷ lệ đăng ký không đủ.
2. **Quản trị vault:** khóa bảo mật có user verification phù hợp hướng bảo vệ mạnh, nhưng vẫn cần kiểm thử đường local, reset, thay đổi policy và hành vi khi xác thực thất bại.
3. **CLI:** token dài hạn có thể tạo đường truy cập độc lập với MFA tương tác. Cần xem nguồn cấp token, phạm vi quyền, khả năng thu hồi và luồng thay thế; chưa thể coi là đạt chỉ vì token do người đã MFA tạo ra.
4. **Helpdesk:** xác minh chỉ bằng tên và email không đủ để tin cậy việc thay quyền kiểm soát tài khoản quản trị. Cần sửa quy trình khôi phục theo chính sách và kiểm thử lại.
5. **Khẩn cấp:** chưa có bằng chứng cảnh báo hoạt động. Phải thử trong phạm vi được duyệt và ghi rõ ngoại lệ nếu có.
6. **Dashboard:** phản ánh việc đăng ký, không thay thế kết quả kiểm tra các đường và vòng đời authenticator.

Sản phẩm của bài thực hành là một bảng gồm đường truy cập, yêu cầu xác thực, bằng chứng, trạng thái, người xử lý và điều kiện retest. Không cần thay đổi hệ thống thật để hoàn thành bài phân tích này.

## 15. Checklist sử dụng khi nghiệm thu

- [ ] Đã kiểm kê đầy đủ tài khoản con người và đường truy cập đặc quyền thuộc phạm vi.
- [ ] Đã xác định mức xác thực cần thiết theo vai trò và hành động.
- [ ] Chính sách đang thực thi, không chỉ ở chế độ quan sát hoặc tự đăng ký.
- [ ] Đã xác minh kết quả chính sách hiệu lực đối với nhóm và tài khoản mẫu.
- [ ] Đã kiểm tra luồng SSO, local, web, broker, CLI/API do con người dùng và truy cập trực tiếp.
- [ ] Hành động nhạy cảm kiểm tra ngữ cảnh và độ mới xác thực theo thiết kế.
- [ ] Đã kiểm thử thành công, từ chối, hủy MFA và các phương thức không đạt yêu cầu.
- [ ] Đăng ký, đổi thiết bị, reset và khôi phục authenticator có kiểm soát phù hợp.
- [ ] Thu hồi tài khoản, vai trò và phiên có hành vi đã được kiểm chứng.
- [ ] Danh tính máy được phân loại và bảo vệ bằng cơ chế riêng, không dùng để né chính sách cho con người.
- [ ] Mọi ngoại lệ có người sở hữu, giới hạn, rà soát và quyết định chấp thuận.
- [ ] Đường khẩn cấp đã được kiểm thử cùng cảnh báo và quy trình sau sử dụng.
- [ ] Log liên kết được danh tính, xác thực, yêu cầu và hành động đặc quyền.
- [ ] Hồ sơ không chứa secret, OTP, token hoặc cookie đầy đủ.
- [ ] Kết luận nghiệm thu nêu rõ phạm vi, phiên bản chính sách, đường chưa đạt và người chịu trách nhiệm.
- [ ] Đã xác định khi nào phải kiểm thử lại sau thay đổi.

Mục “Đã bật MFA” chỉ nên được đánh dấu theo bằng chứng của phạm vi đã kiểm tra. Điều cần giữ được trong vận hành là mối liên hệ giữa **đúng người, mức xác thực phù hợp, hành động được phép và bằng chứng có thể truy lại**.
