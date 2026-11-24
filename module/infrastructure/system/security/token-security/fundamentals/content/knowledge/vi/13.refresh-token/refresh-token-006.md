# Refresh token lưu phía client

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích vì sao **refresh token (RT)** là credential nhạy cảm và việc lưu RT ở phía client phải được quyết định theo **loại client và mô hình đe dọa**, không theo sự tiện lợi của một API lưu trữ.
- Phân biệt rủi ro ở **confidential client**, **Backend-for-Frontend (BFF)**, **SPA thuần trình duyệt**, **mobile**, **desktop/CLI** và thiết bị phân tán.
- Hiểu những giới hạn của **memory, localStorage, sessionStorage, IndexedDB, cookie HttpOnly, Keychain, Android Keystore** và kho bí mật phía backend.
- Thiết kế xử lý **refresh token rotation**, ghi token mới nhất quán, truy cập đồng thời, nhiều tab, lỗi mạng và phát hiện token tái sử dụng.
- Biết cách giảm thiệt hại nếu RT bị đánh cắp qua **TLS, bảo vệ khóa, sender-constraining, giới hạn quyền, hết hạn, revocation và giám sát**.
- Lập checklist triển khai để không đưa refresh token vào Resource Server, URL, log, crash report, backup hoặc mã nguồn.

## 1. Vì sao lưu refresh token là một quyết định bảo mật quan trọng?

Trong OAuth 2.0, **access token (AT)** dùng để client gọi Resource Server. **Refresh token (RT)** được client gửi đến **token endpoint** của Authorization Server (AS) nhằm xin access token mới khi điều kiện còn hợp lệ.

Hãy hình dung ứng dụng đã đăng nhập:

~~~text
Access token:   hạn sử dụng ngắn, audience = orders-api, scope = orders:read
Refresh token:  có thể cho phép xin access token mới theo quyền được ủy quyền
~~~

Nếu access token bị lộ, kẻ tấn công có thể thử sử dụng AT trong khoảng thời gian nó còn được chấp nhận. Nếu refresh token bị lộ, kẻ tấn công có thể **thử duy trì khả năng xin AT mới** qua nhiều vòng refresh, tùy hạn sử dụng, ràng buộc client, rotation và chính sách của AS.

Điều này không có nghĩa RT luôn có quyền rộng hơn AT. Refresh token thường gắn với **client, grant, sự ủy quyền, scope và trạng thái phiên**; AS phải áp dụng các giới hạn này khi cấp token mới. Vấn đề là RT có thể duy trì quyền truy cập **trong một khoảng thời gian dài hơn**, nên nơi lưu RT là điểm kiểm soát quan trọng.

**Nguyên tắc:** Refresh token là một **bí mật có giá trị cao**. Không lưu nó ở phía client chỉ vì client có thể gọi API lưu trữ dễ dàng; hãy đánh giá **ai có thể đọc, sao chép, dùng lại hoặc đồng bộ token đó**.

## 2. Phân biệt refresh token với các credential khác

| Loại dữ liệu | Dùng ở đâu? | Nếu bị lộ, rủi ro chính là gì? | Cách xử lý điển hình |
| --- | --- | --- | --- |
| **Access token** | Resource Server được chỉ định bởi audience. | Bị sử dụng để thử gọi API trong phạm vi token còn được chấp nhận. | Hạn ngắn, scope/audience hẹp, bảo vệ khi lưu và truyền, thu hồi khi cần. |
| **Refresh token** | Token endpoint của Authorization Server. | Bị dùng để thử xin AT mới hoặc chiếm quyền duy trì phiên. | Lưu nghiêm ngặt, ràng buộc client, rotation hoặc sender-constraining, revocation. |
| **ID token (OIDC)** | Client/relying party xác minh thông tin xác thực. | Lộ thông tin danh tính hoặc bị nhầm mục đích trong một triển khai sai. | Xác minh đúng OIDC; không dùng làm AT hoặc RT. |
| **Session cookie của BFF** | Trình duyệt ↔ backend cùng ứng dụng. | Bị lợi dụng để hành động trong phiên hoặc tấn công CSRF/session hijack. | Secure, HttpOnly, SameSite theo policy; chống CSRF/XSS; quản lý phiên phía server. |
| **Client secret/private key** | Xác thực confidential client tại AS. | Client bị giả mạo hoặc mất khả năng giữ bí mật. | Secret manager, khóa/phân quyền hẹp, rotation, không nhúng trong public client. |

**RT không phải credential dành cho Resource Server.** Đưa RT vào HTTP Authorization header khi gọi Orders API là sai luồng OAuth; RT chỉ nên đến token endpoint đáng tin của AS (hoặc thành phần nội bộ chịu trách nhiệm quản lý token theo thiết kế tin cậy).

## 3. Bắt đầu từ mô hình đe dọa thay vì tên kho lưu trữ

Trước khi chọn nơi lưu refresh token, cần trả lời:

1. **Ai điều khiển thiết bị và tiến trình?** Backend do tổ chức quản lý, máy nhân viên, trình duyệt người dùng hay thiết bị đối tác?
2. **Ai có thể chạy mã trong cùng ngữ cảnh?** Script độc hại qua XSS, extension, thư viện bên thứ ba, malware hoặc người dùng có quyền root?
3. **RT tồn tại ở đâu và bao lâu?** RAM, storage bền vững, cookie, database, backup, log, snapshot, hệ thống đồng bộ?
4. **RT được dùng bởi những bên nào?** Một backend, một tab, nhiều tab, nhiều worker hoặc nhiều thiết bị?
5. **AS có biện pháp nào?** Rotation, sender-constraining, expiry tuyệt đối, inactivity timeout, theo dõi token family, revocation?
6. **Yêu cầu trải nghiệm đăng nhập?** Ứng dụng cần duy trì phiên qua restart, offline, đổi thiết bị hay chỉ khi cửa sổ còn mở?
7. **Nếu RT bị sao chép, mức thiệt hại là gì?** Đọc báo cáo, chỉnh đơn hàng, thanh toán, quản trị tenant?

Từ đó mới chọn thiết kế. Không có một câu trả lời đơn giản như **“luôn lưu localStorage”** hoặc **“cookie HttpOnly luôn an toàn tuyệt đối”** phù hợp mọi loại client.

### Hai chiều rủi ro phải tách riêng

- **Token extraction:** Kẻ tấn công lấy được **giá trị RT** để mang sang nơi khác. Biện pháp như lưu trong kho bảo mật phần cứng, không cho JavaScript đọc cookie hoặc sender-constraining có thể giảm rủi ro.
- **Session abuse:** Kẻ tấn công không cần trích xuất RT nhưng có thể điều khiển ứng dụng hoặc gửi yêu cầu bằng phiên đang đăng nhập, ví dụ XSS kích hoạt thao tác khi script chạy trong origin hợp lệ.

Một cơ chế có thể chống **trích xuất RT** tốt mà vẫn cần phòng **lạm dụng phiên**. HttpOnly cookie và hardware-backed key không thay thế kiểm soát XSS, CSRF hay permission.

## 4. Bảng quyết định nơi lưu theo loại client

