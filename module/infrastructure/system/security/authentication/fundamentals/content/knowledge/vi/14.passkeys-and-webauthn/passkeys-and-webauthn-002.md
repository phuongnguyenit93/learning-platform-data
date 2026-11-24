# WebAuthn credential

> **Chương:** Passkey và WebAuthn  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Cấu trúc và vòng đời WebAuthn credential, cách đăng ký khóa công khai, sử dụng assertion để xác thực, ràng buộc origin/RP ID, user verification, discoverability, attestation, đồng bộ và thu hồi credential.

## 1. WebAuthn credential là gì?

**WebAuthn credential** là một credential khóa công khai được tạo và sử dụng theo Web Authentication API. Credential liên kết một relying party (RP) với một authenticator và một cặp khóa mật mã. Khi đăng ký, authenticator tạo khóa riêng và khóa công khai; RP lưu thông tin cần thiết để nhận diện credential và xác minh chữ ký. Khi đăng nhập, authenticator dùng khóa riêng để ký dữ liệu xác thực gắn với challenge do RP tạo.

Điểm quan trọng là **khóa riêng không được gửi lên RP** trong luồng WebAuthn thông thường. Server lưu khóa công khai, credential ID và metadata liên quan. Việc giữ khóa riêng và thực hiện thao tác ký thuộc trách nhiệm của authenticator hoặc nền tảng quản lý credential.

Một WebAuthn credential không chỉ là “một passkey” hiển thị trong giao diện. Nó là một đối tượng kỹ thuật có định danh, khóa công khai, phạm vi relying party và trạng thái vòng đời. Cách credential được lưu (trên thiết bị, khóa bảo mật hay đồng bộ qua hệ sinh thái) ảnh hưởng đến khả năng khôi phục và mức bảo đảm.

### Kết quả học tập

Sau bài này, người học có thể:

- Giải thích cấu trúc và vai trò của WebAuthn credential.
- Phân biệt credential ID, public key, private key, RP ID, origin và challenge.
- Mô tả quy trình đăng ký (registration/attestation) và xác thực (authentication/assertion).
- Phân biệt discoverable và non-discoverable credential, user presence và user verification.
- Đánh giá attestation, backup eligibility/state và sign counter trong đúng ngữ cảnh.
- Thiết kế lưu trữ, quản lý, thay thế và thu hồi credential an toàn.

## 2. Thành phần của một WebAuthn credential

| Thành phần | Ý nghĩa | Nơi thường được xử lý/lưu |
|---|---|---|
| **Credential ID** | Giá trị định danh credential, được RP dùng để tra cứu khóa công khai | RP lưu; client gửi lại trong assertion khi cần |
| **Public key** | Khóa dùng để xác minh chữ ký từ authenticator | RP lưu |
| **Private key** | Khóa bí mật tạo chữ ký | Authenticator hoặc nền tảng quản lý credential giữ |
| **RP ID** | Định danh relying party, thường là domain được cấu hình | RP cấu hình; authenticator data ràng buộc bằng hash |
| **Origin** | Nguồn gốc website gọi WebAuthn, gồm scheme/host/port | Browser ghi vào client data; server xác minh |
| **Challenge** | Giá trị ngẫu nhiên do RP tạo cho một lần đăng ký hoặc xác thực | RP tạo và lưu tạm; response phải khớp |
| **User handle** | Định danh người dùng ổn định, không phải username hiển thị | RP lưu và dùng để liên kết tài khoản |
| **Authenticator data** | Dữ liệu gồm RP ID hash, flags và counter/extension data | Authenticator tạo, RP xác minh |
| **Client data** | Ngữ cảnh do client/browser tạo, gồm type, challenge, origin và thông tin liên quan | Client gửi, RP xác minh |
| **Transports** | Gợi ý cách client có thể liên lạc với authenticator | Có thể lưu như metadata hỗ trợ trải nghiệm |

### Sơ đồ trách nhiệm

