# Credential destruction — Thu hồi và hủy credential an toàn

> **Chương:** Credential lifecycle  
> **Chủ đề:** Credential destruction

**Credential destruction** là quá trình kết thúc khả năng sử dụng một credential và xử lý an toàn mọi bản sao, khóa bí mật hoặc dữ liệu xác minh liên quan khi credential không còn cần thiết, bị mất, bị lộ, hết hạn hoặc tài khoản kết thúc vòng đời. Một credential có thể là password verifier, passkey registration, TOTP seed, recovery code, API key, refresh token, private key, certificate binding hoặc bí mật của workload. Mỗi loại có cách thu hồi và hủy khác nhau.

Hủy credential không chỉ là xóa một dòng trong database. Một credential có thể còn được chấp nhận bởi cache, token đã phát hành, replica, backup, queue, thiết bị, secret manager hoặc một dịch vụ bên ngoài. Với token tự chứa đã ký, bản sao có thể tiếp tục được xác minh đến khi hết hạn dù record phía phát hành đã bị xóa. Với passkey, server thường chỉ lưu public key; private key nằm trong authenticator và server không thể tự xóa từ xa. Với certificate, chứng chỉ thường là dữ liệu công khai, còn private key mới là bí mật cần bảo vệ.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, kết nối credential destruction với password, MFA, passkey, certificate, token, session, SSO, recovery và account lifecycle. Trọng tâm là phân biệt revoke, disable, rotate và destroy; xác định nơi credential tồn tại; chọn phương pháp hủy phù hợp; xử lý trạng thái phân tán; và chứng minh credential đã hủy không còn cấp quyền.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Phân biệt thu hồi, vô hiệu hóa, luân chuyển, xóa logic và hủy vật lý/crypto-erasure.
2. Lập danh mục credential và xác định nơi lưu bản gốc, verifier, bản sao, cache và backup.
3. Chọn cách hủy phù hợp với password verifier, token, API key, passkey, TOTP seed, certificate và private key.
4. Thu hồi session, refresh token, access token và credential liên quan theo mức độ compromise.
5. Thiết kế thứ tự revoke trước, purge sau để giảm cửa sổ truy cập còn sót.
6. Xử lý replica, cache, queue, backup, log, secret manager và hệ thống bên thứ ba.
7. Áp dụng cryptographic erasure, secure media sanitization và zeroization theo đúng giới hạn kỹ thuật.
8. Duy trì retention, legal hold, audit và bằng chứng hủy mà không giữ lại bí mật.
9. Kiểm thử replay, stale credential, race condition và khả năng tái sử dụng sau khi hủy.

## 2. Vì sao credential destruction quan trọng?

Credential là bằng chứng cho phép một principal được xác thực hoặc một hệ thống truy cập tài nguyên. Khi credential không còn được phép sử dụng, mọi bản sao còn hiệu lực đều là bề mặt tấn công.

Ví dụ:

- Nhân viên nghỉ việc nhưng API key cũ vẫn được một job tự động sử dụng;
- Người dùng mất điện thoại nhưng passkey registration cũ vẫn được RP chấp nhận;
- Password bị lộ, người dùng đổi password nhưng refresh token bị đánh cắp vẫn hoạt động;
- Certificate hết hạn nhưng private key còn nằm trong image/container cũ;
- TOTP authenticator bị gỡ trên UI nhưng seed vẫn còn trong database backup;
- JWT access token chứa role cũ vẫn được API chấp nhận sau khi quyền đã bị thu hồi.

Hủy đúng cách giảm khả năng credential bị tái sử dụng, giới hạn thời gian attacker có quyền và hỗ trợ tuân thủ chính sách lưu trữ dữ liệu.

## 3. Phân biệt revoke, disable, rotate và destroy

Các thao tác này thường được gọi chung là “xóa credential”, nhưng có kết quả khác nhau.

| Thao tác | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Disable** | Tạm ngừng chấp nhận credential, có thể bật lại | Tạm khóa API key khi điều tra |
| **Revoke** | Đánh dấu credential hoặc quyền sử dụng không còn hợp lệ | Thu hồi refresh token family hoặc certificate |
| **Rotate** | Thay credential cũ bằng credential mới | Thay API secret, signing key hoặc TOTP seed |
| **Logical delete** | Xóa/ẩn record khỏi luồng sử dụng thông thường | Xóa passkey registration khỏi account |
| **Destroy** | Làm credential hoặc key material không thể sử dụng lại theo mô hình lưu trữ | Xóa key encryption hoặc sanitize thiết bị lưu trữ |
| **Expire** | Credential tự hết hiệu lực theo thời gian | Access token hết hạn |

Revoke và destroy không đồng nghĩa. Một certificate có thể bị revoke nhưng bản sao certificate vẫn tồn tại; private key cần được xử lý riêng. Một JWT có thể bị đánh dấu revoked trong hệ thống nhưng bản sao của nó vẫn tồn tại ở client. Một database row có thể bị xóa logic nhưng dữ liệu vẫn còn trong backup.

### 3.1. Revoke trước, destroy sau

Trong nhiều tình huống, thứ tự an toàn là:

