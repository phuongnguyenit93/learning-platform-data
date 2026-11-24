# Authenticator trong Authentication và vòng đời danh tính IAM

## 1. Authenticator là gì?

Trong **Identity and Access Management (IAM)**, *authenticator* là **phương tiện hoặc bí mật mà chủ thể kiểm soát và sử dụng để chứng minh quyền kiểm soát danh tính khi xác thực**. Authenticator có thể là mật khẩu, thiết bị tạo mã OTP, ứng dụng xác thực, khóa bảo mật FIDO2, passkey, thẻ thông minh chứa khóa mật mã hoặc một khóa riêng được quản lý bởi workload.

Ví dụ, khi Linh đăng nhập vào hệ thống qua **Identity Provider (IdP)**:

1. Linh khai báo danh tính hoặc chọn tài khoản.
2. IdP yêu cầu một hoặc nhiều phương tiện chứng thực đã được **liên kết với danh tính của Linh**.
3. Linh sử dụng phương tiện chứng thực để trả lời thử thách.
4. IdP kiểm tra bằng chứng, trạng thái phương tiện và chính sách đăng nhập.
5. Nếu các điều kiện đều đạt, IdP tạo phiên hoặc phát hành thông tin xác thực cho ứng dụng sử dụng **Single Sign-On (SSO)**.

Ở đây, **authenticator là phương tiện dùng để chứng minh**, còn **authentication** là quá trình xác minh bằng chứng và quyết định có chấp nhận đăng nhập hay không. Trong phạm vi module vòng đời danh tính, mục tiêu là biết cách đăng ký, liên kết, quản trị, kiểm tra và thu hồi authenticator khi nhân viên **Joiner–Mover–Leaver**.

### Phân biệt các khái niệm thường bị trộn lẫn

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Identity** | Bản ghi danh tính số được IAM quản lý | Danh tính nhân viên Linh |
| **Authenticator** | Phương tiện/bí mật để chủ thể chứng minh quyền kiểm soát | Passkey hoặc thiết bị OTP |
| **Authentication factor** | Loại bằng chứng mà authenticator thể hiện | Điều biết, vật sở hữu, đặc điểm sinh trắc |
| **Credential** | Thông tin liên kết danh tính với authenticator hoặc chứng minh quyền truy cập, tùy ngữ cảnh | Bản ghi khóa công khai FIDO, chứng chỉ, mật khẩu đã băm |
| **Verifier** | Thành phần kiểm tra bằng chứng chứng thực | IdP, authentication server |
| **Authentication assertion** | Thông điệp xác nhận sự kiện xác thực cho bên nhận | OIDC ID token hoặc SAML assertion |
| **Access token** | Credential để yêu cầu quyền tới API/resource server | OAuth access token |
| **Authorization** | Quyết định hành động nào được phép trên tài nguyên nào | Chỉ được đọc báo cáo dự án A |

Một người có thể **xác thực thành công** nhưng vẫn không được phép vào tài nguyên. Ngược lại, hệ thống có thể lưu entitlement hợp lệ nhưng cần từ chối đăng nhập vì authenticator bị thu hồi hoặc chưa đạt chính sách MFA.

## 2. Ba nhóm authentication factor và các giới hạn

Các factor thường được chia thành:

| Factor | Câu hỏi bảo mật | Ví dụ | Rủi ro đặc trưng |
| --- | --- | --- | --- |
| **Something you know** — điều người dùng biết | Người dùng biết bí mật gì? | Mật khẩu, PIN độc lập dùng để xác thực | Bị lừa nhập, bị lộ, tái sử dụng hoặc dò đoán |
| **Something you have** — vật/phương tiện sở hữu | Người dùng kiểm soát vật/khóa nào? | Khóa FIDO2, điện thoại chứa khóa, thiết bị OTP | Mất thiết bị, chuyển giao trái phép, sao chép bí mật trong một số thiết kế |
| **Something you are** — sinh trắc học | Người dùng có đặc điểm nào được kiểm tra? | Vân tay, khuôn mặt trên thiết bị hỗ trợ | Sai số, giả mạo cảm biến, quyền riêng tư, khó thay đổi nếu lộ dữ liệu |

**Multi-Factor Authentication (MFA)** yêu cầu bằng chứng từ **ít nhất hai factor độc lập** theo thiết kế xác thực. Dùng mật khẩu cộng một câu hỏi bí mật thường vẫn thuộc nhóm *điều biết*, không tự trở thành MFA. Hai mã OTP được tạo trên hai ứng dụng cũng không nhất thiết đại diện cho hai loại factor khác nhau.

Với **passkey/WebAuthn**, việc thiết bị sở hữu khóa riêng và yêu cầu **user verification** bằng PIN hoặc sinh trắc học cục bộ có thể cung cấp xác thực nhiều yếu tố theo đặc tính authenticator và chính sách verifier. Nếu chỉ sử dụng khóa sở hữu và **không yêu cầu user verification**, không nên mặc định ghi nhận đã đáp ứng MFA. Cần kiểm tra đúng thuộc tính của sự kiện xác thực thay vì suy từ nhãn “passkey”.

**Sinh trắc học** thường được dùng để mở khóa authenticator trên thiết bị. Bản thân việc ứng dụng hiện hình vân tay không chứng minh hệ thống từ xa đã được xác thực bằng giao thức chống phishing; phải xét toàn bộ luồng, thiết bị, khóa, thử thách và thông tin mà verifier kiểm chứng.

