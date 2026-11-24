# Recovery khi mất thiết bị — Khôi phục tài khoản passwordless an toàn

Với phương thức **passwordless** như passkey, người dùng không cần nhập mật khẩu để chứng minh quyền kiểm soát tài khoản. Thay vào đó, thiết bị hoặc authenticator giữ private key và ký challenge; dịch vụ kiểm tra chữ ký bằng public key đã đăng ký. Cách này có thể chống phishing rất tốt, nhưng tạo ra một câu hỏi vận hành quan trọng: **người dùng sẽ lấy lại quyền truy cập thế nào khi mất điện thoại, máy tính hoặc khóa bảo mật?**

**Recovery khi mất thiết bị** là quy trình khôi phục quyền kiểm soát tài khoản và thiết lập lại authenticator sau khi thiết bị hoặc credential không còn khả dụng. Quy trình phải chứng minh người yêu cầu có quyền với tài khoản ở mức phù hợp, thu hồi những credential/phiên có nguy cơ bị chiếm và ghi nhận thay đổi. Nếu đường recovery chỉ cần một email dễ bị chiếm, nó có thể trở thành lối tắt vượt qua chính cơ chế passwordless chống phishing.

Bài học này thuộc chương **Passwordless** trong nền tảng authentication. Ta sẽ phân biệt khôi phục thiết bị với khôi phục tài khoản, thiết kế các phương án dự phòng trước khi sự cố xảy ra, xử lý từng trường hợp mất thiết bị, bảo vệ token recovery, thu hồi phiên và kiểm thử các đường tấn công.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **passkey đồng bộ (syncable)**, passkey gắn với thiết bị (device-bound), security key và tài khoản nền tảng dùng để đồng bộ.
2. Phân biệt **khôi phục thiết bị/authenticator**, **khôi phục tài khoản tại dịch vụ (Relying Party)** và **khôi phục tài khoản nền tảng/IdP**.
3. Xây dựng kế hoạch dự phòng trước sự cố: nhiều authenticator, recovery code, thiết bị tin cậy và quy trình hỗ trợ.
4. Thiết kế recovery flow theo bằng chứng còn lại và mức rủi ro; không tự hạ yêu cầu bảo đảm qua một kênh yếu.
5. Bảo vệ recovery token, chống replay, enumeration, brute force, phishing và social engineering.
6. Thu hồi credential đã mất, phiên, refresh token và quyền truy cập có nguy cơ bị lộ.
7. Viết threat model, sơ đồ trạng thái và bộ kiểm thử cho các tình huống mất một thiết bị hoặc mất toàn bộ phương thức xác thực.

## 2. Vì sao passwordless vẫn cần recovery?

Passkey thường dựa trên cặp khóa mật mã: private key được authenticator bảo vệ, public key được dịch vụ đăng ký. Khi đăng nhập, dịch vụ tạo challenge mới; authenticator ký dữ liệu xác thực và dịch vụ kiểm tra chữ ký, origin/RP ID cùng các điều kiện liên quan. Private key không cần gửi cho dịch vụ.

Cơ chế này giải quyết nhiều rủi ro của mật khẩu, đặc biệt là việc bí mật bị nhập vào website giả. Tuy nhiên, nó không loại bỏ các tình huống:

- Người dùng làm mất hoặc bị trộm điện thoại có passkey.
- Máy tính hỏng, bị xóa dữ liệu hoặc cài lại hệ điều hành.
- Khóa bảo mật USB/NFC bị thất lạc.
- Người dùng không còn truy cập tài khoản nền tảng dùng để đồng bộ passkey.
- Thiết bị mới không thể khôi phục passkey đã đồng bộ.
- Người dùng mất tất cả authenticator đã đăng ký.
- Kẻ tấn công chiếm được thiết bị hoặc tài khoản nền tảng, rồi tìm cách thay đổi credential.
- Nhân viên hỗ trợ bị thuyết phục bỏ qua quy trình xác minh.

**Passwordless không đồng nghĩa với không có recovery.** Một hệ thống an toàn phải thiết kế đường dự phòng ngay khi ghi danh credential, và phải đánh giá đường dự phòng bằng cùng mô hình đe dọa như đường đăng nhập chính.

## 3. Phân biệt ba phạm vi khôi phục

Một người dùng có thể dựa vào nhiều hệ thống khác nhau để đăng nhập. Khi xảy ra mất thiết bị, cần xác định dịch vụ nào có thể khôi phục phần nào.

| Phạm vi | Hệ thống chịu trách nhiệm | Ví dụ | RP cần làm gì? |
| --- | --- | --- | --- |
| **Authenticator/device recovery** | Hệ điều hành, nền tảng đồng bộ passkey, nhà cung cấp security key hoặc người dùng | Khôi phục tài khoản Apple/Google/Microsoft theo quy trình của nhà cung cấp để lấy lại passkey đã đồng bộ; dùng khóa bảo mật dự phòng | Chỉ nhận assertion hợp lệ theo credential đã đăng ký; không giả định RP có thể khôi phục private key. |
| **Account recovery tại RP** | Dịch vụ người dùng muốn truy cập | LearnHub xác minh chủ tài khoản, cho ghi danh passkey mới và thu hồi passkey cũ | Thiết kế bằng chứng, kiểm soát, thông báo, audit và thu hồi. |
| **Identity Provider/platform account recovery** | IdP hoặc tài khoản nền tảng bên ngoài | Người dùng mất quyền truy cập tài khoản trường hoặc tài khoản đồng bộ passkey | Xác minh kết quả liên kết theo issuer/subject và policy; không tự coi recovery tại IdP là đã khôi phục mọi quyền nội bộ. |