| Kiến trúc client | Ai giữ RT? | Phương án thường được cân nhắc | Giới hạn/rủi ro cần xử lý |
| --- | --- | --- | --- |
| **Backend confidential client** | Backend do tổ chức quản lý. | Kho dữ liệu/secret được bảo vệ, mã hóa tại rest, truy cập theo service identity. | Rò rỉ DB/log/backup, nhầm tenant hoặc session, đồng thời refresh. |
| **Web với BFF** | Backend/BFF; trình duyệt giữ **session cookie**, không giữ RT thô. | RT chỉ trong server-side session/token store; cookie phiên Secure/HttpOnly. | XSS vẫn có thể kích hoạt hành động, CSRF, mất phiên, token store bị lộ. |
| **SPA thuần trình duyệt** | JavaScript/runtime của browser nếu AS cấp RT. | Ưu tiên giảm tồn tại và phạm vi; cân nhắc BFF; với SPA thuần phải có biện pháp theo profile/AS. | XSS có thể đọc hoặc lạm dụng RT; Web Storage không là secret vault. |
| **Ứng dụng mobile** | Thiết bị người dùng. | Keychain/Keystore và giải pháp bảo vệ credential theo nền tảng. | Root/jailbreak, malware, backup, accessibility/debug, khóa không chống mọi tấn công runtime. |
| **Desktop/CLI** | Máy người dùng. | OS credential store/keyring khi có, hạn quyền file, mã hóa ở rest tùy threat model. | File cấu hình, shell history, nhiều user/tiến trình, đồng bộ máy. |
| **Thiết bị IoT/edge** | Thiết bị tại hiện trường. | Secure element/TPM hoặc kho khóa phần cứng khi có, hạn phiên và cơ chế cấp lại. | Thiết bị bị chiếm, firmware/flash extraction, mất thiết bị, offline kéo dài. |
| **Service-to-service client credentials** | Thường không có RT. | Dùng credential của confidential client để xin access token khi cần. | Không tạo thêm RT không cần thiết, quản lý client secret/key an toàn. |

**Phương án thường an toàn hơn cho web:** Khi ứng dụng có thể dùng **BFF** phù hợp, browser không cần giữ access/refresh token OAuth thô; backend quản lý token và trình duyệt dùng phiên ứng dụng. Nhưng BFF không miễn trừ các yêu cầu bảo vệ phiên và backend.

## 5. Web với Backend-for-Frontend: giữ RT ngoài JavaScript

Trong kiến trúc **BFF**, OAuth client có thể là một backend confidential client. Browser không trực tiếp quản lý RT.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant F as BFF / Web Backend
    participant AS as Authorization Server
    participant API as Resource Server

    B->>F: HTTPS đăng nhập
    F->>AS: Luồng ủy quyền OIDC/OAuth phù hợp
    AS-->>F: Authorization code
    F->>AS: HTTPS POST /token với code, PKCE/client auth
    AS-->>F: AT + RT nếu được cấp
    F->>F: Lưu RT tại server theo phiên
    F-->>B: Cookie phiên Secure, HttpOnly, SameSite
    B->>F: HTTPS request với cookie phiên
    F->>API: HTTPS request dùng access token của phiên
    API-->>F: Kết quả
    F-->>B: Dữ liệu được phép xem
    Note over F,AS: Khi AT hết hạn, BFF dùng RT gọi token endpoint
~~~

Điều đáng chú ý:

- Browser giữ **cookie phiên ứng dụng**, không giữ RT trực tiếp trong JavaScript hoặc localStorage.
- Backend giữ liên kết **session → user/client/tenant → token set** và dùng RT ở phía server.
- Khi refresh thành công, backend cập nhật RT mới theo quy trình rotation/atomicity.
- Browser không được tự đặt user ID hoặc token handle để truy cập token set của phiên khác.
- BFF vẫn phải kiểm quyền ở API/Resource Server; một session hợp lệ không tự cấp mọi permission.

### Cookie phiên nên có những thuộc tính gì?

Ví dụ header minh họa:

~~~http
Set-Cookie: __Host-session=EXAMPLE_OPAQUE_SESSION_ID; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

**Các thuộc tính cookie có vai trò khác nhau:**

- **Secure**: giới hạn gửi cookie trong điều kiện kênh bảo vệ phù hợp, không dùng để cấp quyền.
- **HttpOnly**: ngăn JavaScript đọc giá trị cookie bằng các API thông thường của trình duyệt.
- **SameSite**: giảm một số luồng gửi cookie xuyên site, có các chế độ Strict/Lax/None tùy nghiệp vụ.
- **__Host- prefix**: khi được trình duyệt hỗ trợ, áp các yêu cầu như Secure, Path=/ và không có Domain, giúp thu hẹp phạm vi cookie.
- **Path và Domain**: điều khiển nơi cookie được gửi; cần tránh chia sẻ không cần thiết.

Ví dụ **SameSite=Lax** không phải giá trị bắt buộc cho mọi BFF. Cần lựa chọn theo luồng đăng nhập, môi trường cross-site và chính sách CSRF; những cookie cần SameSite=None phải đáp ứng các yêu cầu browser tương ứng, bao gồm Secure.

### HttpOnly không tự giải quyết XSS và CSRF

HttpOnly có thể ngăn script đọc thẳng **giá trị cookie**, nhưng **XSS trong cùng origin** vẫn có thể gửi các request được trình duyệt gắn cookie và đọc phản hồi mà script có quyền đọc. **CSRF** cũng cần được xem xét với các request dùng cookie, nhất là hành động thay đổi trạng thái.

BFF nên có:

- Phòng XSS bằng encode output, tránh HTML injection, CSP và kiểm thư viện bên thứ ba.
- CSRF protection cho thao tác thay đổi trạng thái, kết hợp SameSite, Origin/Referer checks và token CSRF hoặc cơ chế tương ứng.
- Quản lý session ID chống fixation/hijacking, timeout và logout server-side.
- Không trả RT/AT thô về browser qua endpoint debug hoặc response không cần thiết.
- Kiểm policy tại backend và Resource Server đối với mọi hành động.

**BFF giảm khả năng browser trích xuất OAuth RT; nó không biến frontend thành môi trường tin cậy tuyệt đối.**

## 6. SPA thuần trình duyệt: localStorage, sessionStorage, IndexedDB hay memory?

Với **Single-Page Application (SPA)** không có backend giữ token, JavaScript chạy trong origin có thể cần dùng access token, và trong một số kiến trúc AS cũng cấp refresh token cho SPA.

Lựa chọn lưu trữ mang những đánh đổi sau:

| Nơi lưu | Tồn tại | Điều đáng chú ý về bảo mật |
| --- | --- | --- |
| **Biến trong memory của JS runtime** | Thường mất khi reload/đóng ngữ cảnh. | Giảm lưu bền vững nhưng script cùng ngữ cảnh bị XSS vẫn có thể khai thác hoặc gọi logic đang giữ token. |
| **sessionStorage** | Thường gắn với ngữ cảnh tab; phụ thuộc hành vi trình duyệt. | JavaScript cùng origin có thể đọc; không phải secret store chống XSS. |
| **localStorage** | Tồn tại qua nhiều lần mở trình duyệt đến khi bị xóa. | JavaScript cùng origin đọc được, nên RT có thể bị trích xuất khi XSS xảy ra. |
| **IndexedDB** | Lưu bền vững, hỗ trợ dữ liệu có cấu trúc. | Script được thực thi trong origin có thể truy cập qua API và gây trích xuất/lạm dụng. |
| **Cookie HttpOnly** | Browser tự gửi cookie theo scope/các thuộc tính. | JS không đọc trực tiếp; dùng cho mô hình token hay phiên cần cân nhắc CSRF, backend, CORS và giao thức. |

