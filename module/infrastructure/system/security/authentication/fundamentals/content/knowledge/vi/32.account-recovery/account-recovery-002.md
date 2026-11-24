# Recovery factor — Các yếu tố dùng để khôi phục quyền truy cập tài khoản

> **Chương:** Account recovery  
> **Chủ đề:** Recovery factor

**Recovery factor** là một bằng chứng hoặc phương thức được hệ thống chấp nhận để giúp người dùng lấy lại quyền truy cập khi họ mất, quên hoặc không còn sử dụng được credential chính. Ví dụ gồm recovery code, email hoặc số điện thoại dự phòng, authenticator thứ hai, passkey trên thiết bị khác, security key dự phòng và quy trình hỗ trợ có xác minh. Recovery factor có thể cứu người dùng khỏi mất tài khoản vĩnh viễn, nhưng cũng có thể trở thành đường tắt để attacker vượt qua password, MFA hoặc passkey nếu nó yếu hơn đáng kể so với phương thức đăng nhập chính.

Thiết kế recovery cần trả lời ba câu hỏi: **bằng chứng nào cho thấy người yêu cầu có quyền kiểm soát tài khoản, bằng chứng đó mạnh đến đâu, và sau khi khôi phục thì những credential/session nào phải được giữ, thay thế hoặc thu hồi?** Không phải mọi kênh liên hệ đều là một yếu tố xác thực độc lập. Email có thể bị chiếm cùng password; SMS có thể bị chuyển SIM; recovery code có thể bị lưu cùng thiết bị bị mất. Cần đánh giá cả tính độc lập và khả năng attacker chiếm nhiều yếu tố cùng lúc.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, kết nối account recovery với credential, password, MFA, passkey, certificate, token, session, SSO và enrollment. Trọng tâm là lựa chọn, đăng ký, bảo vệ, sử dụng và thu hồi recovery factor; chống recovery abuse; và khôi phục tài khoản mà không làm suy yếu toàn bộ mô hình xác thực.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Giải thích recovery factor và phân biệt nó với credential đăng nhập, contact channel và identity proofing.
2. Đánh giá độ mạnh, tính độc lập và rủi ro compromise của từng loại recovery factor.
3. Thiết kế bộ recovery factor dự phòng phù hợp với giá trị tài khoản và khả năng người dùng.
4. Đăng ký, xác minh, lưu trữ, luân chuyển và thu hồi recovery code hoặc authenticator dự phòng an toàn.
5. Thiết kế recovery flow có ràng buộc subject, purpose, thời hạn và giới hạn thử.
6. Ngăn attacker dùng email, SMS, helpdesk hoặc account linking làm đường vòng vượt MFA/passkey.
7. Áp dụng step-up, delay, notification, session restriction và review theo rủi ro.
8. Xây dựng test plan cho factor loss, factor compromise, replay, race condition và recovery abuse.

## 2. Recovery factor là gì?

Khi người dùng không thể đăng nhập bằng phương thức thông thường, hệ thống cần một cách xác minh khác để xác định họ có quyền khôi phục tài khoản. Recovery factor là một trong những bằng chứng đó. Nó có thể là một bí mật đã cấp trước, một authenticator khác, một kênh liên hệ đã xác minh hoặc bằng chứng được đánh giá qua quy trình hỗ trợ.

Recovery factor không nhất thiết là yếu tố đăng nhập thường ngày. Một recovery code có thể chỉ dùng một lần khi mất security key; một email dự phòng có thể chỉ nhận thông báo hoặc link khôi phục; một recovery contact có thể hỗ trợ xác nhận trong quy trình có nhiều bên.

### 2.1. Phân biệt các khái niệm

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Primary authenticator** | Phương thức người dùng thường dùng để đăng nhập | Passkey trên điện thoại |
| **Backup authenticator** | Authenticator thứ hai để tiếp tục đăng nhập khi thiết bị chính mất | Security key dự phòng |
| **Recovery factor** | Bằng chứng dùng trong quy trình phục hồi quyền truy cập | Recovery code hoặc kênh dự phòng |
| **Contact channel** | Kênh liên hệ để gửi thông báo hoặc hướng dẫn | Email, số điện thoại |
| **Identity proofing** | Xác minh người yêu cầu là cá nhân/tổ chức mà họ khai | Đối chiếu hồ sơ với nguồn authoritative |
| **Recovery process** | Toàn bộ quy trình quyết định và thực hiện khôi phục | Xác minh, chờ, thu hồi yếu tố cũ, cấp yếu tố mới |

Một email đã xác minh không tự động là bằng chứng danh tính mạnh. Nó chỉ chứng minh người dùng có khả năng truy cập hộp thư tại thời điểm kiểm tra, trong phạm vi rủi ro của nhà cung cấp email và cách tài khoản đó được bảo vệ.

### 2.2. Recovery không phải reset password đơn thuần

Người dùng có thể mất passkey nhưng vẫn biết password; mất điện thoại nhưng còn security key; mất mọi authenticator nhưng còn recovery code; hoặc tài khoản bị chiếm và attacker đã thay đổi recovery channel. Mỗi trường hợp cần quy trình khác nhau.