~~~mermaid
flowchart LR
    U["Người dùng"] --> C["Browser / WebAuthn client"]
    C <-->|"API WebAuthn / CTAP"| A["Authenticator"]
    A -->|"Tạo và giữ private key"| K["Credential key pair"]
    C -->|"Registration response / assertion"| R["Relying Party"]
    R --> DB["Credential ID + public key + metadata"]
    R -->|"Xác minh chữ ký và ngữ cảnh"| V["Quyết định xác thực"]
~~~

Sơ đồ chỉ thể hiện trách nhiệm khái niệm. Khóa riêng được tạo và bảo vệ bởi authenticator; tùy nền tảng, khóa có thể được bảo vệ bằng phần cứng, vùng bảo mật của hệ điều hành hoặc cơ chế đồng bộ credential. RP không được yêu cầu client gửi private key.

## 3. RP ID và origin: nền tảng chống phishing

Hai giá trị thường bị nhầm lẫn:

- **Origin** xác định nguồn gốc trang web đang chạy, bao gồm scheme, hostname và port (khi khác mặc định). Ví dụ: **https://login.example.com**.
- **RP ID** xác định relying party mà credential được tạo cho, thường là domain như **example.com** hoặc **login.example.com**, theo quy tắc của WebAuthn.

RP ID không phải URL đầy đủ và không chứa path. Origin phải nằm trong phạm vi được phép đối với RP ID theo quy tắc của trình duyệt và giao thức.

Khi credential được đăng ký cho RP ID **example.com**, một trang giả mạo ở **example-login.invalid** không thể yêu cầu authenticator tạo assertion hợp lệ cho RP ID thật chỉ bằng cách sao chép giao diện. Trình duyệt kiểm soát origin và ràng buộc RP ID; server tiếp tục xác minh cả origin lẫn RP ID hash trong authenticator data.

### Vì sao phải kiểm tra cả hai?

1. Origin giúp RP xác nhận trang gọi WebAuthn thuộc nguồn được phép.
2. RP ID hash trong authenticator data ràng buộc credential với relying party.
3. Challenge giúp response gắn với yêu cầu hiện tại, chống sử dụng lại response cũ.
4. Chữ ký chứng minh quyền kiểm soát private key tương ứng với public key đã đăng ký.

Nếu server bỏ qua origin hoặc challenge, có thể làm suy yếu ràng buộc chống phishing hoặc chống replay. Nếu cấu hình RP ID quá rộng, nhiều subdomain có thể nằm trong cùng phạm vi credential; cần đánh giá phạm vi domain và quản trị subdomain, đặc biệt với subdomain do nhiều nhóm hoặc nhà cung cấp khác nhau quản lý.

## 4. Đăng ký credential: Registration và attestation

Đăng ký là bước RP liên kết credential mới với tài khoản. Đây là thao tác nhạy cảm: người có thể thêm credential vào tài khoản sẽ có thêm một cách đăng nhập trong tương lai.

### Luồng đăng ký khái niệm

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Browser
    participant A as Authenticator
    participant R as RP / Server
    U->>C: Chọn tạo passkey
    C->>R: Xin registration options
    R-->>C: Challenge + RP ID + user info + options
    C->>A: Yêu cầu tạo credential
    A->>U: Yêu cầu UP/UV theo chính sách
    U-->>A: Chạm / PIN / sinh trắc học cục bộ
    A-->>C: Credential ID + public key + attestation object
    C->>R: Gửi registration response
    R->>R: Kiểm tra challenge, origin, RP ID, flags, attestation theo chính sách
    R->>R: Liên kết credential với tài khoản
    R-->>C: Đăng ký thành công
~~~

### Các bước chính ở RP

1. Xác minh người dùng đã đăng nhập hoặc đã được chứng minh danh tính ở mức phù hợp để thêm authenticator.
2. Tạo challenge ngẫu nhiên, đủ khó đoán, gắn với tài khoản và phiên đăng ký, có thời hạn ngắn.
3. Xác định RP ID, user handle, thuật toán được phép và yêu cầu user verification.
4. Gửi publicKeyCredentialCreationOptions tới client.
5. Nhận response từ client và dùng thư viện WebAuthn đáng tin cậy để xác minh.
6. Kiểm tra challenge, origin, RP ID hash, credential ID, public key, flags, và attestation nếu chính sách yêu cầu.
7. Kiểm tra credential chưa được liên kết trái phép với tài khoản khác theo chính sách.
8. Lưu credential và metadata cần thiết; tiêu thụ challenge một lần.
9. Ghi audit và thông báo cho chủ tài khoản về credential mới.

