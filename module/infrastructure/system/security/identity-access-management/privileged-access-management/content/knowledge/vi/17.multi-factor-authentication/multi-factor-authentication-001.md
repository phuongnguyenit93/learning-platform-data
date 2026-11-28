# MFA cho PAM portal

## 1. Vì sao cổng PAM cần xác thực đa yếu tố?

PAM portal là điểm vào để người vận hành yêu cầu quyền, mở phiên quản trị, sử dụng credential và thực hiện các thao tác quản lý truy cập đặc quyền. Một tài khoản bị chiếm ở đây có thể tạo ra ảnh hưởng lớn hơn một tài khoản chỉ dùng để đọc thông tin thông thường.

Tùy vai trò được cấp, người dùng portal có thể:

- Yêu cầu hoặc kích hoạt quyền quản trị tạm thời.
- Mở phiên SSH, RDP hoặc phiên quản trị ứng dụng qua PAM.
- Checkout một credential từ vault.
- Phê duyệt yêu cầu truy cập của người khác.
- Thay đổi chính sách, phân công người duyệt hoặc cấu hình ghi nhận phiên.
- Đăng ký yếu tố xác thực mới hoặc khôi phục tài khoản.

**MFA — Multi-Factor Authentication** yêu cầu xác thực dựa trên nhiều loại yếu tố khác nhau. Trong bối cảnh PAM, mục tiêu là giảm khả năng một mật khẩu bị lộ hoặc một yếu tố bị chiếm đoạt riêng lẻ đủ để mở đường đến quyền đặc quyền.

Tuy nhiên, MFA không tự quyết định người dùng được truy cập tài nguyên nào. Một người xác thực thành công vẫn phải qua kiểm tra vai trò, phê duyệt, cửa sổ thời gian và điều kiện cấp quyền. MFA cũng không làm cho một máy trạm đã bị kiểm soát trở thành môi trường an toàn.

Ví dụ, một kỹ sư có thể đăng nhập portal bằng phương thức MFA mạnh nhưng vẫn bị từ chối mở phiên production vì yêu cầu chưa được chủ hệ thống phê duyệt. Ngược lại, một yêu cầu đã được duyệt cũng không cho phép bỏ qua MFA bắt buộc khi kích hoạt.

## 2. Hiểu đúng yếu tố xác thực

### 2.1. Nhiều bước không nhất thiết là nhiều yếu tố

Các nhóm yếu tố thường được diễn giải như sau:

| Nhóm yếu tố | Ý nghĩa | Ví dụ |
|---|---|---|
| Điều người dùng biết | Bí mật được người dùng ghi nhớ | Mật khẩu, PIN trong một cơ chế phù hợp |
| Vật người dùng sở hữu | Thiết bị hoặc khóa mà người dùng kiểm soát | Security key, ứng dụng tạo OTP, authenticator có khóa mật mã |
| Đặc điểm của người dùng | Đặc điểm sinh trắc được cơ chế xác thực sử dụng | Vân tay hoặc nhận diện khuôn mặt trong một authenticator phù hợp |

Mật khẩu cộng câu hỏi bí mật vẫn chủ yếu dựa trên kiến thức, không tạo ra sự độc lập như hai loại yếu tố khác nhau. Nhập cùng một mật khẩu ở hai màn hình cũng không phải MFA.

Vị trí IP, quốc gia, thời gian truy cập và trạng thái thiết bị là tín hiệu ngữ cảnh hữu ích. Chúng không tự trở thành một yếu tố xác thực chỉ vì được đưa vào chính sách rủi ro.

Một thiết bị được quản lý cũng không tự chứng minh rằng người đang thao tác chính là người được cấp quyền. Cần hiểu cơ chế xác thực của thiết bị và người dùng, thay vì đồng nhất “thiết bị đạt chính sách” với “người dùng đã MFA”.

### 2.2. Passwordless có thể là MFA, nhưng cần hiểu cơ chế

Một authenticator có thể kết hợp khóa mật mã do thiết bị kiểm soát với bước xác minh người dùng cục bộ bằng PIN hoặc sinh trắc. Khi được thiết kế, cấu hình và kiểm tra phù hợp, một lần tương tác có thể đáp ứng nhiều yếu tố mà không cần gửi mật khẩu đến portal.

Với passkey hoặc security key, cần phân biệt:

- **User presence:** có một tương tác thể hiện sự hiện diện, chẳng hạn chạm vào khóa.
- **User verification:** authenticator đã thực hiện xác minh người dùng theo cơ chế được hỗ trợ.

Một thao tác chạm không tự đồng nghĩa đã xác minh bằng PIN hoặc sinh trắc. Nếu chính sách yêu cầu user verification, hệ thống phải yêu cầu và kiểm tra kết quả tương ứng, không chỉ dựa vào tên phương thức.