## 3. Các loại authenticator thông dụng

| Loại | Cách sử dụng | Ưu điểm | Giới hạn và lưu ý |
| --- | --- | --- | --- |
| **Memorized secret** | Người dùng nhập mật khẩu hoặc passphrase | Phổ biến, không đòi hỏi thiết bị chuyên biệt | Dễ bị phishing/tái sử dụng; cần rate limit, lưu trữ an toàn |
| **TOTP/HOTP OTP app** | Ứng dụng hoặc thiết bị tạo mã dùng một lần | Có thể làm factor bổ sung, không cần nhận SMS | Mã có thể bị phishing theo thời gian thực; cần chống replay |
| **OTP qua SMS/voice** | Mã gửi tới số điện thoại | Dễ triển khai với một số nhóm người dùng | Rủi ro SIM swap, chuyển số, chặn tin, phụ thuộc mạng; không chống phishing |
| **Push authenticator** | Thiết bị thông báo yêu cầu, người dùng chấp thuận | Trải nghiệm thuận tiện | Push fatigue và phê duyệt nhầm; nên xác minh ngữ cảnh/challenge |
| **FIDO2/WebAuthn security key** | Khóa riêng ký thử thách gắn với RP/origin | Chống phishing khi triển khai và kiểm chứng đúng | Cần kế hoạch mất khóa, đăng ký dự phòng, xác thực UV khi chính sách yêu cầu |
| **Passkey nền tảng** | Khóa WebAuthn dùng trên thiết bị/đồng bộ bởi nhà cung cấp | Thuận tiện, dùng khóa bất đối xứng, chống phishing theo origin | Cần hiểu loại đồng bộ, quản lý thiết bị, recovery và đặc tính UV |
| **Smart card/chứng chỉ số** | Chứng minh sở hữu khóa riêng qua giao thức phù hợp | Có thể bảo vệ khóa bằng phần cứng, đáp ứng chính sách cao | Cần quản trị PKI, chứng chỉ, thu hồi, trình điều khiển và thiết bị |
| **Recovery code** | Mã khôi phục đã cấp khi đăng ký | Hỗ trợ khi mất authenticator chính | Phải lưu và sử dụng rất hạn chế; không xem là phương án yếu mặc định |

Không nên xếp hạng tất cả phương tiện theo một thứ tự đơn giản cho mọi trường hợp. Phải xét **mức đảm bảo cần thiết, khả năng chống phishing, bảo mật khóa, tính sẵn sàng, khả năng khôi phục, chi phí triển khai và đối tượng sử dụng**.

### 3.1. Mật khẩu

Mật khẩu là *memorized secret*. Verifier không nên lưu mật khẩu dạng rõ; cần sử dụng phương án băm mật khẩu chuyên dụng có salt và cấu hình phù hợp, đồng thời có kiểm soát thử sai và phát hiện mật khẩu bị lộ. Quy trình đặt lại mật khẩu phải xác minh đúng chủ thể, bởi kẻ tấn công thường tìm cách chiếm quyền thông qua **khôi phục tài khoản**, không chỉ qua trang đăng nhập.

Mật khẩu có thể là thành phần của MFA nhưng **không chống phishing**: người dùng vẫn có thể bị lừa nhập tại trang giả mạo.

### 3.2. OTP và push

Với TOTP, authenticator và verifier thường chia sẻ bí mật, sinh mã dựa trên thời gian. Với HOTP, mã dựa trên bộ đếm. Verifier cần kiểm soát cửa sổ chấp nhận, giới hạn số lần thử, tránh dùng lại mã và bảo vệ bí mật dùng để xác minh. Mã OTP có thể bị kẻ tấn công chuyển tiếp ngay sang trang thật nên **không được coi là phishing-resistant**.

Push phê duyệt đơn giản bằng nút “Approve” có rủi ro người dùng chấp nhận do bị làm phiền liên tục. Những biến thể yêu cầu người dùng nhập số hiển thị hoặc xác nhận ngữ cảnh đăng nhập có thể giảm phê duyệt nhầm, nhưng **không đồng nghĩa đạt khả năng chống phishing như WebAuthn**.

### 3.3. FIDO2/WebAuthn và passkey

Với WebAuthn, authenticator tạo hoặc sử dụng **cặp khóa bất đối xứng** cho một relying party (RP). RP lưu khóa công khai, còn khóa riêng được bảo vệ bởi authenticator. Khi đăng nhập, authenticator ký thử thách và dữ liệu ngữ cảnh thích hợp; RP kiểm tra chữ ký, challenge, RP ID/origin và các điều kiện chính sách.

Khả năng chống phishing xuất phát từ **ràng buộc với RP/origin và giao thức thử thách có kiểm chứng**, chứ không chỉ vì người dùng dùng vân tay. Một trang web giả mạo có origin khác không thể yêu cầu authenticator tạo bằng chứng hợp lệ cho RP thật nếu các điều kiện WebAuthn được thực thi đúng.

Passkey có thể **ràng buộc với một thiết bị** hoặc **được đồng bộ giữa các thiết bị** tùy authenticator và hệ sinh thái. Hai loại có đặc điểm vận hành và khôi phục khác nhau. Khi chính sách yêu cầu khóa nằm trong phần cứng quản lý hoặc không được sao chép, phải xác minh loại authenticator phù hợp; không dựa vào tên hiển thị “passkey”.

