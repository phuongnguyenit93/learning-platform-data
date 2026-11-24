# MFA fatigue: mệt mỏi xác thực đa yếu tố và cách kiểm soát trong vòng đời danh tính IAM

## 1. MFA fatigue là gì?

**MFA fatigue** (mệt mỏi vì yêu cầu xác thực đa yếu tố), còn được gọi là **push fatigue** hoặc **MFA push bombing**, là tình huống người dùng liên tục nhận được yêu cầu xác thực đa yếu tố, thường dưới dạng thông báo đẩy (*push notification*), đến mức có nguy cơ **chấp thuận một yêu cầu không phải do mình khởi tạo**. Tác nhân tấn công có thể lợi dụng sự mệt mỏi, bối rối, mất tập trung hoặc lời mạo danh bộ phận hỗ trợ để khiến người dùng chấp nhận.

Ví dụ, An đang làm việc bình thường nhưng điện thoại liên tục hiện thông báo “Chấp thuận đăng nhập?”. An không hề bắt đầu một phiên đăng nhập mới. Nếu An nhấn **Approve** chỉ để dừng các thông báo, kẻ đang cố đăng nhập có thể vượt qua bước xác thực bổ sung nếu ứng dụng và IdP chấp nhận hành động đó.

Điều này không có nghĩa **MFA vô dụng**. MFA thường giúp giảm nguy cơ khi mật khẩu bị lộ, nhưng **không phải mọi phương thức MFA đều chống phishing hoặc chống việc người dùng bị thao túng để chấp nhận**. Một luồng push chỉ yêu cầu bấm “Có/Không” có bề mặt rủi ro khác với FIDO2/WebAuthn gắn bằng chứng mật mã với website thật.

Trong quản lý **Identity and Access Management (IAM)**, MFA fatigue thuộc trách nhiệm của cả **thiết kế xác thực, quản lý authenticator, giám sát và vòng đời Joiner–Mover–Leaver**. Không thể giải quyết chỉ bằng nhắc nhở người dùng cẩn thận; hệ thống phải hạn chế khả năng lạm dụng và phát hiện hành vi bất thường.

### Mục tiêu học tập

Sau bài này, người học cần hiểu:

1. MFA fatigue khác một yêu cầu MFA hợp lệ và khác những dạng phishing khác ở điểm nào.
2. Vì sao push approval không được xem là cơ chế chống phishing chỉ vì đã có hai yếu tố.
3. Cách áp dụng number matching, giới hạn yêu cầu, kiểm soát phiên, đánh giá rủi ro và WebAuthn/passkey phù hợp.
4. Cách phản ứng khi xuất hiện hàng loạt yêu cầu MFA không mong đợi hoặc có một lần chấp thuận đáng ngờ.
5. Cách kết nối **HRIS, IdP, SSO, RBAC/ABAC, provisioning/SCIM, audit** và tài khoản dịch vụ để hạn chế truy cập tồn dư.

## 2. Luồng MFA push bình thường và điểm yếu bị khai thác

Thông thường, người dùng nhập thông tin đăng nhập hoặc bắt đầu xác thực tại ứng dụng; **IdP** yêu cầu thêm một yếu tố; authenticator trên điện thoại hiển thị thông báo; người dùng kiểm tra và chấp thuận; IdP tiếp tục tạo phiên hoặc hoàn tất giao thức **Single Sign-On (SSO)**.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant App as Ứng dụng
    participant IdP as IdP / MFA verifier
    participant Phone as Authenticator trên điện thoại
    U->>App: Bắt đầu đăng nhập
    App->>IdP: Chuyển đến quy trình xác thực
    IdP->>IdP: Kiểm tra danh tính, chính sách và rủi ro
    IdP->>Phone: Gửi yêu cầu xác minh phiên đang diễn ra
    Phone-->>U: Hiển thị ngữ cảnh và thử thách
    U->>Phone: Kiểm tra yêu cầu, chỉ chấp thuận nếu tự khởi tạo
    Phone->>IdP: Phản hồi MFA hợp lệ
    IdP->>IdP: Kiểm tra phiên, challenge và chính sách
    IdP-->>App: Kết quả xác thực / assertion
    App->>App: Kiểm tra phiên, quyền tại tài nguyên
~~~

Trong trường hợp MFA fatigue, người đang sở hữu danh tính nhận yêu cầu **không do mình khởi tạo**. Đây có thể là dấu hiệu kẻ khác đã biết mật khẩu hoặc đang cố dùng một đường xác thực có khả năng kích hoạt push. Hành vi tấn công thường tận dụng **yếu tố con người** thay vì phá thuật toán mật mã của OTP hay khóa riêng.

Chuỗi rủi ro ở mức khái niệm:

~~~mermaid
flowchart TD
    A["Một đường xác thực bị lạm dụng<br/>ví dụ thông tin đăng nhập đã lộ"] --> B["Người dùng nhận MFA push không mong đợi"]
    B --> C{"Người dùng nhận ra đây không phải yêu cầu của mình?"}
    C -->|"Có"| D["Từ chối, báo cáo, giữ an toàn tài khoản"]
    C -->|"Không / bị thao túng"| E["Có thể chấp thuận nhầm"]
    E --> F["IdP có thể hoàn tất xác thực cho phiên đang yêu cầu"]
    F --> G["Ứng dụng tạo session / token"]
    G --> H["Tài nguyên bị ảnh hưởng tùy quyền hiệu lực"]
    D --> I["Đội IAM/SOC điều tra và hạn chế các yêu cầu tiếp diễn"]
~~~

**Bằng chứng một yêu cầu đã được chấp thuận không đồng nghĩa mọi phiên trong doanh nghiệp đã bị xâm nhập**. Cần kiểm tra phiên nào được hoàn thành, token nào được cấp, ứng dụng nào được sử dụng và liệu có hành vi trái phép hay không. Ngược lại, một yêu cầu bị từ chối cũng chưa đủ để khẳng định tài khoản đã an toàn: kẻ khác có thể vẫn nắm yếu tố đầu tiên.

