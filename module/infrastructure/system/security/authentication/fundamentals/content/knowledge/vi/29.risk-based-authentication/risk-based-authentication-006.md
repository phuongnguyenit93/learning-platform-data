# Device anomaly

> **Chương:** Risk-based authentication  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Nhận diện thiết bị có hành vi hoặc đặc điểm khác thường trong luồng xác thực, đánh giá độ tin cậy của tín hiệu thiết bị và chọn phản ứng phù hợp mà không nhầm thiết bị với danh tính người dùng.

## 1. Device anomaly là gì?

**Device anomaly (bất thường về thiết bị)** là dấu hiệu cho thấy thiết bị hoặc môi trường client của một yêu cầu xác thực khác đáng kể so với ngữ cảnh đã biết, chính sách mong đợi hoặc các thiết bị tương tự. Hệ thống có thể phát hiện thiết bị mới, thay đổi đột ngột về browser, hệ điều hành, trạng thái bảo mật, khóa thiết bị hoặc cách một tài khoản thường truy cập.

Ví dụ, một nhân viên thường đăng nhập bằng laptop được quản lý bởi công ty, dùng browser đã cập nhật và có khóa bảo mật phần cứng. Một yêu cầu mới xuất hiện từ browser lạ, môi trường không được quản lý và có dấu hiệu tự động hóa. Đây là ngữ cảnh cần đánh giá thêm. Nó chưa đủ để kết luận tài khoản bị chiếm, vì nhân viên có thể vừa đổi máy hoặc đang dùng thiết bị cá nhân được phép.

Device anomaly là một nhóm tín hiệu trong risk-based authentication. Nó giúp hệ thống quyết định có cần step-up, hạn chế hành động, kiểm tra trạng thái thiết bị hoặc thu hồi phiên hay không. Thiết bị quen thuộc không chứng minh người đang cầm thiết bị là chủ tài khoản; thiết bị mới cũng không chứng minh người dùng là kẻ tấn công.

### Kết quả học tập

Sau bài này, người học có thể:

- Phân biệt nhận diện thiết bị, xác thực người dùng và đánh giá rủi ro thiết bị.
- Phân loại tín hiệu về thiết bị, browser, hệ điều hành, posture và khóa mật mã.
- Đánh giá độ tin cậy, độ mới, nguồn gốc và khả năng bị giả mạo của device signal.
- Thiết kế device recognition và device binding có giới hạn rõ ràng.
- Hiểu vai trò cũng như giới hạn của fingerprint, cookie thiết bị, attestation và MDM.
- Chọn phản ứng thích hợp khi thiết bị mới hoặc có dấu hiệu bị xâm nhập.
- Bảo vệ quyền riêng tư, xử lý false positive và kiểm thử khả năng né tránh.

## 2. Thiết bị không phải danh tính

Thiết bị là một phần của ngữ cảnh truy cập, không phải bằng chứng độc lập về danh tính con người.

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| **Device recognition** | Hệ thống có nhận ra thiết bị hoặc môi trường này không? | Browser có cookie thiết bị đã đăng ký |
| **Device authentication/binding** | Client có chứng minh đang kiểm soát khóa hoặc thiết bị đã liên kết không? | Thiết bị ký challenge bằng khóa riêng đã đăng ký |
| **User authentication** | Người đang truy cập có kiểm soát credential của tài khoản không? | Passkey, mật khẩu và MFA |
| **Device posture** | Thiết bị có đáp ứng chính sách bảo mật không? | MDM báo thiết bị còn được quản lý và mã hóa ổ đĩa |
| **Risk assessment** | Ngữ cảnh thiết bị có làm tăng nguy cơ của request không? | Thiết bị mới cộng với recovery vừa bị thay đổi |

Một browser có thể được nhận diện nhờ cookie, nhưng cookie có thể bị sao chép. Một laptop có thể thuộc danh sách quản lý của công ty, nhưng người dùng hiện tại có thể không phải nhân viên được cấp máy. Một passkey có thể gắn với authenticator trên thiết bị, nhưng bằng chứng WebAuthn chủ yếu xác minh quyền kiểm soát khóa và ràng buộc RP/origin theo giao thức, không tự chứng minh danh tính pháp lý của người dùng.

Vì vậy, thiết kế an toàn phải tách:

- Ai là chủ thể đã xác thực?
- Thiết bị hoặc client nào đang gửi request?
- Có bằng chứng nào cho thấy client kiểm soát một khóa hoặc đạt posture?
- Hành động đang yêu cầu có cần thiết bị được quản lý hay không?
- Những tín hiệu nào chỉ mang tính xác suất?

## 3. Các nhóm tín hiệu bất thường về thiết bị

### Thiết bị hoặc browser chưa từng thấy