1. Ngừng chấp nhận credential tại điểm kiểm tra quyền;
2. Thu hồi session/token/credential liên quan;
3. Cập nhật cache, replica và hệ thống tích hợp;
4. Xác nhận không còn đường sử dụng hợp lệ;
5. Hủy key material hoặc dữ liệu credential theo retention policy;
6. Ghi bằng chứng hoàn tất.

Nếu xóa dữ liệu trước khi có cơ chế revoke nhất quán, một dịch vụ khác có thể vẫn giữ bản sao và tiếp tục chấp nhận credential.

## 4. Xác định phạm vi credential cần hủy

Trước khi hủy, cần xác định credential thuộc ai, dùng ở đâu và có thể cấp quyền gì.

### 4.1. Inventory

Một inventory có thể gồm:

- Principal/account/tenant hoặc workload owner;
- Loại credential và identifier;
- Issuer hoặc hệ thống phát hành;
- Mục đích, scope và audience;
- Nơi lưu verifier/private key/secret;
- Thiết bị hoặc ứng dụng đang sử dụng;
- Ngày tạo, hết hạn và lần sử dụng gần nhất;
- Session, token hoặc service phụ thuộc;
- Trạng thái active, disabled, revoked hoặc destroyed;
- Người yêu cầu, người phê duyệt và lý do hủy.

Không lưu plaintext secret vào inventory. Dùng credential ID, key ID hoặc reference đã được bảo vệ.

### 4.2. Xác định dependency

Một credential có thể được dùng bởi nhiều dịch vụ. Trước khi rotate hoặc destroy, xác định:

- API/client nào đang dùng;
- Job, scheduled task, container hoặc mobile app nào phụ thuộc;
- Token nào được phát hành từ credential đó;
- Key nào mã hóa hoặc ký dữ liệu khác;
- Dịch vụ bên thứ ba nào cần nhận thông báo revoke;
- Có credential dự phòng hoặc đường recovery nào cần cập nhật không.

Với compromise đang diễn ra, ưu tiên chặn quyền sử dụng trước rồi xử lý tác động gián đoạn. Với thay đổi định kỳ, có thể triển khai key mới, chuyển consumer, xác minh rồi thu hồi key cũ.

## 5. Các lớp dữ liệu cần xem xét khi hủy

Credential có thể tồn tại ở nhiều lớp:

~~~mermaid
flowchart TD
    C["Credential / key material"] --> A["Primary store: database / vault / HSM"]
    C --> B["Application memory / process"]
    C --> D["Cache / replica / read model"]
    C --> E["Client device / authenticator"]
    C --> F["Token / session đã phát hành"]
    C --> G["Backup / snapshot / export"]
    C --> H["Logs / telemetry / support artifact"]
    C --> I["Third-party provider / integration"]
    A --> J["Revoke và destruction workflow"]
    B --> J
    D --> J
    E --> J
    F --> J
    G --> J
    H --> J
    I --> J
~~~

### 5.1. Primary store

Database, secret manager, HSM hoặc KMS có thể chứa verifier, secret hoặc key reference. Cần xóa hoặc vô hiệu theo API và lifecycle của nền tảng. Xóa record không nhất thiết xóa backup hoặc replica.

### 5.2. Cache và read replica

Cache có thể tiếp tục trả trạng thái active cũ. Cần invalidation hoặc version/fencing mechanism, đặt TTL phù hợp và kiểm tra mọi API instance. Nếu cache không thể được invalidated ngay, policy phải xác định cửa sổ stale tối đa và hành động nào phải fail closed.

### 5.3. Client và authenticator

Private key của passkey/security key thường nằm trong authenticator. RP có thể xóa credential registration và từ chối credential ID đó, nhưng không thể xóa private key khỏi thiết bị người dùng từ xa. Cần hướng dẫn người dùng xóa credential trên thiết bị/hệ sinh thái nếu thiết bị bị mất hoặc bán lại.

### 5.4. Token và session

Credential gốc có thể đã tạo ra session hoặc token. Hủy password/API key không tự động hủy mọi session/token đã phát hành từ trước. Phải có dependency map và quy tắc revoke riêng.

### 5.5. Backup, snapshot và export

Dữ liệu có thể còn trong backup theo lịch retention. Nếu không thể xóa riêng từng record khỏi immutable backup, cần giới hạn quyền truy cập, mã hóa backup, thời hạn retention và quy trình purge/crypto-erasure được phê duyệt.

### 5.6. Log và telemetry

Không ghi secret ngay từ đầu là biện pháp tốt nhất. Nếu credential đã xuất hiện trong log, cần xác định phạm vi bản sao, index, export và retention; hạn chế truy cập và xử lý theo incident/data retention policy. Không sửa audit history theo cách phá vỡ tính toàn vẹn điều tra.

## 6. Hủy password và password verifier

Server thường không lưu password plaintext; nó lưu password verifier được tạo bằng password hashing/KDF với salt riêng và tham số phù hợp.

### 6.1. Khi password bị đổi hoặc account đóng

