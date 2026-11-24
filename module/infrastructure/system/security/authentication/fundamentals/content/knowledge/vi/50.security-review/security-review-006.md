# Secret review

**Secret review** là hoạt động kiểm tra cách một hệ thống tạo, lưu trữ, phân phối, sử dụng, luân chuyển và thu hồi thông tin bí mật. Mục tiêu là bảo đảm chỉ đúng chủ thể được phép mới có thể sử dụng secret, trong đúng phạm vi và thời gian cần thiết; secret không bị lộ qua mã nguồn, log, bản dựng, thiết bị người dùng hoặc quy trình hỗ trợ; và tổ chức có thể phản ứng khi secret bị nghi ngờ xâm phạm.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, secret gắn trực tiếp với credential và ranh giới tin cậy. Mật khẩu, API key, OAuth client secret, khóa riêng ký token, khóa giải mã, seed TOTP và mã khôi phục đều có thể trao quyền xác thực hoặc khôi phục quyền truy cập. Một secret bị lộ có thể cho phép kẻ tấn công giả mạo người dùng, dịch vụ hoặc nhà phát hành token. Vì vậy, đánh giá secret phải xem xét cả tính bí mật, tính toàn vẹn, khả năng thu hồi, phạm vi quyền và bằng chứng kiểm toán.

Một secret không an toàn chỉ vì nó được mã hóa trong cơ sở dữ liệu. Nếu khóa giải mã nằm cùng nơi, tài khoản ứng dụng có quyền đọc toàn bộ secret, giá trị bị ghi vào log hoặc secret tồn tại vô thời hạn trong pipeline, ranh giới bảo vệ đã bị phá vỡ. Secret review cần theo dõi toàn bộ vòng đời và đường đi của secret từ lúc sinh ra đến khi bị hủy.

## 1. Secret là gì và cần bảo vệ điều gì?

Secret là dữ liệu mà việc tiết lộ cho chủ thể không được phép có thể làm mất tính bí mật hoặc cho phép thực hiện một hành động được bảo vệ. Secret thường có khả năng chứng minh quyền sở hữu, cấp quyền, giải mã dữ liệu hoặc tạo chữ ký số.

Một số loại secret thường gặp trong hệ thống xác thực:

| Loại | Công dụng | Hậu quả khi bị lộ |
|---|---|---|
| Mật khẩu | Chứng minh người dùng biết một giá trị đã đăng ký | Chiếm tài khoản nếu không có kiểm soát bổ sung |
| API key | Xác thực ứng dụng hoặc khách hàng gọi API | Gọi API bằng danh tính của chủ key, tiêu thụ quota hoặc truy cập dữ liệu |
| OAuth client secret | Xác thực confidential client với authorization server | Mạo danh client và có thể nhận token theo quyền của client |
| Khóa riêng ký token | Ký JWT hoặc assertion | Tạo token giả có vẻ hợp lệ với bên xác minh |
| Khóa riêng TLS/mTLS | Chứng minh danh tính máy chủ hoặc workload | Mạo danh endpoint hoặc workload |
| Seed TOTP | Sinh mã xác thực theo thời gian | Tạo mã MFA của tài khoản nếu có đủ thông tin liên quan |
| Mã khôi phục | Khôi phục quyền truy cập khi mất yếu tố xác thực | Vượt qua luồng MFA hoặc account recovery |
| Refresh token | Cấp access token mới | Duy trì quyền truy cập lâu dài nếu chưa bị thu hồi |
| Khóa mã hóa dữ liệu | Mở dữ liệu được bảo vệ | Đọc dữ liệu hoặc giải mã bản sao lưu |
| Secret dùng để ký webhook | Chứng minh webhook được tạo bởi bên gửi | Giả mạo sự kiện đến hệ thống nhận |

Không phải mọi thông tin nhạy cảm đều là secret. Email, username, tenant ID, issuer, key ID, certificate công khai, JWKS công khai và khóa công khai có thể cần bảo vệ về quyền riêng tư hoặc tính toàn vẹn, nhưng không có cùng tính chất với khóa riêng hoặc mật khẩu. Đánh giá sai loại dữ liệu có thể dẫn đến chọn sai cơ chế: mã hóa một giá trị vốn cần so khớp, hoặc lưu một giá trị có thể khôi phục dưới dạng bản rõ.

### 1.1. Phân biệt các khái niệm gần nhau

- **Identity:** danh tính mà hệ thống cần nhận biết, ví dụ một người dùng hoặc workload.
- **Credential:** dữ liệu hoặc vật thể được dùng để chứng minh danh tính hay quyền sở hữu, ví dụ mật khẩu, passkey, chứng chỉ hoặc API key.
- **Authenticator:** phương tiện thực hiện việc xác thực, ví dụ khóa bảo mật, ứng dụng TOTP hoặc passkey trong thiết bị.
- **Secret:** phần thông tin bí mật cần giữ khỏi chủ thể không được phép, ví dụ seed TOTP hoặc khóa riêng.
- **Token:** vật mang thông tin xác thực hoặc quyền đã được cấp. Một số token là bearer secret: ai sở hữu nó có thể sử dụng nó cho đến khi hết hạn hoặc bị thu hồi.
- **Public key/certificate:** thông tin công khai dùng để xác minh chữ ký hoặc danh tính chứng chỉ; khóa riêng tương ứng mới là secret.

Một passkey WebAuthn thường giữ khóa riêng trong authenticator hoặc môi trường bảo vệ của thiết bị. Máy chủ lưu credential ID, public key và metadata cần thiết để xác minh chữ ký. Máy chủ không cần lưu khóa riêng của passkey. Đây là ví dụ quan trọng về thiết kế giảm secret tập trung.

## 2. Mô hình đe dọa và ranh giới tin cậy

Secret review bắt đầu bằng việc xác định ai có thể lấy secret, thông qua đường nào và có thể làm gì sau khi lấy được. Không chỉ xem xét hacker bên ngoài. Nhân viên nội bộ, tài khoản CI/CD, extension trình duyệt, thư viện bên thứ ba, workload bị xâm nhập, bản sao lưu và hệ thống quan sát đều có thể trở thành đường rò rỉ.

### 2.1. Tài sản cần lập danh mục

Với mỗi secret, hãy ghi lại tối thiểu:

- Mục đích và loại secret.
- Chủ sở hữu nghiệp vụ và nhóm vận hành.
- Ứng dụng, môi trường, tenant và workload được phép sử dụng.
- Nguồn tạo secret và nơi lưu bản gốc.
- Các bản sao, cache, bản sao lưu và nơi secret được phân phối.
- Quyền đọc, quyền sử dụng, quyền xoay vòng và quyền thu hồi.
- Thời hạn, thời điểm phát hành, lần sử dụng gần nhất và trạng thái hiện tại.
- Cơ chế phát hiện lộ lọt và quy trình xử lý sự cố.

Không ghi giá trị secret vào danh mục. Dùng định danh, fingerprint hoặc prefix không nhạy cảm để tham chiếu. Fingerprint cần được tạo theo cách không làm lộ secret có entropy thấp.

### 2.2. Xác định các chủ thể và đường tấn công

Các câu hỏi quan trọng khi lập threat model:

1. Ai có thể đọc secret trong môi trường chạy?
2. Ai có thể sửa pipeline, image, manifest hoặc cấu hình để lấy secret?
3. Ai có quyền quản trị secret manager, KMS hoặc HSM?
4. Secret có xuất hiện trong log, tracing, crash dump, telemetry hay ticket hỗ trợ không?
5. Secret có được dùng chung giữa môi trường phát triển, staging và production không?
6. Một workload bị xâm nhập có thể đọc secret của workload khác không?
7. Secret có thể được dùng từ thiết bị cá nhân hoặc mạng không tin cậy không?
8. Nếu secret bị lộ, tổ chức có biết nó đã được dùng ở đâu và thu hồi được trong bao lâu không?

### 2.3. Ranh giới tin cậy cần vẽ

Một sơ đồ tối thiểu có thể thể hiện đường đi của secret:

~~~mermaid
flowchart LR
    A[Secret issuer hoặc KMS] -->|Cấp secret| B[Secret manager]
    B -->|Cấp theo danh tính workload| C[Ứng dụng xác thực]
    C -->|Dùng trong bộ nhớ| D[IdP hoặc dịch vụ phụ thuộc]
    C -->|Log đã che dữ liệu| E[Hệ thống quan sát]
    F[CI/CD identity] -->|Deploy workload| C
    G[Operator có phê duyệt] -->|Quản trị vòng đời| B
~~~

Sơ đồ phải thể hiện được nơi secret được tạo, nơi lưu, cách xác minh danh tính workload, các bản sao, người có quyền quản trị và nơi secret có thể vô tình đi vào. Nếu một mũi tên mang secret bản rõ đi qua một hệ thống không cần biết giá trị đó, cần xem lại thiết kế.

## 3. Phân loại và chọn cách lưu trữ

Không có một cách lưu duy nhất phù hợp cho mọi loại secret. Hãy xác định hệ thống cần **so sánh**, **sử dụng để tạo giá trị mới**, hay **khôi phục lại giá trị gốc**.

| Dữ liệu | Hệ thống cần làm gì? | Cách bảo vệ thường phù hợp |
|---|---|---|
| Mật khẩu người dùng | Xác minh giá trị được nhập | Lưu password verifier bằng thuật toán băm mật khẩu chuyên dụng, có salt riêng |
| API key ngẫu nhiên, chỉ dùng để xác minh | So khớp key được trình bày | Lưu hash/HMAC của key; hiển thị secret đầy đủ một lần khi tạo |
| Mã khôi phục ngẫu nhiên dùng một lần | Xác minh và đánh dấu đã tiêu thụ | Lưu verifier/hash, trạng thái sử dụng và thời hạn |
| Seed TOTP | Tạo mã xác thực theo thời gian | Mã hóa có xác thực; giới hạn quyền giải mã và kiểm toán truy cập |
| OAuth client secret cần gửi cho IdP | Lấy lại giá trị để xác thực client | Lưu trong secret manager hoặc kho mã hóa có kiểm soát |
| Khóa riêng ký token | Ký dữ liệu | Ưu tiên thao tác ký bên trong HSM/KMS; hạn chế tối đa xuất khóa |
| Khóa giải mã dữ liệu | Giải mã dữ liệu | KMS/HSM và envelope encryption, tách quyền quản lý khóa với dữ liệu |
| Public key hoặc chứng chỉ công khai | Xác minh chữ ký hoặc chuỗi tin cậy | Có thể công bố; cần bảo vệ tính toàn vẹn, nguồn gốc và cấu hình tin cậy |

### 3.1. Mật khẩu không được lưu dưới dạng có thể giải mã

Mật khẩu người dùng thường cần được xác minh, không cần lấy lại bản gốc. Lưu bằng thuật toán băm mật khẩu chuyên dụng như Argon2id, scrypt hoặc bcrypt với salt riêng cho từng tài khoản và tham số chi phí phù hợp. Cân nhắc pepper được bảo vệ riêng nếu kiến trúc có thể vận hành và xoay vòng an toàn.

Không dùng mã hóa có thể giải mã để lưu password verifier. Không dùng MD5, SHA-1 hoặc SHA-256 đơn lẻ để băm mật khẩu vì chúng quá nhanh trước tấn công dò đoán ngoại tuyến. Khi xác minh, cần giới hạn tốc độ, phát hiện credential stuffing và xử lý thông báo lỗi nhất quán.

### 3.2. Secret ngẫu nhiên có thể dùng verifier

API key hoặc mã khôi phục có entropy cao, được tạo bằng bộ sinh số ngẫu nhiên mật mã và chỉ cần so sánh khi người dùng trình bày có thể lưu dưới dạng hash hoặc HMAC. Vì hệ thống không cần lấy lại giá trị gốc, việc giữ bản có thể giải mã tạo thêm rủi ro không cần thiết.

Một API key nên có phần định danh công khai hoặc prefix để tìm bản ghi và phần secret ngẫu nhiên đủ mạnh. Ví dụ cấu trúc minh họa:

~~~text
ak_live_<public-id>.<random-secret>
~~~

`public-id` chỉ giúp định tuyến đến bản ghi; nó không phải bằng chứng xác thực. Hệ thống chỉ lưu verifier của `random-secret`, không lưu toàn bộ chuỗi. Khi xác minh, cần giới hạn tốc độ, so sánh an toàn và ghi nhận key ID đã dùng mà không ghi secret.

### 3.3. Secret cần khôi phục phải được mã hóa

Seed TOTP, OAuth client secret và một số khóa mã hóa cần được lấy lại để thực hiện phép toán. Các giá trị này phải được mã hóa khi lưu bằng thuật toán mã hóa có xác thực (AEAD), với khóa mã hóa được quản lý độc lập.

Không tự thiết kế thuật toán mã hóa. Dùng thư viện và dịch vụ quản lý khóa được duy trì. Lưu metadata cần thiết như key version, nonce/IV, authentication tag và định danh khóa. Không dùng lại nonce với cùng khóa khi thuật toán yêu cầu nonce duy nhất.

### 3.4. Khóa riêng nên được giữ trong ranh giới bảo vệ

Với khóa ký token hoặc khóa TLS, ưu tiên tạo và sử dụng khóa trong HSM/KMS hoặc thiết bị bảo mật phù hợp. Ứng dụng được cấp quyền thực hiện thao tác ký thay vì đọc khóa riêng ra bộ nhớ nếu kiến trúc cho phép.

Nếu cần sao lưu hoặc di chuyển khóa, phải có quy trình bảo vệ, phân quyền, kiểm toán và thử khôi phục. Việc xuất khóa riêng cần được xem là ngoại lệ có rủi ro cao và phải có lý do rõ ràng.

## 4. Tạo secret đúng cách

Secret phải được sinh bằng nguồn ngẫu nhiên mật mã (cryptographically secure pseudorandom number generator, CSPRNG). Không dùng thời gian, số thứ tự, tên người dùng, email, hash của dữ liệu công khai hoặc bộ sinh ngẫu nhiên không phù hợp làm secret.

### 4.1. Entropy và khả năng đoán

Entropy đo mức độ khó đoán của giá trị. Với một secret được chọn đều từ không gian có \(N\) khả năng, entropy lý tưởng là:

\[
H = \log_2(N) \text{ bit}
\]

Một chuỗi dài nhưng được tạo từ mẫu dễ đoán vẫn có entropy thấp. Ví dụ, ghép tên dịch vụ với ngày triển khai không tạo ra secret mạnh. Ngược lại, chuỗi ngẫu nhiên đủ dài từ CSPRNG có thể có entropy cao dù không dễ đọc.

Đối với API key hoặc token bearer, nên dùng giá trị ngẫu nhiên có ít nhất khoảng 128 bit entropy; nhiều hệ thống chọn 256 bit để có biên an toàn rộng. Con số thực tế phụ thuộc thời hạn, khả năng thử trực tuyến, mức quyền và cách giới hạn tốc độ. Với mật khẩu do con người chọn, cần chính sách độ dài, blocklist mật khẩu phổ biến/bị lộ và password hashing phù hợp; không thể suy ra entropy thực chỉ từ số ký tự.

### 4.2. Sinh và cấp phát

Một quy trình tạo secret an toàn cần:

- Sinh bằng CSPRNG của nền tảng hoặc dịch vụ tin cậy.
- Tránh tự viết PRNG hoặc thuật toán mật mã.
- Không dùng chung một secret cho nhiều khách hàng, tenant hoặc môi trường.
- Gắn định danh, chủ sở hữu, mục đích, thời điểm tạo và thời hạn.
- Hiển thị secret cho người nhận qua kênh an toàn, tối thiểu số lần cần thiết.
- Không đưa secret vào URL, query string, tên file, tên branch hoặc thông điệp commit.
- Có trạng thái thu hồi và quy trình thay thế ngay từ lúc tạo.

Ví dụ dưới đây mô tả một secret placeholder trong tài liệu cấu hình. Giá trị thật phải được cấp bởi secret manager khi triển khai:

~~~yaml
authentication:
  issuer: "https://identity.example.invalid"
  client_id: "workforce-api"
  client_secret_ref: "secret://production/workforce-api/client-secret"
~~~

Ứng dụng chỉ nhận tham chiếu và danh tính cần thiết để lấy secret. Không commit giá trị thật vào repository, kể cả repository private.

## 5. Lưu trữ và mã hóa secret

### 5.1. Dùng secret manager hoặc kho khóa chuyên dụng

Một secret manager giúp tập trung hóa việc lưu, phân phối, phân quyền, kiểm toán và xoay vòng secret. HSM/KMS phù hợp cho khóa mã hóa và ký. Dịch vụ được chọn cần hỗ trợ các thuộc tính mà hệ thống thực sự cần: kiểm soát truy cập theo danh tính, audit log, phiên bản, rotation, replication, backup và khả năng thu hồi.

Secret manager không tự động bảo đảm an toàn. Nếu mọi workload đều có quyền đọc mọi secret, việc tập trung chỉ tạo ra một kho có phạm vi ảnh hưởng lớn. Mỗi secret phải có policy cấp quyền riêng theo workload, môi trường và mục đích.

### 5.2. Envelope encryption

Với dữ liệu secret cần lưu dạng có thể khôi phục, có thể dùng envelope encryption:

1. Tạo một data encryption key (DEK) cho dữ liệu hoặc nhóm dữ liệu theo thiết kế.
2. Dùng DEK để mã hóa dữ liệu bằng AEAD.
3. Dùng key encryption key (KEK) trong KMS/HSM để bảo vệ DEK.
4. Lưu ciphertext, nonce, authentication tag, phiên bản thuật toán và wrapped DEK.
5. Khi cần giải mã, workload được xác thực và cấp quyền yêu cầu KMS mở DEK, sau đó giải mã dữ liệu.

DEK và KEK có mục đích khác nhau. Không lưu KEK trong cùng cơ sở dữ liệu với ciphertext. Cần kiểm soát ai có quyền gọi thao tác decrypt, vì quyền đó có thể tương đương quyền đọc secret.

### 5.3. Quản lý nonce, tag và metadata

Với AEAD như AES-GCM hoặc ChaCha20-Poly1305, cần tuân thủ yêu cầu nonce/IV của thuật toán và thư viện. Không tự tạo nonce bằng timestamp hoặc bộ đếm không được đồng bộ. Không bỏ qua authentication tag khi giải mã. Dữ liệu giải mã chỉ được chấp nhận khi kiểm tra xác thực thành công.

Metadata không phải secret nhưng cần bảo vệ tính toàn vẹn. Gắn ciphertext với ngữ cảnh bằng associated data (AAD) nếu phù hợp, ví dụ tenant ID, secret ID, loại dữ liệu và phiên bản schema. Điều này giúp ngăn tráo ciphertext giữa các bản ghi hoặc tenant.

### 5.4. Bảo vệ bản sao lưu

Bản sao lưu thường chứa secret cũ, phiên bản secret đã thu hồi và khóa bọc dữ liệu. Cần:

- Mã hóa bản sao lưu và bảo vệ khóa giải mã độc lập.
- Giới hạn người có thể tạo, tải xuống, khôi phục hoặc xóa bản sao.
- Dùng bản sao bất biến hoặc kiểm soát chống sửa/xóa trái phép.
- Ghi log thao tác restore và kiểm tra tính toàn vẹn.
- Xác định chính sách retention và cách xóa an toàn theo yêu cầu.
- Đánh giá liệu secret đã thu hồi có thể bị phục hồi lại từ backup hay không.

Sau restore, không tự động kích hoạt lại secret cũ. Cần đối chiếu trạng thái thu hồi, phiên bản và thời điểm hết hạn từ nguồn có thẩm quyền.

## 6. Cấp quyền và phân phối secret

Secret chỉ nên được cung cấp cho workload hoặc người vận hành có nhu cầu thực sự. Quyền đọc secret và quyền sử dụng secret là hai quyền khác nhau. Ví dụ, một dịch vụ có thể cần gọi thao tác ký trong HSM nhưng không cần đọc khóa riêng.

### 6.1. Danh tính workload thay cho credential dùng chung

Ưu tiên xác thực workload bằng danh tính ngắn hạn hoặc cơ chế federation phù hợp với nền tảng. Ví dụ, CI/CD có thể dùng OIDC federation để nhận quyền tạm thời từ cloud provider thay vì giữ access key dài hạn trong repository secret.

Một quy trình phân phối tốt thường gồm:

1. Workload chứng minh danh tính bằng cơ chế của nền tảng.
2. Secret manager xác minh danh tính, môi trường và thuộc tính workload.
3. Policy xác định secret cụ thể mà workload được phép nhận.
4. Secret được cấp với thời hạn và phạm vi phù hợp.
5. Mọi lần đọc hoặc sử dụng được ghi audit mà không ghi giá trị secret.
6. Khi workload bị xóa, đổi danh tính hoặc bị nghi ngờ xâm nhập, quyền cấp secret được thu hồi.

### 6.2. Quyền tối thiểu và tách nhiệm vụ

Không dùng một tài khoản quản trị có quyền đọc, ghi, xóa và cấp mọi secret cho tất cả ứng dụng. Tách các vai trò như:

- Người sở hữu nghiệp vụ phê duyệt mục đích và phạm vi.
- Nhóm vận hành quản lý cấu hình và vòng đời.
- Dịch vụ chạy chỉ đọc hoặc sử dụng secret cụ thể.
- Nhóm bảo mật giám sát, điều tra và phê duyệt ngoại lệ.
- Quản trị KMS/HSM quản lý khóa gốc theo kiểm soát riêng.

Với khóa ký có ảnh hưởng rộng, cân nhắc phê duyệt nhiều bên (dual control hoặc quorum) cho thao tác nhạy cảm như kích hoạt, xuất, khôi phục hoặc thu hồi.

### 6.3. Secret trong biến môi trường, file và container

Biến môi trường tiện cho ứng dụng nhưng có thể xuất hiện trong thông tin chẩn đoán, process inspection, crash dump hoặc công cụ quản trị. File secret có thể an toàn nếu quyền truy cập, quyền mount, vòng đời và xóa được kiểm soát. Secret volume hoặc agent có thể giảm việc ghi vào image, nhưng vẫn cần bảo vệ quyền đọc trong runtime.

Khi đánh giá, hãy hỏi:

- Secret có được bake vào image hoặc layer của container không?
- Secret có xuất hiện trong build argument, command line hoặc process list không?
- Volume có được mount cho mọi container trong pod không cần thiết không?
- File có quyền truy cập quá rộng hoặc tồn tại trên disk lâu hơn cần thiết không?
- Debug endpoint, shell access hoặc crash dump có thể đọc secret không?
- Workload khác cùng node có thể truy cập file hoặc memory không?
- Khi pod/container bị thay thế, secret cũ có còn trong cache hoặc volume không?

Không có một cơ chế phân phối nào tự động an toàn. Chọn dựa trên mô hình đe dọa của nền tảng và xác minh bằng quyền thực tế.

## 7. Sử dụng secret đúng phạm vi

Secret tốt vẫn có thể bị lạm dụng nếu hệ thống cho phép dùng ở quá nhiều nơi hoặc trong thời gian quá dài.

### 7.1. Giới hạn quyền và thời hạn

- Cấp quyền tối thiểu cần thiết cho từng secret.
- Phân tách production, staging, development và sandbox.
- Phân tách tenant hoặc khách hàng nếu ranh giới yêu cầu.
- Dùng access token ngắn hạn và refresh token có rotation/reuse detection khi phù hợp.
- Hạn chế scope, audience và loại thao tác mà secret cho phép.
- Áp dụng quota, rate limit và phát hiện hành vi bất thường.
- Không dùng một API key toàn quyền cho mọi tích hợp.
- Thu hồi quyền khi workload, nhân viên hoặc đối tác không còn nhu cầu.

### 7.2. Không đưa secret vào phía client

Ứng dụng web chạy trong trình duyệt và ứng dụng mobile được phân phối đến thiết bị người dùng không thể giữ một secret chung ở trạng thái bí mật trước chủ sở hữu thiết bị hoặc người có khả năng phân tích ứng dụng. Obfuscation, mã hóa trong binary hoặc đặt secret trong JavaScript bundle không tạo ra ranh giới bí mật đáng tin cậy.

Với OAuth/OIDC:

- Public client như SPA hoặc ứng dụng native không thể dựa vào client secret nhúng trong app để chứng minh danh tính client.
- Dùng Authorization Code Flow với PKCE cho public client theo hướng dẫn giao thức.
- Confidential client chạy phía máy chủ mới có thể giữ credential riêng trong môi trường được kiểm soát.
- Cân nhắc private_key_jwt hoặc mTLS cho xác thực client nếu hệ sinh thái hỗ trợ và vận hành được.
- Không đặt access token, refresh token hoặc mã khôi phục trong URL.
- Dùng redirect URI chính xác và kiểm tra state/nonce theo giao thức.

Nếu một secret phải được phân phối đến mọi bản cài đặt, hãy xem nó là dữ liệu công khai và thiết kế xác thực dựa trên cơ chế khác.

### 7.3. Bearer secret và token

Bearer token có đặc tính: chủ thể sở hữu token có thể sử dụng token trong phạm vi hiệu lực. Vì vậy:

- Không ghi token vào log hoặc telemetry.
- Không truyền qua URL hoặc referrer.
- Giới hạn audience và scope.
- Dùng thời hạn ngắn phù hợp với hành trình.
- Bảo vệ refresh token bằng rotation, phát hiện tái sử dụng và thu hồi theo thiết kế.
- Xem xét sender-constrained token hoặc mTLS/DPoP khi phù hợp.
- Thu hồi token hoặc phiên khi phát hiện rò rỉ, mất thiết bị hoặc thay đổi bảo mật quan trọng.

JWT ký số không tự động được mã hóa. Claim trong JWS thường có thể đọc bởi người sở hữu token. Không đưa mật khẩu, seed MFA, secret nội bộ hoặc dữ liệu nhạy cảm không cần thiết vào payload.

### 7.4. Không tái sử dụng secret giữa các giao thức

Một secret dùng để ký webhook không nên đồng thời dùng làm khóa ký JWT, khóa mã hóa dữ liệu hoặc mật khẩu tài khoản. Việc dùng chung làm tăng phạm vi ảnh hưởng và khiến xoay vòng phức tạp.

Dùng khóa độc lập theo mục đích và thuật toán. Nếu cần dẫn xuất nhiều khóa từ một khóa gốc, dùng KDF chuẩn với context/label rõ ràng và quản lý khóa gốc trong ranh giới bảo vệ.

## 8. Vòng đời secret: tạo, cấp phát, xoay vòng và thu hồi

Một secret không có chủ sở hữu, ngày hết hạn hoặc quy trình thu hồi là một rủi ro tồn đọng. Secret review cần đánh giá toàn bộ vòng đời.

### 8.1. Tạo và đăng ký

Khi tạo secret, hệ thống nên ghi nhận:

- Secret ID hoặc key ID.
- Loại secret, chủ sở hữu, mục đích và workload được phép dùng.
- Môi trường, tenant và phạm vi quyền.
- Thuật toán hoặc phiên bản khóa nếu có.
- Thời điểm tạo, thời hạn, lịch xoay vòng và trạng thái.
- Cách cấp phát và nơi lưu verifier/ciphertext.
- Quy trình thu hồi và liên hệ chịu trách nhiệm.

Không ghi giá trị secret vào metadata hoặc audit event.

### 8.2. Phân phối và tiếp nhận

Người nhận chỉ nên thấy secret khi thực sự cần. Với API key hoặc mã khôi phục, hiển thị một lần và yêu cầu lưu trong password manager hoặc secret store được phê duyệt. Với service secret, cấp trực tiếp cho workload qua danh tính được xác thực. Tránh gửi secret trong email, chat, issue tracker hoặc file đính kèm không có bảo vệ phù hợp.

### 8.3. Xoay vòng (rotation)

Rotation thay thế secret cũ bằng secret mới theo quy trình kiểm soát. Một luồng xoay vòng điển hình:

1. Tạo secret mới và đăng ký phiên bản mới.
2. Cấp secret mới cho workload được phép.
3. Cập nhật consumer và xác nhận hoạt động bằng secret mới.
4. Theo dõi để phát hiện consumer còn dùng secret cũ.
5. Thu hồi secret cũ sau thời gian chuyển tiếp đã định.
6. Kiểm tra không còn bản sao hoặc dependency đang dùng phiên bản cũ.
7. Ghi nhận kết quả và cập nhật lịch xoay vòng.