## 3. MFA fatigue khác gì các rủi ro xác thực khác?

| Khái niệm | Bản chất | Điểm khác biệt |
| --- | --- | --- |
| **MFA fatigue / push bombing** | Lạm dụng yêu cầu xác thực lặp lại để gây mệt mỏi hoặc tạo cơ hội chấp thuận nhầm | Trọng tâm là yêu cầu MFA không mong đợi và hành vi người dùng |
| **Phishing mật khẩu** | Lừa người dùng nhập mật khẩu vào nơi giả mạo | Có thể là nguồn gây lộ yếu tố đầu tiên trước khi xuất hiện MFA fatigue |
| **Adversary-in-the-middle phishing** | Trung gian chuyển tiếp luồng đăng nhập và đánh cắp phiên khi có thể | Có thể xảy ra ngay cả khi người dùng hoàn thành MFA không chống phishing |
| **Credential stuffing** | Thử credential đã lộ trên dịch vụ khác | Có thể dẫn tới yêu cầu push, nhưng không phải mọi đợt stuffing đều gây MFA fatigue |
| **Password spraying** | Thử một vài mật khẩu phổ biến trên nhiều tài khoản | Không đòi hỏi đã biết mật khẩu riêng của từng người |
| **OTP phishing** | Lừa lấy/chuyển tiếp mã OTP | Không nhất thiết dùng thông báo đẩy liên tục |
| **Push fatigue do cấu hình lỗi** | Ứng dụng, thiết bị hoặc quy trình hợp lệ tạo quá nhiều yêu cầu | Không mặc định là tấn công; vẫn cần xác minh nguyên nhân |

**MFA fatigue là một dấu hiệu đáng điều tra, không tự chứng minh đã có tài khoản bị chiếm.** Hệ thống giám sát nên kết hợp telemetry và bối cảnh thay vì coi mọi lần từ chối push là sự cố an ninh.

## 4. Vì sao người dùng có thể chấp thuận một push sai?

MFA fatigue xuất hiện khi giao diện và quy trình khiến **người nhận phải tự suy đoán yêu cầu có hợp lệ không**, trong khi kẻ tấn công có thể gây áp lực. Những yếu tố thường gặp:

- **Thông báo giống nhau, không rõ nguồn:** chỉ hiển thị hai nút Approve/Deny mà không mô tả được ứng dụng và yêu cầu.
- **Tần suất cao:** nhiều thông báo liên tiếp khiến người dùng xử lý bằng phản xạ để dừng phiền nhiễu.
- **Yêu cầu xuất hiện vào thời điểm nhạy cảm:** ban đêm, lúc đang họp hoặc đang xử lý công việc gấp.
- **Thói quen chấp thuận tự động:** thường xuyên bấm Approve khi thấy push mà không đối chiếu với thao tác do mình vừa bắt đầu.
- **Mạo danh helpdesk hoặc quản lý:** người dùng bị thuyết phục rằng phải chấp thuận để “kiểm tra hệ thống” hoặc “khắc phục lỗi”.
- **Lỗ hổng ở khâu hỗ trợ:** helpdesk có thể bị thao túng để reset MFA hay thêm authenticator không đúng chủ thể.
- **Thiếu cơ chế báo cáo dễ dùng:** người dùng không biết cách đánh dấu “Tôi không yêu cầu” hoặc liên hệ đội an ninh.

Các yếu tố trên thuộc **thiết kế sản phẩm và kiểm soát vận hành**, không chỉ trách nhiệm cá nhân. Giảm độ phiền nhiễu, cải thiện ngữ cảnh, dùng cơ chế chống phishing và chuẩn hóa xử lý sự cố sẽ hiệu quả hơn việc chỉ yêu cầu “đừng bấm nhầm”.

### Nguyên tắc hành vi cho người dùng

Khi thấy MFA push không do mình bắt đầu, **không chấp thuận chỉ để thông báo biến mất**. Từ chối hoặc sử dụng nút báo cáo đáng ngờ nếu có, sau đó thông báo qua kênh an ninh/hỗ trợ **đã biết là đáng tin cậy**. Không gọi lại số điện thoại hoặc truy cập đường dẫn do người lạ tự cung cấp trong thông báo hoặc cuộc gọi bất thường.

## 5. MFA không đồng nghĩa với chống phishing

MFA yêu cầu bằng chứng từ **nhiều yếu tố xác thực phù hợp**. Nhưng khả năng chống phishing phụ thuộc **phương thức, giao thức và cách verifier kiểm chứng**, không chỉ số lượng màn hình hay số lần người dùng chạm vào điện thoại.

| Phương thức | Có thể dùng làm MFA? | Có chống phishing theo đặc tính giao thức? | Ghi chú |
| --- | --- | --- | --- |
| Password + push Approve/Deny | Có, tùy cấu hình | **Không mặc nhiên** | Dễ bị thao túng bởi push fatigue |
| Password + TOTP | Có | **Không** | Mã có thể bị chuyển tiếp theo thời gian thực |
| Password + SMS OTP | Có trong một số chính sách | **Không** | Có rủi ro chuyển số, SIM swap, phishing và phụ thuộc mạng |
| Push với number matching | Có, tùy triển khai | **Không mặc nhiên** | Tăng tính gắn kết với phiên, giảm xác nhận phản xạ |
| FIDO2/WebAuthn security key | Có thể là xác thực sở hữu hoặc đa yếu tố tùy UV | **Có**, nếu kiểm tra RP ID/origin/challenge đúng | Không dựa vào mã dùng chung mà người dùng nhập tại website giả |
| Passkey WebAuthn | Có thể đáp ứng MFA theo thuộc tính UV và chính sách | **Có**, nếu RP xác minh đúng | Phân biệt passkey được đồng bộ và khóa bị ràng buộc thiết bị khi chính sách cần |

**User verification (UV)**, chẳng hạn PIN hoặc sinh trắc cục bộ để mở khóa phương tiện, cần được kiểm tra theo tín hiệu giao thức nếu chính sách yêu cầu. **User presence (UP)** không đồng nghĩa UV. Một passkey không nên mặc định được báo cáo là “đáp ứng MFA cấp cao” chỉ vì tên gọi của nó.