### Attestation là gì?

**Attestation** là thông tin mà authenticator có thể cung cấp trong quá trình tạo credential, giúp RP đánh giá nguồn gốc hoặc đặc tính của authenticator theo mô hình tin cậy nhất định. Tùy kiểu attestation, dữ liệu có thể bao gồm chứng thư hoặc chữ ký liên quan đến authenticator.

Attestation không phải lúc nào cũng cần. Đối với nhiều dịch vụ tiêu dùng, yêu cầu attestation có thể tạo thêm phức tạp, ảnh hưởng riêng tư và làm giảm khả năng tương thích. Một tổ chức có thể dùng attestation khi cần chính sách chỉ chấp nhận một nhóm authenticator đã được quản lý/đánh giá, nhưng phải xác định rõ trust roots, quy trình cập nhật metadata và cách xử lý thiết bị không cung cấp attestation.

**Không nhầm attestation với assertion:** attestation gắn với việc tạo credential; assertion được dùng trong những lần xác thực sau đó để chứng minh quyền kiểm soát khóa riêng.

## 5. Xác thực bằng credential: Assertion

Sau khi credential được đăng ký, RP có thể yêu cầu authenticator tạo assertion cho một lần đăng nhập.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Browser / client
    participant A as Authenticator
    participant R as RP / server
    U->>C: Chọn đăng nhập bằng passkey
    C->>R: Xin authentication options
    R-->>C: Challenge + RP ID + allowCredentials (nếu có)
    C->>A: Yêu cầu assertion
    A->>U: Yêu cầu UP/UV
    U-->>A: Chạm / PIN / sinh trắc học
    A-->>C: Authenticator data + signature + credential ID
    C->>R: Gửi assertion
    R->>R: Kiểm tra challenge, origin, RP ID hash, flags, chữ ký
    R-->>C: Cấp phiên hoặc từ chối
~~~

RP cần kiểm tra tối thiểu:

- Challenge khớp yêu cầu đang chờ, còn hạn và chưa được dùng.
- Client data có đúng loại thao tác xác thực và origin được phép.
- RP ID hash trong authenticator data khớp RP ID mong đợi.
- Credential ID tra được public key đã đăng ký và chưa bị thu hồi.
- Chữ ký xác thực được bằng public key đó trên đúng dữ liệu theo chuẩn.
- UP/UV đáp ứng yêu cầu chính sách.
- Tài khoản còn hoạt động và các điều kiện rủi ro/MFA khác được đáp ứng.

Không được cấp phiên chỉ vì client gửi một đối tượng JSON có các trường **verified: true** hoặc **user: alice**. Server phải tự xác minh response bằng thư viện WebAuthn và dữ liệu credential đáng tin cậy.

## 6. User presence và user verification

Hai cờ này có ý nghĩa khác nhau:

| Tín hiệu | Ý nghĩa | Ví dụ |
|---|---|---|
| **User Presence (UP)** | Có tương tác thể hiện người dùng hiện diện | Chạm khóa bảo mật |
| **User Verification (UV)** | Authenticator xác minh người dùng tại chỗ | PIN của khóa, sinh trắc học cục bộ hoặc cơ chế tương đương |

Một thao tác chạm khóa có thể đáp ứng UP nhưng không nhất thiết đáp ứng UV. Nếu RP yêu cầu xác thực người dùng tại authenticator, server phải kiểm tra cờ UV trong authenticator data theo thư viện/chuẩn; không suy luận từ giao diện.

PIN hoặc sinh trắc học thường được xử lý cục bộ bởi authenticator. RP không cần nhận PIN hoặc mẫu vân tay/khuôn mặt. RP nhận kết quả xác thực mật mã và cờ trạng thái theo giao thức.