**Không có Web Storage API nào biến một RT bearer thành bí mật tuyệt đối trước XSS chạy cùng origin.**

### Vì sao localStorage thường không phải lựa chọn tốt cho RT?

RT trong localStorage có thể sống qua nhiều lần mở app, khiến một lần XSS trong origin có cơ hội trích xuất credential dài hạn. Đặc biệt, kẻ tấn công có thể gửi RT ra ngoài và sử dụng nó từ máy khác nếu RT không được sender-constrained và chưa bị rotation/thu hồi làm mất hiệu lực.

Đặt AT trong localStorage cũng có rủi ro tương tự; nhưng RT có khả năng xin token mới nên thường đáng quan tâm hơn về vòng đời.

### Memory có “an toàn khỏi XSS” không?

Không. Memory hạn chế việc token **tồn tại bền vững** trong storage, nhưng mã độc đang chạy cùng ngữ cảnh có thể:

- Gọi những hàm của ứng dụng có quyền dùng RT.
- Hook/intercept fetch hoặc token response nếu có quyền thực thi.
- Kích hoạt API hành động bằng access token còn hiệu lực.
- Tác động luồng refresh trong phiên hiện tại.

Một cấu trúc lưu token trong closure hoặc worker có thể **giảm một số đường đọc trực tiếp**, nhưng không đảm bảo bảo vệ trước toàn bộ XSS hay mã độc cùng origin. Cần threat model cụ thể thay vì coi đó là “kho tuyệt đối an toàn”.

### Có nên mã hóa refresh token trước khi bỏ vào localStorage?

Chỉ có ý nghĩa nếu **khóa giải mã được bảo vệ độc lập** khỏi đối thủ cần chống. Nếu cả ciphertext lẫn khóa (hoặc logic có thể dùng khóa) đều nằm trong JavaScript của cùng origin, XSS có thể tìm cách gọi logic giải mã hay sử dụng RT.

**Mã hóa token bằng khóa hardcode trong frontend** không giải quyết vấn đề trích xuất bởi XSS. WebCrypto hoặc non-extractable key có thể hỗ trợ những kiến trúc ràng buộc khóa nhất định, nhưng không biến toàn bộ JavaScript context bị xâm nhập thành tin cậy.

### Lựa chọn thực tế

Khi có thể, cân nhắc BFF để giữ RT ngoài browser. Nếu kiến trúc bắt buộc là SPA thuần và AS quyết định cấp RT, cần đánh giá ít nhất:

- RT rotation hoặc sender-constraining theo yêu cầu của OAuth 2.0 Security BCP.
- Thời hạn tuyệt đối và inactivity timeout, phạm vi ủy quyền và audience.
- Nơi lưu giảm tối đa khả năng trích xuất/tồn tại không cần thiết.
- XSS/CSP/kiểm supply-chain, cô lập origin và giảm script bên thứ ba.
- Cơ chế phối hợp refresh giữa tab và phát hiện/làm sạch khi logout.
- Phương án không cấp RT và chạy lại luồng authorization nếu phù hợp trải nghiệm và khả năng AS.

**Không nên cấp RT cho mọi SPA mặc định** khi chưa đánh giá rủi ro và lợi ích.

## 7. Mobile: Keychain và Android Keystore giải quyết phần nào?

Một ứng dụng mobile là **public client**: người dùng hoặc kẻ tấn công sở hữu thiết bị có thể phân tích binary và môi trường chạy. Secret nhúng trong app không phải bằng chứng confidential client.

### iOS/iPadOS: Keychain

**Keychain** cung cấp cơ chế lưu credential do hệ điều hành quản lý. Khi lưu RT, ứng dụng cần chọn access-control/accessibility phù hợp với rủi ro và trải nghiệm, ví dụ hạn chế khả năng truy cập khi thiết bị khóa, quyết định dữ liệu có được sao lưu/đồng bộ hay không theo thuộc tính nền tảng.

Không phải mọi Keychain item đều tự gắn với Secure Enclave, và không phải mọi ứng dụng dùng Keychain đều có khả năng chống thiết bị đã bị jailbreak/chiếm quyền. Cần phân biệt **lưu một chuỗi RT** với **giữ khóa riêng không thể xuất để chứng minh sở hữu token**.

### Android: Keystore và lưu dữ liệu được bảo vệ

**Android Keystore** hỗ trợ quản lý khóa mã hóa với các thuộc tính bảo vệ của nền tảng, có thể có hardware-backed security theo thiết bị. Một thiết kế thường dùng khóa được quản lý bởi Keystore để bảo vệ dữ liệu RT được lưu ở vị trí thích hợp, với kiểm soát truy cập/app sandbox và chính sách backup rõ ràng.

**Keystore không mặc nhiên là nơi lưu trực tiếp mọi chuỗi RT**; nó chủ yếu hỗ trợ quản lý khóa và hoạt động mật mã. Cần chọn thư viện/cách lưu dữ liệu được hỗ trợ, tránh tự viết crypto tùy tiện.

### Nguyên tắc chung cho mobile

1. Dùng **Authorization Code + PKCE** với trình duyệt hệ thống, tránh thu thập mật khẩu trong webview tùy tiện.
2. Chỉ cấp RT khi cần duy trì phiên và AS cho phép.
3. Lưu RT trong cơ chế credential bảo vệ của OS, không trong preference/file/log dạng rõ.
4. Giới hạn backup/cloud sync theo chính sách; RT có thể là credential gắn với một thiết bị/khóa và không nên bị copy sang thiết bị khác.
5. Khi app logout hoặc tài khoản bị vô hiệu, xóa RT local và yêu cầu thu hồi tại AS khi khả thi.
6. Khi dùng sender-constrained token, bảo vệ private key tương ứng và xử lý mất/đổi khóa.
7. Không giả định Keychain/Keystore ngăn mọi mã độc chạy với quyền hoặc ngữ cảnh tương đương ứng dụng.

## 8. Desktop, CLI và thiết bị hạn chế tài nguyên

### 8.1 Ứng dụng desktop

Desktop app thường là public client, dù phần mềm được cài trên máy doanh nghiệp. Nơi lưu RT có thể là:

- Windows Credential Manager/DPAPI theo thiết kế hệ điều hành.
- macOS Keychain.
- Secret Service/keyring phù hợp trên Linux khi khả dụng.
- Một kho file được mã hóa với khóa tách biệt, nếu hệ điều hành và mô hình đe dọa cho phép.

Không nên mặc định **file .json hoặc .env trong thư mục home** là secret vault. Cần xét permission file, full-disk encryption, backup, EDR, malware, nhiều user và việc một process khác có thể đọc dữ liệu.