### 3.1. Passkey đồng bộ và passkey gắn với thiết bị

| Đặc điểm | Passkey đồng bộ | Passkey device-bound |
| --- | --- | --- |
| Nơi lưu private key | Được đồng bộ an toàn qua hệ sinh thái/nền tảng của nhà cung cấp | Gắn với authenticator hoặc thiết bị cụ thể theo cách triển khai |
| Khi mất một thiết bị | Có thể khôi phục trên thiết bị khác nếu người dùng còn khôi phục được tài khoản nền tảng và đáp ứng bảo vệ của nhà cung cấp | Cần authenticator dự phòng hoặc quy trình recovery tại RP |
| Phụ thuộc nhà cung cấp | Phụ thuộc cơ chế đồng bộ và recovery của nền tảng | Có thể ít phụ thuộc đồng bộ, nhưng vẫn cần quản lý vòng đời thiết bị/khóa |
| Rủi ro cần xét | Chiếm quyền tài khoản nền tảng hoặc hệ sinh thái đồng bộ; thiết bị khác được đồng bộ có thể trở thành điểm truy cập | Mất thiết bị/khóa; khó khôi phục nếu không có credential khác |
| Kiểm soát của RP | RP không trực tiếp quản lý bản sao private key đồng bộ | RP cũng không có private key; chỉ quản lý credential/public key đã đăng ký |

RP thường không thể tự biết mọi chi tiết bảo vệ và quy trình recovery nội bộ của nền tảng đồng bộ. **Không nên tuyên bố một passkey đồng bộ luôn an toàn hơn hoặc kém an toàn hơn passkey device-bound**; cần đánh giá chính sách nhà cung cấp, loại tài khoản, bảo vệ thiết bị và khả năng khôi phục.

Trong WebAuthn, các cờ backup eligibility/state có thể cung cấp thông tin liên quan đến khả năng sao lưu/đồng bộ của credential theo chuẩn. Chúng không phải bằng chứng đầy đủ rằng người dùng có thể khôi phục tài khoản nền tảng, cũng không thay thế chính sách recovery của RP.

### 3.2. Một thiết bị có thể chứa nhiều yếu tố nhưng vẫn là một điểm lỗi

Người dùng có thể mở khóa passkey bằng PIN hoặc sinh trắc. Điều đó không có nghĩa họ có nhiều thiết bị dự phòng. Nếu mất thiết bị duy nhất, cả passkey và cơ chế mở khóa cục bộ có thể không còn dùng được.

Vì vậy hãy phân biệt:

- **Số yếu tố trong một lần xác thực**: cách authenticator chứng minh quyền kiểm soát khóa và xác minh người dùng.
- **Số authenticator độc lập đã ghi danh**: số đường có thể dùng khi một thiết bị mất.
- **Số kênh recovery độc lập**: số cách khôi phục có thể sử dụng khi các authenticator chính không còn.

Một passkey đa yếu tố không tự tạo ra tính dự phòng nếu nó chỉ tồn tại trên một thiết bị.

## 4. Chuẩn bị recovery trước khi mất thiết bị

Recovery tốt bắt đầu từ lúc người dùng còn đăng nhập bình thường. Đừng chờ đến khi người dùng mất thiết bị mới phát hiện họ không có phương thức dự phòng.

### 4.1. Ghi danh nhiều authenticator

Khuyến khích người dùng có ít nhất hai đường xác thực độc lập khi rủi ro và trải nghiệm cho phép, ví dụ:

- Passkey trên điện thoại cá nhân.
- Passkey trên máy tính hoặc một thiết bị khác được bảo vệ.
- Security key vật lý dự phòng cất ở nơi an toàn.
- Một phương thức dự phòng được tổ chức phê duyệt cho tài khoản có yêu cầu cao.

Hai passkey trên cùng một thiết bị hoặc cùng một hệ sinh thái không nhất thiết là hai miền lỗi độc lập. Nếu tài khoản nền tảng bị khóa, nhiều passkey đồng bộ có thể cùng không truy cập được. Hãy ghi nhận **điều gì sẽ xảy ra nếu thiết bị, nhà cung cấp hoặc kênh recovery cùng mất**.

### 4.2. Recovery code

Recovery code là mã dự phòng được dịch vụ tạo trước và người dùng lưu giữ an toàn. Một thiết kế phù hợp nên:

- Sinh bằng bộ tạo số ngẫu nhiên mật mã, có entropy đủ cao.
- Gắn với đúng account, mục đích và phiên bản bộ mã.
- Chỉ hiển thị một lần khi tạo hoặc tái tạo; hướng dẫn lưu ngoại tuyến hoặc trong password manager an toàn.
- Không lưu mã rõ trong database; lưu verifier/hash phù hợp và so sánh an toàn khi sử dụng.
- Mỗi mã chỉ được dùng một lần; khi xác nhận thành công phải tiêu thụ nguyên tử.
- Có giới hạn thử, thời hạn hoặc quy tắc thay bộ mã theo chính sách.
- Cảnh báo người dùng khi sử dụng mã và cho phép tạo bộ mới sau khi xác thực đủ mạnh.
- Không để recovery code nằm trong cùng thiết bị hoặc tài khoản mà nó được dùng để khôi phục, nếu điều đó tạo một điểm lỗi chung.

Recovery code là một credential nhạy cảm. Ai có mã có thể có khả năng khôi phục, vì vậy cần bảo vệ tương đương một phương thức xác thực quan trọng.

### 4.3. Thiết lập và kiểm tra kênh thông báo