- Device identifier hoặc cookie thiết bị chưa tồn tại.
- Browser, ứng dụng hoặc hệ điều hành mới với tài khoản.
- Thiết bị xuất hiện lần đầu sau một sự kiện recovery hoặc đổi mật khẩu.
- Nhiều tài khoản khác nhau cùng dùng một định danh thiết bị trong thời gian bất thường.

Thiết bị mới là tín hiệu phổ biến nhưng có độ đặc hiệu thấp. Người dùng thay máy, cài lại hệ điều hành, xóa cookie, dùng profile browser mới hoặc chuyển sang ứng dụng khác đều có thể tạo tín hiệu này.

### Thay đổi đặc điểm client

- Phiên bản browser hoặc hệ điều hành thay đổi bất thường.
- User-agent, ngôn ngữ, múi giờ hoặc đặc điểm hiển thị thay đổi đột ngột.
- Các thuộc tính browser không nhất quán với nhau.
- Client báo một nền tảng nhưng hành vi hoặc giao thức lại không phù hợp.
- Thiếu một số API hoặc tính năng vốn có trong môi trường đã biết.

Các thuộc tính client dễ bị giả mạo và thay đổi theo bản cập nhật. Không dùng user-agent hoặc browser fingerprint làm bằng chứng mạnh về danh tính thiết bị.

### Tín hiệu posture và tính toàn vẹn

- Thiết bị không còn đăng ký trong hệ thống quản lý doanh nghiệp.
- MDM/endpoint management báo thiết bị mất tuân thủ chính sách.
- Hệ điều hành quá cũ hoặc thiếu bản vá bắt buộc.
- Thiết bị bị root/jailbreak nếu nền tảng có tín hiệu đáng tin cậy.
- Secure boot, disk encryption hoặc screen lock không đáp ứng chính sách.
- Kết quả attestation không hợp lệ, hết hạn hoặc đến từ nguồn không được tin cậy.

Posture signal phụ thuộc nền tảng và phương thức đo. Một ứng dụng web thông thường không thể tự chứng minh chắc chắn trạng thái mã hóa ổ đĩa hoặc secure boot chỉ bằng JavaScript.

### Tín hiệu về khóa và credential gắn với thiết bị

- Khóa thiết bị đã đăng ký không còn sử dụng được.
- Proof-of-possession không xác minh được.
- Khóa mới xuất hiện ngay trước hành động nhạy cảm.
- Một credential có dấu hiệu được đồng bộ hoặc khôi phục trên thiết bị khác.
- Nhiều phiên sử dụng cùng một khóa theo cách không phù hợp với thiết kế.
- Passkey backup state hoặc authenticator properties thay đổi.

Với passkey/WebAuthn, các thuộc tính như backup eligibility và backup state có thể giúp hiểu credential có khả năng được sao lưu/đồng bộ hay đã được sao lưu. Chúng không phải điểm rủi ro tuyệt đối. Sign counter có thể không tăng đơn điệu với authenticator đồng bộ hoặc một số nền tảng; không kết luận clone chỉ từ counter không tăng nếu chưa xét loại authenticator và profile triển khai.

### Tín hiệu hành vi của thiết bị

- Request phát sinh từ thiết bị với tốc độ hoặc mẫu tự động hóa bất thường.
- Một thiết bị tạo nhiều lần thử đăng nhập hoặc recovery.
- Thiết bị vừa đăng nhập vừa thực hiện hành động có giá trị cao khác thường.
- Một session chuyển đột ngột giữa các client hoặc môi trường.
- Dấu hiệu malware, remote control hoặc browser extension độc hại nếu có nguồn phát hiện đáng tin.

Hành vi tự động không phải lúc nào cũng độc hại. Đồng bộ nền, accessibility tooling, kiosk và ứng dụng doanh nghiệp có thể tạo request lặp. Cần hiểu chức năng và bối cảnh trước khi chặn.

## 4. Nguồn tín hiệu và mức độ tin cậy

Các tín hiệu thiết bị có thể đến từ browser, ứng dụng native, hệ thống quản lý endpoint, nền tảng attestation, khóa thiết bị hoặc hạ tầng backend. Nguồn khác nhau có mức bảo đảm khác nhau.