### User Verification Requirement

Trong quá trình đăng ký/xác thực, RP có thể yêu cầu:

- **required:** cần UV; nếu authenticator không đáp ứng thì thao tác không đạt.
- **preferred:** ưu tiên UV nếu authenticator hỗ trợ, nhưng có thể chấp nhận khi không có.
- **discouraged:** không yêu cầu UV cho thao tác đó.

Tên lựa chọn và hành vi cụ thể phụ thuộc API WebAuthn và phiên bản; chính sách server phải kiểm tra kết quả thực tế. Không coi cấu hình client gửi đi là bằng chứng rằng UV đã thành công.

## 7. Discoverable và non-discoverable credential

WebAuthn credential có thể được sử dụng theo cách RP chỉ định credential được phép, hoặc theo cách authenticator có thể tìm credential phù hợp mà không cần RP gửi trước danh sách.

| Loại | Đặc điểm | Trải nghiệm |
|---|---|---|
| **Non-discoverable credential** (trước đây thường gọi resident-less) | RP thường cung cấp danh sách credential ID được chấp nhận trong allowCredentials | Người dùng có thể phải nhập username trước để RP tìm credential |
| **Discoverable credential** (resident credential) | Authenticator có thể tìm credential theo RP ID mà không cần RP gửi danh sách credential ID | Hỗ trợ username-less flow, ví dụ chọn tài khoản/passkey |

Discoverable credential giúp luồng “Đăng nhập bằng passkey” không cần người dùng nhập username trước. Authenticator có thể hiển thị các tài khoản liên quan đến RP ID; sau khi người dùng chọn, client gửi credential ID và assertion về server.

### User handle

Khi tạo discoverable credential, RP cung cấp **user handle** là định danh ổn định cho người dùng trong phạm vi RP. Không nên dùng email hoặc username có thể thay đổi làm user handle nếu điều đó gây rủi ro riêng tư hoặc liên kết sai. User handle không phải tên hiển thị và không nên chứa dữ liệu cá nhân không cần thiết.

RP cần bảo đảm user handle là duy nhất theo chính sách, gắn với đúng tài khoản và không thể bị client tự sửa để chọn tài khoản khác.

### Lựa chọn resident key

API WebAuthn cung cấp yêu cầu về resident key/discoverability, thường gồm **required**, **preferred** và **discouraged**. Server cần hiểu khả năng tương thích của authenticator, kiểm tra response và chọn trải nghiệm phù hợp. Không nên yêu cầu discoverable credential nếu hệ thống không cần luồng username-less hoặc nếu thiết bị mục tiêu không hỗ trợ.

## 8. Backup eligibility và backup state

Passkey có thể được đồng bộ giữa các thiết bị thông qua hệ sinh thái của nhà cung cấp. WebAuthn có các tín hiệu liên quan đến khả năng backup và trạng thái backup:

- **Backup Eligibility (BE):** tín hiệu cho biết credential có đủ điều kiện được backup/sync theo mô hình authenticator hay không.
- **Backup State (BS):** tín hiệu về trạng thái credential đã được backup/sync hay chưa, theo cách authenticator báo cáo.

Hai tín hiệu này hữu ích để RP hiểu loại credential và hỗ trợ chính sách quản lý. Tuy nhiên, không nên diễn giải chúng thành bằng chứng tuyệt đối rằng người dùng có hoặc không có bản sao, hoặc rằng thiết bị đồng bộ chắc chắn an toàn.

### Tác động đối với threat model

| Mô hình credential | Lợi ích | Cần cân nhắc |
|---|---|---|
| Gắn với một authenticator/thiết bị | Có thể tạo ranh giới thiết bị rõ hơn | Mất thiết bị có thể làm mất khả năng đăng nhập; cần dự phòng/recovery |
| Credential có thể đồng bộ | Khôi phục và sử dụng trên nhiều thiết bị thuận tiện | Phụ thuộc bảo vệ tài khoản đồng bộ, hệ sinh thái và quy trình recovery |
| Khóa bảo mật phần cứng riêng | Khóa có thể được bảo vệ trong phần cứng chuyên dụng | Mất khóa, hỏng thiết bị, quản lý khóa dự phòng và cấp phát |