Recovery có thể bao gồm khôi phục danh tính, cấp credential mới, thu hồi credential cũ, kết thúc session, rà soát linked identity và khôi phục membership. Chỉ đổi password có thể không đủ nếu attacker còn refresh token, passkey hoặc API key.

## 3. Nguyên tắc thiết kế recovery factor

### 3.1. Không tạo đường vòng yếu hơn

Nếu đăng nhập yêu cầu passkey chống phishing nhưng recovery chỉ cần biết email, attacker có thể bỏ qua passkey bằng cách chiếm hộp thư. Khi đó mức bảo đảm thực tế của tài khoản bị giới hạn bởi recovery yếu nhất.

Recovery phải có mức bảo đảm tương xứng với tác động của tài khoản. Nếu không thể cung cấp recovery factor đủ mạnh, có thể cần human review, thời gian chờ, giới hạn quyền sau recovery hoặc xác minh bổ sung.

### 3.2. Đánh giá tính độc lập

Hai factor chỉ tăng độ tin cậy khi rủi ro compromise của chúng không hoàn toàn trùng nhau. Ví dụ:

- Password và email cùng dùng một password có thể bị chiếm cùng lúc;
- Điện thoại chứa cả app email, SMS và TOTP không tạo ra ba thiết bị độc lập;
- Recovery code lưu trong cùng điện thoại bị mất có thể mất cùng authenticator;
- Hai security key được cất ở hai địa điểm riêng thường có tính độc lập vật lý tốt hơn.

Không chỉ đếm số factor. Hãy xem chúng được lưu ở đâu, ai có quyền truy cập, có cùng recovery path hay không và điều gì xảy ra khi một thiết bị bị chiếm.

### 3.3. Tính khả dụng và khả năng tiếp cận

Recovery phải có thể sử dụng trong điều kiện người dùng thực sự gặp sự cố. Không yêu cầu duy nhất một số điện thoại nếu người dùng có thể đổi số hoặc mất SIM; không yêu cầu duy nhất một thiết bị nếu đó là thiết bị đang bị mất. Cung cấp phương án dự phòng đủ an toàn và có hướng dẫn lưu trữ trước khi xảy ra sự cố.

### 3.4. Giới hạn quyền sau recovery

Ngay sau khi recovery thành công, hệ thống có thể áp dụng thời gian bảo vệ:

- Thu hồi session và refresh token cũ;
- Yêu cầu đăng ký lại MFA/passkey;
- Tạm giới hạn thay đổi email, payment destination hoặc quyền quản trị;
- Gửi thông báo qua kênh cũ còn tin cậy;
- Theo dõi đăng nhập và hành động nhạy cảm trong khoảng thời gian xác định.

Thời gian chờ hoặc hạn chế phải dựa trên rủi ro, được giải thích và có đường xử lý cho trường hợp hợp lệ.

## 4. Các loại recovery factor

Không có một factor phù hợp mọi người dùng. Mỗi loại có ưu điểm, giới hạn và điều kiện vận hành riêng.

| Loại | Cách dùng | Điểm mạnh | Rủi ro/giới hạn |
| --- | --- | --- | --- |
| **Recovery code** | Nhập mã dùng một lần đã cấp trước | Không phụ thuộc mạng hoặc thiết bị đang mất | Có thể bị chụp/lưu không an toàn; phải bảo vệ như bí mật |
| **Backup passkey** | Dùng passkey trên thiết bị hoặc authenticator khác | Phishing-resistant nếu triển khai đúng WebAuthn | Có thể mất cùng thiết bị; đồng bộ passkey phụ thuộc tài khoản hệ sinh thái |
| **Security key dự phòng** | Dùng khóa vật lý thứ hai | Tách biệt thiết bị chính, có thể chống phishing | Có thể bị mất hoặc hỏng; cần lưu ở nơi an toàn |
| **Backup TOTP** | Dùng authenticator thứ hai hoặc secret dự phòng | Có thể hoạt động offline | Seed là bí mật lâu dài; mã có thể bị phishing/relay |
| **Email recovery** | Nhận link hoặc xác nhận tại hộp thư dự phòng | Dễ dùng và phổ biến | Hộp thư có thể bị chiếm; không mặc định mạnh hơn MFA |
| **Phone/SMS recovery** | Nhận OTP qua số đã xác minh | Phổ biến, dễ tiếp cận | SIM swap, port-out, chuyển tiếp SMS, mất số |
| **Recovery contact** | Người được chỉ định xác nhận theo quy trình | Có thể giúp người dùng không còn thiết bị | Social engineering, thông đồng, người liên hệ không sẵn có |
| **Helpdesk/administrator review** | Nhân viên xác minh theo quy trình | Hỗ trợ trường hợp mất mọi factor | Rủi ro insider, giả mạo và quy trình không nhất quán |
| **Certificate/PKI recovery** | Dùng certificate hoặc quy trình cấp lại certificate | Phù hợp môi trường quản lý thiết bị | Cần PKI, thu hồi và bảo vệ private key |

## 5. Recovery code

Recovery code là một bí mật ngẫu nhiên được tạo trước và cấp cho người dùng để sử dụng khi mất phương thức đăng nhập chính. Đây thường là phương án hữu ích vì không cần điện thoại, mạng di động hay hộp thư hoạt động tại thời điểm recovery.

### 5.1. Sinh mã