| Nguồn | Ví dụ dữ liệu | Giới hạn chính |
|---|---|---|
| Browser/client tự khai | User-agent, screen size, locale | Dễ thay đổi hoặc giả mạo |
| Cookie/device marker | ID ngẫu nhiên do server cấp | Có thể bị xóa, sao chép hoặc replay |
| Device fingerprint | Tập hợp thuộc tính browser/hardware | Không ổn định, có thể gây theo dõi và false positive |
| App attestation | Bằng chứng app/platform theo cơ chế nền tảng | Phụ thuộc trust root, phiên bản và chính sách nhà cung cấp |
| MDM/endpoint management | Trạng thái tuân thủ thiết bị doanh nghiệp | Chỉ bao phủ thiết bị được quản lý; dữ liệu có thể trễ |
| Device-bound key | Chữ ký challenge bằng khóa đã đăng ký | Khóa có thể bị chiếm cùng thiết bị; cần quản lý vòng đời |
| WebAuthn authenticator | Assertion ký challenge, RP ID và origin | Chứng minh quyền kiểm soát credential, không phải danh tính pháp lý hoặc posture toàn thiết bị |

### Đánh giá mỗi tín hiệu

Trước khi sử dụng, hãy hỏi:

1. Ai tạo tín hiệu và nguồn đó có được tin cậy không?
2. Dữ liệu có được bảo vệ khỏi sửa đổi trên đường truyền không?
3. Tín hiệu được quan sát lúc nào và còn mới không?
4. Kẻ tấn công có thể giả mạo, sao chép hoặc replay không?
5. Tín hiệu có bao phủ mọi loại thiết bị và nhóm người dùng không?
6. Nó liên quan thế nào đến hành động đang được yêu cầu?
7. Có thể kiểm chứng độc lập hay chỉ là dữ liệu client tự khai?

Không nên gán cùng trọng số cho user-agent và chữ ký challenge được xác minh bằng public key đã đăng ký. Cũng không nên mặc định attestation có giá trị cao nếu trust chain không được xác minh hoặc chứng thư đã bị thu hồi.

## 5. Device fingerprint và giới hạn

**Device fingerprint** là cách kết hợp nhiều thuộc tính của browser hoặc thiết bị để tạo một dấu hiệu nhận diện có tính xác suất. Những thuộc tính có thể gồm browser version, hệ điều hành, ngôn ngữ, múi giờ, kích thước màn hình, font, API hỗ trợ và đặc điểm render.

Fingerprint có thể giúp nhận biết một môi trường đã xuất hiện trước đó, nhưng không phải một định danh mật mã.

### Vì sao fingerprint thay đổi?

- Browser cập nhật và thay đổi cách cung cấp thuộc tính.
- Người dùng cài extension hoặc thay đổi privacy setting.
- Thiết bị kết nối màn hình, bàn phím hoặc mạng mới.
- Browser chống fingerprinting làm giảm độ chi tiết hoặc trả giá trị chuẩn hóa.
- Cài lại hệ điều hành, reset profile hoặc dùng chế độ riêng tư.
- Nhiều thiết bị có cấu hình giống nhau.

### Vì sao fingerprint có thể bị giả?

Attacker có thể chỉnh user-agent, dùng automation framework, giả lập môi trường hoặc sao chép một phần thuộc tính. Một số thuộc tính có thể bị thu thập từ script do chính website chạy, nên cần xem xét khả năng can thiệp.

### Cách dùng phù hợp

- Dùng fingerprint như một tín hiệu phụ để phát hiện thay đổi.
- Kết hợp với lịch sử tài khoản, credential event và tín hiệu có nguồn tin cậy hơn.
- Không coi fingerprint trùng là bằng chứng cùng một thiết bị vật lý.
- Không khóa tài khoản chỉ vì fingerprint thay đổi.
- Giới hạn dữ liệu thu thập, thời hạn lưu và mục đích sử dụng.

Fingerprint có thể tạo khả năng theo dõi người dùng qua nhiều phiên hoặc dịch vụ. Không xây dựng định danh liên website bền vững nếu không có mục đích, căn cứ và kiểm soát phù hợp.

## 6. Cookie nhận diện thiết bị

Một hệ thống có thể cấp một device marker ngẫu nhiên sau khi người dùng xác thực thành công và chọn ghi nhớ thiết bị. Marker thường được lưu trong cookie hoặc vùng lưu trữ của ứng dụng.

### Luồng khái niệm

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Browser / Client
    participant A as Authentication service
    participant D as Device registry
    U->>A: Đăng nhập và hoàn tất MFA
    A->>D: Tạo device record và marker ngẫu nhiên
    D-->>A: Device ID + verifier
    A-->>C: Set device cookie
    C->>A: Request sau đó + device cookie
    A->>D: Tra marker và trạng thái thiết bị
    D-->>A: Thiết bị đã biết / trạng thái / thời hạn
    A->>A: Kết hợp với tín hiệu khác để đánh giá rủi ro
~~~

### Marker không phải credential chính

Cookie nhận diện thiết bị có thể bị sao chép hoặc đánh cắp. Nó không nên tự động bỏ qua mật khẩu, passkey hoặc MFA. Nếu cookie bị lộ, attacker có thể làm request trông giống thiết bị quen thuộc.

