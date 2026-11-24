# Điều kiện để tài khoản được phép khôi phục

Trong chương **Eligibility Rules** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, **eligible account conditions** là tập điều kiện xác định một tài khoản có được sử dụng một đường khôi phục cụ thể cho một hành động cụ thể hay không.

Khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực, hệ thống cần giúp họ lấy lại quyền mà không vô tình bỏ qua trạng thái khóa, chính sách quản trị hoặc những hạn chế đang bảo vệ tài khoản. Vì vậy, “tìm thấy tài khoản” không đồng nghĩa “được gửi mọi loại mã”, và “đã xác minh một mã” không đồng nghĩa “được đăng nhập toàn quyền”.

Điều kiện hợp lệ phải kết hợp vòng đời tài khoản, bên quản lý danh tính, phương thức khôi phục đã thiết lập, phạm vi thay đổi và bối cảnh rủi ro. Chúng được kiểm tra phía máy chủ trước khi cấp quyền và kiểm tra lại khi thực hiện thay đổi.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt điều kiện của tài khoản với việc xác minh người đang yêu cầu khôi phục.
- Xác định ảnh hưởng của trạng thái hoạt động, khóa, đình chỉ, đóng hoặc xóa tài khoản.
- Chọn đúng bên chịu trách nhiệm khôi phục khi tài khoản dùng đăng nhập liên kết hoặc được tổ chức quản lý.
- Đánh giá việc một kênh hoặc bằng chứng đã được thiết lập có thực sự dùng được cho hành động yêu cầu hay không.
- Thiết kế kết quả đánh giá có phạm vi rõ, thay vì một cờ “recoverable” chung cho mọi tình huống.
- Ngăn đường khôi phục trở thành cách vượt hạn chế, dò tài khoản hoặc sử dụng một quyền đã mất hiệu lực.

## 2. Bốn câu hỏi phải được tách riêng

Một thiết kế dễ sai là chỉ có một thuộc tính “tài khoản khôi phục được”. Thuộc tính này không cho biết ai đang yêu cầu, muốn làm gì và sau thay đổi còn hạn chế nào.

| Câu hỏi | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Tài khoản có thuộc phạm vi đường khôi phục này không? | Kiểm tra điều kiện tài khoản và chính sách | Tài khoản có hỗ trợ mật khẩu cục bộ để đặt lại không? |
| Người yêu cầu đã chứng minh đủ quyền chưa? | Xác minh bằng chứng | Mã dự phòng có hợp lệ, chưa dùng và liên kết đúng tài khoản không? |
| Được phép thực hiện hành động nào? | Cấp quyền có phạm vi | Được đổi mật khẩu nhưng chưa được gỡ MFA |
| Sau thay đổi có được đăng nhập hoặc sử dụng dịch vụ không? | Áp dụng chính sách truy cập hiện tại | Tài khoản vẫn bị đình chỉ dù credential đã được sửa theo đường được phép |

Bài học tập trung vào câu hỏi thứ nhất và mối liên hệ của nó với ba câu hỏi còn lại.

**Đủ điều kiện để bắt đầu xác minh không phải là đã được xác minh.** Ví dụ, một tài khoản có mã dự phòng đang hoạt động có thể thuộc đường dùng mã dự phòng. Người yêu cầu vẫn phải cung cấp mã được máy chủ chấp nhận trước khi nhận quyền thay đổi.

Tương tự, cho phép sửa credential không nhất thiết có nghĩa được mở lại tài khoản. Một lệnh đình chỉ cần giữ nguyên hiệu lực nếu chưa có quyết định riêng cho việc gỡ đình chỉ.

## 3. Xác định tài khoản đích một cách nhất quán

Trước khi đánh giá điều kiện, hệ thống cần xác định nội bộ tài khoản đích, phạm vi tổ chức và hành động yêu cầu. Không lấy quyết định trực tiếp từ những thuộc tính do client tự khai báo.

Ví dụ, người yêu cầu có thể nhập một email và chọn “tôi quên mật khẩu”. Hệ thống vẫn phải kiểm tra:

- Email đó có ánh xạ đến tài khoản phù hợp trong phạm vi đang xử lý hay không.
- Tài khoản có phương thức mật khẩu mà dịch vụ được quyền đặt lại hay không.
- Hành động yêu cầu có được chính sách của tài khoản cho phép hay không.
- Có đường khôi phục tương ứng được thiết lập và còn đủ điều kiện sử dụng hay không.

### Định danh tài khoản và địa chỉ liên hệ là hai thứ khác nhau

Email hoặc số điện thoại có thể thay đổi, được tái sử dụng hoặc xuất hiện trong nhiều phạm vi tổ chức. Giao dịch nên liên kết với định danh tài khoản nội bộ ổn định, không chỉ với một chuỗi email.

Nếu một email từng thuộc tài khoản đã xóa rồi được dùng cho tài khoản mới, mã khôi phục của tài khoản cũ không được áp dụng cho tài khoản mới. Việc trùng địa chỉ không tạo ra quyền kế thừa danh tính, dữ liệu hoặc credential.

Với hệ thống nhiều tổ chức, việc tìm tài khoản và thực thi thay đổi phải giữ đúng phạm vi tổ chức. Một quyền khôi phục trong tổ chức A không được dùng để thay tài khoản có cùng email trong tổ chức B.

## 4. Điều kiện theo vòng đời tài khoản

Tên trạng thái thực tế khác nhau giữa các hệ thống. Điều quan trọng là định nghĩa tác động của từng trạng thái đến hành động và đường khôi phục.

Bảng dưới đây là một mô hình thiết kế minh họa, không phải quy tắc bắt buộc áp dụng cho mọi dịch vụ.

| Trạng thái hoặc tình huống | Hướng đánh giá | Điều không được tự suy ra |
| --- | --- | --- |
| Đang chờ hoàn tất đăng ký | Có thể hướng tới hoàn tất đăng ký hoặc xác minh liên hệ theo quy trình riêng | Có một bản ghi đăng ký không có nghĩa tài khoản đã có đầy đủ quyền |
| Đang hoạt động | Có thể dùng đường khôi phục nếu các điều kiện khác đạt | Trạng thái hoạt động không tự chứng minh người yêu cầu là chủ tài khoản |
| Tạm khóa do nhiều lần đăng nhập sai | Xác định có đường khôi phục thay thế được phép hay không | Đổi mật khẩu không mặc nhiên xóa mọi hạn chế và cho đăng nhập ngay |
| Bị hạn chế vì nghi bị chiếm | Dùng chính sách xử lý sự cố và xem lại độ tin cậy của các kênh | Kênh đang ghi trong hồ sơ không chắc còn an toàn |
| Bị đình chỉ bởi quản trị | Tách quyền sửa credential nếu có khỏi quyền mở lại tài khoản | Người chứng minh được danh tính không tự có quyền gỡ đình chỉ |
| Đã đóng nhưng có quy trình khôi phục trạng thái được hỗ trợ | Kiểm tra điều kiện của việc mở lại và việc sửa credential riêng biệt | Khôi phục mật khẩu không tự thực hiện mở lại tài khoản |
| Đã xóa vĩnh viễn theo mô hình sản phẩm | Không dùng luồng khôi phục credential để tái tạo tài khoản cũ | Dữ liệu lịch sử còn ở hệ thống khác không có nghĩa được phép khôi phục |
| Không tồn tại trong phạm vi đang xử lý | Nội bộ không tạo quyền thay đổi tài khoản | Phản hồi công khai không nên xác nhận kết quả tra cứu |

### 4.1. Không biến khóa đăng nhập thành mất tài khoản vĩnh viễn

Nếu mọi tài khoản bị khóa do thử sai đều bị cấm khôi phục, đối thủ có thể cố tình làm chủ tài khoản bị mắc kẹt. Cần có đường xử lý phù hợp cho chủ tài khoản hợp lệ khi chính sách cho phép.

Tuy nhiên, đường đó vẫn phải xác minh bằng chứng. Một yêu cầu nặc danh “hãy mở khóa” không đủ để gỡ kiểm soát bảo vệ tài khoản.

### 4.2. Không dùng khôi phục để vượt đình chỉ

Một tài khoản bị đình chỉ có thể có hai nhu cầu khác nhau: sửa thông tin xác thực bị lộ và xin quyền hoạt động trở lại.