Sử dụng xác thực chống phishing giúp giảm phụ thuộc vào việc người dùng phân biệt thông báo hợp lệ/giả mạo, nhưng **không thay thế kiểm soát phiên, bảo mật thiết bị, authorization hay khả năng thu hồi token**.

## 6. Number matching: tác dụng và giới hạn

**Number matching** yêu cầu người dùng đối chiếu hoặc nhập một mã/số xuất hiện ở phiên đăng nhập đang khởi tạo vào ứng dụng MFA, thay vì chỉ bấm Approve. Mục tiêu là tạo **mối liên hệ rõ hơn giữa người dùng và yêu cầu đang diễn ra**, giảm xác nhận phản xạ.

Ví dụ minh họa:

1. An chủ động mở trang đăng nhập của doanh nghiệp.
2. IdP hiển thị số **48** trong ngữ cảnh đăng nhập của An.
3. Ứng dụng MFA trên thiết bị yêu cầu An nhập hoặc chọn số tương ứng.
4. An chỉ hoàn thành nếu thật sự đang đăng nhập và nhận ra cùng ngữ cảnh.

**Số 48 chỉ là giá trị giả lập**, không phải bí mật xác thực hay cấu hình bắt buộc.

Number matching có thể giảm tác động của việc người dùng bấm chấp thuận liên tục, nhưng **không tự biến push MFA thành phishing-resistant authentication**. Nếu người dùng bị dẫn dụ vào một luồng đăng nhập giả, bị thuyết phục đọc hoặc nhập số do bên thứ ba yêu cầu, hoặc chính website bị trung gian chuyển tiếp, số đối chiếu vẫn có thể bị lạm dụng. Cần kết hợp kiểm tra ngữ cảnh, chống social engineering, giới hạn yêu cầu và ưu tiên WebAuthn ở nơi có yêu cầu bảo mật cao.

### Hiển thị ngữ cảnh đăng nhập

Ứng dụng MFA có thể hiển thị tên ứng dụng, trình duyệt, loại thiết bị, thời gian và địa điểm ước tính. Đây là **tín hiệu phụ trợ**, không phải bằng chứng độc lập về tính hợp lệ: địa điểm có thể sai do VPN, mạng di động hoặc định tuyến; tên ứng dụng cần đến từ nguồn đáng tin cậy và được trình bày không gây hiểu lầm.

## 7. Các biện pháp kiểm soát tại IdP và MFA verifier

Mục tiêu là không để bất kỳ ai có thông tin đăng nhập sơ bộ nào cũng có thể **tạo vô hạn yêu cầu push** tới một nhân viên.

| Kiểm soát | Mục đích | Lưu ý khi áp dụng |
| --- | --- | --- |
| **Rate limiting theo account, client, nguồn và ngữ cảnh** | Hạn chế lặp push quá mức | Kết hợp nhiều tín hiệu để tránh kẻ tấn công gây khóa nhầm người dùng |
| **Giới hạn số lần retry của cùng challenge** | Ngăn một phiên phát vô hạn yêu cầu | Ràng buộc yêu cầu vào transaction và TTL ngắn |
| **Cooldown/throttle theo chính sách** | Ngăn các đợt push liên tục | Có ngoại lệ hỗ trợ được kiểm soát, không cho bypass tùy ý |
| **Từ chối các yêu cầu có rủi ro rõ ràng** | Không gửi push cho mọi lần thử xác thực bất thường | Dùng risk engine và độ tin cậy của tín hiệu |
| **Number matching** | Giảm xác nhận nhầm khi chỉ bấm Approve | Không tuyên bố chống phishing tuyệt đối |
| **Context-rich approval** | Giúp người dùng nhận biết yêu cầu do mình khởi tạo | Ngữ cảnh phải chính xác và không hiển thị nội dung giả mạo |
| **Báo cáo “Not me”/“Report suspicious”** | Dễ gửi tín hiệu sự cố về IdP/SOC | Phải có quy trình theo dõi và phản ứng, không chỉ hiện UI |
| **Phishing-resistant MFA** | Giảm sự phụ thuộc vào phê duyệt push | WebAuthn/passkey triển khai và kiểm chứng đúng |
| **Chính sách theo mức đặc quyền** | Bảo vệ tài khoản/admin/action nhạy cảm | Yêu cầu mạnh hơn cho privileged role và step-up |
| **Giám sát theo correlation ID** | Nhận ra nhiều yêu cầu bất thường liên quan cùng identity | Không log OTP, token, seed hay bí mật |

Các kiểm soát **phòng ngừa** nên kết hợp với **phát hiện** và **ứng phó**. Ví dụ, chỉ đặt giới hạn push nhưng vẫn cho phép helpdesk thêm authenticator mới mà không xác minh đầy đủ có thể tạo một đường vòng yếu.

### Cẩn trọng với auto-lock

Tự khóa account vĩnh viễn ngay sau vài lần push bị từ chối có thể tạo rủi ro **denial of service** do kẻ tấn công cố tình gây ra. Phương án phù hợp thường gồm chặn/throttle yêu cầu đáng ngờ, cảnh báo, bảo vệ giao dịch và có quy trình khôi phục được kiểm soát. Chính sách khóa và mở khóa phải cân bằng an toàn với khả năng tiếp tục làm việc.

## 8. Thiết kế authentication challenge đúng cách

Ở phía IdP và ứng dụng MFA, một challenge cần có vòng đời được quản trị:

1. Gắn với **đúng tài khoản, client, giao dịch, thiết bị và ngữ cảnh đăng nhập**.
2. Có **thời hạn sử dụng** và trạng thái rõ: pending, approved, denied, expired hoặc cancelled.
3. Không cho một phản hồi approve cũ được dùng lại cho giao dịch mới (**anti-replay**).
4. Chỉ chấp nhận kết quả từ authenticator **đã được binding hợp lệ** với identity.
5. Sau khi người dùng bấm Deny/Report, ngăn challenge đó tiếp tục hoàn tất và đánh giá có cần hạn chế yêu cầu mới.
6. Phân biệt retry kỹ thuật của cùng giao dịch với yêu cầu đăng nhập độc lập; tránh gửi nhiều push chỉ vì timeout của ứng dụng.
7. Có dấu vết quyết định để đối soát khi xảy ra sự cố nhưng **không lưu mã OTP hoặc token thật**.

Ví dụ mô hình trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Pending: Gửi challenge đã kiểm soát
    Pending --> Approved: Xác nhận hợp lệ
    Pending --> Denied: Từ chối hoặc báo cáo
    Pending --> Expired: Hết thời hạn
    Pending --> Cancelled: Hủy phiên / rủi ro cao
    Approved --> Consumed: Verifier xác nhận một lần
    Denied --> [*]
    Expired --> [*]
    Cancelled --> [*]
    Consumed --> [*]
~~~

Sơ đồ chỉ mô tả khái niệm; các trạng thái cụ thể tùy nhà cung cấp. Một phản hồi **Approved** không phải quyết định cuối cùng nếu tài khoản đã bị khóa, transaction hết hạn hoặc rủi ro mới khiến verifier phải từ chối.

## 9. Xác thực chống phishing: FIDO2, WebAuthn và passkeys

**WebAuthn** dùng khóa mật mã bất đối xứng được liên kết với một **relying party (RP)**. Authenticator dùng khóa riêng để ký thử thách; RP kiểm tra khóa công khai đã lưu, challenge, origin/RP ID và những điều kiện khác theo giao thức. Một website giả có origin khác không thể tự tạo chữ ký hợp lệ cho RP thật nếu việc ràng buộc và kiểm tra được thực hiện đúng.

Đây là thay đổi quan trọng so với push “Approve”: người dùng không phải quyết định một lời mời đăng nhập không rõ nguồn chỉ bằng phản xạ; cơ chế mật mã giúp **ràng buộc kết quả xác thực với RP hợp lệ**.

### Passkey không phải một loại triển khai duy nhất

- **Device-bound authenticator** giữ khóa riêng gắn với thiết bị/phương tiện cụ thể, phù hợp một số yêu cầu đặc biệt về kiểm soát khóa.
- **Synced passkey** có thể đồng bộ trong hệ sinh thái của nhà cung cấp để tăng tính khả dụng và thuận tiện.
- Chính sách cần đánh giá **khả năng bảo vệ khóa, việc đồng bộ, user verification, quản lý thiết bị, khôi phục và attestation nếu thực sự yêu cầu**.

Khi chuyển từ push MFA sang passkey/WebAuthn, cần kiểm tra **luồng fallback**. Nếu người dùng vẫn có thể bấm “Dùng cách khác” để đăng nhập quản trị bằng phương thức yếu hơn mà không kiểm soát, chính sách chống phishing có thể bị vô hiệu trong thực tế.

## 10. Các đường vòng thường bị bỏ sót

Triển khai bảo vệ push tại IdP chưa đủ nếu vẫn còn những đường xác thực khác:

| Đường vào | Rủi ro | Kiểm soát cần xét |
| --- | --- | --- |
| **Ứng dụng local login** | Không dùng IdP/MFA trung tâm | Vô hiệu fallback không cần thiết hoặc áp dụng bảo vệ tương đương |
| **Recovery và reset MFA** | Có thể thêm authenticator mới thông qua xác minh yếu | Identity proofing, step-up, phê duyệt và audit |
| **SSO session đang tồn tại** | Sau khi khóa push, session cũ có thể còn dùng được | Session management, logout và token revocation theo khả năng |
| **Thiết bị/ứng dụng đã tin cậy** | Có thể bỏ qua MFA theo chính sách cũ | Rà soát điều kiện thiết bị và thời hạn tin cậy |
| **Tài khoản đặc quyền riêng** | MFA không mạnh như account thông thường | Bảo vệ riêng, phương thức chống phishing, ghi log |
| **API key/PAT/CLI token** | Không qua màn hình MFA push | Kiểm kê, giới hạn scope, thu hồi và đối soát |
| **Account khẩn cấp (break-glass)** | Cơ chế dự phòng có thể bị lạm dụng | Quyền hạn, điều kiện sử dụng, giám sát, kiểm toán riêng |

**MFA là kiểm soát xác thực, không thay thế authorization.** Dù một phiên được xác thực thành công, ứng dụng vẫn phải thực thi **RBAC/ABAC** theo role, thuộc tính, tài nguyên, hành động và ranh giới tenant.

## 11. MFA fatigue trong Joiner lifecycle

**Joiner** là giai đoạn xác minh chủ thể, tạo account và **đăng ký (enroll/bind) authenticator**. Nhiều sự cố MFA fatigue có thể được giảm từ khâu thiết kế ban đầu.

Quy trình tham khảo:

1. **HRIS hoặc nguồn bảo trợ** xác nhận nhân viên/nhà thầu, trạng thái và ngày bắt đầu; IAM liên kết person–employment–identity đáng tin cậy.
2. Tạo account trên IdP, không kích hoạt sớm nếu chưa đến thời điểm chính sách cho phép.
3. Chọn authenticator theo mức rủi ro công việc: ưu tiên phishing-resistant MFA khi cần; nếu dùng push, áp dụng number matching và rate limiting.
4. **Binding** authenticator phải yêu cầu chứng minh đúng chủ thể và hoàn tất challenge; không chỉ ghi “đã gửi lời mời” rồi coi xong.
5. Hướng dẫn người dùng phân biệt push do chính mình khởi tạo và yêu cầu không mong đợi; cung cấp nút/kênh báo cáo.
6. Thiết lập **phương án phục hồi** an toàn để mất thiết bị không tạo áp lực dùng một đường yếu, đồng thời tránh bypass chính sách.
7. Kiểm tra IdP, SSO và ứng dụng bắt buộc đã áp dụng MFA đúng; đối soát account và quyền cấp ban đầu qua SCIM/API.
8. Lưu bằng chứng hoàn tất theo từng cổng: account ready, authenticator bound, policy applied, first use/activation nếu quy trình yêu cầu.

