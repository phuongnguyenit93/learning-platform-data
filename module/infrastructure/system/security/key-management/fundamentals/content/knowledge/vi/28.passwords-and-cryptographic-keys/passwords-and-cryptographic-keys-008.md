# Credential rotation

Credential rotation là quá trình thay một credential đang được sử dụng bằng credential mới, chuyển các thành phần phụ thuộc sang credential mới, xác nhận hoạt động ổn định rồi vô hiệu hóa credential cũ theo chính sách. Credential có thể là mật khẩu người dùng, API key, mật khẩu database, secret của service account, private key ký số, khóa mã hóa hoặc chứng thư số.

Rotation là một thay đổi có ảnh hưởng trực tiếp đến khả năng xác thực và truy cập. Nếu thay secret ở nơi cấp phát nhưng chưa cập nhật tất cả consumer, hệ thống có thể mất kết nối. Nếu giữ credential cũ quá lâu, credential bị lộ vẫn có thể được sử dụng. Vì vậy, một quy trình rotation cần quản lý đồng thời danh tính, quyền, phiên bản secret, thời gian chồng lấn, cutover, thu hồi và bằng chứng kiểm tra.

Bài học trình bày cách thiết kế rotation cho cả người dùng và workload, phân biệt rotation với renewal, rekey, rewrap và password hashing upgrade, đồng thời đưa ra quy trình triển khai có thể kiểm soát trong hệ thống Java và môi trường KMS/secret manager.

## 1. Mục tiêu và phạm vi

Sau bài học, người đọc cần có khả năng:

- Phân biệt credential, secret, key material, identity, token và certificate.
- Giải thích mục đích của rotation và các tình huống cần thực hiện sớm.
- Xây dựng chính sách rotation theo loại credential, mức độ nhạy cảm và thời gian bảo vệ.
- Thiết kế quy trình chuẩn bị, phát hành, phân phối, cutover, xác minh và thu hồi.
- Dùng khoảng thời gian chồng lấn để chuyển đổi mà không gây gián đoạn ngoài ý muốn.
- Xử lý rotation cho user password, API key, service account, database credential, certificate và cryptographic key.
- Quản lý phiên bản credential, consumer inventory, quyền truy cập và audit.
- Tự động hóa rotation có kiểm soát, hỗ trợ retry, idempotency và phát hiện lỗi.
- Thiết kế rollback an toàn và phân biệt rollback với việc tiếp tục dùng credential đã compromise.
- Kiểm thử rotation, xác minh không còn consumer dùng credential cũ và thu hồi đúng thời điểm.

Bài tập trung vào quản trị vòng đời credential trong hệ thống ứng dụng. Chính sách thời hạn và thuật toán cụ thể phải tuân theo tiêu chuẩn, threat model, yêu cầu pháp lý và nhà cung cấp đang triển khai.

## 2. Credential là gì?

Credential là thông tin hoặc vật chứng được dùng để xác thực một chủ thể hoặc cho phép thực hiện một thao tác. Trong hệ thống quản lý khóa, credential có thể gắn với người dùng, service, thiết bị, ứng dụng hoặc một key operation.

| Loại | Ví dụ | Vai trò |
|---|---|---|
| User authenticator | Password, passkey, security key | Xác thực người dùng |
| Machine secret | API key, client secret | Xác thực ứng dụng hoặc workload |
| Database credential | Username/password, client certificate | Cho phép kết nối database |
| Service identity credential | Private key, workload token | Xác thực service-to-service |
| Cryptographic key | DEK, KEK, signing key, MAC key | Mã hóa, giải mã, ký hoặc xác thực dữ liệu |
| Certificate | X.509 server/client certificate | Gắn public key với danh tính và mục đích |
| Session credential | Session cookie, access token, refresh token | Duy trì hoặc gia hạn phiên xác thực |

Không phải mọi credential đều là key. Password là bí mật do người dùng cung cấp; certificate thường chứa public key và thông tin danh tính; access token là vật mang quyền truy cập; private key là key material dùng cho thao tác mật mã.

Một chính sách rotation tốt phải xác định rõ đối tượng được thay thế. Ví dụ, gia hạn certificate không nhất thiết tạo key pair mới; đổi password không đồng nghĩa đổi password hashing algorithm; thay KEK không nhất thiết phải mã hóa lại toàn bộ data ciphertext.

## 3. Rotation, renewal, rekey, rewrap và revoke

Các thao tác sau liên quan nhưng không thể dùng thay thế cho nhau:

| Thao tác | Điều thay đổi | Ví dụ |
|---|---|---|
| Rotation | Credential hiện hành được thay bằng credential mới và consumer được chuyển sang | API key v1 sang v2 |
| Renewal | Gia hạn thời hạn hiệu lực của credential hoặc certificate | Gia hạn server certificate |
| Rekey | Tạo key material mới | Tạo signing key pair mới |
| Rewrap | Bọc lại cùng một DEK bằng KEK khác | KEK v1 sang KEK v2, giữ nguyên data ciphertext |
| Re-encrypt | Giải mã dữ liệu rồi mã hóa lại bằng key/algorithm mới | Chuyển ciphertext cũ sang AES-GCM |
| Password hash upgrade | Tính lại password verifier bằng KDF/parameters mới sau khi xác thực password | PBKDF2 cost cũ sang profile mới |
| Revoke | Làm credential không còn được chấp nhận | Thu hồi API key hoặc certificate |
| Disable | Tạm hoặc vĩnh viễn chặn operation theo trạng thái provider/policy | Disable key trong KMS |
| Destroy | Hủy key material theo quy trình quản trị | Hủy DEK sau khi hết dependency |

Một rotation thường kết thúc bằng revoke hoặc disable credential cũ. Nhưng trong một số trường hợp, credential cũ phải tiếp tục được dùng để xác minh dữ liệu lịch sử hoặc giải mã ciphertext cũ trong thời gian lưu trữ. Khi đó cần tách quyền tạo dữ liệu mới khỏi quyền đọc/xác minh dữ liệu cũ.

### Ví dụ phân biệt