Sinh trắc trong một authenticator thông thường được dùng để mở khóa việc sử dụng khóa cục bộ; portal không cần nhận dữ liệu vân tay để xác thực bằng cơ chế đó.

Việc gọi một phương thức là “passwordless”, “passkey” hoặc “hardware key” chưa đủ để kết luận mức bảo đảm. Cần xem cách khóa được lưu, cách xác minh người dùng, khả năng khôi phục, đồng bộ nếu có và khả năng đáp ứng chính sách của tổ chức.

## 3. Những rủi ro cần xét tại PAM portal

### 3.1. Mật khẩu bị lộ

Mật khẩu có thể bị tái sử dụng, đoán, lấy từ một dịch vụ khác hoặc thu qua trang giả. Một yếu tố bổ sung độc lập giúp giảm nguy cơ dùng riêng mật khẩu để đăng nhập.

MFA không thay thế việc chống dò mật khẩu, bảo vệ mật khẩu lưu trữ, vô hiệu hóa tài khoản không còn sử dụng hoặc giám sát hành vi đăng nhập bất thường.

### 3.2. Phishing và chuyển tiếp mã xác thực

Mã OTP có thể bị người dùng nhập vào một trang giả rồi bị chuyển tiếp đến hệ thống thật khi còn hiệu lực. Phương thức có thêm OTP không mặc nhiên có khả năng chống phishing.

Các cơ chế xác thực mật mã được ràng buộc đúng với dịch vụ nhận xác thực, như một triển khai WebAuthn phù hợp, giúp ngăn việc dùng kết quả xác thực cho một dịch vụ giả mạo khác. Khả năng này vẫn phụ thuộc vào cấu hình đúng và không bảo vệ mọi hành động trên một endpoint đã bị kiểm soát.

Đối với tài khoản có thể quản trị chính sách PAM, mở kho credential nhạy cảm hoặc truy cập production, nên thiết kế chính sách ưu tiên hoặc yêu cầu phương thức chống phishing phù hợp với rủi ro.

### 3.3. MFA fatigue và người dùng duyệt nhầm

Nếu một phương thức gửi thông báo chấp thuận liên tục, người dùng có thể đồng ý để ngừng bị làm phiền hoặc tưởng đó là yêu cầu của chính mình.

Giảm rủi ro bằng cách giới hạn yêu cầu, phát hiện các chuỗi thất bại, hiển thị ngữ cảnh và sử dụng cơ chế xác nhận phù hợp. Number matching có thể giảm một số kiểu duyệt nhầm, nhưng không nên coi mọi hình thức number matching là tương đương với cơ chế xác thực mật mã chống phishing.

Không huấn luyện người dùng chấp thuận thông báo bất ngờ. Một yêu cầu xác thực không do họ khởi tạo cần được từ chối và báo theo quy trình.

### 3.4. Chiếm phiên sau khi MFA đã thành công

Kẻ tấn công có thể không cần thực hiện lại MFA nếu lấy được cookie phiên hoặc token còn hiệu lực. Vì vậy, portal cần kiểm soát vòng đời phiên, bảo vệ token và yêu cầu xác thực lại ở các điểm phù hợp.

Một trang hiển thị biểu tượng “MFA thành công” không có nghĩa mọi thao tác tiếp theo đều an toàn vô thời hạn.

### 3.5. Đường bỏ qua qua API, trang quản trị hoặc tài khoản cục bộ

MFA chỉ trên giao diện web chính không đủ nếu cùng quyền đó có thể được thực hiện bằng một đường đăng nhập khác yếu hơn.

Cần xác định các đường thuộc phạm vi:

- Portal dành cho người vận hành.
- Giao diện quản trị PAM.
- API phục vụ người dùng tương tác.
- CLI hoặc ứng dụng đi kèm.
- Trang đăng ký và khôi phục MFA.
- Đăng nhập cục bộ dùng khi federation gặp sự cố.

Mỗi đường có thể có cơ chế khác nhau, nhưng không được vô tình tạo một đường đến cùng quyền đặc quyền mà bỏ qua mức xác thực bắt buộc.

## 4. Chọn phương thức MFA theo rủi ro

Bảng dưới đây so sánh ở mức khái niệm; khả năng thực tế phụ thuộc vào triển khai và cấu hình.