Ví dụ, một nhân viên mới chưa kích hoạt thiết bị MFA có thể ở trạng thái **technical account ready nhưng chờ enrollment**; không nên cho truy cập dữ liệu nhạy cảm trước khi thỏa điều kiện bảo mật bắt buộc chỉ để đánh dấu Joiner completed.

## 12. MFA fatigue trong Mover lifecycle

**Mover** thay đổi phòng ban, vị trí, organization, dự án hoặc mức đặc quyền. Điều này có thể làm thay đổi **mức bảo đảm xác thực** cần thiết:

| Sự kiện Mover | Câu hỏi kiểm soát | Biện pháp |
| --- | --- | --- |
| Từ nhân viên thường sang cloud admin | Authenticator hiện tại có đáp ứng chính sách đặc quyền? | Đăng ký WebAuthn/security key hoặc phương thức được duyệt trước khi cấp role |
| Chuyển sang xử lý dữ liệu nhạy cảm | Có yêu cầu step-up khi thực hiện hành động rủi ro cao? | Kiểm chứng độ mới phiên và phương thức xác thực |
| Chuyển sang tổ chức/tenant khác | Chính sách MFA và thiết bị có thay đổi không? | Tính lại policy theo nguồn có thẩm quyền |
| Rời vị trí đặc quyền | Session/token cũ còn mang role quản trị không? | Thu hồi quyền và kiểm tra quyền hiệu lực tại đích |
| Đổi điện thoại hoặc authenticator | Có đường thêm thiết bị mới bị lợi dụng? | Xác minh binding và thu hồi thiết bị cũ phù hợp |

Không nên chỉ thêm nhóm admin và dựa trên MFA push thông thường nếu chính sách yêu cầu chống phishing. Đồng thời **thu hồi role cũ** và kiểm tra token/session có quyền cũ; một token được cấp trước Mover có thể chứa claim chưa cập nhật.

## 13. MFA fatigue trong Leaver lifecycle

Khi một người rời tổ chức, quy trình **Leaver** cần bảo đảm họ không thể xác thực mới bằng authenticator đã đăng ký, đồng thời xử lý những quyền vẫn còn hoạt động.

Các kiểm tra thiết yếu:

- Sự kiện nghỉ việc đến từ **nguồn có thẩm quyền**, được đối chiếu đúng identity và thời điểm hiệu lực.
- Account/IdP được vô hiệu hóa theo chính sách, **binding authenticator** được thu hồi/điều chỉnh phù hợp.
- **SSO session, refresh token, access token và session ứng dụng** được xử lý bằng cơ chế được từng hệ thống hỗ trợ.
- **Tài khoản cục bộ** không dùng IdP, recovery method và quyền trực tiếp phải được đối soát.
- **SCIM deactivation** là một phần deprovisioning, không tự chứng minh mọi token hoặc phiên đã hết hiệu lực.
- Người còn quan hệ lao động hợp lệ khác không bị vô hiệu nhầm toàn bộ quyền; phải tính theo từng employment/tenant.
- **Workload identity** do người nghỉ việc quản lý cần chuyển chủ sở hữu, rà soát secret và quyền cá nhân liên quan.

Nếu có các yêu cầu MFA không mong đợi **sau thời điểm Leaver**, đây là tín hiệu cần điều tra: có thể có tài khoản chưa khóa, đường local login chưa được quản lý, sự kiện cũ hoặc cố gắng xác thực tự động. Không tự kết luận đã có truy cập thành công nếu chưa có log phiên và quyền thực tế.

## 14. Helpdesk, recovery và nguy cơ bị thao túng

Một nguyên nhân khiến kỹ thuật xác thực mạnh vẫn bị vượt qua là **quy trình khôi phục yếu**. Khi người dùng đang bị push liên tục hoặc mất thiết bị, kẻ mạo danh có thể cố thuyết phục helpdesk thay đổi MFA.

Quy trình hỗ trợ cần:

1. **Xác minh danh tính theo mức rủi ro**, không chỉ dựa vào họ tên, email, số điện thoại hoặc những thông tin HR có thể bị lộ.
2. Yêu cầu **ủy quyền phù hợp** với tài khoản đặc quyền hoặc trường hợp đổi authenticator nhạy cảm.
3. Không hướng dẫn người dùng chấp thuận một push mà họ **không tự khởi tạo** để “xác minh nhân viên”.
4. Giới hạn quyền của nhân viên hỗ trợ, tách vai trò phê duyệt và thực thi khi cần.
5. Gửi thông báo độc lập cho người sở hữu account khi có authenticator mới, reset hoặc thay đổi recovery.
6. Lưu audit về actor, lý do, chính sách, phương thức proofing và kết quả; **không lưu OTP, recovery code hoặc private key**.
7. Kiểm tra lại session/token và binding sau khi khôi phục; không coi reset MFA là đã xử lý xong một sự cố chiếm account.

Một phương thức MFA chống phishing có thể bị suy yếu nếu bước recovery cho phép thêm authenticator mới bằng **một kênh yếu hơn không được kiểm soát**. Bảo vệ recovery là một phần của bảo vệ MFA, không phải việc hỗ trợ phụ.

## 15. Playbook khi xuất hiện MFA push không mong đợi

**Tình huống:** người dùng thông báo liên tục nhận MFA push, không thực hiện đăng nhập nào và có thể vừa nhận cuộc gọi “nhân viên hỗ trợ” yêu cầu chấp thuận.