- Thay API key v1 bằng v2 là rotation.
- Gia hạn certificate thêm một năm bằng cùng public key là renewal.
- Phát hành certificate với key pair mới là rekey kèm renewal.
- Bọc lại DEK bằng KEK mới là rewrap.
- Thay DEK và mã hóa lại payload là re-encrypt.
- Vô hiệu hóa API key bị lộ là revoke/disable khẩn cấp.

## 4. Vì sao phải rotation?

Credential có thể bị lộ, bị sao chép, được lưu ở quá nhiều nơi hoặc tiếp tục tồn tại sau khi chủ thể không còn cần quyền truy cập. Rotation giới hạn thời gian và phạm vi tác động của credential.

Các lý do phổ biến:

- Có bằng chứng hoặc nghi ngờ credential bị lộ.
- Nhân sự rời tổ chức hoặc thay đổi vai trò.
- Service account, workload hoặc vendor không còn cần quyền.
- Secret đã được dùng trong môi trường không an toàn.
- Key đạt cryptoperiod hoặc giới hạn sử dụng theo policy.
- Certificate sắp hết hạn hoặc cần thay key pair.
- Thay đổi thuật toán, key size hoặc chuẩn bảo mật.
- Có thay đổi về tenant, environment, ownership hoặc trust boundary.
- Credential được chia sẻ quá rộng và cần tách danh tính/quyền.
- Nhà cung cấp hoặc hệ thống yêu cầu thay đổi định kỳ theo chính sách.

Rotation không sửa được mọi hậu quả của compromise. Nếu kẻ tấn công đã lấy dữ liệu plaintext hoặc đã dùng quyền credential để thay đổi hệ thống, thay secret chỉ ngăn việc tiếp tục dùng credential cũ. Cần incident response để đánh giá dữ liệu, quyền, persistence và hành động đã xảy ra.

## 5. Chính sách rotation không giống nhau cho mọi credential

Không nên áp dụng một lịch xoay vòng chung cho password người dùng, API key, database secret, signing key và DEK. Mỗi loại có rủi ro, dependency và cách thu hồi khác nhau.

| Credential | Cách xác định rotation |
|---|---|
| User password | Theo sự kiện compromise, nghi ngờ lộ, reset hoặc yêu cầu xác thực; không ép đổi định kỳ nếu tiêu chuẩn hiện hành không yêu cầu |
| API key/client secret | Theo mức độ phơi lộ, quyền, thời hạn, khả năng overlap và policy |
| Database password | Theo secret policy, access scope, khả năng tạo principal song song và vòng đời connection pool |
| Service private key | Theo cryptoperiod, mục đích ký/xác thực, HSM policy và khả năng phân phối public key mới |
| KEK | Theo cryptoperiod, usage limit, provider capability và dependency của wrapped DEK |
| DEK | Theo phạm vi dữ liệu, lượng dữ liệu/operation, compromise và yêu cầu re-encryption |
| TLS certificate | Theo thời hạn, CA policy, key reuse policy và khả năng triển khai certificate mới |
| Access/refresh token | Theo expiry, session policy, signing key rotation và sự kiện thu hồi |

Chính sách cần ghi rõ owner, mục đích, thuật toán, key ID, consumer, thời hạn, trigger, overlap window, rollback conditions và tiêu chí thu hồi. Không đặt một con số ngày cố định mà không giải thích threat model và yêu cầu vận hành.

## 6. Password người dùng: đổi theo rủi ro, không ép đổi máy móc

Password người dùng khác với machine secret. Việc bắt mọi người đổi password theo lịch ngắn có thể khiến họ chọn password dễ đoán, thêm số ở cuối hoặc tái sử dụng mẫu cũ.

Hướng dẫn xác thực hiện đại của NIST không yêu cầu verifier ép người dùng thay password định kỳ nếu không có dấu hiệu compromise. Verifier cần yêu cầu thay đổi khi có bằng chứng password bị lộ hoặc không còn an toàn. Tổ chức phải đối chiếu phiên bản tiêu chuẩn và yêu cầu tuân thủ áp dụng cho hệ thống của mình.

Các sự kiện nên kích hoạt đổi password hoặc reset:

- Có bằng chứng password nằm trong dữ liệu rò rỉ.
- Tài khoản có dấu hiệu bị chiếm quyền.
- Password được chia sẻ hoặc nhập vào trang giả mạo.
- Người dùng yêu cầu thay đổi hoặc không còn kiểm soát recovery method.
- Quản trị viên xác định credential không còn đáng tin cậy.

### Quy trình đổi password an toàn

1. Xác thực người dùng bằng phiên hiện tại hoặc step-up authentication phù hợp.
2. Kiểm tra password mới theo chính sách độ dài, blocklist và kiểm soát password phổ biến/bị lộ.
3. Tính password verifier bằng KDF được phê duyệt, salt riêng và parameters hiện hành.
4. Ghi verifier mới nguyên tử.
5. Thu hồi hoặc đánh dấu không còn hiệu lực các session/refresh token theo chính sách.
6. Thông báo thay đổi qua kênh đã đăng ký, không gửi password mới.
7. Ghi audit event không chứa password hoặc hash.
8. Nếu đổi do compromise, điều tra hoạt động trước đó và các credential liên quan.

Không lưu password plaintext để hỗ trợ rotation. Không “mã hóa password để giải mã khi cần”; password xác thực nên được lưu dưới dạng password hash thích hợp.

### Password hash upgrade khác password rotation

Nếu KDF hoặc cost parameter đã cũ, hệ thống có thể nâng password hash khi người dùng đăng nhập thành công: kiểm tra password bằng verifier cũ, sau đó tính verifier mới bằng password vừa nhập. Đây là nâng cấp cách lưu verifier, không phải yêu cầu người dùng đổi password.

## 7. Machine credential và API key

API key hoặc client secret thường được lưu trong secret manager và được nhiều service consumer sử dụng. Việc thay secret phải phối hợp cả nơi phát hành, nơi phân phối và mọi consumer.

Một quy trình overlap phổ biến:

1. Tạo API key v2 với danh tính và quyền tương đương hoặc hẹp hơn v1.
2. Lưu v2 trong secret manager với version mới.
3. Cấp quyền đọc secret v2 cho đúng consumer.
4. Triển khai consumer hỗ trợ v2 và xác minh kết nối.
5. Chuyển traffic hoặc cấu hình sang v2.
6. Theo dõi request, lỗi xác thực và consumer vẫn dùng v1.
7. Chờ hết overlap window theo policy.
8. Revoke v1 và xác minh mọi request dùng v1 bị từ chối.
9. Xóa secret v1 khỏi nơi phân phối theo retention/audit policy.

Nếu API provider chỉ cho phép một key active tại một thời điểm, cần một cơ chế thay thế khác: tạo principal thứ hai, dùng key slot song song, hoặc phối hợp maintenance window. Không revoke key cũ trước khi consumer mới sẵn sàng, trừ khi key cũ đã compromise và cần containment khẩn cấp.

### Hạn chế API key

- Mỗi service hoặc integration có key riêng.
- Gắn key với scope, audience, tenant và environment.
- Không dùng một key toàn cục cho nhiều ứng dụng.
- Không nhúng key vào source code, image container hoặc frontend.
- Không log header Authorization hoặc secret.
- Ưu tiên workload identity và short-lived token khi nền tảng hỗ trợ.
- Theo dõi last-used time và từ chối key không có owner.
- Có thể disable tức thời khi compromise.

## 8. Database credential rotation

Database credential thường được giữ trong connection pool. Đổi password trong database nhưng để ứng dụng tiếp tục dùng pool cũ có thể tạo trạng thái nửa cũ nửa mới: connection hiện tại vẫn hoạt động, connection mới lại thất bại.

Một cách triển khai an toàn là dùng hai database principal có quyền tương đương trong thời gian overlap:

1. Tạo principal mới, ví dụ `app_runtime_v2`.
2. Cấp đúng grants cần thiết; không cấp quyền cao hơn chỉ để dễ migration.
3. Cập nhật secret manager với credential mới.
4. Triển khai instance ứng dụng mới hoặc refresh pool để dùng principal mới.
5. Xác minh truy vấn, transaction, background job và health check.
6. Chờ connection cũ được drain và xác minh không còn login mới bằng principal cũ.
7. Revoke quyền hoặc khóa principal cũ.
8. Xóa principal cũ theo quy trình quản trị database.

Một số database hỗ trợ hai password cho cùng user hoặc cơ chế password overlap riêng; hành vi phụ thuộc engine và phiên bản. Cần kiểm tra tài liệu database thay vì giả định mọi nền tảng đều hỗ trợ giống nhau.

### Connection pool

Khi thay credential:

- Không sửa password trong một pool đang hoạt động rồi giả định mọi connection đã được thay.
- Tạo pool mới, kiểm tra health, chuyển traffic và drain pool cũ.
- Đặt maximum connection lifetime phù hợp để connection cũ được thay dần.
- Bảo đảm transaction đang chạy được hoàn tất theo policy.
- Có timeout và giới hạn retry để tránh tạo bão kết nối khi secret sai.
- Xác minh cả worker nền, batch job, migration tool và service phụ.

Không giữ hai database principal có quyền cao vô thời hạn. Overlap phải có deadline và bằng chứng hoàn tất.

## 9. Rotation cho service account và workload identity

Service account thường tồn tại lâu hơn một cá nhân và có thể bị sử dụng bởi nhiều deployment. Credential tĩnh kéo dài làm tăng nguy cơ lộ và khó xác định owner.

Các hướng cải thiện:

- Tách identity theo workload, namespace, environment và service.
- Dùng workload identity hoặc federation để tránh phân phối long-lived secret.
- Dùng token ngắn hạn có audience và scope rõ.
- Cấp private key trong HSM hoặc signing service nếu cần chữ ký.
- Dùng credential version và key ID để theo dõi consumer.
- Tự động cấp phát, refresh và thu hồi theo lifecycle của workload.
- Gắn owner và expiry cho từng service identity.

Nếu workload dùng client certificate, cần phối hợp phát hành certificate mới, phân phối trust chain, triển khai consumer và thu hồi certificate cũ. Nếu private key bị lộ, phải rekey và đánh giá certificate revocation; chỉ gia hạn certificate với cùng key không giải quyết compromise.

## 10. Cryptographic key rotation

Rotation cho cryptographic key phải dựa vào loại key và operation.

| Loại key | Tác động khi rotation |
|---|---|
| DEK mã hóa dữ liệu | Thường cần re-encrypt dữ liệu hoặc tạo DEK mới cho dữ liệu mới |
| KEK bọc DEK | Có thể rewrap DEK mà không đổi data ciphertext |
| Signing private key | Dữ liệu mới ký bằng key mới; public key cũ có thể cần giữ để verify chữ ký lịch sử |
| MAC key | Bên tạo và xác minh MAC phải phối hợp chuyển key/version |
| TLS private key | Cần certificate mới gắn public key mới và rollout ở các TLS terminator |
| Password pepper | Cần chiến lược migration verifier; không thể chỉ thay pepper nếu không có password hoặc thiết kế nhiều version |

### Originator usage period và recipient usage period

Một key có thể ngừng dùng để tạo dữ liệu mới nhưng vẫn cần để xử lý dữ liệu đã tạo:

- Originator usage period: thời gian key được phép tạo chữ ký, MAC hoặc ciphertext mới.
- Recipient usage period: thời gian key còn được phép xác minh, giải mã hoặc xử lý dữ liệu lịch sử.

Không đồng nhất “không còn active để encrypt/sign” với “có thể destroy ngay”. Với KEK, key cũ có thể cần quyền unwrap để phục hồi wrapped DEK; với signing key, public key cũ có thể cần để verify archive. Policy cần phân biệt quyền theo operation.

### Rotation không nhất thiết phải re-encrypt tất cả