- Dùng CSPRNG với entropy đủ lớn;
- Tạo một hoặc nhiều mã riêng biệt, không dùng mã tuần tự;
- Không chứa user ID, email hoặc thông tin dễ đoán;
- Hiển thị một lần khi tạo hoặc cấp lại;
- Không gửi recovery code qua email/chat không được bảo vệ;
- Không ghi plaintext vào log, analytics hoặc support ticket.

### 5.2. Lưu trữ phía server

Nếu server chỉ cần xác minh mã do người dùng nhập, có thể lưu hash an toàn của recovery code thay vì plaintext. Khi người dùng nhập:

1. Chuẩn hóa định dạng theo quy tắc;
2. Tìm bản ghi phù hợp bằng cơ chế lookup an toàn;
3. So sánh hash bằng phương thức phù hợp;
4. Kiểm tra account, purpose, trạng thái và thời hạn;
5. Tiêu thụ mã nguyên tử;
6. Ghi audit mà không ghi mã.

Với mã entropy cao, hash mật mã phù hợp có thể dùng để lưu lookup; không áp dụng password hashing chậm một cách máy móc nếu thiết kế cần tra cứu token ngẫu nhiên. Chọn giải pháp theo threat model và thư viện đã được kiểm chứng.

### 5.3. One-time use và chống replay

Một recovery code chỉ được chấp nhận một lần. Việc kiểm tra và đánh dấu consumed phải nguyên tử để hai request đồng thời không thể cùng dùng một mã. Giới hạn số lần nhập sai theo account, IP/device signal và toàn dịch vụ.

### 5.4. Cấp lại bộ mã

Khi người dùng tạo bộ recovery code mới:

- Vô hiệu toàn bộ mã còn lại của bộ cũ;
- Hiển thị bộ mới một lần;
- Yêu cầu xác thực đủ mạnh trước khi cấp;
- Gửi thông báo tới kênh đã đăng ký;
- Ghi thời điểm và actor.

Không để mã cũ và mới cùng tồn tại vô thời hạn nếu người dùng tin rằng bộ cũ đã bị lộ.

## 6. Backup passkey và security key

Passkey/WebAuthn có thể là phương thức đăng nhập chính hoặc phương án dự phòng. Một người dùng có thể đăng ký nhiều passkey trên các thiết bị khác nhau hoặc thêm security key vật lý dự phòng.

### 6.1. Backup passkey

Backup passkey nên được đăng ký khi người dùng vẫn còn một phương thức xác thực đáng tin cậy. RP xác minh registration ceremony theo WebAuthn: challenge, origin, RP ID hash, credential ID và flags theo policy. Private key ở authenticator; server lưu public key và metadata cần thiết.

Passkey đồng bộ qua hệ sinh thái có thể giúp phục hồi khi đổi thiết bị, nhưng khả năng sử dụng phụ thuộc vào tài khoản đồng bộ, thiết bị và chính sách nhà cung cấp. Không mặc định mọi passkey được đồng bộ hoặc mọi thiết bị đều có thể khôi phục như nhau.

### 6.2. Security key dự phòng

Với tài khoản có giá trị cao, có thể cấp hai security key:

- Một key dùng thường ngày;
- Một key dự phòng cất ở nơi riêng, an toàn;
- Cả hai được đăng ký trong cùng account qua quy trình xác thực;
- Có nhãn để người dùng nhận biết và thu hồi đúng key;
- Kiểm tra định kỳ key dự phòng còn hoạt động.

Không để key dự phòng cắm thường trực cùng thiết bị chính nếu mục tiêu là tách biệt rủi ro vật lý.

### 6.3. Mất một passkey

Nếu còn passkey khác, người dùng có thể xác thực bằng key còn lại, sau đó thu hồi credential đã mất và đăng ký thay thế. Nếu không còn factor nào, cần chuyển sang recovery flow khác có assurance phù hợp; không cho phép support tự gắn passkey mới chỉ dựa trên email.

## 7. TOTP và authenticator dự phòng

TOTP có thể là recovery option nếu người dùng đã đăng ký một authenticator độc lập. Secret TOTP là bí mật dài hạn; bất kỳ ai có seed đều có thể tạo mã hợp lệ.

### 7.1. Dùng authenticator thứ hai

Người dùng có thể đăng ký TOTP trên thiết bị dự phòng khi vẫn còn đăng nhập và hoàn tất xác minh. Mỗi authenticator nên có record riêng để người dùng gỡ một thiết bị mà không phải reset toàn bộ MFA.

### 7.2. Lưu secret

Server cần bảo vệ TOTP seed bằng mã hóa phù hợp và quản lý khóa riêng. Không ghi provisioning URI hoặc seed vào log. Nếu hệ thống chỉ giữ một bản sao secret, việc backup database và key management cần được tính đến trong disaster recovery.

### 7.3. Giới hạn của TOTP

TOTP dễ triển khai nhưng mã có thể bị phishing hoặc relay theo thời gian. Không xem TOTP là phishing-resistant. Với tài khoản đặc quyền, ưu tiên passkey/security key hoặc phương thức có assurance phù hợp hơn.

## 8. Email recovery