Đăng ký email/số điện thoại liên lạc có thể hữu ích để thông báo sự cố, nhưng **khả năng nhận email/SMS không tự động đủ làm bằng chứng duy nhất** để vượt qua chính sách passkey chống phishing. Xác minh kênh, bảo vệ thay đổi kênh và thông báo đến địa chỉ cũ trước khi áp dụng thay đổi nhạy cảm.

### 4.4. Ghi nhận kế hoạch dự phòng

Cho người dùng xem các authenticator đã ghi danh với thông tin dễ nhận biết: tên thiết bị, loại, ngày thêm, lần dùng gần nhất nếu phù hợp. Tránh hiển thị dữ liệu nhạy cảm không cần thiết. Cung cấp hướng dẫn cách thu hồi thiết bị bị mất và cách lấy lại quyền truy cập.

Ví dụ checklist trước sự cố:

- [ ] Có ít nhất một authenticator thứ hai được ghi danh.
- [ ] Đã tạo và lưu recovery code ở nơi độc lập.
- [ ] Email/số điện thoại thông báo đã được xác minh và bảo vệ.
- [ ] Người dùng biết cách báo mất thiết bị và xem danh sách credential.
- [ ] Tài khoản quản trị có quy trình recovery riêng và audit.
- [ ] Nhóm hỗ trợ biết cách xác minh yêu cầu mà không hỏi mật khẩu, OTP hoặc recovery code qua chat.

## 5. Phân loại tình huống mất thiết bị

Không phải mọi trường hợp mất thiết bị đều giống nhau. Mức rủi ro phụ thuộc thiết bị có bị trộm hay chỉ hỏng, có khóa màn hình không, người khác có thể mở khóa không và phiên ứng dụng còn hoạt động không.

| Tình huống | Rủi ro chính | Hướng xử lý |
| --- | --- | --- |
| Thiết bị hỏng, người dùng còn authenticator khác | Mất khả năng dùng một credential | Xác thực bằng credential còn lại; đăng ký thiết bị mới; xóa credential cũ khi chắc chắn không dùng được. |
| Thiết bị thất lạc nhưng có khóa màn hình và chưa rõ ai giữ | Credential/phiên có thể bị lạm dụng | Báo mất, đánh giá rủi ro, thu hồi phiên và credential nếu cần; không chờ đến khi có bằng chứng sử dụng trái phép. |
| Thiết bị bị trộm khi đang mở khóa hoặc có phiên hoạt động | Nguy cơ truy cập tức thời | Ưu tiên khóa/thu hồi từ xa nếu có, thu hồi phiên/token và credential liên quan, thông báo, điều tra. |
| Mất một security key nhưng còn passkey khác | Mất một authenticator | Dùng authenticator còn lại để xác thực lại, ghi danh khóa mới và thu hồi khóa mất. |
| Mất thiết bị nhưng còn passkey đồng bộ trên thiết bị khác | Có thể tiếp tục đăng nhập qua thiết bị còn lại | Đánh giá cả tài khoản nền tảng đồng bộ; thu hồi thiết bị bị mất và phiên liên quan. |
| Mất quyền truy cập tài khoản nền tảng đồng bộ | Không khôi phục được passkey đồng bộ | Làm recovery với nhà cung cấp nền tảng; RP vẫn áp policy của mình trước khi chấp nhận thay đổi credential hoặc phiên. |
| Mất toàn bộ authenticator và recovery code | Không còn bằng chứng tự phục vụ đã ghi danh | Dùng quy trình recovery tăng cường/identity proofing phù hợp; không bỏ qua MFA bằng email đơn thuần. |

**Điểm phân biệt quan trọng:** “Tôi không còn điện thoại” chưa đủ để biết thiết bị đã bị đánh cắp, còn mở phiên hay chỉ bị hỏng. Quy trình tiếp nhận cần hỏi thông tin tối thiểu để phân loại rủi ro, nhưng không được yêu cầu người dùng tiết lộ bí mật xác thực.

## 6. Quy trình recovery tại Relying Party

Giả sử dịch vụ **StudyHub** sử dụng passkey. Người dùng An mất điện thoại đã đăng ký. StudyHub cần quyết định liệu An còn authenticator khác, recovery code, passkey đồng bộ hay cần quy trình hỗ trợ.

### 6.1. Các nguyên tắc bắt buộc

1. **Định danh đúng tài khoản:** yêu cầu recovery phải gắn với account ID nội bộ đã xác định bằng quy trình đáng tin cậy.
2. **Đánh giá bằng chứng còn lại:** ưu tiên authenticator dự phòng đã ghi danh; nếu không có, áp recovery policy theo mức rủi ro.
3. **Giao dịch có thời hạn:** yêu cầu recovery, challenge và token phải khó đoán, hết hạn và chống replay.
4. **Không tự hạ assurance:** nếu tài khoản yêu cầu xác thực chống phishing, một email dễ bị chiếm không tự đáp ứng điều kiện.
5. **Ghi danh credential mới có kiểm soát:** yêu cầu chứng minh quyền đủ mạnh trước khi thêm passkey; thông báo thay đổi.
6. **Thu hồi có chủ đích:** loại bỏ credential bị mất và phiên/token có nguy cơ; không xóa mọi credential dự phòng còn an toàn mà không có lý do.
7. **Audit và thông báo:** lưu sự kiện cần thiết, thông báo qua kênh đã đăng ký và theo dõi hoạt động sau recovery.

### 6.2. Cây quyết định