Thiết kế cần:

- Sinh marker ngẫu nhiên với CSPRNG, không mã hóa account ID hoặc dữ liệu dễ đoán.
- Lưu verifier/digest phía server nếu cần tra cứu và thu hồi.
- Dùng cookie Secure, HttpOnly, SameSite và scope domain/path phù hợp.
- Đặt thời hạn, giới hạn số thiết bị và cho người dùng xem/thu hồi thiết bị.
- Không dùng marker như một yếu tố duy nhất để khôi phục tài khoản.
- Thay marker khi nghi ngờ bị sao chép và ghi audit.

### Thiết bị được nhớ không đồng nghĩa thiết bị được tin vô điều kiện

“Remember this device” có thể giảm số lần step-up trong ngữ cảnh rủi ro thấp. Tuy nhiên, khi thiết bị có dấu hiệu bất thường, thay đổi recovery method hoặc thực hiện hành động đặc quyền, hệ thống vẫn có thể yêu cầu xác thực lại.

## 7. Device binding và bằng chứng mật mã

**Device binding** liên kết một thiết bị hoặc ứng dụng với một khóa mật mã đã đăng ký. Khi truy cập, client chứng minh quyền kiểm soát khóa bằng cách ký challenge hoặc tạo proof theo giao thức.

Khác với fingerprint, bằng chứng mật mã có thể xác minh bằng public key đã lưu ở server. Nhưng nó vẫn chứng minh quyền kiểm soát khóa, không chứng minh tuyệt đối thiết bị sạch malware hoặc người dùng là chủ tài khoản.

### Luồng challenge-response

1. Server tạo nonce ngẫu nhiên, thời hạn ngắn và gắn với session/request.
2. Client dùng khóa riêng đã đăng ký ký challenge cùng ngữ cảnh cần ràng buộc.
3. Client gửi proof và key ID.
4. Server tìm public key đã đăng ký, xác minh chữ ký, nonce, thời hạn và ngữ cảnh.
5. Server đánh dấu nonce đã dùng để chống replay.
6. Kết quả chỉ được dùng trong phạm vi device binding và chính sách đã xác định.

~~~mermaid
sequenceDiagram
    participant C as Client device
    participant S as Server
    C->>S: Yêu cầu challenge
    S->>S: Tạo nonce + request context + expiry
    S-->>C: Challenge
    C->>C: Ký challenge bằng private key
    C->>S: key_id + signature + challenge_id
    S->>S: Tìm public key, kiểm tra chữ ký và expiry
    S->>S: Kiểm tra nonce chưa dùng và đánh dấu đã dùng
    S-->>C: Proof hợp lệ hoặc từ chối
~~~

### Ràng buộc challenge

Challenge nên liên kết với:

- Account hoặc subject đang xác thực.
- Session hoặc request cụ thể.
- Hành động cần bảo vệ nếu đây là transaction signing.
- Thời hạn ngắn và nonce dùng một lần.
- Loại giao thức và phiên bản thuật toán đã cấu hình.

Nếu chữ ký chỉ bao phủ một chuỗi chung không có nonce, attacker có thể replay proof cũ. Nếu không ràng buộc account/session, proof của thiết bị này có thể bị dùng sai ngữ cảnh.

### Bảo vệ private key

Khóa riêng nên được tạo và giữ trong vùng bảo vệ phù hợp như secure hardware hoặc keystore của nền tảng khi có thể. Không xuất private key ra log hoặc gửi về server. Cần có quy trình đăng ký, đổi thiết bị, backup, thu hồi và xử lý khi thiết bị bị mất.

Nếu malware có thể yêu cầu thiết bị ký challenge trong khi người dùng đã đăng nhập, device binding có thể không ngăn được mọi hành động của attacker. Có thể cần user verification, transaction confirmation hoặc step-up độc lập.

## 8. Attestation và device posture

**Attestation** là cơ chế để một bên chứng minh thuộc tính hoặc trạng thái của ứng dụng/thiết bị bằng bằng chứng được tạo theo trust model của nền tảng. Attestation có thể giúp server đánh giá app có phải bản được phát hành hợp lệ, thiết bị có đáp ứng một số điều kiện hoặc khóa có được tạo trong môi trường bảo vệ hay không.

Attestation không phải một khái niệm đồng nhất. Mỗi nền tảng có định dạng, trust root, mức bảo đảm, chính sách riêng tư và giới hạn khác nhau.

### Các bước đánh giá