- KEK rotation thường có thể rewrap DEK.
- DEK rotation thường cần re-encrypt dữ liệu phụ thuộc.
- Signing key rotation chỉ đổi key dùng cho chữ ký mới; không thể tự thay chữ ký cũ.
- Certificate renewal với cùng key không phải rekey.
- Khi key bị compromise, phải đánh giá riêng mọi dữ liệu và chữ ký được tạo trong khoảng thời gian bị ảnh hưởng.

## 11. Certificate renewal và certificate rekey

Certificate có thời hạn và có thể được gia hạn trước khi hết hạn. Nhưng renewal và rekey có ý nghĩa khác nhau:

- Renewal: phát hành certificate mới, có thể dùng lại key pair cũ.
- Rekey: tạo key pair mới và phát hành certificate mới chứa public key mới.
- Revocation: CA đánh dấu certificate không còn được chấp nhận theo cơ chế thu hồi.

Khi certificate sắp hết hạn, quy trình nên:

1. Kiểm tra Subject/SAN, EKU, Key Usage, issuer và certificate policy.
2. Xác định có cần thay key pair hay chỉ renewal.
3. Tạo key mới nếu policy hoặc threat model yêu cầu.
4. Tạo CSR và phát hành certificate mới.
5. Triển khai certificate chain trên tất cả TLS terminator.
6. Kiểm thử SNI, hostname verification và trust chain.
7. Theo dõi handshake và consumer.
8. Thu hồi certificate cũ nếu có lý do và policy yêu cầu.

Nếu private key cũ bị lộ, renewal với cùng public key là không đủ. Cần rekey, đánh giá phạm vi sử dụng và revoke certificate cũ theo quy trình CA.

## 12. Token, session và signing key

Access token thường có thời hạn ngắn; refresh token có thời hạn dài hơn và có thể được xoay vòng khi sử dụng. Rotation của token cần gắn với session policy.

Một số nguyên tắc:

- Access token ngắn hạn để giảm cửa sổ sử dụng nếu bị lộ.
- Refresh token rotation có thể cấp token mới mỗi lần refresh và phát hiện reuse token cũ.
- Khi phát hiện reuse, thu hồi token family hoặc session theo policy.
- Không lưu bearer token trong log hoặc analytics.
- Ràng buộc token với issuer, audience, scope, subject và expiry.
- Có cơ chế logout/revoke phù hợp với kiến trúc token.

Với JWT ký bất đối xứng, signing key rotation cần key ID (`kid`) và overlap:

1. Công bố public key mới trong JWKS hoặc trust registry.
2. Chờ consumer cập nhật và có thể xác minh key mới.
3. Chuyển issuer sang ký token bằng private key mới.
4. Tiếp tục công bố public key cũ trong thời gian token cũ còn hợp lệ.
5. Khi token cũ hết hạn và không còn dependency, loại public key cũ theo policy.

Không xóa public key cũ ngay khi bắt đầu ký bằng key mới; token đã phát hành vẫn cần xác minh. Nếu private key bị compromise, phải có quy trình khẩn cấp thu hồi token/key và đánh giá token đã phát hành.

## 13. Xác định overlap window

Overlap window là khoảng thời gian credential mới và credential cũ cùng được chấp nhận theo policy để consumer chuyển đổi.

Độ dài overlap phụ thuộc:

- Thời gian rollout tới tất cả instance/region.
- Cache và chu kỳ refresh secret.
- Tuổi thọ connection pool hoặc session.
- Thời hạn token/certificate.
- Số consumer offline hoặc chạy theo lịch.
- Khả năng rollback.
- Mức độ nguy hiểm nếu credential cũ bị lộ.

Không đặt overlap quá ngắn khiến deployment chưa hoàn tất đã revoke credential cũ. Cũng không để overlap vô hạn. Phải có deadline, metric chứng minh consumer cũ đã ngừng hoạt động và quy trình xử lý consumer chưa xác định.

Với credential đã compromise, không dùng overlap thông thường nếu việc tiếp tục chấp nhận credential cũ tạo rủi ro. Cần containment khẩn cấp và xử lý availability theo incident plan.

## 14. State machine cho rotation

Một quy trình rotation có thể mô hình hóa bằng các trạng thái:

~~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE
    ACTIVE --> PREPARED: Tạo credential mới
    PREPARED --> DISTRIBUTED: Lưu và phân phối
    DISTRIBUTED --> CUTOVER: Consumer bắt đầu dùng mới
    CUTOVER --> VERIFYING: Kiểm tra traffic và lỗi
    VERIFYING --> OVERLAP: Mới ổn định, giữ cũ tạm thời
    OVERLAP --> REVOKED: Hết overlap, đủ bằng chứng
    VERIFYING --> ROLLBACK: Phát hiện lỗi
    ROLLBACK --> ACTIVE: Khôi phục cấu hình cũ nếu an toàn
    ACTIVE --> EMERGENCY_REVOKE: Credential cũ bị compromise
    PREPARED --> ABORTED: Hủy trước cutover
    DISTRIBUTED --> ABORTED: Hủy trước cutover
    REVOKED --> [*]
    EMERGENCY_REVOKE --> [*]
~~~~

Ý nghĩa các trạng thái:

| Trạng thái | Quy tắc |
|---|---|
| ACTIVE | Credential hiện hành được dùng theo operation policy |
| PREPARED | Credential mới đã được tạo nhưng chưa phân phối cho traffic |
| DISTRIBUTED | Consumer được cấp quyền đọc credential mới |
| CUTOVER | Consumer đang chuyển sang credential mới |
| VERIFYING | Đang đo lỗi, traffic và mức sử dụng phiên bản |
| OVERLAP | Credential cũ còn được chấp nhận trong thời hạn giới hạn |
| REVOKED | Credential cũ không còn được chấp nhận |
| ROLLBACK | Chuyển về credential trước đó nếu credential đó vẫn an toàn |
| EMERGENCY_REVOKE | Thu hồi ngay vì compromise hoặc rủi ro nghiêm trọng |
| ABORTED | Hủy lần rotation trước khi cutover hoàn tất |

State machine cần được lưu bền vững. Không chỉ dùng một biến trong process vì restart, multi-region hoặc worker retry có thể làm mất trạng thái.

## 15. Quy trình rotation chuẩn

