# Failure path — Các nhánh thất bại trong luồng xác thực

## 1. Failure path là gì và vì sao cần thiết kế trước?

Trong một **authentication flow** (luồng xác thực), *success path* là các bước hợp lệ dẫn đến quyết định xác thực thành công. **Failure path** là những nhánh xử lý khi bằng chứng không đủ, yêu cầu không hợp lệ, điều kiện bảo mật không đạt hoặc thành phần cần thiết gặp sự cố. Ví dụ: mật khẩu sai, TOTP đã hết hạn, passkey không khớp challenge, phản hồi OIDC có issuer sai, phiên hết hạn hoặc dịch vụ xác thực tạm không sẵn sàng.

Một luồng an toàn phải xác định **kết quả và trạng thái** cho mọi nhánh thất bại, chứ không chỉ hiển thị dòng chữ “Đăng nhập thất bại”. Cần trả lời:

1. Có cấp quyền truy cập, tạo phiên hoặc nâng mức bảo đảm xác thực không?
2. Credential, challenge, OTP, mã khôi phục hoặc giao dịch đang chờ còn được phép sử dụng không?
3. Người dùng hợp lệ cần được hướng dẫn phục hồi như thế nào?
4. Server sẽ ghi log, áp dụng giới hạn thử và phát hiện tấn công ra sao?
5. Phản hồi có vô tình tiết lộ tài khoản tồn tại, yếu tố MFA đã đăng ký hoặc thông tin nhạy cảm nào không?

Đây là nội dung của chương **Authentication flow** thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Kiến thức về credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, danh tính liên kết và khôi phục tài khoản phải được áp dụng cả khi **xác thực không thành công**. Người học cần mô hình hóa đúng ranh giới tin cậy và thiết kế phản ứng trước phishing, replay, thử đăng nhập hàng loạt hoặc lỗi vận hành.

> **Bất biến quan trọng:** Không được cấp hoặc nâng quyền xác thực chỉ vì một phần của luồng đã thành công. Quyết định tạo phiên hoặc cấp token phải dựa trên **toàn bộ điều kiện bắt buộc** được kiểm chứng ở phía server.

Failure path không có nghĩa mọi lỗi đều là một cuộc tấn công. Một người dùng gõ sai mật khẩu, đồng hồ TOTP lệch hoặc mạng tạm mất kết nối là những lỗi bình thường. Thiết kế cần an toàn mà vẫn cho phép người dùng hợp lệ thử lại theo chính sách, tránh bị khóa tài khoản hàng loạt do đối thủ cố ý kích hoạt lỗi.

## 2. Phân loại thất bại theo nguyên nhân và quyết định bảo mật

| Nhóm thất bại | Ví dụ | Quyết định tối thiểu | Điều cần lưu ý |
| --- | --- | --- | --- |
| **Bằng chứng không hợp lệ** | Mật khẩu sai, OTP sai, chữ ký WebAuthn không hợp lệ. | Từ chối xác thực; không tạo phiên mới. | Ghi nhận thất bại, giới hạn số lần thử, không lộ bí mật hoặc trạng thái tài khoản. |
| **Bằng chứng không còn hợp lệ** | OTP/challenge hết hạn, token hết hạn hoặc credential đã thu hồi. | Từ chối bằng chứng đó; yêu cầu luồng mới khi cần. | Không “nới hạn” hay chấp nhận lại phản hồi cũ để cứu trải nghiệm. |
| **Sai ngữ cảnh giao thức** | OIDC sai state/nonce/issuer/audience, SAML sai recipient hoặc replay. | Chấm dứt giao dịch đăng nhập liên quan. | Không bỏ qua kiểm tra vì chữ ký hợp lệ ở một ngữ cảnh khác. |
| **Không đạt chính sách** | Thiếu MFA, mức bảo đảm thấp, tài khoản bị vô hiệu hóa. | Không cấp mức truy cập đang yêu cầu. | Có thể cho bước xác thực tăng cường khi chính sách cho phép. |
| **Lạm dụng hoặc tín hiệu rủi ro** | Credential stuffing, password spraying, nhiều yêu cầu khôi phục. | Giới hạn/tạm dừng/thách thức bổ sung theo rủi ro. | Tránh cơ chế khóa đơn giản dễ biến thành tấn công từ chối dịch vụ. |
| **Lỗi hệ thống** | Database xác thực lỗi, IdP không phản hồi, không đọc được khóa xác minh. | Không kết luận xác thực thành công khi chưa kiểm chứng. | Thông báo lỗi tạm thời, đo lường và cho thử lại có kiểm soát. |
| **Lỗi phiên hoặc quyền truy cập** | Session hết hạn, token sai audience, người dùng thiếu quyền trên tài nguyên. | Từ chối request tương ứng. | Phân biệt “chưa xác thực” với “đã xác thực nhưng không đủ quyền”. |

**Sai bằng chứng** và **lỗi hạ tầng** đều có thể làm đăng nhập không thành công, nhưng không nên xử lý giống hệt nhau ở nội bộ. Nếu database hỏng, tăng bộ đếm “mật khẩu sai” cho mọi người dùng sẽ làm xuất hiện khóa nhầm. Nếu đối tượng ký token không thể kiểm chứng do khóa tin cậy không sẵn sàng, server phải **từ chối token chưa được kiểm chứng**, đồng thời phát tín hiệu lỗi vận hành.

### Các nguyên tắc xuyên suốt

- **Fail securely / fail closed đối với quyết định xác thực:** không có bằng chứng đã xác minh thì không có quyền mới. Không có nghĩa phải xóa mọi phiên hợp lệ trước đó mỗi khi một phụ thuộc tạm lỗi; vòng đời phiên đã tồn tại được áp dụng theo chính sách riêng.
- **Phân loại lỗi nội bộ đủ rõ:** credential sai, giao thức sai, rủi ro, hết hạn, thiếu quyền và lỗi vận hành phải có mã/sự kiện riêng cho điều tra.
- **Giảm tiết lộ ở biên công khai:** không để thông điệp, status code, tốc độ phản hồi hoặc bước tiếp theo dễ dàng tiết lộ danh tính tài khoản.
- **Kết thúc/tiêu thụ giao dịch đúng cách:** thử thách đã dùng, hết hạn hoặc không còn khớp phiên không thể được tái dùng để mở đường thành công.
- **Khôi phục có kiểm soát:** cho người dùng bắt đầu một giao dịch mới hoặc dùng kênh phục hồi an toàn, không “bỏ qua bước đang lỗi”.