Không phải loại secret nào cũng có thể tồn tại song song. Với khóa ký token, có thể cần công bố public key mới trước, ký bằng khóa mới và giữ public key cũ trong thời gian token cũ còn hiệu lực. Với mật khẩu người dùng, quy trình đổi mật khẩu khác với xoay API key tự động. Với seed TOTP, thay seed cần một quy trình đăng ký authenticator mới và thu hồi seed cũ.

### 8.4. Thu hồi khẩn cấp

Khi secret bị nghi ngờ lộ:

- Xem secret là đã bị xâm phạm cho đến khi chứng minh ngược lại.
- Thu hồi hoặc vô hiệu hóa secret qua nguồn có thẩm quyền.
- Xoay hoặc tạo secret thay thế từ nguồn tin cậy.
- Thu hồi token, phiên hoặc credential phát sinh từ secret nếu cần.
- Kiểm tra log sử dụng, IP/thiết bị, scope và tài nguyên bị truy cập.
- Xác định thời điểm lộ, thời điểm sử dụng cuối và phạm vi ảnh hưởng.
- Thông báo cho các chủ thể chịu trách nhiệm theo quy trình sự cố.
- Lưu bằng chứng mà không sao chép giá trị secret vào báo cáo.
- Kiểm tra secret có còn trong cache, bản sao lưu, artifact, image hoặc lịch sử repository hay không.

Chỉ xóa file chứa secret khỏi nhánh hiện tại không đủ xử lý sự cố. Secret có thể còn trong Git history, fork, cache, artifact, log và bản sao của người dùng. Điều quan trọng là thu hồi giá trị đã lộ và xác minh mọi consumer đã chuyển sang giá trị mới.

### 8.5. Hết hạn và hủy an toàn

Khi secret không còn cần thiết, thu hồi quyền, xóa bản lưu theo chính sách, hủy hoặc vô hiệu hóa khóa liên quan và xác nhận các bản sao lưu được xử lý theo retention. Với khóa trong HSM/KMS, dùng thao tác disable/destroy theo quy trình của nền tảng; cần hiểu rằng việc hủy khóa có thể làm dữ liệu đã mã hóa không thể khôi phục.

Không xóa khóa giải mã trước khi xác nhận dữ liệu, backup và nghĩa vụ lưu trữ đã được xử lý. Không giữ khóa vô thời hạn chỉ vì chưa biết ai đang dùng; cần xác định owner và dependency để đóng vòng đời có kiểm soát.

## 9. Các điểm rò rỉ thường gặp

Secret thường bị lộ ở nơi không được xem là kho secret. Review cần kiểm tra toàn bộ đường đi của dữ liệu.

| Vị trí | Cách rò rỉ | Kiểm soát cần xem xét |
|---|---|---|
| Git repository | Commit file `.env`, private key, token hoặc cấu hình | Secret scanning, pre-commit, CI scan, thu hồi ngay khi phát hiện |
| CI/CD | Log command, build argument, artifact, cache | Masking, OIDC federation, quyền pipeline tối thiểu, artifact hygiene |
| Container image | Secret nằm trong layer hoặc history | Build không nhận secret qua layer, mount lúc runtime |
| Log ứng dụng | In header Authorization, cookie, exception hoặc request body | Redaction tại nguồn, allowlist field, kiểm thử log |
| APM/tracing | Ghi URL, header, span attribute hoặc payload | Scrub dữ liệu nhạy cảm và giới hạn quyền truy cập |
| Browser/mobile | Secret trong bundle, source map, binary hoặc local storage | Không nhúng secret chung; dùng flow dành cho public client |
| Crash dump | Memory có token, key hoặc password | Hạn chế dump, kiểm soát truy cập, retention và xử lý sau sự cố |
| Ticket/chat/email | Nhân viên dán secret để nhờ hỗ trợ | Hướng dẫn không chia sẻ, công cụ gửi secret có thời hạn |
| Backup/export | Bản sao có secret cũ hoặc khóa bọc | Mã hóa, quyền riêng, retention, kiểm tra restore |
| Metrics/analytics | Secret vô tình trở thành label hoặc event property | Không đưa secret vào label, lọc trước khi gửi |
| Shell/process list | Secret nằm trong argument hoặc history | Tránh truyền secret qua command line, bảo vệ shell history |
| Test fixture | Credential production được dùng trong test | Dữ liệu giả, secret riêng theo môi trường, tự động thu hồi |

### 9.1. Log và telemetry

Không ghi password, seed MFA, API key, OAuth client secret, access/refresh token, session cookie, private key hoặc mã khôi phục. Nếu cần điều tra, ghi metadata an toàn như secret ID, actor ID, action, result, timestamp, source và correlation ID.

Redaction phải được thực hiện càng gần nguồn dữ liệu càng tốt. Chỉ dựa vào bộ lọc ở hệ thống log cuối có thể bỏ sót bản sao trong message queue, agent hoặc trace exporter. Dùng allowlist các trường được phép ghi thay vì ghi toàn bộ object rồi cố xóa trường nhạy cảm.

Cần kiểm thử cả đường lỗi. Exception, retry log, debug mode và audit event thường chứa dữ liệu mà log bình thường đã che.

### 9.2. Repository và lịch sử commit

Secret scanner có thể phát hiện mẫu phổ biến nhưng không chứng minh repository không có secret. Kết hợp scanner với quy tắc review, quyền ghi, branch protection và kiểm tra lịch sử khi cần. Khi scanner phát hiện một secret thật:

1. Xác minh loại secret và owner mà không phát tán giá trị.
2. Thu hồi hoặc xoay secret ngay.
3. Kiểm tra log và hoạt động sử dụng.
4. Xác định artifact, fork, cache và người đã truy cập.
5. Dọn dữ liệu khỏi nơi lưu trữ theo quy trình, nhưng không coi việc rewrite history là biện pháp thay thế thu hồi.
6. Bổ sung kiểm soát để ngăn tái diễn.

### 9.3. Pipeline và artifact

Pipeline thường có quyền cao và có thể truy cập nhiều môi trường. Review cần kiểm tra quyền của người có thể sửa pipeline, dependency, runner và workflow. Một pull request không đáng tin cậy không được phép đọc secret production chỉ vì pipeline có quyền đó.

Không đưa secret vào Docker build argument hoặc image layer. Không in toàn bộ environment khi debug. Không dùng artifact chứa `.env`, keystore hoặc file cấu hình thật. Cân nhắc ephemeral runner, short-lived credential và tách pipeline build khỏi pipeline deploy production.

## 10. Bảo vệ secret trong runtime

Secret có thể bị lộ sau khi đã được cấp hợp lệ. Khi ứng dụng đang chạy, giá trị có thể xuất hiện trong heap, native memory, file tạm, swap, crash dump hoặc công cụ debug.

Các câu hỏi cần đặt ra:

- Secret được nạp khi khởi động hay lấy theo nhu cầu?
- Giá trị tồn tại trong memory bao lâu?
- Có cache không? Cache có thời hạn và cơ chế xóa không?
- Secret có bị copy qua nhiều object hoặc thread không?
- Có endpoint debug/actuator cho phép dump cấu hình không?
- Ai có thể attach debugger hoặc đọc process memory?
- Crash dump được lưu ở đâu, ai có thể tải và khi nào bị xóa?
- Khi workload dừng, secret có bị lưu trong volume hoặc file tạm không?
- Secret có bị serialize vào session, queue hoặc retry payload không?

Nên giảm số lần copy, giới hạn thời gian tồn tại, không đưa secret vào exception và tránh giữ giá trị trong object sống lâu hơn cần thiết. Việc xóa memory trong runtime managed như JVM có thể không bảo đảm xóa mọi bản sao do garbage collection, string immutability và tối ưu hóa runtime. Vì vậy, kiểm soát quyền truy cập process, hạn chế dump và giảm thời gian tồn tại thường quan trọng hơn tuyên bố rằng ứng dụng đã “zeroize” hoàn toàn.

## 11. Quản trị khóa và thuật toán

Secret review phải xem cả thuật toán, cách sử dụng và quyền thao tác khóa. Một thuật toán mạnh vẫn có thể thất bại nếu nonce bị dùng lại, khóa bị lộ hoặc policy cho phép workload không phù hợp thực hiện decrypt.

### 11.1. Phân tách khóa theo mục đích

Dùng khóa khác nhau cho:

- Ký token và assertion.
- Mã hóa dữ liệu và backup.
- Xác thực webhook.
- Xác thực client hoặc workload.
- Dẫn xuất key theo từng tenant hoặc ứng dụng.

Không tái sử dụng khóa giữa môi trường production và non-production. Gắn metadata về thuật toán, key ID, mục đích, chủ sở hữu, thời hạn và trạng thái. Bên xác minh phải có cách nhận biết key ID và từ chối thuật toán ngoài allowlist.

### 11.2. Quản lý khóa ký token

Với JWT hoặc assertion:

- Khóa riêng ký phải nằm trong ranh giới bảo vệ thích hợp.
- Bên xác minh dùng public key lấy từ nguồn tin cậy.
- Kiểm tra `alg` theo cấu hình cho phép; không tin thuật toán do token tự khai báo.
- Xác minh `iss`, `aud`, `exp`, `nbf` và claim cần thiết.
- Có quy trình phát hành, công bố, xoay vòng và thu hồi khóa.
- Không để public key cũ bị loại trước khi token hợp lệ hết hạn nếu thiết kế cần xác minh token cũ.
- Nếu khóa riêng bị lộ, thu hồi khóa, phát hành khóa mới và xử lý token đã ký bằng khóa cũ.

Không đưa private key vào JWKS. JWKS công khai chỉ chứa public key và metadata công khai cần thiết.

### 11.3. Khóa mã hóa và quyền decrypt

Quyền decrypt thường nhạy cảm hơn quyền đọc ciphertext. Một ứng dụng có thể không cần quyền quản lý KEK nhưng vẫn cần quyền yêu cầu giải mã một loại dữ liệu. Cần giới hạn theo resource, context, tenant và mục đích.

Dùng audit log cho thao tác encrypt/decrypt, rotate, disable và destroy. Cảnh báo khi một workload đọc lượng secret bất thường, truy cập ngoài thời gian hoặc gọi KMS từ vị trí không mong đợi.

### 11.4. Xoay vòng khóa và tương thích dữ liệu

Xoay KEK có thể chỉ cần bọc lại DEK mà không phải mã hóa lại toàn bộ dữ liệu, tùy kiến trúc. Xoay DEK hoặc khóa dữ liệu có thể yêu cầu mã hóa lại dữ liệu. Phải lập kế hoạch cho dữ liệu đang hoạt động, bản sao lưu, cache và consumer chưa nâng cấp.

Không xóa key version cũ trước khi xác nhận dữ liệu cần giải mã đã được chuyển hoặc không còn cần thiết. Ngược lại, không giữ key version đã bị xâm phạm hoạt động chỉ để duy trì tương thích.

## 12. Quy trình thực hiện một secret review

Một cuộc review có thể được thực hiện theo các bước sau.

### Bước 1: Xác định phạm vi

Ghi rõ ứng dụng, môi trường, tenant, hành trình xác thực và loại secret cần xem xét. Bao gồm cả hệ thống bên ngoài như IdP, KMS, CI/CD, log platform và nhà cung cấp MFA nếu có liên quan.

### Bước 2: Thu thập sơ đồ và danh mục

Yêu cầu sơ đồ luồng secret, danh sách secret ID, owner, workload consumer, quyền truy cập, nơi lưu, thời hạn và cách xoay vòng. Không yêu cầu gửi giá trị thật của secret cho người review.

### Bước 3: Kiểm tra thiết kế lưu trữ

Xác định loại dữ liệu có cần khôi phục hay chỉ cần xác minh. Kiểm tra password hashing, mã hóa AEAD, quản lý nonce, KMS/HSM, tách khóa, quyền decrypt và backup.

### Bước 4: Kiểm tra quyền và đường phân phối

Đánh giá workload identity, IAM policy, quyền của operator, CI/CD, secret manager, container và môi trường phát triển. Kiểm tra xem một workload có thể lấy secret của workload khác không.

### Bước 5: Kiểm tra cách sử dụng

Xác định secret có bị nhúng ở client, dùng sai audience/scope, chia sẻ giữa môi trường hoặc tồn tại lâu hơn cần thiết không. Kiểm tra token bearer, client authentication và các luồng ký/xác minh.

### Bước 6: Kiểm tra điểm rò rỉ

Dùng secret scanner và kiểm tra cấu hình log, trace, crash dump, repository, artifact, ticket, backup và test fixture. Không sao chép secret tìm được vào báo cáo.

### Bước 7: Kiểm tra vòng đời

Xác minh owner, expiry, rotation, revocation, break-glass, quy trình xử lý lộ lọt và việc dọn các bản sao cũ. Thử diễn tập xoay vòng hoặc thu hồi trong môi trường an toàn.

### Bước 8: Ghi nhận phát hiện và xác minh khắc phục

Mỗi phát hiện cần có bằng chứng đã che secret, tài sản bị ảnh hưởng, đường khai thác, hậu quả, mức độ nghiêm trọng, owner và thời hạn xử lý. Sau khi sửa, kiểm tra lại bằng hành vi thực tế và log kiểm toán.

## 13. Ví dụ review một confidential client

Giả sử một backend gọi authorization server để lấy token truy cập API. Backend là confidential client và có client secret.

### 13.1. Thiết kế có vấn đề

~~~yaml
oauth:
  client_id: workforce-api
  client_secret: "REAL_SECRET_VALUE"
~~~

Nếu file này được commit vào repository, secret có thể tồn tại trong lịch sử Git, fork, CI cache và artifact. Nếu cùng giá trị được dùng ở staging và production, một sự cố ở staging có thể ảnh hưởng production. Nếu backend ghi toàn bộ cấu hình khi khởi động, secret còn có thể đi vào log.

### 13.2. Thiết kế được cải thiện

~~~yaml
oauth:
  issuer: "https://identity.example.invalid"
  client_id: "workforce-api"
  client_secret_ref: "secret://production/workforce-api/oauth-client"