1. Xác định nền tảng và loại attestation cần dùng.
2. Xác minh chữ ký/chứng thư theo trust root đã cấu hình.
3. Kiểm tra thời hạn, trạng thái thu hồi và phiên bản giao thức.
4. Kiểm tra challenge/nonce để chống replay.
5. Kiểm tra app identity, package/bundle và các thuộc tính được chứng minh.
6. Ánh xạ kết quả vào chính sách thiết bị; không suy ra thuộc tính không được attestation bảo đảm.
7. Lưu kết quả tối thiểu và thời điểm, không lưu dữ liệu dư thừa.

### MDM và endpoint management

Trong môi trường doanh nghiệp, MDM hoặc endpoint management có thể cung cấp trạng thái thiết bị:

- Thiết bị còn thuộc tổ chức và được quản lý.
- Mã hóa ổ đĩa đang bật.
- Screen lock và chính sách cập nhật đáp ứng yêu cầu.
- Thiết bị chưa bị đánh dấu mất hoặc thu hồi.
- Ứng dụng bảo mật endpoint đang hoạt động theo báo cáo gần nhất.

Dữ liệu MDM có thể trễ hoặc không có khi thiết bị offline. Một trạng thái compliant từ vài ngày trước không chứng minh thiết bị hiện tại vẫn compliant. Hãy kiểm tra freshness và có chính sách khi hệ thống quản lý không phản hồi.

### Không biến attestation thành phán quyết tuyệt đối

Attestation có thể không khả dụng trên một số thiết bị hợp lệ, bị giới hạn bởi nền tảng hoặc thay đổi theo phiên bản hệ điều hành. Không nên khóa toàn bộ người dùng chỉ vì thiết bị không hỗ trợ một cơ chế nếu có phương thức thay thế an toàn phù hợp.

## 9. WebAuthn và tín hiệu liên quan đến authenticator

Passkey/WebAuthn có thể cung cấp một số thông tin liên quan đến authenticator:

- Credential ID và public key đã đăng ký.
- RP ID và origin được xác minh theo WebAuthn.
- User presence và user verification flags.
- Backup eligibility (BE) và backup state (BS).
- Sign counter nếu authenticator cung cấp.
- Attestation information trong quá trình đăng ký nếu được yêu cầu và chấp nhận.

Những thông tin này cần được diễn giải đúng.

### User verification không phải device posture

UV cho biết authenticator đã thực hiện kiểm tra người dùng theo cơ chế của nó, chẳng hạn PIN hoặc sinh trắc học cục bộ. UV không cho biết hệ điều hành đã cập nhật, ổ đĩa đã mã hóa hoặc thiết bị không có malware.

### Backup eligibility và backup state

Credential có thể được thiết kế để sao lưu/đồng bộ qua hệ sinh thái của nhà cung cấp. BE/BS giúp RP hiểu đặc tính backup của credential theo WebAuthn. Không nên mặc định credential đồng bộ là yếu hoặc credential không đồng bộ luôn an toàn hơn; cần xem threat model, khả năng phục hồi và yêu cầu assurance.

### Sign counter

Một số authenticator cung cấp signature counter để phát hiện một số trường hợp clone. Tuy nhiên, passkey đồng bộ và nhiều authenticator hiện đại có thể không duy trì counter tăng đơn điệu. Counter bằng 0 hoặc không tăng không tự chứng minh credential bị clone. Hãy tuân theo hướng dẫn WebAuthn, xem xét loại authenticator và kết hợp tín hiệu khác.

### Attestation trong WebAuthn

Attestation có thể cung cấp thông tin về authenticator trong lúc đăng ký, nhưng có hệ sinh thái passkey cố ý giảm hoặc ẩn thông tin định danh thiết bị để bảo vệ quyền riêng tư. RP chỉ nên yêu cầu và sử dụng attestation khi có mục đích rõ, hỗ trợ phù hợp và chính sách đã công bố.

## 10. Đánh giá anomaly theo ngữ cảnh

Device anomaly không nên được chấm điểm chỉ từ việc thiết bị có mới hay không. Hãy kết hợp tín hiệu với tài khoản, credential, hành động và chất lượng nguồn.

### Ví dụ các ngữ cảnh

| Ngữ cảnh | Diễn giải có thể phù hợp |
|---|---|
| Thiết bị mới, passkey hợp lệ, không có sự kiện rủi ro khác | Có thể là thay thiết bị hợp pháp; tiếp tục theo chính sách và ghi nhận |
| Cookie thiết bị quen thuộc nhưng recovery method vừa đổi | Cookie không đủ để giảm rủi ro; step-up hoặc review |
| Thiết bị được MDM quản lý, posture mới và đạt | Tín hiệu tích cực trong phạm vi dữ liệu MDM chứng minh |
| Browser fingerprint thay đổi sau cập nhật | Tín hiệu yếu; không tự động chặn |
| Device-bound proof không hợp lệ hoặc nonce đã dùng | Bằng chứng binding thất bại; từ chối proof và đánh giá request |
| Thiết bị bị đánh dấu mất trong MDM | Có căn cứ mạnh để chặn hoặc thu hồi thiết bị theo chính sách |
| Attestation không khả dụng | Unknown; dùng fallback đã phê duyệt |
| Thiết bị mới đồng thời có credential stuffing | Kết hợp tín hiệu để tăng mức kiểm soát |