- Đánh dấu password verifier cũ không còn được chấp nhận;
- Thay bằng verifier mới sau khi xác minh đúng người dùng;
- Thu hồi session/refresh token theo policy;
- Xóa verifier cũ khỏi primary store theo retention;
- Xử lý replica, backup và log theo chính sách;
- Không ghi password mới hoặc cũ vào audit.

### 6.2. Password hash vẫn là dữ liệu nhạy cảm

Hash không phải password plaintext, nhưng có thể bị tấn công offline nếu database bị lộ. Cần bảo vệ như dữ liệu credential: access control, encryption at rest, backup protection và retention. Khi account không còn cần thiết, xóa verifier theo policy và xử lý bản sao.

### 6.3. Không thể thu hồi password đã biết

Nếu attacker đã biết password, xóa verifier ở server ngăn đăng nhập bằng password đó tại hệ thống này, nhưng không thể làm attacker quên bí mật. Người dùng có thể đã dùng lại password ở dịch vụ khác. Thông báo và hướng dẫn thay password ở nơi khác khi có bằng chứng reuse hoặc compromise.

## 7. Hủy API key, client secret và workload secret

API key và client secret thường là bearer credential. Ai có secret có thể sử dụng quyền được gắn với nó.

### 7.1. Quy trình revoke

1. Xác định key ID, owner, scope, consumer và môi trường;
2. Chặn key tại authorization layer hoặc secret validation service;
3. Thu hồi token được cấp từ key nếu policy yêu cầu;
4. Cập nhật vault, cache và consumer;
5. Xóa secret cũ khỏi nguồn lưu trữ theo retention;
6. Xác minh request dùng key cũ bị từ chối;
7. Ghi audit và thông báo owner.

### 7.2. Rotate có kiểm soát

Với rotation định kỳ:

- Tạo key mới có scope tối thiểu;
- Lưu trong secret manager;
- Chuyển consumer sang key mới;
- Kiểm tra hoạt động;
- Revoke key cũ;
- Xóa version cũ theo retention.

Với compromise, có thể cần revoke ngay và chấp nhận downtime thay vì duy trì overlap.

### 7.3. Workload và container image

Không nhúng secret vào source code, image layer hoặc build log. Nếu secret từng nằm trong image, phát hành image mới không xóa layer cũ khỏi registry cache. Cần revoke secret, xử lý image/tag/layer theo chính sách registry và kiểm tra artifact/log liên quan.

## 8. Hủy access token, refresh token và session

Token và session có vòng đời riêng với credential đã tạo ra chúng.

### 8.1. Refresh token

Refresh token thường có thể được revoke tại authorization server. Nếu dùng rotation, phát hiện reuse có thể dẫn tới revoke cả token family. Khi account bị compromise hoặc deprovision, thu hồi refresh token và family liên quan theo policy.

### 8.2. Opaque access token

Opaque token có thể được kiểm tra qua introspection hoặc trạng thái server-side. Revoke record/token reference khiến resource server từ chối sau khi trạng thái được cập nhật và cache hết hiệu lực hoặc bị invalidated.

### 8.3. JWT access token tự chứa

JWT đã ký có thể tiếp tục được xác minh offline cho tới exp nếu resource server chỉ kiểm tra chữ ký và claim. Xóa record ở authorization server không làm các bản sao JWT biến mất.

Các biện pháp:

- TTL ngắn phù hợp với rủi ro;
- Introspection hoặc online status check cho action nhạy cảm;
- Denylist/revocation reference khi cần;
- Session/authorization version được kiểm tra tại API;
- Thu hồi signing key chỉ khi key thực sự bị compromise hoặc cần vô hiệu toàn bộ token đã ký bằng key đó.

Không xoay signing key toàn hệ thống chỉ để thu hồi một token người dùng nếu điều đó gây ảnh hưởng quá rộng. Chọn cơ chế revoke theo phạm vi.

### 8.4. Session cookie

Thu hồi session server-side, tăng session version hoặc đánh dấu session revoked; xóa cookie phía browser chỉ là bước UX. Cookie đã bị sao chép vẫn có thể được gửi tới server nếu session chưa bị vô hiệu.

## 9. Hủy passkey và WebAuthn registration

Với passkey/WebAuthn, RP thường lưu credential ID, public key, sign counter/metadata và account binding. Private key được giữ trong authenticator hoặc hệ sinh thái đồng bộ.

### 9.1. Hủy ở phía RP

- Đánh dấu registration revoked hoặc xóa khỏi danh sách credential active;
- Từ chối assertion mang credential ID đã revoke;
- Thu hồi session/token có liên quan nếu credential bị compromise;
- Ghi credential reference và thời điểm thu hồi;
- Thông báo người dùng và hướng dẫn xóa credential trên thiết bị nếu cần.

### 9.2. Giới hạn xóa từ xa

RP không có quyền xóa private key khỏi authenticator của người dùng. Xóa registration tại RP khiến server không còn tin credential đó, nhưng bản private key có thể còn trong thiết bị, cloud sync account hoặc backup của nền tảng.

Nếu thiết bị bị mất, cần revoke registration ở RP ngay; sau đó hướng dẫn người dùng xóa passkey khỏi thiết bị/hệ sinh thái khi có thể. Không chờ xóa vật lý trên thiết bị mới revoke phía server.