Một quy trình thực tế có thể chia thành tám giai đoạn:

### Giai đoạn 1: Inventory và chuẩn bị

- Xác định credential ID, version, owner và purpose.
- Liệt kê mọi consumer, region, job, backup và dependency.
- Kiểm tra policy, provider capability và quyền thao tác.
- Đánh giá overlap window và rollback conditions.
- Xác định tiêu chí thành công và deadline.

### Giai đoạn 2: Tạo credential mới

- Tạo secret/key mới bằng nguồn ngẫu nhiên hoặc KMS/HSM phù hợp.
- Gắn ID/version duy nhất.
- Áp dụng scope tối thiểu.
- Ghi metadata và audit event.
- Không ghi raw secret vào log hoặc ticket.

### Giai đoạn 3: Phân phối có kiểm soát

- Lưu credential mới vào secret manager.
- Cấp quyền đọc cho đúng consumer.
- Kiểm tra secret version và access policy.
- Không phát tán qua chat, email hoặc file cấu hình không bảo vệ.

### Giai đoạn 4: Chuyển consumer

- Deploy consumer hỗ trợ version mới.
- Refresh secret cache hoặc connection pool theo cách có kiểm soát.
- Dùng canary/rolling deployment nếu phù hợp.
- Kiểm tra health, authentication success và business operation.

### Giai đoạn 5: Quan sát

- Đếm request theo credential version.
- Theo dõi lỗi xác thực và latency.
- Xác định consumer vẫn dùng version cũ.
- Kiểm tra batch job và workload ít hoạt động.
- Không kết luận hoàn tất chỉ từ một health check.

### Giai đoạn 6: Thu hồi credential cũ

- Chỉ revoke khi đủ điều kiện và hết overlap.
- Kiểm tra mọi consumer đã chuyển đổi.
- Thu hồi ở nơi phát hành/provider.
- Kiểm thử credential cũ bị từ chối.
- Xóa cache và bản sao theo retention policy.

### Giai đoạn 7: Xác minh sau rotation

- Kiểm tra operation chính và luồng phục hồi.
- Kiểm tra audit, key usage và trạng thái provider.
- Kiểm tra backup/DR nếu credential có liên quan.
- Xác nhận không còn request mới bằng credential cũ.

### Giai đoạn 8: Đóng và lưu bằng chứng

- Ghi version cũ/mới, thời điểm, owner và kết quả.
- Ghi ngoại lệ và consumer chưa chuyển đổi.
- Lưu audit evidence không chứa secret.
- Cập nhật inventory và lịch rotation tiếp theo.

## 16. Triển khai an toàn với expand, migrate, contract

Mẫu expand-migrate-contract giảm rủi ro khi nhiều service cùng phụ thuộc credential:

~~~~mermaid
flowchart LR
    A[Expand: phát hành credential mới] --> B[Consumer hỗ trợ cả version cũ và mới]
    B --> C[Migrate: chuyển traffic/consumer sang mới]
    C --> D[Measure: xác minh không còn dùng cũ]
    D --> E[Contract: revoke credential cũ]
~~~~

**Expand:** cấp credential mới và cho consumer biết cách dùng nó. Hệ thống có thể tạm thời chấp nhận cả hai version.

**Migrate:** chuyển consumer theo từng nhóm, kiểm tra lỗi và theo dõi usage. Với database, tạo principal mới và chuyển connection pool; với JWT, công bố public key mới trước khi signer bắt đầu dùng private key mới.

**Contract:** khi đã đủ bằng chứng, thu hồi credential cũ và dọn dẹp bản sao. Bước này không được bỏ qua vì credential cũ vẫn có thể là đường truy cập hợp lệ.

Không triển khai contract ngay sau khi deploy một phiên bản ứng dụng. Cần xác minh các consumer ít hoạt động, cron job, region dự phòng và quy trình DR.

## 17. Java example: policy theo phiên bản credential

Ví dụ sau minh họa policy tách quyền sử dụng credential mới và credential cũ. Nó không chứa secret; secret thực tế phải được lấy từ secret manager hoặc provider theo danh tính workload.

~~~~java
import java.time.Instant;
import java.util.Objects;

public final class CredentialVersionPolicy {
    public enum State {
        PREPARED,
        ACTIVE,
        VERIFY_ONLY,
        REVOKED
    }

    public record Version(
            String id,
            int version,
            State state,
            Instant verifyUntil
    ) {
        public Version {
            Objects.requireNonNull(id);
            Objects.requireNonNull(state);
            if (id.isBlank() || version < 1) {
                throw new IllegalArgumentException("Invalid credential version");
            }
        }
    }

    private CredentialVersionPolicy() {
    }

    public static void requireForNewAuthentication(Version credential) {
        if (credential.state() != State.ACTIVE) {
            throw new SecurityException(
                    "Credential version is not active for new use"
            );
        }
    }

    public static void requireForVerification(
            Version credential,
            Instant now
    ) {
        Objects.requireNonNull(now);

        if (credential.state() == State.REVOKED
                || credential.state() == State.PREPARED) {
            throw new SecurityException("Credential is not accepted");
        }

        if (credential.state() == State.VERIFY_ONLY
                && (credential.verifyUntil() == null
                    || now.isAfter(credential.verifyUntil()))) {
            throw new SecurityException(
                    "Credential verification window has ended"
            );
        }
    }
}
~~~~

Trong ví dụ, ACTIVE được phép dùng cho operation mới; VERIFY_ONLY chỉ được dùng để xác minh trong thời hạn. PREPARED chưa được chấp nhận và REVOKED bị từ chối.

Policy production phải kiểm tra thêm purpose, tenant, audience, provider state, key usage, caller identity và authorization. Không dùng enum này làm nguồn trạng thái duy nhất nếu provider/KMS có trạng thái độc lập. Khi có xung đột, phải đối chiếu trạng thái authoritative và fail closed theo policy.

## 18. Java example: chuyển cấu hình credential nguyên tử

Một ứng dụng có thể giữ reference tới phiên bản credential hiện hành. Khi secret mới đã được tạo, phân phối và kiểm tra, ứng dụng mới chuyển reference. Ví dụ sau chỉ mô phỏng metadata reference, không lưu raw secret trong AtomicReference.