Email recovery thường gửi link hoặc mã tới địa chỉ đã xác minh trước đó. Đây là một kênh hữu ích, nhưng độ mạnh phụ thuộc vào bảo mật hộp thư và việc email có được bảo vệ bằng MFA/passkey hay không.

### 8.1. Điều kiện sử dụng

- Email phải được xác minh và gắn với account từ trước;
- Không cho phép đổi email rồi dùng ngay email mới để recovery account cũ;
- Link/mã có purpose riêng, TTL ngắn và one-time use;
- Không chứa password hoặc credential mới trong email;
- Không tạo session đặc quyền chỉ từ việc mở link;
- Gửi thông báo tới kênh cũ khi recovery bắt đầu hoặc hoàn tất.

### 8.2. Hộp thư bị chiếm

Nếu attacker kiểm soát email, email recovery có thể trở thành đường takeover. Với account nhạy cảm, cần thêm factor độc lập, thời gian chờ, review hoặc giới hạn action sau recovery. Không coi email recovery và email notification là hai bằng chứng độc lập.

### 8.3. Email không còn truy cập

Người dùng không còn hộp thư phải có một quy trình khác như backup authenticator, recovery code hoặc identity proofing/support. Không yêu cầu họ truy cập lại chính email đã mất để chứng minh họ không còn truy cập email.

## 9. Phone và SMS recovery

SMS OTP dễ tiếp cận nhưng có các rủi ro đặc thù:

- SIM swap hoặc port-out;
- Nhân viên nhà mạng bị social engineering;
- SMS forwarding hoặc malware;
- Số điện thoại được tái cấp cho người khác;
- Roaming, mất sóng hoặc không còn giữ số.

### 9.1. Quản lý số điện thoại

Số điện thoại cần được xác minh trước khi trở thành recovery factor. Thay đổi số phải yêu cầu xác thực bằng factor hiện có hoặc quy trình recovery đủ mạnh. Không cho phép người dùng thay số trong cùng một phiên recovery chưa hoàn tất rồi dùng số mới để tự xác nhận.

### 9.2. OTP controls

- TTL ngắn;
- Giới hạn số lần thử và gửi lại;
- Rate limit theo account, destination và nguồn request;
- Không dùng lại OTP giữa các purpose;
- Không ghi plaintext OTP;
- Có cooldown và phát hiện SMS bombing;
- Không để thông báo lỗi tiết lộ account có tồn tại hay không.

### 9.3. Không dùng SMS làm fallback phổ quát

Nếu chính sách yêu cầu phishing resistance, SMS OTP không đáp ứng yêu cầu đó. Có thể dùng SMS cho tài khoản rủi ro thấp hoặc như một tín hiệu trong recovery có kiểm soát, nhưng không tự động hạ assurance của mọi account xuống SMS.

## 10. Recovery contact và social recovery

Một số hệ thống cho phép người dùng chỉ định người liên hệ đáng tin cậy hoặc nhóm người hỗ trợ recovery. Cách này có thể hữu ích khi người dùng mất mọi thiết bị, nhưng cần tránh biến người thân/bạn bè thành một điểm takeover dễ bị social engineering.

### 10.1. Thiết kế recovery contact

- Người liên hệ phải chấp nhận lời mời và xác minh danh tính của họ;
- Việc thêm hoặc thay recovery contact cần xác thực mạnh từ account owner;
- Thông báo tới các kênh hiện tại khi danh sách thay đổi;
- Có thời gian chờ trước khi contact mới được dùng;
- Quy định số người cần xác nhận và điều kiện quorum;
- Không tiết lộ dữ liệu account nhạy cảm cho contact;
- Ghi audit mọi yêu cầu và quyết định.

### 10.2. Quorum và độc lập

Nếu cần nhiều contact, yêu cầu hai trong ba người có thể giảm rủi ro một contact bị chiếm. Tuy nhiên, các contact có thể cùng một gia đình, cùng thiết bị hoặc cùng bị lừa; số lượng không đảm bảo độc lập. Hãy đánh giá quan hệ, kênh liên lạc và cách xác minh của từng contact.

### 10.3. Chống thông đồng và social engineering

Recovery contact chỉ cung cấp bằng chứng theo quy trình, không được tự cấp role hoặc credential. Có thể cần thêm thời gian chờ, thông báo cho account owner và xác minh độc lập trước khi thay đổi authenticator.

## 11. Helpdesk và administrator-assisted recovery

Helpdesk có thể hỗ trợ người dùng mất mọi factor, nhưng đây là điểm có nguy cơ social engineering và insider abuse cao.

### 11.1. Quy trình cần có

- Xác minh danh tính theo bằng chứng đã được tổ chức phê duyệt;
- Phân tách người tiếp nhận yêu cầu và người duyệt với account nhạy cảm;
- Không dùng câu hỏi bảo mật dựa trên thông tin công khai làm bằng chứng duy nhất;
- Không yêu cầu người dùng đọc password, OTP hoặc recovery code;
- Không cho nhân viên biết hoặc đặt password mới;
- Dùng recovery transaction có thời hạn, purpose và audit;
- Gửi thông báo qua kênh cũ nếu còn khả năng;
- Giới hạn quyền sau recovery và thu hồi session/token nghi ngờ.

### 11.2. Không biến support thành bypass