### 9.3. Credential ID và backup passkey

Một account có thể có nhiều passkey. Hủy một credential không nên vô tình xóa tất cả credential còn lại. Cần xác định đúng credential ID và tránh nhầm giữa nhiều thiết bị hoặc passkey đồng bộ.

## 10. Hủy TOTP, push authenticator và recovery code

### 10.1. TOTP seed

Server lưu secret TOTP để xác minh mã. Khi authenticator bị mất hoặc thay thế:

- Đánh dấu seed cũ revoked;
- Từ chối mọi TOTP tiếp theo từ seed đó;
- Xóa hoặc crypto-erase secret theo retention;
- Thu hồi các session/token liên quan khi có compromise;
- Đăng ký seed mới qua flow xác thực đủ mạnh.

Nếu secret được mã hóa bằng envelope encryption, xóa data encryption key (DEK) có thể giúp crypto-erase bản mã, nhưng phải xác minh mọi bản DEK/backup/replica và key-encryption-key (KEK) còn tồn tại thế nào.

### 10.2. Push authenticator

Thu hồi device binding, push subscription và key material dùng để xác minh thiết bị. Xóa subscription khỏi notification provider nếu được hỗ trợ. Không chỉ xóa tên thiết bị khỏi UI.

### 10.3. Recovery code

Đánh dấu mã đã dùng hoặc revoked; khi cấp bộ mới, vô hiệu toàn bộ bộ cũ. Nếu mã được lưu dưới dạng hash, xóa record/verifier theo retention. Không giữ plaintext trong audit để chứng minh đã hủy.

## 11. Certificate và private key

Certificate và private key có vai trò khác nhau:

- Certificate thường chứa public key và thông tin định danh; nó không phải bí mật;
- Private key là tài liệu mật dùng ký hoặc chứng minh quyền kiểm soát;
- Certificate revocation làm relying party biết chứng chỉ không còn được tin;
- Hủy private key làm mất khả năng tạo chữ ký mới bằng key đó, nhưng không xóa chữ ký đã tạo.

### 11.1. Thu hồi certificate

Với PKI, sử dụng cơ chế revoke phù hợp như CRL hoặc OCSP theo profile và hạ tầng. Relying party phải kiểm tra trạng thái theo policy; nếu chỉ kiểm tra chain và thời hạn mà không kiểm tra revocation, certificate bị revoke có thể vẫn được chấp nhận trong một số triển khai.

### 11.2. Hủy private key

Private key có thể nằm trong HSM, TPM, smart card, keystore, file hoặc secret manager. Dùng cơ chế zeroize/destroy của thiết bị hoặc nền tảng. Với HSM, cần xác minh key object đã bị hủy và bản backup/replica không thể khôi phục ngoài policy.

### 11.3. Key compromise

Nếu private key bị lộ:

1. Revoke certificate/key identity;
2. Cập nhật CRL/OCSP hoặc trust registry;
3. Thay key pair và cấp certificate mới;
4. Xác định chữ ký/token/dữ liệu nào có thể bị ảnh hưởng;
5. Thu hồi session/credential phụ thuộc;
6. Bảo toàn bằng chứng điều tra và xử lý bản sao theo incident policy.

## 12. Hủy signing key, encryption key và KMS material

Không phải mọi key đều là credential của người dùng, nhưng key material có thể xác thực, ký token hoặc bảo vệ credential khác.

### 12.1. Signing key

Nếu signing key ký JWT, SAML assertion hoặc artifact, hủy key có thể ảnh hưởng toàn bộ đối tượng được ký bằng key đó. Cần xác định phạm vi, thời gian overlap, key ID, verifier cache và token lifetime.

Nếu key bị compromise, ngừng ký bằng key đó, loại khỏi trust JWKS/metadata theo quy trình, phát hành key mới và đánh giá token đã ký. Nếu chỉ rotation định kỳ, giữ overlap theo policy để tránh làm hỏng token hợp lệ chưa hết hạn.

### 12.2. Encryption key và crypto-erasure

Nếu dữ liệu được mã hóa bằng DEK, hủy tất cả bản sao DEK có thể khiến ciphertext không thể giải mã. Đây là cryptographic erasure. Nó chỉ có hiệu lực nếu:

- Thuật toán mã hóa và key management phù hợp;
- Không còn bản sao key trong backup, export, memory dump hoặc hệ thống khác;
- KEK không thể tái tạo DEK;
- Key version và mapping được quản lý chính xác;
- Không có bản plaintext khác còn tồn tại.

Xóa một key reference khỏi database nhưng giữ key material trong KMS hoặc backup không phải crypto-erasure hoàn chỉnh.

### 12.3. Không hủy key dùng chung thiếu đánh giá

Một key có thể bảo vệ nhiều account hoặc tenant. Hủy key dùng chung có thể làm mất khả năng truy cập dữ liệu hợp lệ của nhiều người. Cần phân tích blast radius, migration, backup và quy trình khôi phục trước khi hủy.

## 13. Phương pháp hủy dữ liệu và media

Phương pháp phụ thuộc loại lưu trữ, mức nhạy cảm và yêu cầu của tổ chức.