| Phương thức | Đặc điểm hữu ích | Điểm cần xem xét trong PAM |
|---|---|---|
| Security key hoặc passkey dùng cơ chế chống phishing phù hợp | Xác thực bằng khóa mật mã, có thể ràng buộc với dịch vụ | Kiểm tra user verification, vòng đời khóa, khôi phục và mức bảo đảm yêu cầu |
| Ứng dụng tạo OTP | Dùng được khi không cần nhận mã qua mạng di động | Mã có thể bị chuyển tiếp qua phishing; bảo vệ quá trình đăng ký và secret |
| Push approval | Trải nghiệm thuận tiện | Rủi ro fatigue, duyệt nhầm và cơ chế hiển thị ngữ cảnh |
| SMS OTP | Dễ tiếp cận ở một số môi trường | Rủi ro liên quan số điện thoại, chiếm số và phishing; cần đánh giá trước khi dùng cho đặc quyền |
| Mã khôi phục | Hữu ích khi mất authenticator | Là bí mật có thể dùng để lấy lại truy cập; cần bảo vệ và giới hạn chặt |
| Chứng thư hoặc khóa trên thiết bị | Có thể cung cấp bằng chứng sở hữu khóa | Cần xác định khóa đại diện cho thiết bị, người dùng hay cả hai và cách kết hợp yếu tố còn lại |

Một chính sách mạnh không chỉ xem phương thức đăng nhập chính. Nó phải xem cả đường dự phòng. Nếu người dùng có thể chuyển từ security key sang một cơ chế khôi phục dễ bị lạm dụng mà không kiểm soát bổ sung, mức bảo đảm thực tế có thể bị hạ xuống theo đường đó.

Không đặt cùng một quy tắc cho mọi danh tính mà thiếu phân loại. Người quản trị nền tảng PAM, người phê duyệt quyền production và người chỉ xem trạng thái yêu cầu có thể có mức rủi ro khác nhau. Dù vậy, các quyền đặc quyền cần được xác định rõ để không bị xếp nhầm vào nhóm ít rủi ro.

## 5. Đặt MFA ở đâu trong kiến trúc?

### 5.1. Xác thực trực tiếp và xác thực qua IdP

Portal có thể tự thực hiện xác thực hoặc tin cậy một nhà cung cấp danh tính (Identity Provider — IdP).

Trong mô hình qua IdP:

1. Người dùng bắt đầu đăng nhập portal.
2. Portal chuyển người dùng tới IdP theo giao thức được cấu hình.
3. IdP xác thực theo chính sách, bao gồm MFA khi cần.
4. Portal nhận và kiểm tra bằng chứng xác thực.
5. Portal tạo phiên của chính nó nếu mức xác thực đáp ứng yêu cầu.
6. Mọi quyết định truy cập tiếp theo vẫn được kiểm tra theo chính sách PAM.

Không suy ra rằng “đăng nhập qua SSO” luôn có nghĩa “đã MFA”. Một phiên IdP có thể được thiết lập trước đó bằng phương thức yếu hơn, đã quá lâu hoặc theo chính sách khác.

### 5.2. Portal phải kiểm tra bằng chứng đáng tin cậy

Tùy giao thức, portal cần kiểm tra các thuộc tính bảo mật tương ứng, chẳng hạn:

- Bên phát hành có đúng IdP hoặc tenant được tin cậy không.
- Chữ ký và khóa kiểm chứng có hợp lệ không.
- Bằng chứng có đúng đối tượng nhận và đúng luồng đăng nhập không.
- Thời hạn và các ràng buộc thời gian có hợp lệ không.
- Cơ chế liên kết yêu cầu, chống giả mạo luồng và chống sử dụng lại có được thực hiện không.
- Phương thức hoặc mức xác thực được xác nhận có đáp ứng chính sách không.
- Thời điểm xác thực thực sự có đủ mới không.

Tên claim hoặc cách biểu diễn phụ thuộc giao thức và sản phẩm. Với federation, cần thống nhất ý nghĩa của mức xác thực và dữ liệu phương thức giữa IdP và portal. Không chỉ nhìn thấy một chuỗi có tên “mfa” rồi coi mọi loại xác thực là tương đương.

Thời điểm portal tạo cookie mới cũng không chứng minh người dùng vừa thực hiện lại MFA. Portal có thể vừa tạo phiên từ một phiên SSO đã cũ. Chính sách freshness cần dựa trên bằng chứng thời điểm xác thực phù hợp, không dựa riêng vào lúc mở trang.

### 5.3. Không tin dữ liệu xác thực từ trình duyệt

Những dữ liệu sau không phải bằng chứng đủ:

~~~text
localStorage["mfa_passed"] = true
Một checkbox "đã xác thực" do trình duyệt gửi lên
Một query parameter mfa=true
Một header do client có thể tự thêm
Một trường trong biểu mẫu cho biết thời gian MFA
~~~

Trạng thái xác thực phải được xác lập hoặc kiểm chứng phía máy chủ từ nguồn tin cậy. Nếu dùng proxy để chuyển thông tin xác thực, cần bảo vệ ranh giới tin cậy, loại bỏ header do bên ngoài giả mạo và không cho truy cập vòng qua proxy tới backend.

## 6. Phân biệt MFA đăng nhập với step-up cho thao tác nhạy cảm

### 6.1. Một lần đăng nhập không bao phủ mọi hành động

Một phiên portal có thể tồn tại nhiều giờ. Trong khoảng đó, người dùng có thể chuyển từ đọc yêu cầu sang checkout credential hoặc thay đổi chính sách.