## 3. Mô hình trạng thái của một luồng đăng nhập

Thiết kế failure path dễ kiểm chứng hơn khi mô hình hóa đăng nhập thành **máy trạng thái** thay vì chuỗi điều kiện giao diện:

~~~mermaid
stateDiagram-v2
    [*] --> Started
    Started --> PrimaryVerified: Bằng chứng chính hợp lệ
    Started --> Rejected: Sai bằng chứng / rủi ro
    Started --> Expired: Quá hạn giao dịch
    PrimaryVerified --> AdditionalPending: Yêu cầu MFA / step-up
    PrimaryVerified --> Authenticated: Chính sách đã đủ
    AdditionalPending --> Authenticated: Yếu tố bổ sung hợp lệ
    AdditionalPending --> Rejected: Sai / vượt số lần thử
    AdditionalPending --> Expired: Quá hạn
    Started --> Unavailable: Hệ thống không xác minh được
    PrimaryVerified --> Unavailable: Phụ thuộc không sẵn sàng
    AdditionalPending --> Unavailable: Phụ thuộc không sẵn sàng
    Rejected --> [*]
    Expired --> [*]
    Unavailable --> [*]
    Authenticated --> [*]
~~~

Đây là **máy trạng thái khái niệm**, không mặc định mỗi lần nhập OTP sai đều hủy tức thì toàn bộ giao dịch. Chính sách có thể cho một số lần thử bổ sung trước khi chuyển sang \`Rejected\`. Tuy nhiên, chỉ \`Authenticated\` mới được phép dẫn đến **phiên đăng nhập thành công**.

| Trạng thái | Bảo đảm đã có | Có thể làm gì? | Chưa được làm gì? |
| --- | --- | --- | --- |
| \`Started\` | Chưa xác minh đầy đủ bằng chứng. | Nhận và kiểm tra credential ban đầu. | Cấp phiên được coi là đăng nhập. |
| \`PrimaryVerified\` | Yếu tố đầu tiên hợp lệ. | Tiếp tục các kiểm tra/challenge theo chính sách. | Dùng trạng thái này để truy cập API đã bảo vệ nếu MFA vẫn bắt buộc. |
| \`AdditionalPending\` | Cần xác minh thêm. | Gửi và kiểm tra MFA, giới hạn thử. | Nâng quyền chỉ dựa vào cờ do client gửi. |
| \`Rejected\` | Xác thực chưa đạt hoặc có vi phạm. | Ghi nhận, hướng dẫn thử lại hoặc hỗ trợ. | Tái sử dụng chứng cứ đã bị bác để tạo phiên. |
| \`Expired\` | Giao dịch đã quá hạn. | Bắt đầu giao dịch mới phù hợp. | Gia hạn ngầm để nhận challenge cũ. |
| \`Unavailable\` | Không thể quyết định an toàn vì lỗi hệ thống. | Thông báo tạm thời, cảnh báo và thử lại theo chính sách. | Tự đánh dấu “đúng” vì server xác thực đang lỗi. |
| \`Authenticated\` | Toàn bộ chính sách xác thực đã đạt. | Tạo phiên mới có phạm vi và thời hạn phù hợp. | Mặc định cho mọi quyền tài nguyên mà không kiểm tra phân quyền. |

Một **giao dịch đăng nhập đang chờ** nên ràng buộc với phiên/thiết bị khởi tạo theo cơ chế thích hợp, lưu thời hạn, số lần thử và trạng thái tiêu thụ. Không để ứng dụng client tự gửi \`state=Authenticated\` hay \`mfaPassed=true\` để điều khiển quyết định của server.

## 4. Failure path của đăng nhập bằng mật khẩu

Một luồng mật khẩu an toàn thường có ba lớp: **chống lạm dụng trước kiểm tra**, **kiểm tra verifier** và **kiểm tra chính sách sau khi mật khẩu đúng**.

~~~mermaid
flowchart TD
    A["Yêu cầu đăng nhập qua TLS"] --> B{"Vượt ngưỡng hoặc<br/>bị hạn chế theo rủi ro?"}
    B -->|"Có"| R["Hạn chế / trì hoãn<br/>ghi sự kiện phù hợp"]
    B -->|"Không"| C["Tra cứu verifier<br/>và kiểm chứng mật khẩu"]
    C --> D{"Credential hợp lệ?"}
    D -->|"Không"| F["Phản hồi thất bại chung<br/>cập nhật tín hiệu thử sai"]
    D -->|"Có"| E{"Đã đủ chính sách<br/>xác thực?"}
    E -->|"Không"| M["Tạo challenge MFA/step-up<br/>chưa cấp phiên hoàn chỉnh"]
    E -->|"Có"| S["Tạo phiên mới an toàn"]
    M --> N{"Bằng chứng bổ sung<br/>hợp lệ và còn hạn?"}
    N -->|"Có"| S
    N -->|"Không"| F
~~~

### 4.1. Sai tên tài khoản hoặc sai mật khẩu

Ứng dụng thường nên hiển thị thông điệp chung, chẳng hạn:

> Không thể đăng nhập bằng thông tin đã cung cấp. Hãy kiểm tra lại hoặc sử dụng phương thức khôi phục.

Tránh hai phản hồi công khai có thể dễ phân biệt là “không tồn tại email này” và “email tồn tại nhưng mật khẩu sai”. Việc **liệt kê tài khoản** có thể hỗ trợ phishing, credential stuffing và dò dữ liệu nhân sự. Cần kiểm soát cả sự khác biệt về thời gian xử lý, mã HTTP, dữ liệu API và các màn hình tiếp theo. Không có một phép “sleep cố định” nào bảo đảm cân bằng thời gian tuyệt đối; nên dùng thư viện kiểm chứng mật khẩu đáng tin cậy và thử nghiệm kênh phụ thực tế.

Với tài khoản không tồn tại, server có thể dùng một verifier giả hoặc cơ chế tương đương để giảm chênh lệch rõ rệt so với đường kiểm chứng mật khẩu thật; thiết kế phải cân nhắc chi phí KDF và chống DoS. **Không lưu mật khẩu thô** hoặc đưa mật khẩu, hash, token vào log.

### 4.2. Nhiều lần thử sai và hành vi tự động

Giới hạn số lần thử nên kết hợp **tài khoản, IP/mạng, tín hiệu phiên/thiết bị và mẫu chiến dịch**. Một giới hạn theo IP đơn lẻ có thể chặn người dùng cùng mạng NAT; một giới hạn theo tài khoản đơn lẻ có thể bị kẻ tấn công lợi dụng để khóa tài khoản của nạn nhân.

Các biện pháp có thể chọn theo rủi ro: tăng độ trễ, rate limit, challenge bổ sung, tạm chặn theo thời gian, cảnh báo hoặc quy trình lấy lại quyền truy cập. Cần có **giới hạn chia sẻ giữa nhiều instance** và cơ chế quan sát các đợt thử phân tán. Thông báo cho client có thể dùng phản hồi chờ/giới hạn phù hợp, nhưng vẫn tránh tiết lộ thông tin tài khoản chưa công khai.

### 4.3. Mật khẩu đúng nhưng MFA bắt buộc

Đây **chưa phải success path**. Server chỉ ghi nhận rằng yếu tố chính đã hợp lệ, tạo giao dịch MFA ngắn hạn và chờ bước bổ sung. Nếu OTP sai, quá hạn hoặc vượt giới hạn, hệ thống không cấp phiên đã xác thực. Việc nhận cookie/ID giao dịch tạm để giữ trạng thái MFA **không được** coi là bằng chứng đủ để gọi API bảo vệ hoặc thay đổi credential.

Nếu ứng dụng có sẵn phiên **mức bảo đảm thấp** và người dùng đang thực hiện step-up cho một thao tác nhạy cảm, failure path thường phải **từ chối nâng quyền/thao tác đó**. Có thể vẫn giữ phiên cơ sở đang hợp lệ theo chính sách; không nên tự động coi mọi lần nhập sai MFA là lý do xóa toàn bộ tài khoản.

## 5. Failure path của MFA, OTP và xác thực theo rủi ro

| Tình huống | Quyết định đúng | Phản hồi có ích |
| --- | --- | --- |
| TOTP không khớp | Từ chối bước MFA, ghi nhận một lần thử. | Nhắc người dùng kiểm tra mã đang hiển thị; cho thử lại khi còn lượt. |
| TOTP hết hạn hoặc lệch thời gian ngoài cửa sổ cho phép | Không chấp nhận mã cũ. | Hướng dẫn đồng bộ đồng hồ và lấy mã mới. |
| TOTP đã được chấp nhận trước đó trong cùng cửa sổ | Xử lý chống replay theo chính sách; tránh chấp nhận mã dùng lại. | Yêu cầu mã mới nếu phù hợp, không tiết lộ secret. |
| OTP gửi qua SMS/email không đến | Không mặc định hoàn thành MFA. | Cho yêu cầu gửi lại có giới hạn; mã cũ được xử lý theo chính sách rõ ràng. |
| Push notification bị từ chối | Từ chối bước chờ hoặc kết thúc giao dịch. | Thông báo yêu cầu chưa được duyệt; giúp người dùng báo cáo nếu không tự yêu cầu. |
| Quá nhiều yêu cầu push/OTP | Hạn chế gửi hoặc yêu cầu xác minh qua kênh khác. | Tránh *MFA fatigue*, spam và chi phí gửi mã. |
| Mất thiết bị MFA | Không bỏ qua bước MFA chỉ vì người dùng tuyên bố mất thiết bị. | Chuyển sang mã khôi phục hoặc quy trình phục hồi đủ mạnh. |
| Tín hiệu đăng nhập rủi ro cao | Yêu cầu kiểm chứng tăng cường hoặc chặn theo chính sách. | Giải thích có kiểm soát; không công bố quy tắc phát hiện chi tiết. |

**MFA fatigue** là tình huống kẻ tấn công liên tục phát yêu cầu xác thực đẩy đến thiết bị của nạn nhân, hy vọng nạn nhân bấm “Đồng ý” do mệt mỏi hoặc nhầm lẫn. Failure path phải giảm/giới hạn số yêu cầu, bảo vệ người bị làm phiền và cho phép báo cáo hoạt động không do mình khởi tạo. Sử dụng **number matching** hoặc cơ chế xác nhận ý định phù hợp có thể giảm nhầm lẫn; đối với khả năng chống phishing mạnh, passkey/WebAuthn được triển khai đúng là lựa chọn đáng cân nhắc.

**OTP hết hạn không nên được “cho qua” vì người dùng gần nhập kịp.** Server cần cửa sổ xác thực rõ ràng, chính sách chống replay và số lần thử phù hợp. Tính hữu dụng được xử lý bằng việc cho tạo challenge/mã mới, không phải chấp nhận bằng chứng không hợp lệ.

## 6. Failure path của passkey/WebAuthn và chứng chỉ

### 6.1. Passkey/WebAuthn

WebAuthn dùng thử thách (*challenge*) do RP tạo và bằng chứng mật mã do authenticator cung cấp. Đăng ký credential (\`webauthn.create\`) và đăng nhập (\`webauthn.get\`) có kiểm tra khác nhau; phản hồi chỉ được chấp nhận nếu khớp **giao dịch, RP ID, origin, loại ceremony, chính sách user presence/user verification** và các điều kiện chữ ký/attestation tương ứng.

| Thất bại | Điều server cần làm |
| --- | --- |
| Người dùng hủy hộp thoại passkey hoặc không có authenticator phù hợp | Không tạo phiên; cho người dùng thử lại hoặc chọn phương thức hợp lệ khác. |
| Challenge sai, quá hạn hoặc đã dùng | Từ chối; không dùng lại giao dịch cũ để tạo thành công. |
| Origin hoặc RP ID hash không khớp | Từ chối bằng chứng; ghi nhận lỗi giao thức hoặc dấu hiệu tấn công. |
| Chữ ký assertion không hợp lệ với khóa công khai đã đăng ký | Từ chối xác thực; không cập nhật phiên như thành công. |
| Credential ID không thuộc tài khoản/không còn hoạt động | Từ chối hoặc xử lý theo luồng đăng nhập và khám phá credential đã thiết kế; không tự liên kết sang tài khoản khác. |
| Thiếu cờ user verification khi chính sách yêu cầu | Không xem như đã đạt mức bảo đảm cần thiết. |
| Attestation đăng ký không đạt chính sách thiết bị | Không kích hoạt credential; thông báo cách đăng ký authenticator được hỗ trợ. |

Với **passkey đồng bộ**, signature counter có thể bằng 0 hoặc không tăng như khóa phần cứng truyền thống. Không nên coi mọi trường hợp counter không tăng là bằng chứng chắc chắn có tấn công; thư viện và chính sách phải xử lý phù hợp đặc tính authenticator.

**Phân biệt lỗi bảo mật với thao tác người dùng:** \`NotAllowedError\` trên trình duyệt có thể xảy ra do người dùng hủy hoặc hết thời gian; server vẫn phải kiểm chứng nếu có phản hồi, còn UX có thể đưa cách thử lại. Một phản hồi có **origin sai** là vi phạm ngữ cảnh không thể “thử nhận thêm” hoặc bỏ kiểm tra để khắc phục UX.

### 6.2. Chứng chỉ và mTLS

Khi dùng **chứng chỉ máy khách**, việc xác thực có thể thất bại vì chứng chỉ hết hạn, chuỗi CA không hợp lệ, mục đích sử dụng không phù hợp, trạng thái thu hồi không đạt chính sách hoặc client không chứng minh được quyền kiểm soát khóa riêng. Không được chỉ đọc chuỗi tên \`CN\` trong chứng chỉ rồi coi như người dùng đã xác thực.

Nếu dịch vụ kiểm tra trạng thái chứng chỉ không sẵn sàng, xử lý **fail-open hay fail-closed** phụ thuộc chính sách tin cậy và yêu cầu của hệ thống; đối với quyền truy cập yêu cầu kiểm tra thu hồi thành công, phải từ chối khi không thể kiểm tra. Cần thiết kế đường xử lý sự cố vận hành, quản lý xoay vòng chứng chỉ và khả năng thay thế credential hợp lệ.

## 7. Failure path của đăng nhập liên kết OIDC/SAML

Trong **federated identity**, ứng dụng (RP/SP) tin kết quả xác thực của IdP **chỉ sau khi kiểm tra thông điệp theo giao thức đã cấu hình**. Failure path phải bao phủ cả việc IdP từ chối đăng nhập lẫn phản hồi có vấn đề.

### 7.1. OIDC Authorization Code Flow

| Thất bại | Cách xử lý |
| --- | --- |
| Người dùng hủy đăng nhập ở IdP, IdP trả \`access_denied\` | Kết thúc giao dịch; hiển thị đăng nhập đã hủy, cho thử lại. |
| \`state\` sai hoặc không khớp giao dịch | Từ chối callback; không đổi code thành phiên đăng nhập. |
| Callback thuộc issuer/IdP khác với bên đã chọn | Từ chối để tránh *mix-up* giữa các IdP. |
| Authorization code hết hạn, đã dùng hoặc PKCE verifier sai | Không cấp phiên; bắt đầu giao dịch mới sau khi xác định lỗi. |
| Token endpoint lỗi, timeout hoặc không phản hồi | Không suy đoán ID token hợp lệ; ghi nhận lỗi phụ thuộc, cho retry an toàn khi phù hợp. |
| ID token có chữ ký sai, \`iss\`, \`aud\`, \`exp\` hoặc \`nonce\` không khớp | Từ chối token; không dùng thông tin danh tính trong payload để tạo phiên. |
| Claim danh tính hợp lệ nhưng account nội bộ không được phép đăng nhập | Không cấp phiên; thực thi chính sách account/tenant và xử lý provisioning theo luồng riêng. |

**PKCE** ràng buộc authorization code với bên đã bắt đầu giao dịch, còn **state** bảo vệ ràng buộc callback với trạng thái đăng nhập. **Nonce** (khi dùng trong OIDC) được kiểm tra theo ID token. Chúng bổ sung lẫn nhau và không thể dùng một giá trị để tùy tiện bỏ qua các kiểm tra khác.

Khi IdP không truy cập được hoặc thông tin khóa ký (JWKS) chưa được lấy/xác minh đáng tin cậy, RP không được “chấp nhận ID token tạm” hoặc lấy khóa từ bất kỳ URL do token tự khai. Nếu đã có khóa tin cậy được quản lý theo chính sách cache/quay vòng, hệ thống có thể dùng chúng trong giới hạn cho phép; điều này khác với bỏ kiểm tra chữ ký.

**Chú ý:** ID token dùng để xác thực danh tính với RP; access token dùng để gọi tài nguyên được cấp quyền. Không giải mã một access token bất kỳ rồi xem đó là ID token để né lỗi OIDC.

### 7.2. SAML Web Browser SSO

SP cần xác minh chữ ký tin cậy cùng các ràng buộc như issuer, audience, recipient/destination, điều kiện thời gian, **InResponseTo** khi phù hợp, và trạng thái chống replay của assertion/response.

Những failure path quan trọng:

- SAML Response hoặc Assertion hết hạn, sai audience hoặc gửi tới ACS không được cấu hình: **từ chối**.
- Chữ ký không hợp lệ, không đúng tài liệu/đối tượng được ứng dụng đọc, hoặc chứng chỉ ký không tin cậy: **từ chối**. Dùng thư viện xử lý XML Signature đáng tin cậy để tránh lỗi như *XML signature wrapping*.
- Assertion/response đã xử lý được gửi lại: **từ chối replay**.
- Trong luồng **IdP-initiated**, có thể không có AuthnRequest/InResponseTo để đối chiếu; SP phải có **chính sách chấp nhận riêng** và các kiểm soát bù trừ, thay vì giả định nó giống SP-initiated.
- IdP trả trạng thái lỗi hoặc người dùng chưa xác thực: không cấp phiên.

Với cả OIDC và SAML, **chữ ký hợp lệ chưa đủ** nếu bằng chứng dành cho một ứng dụng khác, issuer khác, tenant khác hoặc giao dịch cũ. Failure path phải ngăn việc dùng bằng chứng sai ngữ cảnh.

## 8. Thất bại của phiên, token và phân quyền sau đăng nhập

Luồng xác thực không chấm dứt về mặt bảo mật ngay sau khi hiển thị trang chủ. Khi một yêu cầu tới API xuất hiện, server vẫn cần xác thực phiên/token và kiểm tra quyền:

| Tình huống | Phản hồi phổ biến | Hành vi phía server |
| --- | --- | --- |
| Chưa có phiên hoặc token hợp lệ | HTTP \`401 Unauthorized\` cho API cần xác thực. | Không phục vụ tài nguyên; client có thể chuyển tới đăng nhập. |
| Token/phiên hết hạn hoặc bị thu hồi | HTTP \`401\` khi cần xác thực lại. | Không tự gia hạn ngoài chính sách; xử lý refresh theo cơ chế được cấp phép. |
| Token sai chữ ký, issuer hoặc audience | HTTP \`401\` hoặc lỗi xác thực phù hợp. | Từ chối token; tuyệt đối không chỉ decode payload rồi tin. |
| Đã xác thực nhưng không được phép truy cập tài nguyên | HTTP \`403 Forbidden\` thường phù hợp. | Không tiết lộ dữ liệu; có thể trả \`404\` nếu chính sách che sự tồn tại tài nguyên. |
| Yêu cầu thao tác nhạy cảm thiếu xác thực gần đây | Thách thức step-up hoặc lỗi nghiệp vụ theo API. | Không thực hiện thao tác cho đến khi đủ mức bảo đảm. |
| Refresh token bị phát hiện dùng lại sau rotation | Từ chối; đánh giá khả năng token bị đánh cắp. | Có thể thu hồi họ token/phiên liên quan theo chính sách; cảnh báo. |

Các mã HTTP trên là **gợi ý phổ biến**, không thay thế chính sách API hoặc cấu trúc thông điệp chuẩn của OAuth/OIDC khi áp dụng. Đừng tự bịa rằng \`403\` nghĩa là tài khoản có tồn tại trong mọi tình huống.

### Bảo vệ ranh giới phiên trong failure path

- **Không tạo phiên đủ quyền trước khi hoàn tất MFA**; “đăng nhập một nửa” chỉ được lưu ở trạng thái hạn chế trên server.
- **Không tin token chỉ vì cú pháp JWT hợp lệ.** Phải kiểm tra chữ ký, issuer, audience, thời hạn và các claim liên quan với bối cảnh.
- **Không dùng bearer token bị lỗi để kích hoạt thao tác phục hồi tự động.** Quy trình làm mới token phải xác minh refresh token riêng và chống lạm dụng.
- **Không cho phép API bỏ qua phân quyền khi dịch vụ phân quyền gặp lỗi.** Có thể trả lỗi tạm thời thay vì mở rộng quyền.
- **Không để lỗi đăng nhập mới xóa nhầm phiên hợp lệ khác** nếu chính sách không yêu cầu; chỉ thu hồi mạnh tay khi có căn cứ rủi ro hoặc sự cố.

Đối với trình duyệt dùng cookie, cần tiếp tục bảo vệ CSRF khi phù hợp, giới hạn phạm vi cookie, dùng \`Secure\`, \`HttpOnly\`, \`SameSite\` theo thiết kế, và có khả năng thu hồi ở server. Một yêu cầu sai CSRF token phải **không gây thay đổi trạng thái**, dù cookie phiên hợp lệ.

## 9. Thất bại trong khôi phục và thay đổi credential

**Recovery flow** là một con đường xác thực thay thế: nếu quá dễ, nó sẽ phá hỏng bảo vệ của đăng nhập chính. Các nhánh thất bại phải được xây dựng sẵn:

1. **Tài khoản không tồn tại:** trả thông điệp chung như “Nếu có tài khoản phù hợp, chúng tôi sẽ gửi hướng dẫn” để hạn chế dò email.
2. **Gửi yêu cầu quá nhiều lần:** giới hạn tần suất gửi email/SMS và thử mã; tránh biến dịch vụ thành công cụ spam.
3. **Mã reset sai, hết hạn hoặc dùng lại:** từ chối và hướng dẫn bắt đầu luồng mới; không gia hạn token cũ một cách ngầm định.
4. **Bằng chứng khôi phục hợp lệ nhưng thao tác không còn đúng ngữ cảnh:** chẳng hạn mật khẩu đã được đổi, account bị vô hiệu hóa hoặc token thuộc giao dịch khác; từ chối hoặc yêu cầu quy trình phù hợp.
5. **Đổi mật khẩu hoặc thêm authenticator thất bại giữa chừng:** không kích hoạt credential chưa xác minh; không để trạng thái nhập nhằng khiến yếu tố cũ bị xóa trước khi yếu tố mới dùng được.
6. **Người dùng mất mọi yếu tố MFA/passkey:** chuyển sang mã phục hồi đủ mạnh hoặc quy trình hỗ trợ được kiểm soát; không bỏ qua xác minh vì người dùng tự khai mất thiết bị.

Ví dụ đăng ký TOTP: **hiển thị QR thành công nhưng người dùng chưa nhập mã đúng** chỉ đạt trạng thái **pending**. Server không được đánh dấu MFA đã bật, vì chưa có bằng chứng người dùng sở hữu secret trên authenticator. Ngược lại, nếu người dùng thoát giữa chừng, record pending cần hết hạn và được dọn dẹp theo chính sách, không biến thành credential hoạt động.

Tương tự, một lần **đăng ký passkey** trả lỗi challenge hoặc origin phải không tạo binding; việc ghi credential ID/khóa công khai chỉ diễn ra sau khi WebAuthn registration response được kiểm chứng đầy đủ.

## 10. Thiết kế phản hồi: an toàn, dễ hiểu và có thể phục hồi

Phản hồi failure path có **ba đối tượng khác nhau**: người dùng cần biết bước tiếp theo; client cần tín hiệu xử lý; đội vận hành cần nguyên nhân đủ để điều tra. Không nhất thiết trả nguyên nhân nội bộ chi tiết cho tất cả bên.

| Lỗi nội bộ | Thông điệp công khai gợi ý | Hành động tiếp theo |
| --- | --- | --- |
| Username hoặc mật khẩu không hợp lệ | “Không thể đăng nhập bằng thông tin này.” | Kiểm tra lại hoặc dùng quên mật khẩu. |
| OTP sai | “Mã chưa hợp lệ. Hãy kiểm tra và thử lại.” | Thử mã hiện tại khác còn hiệu lực, trong giới hạn. |
| OTP/challenge hết hạn | “Phiên xác minh đã hết hạn.” | Yêu cầu thử thách mới. |
| Passkey bị hủy | “Bạn đã hủy bước xác thực bằng passkey.” | Chọn thử lại hoặc phương thức được hỗ trợ. |
| Tài khoản bị hạn chế do nhiều lần thử | “Hiện không thể tiếp tục thử đăng nhập. Hãy thử lại sau hoặc liên hệ hỗ trợ.” | Tuân theo thời gian chờ, kênh hỗ trợ an toàn. |
| IdP hoặc hệ thống phụ thuộc không sẵn sàng | “Dịch vụ đăng nhập đang gặp sự cố tạm thời.” | Thử lại sau hoặc theo chỉ dẫn trạng thái dịch vụ. |
| Callback OIDC sai state/issuer | “Không thể hoàn tất đăng nhập. Hãy bắt đầu lại.” | Khởi tạo luồng mới; nội bộ log mã lỗi giao thức. |
| Token/phiên hết hạn | “Phiên đăng nhập đã hết hạn.” | Đăng nhập lại hoặc refresh hợp lệ. |

**Không phải lúc nào mọi lỗi cũng phải hiển thị y hệt nhau.** Với một giao dịch MFA đã được khởi tạo hợp lệ, có thể cho thông báo “mã chưa hợp lệ” để người dùng sửa. Với bước yêu cầu nhập username công khai, thường nên tránh phân biệt “không có tài khoản” và “sai mật khẩu”. Quyết định phụ thuộc vào **mức độ thông tin được phép tiết lộ ở trạng thái hiện tại**.

### Mẫu phản hồi API

~~~json
{
  "error": "authentication_failed",
  "message": "Không thể hoàn tất đăng nhập bằng thông tin đã cung cấp.",
  "request_id": "req-example-123"
}
~~~

\`request_id\` giúp bộ phận hỗ trợ tra log đã kiểm soát, không phải token cho phép truy cập dữ liệu. Phản hồi công khai **không** nên kèm password hash, secret, token, chi tiết khóa ký, tên người dùng được tra ra, quy tắc chấm điểm rủi ro hoặc stack trace.

Để tránh người dùng bấm gửi nhiều lần vì không thấy phản hồi, giao diện có thể vô hiệu hóa nút gửi khi request đang chạy, hiển thị trạng thái xử lý và cho thử lại sau timeout. Tuy nhiên, **vô hiệu hóa nút chỉ là UX**: server vẫn phải thực hiện chống lạm dụng và quản lý các yêu cầu trùng lặp.

## 11. Timeout, retry và thất bại từng phần

Một luồng xác thực có thể gặp lỗi sau khi đã thực hiện một phần công việc: IdP đã cấp authorization code nhưng RP timeout khi đổi code; server đã xác minh OTP nhưng kết nối ngắt trước khi trả kết quả; hệ thống đã ghi phiên nhưng client chưa nhận cookie.

Các nguyên tắc xử lý:

- **Phân biệt retry request và replay bằng chứng.** Cho người dùng bắt đầu giao dịch mới không có nghĩa cho phép sử dụng lại authorization code, OTP, challenge hoặc recovery token đã tiêu thụ.
- **Giới hạn retry có backoff.** Không tạo vòng lặp request gây quá tải IdP hoặc dịch vụ gửi mã; không tự động thử lại hành động tạo credential nhạy cảm mà thiếu kiểm tra trạng thái.
- **Quản lý trạng thái nguyên tử hoặc có điểm commit rõ ràng.** Khi cấp phiên hoặc gắn credential, tránh trường hợp “đã cấp nhưng chưa ghi” hoặc “đã báo thành công nhưng chưa thực sự lưu”.
- **Thiết kế xử lý sự kiện trùng (idempotency) đúng mục đích.** Idempotent response không đồng nghĩa chấp nhận lại bằng chứng dùng một lần. Có thể kiểm tra kết quả của một giao dịch đã commit mà không tạo thêm phiên/quyền mới.
- **Giới hạn thời hạn pending.** Giao dịch dang dở phải hết hạn và không thể được nâng cấp thành thành công bằng một request ngoài ngữ cảnh.
- **Đặt timeout và tài nguyên giới hạn.** Tránh để request treo vô hạn, giữ khóa database lâu hoặc tạo nhiều pending transaction theo một tài khoản.

**Ví dụ:** người dùng bấm gửi OTP, server đã xác minh đúng và commit giao dịch thành công nhưng phản hồi bị mất trên mạng. Nếu người dùng gửi lại cùng OTP, server không nên “mở” một giao dịch mới dựa trên cùng mã đã dùng. Hệ thống có thể kiểm tra giao dịch đã hoàn thành qua một cơ chế an toàn được thiết kế trước, hoặc yêu cầu đăng nhập lại. Điều quan trọng là **không tạo phiên hoặc cấp quyền nhiều lần chỉ vì retry**.

## 12. Mã giả: xử lý nhánh lỗi tập trung theo trạng thái

Ví dụ dưới đây mô tả việc giữ bất biến bảo mật khi xác thực bằng mật khẩu và MFA. Đây là **mã giả để học kiến trúc**, không phải đoạn mã có thể chép trực tiếp vào production.

~~~text
authenticate(request, context):
    tx = newLoginTransaction(context)
    try:
        if abusePolicy.denies(request, context):
            audit("login_restricted", tx.id, safeMetadata)
            return publicFailure("temporarily_restricted")

        verifier = lookupPasswordVerifier(request.identifier)
        primaryOk = verifyPasswordSafely(verifier, request.password)
        // Không tiết lộ khác biệt giữa tài khoản không tồn tại và mật khẩu sai.
        if not primaryOk:
            updateAbuseSignals(request, context)
            tx.reject("primary_invalid")
            audit("login_failed", tx.id, safeMetadata)
            return publicFailure("authentication_failed")

        tx.markPrimaryVerified()
        if policy.requiresMfa(tx.account, context):
            tx.markAdditionalPending()
            return issueRestrictedMfaChallenge(tx)
            // Không tạo session được phép gọi API đã bảo vệ.

        return finalizeLogin(tx)
    catch TrustedDependencyUnavailable:
        tx.markUnavailable()
        audit("login_unavailable", tx.id, safeMetadata)
        return publicFailure("temporarily_unavailable")

verifyMfaAndFinish(txId, response, context):
    tx = loadPendingLoginTransaction(txId)
    require tx.belongsToContext(context)
    require tx.state == "additional_pending"
    require tx.notExpired
    require tx.attemptsRemaining

    if not verifyMfaProofAndReplayPolicy(tx, response):
        tx.recordFailedAttemptAtomically()
        audit("mfa_failed", tx.id, safeMetadata)
        return publicFailure("mfa_failed")

    return finalizeLogin(tx)

finalizeLogin(tx):
    require tx.allRequiredFactorsVerified
    require tx.account.active
    require policy.allowsLogin(tx.account, tx.authenticationContext)
    atomically:
        consumeTransactionOnce(tx)
        session = createNewSession(tx.account.id, tx.assuranceLevel)
    audit("login_succeeded", tx.id, safeMetadata)
    return protectedSessionResponse(session)
~~~

Để triển khai thực tế cần giải quyết thêm sự đồng thời giữa các request, kiểm tra phiên/trạng thái khi dùng cookie, CSRF, lưu transaction an toàn, định dạng lỗi theo API và thư viện kiểm chứng mật khẩu/MFA. \`finalizeLogin\` không được tin các giá trị “đã xác minh MFA” do client gửi; chúng phải phát sinh từ kết quả server đã kiểm tra. Bộ đếm thử sai và thao tác tiêu thụ một lần phải hoạt động thống nhất trên nhiều instance.

### Ví dụ nhánh fail-closed đối với token

~~~text
authorizeApiRequest(request):
    token = extractTokenSafely(request)
    if token == null:
        return 401

    verification = verifySignatureIssuerAudienceLifetime(token)
    if verification.invalid:
        audit("invalid_token", safeMetadata)
        return 401
    if verification.cannotBeCompletedSafely:
        audit("token_verification_unavailable", safeMetadata)
        return controlledUnavailableResponse()

    subject = verification.trustedSubject
    if not permissionPolicy.canAccess(subject, request.resource, request.action):
        audit("access_denied", safeMetadata)
        return 403

    return performAuthorizedOperation()
~~~

Phân biệt \`invalid\` và \`cannotBeCompletedSafely\` giúp theo dõi lỗi chứng thực với sự cố hạ tầng. **Cả hai đều không được mở quyền truy cập**. Nếu dùng JWT, phần kiểm chứng phải dựa vào khóa/thuật toán được tin cậy theo cấu hình; không dựa trên URL hoặc tùy chọn kiểm chứng do token chưa tin cậy tự cung cấp.

## 13. Log, cảnh báo và hỗ trợ điều tra

Một failure path khó vận hành nếu chỉ ghi “login failed” cho mọi trường hợp. Nội bộ nên phân loại sự kiện có thể phân tích và liên kết chúng bằng **request ID/transaction ID** đã kiểm soát.

| Sự kiện nội bộ | Ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| \`primary_invalid\` | Bằng chứng đăng nhập ban đầu sai. | Quan sát mẫu thử sai theo tài khoản/nguồn, không báo động mỗi lần cá nhân nhập nhầm. |
| \`mfa_failed\` | Yếu tố bổ sung chưa đạt. | Theo dõi số lần thử, dấu hiệu MFA fatigue hoặc phishing. |
| \`challenge_replay\` | Challenge, code hoặc giao dịch đã dùng được gửi lại. | Điều tra replay, retry lỗi hoặc vấn đề đồng thời. |
| \`federation_validation_failed\` | Sai issuer, audience, state, nonce, chữ ký hoặc điều kiện assertion. | Điều tra cấu hình IdP/RP, nguy cơ mix-up hoặc tấn công. |
| \`login_restricted\` | Bị giới hạn theo chính sách chống lạm dụng. | Đo false positive, chiến dịch dò quét và tác động UX. |
| \`auth_dependency_unavailable\` | Không thể xác thực vì phụ thuộc hỏng. | Cảnh báo vận hành; không cộng vào thống kê “mật khẩu sai”. |
| \`session_invalid\` | Phiên/token hết hạn, sai hoặc bị thu hồi. | Theo dõi bất thường và chất lượng quản lý phiên. |

Log cần đủ ngữ cảnh như thời gian, loại giao dịch, tài khoản/tenant khi việc ghi nhận được phép, nguồn/ngữ cảnh đã tối thiểu hóa, kết quả và ID tương quan. **Không ghi mật khẩu, OTP, mã reset, seed TOTP, authorization code, bearer token, session cookie, khóa riêng hay toàn bộ dữ liệu định danh không cần thiết.** Những sự kiện nhạy cảm phải có chính sách bảo vệ và thời hạn lưu log.

Các chỉ số thực tế cần đo:

- Tỷ lệ thất bại phân loại theo **sai credential, sai MFA, lỗi giao thức, bị giới hạn và lỗi hạ tầng**.
- Số chiến dịch credential stuffing/password spraying bị phát hiện và tác động tới tài khoản thật.
- Tỷ lệ người dùng hợp lệ hoàn thành đăng nhập/khôi phục, tỷ lệ khóa nhầm và số lượt gửi OTP không thành công.
- Số trường hợp callback OIDC/SAML bị từ chối do sai ràng buộc hoặc replay, sau khi loại bỏ nhiễu vận hành.
- Thời gian phát hiện và khắc phục sự cố IdP/token verification, cùng khả năng thu hồi phiên khi phát hiện xâm phạm.

Chỉ số thất bại **tăng** có thể do hệ thống chặn được nhiều tấn công hơn hoặc do người dùng bị lỗi trải nghiệm; luôn phân tích cùng ngữ cảnh thay vì kết luận từ một con số đơn lẻ.

## 14. Kiểm thử có hệ thống các failure path

Nên thiết kế bộ kiểm thử bắt đầu từ **bất biến**: không có session trước khi đủ yếu tố; challenge chỉ dùng đúng ngữ cảnh; API không cấp tài nguyên khi token không hợp lệ; khôi phục không bỏ qua xác minh. Bảng dưới là tập tình huống hữu ích:

| Tình huống kiểm thử | Kết quả phải quan sát được |
| --- | --- |
| Nhập username không tồn tại hoặc mật khẩu sai | Không có phiên; phản hồi công khai hạn chế liệt kê tài khoản; log phân loại được nội bộ. |
| Mật khẩu đúng nhưng MFA sai, hủy hoặc hết hạn | Không tạo phiên đăng nhập đầy đủ; giới hạn số lần thử và kết thúc giao dịch khi cần. |
| Phát lại OTP/challenge đã dùng | Không được cấp thêm quyền dựa trên bằng chứng cũ. |
| Gửi đồng thời hai yêu cầu hoàn tất cùng giao dịch | Tối đa một kết quả commit theo chính sách; không tạo liên kết hoặc phiên ngoài kiểm soát. |
| WebAuthn sai challenge, origin, RP ID, chữ ký hoặc thiếu UV bắt buộc | Từ chối; không tạo phiên hoặc credential binding. |
| OIDC callback sai state, issuer, audience, nonce hoặc code hết hạn | Từ chối; không tạo phiên và không lấy claim chưa xác minh làm danh tính. |
| SAML assertion bị phát lại, quá hạn hoặc dành cho SP khác | Từ chối theo chính sách và kiểm tra ràng buộc. |
| Database/IdP/JWKS gặp lỗi kiểm chứng | Không phát sinh “thành công” giả; trả lỗi tạm thời và ghi cảnh báo. |
| Token JWT hết hạn, sai chữ ký hoặc sai audience | API từ chối truy cập; không chỉ decode payload rồi tin. |
| Session hợp lệ nhưng thiếu quyền | Từ chối tài nguyên/thao tác, không lộ dữ liệu. |
| Reset token hết hạn hoặc dùng lần hai | Từ chối reset; không đổi credential. |
| Tài khoản bị thử sai liên tục từ nhiều IP | Chống lạm dụng có tác dụng nhưng không khóa nhầm vô hạn mọi người cùng mạng. |

### Cách suy luận bằng kịch bản

**Kịch bản 1 — MFA bị bỏ qua do sai trạng thái:** Ứng dụng đặt \`logged_in=true\` ngay sau khi kiểm tra mật khẩu, rồi mới điều hướng sang màn hình OTP. Người dùng gọi trực tiếp API bằng cookie đã cấp. Đây là lỗi thiết kế vì **nhánh chờ MFA đã được nâng thành phiên thành công**. Sửa ở nơi tạo session và middleware kiểm tra mức bảo đảm, thay vì chỉ ẩn nút giao diện.

**Kịch bản 2 — IdP bị gián đoạn:** OIDC RP nhận authorization code hợp lệ về mặt cú pháp nhưng token endpoint timeout. Nếu RP dùng một claim email lấy từ query string để “cho người dùng vào tạm”, kẻ tấn công có thể giả mạo danh tính. Phải giữ giao dịch chưa hoàn thành và báo lỗi tạm thời; không cấp phiên.

**Kịch bản 3 — Nạn nhân bị khóa qua password spraying:** Kẻ tấn công cố ý nhập sai mật khẩu cho nhiều tài khoản làm chúng bị khóa vĩnh viễn. Rate limit và cảnh báo cần phối hợp chống thử tự động với phương án khôi phục hợp lệ, không tạo điều kiện cho một cuộc tấn công từ chối dịch vụ rẻ tiền.

**Kịch bản 4 — Bấm lại vì timeout:** Người dùng đã gửi mã khôi phục đúng, nhưng mạng bị ngắt sau khi server ghi mật khẩu mới. Request được gửi lại với cùng mã. Server không được tạo thêm hiệu lực dùng lại mã một lần; cần xử lý thông báo kết quả và cơ chế bắt đầu giao dịch mới một cách an toàn.

## 15. Bài tập tự kiểm tra

**Câu 1.** Đăng nhập đã xác minh mật khẩu nhưng bước MFA chưa hoàn tất. Có thể cấp access token với quyền như phiên đã đăng nhập bình thường không? Giải thích bằng trạng thái và ranh giới tin cậy.

**Câu 2.** Vì sao một ID token OIDC có chữ ký hợp lệ vẫn có thể phải bị từ chối? Hãy nêu ít nhất ba kiểm tra ngoài chữ ký.

**Câu 3.** Trong một hệ thống có nhiều server, mỗi server tự đếm số lần đăng nhập sai. Kẻ tấn công phân tán request thì điều gì xảy ra? Cần điều chỉnh gì?

**Câu 4.** Người dùng báo “OTP đúng nhưng hệ thống vẫn từ chối”. Hãy nêu hai nguyên nhân hợp lệ và cách xử lý mà không bỏ qua bảo vệ.

**Câu 5.** Khi token dùng để gọi API đã hết hạn, tại sao không thể tự động chấp nhận token đó chỉ vì người dùng vừa vượt qua MFA ngày hôm qua?

**Câu 6.** Một người dùng có phiên cơ sở hợp lệ nhưng step-up để đổi mật khẩu thất bại. Nên xử lý thao tác đổi mật khẩu và phiên cơ sở thế nào?

### Gợi ý trả lời

1. **Không.** \`PrimaryVerified\` hoặc \`AdditionalPending\` chưa đạt toàn bộ chính sách; chỉ khi đủ các yếu tố server mới được tạo phiên/tokens với quyền tương ứng.
2. Có thể sai \`issuer\`, \`audience\`, \`nonce\`, đã hết hạn, dùng sai ngữ cảnh hoặc không khớp giao dịch. Chữ ký chỉ xác minh một phần điều kiện.
3. Giới hạn từng instance có thể bị vượt dễ dàng; cần bộ đếm chia sẻ/phối hợp và quan sát theo tài khoản, nguồn, mẫu chiến dịch.
4. Mã hết thời gian, đồng hồ lệch vượt cửa sổ, mã đã dùng hoặc nhầm authenticator là những khả năng. Cho đồng bộ thời gian, mã mới hoặc kênh khôi phục an toàn; không chấp nhận mã đã hết hạn.
5. Phiên/token có thời hạn và điều kiện thu hồi riêng. MFA trước đó không làm một bearer token hết hạn trở thành hợp lệ.
6. **Không thực hiện đổi mật khẩu** khi chưa đủ step-up. Phiên cơ sở có thể được giữ nếu vẫn hợp lệ và không có dấu hiệu xâm phạm; xử lý khác khi chính sách rủi ro yêu cầu thu hồi.

## 16. Ghi nhớ

**Failure path là một phần của giao thức xác thực, không phải màn hình lỗi phụ.** Với mỗi bước kiểm chứng credential, MFA, passkey, chứng chỉ, SSO, phiên, token và khôi phục, phải xác định rõ điều kiện từ chối, trạng thái sau lỗi, khả năng thử lại và dữ liệu được phép tiết lộ. Những bất biến quan trọng là **không cấp quyền khi bằng chứng chưa đủ, không chấp nhận replay hay bằng chứng sai ngữ cảnh, không bỏ qua kiểm chứng khi hệ thống gặp sự cố, và không để biện pháp chống lạm dụng làm người dùng hợp lệ mất khả năng truy cập vô hạn**. Thiết kế failure path từ đầu giúp hệ thống vừa an toàn hơn vừa dễ vận hành và phục hồi.