| Phương pháp | Cách hoạt động | Giới hạn |
| --- | --- | --- |
| **Logical deletion** | Xóa record hoặc đánh dấu deleted | Bản sao có thể còn trong log, replica, backup |
| **Cryptographic erasure** | Hủy key khiến ciphertext không thể giải mã | Phải kiểm soát mọi bản sao key và plaintext |
| **Overwrite/sanitization** | Ghi đè hoặc dùng chức năng sanitize của media | Phụ thuộc loại thiết bị và controller |
| **Secure erase / sanitize command** | Lệnh do thiết bị hỗ trợ để xử lý vùng lưu trữ | Phải xác minh implementation và kết quả |
| **Physical destruction** | Phá hủy media theo quy trình được duyệt | Cần chain of custody và bằng chứng |
| **Memory zeroization** | Ghi đè vùng nhớ chứa secret | Runtime/compiler/GC có thể tạo bản sao khó kiểm soát |

### 13.1. SSD và wear leveling

Ghi đè một file trên SSD không đảm bảo mọi block vật lý từng chứa dữ liệu đã bị ghi đè do wear leveling, over-provisioning và controller remapping. Dùng chức năng sanitize/secure erase được nhà sản xuất hỗ trợ hoặc crypto-erasure với thiết kế mã hóa phù hợp; tuân thủ quy trình media sanitization của tổ chức.

### 13.2. Managed runtime

Trong runtime có garbage collector, immutable string hoặc copy-on-write, ứng dụng khó bảo đảm secret chỉ tồn tại ở một vùng nhớ. Zeroization chỉ có thể là best effort nếu thư viện/runtime không cung cấp primitive đáng tin. Hạn chế thời gian secret ở trong memory, dùng secret type/API chuyên dụng, tránh log và giải phóng buffer theo hướng dẫn nền tảng.

### 13.3. Cloud storage

Xóa object có thể chỉ tạo delete marker hoặc để lại version. Cần kiểm tra versioning, replication, snapshot, lifecycle rule, retention lock và provider deletion semantics. Không tuyên bố đã xóa hoàn toàn chỉ vì API trả thành công cho thao tác delete.

## 14. Backup, replica và immutable retention

Một credential có thể được lưu trong backup để phục hồi hệ thống. Việc xóa riêng một record khỏi backup bất biến có thể không khả thi hoặc bị cấm bởi retention policy.

### 14.1. Xử lý bản sao

- Xác định backup set và thời điểm hết hạn;
- Hạn chế quyền restore và truy cập backup;
- Mã hóa backup bằng key được quản lý riêng;
- Khi restore, chạy tombstone/revocation reconciliation trước khi đưa hệ thống phục vụ;
- Không để credential đã revoked sống lại sau restore;
- Xóa backup theo lịch retention đã phê duyệt.

### 14.2. Tombstone và revocation ledger

Nếu backup cũ có thể chứa credential đã hủy, hệ thống cần một nguồn trạng thái mới hơn như revocation ledger, account version hoặc tombstone. Khi khôi phục backup, áp dụng ledger để loại bỏ credential revoked trước khi cho phép authentication.

### 14.3. Legal hold và retention

Một số dữ liệu cần giữ vì điều tra, tranh chấp hoặc nghĩa vụ lưu trữ. Khi có legal hold, không tự ý xóa audit evidence. Tuy nhiên, cần tách bằng chứng cần giữ khỏi secret có thể dùng để xác thực. Có thể giữ credential identifier, hash, event metadata và chain of custody trong khi revoke key/secret.

## 15. Hủy credential trong hệ thống phân tán

Credential có thể được kiểm tra ở nhiều service, region và cache. Một thao tác revoke chỉ ở database chính có thể chưa đủ.

### 15.1. Revocation propagation

Một workflow có thể:

1. Ghi trạng thái revoked và tăng credential/account version tại nguồn có thẩm quyền;
2. Phát sự kiện qua transactional outbox;
3. Consumer cập nhật cache, replica và authorization service;
4. Resource server kiểm tra version/status hoặc introspection;
5. Dịch vụ tích hợp nhận revoke event/API call;
6. Reconciliation xác nhận mọi consumer đã áp dụng;
7. Chỉ sau đó mới purge key material theo retention.

### 15.2. Fencing và stale cache

Version tăng dần có thể giúp API từ chối trạng thái cũ. Ví dụ, credential version trong request/token thấp hơn version hiện tại thì không được chấp nhận. Cơ chế chỉ hiệu quả nếu mọi điểm xác thực quyền đều kiểm tra version và cache có invalidation/TTL rõ.

### 15.3. Event delivery

Event có thể trễ, trùng hoặc đến sai thứ tự. Consumer cần idempotency và version check. Nếu event revoke bị mất, reconciliation phải phát hiện. Với credential bị compromise, có thể cần online deny check cho action nhạy cảm thay vì chờ event bus.

### 15.4. In-flight request

Một request có thể đã qua authentication trước khi revoke nhưng chưa commit action. Với thao tác nhạy cảm, kiểm tra lại account/credential/session version tại điểm commit. Không để request bắt đầu trước revoke mặc nhiên hoàn tất sau revoke nếu policy yêu cầu chặn ngay.