Nếu sản phẩm hỗ trợ sửa credential trong trạng thái đình chỉ, kết quả chỉ thực hiện thay đổi đã được cho phép. Những API truy cập dữ liệu và phiên đăng nhập vẫn phải thực thi hạn chế hiện tại.

Nếu không hỗ trợ hành động đó trong trạng thái đình chỉ, hệ thống cần một kết quả rõ ràng theo chính sách. Không tự chuyển sang nhánh hỗ trợ có thể bỏ qua trạng thái.

## 5. Ai có thẩm quyền khôi phục danh tính?

Điều kiện không chỉ nằm ở trạng thái “active”. Ứng dụng phải biết credential nào thuộc quyền quản lý của mình và chính sách nào chi phối tài khoản.

### 5.1. Tài khoản được dịch vụ quản lý trực tiếp

Dịch vụ có thể quản lý mật khẩu, TOTP, passkey hoặc mã dự phòng. Mỗi hành động cần một đường tương ứng.

Một tài khoản không dùng mật khẩu không tự thuộc đường đặt lại mật khẩu. Nếu muốn bổ sung mật khẩu như một phương thức mới, sản phẩm phải có thiết kế và chính sách riêng cho việc đó; không thể dùng nhãn “khôi phục” để tạo phương thức ngoài phạm vi đã cho phép.

### 5.2. Tài khoản đăng nhập qua nhà cung cấp danh tính

Với tài khoản chỉ đăng nhập thông qua một nhà cung cấp danh tính, ứng dụng có thể không có mật khẩu cục bộ để đặt lại. Hành trình cần xác định bên xử lý phần mất quyền đó.

Không nên tự tạo mật khẩu cục bộ khi người dùng mất quyền tại nhà cung cấp, vì cách này có thể vượt chính sách xác thực của tổ chức hoặc thay đổi mô hình tin cậy.

Nếu tài khoản thực sự hỗ trợ cả đăng nhập liên kết và phương thức cục bộ, từng đường phải được đánh giá theo cấu hình đã được cho phép. Không suy luận chỉ từ miền email hoặc nút đăng nhập người dùng vừa bấm.

### 5.3. Tài khoản do tổ chức quản lý

Tổ chức có thể quy định phương thức khôi phục, yêu cầu quản trị phê duyệt hoặc giới hạn những hành động tự phục vụ. Dịch vụ cần tải chính sách trong đúng phạm vi tổ chức từ dữ liệu đáng tin cậy phía máy chủ.

Đường khôi phục dành cho tài khoản cá nhân không được tự áp dụng cho tài khoản tổ chức chỉ vì người yêu cầu có cùng một loại bằng chứng.

Đối với tài khoản đặc quyền, hậu quả cấp quyền sai có thể lớn hơn. Chính sách có thể yêu cầu đường riêng, phê duyệt độc lập hoặc quyền ban đầu hạn chế. Đây phải là điều kiện được thiết kế trước, không phải quyết định tùy hứng của nhân viên hỗ trợ.

## 6. Có ít nhất một đường khôi phục phù hợp được thiết lập không?

Tài khoản tồn tại, đang hoạt động và do dịch vụ quản lý vẫn có thể không có đường tự phục vụ phù hợp cho hành động đang yêu cầu.

Một đường chỉ khả dụng khi các điều kiện nền của nó đạt. Ví dụ:

| Đường minh họa | Điều kiện nền cần kiểm tra | Vẫn phải xác minh sau đó |
| --- | --- | --- |
| Dùng authenticator còn lại | Có credential phù hợp đang được tài khoản chấp nhận và không bị vô hiệu hóa | Người yêu cầu hoàn tất xác thực đúng yêu cầu |
| Dùng mã dự phòng | Tài khoản có cơ chế mã dự phòng còn hiệu lực theo chính sách | Mã cung cấp hợp lệ, chưa dùng, đúng phạm vi |
| Nhận liên kết qua email | Có kênh đã được thiết lập, xác minh và được phép dùng cho hành động | Người yêu cầu cung cấp bằng chứng từ giao dịch được chấp nhận |
| Dùng số điện thoại | Số đã được xác minh và đường đó được chính sách hỗ trợ | Mã hoặc bằng chứng đáp ứng điều kiện của giao dịch |
| Xem xét theo quy trình riêng | Loại tài khoản và tình huống nằm trong phạm vi quy trình được hỗ trợ | Hoàn tất kiểm tra và nhận quyết định theo thẩm quyền |