| Giai đoạn | Người/nhóm thực hiện | Mục tiêu |
| --- | --- | --- |
| **Tiếp nhận và xác minh** | Helpdesk/SOC | Xác nhận tài khoản, thời điểm, tình trạng người dùng đã bấm Approve hay chưa |
| **Ngăn tiếp diễn** | IAM/IdP operations | Chặn hoặc throttle yêu cầu bất thường, hạn chế đăng nhập theo rủi ro |
| **Bảo vệ yếu tố đầu tiên** | IAM và người dùng | Xử lý mật khẩu/credential nghi bị lộ, không tạo đường reset yếu |
| **Kiểm tra phiên/token** | IdP/ứng dụng | Thu hồi phiên và credential có rủi ro khi chính sách yêu cầu |
| **Điều tra truy cập** | SOC/chủ ứng dụng | Tìm phiên hoàn tất, client, resource, hành vi bất thường và phạm vi tác động |
| **Khôi phục an toàn** | IAM/helpdesk | Xác minh lại authenticator, chuyển phương thức mạnh hơn nếu phù hợp |
| **Đối soát và đóng sự cố** | IAM/SOC | Chứng minh đường truy cập đã được kiểm soát, lưu bằng chứng và ngoại lệ |

### Hành động dành cho người dùng

Nếu nhận push không mong đợi:

1. **Không chấp thuận**; chọn Deny hoặc Report suspicious nếu ứng dụng hỗ trợ.
2. Không cung cấp mã OTP/number matching cho người gọi hoặc đường dẫn lạ.
3. Báo ngay cho kênh an ninh/hỗ trợ nội bộ đã được xác nhận; nêu thời điểm và loại thông báo.
4. Thực hiện hướng dẫn đổi credential, kiểm tra thiết bị và đăng ký authenticator lại **qua quy trình hợp lệ**.
5. Nếu đã chấp thuận nhầm, phải nói rõ để đội phản ứng kiểm tra và thu hồi phiên/token có rủi ro; không tự suy đoán rằng chỉ đổi mật khẩu là đủ.

### Hành động dành cho IAM/SOC

Cần liên kết **các request MFA, xác thực yếu tố đầu tiên, phản hồi push, session SSO, token đã phát hành và truy cập ứng dụng**. Nếu có thành công bất thường, đánh giá entitlement và dữ liệu tài nguyên theo **RBAC/ABAC** để xác định mức độ ảnh hưởng. Không chặn toàn bộ người dùng khác chỉ vì cùng mạng/IP nếu chưa đánh giá tác động.

## 16. Thu thập telemetry và bằng chứng kiểm toán

Để điều tra MFA fatigue, các log riêng lẻ thường chưa đủ. Cần **correlation ID** cho phiên và challenge, cùng mốc thời gian có thể so sánh giữa IdP, ứng dụng MFA và ứng dụng đích.

| Tín hiệu | Giá trị sử dụng | Cần thận trọng |
| --- | --- | --- |
| **Identity/account reference** | Nối sự kiện về đúng người hoặc workload | Không suy identity chỉ từ email/username có thể tái sử dụng |
| **MFA challenge ID / transaction ID** | Biết các push thuộc cùng hay khác phiên | Không lưu bí mật phản hồi |
| **Thời điểm gửi, nhận, approve/deny/expire** | Phát hiện lặp bất thường và độ trễ | Đồng bộ thời gian và timezone |
| **Số request và khoảng cách giữa request** | Gợi ý push bombing hoặc lỗi retry | Một mẫu lặp có thể do sự cố kỹ thuật |
| **Ứng dụng/client, phương thức, trạng thái** | Khoanh vùng đường đăng nhập | Client name có thể bị sai mapping |
| **Device/authenticator reference** | Xác định thiết bị đã nhận/phản hồi | Hạn chế thu thập fingerprint vượt nhu cầu |
| **Thông tin mạng/rủi ro** | Hỗ trợ điều tra đăng nhập bất thường | IP/geolocation có thể không chính xác, VPN làm lệch tín hiệu |
| **Session/token issuance** | Xác định có phiên được cấp không | Không ghi bearer token, refresh token hoặc cookie |
| **Authorization/effective access** | Xem tài nguyên nào đã được truy cập | Bảo vệ log chứa thông tin nhạy cảm và hành vi người dùng |
| **Helpdesk/recovery actions** | Phát hiện thay đổi MFA không đúng quy trình | Phân quyền đọc nhật ký và dấu vết phê duyệt |

### Ví dụ sự kiện giám sát minh họa

~~~json
{
  "eventId": "mfa-event-2026-1042",
  "identityRef": "iam-id-482",
  "idpAccountRef": "idp-user-482",
  "challengeId": "challenge-991",
  "authenticationTransactionId": "auth-txn-744",
  "clientRef": "company-portal",
  "authenticatorType": "push-number-matching",
  "eventType": "mfa_challenge_denied",
  "initiatedByUser": false,
  "reportedSuspicious": true,
  "occurredAt": "2026-11-23T09:34:12+07:00",
  "result": "DENIED",
  "sessionIssued": false,
  "triageStatus": "OPEN"
}
~~~

Đây là JSON minh họa, không phải schema của một IdP cụ thể. Trường **initiatedByUser** chỉ có thể có độ tin cậy khi đã có bằng chứng từ quy trình hoặc người dùng; hệ thống không nên tự khẳng định chắc chắn chỉ vì không thấy trình duyệt quen thuộc. Kết quả Denied chứng minh một challenge đã bị từ chối, **chưa chứng minh các attempt khác đều thất bại**.

## 17. Mã giả phát hiện và xử lý yêu cầu push bất thường

Mã giả dưới đây mang mục đích giáo dục, không phải cấu hình thật của nhà cung cấp:

~~~text
evaluateMfaChallenge(identity, transaction, context):
    requireValidIdentityAndBoundAuthenticator(identity)
    requireTrustedAuthenticationTransaction(transaction)

    if identity.isDisabled or transaction.isExpired:
        return DENY

    signals = collectRecentChallengeSignals(
        identityId = identity.id,
        client = transaction.client,
        device = context.authenticatorRef
    )

    risk = riskPolicy.evaluate(
        failedFirstFactorAttempts = signals.firstFactorFailures,
        deniedChallenges = signals.deniedCount,
        recentChallengeBurst = signals.unusualRequestRate,
        transactionContext = context
    )

    if risk.isHigh:
        throttleNewChallenges(identity, transaction.client)
        notifySecurityTeamWithCorrelationId(transaction.id)
        return BLOCK_AND_REVIEW

    challenge = createShortLivedBoundChallenge(transaction)
    sendContextRichChallengeWithNumberMatching(challenge)

    response = awaitAuthenticatorResponse(challenge)
    if response.isReportSuspicious:
        cancelTransactionAndOpenIncident(transaction)
        return DENY

    if not response.matchesTransaction or not response.isWithinValidity:
        return DENY

    if identity.isDisabled or riskPolicy.nowRequiresReevaluation(identity):
        return DENY

    return AUTHENTICATION_FACTOR_VERIFIED
~~~

**Lưu ý thiết kế:**

- Không có một ngưỡng **số push/phút** duy nhất đúng cho mọi tổ chức; phải hiệu chỉnh theo loại ứng dụng, rủi ro và kinh nghiệm vận hành.
- Throttle nên gắn với **transaction, danh tính và nguồn**, tránh biến thành công cụ làm khóa account hợp lệ không giới hạn.
- Không dựa vào một tín hiệu địa điểm hoặc IP để quyết định cho phép hoặc từ chối trong mọi tình huống.
- Sau khi một MFA factor được xác minh, vẫn phải kiểm tra **chính sách toàn phiên, trạng thái account, token issuance và authorization**.
- Cơ chế này không thay thế **WebAuthn/phishing-resistant authentication** khi đó là yêu cầu bắt buộc của role hoặc tài nguyên.

## 18. MFA fatigue, session và quyền truy cập tồn dư

Khi một yêu cầu push bị chấp thuận trái phép, kẻ đang xác thực có thể nhận **SSO session**, **OIDC/SAML assertion** hoặc các token tiếp theo tùy luồng. Ngay cả khi người dùng thay đổi mật khẩu, các phiên và token đã được cấp có thể còn hiệu lực.

Vì vậy, khắc phục sự cố không chỉ gồm **reset yếu tố đầu tiên**:

1. Xác định **những phiên xác thực** đã hoàn thành trong khoảng bất thường.
2. Thu hồi session, refresh token/grant và token hoặc credential ứng dụng trong phạm vi nền tảng hỗ trợ.
3. Với **JWT access token xác minh offline**, resource server có thể tiếp tục chấp nhận đến khi hết hạn nếu không có denylist, security epoch, introspection hoặc policy recheck thích hợp.
4. Đọc lại **trạng thái tài khoản, nhóm, role, ACL** và các thay đổi tại ứng dụng đích.
5. Giám sát các attempt lặp lại sau khi xử lý; nếu vẫn tiếp diễn, mở rộng điều tra nguồn đăng nhập và đường fallback.

**SSO** làm giảm nhu cầu đăng nhập nhiều lần, nhưng một phiên SSO bị chiếm có thể ảnh hưởng nhiều ứng dụng. **SCIM** giúp provision/deprovision user/group chứ không bảo đảm thu hồi mọi phiên và token. **RBAC/ABAC** giới hạn hành động tại tài nguyên nhưng không ngăn mọi tổn thất nếu tài khoản bị cấp quyền rộng.

## 19. Tài khoản đặc quyền và workload identity

### Đặc quyền con người

Các tài khoản có quyền quản trị cloud, hệ thống tài chính, IAM hoặc dữ liệu nhạy cảm thường cần **phương thức chống phishing** và chính sách step-up mạnh hơn. Một phương thức push dùng được cho ứng dụng rủi ro thấp không nhất thiết đạt yêu cầu cho account privileged.

Tổ chức nên phân biệt **đăng nhập thông thường** và **thao tác đặc quyền**; yêu cầu xác minh đủ độ mới của phiên và phương thức đã sử dụng, đồng thời kiểm soát những đường fallback. Đối với OIDC, thông tin như **amr, acr, auth_time** có thể hỗ trợ nếu IdP và ứng dụng định nghĩa/kiểm chứng ngữ nghĩa tương ứng. Không suy mức đảm bảo chỉ từ một chuỗi claim không được cấu hình rõ.

### Workload/service accounts

**MFA push là cơ chế cho tương tác của con người**, không nên bắt một bot hoặc job tự động chờ nhân viên bấm Approve trên điện thoại. Workload nên sử dụng credential máy phù hợp như **workload identity federation**, certificate, khóa được quản lý hoặc token ngắn hạn với audience và quyền tối thiểu.

Khi chủ sở hữu một service account chuyển việc hoặc nghỉ, cần **chuyển ownership**, rà soát credential/role và thu hồi **PAT hoặc secret cá nhân** mà người đó từng sử dụng cho workload. Không tự động xóa bot sản xuất còn nhiệm vụ hợp lệ; nhưng cũng không giữ token không có owner mãi mãi.

## 20. Tình huống thực hành: push đến liên tục trong giờ làm việc

**Bối cảnh:** Minh là nhân viên phòng Kỹ thuật, đăng nhập qua IdP của doanh nghiệp với mật khẩu và MFA push. Vào buổi sáng, Minh nhận nhiều yêu cầu MFA mặc dù đang làm tài liệu và không đăng nhập thêm. Một người lạ gọi đến, tự giới thiệu là helpdesk và nói Minh hãy “chấp thuận để hệ thống ngừng báo lỗi”.

### Phân tích vấn đề

- Những push không mong đợi là tín hiệu cần **từ chối và báo cáo**.
- Cuộc gọi mạo danh hỗ trợ có thể là một phần của **social engineering**.
- Nếu mật khẩu của Minh đã bị lộ, người khác có thể đang cố hoàn tất bước MFA; cần điều tra chứ không chỉ tắt thông báo.
- Nếu Minh đã chấp thuận nhầm, phải xác định **phiên được cấp và tài nguyên đã truy cập**, không suy rằng chỉ thay mật khẩu sẽ giải quyết hết.

### Quy trình xử lý đúng