## 16. Hủy credential khi nghỉ việc, mất thiết bị hoặc compromise

### 16.1. Nhân viên rời tổ chức

- Thu hồi membership và role;
- Disable/revoke password, passkey, certificate và API key thuộc tổ chức;
- Thu hồi session, refresh token và service credential;
- Xóa thiết bị khỏi MDM/IdP theo policy;
- Xử lý mailbox, data ownership và workload đang chạy;
- Cập nhật SSO/SCIM và các ứng dụng downstream;
- Lưu audit và bằng chứng hoàn tất.

### 16.2. Mất thiết bị

- Revoke passkey registration hoặc device-bound credential tại RP;
- Thu hồi session và refresh token trên thiết bị;
- Gỡ device binding và push subscription;
- Đánh giá dữ liệu/secret có lưu trên thiết bị;
- Hướng dẫn xóa credential trên hệ sinh thái khi người dùng còn khả năng;
- Cấp credential dự phòng qua recovery flow đủ mạnh.

### 16.3. Credential bị lộ

Ưu tiên containment:

1. Chặn credential tại verifier/resource server;
2. Thu hồi token/session được tạo từ credential đó;
3. Xoay credential phụ thuộc nếu cùng secret/key bị dùng ở nhiều nơi;
4. Xác định thời điểm và phạm vi lộ;
5. Tìm bản sao trong log, artifact, backup và hệ thống bên ngoài;
6. Thông báo và recovery theo policy;
7. Hủy key material/bản sao sau khi bảo toàn bằng chứng cần thiết.

Không chờ hoàn tất mọi bước purge mới revoke quyền sử dụng.

## 17. Bằng chứng và xác minh destruction

Một thao tác delete thành công không tự chứng minh credential không còn được sử dụng. Cần kiểm tra theo loại credential và phạm vi hệ thống.

### 17.1. Bằng chứng có thể ghi

- Credential ID/key ID;
- Principal/tenant reference;
- Loại thao tác: disabled, revoked, rotated, destroyed;
- Actor, approver và lý do;
- Thời điểm bắt đầu/kết thúc;
- Hệ thống/replica/provider đã xác nhận;
- Policy/retention version;
- Kết quả test xác minh credential cũ bị từ chối;
- Ngoại lệ hoặc bản sao còn trong retention.

Không lưu secret gốc làm bằng chứng hủy. Không chụp hoặc export private key/recovery code để chứng minh nó từng tồn tại.

### 17.2. Kiểm tra âm tính

Thử dùng credential cũ trong môi trường kiểm thử hoặc request kiểm soát và xác nhận bị từ chối. Với JWT tự chứa, xác minh resource server thực sự áp dụng revocation/version/introspection hoặc token đã hết hạn theo policy. Với passkey, thử assertion từ credential ID đã revoke và xác nhận RP từ chối.

### 17.3. Kiểm tra mọi consumer

Có thể dùng inventory và acknowledgement để xác nhận từng service đã nhận revoke event. Nếu một consumer không phản hồi, ghi rõ trạng thái pending và áp dụng biện pháp containment thay vì đánh dấu hoàn tất toàn bộ.

## 18. Quyền hạn và separation of duties

Hủy credential có thể gây gián đoạn hoặc làm mất khả năng truy cập dữ liệu. Thao tác cần quyền hạn tương xứng.

- Người dùng có thể tự revoke credential của mình sau khi xác thực;
- Admin chỉ được quản lý credential trong scope được giao;
- Hủy signing key/KMS key dùng chung cần approval và impact review;
- Break-glass revoke cần audit độc lập;
- Người yêu cầu và người phê duyệt có thể cần tách biệt với thay đổi có blast radius lớn;
- Không cho client tự gửi credential ID của người khác rồi yêu cầu xóa mà không kiểm tra ownership.

Trong tình huống compromise đang diễn ra, emergency revoke có thể được thực hiện nhanh theo policy; cần hậu kiểm, lý do và audit sau đó.

## 19. Pseudocode revoke và destroy

~~~text
revoke_credential(credential_ref, actor, reason):
    require actor_is_authorized_for_scope(actor, credential_ref)
    require reason_is_recorded(reason)

    begin transaction
    credential = load_credential_for_update(credential_ref)
    require credential exists
    if credential.status in [REVOKED, DESTROYED]:
        return existing_result

    credential.status = REVOKED
    credential.version = credential.version + 1
    credential.revoked_at = now
    write_audit_event_without_secret(credential, actor, reason)
    write_outbox_event("CREDENTIAL_REVOKED", credential.ref, credential.version)
    commit

    notify_dependents_and_revoke_derived_sessions(credential)
    verify_old_credential_is_rejected(credential)
    return REVOCATION_PENDING_OR_CONFIRMED
~~~

~~~text
destroy_credential_material(credential_ref, retention_policy):
    require credential.status == REVOKED
    require dependent_services_acknowledged_or_exception_approved()
    require retention_policy_allows_destruction()
    require legal_hold_checked()

    identify_all_key_and_secret_copies(credential_ref)
    destroy_or_crypto_erase_material_using_platform_api()
    verify_no_active_key_reference_remains()
    record_destruction_evidence_without_secret()
    return DESTROYED_OR_EXCEPTION_RECORDED