### 8.2 CLI và developer tool

CLI dùng OAuth để đăng nhập vào dịch vụ thường phải lưu phiên qua nhiều lần chạy. Nếu không có OS keyring, việc yêu cầu người dùng đăng nhập lại hoặc dùng credential ngắn hạn có thể an toàn hơn lưu RT dạng rõ.

Những rủi ro đặc trưng:

- In RT ra terminal hoặc file debug; token đi vào terminal scrollback/log.
- Truyền RT dưới dạng **tham số dòng lệnh** có thể xuất hiện trong shell history hoặc thông tin process trên một số hệ thống.
- Đặt RT trong biến môi trường rồi vô tình in toàn bộ environment trong crash report hoặc build log.
- Copy file cấu hình chứa RT vào container image, git repository hoặc artifact CI.
- Dùng chung RT của tài khoản cá nhân cho script chạy CI/CD.

Với CI/CD hoặc automation máy–máy, nên ưu tiên cơ chế credential dành cho workload/client và token ngắn hạn phù hợp; không lưu RT phiên cá nhân chỉ để script tiện chạy.

### 8.3 IoT/edge/offline

Thiết bị phân tán có thể khó bảo vệ khóa, không có màn hình đăng nhập hoặc bị mất kết nối dài ngày. Cần quyết định **có nên cấp RT không**, giới hạn hạn tuyệt đối/inactivity và quy trình thay thế thiết bị.

Nếu có secure element/TPM, có thể giữ khóa sender-constraining ở phần cứng; vẫn cần bảo vệ firmware, cập nhật bảo mật, chứng chỉ và khả năng vô hiệu thiết bị khi mất.

Một thiết bị offline không thể tự chứng minh với AS rằng RT vẫn chưa bị thu hồi; khả năng refresh chỉ được quyết định khi kết nối lại và AS áp trạng thái hiện hành.

## 9. Backend confidential client: lưu RT như một bí mật phía server

Ở confidential client, backend có thể xác thực client tại AS bằng credential phù hợp (client secret, private_key_jwt, mTLS). RT được lưu phía server và không cần xuất hiện ở frontend.

### Mô hình lưu và ràng buộc phiên

~~~text
SessionTokenRecord
    session_id              // định danh phiên nội bộ
    principal_id            // user nội bộ đã xác minh
    issuer                  // AS phát hành
    client_id               // client được cấp RT
    tenant_context          // nếu policy cần
    encrypted_refresh_token // ciphertext được bảo vệ
    token_family_id         // khi dùng rotation, metadata riêng
    generation              // phiên bản dùng cho optimistic locking
    access_token_expiry
    absolute_session_expiry
    last_used_at
    status                  // ACTIVE / REVOKED / EXPIRED
~~~

Đây là cấu trúc minh họa, **không phải schema chuẩn OAuth**. Không cần lưu mọi trường nếu hệ thống không dùng đến; cũng không được dùng một token family ID tự đoán để thay xác minh grant ở AS.

Yêu cầu thiết kế:

- **Bảo vệ dữ liệu ở rest** bằng giải pháp phù hợp như envelope encryption với KMS/key manager, hoặc kho bí mật có phân quyền chặt.
- **Bảo vệ khóa riêng**: key mã hóa không hardcode cạnh dữ liệu token, không chia sẻ cho mọi service.
- **Hạn quyền đọc:** Chỉ service/quy trình chịu trách nhiệm refresh được đọc RT cần thiết; tránh cho hệ thống reporting hoặc worker không liên quan quyền đọc.
- **Ràng buộc đúng phiên/user/client/issuer:** Không lấy RT của phiên A để refresh cho phiên B hoặc gửi tới token endpoint của issuer khác.
- **Bảo vệ backup, snapshot, replica và log:** Mã hóa DB không đủ nếu bản backup chứa bản rõ token/khóa hoặc audit log đã ghi RT.
- **Xóa khi hết hiệu lực:** Có retention và quy trình xóa credential phù hợp với revocation/logout và nhu cầu audit.
- **Chống truy cập chéo tenant:** Bảng token store chứa RT nhạy cảm; mapping theo tenant/user phải kiểm quyền truy cập ở phía server.

**Mã hóa ở rest không thay access control.** Nếu một service bị chiếm quyền có cả RT ciphertext lẫn quyền gọi KMS giải mã, attacker vẫn có thể lấy RT. Cần giảm blast radius, giám sát và khả năng thu hồi.

## 10. Refresh token rotation và yêu cầu lưu phiên bản mới

**Refresh token rotation** là mô hình trong đó AS cấp RT mới khi client dùng RT hiện tại để refresh, đồng thời vô hiệu RT cũ theo quy tắc của AS.

~~~mermaid
sequenceDiagram
    participant C as Client / BFF
    participant S as Secure token store
    participant AS as Authorization Server

    C->>S: Đọc RT thế hệ 1
    S-->>C: RT-1
    C->>AS: POST /token grant_type=refresh_token, RT-1
    AS->>AS: Xác minh RT-1, client, policy
    AS-->>C: AT-2 + RT-2
    C->>S: Ghi RT-2 thay RT-1 và cập nhật generation
    S-->>C: Commit thành công
    Note over C,S: Những lần refresh sau chỉ dùng RT-2
~~~

Các điểm cần lưu ý:

- **RT-1 sau khi được đổi không nên được dùng lại** nếu AS đã vô hiệu nó.
- Client phải lưu **RT-2** trước khi xóa trạng thái cần thiết để những request sau không tiếp tục dùng RT-1.
- Nếu kết quả refresh trả thêm scope hoặc thời hạn khác dự đoán, client phải xử lý **quyền thực sự được cấp**.
- Token endpoint phải được gọi qua TLS, có client authentication/binding khi profile yêu cầu.
- Ghi RT mới phải được bảo vệ khỏi crash, race condition và ghi đè bởi request cũ.

### Reuse detection và token family

AS có thể liên kết các RT trong một **token family** để nhận biết một RT đã bị dùng lại sau rotation. Reuse có thể là dấu hiệu bị đánh cắp; nhiều triển khai phản ứng bằng cách vô hiệu family/phiên liên quan và yêu cầu xác thực lại.

Nhưng **reuse không tự chứng minh có tấn công**. Hai tab cùng refresh, một request retry sau lỗi mạng, hoặc client chưa lưu RT-2 có thể gây reuse do lỗi ứng dụng. Cần thiết kế để giảm race và có policy xử lý sự cố theo rủi ro.

**Không tự viết logic cho client rằng “nếu RT-1 bị từ chối thì vẫn thử liên tục đến khi thành công”**: hành vi đó có thể làm tăng mức nghi ngờ tấn công, gây khóa phiên hoặc lặp lỗi.

## 11. Concurrent refresh: bài toán nhiều request và nhiều tab

Đây là lỗi phổ biến dù đã chọn kho lưu RT khá tốt.

Giả sử access token hết hạn và ba request API cùng lúc nhận 401:

~~~text
Request A -> refresh dùng RT-1
Request B -> refresh dùng RT-1
Request C -> refresh dùng RT-1

AS nhận A trước -> phát RT-2, vô hiệu RT-1
AS nhận B/C sau -> RT-1 không còn hợp lệ, có thể kích hoạt reuse detection
~~~

