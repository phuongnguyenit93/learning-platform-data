# Chính sách mật khẩu, MFA và quản lý phiên đăng nhập

Một tài khoản có quyền quản trị OCI có thể tạo Compute, thay đổi mạng, truy cập dữ liệu hoặc điều chỉnh IAM. Nếu chỉ bảo vệ tài khoản bằng một mật khẩu, việc lộ mật khẩu có thể trở thành điểm khởi đầu của sự cố trên nhiều dịch vụ.

Trong Oracle Cloud Infrastructure, cần phối hợp ba lớp: **chính sách mật khẩu** quản lý mật khẩu của người dùng, **xác thực đa yếu tố (MFA)** tăng mức bảo đảm khi xác thực, và **quản lý phiên đăng nhập** kiểm soát thời gian cùng khả năng tiếp tục sử dụng kết quả xác thực. Các lớp này phục vụ việc bảo vệ danh tính; quyền thao tác tài nguyên vẫn được quyết định bởi các cơ chế phân quyền tương ứng.

Bài học thuộc chương **Danh tính và phân quyền IAM**, tập trung vào OCI IAM với **identity domains**. Những tenancy dùng mô hình IAM cũ có thể có giao diện và cơ chế khác; không áp dụng nguyên các bước của identity domain cho một màn hình Authentication Settings cũ.

## 1. Xác định đúng phạm vi trước khi cấu hình

Trước khi thay đổi chính sách, cần trả lời bốn câu hỏi:

1. Người dùng đang đăng nhập vào tenancy và identity domain nào?
2. Mật khẩu được kiểm tra tại OCI hay tại một identity provider bên ngoài?
3. Ứng dụng đích là OCI Console, My Apps hay một ứng dụng liên kết?
4. Phiên hoặc credential cần kiểm soát thuộc trình duyệt, identity provider hay API?

### 1.1. Các loại chính sách có trách nhiệm khác nhau

| Thành phần | Trách nhiệm chính | Không tự thực hiện |
| --- | --- | --- |
| Password policy | Quy tắc mật khẩu và một số hành vi khóa tài khoản khi đăng nhập sai | Cấp quyền tạo Compute hoặc đọc bucket |
| MFA settings | Các phương thức xác minh được phép dùng trong domain | Bảo đảm mọi đường đăng nhập đều đã bắt buộc MFA |
| Sign-on policy | Điều kiện cho phép đăng nhập, yêu cầu xác thực bổ sung và phạm vi ứng dụng | Thay thế IAM policy cấp quyền tài nguyên |
| Session settings | Thời lượng phiên và các tùy chọn duy trì đăng nhập của domain | Đồng loạt đổi thời hạn mọi token và phiên ứng dụng |
| Console session idle timeout | Thời gian không hoạt động trước khi OCI Console đăng xuất | Đổi session timeout của mọi ứng dụng SSO |
| IAM authorization policy | Ai được làm gì với tài nguyên cloud | Đặt độ dài mật khẩu hoặc cấu hình MFA |

Ví dụ, một người hoàn thành MFA vẫn có thể nhận lỗi không được phép đọc Object Storage. Đó có thể là lỗi phân quyền, không phải bằng chứng MFA chưa hoạt động.

### 1.2. Local user và federated user

**Local user** xác thực bằng thông tin do identity domain quản lý. Password policy của domain có ý nghĩa trực tiếp đối với mật khẩu này.

**Federated user** được chuyển sang identity provider (IdP), chẳng hạn hệ thống danh tính doanh nghiệp, để xác thực. Nếu mật khẩu được kiểm tra ở IdP thì thay đổi password policy tại OCI không tự thay đổi chính sách mật khẩu của IdP.

Với federation, cần xác định nơi thực hiện MFA, cách cấu hình đường đăng nhập liên kết và những đường đăng nhập trực tiếp còn tồn tại. Không mặc định rằng việc có SSO đồng nghĩa mọi người đã dùng MFA, hoặc rằng OCI luôn phải hỏi thêm MFA sau IdP. Tổng quan các mô hình được Oracle trình bày trong [IAM MFA](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-IAM_MFA.htm).

## 2. Chính sách mật khẩu trong identity domain

Password policy quyết định những điều kiện mà mật khẩu phải đáp ứng khi được thiết lập hoặc thay đổi. Khi quản trị, cần kiểm tra cả policy, nhóm được gán và priority, thay vì chỉ nhìn một bảng tiêu chí.

### 2.1. Các nhóm thiết lập thường gặp