RP nên ghi nhận BE/BS khi cần chính sách hoặc phân tích, nhưng không được coi các cờ đó là một cơ chế xác minh thiết bị duy nhất. Chúng cũng không thay thế việc kiểm tra chữ ký, origin, RP ID và trạng thái credential.

## 9. Sign counter và phát hiện credential bất thường

Authenticator data có thể chứa **signature counter**. Một số authenticator tăng bộ đếm sau mỗi lần sử dụng; RP có thể lưu giá trị trước đó và quan sát nếu giá trị mới không tăng như kỳ vọng.

Mục đích lịch sử của counter là hỗ trợ phát hiện credential bị sao chép hoặc sử dụng bất thường. Nhưng trong thực tế:

- Một số authenticator luôn trả counter bằng 0.
- Credential đồng bộ giữa nhiều thiết bị có thể không có bộ đếm đơn điệu toàn cục.
- Yêu cầu đồng thời có thể làm thứ tự counter quan sát được khác dự kiến.
- Counter bất thường là tín hiệu rủi ro, không phải bằng chứng tuyệt đối về clone.

Do đó, RP cần hiểu loại authenticator và chính sách áp dụng. Không khóa tài khoản tự động chỉ vì counter không tăng nếu giao thức/loại credential không bảo đảm điều đó. Có thể ghi nhận tín hiệu, đánh giá thêm phiên, thiết bị và hành vi rồi quyết định step-up hoặc thu hồi theo rủi ro.

## 10. Lưu trữ credential ở phía RP

RP lưu dữ liệu đủ để xác minh và quản lý credential, không lưu private key.

Một schema khái niệm:

~~~sql
CREATE TABLE webauthn_credential (
    credential_id       VARBINARY(1024) PRIMARY KEY,
    account_id          BIGINT NOT NULL,
    user_handle         VARBINARY(64) NOT NULL,
    public_key          BLOB NOT NULL,
    sign_count          BIGINT NOT NULL DEFAULT 0,
    aaguid              VARBINARY(16),
    transports          VARCHAR(255),
    backup_eligible     BOOLEAN,
    backup_state        BOOLEAN,
    created_at          TIMESTAMP NOT NULL,
    last_used_at        TIMESTAMP,
    revoked_at          TIMESTAMP
);
~~~

Schema chỉ minh họa các trường có thể cần; kiểu dữ liệu, chỉ mục, độ dài và metadata phải theo thư viện/DB thực tế. Có thể lưu thêm tên do người dùng đặt cho thiết bị, phiên bản credential hoặc thông tin attestation theo chính sách.

### Nguyên tắc lưu trữ

- Khóa công khai và credential ID cần bảo vệ khỏi sửa đổi trái phép, dù không phải bí mật như private key.
- Credential phải liên kết với đúng account ID ổn định.
- Không dùng username/email thay đổi làm khóa quan hệ duy nhất.
- Lưu trạng thái active/revoked và thời điểm tạo/sử dụng.
- Giới hạn quyền đọc/ghi bảng credential; audit thay đổi và thu hồi.
- Không ghi toàn bộ assertion, challenge hoặc dữ liệu nhạy cảm vào log nếu không cần.
- Không lưu private key hoặc yêu cầu người dùng tải private key lên server.

Challenge nên được lưu tạm theo phiên và mục đích, có thời hạn ngắn, chống dùng lại và gắn với đúng tài khoản/luồng. Không lưu challenge như một credential lâu dài.

## 11. Vòng đời credential: đăng ký, sử dụng, thay thế, thu hồi

~~~mermaid
stateDiagram-v2
    [*] --> Pending: Bắt đầu đăng ký
    Pending --> Active: Registration response hợp lệ
    Pending --> Expired: Challenge hết hạn / hủy
    Active --> Active: Tạo assertion và xác thực
    Active --> Suspected: Dấu hiệu rủi ro
    Suspected --> Active: Kiểm tra và xác nhận an toàn
    Suspected --> Revoked: Xác nhận bị chiếm / mất
    Active --> Revoked: Người dùng hoặc quản trị thu hồi
    Revoked --> [*]
    Expired --> [*]