**Step-up authentication** là yêu cầu xác thực bổ sung hoặc mới hơn khi hành động cần mức bảo đảm cao hơn trạng thái hiện có.

Ví dụ các hành động đáng xem xét step-up:

| Hành động | Lý do |
|---|---|
| Checkout credential có thể xem hoặc sao chép | Bí mật có thể được sử dụng ngoài kênh giám sát |
| Mở phiên đặc quyền trên tài nguyên quan trọng | Tác động trực tiếp tới hệ thống nhạy cảm |
| Phê duyệt quyền rủi ro cao | Quyết định có thể cấp đặc quyền cho người khác |
| Thay đổi chính sách MFA hoặc workflow | Có thể làm yếu kiểm soát cho nhiều tài khoản |
| Thêm authenticator mới hoặc khôi phục tài khoản | Có thể thiết lập khả năng truy cập lâu dài |
| Thay đổi cấu hình ghi nhận phiên hoặc vault | Có thể ảnh hưởng bằng chứng và bảo vệ credential |

Step-up không có nghĩa là hỏi MFA trước từng cú nhấp chuột. Cần cân bằng giữa mức bảo đảm, độ mới của xác thực, rủi ro hành động và khả năng vận hành để tránh làm người dùng phản xạ chấp thuận.

### 6.2. Ràng buộc với hành động phía máy chủ

Khi yêu cầu step-up, portal nên xác định rõ người dùng, loại hành động, phạm vi tài nguyên và thời hạn sử dụng kết quả.

Ví dụ, một lần step-up cho “xem credential của tài khoản A” không nên được mặc nhiên dùng để “tắt MFA cho toàn bộ nhóm quản trị”.

Một mô hình triển khai có thể:

1. Tạo yêu cầu hành động phía máy chủ với định danh và phiên bản.
2. Yêu cầu mức xác thực phù hợp.
3. Liên kết kết quả thành công với danh tính, phiên và yêu cầu hành động đó.
4. Kiểm tra lại quyền, phê duyệt và phạm vi trước khi thực thi.
5. Giới hạn thời gian và số lần sử dụng kết quả theo chính sách.

Đây là ràng buộc ở tầng ứng dụng. Việc chỉ sử dụng WebAuthn không tự bảo đảm người dùng đã đọc hoặc phê duyệt toàn bộ nội dung nghiệp vụ của một giao dịch. Không tuyên bố có xác nhận giao dịch đáng tin cậy nếu kiến trúc chưa cung cấp và kiểm chứng khả năng đó.

### 6.3. MFA và phê duyệt là hai điều kiện riêng

Một người có thể vừa thực hiện MFA nhưng không phải người có thẩm quyền phê duyệt. Ngược lại, một người là chủ hệ thống có thể cần MFA mới đủ để thực hiện quyết định nhạy cảm.

Logic nên là:

~~~text
Được thực hiện hành động
    = danh tính hợp lệ
    VÀ mức xác thực phù hợp, còn đủ mới
    VÀ được phép thực hiện loại hành động
    VÀ đủ phê duyệt nếu hành động yêu cầu
    VÀ đúng tài nguyên, thời gian và điều kiện ngữ cảnh
~~~

Không dùng một thành công MFA để thay thế bất kỳ điều kiện cấp quyền nào trong biểu thức.

## 7. Luồng đăng nhập và mở phiên đặc quyền

~~~mermaid
flowchart TD
    A[Người dùng mở PAM portal] --> B[Xác thực tại IdP hoặc bộ xác thực được quản lý]
    B --> C[Portal kiểm tra bằng chứng và mức xác thực]
    C --> D{Đạt chính sách đăng nhập?}
    D -- Không --> E[Từ chối hoặc yêu cầu phương thức phù hợp]
    D -- Có --> F[Tạo phiên portal có giới hạn]
    F --> G[Yêu cầu hành động đặc quyền]
    G --> H[Kiểm tra quyền, phê duyệt, thời gian và rủi ro]
    H --> I{Cần xác thực mới hoặc mạnh hơn?}
    I -- Có --> J[Thực hiện step-up và kiểm tra kết quả]
    J --> K[Đánh giá lại điều kiện trước khi thực thi]
    I -- Không --> K
    K --> L{Mọi điều kiện còn hợp lệ?}
    L -- Không --> M[Từ chối và ghi lý do]
    L -- Có --> N[Cấp lease hoặc phiên đích có thời hạn]
    N --> O[Giám sát, hết hạn và thu hồi]
~~~

Trong luồng này có ít nhất ba vòng đời khác nhau:

- Phiên đăng nhập tại IdP.
- Phiên web của PAM portal.
- Phiên hoặc lease truy cập hệ thống đích.