~~~

Đây là pseudocode mô tả trình tự. Thực tế cần idempotency, transaction/outbox, retry, timeout, provider-specific deletion API, approval, retention check và xử lý partial failure. Không đánh dấu DESTROYED nếu chỉ revoke ở một service nhưng các bản sao hoặc consumer khác chưa được kiểm tra.

## 20. Kiểm thử credential destruction

Test trong môi trường staging hoặc môi trường thử nghiệm của secret manager/HSM. Dùng credential giả, key thử và dữ liệu không nhạy cảm.

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Password | Đăng nhập bằng password cũ sau reset | Bị từ chối |
| Password verifier | Xóa account theo policy | Verifier cũ không còn được dùng |
| API key | Gọi API bằng key đã revoke | Bị từ chối |
| Secret rotation | Consumer chuyển sang secret mới | Secret cũ bị revoke sau cutover |
| Refresh token | Dùng refresh token đã revoke | Token endpoint từ chối |
| JWT access token | Token cũ sau role/credential revoke | Resource server từ chối theo version/revocation/expiry policy |
| Session | Dùng cookie đã revoke | Server từ chối dù cookie còn ở browser |
| Passkey | Assertion từ credential ID đã revoke | RP từ chối |
| TOTP | Dùng seed đã revoke | Mã không còn hợp lệ |
| Recovery code | Dùng mã đã consumed/revoked | Từ chối |
| Certificate | Dùng certificate đã revoked | Relying party phát hiện trạng thái revoke theo policy |
| Private key | Ký bằng key đã destroy trong HSM | Thiết bị từ chối thao tác |
| Cache | Cache còn trạng thái active cũ | Version/invalidation ngăn chấp nhận stale state |
| Replica | Read replica cập nhật trễ | Action nhạy cảm fail closed hoặc chờ đồng bộ |
| Event loss | Revoke event không tới consumer | Reconciliation phát hiện và retry |
| Out-of-order | Event cũ đến sau event revoke mới | Consumer không phục hồi trạng thái active |
| Backup restore | Restore snapshot cũ có credential revoked | Tombstone/revocation ledger áp dụng trước khi phục vụ |
| Object version | Delete marker nhưng version cũ còn | Lifecycle/sanitization xử lý đúng retention |
| Legal hold | Credential evidence cần giữ | Giữ metadata cần thiết, secret vẫn bị revoke |
| In-flight request | Request qua auth trước revoke, commit sau revoke | Kiểm tra version tại commit theo policy |
| Partial failure | Một provider không xác nhận destruction | Không báo hoàn tất toàn bộ; ghi exception và containment |
| Audit | Hủy credential | Có actor, scope, reason và evidence, không có secret |

### 20.1. Bất biến bảo mật

- Credential đã revoked không được chấp nhận tại bất kỳ verifier nào trong phạm vi SLA;
- Xóa record không được coi là đã hủy mọi bản sao;
- JWT tự chứa và session phải có cơ chế revoke/expiry phù hợp;
- Private key của authenticator không được giả định có thể xóa từ xa;
- Certificate public và private key được xử lý riêng;
- Backup restore không được làm sống lại credential đã revoked;
- Không destroy key dùng chung khi chưa đánh giá blast radius/retention;
- Audit chứng minh thao tác mà không lưu lại secret.

## 21. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Xóa database row rồi coi như xong | Cache, backup hoặc token vẫn hoạt động | Revoke propagation và destruction inventory |
| Chỉ xóa cookie phía client | Session cookie bị sao chép vẫn dùng được | Revoke server-side session |
| Nghĩ JWT biến mất khi xóa record | Token tự chứa còn được verify tới exp | Short TTL, introspection, version hoặc denylist |
| Xóa passkey ở UI nhưng không revoke verifier | RP vẫn chấp nhận assertion | Revoke credential ID tại server |
| Nghĩ có thể xóa private key passkey từ xa | Đánh giá sai khả năng kiểm soát thiết bị | Revoke phía RP và hướng dẫn xóa trên authenticator |
| Revoke certificate nhưng bỏ private key | Key bị lộ vẫn có thể ký | Revoke cert và destroy/rotate private key |
| Ghi secret vào log | Secret tồn tại trong index/export | Không log secret; xử lý incident nếu đã lộ |
| Xóa object nhưng còn version | Bản sao dữ liệu vẫn truy cập được | Xử lý versioning/retention/lifecycle |
| Restore backup làm sống credential cũ | Credential revoked được chấp nhận lại | Tombstone/revocation ledger |
| Không revoke derived session/token | Attacker tiếp tục truy cập | Dependency mapping và revoke theo policy |
| Xóa KMS key dùng chung không đánh giá | Mất dữ liệu của nhiều tenant | Impact review, approval và staged migration |
| Zeroize managed string nhưng còn bản sao | Secret vẫn tồn tại trong memory | Giảm lifetime, API phù hợp và không hứa bảo đảm tuyệt đối |
| Đánh dấu DESTROYED khi provider chưa xác nhận | Báo cáo sai trạng thái | Partial state, acknowledgement và exception |