## 4. Luồng xác thực và vị trí của authenticator

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant Auth as Authenticator
    participant IdP as IdP / Verifier
    participant App as Ứng dụng / RP
    U->>App: Yêu cầu đăng nhập
    App->>IdP: Chuyển đến xác thực theo SSO
    IdP->>IdP: Kiểm tra account và chính sách
    IdP-->>U: Yêu cầu bằng chứng / thử thách
    U->>Auth: Mở khóa hoặc sử dụng authenticator
    Auth-->>IdP: Bằng chứng xác thực phù hợp giao thức
    IdP->>IdP: Kiểm tra bằng chứng, trạng thái và mức đảm bảo
    IdP-->>App: Kết quả xác thực / assertion
    App->>App: Kiểm tra assertion, tạo phiên
    U->>App: Yêu cầu tài nguyên
    App->>App: Kiểm tra quyền tại tài nguyên
~~~

Sơ đồ trên mô tả trách nhiệm logic, không thay thế cấu hình OIDC/SAML/WebAuthn thực tế. **Authenticator không phải access token của ứng dụng**. Một khóa FIDO2 chứng minh khả năng kiểm soát khóa ở bước đăng nhập; token và session được cấp sau đó có vòng đời riêng, cần quản trị và thu hồi riêng trong Leaver.

## 5. Ba thuộc tính bảo mật quan trọng của authenticator

### 5.1. Khả năng chống phishing

*Phishing resistance* là khả năng phương tiện và giao thức xác thực chống việc bằng chứng đăng nhập bị chuyển tiếp sang một verifier giả mạo để đăng nhập vào verifier thật. Mật khẩu, OTP và nhiều push flow không cung cấp tính chất này; WebAuthn với kiểm tra RP ID/origin đúng có thể cung cấp.

**MFA không đồng nghĩa phishing-resistant MFA.** Một chính sách chỉ kiểm tra “đã thực hiện hai bước” có thể chấp nhận mật khẩu + OTP, dù cả hai có thể bị phishing theo thời gian thực.

### 5.2. Bảo vệ bí mật hoặc khóa

Authenticator phải bảo vệ giá trị cần thiết để chứng minh quyền kiểm soát: mật khẩu, seed OTP hoặc khóa riêng. Cần đánh giá việc khóa có thể bị xuất ra, có được bảo vệ bởi phần cứng, có đồng bộ hay không, và liệu việc mất thiết bị/đồng bộ tài khoản có làm thay đổi ranh giới tin cậy.

### 5.3. Ràng buộc với đúng danh tính

Một authenticator mạnh nhưng **đăng ký nhầm cho account khác** vẫn gây sự cố nghiêm trọng. IAM cần quản trị *binding* giữa identity/account và authenticator dựa trên quy trình xác minh có thẩm quyền, lưu trạng thái và lịch sử thay đổi. Không sử dụng email hoặc tên thiết bị làm bằng chứng duy nhất rằng authenticator thuộc đúng chủ thể.

## 6. Authenticator binding: liên kết phương tiện với danh tính

**Authenticator binding** là quá trình thiết lập và ghi nhận rằng một authenticator được phép dùng để xác thực cho một account/identity cụ thể. Đây là bước nhạy cảm bởi nếu kẻ tấn công thêm được authenticator của mình vào account nạn nhân, họ có thể tiếp tục đăng nhập ngay cả khi mật khẩu đã đổi.

Một luồng enrollment điển hình:

1. **Xác minh danh tính và điều kiện khởi tạo:** HRIS hoặc nguồn bảo trợ xác nhận chủ thể; IdP/IAM liên kết đúng identity với account.
2. **Xác minh người đang yêu cầu đăng ký:** yêu cầu phiên đã xác thực ở mức phù hợp, step-up, quy trình bootstrap hoặc chứng minh danh tính ngoài băng được phê duyệt.
3. **Đăng ký authenticator:** tạo hoặc nhập thông tin cần thiết theo giao thức; với WebAuthn, nhận và kiểm tra credential public key; với TOTP, bảo vệ seed chia sẻ.
4. **Kiểm tra bằng chứng sở hữu:** authenticator phải hoàn thành thử thách xác thực/đăng ký để chứng minh có thể sử dụng.
5. **Đánh giá chính sách:** loại authenticator có được phép cho vai trò, tổ chức và mức rủi ro này không? Có yêu cầu user verification hoặc attestation không?
6. **Lưu quan hệ:** liên kết credential ID với account, loại authenticator, chính sách, trạng thái, thời điểm và nguồn phê duyệt.
7. **Thông báo và kiểm toán:** thông báo cho chủ thể về authenticator mới theo kênh phù hợp; ghi sự kiện để phát hiện thay đổi trái phép.

**Attestation** có thể được dùng trong một số triển khai để đánh giá loại hoặc thuộc tính của authenticator, nhưng không phải mọi môi trường đều yêu cầu hoặc có thể dựa vào attestation. Tránh coi việc thiếu attestation là lỗi tuyệt đối nếu chính sách cho phép authenticator không cung cấp thông tin đó.

## 7. Vòng đời authenticator: từ cấp phát đến thu hồi

Không nên xem authenticator là một thiết lập tồn tại mãi sau onboarding. Nó có vòng đời riêng, gắn với trạng thái danh tính và thiết bị.