~~~~java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class ActiveCredentialReference {
    public record Reference(String secretId, String version) {
        public Reference {
            Objects.requireNonNull(secretId);
            Objects.requireNonNull(version);
            if (secretId.isBlank() || version.isBlank()) {
                throw new IllegalArgumentException("Invalid secret reference");
            }
        }
    }

    private final AtomicReference<Reference> active;

    public ActiveCredentialReference(Reference initial) {
        this.active = new AtomicReference<>(
                Objects.requireNonNull(initial)
        );
    }

    public Reference current() {
        return active.get();
    }

    public boolean cutover(
            Reference expectedOld,
            Reference preparedNew
    ) {
        Objects.requireNonNull(expectedOld);
        Objects.requireNonNull(preparedNew);

        if (expectedOld.equals(preparedNew)) {
            throw new IllegalArgumentException(
                    "New reference must differ from old reference"
            );
        }

        return active.compareAndSet(expectedOld, preparedNew);
    }
}
~~~~

Compare-and-set tránh ghi đè một cutover khác đã xảy ra trong cùng process. Trong hệ thống nhiều instance, cần version/lease/transaction hoặc control plane có tính nhất quán phù hợp; AtomicReference cục bộ không điều phối toàn cluster.

Không xóa credential cũ ngay sau khi đổi pointer. Cần overlap, consumer telemetry, drain connection/session và revoke theo quy trình quản trị.

## 19. Tự động hóa rotation

Tự động hóa giúp giảm thao tác thủ công và lỗi do quên thay credential, nhưng automation phải có quyền giới hạn và trạng thái bền vững.

Một rotation controller có thể thực hiện:

- Đọc inventory và policy.
- Phát hiện credential sắp hết hạn hoặc đến cryptoperiod.
- Tạo version mới qua secret manager/KMS.
- Cấp quyền cho consumer.
- Gửi signal hoặc cập nhật cấu hình.
- Chạy health check và xác minh operation.
- Theo dõi usage cũ/mới.
- Thu hồi credential cũ khi đủ điều kiện.
- Ghi audit event và thông báo owner.

### Các thuộc tính cần có

- **Idempotency:** chạy lại cùng một rotation không tạo vô hạn credential.
- **Concurrency control:** hai controller không đồng thời cutover cùng một identity.
- **Durable state:** restart không làm mất phase hiện tại.
- **Least privilege:** controller chỉ có quyền tạo, đọc metadata và revoke đúng credential được giao.
- **Approval gate:** key hoặc identity quan trọng có thể cần dual control.
- **Rate limit:** tránh xoay hàng nghìn credential đồng thời và gây sự cố diện rộng.
- **Observability:** metric theo version, consumer, region và kết quả.
- **Safe retry:** retry không làm credential cũ bị revoke trước khi consumer mới sẵn sàng.

Không tự động rotate toàn bộ credential trong một đợt nếu chưa đánh giá tải và blast radius. Chia batch, canary và có circuit breaker.

## 20. Rollback và điều kiện không được rollback

Rollback có thể cần thiết khi credential mới không hoạt động, nhưng chỉ an toàn nếu credential cũ vẫn đáng tin cậy.

Có thể rollback khi:

- Credential cũ chưa bị compromise.
- Credential cũ vẫn còn active/accepted theo provider.
- Chưa có policy hoặc incident yêu cầu revoke.
- Việc quay lại không tạo downgrade.
- Có bằng chứng và người chịu trách nhiệm phê duyệt.

Không rollback sang credential cũ khi:

- Credential cũ đã bị lộ hoặc bị đánh cắp.
- Private key cũ bị compromise.
- Certificate cũ đã bị revoke.
- Policy cũ không còn đạt yêu cầu.
- Kẻ tấn công có thể tiếp tục sử dụng credential cũ.

Khi credential cũ bị compromise, ưu tiên containment: revoke, chặn session/token, xoay credential liên quan và chấp nhận xử lý availability theo incident plan. Một deployment rollback không được phép khôi phục bí mật đã bị thu hồi.

## 21. Rotation khẩn cấp khi credential bị lộ

Emergency rotation có mục tiêu cô lập nhanh credential bị lộ. Không nhất thiết phải chờ overlap thông thường.

Quy trình tham khảo:

1. Xác định credential ID/version, loại, owner, provider và quyền liên quan.
2. Chặn hoặc revoke credential bị lộ theo mức độ khẩn cấp.
3. Thu hồi session/token và quyền tạm thời nếu có thể.
4. Tạo credential mới từ nguồn tin cậy.
5. Cập nhật consumer và xác minh luồng hoạt động.
6. Tìm nơi credential cũ đã xuất hiện: log, CI/CD, image, repository, backup, chat hoặc endpoint.
7. Kiểm tra hành động đã thực hiện bằng credential cũ.
8. Xoay các credential khác có khả năng cùng bị lộ.
9. Cập nhật audit, incident record và biện pháp ngăn tái diễn.

Không chỉ xóa secret khỏi file hoặc history rồi coi sự cố đã kết thúc. Nếu secret đã từng được commit, gửi qua log hoặc lưu trong artifact, giả định rằng nó có thể đã bị sao chép và phải revoke theo policy.

## 22. Rotation trong KMS/HSM và secret manager

KMS/HSM có thể hỗ trợ versioning, automatic rotation, key aliases, scheduled rotation hoặc operation-specific permissions. Hành vi cụ thể phụ thuộc provider.

Cần xác định:

- Rotation tạo key material mới hay chỉ tạo key version?
- Alias có tự trỏ sang version mới không?
- Key cũ còn được phép decrypt/unwrap/verify không?
- Ciphertext có lưu version ID hay phụ thuộc alias?
- Có cần rewrap hoặc re-encrypt dữ liệu?
- Backup/replica/DR có giữ đủ version không?
- Provider có giới hạn số version, key usage hoặc thời gian giữ không?
- Rotation có audit event và approval gate không?