Không cần bắt người dùng chứng minh vẫn giữ toàn bộ phương thức đã mất để được khôi phục. Điều cần có là một đường thay thế phù hợp với tình huống và mức thay đổi quyền.

Ngược lại, việc một tài khoản có email không có nghĩa email đủ để gỡ mọi MFA. Điều kiện nền phải được đánh giá **theo hành động**, không chỉ theo việc có một trường dữ liệu.

### Kênh có trước, kênh mới và kênh bị nghi chiếm

Một kênh mới do người yêu cầu nhập vào không tự là căn cứ sở hữu tài khoản. Nhận được mã ở email mới chỉ chứng minh khả năng nhận mã tại email đó, không chứng minh quyền thay email của tài khoản cũ.

Với kênh vừa được thay gần đây, chính sách có thể cần xét lịch sử, thời điểm thay và nguồn gốc quyền đã cho phép thay. Không cần mặc định một số ngày cố định cho mọi sản phẩm; quy tắc phải có lý do và được thực thi nhất quán.

Kênh cũ hơn cũng không tự an toàn. Nếu có dấu hiệu email hoặc thiết bị đã bị chiếm, cần xác định đường nào còn đủ tin cậy. Một đường xử lý sự cố có thể sử dụng căn cứ trước sự cố theo quy trình riêng, nhưng không nên tự bỏ kiểm tra vì dữ liệu “đã tồn tại từ lâu”.

## 7. Điều kiện theo hành động và phạm vi kết quả

Nên biểu diễn điều kiện như một quyết định có ngữ cảnh:

> Tài khoản A, trong tổ chức T và trạng thái hiện tại, có thể tiếp tục đường R để xác minh cho hành động X, với các yêu cầu và hạn chế đã nêu.

Cách diễn đạt này rõ hơn “A có thể khôi phục”.

| Hành động | Ví dụ điều kiện tài khoản | Phạm vi kết quả cần giữ |
| --- | --- | --- |
| Đặt lại mật khẩu | Tài khoản có mật khẩu cục bộ và được phép thay qua đường này | Thay mật khẩu; MFA hoặc hạn chế truy cập còn áp dụng vẫn giữ hiệu lực |
| Thay yếu tố MFA bị mất | Loại yếu tố đó tồn tại và có đường thay được chính sách chấp nhận | Chỉ thay yếu tố theo giao dịch được duyệt |
| Đăng ký passkey mới sau mất quyền | Có đường khôi phục cho phép cấp quyền đăng ký authenticator | Không tự cấp thêm quyền đổi email hoặc gỡ mọi phương thức |
| Thay kênh khôi phục | Chính sách cho phép thay và có căn cứ phù hợp độc lập với kênh mới | Thay đúng kênh; đánh giá tác động tới những lần khôi phục sau |
| Xử lý phiên trên thiết bị mất | Hành động thu hồi nằm trong phạm vi được cấp | Không biến quyền quản lý phiên thành quyền đổi mọi credential |
| Mở lại tài khoản đã đóng | Sản phẩm có hỗ trợ mở lại và các điều kiện riêng được đáp ứng | Không gộp tự động với đặt lại mật khẩu |

Nếu người yêu cầu thay đổi mục tiêu giữa chừng, chẳng hạn từ đặt lại mật khẩu sang gỡ MFA, phải đánh giá lại điều kiện và bằng chứng cho hành động mới. Không dùng một giao dịch đã đạt yêu cầu thấp hơn để cấp thêm quyền.

Đăng ký một authenticator mạnh sau khôi phục cũng không sửa được quyết định chấp nhận sai trước đó. Nếu đối thủ được cấp nhầm quyền đăng ký passkey, passkey mới có thể hoạt động đúng giao thức nhưng vẫn thuộc quyền đối thủ.

## 8. Tín hiệu rủi ro và các điều kiện không được bỏ qua

Các tín hiệu như thiết bị quen, IP, lịch sử sử dụng hoặc vị trí gần đúng có thể hỗ trợ đánh giá. Chúng không tự thay thế điều kiện nền hoặc bằng chứng bắt buộc.