1. Minh chọn Deny/Report suspicious, không cung cấp OTP hay mã number matching qua điện thoại và liên hệ helpdesk qua kênh đã biết.
2. SOC/IAM truy vấn log theo identity ID, challenge ID, ứng dụng và khoảng thời gian, phân biệt request được gửi, bị từ chối, chấp thuận và phiên được cấp.
3. IAM chặn/throttle các challenge đáng ngờ theo chính sách, đánh giá việc thay password và vô hiệu hóa phiên/grant có rủi ro.
4. Chủ ứng dụng đối soát **quyền hiệu lực** và hoạt động đáng ngờ theo RBAC/ABAC; không mặc định account bị truy cập mọi dữ liệu.
5. Helpdesk kiểm tra có yêu cầu reset MFA hay thêm authenticator mới không, bảo đảm không có binding trái phép.
6. Nếu chính sách yêu cầu, chuyển Minh sang authenticator **WebAuthn/passkey phù hợp**, bảo vệ cả luồng recovery và fallback.
7. Ghi lại bằng chứng, kết quả xử lý từng hệ thống, owner và hạng mục chưa xác minh.

### Câu hỏi tự kiểm tra

**Câu 1:** Number matching có bảo đảm chống phishing không?

**Trả lời:** Không. Nó làm yêu cầu gắn rõ hơn với phiên đăng nhập, giảm bấm Approve theo phản xạ, nhưng vẫn có thể bị người dùng thao túng hoặc bị lạm dụng trong những luồng phishing khác.

**Câu 2:** Người dùng bấm Deny tất cả push thì có thể đóng sự cố ngay không?

**Trả lời:** Chưa. Cần xem xét yếu tố đầu tiên có bị lộ, còn yêu cầu nào đã thành công và có phiên/token nào tồn tại không.

**Câu 3:** Có nên buộc người dùng thay password nhưng giữ nguyên mọi session cũ?

**Trả lời:** Không nên mặc nhiên làm vậy khi nghi tài khoản bị chiếm; phiên/token cần được đánh giá và thu hồi theo khả năng, phạm vi rủi ro.

**Câu 4:** Bật passkey cho tài khoản mới có xóa hết rủi ro không?

**Trả lời:** Không. Vẫn cần bảo vệ recovery, binding, thiết bị, phiên/token và quyền tại ứng dụng; nhưng WebAuthn đúng cấu hình có khả năng chống phishing mà push approval thông thường không có.

**Câu 5:** Tài khoản bot có cần người vận hành bấm push mỗi lần gọi API không?

**Trả lời:** Không nên thiết kế như vậy. Dùng workload identity và credential máy có giới hạn, quản lý owner và vòng đời riêng.

## 21. Checklist giảm MFA fatigue trong IAM

| Hạng mục | Điều cần được xác nhận |
| --- | --- |
| Nguồn HR/đối tác và identity correlation | Đúng người, quan hệ làm việc, organization và trạng thái |
| Chính sách authenticator theo vai trò | MFA phù hợp, chống phishing cho tài nguyên đặc quyền khi yêu cầu |
| Binding/enrollment | Authenticator được đăng ký đúng chủ thể và có bằng chứng |
| Number matching | Bật và kiểm tra tương tác nếu còn dùng push; không gán nhãn chống phishing tuyệt đối |
| Request throttling | Giới hạn/chặn burst, chống lạm dụng retry và denial of service |
| Challenge lifecycle | Transaction-bound, TTL, anti-replay, Deny/Report có tác dụng thực tế |
| Trải nghiệm người dùng | Ngữ cảnh rõ, nút báo cáo dễ tìm, hướng dẫn xử lý yêu cầu bất thường |
| Helpdesk và recovery | Identity proofing/step-up phù hợp, quyền reset có kiểm toán |
| IdP, SSO và ứng dụng cục bộ | Không còn đường đăng nhập yếu ngoài chính sách |
| Joiner | Đăng ký/kiểm tra MFA đúng người, đúng thời điểm, có recovery an toàn |
| Mover | Đánh giá lại phương thức khi nâng quyền; thu hồi role/token cũ |
| Leaver | Vô hiệu account, binding, session/token và quyền thực tế theo quan hệ còn hiệu lực |
| SCIM/deprovisioning | Đọc lại trạng thái user/group; kiểm tra phiên/credential riêng |
| RBAC/ABAC | Xác thực thành công không tự mở quyền ngoài tài nguyên được duyệt |
| Workload/service identity | Credential máy riêng, owner, scope và thu hồi không phụ thuộc push con người |
| Giám sát/audit | Correlation ID, burst/deny/approve, token issuance, quyền hiệu lực và ngoại lệ |

## 22. Tổng kết

**MFA fatigue** là rủi ro khi người dùng bị dồn dập bởi các yêu cầu xác thực, có thể **chấp thuận nhầm một phiên không do mình khởi tạo**. Đây là vấn đề tổng hợp của **công nghệ, trải nghiệm người dùng, social engineering và quản trị danh tính**. Number matching, hiển thị ngữ cảnh, rate limiting và cảnh báo giúp giảm rủi ro của push MFA, nhưng không nên đánh đồng chúng với **phishing-resistant authentication** như WebAuthn triển khai đúng.

Trong vòng đời **Joiner–Mover–Leaver**, IAM cần đăng ký authenticator đúng chủ thể khi Joiner, nâng yêu cầu xác thực và thu hồi quyền cũ khi Mover, ngắt account/phiên/token và các đường đăng nhập tồn dư khi Leaver. **HRIS/nguồn bảo trợ** cung cấp căn cứ; **IdP và SSO** quản lý xác thực; **SCIM** hỗ trợ user/group provisioning; **RBAC/ABAC** giới hạn quyền trên tài nguyên; còn **service account/workload identity** dùng credential máy được quản trị riêng. Chỉ khi đối soát trạng thái thật tại hệ thống đích, xử lý ngoại lệ và có bằng chứng kiểm toán thì tổ chức mới có thể giảm một cách đáng tin cậy **quyền truy cập tồn dư** phát sinh từ những sự cố MFA fatigue.