Không giả định bật automatic rotation có nghĩa mọi ciphertext đã được chuyển sang key mới. Một số dịch vụ chỉ thay version dùng cho encryption mới, trong khi key version cũ vẫn cần để decrypt dữ liệu cũ.

Secret manager thường lưu nhiều version. Consumer phải xác định rõ đang dùng version nào, không nên đọc một alias thay đổi mà không kiểm tra khả năng cache và rollout. Cần kiểm thử việc refresh secret, restart, failover và rollback.

## 23. Rotation và quyền truy cập

Rotation không chỉ là thay giá trị secret. Đây cũng là cơ hội giảm quyền và sửa identity design.

Mỗi credential cần có:

- Owner chịu trách nhiệm.
- Identity hoặc workload cụ thể.
- Purpose và allowed operation.
- Scope/resource/tenant.
- Environment.
- Expiry hoặc cryptoperiod.
- Consumer inventory.
- Secret/key version.
- Approval và audit history.

Nếu một API key đang có quyền quản trị toàn hệ thống, thay key mới nhưng giữ nguyên quyền sẽ không giảm blast radius. Khi rotation, xem xét tách key theo service, giảm scope và loại bỏ quyền không còn cần.

Với signing key và encryption key, tách purpose. Không dùng cùng key material cho ký và mã hóa chỉ để tiện quản lý.

## 24. Audit, metrics và bằng chứng hoàn tất

Một rotation được coi là hoàn tất khi có bằng chứng consumer đã chuyển sang credential mới và credential cũ không còn được chấp nhận theo policy.

Metric nên theo dõi:

- Credential được tạo theo ngày và loại.
- Credential đến hạn hoặc quá hạn.
- Số consumer đang dùng từng version.
- Request authentication thành công/thất bại theo version.
- Thời điểm last-used của credential cũ.
- Số session/connection còn gắn credential cũ.
- Thời gian từ PREPARED tới REVOKED.
- Rotation thất bại, retry và rollback.
- Số credential không có owner hoặc consumer.
- Số secret xuất hiện trong nơi lưu trữ không được phép.

Audit event nên có:

- Credential ID/version (không có raw secret).
- Actor/workload thực hiện.
- Operation và lý do.
- Thời điểm bắt đầu, cutover và revoke.
- Approval reference.
- Provider/KMS identity.
- Kết quả và error category.
- Consumer coverage và bằng chứng verification.

Không ghi password, API key, private key, access token hoặc secret value vào audit log. Hash của secret cũng không nên tự động ghi nếu có nguy cơ hỗ trợ dò đoán hoặc correlation không cần thiết.

## 25. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Ứng dụng lỗi ngay sau rotation | Consumer chưa nhận secret mới | Kiểm tra version, quyền đọc và rollout |
| Một số instance hoạt động, số khác lỗi | Cache hoặc instance config không đồng nhất | Refresh theo version, canary và kiểm tra từng instance |
| Database connection thất bại ngẫu nhiên | Pool cũ và pool mới cùng tồn tại sai cách | Tạo pool mới, health check, chuyển traffic và drain pool cũ |
| Token mới không xác minh được | Verifier chưa có public key mới | Công bố public key trước khi signer cutover |
| Token cũ đột ngột lỗi | Public key cũ bị xóa quá sớm | Giữ public key theo token lifetime và policy |
| Ciphertext cũ không decrypt được | Xóa key version cũ hoặc alias đổi semantics | Khôi phục key dependency và kiểm tra version ID |
| Rotation chạy lặp tạo nhiều secret | Thiếu idempotency/concurrency control | Dùng operation ID, state bền vững và CAS |
| Credential cũ vẫn được dùng | Consumer ít hoạt động hoặc telemetry thiếu | Inventory cron job, DR, region và consumer offline |
| Rollback không hoạt động | Credential cũ đã revoke hoặc compromise | Dùng incident recovery và credential mới |
| Rotation làm lộ secret | Secret được in vào log hoặc pipeline output | Redact log, secret manager và audit access |

## 26. Tình huống thực tế

### Tình huống A: API key của đối tác

Một service thanh toán dùng API key v1 để gọi đối tác. Đối tác hỗ trợ hai key active đồng thời.

Đội vận hành tạo v2, lưu vào secret manager, cấp quyền cho workload và deploy theo canary. Khi mọi instance gửi request thành công bằng v2, dashboard không còn request dùng v1 và các batch job đã chạy xong, đội vận hành revoke v1. Nếu v1 đã bị lộ, họ phải revoke ngay và phối hợp đối tác xử lý gián đoạn theo incident plan.

### Tình huống B: Database password

Một ứng dụng có 40 instance và connection pool. Đổi password trên cùng một database user khiến instance cũ không thể tạo connection mới sau khi password cũ bị vô hiệu hóa.

Giải pháp là tạo database principal v2 với grants tối thiểu, triển khai pool mới, chuyển traffic, drain pool cũ và sau đó revoke principal v1. Cần xác minh cả worker nền, cron job và disaster recovery environment.

### Tình huống C: JWT signing key

Một authorization service ký JWT bằng key K1. Verifier lấy public key từ JWKS. Nếu issuer chuyển sang K2 trước khi public key K2 được phân phối, verifier sẽ từ chối token mới.

Quy trình đúng là công bố public key K2, đợi cache/consumer cập nhật, chuyển issuer ký bằng K2, giữ K1 cho token còn hạn rồi mới gỡ K1. Khi K1 compromise, quy trình khẩn cấp cần revoke token và key theo policy, không giữ overlap chỉ vì tiện.

### Tình huống D: KEK rotation

Một hệ thống dùng KEK-v1 để bọc DEK. Khi KEK-v2 được tạo, service có thể rewrap DEK sang KEK-v2 trong khi data ciphertext vẫn giữ nguyên. Tuy nhiên, KEK-v1 phải còn khả năng unwrap cho tới khi mọi wrapped DEK, backup và archive cần thiết đã được chuyển đổi. Nếu DEK bị compromise, chỉ rewrap là không đủ; phải tạo DEK mới và re-encrypt dữ liệu.

## 27. Checklist triển khai

### Trước rotation