Ví dụ:

- IP quen thuộc không làm tài khoản bị xóa vĩnh viễn trở thành tài khoản đang hoạt động.
- Cookie nhận diện thiết bị không trao quyền gỡ đình chỉ.
- Thiết bị mới không tự chứng minh chủ tài khoản hợp lệ đã mất quyền sở hữu.
- Nhiều dữ kiện hồ sơ đúng không thay cho bằng chứng còn thiếu nếu dữ kiện đó có thể đã bị lộ.
- Một mã hợp lệ không trao quyền cho hành động nằm ngoài phạm vi của mã.

Khi có nghi ngờ bị chiếm, hệ thống có thể chuyển sang đường xử lý có kiểm soát thay vì tiếp tục đường thường. Nhưng khai báo chưa được kiểm chứng của bất kỳ ai cũng không nên tự động tạo ra hạn chế vĩnh viễn hoặc thu hồi mọi phương thức của tài khoản đích.

### Phân biệt không được phép, chưa đủ căn cứ và lỗi tạm thời

Ba kết quả này cần cách xử lý khác nhau:

| Kết quả nội bộ | Ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| Không được phép theo chính sách | Hành động hoặc đường không nằm trong phạm vi được hỗ trợ | Giữ hạn chế, chỉ chuyển đường khác nếu thật sự được phép |
| Chưa đủ căn cứ | Có thể còn bước xác minh hoặc xem xét được hỗ trợ | Yêu cầu đúng bằng chứng hoặc chuyển xử lý theo quy trình |
| Chưa đánh giá được | Thiếu dữ liệu đáng tin cậy hoặc thành phần phụ thuộc đang lỗi | Chưa cấp quyền thay đổi; cho thử lại hoặc xử lý sự cố vận hành |

Không có dữ liệu về trạng thái đình chỉ không có nghĩa là không bị đình chỉ. Tuy vậy, một lỗi tải chính sách cũng không nên bị ghi thành kết luận vĩnh viễn rằng chủ tài khoản không bao giờ được khôi phục.

## 9. Mô hình kết quả đánh giá

Thay vì trả một giá trị đúng/sai chung, một kết quả nội bộ có thể gồm:

- Tài khoản và phạm vi tổ chức đã được cố định.
- Hành động đang xem xét.
- Kết quả: tiếp tục xác minh, chuyển đúng bên quản lý, chờ xem xét, không hỗ trợ hoặc thử lại sau.
- Những đường xác minh được phép.
- Những hạn chế phải giữ sau thay đổi.
- Phiên bản chính sách và dữ liệu bảo mật liên quan.
- Lý do quyết định dành cho kiểm toán nội bộ.

Các trường này không đồng nghĩa đều được trả cho người dùng chưa xác thực. Thông tin như tài khoản có tồn tại, trạng thái đình chỉ hoặc kênh đăng ký có thể phải được giữ nội bộ.

~~~mermaid
flowchart TD
    A[Yêu cầu khôi phục] --> B[Xác định nội bộ tài khoản, phạm vi và hành động]
    B --> C{Vòng đời và hạn chế cho phép hành động?}
    C -- Không --> D[Không cấp quyền theo đường này]
    C -- Cần dữ liệu hoặc xem xét --> E[Chờ xử lý theo cơ chế được phép]
    C -- Có --> F{Đúng bên quản lý credential?}
    F -- Không --> G[Chuyển đúng đường quản lý nếu được hỗ trợ]
    F -- Có --> H{Có đường khôi phục phù hợp đã thiết lập?}
    H -- Không --> I[Xem xét nếu được hỗ trợ, hoặc kết thúc]
    H -- Có --> J[Cho tiếp tục xác minh theo phạm vi]
    J --> K[Kiểm tra bằng chứng và điều kiện hiện tại]
    K --> L{Được cấp quyền cho hành động?}
    L -- Có --> M[Thực hiện đúng thay đổi, giữ hạn chế còn hiệu lực]
    L -- Chưa đủ --> N[Bổ sung bằng chứng hoặc kết thúc theo chính sách]
~~~