~~~mermaid
flowchart TD
    A["Nguồn nhân sự / identity đã xác minh"] --> B["Chọn phương tiện theo chính sách"]
    B --> C["Đăng ký và binding"]
    C --> D["Xác minh sở hữu / user verification"]
    D --> E["Authenticator ACTIVE"]
    E --> F["Sử dụng và giám sát"]
    F --> G{"Có sự kiện thay đổi?"}
    G -->|"Không"| F
    G -->|"Mất thiết bị / nghi lộ"| H["Tạm khóa hoặc thu hồi"]
    G -->|"Đổi thiết bị / chính sách"| I["Đăng ký thay thế có xác minh"]
    G -->|"Mover / Leaver"| J["Đánh giá lại phạm vi và trạng thái"]
    I --> E
    J -->|"Vẫn hợp lệ"| E
    J -->|"Không còn hợp lệ"| H
    H --> K["Hủy binding, revoke phiên/token nếu cần"]
    K --> L["Đối soát và audit"]
~~~

Các trạng thái minh họa có thể là *PENDING_BINDING*, *ACTIVE*, *SUSPENDED*, *REVOKED*, *REPLACED*. Trạng thái thực tế tùy hệ thống, nhưng cần định nghĩa rõ **khi nào verifier phải từ chối** và không cho authenticator bị thu hồi tiếp tục chứng thực.

### Thay thế không đồng nghĩa tự động kế thừa sự tin cậy

Nếu nhân viên đổi điện thoại, việc xóa authenticator cũ và thêm authenticator mới phải được kiểm tra theo mức rủi ro. Không nên cho phép đổi số điện thoại hoặc thêm passkey chỉ bằng một liên kết email yếu hơn nhiều so với phương thức xác thực hiện hành mà không có biện pháp bảo vệ bổ sung.

## 8. Authenticator trong Joiner–Mover–Leaver

| Giai đoạn | Sự kiện | Việc cần thực hiện với authenticator |
| --- | --- | --- |
| **Joiner** | Danh tính mới đã xác minh, account được provision | Chọn loại phù hợp, bootstrap an toàn, binding, kiểm chứng hoạt động, lưu phương án khôi phục |
| **Mover** | Thay đổi vai trò, tổ chức, mức đặc quyền | Đánh giá lại yêu cầu MFA, phishing resistance và thiết bị; thực hiện step-up hoặc cấp authenticator thích hợp |
| **Leaver** | Quan hệ làm việc hết hiệu lực | Vô hiệu account theo chính sách, thu hồi binding/credential được tổ chức quản lý và xử lý session/token còn hiệu lực |
| **Lost/stolen** | Thiết bị thất lạc hoặc nghi bị chiếm quyền | Khóa/revoke authenticator, đánh giá phiên và token, thay thế qua quy trình xác minh |
| **Rehire** | Người cũ quay lại với quan hệ mới | Xác minh lại identity và quyền; không tự bật lại authenticator/phiên đã thu hồi |

### Joiner

Với nhân viên mới, yêu cầu “đăng ký MFA” phải đi kèm tiêu chí cụ thể: người đó có được cấp đúng loại authenticator không, đã hoàn thành bước binding chưa, có đăng nhập được theo chính sách không, và **có phải đăng ký authenticator dự phòng** không? Account tạo trước ngày nhận việc có thể được chuẩn bị nhưng phải giữ trạng thái hạn chế cho đến mốc cho phép.

### Mover

Giả sử kỹ sư chuyển sang vai trò quản trị hạ tầng sản xuất. Việc có TOTP cho tài khoản thông thường **chưa đủ để khẳng định** đã đạt chính sách mới nếu hệ thống yêu cầu authenticator chống phishing hoặc phần cứng được quản lý cho đặc quyền. Quy trình Mover phải đánh giá lại phương thức và, nếu cần, yêu cầu đăng ký bổ sung trước khi cấp quyền quản trị. Đồng thời thu hồi role và phiên có quyền cũ khi chính sách đòi hỏi.

### Leaver

Khi nhân viên nghỉ việc, khóa account IdP có thể ngăn xác thực mới, nhưng **access token, refresh token, SSO session hoặc phiên riêng ở ứng dụng** vẫn có thể còn hiệu lực. Quy trình Leaver cần xử lý các lớp đó tại nơi phát hành và nơi thực thi, đồng thời kiểm tra authenticator bị thu hồi không thể đăng nhập lại.

Nếu một người có **hai quan hệ làm việc hợp lệ** và chỉ kết thúc một quan hệ, cần tính phạm vi quyền theo từng hợp đồng/organization trước khi khóa danh tính dùng chung. Không thu hồi nhầm truy cập hợp lệ của quan hệ còn tồn tại.

## 9. MFA, chính sách rủi ro và step-up

Authenticator phù hợp phụ thuộc **mức rủi ro tài nguyên và hành động**. Đăng nhập để đọc thông tin nội bộ thông thường có thể có yêu cầu khác với việc phê duyệt thanh toán, xuất dữ liệu nhạy cảm hoặc thay đổi cấu hình sản xuất.