~~~mermaid
flowchart TD
    A["Người dùng báo mất thiết bị"] --> B["Xác định account và phân loại sự cố"]
    B --> C{"Còn authenticator đã ghi danh?"}
    C -->|Có| D["Xác thực bằng authenticator còn lại"]
    D --> E["Ghi danh thiết bị/passkey mới"]
    E --> F["Thu hồi credential và phiên có nguy cơ"]
    C -->|Không| G{"Có recovery code hợp lệ?"}
    G -->|Có| H["Xác minh và tiêu thụ recovery code một lần"]
    H --> E
    G -->|Không| I{"Có thể khôi phục passkey đồng bộ?"}
    I -->|Có| J["Khôi phục tài khoản nền tảng theo quy trình nhà cung cấp"]
    J --> K["Đăng nhập lại và đánh giá policy tại RP"]
    K --> E
    I -->|Không| L["Quy trình recovery tăng cường / hỗ trợ"]
    L --> M["Xác minh bằng chứng phù hợp và thời gian chờ nếu cần"]
    M --> N["Cho phép ghi danh lại theo policy"]
    N --> F
~~~

Đây là cây quyết định khái niệm. Thứ tự phương án có thể thay đổi theo loại tài khoản và bằng chứng còn lại. Với tài khoản quản trị hoặc tài khoản tài chính, có thể cần phê duyệt bổ sung, thời gian chờ và kiểm soát hai người.

### 6.3. Luồng tổng thể

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant RP as StudyHub RP
    participant V as Authenticator / recovery verifier
    participant DB as Credential và session store
    participant N as Kênh thông báo
    U->>RP: Báo mất thiết bị, yêu cầu recovery
    RP->>RP: Xác định account, rate limit, tạo recovery transaction
    RP-->>U: Hướng dẫn phương thức dự phòng được phép
    U->>V: Cung cấp bằng chứng còn lại
    V-->>RP: Kết quả xác minh
    RP->>RP: Kiểm tra policy, freshness, ràng buộc transaction
    RP-->>U: Yêu cầu đăng ký passkey mới
    U->>RP: Hoàn tất WebAuthn registration
    RP->>RP: Xác minh challenge, origin, RP ID và attestation theo policy
    RP->>DB: Lưu public key/credential mới
    RP->>DB: Thu hồi credential mất và phiên có nguy cơ
    RP->>N: Gửi thông báo recovery và thay đổi credential
    RP-->>U: Hoàn tất hoặc thông báo bước tiếp theo
~~~

RP không nhận private key của passkey mới. Nó xác minh phản hồi đăng ký WebAuthn và lưu public key/credential ID cùng metadata cần thiết.

## 7. Các phương án recovery và mức bảo đảm

Không có một phương thức recovery phù hợp cho mọi tài khoản. Hãy đánh giá **bằng chứng thực tế**, khả năng bị chiếm quyền và hậu quả nếu chấp nhận nhầm người.

| Phương án | Điểm mạnh | Giới hạn/rủi ro | Dùng khi |
| --- | --- | --- | --- |
| Authenticator thứ hai đã ghi danh | Bằng chứng đã được liên kết trước với tài khoản; có thể giữ mức bảo đảm cao | Có thể cùng bị mất hoặc thuộc cùng miền lỗi | Lựa chọn ưu tiên khi còn thiết bị/khóa dự phòng. |
| Passkey đồng bộ trên thiết bị khác | Khôi phục trải nghiệm nhanh nếu hệ sinh thái còn truy cập | Phụ thuộc recovery của tài khoản nền tảng và thiết bị đồng bộ | Người dùng còn thiết bị tin cậy, tài khoản nền tảng an toàn. |
| Recovery code một lần | Không cần thiết bị cũ; đã được cấp trước | Có thể bị chụp ảnh, lưu chung thiết bị hoặc lộ qua phishing | Phương thức dự phòng khi được bảo vệ và lưu độc lập. |
| Security key dự phòng | Khóa vật lý độc lập, có thể chống phishing | Có thể thất lạc; cần ghi danh và quản lý trước | Tài khoản quan trọng hoặc người dùng có nhu cầu assurance cao. |
| Recovery qua IdP/tài khoản nền tảng | Nhà cung cấp có thể có quy trình xác minh và thiết bị dự phòng | RP không kiểm soát toàn bộ quy trình; recovery IdP không tự chứng minh quyền trong ứng dụng | Passkey đồng bộ hoặc federated identity. |
| Hỗ trợ thủ công/identity proofing | Có thể xử lý trường hợp mất mọi credential | Dễ bị social engineering, giả mạo giấy tờ hoặc thông đồng; tốn thời gian | Trường hợp không còn bằng chứng tự phục vụ và có quy trình được kiểm soát. |
| Email/SMS link đơn lẻ | Dễ sử dụng, phổ biến | Hộp thư/SIM có thể bị chiếm; không tương đương passkey chống phishing | Chỉ cho tác vụ rủi ro thấp nếu threat model và policy cho phép; không làm lối tắt cho tài khoản assurance cao. |

### 7.1. Recovery không được mạnh hơn một cách giả tạo

Một recovery code có thể được thiết kế như bí mật ngẫu nhiên có entropy cao, dùng một lần. Tuy nhiên, nếu mã được lưu trong ảnh chụp trên chính điện thoại bị mất, nó không còn là kênh độc lập. Tương tự, email có thể được bảo vệ bằng passkey nhưng nếu quy trình reset email chỉ cần SMS yếu, toàn bộ chuỗi vẫn có điểm yếu.

Đánh giá **đường khôi phục thực tế từ đầu đến cuối**:

- Ai có thể truy cập kênh recovery?
- Kênh đó được ghi danh và xác minh thế nào?
- Token/mã có thể bị đánh cắp hoặc replay không?
- Người dùng có nhận biết khi recovery bắt đầu/hoàn tất không?
- Sau recovery, attacker có thể đổi thêm yếu tố hoặc khóa chủ tài khoản không?
- Mức assurance của tài khoản có bị hạ vĩnh viễn hay chỉ tạm thời?

### 7.2. Thời gian chờ và hạn chế sau recovery

Với tài khoản rủi ro cao, có thể áp dụng thời gian chờ sau khi mất mọi authenticator hoặc dùng hỗ trợ thủ công. Trong khoảng đó, hạn chế hành động có tác động lớn như chuyển tài sản, thêm quản trị viên, đổi thông tin khôi phục hoặc xuất dữ liệu. Thông báo tới kênh cũ và cung cấp cách báo cáo nếu không phải chủ tài khoản.

Thời gian chờ không thay thế bằng chứng danh tính. Nó chỉ tạo cơ hội phát hiện và ngăn chặn trước khi một thay đổi nhạy cảm có hiệu lực. Phải có chính sách ngoại lệ được kiểm soát cho trường hợp khẩn cấp.

## 8. Recovery code và token: thiết kế chi tiết

Một recovery flow thường có hai loại dữ liệu:

- **Recovery code dài hạn**: được tạo trước và người dùng giữ để sử dụng khi mất authenticator.
- **Recovery transaction/token ngắn hạn**: được server tạo khi bắt đầu một quy trình recovery, gắn với account, mục đích, thời hạn và trạng thái.

Không nên nhầm recovery code với session cookie hoặc access token. Mỗi loại có mục đích, audience, thời hạn và cơ chế thu hồi riêng.

### 8.1. Sinh và lưu recovery code

Ví dụ cấu trúc khái niệm phía server:

~~~text
RecoveryCodeRecord:
  account_id
  code_verifier
  code_set_version
  created_at
  consumed_at
  revoked_at
~~~

- Dùng CSPRNG để tạo mã có entropy cao; không dùng số tăng dần, ngày sinh hoặc mã ngắn dễ đoán.
- Lưu verifier/hash với salt/thuật toán phù hợp; nếu mã có entropy thấp, KDF có thể làm tăng chi phí đoán nhưng **không thay thế việc tăng entropy và rate limit**.
- Chỉ hiển thị mã một lần; không có chức năng “xem lại mã cũ”.
- Khi người dùng tạo bộ mã mới, vô hiệu bộ cũ theo chính sách và ghi audit.
- Tiêu thụ mã theo thao tác nguyên tử để hai request đồng thời không thể dùng cùng mã.
- Giới hạn số lần thử trên account, transaction và các tín hiệu nguồn; không khóa tài khoản vĩnh viễn theo cách attacker có thể lạm dụng.

### 8.2. Recovery transaction

Mỗi lần recovery nên có transaction riêng:

~~~text
RecoveryTransaction:
  transaction_id
  account_id
  initiated_at
  expires_at
  requested_action
  proof_type
  proof_verified_at
  source_session_or_channel
  status: pending | verified | completed | rejected | expired
  attempt_counter
  consumed_at
~~~

Các trường trên là mô hình logic, không phải schema bắt buộc. Transaction cần được lưu server-side, ràng buộc với account và mục đích. Không tin account ID hoặc trạng thái do client tự gửi.

### 8.3. Luồng sử dụng recovery code

~~~text
POST /recovery/start
  identify account without revealing whether it exists
  apply rate limits
  create short-lived recovery transaction
  return generic instructions

POST /recovery/verify
  load transaction from trusted server-side state
  assert transaction is pending and not expired
  verify recovery code for the same account
  atomically consume the code
  mark proof as verified
  allow only the permitted recovery operation

POST /recovery/register-passkey
  require verified recovery transaction
  create fresh WebAuthn challenge bound to account and transaction
  verify registration response, origin, RP ID and challenge
  store new public key/credential ID
  apply lost-credential and session revocation policy
  complete transaction exactly once
  notify registered channels
~~~

Sau khi recovery code được sử dụng, không nên cho phép nó tự động tạo vô hạn session hoặc thực hiện mọi hành động quản trị. Phạm vi cho phép cần rõ: khôi phục authenticator, thay đổi credential hay cấp lại phiên. Với tài khoản có assurance cao, có thể cần thêm bước xác minh hoặc giới hạn hành động sau recovery.

## 9. Thu hồi thiết bị và credential đã mất

Khi người dùng mất thiết bị, có hai vấn đề khác nhau:

1. **Ngăn credential cũ tiếp tục đăng nhập:** RP đánh dấu credential ID bị mất là revoked/disabled, không chấp nhận assertion từ credential đó nữa.
2. **Ngăn phiên đã được cấp tiếp tục truy cập:** thu hồi session, refresh token và các grant liên quan theo chính sách.

Xóa credential khỏi danh sách phía RP không xóa private key khỏi thiết bị bị mất. Nó làm cho RP từ chối credential đó khi đăng nhập tiếp. Nếu thiết bị được khôi phục, người dùng có thể phải đăng ký lại sau khi xác minh đủ mạnh.

### 9.1. Xác định chính xác credential cần thu hồi

Một tài khoản có thể có nhiều passkey. Khi người dùng báo mất điện thoại, cần định danh credential tương ứng bằng metadata đã ghi nhận: credential ID, tên thiết bị do người dùng đặt, thời gian thêm và lịch sử sử dụng. Không thu hồi nhầm toàn bộ passkey nếu còn thiết bị dự phòng an toàn.