Điểm J chỉ cho phép bước xác minh tiếp theo. Quyền thay credential chỉ xuất hiện khi các kiểm tra tiếp theo đạt điều kiện.

### Mã giả minh họa

~~~text
evaluateAccountEligibility(account, action, policy, now):
    if account is absent:
        return INTERNAL_UNAVAILABLE

    if not policy.allowsActionInLifecycle(account.lifecycle, action):
        return UNAVAILABLE_FOR_THIS_ACTION

    if policy.requiresDifferentAuthority(account, action):
        return USE_APPROVED_AUTHORITY_ROUTE

    restrictions = policy.restrictionsToPreserve(account, action)

    if policy.requiresControlledReview(account, action):
        return REVIEW_ONLY_IF_SUPPORTED(restrictions)

    routes = policy.routesWithEstablishedPrerequisites(
        account = account,
        action = action,
        atTime = now
    )

    if routes is empty:
        return NO_SELF_SERVICE_ROUTE

    return CONTINUE_VERIFICATION(
        accountId = account.id,
        tenantId = account.tenantId,
        action = action,
        permittedRoutes = routes,
        restrictionsToPreserve = restrictions,
        policyVersion = policy.version
    )
~~~

Mã giả không kiểm tra OTP và không cấp phiên đăng nhập. Nó chỉ minh họa đánh giá điều kiện tài khoản. Trường hợp không thể tải dữ liệu hoặc chính sách phải được xử lý như chưa đánh giá được, không tự đi tới kết quả cho phép.

Các điều kiện trong mã thực tế phải dựa trên dữ liệu phía máy chủ. Những cờ do client gửi như “accountActive=true” hoặc “isPersonalAccount=true” không phải căn cứ đáng tin cậy.

## 10. Điều kiện có thể thay đổi trong lúc khôi phục

Một giao dịch có thể kéo dài qua nhiều bước. Trong thời gian đó:

- Quản trị viên đình chỉ tài khoản.
- Một kênh khôi phục bị thay hoặc bị thu hồi.
- Bằng chứng bị báo mất an toàn.
- Tài khoản được đóng hoặc xóa theo quy trình sản phẩm.
- Chính sách áp dụng cho loại tài khoản thay đổi.
- Một giao dịch khác đã thay credential hoặc tiêu thụ quyền.

Vì vậy, đánh giá đạt điều kiện ở thời điểm bắt đầu không phải là giấy phép vô thời hạn.

### Ví dụ thay đổi trạng thái

Lúc 09:00, tài khoản đang hoạt động và đủ điều kiện nhận liên kết đặt lại mật khẩu. Lúc 09:02, tài khoản bị đình chỉ theo chính sách quản trị. Lúc 09:05, người yêu cầu mở liên kết.

Ngay cả khi liên kết đúng chữ ký, chưa hết hạn và chưa dùng, hệ thống vẫn phải kiểm tra điều kiện hiện tại cho hành động. Nếu chính sách không cho thay mật khẩu trong trạng thái đình chỉ, không được thực hiện. Nếu cho phép sửa credential nhưng không mở lại truy cập, phải giữ đúng giới hạn đó.

**Token hợp lệ không thay thế điều kiện hiện tại của tài khoản.**

### Dữ liệu cần cố định và dữ liệu cần kiểm tra lại

Tài khoản đích, tổ chức và hành động không được âm thầm đổi theo địa chỉ liên hệ mới. Những dữ liệu bảo mật có ảnh hưởng đến quyết định phải được kiểm tra lại ở thời điểm cấp và thực hiện quyền.

Có thể dùng phiên bản chính sách hoặc phiên bản trạng thái bảo mật để hỗ trợ phát hiện thay đổi. Cần định nghĩa thay đổi nào làm quyền mất hiệu lực, thay đổi nào cần đánh giá lại; không nhất thiết mọi sửa tên hiển thị đều phải hủy giao dịch.

Việc kiểm tra trạng thái, tiêu thụ quyền một lần và cập nhật credential phải có cơ chế nhất quán. Nếu chỉ kiểm tra rồi ghi sau mà không bảo vệ trước thay đổi đồng thời, tài khoản có thể đã không còn đủ điều kiện tại lúc cập nhật.

## 11. Không biến đánh giá điều kiện thành công cụ dò tài khoản