## 22. Checklist production

1. **Inventory:** Credential ID, owner, scope, issuer, consumer và nơi lưu đã được xác định?
2. **Classification:** Đây là password verifier, bearer secret, token, public key, private key hay encryption key?
3. **Dependency:** Session, token, cache, service, device và third-party dependency đã được liệt kê?
4. **Revocation:** Có thể chặn credential tại mọi verifier trước khi purge không?
5. **Derived access:** Session, refresh/access token, API key hoặc certificate phụ thuộc được xử lý?
6. **Propagation:** Replica, cache, event consumer và provider có acknowledgement/reconciliation?
7. **Client side:** Credential trên authenticator/thiết bị có giới hạn xóa từ xa được giải thích đúng?
8. **Storage:** Database, vault, HSM, KMS, object version và container image có phương án hủy?
9. **Backup:** Retention, immutable backup, restore và tombstone có được kiểm soát?
10. **Crypto-erasure:** Mọi bản sao DEK/KEK và plaintext có được xem xét?
11. **Media:** Phương pháp sanitize phù hợp SSD/HDD/flash/HSM và quy trình của tổ chức?
12. **Memory/logs:** Secret không bị log; memory handling có giới hạn và được hiểu đúng?
13. **Retention/legal hold:** Bằng chứng cần giữ được tách khỏi secret có thể dùng xác thực?
14. **Authorization:** Actor, approver và scope có hợp lệ; key dùng chung có impact review?
15. **Verification:** Credential cũ bị từ chối ở mọi consumer trong SLA?
16. **Audit:** Có evidence, exception, policy version và trạng thái partial/complete?
17. **Recovery:** Credential mới được cấp qua quy trình đủ mạnh và session cũ được xử lý?
18. **Testing:** Có test replay, stale cache, backup restore, race, partial failure và in-flight request?

## 23. Bài tập tình huống

Một nhân viên rời công ty. Admin xóa tài khoản trong database và xóa cookie khỏi trình duyệt công ty. Nhân viên từng có passkey trên điện thoại cá nhân, API key trong một CI secret store, refresh token trong ứng dụng mobile và certificate client được cài trên laptop. Một số API dùng JWT access token tự chứa với TTL 8 giờ; cache role có TTL 30 phút. Backup database được giữ 90 ngày.

**Yêu cầu:**

1. Liệt kê các credential, verifier, token, session và bản sao cần xử lý.
2. Phân biệt thao tác revoke, disable, rotate và destroy cho từng loại.
3. Thiết kế thứ tự containment và revoke để ngăn truy cập ngay cả khi backup chưa hết hạn.
4. Đề xuất xử lý passkey trên điện thoại cá nhân và certificate trên laptop.
5. Thiết kế cơ chế xử lý JWT cũ, refresh token và cache role stale.
6. Mô tả cách dùng tombstone/revocation ledger khi restore backup.
7. Xác định bằng chứng nào cần giữ cho audit và dữ liệu bí mật nào phải hủy.
8. Viết test chứng minh mọi credential cũ bị từ chối sau khi quy trình hoàn tất.

**Gợi ý đối chiếu:** revoke account/membership và credential ở nguồn có thẩm quyền trước; thu hồi refresh token/session; API cần version/introspection/TTL phù hợp cho JWT; revoke passkey registration tại RP và hướng dẫn xóa trên authenticator; revoke certificate và xử lý private key; xóa API secret khỏi vault/CI; cache invalidation; restore phải áp dụng tombstone; backup retention không được làm credential sống lại.

## 24. Ghi nhớ

- **Credential destruction** kết thúc khả năng sử dụng credential và xử lý an toàn các bản sao/key material; nó rộng hơn xóa một record.
- Phân biệt disable, revoke, rotate, logical delete và destroy. Thông thường phải revoke trước rồi purge/destroy theo retention.
- Mỗi loại credential có cách xử lý riêng: password verifier, token, API secret, passkey registration, TOTP seed, recovery code, certificate và private key.
- JWT tự chứa có thể còn được chấp nhận tới exp; session/token phụ thuộc phải được thu hồi riêng.
- RP có thể revoke passkey registration nhưng không thể xóa private key khỏi authenticator từ xa. Certificate công khai và private key cần được xử lý riêng.
- Backup, replica, cache, object version, log, container image và hệ thống bên thứ ba đều có thể giữ bản sao.
- Cryptographic erasure chỉ hiệu quả khi mọi bản sao key material và plaintext được kiểm soát; xóa key reference chưa đủ.
- Restore backup phải áp dụng revocation ledger/tombstone để không làm sống lại credential đã hủy.
- Bằng chứng destruction cần ghi actor, scope, reason và kết quả mà không lưu lại secret.

Credential destruction an toàn khi hệ thống có thể chứng minh **credential đã bị từ chối ở mọi điểm xác minh, các quyền phát sinh từ nó đã được xử lý, key material và bản sao được hủy theo retention, và việc khôi phục backup không làm credential cũ sống lại**.