Nếu người dùng có thể gọi helpdesk, cung cấp tên, email và vài thông tin cá nhân để bỏ MFA, attacker sẽ nhắm vào helpdesk. Quy trình cần chống giả mạo, ghi nhận lý do ngoại lệ, review và giám sát các yêu cầu bất thường.

### 11.3. Break-glass account

Tổ chức có thể cần tài khoản khẩn cấp cho sự cố IdP hoặc mất hệ thống xác thực. Tài khoản này cần số lượng ít, quyền tối thiểu, credential được cất giữ có kiểm soát, phê duyệt kép, audit độc lập và diễn tập định kỳ. Không dùng break-glass như đường recovery tiện lợi hàng ngày.

## 12. Đánh giá độ mạnh và tính độc lập của recovery factor

Không nên xếp hạng factor chỉ bằng một bảng mạnh/yếu cố định. Đánh giá phụ thuộc vào account, threat model, thiết bị, kênh và quy trình.

| Factor | Phishing resistance | Phụ thuộc thiết bị/kênh | Điểm cần xem xét |
| --- | --- | --- | --- |
| Recovery code | Không chống phishing tự thân | Phụ thuộc nơi lưu | Bí mật có entropy cao, one-time use |
| Passkey/WebAuthn | Có thể chống phishing nhờ RP ID/origin | Authenticator và khả năng truy cập | User verification, đồng bộ và thiết bị dự phòng |
| Security key | Có thể chống phishing | Khóa vật lý | Bảo quản độc lập và quy trình thu hồi |
| TOTP | Không chống phishing tốt | App và seed | Seed compromise, relay và backup |
| Email link | Không chống phishing tự thân | Hộp thư | Bảo mật email và account linking |
| SMS OTP | Không chống phishing tốt | Số/SIM/nhà mạng | SIM swap, port-out và tái cấp số |
| Recovery contact | Phụ thuộc quy trình | Người liên hệ và kênh của họ | Social engineering và thông đồng |
| Helpdesk | Phụ thuộc proofing/controls | Nhân viên và quy trình | Insider risk, consistency và audit |

Với account có giá trị cao, recovery thường cần nhiều lớp bằng chứng và hạn chế sau khôi phục. Với account rủi ro thấp, có thể chấp nhận flow đơn giản hơn nhưng vẫn cần chống replay, brute force và account enumeration.

## 13. Recovery flow và ràng buộc giao dịch

Recovery factor chỉ là một phần của quy trình. Một flow tổng quát:

~~~mermaid
flowchart TD
    A["Người dùng yêu cầu recovery"] --> B["Tạo recovery transaction"]
    B --> C["Kiểm tra account state và rate limit"]
    C --> D["Chọn factor/bằng chứng phù hợp"]
    D --> E["Xác minh proof và purpose"]
    E --> F{"Đạt policy?"}
    F -->|"Không"| G["Từ chối / review / thử phương án hợp lệ"]
    F -->|"Có"| H["Áp dụng delay hoặc approval nếu cần"]
    H --> I["Thu hồi hoặc thay credential bị mất"]
    I --> J["Tạo credential mới và giới hạn session"]
    J --> K["Thông báo, audit và giám sát"]
~~~

### 13.1. Recovery transaction

Transaction cần ràng buộc:

- Subject/account reference;
- Purpose cụ thể: reset password, thay MFA, phục hồi passkey hay đổi contact;
- Factor được dùng và bằng chứng đã xác minh;
- Thời điểm tạo/hết hạn;
- Số lần thử và trạng thái;
- Tenant/client nếu account thuộc nhiều tổ chức;
- Recovery action dự kiến;
- Actor hoặc reviewer nếu có.

Một link khôi phục password không được dùng để thêm passkey hoặc thay email nếu purpose không cho phép. Nếu người dùng thay đổi mục tiêu trong flow, tạo transaction mới và xác minh lại theo policy.

### 13.2. Ràng buộc với account

Không cho phép người dùng nhập một email rồi nhận recovery token mà không chứng minh mối liên hệ với account. Token phải gắn server-side với subject đã xác định, không chỉ với chuỗi email từ request.

### 13.3. One-time consumption và race

Xác minh factor, cập nhật trạng thái và tiêu thụ token phải nguyên tử. Hai request đồng thời không được cùng khôi phục account hoặc cấp hai credential mới từ một proof. Cần idempotency cho retry sau timeout mà không cho phép replay.

## 14. Sau khi recovery thành công

Recovery thành công không có nghĩa mọi thứ trở lại trạng thái cũ. Cần xử lý các credential và session có thể đã bị attacker kiểm soát.

### 14.1. Thu hồi theo nguyên nhân

- Mất điện thoại: thu hồi authenticator/credential gắn với thiết bị đó;
- Mất security key: thu hồi credential ID tương ứng và kiểm tra key còn lại;
- Email bị chiếm: không tiếp tục tin email đó; xem xét thay contact và revoke session;
- Nghi ngờ password bị lộ: reset password, thu hồi refresh token và session theo policy;
- Compromise toàn account: thu hồi mọi session/token/API key/certificate liên quan và kiểm tra linked IdP.

### 14.2. Session sau recovery

Có thể cấp một recovery session giới hạn chỉ cho phép:

- Thiết lập password hoặc passkey mới;
- Đăng ký MFA dự phòng;
- Xem trạng thái recovery;
- Hoàn tất các bước bắt buộc.