Đăng xuất một lớp không nhất thiết kết thúc ngay mọi lớp còn lại. Kiến trúc phải quy định cách truyền tín hiệu hủy và cách thu hồi phiên đích. Đặc biệt, đã khóa tài khoản portal không có nghĩa credential từng checkout tự biến mất khỏi hệ thống đích.

Nếu portal dùng token cho API, token đó có thời hạn, phạm vi và cơ chế thu hồi riêng. Một bearer token bị lấy cắp có thể được sử dụng trong phạm vi của nó cho đến khi hết hạn hoặc bị chặn theo cơ chế thực thi. Không nên coi bước MFA khi phát hành token là bảo vệ đầy đủ cho mọi lần sử dụng token về sau.

## 8. Quản lý phiên sau khi MFA thành công

### 8.1. Giới hạn phiên và freshness

Cần phân biệt:

| Giới hạn | Điều được kiểm soát |
|---|---|
| Thời lượng phiên tuyệt đối | Phiên portal tồn tại tối đa bao lâu |
| Idle timeout | Phiên không hoạt động bao lâu thì hết |
| Tuổi của bằng chứng xác thực | Lần xác thực phù hợp đã xảy ra cách đây bao lâu |
| Hạn sử dụng kết quả step-up | Kết quả có thể hỗ trợ hành động trong khoảng nào |
| Thời hạn quyền trên đích | Quyền đặc quyền thực sự tồn tại đến khi nào |

Hoạt động liên tục có thể tránh idle timeout nhưng không được tự kéo dài thời lượng tuyệt đối hoặc làm mới tuổi MFA.

Các thời lượng phải được lựa chọn theo rủi ro. Chẳng hạn, một tổ chức có thể cho phiên portal tồn tại vài giờ nhưng yêu cầu xác thực rất gần thời điểm checkout một credential quan trọng. Đó là một lựa chọn chính sách, không phải giá trị chuẩn cho mọi PAM.

### 8.2. Bảo vệ cookie và token

Với phiên trình duyệt, cần bảo vệ đường truyền và cấu hình cookie phù hợp, bao gồm các thuộc tính như Secure, HttpOnly và SameSite khi áp dụng. Cấu hình phải được kiểm thử với luồng federation thực tế; một thuộc tính cookie không thay thế kiểm soát giả mạo yêu cầu.

Các điểm thiết kế khác gồm:

- Không đặt token hoặc thông tin phiên trong URL dễ bị ghi vào lịch sử và log.
- Không ghi credential, OTP, recovery code hoặc token có thể dùng lại vào log.
- Bảo vệ thao tác thay đổi trạng thái khỏi CSRF theo kiến trúc ứng dụng.
- Đổi định danh phiên khi chuyển từ chưa xác thực sang đã xác thực và khi cần để chống session fixation.
- Hạn chế lưu bí mật phía trình duyệt và phòng ngừa việc mã độc trong ứng dụng đọc chúng.
- Thu hồi hoặc giới hạn các phiên liên quan khi xảy ra sự kiện tài khoản nghiêm trọng.

HttpOnly giảm khả năng JavaScript đọc cookie, nhưng không ngăn hoàn toàn một mã độc đang chạy trong trang thực hiện hành động bằng phiên của người dùng. Bảo vệ ứng dụng và endpoint vẫn cần thiết.

### 8.3. Tín hiệu rủi ro và thu hồi

Khi phát hiện mất authenticator, tài khoản bị chiếm hoặc thiết bị không còn đáng tin cậy, tổ chức có thể cần:

- Chặn đăng nhập mới.
- Hủy phiên portal và token liên quan.
- Thu hồi quyền JIT hoặc lease đang hoạt động theo chính sách.
- Xử lý credential đã được cấp và khả năng truy cập trực tiếp.
- Kiểm tra phiên đích còn tồn tại.
- Lưu bằng chứng và thông báo cho người chịu trách nhiệm.

Không khẳng định thu hồi tức thì nếu các thành phần chỉ cập nhật trạng thái theo chu kỳ. Cần xác định độ trễ thực thi, giám sát thất bại và kiểm chứng trạng thái trên các điểm kiểm soát.

## 9. Vòng đời authenticator: đăng ký, thay đổi và khôi phục

### 9.1. Đăng ký ban đầu là một bước thiết lập quyền

Nếu một người chỉ cần biết mật khẩu là có thể đăng ký authenticator đầu tiên cho tài khoản quản trị, kẻ đã lấy mật khẩu có thể tự thiết lập yếu tố thứ hai của mình.

Quy trình đăng ký ban đầu cần có cơ chế xác minh danh tính và phân phối quyền khởi tạo phù hợp, chẳng hạn một bước onboarding được kiểm soát. Không chỉ thiết kế màn hình đăng nhập mà bỏ qua cách tài khoản được gắn với authenticator.