~~~

### Đăng ký ban đầu và thêm credential

Chỉ cho phép đăng ký khi tài khoản ở trạng thái hợp lệ và chủ thể đạt mức xác thực cần thiết. Thêm credential mới cần xác thực lại/step-up theo rủi ro, ghi audit và thông báo. Đặc biệt với tài khoản đặc quyền, có thể yêu cầu phê duyệt bổ sung hoặc thiết bị đáp ứng chính sách.

### Sử dụng và theo dõi

Mỗi assertion phải được xác minh với challenge riêng. Theo dõi lần sử dụng gần nhất, trạng thái credential và tín hiệu rủi ro ở mức cần thiết. Không coi việc credential đã đăng ký một lần là cho phép nó được sử dụng vô thời hạn.

### Thay thế và thu hồi

Khi người dùng mất thiết bị, nghi bị chiếm tài khoản hoặc không còn kiểm soát credential:

1. Xác minh yêu cầu thu hồi từ chủ thể có thẩm quyền.
2. Đánh dấu credential cụ thể là revoked và ngăn dùng trong assertion mới.
3. Rà soát phiên/token đã phát hành từ credential đó nếu có dấu hiệu chiếm quyền.
4. Thông báo qua kênh liên hệ phù hợp và ghi audit.
5. Đăng ký credential thay thế sau khi xác thực chủ tài khoản bằng quy trình đủ mạnh.

Thu hồi credential không nhất thiết tự động hủy mọi phiên đã cấp trước đó. Hệ thống phải có chính sách riêng cho session, refresh token và access token.

## 12. Các lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Bỏ qua kiểm tra origin | Có thể chấp nhận response sai nguồn | Xác minh origin theo allowlist cấu hình |
| Bỏ qua RP ID hash | Mất ràng buộc relying party | Kiểm tra RP ID trong authenticator data |
| Challenge tĩnh hoặc dùng lại | Replay response | Challenge ngẫu nhiên, gắn phiên, tiêu thụ một lần |
| Chỉ kiểm tra cờ verified do client gửi | Client giả có thể tự tuyên bố thành công | Server xác minh bằng thư viện và khóa công khai |
| Lưu private key phía server | Tăng rủi ro lộ khóa, sai mô hình WebAuthn | Chỉ lưu public key và metadata cần thiết |
| Không ràng buộc credential với account | Credential có thể bị gắn nhầm tài khoản | Liên kết bằng account ID/user handle đáng tin cậy |
| Coi UP là UV | Đánh giá quá cao mức xác minh người dùng | Kiểm tra đúng cờ UV theo chính sách |
| Coi counter không tăng là bằng chứng clone chắc chắn | Khóa nhầm credential hợp lệ | Dùng counter như tín hiệu, đánh giá theo loại authenticator |
| Yêu cầu attestation không có lý do | Giảm riêng tư/tương thích và tăng vận hành | Xác định threat model và chính sách attestation |
| Cho phép thêm passkey từ phiên cũ | Attacker có thể gắn credential của mình | Re-auth/step-up, audit, thông báo |
| Thu hồi passkey nhưng giữ phiên chiếm quyền | Attacker tiếp tục sử dụng token cũ | Đánh giá và thu hồi phiên/token riêng |

## 13. Tình huống thực hành: tài khoản quản trị có hai passkey

**Bối cảnh:** Một quản trị viên có tài khoản quản lý dữ liệu nhân sự. Họ đăng ký một passkey đồng bộ trên điện thoại và một khóa bảo mật FIDO2 dự phòng. Chính sách yêu cầu user verification cho thao tác quản trị.

### Luồng bình thường

1. Quản trị viên truy cập origin chính thức.
2. RP gửi challenge và yêu cầu UV.
3. Người dùng chọn passkey hoặc khóa dự phòng.
4. Authenticator thực hiện UP/UV theo khả năng và ký assertion.
5. RP xác minh challenge, origin, RP ID, credential, chữ ký và UV.
6. Server kiểm tra tài khoản hoạt động, cấp phiên có mức xác thực phù hợp.
7. API kiểm tra quyền trước mỗi hành động quản trị.