Không cho recovery session truy cập dữ liệu nhạy cảm hoặc thay đổi payment destination/role trước khi hoàn tất enrollment và thời gian bảo vệ cần thiết.

### 14.3. Thông báo và cảnh báo

Thông báo cho kênh đã đăng ký trước recovery nếu còn tin cậy và cho kênh mới sau khi được xác minh. Nội dung nên nêu thời điểm, thay đổi đã xảy ra và cách báo cáo nếu không phải người dùng thực hiện. Không chứa password, OTP, recovery code hoặc token.

### 14.4. Thời gian chờ

Với thay đổi có rủi ro cao, có thể áp dụng cooldown trước khi cho phép hành động tiếp theo. Thời gian chờ không thay thế xác minh; nó tạo cơ hội phát hiện và phản ứng nếu recovery bị thực hiện bởi attacker. Phải có cơ chế xử lý khi người dùng thực sự cần truy cập khẩn cấp.

## 15. Account recovery trong SSO và tenant

Trong hệ thống federation, RP có thể không quản lý password của người dùng. Recovery thường diễn ra ở IdP; RP cần xử lý session, linked identity và membership của mình.

### 15.1. Recovery tại IdP

Người dùng khôi phục account ở IdP. RP chỉ nhận kết quả authentication mới sau khi IdP xác minh. RP không nên tự tạo đường recovery riêng yếu hơn để bỏ qua policy của IdP nếu danh tính được quản lý tập trung.

### 15.2. RP session còn tồn tại

Người dùng có thể khôi phục account tại IdP nhưng session RP cũ vẫn còn. Tổ chức cần logout/revocation protocol, session version hoặc kiểm tra account state để thu hồi session cũ theo SLA.

### 15.3. Nhiều tenant

Một người có thể có membership ở nhiều tenant. Recovery account toàn cục không nên tự cấp lại membership đã bị thu hồi ở tenant cụ thể. Sau recovery, RP vẫn kiểm tra membership và authorization hiện tại.

### 15.4. Linked identity bị compromise

Nếu một IdP liên kết bị chiếm, cần xem xét gỡ liên kết, thu hồi session và yêu cầu xác minh lại. Không tự động chuyển quyền sở hữu sang một IdP khác chỉ vì email trùng.

## 16. Những cuộc tấn công nhắm vào recovery

| Threat | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Email takeover** | Attacker chiếm hộp thư và dùng recovery link | Factor độc lập, notification và delay |
| **SIM swap** | Attacker chiếm số điện thoại | Không phụ thuộc SMS duy nhất; xác minh thay đổi số |
| **Recovery code theft** | Mã bị chụp hoặc lưu cùng thiết bị | Hiển thị một lần, hash server-side, revoke/regenerate |
| **Helpdesk social engineering** | Giả danh người dùng để nhân viên reset MFA | Proofing, dual control, audit và training |
| **Recovery contact collusion** | Contact bị lừa hoặc thông đồng | Quorum, delay, owner notification |
| **Account pre-hijacking** | Attacker đăng ký trước email/identity | Claim flow, identity binding và credential reset |
| **Token replay** | Link/code recovery bị dùng lại | TTL, purpose binding, one-time atomic consumption |
| **Enumeration** | Dò account qua thông báo recovery | Phản hồi chung và rate limit |
| **Brute force** | Đoán OTP/recovery code | Entropy, attempt limit và monitoring |
| **Session persistence** | Attacker giữ session sau recovery | Revoke session/token và kiểm tra version |
| **Factor replacement race** | Hai request thay recovery factor đồng thời | Transaction/lock và reauthentication |
| **Recovery bypass** | Recovery yếu hơn login | Assurance tương xứng, review và hạn chế sau recovery |

## 17. Audit, privacy và quản trị recovery factor

Recovery factor là dữ liệu bảo mật nhạy cảm. Hệ thống cần quản lý vòng đời từ đăng ký tới thu hồi.

### 17.1. Audit event

Nên ghi:

- Factor được đăng ký, xác minh, sử dụng, thay thế hoặc thu hồi;
- Recovery transaction được bắt đầu, duyệt, từ chối hoặc hết hạn;
- Actor, reviewer, tenant và purpose;
- Thời điểm, kết quả và reason code;
- Session/token được revoke;
- Notification được gửi và trạng thái gửi;
- Policy version và phương thức proofing.

Không ghi recovery code, OTP, TOTP seed, private key, activation token, session cookie hoặc refresh token nguyên dạng.

### 17.2. Hiển thị factor cho người dùng

Trang bảo mật có thể hiển thị:

- Loại factor;
- Nhãn do người dùng đặt;
- Thời điểm đăng ký và sử dụng gần nhất nếu có;
- Trạng thái active/revoked;
- Hướng dẫn tạo hoặc lưu phương án dự phòng.

Không hiển thị secret hoặc recovery code cũ. Không để user agent hoặc vị trí IP được diễn giải như tên thiết bị chắc chắn.

### 17.3. Retention và quyền truy cập

Giới hạn người có thể xem recovery event. Giữ audit đủ lâu cho điều tra theo policy, nhưng không giữ raw proof hoặc dữ liệu định danh vượt mục đích. Review quyền helpdesk/admin định kỳ và thu hồi khi nhân viên đổi vai trò.