Nên lưu định danh authenticator, ngày đăng ký, trạng thái và thông tin cần thiết để quản lý. Không lưu dữ liệu nhạy cảm vượt nhu cầu; đối với khóa công khai, portal hoặc IdP không cần giữ private key của người dùng.

### 9.2. Thêm hoặc thay authenticator

Đây là hành động nhạy cảm vì có thể tạo một con đường truy cập mới. Quy trình nên:

- Yêu cầu xác thực phù hợp bằng một cơ chế còn đáng tin cậy hoặc đi qua tuyến khôi phục riêng.
- Hiển thị rõ hành động đang thực hiện.
- Thông báo qua kênh đã đăng ký đáng tin cậy theo chính sách.
- Cho phép người dùng và đội hỗ trợ phát hiện đăng ký bất thường.
- Ghi lại danh tính người thao tác và kết quả.
- Thu hồi authenticator cũ khi bị mất hoặc bị nghi chiếm đoạt.
- Đánh giá việc hủy các phiên và token liên quan.

Không để một phiên portal cũ, không còn đủ mức bảo đảm, tự thêm yếu tố mới rồi tiếp tục thao tác đặc quyền.

### 9.3. Khôi phục không được là cửa sau

Mất điện thoại hoặc security key là tình huống vận hành bình thường và cần quy trình từ trước.

Các nguyên tắc quan trọng:

- Xác minh người yêu cầu khôi phục bằng cách tương xứng với giá trị tài khoản.
- Không chỉ dựa vào một email hoặc thông tin dễ biết như chức danh.
- Không để cùng một người vừa yêu cầu vừa tự duyệt ngoại lệ nếu chính sách cần độc lập.
- Giới hạn phạm vi và thời hạn của quyền khôi phục tạm thời.
- Buộc đăng ký lại authenticator theo quy trình và chấm dứt ngoại lệ sau đó.
- Thông báo, ghi bằng chứng và hậu kiểm trường hợp nhạy cảm.

Nếu dùng recovery code, cần quản lý như bí mật: đủ khó đoán, bảo vệ khi phát hành và lưu giữ, tránh ghi log, dùng một lần theo thiết kế và vô hiệu hóa mã đã dùng. Phía xác minh có thể lưu giá trị kiểm chứng phù hợp thay vì lưu mã có thể khôi phục trực tiếp.

Một tài khoản quản trị không nên được hỗ trợ bằng cách “tắt MFA vĩnh viễn cho tiện”. Nếu phải có ngoại lệ, ngoại lệ phải có giới hạn và khả năng theo dõi.

## 10. Chính sách và logic minh họa

### 10.1. Mô hình chính sách

Cấu hình dưới đây là mô hình trao đổi thiết kế, không phải cú pháp của một sản phẩm PAM cụ thể. Các thời lượng chỉ để minh họa:

~~~yaml
pam_portal_authentication:
  interactive_users:
    mfa_required: true
    privileged_roles:
      phishing_resistant_required: true
      user_verification_required: true

  sessions:
    maximum_minutes: 240
    idle_timeout_minutes: 15
    authentication_age_is_separate: true

  sensitive_actions:
    - name: "credential-checkout"
      maximum_authentication_age_minutes: 5
      bind_to_server_side_action: true
    - name: "change-pam-policy"
      maximum_authentication_age_minutes: 5
      bind_to_server_side_action: true
      independent_approval_if_required: true

  enrollment_and_recovery:
    protect_authenticator_changes: true
    notify_registered_contacts: true
    temporary_exceptions_must_expire: true

  failures:
    grant_without_required_authentication: false
    emergency_route: "separately-controlled-break-glass"
~~~

Chính sách không được chỉ nằm trong tài liệu. Cần ánh xạ từng điều kiện sang thành phần thực thi: IdP, backend portal, API gateway, dịch vụ cấp quyền hoặc điểm kiểm soát tương ứng.

### 10.2. Mã giả cho một hành động đặc quyền

~~~text
perform_sensitive_action(session_id, action_id):
    session = load_server_side_session(session_id)
    require(session.active)
    require(not session.expired)

    action = load_server_side_action(action_id)
    require(action.belongs_to(session.principal))
    require(action.not_expired)
    require(action.scope_has_not_changed)

    authentication = session.trusted_authentication_context

    if not meets_required_method(authentication, action):
        return REQUIRE_STRONGER_AUTHENTICATION

    if not sufficiently_recent(authentication, action, trusted_now):
        return REQUIRE_FRESH_AUTHENTICATION

    require(identity_is_active(session.principal))
    require(authorization_matches(session.principal, action))
    require(required_approvals_are_current(action))
    require(access_window_is_open(action))
    require(context_and_risk_are_acceptable(action))

    execute_once_or_idempotently_according_to_action_design(action)
    audit_result_without_secrets()
~~~

Các hàm trên là khái niệm, không thay thế triển khai xác minh giao thức hoặc mật mã. Những kiểm tra phiên bản và trạng thái cần được thiết kế để tránh khoảng đua giữa kiểm tra và thực thi.