### Kịch bản mất điện thoại

Quản trị viên báo mất điện thoại. Hệ thống cần:

- Thu hồi credential tương ứng với điện thoại hoặc đánh dấu rủi ro theo chính sách.
- Giữ khóa bảo mật dự phòng nếu chưa có dấu hiệu bị mất/chiếm.
- Thu hồi phiên/token có liên quan nếu thiết bị có thể bị mở khóa hoặc phiên bị chiếm.
- Yêu cầu xác minh đủ mạnh trước khi đăng ký passkey mới.
- Thông báo thay đổi và kiểm tra hoạt động trong khoảng thời gian mất thiết bị.

Không xóa mọi credential ngay khi nhận email tự khai “tôi bị mất điện thoại”; cần quy trình xác minh người yêu cầu. Ngược lại, không trì hoãn thu hồi nếu có bằng chứng rõ về nguy cơ truy cập trái phép.

### Kịch bản credential đồng bộ

Nếu passkey được đồng bộ, quản trị viên có thể sử dụng nó trên thiết bị mới thông qua hệ sinh thái đồng bộ. RP có thể nhận tín hiệu BE/BS tùy authenticator. Tổ chức cần quyết định liệu mô hình đồng bộ có phù hợp với chính sách tài khoản đặc quyền hay yêu cầu khóa phần cứng riêng. Dù chọn cách nào, việc xác minh assertion vẫn phải thực hiện đầy đủ.

## 14. Checklist triển khai WebAuthn credential

- [ ] Credential ID, public key, private key, RP ID, origin và challenge được phân biệt rõ.
- [ ] Private key được giữ trong authenticator/nền tảng quản lý credential; server chỉ lưu public key và metadata cần thiết.
- [ ] Registration challenge ngẫu nhiên, có thời hạn, gắn tài khoản và dùng một lần.
- [ ] Registration response được xác minh bằng thư viện WebAuthn đáng tin cậy.
- [ ] Assertion challenge, origin, RP ID hash, credential ID và chữ ký đều được kiểm tra.
- [ ] UP và UV được xử lý riêng theo yêu cầu chính sách.
- [ ] Discoverable/non-discoverable được chọn theo trải nghiệm và yêu cầu hệ thống.
- [ ] User handle ổn định, không chứa dữ liệu cá nhân không cần thiết.
- [ ] Attestation chỉ được yêu cầu khi threat model và chính sách cần.
- [ ] BE/BS và sign counter được diễn giải đúng giới hạn, không dùng như bằng chứng tuyệt đối.
- [ ] Thêm credential yêu cầu xác thực lại phù hợp, audit và thông báo.
- [ ] Có trạng thái active/revoked và quy trình thu hồi credential bị mất.
- [ ] Có phương án cho thiết bị dự phòng, đồng bộ và khôi phục tài khoản.
- [ ] Khi thu hồi credential, đánh giá cả phiên/token đã phát hành.
- [ ] API vẫn kiểm tra quyền tài nguyên sau khi xác thực WebAuthn thành công.

## Ghi nhớ

WebAuthn credential là một **credential khóa công khai gắn với relying party**: authenticator giữ khóa riêng, RP lưu khóa công khai và thông tin liên kết. Đăng ký tạo credential; xác thực dùng assertion ký challenge gắn với origin và RP ID. Các tín hiệu UP/UV, discoverability, attestation, backup state và sign counter cung cấp ngữ cảnh cho chính sách, nhưng phải được hiểu đúng giới hạn.

Một triển khai an toàn cần xác minh đầy đủ response ở server, bảo vệ việc thêm và thu hồi credential, quản lý phiên/token sau xác thực và duy trì phân quyền ở API. **Passkey giảm phishing ở bước chứng minh danh tính; vòng đời credential và các lớp kiểm soát còn lại quyết định tài khoản có được bảo vệ lâu dài hay không.**