| Thiết lập | Ý nghĩa | Điểm cần cân nhắc |
| --- | --- | --- |
| Độ dài tối thiểu và tối đa | Giới hạn chiều dài mật khẩu | Cho phép mật khẩu dài và tương thích trình quản lý mật khẩu |
| Yêu cầu ký tự | Số lượng chữ, số, ký tự đặc biệt hoặc ký tự khác nhau | Quá nhiều ràng buộc dễ dẫn đến mẫu mật khẩu dễ đoán |
| Giá trị không được chứa | Hạn chế thông tin cá nhân hoặc chuỗi không phù hợp theo tùy chọn được hỗ trợ | Kiểm tra khả năng thực tế của loại policy |
| Password history | Hạn chế sử dụng lại mật khẩu trước đó | Không ngăn được việc dùng cùng mật khẩu trên dịch vụ khác |
| Password expiration | Thời hạn hiệu lực của mật khẩu | Phải phù hợp yêu cầu tổ chức và quy trình thay đổi |
| Account lock threshold | Số lần nhập sai liên tiếp dẫn đến khóa | Cân bằng chống dò mật khẩu với nguy cơ người dùng bị khóa |
| Automatic account unlock | Tự mở khóa sau thời gian cấu hình | Không đồng nghĩa nguyên nhân đăng nhập sai đã được xử lý |