### Single-flight refresh

**Single-flight** là nguyên tắc: trong một vùng quản lý phiên, nếu đã có một tác vụ refresh đang chạy, những request khác **chờ cùng kết quả** thay vì gửi nhiều yêu cầu dùng chung RT.

Mã giả của một client manager:

~~~text
function getValidAccessToken(session):
    if session.accessTokenIsUsableWithSafetyMargin():
        return session.accessToken

    return singleFlight.forKey(session.id, async function():
        latest = tokenStore.load(session.id)

        // Double-check sau khi vào vùng được đồng bộ:
        if latest.accessTokenIsUsableWithSafetyMargin():
            return latest.accessToken

        result = await authorizationServer.refresh(
            refreshToken = latest.refreshToken,
            clientBinding = latest.clientBinding
        )

        tokenStore.replaceAtomically(
            sessionId = session.id,
            expectedGeneration = latest.generation,
            newAccessToken = result.accessToken,
            newRefreshToken = result.refreshTokenIfRotated,
            newGeneration = latest.generation + 1
        )

        return result.accessToken
    )
~~~

Mã giả **không phải triển khai production**. Nó cần bổ sung xử lý cancellation, timeout, lỗi mạng, rate limiting, client authentication, kết quả token endpoint và bảo vệ secret trong memory.

### Trên một process chưa đủ

Một **mutex trong memory** chỉ đồng bộ những request trong process đó. Với BFF có nhiều instance hoặc SPA nhiều tab, vẫn có thể xảy ra refresh cùng RT từ nhiều nơi.

Các phương án tùy kiến trúc:

- **Backend nhiều instance:** khóa phân tán, optimistic concurrency qua database generation hoặc một dịch vụ quản lý token tập trung. Phải xử lý tình huống RT đã được AS rotate nhưng DB commit thất bại.
- **SPA nhiều tab:** cơ chế phối hợp tab như BroadcastChannel hoặc lock API được browser hỗ trợ có thể giảm request trùng, nhưng không biến storage thành an toàn khỏi XSS. Các tab phải nhận được thông tin phiên bản token mới nhất theo chính sách.
- **Mobile nhiều worker:** một token manager/service duy nhất điều phối refresh và cập nhật Keychain/Keystore-protected storage.
- **Desktop nhiều tiến trình:** file lock, IPC hoặc một credential broker nếu có, không cho các process tự refresh cùng RT mà thiếu đồng bộ.

### Lỗi khó: AS đã đổi RT nhưng response bị mất

~~~text
1. Client gửi RT-1.
2. AS nhận và xử lý thành công, phát RT-2, vô hiệu RT-1.
3. Kết nối đứt trước khi client nhận RT-2.
4. Client chỉ còn RT-1.
5. Retry RT-1 có thể bị xem là reuse.
~~~

Client **không thể bảo đảm tự khôi phục RT-2** nếu không nhận được giá trị đó. Không nên tự tạo một RT mới hoặc sửa chữ ký. Hành vi phục hồi phụ thuộc hợp đồng và chính sách AS: có thể phải yêu cầu đăng nhập/ủy quyền lại. Nếu nhà cung cấp có cơ chế xử lý retry an toàn được tài liệu hóa, mới áp dụng đúng hợp đồng đó.

**Atomic local write giải quyết tính nhất quán khi nhận được RT mới; nó không giải quyết được mọi lỗi mất response giữa hai hệ thống.**

## 12. Phân biệt làm mới access token với refresh token rotation

Một số luồng cấp token cần tách:

- **Access token refresh:** dùng RT hợp lệ để xin AT mới.
- **Refresh token rotation:** việc AS cũng cấp **RT mới** và vô hiệu RT cũ.
- **Refresh token reuse detection:** kiểm tra RT cũ được sử dụng lại sau rotation hoặc vi phạm chính sách.
- **Refresh token revocation:** vô hiệu RT theo yêu cầu người dùng, client, quản trị viên hoặc AS.
- **Session expiration:** kết thúc phiên do timeout, inactivity hoặc chính sách đăng nhập.

Không phải mọi lần xin AT mới đều bắt buộc trả RT mới theo mọi profile. Nếu AS không trả RT mới ở một phản hồi mà hợp đồng cho phép giữ RT cũ, client phải xử lý đúng. Không tự xóa RT còn hợp lệ chỉ vì response thiếu trường refresh_token, nhưng cũng **không giữ RT cũ nếu AS báo nó đã rotate/vô hiệu**. Hành vi cuối cùng phải theo AS đã đăng ký.

Ngoài ra, một AT mới được cấp sau refresh **không chứng minh** người dùng vừa đăng nhập hoặc vừa thực hiện MFA. Nếu giao dịch yêu cầu xác thực gần đây, phải kiểm **auth_time/max_age** theo OIDC hoặc policy step-up phù hợp.

## 13. Sender-constraining: giảm rủi ro bản sao RT được dùng ở nơi khác

**Bearer RT** có nguy cơ bị sao chép và dùng bởi bên khác nếu AS không có lớp binding thích hợp. OAuth 2.0 Security Best Current Practice (RFC 9700) yêu cầu với **public clients**, refresh token phải được bảo vệ bằng một trong hai hướng: **sender-constrained refresh token** hoặc **refresh token rotation**.

### Sender-constrained RT có ý nghĩa gì?

AS ràng buộc RT với một khóa/chứng chỉ hoặc phương thức proof của client. Khi RT được gửi tới token endpoint, bên gửi phải chứng minh đang sở hữu credential ràng buộc phù hợp. Chỉ có **chuỗi RT** không đủ để đổi token nếu AS thực thi binding đúng.

Một số mô hình liên quan:

| Cơ chế | Ý tưởng | Giới hạn |
| --- | --- | --- |
| **DPoP** | Proof của khóa bất đối xứng gắn với request/token theo profile. | Khóa cần được bảo vệ; script độc hại có thể tận dụng khóa nếu chạy trong ngữ cảnh client. |
| **mTLS binding** | Sử dụng khóa/chứng chỉ của client trong TLS và kiểm binding. | Phù hợp nhiều backend/workload; quản lý chứng chỉ và kết nối có chi phí. |
| **Refresh token rotation** | RT cũ hết hiệu lực khi RT mới được cấp; AS có thể nhận biết reuse. | Không bảo đảm chống lộ lần đầu; race/retry gây phức tạp và cần AS hỗ trợ. |

Với DPoP/mTLS, cần kiểm **ràng buộc ở token endpoint** theo giao thức; chỉ thêm một header hoặc bật TLS thường không đủ. Với client bị chiếm quyền hoàn toàn, attacker vẫn có thể lợi dụng môi trường hợp lệ để yêu cầu refresh dù không trích xuất được khóa.

**Sender-constraining không làm scope rộng trở thành an toàn.** RT và những AT cấp từ nó cần scope/audience hẹp và chính sách phù hợp.

## 14. Một request refresh an toàn gửi gì và đi đâu?

Ví dụ client gửi refresh token tới **token endpoint**:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=EXAMPLE_REFRESH_TOKEN&client_id=dashboard-public
~~~