Kết quả nội bộ có thể rất chi tiết, nhưng điểm bắt đầu khôi phục thường dành cho người chưa đăng nhập. Trả trực tiếp “tài khoản không tồn tại”, “đang đình chỉ” hoặc “chỉ có passkey” có thể làm lộ thông tin.

Một phản hồi công khai minh họa là:

> Nếu thông tin phù hợp với một tài khoản và đường khôi phục được hỗ trợ, hướng dẫn sẽ được gửi.

Phản hồi này không tự làm hệ thống an toàn nếu những yếu tố khác vẫn khác biệt rõ rệt. Cần xét mã phản hồi, thời gian xử lý, đường gửi lại, giới hạn thử và các API phụ.

Chỉ tiết lộ những thông tin cần thiết khi người yêu cầu đã đạt điều kiện được xem. Che một phần số điện thoại hoặc email không mặc nhiên làm chúng phù hợp để công khai.

Các yêu cầu khôi phục cũng cần giới hạn lạm dụng phù hợp để tránh dò định danh, gửi thông báo hàng loạt và gây phiền cho chủ tài khoản. Nhưng giới hạn thử không được bị hiểu thành bằng chứng sở hữu: chờ qua thời gian giới hạn không làm một tài khoản không đủ điều kiện trở thành đủ điều kiện.

### Ghi nhận quyết định mà không ghi bí mật

Bản ghi nội bộ có thể lưu mã quyết định, hành động, đường đang xét, phiên bản chính sách, thời điểm và hạn chế phải giữ. Dữ liệu này giúp phân biệt lỗi chính sách, thiếu bằng chứng và lỗi vận hành.

Không ghi token, OTP, mã dự phòng, cookie hoặc tài liệu nhạy cảm đầy đủ vào log chỉ để biết vì sao một đường bị từ chối. Quyền xem log và thời hạn lưu cũng cần phù hợp với mục đích sử dụng.

## 12. Các tình huống thực tế

### Tình huống A: Tài khoản đang hoạt động nhưng chưa có đường phù hợp

Mai có tài khoản không dùng mật khẩu, đã mất mọi passkey và chưa thiết lập mã dự phòng. Hồ sơ có một email liên hệ.

Nếu chính sách không chấp nhận email đơn lẻ để đăng ký authenticator mới, kết luận không thể là “active nên cho khôi phục qua email”. Tài khoản có thể không có đường tự phục vụ đủ điều kiện cho hành động này.

Hệ thống chuyển xem xét nếu có quy trình phù hợp, hoặc kết thúc chưa thể khôi phục theo đường đang xét. Không tự tạo mật khẩu mới để lách yêu cầu.

### Tình huống B: Tài khoản bị khóa do thử sai

Nam còn giữ một authenticator được chính sách chấp nhận nhưng tài khoản bị tạm khóa sau nhiều lần thử sai. Sản phẩm có đường xử lý phù hợp cho tình huống này.

Hệ thống có thể cho Nam tiếp tục xác minh qua đường đó. Sau xác minh, chỉ áp dụng các thay đổi hoặc việc mở khóa mà chính sách cho phép; không bỏ mọi hạn chế chỉ vì người dùng đã vào trang khôi phục.

### Tình huống C: Tài khoản tổ chức chỉ dùng đăng nhập liên kết

Lan dùng tài khoản do tổ chức quản lý, đăng nhập thông qua nhà cung cấp danh tính. Ứng dụng không quản lý mật khẩu cục bộ của Lan.

Luồng đặt lại mật khẩu cục bộ không thuộc phạm vi tài khoản này. Hệ thống cần hướng tới đường quản lý đã được tổ chức chấp nhận, thay vì tạo credential cục bộ mới và làm mất tác dụng của chính sách tổ chức.

### Tình huống D: Sửa credential của tài khoản đang đình chỉ

Tài khoản của Huy bị đình chỉ. Chính sách minh họa của sản phẩm cho phép sửa credential bị lộ qua một quy trình có kiểm soát nhưng chưa cho phép hoạt động trở lại.

Sau khi Huy đạt điều kiện và xác minh đủ, mật khẩu có thể được thay theo phạm vi đã duyệt. Tài khoản vẫn đình chỉ; hệ thống không cấp một phiên truy cập toàn quyền.