| Ngữ cảnh | Chính sách minh họa | Điều cần kiểm chứng |
| --- | --- | --- |
| Truy cập ứng dụng nội bộ thông thường | Authenticator được chấp thuận theo rủi ro | Đúng chủ thể, binding còn hiệu lực |
| Truy cập dữ liệu nhạy cảm | MFA, điều kiện thiết bị và phiên phù hợp | Không chỉ có claim cũ, quyền tài nguyên thực sự hợp lệ |
| Quản trị đặc quyền | Phương thức chống phishing và step-up theo chính sách | Authenticator, phiên và account đặc quyền đủ yêu cầu |
| Đăng ký authenticator mới | Step-up hoặc quy trình chứng minh danh tính phù hợp | Tránh chiếm quyền qua enrollment |
| Phục hồi khi mất mọi thiết bị | Quy trình recovery được phê duyệt, có kiểm toán | Không dùng đường tắt yếu làm vô hiệu MFA |
| Workload gọi API | Credential máy, khóa/certificate ngắn hạn hoặc cơ chế federation | Đúng workload/owner/scope, không dùng OTP của con người |

**Step-up authentication** yêu cầu xác thực bổ sung khi rủi ro hoặc hành động tăng lên. Ứng dụng có thể cần dựa vào thông tin sự kiện xác thực như thời điểm đăng nhập, mức đảm bảo hoặc phương thức đã dùng. Với OIDC, các claim như *amr*, *acr* và *auth_time* có thể hỗ trợ tùy IdP và hợp đồng tích hợp, nhưng không nên suy mức bảo đảm từ một nhãn không được định nghĩa hoặc không được xác minh.

## 10. Kiểm tra tính hợp lệ của authenticator ở verifier

### 10.1. Mật khẩu và mã OTP

Verifier cần giới hạn thử sai, xử lý sai lệch thời gian hoặc bộ đếm trong phạm vi được chấp thuận, ngăn replay mã OTP khi áp dụng và bảo vệ dữ liệu xác thực. Với mật khẩu, cần băm bằng thuật toán dành cho mật khẩu, có salt, cấu hình chi phí và chính sách bảo vệ đăng nhập phù hợp.

Trong trường hợp TOTP, mã được tạo từ một seed bí mật được chia sẻ với verifier. Nếu seed bị lộ, kẻ tấn công có thể tạo mã hợp lệ. Vì vậy, seed phải được bảo vệ trong quá trình enrollment, truyền, lưu trữ và vòng đời thay thế; không log mã QR chứa seed hoặc đưa seed vào tài liệu.

### 10.2. WebAuthn

Với WebAuthn, relying party phải kiểm tra **challenge, origin, RP ID, chữ ký, credential ID, trạng thái credential và cờ user presence/user verification khi chính sách yêu cầu**. Việc sử dụng thư viện giao thức đúng và cấu hình RP ID đáng tin cậy là quan trọng.

Không chỉ kiểm tra “chữ ký đúng” rồi bỏ qua origin/challenge: như vậy có thể làm mất tính chất chống phishing hoặc chống replay của giao thức. Cũng không đồng nhất **user presence** với **user verification**; hai tín hiệu có ý nghĩa khác nhau.

### 10.3. Chứng chỉ và khóa riêng

Nếu sử dụng thẻ thông minh hoặc chứng chỉ máy khách, verifier cần kiểm tra chuỗi tin cậy, mục đích sử dụng, thời hạn, trạng thái thu hồi khi chính sách yêu cầu và bằng chứng người/thiết bị kiểm soát khóa riêng. Một chứng chỉ chưa hết hạn vẫn có thể cần bị từ chối khi đã bị thu hồi hoặc không còn được gán cho danh tính hợp lệ.

## 11. Đăng ký và thay đổi authenticator là nghiệp vụ nhạy cảm

Các thao tác thêm, xóa hoặc đổi authenticator có thể dẫn đến chiếm đoạt tài khoản nếu kẻ tấn công thực hiện được. Vì vậy cần kiểm soát:

- **Ai có quyền thêm hoặc xóa:** chủ thể đã chứng minh quyền kiểm soát, admin được ủy quyền hoặc quy trình recovery hợp lệ.
- **Điều kiện đăng ký:** yêu cầu step-up hoặc identity proofing bổ sung khi rủi ro cao; không chỉ dựa vào phiên đăng nhập cũ đã quá lâu.
- **Thông báo thay đổi:** chủ thể được thông báo về authenticator mới, bị xóa hoặc bị thay thế qua kênh phù hợp.
- **Thời hạn an toàn:** khi phát hiện thay đổi đáng ngờ, có quy trình khóa tạm thời, điều tra và xác nhận.
- **Phân tách trách nhiệm:** người trợ giúp phục hồi không tự cấp thêm role quản trị ngoài quy trình phân quyền.
- **Bằng chứng kiểm toán:** lưu loại, thời điểm, phương thức binding, phê duyệt và trạng thái; không lưu khóa bí mật hoặc mã OTP.

Một authenticator được ghi nhận là *ACTIVE* nên có bằng chứng rằng việc đăng ký hoàn tất đúng giao thức. Bản ghi chỉ thể hiện “đã gửi link đăng ký” chưa đủ chứng minh chủ thể đã có thể sử dụng phương tiện.

## 12. Khôi phục tài khoản và mất authenticator

**Account recovery** là một phần quan trọng của vòng đời authenticator. Nếu người dùng mất điện thoại hoặc khóa bảo mật, tổ chức phải có cách cấp authenticator thay thế mà vẫn ngăn kẻ tấn công lợi dụng luồng khôi phục để vượt qua MFA.