Nếu không thể xác định chính xác credential bị mất, đánh giá theo mức rủi ro và có thể thu hồi toàn bộ credential thuộc phạm vi nghi ngờ, sau đó hỗ trợ ghi danh lại.

### 9.2. Phiên và token

- Thu hồi session trên các thiết bị có nguy cơ.
- Vô hiệu refresh token hoặc token family liên quan; xử lý refresh token reuse nếu hệ thống có rotation.
- Xem xét access token tự chứa còn hiệu lực: cần TTL phù hợp, introspection/revocation hoặc kiểm tra trạng thái phiên theo kiến trúc.
- Xóa cookie phía client là cần thiết cho thiết bị còn trong tay người dùng nhưng **không đủ** để thu hồi phiên trên thiết bị đã mất.
- Nếu có SSO/federation, phân biệt phiên RP với phiên IdP; phối hợp logout/deprovisioning theo khả năng giao thức và chính sách.
- Yêu cầu xác thực lại cho hành động nhạy cảm sau recovery.

### 9.3. Thông báo và điều tra

Thông báo qua các kênh đã đăng ký về: yêu cầu recovery bắt đầu, credential mới được thêm, credential cũ bị thu hồi, phiên bị đăng xuất và các hành động hạn chế được áp dụng. Cung cấp cách báo cáo nếu người dùng không khởi tạo sự kiện.

Audit log nên lưu account ID nội bộ, credential ID đã che/mã hóa theo chính sách, thời gian, loại sự kiện, kết quả, transaction ID và nguồn ở mức cần thiết. Không lưu private key, recovery code rõ, token, OTP hoặc dữ liệu sinh trắc.

## 10. Chống tấn công vào quy trình recovery

| Tấn công | Cách xảy ra | Phòng vệ |
| --- | --- | --- |
| **Account enumeration** | Kẻ tấn công dò xem email/tài khoản có tồn tại qua phản hồi recovery | Thông báo chung, giới hạn request, tránh khác biệt thời gian dễ khai thác. |
| **Recovery code brute force** | Thử nhiều mã trên tài khoản | Entropy cao, rate limit, KDF/verifier phù hợp, cảnh báo và tiêu thụ một lần. |
| **Phishing recovery** | Trang giả lấy recovery code hoặc dụ người dùng phê duyệt reset | Hướng dẫn không chia sẻ mã; ràng buộc transaction; thông báo rõ mục đích; dùng kênh an toàn. |
| **SIM swap/email takeover** | Chiếm kênh liên lạc rồi yêu cầu reset | Không coi SMS/email đơn lẻ là bằng chứng đủ cho tài khoản assurance cao; bảo vệ thay đổi kênh. |
| **Help desk social engineering** | Giả danh nhân viên/người dùng để nhờ bỏ MFA | Xác minh độc lập, quy trình hai người cho thao tác đặc quyền, audit và đào tạo. |
| **Replay** | Dùng lại code, link hoặc transaction đã hoàn tất | TTL, nonce, trạng thái một lần, atomic consume và ràng buộc account/action. |
| **Session fixation/hijack** | Dùng phiên cũ hoặc phiên của attacker sau recovery | Tạo phiên mới, xoay session ID, thu hồi phiên nghi ngờ, bảo vệ cookie. |
| **Credential substitution** | Dùng transaction recovery của account A để ghi danh credential vào account B | Gắn transaction, challenge và account ID server-side; kiểm tra subject tại mọi bước. |
| **Recovery downgrade** | Bỏ qua passkey/MFA bằng một đường dự phòng yếu | Policy assurance áp dụng cả recovery; hạn chế hành động sau recovery nếu bằng chứng thấp hơn. |
| **Race condition** | Gửi song song hai yêu cầu tiêu thụ cùng mã hoặc thay credential | Transaction/lock/CAS; chỉ một request được hoàn tất. |
| **Denial of service** | Gửi nhiều yêu cầu recovery hoặc khóa tài khoản nạn nhân | Rate limit đa chiều, phản hồi chung, không khóa cứng dễ bị lạm dụng. |
| **Lost-device abuse** | Attacker báo mất thiết bị để buộc thu hồi credential của chủ tài khoản | Xác minh yêu cầu trước khi thay đổi trạng thái; cảnh báo và quy trình khiếu nại. |

**Không biến báo mất thiết bị thành lệnh thu hồi vô điều kiện.** Người dùng có thể báo nhầm hoặc attacker có thể cố tình phá khả năng đăng nhập của chủ tài khoản. Thu hồi khẩn cấp vẫn cần thiết khi nguy cơ cao, nhưng phải có cơ chế xác minh, thông báo và phục hồi an toàn.

## 11. Khôi phục tài khoản khi không còn authenticator

Đây là tình huống khó nhất: người dùng mất mọi passkey, security key và recovery code. Hệ thống không còn bằng chứng đã ghi danh trước để xác minh tự phục vụ. Cần một quy trình **recovery tăng cường** tương xứng với giá trị tài khoản.

### 11.1. Bằng chứng thay thế

Tùy sản phẩm, có thể dùng:

- Identity proofing ban đầu đã được thực hiện và còn giá trị, cùng bước đối chiếu lại theo quy trình.
- Thiết bị hoặc kênh dự phòng đã xác minh từ trước.
- Quy trình xác nhận qua tổ chức quản lý tài khoản (ví dụ quản trị viên trường/doanh nghiệp) với phân quyền, bằng chứng và audit.
- Kiểm tra thủ công bởi nhân viên được ủy quyền, dùng nhiều nguồn độc lập và có kiểm soát chống thông đồng.
- Thời gian chờ và thông báo tới các kênh cũ để chủ tài khoản có cơ hội phản đối.