### Cẩn trọng với tín hiệu tương quan

Một browser mới có thể đồng thời tạo fingerprint khác, cookie mới và user-agent khác. Đây có thể là ba biểu hiện của cùng một thay đổi môi trường, không phải ba bằng chứng độc lập.

Tương tự, IP mới và vị trí mới có thể cùng xuất phát từ một mạng di động. Nếu cộng điểm riêng cho mọi biểu hiện mà không xét tương quan, risk score sẽ phóng đại bất thường.

## 11. Phản ứng thích ứng

Phản ứng phải tương xứng với độ tin cậy của tín hiệu và hậu quả của hành động.

| Mức/loại tín hiệu | Phản ứng có thể chọn |
|---|---|
| Thiết bị mới nhưng rủi ro thấp | Cho phép sau authentication bình thường; ghi nhận thiết bị mới |
| Thiết bị mới và hành động nhạy cảm | Step-up bằng passkey/MFA hoặc xác thực lại |
| Fingerprint bất thường nhưng nguồn yếu | Observe, không tự động khóa tài khoản |
| Posture không đạt chính sách bắt buộc | Hạn chế tài nguyên doanh nghiệp hoặc yêu cầu thiết bị compliant |
| Device-bound proof sai | Từ chối proof, không coi thiết bị đã được xác minh |
| Attestation lỗi hoặc hết hạn | Thử lại có giới hạn hoặc fallback theo chính sách |
| Thiết bị báo mất/thu hồi từ MDM | Chặn thiết bị và thu hồi session liên quan |
| Có bằng chứng thiết bị bị xâm nhập | Thu hồi session/token, step-up hoặc incident response |

### Step-up đúng loại rủi ro

Nếu rủi ro là thiết bị bị sao chép cookie, chỉ yêu cầu mật khẩu có thể không đủ nếu mật khẩu cũng đã bị lộ. Nếu rủi ro là thiết bị không compliant, yêu cầu OTP không sửa được posture. Cần chọn kiểm soát giải quyết nguyên nhân:

- Credential theft: passkey hoặc xác thực chống phishing, thu hồi session.
- Device posture: kiểm tra MDM/attestation hoặc dùng thiết bị compliant.
- Session replay: thu hồi cookie/token, nonce và sender-constraining.
- Hành động giá trị cao: xác thực lại và kiểm tra quyền riêng.

### Không để risk signal bỏ qua yêu cầu tối thiểu

Thiết bị quen thuộc hoặc posture đạt không được phép bỏ qua MFA bắt buộc, user verification hoặc kiểm tra quyền. Risk-based authentication chỉ điều chỉnh bước bổ sung; không hạ mức assurance tối thiểu do chính sách yêu cầu.

## 12. Vòng đời thiết bị

Device registry cần có vòng đời rõ ràng, giống như credential registry.

### Đăng ký

- Chỉ đăng ký thiết bị sau khi tài khoản đã được xác thực đủ mạnh.
- Hiển thị tên/mô tả thiết bị cho người dùng kiểm tra.
- Lưu loại tín hiệu, nguồn và thời điểm đăng ký.
- Nếu có khóa mật mã, lưu public key và metadata cần thiết; private key ở lại client.
- Không cấp trạng thái trusted vĩnh viễn.

### Cập nhật

- Làm mới posture theo chu kỳ và khi có sự kiện.
- Ghi nhận thay đổi browser/OS mà không mặc định đó là thiết bị khác.
- Xác minh lại attestation khi cần.
- Cập nhật trạng thái sau khi thiết bị được sửa chữa, cài lại hoặc chuyển chủ sở hữu.

### Thu hồi

Thu hồi khi:

- Người dùng báo mất hoặc bán thiết bị.
- Thiết bị bị xóa khỏi MDM hoặc tổ chức.
- Khóa thiết bị bị nghi lộ.
- Phát hiện session theft hoặc hoạt động bất thường.
- Thiết bị không còn đáp ứng chính sách bắt buộc.

Thu hồi device marker không nhất thiết thu hồi session cookie đã bị sao chép nếu hai thứ không có mapping. Cần xác định và thu hồi các session/token liên quan theo chính sách.

### Thiết bị dùng chung

Kiosk, máy quầy, máy phòng lab và máy gia đình dùng chung không nên được đánh dấu “trusted” cho một cá nhân theo cách làm lộ phiên người dùng tiếp theo. Cần:

- Tách user session và device identity.
- Logout rõ ràng, xóa dữ liệu cục bộ và browser profile khi cần.
- Không lưu cookie ghi nhớ thiết bị dùng chung nếu không phù hợp.
- Có timeout ngắn và giới hạn hành động.
- Yêu cầu người dùng xác thực riêng cho mỗi phiên.

## 13. Rủi ro riêng tư và khả năng tiếp cận

Fingerprint và device tracking có thể tạo hồ sơ dài hạn về thiết bị và hoạt động của một người. Việc thu thập cần giới hạn theo mục đích bảo vệ tài khoản.

### Data minimization

- Chỉ thu thập thuộc tính cần thiết để đánh giá rủi ro cụ thể.
- Tránh fingerprint bền vững liên website.
- Đặt thời hạn lưu và xóa dữ liệu thiết bị không còn hoạt động.
- Hạn chế ai có thể xem device history và posture.
- Không đưa raw fingerprint, attestation token hoặc private data vào log chung.
- Thông báo rõ thiết bị nào được ghi nhớ và cách người dùng thu hồi.

### Tránh phân biệt đối xử

Người dùng có thể hợp lệ khi:

- Dùng thiết bị cũ hoặc không hỗ trợ attestation.
- Thường xuyên xóa cookie vì lý do riêng tư.
- Dùng browser chống fingerprinting.
- Sử dụng công nghệ hỗ trợ hoặc cấu hình đặc biệt.
- Đăng nhập từ máy dùng chung hoặc thiết bị được tổ chức cấp tạm.

Không nên biến các đặc điểm đó thành căn cứ tự động từ chối nếu có phương thức xác minh thay thế phù hợp. Đo tỷ lệ step-up và từ chối giữa các loại thiết bị/nhóm người dùng trong phạm vi hợp pháp, rồi điều tra chênh lệch.

## 14. Tình huống thực hành: thiết bị mới truy cập hệ thống quản trị

**Bối cảnh:** Một quản trị viên thường đăng nhập bằng laptop công ty có MDM. Hôm nay người này dùng laptop cá nhân để xem bảng điều khiển. Browser fingerprint mới, không có device cookie, nhưng passkey đã đăng ký xác thực thành công với user verification.

### Đánh giá

1. Fingerprint và cookie mới chỉ cho biết client chưa được nhận diện.
2. Passkey hợp lệ xác minh quyền kiểm soát credential và ràng buộc RP/origin theo WebAuthn.
3. Passkey không chứng minh laptop cá nhân đạt posture của công ty.
4. Tài khoản có quyền quản trị nên policy có thể yêu cầu thiết bị compliant.
5. MDM không có bản ghi thiết bị cá nhân; đây là trạng thái unknown, không phải bằng chứng thiết bị độc hại.

### Phản ứng

- Cho phép truy cập trang thông tin công khai hoặc tài nguyên ít nhạy cảm nếu chính sách cho phép.
- Chặn hoặc giới hạn thao tác quản trị yêu cầu thiết bị được quản lý.
- Yêu cầu người dùng chuyển sang laptop compliant hoặc thực hiện quy trình ngoại lệ có phê duyệt.
- Ghi nhận thiết bị mới với thời hạn và quyền tối thiểu nếu người dùng muốn ghi nhớ.
- Không cấp trạng thái trusted cho laptop cá nhân chỉ vì passkey thành công.

### Kịch bản thiết bị bị mất

Nếu MDM đánh dấu laptop công ty bị mất, hệ thống nên:

1. Thu hồi device binding và marker liên quan.
2. Thu hồi session/token được liên kết với thiết bị nếu có thể xác định.
3. Yêu cầu xác thực lại trên thiết bị khác.
4. Kiểm tra credential hoặc recovery method mới được thêm.
5. Điều tra request sau thời điểm thiết bị mất.

## 15. Kiểm thử device anomaly