| Tình huống | Cách xử lý đúng hướng |
| --- | --- |
| Còn authenticator dự phòng tin cậy | Dùng phương tiện dự phòng theo chính sách để xác minh và đăng ký thay thế |
| Mất thiết bị duy nhất | Áp dụng quy trình recovery/identity proofing phù hợp rủi ro, có người chịu trách nhiệm |
| Có dấu hiệu thiết bị bị đánh cắp | Khóa/revoke authenticator cũ, đánh giá phiên/token và dấu hiệu truy cập bất thường |
| Đổi số điện thoại | Không tự xem số mới là bằng chứng sở hữu account; xác minh theo chính sách |
| Khôi phục sau Leaver | Chỉ thực hiện khi có căn cứ hợp lệ và quy trình Joiner/rehire mới; không tự phục hồi quyền cũ |

**Recovery path thường là điểm yếu nếu bảo vệ kém hơn nhiều so với đăng nhập chính.** Không nên cấp lại quyền chỉ vì người gọi hỗ trợ biết họ tên, email, ngày sinh hoặc mã nhân viên. Những thông tin này có thể bị lộ hoặc dễ thu thập.

Mọi mã khôi phục, đường dẫn dùng một lần hoặc thao tác reset cần có thời hạn, giới hạn thử sai và khả năng thu hồi theo cơ chế thích hợp. Người xử lý hỗ trợ không cần biết mật khẩu, seed OTP, khóa riêng hay mã recovery của người dùng.

## 13. IdP, SSO, SCIM và liên hệ với authenticator

**IdP** thường là nơi quản lý phương thức xác thực và chính sách MFA, nhưng ứng dụng có thể có authenticator hoặc session cục bộ riêng. Trong **SSO**, ứng dụng nhận kết quả xác thực từ IdP; nó cần kiểm tra đúng issuer, audience, chữ ký, thời hạn, nonce hoặc state theo giao thức và điều kiện bảo mật của phiên.

**SCIM (System for Cross-domain Identity Management)** được dùng phổ biến để provision và deprovision user/group. **SCIM không tự định nghĩa việc đăng ký, kiểm chứng hoặc thu hồi mọi authenticator**. Một ứng dụng có thể hỗ trợ SCIM để khóa account nhưng vẫn có session, khóa API hoặc authenticator riêng cần xử lý bằng API/quy trình khác.

| Thành phần | Đóng góp cho authenticator | Giới hạn |
| --- | --- | --- |
| **HRIS / nguồn bảo trợ** | Xác nhận người, trạng thái, ngày bắt đầu/kết thúc | Không giữ bằng chứng mọi lần xác thực |
| **IAM governance** | Điều phối vòng đời, kiểm toán, chính sách theo vai trò | Cần kết quả thực tế từ IdP/ứng dụng |
| **IdP / verifier** | Binding authenticator, kiểm tra thử thách, MFA, trạng thái | Có thể không quản lý authenticator cục bộ ở SaaS |
| **SSO/OIDC/SAML** | Truyền kết quả xác thực tới ứng dụng | Không thay thế kiểm soát authorization tại tài nguyên |
| **SCIM/API provisioning** | Đồng bộ account, nhóm, trạng thái nếu hệ thống hỗ trợ | Không bảo đảm revoke token/phiên hoặc thiết bị MFA |
| **Ứng dụng / resource server** | Đánh giá session, token, quyền và chính sách | Có thể giữ session/credential riêng sau khi IdP khóa account |

Khi một người **Mover**, thuộc tính role trong IdP có thể thay đổi nhưng token SSO đã phát hành còn claim cũ. Khi **Leaver**, chặn đăng nhập ở IdP không đủ để chứng minh mọi phiên ứng dụng đã mất hiệu lực. Phải kiểm tra cơ chế refresh, revoke, session invalidation và quyền hiệu lực ở hệ thống đích.

## 14. Authenticator của service account và workload identity

Một tác vụ tự động không nên dùng điện thoại hoặc OTP của nhân viên để duy trì truy cập. **Workload identity** cần cơ chế chứng thực của máy như khóa riêng, certificate, mật khẩu máy được quản lý, client credential hoặc **federated workload identity** qua nền tảng tin cậy. Các lựa chọn và yêu cầu cụ thể phụ thuộc môi trường và chính sách.

Ví dụ, dịch vụ CI/CD triển khai Dự án Atlas cần xác thực với cloud API. Thiết kế phù hợp có thể gồm:

1. Mỗi workload/môi trường có định danh riêng và **owner team**.
2. Nền tảng chạy workload phát hành hoặc hỗ trợ credential ngắn hạn, có thể dùng federation để giảm lưu secret dài hạn.
3. Token hoặc certificate chỉ có audience, scope, role cần thiết.
4. IAM lưu quan hệ workload–organization–ứng dụng–owner và kiểm tra khi chuyển đội vận hành.
5. Khi workload ngừng hoạt động hoặc credential nghi bị lộ, thực hiện thu hồi và đối soát tại hệ thống đích.

Nếu nhân viên phụ trách workload nghỉ việc, không nhất thiết xóa ngay dịch vụ sản xuất. Cần **chuyển owner, thu hồi đặc quyền cá nhân và thay credential mà người đó có thể đã biết**, theo quy trình vận hành phù hợp. Tài khoản dịch vụ không có người chịu trách nhiệm là rủi ro tồn dư cần được rà soát.