Không nên dùng câu hỏi bí mật, thông tin công khai trên mạng xã hội hoặc chỉ một cuộc gọi tới help desk làm bằng chứng duy nhất cho tài khoản có rủi ro cao. Giấy tờ tùy thân cũng cần quy trình xác minh, bảo vệ dữ liệu và đánh giá khả năng giả mạo; không phải bằng chứng tuyệt đối.

### 11.2. Tách vai trò hỗ trợ khỏi quyền phê duyệt

Với tài khoản quản trị, người tiếp nhận yêu cầu không nên có khả năng tự mình xác minh và hoàn tất recovery đặc quyền. Có thể yêu cầu người thứ hai phê duyệt, lưu lý do, chứng cứ, thời điểm và kết quả. Phân tách nhiệm vụ giảm nguy cơ một nhân viên bị social engineering hoặc thông đồng.

### 11.3. Hạn chế sau recovery

Nếu quy trình recovery có assurance thấp hơn đăng nhập bình thường, không nên lập tức cấp toàn bộ quyền nhạy cảm. Có thể:
- Cho phép đăng ký lại authenticator nhưng tạm hạn chế thay đổi thông tin tài chính/quyền quản trị.
- Thu hồi session/token cũ và yêu cầu đăng nhập lại.
- Thông báo tới kênh cũ, đặt thời gian chờ cho thay đổi đặc biệt nhạy cảm.
- Yêu cầu xác minh mạnh hơn trước khi thực hiện tác vụ có hậu quả cao.
- Đánh giá lại các credential và liên kết IdP hiện có.

Hạn chế phải được công bố rõ, có thời hạn và đường khiếu nại; không biến recovery thành trạng thái khóa tài khoản vô thời hạn.

## 12. Tích hợp IdP và tài khoản nền tảng

Với đăng nhập federated, có thể người dùng mất quyền truy cập IdP thay vì mất thiết bị trực tiếp. RP cần phân biệt:

- **Khôi phục passkey ở IdP:** do nhà cung cấp danh tính xử lý.
- **Khôi phục liên kết danh tính tại RP:** xác định đúng `issuer + subject` đã liên kết.
- **Khôi phục quyền trong ứng dụng:** kiểm tra account nội bộ, role, trạng thái khóa và policy riêng.
- **Khôi phục phiên:** thu hồi hoặc cấp lại phiên RP theo bằng chứng đã xác minh.

Không tự ghép tài khoản mới với tài khoản cũ chỉ vì email giống nhau. Nếu IdP thay đổi subject hoặc issuer, phải có quy trình migration/liên kết rõ ràng. Nếu IdP đã recovery tài khoản, RP vẫn cần quyết định có chấp nhận kết quả đó cho hành động nhạy cảm hay yêu cầu step-up bổ sung.

## 13. Bài thực hành: thiết kế recovery cho StudyHub

**Bối cảnh:** StudyHub hỗ trợ passkey trên điện thoại và máy tính; một số người dùng có security key dự phòng; người dùng có thể tạo recovery code. Giảng viên quản lý điểm, quản trị viên có thể cấp quyền. Tài khoản được liên kết với CampusID cho một số nhóm người dùng.

### 13.1. Thiết kế chính sách cho từng tình huống

| Tình huống | Bằng chứng còn lại | Quyết định cần thiết |
| --- | --- | --- |
| Mất điện thoại, còn passkey trên laptop | Authenticator đã ghi danh | Xác thực lại, thêm passkey mới, thu hồi credential điện thoại và phiên có nguy cơ. |
| Mất khóa bảo mật chính, còn khóa dự phòng | Authenticator độc lập | Dùng khóa dự phòng, ghi danh khóa mới và thu hồi khóa mất. |
| Mất điện thoại nhưng passkey đồng bộ còn trên tablet | Passkey có thể khôi phục qua hệ sinh thái | Xác minh thiết bị/tài khoản nền tảng, đánh giá rủi ro và xử lý thiết bị mất. |
| Mất toàn bộ thiết bị, còn recovery code | Mã dự phòng đã tạo trước | Xác minh và tiêu thụ mã một lần, đăng ký passkey mới, thông báo và thu hồi credential cũ. |
| Mất toàn bộ thiết bị và recovery code | Không còn authenticator dự phòng | Recovery tăng cường, identity proofing hoặc xác nhận tổ chức, thời gian chờ và hạn chế sau recovery. |
| Thiết bị bị trộm đang mở phiên admin | Có nguy cơ phiên và credential bị chiếm | Thu hồi phiên/token khẩn cấp, khóa credential, kiểm tra hoạt động và recovery có kiểm soát. |
| Mất quyền truy cập tài khoản nền tảng đồng bộ | RP credential chưa chắc mất nhưng không dùng được | Recovery tại nhà cung cấp nền tảng; RP kiểm tra lại subject, policy và phiên. |