- [ ] Có owner, purpose, identity và consumer inventory.
- [ ] Xác định loại credential và operation phụ thuộc.
- [ ] Xác định trigger, overlap window và deadline.
- [ ] Kiểm tra provider/KMS/secret manager capability.
- [ ] Có credential mới và quyền truy cập đúng scope.
- [ ] Có kế hoạch rollback và emergency revoke.
- [ ] Có canary, health check và telemetry.

### Trong rotation

- [ ] Credential mới được tạo và lưu an toàn.
- [ ] Consumer nhận đúng version.
- [ ] Không log secret value.
- [ ] Có thể xác minh từng instance/region.
- [ ] Connection/session/cache được refresh đúng cách.
- [ ] Retry có idempotency và concurrency control.
- [ ] Credential cũ chỉ được giữ trong overlap đã phê duyệt.

### Sau rotation

- [ ] Traffic mới dùng credential mới.
- [ ] Cron job, batch, backup và DR consumer đã được kiểm tra.
- [ ] Credential cũ đã revoke/disable đúng thời điểm.
- [ ] Credential cũ bị từ chối trong negative test.
- [ ] Secret cache và bản sao được xử lý.
- [ ] Inventory, owner và expiry được cập nhật.
- [ ] Audit evidence không chứa bí mật.
- [ ] Có bằng chứng hoàn tất và thời hạn ngoại lệ nếu còn.

## 28. Câu hỏi tự kiểm tra

**1. Credential rotation là gì?**

Thay credential đang sử dụng bằng credential mới, chuyển consumer sang credential mới, xác minh và thu hồi credential cũ theo policy.

**2. Rotation khác renewal thế nào?**

Rotation thay credential hiện hành; renewal gia hạn thời hạn hiệu lực và có thể giữ nguyên key pair.

**3. Rotation khác rekey thế nào?**

Rotation là quy trình chuyển đổi tổng thể; rekey là tạo key material mới, thường là một phần của rotation.

**4. Rewrap có cần mã hóa lại data ciphertext không?**

Không nhất thiết. Rewrap chỉ thay lớp bọc DEK bằng KEK mới; data ciphertext có thể giữ nguyên.

**5. Có nên ép mọi người đổi password mỗi 30 hoặc 90 ngày không?**

Không nên áp dụng máy móc. Theo hướng dẫn xác thực hiện đại, cần đổi khi có dấu hiệu compromise hoặc sự kiện rủi ro; chính sách cụ thể phải theo tiêu chuẩn áp dụng.

**6. Password hash upgrade có phải password rotation không?**

Không. Đây là thay đổi cách lưu verifier sau khi xác thực password thành công.

**7. Vì sao cần overlap window?**

Để consumer chuyển sang credential mới trong khi credential cũ còn được chấp nhận có thời hạn, giảm gián đoạn.

**8. Overlap có nên kéo dài vô hạn không?**

Không. Cần deadline, telemetry và tiêu chí thu hồi rõ ràng.

**9. Khi credential cũ bị compromise có nên giữ overlap thông thường không?**

Không nếu việc tiếp tục chấp nhận nó tạo rủi ro. Cần containment và emergency revoke theo incident plan.

**10. Vì sao database rotation cần quan tâm connection pool?**

Connection hiện tại có thể vẫn hoạt động trong khi connection mới thất bại do credential đã đổi; cần refresh pool và drain có kiểm soát.

**11. Khi rotate JWT signing key, cần phân phối thành phần nào trước?**

Public key mới cần được công bố cho verifier trước khi issuer bắt đầu ký bằng private key mới.

**12. Có nên xóa public key cũ ngay khi chuyển sang signing key mới không?**

Không. Token hoặc chữ ký cũ có thể vẫn cần được xác minh trong thời hạn và policy lưu trữ.

**13. Automatic KMS rotation có tự re-encrypt mọi ciphertext không?**

Không thể giả định như vậy. Cần kiểm tra semantics của provider và version key trong ciphertext.

**14. Rotation có thay thế incident response không?**

Không. Nếu credential đã bị dùng trái phép, cần điều tra hành động, dữ liệu và persistence ngoài việc thay secret.

**15. Vì sao phải inventory consumer trước khi rotation?**

Để không bỏ sót service, cron job, region dự phòng, backup hoặc workload ít hoạt động vẫn phụ thuộc credential cũ.

**16. Khi nào rollback sang credential cũ không được phép?**

Khi credential cũ đã compromise, revoked, bị policy cấm hoặc việc dùng lại tạo downgrade.

**17. Idempotency giúp gì cho rotation automation?**

Ngăn retry tạo nhiều credential hoặc thực hiện cutover/revoke lặp ngoài ý muốn.

**18. Credential ID/version có được ghi vào audit không?**

Có thể ghi metadata cần thiết theo policy, nhưng tuyệt đối không ghi raw secret hoặc token value.

**19. Có nên dùng cùng một API key cho nhiều service không?**

Không nên. Tách credential theo workload và scope giúp giảm blast radius và xác định owner.

**20. Khi nào rotation được coi là hoàn tất?**

Khi consumer đã chuyển đổi, operation mới dùng version mới, credential cũ đã bị thu hồi đúng policy và có bằng chứng xác minh.

## 29. Tài liệu tham khảo

- NIST SP 800-57 Part 1 — Recommendation for Key Management: cryptoperiod, key lifecycle và quản trị khóa.
- NIST SP 800-63B-4 — Digital Identity Guidelines: Authentication and Authenticator Management; tham khảo yêu cầu hiện hành cho chính sách password.
- NIST SP 800-132 — Recommendation for Password-Based Key Derivation.
- NIST SP 800-131A — Transitioning the Use of Cryptographic Algorithms and Key Lengths.
- RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile.
- RFC 7517 — JSON Web Key (JWK).
- RFC 7519 — JSON Web Token (JWT).
- RFC 7515 — JSON Web Signature (JWS).
- Tài liệu chính thức của secret manager, KMS, HSM, database engine và identity provider đang triển khai; đặc biệt về versioning, overlap, revoke, cache và automatic rotation.