## 18. Pseudocode recovery factor

### 18.1. Sử dụng recovery code

~~~text
use_recovery_code(account_ref, code, transaction):
    require transaction.account_ref == account_ref
    require transaction.purpose == ACCOUNT_RECOVERY
    require transaction.status == PENDING
    require now < transaction.expires_at
    enforce_attempt_limits(account_ref, request_context)

    begin transaction
    record = find_recovery_code_for_update(account_ref, secure_lookup(code))
    require record exists
    require record.status == UNUSED
    verify_code_hash(code, record.hash)
    mark_code_consumed(record)
    mark_recovery_proof_verified(transaction)
    commit

    continue_recovery_with_limited_session(transaction)
~~~

### 18.2. Thay factor bị mất

~~~text
replace_lost_factor(account, old_factor_ref, new_factor_proof):
    require account_is_eligible_for_recovery(account)
    require recovery_policy_satisfied(account)
    verify_new_factor_registration(new_factor_proof)

    begin transaction
    lock_account_security_state(account)
    require old_factor_belongs_to_account(old_factor_ref, account)
    revoke_factor(old_factor_ref)
    bind_new_factor_to_account(new_factor_proof, account)
    revoke_sessions_and_tokens_required_by_policy(account)
    record_audit_without_secrets(account)
    commit

    notify_existing_verified_channels(account)
~~~

Pseudocode chỉ mô tả nguyên tắc. Triển khai cần xử lý factor uniqueness, concurrent updates, notification retry, key management, recovery policy, idempotency và các thao tác ngoài database.

## 19. Kiểm thử recovery factor

Test trong môi trường staging với account, factor và contact giả lập. Không dùng recovery code hoặc OTP của người dùng thật.

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Recovery code | Mã hợp lệ chưa dùng | Được chấp nhận theo đúng purpose |
| Code replay | Dùng lại mã đã consumed | Từ chối |
| Concurrent use | Hai request dùng cùng mã | Chỉ một request thành công |
| Wrong account | Mã của account A dùng cho account B | Từ chối |
| Wrong purpose | Link email dùng để thêm passkey | Từ chối |
| Expiry | Recovery token hết hạn | Từ chối |
| Brute force | Nhập sai nhiều lần | Rate limit/cooldown được áp dụng |
| Regeneration | Tạo bộ recovery code mới | Bộ cũ bị vô hiệu |
| Backup passkey | Dùng passkey dự phòng hợp lệ | Xác minh đúng subject và RP |
| Lost key | Security key bị mất và revoke | Credential ID đó không còn được chấp nhận |
| TOTP backup | Seed dự phòng đúng và chưa revoke | Xác minh theo time window/policy |
| Email takeover | Chỉ kiểm soát mailbox nhưng account yêu cầu factor độc lập | Không thể bypass policy |
| SIM swap | Số điện thoại mới được chuyển quyền sở hữu | Không tự động thay recovery factor |
| Helpdesk | Caller chỉ biết thông tin công khai | Không được reset MFA |
| Recovery contact | Một contact xác nhận khi policy cần quorum | Không hoàn tất nếu chưa đủ quorum |
| Contact change | Đổi email rồi lập tức dùng email mới recovery | Bị chặn theo policy/cooldown |
| Session revoke | Recovery do compromise | Session/token cũ bị thu hồi theo SLA |
| Limited session | Recovery thành công nhưng enrollment chưa xong | Chỉ truy cập chức năng recovery được phép |
| Tenant | Recovery account toàn cục sau khi rời tenant A | Không tự cấp lại membership A |
| Notification | Thêm factor hoặc recovery hoàn tất | Gửi thông báo không chứa bí mật |
| Logging | Bật debug/trace | Không log secret, OTP, code hoặc token |

### 19.1. Bất biến bảo mật

- Recovery factor phải gắn với đúng account và purpose;
- Factor dùng một lần không thể được replay hoặc tiêu thụ hai lần;
- Recovery không được làm giảm assurance dưới policy của account;
- Factor mới không được kích hoạt trước khi xác minh đúng transaction;
- Session/token nghi ngờ được xử lý theo policy sau recovery;
- Helpdesk và recovery contact không tự cấp quyền vượt quy trình;
- Membership/authorization được đánh giá độc lập với account recovery;
- Không ghi bí mật recovery vào log hoặc notification.

## 20. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Email là recovery duy nhất cho account passkey | Hộp thư bị chiếm sẽ bypass passkey | Factor độc lập hoặc proofing bổ sung |
| SMS là fallback bắt buộc cho mọi account | SIM swap trở thành đường takeover | Phương thức thay thế theo assurance |
| Recovery code không one-time | Replay và chiếm account | Atomic consumption và revoke |
| Recovery code lưu plaintext | DB leak làm lộ toàn bộ mã | Hash/reference an toàn |
| Tạo recovery code mới nhưng giữ mã cũ | Mã đã lộ vẫn hoạt động | Revoke toàn bộ bộ cũ |
| Helpdesk reset MFA theo email/tên | Social engineering | Proofing, dual control và audit |
| Cho phép đổi contact trong cùng recovery | Attacker chuyển kênh rồi chiếm account | Tách transaction, delay và xác minh độc lập |
| Không revoke session sau compromise | Attacker tiếp tục dùng session cũ | Session/token revocation |
| Recovery session có quyền đầy đủ | Attacker truy cập trước khi hoàn tất enrollment | Limited recovery session |
| Factor cùng nằm trên một thiết bị | Mất thiết bị làm mất tất cả factor | Phân tán phương án dự phòng |
| Recovery contact không có quorum | Một người bị lừa đủ để takeover | Quorum, delay và owner notification |
| Recovery không kiểm tra tenant | Account khôi phục nhận lại quyền cũ sai phạm vi | Membership/authorization check |