Đây là **request minh họa**: phải truyền qua **HTTPS**, và nếu profile/client đăng ký yêu cầu DPoP, mTLS hoặc xác thực client thì phải thêm/cấu hình đúng bằng chứng tương ứng. Không dùng chuỗi giả này như credential thực.

Một phản hồi thành công có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "EXAMPLE_ACCESS_TOKEN_2",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders:read",
  "refresh_token": "EXAMPLE_REFRESH_TOKEN_2"
}
~~~

Trong ví dụ này AS thực hiện rotation. **900 giây** chỉ là giá trị minh họa cho AT, không phải thời hạn RT hay giá trị mặc định khuyến nghị.

Trên client:

1. Chỉ gửi RT tới token endpoint **đã xác minh thuộc issuer tin cậy**.
2. Không cho thư viện HTTP tự chuyển request chứa RT sang HTTP hoặc host khác khi redirect.
3. Không log body request, Authorization header/client assertion hoặc response có token.
4. Xác thực client theo loại client và cấu hình AS; **client_id của public client không phải bí mật**.
5. Cập nhật AT/RT **theo response thực tế**, không giả định phạm vi hoặc RT có luôn thay đổi.
6. Xử lý lỗi như **invalid_grant** theo chính sách: RT có thể hết hạn, bị thu hồi, đã dùng lại hoặc không đúng client.
7. Khi lỗi, không gửi RT tới Orders API hoặc thử dùng RT thay AT.

## 15. XSS, CSRF, CORS và SameSite ảnh hưởng tới RT ra sao?

Những khái niệm này thường bị trộn lẫn.

### XSS: mã độc chạy trong origin của ứng dụng

Nếu một script độc hại chạy với quyền của SPA:

- Nó có thể đọc RT ở storage mà JavaScript cùng origin truy cập được.
- Nó có thể gọi những hàm đang giữ token trong memory hoặc kích hoạt refresh.
- Nó có thể gửi request nghiệp vụ bằng phiên hợp lệ dù không nhìn thấy cookie HttpOnly.

Biện pháp nền tảng: encode output đúng ngữ cảnh, chống injection/DOM XSS, Content Security Policy, quản trị dependency và script bên thứ ba, hạn quyền của các API nhạy cảm.

### CSRF: trình duyệt tự gửi cookie trong yêu cầu ngoài ý muốn

Với mô hình **BFF session cookie**, browser có thể gửi cookie tự động theo thuộc tính cookie và ngữ cảnh request. Vì vậy endpoint thay đổi trạng thái cần kiểm **CSRF** phù hợp (SameSite, kiểm Origin/Referer, CSRF token hoặc cơ chế theo thiết kế).

**HttpOnly chống đọc cookie bằng JS, không tự chống mọi CSRF.**

### CORS: quy tắc đọc phản hồi giữa các origin

CORS kiểm soát khả năng JavaScript ở một origin đọc response từ origin khác theo chính sách browser. **CORS không phải cơ chế xác thực client hay chứng minh chủ sở hữu RT**.

Token endpoint chỉ nên mở CORS theo kiến trúc public client mà AS hỗ trợ, không bật wildcard với credential một cách tùy tiện. Một backend không chịu ràng buộc browser CORS giống SPA, nên không thể dùng CORS làm lớp bảo vệ duy nhất trước việc RT bị sử dụng sai.

### SameSite: ảnh hưởng việc cookie được gửi xuyên site

SameSite có thể giảm một số kiểu CSRF nhưng không thay anti-CSRF token/Origin validation trong mọi trường hợp. Các luồng OIDC, domain, iframe, cross-origin và cookie partitioning có thể cần đánh giá riêng; không chọn SameSite=Strict/Lax/None chỉ vì một ví dụ trên Internet.

## 16. Backup, log và crash report: nơi RT bị quên

Một nơi lưu RT có vẻ an toàn nhưng credential có thể bị sao chép sang môi trường khác:

| Đường rò rỉ | Ví dụ | Cách kiểm soát |
| --- | --- | --- |
| **Application log** | Log toàn bộ token response sau refresh. | Redact fields access_token, refresh_token, client_secret, assertion. |
| **Gateway/proxy log** | Ghi POST body của token endpoint. | Không log body nhạy cảm; phân quyền và retention log. |
| **Crash report/analytics** | Tự thu thập toàn bộ preferences hoặc network trace. | Lọc dữ liệu trước khi gửi; test crash reporting. |
| **Backup/snapshot** | RT nằm trong SQLite/preferences/database backup. | Mã hóa và hạn quyền backup; loại trừ dữ liệu phiên khi phù hợp. |
| **Clipboard/screenshot** | Debug UI hiện token để nhân viên copy. | Không hiển thị/cho copy RT trong sản phẩm. |
| **Git/CI artifact** | File credentials bị commit hoặc bundle vào image. | Secret scanning, ignore rules, credential cho CI riêng và rotation. |
| **Browser extension/devtools** | Môi trường browser bị mở rộng quyền theo extension hoặc mã độc. | Giảm token trong JS, threat model browser, BFF nếu phù hợp. |
| **Shared workstation** | Một user khác đọc file token trên máy dùng chung. | OS credential store, phân quyền tài khoản và logout đúng. |

Một RT được lưu ở Keychain hoặc secret manager vẫn có thể bị lộ nếu **ứng dụng lấy RT ra rồi in nó vào debug log**. Bảo vệ phải xuyên suốt đường đi **tạo → truyền → lưu → sử dụng → xoay vòng → xóa**.

## 17. Logout, thu hồi và xóa local không phải cùng một việc

Khi người dùng chọn **Đăng xuất**, thường cần hai hành động khác nhau:

1. **Xóa hoặc vô hiệu trạng thái client/local session**, để ứng dụng không tiếp tục dùng RT/AT đã lưu.
2. **Yêu cầu AS thu hồi RT hoặc phiên/sự ủy quyền** khi giao thức và chính sách cho phép, để bản sao đã bị lấy không thể tiếp tục đổi AT mới.

Ví dụ trạng thái:

~~~text
T0: RT-3 được lưu trên thiết bị.
T1: Một bản sao RT-3 đã bị lấy (nếu không sender-constrained).
T2: App xóa RT-3 local khi logout.
T3: Kẻ tấn công thử dùng bản sao RT-3 ở nơi khác.
~~~

Nếu chỉ làm T2, bản sao có thể vẫn được AS chấp nhận nếu RT chưa bị thu hồi và không có binding/ngăn chặn khác. Vì vậy cần thiết kế revocation server-side hoặc cơ chế quản lý phiên tương ứng.

### Revocation không tự làm mọi AT hết hiệu lực ngay

OAuth 2.0 token revocation (RFC 7009) cho phép client yêu cầu thu hồi token. Tuy nhiên, **access token JWT đã phát hành** có thể còn được RS chấp nhận tới exp nếu RS chỉ xác minh offline và không kiểm trạng thái thu hồi. Khi nghiệp vụ cần khóa ngay, hãy dùng cơ chế trạng thái/denylist/introspection hoặc policy động với độ trễ được đo.

### Khi người dùng mất thiết bị

Ứng dụng cần có khả năng:

- Thu hồi RT và phiên **theo thiết bị** nếu hệ thống có phân biệt phiên/thiết bị.
- Vô hiệu khóa sender-binding liên quan khi cần.
- Yêu cầu đăng nhập lại hoặc step-up cho thiết bị mới.
- Thông báo/ghi nhận sự kiện bảo mật và phát hiện refresh bất thường.
- Tránh thu hồi nhầm mọi thiết bị nếu mục tiêu chỉ là một phiên, trừ khi risk policy yêu cầu.

**Kết thúc local session**, **thu hồi RT**, **thu hồi AT**, **đăng xuất khỏi IdP** và **xóa SSO cookie** có thể là những hành động khác nhau; phải xác định rõ sản phẩm đang hứa thực hiện điều nào.

## 18. Các giới hạn thời gian của refresh token

Refresh token thường sống lâu hơn access token, nhưng **không có một TTL chuẩn bắt buộc cho mọi sản phẩm**. AS nên có chính sách theo client và rủi ro:

- **Absolute lifetime:** giới hạn cuối cùng của sự ủy quyền/RT hoặc token family.
- **Inactivity timeout:** tự hết hiệu lực sau khoảng không dùng để refresh.
- **Session/revocation lifetime:** bị vô hiệu khi logout, khóa tài khoản, rút sự ủy quyền hoặc chính sách an ninh thay đổi.
- **Scope/audience grant:** refresh không được mở rộng quyền vượt sự ủy quyền gốc.
- **Client binding:** RT chỉ dùng với client đã được cấp; public client được bảo vệ theo rotation/sender-constraining.
- **Risk events:** mật khẩu đổi, thiết bị mất, reuse detection, đăng nhập bất thường có thể dẫn tới thu hồi hoặc yêu cầu xác thực lại.

Một quy tắc cần hiểu đúng: **rotation không nên âm thầm kéo dài vô hạn thời hạn cuối** nếu chính sách tuyệt đối yêu cầu giới hạn tối đa. AS phải quản lý deadline/phiên độc lập với việc phát RT mới.

Refresh token cũng có thể không phải JWT nên client **không nên tự giải mã để đoán exp**. AS quyết định hiệu lực RT; nếu có metadata về expires_in/expiry theo extension cụ thể thì cần đọc đúng hợp đồng, không áp quy tắc access token JWT lên RT opaque.

## 19. Cách xử lý lỗi không tạo thêm rủi ro

Một số lỗi ở token endpoint phổ biến:

| Tình huống | Hành vi client an toàn |
| --- | --- |
| **invalid_grant** | RT/code không hợp lệ, hết hạn, bị thu hồi hoặc vi phạm ràng buộc; xóa trạng thái không dùng được và khởi động lại authorization khi cần. |
| **invalid_client** | Kiểm cấu hình/auth của confidential client, không retry vô hạn với credential sai. |
| **Timeout trước khi biết response** | Xem xét khả năng RT đã được AS rotate; không retry mù cùng RT không giới hạn. |
| **AT bị API trả 401 vì hết hạn** | Nếu policy cho phép, thử refresh có kiểm soát; retry request tối đa theo quy tắc rõ. |
| **AT bị API trả 401 vì issuer/audience sai** | Refresh đơn thuần thường không chữa lỗi cấu hình; phải kiểm nguyên nhân. |
| **AT bị API trả 403** | Thiếu scope/permission; không tự xin quyền cao hơn hoặc refresh vô hạn để vượt policy. |
| **RT mới lưu thất bại** | Không xem việc refresh đã hoàn tất an toàn; áp quy tắc phục hồi hoặc buộc đăng nhập lại. |
| **Reuse được AS phát hiện** | Xử lý như sự kiện an ninh hoặc lỗi đồng bộ theo mức độ; không cố né việc khóa phiên. |

**Không nên dùng refresh token cho mọi lỗi API**. Phân biệt hết hạn với sai audience, token giả, lỗi mạng, thiếu scope và policy từ chối.

### Tránh refresh loop

Một bug phổ biến:

~~~text
API trả 401
  -> refresh AT
  -> retry API
  -> vẫn 401
  -> refresh tiếp
  -> retry vô hạn
~~~

Giới hạn **một refresh attempt cho một vòng xử lý lỗi hợp lệ** và có backoff/circuit breaker khi AS lỗi. Đối với tác vụ gửi dữ liệu hoặc thanh toán, retry API cũng cần kiểm **idempotency** để không tạo giao dịch trùng.

## 20. Kịch bản tổng hợp: cùng một ứng dụng, ba phương án lưu RT

Một ứng dụng nhân viên gọi Orders API và muốn giữ phiên qua ngày làm việc.

### Phương án A: SPA lưu RT trong localStorage

~~~text
Browser
    localStorage: refresh_token = RT-1
    JavaScript: lấy RT và POST /token
    API: gọi bằng AT
~~~

**Ưu điểm:** đơn giản về mặt phát triển, trạng thái tồn tại sau reload.

**Rủi ro:** script độc hại trong origin có thể đọc RT từ localStorage; RT có thể tồn tại lâu ngoài nhu cầu; nhiều tab có thể race rotation; cần bảo vệ CORS/PKCE/RT theo hợp đồng AS. Không nên mặc định chọn A chỉ vì dễ triển khai.

### Phương án B: SPA giữ token trong memory

~~~text
Browser
    Memory: access token / refresh token nếu được cấp
    Reload: mất trạng thái runtime
    Auth flow: có thể cần lấy phiên mới
~~~

**Ưu điểm:** giảm lưu bền vững và một số đường trích xuất từ storage.

**Giới hạn:** XSS trong runtime vẫn có thể gọi logic có quyền; reload làm mất RT; không tự giải quyết nguy cơ đa tab hoặc tính liên tục phiên. Cần đánh giá thật kỹ nhu cầu duy trì phiên.

### Phương án C: BFF giữ RT phía server

~~~text
Browser
    Cookie phiên: __Host-session=opaque-id; Secure; HttpOnly
          |
          | HTTPS
          v
BFF
    Server-side token store: RT-1, client binding, session mapping
    Refresh manager: single-flight, rotation, revocation
          |
          v
Authorization Server / Resource Server
~~~

**Ưu điểm:** browser không cần được cấp quyền đọc RT; backend có thể quản lý khóa, audit, concurrency và revocation tập trung.

**Giới hạn:** phải vận hành BFF/token store, tránh session fixation, CSRF/XSS và rò rỉ token tại backend. Không được coi HttpOnly là điều kiện đủ để chống lạm dụng phiên.

Nếu ứng dụng có backend đủ tin cậy và kiến trúc cho phép, **C thường đáng cân nhắc mạnh nhất** để giảm tiếp xúc của RT với JavaScript. Tuy nhiên, quyết định cuối cùng còn phụ thuộc khả năng triển khai, privacy, SLA, môi trường và chính sách AS.

## 21. Bài tập tình huống

**Tình huống 1 — localStorage và XSS**

Một SPA lưu RT trong localStorage và tự nhận “RT đã được mã hóa”, nhưng khóa giải mã được hardcode trong bundle JavaScript.