Kiểm thử trong môi trường được phép, dùng tài khoản và thiết bị thử nghiệm:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Đăng nhập từ browser mới | Ghi nhận tín hiệu thiết bị mới; không tự động kết luận chiếm tài khoản |
| Cookie thiết bị bị xóa | Thiết bị có thể được nhận diện là mới; authentication vẫn bắt buộc |
| Device marker bị sao chép | Không được coi marker là bằng chứng đủ; phát hiện qua binding/risk khác khi có |
| User-agent bị giả | Không dùng user-agent làm bằng chứng thiết bị mạnh |
| Browser cập nhật làm fingerprint thay đổi | Không tự động khóa tài khoản |
| Device-bound signature sai | Từ chối proof |
| Challenge hết hạn hoặc nonce đã dùng | Từ chối replay |
| Public key bị thu hồi | Không chấp nhận proof bằng khóa đó |
| Attestation signature sai | Từ chối kết quả attestation |
| Attestation hết hạn hoặc trust chain không hợp lệ | Đánh dấu không hợp lệ/unknown theo chính sách |
| MDM posture cũ | Không coi dữ liệu cũ là trạng thái hiện tại |
| Thiết bị bị đánh dấu mất | Chặn hoặc thu hồi theo chính sách |
| Passkey backup state thay đổi | Đánh giá theo profile; không tự động kết luận clone |
| Sign counter không tăng với passkey đồng bộ | Không kết luận clone chỉ từ counter |
| Thiết bị dùng chung | Không gắn session cá nhân lâu dài cho người dùng tiếp theo |
| Risk engine không nhận được device signal | Fallback an toàn, không bỏ qua authentication bắt buộc |
| Người dùng hợp lệ dùng browser privacy mode | Có phương thức thay thế, không khóa mặc định |
| Thiết bị mới yêu cầu hành động quản trị | Step-up/posture check theo chính sách |

### Chỉ số theo dõi

- Tỷ lệ đăng nhập từ thiết bị mới theo ứng dụng và loại client.
- Tỷ lệ false positive do fingerprint hoặc cookie thay đổi.
- Tỷ lệ step-up thành công và tỷ lệ người dùng bỏ dở.
- Tỷ lệ thiết bị compliant/unknown/non-compliant.
- Tuổi dữ liệu posture và tỷ lệ nguồn MDM không khả dụng.
- Số device marker hoặc khóa bị thu hồi.
- Số sự cố session theft có liên quan đến thiết bị.
- Chênh lệch từ chối giữa loại thiết bị, browser và công nghệ hỗ trợ.

Không tối ưu chỉ theo số lượng thiết bị nhận diện được. Mục tiêu là giảm rủi ro với mức thu thập và ma sát hợp lý.

## 16. Checklist thiết kế device anomaly

- [ ] Phân biệt device recognition, device binding, user authentication và device posture.
- [ ] Thiết bị mới được xem là tín hiệu, không phải bằng chứng tấn công.
- [ ] Mỗi signal có nguồn, thời điểm, confidence, integrity và TTL.
- [ ] User-agent/fingerprint không được coi là định danh mật mã.
- [ ] Device cookie được sinh ngẫu nhiên, có expiry, verifier và khả năng thu hồi.
- [ ] Cookie thiết bị không thay thế password/passkey/MFA.
- [ ] Device binding dùng challenge ngẫu nhiên, hết hạn, gắn với session/request và chống replay.
- [ ] Private key được bảo vệ ở client; server chỉ lưu public key và metadata cần thiết.
- [ ] Attestation được xác minh theo trust root, nonce, thời hạn và trạng thái thu hồi.
- [ ] MDM posture có freshness; trạng thái unknown không bị hiểu nhầm là compliant.
- [ ] WebAuthn UV, BE/BS và sign counter được diễn giải theo đúng đặc tính authenticator.
- [ ] Không dùng sign counter đơn lẻ để kết luận passkey bị clone.
- [ ] Phản ứng risk-based phù hợp với nguyên nhân: step-up, posture check, restrict hoặc revoke.
- [ ] Thiết bị quen thuộc không được bỏ qua assurance tối thiểu và authorization.
- [ ] Có quy trình đăng ký, cập nhật, thu hồi, thiết bị mất và thiết bị dùng chung.
- [ ] Dữ liệu fingerprint/posture được tối thiểu hóa, giới hạn lưu và kiểm soát truy cập.
- [ ] Có fallback công bằng cho thiết bị không hỗ trợ attestation hoặc browser privacy mode.
- [ ] Kiểm thử spoofing, replay, cookie theft, stale posture và false positive.

## Ghi nhớ

Device anomaly là tín hiệu về thiết bị hoặc môi trường client khác với ngữ cảnh đã biết. Nó có thể đến từ fingerprint, cookie, posture, attestation, MDM hoặc bằng chứng kiểm soát khóa. Các nguồn này có mức bảo đảm khác nhau: fingerprint và cookie dễ thay đổi hoặc bị sao chép; device-bound proof mạnh hơn về quyền kiểm soát khóa; attestation/MDM chỉ chứng minh những thuộc tính mà trust model của chúng thực sự bảo đảm.

Thiết bị quen thuộc không chứng minh người dùng là chủ tài khoản, và thiết bị mới không chứng minh có tấn công. Hãy kết hợp tín hiệu với credential, lịch sử tài khoản và hành động; chọn step-up hoặc giới hạn theo rủi ro; quản lý vòng đời thiết bị; đồng thời bảo vệ quyền riêng tư và cung cấp phương thức thay thế công bằng.