Portal cũng cần phân biệt bằng chứng xác thực người dùng với token cấp quyền gọi API. Không dùng một loại token cho mục đích khác chỉ vì nó có chữ ký hợp lệ.

### 10.3. Danh tính máy không dùng quy trình người dùng

Dịch vụ tự động thường không có người để nhận OTP hoặc bấm push ở mỗi lần chạy. Không nên giải quyết bằng cách chia sẻ một điện thoại giữa các tiến trình hoặc lưu OTP seed cùng mật khẩu trong script.

Đối với workload, cần mô hình xác thực danh tính máy phù hợp, credential ngắn hạn, quyền tối thiểu, ràng buộc phạm vi và khả năng thu hồi. Người tạo hoặc thay đổi cấu hình đó vẫn có thể cần MFA khi thao tác trên portal.

Việc không dùng MFA tương tác cho một workload không có nghĩa tài khoản người dùng có thể được đổi tên thành “service” để bỏ qua kiểm soát.

## 11. Khi IdP hoặc dịch vụ MFA không khả dụng

Một sự cố dịch vụ xác thực không nên làm portal tự hạ từ MFA xuống mật khẩu mà không có quy trình.

Cần xác định trước:

- Có cho phép các phiên đã xác thực tiếp tục đến hạn hiện tại không.
- Hành động nào vẫn cần step-up và sẽ bị chặn khi không thực hiện được.
- Có chấp nhận bằng chứng xác thực còn đủ mới từ phiên hiện hữu không.
- Khi nào phải từ chối mọi hành động đặc quyền mới.
- Tuyến break-glass nào được phép hoạt động khi hệ thống phụ thuộc bị lỗi.
- Cách giám sát, thông báo và kiểm tra lại sau sự cố.

Không thể coi lỗi xác thực là kết quả “đã MFA”. Trạng thái không xác định phải được xử lý theo chính sách, không chuyển thành cho phép mặc định.

Nếu có tài khoản break-glass cục bộ, cần bảo vệ credential, giới hạn người được sử dụng, cảnh báo khi sử dụng, giới hạn thời gian và hậu kiểm. Tài khoản này không nên là đường đăng nhập thường ngày.

Việc khôi phục dịch vụ cũng cần kiểm tra các ngoại lệ còn tồn tại, authenticator đã thay đổi và phiên được tạo trong giai đoạn sự cố. Không để ngoại lệ tạm thời kéo dài sau khi nguyên nhân đã được xử lý.

## 12. Bằng chứng vận hành và giám sát

### 12.1. Ghi điều cần chứng minh, không ghi bí mật

Các sự kiện hữu ích gồm:

| Sự kiện | Dữ liệu gợi ý |
|---|---|
| Đăng nhập thành công hoặc thất bại | Danh tính, thời điểm, nguồn xác thực, kết quả và lý do phù hợp |
| Đánh giá mức xác thực | Mức hoặc loại phương thức theo mô hình đã thống nhất, tuổi xác thực và chính sách áp dụng |
| Step-up | Hành động, tài nguyên, thời điểm yêu cầu, kết quả và liên kết tới quyết định |
| Thay đổi authenticator | Người thao tác, định danh authenticator, thời điểm, loại thay đổi |
| Khôi phục hoặc ngoại lệ | Hồ sơ xử lý, người có thẩm quyền, phạm vi và hạn kết thúc |
| Thu hồi phiên | Nguyên nhân, thành phần thực thi, thời điểm và kết quả |
| Thực thi quyền PAM | Yêu cầu, phê duyệt, lease hoặc phiên đích và kết quả cấp hoặc từ chối |

Dùng định danh tương quan phù hợp để liên kết sự kiện. Không đưa cookie phiên thô, access token, OTP hoặc recovery code vào log nhằm tiện đối chiếu.

Đồng hồ giữa các thành phần cần đủ nhất quán để xác định thứ tự sự kiện và đánh giá freshness. Nếu có độ trễ hoặc lệch thời gian, bằng chứng phải được diễn giải trong giới hạn đó.

### 12.2. Những tín hiệu đáng điều tra

- Nhiều yêu cầu MFA không thành công hoặc bị người dùng từ chối liên tiếp.
- Đăng ký authenticator mới ngay trước một thao tác đặc quyền.
- Khôi phục tài khoản rồi checkout nhiều credential.
- Thay đổi chính sách để cho phép phương thức yếu hơn.
- Đăng nhập qua một đường cục bộ ít được sử dụng.
- Hành động đặc quyền xuất hiện mà không có bằng chứng xác thực tương ứng.
- Sử dụng phiên hoặc token sau sự kiện đáng lẽ phải thu hồi.
- Ngoại lệ hết hạn nhưng vẫn có thể đăng nhập hoặc thực hiện hành động.