OCI identity domains có các lựa chọn như Simple, Standard và Custom. Custom cho phép điều chỉnh tiêu chí; Simple và Standard dùng bộ tiêu chí của loại policy đó. Oracle mô tả các trường và quan hệ giữa group với policy trong [Creating a Password Policy](https://docs.oracle.com/en-us/iaas/Content/Identity/passwordpolicies/Managing-Password-Policies_set-password-policies-your-identity-domain.htm).

Không coi một bộ giá trị lấy từ ảnh minh họa là mặc định của mọi tenancy. Domain có thể đã được tùy chỉnh, di chuyển từ hệ thống cũ hoặc có các nhóm áp dụng chính sách khác nhau.

### 2.2. Chọn mật khẩu và thời hạn sử dụng

Mật khẩu nên dài, riêng cho tài khoản và được quản lý bằng công cụ phù hợp. Tránh tên công ty, tên người dùng, ngày sinh hoặc việc chỉ thay số cuối trong một mẫu quen thuộc.

Password expiration và việc đổi mật khẩu khi có sự cố là hai vấn đề khác nhau:

- Expiration là yêu cầu thay mật khẩu theo thời gian cấu hình.
- Khi nghi mật khẩu đã lộ, cần xử lý ngay theo quy trình sự cố, kể cả mật khẩu chưa hết hạn.
- Đổi mật khẩu không thay thế việc xem xét phiên còn hoạt động, factor MFA và credential API.

Trong identity domains, giá trị `0` ở trường hết hạn có thể có nghĩa là mật khẩu không tự hết hạn. Đây là ý nghĩa cấu hình, không phải khuyến nghị áp dụng đại trà. Nếu tổ chức có yêu cầu về vòng đời mật khẩu, phải thể hiện rõ yêu cầu đó trong thiết kế.

### 2.3. Khóa tài khoản không phải là vô hiệu hóa tài khoản

Tài khoản bị khóa vì nhập sai có thể được mở theo thời gian hoặc bởi người có quyền phù hợp. Tài khoản bị vô hiệu hóa vì nghỉ việc hoặc sự cố là một trạng thái quản trị khác.

Ví dụ, nếu ngưỡng khóa được đặt là năm lần sai liên tiếp, người dùng nhập sai nhiều lần có thể bị khóa dù mật khẩu chưa hết hạn. Đặt ngưỡng quá thấp còn có thể tạo điều kiện cho kẻ khác cố tình làm gián đoạn đăng nhập.

Cần phân biệt ba bộ đếm nếu domain có cấu hình tương ứng:

- Đăng nhập sai mật khẩu.
- Xác minh MFA thất bại.
- Khôi phục tài khoản thất bại.

Mở khóa vì nhập sai mật khẩu không nhất thiết giải quyết một cơ chế khóa khác.

### 2.4. Priority quyết định policy có hiệu lực

Một người có thể thuộc nhiều group. Trong mô hình password policies của identity domain, policy có priority cao nhất trong các policy gắn với những group liên quan sẽ được áp dụng; không tự động cộng mọi tiêu chí thành một policy mạnh nhất.

Ví dụ thiết kế:

| Group | Policy | Priority minh họa |
| --- | --- | --- |
| `oci-security-lab-users` | `lab-password-policy` | 2 |
| `oci-project-users` | `project-password-policy` | 5 |

Nếu người dùng thuộc cả hai nhóm, policy ở priority 2 được ưu tiên hơn priority 5. Trong giao diện này, số nhỏ hơn thể hiện mức ưu tiên cao hơn.

Hệ quả là việc thêm người dùng vào một group cũng có thể thay đổi yêu cầu mật khẩu có hiệu lực. Khi điều tra sự khác biệt giữa hai tài khoản, kiểm tra membership và priority trước khi kết luận hệ thống áp dụng sai.

Không giả định rằng đổi tiêu chí lập tức làm mọi người bị đăng xuất hoặc buộc toàn bộ mật khẩu hiện hữu được nhập lại. Hãy kiểm tra hành vi reset, yêu cầu đổi mật khẩu và thời điểm policy được đánh giá trong luồng cụ thể.

## 3. MFA: phương thức, đăng ký và bắt buộc sử dụng

MFA sử dụng nhiều yếu tố để tăng mức tin cậy vào danh tính người đăng nhập. Mật khẩu và một câu hỏi bí mật đều dựa trên điều người dùng biết; không nên coi việc thêm bất kỳ màn hình nào cũng đem lại mức bảo vệ tương đương một thiết bị xác thực độc lập.

### 3.1. Những phương thức thường gặp

| Phương thức | Cách sử dụng | Điều cần hiểu |
| --- | --- | --- |
| Mobile app passcode, thường là TOTP | Nhập mã do ứng dụng xác thực tạo | Có thể tạo mã khi điện thoại không có mạng; đồng hồ phải chính xác |
| Mobile app notification | Xác nhận yêu cầu trên ứng dụng di động | Chỉ chấp thuận yêu cầu do chính mình khởi tạo |
| FIDO authenticator | Sử dụng khóa bảo mật hoặc authenticator tương thích trên thiết bị | Cần thiết bị và trình duyệt phù hợp; chuẩn bị phương án thay thiết bị |
| Email hoặc SMS, nếu được cho phép | Nhận và nhập mã xác minh | Mức bảo vệ phụ thuộc cả email, số điện thoại và kênh khôi phục |
| Bypass code | Dùng mã dự phòng theo phạm vi được cấu hình | Là thông tin nhạy cảm, không phải cách bỏ MFA vĩnh viễn |

Các phương thức thực sự hiển thị phụ thuộc cấu hình của domain, sign-on rule và khả năng được hỗ trợ. Không mặc định rằng tất cả phương thức trong bảng đều được cho phép cho OCI Console.

Oracle mô tả các phương thức và cách người dùng quản lý chúng trong [Managing 2-Step Verification](https://docs.oracle.com/en-us/iaas/Content/Identity/mfa/manage-2-step-verification.htm).

Với tài khoản quản trị, nên ưu tiên cơ chế mạnh được tổ chức hỗ trợ, chẳng hạn FIDO khi phù hợp. Mã OTP có thể bị nhập vào một trang giả mạo và chuyển tiếp; một thông báo push cũng có thể bị người dùng chấp thuận nhầm. Vì vậy, đào tạo người dùng vẫn là một phần của thiết kế MFA.

### 3.2. Ba trạng thái không được đánh đồng

```text
Domain cho phép một factor
            ↓
Người dùng đăng ký và xác minh factor
            ↓
Sign-on policy yêu cầu factor trong đường truy cập tương ứng
```

Bật phương thức TOTP trong domain không chứng minh mọi người đã đăng ký. Người dùng đã đăng ký cũng không chứng minh mọi ứng dụng đang bắt buộc sử dụng phương thức đó.

Ngược lại, bắt buộc một factor mà người dùng chưa có khả năng đăng ký hoặc sử dụng sẽ gây gián đoạn. Phải thiết kế luồng enrollment và recovery trước khi mở rộng phạm vi áp dụng.

### 3.3. Tránh nhầm MFA settings với sign-on policy

MFA settings quyết định các factor và các tùy chọn liên quan. Sign-on policy quyết định khi nào cho phép truy cập, khi nào yêu cầu factor bổ sung, áp dụng cho ai và cho ứng dụng nào.

Những điểm cần đọc trong một sign-on rule gồm:

- Điều kiện user hoặc group.
- Ứng dụng và đường xác thực mà policy đang bảo vệ.
- Điều kiện mạng hoặc ngữ cảnh khác nếu có.
- Allow hay deny.
- Có yêu cầu factor bổ sung không.
- Enrollment là bắt buộc hay tùy chọn.
- Factor được yêu cầu và tần suất xác minh.
- Điều kiện loại trừ và thứ tự ưu tiên.

Oracle hướng dẫn phối hợp hai phần trong [Configuring Multifactor Authentication Settings](https://docs.oracle.com/en-us/iaas/Content/Identity/mfa/configure-multi-factor-authentication-settings.htm).

## 4. Sign-on policy và thứ tự đánh giá rule

### 4.1. Policy gắn với ứng dụng

Một ứng dụng có thể được gắn với sign-on policy riêng; nếu không có policy riêng phù hợp thì cần xem hành vi của Default Sign-On Policy. Vì vậy, việc chỉnh rule mặc định chưa chắc thay đổi luồng vào OCI Console nếu Console đã được gắn với policy riêng.

Trước khi sửa, xác định application assignment và rule đang có hiệu lực. Oracle mô tả quan hệ ứng dụng, policy và điều kiện đăng nhập trong [Managing Sign-On Policies](https://docs.oracle.com/en-us/iaas/Content/Identity/signonpolicies/managingsignonpolicies.htm).

### 4.2. Rule rộng đặt trước có thể che rule cần thiết

Bảng dưới là mô hình thiết kế để phân tích thứ tự, không phải câu lệnh OCI IAM policy:

| Thứ tự minh họa | Điều kiện | Hành động dự kiến |
| --- | --- | --- |
| 1 | Truy cập từ phạm vi mạng bị chặn đã xác định | Deny |
| 2 | Nhóm quản trị được chọn | Allow sau khi đáp ứng MFA theo yêu cầu |
| 3 | Nhóm người dùng ứng dụng được chọn | Allow với yêu cầu MFA của ứng dụng |
| 4 | Trường hợp còn lại | Xử lý theo rule nền đã được phê duyệt |

Rule được đánh giá theo priority. Một rule cho phép rất rộng nằm trước rule yêu cầu MFA cho quản trị viên có thể khiến luồng thực tế khác thiết kế mong muốn.

Đừng chỉ đọc riêng nội dung rule “MFA cho quản trị viên”; cần đọc cả những rule đứng trước nó. Cách thay đổi thứ tự được mô tả trong [Changing the Priority of a Rule for a Sign-On Policy](https://docs.oracle.com/en-us/iaas/Content/Identity/signonpolicies/change-priority-sign-rule-policy.htm).

### 4.3. Security Policy for OCI Console

Một domain có thể đã có **Security Policy for OCI Console**, gồm các rule MFA được chuẩn bị sẵn cho quản trị viên và người dùng. Nếu đã có policy này, bắt đầu bằng việc kiểm tra trạng thái, ứng dụng được gắn và rule thực tế.

Không tạo một đường đăng nhập yếu hơn chỉ để bài lab xuất hiện màn hình giống hướng dẫn cũ. Cũng không hạ yêu cầu MFA có sẵn chỉ vì nhóm thử nghiệm chưa đăng ký factor. Oracle mô tả policy này và việc bảo vệ khả năng khôi phục quản trị trong [Identity Domains With the Security Policy for OCI Console](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-iam_mfa_identity_domains_signon_policy.htm).

My Profile và My Apps cũng có thể áp dụng bảo vệ MFA mặc định riêng. Vì vậy, việc bị hỏi lại MFA khi vào trang quản lý bảo mật không tự chứng minh phiên Console bị lỗi. Xem [Default MFA Security for Identity Domains My Profile and My Apps Pages](https://docs.oracle.com/en-us/iaas/Content/Identity/mfa/default_mfa_access_for_identity_domains_my_profile.htm).

## 5. Quản lý phiên: nhiều đồng hồ cùng tồn tại

Sau khi xác thực, trình duyệt thường sử dụng cookie hoặc trạng thái phiên để tiếp tục truy cập. Nếu phải nhập mật khẩu cho mọi thao tác thì trải nghiệm rất bất tiện; nếu giữ phiên quá lâu thì phiên bị đánh cắp có giá trị sử dụng lâu hơn.

### 5.1. Các loại thời hạn

| Loại | Được tính theo gì? | Hệ quả khi hết hạn |
| --- | --- | --- |
| Session duration của identity domain | Thời gian từ lúc phiên được thiết lập | Phiên domain hết hiệu lực dù vẫn có hoạt động |
| Idle timeout của OCI Console | Thời gian không hoạt động theo cơ chế Console | Console yêu cầu thiết lập lại truy cập |
| My Apps idle timeout | Không hoạt động trong My Apps theo cấu hình tương ứng | Ảnh hưởng phạm vi My Apps |
| Thời hạn phiên tại IdP ngoài | Quy tắc của IdP | Có thể yêu cầu xác thực lại tại IdP |
| Phiên ứng dụng hoặc OAuth token | Cấu hình và cơ chế của ứng dụng hoặc token | Cần xử lý theo giao thức và ứng dụng đó |

**Session duration** và **idle timeout** không thay thế nhau. OCI công bố session duration của identity domain là thời hạn không phụ thuộc người dùng đang hoạt động hay không trong [Setting Session Limits](https://docs.oracle.com/en-us/iaas/Content/Identity/sessionsettings/session-limits.htm).

### 5.2. Ví dụ phân biệt thời hạn tối đa và không hoạt động

Giả sử trong môi trường thử nghiệm:

- Session duration của domain là 120 phút.
- Console idle timeout là 15 phút.
- Không bật Keep me signed in.
- Không có hành vi gia hạn khác làm thay đổi tình huống minh họa.

Người dùng đăng nhập lúc 09:00:

| Diễn biến | Điều kiện hết hạn cần xem xét |
| --- | --- |
| Có hoạt động đều từ 09:00 đến gần 11:00 | Phiên domain vẫn đến giới hạn 120 phút |
| Hoạt động lần cuối lúc 09:20 rồi để yên | Console có thể kết thúc phiên truy cập sau khoảng 15 phút không hoạt động |
| Quay lại sau khi Console hết thời gian chờ | Có thể được chuyển qua luồng SSO để thiết lập lại truy cập |

Phép tính 09:20 cộng 15 phút cho thấy ý nghĩa của idle timeout, không phải cam kết mọi tab sẽ đổi màn hình đúng 09:35. Việc phát hiện hết hạn và yêu cầu lại thông tin xác thực còn phụ thuộc request tiếp theo, trạng thái SSO và sign-on rule.

Phiên Console kết thúc cũng không luôn đồng nghĩa người dùng phải gõ lại mật khẩu ngay: IdP hoặc phiên SSO hợp lệ có thể tham gia luồng đăng nhập lại. Muốn yêu cầu xác thực mới hoặc MFA lại, phải xem cả sign-on policy và IdP.

### 5.3. OCI Console có thiết lập idle timeout riêng

Theo tài liệu Oracle, có thể mở Profile menu, chọn Console settings và cấu hình Session idle timeout. Đây là thiết lập ở phạm vi tenancy; quyền thay đổi cũng khác việc chỉ sửa một tài khoản cá nhân.

Không dùng trường My Apps idle timeout làm bằng chứng đã đổi thời gian chờ của OCI Console. Các bước và phạm vi quyền được mô tả trong [Changing the Session Time-Out](https://docs.oracle.com/en-us/iaas/Content/GSG/Concepts/console_topic-session-timeout.htm).

### 5.4. Keep me signed in khác trusted device

**Keep me signed in** hỗ trợ duy trì trạng thái đăng nhập theo cấu hình domain. **Trusted device** liên quan việc ghi nhớ thiết bị và yêu cầu factor bổ sung trong những điều kiện được cho phép.

Hai cơ chế này không đồng nghĩa và không thay thế password policy. Chúng cũng không nên được sử dụng trên máy dùng chung chỉ vì việc nhập MFA gây bất tiện.

Khi bật duy trì đăng nhập, phải xem thời hạn, yêu cầu xác thực lại và các sign-on rule. Chính sách đăng nhập vẫn có thể buộc người dùng xác minh lại. Oracle mô tả các tùy chọn trong [Changing Data Sharing Settings](https://docs.oracle.com/en-us/iaas/Content/Identity/sessionsettings/data-sharing-settings.htm).

### 5.5. Đóng tab, đăng xuất và thu hồi phiên

Đóng tab không phải thao tác đăng xuất. Đóng trình duyệt cũng không bảo đảm mọi cookie tồn tại lâu dài đã bị xóa.

Đăng xuất khỏi một ứng dụng không bảo đảm mọi phiên tại IdP, domain và ứng dụng khác cùng kết thúc. Trong federation, phải kiểm tra cơ chế logout được cấu hình giữa các bên.

Xóa cookie tại một máy chỉ xử lý trạng thái phía máy đó; nó không phải bằng chứng mọi bản sao credential hoặc phiên ở thiết bị khác đã bị vô hiệu hóa.

## 6. Recovery và khả năng tiếp tục quản trị

MFA mạnh nhưng thiếu phương án khôi phục có thể khiến tổ chức không vào được hệ thống khi mất điện thoại, hỏng khóa bảo mật hoặc cấu hình sai policy.

### 6.1. Thiết kế recovery như một phần của bảo mật

Cần chuẩn bị:

- Factor dự phòng nếu policy và thiết bị cho phép.
- Kênh recovery còn hoạt động và được bảo vệ.
- Quy trình xác minh người yêu cầu hỗ trợ.
- Người có quyền mở khóa, reset factor và xử lý sự cố đăng nhập.
- Đường quản trị dự phòng được kiểm tra trước khi mở rộng enforcement.

Một email khôi phục không được bảo vệ có thể trở thành điểm yếu dù tài khoản OCI dùng MFA mạnh. Quy trình help desk cũng không nên cấp mã dự phòng chỉ dựa vào tên hiển thị hoặc một tin nhắn không xác minh.

Các cơ chế account recovery được cấu hình riêng với việc đăng ký factor đăng nhập; Oracle mô tả phạm vi này trong [Managing Account Recovery](https://docs.oracle.com/en-us/iaas/Content/Identity/accountrecovery/understand-account-recovery.htm).

### 6.2. Quản trị dự phòng

Trong hướng dẫn MFA, Oracle yêu cầu chuẩn bị khả năng truy cập dự phòng và có hướng dẫn loại trừ ít nhất một quản trị viên khỏi những rule liên quan để tránh mất toàn bộ khả năng quản trị. Nếu dùng cơ chế này, phải quản lý như tài khoản khẩn cấp chuyên trách: hạn chế sử dụng, bảo vệ credential, theo dõi truy cập và định kỳ kiểm tra.

Một phương án khác trong tài liệu triển khai là chuẩn bị client quản trị qua REST API trước khi cấu hình có khả năng chặn mọi đăng nhập. Client có quyền cao là một danh tính nhạy cảm cần được quản lý tương ứng.

Giữ một tab quản trị đang mở hữu ích khi thử nghiệm, nhưng không thay thế đường recovery: phiên đó vẫn có thể hết hạn.

### 6.3. Bypass code và reset factor

Bypass code là thông tin dự phòng có thể cho phép hoàn thành bước xác minh. Không gửi mã vào nhóm chat, log hoặc tài liệu dùng chung.

Phân biệt mã người dùng tự tạo với mã do quản trị viên cấp. Với mã do quản trị viên tạo, OCI cho phép cấu hình thời hạn và số lần dùng; khi cấp hỗ trợ tạm thời, lựa chọn thời hạn ngắn và số lần sử dụng phù hợp giúp giới hạn tác động. Chi tiết ở [Generating a Bypass Code for a User](https://docs.oracle.com/en-us/iaas/Content/Identity/users/generate-bypass-codes-user-accounts.htm).

Reset factor không phải đổi mật khẩu, và đổi mật khẩu không phải xóa mọi factor đã đăng ký. Khi nghi thiết bị MFA bị mất kiểm soát, cần xem các factor cũ, đăng ký lại bằng thiết bị tin cậy và xử lý phiên liên quan.

## 7. Thực hành có kiểm soát trong môi trường riêng

Mục tiêu thực hành là quan sát từng lớp chính sách và chứng minh đường đăng nhập thực tế. Các bước dưới đây thực hiện trên **identity domain thử nghiệm**; những thay đổi cấp tenancy, như Console idle timeout, cần một tenancy thực hành riêng hoặc chỉ được quan sát ở giá trị đang có nếu dùng chung.

### 7.1. Chuẩn bị đối tượng và quyền

Chuẩn bị:

1. Một quản trị viên được giao quyền quản lý thiết lập bảo mật cần thiết.
2. Một tài khoản local user thử nghiệm, không dùng tài khoản quản trị làm đối tượng kiểm tra lỗi.
3. Group `oci-security-lab-users`, chỉ chứa người dùng thử nghiệm.
4. Ứng dụng đích và đường đăng nhập được xác định rõ.
5. Một thiết bị hoặc ứng dụng MFA tương thích, cùng đường recovery đã sẵn sàng.
6. Một browser profile riêng cho người dùng thử nghiệm.

Quyền quản lý thiết lập domain và quyền thay Console settings cấp tenancy phải được xác định riêng. Không gán quyền quản trị toàn tenancy cho người dùng thử nghiệm chỉ để họ kiểm tra đăng nhập.

Trước khi sửa, ghi nhận policy hiện tại, assignment, rule priority, trạng thái MFA và session settings. Không lưu mật khẩu, QR enrollment hoặc bypass code vào bằng chứng thực hành.

### 7.2. Tạo hoặc kiểm tra password policy cho group thử nghiệm

Có thể sử dụng bộ giá trị minh họa sau trong môi trường riêng:

| Tham số | Giá trị minh họa |
| --- | --- |
| Độ dài tối thiểu | 16 ký tự |
| Độ dài tối đa | 128 ký tự |
| Số mật khẩu trước được ghi nhớ | 5 |
| Ngưỡng khóa do nhập sai | 5 lần liên tiếp |
| Tự mở khóa | Sau 15 phút |
| Hết hạn mật khẩu | Theo yêu cầu đã chọn cho môi trường thử nghiệm |

Đây là dữ liệu thực hành, không phải mặc định OCI hay một chuẩn áp dụng cho mọi tổ chức. Nếu cấu hình hiện tại mạnh hơn, không hạ yêu cầu chỉ để khớp bảng.

Trong Password policies của domain:

1. Tạo policy Custom hoặc chọn policy thử nghiệm đã chuẩn bị.
2. Gắn group `oci-security-lab-users`.
3. Kiểm tra priority so với các policy khác của những group mà user đang thuộc.
4. Lưu thay đổi.
5. Trong browser profile của user thử nghiệm, mở luồng đổi mật khẩu.
6. Kiểm tra một mật khẩu không đủ chiều dài bị từ chối; sau đó đặt mật khẩu riêng đáp ứng đầy đủ tiêu chí.

Không cần công bố mật khẩu mẫu có thể sao chép. Hãy tự tạo mật khẩu bằng công cụ thích hợp và chỉ ghi nhận việc tiêu chí được chấp nhận hay từ chối.

Không thử nhập sai liên tục trên tài khoản quản trị. Việc kiểm tra lockout, nếu cần, chỉ thực hiện trên tài khoản lab đã có phương án mở khóa và số lần thử được kiểm soát.

### 7.3. Đăng ký và kiểm tra MFA

Trước hết kiểm tra policy MFA đang bảo vệ ứng dụng đích. Nếu OCI Console đã yêu cầu MFA, sử dụng chính yêu cầu hiện hữu; không tắt rồi bật lại để mô phỏng enrollment.

Trong domain thử nghiệm:

1. Quản trị viên xác nhận các factor được phép.
2. Người dùng đăng ký factor trong luồng đăng nhập hoặc My Profile theo giao diện.
3. Hoàn tất bước xác minh factor.
4. Chuẩn bị recovery phù hợp.
5. Xác nhận rule áp dụng cho người dùng và ứng dụng đang yêu cầu MFA.
6. Đăng xuất rồi mở phiên trình duyệt thử nghiệm mới, tránh dùng trạng thái SSO cũ.
7. Đăng nhập đúng đường và quan sát việc yêu cầu factor.

Nếu có QR enrollment, đó là dữ liệu thiết lập bí mật: không chụp đưa vào báo cáo công khai. Sau khi hoàn tất, chỉ lưu bằng chứng về phương thức và trạng thái đăng ký.

Hướng dẫn phía người dùng có trong [Setting Up Account Recovery and 2-Step Verification](https://docs.oracle.com/en-us/iaas/Content/Identity/usersettings/manage_security_and_2_step_verification.htm).

### 7.4. Kiểm tra phiên đăng nhập

Trong môi trường riêng, ví dụ đặt session duration của domain là 30 phút. Nếu tenancy thực hành cho phép thay idle timeout, có thể dùng Console idle timeout 5 phút để dễ quan sát; nếu tenancy dùng chung, chỉ ghi nhận giá trị hiện tại.

Chạy hai tình huống độc lập:

| Tình huống | Cách thực hiện | Điều cần ghi nhận |
| --- | --- | --- |
| Không hoạt động | Đăng nhập, ghi giờ, để yên đủ thời gian rồi gửi thao tác mới | Console có yêu cầu đăng nhập lại không, luồng SSO tiếp theo là gì |
| Có hoạt động | Đăng nhập bằng phiên mới, thao tác định kỳ đến quá session duration | Phiên domain hết hạn và hệ thống thiết lập lại xác thực như thế nào |

Ghi lại giờ đăng nhập, giờ thao tác cuối, giờ nhận yêu cầu lại, policy được áp dụng và trạng thái Keep me signed in. Nếu dùng federation, ghi cả việc IdP còn phiên hay không.

Không kết luận “MFA bị bỏ qua” chỉ vì không thấy trang mật khẩu. Phải xác định kết quả xác thực nào được tái sử dụng và rule có yêu cầu factor mới cho tình huống đó không.

### 7.5. Tiêu chí hoàn thành thực hành

| Kiểm tra | Bằng chứng cần có |
| --- | --- |
| Đúng domain và local user | Ghi nhận danh tính cùng đường đăng nhập |
| Password policy có hiệu lực | Mật khẩu sai tiêu chí bị từ chối, mật khẩu hợp lệ được chấp nhận |
| MFA enrollment hoàn tất | Factor được xác minh và có recovery |
| MFA enforcement đúng phạm vi | Phiên đăng nhập mới vào ứng dụng đích đi qua yêu cầu tương ứng |
| Idle timeout được hiểu đúng | Có giờ thao tác cuối và giờ quan sát yêu cầu lại |
| Session duration được hiểu đúng | Phân biệt hết thời gian tối đa với không hoạt động |
| Quản trị dự phòng hoạt động | Có đường recovery đã kiểm tra phù hợp với thiết kế |

Kết thúc bài lab, khôi phục những thiết lập cấp domain hoặc tenancy đã thay đổi theo cấu hình cần giữ. Gỡ user, group và policy thử nghiệm khi không còn dùng; tránh xóa đối tượng đang được ứng dụng khác tham chiếu.

## 8. Chẩn đoán những tình huống thường gặp

| Triệu chứng | Khả năng cần kiểm tra | Hành động có mục tiêu |
| --- | --- | --- |
| User A và B nhận tiêu chí mật khẩu khác nhau | Group, priority, nguồn xác thực khác nhau | Đối chiếu policy có hiệu lực và IdP |
| Mật khẩu đúng nhưng vẫn không vào được | Tài khoản bị khóa, rule deny, MFA hoặc domain sai | Xác định bước thất bại và trạng thái tài khoản |
| Đăng ký MFA rồi nhưng ứng dụng không hỏi | Policy không gắn đúng ứng dụng, rule khác được áp dụng, phiên hoặc thiết bị được nhớ | Kiểm tra assignment, priority và một phiên mới |
| Không thấy factor mong muốn | Domain chưa cho phép hoặc rule giới hạn factor | Kiểm tra cả MFA settings và rule |
| TOTP liên tục sai | Lệch giờ, nhầm tài khoản trong app, enrollment cũ | Đồng bộ giờ và xác nhận đúng factor |
| Push đến dù người dùng không đăng nhập | Có thể có nỗ lực đăng nhập không do người dùng khởi tạo | Từ chối, ghi nhận và báo theo quy trình sự cố |
| Đổi My Apps timeout nhưng Console không đổi | Cấu hình nhầm lớp | Kiểm tra Console settings riêng |
| Đổi mật khẩu nhưng một công cụ vẫn gọi API được | Công cụ dùng API key, token hoặc danh tính khác | Xác định credential thực tế thay vì thử đổi mật khẩu tiếp |
| Vừa cấu hình MFA thì quản trị viên bị chặn | Rule quá rộng, thứ tự sai hoặc không có factor hợp lệ | Dùng đường recovery đã chuẩn bị, không chỉnh ngẫu nhiên mọi rule |

Một lỗi `NotAuthorized` khi thao tác tài nguyên sau đăng nhập thường cần điều tra IAM policy cấp quyền, không phải hạ yêu cầu MFA.

Nếu gửi thông tin cho người hỗ trợ, cung cấp thời gian, domain, ứng dụng, mã lỗi và định danh sự kiện phù hợp. Không gửi mật khẩu, cookie phiên, OTP, token hoặc QR enrollment.

## 9. Thu hồi truy cập khi nghỉ việc hoặc xảy ra sự cố

Password policy, MFA và session timeout giúp phòng ngừa; chúng không thay thế quy trình thu hồi.

Một trình tự xử lý có thể gồm:

1. Xác định local user hay federated user và phạm vi tài nguyên bị ảnh hưởng.
2. Vô hiệu hóa hoặc hạn chế danh tính theo thẩm quyền để chặn đăng nhập mới.
3. Xem và xử lý các phiên được duy trì, phiên IdP và phiên ứng dụng liên quan.
4. Đổi mật khẩu hoặc khôi phục factor nếu có nguy cơ bị lộ.
5. Rà soát API signing key, auth token, customer secret key và credential khác.
6. Gỡ quyền, membership hoặc application assignment theo nhu cầu.
7. Kiểm tra log để xác định hoạt động trước và sau thời điểm thu hồi.

Với Keep me signed in, người dùng có chức năng xem và xóa các phiên được ghi nhớ; quản trị viên có chức năng tương ứng trong quản lý user theo quyền được cấp. Việc xóa loại phiên này không nên được diễn giải thành thu hồi mọi access token hoặc mọi phiên dịch vụ. Oracle mô tả thao tác phía người dùng trong [Clearing Your Keep Me Signed-In Sessions](https://docs.oracle.com/en-us/iaas/Content/Identity/usersettings/access-your-signed-in-sessions.htm).

Đổi mật khẩu Console không làm một API signing key trở thành khóa mới. MFA cho đăng nhập trình duyệt cũng không tự thêm một bước OTP cho mỗi request được ký bằng API key. Các credential cần có vòng đời và cách thu hồi riêng; xem phạm vi credential trong [IAM Credentials](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-IAM_Credentials.htm).

Đối với workload trên Compute, ưu tiên xem xét danh tính workload phù hợp như Instance Principals thay vì sử dụng tài khoản người dùng có phiên đăng nhập kéo dài để chạy tự động hóa.

## 10. Giám sát và duy trì chính sách

Theo dõi những tín hiệu có ý nghĩa với mô hình triển khai:

- Đăng nhập thất bại tăng bất thường.
- MFA bị từ chối hoặc thất bại nhiều lần.
- Đăng ký, thay đổi hoặc reset factor ngoài dự kiến.
- Tạo bypass code hoặc sử dụng tài khoản khẩn cấp.
- Thay đổi password policy, sign-on rule, assignment hoặc session settings.
- Đăng nhập tiếp tục xảy ra sau thời điểm dự kiến thu hồi truy cập.

Sử dụng báo cáo và log của identity domain, OCI Audit cùng log IdP theo loại sự kiện; không giả định mọi nguồn đều chứa đầy đủ mọi bước xác thực. Các mốc thời gian, danh tính và ứng dụng giúp đối chiếu luồng sự cố.

Khi thay đổi chính sách, đánh giá cả bảo mật lẫn khả năng vận hành: người dùng có factor hợp lệ không, recovery có hoạt động không, ai chịu trách nhiệm hỗ trợ và những ứng dụng nào chịu tác động. Theo dõi nhóm thử nghiệm trước khi mở rộng.

Tài khoản quản trị cần được rà soát thường xuyên về quyền, đường đăng nhập và các ngoại lệ. Với user thường, kiểm tra cả membership vì nó có thể ảnh hưởng password policy và sign-on rule. Với federated user, duy trì trách nhiệm rõ ràng giữa đội quản trị IdP và đội quản trị OCI.

Một thiết kế có thể kiểm chứng phải chỉ ra được: mật khẩu được kiểm tra ở đâu, MFA được yêu cầu ở đường truy cập nào, từng loại phiên hết hạn theo điều kiện gì và cách chấm dứt truy cập khi cần.