## 21. Checklist production

1. **Threat model:** Tài khoản có giá trị gì và attacker có thể chiếm factor/kênh nào?
2. **Factor inventory:** Người dùng có bao nhiêu factor đăng nhập và recovery đang active?
3. **Independence:** Các factor dự phòng có cùng phụ thuộc vào một thiết bị, mailbox hoặc tài khoản cloud không?
4. **Assurance:** Recovery đáp ứng mức bảo đảm cần thiết của account và action?
5. **Enrollment:** Factor được đăng ký khi account đã xác thực đủ mạnh?
6. **Storage:** Recovery code/seed/private key được bảo vệ; secret không xuất hiện trong log?
7. **Purpose binding:** Token và proof gắn đúng subject, tenant, purpose và transaction?
8. **Expiry/replay:** Có TTL, one-time use, atomic consumption và attempt limit?
9. **Contact security:** Email/phone được xác minh trước; thay đổi contact có reauthentication và delay phù hợp?
10. **Helpdesk:** Có proofing, phân tách nhiệm vụ, audit và kiểm soát insider?
11. **Recovery session:** Quyền sau recovery có giới hạn tới khi hoàn tất credential setup?
12. **Revocation:** Session, refresh token, passkey, certificate và API key bị mất/compromise được xử lý?
13. **Notification:** Kênh cũ và mới nhận thông báo phù hợp, không chứa secret?
14. **Tenant:** Recovery không tự cấp lại membership hoặc role đã bị thu hồi?
15. **Privacy:** Thu thập bằng chứng tối thiểu, retention và access control rõ?
16. **Testing:** Đã test replay, race, SIM swap, mailbox takeover, helpdesk abuse và account enumeration?

## 22. Bài tập tình huống

Một nền tảng học tập yêu cầu giảng viên đăng nhập bằng passkey. Khi mất điện thoại, giảng viên có thể nhập email để nhận link recovery. Link cho phép đặt password mới, thêm passkey mới và giữ nguyên mọi session cũ. Recovery code được hiển thị trong trang hồ sơ nhưng không có giới hạn số lần dùng. Helpdesk có thể gỡ MFA nếu người gọi cung cấp email và mã học viên.

**Yêu cầu:**

1. Xác định ít nhất **tám lỗ hổng** trong recovery factor, token lifecycle, helpdesk và session management.
2. Thiết kế bộ recovery factor dự phòng cho giảng viên: security key thứ hai, recovery code và phương án support.
3. Đề xuất quy trình dùng email recovery mà không biến mailbox thành đường bypass passkey.
4. Xác định cách lưu, tiêu thụ và cấp lại recovery code.
5. Thiết kế recovery session giới hạn, thu hồi session cũ và thông báo tới kênh đã đăng ký.
6. Xây dựng test cho replay, brute force, helpdesk social engineering và concurrent recovery.

**Gợi ý đối chiếu:** recovery phải có assurance tương xứng; email không phải bằng chứng duy nhất cho account nhạy cảm; recovery code cần entropy, hash và one-time use; helpdesk cần proofing; session/token cũ cần revoke theo policy; recovery session chỉ có quyền giới hạn.

## 23. Ghi nhớ

- **Recovery factor** là bằng chứng dự phòng để lấy lại quyền truy cập; nó có thể là recovery code, backup authenticator, email/phone, recovery contact hoặc quy trình support.
- Recovery yếu hơn login sẽ trở thành đường vòng cho attacker. Đánh giá cả assurance, tính độc lập và nơi lưu factor.
- Recovery code cần entropy cao, hiển thị một lần, lưu an toàn, giới hạn thử và tiêu thụ nguyên tử một lần.
- Email và SMS là kênh tiện dụng nhưng có rủi ro mailbox takeover, SIM swap và phishing; không mặc định chúng đáp ứng phishing resistance.
- Backup passkey/security key cần được đăng ký trước khi mất factor chính và có cách thu hồi riêng.
- Helpdesk/recovery contact cần proofing, phân quyền, audit, delay hoặc quorum theo rủi ro.
- Sau recovery, thu hồi credential/session/token bị mất hoặc nghi compromise; giới hạn session cho tới khi hoàn tất thiết lập mới.
- Recovery không tự cấp lại tenant membership hay authorization; quyền hiện tại phải được kiểm tra độc lập.

Recovery an toàn khi người dùng có phương án dự phòng thực sự sử dụng được, còn hệ thống bảo đảm rằng **bằng chứng khôi phục đủ mạnh, gắn đúng tài khoản, chỉ dùng đúng mục đích và không để credential hoặc session cũ tiếp tục nằm trong tay attacker**.