Không dùng một tín hiệu đơn lẻ như địa chỉ IP mới để kết luận chắc chắn tài khoản đã bị chiếm. Kết hợp dữ liệu và điều tra theo ngữ cảnh, đồng thời áp dụng các biện pháp hạn chế phù hợp với mức rủi ro.

## 13. Tình huống: SSO thành công nhưng chưa đủ để checkout credential

Một kỹ sư đã đăng nhập hệ thống công ty từ đầu buổi sáng. Chiều cùng ngày, kỹ sư mở PAM portal để xử lý sự cố production.

Nếu portal chỉ kiểm tra rằng IdP trả về thành công, nó có thể tạo phiên từ một lần xác thực cũ hoặc không đạt mức bảo đảm cần cho quyền PAM.

Một luồng phù hợp hơn:

1. Portal xác minh bằng chứng từ đúng IdP, đúng đối tượng nhận và đúng luồng.
2. Portal kiểm tra mức và thời điểm xác thực theo chính sách đăng nhập.
3. Nếu chưa đạt, portal yêu cầu phương thức phù hợp rồi mới tạo phiên.
4. Kỹ sư gửi yêu cầu truy cập, được chủ hệ thống phê duyệt cho tài nguyên và khoảng thời gian cụ thể.
5. Khi kỹ sư chọn checkout credential, backend kiểm tra yêu cầu, quyền, thời gian và tuổi của xác thực.
6. Nếu bằng chứng đã quá cũ cho hành động này, portal yêu cầu step-up.
7. Kết quả step-up được liên kết với hành động phía máy chủ; trước khi cấp credential, backend kiểm tra lại các điều kiện.
8. Credential hoặc lease được cấp có thời hạn và việc sử dụng được ghi nhận theo chính sách.

Nếu người dùng mất authenticator ở bước 6, quy trình phải chuyển sang tuyến khôi phục hoặc khẩn cấp được kiểm soát. Nhân viên hỗ trợ không được coi sự hiện diện của một phiên SSO là lý do đủ để tắt MFA và cấp quyền ngay.

Sau khi kết thúc, việc đóng phiên portal và việc chấm dứt quyền trên đích phải được xử lý theo các vòng đời tương ứng. MFA tại portal không tự thu hồi một mật khẩu đã được tiết lộ.

## 14. Kiểm chứng trước khi triển khai

Kiểm thử cần bao phủ cả trường hợp thành công, đường thất bại và các đường truy cập thay thế.

| Ca kiểm thử | Kết quả cần đạt |
|---|---|
| Chỉ có mật khẩu khi chính sách yêu cầu MFA | Không tạo được phiên có mức bảo đảm bắt buộc |
| Có phiên SSO cũ | Không tự được coi là vừa thực hiện MFA |
| Có bằng chứng từ sai issuer hoặc đối tượng nhận | Bị từ chối |
| Client gửi mfa=true hoặc sửa trạng thái cục bộ | Không làm thay đổi trạng thái tin cậy phía máy chủ |
| Phương thức không đáp ứng yêu cầu chống phishing | Không được dùng cho nhóm hành động yêu cầu mức đó |
| User presence đạt nhưng user verification bắt buộc chưa đạt | Không được coi là đủ điều kiện |
| Checkout credential khi xác thực đã quá cũ | Yêu cầu xác thực mới phù hợp |
| Step-up xong nhưng hành động đổi tài nguyên hoặc quyền | Không tái sử dụng kết quả ngoài phạm vi đã ràng buộc |
| API hoặc CLI thực hiện hành động tương đương | Áp dụng mức bảo đảm và cấp quyền phù hợp, không tạo đường bỏ qua |
| Phiên hết hạn nhưng cookie vẫn còn trên trình duyệt | Backend từ chối |
| Thêm authenticator từ phiên không đủ bảo đảm | Bị chặn hoặc chuyển sang tuyến xác minh phù hợp |
| Recovery code đã dùng lại được gửi lần nữa | Bị từ chối theo thiết kế dùng một lần |
| Dịch vụ MFA không khả dụng | Không tự hạ yêu cầu xác thực cho luồng thường |
| Tài khoản bị khóa hoặc yếu tố bị báo mất | Các hành động và phiên liên quan được xử lý theo chính sách thu hồi |
| Đăng xuất portal khi có phiên đích đang chạy | Kết quả đúng với chính sách đã công bố và có bằng chứng |
| Log được kiểm tra sau các ca trên | Không chứa OTP, token, cookie hoặc credential có thể dùng lại |

MFA cho PAM portal cần được triển khai như một phần của chuỗi kiểm soát truy cập đặc quyền. Giá trị của nó nằm ở bằng chứng xác thực đáng tin cậy, mức bảo đảm phù hợp với hành động, phiên được giới hạn và quy trình khôi phục không làm mất các ràng buộc đã thiết kế.