## 15. Mô hình dữ liệu authenticator và bằng chứng kiểm toán

Hệ thống có thể lưu một bản ghi **metadata** về authenticator để quản lý vòng đời. Ví dụ JSON dưới đây chỉ dùng để minh họa, không phải schema chính thức của IdP hay FIDO2:

~~~json
{
  "authenticatorId": "auth-902",
  "identityId": "iam-id-482",
  "accountRef": "idp-account-482",
  "type": "webauthn-public-key",
  "credentialReference": "public-credential-ref-902",
  "status": "ACTIVE",
  "phishingResistant": true,
  "userVerificationRequired": true,
  "boundAt": "2026-11-23T09:30:00+07:00",
  "bindingMethod": "verified-enrollment",
  "policyVersion": "authentication-policy-v4",
  "owner": "iam-identity-482",
  "lastVerifiedAt": "2026-11-23T09:32:00+07:00"
}
~~~

Trong triển khai thực, các trường như *phishingResistant* hoặc *userVerificationRequired* phải phản ánh **khả năng và chính sách đã được kiểm chứng**, không phải nhãn do client tự khai. **Không lưu private key, TOTP seed, mã khôi phục, mật khẩu rõ hoặc token thật** trong bản ghi audit. Với WebAuthn, server thường lưu credential public key cùng metadata và trạng thái; việc lưu trữ cụ thể do thư viện và nền tảng xác thực quản lý.

Các sự kiện nên có dấu vết: bắt đầu đăng ký, hoàn thành binding, xác thực thành công/thất bại, thêm/xóa, tạm khóa, khôi phục, đổi thiết bị, revoke và kết quả sau khi thực thi. Nhật ký cần lưu timestamp, actor, client/ngữ cảnh và trạng thái, nhưng tránh thông tin sinh trắc hay bí mật có thể dùng để giả mạo.

## 16. Đối soát authenticator với danh tính và quyền

Quá trình **account reconciliation** không chỉ so sánh account trong HRIS, IdP và ứng dụng. Nó cần nhận biết authenticator có gắn với identity/account hợp lệ không và đã bị thu hồi đúng khi nguồn nhân sự thay đổi chưa.

| Sai lệch | Rủi ro | Cách kiểm tra |
| --- | --- | --- |
| Authenticator ACTIVE cho identity đã Leaver | Khả năng đăng nhập mới hoặc đường khôi phục còn tồn tại | Đối chiếu trạng thái HR, IdP, danh sách binding và app |
| Người Mover có đặc quyền nhưng chỉ có phương thức không đạt chính sách | Account quản trị thiếu xác thực phù hợp | Đánh giá role/assurance và yêu cầu enrollment/step-up |
| Một authenticator được liên kết nhầm identity | Chiếm đoạt hoặc truy cập sai người | Kiểm tra nguồn binding, identity correlation, lịch sử thay đổi |
| Không còn authenticator dự phòng | Nguy cơ khóa tài khoản, recovery khó kiểm soát | Rà soát phương án dự phòng theo chính sách |
| Authenticator bị mất nhưng vẫn ACTIVE | Kẻ khác có thể sử dụng nếu chiếm được thiết bị/khóa | Revoke, đánh giá phiên/token, đăng ký thay thế |
| Service account dựa vào credential cá nhân của Leaver | Quyền tồn dư hoặc gián đoạn khi thu hồi | Chuyển sang workload identity, quản lý owner và secret |

**Bằng chứng hoàn tất** là trạng thái tại verifier/IdP hoặc ứng dụng đích đã được đọc lại và xác minh. Một lệnh “disable authenticator” được gửi thành công chỉ chứng minh tác vụ được tiếp nhận, chưa chắc mọi node hoặc ứng dụng liên quan đã ngừng chấp nhận credential.

## 17. Những nhầm lẫn và lỗi triển khai phổ biến

### “Có OTP là chống phishing”

Không đúng. Mã OTP có thể bị kẻ tấn công chuyển tiếp ngay tới website thật. Nếu yêu cầu chống phishing, phải chọn phương thức và giao thức có tính chất tương ứng, chẳng hạn WebAuthn triển khai đúng.

### “Có vân tay là đủ MFA”

Không thể kết luận chỉ từ giao diện. Cần biết sinh trắc được dùng để mở khóa khóa riêng trên thiết bị hay chỉ là kiểm tra cục bộ, có user verification được chứng minh với verifier không và chính sách yêu cầu gì.

### “IdP đã khóa account thì không còn phiên”

Không chắc. Phiên ứng dụng, access token, refresh token và PAT có thể có vòng đời độc lập; Leaver phải kiểm tra và thu hồi theo cơ chế thực tế.

### “MFA luôn là hai màn hình nhập mã”

Không đúng. Một authenticator đa yếu tố có thể kết hợp sở hữu khóa phần cứng với PIN/sinh trắc cục bộ khi verifier kiểm chứng được thuộc tính cần thiết. Cần xét factor thực tế thay vì số lượng bước giao diện.

### “Có email khôi phục thì việc reset chắc chắn an toàn”

Không mặc nhiên. Tài khoản email có thể bị chiếm quyền; recovery phải đạt mức đảm bảo phù hợp, chống lạm dụng và có kiểm toán.

### “Mọi ứng dụng đều dùng chung MFA từ IdP”