### 13.2. Bộ ca kiểm thử chấp nhận

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Dùng authenticator dự phòng hợp lệ | Recovery hoàn tất theo policy và ghi danh credential mới. |
| Recovery code sai hoặc đã dùng | Từ chối; không thay đổi credential hoặc cấp phiên mới. |
| Dùng lại recovery transaction đã hoàn tất | Từ chối do trạng thái một lần. |
| Dùng transaction của account A để ghi danh vào account B | Từ chối. |
| Hai request đồng thời dùng cùng recovery code | Chỉ một request thành công. |
| Email tồn tại/không tồn tại | Phản hồi không tiết lộ thông tin tài khoản. |
| Người dùng báo mất thiết bị nhưng không vượt xác minh | Không tự động thu hồi/đổi credential theo yêu cầu chưa xác minh, trừ cơ chế khóa khẩn cấp đã được policy định nghĩa. |
| Credential đã mất bị dùng lại sau khi thu hồi | RP từ chối assertion. |
| Session cũ trên thiết bị mất | Bị thu hồi hoặc hết hiệu lực theo chính sách; không chỉ xóa cookie ở thiết bị còn lại. |
| Refresh token family đã bị thu hồi | Không thể cấp access token mới. |
| Passkey mới đăng ký với challenge/origin/RP ID sai | WebAuthn registration bị từ chối. |
| Recovery qua email đơn lẻ cho tài khoản admin | Không đạt policy assurance cao; không cấp quyền quản trị. |
| IdP recovery nhưng subject không khớp liên kết cũ | Không tự chuyển mapping hoặc đăng nhập vào account cũ. |
| Recovery thành công | Có thông báo, audit event và trạng thái credential/phiên chính xác. |
| Recovery outage hoặc timeout giữa chừng | Transaction không bị tiêu thụ sai; người dùng có thể tiếp tục hoặc khởi tạo lại an toàn theo trạng thái. |

### 13.3. Câu hỏi tự đánh giá

1. Vì sao một passkey có thể đa yếu tố nhưng vẫn là một điểm lỗi nếu chỉ có trên một thiết bị?
2. Passkey đồng bộ khác passkey device-bound ở khía cạnh recovery nào?
3. Vì sao RP không thể khôi phục private key chỉ bằng cách gửi email?
4. Recovery code cần những thuộc tính gì để chống đoán và replay?
5. Khi nào nên thu hồi credential bị mất và khi nào cần thu hồi toàn bộ session?
6. Vì sao email/SMS không tự động đủ cho recovery của tài khoản assurance cao?
7. Recovery tại IdP có tự động khôi phục quyền trong RP không?
8. Làm thế nào ngăn help desk bị social engineering để bỏ qua passkey?
9. Nếu hai request cùng sử dụng một recovery code, backend phải bảo đảm điều gì?
10. Sau recovery, những hành động nào cần bị giới hạn hoặc yêu cầu step-up?

**Tiêu chí hoàn thành:** Người học có thể vẽ cây quyết định recovery, nêu bằng chứng được chấp nhận cho từng nhánh, xác định credential/session cần thu hồi, mô tả thông báo/audit và chứng minh bằng ca kiểm thử rằng recovery không trở thành lối tắt chiếm tài khoản.

## 14. Vận hành và chỉ số theo dõi

Theo dõi recovery để phát hiện lạm dụng nhưng không thu thập dữ liệu nhạy cảm vượt nhu cầu.

Các chỉ số hữu ích:

- Số yêu cầu báo mất thiết bị theo loại tài khoản và loại authenticator.
- Tỷ lệ recovery thành công/thất bại theo phương thức bằng chứng.
- Tỷ lệ sử dụng recovery code và số mã còn lại nếu chính sách cho phép theo dõi an toàn.
- Số lần thêm/xóa passkey, security key và thay đổi kênh recovery.
- Số phiên/token bị thu hồi sau báo mất thiết bị.
- Thời gian từ lúc báo mất tới lúc khóa credential hoặc hoàn tất recovery.
- Tỷ lệ khiếu nại do recovery nhầm hoặc bị lạm dụng.
- Sự kiện help desk can thiệp, phê duyệt hai người và bất thường theo nhân viên/đơn vị.
- Tỷ lệ người dùng có authenticator dự phòng và cập nhật recovery code.

Log nên có account ID nội bộ, transaction ID, loại credential (không ghi private key), thời gian, kết quả và lý do policy ở mức cần thiết. Không log recovery code rõ, token, OTP, dữ liệu sinh trắc, giấy tờ tùy thân hoặc bí mật hỗ trợ.

Khi phát hiện recovery bất thường, có thể tạm dừng thay đổi nhạy cảm, yêu cầu xác thực lại, thu hồi phiên đáng ngờ và thông báo cho người dùng. Cần có playbook xử lý sự cố rõ ràng để đội vận hành không tùy tiện bỏ qua kiểm soát.

## 15. Tài liệu nên đọc tiếp

- **W3C Web Authentication (WebAuthn)**: credential, challenge, user verification, backup eligibility/state và quy trình đăng ký/xác thực.
- **FIDO Alliance — Passkeys**: mô hình passkey đồng bộ, thiết bị, authenticator và trải nghiệm người dùng.
- **NIST SP 800-63B**: authenticator lifecycle, recovery và mức bảo đảm; kiểm tra phiên bản hiện hành và phạm vi áp dụng.
- **OWASP Forgot Password Cheat Sheet**: token recovery, giới hạn thử, thông báo và bảo vệ reset.
- **OWASP Authentication và Session Management Cheat Sheets**: quản lý credential, phiên, thu hồi và xác thực lại.
- **OWASP ASVS**: chuyển các yêu cầu recovery, session và authentication thành tiêu chí kiểm chứng.

Khi triển khai thực tế, hãy đánh giá nhà cung cấp nền tảng, loại passkey, thiết bị, giá trị tài khoản, quy trình hỗ trợ và yêu cầu pháp lý. Một hệ thống passwordless đáng tin cậy cần bảo vệ cả **đường đăng nhập mạnh nhất và đường recovery yếu nhất**, đồng thời giúp người dùng khôi phục quyền truy cập mà không trao cơ hội chiếm tài khoản cho kẻ tấn công.