### Tình huống E: Liên kết thuộc tài khoản cũ đã bị xóa

Một địa chỉ email được dùng cho tài khoản mới sau khi tài khoản cũ đã bị xóa. Có người mở một liên kết khôi phục được phát hành cho tài khoản cũ.

Liên kết không được áp dụng cho tài khoản mới chỉ vì cùng email. Tài khoản đích và phạm vi của giao dịch phải giữ nguyên; điều kiện hiện tại của tài khoản cũ quyết định việc xử lý.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Hướng thiết kế |
| --- | --- | --- |
| Chỉ kiểm tra tài khoản tồn tại | Bất kỳ bản ghi nào cũng có thể bị đưa vào đường cấp quyền | Kiểm tra vòng đời, thẩm quyền, hành động và đường được phép |
| Một cờ “recoverable” cho mọi việc | Đặt lại mật khẩu có thể bị dùng để gỡ MFA hoặc thay email | Đánh giá theo hành động và ghi rõ phạm vi |
| Coi mã đúng là đủ | Vượt trạng thái đình chỉ, sai tổ chức hoặc điều kiện đã đổi | Kiểm tra cả bằng chứng và điều kiện tài khoản tại thời điểm quyết định |
| Dùng email mới làm căn cứ duy nhất | Người yêu cầu tự chọn nơi nhận bằng chứng rồi chiếm quyền | Dựa vào đường đã được thiết lập hoặc quy trình khác được phép |
| Tự tạo mật khẩu cho tài khoản liên kết | Vượt bên quản lý danh tính và chính sách tổ chức | Giữ đúng thẩm quyền quản lý credential |
| Cấm mọi tài khoản bị khóa khôi phục | Đối thủ có thể gây thử sai để chặn chủ tài khoản | Thiết kế đường xử lý có bằng chứng cho loại khóa phù hợp |
| Đặt lại mật khẩu tự gỡ đình chỉ | Khôi phục trở thành đường vượt hạn chế | Giữ trạng thái truy cập và quyền sửa credential tách biệt |
| Chỉ đánh giá ở đầu giao dịch | Quyền còn được dùng sau khi tài khoản không còn đủ điều kiện | Đánh giá lại khi cấp quyền và trước thay đổi |
| Hỗ trợ có quyền bỏ qua mọi điều kiện | Đường thủ công trở thành điểm vượt chính sách | Xác định thẩm quyền, điều kiện và kiểm toán của từng ngoại lệ |
| Trả lý do nội bộ cho mọi người | Làm lộ tài khoản và trạng thái bảo mật | Tách kết quả nội bộ khỏi phản hồi công khai |

## 14. Danh sách kiểm tra khi xác định điều kiện

Một đặc tả đủ rõ cần trả lời được:

- Tài khoản đích và phạm vi tổ chức được xác định bằng dữ liệu nào?
- Vòng đời hiện tại cho phép hành động nào và giữ lại hạn chế nào?
- Dịch vụ hay bên quản lý danh tính khác có thẩm quyền thay credential?
- Có đường khôi phục phù hợp đã được thiết lập cho hành động yêu cầu không?
- Điều kiện nền nào khác với bằng chứng người yêu cầu phải cung cấp?
- Một kênh mới, kênh vừa thay hoặc kênh bị nghi chiếm được xử lý ra sao?
- Khi chưa có đường tự phục vụ, có quy trình xem xét được hỗ trợ thật sự không?
- Kết quả cho phép tiếp tục xác minh có bị nhầm với quyền thay đổi hoặc đăng nhập không?
- Những thay đổi trạng thái nào phải làm giao dịch dừng hoặc đánh giá lại?
- Phản hồi công khai và log có giữ đúng giới hạn tiết lộ dữ liệu không?

Điều kiện tài khoản hợp lệ phải dẫn đến một quyết định có phạm vi: tài khoản nào được tiếp tục đường nào, cho hành động nào, với những yêu cầu và hạn chế nào. Nhờ đó, luồng khôi phục có thể giúp chủ tài khoản lấy lại quyền mà vẫn giữ hiệu lực của các cơ chế bảo vệ đang áp dụng.