Không chắc. Một số ứng dụng có account cục bộ, login bypass, API key hoặc đường quản trị riêng. Cần kiểm kê và bảo vệ tất cả đường xác thực, nhất là tài khoản đặc quyền.

## 18. Tình huống thực hành: chuyển vai trò và mất khóa bảo mật

**Bối cảnh:** Mai làm nhân viên phân tích với account SSO, đã đăng ký mật khẩu và TOTP. Từ ngày 01/12, Mai được điều chuyển sang nhóm vận hành cloud, có nhu cầu sử dụng quyền quản trị sản xuất. Chính sách nội bộ yêu cầu **authenticator chống phishing** cho account đặc quyền.

**Yêu cầu thứ nhất:** Mai đã có TOTP, có thể cấp quyền admin ngay không?

**Phân tích:** TOTP có thể cung cấp yếu tố bổ sung nhưng không chống phishing. IAM cần kiểm tra chính sách, yêu cầu Mai đăng ký phương tiện đáp ứng điều kiện cho account đặc quyền và xác minh binding trước khi cấp hoặc kích hoạt role admin.

**Yêu cầu thứ hai:** Mai đăng ký khóa bảo mật WebAuthn, nhưng một tuần sau làm mất khóa.

**Xử lý:** Giữ hoặc thu hồi quyền tùy chính sách rủi ro, lập tức khóa/revoke credential bị mất, kiểm tra hoạt động bất thường và các session/token còn hiệu lực; dùng authenticator dự phòng hoặc quy trình identity proofing được duyệt để đăng ký khóa mới. Không cho phép nhân viên hỗ trợ chỉ cần biết email là thêm được khóa mới vào account admin.

**Yêu cầu thứ ba:** Mai chuyển khỏi nhóm vận hành sau ba tháng.

**Xử lý:** Mover phải thu hồi role/entitlement admin và đánh giá lại nhu cầu account đặc quyền, session/token. Authenticator của account thông thường có thể tiếp tục được giữ nếu danh tính còn hợp lệ và chính sách cho phép, trong khi authenticator hoặc account riêng dành cho quản trị có thể cần bị vô hiệu hóa.

**Yêu cầu thứ tư:** Mai nghỉ việc hoàn toàn.

**Xử lý:** Leaver cần chặn đăng nhập mới, thu hồi binding thích hợp và kết thúc phiên/token tại IdP cùng ứng dụng; kiểm tra đường truy cập cục bộ và chuyển giao workload do Mai sở hữu. Một binding đã bị xóa trong IdP không tự chứng minh access token đã phát hành không còn được API chấp nhận.

## 19. Checklist thiết kế và vận hành authenticator

| Câu hỏi | Điều cần có bằng chứng |
| --- | --- |
| Authenticator thuộc loại nào và đáp ứng factor nào? | Loại phương tiện, bảo vệ khóa, yêu cầu user verification |
| Có chống phishing theo chính sách không? | Giao thức, RP/origin/challenge, cách verifier kiểm tra |
| Ai được phép đăng ký và cho identity nào? | Nguồn danh tính, bước proofing, step-up, phê duyệt |
| Binding có thành công không? | Credential ID, kết quả thử thách, trạng thái thực tế |
| Có phương án dự phòng hoặc khôi phục không? | Quy trình được duyệt, mức bảo mật phù hợp, audit |
| Có giới hạn thử sai và chống replay? | Kiểm soát tại verifier, OTP/mật khẩu/session |
| IdP và ứng dụng cục bộ có nhất quán? | Authenticator, SSO, session và MFA theo policy |
| Mover có làm thay đổi yêu cầu bảo mật? | Đánh giá lại mức đảm bảo và step-up trước khi cấp quyền |
| Leaver đã vô hiệu đúng đường truy cập? | Authenticator, account, token, phiên và quyền đích |
| Có quản trị service account/workload riêng? | Owner, credential máy, scope, thời hạn và thu hồi |
| Có lưu bí mật trong log không? | Nhật ký không chứa seed, OTP, private key hoặc token thật |
| Có đối soát và xử lý ngoại lệ? | Readback, sai lệch, owner, deadline và kết quả khắc phục |

## 20. Tổng kết

**Authenticator** là phương tiện hoặc bí mật mà chủ thể sử dụng để chứng minh quyền kiểm soát danh tính trong quá trình **authentication**. Sự an toàn không chỉ phụ thuộc loại phương tiện mạnh hay yếu, mà còn phụ thuộc **binding đúng danh tính, kiểm chứng tại verifier, khả năng chống phishing, quy trình khôi phục, quản lý phiên và thu hồi khi không còn hợp lệ**.

Trong **Joiner–Mover–Leaver**, IAM cần đăng ký authenticator đúng người khi Joiner, đánh giá lại yêu cầu MFA/phishing resistance khi Mover và vô hiệu hóa các đường xác thực, token, session liên quan khi Leaver. **HRIS** cung cấp căn cứ vòng đời; **IdP và SSO** hỗ trợ xác thực tập trung; **SCIM** hỗ trợ quản lý user/group; **RBAC/ABAC** quyết định quyền trên tài nguyên; còn workload identity và tài khoản dịch vụ cần quy trình credential riêng. Việc đối soát trạng thái tại hệ thống đích và lưu bằng chứng kiểm toán giúp giảm **quyền truy cập tồn dư**.