**Phân tích:** Mã độc chạy trong origin có thể tìm hoặc gọi logic dùng khóa; việc mã hóa không tạo ranh giới bí mật mới. Cần xem xét chuyển RT ra BFF hoặc hạn tồn tại/rotation/sender-constraining theo mô hình SPA, cùng phòng XSS.

**Tình huống 2 — cookie HttpOnly**

Một BFF dùng cookie HttpOnly/Secure, nhưng endpoint chuyển tiền không kiểm CSRF và frontend có DOM XSS.

**Phân tích:** RT không bị đọc trực tiếp từ JS là lợi ích, song script độc hại vẫn có thể dùng phiên gửi lệnh và CSRF có thể tác động theo ngữ cảnh. Bảo vệ session và API authorization vẫn là yêu cầu riêng.

**Tình huống 3 — refresh token rotation đồng thời**

Hai tab cùng dùng RT-8 và gửi refresh đúng lúc. AS cấp RT-9 cho tab đầu rồi từ chối tab sau.

**Phân tích:** Cần phối hợp refresh, cập nhật RT mới nhất một cách nhất quán, tránh request đồng thời và xử lý reuse theo policy. Không thể chỉ tăng thời hạn RT để khắc phục.

**Tình huống 4 — mất response refresh**

AS đã đổi RT-2 thành RT-3, nhưng kết nối đứt trước khi client nhận RT-3.

**Phân tích:** Client không thể tự phục hồi RT-3. Retry RT-2 có thể kích hoạt reuse detection; chính sách phục hồi phải theo AS và có thể cần đăng nhập lại.

**Tình huống 5 — mobile backup**

Ứng dụng lưu RT trong một file được mã hóa bằng khóa riêng của thiết bị nhưng backup tự động đưa ciphertext sang thiết bị mới, nơi khóa cũ không tồn tại.

**Phân tích:** Token không nhất thiết đọc được trên thiết bị mới, nhưng restore có thể lỗi; cần chính sách backup/restore rõ ràng và quy trình đăng nhập lại. Nếu backup mang cả khóa bảo vệ hoặc RT dạng rõ, rủi ro cao hơn.

**Tình huống 6 — logout chỉ xóa local**

Người dùng nhấn logout, ứng dụng xóa RT local nhưng không thu hồi RT tại AS. Một bản sao RT đã bị lấy từ trước.

**Phân tích:** Bản sao có thể vẫn dùng được nếu không có binding và RT còn hợp lệ. Cần thu hồi server-side/phiên phù hợp, đồng thời hiểu rằng AT đang lưu hành có vòng đời riêng.

**Tình huống 7 — client credentials**

Một batch worker có credential confidential client và vẫn được team yêu cầu lưu RT trong file để “đỡ phải xin token”.

**Phân tích:** Với client_credentials, AS thường không cấp refresh token và theo RFC 6749 refresh token **SHOULD NOT** được đưa vào phản hồi. Worker có thể xin AT mới bằng client authentication khi cần; đừng tạo thêm credential lâu hạn không có lý do.

## 22. Checklist triển khai lưu refresh token phía client

Trước khi đưa một client OAuth/OIDC vào production:

1. **Sự cần thiết:** AS có cần cấp RT cho loại client này không? Có thể dùng BFF hoặc đăng nhập/ủy quyền lại mà vẫn đáp ứng trải nghiệm không?
2. **Mục đích:** RT chỉ được gửi tới token endpoint đáng tin, không dùng làm AT hoặc ID token.
3. **Kiểu client:** Đã phân biệt confidential, public SPA, mobile, desktop, service-to-service và quy tắc client authentication chưa?
4. **Nơi lưu:** Có chọn kho phù hợp threat model và bảo đảm RT không nằm trong log/URL/file cấu hình công khai không?
5. **Browser:** Đã phân tích XSS, CSRF, cookie, memory và Web Storage; không tự coi localStorage/IndexedDB là secret vault?
6. **Mobile/desktop:** Đã chọn Keychain/Keystore/OS keyring thích hợp, chính sách backup và thiết bị root/jailbreak/compromise chưa?
7. **Server storage:** Có access control, mã hóa dữ liệu ở rest, bảo vệ khóa, retention, backup và mapping phiên/client/tenant an toàn không?
8. **TLS:** Mọi yêu cầu refresh dùng HTTPS với certificate/hostname validation và token endpoint đã xác minh, không tự redirect sang HTTP/host khác?
9. **Rotation:** Nếu AS trả RT mới, client có cập nhật an toàn, không dùng RT cũ và có phát hiện lỗi lưu không?
10. **Concurrency:** Có single-flight, xử lý nhiều tab/process/instance và tránh retry RT cũ mù quáng không?
11. **Sender-constraining:** Với public client, RT được bảo vệ theo rotation hoặc sender-constraining theo RFC 9700; khóa/proof được xử lý đúng profile?
12. **Vòng đời:** Có absolute/inactivity timeout, giới hạn scope/audience, khóa tài khoản, revocation và giám sát được không?
13. **Logout/thiết bị mất:** Có quy trình xóa local và thu hồi server-side khi phù hợp, không hứa sai về AT đã cấp?
14. **API authorization:** AT mới sau refresh vẫn được RS kiểm issuer, audience, exp, scope và permission theo tài nguyên?
15. **Kiểm thử:** Đã thử XSS/storage extraction, token trong log, concurrent refresh, response mất, invalid_grant, logout, restore backup và reuse detection?
16. **Audit/privacy:** Chỉ ghi metadata cần thiết về phiên, không ghi RT, AT, client secret hoặc DPoP private key vào telemetry.

## Kết luận

**Refresh token lưu phía client** là một quyết định về **ranh giới tin cậy và vòng đời credential**. Không có kho lưu nào an toàn tuyệt đối trước mọi kiểu tấn công: localStorage/IndexedDB dễ bị truy cập bởi script cùng origin; memory giảm lưu bền vững nhưng vẫn chịu rủi ro khi runtime bị chiếm; HttpOnly cookie giúp giảm khả năng đọc trực tiếp nhưng vẫn đòi hỏi CSRF/XSS defense; Keychain/Keystore bảo vệ credential theo nền tảng nhưng không khắc phục thiết bị bị chiếm quyền hoàn toàn.

Với web app có thể triển khai **BFF**, giữ RT tại backend và cho browser dùng session cookie được bảo vệ thường là phương án đáng cân nhắc để giảm phơi nhiễm RT. Với public client trực tiếp giữ RT, cần bảo vệ theo **OAuth 2.0 Security BCP**, đặc biệt **rotation hoặc sender-constraining**, cùng TLS, giới hạn phạm vi, hết hạn, thu hồi và xử lý đồng thời.

Điểm kiểm tra quan trọng nhất không phải “RT được lưu ở API nào”, mà là **ai có thể sao chép hoặc sử dụng RT, client có thể an toàn thay nó sau rotation không, và hệ thống sẽ thu hồi/khôi phục như thế nào khi credential bị lộ hoặc phiên kết thúc**.

### Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework, Section 1.5: Refresh Token](https://www.rfc-editor.org/rfc/rfc6749#section-1.5)
- [RFC 6749 — Section 6: Refreshing an Access Token](https://www.rfc-editor.org/rfc/rfc6749#section-6)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