~~~

Backend lấy secret qua danh tính workload và policy chỉ cho phép đọc đúng secret trong môi trường production. Secret manager ghi audit event cho thao tác đọc nhưng không ghi giá trị. Secret có owner, thời hạn và quy trình rotation. CI/CD dùng danh tính federation ngắn hạn để deploy và không cần lưu một cloud access key dài hạn.

Nếu authorization server hỗ trợ, tổ chức có thể đánh giá private_key_jwt hoặc mTLS để xác thực confidential client. Khóa riêng cần được bảo vệ trong KMS/HSM hoặc môi trường phù hợp; public key được đăng ký theo quy trình có kiểm soát.

### 13.3. Kế hoạch xử lý khi secret bị lộ

Nếu phát hiện secret trong commit:

1. Xác định client ID và secret ID liên quan mà không dán giá trị vào ticket.
2. Thu hồi hoặc thay thế client secret tại authorization server.
3. Cấp secret mới và cập nhật secret manager.
4. Triển khai backend, xác minh token mới được cấp đúng.
5. Thu hồi token hoặc grant có thể bị ảnh hưởng theo khả năng của hệ thống.
6. Kiểm tra audit log, token issuance và API access trong khoảng thời gian nghi ngờ.
7. Kiểm tra log, artifact, fork và cache; xử lý các bản sao theo quy trình.
8. Bổ sung scanner, rule review và quyền CI/CD để ngăn tái diễn.

Không được xem việc xóa dòng khỏi commit mới là hoàn tất. Secret đã xuất hiện trong repository phải được coi là có khả năng đã bị sao chép.

## 14. Kiểm thử kiểm soát secret

Một thiết kế chỉ có giá trị khi có thể kiểm chứng. Có thể xây dựng các nhóm kiểm thử sau:

| Nhóm kiểm thử | Tình huống | Kết quả mong đợi |
|---|---|---|
| Quyền truy cập | Workload A yêu cầu secret của workload B | Bị từ chối và có audit event |
| Môi trường | Workload staging yêu cầu secret production | Bị từ chối |
| Secret hết hạn | Workload sử dụng secret đã hết hạn | Bị từ chối hoặc yêu cầu cấp mới theo policy |
| Thu hồi | Secret bị thu hồi nhưng consumer vẫn giữ cache | Consumer ngừng chấp nhận trong giới hạn đã định |
| Rotation | Hai phiên bản tồn tại trong thời gian chuyển tiếp | Consumer chuyển sang phiên bản mới, phiên bản cũ bị thu hồi đúng lúc |
| Logging | Gửi request lỗi có Authorization header | Log không chứa token hoặc secret |
| CI/CD | Pipeline từ pull request không tin cậy yêu cầu secret production | Không được cấp secret |
| Container | Quét image và layer sau build | Không tìm thấy secret triển khai |
| Backup | Khôi phục bản sao có secret đã thu hồi | Secret cũ không được kích hoạt lại |
| KMS/HSM | Workload ngoài policy yêu cầu decrypt/sign | Thao tác bị từ chối và ghi audit |
| Phát hiện lộ | Scanner tìm thấy secret giả lập trong repository test | Pipeline cảnh báo hoặc chặn theo policy |
| Khôi phục sự cố | Secret bị nghi ngờ lộ và cần xoay khẩn cấp | Có thể thu hồi, thay thế và xác minh consumer |

Kiểm thử không nên dùng secret production thật. Tạo fixture riêng, có thời hạn, scope nhỏ và quy trình tự động dọn dẹp. Với kiểm thử quyền, xác minh cả trường hợp được phép lẫn bị từ chối; một hệ thống chỉ kiểm tra happy path sẽ bỏ sót lỗi phân quyền.

## 15. Đánh giá phát hiện và mức độ nghiêm trọng

Mức độ phát hiện nên dựa trên khả năng khai thác, phạm vi quyền, thời hạn, mức độ phơi lộ và tác động nghiệp vụ.

| Mức độ | Ví dụ | Hành động gợi ý |
|---|---|---|
| Critical | Khóa riêng ký token production bị lộ; secret quản trị toàn hệ thống có thể truy cập công khai | Thu hồi/disable ngay, xử lý sự cố, đánh giá token và dữ liệu bị ảnh hưởng |
| High | Client secret production dùng chung nhiều môi trường; workload không liên quan đọc được seed MFA | Hạn chế quyền, xoay secret, kiểm tra truy cập và mở rộng phạm vi điều tra |
| Medium | Secret có thời hạn dài, rotation thủ công khó kiểm soát hoặc log có thể lộ một phần token | Lập kế hoạch khắc phục có hạn, giảm scope và bổ sung kiểm thử |
| Low | Metadata hoặc quy trình quản lý thiếu owner nhưng chưa có đường truy cập trái phép | Bổ sung owner, inventory, expiry và quy trình kiểm soát |

Đây là khung tham khảo. Tổ chức cần dùng thang mức độ và SLA phản ứng phù hợp với quy trình quản trị rủi ro của mình. Một secret có quyền nhỏ nhưng tồn tại trên hàng nghìn thiết bị có thể có phạm vi ảnh hưởng lớn; một secret có quyền cao nhưng được bảo vệ trong HSM và có kiểm soát chặt vẫn cần đánh giá theo threat model cụ thể.

### 15.1. Nội dung một finding tốt

Một finding cần có:

- Tiêu đề mô tả vấn đề và tài sản.
- Mô tả ngắn đường khai thác.
- Bằng chứng đã che hoặc thay thế giá trị secret.
- Chủ thể có thể khai thác và điều kiện cần có.
- Hậu quả đối với xác thực, token, phiên hoặc dữ liệu.
- Phạm vi ảnh hưởng và mức độ nghiêm trọng.
- Biện pháp khắc phục ưu tiên và biện pháp giảm thiểu tạm thời.
- Người chịu trách nhiệm và thời hạn xử lý.
- Kết quả xác minh sau khắc phục.

Không đưa giá trị secret, token còn hiệu lực hoặc thông tin cho phép tái tạo secret vào finding. Bằng chứng phải đủ để tái hiện vấn đề trong môi trường kiểm soát mà không tạo thêm bản sao secret.

## 16. Tình huống thực tế: API key bị lộ qua log

Một dịch vụ xác thực gọi hệ thống kiểm tra rủi ro bằng API key. Khi nhà cung cấp trả về HTTP 500, middleware ghi toàn bộ request headers vào log để debug. Header `Authorization` chứa API key. Log được gửi đến nền tảng quan sát mà nhiều nhóm kỹ thuật có quyền đọc.

Phân tích:

1. Secret được cấp đúng và lưu đúng trong secret manager, nhưng bị lộ ở bước sử dụng.
2. Phạm vi người có thể đọc log rộng hơn phạm vi được phép sử dụng API key.
3. Việc lỗi 500 kích hoạt logging làm đường rò rỉ chỉ xuất hiện trong tình huống bất thường.
4. API key có thể tiếp tục hoạt động sau khi log bị lộ nếu không có expiry hoặc rotation.
5. Không thể kết luận key chưa bị lạm dụng chỉ vì chưa có cảnh báo.

Cách xử lý:

- Thu hồi hoặc xoay API key và xác minh dịch vụ dùng key mới.
- Kiểm tra audit log của nhà cung cấp và log truy cập nội bộ trong khoảng thời gian nghi ngờ.
- Giới hạn quyền truy cập log, retention và khả năng export.
- Sửa middleware theo allowlist, luôn loại bỏ Authorization và cookie.
- Kiểm thử cả đường lỗi và retry.
- Thêm secret scanning hoặc rule phát hiện token trong log.
- Ghi nhận finding và kiểm tra các dịch vụ khác dùng cùng middleware.

Bài học là secret review phải kiểm tra đường đi end-to-end, bao gồm cả lỗi, retry và hệ thống quan sát. Bảo vệ kho lưu trữ mà bỏ qua log không đủ để giữ secret.

## 17. Checklist secret review

Trước khi chấp thuận một thiết kế xác thực, hãy kiểm tra:

- [ ] Đã lập danh mục secret theo loại, owner, môi trường, tenant và workload.
- [ ] Đã xác định secret nào cần so khớp, secret nào cần khôi phục và secret nào nên giữ trong HSM/KMS.
- [ ] Mật khẩu được lưu bằng password hashing chuyên dụng với salt riêng; không lưu bản có thể giải mã.
- [ ] API key và mã khôi phục ngẫu nhiên chỉ lưu verifier khi không cần khôi phục giá trị gốc.
- [ ] Seed TOTP và secret cần khôi phục được mã hóa có xác thực, khóa bảo vệ tách biệt.
- [ ] Khóa riêng ký token và TLS được bảo vệ trong ranh giới phù hợp, có kiểm soát sử dụng và thu hồi.
- [ ] Secret được tạo bằng CSPRNG, có entropy phù hợp và không dùng lại giữa môi trường.
- [ ] Public client không chứa client secret hoặc khóa chung trong browser/mobile bundle.
- [ ] Workload dùng danh tính riêng và chỉ nhận secret đúng phạm vi cần thiết.
- [ ] Quyền đọc, sử dụng, xoay vòng, quản trị và hủy secret được phân tách phù hợp.
- [ ] Secret không xuất hiện trong repository, image, build artifact, command line hoặc shell history.
- [ ] Log, trace, metric, exception và crash dump không chứa secret hoặc bearer token.
- [ ] Có expiry, rotation, revoke, owner và quy trình xử lý khi lộ lọt.
- [ ] Backup được mã hóa, quyền độc lập và restore không kích hoạt lại secret đã thu hồi.
- [ ] Có audit log cho thao tác đọc, ký, giải mã, xoay vòng và thu hồi.
- [ ] Có kiểm thử quyền cho phép/từ chối, rotation, revoke, log redaction và CI/CD.
- [ ] Finding không chứa giá trị secret; có owner, mức độ và kết quả xác minh.

## 18. Câu hỏi tự kiểm tra

**1. Vì sao mật khẩu người dùng thường nên được lưu bằng password hashing thay vì mã hóa có thể giải mã?**

Vì hệ thống chỉ cần xác minh mật khẩu người dùng nhập, không cần lấy lại mật khẩu gốc. Password hashing chuyên dụng làm tăng chi phí dò đoán ngoại tuyến nếu cơ sở dữ liệu bị lộ.

**2. Vì sao seed TOTP cần được bảo vệ khác với password verifier?**

Máy chủ cần dùng seed để tính mã TOTP, nên phải có khả năng khôi phục giá trị gốc. Do đó cần mã hóa có xác thực và kiểm soát quyền giải mã.

**3. Một API key ngẫu nhiên chỉ dùng để xác minh có nhất thiết phải lưu bản rõ không?**

Không. Có thể lưu verifier/hash của phần secret ngẫu nhiên và chỉ hiển thị giá trị đầy đủ khi tạo.

**4. Vì sao không thể giữ client secret trong ứng dụng mobile?**

Ứng dụng được phân phối đến thiết bị người dùng; người kiểm soát thiết bị có thể phân tích binary, memory hoặc cấu hình. Secret chung nhúng trong ứng dụng không thể được giữ bí mật đáng tin cậy.

**5. Nếu secret đã bị commit lên Git nhưng sau đó bị xóa khỏi file, sự cố đã được xử lý chưa?**

Chưa. Secret có thể còn trong history, fork, cache, artifact và bản sao của người khác. Cần thu hồi/rotation, điều tra việc sử dụng và xử lý các bản sao theo quy trình.

**6. Vì sao cần phân biệt quyền đọc secret với quyền sử dụng secret?**

Một workload có thể cần thực hiện ký hoặc giải mã mà không cần nhìn thấy khóa riêng. Giới hạn thao tác giúp giảm nguy cơ secret bị trích xuất.

**7. Rotation khác revocation như thế nào?**

Rotation thay thế secret cũ bằng secret mới theo một quy trình chuyển tiếp. Revocation vô hiệu hóa quyền sử dụng secret. Khi secret bị lộ, cần thu hồi khẩn cấp và cấp giá trị thay thế nếu dịch vụ vẫn cần hoạt động.

**8. Vì sao secret scanner không thể chứng minh hệ thống không có secret bị lộ?**

Scanner chỉ phát hiện các mẫu và nguồn dữ liệu mà nó có thể kiểm tra. Secret có thể bị che, mã hóa, nằm trong log, artifact, thiết bị hoặc hệ thống bên ngoài.

**9. Khi khôi phục backup, vì sao không nên tự động kích hoạt lại mọi secret có trong bản sao?**

Bản sao có thể chứa secret đã bị thu hồi hoặc phiên bản cũ. Cần đối chiếu trạng thái hiện hành và chỉ kích hoạt secret được phê duyệt.

**10. Điều kiện nào chứng minh một secret review đã hoàn tất?**

Danh mục, luồng dữ liệu, quyền truy cập, lưu trữ, phân phối, vòng đời, điểm rò rỉ và kiểm thử đã được đánh giá; phát hiện có bằng chứng an toàn, owner và kế hoạch xử lý; các biện pháp quan trọng đã được xác minh.

## 19. Kết luận

Secret review phải theo dõi secret trong toàn bộ vòng đời và mọi ranh giới mà nó đi qua. Mỗi loại secret cần cách bảo vệ phù hợp với mục đích: mật khẩu cần password hashing, secret ngẫu nhiên chỉ dùng để xác minh có thể lưu verifier, secret cần khôi phục phải được mã hóa có xác thực, còn khóa riêng quan trọng nên được giữ trong HSM/KMS hoặc ranh giới bảo vệ tương đương.

Một thiết kế tốt giới hạn quyền theo workload, môi trường và mục đích; không nhúng secret vào client; tránh rò rỉ qua repository, pipeline, log và runtime; có rotation, revocation và audit; đồng thời kiểm thử cả trường hợp được phép lẫn bị từ chối. Khi phát hiện secret bị lộ, cần xem nó là đã bị xâm phạm, thu hồi hoặc thay thế, điều tra việc sử dụng và xử lý các bản sao. Chỉ khi tổ chức kiểm soát được nơi secret tồn tại, ai có thể dùng nó và cách vô hiệu hóa nó thì ranh giới xác thực mới có thể được tin cậy.

